# 🎬 Plex Movie & TV Renamer (OMDb‑Powered)

A small Python utility that renames movie and TV episode files into a Plex‑friendly structure using metadata from the OMDb API. It can detect TV episodes (`S01E02`), fetch IMDb IDs, and organize files into clean folders. Windows PowerShell examples are provided below; adapt commands for your OS as needed.

---

## Stack and Entry Points

- Language: Python (tested with 3.13; expected to work on 3.9+)
- Runtime OS: Developed and tested on Windows (PowerShell); should be portable
- Dependencies (runtime):
  - requests (HTTP to OMDb)
  - tqdm (progress bar)
- Package manager: none (install deps with pip if desired)
- Entry point: `plex_renamer.py` (CLI script)
- Scripts: none defined (use `python .\plex_renamer.py ...`)

---

## ✨ Features

- Automatic detection of TV episodes from filenames like `Show.Name.S02E03.mkv`
- OMDb lookup for movies and TV series/episodes
- Adds IMDb IDs to target folders for unambiguous identification when a match is found
- Automatic routing of files:
  - Matched items (with IMDb ID) go to your Upload area
  - Unmatched but renamable items:
    - If the file is .mkv → Upload area (keeps your MKVs ready for Plex)
    - If the file is NOT .mkv → Convert area (to be transcoded first)
  - Not renamable (no reliable metadata and no safe fallback title) → Manual Check area
- After real moves, automatically prunes now-empty directories left under the source root (keeps the top-level root)
- Organized output structure, for example:
  ```
  Movies/
    The Matrix (1999) {imdb-tt0133093}/
      The Matrix (1999).mkv

  TV Shows/
    Breaking Bad (2008) {imdb-tt0903747}/
      Season 01/
        Breaking Bad - s01e01 - Pilot.mkv
  ```
- Dry‑run mode to preview changes
- Progress bar with tqdm

---

## Requirements

- Python 3.9+ (tested with 3.13)
- OMDb API key (free/paid): https://www.omdbapi.com/apikey.aspx
- Optional: `pip install requests tqdm` if you want real network calls and progress bars outside of tests

Important: This module reads `OMDB_API_KEY` at import time. Importing `plex_renamer.py` without this variable set will raise `ValueError` immediately.

---

## Setup

1) Obtain an OMDb API key.

2) Set the environment variable before running or importing the module.
- PowerShell:
  ```powershell
  $env:OMDB_API_KEY = 'your-key'
  ```
- CMD:
  ```cmd
  set OMDB_API_KEY=your-key
  ```
- Bash:
  ```bash
  export OMDB_API_KEY=your-key
  ```

1) (Optional) Install optional dependencies:
```powershell
python -m pip install requests tqdm
```

---

## Usage (CLI)

Basic form:
```powershell
python .\plex_renamer.py "C:\\path\\to\\media" [--dry-run] [--no-confirm] [--debug] [--upload-root PATH] [--convert-root PATH] [--manual-root PATH]
```

Examples:
```powershell
# Preview proposed renames without changing files
python .\plex_renamer.py "C:\\Media" --dry-run

# Confirmed run (asks before changing unless --no-confirm)
python .\plex_renamer.py "C:\\Media"

# Skip confirmation and enable debug logging
python .\plex_renamer.py "C:\\Media" --no-confirm --debug

# Explicitly provide output roots (script creates Movies/TV Shows subfolders under each)
python .\plex_renamer.py "C:\\Media\\Plex Media\\1.Rename" --upload-root "C:\\Media\\Plex Media\\3.Upload" --convert-root "C:\\Media\\Plex Media\\2.Convert" --manual-root "C:\\Media\\Plex Media\\1.Manual Check"
```

CLI options (from `argparse`):
- `root` (positional): root folder to scan for media
- `--dry-run`: simulate renaming without making changes
- `--no-confirm`: skip confirmation prompt
- `--debug`: enable verbose debug output
- `--upload-root`: root folder for matched items (IMDb‑identified) and unmatched `.mkv` files that were safely renamed. The script writes into `Movies/` and `TV Shows/` under this root.
- `--convert-root`: root folder for unmatched, safely‑renamed non‑`.mkv` items (to be transcoded). The script writes into `Movies/` and `TV Shows/` under this root.
- `--manual-root`: root folder for items that cannot be safely renamed (no reliable metadata and no usable fallback). The script writes into `Movies/` and `TV Shows/` under this root.

Notes:
- Supported extensions: `.mkv`, `.mp4`, `.avi`, `.mov`
- Files/folders that already contain an IMDb ID pattern like `{imdb-tt1234567}` are skipped
- If your source path looks like `...\Plex Media\1.Rename`, the script will automatically infer sibling destinations `...\Plex Media\1.Manual Check`, `...\Plex Media\2.Convert`, and `...\Plex Media\3.Upload` unless you pass the flags.
- In non-dry runs, after files are moved, the tool removes empty directories under the provided `root` to keep your staging area tidy (with `--debug`, it logs each pruned folder).

---

## How it works (high‑level)

1) Recursively scans the given root for supported video files.
2) Skips items already containing an IMDb ID.
3) Detects TV episodes by `SxxExx` pattern; others are treated as movies.
4) Queries OMDb for title/year/IMDb ID (and episode title for TV when available).
5) If OMDb match exists, includes `{imdb-tt...}` in the folder name and routes to Upload. If no match, generates Plex‑style names from the filename (fallback) and routes as follows: `.mkv` → Upload; non‑`.mkv` → Convert; if no safe fallback title can be determined → Manual Check.
6) Prints a list of proposed renames/moves. In non‑dry runs, it moves files to the new structure and prunes now-empty directories under the source root.

---

## Environment variables

- `OMDB_API_KEY` (required at import): your OMDb API key.

If this variable is missing, importing or running `plex_renamer.py` will fail immediately with `ValueError`.

---

## Project structure

```
.
├─ README.md               # This file
├─ README_SHORT.md         # Shortened overview (see this for a quick summary)
└─ plex_renamer.py         # Main CLI and implementation
```

---

## Scripts

There are no packaged scripts in this repo. Use the CLI directly via Python:
```powershell
python .\plex_renamer.py "C:\\path\\to\\media" --dry-run
```

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## Additional notes

- The code imports `requests` and `tqdm`. If you don’t want to install them for testing, mock them as shown above.
- Consider starting with `--dry-run` on a small subset of files before pointing at your full library.
- Potential future improvements are listed in `.junie/guidelines.md` (e.g., deferring API key read until use, adding a network wrapper, formal test suite).
