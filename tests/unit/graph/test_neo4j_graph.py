"""Unit tests for apps.agent.graph.neo4j_graph.Neo4jGraph — Track D.

`Neo4jGraph` is the single `GraphPort` implementation the orchestrator (Track B)
loads in live mode via `apps.agent.orchestrator.deps.live_ports`. These tests pin
the three things that make it a drop-in for `FakeGraph`:

  1. it structurally satisfies `GraphPort` and constructs with no arguments;
  2. the visited set lives in Redis, never on Neo4j's hot path (ADR-001 dec. 3);
  3. `persist_edge` tolerates the orchestrator's call order — the destination
     node is persisted *after* the edge, so the edge write must MERGE endpoints.

Neo4j is mocked; Redis is `fakeredis`. No Docker.

Run:  pytest tests/unit/graph/test_neo4j_graph.py -v
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import fakeredis
import pytest

import apps.agent.graph.cache as cache_module
from apps.agent.contracts import CaptureBundle, GraphPort, StateEdge, StateNode, Violation
from apps.agent.graph.neo4j_graph import Neo4jGraph


@pytest.fixture
def mock_neo4j():
    """Patch the Neo4j driver; yield the mock driver instance."""
    with patch("apps.agent.graph.graph_store.GraphDatabase.driver") as mock_cls:
        drv = MagicMock()
        drv.verify_connectivity.return_value = None
        mock_cls.return_value = drv
        yield drv


@pytest.fixture
def fake_redis(monkeypatch):
    """Route VisitedCache at a shared FakeStrictRedis instance."""
    fake = fakeredis.FakeStrictRedis(decode_responses=True)
    monkeypatch.setattr(cache_module.redis, "from_url", lambda url, decode_responses=True: fake)
    return fake


@pytest.fixture
def graph(mock_neo4j, fake_redis):
    return Neo4jGraph(scan_id="scan-test")


def _session(mock_neo4j) -> MagicMock:
    sess = MagicMock()
    mock_neo4j.session.return_value.__enter__.return_value = sess
    return sess


BUNDLE = CaptureBundle(
    url="/dashboard",
    dom="<h1>Dashboard</h1>",
    ax_tree={"role": "document", "name": "Dashboard"},
    title="Dashboard",
)


class TestConformance:
    def test_satisfies_graphport_protocol(self, graph):
        assert isinstance(graph, GraphPort)

    def test_constructs_with_no_arguments(self, mock_neo4j, fake_redis):
        g = Neo4jGraph()
        assert g.scan_id  # auto-generated, non-empty

    def test_explicit_scan_id_is_used(self, mock_neo4j, fake_redis):
        assert Neo4jGraph(scan_id="abc").scan_id == "abc"

    def test_scan_id_falls_back_to_env(self, mock_neo4j, fake_redis, monkeypatch):
        monkeypatch.setenv("STATESCOUT_SCAN_ID", "from-env")
        assert Neo4jGraph().scan_id == "from-env"

    def test_verifies_neo4j_connectivity_on_construction(self, mock_neo4j, fake_redis):
        Neo4jGraph()
        mock_neo4j.verify_connectivity.assert_called()


class TestVisitedSetIsRedis:
    def test_unmarked_pair_is_not_visited(self, graph):
        assert not graph.is_visited("s1", "a1")

    def test_marked_pair_is_visited(self, graph):
        graph.mark_visited("s1", "a1")
        assert graph.is_visited("s1", "a1")

    def test_pairs_are_distinct(self, graph):
        graph.mark_visited("s1", "a1")
        assert not graph.is_visited("s1", "a2")
        assert not graph.is_visited("s2", "a1")

    def test_mark_visited_is_idempotent(self, graph):
        graph.mark_visited("s1", "a1")
        graph.mark_visited("s1", "a1")
        assert graph.is_visited("s1", "a1")

    def test_visited_ops_never_touch_neo4j(self, graph, mock_neo4j):
        graph.mark_visited("s1", "a1")
        graph.is_visited("s1", "a1")
        graph.is_visited("s1", "a2")
        mock_neo4j.session.assert_not_called()

    def test_visited_keys_are_scoped_to_the_scan(self, graph, fake_redis):
        graph.mark_visited("s1", "a1")
        assert fake_redis.keys("session:scan-test:*")


class TestFingerprint:
    def test_delegates_to_the_normalising_fingerprint(self, graph):
        from apps.agent.graph.fingerprint import fingerprint

        expected = fingerprint(BUNDLE.dom, BUNDLE.url, '{"name": "Dashboard", "role": "document"}')
        assert graph.fingerprint(BUNDLE) == expected

    def test_is_stable(self, graph):
        assert graph.fingerprint(BUNDLE) == graph.fingerprint(BUNDLE)

    def test_ignores_volatile_noise(self, graph):
        a = CaptureBundle(url="/x", dom='<i data-session="sess_a">Hi</i>', ax_tree="")
        b = CaptureBundle(url="/x", dom='<i data-session="sess_b">Hi</i>', ax_tree="")
        assert graph.fingerprint(a) == graph.fingerprint(b)


class TestPersistState:
    def test_merges_on_fingerprint(self, graph, mock_neo4j):
        sess = _session(mock_neo4j)
        graph.persist_state(StateNode(state_id="fp1", url="/x", role="guest", depth=2))
        query = sess.run.call_args[0][0]
        assert "MERGE" in query
        assert "fingerprint" in query

    def test_depth_is_first_write_wins(self, graph, mock_neo4j):
        sess = _session(mock_neo4j)
        graph.persist_state(StateNode(state_id="fp1", url="/x", role="guest", depth=2))
        query = sess.run.call_args[0][0]
        assert "coalesce(s.depth" in query

    def test_passes_all_fields_as_params(self, graph, mock_neo4j):
        sess = _session(mock_neo4j)
        graph.persist_state(StateNode(state_id="fp1", url="/x", role="guest", depth=2, title="X"))
        kwargs = sess.run.call_args[1]
        assert kwargs["fp"] == "fp1"
        assert kwargs["url"] == "/x"
        assert kwargs["role"] == "guest"
        assert kwargs["depth"] == 2
        assert kwargs["title"] == "X"


class TestPersistEdge:
    def test_merges_both_endpoints_then_creates_edge(self, graph, mock_neo4j):
        """The orchestrator persists the destination node *after* this call, so a
        plain MATCH would silently drop the edge. Endpoints must be MERGEd."""
        sess = _session(mock_neo4j)
        graph.persist_edge(StateEdge("fp_a", "fp_b", "act_1"))
        query = sess.run.call_args[0][0]
        assert query.count("MERGE") >= 2
        assert "CREATE" in query
        assert ":ACTION" in query

    def test_records_is_back_edge(self, graph, mock_neo4j):
        sess = _session(mock_neo4j)
        graph.persist_edge(StateEdge("fp_a", "fp_b", "act_1", is_back_edge=True))
        assert "is_back_edge" in sess.run.call_args[0][0]
        assert sess.run.call_args[1]["ibe"] is True

    def test_parallel_edges_are_preserved(self, graph, mock_neo4j):
        """Two traversals of the same (from, action, to) → two CREATE calls."""
        sess = _session(mock_neo4j)
        edge = StateEdge("fp_a", "fp_b", "act_1")
        graph.persist_edge(edge)
        graph.persist_edge(edge)
        assert sess.run.call_count == 2
        assert "CREATE" in sess.run.call_args[0][0]


class TestDelegationAndLifecycle:
    def test_persist_violation_delegates_to_the_store(self, mock_neo4j, fake_redis):
        store = MagicMock()
        g = Neo4jGraph(scan_id="s", store=store)
        v = Violation("v1", "fp1", "e1", "forbidden_present", "high", "why")
        g.persist_violation(v)
        store.persist_violation.assert_called_once_with(v)

    def test_close_releases_the_store(self, mock_neo4j, fake_redis):
        store = MagicMock()
        Neo4jGraph(scan_id="s", store=store).close()
        store.close.assert_called_once()


class TestRunsWithTheOrchestrator:
    """The real proof: drop `Neo4jGraph` into `Ports` and run Track B's loop.

    Both the reference loop and the LangGraph port are exercised against the
    scripted app, with Neo4j mocked and Redis faked — nothing about the loop
    changes when the graph port is the real one.
    """

    @pytest.fixture
    def _ports(self, graph):
        from apps.agent.orchestrator.deps import Ports
        from apps.agent.orchestrator.fakes import FakeCrawler, FakePerception

        return Ports(crawler=FakeCrawler(role="guest"), perception=FakePerception(), graph=graph)

    @pytest.fixture
    def _config(self):
        from apps.agent.orchestrator.config import OrchestratorConfig

        return OrchestratorConfig(_env_file=None, perception_rate_per_min=0)

    @pytest.mark.parametrize("impl", ["reference", "langgraph"])
    def test_loop_completes_and_persists(self, impl, _ports, _config, mock_neo4j, fake_redis):
        from apps.agent.orchestrator import explore as reference
        from apps.agent.orchestrator import graph_runner
        from apps.agent.orchestrator.fakes import DEFAULT_POLICY

        _session(mock_neo4j)  # so `with driver.session() as s: s.run(...)` works
        run = {"reference": reference.explore, "langgraph": graph_runner.explore}[impl]

        result = run(_ports, "http://fake.test/login", DEFAULT_POLICY, _config)

        assert result.termination_reason == "frontier_exhausted"
        assert result.states > 0
        # The planted violation: a guest sees the admin link on /dashboard.
        assert any(v.expectation_id == "e-admin-link" for v in result.violations)
        # Persistence actually happened (state + edge + violation writes).
        assert mock_neo4j.session.called
        # Loop-prevention marks went to Redis, not Neo4j.
        assert fake_redis.keys("session:scan-test:visited:*")

    def test_importable_from_the_submodule(self):
        """The type-checked import path. Package-root re-export is intentionally
        deferred to Track B's live-integration PR — see the module docstring."""
        from apps.agent.graph.neo4j_graph import Neo4jGraph as FromSubmodule

        assert FromSubmodule is Neo4jGraph
