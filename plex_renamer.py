#!/usr/bin/env python3
import os
import re
import argparse
import requests
import shutil
from pathlib import Path
from tqdm import tqdm

OMDB_API_KEY = os.getenv("OMDB_API_KEY")
if not OMDB_API_KEY:
    raise ValueError("OMDB_API_KEY environment variable is not set!")

SEASON_EPISODE_REGEX = re.compile(r"[Ss](\d{1,2})[Ee](\d{1,2})")
IMDB_ID_REGEX = re.compile(r"imdb-tt\d+")

VIDEO_EXTENSIONS = [".mkv", ".mp4", ".avi", ".mov"]
DEBUG = False


def sanitize_filename(name: str):
    invalid_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
    for char in invalid_chars:
        name = name.replace(char, '')
    return name.strip()


def search_omdb(title: str, type_: str, season: int = None, episode: int = None):
    """
    Search OMDb for a movie or TV episode.
    If season and episode are provided, returns episode data.
    """
    url = "http://www.omdbapi.com/"
    params = {
        "apikey": OMDB_API_KEY,
        "t": title,
        "type": type_
    }
    if type_ == "episode" and season is not None and episode is not None:
        params = {
            "apikey": OMDB_API_KEY,
            "t": title,
            "Season": season,
            "Episode": episode
        }

    resp = requests.get(url, params=params)
    if resp.status_code != 200:
        return None
    data = resp.json()
    if data.get("Response") == "False":
        return None
    return data


def parse_tv_filename(filename: str):
    match = SEASON_EPISODE_REGEX.search(filename)
    if match:
        season = int(match.group(1))
        episode = int(match.group(2))
        return season, episode
    return None, None


def clean_search_title(raw_title: str):
    """
    Remove empty segments or extra hyphens from filename for OMDb search
    """
    parts = [p.strip() for p in raw_title.replace(".", " ").split("-") if p.strip()]
    return " - ".join(parts)


def get_existing_imdb_id(file_path: Path):
    """
    Check if the file or its parent folder already has an IMDb ID
    """
    match = IMDB_ID_REGEX.search(file_path.name)
    if match:
        return match.group(0)  # return the string, not the match object
    match = IMDB_ID_REGEX.search(file_path.parent.name)
    if match:
        return match.group(0)
    return None


def rename_tv_file(file, season, episode):
    type_ = "series"
    # Use only series title for OMDb search
    search_title_series = file.stem
    search_title_series = re.split(SEASON_EPISODE_REGEX, search_title_series)[0]
    search_title_series = search_title_series.split(" - ")[0]  # remove anything after first dash
    search_title_series = re.sub(r"\(\d{4}\)", "", search_title_series)
    search_title_series = search_title_series.replace(".", " ").replace("_", " ").strip()
    search_title_series = re.sub(r"\s+", " ", search_title_series)

    if DEBUG:
        print(f"[DEBUG] Processing: {file}, type: {type_}, season search title: {search_title_series}, "
              f"season: {season}, episode: {episode}")

    # Get series data for IMDb ID and year
    series_data = search_omdb(search_title_series, type_)

    if not series_data or not series_data.get("imdbID"):
        if DEBUG:
            print(f"[DEBUG] No series match for {search_title_series}, skipping file")
        return

    series_imdb_id = series_data["imdbID"]
    series_year = series_data.get("Year", "Unknown")

    # Now get episode data for the episode title
    episode_data = search_omdb(search_title_series, "episode", season=season, episode=episode)
    if episode_data and episode_data.get("Title"):
        episode_title = sanitize_filename(episode_data["Title"])
    else:
        episode_title = file.stem  # fallback
    season_num = season or 1
    episode_num = episode or 1
    new_folder = file.parent / f"{search_title_series} ({series_year}) {{imdb-{series_imdb_id}}}" / f"Season {season_num:02d}"
    new_filename = f"{search_title_series} - s{season_num:02d}e{episode_num:02d} - {episode_title}{file.suffix}"
    return new_folder / new_filename


def rename_movie_file(file):
    type_ = 'movie'
    search_title = file.stem.replace(".", " ").strip()
    if DEBUG:
        print(f"[DEBUG] Processing: {file}, type: {type_}, search title: {search_title}")

    omdb_data = search_omdb(search_title, type_)

    if not omdb_data:
        if DEBUG:
            print(f"[DEBUG] No OMDb match for {search_title}")
        return

    imdb_id = omdb_data.get("imdbID")
    if not imdb_id:
        if DEBUG:
            print(f"[DEBUG] OMDb match found for {search_title} but no IMDb ID, skipping file")
        return

    title = sanitize_filename(omdb_data.get("Title", search_title))
    year = omdb_data.get("Year", "Unknown")

    new_folder = file.parent / f"{title} ({year}) {{imdb-{imdb_id}}}"
    new_filename = f"{title} ({year}){file.suffix}"
    return new_folder / new_filename


def rename_files(root_folder: Path, dry_run=False, confirm=True):
    root_folder = Path(root_folder)
    if not root_folder.exists():
        print(f"❌ Folder {root_folder} does not exist")
        return

    all_files = [f for f in root_folder.rglob("*") if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS]

    proposed_renames = []

    for file in tqdm(all_files, desc="Analyzing files"):
        existing_imdb_id = get_existing_imdb_id(file)
        if existing_imdb_id is not None:
            if DEBUG:
                print(f"[SKIP] Already has IMDb ID: {existing_imdb_id}")
            continue

        season, episode = parse_tv_filename(file.stem)
        is_tv = season is not None

        if is_tv:
            new_file_path = rename_tv_file(file, season, episode)
        else:
            new_file_path = rename_movie_file(file)

        if new_file_path:
            proposed_renames.append((file, new_file_path))

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

    print("\n🎉 Finished renaming files.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rename Movies and TV Episodes for Plex with IMDb IDs.")
    parser.add_argument("root", help="Root folder containing Movies/TV folders")
    parser.add_argument("--dry-run", action="store_true", help="Simulate renaming without changes")
    parser.add_argument("--no-confirm", action="store_true", help="Skip confirmation prompt")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    args = parser.parse_args()

    DEBUG = args.debug
    rename_files(
        root_folder=args.root,
        dry_run=args.dry_run,
        confirm=not args.no_confirm
    )
