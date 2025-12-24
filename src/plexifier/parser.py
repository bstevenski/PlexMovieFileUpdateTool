"""
Filename parser for extracting media metadata from filenames.

This module provides functions to parse TV show and movie filenames,
extracting information like series names, season/episode numbers, years,
and episode titles for use in media processing and Plex naming.
"""

import re
from pathlib import Path
from typing import Optional, Tuple

from .constants import SEASON_EPISODE_REGEX, YEAR_REGEX, DATE_REGEXES, QUALITY_FORMATS_REGEX


### Internal helper functions ###
def _normalize_text(text: str) -> str:
    """Normalize text by replacing common separators and removing extra whitespace."""
    separators = r"[._\-\+]"
    text = re.sub(separators, " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _sanitize_filename(text: str) -> str:
    """Remove characters that are problematic in filenames."""
    invalid_chars = r'[<>:"/\\|?*]'
    return re.sub(invalid_chars, "", text).strip()


def _parse_tv_filename(filename: str) -> Tuple[Optional[int], Optional[int]]:
    """Extract season and episode numbers from a TV show filename."""
    match = SEASON_EPISODE_REGEX.search(filename)
    if match:
        season = int(match.group(1))
        episode = int(match.group(2))
        return season, episode
    return None, None


def _parse_date_in_filename(filename: str) -> Tuple[Optional[str], Optional[int]]:
    """Extract date from filename for date-based TV shows."""
    for rx in DATE_REGEXES:
        m = rx.search(filename)
        if m:
            y, mo, d = m.group(1), m.group(2), m.group(3)
            return f"{y}-{mo}-{d}", int(y)
    return None, None


def _extract_year_from_stem(stem: str) -> Optional[int]:
    """Extract the first 4-digit year between 1900-2099 from a filename stem."""
    for match in YEAR_REGEX.finditer(stem):
        if match:
            year = int(match.group(0))
            if 1900 <= year <= 2099:
                return year
    return None


def _guess_title_and_year_from_stem(stem: str) -> Tuple[str, Optional[int]]:
    """
    Extract human-readable title and year from a noisy filename stem.

    Examples:
        "Movie.Title.2024.2160p.WEB-DL" -> ("Movie Title", 2024)
        "Intervention.S01E05.720p" -> ("Intervention", None)
        "Chernobyl Diaries (2012)" -> ("Chernobyl Diaries", 2012)
    """
    # Normalize text
    s = _normalize_text(stem)

    # First try parentheses style: Title (2024) - most common for movies
    year = None
    title_part = s
    m = re.search(r"\((19|20)\d{2}\)", s)
    if m:
        year_match = re.search(r"(19|20)\d{2}", m.group(0))
        if year_match:
            year = int(year_match.group(0))
        title_part = s[: m.start()].strip()
    else:
        # Otherwise pick the last 4-digit year token between 1900-2099
        year = _extract_year_from_stem(s)
        if year:
            # Find the position of year to split the title
            year_match = None
            for match in YEAR_REGEX.finditer(s):
                if int(match.group(0)) == year:
                    year_match = match
                    break
            if year_match:
                title_part = s[: year_match.start()].strip()

    # Remove season/episode patterns from title (for TV shows that fall through)
    title_part = SEASON_EPISODE_REGEX.sub("", title_part)

    # Remove quality/format tags at the end
    title_part = QUALITY_FORMATS_REGEX.sub("", title_part)

    # Remove common noisy patterns
    noisy_patterns = [
        r"\b(S\d{1,2}E\d{1,2})\b",  # Season/episode
        r"\b(1080p|720p|480p|2160p|4k)\b",  # Resolution
        r"\b(WEB[-\s]?DL|BluRay|DVDRip)\b",  # Source
        r"\b(x264|x265|h\.264|h\.265)\b",  # Codec
        r"\b(DDP?\d*\.?\d*|AAC|AC3)\b",  # Audio
        r"\b(AMZN|NF|HBO|HULU)\b",  # Streaming services
        r"\b(NTb|ELiTE)\b",  # Release groups
        r"\[\w+\]",  # Bracketed tags
    ]

    for pattern in noisy_patterns:
        title_part = re.sub(pattern, "", title_part, flags=re.IGNORECASE)

    title_part = re.sub(r"\s+", " ", title_part).strip(" -_()")

    # Convert to title case if all caps
    if title_part.isupper():
        title_part = title_part.title()

    return title_part.strip(), year


def _extract_episode_title_from_filename(stem: str) -> Optional[str]:
    """
    Extract episode title from a TV show filename stem.

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
        if candidate and not SEASON_EPISODE_REGEX.search(candidate):
            return _sanitize_filename(candidate)

    # Fallback: last "-" segment, if it doesn't look like tech garbage
    parts = [p.strip() for p in s.split(" - ") if p.strip()]
    if len(parts) >= 2:
        candidate = parts[-1]
        if not SEASON_EPISODE_REGEX.search(candidate) and not QUALITY_FORMATS_REGEX.search(candidate):
            return _sanitize_filename(candidate)

    return None


### Public functions ###
def parse_media_file(filepath: Path) -> dict:
    """
    Parse a media file and extract all relevant metadata.

    Returns a dictionary with:
        - content_type: "TV Shows" or "Movies"
        - title: Clean title
        - year: Extracted year (if any)
        - season: Season number (TV only)
        - episode: Episode number (TV only)
        - episode_title: Episode title (TV only, if available)
        - date_str: Date string for date-based shows (if applicable)
    """
    stem = filepath.stem
    filename = filepath.name

    # Check if it's a TV show by looking for season/episode patterns
    season, episode = _parse_tv_filename(filename)

    if season is not None and episode is not None:
        # TV Show -优先使用父目录名作为标题
        parent_dir = filepath.parent.name

        # Clean up parent directory name (remove things like "(US)" etc.)
        parent_title = re.sub(r"\s*\([^)]*\)", "", parent_dir).strip()
        # Also clean up brackets and other patterns
        parent_title = re.sub(r"\[.*?]", "", parent_title).strip()
        # Clean up quality tags and release groups from parent directory
        parent_title = QUALITY_FORMATS_REGEX.sub("", parent_title)
        parent_title = re.sub(r"\.ELiTE.*", "", parent_title)
        parent_title = re.sub(r"\.NTb.*", "", parent_title)
        parent_title = re.sub(r"\.EZTV.*", "", parent_title)
        parent_title = re.sub(r"\.x265.*", "", parent_title)
        parent_title = re.sub(r"\.1080p.*", "", parent_title)
        parent_title = parent_title.strip()

        # Check if parent directory looks like a filename (contains quality tags, etc.)
        parent_is_filename = (
                SEASON_EPISODE_REGEX.search(parent_dir)
                or QUALITY_FORMATS_REGEX.search(parent_dir)
                or re.search(r"\[.*?]", parent_dir)  # Brackets
                or ".to" in parent_dir  # Domain-like patterns
                or re.search(r"\.(ELiTE|NTb|EZTV)", parent_dir)  # Release groups
                or "S25." in parent_dir  # Season-specific pattern
        )

        # Use parent directory title unless it's clearly a filename pattern or generic
        if parent_is_filename or parent_title.lower() in ["tv shows", "season", "episodes"]:
            title, year = _guess_title_and_year_from_stem(stem)
        else:
            title = parent_title
            # Try to extract year from filename since parent dir might not have it
            _, year = _guess_title_and_year_from_stem(stem)

        episode_title = _extract_episode_title_from_filename(stem)
        date_str, date_year = _parse_date_in_filename(filename)

        # Use date year if no year found in title
        if year is None and date_year is not None:
            year = date_year

        return {
            "content_type": "TV Shows",
            "title": title,
            "year": year,
            "season": season,
            "episode": episode,
            "episode_title": episode_title,
            "date_str": date_str,
        }
    else:
        # Movie
        title, year = _guess_title_and_year_from_stem(stem)

        return {
            "content_type": "Movies",
            "title": title,
            "year": year,
            "season": None,
            "episode": None,
            "episode_title": None,
            "date_str": None,
        }
