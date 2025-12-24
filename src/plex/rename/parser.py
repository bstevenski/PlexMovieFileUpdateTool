"""
Module for parsing and sanitizing filenames, extracting title and metadata components
such as season, episode numbers, and dates, as well as cleaning text for further usage.
Primarily used in media management or indexing systems.
"""

import re

from plex.utils import DATE_REGEXES, SEASON_EPISODE_REGEX, file_util


def parse_tv_filename(filename: str) -> tuple[int | None, int | None]:
    """Extract season and episode numbers from a filename."""
    match = SEASON_EPISODE_REGEX.search(filename)
    if match:
        season = int(match.group(1))
        episode = int(match.group(2))
        return season, episode
    return None, None


def parse_date_in_filename(filename: str) -> tuple[str | None, int | None]:
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


def guess_title_and_year_from_stem(stem: str) -> tuple[str, str | None]:
    """
    Best-effort extraction of a human title and a (possible) year from a noisy filename stem.
    Examples:
      "Movie.Title.2024.2160p.WEB-DL" -> ("Movie Title", "2024")
      "Intervention.S01E05.720p" -> ("Intervention", None)
      "Chernobyl Diaries (2012)" -> ("Chernobyl Diaries", "2012")
    """
    # Normalize text
    s = file_util.normalize_text(stem)

    # First try parentheses style: Title (2024) - most common for movies
    year = None
    title_part = s
    m = re.search(r"\((19|20)\d{2}\)", s)
    if m:
        year = re.search(r"(19|20)\d{2}", m.group(0)).group(0)
        title_part = s[: m.start()].strip()
    else:
        # Otherwise pick the last 4-digit year token between 1900-2099
        year_match = None
        for match in re.finditer(r"(19|20)\d{2}", s):
            year_match = match
        if year_match:
            year = year_match.group(0)
            title_part = s[: year_match.start()].strip()

    # Remove leftover common tags like resolution/encoders at the end
    title_part = re.sub(
        r"\b(480p|720p|1080p|2160p|4k|hdr|hdr10\+?|dv|web[- ]?dl|bluray|webrip|x264|x265|h\.264|h\.265|ddp?\d?\.?\d?|atmos|remux)\b",
        "",
        title_part,
        flags=re.IGNORECASE,
    )
    title_part = re.sub(r"\s+", " ", title_part).strip(" -_()")
    # Title case lightly (don't shout)
    if title_part.isupper():
        title_part = title_part.title()
    return title_part.strip(), year


def extract_episode_title_from_filename(stem: str) -> str | None:
    """
    Attempt to extract a human episode title from a filename stem.
    Examples:
      "Intervention - s08e11 - Marquel" -> "Marquel"
      "Ghosts - S01E01 - Pilot" -> "Pilot"
    Returns None if no obvious title segment exists.
    """
    s = file_util.normalize_text(stem)

    # Prefer the segment after the sXXeYY token
    m = re.search(r"[Ss]\d{1,2}[Ee]\d{1,2}\s*-\s*(.+)$", s)
    if m:
        candidate = m.group(1).strip(" -_")
        if candidate:
            return file_util.sanitize_filename(candidate)

    # Fallback: last "-" segment, if it doesn't look like just tech garbage
    parts = [p.strip() for p in s.split(" - ") if p.strip()]
    if len(parts) >= 2:
        candidate = parts[-1]
        if not SEASON_EPISODE_REGEX.search(candidate):
            return file_util.sanitize_filename(candidate)

    return None


def clean_search_title(stem: str, date_str: str | None = None) -> str:
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
        ds = date_str.replace("-", "[\\-_. ]")
        try:
            search_title = re.sub(ds, "", search_title)
        except re.error:
            pass
    return file_util.normalize_text(search_title)
