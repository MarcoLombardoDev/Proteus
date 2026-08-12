#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Tests for the application logic (core.py), with no GUI dependency."""

from __future__ import annotations

import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core  # noqa: E402

PIL = pytest.importorskip("PIL", reason="Pillow is needed to build test images")
from PIL import Image  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_image(path, size=(100, 50), fmt=None, color=(255, 0, 0)):
    path = str(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new("RGB", size, color).save(path, format=fmt)
    return path


def make_svg(path, width="120px", height="60px", viewbox=None):
    path = str(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    attrs = f'width="{width}" height="{height}"' if width else ""
    if viewbox:
        attrs += f' viewBox="{viewbox}"'
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f'<svg xmlns="http://www.w3.org/2000/svg" {attrs}><rect/></svg>')
    return path


# ---------------------------------------------------------------------------
# format_size
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    (0, "0.0 B"),
    (512, "512.0 B"),
    (1024, "1.0 KB"),
    (1536, "1.5 KB"),
    (1024 ** 2, "1.0 MB"),
    (1024 ** 3, "1.0 GB"),
    (1024 ** 4, "1.0 TB"),
])
def test_format_size(value, expected):
    assert core.format_size(value) == expected


# ---------------------------------------------------------------------------
# Pattern
# ---------------------------------------------------------------------------

def test_parse_patterns_splits_and_trims():
    assert core.parse_patterns("logo*.png; banner*.jpg , *.svg") == [
        "logo*.png", "banner*.jpg", "*.svg"]


def test_parse_patterns_empty():
    assert core.parse_patterns("") == []
    assert core.parse_patterns("  ;  ,  ") == []


def test_validate_pattern_rejects_empty_and_path_separators():
    assert core.validate_pattern("") is not None
    assert core.validate_pattern("sub/logo*.png") is not None
    assert core.validate_pattern("sub\\logo*.png") is not None


def test_validate_pattern_rejects_catch_all():
    assert core.validate_pattern("*") is not None
    assert core.validate_pattern("*.png") is None


def test_matches_patterns_is_case_insensitive():
    assert core.matches_patterns("LOGO_Header.PNG", ["logo*.png"])
    assert not core.matches_patterns("banner.png", ["logo*.png"])


# ---------------------------------------------------------------------------
# Equivalent extensions
# ---------------------------------------------------------------------------

def test_normalized_ext_groups_jpeg_and_tiff():
    assert core.normalized_ext("a.jpg") == core.normalized_ext("b.jpeg")
    assert core.normalized_ext("a.tif") == core.normalized_ext("b.tiff")
    assert core.normalized_ext(".PNG") == ".png"
    assert core.normalized_ext("a.png") != core.normalized_ext("a.gif")


# ---------------------------------------------------------------------------
# Image dimensions
# ---------------------------------------------------------------------------

def test_get_image_dimensions_png(tmp_path):
    path = make_image(tmp_path / "img" / "a.png", (320, 240))
    assert core.get_image_dimensions(path) == (320, 240)


def test_get_image_dimensions_unreadable(tmp_path):
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"not an image")
    assert core.get_image_dimensions(str(broken)) is None


def test_svg_dimensions_from_width_height(tmp_path):
    path = make_svg(tmp_path / "s" / "logo.svg", "120px", "60px")
    assert core.svg_dimensions(path) == (120, 60)


def test_svg_dimensions_from_viewbox(tmp_path):
    path = make_svg(tmp_path / "s" / "logo.svg", "", "", viewbox="0 0 200 100")
    assert core.svg_dimensions(path) == (200, 100)


def test_svg_dimensions_converts_units(tmp_path):
    path = make_svg(tmp_path / "s" / "logo.svg", "1in", "72pt")
    assert core.svg_dimensions(path) == (96, 96)


def test_svg_dimensions_invalid_file(tmp_path):
    path = tmp_path / "bad.svg"
    path.write_text("<svg unclosed")
    assert core.svg_dimensions(str(path)) is None


