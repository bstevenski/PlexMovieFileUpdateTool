# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2025-12-24

### Added

- Initial release of Plex Media Tool
- Automated media file processing pipeline
- TMDb API integration for metadata lookup
- Plex-compliant file naming and organization
- Video transcoding to H.264/AAC for maximum compatibility
- CLI with dry-run and debug capabilities
- Comprehensive logging system
- Error handling and file recovery mechanisms

### Changed

- Simplified transcoding to always target H.264 instead of HEVC for broader device compatibility
- Removed HEVC detection and compatibility checks
- Improved package structure following Python packaging standards
- Updated imports to use relative imports in package `__init__.py`
- Fixed entry point configuration in pyproject.toml
- Updated log directory to use `.logs/` (hidden directory)
- Fixed coverage configuration from `plex` to `plexifier`

### Fixed

- Fixed missing formatter and parser module imports
- Fixed unused 'frame' parameter in signal handler
- Fixed wildcard imports in package initialization
- Added IDE files (.project, .pydevproject) to .gitignore
- Updated all references to use consistent log directory naming

### Deprecated

- HEVC skipping functionality - all files are now processed for maximum compatibility
- Previous CLI flags related to HEVC handling (kept for backward compatibility)

### Security

- No sensitive information logged or committed
- Environment variable usage for API keys

### Documentation

- Updated README with current CLI options and usage
- Added comprehensive troubleshooting section
- Added development and testing instructions
- Documented project structure and architecture

---

## [Unreleased] - Development

### Planned

- [ ] Unit test coverage for all modules
- [ ] Integration tests for end-to-end workflows
- [ ] Configuration file support
- [ ] More transcoding options (quality settings, different codecs)
- [ ] Progress reporting and notifications
- [ ] Docker containerization