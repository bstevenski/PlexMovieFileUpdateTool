# 🎬 Plex Movie & TV Renamer (OMDb-Powered)

A Python script that automatically renames your movie and TV show files into a clean, [Plex](https://www.plex.tv/)-friendly structure using metadata from the [OMDb API](https://www.omdbapi.com/).  
It can detect TV episodes, fetch IMDb IDs, and organize everything into properly named folders.

---

## ✨ Features

- 🧠 **Automatic detection** of TV episodes based on filename patterns (e.g. `ShowName.S02E03.mkv`)  
- 🎥 **Movie and TV metadata lookup** from the OMDb API  
- 🆔 **Adds IMDb IDs** to renamed folders for easy identification  
- 🗂️ **Organized folder structure**, e.g.  
  ```
  Movies/
    The Matrix (1999) {imdb-tt0133093}/
      The Matrix (1999).mkv

  TV Shows/
    Breaking Bad (2008) {imdb-tt0903747}/
      Season 01/
        Breaking Bad - s01e01 - Pilot.mkv
  ```
- 🧪 **Dry-run mode** to preview changes without modifying files  
- ⚙️ **Command-line options** for automation and flexibility  
- 🪶 **Progress bar** via [tqdm](https://pypi.org/project/tqdm/)

---

## 🧰 Requirements

- Python **3.8+**
- OMDb API key ([get one here](https://www.omdbapi.com/apikey.aspx))
- Installed Python packages:
  ```bash
  pip install requests tqdm
  ```

---

## 🔧 Setup

1. **Clone or download** this script.

2. **Set your OMDb API key** as an environment variable:
   ```bash
   export OMDB_API_KEY=your_api_key_here
   ```

3. (Optional) Make the script executable:
   ```bash
   chmod +x plex_renamer.py
   ```

---

## 🚀 Usage

```bash
./plex_renamer.py <root_folder> [options]
```

### Example
```bash
./plex_renamer.py ~/Movies --dry-run
```

### Arguments

| Option | Description |
|--------|-------------|
| `root` | Root folder containing your movies and/or TV shows. |
| `--dry-run` | Simulate the renames without making any changes. |
| `--no-confirm` | Skip confirmation before renaming files. |
| `--debug` | Enable detailed debug output for troubleshooting. |

---

## 🧩 How It Works

1. The script recursively scans the provided folder for video files (`.mkv`, `.mp4`, `.avi`, `.mov`).
2. For each file:
   - Checks if it already includes an IMDb ID in its name or folder.
   - Attempts to identify whether it's a movie or TV episode.
   - Queries the OMDb API for title, year, and IMDb ID.
   - Builds a standardized file and folder name.
3. Displays a preview of all proposed renames.
4. If confirmed, moves the files into the new structure.

---

## 🧠 Filename Detection Examples

| Input Filename | Output Filename |
|----------------|-----------------|
| `Breaking.Bad.S01E01.mkv` | `Breaking Bad - s01e01 - Pilot.mkv` |
| `The.Matrix.1999.mp4` | `The Matrix (1999).mp4` |
| `Friends-S02E10.avi` | `Friends - s02e10 - The One with Russ.avi` |

---

## 🧹 Folder Output Example

```
/Movies
  The Matrix (1999) {imdb-tt0133093}/
    The Matrix (1999).mkv

/TV Shows
  The Office (2005) {imdb-tt0386676}/
    Season 01/
      The Office - s01e01 - Pilot.mkv
      The Office - s01e02 - Diversity Day.mkv
```

---

## ⚠️ Notes

- The OMDb API has daily request limits unless you have a paid key.
- Filenames **must** include recognizable season/episode tags like `S01E01` for TV shows.
- Files already containing an IMDb ID (e.g. `{imdb-tt1234567}`) are skipped.

---

## 🪛 Troubleshooting

| Issue | Solution |
|--------|-----------|
| `ValueError: OMDB_API_KEY environment variable is not set!` | Make sure you’ve exported your API key in the terminal before running. |
| Script doesn’t rename some files | They might not have clear title or season/episode info — use `--debug` to see why. |
| Wrong match from OMDb | Rename the file more accurately before re-running. |

---

## 🧑‍💻 Example Workflow

```bash
# Preview all renames without changing files
./plex_renamer.py ~/Downloads/Videos --dry-run

# Rename everything automatically (no confirmation)
./plex_renamer.py ~/Downloads/Videos --no-confirm

# Rename with debug logging
./plex_renamer.py ~/Downloads/Videos --debug
```

---

## 🪄 License

MIT License © 2025  
Developed for personal media library organization.
