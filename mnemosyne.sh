#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#                   MNEMOSYNE V1.0 - Mac/Linux Launcher
# ═══════════════════════════════════════════════════════════════════════════

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo ""
    echo "[!] Python 3 is required but not found."
    echo ""
    echo "Please install Python 3:"
    echo "  - macOS: brew install python3"
    echo "  - Ubuntu/Debian: sudo apt install python3"
    echo "  - Fedora: sudo dnf install python3"
    echo ""
    exit 1
fi

# Launch Mnemosyne
python3 "$SCRIPT_DIR/mnemosyne.py" "$@"
exit_code=$?

# Pause on error
if [ $exit_code -ne 0 ]; then
    echo ""
    echo "[!] Mnemosyne exited with error code $exit_code"
    read -p "Press Enter to continue..."
fi

exit $exit_code
