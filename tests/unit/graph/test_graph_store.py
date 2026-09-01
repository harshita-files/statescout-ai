"""
Unit tests for apps.agent.graph.graph_store

All tests mock the Neo4j driver — no real database or Docker required.

Critical invariant tested:
  - StateNode  → MERGE query  (dedup by fingerprint)
  - ActionEdge → CREATE query (not MERGE — every traversal is preserved)

Run:  pytest tests/unit/test_graph_store.py -v
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from apps.agent.graph.graph_store import GraphStore


@pytest.fixture
def mock_neo4j_driver():
    """
    Patch GraphDatabase.driver so no real Neo4j connection is made.

    Yields the mock driver instance (not the class) so tests can inspect
    call counts and arguments directly.
    """
    with patch("apps.agent.graph.graph_store.GraphDatabase.driver") as mock_cls:
        mock_drv = MagicMock()
        # verify_connectivity() is called in __init__; let it pass silently
        mock_drv.verify_connectivity.return_value = None
        mock_cls.return_value = mock_drv
        yield mock_drv


class TestGraphStoreInit:
    def test_reads_credentials_from_env(self, mock_neo4j_driver):
        """GraphStore must read NEO4J_* credentials from environment variables."""
        os.environ["NEO4J_URI"] = "bolt://test-host:7687"
        os.environ["NEO4J_USER"] = "testuser"
        os.environ["NEO4J_PASSWORD"] = "testpass"

        # The fixture has already patched GraphDatabase.driver.
        # Constructing GraphStore here causes the patched driver class to be
        # called — we can then inspect what arguments it received.
        with patch("apps.agent.graph.graph_store.GraphDatabase.driver") as mock_cls:
            mock_drv = MagicMock()
            mock_drv.verify_connectivity.return_value = None
            mock_cls.return_value = mock_drv

            GraphStore()

            mock_cls.assert_called_once_with(
                "bolt://test-host:7687",
                auth=("testuser", "testpass"),
            )

    def test_verify_connectivity_is_called(self, mock_neo4j_driver):
        """GraphStore.__init__ must call verify_connectivity to fail fast."""
        GraphStore()
        mock_neo4j_driver.verify_connectivity.assert_called_once()


class TestCreateStateNode:
    def test_uses_merge_query(self, mock_neo4j_driver):
        """StateNode creation must use MERGE (idempotent by fingerprint)."""
        mock_session = MagicMock()
        mock_neo4j_driver.session.return_value.__enter__.return_value = mock_session

        gs = GraphStore()
        gs.create_state_node("fp_abc123", "https://app.local/dashboard")

        mock_session.run.assert_called_once()
        query = mock_session.run.call_args[0][0]
        assert "MERGE" in query, "StateNode write must use MERGE"

    def test_merge_query_contains_on_create_set(self, mock_neo4j_driver):
        """MERGE query must include ON CREATE SET so timestamps only set once."""
        mock_session = MagicMock()
        mock_neo4j_driver.session.return_value.__enter__.return_value = mock_session

        gs = GraphStore()
        gs.create_state_node("fp_abc123", "https://app.local/dashboard")

        query = mock_session.run.call_args[0][0]
        assert "ON CREATE SET" in query

    def test_passes_fingerprint_and_url(self, mock_neo4j_driver):
        """create_state_node must pass fp and url as query parameters."""
        mock_session = MagicMock()
        mock_neo4j_driver.session.return_value.__enter__.return_value = mock_session

        gs = GraphStore()
        gs.create_state_node("fp_abc123", "https://app.local/dashboard")

        kwargs = mock_session.run.call_args[1]
        assert kwargs.get("fp") == "fp_abc123"
        assert kwargs.get("url") == "https://app.local/dashboard"


class TestCreateActionEdge:
    def test_uses_create_not_merge(self, mock_neo4j_driver):
        """ActionEdge must use CREATE (not MERGE) — every traversal is recorded."""
        mock_session = MagicMock()
        mock_neo4j_driver.session.return_value.__enter__.return_value = mock_session

        gs = GraphStore()
        gs.create_action_edge("fp_abc", "fp_xyz", "click")

        query = mock_session.run.call_args[0][0]
        assert "CREATE" in query, "ActionEdge write must use CREATE"
        assert "MERGE" not in query, "ActionEdge must NOT use MERGE (cycles must be preserved)"

    def test_passes_all_three_parameters(self, mock_neo4j_driver):
        """create_action_edge must pass from_fp, to_fp, and action as query params."""
        mock_session = MagicMock()
        mock_neo4j_driver.session.return_value.__enter__.return_value = mock_session

        gs = GraphStore()
        gs.create_action_edge("fp_abc", "fp_xyz", "click")

        kwargs = mock_session.run.call_args[1]
        assert kwargs.get("from_fp") == "fp_abc"
        assert kwargs.get("to_fp") == "fp_xyz"
        assert kwargs.get("action") == "click"


class TestClose:
    def test_close_calls_driver_close(self, mock_neo4j_driver):
        """close() must delegate to driver.close() to release connection pool."""
        gs = GraphStore()
        gs.close()
        mock_neo4j_driver.close.assert_called_once()
