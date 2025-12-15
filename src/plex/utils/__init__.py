"""
A module providing constants, utility functions, and logging mechanisms
for multimedia processing tasks.

This module includes a collection of constants related to video
processing workflows, utility functions for system operations such as
command execution, and file utility functionalities. It also integrates
a logging mechanism for safe and controlled outputs.
"""

from .constants import (
    DEBUG,
    VIDEO_EXTENSIONS,
    SEASON_EPISODE_REGEX,
    TMDB_ID_REGEX,
    DATE_REGEXES,
    TMDB_API_KEY,
    TMDB_BASE_URL,
    STATUS_STAGED,
    STATUS_STAGED_HEVC,
    STATUS_STAGED_NO_INFO,
    STATUS_SKIP,
    STATUS_OK,
    STATUS_COPY,
    STATUS_MOVED,
    STATUS_FAIL,
    STATUS_MANUAL,
    STATUS_DRY_RUN,
    CONTENT_TYPE_MOVIES,
    CONTENT_TYPE_TV,
    FOLDER_UPLOAD,
    FOLDER_ISSUES,
)

__all__ = [
    # Constants
    "DEBUG",
    "VIDEO_EXTENSIONS",
    "SEASON_EPISODE_REGEX",
    "TMDB_ID_REGEX",
    "DATE_REGEXES",
    "TMDB_API_KEY",
    "TMDB_BASE_URL",
    "STATUS_STAGED",
    "STATUS_STAGED_HEVC",
    "STATUS_STAGED_NO_INFO",
    "STATUS_SKIP",
    "STATUS_OK",
    "STATUS_COPY",
    "STATUS_MOVED",
    "STATUS_FAIL",
    "STATUS_MANUAL",
    "STATUS_DRY_RUN",
    "CONTENT_TYPE_MOVIES",
    "CONTENT_TYPE_TV",
    "FOLDER_UPLOAD",
    "FOLDER_ISSUES",
]
