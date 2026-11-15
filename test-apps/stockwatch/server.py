#!/usr/bin/env python3
# ruff: noqa: E501, SIM105
"""StockWatch - a polished, dynamic, deliberately FLAWED stock-market demo app.

Stdlib only.  Run:  python test-apps/stockwatch/server.py --port 8765 [--seed 7]
See README.md and expected.json for the seeded flaws.  Every flaw is on purpose.
"""

from __future__ import annotations

import argparse
import html
import json
import random
import secrets
import threading
import time
from collections import deque
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
STALE_AFTER_TICKS = 8  # FLAW 5: "Last updated" stops advancing after this many ticks
TICKET_MARKUP = 1.02  # FLAW 2: order ticket price = market price * 1.02
PORTFOLIO_ADJ = 1250.00  # FLAW 4: phantom amount added to the portfolio total
INVERTED_PCT = {"TSLA", "AMD"}  # FLAW 9: % change sign flipped for these tickers

# symbol, name, sector, base price, volume
TICKERS = [
    ("AAPL", "Apple Inc.", "Tech", 189.3, 52_000_000),
    ("MSFT", "Microsoft Corp.", "Tech", 415.1, 21_000_000),
    ("NVDA", "NVIDIA Corp.", "Tech", 875.4, 43_000_000),
    ("GOOGL", "Alphabet Inc.", "Tech", 152.6, 24_000_000),
    ("AMZN", "Amazon.com Inc.", "Consumer", 178.2, 38_000_000),
    ("TSLA", "Tesla Inc.", "Auto", 175.8, 91_000_000),
    ("META", "Meta Platforms", "Tech", 495.7, 14_000_000),
    ("JPM", "JPMorgan Chase", "Finance", 195.4, 9_000_000),
    ("XOM", "Exxon Mobil", "Energy", 118.9, 15_000_000),
    ("JNJ", "Johnson & Johnson", "Health", 156.2, 7_000_000),
    ("AMD", "Advanced Micro Devices", "Tech", 165.3, 48_000_000),
    ("SPY", "SPDR S&P 500 ETF", "ETF", 520.6, 70_000_000),
    ("QQQ", "Invesco QQQ Trust", "ETF", 440.2, 40_000_000),
    ("DIA", "SPDR Dow Jones ETF", "ETF", 390.8, 4_000_000),
]
SECTORS = ["All", "Tech", "Consumer", "Auto", "Finance", "Energy", "Health", "ETF"]
INFO = {t[0]: t for t in TICKERS}
NAV = [("Markets", "/markets"), ("Watchlist", "/watchlist"), ("Portfolio", "/portfolio"),
       ("Trade", "/trade"), ("News", "/news"), ("Settings", "/settings"), ("Admin", "/admin")]
ROLES = {
    "guest": "Browse markets without an account.",
    "trader": "Place orders and manage a portfolio.",
    "admin": "Manage users and platform settings.",
}
NEWS = [
    (1, "Chipmakers rally as AI demand outlook brightens", "NVDA", 12),
    (2, "Fed minutes hint at slower pace of rate cuts", "SPY", 47),
    (3, "Oil slips as inventories build more than expected", "XOM", 95),
    (4, "Automakers weigh price cuts amid softer EV demand", "TSLA", 180),
    (5, "Cloud spending steady; software names hold gains", "MSFT", 260),
]
USERS = [(1, "ava.martin", "trader"), (2, "ben.okafor", "trader"), (3, "chen.li", "admin"),
         (4, "dara.novak", "trader")]


