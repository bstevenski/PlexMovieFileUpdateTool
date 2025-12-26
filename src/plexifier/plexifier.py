#!/usr/bin/env python3
"""
Plexifier: Automated Plex media file processing pipeline.

This script orchestrates the entire media processing workflow including:
- File scanning and parsing
- TMDb metadata lookup
- File renaming according to Plex conventions
- Video transcoding for device compatibility
- File organization and error handling
"""

import argparse
import concurrent.futures
import os
import signal
import sys
import time
from pathlib import Path

from .constants import (
    COMPLETED_FOLDER,
    CONTENT_TYPE_MOVIES,
    CONTENT_TYPE_TV,
    DEFAULT_LOG_LEVEL,
    ERROR_FOLDER,
    QUEUE_FOLDER,
    STAGED_FOLDER,
    WORKERS,
    LOG_DIR,
)
from .file_manager import (
    create_error_directory,
    ensure_directory_exists,
    safe_move_with_backup,
    scan_media_files,
)
from .formatter import (
    construct_movie_path,
    construct_tv_show_path,
)
from .logger import setup_logging
from .parser import parse_media_file
from .tmdb_client import TMDbClient, TMDbError
from .transcoder import (
    VideoInfo,
    cleanup_all_processes,
    cleanup_transcoding_artifacts,
    get_transcode_output_path,
    needs_transcoding,
    transcode_video,
    validate_transcoded_file,
)


