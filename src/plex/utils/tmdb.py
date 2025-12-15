"""TMDb API integration for movie and TV metadata lookup."""
import threading
import typing

import requests

from . import constants
from . import logger

# Validate API key
if not constants.TMDB_API_KEY:
    raise ValueError("TMDB_API_KEY environment variable is not set!")

# Thread-safe caching
_tmdb_cache = {}
_cache_lock = threading.Lock()


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
        if constants.DEBUG:
            logger.safe_print(f"[TMDb] Error {error_context}: {e}")
    return None


def search_tmdb_movie(title: str, year: typing.Optional[int] = None) -> typing.Optional[dict]:
    """
    Search TMDb for a movie.
    Returns movie data including TMDb ID, title, and release year or None if not found.
    Uses in-memory cache to avoid redundant API calls.
    """
    # Check cache first
    cache_key = f"movie:{title}:{year}"
    with _cache_lock:
        if cache_key in _tmdb_cache:
            return _tmdb_cache[cache_key]

    url = f"{constants.TMDB_BASE_URL}/search/movie"
    params = {
        "api_key": constants.TMDB_API_KEY,
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
    year_val = release_date[:4] if release_date else "Unknown"

    result = {
        "tmdb_id": movie.get("id"),
        "title": movie.get("title"),
        "year": year_val,
        "original_title": movie.get("original_title")
    }

    # Cache the result
    with _cache_lock:
        _tmdb_cache[cache_key] = result

    return result


def search_tmdb_tv(title: str, year: typing.Optional[int] = None) -> typing.Optional[dict]:
    """
    Search TMDb for a TV series.
    Returns series data including TMDb ID, name, and year range or None if not found.
    Uses in-memory cache to avoid redundant API calls.
    """
    # Check cache first
    cache_key = f"tv:{title}:{year}"
    with _cache_lock:
        if cache_key in _tmdb_cache:
            return _tmdb_cache[cache_key]

    url = f"{constants.TMDB_BASE_URL}/search/tv"
    params = {
        "api_key": constants.TMDB_API_KEY,
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
    details_url = f"{constants.TMDB_BASE_URL}/tv/{tmdb_id}"
    details_params = {"api_key": constants.TMDB_API_KEY}
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

        result = {
            "tmdb_id": tmdb_id,
            "name": details.get("name"),
            "year": year_str,
            "original_name": details.get("original_name")
        }
    else:
        # Fallback if details fetch fails
        first_air = show.get("first_air_date", "")
        year_val = first_air[:4] if first_air else "Unknown"
        result = {
            "tmdb_id": tmdb_id,
            "name": show.get("name"),
            "year": year_val,
            "original_name": show.get("original_name")
        }

    # Cache the result
    with _cache_lock:
        _tmdb_cache[cache_key] = result

    return result


def get_tmdb_episode(tmdb_id: int, season: int, episode: int):
    """
    Get episode details from TMDb by show ID, season, and episode number.
    """
    url = f"{constants.TMDB_BASE_URL}/tv/{tmdb_id}/season/{season}/episode/{episode}"
    params = {"api_key": constants.TMDB_API_KEY}

    data = _make_tmdb_request(url, params, f"getting episode s{season:02d}e{episode:02d}")
    if not data:
        return None

    return {
        "name": data.get("name"),
        "season": season,
        "episode": episode
    }
