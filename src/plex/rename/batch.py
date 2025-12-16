# python
"""Batch rename utilities for Plex-compatible Movies/TV Shows layout.

This module scans a folder for video files, proposes renames using the
project's parser/core logic, and moves files into the Staged folder structure
or into Errors for manual review. It is non-interactive and intended to be
used by the CLI pipeline before transcoding.
"""
import shutil
import sys
from pathlib import Path

from tqdm import tqdm

from plex.rename import parser, core
from plex.utils import CONTENT_TYPE_TV, CONTENT_TYPE_MOVIES, VIDEO_EXTENSIONS


def rename_files(root_folder: Path, stage_root: Path, error_root: Path, dry_run=False):
    """Rename media files under `root_folder` into Plex Movies/TV Shows structure.

    The function:
    - Scans recursively for video files.
    - Uses filename parsing to detect TV episodes vs movies.
    - Builds a list of proposed renames and displays them.
    - Applies the renames unless `dry_run=True`.

    Args:
        root_folder (Path): Root directory to scan for video files.
        stage_root (Path): Destination root for renamable files (Staged).
        error_root (Path): Destination root for files requiring manual handling (Errors).
        dry_run (bool): If True, only show proposed renames without applying them.

    Returns:
        None

    Raises:
        SystemExit: When no files found or when running in dry-run mode (exits after printing).
    """
    root = Path(root_folder)
    if not root.exists() or not root.is_dir():
        print(f"❌ Folder {root} does not exist")
        return

    all_files = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS]
    proposed_renames: list[tuple[Path, Path]] = []

    def _route_file(rel_path: Path, is_renamable: bool, content_subdir: str, src_file: Path):
        """Determine target base (Staged/Errors) and append proposed rename.

        The provided `rel_path` is joined under either `stage_root` or
        `error_root` depending on `is_renamable`. If the source and target
        differ, the pair is added to `proposed_renames`.

        Args:
            rel_path (Path): Relative destination path computed by core.rename_*.
            is_renamable (bool): Whether the file is safe to place under output.
            content_subdir (str): Either CONTENT_TYPE_TV or CONTENT_TYPE_MOVIES.
            src_file (Path): Original source file path.

        Returns:
            None
        """
        base_dest = error_root if not is_renamable else stage_root
        target = (base_dest / content_subdir / rel_path).resolve()
        if src_file.resolve() != target:
            proposed_renames.append((src_file, target))

    for file in tqdm(all_files, desc="Analyzing files"):
        season, episode = parser.parse_tv_filename(file.stem)
        if season is not None or episode is not None:
            date_str, date_year = (None, None)
        else:
            date_str, date_year = parser.parse_date_in_filename(file.stem)

        is_tv = (season is not None) or (date_str is not None)

        if is_tv:
            res = core.rename_tv_file(file, season, episode, date_str=date_str, date_year=date_year)
            if res:
                new_path, matched, renamable = res
                _route_file(new_path, renamable, CONTENT_TYPE_TV, file)
        else:
            res = core.rename_movie_file(file)
            if res:
                new_path, matched, renamable = res
                _route_file(new_path, renamable, CONTENT_TYPE_MOVIES, file)

    if not proposed_renames:
        print("⚠️ No matching files found to rename.")
        sys.exit(0)

    print("\n📋 Proposed renames:")
    for old, new in proposed_renames:
        print(f"{old} → {new}")
    print(f"\nTotal files: {len(proposed_renames)}")

    if dry_run:
        print("\n🧪 Dry-run mode: no changes will be made.")
        sys.exit(0)

    for old, new in tqdm(proposed_renames, desc="Renaming files"):
        new.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(old), str(new))
        except Exception as e:
            print(f"❌ Failed to rename {old}: {e}")

    print("\n🎉 Finished renaming files.")
