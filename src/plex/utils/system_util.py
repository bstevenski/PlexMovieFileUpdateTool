"""
Utility functions for running system commands and verifying binary availability.

This module provides helper functions to execute external commands and check if
required binaries exist in the system's PATH. These tools are particularly
useful in scenarios involving external dependencies, ensuring their availability
and proper configuration.

Functions:
    - run_cmd: Executes a system command and returns its exit code along with its
      standard output and error streams.
    - which_or_die: Checks for the presence of a specific binary on the system's
      PATH and terminates the process if it is unavailable.
"""
import shutil
import subprocess
import sys
from typing import Tuple, List

from plex.utils.logger import safe_print


def run_cmd(cmd: List[str]) -> Tuple[int, str, str]:
    """Run a command and return (code, stdout, stderr)."""
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return p.returncode, p.stdout, p.stderr


def which_or_die(binary: str):
    """Check if a binary exists on PATH, exit if not found."""
    if shutil.which(binary) is None:
        safe_print(f"ERROR: '{binary}' not found on PATH. Install it first (e.g. brew install ffmpeg).",
                   file=sys.stderr)
        sys.exit(2)
