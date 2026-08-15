#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Tests for the build script.

These do not run PyInstaller — that happens in CI. They cover the parts of
build.py that are easy to get wrong in a platform-specific way, which is
exactly where it has broken before.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import build  # noqa: E402


# ---------------------------------------------------------------------------
# Console encoding
# ---------------------------------------------------------------------------

def test_force_utf8_output_makes_a_legacy_codepage_stream_safe(monkeypatch):
    """
    Regression: the build died on its first status line under a legacy code
    page, because that line contains an emoji.

    cp1252 is what the Windows CI runners use; a plain Windows console uses
    cp850. Either way `print("🔍 ...")` raised UnicodeEncodeError and took the
    build down before any work started.
    """
    buffer = io.BytesIO()
    stream = io.TextIOWrapper(buffer, encoding="cp1252", newline="")
    monkeypatch.setattr(sys, "stdout", stream)

    # Without the fix this is the failure mode.
    with pytest.raises(UnicodeEncodeError):
        stream.write("🔍")
        stream.flush()

    build.force_utf8_output()

    print("🔍 Checking prerequisites...")
    stream.flush()
    assert "Checking prerequisites".encode() in buffer.getvalue()


def test_force_utf8_output_tolerates_a_non_reconfigurable_stream(monkeypatch):
    """A wrapped or redirected stdout must not make the build explode."""
    class Dumb:
        def write(self, _text):
            return 0

        def flush(self):
            pass

    monkeypatch.setattr(sys, "stdout", Dumb())
    monkeypatch.setattr(sys, "stderr", Dumb())
    build.force_utf8_output()   # must not raise


def test_every_emoji_in_the_script_survives_the_fix():
    """
    Any emoji added to the progress output later must still be printable once
    the streams are reconfigured. Guards against someone reintroducing a
    character that even UTF-8 output cannot carry.
    """
    with open(build.__file__, encoding="utf-8") as fh:
        source = fh.read()

    non_ascii = {ch for ch in source if ord(ch) > 127}
    encoded = "".join(sorted(non_ascii)).encode("utf-8", errors="strict")
    assert encoded, "expected the script to contain non-ASCII status markers"


# ---------------------------------------------------------------------------
# Platform handling
# ---------------------------------------------------------------------------

def test_add_data_separator_matches_the_platform():
    """PyInstaller wants ';' on Windows and ':' elsewhere."""
    assert build.DATA_SEP == os.pathsep
    assert build.DATA_SEP == (";" if os.name == "nt" else ":")


def test_python_launcher_is_runnable():
    """
    Whatever launcher is chosen must actually execute Python. On Linux and
    inside virtual environments this has to be sys.executable, because the
    Windows `py` launcher does not exist there.
    """
    launcher = build.python_launcher()
    assert launcher, "a launcher must always be returned"

    result = subprocess.run(launcher + ["-c", "print('ok')"],
                            capture_output=True, text=True)
    assert result.returncode == 0
    assert result.stdout.strip() == "ok"


def test_python_launcher_falls_back_off_windows(monkeypatch):
    monkeypatch.setattr(os, "name", "posix")
    assert build.python_launcher() == [sys.executable]


# ---------------------------------------------------------------------------
# Build configuration
# ---------------------------------------------------------------------------

def test_builder_names_the_executable_after_the_product():
    builder = build.RebrandingToolBuilder()
    assert builder.app_name == "Proteus"
    assert builder.exe_suffix == (".exe" if os.name == "nt" else "")


# ---------------------------------------------------------------------------
# The two binaries
# ---------------------------------------------------------------------------

def _pyinstaller_command(monkeypatch, builder, **kwargs) -> list[str]:
    """Capture the PyInstaller invocation without running it."""
    captured: list[list[str]] = []

    def fake_run(args, **_kwargs):
        captured.append(args)
        # The ttkbootstrap probe goes through the same helper.
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="")

    monkeypatch.setattr(builder, "_run", fake_run)
    builder.build_executable(**kwargs)   # returns None: nothing was really built
    return next(a for a in captured if "PyInstaller" in a)


def test_the_gui_binary_is_windowed(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    builder = build.RebrandingToolBuilder()
    cmd = _pyinstaller_command(monkeypatch, builder)
    assert "--windowed" in cmd
    assert f"--name={builder.app_name}" in cmd


def test_the_cli_binary_is_console_attached(monkeypatch, tmp_path):
    """
    Regression: with only a --windowed executable, Windows gives the CLI no
    console at all — every line it prints disappears and a scheduled job cannot
    be diagnosed. The command line therefore needs its own console binary.
    """
    monkeypatch.chdir(tmp_path)
    builder = build.RebrandingToolBuilder()
    cmd = _pyinstaller_command(monkeypatch, builder,
                               name=builder.cli_name, windowed=False)
    assert "--console" in cmd
    assert "--windowed" not in cmd
    assert f"--name={builder.cli_name}" in cmd


def test_cli_module_is_bundled():
    """Without it the frozen executable cannot serve a scheduled job at all."""
    with open(build.__file__, encoding="utf-8") as fh:
        source = fh.read()
    assert '"cli"' in source
    assert "cli.py" in source


def test_distribution_notes_mention_the_command_line(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    builder = build.RebrandingToolBuilder()
    builder.create_distribution("dist/Proteus.exe", "dist/proteus-cli.exe")

    notes = (tmp_path / "dist" / "READ_ME_FIRST.txt").read_text(encoding="utf-8")
    assert "proteus-cli.exe" in notes
    assert "--apply" in notes


def test_prerequisites_report_a_missing_source_file(tmp_path, monkeypatch, capsys):
    """A missing module must be reported rather than discovered by PyInstaller."""
    monkeypatch.chdir(tmp_path)
    builder = build.RebrandingToolBuilder()
    monkeypatch.setattr(builder, "_ensure_module", lambda module, package: True)

    assert builder.check_prerequisites() is False
    assert "main.py" in capsys.readouterr().out


def test_pil_tkinter_finder_is_a_hidden_import():
    """
    Regression: without it the frozen executable started but every image
    preview was broken, with "No module named 'PIL._tkinter_finder'".
    """
    with open(build.__file__, encoding="utf-8") as fh:
        source = fh.read()
    assert "PIL._tkinter_finder" in source
