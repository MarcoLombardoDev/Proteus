#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Proteus - application logic (no tkinter dependency).

Everything that is not user interface lives here: scanning, matching, atomic
replacement, backup/restore, CSV export, settings persistence and logging.

Having no GUI dependency makes this module fully testable headlessly.
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

import i18n
import office
from i18n import t

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:  # pragma: no cover - environment dependent
    Image = None
    PIL_AVAILABLE = False


# ---------------------------------------------------------------------------
# Application constants
# ---------------------------------------------------------------------------

APP_NAME = "Proteus"
#: Shown next to the name: Proteus is the product, this says what it does.
APP_TAGLINE = "Rebranding Tool"
APP_VERSION = "1.3"
APP_SLUG = "Proteus"

APP_AUTHOR = "Marco Lombardo"
APP_COPYRIGHT_YEAR = "2026"

#: Where commercial licensing enquiries go. Single source of truth: the
#: interface, the README and COMMERCIAL-LICENSE.md must never disagree.
CONTACT_EMAIL = "marco.lombardo@gmail.com"

#: Legal notice shown in the application footer. Kept in English in every
#: language: it is a licence notice, not interface copy. Displaying it also
#: satisfies the "Appropriate Legal Notices" requirement of AGPL-3.0 section 5.
#:
#: It ends on a colon because the interface appends CONTACT_EMAIL as a
#: separate, clickable label. Whoever is running the application is exactly
#: the person who might need to buy a commercial licence, and "available on
#: request" tells them nothing about how to ask.
LICENSE_NOTICE = (
    f"© {APP_COPYRIGHT_YEAR} {APP_AUTHOR} — {APP_NAME}"
    "  |  Licensed under AGPL-3.0"
    "  |  Commercial licensing:"
)

#: Subject line pre-filled when the footer address is clicked. Kept identical
#: to the mailto: links in the README and in COMMERCIAL-LICENSE.md — the same
#: enquiry should not arrive under two different subjects depending on where
#: the reader clicked. A test compares them.
LICENSE_EMAIL_SUBJECT = f"{APP_NAME} commercial licence enquiry"

#: File types treated as images when collected from the source folder.
SUPPORTED_FORMATS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif",
    ".svg", ".ico", ".webp", ".eps", ".pdf",
})

#: Extensions considered interchangeable while matching.
#: A `logo.jpg` may be replaced by a `new_logo.jpeg` and vice versa.
EQUIVALENT_EXTENSIONS: dict[str, str] = {
    ".jpg": ".jpeg",
    ".jpeg": ".jpeg",
    ".tif": ".tiff",
    ".tiff": ".tiff",
}

#: Extensions whose dimensions Pillow cannot read. SVG is handled separately
#: by parsing the XML markup (see `svg_dimensions`).
NO_PIL_PREVIEW = frozenset({".svg", ".eps", ".pdf"})

#: Suffix used for backups of the original files.
BACKUP_SUFFIX = ".bak"

#: Weight of the resolution gap in the ranking score. The dimensional
#: criterion stays dominant; the file name only breaks ties.
WEIGHT_DIMENSION = 0.65
WEIGHT_NAME = 0.35

#: Thresholds on the *relative* resolution gap used to grade a match. The file
#: name influences which candidate wins but never the grade: a logo with the
#: exact resolution is an excellent match even if the source file is named
#: differently.
QUALITY_GOOD = 0.10
QUALITY_FAIR = 0.35

#: Side of the grayscale grid used for perceptual hashing. 8 gives a 64-bit
#: hash, the usual trade-off between discrimination and tolerance to rescaling.
HASH_SIDE = 8

#: Background composited under transparent pixels before hashing. Without it,
#: the same logo saved with and without an alpha channel hashes differently,
#: which is precisely the case a rebranding has to catch.
HASH_MATTE = (255, 255, 255)

#: Default similarity above which a file is considered a hit in content search.
#: Deliberately strict: this tool overwrites files, so a false positive
#: destroys an unrelated image. Lower it knowingly, not by default.
DEFAULT_SIMILARITY = 0.90

#: Below this, a content hit is shown but flagged as needing human eyes.
SIMILARITY_CONFIDENT = 0.95

#: Name-similarity threshold used when resolutions cannot be determined
#: (PDF, EPS, corrupted files).
NAME_ONLY_GOOD = 0.80

#: Canonical match grades. These strings double as translation keys, so they
#: stay stable across languages and can be asserted on in tests.
QUALITY_EXCELLENT = "Excellent"
QUALITY_GOOD_LABEL = "Good"
QUALITY_WEAK = "Weak"
QUALITY_MANUAL = "Manual"
QUALITY_NONE = "—"


class OperationCancelled(Exception):
    """Raised when the user cancels a long-running operation."""


