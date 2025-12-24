"""
This module provides functionality for video transcoding and recursive discovery
of video files in specified directories.

The module includes methods for transcoding individual video files to a specific
format and discovering video files supporting defined extensions within a folder
and its subfolders.
"""

from pathlib import Path

from plex.utils import STATUS_DRY_RUN, STATUS_FAIL, STATUS_OK, STATUS_SKIP, VIDEO_EXTENSIONS
from . import core


def transcode_one(src: Path, src_root: Path, out_root: Path, args) -> tuple[Path, Path | None, str]:
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

    # Skip HEVC files if skip_hevc flag is set
    skip_hevc = getattr(args, "skip_hevc", False)
    if skip_hevc and info.codec.lower() == "hevc":
        return src, dst, f"{STATUS_SKIP} (HEVC codec with skip_hevc enabled)"

    force_audio_aac = getattr(args, "force_audio_aac", False) or (src.suffix.lower() == ".avi")
    if getattr(args, "dry_run", False):
        return src, dst, STATUS_DRY_RUN

    code, out, err = core.transcode_video(
        src,
        dst,
        info,
        force_audio_aac=force_audio_aac,
        debug=args.debug,
        delete_source=args.delete_source,
        video_encoder=getattr(args, "video_encoder", None),
    )
    if code != 0:
        msg = f"{STATUS_FAIL} (ffmpeg code {code})"
        return src, None, msg

    return src, dst, STATUS_OK


def iter_video_files(root: Path) -> list[Path]:
    """Find all video files recursively."""
    files = []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS:
            files.append(p)
    return files