def test_get_image_dimensions_dispatches_svg(tmp_path):
    path = make_svg(tmp_path / "s" / "l.svg", "50px", "25px")
    assert core.get_image_dimensions(path) == (50, 25)


def test_get_image_dimensions_pdf_returns_none(tmp_path):
    path = tmp_path / "doc.pdf"
    path.write_bytes(b"%PDF-1.4")
    assert core.get_image_dimensions(str(path)) is None


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------

def test_scan_files_recursive_and_sorted(tmp_path):
    make_image(tmp_path / "a" / "logo_1.png")
    make_image(tmp_path / "b" / "c" / "logo_2.png")
    make_image(tmp_path / "b" / "other.png")

    found = core.scan_files(str(tmp_path), "logo*.png")
    assert [os.path.basename(f) for f in found] == ["logo_1.png", "logo_2.png"]
    assert found == sorted(found)


def test_scan_files_multiple_patterns(tmp_path):
    make_image(tmp_path / "x" / "logo.png")
    make_image(tmp_path / "x" / "banner.jpg", fmt="JPEG")
    found = core.scan_files(str(tmp_path), "logo*.png; banner*.jpg")
    assert len(found) == 2


def test_scan_files_skips_backups(tmp_path):
    make_image(tmp_path / "x" / "logo.png")
    (tmp_path / "x" / "logo.png.bak").write_bytes(b"old")
    found = core.scan_files(str(tmp_path), "logo*")
    assert [os.path.basename(f) for f in found] == ["logo.png"]


def test_scan_files_excludes_source_folder(tmp_path):
    """A nested source folder must not end up among the targets."""
    scan = tmp_path / "share"
    source = scan / "nuovi_loghi"
    make_image(scan / "sito" / "logo.png")
    make_image(source / "logo.png")

    found = core.scan_files(str(scan), "logo*.png", exclude_dirs=[str(source)])
    assert len(found) == 1
    assert "nuovi_loghi" not in found[0]


def test_scan_files_reports_cancel(tmp_path):
    make_image(tmp_path / "a" / "logo.png")
    event = threading.Event()
    event.set()
    with pytest.raises(core.OperationCancelled):
        core.scan_files(str(tmp_path), "logo*.png", cancel_event=event)


def test_collect_source_files_only_supported_formats(tmp_path):
    make_image(tmp_path / "s" / "a.png")
    (tmp_path / "s" / "notes.txt").write_text("x")
    found = core.collect_source_files(str(tmp_path))
    assert [os.path.basename(f) for f in found] == ["a.png"]


def test_is_within(tmp_path):
    inner = tmp_path / "a" / "b"
    inner.mkdir(parents=True)
    assert core.is_within(str(inner), str(tmp_path))
    assert not core.is_within(str(tmp_path), str(inner))


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def test_find_best_match_prefers_same_resolution(tmp_path):
    target = core.FileInfo.from_path(make_image(tmp_path / "t" / "logo.png", (200, 100)))
    close = core.FileInfo.from_path(make_image(tmp_path / "s" / "a.png", (200, 100)))
    far = core.FileInfo.from_path(make_image(tmp_path / "s" / "b.png", (1000, 900)))

    best, score = core.find_best_match(target, [far, close])
    assert best.path == close.path
    # Identical resolution: an excellent match even if the name differs.
    assert core.Match(target=target, source=best, score=score).quality == core.QUALITY_EXCELLENT


def test_find_best_match_requires_same_format(tmp_path):
    target = core.FileInfo.from_path(make_image(tmp_path / "t" / "logo.png", (100, 100)))
    gif = core.FileInfo.from_path(make_image(tmp_path / "s" / "a.gif", (100, 100), fmt="GIF"))
    best, _ = core.find_best_match(target, [gif])
    assert best is None


def test_find_best_match_treats_jpg_and_jpeg_as_equivalent(tmp_path):
    target = core.FileInfo.from_path(
        make_image(tmp_path / "t" / "logo.jpg", (100, 100), fmt="JPEG"))
    source = core.FileInfo.from_path(
        make_image(tmp_path / "s" / "logo_new.jpeg", (100, 100), fmt="JPEG"))
    best, _ = core.find_best_match(target, [source])
    assert best is not None and best.path == source.path


