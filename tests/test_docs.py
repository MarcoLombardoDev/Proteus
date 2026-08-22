#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Guards against documentation drifting away from the product.

A price quoted in two places will eventually disagree with itself, and a
screenshot referenced after being renamed leaves a broken image on the project's
front page. Neither failure is visible to anyone editing the code, so both are
checked here.
"""

from __future__ import annotations

import os
import re

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(name: str) -> str:
    with open(os.path.join(REPO, name), encoding="utf-8") as fh:
        return fh.read()


# ---------------------------------------------------------------------------
# Screenshots
# ---------------------------------------------------------------------------

def test_every_referenced_image_exists():
    """A renamed capture must not leave a broken image in the README."""
    missing = [target for target in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", read("README.md"))
               if not target.startswith("http")
               and not os.path.exists(os.path.join(REPO, target))]
    assert not missing, f"README references missing images: {missing}"


def test_every_capture_the_generator_produces_is_shown():
    """
    The reverse direction: a capture nobody displays is dead weight in the
    repository, and usually means a README edit was forgotten.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "generate_screenshots", os.path.join(REPO, "docs", "generate_screenshots.py"))
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)

    expected = [name for name, _tab in generator.SHOTS] + [generator.CLI_SHOT]
    readme = read("README.md")
    unused = [name for name in expected if f"{name}.png" not in readme]
    assert not unused, f"captures produced but never shown: {unused}"


# ---------------------------------------------------------------------------
# Licensing
# ---------------------------------------------------------------------------

#: Tiers that must exist under the same name in both documents. Commercial and
#: Redistribution each cover several sub-tiers (Small/Medium/Large/Enterprise,
#: Standard/Enterprise) that the README does not necessarily spell out row by
#: row, so matching is done at the licence-family level; their figures are
#: checked below by amount instead of by sub-tier name.
TIERS = ("Community", "Commercial", "Redistribution")


def section(text: str, heading: str, stop: str) -> str:
    """The slice of a document between two headings."""
    start = text.index(heading)
    end = text.index(stop, start)
    return text[start:end]


def tier_rows(text: str) -> dict[str, str]:
    """Map each tier name to the raw table row quoting its price."""
    found: dict[str, str] = {}
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        for tier in TIERS:
            if f"**{tier}" in line:
                found.setdefault(tier, line)
    return found


def amounts(text: str) -> set[str]:
    """Every monetary figure in `text`, normalised."""
    return {a.replace(",", "").replace(" ", "")
            for a in re.findall(r"€\s?[\d,]+", text)}


def test_the_price_list_agrees_with_itself():
    """
    The README summarises the price list; COMMERCIAL-LICENSE.md is the source
    of truth. Two copies of a number is one copy too many, so they are compared
    rather than trusted.

    Compared by amount rather than by row, because the README legitimately
    collapses rows the licence keeps separate. What must never differ is the
    set of figures a reader is quoted.
    """
    terms = read("COMMERCIAL-LICENSE.md")
    # The README's licensing section summarises the whole offer, so it is
    # compared against both places the licence quotes a figure: the price list
    # and the custom-development day rate.
    licence = (amounts(section(terms, "## 5. Price list", "## 6."))
               | amounts(section(terms, "## 7. Custom development", "## 8.")))
    readme = amounts(section(read("README.md"),
                             "### Commercial Licensing", "### Contributing"))

    assert readme == licence, (f"README quotes {sorted(readme)}, "
                               f"COMMERCIAL-LICENSE.md quotes {sorted(licence)}")


def test_every_tier_is_named_in_both_documents():
    """A tier the README never mentions is a tier nobody will ask about."""
    licence = tier_rows(section(read("COMMERCIAL-LICENSE.md"), "## 5. Price list", "## 6."))
    readme = tier_rows(section(read("README.md"), "### Commercial Licensing", "### Contributing"))

    assert set(licence) == set(TIERS), f"tiers missing from the licence: {sorted(licence)}"
    assert set(readme) == set(TIERS), f"tiers missing from the README: {sorted(readme)}"


