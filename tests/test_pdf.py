#!/usr/bin/env python
# Proteus — Rebranding Tool
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.
# A commercial licence, without the AGPL's obligations, is available for use
# in proprietary or closed-source products — see COMMERCIAL-LICENSE.md.

"""
Tests for PDF support.

Two things are being checked, and the second matters more than the first. One:
that a raster logo inside a PDF really is found, compared and replaced. Two:
that everything Proteus *cannot* do to a PDF is reported rather than skipped —
a vector logo, an encrypted or signed file, an unreadable image. A rebranding
that quietly leaves logos behind is the failure mode this feature was designed
against, so most of what follows is about the reporting.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core  # noqa: E402
import pdf  # noqa: E402

pytest.importorskip("PIL", reason="Pillow is needed to build test images")
pypdf = pytest.importorskip("pypdf", reason="pypdf is needed for PDF support")

from PIL import Image, ImageDraw  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def mark(path, size=(240, 80), colour=(196, 62, 58), shape="logo"):
    """A logo-like mark. Flat colour has no gradient for dHash to encode."""
    path = str(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    image = Image.new("RGB", size, (255, 255, 255))
    draw = ImageDraw.Draw(image)
    w, h = size
    if shape == "logo":
        draw.ellipse((w * .04, h * .15, w * .32, h * .85), fill=colour)
        draw.rectangle((w * .38, h * .30, w * .94, h * .48), fill=colour)
        draw.rectangle((w * .38, h * .56, w * .72, h * .72), fill=(90, 90, 90))
    else:
        # A deliberately different silhouette, for the "must not match" case.
        draw.polygon([(w * .5, h * .1), (w * .9, h * .9), (w * .1, h * .9)],
                     fill=colour)
    image.save(path)
    return path


def pdf_with_images(path, *images):
    """A PDF holding one image per page, in order."""
    os.makedirs(os.path.dirname(str(path)) or ".", exist_ok=True)
    first, *rest = [Image.open(i).convert("RGB") for i in images]
    first.save(str(path), save_all=bool(rest), append_images=rest)
    return str(path)


def vector_pdf(path):
    """
    A valid PDF whose only artwork is drawn with path operators.

    This is what a print-quality logo actually looks like, and it is invisible
    to any approach based on image XObjects — which is why it has to be
    reported instead.
    """
    from pypdf.generic import DecodedStreamObject, NameObject

    os.makedirs(os.path.dirname(str(path)) or ".", exist_ok=True)
    writer = pypdf.PdfWriter()
    page = writer.add_blank_page(200, 100)
    content = DecodedStreamObject()
    content.set_data(b"0.77 0.24 0.23 rg 10 20 100 50 re f")
    page[NameObject("/Contents")] = writer._add_object(content)
    with open(str(path), "wb") as handle:
        writer.write(handle)
    return str(path)


@pytest.fixture
def brochure(tmp_path):
    """A two-page PDF, the same logo on each page."""
    logo = mark(tmp_path / "assets" / "old.png")
    return pdf_with_images(tmp_path / "brochure.pdf", logo, logo)


# ---------------------------------------------------------------------------
# Finding
# ---------------------------------------------------------------------------

def test_raster_images_are_found_one_per_page(brochure):
    images, problems = pdf.list_images(brochure)

    assert problems == []
    assert [i.entry for i in images] == ["p1i1", "p2i1"]
    assert [i.page for i in images] == [1, 2]
    assert all(i.size > 0 for i in images)
    assert images[0].name.endswith("brochure.pdf!/p1i1")
    assert images[0].key == f"{brochure}!/p1i1"


def test_the_entry_survives_the_writer_renumbering_objects(brochure):
    """
    Regression, and the reason entries are positional.

    `PdfWriter(clone_from=...)` renumbers objects: an image read as object 1
    comes back as object 4. Keying on the object number meant the write step
    could not find the picture the scan had reviewed.
    """
    reader_numbers = {
        image.indirect_reference.idnum
        for page in pypdf.PdfReader(brochure).pages for image in page.images
    }
    writer_numbers = {
        image.indirect_reference.idnum
        for page in pypdf.PdfWriter(clone_from=brochure).pages
        for image in page.images
    }
    assert reader_numbers != writer_numbers, "the premise of this test is gone"

    # The positional entry is unaffected, and still resolves.
    images, _ = pdf.list_images(brochure)
    assert pdf.extract(brochure, images[1].entry) is not None


def test_an_extracted_image_can_be_matched_by_content(brochure, tmp_path):
    """The existing perceptual hash works on PDF images with no changes."""
    reference = mark(tmp_path / "ref" / "old.png")
    images, _ = pdf.list_images(brochure)

    temp = pdf.extract_to_temp(brochure, images[0].entry)
    assert temp is not None
    try:
        similarity = core.hash_similarity(core.perceptual_hash(temp),
                                          core.perceptual_hash(reference))
    finally:
        os.remove(temp)

    # Not 100%: the PDF stores it JPEG-compressed, which perturbs the gradients.
    assert similarity > 0.90, f"expected a strong match, got {similarity:.0%}"


def test_a_different_shape_does_not_match(brochure, tmp_path):
    other = mark(tmp_path / "ref" / "triangle.png", shape="triangle")
    images, _ = pdf.list_images(brochure)

    temp = pdf.extract_to_temp(brochure, images[0].entry)
    try:
        similarity = core.hash_similarity(core.perceptual_hash(temp),
                                          core.perceptual_hash(other))
    finally:
        os.remove(temp)
    assert similarity < core.DEFAULT_SIMILARITY


# ---------------------------------------------------------------------------
# Replacing
# ---------------------------------------------------------------------------

def _pixels(path):
    """Sample colour of each image in the PDF, page by page."""
    return [image.image.convert("RGB").getpixel((60, 40))
            for page in pypdf.PdfReader(path).pages for image in page.images]


def test_only_the_targeted_image_is_replaced(brochure, tmp_path):
    new = mark(tmp_path / "new" / "logo.png", colour=(20, 90, 170))
    images, _ = pdf.list_images(brochure)

    pdf.write_replacements(brochure, {images[1].entry: (new, images[1].size)})

    page1, page2 = _pixels(brochure)
    assert page1[0] > page1[2], "page 1 should still be the red logo"
    assert page2[2] > page2[0], "page 2 should now be the blue logo"


def test_the_document_still_opens_in_an_independent_parser(brochure, tmp_path):
    """A rewritten PDF nobody can open would be worse than no feature."""
    new = mark(tmp_path / "new" / "logo.png", colour=(20, 90, 170))
    images, _ = pdf.list_images(brochure)
    pdf.write_replacements(brochure, {images[0].entry: (new, images[0].size)})

    reader = pypdf.PdfReader(brochure)
    assert len(reader.pages) == 2
    assert len(list(reader.pages[0].images)) == 1


def test_a_png_may_replace_a_jpeg_encoded_picture(brochure, tmp_path):
    """
    Inside a PDF the stored encoding is not a format contract.

    The picture is re-encoded from pixels on write, so insisting on the stored
    encoding would reject a PNG for a JPEG-compressed logo — which is the normal
    case, because brand assets arrive as PNG.
    """
    images, _ = pdf.list_images(brochure)
    assert images[0].ext == ".jpg", "expected Pillow to store it as DCTDecode"

    target = core.FileInfo.from_pdf_image(images[0])
    assert target.reencoded is True

    png = core.FileInfo.from_path(mark(tmp_path / "new" / "logo.png"))
    source, score = core.find_best_match(target, [png])
    assert source is png and score < float("inf")


def test_a_vector_source_is_never_offered_for_a_pdf_image(tmp_path, brochure):
    """An SVG cannot be re-encoded into a PDF image stream."""
    images, _ = pdf.list_images(brochure)
    target = core.FileInfo.from_pdf_image(images[0])

    svg = tmp_path / "new" / "logo.svg"
    os.makedirs(svg.parent, exist_ok=True)
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" '
                   'width="240px" height="80px"/>', encoding="utf-8")

    source, _ = core.find_best_match(target, [core.FileInfo.from_path(str(svg))])
    assert source is None


def test_a_stale_entry_refuses_to_write(brochure, tmp_path):
    """
    The position was reviewed with a particular picture in it. If the document
    changed since, writing would overwrite something nobody looked at.
    """
    new = mark(tmp_path / "new" / "logo.png", colour=(20, 90, 170))
    images, _ = pdf.list_images(brochure)
    before = open(brochure, "rb").read()

    with pytest.raises(ValueError):
        pdf.write_replacements(brochure, {images[0].entry: (new, 999_999)})

    assert open(brochure, "rb").read() == before, "the file must be untouched"


def test_a_whole_campaign_backs_the_pdf_up_once(brochure, tmp_path):
    """
    Two pictures, one document: one rewrite and one backup.

    Replacing them one at a time would leave a backup of an already-modified
    state and never a clean copy of the original.
    """
    new = mark(tmp_path / "new" / "logo.png", colour=(20, 90, 170))
    targets = [core.FileInfo.from_pdf_image(i) for i in pdf.list_images(brochure)[0]]
    source = core.FileInfo.from_path(new)
    matches = [core.Match(target=target, source=source, enabled=True)
               for target in targets]

    report = core.replace_all(matches, backup=True, dry_run=False)

    assert report.errors == 0
    assert report.total == 1, "the two pictures must be one outcome, not two"
    backups = [f for f in os.listdir(tmp_path) if f.endswith(".bak")]
    assert len(backups) == 1
    assert all(px[2] > px[0] for px in _pixels(brochure)), "both pages replaced"


def test_a_dry_run_writes_nothing(brochure, tmp_path):
    new = mark(tmp_path / "new" / "logo.png", colour=(20, 90, 170))
    before = open(brochure, "rb").read()
    images, _ = pdf.list_images(brochure)
    target = core.FileInfo.from_pdf_image(images[0])

    report = core.replace_all(
        [core.Match(target=target, source=core.FileInfo.from_path(new), enabled=True)],
        backup=True, dry_run=True)

    assert report.ok == 1
    assert open(brochure, "rb").read() == before
    assert not [f for f in os.listdir(tmp_path) if f.endswith(".bak")]


# ---------------------------------------------------------------------------
# Reporting what cannot be done — the rule this feature exists to honour
# ---------------------------------------------------------------------------

def test_a_vector_logo_is_reported_when_the_file_was_asked_for(tmp_path):
    document = vector_pdf(tmp_path / "flyer.pdf")

    images, problems = pdf.list_images(document, report_empty=True)

    assert images == []
    assert len(problems) == 1
    assert "vector" in problems[0].reason.lower()
    assert problems[0].hint, "a problem without a remedy is only half reported"


def test_a_vector_pdf_is_silent_during_a_whole_tree_search(tmp_path):
    """
    The other half of the rule: reporting must stay worth reading.

    During a content search across a tree, every unrelated PDF would otherwise
    produce a finding, and a warning list nobody can read is as good as none.
    """
    document = vector_pdf(tmp_path / "flyer.pdf")
    images, problems = pdf.list_images(document, report_empty=False)
    assert (images, problems) == ([], [])


def test_an_encrypted_pdf_is_reported_not_skipped(tmp_path, brochure):
    writer = pypdf.PdfWriter(clone_from=brochure)
    writer.encrypt("secret")
    locked = str(tmp_path / "locked.pdf")
    with open(locked, "wb") as handle:
        writer.write(handle)

    problems = pdf.inspect(locked)
    assert any("encrypted" in p.reason.lower() for p in problems)
    assert all(p.hint for p in problems)

    images, reported = pdf.list_images(locked)
    assert images == [] and reported, "silently returning nothing is the bug"


def test_a_damaged_pdf_is_reported(tmp_path):
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"%PDF-1.4\nthis is not a PDF at all\n")

    images, problems = pdf.list_images(str(broken))
    assert images == []
    assert problems and all(p.hint for p in problems)


def test_a_missing_pypdf_is_reported_rather_than_crashing(monkeypatch, brochure):
    """
    pypdf is optional at runtime. Ticking the PDF box without it must explain
    itself, not raise.
    """
    monkeypatch.setattr(pdf, "PYPDF_AVAILABLE", False)

    problems = pdf.inspect(brochure)
    assert len(problems) == 1
    assert "pypdf" in problems[0].reason
    assert "pip install" in problems[0].hint

    images, reported = pdf.list_images(brochure)
    assert images == [] and reported

    with pytest.raises(RuntimeError):
        pdf.write_replacements(brochure, {"p1i1": ("whatever.png", None)})


def test_a_signed_pdf_is_refused(tmp_path, brochure):
    """
    Any byte written into a signed PDF invalidates the signature, so it is
    reported instead of quietly broken.
    """
    from pypdf.generic import (ArrayObject, DictionaryObject, NameObject,
                               NumberObject)

    writer = pypdf.PdfWriter(clone_from=brochure)
    field = DictionaryObject({NameObject("/FT"): NameObject("/Sig")})
    writer._root_object[NameObject("/AcroForm")] = DictionaryObject({
        NameObject("/SigFlags"): NumberObject(3),
        NameObject("/Fields"): ArrayObject([writer._add_object(field)]),
    })
    signed = str(tmp_path / "signed.pdf")
    with open(signed, "wb") as handle:
        writer.write(handle)

    problems = pdf.inspect(signed)
    assert any("signed" in p.reason.lower() for p in problems)


def test_the_scan_passes_every_problem_to_the_caller(tmp_path):
    """
    End to end: a folder holding one usable PDF and one vector-only PDF yields
    the images from the first and a finding for the second.
    """
    logo = mark(tmp_path / "assets" / "old.png")
    pdf_with_images(tmp_path / "scan" / "brochure.pdf", logo)
    vector_pdf(tmp_path / "scan" / "flyer.pdf")

    seen: list = []
    found = core.scan_pdf_documents(str(tmp_path / "scan"),
                                    patterns=["*.pdf"],
                                    on_problem=seen.append)

    assert [f.name.split("!/")[1] for f in found] == ["p1i1"]
    assert len(seen) == 1
    assert seen[0].name == "flyer.pdf"


def test_backups_are_not_rescanned(tmp_path):
    """A `.pdf.bak` is a backup, not a target — as for every other format."""
    logo = mark(tmp_path / "assets" / "old.png")
    document = pdf_with_images(tmp_path / "scan" / "brochure.pdf", logo)
    import shutil
    shutil.copy2(document, document + ".bak")

    found = core.scan_pdf_documents(str(tmp_path / "scan"))
    assert {f.container for f in found} == {document}
