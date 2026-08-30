# Proteus — Rebranding Tool
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.
# A commercial licence, without the AGPL's obligations, is available for use
# in proprietary or closed-source products — see COMMERCIAL-LICENSE.md.

"""What must and must not end up inside a built bundle.

There is one thing in here, and it is not about size.

PyInstaller collects the standard library's optional ``readline`` extension by
default. It links ``libreadline``, which is **GPL-3.0-or-later with no linking
exception** — so every Linux archive Proteus has published contains a GPL-3
library, inside an archive COMMERCIAL-LICENSE.md offers for redistribution in
closed-source products. That is the one combination the commercial tier cannot
survive, and it arrived by default rather than by decision.

``libpython`` does not link it; only that module does. Nothing in Proteus
reads a line from an interactive prompt. So it is excluded — and pinned here,
because an exclusion nobody checks is an exclusion that comes back the next
time somebody regenerates a spec file.
"""

import pathlib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


#: The module each of these products keeps its interface constants in.
UI_MODULE = "rebranding_tool.py"


def _assigned(name: str, path: str = None):
    """The AST node a module-level constant is assigned, without importing it.

    These constants are declarations — the theme order, the font order, the
    button styles — and their whole job is to be identical across the four
    products. Reading them by ``import`` made that check depend on Tk being
    installed, so on a machine without the toolkit the comparison did not fail:
    it errored, next to four neighbours in the same file that skip cleanly for
    the same reason. Neither is what a declaration deserves. Parsed from the
    source, it is checked everywhere, with no toolkit and no window.
    """
    import ast

    source = (REPO / (path or UI_MODULE)).read_text(encoding="utf-8")
    for node in ast.parse(source).body:
        targets = getattr(node, "targets", [])
        if any(isinstance(t, ast.Name) and t.id == name for t in targets):
            return node.value
    raise AssertionError(f"{name} is not assigned at the top level of {path or UI_MODULE}")


def declared(name: str):
    """The literal value of a module-level constant."""
    import ast

    return ast.literal_eval(_assigned(name))


def declared_keys(name: str) -> set:
    """The keys of a module-level dict whose values need not be literals."""
    import ast

    return {ast.literal_eval(key) for key in _assigned(name).keys}

#: Every file that decides what goes into a bundle. More than one, in two of
#: these projects, because build.py generates its own spec rather than using
#: the versioned one — so they are separate inputs to the same decision, and
#: nothing but this test notices when they disagree.
BUILD_INPUTS = ['build.py']


@pytest.fixture(scope="module", params=BUILD_INPUTS)
def build_input(request) -> str:
    path = REPO / request.param
    if not path.exists():
        pytest.fail(f"{request.param} is gone; this test guards a file that no "
                    "longer decides anything")
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "module, reason",
    [
        ("readline", "links libreadline, GPL-3.0-or-later with no linking exception"),
        ("rlcompleter", "imports readline and exists for nothing else"),
    ],
)
def test_the_gpl3_readline_chain_is_excluded(build_input: str, module: str,
                                             reason: str) -> None:
    assert f'"{module}"' in build_input or f"'{module}'" in build_input, (
        f"{module} is not excluded from the bundle — {reason}"
    )


def test_the_exclusion_says_why():
    """A bare name in an exclusion list is deleted by the next person who
    tidies it, because nothing tells them what it is for.
    """
    for name in BUILD_INPUTS:
        text = (REPO / name).read_text(encoding="utf-8")
        assert "GPL-3" in text, f"{name} excludes readline without saying why"


def test_the_licence_tooling_is_present():
    """The archive's licence tree and its inventory are both generated at build
    time; the release workflow calls these two by path.
    """
    for tool in ("tools/collect_licences.py", "tools/licence_inventory.py"):
        assert (REPO / tool).exists(), f"{tool} is missing"


