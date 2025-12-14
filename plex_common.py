#!/usr/bin/env python3
"""
Common utilities shared across plex_renamer, plex_pipeline, and plex_transcoder.
Extracted to eliminate code duplication.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple, Optional, List

import requests

__version__ = "1.0.0"

# Thread-safe printing
_print_lock = threading.Lock()

def safe_print(*args, **kwargs):
    """Thread-safe print function."""
    with _print_lock:
        print(*args, **kwargs)

# ============================================================================
# Configuration Constants
# ============================================================================

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
if not TMDB_API_KEY:
    raise ValueError("TMDB_API_KEY environment variable is not set!")

TMDB_BASE_URL = "https://api.themoviedb.org/3"

SEASON_EPISODE_REGEX = re.compile(r"[Ss](\d{1,2})[Ee](\d{1,2})")
TMDB_ID_REGEX = re.compile(r"tmdb-\d+")
DATE_REGEXES = [
    re.compile(r"(20\d{2}|19\d{2})[-_. ](0[1-9]|1[0-2])[-_. ](0[1-9]|[12]\d|3[01])"),
]

VIDEO_EXTENSIONS = [".mkv", ".mp4", ".avi", ".mov"]
VIDEO_EXTS = {".mkv", ".mp4", ".avi", ".mov"}
DEBUG = False


# ============================================================================
# Transcoding Classes and Functions
# ============================================================================

@dataclass
class VideoInfo:
    codec: str
    width: Optional[int]
    height: Optional[int]
    pix_fmt: Optional[str]
    color_primaries: Optional[str]
    color_transfer: Optional[str]
    color_space: Optional[str]


def run_cmd(cmd: List[str]) -> Tuple[int, str, str]:
    """Run a command and return (code, stdout, stderr)."""
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return p.returncode, p.stdout, p.stderr


def which_or_die(binary: str):
    """Check if a binary exists on PATH, exit if not found."""
    if shutil.which(binary) is None:
        safe_print(f"ERROR: '{binary}' not found on PATH. Install it first (e.g. brew install ffmpeg).", file=sys.stderr)
        sys.exit(2)


def ffprobe_video_info(path: Path) -> Optional[VideoInfo]:
    """Probe video file for codec and format information."""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries",
        "stream=codec_name,width,height,pix_fmt,color_primaries,color_transfer,color_space",
        "-of", "json",
        str(path)
    ]
    code, out, err = run_cmd(cmd)
    if code != 0:
        return None
    data = json.loads(out)
    streams = data.get("streams") or []
    if not streams:
        return None
    s = streams[0]
    return VideoInfo(
        codec=s.get("codec_name", ""),
        width=s.get("width"),
        height=s.get("height"),
        pix_fmt=s.get("pix_fmt"),
        color_primaries=s.get("color_primaries"),
        color_transfer=s.get("color_transfer"),
        color_space=s.get("color_space"),
    )


def is_4k(info: VideoInfo) -> bool:
    """Check if video resolution is 4K or higher."""
    return (info.width or 0) >= 3800 or (info.height or 0) >= 2000


def looks_hdr(info: VideoInfo) -> bool:
    """Check if video appears to be HDR based on color metadata."""
    return (info.color_primaries == "bt2020") or (info.color_transfer in {"smpte2084", "arib-std-b67"})


def build_ffmpeg_cmd(src: Path, dst: Path, info: VideoInfo, force_audio_aac: bool, include_subs: bool) -> List[str]:
    """Build ffmpeg command for transcoding video to HEVC."""
    dst.parent.mkdir(parents=True, exist_ok=True)

    if is_4k(info):
        v_bitrate = "20000k"
        maxrate = "25000k"
        bufsize = "40000k"
        profile = "main10"
        pix_fmt = "p010le" if looks_hdr(info) else "yuv420p"
    else:
        v_bitrate = "7000k"
        maxrate = "9000k"
        bufsize = "14000k"
        profile = "main"
        pix_fmt = "yuv420p"

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-stats",
        "-i", str(src),
        "-map", "0",
        "-c:v", "hevc_videotoolbox",
        "-b:v", v_bitrate,
        "-maxrate", maxrate,
        "-bufsize", bufsize,
        "-profile:v", profile,
        "-pix_fmt", pix_fmt,
    ]

    if force_audio_aac:
        cmd += ["-c:a", "aac", "-b:a", "192k"]
    else:
        cmd += ["-c:a", "copy"]

    if include_subs:
        cmd += ["-c:s", "copy"]
    else:
        cmd += ["-sn"]

    cmd += ["-movflags", "+faststart", str(dst)]
    return cmd


# ============================================================================
# TMDb API Functions
# ============================================================================

def _make_tmdb_request(url: str, params: dict, error_context: str):
    """
    Common helper for TMDb API requests with error handling.
    Returns JSON response data or None on failure.
    """
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            return None
        return resp.json()
    except Exception as e:
        if DEBUG:
            safe_print(f"[TMDb] Error {error_context}: {e}")
    return None


def search_tmdb_movie(title: str, year: int = None):
    """
    Search TMDb for a movie.
    Returns movie data including TMDb ID, title, and release year.
    """
    url = f"{TMDB_BASE_URL}/search/movie"
    params = {
        "api_key": TMDB_API_KEY,
        "query": title,
        "include_adult": "false"
    }
    if year:
        params["year"] = str(year)

    data = _make_tmdb_request(url, params, f"searching movie '{title}'")
    if not data:
        return None

    results = data.get("results", [])
    if not results:
        return None

    # Return the first (best) match
    movie = results[0]
    release_date = movie.get("release_date", "")
    year = release_date[:4] if release_date else "Unknown"
    return {
        "tmdb_id": movie.get("id"),
        "title": movie.get("title"),
        "year": year,
        "original_title": movie.get("original_title")
    }


def search_tmdb_tv(title: str, year: int = None):
    """
    Search TMDb for a TV series.
    Returns series data including TMDb ID, name, and year range.
    """
    url = f"{TMDB_BASE_URL}/search/tv"
    params = {
        "api_key": TMDB_API_KEY,
        "query": title,
        "include_adult": "false"
    }
    if year:
        params["first_air_date_year"] = str(year)

    data = _make_tmdb_request(url, params, f"searching TV '{title}'")
    if not data:
        return None

    results = data.get("results", [])
    if not results:
        return None

    # Return the first (best) match
    show = results[0]
    tmdb_id = show.get("id")

    # Get full details including last air date
    details_url = f"{TMDB_BASE_URL}/tv/{tmdb_id}"
    details_params = {"api_key": TMDB_API_KEY}
    details = _make_tmdb_request(details_url, details_params, f"getting TV details for ID {tmdb_id}")

    if details:
        first_air = details.get("first_air_date", "")
        last_air = details.get("last_air_date", "")
        status = details.get("status", "")

        start_year = first_air[:4] if first_air else None
        end_year = last_air[:4] if last_air else None

        # Determine year format
        if start_year:
            if status in ["Returning Series", "In Production", "Planned"] or not end_year:
                year_str = f"{start_year}-"
            elif start_year == end_year:
                year_str = start_year
            else:
                year_str = f"{start_year}-{end_year}"
        else:
            year_str = "Unknown"

        return {
            "tmdb_id": tmdb_id,
            "name": details.get("name"),
            "year": year_str,
            "original_name": details.get("original_name")
        }
    else:
        # Fallback if details fetch fails
        first_air = show.get("first_air_date", "")
        year = first_air[:4] if first_air else "Unknown"
        return {
            "tmdb_id": tmdb_id,
            "name": show.get("name"),
            "year": year,
            "original_name": show.get("original_name")
        }


def get_tmdb_episode(tmdb_id: int, season: int, episode: int):
    """
    Get episode details from TMDb by show ID, season, and episode number.
    """
    url = f"{TMDB_BASE_URL}/tv/{tmdb_id}/season/{season}/episode/{episode}"
    params = {"api_key": TMDB_API_KEY}

    data = _make_tmdb_request(url, params, f"getting episode s{season:02d}e{episode:02d}")
    if not data:
        return None

    return {
        "name": data.get("name"),
        "season": season,
        "episode": episode
    }


# ============================================================================
# Filename Parsing Functions
# ============================================================================

def sanitize_filename(name: str):
    """Remove invalid filesystem characters from a name."""
    invalid_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
    for char in invalid_chars:
        name = name.replace(char, '')
    return name.strip()


def parse_tv_filename(filename: str) -> Tuple[int | None, int | None]:
    """Extract season and episode numbers from a filename."""
    match = SEASON_EPISODE_REGEX.search(filename)
    if match:
        season = int(match.group(1))
        episode = int(match.group(2))
        return season, episode
    return None, None


def parse_date_in_filename(filename: str) -> Tuple[str | None, int | None]:
    """
    Find a date token in the filename and normalize to YYYY-MM-DD for Plex date-based shows.
    Returns (date_str, year_int) or (None, None)
    """
    for rx in DATE_REGEXES:
        m = rx.search(filename)
        if m:
            y, mo, d = m.group(1), m.group(2), m.group(3)
            return f"{y}-{mo}-{d}", int(y)
    return None, None


def _normalize_text(text: str) -> str:
    """
    Normalize text by replacing separators with spaces and collapsing whitespace.
    """
    text = text.replace("_", " ").replace(".", " ")
    return re.sub(r"\s+", " ", text).strip()


def _guess_title_and_year_from_stem(stem: str) -> Tuple[str, str | None]:
    """
    Best-effort extraction of a human title and a (possible) year from a noisy filename stem.
    Examples:
      "Movie.Title.2024.2160p.WEB-DL" -> ("Movie Title", "2024")
      "Intervention.S01E05.720p" -> ("Intervention", None)
      "Chernobyl Diaries (2012)" -> ("Chernobyl Diaries", "2012")
    """
    # Normalize text
    s = _normalize_text(stem)

    # First try parentheses style: Title (2024) - most common for movies
    year = None
    title_part = s
    m = re.search(r"\((19|20)\d{2}\)", s)
    if m:
        year = re.search(r"(19|20)\d{2}", m.group(0)).group(0)
        title_part = s[:m.start()].strip()
    else:
        # Otherwise pick the last 4-digit year token between 1900-2099
        year_match = None
        for match in re.finditer(r"(19|20)\d{2}", s):
            year_match = match
        if year_match:
            year = year_match.group(0)
            title_part = s[:year_match.start()].strip()

    # Remove leftover common tags like resolution/encoders at the end
    title_part = re.sub(
        r"\b(480p|720p|1080p|2160p|4k|hdr|hdr10\+?|dv|web[- ]?dl|bluray|webrip|x264|x265|h\.264|h\.265|ddp?\d?\.?\d?|atmos|remux)\b",
        "", title_part, flags=re.IGNORECASE)
    title_part = re.sub(r"\s+", " ", title_part).strip(" -_()")
    # Title case lightly (don't shout)
    if title_part.isupper():
        title_part = title_part.title()
    return title_part.strip(), year


def _extract_episode_title_from_filename(stem: str) -> str | None:
    """
    Attempt to extract a human episode title from a filename stem.
    Examples:
      "Intervention - s08e11 - Marquel" -> "Marquel"
      "Ghosts - S01E01 - Pilot" -> "Pilot"
    Returns None if no obvious title segment exists.
    """
    s = _normalize_text(stem)

    # Prefer the segment after the sXXeYY token
    m = re.search(r"[Ss]\d{1,2}[Ee]\d{1,2}\s*-\s*(.+)$", s)
    if m:
        candidate = m.group(1).strip(" -_")
        if candidate:
            return sanitize_filename(candidate)

    # Fallback: last "-" segment, if it doesn't look like just tech garbage
    parts = [p.strip() for p in s.split(" - ") if p.strip()]
    if len(parts) >= 2:
        candidate = parts[-1]
        if not SEASON_EPISODE_REGEX.search(candidate):
            return sanitize_filename(candidate)

    return None


def _clean_search_title(stem: str, date_str: str | None = None) -> str:
    """
    Clean a filename stem to extract the base title for TMDb search.
    Removes season/episode patterns, dates, years, and normalizes text.
    """
    # Strip season/episode patterns
    search_title = re.split(SEASON_EPISODE_REGEX, stem)[0]
    # Remove anything after the first dash
    search_title = search_title.split(" - ")[0]
    # Remove years in parentheses
    search_title = re.sub(r"\(\d{4}\)", "", search_title)
    # Remove matched date token text if present
    if date_str:
        ds = date_str.replace('-', '[\\-_. ]')
        try:
            search_title = re.sub(ds, '', search_title)
        except re.error:
            pass
    return _normalize_text(search_title)


def _build_tv_folder_name(title: str, year: str | None, tmdb_id: int | None) -> Path:
    """
    Build a Plex-formatted TV show folder name.
    """
    if tmdb_id:
        return Path(f"{title} ({year}) {{tmdb-{tmdb_id}}}")
    return Path(f"{title} ({year})") if year else Path(title)


def _build_movie_folder_name(title: str, year: str | None, tmdb_id: int | None) -> Path:
    """
    Build a Plex-formatted movie folder name.
    """
    if tmdb_id:
        return Path(f"{title} ({year}) {{tmdb-{tmdb_id}}}")
    return Path(f"{title} ({year})") if year else Path(title)


# ============================================================================
# Path Inference Functions
# ============================================================================

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


# ============================================================================
# Renaming Functions
# ============================================================================

def rename_tv_file(file, season, episode, date_str: str | None = None, date_year: int | None = None):
    """Rename a TV file with TMDb metadata lookup."""
    search_title_series = _clean_search_title(file.stem, date_str)

    if DEBUG:
        safe_print(f"[LOOKUP] TV: {file.name} (S{season:02d}E{episode:02d})")

    # Search TMDb for TV show
    tmdb_data = search_tmdb_tv(search_title_series)
    series_tmdb_id: int | None = None
    series_year: str | None = None
    series_title_clean: str | None = None

    if tmdb_data:
        series_tmdb_id = tmdb_data.get("tmdb_id")
        series_title_clean = sanitize_filename(tmdb_data.get("name", search_title_series))
        series_year = tmdb_data.get("year", "Unknown")
        if DEBUG:
            safe_print(f"  └─ Matched: {series_title_clean} ({series_year}) [tmdb-{series_tmdb_id}]")

    matched = bool(series_tmdb_id)

    if not matched:
        # No match - build names without TMDb
        base_title, guessed_year = _guess_title_and_year_from_stem(search_title_series)
        renamable = bool(base_title) and len(base_title.strip()) >= 2
        if not renamable:
            return Path(file.name), False, False
        if date_str:
            # Date-based fallback
            folder_year = guessed_year or (str(date_year) if date_year else None)
            new_folder = _build_tv_folder_name(base_title, folder_year, None) / f"Season {date_year or '01'}"
            episode_title = date_str
            new_filename = f"{base_title} - {episode_title}{file.suffix}"
        else:
            season_num = season or 1
            episode_num = episode or 1
            token = f"s{season_num:02d}e{episode_num:02d}"
            episode_title = token
            new_folder = _build_tv_folder_name(base_title, guessed_year, None) / f"Season {season_num:02d}"
            if episode_title.strip().lower() == token.lower():
                new_filename = f"{base_title} - {token}{file.suffix}"
            else:
                new_filename = f"{base_title} - {token} - {episode_title}{file.suffix}"
        return new_folder / new_filename, matched, True

    season_num = season or 1
    episode_num = episode or 1
    episode_title = None

    # First, try to extract episode title from the original filename
    filename_episode_title = _extract_episode_title_from_filename(file.stem)

    if date_str is None:
        # If we have a filename episode title, use it (more reliable for shows with inconsistent numbering)
        if filename_episode_title:
            episode_title = filename_episode_title
            if DEBUG:
                print(f"  └─ Episode: {episode_title} (from filename)")
        else:
            # Otherwise try TMDb for episode title
            ep_data = get_tmdb_episode(series_tmdb_id, season_num, episode_num)
            if ep_data and ep_data.get("name"):
                episode_title = sanitize_filename(ep_data["name"])
                if DEBUG:
                    print(f"  └─ Episode: {episode_title} (from TMDb)")

        if not episode_title:
            episode_title = _extract_episode_title_from_filename(file.stem) or f"s{season_num:02d}e{episode_num:02d}"

        new_folder = _build_tv_folder_name(series_title_clean, series_year, series_tmdb_id) / f"Season {season_num:02d}"
        token = f"s{season_num:02d}e{episode_num:02d}"
        if (episode_title or '').strip().lower() == token.lower():
            new_filename = f"{series_title_clean} - {token}{file.suffix}"
        else:
            new_filename = f"{series_title_clean} - {token} - {episode_title}{file.suffix}"
    else:
        # Date-based episode
        new_folder = _build_tv_folder_name(series_title_clean, series_year, series_tmdb_id) / f"Season {date_year or '01'}"
        episode_title = date_str
        new_filename = f"{series_title_clean} - {episode_title}{file.suffix}"

    return new_folder / new_filename, matched, True


def rename_movie_file(file):
    """Rename a movie file with TMDb metadata lookup."""
    base_title, guessed_year = _guess_title_and_year_from_stem(file.stem)
    search_title = _normalize_text(file.stem)

    if DEBUG:
        safe_print(f"[LOOKUP] Movie: {file.name}")

    # Search TMDb for movie
    tmdb_data = search_tmdb_movie(search_title, year=int(guessed_year) if guessed_year and guessed_year.isdigit() else None)

    if not tmdb_data:
        # Fallback naming - ensure we have a valid title
        if not base_title or len(base_title.strip()) < 2:
            # Try to extract title before year from original stem
            title_match = re.match(r"^(.+?)\s*\(?\d{4}\)?", file.stem)
            if title_match:
                base_title = _normalize_text(title_match.group(1))
            else:
                base_title = search_title

        title = sanitize_filename(base_title or search_title)
        renamable = bool(title) and len(title) >= 2
        if not renamable:
            return Path(file.name), False, False
        new_folder = _build_movie_folder_name(title, guessed_year, None)
        new_filename = f"{title} ({guessed_year}){file.suffix}" if guessed_year else f"{title}{file.suffix}"
        return new_folder / new_filename, False, True

    tmdb_id = tmdb_data.get("tmdb_id")
    title = sanitize_filename(tmdb_data.get("title", ""))
    year = tmdb_data.get("year", "Unknown")

    # Fallback if TMDb returned empty title
    if not title or len(title.strip()) < 2:
        title = sanitize_filename(base_title or search_title)

    if DEBUG:
        safe_print(f"  └─ Matched: {title} ({year}) [tmdb-{tmdb_id}]")

    new_folder = _build_movie_folder_name(title, year, tmdb_id)
    # Include TMDb ID in filename if available
    if tmdb_id:
        new_filename = f"{title} ({year}) {{tmdb-{tmdb_id}}}{file.suffix}"
    else:
        new_filename = f"{title} ({year}){file.suffix}"
    return new_folder / new_filename, True, True
