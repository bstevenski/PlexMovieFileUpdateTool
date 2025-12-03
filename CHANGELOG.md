Changelog
=========

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project adheres to Semantic Versioning.

## [Unreleased]

- Nothing yet.

## [0.2.0] - 2025-12-03

### Added
- Manual Check destination and `--manual-root` CLI flag for items that cannot be safely renamed.
- Automatic post-run pruning of empty folders under the source `root` (skips the top-level root).
- README updates documenting routing matrix, inferred destination roots, and pruning behavior.

### Changed
- Routing rules finalized:
  - Matched (IMDb ID found) → `3.Upload`
  - Unmatched but renamable → `.mkv` → `3.Upload`, non-`.mkv` → `2.Convert`
  - Not renamable → `1.Manual Check`
- Improved title/year fallback extraction from noisy filenames.
- Switched OMDb endpoint to HTTPS.

### Fixed
- Removed duplicate `sXXeYY` token in TV filenames (now `Show - s01e01.ext` when no episode title).
- Addressed IDE/static analysis warnings in `plex_renamer.py` (uninitialized locals, unused vars, shadowed names, redundant parentheses, narrowed exceptions, typos).

## [0.1.1] - 2025-11-30

Patch release inferred from the most recent commits on the default branch (2–5 latest commits).

### Added
- Add MIT LICENSE file to the repository.

### Changed
- Update and expand README.md (usage, requirements, notes).
- Refine .gitignore entries.

## [0.1.0] - Initial release

### Added
- Initial CLI tool plex_renamer.py with core functionality:
  - OMDb-powered lookups for movies and TV.
  - TV episode detection from filenames (e.g., S01E02).
  - IMDb ID tagging in destination folders.
  - Dry-run support and optional progress display.