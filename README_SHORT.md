# 🎬 Plex Renamer

A simple Python tool that organizes and renames your Movies and TV Shows for Plex using the [OMDb API](https://www.omdbapi.com/).

---

## ✨ Features
- Auto-detects TV episodes (e.g., `S01E01`).
- Fetches IMDb IDs and metadata.
- Organizes files into clean Plex folders.
- Supports `--dry-run`, `--no-confirm`, and `--debug` modes.
- Works with `.mkv`, `.mp4`, `.avi`, `.mov`.

---

## 🚀 Quick Start
```bash
pip install requests tqdm
export OMDB_API_KEY=your_api_key_here
./plex_renamer.py ~/Movies --dry-run
```

---

## 📂 Example Output
```
/Movies
  The Matrix (1999) {imdb-tt0133093}/
    The Matrix (1999).mkv

/TV Shows
  Breaking Bad (2008) {imdb-tt0903747}/
    Season 01/
      Breaking Bad - s01e01 - Pilot.mkv
```

---

MIT License © 2025
