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
import signal
import sys
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
    cleanup_transcoding_artifacts,
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

    def _format_new_path(self, media_info: dict, tmdb_data: dict, use_episode_titles: bool, filepath: Path) -> Path:
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
        relative_path = filepath.relative_to(Path(STAGED_FOLDER) / content_type)
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
  %(prog)s                                    # Process from default queue directory
  %(prog)s /path/to/media                    # Process from custom directory
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
        help=f"Number of worker processes (default: {WORKERS})",
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
        plexifier.run(args.source_dir)
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