# ---------------------------------------------------------------------------
# Application paths
# ---------------------------------------------------------------------------

def get_base_path() -> str:
    """Base path of the application (executable or script folder)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(relative: str) -> str:
    """Path of a bundled resource, valid both from source and from PyInstaller."""
    base = getattr(sys, "_MEIPASS", get_base_path())
    return os.path.join(base, relative)


def user_data_dir() -> str:
    """
    Writable per-user data folder, used as a fallback when the application
    folder is read-only (the typical `C:\\Program Files` case).
    """
    if os.name == "nt":
        root = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    else:
        root = os.environ.get("XDG_DATA_HOME") or os.path.join(
            os.path.expanduser("~"), ".local", "share"
        )
    return os.path.join(root, APP_SLUG)


def _is_writable_dir(path: str) -> bool:
    """Real writability probe (os.access lies on some SMB shares)."""
    try:
        os.makedirs(path, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path, prefix=".wtest_", delete=True):
            return True
    except Exception:
        return False


def writable_app_dir(subfolder: str) -> str:
    """
    Return `<base>/<subfolder>` when writable, otherwise the same subfolder
    inside the user data directory. Creates the chosen folder.
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

def setup_logging(logger_name: str = "proteus") -> logging.Logger:
    """
    Configure the application logger with rotation (5 files of 2 MB).
    Idempotent: repeated calls do not duplicate handlers.
    """
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return logger

    try:
        log_dir = writable_app_dir("logs")
        fname = f"proteus_{datetime.datetime.now():%Y%m%d}.log"
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
    except Exception as exc:  # pragma: no cover - permission dependent
        logger.addHandler(logging.StreamHandler())
        logger.warning("File logging unavailable: %s", exc)

    return logger


# ---------------------------------------------------------------------------
# Formatting and image reading helpers
# ---------------------------------------------------------------------------

def format_size(size_bytes: float) -> str:
    """Format a byte count as a readable string (e.g. `1.5 MB`)."""
    value = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if abs(value) < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


_SVG_LEN_RE = re.compile(r"^\s*([0-9]*\.?[0-9]+)\s*([a-z%]*)\s*$", re.IGNORECASE)

#: Conversion factors to CSS pixels (96 dpi), per the SVG specification.
_SVG_UNITS = {
    "": 1.0, "px": 1.0, "pt": 96 / 72, "pc": 16.0,
    "mm": 96 / 25.4, "cm": 96 / 2.54, "in": 96.0,
}


def _svg_length_to_px(raw: str | None) -> float | None:
    """Convert an SVG length (`120`, `2.5cm`, `10pt`) to pixels."""
    if not raw:
        return None
    match = _SVG_LEN_RE.match(raw)
    if not match:
        return None
    value, unit = float(match.group(1)), match.group(2).lower()
    factor = _SVG_UNITS.get(unit)
    if factor is None:  # percentages and relative units are not resolvable
        return None
    return value * factor


def svg_dimensions(filepath: str) -> tuple[int, int] | None:
    """
    Derive (width, height) in pixels from an SVG file, using the `width` and
    `height` attributes and falling back to `viewBox`. None if unreadable.
    """
    try:
        # SVGs can be huge: only the root element is needed.
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
    """Return (width, height) for the file, or None if undeterminable."""
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
    """Euclidean distance between two resolutions. `inf` if either is unknown."""
    if dim1 is None or dim2 is None:
        return float("inf")
    (w1, h1), (w2, h2) = dim1, dim2
    return ((w1 - w2) ** 2 + (h1 - h2) ** 2) ** 0.5


# ---------------------------------------------------------------------------
# Perceptual hashing
# ---------------------------------------------------------------------------

def _prepare_for_hash(image) -> "Image.Image":
    """
    Flatten an image to a grayscale grid suitable for hashing.

    Transparency is composited onto a fixed matte first: the same logo exported
    once with an alpha channel and once flattened must hash the same, otherwise
    content search misses exactly the duplicates it exists to find.
    """
    if image.mode in ("RGBA", "LA", "P"):
        image = image.convert("RGBA")
        background = Image.new("RGBA", image.size, HASH_MATTE + (255,))
        image = Image.alpha_composite(background, image)

    # One extra column: dHash compares each pixel with its right-hand neighbour.
    return image.convert("L").resize((HASH_SIDE + 1, HASH_SIDE),
                                     Image.Resampling.LANCZOS)


