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

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

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

    def test_the_generator_is_kept_with_them(self):
        """So the next one can be drawn the same way rather than guessed at."""
        assert (REPO / "tools" / "make_icon.py").is_file()
