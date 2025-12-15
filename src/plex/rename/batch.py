# python
"""Batch rename utilities for Plex-compatible Movies/TV Shows layout.

This module scans a folder for video files, proposes renames using the
project's parser/core logic, performs the renames (optionally), and prunes
empty directories created by the operation.
"""
import os
import sys
import shutil
from pathlib import Path

from tqdm import tqdm

from plex import CONTENT_TYPE_TV, CONTENT_TYPE_MOVIES, DEBUG, VIDEO_EXTENSIONS
from plex.rename import parser, core
from plex.utils import file_util


def rename_files(root_folder: Path, dry_run=False, confirm=True, output_root: Path | None = None,
                 manual_root: Path | None = None):
    """Rename media files under `root_folder` into Movies/TV Shows output structure.

    The function:
    - Infers output/manual roots when not provided.
    - Scans recursively for video files.
    - Uses filename parsing to detect TV episodes vs movies.
    - Builds a list of proposed renames and displays them.
    - Optionally performs the renames after confirmation.
    - Prunes empty source directories created by the operation.

    Args:
        root_folder (Path): Root directory to scan for video files.
        dry_run (bool): If True, only show proposed renames without applying them.
        confirm (bool): If True, prompt the user before performing renames.
        output_root (Path | None): Destination root for renamable files. Inferred if None.
        manual_root (Path | None): Destination root for files requiring manual handling. Inferred if None.

    Returns:
        None

    Raises:
        SystemExit: When no files found or when running in dry-run mode (exits after printing).
    """
    root = Path(root_folder)
    if not root.exists() or not root.is_dir():
        print(f"❌ Folder {root} does not exist")
        return

    if output_root is None or manual_root is None:
        inferred_output, inferred_manual = file_util.infer_output_roots(root)
        output_root = output_root or inferred_output
        manual_root = manual_root or inferred_manual

    all_files = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS]
    proposed_renames: list[tuple[Path, Path]] = []

    def _route_file(rel_path: Path, is_renamable: bool, content_subdir: str, src_file: Path):
        """Determine target base (output/manual) and append proposed rename.

        The provided `rel_path` is joined under either the `output_root` or
        `manual_root` depending on `is_renamable`. If the source and target
        differ, the pair is added to `proposed_renames`.

        Args:
            rel_path (Path): Relative destination path computed by core.rename_*.
            is_renamable (bool): Whether the file is safe to place under output.
            content_subdir (str): Either CONTENT_TYPE_TV or CONTENT_TYPE_MOVIES.
            src_file (Path): Original source file path.

        Returns:
            None
        """
        base_dest = manual_root if not is_renamable else output_root
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

    if confirm:
        answer = input("\nProceed with all renames? (y/n): ").strip().lower()
        if answer != "y":
            print("❌ Rename canceled.")
            return

    for old, new in tqdm(proposed_renames, desc="Renaming files"):
        new.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(old), str(new))
        except Exception as e:
            print(f"❌ Failed to rename {old}: {e}")

    def _prune_empty_dirs(root_path: Path, output: Path, manual: Path) -> int:
        """Remove empty directories under `root_path`, excluding keep list.

        The function walks the tree bottom-up and removes directories that are
        empty, skipping a small set of important folders (root, Movies/TV Shows,
        and the corresponding output/manual roots).

        Args:
            root_path (Path): The original scanned root folder to prune.
            output (Path): The resolved output root used above.
            manual (Path): The resolved manual root used above.

        Returns:
            int: Number of directories removed.
        """
        removed = 0
        root_res = root_path.resolve()
        output_res = output.resolve()
        manual_res = manual.resolve()

        keep = {
            root_res,
            (root_res / "Movies").resolve(),
            (root_res / "TV Shows").resolve(),
            output_res,
            (output_res / "Movies").resolve(),
            (output_res / "TV Shows").resolve(),
            manual_res,
            (manual_res / "Movies").resolve(),
            (manual_res / "TV Shows").resolve(),
        }

        for dirpath, _, _ in os.walk(root_path, topdown=False):
            p = Path(dirpath).resolve()
            if p in keep:
                continue
            try:
                if not any(p.iterdir()):
                    p.rmdir()
                    removed += 1
                    if DEBUG:
                        print(f"[PRUNE] Removed empty folder: {p}")
            except Exception as err:
                if DEBUG:
                    print(f"[PRUNE] Skipped {p}: {err}")
        return removed

    pruned = _prune_empty_dirs(root, output_root, manual_root)
    if pruned:
        print(f"\n🧹 Removed {pruned} empty folder(s) from {root}")

    print("\n🎉 Finished renaming files.")
