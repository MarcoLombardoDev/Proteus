#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Tests for the graphical interface.

They run headless (Xvfb on Linux, natively on Windows) and are skipped
automatically where no display is available.
"""

from __future__ import annotations

import os
import threading
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

tk = pytest.importorskip("tkinter", reason="tkinter is unavailable")
pytest.importorskip("PIL", reason="Pillow is needed for the previews")

from PIL import Image  # noqa: E402

import core  # noqa: E402


def _display_available() -> bool:
    if os.name == "nt" or sys.platform == "darwin":
        return True
    return bool(os.environ.get("DISPLAY"))


pytestmark = pytest.mark.skipif(
    not _display_available(), reason="No display available (use xvfb-run)"
)


@pytest.fixture(scope="session")
def tk_root():
    """
    One Tk interpreter for the whole test session.

    Creating and destroying a root per test looks tidier, but Tk does not
    survive it: after a couple of dozen create/destroy cycles in one process,
    Windows fails to build another interpreter with
    `TclError: invalid command name "tcl_findLibrary"`. Linux tolerates it,
    which is exactly why this only ever broke in CI. Reusing a single root
    removes the cycle entirely.
    """
    root = tk.Tk()
    root.withdraw()
    yield root
    try:
        root.destroy()
    except tk.TclError:
        pass


@pytest.fixture
def app(tk_root, tmp_path, monkeypatch):
    """Application instance isolated from the real user's settings."""
    monkeypatch.setattr(core, "writable_app_dir", lambda sub: str(tmp_path / sub))
    os.makedirs(tmp_path / "config", exist_ok=True)
    os.makedirs(tmp_path / "logs", exist_ok=True)

    from rebranding_tool import RebrandingToolApp

    instance = RebrandingToolApp(tk_root)
    tk_root.update()
    yield instance

    # Tear down the app but leave the shared interpreter alive: cancel the UI
    # queue tick first, otherwise the pending after() fires during the next
    # test against widgets that no longer exist.
    instance._worker = None
    instance._closing = True
    if instance._pump_after_id is not None:
        try:
            tk_root.after_cancel(instance._pump_after_id)
        except tk.TclError:
            pass
        instance._pump_after_id = None

    for child in list(tk_root.winfo_children()):
        try:
            child.destroy()
        except tk.TclError:
            pass
    try:
        tk_root.update()
    except tk.TclError:
        pass