def perceptual_hash(filepath: str) -> int | None:
    """
    64-bit difference hash of an image, or None if it cannot be read.

    dHash encodes the *gradient* between neighbouring pixels rather than
    absolute brightness, which makes it stable across rescaling, re-encoding
    and moderate quality loss — the three things that happen to a logo as it
    gets copied around an organisation. It is not stable across recolouring,
    cropping or rotation; see the README for what that rules out.
    """
    if not PIL_AVAILABLE:
        return None
    if Path(filepath).suffix.lower() in NO_PIL_PREVIEW:
        return None

    try:
        with Image.open(filepath) as image:
            # The grid is mode "L", so its raw bytes are one grey level per
            # pixel in row-major order. tobytes() also avoids Image.getdata(),
            # which Pillow deprecates for removal in version 14.
            pixels = _prepare_for_hash(image).tobytes()
    except Exception:
        return None

    bits = 0
    for row in range(HASH_SIDE):
        offset = row * (HASH_SIDE + 1)
        for column in range(HASH_SIDE):
            bits <<= 1
            if pixels[offset + column] > pixels[offset + column + 1]:
                bits |= 1
    return bits


def hash_distance(hash_a: int, hash_b: int) -> int:
    """Hamming distance between two perceptual hashes (0 = identical)."""
    return bin(hash_a ^ hash_b).count("1")


def hash_similarity(hash_a: int | None, hash_b: int | None) -> float:
    """Similarity in [0..1] between two hashes; 0.0 when either is missing."""
    if hash_a is None or hash_b is None:
        return 0.0
    bits = HASH_SIDE * HASH_SIDE
    return 1.0 - hash_distance(hash_a, hash_b) / bits


class HashCache:
    """
    Cache of perceptual hashes.

    Content search compares every candidate against every reference, so without
    a cache each candidate would be decoded once per reference.
    """

    def __init__(self) -> None:
        self._cache: dict[str, int | None] = {}

    def get(self, path: str) -> int | None:
        if path not in self._cache:
            self._cache[path] = perceptual_hash(path)
        return self._cache[path]

    def __len__(self) -> int:
        return len(self._cache)


def best_similarity(
    path: str,
    reference_hashes: Sequence[int],
    cache: HashCache | None = None,
) -> float:
    """Highest similarity between `path` and any of the reference images."""
    if not reference_hashes:
        return 0.0
    candidate = (cache.get(path) if cache is not None else perceptual_hash(path))
    if candidate is None:
        return 0.0
    return max(hash_similarity(candidate, ref) for ref in reference_hashes)


def reference_hashes(paths: Sequence[str]) -> list[int]:
    """
    Hashes of the reference images, skipping any that cannot be read.

    Vector formats have no raster to hash, so an SVG reference silently
    contributes nothing; `validate_references` reports that to the user.
    """
    hashes = []
    for path in paths:
        digest = perceptual_hash(path)
        if digest is not None:
            hashes.append(digest)
    return hashes


def validate_references(paths: Sequence[str]) -> list[str]:
    """Problems that would make a content search useless. Empty when fine."""
    problems: list[str] = []
    if not paths:
        problems.append(t("Choose at least one reference image to search by "
                          "content."))
        return problems

    unreadable = [p for p in paths if perceptual_hash(p) is None]
    if len(unreadable) == len(paths):
        problems.append(
            t("None of the reference images can be read. Vector formats (SVG) "
              "and documents (PDF, EPS) cannot be matched by content.")
        )
    return problems


def normalized_ext(path_or_ext: str) -> str:
    """
    Normalised extension used to compare formats.
    `.jpg`/`.jpeg` and `.tif`/`.tiff` collapse onto the same value.
    """
    ext = path_or_ext if path_or_ext.startswith(".") else Path(path_or_ext).suffix
    ext = ext.lower()
    return EQUIVALENT_EXTENSIONS.get(ext, ext)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class FileInfo:
    """Metadata of a file found by the scan."""

    path: str
    name: str
    ext: str                    # lowercase extension with dot (".png")
    size: int
    dim: tuple[int, int] | None

    #: Visual similarity to the closest reference image, when the file was
    #: found by content search. None when it was found by file name, where the
    #: notion does not apply.
    similarity: float | None = None

    #: For a picture stored inside an Office package: the document on disk and
    #: the entry within it. Both None for an ordinary file.
    container: str | None = None
    entry: str | None = None

    @property
    def fmt(self) -> str:
        """Uppercase format for display (`PNG`)."""
        return self.ext.lstrip(".").upper()

    @property
    def size_str(self) -> str:
        return format_size(self.size)

    @property
    def dim_str(self) -> str:
        return f"{self.dim[0]}×{self.dim[1]} px" if self.dim else t("N/A")

    @property
    def embedded(self) -> bool:
        """True when this is a picture inside an Office document."""
        return self.container is not None

    @property
    def location(self) -> str:
        """Where the file lives, for display: the document for embedded ones."""
        return self.container or self.path

    @property
    def similarity_str(self) -> str:
        return "—" if self.similarity is None else f"{self.similarity * 100:.0f}%"

    @property
    def needs_review(self) -> bool:
        """
        True for a content hit found below the confident threshold.

        These are the rows a user must actually look at: the tool overwrites
        files, so an uncertain visual match is the one way it could destroy an
        unrelated image.
        """
        return self.similarity is not None and self.similarity < SIMILARITY_CONFIDENT

    @classmethod
    def from_embedded(cls, image: "office.EmbeddedImage",
                      similarity: float | None = None) -> "FileInfo":
        """
        Describe a picture stored inside an Office package.

        Its dimensions have to be read from the extracted bytes, so the image
        is unpacked to a temporary file and removed straight away.
        """
        dim = None
        temp = office.extract_to_temp(image.document, image.entry)
        if temp:
            try:
                dim = get_image_dimensions(temp)
            finally:
                try:
                    os.remove(temp)
                except OSError:
                    pass

        return cls(
            path=image.key,
            name=image.name,
            ext=image.ext,
            size=image.size,
            dim=dim,
            similarity=similarity,
            container=image.document,
            entry=image.entry,
        )

    @classmethod
    def from_path(cls, path: str, similarity: float | None = None) -> "FileInfo":
        stat = os.stat(path)
        return cls(
            path=path,
            name=os.path.basename(path),
            ext=Path(path).suffix.lower(),
            size=stat.st_size,
            dim=get_image_dimensions(path),
            similarity=similarity,
        )


