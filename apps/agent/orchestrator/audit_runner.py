"""User-facing audit entry point: explore, then shape the result as an `AuditReport`."""

from __future__ import annotations

import contextlib
import hashlib
import re
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import Any, Literal

from apps.agent.audit_models import AuditConfig, AuditReport, BlockedNote, Finding, Rule
from apps.agent.contracts import (
    CaptureBundle,
    ExpectationSet,
    Role,
    SemanticUIMap,
    StateEdge,
    StateNode,
    Violation,
)
from apps.agent.negation.checks import check_rules, visible_text
from apps.agent.orchestrator.config import OrchestratorConfig
from apps.agent.orchestrator.deps import Ports
from apps.agent.orchestrator.dynamic import DynamicStats, observe_transition, pair_key
from apps.agent.orchestrator.export import export_graph
from apps.agent.orchestrator.graph_runner import explore
from apps.agent.orchestrator.probes import (
    distinct_targets,
    resample,
    resample_violations,
)
from apps.agent.orchestrator.runlog import Logger
from apps.agent.orchestrator.state import ExplorationResult

__all__ = ["run_audit"]

Progress = Callable[[dict[str, Any]], None]
Stop = Callable[[], bool]


#: Most page reloads the resample phase may spend, whatever `resamples` says.
RESAMPLE_CAP = 100


def _close_quietly(crawler: Any) -> None:
    with contextlib.suppress(Exception):  # releasing the browser must never fail a report
        crawler.close()


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

    def should_stop(self) -> bool:
        """True once a stop was requested or the time budget is spent (sticky)."""
        if not (self.stopped or self.timed_out):
            if self._stop is not None and self._stop():
                self.stopped = True
            elif time.monotonic() > self._deadline:
                self.timed_out = True
        return self.stopped or self.timed_out

    def is_visited(self, state_id: str, action_id: str) -> bool:
        # Fallback only: the loop itself ends on `should_stop` before queued pairs drain.
        if self.should_stop():
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


class _Observer:
    """Wraps the perception port and keeps what each state looked like (first sighting).

    `audit` runs right after `analyze` on the same capture and receives the map with
    the final state id, so that is where map and page text are paired up.
    """

    def __init__(self, inner: Any):
        self._inner = inner
        self._bundle: CaptureBundle | None = None
        self.maps: dict[str, SemanticUIMap] = {}
        self.texts: dict[str, str] = {}
        self.markup: dict[str, str] = {}

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def analyze(self, bundle: CaptureBundle, role: Role) -> SemanticUIMap:
        self._bundle = bundle
        return self._inner.analyze(bundle, role)  # type: ignore[no-any-return]

    def audit(self, s_current: SemanticUIMap, expectations: ExpectationSet) -> Any:
        if s_current.state_id not in self.maps:
            self.maps[s_current.state_id] = s_current
            if self._bundle is not None:
                self.texts[s_current.state_id] = (
                    f"{self._bundle.title}\n{visible_text(self._bundle.dom)}"
                )
                self.markup[s_current.state_id] = self._bundle.dom
        return self._inner.audit(s_current, expectations)


def _rule_key(rule: Rule) -> tuple[Any, ...]:
    p = rule.params
    if rule.kind in {"presence", "absence"}:
        return (rule.kind, p.get("subject"), tuple(p.get("roles") or ()))
    return (
        rule.kind,
        p.get("subject"),
        p.get("mode"),
        p.get("forbid_pattern"),
        p.get("require_pattern"),
        p.get("min"),
        p.get("max"),
        p.get("pattern"),
    )


def _drop_duplicate_rules(rules: Sequence[Rule]) -> tuple[list[Rule], list[str]]:
    """Drop generated rules that repeat a user rule's clause (or an earlier generated one)."""
    seen = {_rule_key(r) for r in rules if r.source == "user"}
    kept: list[Rule] = []
    dropped: list[str] = []
    for r in rules:
        if r.source == "user":
            kept.append(r)
            continue
        key = _rule_key(r)
        if key in seen:
            dropped.append(r.rule_id)
        else:
            seen.add(key)
            kept.append(r)
    return kept, dropped


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\d+", "#", text.lower())).strip()


def _evidence_signature(v: Violation) -> str:
    ev = v.evidence
    if ev.selector:
        return _norm(f"{ev.selector}")
    return _norm((ev.text or "").split(" | vs ")[0])


def _group_key(rule_id: str | None, signature: str) -> str:
    return hashlib.sha1(f"{rule_id}|{signature}".encode()).hexdigest()[:12]


def _describe(v: Violation) -> str:
    ev = v.evidence
    parts = [p for p in (ev.text and f"'{ev.text}'", ev.selector and f"[{ev.selector}]") if p]
    return " ".join(parts)


