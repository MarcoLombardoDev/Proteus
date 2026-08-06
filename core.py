#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Rebranding Tool - Logica applicativa (nessuna dipendenza da tkinter).

Questo modulo contiene tutto ciò che non è interfaccia grafica:
scansione, abbinamento, sostituzione atomica, backup/ripristino,
export CSV, persistenza impostazioni e logging.

Essendo privo di dipendenze GUI è interamente testabile da riga di comando.

SACE S.p.A
"""

from __future__ import annotations

import csv
import datetime
import difflib
import fnmatch
import json
import logging
import os
import re
import shutil
import sys
import tempfile
import threading
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Callable, Iterable, Sequence

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:  # pragma: no cover - dipende dall'ambiente
    Image = None
    PIL_AVAILABLE = False


# ---------------------------------------------------------------------------
# Costanti applicazione
# ---------------------------------------------------------------------------

APP_NAME = "Rebranding Tool"
APP_VERSION = "1.1"
APP_COMPANY = "SACE S.p.A"
APP_SLUG = "RebrandingTool"

#: Formati file considerati "immagine" nella cartella sorgente.
SUPPORTED_FORMATS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif",
    ".svg", ".ico", ".webp", ".eps", ".pdf",
})

#: Estensioni intercambiabili tra loro in fase di abbinamento.
#: Un `logo.jpg` può essere sostituito da un `logo_nuovo.jpeg` e viceversa.
EQUIVALENT_EXTENSIONS: dict[str, str] = {
    ".jpg": ".jpeg",
    ".jpeg": ".jpeg",
    ".tif": ".tiff",
    ".tiff": ".tiff",
}

#: Estensioni per cui Pillow non è in grado di ricavare le dimensioni.
#: Per l'SVG le dimensioni vengono lette dal markup XML (vedi `svg_dimensions`).
NO_PIL_PREVIEW = frozenset({".svg", ".eps", ".pdf"})

#: Suffisso usato per i backup dei file originali.
BACKUP_SUFFIX = ".bak"

#: Peso della differenza di risoluzione nel punteggio di abbinamento.
#: Il criterio dimensionale resta dominante, il nome file fa da spareggio.
WEIGHT_DIMENSION = 0.65
WEIGHT_NAME = 0.35

#: Soglie sullo scarto *dimensionale* relativo per la classificazione
#: qualitativa. Il nome file influenza la scelta del candidato ma non il
#: giudizio: un logo con la risoluzione esatta è un'ottima corrispondenza
#: anche se il file sorgente si chiama diversamente.
QUALITY_GOOD = 0.10
QUALITY_FAIR = 0.35

#: Soglia di somiglianza del nome usata quando le risoluzioni non sono
#: determinabili (PDF, EPS, file corrotti).
NAME_ONLY_GOOD = 0.80


class OperationCancelled(Exception):
    """Sollevata quando l'utente annulla un'operazione lunga."""


# ---------------------------------------------------------------------------
# Percorsi applicazione
# ---------------------------------------------------------------------------

def get_base_path() -> str:
    """Path base dell'applicazione (cartella dell'eseguibile o dello script)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(relative: str) -> str:
    """Percorso di una risorsa, valido sia da sorgente sia da bundle PyInstaller."""
    base = getattr(sys, "_MEIPASS", get_base_path())
    return os.path.join(base, relative)


def user_data_dir() -> str:
    """
    Cartella dati utente scrivibile, usata come fallback quando la cartella
    dell'applicazione è in sola lettura (tipico caso `C:\\Program Files`).
    """
    if os.name == "nt":
        root = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    else:
        root = os.environ.get("XDG_DATA_HOME") or os.path.join(
            os.path.expanduser("~"), ".local", "share"
        )
    return os.path.join(root, APP_SLUG)


def _is_writable_dir(path: str) -> bool:
    """Verifica *effettiva* di scrivibilità (os.access mente su alcune share SMB)."""
    try:
        os.makedirs(path, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path, prefix=".wtest_", delete=True):
            return True
    except Exception:
        return False