def test_the_canonical_texts_the_wheels_do_not_ship_are_vendored():
    """CPython and Tcl/Tk are not wheels, so nothing carries their terms.

    Without these the licence tree would be missing the terms of the
    interpreter that runs the application and the toolkit it draws with —
    which is to say, of the two things every single archive contains.
    """
    for name in ("Python-LICENSE.txt", "Tcl-license.terms.txt",
                 "Tk-license.terms.txt", "Apache-2.0.txt"):
        path = REPO / "licenses" / name
        assert path.exists(), f"licenses/{name} is missing"
        assert len(path.read_text(encoding="utf-8")) > 1000, (
            f"licenses/{name} is too short to be a licence"
        )


class TestApplicationIcon:
    """One letter, black, on white, in a serif face — the same drawing in all
    four products, differing only in the letter.

    Committed rather than generated during the build: a release that depended
    on which fonts a runner happened to have would produce a different icon
    depending on the machine, or none.
    """

    ICO = REPO / "app.ico"
    PNG = REPO / "app.png"

    def test_both_files_are_in_the_repository(self):
        assert self.ICO.is_file(), f"{self.ICO} is missing"
        assert self.PNG.is_file(), f"{self.PNG} is missing"

    def test_the_ico_carries_every_size_windows_asks_for(self):
        """An .ico with only one frame makes Windows scale it, and a 256-pixel
        letter scaled to 16 is a grey smudge on the taskbar.
        """
        Image = pytest.importorskip("PIL.Image", reason="Pillow reads the icon")
        with Image.open(self.ICO) as icon:
            sizes = {size[0] for size in icon.info["sizes"]}
        assert {16, 24, 32, 48, 64, 128, 256} <= sizes, f"only {sorted(sizes)}"

    def test_the_png_is_big_enough_for_a_retina_dock(self):
        Image = pytest.importorskip("PIL.Image", reason="Pillow reads the icon")
        with Image.open(self.PNG) as png:
            assert png.size == (512, 512)

    def test_the_frame_is_there_at_every_size(self):
        """The four products draw their window icon from different sources —
        Qt scales the 512-pixel PNG, Tk picks the matching frame out of the
        .ico — so a rule that dropped the frame at small sizes made one
        product look like two and the four look like four families. Reported
        exactly that way: one had a black border and another did not.
        """
        Image = pytest.importorskip("PIL.Image", reason="Pillow reads the icon")
        with Image.open(self.ICO) as icon:
            sizes = sorted(icon.info["sizes"])
            for size in sizes:
                icon.size = size
                frame = icon.copy().convert("L")
                width, height = frame.size
                edge = (
                    [frame.getpixel((x, 0)) for x in range(width)]
                    + [frame.getpixel((x, height - 1)) for x in range(width)]
                    + [frame.getpixel((0, y)) for y in range(height)]
                    + [frame.getpixel((width - 1, y)) for y in range(height)]
                )
                dark = sum(1 for value in edge if value < 128)
                assert dark > len(edge) * 0.8, (
                    f"the {width}px frame is missing or too faint "
                    f"({dark} of {len(edge)} edge pixels are dark)"
                )

    def test_it_is_black_on_white(self):
        """Not a check of taste: an icon that came out mostly transparent, or
        inverted, still opens and still looks like a file.
        """
        Image = pytest.importorskip("PIL.Image", reason="Pillow reads the icon")
        with Image.open(self.PNG) as png:
            pixels = list(png.convert("L").getdata())
        white = sum(1 for value in pixels if value > 200)
        black = sum(1 for value in pixels if value < 60)
        assert white > black, "the icon is mostly dark; the background should be white"
        assert black > len(pixels) // 100, "there is almost no ink; is the letter there?"

    def test_the_small_frames_are_uncompressed(self):
        """DIB below 256 pixels, PNG only for the 256.

        Windows has accepted PNG-compressed frames since Vista, but the format
        every icon editor produces — and the one the shell has always read —
        is an uncompressed DIB at the small sizes. Explorer showing a stale or
        generic icon for an executable whose resources are demonstrably
        correct is exactly the shape of problem that convention avoids.
        """
        import struct

        data = self.ICO.read_bytes()
        _, _, count = struct.unpack("<HHH", data[:6])
        png_magic = b"\x89PNG\r\n\x1a\x0a"
        for index in range(count):
            entry = 6 + index * 16
            width, _h, _c, _r, _p, _b, size, offset = struct.unpack(
                "<BBBBHHII", data[entry:entry + 16]
            )
            width = width or 256
            is_png = data[offset:offset + 8] == png_magic
            if width >= 256:
                assert is_png, "the 256 frame should be PNG; it is the one worth compressing"
            else:
                assert not is_png, f"the {width}px frame is PNG-compressed"

    def test_every_frame_reads_back_at_its_declared_size(self):
        """The .ico is assembled by hand, so a wrong header length or a
        bottom-up row order would produce a file that still opens and is
        quietly wrong.
        """
        Image = pytest.importorskip("PIL.Image", reason="Pillow reads the icon")
        with Image.open(self.ICO) as icon:
            sizes = sorted(icon.info["sizes"])
            for size in sizes:
                icon.size = size
                frame = icon.copy().convert("L")
                pixels = list(frame.get_flattened_data()
                              if hasattr(frame, "get_flattened_data") else frame.getdata())
                assert len(pixels) == size[0] * size[1]
                assert any(value < 60 for value in pixels), f"{size[0]}px has no ink"
                assert any(value > 200 for value in pixels), f"{size[0]}px has no ground"

    def test_regenerating_them_reproduces_what_is_committed(self, tmp_path):
        """The committed files are the generator's output, and stay that way.

        This is the check that makes "regenerate and diff" a usable answer to
        "is the icon still the one the script draws". It is also the check that
        would have caught the way the arguments used to work: the letter and
        the file name came from one argument, so the only way to write the
        right file name here was to pass the wrong letter, and doing exactly
        that redrew this product's icons with someone else's initial on them.

        Skipped where the serif face is not installed: the drawing depends on
        it, so on a machine without it the comparison would be measuring the
        font rather than the generator.
        """
        import subprocess
        import sys

        pytest.importorskip("PIL", reason="Pillow draws the icons")
        sys.path.insert(0, str(REPO / "tools"))
        try:
            import make_icon
        finally:
            sys.path.pop(0)
        if not any(pathlib.Path(p).exists() for p in make_icon.FONT_CANDIDATES):
            pytest.skip("no serif font installed; the drawing would differ")

        run = subprocess.run(
            [sys.executable, str(REPO / "tools" / "make_icon.py"),
             "Proteus", str(tmp_path), "app"],
            capture_output=True, text=True,
        )
        assert run.returncode == 0, run.stderr

        for suffix in (".png", ".ico", ".icns"):
            committed = REPO / "." / f"app{suffix}"
            if not committed.exists():
                # The generator writes all three for everybody; only the
                # products that build a macOS application bundle have any
                # use for the .icns, and the rest do not carry one.
                assert suffix == ".icns", f"{committed.name} is missing"
                continue
            fresh = (tmp_path / "app").with_suffix(suffix)
            assert fresh.read_bytes() == committed.read_bytes(), (
                f"{committed.name} is not what tools/make_icon.py draws today"
            )

    def test_the_generator_is_kept_with_them(self):
        """So the next one can be drawn the same way rather than guessed at."""
        assert (REPO / "tools" / "make_icon.py").is_file()


