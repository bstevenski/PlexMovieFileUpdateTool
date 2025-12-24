# Plex Media Tool — Rename + Transcode Pipeline

Automated, non-interactive pipeline to rename and transcode media for Plex. Optimized for Apple devices (Apple TV,
iPhone, Mac) using H.264 for maximum compatibility.

## Overview

Single CLI `src/plexifier/plexifier.py` orchestrates two phases:

- Phase 1 — Rename/Stage: Scan `Queue` and move files into `Staged` with Plex-friendly names and folders. Unrenamable
  files go to `Errors`.
- Phase 2 — Transcode: Read from `Staged`, transcode to MP4 (H.264/AAC), then move results to `Completed`.
  Failures go to `Errors`.
- Final cleanup — Remove `Staged` entirely, move any strays in `Staged`/`Queue` to `Errors`, and reset `Queue` to only
  `Movies` and `TV Shows` subfolders. `Completed` and `Errors` are left untouched.

The CLI is non-interactive and safe for background runs.

## Prerequisites

1. Python 3.10+
2. FFmpeg:
    - **macOS:**
      ```bash
      brew install ffmpeg
      ```
    - **Windows:**
      ```powershell
      choco install ffmpeg
      ```
3. TMDb API Key (free): set environment variable
   ```bash
   export TMDB_API_KEY="your_api_key_here"
   ```

## Installation

### Option 1: Install from source

```bash
git clone <repository-url>
cd plex-media-tool
pip install -e .
```

### Option 2: Run directly

```bash
git clone <repository-url>
cd plex-media-tool
pip install -r requirements.txt
```

## Folder structure

Your root folder will contain:

```
Root/
├── Queue/
│   ├── Movies/
│   └── TV Shows/
├── Staged/            # auto-created
├── Completed/         # auto-created
└── Errors/            # auto-created
```

Place your source files under `Queue/Movies` or `Queue/TV Shows`.

## Usage

### Option 1: Installed package

```bash
plexifier /path/to/media
```

### Option 2: Run directly

```bash
python3 src/plexifier/plexifier.py /path/to/media
```

### CLI flags

```
positional:
  source_dir            Source directory containing media files (default: ../ready-to-process)

optional:
  --dry-run             Preview changes without making modifications
  --skip-transcoding     Skip video transcoding step
  --log-level {DEBUG,INFO,WARN,ERROR}
                        Logging level (default: INFO)
  --workers WORKERS      Number of worker processes (default: 4)
```

### Development commands (using hatch)

```bash
hatch run standard-run    # Run plexifier in standard mode
hatch run debug-run       # Run plexifier in debug/dry-run mode
hatch run ps             # List running plexifier and ffmpeg processes
hatch run trail-log      # Tail the latest log file
hatch run kill           # Stop any running plexifier and ffmpeg processes
hatch run clean-all      # Full clean (Python cache + log files)
```

    - **Windows (software or GPU accel if available):**
      ```powershell
      choco install ffmpeg
      ```

3. TMDb API Key (free): set environment variable
   ```bash
   export TMDB_API_KEY="your_api_key_here"
   ```

## Folder structure

Your root folder will contain:

```
Root/
├── Queue/
│   ├── Movies/
│   └── TV Shows/
├── Staged/            # auto-created
├── Completed/         # auto-created
└── Errors/            # auto-created
```

Place your source files under `Queue/Movies` or `Queue/TV Shows`.

## Usage

Run from project root (or install as a script) and pass your media root:

```bash
python3 src/plexifier.py /path/to/Root
```

Behavior by default:

- Non-interactive (no prompts)
- Uses 4 worker threads for transcoding
- Deletes staged source after successful transcode unless `--debug-keep-source`
- Overwrites existing outputs unless `--debug-no-overwrite`
- Honors `--debug-dry-run` for a preview-only run

### CLI flags

```
positional:
  root                  Root directory containing Queue and where Staged/Completed/Errors live

optional:
  --log-dir DIR         Directory for log files (default: ./logs)
  --encoder ENCODER     FFmpeg encoder to use (e.g., hevc_videotoolbox, hevc_nvenc, libx265). Defaults to the best
                        available encoder for your OS.
  --debug               Foreground mode + verbose logging
  --debug-keep-source   Keep source files after processing (no delete)
  --debug-no-overwrite  Do not overwrite existing outputs
  --debug-dry-run       Preview actions without moving/transcoding
  --no-skip-hevc        (Kept for compatibility; currently no-op — HEVC is processed)
  --version             Show version and exit
```

