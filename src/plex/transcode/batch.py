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
    VIDEO_EXTENSIONS,
    system_util
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

    if args.skip_hevc and info.codec.lower() == "hevc":
        return src, None, f"{STATUS_SKIP} (already HEVC)"

    if args.only_avi and src.suffix.lower() != ".avi":
        return src, None, f"{STATUS_SKIP} (only-avi)"

    force_audio_aac = args.force_audio_aac or (src.suffix.lower() == ".avi")
    include_subs = not args.no_subs

    cmd = core.build_ffmpeg_cmd(src, dst, info, force_audio_aac=force_audio_aac, include_subs=include_subs)

    if args.dry_run:
        return src, dst, STATUS_DRY_RUN

    code, out, err = system_util.run_cmd(cmd)
    if code != 0:
        # If subtitle copy caused failure, suggest retry without subs
        msg = f"{STATUS_FAIL} (ffmpeg code {code})"
        if "Subtitle" in err or "subtitles" in err or "codec" in err:
            msg += " — (maybe subtitle stream not compatible with MP4; try --no-subs)"
        return src, None, msg

    # After successful transcoding, optionally delete the source
    if args.delete_source:
        try:
            src.unlink()
            return src, dst, f"{STATUS_OK} (source deleted)"
        except (OSError, PermissionError) as e:
            return src, dst, f"{STATUS_OK} (failed to delete source: {e})"

    return src, dst, STATUS_OK


def iter_video_files(root: Path) -> List[Path]:
    """Find all video files recursively."""
    files = []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS:
            files.append(p)
    return files
