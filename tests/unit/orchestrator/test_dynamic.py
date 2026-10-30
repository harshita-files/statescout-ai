"""Acceptance tests for the opt-in dynamic model (no browser or services)."""

import random
from dataclasses import replace

from langgraph.checkpoint.memory import InMemorySaver

from apps.agent.orchestrator.config import OrchestratorConfig
from apps.agent.orchestrator.deps import Ports
from apps.agent.orchestrator.dynamic import DynamicStats, identity, observe_transition, probability
from apps.agent.orchestrator.fakes import DEFAULT_POLICY, FakeCrawler, FakeGraph, FakePerception
from apps.agent.orchestrator.graph_runner import build_graph, explore


class DynamicCrawler(FakeCrawler):
    def __init__(self):
        super().__init__()
        self.random = random.Random(46)
        self.calls = []

    def _render(self, path, page):
        bundle = super()._render(path, page)
        noise = f"noise-{self.random.randrange(10**9)}"
        return replace(
            bundle,
            dom=bundle.dom + f"<aside>{noise}</aside>",
            ax_tree={"page": bundle.ax_tree, "noise": noise},
        )

    def act(self, action):
        self.calls.extend(["GET /api/view", "GET /api/view"])
        return super().act(action)

    def drain(self):
        calls, self.calls = self.calls, []
        return tuple(calls)


def settings(enabled=True):
    return OrchestratorConfig(
        _env_file=None,
        probabilistic_states=enabled,
        volatility_patterns=(r"noise-\d+", r'data-nonce="[^"]*"'),
        perception_rate_per_min=0,
        depth_limit=20,
        max_states=40,
    )


def run(enabled=True, saver=None):
    crawler, graph = DynamicCrawler(), FakeGraph()
    ports = Ports(crawler, FakePerception(), graph, network=crawler)
    result = explore(
        ports,
        "http://fake.test/login",
        DEFAULT_POLICY,
        settings(enabled),
        run_id="dynamic",
        checkpointer=saver,
    )
    return result, ports


def test_dynamic_bounded_replay_recall_and_counts():
    old, _ = run(False)
    new, ports = run()
    assert new.states == 4
    assert new.termination_reason == "frontier_exhausted"
    assert sum("replay diverged" in s.reason for s in old.skipped) > 0
    assert not new.skipped
    assert ports.graph.back_edges()
    assert len(ports.graph.visited) == new.visited_pairs
    expected = explore(
        Ports(FakeCrawler(), FakePerception(), FakeGraph()),
        "http://fake.test/login",
        DEFAULT_POLICY,
        settings(False),
    )
    assert {v.expectation_id for v in new.violations} == {
        v.expectation_id for v in expected.violations
    }
    assert all(v.state_id in ports.graph.states for v in new.violations)
    assert new.dynamic.endpoints["GET /api/view"]["calls"] == 2 * len(ports.crawler.acted)
    assert new.dynamic.endpoints["GET /api/view"]["actions"] == len(ports.crawler.acted)
    assert new.dynamic.endpoints["GET /api/view"]["replay_calls"] == 2 * new.replay_steps
    assert new.dynamic.confidence
    assert old.dynamic is None


def test_identity_preserves_url_ax_and_controls():
    crawler = DynamicCrawler()
    first = crawler.open("/login")
    second = crawler.open("/login")
    assert identity(first, settings()) == identity(second, settings())
    assert identity(first, settings()) != identity(replace(first, url="/other"), settings())
    assert identity(first, settings()) != identity(
        replace(first, ax_tree={"role": "dialog"}), settings()
    )
    assert identity(first, settings()) != identity(
        replace(first, dom=first.dom + "<button>Admin</button>"), settings()
    )


def test_probabilities_count_observations_not_visited_claims():
    stats = DynamicStats()
    for target in ["a", "a", "b"]:
        observe_transition(stats, "s", "click", target, replay=False)
    assert probability(stats, "s", "click", "a") == 2 / 3
    assert probability(stats, "s", "click", "b") == 1 / 3
    assert probability(stats, "s", "click", "unknown") == 0


def test_statistics_survive_checkpoints():
    saver = InMemorySaver()
    result, ports = run(saver=saver)
    saved = (
        build_graph(ports, DEFAULT_POLICY, settings(), saver)
        .get_state({"configurable": {"thread_id": "dynamic"}})
        .values
    )
    assert saved["dynamic"] == result.dynamic
    assert len(result.dynamic.exact_hashes) == 4
    assert any(len(hashes) > 1 for hashes in result.dynamic.exact_hashes.values())


def test_replay_retarget_requires_previously_observed_outcome_and_live_action():
    from apps.agent.contracts import Action
    from apps.agent.orchestrator.dynamic import replay_target_allowed

    stats = DynamicStats()
    action = Action("continue", "click", "#continue")
    observe_transition(stats, "source", "branch", "alternative", replay=False)
    assert replay_target_allowed(
        stats, "source", "branch", "alternative", action, (action,), {"alternative"}, 0.05
    )
    assert not replay_target_allowed(
        stats, "source", "branch", "unknown", action, (action,), {"alternative"}, 0.05
    )
    assert not replay_target_allowed(
        stats, "source", "branch", "alternative", action, (), {"alternative"}, 0.05
    )


def test_live_dynamic_ports_enable_crawler_and_telemetry():
    from unittest.mock import MagicMock, patch

    from apps.agent.orchestrator.deps import build_ports

    with (
        patch("apps.agent.crawler.PlaywrightCrawler") as crawler,
        patch.dict("sys.modules", {"apps.agent.perception": MagicMock()}),
        patch("apps.agent.graph.neo4j_graph.Neo4jGraph", return_value=MagicMock()),
    ):
        ports = build_ports(settings(), live=True)
        crawler.assert_called_once_with(role="guest", probabilistic_states=True)
        assert ports.network is ports.crawler


def test_endpoint_counts_are_attributed_to_state_action_pairs():
    result, ports = run()
    stats = result.dynamic
    assert sum(
        counts["GET /api/view"]["calls"] for counts in stats.action_endpoints.values()
    ) == 2 * len(ports.crawler.acted)
    assert set(stats.action_endpoints) <= set(stats.transitions)


def test_dynamic_churn_finishes_without_using_state_cap():
    from apps.agent.orchestrator.fakes import FakeLink, FakePage

    results = []
    for enabled in (False, True):
        crawler = DynamicCrawler()
        crawler.app = {
            "/login": FakePage(
                "Feed",
                transitions=(FakeLink("Refresh", "/login", role="button"),),
            )
        }
        result = explore(
            Ports(crawler, FakePerception(), FakeGraph(), network=crawler),
            "http://fake.test/login",
            DEFAULT_POLICY,
            settings(enabled).model_copy(update={"max_states": 12}),
        )
        results.append(result)
    assert results[0].states == 12
    assert results[0].termination_reason == "max_states"
    assert results[1].states == 1
    assert results[1].edges == 1
    assert results[1].termination_reason == "frontier_exhausted"


def test_readiness_timeouts_are_reported():
    crawler = DynamicCrawler()
    crawler.last_capture_ready = False
    result = explore(
        Ports(crawler, FakePerception(), FakeGraph(), network=crawler),
        "http://fake.test/login",
        DEFAULT_POLICY,
        settings(),
    )
    assert result.dynamic.readiness["incomplete"] > 0
    assert result.dynamic.readiness["ready"] == 0
