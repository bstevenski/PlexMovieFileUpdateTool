#!/usr/bin/env python3
import argparse
import os
import shutil
from pathlib import Path

from tqdm import tqdm

# Import all shared functionality from common module
import plex_common
from plex_common import (
    VIDEO_EXTENSIONS,
    parse_tv_filename,
    parse_date_in_filename,
    infer_output_roots,
    rename_tv_file,
    rename_movie_file,
)

__version__ = "0.3.0"


# noinspection DuplicatedCode
def rename_files(root_folder: Path, dry_run=False, confirm=True, output_root: Path | None = None,
                 manual_root: Path | None = None):
    root_folder = Path(root_folder)
    if not root_folder.exists():
        print(f"❌ Folder {root_folder} does not exist")
        return

    # Infer default destinations if not specified
    if output_root is None or manual_root is None:
        inferred_output, inferred_manual = infer_output_roots(root_folder)
        output_root = output_root or inferred_output
        manual_root = manual_root or inferred_manual

    all_files = [f for f in root_folder.rglob("*") if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS]

    proposed_renames = []

    def _route_file(rel_path, is_renamable, content_subdir, src_file):
        """Route file to appropriate destination based on renamability."""
        base_dest = manual_root if not is_renamable else output_root
        target = (base_dest / content_subdir / rel_path).resolve()
        # Only propose rename if the target is different from the source
        if src_file.resolve() != target:
            proposed_renames.append((src_file, target))

    for file in tqdm(all_files, desc="Analyzing files"):
        season, episode = parse_tv_filename(file.stem)
        date_str, date_year = (None, None) if (season is not None) else parse_date_in_filename(file.stem)
        is_tv = (season is not None) or (date_str is not None)

        if is_tv:
            result = rename_tv_file(file, season, episode, date_str=date_str, date_year=date_year)
            if result:
                new_file_path, matched, renamable = result
                _route_file(new_file_path, renamable, 'TV Shows', file)
        else:
            result = rename_movie_file(file)
            if result:
                new_file_path, matched, renamable = result
                _route_file(new_file_path, renamable, 'Movies', file)

    if not proposed_renames:
        print("⚠️ No matching files found to rename.")
        return

    print("\n📋 Proposed renames:")
    for old, new in proposed_renames:
        print(f"{old} → {new}")
    print(f"\nTotal files: {len(proposed_renames)}")

    if dry_run:
        print("\n🧪 Dry-run mode: no changes will be made.")
        return

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

    # After moving files, prune any empty folders left under the source root
    # noinspection DuplicatedCode
    def _prune_empty_dirs(root: Path, output: Path, manual: Path):
        removed = 0
        root_resolved = root.resolve()
        output_resolved = output.resolve()
        manual_resolved = manual.resolve()

        # Keep these special folders even if empty
        keep_folders = {
            # Source folder structure
            root_resolved,
            (root_resolved / "Movies").resolve(),
            (root_resolved / "TV Shows").resolve(),
            # Output folder structure
            output_resolved,
            (output_resolved / "Movies").resolve(),
            (output_resolved / "TV Shows").resolve(),
            # Issues folder structure
            manual_resolved,
            (manual_resolved / "Movies").resolve(),
            (manual_resolved / "TV Shows").resolve(),
        }
        # Walk bottom-up so children are pruned before parents
        for dirpath, dir_names, file_names in os.walk(root, topdown=False):
            p = Path(dirpath).resolve()
            # Keep the root folder and Movies/TV Shows subfolders even if empty
            if p in keep_folders:
                continue
            try:
                # If the directory is empty now, remove it
                if not any(p.iterdir()):
                    p.rmdir()
                    removed += 1
                    if plex_common.DEBUG:
                        print(f"[PRUNE] Removed empty folder: {p}")
            except Exception as err:
                if plex_common.DEBUG:
                    print(f"[PRUNE] Skipped {p}: {err}")
        return removed

    pruned = _prune_empty_dirs(root_folder, output_root, manual_root)
    if pruned:
        print(f"\n🧹 Removed {pruned} empty folder(s) from {root_folder}")

    print("\n🎉 Finished renaming files.")


if __name__ == "__main__":
    # noinspection DuplicatedCode
    parser = argparse.ArgumentParser(description="Rename Movies and TV Episodes for Plex with IMDb IDs.")
    parser.add_argument("root", help="Root folder containing Movies/TV folders")
    parser.add_argument("--dry-run", action="store_true", help="Simulate renaming without changes")
    parser.add_argument("--no-confirm", action="store_true", help="Skip confirmation prompt")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--output-root",
                        help="Root output folder for renamed files ready for transcoding (will create 'Movies' and 'TV Shows' inside). Defaults to '2.Staged'")
    parser.add_argument("--manual-root",
                        help="Root output folder for items that cannot be safely renamed (will create 'Movies' and 'TV Shows' inside). Defaults to 'X.Issues'")
    args = parser.parse_args()

    plex_common.DEBUG = args.debug
    rename_files(
        root_folder=args.root,
        dry_run=args.dry_run,
        confirm=not args.no_confirm,
        output_root=Path(args.output_root) if args.output_root else None,
        manual_root=Path(args.manual_root) if args.manual_root else None,
    )