class Market:
    def __init__(self, seed: int | None, interval: float) -> None:
        self.seed = seed
        self.interval = interval
        self.rng = random.Random(seed)
        self.flaky = random.Random(None if seed is None else seed * 7 + 1)
        self.promo_rng = random.Random(None if seed is None else seed * 13 + 5)
        self.lock = threading.Lock()
        self.ticks = 0
        self.prices: dict[str, float] = {}
        self.prev: dict[str, float] = {}
        self.vol: dict[str, int] = {}
        self.hist: dict[str, deque[float]] = {}
        for sym, _n, _s, base, vol in TICKERS:
            p = base
            seq = []
            for _ in range(40):
                p *= 1 + self.rng.gauss(0, 0.002)
                seq.append(round(p, 2))
            self.hist[sym] = deque(seq, maxlen=40)
            self.prices[sym] = seq[-1]
            prev = round(base * (1 + self.rng.uniform(-0.012, 0.012)), 2)
            if prev == seq[-1]:
                prev += 0.07
            self.prev[sym] = prev
            self.vol[sym] = int(vol * self.rng.uniform(0.8, 1.2))
        self.updated_at = time.strftime("%H:%M:%S")
        self.started = time.time()

    def tick(self) -> None:
        with self.lock:
            self.ticks += 1
            for sym in self.prices:
                p = self.prices[sym] * (1 + self.rng.gauss(0, 0.0016))
                self.prices[sym] = round(p, 2)
                self.hist[sym].append(self.prices[sym])
                self.vol[sym] += self.rng.randint(1_000, 40_000)
            if self.ticks <= STALE_AFTER_TICKS:
                self.updated_at = time.strftime("%H:%M:%S")  # then frozen: FLAW 5

    def quote(self, sym: str) -> dict:
        p, pv = self.prices[sym], self.prev[sym]
        ch = round(p - pv, 2)
        pct = round(ch / pv * 100, 2)
        if sym in INVERTED_PCT:
            pct = -pct  # FLAW 9
        return {"price": p, "change": ch, "pct": pct, "volume": self.vol[sym],
                "spark": list(self.hist[sym])}

    def snapshot(self) -> dict:
        with self.lock:
            return {"seq": self.ticks, "updated_at": self.updated_at,
                    "server_time": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "quotes": {s: self.quote(s) for s in self.prices}}

    def candles(self, sym: str, n: int) -> list[dict]:
        r = random.Random(f"{self.seed}:{sym}")
        with self.lock:
            end = self.prices[sym]
        closes = [end]
        for _ in range(n - 1):
            closes.append(closes[-1] / (1 + r.gauss(0, 0.006)))
        closes.reverse()
        out, prev = [], closes[0]
        for i, c in enumerate(closes):
            hi = max(prev, c) * (1 + abs(r.gauss(0, 0.003)))
            lo = min(prev, c) * (1 - abs(r.gauss(0, 0.003)))
            out.append({"t": i, "o": round(prev, 2), "h": round(hi, 2), "l": round(lo, 2),
                        "c": round(c, 2)})
            prev = c
        return out

    def rand(self, rng: random.Random) -> float:
        with self.lock:
            return rng.random()


class Session:
    def __init__(self) -> None:
        self.role = "guest"
        self.watch = {"AAPL", "NVDA"}
        self.cash = 25_000.0
        self.holdings = {"AAPL": 10.0, "MSFT": 5.0, "NVDA": 8.0, "TSLA": 12.0}
        self.saved = False


MARKET: Market
SESSIONS: dict[str, Session] = {}
DELETED_USERS: set[int] = set()
DEBUG = False


def e(s: object) -> str:
    return html.escape(str(s), quote=True)


def spark_svg(sym: str, vals: list[float], up: bool) -> str:
    lo, hi = min(vals), max(vals)
    rg = (hi - lo) or 1
    pts = [f"{'M' if i == 0 else 'L'}{i * 110 / (len(vals) - 1):.1f} {28 - (v - lo) / rg * 26:.1f}"
           for i, v in enumerate(vals)]
    return (f'<svg class="spark {"up" if up else "down"}" data-symbol="{sym}" viewBox="0 0 110 30" '
            f'role="img" aria-label="{sym} 40 tick trend"><path d="{" ".join(pts)}"/></svg>')


def sgn(x: float) -> str:
    return f"{x:+.2f}"


STAR = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1'
        'L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z"/></svg>')
SEARCH_ICON = ('<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/>'
               '<path d="M21 21l-4.3-4.3"/></svg>')


def star_btn(sym: str, on: bool) -> str:
    # FLAW 6: icon-only button with no accessible name (no aria-label / title / text)
    return (f'<button type="button" class="icon-btn star" data-symbol="{sym}" '
            f'aria-pressed="{"true" if on else "false"}">{STAR}</button>')


