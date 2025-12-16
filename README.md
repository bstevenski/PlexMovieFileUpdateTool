# Plex Media Tool — Rename + Transcode Pipeline

Automated, non-interactive pipeline to rename and transcode media for Plex. Optimized for Apple devices (Apple TV,
iPhone, Mac) using VideoToolbox hardware acceleration.

## Overview

Single CLI `src/plexifier.py` orchestrates two phases:

- Phase 1 — Rename/Stage: Scan `Queue` and move files into `Staged` with Plex-friendly names and folders. Unrenamable
  files go to `Errors`.
- Phase 2 — Transcode: Read from `Staged`, transcode to MP4 (HEVC/AAC as needed), then move results to `Completed`.
  Failures go to `Errors`.
- Final cleanup — Remove `Staged` entirely, move any strays in `Staged`/`Queue` to `Errors`, and reset `Queue` to only
  `Movies` and `TV Shows` subfolders. `Completed` and `Errors` are left untouched.

The CLI is non-interactive and safe for background runs.

## Prerequisites

1. Python 3.9+
2. FFmpeg with VideoToolbox (macOS):
   ```bash
   brew install ffmpeg
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

## How it works (high level)

1. Rename & Stage (Queue → Staged/Errors)
    - Scans `Queue` recursively for supported video extensions
    - Infers Movies vs TV (season/date-based) using filename parsing
    - Queries TMDb where appropriate; formats names and folders
    - Moves renamable files into `Staged/[Movies|TV Shows]/...`
    - Sends ambiguous/unmatched files to `Errors` for manual review
2. Transcode (Staged → Completed)
    - 4-thread pool runs `plex.transcode.batch.transcode_one`
    - Outputs `.mp4`; may force audio to AAC for `.avi` inputs
    - On success: file is placed in `Completed` and staged source removed (unless debug keep)
    - On failure: staged source is moved to `Errors`
3. Cleanup
    - Move any strays from `Staged`/`Queue` to `Errors`
    - Remove `Staged` entirely; reset `Queue` to only the two subfolders

## Developer notes

- Folder names are centralized in `plex.utils.constants`:
  `QUEUE_FOLDER`, `STAGED_FOLDER`, `ERROR_FOLDER`, `COMPLETED_FOLDER`.
- Batch entrypoints used by the CLI:
    - `plex.rename.batch.rename_files(root, stage_root, error_root, dry_run)`
    - `plex.transcode.batch.iter_video_files(staged_root)`
    - `plex.transcode.batch.transcode_one(src, staged_root, completed_root, args)`
- No interactive prompts anywhere. Dry-run prints proposed renames and exits.

## License

MIT © 2025

**Other options:**

- `--dry-run` - Preview what would happen
- `--overwrite` - Overwrite existing outputs
- `--force-audio-aac` - Force AAC audio for all files
- `--no-subs` - Don't include subtitle streams
- `--debug` - Show detailed TMDb API info
- `--output-root` - Custom output folder (default: `4.Upload`)
- `--manual-root` - Custom issues folder (default: `X.Issues`)

#### Complete Workflow

```bash
# Single step: Process all files
python3 plex_pipeline.py ./1.Rename --skip-hevc --delete-source

# Upload to Plex
rsync -avh ./4.Upload/ /path/to/plex/media/

# Review any problem files
ls -la ./X.Issues/
```

---

### Option 2: Two-Step Workflow (Advanced)

If you prefer to separate renaming and transcoding:

#### Folder Structure

```
your-base-folder/
├── 1.Rename/          # Input: Place raw video files here
├── 2.Staged/          # Auto-created: Renamed files ready for transcoding
├── 4.Upload/          # Auto-created: Final transcoded files for Plex
└── X.Issues/          # Auto-created: Files that need manual review
```

#### Step 1: Rename Files

```bash
python3 plex_renamer.py ./1.Rename
```

**Options:**

- `--dry-run` - Preview changes without moving files
- `--debug` - Show detailed API search information
- `--no-confirm` - Skip confirmation prompt
- `--output-root` - Custom output folder (default: `2.Staged`)
- `--manual-root` - Custom issues folder (default: `X.Issues`)

#### Step 2: Transcode to HEVC

```bash
python3 plex_transcoder.py --src ./2.Staged --out ./4.Upload --skip-hevc --delete-source
```

**Recommended options:**

- `--skip-hevc` - Skip files already in HEVC (faster, recommended)
- `--delete-source` - Delete source after successful transcode
- `--workers 2` - Number of concurrent transcodes (default: 2)

**Other options:**

- `--dry-run` - Preview what would be transcoded
- `--overwrite` - Overwrite existing outputs
- `--only-avi` - Only process .avi files
- `--force-audio-aac` - Force AAC audio for all files
- `--no-subs` - Don't include subtitle streams

#### Step 3: Upload to Plex

```bash
rsync -avh --progress ./4.Upload/ /path/to/plex/media/
```

#### Complete Two-Step Workflow

```bash
# Step 1: Rename files
python3 plex_renamer.py ./1.Rename

# Step 2: Transcode to HEVC
python3 plex_transcoder.py --src ./2.Staged --out ./4.Upload --skip-hevc --delete-source

# Step 3: Upload to Plex
rsync -avh ./4.Upload/ /path/to/plex/media/

# Review any problem files
ls -la ./X.Issues/
```

---

## Transcoding Settings

### 1080p Content

- Codec: HEVC (H.265) Main profile
- Bitrate: 7 Mbps (target) / 9 Mbps (max)
- Container: MP4
- Audio: Copy original or AAC 192k (for AVI)

### 4K/HDR Content

- Codec: HEVC (H.265) Main10 profile
- Bitrate: 20 Mbps (target) / 25 Mbps (max)
- Pixel Format: p010le (10-bit for HDR)
- HDR: Preserved (BT.2020 color space)
- Container: MP4

## Plex Naming Convention

The scripts follow Plex's recommended naming:

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

### Files going to X.Issues folder

These files couldn't be automatically identified. Common reasons:

- Unclear filename
- Not in TMDb database
- Ambiguous search results

Manually rename these files or fix the filename and re-run.

### "ffmpeg not found"

Install ffmpeg:

```bash
brew install ffmpeg
```

### Transcode is slow

- Reduce `--workers` to 1
- Check Activity Monitor for CPU/GPU usage
- Ensure you're not running other intensive tasks

### Processing stopped early

Check for errors in the output. Common issues:

- Network timeout (TMDb API)
- Disk space
- Permission issues

## Version History

- **1.0.0** - Added unified pipeline script (plex_pipeline.py)
- **0.3.0** - Switched to TMDb API, removed OMDb/TVMaze dependencies
- **0.2.0** - Added convert folder workflow
- **0.1.0** - Initial release with OMDb/TVMaze

## License

MIT License - feel free to modify and use as needed.