Notes:

- The previous `--only-avi` option has been removed.
- HEVC skipping has been disabled by design; all files in `Queue` are treated as needing processing. The
  `--no-skip-hevc` flag is retained only for CLI compatibility.
- Encoder selection is automatic: macOS prefers VideoToolbox, Windows tries GPU encoders (NVENC/Quick Sync/AMF)
  when present, and any platform can fall back to software `libx265`. Use `--encoder` to force a specific
  ffmpeg encoder if desired.

### Background mode

- Default: If you do not pass `--debug`, `plexifier.py` relaunches itself in the background and writes logs to
  `./logs/plexifier-YYYYMMDD-HHMMSS.log`.
- Foreground: Use `--debug` to run in the foreground with detailed logs.

If you use the provided Makefile, handy commands:

```bash
make logs   # tail the latest log
make ps     # show running plexifier processes
make kill   # kill running plexifier processes
```

## How it works

1. **Rename & Stage** (Queue → Staged/Errors)
    - Scans `Queue` recursively for supported video extensions
    - Infers Movies vs TV (season/date-based) using filename parsing
    - Queries TMDb API for metadata; formats names and folders according to Plex conventions
    - Moves renamable files into `Staged/[Movies|TV Shows]/...`
    - Sends ambiguous/unmatched files to `Errors` for manual review

2. **Handle Problematic Shows** (Manual Intervention)
    - Some TV shows may have incorrect episode numbering but correct titles in filenames
    - These files typically get sent to `Errors` folder during standard processing
    - **Solution**: Process these problematic shows separately after main run:
      ```bash
      # Manually rename files to correct format and re-run only on specific folder
      python3 src/plexifier/plexifier.py /path/to/Errors/TV\ Shows --dry-run
      ```

3. **Transcode** (Staged → Completed)
    - Converts videos to MP4 format using H.264/AAC for maximum device compatibility
    - Only transcodes files that are not already in compatible format
    - On success: file is placed in `Completed` and staged source is removed
    - On failure: staged source is moved to `Errors`

4. **Cleanup**
    - Move any strays from `Staged`/`Queue` to `Errors`
    - Reset `Queue` to only `Movies` and `TV Shows` subfolders

## Transcoding Settings

All content is transcoded to ensure maximum compatibility:

- **Video Codec**: H.264 (libx264)
- **Audio Codec**: AAC
- **Preset**: Medium (balanced speed/quality)
- **CRF**: 23 (good quality at reasonable file size)
- **Audio Bitrate**: 128k
- **Audio Channels**: Maximum 2 (stereo)
- **Container**: MP4

## Plex Naming Convention

The tool follows Plex's recommended naming:

**Movies:**

```
Movies/
  Movie Title (2024) {tmdb-12345}/
    Movie Title (2024).mp4
```

**TV Shows:**

```
TV Shows/
  Show Name (2020-2024) {tmdb-67890}/
    Season 01/
      Show Name - s01e01 - Episode Title.mp4
      Show Name - s01e02 - Episode Title.mp4
```

## Troubleshooting

### "TMDB_API_KEY environment variable is not set!"

Make sure you've exported your TMDb API key:

```bash
export TMDB_API_KEY="your_key_here"
```

### Files going to Errors folder

These files couldn't be automatically identified. Common reasons:

- Unclear filename
- Not in TMDb database
- Ambiguous search results

Manually rename these files or fix filename and re-run.

### "ffmpeg not found"

Install ffmpeg:

```bash
brew install ffmpeg  # macOS
choco install ffmpeg  # Windows
```

### Processing stopped early

Check logs in `.logs/` directory. Common issues:

- Network timeout (TMDb API)
- Disk space
- Permission issues

## Development

### Project Structure

```
src/plexifier/
├── __init__.py              # Package initialization and public API
├── plexifier.py            # Main CLI entry point
└── utils/
    ├── __init__.py
    ├── constants.py         # Configuration constants
    ├── file_manager.py      # File operations
    ├── formatter.py         # Plex naming conventions
    ├── logger.py            # Logging setup
    ├── parser.py            # Filename parsing
    ├── tmdb_client.py       # TMDb API integration
    └── transcoder.py        # Video transcoding
```

### Testing

```bash
pytest tests/ --cov=plexifier --cov-report=term-missing
```

### Code Quality

```bash
ruff check src/           # Linting
black src/                # Formatting
```

## License

MIT License - feel free to modify and use as needed.