@dataclass
class Match:
    """Proposed pairing between a file to replace and a source file."""

    target: FileInfo
    source: FileInfo | None
    score: float = float("inf")     # ranking score (resolution + name)
    enabled: bool = False
    manual: bool = False            # True when the user picked the source

    @property
    def source_name(self) -> str:
        return self.source.name if self.source else t("NO MATCH")

    @property
    def source_dim_str(self) -> str:
        return self.source.dim_str if self.source else ""

    @property
    def quality(self) -> str:
        """
        Canonical grade of the match, in English, usable as a translation key.

        It is based on the resolution gap, not on the ranking score: the
        latter includes name similarity, which is there to choose between
        equivalent candidates and must not downgrade a dimensionally perfect
        match.
        """
        if self.source is None:
            return QUALITY_NONE
        if self.manual:
            return QUALITY_MANUAL

        if self.target.dim is None or self.source.dim is None:
            similarity = name_similarity(self.target.path, self.source.path)
            return QUALITY_GOOD_LABEL if similarity >= NAME_ONLY_GOOD else QUALITY_WEAK

        relative = dimension_distance(self.target.dim, self.source.dim)
        if relative <= QUALITY_GOOD:
            return QUALITY_EXCELLENT
        if relative <= QUALITY_FAIR:
            return QUALITY_GOOD_LABEL
        return QUALITY_WEAK

    @property
    def distorts(self) -> bool:
        """
        True when this replacement would visibly stretch the picture.

        Only meaningful inside Office documents, where the frame keeps its own
        proportions regardless of what is dropped into it.
        """
        if self.source is None or not self.target.embedded:
            return False
        return office.aspect_mismatch(self.target.dim, self.source.dim)

    @property
    def quality_label(self) -> str:
        """Grade translated into the active language, for display."""
        return t(self.quality)


@dataclass
class ReplaceOutcome:
    """Outcome of replacing a single file."""

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
    """Summary of a whole replacement session."""

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
# Scanning
# ---------------------------------------------------------------------------

def parse_patterns(raw: str) -> list[str]:
    """
    Parse the search key entered by the user.
    Multiple patterns separated by `;` or `,` are allowed
    (e.g. `logo*.png; banner*.jpg`).
    """
    parts = [p.strip() for p in re.split(r"[;,]", raw or "")]
    return [p for p in parts if p]


def validate_pattern(raw: str) -> str | None:
    """Return an error message if the pattern is unusable, otherwise None."""
    patterns = parse_patterns(raw)
    if not patterns:
        return t("Enter at least one search pattern.")
    for pattern in patterns:
        if "/" in pattern or "\\" in pattern:
            return t("Pattern «{pattern}» contains a path separator: give the "
                     "file name only (e.g. logo*.png).").format(pattern=pattern)
        if set(pattern) <= {"*", "?", " "}:
            return t("Pattern «{pattern}» is too broad and would select any "
                     "file. Specify at least an extension.").format(pattern=pattern)
    return None


def matches_patterns(filename: str, patterns: Sequence[str]) -> bool:
    """True if the file name matches at least one pattern (case-insensitive)."""
    lowered = filename.lower()
    return any(fnmatch.fnmatchcase(lowered, p.lower()) for p in patterns)


