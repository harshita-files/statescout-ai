"""Optional shared-secret auth for the local API — Track D.

Local-first, single-user: the handbook rules out hosted / multi-tenant auth for
v1 (§1.2, §1.5). This is the minimal thing that keeps the API from being wide
open on a shared machine — one static key, sent by the client as an ``X-API-Key``
header, checked against the ``STATESCOUT_API_KEY`` environment variable.

Auth is **off** when ``STATESCOUT_API_KEY`` is unset or empty — the default for
local dev and for CI. Set it (in ``.env``, which is git-ignored per NFR-11) to
lock the API down; the VS Code extension then sends the same value on every
request and on the WebSocket handshake.

``GET /health`` is always open (Docker healthcheck / liveness probe).
"""

from __future__ import annotations

import hmac
import os

from fastapi import Header, HTTPException, WebSocket, status

API_KEY_ENV = "STATESCOUT_API_KEY"
API_KEY_HEADER = "X-API-Key"


def _expected_key() -> str:
    return os.environ.get(API_KEY_ENV, "").strip()


def auth_enabled() -> bool:
    """True when a key is configured. Exposed so /health can report it."""
    return bool(_expected_key())


def _accepts(provided: str | None) -> bool:
    expected = _expected_key()
    if not expected:
        return True  # auth disabled
    if not provided:
        return False
    return hmac.compare_digest(provided, expected)  # constant-time (NFR-11)


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """FastAPI dependency: 401 unless the header matches, or auth is disabled."""
    if not _accepts(x_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Missing or invalid {API_KEY_HEADER} header.",
            headers={"WWW-Authenticate": API_KEY_HEADER},
        )


async def websocket_authorized(websocket: WebSocket) -> bool:
    """Handshake check for the WS endpoint. Closes the socket on mismatch and
    returns False; the caller should then return without accepting."""
    if _accepts(websocket.headers.get(API_KEY_HEADER.lower())):
        return True
    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
    return False
