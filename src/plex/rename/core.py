"""
Utilities for renaming TV and movie files using metadata lookup.

This module provides functions to rename TV and movie files based on metadata
retrieved from The Movie Database (TMDb). It includes functionality to handle
fallbacks when metadata is unavailable and ensures filenames are sanitized
and formatted consistently.

Functions:
- rename_tv_file: Renames TV show files using TMDb metadata.
- rename_movie_file: Renames movie files using TMDb metadata.
- _build_tv_fallback: Builds a fallback filename for TV shows when metadata is unavailable.
- _get_episode_title: Retrieves the episode title from TMDb or the filename.
- _build_tv_filename: Constructs a formatted filename for TV episodes.
- _build_movie_fallback: Builds a fallback filename for movies when metadata is unavailable.
- _extract_fallback_title: Extracts a fallback title from the filename if metadata is unavailable.
"""

import re
from pathlib import Path

from plex.rename import formatter, parser
from plex.utils import LogLevel, file_util, logger, tmdb


def rename_tv_file(
        file: Path, season: int, episode: int, date_str: str | None = None, date_year: int | None = None
) -> tuple[Path, bool, bool]:
    """
    Rename a TV file using TMDb metadata lookup and formatting helpers.

    This function attempts to find series and episode metadata via TMDb and
    builds a destination path and filename using the project's formatter and
    sanitization utilities. If TMDb lookup fails, it will attempt sensible
    fallbacks derived from the original filename (including date-based titles).

    Parameters:
    - file (Path): Path object referencing the original media file.
    - season (int): Season number for the episode.
    - episode (int): Episode number for the episode.
    - date_str (Optional[str]): Optional date string used for date-based episodes (e.g., daily shows).
    - Date_year (Optional[int]): Optional year accompanying `date_str` to construct folder names.

    Returns:
    Tuple[Path, bool, bool]:
    - New_path (Path): Proposed new path (folder and filename) for the media file. May be `Path(file.name)` if not renamable.
    - matched_tmdb (bool): True if a TMDb match was found and used; False if fallbacks were used.
    - is_renamable (bool): True if the file can be renamed (fallbacks allowed); False if not enough information to rename.
    """
    search_title = parser.clean_search_title(file.stem, date_str)

    log_fields = {
        "file": file.name,
        "type": "tv",
        "search_term": search_title,
    }
    if season is not None:
        log_fields["season"] = f"S{season:02d}"
    if episode is not None:
        log_fields["episode"] = f"E{episode:02d}"
    logger.log("rename.lookup", LogLevel.DEBUG, **log_fields)

    tmdb_data = tmdb.search_tmdb_tv(search_title)
    series_info = {
        "id": tmdb_data.get("tmdb_id") if tmdb_data else None,
        "title": file_util.sanitize_filename(tmdb_data.get("name", search_title)) if tmdb_data else None,
        "year": tmdb_data.get("year", "Unknown") if tmdb_data else None,
    }

    if series_info["id"]:
        logger.log(
            "rename.tmdb.match",
            LogLevel.DEBUG,
            title=series_info["title"],
            year=series_info["year"],
            tmdb_id=series_info["id"],
        )

    if not series_info["id"]:
        logger.log("rename.tmdb.no_match", LogLevel.WARN, file=file.name, search_term=search_title)

        base_title, guessed_year = parser.guess_title_and_year_from_stem(search_title)
        if not base_title or len(base_title.strip()) < 2:
            return Path(file.name), False, False
        return _build_tv_fallback(file, base_title, guessed_year, season, episode, date_str, date_year)

    if date_str:
        folder_year = str(date_year) if date_year else series_info["year"]
        new_folder = (
                formatter.build_folder_name(series_info["title"], folder_year, series_info["id"])
                / f"Season {date_year or '01'}"
        )
        new_filename = f"{series_info['title']} - {date_str}{file.suffix}"
        return new_folder / new_filename, True, True

    episode_title = _get_episode_title(file, series_info["id"], season, episode, date_str)
    new_folder = (
            formatter.build_folder_name(series_info["title"], series_info["year"], series_info["id"])
            / f"Season {season:02d}"
    )
    new_filename = _build_tv_filename(series_info["title"], season, episode, episode_title, file.suffix)
    return new_folder / new_filename, True, True


def rename_movie_file(file: Path) -> tuple[Path, bool, bool]:
    """
    Rename a movie file using TMDb metadata lookup and project helpers.

    This function attempts to find movie metadata via TMDb and builds a
    destination path and filename using the project's formatter and
    sanitization utilities. If a TMDb match is found, the resulting folder
    and filename include the TMDb id; if not, sensible fallbacks derived
    from the original filename are used when possible.

    Parameters:
    - file (Path): Path object referencing the original movie file.

    Returns:
    Tuple[Path, bool, bool]:
    - new_path (Path): Proposed new path (folder + filename) for the movie file.
                      May be `Path(file.name)` if not renamable.
    - matched_tmdb (bool): True when a TMDb entry was matched and used.
    - is_renamable (bool): True when the file can be renamed (fallbacks allowed);
                           False when insufficient information prevents renaming.
    """
    base_title, guessed_year = parser.guess_title_and_year_from_stem(file.stem)
    search_title = base_title if base_title else file_util.normalize_text(file.stem)

    logger.log(
        "rename.lookup",
        LogLevel.DEBUG,
        file=file.name,
        type="movie",
        search_term=search_title,
        guessed_year=guessed_year or "unknown",
    )

    tmdb_data = tmdb.search_tmdb_movie(search_title, year=int(guessed_year) if guessed_year else None)
    if not tmdb_data:
        logger.log("rename.tmdb.no_match", LogLevel.WARN, file=file.name, search_term=search_title)

        if not base_title or len(base_title.strip()) < 2:
            base_title = _extract_fallback_title(file.stem)
        if not base_title or len(base_title.strip()) < 2:
            return Path(file.name), False, False
        return _build_movie_fallback(file, base_title, guessed_year)

    title = file_util.sanitize_filename(tmdb_data.get("title", base_title))
    year = tmdb_data.get("year", "Unknown")
    tmdb_id = tmdb_data.get("tmdb_id")

    logger.log("rename.tmdb.match", LogLevel.DEBUG, title=title, year=year, tmdb_id=tmdb_id)

    new_folder = formatter.build_folder_name(title, year, tmdb_id)
    new_filename = f"{title} ({year}) {{tmdb-{tmdb_id}}}{file.suffix}" if tmdb_id else f"{title} ({year}){file.suffix}"
    return new_folder / new_filename, True, True


