#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Proteus - reading and replacing raster images inside PDF files.

A PDF is not a ZIP, so none of `office.py` applies. Every bitmap it shows is an
*image XObject*: a stream of encoded pixels plus a dictionary saying how wide it
is, how it is compressed and in which colour space. The page's content stream
then paints it through a transformation matrix. Replacing a logo therefore means
swapping the stream and its dictionary while leaving the reference — and the
matrix — alone.

This module uses **pypdf** (BSD-3-Clause) and specifically its native
`ImageFile.replace()`, rather than editing the file's bytes directly. Hand-rolled
surgery does work on simple documents — it was measured before this module was
written — but it has to rebuild the cross-reference table by hand, and it goes
blind the moment a producer uses object streams, which modern writers do. On a
tool that overwrites files in place, that trade is not worth 400 KB.

**What this cannot do, and says so.** A logo drawn as vector paths in the content
stream is not an image XObject at all: it is invisible here, and most
print-quality PDFs are built that way. Inline images cannot be replaced either.
Neither case is swallowed — both are reported as problems, because a logo the
tool fails to replace without telling anyone is worse than one it refuses.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass

from i18n import t
from office import ENTRY_SEPARATOR

try:
    import pypdf
    PYPDF_AVAILABLE = True
except ImportError:                            # pragma: no cover - env dependent
    pypdf = None
    PYPDF_AVAILABLE = False

#: The only extension handled here.
PDF_EXTENSIONS = frozenset({".pdf"})

#: Encodings whose pixels Pillow can reconstruct once pypdf has decoded the
#: stream. Anything else is reported rather than guessed at: JPEG 2000, JBIG2
#: and the fax encodings would have to be swapped blind.
DECODABLE_FILTERS = frozenset({
    "/DCTDecode", "/FlateDecode", "/LZWDecode", "/RunLengthDecode",
})


@dataclass(frozen=True)
class EmbeddedImage:
    """
    One raster image inside a PDF.

    `entry` is a position, `"p2i1"`, meaning "first image painted on page 2".

    Neither of the obvious alternatives works. A PDF image has no file name —
    pypdf synthesises display names like `image.jpg` and gives the same one to
    every image in the document. And its object number, which *is* intrinsic,
    is renumbered by `PdfWriter(clone_from=...)`: an image read as object 1
    comes back as object 4, so a number captured while scanning cannot find the
    picture again while writing. Position survives the clone; `write_replacements`
    checks the stream size still matches before touching anything.
    """

    document: str        # path of the .pdf on disk
    entry: str           # "p2i1" — image 1 painted on page 2
    size: int            # encoded stream size in bytes
    page: int            # 1-based page number, for display only
    ext: str = ".png"    # encoding pypdf reports, e.g. ".jpg"

    @property
    def name(self) -> str:
        """`brochure.pdf!/p2i1` — identifies the picture in one line."""
        return (f"{os.path.basename(self.document)}{ENTRY_SEPARATOR}{self.entry}")

    @property
    def key(self) -> str:
        """Unique identifier usable where a file path would normally go."""
        return f"{self.document}{ENTRY_SEPARATOR}{self.entry}"


@dataclass(frozen=True)
class Problem:
    """
    Something Proteus found but cannot deal with on its own.

    The whole point of this type is that it reaches the user. A rebranding that
    quietly leaves three logos in place is worse than one that stops and names
    them, because nobody goes looking for a failure they were never told about.
    """

    path: str            # file, or `document!/entry` when it is one picture
    reason: str          # what is wrong, already translated
    hint: str = ""       # what the user can do by hand

    @property
    def name(self) -> str:
        return os.path.basename(self.path.split(ENTRY_SEPARATOR)[0])


