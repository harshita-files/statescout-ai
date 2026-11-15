"""Read-only bridge between the run's `DynamicStats` and the stochastic models.

`dynamic.py` stays the single writer of run statistics and the only source of state
identity. Nothing here changes an id, a frontier or a verdict: learned volatility is
only *suggested* for a human to approve into `volatility_patterns`, because ids that
shifted mid-run would orphan already-visited `(state_id, action_id)` pairs.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from apps.agent.orchestrator.dynamic import DynamicStats
from apps.agent.orchestrator.stochastic.confidence import (
    ObservationConfidence,
    observation_confidence,
)
from apps.agent.orchestrator.stochastic.transition_model import TransitionModel
from apps.agent.orchestrator.stochastic.volatility import (
    VolatilityEstimator,
    region_texts,
)

__all__ = [
    "MaskSuggestion",
    "suggest_masks",
    "transition_model_from_stats",
    "violation_confidences",
]

_DIGITS = re.compile(r"\d+")


def transition_model_from_stats(stats: DynamicStats, alpha: float = 1.0) -> TransitionModel:
    """Dirichlet-smoothed view of the empirical transition counts (keeps unseen-target mass)."""
    model = TransitionModel(alpha=alpha)
    for key, counts in stats.transitions.items():
        source, action = json.loads(key)
        for target, n in counts.items():
            for _ in range(n):
                model.observe(source, action, target)
    return model


def violation_confidences(
    stats: DynamicStats, violation_states: Mapping[str, str]
) -> dict[str, ObservationConfidence]:
    """Beta-posterior confidence per violation: hits out of audits of its own state.

    Violations whose state has no audit record are skipped rather than guessed.
    """
    out: dict[str, ObservationConfidence] = {}
    for violation_id, hits in stats.hits.items():
        audits = stats.audits.get(violation_states.get(violation_id, ""))
        if audits is None:
            continue
        out[violation_id] = observation_confidence(hits, audits)
    return out


@dataclass(frozen=True, slots=True)
class MaskSuggestion:
    """A volatile region and a candidate regex for `OrchestratorConfig.volatility_patterns`."""

    path: str
    pattern: str
    samples: tuple[str, ...]
    change_rate: float


_ATTR = re.compile(r"""\b(class|id)\s*=\s*(["'])(.*?)\2""", re.DOTALL)
_ATTR_TOKEN = re.compile(r"^(.*[-_])([A-Za-z0-9]{4,})$")
#: Fewest literal alphanumerics a pattern must keep, so `\d+` or `.` can never be proposed.
_MIN_LITERAL = 3
#: Attribute patterns also pin a fixed-width suffix, so two prefix letters are specific enough.
_MIN_LITERAL_ATTR = 2


def _template(sample: str) -> str:
    return _DIGITS.sub(lambda _: r"\d+", re.escape(sample))


def _literal_chars(pattern: str) -> int:
    return len(re.findall(r"[A-Za-z]", re.sub(r"\\d\+|\[A-Za-z0-9\]\{\d+\}", "", pattern)))


def _usable(pattern: str, raw_doms: Sequence[str], min_literal: int = _MIN_LITERAL) -> bool:
    """A suggestion must be specific and must actually occur in the raw markup.

    `dynamic.identity` applies patterns with `re.sub` to the raw DOM, so a pattern
    built from normalised or multi-element text would silently do nothing.
    """
    if _literal_chars(pattern) < min_literal:
        return False
    regex = re.compile(pattern)
    return any(regex.search(dom) for dom in raw_doms)


def _attribute_suggestions(raw_doms: Sequence[str]) -> list[MaskSuggestion]:
    per_capture: list[set[str]] = []
    for dom in raw_doms:
        tokens: set[str] = set()
        for match in _ATTR.finditer(dom):
            tokens.update(match.group(3).split())
        per_capture.append(tokens)
    groups: dict[tuple[str, int], set[str]] = {}
    for tokens in per_capture:
        for token in tokens:
            seen_in = sum(token in other for other in per_capture)
            found = _ATTR_TOKEN.match(token)
            if seen_in == 1 and found:
                groups.setdefault((found.group(1), len(found.group(2))), set()).add(token)
    out: list[MaskSuggestion] = []
    for (prefix, width), tokens in sorted(groups.items()):
        if len(tokens) < 2:
            continue
        pattern = f"{re.escape(prefix)}[A-Za-z0-9]{{{width}}}"
        if _usable(pattern, raw_doms, _MIN_LITERAL_ATTR):
            out.append(MaskSuggestion("attr:class|id", pattern, tuple(sorted(tokens)), 1.0))
    return out


def suggest_masks(
    captures: Sequence[tuple[str, object]],
    *,
    threshold: float = 0.25,
    max_depth: int = 3,
) -> tuple[MaskSuggestion, ...]:
    """Repeated captures of ONE state in, reviewable mask candidates out.

    Two kinds: text patterns from volatile regions (digit runs become `\\d+`) and
    attribute patterns for per-load random class/id suffixes. Every suggestion is
    checked to be specific (at least three literal letters, two for attribute suffix
    patterns) and to match the raw markup in at least one capture. That does not make
    it safe to apply: a person must still approve each pattern, because a pattern can
    match text that carries meaning. Nothing is applied automatically.
    """
    if len(captures) < 2:
        return ()
    raw_doms = [dom for dom, _ in captures]
    estimator = VolatilityEstimator(threshold=threshold, max_depth=max_depth)
    for dom, ax in captures:
        estimator.observe(dom, ax)
    texts = [region_texts(dom, max_depth, raw=True) for dom in raw_doms]
    # The estimator normalises timestamps away, so also take every region whose RAW
    # text varies: identity() hashes the raw markup and would see that churn.
    varying = {
        path
        for path in {p for per_capture in texts for p in per_capture}
        if len({per_capture[path] for per_capture in texts if path in per_capture}) > 1
    }
    volatile = sorted({p for p in estimator.volatile_paths() if p.startswith("dom:")} | varying)
    suggestions: list[MaskSuggestion] = []
    for path in volatile:
        by_template: dict[str, list[str]] = {}
        for per_capture in texts:
            sample = per_capture.get(path)
            if sample:
                by_template.setdefault(_template(sample), []).append(sample)
        for pattern, samples in sorted(by_template.items()):
            if _usable(pattern, raw_doms):
                suggestions.append(
                    MaskSuggestion(
                        path=path,
                        pattern=pattern,
                        samples=tuple(dict.fromkeys(samples)),
                        change_rate=estimator.change_rate(path),
                    )
                )
    suggestions.extend(_attribute_suggestions(raw_doms))
    return tuple(suggestions)
