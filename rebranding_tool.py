#!/usr/bin/env python
# Proteus — Rebranding Tool
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.
# A commercial licence, without the AGPL's obligations, is available for use
# in proprietary or closed-source products — see COMMERCIAL-LICENSE.md.

"""
Proteus - Rebranding Tool: bulk replacement of logo and graphic files.
Graphical user interface.

The application logic (scanning, matching, replacement) lives in `core.py` and
does not depend on tkinter: this module only deals with presentation.
"""

from __future__ import annotations

import datetime
import gc
import logging
import os
import re
import threading
import webbrowser
from collections import deque
from pathlib import Path
from urllib.parse import quote

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import core
import i18n
import office
import paths
from core import (
    APP_NAME,
    APP_TAGLINE,
    APP_VERSION,
    CONTACT_EMAIL,
    LICENSE_EMAIL_SUBJECT,
    LICENSE_NOTICE,
    FileInfo,
    Match,
    OperationCancelled,
)
from i18n import t

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    Image = ImageTk = None
    PIL_AVAILABLE = False

try:
    import ttkbootstrap as tb
    BOOTSTRAP_AVAILABLE = True
except Exception:  # pragma: no cover - environment dependent
    tb = None
    BOOTSTRAP_AVAILABLE = False


# ---------------------------------------------------------------------------
# Palette and styles
# ---------------------------------------------------------------------------

BRAND_BLUE = "#3365ae"

#: Button styles: (base colour, hover colour, pressed colour).
#: These are registered as our own ttk styles (`Primary.TButton`, ...) instead
#: of relying on ttkbootstrap's `bootstyle` option, which only exists on that
#: library's widgets and makes standard ttk widgets fail.
BUTTON_PALETTE = {
    "primary": (BRAND_BLUE, "#28508a", "#1e3c6a"),
    "success": ("#28a745", "#218838", "#1c7430"),
    "warning": ("#e08e0b", "#c47c09", "#a86a08"),
    "danger":  ("#d9534f", "#c33f3b", "#a83531"),
}

PROGRESS_STYLE = "Brand.Horizontal.TProgressbar"

#: Colour of the "needs attention" bar. Red rather than the orange used
#: for uncertain matches: an uncertain match is a judgement call, this is
#: work the tool could not do at all.
PROBLEM_COLOUR = "#c0392b"

PREVIEW_SIZE = (110, 80)
MATCH_PREVIEW_SIZE = (90, 70)

#: Columns sorted numerically rather than alphabetically.
NUMERIC_COLUMNS = {"#"}
#: Columns sorted by the real underlying value (weight, resolution).
SORT_KEY_COLUMNS = {"size", "dim", "sim", "target_dim", "src_dim"}

#: Upper bound on the in-memory log, kept so the language switch can rebuild
#: the interface without losing what the user has already seen.
LOG_BUFFER_SIZE = 2000



def set_window_icon(window) -> None:
    """Give a Tk window the application icon, whatever the platform.

    Two independent attempts, and the independence is the point. The first
    version tried ``iconbitmap`` on Windows and fell through to ``iconphoto``
    only on the other platforms, with one ``try`` around both -- so when
    ``iconbitmap`` raised, the fallback never ran and the window kept Tk's
    default feather. Which is what was reported: the .ico and the .png were
    both inside the executable and neither reached the window.

    So the PhotoImage goes on first, because it works everywhere and Tk has
    read PNG since 8.6, and ``iconbitmap`` is tried afterwards on Windows for
    the sharper small sizes. If that one fails, what the first set stays set;
    Tk raises before it changes anything, so a failure cannot undo it.

    The PhotoImage is kept on the window: Tk holds only a weak reference to
    it, and a garbage-collected image leaves a blank icon behind.

    Never raises. A missing icon is a cosmetic problem, and no cosmetic
    problem should be a reason the program does not start.
    """
    png = core.resource_path("app.png")
    if os.path.exists(png):
        try:
            window._app_icon = tk.PhotoImage(file=png)
            window.iconphoto(True, window._app_icon)
        except Exception:  # noqa: BLE001 — see the docstring
            pass

    if os.name == "nt":
        ico = core.resource_path("app.ico")
        if os.path.exists(ico):
            try:
                window.iconbitmap(ico)
            except Exception:  # noqa: BLE001 — iconphoto already did the job
                pass