def is_within(path: str, folder: str) -> bool:
    """True if `path` sits inside `folder` (or is the same folder)."""
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
    Scan `folder` recursively and return the files matching the pattern (or the
    patterns separated by `;`).

    exclude_dirs  folders to skip, typically the source folder when it is
                  nested inside the folder being scanned
    skip_backups  ignore the `.bak` files produced by the tool itself
    cancel_event  when set, aborts the scan with OperationCancelled
    on_error      callback for access errors (network shares, permissions)
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

        # Guard against junction/symlink cycles on network shares.
        try:
            stat = os.stat(root)
            key = (stat.st_dev, stat.st_ino)
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


def scan_by_content(
    folder: str,
    references: Sequence[str],
    *,
    threshold: float = DEFAULT_SIMILARITY,
    pattern: str = "",
    exclude_dirs: Iterable[str] = (),
    skip_backups: bool = True,
    progress: Callable[[int, int], None] | None = None,
    cancel_event: threading.Event | None = None,
    on_error: Callable[[str, Exception], None] | None = None,
) -> list[tuple[str, float]]:
    """
    Find images that *look like* the reference ones, whatever they are called.

    This is the answer to the hard half of a rebranding: the old logo is rarely
    filed under `logo*.png`. It hides in `header_bg.png`, `img_04.jpg`, or a
    folder someone named after a project from 2014.

    `pattern` still applies when given, as a cheap pre-filter — narrowing by
    name first avoids decoding every image in the tree.

    Returns `(path, similarity)` pairs sorted by descending similarity, so the
    most certain hits are reviewed first.
    """
    refs = reference_hashes(references)
    if not refs:
        return []

    patterns = parse_patterns(pattern)
    excluded = [os.path.realpath(d) for d in exclude_dirs if d]
    reference_real = {os.path.realpath(p) for p in references}

    def _walk_error(exc: OSError) -> None:
        if on_error:
            on_error(getattr(exc, "filename", folder) or folder, exc)

    # Enumerate first so progress can be reported against a known total.
    candidates: list[str] = []
    for root, dirs, files in os.walk(folder, onerror=_walk_error, followlinks=False):
        if cancel_event is not None and cancel_event.is_set():
            raise OperationCancelled()

        real_root = os.path.realpath(root)
        dirs[:] = [
            d for d in dirs
            if not any(is_within(os.path.join(real_root, d), ex) for ex in excluded)
        ]

        for fname in files:
            if skip_backups and fname.lower().endswith(BACKUP_SUFFIX):
                continue
            ext = Path(fname).suffix.lower()
            # Only raster formats can be hashed at all.
            if ext in NO_PIL_PREVIEW or ext not in SUPPORTED_FORMATS:
                continue
            if patterns and not matches_patterns(fname, patterns):
                continue
            candidates.append(os.path.join(root, fname))

    cache = HashCache()
    hits: list[tuple[str, float]] = []
    total = len(candidates)

    for index, path in enumerate(sorted(candidates), 1):
        if cancel_event is not None and cancel_event.is_set():
            raise OperationCancelled()
        # A reference image is not a target: it would be replaced by itself.
        if os.path.realpath(path) not in reference_real:
            score = best_similarity(path, refs, cache)
            if score >= threshold:
                hits.append((path, score))
        if progress:
            progress(index, total)

    hits.sort(key=lambda item: (-item[1], item[0]))
    return hits


def scan_office_documents(
    folder: str,
    *,
    references: Sequence[str] = (),
    threshold: float = DEFAULT_SIMILARITY,
    exclude_dirs: Iterable[str] = (),
    progress: Callable[[int, int], None] | None = None,
    cancel_event: threading.Event | None = None,
    on_error: Callable[[str, Exception], None] | None = None,
) -> list[FileInfo]:
    """
    Find replaceable pictures inside the Office documents under `folder`.

    Without `references` every embedded picture is returned; with them, only
    those that look like the old logo. Content matching is the sensible mode
    here: nobody names a picture inside a document, so `image1.png` tells you
    nothing about what it depicts.
    """
    refs = reference_hashes(references) if references else []
    excluded = [os.path.realpath(d) for d in exclude_dirs if d]

    def _walk_error(exc: OSError) -> None:
        if on_error:
            on_error(getattr(exc, "filename", folder) or folder, exc)

    documents: list[str] = []
    for root, dirs, files in os.walk(folder, onerror=_walk_error, followlinks=False):
        if cancel_event is not None and cancel_event.is_set():
            raise OperationCancelled()
        real_root = os.path.realpath(root)
        dirs[:] = [d for d in dirs
                   if not any(is_within(os.path.join(real_root, d), ex)
                              for ex in excluded)]
        for fname in files:
            if office.is_office_document(fname):
                documents.append(os.path.join(root, fname))

    found: list[FileInfo] = []
    total = len(documents)

    for index, document in enumerate(sorted(documents), 1):
        if cancel_event is not None and cancel_event.is_set():
            raise OperationCancelled()
        for image in office.list_images(document):
            similarity = None
            if refs:
                temp = office.extract_to_temp(document, image.entry)
                if temp is None:
                    continue
                try:
                    similarity = best_similarity(temp, refs)
                finally:
                    try:
                        os.remove(temp)
                    except OSError:
                        pass
                if similarity < threshold:
                    continue
            found.append(FileInfo.from_embedded(image, similarity=similarity))
        if progress:
            progress(index, total)

    return found


