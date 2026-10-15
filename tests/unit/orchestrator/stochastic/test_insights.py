"""Read-only bridge from DynamicStats to the stochastic models."""

from __future__ import annotations

import pytest

from apps.agent.orchestrator.dynamic import DynamicStats, observe_transition
from apps.agent.orchestrator.stochastic.insights import (
    MaskSuggestion,
    suggest_masks,
    transition_model_from_stats,
    violation_confidences,
)


def _page(ad: str, counter: int) -> str:
    return (
        "<html><body><nav><a href='/home'>Home</a></nav>"
        f"<div class='ad'>{ad}</div><main><h1>Orders</h1>"
        f"<p>Visitors online: {counter}</p></main></body></html>"
    )


def test_transition_model_is_rebuilt_from_empirical_counts() -> None:
    stats = DynamicStats()
    for target in ["B", "B", "B", "C"]:
        observe_transition(stats, "A", "go", target, replay=False)

    model = transition_model_from_stats(stats)

    assert model.total_observations("A", "go") == 4
    assert model.prob("A", "go", "B") > model.prob("A", "go", "C") > 0
    assert model.entropy("A", "go") > 0


def test_unseen_target_keeps_probability_mass_unlike_the_empirical_estimate() -> None:
    stats = DynamicStats()
    observe_transition(stats, "A", "go", "B", replay=False)

    model = transition_model_from_stats(stats)

    assert model.prob("A", "go", "never-seen") > 0


def test_violation_confidence_uses_audits_of_the_violations_state() -> None:
    stats = DynamicStats(audits={"s1": 10}, hits={"v1": 4, "v2": 10})

    result = violation_confidences(stats, {"v1": "s1", "v2": "s1"})

    assert result["v1"].label == "flaky"
    assert result["v2"].label == "stable"
    assert result["v1"].lower_bound < result["v2"].lower_bound


def test_violation_without_audit_record_is_skipped_not_guessed() -> None:
    stats = DynamicStats(hits={"v1": 3})

    assert violation_confidences(stats, {"v1": "unknown-state"}) == {}


def test_hits_cannot_exceed_audits() -> None:
    stats = DynamicStats(audits={"s1": 2}, hits={"v1": 5})

    with pytest.raises(ValueError):
        violation_confidences(stats, {"v1": "s1"})


def test_suggest_masks_reports_volatile_regions_for_human_approval() -> None:
    captures = [(_page(f"ad-{i}", 100 + i), {"nodes": []}) for i in range(6)]

    suggestions = suggest_masks(captures)

    assert suggestions
    assert all(isinstance(s, MaskSuggestion) for s in suggestions)
    paths = {s.path for s in suggestions}
    assert not any("nav" in p for p in paths)
    assert any("Visitors" in sample for s in suggestions for sample in s.samples)


def test_suggested_patterns_compile_and_match_their_samples() -> None:
    import re

    captures = [(_page("same", 100 + i), {"nodes": []}) for i in range(6)]

    for s in suggest_masks(captures):
        regex = re.compile(s.pattern)
        assert all(regex.search(sample) for sample in s.samples)


def test_stable_pages_produce_no_suggestions() -> None:
    captures = [(_page("same", 7), {"nodes": []}) for _ in range(5)]

    assert suggest_masks(captures) == ()