def test_find_best_match_uses_name_as_tiebreak(tmp_path):
    """With equal resolutions, the most similar file name wins."""
    target = core.FileInfo.from_path(
        make_image(tmp_path / "t" / "logo_header.png", (100, 100)))
    unrelated = core.FileInfo.from_path(
        make_image(tmp_path / "s" / "zzz_qqq.png", (100, 100)))
    similar = core.FileInfo.from_path(
        make_image(tmp_path / "s" / "logo_header.png", (100, 100)))

    best, _ = core.find_best_match(target, [unrelated, similar])
    assert best.path == similar.path


def test_find_best_match_is_deterministic(tmp_path):
    """Equivalent candidates must always yield the same result."""
    target = core.FileInfo.from_path(make_image(tmp_path / "t" / "logo.png", (100, 100)))
    sources = [
        core.FileInfo.from_path(make_image(tmp_path / "s" / f"x{i}.png", (100, 100)))
        for i in range(5)
    ]
    first, _ = core.find_best_match(target, sources)
    second, _ = core.find_best_match(target, list(reversed(sources)))
    assert first.path == second.path


def test_build_matches_reports_progress(tmp_path):
    targets = [core.FileInfo.from_path(make_image(tmp_path / "t" / f"logo{i}.png"))
               for i in range(3)]
    sources = [core.FileInfo.from_path(make_image(tmp_path / "s" / "logo.png"))]

    seen = []
    matches = core.build_matches(targets, sources, progress=lambda d, t: seen.append((d, t)))
    assert len(matches) == 3
    assert seen == [(1, 3), (2, 3), (3, 3)]
    assert all(m.enabled for m in matches)


def test_match_quality_reflects_resolution_gap(tmp_path):
    """The grade depends on the resolution gap, not on the file name."""
    target = core.FileInfo.from_path(make_image(tmp_path / "t" / "logo.png", (100, 100)))
    identical = core.FileInfo.from_path(make_image(tmp_path / "s" / "zzz.png", (100, 100)))
    close = core.FileInfo.from_path(make_image(tmp_path / "s" / "b.png", (120, 125)))
    far = core.FileInfo.from_path(make_image(tmp_path / "s" / "c.png", (900, 700)))

    assert core.Match(target=target, source=identical).quality == core.QUALITY_EXCELLENT
    assert core.Match(target=target, source=close).quality == core.QUALITY_GOOD_LABEL
    assert core.Match(target=target, source=far).quality == core.QUALITY_WEAK
    assert core.Match(target=target, source=None).quality == core.QUALITY_NONE
    assert core.Match(target=target, source=far, manual=True).quality == core.QUALITY_MANUAL


def test_match_quality_falls_back_to_name_without_dimensions(tmp_path):
    """For formats whose resolution cannot be read (PDF/EPS), the name decides."""
    pdf_target = tmp_path / "t" / "logo_brand.pdf"
    pdf_target.parent.mkdir(parents=True)
    pdf_target.write_bytes(b"%PDF-1.4")
    same_name = tmp_path / "s" / "logo_brand.pdf"
    same_name.parent.mkdir(parents=True)
    same_name.write_bytes(b"%PDF-1.4")
    other_name = tmp_path / "s" / "documento_generico.pdf"
    other_name.write_bytes(b"%PDF-1.4")

    target = core.FileInfo.from_path(str(pdf_target))
    assert target.dim is None

    assert core.Match(target=target,
                      source=core.FileInfo.from_path(str(same_name))).quality == core.QUALITY_GOOD_LABEL
    assert core.Match(target=target,
                      source=core.FileInfo.from_path(str(other_name))).quality == core.QUALITY_WEAK


