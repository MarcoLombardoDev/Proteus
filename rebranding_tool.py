#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Rebranding Tool - Strumento per la sostituzione massiva di file grafici/logo.
SACE S.p.A - Modulo principale applicazione.
"""

import os
import sys
import re
import fnmatch
import shutil
import logging
import threading
import datetime
import queue
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import ttkbootstrap as tb
    BOOTSTRAP_AVAILABLE = True
    BOOTSTRAP_ERROR = None
except Exception as e:
    tb = None
    BOOTSTRAP_AVAILABLE = False
    BOOTSTRAP_ERROR = str(e)

# ---------------------------------------------------------------------------
# Costanti applicazione
# ---------------------------------------------------------------------------
APP_NAME = "Rebranding Tool"
APP_VERSION = "1.0"
APP_COMPANY = "SACE S.p.A"

# Formati immagine supportati
SUPPORTED_FORMATS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif",
    ".svg", ".ico", ".webp", ".eps", ".pdf"
}

# Dimensione anteprima miniatura
THUMB_SIZE = (80, 80)

# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def get_base_path() -> str:
    """Restituisce il path base dell'applicazione (eseguibile o script)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(relative: str) -> str:
    """Percorso resource corretto sia per script che per PyInstaller."""
    base = getattr(sys, "_MEIPASS", get_base_path())
    return os.path.join(base, relative)


def format_size(size_bytes: int) -> str:
    """Formatta dimensione in bytes in stringa leggibile."""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def get_image_dimensions(filepath: str):
    """Ritorna (width, height) o None se non leggibile come immagine."""
    if not PIL_AVAILABLE:
        return None
    ext = Path(filepath).suffix.lower()
    if ext in (".svg", ".eps", ".pdf"):
        return None  # Non apribili con PIL direttamente
    try:
        with Image.open(filepath) as img:
            return img.size  # (width, height)
    except Exception:
        return None


def size_diff(dim1, dim2) -> float:
    """Differenza normalizzata tra due dimensioni (w,h). 0=identiche."""
    if dim1 is None or dim2 is None:
        return float("inf")
    w1, h1 = dim1
    w2, h2 = dim2
    # Differenza euclidea normalizzata
    return ((w1 - w2) ** 2 + (h1 - h2) ** 2) ** 0.5


def make_thumbnail(filepath: str, size=THUMB_SIZE):
    """
    Crea un ImageTk.PhotoImage thumbnail dal file.
    Ritorna None se impossibile.
    Assicura la chiusura del file per evitare blocchi (file locking).
    """
    if not PIL_AVAILABLE:
        return None
    ext = Path(filepath).suffix.lower()
    if ext in (".svg", ".eps", ".pdf"):
        return None
    try:
        with Image.open(filepath) as img:
            img.thumbnail(size, Image.Resampling.LANCZOS)
            # PhotoImage crea una copia interna dei dati
            return ImageTk.PhotoImage(img)
    except Exception:
        return None


def scan_files(folder: str, pattern: str) -> list:
    """
    Scansiona folder ricorsivamente cercando file che corrispondono
    al pattern (supporta wildcard come logo*.png).
    Ritorna lista di path assoluti.
    """
    results = []
    pattern_lower = pattern.lower()
    for root, dirs, files in os.walk(folder):
        for fname in files:
            if fnmatch.fnmatch(fname.lower(), pattern_lower):
                full = os.path.join(root, fname)
                results.append(full)
    return sorted(results)


def find_best_match(target_path: str, source_files: list) -> str | None:
    """
    Trova il file sorgente più adatto per sostituire target_path.
    Criteri:
      1. Stesso formato/estensione
      2. Dimensione (pixel) più vicina possibile
    Ritorna il path sorgente migliore o None.
    """
    target_ext = Path(target_path).suffix.lower()
    target_dim = get_image_dimensions(target_path)

    # Filtra per stesso formato
    candidates = [f for f in source_files if Path(f).suffix.lower() == target_ext]

    if not candidates:
        return None

    if target_dim is None:
        # Non possiamo misurare dimensione: ritorna il primo candidato
        return candidates[0]

    # Ordina per differenza di dimensione
    def score(src):
        src_dim = get_image_dimensions(src)
        return size_diff(target_dim, src_dim)

    candidates.sort(key=score)
    return candidates[0]


# ---------------------------------------------------------------------------
# Classe principale applicazione
# ---------------------------------------------------------------------------

