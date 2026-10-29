"""Boots StockWatch on a free port and asserts every seeded flaw is present over HTTP."""

from __future__ import annotations

import json
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

APP = Path(__file__).resolve().parents[3] / "test-apps" / "stockwatch"
EXPECTED = json.loads((APP / "expected.json").read_text(encoding="utf-8"))


def _get(base: str, path: str, headers: dict[str, str] | None = None) -> tuple[int, str, Any]:
    req = urllib.request.Request(base + path, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read().decode(errors="replace"), r.headers
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode(errors="replace"), err.headers


def _post(base: str, path: str, data: dict) -> dict:
    req = urllib.request.Request(base + path, data=json.dumps(data).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


@pytest.fixture(scope="module")
def base() -> Iterator[str]:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen(
        [sys.executable, str(APP / "server.py"), "--port", str(port), "--seed", "7",
         "--tick-interval", "0", "--debug"], stdout=subprocess.PIPE, text=True)
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(50):
            try:
                _get(url, "/markets")
                break
            except OSError:
                time.sleep(0.1)
        else:
            pytest.fail("server did not start")
        yield url
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_expected_json_schema() -> None:
    flaws = EXPECTED["flaws"]
    ids = [f["id"] for f in flaws]
    assert len(ids) == len(set(ids)) == 10
    for f in flaws:
        assert set(f) == {"id", "description", "page", "rule_text", "severity"}
        assert all(isinstance(v, str) and v for v in f.values())
        assert f["severity"] in {"low", "medium", "high", "critical"}


def test_pages_are_reachable(base: str) -> None:
    for p in ["/markets", "/watchlist", "/portfolio", "/trade", "/news", "/news/1", "/settings",
              "/admin", "/login", "/about", "/stock/NVDA", "/static/app.js", "/static/app.css"]:
        assert _get(base, p)[0] == 200, p


def test_sw01_guest_sees_admin(base: str) -> None:
    _, markets, _ = _get(base, "/markets")
    assert 'href="/admin"' in markets
    assert ">guest<" in markets
    _, admin, _ = _get(base, "/admin")
    assert "Delete user" in admin


def _price_on_markets(html: str, sym: str) -> float:
    m = re.search(rf'<tr data-symbol="{sym}">.*?data-field="price">([\d.]+)<', html, re.S)
    assert m
    return float(m.group(1))


def test_sw02_ticket_price_differs(base: str) -> None:
    _, markets, _ = _get(base, "/markets")
    _, trade, _ = _get(base, "/trade?symbol=AAPL")
    m = re.search(r'data-testid="ticket-price"[^>]*>([\d.]+)<', trade)
    assert m
    assert float(m.group(1)) != _price_on_markets(markets, "AAPL")


def test_sw03_bad_orders_accepted(base: str) -> None:
    neg = _post(base, "/api/order", {"symbol": "AAPL", "side": "buy", "qty": -5})
    big = _post(base, "/api/order", {"symbol": "AAPL", "side": "buy", "qty": 10_000_000})
    assert neg["ok"] and "filled" in neg["message"]
    assert big["ok"] and big["cash"] < 0


def test_sw04_portfolio_total_mismatch(base: str) -> None:
    _, pf, _ = _get(base, "/portfolio")
    values = [float(v) for v in re.findall(r'data-field="value" data-qty="[^"]+">([\d.-]+)<', pf)]
    total = float(re.search(r'data-testid="portfolio-total"[^>]*>([\d.-]+)<', pf).group(1))  # type: ignore[union-attr]
    assert values and abs(total - sum(values)) > 1


def test_sw05_stale_timestamp(base: str) -> None:
    a = json.loads(_get(base, "/api/_tick?n=12")[1])
    assert a["ticks"] >= 12
    q1 = json.loads(_get(base, "/api/quotes")[1])
    json.loads(_get(base, "/api/_tick?n=5")[1])
    q2 = json.loads(_get(base, "/api/quotes")[1])
    assert q1["updated_at"] == q2["updated_at"]
    assert q1["quotes"]["AAPL"]["price"] != q2["quotes"]["AAPL"]["price"] or q1["seq"] != q2["seq"]
    assert q2["seq"] > q1["seq"]


def test_sw06_unnamed_icon_buttons(base: str) -> None:
    _, html, _ = _get(base, "/markets")
    stars = re.findall(r'<button[^>]*class="icon-btn star"[^>]*>', html)
    assert stars and all("aria-label" not in s and "title=" not in s for s in stars)
    assert 'aria-label="Toggle dark or light theme"' in html  # others stay accessible


def test_sw07_dead_links(base: str) -> None:
    _, html, _ = _get(base, "/markets")
    assert 'href="/legal/terms"' in html
    assert _get(base, "/legal/terms")[0] == 404
    assert _get(base, "/news/archive/2019")[0] == 404


def test_sw08_tracking_without_consent(base: str) -> None:
    _, html, _ = _get(base, "/markets")
    assert "cookie" not in html.lower().replace("/track.gif", "")
    assert "/track.gif" in html
    status, _, headers = _get(base, "/track.gif")
    assert status == 200 and any("_sw_uid" in c for c in headers.get_all("Set-Cookie"))


def test_sw09_pct_sign_contradiction(base: str) -> None:
    quotes = json.loads(_get(base, "/api/quotes")[1])["quotes"]
    bad = [s for s, q in quotes.items() if q["change"] * q["pct"] < 0]
    assert {"TSLA", "AMD"} <= set(bad)


def test_sw10_flaky_quote(base: str) -> None:
    codes, partial = [], 0
    for _ in range(120):
        code, body, _ = _get(base, "/api/quote?symbol=NVDA")
        codes.append(code)
        if code == 200 and "bid" not in json.loads(body):
            partial += 1
    failures = codes.count(503) + partial
    assert 0.08 < failures / 120 < 0.35
    assert codes.count(503) > 0 and partial > 0
    assert "Number(q.bid)" in _get(base, "/static/app.js")[1]  # rendered unguarded -> NaN
