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
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import plex as plex_module
from plex import rename, transcode
from plex.utils import LogLevel, logger, system_util, time_util
from plex.utils.constants import (
    COMPLETED_FOLDER,
    CONTENT_TYPE_MOVIES,
    CONTENT_TYPE_TV,
    ERROR_FOLDER,
    QUEUE_FOLDER,
    STAGED_FOLDER,
    STATUS_COPY,
    STATUS_DRY_RUN,
    STATUS_FAIL,
    STATUS_MANUAL,
    STATUS_MOVED,
    STATUS_OK,
    STATUS_SKIP,
    STATUS_STAGED,
    STATUS_STAGED_HEVC,
    STATUS_STAGED_NO_INFO,
    VIDEO_EXTENSIONS,
    WORKERS,
)
from plex.utils.time_util import get_eta_from_start

# Global executor reference for graceful shutdown
# Executor used for background transcoding tasks
_executor: ThreadPoolExecutor | None = None
_shutdown_requested: bool = False


def _signal_handler(signum, frame):
    """Handle termination signals gracefully."""
    global _shutdown_requested
    _shutdown_requested = True
    # In debug mode, log details about the received signal and (lightweight) frame info
    if getattr(plex_module, "DEBUG", False):
        try:
            sig_name = signal.Signals(signum).name
        except ValueError:
            # Fallback if the signal number isn't recognized
            sig_name = str(signum)

        location = None
        if frame is not None:
            mod = frame.f_globals.get("__name__", "?")
            func = getattr(frame.f_code, "co_name", "?")
            lineno = getattr(frame, "f_lineno", "?")
            location = f" at {mod}.{func}:{lineno}"

        try:
            logger.safe_print(f"[DEBUG] Signal received: {sig_name} ({signum})" + (location or ""))
        except (BrokenPipeError, OSError, UnicodeEncodeError):
            # Never let debug logging raise inside a signal handler
            pass
    logger.safe_print("\nShutdown signal received. Stopping gracefully...")
    logger.safe_print("Waiting for current transcoding jobs to complete...")

    if _executor:
        _executor.shutdown(wait=True, cancel_futures=False)

    logger.safe_print("Shutdown complete.")
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
    info: transcode.VideoInfo | None
    force_audio_aac: bool
    is_copy_only: bool = False
    status: str = STATUS_STAGED


def stage_file(
        file: Path, output_root: Path, manual_root: Path, skip_hevc: bool, overwrite: bool, dry_run: bool
) -> tuple[Path, Path | None, str, StagedFile | None]:
    """Stage a file: determine target path and check if transcoding is needed. Returns (source, target, status, staged_file)."""

    # Determine new name and path
    season, episode = rename.parse_tv_filename(file.stem)
    date_str, date_year = (None, None) if (season is not None) else rename.parse_date_in_filename(file.stem)
    is_tv = (season is not None) or (date_str is not None)

    new_file_path = None
    base_dest = None
    subdir = None

    if is_tv and season is not None and episode is not None:
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
        staged = StagedFile(file, target, None, False, is_copy_only=True)
        return file, target, STATUS_STAGED_NO_INFO, staged

    if skip_hevc and info.codec.lower() == "hevc":
        if target.exists() and not overwrite:
            return file, target, f"{STATUS_SKIP} (already exists)", None
        staged = StagedFile(file, target, info, False, is_copy_only=True)
        return file, target, STATUS_STAGED_HEVC, staged

    # Check if target exists before transcoding
    if target.exists() and not overwrite:
        return file, target, f"{STATUS_SKIP} (already exists)", None

    # Needs transcoding
    # Auto-detect: Force AAC audio for AVI files (often have incompatible audio codecs)
    force_audio_aac = file.suffix.lower() == ".avi"
    # Subtitles are excluded by default due to bitmap subtitle incompatibility
    staged = StagedFile(file, target, info, force_audio_aac, is_copy_only=False)

    if dry_run:
        return file, target, STATUS_DRY_RUN, staged

    return file, target, STATUS_STAGED, staged


def transcode_file(
        staged: StagedFile, delete_source: bool, dry_run: bool, debug: bool, source_root: Path
) -> tuple[Path, Path | None, str]:
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
        file, target, staged.info, force_audio_aac=staged.force_audio_aac, debug=debug
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
            msg = f"{STATUS_FAIL} (ffmpeg code {code}) - moved to Errors"
        except (OSError, shutil.Error, PermissionError) as e:
            msg = f"{STATUS_FAIL} (ffmpeg code {code}) - could not move to Errors: {e}"

        if "Subtitle" in err or "subtitles" in err or "codec" in err:
            msg += " (subtitle issue)"

        return file, None, msg

    # Success - move transcoded file to Completed folder
    root_dir = source_root.parent
    output_root = root_dir / STAGED_FOLDER
    completed_root = root_dir / COMPLETED_FOLDER
    completed_target = completed_root / target.relative_to(output_root)

    try:
        completed_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(target), str(completed_target))
        final_target = completed_target
    except (OSError, shutil.Error, PermissionError):
        # If move fails, leave in Transcoding folder
        final_target = target

    return file, final_target, STATUS_OK


