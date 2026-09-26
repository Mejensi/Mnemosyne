# Changelog

All notable changes to the Mnemosyne project.

---

## [2.1] — 2026-09-26

### Security & Hardening

- **Eliminated permanent unverified bypass**: Removed the "Accept and remember" option from unverified FFmpeg download prompts. Unverified binaries can now only be accepted for the current session.
- **Enforced pinned Evermeet GPG fingerprint verification**: `verify_evermeet_signature` now checks `--status-fd 1` output for `[GNUPG:] VALIDSIG` matching the pinned fingerprint (`20F6EA3E...`), defeating foreign-key keyring attacks.
- **Fixed Windows SSL error abort**: Reordered SSL certificate validation before PowerShell download fallback to ensure connection aborts immediately on certificate failure.
- **Enforced explicit overwrite confirmation**: `audit_orphaned_backups` requires typing `"OVERWRITE"` in full before restoring backups, preventing accidental data loss.
- **Archive safety**: Added `MAX_EXTRACTED_BINARY_SIZE = 500 MB` ceiling to prevent zip bomb attacks during archive extraction.
- **Command argument injection hardening**: Added `--` argument separator to `ffprobe` invocations to safely handle filenames beginning with a hyphen.
- **Win32 64-bit handle safety**: Added explicit `restype = wintypes.HANDLE` and `argtypes` for `CreateFileW` and `CloseHandle` in `restore_file_metadata`.

### Reliability & Crash Safety

- **Atomic JSON journal writing**: Added `atomic_write_json` (`.tmp` + `flush` + `os.fsync` + `os.replace`) to prevent corrupted transaction journals during crashes.
- **JSON decode error handling**: `load_json_file` now catches `json.JSONDecodeError` and `ValueError` in addition to `OSError`.
- **Interrupt grace period**: Added `_ACTIVE_SWAPS` tracking in `handle_interrupt` giving in-flight atomic file swaps up to 2 seconds to complete cleanly on `SIGINT`.
- **Unhandled worker exception protection**: Wrapped `f.result()` in `ThreadPoolExecutor` loop with `try/except` to protect final reporting and cleanup.
- **Single-line SHA-256 parsing**: `parse_checksum_file` now handles bare single-line 64-character hash files (e.g. from gyan.dev).

### Architecture & Types

- **Typed Enums**: Replaced magic numbers and loose strings with `IntEnum` and `(str, Enum)` types:
  - `ProcessResult`: `FAILED = 0`, `SUCCESS = 1`, `SKIPPED = 2`
  - `DriveType`: `UNKNOWN = 0`, `REMOVABLE = 2`, `FIXED = 3`, etc.
  - `StorageMode`: `APPDATA`, `PORTABLE`, `SESSION`, `CUSTOM`
  - `SortOrder`: `NAME_AZ`, `NAME_ZA`, `SIZE_DESC`, `SIZE_ASC`
  - `SystemFFmpegPolicy`: `PROMPT`, `ALLOW`, `DENY`
  - `VideoCodec`: `AUTO`, `NVENC`, `AMF`, `QSV`, `VAAPI`, `VIDEOTOOLBOX`, `CPU`
  - `ExitCode`: `SUCCESS = 0`, `ERROR = 1`, `INTERRUPTED = 130`
- **Subfolder probing**: Added `probe_subfolder_videos` prompting users to enable recursive scanning (`-r`) when root directory contains no videos.
- **Launchers**: Added `Mnemosyne v2.1` window title escape sequence to `mnemosyne.sh`.

### Test Suite

- Expanded test suite to 170+ tests covering drive safety, crash recovery, terminal clipping boundaries, CLI precedence, and Enum invariants.
- Added `tests/README.md` test architecture and catalog guide.

---

## [2.0] — 2026-06-25

### Runtime

- **FPS/Speed parsing fixed in live dashboard** (lines 2875–2881)
  - FFmpeg `-progress` output emits `fps=` and `speed=` on separate lines; the previous code tried to parse both from the `fps=` line → `IndexError` → metrics never updated.
  - `speed=` moved to its own `elif` branch; each metric now parses on its own line.
- **`format_bytes()` was skipping the KB unit** (line 634)
  - Unit list was `("B", "MB", "GB", "TB")` → `("B", "KB", "MB", "GB", "TB")`.
  - Values between 1024 and 1048575 bytes were mislabeled (e.g. 2048 bytes → "2.0 MB" instead of "2.0 KB").
- **Inline default FFmpeg checksums refreshed**
  - Windows BtbN shared: `3795a54b…` → `3913e326…`
  - Linux BtbN shared: `b46c86f1…` → `b5c84340…`

### FFmpeg Sources

- **BtbN (Windows / Linux) now uses the `latest` tag**
  - `autobuild-2026-05-26-13-56/ffmpeg-N-124653-…` → `latest/ffmpeg-master-latest-…`
  - Checksum is now parsed dynamically from `checksums.sha256`; no manual URL update needed for new FFmpeg builds.
- **macOS (evermeet.cx) reverted to `/getrelease/` endpoints**
  - `ffmpeg-8.1.1.zip` (pinned static build) → `getrelease/zip` (always redirects to the current release).
  - Signature fallback added: when `/getrelease/zip/sig` returns 404 on a mirror, the version is scraped from the evermeet home page and the `.sig` URL is built directly.
- **johnvansickle (Linux fallback)** — already on stable URL, no change.
- **gyan.dev (Windows fallback)** — already on stable URL, no change.
- **`ffmpeg_sources.json` removed**
  - No longer a separate file shipped in the release.
  - All source data now lives in the `DEFAULT_FFMPEG_DOWNLOADS` inline default.
  - Code falls back to the inline default when the JSON is missing (it now never exists).
  - Users only need `.py` + `.bat` / `.sh` to run.

### Launchers

- **`mnemosyne.sh` slimmed down** — 3616 lines (152.8 KB) → 35 lines.
  - Previously embedded the entire `mnemosyne.py` via heredoc.
  - Now a pure launcher that calls `.py`, just like `.bat`.
  - Antivirus false-positive risk minimized.
  - `MNEMOSYNE_LAUNCHER_DIR` export and log-copy behavior preserved.
- **`sync_wrappers.py` removed** — the Python-injection tool into `.sh` is no longer needed.

### Documentation

- **README.md rewritten** (user-facing revision)
  - New features table, detailed usage, FFmpeg source table.
  - Installation & Usage, Command-Line Options, Safety & Recovery, Configuration sections.
  - Interactive Menu, Auto-Skip Logic, Legal & Attribution.
- **NOTICE.md updated** — full URLs for every FFmpeg download source, including Windows (BtbN + gyan.dev), Linux (BtbN + johnvansickle.com), macOS (evermeet.cx with GPG key `0x1A660874`), and mirror redirects (deolaha.ca).
- **README and tests updated** for `.sh` launcher-only format.

### Tests

- **`test_runtime_validation.py` line 950 assertion fixed**
  - `"auto-download is disabled"` → `"FFmpeg could not be downloaded or found"`
- **`test_launchers.py` updated**
  - `test_ffmpeg_source_manifest_is_pinned` now tests the inline default; `ffmpeg_sources.json` dependency removed.
  - `test_unix_launcher_exports_launcher_dir_and_prefers_external_python` adapted to `.sh` launcher-only format.
  - `test_download_ffmpeg_unverified_override_requires_stage_validation` — source count reduced 5 → 4.
- **Test results:** 117 tests, all passing (10 skip — platform-specific).