def writable_app_dir(subfolder: str) -> str:
    """
    Restituisce `<base>/<subfolder>` se scrivibile, altrimenti la stessa
    sottocartella dentro la cartella dati utente. Crea la cartella scelta.
    """
    preferred = os.path.join(get_base_path(), subfolder)
    if _is_writable_dir(preferred):
        return preferred
    fallback = os.path.join(user_data_dir(), subfolder)
    os.makedirs(fallback, exist_ok=True)
    return fallback


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def setup_logging(logger_name: str = "rebranding_tool") -> logging.Logger:
    """
    Configura il logger applicativo con rotazione (5 file da 2 MB).
    Idempotente: chiamate successive non duplicano gli handler.
    """
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return logger

    try:
        log_dir = writable_app_dir("logs")
        fname = f"rebranding_{datetime.datetime.now():%Y%m%d}.log"
        handler = RotatingFileHandler(
            os.path.join(log_dir, fname),
            maxBytes=2 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter("[%(asctime)s] %(levelname)-7s %(message)s",
                              datefmt="%Y-%m-%d %H:%M:%S")
        )
        logger.addHandler(handler)
    except Exception as exc:  # pragma: no cover - dipende dai permessi
        logger.addHandler(logging.StreamHandler())
        logger.warning("Logging su file non disponibile: %s", exc)

    return logger


# ---------------------------------------------------------------------------
# Utility di formattazione e lettura immagini
# ---------------------------------------------------------------------------

def format_size(size_bytes: float) -> str:
    """Formatta una dimensione in byte in stringa leggibile (es. `1.5 MB`)."""
    value = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if abs(value) < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


_SVG_LEN_RE = re.compile(r"^\s*([0-9]*\.?[0-9]+)\s*([a-z%]*)\s*$", re.IGNORECASE)

#: Fattori di conversione verso pixel CSS (96 dpi), come da specifica SVG.
_SVG_UNITS = {
    "": 1.0, "px": 1.0, "pt": 96 / 72, "pc": 16.0,
    "mm": 96 / 25.4, "cm": 96 / 2.54, "in": 96.0,
}


def _svg_length_to_px(raw: str | None) -> float | None:
    """Converte una lunghezza SVG (`120`, `2.5cm`, `10pt`) in pixel."""
    if not raw:
        return None
    m = _SVG_LEN_RE.match(raw)
    if not m:
        return None
    value, unit = float(m.group(1)), m.group(2).lower()
    factor = _SVG_UNITS.get(unit)
    if factor is None:  # percentuali e unità relative non sono risolvibili
        return None
    return value * factor


def svg_dimensions(filepath: str) -> tuple[int, int] | None:
    """
    Ricava (larghezza, altezza) in pixel da un file SVG, usando gli attributi
    `width`/`height` e, in mancanza, il `viewBox`. Ritorna None se illeggibile.
    """
    try:
        # Gli SVG possono essere enormi: ci serve solo l'elemento radice.
        for _event, elem in ET.iterparse(filepath, events=("start",)):
            width = _svg_length_to_px(elem.get("width"))
            height = _svg_length_to_px(elem.get("height"))
            if width is None or height is None:
                viewbox = (elem.get("viewBox") or "").replace(",", " ").split()
                if len(viewbox) == 4:
                    try:
                        width = width or float(viewbox[2])
                        height = height or float(viewbox[3])
                    except ValueError:
                        pass
            elem.clear()
            if width and height:
                return int(round(width)), int(round(height))
            return None
    except Exception:
        return None
    return None


def get_image_dimensions(filepath: str) -> tuple[int, int] | None:
    """Ritorna (width, height) del file, oppure None se non determinabile."""
    ext = Path(filepath).suffix.lower()
    if ext == ".svg":
        return svg_dimensions(filepath)
    if ext in NO_PIL_PREVIEW or not PIL_AVAILABLE:
        return None
    try:
        with Image.open(filepath) as img:
            return img.size
    except Exception:
        return None


