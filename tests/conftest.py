#!/usr/bin/env python
# Proteus — Rebranding Tool
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.
# A commercial licence, without the AGPL's obligations, is available for use
# in proprietary or closed-source products — see COMMERCIAL-LICENSE.md.

"""Shared test configuration."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def reset_language():
    """
    Start every test from the default language.

    The active language is module-level state: without this, a test that
    switches to Italian would leak into the ones that follow.
    """
    import i18n

    previous = i18n.get_language()
    i18n.set_language(i18n.DEFAULT_LANGUAGE)
    yield
    i18n.set_language(previous)


@pytest.fixture(autouse=True)
def no_modal_dialogs(monkeypatch):
    """
    Neutralise every modal dialog.

    Without this guard, a test walking a branch with `askyesno` or
    `asksaveasfilename` opens a real window and the suite hangs indefinitely
    instead of failing.
    """
    try:
        from tkinter import filedialog, messagebox
    except ImportError:
        return  # no tkinter: the GUI tests are skipped anyway

    for name in ("showinfo", "showwarning", "showerror"):
        monkeypatch.setattr(messagebox, name, lambda *a, **k: "ok", raising=False)
    for name in ("askyesno", "askokcancel", "askretrycancel"):
        monkeypatch.setattr(messagebox, name, lambda *a, **k: False, raising=False)
    monkeypatch.setattr(messagebox, "askquestion", lambda *a, **k: "no", raising=False)

    for name in ("askdirectory", "askopenfilename", "asksaveasfilename"):
        monkeypatch.setattr(filedialog, name, lambda *a, **k: "", raising=False)
    monkeypatch.setattr(filedialog, "askopenfilenames", lambda *a, **k: (), raising=False)
