"""`observe` is a lean reload: DOM + title + background requests, no screenshot/AX capture."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest

from apps.agent.crawler.playwright_crawler import PlaywrightCrawler
from apps.agent.crawler.safety import SafetyPolicy

PAGE = (
    "<title>Live</title><div id=v>loading</div>"
    "<script>fetch('/api/thing').then(r=>r.json()).then(j=>{v.textContent='n='+j.n})</script>"
)


class _H(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path.startswith("/api/thing"):
            body, kind = b'{"n": 7}', "application/json"
        else:
            body, kind = PAGE.encode(), "text/html"
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a: Any) -> None:
        pass


@pytest.fixture()
def server() -> Iterator[str]:
    srv = HTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_observe_returns_rendered_dom_and_the_background_requests(
    server: str, tmp_path: Path
) -> None:
    c = PlaywrightCrawler(output_dir=str(tmp_path), probabilistic_states=True)
    try:
        c.open(server + "/")
        url, title, dom, calls = c.observe(server + "/")
    finally:
        c.close()
    assert url == server + "/" and title == "Live"
    assert "n=7" in dom  # waited for the page's own data request before reading the DOM
    assert calls == ("GET /api/thing",)


def test_observe_writes_no_screenshot_or_capture_files(server: str, tmp_path: Path) -> None:
    c = PlaywrightCrawler(output_dir=str(tmp_path), probabilistic_states=True)
    try:
        c.open(server + "/")
        before = len(list(tmp_path.iterdir()))
        for _ in range(3):
            c.observe(server + "/")
    finally:
        c.close()
    assert len(list(tmp_path.iterdir())) == before


def test_observe_goes_through_the_safety_gate(server: str, tmp_path: Path) -> None:
    from apps.agent.contracts import NavigationError

    c = PlaywrightCrawler(
        output_dir=str(tmp_path), probabilistic_states=True, safety=SafetyPolicy(max_pages=1)
    )
    try:
        c.open(server + "/")
        with pytest.raises(NavigationError):
            c.observe(server + "/other")  # a second distinct page is over the cap
    finally:
        c.close()
