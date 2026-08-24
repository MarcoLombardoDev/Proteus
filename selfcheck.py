# Proteus — Rebranding Tool
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.
# A commercial licence, without the AGPL's obligations, is available for use
# in proprietary or closed-source products — see COMMERCIAL-LICENSE.md.

"""The check the release workflow runs against every bundle it builds.

``--version`` is not a smoke test. argparse prints the version and exits
during argument parsing, before Tk is imported and before a single one of the
product's own modules is loaded, so it proves the frozen interpreter and the
bundled standard library work and nothing else. A bundle whose Tcl/Tk
libraries were not collected passes it. So does one that cannot save a file.
Both then fail on the user's machine, after the release is published.

Two things are checked here instead, because these are the two ways a frozen
bundle actually breaks:

**The toolkit starts.** Creating a Tk root is what makes Tcl go looking for
its script library and Tk for its own, and both are data directories that
PyInstaller has to have collected. The windowing system is reported rather
than assumed — a Linux bundle must come up on ``x11``, and the workflow fails
the build if it does not, because "Tk started" under some fallback is exactly
the result that would hide a broken bundle.

**A file is written and read back.** This is where a frozen application
breaks: a data directory PyInstaller did not collect, a shared library it did
not find. Those failures happen the first time a user saves, not at startup,
and the test suite cannot see them either — it runs against an installed
package, where nothing is missing.

Nothing is left behind: everything is written inside a temporary directory
that goes away with it. A smoke test that litters the user's disk is its own
bug report.
"""

from __future__ import annotations

from core import APP_NAME, APP_VERSION as __version__


def _toolkit() -> list[str]:
    """Start Tk for real and report what backend it came up on.

    Withdrawn immediately: the point is that the toolkit loaded, not that
    anything is shown, and a window flashing up on a build runner would be a
    nuisance at best. ``destroy`` runs whatever happens, so the process can
    still exit cleanly when the report is being written.
    """
    import tkinter

    root = tkinter.Tk()
    try:
        root.withdraw()
        return [
            f"windowing system: {root.tk.call('tk', 'windowingsystem')}",
            f"tk version: {root.tk.call('info', 'patchlevel')}",
        ]
    finally:
        root.destroy()


def _round_trip() -> str:
    """Replace a picture inside an Office document and read the result back.

    The smallest thing that touches everything the product is: Pillow renders
    and measures the images, ``core`` compares them the way a scan does,
    ``office`` rewrites the package, and the whole of it goes through a real
    file on disk. A ``.docx`` is a zip with pictures under ``word/media/``,
    which is all ``office.list_images`` looks for, so one can be built here
    without Word and without python-docx — which is not in the bundle.
    """
    import io
    import tempfile
    import zipfile
    from pathlib import Path

    from PIL import Image

    import core
    import office

    def png(colour: tuple[int, int, int]) -> bytes:
        buffer = io.BytesIO()
        Image.new("RGB", (48, 48), colour).save(buffer, format="PNG")
        return buffer.getvalue()

    old, new = png((200, 30, 30)), png((30, 30, 200))
    entry = "word/media/image1.png"

    with tempfile.TemporaryDirectory(prefix="proteus-self-check-") as directory:
        document = str(Path(directory) / "self-check.docx")
        with zipfile.ZipFile(document, "w") as package:
            package.writestr("[Content_Types].xml", "<Types/>")
            package.writestr("word/document.xml", "<document/>")
            package.writestr(entry, old)

        found, problems = office.list_images(document)
        if [image.entry for image in found] != [entry]:
            raise RuntimeError(f"the picture was not found: {found}, {problems}")

        office.write_replacements(document, {entry: new})

        written = office.extract(document, entry)
        if written != new:
            raise RuntimeError("the replacement did not survive the rewrite")
        with zipfile.ZipFile(document) as package:
            names = sorted(package.namelist())
        if "word/document.xml" not in names:
            raise RuntimeError("rewriting the package lost its other parts")

        # Pillow has to be able to open what came back out, and the hash has to
        # tell the two pictures apart — that is the comparison a real scan runs.
        target = Path(directory) / "written.png"
        target.write_bytes(written)
        source = Path(directory) / "original.png"
        source.write_bytes(old)
        if core.get_image_dimensions(str(target)) != (48, 48):
            raise RuntimeError("the written picture would not open")
        similarity = core.hash_similarity(
            core.perceptual_hash(str(source)), core.perceptual_hash(str(target))
        )

    return (
        f"replaced 1 picture in a {len(names)}-part package, "
        f"read back {len(written)} bytes, similarity to the original "
        f"{similarity:.0%}"
    )


def run(report_path: str | None = None) -> int:
    """Run the check, print the report, and return an exit code.

    The report is written to a file as well as printed because two of these
    three products are built ``--windowed`` on Windows, where the process has
    no stdout at all and ``print`` is a no-op. Parsing stdout would work on
    Linux and macOS and silently check nothing on Windows, which is the
    platform whose bundles are least like the machine they were built on.
    """
    lines = [f"{APP_NAME} {__version__}"]
    ok = True

    try:
        lines += _toolkit()
    except Exception as exc:  # noqa: BLE001 - the report is the error handler
        lines.append(f"windowing system: FAILED — {exc}")
        ok = False

    try:
        lines.append(f"round trip: {_round_trip()}")
    except Exception as exc:  # noqa: BLE001 - as above
        lines.append(f"round trip: FAILED — {exc}")
        ok = False

    report = "\n".join(lines)
    print(report)
    if report_path:
        with open(report_path, "w", encoding="utf-8") as handle:
            handle.write(report + "\n")
    return 0 if ok else 1
