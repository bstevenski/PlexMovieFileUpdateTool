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
# All paths are relative to plex-media-tool directory where script is run
QUEUE_FOLDER = "../ready-to-process"  # Input folder at same level as plex-media-tool
ERROR_FOLDER = "../.media/errored-files"  # Error files in .media folder at plex-media-tool level
STAGED_FOLDER = "../.media/ready-to-transcode"  # Staging files in .media folder at plex-media-tool level
COMPLETED_FOLDER = "../ready-for-plex"  # Output folder at same level as plex-media-tool

# Run settings
DEBUG = False
WORKERS = 4

# Estimated processing parameters
EST_AVG_SPEED = 1.5  # Estimated average speed multiplier for processing (45min -> ~30min)
EST_AVG_VIDEO_LENGTH = 2700  # Estimated average video length in seconds (45 minutes)

# Accepted video file extensions
VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".webm"}

# Regex patterns for filename parsing
SEASON_EPISODE_REGEX = re.compile(r"[Ss](\d{1,2})[Ee](\d{1,2})")
TMDB_ID_REGEX = re.compile(r"tmdb-\d+")
YEAR_REGEX = re.compile(r"(19|20)\d{2}")
DATE_REGEXES = [
    re.compile(r"(20\d{2}|19\d{2})[-_. ](0[1-9]|1[0-2])[-_. ](0[1-9]|[12]\d|3[01])"),
]
QUALITY_FORMATS_REGEX = re.compile(
    r"\b(480p|720p|1080p|2160p|4k|hdr|hdr10\+?|dv|web[- ]?dl|bluray|webrip|x264|x265|h\.264|h\.265|ddp?\d?\.?\d?|atmos|remux)\b",
    flags=re.IGNORECASE,
)

# TMDb API configuration
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/original"

# Transcoding settings for Apple TV compatibility
TRANSCODE_SETTINGS = {
    "video_codec": "libx264",
    "audio_codec": "aac",
    "preset": "medium",
    "crf": 23,
    "audio_bitrate": "128k",
    "max_audio_channels": 2,
}

# Logging configuration
LOG_LEVELS = {"DEBUG": 10, "INFO": 20, "WARN": 30, "WARNING": 30, "ERROR": 40}
DEFAULT_LOG_LEVEL = "INFO"
LOG_DIR = "./.logs"
