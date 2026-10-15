"""Beta-posterior confidence for 'violation element present in this state class'."""

from __future__ import annotations

import math

import pytest

from apps.agent.orchestrator.stochastic.confidence import (
    ObservationConfidence,
    beta_cdf,
    beta_ppf,
    observation_confidence,
)


def test_beta_cdf_known_values() -> None:
    assert beta_cdf(0.0, 2, 3) == 0.0
    assert beta_cdf(1.0, 2, 3) == 1.0
    assert beta_cdf(0.3, 1, 1) == pytest.approx(0.3)
    assert beta_cdf(0.5, 2, 2) == pytest.approx(0.5)
    assert beta_cdf(0.4, 3, 1) == pytest.approx(0.4**3)


def test_beta_ppf_known_values() -> None:
    assert beta_ppf(0.05, 6, 1) == pytest.approx(0.05 ** (1 / 6), abs=1e-9)
    assert beta_ppf(0.5, 2, 2) == pytest.approx(0.5, abs=1e-9)
    assert beta_ppf(0.25, 1, 1) == pytest.approx(0.25, abs=1e-9)


def test_beta_ppf_inverts_cdf() -> None:
    for a, b in [(0.5, 0.5), (2, 7), (30, 4), (1, 50)]:
        for p in (0.01, 0.2, 0.5, 0.95):
            assert beta_cdf(beta_ppf(p, a, b), a, b) == pytest.approx(p, abs=1e-8)


def test_beta_rejects_bad_parameters() -> None:
    with pytest.raises(ValueError):
        beta_cdf(0.5, 0, 1)
    with pytest.raises(ValueError):
        beta_ppf(1.5, 1, 1)


def test_posterior_mean_with_uniform_prior() -> None:
    r = observation_confidence(3, 4)
    assert r.mean == pytest.approx(4 / 6)
    assert (r.n_present, r.n_observations) == (3, 4)


def test_no_observations_is_insufficient_with_prior_mean() -> None:
    r = observation_confidence(0, 0)
    assert r.mean == pytest.approx(0.5)
    assert r.label == "insufficient_evidence"
    assert 0.0 <= r.lower_bound < r.mean


def test_few_observations_are_insufficient_even_if_unanimous() -> None:
    assert observation_confidence(4, 4).label == "insufficient_evidence"


def test_unanimous_with_enough_observations_is_stable() -> None:
    r = observation_confidence(5, 5)
    assert r.lower_bound == pytest.approx(0.05 ** (1 / 6), abs=1e-9)
    assert r.label == "stable"


def test_mixed_observations_are_flaky() -> None:
    assert observation_confidence(7, 10).label == "flaky"
    assert observation_confidence(0, 10).label == "flaky"


def test_more_evidence_tightens_the_bound() -> None:
    assert observation_confidence(50, 50).lower_bound > observation_confidence(5, 5).lower_bound


def test_lower_bound_never_exceeds_mean() -> None:
    for k, n in [(0, 6), (3, 6), (6, 6), (1, 100)]:
        r = observation_confidence(k, n)
        assert 0.0 <= r.lower_bound <= r.mean <= 1.0


def test_custom_thresholds_and_prior() -> None:
    r = observation_confidence(
        3, 3, prior_alpha=0.5, prior_beta=0.5, min_observations=3, stable_lower_bound=0.3
    )
    assert r.label == "stable"
    assert r.mean == pytest.approx(3.5 / 4)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"n_present": -1, "n_observations": 3},
        {"n_present": 4, "n_observations": 3},
        {"n_present": 1, "n_observations": 3, "prior_alpha": 0},
        {"n_present": 1, "n_observations": 3, "credible_level": 1.0},
        {"n_present": 1, "n_observations": 3, "credible_level": 0.0},
        {"n_present": 1, "n_observations": 3, "min_observations": -1},
        {"n_present": 1, "n_observations": 3, "stable_lower_bound": 1.5},
    ],
)
def test_invalid_inputs_raise(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        observation_confidence(**kwargs)  # type: ignore[arg-type]


def test_result_is_frozen_and_finite() -> None:
    r = observation_confidence(2, 9)
    assert isinstance(r, ObservationConfidence)
    assert math.isfinite(r.mean) and math.isfinite(r.lower_bound)
    with pytest.raises(AttributeError):
        r.mean = 0.0  # type: ignore[misc]