def size_diff(dim1: tuple[int, int] | None, dim2: tuple[int, int] | None) -> float:
    """Distanza euclidea tra due risoluzioni. `inf` se una delle due è ignota."""
    if dim1 is None or dim2 is None:
        return float("inf")
    (w1, h1), (w2, h2) = dim1, dim2
    return ((w1 - w2) ** 2 + (h1 - h2) ** 2) ** 0.5


def normalized_ext(path_or_ext: str) -> str:
    """
    Estensione normalizzata usata per il confronto di formato.
    `.jpg`/`.jpeg` e `.tif`/`.tiff` collassano sullo stesso valore.
    """
    ext = path_or_ext if path_or_ext.startswith(".") else Path(path_or_ext).suffix
    ext = ext.lower()
    return EQUIVALENT_EXTENSIONS.get(ext, ext)


# ---------------------------------------------------------------------------
# Modello dati
# ---------------------------------------------------------------------------

@dataclass
class FileInfo:
    """Metadati di un file individuato dalla scansione."""

    path: str
    name: str
    ext: str                    # estensione con punto, minuscola (".png")
    size: int
    dim: tuple[int, int] | None

    @property
    def fmt(self) -> str:
        """Formato in maiuscolo per la visualizzazione (`PNG`)."""
        return self.ext.lstrip(".").upper()

    @property
    def size_str(self) -> str:
        return format_size(self.size)

    @property
    def dim_str(self) -> str:
        return f"{self.dim[0]}×{self.dim[1]} px" if self.dim else "N/D"

    @classmethod
    def from_path(cls, path: str) -> "FileInfo":
        stat = os.stat(path)
        return cls(
            path=path,
            name=os.path.basename(path),
            ext=Path(path).suffix.lower(),
            size=stat.st_size,
            dim=get_image_dimensions(path),
        )


@dataclass
class Match:
    """Abbinamento proposto tra un file da sostituire e un file sorgente."""

    target: FileInfo
    source: FileInfo | None
    score: float = float("inf")     # punteggio di ranking (dimensione + nome)
    enabled: bool = False
    manual: bool = False            # True se l'utente ha scelto la sorgente a mano

    @property
    def source_name(self) -> str:
        return self.source.name if self.source else "NESSUNA CORRISPONDENZA"

    @property
    def source_dim_str(self) -> str:
        return self.source.dim_str if self.source else ""

    @property
    def quality(self) -> str:
        """
        Giudizio leggibile sulla bontà dell'abbinamento.

        Si basa sullo scarto di risoluzione, non sul punteggio di ranking:
        quest'ultimo include la somiglianza del nome, che serve a scegliere
        tra candidati equivalenti ma non deve declassare una corrispondenza
        dimensionalmente perfetta.
        """
        if self.source is None:
            return "—"
        if self.manual:
            return "Manuale"

        if self.target.dim is None or self.source.dim is None:
            similarity = name_similarity(self.target.path, self.source.path)
            return "Buona" if similarity >= NAME_ONLY_GOOD else "Debole"

        relative = dimension_distance(self.target.dim, self.source.dim)
        if relative <= QUALITY_GOOD:
            return "Ottima"
        if relative <= QUALITY_FAIR:
            return "Buona"
        return "Debole"


@dataclass
class ReplaceOutcome:
    """Esito della sostituzione di un singolo file."""

    target: str
    source: str
    status: str                 # "ok" | "skipped" | "error"
    message: str = ""
    backup: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"


@dataclass
class ReplaceReport:
    """Riepilogo di un'intera sessione di sostituzione."""

    outcomes: list[ReplaceOutcome] = field(default_factory=list)
    cancelled: bool = False

    @property
    def ok(self) -> int:
        return sum(1 for o in self.outcomes if o.status == "ok")

    @property
    def skipped(self) -> int:
        return sum(1 for o in self.outcomes if o.status == "skipped")

    @property
    def errors(self) -> int:
        return sum(1 for o in self.outcomes if o.status == "error")

    @property
    def total(self) -> int:
        return len(self.outcomes)


