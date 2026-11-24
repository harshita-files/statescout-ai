"""Selectors are built from CDP accessible names but resolved by Playwright.

The two disagree: CDP applies CSS `text-transform` and keeps the glyph an icon
font injects through a ::before pseudo-element, Playwright does neither. An
exact, case-sensitive regex built from the CDP name therefore matched nothing on
Spring PetClinic, whose whole navigation uses Font Awesome, and the crawl
stopped after two states.
"""

from __future__ import annotations

import re

from apps.agent.crawler.playwright_crawler import _name_pattern


def _matches(pattern: str, playwright_name: str) -> bool:
    return re.search(pattern, playwright_name, re.IGNORECASE) is not None


def test_icon_glyph_and_text_transform_are_tolerated() -> None:
    # CDP reports " HOME"; Playwright reports " Home".
    assert _matches(_name_pattern(" HOME"), " Home")


def test_plain_name_still_matches_itself() -> None:
    assert _matches(_name_pattern("Delete All Records"), "Delete All Records")


def test_internal_punctuation_is_preserved() -> None:
    assert _matches(_name_pattern("SQL Injection (Blind)"), "SQL Injection (Blind)")


def test_a_different_control_still_does_not_match() -> None:
    assert not _matches(_name_pattern(" HOME"), " Find Owners")


def test_a_longer_name_is_not_matched_by_a_shorter_one() -> None:
    assert not _matches(_name_pattern("Delete"), "Delete All Records")


def test_name_of_only_glyphs_falls_back_to_the_raw_name() -> None:
    pattern = _name_pattern("")
    assert _matches(pattern, "")
