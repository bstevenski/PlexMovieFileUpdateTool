# Episode Title Override Feature

This feature allows you to specify which TV series should use episode titles instead of S##E## numbering in their filenames, which is useful when:

- Episode numbers are incorrect but titles are correct
- You have intervention files with mismatched episode numbering
- Certain series have inconsistent episode numbering across releases

## Configuration

Create a JSON file (e.g., `episode-title-overrides.json`) with the following format:

```json
{
  "series": [
    "Problematic TV Show",
    "Another Series with Wrong Episode Numbers",
    "Law and Order: SVU",
    "Some Anime Series"
  ]
}
```

## Usage Scenarios

### 1. Global Episode Titles (All TV Shows)
Use episode titles for ALL TV shows:

```bash
hatch run episode-title-run
hatch run episode-title-debug
```

### 2. Per-Series Override (Only Specific Shows)
Only the series listed in your JSON file will use episode titles:

```bash
hatch run episode-title-override-run
hatch run episode-title-override-debug
```

### 3. Global with Exclusions (All Except Specific Shows)
Use episode titles for ALL shows EXCEPT those in your JSON file:

```bash
python -m plexifier.plexifier --use-episode-titles --episode-title-overrides episode-title-overrides.json
```

## File Naming Examples

### Standard Format
```
Law and Order: SVU (1999-) {tmdb-4357}/Season 25/Law and Order: SVU - S25E13 - Children of Shadow.mkv
```

### Episode Title Only Format
```
Law and Order: SVU (1999-) {tmdb-4357}/Season 25/Law and Order: SVU - Children of Shadow.mkv
```

## How It Works

1. **Global Mode** (`--use-episode-titles`): All TV shows use episode titles
2. **Override Mode** (`--episode-title-overrides file.json`): Only shows in JSON file use episode titles
3. **Exclusion Mode** (`--use-episode-titles --episode-title-overrides file.json`): All shows use episode titles EXCEPT those in JSON file

The system matches series names **case-insensitively** and ignores extra whitespace.