"""Post-crawl probes: intermittent defects need repeated observation of the same page."""

from __future__ import annotations

from typing import Any

import pytest

from apps.agent.audit_models import AuditConfig, Rule
from apps.agent.contracts import Action, CaptureBundle, ExpectationSet
from apps.agent.orchestrator.audit_runner import run_audit
from apps.agent.orchestrator.deps import Ports
from apps.agent.orchestrator.fakes import FakeGraph
from apps.agent.orchestrator.probes import distinct_targets, resample
from apps.agent.perception import VLMPerception

PAGE = "<html><head><title>AAPL</title></head><body><h1>AAPL</h1><span>{v}</span></body></html>"
NAN_RULE = Rule(
    "nan",
    "The page must never display NaN or undefined",
    "user",
    "medium",
    "content",
    {"forbid_pattern": r"\bNaN\b|\bundefined\b"},
)


class FlakyCrawler:
    """One page whose price shows `$NaN` on every `flaky_every`-th load (not the first)."""

    def __init__(self, flaky_every: int = 3, url: str = "http://a.test/stock/AAPL") -> None:
        self.n, self.every, self.url = 0, flaky_every, url

    def open(self, url: str) -> CaptureBundle:
        self.n += 1
        bad = self.n > 1 and self.n % self.every == 0
        return CaptureBundle(
            self.url, PAGE.format(v="$NaN" if bad else "$190.10"), {}, None, "AAPL"
        )

    def act(self, action: Action) -> CaptureBundle:  # pragma: no cover - no actions here
        raise AssertionError

    def enumerate_actions(self, bundle: CaptureBundle) -> tuple[Action, ...]:
        return ()

    def close(self) -> None:
        pass


def _ports(crawler: Any) -> Ports:
    return Ports(crawler=crawler, perception=VLMPerception(dom_only=True), graph=FakeGraph())


def test_distinct_targets_keep_one_page_per_kind() -> None:
    pairs = [
        ("s1", "http://a.test/stock/AAPL"),
        ("s2", "http://a.test/stock/MSFT"),
        ("s3", "http://a.test/markets"),
        ("s4", "http://a.test/markets?sector=Tech"),
        ("s5", "javascript:void(0)"),
    ]
    assert distinct_targets(pairs) == [
        ("s1", "http://a.test/stock/AAPL"),
        ("s3", "http://a.test/markets"),
        ("s4", "http://a.test/markets?sector=Tech"),
    ]


def test_resample_reopens_each_target_n_times_within_the_cap() -> None:
    crawler = FlakyCrawler()
    got = resample(crawler, [("s1", "http://a.test/x"), ("s2", "http://a.test/y")], 4, cap=6)
    assert crawler.n == 6 and sum(len(v) for v in got.values()) == 6


def test_resample_stops_when_asked() -> None:
    crawler = FlakyCrawler()
    calls = {"n": 0}

    def stop() -> bool:
        calls["n"] += 1
        return calls["n"] > 2

    resample(crawler, [("s1", "http://a.test/x")], 10, cap=50, should_stop=stop)
    assert crawler.n == 2


def test_resample_survives_a_failing_reload() -> None:
    class Down(FlakyCrawler):
        def open(self, url: str) -> CaptureBundle:
            self.n += 1
            raise OSError("boom")

    assert resample(Down(), [("s1", "http://a.test/x")], 3, cap=10) == {"s1": []}


def test_an_intermittent_defect_is_found_with_its_flakiness_as_confidence() -> None:
    crawler = FlakyCrawler()  # load 1 (the crawl) is clean; resample loads 3 and 6 are bad
    report = run_audit(
        AuditConfig(
            url="http://a.test/stock/AAPL",
            rules=(NAN_RULE,),
            auto_rules=False,
            probabilistic=False,
            resamples=5,
        ),
        _ports(crawler),
        ExpectationSet((), ()),
    )
    hits = [f for f in report.findings if f.rule_id == "nan"]
    assert len(hits) == 1
    assert hits[0].url == "http://a.test/stock/AAPL"
    assert "2 of 5" in hits[0].rationale
    assert 0.3 <= hits[0].confidence <= 0.5  # ~ 2/5, not a certainty


def test_resamples_zero_disables_the_phase() -> None:
    crawler = FlakyCrawler()
    run_audit(
        AuditConfig(
            url="http://a.test/x",
            rules=(NAN_RULE,),
            auto_rules=False,
            probabilistic=False,
            resamples=0,
        ),
        _ports(crawler),
        ExpectationSet((), ()),
    )
    assert crawler.n == 1  # only the crawl's own load


