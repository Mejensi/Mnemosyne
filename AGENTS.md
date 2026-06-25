# Mnemosyne Agent Guide

## What This Project Is
Mnemosyne is a local-first video compression tool.

Its job is simple:
- convert videos to H.264 / 480p
- keep user data safe
- never replace the original until verification passes

Core flow:
1. Encode to a temporary workspace.
2. Verify the result.
3. Rename the original to `.bak`.
4. Move the verified output into place.
5. Restore original timestamps (atime/mtime/ctime).
6. Remove the backup only after a final size check passes.

## Source Of Truth
- `mnemosyne.py`: main implementation (~3680 lines, single-file runtime)
- `mnemosyne.bat`: Windows launcher only; requires `mnemosyne.py` beside it
- `mnemosyne.sh`: Unix launcher only; requires `mnemosyne.py` beside it

`mnemosyne.sh` and `mnemosyne.bat` are both **launcher-only** — Python code is intentionally not embedded to minimize antivirus false positives. Both detect the script directory, verify that `mnemosyne.py` is present, locate a usable `python`/`python3`, and exec into the script.

## Non-Negotiables
- Prefer `mnemosyne.py` over docs if they disagree.
- Never delete or overwrite original media before verification succeeds.
- Treat `.bak` files as recovery data, not junk.
- FFmpeg discovery/download is security-sensitive. Do not weaken trusted-binary checks.
- Do not re-introduce Python embedding into `.bat` or `.sh`. Keep them launcher-only.
- Do not bring back `ffmpeg_sources.json` — all FFmpeg source info lives inline in `mnemosyne.py` (`DEFAULT_FFMPEG_DOWNLOADS`).
- Do not bring back `sync_wrappers.py` — there is nothing to inject into the Unix wrapper anymore.
- `runtime_validation/` and `tests/` are intentional and must stay.

## Test Entry Point
Run this after substantial changes:
```powershell
python tests\test_runtime_validation.py
```

Current coverage includes:
- truncated output rejection
- stream-loss rejection
- low/high FPS behavior
- chapter and metadata preservation
- temp workspace cleanup safety
- backup restore/purge behavior
- FFmpeg discovery hardening
- staged install safety
- runtime fixture scenarios
- launcher smoke tests (`.bat` / `.sh` / `.py` startup behavior)
- FFmpeg source manifest pinning (inline default, no JSON dependency)
- checksum verification (sha256) and Evermeet GPG signature verification
- unverified-source prompt override behavior

Useful next tests:
- FFmpeg auto-download/bootstrap flows with mocked network/process calls
- Live dashboard FPS/speed regression coverage (post-`format_bytes` / `fps=`/`speed=` fix)

## Repo Map
- `bin/`: bundled FFmpeg/FFprobe binaries
- `Lib/`, `Scripts/`: Python runtime fragments (Windows embeddable)
- `runtime_validation/`: reusable media fixtures (scenarios 01-04)
- `tests/`: automated regression tests
- `config.json`: local/sample config
- `README.md`: user-facing overview
- `NOTICE.md`: licensing and attribution
- `run_windows_tests.bat`: Windows test entry helper

## Safe To Ignore
- `__pycache__/`
- `Mnemosyne_Log.txt`
- ad-hoc media files created for manual testing
- empty temporary sandboxes such as `test_appdata/`

## Do Not Remove Without Approval
- generated logs or temp sandboxes only if the user asks
- `runtime_validation/`
- `tests/`
- `bin/`