def is_pdf(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in PDF_EXTENSIONS


def entry_for(page: int, index: int) -> str:
    """Positional identity of one image: page number and paint order."""
    return f"p{page}i{index}"


def _is_signed(reader) -> bool:
    """
    True when the document carries a digital signature.

    Any byte written into a signed PDF invalidates the signature, so these are
    refused rather than silently broken.
    """
    try:
        root = reader.trailer["/Root"]
        form = root.get("/AcroForm")
        if not form:
            return False
        if int(form.get("/SigFlags", 0)) & 1:
            return True
        for field in form.get("/Fields", []) or []:
            try:
                if field.get_object().get("/FT") == "/Sig":
                    return True
            except Exception:
                continue
    except Exception:
        return False
    return False


def inspect(document: str) -> list[Problem]:
    """
    Problems that stop this PDF being processed at all.

    Returned before any image is looked at, so the caller can report the file
    and move on instead of failing halfway through.
    """
    if not PYPDF_AVAILABLE:
        return [Problem(
            document,
            t("PDF support needs the «pypdf» package, which is not installed."),
            t("Install it with: pip install pypdf"),
        )]

    try:
        reader = pypdf.PdfReader(document)
    except Exception as exc:
        return [Problem(document,
                        t("This PDF could not be read: {error}").format(error=exc),
                        t("Open it in a PDF reader to check it is not damaged."))]

    problems: list[Problem] = []
    if reader.is_encrypted:
        problems.append(Problem(
            document,
            t("This PDF is encrypted, so its images cannot be read."),
            t("Remove the password, then run the scan again."),
        ))
    if _is_signed(reader):
        problems.append(Problem(
            document,
            t("This PDF is digitally signed: replacing an image would "
              "invalidate the signature."),
            t("Replace the logo in the source document and sign it again."),
        ))
    return problems


def list_images(document: str, *,
                report_empty: bool = False) -> tuple[list[EmbeddedImage], list[Problem]]:
    """
    Every replaceable raster image inside `document`, plus what went wrong.

    `report_empty` asks for a problem to be raised when the file contains no
    replaceable image at all. The caller turns it on when the user pointed at
    this file by name — that is the case where "nothing found" is a finding,
    because the logo is presumably there and drawn as vectors. During a
    whole-tree content search it stays off, or every unrelated PDF in the tree
    would produce a line of noise.
    """
    if not is_pdf(document):
        return [], []

    blocking = inspect(document)
    if blocking:
        return [], blocking

    images: list[EmbeddedImage] = []
    problems: list[Problem] = []

    try:
        reader = pypdf.PdfReader(document)
        for number, page in enumerate(reader.pages, 1):
            try:
                page_images = list(page.images)
            except Exception as exc:
                problems.append(Problem(
                    document,
                    t("Page {page} of this PDF could not be read: {error}")
                    .format(page=number, error=exc),
                    t("The other pages were still processed."),
                ))
                continue

            for index, image in enumerate(page_images, 1):
                entry = entry_for(number, index)

                # Inline images live inside the content stream itself rather
                # than as their own object, so there is nothing to point at and
                # nothing pypdf can replace.
                if getattr(image, "is_inline", False):
                    problems.append(Problem(
                        document,
                        t("Page {page} contains an inline image that cannot be "
                          "replaced automatically.").format(page=number),
                        t("Edit this page by hand in a PDF editor."),
                    ))
                    continue

                filters = _filters_of(image)
                unsupported = [f for f in filters if f not in DECODABLE_FILTERS]
                if unsupported:
                    problems.append(Problem(
                        f"{document}{ENTRY_SEPARATOR}{entry}",
                        t("Image on page {page} uses the unsupported encoding "
                          "{encoding}.").format(page=number,
                                                encoding=", ".join(unsupported)),
                        t("Replace this picture by hand in a PDF editor."),
                    ))
                    continue

                try:
                    data = image.data
                except Exception as exc:
                    problems.append(Problem(
                        f"{document}{ENTRY_SEPARATOR}{entry}",
                        t("Image on page {page} could not be decoded: {error}")
                        .format(page=number, error=exc),
                        t("Replace this picture by hand in a PDF editor."),
                    ))
                    continue

                images.append(EmbeddedImage(
                    document=document, entry=entry, size=len(data),
                    page=number, ext=_extension_of(image),
                ))
    except Exception as exc:
        problems.append(Problem(
            document,
            t("This PDF could not be read: {error}").format(error=exc),
            t("Open it in a PDF reader to check it is not damaged."),
        ))

    if report_empty and not images and not problems:
        problems.append(Problem(
            document,
            t("No replaceable image found in this PDF: a logo drawn as vector "
              "artwork cannot be swapped."),
            t("Replace it by hand, or export the page and edit the original."),
        ))

    return images, problems


def _filters_of(image) -> list[str]:
    """Encoding filters declared on an image XObject."""
    try:
        obj = image.indirect_reference.get_object()
        raw = obj.get("/Filter")
    except Exception:
        return []
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(f) for f in raw]
    return [str(raw)]


