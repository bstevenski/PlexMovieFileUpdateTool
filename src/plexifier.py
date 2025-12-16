"""
Unified Plex media pipeline: Rename + Transcode in one step
Combines plex_renamer.py and plex_transcoder.py functionality
"""
import argparse
import atexit
import os
import shutil
import signal
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

import plex
from plex import rename, transcode, STATUS_STAGED, CONTENT_TYPE_TV, CONTENT_TYPE_MOVIES, STATUS_SKIP, STATUS_MANUAL, \
    STATUS_FAIL, STATUS_STAGED_NO_INFO, STATUS_STAGED_HEVC, STATUS_DRY_RUN, STATUS_MOVED, STATUS_COPY, STATUS_OK, DEBUG
from plex.utils import logger, system_util

in_debug_mode = DEBUG

# Global executor reference for graceful shutdown
_executor = None
_shutdown_requested = False


def _signal_handler():
    """Handle termination signals gracefully."""
    global _shutdown_requested
    _shutdown_requested = True
    logger.safe_print("\n⚠️  Shutdown signal received. Stopping gracefully...")
    logger.safe_print("⏳ Waiting for current transcoding jobs to complete...")

    if _executor:
        _executor.shutdown(wait=True, cancel_futures=False)

    logger.safe_print("✅ Shutdown complete.")
    sys.exit(0)


def _cleanup():
    """Cleanup function called on exit."""
    if _executor:
        _executor.shutdown(wait=False, cancel_futures=True)


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


def stage_file(file: Path, output_root: Path, manual_root: Path, skip_hevc: bool, overwrite: bool, dry_run: bool) -> \
        Tuple[
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
        if target.exists() and not overwrite:
            return file, target, f"{STATUS_SKIP} (already exists)", None
        staged = StagedFile(file, target, None, False, False, is_copy_only=True)
        return file, target, STATUS_STAGED_NO_INFO, staged

    if skip_hevc and info.codec.lower() == "hevc":
        if target.exists() and not overwrite:
            return file, target, f"{STATUS_SKIP} (already exists)", None
        staged = StagedFile(file, target, info, False, False, is_copy_only=True)
        return file, target, STATUS_STAGED_HEVC, staged

    # Check if target exists before transcoding
    if target.exists() and not overwrite:
        return file, target, f"{STATUS_SKIP} (already exists)", None

    # Needs transcoding
    # Auto-detect: Force AAC audio for AVI files (often have incompatible audio codecs)
    force_audio_aac = (file.suffix.lower() == ".avi")
    # Subtitles are excluded by default due to bitmap subtitle incompatibility
    include_subs = False

    staged = StagedFile(file, target, info, force_audio_aac, include_subs, is_copy_only=False)

    if dry_run:
        return file, target, STATUS_DRY_RUN, staged

    return file, target, STATUS_STAGED, staged


def transcode_file(staged: StagedFile, delete_source: bool, dry_run: bool, debug: bool, source_root: Path) -> Tuple[
    Path, Optional[Path], str]:
    """Transcode a staged file."""
    file = staged.source
    target = staged.target

    # Dry-run mode - just report what would happen
    if dry_run:
        return file, target, STATUS_DRY_RUN

    target.parent.mkdir(parents=True, exist_ok=True)

    # Handle copy-only files - use move if delete_source is enabled
    if staged.is_copy_only:
        try:
            if delete_source:
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

    code, out, err = transcode.transcode_video(
        file, target, staged.info,
        force_audio_aac=staged.force_audio_aac,
        include_subs=staged.include_subs,
        debug=debug
    )

    if code != 0:
        # Clean up partial/broken output file
        if target.exists():
            try:
                target.unlink()
            except (OSError, PermissionError):
                pass  # Best effort cleanup

        # Move source file to manual review folder, preserving directory structure
        manual_root = source_root.parent / "Errors"

        # Get the relative path from source root to the file
        # This preserves the Movies/TV Shows and any subdirectories (e.g., Series/Season folders)
        try:
            relative_path = file.resolve().relative_to(source_root)
            manual_target = manual_root / relative_path
        except ValueError:
            # If file is not relative to source root, fall back to simple naming
            if "/Movies/" in str(target) or "\\Movies\\" in str(target):
                subdir = CONTENT_TYPE_MOVIES
            else:
                subdir = CONTENT_TYPE_TV
            manual_target = manual_root / subdir / file.name

        try:
            manual_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(file), str(manual_target))
            msg = f"{STATUS_FAIL} (ffmpeg code {code}) — moved to Errors"
        except (OSError, shutil.Error, PermissionError) as e:
            msg = f"{STATUS_FAIL} (ffmpeg code {code}) — could not move to Errors: {e}"

        if "Subtitle" in err or "subtitles" in err or "codec" in err:
            msg += " (subtitle issue)"

        return file, None, msg

    # Success - move transcoded file to Completed folder
    root_dir = source_root.parent
    output_root = root_dir / "ToTranscode"
    completed_root = root_dir / "Completed"
    completed_target = completed_root / target.relative_to(output_root)

    try:
        completed_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(target), str(completed_target))
        final_target = completed_target
    except (OSError, shutil.Error, PermissionError):
        # If move fails, leave in Transcoding folder
        final_target = target

    if delete_source:
        try:
            file.unlink()
            return file, final_target, f"{STATUS_OK} (source deleted)"
        except (OSError, PermissionError) as e:
            return file, final_target, f"{STATUS_OK} (failed to delete source: {e})"

    return file, final_target, STATUS_OK