class TestWindowIcon:
    """The icon has to reach the window, not merely ship beside it.

    Reported: the executable carried both the .ico and the .png -- verified by
    reading them back out of the published build -- and the window still came
    up under Tk's default feather. The cause was one ``try`` around both
    attempts: ``iconbitmap`` raised, and the fallback that would have set the
    PNG never ran.
    """

    SOURCE = REPO / "rebranding_tool.py"
    FUNCTION = "set_window_icon"

    def _icon_function(self):
        import ast

        tree = ast.parse(self.SOURCE.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == self.FUNCTION:
                return node
        raise AssertionError(f"{self.FUNCTION} is not in {self.SOURCE}")

    def test_it_sets_the_icon_from_both_files(self):
        import ast

        called = {
            node.func.attr
            for node in ast.walk(self._icon_function())
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert "iconphoto" in called, "nothing sets the icon off Windows"
        assert "iconbitmap" in called, "nothing uses the .ico on Windows"

    def test_one_attempt_failing_does_not_take_the_other_down(self):
        """The bug, stated as a shape: no single ``try`` may hold both calls.

        Tk raises before it changes anything, so the two are safe to attempt
        independently -- and independent is the only way a failure in one
        leaves the other's work standing.
        """
        import ast

        for node in ast.walk(self._icon_function()):
            if not isinstance(node, ast.Try):
                continue
            inside = {
                call.func.attr
                for call in ast.walk(node)
                if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
            }
            assert not {"iconphoto", "iconbitmap"} <= inside, (
                "both attempts share one try: a failure in either loses both"
            )

    def test_the_photo_image_is_kept_alive(self):
        """Tk holds only a weak reference to it. A collected PhotoImage
        leaves a blank icon, which looks exactly like never setting one.
        """
        import ast

        assigned = [
            target.attr
            for node in ast.walk(self._icon_function())
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Attribute)
        ]
        assert assigned, "the PhotoImage is not stored anywhere and will be collected"


class TestStartsMaximised:
    """The window opens filling the screen.

    Measured rather than trusted, which is the whole point of the helper:
    ``state("zoomed")`` and the ``-zoomed`` attribute are both accepted in
    silence by a Tk with no window manager behind it, so a chain that stops at
    the first call that did not raise can leave a 300x200 window and report
    success.
    """

    def _maximise(self):
        pytest.importorskip("tkinter", reason="the toolkit is not installed here")
        from rebranding_tool import maximise
        return maximise

    def test_it_fills_the_screen(self):
        tk = pytest.importorskip("tkinter", reason="the toolkit is not installed here")
        maximise = self._maximise()
        try:
            root = tk.Tk()
        except tk.TclError as exc:               # no display
            pytest.skip(f"no display: {exc}")

        try:
            root.geometry("300x200")
            root.update()
            assert root.winfo_width() < root.winfo_screenwidth() * 0.9, (
                "the window was already the size of the screen; nothing was proved"
            )

            maximise(root)
            root.update()
            assert root.winfo_width() >= root.winfo_screenwidth() * 0.9
            assert root.winfo_height() >= root.winfo_screenheight() * 0.8
        finally:
            root.destroy()

    def test_it_does_not_raise_on_a_window_that_cannot_be_measured(self):
        """A window that opened at the wrong size is a nuisance. One that
        failed to open is not.
        """
        maximise = self._maximise()

        class Hopeless:
            def __getattr__(self, name):
                def boom(*args, **kwargs):
                    raise RuntimeError("no window manager, no window, nothing")
                return boom

        maximise(Hopeless())      # must simply return


class TestLooksLikeTheOthers:
    """Iris and Proteus share a toolkit, a theme and a set of button styles.

    They did not. Both used ttkbootstrap, but Iris took its buttons from the
    theme and Proteus drew its own — its own blue, Arial bold, square corners
    — so the two read as different products. And the theme names were chosen
    by different rules: Iris asked for "flatly" directly, Proteus checked
    ``theme_names()`` first, which does not list the legacy names, so it
    silently landed on "bootstrap-light" instead. Those are not the same
    palette: flatly's primary is a dark navy, bootstrap-light's a bright blue.
    """

    #: The same tuple, in the same order, is in the other product. If one of
    #: them is edited, this is what should make it obvious that the other has
    #: to be edited too.
    PREFERENCE = ("flatly", "bootstrap-light", "litera", "cosmo")

    def test_the_theme_preference_is_the_shared_one(self):
        assert declared("THEME_PREFERENCE") == self.PREFERENCE

    def test_the_theme_is_chosen_by_trying_not_by_looking_it_up(self):
        """A legacy name still resolves while being deliberately absent from
        ``theme_names()``, so checking membership first is exactly how the
        preferred theme gets skipped — which is what happened.
        """
        import ast

        source = (REPO / "rebranding_tool.py").read_text(encoding="utf-8")
        loops = [
            node
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.For)
            and "THEME_PREFERENCE" in (ast.dump(node.iter) or "")
        ]
        assert loops, "nothing walks THEME_PREFERENCE"

        def calls(node, name):
            return any(
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and call.func.attr == name
                for call in ast.walk(node)
            )

        # Applied inside a ``try``, which is what "tried" means here: the
        # alternative — asking whether the name is in theme_names() and
        # skipping it if not — is what silently dropped the preferred theme,
        # and it does not need a try because it never expects to fail.
        tried = False
        for loop in loops:
            assert not calls(loop, "theme_names"), (
                "the theme is still selected by looking in theme_names()"
            )
            for guarded in (n for n in ast.walk(loop) if isinstance(n, ast.Try)):
                if calls(guarded, "theme_use"):
                    tried = True

        assert tried, (
            "no theme is applied inside a try: the preferred name is being "
            "checked for rather than attempted"
        )

    def test_the_theme_resolves_to_the_same_palette(self):
        tk = pytest.importorskip("tkinter", reason="the toolkit is not installed here")
        tb = pytest.importorskip("ttkbootstrap", reason="ttkbootstrap is optional")
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            pytest.skip(f"no display: {exc}")
        try:
            style = tb.Style()
            for name in self.PREFERENCE:
                try:
                    style.theme_use(name)
                    break
                except Exception:
                    continue
            # flatly's primary. If this changes, the two products have to
            # change together, which is what the shared tuple is for.
            assert style.colors.primary == "#2c3e50"
        finally:
            root.destroy()

    def test_the_buttons_come_from_the_theme(self):
        """Not from a palette of our own. Every button in the interface goes
        through one helper, so this is decided in one place rather than at
        twenty-odd call sites.
        """
        themed = declared("THEMED_BUTTONS")

        assert themed["primary"] == "primary.TButton"
        assert themed["outline"].endswith("Outline.TButton")

    def test_the_hand_made_palette_survives_as_the_fallback(self):
        """A machine without ttkbootstrap still gets coloured buttons rather
        than an interface of identical grey rectangles.
        """
        # Read as keys rather than as a value: the palette names
        # BRAND_BLUE, so it is not a literal, and it is the names that are
        # being checked here anyway.
        assert declared_keys("BUTTON_PALETTE") >= {"primary", "success", "warning", "danger"}


