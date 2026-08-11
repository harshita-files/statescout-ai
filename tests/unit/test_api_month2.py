"""
Unit tests for services.api.main — Month 2 endpoints.

Uses FastAPI's TestClient with mocked GraphStore so no Neo4j or Redis is needed.

Run:  pytest tests/unit/test_api_month2.py -v
"""

from typing import Any, ClassVar
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from services.api.main import app


@pytest.fixture
def mock_graph():
    """A MagicMock that satisfies every GraphStore method called by the API."""
    g = MagicMock()
    g.create_policy_context.return_value = None
    g.update_scan_status.return_value = None
    g.get_scan_counts.return_value = {"states_explored": 0, "violations_found": 0}
    g.get_violations_for_scan.return_value = []
    g.persist_state.return_value = None
    g.persist_edge.return_value = None
    g.persist_violation.return_value = None
    return g


@pytest.fixture
def client(mock_graph):
    """TestClient with injected mock GraphStore."""
    app.state.graph = mock_graph
    app.state.redis = MagicMock()
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------


class TestHealth:
    def test_returns_200(self, client):
        r = client.get("/health")
        assert r.status_code == 200

    def test_returns_ok_status(self, client):
        r = client.get("/health")
        assert r.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# POST /scan/start
# ---------------------------------------------------------------------------


class TestStartScan:
    def test_returns_200(self, client):
        r = client.post(
            "/scan/start",
            json={"url": "http://app.local", "policy": "guest must not see admin"},
        )
        assert r.status_code == 200

    def test_returns_scan_id(self, client):
        r = client.post("/scan/start", json={"url": "http://app.local", "policy": "policy"})
        body = r.json()
        assert "scan_id" in body
        assert len(body["scan_id"]) == 36  # UUID4

    def test_status_is_queued(self, client):
        r = client.post("/scan/start", json={"url": "http://app.local", "policy": "policy"})
        assert r.json()["status"] == "queued"

    def test_calls_create_policy_context(self, client, mock_graph):
        client.post("/scan/start", json={"url": "http://app.local", "policy": "policy"})
        mock_graph.create_policy_context.assert_called_once()

    def test_missing_url_returns_422(self, client):
        r = client.post("/scan/start", json={"policy": "no url"})
        assert r.status_code == 422

    def test_missing_policy_returns_422(self, client):
        r = client.post("/scan/start", json={"url": "http://app.local"})
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# GET /scan/{id}/status
# ---------------------------------------------------------------------------


class TestScanStatus:
    def test_returns_200(self, client):
        r = client.get("/scan/some-id/status")
        assert r.status_code == 200

    def test_returns_real_counts_from_graph(self, client, mock_graph):
        mock_graph.get_scan_counts.return_value = {"states_explored": 12, "violations_found": 3}
        r = client.get("/scan/some-id/status")
        body = r.json()
        assert body["states_explored"] == 12
        assert body["violations_found"] == 3

    def test_returns_queued_when_zero_counts(self, client, mock_graph):
        mock_graph.get_scan_counts.return_value = {"states_explored": 0, "violations_found": 0}
        r = client.get("/scan/some-id/status")
        assert r.json()["status"] == "queued"


# ---------------------------------------------------------------------------
# POST /crawl/state-visit
# ---------------------------------------------------------------------------


class TestCrawlStateVisit:
    _payload: ClassVar[dict[str, Any]] = {
        "scan_id": "scan-111",
        "url": "/dashboard",
        "dom": "<h1>Dashboard</h1>",
        "ax_tree": {"role": "document", "name": "Dashboard"},
        "title": "Dashboard",
    }

    def test_returns_200(self, client):
        r = client.post("/crawl/state-visit", json=self._payload)
        assert r.status_code == 200

    def test_returns_accepted_true(self, client):
        r = client.post("/crawl/state-visit", json=self._payload)
        assert r.json()["accepted"] is True

    def test_returns_fingerprint(self, client):
        r = client.post("/crawl/state-visit", json=self._payload)
        fp = r.json().get("state_fingerprint", "")
        assert len(fp) == 64  # SHA-256 hex

    def test_calls_persist_state(self, client, mock_graph):
        client.post("/crawl/state-visit", json=self._payload)
        mock_graph.persist_state.assert_called_once()

    def test_does_not_call_persist_edge_without_prev(self, client, mock_graph):
        """No edge should be written when prev_state_fingerprint is absent."""
        client.post("/crawl/state-visit", json=self._payload)
        mock_graph.persist_edge.assert_not_called()

    def test_calls_persist_edge_when_prev_given(self, client, mock_graph):
        payload = {**self._payload, "prev_state_fingerprint": "a" * 64, "action_id": "act_1"}
        client.post("/crawl/state-visit", json=payload)
        mock_graph.persist_edge.assert_called_once()

    def test_idempotent_fingerprint(self, client):
        r1 = client.post("/crawl/state-visit", json=self._payload)
        r2 = client.post("/crawl/state-visit", json=self._payload)
        assert r1.json()["state_fingerprint"] == r2.json()["state_fingerprint"]


# ---------------------------------------------------------------------------
# POST /violations/report
# ---------------------------------------------------------------------------


class TestViolationsReport:
    _payload: ClassVar[dict[str, Any]] = {
        "scan_id": "scan-111",
        "violation_id": "v-001",
        "state_fingerprint": "a" * 64,
        "expectation_id": "e-admin",
        "clause_type": "forbidden_present",
        "severity": "critical",
        "rationale": "Admin link visible to guest",
        "url": "/dashboard",
        "policy_violated": "guest must not see admin link",
    }

    def test_returns_200(self, client):
        r = client.post("/violations/report", json=self._payload)
        assert r.status_code == 200

    def test_returns_recorded_true(self, client):
        r = client.post("/violations/report", json=self._payload)
        assert r.json()["recorded"] is True

    def test_returns_violation_id(self, client):
        r = client.post("/violations/report", json=self._payload)
        assert r.json()["violation_id"] == "v-001"

    def test_calls_persist_violation(self, client, mock_graph):
        client.post("/violations/report", json=self._payload)
        mock_graph.persist_violation.assert_called_once()
