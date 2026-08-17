#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Tests for the command line interface.

Unattended runs are where a mistake is most expensive: no preview, no colours,
nobody watching. Most of what follows is therefore about the run *not*
happening — the defaults and the guards that stop a scheduled job from
overwriting something it should not have.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cli  # noqa: E402
import core  # noqa: E402

pytest.importorskip("PIL", reason="Pillow is needed to build test images")
from PIL import Image, ImageDraw  # noqa: E402


def mark(path, size=(240, 80), colour=(196, 62, 58)):
    path = str(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    image = Image.new("RGB", size, (255, 255, 255))
    draw = ImageDraw.Draw(image)
    w, h = size
    draw.ellipse((w * .04, h * .15, w * .32, h * .85), fill=colour)
    draw.rectangle((w * .38, h * .30, w * .94, h * .48), fill=colour)
    draw.rectangle((w * .38, h * .56, w * .72, h * .72), fill=(90, 90, 90))
    image.save(path)
    return path


@pytest.fixture
def tree(tmp_path):
    """A share with the logo hiding under a name no pattern would guess."""
    mark(tmp_path / "share" / "web" / "header_bg.png")
    mark(tmp_path / "share" / "site" / "logo_header.png")
    mark(tmp_path / "new" / "brand.png", colour=(20, 90, 170))
    return {
        "scan": str(tmp_path / "share"),
        "source": str(tmp_path / "new"),
        "reference": mark(tmp_path / "ref" / "old.png"),
        "target": str(tmp_path / "share" / "web" / "header_bg.png"),
    }


def run(*args) -> int:
    return cli.main(list(args))


# ---------------------------------------------------------------------------
# The default is to change nothing
# ---------------------------------------------------------------------------

def test_a_run_without_apply_writes_nothing(tree, capsys):
    before = open(tree["target"], "rb").read()

    code = run("--scan", tree["scan"], "--source", tree["source"],
               "--reference", tree["reference"])

    assert code == cli.EXIT_OK
    assert open(tree["target"], "rb").read() == before, (
        "a dry run must be the default: an unattended job that overwrites "
        "because someone forgot a flag is the failure mode to design out"
    )
    assert "Dry run" in capsys.readouterr().out


def test_apply_actually_replaces(tree):
    code = run("--scan", tree["scan"], "--source", tree["source"],
               "--reference", tree["reference"], "--apply")

    assert code == cli.EXIT_OK
    assert Image.open(tree["target"]).convert("RGB").getpixel((60, 40)) == (20, 90, 170)
    assert os.path.exists(tree["target"] + ".bak"), "backups are on by default"


def test_no_backup_is_honoured(tree):
    run("--scan", tree["scan"], "--source", tree["source"],
        "--pattern", "logo*.png", "--apply", "--no-backup")
    assert not os.path.exists(str(tree["scan"]) + "/site/logo_header.png.bak")


# ---------------------------------------------------------------------------
# Exit codes: what a scheduler actually reads
# ---------------------------------------------------------------------------

def test_nothing_found(tree):
    assert run("--scan", tree["scan"], "--source", tree["source"],
               "--pattern", "nothing_like_this*.png") == cli.EXIT_NOTHING_FOUND


def test_a_bad_folder_is_a_bad_request(tree, capsys):
    assert run("--scan", "/no/such/folder", "--source", tree["source"],
               "--pattern", "logo*.png") == cli.EXIT_BAD_REQUEST
    assert capsys.readouterr().err.strip()


def test_an_unusable_reference_is_a_bad_request(tmp_path, tree):
    svg = tmp_path / "ref.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
    assert run("--scan", tree["scan"], "--source", tree["source"],
               "--reference", str(svg)) == cli.EXIT_BAD_REQUEST


def test_a_failed_replacement_is_reported_as_errors(tree, monkeypatch):
    monkeypatch.setattr(core, "replace_file",
                        lambda target, source, **kw: core.ReplaceOutcome(
                            target, source, "error", "nope"))
    assert run("--scan", tree["scan"], "--source", tree["source"],
               "--pattern", "logo*.png", "--apply") == cli.EXIT_ERRORS


def test_missing_arguments_are_refused(tree):
    with pytest.raises(SystemExit):
        run("--scan", tree["scan"], "--source", tree["source"])   # no way to search
    with pytest.raises(SystemExit):
        run("--source", tree["source"], "--pattern", "logo*.png")  # no --scan


# ---------------------------------------------------------------------------
# Safety guards: the point of the whole exercise
# ---------------------------------------------------------------------------

def _match(similarity=None, target_dim=(240, 80), source_dim=(240, 80),
           embedded=False):
    target = core.FileInfo(path="t.png", name="t.png", ext=".png", size=1,
                           dim=target_dim, similarity=similarity,
                           container="d.docx" if embedded else None,
                           entry="word/media/image1.png" if embedded else None)
    source = core.FileInfo(path="s.png", name="s.png", ext=".png", size=1,
                           dim=source_dim)
    return core.Match(target=target, source=source, enabled=True)


class Args:
    """Just enough of the parsed arguments for the guard."""
    def __init__(self, **kwargs):
        self.apply = kwargs.get("apply", True)
        self.max_uncertain = kwargs.get("max_uncertain", 0)
        self.allow_distortion = kwargs.get("allow_distortion", False)


def test_uncertain_hits_block_a_writing_run(capsys):
    """
    Below the confident threshold the interface would colour the row and expect
    a human to look. Unattended there is nobody, so the run stops instead.
    """
    matches = [_match(similarity=0.91), _match(similarity=0.99)]
    reporter = cli.Reporter()

    assert cli.check_safety(Args(), matches, reporter) == cli.EXIT_REFUSED
    assert "Refusing to write" in capsys.readouterr().err


def test_uncertain_hits_do_not_block_a_dry_run(capsys):
    """A dry run is exactly how you discover them."""
    matches = [_match(similarity=0.91)]
    assert cli.check_safety(Args(apply=False), matches, cli.Reporter()) is None


def test_the_uncertainty_budget_can_be_raised_deliberately():
    matches = [_match(similarity=0.91)]
    assert cli.check_safety(Args(max_uncertain=1), matches, cli.Reporter()) is None


def test_confident_hits_pass():
    matches = [_match(similarity=0.99), _match(similarity=1.0)]
    assert cli.check_safety(Args(), matches, cli.Reporter()) is None


def test_name_based_hits_are_never_uncertain():
    """A file matched by name has no similarity, and none is implied."""
    matches = [_match(similarity=None)]
    assert cli.check_safety(Args(), matches, cli.Reporter()) is None


def test_a_distorting_replacement_blocks_a_writing_run(capsys):
    """A square logo bound for a 3:1 frame would be stretched silently."""
    matches = [_match(target_dim=(240, 80), source_dim=(200, 200), embedded=True)]
    assert cli.check_safety(Args(), matches, cli.Reporter()) == cli.EXIT_REFUSED
    assert "stretch" in capsys.readouterr().err


def test_distortion_can_be_allowed_deliberately():
    matches = [_match(target_dim=(240, 80), source_dim=(200, 200), embedded=True)]
    assert cli.check_safety(Args(allow_distortion=True), matches,
                            cli.Reporter()) is None


def test_distortion_only_applies_inside_documents():
    """A loose file has no frame to be stretched by."""
    matches = [_match(target_dim=(240, 80), source_dim=(200, 200), embedded=False)]
    assert cli.check_safety(Args(), matches, cli.Reporter()) is None


def test_the_guard_reports_the_offending_files(capsys):
    matches = [_match(similarity=0.90 + index / 1000) for index in range(15)]
    cli.check_safety(Args(), matches, cli.Reporter())

    err = capsys.readouterr().err
    assert "and 5 more" in err, "the list is capped so a log stays readable"


# ---------------------------------------------------------------------------
# Office documents and reports
# ---------------------------------------------------------------------------

def test_office_documents_are_searched_when_asked(tmp_path, tree):
    docx = pytest.importorskip("docx")
    import office

    document = docx.Document()
    document.add_picture(tree["reference"])
    path = os.path.join(tree["scan"], "report.docx")
    document.save(path)

    assert run("--scan", tree["scan"], "--source", tree["source"],
               "--reference", tree["reference"], "--office", "--apply") == cli.EXIT_OK

    entry = office.list_images(path)[0][0].entry
    temp = office.extract_to_temp(path, entry)
    try:
        assert Image.open(temp).convert("RGB").getpixel((60, 40)) == (20, 90, 170)
    finally:
        os.remove(temp)


def test_a_report_is_written_without_asking(tree, tmp_path):
    report = tmp_path / "out.csv"
    run("--scan", tree["scan"], "--source", tree["source"],
        "--pattern", "logo*.png", "--report", str(report))

    assert report.exists()
    content = report.read_text(encoding="utf-8-sig")
    assert "logo_header.png" in content


def test_a_report_is_still_written_when_the_run_is_refused(tree, tmp_path,
                                                           monkeypatch):
    """Refusing must still leave evidence of why."""
    report = tmp_path / "refused.csv"
    monkeypatch.setattr(cli, "check_safety",
                        lambda *a, **k: cli.EXIT_REFUSED)

    assert run("--scan", tree["scan"], "--source", tree["source"],
               "--pattern", "logo*.png", "--apply",
               "--report", str(report)) == cli.EXIT_REFUSED
    assert report.exists()


# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------

def test_restore_also_defaults_to_a_dry_run(tree, capsys):
    run("--scan", tree["scan"], "--source", tree["source"],
        "--pattern", "logo*.png", "--apply")
    replaced = os.path.join(tree["scan"], "site", "logo_header.png")
    assert Image.open(replaced).convert("RGB").getpixel((60, 40)) == (20, 90, 170)

    assert run("--scan", tree["scan"], "--restore") == cli.EXIT_OK
    assert Image.open(replaced).convert("RGB").getpixel((60, 40)) == (20, 90, 170), \
        "without --apply nothing should have been restored"

    assert run("--scan", tree["scan"], "--restore", "--apply") == cli.EXIT_OK
    assert Image.open(replaced).convert("RGB").getpixel((60, 40)) == (196, 62, 58)


def test_restore_with_no_backups_says_so(tree):
    assert run("--scan", tree["scan"], "--restore") == cli.EXIT_NOTHING_FOUND


# ---------------------------------------------------------------------------
# Output control and language
# ---------------------------------------------------------------------------

def test_quiet_suppresses_progress_but_not_problems(tree, capsys):
    run("--scan", "/no/such/folder", "--source", tree["source"],
        "--pattern", "logo*.png", "--quiet")
    captured = capsys.readouterr()
    assert captured.out.strip() == ""
    assert captured.err.strip(), "problems must survive --quiet"


def test_verbose_lists_each_pairing(tree, capsys):
    run("--scan", tree["scan"], "--source", tree["source"],
        "--pattern", "logo*.png", "--verbose")
    assert "logo_header.png <-" in capsys.readouterr().out


def test_language_affects_core_messages(tree, capsys):
    import i18n

    run("--scan", "/no/such/folder", "--source", tree["source"],
        "--pattern", "logo*.png", "--language", "it")
    assert "Seleziona una cartella" in capsys.readouterr().err
    assert i18n.get_language() == "it"


# ---------------------------------------------------------------------------
# The entry point
# ---------------------------------------------------------------------------

def test_main_dispatches_to_the_cli_when_given_arguments(monkeypatch, tree):
    """One executable serves both a person and a scheduled job."""
    import main as main_module

    monkeypatch.setattr(sys, "argv", ["proteus", "--scan", tree["scan"],
                                      "--source", tree["source"],
                                      "--pattern", "logo*.png"])
    assert main_module.main() == cli.EXIT_OK


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.mark.skipif(os.name == "nt", reason="run.sh is the POSIX launcher")
def test_the_posix_launcher_forwards_arguments_and_the_exit_code(tree):
    """
    Regression: run.sh refused to start without tkinter and swallowed its
    arguments. Both are fatal for the case it now has to serve — a scheduled
    job on a headless server, whose scheduler reads the exit code.
    """
    import subprocess

    result = subprocess.run(
        [os.path.join(REPO, "run.sh"), "--scan", tree["scan"],
         "--source", tree["source"], "--pattern", "nothing*.png"],
        capture_output=True, text=True,
        env={**os.environ, "PYTHON": sys.executable},
    )
    assert result.returncode == cli.EXIT_NOTHING_FOUND, result.stderr


def test_the_windows_launcher_does_not_wait_for_a_keypress_when_scripted():
    """`pause` in an unattended run means a job that never finishes."""
    with open(os.path.join(REPO, "run.bat"), encoding="utf-8") as fh:
        script = fh.read()

    scripted = script.split('if not "%~1"=="" (', 1)[1].split(")", 1)[0]
    assert "main.py" in scripted and "%*" in scripted
    assert "pause" not in scripted
    assert "exit /b %errorlevel%" in scripted


def test_version_is_reported_and_exits_cleanly(capsys):
    """
    What a packaging script or a deployment check calls first. argparse raises
    SystemExit for --version, which must not read as a failure.
    """
    with pytest.raises(SystemExit) as exit_info:
        cli.build_parser().parse_args(["--version"])

    assert exit_info.value.code == 0
    assert core.APP_VERSION in capsys.readouterr().out


def test_an_interruption_uses_the_conventional_exit_code(monkeypatch):
    monkeypatch.setattr(cli, "main", lambda *a, **k: (_ for _ in ()).throw(
        KeyboardInterrupt()))
    assert cli.entry_point() == cli.EXIT_INTERRUPTED


# ---------------------------------------------------------------------------
# PDF support, and the rule that nothing is dropped silently
# ---------------------------------------------------------------------------

def _pdf_tree(tmp_path):
    """A share with one replaceable PDF and one vector-only PDF."""
    pytest.importorskip("pypdf")
    from PIL import Image
    from pypdf.generic import DecodedStreamObject, NameObject
    import pypdf

    scan = tmp_path / "share"
    os.makedirs(scan, exist_ok=True)
    logo = mark(tmp_path / "assets" / "old.png")
    Image.open(logo).convert("RGB").save(str(scan / "brochure.pdf"))

    writer = pypdf.PdfWriter()
    page = writer.add_blank_page(200, 100)
    content = DecodedStreamObject()
    content.set_data(b"0.77 0.24 0.23 rg 10 20 100 50 re f")
    page[NameObject("/Contents")] = writer._add_object(content)
    with open(str(scan / "flyer.pdf"), "wb") as handle:
        writer.write(handle)

    mark(tmp_path / "new" / "brand.png", colour=(20, 90, 170))
    return {"scan": str(scan), "source": str(tmp_path / "new")}


def test_pdf_images_are_found_when_asked(tmp_path, capsys):
    tree = _pdf_tree(tmp_path)
    run("--scan", tree["scan"], "--source", tree["source"], "--pdf", "--verbose")
    assert "brochure.pdf!/p1i1" in capsys.readouterr().out


def test_a_finding_changes_the_exit_code(tmp_path, capsys):
    """
    The rule, expressed where it matters most.

    A scheduled job reads the exit code and nothing else. A run that replaced
    what it could but left a vector logo behind must not look like a clean one,
    or nobody will ever go and fix it by hand.
    """
    tree = _pdf_tree(tmp_path)
    code = run("--scan", tree["scan"], "--source", tree["source"],
               "--pattern", "*.pdf", "--pdf", "--apply")

    assert code == cli.EXIT_ATTENTION
    captured = capsys.readouterr()
    assert "flyer.pdf" in captured.err
    assert "vector" in captured.err.lower()
    assert "need manual intervention" in captured.err


def test_a_finding_carries_a_remedy(tmp_path, capsys):
    tree = _pdf_tree(tmp_path)
    run("--scan", tree["scan"], "--source", tree["source"],
        "--pattern", "*.pdf", "--pdf")
    assert "->" in capsys.readouterr().err, "a problem needs a suggested fix"


def test_findings_survive_quiet(tmp_path, capsys):
    """--quiet silences progress, never something needing a human."""
    tree = _pdf_tree(tmp_path)
    code = run("--scan", tree["scan"], "--source", tree["source"],
               "--pattern", "*.pdf", "--pdf", "--quiet")
    captured = capsys.readouterr()

    assert code == cli.EXIT_ATTENTION
    assert captured.out.strip() == ""
    assert "flyer.pdf" in captured.err


def test_a_clean_pdf_run_still_exits_zero(tmp_path):
    """The attention code must mean something, so it cannot be the default."""
    pytest.importorskip("pypdf")
    from PIL import Image

    scan = tmp_path / "share"
    os.makedirs(scan, exist_ok=True)
    Image.open(mark(tmp_path / "a" / "old.png")).convert("RGB").save(
        str(scan / "brochure.pdf"))
    mark(tmp_path / "new" / "brand.png", colour=(20, 90, 170))

    code = run("--scan", str(scan), "--source", str(tmp_path / "new"),
               "--pdf", "--apply")
    assert code == cli.EXIT_OK


def test_pdf_alone_is_enough_to_start(tmp_path):
    """--pdf is a source of work in its own right, like --office."""
    tree = _pdf_tree(tmp_path)
    assert run("--scan", tree["scan"], "--source", tree["source"],
               "--pdf") in (cli.EXIT_OK, cli.EXIT_ATTENTION)


# ---------------------------------------------------------------------------
# Inventory mode
# ---------------------------------------------------------------------------

def test_audit_needs_no_source_folder(tree, capsys):
    """
    Step one of a rebranding: count the copies before the new logo exists.

    Requiring --source here would have forced people to invent an empty folder
    just to be allowed to look.
    """
    code = run("--scan", tree["scan"], "--pattern", "logo*.png", "--audit")

    assert code == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "Inventory of" in out
    assert "By format:" in out and "By folder:" in out


def test_audit_writes_nothing(tree):
    before = open(tree["target"], "rb").read()
    run("--scan", tree["scan"], "--reference", tree["reference"], "--audit")
    assert open(tree["target"], "rb").read() == before


def test_audit_refuses_apply(tree):
    """The two are contradictory, so it is an argument error, not a silent skip."""
    with pytest.raises(SystemExit):
        run("--scan", tree["scan"], "--pattern", "logo*.png", "--audit", "--apply")


def test_audit_counts_by_format_and_folder(tree, capsys):
    code = run("--scan", tree["scan"], "--reference", tree["reference"], "--audit")
    out = capsys.readouterr().out

    assert code == cli.EXIT_OK
    assert "2 file(s) carry the logo" in out
    assert "PNG" in out


def test_audit_reports_nothing_found(tmp_path):
    empty = tmp_path / "empty"
    os.makedirs(empty, exist_ok=True)
    assert run("--scan", str(empty), "--pattern", "logo*.png",
               "--audit") == cli.EXIT_NOTHING_FOUND


def test_audit_csv_holds_both_halves_of_the_job(tmp_path, capsys):
    """
    The findings share the file with the matches on purpose. Two files would let
    somebody circulate the encouraging half alone, and an inventory exists to
    size the whole job — including the part no tool will do.
    """
    tree = _pdf_tree(tmp_path)
    report = tmp_path / "inventory.csv"

    run("--scan", tree["scan"], "--pattern", "*.pdf", "--pdf", "--audit",
        "--report", str(report))

    rows = report.read_text(encoding="utf-8-sig").splitlines()
    assert rows[0].startswith("Status;Folder;File")
    assert any(row.startswith("found;") for row in rows[1:])
    assert any(row.startswith("needs attention;") for row in rows[1:])
    assert any("vector" in row for row in rows[1:])


def test_audit_on_a_missing_folder_is_a_bad_request(tmp_path):
    assert run("--scan", "/no/such/folder", "--pattern", "logo*.png",
               "--audit") == cli.EXIT_BAD_REQUEST


def test_an_unreadable_folder_becomes_a_finding(tree, monkeypatch, capsys):
    """
    "We scanned everything" is false while one branch of the tree was refused,
    so a folder the scan could not enter is a finding and changes the exit code.
    """
    import errno

    real_walk = os.walk

    def refusing_walk(top, **kwargs):
        onerror = kwargs.get("onerror")
        if onerror:
            exc = PermissionError("denied")
            exc.errno = errno.EACCES
            exc.filename = os.path.join(str(top), "finance")
            onerror(exc)
        yield from real_walk(top, **kwargs)

    monkeypatch.setattr(core.os, "walk", refusing_walk)
    code = run("--scan", tree["scan"], "--pattern", "logo*.png", "--audit")

    captured = capsys.readouterr()
    assert code == cli.EXIT_ATTENTION
    assert "finance" in captured.err
    assert "not examined" in captured.err