class TestInterfaceFont:
    """One font across the four, named rather than left to a default.

    Arial was hard-coded in Iris and Proteus — nowhere else — which is what made those
    labels the odd ones out. Nothing asks for it now, and nothing relies on
    whichever family the toolkit would have picked.
    """

    PREFERENCE = (
        "Segoe UI",
        "SF Pro Text",
        "Helvetica Neue",
        "Noto Sans",
        "DejaVu Sans",
    )

    def test_the_preference_list_is_the_shared_one(self):
        assert declared("UI_FONT_PREFERENCE") == self.PREFERENCE

    def test_nothing_asks_for_arial(self):
        import re

        for path in ("rebranding_tool.py",):
            source = (REPO / path).read_text(encoding="utf-8")
            code = "\n".join(
                line for line in source.splitlines()
                if not line.lstrip().startswith("#")
            )
            assert not re.search(r'"Arial"', code), f"{path} still asks for Arial"

    def test_the_family_resolves_to_something_real(self):
        pytest.importorskip("tkinter", reason="the toolkit is not installed here")
        import tkinter as tk

        from rebranding_tool import ui_font_family
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            pytest.skip(f"no display: {exc}")
        try:
            from tkinter import font as tkfont

            family = ui_font_family()
            assert family, "no family was resolved"
            # Either one of ours, or the one Tk itself would have used — never
            # a name the system will silently substitute for something else.
            assert (family in self.PREFERENCE
                    or family == tkfont.nametofont("TkDefaultFont").actual("family"))
        finally:
            root.destroy()
