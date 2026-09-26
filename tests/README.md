# Mnemosyne Test Suite Architecture & Catalog

This document details the hierarchy, scope, and safety guarantees of the Mnemosyne test suite, ordered from **User-Facing (High-Level Workflows)** to **Kernel, Concurrency & Cryptographic Internals (Expert)**.

---

## Test Directory Overview

```
tests/
├── 1. User Journey & Configuration
│   ├── test_empty_scan_flow.py           # User guidance when no videos are found
│   └── test_config_and_cli.py            # CLI options, profiles, and Enum backward compatibility
├── 2. UI & Terminal Resilience
│   ├── test_ui_and_worker_enhancements.py# Live dashboard, smoothed ETA & speed, thread safety
│   ├── test_ui_multiworker_collapse.py   # Boundary budget guards, artifact prevention
│   └── test_ui_stability.py              # Fuzzing, non-UTF8/ASCII fallback, headless mode
├── 3. System Launchers
│   └── test_launchers.py                 # Windows .bat & Unix .sh launchers, Python bootstrap
├── 4. Hardware & Storage Safety
│   └── test_drive_and_storage_safety.py  # USB/NVMe detection, worker throttling, space headroom
├── 5. Crash Recovery & Transaction Safety
│   └── test_journal_recovery.py          # Atomic swap rollback, journal recovery, power outage safety
├── 6. Supply Chain & Cryptography
│   ├── test_ffmpeg_verification.py       # Official SHA-256 and GPG verification
│   └── test_ffmpeg_verification_more.py  # Foreign-key rejection, signature fallback scraping
└── 7. Core Transcoding & Stream Integrity
    └── test_runtime_validation.py        # Stream/subtitle/chapter preservation, ProcessManager
```

---

## 1. User Journey & Configuration (High-Level)

Tests the entry points that users interact with directly.

### `test_empty_scan_flow.py`
* **Purpose:** Ensures the application never fails silently when an empty directory is selected.
* **Scenarios Covered:**
  * Detects videos located in subfolders when the root directory has none, prompting the user: *"Enable recursive subfolder scan?"*.
  * Non-interactive mode (pipes, scripts, cron jobs) exits cleanly with appropriate exit codes (`ExitCode.ERROR` / `ExitCode.SUCCESS`) without blocking on `stdin`.

### `test_config_and_cli.py`
* **Purpose:** Validates CLI argument parsing, configuration precedence, and data integrity.
* **Scenarios Covered:**
  * CLI arguments (`-r`, `-w`, `--height`, `-d`, `--codec`) override saved configuration.
  * Corrupted configuration values (e.g. negative FPS, invalid worker counts) gracefully fall back to safe defaults (`DEFAULT_CONFIG`).
  * Profile selection (`720p`, `1080p`) correctly adjusts resolution and bitrate.
  * **Enum Invariants:** Asserts `ProcessResult`, `DriveType`, `StorageMode`, `SortOrder`, and `SystemFFmpegPolicy` are strictly backwards-compatible with primitive `int` and `str` types and serialize cleanly to JSON.

---

## 2. UI & Terminal Resilience (User Experience)

Ensures terminal output remains clear, stable, and visually artifact-free under all conditions.

### `test_ui_and_worker_enhancements.py`
* **Purpose:** Validates real-time metrics and concurrent worker progress display.
* **Scenarios Covered:**
  * Uses Exponential Moving Average (EMA) to smooth transcode speed and provide stable, jitter-free ETA calculations.
  * Hardware-safe worker allocation: dynamically caps parallel workers based on CPU core count, GPU availability, and storage medium.

### `test_ui_multiworker_collapse.py`
* **Purpose:** Prevents line wrapping and scrolling artifacts when running high worker counts in restricted terminal windows.
* **Scenarios Covered:**
  * Enforces maximum rendered line width <= terminal columns (truncating with `...` when necessary).
  * Enforces total rendered lines <= terminal height budget to prevent terminal ghosting and unwanted scrolling.