def collect_source_files(
    folder: str,
    *,
    cancel_event: threading.Event | None = None,
    on_error: Callable[[str, Exception], None] | None = None,
) -> list[str]:
    """List every supported image file present in the source folder."""
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
# Matching
# ---------------------------------------------------------------------------

def name_similarity(path_a: str, path_b: str) -> float:
    """Similarity [0..1] between two file names, extension excluded."""
    stem_a = Path(path_a).stem.lower()
    stem_b = Path(path_b).stem.lower()
    return difflib.SequenceMatcher(None, stem_a, stem_b).ratio()


def dimension_distance(
    target_dim: tuple[int, int] | None,
    source_dim: tuple[int, int] | None,
) -> float:
    """
    *Relative* resolution gap in [0..1]; 0 means identical resolutions.

    The euclidean distance is normalised over the target diagonal, so a 20 px
    gap weighs heavily on a 32×32 icon and lightly on a 1920×1080 banner.
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
    *Ranking* score: 0 is perfect, larger is worse.

    Used only to order candidates against each other. The resolution gap
    weighs 65%, name similarity the remaining 35%; the latter breaks ties when
    several sources share the same resolution. The grade shown to the user
    comes from `Match.quality`, which looks at resolution alone.
    """
    name_component = 1.0 - name_similarity(target_path, source_path)

    if target_dim is None or source_dim is None:
        # With no comparable resolutions only the name is left.
        return name_component

    return (WEIGHT_DIMENSION * dimension_distance(target_dim, source_dim)
            + WEIGHT_NAME * name_component)


