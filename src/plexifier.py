"""
Unified Plex media pipeline: Rename + Transcode in one step
Combines plex_renamer.py and plex_transcoder.py functionality
"""
import argparse
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import plex
from plex import rename, transcode, STATUS_STAGED, CONTENT_TYPE_TV, CONTENT_TYPE_MOVIES, STATUS_SKIP, STATUS_MANUAL, \
    STATUS_FAIL, STATUS_STAGED_NO_INFO, STATUS_STAGED_HEVC, STATUS_DRY_RUN, STATUS_MOVED, STATUS_COPY, STATUS_OK, DEBUG
from plex.utils import logger, system_util, file_util

in_debug_mode = DEBUG


@dataclass
class StagedFile:
    """Represents a file that has been staged and is ready for transcoding."""
    source: Path
    target: Path
    info: Optional[transcode.VideoInfo]
    force_audio_aac: bool
    include_subs: bool
    is_copy_only: bool = False
    status: str = STATUS_STAGED


def stage_file(file: Path, output_root: Path, manual_root: Path, args) -> Tuple[
    Path, Optional[Path], str, Optional[StagedFile]]:
    """Stage a file: determine target path and check if transcoding is needed. Returns (source, target, status, staged_file)."""

    # Determine new name and path
    season, episode = rename.parse_tv_filename(file.stem)
    date_str, date_year = (None, None) if (season is not None) else rename.parse_date_in_filename(file.stem)
    is_tv = (season is not None) or (date_str is not None)

    new_file_path = None
    base_dest = None
    subdir = None

    if is_tv:
        result = rename.rename_tv_file(file, season, episode, date_str=date_str, date_year=date_year)
        if result:
            new_file_path, matched, renamable = result
            subdir = CONTENT_TYPE_TV
            if not renamable:
                base_dest = manual_root
            else:
                base_dest = output_root
    else:
        result = rename.rename_movie_file(file)
        if result:
            new_file_path, matched, renamable = result
            subdir = CONTENT_TYPE_MOVIES
            if not renamable:
                base_dest = manual_root
            else:
                base_dest = output_root

    if not result or new_file_path is None or base_dest is None or subdir is None:
        return file, None, f"{STATUS_SKIP} (could not process)", None

    target = (base_dest / subdir / new_file_path).resolve()

    # Manual review files - move immediately (no transcoding needed)
    if base_dest == manual_root:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(file), str(target))
            return file, target, f"{STATUS_MANUAL} (moved)", None
        except (OSError, shutil.Error, PermissionError) as e:
            return file, None, f"{STATUS_FAIL} (move error: {e})", None

    target = target.with_suffix(".mp4")  # Always output as MP4

    info = transcode.ffprobe_video_info(file)
    if not info:
        if target.exists() and not args.overwrite:
            return file, target, f"{STATUS_SKIP} (already exists)", None
        staged = StagedFile(file, target, None, False, False, is_copy_only=True)
        return file, target, STATUS_STAGED_NO_INFO, staged

    if args.skip_hevc and info.codec.lower() == "hevc":
        if target.exists() and not args.overwrite:
            return file, target, f"{STATUS_SKIP} (already exists)", None
        staged = StagedFile(file, target, info, False, False, is_copy_only=True)
        return file, target, STATUS_STAGED_HEVC, staged

    # Check if target exists before transcoding
    if target.exists() and not args.overwrite:
        return file, target, f"{STATUS_SKIP} (already exists)", None

    # Needs transcoding
    force_audio_aac = args.force_audio_aac or (file.suffix.lower() == ".avi")
    include_subs = not args.no_subs

    staged = StagedFile(file, target, info, force_audio_aac, include_subs, is_copy_only=False)

    if args.dry_run:
        return file, target, STATUS_DRY_RUN, staged

    return file, target, STATUS_STAGED, staged


def transcode_file(staged: StagedFile, args) -> Tuple[Path, Optional[Path], str]:
    """Transcode a staged file."""
    file = staged.source
    target = staged.target

    # Dry-run mode - just report what would happen
    if args.dry_run:
        return file, target, STATUS_DRY_RUN

    target.parent.mkdir(parents=True, exist_ok=True)

    # Handle copy-only files - use move if delete_source is enabled
    if staged.is_copy_only:
        try:
            if args.delete_source:
                shutil.move(str(file), str(target))
                return file, target, STATUS_MOVED
            else:
                shutil.copy2(str(file), str(target))
                return file, target, STATUS_COPY
        except (OSError, shutil.Error, PermissionError) as e:
            return file, None, f"{STATUS_FAIL} (copy/move error: {e})"

    # Transcode
    if not staged.info:
        # Should never happen for non-copy files, but handle gracefully
        return file, None, f"{STATUS_FAIL} (no video info)"

    cmd = transcode.build_ffmpeg_cmd(file, target, staged.info, staged.force_audio_aac, staged.include_subs)

    logger.log_transcode_start(file.name, target.name)
    if args.debug:
        is_4k_video = transcode.is_4k(staged.info)
        is_hdr_video = transcode.looks_hdr(staged.info)
        logger.log_detail(f"Source: {staged.info.codec.upper()} {staged.info.width}x{staged.info.height}")
        logger.log_detail(f"Target: HEVC (H.265) {'4K' if is_4k_video else '1080p'} {'HDR' if is_hdr_video else 'SDR'}")
        logger.log_detail(
            f"Audio: {'AAC' if staged.force_audio_aac else 'Copy'} | Subtitles: {'Yes' if staged.include_subs else 'No'}")

    code, out, err = system_util.run_cmd(cmd)

    if code != 0:
        msg = f"{STATUS_FAIL} (ffmpeg code {code})"
        if "Subtitle" in err or "subtitles" in err or "codec" in err:
            msg += " — (maybe subtitle issue; try --no-subs)"
        logger.log_transcode_failed(file.name)
        if args.debug:
            logger.log_detail(f"Error: {err[:200]}")
        return file, None, msg

    logger.log_transcode_complete(file.name)

    if args.delete_source:
        try:
            file.unlink()
            return file, target, f"{STATUS_OK} (source deleted)"
        except (OSError, PermissionError) as e:
            return file, target, f"{STATUS_OK} (failed to delete source: {e})"

    return file, target, STATUS_OK


