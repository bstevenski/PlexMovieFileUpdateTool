"""
Provides structured logging with thread-safety and log levels.

This module provides a structured logging system with UTC timestamps, log levels,
and key-value pair formatting for better log parsing and analysis.
"""
import threading
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any

_print_lock = threading.Lock()
_log_level = None
_worker_id_map = {}
_worker_counter = 0
_worker_lock = threading.Lock()
_separator = " | "


class LogLevel(Enum):
    """Log level enumeration."""
    TRACE = 0
    DEBUG = 1
    INFO = 2
    WARN = 3
    ERROR = 4


_current_level = LogLevel.INFO


def set_log_level(level: LogLevel) -> None:
    """Set the current log level."""
    global _current_level
    _current_level = level


def get_log_level() -> LogLevel:
    """Get the current log level."""
    return _current_level


def _format_kv(data: Dict[str, Any]) -> str:
    """Format key-value pairs for logging."""
    parts = []
    for key, value in data.items():
        if isinstance(value, str):
            # Escape quotes and newlines to keep log entries single-line.
            escaped = value.replace("\r", "\\r").replace("\n", "\\n")
            escaped = escaped.replace('"', '\\"')
            parts.append(f'{key}="{escaped}"')
        elif value is None:
            parts.append(f'{key}=null')
        elif isinstance(value, bool):
            parts.append(f'{key}={str(value).lower()}')
        else:
            parts.append(f'{key}={value}')
    return _separator.join(parts)


def _write_line(text: str) -> None:
    try:
        from tqdm import tqdm
    except Exception:
        print(text, flush=True)
        return

    try:
        tqdm.write(text)
    except Exception:
        print(text, flush=True)


def _should_log(level: LogLevel) -> bool:
    """Check if a message at the given level should be logged."""
    return level.value >= _current_level.value


def log(event: str, level: LogLevel = LogLevel.INFO, **kwargs) -> None:
    """
    Structured logging function.

    Args:
        event: Event name (e.g., 'rename.propose', 'transcode.complete')
        level: Log level (TRACE, DEBUG, INFO, WARN, ERROR)
        **kwargs: Key-value pairs to log
    """
    if not _should_log(level):
        return

    # Add worker/thread info
    if "worker" not in kwargs:
        kwargs["worker"] = get_worker_id()

    with _print_lock:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        level_str = level.name
        kv_str = _format_kv(kwargs) if kwargs else ""
        header = f"{timestamp}{_separator}[{level_str}]{_separator}{event}"

        if kv_str:
            _write_line(f"{header}{_separator}{kv_str}")
        else:
            _write_line(header)


def safe_print(*args, **kwargs) -> None:
    """
    Thread-safe print function (legacy support).
    Use log() for structured logging instead.
    """
    with _print_lock:
        print(*args, **kwargs, flush=True)


def get_worker_id() -> str:
    """Get current worker/thread identifier (numeric ID for worker threads)."""
    global _worker_counter
    thread = threading.current_thread()

    if thread.name == "MainThread":
        return "main"

    # Check if we've already assigned an ID to this thread
    if thread.ident in _worker_id_map:
        return _worker_id_map[thread.ident]

    # Assign a new worker ID
    with _worker_lock:
        _worker_counter += 1
        worker_id = f"w{_worker_counter}"
        _worker_id_map[thread.ident] = worker_id
        return worker_id