class RebrandingToolApp:
    """Main Rebranding Tool application."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.logger = core.setup_logging()

        # --- State ---
        settings = core.load_settings()
        i18n.set_language(str(settings["language"]))

        self.source_folder = tk.StringVar(value=str(settings["source_folder"]))
        self.scan_folder = tk.StringVar(value=str(settings["scan_folder"]))
        self.search_pattern = tk.StringVar(value=str(settings["search_pattern"]))
        self._backup_var = tk.BooleanVar(value=bool(settings["backup"]))
        self._dry_run_var = tk.BooleanVar(value=bool(settings["dry_run"]))
        self._language_var = tk.StringVar(value=i18n.language_name(i18n.get_language()))
        self._search_mode = tk.StringVar(value=str(settings["search_mode"]))
        self._similarity_var = tk.IntVar(value=int(settings["similarity"]))
        self._references: list[str] = [r for r in settings["references"]
                                       if os.path.isfile(r)]
        self._include_office = tk.BooleanVar(value=bool(settings["include_office"]))
        self._include_pdf = tk.BooleanVar(value=bool(settings["include_pdf"]))

        #: Findings the scan could not deal with. Never dropped: whatever
        #: Proteus notices but cannot replace is put in front of the user, so a
        #: logo left behind is a decision rather than an accident.
        self._problems: list = []

        self.scanned_files: list[FileInfo] = []
        self.source_files: list[FileInfo] = []
        self.matches: list[Match] = []
        self._match_by_path: dict[str, Match] = {}

        # Thumbnails currently on screen, one per preview box.
        # See `_keep_image` for why they are not stored on the widgets.
        self._image_refs: dict[str, object] = {}

        # --- Concurrency ---
        # One long operation at a time; the event allows cancellation.
        self._ui_queue: list = []
        self._ui_lock = threading.Lock()
        self._cancel_event = threading.Event()
        self._worker: threading.Thread | None = None
        self._closing = False
        self._pump_after_id: str | None = None
        self._pending_progress: tuple[float, str] | None = None
        self._sort_state: dict[tuple[int, str], bool] = {}
        self._log_buffer: deque[str] = deque(maxlen=LOG_BUFFER_SIZE)

        self.progress_var = tk.DoubleVar(value=0)

        # --- Setup ---
        self._apply_window_chrome()
        self._apply_theme()
        # After the theme, not before: whatever a theme library does to the
        # root on the way in, it cannot undo an icon set after it.
        self._set_window_icon()
        self._create_widgets()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._pump_ui_queue()

        self.log(t("{app} {version} started.").format(app=APP_NAME,
                                                      version=APP_VERSION))
        if not PIL_AVAILABLE:
            self.log(t("Pillow is unavailable: image previews and resolutions "
                       "will not be shown."), logging.WARNING)

    # ------------------------------------------------------------------
    # Window setup
    # ------------------------------------------------------------------

    def _apply_window_chrome(self):
        self.root.title(f"{APP_NAME} - {APP_TAGLINE} {APP_VERSION}")
        self.root.geometry("1150x780")
        self.root.minsize(940, 660)

    def _set_window_icon(self):
        set_window_icon(self.root)

    def _apply_theme(self):
        """
        Apply the theme and register the button styles.

        ttkbootstrap is optional and used only for the base theme: every button
        uses a ttk style registered here, so the application also works without
        the library and with any version of it.
        """
        self.style: ttk.Style | None = None

        if BOOTSTRAP_AVAILABLE:
            try:
                self.style = tb.Style()
                # `flatly` only exists up to 2.x and is deprecated: try the
                # modern name first, so no warning is emitted and we do not
                # depend on a theme being removed.
                available = set(self.style.theme_names())
                for theme in ("bootstrap-light", "flatly", "litera", "cosmo"):
                    if theme in available:
                        self.style.theme_use(theme)
                        break
            except Exception:
                self.style = None

        if self.style is None:
            self.style = ttk.Style()
            if "clam" in self.style.theme_names():
                # 'clam' honours background/foreground on buttons; the native
                # Windows theme ("vista") would ignore them.
                try:
                    self.style.theme_use("clam")
                except tk.TclError:
                    pass

        for name, (base, hover, pressed) in BUTTON_PALETTE.items():
            style_name = f"{name.capitalize()}.TButton"
            self.style.configure(
                style_name,
                font=("Arial", 9, "bold"),
                background=base,
                foreground="white",
                bordercolor=base,
                focuscolor=base,
                borderwidth=0,
                padding=(10, 6),
            )
            self.style.map(
                style_name,
                background=[("disabled", "#b9c2cc"), ("pressed", pressed),
                            ("active", hover)],
                foreground=[("disabled", "#eeeeee"), ("active", "white")],
            )

        # Without explicit colours the bar is drawn white on a white trough:
        # technically working, but invisible.
        self.style.configure(
            PROGRESS_STYLE,
            troughcolor="#e6e9ee",
            bordercolor="#c9d0d8",
            background=BRAND_BLUE,
            lightcolor=BRAND_BLUE,
            darkcolor=BRAND_BLUE,
        )

        self.style.configure(
            "Outline.TButton",
            font=("Arial", 9),
            foreground=BRAND_BLUE,
            padding=(10, 6),
        )
        self.style.map(
            "Outline.TButton",
            foreground=[("disabled", "#999999"), ("active", "#1e3c6a")],
        )

    @staticmethod
    def btn(kind: str) -> dict:
        """Style options for a button ('primary', 'success', ..., 'outline')."""
        if kind == "outline" or kind not in BUTTON_PALETTE:
            return {"style": "Outline.TButton"}
        return {"style": f"{kind.capitalize()}.TButton"}

    # ------------------------------------------------------------------
    # Thread-safe UI updates
    # ------------------------------------------------------------------

    def _ui(self, fn):
        """Queue a callable to run on the main thread."""
        with self._ui_lock:
            self._ui_queue.append(fn)

    def _set_progress(self, value: float, text: str | None = None):
        """
        Record progress. Updates are coalesced and applied once per tick: over
        tens of thousands of files, queueing one callback per item would
        saturate the queue and freeze the UI.
        """
        self._pending_progress = (value, text or "")

    def _pump_ui_queue(self):
        if self._closing:
            return

        with self._ui_lock:
            pending, self._ui_queue = self._ui_queue, []

        for fn in pending:
            try:
                fn()
            except tk.TclError:
                return  # window destroyed while processing
            except Exception as exc:
                self.logger.error("UI update error: %s", exc)

        if self._pending_progress is not None:
            value, text = self._pending_progress
            self._pending_progress = None
            try:
                self.progress_var.set(value)
                if text:
                    self.status_label.config(text=text)
            except tk.TclError:
                return

        # The id lets us cancel the tick on shutdown: a pending after() on a
        # destroyed interpreter raises a background Tcl error.
        self._pump_after_id = self.root.after(80, self._pump_ui_queue)

    # ------------------------------------------------------------------
    # Log
    # ------------------------------------------------------------------

    def log(self, message: str, level: int = logging.INFO):
        self.logger.log(level, message)
        entry = f"[{datetime.datetime.now():%H:%M:%S}] {message}"
        self._log_buffer.append(entry)
        self._ui(lambda e=entry: self._append_log(e))

    def _append_log(self, entry: str):
        if not hasattr(self, "log_text"):
            return
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, entry + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _restore_log(self):
        """Repopulate the log widget from the buffer after a UI rebuild."""
        if not self._log_buffer or not hasattr(self, "log_text"):
            return
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, "\n".join(self._log_buffer) + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _status(self, msg: str):
        self._ui(lambda m=msg: self.status_label.config(text=m))

    # ------------------------------------------------------------------
    # Widget creation
    # ------------------------------------------------------------------

    def _create_widgets(self):
        # Both bottom bars must be packed *before* the notebook: in Tk whatever
        # comes first reserves its space, and a notebook with expand=True would
        # squeeze them until their contents are clipped. The footer goes first so
        # it ends up below the status bar.
        self._build_footer()
        self._build_status_bar()

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        ttk.Label(
            self.root,
            text=t("VERSION {version}").format(version=APP_VERSION),
            font=("Arial", 8),
            foreground="#888888",
        ).place(relx=1.0, y=10, anchor=tk.NE, x=-12)

        self._frame_config = ttk.Frame(self.notebook)
        self.notebook.add(self._frame_config, text=t("  ① CONFIGURATION  "))

        self._frame_scan = ttk.Frame(self.notebook)
        self.notebook.add(self._frame_scan, text=t("  ② SCAN RESULTS  "))

        self._frame_match = ttk.Frame(self.notebook)
        self.notebook.add(self._frame_match, text=t("  ③ MATCHES  "))

        self._frame_replace = ttk.Frame(self.notebook)
        self.notebook.add(self._frame_replace, text=t("  ④ REPLACEMENT  "))

        self._build_config_tab(self._frame_config)
        self._build_scan_tab(self._frame_scan)
        self._build_match_tab(self._frame_match)
        self._build_replace_tab(self._frame_replace)

        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    def _build_footer(self):
        """
        Fixed licence notice along the bottom of the window.

        Deliberately not translated: it is a legal notice rather than interface
        copy, and showing it is how the application meets the "Appropriate
        Legal Notices" requirement of AGPL-3.0 section 5.

        The licensing address is a separate, clickable label rather than part
        of the notice: the person running the application is the one who might
        need to buy a commercial licence, and telling them it is "available"
        without saying where to ask wastes the only place they will look.
        """
        footer = ttk.Frame(self.root)
        footer.pack(fill=tk.X, side=tk.BOTTOM, padx=8, pady=(0, 4))

        # Centred as a pair: packing both into the full width would push the
        # address to the far edge, away from the sentence introducing it.
        centre = ttk.Frame(footer)
        centre.pack(anchor=tk.CENTER)

        self._footer_label = ttk.Label(
            centre,
            text=LICENSE_NOTICE,
            font=("Arial", 8),
            foreground="#8a94a0",
        )
        self._footer_label.pack(side=tk.LEFT)

        self._footer_email = ttk.Label(
            centre,
            text=CONTACT_EMAIL,
            font=("Arial", 8, "underline"),
            foreground=BRAND_BLUE,
            cursor="hand2",
        )
        self._footer_email.pack(side=tk.LEFT, padx=(4, 0))
        self._footer_email.bind("<Button-1>", self._open_licensing_email)

    def _open_licensing_email(self, _event=None):
        """Open the mail client on a commercial licensing enquiry."""
        subject = quote(LICENSE_EMAIL_SUBJECT)
        try:
            webbrowser.open(f"mailto:{CONTACT_EMAIL}?subject={subject}")
        except Exception as exc:
            # No mail client configured, or none reachable. Not worth a dialog:
            # the address is legible on screen and can be copied by hand.
            self.log(t("Could not open the mail client: {error}").format(error=exc),
                     level=logging.WARNING)

    def _build_status_bar(self):
        status_bar = ttk.Frame(self.root, relief=tk.SUNKEN)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM, padx=8, pady=(0, 6))

        self.status_label = ttk.Label(status_bar, text=t("Ready"), anchor=tk.W)
        self.status_label.pack(side=tk.LEFT, padx=6)

        self._btn_cancel = ttk.Button(
            status_bar, text=t("Cancel"), width=10,
            command=self._request_cancel, state=tk.DISABLED, **self.btn("outline"),
        )
        self._btn_cancel.pack(side=tk.RIGHT, padx=6, pady=2)

        # The progressbar used to exist only as a variable: with no widget
        # bound to it, progress was not visible anywhere.
        self._progress = ttk.Progressbar(
            status_bar, variable=self.progress_var, maximum=100,
            length=240, mode="determinate", style=PROGRESS_STYLE,
        )
        self._progress.pack(side=tk.RIGHT, padx=6, pady=2)

    # ------------------------------------------------------------------
    # TAB 1 - CONFIGURATION
    # ------------------------------------------------------------------

    def _build_config_tab(self, parent: ttk.Frame):
        top = ttk.Frame(parent)
        top.pack(fill=tk.X, padx=8, pady=(12, 4))
        ttk.Label(top, text=t("Search Configuration"),
                  font=("Arial", 13, "bold")).pack(side=tk.LEFT, padx=16)

        # Language picker: kept next to the title so it is discoverable
        # without hunting through a settings dialog.
        lang_box = ttk.Frame(top)
        lang_box.pack(side=tk.RIGHT, padx=16)
        ttk.Label(lang_box, text=t("Language:"), font=("Arial", 9)).pack(side=tk.LEFT,
                                                                        padx=(0, 4))
        self._language_combo = ttk.Combobox(
            lang_box, textvariable=self._language_var, state="readonly",
            values=list(i18n.LANGUAGES.values()), width=12,
        )
        self._language_combo.pack(side=tk.LEFT)
        self._language_combo.bind("<<ComboboxSelected>>", self._on_language_selected)

        ttk.Label(
            parent,
            text=t("Set the folders and the search key, then start the scan."),
            font=("Arial", 10), foreground="#666666",
        ).pack(anchor=tk.W, padx=24, pady=(0, 16))

        # --- Source folder ---
        src_frame = ttk.LabelFrame(parent, text=t(" SOURCE FOLDER (new logos) "))
        src_frame.pack(fill=tk.X, padx=24, pady=6)
        ttk.Label(
            src_frame,
            text=t("Folder holding the new logo files (the replacement source):"),
            font=("Arial", 9), foreground="#555555",
        ).grid(row=0, column=0, columnspan=3, sticky=tk.W, padx=8, pady=(8, 2))
        ttk.Label(src_frame, text=t("Path:")).grid(row=1, column=0, sticky=tk.W,
                                                   padx=8, pady=4)
        self._entry_source = ttk.Entry(src_frame, textvariable=self.source_folder,
                                       width=68)
        self._entry_source.grid(row=1, column=1, padx=4, pady=4, sticky=tk.EW)
        ttk.Button(src_frame, text=t("Browse..."), command=self._browse_source_folder,
                   **self.btn("outline")).grid(row=1, column=2, padx=8, pady=4)
        src_frame.columnconfigure(1, weight=1)

        # --- Folder to scan ---
        scan_frame = ttk.LabelFrame(parent, text=t(" FOLDER TO SCAN "))
        scan_frame.pack(fill=tk.X, padx=24, pady=6)
        ttk.Label(
            scan_frame,
            text=t("Folder (and subfolders) to search for the files to replace "
                   "(e.g. a server or network share):"),
            font=("Arial", 9), foreground="#555555",
        ).grid(row=0, column=0, columnspan=3, sticky=tk.W, padx=8, pady=(8, 2))
        ttk.Label(scan_frame, text=t("Path:")).grid(row=1, column=0, sticky=tk.W,
                                                    padx=8, pady=4)
        self._entry_scan = ttk.Entry(scan_frame, textvariable=self.scan_folder, width=68)
        self._entry_scan.grid(row=1, column=1, padx=4, pady=4, sticky=tk.EW)
        ttk.Button(scan_frame, text=t("Browse..."), command=self._browse_scan_folder,
                   **self.btn("outline")).grid(row=1, column=2, padx=8, pady=4)
        scan_frame.columnconfigure(1, weight=1)

        # --- Search key ---
        key_frame = ttk.LabelFrame(parent, text=t(" SEARCH KEY "))
        key_frame.pack(fill=tk.X, padx=24, pady=6)
        ttk.Label(
            key_frame,
            text=t("Wildcard pattern (* = many characters, ? = one character). "
                   "Separate multiple patterns with «;».\n"
                   "Examples: logo*.png  |  banner_*.jpg  |  icon_??.svg  |  "
                   "logo*.png; logo*.svg"),
            font=("Arial", 9), foreground="#555555", justify=tk.LEFT,
        ).grid(row=0, column=0, columnspan=3, sticky=tk.W, padx=8, pady=(8, 2))
        mode_row = ttk.Frame(key_frame)
        mode_row.grid(row=1, column=0, columnspan=3, sticky=tk.W, padx=8, pady=(2, 4))
        ttk.Label(mode_row, text=t("Search by:")).pack(side=tk.LEFT, padx=(0, 8))
        for value, label in (("name", t("File name")), ("content", t("Image content"))):
            ttk.Radiobutton(mode_row, text=label, value=value,
                            variable=self._search_mode,
                            command=self._on_search_mode_changed).pack(side=tk.LEFT,
                                                                      padx=(0, 12))

        ttk.Label(key_frame, text=t("Pattern:")).grid(row=2, column=0, sticky=tk.W,
                                                      padx=8, pady=4)
        self._entry_pattern = ttk.Entry(key_frame, textvariable=self.search_pattern,
                                        width=40)
        self._entry_pattern.grid(row=2, column=1, padx=4, pady=4, sticky=tk.W)
        self._entry_pattern.bind("<Return>", lambda _e: self._start_scan())

        ttk.Label(
            key_frame,
            text=t("Find images that look like the reference ones, whatever they "
                   "are called.\n"
                   "Raster formats only: SVG, PDF and EPS cannot be matched by "
                   "content."),
            font=("Arial", 9), foreground="#555555", justify=tk.LEFT,
        ).grid(row=3, column=0, columnspan=3, sticky=tk.W, padx=8, pady=(6, 2))

        ttk.Label(key_frame, text=t("Reference images:")).grid(row=4, column=0,
                                                               sticky=tk.W, padx=8,
                                                               pady=4)
        ref_row = ttk.Frame(key_frame)
        ref_row.grid(row=4, column=1, columnspan=2, sticky=tk.EW, padx=4, pady=4)
        self._btn_references = ttk.Button(ref_row, text=t("Choose images..."),
                                          command=self._choose_references,
                                          **self.btn("outline"))
        self._btn_references.pack(side=tk.LEFT)
        self._references_label = ttk.Label(ref_row, text="", font=("Arial", 9),
                                           foreground="#555555")
        self._references_label.pack(side=tk.LEFT, padx=10)

        ttk.Label(key_frame, text=t("Minimum similarity:")).grid(row=5, column=0,
                                                                 sticky=tk.W, padx=8,
                                                                 pady=4)
        sim_row = ttk.Frame(key_frame)
        sim_row.grid(row=5, column=1, sticky=tk.W, padx=4, pady=4)
        self._similarity_spin = ttk.Spinbox(sim_row, from_=70, to=100, increment=1,
                                            width=5, textvariable=self._similarity_var)
        self._similarity_spin.pack(side=tk.LEFT)
        ttk.Label(sim_row, text="%").pack(side=tk.LEFT, padx=(2, 0))

        ttk.Checkbutton(
            key_frame,
            text=t("Also look inside Office documents (.docx, .pptx, .xlsx)"),
            variable=self._include_office,
        ).grid(row=6, column=0, columnspan=3, sticky=tk.W, padx=8, pady=(6, 2))

        ttk.Checkbutton(
            key_frame,
            text=t("Also look inside PDF files (raster images only)"),
            variable=self._include_pdf,
        ).grid(row=7, column=0, columnspan=3, sticky=tk.W, padx=8, pady=(0, 4))

        key_frame.columnconfigure(1, weight=1)
        self._refresh_references_label()
        self._on_search_mode_changed()

        if not PIL_AVAILABLE:
            warn = ttk.Frame(parent)
            warn.pack(fill=tk.X, padx=24, pady=4)
            ttk.Label(
                warn,
                text=t("⚠️  Pillow (PIL) is not installed: previews and resolutions "
                       "will be unavailable. Install it with: pip install pillow"),
                font=("Arial", 9), foreground="#cc6600",
            ).pack(anchor=tk.W)

        # --- Buttons ---
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=24, pady=20)

        self._btn_scan = ttk.Button(
            btn_frame, text=t("🔍  START SCAN"), command=self._start_scan,
            width=26, **self.btn("success"),
        )
        self._btn_scan.pack(side=tk.RIGHT, padx=4)

        ttk.Button(btn_frame, text=t("Clear fields"), command=self._clear_fields,
                   **self.btn("outline")).pack(side=tk.RIGHT, padx=4)

        ttk.Button(btn_frame, text=t("Open log folder"), command=self._open_log_folder,
                   **self.btn("outline")).pack(side=tk.LEFT, padx=4)

    def _searching_by_content(self) -> bool:
        return self._search_mode.get() == "content"

    def _on_search_mode_changed(self):
        """Enable only the controls belonging to the selected search mode."""
        by_content = self._searching_by_content()
        for widget in (self._btn_references, self._similarity_spin):
            widget.config(state=tk.NORMAL if by_content else tk.DISABLED)
        self._references_label.config(
            foreground="#555555" if by_content else "#aaaaaa")

    def _choose_references(self):
        chosen = filedialog.askopenfilenames(
            title=t("Select the old logo, in one or more versions"),
            filetypes=[("Images", "*.png *.jpg *.jpeg *.gif *.bmp *.tif *.tiff "
                                  "*.webp *.ico"),
                       ("All files", "*.*")],
        )
        if chosen:
            self._references = list(chosen)
            self._refresh_references_label()

    def _refresh_references_label(self):
        if not self._references:
            self._references_label.config(text=t("No reference image chosen"))
            return
        names = ", ".join(os.path.basename(r) for r in self._references[:3])
        if len(self._references) > 3:
            names += ", ..."
        self._references_label.config(
            text=t("{count} chosen: {names}").format(count=len(self._references),
                                                     names=names))

    # ------------------------------------------------------------------
    # TAB 2 - SCAN RESULTS
    # ------------------------------------------------------------------

    def _build_scan_tab(self, parent: ttk.Frame):
        top = ttk.Frame(parent)
        top.pack(fill=tk.X, padx=8, pady=(12, 4))
        ttk.Label(top, text=t("Scan Results"),
                  font=("Arial", 13, "bold")).pack(side=tk.LEFT)
        self._scan_count_lbl = ttk.Label(top, text=t("No scan performed yet"),
                                         foreground="#888888")
        self._scan_count_lbl.pack(side=tk.RIGHT, padx=8)

        ttk.Label(
            parent,
            text=t("Review the files found, then start the match analysis. "
                   "Double-click a row to open its containing folder."),
            font=("Arial", 10), foreground="#666666",
        ).pack(anchor=tk.W, padx=8, pady=(0, 10))

        # Findings the scan could not handle. Packed before the expanding tree
        # so it reserves its space, and left un-packed until there is something
        # to report — an empty warning bar teaches people to ignore the real one.
        self._problem_bar = ttk.Frame(parent)
        self._problem_lbl = ttk.Label(self._problem_bar, text="",
                                      foreground=PROBLEM_COLOUR,
                                      font=("Arial", 9, "bold"))
        self._problem_lbl.pack(side=tk.LEFT, padx=8)
        self._btn_problems = ttk.Button(
            self._problem_bar, text=t("Show details"),
            command=self._show_problems, **self.btn("outline"))
        self._btn_problems.pack(side=tk.RIGHT, padx=8)

        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        columns = ("#", "name", "ext", "size", "dim", "sim", "path")
        self._scan_tree = ttk.Treeview(tree_frame, columns=columns, show="headings",
                                       height=12, selectmode="extended")
        headers = {
            "#":    ("#", 46),
            "name": (t("File Name"), 180),
            "ext":  (t("Format"), 70),
            "size": (t("Size"), 100),
            "dim":  (t("Resolution"), 120),
            "sim":  (t("Similarity"), 90),
            "path": (t("Full Path"), 420),
        }
        for col, (label, width) in headers.items():
            self._scan_tree.heading(
                col, text=label,
                command=lambda c=col: self._sort_tree(self._scan_tree, c),
            )
            self._scan_tree.column(col, width=width, minwidth=60)

        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self._scan_tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL,
                            command=self._scan_tree.xview)
        self._scan_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self._scan_tree.grid(row=0, column=0, sticky=tk.NSEW)
        vsb.grid(row=0, column=1, sticky=tk.NS)
        hsb.grid(row=1, column=0, sticky=tk.EW)
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        # A content hit below the confident threshold is the one case where the
        # tool could overwrite an unrelated image, so it is coloured for review.
        self._scan_tree.tag_configure("review", foreground="#b06a00")

        self._scan_tree.bind("<<TreeviewSelect>>", self._on_scan_select)
        self._scan_tree.bind("<Double-1>", self._on_scan_double_click)

        preview_outer = ttk.LabelFrame(parent, text=t(" Preview "))
        preview_outer.pack(fill=tk.X, padx=8, pady=4)
        self._preview_canvas = tk.Canvas(preview_outer, width=120, height=90,
                                         bg="#f5f5f5", highlightthickness=1,
                                         highlightbackground="#cccccc")
        self._preview_canvas.pack(side=tk.LEFT, padx=8, pady=6)
        self._preview_info = ttk.Label(preview_outer, text=t("Select a file to preview it"),
                                       font=("Arial", 9), foreground="#888888",
                                       justify=tk.LEFT)
        self._preview_info.pack(side=tk.LEFT, padx=12, pady=6, anchor=tk.W)

        legend = ttk.Frame(parent)
        legend.pack(fill=tk.X, padx=8, pady=(2, 0))
        ttk.Label(legend,
                  text=t("orange = found by content, below the confident threshold"),
                  font=("Arial", 8), foreground="#888888").pack(side=tk.LEFT)

        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, padx=8, pady=8)

        self._btn_match = ttk.Button(
            btn_frame, text=t("🔗  FIND MATCHES"), command=self._start_matching,
            width=32, **self.btn("primary"),
        )
        self._btn_match.pack(side=tk.RIGHT, padx=4)

        ttk.Button(btn_frame, text=t("← Back to Configuration"),
                   command=lambda: self.notebook.select(0),
                   **self.btn("outline")).pack(side=tk.LEFT, padx=4)

    # ------------------------------------------------------------------
    # TAB 3 - MATCHES
    # ------------------------------------------------------------------

    def _build_match_tab(self, parent: ttk.Frame):
        top = ttk.Frame(parent)
        top.pack(fill=tk.X, padx=8, pady=(12, 4))
        ttk.Label(top, text=t("Proposed Matches"),
                  font=("Arial", 13, "bold")).pack(side=tk.LEFT)
        self._match_count_lbl = ttk.Label(top, text="", foreground="#888888")
        self._match_count_lbl.pack(side=tk.RIGHT, padx=8)

        ttk.Label(
            parent,
            text=t("Each file found is paired with the most suitable source "
                   "(same format, closest resolution, most similar name).\n"
                   "Click the ✓ column or press space to include/exclude a row; "
                   "double-click to pick a different source."),
            font=("Arial", 9), foreground="#555555", justify=tk.LEFT,
        ).pack(anchor=tk.W, padx=8, pady=(0, 6))

        mf = ttk.Frame(parent)
        mf.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        columns = ("#", "chk", "target_name", "target_fmt", "target_dim",
                   "src_name", "src_dim", "quality", "target_path")
        self._match_tree = ttk.Treeview(mf, columns=columns, show="headings",
                                        height=14, selectmode="browse")
        headers = {
            "#":           ("#", 46),
            "chk":         ("✓", 34),
            "target_name": (t("File to Replace"), 185),
            "target_fmt":  (t("Format"), 70),
            "target_dim":  (t("Target Resolution"), 130),
            "src_name":    (t("New Source File"), 185),
            "src_dim":     (t("Source Resolution"), 130),
            "quality":     (t("Quality"), 80),
            "target_path": (t("Target Path"), 340),
        }
        for col, (label, width) in headers.items():
            self._match_tree.heading(
                col, text=label,
                command=lambda c=col: self._sort_tree(self._match_tree, c),
            )
            self._match_tree.column(col, width=width, minwidth=30)

        mvsb = ttk.Scrollbar(mf, orient=tk.VERTICAL, command=self._match_tree.yview)
        mhsb = ttk.Scrollbar(mf, orient=tk.HORIZONTAL, command=self._match_tree.xview)
        self._match_tree.configure(yscrollcommand=mvsb.set, xscrollcommand=mhsb.set)
        self._match_tree.grid(row=0, column=0, sticky=tk.NSEW)
        mvsb.grid(row=0, column=1, sticky=tk.NS)
        mhsb.grid(row=1, column=0, sticky=tk.EW)
        mf.rowconfigure(0, weight=1)
        mf.columnconfigure(0, weight=1)

        self._match_tree.tag_configure("no_match", foreground="#cc4444")
        self._match_tree.tag_configure("matched", foreground="#226622")
        self._match_tree.tag_configure("disabled", foreground="#aaaaaa")
        self._match_tree.tag_configure("weak", foreground="#b06a00")

        # The toggle only fires on the ✓ column (or with the space bar):
        # previously any click inverted the row, making it impossible to select
        # one just to look at its preview.
        self._match_tree.bind("<Button-1>", self._on_match_click)
        self._match_tree.bind("<Double-1>", self._on_match_double_click)
        self._match_tree.bind("<space>", self._on_match_space)
        self._match_tree.bind("<<TreeviewSelect>>", self._on_match_select)

        preview_outer = ttk.Frame(parent)
        preview_outer.pack(fill=tk.X, padx=8, pady=4)

        target_box = ttk.LabelFrame(preview_outer, text=t(" Original Logo "))
        target_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 4))
        self._target_canvas = tk.Canvas(target_box, width=90, height=70, bg="#f5f5f5",
                                        highlightthickness=1)
        self._target_canvas.pack(side=tk.LEFT, padx=6, pady=4)
        self._target_preview_info = ttk.Label(target_box, text=t("Select a row"),
                                              font=("Arial", 8), justify=tk.LEFT)
        self._target_preview_info.pack(side=tk.LEFT, padx=6, pady=4, anchor=tk.W)

        ttk.Label(preview_outer, text="➜", font=("Arial", 20),
                  foreground=BRAND_BLUE).pack(side=tk.LEFT, padx=4)

        src_box = ttk.LabelFrame(preview_outer, text=t(" Proposed New Logo "))
        src_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(4, 0))
        self._src_canvas = tk.Canvas(src_box, width=90, height=70, bg="#f5f5f5",
                                     highlightthickness=1)
        self._src_canvas.pack(side=tk.LEFT, padx=6, pady=4)
        self._src_preview_info = ttk.Label(src_box, text=t("Select a row"),
                                           font=("Arial", 8), justify=tk.LEFT)
        self._src_preview_info.pack(side=tk.LEFT, padx=6, pady=4, anchor=tk.W)

        leg = ttk.Frame(parent)
        leg.pack(fill=tk.X, padx=8, pady=2)
        ttk.Label(leg, text=t("✓ = included   ✗ = excluded   red = no match   "
                              "orange = weak match, worth checking"),
                  font=("Arial", 8), foreground="#888888").pack(side=tk.LEFT)

        btn_f = ttk.Frame(parent)
        btn_f.pack(fill=tk.X, padx=8, pady=8)

        ttk.Button(btn_f, text=t("Select all"), command=self._select_all_matches,
                   **self.btn("outline")).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_f, text=t("Deselect all"), command=self._deselect_all_matches,
                   **self.btn("outline")).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_f, text=t("Export CSV"), command=self._export_matches,
                   **self.btn("outline")).pack(side=tk.LEFT, padx=4)

        ttk.Button(btn_f, text=t("✅  PROCEED WITH REPLACEMENT"),
                   command=self._go_to_replace,
                   width=34, **self.btn("warning")).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btn_f, text=t("← Back to Results"),
                   command=lambda: self.notebook.select(1),
                   **self.btn("outline")).pack(side=tk.RIGHT, padx=4)

    # ------------------------------------------------------------------
    # TAB 4 - REPLACEMENT
    # ------------------------------------------------------------------

    def _build_replace_tab(self, parent: ttk.Frame):
        top = ttk.Frame(parent)
        top.pack(fill=tk.X, padx=8, pady=(12, 4))
        ttk.Label(top, text=t("File Replacement"),
                  font=("Arial", 13, "bold")).pack(side=tk.LEFT, padx=16)

        ttk.Label(
            parent,
            text=t("The files selected in the previous tab will be overwritten "
                   "with their matching source files.\n"
                   "With backup enabled the operation can be undone from "
                   "«Restore backups»."),
            font=("Arial", 10), foreground="#666666",
        ).pack(anchor=tk.W, padx=24, pady=(0, 14))

        summary = ttk.LabelFrame(parent, text=t(" Operation summary "))
        summary.pack(fill=tk.X, padx=24, pady=6)
        self._replace_summary_lbl = ttk.Label(summary, text=t("No operation pending."),
                                              font=("Arial", 10), justify=tk.LEFT)
        self._replace_summary_lbl.pack(padx=12, pady=10, anchor=tk.W)

        opts = ttk.Frame(parent)
        opts.pack(fill=tk.X, padx=24, pady=4)
        ttk.Checkbutton(
            opts,
            text=t("Back up the original files before overwriting (.bak suffix)"),
            variable=self._backup_var, command=self._refresh_replace_summary,
        ).pack(anchor=tk.W)
        ttk.Checkbutton(
            opts,
            text=t("Dry run: performs every check without modifying any file"),
            variable=self._dry_run_var, command=self._refresh_replace_summary,
        ).pack(anchor=tk.W)

        log_frame = ttk.LabelFrame(parent, text=t(" Operation log "))
        log_frame.pack(fill=tk.BOTH, expand=True, padx=24, pady=6)
        self.log_text = tk.Text(log_frame, height=12, wrap=tk.WORD, font=("Courier", 9),
                                state=tk.DISABLED, bg="#fafafa")
        log_vsb = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_vsb.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=4)
        log_vsb.pack(side=tk.RIGHT, fill=tk.Y, pady=4)

        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, padx=24, pady=10)

        self._btn_execute = ttk.Button(
            btn_frame, text=t("⚡  RUN REPLACEMENT"), command=self._execute_replacement,
            width=28, **self.btn("danger"),
        )
        self._btn_execute.pack(side=tk.RIGHT, padx=4)

        ttk.Button(btn_frame, text=t("← Back to Matches"),
                   command=lambda: self.notebook.select(2),
                   **self.btn("outline")).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text=t("Clear log"), command=self._clear_log,
                   **self.btn("outline")).pack(side=tk.LEFT, padx=4)
        self._btn_restore = ttk.Button(
            btn_frame, text=t("↩  Restore backups"), command=self._restore_backups,
            **self.btn("outline"),
        )
        self._btn_restore.pack(side=tk.LEFT, padx=4)

    # ------------------------------------------------------------------
    # Language
    # ------------------------------------------------------------------

    def _on_language_selected(self, _event=None):
        self._change_language(i18n.code_for_name(self._language_var.get()))

    def _change_language(self, code: str):
        """Switch language and rebuild the interface in place."""
        if code == i18n.get_language():
            return
        if self._busy():
            # Rebuilding while a worker is publishing updates would destroy the
            # widgets its queued callbacks are about to touch.
            messagebox.showinfo(t("Operation in progress"),
                                t("Wait for the current operation to finish."))
            self._language_var.set(i18n.language_name(i18n.get_language()))
            return

        i18n.set_language(code)
        self._save_settings()
        self._rebuild_ui()
        self.log(t("Language changed to {language}.").format(
            language=i18n.language_name(code)))

    def _rebuild_ui(self):
        """
        Recreate every widget in the newly selected language.

        Rebuilding is preferred over updating each label one by one: the tables
        and previews are repopulated from the data already in memory, so there
        is a single code path producing the interface and no risk of a label
        being forgotten.
        """
        current_tab = 0
        try:
            current_tab = self.notebook.index("current")
        except tk.TclError:
            pass

        self._release_images()
        for child in list(self.root.winfo_children()):
            child.destroy()

        self._create_widgets()
        self._restore_log()

        if self.scanned_files:
            self._populate_scan_tree(announce=False)
        if self.matches:
            self._populate_match_tree()

        try:
            self.notebook.select(current_tab)
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Background operations
    # ------------------------------------------------------------------

    def _busy(self) -> bool:
        return self._worker is not None and self._worker.is_alive()

    def _start_worker(self, target, args=(), status: str = ""):
        """Start a long operation, preventing concurrent runs."""
        if self._busy():
            messagebox.showinfo(t("Operation in progress"),
                                t("Wait for the current operation to finish."))
            return False

        self._cancel_event.clear()
        self._set_action_buttons(tk.DISABLED)
        self._btn_cancel.config(state=tk.NORMAL)
        self.progress_var.set(0)
        self._status(status)

        # Flush any pending cyclic garbage here, on the main thread, then pause
        # the collector while the worker runs.
        #
        # A Tk thumbnail's destructor calls into the Tcl interpreter. If the
        # collector finalises one while running on a worker thread (it can fire
        # on any allocation, anywhere), that call arrives from outside the main
        # thread and freezes the application. With the collector paused, the
        # only finalisations left are reference-counted ones, which happen on
        # the thread that releases the object.
        gc.collect()
        gc.disable()

        def runner():
            try:
                target(*args)
            except OperationCancelled:
                self.log(t("Operation cancelled by the user."), logging.WARNING)
                self._status(t("Operation cancelled."))
            except Exception as exc:
                self.logger.exception("Background operation failed")
                self.log(t("Error: {error}").format(error=exc), logging.ERROR)
                self._ui(lambda e=exc: messagebox.showerror(t("Error"), str(e)))
                self._status(t("Operation failed with an error."))
            finally:
                self._ui(self._worker_finished)

        self._worker = threading.Thread(target=runner, daemon=True)
        self._worker.start()
        return True

    def _worker_finished(self):
        # Resume the collector and reclaim, here on the main thread, everything
        # that accumulated during the operation.
        gc.enable()
        gc.collect()
        self._set_action_buttons(tk.NORMAL)
        self._btn_cancel.config(state=tk.DISABLED)

    def _set_action_buttons(self, state):
        for btn in (self._btn_scan, self._btn_match, self._btn_execute,
                    self._btn_restore):
            try:
                btn.config(state=state)
            except tk.TclError:
                pass

    def _request_cancel(self):
        if self._busy():
            self._cancel_event.set()
            self._status(t("Cancelling..."))

    def _on_close(self):
        if self._busy():
            if not messagebox.askyesno(
                t("Operation in progress"),
                t("An operation is still running.\nQuit anyway?"),
            ):
                return
            self._cancel_event.set()

        self._closing = True
        self._save_settings()
        gc.enable()   # never leave it paused if we exit mid-operation

        if self._pump_after_id is not None:
            try:
                self.root.after_cancel(self._pump_after_id)
            except tk.TclError:
                pass
            self._pump_after_id = None

        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _save_settings(self):
        core.save_settings({
            "language": i18n.get_language(),
            "source_folder": self.source_folder.get().strip(),
            "scan_folder": self.scan_folder.get().strip(),
            "search_pattern": self.search_pattern.get().strip(),
            "search_mode": self._search_mode.get(),
            "references": list(self._references),
            "similarity": int(self._similarity_var.get()),
            "include_office": self._include_office.get(),
            "include_pdf": self._include_pdf.get(),
            "backup": self._backup_var.get(),
            "dry_run": self._dry_run_var.get(),
        })

    # ------------------------------------------------------------------
    # Configuration actions
    # ------------------------------------------------------------------

    def _browse_source_folder(self):
        folder = filedialog.askdirectory(
            title=t("Select source folder (new logos)"),
            initialdir=self.source_folder.get() or None,
        )
        if folder:
            self.source_folder.set(folder)

    def _browse_scan_folder(self):
        folder = filedialog.askdirectory(
            title=t("Select folder to scan"),
            initialdir=self.scan_folder.get() or None,
        )
        if folder:
            self.scan_folder.set(folder)

    def _clear_fields(self):
        self.source_folder.set("")
        self.scan_folder.set("")
        self.search_pattern.set("logo*.png")

    def _open_log_folder(self):
        self._open_in_file_manager(core.writable_app_dir("logs"))

    def _open_in_file_manager(self, path: str):
        try:
            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                webbrowser.open(Path(path).as_uri())
        except Exception as exc:
            messagebox.showinfo(
                t("Path"),
                t("{path}\n\n(Could not open it automatically: {error})").format(
                    path=path, error=exc),
            )

    # ------------------------------------------------------------------
    # Scan
    # ------------------------------------------------------------------

    def _start_scan(self):
        source = self.source_folder.get().strip()
        scan = self.scan_folder.get().strip()
        pattern = self.search_pattern.get().strip()

        problems = core.validate_config(source, scan, pattern,
                                        require_pattern=not self._searching_by_content())
        if self._searching_by_content():
            problems += core.validate_references(self._references)
        if problems:
            messagebox.showerror(t("Invalid configuration"), "\n\n".join(problems))
            return

        for warning in core.config_warnings(source, scan):
            self.log(t("Warning: {message}").format(message=warning), logging.WARNING)

        self._save_settings()
        self.scanned_files = []
        self.source_files = []
        self.matches = []
        self._match_by_path = {}
        self._clear_tree(self._scan_tree)
        self._clear_tree(self._match_tree)
        self._clear_previews()
        self._scan_count_lbl.config(text=t("Scanning..."))
        self._match_count_lbl.config(text="")
        self.notebook.select(1)

        self._start_worker(
            self._scan_worker,
            (source, scan, pattern, self._searching_by_content(),
             list(self._references), int(self._similarity_var.get()),
             self._include_office.get(), self._include_pdf.get()),
            t("Scanning..."),
        )

    def _scan_worker(self, source: str, scan: str, pattern: str,
                     by_content: bool, references: list[str], threshold: int,
                     include_office: bool = False, include_pdf: bool = False):
        self._problems = []
        if by_content:
            self.log(t("Content search started — folder: {folder} | "
                       "references: {count} | threshold: {threshold}%").format(
                folder=scan, count=len(references), threshold=threshold))
        else:
            self.log(t("Scan started — folder: {folder} | pattern: {pattern}").format(
                folder=scan, pattern=pattern))
        self.log(t("Source logo folder: {folder}").format(folder=source))

        def walk_error(path: str, exc: Exception):
            """
            A folder the scan could not enter is a finding, not a log line.

            It may be full of logos, and "we scanned everything" is false while
            one branch of the tree was refused.
            """
            self.log(t("  Access denied or error on {path}: {error}").format(
                path=path, error=exc), logging.WARNING)
            if isinstance(exc, OSError):
                reason, hint = paths.describe_unreadable_folder(exc, path)
                self._problems.append(core.Problem(path, reason, hint))

        source_paths = core.collect_source_files(
            source, cancel_event=self._cancel_event, on_error=walk_error)
        self.log(t("Source files found: {count}").format(count=len(source_paths)))

        # The source folder, when nested inside the scanned one, must be
        # excluded: otherwise the new logos would be treated as targets.
        exclude = [source] if core.is_within(source, scan) else []

        if by_content:
            def content_progress(done: int, of: int):
                self._set_progress(
                    done / max(of, 1) * 60,
                    t("Searching by content... {done}/{total}").format(done=done,
                                                                      total=of),
                )

            hits = core.scan_by_content(
                scan, references, threshold=threshold / 100.0, pattern=pattern,
                exclude_dirs=exclude, progress=content_progress,
                cancel_event=self._cancel_event, on_error=walk_error,
            )
            found = [path for path, _ in hits]
            similarity_by_path = {path: score for path, score in hits}
        else:
            found = core.scan_files(scan, pattern, exclude_dirs=exclude,
                                    cancel_event=self._cancel_event,
                                    on_error=walk_error)
            similarity_by_path = {}

        total = len(found)
        self.log(t("Files matching the pattern: {count}").format(count=total))

        source_files: list[FileInfo] = []
        for index, path in enumerate(source_paths, 1):
            if self._cancel_event.is_set():
                raise OperationCancelled()
            try:
                source_files.append(FileInfo.from_path(path))
            except OSError as exc:
                self.log(t("  Unreadable source {path}: {error}").format(
                    path=path, error=exc), logging.WARNING)
            self._set_progress(
                index / max(len(source_paths), 1) * 30,
                t("Reading sources... {done}/{total}").format(
                    done=index, total=len(source_paths)),
            )

        scanned: list[FileInfo] = []
        for index, path in enumerate(found, 1):
            if self._cancel_event.is_set():
                raise OperationCancelled()
            try:
                scanned.append(FileInfo.from_path(
                    path, similarity=similarity_by_path.get(path)))
            except OSError as exc:
                self.log(t("  Error on {path}: {error}").format(path=path, error=exc),
                         logging.WARNING)
            self._set_progress(
                30 + index / max(total, 1) * 70,
                t("Analysing files... {done}/{total}").format(done=index, total=total),
            )

        def on_problem(problem):
            """
            Surface a finding. Shared by both document scans: the rule that
            nothing is dropped is not per-format.
            """
            self._problems.append(problem)
            self.log(t("  Needs attention: {path} — {reason}").format(
                path=problem.path, reason=problem.reason), logging.WARNING)

        if include_office:
            def document_progress(done: int, of: int):
                self._set_progress(
                    done / max(of, 1) * 100,
                    t("Scanning documents... {done}/{total}").format(done=done,
                                                                    total=of),
                )

            embedded = core.scan_office_documents(
                scan,
                references=references if by_content else (),
                threshold=threshold / 100.0,
                exclude_dirs=exclude,
                progress=document_progress,
                cancel_event=self._cancel_event,
                on_error=walk_error,
                on_problem=on_problem,
            )
            self.log(t("Pictures found inside documents: {count}").format(
                count=len(embedded)))
            scanned.extend(embedded)

        if include_pdf:
            def pdf_progress(done: int, of: int):
                self._set_progress(
                    done / max(of, 1) * 100,
                    t("Scanning PDFs... {done}/{total}").format(done=done, total=of),
                )

            in_pdfs = core.scan_pdf_documents(
                scan,
                patterns=core.parse_patterns(pattern),
                references=references if by_content else (),
                threshold=threshold / 100.0,
                exclude_dirs=exclude,
                progress=pdf_progress,
                cancel_event=self._cancel_event,
                on_error=walk_error,
                on_problem=on_problem,
            )
            self.log(t("Pictures found inside PDFs: {count}").format(
                count=len(in_pdfs)))
            scanned.extend(in_pdfs)

        self.source_files = source_files
        self.scanned_files = scanned
        self._ui(self._populate_scan_tree)

    def _refresh_problem_bar(self):
        """Show or hide the findings bar according to what the scan reported."""
        if not self._problems:
            self._problem_bar.pack_forget()
            return
        self._problem_lbl.config(text=t(
            "⚠  {count} file(s) may carry the logo but could not be handled "
            "automatically — they need manual attention.").format(
                count=len(self._problems)))
        # Before the tree, which expands: packing after would leave the bar
        # clipped off the bottom of the tab.
        self._problem_bar.pack(fill=tk.X, padx=8, pady=(6, 0), before=self._scan_tree.master)

    def _show_problems(self):
        """List every finding, with what the user can do about each."""
        if not self._problems:
            return
        lines = []
        for problem in self._problems:
            lines.append(problem.path)
            lines.append(f"    {problem.reason}")
            if problem.hint:
                lines.append(f"    → {problem.hint}")
            lines.append("")
        messagebox.showwarning(t("Needs manual attention"), "\n".join(lines).strip())

    def _populate_scan_tree(self, announce: bool = True):
        self._refresh_problem_bar()
        self._clear_tree(self._scan_tree)
        for index, info in enumerate(self.scanned_files, 1):
            self._scan_tree.insert(
                "", tk.END, iid=info.path,
                values=(index, info.name, info.fmt, info.size_str, info.dim_str,
                        info.similarity_str, info.path),
                tags=("review",) if info.needs_review else (),
            )

        count = len(self.scanned_files)
        by_content = any(f.similarity is not None for f in self.scanned_files)
        template = (t("{count} files found by content — {sources} sources available")
                    if by_content
                    else t("{count} files found — {sources} sources available"))
        self._scan_count_lbl.config(
            text=template.format(count=count, sources=len(self.source_files)))

        if not announce:
            return

        self.progress_var.set(100)
        self._status(t("Scan complete: {count} files found.").format(count=count))
        self.log(t("Scan complete: {count} files, {sources} sources available.").format(
            count=count, sources=len(self.source_files)))

        uncertain = sum(1 for f in self.scanned_files if f.needs_review)
        if uncertain:
            self.log(t("⚠  {count} of them are below {threshold}% similarity: "
                       "look at those before replacing.").format(
                count=uncertain,
                threshold=int(core.SIMILARITY_CONFIDENT * 100)), logging.WARNING)

        if count == 0:
            messagebox.showinfo(
                t("No results"),
                t("No file matches the given pattern.\n\n"
                  "Check the pattern (e.g. logo*.png) and the folder to scan."),
            )

    def _on_scan_select(self, _event=None):
        selection = self._scan_tree.selection()
        if not selection:
            return
        info = next((f for f in self.scanned_files if f.path == selection[0]), None)
        if info:
            self._show_preview(info)

    def _on_scan_double_click(self, _event=None):
        selection = self._scan_tree.selection()
        if not selection:
            return
        info = next((f for f in self.scanned_files if f.path == selection[0]), None)
        if info:
            self._open_in_file_manager(os.path.dirname(info.location))

    def _show_preview(self, info: FileInfo):
        self._preview_canvas.delete("all")
        thumb = self._thumbnail_for(info, PREVIEW_SIZE)
        if thumb:
            self._keep_image("scan", thumb)
            self._preview_canvas.create_image(60, 45, image=thumb, anchor=tk.CENTER)
        else:
            self._preview_canvas.create_text(60, 45, text=t("N/A"), fill="#aaaaaa",
                                             font=("Arial", 11))

        self._preview_info.config(
            text=t("Name: {name}\nFormat: {fmt}\nSize: {size}\n"
                   "Resolution: {dim}\nPath: {path}").format(
                name=info.name, fmt=info.fmt, size=info.size_str,
                dim=info.dim_str, path=info.path),
            foreground="#333333",
        )

    def _keep_image(self, slot: str, photo):
        """
        Hold a thumbnail in an application-owned registry.

        `ImageTk.PhotoImage.__del__` calls Tk to free the image. If the object
        ends up in cyclic garbage, the collector may run its finaliser on any
        thread: when that happens on a worker thread, the call into Tk from
        outside the main thread blocks the interpreter and the application
        hangs.

        Keeping a strong reference here means thumbnails stay reachable and
        never become garbage; they are released explicitly by
        `_release_images`, which runs on the main thread.
        """
        self._image_refs[slot] = photo
        return photo

    def _release_images(self):
        """Release the thumbnails. Main thread only."""
        self._image_refs.clear()
        # Collect any remaining cycles right here and now, so the finalisers
        # run on this thread and not on a worker.
        gc.collect()

    @classmethod
    def _thumbnail_for(cls, info: FileInfo, size):
        """Thumbnail for a file, unpacking it first when it lives in a document."""
        if not info.embedded:
            return cls._make_thumbnail(info.path, size)
        temp = office.extract_to_temp(info.container, info.entry)
        if temp is None:
            return None
        try:
            return cls._make_thumbnail(temp, size)
        finally:
            try:
                os.remove(temp)
            except OSError:
                pass

    @staticmethod
    def _make_thumbnail(filepath: str, size):
        """
        Thumbnail for the preview. The file is closed immediately: keeping it
        open would prevent overwriting it on Windows.
        """
        if not PIL_AVAILABLE:
            return None
        if Path(filepath).suffix.lower() in core.NO_PIL_PREVIEW:
            return None
        try:
            with Image.open(filepath) as img:
                img.thumbnail(size, Image.Resampling.LANCZOS)
                return ImageTk.PhotoImage(img)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Matching
    # ------------------------------------------------------------------

    def _start_matching(self):
        if not self.scanned_files:
            messagebox.showwarning(
                t("Warning"),
                t("No file found in the scan.\nRun the scan first."))
            return
        if not self.source_files:
            messagebox.showwarning(t("Warning"),
                                   t("No image file in the source folder."))
            return

        self.matches = []
        self._match_by_path = {}
        self._clear_tree(self._match_tree)
        self._match_count_lbl.config(text=t("Analysing matches..."))
        self.notebook.select(2)
        self._start_worker(self._match_worker, (), t("Analysing matches..."))

    def _match_worker(self):
        total = len(self.scanned_files)
        self.log(t("Starting match: {count} files to analyse, {sources} sources "
                   "available.").format(count=total, sources=len(self.source_files)))

        def progress(done: int, of: int):
            self._set_progress(
                done / max(of, 1) * 100,
                t("Matching... {done}/{total}").format(done=done, total=of),
            )

        matches = core.build_matches(self.scanned_files, self.source_files,
                                     progress=progress, cancel_event=self._cancel_event)
        self.matches = matches
        self._match_by_path = {m.target.path: m for m in matches}
        self._ui(self._populate_match_tree)

    def _populate_match_tree(self):
        self._clear_tree(self._match_tree)
        for index, match in enumerate(self.matches, 1):
            self._match_tree.insert("", tk.END, iid=match.target.path,
                                    values=self._match_row(index, match),
                                    tags=(self._row_tag(match),))

        matched = sum(1 for m in self.matches if m.source is not None)
        weak = sum(1 for m in self.matches
                   if m.source is not None and m.quality == core.QUALITY_WEAK)
        total = len(self.matches)

        label = t("{total} files analysed: {matched} matches").format(
            total=total, matched=matched)
        if total - matched:
            label += t(", {count} without a match").format(count=total - matched)
        if weak:
            label += t(", {count} to review").format(count=weak)
        self._match_count_lbl.config(text=label)
        self.progress_var.set(100)
        self._status(label)
        self.log(t("Match complete: {matched}/{total} matches ({weak} weak).").format(
            matched=matched, total=total, weak=weak))

    @staticmethod
    def _match_row(index, match: Match) -> tuple:
        return (
            index,
            "✓" if match.enabled else "✗",
            match.target.name,
            match.target.fmt,
            match.target.dim_str,
            match.source_name,
            match.source_dim_str,
            match.quality_label,
            match.target.path,
        )

    @staticmethod
    def _row_tag(match: Match) -> str:
        if match.source is None:
            return "no_match"
        if not match.enabled:
            return "disabled"
        if match.quality == core.QUALITY_WEAK or match.distorts:
            return "weak"
        return "matched"

    def _refresh_match_row(self, match: Match):
        row_id = match.target.path
        if not self._match_tree.exists(row_id):
            return
        current = self._match_tree.item(row_id, "values")
        index = current[0] if current else ""
        self._match_tree.item(row_id, values=self._match_row(index, match),
                              tags=(self._row_tag(match),))

    def _toggle_match(self, row_id: str):
        match = self._match_by_path.get(row_id)
        if not match or match.source is None:
            return
        match.enabled = not match.enabled
        self._refresh_match_row(match)

    def _on_match_click(self, event):
        if self._match_tree.identify_region(event.x, event.y) != "cell":
            return
        if self._match_tree.identify_column(event.x) != "#2":  # the ✓ column
            return
        row_id = self._match_tree.identify_row(event.y)
        if row_id:
            self._toggle_match(row_id)

    def _on_match_space(self, _event=None):
        selection = self._match_tree.selection()
        if selection:
            self._toggle_match(selection[0])
        return "break"

    def _on_match_double_click(self, event):
        row_id = self._match_tree.identify_row(event.y)
        if row_id:
            self._choose_source_dialog(row_id)

    def _on_match_select(self, _event=None):
        selection = self._match_tree.selection()
        if not selection:
            return
        match = self._match_by_path.get(selection[0])
        if not match:
            return

        self._target_canvas.delete("all")
        thumb = self._thumbnail_for(match.target, MATCH_PREVIEW_SIZE)
        if thumb:
            self._keep_image("match_target", thumb)
            self._target_canvas.create_image(45, 35, image=thumb, anchor=tk.CENTER)
        else:
            self._target_canvas.create_text(45, 35, text=t("N/A"), fill="#aaaaaa")

        self._target_preview_info.config(
            text=t("Name: {name}\nFormat: {fmt}\nRes: {dim}\nWeight: {size}").format(
                name=match.target.name, fmt=match.target.fmt,
                dim=match.target.dim_str, size=match.target.size_str)
        )

        self._src_canvas.delete("all")
        if match.source is None:
            self._src_canvas.create_text(45, 35, text=t("No\nMatch"), fill="#cc4444")
            self._src_preview_info.config(
                text=t("Match not found.\nDouble-click to choose one manually."))
            return

        src_thumb = self._thumbnail_for(match.source, MATCH_PREVIEW_SIZE)
        if src_thumb:
            self._keep_image("match_source", src_thumb)
            self._src_canvas.create_image(45, 35, image=src_thumb, anchor=tk.CENTER)
        else:
            self._src_canvas.create_text(45, 35, text=t("N/A"), fill="#aaaaaa")

        self._src_preview_info.config(
            text=t("Name: {name}\nFormat: {fmt}\nRes: {dim}\nQuality: {quality}").format(
                name=match.source.name, fmt=match.source.fmt,
                dim=match.source.dim_str, quality=match.quality_label)
        )

    def _choose_source_dialog(self, row_id: str) -> tk.Toplevel | None:
        """
        Let the user pick the source file for a row by hand.
        Returns the window created (handy for tests), or None if not applicable.
        """
        match = self._match_by_path.get(row_id)
        if not match:
            return None
        if not self.source_files:
            messagebox.showinfo(t("No sources"),
                                t("The source folder contains no files."))
            return None

        # Same-format sources first, ordered by suitability.
        target_ext = core.normalized_ext(match.target.ext)
        ordered = sorted(
            self.source_files,
            key=lambda s: (
                core.normalized_ext(s.ext) != target_ext,
                core.match_score(match.target.dim, s.dim, match.target.path, s.path),
            ),
        )

        dialog = tk.Toplevel(self.root)
        dialog.title(t("Choose a source for {name}").format(name=match.target.name))
        dialog.transient(self.root)
        dialog.geometry("640x420")

        ttk.Label(dialog,
                  text=t("File to replace: {name} ({fmt}, {dim})").format(
                      name=match.target.name, fmt=match.target.fmt,
                      dim=match.target.dim_str),
                  font=("Arial", 10, "bold")).pack(anchor=tk.W, padx=12, pady=(12, 4))
        ttk.Label(dialog,
                  text=t("Sources with a matching format are listed first."),
                  font=("Arial", 9), foreground="#666666").pack(anchor=tk.W, padx=12)

        list_frame = ttk.Frame(dialog)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)
        listbox = tk.Listbox(list_frame, activestyle="dotbox")
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=listbox.yview)
        listbox.configure(yscrollcommand=scrollbar.set)
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        for info in ordered:
            flag = ("" if core.normalized_ext(info.ext) == target_ext
                    else t("  [different format]"))
            listbox.insert(tk.END, f"{info.name}  —  {info.dim_str}, "
                                   f"{info.size_str}{flag}")

        if match.source is not None:
            try:
                listbox.selection_set(ordered.index(match.source))
                listbox.see(ordered.index(match.source))
            except ValueError:
                pass

        def confirm():
            selection = listbox.curselection()
            if not selection:
                messagebox.showwarning(t("Warning"), t("Select a source file."),
                                       parent=dialog)
                return
            chosen = ordered[selection[0]]
            match.source = chosen
            match.manual = True
            match.enabled = True
            match.score = core.match_score(match.target.dim, chosen.dim,
                                           match.target.path, chosen.path)
            self._refresh_match_row(match)
            self._on_match_select()
            self.log(t("Source manually set for {target}: {source}").format(
                target=match.target.name, source=chosen.name))
            dialog.destroy()

        buttons = ttk.Frame(dialog)
        buttons.pack(fill=tk.X, padx=12, pady=(0, 12))
        ttk.Button(buttons, text=t("Confirm"), command=confirm,
                   **self.btn("primary")).pack(side=tk.RIGHT, padx=4)
        ttk.Button(buttons, text=t("Cancel"), command=dialog.destroy,
                   **self.btn("outline")).pack(side=tk.RIGHT, padx=4)

        listbox.bind("<Double-1>", lambda _e: confirm())
        dialog.bind("<Escape>", lambda _e: dialog.destroy())
        listbox.focus_set()
        dialog.grab_set()
        return dialog

    def _select_all_matches(self):
        for match in self.matches:
            if match.source is not None:
                match.enabled = True
            self._refresh_match_row(match)

    def _deselect_all_matches(self):
        for match in self.matches:
            match.enabled = False
            self._refresh_match_row(match)

    def _export_matches(self):
        if not self.matches:
            messagebox.showinfo(t("No data"), t("Run the match analysis first."))
            return
        destination = filedialog.asksaveasfilename(
            title=t("Export matches"),
            defaultextension=".csv",
            initialfile="matches.csv",
            filetypes=[("CSV", "*.csv"), ("All files", "*.*")],
        )
        if not destination:
            return
        try:
            core.export_matches_csv(self.matches, destination)
            self.log(t("Matches exported to {path}").format(path=destination))
            messagebox.showinfo(t("Export complete"),
                                t("File saved:\n{path}").format(path=destination))
        except OSError as exc:
            messagebox.showerror(t("Export error"), str(exc))

    # ------------------------------------------------------------------
    # Replacement
    # ------------------------------------------------------------------

    def _enabled_matches(self) -> list[Match]:
        return [m for m in self.matches if m.enabled and m.source is not None]

    def _go_to_replace(self):
        if not self._enabled_matches():
            messagebox.showwarning(t("Warning"), t("No replacement selected."))
            return
        self.notebook.select(3)

    def _on_tab_changed(self, _event=None):
        # The summary must be recomputed when the user reaches tab 4 straight
        # from the tab strip, not only via the «Proceed» button.
        if self.notebook.index("current") == 3:
            self._refresh_replace_summary()

    def _refresh_replace_summary(self):
        enabled = self._enabled_matches()
        if not enabled:
            self._replace_summary_lbl.config(
                text=t("No replacement selected.\nGo back to tab ③ and select at "
                       "least one match."))
            return

        if self._dry_run_var.get():
            mode = t("DRY RUN ENABLED: no file will be modified.")
        elif self._backup_var.get():
            mode = t("The original files will be saved with a .bak extension "
                     "(restorable).")
        else:
            mode = t("BACKUP DISABLED: the original files will be overwritten "
                     "permanently.")

        distorting = sum(1 for m in enabled if m.distorts)
        weak = sum(1 for m in enabled if m.quality == core.QUALITY_WEAK)
        text = t("{count} of {total} analysed files will be replaced.\n{mode}").format(
            count=len(enabled), total=len(self.matches), mode=mode)
        if weak:
            text += t("\n⚠  {count} matches are rated «Weak»: review them in "
                      "tab ③.").format(count=weak)
        if distorting:
            text += t("\n⚠  {count} replacements would stretch the picture: inside "
                      "a document the frame keeps its own proportions.").format(
                count=distorting)
        self._replace_summary_lbl.config(text=text)

    def _execute_replacement(self):
        enabled = self._enabled_matches()
        if not enabled:
            messagebox.showwarning(t("Warning"), t("No replacement to run."))
            return

        do_backup = self._backup_var.get()
        dry_run = self._dry_run_var.get()

        if dry_run:
            question = t("Dry run over {count} files.\n\n"
                         "No file will be modified.\n\nContinue?").format(
                count=len(enabled))
        else:
            question = t("You are about to overwrite {count} files.\n\n"
                         "Backup: {backup}\n\nContinue?").format(
                count=len(enabled),
                backup=t("YES") if do_backup else t("NO — this cannot be undone"))
        if not messagebox.askyesno(t("Confirm Replacement"), question):
            return

        self._save_settings()
        # The previews hold a reference to the images: on Windows that would
        # prevent the target files from being overwritten.
        self._clear_previews()
        self._start_worker(self._replace_worker, (enabled, do_backup, dry_run),
                           t("Replacing..."))

    def _replace_worker(self, matches: list[Match], do_backup: bool, dry_run: bool):
        action = t("DRY RUN") if dry_run else t("REPLACEMENT")
        action_title = t("Dry run") if dry_run else t("Replacement")
        self.log(t("=== {action} START: {count} files (backup: {backup}) ===").format(
            action=action, count=len(matches),
            backup=t("yes") if do_backup else t("no")))

        def progress(done: int, of: int, outcome: core.ReplaceOutcome):
            name = os.path.basename(outcome.target)
            if outcome.status == "ok":
                if dry_run:
                    self.log(t("  ○ [simulated] {target}  ←  {source}").format(
                        target=name, source=os.path.basename(outcome.source)))
                else:
                    if outcome.backup:
                        self.log(t("  backup: {path}").format(path=outcome.backup))
                    self.log(t("  ✅ Replaced: {target}  ←  {source}").format(
                        target=name, source=os.path.basename(outcome.source)))
            elif outcome.status == "skipped":
                self.log(t("  ⏭ Skipped {target}: {message}").format(
                    target=name, message=outcome.message), logging.WARNING)
            else:
                self.log(t("  ❌ Error on {target}: {message}").format(
                    target=name, message=outcome.message), logging.ERROR)

            template = (t("Dry run... {done}/{total}") if dry_run
                        else t("Replacement... {done}/{total}"))
            self._set_progress(done / max(of, 1) * 100,
                               template.format(done=done, total=of))

        report = core.replace_all(matches, backup=do_backup, dry_run=dry_run,
                                  progress=progress, cancel_event=self._cancel_event)

        self.log(t("=== {action} COMPLETE: {ok} ok, {skipped} skipped, {errors} "
                   "errors out of {total} files ===").format(
            action=action, ok=report.ok, skipped=report.skipped,
            errors=report.errors, total=report.total))
        self._ui(lambda: self._replacement_done(report, dry_run, action_title))

    def _replacement_done(self, report: core.ReplaceReport, dry_run: bool,
                          action_title: str):
        self.progress_var.set(100)
        self._status(t("{action} complete: {ok} ok, {skipped} skipped, "
                       "{errors} errors.").format(
            action=action_title, ok=report.ok, skipped=report.skipped,
            errors=report.errors))

        detail = t("Files processed: {total}\nCompleted: {ok}\nSkipped: {skipped}\n"
                   "Errors: {errors}").format(
            total=report.total, ok=report.ok, skipped=report.skipped,
            errors=report.errors)
        if report.cancelled:
            detail += t("\n\nOperation interrupted by the user.")

        if report.errors:
            messagebox.showwarning(
                t("Completed with errors"),
                t("{detail}\n\nSee the log for details.").format(detail=detail))
        elif dry_run:
            messagebox.showinfo(
                t("Dry run complete"),
                t("{detail}\n\nNo file was modified.").format(detail=detail))
        else:
            messagebox.showinfo(
                t("Completed"),
                t("✅ Replacement completed successfully!\n\n{detail}").format(
                    detail=detail))

        if not dry_run and report.ok:
            self._ask_export_report(report)

    def _ask_export_report(self, report: core.ReplaceReport):
        if not messagebox.askyesno(
            t("Report"), t("Do you want to save a CSV report of the operation?")
        ):
            return
        destination = filedialog.asksaveasfilename(
            title=t("Save report"), defaultextension=".csv",
            initialfile="replacement_report.csv",
            filetypes=[("CSV", "*.csv"), ("All files", "*.*")],
        )
        if not destination:
            return
        try:
            core.export_report_csv(report, destination)
            self.log(t("Report saved to {path}").format(path=destination))
        except OSError as exc:
            messagebox.showerror(t("Report save error"), str(exc))

    def _restore_backups(self):
        folder = self.scan_folder.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showerror(
                t("Error"),
                t("Select a valid folder to scan in tab ① before restoring."))
            return

        backups = core.find_backups(folder)
        if not backups:
            messagebox.showinfo(t("No backup"),
                                t("No .bak file found in:\n{path}").format(path=folder))
            return

        distinct = len({core.backup_origin(b) for b in backups})
        if not messagebox.askyesno(
            t("Confirm restore"),
            t("Found {count} backups covering {files} files in:\n{path}\n\n"
              "The current files will be reverted to their pre-rebranding "
              "version.\n\nContinue?").format(
                count=len(backups), files=distinct, path=folder),
        ):
            return

        remove = messagebox.askyesno(
            t("Backup"),
            t("Do you want to delete the .bak files after restoring?\n\n"
              "Choose «No» to keep them."),
        )
        self._clear_previews()
        self._start_worker(self._restore_worker, (folder, remove), t("Restoring..."))

    def _restore_worker(self, folder: str, remove: bool):
        self.log(t("=== RESTORE START from {path} ===").format(path=folder))

        def progress(done: int, of: int, outcome: core.ReplaceOutcome):
            name = os.path.basename(outcome.target)
            if outcome.ok:
                self.log(t("  ↩ Restored: {target}").format(target=name))
            else:
                self.log(t("  ❌ Restore error on {target}: {message}").format(
                    target=name, message=outcome.message), logging.ERROR)
            self._set_progress(
                done / max(of, 1) * 100,
                t("Restore... {done}/{total}").format(done=done, total=of),
            )

        report = core.restore_backups(folder, remove_backup=remove, progress=progress,
                                      cancel_event=self._cancel_event)
        self.log(t("=== RESTORE COMPLETE: {ok} ok, {errors} errors ===").format(
            ok=report.ok, errors=report.errors))

        def done():
            self.progress_var.set(100)
            self._status(t("Restore complete: {ok} ok, {errors} errors.").format(
                ok=report.ok, errors=report.errors))
            messagebox.showinfo(
                t("Restore complete"),
                t("Files restored: {ok}\nErrors: {errors}").format(
                    ok=report.ok, errors=report.errors),
            )

        self._ui(done)

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------

    def _sort_tree(self, tree: ttk.Treeview, col: str):
        """
        Sort a column, alternating ascending/descending.

        The sort is type-aware: numeric columns and those carrying units used
        to be sorted as text, putting «10» before «2».
        """
        key = (id(tree), col)
        descending = self._sort_state.get(key, False)

        def sort_key(item: str):
            raw = tree.set(item, col)
            if col in NUMERIC_COLUMNS:
                try:
                    return (0, float(raw))
                except ValueError:
                    return (1, 0.0)
            if col in SORT_KEY_COLUMNS:
                return (0, self._numeric_prefix(raw))
            return (0, raw.lower())

        items = sorted(tree.get_children(""), key=sort_key, reverse=descending)
        for position, item in enumerate(items):
            tree.move(item, "", position)
        self._sort_state[key] = not descending

    @staticmethod
    def _numeric_prefix(raw: str) -> float:
        """
        Numeric value out of a formatted cell (`1.5 MB`, `800×600 px`).
        Resolutions use the area, so the ordering is meaningful.
        """
        numbers = [float(n) for n in re.findall(r"[0-9]+(?:\.[0-9]+)?", raw)]
        if not numbers:
            return -1.0
        if "×" in raw and len(numbers) >= 2:
            return numbers[0] * numbers[1]
        value = numbers[0]
        for unit, factor in (("TB", 1024 ** 4), ("GB", 1024 ** 3),
                             ("MB", 1024 ** 2), ("KB", 1024)):
            if unit in raw:
                return value * factor
        return value

    def _clear_tree(self, tree: ttk.Treeview):
        tree.delete(*tree.get_children())

    def _clear_previews(self):
        """
        Empty the previews, releasing the image references.
        This also unlocks the files on Windows before overwriting them.
        """
        for canvas in (self._preview_canvas, self._target_canvas, self._src_canvas):
            canvas.delete("all")
        self._release_images()
        self.root.update_idletasks()

    def _clear_log(self):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)
        self._log_buffer.clear()


# Backwards compatibility: some scripts imported these helpers from here.
get_base_path = core.get_base_path
resource_path = core.resource_path
scan_files = core.scan_files
get_image_dimensions = core.get_image_dimensions
size_diff = core.size_diff
SUPPORTED_FORMATS = core.SUPPORTED_FORMATS
