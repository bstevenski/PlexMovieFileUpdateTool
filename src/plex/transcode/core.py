"""
Functions to gather video information and generate ffmpeg commands for transcoding.

This module provides functionality to extract details about a video file's codec and
attributes using ffprobe, determine if a video qualifies as 4K or HDR, and create
customized ffmpeg command lines for transcoding video content to the HEVC format.
"""
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List

from plex.utils import system_util


@dataclass
class VideoInfo:
    codec: str
    width: Optional[int]
    height: Optional[int]
    pix_fmt: Optional[str]
    color_primaries: Optional[str]
    color_transfer: Optional[str]
    color_space: Optional[str]


def ffprobe_video_info(path: Path) -> Optional[VideoInfo]:
    """Probe video file for codec and format information."""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries",
        "stream=codec_name,width,height,pix_fmt,color_primaries,color_transfer,color_space",
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
    return VideoInfo(
        codec=s.get("codec_name", ""),
        width=s.get("width"),
        height=s.get("height"),
        pix_fmt=s.get("pix_fmt"),
        color_primaries=s.get("color_primaries"),
        color_transfer=s.get("color_transfer"),
        color_space=s.get("color_space"),
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
        "-map", "0",
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

    if include_subs:
        cmd += ["-c:s", "copy"]
    else:
        cmd += ["-sn"]

    cmd += ["-movflags", "+faststart", str(dst)]
    return cmd
