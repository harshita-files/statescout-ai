# ruff: noqa: E501
"""Specialised consistency modes, percent-aware numeric check, and text extraction."""

from apps.agent.audit_models import Rule
from apps.agent.contracts import SemanticUIMap
from apps.agent.negation.checks import check_rules, visible_text


def _smap(sid: str, url: str = "http://x.test/") -> SemanticUIMap:
    return SemanticUIMap(state_id=sid, url=url, role="guest")


def _rule(kind: str, **params: object) -> Rule:
    return Rule("r1", "rule text", "user", "high", kind, dict(params))


def test_visible_text_keeps_rows_and_drops_scripts() -> None:
    html = "<script>var NaN=1</script><tr><td>AAPL</td><td>10.00</td></tr><p>a&amp;b</p>"
    assert visible_text(html) == "AAPL 10.00\na&b"


def test_visible_text_ignores_source_newlines() -> None:
    assert visible_text("<td>1.0</td>\n<td>-2%</td>\n") == "1.0 -2%"


def test_sign_mode_flags_opposite_signs_only() -> None:
    page = _smap("s1")
    text = {"s1": "AAPL Apple 200.45 +11.36 +6.01% 1,000\nTSLA Tesla 181.10 +5.29 -3.01% 2,000"}
    out = check_rules([_rule("consistency", mode="sign")], [page], text)
    assert len(out) == 1 and "TSLA" in (out[0].evidence.text or "")


def test_ticker_mode_flags_ticket_that_disagrees_with_same_page_price() -> None:
    maps = [_smap("m", "http://x/markets"), _smap("t", "http://x/trade?symbol=AAPL")]
    texts = {
        "m": "AAPL Apple Inc. 200.00 +1.00 +0.5%\nAAPL 200.10 +0.5%",
        "t": "AAPL 200.00 +0.5%\nOrder ticket\nMarket price\n204.00",
    }
    out = check_rules([_rule("consistency", mode="ticker")], maps, texts)
    assert [v.state_id for v in out] == ["t"] and "order ticket" in out[0].rationale


def test_ticker_mode_ignores_price_drift_between_pages() -> None:
    maps = [_smap("m"), _smap("w")]
    texts = {"m": "AAPL Apple Inc. 200.00 +1.00 +0.5%", "w": "AAPL Apple Inc. 210.00 +1.00 +0.5%"}
    assert not check_rules([_rule("consistency", mode="ticker")], maps, texts)


def test_sum_mode_flags_phantom_total() -> None:
    texts = {
        "p": "Total value $ 14325.30\nAAPL 10 200.22 +5.89% 2002.20 Sell\nMSFT 5 434.74 +5.85% 2173.70 Sell"
    }
    out = check_rules([_rule("consistency", mode="sum")], [_smap("p")], texts)
    assert len(out) == 1 and "add up" in out[0].rationale
    ok = {
        "p": "Total value $ 4175.90\nAAPL 10 200.22 +5.89% 2002.20 Sell\nMSFT 5 434.74 +5.85% 2173.70 Sell"
    }
    assert not check_rules([_rule("consistency", mode="sum")], [_smap("p")], ok)


def test_numeric_ignores_negative_percentages() -> None:
    texts = {"s": "NVDA 840.82 -2.93%\nAMD 164 -1.11\n+0.67%\nCash -5.00"}
    out = check_rules([_rule("numeric", min=0)], [_smap("s")], texts)
    assert len(out) == 1 and "-5" in (out[0].evidence.text or "")


# -- SW-02: the order ticket lives on another page than the Markets table -------------------


def _run_ticker(*pages: tuple[str, str, str]) -> list:  # type: ignore[type-arg]
    maps = [_smap(sid, url) for sid, url, _ in pages]
    texts = {sid: text for sid, _, text in pages}
    return list(check_rules([_rule("consistency", mode="ticker")], maps, texts))


MARKETS = ("m", "http://x.test/markets", "Markets\nAAPL Apple Inc. 190.00 +1.00 +0.53% 1,000")


def test_ticker_cross_page_flags_a_ticket_priced_off_the_markets_table() -> None:
    trade = ("t", "http://x.test/trade?symbol=AAPL", "Order ticket\nMarket price\n193.80")
    out = _run_ticker(MARKETS, trade)
    assert len(out) == 1 and out[0].state_id == "t"
    assert "AAPL" in out[0].rationale and "193.8" in out[0].rationale


def test_ticker_cross_page_tolerates_price_drift() -> None:
    trade = ("t", "http://x.test/trade?symbol=AAPL", "Market price\n190.50")
    assert _run_ticker(MARKETS, trade) == []


def test_ticker_cross_page_reads_the_symbol_from_the_view_details_link() -> None:
    trade = ("t", "http://x.test/trade", "Market price\n193.80\nView AAPL details")
    assert len(_run_ticker(MARKETS, trade)) == 1


def test_ticker_cross_page_needs_a_market_observation_of_that_symbol() -> None:
    trade = ("t", "http://x.test/trade?symbol=MSFT", "Market price\n999.00")
    assert _run_ticker(MARKETS, trade) == []


def test_ticker_cross_page_compares_with_the_nearest_observations_on_both_sides() -> None:
    """Prices tick: an early 150.00 must not make an honest 190.40 ticket look wrong."""
    early = ("e", "http://x.test/markets", "AAPL Apple Inc. 150.00 +1.00 +0.53% 1,000")
    trade = ("t", "http://x.test/trade?symbol=AAPL", "Market price\n190.40")
    late = ("l", "http://x.test/markets?x=1", "AAPL Apple Inc. 190.20 +1.00 +0.53% 1,000")
    assert _run_ticker(early, trade, late) == []
