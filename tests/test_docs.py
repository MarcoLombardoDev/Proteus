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

TIERS = ("Community", "Startup", "Business", "Enterprise")


def prices(text: str) -> dict[str, set[str]]:
    """Map each tier name to the prices quoted on its row."""
    found: dict[str, set[str]] = {}
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        for tier in TIERS:
            if f"**{tier}**" in line:
                found.setdefault(tier, set()).update(
                    re.findall(r"€[\d,]+(?:\s*/\s*year)?|€0", line))
    return found


def test_the_price_list_agrees_with_itself():
    """
    The README summarises the price list; COMMERCIAL-LICENSE.md is the source
    of truth. Two copies of a number is one copy too many, so they are compared
    rather than trusted.
    """
    licence = prices(read("COMMERCIAL-LICENSE.md"))
    readme = prices(read("README.md"))

    assert set(licence) == set(TIERS), f"tiers missing from the licence: {licence.keys()}"
    for tier in TIERS:
        assert readme.get(tier) == licence[tier], (
            f"{tier}: README says {readme.get(tier)}, "
            f"COMMERCIAL-LICENSE.md says {licence[tier]}")


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
    assert "internal business use of the unmodified tool is free" in terms


CONTACT = "marco.lombardo@gmail.com"


@pytest.mark.parametrize("document", ["README.md", "COMMERCIAL-LICENSE.md", "CLA.md"])
def test_a_buyer_can_find_a_way_to_get_in_touch(document):
    """A price list nobody can respond to is decoration."""
    assert CONTACT in read(document)


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