def make_image(path, size=(100, 50), color=(255, 0, 0), fmt=None):
    path = str(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new("RGB", size, color).save(path, format=fmt)
    return path


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

def test_app_starts_with_all_tabs(app):
    """Regression: with ttkbootstrap 2.x startup failed with a TclError."""
    assert len(app.notebook.tabs()) == 4


def test_progressbar_widget_exists_and_is_bound(app):
    """The progressbar existed only as a variable, with no widget bound to it."""
    assert app._progress is not None
    assert str(app._progress.cget("variable")) == str(app.progress_var)
    app.progress_var.set(42)
    assert app._progress["value"] == pytest.approx(42)


def test_progressbar_is_actually_visible(app):
    """
    Regression: with the default colours the bar was drawn white on a white
    trough, so progress was invisible even though it was correct.
    """
    style = app.style.configure("Brand.Horizontal.TProgressbar") or {}
    from rebranding_tool import BRAND_BLUE, PROGRESS_STYLE

    assert str(app._progress.cget("style")) == PROGRESS_STYLE
    assert style.get("background") == BRAND_BLUE
    assert style.get("troughcolor") != style.get("background")


def test_button_styles_do_not_use_bootstyle(app):
    """Buttons must use our own ttk styles, not the bootstyle option."""
    for kind in ("primary", "success", "warning", "danger", "outline"):
        options = app.btn(kind)
        assert "bootstyle" not in options
        assert options["style"].endswith(".TButton")


def test_all_registered_button_styles_are_usable(app):
    """Every declared style must apply to a real ttk.Button."""
    from tkinter import ttk

    for kind in ("primary", "success", "warning", "danger", "outline", "unknown"):
        widget = ttk.Button(app.root, text="x", **app.btn(kind))
        widget.destroy()


# ---------------------------------------------------------------------------
# Full flow
# ---------------------------------------------------------------------------

def _run_workers(app, timeout=15.0):
    """Wait for the worker to finish, draining the UI queue as the mainloop would."""
    import time

    deadline = time.time() + timeout
    while app._busy() and time.time() < deadline:
        app.root.update()
        time.sleep(0.01)
    # A few final rounds to apply the updates queued by the worker.
    for _ in range(5):
        app.root.update()
        time.sleep(0.02)
    assert not app._busy(), "The worker did not finish within the timeout"


def _drain_ui(app, seconds=0.5):
    """
    Let the UI queue drain. Entries are applied by an after(80ms) tick, so a
    single root.update() is not enough to see them.
    """
    import time

    deadline = time.time() + seconds
    while time.time() < deadline:
        app.root.update()
        time.sleep(0.02)


def test_scan_match_and_replace_flow(app, tmp_path, monkeypatch):
    scan = tmp_path / "share"
    source = tmp_path / "nuovi"
    make_image(scan / "sito" / "logo_a.png", (200, 60), (255, 0, 0))
    make_image(scan / "sito" / "logo_b.png", (100, 30), (255, 0, 0))
    make_image(scan / "sito" / "foto.png", (100, 30), (255, 0, 0))   # fuori pattern
    make_image(source / "logo_a.png", (200, 60), (0, 0, 255))
    make_image(source / "logo_b.png", (100, 30), (0, 0, 255))

    app.source_folder.set(str(source))
    app.scan_folder.set(str(scan))
    app.search_pattern.set("logo*.png")

    monkeypatch.setattr("tkinter.messagebox.showinfo", lambda *a, **k: None)
    monkeypatch.setattr("tkinter.messagebox.showwarning", lambda *a, **k: None)
    monkeypatch.setattr("tkinter.messagebox.askyesno", lambda *a, **k: True)

    app._start_scan()
    _run_workers(app)
    assert len(app.scanned_files) == 2
    assert len(app._scan_tree.get_children()) == 2

    app._start_matching()
    _run_workers(app)
    assert len(app.matches) == 2
    assert all(m.source is not None for m in app.matches)
    assert len(app._match_tree.get_children()) == 2

    app._dry_run_var.set(False)
    app._backup_var.set(True)
    app._execute_replacement()
    _run_workers(app)

    assert Image.open(scan / "sito" / "logo_a.png").getpixel((0, 0)) == (0, 0, 255)
    assert os.path.exists(str(scan / "sito" / "logo_a.png") + ".bak")


def test_dry_run_leaves_files_untouched(app, tmp_path, monkeypatch):
    scan = tmp_path / "share"
    source = tmp_path / "nuovi"
    target = make_image(scan / "logo.png", (200, 60), (255, 0, 0))
    make_image(source / "logo.png", (200, 60), (0, 0, 255))

    app.source_folder.set(str(source))
    app.scan_folder.set(str(scan))
    app.search_pattern.set("logo*.png")

    monkeypatch.setattr("tkinter.messagebox.showinfo", lambda *a, **k: None)
    monkeypatch.setattr("tkinter.messagebox.askyesno", lambda *a, **k: True)

    app._start_scan()
    _run_workers(app)
    app._start_matching()
    _run_workers(app)

    app._dry_run_var.set(True)
    app._execute_replacement()
    _run_workers(app)

    assert Image.open(target).getpixel((0, 0)) == (255, 0, 0)
    assert not os.path.exists(target + ".bak")


def test_nested_source_folder_is_not_a_target(app, tmp_path, monkeypatch):
    """New logos inside the scanned folder must not be replaced."""
    scan = tmp_path / "share"
    source = scan / "nuovi_loghi"
    make_image(scan / "sito" / "logo.png", (200, 60), (255, 0, 0))
    make_image(source / "logo.png", (200, 60), (0, 0, 255))

    app.source_folder.set(str(source))
    app.scan_folder.set(str(scan))
    app.search_pattern.set("logo*.png")
    monkeypatch.setattr("tkinter.messagebox.showinfo", lambda *a, **k: None)

    app._start_scan()
    _run_workers(app)

    assert len(app.scanned_files) == 1
    assert "nuovi_loghi" not in app.scanned_files[0].path


def test_thumbnails_are_never_finalized_off_the_main_thread(app, tmp_path, monkeypatch):
    """
    Regression for the interface freeze.

    ImageTk.PhotoImage's destructor calls into Tk. When the cyclic garbage
    collector ran it while executing on a worker thread, that call into Tk from
    outside the main thread hung the application halfway through a scan.
    """
    import gc

    scan = tmp_path / "share"
    source = tmp_path / "nuovi"
    for i in range(4):
        make_image(scan / f"logo_{i}.png", (60 + i, 40))
        make_image(source / f"logo_{i}.png", (60 + i, 40))

    app.source_folder.set(str(source))
    app.scan_folder.set(str(scan))
    app.search_pattern.set("logo*.png")

    app._start_scan()
    _run_workers(app)

    # Create thumbnails (hence potential cyclic Tk garbage) the way a user
    # browsing previews before starting the analysis would.
    for row in app._scan_tree.get_children():
        app._scan_tree.selection_set(row)
        app.root.update()
    assert app._image_refs, "thumbnails must be retained by the app"

    collected_on = []
    real_collect = gc.collect

    def tracking_collect(*args):
        collected_on.append(threading.current_thread().name)
        return real_collect(*args)

    monkeypatch.setattr(gc, "collect", tracking_collect)

    app._start_matching()
    assert not gc.isenabled(), "the collector must be paused while the worker runs"
    _run_workers(app)

    assert gc.isenabled(), "the collector must be resumed when the operation ends"
    assert collected_on, "garbage must be collected explicitly"
    assert set(collected_on) == {"MainThread"}
    assert len(app.matches) == 4


def test_clear_previews_releases_image_references(app, tmp_path, monkeypatch):
    """On Windows a thumbnail still open prevents overwriting the file."""
    scan = tmp_path / "share"
    make_image(scan / "logo.png")
    app.source_folder.set(str(tmp_path / "nuovi"))
    os.makedirs(tmp_path / "nuovi", exist_ok=True)
    make_image(tmp_path / "nuovi" / "logo.png")
    app.scan_folder.set(str(scan))
    app.search_pattern.set("logo*.png")

    app._start_scan()
    _run_workers(app)
    app._scan_tree.selection_set(app._scan_tree.get_children()[0])
    app.root.update()
    assert app._image_refs

    app._clear_previews()
    assert app._image_refs == {}


# ---------------------------------------------------------------------------
# Match table interaction
# ---------------------------------------------------------------------------

def _prepare_matches(app, tmp_path, monkeypatch, count=3):
    scan = tmp_path / "share"
    source = tmp_path / "nuovi"
    for i in range(count):
        make_image(scan / f"logo_{i}.png", (100 + i, 50))
        make_image(source / f"logo_{i}.png", (100 + i, 50))

    app.source_folder.set(str(source))
    app.scan_folder.set(str(scan))
    app.search_pattern.set("logo*.png")
    monkeypatch.setattr("tkinter.messagebox.showinfo", lambda *a, **k: None)

    app._start_scan()
    _run_workers(app)
    app._start_matching()
    _run_workers(app)
    return app.matches


def test_toggle_only_affects_the_checkbox_column(app, tmp_path, monkeypatch):
    """
    Regression: any click inverted the row, making it impossible to select one
    just to look at its preview.
    """
    matches = _prepare_matches(app, tmp_path, monkeypatch, count=1)
    row_id = matches[0].target.path
    assert matches[0].enabled

    class Event:
        x = y = 5

    monkeypatch.setattr(app._match_tree, "identify_region", lambda x, y: "cell")
    monkeypatch.setattr(app._match_tree, "identify_row", lambda y: row_id)

    monkeypatch.setattr(app._match_tree, "identify_column", lambda x: "#3")
    app._on_match_click(Event())
    assert matches[0].enabled, "a click outside the ✓ column must not invert the row"

    monkeypatch.setattr(app._match_tree, "identify_column", lambda x: "#2")
    app._on_match_click(Event())
    assert not matches[0].enabled
    assert app._match_tree.set(row_id, "chk") == "✗"


def test_select_and_deselect_all(app, tmp_path, monkeypatch):
    matches = _prepare_matches(app, tmp_path, monkeypatch)
    app._deselect_all_matches()
    assert not any(m.enabled for m in matches)
    assert app._enabled_matches() == []

    app._select_all_matches()
    assert all(m.enabled for m in matches)
    assert len(app._enabled_matches()) == len(matches)


def test_sorting_is_numeric_and_toggles(app, tmp_path, monkeypatch):
    """Sorted as text, «10» came before «2»."""
    _prepare_matches(app, tmp_path, monkeypatch, count=12)
    tree = app._match_tree

    app._sort_tree(tree, "#")
    ascending = [int(tree.set(i, "#")) for i in tree.get_children("")]
    assert ascending == sorted(ascending)

    app._sort_tree(tree, "#")
    descending = [int(tree.set(i, "#")) for i in tree.get_children("")]
    assert descending == sorted(descending, reverse=True)


def test_size_column_sorts_by_real_magnitude(app):
    """«2.0 MB» must outrank «900.0 KB», which would lose as plain text."""
    assert app._numeric_prefix("2.0 MB") > app._numeric_prefix("900.0 KB")
    assert app._numeric_prefix("1.0 GB") > app._numeric_prefix("999.0 MB")
    assert app._numeric_prefix("800×600 px") > app._numeric_prefix("100×100 px")
    assert app._numeric_prefix("N/A") == -1.0


def _find_widget(parent, cls, text=None):
    """Recursively find the first widget of the given type (and optional text)."""
    for child in parent.winfo_children():
        if isinstance(child, cls):
            if text is None or str(child.cget("text")) == text:
                return child
        found = _find_widget(child, cls, text)
        if found is not None:
            return found
    return None


def test_manual_source_override_through_dialog(app, tmp_path, monkeypatch):
    """Double-clicking a row allows choosing a different source."""
    from tkinter import ttk

    matches = _prepare_matches(app, tmp_path, monkeypatch, count=3)
    match = matches[0]
    original_source = match.source.path

    dialog = app._choose_source_dialog(match.target.path)
    assert dialog is not None
    app.root.update()

    listbox = _find_widget(dialog, tk.Listbox)
    assert listbox is not None and listbox.size() == len(app.source_files)

    # The first entry is the best candidate: pick a different one.
    listbox.selection_clear(0, tk.END)
    listbox.selection_set(1)
    _find_widget(dialog, ttk.Button, "Confirm").invoke()
    app.root.update()

    assert match.manual is True
    assert match.enabled is True
    assert match.source.path != original_source
    assert app._match_tree.set(match.target.path, "quality") == "Manual"
    assert app._match_tree.set(match.target.path, "src_name") == match.source.name


def test_choose_source_dialog_cancel_leaves_match_untouched(app, tmp_path, monkeypatch):
    from tkinter import ttk

    matches = _prepare_matches(app, tmp_path, monkeypatch, count=2)
    match = matches[0]
    original = match.source.path

    dialog = app._choose_source_dialog(match.target.path)
    app.root.update()
    _find_widget(dialog, ttk.Button, "Cancel").invoke()
    app.root.update()

    assert match.source.path == original
    assert match.manual is False


# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------

def test_restore_backups_undoes_a_campaign(app, tmp_path, monkeypatch):
    scan = tmp_path / "share"
    source = tmp_path / "nuovi"
    target = make_image(scan / "logo.png", (200, 60), (255, 0, 0))
    make_image(source / "logo.png", (200, 60), (0, 0, 255))

    app.source_folder.set(str(source))
    app.scan_folder.set(str(scan))
    app.search_pattern.set("logo*.png")
    monkeypatch.setattr("tkinter.messagebox.askyesno", lambda *a, **k: True)

    app._start_scan()
    _run_workers(app)
    app._start_matching()
    _run_workers(app)
    app._dry_run_var.set(False)
    app._backup_var.set(True)
    app._execute_replacement()
    _run_workers(app)
    assert Image.open(target).getpixel((0, 0)) == (0, 0, 255)

    app._restore_backups()
    _run_workers(app)
    assert Image.open(target).getpixel((0, 0)) == (255, 0, 0)


def test_restore_without_backups_reports_nothing_to_do(app, tmp_path, monkeypatch):
    scan = tmp_path / "share"
    make_image(scan / "logo.png")
    app.scan_folder.set(str(scan))

    seen = {}
    monkeypatch.setattr("tkinter.messagebox.showinfo",
                        lambda title, msg, *a, **k: seen.update(title=title))
    app._restore_backups()
    assert seen.get("title") == "No backup"
    assert not app._busy()


# ---------------------------------------------------------------------------
# Summary and shutdown
# ---------------------------------------------------------------------------

def test_replace_summary_warns_when_backup_is_off(app, tmp_path, monkeypatch):
    _prepare_matches(app, tmp_path, monkeypatch, count=2)

    app._dry_run_var.set(False)
    app._backup_var.set(True)
    app._refresh_replace_summary()
    assert ".bak" in app._replace_summary_lbl.cget("text")

    app._backup_var.set(False)
    app._refresh_replace_summary()
    assert "permanently" in app._replace_summary_lbl.cget("text").lower()

    app._dry_run_var.set(True)
    app._refresh_replace_summary()
    assert "DRY RUN" in app._replace_summary_lbl.cget("text")


def test_summary_refreshes_when_switching_to_tab_four(app, tmp_path, monkeypatch):
    """Reaching tab ④ from the tab strip left the summary stale."""
    _prepare_matches(app, tmp_path, monkeypatch, count=2)
    app.notebook.select(3)
    app.root.update()
    assert "2 of 2" in app._replace_summary_lbl.cget("text")

    app._deselect_all_matches()
    app.notebook.select(0)
    app.notebook.select(3)
    app.root.update()
    assert "No replacement" in app._replace_summary_lbl.cget("text")


def test_settings_are_persisted_on_close(app, tmp_path, monkeypatch):
    app.source_folder.set(str(tmp_path / "src"))
    app.search_pattern.set("banner_*.jpg")
    app._backup_var.set(False)
    app._save_settings()

    assert core.load_settings()["search_pattern"] == "banner_*.jpg"
    assert core.load_settings()["backup"] is False


# ---------------------------------------------------------------------------
# Language switching
# ---------------------------------------------------------------------------

def test_language_switch_retranslates_the_interface(app):
    import i18n

    assert app.notebook.tab(0, "text") == "  ① CONFIGURATION  "
    assert app.status_label.cget("text") == "Ready"

    app._change_language("it")

    assert i18n.get_language() == "it"
    assert app.notebook.tab(0, "text") == "  ① CONFIGURAZIONE  "
    assert app._btn_scan.cget("text") == "🔍  AVVIA SCANSIONE"
    assert app._scan_tree.heading("name")["text"] == "Nome File"
    assert app._match_tree.heading("quality")["text"] == "Qualità"


def test_language_switch_keeps_data_and_repopulates_tables(app, tmp_path, monkeypatch):
    """Switching language rebuilds the widgets: the results must survive."""
    matches = _prepare_matches(app, tmp_path, monkeypatch, count=3)
    app._deselect_all_matches()
    matches[0].enabled = True
    app._refresh_match_row(matches[0])

    app.notebook.select(2)
    app.root.update()

    app._change_language("it")
    app.root.update()

    assert len(app.scanned_files) == 3
    assert len(app._scan_tree.get_children()) == 3
    assert len(app._match_tree.get_children()) == 3
    # The selection state is data, not presentation: it must not be lost.
    assert len(app._enabled_matches()) == 1
    assert app.notebook.index("current") == 2
    assert app._match_tree.set(matches[0].target.path, "quality") == "Ottima"


def test_language_switch_preserves_the_log(app):
    app.log("a distinctive log line")
    _drain_ui(app)
    assert "a distinctive log line" in app.log_text.get("1.0", tk.END)

    app._change_language("it")
    _drain_ui(app)
    assert "a distinctive log line" in app.log_text.get("1.0", tk.END)


def test_language_settings_survive_a_restart(app, tmp_path, monkeypatch):
    app._change_language("it")
    assert core.load_settings()["language"] == "it"


def test_language_switch_is_refused_while_busy(app, tmp_path, monkeypatch):
    """
    Rebuilding mid-operation would destroy the widgets the worker's queued
    callbacks are about to touch.
    """
    import i18n

    scan = tmp_path / "share"
    source = tmp_path / "nuovi"
    for i in range(3):
        make_image(scan / f"logo_{i}.png")
        make_image(source / f"logo_{i}.png")
    app.source_folder.set(str(source))
    app.scan_folder.set(str(scan))
    app.search_pattern.set("logo*.png")

    seen = {}
    monkeypatch.setattr("tkinter.messagebox.showinfo",
                        lambda title, msg, *a, **k: seen.update(title=title))

    app._start_scan()
    app._change_language("it")          # while the worker is running
    assert i18n.get_language() == "en"
    assert seen.get("title") == "Operation in progress"
    # The combobox must snap back to the language actually in use.
    assert app._language_var.get() == "English"

    _run_workers(app)
    app._change_language("it")          # now it is allowed
    assert i18n.get_language() == "it"


def test_closing_stops_the_ui_pump(app, monkeypatch):
    """
    The after() loop kept running after the window was destroyed, raising a
    background Tcl error.

    `destroy` is stubbed out because the interpreter is shared with the rest of
    the session; everything else runs for real.
    """
    import gc

    destroyed = []
    monkeypatch.setattr(app.root, "destroy", lambda: destroyed.append(True))

    assert app._pump_after_id is not None
    app._on_close()

    assert destroyed == [True]
    assert app._closing is True
    assert app._pump_after_id is None, "the pending tick must be cancelled"
    assert gc.isenabled(), "the collector must never be left paused on exit"

    # A later pump must return immediately instead of rescheduling itself.
    app._pump_ui_queue()
    assert app._pump_after_id is None


# ---------------------------------------------------------------------------
# Content search
# ---------------------------------------------------------------------------

def _logo(path, size=(240, 80), colour=(196, 62, 58)):
    """A mark with enough structure to hash consistently."""
    from PIL import ImageDraw

    path = str(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    image = Image.new("RGB", size, (255, 255, 255))
    draw = ImageDraw.Draw(image)
    w, h = size
    draw.ellipse((w * 0.04, h * 0.15, w * 0.32, h * 0.85), fill=colour)
    draw.rectangle((w * 0.38, h * 0.30, w * 0.94, h * 0.48), fill=colour)
    draw.rectangle((w * 0.38, h * 0.56, w * 0.72, h * 0.72), fill=(90, 90, 90))
    image.save(path)
    return path


def test_search_mode_toggles_the_relevant_controls(app):
    assert app._searching_by_content() is False
    assert str(app._btn_references.cget("state")) == "disabled"

    app._search_mode.set("content")
    app._on_search_mode_changed()

    assert app._searching_by_content() is True
    assert str(app._btn_references.cget("state")) == "normal"
    assert str(app._similarity_spin.cget("state")) == "normal"


def test_content_search_finds_logos_no_pattern_would_catch(app, tmp_path, monkeypatch):
    """The feature's whole point, exercised through the real interface."""
    scan = tmp_path / "share"
    source = tmp_path / "new_logos"
    _logo(scan / "web" / "header_bg.png", (240, 80))     # hidden under a bland name
    _logo(scan / "docs" / "img_04.jpg", (120, 40))       # and another
    make_image(scan / "docs" / "chart.png", (100, 100))  # unrelated: must not match
    _logo(source / "brand.png", (240, 80), (20, 90, 170))
    reference = _logo(tmp_path / "ref" / "old_logo.png")

    app.source_folder.set(str(source))
    app.scan_folder.set(str(scan))
    app.search_pattern.set("")
    app._search_mode.set("content")
    app._references = [reference]
    app._on_search_mode_changed()
    monkeypatch.setattr("tkinter.messagebox.showinfo", lambda *a, **k: None)

    app._start_scan()
    _run_workers(app)

    found = sorted(f.name for f in app.scanned_files)
    assert found == ["header_bg.png", "img_04.jpg"]
    assert all(f.similarity is not None for f in app.scanned_files)
    # And a name-based search would have found nothing at all.
    assert core.scan_files(str(scan), "logo*") == []


def test_scan_tree_shows_similarity_and_flags_uncertain_rows(app, tmp_path, monkeypatch):
    scan = tmp_path / "share"
    source = tmp_path / "new_logos"
    target = _logo(scan / "header_bg.png")
    _logo(source / "brand.png", colour=(20, 90, 170))
    reference = _logo(tmp_path / "ref.png")

    app.source_folder.set(str(source))
    app.scan_folder.set(str(scan))
    app.search_pattern.set("")
    app._search_mode.set("content")
    app._references = [reference]
    monkeypatch.setattr("tkinter.messagebox.showinfo", lambda *a, **k: None)

    app._start_scan()
    _run_workers(app)

    assert app._scan_tree.set(target, "sim") == "100%"
    assert "review" not in app._scan_tree.item(target, "tags")

    # An uncertain hit must be coloured, because it is the one case where the
    # tool could overwrite an unrelated image.
    app.scanned_files[0].similarity = 0.91
    app._populate_scan_tree(announce=False)
    assert "review" in app._scan_tree.item(target, "tags")


def test_content_search_requires_a_reference_image(app, tmp_path, monkeypatch):
    scan = tmp_path / "share"
    source = tmp_path / "new_logos"
    make_image(scan / "a.png")
    make_image(source / "a.png")

    app.source_folder.set(str(source))
    app.scan_folder.set(str(scan))
    app._search_mode.set("content")
    app._references = []

    shown = {}
    monkeypatch.setattr("tkinter.messagebox.showerror",
                        lambda title, msg, *a, **k: shown.update(msg=msg))
    app._start_scan()

    assert "reference image" in shown.get("msg", "")
    assert not app._busy(), "the scan must not start without a reference"


def test_empty_pattern_is_allowed_only_in_content_mode(app, tmp_path, monkeypatch):
    """In content search an empty pattern legitimately means "every image"."""
    scan = tmp_path / "share"
    source = tmp_path / "new_logos"
    make_image(scan / "a.png")
    make_image(source / "a.png")
    reference = _logo(tmp_path / "ref.png")

    app.source_folder.set(str(source))
    app.scan_folder.set(str(scan))
    app.search_pattern.set("")

    shown = {}
    monkeypatch.setattr("tkinter.messagebox.showerror",
                        lambda title, msg, *a, **k: shown.update(msg=msg))
    monkeypatch.setattr("tkinter.messagebox.showinfo", lambda *a, **k: None)

    app._search_mode.set("name")
    app._start_scan()
    assert shown.get("msg"), "an empty pattern must be rejected in name mode"

    shown.clear()
    app._search_mode.set("content")
    app._references = [reference]
    app._start_scan()
    _run_workers(app)
    assert not shown, "an empty pattern is valid in content mode"


def test_reference_selection_is_persisted(app, tmp_path):
    reference = _logo(tmp_path / "ref.png")
    app._search_mode.set("content")
    app._references = [reference]
    app._similarity_var.set(93)
    app._save_settings()

    stored = core.load_settings()
    assert stored["search_mode"] == "content"
    assert stored["references"] == [reference]
    assert stored["similarity"] == 93


def test_references_label_summarises_the_selection(app, tmp_path):
    app._references = []
    app._refresh_references_label()
    assert "No reference" in app._references_label.cget("text")

    app._references = [_logo(tmp_path / f"r{i}.png") for i in range(5)]
    app._refresh_references_label()
    text = app._references_label.cget("text")
    assert text.startswith("5 chosen:")
    assert text.endswith("...")


# ---------------------------------------------------------------------------
# Office documents
# ---------------------------------------------------------------------------

def test_office_documents_flow_through_the_whole_wizard(app, tmp_path, monkeypatch):
    """Scan, match and replace a logo living inside a .docx, via the real UI."""
    docx = pytest.importorskip("docx", reason="python-docx is needed")
    from PIL import ImageDraw

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

    scan = tmp_path / "share"
    source = tmp_path / "new_logos"
    old = mark(tmp_path / "brand" / "old.png")
    mark(source / "brand.png", colour=(20, 90, 170))

    document = docx.Document()
    document.add_picture(old)
    os.makedirs(str(scan), exist_ok=True)
    doc_path = str(scan / "report.docx")
    document.save(doc_path)

    app.source_folder.set(str(source))
    app.scan_folder.set(str(scan))
    app.search_pattern.set("logo*.png")      # matches nothing on disk
    app._include_office.set(True)
    monkeypatch.setattr("tkinter.messagebox.showinfo", lambda *a, **k: None)
    monkeypatch.setattr("tkinter.messagebox.showwarning", lambda *a, **k: None)
    monkeypatch.setattr("tkinter.messagebox.askyesno", lambda *a, **k: True)

    app._start_scan()
    _run_workers(app)

    assert len(app.scanned_files) == 1
    found = app.scanned_files[0]
    assert found.embedded and found.container == doc_path
    assert found.dim == (240, 80)

    # The preview must reach inside the package.
    app._scan_tree.selection_set(found.path)
    app.root.update()
    assert "scan" in app._image_refs, "an embedded picture must still preview"

    app._start_matching()
    _run_workers(app)
    assert app.matches[0].source is not None

    app._dry_run_var.set(False)
    app._backup_var.set(True)
    app._execute_replacement()
    _run_workers(app)

    import office
    entry = office.list_images(doc_path)[0].entry
    temp = office.extract_to_temp(doc_path, entry)
    try:
        assert Image.open(temp).convert("RGB").getpixel((60, 40)) == (20, 90, 170)
    finally:
        os.remove(temp)
    assert os.path.exists(doc_path + ".bak")


def test_a_distorting_replacement_is_flagged(app, tmp_path):
    """A square logo bound for a 3:1 frame must be called out, not silently applied."""
    import office

    target = core.FileInfo(path="r.docx!/word/media/image1.png", name="image1.png",
                           ext=".png", size=100, dim=(240, 80),
                           container="r.docx", entry="word/media/image1.png")
    square = core.FileInfo(path="s.png", name="s.png", ext=".png",
                           size=100, dim=(200, 200))
    same = core.FileInfo(path="w.png", name="w.png", ext=".png",
                         size=100, dim=(480, 160))

    assert core.Match(target=target, source=square, enabled=True).distorts is True
    assert core.Match(target=target, source=same, enabled=True).distorts is False

    app.matches = [core.Match(target=target, source=square, enabled=True)]
    app._match_by_path = {target.path: app.matches[0]}
    assert app._row_tag(app.matches[0]) == "weak"

    app._refresh_replace_summary()
    assert "stretch" in app._replace_summary_lbl.cget("text")
    assert office.aspect_mismatch((240, 80), (200, 200))
