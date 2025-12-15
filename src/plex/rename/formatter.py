# python
"""
Utilities to build Plex-formatted folder names for TV shows and movies.

This module provides a single helper used by higher-level formatters to
produce folder names that follow common Plex conventions:

- "Title (Year) {tmdb-1234}"
- "Title (Year)"
- "Title"

Notes:
- The `year` parameter is treated as a verbatim string. If the caller supplies
  an ongoing-year style string like "2005-", it will be preserved and appear
  in the output exactly as provided (e.g. "Intervention (2005-) {tmdb-11145}").
- The `tmdb_id`, when provided, is formatted as `{tmdb-<id>}` (curly braces).
- This helper intentionally keeps formatting logic minimal and deterministic so
  callers can control presentation by preparing the `title` and `year` inputs.

Example:
    build_folder_name("Intervention", "2005-", 11145) -> Path("Intervention (2005-) {tmdb-11145}")
"""
from pathlib import Path


def build_folder_name(title: str, year: str | None, tmdb_id: int | None) -> Path:
    """
    Build a Plex-style folder name for a media title.

    The function applies these rules (in order):
    1. If `tmdb_id` is provided (truthy), return:
         Path("Title (Year) {tmdb-<tmdb_id>}")
       If `year` is None or empty, the parentheses will still contain `None`
       unless the caller supplies a meaningful `year` string; callers should
       provide a valid `year` string when using `tmdb_id`.
    2. If `tmdb_id` is not provided but `year` is provided (non-None, non-empty),
       return:
         Path("Title (Year)")
    3. Otherwise, return:
         Path("Title")

    Parameters:
    - title (str): The primary title to use (e.g. "The Office").
    - year (str | None): A year string to include in parentheses. Treated verbatim;
      if the show is ongoing use a value such as "2005-" to indicate an open range.
    - tmdb_id (int | None): Numeric TMDb identifier. When present the ID is
      included in curly braces as `"{tmdb-<id>}"`.

    Returns:
    - Path: A `pathlib.Path` representing the formatted folder name.

    Examples:
    - build_folder_name("Movie", "1999", 123) -> Path("Movie (1999) {tmdb-123}")
    - build_folder_name("Show", "2005-", 11145) -> Path("Show (2005-) {tmdb-11145}")
    - build_folder_name("Indie", None, None) -> Path("Indie")
    """
    # If a TMDb id is present, include it in curly braces after the year.
    if tmdb_id:
        return Path(f"{title} ({year}) {{tmdb-{tmdb_id}}}")

    # If no TMDb id but a year is provided, include the year in parentheses.
    if year:
        return Path(f"{title} ({year})")

    # Fallback: just the title alone.
    return Path(title)