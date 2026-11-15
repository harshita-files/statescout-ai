"""Run control — POST /scan/{id}/stop and visited-cache expiry — Track D, Month 2.

Month 2 exit criterion: *"FastAPI can start/stop/stream a run."* Start and
stream exist; this adds stop.

The stop contract (see `services/api/README.md`):
  - `POST /scan/{id}/stop` records intent on the PolicyContext (`status`).
  - Whatever drives the loop polls `GraphStore.is_stop_requested(scan_id)` between
    iterations and exits cleanly — the in-flight iteration is allowed to finish.
  - When a run reaches any terminal state, its Redis visited keys are given a
    TTL so they expire instead of leaking (`VisitedCache.set_ttl`).

Neo4j is mocked; the TTL wiring is asserted via a patched `VisitedCache`.

Run:  pytest tests/unit/graph/test_scan_stop.py -v
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from apps.agent.graph.graph_store import GraphStore

# ---------------------------------------------------------------------------
# GraphStore — the durable side of the stop contract
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_driver():
    with patch("apps.agent.graph.graph_store.GraphDatabase.driver") as mock_cls:
        drv = MagicMock()
        drv.verify_connectivity.return_value = None
        mock_cls.return_value = drv
        yield drv


@pytest.fixture
def gs(mock_driver):
    os.environ.setdefault("NEO4J_PASSWORD", "test")
    return GraphStore()


def _session(mock_driver) -> MagicMock:
    sess = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = sess
    return sess


class TestGetScan:
    def test_returns_policy_context_properties(self, gs, mock_driver):
        sess = _session(mock_driver)
        sess.run.return_value.single.return_value = {"p": {"scan_id": "s1", "status": "running"}}
        assert gs.get_scan("s1") == {"scan_id": "s1", "status": "running"}

    def test_returns_none_for_unknown_scan(self, gs, mock_driver):
        sess = _session(mock_driver)
        sess.run.return_value.single.return_value = None
        assert gs.get_scan("nope") is None


class TestIsStopRequested:
    @pytest.mark.parametrize(
        ("status", "expected"),
        [("stopping", True), ("stopped", True), ("running", False), ("queued", False)],
    )
    def test_reflects_policy_context_status(self, gs, mock_driver, status, expected):
        sess = _session(mock_driver)
        sess.run.return_value.single.return_value = {"p": {"status": status}}
        assert gs.is_stop_requested("s1") is expected

    def test_false_for_unknown_scan(self, gs, mock_driver):
        sess = _session(mock_driver)
        sess.run.return_value.single.return_value = None
        assert gs.is_stop_requested("nope") is False


class TestUpdateScanStatusTerminal:
    def test_terminal_status_stamps_finished_at(self, gs, mock_driver):
        sess = _session(mock_driver)
        gs.update_scan_status("s1", "stopped")
        query = sess.run.call_args[0][0]
        kwargs = sess.run.call_args[1]
        assert "finished_at" in query
        assert "stopped" in kwargs["terminal"]  # the terminal-status guard list


# ---------------------------------------------------------------------------
# POST /scan/{id}/stop
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_graph():
    g = MagicMock()
    g.get_scan.return_value = {"scan_id": "s1", "status": "running"}
    g.get_scan_counts.return_value = {"states_explored": 3, "violations_found": 1}
    g.update_scan_status.return_value = None
    return g


@pytest.fixture
def patched_visited_cache():
    # Both the stop endpoint's grace TTL and finalize_scan_sync's terminal TTL
    # go through services.api.runner.set_visited_ttl -> VisitedCache.
    with patch("services.api.runner.VisitedCache") as vc_cls:
        yield vc_cls.return_value


@pytest.fixture
def client(mock_graph, patched_visited_cache):
    from services.api.main import app

    app.state.graph = mock_graph
    app.state.redis = MagicMock()
    with TestClient(app) as c:
        yield c


class TestStopEndpoint:
    def test_running_scan_transitions_to_stopping(self, client, mock_graph):
        r = client.post("/scan/s1/stop")
        assert r.status_code == 200
        assert r.json()["status"] == "stopping"
        mock_graph.update_scan_status.assert_called_once_with("s1", "stopping")

    def test_running_scan_gives_visited_keys_a_grace_ttl(self, client, patched_visited_cache):
        client.post("/scan/s1/stop")
        patched_visited_cache.set_ttl.assert_called_once()
        assert patched_visited_cache.set_ttl.call_args[0][0] > 0

    def test_queued_scan_is_finalized_immediately(self, client, mock_graph, patched_visited_cache):
        mock_graph.get_scan.return_value = {"scan_id": "s1", "status": "queued"}
        r = client.post("/scan/s1/stop")
        assert r.json()["status"] == "stopped"
        mock_graph.update_scan_status.assert_called_once_with("s1", "stopped")
        patched_visited_cache.set_ttl.assert_called_once()

    def test_already_terminal_scan_is_idempotent(self, client, mock_graph):
        mock_graph.get_scan.return_value = {"scan_id": "s1", "status": "stopped"}
        r = client.post("/scan/s1/stop")
        assert r.json()["status"] == "stopped"
        mock_graph.update_scan_status.assert_not_called()

    def test_unknown_scan_soft_fails(self, client, mock_graph):
        mock_graph.get_scan.return_value = None
        r = client.post("/scan/does-not-exist/stop")
        assert r.status_code == 200
        assert r.json()["status"] == "failed"