# -- adaptive allocation: pages with background requests of their own get more reloads --------


class ObservingCrawler:
    """`observe` is the lean reload; `calls` lists the background requests per URL."""

    def __init__(self, calls: dict[str, tuple[str, ...]]) -> None:
        self.calls, self.loads = calls, {}

    def observe(self, url: str) -> tuple[str, str, str, tuple[str, ...]]:
        self.loads[url] = self.loads.get(url, 0) + 1
        return url, "t", "<p>x</p>", self.calls.get(url, ())

    def open(self, url: str) -> CaptureBundle:  # pragma: no cover - must not be used
        raise AssertionError("resample should prefer the lean observe()")


def test_pages_with_their_own_background_requests_get_the_most_reloads() -> None:
    shared = ("GET /api/quotes",)  # polled by every page
    urls = {f"http://a.test/{p}": shared for p in ("a", "b", "c", "d")}
    urls["http://a.test/static"] = ()
    urls["http://a.test/stock/AAPL"] = (*shared, "GET /api/quote")  # unique to this kind
    crawler = ObservingCrawler(urls)
    targets = [(f"s{i}", u) for i, u in enumerate(urls)]
    resample(crawler, targets, 2, dynamic_n=10, cap=100)
    assert crawler.loads["http://a.test/stock/AAPL"] == 10  # specific endpoint: dynamic_n
    assert crawler.loads["http://a.test/a"] == 2  # shared polling: the base n
    assert crawler.loads["http://a.test/static"] == 2


def test_the_cap_bounds_total_loads_even_for_specific_pages() -> None:
    urls = {"http://a.test/x": ("GET /api/one",), "http://a.test/y": ("GET /api/two",)}
    crawler = ObservingCrawler(urls)
    resample(
        crawler, [("s1", "http://a.test/x"), ("s2", "http://a.test/y")], 2, dynamic_n=50, cap=20
    )
    assert sum(crawler.loads.values()) == 20


class StrictCrawler(FlakyCrawler):
    """Like a real browser: unusable once closed."""

    closed = False

    def open(self, url: str) -> CaptureBundle:
        if self.closed:
            raise RuntimeError("PlaywrightCrawler has been closed.")
        return super().open(url)

    def close(self) -> None:
        self.closed = True


def test_probes_run_before_the_crawler_is_closed_and_it_is_closed_afterwards() -> None:
    crawler = StrictCrawler(flaky_every=2)
    report = run_audit(
        AuditConfig(
            url="http://a.test/stock/AAPL",
            rules=(NAN_RULE,),
            auto_rules=False,
            probabilistic=False,
            resamples=4,
        ),
        _ports(crawler),
        ExpectationSet((), ()),
    )
    assert any(f.rule_id == "nan" for f in report.findings)  # the reloads worked
    assert crawler.closed  # and the browser is still released at the end


def test_the_crawler_is_closed_even_when_the_probe_phase_fails() -> None:
    class Boom(StrictCrawler):
        def open(self, url: str) -> CaptureBundle:
            if self.n >= 1:
                raise RuntimeError("down")
            return super().open(url)

    crawler = Boom()
    run_audit(
        AuditConfig(
            url="http://a.test/x",
            rules=(NAN_RULE,),
            auto_rules=False,
            probabilistic=False,
            resamples=3,
        ),
        _ports(crawler),
        ExpectationSet((), ()),
    )
    assert crawler.closed


# -- SW-05: a timestamp that stops advancing while the data keeps changing ------------------

from apps.agent.contracts import SemanticUIMap  # noqa: E402
from apps.agent.orchestrator.probes import Observation, liveness_violations  # noqa: E402

LIVE_RULE = Rule(
    "live",
    "A 'Last updated' timestamp must advance whenever the displayed live prices change.",
    "user",
    "medium",
    "liveness",
)
BASE = SemanticUIMap("s1", "http://a.test/markets", "guest")


def _ob(ts: str, price: str) -> Observation:
    dom = f"<p>Last updated: <time>{ts}</time></p><td>AAPL</td><td>{price}</td>"
    return Observation("http://a.test/markets", "Markets", dom)


def _live(*obs: Observation, base_text: str = "") -> list:  # type: ignore[type-arg]
    return liveness_violations([LIVE_RULE], [BASE], {"s1": list(obs)}, {"s1": base_text})


