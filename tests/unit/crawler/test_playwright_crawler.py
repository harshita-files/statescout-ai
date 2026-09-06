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


def test_extract_cdp_builds_a_resolvable_role_selector() -> None:
    """The target must be a selector Playwright can actually resolve. A CDP
    ``backendDOMNodeId`` is a DevTools-session id, not a DOM attribute, so a
    ``[data-...]`` selector built from it matches nothing and every click times
    out. The AX node already carries role + accessible name -- feed those to
    Playwright's role engine."""
    collected: list[Action] = []
    _extract_actions(CDP_AX, collected)
    admin = next(a for a in collected if "Admin panel" in a.label)
    assert admin.target == 'role=link[name="Admin panel"] >> nth=0'
    logout = next(a for a in collected if "Log out" in a.label)
    assert logout.target == 'role=button[name="Log out"] >> nth=0'


def test_extract_selector_escapes_quotes_in_the_name() -> None:
    ax: dict[str, Any] = {"nodes": [{"role": {"value": "button"}, "name": {"value": 'Say "hi"'}}]}
    collected: list[Action] = []
    _extract_actions(ax, collected)
    assert collected[0].target == r'role=button[name="Say \"hi\""] >> nth=0'


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


# ---------------------------------------------------------------------------
# LIVE -- a real browser against real HTML. The mocked tests above check the
# selector *string*; this checks it actually resolves and the click navigates.
# Run:  uv run pytest -m live tests/unit/crawler/
# ---------------------------------------------------------------------------


@pytest.mark.live
def test_enumerated_action_actually_clicks_through(tmp_path: Any) -> None:
    import http.server
    import threading

    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text(
        "<!doctype html><title>Home</title><h1>Home</h1>"
        '<nav><a href="settings.html">Settings</a></nav>'
    )
    (site / "settings.html").write_text(
        "<!doctype html><title>Settings</title><h1>Settings</h1>"
        '<nav><a href="index.html">Home</a></nav>'
    )

    handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(  # noqa: E731
        *a, directory=str(site), **kw
    )
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_address[1]

    crawler = PlaywrightCrawler(role="guest", output_dir=str(tmp_path / "shots"))
    try:
        home = crawler.open(f"http://127.0.0.1:{port}/index.html")
        actions = crawler.enumerate_actions(home)
        settings_link = next(a for a in actions if a.label == 'click "Settings"')

        after = crawler.act(settings_link)  # the bug: this used to time out

        assert after.url.endswith("/settings.html")
        assert "Settings" in after.title
    finally:
        crawler.close()
        httpd.shutdown()