class Plexifier:
    """Main orchestrator for the media processing pipeline."""

    def __init__(
        self,
        dry_run: bool = False,
        log_level: str = DEFAULT_LOG_LEVEL,
        workers: int = WORKERS,
        skip_transcoding: bool = False,
        use_episode_titles: bool = False,
    ):
        """
        Initialize the Plexifier.

        Args:
            dry_run: Preview changes without making modifications
            log_level: Logging level
            workers: Number of worker processes
            skip_transcoding: Skip video transcoding step
            use_episode_titles: Use episode titles instead of S##E## numbers for TV shows
        """
        self.dry_run = dry_run
        self.log_level = log_level
        self.workers = workers
        self.skip_transcoding = skip_transcoding
        self.use_episode_titles = use_episode_titles

        # Set up logging
        self.logger = setup_logging(
            log_level=log_level,
            log_dir=Path(LOG_DIR),
            enable_console=True,
        )

        # Initialize TMDb client
        try:
            self.tmdb_client = TMDbClient()
        except TMDbError as e:
            self.logger.error(f"Failed to initialize TMDb client: {e}")
            sys.exit(1)

        # Set up signal handlers for graceful shutdown
        self.running = True
        signal.signal(signal.SIGINT, self._signal_handler)
        try:
            signal.signal(signal.SIGTERM, self._signal_handler)
        except (AttributeError, OSError):
            pass

        self.logger.info("Plexifier initialized", dry_run=dry_run, workers=workers)

    def _signal_handler(self, signum, _frame):
        """Handle shutdown signals gracefully."""
        self.logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.running = False

        # Clean up all active subprocesses
        cleanup_all_processes()

    def run(self, source_dir: str | None = None) -> None:
        """Run the main processing pipeline."""
        if source_dir:
            queue_dir = Path(source_dir).resolve()
        else:
            queue_dir = Path(QUEUE_FOLDER).resolve()

        self.logger.info(f"Starting media processing from: {queue_dir}")

        # Ensure all required directories exist
        self._setup_directories()

        # Initialize counters for final summary
        total_files_processed = 0
        total_files_successful = 0
        total_files_failed = 0

        # Process each content type
        try:
            movies_stats = self._process_content_type(queue_dir, CONTENT_TYPE_MOVIES)
            tv_stats = self._process_content_type(queue_dir, CONTENT_TYPE_TV)

            # Accumulate totals
            total_files_processed += movies_stats[0]
            total_files_successful += movies_stats[1]
            total_files_failed += movies_stats[2]

            total_files_processed += tv_stats[0]
            total_files_successful += tv_stats[1]
            total_files_failed += tv_stats[2]

        except KeyboardInterrupt:
            self.logger.info("Processing interrupted by user")
        except Exception as e:
            self.logger.error(f"Processing failed: {e}")
            raise
        finally:
            self.logger.info(
                f"Media processing completed - "
                f"Total: {total_files_processed}, "
                f"Successful: {total_files_successful}, "
                f"Failed: {total_files_failed}"
            )

    def _setup_directories(self) -> None:
        """Ensure all required directories exist."""
        directories = [
            Path(STAGED_FOLDER) / CONTENT_TYPE_MOVIES,
            Path(STAGED_FOLDER) / CONTENT_TYPE_TV,
            Path(COMPLETED_FOLDER) / CONTENT_TYPE_MOVIES,
            Path(COMPLETED_FOLDER) / CONTENT_TYPE_TV,
            Path(ERROR_FOLDER),
        ]

        for directory in directories:
            ensure_directory_exists(directory)
            self.logger.debug(f"Ensured directory exists: {directory}")

    def run_parallel(self, source_dir: str | None = None, daemon_mode: bool = False) -> None:
        """Run the parallel processing pipeline with workers."""
        if source_dir:
            queue_dir = Path(source_dir).resolve()
        else:
            queue_dir = Path(QUEUE_FOLDER).resolve()

        self.logger.info(f"Starting parallel media processing from: {queue_dir}")
        self.logger.info(f"Using {self.workers} worker threads")

        # Ensure all required directories exist
        self._setup_directories()

        if daemon_mode:
            self._run_daemon_mode(queue_dir)
        else:
            self._run_batch_mode(queue_dir)

    def _run_daemon_mode(self, queue_dir: Path) -> None:
        """Run in daemon mode, continuously monitoring for new files."""
        self.logger.info("Starting daemon mode - monitoring for new files...")

        # Make process a daemon
        if os.fork() > 0:
            return  # Parent exits

        os.setsid()
        if os.fork() > 0:
            return  # Second fork

        # Close stdin/stdout/stderr
        sys.stdin.close()
        sys.stdout.close()
        sys.stderr.close()

        while self.running:
            try:
                # Process current files
                self._run_batch_mode(queue_dir)

                # Wait before next check
                time.sleep(30)  # Check every 30 seconds

            except KeyboardInterrupt:
                self.logger.info("Daemon interrupted by user")
                break
            except Exception as e:
                self.logger.error(f"Daemon error: {e}")
                time.sleep(60)  # Wait longer on error

    def _run_batch_mode(self, queue_dir: Path) -> None:
        """Run batch processing: rename first, then transcode in parallel."""
        # Phase 1: Rename and move all files to staging
        self.logger.info("Phase 1: Renaming and organizing files...")
        staged_files = self._batch_rename_and_stage(queue_dir)

        if not staged_files:
            self.logger.info("No files to process")
            return

        self.logger.info(f"Staged {len(staged_files)} files for transcoding")

        # Phase 2: Transcode in parallel using workers
        if not self.skip_transcoding:
            self.logger.info(f"Phase 2: Transcoding with {self.workers} workers...")
            self._parallel_transcode(staged_files)

        # Phase 3: Move completed files to final destination
        self.logger.info("Phase 3: Moving completed files...")
        self._move_completed_files(staged_files)

        self.logger.info("Batch processing completed")

    def _batch_rename_and_stage(self, queue_dir: Path) -> list[dict]:
        """Phase 1: Rename and move all files to staging area."""
        staged_files = []

        for content_type in [CONTENT_TYPE_MOVIES, CONTENT_TYPE_TV]:
            content_queue_dir = queue_dir / content_type

            if not content_queue_dir.exists():
                continue

            self.logger.info(f"Processing {content_type} from: {content_queue_dir}")

            for filepath in scan_media_files(content_queue_dir):
                if not self.running:
                    break

                try:
                    staged_info = self._stage_file(filepath, content_type)
                    if staged_info:
                        staged_files.append(staged_info)

                except Exception as e:
                    self.logger.error(f"Failed to stage file {filepath}: {e}")
                    self._handle_error(filepath, str(e))

        return staged_files

    def _stage_file(self, filepath: Path, content_type: str) -> dict | None:
        """Stage a single file (rename and move to staging area)."""
        try:
            # Step 1: Parse filename
            media_info = parse_media_file(filepath)

            # Step 2: Lookup TMDb metadata
            tmdb_data = self._lookup_tmdb_metadata(media_info)
            if not tmdb_data:
                return None

            # Step 3: Format new filename and path
            new_path = self._format_new_path(media_info, tmdb_data, self.use_episode_titles, filepath)

            # Step 4: Move to staging area
            if not self._move_to_staging(filepath, new_path):
                return None

            # Check if transcoding is needed (catch errors to avoid breaking staging)
            try:
                needs_trans = not self.skip_transcoding and needs_transcoding(VideoInfo(new_path))
            except Exception as e:
                self.logger.warning(f"Could not determine transcoding need for {new_path}: {e}")
                needs_trans = False

            return {
                "original_path": filepath,
                "staged_path": new_path,
                "content_type": content_type,
                "media_info": media_info,
                "tmdb_data": tmdb_data,
                "needs_transcoding": needs_trans,
            }

        except Exception as e:
            self.logger.error(f"Failed to stage file {filepath}: {e}")
            return None

    def _parallel_transcode(self, staged_files: list[dict]) -> None:
        """Phase 2: Transcode files in parallel using workers."""
        # Filter files that need transcoding
        files_to_transcode = [f for f in staged_files if f["needs_transcoding"]]

        if not files_to_transcode:
            self.logger.info("No files need transcoding")
            return

        self.logger.info(f"Transcoding {len(files_to_transcode)} files with {self.workers} workers")

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.workers) as executor:
            # Submit all transcoding jobs
            future_to_file = {
                executor.submit(self._transcode_staged_file, file_info): file_info for file_info in files_to_transcode
            }

            # Process completed jobs
            completed = 0
            for future in concurrent.futures.as_completed(future_to_file):
                file_info = future_to_file[future]
                completed += 1

                try:
                    transcoded_path = future.result()
                    if transcoded_path:
                        file_info["transcoded_path"] = transcoded_path
                        self.logger.info(
                            f"[{completed}/{len(files_to_transcode)}] Transcoded: {file_info['staged_path'].name}"
                        )
                    else:
                        self.logger.error(
                            f"[{completed}/{len(files_to_transcode)}] Failed to transcode: {file_info['staged_path'].name}"
                        )

                except Exception as e:
                    self.logger.error(f"Transcoding error for {file_info['staged_path'].name}: {e}")

    def _transcode_staged_file(self, file_info: dict) -> Path | None:
        """Transcode a single staged file."""
        staged_path = file_info["staged_path"]

        try:
            # Determine output path
            output_path = get_transcode_output_path(staged_path)

            # Transcode
            success = transcode_video(staged_path, output_path)

            if success and validate_transcoded_file(staged_path, output_path):
                # Clean up original transcoded file
                cleanup_transcoding_artifacts(staged_path)
                return output_path
            else:
                # Remove failed transcoding attempt
                if output_path.exists():
                    output_path.unlink()
                return None

        except Exception as e:
            self.logger.error(f"Transcoding failed for {staged_path}: {e}")
            return None

    def _move_completed_files(self, staged_files: list[dict]) -> None:
        """Phase 3: Move all completed files to final destination."""
        for file_info in staged_files:
            try:
                # Determine final path (either original staged or transcoded)
                final_path = file_info.get("transcoded_path", file_info["staged_path"])
                content_type = file_info["content_type"]

                # Check if the file still exists (it may have been cleaned up if transcoding failed)
                if not final_path.exists():
                    self.logger.warning(f"File not found, skipping: {final_path}")
                    continue

                # Move to completed area
                if self._move_to_completed(final_path, content_type):
                    self.logger.info(f"Completed: {final_path.name}")
                else:
                    self.logger.error(f"Failed to move completed file: {final_path.name}")

            except Exception as e:
                self.logger.error(f"Error moving completed file {file_info.get('staged_path', 'unknown')}: {e}")

    def _process_content_type(self, queue_dir: Path, content_type: str) -> tuple[int, int, int]:
        """Process all files of a specific content type."""
        content_queue_dir = queue_dir / content_type

        if not content_queue_dir.exists():
            self.logger.warning(f"Queue directory does not exist: {content_queue_dir}")
            return 0, 0, 0

        self.logger.info(f"Processing {content_type} from: {content_queue_dir}")

        processed_count = 0
        error_count = 0

        for filepath in scan_media_files(content_queue_dir):
            if not self.running:
                break

            try:
                success = self._process_file(filepath, content_type)
                if success:
                    processed_count += 1
                else:
                    error_count += 1

            except Exception as e:
                self.logger.error(f"Failed to process file {filepath}: {e}")
                error_count += 1

        self.logger.info(
            f"Completed processing {content_type}",
            processed=processed_count,
            errors=error_count,
        )

        return processed_count + error_count, processed_count, error_count

    def _process_file(self, filepath: Path, content_type: str) -> bool:
        """Process a single media file through the entire pipeline."""
        self.logger.info(f"Processing file: {filepath}")

        try:
            # Step 1: Parse filename
            media_info = parse_media_file(filepath)
            self.logger.debug(f"Parsed media info: {media_info}")

            # Step 2: Lookup TMDb metadata
            tmdb_data = self._lookup_tmdb_metadata(media_info)
            if not tmdb_data:
                return self._handle_error(filepath, "TMDb lookup failed")

            # Step 3: Format new filename and path
            new_path = self._format_new_path(media_info, tmdb_data, self.use_episode_titles, filepath)
            self.logger.debug(f"New path: {new_path}")

            # Step 4: Move to staging area
            if not self._move_to_staging(filepath, new_path):
                return False

            # Step 5: Transcode if needed
            if not self.skip_transcoding:
                transcoded_path = self._transcode_if_needed(new_path)
                if transcoded_path:
                    new_path = transcoded_path

            # Step 6: Move to completed area
            if not self._move_to_completed(new_path, content_type):
                return False

            self.logger.info(f"Successfully processed: {filepath}")
            return True

        except Exception as e:
            self.logger.error(f"Processing failed for {filepath}: {e}")
            return self._handle_error(filepath, str(e))

    def _lookup_tmdb_metadata(self, media_info: dict) -> dict | None:
        """Lookup metadata from TMDb API."""
        try:
            if media_info["content_type"] == CONTENT_TYPE_MOVIES:
                result = self.tmdb_client.find_best_movie_match(media_info["title"], media_info["year"])
            else:  # TV Show
                result = self.tmdb_client.find_best_tv_match(media_info["title"], media_info["year"])

            if result:
                # Use appropriate field name for movies vs TV shows
                display_name = result.get("title") or result.get("name", "Unknown")
                self.logger.debug(f"Found TMDb match: {display_name}")
                return result
            else:
                self.logger.warning(f"No TMDb match found for: {media_info['title']}")
                return None

        except TMDbError as e:
            self.logger.error(f"TMDb lookup failed: {e}")
            return None

    @staticmethod
    def _format_new_path(media_info: dict, tmdb_data: dict, use_episode_titles: bool, filepath: Path) -> Path:
        """Format the new path according to Plex conventions."""
        staged_dir = Path(STAGED_FOLDER) / media_info["content_type"]
        tmdb_id = tmdb_data["id"]
        extension = filepath.suffix

        if media_info["content_type"] == CONTENT_TYPE_MOVIES:
            new_path = construct_movie_path(
                staged_dir,
                tmdb_data["title"],
                int(tmdb_data["release_date"][:4]) if tmdb_data.get("release_date") else media_info["year"],
                tmdb_id,
                extension,
            )
        else:  # TV Show
            new_path = construct_tv_show_path(
                staged_dir,
                tmdb_data["name"],
                int(tmdb_data["first_air_date"][:4]) if tmdb_data.get("first_air_date") else media_info["year"],
                tmdb_id,
                media_info["season"],
                media_info["episode"],
                media_info["episode_title"],
                extension,
                use_episode_titles,
            )

        return new_path

    def _move_to_staging(self, source_path: Path, destination_path: Path) -> bool:
        """Move file to staging area."""
        if self.dry_run:
            self.logger.info(f"DRY RUN: Would move {source_path} to {destination_path}")
            return True

        error_dir = create_error_directory(Path(ERROR_FOLDER), "staging_errors")
        return safe_move_with_backup(source_path, destination_path, error_dir)

    def _transcode_if_needed(self, filepath: Path) -> Path | None:
        """Transcode video if needed for compatibility."""
        if self.dry_run:
            self.logger.info(f"DRY RUN: Would check transcoding need for {filepath}")
            return None

        try:
            video_info = VideoInfo(filepath)

            if not needs_transcoding(video_info):
                self.logger.info(f"File {filepath} is already compatible, skipping transcoding")
                return None

            self.logger.info(f"Transcoding needed for {filepath}")

            # Generate output path
            output_path = filepath.with_suffix(".mp4")

            # Transcode the file
            success = transcode_video(filepath, output_path)

            if success and validate_transcoded_file(filepath, output_path):
                # Remove original file and return transcoded path
                filepath.unlink()
                cleanup_transcoding_artifacts(filepath)
                return output_path
            else:
                self.logger.error(f"Transcoding failed for {filepath}")
                cleanup_transcoding_artifacts(output_path)
                return None

        except Exception as e:
            self.logger.error(f"Transcoding error for {filepath}: {e}")
            cleanup_transcoding_artifacts(filepath)
            return None

    def _move_to_completed(self, filepath: Path, content_type: str) -> bool:
        """Move processed file to completed area."""
        if self.dry_run:
            self.logger.info(f"DRY RUN: Would move {filepath} to completed area")
            return True

        completed_dir = Path(COMPLETED_FOLDER) / content_type

        # Handle both staged files and transcoded files
        try:
            # Try to get relative path from staged folder
            staged_base = Path(STAGED_FOLDER) / content_type
            relative_path = filepath.relative_to(staged_base)
        except ValueError:
            # File might be transcoded and not in the expected staged structure
            # Extract the show/season info from the path or create a fallback structure
            if content_type == CONTENT_TYPE_TV:
                # For TV shows, try to extract show and season from path
                path_parts = filepath.parts
                show_name = "Unknown Show"
                season = "Season 01"

                for part in path_parts:
                    if part.endswith(f" {{tmdb-"):
                        show_name = part
                    elif part.startswith("Season "):
                        season = part

                relative_path = Path(show_name) / season / filepath.name
            else:
                # For movies, just use the filename
                relative_path = Path(filepath.name)

        destination_path = completed_dir / relative_path

        error_dir = create_error_directory(Path(ERROR_FOLDER), "completion_errors")
        return safe_move_with_backup(filepath, destination_path, error_dir)

    def _handle_error(self, filepath: Path, error_message: str) -> bool:
        """Handle processing errors by moving file to error directory."""
        self.logger.error(f"Handling error for {filepath}: {error_message}")

        if self.dry_run:
            self.logger.info(f"DRY RUN: Would move {filepath} to error directory")
            return False

        error_dir = create_error_directory(Path(ERROR_FOLDER), "processing_errors")
        error_destination = error_dir / filepath.name

        try:
            safe_move_with_backup(filepath, error_destination)
            return False
        except Exception as e:
            self.logger.error(f"Failed to move error file: {e}")
            return False


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description="Automated Plex media file processing pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
 Examples:
  %(prog)s                                    # Run in background daemon mode with 4 workers
  %(prog)s /path/to/media                    # Process from custom directory
  %(prog)s --foreground                       # Run in foreground (non-daemon) mode
  %(prog)s --workers 8                       # Use 8 parallel workers for transcoding
  %(prog)s --dry-run                         # Preview changes without modifications
  %(prog)s --skip-transcoding                 # Skip video transcoding
  %(prog)s --log-level DEBUG                 # Enable debug logging
  %(prog)s --use-episode-titles              # Use episode titles instead of S##E## numbers for TV shows
        """,
    )

    parser.add_argument(
        "source_dir",
        nargs="?",
        help="Source directory containing media files (default: ../ready-to-process)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without making modifications",
    )

    parser.add_argument(
        "--skip-transcoding",
        action="store_true",
        help="Skip video transcoding step",
    )

    parser.add_argument(
        "--use-episode-titles",
        action="store_true",
        help="Use episode titles instead of S##E## numbers for TV shows (useful when episode numbers are incorrect)",
    )

    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARN", "ERROR"],
        default=DEFAULT_LOG_LEVEL,
        help="Logging level (default: INFO)",
    )

    parser.add_argument(
        "--workers",
        type=int,
        default=WORKERS,
        help=f"Number of worker processes for transcoding (default: {WORKERS})",
    )

    parser.add_argument(
        "--foreground",
        action="store_true",
        help="Run in foreground mode (default is background daemon mode)",
    )

    args = parser.parse_args()

    # Create and run the plexifier
    plexifier = Plexifier(
        dry_run=args.dry_run,
        log_level=args.log_level,
        workers=args.workers,
        skip_transcoding=args.skip_transcoding,
        use_episode_titles=getattr(args, "use_episode_titles", False),
    )

    try:
        # Default to daemon mode unless explicitly foreground
        daemon_mode = not getattr(args, "foreground", False)
        plexifier.run_parallel(args.source_dir, daemon_mode)
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