def test_dimension_distance_is_relative_to_target_size():
    """A 20 px gap matters on an icon but not on a banner."""
    icon = core.dimension_distance((32, 32), (52, 32))
    banner = core.dimension_distance((1920, 1080), (1940, 1080))
    assert icon > banner
    assert core.dimension_distance((100, 100), (100, 100)) == 0.0
    assert core.dimension_distance((100, 100), None) == 1.0


def test_dimension_cache_reads_each_file_once(tmp_path, monkeypatch):
    path = make_image(tmp_path / "s" / "a.png", (10, 10))
    calls = []
    real = core.get_image_dimensions

    def counting(p):
        calls.append(p)
        return real(p)

    monkeypatch.setattr(core, "get_image_dimensions", counting)
    cache = core.DimensionCache()
    for _ in range(5):
        assert cache.get(path) == (10, 10)
    assert len(calls) == 1


# ---------------------------------------------------------------------------
# Replacement
# ---------------------------------------------------------------------------

def test_replace_file_copies_content(tmp_path):
    target = make_image(tmp_path / "t" / "logo.png", (10, 10), color=(255, 0, 0))
    source = make_image(tmp_path / "s" / "logo.png", (20, 20), color=(0, 255, 0))

    outcome = core.replace_file(target, source, backup=False)
    assert outcome.ok
    assert core.get_image_dimensions(target) == (20, 20)


def test_replace_file_creates_backup(tmp_path):
    target = make_image(tmp_path / "t" / "logo.png", (10, 10))
    source = make_image(tmp_path / "s" / "logo.png", (20, 20))

    outcome = core.replace_file(target, source, backup=True)
    assert outcome.ok
    assert outcome.backup == target + ".bak"
    assert core.get_image_dimensions(outcome.backup) == (10, 10)


def test_second_run_does_not_overwrite_existing_backup(tmp_path):
    """The first campaign's .bak must survive the second one."""
    target = make_image(tmp_path / "t" / "logo.png", (10, 10))
    first_source = make_image(tmp_path / "s" / "v1.png", (20, 20))
    second_source = make_image(tmp_path / "s" / "v2.png", (30, 30))

    first = core.replace_file(target, first_source, backup=True)
    second = core.replace_file(target, second_source, backup=True)

    assert first.backup != second.backup
    assert core.get_image_dimensions(first.backup) == (10, 10)   # original intact
    assert core.get_image_dimensions(second.backup) == (20, 20)
    assert core.get_image_dimensions(target) == (30, 30)


def test_replace_file_skips_same_file(tmp_path):
    path = make_image(tmp_path / "t" / "logo.png", (10, 10))
    outcome = core.replace_file(path, path, backup=True)
    assert outcome.status == "skipped"
    assert not os.path.exists(path + ".bak")


def test_replace_file_missing_source(tmp_path):
    target = make_image(tmp_path / "t" / "logo.png")
    outcome = core.replace_file(target, str(tmp_path / "nope.png"))
    assert outcome.status == "error"
    assert "source" in outcome.message.lower()


def test_replace_file_missing_target(tmp_path):
    source = make_image(tmp_path / "s" / "logo.png")
    outcome = core.replace_file(str(tmp_path / "nope.png"), source)
    assert outcome.status == "error"


def test_replace_file_dry_run_changes_nothing(tmp_path):
    target = make_image(tmp_path / "t" / "logo.png", (10, 10))
    source = make_image(tmp_path / "s" / "logo.png", (20, 20))

    outcome = core.replace_file(target, source, backup=True, dry_run=True)
    assert outcome.ok
    assert core.get_image_dimensions(target) == (10, 10)
    assert not os.path.exists(target + ".bak")


