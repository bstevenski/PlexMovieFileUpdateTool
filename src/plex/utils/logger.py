"""
Provides a thread-safe print function for multi-threaded environments.

This module ensures safe output to the standard output by guarding the `print`
function with a threading lock, preventing potential race conditions when used
from multiple threads.
"""
import threading

_print_lock = threading.Lock()


def safe_print(*args, **kwargs) -> None:
    """Thread-safe print function to prevent race conditions in multi-threaded environments."""
    with _print_lock:
        print(*args, **kwargs)


def log_lookup_tv(filename: str, season: int, episode: int) -> None:
    """Log TV file lookup."""
    safe_print(f"[LOOKUP] TV: {filename} (S{season:02d}E{episode:02d})")


def log_lookup_movie(filename: str) -> None:
    """Log movie file lookup."""
    safe_print(f"[LOOKUP] Movie: {filename}")


def log_matched(title: str, year: str, tmdb_id: int) -> None:
    """Log successful TMDb match."""
    safe_print(f"  └─ Matched: {title} ({year}) [tmdb-{tmdb_id}]")


def log_episode(episode_title: str, source: str) -> None:
    """Log episode information."""
    safe_print(f"  └─ Episode: {episode_title} (from {source})")


def log_transcode_start(source_name: str, target_name: str) -> None:
    """Log transcode start."""
    safe_print(f"[TRANSCODE] Starting: {source_name} -> {target_name}")


def log_transcode_complete(filename: str) -> None:
    """Log transcode completion."""
    safe_print(f"[TRANSCODE] Completed: {filename}")


def log_transcode_failed(filename: str) -> None:
    """Log transcode failure."""
    safe_print(f"[ERROR] Transcoding failed: {filename}")


def log_detail(message: str) -> None:
    """Log detailed information (indented tree format)."""
    safe_print(f"  └─ {message}")
