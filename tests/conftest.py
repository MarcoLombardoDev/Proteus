#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Configurazione comune dei test."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def no_modal_dialogs(monkeypatch):
    """
    Neutralizza tutte le finestre modali.

    Senza questa protezione un test che percorre un ramo con `askyesno` o
    `asksaveasfilename` apre una finestra reale e la suite resta appesa a
    tempo indefinito invece di fallire.
    """
    try:
        from tkinter import filedialog, messagebox
    except ImportError:
        return  # tkinter assente: i test GUI vengono comunque saltati

    for name in ("showinfo", "showwarning", "showerror"):
        monkeypatch.setattr(messagebox, name, lambda *a, **k: "ok", raising=False)
    for name in ("askyesno", "askokcancel", "askretrycancel"):
        monkeypatch.setattr(messagebox, name, lambda *a, **k: False, raising=False)
    monkeypatch.setattr(messagebox, "askquestion", lambda *a, **k: "no", raising=False)

    for name in ("askdirectory", "askopenfilename", "asksaveasfilename"):
        monkeypatch.setattr(filedialog, name, lambda *a, **k: "", raising=False)
    monkeypatch.setattr(filedialog, "askopenfilenames", lambda *a, **k: (), raising=False)