def _extension_of(image) -> str:
    """
    Extension implied by the encoding, taken from the name pypdf synthesises.

    Only the encoding is being described here. Unlike an Office package, where
    the media file's extension is part of a content-type contract, a PDF image
    is re-encoded when written back, so this does not constrain what the user
    may replace it with.
    """
    name = getattr(image, "name", "") or ""
    ext = os.path.splitext(name)[1].lower()
    return ext or ".png"


def extract(document: str, entry: str) -> bytes | None:
    """Decoded bytes of one image, in a format Pillow can open, or None."""
    if not PYPDF_AVAILABLE:
        return None
    try:
        reader = pypdf.PdfReader(document)
        for number, page in enumerate(reader.pages, 1):
            for index, image in enumerate(page.images, 1):
                if entry_for(number, index) == entry:
                    return image.data
    except Exception:
        return None
    return None


def extract_to_temp(document: str, entry: str) -> str | None:
    """
    Write one image to a temporary file and return its path.

    Mirrors `office.extract_to_temp`: the matcher and the perceptual hash both
    work on paths. The caller owns the file and must delete it.
    """
    data = extract(document, entry)
    if data is None:
        return None

    fd, path = tempfile.mkstemp(prefix=".proteus_pdf_", suffix=".png")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
    except OSError:
        os.remove(path)
        return None
    return path


def write_replacements(document: str, replacements: dict[str, str]) -> None:
    """
    Rewrite `document` with the given object numbers replaced.

    `replacements` maps an entry like `"p2i1"` to a
    `(source path, expected stream size)` pair. The size is what the scan saw;
    passing `None` skips the check.

    pypdf's own `ImageFile.replace()` does the swap: it re-encodes the picture,
    rewrites the stream and fixes `/Width`, `/Height`, `/ColorSpace`,
    `/BitsPerComponent` and `/Length` to match. Doing that by hand is where a
    home-made implementation goes wrong.

    The rebuilt document lands on a temporary file in the same folder and is
    promoted with `os.replace`, so an interrupted write cannot leave a
    half-written PDF behind — the same guarantee ordinary replacement gives.

    Raises on failure; the caller decides how to report it.
    """
    if not PYPDF_AVAILABLE:
        raise RuntimeError(t("PDF support needs the «pypdf» package, which is "
                             "not installed."))

    from PIL import Image

    folder = os.path.dirname(document) or "."
    fd, tmp_path = tempfile.mkstemp(prefix=".proteus_", dir=folder, suffix=".pdf")
    os.close(fd)

    try:
        writer = pypdf.PdfWriter(clone_from=document)

        remaining = dict(replacements)
        for number, page in enumerate(writer.pages, 1):
            for index, image in enumerate(page.images, 1):
                entry = entry_for(number, index)
                if entry not in remaining:
                    continue
                source, expected = remaining.pop(entry)
                if expected is not None and len(image.data) != expected:
                    # The document changed between the scan and now, so this
                    # position no longer holds the picture that was reviewed.
                    # Refuse rather than overwrite something unexamined.
                    raise ValueError(
                        t("Image {entry} has changed since the scan; nothing "
                          "was written.").format(entry=entry))
                with Image.open(source) as replacement:
                    # The stored image is re-encoded from pixels, so the source
                    # may be any raster format Pillow reads.
                    image.replace(replacement.convert("RGB"))

        if remaining:
            raise KeyError(t("Image {entry} is no longer in the document.")
                           .format(entry=", ".join(sorted(remaining))))

        with open(tmp_path, "wb") as handle:
            writer.write(handle)

        os.replace(tmp_path, document)
        tmp_path = None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
