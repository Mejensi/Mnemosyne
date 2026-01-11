# Changelog

## [1.0.0] - 2026-01-12

### Added
- Initial stable release
- Full video transcoding engine with hardware acceleration support
  - NVIDIA NVENC (Constant Quality mode)
  - Intel QuickSync
  - Apple VideoToolbox
  - VAAPI (Linux AMD/Intel)
  - CPU fallback (libx264)
- Metadata preservation (file timestamps)
- Atomic file swap safety system with backup (.bak)
- Multi-threaded parallel processing
- Frame verification for quality assurance
- Recursive folder scanning
- Customizable output resolution (default 480p)
- Customizable bitrates and FPS
- Real-time progress monitoring
- Security & transparency dashboard
- Removable media detection and warnings
- Desktop and AppData logging options
- Auto-cleanup of temporary files
- Cross-platform support (Windows, macOS, Linux)
- FFmpeg auto-download functionality
- Command-line argument support (-r, -w, --height, --codec)
- Graceful shutdown with Ctrl+C support
- Process monitoring and error recovery

### Features
- **The Guardian Protocol**: Zero-loss atomic file swaps with backup verification
- **Aesthetic Intelligence**: Modern terminal UI with real-time telemetry
- **Hardware Acceleration**: Automatic codec detection and selection
- **Privacy First**: 100% local processing, no telemetry
- **History Preservation**: Original file timestamps restored after conversion

### Built With
- Python 3.7+
- FFmpeg (auto-downloaded if missing)
- Cross-platform compatibility (Windows CMD, Bash, Python)

### License
GNU General Public License v3.0