def layout(sess: Session, path: str, title: str, body: str, page: str = "") -> str:
    snap = MARKET.snapshot()
    nav = "".join(
        f'<a href="{h}"{" aria-current=page" if path.startswith(h) else ""}>{n}</a>'
        for n, h in NAV)  # FLAW 1: Admin is shown to every role, guests included
    items = ""
    for sym, q in snap["quotes"].items():
        d = "up" if q["change"] >= 0 else "down"
        items += (f'<span class="tape-item"><b>{sym}</b><span data-symbol="{sym}" data-field="price">'
                  f'{q["price"]:.2f}</span><span class="num {d}" data-symbol="{sym}" '
                  f'data-field="pct">{q["pct"]:+.2f}%</span></span>')
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)} - StockWatch</title>
<script>try{{var t=localStorage.getItem('sw-theme');if(t)document.documentElement.setAttribute('data-theme',t)}}catch(e){{}}</script>
<link rel="stylesheet" href="/static/app.css"></head>
<body data-page="{page}">
<a class="skip" href="#main">Skip to content</a>
<header class="top"><div class="bar">
<a class="brand" href="/markets"><span class="logo" aria-hidden="true">&#9650;</span>StockWatch</a>
<nav class="main" aria-label="Primary">{nav}</nav>
<div class="tools"><span class="role" data-testid="role-badge">{sess.role}</span>
<button type="button" id="theme-toggle" class="icon-btn" aria-label="Toggle dark or light theme"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 12.8A9 9 0 1111.2 3a7 7 0 009.8 9.8z"/></svg></button>
<a class="btn sm" href="/login">{"Sign in" if sess.role == "guest" else "Switch role"}</a></div></div>
<div class="tape" aria-label="Live ticker tape" role="marquee"><div class="tape-track">{items}{items}</div></div></header>
<div class="statusbar"><span class="live"><i></i>LIVE</span>
<span>Last updated: <time id="last-updated" data-testid="last-updated">{snap["updated_at"]}</time></span>
<span class="hide-sm">Delayed quotes are simulated.</span></div>
<main id="main">{body}</main>
<footer><div class="in"><span>&copy; 2026 StockWatch Demo. Not financial advice. Simulated data.</span>
<nav aria-label="Footer"><a href="/about">About</a><a href="/news">News</a><a href="/legal/terms">Terms of service</a><a href="/legal/privacy">Privacy</a></nav></div></footer>
<img src="/track.gif?p={e(path)}" width="1" height="1" alt="" style="position:absolute;left:-9999px">
<script src="/static/app.js" defer></script></body></html>"""


def quote_rows(sess: Session, syms: list[str], with_star: bool = True) -> str:
    snap = MARKET.snapshot()["quotes"]
    out = ""
    for sym in syms:
        q = snap[sym]
        d = "up" if q["change"] >= 0 else "down"
        out += (f'<tr data-symbol="{sym}"><td>{star_btn(sym, sym in sess.watch) if with_star else ""}</td>'
                f'<td><a class="sym" href="/stock/{sym}">{sym}</a></td><td class="name">{e(INFO[sym][1])}</td>'
                f'<td class="num" data-symbol="{sym}" data-field="price">{q["price"]:.2f}</td>'
                f'<td class="num {d}" data-symbol="{sym}" data-field="change">{sgn(q["change"])}</td>'
                f'<td class="num {d}" data-symbol="{sym}" data-field="pct">{q["pct"]:+.2f}%</td>'
                f'<td class="num hide-sm" data-symbol="{sym}" data-field="volume">{q["volume"]:,}</td>'
                f'<td>{spark_svg(sym, q["spark"], q["change"] >= 0)}</td>'
                f'<td><a class="btn sm" href="/trade?symbol={sym}&amp;side=buy">Trade</a></td></tr>')
    return out


THEAD = ["", "symbol", "name", "price", "change", "pct", "volume", "", ""]


def table(sess: Session, syms: list[str], sort: str, direction: str, qs: dict[str, str]) -> str:
    heads = ""
    labels = {"symbol": "Symbol", "name": "Name", "price": "Price", "change": "Chg", "pct": "% Chg",
              "volume": "Volume"}
    for key in THEAD:
        if not key:
            heads += '<th scope="col"><span class="sr">&nbsp;</span></th>'
            continue
        nd = "desc" if (sort == key and direction == "asc") else "asc"
        link = "&amp;".join([f"sort={key}", f"dir={nd}"] + [f"{k}={e(v)}" for k, v in qs.items() if v])
        aria = (' aria-sort="ascending"' if direction == "asc" else ' aria-sort="descending"') \
            if sort == key else ""
        cls = ' class="num"' if key in ("price", "change", "pct", "volume") else ""
        heads += f'<th scope="col"{cls}{aria}><a href="?{link}">{labels[key]}</a></th>'
    return (f'<div class="tablewrap"><table id="quotes" data-testid="quotes-table"><thead><tr>{heads}</tr></thead>'
            f'<tbody>{quote_rows(sess, syms)}</tbody></table></div>')


def page_markets(sess: Session, qs: dict[str, str]) -> str:
    q, sector = qs.get("q", ""), qs.get("sector", "All")
    sort, direction = qs.get("sort", "symbol"), qs.get("dir", "asc")
    snap = MARKET.snapshot()["quotes"]
    syms = [t[0] for t in TICKERS if (sector in ("All", "") or t[2] == sector)
            and (not q or q.lower() in (t[0] + t[1]).lower())]
    keyf = {"symbol": lambda s: s, "name": lambda s: INFO[s][1], "price": lambda s: snap[s]["price"],
            "change": lambda s: snap[s]["change"], "pct": lambda s: snap[s]["pct"],
            "volume": lambda s: snap[s]["volume"]}.get(sort, lambda s: s)
    syms.sort(key=keyf, reverse=(direction == "desc"))
    cards = ""
    for sym in ("SPY", "QQQ", "DIA"):
        x = snap[sym]
        d = "up" if x["change"] >= 0 else "down"
        cards += (f'<a class="card kpi" href="/stock/{sym}" style="color:inherit"><span class="lbl">{e(INFO[sym][1])}</span>'
                  f'<div class="idx"><span class="val" data-symbol="{sym}" data-field="price">{x["price"]:.2f}</span>'
                  f'{spark_svg(sym, x["spark"], x["change"] >= 0)}</div>'
                  f'<span class="num {d}" data-symbol="{sym}" data-field="pct">{x["pct"]:+.2f}%</span></a>')
    chips = "".join(
        f'<a class="chip" href="/markets?sector={s}"{" aria-current=true" if s == (sector or "All") else ""}>{s}</a>'
        for s in SECTORS)
    body = f"""<h1>Markets</h1><p class="sub">Live prices across {len(TICKERS)} instruments.</p>
