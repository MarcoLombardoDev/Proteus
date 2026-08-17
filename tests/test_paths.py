#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Tests for the filesystem quirks of the environment Proteus actually runs in.

Most of this is about Windows and network shares, so the honest position is
stated up front: on Linux the *logic* is tested by simulating the errors, and the
real behaviour — a 300-character path, a locked file — is verified by the Windows
half of the CI matrix. A test that quietly passes on Linux and was never run
where it matters is worse than no test, so the ones that need Windows say so and
skip.
"""

from __future__ import annotations

import errno
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core  # noqa: E402
import paths  # noqa: E402

WINDOWS = os.name == "nt"
windows_only = pytest.mark.skipif(not WINDOWS,
                                  reason="Windows path semantics; run in CI on Windows")


# ---------------------------------------------------------------------------
# The extended-length prefix
# ---------------------------------------------------------------------------

def test_long_path_is_a_no_op_off_windows(monkeypatch):
    monkeypatch.setattr(os, "name", "posix")
    assert paths.long_path("/srv/share/logo.png") == "/srv/share/logo.png"


def test_long_path_prefixes_a_drive_path(monkeypatch):
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr(os.path, "abspath", lambda p: p)
    assert paths.long_path("C:\\share\\logo.png") == "\\\\?\\C:\\share\\logo.png"


def test_long_path_uses_the_unc_form_for_a_share(monkeypatch):
    """
    A UNC path needs a different prefix, and getting it wrong is silent: the
    plain prefix on `\\\\server\\share` produces a path Windows cannot resolve.
    """
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr(os.path, "abspath", lambda p: p)
    assert (paths.long_path("\\\\fs01\\shared\\logo.png")
            == "\\\\?\\UNC\\fs01\\shared\\logo.png")


def test_long_path_is_idempotent(monkeypatch):
    """Applied twice by two layers, it must not double the prefix."""
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr(os.path, "abspath", lambda p: p)
    once = paths.long_path("C:\\share\\logo.png")
    assert paths.long_path(once) == once


def test_long_path_tolerates_an_empty_string(monkeypatch):
    monkeypatch.setattr(os, "name", "nt")
    assert paths.long_path("") == ""


def test_is_long_matches_the_windows_limit():
    assert not paths.is_long("C:\\" + "a" * 100)
    assert paths.is_long("C:\\" + "a" * 300)


# ---------------------------------------------------------------------------
# Explaining a filesystem error
# ---------------------------------------------------------------------------

def _error(errno_code=None, winerror=None):
    exc = OSError("boom")
    exc.errno = errno_code
    if winerror is not None:
        exc.winerror = winerror
    return exc


def test_a_locked_file_is_not_reported_as_a_permission_problem():
    """
    Windows raises PermissionError when a file is open in Word. Saying
    "access denied" sends the user to their IT department for something they
    can fix by closing the document.
    """
    reason, hint = paths.describe_os_error(_error(errno.EACCES, winerror=32),
                                          "C:\\share\\offer.docx")
    assert "open in another program" in reason
    assert "offer.docx" in reason
    assert "Close the file" in hint


def test_access_denied_names_both_likely_causes():
    reason, hint = paths.describe_os_error(_error(errno.EACCES), "/srv/logo.png")
    assert "Access denied" in reason
    assert "read-only" in hint and "permission" in hint


def test_a_too_long_path_wins_over_the_not_found_message():
    """
    Regression in this module's own logic. Windows reports a path past
    MAX_PATH as "cannot find the file", so the generic not-found branch fired
    first and told the user a file that is right there does not exist.
    """
    long = "C:\\" + "\\".join("department" for _ in range(30)) + "\\logo.png"
    assert paths.is_long(long)

    reason, hint = paths.describe_os_error(_error(errno.ENOENT), long)
    assert "too long" in reason
    assert str(len(long)) in reason
    assert "Shorten" in hint


def test_a_short_missing_path_still_says_missing():
    reason, _ = paths.describe_os_error(_error(errno.ENOENT), "/srv/logo.png")
    assert "no longer exists" in reason


def test_a_full_disk_says_so():
    reason, hint = paths.describe_os_error(_error(errno.ENOSPC), "/srv/logo.png")
    assert "No space" in reason and "Free some space" in hint


def test_an_unknown_error_still_produces_a_remedy():
    """Every finding carries a next step, even the ones we cannot classify."""
    reason, hint = paths.describe_os_error(_error(errno.EIO), "/srv/logo.png")
    assert "logo.png" in reason
    assert hint


def test_an_unreadable_folder_says_its_contents_were_not_examined():
    """
    The wording matters: the user has to understand that the scan is
    incomplete, not merely that one folder was odd.
    """
    reason, hint = paths.describe_unreadable_folder(_error(errno.EACCES),
                                                    "/srv/finance")
    assert "not examined" in reason
    assert "/srv/finance" in reason
    assert hint


# ---------------------------------------------------------------------------
# Replacement behaviour, through core
# ---------------------------------------------------------------------------

def test_a_replacement_error_is_explained_not_dumped(tmp_path, monkeypatch):
    """
    The outcome message is what a user reads in the log. A raw OSError repr is
    not an explanation, and on a share it is usually the wrong one.
    """
    target = tmp_path / "logo.png"
    source = tmp_path / "new.png"
    target.write_bytes(b"old")
    source.write_bytes(b"new")

    def locked(*_args, **_kwargs):
        exc = PermissionError("denied")
        exc.errno = errno.EACCES
        exc.winerror = 32
        raise exc

    monkeypatch.setattr(core.os, "replace", locked)
    outcome = core.replace_file(str(target), str(source), backup=False)

    assert outcome.status == "error"
    assert "open in another program" in outcome.message
    assert "Close the file" in outcome.message


def test_the_original_survives_a_failed_replacement(tmp_path, monkeypatch):
    """The whole reason the copy lands on a temporary file first."""
    target = tmp_path / "logo.png"
    source = tmp_path / "new.png"
    target.write_bytes(b"original")
    source.write_bytes(b"replacement")

    def boom(*_args, **_kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr(core.os, "replace", boom)
    core.replace_file(str(target), str(source), backup=False)

    assert target.read_bytes() == b"original"
    leftovers = [f for f in os.listdir(tmp_path) if f.startswith(".proteus_")]
    assert leftovers == [], "the temporary file must be cleaned up"


# ---------------------------------------------------------------------------
# Real Windows behaviour — verified by the Windows half of the CI matrix
# ---------------------------------------------------------------------------

@windows_only
def test_a_path_past_max_path_can_really_be_replaced(tmp_path):
    """
    The one that matters, and the one that cannot be faked: build a path longer
    than 260 characters and replace a file at the end of it.
    """
    deep = tmp_path
    while len(str(deep)) < 300:
        deep = deep / "department_with_a_long_name"
    os.makedirs(paths.long_path(str(deep)), exist_ok=True)

    target = str(deep / "logo.png")
    source = str(tmp_path / "new.png")
    assert paths.is_long(target), f"path is only {len(target)} characters"

    with open(paths.long_path(target), "wb") as handle:
        handle.write(b"old")
    with open(paths.long_path(source), "wb") as handle:
        handle.write(b"new")

    outcome = core.replace_file(target, source, backup=True)

    assert outcome.ok, outcome.message
    with open(paths.long_path(target), "rb") as handle:
        assert handle.read() == b"new"
    assert os.path.exists(paths.long_path(outcome.backup))


@windows_only
def test_a_file_open_elsewhere_is_reported_with_its_remedy(tmp_path):
    """
    A document open in Word is the commonest failure on a live share.

    Reproducing it needs care, and the first attempt did not. `msvcrt.locking`
    locks a byte range, which `os.replace` never consults, and CPython opens
    files with FILE_SHARE_DELETE — so holding the file with a plain `open()`
    does not block the replacement at all. CI proved it: the test self-skipped
    on Windows with "allowed the replace despite the lock", verifying nothing.

    Word holds the file with a restrictive share mode, so that is what this
    does: CreateFileW with dwShareMode = 0. No extra dependency, just ctypes.
    """
    import ctypes

    target = tmp_path / "logo.png"
    source = tmp_path / "new.png"
    target.write_bytes(b"old")
    source.write_bytes(b"new")

    GENERIC_READ = 0x80000000
    OPEN_EXISTING = 3
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.restype = ctypes.c_void_p
    handle = kernel32.CreateFileW(str(target), GENERIC_READ,
                                  0,           # exclusive: what Word does
                                  None, OPEN_EXISTING, 0, None)
    assert handle != INVALID_HANDLE_VALUE, (
        f"could not open exclusively: {ctypes.get_last_error()}")

    try:
        outcome = core.replace_file(str(target), str(source), backup=False)
    finally:
        kernel32.CloseHandle(ctypes.c_void_p(handle))

    assert outcome.status == "error", "an exclusively held file must not be replaced"
    assert "open in another program" in outcome.message, outcome.message
    assert "Close the file" in outcome.message
    assert target.read_bytes() == b"old", "the original must survive"
