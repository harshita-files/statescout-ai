"""export_graph, run_audit, and the stochastic wiring in graph_runner."""

import random
from dataclasses import replace

from apps.agent.audit_models import AuditConfig, BlockedNote
from apps.agent.orchestrator.audit_runner import run_audit
from apps.agent.orchestrator.config import OrchestratorConfig
from apps.agent.orchestrator.deps import Ports
from apps.agent.orchestrator.export import export_graph
from apps.agent.orchestrator.fakes import DEFAULT_POLICY, FakeCrawler, FakeGraph, FakePerception
from apps.agent.orchestrator.graph_runner import explore

LOGIN = "http://fake.test/login"
NONCE = (r'data-nonce="[^"]*"',)


def ports(crawler=None):
    return Ports(crawler or FakeCrawler(), FakePerception(), FakeGraph())


def cfg(**kw):
    return AuditConfig(url=LOGIN, depth_limit=20, max_states=40, volatility_patterns=NONCE, **kw)


def test_export_preserves_cycles_probabilities_and_counts():
    report = run_audit(cfg(), ports(), DEFAULT_POLICY)
    assert report.status == "done"
    nodes, edges = report.graph["nodes"], report.graph["edges"]
    ids = {n["id"] for n in nodes}
    assert all(e["source"] in ids and e["target"] in ids for e in edges)
    assert all(0 < e["probability"] <= 1 and e["count"] >= 1 for e in edges)
    assert edges
    assert any(n["violation_count"] for n in nodes) == bool(report.findings)
    assert all(n["url"] for n in nodes)
    assert report.stats["termination_reason"] == "frontier_exhausted"


def test_export_graph_matches_dynamic_result_edges():
    crawler = FakeCrawler()
    config = OrchestratorConfig(
        _env_file=None, probabilistic_states=True, depth_limit=20, volatility_patterns=NONCE
    )
    result = explore(ports(crawler), LOGIN, DEFAULT_POLICY, config)
    out = export_graph(result, result.dynamic)
    replayed = sum(sum(c.values()) for c in result.dynamic.replay_transitions.values())
    assert sum(e["count"] for e in out["edges"]) - replayed == result.edges
    assert any(e["source"] == e["target"] or e["target"] in result.order for e in out["edges"])
    assert out["stats"]["states"] == result.states


def test_findings_have_confidence_label_and_url():
    report = run_audit(cfg(), ports(), DEFAULT_POLICY)
    assert report.findings
    for f in report.findings:
        assert 0 < f.confidence <= 1 and f.url
        assert any(e.startswith("observation: ") for e in f.evidence)
    assert report.stats["confidence_labels"]


def test_blocked_notes_merged_when_crawler_has_them():
    crawler = FakeCrawler()
    crawler.blocked_notes = lambda: [BlockedNote("http://x/robots", "robots")]
    assert run_audit(cfg(), ports(crawler), DEFAULT_POLICY).blocked == (
        BlockedNote("http://x/robots", "robots"),
    )
    assert run_audit(cfg(), ports(), DEFAULT_POLICY).blocked == ()


def test_stop_callback_yields_partial_stopped_report_and_progress_fires():
    events = []
    calls = {"n": 0}

    def stop():
        calls["n"] += 1
        return calls["n"] > 2

    full = run_audit(cfg(), ports(), DEFAULT_POLICY)
    part = run_audit(cfg(), ports(), DEFAULT_POLICY, stop=stop, progress=events.append)
    assert part.status == "stopped"
    assert part.stats["visited_pairs"] < full.stats["visited_pairs"]
    phases = {e["phase"] for e in events}
    assert {"state", "done"} <= phases


def test_unopenable_seed_is_an_error_report():
    class Dead(FakeCrawler):
        def open(self, url):
            from apps.agent.contracts import NavigationError

            raise NavigationError("down")

    assert run_audit(cfg(), ports(Dead()), DEFAULT_POLICY).status == "error"


class Ticker(FakeCrawler):
    """Every render carries a changing 'N people online' counter."""

    def __init__(self):
        super().__init__()
        self.random = random.Random(3)

    def _render(self, path, page):
        bundle = super()._render(path, page)
        n = self.random.randrange(10**6)
        return replace(
            bundle, dom=bundle.dom.replace("</body>", f"<p>{n} people online</p></body>")
        )


def test_auto_mask_learns_counter_and_keeps_state_count_stable():
    def states(auto):
        config = OrchestratorConfig(
            _env_file=None,
            probabilistic_states=True,
            auto_mask=auto,
            volatility_patterns=NONCE,
            depth_limit=20,
            max_states=40,
        )
        return explore(ports(Ticker()), LOGIN, DEFAULT_POLICY, config)

    plain, masked = states(False), states(True)
    base = explore(
        ports(), LOGIN, DEFAULT_POLICY, OrchestratorConfig(_env_file=None, depth_limit=20)
    )
    assert masked.states == base.states > plain.states
    assert masked.dynamic.masks and "online" in masked.dynamic.masks[0]["pattern"]
    assert plain.dynamic.masks == []


def test_ucb_frontier_only_reorders():
    def run(ucb):
        config = OrchestratorConfig(
            _env_file=None,
            probabilistic_states=True,
            ucb_frontier=ucb,
            depth_limit=20,
            volatility_patterns=NONCE,
        )
        return explore(ports(), LOGIN, DEFAULT_POLICY, config)

    a, b = run(False), run(True)
    assert a.states == b.states and a.visited_pairs == b.visited_pairs
    assert {v.violation_id for v in a.violations} == {v.violation_id for v in b.violations}
