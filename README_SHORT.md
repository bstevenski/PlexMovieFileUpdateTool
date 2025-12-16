# 🎬 Plex Media Tool — Quick Start

Non-interactive pipeline to rename and transcode media for Plex. Optimized for Apple devices with VideoToolbox.

---

## ✨ Highlights

- One-step: Rename → Transcode with a single command
- TMDb-powered naming and folder structure
- 4-thread transcoding, outputs `.mp4`
- `.mkv`, `.mp4`, `.avi`, `.mov` supported

---

## 🚀 Run it

```bash
brew install ffmpeg
export TMDB_API_KEY='your_api_key_here'

# Root contains Queue/Movies and Queue/TV Shows
python3 src/plexifier.py /path/to/Root
```

Defaults: non-interactive, background mode (unless `--debug`), 4 workers, overwrite outputs, delete staged sources on
success.

---

## 📁 Folders

```
Root/
├── Queue/
│   ├── Movies/
│   └── TV Shows/
├── Staged/
├── Completed/
└── Errors/
```

Cleanup: `Staged` is removed; strays in `Queue`/`Staged` moved to `Errors`; `Completed` and `Errors` untouched.

---

## 🧰 Tips

- Foreground + verbose: `--debug`
- Keep sources: `--debug-keep-source`
- Don’t overwrite: `--debug-no-overwrite`
- Preview only: `--debug-dry-run`
- HEVC skip flag is retained for compatibility but is a no-op; HEVC is processed.

---

MIT License © 2025
