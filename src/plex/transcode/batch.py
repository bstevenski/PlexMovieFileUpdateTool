"""
This module provides functionality for video transcoding and recursive discovery
of video files in specified directories.

The module includes methods for transcoding individual video files to a specific
format and discovering video files supporting defined extensions within a folder
and its subfolders.
"""
from pathlib import Path
from typing import Optional, Tuple, List

from plex.utils import (
    STATUS_SKIP,
    STATUS_OK,
    STATUS_FAIL,
    STATUS_DRY_RUN,
    VIDEO_EXTENSIONS
)
from . import core


def transcode_one(src: Path, src_root: Path, out_root: Path, args) -> Tuple[Path, Optional[Path], str]:
    """Transcode a single video file."""
    # Mirror folder structure under out_root
    rel = src.relative_to(src_root)
    dst = out_root / rel
    dst = dst.with_suffix(".mp4")  # Always output as .mp4

    if dst.exists() and not args.overwrite:
        return src, dst, f"{STATUS_SKIP} (already exists)"

    info = core.ffprobe_video_info(src)
    if not info:
        return src, None, f"{STATUS_SKIP} (ffprobe failed)"

    # Always process HEVC too; queue should contain files that need processing

    force_audio_aac = getattr(args, "force_audio_aac", False) or (src.suffix.lower() == ".avi")
    include_subs = not getattr(args, "no_subs", False)

    if getattr(args, "dry_run", False):
        return src, dst, STATUS_DRY_RUN

    code, out, err = core.transcode_video(src, dst, info, force_audio_aac=force_audio_aac,
                                          include_subs=include_subs, debug=args.debug,
                                          delete_source=args.delete_source)
    if code != 0:
        # If subtitle copy caused failure, suggest retry without subs
        msg = f"{STATUS_FAIL} (ffmpeg code {code})"
        if "Subtitle" in err or "subtitles" in err or "codec" in err:
            msg += " — (maybe subtitle stream not compatible with MP4; try --no-subs)"
        return src, None, msg

    return src, dst, STATUS_OK


def iter_video_files(root: Path) -> List[Path]:
    """Find all video files recursively."""
    files = []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS:
            files.append(p)
    return files
