"""Video transcoding functionality for Plex media processing.

This package provides two levels of functionality:
- core: Low-level FFmpeg utilities (VideoInfo, probing, command building)
- batch: High-level transcoding orchestration (single file processing, file discovery)
"""

from .core import (
    VideoInfo,
    ffprobe_video_info,
    is_4k,
    looks_hdr,
    build_ffmpeg_cmd,
    transcode_video,
)
from .batch import (
    transcode_one,
    iter_video_files,
)

__all__ = [
    # Video info
    "VideoInfo",
    "ffprobe_video_info",
    "is_4k",
    "looks_hdr",
    # Transcoding
    "build_ffmpeg_cmd",
    "transcode_video",
    "transcode_one",
    "iter_video_files",
]
