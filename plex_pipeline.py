#!/usr/bin/env python3
"""
Unified Plex media pipeline: Rename + Transcode in one step
Combines plex_renamer.py and plex_transcoder.py functionality
"""
import argparse
import shutil
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional, Tuple

# Import shared functionality from common module
import plex_common
from plex_common import (
    VIDEO_EXTENSIONS,
    VideoInfo,
    run_cmd,
    which_or_die,
    ffprobe_video_info,
    is_4k,
    looks_hdr,
    build_ffmpeg_cmd,
    parse_tv_filename,
    parse_date_in_filename,
    rename_tv_file,
    rename_movie_file,
)

__version__ = "1.0.0"

# Thread-safe printing
print_lock = threading.Lock()


def safe_print(*args, **kwargs):
    """Thread-safe print function."""
    with print_lock:
        print(*args, **kwargs)


# ============================================================================
# Pipeline Functions
# ============================================================================

from dataclasses import dataclass


@dataclass
class StagedFile:
    """Represents a file that has been staged and is ready for transcoding."""
    source: Path
    target: Path
    info: Optional[VideoInfo]
    force_audio_aac: bool
    include_subs: bool
    is_copy_only: bool = False
    status: str = "STAGED"


# noinspection DuplicatedCode
def stage_file(file: Path, output_root: Path, manual_root: Path, args) -> Tuple[
    Path, Optional[Path], str, Optional[StagedFile]]:
    """Stage a file: determine target path and check if transcoding is needed. Returns (source, target, status, staged_file)."""

    # Step 1: Determine new name and path
    season, episode = parse_tv_filename(file.stem)
    date_str, date_year = (None, None) if (season is not None) else parse_date_in_filename(file.stem)
    is_tv = (season is not None) or (date_str is not None)

    new_file_path = None
    base_dest = None
    subdir = None

    if is_tv:
        result = rename_tv_file(file, season, episode, date_str=date_str, date_year=date_year)
        if result:
            new_file_path, matched, renamable = result
            subdir = 'TV Shows'
            if not renamable:
                base_dest = manual_root
            else:
                base_dest = output_root
    else:
        result = rename_movie_file(file)
        if result:
            new_file_path, matched, renamable = result
            subdir = 'Movies'
            if not renamable:
                base_dest = manual_root
            else:
                base_dest = output_root

    if not result or new_file_path is None or base_dest is None or subdir is None:
        return file, None, "SKIP (could not process)", None

    target = (base_dest / subdir / new_file_path).resolve()

    # Manual review files - move immediately (no transcoding needed)
    if base_dest == manual_root:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(file), str(target))
        return file, target, "MANUAL REVIEW (moved)", None

    target = target.with_suffix(".mp4")  # Always output as MP4

    if target.exists() and not args.overwrite:
        return file, target, "SKIP (already exists)", None

    info = ffprobe_video_info(file)
    if not info:
        staged = StagedFile(file, target, None, False, False, is_copy_only=True)
        return file, target, "STAGED (no codec info)", staged

    if args.skip_hevc and info.codec.lower() == "hevc":
        staged = StagedFile(file, target, info, False, False, is_copy_only=True)
        return file, target, "STAGED (HEVC copy)", staged

    # Needs transcoding
    force_audio_aac = args.force_audio_aac or (file.suffix.lower() == ".avi")
    include_subs = not args.no_subs

    if args.dry_run:
        return file, target, "DRY-RUN", None

    staged = StagedFile(file, target, info, force_audio_aac, include_subs, is_copy_only=False)
    return file, target, "STAGED", staged


# noinspection DuplicatedCode
def transcode_file(staged: StagedFile, args) -> Tuple[Path, Optional[Path], str]:
    """Transcode a staged file."""
    file = staged.source
    target = staged.target

    target.parent.mkdir(parents=True, exist_ok=True)

    # Handle copy-only files - use move if delete_source is enabled
    if staged.is_copy_only:
        if args.delete_source:
            shutil.move(str(file), str(target))
            return file, target, "MOVED"
        else:
            shutil.copy2(str(file), str(target))
            return file, target, "COPY"

    # Transcode
    if not staged.info:
        # Should never happen for non-copy files, but handle gracefully
        return file, None, "FAIL (no video info)"

    cmd = build_ffmpeg_cmd(file, target, staged.info, staged.force_audio_aac, staged.include_subs)

    safe_print(f"[TRANSCODE] Starting: {file.name} -> {target.name}")
    if args.debug:
        is_4k_video = is_4k(staged.info)
        is_hdr_video = looks_hdr(staged.info)
        safe_print(f"  └─ Source: {staged.info.codec.upper()} {staged.info.width}x{staged.info.height}")
        safe_print(f"  └─ Target: HEVC (H.265) {'4K' if is_4k_video else '1080p'} {'HDR' if is_hdr_video else 'SDR'}")
        safe_print(
            f"  └─ Audio: {'AAC' if staged.force_audio_aac else 'Copy'} | Subtitles: {'Yes' if staged.include_subs else 'No'}")

    code, out, err = run_cmd(cmd)

    if code != 0:
        msg = f"FAIL (ffmpeg code {code})"
        if "Subtitle" in err or "subtitles" in err or "codec" in err:
            msg += " — (maybe subtitle issue; try --no-subs)"
        safe_print(f"[ERROR] Transcoding failed: {file.name}")
        if args.debug:
            safe_print(f"  └─ Error: {err[:200]}")
        return file, None, msg

    safe_print(f"[TRANSCODE] Completed: {file.name}")

    if args.delete_source:
        try:
            file.unlink()
            return file, target, "OK (source deleted)"
        except Exception as e:
            return file, target, f"OK (failed to delete source: {e})"

    return file, target, "OK"


