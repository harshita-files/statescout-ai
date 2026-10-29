"""User-facing audit entry point: explore, then shape the result as an `AuditReport`."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import Any, Literal

from apps.agent.audit_models import AuditConfig, AuditReport, BlockedNote, Finding
from apps.agent.contracts import (
    ExpectationSet,
    StateEdge,
    StateNode,
    Violation,
)
from apps.agent.orchestrator.config import OrchestratorConfig
from apps.agent.orchestrator.deps import Ports
from apps.agent.orchestrator.dynamic import DynamicStats, observe_transition, pair_key
from apps.agent.orchestrator.export import export_graph
from apps.agent.orchestrator.graph_runner import explore
from apps.agent.orchestrator.runlog import Logger
from apps.agent.orchestrator.state import ExplorationResult

__all__ = ["run_audit"]

Progress = Callable[[dict[str, Any]], None]
Stop = Callable[[], bool]


class _Tap:
    """Wraps the graph port: progress events, stop/deadline, and a record of the graph.

    Stopping makes `is_visited` answer True, so every queued pair is skipped without
    touching the crawler and the loop drains to a normal, partial result.
    """

    def __init__(self, inner: Any, stop: Stop | None, deadline: float, progress: Progress | None):
        self._inner = inner
        self._stop = stop
        self._deadline = deadline
        self._progress = progress
        self.stopped = False
        self.timed_out = False
        self.stats = DynamicStats()
        self.counts = {"states": 0, "edges": 0, "violations": 0}

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def _emit(self, phase: str, **fields: Any) -> None:
        if self._progress is not None:
            self._progress({"phase": phase, **self.counts, **fields})

    def is_visited(self, state_id: str, action_id: str) -> bool:
        if not (self.stopped or self.timed_out):
            if self._stop is not None and self._stop():
                self.stopped = True
            elif time.monotonic() > self._deadline:
                self.timed_out = True
        if self.stopped or self.timed_out:
            return True
        return bool(self._inner.is_visited(state_id, action_id))

    def persist_state(self, state: StateNode) -> None:
        self._inner.persist_state(state)
        self.counts["states"] += 1
        self.stats.nodes[state.state_id] = {
            "url": state.url,
            "title": state.title,
            "depth": state.depth,
            "screenshot": state.screenshot_path,
        }
        self._emit("state", state_id=state.state_id, url=state.url)

    def persist_edge(self, edge: StateEdge) -> None:
        self._inner.persist_edge(edge)
        self.counts["edges"] += 1
        observe_transition(
            self.stats, edge.from_state_id, edge.action_id, edge.to_state_id, replay=False
        )
        self.stats.edge_labels[pair_key(edge.from_state_id, edge.action_id)] = edge.label
        self._emit("edge", source=edge.from_state_id, target=edge.to_state_id)

    def persist_violation(self, violation: Violation) -> None:
        self._inner.persist_violation(violation)
        self.counts["violations"] += 1
        self._emit("violation", violation_id=violation.violation_id)


def _blocked(crawler: Any) -> tuple[BlockedNote, ...]:
    getter = getattr(crawler, "blocked_notes", None)
    if getter is None:
        return ()
    out: list[BlockedNote] = []
    for note in getter() or ():
        if isinstance(note, BlockedNote):
            out.append(note)
        elif isinstance(note, dict):
            out.append(BlockedNote(str(note.get("url", "")), str(note.get("reason", ""))))
        else:
            out.append(BlockedNote(str(getattr(note, "url", "")), str(getattr(note, "reason", ""))))
    return tuple(dict.fromkeys(out))


def _finding(v: Violation, stats: DynamicStats) -> Finding:
    node = stats.nodes.get(v.state_id, {})
    label = stats.labels.get(v.violation_id)
    evidence = [e for e in (v.evidence.selector, v.evidence.text) if e]
    if label:
        evidence.append(f"observation: {label}")
    return Finding(
        finding_id=v.violation_id,
        rule_id=v.expectation_id,
        state_id=v.state_id,
        url=node.get("url", ""),
        severity=v.severity,
        title=f"{v.clause_type}: {v.expectation_id}",
        rationale=v.rationale,
        confidence=stats.confidence.get(v.violation_id, 1.0),
        screenshot=v.evidence.screenshot_path or node.get("screenshot"),
        evidence=tuple(evidence),
    )


def run_audit(
    config: AuditConfig,
    ports: Ports,
    expectations: ExpectationSet,
    log: Logger | None = None,
    *,
    stop: Stop | None = None,
    progress: Progress | None = None,
) -> AuditReport:
    """Run one audit. Never raises for application-level failures: they become
    `status="error"` with a message."""
    audit_id = f"audit-{uuid.uuid4().hex[:12]}"
    log = log or Logger.discard(audit_id)
    orch = OrchestratorConfig(  # type: ignore[call-arg]
        _env_file=None,
        probabilistic_states=config.probabilistic,
        auto_mask=config.probabilistic,
        volatility_patterns=config.volatility_patterns,
        depth_limit=config.depth_limit,
        max_states=config.max_states,
        perception_rate_per_min=0,
    )
    tap = _Tap(ports.graph, stop, time.monotonic() + config.max_seconds, progress)
    wrapped = Ports(ports.crawler, ports.perception, tap, ports.network)
    try:
        result: ExplorationResult = explore(
            wrapped, config.url, expectations, orch, run_id=audit_id, log=log
        )
    except Exception as exc:
        return AuditReport(
            audit_id=audit_id,
            url=config.url,
            status="error",
            rules=config.rules,
            blocked=_blocked(ports.crawler),
            error=f"{type(exc).__name__}: {exc}",
        )

    stats = result.dynamic or DynamicStats()
    # Fill graph metadata the dynamic path did not record (flag off).
    for sid, meta in tap.stats.nodes.items():
        stats.nodes.setdefault(sid, meta)
    if not stats.transitions:
        stats.transitions = tap.stats.transitions
        stats.transition_probabilities = tap.stats.transition_probabilities
    for key, label in tap.stats.edge_labels.items():
        stats.edge_labels.setdefault(key, label)

    findings = tuple(_finding(v, stats) for v in result.violations)
    status: Literal["done", "error", "stopped"] = (
        "error"
        if result.termination_reason == "error"
        else "stopped"
        if tap.stopped or tap.timed_out
        else "done"
    )
    graph = export_graph(result, stats)
    report_stats: dict[str, Any] = {
        **graph["stats"],
        "confidence_labels": dict(stats.labels),
        "timed_out": tap.timed_out,
        "duration_ms": result.duration_ms,
    }
    if progress is not None:
        progress({"phase": "done", "status": status, **tap.counts})
    return AuditReport(
        audit_id=audit_id,
        url=config.url,
        status=status,
        rules=config.rules,
        findings=findings,
        blocked=_blocked(ports.crawler),
        graph={"nodes": graph["nodes"], "edges": graph["edges"]},
        stats=report_stats,
        error="seed could not be opened" if result.termination_reason == "error" else None,
    )
