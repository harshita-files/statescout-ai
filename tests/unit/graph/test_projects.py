"""Projects — saved (url + policy + role) targets — Track D, Month 2.

The last item on the handbook's Month 2 FastAPI scaffold list
("auth / projects / run / status / WS"). A `Project` node the VS Code extension
can create once and re-scan; `POST /scan/start` accepts a `project_id` instead of
a fresh url + policy.

Neo4j is mocked.

Run:  pytest tests/unit/graph/test_projects.py -v
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from apps.agent.graph.graph_store import GraphStore

# ---------------------------------------------------------------------------
# GraphStore CRUD
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
    return GraphStore()


def _session(mock_driver) -> MagicMock:
    sess = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = sess
    return sess


class TestGraphStoreProjects:
    def test_create_project_merges_on_id(self, gs, mock_driver):
        sess = _session(mock_driver)
        gs.create_project("p1", "Staging admin", "http://x", "guest sees no admin", "guest")
        query = sess.run.call_args[0][0]
        assert "MERGE (p:Project {project_id: $pid})" in query
        kwargs = sess.run.call_args[1]
        assert kwargs["pid"] == "p1"
        assert kwargs["name"] == "Staging admin"
        assert kwargs["url"] == "http://x"
        assert kwargs["role"] == "guest"

    def test_get_project_returns_dict_or_none(self, gs, mock_driver):
        sess = _session(mock_driver)
        sess.run.return_value.single.return_value = {"p": {"project_id": "p1", "name": "X"}}
        assert gs.get_project("p1") == {"project_id": "p1", "name": "X"}
        sess.run.return_value.single.return_value = None
        assert gs.get_project("nope") is None

    def test_list_projects(self, gs, mock_driver):
        sess = _session(mock_driver)
        sess.run.return_value = [
            {"p": {"project_id": "p1"}},
            {"p": {"project_id": "p2"}},
        ]
        assert [row["project_id"] for row in gs.list_projects()] == ["p1", "p2"]

    def test_update_project_returns_false_when_missing(self, gs, mock_driver):
        sess = _session(mock_driver)
        sess.run.return_value.single.return_value = None
        assert gs.update_project("nope", name="new") is False

    def test_delete_project_returns_true_when_deleted(self, gs, mock_driver):
        sess = _session(mock_driver)
        sess.run.return_value.single.return_value = {"ok": 1}
        assert gs.delete_project("p1") is True
        sess.run.return_value.single.return_value = None
        assert gs.delete_project("nope") is False

    def test_link_scan_to_project(self, gs, mock_driver):
        sess = _session(mock_driver)
        gs.link_scan_to_project("p1", "scan-1")
        query = sess.run.call_args[0][0]
        assert "Project" in query and "PolicyContext" in query and "HAS_SCAN" in query


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_graph():
    g = MagicMock()
    g.create_project.return_value = None
    g.list_projects.return_value = [
        {"project_id": "p1", "name": "A", "url": "u", "policy": "x", "role": "guest"}
    ]
    g.get_project.return_value = {
        "project_id": "p1",
        "name": "A",
        "url": "http://app",
        "policy": "guest sees no admin",
        "role": "guest",
    }
    g.update_project.return_value = True
    g.delete_project.return_value = True
    g.create_policy_context.return_value = None
    return g


@pytest.fixture
def client(mock_graph):
    from services.api.main import app

    app.state.graph = mock_graph
    app.state.redis = MagicMock()
    with patch("services.api.main.run_scan") as run, TestClient(app) as c:
        c._run_scan = run
        yield c


_BODY = {"name": "A", "url": "http://app", "policy": "guest sees no admin", "role": "guest"}


class TestProjectEndpoints:
    def test_create_returns_project_with_id(self, client, mock_graph):
        r = client.post("/projects", json=_BODY)
        assert r.status_code == 200
        body = r.json()
        assert len(body["project_id"]) == 36  # uuid4
        assert body["name"] == "A"
        mock_graph.create_project.assert_called_once()

    def test_list(self, client):
        r = client.get("/projects")
        assert r.status_code == 200
        assert r.json()[0]["project_id"] == "p1"

    def test_get_known(self, client):
        assert client.get("/projects/p1").status_code == 200

    def test_get_unknown_404(self, client, mock_graph):
        mock_graph.get_project.return_value = None
        assert client.get("/projects/nope").status_code == 404

    def test_update_unknown_404(self, client, mock_graph):
        mock_graph.update_project.return_value = False
        assert client.put("/projects/nope", json=_BODY).status_code == 404

    def test_delete(self, client):
        assert client.delete("/projects/p1").status_code == 204

    def test_delete_unknown_404(self, client, mock_graph):
        mock_graph.delete_project.return_value = False
        assert client.delete("/projects/nope").status_code == 404


class TestScanStartWithProject:
    def test_project_id_supplies_url_and_policy(self, client, mock_graph):
        r = client.post("/scan/start", json={"project_id": "p1"})
        assert r.status_code == 200
        mock_graph.create_policy_context.assert_called_once()
        kw = mock_graph.create_policy_context.call_args.kwargs
        assert kw["url"] == "http://app"
        assert kw["policy"] == "guest sees no admin"
        mock_graph.link_scan_to_project.assert_called_once()
        assert client._run_scan.call_args.kwargs["seed_url"] == "http://app"

    def test_unknown_project_id_404(self, client, mock_graph):
        mock_graph.get_project.return_value = None
        assert client.post("/scan/start", json={"project_id": "nope"}).status_code == 404

    def test_still_accepts_bare_url_and_policy(self, client):
        r = client.post("/scan/start", json={"url": "http://x", "policy": "p"})
        assert r.status_code == 200

    def test_requires_url_policy_or_project(self, client):
        assert client.post("/scan/start", json={"role": "guest"}).status_code == 422
