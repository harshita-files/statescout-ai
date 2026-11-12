"""Additively smoothed transition model over state classes.

Keyed by ``(state_class, action_id)``; holds counts over successor state classes.
``posterior`` is the mean of a symmetric Dirichlet(alpha) over the ``K`` seen classes
plus one pseudo-class, :data:`UNSEEN`, standing for "some class not seen so far".
The bucket as a whole has mass ``alpha / (N + alpha * (K + 1))``.

This is a heuristic, not a coherent Bayesian model: ``K`` grows with the data, so the
prior depends on what was observed, and :meth:`prob` returns the WHOLE bucket mass for
any one unseen class, so the values for several different unseen classes do not sum to
one.  Treat it as an upper bound on "this unseen class", used to avoid declaring a rare
outcome impossible, and do not describe it as a Dirichlet posterior in write-ups.

This module only estimates probabilities.  It never decides termination.
"""

from __future__ import annotations

import math
from typing import Any

UNSEEN = "__unseen__"

_DEFAULT_ALPHA = 1.0


class TransitionModel:
    """Counts of ``(state_class, action_id) -> successor class`` with Dirichlet smoothing."""

    __slots__ = ("_alpha", "_counts")

    def __init__(self, alpha: float = _DEFAULT_ALPHA) -> None:
        if not alpha > 0.0 or math.isinf(alpha):
            raise ValueError("alpha must be a finite positive number")
        self._alpha = alpha
        self._counts: dict[str, dict[str, dict[str, int]]] = {}

    @property
    def alpha(self) -> float:
        return self._alpha

    def observe(self, state: str, action: str, next_state: str) -> None:
        """Record one observed transition."""
        row = self._counts.setdefault(state, {}).setdefault(action, {})
        row[next_state] = row.get(next_state, 0) + 1

    def _row(self, state: str, action: str) -> dict[str, int]:
        return self._counts.get(state, {}).get(action, {})

    def total_observations(self, state: str, action: str) -> int:
        return sum(self._row(state, action).values())

    def _denominator(self, row: dict[str, int]) -> float:
        return sum(row.values()) + self._alpha * (len(row) + 1)

    def posterior(self, state: str, action: str) -> dict[str, float]:
        """Posterior mean over seen classes plus the aggregate ``UNSEEN`` bucket.

        Sums to 1.  With no observations the result is ``{UNSEEN: 1.0}``.
        """
        row = self._row(state, action)
        denom = self._denominator(row)
        out = {k: (row[k] + self._alpha) / denom for k in sorted(row)}
        out[UNSEEN] = self._alpha / denom
        return out

    def prob(self, state: str, action: str, next_state: str) -> float:
        """Posterior probability of landing in ``next_state``.

        A class never seen for this pair gets the Dirichlet prior mass.
        """
        row = self._row(state, action)
        return (row.get(next_state, 0) + self._alpha) / self._denominator(row)

    def entropy(self, state: str, action: str) -> float:
        """Shannon entropy (bits) of the posterior; 0.0 when nothing was observed.

        Callers that need to tell "certain" from "no data" should check
        :meth:`total_observations`.
        """
        if not self._row(state, action):
            return 0.0
        return -sum(p * math.log2(p) for p in self.posterior(state, action).values() if p > 0.0)

    def accepts_replay(self, state: str, action: str, landed: str, min_prob: float) -> bool:
        """True if ``landed`` has posterior mass >= ``min_prob``.

        With no observations for the pair there is no evidence to reject on, so any
        landing is accepted.
        """
        if not 0.0 <= min_prob <= 1.0:
            raise ValueError("min_prob must be in [0, 1]")
        if not self._row(state, action):
            return True
        return self.prob(state, action, landed) >= min_prob

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable snapshot."""
        return {
            "alpha": self._alpha,
            "counts": {
                s: {a: dict(sorted(r.items())) for a, r in sorted(acts.items())}
                for s, acts in sorted(self._counts.items())
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TransitionModel:
        """Rebuild from :meth:`to_dict` output; raises ``ValueError`` if malformed."""
        try:
            model = cls(alpha=float(data["alpha"]))
            counts = data["counts"]
            for s, acts in counts.items():
                for a, row in acts.items():
                    for nxt, n in row.items():
                        if not isinstance(n, int) or isinstance(n, bool) or n < 0:
                            raise ValueError(f"invalid count for {s!r}/{a!r}/{nxt!r}")
                        if n:
                            model._counts.setdefault(s, {}).setdefault(a, {})[nxt] = n
        except (KeyError, TypeError, AttributeError) as exc:
            raise ValueError(f"malformed TransitionModel snapshot: {exc!r}") from exc
        return model
