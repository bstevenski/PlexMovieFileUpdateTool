"""
Functions to gather video information and generate ffmpeg commands for transcoding.

This module provides functionality to extract details about a video file's codec and
attributes using ffprobe, determine if a video qualifies as 4K or HDR, and create
customized ffmpeg command lines for transcoding video content to the HEVC format.
"""
import json
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Tuple

from plex.utils import system_util
from plex.utils.logger import (
    log_transcode_start,
    log_transcode_complete,
    log_transcode_failed,
    log_detail,
    safe_print
)


@dataclass
class VideoInfo:
    codec: str
    width: Optional[int]
    height: Optional[int]
    pix_fmt: Optional[str]
    color_primaries: Optional[str]
    color_transfer: Optional[str]
    color_space: Optional[str]
    duration: Optional[float] = None


def ffprobe_video_info(path: Path) -> Optional[VideoInfo]:
    """Probe video file for codec and format information including duration."""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries",
        "stream=codec_name,width,height,pix_fmt,color_primaries,color_transfer,color_space:format=duration",
        "-of", "json",
        str(path)
    ]
    code, out, err = system_util.run_cmd(cmd)
    if code != 0:
        return None
    data = json.loads(out)
    streams = data.get("streams") or []
    if not streams:
        return None
    s = streams[0]

    # Get duration from format section
    duration = None
    if "format" in data and "duration" in data["format"]:
        try:
            duration = float(data["format"]["duration"])
        except (ValueError, TypeError):
            pass

    return VideoInfo(
        codec=s.get("codec_name", ""),
        width=s.get("width"),
        height=s.get("height"),
        pix_fmt=s.get("pix_fmt"),
        color_primaries=s.get("color_primaries"),
        color_transfer=s.get("color_transfer"),
        color_space=s.get("color_space"),
        duration=duration
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
        "-map", "0:v",
        "-map", "0:a",
        "-c:v", "hevc_videotoolbox",
        "-b:v", v_bitrate,
        "-maxrate", maxrate,
        "-bufsize", bufsize,
        "-profile:v", profile,
        "-pix_fmt", pix_fmt,
        "-tag:v", "hvc1",
    ]

    if force_audio_aac:
        cmd += ["-c:a", "aac", "-b:a", "192k"]
    else:
        cmd += ["-c:a", "copy"]

    # Subtitles are currently skipped because:
    # - Text subtitles (SRT, ASS) can be converted to mov_text
    # - Bitmap subtitles (PGS, VobSub) cannot be stored in MP4 containers
    # - ffmpeg cannot selectively convert only text subs when both types are present
    # - Error 234 occurs when trying to convert bitmap subs to mov_text
    # TODO: Add intelligent subtitle handling with per-stream codec detection
    # For now, subtitles are excluded to avoid transcode failures

    cmd += ["-movflags", "+faststart", str(dst)]
    return cmd


def transcode_video(src: Path, dst: Path, info: VideoInfo, force_audio_aac: bool = False,
                    include_subs: bool = True, debug: bool = False) -> Tuple[int, str, str]:
    """
    Transcode a video file to HEVC with logging and progress updates.

    Args:
        src: Source video file path
        dst: Destination video file path
        info: Video information from ffprobe
        force_audio_aac: Force AAC audio encoding (default: False, copies audio)
        include_subs: Include subtitle streams (default: True)
        debug: Enable debug logging (default: False)

    Returns:
        Tuple of (exit_code, stdout, stderr)
    """
    cmd = build_ffmpeg_cmd(src, dst, info, force_audio_aac, include_subs)

    log_transcode_start(src.name, dst.name)
    if debug:
        is_4k_video = is_4k(info)
        is_hdr_video = looks_hdr(info)
        log_detail(f"Source: {info.codec.upper()} {info.width}x{info.height}")
        log_detail(f"Target: HEVC (H.265) {'4K' if is_4k_video else '1080p'} {'HDR' if is_hdr_video else 'SDR'}")
        log_detail(f"Audio: {'AAC' if force_audio_aac else 'Copy'} | Subtitles: {'Yes' if include_subs else 'No'}")

    # Run ffmpeg with progress monitoring
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    stderr_output = []
    last_progress_log = time.time()
    progress_interval = 60  # Log progress every 60 seconds

    # Read stderr line by line for progress updates
    while True:
        line = process.stderr.readline()
        if not line and process.poll() is not None:
            break

        if line:
            stderr_output.append(line)

            # Parse ffmpeg progress (looks for "time=" and "speed=" in output)
            # Example: frame= 1234 fps=18 q=-0.0 size=  10240KiB time=00:01:23.45 bitrate=1234.5kbits/s speed=0.75x
            if "time=" in line and "speed=" in line:
                current_time = time.time()
                if current_time - last_progress_log >= progress_interval:
                    # Extract time and speed from the line
                    time_match = re.search(r'time=(\S+)', line)
                    speed_match = re.search(r'speed=(\S+)', line)

                    if time_match and speed_match:
                        time_str = time_match.group(1)
                        speed_str = speed_match.group(1).rstrip('x')
                        size_match = re.search(r'size=\s*(\S+)', line)

                        try:
                            # Convert time string to seconds
                            time_parts = time_str.split(':')
                            if len(time_parts) == 3:
                                elapsed_seconds = float(time_parts[0]) * 3600 + float(time_parts[1]) * 60 + float(time_parts[2])

                                if info.duration:
                                    # Calculate percentage
                                    percent = (elapsed_seconds / info.duration) * 100

                                    # Calculate ETA based on encoding speed
                                    speed_val = float(speed_str)
                                    if speed_val > 0:
                                        remaining_seconds = (info.duration - elapsed_seconds) / speed_val
                                        eta_minutes = int(remaining_seconds / 60)
                                        eta_hours = eta_minutes // 60
                                        eta_mins = eta_minutes % 60

                                        if eta_hours > 0:
                                            eta_str = f"{eta_hours}h {eta_mins}m"
                                        else:
                                            eta_str = f"{eta_mins}m"

                                        safe_print(f"  └─ Progress [{src.name}]: {percent:.1f}% complete | ETA: {eta_str} (speed: {speed_str}x)")
                                    else:
                                        safe_print(f"  └─ Progress [{src.name}]: {percent:.1f}% complete")
                                else:
                                    # Duration not available
                                    safe_print(f"  └─ Progress [{src.name}]: N/A complete | ETA: N/A (speed: {speed_str}x)")
                        except (ValueError, ZeroDivisionError):
                            pass  # Skip progress update if parsing fails

                        last_progress_log = current_time

    # Wait for process to complete and get remaining output
    stdout, remaining_stderr = process.communicate()
    stderr_output.append(remaining_stderr)

    stderr_text = ''.join(stderr_output)
    code = process.returncode

    if code != 0:
        log_transcode_failed(src.name)
        if debug:
            log_detail(f"Error: {stderr_text[:200]}")
    else:
        log_transcode_complete(src.name)

    return code, stdout, stderr_text
