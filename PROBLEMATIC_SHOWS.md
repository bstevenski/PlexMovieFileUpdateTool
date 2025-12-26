# Handling TV Shows with Wrong Episode Numbers

## Problem

You have TV shows where the episode titles are correct but the season/episode numbers in the filenames are wrong. The
current plexifier sends these files to the `Errors` folder during processing.

## Solution

Process these problematic shows **separately** after your main run:

### Step 1: Run Main Pipeline

Process all your normally-behaving shows:

```bash
hatch run standard-run
# Or for testing:
hatch run debug-run
```

This will send problematic shows to `Errors/TV Shows/` while successfully processing the rest.

### Step 2: Fix and Re-process Problematic Shows

1. **Manually fix the episode numbers** in the filenames in `Errors/TV Shows/`
2. **Re-run only on the errors folder**:

```bash
python3 src/plexifier/plexifier.py ../Errors --dry-run --log-level DEBUG
```

### Example Workflow

```bash
# Step 1: Process everything
hatch run debug-run

# Review files in ../Errors/TV Shows/ - manually fix episode numbers
# Example: Rename "Show.S99E99.Episode Title.mkv" to "Show.S02E05.Episode Title.mkv"

# Step 2: Re-process only the fixed files
python3 src/plexifier/plexifier.py ../Errors --dry-run

# Step 3: If dry-run looks good, process for real
python3 src/plexifier/plexifier.py ../Errors
```

## Why This Approach Works

1. **Standard pipeline handles 90% of content** automatically
2. **Manual intervention only for truly problematic files**
3. **Dry-run preview** prevents mistakes on already-fixed content
4. **Targeted re-processing** saves time and API calls

## File Naming Guidelines

When fixing episode numbers manually, follow this format:

```
Show Name - S##E## - Episode Title.extension
```

Examples:

- ✅ `Law and Order SVU - S25E13 - Children of Shadow.mkv`
- ✅ `Office - S01E01 - Pilot.mkv`
- ❌ `Law and Order SVU - Episode Title.mkv` (missing S##E##)

This approach gives you maximum control while preserving the efficiency of the automated pipeline.