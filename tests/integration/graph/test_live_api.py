"""LIVE — the actual HTTP endpoints against real Neo4j + Redis.

`tests/integration/graph/test_live_crawl.py` proves the exploration loop and
`Neo4jGraph` work together; it never goes through FastAPI. This file closes
that gap: it drives `POST /scan/start`, `GET /scan/{id}/status`,
`GET /scan/{id}/report`, and `POST /scan/{id}/stop` as real HTTP requests
against the running app, with `app.state.graph` wired to a **real**
`GraphStore` — not the mocked one `tests/unit/graph/test_api_month2.py` uses.

Requires the stack:

    docker compose -f infra/docker-compose.yml up -d

Run:

    uv run pytest -m live tests/integration/graph/test_live_api.py -v

Excluded from the default CI gate (`pytest -m "not live"`). Skips the module
if the stack is unreachable, rather than erroring.
"""

from __future__ import annotations

import contextlib
import time
import uuid
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.live

#: services/api/runner.build_scan_ports degrades to FakeCrawler + FakePerception
#: on this branch (Track A/C aren't merged here) — a 4-page app, two cycles.
SEED = "http://fake.test/login"
EXPECTED_STATES = 4


@pytest.fixture
def client():
    """A TestClient wired to a real GraphStore. Skips if Neo4j/Redis are down."""
    store = None
    try:
        from apps.agent.graph.graph_store import GraphStore

        store = GraphStore()
    except Exception as exc:  # ServiceUnavailable, ConnectionError, OSError, ...
        if store is not None:
            with contextlib.suppress(Exception):
                store.close()
        pytest.skip(f"Neo4j/Redis not reachable ({exc}) — run docker compose up")

    from fastapi.testclient import TestClient

    from services.api.main import app

    app.state.graph = store
    app.state.redis = MagicMock()
    with TestClient(app) as c:
        yield c, store
    store.close()


def _cleanup(store, scan_id: str) -> None:
    with store.driver.session() as session:
        session.run(
            "MATCH (p:PolicyContext {scan_id: $sid}) "
            "OPTIONAL MATCH (p)-[:CONTAINS]->(s:StateNode) "
            "DETACH DELETE p, s",
            sid=scan_id,
        )
    from services.api.runner import VisitedCache

    with contextlib.suppress(Exception):
        VisitedCache(scan_id).clear()


class TestLiveHTTPEndpoints:
    def test_start_status_report_round_trip_over_http(self, client):
        """The whole scan lifecycle, driven only through HTTP requests."""
        c, store = client
        scan_id: str | None = None
        try:
            start = c.post("/scan/start", json={"url": SEED, "policy": "no policy parser yet"})
            assert start.status_code == 200
            body = start.json()
            scan_id = body["scan_id"]
            assert body["status"] == "queued"

            status = None
            for _ in range(40):
                status = c.get(f"/scan/{scan_id}/status").json()
                if status["status"] in ("completed", "failed", "stopped"):
                    break
                time.sleep(0.25)

            assert status is not None, "scan never reached a terminal status"
            assert status["status"] == "completed", status
            assert status["states_explored"] == EXPECTED_STATES

            report = c.get(f"/scan/{scan_id}/report").json()
            assert report["scan_id"] == scan_id
            assert report["total_states"] == EXPECTED_STATES

            # Not just trusting the response body — the graph is really there.
            live_counts = store.get_scan_counts(scan_id)
            assert live_counts["states_explored"] == EXPECTED_STATES
        finally:
            if scan_id:
                _cleanup(store, scan_id)

    def test_unknown_scan_status_and_report_soft_fail(self, client):
        c, _store = client
        unknown = f"no-such-scan-{uuid.uuid4().hex[:8]}"

        status = c.get(f"/scan/{unknown}/status")
        assert status.status_code == 200
        assert status.json()["status"] == "queued"

        report = c.get(f"/scan/{unknown}/report")
        assert report.status_code == 200
        assert report.json()["violations"] == []

    def test_stop_over_http_is_idempotent_and_terminal(self, client):
        """Whether the fake crawl finishes before /stop lands or not, the scan
        must end in a terminal state and /stop must never error."""
        c, store = client
        start = c.post("/scan/start", json={"url": SEED, "policy": "x"})
        scan_id = start.json()["scan_id"]
        try:
            stop = c.post(f"/scan/{scan_id}/stop")
            assert stop.status_code == 200
            assert stop.json()["status"] in ("stopped", "stopping", "completed")

            status = None
            for _ in range(40):
                status = c.get(f"/scan/{scan_id}/status").json()
                if status["status"] in ("completed", "failed", "stopped"):
                    break
                time.sleep(0.25)
            assert status is not None
            assert status["status"] in ("completed", "failed", "stopped")
        finally:
            _cleanup(store, scan_id)
