"""Post-crawl probes: intermittent defects need repeated observation of the same page."""

from __future__ import annotations

from typing import Any

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
