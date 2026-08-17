<img width="2633" height="1171" alt="believeinyourself" src="https://github.com/user-attachments/assets/1942c116-a65b-49e1-b0cc-2f90a83e0ca5" />

# Mnemosyne


Mnemosyne is a powerful, automated video compression engine built for simplicity and absolute data safety. It re-encodes your video collection to H.264 while preserving original timestamps, metadata, subtitles, audio tracks, and chapters — leaving your digital history exactly as you left it.

---

## Features

- **Smart Compression** — Compresses videos to H.264 with configurable resolution (default 480p) and bitrate. Automatically detects and uses the best available hardware encoder: NVENC (NVIDIA), AMF (AMD), QSV (Intel), VideoToolbox (macOS), or VAAPI (Linux). Falls back to CPU (`libx264`) if hardware encoding fails.
- **Safety Bridge** — Every conversion uses an atomic backup-and-swap system. The original file is renamed to `.bak` before the new file is placed, then the backup is deleted only after successful verification. A transaction journal tracks each step so interrupted runs can be recovered safely.
- **Orphaned Backup Recovery** — If a previous run was interrupted, Mnemosyne detects leftover `.bak` files on startup and offers interactive rescue options: restore, preserve-and-restore, overwrite, or purge.
- **Deep Verification** — Before the original is replaced, the output is checked against the input for codec, resolution, aspect ratio, duration, FPS, frame count, audio streams, subtitles, chapters, and pixel format. Files that fail verification are discarded and optionally retried with CPU encoding.
- **Timeline Preservation** — Original file access time, modification time, and creation time (Windows) are restored to the new file after conversion. Your folder stays sorted exactly as before.
- **Full Stream Preservation** — All audio tracks, subtitle streams, data streams, attachment streams, and chapters are copied without re-encoding unless overridden.
- **Managed FFmpeg** — Mnemosyne can download, verify, and manage its own FFmpeg binaries. Supports appdata, portable, session-scoped, and custom install locations. GPG signature verification is enforced on macOS (Evermeet source). Stale installs are detected and can be cleaned up automatically.
- **Live Dashboard** — A real-time terminal dashboard shows per-worker progress, FPS, encoding speed, ETA, and file size deltas. Falls back to compact single-line output on narrow terminals or non-TTY environments.
- **Multi-threaded Processing** — Configurable worker count (sequential, parallel, or custom). Automatically limits to 1 worker when removable media is detected.
- **Drag-and-Drop Mode** — Drop video files directly onto the launcher script to process specific files without a folder scan.

---

## Requirements

- **Python 3.8+**
- **FFmpeg + FFprobe** — Either already installed on your system, or Mnemosyne can download and manage them for you.

---

## Installation & Usage

Download `mnemosyne.py` along with the launcher script for your platform and place them in the same folder.

### Windows

Run **`mnemosyne.bat`** (requires `mnemosyne.py` in the same folder). The launcher checks for Python and can install it automatically via `winget` if missing.

### Linux & macOS

```bash
bash mnemosyne.sh
```

Requires `mnemosyne.py` in the same folder. Ensure Python 3 is installed. On macOS, GPG is required for automatic FFmpeg download (signature verification). Install via Homebrew: `brew install gnupg`.

### Direct Python

```bash
python mnemosyne.py [options] [files...]
```

---

## Command-Line Options

| Option | Description |
|---|---|
| `paths` | Specific video files to process (drag-and-drop mode) |
| `-r`, `--recursive` | Scan subfolders |
| `-w N`, `--workers N` | Number of parallel encoding threads |
| `--height N` | Target output height in pixels (default: 480) |
| `--desktop-log` | Write log file to Desktop instead of temp folder |
| `--codec` | Force a specific encoder: `auto`, `h264_nvenc`, `h264_amf`, `h264_qsv`, `h264_videotoolbox`, `h264_vaapi`, `libx264` |

---

## Interactive Menu

When run interactively, Mnemosyne shows a mission briefing before starting and allows you to adjust settings before each run:

- **Profile** — Output resolution preset
- **Worker Mode** — Sequential, parallel, or custom thread count
- **Scan Scope** — Current folder only or recursive
- **Sort Order** — Name A-Z, Name Z-A, Largest First, Smallest First
- **Log File Location** — Temp folder or Desktop
- **FFmpeg** — Download behavior and install location

Press `E` to edit, `S` to save settings for future runs, `Q`/`C` to quit.

---

## Safety & Recovery

Mnemosyne uses a multi-stage atomic swap to ensure your originals are never lost:

1. Output is encoded to a temp file inside a session workspace.
2. Output is fully verified before touching the original.
3. Original is renamed to `filename.ext.bak`.
4. Verified output is moved to the original path.
5. Timestamps are restored.
6. Backup is deleted only after a final size check passes.

If anything fails at any stage, the backup is restored automatically. Transaction journals record each step and survive crashes, allowing recovery on the next run.

If Ctrl+C is pressed during processing, in-flight FFmpeg processes are terminated, temp files are cleaned up, and any remaining backups are reported so they can be rescued safely.

---

## Configuration

Settings are saved to:
- **Windows:** `%APPDATA%\Mnemosyne\config.json`
- **Linux/macOS:** `~/.mnemosyne/config.json`

Saved settings include resolution, bitrate, FPS, worker count, recursive mode, sort order, log location, and FFmpeg preferences. Command-line arguments override saved settings for that session only.

---

## Supported Formats

`.mp4` `.mkv` `.avi` `.mov` `.flv` `.wmv` `.webm` `.ts` `.m4v`

---

## Auto-Skip Logic

Files are skipped automatically if they already meet the target parameters (resolution ≤ target height, correct codec, correct pixel format, matching FPS). This makes it safe to re-run Mnemosyne on a folder that has already been processed.

---

## Legal & Attribution

This project is open-source software licensed under the **GNU General Public License v3.0**.

Mnemosyne relies on **FFmpeg** for video processing. FFmpeg is licensed under the LGPL/GPL. Please refer to [NOTICE.md](https://github.com/Mejensi/Mnemosyne/blob/main/NOTICE.md) for full third-party attributions, license details, and the disclaimer of warranty.

Copyright (C) 2026 Mejensi.
