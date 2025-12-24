"""
File manager for handling media file operations.

This module provides functions for scanning, moving, copying, and organizing
media files throughout the processing pipeline.
"""

import logging
import shutil
from pathlib import Path
from typing import Generator, Optional

from .constants import VIDEO_EXTENSIONS

logger = logging.getLogger(__name__)


class FileOperationError(Exception):
    """Exception for file operation failures."""

    pass


### Internal helper functions ###
def _get_file_size(filepath: Path) -> int:
    """Get file size in bytes."""
    try:
        return filepath.stat().st_size
    except OSError:
        return 0


def _get_available_space(directory: Path) -> int:
    """Get available disk space in bytes for a directory."""
    try:
        stat = shutil.disk_usage(directory)
        return stat.free
    except OSError:
        return 0


def _move_file(source: Path, destination: Path, create_dirs: bool = True) -> None:
    """
    Move a file from source to destination.

    Args:
        source: Source file path
        destination: Destination file path
        create_dirs: Whether to create parent directories for destination
    """
    if not source.exists():
        raise FileOperationError(f"Source file does not exist: {source}")

    if create_dirs:
        ensure_directory_exists(destination.parent)

    try:
        shutil.move(str(source), str(destination))
        logger.info(f"Moved file: {source} -> {destination}")
    except OSError as e:
        raise FileOperationError(f"Failed to move file {source} to {destination}: {e}")


### Public functions ###
def scan_media_files(directory: Path, recursive: bool = True) -> Generator[Path, None, None]:
    """
    Scan a directory for media files.

    Args:
        directory: Directory to scan
        recursive: Whether to scan subdirectories

    Yields:
        Path objects for found media files
    """
    if not directory.exists():
        logger.warning(f"Directory does not exist: {directory}")
        return

    if not directory.is_dir():
        logger.error(f"Path is not a directory: {directory}")
        return

    pattern = "**/*" if recursive else "*"

    for path in directory.glob(pattern):
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
            yield path


def ensure_directory_exists(directory: Path) -> None:
    """Ensure a directory exists, creating it if necessary."""
    try:
        directory.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Ensured directory exists: {directory}")
    except OSError as e:
        raise FileOperationError(f"Failed to create directory {directory}: {e}")


def safe_move_with_backup(source: Path, destination: Path, error_dir: Optional[Path] = None) -> bool:
    """
    Safely move a file with error handling and backup.

    Args:
        source: Source file path
        destination: Destination file path
        error_dir: Directory to move file to if operation fails

    Returns:
        True if move succeeded, False if failed and file was moved to error_dir
    """
    try:
        _move_file(source, destination)
        return True
    except FileOperationError as e:
        logger.error(f"Failed to move file {source}: {e}")

        if error_dir:
            try:
                error_destination = error_dir / source.name
                _move_file(source, error_destination)
                logger.warning(f"Moved failed file to error directory: {error_destination}")
                return False
            except FileOperationError as backup_error:
                logger.error(f"Failed to move file to error directory: {backup_error}")

        return False


def create_error_directory(base_error_dir: Path, content_type: str) -> Path:
    """Create an error directory for a specific content type."""
    error_dir = base_error_dir / content_type
    ensure_directory_exists(error_dir)
    return error_dir