def _build_tv_fallback(file, base_title, guessed_year, season, episode, date_str, date_year):
    """
    Build a fallback path and filename for a TV episode when TMDb data is unavailable.

    Parameters:
    - file (Path): Original file Path object (used for suffix).
    - base_title (str): Guessed series title derived from the filename.
    - guessed_year (str|None): Guessed year derived from the filename, if any.
    - season (int): Season number.
    - episode (int): Episode number.
    - date_str (str|None): If present, treat the episode as a date-based episode (e.g., daily shows).
    - date_year (int|None): Year associated with `date_str` for folder naming.

    Returns:
    Tuple[Path, bool, bool]:
    - new_path (Path): Proposed new path (folder + filename).
    - matched_tmdb (bool): Always False for fallback.
    - is_renamable (bool): True when a fallback filename can be returned.
    """
    if date_str:
        folder_year = guessed_year or str(date_year) if date_year else None
        new_folder = formatter.build_folder_name(base_title, folder_year, None) / f"Season {date_year or '01'}"
        new_filename = f"{base_title} - {date_str}{file.suffix}"
    else:
        token = f"s{season:02d}e{episode:02d}"
        new_folder = formatter.build_folder_name(base_title, guessed_year, None) / f"Season {season:02d}"
        new_filename = f"{base_title} - {token}{file.suffix}"
    return new_folder / new_filename, False, True


def _get_episode_title(file, series_id, season, episode, date_str):
    """
    Determine the episode title to use.

    Priority:
    1. If `date_str` is provided, use it (date-based episode).
    2. Try to extract a title from the filename using `parser.extract_episode_title_from_filename`.
    3. Query TMDb for the episode name via `tmdb.get_tmdb_episode`.
    4. Fall back to a season/episode token like "s01e02".

    Parameters:
    - file (Path): Original file Path object (used for stem when extracting from filename).
    - series_id (int|str): TMDb series id used when querying episode metadata.
    - season (int): Season number.
    - episode (int): Episode number.
    - date_str (str|None): Optional date string for date-based episodes.

    Returns:
    - episode_title (str): The chosen episode title (maybe the date string or a token).
    """
    if date_str:
        return date_str
    filename_title = parser.extract_episode_title_from_filename(file.stem)
    if filename_title:
        logger.log("rename.episode", LogLevel.TRACE, episode_title=filename_title, source="filename")
        return filename_title
    ep_data = tmdb.get_tmdb_episode(series_id, season, episode)
    if ep_data and ep_data.get("name"):
        episode_title = file_util.sanitize_filename(ep_data["name"])
        logger.log("rename.episode", LogLevel.TRACE, episode_title=episode_title, source="TMDb")
        return episode_title
    return f"s{season:02d}e{episode:02d}"


def _build_tv_filename(series_title, season, episode, episode_title, suffix):
    """
    Construct the final TV episode filename.

    Format rules:
    - Always include series title and token `s{season:02d}e{episode:02d}`.
    - If `episode_title` equals the token (case-insensitive), omit the redundant title.
    - Append the file suffix.

    Parameters:
    - series_title (str): Sanitized series title.
    - season (int): Season number.
    - episode (int): Episode number.
    - episode_title (str): Episode title or token.
    - suffix (str): File extension (e.g. ".mkv").

    Returns:
    - filename (str): Formatted filename string.
    """
    token = f"s{season:02d}e{episode:02d}"
    if episode_title.strip().lower() == token.lower():
        return f"{series_title} - {token}{suffix}"
    return f"{series_title} - {token} - {episode_title}{suffix}"


def _build_movie_fallback(file, base_title, guessed_year):
    """
    Build a fallback path and filename for a movie when TMDb data is unavailable.

    Parameters:
    - file (Path): Original file Path object (used for suffix).
    - base_title (str): Guessed movie title derived from the filename.
    - guessed_year (str|None): Guessed year derived from the filename, if any.

    Returns:
    Tuple[Path, bool, bool]:
    - new_path (Path): Proposed new path (folder + filename).
    - matched_tmdb (bool): Always False for fallback.
    - is_renamable (bool): True when a fallback filename can be returned.
    """
    new_folder = formatter.build_folder_name(base_title, guessed_year, None)
    new_filename = f"{base_title} ({guessed_year}){file.suffix}" if guessed_year else f"{base_title}{file.suffix}"
    return new_folder / new_filename, False, True


def _extract_fallback_title(stem):
    """
    Extract a fallback title from a filename stem by stripping a trailing four-digit year.

    Behavior:
    - Matches the first group of characters before an optional year pattern like " (2020)" or " 2020".
    - Returns the normalized text via `file_util.normalize_text`.

    Parameters:
    - stem (str): The filename stem to analyze.

    Returns:
    - title (str): Normalized fallback title.
    """
    match = re.match(r"^(.+?)\s*\(?\d{4}\)?", stem)
    return file_util.normalize_text(match.group(1)) if match else file_util.normalize_text(stem)
