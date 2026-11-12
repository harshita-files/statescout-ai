"""Pages of one kind (same URL pattern) must not crowd out the other kinds of page."""

from __future__ import annotations

import pytest

from apps.agent.contracts import Action
from apps.agent.orchestrator.frontier_diversity import diversify, url_template
from apps.agent.orchestrator.state import PendingAction


@pytest.mark.parametrize(
    ("url", "template"),
    [
        ("http://a.test/stock/AAPL", "/stock/*"),
        ("http://a.test/stock/MSFT#tab", "/stock/*"),
        ("http://a.test/markets?sector=Tech", "/markets?sector"),
        ("http://a.test/markets?sector=Auto&page=2", "/markets?page&sector"),
        ("http://a.test/trade?symbol=AAPL", "/trade?symbol"),
        ("http://a.test/orders/12345/items/9", "/orders/*/items/*"),
        ("http://a.test/about", "/about"),
        ("http://a.test/", "/"),
    ],
)
def test_url_template_groups_pages_of_one_kind(url: str, template: str) -> None:
    assert url_template(url) == template


def _p(target: str, depth: int = 1, kind: str = "navigate") -> PendingAction:
    return PendingAction("s0", Action(f"id-{target}", kind, target, target), depth)  # type: ignore[arg-type]


def test_unseen_kinds_come_before_more_of_a_kind_already_seen() -> None:
    frontier = [
        _p("http://a.test/stock/AAPL"),
        _p("http://a.test/stock/MSFT"),
        _p("http://a.test/trade?symbol=AAPL"),
        _p("http://a.test/portfolio"),
    ]
    seen = ["http://a.test/markets", "http://a.test/stock/GOOGL", "http://a.test/stock/AMZN"]
    got = [p.action.target for p in diversify(frontier, seen)]
    assert got[:2] == ["http://a.test/trade?symbol=AAPL", "http://a.test/portfolio"]
    assert set(got[2:]) == {"http://a.test/stock/AAPL", "http://a.test/stock/MSFT"}


def test_depth_stays_primary_and_ties_keep_their_order() -> None:
    frontier = [_p("http://a.test/stock/A", 2), _p("http://a.test/x", 1), _p("http://a.test/y", 1)]
    got = [p.action.target for p in diversify(frontier, [])]
    assert got == ["http://a.test/x", "http://a.test/y", "http://a.test/stock/A"]


def test_clicks_without_a_known_url_are_never_penalised() -> None:
    frontier = [_p("role=button[name=/^Star$/] >> nth=0", 1, "click"), _p("http://a.test/stock/A")]
    seen = ["http://a.test/stock/B"] * 5
    assert diversify(frontier, seen)[0].action.kind == "click"


def test_diversify_never_drops_or_adds_pairs() -> None:
    frontier = [_p(f"http://a.test/stock/{c}") for c in "ABCDEF"]
    assert sorted(
        p.action.target for p in diversify(frontier, ["http://a.test/stock/Z"])
    ) == sorted(p.action.target for p in frontier)
