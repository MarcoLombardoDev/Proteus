#!/usr/bin/env bash
# Avvio di Rebranding Tool su Linux/macOS (utile per sviluppo e test).
set -euo pipefail

cd "$(dirname "$0")"

PY="${PYTHON:-python3}"

if ! "$PY" -c "import tkinter" >/dev/null 2>&1; then
    echo "ERRORE: il modulo tkinter non e' disponibile per $PY." >&2
    echo "  Debian/Ubuntu: sudo apt install python3-tk" >&2
    echo "  Fedora:        sudo dnf install python3-tkinter" >&2
    echo "  macOS (brew):  brew install python-tk" >&2
    exit 1
fi

if ! "$PY" -c "import PIL" >/dev/null 2>&1; then
    echo "AVVISO: Pillow non installato, anteprime disabilitate." >&2
    echo "        Installa con: $PY -m pip install -r requirements.txt" >&2
fi

exec "$PY" main.py "$@"