class RebrandingToolApp:
    """Applicazione principale del Rebranding Tool."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"{APP_NAME} - {APP_COMPANY}")
        self.root.geometry("1100x750")
        self.root.minsize(900, 650)

        # --- Variabili di stato ---
        self.source_folder = tk.StringVar()
        self.scan_folder = tk.StringVar()
        self.search_pattern = tk.StringVar(value="logo*.png")

        # Dati elaborazione
        self.scanned_files: list[dict] = []       # [{path, name, ext, size, dim, thumb}]
        self.source_files: list[str] = []         # path file sorgente
        self.matches: list[dict] = []             # [{target:dict, best_src:str, enabled:bool, thumb_src}]
        self.thumbnail_refs: list = []            # Riferimenti PhotoImage (anti-GC)

        # Coda UI thread-safe
        self.ui_queue: queue.Queue = queue.Queue()

        # Progressbar & log
        self.progress_var = tk.DoubleVar(value=0)
        self.log_messages: list[str] = []

        # --- Setup ---
        self._setup_logging()
        self._set_window_icon()
        self._apply_theme()
        self._create_widgets()
        self._process_ui_queue()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_logging(self):
        self.logger = logging.getLogger("rebranding_tool")
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            try:
                log_dir = os.path.join(get_base_path(), "logs")
                os.makedirs(log_dir, exist_ok=True)
                fname = f"rebranding_{datetime.datetime.now().strftime('%Y%m%d')}.log"
                fh = logging.FileHandler(os.path.join(log_dir, fname), encoding="utf-8")
                fh.setLevel(logging.INFO)
                fmt = logging.Formatter("[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
                fh.setFormatter(fmt)
                self.logger.addHandler(fh)
            except Exception as exc:
                print(f"Logging non inizializzato su file: {exc}")

    def _set_window_icon(self):
        icon = resource_path("sace.ico")
        if os.path.exists(icon):
            try:
                self.root.iconbitmap(icon)
            except Exception:
                pass

    def _apply_theme(self):
        self.bs_available = BOOTSTRAP_AVAILABLE
        if self.bs_available:
            try:
                self.style = tb.Style("flatly")
                # Definizione stile personalizzato per i bottoni #3365ae (SENZA BORDI)
                self.style.configure('Custom.TButton', font=('Arial', 9, 'bold'), 
                                   background='#3365ae', foreground='white', borderwidth=0)
                self.style.map('Custom.TButton',
                               background=[('active', '#28508a'), ('pressed', '#1e3c6a')],
                               foreground=[('active', 'white')])
                
            except Exception:
                self.bs_available = False

    def bs(self, style: str) -> dict:
        # Se lo stile richiesto è "outline" o contiene "outline", usiamo lo stile originale ttkbootstrap (bianco)
        if "outline" in style:
            # Riduciamo comunque il bordo o lo rendiamo coerente se possibile tramite bootstyle
            return {"bootstyle": style} if self.bs_available else {}
        
        # Altrimenti usiamo il nostro stile pieno #3365ae senza bordi
        return {"style": "Custom.TButton"} if self.bs_available else {}

    # ------------------------------------------------------------------
    # Aggiornamento UI thread-safe
    # ------------------------------------------------------------------

    def _process_ui_queue(self):
        try:
            while not self.ui_queue.empty():
                fn = self.ui_queue.get_nowait()
                fn()
        except queue.Empty:
            pass
        except Exception as exc:
            self.log(f"Errore queue UI: {exc}", logging.ERROR)
        self.root.after(100, self._process_ui_queue)

    def _ui(self, fn):
        """Accoda una funzione da eseguire nel main thread."""
        self.ui_queue.put(fn)

    # ------------------------------------------------------------------
    # Log
    # ------------------------------------------------------------------

    def log(self, message: str, level=logging.INFO):
        self.logger.log(level, message)
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        entry = f"[{ts}] {message}"
        self.log_messages.append(entry)
        self._ui(lambda e=entry: self._append_log(e))

    def _append_log(self, entry: str):
        if hasattr(self, "log_text"):
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, entry + "\n")
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)

    # ------------------------------------------------------------------
    # Creazione widget
    # ------------------------------------------------------------------

    def _create_widgets(self):
        # Notebook principale
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # Versione label sovrapposta al notebook
        ver_lbl = ttk.Label(
            self.root,
            text=f"VERSIONE {APP_VERSION} - ©{APP_COMPANY}",
            font=("Arial", 8),
            foreground="#888888"
        )
        ver_lbl.place(relx=1.0, y=10, anchor=tk.NE, x=-12)

        # Tab 1 - Configurazione
        self._frame_config = ttk.Frame(self.notebook)
        self.notebook.add(self._frame_config, text="  ① CONFIGURAZIONE  ")
        self._build_config_tab(self._frame_config)

        # Tab 2 - Risultati scansione
        self._frame_scan = ttk.Frame(self.notebook)
        self.notebook.add(self._frame_scan, text="  ② RISULTATI SCANSIONE  ")
        self._build_scan_tab(self._frame_scan)

        # Tab 3 - Corrispondenze
        self._frame_match = ttk.Frame(self.notebook)
        self.notebook.add(self._frame_match, text="  ③ CORRISPONDENZE  ")
        self._build_match_tab(self._frame_match)

        # Tab 4 - Sostituzione
        self._frame_replace = ttk.Frame(self.notebook)
        self.notebook.add(self._frame_replace, text="  ④ SOSTITUZIONE  ")
        self._build_replace_tab(self._frame_replace)

        # Status bar
        status_bar = ttk.Frame(self.root, relief=tk.SUNKEN)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM, padx=8, pady=(0, 6))
        self.status_label = ttk.Label(status_bar, text="Pronto", anchor=tk.W)
        self.status_label.pack(side=tk.LEFT, padx=6)

    # ------------------------------------------------------------------
    # TAB 1 - CONFIGURAZIONE
    # ------------------------------------------------------------------

    def _build_config_tab(self, parent: ttk.Frame):
        # Titolo (formattato come Tab 3)
        top = ttk.Frame(parent)
        top.pack(fill=tk.X, padx=8, pady=(12, 4))
        
        ttk.Label(
            top,
            text="Configurazione Ricerca",
            font=("Arial", 13, "bold")
        ).pack(side=tk.LEFT, padx=16)

        ttk.Label(
            parent,
            text="Imposta le cartelle e la chiave di ricerca, poi avvia la scansione.",
            font=("Arial", 10),
            foreground="#666666"
        ).pack(anchor=tk.W, padx=24, pady=(0, 16))

        # --- Sezione: Cartella SORGENTE ---
        src_frame = ttk.LabelFrame(parent, text=" CARTELLA SORGENTE (nuovi loghi) ")
        src_frame.pack(fill=tk.X, padx=24, pady=6)

        ttk.Label(
            src_frame,
            text="Cartella contenente i nuovi file logo (sorgente della sostituzione):",
            font=("Arial", 9),
            foreground="#555555"
        ).grid(row=0, column=0, columnspan=3, sticky=tk.W, padx=8, pady=(8, 2))

        ttk.Label(src_frame, text="Percorso:").grid(row=1, column=0, sticky=tk.W, padx=8, pady=4)
        self._entry_source = ttk.Entry(src_frame, textvariable=self.source_folder, width=68)
        self._entry_source.grid(row=1, column=1, padx=4, pady=4, sticky=tk.EW)
        ttk.Button(
            src_frame, text="Sfoglia...",
            command=self._browse_source_folder,
            **self.bs("info-outline")
        ).grid(row=1, column=2, padx=8, pady=4)
        src_frame.columnconfigure(1, weight=1)

        # --- Sezione: Cartella DA SCANSIONARE ---
        scan_frame = ttk.LabelFrame(parent, text=" CARTELLA DA SCANSIONARE ")
        scan_frame.pack(fill=tk.X, padx=24, pady=6)

        ttk.Label(
            scan_frame,
            text="Cartella (e sottocartelle) dove cercare i file da sostituire (es. server, share di rete):",
            font=("Arial", 9),
            foreground="#555555"
        ).grid(row=0, column=0, columnspan=3, sticky=tk.W, padx=8, pady=(8, 2))

        ttk.Label(scan_frame, text="Percorso:").grid(row=1, column=0, sticky=tk.W, padx=8, pady=4)
        self._entry_scan = ttk.Entry(scan_frame, textvariable=self.scan_folder, width=68)
        self._entry_scan.grid(row=1, column=1, padx=4, pady=4, sticky=tk.EW)
        ttk.Button(
            scan_frame, text="Sfoglia...",
            command=self._browse_scan_folder,
            **self.bs("info-outline")
        ).grid(row=1, column=2, padx=8, pady=4)
        scan_frame.columnconfigure(1, weight=1)

        # --- Sezione: CHIAVE DI RICERCA ---
        key_frame = ttk.LabelFrame(parent, text=" CHIAVE DI RICERCA ")
        key_frame.pack(fill=tk.X, padx=24, pady=6)

        ttk.Label(
            key_frame,
            text="Pattern di ricerca con supporto wildcard (* = qualsiasi carattere, ? = singolo carattere).\n"
                 "Esempi: logo*.png  |  banner_*.jpg  |  icon_*.svg  |  *.png",
            font=("Arial", 9),
            foreground="#555555",
            justify=tk.LEFT
        ).grid(row=0, column=0, columnspan=3, sticky=tk.W, padx=8, pady=(8, 2))

        ttk.Label(key_frame, text="Pattern:").grid(row=1, column=0, sticky=tk.W, padx=8, pady=4)
        self._entry_pattern = ttk.Entry(key_frame, textvariable=self.search_pattern, width=40)
        self._entry_pattern.grid(row=1, column=1, padx=4, pady=4, sticky=tk.W)
        key_frame.columnconfigure(1, weight=1)

        # --- PIL Warning ---
        if not PIL_AVAILABLE:
            warn_frame = ttk.Frame(parent)
            warn_frame.pack(fill=tk.X, padx=24, pady=4)
            ttk.Label(
                warn_frame,
                text="⚠️  Pillow (PIL) non installato: le anteprime immagini non saranno disponibili. "
                     "Installa con: pip install pillow",
                font=("Arial", 9),
                foreground="#cc6600"
            ).pack(anchor=tk.W)

        # --- Pulsanti azione (in fondo) ---
        # DEFINIAMO E POSIZIONIAMO PRIMA I BOTTONI IN FONDO
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=24, pady=20)

        ttk.Button(
            btn_frame,
            text="🔍  AVVIA SCANSIONE",
            command=self._start_scan,
            width=26,
            **self.bs("success")
        ).pack(side=tk.RIGHT, padx=4)

        ttk.Button(
            btn_frame,
            text="Pulisci campi",
            command=self._clear_fields,
            **self.bs("secondary-outline")
        ).pack(side=tk.RIGHT, padx=4)

        # --- Immagine Banner (Spazio flessibile centrale) ---
        banner_container = ttk.Frame(parent)
        banner_container.pack(fill=tk.BOTH, expand=True, padx=24, pady=10)
        
        if PIL_AVAILABLE:
            try:
                # Utilizziamo la funzione resource_path già definita per sicurezza
                banner_path = resource_path("banner.jpg")
                
                if os.path.exists(banner_path):
                    with Image.open(banner_path) as img:
                        # Ridimensionamento proporzionale (max larghezza 900px, max altezza 300px)
                        max_w = 900
                        max_h = 300
                        
                        # Calcola il fattore di scala più ristretto
                        ratio = min(max_w / img.width, max_h / img.height)
                        if ratio < 1:
                            new_w = int(img.width * ratio)
                            new_h = int(img.height * ratio)
                            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                        
                        banner_photo = ImageTk.PhotoImage(img)
                        self._banner_ref = banner_photo  # Riferimento nell'istanza (anti-GC)
                        
                        banner_label = ttk.Label(banner_container, image=banner_photo)
                        banner_label.image = banner_photo  # Riferimento sul widget (doppia sicurezza)
                        banner_label.pack(expand=True)
                else:
                    self.log(f"File banner.jpg non trovato in: {banner_path}", logging.WARNING)
            except Exception as e:
                self.log(f"Errore caricamento banner.jpg: {e}", logging.ERROR)
        else:
            self.log("Libreria Pillow non rilevata, impossibile mostrare banner.jpg", logging.WARNING)

    # ------------------------------------------------------------------
    # TAB 2 - RISULTATI SCANSIONE
    # ------------------------------------------------------------------

    def _build_scan_tab(self, parent: ttk.Frame):
        # Titolo + counter
        top = ttk.Frame(parent)
        top.pack(fill=tk.X, padx=8, pady=(12, 4))

        ttk.Label(top, text="Risultati Scansione", font=("Arial", 13, "bold")).pack(side=tk.LEFT)
        self._scan_count_lbl = ttk.Label(top, text="Nessuna scansione effettuata", foreground="#888888")
        self._scan_count_lbl.pack(side=tk.RIGHT, padx=8)
        
        ttk.Label(
            parent,
            text="Analizza il risultato della ricerca e avvia l'analisi per trovare le migliori corrispondenze.",
            font=("Arial", 10),
            foreground="#666666"
        ).pack(anchor=tk.W, padx=8, pady=(0, 10))

        # Treeview con colonne
        columns = ("#", "name", "ext", "size", "dim", "path")
        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        self._scan_tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="headings",
            height=12,
            selectmode="extended"
        )

        hdrs = {
            "#":    ("#", 40),
            "name": ("Nome File", 180),
            "ext":  ("Formato", 70),
            "size": ("Dimensione", 100),
            "dim":  ("Risoluzione", 120),
            "path": ("Percorso Completo", 460),
        }
        for col, (label, w) in hdrs.items():
            self._scan_tree.heading(col, text=label, command=lambda c=col: self._sort_tree(self._scan_tree, c))
            self._scan_tree.column(col, width=w, minwidth=60)

        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self._scan_tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self._scan_tree.xview)
        self._scan_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self._scan_tree.grid(row=0, column=0, sticky=tk.NSEW)
        vsb.grid(row=0, column=1, sticky=tk.NS)
        hsb.grid(row=1, column=0, sticky=tk.EW)
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        # Binding selezione → anteprima
        self._scan_tree.bind("<<TreeviewSelect>>", self._on_scan_select)

        # Panel anteprima destra
        preview_outer = ttk.LabelFrame(parent, text=" Anteprima ")
        preview_outer.pack(fill=tk.X, padx=8, pady=4)

        self._preview_canvas = tk.Canvas(preview_outer, width=120, height=90, bg="#f5f5f5", highlightthickness=1,
                                         highlightbackground="#cccccc")
        self._preview_canvas.pack(side=tk.LEFT, padx=8, pady=6)

        self._preview_info = ttk.Label(preview_outer, text="Seleziona un file per l'anteprima",
                                       font=("Arial", 9), foreground="#888888", justify=tk.LEFT)
        self._preview_info.pack(side=tk.LEFT, padx=12, pady=6, anchor=tk.W)

        # Bottoni
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, padx=8, pady=8)

        ttk.Button(
            btn_frame,
            text="🔗  TROVA CORRISPONDENZE",
            command=self._start_matching,
            width=36,
            **self.bs("primary")
        ).pack(side=tk.RIGHT, padx=4)

        ttk.Button(
            btn_frame,
            text="← Torna alla Configurazione",
            command=lambda: self.notebook.select(0),
            **self.bs("secondary-outline")
        ).pack(side=tk.LEFT, padx=4)

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
            text="Ogni file trovato viene abbinato al file sorgente più idoneo (stesso formato, "
                 "dimensione più simile).\nVedi l'anteprima e se necessario escludi le righe che non vuoi processare.",
            font=("Arial", 9),
            foreground="#555555",
            justify=tk.LEFT
        ).pack(anchor=tk.W, padx=8, pady=(0, 6))

        # Treeview corrispondenze
        col_match = ("#", "chk", "target_name", "target_fmt", "target_dim", "src_name", "src_dim", "target_path")
        mf = ttk.Frame(parent)
        mf.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        self._match_tree = ttk.Treeview(
            mf,
            columns=col_match,
            show="headings",
            height=14,
            selectmode="browse"
        )

        match_hdrs = {
            "#":           ("#", 40),
            "chk":         ("✓", 30),
            "target_name": ("File da Sostituire", 190),
            "target_fmt":  ("Formato", 70),
            "target_dim":  ("Dimensione Target", 130),
            "src_name":    ("Nuovo File Sorgente", 190),
            "src_dim":     ("Dimensione Sorgente", 130),
            "target_path": ("Percorso Target", 360),
        }
        for col, (lbl, w) in match_hdrs.items():
            self._match_tree.heading(col, text=lbl)
            self._match_tree.column(col, width=w, minwidth=30)

        mvsb = ttk.Scrollbar(mf, orient=tk.VERTICAL, command=self._match_tree.yview)
        mhsb = ttk.Scrollbar(mf, orient=tk.HORIZONTAL, command=self._match_tree.xview)
        self._match_tree.configure(yscrollcommand=mvsb.set, xscrollcommand=mhsb.set)

        self._match_tree.grid(row=0, column=0, sticky=tk.NSEW)
        mvsb.grid(row=0, column=1, sticky=tk.NS)
        mhsb.grid(row=1, column=0, sticky=tk.EW)
        mf.rowconfigure(0, weight=1)
        mf.columnconfigure(0, weight=1)

        # Colore righe no-match
        self._match_tree.tag_configure("no_match", foreground="#cc4444")
        self._match_tree.tag_configure("matched",  foreground="#226622")
        self._match_tree.tag_configure("disabled", foreground="#aaaaaa")

        # Binding click per toggle checkbox e visualizzazione anteprima
        self._match_tree.bind("<Button-1>", self._on_match_click)
        self._match_tree.bind("<<TreeviewSelect>>", self._on_match_select)

        # Panel Doppia Anteprima (Originale vs Nuovo)
        match_preview_outer = ttk.Frame(parent)
        match_preview_outer.pack(fill=tk.X, padx=8, pady=4)

        # Anteprima Originale (Sinistra)
        self._target_preview_box = ttk.LabelFrame(match_preview_outer, text=" Logo Originale ")
        self._target_preview_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 4))
        
        self._target_canvas = tk.Canvas(self._target_preview_box, width=90, height=70, bg="#f5f5f5", highlightthickness=1)
        self._target_canvas.pack(side=tk.LEFT, padx=6, pady=4)
        self._target_preview_info = ttk.Label(self._target_preview_box, text="Seleziona una riga", font=("Arial", 8), justify=tk.LEFT)
        self._target_preview_info.pack(side=tk.LEFT, padx=6, pady=4, anchor=tk.W)

        # Freccia
        ttk.Label(match_preview_outer, text="➜", font=("Arial", 20), foreground="#3365ae").pack(side=tk.LEFT, padx=4)

        # Anteprima Nuovo (Destra)
        self._src_preview_box = ttk.LabelFrame(match_preview_outer, text=" Nuovo Logo Proposto ")
        self._src_preview_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(4, 0))

        self._src_canvas = tk.Canvas(self._src_preview_box, width=90, height=70, bg="#f5f5f5", highlightthickness=1)
        self._src_canvas.pack(side=tk.LEFT, padx=6, pady=4)
        self._src_preview_info = ttk.Label(self._src_preview_box, text="Seleziona una riga", font=("Arial", 8), justify=tk.LEFT)
        self._src_preview_info.pack(side=tk.LEFT, padx=6, pady=4, anchor=tk.W)

        # Legenda
        leg = ttk.Frame(parent)
        leg.pack(fill=tk.X, padx=8, pady=2)
        ttk.Label(leg, text="✓ = incluso nella sostituzione   ✗ = escluso (clicca sulla riga per cambiare)", 
                  font=("Arial", 8), foreground="#888888").pack(side=tk.LEFT)

        # Bottoni
        btn_f = ttk.Frame(parent)
        btn_f.pack(fill=tk.X, padx=8, pady=8)

        ttk.Button(btn_f, text="Seleziona tutto", command=self._select_all_matches,
                   **self.bs("secondary-outline")).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_f, text="Deseleziona tutto", command=self._deselect_all_matches,
                   **self.bs("secondary-outline")).pack(side=tk.LEFT, padx=4)

        ttk.Button(
            btn_f,
            text="✅  PROCEDI CON LA SOSTITUZIONE",
            command=self._go_to_replace,
            width=32,
            **self.bs("warning")
        ).pack(side=tk.RIGHT, padx=4)

        ttk.Button(
            btn_f, text="← Torna ai Risultati",
            command=lambda: self.notebook.select(1),
            **self.bs("secondary-outline")
        ).pack(side=tk.RIGHT, padx=4)

    # ------------------------------------------------------------------
    # TAB 4 - SOSTITUZIONE
    # ------------------------------------------------------------------

    def _build_replace_tab(self, parent: ttk.Frame):
        # Titolo (formattato come Tab 3)
        top = ttk.Frame(parent)
        top.pack(fill=tk.X, padx=8, pady=(12, 4))

        ttk.Label(
            top,
            text="Sostituzione File",
            font=("Arial", 13, "bold")
        ).pack(side=tk.LEFT, padx=16)

        ttk.Label(
            parent,
            text="I file selezionati nel tab precedente verranno sovrascritti con i corrispondenti "
                 "file sorgente.\nQuesta operazione non può essere annullata automaticamente.",
            font=("Arial", 10),
            foreground="#666666"
        ).pack(anchor=tk.W, padx=24, pady=(0, 14))

        # Riepilogo
        self._replace_summary = ttk.LabelFrame(parent, text=" Riepilogo operazione ")
        self._replace_summary.pack(fill=tk.X, padx=24, pady=6)
        self._replace_summary_lbl = ttk.Label(self._replace_summary, text="Nessuna operazione in attesa.",
                                              font=("Arial", 10), justify=tk.LEFT)
        self._replace_summary_lbl.pack(padx=12, pady=10, anchor=tk.W)

        # Opzione backup
        self._backup_var = tk.BooleanVar(value=True)
        bk_frame = ttk.Frame(parent)
        bk_frame.pack(fill=tk.X, padx=24, pady=4)
        ttk.Checkbutton(
            bk_frame,
            text="Crea backup dei file originali prima di sovrascrivere "
                 "(verrà aggiunto il suffisso .bak al file originale)",
            variable=self._backup_var
        ).pack(side=tk.LEFT)

        # Log sostituzione
        log_frame = ttk.LabelFrame(parent, text=" Log operazioni ")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=24, pady=6)

        self.log_text = tk.Text(log_frame, height=12, wrap=tk.WORD, font=("Courier", 9),
                                state=tk.DISABLED, bg="#fafafa")
        log_vsb = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_vsb.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=4)
        log_vsb.pack(side=tk.RIGHT, fill=tk.Y, pady=4)

        # Bottoni
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, padx=24, pady=10)

        self._btn_execute = ttk.Button(
            btn_frame,
            text="⚡  ESEGUI SOSTITUZIONE",
            command=self._execute_replacement,
            width=28,
            **self.bs("danger")
        )
        self._btn_execute.pack(side=tk.RIGHT, padx=4)

        ttk.Button(
            btn_frame,
            text="← Torna alle Corrispondenze",
            command=lambda: self.notebook.select(2),
            **self.bs("secondary-outline")
        ).pack(side=tk.LEFT, padx=4)

        ttk.Button(
            btn_frame,
            text="Pulisci log",
            command=self._clear_log,
            **self.bs("secondary-outline")
        ).pack(side=tk.LEFT, padx=4)

    # ------------------------------------------------------------------
    # Azioni: Configurazione
    # ------------------------------------------------------------------

    def _browse_source_folder(self):
        folder = filedialog.askdirectory(title="Seleziona cartella sorgente (nuovi loghi)")
        if folder:
            self.source_folder.set(folder)

    def _browse_scan_folder(self):
        folder = filedialog.askdirectory(title="Seleziona cartella da scansionare")
        if folder:
            self.scan_folder.set(folder)

    def _clear_fields(self):
        self.source_folder.set("")
        self.scan_folder.set("")
        self.search_pattern.set("logo*.png")

    def _validate_config(self) -> bool:
        src = self.source_folder.get().strip()
        scan = self.scan_folder.get().strip()
        pat = self.search_pattern.get().strip()

        if not src or not os.path.isdir(src):
            messagebox.showerror("Errore", "Seleziona una cartella sorgente valida.")
            return False
        if not scan or not os.path.isdir(scan):
            messagebox.showerror("Errore", "Seleziona una cartella da scansionare valida.")
            return False
        if not pat:
            messagebox.showerror("Errore", "Inserisci un pattern di ricerca.")
            return False
        return True

    # ------------------------------------------------------------------
    # Azioni: Scansione
    # ------------------------------------------------------------------

    def _start_scan(self):
        if not self._validate_config():
            return

        # Riabilita il pulsante di sostituzione per una nuova sessione
        self._btn_execute.config(state=tk.NORMAL)

        self.scanned_files.clear()
        self.source_files.clear()
        self.matches.clear()
        self._clear_tree(self._scan_tree)
        self.progress_var.set(0)
        self._scan_count_lbl.config(text="Scansione in corso...")
        self._status("Scansione in corso...")
        self.notebook.select(1)

        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self):
        try:
            src_folder = self.source_folder.get().strip()
            scan_folder = self.scan_folder.get().strip()
            pattern = self.search_pattern.get().strip()

            self.log(f"Scansione avviata: cartella={scan_folder}  pattern={pattern}")
            self.log(f"Sorgente loghi: {src_folder}")

            # Scansione cartella sorgente (tutti i formati immagine supportati)
            self.source_files = []
            for root, _, files in os.walk(src_folder):
                for f in files:
                    if Path(f).suffix.lower() in SUPPORTED_FORMATS:
                        self.source_files.append(os.path.join(root, f))
            self.log(f"File sorgente trovati: {len(self.source_files)}")

            # Scansione cartella target
            found = scan_files(scan_folder, pattern)
            total = len(found)
            self.log(f"File trovati nella scansione: {total}")

            for i, fpath in enumerate(found):
                try:
                    stat = os.stat(fpath)
                    size_bytes = stat.st_size
                    ext = Path(fpath).suffix.lower()
                    dim = get_image_dimensions(fpath)
                    fname = os.path.basename(fpath)

                    dim_str = f"{dim[0]}×{dim[1]} px" if dim else "N/D"

                    item = {
                        "path": fpath,
                        "name": fname,
                        "ext": ext.lstrip(".").upper(),
                        "size": size_bytes,
                        "size_str": format_size(size_bytes),
                        "dim": dim,
                        "dim_str": dim_str,
                    }
                    self.scanned_files.append(item)

                    pct = int((i + 1) / total * 100) if total > 0 else 100
                    self._ui(lambda v=pct: self.progress_var.set(v))

                except Exception as exc:
                    self.log(f"  Errore su {fpath}: {exc}", logging.WARNING)

            # Aggiorna treeview nel main thread
            self._ui(self._populate_scan_tree)

        except Exception as exc:
            self.log(f"Errore durante la scansione: {exc}", logging.ERROR)
            self._ui(lambda: messagebox.showerror("Errore Scansione", str(exc)))

    def _populate_scan_tree(self):
        self._clear_tree(self._scan_tree)
        self.thumbnail_refs.clear()

        for idx, item in enumerate(self.scanned_files, 1):
            self._scan_tree.insert(
                "", tk.END,
                iid=item["path"],
                values=(
                    idx,
                    item["name"],
                    item["ext"],
                    item["size_str"],
                    item["dim_str"],
                    item["path"]
                )
            )

        n = len(self.scanned_files)
        self._scan_count_lbl.config(text=f"{n} file trovati")
        self.progress_var.set(100)
        self._status(f"Scansione completata: {n} file trovati.")
        self.log(f"Popolazione treeview completata: {n} voci.")

    def _on_scan_select(self, event=None):
        sel = self._scan_tree.selection()
        if not sel:
            return
        fpath = sel[0]  # iid = path
        item = next((x for x in self.scanned_files if x["path"] == fpath), None)
        if item:
            self._show_preview(fpath, item)

    def _show_preview(self, fpath: str, item: dict):
        # Cancella canvas
        self._preview_canvas.delete("all")
        thumb = make_thumbnail(fpath, (110, 80))
        if thumb:
            self._preview_canvas._thumb_ref = thumb  # Anti GC
            w = self._preview_canvas.winfo_width() or 120
            h = self._preview_canvas.winfo_height() or 90
            self._preview_canvas.create_image(w // 2, h // 2, image=thumb, anchor=tk.CENTER)
        else:
            self._preview_canvas.create_text(60, 45, text="N/D", fill="#aaaaaa", font=("Arial", 11))

        info = (
            f"Nome: {item['name']}\n"
            f"Formato: {item['ext']}\n"
            f"Dimensione: {item['size_str']}\n"
            f"Risoluzione: {item['dim_str']}\n"
            f"Percorso: {item['path']}"
        )
        self._preview_info.config(text=info, foreground="#333333")

    # ------------------------------------------------------------------
    # Azioni: Matching
    # ------------------------------------------------------------------

    def _start_matching(self):
        if not self.scanned_files:
            messagebox.showwarning("Attenzione", "Nessun file trovato nella scansione.\nEsegui prima la scansione.")
            return
        if not self.source_files:
            messagebox.showwarning("Attenzione", "Nessun file trovato nella cartella sorgente.")
            return

        self.matches.clear()
        self._clear_tree(self._match_tree)
        self.progress_var.set(0)
        self._match_count_lbl.config(text="Analisi in corso...")
        self._status("Analisi e matching in corso...")
        self.notebook.select(2)

        threading.Thread(target=self._match_worker, daemon=True).start()

    def _match_worker(self):
        try:
            total = len(self.scanned_files)
            self.log(f"Avvio matching: {total} file da analizzare, {len(self.source_files)} sorgenti disponibili")

            for i, item in enumerate(self.scanned_files):
                best_src = find_best_match(item["path"], self.source_files)
                if best_src:
                    src_dim = get_image_dimensions(best_src)
                    src_dim_str = f"{src_dim[0]}×{src_dim[1]} px" if src_dim else "N/D"
                else:
                    src_dim_str = ""

                match = {
                    "target": item,
                    "best_src": best_src,
                    "src_name": os.path.basename(best_src) if best_src else "NESSUNA CORRISPONDENZA",
                    "src_dim_str": src_dim_str,
                    "enabled": best_src is not None,   # Default: abilitato se trovato un match
                }
                self.matches.append(match)
                pct = int((i + 1) / total * 100)
                self._ui(lambda v=pct: self.progress_var.set(v))

            self._ui(self._populate_match_tree)

        except Exception as exc:
            self.log(f"Errore durante il matching: {exc}", logging.ERROR)
            self._ui(lambda: messagebox.showerror("Errore Matching", str(exc)))

    def _populate_match_tree(self):
        self._clear_tree(self._match_tree)

        matched = sum(1 for m in self.matches if m["best_src"] is not None)
        unmatched = len(self.matches) - matched

        for idx, m in enumerate(self.matches, 1):
            tgt = m["target"]
            chk = "✓" if m["enabled"] else "✗"
            tag = "matched" if m["best_src"] else "no_match"
            if not m["enabled"] and m["best_src"]:
                tag = "disabled"

            self._match_tree.insert(
                "", tk.END,
                iid=tgt["path"],
                values=(
                    idx,
                    chk,
                    tgt["name"],
                    tgt["ext"],
                    tgt["dim_str"],
                    m["src_name"],
                    m["src_dim_str"],
                    tgt["path"]
                ),
                tags=(tag,)
            )

        total = len(self.matches)
        lbl = f"{total} file analizzati: {matched} corrispondenze trovate"
        if unmatched:
            lbl += f", {unmatched} senza corrispondenza (rosso)"
        self._match_count_lbl.config(text=lbl)
        self.progress_var.set(100)
        self._status(lbl)
        self.log(f"Matching completato: {matched}/{total} corrispondenze trovate")

    def _on_match_click(self, event):
        """Toggle abilitazione riga al click."""
        region = self._match_tree.identify_region(event.x, event.y)
        if region != "cell":
            return
        row_id = self._match_tree.identify_row(event.y)
        if not row_id:
            return

        # Trova match corrispondente
        match = next((m for m in self.matches if m["target"]["path"] == row_id), None)
        if not match or match["best_src"] is None:
            return  # Non modificabile se senza corrispondenza

        match["enabled"] = not match["enabled"]
        chk = "✓" if match["enabled"] else "✗"
        tag = "matched" if match["enabled"] else "disabled"

        vals = list(self._match_tree.item(row_id, "values"))
        vals[1] = chk
        self._match_tree.item(row_id, values=vals, tags=(tag,))

    def _on_match_select(self, event=None):
        """Visualizza l'anteprima doppia per il match selezionato."""
        sel = self._match_tree.selection()
        if not sel:
            return
        target_path = sel[0]
        match = next((m for m in self.matches if m["target"]["path"] == target_path), None)
        if not match:
            return

        target_item = match["target"]
        src_path = match["best_src"]

        # --- Aggiorna Anteprima Target (Originale) ---
        self._target_canvas.delete("all")
        t_thumb = make_thumbnail(target_path, (90, 70))
        if t_thumb:
            self._target_canvas._t_thumb_ref = t_thumb
            self._target_canvas.create_image(45, 35, image=t_thumb, anchor=tk.CENTER)
        else:
            self._target_canvas.create_text(45, 35, text="N/D", fill="#aaaaaa")

        t_info = (f"Nome: {target_item['name']}\n"
                  f"Formato: {target_item['ext']}\n"
                  f"Dim: {target_item['dim_str']}\n"
                  f"Peso: {target_item['size_str']}")
        self._target_preview_info.config(text=t_info)

        # --- Aggiorna Anteprima Source (Nuovo) ---
        self._src_canvas.delete("all")
        if src_path:
            s_thumb = make_thumbnail(src_path, (90, 70))
            if s_thumb:
                self._src_canvas._s_thumb_ref = s_thumb
                self._src_canvas.create_image(45, 35, image=s_thumb, anchor=tk.CENTER)
            else:
                self._src_canvas.create_text(45, 35, text="N/D", fill="#aaaaaa")
            
            s_info = (f"Nome: {os.path.basename(src_path)}\n"
                      f"Formato: {Path(src_path).suffix.lstrip('.').upper()}\n"
                      f"Dim: {match['src_dim_str']}\n"
                      f"Peso: {format_size(os.path.getsize(src_path))}")
            self._src_preview_info.config(text=s_info)
        else:
            self._src_canvas.create_text(45, 35, text="Nessun Match", fill="#cc4444")
            self._src_preview_info.config(text="Corrispondenza non\ntrovata.")

    def _select_all_matches(self):
        for m in self.matches:
            if m["best_src"]:
                m["enabled"] = True
        self._refresh_match_checkboxes()

    def _deselect_all_matches(self):
        for m in self.matches:
            m["enabled"] = False
        self._refresh_match_checkboxes()

    def _refresh_match_checkboxes(self):
        for m in self.matches:
            row_id = m["target"]["path"]
            if not self._match_tree.exists(row_id):
                continue
            chk = "✓" if m["enabled"] else "✗"
            tag = "matched" if m["enabled"] else ("no_match" if not m["best_src"] else "disabled")
            vals = list(self._match_tree.item(row_id, "values"))
            vals[1] = chk
            self._match_tree.item(row_id, values=vals, tags=(tag,))

    # ------------------------------------------------------------------
    # Azioni: Sostituzione
    # ------------------------------------------------------------------

    def _go_to_replace(self):
        enabled = [m for m in self.matches if m["enabled"]]
        if not enabled:
            messagebox.showwarning("Attenzione", "Nessuna sostituzione selezionata.")
            return

        self._replace_summary_lbl.config(
            text=f"Verranno sostituiti {len(enabled)} file su {len(self.matches)} totali analizzati.\n"
                 f"I file originali {'verranno salvati con estensione .bak' if self._backup_var.get() else 'SARANNO SOVRASCRITTI DEFINITIVAMENTE'}."
        )
        self.progress_var.set(0)
        self.notebook.select(3)

    def _execute_replacement(self):
        enabled = [m for m in self.matches if m["enabled"]]
        if not enabled:
            messagebox.showwarning("Attenzione", "Nessuna sostituzione da eseguire.")
            return

        confirm = messagebox.askyesno(
            "Conferma Sostituzione",
            f"Stai per sovrascrivere {len(enabled)} file.\n\n"
            f"Backup: {'SÌ' if self._backup_var.get() else 'NO'}\n\n"
            "Continuare?"
        )
        if not confirm:
            return

        # Rilascia riferimenti alle immagini per evitare file locking
        self._clear_previews()

        self._btn_execute.config(state=tk.DISABLED)
        self.progress_var.set(0)
        self._status("Sostituzione in corso...")

        threading.Thread(
            target=self._replace_worker,
            args=(enabled, self._backup_var.get()),
            daemon=True
        ).start()

    def _clear_previews(self):
        """Pulisce tutte le anteprime UI per sbloccare i file."""
        # Tab 2
        self._preview_canvas.delete("all")
        if hasattr(self._preview_canvas, "_thumb_ref"):
            del self._preview_canvas._thumb_ref
        
        # Tab 3
        self._target_canvas.delete("all")
        if hasattr(self._target_canvas, "_t_thumb_ref"):
            del self._target_canvas._t_thumb_ref
        
        self._src_canvas.delete("all")
        if hasattr(self._src_canvas, "_s_thumb_ref"):
            del self._src_canvas._s_thumb_ref
        
        # Riferimenti globali
        self.thumbnail_refs.clear()
        self.root.update_idletasks()

    def _replace_worker(self, matches_to_replace: list, do_backup: bool):
        total = len(matches_to_replace)
        ok = 0
        errors = 0

        self.log(f"=== INIZIO SOSTITUZIONE: {total} file ===")

        for i, m in enumerate(matches_to_replace):
            target_path = m["target"]["path"]
            src_path = m["best_src"]
            fname = m["target"]["name"]

            try:
                # Backup file originale
                if do_backup:
                    bak_path = target_path + ".bak"
                    shutil.copy2(target_path, bak_path)
                    self.log(f"  Backup: {bak_path}")

                # Sostituzione
                shutil.copy2(src_path, target_path)
                self.log(f"  ✅ Sostituito: {fname}  ←  {os.path.basename(src_path)}")
                ok += 1

            except Exception as exc:
                self.log(f"  ❌ Errore su {fname}: {exc}", logging.ERROR)
                errors += 1

            pct = int((i + 1) / total * 100)
            self._ui(lambda v=pct: self.progress_var.set(v))

        self.log(f"=== SOSTITUZIONE COMPLETATA: {ok} OK, {errors} errori su {total} file ===")
        self.log("(avvia una nuova scansione prima di poter avviare di nuovo la sostituzione)")

        def _done():
            # Il pulsante rimane disabilitato fino a nuova scansione (richiesta utente)
            # self._btn_execute.config(state=tk.NORMAL) 
            self.progress_var.set(100)
            self._status(f"Sostituzione completata: {ok} OK, {errors} errori.")
            if errors == 0:
                messagebox.showinfo(
                    "Completato",
                    f"✅ Sostituzione completata con successo!\n\n"
                    f"File sostituiti: {ok}\n"
                    f"Errori: {errors}"
                )
            else:
                messagebox.showwarning(
                    "Completato con errori",
                    f"Sostituzione completata con alcuni errori.\n\n"
                    f"File sostituiti: {ok}\n"
                    f"Errori: {errors}\n\nConsulta il log per i dettagli."
                )

        self._ui(_done)

    # ------------------------------------------------------------------
    # Utilità UI
    # ------------------------------------------------------------------

    def _sort_tree(self, tree: ttk.Treeview, col: str):
        """Ordinamento colonne treeview."""
        data = [(tree.set(child, col), child) for child in tree.get_children("")]
        data.sort()
        for index, (_, child) in enumerate(data):
            tree.move(child, "", index)

    def _clear_tree(self, tree: ttk.Treeview):
        tree.delete(*tree.get_children())

    def _clear_log(self):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)
        self.log_messages.clear()

    def _status(self, msg: str):
        self._ui(lambda m=msg: self.status_label.config(text=m))