def test_a_frozen_timestamp_over_changing_prices_is_flagged() -> None:
    got = _live(_ob("12:00:08", "190.10"), _ob("12:00:08", "190.55"), _ob("12:00:08", "191.02"))
    assert len(got) == 1 and got[0].state_id == "s1"
    assert "last updated" in (got[0].evidence.text or "").lower()
    assert "12:00:08" in got[0].rationale


def test_an_advancing_timestamp_is_fine() -> None:
    assert (
        _live(_ob("12:00:08", "190.10"), _ob("12:00:09", "190.55"), _ob("12:00:10", "191.02")) == []
    )


def test_a_timestamp_over_unchanged_prices_is_fine() -> None:
    assert (
        _live(_ob("12:00:08", "190.10"), _ob("12:00:08", "190.10"), _ob("12:00:08", "190.10")) == []
    )


def test_two_readings_are_not_enough_evidence() -> None:
    assert _live(_ob("12:00:08", "190.10"), _ob("12:00:08", "190.55")) == []


def test_the_crawls_own_capture_counts_as_the_earliest_observation() -> None:
    base = "Last updated: 12:00:08\nAAPL 189.90"
    got = _live(_ob("12:00:08", "190.10"), _ob("12:00:08", "190.55"), base_text=base)
    assert len(got) == 1


def test_pages_without_a_timestamp_are_ignored() -> None:
    plain = Observation("http://a.test/x", "t", "<td>AAPL</td><td>190.10</td>")
    other = Observation("http://a.test/x", "t", "<td>AAPL</td><td>191.10</td>")
    assert _live(plain, other, plain) == []


# -- SW-03: an invalid value submitted to a form must be rejected, not reported as success ----

from apps.agent.orchestrator.probes import FormProbe, form_probe_violations  # noqa: E402

VALID_RULE = Rule(
    "valid",
    "An order with a negative quantity must be rejected with an error, never shown as a success.",
    "user",
    "critical",
    "validation",
)
FORM = "<form><input name=qty type=number><button>Place order</button></form>"


def _probe(value: str, after_msg: str) -> FormProbe:
    before = f"<h1>Trade</h1>{FORM}"
    after = f"<h1>Trade</h1>{FORM}<div role=status>{after_msg}</div>"
    return FormProbe("http://a.test/trade", "qty", value, before, after)


def _valid(*probes: FormProbe) -> list:  # type: ignore[type-arg]
    return form_probe_violations([VALID_RULE], [BASE], {"s1": list(probes)})


def test_an_invalid_value_reported_as_success_is_flagged() -> None:
    got = _valid(_probe("-5", "Order filled: BUY -5 AAPL"))
    assert len(got) == 1 and got[0].state_id == "s1"
    assert "Order filled" in (got[0].evidence.text or "") and "-5" in got[0].rationale


def test_an_invalid_value_rejected_with_an_error_is_fine() -> None:
    assert _valid(_probe("-5", "Error: quantity must be positive")) == []


def test_a_response_that_says_nothing_new_is_not_a_finding() -> None:
    assert _valid(_probe("-5", "")) == []


def test_success_words_already_on_the_page_do_not_count() -> None:
    before = "<h1>Trade</h1><p>Order filled instantly or your money back</p>"
    probe = FormProbe("http://a.test/trade", "qty", "-5", before, before)
    assert _valid(probe) == []


def test_a_response_with_both_success_and_error_wording_is_not_flagged() -> None:
    assert _valid(_probe("-5", "Order filled? No: invalid quantity")) == []


def test_validation_rules_only() -> None:
    other = Rule("x", "t", "user", "high", "content", {"forbid_pattern": "zzz"})
    assert form_probe_violations([other], [BASE], {"s1": [_probe("-5", "Order filled")]}) == []


class FormCrawler(FlakyCrawler):
    """A page with an order form; `probe_forms` records calls and answers like a flawed app."""

    def __init__(self, url: str) -> None:
        super().__init__(flaky_every=10_000, url=url)
        self.probed: list[str] = []

    def open(self, url: str) -> CaptureBundle:
        self.n += 1
        dom = f"<html><body><h1>Trade</h1>{FORM}</body></html>"
        return CaptureBundle(self.url, dom, {}, None, "Trade")

    def probe_forms(self, url: str, values: Any) -> list[FormProbe]:
        self.probed.append(url)
        return [_probe(v, "Order filled") for v in values]


