#!/usr/bin/env python3
import argparse
import os
import re
import shutil
from pathlib import Path

import requests
from tqdm import tqdm

__version__ = "0.2.0"

OMDB_API_KEY = os.getenv("OMDB_API_KEY")
if not OMDB_API_KEY:
    raise ValueError("OMDB_API_KEY environment variable is not set!")

SEASON_EPISODE_REGEX = re.compile(r"[Ss](\d{1,2})[Ee](\d{1,2})")
IMDB_ID_REGEX = re.compile(r"imdb-tt\d+")
# Date-based episode patterns: 2025-12-03, 2025.12.03, 2025_12_03, 2025 12 03
DATE_REGEXES = [
    re.compile(r"(20\d{2}|19\d{2})[-_. ](0[1-9]|1[0-2])[-_. ](0[1-9]|[12]\d|3[01])"),
]

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
    # Use HTTPS for OMDb API endpoint
    url = "https://www.omdbapi.com/"
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


def parse_date_in_filename(filename: str):
    """
    Find a date token in the filename and normalize to YYYY-MM-DD for Plex date-based shows.
    Returns (date_str, year_int) or (None, None)
    """
    for rx in DATE_REGEXES:
        m = rx.search(filename)
        if m:
            y, mo, d = m.group(1), m.group(2), m.group(3)
            return f"{y}-{mo}-{d}", int(y)
    return None, None


def _guess_title_and_year_from_stem(stem: str):
    """
    Best-effort extraction of a human title and a (possible) year from a noisy filename stem.
    Examples:
      "Movie.Title.2024.2160p.WEB-DL" -> ("Movie Title", "2024")
      "Intervention.S01E05.720p" -> ("Intervention", None)
    """
    # Remove common tech tags
    s = stem
    # Keep season/episode for TV detection elsewhere, here we just want a base title + maybe year
    # Replace separators with spaces
    s = s.replace("_", " ").replace(".", " ")
    # Collapse multiple spaces
    s = re.sub(r"\s+", " ", s).strip()

    # Attempt to pick a year (prefer the last 4-digit token between 1900-2099)
    year = None
    year_match = None
    for m in re.finditer(r"(19|20)\d{2}", s):
        year_match = m
    if year_match:
        year = year_match.group(0)
        title_part = s[:year_match.start()].strip()
    else:
        # Try parentheses style: Title (2024)
        m = re.search(r"\((19|20)\d{2}\)", s)
        if m:
            year = re.search(r"(19|20)\d{2}", m.group(0)).group(0)
            title_part = s[:m.start()].strip()
        else:
            title_part = s

    # Remove leftover common tags like resolution/encoders at the end
    title_part = re.sub(
        r"\b(480p|720p|1080p|2160p|4k|hdr|hdr10\+?|dv|web[- ]?dl|bluray|webrip|x264|x265|h\.264|h\.265|ddp?\d?\.?\d?|atmos|remux)\b",
        "", title_part, flags=re.IGNORECASE)
    title_part = re.sub(r"\s+", " ", title_part).strip(" -_")
    # Title case lightly (don’t shout)
    if title_part.isupper():
        title_part = title_part.title()
    return title_part.strip(), year


