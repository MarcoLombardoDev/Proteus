#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Proteus - Rebranding Tool: application entry point.
"""

import os
import sys
import traceback

MIN_PYTHON = (3, 10)


def _hide_console_window() -> None:
    """
    Hide the console window that comes with launching a console-subsystem
    executable, when the GUI is what was actually asked for.

    The frozen build is a single .exe rather than one windowed binary plus a
    separate console one for the CLI: a --windowed executable has no console
    at all, so the CLI half would print into nothing. A --console executable
    solves that, but then double-clicking it for the GUI briefly shows a
    console window before this hides it — a visible trade-off for shipping
    one file instead of two, not a bug to chase away.

    A no-op anywhere this does not apply: unfrozen (running from source),
    non-Windows, or no console attached (already hidden, or launched from a
    parent that redirected the streams).
    """
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return
    try:
        import ctypes

        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            SW_HIDE = 0
            ctypes.windll.user32.ShowWindow(hwnd, SW_HIDE)
    except Exception:
        pass  # cosmetic only: a visible console must never block the GUI


def _fatal(title: str, message: str) -> None:
    """
    Show a blocking error, falling back to the console if the GUI is unusable.

    These messages stay in English: they fire before the settings (and hence
    the chosen language) can be loaded.
    """
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
    # Any argument means the caller wants the command line, not the window.
    # This keeps one entry point for both, so the packaged executable can serve
    # a scheduled job as well as a person.
    if len(sys.argv) > 1:
        from cli import entry_point
        return entry_point()

    _hide_console_window()

    if sys.version_info < MIN_PYTHON:
        _fatal(
            "Unsupported Python version",
            f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or newer is required.\n"
            f"Detected version: {sys.version.split()[0]}",
        )
        return 1

    try:
        import tkinter as tk
    except ImportError:
        # On Linux tkinter ships as a separate package: without this message the
        # user would only see a ModuleNotFoundError.
        _fatal(
            "Missing component",
            "The tkinter module is not available.\n\n"
            "Windows: reinstall Python with the \u00abtcl/tk and IDLE\u00bb option.\n"
            "Linux:   sudo apt install python3-tk\n"
            "macOS:   brew install python-tk",
        )
        return 1

    try:
        from rebranding_tool import RebrandingToolApp

        root = tk.Tk()

        base = (os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
                else os.path.dirname(os.path.abspath(__file__)))
        icon_path = os.path.join(base, "app.ico")
        if os.path.exists(icon_path):
            try:
                root.iconbitmap(icon_path)
            except Exception:
                pass  # icon format unsupported on this platform

        RebrandingToolApp(root)
        root.mainloop()
        return 0

    except Exception as exc:
        _fatal(
            "Critical error",
            f"Unrecoverable error during startup:\n\n{exc}\n\n"
            f"{traceback.format_exc(limit=3)}",
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
