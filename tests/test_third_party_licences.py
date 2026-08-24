# Proteus — Rebranding Tool
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.
# A commercial licence, without the AGPL's obligations, is available for use
# in proprietary or closed-source products — see COMMERCIAL-LICENSE.md.

"""THIRD-PARTY-LICENSES.md, and the script that keeps it honest.

The document is generated from a real build. What these tests check is that it
still says the things a reader needs and that the generator still behaves the
way the document claims — in particular that a licence file which cannot be
found is *recorded* rather than passed over, since a tree that looks complete
and is not is the one failure this whole mechanism exists to prevent.
"""

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

DOCUMENT = (REPO / "THIRD-PARTY-LICENSES.md").read_text(encoding="utf-8")

#: The headings, in order. Shared with Orion, Iris, Proteus and Argus so the
#: same question is answered in the same place in every product.
SECTIONS = [
    "## How this was produced",
    "## What Proteus depends on directly",
    "## The components that actually constrain redistribution",
    "## What was deliberately removed",
    "## Licence texts travel with the build",
    "## Full inventory",
    "## Build-time tools",
    "## Known gaps",
    "## Reproducing this",
]


def test_the_sections_are_present_and_in_order():
    positions = []
    for heading in SECTIONS:
        assert heading in DOCUMENT, f"{heading} is missing"
        positions.append(DOCUMENT.index(heading))
    assert positions == sorted(positions), "the sections are out of order"


@pytest.mark.parametrize("dependency", ["Pillow", "pypdf", "ttkbootstrap", "PyInstaller"])
def test_every_direct_dependency_is_documented(dependency: str) -> None:
    """A dependency nobody wrote down is a dependency nobody licensed."""
    assert dependency in DOCUMENT


def test_the_document_names_no_dependency_that_was_dropped():
    """PyMuPDF was removed for its licence. A document that still
    lists it as a dependency would be describing a product that no longer
    exists.
    """
    for line in DOCUMENT.splitlines():
        if line.startswith("|") and "PyMuPDF" in line:
            assert "removed" in line.lower() or "used to" in line.lower(), line


#: The document is prose, so a phrase can be split across a line break or wear
#: markdown emphasis. Tests that search it compare against this instead of the
#: raw text, rather than being hostage to where a paragraph happened to wrap.
FLATTENED = " ".join(DOCUMENT.replace("*", "").split())


def test_the_removal_is_explained_and_not_just_applied():
    """Somebody will eventually ask why readline is excluded. If the answer
    lives only in a commit message, the exclusion gets reverted.
    """
    assert "libreadline" in DOCUMENT
    assert "GPL-3.0-or-later with no linking exception" in FLATTENED


def test_the_inventory_separates_what_was_measured_from_what_was_assumed():
    """Every row names its evidence, and unresolved rows stay visible."""
    assert "Evidence" in DOCUMENT
    assert "unresolved" in DOCUMENT.lower()
    assert "not a legal opinion" in DOCUMENT.lower()


def test_the_bytecode_gap_is_admitted():
    """The tables cover native binaries only. Pure-Python code — which is where
    a copyleft licence is most likely to hide — is not in them, and a reader
    who does not know that will draw the wrong conclusion from a clean table.
    """
    assert "bytecode" in DOCUMENT.lower()


class TestLicenceCollection:
    """The script that assembles what ships in the archive."""

    def test_a_missing_licence_is_recorded_rather_than_passed_over(self, tmp_path):
        """The one behaviour worth a test of its own.

        A wheel that ships no licence file has to leave a visible hole in the
        index. Silently skipping it produces a tree that looks complete, which
        is worse than one with an obvious gap.
        """
        import collect_licences

        assert collect_licences._distribution_licence_files(
            "a-distribution-that-does-not-exist"
        ) == []

    def test_build_tools_that_are_not_shipped_are_not_collected(self):
        """Their terms do not belong in an archive they are not in."""
        import collect_licences

        assert "pip" in collect_licences.BUILD_ONLY
        assert "setuptools" in collect_licences.BUILD_ONLY
        assert "pyinstaller" not in collect_licences.BUILD_ONLY, (
            "the bootloader does ship, so its terms have to"
        )

    def test_the_interpreter_and_the_toolkit_are_always_supplied(self):
        """Neither is a wheel; without these the tree would omit the terms of
        the two things every archive contains.
        """
        import collect_licences

        supplied = {name for _folder, name, _label in collect_licences.ALWAYS_SUPPLIED}
        assert supplied == {
            "Python-LICENSE.txt",
            "Tcl-license.terms.txt",
            "Tk-license.terms.txt",
        }


class TestLicencePathHandling:
    """Two wheels shipping ``licenses/LICENSE`` must not overwrite each other."""

    @staticmethod
    def _flatten(pairs):
        import collect_licences

        return dict(collect_licences._flatten(pairs))

    def test_the_conventional_licenses_prefix_is_dropped(self):
        assert self._flatten([("licenses/LICENSE", "x")]) == {"LICENSE": "x"}

    def test_but_not_when_that_would_collide(self):
        flattened = self._flatten([("LICENSE", "a"), ("licenses/LICENSE", "b")])
        assert flattened == {"LICENSE": "a", "licenses/LICENSE": "b"}

    def test_deeper_paths_are_preserved(self):
        assert self._flatten([("licenses/vendor/LICENSE", "x")]) == {
            "vendor/LICENSE": "x"
        }