# ---------------------------------------------------------------------------
# Scansione
# ---------------------------------------------------------------------------

def parse_patterns(raw: str) -> list[str]:
    """
    Interpreta la chiave di ricerca inserita dall'utente.
    Sono ammessi più pattern separati da `;` o `,` (es. `logo*.png; banner*.jpg`).
    """
    parts = [p.strip() for p in re.split(r"[;,]", raw or "")]
    return [p for p in parts if p]


def validate_pattern(raw: str) -> str | None:
    """Ritorna un messaggio d'errore se il pattern non è utilizzabile, altrimenti None."""
    patterns = parse_patterns(raw)
    if not patterns:
        return "Inserisci almeno un pattern di ricerca."
    for pat in patterns:
        if "/" in pat or "\\" in pat:
            return (f"Il pattern «{pat}» contiene un separatore di percorso: "
                    "indica solo il nome del file (es. logo*.png).")
        if set(pat) <= {"*", "?", " "}:
            return (f"Il pattern «{pat}» è troppo generico e selezionerebbe "
                    "qualsiasi file. Specifica almeno un'estensione.")
    return None


def matches_patterns(filename: str, patterns: Sequence[str]) -> bool:
    """True se il nome file corrisponde ad almeno uno dei pattern (case-insensitive)."""
    lowered = filename.lower()
    return any(fnmatch.fnmatchcase(lowered, p.lower()) for p in patterns)


def is_within(path: str, folder: str) -> bool:
    """True se `path` si trova dentro `folder` (o coincide con esso)."""
    try:
        Path(os.path.realpath(path)).relative_to(os.path.realpath(folder))
        return True
    except (ValueError, OSError):
        return False


def scan_files(
    folder: str,
    pattern: str,
    *,
    exclude_dirs: Iterable[str] = (),
    skip_backups: bool = True,
    cancel_event: threading.Event | None = None,
    on_error: Callable[[str, Exception], None] | None = None,
) -> list[str]:
    """
    Scansiona `folder` ricorsivamente restituendo i file che corrispondono
    al pattern (o ai pattern separati da `;`).

    exclude_dirs  cartelle da saltare, tipicamente la cartella sorgente quando
                  è annidata dentro quella da scansionare
    skip_backups  ignora i file `.bak` generati dal tool stesso
    cancel_event  se impostato, interrompe la scansione con OperationCancelled
    on_error      callback per gli errori di accesso (share di rete, permessi)
    """
    patterns = parse_patterns(pattern)
    if not patterns:
        return []

    excluded = [os.path.realpath(d) for d in exclude_dirs if d]
    results: list[str] = []
    visited: set[tuple[int, int]] = set()

    def _walk_error(exc: OSError) -> None:
        if on_error:
            on_error(getattr(exc, "filename", folder) or folder, exc)

    for root, dirs, files in os.walk(folder, onerror=_walk_error, followlinks=False):
        if cancel_event is not None and cancel_event.is_set():
            raise OperationCancelled()

        # Protezione contro cicli via junction/symlink su share di rete.
        try:
            st = os.stat(root)
            key = (st.st_dev, st.st_ino)
            if key in visited:
                dirs[:] = []
                continue
            visited.add(key)
        except OSError as exc:
            _walk_error(exc)
            dirs[:] = []
            continue

        real_root = os.path.realpath(root)
        dirs[:] = [
            d for d in dirs
            if not any(
                os.path.realpath(os.path.join(real_root, d)) == ex
                or is_within(os.path.join(real_root, d), ex)
                for ex in excluded
            )
        ]

        for fname in files:
            if skip_backups and fname.lower().endswith(BACKUP_SUFFIX):
                continue
            if matches_patterns(fname, patterns):
                results.append(os.path.join(root, fname))

    return sorted(results)


