#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Proteus - reading and rewriting images inside Office documents.

Modern Office files (.docx, .pptx, .xlsx and their macro-enabled and template
variants) are ZIP packages, and every picture they contain is stored as a plain
image file under a `media/` folder inside them. That makes a logo embedded in a
report as replaceable as one sitting loose on a file server — which matters,
because in a real rebranding most of the logos are in documents, not in stray
PNGs.

Only the standard library is used: `zipfile` is all this needs.

Deliberately *not* handled:
  * the pre-2007 binary formats (.doc, .ppt, .xls) — OLE compound files, not ZIPs;
  * EMF/WMF metafiles, which Office produces when a logo is pasted rather than
    inserted, and which cannot be compared or previewed;
  * images composited into a larger picture, or drawn with native shapes.
"""

from __future__ import annotations

import os
import posixpath
import tempfile
import zipfile
from dataclasses import dataclass

#: Package formats built on OOXML. The macro-enabled and template variants use
#: exactly the same layout, so they cost nothing extra to support.
OFFICE_EXTENSIONS = frozenset({
    ".docx", ".docm", ".dotx", ".dotm",
    ".pptx", ".pptm", ".potx", ".potm", ".ppsx",
    ".xlsx", ".xlsm", ".xltx", ".xltm",
})

#: Image types worth touching inside a package. EMF and WMF are deliberately
#: absent: they are vector metafiles that Pillow cannot read, so they could be
#: neither previewed nor compared, only swapped blindly.
EMBEDDED_IMAGE_EXTENSIONS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif", ".webp",
})

#: Separator between a document and an entry inside it, in the synthetic path
#: used to identify an embedded image. Chosen because it cannot occur in a
#: Windows or POSIX file name, so the two halves are always recoverable.
ENTRY_SEPARATOR = "!/"


@dataclass(frozen=True)
class EmbeddedImage:
    """One picture stored inside an Office package."""

    document: str       # path of the .docx/.pptx/.xlsx on disk
    entry: str          # path inside the package, e.g. "word/media/image1.png"
    size: int           # uncompressed size in bytes

    @property
    def ext(self) -> str:
        return posixpath.splitext(self.entry)[1].lower()

    @property
    def name(self) -> str:
        """`report.docx!/image1.png` — short enough to read in a table."""
        return (f"{os.path.basename(self.document)}{ENTRY_SEPARATOR}"
                f"{posixpath.basename(self.entry)}")

    @property
    def key(self) -> str:
        """Unique identifier usable where a file path would normally go."""
        return f"{self.document}{ENTRY_SEPARATOR}{self.entry}"


def is_office_document(path: str) -> bool:
    """True for a file whose extension is an OOXML package format."""
    return os.path.splitext(path)[1].lower() in OFFICE_EXTENSIONS


def split_key(key: str) -> tuple[str, str] | None:
    """Split `document!/entry` back into its two halves, or None if not one."""
    if ENTRY_SEPARATOR not in key:
        return None
    document, entry = key.split(ENTRY_SEPARATOR, 1)
    return document, entry


def is_embedded_key(key: str) -> bool:
    return ENTRY_SEPARATOR in key


def list_images(document: str) -> list[EmbeddedImage]:
    """
    Every replaceable picture inside `document`.

    Returns an empty list rather than raising when the file is not a readable
    package: a corrupt or password-protected document should be skipped, not
    abort a scan of ten thousand files.
    """
    if not is_office_document(document):
        return []

    found: list[EmbeddedImage] = []
    try:
        with zipfile.ZipFile(document) as package:
            for info in package.infolist():
                if info.is_dir():
                    continue
                # Pictures live under a media/ folder in every OOXML flavour:
                # word/media/, ppt/media/, xl/media/.
                if "/media/" not in info.filename:
                    continue
                if posixpath.splitext(info.filename)[1].lower() \
                        not in EMBEDDED_IMAGE_EXTENSIONS:
                    continue
                found.append(EmbeddedImage(document=document,
                                           entry=info.filename,
                                           size=info.file_size))
    except (zipfile.BadZipFile, OSError, RuntimeError):
        return []

    return sorted(found, key=lambda image: image.entry)


def extract(document: str, entry: str) -> bytes | None:
    """Raw bytes of one embedded image, or None if it cannot be read."""
    try:
        with zipfile.ZipFile(document) as package:
            return package.read(entry)
    except (zipfile.BadZipFile, KeyError, OSError, RuntimeError):
        return None


def extract_to_temp(document: str, entry: str) -> str | None:
    """
    Write an embedded image to a temporary file and return its path.

    Pillow needs a real file (or at least a stream) to work with, and the
    caller usually wants the right extension so format detection succeeds.
    The caller owns the file and must delete it.
    """
    data = extract(document, entry)
    if data is None:
        return None

    suffix = posixpath.splitext(entry)[1] or ".bin"
    fd, path = tempfile.mkstemp(prefix=".proteus_embedded_", suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
    except OSError:
        os.remove(path)
        return None
    return path


def write_replacements(document: str, replacements: dict[str, bytes]) -> None:
    """
    Rewrite `document` with the given entries replaced.

    A ZIP entry cannot be modified in place, so the package is rebuilt: every
    other entry is copied across untouched, keeping its original order,
    compression method and permissions. Order matters because the OPC
    specification expects `[Content_Types].xml` in the package, and some
    readers are particular about where it sits.

    The rebuild lands on a temporary file in the same folder and is promoted
    with `os.replace`, so an interrupted write can never leave a half-written
    document behind — the same guarantee ordinary replacement already gives.

    Raises on failure; the caller decides how to report it.
    """
    folder = os.path.dirname(document) or "."
    fd, tmp_path = tempfile.mkstemp(prefix=".proteus_", dir=folder)
    os.close(fd)

    try:
        with zipfile.ZipFile(document) as source, \
                zipfile.ZipFile(tmp_path, "w") as target:
            for info in source.infolist():
                data = (replacements[info.filename]
                        if info.filename in replacements
                        else source.read(info.filename))

                # Rebuild the entry metadata rather than reusing the original
                # ZipInfo: its header offsets belong to the old archive.
                copied = zipfile.ZipInfo(filename=info.filename,
                                         date_time=info.date_time)
                copied.compress_type = info.compress_type
                copied.external_attr = info.external_attr
                copied.internal_attr = info.internal_attr
                copied.create_system = info.create_system
                target.writestr(copied, data)

        os.replace(tmp_path, document)
        tmp_path = None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Aspect ratio
# ---------------------------------------------------------------------------

#: How far the new picture's aspect ratio may drift from the old one before the
#: replacement is called out. 2% absorbs rounding without hiding a real change.
ASPECT_TOLERANCE = 0.02


def aspect_ratio(dim: tuple[int, int] | None) -> float | None:
    if not dim or not dim[1]:
        return None
    return dim[0] / dim[1]


def aspect_mismatch(old_dim: tuple[int, int] | None,
                    new_dim: tuple[int, int] | None,
                    tolerance: float = ASPECT_TOLERANCE) -> bool:
    """
    True when swapping these two pictures would visibly distort the document.

    Inside an Office file the *frame* is stored in the document XML, not in the
    picture: a shape sized 3.33 × 1.11 inches stays 3.33 × 1.11 inches after
    the image inside it is swapped. Drop a square logo into a frame that was
    laid out for a 3:1 one and Word will stretch it to fit, silently.

    The old picture's own aspect ratio is used as the proxy for the frame,
    since the frame was almost certainly sized to it when the image was first
    inserted. That is an approximation, and a cheap one compared with parsing
    the drawing XML of three different formats — but it catches the case that
    actually ruins documents.
    """
    old_ratio = aspect_ratio(old_dim)
    new_ratio = aspect_ratio(new_dim)
    if old_ratio is None or new_ratio is None:
        return False
    return abs(new_ratio - old_ratio) / old_ratio > tolerance
