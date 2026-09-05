"""Unit tests for PlaywrightCrawler.

All tests are marked ``not live`` -- no real browser is launched.
The enumerate_actions logic is tested with synthetic AX tree dicts that
match both the CDP flat shape and the nested FakeCrawler shape.
The open/act/close wiring is tested with lightweight monkey-patching of the
low-level functions so no Playwright binary is needed.
"""

from __future__ import annotations

from typing import Any

import pytest

from apps.agent.contracts import Action, CaptureBundle, NavigationError
from apps.agent.crawler.playwright_crawler import (
    PlaywrightCrawler,
    _action_id,
    _extract_actions,
)

# ---------------------------------------------------------------------------
# _action_id  (decision 1)
# ---------------------------------------------------------------------------


def test_action_id_is_deterministic() -> None:
    """Same inputs always produce the same 16-char hex string."""
    a = _action_id("button", "Submit", "#submit")
    b = _action_id("button", "Submit", "#submit")
    assert a == b
    assert len(a) == 16
    assert all(c in "0123456789abcdef" for c in a)


def test_action_id_differs_for_different_inputs() -> None:
    a = _action_id("button", "Submit", "#submit")
    b = _action_id("link", "Submit", "#submit")
    assert a != b


def test_action_id_case_insensitive_on_role_and_name() -> None:
    """Role and name are normalised to lower-case before hashing."""
    a = _action_id("Button", "SUBMIT", "#submit")
    b = _action_id("button", "submit", "#submit")
    assert a == b


# ---------------------------------------------------------------------------
# _extract_actions with nested AX tree (FakeCrawler / tests shape)
# ---------------------------------------------------------------------------


NESTED_AX: dict[str, Any] = {
    "role": "document",
    "name": "Home",
    "children": [
        {"role": "link", "name": "Login", "selector": "#login-link"},
        {"role": "button", "name": "Submit", "selector": "#submit-btn"},
        {"role": "heading", "name": "Welcome"},  # not actionable
        {
            "role": "nav",
            "name": "",
            "children": [{"role": "link", "name": "Dashboard", "selector": "#dash"}],
        },
    ],
}


def test_extract_nested_finds_links_and_buttons() -> None:
    collected: list[Action] = []
    _extract_actions(NESTED_AX, collected)
    roles = {a.kind for a in collected}
    names = {a.label for a in collected}
    assert "click" in roles
    assert 'click "Login"' in names
    assert 'click "Submit"' in names
    assert 'click "Dashboard"' in names


def test_extract_nested_skips_non_actionable() -> None:
    collected: list[Action] = []
    _extract_actions(NESTED_AX, collected)
    names = {a.label for a in collected}
    assert 'click "Welcome"' not in names


# ---------------------------------------------------------------------------
# _extract_actions with CDP flat format
# ---------------------------------------------------------------------------


CDP_AX: dict[str, Any] = {
    "nodes": [
        {
            "nodeId": "1",
            "role": {"value": "RootWebArea"},
            "name": {"value": "Page"},
        },
        {
            "nodeId": "2",
            "role": {"value": "link"},
            "name": {"value": "Admin panel"},
            "backendDOMNodeId": 42,
        },
        {
            "nodeId": "3",
            "role": {"value": "button"},
            "name": {"value": "Log out"},
            "backendDOMNodeId": 99,
        },
        {
            "nodeId": "4",
            "role": {"value": "generic"},
            "name": {"value": ""},  # empty name -- should be skipped
        },
    ]
}


def test_extract_cdp_finds_link_and_button() -> None:
    collected: list[Action] = []
    _extract_actions(CDP_AX, collected)
    labels = {a.label for a in collected}
    assert 'click "Admin panel"' in labels
    assert 'click "Log out"' in labels


def test_extract_cdp_skips_empty_name() -> None:
    collected: list[Action] = []
    _extract_actions(CDP_AX, collected)
    assert all(a.label != 'click ""' for a in collected)


def test_extract_cdp_uses_backend_node_id_selector() -> None:
    collected: list[Action] = []
    _extract_actions(CDP_AX, collected)
    admin = next(a for a in collected if "Admin panel" in a.label)
    assert "42" in admin.target


# ---------------------------------------------------------------------------
# enumerate_actions (deduplication)
# ---------------------------------------------------------------------------


DUPE_AX: dict[str, Any] = {
    "role": "document",
    "name": "Dupes",
    "children": [
        {"role": "link", "name": "Login", "selector": "#a"},
        {"role": "link", "name": "Login", "selector": "#a"},  # exact duplicate
    ],
}


def test_enumerate_deduplicates_by_action_id() -> None:
    crawler = PlaywrightCrawler.__new__(PlaywrightCrawler)
    bundle = CaptureBundle(url="http://x", dom="", ax_tree=DUPE_AX)
    actions = crawler.enumerate_actions(bundle)
    assert len(actions) == 1


def test_enumerate_empty_ax_tree() -> None:
    crawler = PlaywrightCrawler.__new__(PlaywrightCrawler)
    bundle = CaptureBundle(url="http://x", dom="", ax_tree={})
    assert crawler.enumerate_actions(bundle) == ()


def test_enumerate_none_ax_tree() -> None:
    crawler = PlaywrightCrawler.__new__(PlaywrightCrawler)
    bundle = CaptureBundle(url="http://x", dom="", ax_tree=None)
    assert crawler.enumerate_actions(bundle) == ()


# ---------------------------------------------------------------------------
# close() is safe to call twice
# ---------------------------------------------------------------------------


def test_close_is_idempotent() -> None:
    crawler = PlaywrightCrawler.__new__(PlaywrightCrawler)
    crawler._closed = False
    crawler._session_ctx = None
    crawler._page = None
    crawler.close()
    crawler.close()  # must not raise


# ---------------------------------------------------------------------------
# CrawlerPort protocol compliance
# ---------------------------------------------------------------------------


def test_playwright_crawler_satisfies_crawler_port() -> None:
    """runtime_checkable ensures isinstance works against Protocol."""
    from apps.agent.contracts import CrawlerPort

    crawler = PlaywrightCrawler.__new__(PlaywrightCrawler)
    assert isinstance(crawler, CrawlerPort)


# ---------------------------------------------------------------------------
# open() raises NavigationError when page is not initialised
# ---------------------------------------------------------------------------


def test_open_without_session_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """open() wraps all failures as NavigationError."""

    def _fail_goto(*args: object, **kwargs: object) -> None:
        from playwright.sync_api import TimeoutError as PTE

        raise PTE("timeout")

    # Stub _start_session so no real browser is launched, but set a fake page.
    class _FakePage:
        def goto(self, *a: object, **kw: object) -> None:
            return _fail_goto()

    crawler = PlaywrightCrawler.__new__(PlaywrightCrawler)
    crawler._closed = False
    crawler._session_ctx = object()  # truthy -- skip _start_session
    crawler._page = _FakePage()  # type: ignore[assignment]
    crawler._headless = True
    crawler._output_dir = "/tmp"

    with pytest.raises(NavigationError):
        crawler.open("http://unreachable.local")