class DimensionCache:
    """
    Cache of file resolutions.

    Without it, matching reopens every source image for every target file
    (O(N×M) disk reads), which is prohibitive on a network share.
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
    Find the source file best suited to replace `target`.

    Criteria, in order of importance:
      1. same format (with `.jpg`/`.jpeg` and `.tif`/`.tiff` equivalent);
      2. closest possible resolution;
      3. most similar file name, as a tie-break.

    Returns `(source, score)`; `(None, inf)` when there is no candidate.
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
    """Build the list of proposed matches for every target."""
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
# Backup and replacement
# ---------------------------------------------------------------------------

def make_backup_path(target: str) -> str:
    """
    Backup path that never overwrites an existing backup.

    The first run produces `file.png.bak`; if that already exists (a second
    rebranding campaign over the same folder) it falls back to
    `file.png.20260806-101500.bak`, so the original is never lost.
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
    Replace `target` with the contents of `source`.

    The copy goes to a temporary file in the same folder and is then promoted
    with `os.replace`: if anything fails halfway through the copy the original
    file stays intact, never truncated.
    """
    if not os.path.isfile(source):
        return ReplaceOutcome(target, source, "error",
                              t("Source file not found, or not a file."))
    if not os.path.isfile(target):
        return ReplaceOutcome(target, source, "error",
                              t("File to replace not found, or not a file."))
    try:
        if os.path.samefile(source, target):
            return ReplaceOutcome(target, source, "skipped",
                                  t("Source and destination are the same file."))
    except OSError:
        pass

    if dry_run:
        return ReplaceOutcome(target, source, "ok",
                              t("Dry run: nothing written to disk."),
                              make_backup_path(target) if backup else None)

    backup_path: str | None = None
    tmp_path: str | None = None
    folder = os.path.dirname(target) or "."

    try:
        if backup:
            backup_path = make_backup_path(target)
            shutil.copy2(target, backup_path)

        fd, tmp_path = tempfile.mkstemp(prefix=".proteus_", dir=folder)
        os.close(fd)
        shutil.copy2(source, tmp_path)
        os.replace(tmp_path, target)   # atomic on the same filesystem
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


def replace_in_document(
    document: str,
    replacements: dict[str, str],
    *,
    backup: bool = True,
    dry_run: bool = False,
) -> ReplaceOutcome:
    """
    Replace one or more pictures inside a single Office document.

    Every picture destined for the same document is handled in one pass: the
    package is rewritten once and, crucially, backed up once. Replacing three
    logos in a report one at a time would otherwise produce three backups of
    successive states and never a clean copy of the original.
    """
    if not os.path.isfile(document):
        return ReplaceOutcome(document, "", "error",
                              t("File to replace not found, or not a file."))

    payload: dict[str, bytes] = {}
    for entry, source in replacements.items():
        if not os.path.isfile(source):
            return ReplaceOutcome(document, source, "error",
                                  t("Source file not found, or not a file."))
        try:
            with open(source, "rb") as handle:
                payload[entry] = handle.read()
        except OSError as exc:
            return ReplaceOutcome(document, source, "error", str(exc))

    if dry_run:
        return ReplaceOutcome(document, ", ".join(replacements.values()), "ok",
                              t("Dry run: nothing written to disk."),
                              make_backup_path(document) if backup else None)

    backup_path: str | None = None
    try:
        if backup:
            backup_path = make_backup_path(document)
            shutil.copy2(document, backup_path)
        office.write_replacements(document, payload)
        return ReplaceOutcome(document, ", ".join(replacements.values()), "ok",
                              "", backup_path)
    except Exception as exc:
        return ReplaceOutcome(document, ", ".join(replacements.values()),
                              "error", str(exc), backup_path)


def replace_all(
    matches: Sequence[Match],
    *,
    backup: bool = True,
    dry_run: bool = False,
    progress: Callable[[int, int, ReplaceOutcome], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> ReplaceReport:
    """
    Run the replacement over every match passed in.

    Loose files are handled one by one. Pictures embedded in Office documents
    are grouped by document first, so each package is rewritten and backed up
    exactly once however many of its images are being replaced.
    """
    report = ReplaceReport()

    loose: list[Match] = []
    grouped: dict[str, dict[str, str]] = {}
    for match in matches:
        if match.target.embedded and match.source is not None:
            grouped.setdefault(match.target.container, {})[
                match.target.entry] = match.source.path
        else:
            loose.append(match)

    total = len(loose) + len(grouped)
    index = 0

    for match in loose:
        if cancel_event is not None and cancel_event.is_set():
            report.cancelled = True
            return report
        index += 1
        if match.source is None:
            outcome = ReplaceOutcome(match.target.path, "", "skipped", t("No match."))
        else:
            outcome = replace_file(match.target.path, match.source.path,
                                   backup=backup, dry_run=dry_run)
        report.outcomes.append(outcome)
        if progress:
            progress(index, total, outcome)

    for document, replacements in sorted(grouped.items()):
        if cancel_event is not None and cancel_event.is_set():
            report.cancelled = True
            return report
        index += 1
        outcome = replace_in_document(document, replacements,
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
    Original path derived from a backup file.

    `logo.png.bak` and `logo.png.20260806-101500.bak` both yield `logo.png`.
    """
    without_stamp = _TIMESTAMPED_BAK_RE.sub("", backup_path)
    if without_stamp != backup_path:
        return without_stamp
    if backup_path.lower().endswith(BACKUP_SUFFIX):
        return backup_path[: -len(BACKUP_SUFFIX)]
    return backup_path


def backup_age_key(backup_path: str) -> tuple:
    """
    Chronological sort key for the backups of one file.

    The backup without a timestamp (`logo.png.bak`) is always the first one
    created, hence the oldest; timestamped ones follow in date order. Sorting
    by name is not enough: `logo.png.20260806-101500.bak` would sort before
    `logo.png.bak`, inverting the real order.
    """
    match = _TIMESTAMPED_BAK_RE.search(backup_path)
    if not match:
        return (0, "", 0)
    return (1, match.group("stamp"), int(match.group("counter") or 0))


def find_backups(folder: str) -> list[str]:
    """
    List the backups present in `folder`, recursively.

    Ordered by original file and, within each, from oldest to newest.
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
    Restore the original files from the `.bak` backups found in `folder`.

    When several backups exist for the same file the oldest one is used, that
    is the one predating the first replacement.
    """
    report = ReplaceReport()
    backups = find_backups(folder)

    # One backup per original file: the first in order (the oldest).
    chosen: dict[str, str] = {}
    for backup in backups:
        chosen.setdefault(backup_origin(backup), backup)

    items = sorted(chosen.items())
    total = len(items)

    for index, (origin, backup) in enumerate(items, 1):
        if cancel_event is not None and cancel_event.is_set():
            report.cancelled = True
            break
        try:
            shutil.copy2(backup, origin)
            if remove_backup:
                os.remove(backup)
            outcome = ReplaceOutcome(origin, backup, "ok", t("Restored from backup."))
        except Exception as exc:
            outcome = ReplaceOutcome(origin, backup, "error", str(exc))
        report.outcomes.append(outcome)
        if progress:
            progress(index, total, outcome)

    return report


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