<section class="grid g3" aria-label="Indices">{cards}</section>
<div class="toolbar" style="margin-top:20px"><form class="search" role="search" action="/markets" method="get">
<input id="q" name="q" type="search" value="{e(q)}" placeholder="Search symbol or company" aria-label="Search symbol or company">
<button class="icon-btn" type="submit">{SEARCH_ICON}</button></form><div class="chips">{chips}</div></div>
{table(sess, syms, sort, direction, {"q": q, "sector": sector}) if syms else '<p class="empty">No matches. <a href="/markets">Reset filters</a></p>'}"""
    return layout(sess, "/markets", "Markets", body, "markets")


def page_watchlist(sess: Session) -> str:
    syms = [t[0] for t in TICKERS if t[0] in sess.watch]
    inner = (table(sess, syms, "symbol", "asc", {}) if syms else
             '<div class="card empty">Nothing on your watchlist yet. Star a ticker on '
             '<a href="/markets">Markets</a>.</div>')
    return layout(sess, "/watchlist", "Watchlist",
                  f'<h1>Watchlist</h1><p class="sub">{len(syms)} symbols you follow.</p>{inner}', "watchlist")


def page_portfolio(sess: Session) -> str:
    snap = MARKET.snapshot()["quotes"]
    rows, total, parts = "", 0.0, ""
    colors = ["#5b8cff", "#7c5cff", "#22c55e", "#f5b301", "#ef4444", "#14b8a6"]
    vals = {s: q * snap[s]["price"] for s, q in sess.holdings.items() if q}
    for i, (sym, qty) in enumerate(sess.holdings.items()):
        v = round(qty * snap[sym]["price"], 2)
        total += v
        d = "up" if snap[sym]["change"] >= 0 else "down"
        rows += (f'<tr data-symbol="{sym}"><td><a class="sym" href="/stock/{sym}">{sym}</a></td>'
                 f'<td class="num">{qty:g}</td><td class="num" data-symbol="{sym}" data-field="price">'
                 f'{snap[sym]["price"]:.2f}</td><td class="num {d}" data-symbol="{sym}" data-field="pct">'
                 f'{snap[sym]["pct"]:+.2f}%</td><td class="num" data-symbol="{sym}" data-field="value" '
                 f'data-qty="{qty}">{v:.2f}</td><td><a class="btn sm sell" href="/trade?symbol={sym}&amp;side=sell">Sell</a></td></tr>')
        if vals.get(sym, 0) > 0:
            w = vals[sym] / sum(x for x in vals.values() if x > 0) * 100
            parts += f'<span title="{sym}" style="width:{w:.1f}%;background:{colors[i % 6]}"></span>'
    shown = total + PORTFOLIO_ADJ  # FLAW 4: does not equal the sum of the holdings
    body = f"""<h1>Portfolio</h1><p class="sub">Account for role <strong>{sess.role}</strong>.</p>
<section class="grid g3"><div class="card kpi"><span class="lbl">Cash</span><span class="val" data-testid="cash">${sess.cash:,.2f}</span></div>
<div class="card kpi"><span class="lbl">Holdings</span><span class="val">{len(sess.holdings)} positions</span></div>
<div class="card kpi"><span class="lbl">Total value</span><span class="val">$<span id="pf-total" data-testid="portfolio-total" data-field="pftotal" data-adj="{PORTFOLIO_ADJ}">{shown:.2f}</span></span></div></section>
<div class="bar-alloc" aria-hidden="true">{parts}</div>
<h2 style="margin-top:22px">Holdings</h2><div class="tablewrap"><table id="holdings" data-testid="holdings-table"><thead><tr>
<th scope="col">Symbol</th><th scope="col" class="num">Qty</th><th scope="col" class="num">Price</th><th scope="col" class="num">% Chg</th><th scope="col" class="num">Value</th><th scope="col">Action</th></tr></thead><tbody>{rows}</tbody></table></div>"""
    return layout(sess, "/portfolio", "Portfolio", body, "portfolio")


def page_trade(sess: Session, qs: dict[str, str], result: dict | None = None) -> str:
    sym = qs.get("symbol", "AAPL").upper()
    sym = sym if sym in INFO else "AAPL"
    side = "sell" if qs.get("side") == "sell" else "buy"
    q = MARKET.snapshot()["quotes"][sym]
    opts = "".join(f'<option value="{t[0]}"{" selected" if t[0] == sym else ""}>{t[0]} - {e(t[1])}</option>'
                   for t in TICKERS)
    note = ""
    if result:
        note = f'<div class="notice {"ok" if result["ok"] else "err"}" role="status">{e(result["message"])}</div>'
    body = f"""<h1>Trade</h1><p class="sub">Place a simulated market or limit order.</p>
