"""
Redis-backed visited-state cache for StateScout AI — Track D.

Month 2 upgrade: Keys are now session-scoped to scan_id so multiple parallel
scans are isolated and clear() only resets the current session.

Key pattern:  session:{scan_id}:visited:{state_id}:{action_id}

Implements the is_visited / mark_visited half of GraphPort (contracts.py).

Note: The constructor does NOT ping Redis on startup — connectivity failures
surface naturally on first use, keeping imports safe for unit tests using fakeredis.
"""

from __future__ import annotations

import os

import redis


class VisitedCache:
    """Session-scoped Redis cache tracking (state_id, action_id) pairs.

    Parameters
    ----------
    scan_id:
        The active scan session.  All keys written by this instance are
        namespaced under ``session:{scan_id}:*``.
    redis_url:
        Optional override for the Redis URL.  Defaults to the ``REDIS_URL``
        environment variable, then ``redis://localhost:6379``.
    """

    def __init__(self, scan_id: str, redis_url: str | None = None) -> None:
        self.scan_id = scan_id
        url = redis_url or os.environ.get("REDIS_URL", "redis://localhost:6379")
        self.r = redis.from_url(url, decode_responses=True)

    # ------------------------------------------------------------------
    # Key helpers
    # ------------------------------------------------------------------

    def _key(self, state_id: str, action_id: str) -> str:
        return f"session:{self.scan_id}:visited:{state_id}:{action_id}"

    def _session_pattern(self) -> str:
        return f"session:{self.scan_id}:*"

    # ------------------------------------------------------------------
    # Public API  (satisfies GraphPort.is_visited / mark_visited)
    # ------------------------------------------------------------------

    def is_visited(self, state_id: str, action_id: str) -> bool:
        """Return True if (state_id, action_id) has been claimed for this scan."""
        return self.r.exists(self._key(state_id, action_id)) == 1

    def mark_visited(self, state_id: str, action_id: str) -> None:
        """Claim (state_id, action_id) BEFORE the action executes (ADR-001 decision 3).

        Idempotent — calling twice is safe.
        """
        self.r.set(self._key(state_id, action_id), 1)

    def set_ttl(self, seconds: int) -> None:
        """Set an expiry on all visited keys for this scan session.

        Called when a scan completes or fails so keys expire automatically
        rather than accumulating indefinitely.
        """
        cursor = 0
        pattern = self._session_pattern()
        while True:
            cursor, keys = self.r.scan(cursor, match=pattern, count=100)
            if keys:
                pipe = self.r.pipeline()
                for key in keys:
                    pipe.expire(key, seconds)
                pipe.execute()
            if cursor == 0:
                break

    def clear(self) -> None:
        """Delete all visited marks for this scan session only.

        Uses SCAN + DEL rather than FLUSHDB so other sessions are not affected.
        Called at the start of a new scan and in tests.
        """
        cursor = 0
        pattern = self._session_pattern()
        while True:
            cursor, keys = self.r.scan(cursor, match=pattern, count=100)
            if keys:
                self.r.delete(*keys)
            if cursor == 0:
                break
