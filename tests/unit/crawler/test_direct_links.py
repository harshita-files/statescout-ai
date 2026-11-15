"""Links become reload-independent `navigate` actions; clicks fail fast when absent."""

from __future__ import annotations

from typing import Any

import pytest

from apps.agent.contracts import Action, CaptureBundle
from apps.agent.crawler.actions import _perform_action
from apps.agent.crawler.playwright_crawler import PlaywrightCrawler, _extract_actions
from apps.agent.orchestrator.graph_runner import is_direct

AX = {
    "role": "RootWebArea",
    "name": "Page",
    "children": [
        {"role": "link", "name": "Markets"},
        {"role": "link", "name": "Elsewhere"},
        {"role": "link", "name": "Top"},
        {"role": "button", "name": "Star"},
    ],
}
ANCHORS = [
    {"name": "Markets", "href": "http://a.test/markets"},
    {"name": "Elsewhere", "href": "http://other.test/x"},
    {"name": "Top", "href": "http://a.test/page#top"},
]


class _Page:
    def __init__(self, count: int = 1) -> None:
        self._count = count

    def evaluate(self, _js: str) -> list[dict[str, str]]:
        return ANCHORS

    def locator(self, _sel: str) -> Any:
        class _L:
            def count(_s) -> int:
                return self._count

        return _L()

    def click(self, *_a: Any, **_k: Any) -> None:  # pragma: no cover - must not be reached
        raise AssertionError("click should not run")


def _crawler(page: _Page) -> PlaywrightCrawler:
    c = PlaywrightCrawler.__new__(PlaywrightCrawler)
    c._page, c._closed, c._safety = page, False, None  # type: ignore[attr-defined]
    return c


def test_links_become_navigate_and_buttons_stay_clicks() -> None:
    acts: list[Action] = []
    _extract_actions(AX, acts)
    out = _crawler(_Page())._direct_links(CaptureBundle("http://a.test/page", "", {}), acts)
    by_label = {a.label: a for a in out}
    assert by_label['navigate "Markets"'].target == "http://a.test/markets"
    assert by_label['click "Star"'].kind == "click"
    assert not any("Top" in a.label for a in out)  # in-page anchor is not a new state


def test_action_id_is_unchanged_by_conversion() -> None:
    acts: list[Action] = []
    _extract_actions(AX, acts)
    before = {a.label.split('"')[1]: a.action_id for a in acts}
    out = _crawler(_Page())._direct_links(CaptureBundle("http://a.test/page", "", {}), acts)
    assert next(a for a in out if "Markets" in a.label).action_id == before["Markets"]


def test_click_on_missing_element_fails_fast() -> None:
    with pytest.raises(ValueError, match="element not found"):
        _perform_action(_Page(count=0), {"type": "click", "selector": "role=button[name=/^x$/]"})  # type: ignore[arg-type]


def test_is_direct_only_for_absolute_navigate() -> None:
    assert is_direct(Action("a", "navigate", "https://a.test/x", "l"))
    assert not is_direct(Action("a", "navigate", "/x", "l"))
    assert not is_direct(Action("a", "click", "https://a.test/x", "l"))