<div class="grid g2"><form class="card stack" id="order-form" method="post" action="/trade">
<div id="order-result" role="status" class="notice" hidden></div>{note}
<label for="symbol">Symbol<select id="symbol" name="symbol">{opts}</select></label>
<fieldset class="sidepick" style="border:0;padding:0;margin:0"><legend class="meta" style="margin-bottom:6px">Side</legend>
<label><input type="radio" name="side" value="buy"{" checked" if side == "buy" else ""}><span class="b">Buy</span></label>
<label><input type="radio" name="side" value="sell"{" checked" if side == "sell" else ""}><span class="s">Sell</span></label></fieldset>
<label for="qty">Quantity<input id="qty" name="qty" type="number" value="1" step="any"></label>
<label for="otype">Order type<select id="otype" name="type"><option value="market">Market</option><option value="limit">Limit</option></select></label>
<button class="btn primary" type="submit" id="place-order">Place order</button></form>
<aside class="card"><h2>Order ticket</h2><div class="meta">Market price</div>
<div class="price-big" data-testid="ticket-price" data-symbol="{sym}" data-field="ticket">{q["price"] * TICKET_MARKUP:.2f}</div>
<p class="meta">Cash available: <strong data-testid="cash">${sess.cash:,.2f}</strong></p>
<p><a href="/stock/{sym}">View {sym} details</a> &middot; <a href="/portfolio">Portfolio</a></p></aside></div>"""
    return layout(sess, "/trade", "Trade", body, "trade")


def page_stock(sess: Session, sym: str) -> str:
    t = INFO[sym]
    q = MARKET.snapshot()["quotes"][sym]
    d = "up" if q["change"] >= 0 else "down"
    related = "".join(f'<a class="chip" href="/stock/{x[0]}">{x[0]}</a>' for x in TICKERS
                      if x[2] == t[2] and x[0] != sym) or '<span class="meta">none</span>'
    fin = "".join(f"<tr><th scope='row'>{k}</th><td class='num'>{v}</td></tr>" for k, v in [
        ("Market cap", f"${q['price'] * 14.2:,.1f}B"), ("P/E ratio", "28.4"), ("EPS (TTM)", "6.51"),
        ("Dividend yield", "0.55%"), ("52-week range", f"{q['price'] * .72:.2f} - {q['price'] * 1.18:.2f}")])
    body = f"""<div id="stock-page" data-symbol="{sym}"><p class="meta"><a href="/markets">Markets</a> / {sym}</p>
