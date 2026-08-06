#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test dell'interfaccia grafica.

Girano headless (Xvfb su Linux, nativamente su Windows) e vengono saltati
automaticamente dove non esiste un display.
"""

from __future__ import annotations

import os
import threading
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

tk = pytest.importorskip("tkinter", reason="tkinter non disponibile")
pytest.importorskip("PIL", reason="Pillow necessario per le anteprime")

from PIL import Image  # noqa: E402

import core  # noqa: E402


def _display_available() -> bool:
    if os.name == "nt" or sys.platform == "darwin":
        return True
    return bool(os.environ.get("DISPLAY"))


pytestmark = pytest.mark.skipif(
    not _display_available(), reason="Nessun display disponibile (usa xvfb-run)"
)


@pytest.fixture
def app(tmp_path, monkeypatch):
    """Istanza dell'applicazione isolata dalle impostazioni dell'utente reale."""
    monkeypatch.setattr(core, "writable_app_dir", lambda sub: str(tmp_path / sub))
    os.makedirs(tmp_path / "config", exist_ok=True)
    os.makedirs(tmp_path / "logs", exist_ok=True)

    from rebranding_tool import RebrandingToolApp

    root = tk.Tk()
    root.withdraw()
    instance = RebrandingToolApp(root)
    root.update()
    yield instance

    # Chiusura come quella reale: annulla il tick della coda UI, altrimenti
    # l'after() pendente si ripresenta durante il test successivo.
    instance._worker = None
    try:
        instance._on_close()
    except tk.TclError:
        pass
    tk._default_root = None


def make_image(path, size=(100, 50), color=(255, 0, 0), fmt=None):
    path = str(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new("RGB", size, color).save(path, format=fmt)
    return path


# ---------------------------------------------------------------------------
# Avvio
# ---------------------------------------------------------------------------

def test_app_starts_with_all_tabs(app):
    """Regressione: con ttkbootstrap 2.x l'avvio falliva con TclError."""
    assert len(app.notebook.tabs()) == 4


def test_progressbar_widget_exists_and_is_bound(app):
    """La progressbar esisteva solo come variabile, senza widget associato."""
    assert app._progress is not None
    assert str(app._progress.cget("variable")) == str(app.progress_var)
    app.progress_var.set(42)
    assert app._progress["value"] == pytest.approx(42)


def test_progressbar_is_actually_visible(app):
    """
    Regressione: con i colori di default la barra veniva disegnata bianca su
    fondo bianco, quindi l'avanzamento era invisibile pur essendo corretto.
    """
    style = app.style.configure("Sace.Horizontal.TProgressbar") or {}
    from rebranding_tool import PROGRESS_STYLE, SACE_BLUE

    assert str(app._progress.cget("style")) == PROGRESS_STYLE
    assert style.get("background") == SACE_BLUE
    assert style.get("troughcolor") != style.get("background")


def test_button_styles_do_not_use_bootstyle(app):
    """I pulsanti devono usare stili ttk nostri, non l'opzione bootstyle."""
    for kind in ("primary", "success", "warning", "danger", "outline"):
        options = app.btn(kind)
        assert "bootstyle" not in options
        assert options["style"].endswith(".TButton")


def test_all_registered_button_styles_are_usable(app):
    """Ogni stile dichiarato deve essere applicabile a un ttk.Button reale."""
    from tkinter import ttk

    for kind in ("primary", "success", "warning", "danger", "outline", "sconosciuto"):
        widget = ttk.Button(app.root, text="x", **app.btn(kind))
        widget.destroy()


# ---------------------------------------------------------------------------
# Flusso completo
# ---------------------------------------------------------------------------

def _run_workers(app, timeout=15.0):
    """Attende la fine del worker svuotando la coda UI, come farebbe il mainloop."""
    import time

    deadline = time.time() + timeout
    while app._busy() and time.time() < deadline:
        app.root.update()
        time.sleep(0.01)
    # Ultimi giri per applicare gli aggiornamenti accodati dal worker.
    for _ in range(5):
        app.root.update()
        time.sleep(0.02)
    assert not app._busy(), "Il worker non è terminato entro il timeout"


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
    """I nuovi loghi dentro la cartella scansionata non vanno sostituiti."""
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
    Regressione del blocco dell'interfaccia.

    Il distruttore di ImageTk.PhotoImage chiama Tk. Se il garbage collector
    ciclico lo eseguiva mentre girava su un thread di lavoro, la chiamata a
    Tk fuori dal thread principale piantava l'applicazione a metà scansione.
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

    # Genera miniature (e quindi potenziale spazzatura ciclica Tk) come
    # farebbe un utente che sfoglia le anteprime prima di lanciare l'analisi.
    for row in app._scan_tree.get_children():
        app._scan_tree.selection_set(row)
        app.root.update()
    assert app._image_refs, "le miniature devono essere trattenute dall'app"

    collected_on = []
    real_collect = gc.collect

    def tracking_collect(*args):
        collected_on.append(threading.current_thread().name)
        return real_collect(*args)

    monkeypatch.setattr(gc, "collect", tracking_collect)

    app._start_matching()
    assert not gc.isenabled(), "il collector va sospeso mentre il worker lavora"
    _run_workers(app)

    assert gc.isenabled(), "il collector va riattivato a fine operazione"
    assert collected_on, "la spazzatura va raccolta esplicitamente"
    assert set(collected_on) == {"MainThread"}
    assert len(app.matches) == 4


