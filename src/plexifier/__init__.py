"""
Plex Media Tool - Automated Plex media file processing pipeline.

This package provides tools for processing media files downloaded from torrent
clients and preparing them for Plex, including filename parsing, TMDb metadata
lookup, file renaming, and video transcoding.
"""

__version__ = "1.0.0"
__author__ = "Bri Stevenski"

# Import main function for CLI entry point
from .plexifier import main

__all__ = ["main", "__version__", "__author__"]
