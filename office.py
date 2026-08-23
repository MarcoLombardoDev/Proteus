#!/usr/bin/env python
# Proteus — Rebranding Tool
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.
# A commercial licence, without the AGPL's obligations, is available for use
# in proprietary or closed-source products — see COMMERCIAL-LICENSE.md.

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

import paths
from i18n import t

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

#: Vector metafiles Office writes when a logo is *pasted* rather than inserted.
#: They cannot be replaced — but they are exactly where a corporate logo hides,
#: so they are reported by name instead of quietly ignored.
METAFILE_EXTENSIONS = frozenset({".emf", ".wmf"})

#: First bytes of an OLE compound file. A password-protected .docx is one of
#: these rather than a ZIP, which is why it looks "corrupt" from the outside.
OLE_MAGIC = b"\xd0\xcf\x11\xe0"

#: Separator between a document and an entry inside it, in the synthetic path
#: used to identify an embedded image. Chosen because it cannot occur in a
#: Windows or POSIX file name, so the two halves are always recoverable.
ENTRY_SEPARATOR = "!/"


@dataclass(frozen=True)
class Problem:
    """
    Something Proteus found but cannot deal with on its own.

    The whole point of this type is that it reaches the user. A rebranding that
    quietly leaves three logos in place is worse than one that stops and names
    them, because nobody goes looking for a failure they were never told about.

    It lives here rather than in `pdf.py` because both document formats produce
    them, and `pdf.py` already depends on this module.
    """

    path: str            # file, or `document!/entry` when it is one picture
    reason: str          # what is wrong, already translated
    hint: str = ""       # what the user can do by hand

    @property
    def name(self) -> str:
        return os.path.basename(self.path.split(ENTRY_SEPARATOR)[0])


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


def list_images(document: str) -> tuple[list[EmbeddedImage], list[Problem]]:
    """
    Every replaceable picture inside `document`, plus what could not be handled.

    Never raises: a corrupt document must not abort a scan of ten thousand
    files. But it is not silent either — the second half of the return value
    carries everything that was noticed and skipped, so it can be put in front
    of the user. The two cases that matter in practice:

    * **a pasted logo.** Office stores it as an EMF or WMF metafile, which
      cannot be rasterised, compared or previewed. This is how most logos end
      up in a corporate Word document, so saying nothing about it would leave
      the commonest case silently unhandled.
    * **a package that will not open**, because it is damaged or
      password-protected. A protected .docx is an OLE compound file rather than
      a ZIP, which is worth telling the user, since "corrupt" would send them
      looking for the wrong problem.
    """
    if not is_office_document(document):
        return [], []

    found: list[EmbeddedImage] = []
    problems: list[Problem] = []
    metafiles: list[str] = []

    try:
        with zipfile.ZipFile(paths.long_path(document)) as package:
            for info in package.infolist():
                if info.is_dir():
                    continue
                # Pictures live under a media/ folder in every OOXML flavour:
                # word/media/, ppt/media/, xl/media/.
                if "/media/" not in info.filename:
                    continue
                ext = posixpath.splitext(info.filename)[1].lower()
                if ext in METAFILE_EXTENSIONS:
                    metafiles.append(posixpath.basename(info.filename))
                    continue
                if ext not in EMBEDDED_IMAGE_EXTENSIONS:
                    continue
                found.append(EmbeddedImage(document=document,
                                           entry=info.filename,
                                           size=info.file_size))
    except (zipfile.BadZipFile, OSError, RuntimeError) as exc:
        return [], [Problem(document, *_unreadable(document, exc))]

    if metafiles:
        problems.append(Problem(
            document,
            t("Contains {count} pasted image(s) ({names}) that cannot be "
              "replaced automatically.").format(count=len(metafiles),
                                                names=", ".join(metafiles[:3])),
            t("Open the document, delete the pasted logo and insert the new "
              "one with Insert > Pictures."),
        ))

    return sorted(found, key=lambda image: image.entry), problems


def _unreadable(document: str, exc: Exception) -> tuple[str, str]:
    """Reason and remedy for a package that would not open."""
    try:
        with open(paths.long_path(document), "rb") as handle:
            protected = handle.read(4) == OLE_MAGIC
    except OSError:
        protected = False

    if protected:
        return (t("This document is password-protected, so its images cannot "
                  "be read."),
                t("Remove the password, then run the scan again."))
    return (t("This document could not be opened: {error}").format(error=exc),
            t("Open it in Office to check it is not damaged."))


def extract(document: str, entry: str) -> bytes | None:
    """Raw bytes of one embedded image, or None if it cannot be read."""
    try:
        with zipfile.ZipFile(paths.long_path(document)) as package:
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
    fd, tmp_path = tempfile.mkstemp(prefix=".proteus_", dir=paths.long_path(folder))
    os.close(fd)

    try:
        with zipfile.ZipFile(paths.long_path(document)) as source, \
                zipfile.ZipFile(paths.long_path(tmp_path), "w") as target:
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

        os.replace(paths.long_path(tmp_path), paths.long_path(document))
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
