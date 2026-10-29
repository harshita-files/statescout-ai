from __future__ import annotations

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

from apps.agent.contracts import Action, CaptureBundle, NavigationError
from apps.agent.crawler.playwright_crawler import PlaywrightCrawler
from apps.agent.crawler.safety import SafetyPolicy

ROBOTS = "User-agent: *\nDisallow: /private\n"


def pol(**kw: Any) -> SafetyPolicy:
    kw.setdefault("robots_fetcher", lambda url: (200, ROBOTS))
    return SafetyPolicy(**kw)


def b(dom: str = "", url: str = "http://a.test/", title: str = "") -> CaptureBundle:
    return CaptureBundle(url=url, dom=dom, ax_tree={}, title=title)


def test_robots_blocks_and_records() -> None:
    p = pol()
    assert p.check_navigation("http://a.test/") is None
    assert p.check_navigation("http://a.test/private/x") == "robots"
    assert [(n.url, n.reason) for n in p.blocked_notes()] == [("http://a.test/private/x", "robots")]


def test_robots_ignored_when_disabled() -> None:
    assert pol(respect_robots=False).check_navigation("http://a.test/private") is None


def test_robots_fetch_failure_allows_with_warning_and_caches() -> None:
    calls: list[str] = []

    def boom(url: str) -> tuple[int, str]:
        calls.append(url)
        raise OSError("down")

    p = SafetyPolicy(robots_fetcher=boom)
    assert p.check_navigation("http://a.test/private") is None
    assert p.check_navigation("http://a.test/other") is None
    assert len(calls) == 1 and p.warnings


def test_robots_404_allows_403_denies() -> None:
    assert (
        SafetyPolicy(robots_fetcher=lambda u: (404, "")).check_navigation("http://a.test/x") is None
    )
    assert (
        SafetyPolicy(robots_fetcher=lambda u: (403, "")).check_navigation("http://a.test/x")
        == "robots"
    )


def test_page_cap_and_time_cap() -> None:
    p = pol(max_pages=2)
    p.check_navigation("http://a.test/")
    p.record_page()
    p.record_page()
    assert p.check_navigation("http://a.test/x") == "cap"
    t = [0.0]
    q = pol(max_seconds=10, clock=lambda: t[0])
    assert q.check_navigation("http://a.test/") is None
    t[0] = 11
    assert q.check_navigation("http://a.test/") == "cap"


def test_same_origin_only() -> None:
    p = pol()
    p.check_navigation("http://a.test/")
    assert p.check_navigation("http://evil.test/") == "offsite"
    assert not p.blocked_notes()
    q = pol(same_origin_only=False)
    q.check_navigation("http://a.test/")
    assert q.check_navigation("http://other.test/") is None


def test_rate_limit_sleeps_per_host() -> None:
    sleeps: list[float] = []
    p = pol(requests_per_second=2, clock=lambda: 100.0, sleeper=sleeps.append)
    p.throttle("http://a.test/1")
    p.throttle("http://a.test/2")
    p.throttle("http://b.test/1")
    assert sleeps == [pytest.approx(0.5)]


@pytest.mark.parametrize(
    "label",
    [
        "Log out",
        "Sign out",
        "Delete account",
        "Buy now",
        "Pay",
        "Confirm order",
        "Unsubscribe",
        "Remove item",
    ],
)
def test_destructive_filtered(label: str) -> None:
    acts = (
        Action(action_id="1", kind="click", target="#x", label=f'click "{label}"'),
        Action(action_id="2", kind="click", target="#y", label='click "About"'),
    )
    assert [a.action_id for a in pol().filter_actions(acts)] == ["2"]
    assert len(pol(allow_destructive=True).filter_actions(acts)) == 2


def test_wall_detection() -> None:
    p = pol()
    assert p.detect_wall(b('<div class="g-recaptcha"></div>')) == "captcha"
    assert p.detect_wall(b("<p>Our systems detected unusual traffic</p>")) == "captcha"
    assert p.detect_wall(b("<p>Please verify you are human</p>")) == "captcha"
    assert p.detect_wall(b('<h1>Sign in</h1><input type="password">')) == "login_wall"
    assert p.detect_wall(b('<div id="onetrust-consent-sdk"></div>')) == "consent_wall"
    assert p.detect_wall(b("<h1>Hello</h1><a>About</a>")) is None
    assert p.detect_wall(b('<input type="password">')) is None  # no login hint


def test_check_bundle_records_note() -> None:
    p = pol()
    assert p.check_bundle(b("unusual traffic", url="http://a.test/z")) == "captcha"
    assert p.blocked_notes()[0].reason == "captcha"


# -- crawler wiring (no browser) ---------------------------------------------


def test_enumerate_actions_filters_destructive_only_with_safety() -> None:
    ax = {
        "role": "document",
        "children": [
            {"role": "button", "name": "Log out", "selector": "#o"},
            {"role": "link", "name": "Docs", "selector": "#d"},
        ],
    }
    bundle = CaptureBundle(url="http://a.test/", dom="", ax_tree=ax)
    assert len(PlaywrightCrawler().enumerate_actions(bundle)) == 2
    c = PlaywrightCrawler(safety=pol())
    assert [a.label for a in c.enumerate_actions(bundle)] == ['click "Docs"']
    assert c.blocked_notes() == ()
    assert PlaywrightCrawler().blocked_notes() == ()


def test_open_blocked_by_robots_raises_before_browser() -> None:
    c = PlaywrightCrawler(safety=pol())
    with pytest.raises(NavigationError, match="robots"):
        c.open("http://a.test/private")
    assert c.blocked_notes()[0].reason == "robots"


# -- real browser against a local server -------------------------------------


class _H(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        pages = {
            "/robots.txt": (200, "User-agent: *\nDisallow: /private\n"),
            "/": (200, "<title>Home</title><a href='/next'>Next</a><button>Log out</button>"),
            "/captcha": (
                200,
                "<title>x</title><div class='g-recaptcha'></div><a href='/next'>Go</a>",
            ),
            "/limited": (429, "slow down"),
        }
        status, body = pages.get(self.path, (404, "nf"))
        self.send_response(status)
        self.send_header(
            "Content-Type", "text/plain" if self.path == "/robots.txt" else "text/html"
        )
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *a: Any) -> None:
        pass


@pytest.fixture()
def server() -> Iterator[str]:
    srv = HTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_real_browser_walls_and_filtering(server: str, tmp_path: Any) -> None:
    p = SafetyPolicy(requests_per_second=100)
    c = PlaywrightCrawler(output_dir=str(tmp_path), safety=p)
    try:
        home = c.open(server + "/")
        labels = [a.label for a in c.enumerate_actions(home)]
        assert not any("Log out" in label for label in labels)
        cap = c.open(server + "/captcha")
        assert c.enumerate_actions(cap) == ()
        with pytest.raises(NavigationError):
            c.open(server + "/limited")
        with pytest.raises(NavigationError):
            c.open(server + "/private/x")
    finally:
        c.close()
    assert {n.reason for n in c.blocked_notes()} == {"captcha", "rate_limit", "robots"}


def test_cap_counts_distinct_urls_not_replays() -> None:
    p = pol(max_pages=2)
    for u in ("http://a.test/", "http://a.test/", "http://a.test/#tab", "http://a.test/b"):
        assert p.check_navigation(u) is None
        p.record_page(u)
    assert p.pages == 2
    assert p.check_navigation("http://a.test/") is None  # revisit is not a new page
    assert p.check_navigation("http://a.test/c") == "cap"
