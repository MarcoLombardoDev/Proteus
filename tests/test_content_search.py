#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Tests for perceptual hashing and content-based search.

This is the feature that lets Proteus find a logo that is not called "logo".
Because a hit here leads to a file being overwritten, the tests care as much
about what must *not* match as about what must.
"""

from __future__ import annotations

import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core  # noqa: E402

pytest.importorskip("PIL", reason="Pillow is needed to build test images")
from PIL import Image, ImageDraw  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers: a recognisable "logo" and an unrelated picture
# ---------------------------------------------------------------------------

def logo_image(size=(240, 80), colour=(196, 62, 58)):
    """A shape with enough internal structure to produce a stable hash."""
    image = Image.new("RGB", size, (255, 255, 255))
    draw = ImageDraw.Draw(image)
    w, h = size
    draw.ellipse((w * 0.04, h * 0.15, w * 0.32, h * 0.85), fill=colour)
    draw.rectangle((w * 0.38, h * 0.30, w * 0.94, h * 0.48), fill=colour)
    draw.rectangle((w * 0.38, h * 0.56, w * 0.72, h * 0.72), fill=(90, 90, 90))
    return image


def other_image(size=(240, 80)):
    """A visually different image: horizontal bands instead of a mark."""
    image = Image.new("RGB", size, (255, 255, 255))
    draw = ImageDraw.Draw(image)
    w, h = size
    for index in range(6):
        top = h * index / 6
        shade = 20 + index * 35
        draw.rectangle((0, top, w, top + h / 6), fill=(shade, shade, shade))
    return image


def save(image, path, **kwargs):
    path = str(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    image.save(path, **kwargs)
    return path


# ---------------------------------------------------------------------------
# Hashing basics
# ---------------------------------------------------------------------------

def test_hash_is_stable_for_the_same_file(tmp_path):
    path = save(logo_image(), tmp_path / "a.png")
    assert core.perceptual_hash(path) == core.perceptual_hash(path)


def test_hash_is_a_64_bit_value(tmp_path):
    path = save(logo_image(), tmp_path / "a.png")
    assert 0 <= core.perceptual_hash(path) < 2 ** (core.HASH_SIDE ** 2)


def test_unreadable_and_vector_files_have_no_hash(tmp_path):
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"not an image")
    assert core.perceptual_hash(str(broken)) is None

    svg = tmp_path / "logo.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"/>')
    assert core.perceptual_hash(str(svg)) is None


def test_identical_hashes_are_fully_similar(tmp_path):
    path = save(logo_image(), tmp_path / "a.png")
    digest = core.perceptual_hash(path)
    assert core.hash_distance(digest, digest) == 0
    assert core.hash_similarity(digest, digest) == 1.0


def test_similarity_of_a_missing_hash_is_zero():
    assert core.hash_similarity(None, 123) == 0.0
    assert core.hash_similarity(123, None) == 0.0


# ---------------------------------------------------------------------------
# What must match: the same logo, mangled the way real files are
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("size", [(120, 40), (480, 160), (60, 20), (960, 320)])
def test_the_same_logo_matches_across_sizes(tmp_path, size):
    """The same mark exported at four scales must still read as itself."""
    reference = save(logo_image(), tmp_path / "ref.png")
    rescaled = save(logo_image(size), tmp_path / f"copy_{size[0]}.png")

    score = core.hash_similarity(core.perceptual_hash(reference),
                                 core.perceptual_hash(rescaled))
    assert score >= core.DEFAULT_SIMILARITY, f"{size} scored only {score:.2f}"


def test_the_same_logo_matches_across_formats(tmp_path):
    reference = save(logo_image(), tmp_path / "ref.png")
    as_jpeg = save(logo_image(), tmp_path / "copy.jpg", quality=88)
    as_bmp = save(logo_image(), tmp_path / "copy.bmp")

    for candidate in (as_jpeg, as_bmp):
        score = core.hash_similarity(core.perceptual_hash(reference),
                                     core.perceptual_hash(candidate))
        assert score >= core.DEFAULT_SIMILARITY, f"{candidate} scored {score:.2f}"


def test_jpeg_recompression_does_not_break_the_match(tmp_path):
    reference = save(logo_image(), tmp_path / "ref.png")
    degraded = save(logo_image(), tmp_path / "low.jpg", quality=35)

    score = core.hash_similarity(core.perceptual_hash(reference),
                                 core.perceptual_hash(degraded))
    assert score >= core.DEFAULT_SIMILARITY


def test_transparency_is_flattened_before_hashing(tmp_path):
    """
    The same logo with and without an alpha channel must hash the same.

    Without compositing onto a fixed matte, transparent pixels decode as black
    and the two files look nothing alike — which is exactly the duplicate a
    rebranding needs to catch.
    """
    flat = logo_image()
    transparent = flat.convert("RGBA")
    transparent.putalpha(Image.new("L", transparent.size, 255))
    # Punch a transparent hole in the white background.
    pixels = transparent.load()
    for x in range(transparent.width):
        for y in range(4):
            pixels[x, y] = (0, 0, 0, 0)

    a = save(flat, tmp_path / "flat.png")
    b = save(transparent, tmp_path / "alpha.png")

    score = core.hash_similarity(core.perceptual_hash(a), core.perceptual_hash(b))
    assert score >= core.DEFAULT_SIMILARITY, f"alpha handling scored {score:.2f}"


# ---------------------------------------------------------------------------
# What must NOT match: this tool overwrites files
# ---------------------------------------------------------------------------

def test_an_unrelated_image_does_not_reach_the_threshold(tmp_path):
    reference = save(logo_image(), tmp_path / "ref.png")
    unrelated = save(other_image(), tmp_path / "unrelated.png")

    score = core.hash_similarity(core.perceptual_hash(reference),
                                 core.perceptual_hash(unrelated))
    assert score < core.DEFAULT_SIMILARITY, (
        f"an unrelated image scored {score:.2f}; at that rate content search "
        "would overwrite innocent files"
    )


def test_a_blank_image_does_not_match_a_logo(tmp_path):
    reference = save(logo_image(), tmp_path / "ref.png")
    blank = save(Image.new("RGB", (240, 80), (255, 255, 255)), tmp_path / "blank.png")

    score = core.hash_similarity(core.perceptual_hash(reference),
                                 core.perceptual_hash(blank))
    assert score < core.DEFAULT_SIMILARITY


# ---------------------------------------------------------------------------
# Content scan
# ---------------------------------------------------------------------------

def _tree(tmp_path):
    """A folder where the logo hides under names no pattern would guess."""
    scan = tmp_path / "share"
    save(logo_image((240, 80)), scan / "web" / "header_bg.png")      # hidden
    save(logo_image((120, 40)), scan / "docs" / "img_04.jpg")        # hidden
    save(logo_image((480, 160)), scan / "old" / "PROGETTO2014.bmp")  # hidden
    save(other_image(), scan / "web" / "banner_photo.png")           # unrelated
    save(other_image((100, 100)), scan / "docs" / "chart.png")       # unrelated
    reference = save(logo_image(), tmp_path / "ref" / "old_logo.png")
    return str(scan), reference


def test_content_scan_finds_logos_no_pattern_would_catch(tmp_path):
    scan, reference = _tree(tmp_path)

    hits = core.scan_by_content(scan, [reference])
    found = sorted(os.path.basename(p) for p, _ in hits)

    assert found == ["PROGETTO2014.bmp", "header_bg.png", "img_04.jpg"]
    # And a name-based scan finds none of them, which is the whole point.
    assert core.scan_files(scan, "logo*") == []


def test_content_scan_reports_similarity_sorted_by_confidence(tmp_path):
    scan, reference = _tree(tmp_path)
    hits = core.scan_by_content(scan, [reference])

    scores = [score for _, score in hits]
    assert scores == sorted(scores, reverse=True)
    assert all(score >= core.DEFAULT_SIMILARITY for score in scores)


def test_content_scan_excludes_the_reference_itself(tmp_path):
    """A reference inside the scanned tree must not be replaced by itself."""
    scan = tmp_path / "share"
    save(logo_image(), scan / "web" / "header_bg.png")
    reference = save(logo_image(), scan / "brand" / "old_logo.png")

    hits = core.scan_by_content(str(scan), [reference])
    paths = [p for p, _ in hits]
    assert reference not in paths
    assert len(paths) == 1


def test_content_scan_honours_the_pattern_prefilter(tmp_path):
    scan, reference = _tree(tmp_path)
    hits = core.scan_by_content(scan, [reference], pattern="*.jpg")
    assert [os.path.basename(p) for p, _ in hits] == ["img_04.jpg"]


def test_content_scan_honours_the_threshold(tmp_path):
    scan, reference = _tree(tmp_path)
    assert core.scan_by_content(scan, [reference], threshold=1.01) == []


def test_content_scan_skips_backups_and_vector_files(tmp_path):
    scan = tmp_path / "share"
    original = save(logo_image(), scan / "header_bg.png")
    # Written as raw bytes: PIL cannot infer a format from a ".bak" suffix.
    (scan / "header_bg.png.bak").write_bytes(open(original, "rb").read())
    (scan / "logo.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
    reference = save(logo_image(), tmp_path / "ref.png")

    hits = core.scan_by_content(str(scan), [reference])
    assert [os.path.basename(p) for p, _ in hits] == ["header_bg.png"]


def test_content_scan_excludes_the_source_folder(tmp_path):
    scan = tmp_path / "share"
    source = scan / "new_logos"
    save(logo_image(), scan / "site" / "header_bg.png")
    save(logo_image(), source / "brand.png")
    reference = save(logo_image(), tmp_path / "ref.png")

    hits = core.scan_by_content(str(scan), [reference], exclude_dirs=[str(source)])
    assert [os.path.basename(p) for p, _ in hits] == ["header_bg.png"]


def test_content_scan_reports_progress_and_can_be_cancelled(tmp_path):
    scan, reference = _tree(tmp_path)

    seen: list[tuple[int, int]] = []
    core.scan_by_content(scan, [reference], progress=lambda d, t: seen.append((d, t)))
    assert seen and seen[-1][0] == seen[-1][1]

    event = threading.Event()
    event.set()
    with pytest.raises(core.OperationCancelled):
        core.scan_by_content(scan, [reference], cancel_event=event)


def test_content_scan_without_usable_references_finds_nothing(tmp_path):
    scan, _ = _tree(tmp_path)
    svg = tmp_path / "ref.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
    assert core.scan_by_content(scan, [str(svg)]) == []


def test_multiple_references_widen_the_search(tmp_path):
    """Two different old marks can be retired in a single pass."""
    scan = tmp_path / "share"
    save(logo_image(), scan / "one.png")
    save(other_image(), scan / "two.png")

    logo_ref = save(logo_image(), tmp_path / "ref_logo.png")
    other_ref = save(other_image(), tmp_path / "ref_other.png")

    assert len(core.scan_by_content(str(scan), [logo_ref])) == 1
    assert len(core.scan_by_content(str(scan), [logo_ref, other_ref])) == 2


# ---------------------------------------------------------------------------
# Caching and reporting
# ---------------------------------------------------------------------------

def test_hash_cache_reads_each_file_once(tmp_path, monkeypatch):
    path = save(logo_image(), tmp_path / "a.png")
    calls = []
    real = core.perceptual_hash
    monkeypatch.setattr(core, "perceptual_hash",
                        lambda p: (calls.append(p), real(p))[1])

    cache = core.HashCache()
    for _ in range(5):
        cache.get(path)
    assert len(calls) == 1


def test_file_info_carries_and_formats_similarity(tmp_path):
    path = save(logo_image(), tmp_path / "a.png")

    by_name = core.FileInfo.from_path(path)
    assert by_name.similarity is None
    assert by_name.similarity_str == "—"
    assert by_name.needs_review is False

    confident = core.FileInfo.from_path(path, similarity=0.98)
    assert confident.similarity_str == "98%"
    assert confident.needs_review is False

    uncertain = core.FileInfo.from_path(path, similarity=0.91)
    assert uncertain.similarity_str == "91%"
    assert uncertain.needs_review is True, (
        "a content hit below the confident threshold must be flagged: it is "
        "the one case where the tool could overwrite an unrelated image"
    )


def test_validate_references_rejects_empty_and_unusable(tmp_path):
    assert core.validate_references([]) != []

    svg = tmp_path / "ref.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
    problems = core.validate_references([str(svg)])
    assert problems and "cannot be" in problems[0].lower()

    usable = save(logo_image(), tmp_path / "ref.png")
    assert core.validate_references([usable]) == []
