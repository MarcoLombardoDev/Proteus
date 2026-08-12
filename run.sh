#!/usr/bin/env bash
# Run Proteus on Linux/macOS (handy for development and testing).
set -euo pipefail

cd "$(dirname "$0")"

PY="${PYTHON:-python3}"

if ! "$PY" -c "import tkinter" >/dev/null 2>&1; then
    echo "ERROR: the tkinter module is not available for $PY." >&2
    echo "  Debian/Ubuntu: sudo apt install python3-tk" >&2
    echo "  Fedora:        sudo dnf install python3-tkinter" >&2
    echo "  macOS (brew):  brew install python-tk" >&2
    exit 1
fi

if ! "$PY" -c "import PIL" >/dev/null 2>&1; then
    echo "WARNING: Pillow is not installed, previews are disabled." >&2
    echo "         Install it with: $PY -m pip install -r requirements.txt" >&2
fi

exec "$PY" main.py "$@"