def test_replace_file_leaves_target_intact_on_copy_failure(tmp_path, monkeypatch):
    """A copy that fails halfway must not truncate the original file."""
    target = make_image(tmp_path / "t" / "logo.png", (10, 10))
    source = make_image(tmp_path / "s" / "logo.png", (20, 20))
    original = open(target, "rb").read()

    real_copy = core.shutil.copy2

    def failing_copy(src, dst, *args, **kwargs):
        if os.path.basename(str(src)) == "logo.png" and ".rebranding_" in str(dst):
            raise OSError("disco pieno")
        return real_copy(src, dst, *args, **kwargs)

    monkeypatch.setattr(core.shutil, "copy2", failing_copy)
    outcome = core.replace_file(target, source, backup=False)

    assert outcome.status == "error"
    assert open(target, "rb").read() == original
    leftovers = [f for f in os.listdir(os.path.dirname(target))
                 if f.startswith(".rebranding_")]
    assert leftovers == []


def test_replace_all_counts_and_cancels(tmp_path):
    matches = []
    for i in range(3):
        target = core.FileInfo.from_path(make_image(tmp_path / "t" / f"logo{i}.png", (10, 10)))
        source = core.FileInfo.from_path(make_image(tmp_path / "s" / f"new{i}.png", (20, 20)))
        matches.append(core.Match(target=target, source=source, enabled=True))

    report = core.replace_all(matches, backup=False)
    assert (report.ok, report.errors, report.total) == (3, 0, 3)

    event = threading.Event()
    event.set()
    cancelled = core.replace_all(matches, backup=False, cancel_event=event)
    assert cancelled.cancelled and cancelled.total == 0


def test_replace_all_skips_matches_without_source(tmp_path):
    target = core.FileInfo.from_path(make_image(tmp_path / "t" / "logo.png"))
    report = core.replace_all([core.Match(target=target, source=None, enabled=True)])
    assert report.skipped == 1


# ---------------------------------------------------------------------------
# Backup and restore
# ---------------------------------------------------------------------------

def test_backup_origin_plain_and_timestamped():
    assert core.backup_origin("/x/logo.png.bak") == "/x/logo.png"
    assert core.backup_origin("/x/logo.png.20260806-101500.bak") == "/x/logo.png"
    assert core.backup_origin("/x/logo.png.20260806-101500-2.bak") == "/x/logo.png"


def test_find_backups_and_restore(tmp_path):
    target = make_image(tmp_path / "t" / "logo.png", (10, 10))
    source = make_image(tmp_path / "s" / "logo.png", (20, 20))
    core.replace_file(target, source, backup=True)
    assert core.get_image_dimensions(target) == (20, 20)

    assert len(core.find_backups(str(tmp_path))) == 1

    report = core.restore_backups(str(tmp_path / "t"))
    assert report.ok == 1
    assert core.get_image_dimensions(target) == (10, 10)
    assert os.path.exists(target + ".bak")


def test_restore_uses_oldest_backup(tmp_path):
    """After two rebranding campaigns we return to the original, not the interim one."""
    target = make_image(tmp_path / "t" / "logo.png", (10, 10))
    core.replace_file(target, make_image(tmp_path / "s" / "v1.png", (20, 20)), backup=True)
    core.replace_file(target, make_image(tmp_path / "s" / "v2.png", (30, 30)), backup=True)

    core.restore_backups(str(tmp_path / "t"))
    assert core.get_image_dimensions(target) == (10, 10)


def test_restore_can_remove_backups(tmp_path):
    target = make_image(tmp_path / "t" / "logo.png", (10, 10))
    core.replace_file(target, make_image(tmp_path / "s" / "v1.png", (20, 20)), backup=True)

    core.restore_backups(str(tmp_path / "t"), remove_backup=True)
    assert core.find_backups(str(tmp_path / "t")) == []


# ---------------------------------------------------------------------------
# Export CSV
# ---------------------------------------------------------------------------

def test_export_matches_csv(tmp_path):
    target = core.FileInfo.from_path(make_image(tmp_path / "t" / "logo.png", (10, 10)))
    source = core.FileInfo.from_path(make_image(tmp_path / "s" / "new.png", (10, 10)))
    matches = [core.Match(target=target, source=source, score=0.01, enabled=True),
               core.Match(target=target, source=None)]

    destination = str(tmp_path / "out.csv")
    core.export_matches_csv(matches, destination)

    content = open(destination, encoding="utf-8-sig").read()
    assert "File to Replace" in content
    assert "YES" in content and "NO" in content
    assert content.count("\n") >= 3


