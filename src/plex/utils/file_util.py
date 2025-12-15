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


def infer_output_roots(src: Path) -> Tuple[Path, Path]:
    """
    Infer default output paths for processed files and manual review.
    Returns (output_root, manual_root)
    """
    parts = [p.lower() for p in src.parts]
    # Look for a folder named "ToProcess" or legacy names
    base = None
    for folder_name in ['toprocess', '1.rename']:
        if folder_name in parts:
            try:
                ix = parts.index(folder_name)
                base = Path(*src.parts[:ix])
                break
            except (ValueError, IndexError):
                pass

    if base is None:
        # If no known folder found, use the parent of the source
        base = src.parent

    out = base / 'Processed'
    mc = base / 'NeedsReview'
    return out, mc


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