def main():
    parser = argparse.ArgumentParser(
        description="Plexify your files! Rename and transcode media files for use with a Plex Media Server. "
                    "Uses TMDb API for metadata and hardware acceleration when available.",
        epilog="Example: plexifier /Users/briannastevenski/Plex",
    )
    parser.add_argument("root", help="Root directory containing Queue folder and where output folders will be created")
    parser.add_argument(
        "--no-skip-hevc", action="store_true", help="Transcode files already in HEVC (default: skip HEVC files)"
    )
    parser.add_argument("--log-dir", help="Directory for log files (default: ./logs or $PLEXIFIER_LOG_DIR)")
    parser.add_argument(
        "--log-file",
        help="Write console output to a file (in addition to the console); overrides --log-dir and $PLEXIFIER_LOG_FILE",
    )
    parser.add_argument(
        "--encoder",
        help="FFmpeg video encoder to use (e.g., hevc_videotoolbox, hevc_nvenc, libx265). "
             "Defaults to best available for your OS.",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug output and additional options")
    parser.add_argument("--debug-keep-source", action="store_true", help="[DEBUG] Keep source files after processing")
    parser.add_argument("--debug-no-overwrite", action="store_true", help="[DEBUG] Don't overwrite existing outputs")
    parser.add_argument("--debug-dry-run", action="store_true", help="[DEBUG] Preview without processing")
    parser.add_argument("--version", action="version", version=f"%(prog)s {plex_module.__version__}")
    args = parser.parse_args()

    # Allow log configuration via environment variables.
    env_log_dir = os.getenv("PLEXIFIER_LOG_DIR")
    env_log_file = os.getenv("PLEXIFIER_LOG_FILE")
    if not args.log_file and env_log_file:
        args.log_file = env_log_file
    if not args.log_dir and env_log_dir:
        args.log_dir = env_log_dir

    class _TeeStream:
        def __init__(self, *streams):
            self._streams = streams

        def write(self, data):
            for stream in self._streams:
                stream.write(data)
            return len(data)

        def flush(self):
            for stream in self._streams:
                stream.flush()

        def isatty(self):
            return any(getattr(stream, "isatty", lambda: False)() for stream in self._streams)

    # Check if running as background child process
    is_background_child = os.environ.get("PLEXIFIER_BACKGROUND_MODE") == "1"

    # In debug mode, default to foreground; otherwise background (unless already a child process)
    run_foreground = args.debug or is_background_child

    # Optional log file for foreground runs (Run/Debug console wraps long lines).
    if run_foreground:
        if args.log_file:
            log_path = Path(args.log_file).expanduser().resolve()
        else:
            log_dir = Path(args.log_dir) if args.log_dir else Path("./logs")
            log_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            log_path = (log_dir / f"plexifier-{timestamp}.log").resolve()

        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_file_handle = open(log_path, "a", encoding="utf-8", buffering=1)
        sys.stdout = _TeeStream(sys.stdout, log_file_handle)
        sys.stderr = _TeeStream(sys.stderr, log_file_handle)
        atexit.register(log_file_handle.close)
        print(f"Logging to: {log_path}")

    # Default to background mode unless in debug mode
    if not run_foreground:
        import subprocess

        # Create logs directory
        if args.log_file:
            log_path = Path(args.log_file).expanduser().resolve()
            log_path.parent.mkdir(parents=True, exist_ok=True)
        else:
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
                env=env,
            )

        print(f"Started background process (PID: {process.pid})")
        print(f"Logging to: {log_path}")
        print("\nMonitor progress:")
        print("  OR make logs")
        print("\nCheck if running:")
        print("  make ps")
        print("\nStop process:")
        print("  make kill")
        return

    plex_module.DEBUG = args.debug

    # Set log level based on debug mode
    if args.debug:
        logger.set_log_level(LogLevel.DEBUG)
    else:
        logger.set_log_level(LogLevel.INFO)

    # Set defaults based on debug mode
    delete_source = not args.debug_keep_source  # Default: delete source (unless debug)
    overwrite = not args.debug_no_overwrite  # Default: overwrite (unless debug)
    dry_run = args.debug_dry_run  # Default: false (only in debug)

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    atexit.register(_cleanup)

    system_util.which_or_die("ffmpeg")
    system_util.which_or_die("ffprobe")

    root_dir = Path(args.root).expanduser().resolve()
    if not root_dir.exists():
        logger.log("startup.error", LogLevel.ERROR, msg="Root directory does not exist", root=str(root_dir))
        sys.exit(2)

    # Resolve key folders under the provided root
    queue_root = (root_dir / QUEUE_FOLDER).resolve()
    staged_root = (root_dir / STAGED_FOLDER).resolve()
    error_root = (root_dir / ERROR_FOLDER).resolve()
    completed_root = (root_dir / COMPLETED_FOLDER).resolve()

    if not queue_root.exists():
        logger.log("startup.error", LogLevel.ERROR, msg="Queue folder does not exist", path=str(queue_root))
        sys.exit(2)

    staged_root.mkdir(parents=True, exist_ok=True)
    error_root.mkdir(parents=True, exist_ok=True)
    completed_root.mkdir(parents=True, exist_ok=True)

    # Find all video files in Queue
    all_files = [f for f in queue_root.rglob("*") if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS]

    # Check if there are staged files from a previous run
    staged_files_exist = False
    staged_video_files = []
    if staged_root.exists():
        staged_video_files = [f for f in staged_root.rglob("*") if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS]
        staged_files_exist = len(staged_video_files) > 0

    if not all_files and not staged_files_exist:
        logger.log(
            "startup.complete",
            LogLevel.INFO,
            msg="No video files found in Queue or Staged folders",
            queue=str(queue_root),
            staged=str(staged_root),
        )
        return

    skip_hevc = not args.no_skip_hevc

    total_files_count = len(all_files)
    eta_str = get_eta_from_start(total_files_count)

    start_time = time.time()

    # Check if we're resuming from staged files (Queue is empty but Staged has files)
    is_resuming = len(all_files) == 0 and staged_files_exist

    if is_resuming:
        logger.safe_print(f"\n⏸️  Resuming from previous run. Processing {len(staged_video_files)} staged file(s)...\n")

    logger.log(
        "plexifier.start",
        LogLevel.INFO,
        pid=os.getpid(),
        files_found=total_files_count,
        source=str(queue_root),
        staging=str(staged_root),
        completed=str(root_dir / COMPLETED_FOLDER),
        errors=str(error_root),
        WORKERS=WORKERS,
        skip_hevc=skip_hevc,
        delete_source=delete_source,
        dry_run=dry_run,
        eta=eta_str,
        resuming=is_resuming,
    )

    # Phase 1: Stage all files by renaming/moving from Queue -> Staged using batch API
    if all_files:
        logger.safe_print("\n=== Phase 1: Staging files ===")
        try:
            # Use batch renamer: scan Queue, compute Plex-friendly paths, move to Staged; non-renamables -> Errors
            # Non-interactive; honors dry_run.
            rename.rename_files(queue_root, stage_root=staged_root, error_root=error_root, dry_run=dry_run)
        except SystemExit:
            # rename_files may sys.exit(0) on dry-run or no files; continue flow safely
            pass
    else:
        logger.safe_print("\n=== Phase 1: Staging files ===")
        logger.safe_print("ℹ️  No new files in Queue. Skipping staging phase.")

    results = []

    # After staging, discover staged files for transcoding
    staged_file_paths = transcode.iter_video_files(staged_root)
    staged_count = len(staged_file_paths)

    logger.safe_print(f"\nStaging complete: {staged_count} files ready for transcoding")

    if not staged_file_paths:
        logger.safe_print("No files need transcoding.")
    else:
        # Phase 2: Transcode staged files (slow - actual video processing)
        logger.safe_print(f"\n=== Phase 2: Transcoding {staged_count} files ===\n")
        transcoded_count = 0

        global _executor
        _executor = ThreadPoolExecutor(max_workers=WORKERS)
        try:
            # Build adapter for transcode.batch.transcode_one expected args
            from types import SimpleNamespace

            _args = SimpleNamespace(
                overwrite=overwrite,
                skip_hevc=skip_hevc,
                force_audio_aac=False,
                dry_run=dry_run,
                debug=args.debug,
                delete_source=delete_source,
                video_encoder=args.encoder,
            )

            futs = {
                _executor.submit(
                    transcode.transcode_one,
                    src,
                    staged_root,
                    completed_root,
                    _args,
                ): src
                for src in staged_file_paths
            }
            for fut in as_completed(futs):
                if _shutdown_requested:
                    logger.safe_print("Shutdown requested, stopping new jobs...")
                    break

                source_file, dest_file, status = fut.result()
                # Handle outcomes: move/copy/move to error as needed
                if status == STATUS_OK and dest_file:
                    # On success, remove staged source if requested (transcode handled delete when asked)
                    try:
                        if source_file.exists() and delete_source:
                            source_file.unlink(missing_ok=True)
                    except Exception:
                        pass
                elif status.startswith(STATUS_SKIP):
                    # Move skipped file to Completed preserving original extension
                    rel = source_file.relative_to(staged_root)
                    skip_target = (completed_root / rel).resolve()
                    skip_target.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        if not dry_run:
                            shutil.move(str(source_file), str(skip_target))
                        dest_file = skip_target
                    except Exception:
                        # If move fails, send to Errors
                        err_target = (error_root / rel).resolve()
                        err_target.parent.mkdir(parents=True, exist_ok=True)
                        try:
                            shutil.move(str(source_file), str(err_target))
                            dest_file = err_target
                            status = STATUS_FAIL
                        except Exception:
                            status = STATUS_FAIL
                else:
                    # Failure case: move staged to Errors
                    rel = source_file.relative_to(staged_root)
                    err_target = (error_root / rel).resolve()
                    err_target.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        if not dry_run:
                            shutil.move(str(source_file), str(err_target))
                        dest_file = err_target
                    except Exception:
                        pass

                results.append((source_file, dest_file, status))
                transcoded_count += 1

                # Calculate overall progress
                if transcoded_count > 0:
                    progress_pct = (transcoded_count / staged_count) * 100
                    elapsed_seconds = time.time() - start_time
                    eta_str = time_util.get_eta_total(transcoded_count, staged_count, elapsed_seconds)
                    logger.log(
                        "plexifier.progress",
                        LogLevel.INFO,
                        completed=transcoded_count,
                        total=staged_count,
                        pct=round(progress_pct, 1),
                        eta=eta_str,
                    )
        finally:
            _executor.shutdown(wait=True)
            _executor = None

    ok = sum(1 for _, _, s in results if STATUS_OK in s or STATUS_COPY in s or STATUS_MOVED in s)
    skip = sum(1 for _, _, s in results if s.startswith(STATUS_SKIP))
    manual = sum(1 for _, _, s in results if s.startswith(STATUS_MANUAL))
    fail = sum(1 for _, _, s in results if s.startswith(STATUS_FAIL))
    dry = sum(1 for _, _, s in results if s.startswith(STATUS_DRY_RUN))

    # Final cleanup and pruning according to rules
    def _prune_staged_move_strays_to_errors(staged: Path, errors: Path):
        if not staged.exists():
            return 0
        moved = 0
        for p in staged.rglob("*"):
            if p.is_file():
                _rel = p.relative_to(staged)
                _err_target = (errors / _rel).resolve()
                _err_target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.move(str(p), str(_err_target))
                    moved += 1
                except Exception:
                    pass
        # Remove staged folder entirely
        try:
            shutil.rmtree(staged, ignore_errors=True)
        except Exception:
            pass
        return moved

    def _prune_queue_keep_top_subdirs(queue: Path, errors: Path):
        if not queue.exists():
            return 0
        moved = 0
        # Move all files under Queue to Errors
        for p in queue.rglob("*"):
            if p.is_file():
                try:
                    _rel = p.relative_to(queue)
                except ValueError:
                    continue
                _err_target = (errors / _rel).resolve()
                _err_target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.move(str(p), str(_err_target))
                    moved += 1
                except Exception:
                    pass
        # Remove all directories under Queue, then recreate Movies and TV Shows
        try:
            for child in queue.iterdir():
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
        except Exception:
            pass
        # Recreate empty Movies and TV Shows subfolders
        (queue / CONTENT_TYPE_MOVIES).mkdir(parents=True, exist_ok=True)
        (queue / CONTENT_TYPE_TV).mkdir(parents=True, exist_ok=True)
        return moved

    if not dry_run:
        logger.safe_print("\n=== Final cleanup ===")
        moved_staged = _prune_staged_move_strays_to_errors(staged_root, error_root)
        moved_queue = _prune_queue_keep_top_subdirs(queue_root, error_root)
        if moved_staged:
            logger.safe_print(f"Moved {moved_staged} stray file(s) from Staged to Errors and removed Staged folder")
        if moved_queue:
            logger.safe_print(f"Moved {moved_queue} stray file(s) from Queue to Errors and reset Queue structure")

    # Calculate runtime
    runtime_seconds = int(time.time() - start_time)
    runtime_hours = runtime_seconds // 3600
    runtime_mins = (runtime_seconds % 3600) // 60
    runtime_secs = runtime_seconds % 60
    runtime_str = f"{runtime_hours:02d}:{runtime_mins:02d}:{runtime_secs:02d}.000"

    logger.log(
        "plexifier.end",
        LogLevel.INFO,
        pid=os.getpid(),
        runtime=runtime_str,
        completed=str(root_dir / "Completed"),
        errors=str(error_root),
        ok=ok,
        manual=manual,
        skip=skip,
        fail=fail,
        dry_run=dry,
    )


if __name__ == "__main__":
    main()
