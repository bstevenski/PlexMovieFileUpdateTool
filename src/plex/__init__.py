"""
A media processing module for renaming, parsing, and transcoding operations.

This module provides a set of utilities for managing media files associated with
Plex media server workflows. It supports features like renaming TV and movie files,
interfacing with TMDb for metadata lookup, and handling video transcoding. Core
functionalities include retrieving video information, sanitizing file names, and
managing output settings.

The module is organized into several categories:
- Parsing and renaming files (movies and TV shows).
- Interfacing with TMDb for metadata-related operations.
- Utility functions for system commands and file handling.
- Video transcoding capabilities to ensure media compatibility with supported devices.
"""

__version__ = "1.0.0"

# Debug flag for controlling verbose output
DEBUG: bool = False

__all__ = ["__version__", "DEBUG"]
