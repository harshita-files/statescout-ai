"""Perception throttling (M2-P3).

Track C owns the provider's rate limit, but a limit enforced only on their side
turns into 429s and retries on ours. The orchestrator holds a token bucket and
waits for a token before **every** `PerceptionPort` call, so a burst of states
becomes a slow crawl instead of a wall of errors.

Why a wrapper and not a call in the loop
----------------------------------------
`ThrottledPerception` is a `PerceptionPort` that wraps a `PerceptionPort`. The
loop cannot forget to acquire a token, because there is nowhere left to forget:
the only perception object the nodes ever see is already throttled. A
`limiter.acquire()` line sprinkled before each call is one refactor away from
being dropped from the path nobody tests.

Why a token bucket and not a fixed sleep
----------------------------------------
Perception is bursty — a fan-out state enqueues twenty actions at once, then the
loop spends seconds in the crawler. A bucket lets the idle time bank credit and
spends it on the burst, holding the *average* to the configured rate. A fixed
`60/rate` sleep between calls would pay the full penalty even when the last call
was a minute ago.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from apps.agent.contracts import (
    CaptureBundle,
    ExpectationSet,
    PerceptionPort,
    Role,
    SemanticUIMap,
    Violation,
)

__all__ = ["RateLimiter", "ThrottledPerception"]


class RateLimiter:
    """A monotonic token bucket.

    `clock` and `sleep` are injected so tests can advance time instead of
    spending it: a test that really waits four seconds to prove a four-second
    wait is a test people delete.
    """

    def __init__(
        self,
        per_minute: int,
        *,
        burst: int | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if per_minute < 0:
            raise ValueError("per_minute must be >= 0")

        self.per_minute = per_minute
        #: Default burst is one minute of budget: idle time banks up to a minute
        #: of credit, never more, so a long pause cannot buy an unbounded spike.
        self.capacity = float(burst if burst is not None else max(per_minute, 1))
        self._clock = clock
        self._sleep = sleep
        self._tokens = self.capacity
        self._last = clock()
        #: Cumulative seconds spent waiting. Goes into the M4 run manifest, where
        #: "the crawl took an hour" and "the crawl waited 55 minutes" are very
        #: different findings.
        self.total_wait = 0.0
        self.acquisitions = 0

    @property
    def unlimited(self) -> bool:
        return self.per_minute == 0

    def _refill(self) -> None:
        now = self._clock()
        elapsed = max(now - self._last, 0.0)
        self._last = now
        self._tokens = min(self.capacity, self._tokens + elapsed * self.per_minute / 60.0)

    def acquire(self) -> float:
        """Block until a token is available. Returns the seconds waited."""
        self.acquisitions += 1
        if self.unlimited:
            return 0.0

        self._refill()
        waited = 0.0
        if self._tokens < 1.0:
            waited = (1.0 - self._tokens) * 60.0 / self.per_minute
            self._sleep(waited)
            self.total_wait += waited
            self._refill()
            # Floating-point refill can land a hair under 1.0; the wait was
            # already paid, so spend the token rather than sleep twice.
            self._tokens = max(self._tokens, 1.0)

        self._tokens -= 1.0
        return waited


class ThrottledPerception:
    """A `PerceptionPort` that spends a token before delegating.

    Every method is throttled, including `audit` and `complete_text`: the
    contract makes this the single door to a model, and which methods happen to
    call one today is Track C's business, not something the loop should encode.
    """

    def __init__(self, inner: PerceptionPort, limiter: RateLimiter) -> None:
        self.inner = inner
        self.limiter = limiter

    def analyze(self, bundle: CaptureBundle, role: Role) -> SemanticUIMap:
        self.limiter.acquire()
        return self.inner.analyze(bundle, role)

    def audit(
        self,
        s_current: SemanticUIMap,
        expectations: ExpectationSet,
    ) -> tuple[Violation, ...]:
        self.limiter.acquire()
        return self.inner.audit(s_current, expectations)

    def complete_text(self, prompt: str) -> str:
        self.limiter.acquire()
        return self.inner.complete_text(prompt)