<div class="hero"><div><h1>{e(t[1])} <span class="tag">{sym}</span> <span class="tag">{t[2]}</span></h1>
<div><span class="price-big" data-symbol="{sym}" data-field="price">{q["price"]:.2f}</span>
<span class="num {d}" data-symbol="{sym}" data-field="pct" style="font-size:20px;font-weight:700">{q["pct"]:+.2f}%</span></div></div>
<div class="row" style="margin:0">{star_btn(sym, sym in sess.watch)}
<a class="btn buy" href="/trade?symbol={sym}&amp;side=buy">Buy</a><a class="btn sell" href="/trade?symbol={sym}&amp;side=sell">Sell</a></div></div>
<div class="tabs" role="tablist"><a class="tab" role="tab" data-tab="overview" href="#overview">Overview</a>
<a class="tab" role="tab" data-tab="chart" href="#chart">Chart</a><a class="tab" role="tab" data-tab="financials" href="#financials">Financials</a></div>
<section data-panel="overview"><div id="q-err" class="notice err" role="alert" hidden>Quote service unavailable. <button type="button" class="btn sm" id="q-retry">Retry</button></div>
<dl class="dl"><div><dt>Bid</dt><dd id="q-bid">...</dd></div><div><dt>Ask</dt><dd id="q-ask">...</dd></div><div><dt>Volume</dt><dd id="q-vol">...</dd></div></dl>
<h2 style="margin-top:22px">Related</h2><div class="chips">{related}</div></section>
<section data-panel="chart" hidden><div class="toolbar"><div class="seg" role="group" aria-label="Chart type">
<button type="button" data-mode="candles" aria-pressed="true">Candles</button><button type="button" data-mode="line" aria-pressed="false">Line</button></div></div><div id="chart"></div></section>
<section data-panel="financials" hidden><div class="tablewrap"><table><tbody>{fin}</tbody></table></div></section></div>"""
    return layout(sess, "/stock", f"{sym} quote", body, "stock")


def page_news(sess: Session) -> str:
    now = time.time() - MARKET.started
    cards = "".join(
        f'<article class="card"><span class="tag">{s}</span><h3><a href="/news/{i}">{e(t)}</a></h3>'
        f'<span class="meta">{int((m * 60 + now) // 60)} minutes ago &middot; StockWatch Desk</span></article>'
        for i, t, s, m in NEWS)
    body = f'<h1>News</h1><p class="sub">Market-moving headlines.</p><div class="news">{cards}</div><p><a href="/news/archive/2019">Browse the 2019 archive</a></p>'
    return layout(sess, "/news", "News", body, "news")


def page_article(sess: Session, aid: int) -> str:
    a = next((n for n in NEWS if n[0] == aid), None)
    if not a:
        return page_404(sess, f"/news/{aid}")
    body = (f'<p class="meta"><a href="/news">News</a> / Article</p><article class="card"><h1>{e(a[1])}</h1>'
            f'<p class="meta">Related: <a href="/stock/{a[2]}">{a[2]}</a></p>'
            f'<p>Analysts said the move reflects shifting expectations. Prices for {a[2]} are shown live on the '
            f'<a href="/markets">Markets</a> page. Published {time.strftime("%H:%M")} server time.</p></article>')
    return layout(sess, "/news", a[1], body, "article")


def page_settings(sess: Session, saved: bool) -> str:
    note = '<div class="notice ok" role="status">Settings saved.</div>' if saved else ""
    body = f"""<h1>Settings</h1><p class="sub">Preferences for this browser session.</p>{note}
<form class="card stack" method="post" action="/settings" style="max-width:520px">
<label for="cur">Display currency<select id="cur" name="currency"><option>USD</option><option>EUR</option><option>GBP</option></select></label>
<label class="inline"><input type="checkbox" name="alerts" checked> Price alerts by email</label>
<label class="inline"><input type="checkbox" name="twofa"> Require two-factor authentication</label>
<label for="refresh">Refresh interval<select id="refresh" name="refresh"><option value="2">2 seconds</option><option value="5">5 seconds</option></select></label>
<div class="row" style="margin:0"><button class="btn primary" type="submit">Save settings</button><a class="btn" href="/markets">Cancel</a></div></form>"""
    return layout(sess, "/settings", "Settings", body, "settings")


def page_admin(sess: Session) -> str:
    # FLAW 1: no role check at all; guests see the full user table and destructive controls
    rows = "".join(
        f'<tr><td>{uid}</td><td>{e(name)}</td><td>{role}</td><td><form method="post" action="/admin/delete">'
        f'<input type="hidden" name="id" value="{uid}"><button class="btn danger sm" type="submit">Delete user</button></form></td></tr>'
        for uid, name, role in USERS if uid not in DELETED_USERS)
    body = f"""<h1>Admin console</h1><p class="sub">Manage platform users. Signed in as <strong>{sess.role}</strong>.</p>