# Legacy function for compatibility
# noinspection DuplicatedCode
def process_file(file: Path, output_root: Path, manual_root: Path, args) -> Tuple[Path, Optional[Path], str]:
    """Process a single file: rename + transcode in one step."""

    # Step 1: Determine new name and path
    season, episode = parse_tv_filename(file.stem)
    date_str, date_year = (None, None) if (season is not None) else parse_date_in_filename(file.stem)
    is_tv = (season is not None) or (date_str is not None)

    new_file_path = None
    base_dest = None
    subdir = None

    if is_tv:
        result = rename_tv_file(file, season, episode, date_str=date_str, date_year=date_year)
        if result:
            new_file_path, matched, renamable = result
            subdir = 'TV Shows'
            if not renamable:
                base_dest = manual_root
            else:
                base_dest = output_root
    else:
        result = rename_movie_file(file)
        if result:
            new_file_path, matched, renamable = result
            subdir = 'Movies'
            if not renamable:
                base_dest = manual_root
            else:
                base_dest = output_root

    if not result or new_file_path is None or base_dest is None or subdir is None:
        return file, None, "SKIP (could not process)"

    if base_dest == manual_root:
        target = (base_dest / subdir / new_file_path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(file), str(target))
        return file, target, "MANUAL REVIEW"

    # Step 2: Transcode directly to final location
    target = (base_dest / subdir / new_file_path).resolve()
    target = target.with_suffix(".mp4")  # Always output as MP4

    if target.exists() and not args.overwrite:
        return file, target, "SKIP (already exists)"

    info = ffprobe_video_info(file)
    if not info:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(file), str(target))
        return file, target, "COPY (ffprobe failed)"

    if args.skip_hevc and info.codec.lower() == "hevc":
        # Already HEVC, just copy with new name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(file), str(target))
        if args.delete_source:
            file.unlink()
            return file, target, "COPY HEVC (source deleted)"
        return file, target, "COPY HEVC"

    # Transcode
    force_audio_aac = args.force_audio_aac or (file.suffix.lower() == ".avi")
    include_subs = not args.no_subs

    cmd = build_ffmpeg_cmd(file, target, info, force_audio_aac=force_audio_aac, include_subs=include_subs)

    if args.dry_run:
        return file, target, "DRY-RUN"

    # Log transcoding start
    safe_print(f"[TRANSCODE] Starting: {file.name} -> {target.name}")
    if args.debug:
        # User-friendly debug info
        is_4k_video = is_4k(info)
        is_hdr_video = looks_hdr(info)
        safe_print(f"  └─ Source: {info.codec.upper()} {info.width}x{info.height}")
        safe_print(f"  └─ Target: HEVC (H.265) {'4K' if is_4k_video else '1080p'} {'HDR' if is_hdr_video else 'SDR'}")
        safe_print(f"  └─ Audio: {'AAC' if force_audio_aac else 'Copy'} | Subtitles: {'Yes' if include_subs else 'No'}")

    code, out, err = run_cmd(cmd)

    if code != 0:
        msg = f"FAIL (ffmpeg code {code})"
        if "Subtitle" in err or "subtitles" in err or "codec" in err:
            msg += " — (maybe subtitle issue; try --no-subs)"
        safe_print(f"[ERROR] Transcoding failed: {file.name}")
        if args.debug:
            safe_print(f"  └─ Error: {err[:200]}")  # First 200 chars of error
        return file, None, msg

    safe_print(f"[TRANSCODE] Completed: {file.name}")

    if args.delete_source:
        try:
            file.unlink()
            return file, target, "OK (source deleted)"
        except Exception as e:
            return file, target, f"OK (failed to delete source: {e})"

    return file, target, "OK"


