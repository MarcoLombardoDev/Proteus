#!/usr/bin/env python
# Proteus — Rebranding Tool
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.
# A commercial licence, without the AGPL's obligations, is available for use
# in proprietary or closed-source products — see COMMERCIAL-LICENSE.md.

"""Tests for the translation layer and the language switcher."""

from __future__ import annotations

import ast
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core  # noqa: E402
import i18n  # noqa: E402

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#: Every module that puts text in front of a user. A module missing here
#: makes the stale-entry guard report its strings as unused, and lets its
#: untranslated ones through unnoticed.
TRANSLATED_MODULES = ("core.py", "rebranding_tool.py", "pdf.py", "office.py",
                      "paths.py", "cli.py")


# ---------------------------------------------------------------------------
# Basic behaviour
# ---------------------------------------------------------------------------

def test_default_language_is_english():
    assert i18n.DEFAULT_LANGUAGE == "en"
    assert i18n.get_language() == "en"
    assert i18n.t("Excellent") == "Excellent"


def test_switching_language_translates():
    i18n.set_language("it")
    assert i18n.t("Excellent") == "Ottima"
    assert i18n.t("Cancel") == "Annulla"


def test_unknown_language_falls_back_to_default():
    """A corrupted settings file must never stop the app from starting."""
    assert i18n.set_language("klingon") == i18n.DEFAULT_LANGUAGE
    assert i18n.get_language() == "en"


def test_missing_key_returns_the_english_source():
    i18n.set_language("it")
    assert i18n.t("A string nobody translated") == "A string nobody translated"


def test_language_name_and_code_roundtrip():
    for code in i18n.LANGUAGES:
        assert i18n.code_for_name(i18n.language_name(code)) == code
    assert i18n.code_for_name("Nonexistent") == i18n.DEFAULT_LANGUAGE


def test_every_language_has_a_display_name():
    for code, label in i18n.LANGUAGES.items():
        assert isinstance(label, str) and label.strip()
        assert code == code.lower()


# ---------------------------------------------------------------------------
# Catalogue integrity
# ---------------------------------------------------------------------------

def test_italian_catalogue_is_complete():
    assert i18n.missing_translations("it") == []


def test_no_italian_entry_is_left_untranslated():
    """
    Every Italian value must differ from its English key, except where the two
    languages genuinely coincide (proper nouns, acronyms, symbols).
    """
    allowed_identical = {
        "Pattern:", "Backup", "NO", "Format", "File", "Report", "no",
        "  backup: {path}",
    }
    identical = [
        key for key, value in i18n.CATALOGUES["it"].items()
        if key == value and key not in allowed_identical
    ]
    assert identical == [], f"Untranslated Italian entries: {identical}"


def _translated_literals(filename: str) -> set[str]:
    """Every literal string passed to t() in a module."""
    with open(os.path.join(PROJECT_ROOT, filename), encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=filename)

    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        name = (target.id if isinstance(target, ast.Name)
                else target.attr if isinstance(target, ast.Attribute) else None)
        if name != "t" or not node.args:
            continue
        literal = node.args[0]
        # Implicit concatenation of adjacent literals arrives already folded.
        if isinstance(literal, ast.Constant) and isinstance(literal.value, str):
            found.add(literal.value)
    return found


@pytest.mark.parametrize("module", TRANSLATED_MODULES)
def test_every_translated_string_is_in_the_italian_catalogue(module):
    """
    Guard against drift: a new UI string added without its Italian entry would
    silently show up in English while the rest of the interface is Italian.
    """
    catalogue = i18n.CATALOGUES["it"]
    missing = sorted(s for s in _translated_literals(module) if s not in catalogue)
    assert missing == [], (
        f"{module}: {len(missing)} strings have no Italian translation:\n"
        + "\n".join(f"  - {s!r}" for s in missing)
    )


def test_catalogue_has_no_stale_entries():
    """Catalogue keys that no longer appear anywhere in the code."""
    used: set[str] = set()
    for name in TRANSLATED_MODULES:
        used |= _translated_literals(name)
    # Grades are looked up through Match.quality rather than a literal t().
    used |= {core.QUALITY_EXCELLENT, core.QUALITY_GOOD_LABEL,
             core.QUALITY_WEAK, core.QUALITY_MANUAL}

    stale = sorted(k for k in i18n.CATALOGUES["it"] if k not in used)
    assert stale == [], ("Stale catalogue entries:\n"
                         + "\n".join(f"  - {s!r}" for s in stale))


def test_placeholders_match_between_languages():
    """
    A translation that drops or renames a {placeholder} would raise KeyError at
    format() time, in front of the user.
    """
    import re

    pattern = re.compile(r"\{(\w+)\}")
    mismatched: list[str] = []
    for code, catalogue in i18n.CATALOGUES.items():
        for key, value in catalogue.items():
            if set(pattern.findall(key)) != set(pattern.findall(value)):
                mismatched.append(f"[{code}] {key!r} -> {value!r}")
    assert mismatched == [], "\n".join(mismatched)


# ---------------------------------------------------------------------------
# Integration with core
# ---------------------------------------------------------------------------

def test_core_messages_follow_the_active_language(tmp_path):
    target = tmp_path / "logo.png"
    target.write_bytes(b"x")

    outcome_en = core.replace_file(str(target), str(tmp_path / "missing.png"))
    assert "Source file not found" in outcome_en.message

    i18n.set_language("it")
    outcome_it = core.replace_file(str(target), str(tmp_path / "missing.png"))
    assert "File sorgente non trovato" in outcome_it.message


def test_validation_messages_follow_the_active_language():
    assert "Enter at least one" in core.validate_pattern("")
    i18n.set_language("it")
    assert "Inserisci almeno" in core.validate_pattern("")


def test_quality_key_is_stable_while_label_translates(tmp_path):
    """
    The canonical grade must not change with the language: it drives the row
    colour and is what tests and CSV consumers rely on.
    """
    pytest.importorskip("PIL")
    from PIL import Image

    def image(name, size):
        path = tmp_path / name
        Image.new("RGB", size, (255, 0, 0)).save(path)
        return core.FileInfo.from_path(str(path))

    match = core.Match(target=image("a.png", (100, 100)),
                       source=image("b.png", (100, 100)))

    assert match.quality == core.QUALITY_EXCELLENT
    assert match.quality_label == "Excellent"

    i18n.set_language("it")
    assert match.quality == core.QUALITY_EXCELLENT
    assert match.quality_label == "Ottima"


def test_language_is_persisted_in_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "writable_app_dir", lambda sub: str(tmp_path))
    assert core.save_settings({"language": "it"})
    assert core.load_settings()["language"] == "it"


def test_corrupted_language_setting_is_normalised(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "writable_app_dir", lambda sub: str(tmp_path))
    core.save_settings({"language": "it"})
    (tmp_path / core.SETTINGS_FILE).write_text('{"language": "xx"}')
    assert core.load_settings()["language"] == i18n.DEFAULT_LANGUAGE
