"""
Constants and configuration settings for media processing.

This module contains a set of constants used for video processing tasks. It
includes default extensions for video files, various status codes for message
representation, content type categories, and folder naming conventions for
organization. A debug setting is also included for troubleshooting processes.
"""

import os
import re

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

if load_dotenv:
    load_dotenv()

# Content type constants
CONTENT_TYPE_MOVIES = "Movies"
CONTENT_TYPE_TV = "TV Shows"

# Folder name constants
QUEUE_FOLDER = "../ready-to-process"
ERROR_FOLDER = "./media-processing/errored-files"
STAGED_FOLDER = "./media-processing/ready-to-transcode"
COMPLETED_FOLDER = "../ready-for-plex"

# Run settings
DEBUG = False
WORKERS = 4

# Estimated processing parameters
EST_AVG_SPEED = 1.5  # Estimated average speed multiplier for processing (45min -> ~30min)
EST_AVG_VIDEO_LENGTH = 2700  # Estimated average video length in seconds (45 minutes)

# Accepted video file extensions
VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov"}

# Regex patterns for filename parsing
SEASON_EPISODE_REGEX = re.compile(r"[Ss](\d{1,2})[Ee](\d{1,2})")
TMDB_ID_REGEX = re.compile(r"tmdb-\d+")
DATE_REGEXES = [
    re.compile(r"(20\d{2}|19\d{2})[-_. ](0[1-9]|1[0-2])[-_. ](0[1-9]|[12]\d|3[01])"),
]

# TMDb API configuration
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_BASE_URL = "https://api.themoviedb.org/3"

# Processing status codes
STATUS_STAGED = "STAGED"
STATUS_STAGED_HEVC = "STAGED (HEVC copy)"
STATUS_STAGED_NO_INFO = "STAGED (no codec info)"
STATUS_SKIP = "SKIP"
STATUS_OK = "OK"
STATUS_COPY = "COPY"
STATUS_MOVED = "MOVED"
STATUS_FAIL = "FAIL"
STATUS_MANUAL = "MANUAL REVIEW"
STATUS_DRY_RUN = "DRY-RUN"
