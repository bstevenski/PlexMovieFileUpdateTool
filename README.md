# Plex Media Renamer & Transcoder

Automated pipeline to rename and transcode media files for Plex, optimized for Apple TV playback.

## Features

### plex_pipeline.py (Recommended - Unified Pipeline)
- **One-step processing**: Rename + Transcode in a single command
- Automatically renames movies and TV shows with Plex-friendly names
- Uses **TMDb API** (Plex's native metadata source)
- Adds TMDb IDs to folder names for accurate Plex matching
- Hardware-accelerated transcoding using Apple M1 VideoToolbox
- Converts to HEVC (H.265) for Apple TV direct play
- Auto-detects 1080p vs 4K and adjusts bitrate
- Preserves HDR metadata
- Parallel processing for faster batch conversion
- Supports TV shows (seasonal and date-based episodes)
- Supports movies with year detection
- Optional source deletion after successful processing

### Individual Scripts (Alternative Two-Step Workflow)

**plex_renamer.py** - Renames files only
**plex_transcoder.py** - Transcodes files only

Use these if you prefer to separate renaming and transcoding steps.

## Prerequisites

1. **Python 3.9+**
2. **FFmpeg** with VideoToolbox support (for transcoding)
   ```bash
   brew install ffmpeg
   ```
3. **TMDb API Key** (free)
   - Go to https://www.themoviedb.org/signup
   - Create an account
   - Go to Settings → API
   - Request an API key (select "Developer" option)
   - Copy your API key

## Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/yourusername/plex_renamer.git
   cd plex_renamer
   ```

2. Install Python dependencies:
   ```bash
   pip install requests tqdm
   ```

3. Set your TMDb API key:
   ```bash
   export TMDB_API_KEY="your_api_key_here"
   ```

   To make it permanent, add to your `~/.zshrc` or `~/.bashrc`:
   ```bash
   echo 'export TMDB_API_KEY="your_api_key_here"' >> ~/.zshrc
   source ~/.zshrc
   ```

## Workflow Options

### Option 1: Unified Pipeline (Recommended)

**One command does everything!**

#### Folder Structure
```
your-base-folder/
├── 1.Rename/          # Input: Place raw video files here
├── 4.Upload/          # Auto-created: Final transcoded files for Plex
└── X.Issues/          # Auto-created: Files that need manual review
```

#### Single Step: Process Everything

```bash
python3 plex_pipeline.py ./1.Rename --skip-hevc --delete-source
```

**What it does:**
- Scans files in `1.Rename/`
- Searches TMDb for movie/TV metadata
- Renames to Plex-friendly format with `{tmdb-12345}` IDs
- Transcodes to HEVC using M1 hardware acceleration
- Outputs directly to `4.Upload/` ready for Plex
- Puts problematic files in `X.Issues/` for manual review

**Example output:**
```
Before: The.Movie.2024.1080p.WEB-DL.mkv
After:  4.Upload/Movies/The Movie (2024) {tmdb-12345}/The Movie (2024).mp4

Before: Show.S01E05.Episode.Title.avi
After:  4.Upload/TV Shows/Show (2020-) {tmdb-67890}/Season 01/Show - s01e05 - Episode Title.mp4
```

**Recommended options:**
- `--skip-hevc` - Skip transcoding files already in HEVC (just copies them)
- `--delete-source` - Delete source files after successful processing
- `--workers 2` - Number of parallel processes (default: 2)

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