def collect_source_files(
    folder: str,
    *,
    cancel_event: threading.Event | None = None,
    on_error: Callable[[str, Exception], None] | None = None,
) -> list[str]:
    """Elenca tutti i file immagine supportati presenti nella cartella sorgente."""
    def _walk_error(exc: OSError) -> None:
        if on_error:
            on_error(getattr(exc, "filename", folder) or folder, exc)

    found: list[str] = []
    for root, _dirs, files in os.walk(folder, onerror=_walk_error, followlinks=False):
        if cancel_event is not None and cancel_event.is_set():
            raise OperationCancelled()
        for fname in files:
            if Path(fname).suffix.lower() in SUPPORTED_FORMATS:
                found.append(os.path.join(root, fname))
    return sorted(found)


# ---------------------------------------------------------------------------
# Abbinamento
# ---------------------------------------------------------------------------

def name_similarity(path_a: str, path_b: str) -> float:
    """Somiglianza [0..1] tra i nomi file (estensione esclusa)."""
    stem_a = Path(path_a).stem.lower()
    stem_b = Path(path_b).stem.lower()
    return difflib.SequenceMatcher(None, stem_a, stem_b).ratio()


def dimension_distance(
    target_dim: tuple[int, int] | None,
    source_dim: tuple[int, int] | None,
) -> float:
    """
    Scarto di risoluzione *relativo* in [0..1], 0 = risoluzioni identiche.

    La distanza euclidea viene normalizzata sulla diagonale del target, così
    che uno scarto di 20 px pesi molto su un'icona 32×32 e poco su un banner
    1920×1080.
    """
    if target_dim is None or source_dim is None:
        return 1.0
    diagonal = (target_dim[0] ** 2 + target_dim[1] ** 2) ** 0.5 or 1.0
    return min(size_diff(target_dim, source_dim) / diagonal, 1.0)


def match_score(
    target_dim: tuple[int, int] | None,
    source_dim: tuple[int, int] | None,
    target_path: str,
    source_path: str,
) -> float:
    """
    Punteggio di *ranking*: 0 = perfetto, valori maggiori = peggiore.

    Serve solo a ordinare i candidati fra loro. Lo scarto di risoluzione pesa
    il 65%, la somiglianza del nome il restante 35%: quest'ultima fa da
    spareggio quando più sorgenti hanno la stessa risoluzione.
    Il giudizio mostrato all'utente usa invece `Match.quality`, che guarda
    alla sola risoluzione.
    """
    name_component = 1.0 - name_similarity(target_path, source_path)

    if target_dim is None or source_dim is None:
        # Senza risoluzioni confrontabili resta solo il nome.
        return name_component

    return (WEIGHT_DIMENSION * dimension_distance(target_dim, source_dim)
            + WEIGHT_NAME * name_component)


class DimensionCache:
    """
    Cache delle risoluzioni dei file.

    Senza cache l'abbinamento riapre ogni immagine sorgente per ogni file
    target (O(N×M) letture da disco), che su una share di rete è proibitivo.
    """

    def __init__(self) -> None:
        self._cache: dict[str, tuple[int, int] | None] = {}

    def get(self, path: str) -> tuple[int, int] | None:
        if path not in self._cache:
            self._cache[path] = get_image_dimensions(path)
        return self._cache[path]

    def preload(self, paths: Iterable[str]) -> None:
        for path in paths:
            self.get(path)

    def __len__(self) -> int:
        return len(self._cache)