<div class="tablewrap"><table data-testid="users-table"><thead><tr><th scope="col">ID</th><th scope="col">User</th><th scope="col">Role</th><th scope="col">Actions</th></tr></thead><tbody>{rows}</tbody></table></div>
<p><a class="btn" href="/settings">Platform settings</a></p>"""
    return layout(sess, "/admin", "Admin", body, "admin")


def page_login(sess: Session) -> str:
    cards = "".join(
        f'<form class="card stack" method="post" action="/login"><h2>{r.title()}</h2><p class="meta">{d}</p>'
        f'<input type="hidden" name="role" value="{r}"><button class="btn {"primary" if r == "trader" else ""}" type="submit">Continue as {r}</button></form>'
        for r, d in ROLES.items())
    return layout(sess, "/login", "Sign in", f'<h1>Choose a role</h1><p class="sub">Demo sign-in, no password needed. Current role: {sess.role}.</p><div class="rolecards">{cards}</div>', "login")


def page_about(sess: Session) -> str:
    return layout(sess, "/about", "About", '<h1>About StockWatch</h1><div class="card"><p>StockWatch is a simulated market dashboard used as a test target. See <a href="/markets">Markets</a> or <a href="/news">News</a>.</p></div>', "about")


def page_404(sess: Session, path: str) -> str:
    return layout(sess, path, "Not found", f'<div class="card empty"><h1>404 - Page not found</h1><p>No page at <code>{e(path)}</code>.</p><a class="btn primary" href="/markets">Back to Markets</a></div>', "404")


def place_order(sess: Session, data: dict) -> dict:
    sym = str(data.get("symbol", "AAPL")).upper()
    side = "sell" if data.get("side") == "sell" else "buy"
    try:
        qty = float(data.get("qty", 0))
    except (TypeError, ValueError):
        qty = 0.0
    if sym not in INFO:
        return {"ok": False, "message": f"Unknown symbol {sym}"}
    price = round(MARKET.snapshot()["quotes"][sym]["price"] * TICKET_MARKUP, 2)
    # FLAW 3: no validation of quantity sign/size or available cash - always "filled"
    cost = qty * price
    if side == "buy":
        sess.cash -= cost
        sess.holdings[sym] = sess.holdings.get(sym, 0.0) + qty
    else:
        sess.cash += cost
        sess.holdings[sym] = sess.holdings.get(sym, 0.0) - qty
    return {"ok": True, "status": "filled", "symbol": sym, "side": side, "qty": qty, "price": price,
            "cash": round(sess.cash, 2),
            "message": f"Order filled: {side.upper()} {qty:g} {sym} @ {price:.2f}"}


GIF = bytes.fromhex("47494638396101000100800000000000ffffff21f90401000000002c00000000010001000002024401003b")


class Handler(BaseHTTPRequestHandler):
    server_version = "StockWatch/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, *_a: object) -> None:
        pass

    # --- helpers
    def _session(self) -> tuple[Session, str | None]:
        ck = SimpleCookie(self.headers.get("Cookie", ""))
        sid = ck["sw_sid"].value if "sw_sid" in ck else ""
        if sid in SESSIONS:
            return SESSIONS[sid], None
        sid = secrets.token_hex(8)
        SESSIONS[sid] = Session()
        return SESSIONS[sid], sid

    def _send(self, code: int, body: bytes, ctype: str, extra: list[tuple[str, str]] | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or []) + self._cookies:
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _html(self, s: str, code: int = 200) -> None:
        self._send(code, s.encode(), "text/html; charset=utf-8")

    def _json(self, obj: object, code: int = 200) -> None:
        self._send(code, json.dumps(obj).encode(), "application/json")

    def _redirect(self, to: str) -> None:
        self._send(303, b"", "text/plain", [("Location", to)])

    def _form(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n).decode() if n else ""
        if "json" in (self.headers.get("Content-Type") or ""):
            try:
                v = json.loads(raw or "{}")
                return v if isinstance(v, dict) else {}
            except ValueError:
                return {}
        return {k: v[0] for k, v in parse_qs(raw).items()}

    # --- dispatch
    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        self._cookies: list[tuple[str, str]] = []
        sess, new = self._session()
        if new:
            self._cookies.append(("Set-Cookie", f"sw_sid={new}; Path=/; HttpOnly; SameSite=Lax"))
        u = urlparse(self.path)
        path = u.path.rstrip("/") or "/"
        qs = {k: v[0] for k, v in parse_qs(u.query).items()}
        if path == "/":
            return self._redirect("/markets")
        if path.startswith("/static/"):
            f = (STATIC / path[8:]).resolve()
            if STATIC in f.parents and f.is_file():
                ct = {"css": "text/css", "js": "text/javascript"}.get(f.suffix[1:], "text/plain")
                return self._send(200, f.read_bytes(), ct + "; charset=utf-8")
            return self._html(page_404(sess, path), 404)
        if path.startswith("/api/") or path == "/track.gif":
            return self._api_get(path, qs, sess)
        pages = {"/markets": lambda: page_markets(sess, qs), "/watchlist": lambda: page_watchlist(sess),
                 "/portfolio": lambda: page_portfolio(sess), "/trade": lambda: page_trade(sess, qs),
                 "/news": lambda: page_news(sess), "/settings": lambda: page_settings(sess, "saved" in qs),
                 "/admin": lambda: page_admin(sess), "/login": lambda: page_login(sess),
                 "/about": lambda: page_about(sess)}
        if path in pages:
            return self._html(pages[path]())
        if path.startswith("/stock/") and path[7:].upper() in INFO:
            return self._html(page_stock(sess, path[7:].upper()))
        if path.startswith("/news/") and path[6:].isdigit():
            return self._html(page_article(sess, int(path[6:])))
        # FLAWS 7: /legal/terms, /legal/privacy and /news/archive/2019 are linked but do not exist
        self._html(page_404(sess, path), 404)

    def _api_get(self, path: str, qs: dict[str, str], sess: Session) -> None:
        if path == "/track.gif":  # FLAW 8: tracking pixel + persistent id cookie without any consent
            self._cookies.append(("Set-Cookie", "_sw_uid=" + secrets.token_hex(6) + "; Path=/; Max-Age=31536000"))
            return self._send(200, GIF, "image/gif")
        if path == "/api/quotes":
            return self._json(MARKET.snapshot())
        if path == "/api/stream":
            return self._stream()
        if path == "/api/quote":
            sym = qs.get("symbol", "").upper()
            if sym not in INFO:
                return self._json({"error": "unknown symbol"}, 404)
            u = MARKET.rand(MARKET.flaky)
            if u < 0.10:  # FLAW 10a: transient failure
                return self._json({"error": "upstream timeout"}, 503)
            q = MARKET.snapshot()["quotes"][sym]
            full = {"symbol": sym, "price": q["price"], "bid": round(q["price"] - 0.02, 2),
                    "ask": round(q["price"] + 0.02, 2), "volume": q["volume"]}
            if u < 0.20:  # FLAW 10b: 200 OK with missing fields -> UI shows NaN / undefined
                return self._json({"symbol": sym, "price": q["price"]})
            return self._json(full)
        if path == "/api/candles":
            sym = qs.get("symbol", "").upper()
            if sym not in INFO:
                return self._json({"error": "unknown symbol"}, 404)
            n = max(8, min(120, int(qs.get("n", "48") or 48)))
            return self._json({"symbol": sym, "candles": MARKET.candles(sym, n)})
        if path == "/api/promo":  # non-deterministic promo modal (35%)
            if MARKET.rand(MARKET.promo_rng) < 0.35:
                return self._json({"id": "nvda-fee-free", "title": "Zero-fee week on NVDA",
                                   "body": "Trade NVDA commission-free until Friday.",
                                   "href": "/trade?symbol=NVDA&side=buy"})
            return self._json({})
        if path == "/api/_tick" and DEBUG:
            for _ in range(int(qs.get("n", "1"))):
                MARKET.tick()
            return self._json({"ticks": MARKET.ticks})
        if path == "/api/me":
            return self._json({"role": sess.role, "watch": sorted(sess.watch), "cash": sess.cash})
        self._json({"error": "not found"}, 404)

    def _stream(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        try:
            while True:
                self.wfile.write(b"retry: 3000\ndata: " + json.dumps(MARKET.snapshot()).encode() + b"\n\n")
                self.wfile.flush()
                if MARKET.interval <= 0:
                    return
                time.sleep(MARKET.interval)
        except (BrokenPipeError, ConnectionResetError, OSError):
            return

    def do_POST(self) -> None:
        self._cookies = []
        sess, new = self._session()
        if new:
            self._cookies.append(("Set-Cookie", f"sw_sid={new}; Path=/; HttpOnly; SameSite=Lax"))
        path = urlparse(self.path).path.rstrip("/")
        data = self._form()
        if path == "/login":
            role = data.get("role", "guest")
            sess.role = role if role in ROLES else "guest"
            return self._redirect("/markets")
        if path == "/api/order":
            return self._json(place_order(sess, data))
        if path == "/trade":
            return self._html(page_trade(sess, {"symbol": str(data.get("symbol", "AAPL")),
                                                "side": str(data.get("side", "buy"))}, place_order(sess, data)))
        if path == "/api/watchlist":
            sym = str(data.get("symbol", "")).upper()
            if sym not in INFO:
                return self._json({"error": "unknown symbol"}, 400)
            sess.watch ^= {sym}
            return self._json({"symbol": sym, "watching": sym in sess.watch})
        if path == "/settings":
            sess.saved = True
            return self._redirect("/settings?saved=1")
        if path == "/admin/delete":
            try:
                DELETED_USERS.add(int(data.get("id", 0)))
            except ValueError:
                pass
            return self._redirect("/admin")
        self._html(page_404(sess, path), 404)


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main() -> None:
    global MARKET, DEBUG
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--seed", type=int, default=None, help="deterministic prices, flakiness and promos")
    ap.add_argument("--tick-interval", type=float, default=2.0,
                    help="seconds between price ticks; 0 freezes prices (use with --debug /api/_tick)")
    ap.add_argument("--debug", action="store_true", help="enable /api/_tick test hook")
    a = ap.parse_args()
    DEBUG = a.debug
    MARKET = Market(a.seed, a.tick_interval)
    if a.tick_interval > 0:
        def loop() -> None:
            while True:
                time.sleep(a.tick_interval)
                MARKET.tick()
        threading.Thread(target=loop, daemon=True).start()
    srv = Server((a.host, a.port), Handler)
    print(f"StockWatch listening on http://{a.host}:{srv.server_address[1]}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