def test_the_free_tier_stays_free():
    """
    The Community row is the one a hostile reading would quietly reprice. It
    must cost nothing, in both documents, in words a reader cannot misread.
    """
    for document, heading, stop in (
            ("COMMERCIAL-LICENSE.md", "## 5. Price list", "## 6."),
            ("README.md", "### Commercial Licensing", "### Contributing")):
        row = tier_rows(section(read(document), heading, stop))["Community"]
        assert re.search(r"\*\*(Free|€0)\*\*", row), f"{document}: {row.strip()}"


def test_the_agpl_text_is_not_edited():
    """
    The AGPL may be applied to a work, never rewritten. Adding commercial terms
    to LICENSE itself would make the licence unrecognisable and unenforceable.
    """
    licence = read("LICENSE")
    assert "GNU AFFERO GENERAL PUBLIC LICENSE" in licence
    assert "Version 3, 19 November 2007" in licence

    # Deliberately not the word "price": the AGPL preamble uses it itself,
    # in "free as in freedom, not price". And matched on word boundaries,
    # because "VAT" is a substring of "private".
    for word in ("€", "VAT", "invoice", "per year", "subscription"):
        pattern = re.escape(word) if not word.isalpha() else rf"\b{word}\b"
        assert not re.search(pattern, licence, re.IGNORECASE), (
            f"LICENSE must stay verbatim AGPL, found {word!r} — "
            "commercial terms belong in COMMERCIAL-LICENSE.md")


def test_the_commercial_terms_do_not_contradict_the_agpl_on_internal_use():
    """
    Regression against the commonest dual-licensing lie. The AGPL grants free
    internal use to organisations of any size; a price list that implies
    otherwise would be misrepresenting the licence the project ships under.
    """
    terms = read("COMMERCIAL-LICENSE.md").lower()

    # Matched on substance rather than on an exact sentence: the wording has
    # already been rewritten once, and pinning the phrasing only teaches the
    # next editor to delete the test.
    match = re.search(r"organisations of any size", terms)
    assert match, "the terms must state that internal use is free at any size"
    assert "free" in terms[max(0, match.start() - 160):match.end()], (
        "'organisations of any size' must appear in a sentence about it being free")


CONTACT = "marco.lombardo@gmail.com"


@pytest.mark.parametrize("document", ["README.md", "COMMERCIAL-LICENSE.md", "CLA.md"])
def test_a_buyer_can_find_a_way_to_get_in_touch(document):
    """A price list nobody can respond to is decoration."""
    assert CONTACT in read(document)


def test_the_mail_subject_is_the_same_wherever_the_reader_clicks():
    """
    The footer, the README and the licence all open a mail client. The same
    enquiry arriving under two different subjects makes it look like two
    different enquiries — and the drift is invisible, because nobody clicks
    all four links.
    """
    from urllib.parse import quote

    import core

    expected = f"subject={quote(core.LICENSE_EMAIL_SUBJECT)}"
    for document in ("README.md", "COMMERCIAL-LICENSE.md"):
        subjects = set(re.findall(r"subject=[^)\s]+", read(document)))
        assert subjects, f"{document} has no mailto subject to check"
        assert subjects == {expected}, (
            f"{document} uses {subjects}, core.LICENSE_EMAIL_SUBJECT gives {expected!r}")


def test_the_documented_dev_dependencies_cover_the_docs_tooling():
    """
    Regression: `mss` was needed to regenerate the screenshots but declared
    nowhere, so the instruction only worked for whoever already had it.
    """
    declared = read("requirements-dev.txt")
    generator = read(os.path.join("docs", "generate_screenshots.py"))

    if "import mss" in generator:
        assert "mss" in declared, "docs/generate_screenshots.py needs mss"


def test_no_placeholder_survived_into_the_published_terms():
    """
    Regression: the contact address started life as a marked placeholder. A
    price list shipped with `(to be published)` still in it is worse than one
    with no price list at all.
    """
    terms = read("COMMERCIAL-LICENSE.md").lower()
    for placeholder in ("to be published", "tbd", "todo", "xxx", "your-domain"):
        assert placeholder not in terms, f"placeholder left in the terms: {placeholder!r}"


@pytest.mark.parametrize("document", ["README.md", "COMMERCIAL-LICENSE.md", "CLA.md"])
def test_licensing_documents_are_reachable_from_the_readme(document):
    assert os.path.exists(os.path.join(REPO, document))
    if document != "README.md":
        assert document in read("README.md"), f"{document} is not linked from the README"
