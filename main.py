#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Rebranding Tool - Script di avvio principale.
SACE S.p.A
"""

import os
import sys
import traceback

MIN_PYTHON = (3, 10)


def _fatal(title: str, message: str) -> None:
    """Mostra un errore bloccante, con fallback su console se la GUI non è usabile."""
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(title, message)
        root.destroy()
    except Exception:
        print(f"{title}: {message}", file=sys.stderr)


def main() -> int:
    if sys.version_info < MIN_PYTHON:
        _fatal(
            "Versione Python non supportata",
            f"È richiesto Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} o superiore.\n"
            f"Versione rilevata: {sys.version.split()[0]}",
        )
        return 1

    try:
        import tkinter as tk
    except ImportError:
        # Su Linux tkinter è un pacchetto separato: senza questo messaggio
        # l'utente vedrebbe solo un ModuleNotFoundError.
        _fatal(
            "Componente mancante",
            "Il modulo tkinter non è disponibile.\n\n"
            "Windows: reinstalla Python selezionando «tcl/tk and IDLE».\n"
            "Linux:   sudo apt install python3-tk",
        )
        return 1

    try:
        from rebranding_tool import RebrandingToolApp

        root = tk.Tk()

        base = (os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
                else os.path.dirname(os.path.abspath(__file__)))
        icon_path = os.path.join(base, "sace.ico")
        if os.path.exists(icon_path):
            try:
                root.iconbitmap(icon_path)
            except Exception:
                pass  # formato icona non supportato su questa piattaforma

        RebrandingToolApp(root)
        root.mainloop()
        return 0

    except Exception as exc:
        _fatal(
            "Errore Critico",
            f"Errore irreversibile durante l'avvio:\n\n{exc}\n\n"
            f"{traceback.format_exc(limit=3)}",
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