### `test_ui_stability.py`
* **Purpose:** Guarantees display stability across edge-case terminal configurations and encodings.
* **Scenarios Covered:**
  * Automatic ASCII fallback (`+`, `-`, `|`) for box borders when running on terminals without UTF-8 support.
  * Terminal resize fuzz testing down to `0x0` dimensions without throwing unhandled exceptions.
  * Piped / headless environments disable ANSI escape codes and screen clearing.

---

## 3. System Launchers & Platform Integration

### `test_launchers.py`
* **Purpose:** Verifies that platform launcher scripts initialize the runtime safely across Windows, Linux, and macOS.
* **Scenarios Covered:**
  * Windows `mnemosyne.bat`: Python version detection (`py -3`, `python`, `python3`), automated `winget` installation prompts when Python is absent, and UTF-8 code page configuration.
  * Unix `mnemosyne.sh`: `MNEMOSYNE_LAUNCHER_DIR` resolution, execution permissions, and exit code propagation.

---

## 4. Hardware & Storage Safety (Hardware-Aware)

Protects user hardware and storage devices from I/O saturation, overheating, and out-of-space crashes.

### `test_drive_and_storage_safety.py`
* **Purpose:** Distinguishes between internal high-speed drives (NVMe, SATA) and external removable media (USB, SD cards).
* **Scenarios Covered:**
  * Parses Linux `/proc/mounts` and sysfs attributes to detect USB storage.
  * Automatically throttles workers to `1` on removable media to prevent bus disconnects and filesystem corruption.
  * Verifies disk space headroom (minimum 512 MB and 1.25x the file size) before encoding begins.

---

## 5. Crash Recovery & Transaction Safety (Mission-Critical)

Guarantees zero data loss even if the process is terminated mid-transcode or system power is cut.

### `test_journal_recovery.py`
* **Purpose:** Validates the atomic file replacement pipeline and journal recovery engine.
* **Scenarios Covered:**
  * **Atomic Swap:** Safe sequence: `original -> .bak -> place verified temp -> verify file size -> remove .bak`.
  * **Transaction Journal:** Step-by-step progress logging in `.mnemosyne_txn.json`.
  * **Rollforward / Rollback:** On startup after an unexpected crash, automatically detects leftover `.bak` files and journal states to restore the original uncorrupted file.

---

## 6. Supply Chain & Cryptographic Verification (Security)

Ensures downloaded FFmpeg binaries are verified authentic and untampered.

### `test_ffmpeg_verification.py` & `test_ffmpeg_verification_more.py`
* **Purpose:** Cryptographic validation of managed FFmpeg downloads.
* **Scenarios Covered:**
  * Checksum verification: downloaded archives must match official SHA-256 hashes.
  * GPG signature verification: validates signatures against official distributor public keys.
  * **Foreign-Key Attack Rejection:** Strictly rejects archives signed by valid GPG keys that do not match the expected publisher fingerprint (`20F6EA3E0CFD6B4C53447A73476C4B611A660874`).
  * HTML scraping fallback when static release URLs return HTTP 404.

---

## 7. Core Transcoding & Stream Integrity (Deep AV Internals)

Comprehensive end-to-end verification of video transcode quality and metadata preservation.

### `test_runtime_validation.py`
* **Purpose:** Runs real FFmpeg transcode passes against synthetic test media (`lavfi`).
* **Scenarios Covered:**
  * **Multi-Stream Preservation:** Ensures secondary audio tracks (e.g. English, Turkish), subtitle streams (`.srt`), embedded font attachments (`.ttf`), and chapter markers are preserved without loss.
  * **Timestamp Preservation:** File creation and modification timestamps (`st_mtime`) match the original input file.
  * **ProcessManager Lifecycle:** Cleanly terminates FFmpeg subprocesses on SIGINT/SIGTERM, preventing orphan/zombie processes.
  * **Dynamic Timeout Scaling:** Enforces timeout scaling (`duration * 4 + 15s`, minimum 30s, capped at 900s) to prevent frozen decode jobs.

---

## Running the Test Suite

```bash
# Standard library unittest (no external dependencies required):
python3 -m unittest discover -s tests

# With pytest:
pytest -v tests
```
