#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Rebranding Tool - Strumento per la sostituzione massiva di file grafici/logo.
SACE S.p.A - Interfaccia grafica.

La logica applicativa (scansione, abbinamento, sostituzione) vive in `core.py`
e non dipende da tkinter: questo modulo si occupa solo della presentazione.
"""

from __future__ import annotations

import datetime
import gc
import logging
import os
import re
import threading
import webbrowser
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import core
from core import (
    APP_COMPANY,
    APP_NAME,
    APP_VERSION,
    FileInfo,
    Match,
    OperationCancelled,
)

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    Image = ImageTk = None
    PIL_AVAILABLE = False

try:
    import ttkbootstrap as tb
    BOOTSTRAP_AVAILABLE = True
except Exception:  # pragma: no cover - dipende dall'ambiente
    tb = None
    BOOTSTRAP_AVAILABLE = False


# ---------------------------------------------------------------------------
# Palette e stili
# ---------------------------------------------------------------------------

SACE_BLUE = "#3365ae"

#: Stili pulsante: (colore, colore hover, colore premuto).
#: Vengono registrati come stili ttk nostri (`Primary.TButton`, ...) invece di
#: affidarsi all'opzione `bootstyle` di ttkbootstrap, che esiste solo sui
#: widget di quella libreria e fa fallire i widget ttk standard.
BUTTON_PALETTE = {
    "primary": (SACE_BLUE, "#28508a", "#1e3c6a"),
    "success": ("#28a745", "#218838", "#1c7430"),
    "warning": ("#e08e0b", "#c47c09", "#a86a08"),
    "danger":  ("#d9534f", "#c33f3b", "#a83531"),
}

PROGRESS_STYLE = "Sace.Horizontal.TProgressbar"

PREVIEW_SIZE = (110, 80)
MATCH_PREVIEW_SIZE = (90, 70)

#: Colonne ordinabili numericamente invece che alfabeticamente.
NUMERIC_COLUMNS = {"#"}
#: Colonne ordinate per il valore reale sottostante (peso, risoluzione).
SORT_KEY_COLUMNS = {"size", "dim", "target_dim", "src_dim"}


def _tag_from_match(match: Match) -> str:
    if match.source is None:
        return "no_match"
    return "matched" if match.enabled else "disabled"


class RebrandingToolApp:
    """Applicazione principale del Rebranding Tool."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"{APP_NAME} {APP_VERSION} - {APP_COMPANY}")
        self.root.geometry("1150x780")
        self.root.minsize(940, 660)

        self.logger = core.setup_logging()

        # --- Stato ---
        settings = core.load_settings()
        self.source_folder = tk.StringVar(value=str(settings["source_folder"]))
        self.scan_folder = tk.StringVar(value=str(settings["scan_folder"]))
        self.search_pattern = tk.StringVar(value=str(settings["search_pattern"]))
        self._backup_var = tk.BooleanVar(value=bool(settings["backup"]))
        self._dry_run_var = tk.BooleanVar(value=bool(settings["dry_run"]))

        self.scanned_files: list[FileInfo] = []
        self.source_files: list[FileInfo] = []
        self.matches: list[Match] = []
        self._match_by_path: dict[str, Match] = {}

        # Riferimenti alle miniature attualmente visibili, uno per riquadro.
        # Vedi `_keep_image` per il motivo per cui non stanno sui widget.
        self._image_refs: dict[str, object] = {}

        # --- Concorrenza ---
        # Una sola operazione lunga per volta; l'evento consente l'annullamento.
        self._ui_queue: "list[callable]" = []
        self._ui_lock = threading.Lock()
        self._cancel_event = threading.Event()
        self._worker: threading.Thread | None = None
        self._closing = False
        self._pump_after_id: str | None = None
        self._pending_progress: tuple[float, str] | None = None
        self._sort_state: dict[tuple[int, str], bool] = {}

        self.progress_var = tk.DoubleVar(value=0)

        # --- Setup ---
        self._set_window_icon()
        self._apply_theme()
        self._create_widgets()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._pump_ui_queue()

        self.log(f"{APP_NAME} {APP_VERSION} avviato.")
        if not PIL_AVAILABLE:
            self.log("Pillow non disponibile: anteprime e risoluzioni immagine "
                     "non saranno mostrate.", logging.WARNING)

    # ------------------------------------------------------------------
    # Setup finestra
    # ------------------------------------------------------------------

    def _set_window_icon(self):
        icon = core.resource_path("sace.ico")
        if os.path.exists(icon):
            try:
                self.root.iconbitmap(icon)
            except Exception:
                pass  # iconbitmap .ico non è supportato su tutte le piattaforme

    def _apply_theme(self):
        """
        Applica il tema e registra gli stili dei pulsanti.

        ttkbootstrap è opzionale e usato solo per il tema di base: tutti i
        pulsanti usano stili ttk registrati qui, così l'app funziona anche
        senza la libreria e con qualunque sua versione.
        """
        self.style: ttk.Style | None = None

        if BOOTSTRAP_AVAILABLE:
            try:
                self.style = tb.Style()
                # `flatly` esiste solo fino alla 2.x ed è deprecato: si prova
                # prima il nome moderno, così non si emette un warning né si
                # dipende da un tema in via di rimozione.
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
                # 'clam' onora background/foreground sui pulsanti, i temi nativi
                # Windows ("vista") li ignorerebbero.
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
                background=[("disabled", "#b9c2cc"), ("pressed", pressed), ("active", hover)],
                foreground=[("disabled", "#eeeeee"), ("active", "white")],
            )

        # Senza colori espliciti la barra viene disegnata bianca su fondo
        # bianco: tecnicamente funziona, ma è invisibile.
        self.style.configure(
            PROGRESS_STYLE,
            troughcolor="#e6e9ee",
            bordercolor="#c9d0d8",
            background=SACE_BLUE,
            lightcolor=SACE_BLUE,
            darkcolor=SACE_BLUE,
        )

        self.style.configure(
            "Outline.TButton",
            font=("Arial", 9),
            foreground=SACE_BLUE,
            padding=(10, 6),
        )
        self.style.map(
            "Outline.TButton",
            foreground=[("disabled", "#999999"), ("active", "#1e3c6a")],
        )

    @staticmethod
    def btn(kind: str) -> dict:
        """Opzioni di stile per un pulsante ('primary', 'success', ..., 'outline')."""
        if kind == "outline" or kind not in BUTTON_PALETTE:
            return {"style": "Outline.TButton"}
        return {"style": f"{kind.capitalize()}.TButton"}

    # ------------------------------------------------------------------
    # Aggiornamento UI thread-safe
    # ------------------------------------------------------------------

    def _ui(self, fn):
        """Accoda una callable da eseguire nel thread principale."""
        with self._ui_lock:
            self._ui_queue.append(fn)

    def _set_progress(self, value: float, text: str | None = None):
        """
        Registra un avanzamento. Gli aggiornamenti sono accorpati e applicati
        una volta per tick: su decine di migliaia di file, accodare una
        callback per elemento saturerebbe la coda e bloccherebbe la UI.
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
                return  # finestra distrutta durante l'elaborazione
            except Exception as exc:
                self.logger.error("Errore aggiornamento UI: %s", exc)

        if self._pending_progress is not None:
            value, text = self._pending_progress
            self._pending_progress = None
            try:
                self.progress_var.set(value)
                if text:
                    self.status_label.config(text=text)
            except tk.TclError:
                return

        # L'id serve per annullare il tick alla chiusura: un after() pendente
        # su un interprete distrutto produce un errore Tcl in background.
        self._pump_after_id = self.root.after(80, self._pump_ui_queue)

    # ------------------------------------------------------------------
    # Log
    # ------------------------------------------------------------------

    def log(self, message: str, level: int = logging.INFO):
        self.logger.log(level, message)
        entry = f"[{datetime.datetime.now():%H:%M:%S}] {message}"
        self._ui(lambda e=entry: self._append_log(e))

    def _append_log(self, entry: str):
        if not hasattr(self, "log_text"):
            return
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, entry + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _status(self, msg: str):
        self._ui(lambda m=msg: self.status_label.config(text=m))

    # ------------------------------------------------------------------
    # Creazione widget
    # ------------------------------------------------------------------

    def _create_widgets(self):
        # La barra di stato va impacchettata *prima* del notebook: in Tk chi
        # viene prima si riserva lo spazio, e un notebook con expand=True
        # schiaccerebbe la barra fino a tagliarne progressbar e pulsante.
        self._build_status_bar()

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        ttk.Label(
            self.root,
            text=f"VERSIONE {APP_VERSION} - ©{APP_COMPANY}",
            font=("Arial", 8),
            foreground="#888888",
        ).place(relx=1.0, y=10, anchor=tk.NE, x=-12)

        self._frame_config = ttk.Frame(self.notebook)
        self.notebook.add(self._frame_config, text="  ① CONFIGURAZIONE  ")

        self._frame_scan = ttk.Frame(self.notebook)
        self.notebook.add(self._frame_scan, text="  ② RISULTATI SCANSIONE  ")

        self._frame_match = ttk.Frame(self.notebook)
        self.notebook.add(self._frame_match, text="  ③ CORRISPONDENZE  ")

        self._frame_replace = ttk.Frame(self.notebook)
        self.notebook.add(self._frame_replace, text="  ④ SOSTITUZIONE  ")

        self._build_config_tab(self._frame_config)
        self._build_scan_tab(self._frame_scan)
        self._build_match_tab(self._frame_match)
        self._build_replace_tab(self._frame_replace)

        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    def _build_status_bar(self):
        status_bar = ttk.Frame(self.root, relief=tk.SUNKEN)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM, padx=8, pady=(0, 6))

        self.status_label = ttk.Label(status_bar, text="Pronto", anchor=tk.W)
        self.status_label.pack(side=tk.LEFT, padx=6)

        self._btn_cancel = ttk.Button(
            status_bar, text="Annulla", width=10,
            command=self._request_cancel, state=tk.DISABLED, **self.btn("outline"),
        )
        self._btn_cancel.pack(side=tk.RIGHT, padx=6, pady=2)

        # La progressbar esisteva solo come variabile: senza widget associato
        # l'avanzamento non era visibile da nessuna parte.
        self._progress = ttk.Progressbar(
            status_bar, variable=self.progress_var, maximum=100,
            length=240, mode="determinate", style=PROGRESS_STYLE,
        )
        self._progress.pack(side=tk.RIGHT, padx=6, pady=2)

    # ------------------------------------------------------------------
    # TAB 1 - CONFIGURAZIONE
    # ------------------------------------------------------------------

    def _build_config_tab(self, parent: ttk.Frame):
        top = ttk.Frame(parent)
        top.pack(fill=tk.X, padx=8, pady=(12, 4))
        ttk.Label(top, text="Configurazione Ricerca",
                  font=("Arial", 13, "bold")).pack(side=tk.LEFT, padx=16)

        ttk.Label(
            parent,
            text="Imposta le cartelle e la chiave di ricerca, poi avvia la scansione.",
            font=("Arial", 10), foreground="#666666",
        ).pack(anchor=tk.W, padx=24, pady=(0, 16))

        # --- Cartella sorgente ---
        src_frame = ttk.LabelFrame(parent, text=" CARTELLA SORGENTE (nuovi loghi) ")
        src_frame.pack(fill=tk.X, padx=24, pady=6)
        ttk.Label(
            src_frame,
            text="Cartella contenente i nuovi file logo (sorgente della sostituzione):",
            font=("Arial", 9), foreground="#555555",
        ).grid(row=0, column=0, columnspan=3, sticky=tk.W, padx=8, pady=(8, 2))
        ttk.Label(src_frame, text="Percorso:").grid(row=1, column=0, sticky=tk.W, padx=8, pady=4)
        self._entry_source = ttk.Entry(src_frame, textvariable=self.source_folder, width=68)
        self._entry_source.grid(row=1, column=1, padx=4, pady=4, sticky=tk.EW)
        ttk.Button(src_frame, text="Sfoglia...", command=self._browse_source_folder,
                   **self.btn("outline")).grid(row=1, column=2, padx=8, pady=4)
        src_frame.columnconfigure(1, weight=1)

        # --- Cartella da scansionare ---
        scan_frame = ttk.LabelFrame(parent, text=" CARTELLA DA SCANSIONARE ")
        scan_frame.pack(fill=tk.X, padx=24, pady=6)
        ttk.Label(
            scan_frame,
            text="Cartella (e sottocartelle) dove cercare i file da sostituire "
                 "(es. server, share di rete):",
            font=("Arial", 9), foreground="#555555",
        ).grid(row=0, column=0, columnspan=3, sticky=tk.W, padx=8, pady=(8, 2))
        ttk.Label(scan_frame, text="Percorso:").grid(row=1, column=0, sticky=tk.W, padx=8, pady=4)
        self._entry_scan = ttk.Entry(scan_frame, textvariable=self.scan_folder, width=68)
        self._entry_scan.grid(row=1, column=1, padx=4, pady=4, sticky=tk.EW)
        ttk.Button(scan_frame, text="Sfoglia...", command=self._browse_scan_folder,
                   **self.btn("outline")).grid(row=1, column=2, padx=8, pady=4)
        scan_frame.columnconfigure(1, weight=1)

        # --- Chiave di ricerca ---
        key_frame = ttk.LabelFrame(parent, text=" CHIAVE DI RICERCA ")
        key_frame.pack(fill=tk.X, padx=24, pady=6)
        ttk.Label(
            key_frame,
            text="Pattern con wildcard (* = più caratteri, ? = un carattere). "
                 "Più pattern separati da «;».\n"
                 "Esempi: logo*.png  |  banner_*.jpg  |  icon_??.svg  |  logo*.png; logo*.svg",
            font=("Arial", 9), foreground="#555555", justify=tk.LEFT,
        ).grid(row=0, column=0, columnspan=3, sticky=tk.W, padx=8, pady=(8, 2))
        ttk.Label(key_frame, text="Pattern:").grid(row=1, column=0, sticky=tk.W, padx=8, pady=4)
        self._entry_pattern = ttk.Entry(key_frame, textvariable=self.search_pattern, width=40)
        self._entry_pattern.grid(row=1, column=1, padx=4, pady=4, sticky=tk.W)
        self._entry_pattern.bind("<Return>", lambda _e: self._start_scan())
        key_frame.columnconfigure(1, weight=1)

        if not PIL_AVAILABLE:
            warn = ttk.Frame(parent)
            warn.pack(fill=tk.X, padx=24, pady=4)
            ttk.Label(
                warn,
                text="⚠️  Pillow (PIL) non installato: anteprime e risoluzioni non "
                     "saranno disponibili. Installa con: pip install pillow",
                font=("Arial", 9), foreground="#cc6600",
            ).pack(anchor=tk.W)

        # --- Pulsanti ---
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=24, pady=20)

        self._btn_scan = ttk.Button(
            btn_frame, text="🔍  AVVIA SCANSIONE", command=self._start_scan,
            width=26, **self.btn("success"),
        )
        self._btn_scan.pack(side=tk.RIGHT, padx=4)

        ttk.Button(btn_frame, text="Pulisci campi", command=self._clear_fields,
                   **self.btn("outline")).pack(side=tk.RIGHT, padx=4)

        ttk.Button(btn_frame, text="Apri cartella log", command=self._open_log_folder,
                   **self.btn("outline")).pack(side=tk.LEFT, padx=4)

        # --- Banner ---
        banner_container = ttk.Frame(parent)
        banner_container.pack(fill=tk.BOTH, expand=True, padx=24, pady=10)
        self._load_banner(banner_container)

    def _load_banner(self, container: ttk.Frame):
        if not PIL_AVAILABLE:
            return
        banner_path = core.resource_path("banner.jpg")
        if not os.path.exists(banner_path):
            self.log(f"banner.jpg non trovato in {banner_path}", logging.WARNING)
            return
        try:
            with Image.open(banner_path) as img:
                ratio = min(900 / img.width, 300 / img.height, 1.0)
                if ratio < 1:
                    img = img.resize(
                        (int(img.width * ratio), int(img.height * ratio)),
                        Image.Resampling.LANCZOS,
                    )
                photo = ImageTk.PhotoImage(img)
            self._banner_ref = photo  # anti garbage collection
            label = ttk.Label(container, image=photo)
            label.image = photo
            label.pack(expand=True)
        except Exception as exc:
            self.log(f"Errore caricamento banner.jpg: {exc}", logging.ERROR)

    # ------------------------------------------------------------------
    # TAB 2 - RISULTATI SCANSIONE
    # ------------------------------------------------------------------

    def _build_scan_tab(self, parent: ttk.Frame):
        top = ttk.Frame(parent)
        top.pack(fill=tk.X, padx=8, pady=(12, 4))
        ttk.Label(top, text="Risultati Scansione", font=("Arial", 13, "bold")).pack(side=tk.LEFT)
        self._scan_count_lbl = ttk.Label(top, text="Nessuna scansione effettuata",
                                         foreground="#888888")
        self._scan_count_lbl.pack(side=tk.RIGHT, padx=8)

        ttk.Label(
            parent,
            text="Controlla i file individuati, poi avvia l'analisi delle corrispondenze. "
                 "Doppio clic su una riga per aprire la cartella che la contiene.",
            font=("Arial", 10), foreground="#666666",
        ).pack(anchor=tk.W, padx=8, pady=(0, 10))

        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        columns = ("#", "name", "ext", "size", "dim", "path")
        self._scan_tree = ttk.Treeview(tree_frame, columns=columns, show="headings",
                                       height=12, selectmode="extended")
        headers = {
            "#":    ("#", 46),
            "name": ("Nome File", 180),
            "ext":  ("Formato", 70),
            "size": ("Dimensione", 100),
            "dim":  ("Risoluzione", 120),
            "path": ("Percorso Completo", 460),
        }
        for col, (label, width) in headers.items():
            self._scan_tree.heading(
                col, text=label,
                command=lambda c=col: self._sort_tree(self._scan_tree, c),
            )
            self._scan_tree.column(col, width=width, minwidth=60)

        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self._scan_tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self._scan_tree.xview)
        self._scan_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self._scan_tree.grid(row=0, column=0, sticky=tk.NSEW)
        vsb.grid(row=0, column=1, sticky=tk.NS)
        hsb.grid(row=1, column=0, sticky=tk.EW)
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        self._scan_tree.bind("<<TreeviewSelect>>", self._on_scan_select)
        self._scan_tree.bind("<Double-1>", self._on_scan_double_click)

        preview_outer = ttk.LabelFrame(parent, text=" Anteprima ")
        preview_outer.pack(fill=tk.X, padx=8, pady=4)
        self._preview_canvas = tk.Canvas(preview_outer, width=120, height=90, bg="#f5f5f5",
                                         highlightthickness=1, highlightbackground="#cccccc")
        self._preview_canvas.pack(side=tk.LEFT, padx=8, pady=6)
        self._preview_info = ttk.Label(preview_outer, text="Seleziona un file per l'anteprima",
                                       font=("Arial", 9), foreground="#888888", justify=tk.LEFT)
        self._preview_info.pack(side=tk.LEFT, padx=12, pady=6, anchor=tk.W)

        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, padx=8, pady=8)

        self._btn_match = ttk.Button(
            btn_frame, text="🔗  TROVA CORRISPONDENZE", command=self._start_matching,
            width=32, **self.btn("primary"),
        )
        self._btn_match.pack(side=tk.RIGHT, padx=4)

        ttk.Button(btn_frame, text="← Torna alla Configurazione",
                   command=lambda: self.notebook.select(0),
                   **self.btn("outline")).pack(side=tk.LEFT, padx=4)

    # ------------------------------------------------------------------
    # TAB 3 - CORRISPONDENZE
    # ------------------------------------------------------------------

    def _build_match_tab(self, parent: ttk.Frame):
        top = ttk.Frame(parent)
        top.pack(fill=tk.X, padx=8, pady=(12, 4))
        ttk.Label(top, text="Corrispondenze Proposte", font=("Arial", 13, "bold")).pack(side=tk.LEFT)
        self._match_count_lbl = ttk.Label(top, text="", foreground="#888888")
        self._match_count_lbl.pack(side=tk.RIGHT, padx=8)

        ttk.Label(
            parent,
            text="Ogni file trovato viene abbinato al sorgente più idoneo (stesso formato, "
                 "risoluzione più simile, nome più affine).\n"
                 "Clic sulla colonna ✓ o barra spaziatrice per includere/escludere una riga; "
                 "doppio clic per scegliere un sorgente diverso.",
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
            "target_name": ("File da Sostituire", 185),
            "target_fmt":  ("Formato", 70),
            "target_dim":  ("Risoluzione Target", 130),
            "src_name":    ("Nuovo File Sorgente", 185),
            "src_dim":     ("Risoluzione Sorgente", 130),
            "quality":     ("Qualità", 80),
            "target_path": ("Percorso Target", 340),
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

        # Il toggle scatta solo sulla colonna ✓ (o con la barra spaziatrice):
        # prima qualunque clic invertiva la riga, rendendo impossibile
        # selezionarla per vederne l'anteprima senza modificarla.
        self._match_tree.bind("<Button-1>", self._on_match_click)
        self._match_tree.bind("<Double-1>", self._on_match_double_click)
        self._match_tree.bind("<space>", self._on_match_space)
        self._match_tree.bind("<<TreeviewSelect>>", self._on_match_select)

        preview_outer = ttk.Frame(parent)
        preview_outer.pack(fill=tk.X, padx=8, pady=4)

        target_box = ttk.LabelFrame(preview_outer, text=" Logo Originale ")
        target_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 4))
        self._target_canvas = tk.Canvas(target_box, width=90, height=70, bg="#f5f5f5",
                                        highlightthickness=1)
        self._target_canvas.pack(side=tk.LEFT, padx=6, pady=4)
        self._target_preview_info = ttk.Label(target_box, text="Seleziona una riga",
                                              font=("Arial", 8), justify=tk.LEFT)
        self._target_preview_info.pack(side=tk.LEFT, padx=6, pady=4, anchor=tk.W)

        ttk.Label(preview_outer, text="➜", font=("Arial", 20),
                  foreground=SACE_BLUE).pack(side=tk.LEFT, padx=4)

        src_box = ttk.LabelFrame(preview_outer, text=" Nuovo Logo Proposto ")
        src_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(4, 0))
        self._src_canvas = tk.Canvas(src_box, width=90, height=70, bg="#f5f5f5",
                                     highlightthickness=1)
        self._src_canvas.pack(side=tk.LEFT, padx=6, pady=4)
        self._src_preview_info = ttk.Label(src_box, text="Seleziona una riga",
                                           font=("Arial", 8), justify=tk.LEFT)
        self._src_preview_info.pack(side=tk.LEFT, padx=6, pady=4, anchor=tk.W)

        leg = ttk.Frame(parent)
        leg.pack(fill=tk.X, padx=8, pady=2)
        ttk.Label(leg, text="✓ = incluso   ✗ = escluso   rosso = nessuna corrispondenza   "
                            "arancio = abbinamento debole, da verificare",
                  font=("Arial", 8), foreground="#888888").pack(side=tk.LEFT)

        btn_f = ttk.Frame(parent)
        btn_f.pack(fill=tk.X, padx=8, pady=8)

        ttk.Button(btn_f, text="Seleziona tutto", command=self._select_all_matches,
                   **self.btn("outline")).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_f, text="Deseleziona tutto", command=self._deselect_all_matches,
                   **self.btn("outline")).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_f, text="Esporta CSV", command=self._export_matches,
                   **self.btn("outline")).pack(side=tk.LEFT, padx=4)

        ttk.Button(btn_f, text="✅  PROCEDI CON LA SOSTITUZIONE", command=self._go_to_replace,
                   width=34, **self.btn("warning")).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btn_f, text="← Torna ai Risultati", command=lambda: self.notebook.select(1),
                   **self.btn("outline")).pack(side=tk.RIGHT, padx=4)

    # ------------------------------------------------------------------
    # TAB 4 - SOSTITUZIONE
    # ------------------------------------------------------------------

    def _build_replace_tab(self, parent: ttk.Frame):
        top = ttk.Frame(parent)
        top.pack(fill=tk.X, padx=8, pady=(12, 4))
        ttk.Label(top, text="Sostituzione File",
                  font=("Arial", 13, "bold")).pack(side=tk.LEFT, padx=16)

        ttk.Label(
            parent,
            text="I file selezionati nel tab precedente verranno sovrascritti con i "
                 "corrispondenti file sorgente.\n"
                 "Con il backup attivo l'operazione è reversibile dal pulsante "
                 "«Ripristina backup».",
            font=("Arial", 10), foreground="#666666",
        ).pack(anchor=tk.W, padx=24, pady=(0, 14))

        summary = ttk.LabelFrame(parent, text=" Riepilogo operazione ")
        summary.pack(fill=tk.X, padx=24, pady=6)
        self._replace_summary_lbl = ttk.Label(summary, text="Nessuna operazione in attesa.",
                                              font=("Arial", 10), justify=tk.LEFT)
        self._replace_summary_lbl.pack(padx=12, pady=10, anchor=tk.W)

        opts = ttk.Frame(parent)
        opts.pack(fill=tk.X, padx=24, pady=4)
        ttk.Checkbutton(
            opts,
            text="Crea backup dei file originali prima di sovrascrivere (suffisso .bak)",
            variable=self._backup_var, command=self._refresh_replace_summary,
        ).pack(anchor=tk.W)
        ttk.Checkbutton(
            opts,
            text="Simulazione (dry-run): esegue tutti i controlli senza modificare alcun file",
            variable=self._dry_run_var, command=self._refresh_replace_summary,
        ).pack(anchor=tk.W)

        log_frame = ttk.LabelFrame(parent, text=" Log operazioni ")
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
            btn_frame, text="⚡  ESEGUI SOSTITUZIONE", command=self._execute_replacement,
            width=28, **self.btn("danger"),
        )
        self._btn_execute.pack(side=tk.RIGHT, padx=4)

        ttk.Button(btn_frame, text="← Torna alle Corrispondenze",
                   command=lambda: self.notebook.select(2),
                   **self.btn("outline")).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Pulisci log", command=self._clear_log,
                   **self.btn("outline")).pack(side=tk.LEFT, padx=4)
        self._btn_restore = ttk.Button(
            btn_frame, text="↩  Ripristina backup", command=self._restore_backups,
            **self.btn("outline"),
        )
        self._btn_restore.pack(side=tk.LEFT, padx=4)

    # ------------------------------------------------------------------
    # Gestione operazioni in background
    # ------------------------------------------------------------------

    def _busy(self) -> bool:
        return self._worker is not None and self._worker.is_alive()

    def _start_worker(self, target, args=(), status: str = "Operazione in corso..."):
        """Avvia un'operazione lunga, impedendo esecuzioni concorrenti."""
        if self._busy():
            messagebox.showinfo("Operazione in corso",
                                "Attendi il completamento dell'operazione corrente.")
            return False

        self._cancel_event.clear()
        self._set_action_buttons(tk.DISABLED)
        self._btn_cancel.config(state=tk.NORMAL)
        self.progress_var.set(0)
        self._status(status)

        # Svuota qui, nel thread principale, la spazzatura ciclica ancora in
        # attesa, poi sospende il collector finché il worker è in esecuzione.
        #
        # Il distruttore di una miniatura Tk chiama l'interprete Tcl. Se il
        # collector la finalizza mentre gira su un thread di lavoro (può
        # scattare a ogni allocazione, ovunque), quella chiamata arriva da
        # fuori dal thread principale e blocca l'applicazione. Sospendendolo,
        # le uniche finalizzazioni possibili restano quelle per conteggio dei
        # riferimenti, che avvengono sul thread che rilascia l'oggetto.
        gc.collect()
        gc.disable()

        def runner():
            try:
                target(*args)
            except OperationCancelled:
                self.log("Operazione annullata dall'utente.", logging.WARNING)
                self._status("Operazione annullata.")
            except Exception as exc:
                self.logger.exception("Errore nell'operazione in background")
                self.log(f"Errore: {exc}", logging.ERROR)
                self._ui(lambda e=exc: messagebox.showerror("Errore", str(e)))
                self._status("Operazione terminata con errore.")
            finally:
                self._ui(self._worker_finished)

        self._worker = threading.Thread(target=runner, daemon=True)
        self._worker.start()
        return True

    def _worker_finished(self):
        # Riprende il collector e recupera qui, nel thread principale, tutto
        # ciò che si è accumulato durante l'operazione.
        gc.enable()
        gc.collect()
        self._set_action_buttons(tk.NORMAL)
        self._btn_cancel.config(state=tk.DISABLED)

    def _set_action_buttons(self, state):
        for btn in (self._btn_scan, self._btn_match, self._btn_execute, self._btn_restore):
            try:
                btn.config(state=state)
            except tk.TclError:
                pass

    def _request_cancel(self):
        if self._busy():
            self._cancel_event.set()
            self._status("Annullamento in corso...")

    def _on_close(self):
        if self._busy():
            if not messagebox.askyesno(
                "Operazione in corso",
                "Un'operazione è ancora in esecuzione.\nUscire comunque?",
            ):
                return
            self._cancel_event.set()

        self._closing = True
        self._save_settings()
        gc.enable()   # non lasciarlo sospeso se si esce durante un'operazione

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
            "source_folder": self.source_folder.get().strip(),
            "scan_folder": self.scan_folder.get().strip(),
            "search_pattern": self.search_pattern.get().strip(),
            "backup": self._backup_var.get(),
            "dry_run": self._dry_run_var.get(),
        })

    # ------------------------------------------------------------------
    # Azioni: Configurazione
    # ------------------------------------------------------------------

    def _browse_source_folder(self):
        folder = filedialog.askdirectory(
            title="Seleziona cartella sorgente (nuovi loghi)",
            initialdir=self.source_folder.get() or None,
        )
        if folder:
            self.source_folder.set(folder)

    def _browse_scan_folder(self):
        folder = filedialog.askdirectory(
            title="Seleziona cartella da scansionare",
            initialdir=self.scan_folder.get() or None,
        )
        if folder:
            self.scan_folder.set(folder)

    def _clear_fields(self):
        self.source_folder.set("")
        self.scan_folder.set("")
        self.search_pattern.set("logo*.png")

    def _open_log_folder(self):
        folder = core.writable_app_dir("logs")
        self._open_in_file_manager(folder)

    def _open_in_file_manager(self, path: str):
        try:
            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                webbrowser.open(Path(path).as_uri())
        except Exception as exc:
            messagebox.showinfo("Percorso", f"{path}\n\n(Apertura automatica non riuscita: {exc})")

    # ------------------------------------------------------------------
    # Azioni: Scansione
    # ------------------------------------------------------------------

    def _start_scan(self):
        source = self.source_folder.get().strip()
        scan = self.scan_folder.get().strip()
        pattern = self.search_pattern.get().strip()

        problems = core.validate_config(source, scan, pattern)
        if problems:
            messagebox.showerror("Configurazione non valida", "\n\n".join(problems))
            return

        for warning in core.config_warnings(source, scan):
            self.log(f"Avviso: {warning}", logging.WARNING)

        self._save_settings()
        self.scanned_files = []
        self.source_files = []
        self.matches = []
        self._match_by_path = {}
        self._clear_tree(self._scan_tree)
        self._clear_tree(self._match_tree)
        self._clear_previews()
        self._scan_count_lbl.config(text="Scansione in corso...")
        self._match_count_lbl.config(text="")
        self.notebook.select(1)

        self._start_worker(self._scan_worker, (source, scan, pattern),
                           "Scansione in corso...")

    def _scan_worker(self, source: str, scan: str, pattern: str):
        self.log(f"Scansione avviata — cartella: {scan} | pattern: {pattern}")
        self.log(f"Cartella sorgente loghi: {source}")

        def walk_error(path: str, exc: Exception):
            self.log(f"  Accesso negato o errore su {path}: {exc}", logging.WARNING)

        source_paths = core.collect_source_files(
            source, cancel_event=self._cancel_event, on_error=walk_error)
        self.log(f"File sorgente trovati: {len(source_paths)}")

        # La cartella sorgente, se annidata nella cartella scansionata, va
        # esclusa: altrimenti i nuovi loghi verrebbero trattati come target.
        exclude = [source] if core.is_within(source, scan) else []
        found = core.scan_files(scan, pattern, exclude_dirs=exclude,
                                cancel_event=self._cancel_event, on_error=walk_error)
        total = len(found)
        self.log(f"File corrispondenti al pattern: {total}")

        source_files: list[FileInfo] = []
        for index, path in enumerate(source_paths, 1):
            if self._cancel_event.is_set():
                raise OperationCancelled()
            try:
                source_files.append(FileInfo.from_path(path))
            except OSError as exc:
                self.log(f"  Sorgente illeggibile {path}: {exc}", logging.WARNING)
            self._set_progress(index / max(len(source_paths), 1) * 30,
                               f"Lettura sorgenti... {index}/{len(source_paths)}")

        scanned: list[FileInfo] = []
        for index, path in enumerate(found, 1):
            if self._cancel_event.is_set():
                raise OperationCancelled()
            try:
                scanned.append(FileInfo.from_path(path))
            except OSError as exc:
                self.log(f"  Errore su {path}: {exc}", logging.WARNING)
            self._set_progress(30 + index / max(total, 1) * 70,
                               f"Analisi file... {index}/{total}")

        self.source_files = source_files
        self.scanned_files = scanned
        self._ui(self._populate_scan_tree)

    def _populate_scan_tree(self):
        self._clear_tree(self._scan_tree)
        for index, info in enumerate(self.scanned_files, 1):
            self._scan_tree.insert(
                "", tk.END, iid=info.path,
                values=(index, info.name, info.fmt, info.size_str, info.dim_str, info.path),
            )

        count = len(self.scanned_files)
        self._scan_count_lbl.config(
            text=f"{count} file trovati — {len(self.source_files)} sorgenti disponibili")
        self.progress_var.set(100)
        self._status(f"Scansione completata: {count} file trovati.")
        self.log(f"Scansione completata: {count} file, "
                 f"{len(self.source_files)} sorgenti disponibili.")

        if count == 0:
            messagebox.showinfo(
                "Nessun risultato",
                "Nessun file corrisponde al pattern indicato.\n\n"
                "Verifica il pattern (es. logo*.png) e la cartella da scansionare.",
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
        if selection:
            self._open_in_file_manager(os.path.dirname(selection[0]))

    def _show_preview(self, info: FileInfo):
        self._preview_canvas.delete("all")
        thumb = self._make_thumbnail(info.path, PREVIEW_SIZE)
        if thumb:
            self._keep_image("scan", thumb)
            self._preview_canvas.create_image(60, 45, image=thumb, anchor=tk.CENTER)
        else:
            self._preview_canvas.create_text(60, 45, text="N/D", fill="#aaaaaa",
                                             font=("Arial", 11))

        self._preview_info.config(
            text=(f"Nome: {info.name}\n"
                  f"Formato: {info.fmt}\n"
                  f"Dimensione: {info.size_str}\n"
                  f"Risoluzione: {info.dim_str}\n"
                  f"Percorso: {info.path}"),
            foreground="#333333",
        )

    def _keep_image(self, slot: str, photo):
        """
        Trattiene una miniatura in un registro dell'applicazione.

        Il distruttore di `ImageTk.PhotoImage` chiama Tk per liberare
        l'immagine. Se l'oggetto finisce nella spazzatura ciclica, il garbage
        collector può eseguirne il finalizzatore su un thread qualsiasi:
        quando capita su un thread di lavoro, la chiamata a Tk da fuori dal
        thread principale blocca l'interprete e l'applicazione si pianta.

        Tenendo un riferimento forte qui le miniature restano raggiungibili e
        non diventano mai spazzatura; vengono rilasciate esplicitamente da
        `_release_images`, che gira nel thread principale.
        """
        self._image_refs[slot] = photo
        return photo

    def _release_images(self):
        """Libera le miniature. Da chiamare solo dal thread principale."""
        self._image_refs.clear()
        # Raccoglie subito, qui e ora, gli eventuali cicli rimasti: così i
        # finalizzatori girano su questo thread e non su un worker.
        gc.collect()

    @staticmethod
    def _make_thumbnail(filepath: str, size):
        """
        Miniatura per l'anteprima. Il file viene chiuso subito: tenerlo aperto
        impedirebbe di sovrascriverlo su Windows.
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
    # Azioni: Abbinamento
    # ------------------------------------------------------------------

    def _start_matching(self):
        if not self.scanned_files:
            messagebox.showwarning("Attenzione",
                                   "Nessun file trovato nella scansione.\n"
                                   "Esegui prima la scansione.")
            return
        if not self.source_files:
            messagebox.showwarning("Attenzione",
                                   "Nessun file immagine nella cartella sorgente.")
            return

        self.matches = []
        self._match_by_path = {}
        self._clear_tree(self._match_tree)
        self._match_count_lbl.config(text="Analisi in corso...")
        self.notebook.select(2)
        self._start_worker(self._match_worker, (), "Analisi corrispondenze in corso...")

    def _match_worker(self):
        total = len(self.scanned_files)
        self.log(f"Avvio abbinamento: {total} file da analizzare, "
                 f"{len(self.source_files)} sorgenti disponibili.")

        def progress(done: int, of: int):
            self._set_progress(done / max(of, 1) * 100, f"Abbinamento... {done}/{of}")

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
        weak = sum(1 for m in self.matches if m.source is not None and m.quality == "Debole")
        total = len(self.matches)

        label = f"{total} file analizzati: {matched} corrispondenze"
        if total - matched:
            label += f", {total - matched} senza corrispondenza"
        if weak:
            label += f", {weak} da verificare"
        self._match_count_lbl.config(text=label)
        self.progress_var.set(100)
        self._status(label)
        self.log(f"Abbinamento completato: {matched}/{total} corrispondenze "
                 f"({weak} deboli).")

    @staticmethod
    def _match_row(index: int, match: Match) -> tuple:
        return (
            index,
            "✓" if match.enabled else "✗",
            match.target.name,
            match.target.fmt,
            match.target.dim_str,
            match.source_name,
            match.source_dim_str,
            match.quality,
            match.target.path,
        )

    @staticmethod
    def _row_tag(match: Match) -> str:
        if match.source is None:
            return "no_match"
        if not match.enabled:
            return "disabled"
        return "weak" if match.quality == "Debole" else "matched"

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
        if self._match_tree.identify_column(event.x) != "#2":  # colonna ✓
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
        thumb = self._make_thumbnail(match.target.path, MATCH_PREVIEW_SIZE)
        if thumb:
            self._keep_image("match_target", thumb)
            self._target_canvas.create_image(45, 35, image=thumb, anchor=tk.CENTER)
        else:
            self._target_canvas.create_text(45, 35, text="N/D", fill="#aaaaaa")

        self._target_preview_info.config(
            text=(f"Nome: {match.target.name}\n"
                  f"Formato: {match.target.fmt}\n"
                  f"Dim: {match.target.dim_str}\n"
                  f"Peso: {match.target.size_str}")
        )

        self._src_canvas.delete("all")
        if match.source is None:
            self._src_canvas.create_text(45, 35, text="Nessun\nMatch", fill="#cc4444")
            self._src_preview_info.config(text="Corrispondenza non trovata.\n"
                                               "Doppio clic per sceglierla a mano.")
            return

        src_thumb = self._make_thumbnail(match.source.path, MATCH_PREVIEW_SIZE)
        if src_thumb:
            self._keep_image("match_source", src_thumb)
            self._src_canvas.create_image(45, 35, image=src_thumb, anchor=tk.CENTER)
        else:
            self._src_canvas.create_text(45, 35, text="N/D", fill="#aaaaaa")

        self._src_preview_info.config(
            text=(f"Nome: {match.source.name}\n"
                  f"Formato: {match.source.fmt}\n"
                  f"Dim: {match.source.dim_str}\n"
                  f"Qualità: {match.quality}")
        )

    def _choose_source_dialog(self, row_id: str) -> tk.Toplevel | None:
        """
        Permette di scegliere manualmente il file sorgente per una riga.
        Restituisce la finestra creata (utile ai test), o None se non applicabile.
        """
        match = self._match_by_path.get(row_id)
        if not match:
            return None
        if not self.source_files:
            messagebox.showinfo("Nessun sorgente", "La cartella sorgente non contiene file.")
            return None

        # I sorgenti dello stesso formato per primi, ordinati per idoneità.
        target_ext = core.normalized_ext(match.target.ext)
        ordered = sorted(
            self.source_files,
            key=lambda s: (
                core.normalized_ext(s.ext) != target_ext,
                core.match_score(match.target.dim, s.dim, match.target.path, s.path),
            ),
        )

        dialog = tk.Toplevel(self.root)
        dialog.title(f"Scegli sorgente per {match.target.name}")
        dialog.transient(self.root)
        dialog.geometry("640x420")

        ttk.Label(dialog,
                  text=f"File da sostituire: {match.target.name} "
                       f"({match.target.fmt}, {match.target.dim_str})",
                  font=("Arial", 10, "bold")).pack(anchor=tk.W, padx=12, pady=(12, 4))
        ttk.Label(dialog,
                  text="I sorgenti dello stesso formato sono elencati per primi.",
                  font=("Arial", 9), foreground="#666666").pack(anchor=tk.W, padx=12)

        list_frame = ttk.Frame(dialog)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)
        listbox = tk.Listbox(list_frame, activestyle="dotbox")
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=listbox.yview)
        listbox.configure(yscrollcommand=scrollbar.set)
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        for info in ordered:
            flag = "" if core.normalized_ext(info.ext) == target_ext else "  [formato diverso]"
            listbox.insert(tk.END, f"{info.name}  —  {info.dim_str}, {info.size_str}{flag}")

        if match.source is not None:
            try:
                listbox.selection_set(ordered.index(match.source))
                listbox.see(ordered.index(match.source))
            except ValueError:
                pass

        def confirm():
            selection = listbox.curselection()
            if not selection:
                messagebox.showwarning("Attenzione", "Seleziona un file sorgente.",
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
            self.log(f"Sorgente impostato manualmente per {match.target.name}: "
                     f"{chosen.name}")
            dialog.destroy()

        buttons = ttk.Frame(dialog)
        buttons.pack(fill=tk.X, padx=12, pady=(0, 12))
        ttk.Button(buttons, text="Conferma", command=confirm,
                   **self.btn("primary")).pack(side=tk.RIGHT, padx=4)
        ttk.Button(buttons, text="Annulla", command=dialog.destroy,
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
            messagebox.showinfo("Nessun dato", "Esegui prima l'analisi delle corrispondenze.")
            return
        destination = filedialog.asksaveasfilename(
            title="Esporta corrispondenze",
            defaultextension=".csv",
            initialfile="corrispondenze.csv",
            filetypes=[("CSV", "*.csv"), ("Tutti i file", "*.*")],
        )
        if not destination:
            return
        try:
            core.export_matches_csv(self.matches, destination)
            self.log(f"Corrispondenze esportate in {destination}")
            messagebox.showinfo("Esportazione completata", f"File salvato:\n{destination}")
        except OSError as exc:
            messagebox.showerror("Errore esportazione", str(exc))

    # ------------------------------------------------------------------
    # Azioni: Sostituzione
    # ------------------------------------------------------------------

    def _enabled_matches(self) -> list[Match]:
        return [m for m in self.matches if m.enabled and m.source is not None]

    def _go_to_replace(self):
        if not self._enabled_matches():
            messagebox.showwarning("Attenzione", "Nessuna sostituzione selezionata.")
            return
        self.notebook.select(3)

    def _on_tab_changed(self, _event=None):
        # Il riepilogo va ricalcolato anche quando si arriva al tab 4
        # direttamente dalla barra dei tab, non solo dal pulsante «Procedi».
        if self.notebook.index("current") == 3:
            self._refresh_replace_summary()

    def _refresh_replace_summary(self):
        enabled = self._enabled_matches()
        if not enabled:
            self._replace_summary_lbl.config(
                text="Nessuna sostituzione selezionata.\n"
                     "Torna al tab ③ e seleziona almeno una corrispondenza.")
            return

        if self._dry_run_var.get():
            mode = "SIMULAZIONE ATTIVA: nessun file verrà modificato."
        elif self._backup_var.get():
            mode = "I file originali verranno salvati con estensione .bak (ripristinabili)."
        else:
            mode = "BACKUP DISATTIVO: i file originali saranno sovrascritti definitivamente."

        weak = sum(1 for m in enabled if m.quality == "Debole")
        text = (f"Verranno sostituiti {len(enabled)} file su "
                f"{len(self.matches)} analizzati.\n{mode}")
        if weak:
            text += f"\n⚠  {weak} abbinamenti sono classificati «Debole»: verificali nel tab ③."
        self._replace_summary_lbl.config(text=text)

    def _execute_replacement(self):
        enabled = self._enabled_matches()
        if not enabled:
            messagebox.showwarning("Attenzione", "Nessuna sostituzione da eseguire.")
            return

        do_backup = self._backup_var.get()
        dry_run = self._dry_run_var.get()

        if dry_run:
            question = (f"Simulazione su {len(enabled)} file.\n\n"
                        "Nessun file verrà modificato.\n\nContinuare?")
        else:
            question = (f"Stai per sovrascrivere {len(enabled)} file.\n\n"
                        f"Backup: {'SÌ' if do_backup else 'NO — operazione irreversibile'}\n\n"
                        "Continuare?")
        if not messagebox.askyesno("Conferma Sostituzione", question):
            return

        self._save_settings()
        # Le anteprime tengono un riferimento alle immagini: su Windows
        # impedirebbero la sovrascrittura dei file target.
        self._clear_previews()
        self._start_worker(self._replace_worker, (enabled, do_backup, dry_run),
                           "Sostituzione in corso...")

    def _replace_worker(self, matches: list[Match], do_backup: bool, dry_run: bool):
        prefix = "SIMULAZIONE" if dry_run else "SOSTITUZIONE"
        self.log(f"=== INIZIO {prefix}: {len(matches)} file "
                 f"(backup: {'sì' if do_backup else 'no'}) ===")

        def progress(done: int, of: int, outcome: core.ReplaceOutcome):
            name = os.path.basename(outcome.target)
            if outcome.status == "ok":
                if dry_run:
                    self.log(f"  ○ [simulato] {name}  ←  {os.path.basename(outcome.source)}")
                else:
                    if outcome.backup:
                        self.log(f"  backup: {outcome.backup}")
                    self.log(f"  ✅ Sostituito: {name}  ←  {os.path.basename(outcome.source)}")
            elif outcome.status == "skipped":
                self.log(f"  ⏭ Saltato {name}: {outcome.message}", logging.WARNING)
            else:
                self.log(f"  ❌ Errore su {name}: {outcome.message}", logging.ERROR)
            self._set_progress(done / max(of, 1) * 100, f"{prefix.title()}... {done}/{of}")

        report = core.replace_all(matches, backup=do_backup, dry_run=dry_run,
                                  progress=progress, cancel_event=self._cancel_event)

        self.log(f"=== {prefix} COMPLETATA: {report.ok} ok, {report.skipped} saltati, "
                 f"{report.errors} errori su {report.total} file ===")
        self._ui(lambda: self._replacement_done(report, dry_run))

    def _replacement_done(self, report: core.ReplaceReport, dry_run: bool):
        self.progress_var.set(100)
        summary = (f"{'Simulazione' if dry_run else 'Sostituzione'} completata: "
                   f"{report.ok} ok, {report.skipped} saltati, {report.errors} errori.")
        self._status(summary)

        detail = (f"File elaborati: {report.total}\n"
                  f"Completati: {report.ok}\n"
                  f"Saltati: {report.skipped}\n"
                  f"Errori: {report.errors}")
        if report.cancelled:
            detail += "\n\nOperazione interrotta dall'utente."

        if report.errors:
            messagebox.showwarning("Completato con errori",
                                   f"{detail}\n\nConsulta il log per i dettagli.")
        elif dry_run:
            messagebox.showinfo("Simulazione completata",
                                f"{detail}\n\nNessun file è stato modificato.")
        else:
            messagebox.showinfo("Completato",
                                f"✅ Sostituzione completata con successo!\n\n{detail}")

        if not dry_run and report.ok:
            self._ask_export_report(report)

    def _ask_export_report(self, report: core.ReplaceReport):
        if not messagebox.askyesno("Report", "Vuoi salvare un report CSV dell'operazione?"):
            return
        destination = filedialog.asksaveasfilename(
            title="Salva report", defaultextension=".csv",
            initialfile="report_sostituzione.csv",
            filetypes=[("CSV", "*.csv"), ("Tutti i file", "*.*")],
        )
        if not destination:
            return
        try:
            core.export_report_csv(report, destination)
            self.log(f"Report salvato in {destination}")
        except OSError as exc:
            messagebox.showerror("Errore salvataggio report", str(exc))

    def _restore_backups(self):
        folder = self.scan_folder.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showerror("Errore", "Seleziona una cartella da scansionare valida "
                                           "nel tab ① prima di ripristinare.")
            return

        backups = core.find_backups(folder)
        if not backups:
            messagebox.showinfo("Nessun backup",
                                f"Nessun file .bak trovato in:\n{folder}")
            return

        distinct = len({core.backup_origin(b) for b in backups})
        if not messagebox.askyesno(
            "Conferma ripristino",
            f"Trovati {len(backups)} backup relativi a {distinct} file in:\n{folder}\n\n"
            "I file correnti verranno riportati alla versione precedente al rebranding.\n\n"
            "Continuare?",
        ):
            return

        remove = messagebox.askyesno(
            "Backup",
            "Vuoi eliminare i file .bak dopo il ripristino?\n\n"
            "Scegli «No» per conservarli.",
        )
        self._clear_previews()
        self._start_worker(self._restore_worker, (folder, remove), "Ripristino in corso...")

    def _restore_worker(self, folder: str, remove: bool):
        self.log(f"=== INIZIO RIPRISTINO da {folder} ===")

        def progress(done: int, of: int, outcome: core.ReplaceOutcome):
            name = os.path.basename(outcome.target)
            if outcome.ok:
                self.log(f"  ↩ Ripristinato: {name}")
            else:
                self.log(f"  ❌ Errore ripristino {name}: {outcome.message}", logging.ERROR)
            self._set_progress(done / max(of, 1) * 100, f"Ripristino... {done}/{of}")

        report = core.restore_backups(folder, remove_backup=remove, progress=progress,
                                      cancel_event=self._cancel_event)
        self.log(f"=== RIPRISTINO COMPLETATO: {report.ok} ok, {report.errors} errori ===")

        def done():
            self.progress_var.set(100)
            self._status(f"Ripristino completato: {report.ok} ok, {report.errors} errori.")
            messagebox.showinfo(
                "Ripristino completato",
                f"File ripristinati: {report.ok}\nErrori: {report.errors}",
            )

        self._ui(done)

    # ------------------------------------------------------------------
    # Utilità UI
    # ------------------------------------------------------------------

    def _sort_tree(self, tree: ttk.Treeview, col: str):
        """
        Ordina una colonna alternando crescente/decrescente.

        L'ordinamento è consapevole del tipo: le colonne numeriche e quelle
        con unità di misura venivano prima ordinate come testo, mettendo
        «10» prima di «2».
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
        Valore numerico da una cella formattata (`1.5 MB`, `800×600 px`).
        Per le risoluzioni usa l'area, così l'ordinamento è sensato.
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
        Svuota le anteprime rilasciando i riferimenti alle immagini.
        Serve anche a sbloccare i file su Windows prima di sovrascriverli.
        """
        for canvas in (self._preview_canvas, self._target_canvas, self._src_canvas):
            canvas.delete("all")
        self._release_images()
        self.root.update_idletasks()

    def _clear_log(self):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)


# Compatibilità: alcuni script importavano queste utility da questo modulo.
get_base_path = core.get_base_path
resource_path = core.resource_path
scan_files = core.scan_files
get_image_dimensions = core.get_image_dimensions
size_diff = core.size_diff
SUPPORTED_FORMATS = core.SUPPORTED_FORMATS
