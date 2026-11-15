"""Login and per-project session tests — Track D.

The requirement these pin down: one login, but a separate session per project,
so the same user running two projects side by side (two VS Code windows, two
audits) keeps both alive and independent. Ending one must not end the other.

No network, no Neo4j, no new dependencies: tokens are stdlib HMAC.
"""

from __future__ import annotations

import time
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.api import sessions
from services.api.sessions import create_router

KEY = "sk-local-dev-key-123"


@pytest.fixture(autouse=True)
def _isolated_store(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Every test gets a clean store and a known signing secret."""
    monkeypatch.setenv("STATESCOUT_API_KEY", KEY)
    monkeypatch.setenv("STATESCOUT_SESSION_SECRET", "unit-test-signing-secret")
    sessions.reset_store()
    yield
    sessions.reset_store()


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(create_router())
    return TestClient(app)


def login(client: TestClient, key: str = KEY) -> str:
    response = client.post("/auth/login", json={"api_key": key})
    assert response.status_code == 200, response.text
    return str(response.json()["access_token"])


def open_session(client: TestClient, token: str, project_id: str) -> dict[str, Any]:
    response = client.post(
        "/auth/sessions",
        json={"project_id": project_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


def test_login_with_the_configured_key_returns_an_access_token(client: TestClient) -> None:
    response = client.post("/auth/login", json={"api_key": KEY})
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["expires_at"] > time.time()
    # The key itself must never be echoed back (NFR-11).
    assert KEY not in response.text


def test_login_with_a_wrong_key_is_rejected(client: TestClient) -> None:
    response = client.post("/auth/login", json={"api_key": "sk-wrong"})
    assert response.status_code == 401
    assert "sk-wrong" not in response.text


def test_login_is_open_when_no_api_key_is_configured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Parity with services/api/auth.py: unset key means auth is off for local dev."""
    monkeypatch.delenv("STATESCOUT_API_KEY", raising=False)
    response = client.post("/auth/login", json={})
    assert response.status_code == 200
    assert response.json()["access_token"]


# ---------------------------------------------------------------------------
# One login, a session per project
# ---------------------------------------------------------------------------


def test_two_projects_under_one_login_get_two_independent_sessions(client: TestClient) -> None:
    token = login(client)
    first = open_session(client, token, "project-alpha")
    second = open_session(client, token, "project-beta")

    assert first["session_id"] != second["session_id"]
    assert first["session_token"] != second["session_token"]
    assert first["project_id"] == "project-alpha"
    assert second["project_id"] == "project-beta"


def test_both_project_sessions_are_listed_for_the_same_login(client: TestClient) -> None:
    token = login(client)
    open_session(client, token, "project-alpha")
    open_session(client, token, "project-beta")

    response = client.get("/auth/sessions", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    projects = sorted(row["project_id"] for row in response.json()["sessions"])
    assert projects == ["project-alpha", "project-beta"]


def test_reopening_a_project_reuses_its_session(client: TestClient) -> None:
    """A second window on the same project must not fork a second session."""
    token = login(client)
    first = open_session(client, token, "project-alpha")
    again = open_session(client, token, "project-alpha")
    assert first["session_id"] == again["session_id"]


def test_ending_one_project_session_leaves_the_other_alive(client: TestClient) -> None:
    """The core requirement: two projects, independent lifecycles."""
    token = login(client)
    alpha = open_session(client, token, "project-alpha")
    beta = open_session(client, token, "project-beta")

    ended = client.delete(
        f"/auth/sessions/{alpha['session_id']}", headers={"Authorization": f"Bearer {token}"}
    )
    assert ended.status_code == 204

    assert sessions.verify_session(alpha["session_token"]) is None
    still_open = sessions.verify_session(beta["session_token"])
    assert still_open is not None
    assert still_open.project_id == "project-beta"


def test_logout_ends_every_session_for_the_login(client: TestClient) -> None:
    token = login(client)
    alpha = open_session(client, token, "project-alpha")
    beta = open_session(client, token, "project-beta")

    response = client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 204
    assert sessions.verify_session(alpha["session_token"]) is None
    assert sessions.verify_session(beta["session_token"]) is None


# ---------------------------------------------------------------------------
# Token integrity
# ---------------------------------------------------------------------------


def test_a_session_token_names_its_own_project(client: TestClient) -> None:
    token = login(client)
    alpha = open_session(client, token, "project-alpha")
    claims = sessions.verify_session(alpha["session_token"])
    assert claims is not None
    assert claims.project_id == "project-alpha"


def test_a_tampered_token_is_rejected(client: TestClient) -> None:
    token = login(client)
    alpha = open_session(client, token, "project-alpha")
    payload, _, signature = alpha["session_token"].partition(".")
    forged = f"{payload}x.{signature}"
    assert sessions.verify_session(forged) is None


def test_a_token_signed_with_another_secret_is_rejected(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = login(client)
    alpha = open_session(client, token, "project-alpha")
    monkeypatch.setenv("STATESCOUT_SESSION_SECRET", "a-different-secret")
    assert sessions.verify_session(alpha["session_token"]) is None


def test_an_expired_session_is_rejected(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STATESCOUT_SESSION_TTL_SECONDS", "1")
    token = login(client)
    alpha = open_session(client, token, "project-alpha")
    monkeypatch.setattr(sessions, "_now", lambda: time.time() + 120)
    assert sessions.verify_session(alpha["session_token"]) is None


def test_opening_a_session_needs_a_valid_login(client: TestClient) -> None:
    response = client.post(
        "/auth/sessions",
        json={"project_id": "project-alpha"},
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert response.status_code == 401


def test_opening_a_session_without_a_login_is_rejected(client: TestClient) -> None:
    response = client.post("/auth/sessions", json={"project_id": "project-alpha"})
    assert response.status_code == 401