def clean_search_title(raw_title: str):
    """
    Remove empty segments or extra hyphens from the filename for OMDb search
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


def rename_tv_file(file, season, episode, date_str: str | None = None, date_year: int | None = None):
    type_ = "series"
    # Use only series title for OMDb search
    search_title_series = file.stem
    # Strip season/episode and date parts from the search title
    search_title_series = re.split(SEASON_EPISODE_REGEX, search_title_series)[0]
    search_title_series = search_title_series.split(" - ")[0]  # remove anything after first dash
    search_title_series = re.sub(r"\(\d{4}\)", "", search_title_series)
    # remove matched date token text if present
    if date_str:
        # permissive removal: replace non-digit separators variants
        ds = date_str.replace('-', '[\\-_. ]')
        try:
            search_title_series = re.sub(ds, '', search_title_series)
        except re.error:
            pass
    search_title_series = search_title_series.replace(".", " ").replace("_", " ").strip()
    search_title_series = re.sub(r"\s+", " ", search_title_series)

    if DEBUG:
        print(f"[DEBUG] Processing: {file}, type: {type_}, season search title: {search_title_series}, "
              f"season: {season}, episode: {episode}")

    # Get series data for IMDb ID and year
    series_data = search_omdb(search_title_series, type_)

    matched = True
    if not series_data or not series_data.get("imdbID"):
        matched = False
        # Fallback: build names without IMDb and without authoritative year
        base_title, series_year = _guess_title_and_year_from_stem(search_title_series)
        # Determine if we can safely rename
        renamable = bool(base_title) and len(base_title.strip()) >= 2
        if not renamable:
            return Path(file.name), False, False
        if date_str:
            # Date-based fallback
            folder = f"{base_title}"
            # prefer series folder year from series_year if we guessed one, else from date year
            folder_year = series_year or (str(date_year) if date_year else None)
            if folder_year:
                folder = f"{base_title} ({folder_year})"
            new_folder = Path(folder) / f"Season {date_year or '01'}"
            episode_title = date_str
            new_filename = f"{base_title} - {episode_title}{file.suffix}"
        else:
            season_num = season or 1
            episode_num = episode or 1
            token = f"s{season_num:02d}e{episode_num:02d}"
            episode_title = token
            folder = f"{base_title}"
            if series_year:
                folder = f"{base_title} ({series_year})"
            new_folder = Path(folder) / f"Season {season_num:02d}"
            # Avoid duplicating the token in filename (e.g., '... - s01e01 - s01e01')
            if episode_title.strip().lower() == token.lower():
                new_filename = f"{base_title} - {token}{file.suffix}"
            else:
                new_filename = f"{base_title} - {token} - {episode_title}{file.suffix}"
        return new_folder / new_filename, matched, True

    series_imdb_id = series_data["imdbID"]
    series_year = series_data.get("Year", "Unknown")

    # Now get episode data for the episode title
    # Determine episode title, if available
    season_num = season or 1
    episode_num = episode or 1
    if date_str is None:
        _ep = search_omdb(search_title_series, "episode", season=season, episode=episode)
        if _ep and _ep.get("Title"):
            episode_title = sanitize_filename(_ep["Title"])
        else:
            episode_title = f"s{season_num:02d}e{episode_num:02d}"
        series_title_clean = sanitize_filename(search_title_series)
        new_folder = Path(
            f"{series_title_clean} ({series_year}) {{imdb-{series_imdb_id}}}") / f"Season {season_num:02d}"
        token = f"s{season_num:02d}e{episode_num:02d}"
        # Avoid duplicating the token in filename
        if (episode_title or '').strip().lower() == token.lower():
            new_filename = f"{series_title_clean} - {token}{file.suffix}"
        else:
            new_filename = f"{series_title_clean} - {token} - {episode_title}{file.suffix}"
    else:
        # Date-based episode: use date as the key; put in Season YYYY
        series_title_clean = sanitize_filename(search_title_series)
        new_folder = Path(
            f"{series_title_clean} ({series_year}) {{imdb-{series_imdb_id}}}") / f"Season {date_year or '01'}"
        # No reliable OMDb episode lookup by date here; keep date in filename
        episode_title = date_str
        new_filename = f"{series_title_clean} - {episode_title}{file.suffix}"
    return new_folder / new_filename, matched, True


def rename_movie_file(file):
    type_ = 'movie'
    search_title = file.stem.replace(".", " ").strip()
    if DEBUG:
        print(f"[DEBUG] Processing: {file}, type: {type_}, search title: {search_title}")

    omdb_data = search_omdb(search_title, type_)

    if not omdb_data:
        # Fallback naming: try to guess title and year from stem
        base_title, year = _guess_title_and_year_from_stem(file.stem)
        title = sanitize_filename(base_title or search_title)
        # Determine if we have enough to safely rename
        renamable = bool(title) and len(title) >= 2
        if not renamable:
            # Caller will route to Manual Check; keep the original filename
            return Path(file.name), False, False
        folder = f"{title}"
        if year:
            folder = f"{title} ({year})"
        new_folder = Path(folder)
        new_filename = f"{title}"
        if year:
            new_filename = f"{title} ({year})"
        new_filename = f"{new_filename}{file.suffix}"
        return new_folder / new_filename, False, True

    imdb_id = omdb_data.get("imdbID")
    if not imdb_id:
        # Treat as unmatched – still use OMDb title/year if present
        title = sanitize_filename(omdb_data.get("Title", search_title))
        renamable = bool(title) and len(title) >= 2
        if not renamable:
            return Path(file.name), False, False
        year = omdb_data.get("Year")
        folder = f"{title}"
        if year:
            folder = f"{title} ({year})"
        new_folder = Path(folder)
        new_filename = f"{title}"
        if year:
            new_filename = f"{title} ({year})"
        return new_folder / f"{new_filename}{file.suffix}", False, True

    title = sanitize_filename(omdb_data.get("Title", search_title))
    year = omdb_data.get("Year", "Unknown")

    new_folder = Path(f"{title} ({year}) {{imdb-{imdb_id}}}")
    new_filename = f"{title} ({year}){file.suffix}"
    return new_folder / new_filename, True, True


def rename_files(root_folder: Path, dry_run=False, confirm=True, upload_root: Path | None = None,
                 convert_root: Path | None = None, manual_root: Path | None = None):
    root_folder = Path(root_folder)
    if not root_folder.exists():
        print(f"❌ Folder {root_folder} does not exist")
        return

    # Infer default destinations if not specified
    def _infer_roots(src: Path):
        parts = [p.lower() for p in src.parts]
        if 'plex media' in parts and '1.rename' in parts:
            # assume .../Plex Media/1.Rename
            try:
                ix_pm = parts.index('plex media')
                base = Path(*src.parts[:ix_pm + 1])
            except ValueError:
                base = src.parent
        else:
            base = src
        up = base / '3.Upload'
        cv = base / '2.Convert'
        mc = base / '1.Manual Check'
        return up, cv, mc

    if upload_root is None or convert_root is None or manual_root is None:
        inferred_upload, inferred_convert, inferred_manual = _infer_roots(root_folder)
        upload_root = upload_root or inferred_upload
        convert_root = convert_root or inferred_convert
        manual_root = manual_root or inferred_manual

    all_files = [f for f in root_folder.rglob("*") if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS]

    proposed_renames = []

    for file in tqdm(all_files, desc="Analyzing files"):
        # Defaults to satisfy static analyzers; will be set when a result is produced
        new_file_path = None
        base_dest = None
        subdir = None
        existing_imdb_id = get_existing_imdb_id(file)
        if existing_imdb_id is not None:
            if DEBUG:
                print(f"[SKIP] Already has IMDb ID: {existing_imdb_id}")
            continue

        season, episode = parse_tv_filename(file.stem)
        date_str, date_year = (None, None) if (season is not None) else parse_date_in_filename(file.stem)
        is_tv = (season is not None) or (date_str is not None)

        if is_tv:
            result = rename_tv_file(file, season, episode, date_str=date_str, date_year=date_year)
            if result:
                new_file_path, matched, renamable = result
                subdir = 'TV Shows'
                if matched:
                    base_dest = upload_root
                else:
                    if not renamable:
                        base_dest = manual_root
                    else:
                        # Unmatched but renamable: route by extension
                        base_dest = convert_root if file.suffix.lower() != '.mkv' else upload_root
        else:
            result = rename_movie_file(file)
            if result:
                new_file_path, matched, renamable = result
                subdir = 'Movies'
                if matched:
                    base_dest = upload_root
                else:
                    if not renamable:
                        base_dest = manual_root
                    else:
                        base_dest = convert_root if file.suffix.lower() != '.mkv' else upload_root

        if result and new_file_path is not None and base_dest is not None and subdir is not None:
            # new_file_path is relative (folder/name). Place under the appropriate base/subdir.
            target = (base_dest / subdir / new_file_path).resolve()
            proposed_renames.append((file, target))

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
    def _prune_empty_dirs(root: Path):
        removed = 0
        # Walk bottom-up so children are pruned before parents
        for dirpath, dir_names, file_names in os.walk(root, topdown=False):
            p = Path(dirpath)
            # Keep the top-level root folder even if empty
            if p.resolve() == root.resolve():
                continue
            try:
                # If directory is empty now, remove it
                if not any(p.iterdir()):
                    p.rmdir()
                    removed += 1
                    if DEBUG:
                        print(f"[PRUNE] Removed empty folder: {p}")
            except Exception as err:
                if DEBUG:
                    print(f"[PRUNE] Skipped {p}: {err}")
        return removed

    pruned = _prune_empty_dirs(root_folder)
    if pruned:
        print(f"\n🧹 Removed {pruned} empty folder(s) from {root_folder}")

    print("\n🎉 Finished renaming files.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rename Movies and TV Episodes for Plex with IMDb IDs.")
    parser.add_argument("root", help="Root folder containing Movies/TV folders")
    parser.add_argument("--dry-run", action="store_true", help="Simulate renaming without changes")
    parser.add_argument("--no-confirm", action="store_true", help="Skip confirmation prompt")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--upload-root",
                        help="Root output folder for matched items (will create 'Movies' and 'TV Shows' inside)")
    parser.add_argument("--convert-root",
                        help="Root output folder for non-.mkv unmatched items (will create 'Movies' and 'TV Shows' inside)")
    parser.add_argument("--manual-root",
                        help="Root output folder for items that cannot be safely renamed (will create 'Movies' and 'TV Shows' inside)")
    args = parser.parse_args()

    DEBUG = args.debug
    rename_files(
        root_folder=args.root,
        dry_run=args.dry_run,
        confirm=not args.no_confirm,
        upload_root=Path(args.upload_root) if args.upload_root else None,
        convert_root=Path(args.convert_root) if args.convert_root else None,
        manual_root=Path(args.manual_root) if args.manual_root else None,
    )
