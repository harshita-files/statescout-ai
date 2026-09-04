"""
Unit tests for apps.agent.graph.graph_store — Month 2 GraphPort methods.

All tests mock the Neo4j driver — no Docker required.

Invariants tested:
  - persist_state   → MERGE on fingerprint
  - persist_edge    → CREATE (not MERGE); is_back_edge stored
  - persist_violation → MERGE on violation_id + relationships
  - mark_visited    → MERGE on (state_id, action_id)
  - is_visited      → queries VisitedPair
  - get_scan_counts → returns int dict

Run:  pytest tests/unit/test_graph_store_month2.py -v
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from apps.agent.graph.graph_store import GraphStore


@pytest.fixture
def mock_driver():
    with patch("apps.agent.graph.graph_store.GraphDatabase.driver") as mock_cls:
        drv = MagicMock()
        drv.verify_connectivity.return_value = None
        mock_cls.return_value = drv
        yield drv


@pytest.fixture
def gs(mock_driver):
    os.environ["NEO4J_URI"] = "bolt://test:7687"
    os.environ["NEO4J_USER"] = "neo4j"
    os.environ["NEO4J_PASSWORD"] = "test"
    return GraphStore()


def _session(mock_driver):
    sess = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = sess
    return sess


class TestPersistState:
    def test_uses_merge(self, gs, mock_driver):
        sess = _session(mock_driver)
        from apps.agent.contracts import StateNode

        gs.persist_state(StateNode(state_id="fp_abc", url="/dashboard", role="guest", depth=1))
        query = sess.run.call_args[0][0]
        assert "MERGE" in query

    def test_merge_on_fingerprint(self, gs, mock_driver):
        sess = _session(mock_driver)
        from apps.agent.contracts import StateNode

        gs.persist_state(StateNode(state_id="fp_abc", url="/dashboard", role="guest", depth=1))
        query = sess.run.call_args[0][0]
        assert "fingerprint" in query

    def test_on_create_set_for_immutable_fields(self, gs, mock_driver):
        sess = _session(mock_driver)
        from apps.agent.contracts import StateNode

        gs.persist_state(StateNode(state_id="fp_abc", url="/x", role="guest", depth=0))
        query = sess.run.call_args[0][0]
        assert "ON CREATE SET" in query


class TestPersistEdge:
    def test_relationship_is_created_never_merged(self, gs, mock_driver):
        """The :ACTION relationship is CREATEd — every traversal is a distinct
        record, cycles/parallel edges preserved. (Endpoint nodes may be MERGEd so
        an edge to a not-yet-persisted state still lands.)"""
        sess = _session(mock_driver)
        from apps.agent.contracts import StateEdge

        gs.persist_edge(StateEdge("fp_a", "fp_b", "act_1"))
        query = sess.run.call_args[0][0]
        assert "CREATE (a)-[:ACTION" in query
        assert "MERGE (a-[:ACTION" not in query  # the relationship is never MERGEd

    def test_stores_is_back_edge(self, gs, mock_driver):
        sess = _session(mock_driver)
        from apps.agent.contracts import StateEdge

        gs.persist_edge(StateEdge("fp_a", "fp_b", "act_1", is_back_edge=True))
        query = sess.run.call_args[0][0]
        assert "is_back_edge" in query

    def test_passes_all_edge_params(self, gs, mock_driver):
        sess = _session(mock_driver)
        from apps.agent.contracts import StateEdge

        gs.persist_edge(StateEdge("fp_a", "fp_b", "act_1", label="click btn", is_back_edge=False))
        kwargs = sess.run.call_args[1]
        assert kwargs["from_fp"] == "fp_a"
        assert kwargs["to_fp"] == "fp_b"
        assert kwargs["aid"] == "act_1"


class TestPersistViolation:
    def test_upserts_violation_node(self, gs, mock_driver):
        sess = _session(mock_driver)
        from apps.agent.contracts import Violation

        v = Violation(
            "v-1", "fp_abc", "e-admin", "forbidden_present", "critical", "admin link visible"
        )
        gs.persist_violation(v)
        calls = [call[0][0] for call in sess.run.call_args_list]
        assert any("MERGE" in q and "ViolationNode" in q for q in calls)

    def test_links_violation_to_state(self, gs, mock_driver):
        sess = _session(mock_driver)
        from apps.agent.contracts import Violation

        v = Violation("v-1", "fp_abc", "e-admin", "forbidden_present", "critical", "rationale")
        gs.persist_violation(v)
        calls = [call[0][0] for call in sess.run.call_args_list]
        assert any("HAS_VIOLATION" in q for q in calls)

    def test_links_violation_to_expectation(self, gs, mock_driver):
        sess = _session(mock_driver)
        from apps.agent.contracts import Violation

        v = Violation("v-1", "fp_abc", "e-admin", "forbidden_present", "critical", "rationale")
        gs.persist_violation(v)
        calls = [call[0][0] for call in sess.run.call_args_list]
        assert any("VIOLATES" in q for q in calls)


class TestMarkAndIsVisited:
    def test_mark_visited_uses_merge(self, gs, mock_driver):
        sess = _session(mock_driver)
        gs.mark_visited("fp_abc", "act_1")
        query = sess.run.call_args[0][0]
        assert "MERGE" in query
        assert "VisitedPair" in query

    def test_is_visited_returns_false_when_no_record(self, gs, mock_driver):
        sess = _session(mock_driver)
        sess.run.return_value.single.return_value = None
        assert not gs.is_visited("fp_abc", "act_1")

    def test_is_visited_returns_true_when_record_exists(self, gs, mock_driver):
        sess = _session(mock_driver)
        sess.run.return_value.single.return_value = {"v": {}}
        assert gs.is_visited("fp_abc", "act_1")


class TestGetScanCounts:
    def test_returns_zero_when_no_record(self, gs, mock_driver):
        sess = _session(mock_driver)
        sess.run.return_value.single.return_value = None
        counts = gs.get_scan_counts("scan-123")
        assert counts == {"states_explored": 0, "violations_found": 0}

    def test_returns_counts_from_neo4j(self, gs, mock_driver):
        sess = _session(mock_driver)
        sess.run.return_value.single.return_value = {"states": 7, "violations": 2}
        counts = gs.get_scan_counts("scan-123")
        assert counts["states_explored"] == 7
        assert counts["violations_found"] == 2


class TestClose:
    def test_close_delegates_to_driver(self, gs, mock_driver):
        gs.close()
        mock_driver.close.assert_called_once()
