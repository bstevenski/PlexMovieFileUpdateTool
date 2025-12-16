"""
Path inference utilities for determining output paths for processed files
and manual review.

This module contains a function that helps infer the default output
directories for processed files and manual review based on a given
source file or directory path.
"""
import re
from pathlib import Path
from typing import Tuple

from plex.utils import STAGED_FOLDER, ERROR_FOLDER, COMPLETED_FOLDER


def normalize_text(text: str) -> str:
    """Normalize text by replacing separators with spaces and collapsing whitespace."""
    text = text.replace("_", " ").replace(".", " ")
    return re.sub(r"\s+", " ", text).strip()


def sanitize_filename(name: str) -> str:
    """
    Remove invalid filesystem characters from a name.
    Uses str.translate() for optimal performance.
    """
    invalid_chars = '<>:"/\\|?*'
    translation_table = str.maketrans('', '', invalid_chars)
    return name.translate(translation_table).strip()


def set_root_folders(base: Path) -> Tuple[Path, Path, Path]:
    """
    Create and return paths for Staged, Errors, and Completed folders under base.
    """
    staged_root = base / STAGED_FOLDER
    error_root = base / ERROR_FOLDER
    complete_root = base / COMPLETED_FOLDER
    staged_root.mkdir(parents=True, exist_ok=True)
    error_root.mkdir(parents=True, exist_ok=True)
    complete_root.mkdir(parents=True, exist_ok=True)
    return staged_root, error_root, complete_root
