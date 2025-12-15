"""
File renaming functionality for Plex media organization.

This package contains utilities to parse media filenames, format folder and
filename structures according to Plex conventions, and perform TMDb-based
renaming for TV shows and movies.

Package organization:
- parsing: Filename parsing and text normalization utilities (e.g. extracting
  titles, seasons, episodes, and dates from filenames).
- formatting: Path and filename formatting helpers to produce consistent Plex
  folder and file names.
- core: TMDb-based renaming logic for TV shows and movies. Core functions use
  metadata lookups and sensible fallbacks to propose new paths and filenames.
- batch: High-level batch processing with progress tracking for renaming many
  files at once.

Public API (top-level exports)
- Parsing:
  - `parse_tv_filename`: Parse a TV filename into structured components.
  - `parse_date_in_filename`: Detect and parse date-based episode filenames.
- Core renaming:
  - `rename_tv_file`: Compute a new path for a TV episode (returns (Path, matched_tmdb, is_renamable)).
  - `rename_movie_file`: Compute a new path for a movie (returns (Path, matched_tmdb, is_renamable)).
- Batch processing:
  - `rename_files`: Perform batch renaming with progress reporting.

Behavior notes:
- Core renaming functions return a tuple: (proposed_path, matched_tmdb: bool, is_renamable: bool).
  - `matched_tmdb` is True when TMDb metadata was used.
  - `is_renamable` is False when insufficient information prevents a safe rename.
- When TMDb lookup fails, the code attempts to derive titles and years from the
  filename and uses formatter helpers to build consistent fallbacks.
- Filenames and folder names are sanitized to be filesystem-safe.

Example:
    from pathlib import Path
    import plex.rename as rename
    new_path, matched, renamable = rename.rename_movie_file(Path("Some.Movie.2020.mkv"))

Dependencies and compatibility:
- Expects the project's `parser`, `formatter`, `tmdb`, `file_util`, and `logger`
  utilities to be available under the `plex` package.
- Written for modern Python (3.8+). Platform-independent, used on macOS in the
  development environment.
"""
# Public parsing functions
from .parser import (
    parse_tv_filename,
    parse_date_in_filename,
)

# Core renaming functions
from .core import (
    rename_tv_file,
    rename_movie_file,
)

# Batch processing
from .batch import rename_files

__all__ = [
    # Parsing
    "parse_tv_filename",
    "parse_date_in_filename",
    # Core renaming
    "rename_tv_file",
    "rename_movie_file",
    # Batch processing
    "rename_files",
]