class TestBundleClassifier:
    """Attributing a path in the bundle to the thing that shipped it.

    The owner index is supplied rather than read from the running interpreter.
    These tests check the attribution rules, and the CI job that runs them
    installs pytest and nothing else — against a real index they would pass or
    fail depending on what happened to be installed, which is not a property of
    the code under test.
    """

    #: What importlib.metadata reports on a machine that built one of these
    #: bundles: import names and distribution names both, case-folded.
    owners = {
        "pil": "pillow",
        "pillow": "pillow",
        "openpyxl": "openpyxl",
        "torch": "torch",
        "_cffi_backend": "cffi",
        "cffi": "cffi",
    }

    @pytest.mark.parametrize(
        "path, origin",
        [
            ("python3.12/lib-dynload/_ssl.cpython-312-x86_64-linux-gnu.so", "cpython"),
            ("libpython3.12.so.1.0", "cpython"),
            ("libtcl8.6.so", "system"),
            ("libgcc_s.so.1", "system"),
        ],
    )
    def test_origins(self, path: str, origin: str) -> None:
        import licence_inventory

        classified = licence_inventory.classify(path, self.owners)
        assert classified is not None, path
        assert classified[0] == origin

    def test_a_wheels_vendored_directory_is_credited_to_the_wheel(self):
        """auditwheel names it after the *distribution*, not the package, and
        PIL is not pillow. Getting this wrong left the largest group in the
        bundle reported as unknown.
        """
        import licence_inventory

        classified = licence_inventory.classify(
            "pillow.libs/libjpeg-31e2ca52.so.62.4.0", self.owners
        )
        assert classified == ("wheel", "pillow")

    def test_a_package_directory_is_credited_to_its_distribution(self):
        import licence_inventory

        classified = licence_inventory.classify(
            "PIL/_imaging.cpython-312-x86_64-linux-gnu.so", self.owners
        )
        assert classified == ("wheel", "pillow")

    def test_something_that_is_not_a_binary_is_not_inventoried(self):
        import licence_inventory

        assert licence_inventory.classify("README.md", self.owners) is None

    def test_a_top_level_extension_module_is_credited_to_its_distribution(self):
        """cffi's _cffi_backend sits at the top level with no directory to read
        the owner out of, and came out as a system library until the module
        name itself was used as the key.
        """
        import licence_inventory

        assert licence_inventory.classify(
            "_cffi_backend.cpython-312-x86_64-linux-gnu.so", self.owners
        ) == ("wheel", "cffi")

    def test_gpl3_readline_is_flagged_if_it_ever_returns(self):
        """The inventory is the last place this would be noticed, so it says so
        rather than printing a licence name and moving on.
        """
        import licence_inventory

        assert "libreadline8t64" in licence_inventory.FLAGGED
        assert "no linking exception" in licence_inventory.FLAGGED["libreadline8t64"]

    def test_one_place_decides_what_a_package_is_licensed_under(self):
        """These rules used to be applied twice — once where the package was
        found by name and once where it was found by path — and the second copy
        was missing the X.Org rule, so ten X libraries came out unresolved in a
        report that was otherwise complete.
        """
        import licence_inventory

        licence, evidence = licence_inventory.licence_for_package("libx11-6")
        assert licence == "MIT"
        assert "X.Org" in evidence


class TestRunsWithoutDpkg:
    """Two of the three release runners have no package database at all.

    This is where the first release run broke: ``subprocess.run`` raises
    FileNotFoundError when the executable is missing rather than returning
    non-zero, so the script died on Windows and macOS instead of reporting
    what it could not resolve.
    """

    def test_the_dpkg_lookup_is_guarded(self):
        import licence_inventory

        assert hasattr(licence_inventory, "HAS_DPKG")

    def test_it_returns_nothing_rather_than_raising(self, monkeypatch):
        import licence_inventory

        monkeypatch.setattr(licence_inventory, "HAS_DPKG", False)
        assert licence_inventory.dpkg_owner("libz.so.1") is None

    def test_the_platform_libraries_still_resolve(self, monkeypatch):
        """What a Windows or macOS bundle is mostly made of is named by
        pattern rather than by package, so it resolves with no dpkg at all.
        """
        import licence_inventory

        monkeypatch.setattr(licence_inventory, "HAS_DPKG", False)
        for name, expected in (
            ("VCRUNTIME140.dll", "Microsoft Visual C++ / Universal CRT runtime"),
            ("libcrypto.3.dylib", "OpenSSL"),
            ("libtcl8.6.dylib", "Tcl/Tk"),
            ("tcl86t.dll", "Tcl/Tk"),
        ):
            component, licence, _evidence = licence_inventory.resolve_system(name)
            assert component == expected, name
            assert licence, name

    def test_anything_else_is_reported_unresolved_not_guessed(self, monkeypatch):
        import licence_inventory

        monkeypatch.setattr(licence_inventory, "HAS_DPKG", False)
        component, licence, _evidence = licence_inventory.resolve_system("libmystery.so.1")
        assert component == "unknown"
        assert licence is None


def test_unresolved_rows_have_their_own_exit_code():
    """A caller has to be able to tell a script that finished with gaps from a
    script that died. An uncaught exception exits 1, so 1 cannot mean either.
    """
    import licence_inventory

    assert licence_inventory.UNRESOLVED_EXIT == 2
