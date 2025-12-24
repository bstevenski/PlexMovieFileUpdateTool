"""
Filename formatter for creating Plex-compliant media file names.

This module provides functions to format media filenames according to
Plex naming conventions for both movies and TV shows.
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


### Internal helper functions ###
def _format_movie_filename(title: str, year: int, tmdb_id: int, extension: str) -> str:
    """
    Format a movie filename according to Plex conventions.

    Example: "Wake Up Dead Man A Knives Out Mystery (2025) {tmdb-812583}.mkv"
    """
    # Clean title and ensure proper spacing
    clean_title = " ".join(title.split())

    # Format: Title (Year) {tmdb-id}.ext
    filename = f"{clean_title} ({year}) {{tmdb-{tmdb_id}}}{extension}"

    logger.debug(f"Formatted movie filename: {filename}")
    return filename


def _format_episode_filename(
    series_title: str,
    season: int,
    episode: int,
    episode_title: Optional[str],
    extension: str,
    use_episode_title_only: bool = False,
) -> str:
    """
    Format a TV show episode filename according to Plex conventions.

    Standard Example: "It's Always Sunny in Philadelphia - S01E06 - The Gang Finds a Dead Guy.mkv"
    Episode Title Only Example: "It's Always Sunny in Philadelphia - The Gang Finds a Dead Guy.mkv"
    """
    # Clean title and ensure proper spacing
    clean_title = " ".join(series_title.split())

    if use_episode_title_only and episode_title:
        # Use episode title only, no season/episode numbers
        clean_episode_title = " ".join(episode_title.split())
        filename = f"{clean_title} - {clean_episode_title}{extension}"
    else:
        # Standard format with season/episode numbers
        season_str = f"{season:02d}"
        episode_str = f"{episode:02d}"

        if episode_title:
            clean_episode_title = " ".join(episode_title.split())
            filename = f"{clean_title} - S{season_str}E{episode_str} - {clean_episode_title}{extension}"
        else:
            filename = f"{clean_title} - S{season_str}E{episode_str}{extension}"

    logger.debug(f"Formatted TV filename: {filename}")
    return filename


def _format_tv_show_folder_name(title: str, year: Optional[int], tmdb_id: int) -> str:
    """
    Format a TV show folder name according to Plex conventions.

    Example: "It's Always Sunny in Philadelphia (2005-) {tmdb-2710}"
    """
    # Clean title and ensure proper spacing
    clean_title = " ".join(title.split())

    if year:
        folder_name = f"{clean_title} ({year}-) {{tmdb-{tmdb_id}}}"
    else:
        folder_name = f"{clean_title} {{tmdb-{tmdb_id}}}"

    logger.debug(f"Formatted TV show folder name: {folder_name}")
    return folder_name


def _format_season_folder_name(season: int) -> str:
    """
    Format a season folder name according to Plex conventions.

    Example: "Season 01"
    """
    season_str = f"{season:02d}"
    folder_name = f"Season {season_str}"

    logger.debug(f"Formatted season folder name: {folder_name}")
    return folder_name


### Public functions ###
def construct_movie_path(
    base_dir: Path,
    title: str,
    year: int,
    tmdb_id: int,
    extension: str,
) -> Path:
    """Construct the full path for a movie file."""
    filename = _format_movie_filename(title, year, tmdb_id, extension)
    return base_dir / filename


def construct_tv_show_path(
    base_dir: Path,
    title: str,
    year: Optional[int],
    tmdb_id: int,
    season: int,
    episode: int,
    episode_title: Optional[str],
    extension: str,
    use_episode_title_only: bool = False,
) -> Path:
    """Construct the full path for a TV show episode file.

    Args:
        use_episode_title_only: If True, use episode title instead of S##E## numbers
    """
    # Create show folder
    show_folder_name = _format_tv_show_folder_name(title, year, tmdb_id)
    show_folder = base_dir / show_folder_name

    # Create season folder
    season_folder_name = _format_season_folder_name(season)
    season_folder = show_folder / season_folder_name

    # Create filename
    filename = _format_episode_filename(title, season, episode, episode_title, extension, use_episode_title_only)

    return season_folder / filename
