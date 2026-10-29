"""Track B's experimental model. All accumulated data belongs to the checkpoint.

Masks are application-specific regular expressions, applied to DOM and AX string
values only. No numeric text, role, URL, or attribute is guessed to be volatile.
Unmasked captures always go to perception. Probabilities are empirical frequencies,
not calibrated estimates of security correctness.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from apps.agent.contracts import Action, CaptureBundle, JSONValue
from apps.agent.orchestrator.config import OrchestratorConfig


class NetworkObservations(Protocol):
    """Injected action-window telemetry; producer returns sanitized METHOD /template.

    Drain consumes only calls since the previous drain, including failed actions.
    No URL queries, credentials, headers or bodies may cross this boundary.
    A real Track A implementation is proposed in ADR-002, not silently assumed.
    """

    def drain(self) -> tuple[str, ...]: ...


@dataclass
class DynamicStats:
    transitions: dict[str, dict[str, int]] = field(default_factory=dict)
    transition_probabilities: dict[str, dict[str, float]] = field(default_factory=dict)
    replay_transitions: dict[str, dict[str, int]] = field(default_factory=dict)
    exact_hashes: dict[str, list[str]] = field(default_factory=dict)
    endpoints: dict[str, dict[str, int]] = field(default_factory=dict)
    action_endpoints: dict[str, dict[str, dict[str, int]]] = field(default_factory=dict)
    audits: dict[str, int] = field(default_factory=dict)
    hits: dict[str, int] = field(default_factory=dict)
    recurrence: dict[str, float] = field(default_factory=dict)
    reproducibility: dict[str, float] = field(default_factory=dict)
    confidence: dict[str, float] = field(default_factory=dict)
    readiness: dict[str, int] = field(
        default_factory=lambda: {"ready": 0, "incomplete": 0, "unknown": 0}
    )
    network_available: bool = False
    #: Per-violation `stable` / `flaky` / `insufficient_evidence` (Beta posterior).
    labels: dict[str, str] = field(default_factory=dict)
    #: Volatile regions learned and applied automatically (`auto_mask`).
    masks: list[dict[str, Any]] = field(default_factory=list)
    #: state_id -> {url, title, depth, screenshot}; for graph export.
    nodes: dict[str, dict[str, Any]] = field(default_factory=dict)
    #: pair_key -> action label; for graph export.
    edge_labels: dict[str, str] = field(default_factory=dict)


def pair_key(source: str, action: str) -> str:
    return json.dumps([source, action], separators=(",", ":"))


def identity(bundle: CaptureBundle, config: OrchestratorConfig) -> str:
    def mask(value: JSONValue) -> JSONValue:
        if isinstance(value, str):
            for pattern in config.volatility_patterns:
                value = re.sub(pattern, "<volatile>", value)
            return value
        if isinstance(value, list):
            return [mask(item) for item in value]
        if isinstance(value, dict):
            return {key: mask(item) for key, item in value.items()}
        return value

    material = [config.role, bundle.url, mask(bundle.dom), mask(bundle.ax_tree)]
    return "eq-" + hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()


def record_capture(
    stats: DynamicStats, state_id: str, bundle: CaptureBundle, ready: bool | None = None
) -> None:
    status = "ready" if ready is True else "incomplete" if ready is False else "unknown"
    stats.readiness[status] += 1
    exact = hashlib.sha256(
        json.dumps([bundle.url, bundle.dom, bundle.ax_tree], sort_keys=True).encode()
    ).hexdigest()
    hashes = stats.exact_hashes.setdefault(state_id, [])
    if exact not in hashes:
        hashes.append(exact)


def observe_transition(
    stats: DynamicStats, source: str, action: str, target: str, *, replay: bool
) -> None:
    key = pair_key(source, action)
    counts = stats.transitions.setdefault(key, {})
    counts[target] = counts.get(target, 0) + 1
    total = sum(counts.values())
    stats.transition_probabilities[key] = {target: n / total for target, n in counts.items()}
    if replay:
        counts = stats.replay_transitions.setdefault(key, {})
        counts[target] = counts.get(target, 0) + 1


def probability(stats: DynamicStats, source: str, action: str, target: str) -> float:
    counts = stats.transitions.get(pair_key(source, action), {})
    total = sum(counts.values())
    return counts.get(target, 0) / total if total else 0.0


def priority(stats: DynamicStats, source: str, action: str) -> float:
    """Prefer unknown/uncertain pairs within a BFS depth; never discard a pair."""
    counts = stats.transitions.get(pair_key(source, action), {})
    n = sum(counts.values())
    return 1.0 if not n else 1 / (n + 1) + 1 - max(counts.values()) / n


def record_calls(
    stats: DynamicStats,
    network: NetworkObservations | None,
    *,
    replay: bool,
    click: bool,
    source: str,
    action: str,
) -> None:
    if network is None:
        return
    stats.network_available = True
    calls = network.drain()
    # Reject malformed labels rather than risk persisting raw authenticated URLs.
    safe = [
        call
        for call in calls
        if re.fullmatch(r"(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS) /[A-Za-z0-9_/{}:.-]*", call)
    ]
    per_action = stats.action_endpoints.setdefault(pair_key(source, action), {})
    for endpoint in set(safe):
        for totals in (stats.endpoints, per_action):
            counts = totals.setdefault(
                endpoint,
                {
                    "calls": 0,
                    "actions": 0,
                    "clicks": 0,
                    "replay_calls": 0,
                    "replay_clicks": 0,
                },
            )
            n = safe.count(endpoint)
            counts["calls"] += n
            counts["actions"] += 1
            counts["clicks"] += int(click)
            counts["replay_calls"] += n if replay else 0
            counts["replay_clicks"] += int(replay and click)


def replay_target_allowed(
    stats: DynamicStats,
    source: str,
    step_id: str,
    landed: str,
    action: Action,
    available: tuple[Action, ...],
    seen: set[str],
    minimum: float,
) -> bool:
    """A learned alternate may be used only with its own identity and live control.

    Caller must pass statistics from BEFORE this replay, and check the landed
    visited pair before claiming it. This cannot turn a first-time surprise into
    evidence that replay was safe.
    """
    return (
        landed in seen
        and probability(stats, source, step_id, landed) >= minimum
        and any(item == action for item in available)
    )
