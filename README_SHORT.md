# 🎬 Plex Media Pipeline

Automated tool to rename and transcode your Movies and TV Shows for Plex using the [TMDb API](https://www.themoviedb.org/). Optimized for Apple TV with hardware-accelerated HEVC transcoding.

---

## ✨ Features
- **One-step processing**: Rename + Transcode in a single command
- Auto-detects TV episodes (e.g., `S01E01`) and date-based episodes
- TMDb lookups add `{tmdb-12345}` to folders for accurate Plex matching
- Hardware-accelerated HEVC transcoding (Apple M1 VideoToolbox)
- Auto-detects 1080p vs 4K and HDR, adjusts settings accordingly
- Parallel processing for speed
- Supports `.mkv`, `.mp4`, `.avi`, `.mov`

---

## 🚀 Quick Start (macOS)
```bash
# Install dependencies
brew install ffmpeg
pip install requests tqdm

# Set TMDb API key (get free key from themoviedb.org)
export TMDB_API_KEY='your_api_key_here'

# Process files (rename + transcode in one step)
python3 plex_pipeline.py ./1.Rename --skip-hevc --delete-source
```

---

## 📂 Example Output
```
Movies/
  The Matrix (1999) {tmdb-603}/
    The Matrix (1999).mp4

TV Shows/
  Breaking Bad (2008-2013) {tmdb-1396}/
    Season 01/
      Breaking Bad - s01e01 - Pilot.mp4
```

---

## 📁 Folder Structure
```
1.Rename/      # Input: raw files
4.Upload/      # Output: ready for Plex
X.Issues/      # Files needing manual review
```

---

## 🔧 Alternative: Two-Step Workflow
```bash
# Step 1: Rename only
python3 plex_renamer.py ./1.Rename

# Step 2: Transcode only
python3 plex_transcoder.py --src ./2.Staged --out ./4.Upload --skip-hevc --delete-source
```

---

MIT License © 2025
