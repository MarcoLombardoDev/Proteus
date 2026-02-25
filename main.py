#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Rebranding Tool - Script di avvio principale.
SACE S.p.A
"""

import os
import sys


def main():
    """Funzione principale - avvio applicazione."""
    try:
        from rebranding_tool import RebrandingToolApp
        import tkinter as tk

        root = tk.Tk()

        # Icona app
        if getattr(sys, "frozen", False):
            base = os.path.dirname(sys.executable)
        else:
            base = os.path.dirname(os.path.abspath(__file__))

        icon_path = os.path.join(base, "sace.ico")
        if os.path.exists(icon_path):
            try:
                root.iconbitmap(icon_path)
            except Exception:
                pass

        app = RebrandingToolApp(root)
        root.mainloop()

    except Exception as e:
        try:
            import tkinter as tk
            from tkinter import messagebox
            err_root = tk.Tk()
            err_root.withdraw()
            messagebox.showerror(
                "Errore Critico",
                f"Errore irreversibile durante l'avvio:\n\n{str(e)}\n\nL'applicazione si chiuderà."
            )
            err_root.destroy()
        except Exception:
            print(f"ERRORE CRITICO DI AVVIO: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