def _audit_forms(url: str, probe: bool) -> tuple[FormCrawler, Any]:
    crawler = FormCrawler(url)
    report = run_audit(
        AuditConfig(
            url=url,
            rules=(VALID_RULE,),
            auto_rules=False,
            probabilistic=False,
            resamples=0,
            probe_forms=probe,
        ),
        _ports(crawler),
        ExpectationSet((), ()),
    )
    return crawler, report


def test_an_accepted_invalid_value_becomes_a_critical_finding_on_a_local_target() -> None:
    crawler, report = _audit_forms("http://localhost:8765/trade", probe=True)
    hits = [f for f in report.findings if f.rule_id == "valid"]
    assert crawler.probed == ["http://localhost:8765/trade"]
    assert hits and hits[0].severity == "critical" and "Order filled" in " ".join(hits[0].evidence)


def test_form_probing_is_off_by_default() -> None:
    crawler, report = _audit_forms("http://localhost:8765/trade", probe=False)
    assert crawler.probed == [] and not report.findings


@pytest.mark.parametrize("url", ["https://example.com/trade", "http://8.8.8.8/trade"])
def test_form_probing_never_runs_against_a_public_site(url: str) -> None:
    crawler, report = _audit_forms(url, probe=True)
    assert crawler.probed == [] and not [f for f in report.findings if f.rule_id == "valid"]


def test_a_failing_probe_does_not_fail_the_audit() -> None:
    class Down(FormCrawler):
        def probe_forms(self, url: str, values: Any) -> list[FormProbe]:
            raise RuntimeError("browser died")

    crawler = Down("http://localhost:8765/trade")
    report = run_audit(
        AuditConfig(
            url=crawler.url,
            rules=(VALID_RULE,),
            auto_rules=False,
            probabilistic=False,
            resamples=0,
            probe_forms=True,
        ),
        _ports(crawler),
        ExpectationSet((), ()),
    )
    assert report.status == "done"


def test_the_evidence_quotes_the_success_line_not_unrelated_changes() -> None:
    """Live prices change between the before/after captures; they must not crowd the quote."""
    before = "<h1>Trade</h1><p>AAPL 190.10</p><p>MSFT 410.20</p>"
    after = (
        "<h1>Trade</h1><p>AAPL 190.55</p><p>MSFT 410.80</p>"
        "<p>GOOGL 140.00 +0.5%</p><div role=status>Order filled: BUY -5 AAPL</div>"
    )
    got = _valid(FormProbe("http://a.test/trade", "qty", "-5", before, after))
    assert len(got) == 1
    assert "Order filled" in (got[0].evidence.text or "")
    assert "190.55" not in (got[0].evidence.text or "")


def test_a_validation_rule_is_proposed_once_a_numeric_form_has_been_seen() -> None:
    """Auto-rules are made before the crawl; the form only shows up during it."""
    crawler = FormCrawler("http://localhost:8765/trade")
    report = run_audit(
        AuditConfig(
            url=crawler.url,
            rules=(),
            auto_rules=True,
            probabilistic=False,
            resamples=0,
            probe_forms=True,
        ),
        _ports(crawler),
        ExpectationSet((), ()),
    )
    proposed = [r for r in report.rules if r.kind == "validation"]
    assert len(proposed) == 1 and proposed[0].source == "generated"
    assert any(f.rule_id == proposed[0].rule_id for f in report.findings)


def test_no_validation_rule_is_proposed_when_auto_rules_is_off_or_probing_is_off() -> None:
    for auto, probe in ((False, True), (True, False)):
        crawler = FormCrawler("http://localhost:8765/trade")
        report = run_audit(
            AuditConfig(
                url=crawler.url,
                rules=(),
                auto_rules=auto,
                probabilistic=False,
                resamples=0,
                probe_forms=probe,
            ),
            _ports(crawler),
            ExpectationSet((), ()),
        )
        assert not [r for r in report.rules if r.kind == "validation"]


def test_an_existing_validation_rule_is_not_duplicated() -> None:
    crawler = FormCrawler("http://localhost:8765/trade")
    report = run_audit(
        AuditConfig(
            url=crawler.url,
            rules=(VALID_RULE,),
            auto_rules=True,
            probabilistic=False,
            resamples=0,
            probe_forms=True,
        ),
        _ports(crawler),
        ExpectationSet((), ()),
    )
    assert len([r for r in report.rules if r.kind == "validation"]) == 1
