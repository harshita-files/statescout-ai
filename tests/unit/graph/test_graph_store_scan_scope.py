"""Scan-scoping for GraphStore — Track D, Month 2.

Month 1 shipped `get_scan_counts` / `get_violations_for_scan` querying
``WHERE s.scan_id = $sid`` — a property nothing ever wrote, so every scan
reported zero. Month 2 wires the real schema relationships the module docstring
already promised:

    (PolicyContext)-[:CONTAINS]->(StateNode)
    (PolicyContext)-[:HAS_EXPECTATION]->(ExpectationNode)

and the counts/report queries traverse them.

Neo4j is mocked — no Docker.

Run:  pytest tests/unit/graph/test_graph_store_scan_scope.py -v
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from apps.agent.contracts import ExpectationNode, ExpectationSet
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


def _session(mock_driver) -> MagicMock:
    sess = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = sess
    return sess


class _Record(dict):
    """A Neo4j-record stand-in: subscriptable, nothing more."""


class TestAttachStateToScan:
    def test_merges_a_contains_edge_from_the_policy_context(self, gs, mock_driver):
        sess = _session(mock_driver)
        gs.attach_state_to_scan("scan-1", "fp_abc")
        query = sess.run.call_args[0][0]
        assert "PolicyContext" in query
        assert "StateNode" in query
        assert "CONTAINS" in query
        assert "MERGE" in query

    def test_passes_scan_id_and_fingerprint(self, gs, mock_driver):
        sess = _session(mock_driver)
        gs.attach_state_to_scan("scan-1", "fp_abc")
        kwargs = sess.run.call_args[1]
        assert kwargs["sid"] == "scan-1"
        assert kwargs["fp"] == "fp_abc"


class TestPersistExpectation:
    def _node(self) -> ExpectationNode:
        return ExpectationNode(
            expectation_id="e-admin",
            polarity="must_not_exist",
            subject="admin-link",
            roles=("guest",),
            source_text="A guest must never see the admin link.",
        )

    def test_upserts_expectation_node_and_links_to_scan(self, gs, mock_driver):
        sess = _session(mock_driver)
        gs.persist_expectation("scan-1", self._node())
        query = sess.run.call_args[0][0]
        assert "MERGE (e:ExpectationNode" in query
        assert "HAS_EXPECTATION" in query

    def test_stores_the_clause_semantics(self, gs, mock_driver):
        sess = _session(mock_driver)
        gs.persist_expectation("scan-1", self._node())
        kwargs = sess.run.call_args[1]
        assert kwargs["eid"] == "e-admin"
        assert kwargs["pol"] == "must_not_exist"
        assert kwargs["subj"] == "admin-link"
        assert kwargs["roles"] == ["guest"]  # tuple -> list for Neo4j
        assert kwargs["sid"] == "scan-1"

    def test_persist_expectation_set_writes_both_halves(self, gs, mock_driver):
        sess = _session(mock_driver)
        policy = ExpectationSet(
            forbidden=(self._node(),),
            required=(
                ExpectationNode(
                    expectation_id="e-logout",
                    polarity="must_exist",
                    subject="logout-button",
                    source_text="Every page must offer logout.",
                ),
            ),
        )
        gs.persist_expectation_set("scan-1", policy)
        written = {c[1]["eid"] for c in sess.run.call_args_list}
        assert written == {"e-admin", "e-logout"}


class TestGetScanCounts:
    def test_traverses_contains_and_has_violation(self, gs, mock_driver):
        sess = _session(mock_driver)
        sess.run.return_value.single.return_value = {"states": 5, "violations": 2}
        counts = gs.get_scan_counts("scan-1")
        query = sess.run.call_args[0][0]
        assert "CONTAINS" in query
        assert "HAS_VIOLATION" in query
        assert "s.scan_id" not in query  # the Month 1 bug is gone
        assert counts == {"states_explored": 5, "violations_found": 2}

    def test_zero_when_no_policy_context(self, gs, mock_driver):
        sess = _session(mock_driver)
        sess.run.return_value.single.return_value = None
        assert gs.get_scan_counts("nope") == {
            "states_explored": 0,
            "violations_found": 0,
        }


class TestGetViolationsForScan:
    def test_traverses_contains_and_returns_state_url(self, gs, mock_driver):
        sess = _session(mock_driver)
        sess.run.return_value = [
            _Record(
                v={"violation_id": "v1", "rationale": "admin link visible"},
                state_url="/dashboard",
            )
        ]
        rows = gs.get_violations_for_scan("scan-1")
        query = sess.run.call_args[0][0]
        assert "CONTAINS" in query
        assert "HAS_VIOLATION" in query
        assert rows[0]["violation_id"] == "v1"
        assert rows[0]["url"] == "/dashboard"

    def test_empty_when_no_violations(self, gs, mock_driver):
        sess = _session(mock_driver)
        sess.run.return_value = []
        assert gs.get_violations_for_scan("scan-1") == []
