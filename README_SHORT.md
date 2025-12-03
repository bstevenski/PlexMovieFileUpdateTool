# 🎬 Plex Renamer

A simple Python tool that organizes and renames your Movies and TV Shows for Plex using the [OMDb API](https://www.omdbapi.com/). It reads the `OMDB_API_KEY` at import time.

---

## ✨ Features
- Auto-detects TV episodes (e.g., `S01E01`) and date-based episodes.
- OMDb lookups add `{imdb-tt…}` to matched folders.
- Routing after rename:
  - Matched items → Upload
  - Unmatched but renamable: `.mkv` → Upload, non-`.mkv` → Convert
  - Not renamable → Manual Check
- Removes empty folders from the source tree after a real run.
- Supports `--dry-run`, `--no-confirm`, and `--debug` modes.
- Works with `.mkv`, `.mp4`, `.avi`, `.mov`.

---

## 🚀 Quick Start (Windows PowerShell)
```powershell
python -m pip install requests tqdm
$env:OMDB_API_KEY = 'your_api_key_here'
python .\plex_renamer.py "C:\\path\\to\\Plex Media\\1.Rename" --dry-run
```

---

## 📂 Example Output
```
Movies
  The Matrix (1999) {imdb-tt0133093}/
    The Matrix (1999).mkv

TV Shows
  Breaking Bad (2008) {imdb-tt0903747}/
    Season 01/
      Breaking Bad - s01e01 - Pilot.mkv
```

---

MIT License © 2025
