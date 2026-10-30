"""Form probing: only eligible forms, only refusable values, and every guard is exercised."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, ClassVar

import pytest

from apps.agent.crawler.playwright_crawler import PlaywrightCrawler
from apps.agent.crawler.safety import is_local_target

ORDER_JS = (
    "document.getElementById('f').addEventListener('submit', e => { e.preventDefault();"
    " fetch('/api/order', {method:'POST', body: JSON.stringify({qty: q.value})})"
    ".then(r => r.json()).then(j => { msg.textContent = j.message; }); });"
)
PAGES = {
    "/trade": (
        "<h1>Trade</h1><form id=f><input id=q name=qty type=number value=1>"
        f"<button type=submit>Place order</button></form><p id=msg></p><script>{ORDER_JS}</script>"
    ),
    # Not eligible: a password field, a risky button, a cross-origin action, no numeric field.
    "/login": (
        "<form><input name=qty type=number><input type=password name=pw><button>Go</button></form>"
    ),
    "/pay": "<form><input name=amount type=number><button>Pay now</button></form>",
    "/offsite": (
        "<form action='http://elsewhere.invalid/x'><input name=qty type=number>"
        "<button>Send</button></form>"
    ),
    "/search": "<form><input name=q type=text><button>Search</button></form>",
}


class _H(BaseHTTPRequestHandler):
    posts: ClassVar[list[str]] = []
    flawed: ClassVar[bool] = True

    def _send(self, body: bytes, kind: str = "text/html", code: int = 200) -> None:
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        self._send(PAGES.get(self.path.split("?")[0], "<p>nf</p>").encode())

    def do_POST(self) -> None:
        n = int(self.headers.get("Content-Length", 0))
        self.posts.append(f"{self.path} {self.rfile.read(n).decode()}")
        ok = self.flawed
        msg = "Order filled" if ok else "Invalid quantity"
        self._send(json.dumps({"ok": ok, "message": msg}).encode(), "application/json")

    def log_message(self, *a: Any) -> None:
        pass


@pytest.fixture()
def server() -> Iterator[str]:
    _H.posts, _H.flawed = [], True
    srv = HTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def _probe(server: str, path: str, tmp: Path) -> list[Any]:
    c = PlaywrightCrawler(output_dir=str(tmp), probabilistic_states=True)
    try:
        c.open(server + "/trade")
        return c.probe_forms(server + path, ("-5", "1000000000"))
    finally:
        c.close()


def test_an_eligible_form_is_submitted_with_each_invalid_value(server: str, tmp_path: Path) -> None:
    got = _probe(server, "/trade", tmp_path)
    assert [p.value for p in got] == ["-5", "1000000000"] and {p.field for p in got} == {"qty"}
    assert all("Order filled" in p.after_dom and "Order filled" not in p.before_dom for p in got)
    assert [json.loads(x.split(" ", 1)[1])["qty"] for x in _H.posts] == ["-5", "1000000000"]


def test_a_server_that_validates_shows_its_error(server: str, tmp_path: Path) -> None:
    _H.flawed = False
    got = _probe(server, "/trade", tmp_path)
    assert all("Invalid quantity" in p.after_dom for p in got)


@pytest.mark.parametrize("path", ["/login", "/pay", "/offsite", "/search"])
def test_ineligible_forms_are_never_submitted(server: str, tmp_path: Path, path: str) -> None:
    assert _probe(server, path, tmp_path) == [] and _H.posts == []


@pytest.mark.parametrize(
    ("url", "local"),
    [
        ("http://localhost:8000/", True),
        ("http://127.0.0.1/x", True),
        ("http://192.168.1.5/", True),
        ("http://10.0.0.2:3000/", True),
        ("http://app.localhost/", True),
        ("https://www.google.com/", False),
        ("https://example.com/", False),
        ("http://8.8.8.8/", False),
        ("not a url", False),
    ],
)
def test_form_probing_is_limited_to_local_targets(url: str, local: bool) -> None:
    assert is_local_target(url, resolver=lambda h: []) is local
