#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Regenerate the README screenshots.

Boots the real application against synthetic sample data and captures one PNG
per tab. Nothing is faked: the windows below are the actual interface.

The script is deliberately side-effect free with respect to the machine it runs
on — the settings file, the log folder and the sample images all live in a
temporary directory that is removed on exit, so running it never touches your
real configuration.

Usage:
    xvfb-run -a python docs/generate_screenshots.py                 # English
    xvfb-run -a python docs/generate_screenshots.py --language it   # Italian
    SHOTDIR=/tmp/shots xvfb-run -a python docs/generate_screenshots.py

Requires `mss` for the screen capture:
    pip install mss
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

DEFAULT_SHOTDIR = os.path.join(PROJECT_ROOT, "docs", "screenshots")

#: Colours of the sample logos: the "old" ones being replaced and the "new"
#: ones coming from the source folder. Flat colour blocks keep the previews
#: readable and the repository free of any real brand asset.
OLD_COLOUR = (196, 62, 58)
NEW_COLOUR = (38, 92, 168)

#: One entry per screenshot: (file name, tab index, extra settle time).
SHOTS = (
    ("01_configuration", 0),
    ("02_scan_results", 1),
    ("03_matches", 2),
    ("04_replacement", 3),
)


def build_sample_tree(root: str) -> tuple[str, str]:
    """
    Create a small but representative folder tree.

    It intentionally covers every case the matcher has to grade: exact hits, a
    jpg/jpeg cross-match, an SVG whose size comes from the markup, a weak match
    and a file with no counterpart at all.
    """
    from PIL import Image

    scan = os.path.join(root, "share")
    source = os.path.join(root, "new_logos")

    def png(folder: str, name: str, size, colour):
        path = os.path.join(folder, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        Image.new("RGB", size, colour).save(path)

    def svg(folder: str, name: str, width: int, height: int):
        path = os.path.join(folder, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write('<svg xmlns="http://www.w3.org/2000/svg" '
                     f'width="{width}px" height="{height}px"/>')

    # Files to be replaced.
    png(scan, "website/logo_header.png", (240, 80), OLD_COLOUR)
    png(scan, "website/logo_footer.png", (120, 40), OLD_COLOUR)
    png(scan, "intranet/logo_small.png", (64, 64), OLD_COLOUR)   # weak match
    png(scan, "print/logo_press.jpg", (300, 100), OLD_COLOUR)    # jpg -> jpeg
    png(scan, "legacy/logo_orphan.gif", (50, 50), OLD_COLOUR)    # no match
    svg(scan, "web/logo_vector.svg", 500, 200)

    # New logos.
    png(source, "logo_header.png", (240, 80), NEW_COLOUR)
    png(source, "logo_footer.png", (120, 40), NEW_COLOUR)
    png(source, "logo_press.jpeg", (300, 100), NEW_COLOUR)
    svg(source, "logo_vector.svg", 500, 200)

    return scan, source


def capture(path: str) -> None:
    """Grab the whole virtual screen into `path`."""
    import mss
    from PIL import Image

    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[1])
        Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX").save(path)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--language", default="en",
                        help="interface language to capture (en, it)")
    parser.add_argument("--outdir", default=os.environ.get("SHOTDIR", DEFAULT_SHOTDIR),
                        help="destination folder for the PNG files")
    args = parser.parse_args(argv[1:])

    if not os.environ.get("DISPLAY") and os.name != "nt":
        print("No DISPLAY found. Run this under Xvfb:\n"
              "  xvfb-run -a python docs/generate_screenshots.py", file=sys.stderr)
        return 1

    try:
        import mss  # noqa: F401
    except ImportError:
        print("The 'mss' package is required: pip install mss", file=sys.stderr)
        return 1

    workdir = tempfile.mkdtemp(prefix="rebranding_shots_")
    try:
        import tkinter as tk

        import core
        import i18n

        # Redirect settings and logs into the throwaway folder *before* the
        # application reads them, so the real configuration is left alone.
        core.writable_app_dir = lambda sub: _ensure(os.path.join(workdir, sub))

        scan, source = build_sample_tree(workdir)
        core.save_settings({
            "language": args.language,
            "source_folder": source,
            "scan_folder": scan,
            "search_pattern": "logo*",
            "backup": True,
            "dry_run": False,
        })

        from rebranding_tool import RebrandingToolApp

        os.makedirs(args.outdir, exist_ok=True)

        root = tk.Tk()
        app = RebrandingToolApp(root)
        root.update()

        def settle(seconds: float = 0.6) -> None:
            """Pump the event loop, waiting out any running worker."""
            deadline = time.time() + max(seconds, 0.1)
            while app._busy() or time.time() < deadline:
                root.update()
                time.sleep(0.02)
                if time.time() > deadline + 30:
                    break
            for _ in range(6):
                root.update()
                time.sleep(0.03)

        # Walk the wizard exactly as a user would.
        settle()
        _shoot(app, root, args.outdir, "01_configuration", 0, settle)

        app._start_scan()
        settle(1.0)
        _shoot(app, root, args.outdir, "02_scan_results", 1, settle)

        app._start_matching()
        settle(1.0)
        rows = app._match_tree.get_children()
        if rows:
            # Select the weak match so both preview panes are populated.
            app._match_tree.selection_set(rows[0])
        settle()
        _shoot(app, root, args.outdir, "03_matches", 2, settle)

        _shoot(app, root, args.outdir, "04_replacement", 3, settle)

        print(f"{len(SHOTS)} screenshots written to {args.outdir} "
              f"(language: {i18n.get_language()})")
        root.destroy()
        return 0

    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _ensure(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def _shoot(app, root, outdir: str, name: str, tab: int, settle) -> None:
    app.notebook.select(tab)
    settle(0.4)
    capture(os.path.join(outdir, f"{name}.png"))
    print(f"  captured {name}.png")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
