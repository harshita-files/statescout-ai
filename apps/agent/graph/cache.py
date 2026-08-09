"""
Redis-backed visited-state cache for StateScout AI — Track D.

Provides O(1) deduplication of (state_fingerprint, action) pairs during a
crawl session, preventing infinite loops in cyclic UI graphs (NFR-05).

The cache uses a flat Redis key-space:  ``visited:{fingerprint}:{action}``

Note: The constructor does NOT ping Redis on startup.  Connectivity failures
surface naturally when the first read/write is attempted, which keeps imports
safe in environments where Redis may not be available (e.g., unit tests using
fakeredis).
"""

import os
import redis


class VisitedCache:
    """
    Thin wrapper around Redis for tracking visited (state, action) pairs.

    Parameters
    ----------
    redis_url:
        Optional override for the Redis connection URL.  Defaults to the
        ``REDIS_URL`` environment variable, then ``redis://localhost:6379``.
    """

    def __init__(self, redis_url: str | None = None):
        url = redis_url or os.environ.get("REDIS_URL", "redis://localhost:6379")
        self.r = redis.from_url(url, decode_responses=True)
        # No ping() here — fail-fast happens on first actual operation,
        # keeping the constructor safe for import without a live Redis server.

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_visited(self, state_fp: str, action: str) -> bool:
        """Return True if the (state_fp, action) pair has been visited."""
        key = f"visited:{state_fp}:{action}"
        return self.r.exists(key) == 1

    def mark_visited(self, state_fp: str, action: str) -> None:
        """Record that the (state_fp, action) pair has been visited."""
        key = f"visited:{state_fp}:{action}"
        self.r.set(key, 1)

    def clear(self) -> None:
        """
        Delete all visited marks from the cache.

        Used during tests and at the start of a new crawl session.
        """
        keys = self.r.keys("visited:*")
        if keys:
            self.r.delete(*keys)
