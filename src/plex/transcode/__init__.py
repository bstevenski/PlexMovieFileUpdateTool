"""Video transcoding functionality for Plex media processing.

This package provides two levels of functionality:
- core: Low-level FFmpeg utilities (VideoInfo, probing, command building)
- batch: High-level transcoding orchestration (single file processing, file discovery)
"""
# Public transcode functions
from .batch import (
    transcode_one,
    iter_video_files,
)
from .core import (
    VideoInfo,
    ffprobe_video_info,
    transcode_video,
)

__all__ = [
    "VideoInfo",
    "ffprobe_video_info",
    "transcode_video",
    "transcode_one",
    "iter_video_files",
]