def test_export_report_csv(tmp_path):
    report = core.ReplaceReport(outcomes=[
        core.ReplaceOutcome("/a/logo.png", "/s/new.png", "ok", "", "/a/logo.png.bak"),
        core.ReplaceOutcome("/a/b.png", "/s/x.png", "error", "permission denied"),
    ])
    destination = str(tmp_path / "report.csv")
    core.export_report_csv(report, destination)
    content = open(destination, encoding="utf-8-sig").read()
    assert "OK" in content and "ERROR" in content and "permission denied" in content


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def test_settings_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "writable_app_dir", lambda sub: str(tmp_path))
    assert core.save_settings({"search_pattern": "banner*.jpg", "backup": False,
                               "ignored": "x"})
    loaded = core.load_settings()
    assert loaded["search_pattern"] == "banner*.jpg"
    assert loaded["backup"] is False
    assert "ignored" not in loaded
    assert loaded["source_folder"] == ""      # default preserved


def test_load_settings_survives_corrupted_file(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "writable_app_dir", lambda sub: str(tmp_path))
    (tmp_path / core.SETTINGS_FILE).write_text("{ not json")
    assert core.load_settings() == core.DEFAULT_SETTINGS


def test_writable_app_dir_falls_back(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "get_base_path", lambda: "/proc/definitely/not/writable")
    monkeypatch.setattr(core, "user_data_dir", lambda: str(tmp_path / "userdata"))
    result = core.writable_app_dir("logs")
    assert result.startswith(str(tmp_path))
    assert os.path.isdir(result)


# ---------------------------------------------------------------------------
# Configuration validation
# ---------------------------------------------------------------------------

def test_validate_config_all_problems(tmp_path):
    problems = core.validate_config("", "", "")
    assert len(problems) == 3


def test_validate_config_ok(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "scan").mkdir()
    assert core.validate_config(str(tmp_path / "src"), str(tmp_path / "scan"),
                                "logo*.png") == []


def test_validate_config_rejects_identical_folders(tmp_path):
    problems = core.validate_config(str(tmp_path), str(tmp_path), "logo*.png")
    assert any("same" in p for p in problems)


def test_config_warnings_for_nested_source(tmp_path):
    source = tmp_path / "scan" / "nuovi"
    source.mkdir(parents=True)
    warnings = core.config_warnings(str(source), str(tmp_path / "scan"))
    assert warnings and "excluded" in warnings[0]


# ---------------------------------------------------------------------------
# End-to-end scenario
# ---------------------------------------------------------------------------

def test_end_to_end_rebranding_campaign(tmp_path):
    """Scan -> match -> replace -> restore."""
    scan = tmp_path / "share"
    source = tmp_path / "nuovi_loghi"

    make_image(scan / "sito" / "logo_header.png", (200, 60))
    make_image(scan / "intranet" / "logo_footer.png", (100, 30))
    make_image(scan / "docs" / "immagine.png", (50, 50))       # outside the pattern
    make_image(source / "logo_header.png", (200, 60), color=(0, 0, 255))
    make_image(source / "logo_footer.png", (100, 30), color=(0, 0, 255))

    targets = [core.FileInfo.from_path(p)
               for p in core.scan_files(str(scan), "logo*.png")]
    sources = [core.FileInfo.from_path(p)
               for p in core.collect_source_files(str(source))]
    assert len(targets) == 2

    matches = core.build_matches(targets, sources)
    assert all(m.source is not None and m.quality == core.QUALITY_EXCELLENT
               for m in matches)

    report = core.replace_all(matches, backup=True)
    assert report.ok == 2 and report.errors == 0

    header = scan / "sito" / "logo_header.png"
    assert Image.open(header).getpixel((0, 0)) == (0, 0, 255)

    restore = core.restore_backups(str(scan))
    assert restore.ok == 2
    assert Image.open(header).getpixel((0, 0)) == (255, 0, 0)