def test_clear_previews_releases_image_references(app, tmp_path, monkeypatch):
    """Su Windows una miniatura ancora aperta impedisce di sovrascrivere il file."""
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
# Interazione con la tabella corrispondenze
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
    Regressione: qualunque clic invertiva la riga, rendendo impossibile
    selezionarla per vederne l'anteprima.
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
    assert matches[0].enabled, "un clic fuori dalla colonna ✓ non deve invertire la riga"

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
    """Ordinando come testo «10» finiva prima di «2»."""
    _prepare_matches(app, tmp_path, monkeypatch, count=12)
    tree = app._match_tree

    app._sort_tree(tree, "#")
    ascending = [int(tree.set(i, "#")) for i in tree.get_children("")]
    assert ascending == sorted(ascending)

    app._sort_tree(tree, "#")
    descending = [int(tree.set(i, "#")) for i in tree.get_children("")]
    assert descending == sorted(descending, reverse=True)


def test_size_column_sorts_by_real_magnitude(app):
    """«2.0 MB» deve valere più di «900.0 KB», che come testo perderebbe."""
    assert app._numeric_prefix("2.0 MB") > app._numeric_prefix("900.0 KB")
    assert app._numeric_prefix("1.0 GB") > app._numeric_prefix("999.0 MB")
    assert app._numeric_prefix("800×600 px") > app._numeric_prefix("100×100 px")
    assert app._numeric_prefix("N/D") == -1.0


def _find_widget(parent, cls, text=None):
    """Cerca ricorsivamente il primo widget del tipo (ed eventuale testo) dato."""
    for child in parent.winfo_children():
        if isinstance(child, cls):
            if text is None or str(child.cget("text")) == text:
                return child
        found = _find_widget(child, cls, text)
        if found is not None:
            return found
    return None


def test_manual_source_override_through_dialog(app, tmp_path, monkeypatch):
    """Doppio clic su una riga permette di scegliere un sorgente diverso."""
    from tkinter import ttk

    matches = _prepare_matches(app, tmp_path, monkeypatch, count=3)
    match = matches[0]
    original_source = match.source.path

    dialog = app._choose_source_dialog(match.target.path)
    assert dialog is not None
    app.root.update()

    listbox = _find_widget(dialog, tk.Listbox)
    assert listbox is not None and listbox.size() == len(app.source_files)

    # La prima voce è il candidato migliore: ne scegliamo un altro.
    listbox.selection_clear(0, tk.END)
    listbox.selection_set(1)
    _find_widget(dialog, ttk.Button, "Conferma").invoke()
    app.root.update()

    assert match.manual is True
    assert match.enabled is True
    assert match.source.path != original_source
    assert app._match_tree.set(match.target.path, "quality") == "Manuale"
    assert app._match_tree.set(match.target.path, "src_name") == match.source.name


def test_choose_source_dialog_cancel_leaves_match_untouched(app, tmp_path, monkeypatch):
    from tkinter import ttk

    matches = _prepare_matches(app, tmp_path, monkeypatch, count=2)
    match = matches[0]
    original = match.source.path

    dialog = app._choose_source_dialog(match.target.path)
    app.root.update()
    _find_widget(dialog, ttk.Button, "Annulla").invoke()
    app.root.update()

    assert match.source.path == original
    assert match.manual is False


# ---------------------------------------------------------------------------
# Ripristino
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
    assert seen.get("title") == "Nessun backup"
    assert not app._busy()


# ---------------------------------------------------------------------------
# Riepilogo e chiusura
# ---------------------------------------------------------------------------

def test_replace_summary_warns_when_backup_is_off(app, tmp_path, monkeypatch):
    _prepare_matches(app, tmp_path, monkeypatch, count=2)

    app._dry_run_var.set(False)
    app._backup_var.set(True)
    app._refresh_replace_summary()
    assert ".bak" in app._replace_summary_lbl.cget("text")

    app._backup_var.set(False)
    app._refresh_replace_summary()
    assert "definitivamente" in app._replace_summary_lbl.cget("text").lower()

    app._dry_run_var.set(True)
    app._refresh_replace_summary()
    assert "SIMULAZIONE" in app._replace_summary_lbl.cget("text")


def test_summary_refreshes_when_switching_to_tab_four(app, tmp_path, monkeypatch):
    """Arrivando al tab ④ dalla barra dei tab il riepilogo era stantio."""
    _prepare_matches(app, tmp_path, monkeypatch, count=2)
    app.notebook.select(3)
    app.root.update()
    assert "2 file" in app._replace_summary_lbl.cget("text")

    app._deselect_all_matches()
    app.notebook.select(0)
    app.notebook.select(3)
    app.root.update()
    assert "Nessuna sostituzione" in app._replace_summary_lbl.cget("text")


def test_settings_are_persisted_on_close(app, tmp_path, monkeypatch):
    app.source_folder.set(str(tmp_path / "src"))
    app.search_pattern.set("banner_*.jpg")
    app._backup_var.set(False)
    app._save_settings()

    assert core.load_settings()["search_pattern"] == "banner_*.jpg"
    assert core.load_settings()["backup"] is False


def test_closing_stops_the_ui_pump(app):
    """Il ciclo after() continuava a girare dopo la distruzione della finestra."""
    app._on_close()
    assert app._closing is True
    # Un pump successivo deve uscire subito senza sollevare TclError.
    app._pump_ui_queue()