def _finding(
    v: Violation,
    stats: DynamicStats,
    rule_text: dict[str, str],
    smap_url: dict[str, str],
) -> Finding:
    node = stats.nodes.get(v.state_id, {})
    url = node.get("url") or smap_url.get(v.state_id, "")
    label = stats.labels.get(v.violation_id)
    evidence = [e for e in (v.evidence.selector, v.evidence.text) if e]
    if label:
        evidence.append(f"observation: {label}")
    seen = _describe(v)
    rationale = v.rationale
    if seen and v.clause_type == "forbidden_present":
        rationale = f"{rationale} Seen at {url}: {seen}."
    rid = v.expectation_id
    return Finding(
        finding_id=v.violation_id,
        rule_id=rid,
        state_id=v.state_id,
        url=url,
        severity=v.severity,
        title=rule_text.get(rid) or f"{v.clause_type}: {rid}",
        rationale=rationale,
        confidence=stats.confidence.get(v.violation_id, 1.0),
        screenshot=v.evidence.screenshot_path or node.get("screenshot"),
        evidence=tuple(evidence),
        group_key=_group_key(rid, _evidence_signature(v) or v.clause_type),
    )


def _merge_findings(
    violations: Sequence[Violation],
    stats: DynamicStats,
    rules: Sequence[Rule],
    expectations: ExpectationSet,
    smap_url: dict[str, str],
) -> tuple[Finding, ...]:
    """Findings from every source: user rules win over generated ones that hit the same
    element in the same state."""
    rule_text = {
        n.expectation_id: n.source_text
        for n in (*expectations.forbidden, *expectations.required)
        if n.source_text
    }
    rule_text.update({r.rule_id: r.text for r in rules})
    source = {r.rule_id: r.source for r in rules}
    ordered = sorted(
        violations, key=lambda v: source.get(v.expectation_id, "user") != "user"
    )  # stable: user rules first
    out: list[Finding] = []
    claimed: set[tuple[str, str]] = set()
    for v in ordered:
        sig = _evidence_signature(v)
        if sig:
            if (v.state_id, sig) in claimed:
                continue
            claimed.add((v.state_id, sig))
        out.append(_finding(v, stats, rule_text, smap_url))
    return tuple(out)


def _groups(findings: Sequence[Finding]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for f in findings:
        g = groups.setdefault(
            f.group_key,
            {
                "group_key": f.group_key,
                "rule_id": f.rule_id,
                "title": f.title,
                "severity": f.severity,
                "evidence": f.evidence[:2],
                "count": 0,
                "state_ids": [],
            },
        )
        g["count"] += 1
        g["state_ids"].append(f.state_id)
    return sorted(groups.values(), key=lambda g: -g["count"])


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
    observer = _Observer(ports.perception)
    wrapped = Ports(ports.crawler, observer, tap, ports.network)
    rules, dropped = _drop_duplicate_rules(config.rules)
    if dropped:
        expectations = ExpectationSet(
            tuple(n for n in expectations.forbidden if n.expectation_id not in dropped),
            tuple(n for n in expectations.required if n.expectation_id not in dropped),
        )
        config = replace(config, rules=tuple(rules))
    try:
        result: ExplorationResult = explore(
            wrapped,
            config.url,
            expectations,
            orch,
            run_id=audit_id,
            log=log,
            should_stop=tap.should_stop,
            close_crawler=False,
        )
    except Exception as exc:
        _close_quietly(ports.crawler)
        return AuditReport(
            audit_id=audit_id,
            url=config.url,
            status="error",
            rules=config.rules,
            blocked=_blocked(ports.crawler),
            error=f"{type(exc).__name__}: {exc}",
        )

    maps = list(observer.maps.values())
    resampled: list[Violation] = []
    rates: dict[str, float] = {}
    try:
        if config.resamples > 0 and not tap.should_stop():
            observed = resample(
                ports.crawler,
                distinct_targets((m.state_id, m.url) for m in maps),
                config.resamples,
                dynamic_n=config.resamples_dynamic,
                cap=RESAMPLE_CAP,
                should_stop=tap.should_stop,
            )
            resampled, rates = resample_violations(rules, maps, observed)
    finally:
        _close_quietly(ports.crawler)  # explore() left it open for the probes above

    stats = result.dynamic or DynamicStats()
    # Fill graph metadata the dynamic path did not record (flag off).
    for sid, meta in tap.stats.nodes.items():
        stats.nodes.setdefault(sid, meta)
    if not stats.transitions:
        stats.transitions = tap.stats.transitions
        stats.transition_probabilities = tap.stats.transition_probabilities
    for key, label in tap.stats.edge_labels.items():
        stats.edge_labels.setdefault(key, label)

    for vid, rate in rates.items():
        stats.confidence[vid] = rate
        stats.labels[vid] = "stable" if rate >= 1.0 else "flaky"
    checked = check_rules(rules, maps, observer.texts, observer.markup)
    findings = _merge_findings(
        [*result.violations, *checked, *resampled],
        stats,
        rules,
        expectations,
        {m.state_id: m.url for m in maps},
    )
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
        "finding_groups": _groups(findings),
        "deduplicated_rules": dropped,
    }
    degraded = getattr(ports.perception, "degraded_calls", 0)
    if isinstance(degraded, int) and degraded > 0:
        report_stats["perception_degraded"] = degraded  # VLM calls that failed -> DOM-only
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