def main():
    parser = argparse.ArgumentParser(
        description="Unified Plex pipeline: Rename and transcode media files in one step. "
                    "Uses TMDb API for metadata and Apple VideoToolbox for hardware transcoding.",
        epilog="Example: python3 plex_pipeline.py ./1.Rename --skip-hevc --delete-source"
    )
    parser.add_argument("source", help="Source folder containing video files to process")
    parser.add_argument("--output-root", help="Output folder for processed files (default: 4.Upload)")
    parser.add_argument("--manual-root", help="Output folder for files needing review (default: X.Issues)")
    parser.add_argument("--workers", type=int, default=4, help="Concurrent processes (default: 4)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without processing")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing outputs")
    parser.add_argument("--skip-hevc", action="store_true", help="Skip transcoding files already in HEVC (recommended)")
    parser.add_argument("--force-audio-aac", action="store_true", help="Force AAC audio for all files")
    parser.add_argument("--no-subs", action="store_true", help="Don't include subtitle streams")
    parser.add_argument("--delete-source", action="store_true",
                        help="Move/delete source files after processing (saves storage space)")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args()

    plex_common.DEBUG = args.debug

    which_or_die("ffmpeg")
    which_or_die("ffprobe")

    source_root = Path(args.source).expanduser().resolve()
    if not source_root.exists():
        print(f"ERROR: Source folder does not exist: {source_root}", file=sys.stderr)
        sys.exit(2)

    # Infer output paths using common module
    inferred_output, inferred_manual = plex_common.infer_output_roots(source_root)

    output_root = Path(args.output_root).resolve() if args.output_root else inferred_output
    manual_root = Path(args.manual_root).resolve() if args.manual_root else inferred_manual

    output_root.mkdir(parents=True, exist_ok=True)
    manual_root.mkdir(parents=True, exist_ok=True)

    # Find all video files
    all_files = [f for f in source_root.rglob("*") if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS]

    if not all_files:
        print("No video files found.")
        return

    print(f"Found {len(all_files)} files in: {source_root}")
    print(f"Output: {output_root}")
    print(f"Manual review: {manual_root}")
    print(f"Workers: {args.workers} | skip-hevc: {args.skip_hevc}")

    if args.delete_source:
        print(f"⚠️  Storage Mode: Source files will be MOVED/DELETED (saves space)")
    else:
        print(f"ℹ️  Storage Mode: Source files will be KEPT (uses more space)")
    print()

    # Phase 1: Stage all files (fast - just lookups and file checks)
    safe_print("\n=== Phase 1: Staging files ===")
    staged_files = []
    results = []

    for idx, file in enumerate(all_files, 1):
        progress_pct = (idx / len(all_files)) * 100
        source_file, dest_file, status, staged = stage_file(file, output_root, manual_root, args)

        if staged:
            staged_files.append(staged)

        if status not in ["STAGED", "STAGED (HEVC copy)", "STAGED (no codec info)"]:
            results.append((source_file, dest_file, status))

        if dest_file and status not in ["STAGED", "STAGED (HEVC copy)", "STAGED (no codec info)"]:
            safe_print(f"[{idx}/{len(all_files)} - {progress_pct:.1f}%] [{status}] {source_file.name}")

    safe_print(f"\nStaging complete: {len(staged_files)} files ready for transcoding, {len(results)} already processed")

    if not staged_files:
        safe_print("No files need transcoding.")
    else:
        # Phase 2: Transcode staged files (slow - actual video processing)
        safe_print(f"\n=== Phase 2: Transcoding {len(staged_files)} files ===\n")
        transcoded = 0

        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(transcode_file, staged, args): staged for staged in staged_files}
            for fut in as_completed(futs):
                source_file, dest_file, status = fut.result()
                results.append((source_file, dest_file, status))
                transcoded += 1

                progress_pct = (transcoded / len(staged_files)) * 100
                if dest_file:
                    safe_print(
                        f"[{transcoded}/{len(staged_files)} - {progress_pct:.1f}%] [{status}] {source_file.name} -> {dest_file.name}")
                else:
                    safe_print(
                        f"[{transcoded}/{len(staged_files)} - {progress_pct:.1f}%] [{status}] {source_file.name}")

    ok = sum(1 for _, _, s in results if "OK" in s or "COPY" in s)
    skip = sum(1 for _, _, s in results if s.startswith("SKIP"))
    manual = sum(1 for _, _, s in results if s.startswith("MANUAL"))
    fail = sum(1 for _, _, s in results if s.startswith("FAIL"))
    dry = sum(1 for _, _, s in results if s.startswith("DRY-RUN"))

    print(f"\n🎉 Done. OK={ok} MANUAL={manual} SKIP={skip} FAIL={fail} DRY-RUN={dry}")


if __name__ == "__main__":
    main()
