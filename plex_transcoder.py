#!/usr/bin/env python3
import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional, Tuple, List

# Import shared functionality from common module
from plex_common import (
    VIDEO_EXTS,
    run_cmd,
    which_or_die,
    ffprobe_video_info,
    build_ffmpeg_cmd,
)

__version__ = "0.1.0"


# noinspection DuplicatedCode
def transcode_one(src: Path, src_root: Path, out_root: Path, args) -> Tuple[Path, Optional[Path], str]:
    """Transcode a single video file."""
    # Mirror folder structure under out_root
    rel = src.relative_to(src_root)
    dst = out_root / rel
    dst = dst.with_suffix(".mp4")  # Always output as .mp4

    if dst.exists() and not args.overwrite:
        return src, dst, "SKIP (already exists)"

    info = ffprobe_video_info(src)
    if not info:
        return src, None, "SKIP (ffprobe failed)"

    if args.skip_hevc and info.codec.lower() == "hevc":
        return src, None, "SKIP (already HEVC)"

    if args.only_avi and src.suffix.lower() != ".avi":
        return src, None, "SKIP (only-avi)"

    force_audio_aac = args.force_audio_aac or (src.suffix.lower() == ".avi")
    include_subs = not args.no_subs

    cmd = build_ffmpeg_cmd(src, dst, info, force_audio_aac=force_audio_aac, include_subs=include_subs)

    if args.dry_run:
        return src, dst, "DRY-RUN"

    code, out, err = run_cmd(cmd)
    if code != 0:
        # If subtitle copy caused failure, suggest retry without subs
        msg = f"FAIL (ffmpeg code {code})"
        if "Subtitle" in err or "subtitles" in err or "codec" in err:
            msg += " — (maybe subtitle stream not compatible with MP4; try --no-subs)"
        return src, None, msg

    # After successful transcoding, optionally delete the source
    if args.delete_source:
        try:
            src.unlink()
            return src, dst, "OK (source deleted)"
        except Exception as e:
            return src, dst, f"OK (failed to delete source: {e})"

    return src, dst, "OK"


# noinspection DuplicatedCode
def iter_video_files(root: Path) -> List[Path]:
    """Find all video files recursively."""
    files = []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS:
            files.append(p)
    return files


def main():
    parser = argparse.ArgumentParser(
        description="Batch transcode Plex media to HEVC (VideoToolbox) for Apple TV. "
                    "Designed to work with plex_renamer.py - run after renaming files.",
        epilog="Example: python3 plex_transcoder.py --src ./2.Staged --out ./4.Upload --skip-hevc --delete-source"
    )
    parser.add_argument("--src", required=True, help="Source root folder (e.g. 2.Staged from plex_renamer)")
    parser.add_argument("--out", required=True, help="Output root folder (e.g. 4.Upload for Plex)")
    parser.add_argument("--workers", type=int, default=2, help="Concurrent transcodes (M1 usually 1-2 is safe)")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen without transcoding")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing outputs")
    parser.add_argument("--skip-hevc", action="store_true", help="Skip files whose video codec is already HEVC (recommended)")
    parser.add_argument("--only-avi", action="store_true", help="Only process .avi files")
    parser.add_argument("--force-audio-aac", action="store_true", help="Force AAC audio for all outputs (AVI always uses AAC)")
    parser.add_argument("--no-subs", action="store_true", help="Do not include subtitle streams in output")
    parser.add_argument("--delete-source", action="store_true", help="Delete source files after successful transcode (recommended for production)")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args()

    which_or_die("ffmpeg")
    which_or_die("ffprobe")

    src_root = Path(args.src).expanduser().resolve()
    out_root = Path(args.out).expanduser().resolve()

    if not src_root.exists():
        print(f"ERROR: --src does not exist: {src_root}", file=sys.stderr)
        sys.exit(2)

    out_root.mkdir(parents=True, exist_ok=True)

    files = iter_video_files(src_root)
    if not files:
        print("No video files found.")
        return

    print(f"Found {len(files)} files under: {src_root}")
    print(f"Output will be written to: {out_root}")
    print(f"Workers: {args.workers} | dry-run: {args.dry_run} | skip-hevc: {args.skip_hevc} | only-avi: {args.only_avi}")

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(transcode_one, f, src_root, out_root, args): f for f in files}
        for fut in as_completed(futs):
            src, dst, status = fut.result()
            results.append((src, dst, status))
            if status.startswith("SKIP") or status.startswith("DRY-RUN"):
                print(f"[{status}] {src}")
            elif status.startswith("OK"):
                print(f"[{status}] {src} -> {dst}")
            else:
                print(f"[{status}] {src}")

    ok = sum(1 for _, _, s in results if s.startswith("OK"))
    skip = sum(1 for _, _, s in results if s.startswith("SKIP"))
    fail = sum(1 for _, _, s in results if s.startswith("FAIL"))
    dry = sum(1 for _, _, s in results if s.startswith("DRY-RUN"))

    print(f"\n🎉 Done. OK={ok} SKIP={skip} FAIL={fail} DRY-RUN={dry}")


if __name__ == "__main__":
    main()