def main():
    parser = argparse.ArgumentParser(
        description="Plexify your files! Rename and transcode media files for use with a Plex Media Server. "
                    "Uses TMDb API for metadata and Apple VideoToolbox for hardware transcoding.",
        epilog="Example: plex-pipeline ./ToProcess --skip-hevc --delete-source"
    )
    parser.add_argument("source", help="Source folder containing video files to process")
    parser.add_argument("--output-root", help="Output folder for processed files (default: Processed)")
    parser.add_argument("--manual-root", help="Output folder for files needing review (default: NeedsReview)")
    parser.add_argument("--workers", type=int, default=4, help="Concurrent processes (default: 4)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without processing")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing outputs")
    parser.add_argument("--skip-hevc", action="store_true", help="Skip transcoding files already in HEVC (recommended)")
    parser.add_argument("--force-audio-aac", action="store_true", help="Force AAC audio for all files")
    parser.add_argument("--no-subs", action="store_true", help="Don't include subtitle streams")
    parser.add_argument("--delete-source", action="store_true",
                        help="Move/delete source files after processing (saves storage space)")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    parser.add_argument("--version", action="version", version=f"%(prog)s {plex.__version__}")
    args = parser.parse_args()

    plex.DEBUG = args.debug

    system_util.which_or_die("ffmpeg")
    system_util.which_or_die("ffprobe")

    source_root = Path(args.source).expanduser().resolve()
    if not source_root.exists():
        print(f"ERROR: Source folder does not exist: {source_root}", file=sys.stderr)
        sys.exit(2)

    # Infer output paths using common module
    inferred_output, inferred_manual = file_util.infer_output_roots(source_root)

    output_root = Path(args.output_root).resolve() if args.output_root else inferred_output
    manual_root = Path(args.manual_root).resolve() if args.manual_root else inferred_manual

    output_root.mkdir(parents=True, exist_ok=True)
    manual_root.mkdir(parents=True, exist_ok=True)

    # Find all video files
    all_files = [f for f in source_root.rglob("*") if f.is_file() and f.suffix.lower() in plex.VIDEO_EXTENSIONS]

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
    logger.safe_print("\n=== Phase 1: Staging files ===")
    staged_files = []
    results = []

    for idx, file in enumerate(all_files, 1):
        progress_pct = (idx / len(all_files)) * 100
        source_file, dest_file, status, staged = stage_file(file, output_root, manual_root, args)

        if staged:
            staged_files.append(staged)

        if status not in [plex.STATUS_STAGED, plex.STATUS_STAGED_HEVC, plex.STATUS_STAGED_NO_INFO]:
            results.append((source_file, dest_file, status))

        if dest_file and status not in [plex.STATUS_STAGED, plex.STATUS_STAGED_HEVC,
                                        plex.STATUS_STAGED_NO_INFO]:
            logger.safe_print(f"[{idx}/{len(all_files)} - {progress_pct:.1f}%] [{status}] {source_file.name}")

    logger.safe_print(
        f"\nStaging complete: {len(staged_files)} files ready for transcoding, {len(results)} already processed")

    if not staged_files:
        logger.safe_print("No files need transcoding.")
    else:
        # Phase 2: Transcode staged files (slow - actual video processing)
        logger.safe_print(f"\n=== Phase 2: Transcoding {len(staged_files)} files ===\n")
        transcoded = 0

        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(transcode_file, staged, args): staged for staged in staged_files}
            for fut in as_completed(futs):
                source_file, dest_file, status = fut.result()
                results.append((source_file, dest_file, status))
                transcoded += 1

                progress_pct = (transcoded / len(staged_files)) * 100
                if dest_file:
                    logger.safe_print(
                        f"[{transcoded}/{len(staged_files)} - {progress_pct:.1f}%] [{status}] {source_file.name} -> {dest_file.name}")
                else:
                    logger.safe_print(
                        f"[{transcoded}/{len(staged_files)} - {progress_pct:.1f}%] [{status}] {source_file.name}")

    ok = sum(1 for _, _, s in results if
             plex.STATUS_OK in s or plex.STATUS_COPY in s or plex.STATUS_MOVED in s)
    skip = sum(1 for _, _, s in results if s.startswith(plex.STATUS_SKIP))
    manual = sum(1 for _, _, s in results if s.startswith(plex.STATUS_MANUAL))
    fail = sum(1 for _, _, s in results if s.startswith(plex.STATUS_FAIL))
    dry = sum(1 for _, _, s in results if s.startswith(plex.STATUS_DRY_RUN))

    print(f"\n🎉 Done. OK={ok} MANUAL={manual} SKIP={skip} FAIL={fail} DRY-RUN={dry}")


if __name__ == "__main__":
    main()