def find_best_match(
    target: FileInfo,
    sources: Sequence[FileInfo],
) -> tuple[FileInfo | None, float]:
    """
    Individua il file sorgente più adatto a sostituire `target`.

    Criteri, in ordine di importanza:
      1. stesso formato (con `.jpg`/`.jpeg` e `.tif`/`.tiff` equivalenti);
      2. risoluzione più vicina possibile;
      3. nome file più simile, come spareggio.

    Ritorna `(sorgente, punteggio)`; `(None, inf)` se nessun candidato.
    """
    target_ext = normalized_ext(target.ext)
    candidates = [s for s in sources if normalized_ext(s.ext) == target_ext]
    if not candidates:
        return None, float("inf")

    best = min(
        candidates,
        key=lambda s: (match_score(target.dim, s.dim, target.path, s.path), s.path),
    )
    return best, match_score(target.dim, best.dim, target.path, best.path)


def build_matches(
    targets: Sequence[FileInfo],
    sources: Sequence[FileInfo],
    *,
    progress: Callable[[int, int], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> list[Match]:
    """Costruisce la lista di abbinamenti proposti per tutti i target."""
    matches: list[Match] = []
    total = len(targets)
    for index, target in enumerate(targets, 1):
        if cancel_event is not None and cancel_event.is_set():
            raise OperationCancelled()
        source, score = find_best_match(target, sources)
        matches.append(
            Match(target=target, source=source, score=score, enabled=source is not None)
        )
        if progress:
            progress(index, total)
    return matches


# ---------------------------------------------------------------------------
# Backup e sostituzione
# ---------------------------------------------------------------------------

def make_backup_path(target: str) -> str:
    """
    Percorso di backup che non sovrascrive backup già esistenti.

    Alla prima esecuzione produce `file.png.bak`; se quel file esiste già
    (seconda campagna di rebranding sulla stessa cartella) ripiega su
    `file.png.20260806-101500.bak`, così l'originale non viene mai perso.
    """
    simple = target + BACKUP_SUFFIX
    if not os.path.exists(simple):
        return simple

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = f"{target}.{stamp}{BACKUP_SUFFIX}"
    counter = 1
    while os.path.exists(candidate):
        candidate = f"{target}.{stamp}-{counter}{BACKUP_SUFFIX}"
        counter += 1
    return candidate


def replace_file(
    target: str,
    source: str,
    *,
    backup: bool = True,
    dry_run: bool = False,
) -> ReplaceOutcome:
    """
    Sostituisce `target` con il contenuto di `source`.

    La copia avviene su un file temporaneo nella stessa cartella, poi
    promosso con `os.replace`: se qualcosa va storto a metà copia il file
    originale resta intatto, mai troncato.
    """
    if not os.path.isfile(source):
        return ReplaceOutcome(target, source, "error",
                              "File sorgente non trovato o non è un file.")
    if not os.path.isfile(target):
        return ReplaceOutcome(target, source, "error",
                              "File da sostituire non trovato o non è un file.")
    try:
        if os.path.samefile(source, target):
            return ReplaceOutcome(target, source, "skipped",
                                  "Sorgente e destinazione sono lo stesso file.")
    except OSError:
        pass

    if dry_run:
        note = "Simulazione: nessuna modifica scritta su disco."
        return ReplaceOutcome(target, source, "ok", note,
                              make_backup_path(target) if backup else None)

    backup_path: str | None = None
    tmp_path: str | None = None
    folder = os.path.dirname(target) or "."

    try:
        if backup:
            backup_path = make_backup_path(target)
            shutil.copy2(target, backup_path)

        fd, tmp_path = tempfile.mkstemp(prefix=".rebranding_", dir=folder)
        os.close(fd)
        shutil.copy2(source, tmp_path)
        os.replace(tmp_path, target)   # atomico sullo stesso filesystem
        tmp_path = None

        return ReplaceOutcome(target, source, "ok", "", backup_path)

    except Exception as exc:
        return ReplaceOutcome(target, source, "error", str(exc), backup_path)

    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def replace_all(
    matches: Sequence[Match],
    *,
    backup: bool = True,
    dry_run: bool = False,
    progress: Callable[[int, int, ReplaceOutcome], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> ReplaceReport:
    """Esegue la sostituzione su tutti gli abbinamenti passati."""
    report = ReplaceReport()
    total = len(matches)

    for index, match in enumerate(matches, 1):
        if cancel_event is not None and cancel_event.is_set():
            report.cancelled = True
            break
        if match.source is None:
            outcome = ReplaceOutcome(match.target.path, "", "skipped",
                                     "Nessuna corrispondenza.")
        else:
            outcome = replace_file(match.target.path, match.source.path,
                                   backup=backup, dry_run=dry_run)
        report.outcomes.append(outcome)
        if progress:
            progress(index, total, outcome)

    return report


_TIMESTAMPED_BAK_RE = re.compile(
    r"\.(?P<stamp>\d{8}-\d{6})(?:-(?P<counter>\d+))?" + re.escape(BACKUP_SUFFIX) + r"$"
)


def backup_origin(backup_path: str) -> str:
    """
    Percorso originale a partire da un file di backup.

    `logo.png.bak` e `logo.png.20260806-101500.bak` restituiscono entrambi
    `logo.png`.
    """
    without_stamp = _TIMESTAMPED_BAK_RE.sub("", backup_path)
    if without_stamp != backup_path:
        return without_stamp
    if backup_path.lower().endswith(BACKUP_SUFFIX):
        return backup_path[: -len(BACKUP_SUFFIX)]
    return backup_path


def backup_age_key(backup_path: str) -> tuple:
    """
    Chiave di ordinamento cronologico dei backup di uno stesso file.

    Il backup senza timestamp (`logo.png.bak`) è sempre il primo creato, quindi
    il più vecchio; quelli con timestamp seguono in ordine di data. Ordinare
    per nome non basta: `logo.png.20260806-101500.bak` precederebbe
    alfabeticamente `logo.png.bak`, invertendo l'ordine reale.
    """
    match = _TIMESTAMPED_BAK_RE.search(backup_path)
    if not match:
        return (0, "", 0)
    return (1, match.group("stamp"), int(match.group("counter") or 0))


def find_backups(folder: str) -> list[str]:
    """
    Elenca ricorsivamente i backup presenti in `folder`.

    L'ordine è per file originale e, all'interno, dal più vecchio al più
    recente.
    """
    found: list[str] = []
    for root, _dirs, files in os.walk(folder, followlinks=False):
        for fname in files:
            if fname.lower().endswith(BACKUP_SUFFIX):
                found.append(os.path.join(root, fname))
    return sorted(found, key=lambda p: (backup_origin(p), backup_age_key(p)))


def restore_backups(
    folder: str,
    *,
    remove_backup: bool = False,
    progress: Callable[[int, int, ReplaceOutcome], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> ReplaceReport:
    """
    Ripristina i file originali dai backup `.bak` presenti in `folder`.

    Se per lo stesso file esistono più backup viene usato il più vecchio,
    cioè quello anteriore alla prima sostituzione.
    """
    report = ReplaceReport()
    backups = find_backups(folder)

    # Un solo backup per file originale: il primo in ordine (il più vecchio).
    chosen: dict[str, str] = {}
    for bak in backups:
        chosen.setdefault(backup_origin(bak), bak)

    items = sorted(chosen.items())
    total = len(items)

    for index, (origin, bak) in enumerate(items, 1):
        if cancel_event is not None and cancel_event.is_set():
            report.cancelled = True
            break
        try:
            shutil.copy2(bak, origin)
            if remove_backup:
                os.remove(bak)
            outcome = ReplaceOutcome(origin, bak, "ok", "Ripristinato dal backup.")
        except Exception as exc:
            outcome = ReplaceOutcome(origin, bak, "error", str(exc))
        report.outcomes.append(outcome)
        if progress:
            progress(index, total, outcome)

    return report


# ---------------------------------------------------------------------------
# Export CSV
# ---------------------------------------------------------------------------

def export_matches_csv(matches: Sequence[Match], destination: str) -> str:
    """Esporta gli abbinamenti in CSV (separatore `;`, compatibile con Excel IT)."""
    with open(destination, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh, delimiter=";")
        writer.writerow([
            "Incluso", "File da sostituire", "Formato", "Risoluzione target",
            "Peso target", "Nuovo file sorgente", "Risoluzione sorgente",
            "Qualità", "Punteggio", "Percorso target", "Percorso sorgente",
        ])
        for match in matches:
            writer.writerow([
                "SI" if match.enabled else "NO",
                match.target.name,
                match.target.fmt,
                match.target.dim_str,
                match.target.size_str,
                match.source_name,
                match.source_dim_str,
                match.quality,
                "" if match.score == float("inf") else f"{match.score:.4f}",
                match.target.path,
                match.source.path if match.source else "",
            ])
    return destination


def export_report_csv(report: ReplaceReport, destination: str) -> str:
    """Esporta l'esito di una sostituzione in CSV."""
    with open(destination, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh, delimiter=";")
        writer.writerow(["Esito", "File", "Sorgente", "Backup", "Messaggio"])
        for outcome in report.outcomes:
            writer.writerow([
                outcome.status.upper(), outcome.target, outcome.source,
                outcome.backup or "", outcome.message,
            ])
    return destination


# ---------------------------------------------------------------------------
# Persistenza impostazioni
# ---------------------------------------------------------------------------

SETTINGS_FILE = "settings.json"
DEFAULT_SETTINGS: dict[str, object] = {
    "source_folder": "",
    "scan_folder": "",
    "search_pattern": "logo*.png",
    "backup": True,
    "dry_run": False,
}


def settings_path() -> str:
    return os.path.join(writable_app_dir("config"), SETTINGS_FILE)


def load_settings() -> dict:
    """Carica le ultime impostazioni usate; ritorna i default se assenti o corrotte."""
    settings = dict(DEFAULT_SETTINGS)
    try:
        with open(settings_path(), encoding="utf-8") as fh:
            stored = json.load(fh)
        if isinstance(stored, dict):
            settings.update({k: v for k, v in stored.items() if k in DEFAULT_SETTINGS})
    except (OSError, ValueError):
        pass
    return settings


def save_settings(values: dict) -> bool:
    """Salva le impostazioni. Ritorna False se il salvataggio non è possibile."""
    try:
        payload = {k: v for k, v in values.items() if k in DEFAULT_SETTINGS}
        with open(settings_path(), "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Validazione configurazione
# ---------------------------------------------------------------------------

def validate_config(source_folder: str, scan_folder: str, pattern: str) -> list[str]:
    """
    Valida la configurazione della scansione.
    Ritorna la lista dei problemi bloccanti (vuota se tutto ok).
    """
    problems: list[str] = []

    if not source_folder or not os.path.isdir(source_folder):
        problems.append("Seleziona una cartella sorgente valida.")
    if not scan_folder or not os.path.isdir(scan_folder):
        problems.append("Seleziona una cartella da scansionare valida.")

    pattern_error = validate_pattern(pattern)
    if pattern_error:
        problems.append(pattern_error)

    if (source_folder and scan_folder
            and os.path.isdir(source_folder) and os.path.isdir(scan_folder)):
        try:
            if os.path.samefile(source_folder, scan_folder):
                problems.append(
                    "La cartella sorgente e quella da scansionare coincidono: "
                    "i nuovi loghi verrebbero sostituiti con se stessi."
                )
        except OSError:
            pass

    return problems


def config_warnings(source_folder: str, scan_folder: str) -> list[str]:
    """Avvisi non bloccanti sulla configurazione scelta."""
    warnings: list[str] = []
    if not (source_folder and scan_folder):
        return warnings
    if is_within(source_folder, scan_folder):
        warnings.append(
            "La cartella sorgente si trova dentro quella da scansionare: "
            "verrà esclusa automaticamente dalla ricerca."
        )
    return warnings
