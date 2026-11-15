"""Optional X-API-Key auth — Track D, Month 2.

`STATESCOUT_API_KEY` unset  → auth disabled, every endpoint open (dev / CI).
`STATESCOUT_API_KEY` set     → X-API-Key header required on everything but /health.

Run:  pytest tests/unit/graph/test_auth.py -v
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from services.api import auth

KEY = "s3cr3t-local-key"


@pytest.fixture
def client():
    from services.api.main import app

    app.state.graph = MagicMock(
        get_scan=MagicMock(return_value={"scan_id": "s", "status": "running"}),
        get_scan_counts=MagicMock(return_value={"states_explored": 0, "violations_found": 0}),
    )
    app.state.redis = MagicMock()
    with patch("services.api.main.run_scan"), TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# auth.py units
# ---------------------------------------------------------------------------


class TestAuthUnit:
    def test_disabled_when_env_unset(self, monkeypatch):
        monkeypatch.delenv(auth.API_KEY_ENV, raising=False)
        assert auth.auth_enabled() is False
        assert auth._accepts(None) is True  # anything goes

    def test_enabled_when_env_set(self, monkeypatch):
        monkeypatch.setenv(auth.API_KEY_ENV, KEY)
        assert auth.auth_enabled() is True
        assert auth._accepts(KEY) is True
        assert auth._accepts("wrong") is False
        assert auth._accepts(None) is False

    def test_require_api_key_raises_401_on_mismatch(self, monkeypatch):
        monkeypatch.setenv(auth.API_KEY_ENV, KEY)
        with pytest.raises(Exception) as ei:
            auth.require_api_key(x_api_key="nope")
        assert getattr(ei.value, "status_code", None) == 401

    def test_require_api_key_passes_when_disabled(self, monkeypatch):
        monkeypatch.delenv(auth.API_KEY_ENV, raising=False)
        assert auth.require_api_key(x_api_key=None) is None

    @pytest.mark.asyncio
    async def test_websocket_authorized_closes_on_mismatch(self, monkeypatch):
        monkeypatch.setenv(auth.API_KEY_ENV, KEY)
        ws = MagicMock(headers={}, close=AsyncMock())
        assert await auth.websocket_authorized(ws) is False
        ws.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_websocket_authorized_allows_with_header(self, monkeypatch):
        monkeypatch.setenv(auth.API_KEY_ENV, KEY)
        ws = MagicMock(headers={"x-api-key": KEY}, close=AsyncMock())
        assert await auth.websocket_authorized(ws) is True
        ws.close.assert_not_called()


# ---------------------------------------------------------------------------
# endpoint enforcement
# ---------------------------------------------------------------------------


class TestHealthAlwaysOpen:
    def test_no_key_configured(self, client, monkeypatch):
        monkeypatch.delenv(auth.API_KEY_ENV, raising=False)
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["auth_required"] is False

    def test_key_configured_still_open_and_reports_it(self, client, monkeypatch):
        monkeypatch.setenv(auth.API_KEY_ENV, KEY)
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["auth_required"] is True


class TestAuthDisabled:
    def test_endpoints_open_without_header(self, client, monkeypatch):
        monkeypatch.delenv(auth.API_KEY_ENV, raising=False)
        assert client.get("/scan/s1/status").status_code == 200
        assert client.post("/scan/s1/stop").status_code == 200


class TestAuthEnabled:
    @pytest.fixture(autouse=True)
    def _key(self, monkeypatch):
        monkeypatch.setenv(auth.API_KEY_ENV, KEY)

    def test_401_without_header(self, client):
        assert client.get("/scan/s1/status").status_code == 401
        assert (
            client.post("/scan/start", json={"url": "http://a", "policy": "p"}).status_code == 401
        )

    def test_401_with_wrong_header(self, client):
        assert client.get("/scan/s1/status", headers={"X-API-Key": "wrong"}).status_code == 401

    def test_200_with_correct_header(self, client):
        assert client.get("/scan/s1/status", headers={"X-API-Key": KEY}).status_code == 200
        assert (
            client.post(
                "/scan/start",
                json={"url": "http://a", "policy": "p"},
                headers={"X-API-Key": KEY},
            ).status_code
            == 200
        )