def main():
    parser = argparse.ArgumentParser(
        description="Plexify your files! Rename and transcode media files for use with a Plex Media Server. "
                    "Uses TMDb API for metadata and Apple VideoToolbox for hardware transcoding.",
        epilog="Example: plexifier /Users/briannastevenski/Plex"
    )
    parser.add_argument("root",
                        help="Root directory containing ToProcess folder and where output folders will be created")
    parser.add_argument("--no-skip-hevc", action="store_true",
                        help="Transcode files already in HEVC (default: skip HEVC files)")
    parser.add_argument("--log-dir", help="Directory for log files (default: ./logs)")
    parser.add_argument("--debug", action="store_true", help="Enable debug output and additional options")
    parser.add_argument("--debug-keep-source", action="store_true", help="[DEBUG] Keep source files after processing")
    parser.add_argument("--debug-no-overwrite", action="store_true", help="[DEBUG] Don't overwrite existing outputs")
    parser.add_argument("--debug-dry-run", action="store_true", help="[DEBUG] Preview without processing")
    parser.add_argument("--version", action="version", version=f"%(prog)s {plex.__version__}")
    args = parser.parse_args()

    # Check if running as background child process
    is_background_child = os.environ.get("PLEXIFIER_BACKGROUND_MODE") == "1"

    # In debug mode, default to foreground; otherwise background (unless already a child process)
    run_foreground = args.debug or is_background_child

    # Default to background mode unless in debug mode
    if not run_foreground:
        import subprocess

        # Create logs directory
        log_dir = Path(args.log_dir) if args.log_dir else Path("./logs")
        log_dir.mkdir(parents=True, exist_ok=True)

        # Generate unique log filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        log_file = log_dir / f"plexifier-{timestamp}.log"
        log_path = log_file.resolve()

        # Build command - remove --debug to run in background
        script_path = Path(__file__).resolve()
        cmd = [sys.executable, str(script_path)] + [arg for arg in sys.argv[1:] if arg != "--debug"]

        # Set environment variable to indicate this is a background child process
        env = os.environ.copy()
        env["PLEXIFIER_BACKGROUND_MODE"] = "1"

        # Start background process
        with open(log_path, "w") as log:
            process = subprocess.Popen(
                cmd,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,  # Detach from parent
                env=env
            )

        print(f"✅ Started background process (PID: {process.pid})")
        print(f"📝 Logging to: {log_path}")
        print(f"\nMonitor progress:")
        print(f"  tail -f {log_path}")
        print(f"\nCheck if running:")
        print(f"  ps {process.pid}")
        return

    plex.DEBUG = args.debug

    # Set defaults based on debug mode
    workers = 4
    delete_source = not args.debug_keep_source  # Default: delete source (unless debug)
    overwrite = not args.debug_no_overwrite  # Default: overwrite (unless debug)
    dry_run = args.debug_dry_run  # Default: false (only in debug)

    # Enable timestamps when running in background
    logger.enable_timestamps(True)

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    atexit.register(_cleanup)

    system_util.which_or_die("ffmpeg")
    system_util.which_or_die("ffprobe")

    root_dir = Path(args.root).expanduser().resolve()
    if not root_dir.exists():
        print(f"ERROR: Root directory does not exist: {root_dir}", file=sys.stderr)
        sys.exit(2)

    # Define folder structure
    source_root = root_dir / "ToProcess"
    output_root = root_dir / "ToTranscode"
    manual_root = root_dir / "Errors"

    if not source_root.exists():
        print(f"ERROR: ToProcess folder does not exist: {source_root}", file=sys.stderr)
        sys.exit(2)

    output_root.mkdir(parents=True, exist_ok=True)
    manual_root.mkdir(parents=True, exist_ok=True)

    # Find all video files
    all_files = [f for f in source_root.rglob("*") if f.is_file() and f.suffix.lower() in plex.VIDEO_EXTENSIONS]

    if not all_files:
        print("No video files found.")
        return

    print(f"Found {len(all_files)} files in: {source_root}")
    print(f"Staging: {output_root}")
    print(f"Completed: {root_dir / 'Completed'}")
    print(f"Errors: {manual_root}")
    skip_hevc = not args.no_skip_hevc
    print(f"Workers: {workers} | skip-hevc: {skip_hevc}")

    if delete_source:
        print(f"⚠️  Storage Mode: Source files will be MOVED/DELETED (saves space)")
    else:
        print(f"ℹ️  Storage Mode: Source files will be KEPT (uses more space)")

    if dry_run:
        print(f"🔍 DRY RUN MODE: No files will be modified")

    print()

    # Phase 1: Stage all files (fast - just lookups and file checks)
    logger.safe_print("\n=== Phase 1: Staging files ===")
    staged_files = []
    results = []

    for idx, file in enumerate(all_files, 1):
        progress_pct = (idx / len(all_files)) * 100
        source_file, dest_file, status, staged = stage_file(file, output_root, manual_root, skip_hevc, overwrite,
                                                            dry_run)

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

        global _executor
        _executor = ThreadPoolExecutor(max_workers=workers)
        try:
            futs = {_executor.submit(transcode_file, staged, delete_source, dry_run, args.debug, source_root): staged
                    for staged in staged_files}
            for fut in as_completed(futs):
                if _shutdown_requested:
                    logger.safe_print("⚠️  Shutdown requested, stopping new jobs...")
                    break

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
        finally:
            _executor.shutdown(wait=True)
            _executor = None

    ok = sum(1 for _, _, s in results if
             plex.STATUS_OK in s or plex.STATUS_COPY in s or plex.STATUS_MOVED in s)
    skip = sum(1 for _, _, s in results if s.startswith(plex.STATUS_SKIP))
    manual = sum(1 for _, _, s in results if s.startswith(plex.STATUS_MANUAL))
    fail = sum(1 for _, _, s in results if s.startswith(plex.STATUS_FAIL))
    dry = sum(1 for _, _, s in results if s.startswith(plex.STATUS_DRY_RUN))

    print(f"\n🎉 Done. OK={ok} MANUAL={manual} SKIP={skip} FAIL={fail} DRY-RUN={dry}")


if __name__ == "__main__":
    main()
