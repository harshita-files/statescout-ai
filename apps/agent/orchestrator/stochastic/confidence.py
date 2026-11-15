"""Observation confidence for a violation element, from repeated observations.

Model: `p` = P(the violating element is present | state class). With a
`Beta(alpha0, beta0)` prior (default uniform) and `k` of `n` observations showing
the element, the posterior is `Beta(alpha0 + k, beta0 + n - k)`. We report its
mean and a one-sided lower credible bound, then label the finding.

Labels (defaults, all overridable):

* `insufficient_evidence` -- fewer than `min_observations` (5) observations.
  Nothing else is claimed, however unanimous the few samples are.
* `stable` -- enough observations and the lower credible bound at
  `credible_level` (0.95, i.e. the 5% quantile) is at least
  `stable_lower_bound` (0.6). Five unanimous sightings just clear this bar
  (0.05^(1/6) ~= 0.607); four never reach it.
* `flaky` -- enough observations but the element is not reliably present
  (including reliably *absent*, which is a rare/transient sighting).

Stdlib only: the Beta CDF is the regularised incomplete beta function by a
continued fraction, and the quantile is found by bisection. Deterministic.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

__all__ = [
    "ConfidenceLabel",
    "ObservationConfidence",
    "beta_cdf",
    "beta_ppf",
    "observation_confidence",
]

ConfidenceLabel = Literal["stable", "flaky", "insufficient_evidence"]

_MAX_ITER = 300
_EPS = 3e-14
_TINY = 1e-300


@dataclass(frozen=True, slots=True)
class ObservationConfidence:
    n_present: int
    n_observations: int
    #: Posterior mean of P(present).
    mean: float
    #: One-sided lower credible bound of P(present) at the requested level.
    lower_bound: float
    label: ConfidenceLabel


def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta (modified Lentz)."""
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > _TINY else _TINY)
    h = d
    for m in range(1, _MAX_ITER + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > _TINY else _TINY)
        c = 1.0 + aa / c
        c = c if abs(c) > _TINY else _TINY
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > _TINY else _TINY)
        c = 1.0 + aa / c
        c = c if abs(c) > _TINY else _TINY
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < _EPS:
            break
    return h


def beta_cdf(x: float, a: float, b: float) -> float:
    """Regularised incomplete beta `I_x(a, b)`, the CDF of `Beta(a, b)`."""
    if a <= 0 or b <= 0:
        raise ValueError("beta parameters must be positive")
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    ln_front = (
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x)
    )
    front = math.exp(ln_front)
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def beta_ppf(p: float, a: float, b: float) -> float:
    """Quantile function of `Beta(a, b)` by bisection on `beta_cdf`."""
    if not 0.0 <= p <= 1.0:
        raise ValueError("p must be in [0, 1]")
    if a <= 0 or b <= 0:
        raise ValueError("beta parameters must be positive")
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if beta_cdf(mid, a, b) < p:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-15:
            break
    return (lo + hi) / 2.0


def observation_confidence(
    n_present: int,
    n_observations: int,
    *,
    prior_alpha: float = 1.0,
    prior_beta: float = 1.0,
    credible_level: float = 0.95,
    min_observations: int = 5,
    stable_lower_bound: float = 0.6,
) -> ObservationConfidence:
    """Posterior mean, lower credible bound and label for `n_present / n_observations`."""
    if n_observations < 0 or n_present < 0 or n_present > n_observations:
        raise ValueError("need 0 <= n_present <= n_observations")
    if prior_alpha <= 0 or prior_beta <= 0:
        raise ValueError("prior parameters must be positive")
    if not 0.0 < credible_level < 1.0:
        raise ValueError("credible_level must be in (0, 1)")
    if min_observations < 0:
        raise ValueError("min_observations must be >= 0")
    if not 0.0 <= stable_lower_bound <= 1.0:
        raise ValueError("stable_lower_bound must be in [0, 1]")

    alpha = prior_alpha + n_present
    beta = prior_beta + (n_observations - n_present)
    mean = alpha / (alpha + beta)
    lower = min(beta_ppf(1.0 - credible_level, alpha, beta), mean)

    label: ConfidenceLabel
    if n_observations < min_observations:
        label = "insufficient_evidence"
    elif lower >= stable_lower_bound:
        label = "stable"
    else:
        label = "flaky"
    return ObservationConfidence(n_present, n_observations, mean, lower, label)
