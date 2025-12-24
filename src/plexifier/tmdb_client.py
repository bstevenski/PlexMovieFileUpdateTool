"""
TMDb API client for fetching movie and TV show metadata.

This module provides a clean interface to The Movie Database API,
handling search requests, error handling, and response parsing.
"""

import logging
from typing import Dict, List, Optional, Any

import requests

from constants import TMDB_API_KEY, TMDB_BASE_URL

logger = logging.getLogger(__name__)


class TMDbError(Exception):
    """Base exception for TMDb API errors."""

    pass


class TMDbAPIError(TMDbError):
    """Exception for API request failures."""

    pass


class TMDbNotFoundError(TMDbError):
    """Exception for when content is not found."""

    pass


class TMDbClient:
    """Client for interacting with The Movie Database API."""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize the TMDb client with an API key."""
        self.api_key = api_key or TMDB_API_KEY
        if not self.api_key:
            raise TMDbError("TMDb API key is required. Set TMDB_API_KEY environment variable.")

        self.session = requests.Session()
        self.session.params = {"api_key": self.api_key}

    def _make_request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make a request to the TMDb API and handle errors."""
        url = f"{TMDB_BASE_URL}/{endpoint.lstrip('/')}"

        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()

            data = response.json()

            if "success" in data and not data["success"]:
                raise TMDbAPIError(f"TMDb API error: {data.get('status_message', 'Unknown error')}")

            return data

        except requests.exceptions.RequestException as e:
            raise TMDbAPIError(f"Request failed: {e}")
        except ValueError as e:
            raise TMDbAPIError(f"Invalid JSON response: {e}")

    def search_movie(self, title: str, year: Optional[int] = None) -> List[Dict[str, Any]]:
        """Search for movies by title and optionally year."""
        params = {"query": title}
        if year:
            params["year"] = str(year)

        logger.info(f"🔍 Searching TMDb for movie: '{title}' ({year})")
        data = self._make_request("search/movie", params)
        results = data.get("results", [])
        logger.info(f"📊 TMDb returned {len(results)} movie results")
        return results

    def search_tv_show(self, title: str, first_air_date_year: Optional[int] = None) -> List[Dict[str, Any]]:
        """Search for TV shows by title and optionally first air date year."""
        params = {"query": title}
        if first_air_date_year:
            params["first_air_date_year"] = str(first_air_date_year)

        logger.info(f"🔍 Searching TMDb for TV show: '{title}' ({first_air_date_year})")
        data = self._make_request("search/tv", params)
        results = data.get("results", [])
        logger.info(f"📊 TMDb returned {len(results)} TV show results")
        return results

    def get_movie_details(self, tmdb_id: int) -> Dict[str, Any]:
        """Get detailed information for a specific movie."""
        logger.debug(f"Getting movie details for ID: {tmdb_id}")
        return self._make_request(f"movie/{tmdb_id}")

    def get_tv_show_details(self, tmdb_id: int) -> Dict[str, Any]:
        """Get detailed information for a specific TV show."""
        logger.debug(f"Getting TV show details for ID: {tmdb_id}")
        return self._make_request(f"tv/{tmdb_id}")

    def get_tv_episode_details(self, tmdb_id: int, season_number: int, episode_number: int) -> Dict[str, Any]:
        """Get detailed information for a specific TV episode."""
        logger.debug(f"Getting episode details for show ID {tmdb_id}, S{season_number}E{episode_number}")
        return self._make_request(f"tv/{tmdb_id}/season/{season_number}/episode/{episode_number}")

    def find_best_movie_match(self, title: str, year: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Find the best matching movie for a given title and year."""
        results = self.search_movie(title, year)

        if not results:
            logger.warning(f"❌ No TMDb results found for movie: '{title}' ({year})")
            return None

        # If we have a Year, prefer exact year matches
        if year:
            exact_matches = [r for r in results if r.get("release_date", "").startswith(str(year))]
            if exact_matches:
                result = exact_matches[0]
                logger.info(f"✅ Found exact year match: '{result.get('title')}' ({result.get('release_date')})")
                return result

        # Return the first (highest rated) result
        result = results[0]
        logger.info(
            f"🎬 Using best match: '{result.get('title')}' ({result.get('release_date')}) - ID: {result.get('id')}"
        )
        return result

    def find_best_tv_match(self, title: str, year: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Find the best matching TV show for a given title and year."""
        results = self.search_tv_show(title, year)

        if not results:
            logger.warning(f"❌ No TMDb results found for TV show: '{title}' ({year})")
            return None

        # If we have a Year, prefer exact year matches
        if year:
            exact_matches = [r for r in results if r.get("first_air_date", "").startswith(str(year))]
            if exact_matches:
                result = exact_matches[0]
                logger.info(f"✅ Found exact year match: '{result.get('name')}' ({result.get('first_air_date')})")
                return result

        # Return the first (highest rated) result
        result = results[0]
        logger.info(
            f"📺 Using best match: '{result.get('name')}' ({result.get('first_air_date')}) - ID: {result.get('id')}"
        )
        return result

    def get_episode_info(self, tmdb_id: int, season_number: int, episode_number: int) -> Optional[Dict[str, Any]]:
        """Get episode information, returning None if not found."""
        try:
            return self.get_tv_episode_details(tmdb_id, season_number, episode_number)
        except TMDbAPIError as e:
            if "404" in str(e):
                logger.debug(f"Episode S{season_number}E{episode_number} not found for show ID {tmdb_id}")
                return None
            raise
