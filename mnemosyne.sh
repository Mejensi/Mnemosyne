#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# ============================================================================
#                               MNEMOSYNE
#                      The Keeper of Digital Memory
# ============================================================================
# Copyright (C) 2026 Mejensi
# Licensed under GNU General Public License v3.0
# ============================================================================
# Unix launcher only. Requires mnemosyne.py in the same folder.
# Python code is intentionally not embedded to reduce false positives.
# ============================================================================

# Detect Script Directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export MNEMOSYNE_LAUNCHER_DIR="$SCRIPT_DIR"

if [ ! -f "$SCRIPT_DIR/mnemosyne.py" ]; then
    echo "[!] mnemosyne.py is required."
    echo "[!] Keep mnemosyne.py in the same folder as mnemosyne.sh."
    echo "[!] This shell file is only a launcher and does not contain the app."
    exit 1
fi

if ! command -v python3 &> /dev/null; then
    echo "[!] Python 3 is required but not found."
    echo "[!] Please install Python 3 before running Mnemosyne."
    exit 1
fi

python3 "$SCRIPT_DIR/mnemosyne.py" "$@"
EXIT_CODE=$?

# Copy log beside launcher if it exists in runtime dir
if [ -f "$SCRIPT_DIR/.mnemosyne_runtime/Mnemosyne_Log.txt" ]; then
    cp "$SCRIPT_DIR/.mnemosyne_runtime/Mnemosyne_Log.txt" "$SCRIPT_DIR/Mnemosyne_Log.txt" 2>/dev/null
fi

exit $EXIT_CODE
