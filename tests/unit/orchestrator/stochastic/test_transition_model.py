"""Tests for the Dirichlet-smoothed TransitionModel."""

from __future__ import annotations

import json
import math

import pytest

from apps.agent.orchestrator.stochastic.transition_model import UNSEEN, TransitionModel


def test_empty_pair_has_no_observations_and_all_mass_on_unseen() -> None:
    m = TransitionModel()
    assert m.total_observations("s", "a") == 0
    assert m.posterior("s", "a") == {UNSEEN: 1.0}
    assert m.prob("s", "a", "x") == 1.0
    assert m.entropy("s", "a") == 0.0


def test_posterior_is_smoothed_and_sums_to_one() -> None:
    m = TransitionModel(alpha=1.0)
    for _ in range(3):
        m.observe("s", "a", "x")
    m.observe("s", "a", "y")
    post = m.posterior("s", "a")
    # N=4, K=2 seen, +1 unseen bucket -> denominator 4 + 3
    assert post["x"] == pytest.approx(4 / 7)
    assert post["y"] == pytest.approx(2 / 7)
    assert post[UNSEEN] == pytest.approx(1 / 7)
    assert sum(post.values()) == pytest.approx(1.0)
    assert m.total_observations("s", "a") == 4


def test_prob_unseen_class_gets_prior_mass() -> None:
    m = TransitionModel(alpha=0.5)
    m.observe("s", "a", "x")
    # N=1, K=1 -> denom 1 + 0.5*2 = 2
    assert m.prob("s", "a", "x") == pytest.approx(1.5 / 2)
    assert m.prob("s", "a", "never") == pytest.approx(0.5 / 2)


def test_pairs_are_independent() -> None:
    m = TransitionModel()
    m.observe("s", "a", "x")
    assert m.total_observations("s", "b") == 0
    assert m.total_observations("t", "a") == 0


def test_entropy_grows_with_dispersion() -> None:
    det = TransitionModel()
    mixed = TransitionModel()
    for _ in range(50):
        det.observe("s", "a", "x")
    for i in range(50):
        mixed.observe("s", "a", "x" if i % 2 else "y")
    assert mixed.entropy("s", "a") > det.entropy("s", "a")
    assert det.entropy("s", "a") >= 0.0
    post = mixed.posterior("s", "a")
    expected = -sum(p * math.log2(p) for p in post.values() if p > 0)
    assert mixed.entropy("s", "a") == pytest.approx(expected)


def test_accepts_replay_threshold() -> None:
    m = TransitionModel(alpha=1.0)
    for _ in range(9):
        m.observe("s", "a", "x")
    assert m.accepts_replay("s", "a", "x", 0.5)
    # unseen: 1/(9+2) ~ 0.09
    assert not m.accepts_replay("s", "a", "z", 0.5)
    assert m.accepts_replay("s", "a", "z", 0.05)


def test_accepts_replay_without_evidence_accepts() -> None:
    assert TransitionModel().accepts_replay("s", "a", "anything", 0.9)


def test_invalid_parameters_rejected() -> None:
    with pytest.raises(ValueError):
        TransitionModel(alpha=0.0)
    m = TransitionModel()
    with pytest.raises(ValueError):
        m.accepts_replay("s", "a", "x", 1.5)


def test_round_trip_through_json() -> None:
    m = TransitionModel(alpha=0.25)
    m.observe("s", "a", "x")
    m.observe("s", "a", "y")
    m.observe("t", "b", "s")
    restored = TransitionModel.from_dict(json.loads(json.dumps(m.to_dict())))
    assert restored.to_dict() == m.to_dict()
    assert restored.posterior("s", "a") == m.posterior("s", "a")
    restored.observe("s", "a", "x")
    assert m.total_observations("s", "a") == 2  # original untouched


def test_from_dict_rejects_malformed() -> None:
    with pytest.raises(ValueError):
        TransitionModel.from_dict({"alpha": 1.0, "counts": {"s": {"a": {"x": -1}}}})
    with pytest.raises(ValueError):
        TransitionModel.from_dict({"counts": {}})
