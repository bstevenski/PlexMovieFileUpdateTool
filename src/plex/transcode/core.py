"""
Functions to gather video information and generate ffmpeg commands for transcoding.

This module provides functionality to extract details about a video file's codec and
attributes using ffprobe, determine if a video qualifies as 4K or HDR, and create
customized ffmpeg command lines for transcoding video content to the HEVC format.
"""
import json
import platform
import re
import subprocess
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional, List, Tuple

from plex.utils import system_util, logger, time_util, LogLevel


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


def _is_4k(info: VideoInfo) -> bool:
    """Check if video resolution is 4K or higher."""
    return (info.width or 0) >= 3800 or (info.height or 0) >= 2000


def _looks_hdr(info: VideoInfo) -> bool:
    """Check if video appears to be HDR based on color metadata."""
    return (info.color_primaries == "bt2020") or (info.color_transfer in {"smpte2084", "arib-std-b67"})


@lru_cache(maxsize=1)
def _available_ffmpeg_encoders() -> List[str]:
    """Return a cached list of available ffmpeg encoders."""
    code, out, _ = system_util.run_cmd(["ffmpeg", "-hide_banner", "-encoders"])
    if code != 0:
        return []

    encoders = []
    for line in out.splitlines():
        parts = line.split()
        # Lines look like: " V..... hevc_videotoolbox ..."
        if len(parts) >= 2 and parts[0].startswith("V"):
            encoders.append(parts[1])
        elif len(parts) >= 3 and parts[1].startswith("V"):
            encoders.append(parts[2])
    return encoders


def _select_encoder(preferred: Optional[str] = None) -> str:
    """Pick an ffmpeg HEVC encoder with platform-aware fallbacks."""
    encoders = set(_available_ffmpeg_encoders())

    if preferred:
        if preferred in encoders:
            return preferred
        logger.safe_print(f"WARN: Requested encoder '{preferred}' not found. Falling back automatically.")

    system = platform.system()
    candidates: List[str]
    if system == "Darwin":
        candidates = ["hevc_videotoolbox", "hevc_nvenc", "hevc_qsv", "libx265"]
    elif system == "Windows":
        candidates = ["hevc_nvenc", "hevc_qsv", "hevc_amf", "libx265"]
    else:
        candidates = ["hevc_nvenc", "hevc_qsv", "libx265"]

    for encoder in candidates:
        if encoder in encoders:
            return encoder

    # Last resort, use libx265 even if ffmpeg did not list encoders (will error clearly later)
    return "libx265"


def _build_ffmpeg_cmd(src: Path, dst: Path, info: VideoInfo, force_audio_aac: bool,
                      preferred_encoder: Optional[str]) -> List[str]:
    """Build ffmpeg command for transcoding video to HEVC."""
    dst.parent.mkdir(parents=True, exist_ok=True)

    encoder = _select_encoder(preferred_encoder)

    if _is_4k(info):
        v_bitrate = "20000k"
        maxrate = "25000k"
        bufsize = "40000k"
        profile = "main10"
        pix_fmt = "p010le" if _looks_hdr(info) else "yuv420p"
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
        "-map", "0:v:0",
        "-map", "0:a?",
        "-c:v", encoder,
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
                    debug: bool = False, delete_source: bool = False,
                    video_encoder: Optional[str] = None) -> Tuple[
    int, str, str]:
    """
    Transcode a video file to HEVC with logging and progress updates.

    Args:
        src: Source video file path
        dst: Destination video file path
        info: Video information from ffprobe
        force_audio_aac: Force AAC audio encoding (default: False, copies audio)
        debug: Enable debug logging (default: False)
        delete_source: Delete source file after successful transcode (default: False)

    Returns:
        Tuple of (exit_code, stdout, stderr)
    """
    cmd = _build_ffmpeg_cmd(src, dst, info, force_audio_aac, video_encoder)

    logger.log("transcode.start", LogLevel.INFO,
               file=src.name,
               dst=dst.name)

    if debug:
        is_4k_video = _is_4k(info)
        is_hdr_video = _looks_hdr(info)
        logger.log("transcode.details", LogLevel.DEBUG,
                   source_codec=info.codec.upper(),
                   source_res=f"{info.width}x{info.height}",
                   target="HEVC (H.265)",
                   encoder=cmd[cmd.index("-c:v") + 1],
                   quality='4K' if is_4k_video else '1080p',
                   hdr='HDR' if is_hdr_video else 'SDR',
                   audio='AAC' if force_audio_aac else 'Copy')

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

                        try:
                            # Convert time string to seconds
                            time_parts = time_str.split(':')
                            if len(time_parts) == 3:
                                elapsed_seconds = float(time_parts[0]) * 3600 + float(time_parts[1]) * 60 + float(
                                    time_parts[2])

                                if info.duration:
                                    # Calculate percentage
                                    percent = (elapsed_seconds / info.duration) * 100

                                    # Calculate ETA based on encoding speed
                                    speed_val = float(speed_str)
                                    if speed_val > 0:
                                        eta_str = time_util.get_eta_single_file(info.duration, speed_val,
                                                                                elapsed_seconds)

                                        logger.log("transcode.progress", LogLevel.INFO,
                                                   file=src.name,
                                                   pct=round(percent, 1),
                                                   eta=eta_str,
                                                   speed=f"{speed_str}x")
                                    else:
                                        logger.log("transcode.progress", LogLevel.INFO,
                                                   file=src.name,
                                                   pct=round(percent, 1),
                                                   speed=f"{speed_str}x")
                                else:
                                    # Duration not available
                                    logger.log("transcode.progress", LogLevel.INFO,
                                               file=src.name,
                                               pct="N/A",
                                               eta="N/A",
                                               speed=f"{speed_str}x")
                        except (ValueError, ZeroDivisionError):
                            pass  # Skip progress update if parsing fails

                        last_progress_log = current_time

    # Wait for process to complete and get remaining output
    stdout, remaining_stderr = process.communicate()
    stderr_output.append(remaining_stderr)

    stderr_text = ''.join(stderr_output)
    code = process.returncode

    if code != 0:
        logger.log("transcode.failed", LogLevel.ERROR,
                   file=src.name,
                   exit_code=code,
                   error=stderr_text[:200] if debug else "see logs")
    else:
        source_deleted = False
        if delete_source:
            try:
                src.unlink()
                source_deleted = True
            except (OSError, PermissionError) as e:
                logger.log("transcode.delete_failed", LogLevel.WARN,
                           file=src.name,
                           error=str(e))

        logger.log("transcode.complete", LogLevel.INFO,
                   file=src.name,
                   source_deleted=source_deleted)

    return code, stdout, stderr_text
