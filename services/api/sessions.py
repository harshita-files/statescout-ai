"""Login and per-project sessions for the local API — Track D.

Why this exists
---------------
``services/api/auth.py`` is a single static shared secret: it answers "may this
client call the API at all", and nothing else. It has no notion of *who* is
calling or of *what they are working on*, so two projects driven from two VS
Code windows are indistinguishable to it and share one undifferentiated
identity.

This module adds the missing layer, in the shape the SRS asks for: **one login,
one session per project**.

- ``POST /auth/login`` exchanges the configured ``STATESCOUT_API_KEY`` for a
  short-lived *access token*. That is the login, and it happens once.
- ``POST /auth/sessions`` opens a *session* bound to one ``project_id``. The
  same login may hold several at once, one per project, and each has its own
  lifecycle: ending one leaves the others untouched.

This supersedes the "local-first, single-user, no sessions" decision recorded in
``auth.py`` (handbook Sections 1.2 and 1.5). See ``docs/adr-003-api-sessions.md``
for what changed and why.

Design constraints honoured here
--------------------------------
- **No new dependencies** (CLAUDE.md). Tokens are signed with stdlib
  ``hmac``/``hashlib``, not PyJWT, and compared in constant time.
- **No secrets in logs or responses** (NFR-11). The API key is never echoed, and
  listing sessions never returns their tokens.
- ``contracts.py`` is untouched: nothing here crosses a module boundary.

Known limits for v1
-------------------
The store is in-process, so sessions do not survive a restart and do not span
multiple uvicorn workers. That matches the local-first deployment the handbook
describes; moving the store to Redis (already a dependency) is the documented
next step if the API is ever run with more than one worker.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, Field

__all__ = [
    "SessionClaims",
    "create_router",
    "mint_session",
    "require_login",
    "reset_store",
    "verify_session",
]

API_KEY_ENV = "STATESCOUT_API_KEY"
SECRET_ENV = "STATESCOUT_SESSION_SECRET"
TTL_ENV = "STATESCOUT_SESSION_TTL_SECONDS"

#: Eight hours: long enough for a working day, short enough that a leaked token
#: on a shared machine is not indefinite.
DEFAULT_TTL_SECONDS = 8 * 60 * 60

#: There is exactly one identity in v1 (see the ADR). Named rather than implied,
#: so the store is already keyed correctly if real users ever arrive.
LOCAL_USER = "local"

_TYP_ACCESS = "access"
_TYP_SESSION = "session"

#: Signing key of last resort: no API key, no explicit secret. Regenerated per
#: process, so tokens from a previous run stop verifying after a restart.
_EPHEMERAL_SECRET = secrets.token_bytes(32)


def _now() -> float:
    """Indirection so tests can move the clock without sleeping."""
    return time.time()


def _ttl_seconds() -> int:
    raw = os.environ.get(TTL_ENV, "").strip()
    if not raw:
        return DEFAULT_TTL_SECONDS
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_TTL_SECONDS
    return value if value > 0 else DEFAULT_TTL_SECONDS


def _signing_secret() -> bytes:
    """Explicit secret, else one derived from the API key, else per-process.

    Derived rather than reused directly, so a token can never be reversed into
    the API key even if the signing input is known.
    """
    explicit = os.environ.get(SECRET_ENV, "").strip()
    if explicit:
        return explicit.encode("utf-8")
    api_key = os.environ.get(API_KEY_ENV, "").strip()
    if api_key:
        return hashlib.sha256(b"statescout-session-v1:" + api_key.encode("utf-8")).digest()
    return _EPHEMERAL_SECRET


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(payload: str) -> str:
    return _b64(hmac.new(_signing_secret(), payload.encode("ascii"), hashlib.sha256).digest())


def _mint(claims: dict[str, Any]) -> str:
    payload = _b64(json.dumps(claims, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return f"{payload}.{_sign(payload)}"


def _read(token: str, expected_typ: str) -> dict[str, Any] | None:
    """Verify signature, type and expiry. Returns None on any failure.

    Deliberately total: a malformed, forged or expired token is simply not a
    token. Callers turn None into 401 rather than leaking which check failed.
    """
    if not token or token.count(".") != 1:
        return None
    payload, _, signature = token.partition(".")
    if not hmac.compare_digest(signature, _sign(payload)):
        return None
    try:
        claims = json.loads(_unb64(payload))
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(claims, dict) or claims.get("typ") != expected_typ:
        return None
    expires_at = claims.get("exp")
    if not isinstance(expires_at, (int, float)) or expires_at <= _now():
        return None
    return claims


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


@dataclass
class SessionClaims:
    """A live session: one user, one project."""

    session_id: str
    project_id: str
    user_id: str
    created_at: float
    expires_at: float
    last_seen: float


@dataclass
class _Store:
    #: user_id -> project_id -> session_id. One session per project, by design.
    by_project: dict[str, dict[str, str]] = field(default_factory=dict)
    #: session_id -> record
    by_id: dict[str, SessionClaims] = field(default_factory=dict)
    #: Logins that have not been revoked. Logging out drops the login and every
    #: session it opened.
    logins: set[str] = field(default_factory=set)


_store = _Store()


def reset_store() -> None:
    """Drop every login and session. Used by tests and by lifespan shutdown."""
    global _store
    _store = _Store()


def _prune() -> None:
    dead = [sid for sid, record in _store.by_id.items() if record.expires_at <= _now()]
    for sid in dead:
        record = _store.by_id.pop(sid, None)
        if record is not None:
            _store.by_project.get(record.user_id, {}).pop(record.project_id, None)


def mint_session(user_id: str, project_id: str) -> tuple[SessionClaims, str]:
    """Open, or re-join, this user's session for one project.

    Re-joining matters: a second editor window on the same project must land on
    the same session rather than forking a rival one.
    """
    _prune()
    now = _now()
    existing_id = _store.by_project.setdefault(user_id, {}).get(project_id)
    if existing_id and existing_id in _store.by_id:
        record = _store.by_id[existing_id]
        record.last_seen = now
    else:
        record = SessionClaims(
            session_id=secrets.token_urlsafe(16),
            project_id=project_id,
            user_id=user_id,
            created_at=now,
            expires_at=now + _ttl_seconds(),
            last_seen=now,
        )
        _store.by_id[record.session_id] = record
        _store.by_project[user_id][project_id] = record.session_id

    token = _mint(
        {
            "typ": _TYP_SESSION,
            "sid": record.session_id,
            "pid": record.project_id,
            "sub": record.user_id,
            "iat": record.created_at,
            "exp": record.expires_at,
        }
    )
    return record, token


def verify_session(token: str) -> SessionClaims | None:
    """Resolve a session token to a live session, or None.

    Both halves have to agree: the token must verify *and* the session must
    still be in the store, so revoking one project's session takes effect
    immediately even though its token is still cryptographically intact.
    """
    claims = _read(token, _TYP_SESSION)
    if claims is None:
        return None
    record = _store.by_id.get(str(claims.get("sid", "")))
    if record is None or record.expires_at <= _now():
        return None
    if record.project_id != claims.get("pid") or record.user_id != claims.get("sub"):
        return None
    record.last_seen = _now()
    return record


def end_session(session_id: str) -> bool:
    record = _store.by_id.pop(session_id, None)
    if record is None:
        return False
    _store.by_project.get(record.user_id, {}).pop(record.project_id, None)
    return True


def end_all(user_id: str) -> int:
    projects = _store.by_project.pop(user_id, {})
    for session_id in projects.values():
        _store.by_id.pop(session_id, None)
    return len(projects)


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


def _expected_key() -> str:
    return os.environ.get(API_KEY_ENV, "").strip()


def _key_accepted(provided: str | None) -> bool:
    expected = _expected_key()
    if not expected:
        return True  # auth disabled, same rule as services/api/auth.py
    return bool(provided) and hmac.compare_digest(provided or "", expected)


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        return ""
    return authorization[7:].strip()


def require_login(authorization: str | None = Header(default=None)) -> str:
    """FastAPI dependency: a valid, unrevoked access token. Returns the user id."""
    claims = _read(_bearer(authorization), _TYP_ACCESS)
    if claims is None or str(claims.get("jti", "")) not in _store.logins:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid access token. Call POST /auth/login first.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return str(claims.get("sub", LOCAL_USER))


# ---------------------------------------------------------------------------
# Wire models
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    api_key: str | None = Field(
        default=None,
        description=(
            "The value of STATESCOUT_API_KEY. May be omitted when no key is "
            "configured, which is the default for local development."
        ),
    )


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: float
    auth_required: bool


class SessionRequest(BaseModel):
    project_id: str = Field(..., description="Project this session is bound to.")


class SessionResponse(BaseModel):
    session_id: str
    session_token: str
    project_id: str
    created_at: float
    expires_at: float


class SessionSummary(BaseModel):
    """A listed session. Carries no token: listing must not hand them out."""

    session_id: str
    project_id: str
    created_at: float
    expires_at: float
    last_seen: float


class SessionListResponse(BaseModel):
    sessions: list[SessionSummary]


def _summary(record: SessionClaims) -> SessionSummary:
    return SessionSummary(
        session_id=record.session_id,
        project_id=record.project_id,
        created_at=record.created_at,
        expires_at=record.expires_at,
        last_seen=record.last_seen,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def create_router() -> APIRouter:
    router = APIRouter(prefix="/auth", tags=["auth"])

    @router.post("/login", response_model=LoginResponse)
    async def login(body: LoginRequest | None = None) -> LoginResponse:
        """Exchange the configured API key for an access token.

        The key is never echoed back, and a wrong key is refused without
        repeating what was sent (NFR-11).
        """
        provided = body.api_key if body else None
        if not _key_accepted(provided):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        now = _now()
        expires_at = now + _ttl_seconds()
        login_id = secrets.token_urlsafe(16)
        _store.logins.add(login_id)
        token = _mint(
            {
                "typ": _TYP_ACCESS,
                "jti": login_id,
                "sub": LOCAL_USER,
                "iat": now,
                "exp": expires_at,
            }
        )
        return LoginResponse(
            access_token=token, expires_at=expires_at, auth_required=bool(_expected_key())
        )

    @router.post("/sessions", response_model=SessionResponse, status_code=201)
    async def open_session(
        body: SessionRequest, user_id: str = Depends(require_login)
    ) -> SessionResponse:
        """Open, or re-join, this login's session for one project."""
        record, token = mint_session(user_id, body.project_id)
        return SessionResponse(
            session_id=record.session_id,
            session_token=token,
            project_id=record.project_id,
            created_at=record.created_at,
            expires_at=record.expires_at,
        )

    @router.get("/sessions", response_model=SessionListResponse)
    async def list_sessions(user_id: str = Depends(require_login)) -> SessionListResponse:
        """Every live session for this login, one per project."""
        _prune()
        ids = _store.by_project.get(user_id, {}).values()
        rows = [_summary(_store.by_id[sid]) for sid in ids if sid in _store.by_id]
        rows.sort(key=lambda row: row.created_at)
        return SessionListResponse(sessions=rows)

    @router.get("/sessions/{session_id}", response_model=SessionSummary)
    async def get_session(
        session_id: str, user_id: str = Depends(require_login)
    ) -> SessionSummary:
        _prune()
        record = _store.by_id.get(session_id)
        if record is None or record.user_id != user_id:
            raise HTTPException(status_code=404, detail=f"Unknown session '{session_id}'.")
        return _summary(record)

    @router.delete("/sessions/{session_id}", status_code=204)
    async def close_session(session_id: str, user_id: str = Depends(require_login)) -> Response:
        """End one project's session. The login's other sessions stay open."""
        record = _store.by_id.get(session_id)
        if record is None or record.user_id != user_id:
            raise HTTPException(status_code=404, detail=f"Unknown session '{session_id}'.")
        end_session(session_id)
        return Response(status_code=204)

    @router.post("/logout", status_code=204)
    async def logout(
        user_id: str = Depends(require_login), authorization: str | None = Header(default=None)
    ) -> Response:
        """End the login and every session it opened."""
        end_all(user_id)
        claims = _read(_bearer(authorization), _TYP_ACCESS)
        if claims is not None:
            _store.logins.discard(str(claims.get("jti", "")))
        return Response(status_code=204)

    return router