def export_matches_csv(matches: Sequence[Match], destination: str) -> str:
    """Export the matches to CSV (`;` separator, Excel-friendly in Europe)."""
    with open(destination, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh, delimiter=";")
        writer.writerow([
            t("Included"), t("File to Replace"), t("Format"), t("Target resolution"),
            t("Target weight"), t("New Source File"), t("Source resolution"),
            t("Quality"), t("Score"), t("Target path"), t("Source path"),
        ])
        for match in matches:
            writer.writerow([
                t("YES") if match.enabled else t("NO"),
                match.target.name,
                match.target.fmt,
                match.target.dim_str,
                match.target.size_str,
                match.source_name,
                match.source_dim_str,
                match.quality_label,
                "" if match.score == float("inf") else f"{match.score:.4f}",
                match.target.path,
                match.source.path if match.source else "",
            ])
    return destination


def export_report_csv(report: ReplaceReport, destination: str) -> str:
    """Export the outcome of a replacement to CSV."""
    with open(destination, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh, delimiter=";")
        writer.writerow([t("Outcome"), t("File"), t("Source"), t("Backup"),
                         t("Message")])
        for outcome in report.outcomes:
            writer.writerow([
                outcome.status.upper(), outcome.target, outcome.source,
                outcome.backup or "", outcome.message,
            ])
    return destination


# ---------------------------------------------------------------------------
# Settings persistence
# ---------------------------------------------------------------------------

SETTINGS_FILE = "settings.json"
DEFAULT_SETTINGS: dict[str, object] = {
    "language": i18n.DEFAULT_LANGUAGE,
    "source_folder": "",
    "scan_folder": "",
    "search_pattern": "logo*.png",
    "search_mode": "name",
    "references": [],
    "similarity": int(DEFAULT_SIMILARITY * 100),
    "include_office": False,
    "backup": True,
    "dry_run": False,
}


def settings_path() -> str:
    return os.path.join(writable_app_dir("config"), SETTINGS_FILE)


def load_settings() -> dict:
    """Load the last used settings; return defaults if absent or corrupted."""
    settings = dict(DEFAULT_SETTINGS)
    try:
        with open(settings_path(), encoding="utf-8") as fh:
            stored = json.load(fh)
        if isinstance(stored, dict):
            settings.update({k: v for k, v in stored.items() if k in DEFAULT_SETTINGS})
    except (OSError, ValueError):
        pass

    if settings["language"] not in i18n.LANGUAGES:
        settings["language"] = i18n.DEFAULT_LANGUAGE
    if settings["search_mode"] not in ("name", "content"):
        settings["search_mode"] = "name"
    if not isinstance(settings["references"], list):
        settings["references"] = []
    try:
        settings["similarity"] = max(50, min(100, int(settings["similarity"])))
    except (TypeError, ValueError):
        settings["similarity"] = int(DEFAULT_SIMILARITY * 100)
    return settings


def save_settings(values: dict) -> bool:
    """Save the settings. Returns False when saving is not possible."""
    try:
        payload = {k: v for k, v in values.items() if k in DEFAULT_SETTINGS}
        with open(settings_path(), "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Configuration validation
# ---------------------------------------------------------------------------

def validate_config(source_folder: str, scan_folder: str, pattern: str,
                    *, require_pattern: bool = True) -> list[str]:
    """
    Validate the scan configuration.
    Returns the list of blocking problems (empty when everything is fine).

    `require_pattern` is False for content search, where the pattern is only an
    optional pre-filter and an empty one legitimately means "every image".
    """
    problems: list[str] = []

    if not source_folder or not os.path.isdir(source_folder):
        problems.append(t("Select a valid source folder."))
    if not scan_folder or not os.path.isdir(scan_folder):
        problems.append(t("Select a valid folder to scan."))

    if require_pattern or pattern.strip():
        pattern_error = validate_pattern(pattern)
        if pattern_error:
            problems.append(pattern_error)

    if (source_folder and scan_folder
            and os.path.isdir(source_folder) and os.path.isdir(scan_folder)):
        try:
            if os.path.samefile(source_folder, scan_folder):
                problems.append(
                    t("The source folder and the folder to scan are the same: "
                      "the new logos would be replaced with themselves.")
                )
        except OSError:
            pass

    return problems


def config_warnings(source_folder: str, scan_folder: str) -> list[str]:
    """Non-blocking warnings about the chosen configuration."""
    warnings: list[str] = []
    if not (source_folder and scan_folder):
        return warnings
    if is_within(source_folder, scan_folder):
        warnings.append(
            t("The source folder sits inside the folder to scan: it will be "
              "excluded from the search automatically.")
        )
    return warnings
