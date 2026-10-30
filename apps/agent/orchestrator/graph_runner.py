"""The LangGraph port of the exploration loop (M2-P2).

Same `explore()` signature as `explore.py`, same `ExplorationResult`, same
behaviour — `tests/unit/orchestrator/test_explore.py` runs its entire suite
against both implementations, which is what "test-identical" is allowed to mean.
What this buys over the plain-Python version is durability: the loop's state is a
checkpointed `TypedDict` rather than local variables, so M4-P1 can resume a
crashed run instead of restarting it.

The mapping
===========
`explore.py`'s single `while` loop becomes four nodes and two conditional edges.

==================================== ==========================================
Plain Python                         LangGraph
==================================== ==========================================
`scan()` fingerprint + persist +     `scan` node
enumerate + enqueue
`scan()` analyze + audit             `reason` node — split out so the
                                     conditional edge has something to branch on
`while` head: frontier / max_states  `route` conditional edge off `reason`
pop + `reach()` + `mark_visited` +   `act` node
`crawler.act()`
`persist_edge` + advance to the      `observe` node
next capture
`continue` after a skip              `route_after_act` conditional edge off
                                     `observe`, back to `act`
local variables                      `ExplorationState`, checkpointed every
                                     superstep
==================================== ==========================================

::

    START -> scan -> reason --clean/violated--> act -> observe --progressed--> scan
                       |                                   |
                       |                                   +--skipped--> act
                       +--terminal--> END                  +--terminal--> END

Why `observe` needs its own conditional edge
--------------------------------------------
A skipped action must not reach `scan`. `explore.py` expresses that as
`continue`; here it is an edge back to `act`. Routing a skip through `scan`
instead would append a phantom entry to `order` and re-audit a state that never
changed, which shows up immediately as a parity failure — and would be a real
bug, not a cosmetic one, because `order` is how a cycle is evidenced.

Recursion limit
---------------
LangGraph counts supersteps and defaults to 25, which a real crawl blows through
in the first few states. The limit is derived from `max_states` and set far above
any reachable value: our own termination argument is the real bound, and the
recursion limit is a backstop that should never fire. If it ever does, the bug is
in the termination reasoning, not in the constant.
"""

from __future__ import annotations

import re
import sys
import time
from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace
from typing import Literal, cast

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from apps.agent.contracts import (
    Action,
    CaptureBundle,
    CrawlerError,
    ExpectationSet,
    StateEdge,
    StateNode,
    StateScoutError,
    TerminationReason,
    Violation,
)
from apps.agent.orchestrator.config import OrchestratorConfig
from apps.agent.orchestrator.deps import Ports
from apps.agent.orchestrator.dynamic import (
    DynamicStats,
    identity,
    observe_transition,
    pair_key,
    priority,
    record_calls,
    record_capture,
    replay_target_allowed,
)
from apps.agent.orchestrator.runlog import Logger
from apps.agent.orchestrator.state import (
    ExplorationResult,
    ExplorationState,
    PendingAction,
    SkippedAction,
    initial_state,
)
from apps.agent.orchestrator.stochastic.confidence import observation_confidence
from apps.agent.orchestrator.stochastic.frontier_policy import ucb_priority
from apps.agent.orchestrator.stochastic.insights import (
    suggest_masks,
    transition_model_from_stats,
)

__all__ = ["Route", "build_graph", "explore", "learn_masks", "recursion_limit"]

Route = Literal["clean", "violated", "terminal"]
AfterAct = Literal["progressed", "skipped", "terminal"]

Runner = CompiledStateGraph[ExplorationState, None, ExplorationState, ExplorationState]


def recursion_limit(config: OrchestratorConfig) -> int:
    """A backstop, not a policy. Four supersteps per candidate, a generous
    fan-out allowance per state, and a floor for tiny runs."""
    # Equivalence can collapse arbitrarily many finite actions into one state.
    # No state-based framework budget may truncate that frontier.
    if config.probabilistic_states:
        return sys.maxsize
    return max(100, 40 * config.max_states + 100)


def _terminal_reason(
    state: ExplorationState,
    config: OrchestratorConfig,
    should_stop: Callable[[], bool] | None = None,
) -> TerminationReason | None:
    """The `while` head of `explore.py`, verbatim.

    Order matters and matches the reference: an empty frontier is
    `frontier_exhausted` even when the state cap has been reached, because the
    run genuinely finished rather than being cut short.
    """
    if should_stop is not None and should_stop():
        return "stopped"  # a stop request or deadline ends the run now; no draining
    if not state["frontier"]:
        return "frontier_exhausted"
    if len(state["seen"]) >= config.max_states:
        return "max_states"
    return None


def build_graph(
    ports: Ports,
    policy: ExpectationSet,
    config: OrchestratorConfig,
    checkpointer: BaseCheckpointSaver[str] | None = None,
    log: Logger | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> Runner:
    """Compile the loop. Ports, policy, and config are closed over — never
    imported by the nodes, and never stored in the checkpointed state."""
    emit = (log or Logger.discard()).emit

    def skip(state: ExplorationState, candidate: PendingAction, reason: str) -> list[SkippedAction]:
        emit(
            "act",
            "skipped",
            state_id=candidate.from_state_id,
            action_id=candidate.action.action_id,
            reason=reason,
        )
        return [
            *state["skipped"],
            SkippedAction(candidate.from_state_id, candidate.action.action_id, reason),
        ]

    def fingerprint(bundle: CaptureBundle) -> str:
        return (
            identity(bundle, config)
            if config.probabilistic_states
            else ports.graph.fingerprint(bundle)
        )

    # -- nodes ------------------------------------------------------------

    def scan(state: ExplorationState) -> dict[str, object]:
        """Fingerprint, persist the node, and enqueue what leads out of it."""
        bundle = state["current_bundle"]
        assert bundle is not None  # the seed is opened before the graph runs
        state_id = fingerprint(bundle)
        first_visit = state_id not in state["seen"]

        emit("scan", "scanned", state_id=state_id, depth=state["depth"], first_visit=first_visit)

        update: dict[str, object] = {
            "current_state_id": state_id,
            "order": [*state["order"], state_id],
            "first_visit": first_visit,
        }
        if config.probabilistic_states:
            stats = deepcopy(state["dynamic"]) or DynamicStats()
            record_capture(
                stats, state_id, bundle, getattr(ports.network, "last_capture_ready", None)
            )
            stats.nodes.setdefault(
                state_id,
                {
                    "url": bundle.url,
                    "title": bundle.title,
                    "depth": state["depth"],
                    "screenshot": bundle.screenshot_path,
                },
            )
            update["dynamic"] = stats
        if not first_visit:
            # Everything below is idempotent by state. The revisit is already
            # recorded: `order` grew, and the edge that brought us here was
            # persisted as a back-edge.
            return update

        ports.graph.persist_state(
            StateNode(
                state_id=state_id,
                url=bundle.url,
                role=config.role,
                depth=state["depth"],
                title=bundle.title,
                screenshot_path=bundle.screenshot_path,
            )
        )

        frontier = list(state["frontier"])
        if state["depth"] < config.depth_limit:
            queued = {(item.from_state_id, item.action.action_id) for item in frontier}
            for action in ports.crawler.enumerate_actions(bundle):
                pair = (state_id, action.action_id)
                if pair in queued or ports.graph.is_visited(*pair):
                    continue
                queued.add(pair)
                frontier.append(
                    PendingAction(
                        state_id, action, state["depth"] + 1, tuple(state["current_path"])
                    )
                )

        return {**update, "seen": [*state["seen"], state_id], "frontier": frontier}

    def audit_capture(
        bundle: CaptureBundle,
        state_id: str,
        previous: list[Violation],
        stats: DynamicStats | None,
    ) -> tuple[Violation, ...]:
        ui_map = ports.perception.analyze(bundle, config.role)
        if config.probabilistic_states:
            ui_map = replace(ui_map, state_id=state_id)
        found = ports.perception.audit(ui_map, policy)
        if stats is not None:
            stats.audits[state_id] = stats.audits.get(state_id, 0) + 1
            for violation in found:
                stats.hits[violation.violation_id] = stats.hits.get(violation.violation_id, 0) + 1
            for violation in (*previous, *found):
                recurrence = (stats.hits.get(violation.violation_id, 0) + 1) / (
                    stats.audits[violation.state_id] + 2
                )
                incoming = [
                    counts for counts in stats.transitions.values() if violation.state_id in counts
                ]
                reproducibility = (
                    sum(counts[violation.state_id] for counts in incoming)
                    / sum(sum(counts.values()) for counts in incoming)
                    if incoming
                    else 1.0
                )
                stats.recurrence[violation.violation_id] = recurrence
                stats.reproducibility[violation.violation_id] = reproducibility
                stats.confidence[violation.violation_id] = recurrence * reproducibility
                audits = stats.audits[violation.state_id]
                stats.labels[violation.violation_id] = observation_confidence(
                    min(stats.hits.get(violation.violation_id, 0), audits), audits
                ).label
            existing = {v.violation_id for v in previous}
            found = tuple(v for v in found if v.violation_id not in existing)
        for violation in found:
            ports.graph.persist_violation(violation)
            emit(
                "audit",
                "violation",
                state_id=state_id,
                expectation_id=violation.expectation_id,
                clause_type=violation.clause_type,
                severity=violation.severity,
            )
        return found

    def reason(state: ExplorationState) -> dict[str, object]:
        """Audit raw captures, including equivalent revisits in dynamic mode."""
        if not state["first_visit"] and not config.probabilistic_states:
            return {"verdict": "clean"}
        bundle, state_id = state["current_bundle"], state["current_state_id"]
        assert bundle is not None and state_id is not None
        stats = deepcopy(state["dynamic"])
        found = audit_capture(bundle, state_id, state["violations"], stats)
        return {
            "dynamic": stats,
            "violations": [*state["violations"], *found],
            "verdict": "violated" if found else "clean",
        }

    def act(state: ExplorationState) -> dict[str, object]:
        """Return to the candidate's state, claim the pair, execute the action."""
        frontier = list(state["frontier"])
        stats = deepcopy(state["dynamic"])
        if stats is not None:
            if config.ucb_frontier:
                # Reorder only: BFS depth stays primary, UCB novelty ranks within it.
                model = transition_model_from_stats(stats)
                ordered: list[PendingAction] = []
                for depth in sorted({item.depth for item in frontier}):
                    ordered.extend(
                        ucb_priority([item for item in frontier if item.depth == depth], model)
                    )
                frontier = ordered
            else:
                frontier.sort(
                    key=lambda item: (
                        item.depth,
                        -priority(stats, item.from_state_id, item.action.action_id),
                    )
                )
        candidate = frontier.pop(0)
        base: dict[str, object] = {"frontier": frontier, "pending": candidate, "acted": False}

        replay_violations = list(state["violations"])
        if stats is not None:
            base["dynamic"] = stats
            base["violations"] = replay_violations

        def audit_replay(bundle: CaptureBundle) -> None:
            replay_id = fingerprint(bundle)
            if stats is not None:
                record_capture(
                    stats, replay_id, bundle, getattr(ports.network, "last_capture_ready", None)
                )
                if replay_id in state["seen"]:
                    replay_violations.extend(
                        audit_capture(bundle, replay_id, replay_violations, stats)
                    )

        if ports.graph.is_visited(candidate.from_state_id, candidate.action.action_id):
            return {**base, "skipped": skip(state, candidate, "pair already visited")}

        # -- get back to where the action is valid ------------------------
        landed_at = state["current_state_id"]
        path = state["current_path"]
        replays = state["replays"]
        replay_steps = state["replay_steps"]

        if landed_at != candidate.from_state_id and not is_direct(candidate.action):
            if not candidate.replayable:
                return {
                    **base,
                    "skipped": skip(
                        state,
                        candidate,
                        "unreplayable path: it contains a side-effecting action",
                    ),
                }
            try:
                # An absolute navigate step replaces the seed load: start from the last one.
                start = max((i for i, st in enumerate(candidate.path) if is_direct(st)), default=-1)
                bundle: CaptureBundle | None = None
                if start < 0:
                    bundle = ports.crawler.open(state["seed_url"])
                    if stats is not None:
                        if ports.network is not None:
                            ports.network.drain()  # seed traffic is not caused by a click
                        audit_replay(bundle)
                for step in candidate.path[max(start, 0) :]:
                    # No source when the replay began at a direct navigate (no prior page).
                    source = fingerprint(bundle) if bundle is not None else None
                    if stats is not None and ports.network is not None:
                        ports.network.drain()  # discard traffic outside the action window
                    try:
                        bundle = ports.crawler.act(step)
                    finally:
                        if stats is not None and source is not None:
                            record_calls(
                                stats,
                                ports.network,
                                replay=True,
                                click=step.kind == "click",
                                source=source,
                                action=step.action_id,
                            )
                    replay_steps += 1
                    if stats is not None:
                        if source is not None:
                            target = fingerprint(bundle)
                            observe_transition(stats, source, step.action_id, target, replay=True)
                        audit_replay(bundle)
            except StateScoutError as exc:
                return {
                    **base,
                    "replay_steps": replay_steps,
                    **({"current_state_id": None} if stats is not None else {}),
                    "skipped": skip(state, candidate, f"replay failed: {exc}"),
                }

            assert bundle is not None  # opened above, or set by the first replayed step
            replays += 1
            landed_at = fingerprint(bundle)
            path = candidate.path
            if (
                landed_at != candidate.from_state_id
                and stats is not None
                and state["dynamic"] is not None
                and candidate.path
                and source is not None
                and replay_target_allowed(
                    state["dynamic"],
                    source,
                    candidate.path[-1].action_id,
                    landed_at,
                    candidate.action,
                    ports.crawler.enumerate_actions(bundle),
                    set(state["seen"]),
                    config.replay_min_probability,
                )
            ):
                candidate = replace(candidate, from_state_id=landed_at)
                base["pending"] = candidate
                emit(
                    "replay", "retargeted", state_id=landed_at, action_id=candidate.action.action_id
                )
            if landed_at != candidate.from_state_id:
                # The same path led somewhere else: the app is non-deterministic
                # or a fingerprint is unstable. Acting here would attribute the
                # edge to the wrong state.
                return {
                    **base,
                    "replays": replays,
                    "replay_steps": replay_steps,
                    "current_state_id": landed_at,
                    "current_path": path,
                    "skipped": skip(
                        state,
                        candidate,
                        f"replay diverged: expected {candidate.from_state_id}, got {landed_at}",
                    ),
                }
            emit("replay", "replayed", state_id=landed_at, steps=len(candidate.path))

        base |= {"replays": replays, "replay_steps": replay_steps, "current_state_id": landed_at}

        if ports.graph.is_visited(candidate.from_state_id, candidate.action.action_id):
            return {
                **base,
                "current_path": path,
                "skipped": skip(state, candidate, "pair already visited after replay"),
            }

        # ADR-001 decision 3: claim before executing. A crash between here and
        # the edge in `observe` leaves a claimed pair with no edge, which resume
        # treats as done-but-unrecorded rather than re-firing the action.
        ports.graph.mark_visited(candidate.from_state_id, candidate.action.action_id)
        visited_pairs = state["visited_pairs"] + 1

        if stats is not None and ports.network is not None:
            ports.network.drain()  # auditing time may have produced background polling
        try:
            try:
                next_bundle = ports.crawler.act(candidate.action)
            finally:
                if stats is not None:
                    record_calls(
                        stats,
                        ports.network,
                        replay=False,
                        click=candidate.action.kind == "click",
                        source=candidate.from_state_id,
                        action=candidate.action.action_id,
                    )
        except CrawlerError as exc:
            return {
                **base,
                "visited_pairs": visited_pairs,
                **({"current_state_id": None} if stats is not None else {}),
                "skipped": skip(state, candidate, str(exc)),
            }

        return {
            **base,
            "visited_pairs": visited_pairs,
            "next_bundle": next_bundle,
            "acted": True,
            "current_path": path,
        }

    def observe(state: ExplorationState) -> dict[str, object]:
        """Record the edge and advance to the state the action produced."""
        if not state["acted"]:
            return {"next_bundle": None}

        candidate = state["pending"]
        bundle = state["next_bundle"]
        assert candidate is not None and bundle is not None

        to_state_id = fingerprint(bundle)
        stats = deepcopy(state["dynamic"])
        if stats is not None:
            observe_transition(
                stats,
                candidate.from_state_id,
                candidate.action.action_id,
                to_state_id,
                replay=False,
            )
            stats.edge_labels[pair_key(candidate.from_state_id, candidate.action.action_id)] = (
                candidate.action.label
            )
        ports.graph.persist_edge(
            StateEdge(
                from_state_id=candidate.from_state_id,
                to_state_id=to_state_id,
                action_id=candidate.action.action_id,
                label=candidate.action.label,
                # A cycle closed. Recorded, never pruned.
                is_back_edge=to_state_id in state["seen"],
            )
        )

        return {
            "dynamic": stats,
            "edges": state["edges"] + 1,
            "current_bundle": bundle,
            "next_bundle": None,
            "depth": candidate.depth,
            "current_path": (*candidate.path, candidate.action),
        }

    # -- edges ------------------------------------------------------------

    def route(state: ExplorationState) -> Route:
        if _terminal_reason(state, config, should_stop) is not None:
            return "terminal"
        return "violated" if state["verdict"] == "violated" else "clean"

    def route_after_act(state: ExplorationState) -> AfterAct:
        if state["acted"]:
            return "progressed"
        return "terminal" if _terminal_reason(state, config, should_stop) is not None else "skipped"

    graph: StateGraph[ExplorationState, None, ExplorationState, ExplorationState] = StateGraph(
        ExplorationState
    )
    graph.add_node("scan", scan)
    graph.add_node("reason", reason)
    graph.add_node("act", act)
    graph.add_node("observe", observe)

    graph.add_edge(START, "scan")
    graph.add_edge("scan", "reason")
    # Mapped explicitly. A computed edge name is a runtime failure that compiles.
    graph.add_conditional_edges(
        "reason", route, {"clean": "act", "violated": "act", "terminal": END}
    )
    graph.add_edge("act", "observe")
    graph.add_conditional_edges(
        "observe", route_after_act, {"progressed": "scan", "skipped": "act", "terminal": END}
    )

    return graph.compile(checkpointer=checkpointer or InMemorySaver())


#: Numbers as displayed to users: $1,234.56, -1.2%, 12:04:33, 42.
_NUMERIC_MASK = r"[-+]?\$?\d[\d,]*(?:[.:]\d+)*%?"


def is_direct(action: Action) -> bool:
    """A navigate to an absolute URL is valid from anywhere: no replay needed to act."""
    return action.kind == "navigate" and action.target.startswith(("http://", "https://"))


#: Transient styling state that live pages toggle per tick (flash on update, up/down by sign).
#: Matched only inside tags: the lookahead refuses text between tags.
_TRANSIENT_MASKS = (
    r'\s?class="(?:flash|highlight|pulse|blink|updated|changed)[\w-]*"',
    r"\b(?:flash-up|flash-down|up|down|gain|loss|positive|negative)\b(?=[^<>]*>)",
)


def learn_masks(
    ports: Ports,
    seed_url: str,
    seed_bundle: CaptureBundle,
    config: OrchestratorConfig,
    stats: DynamicStats,
    log: Logger,
) -> OrchestratorConfig:
    """Re-capture the seed, learn volatile regions, return a config that masks them.

    Done once, before the first state id is minted: changing identity mid-run would
    orphan visited `(state_id, action_id)` pairs. Learned regions are recorded in
    `stats.masks`. Failures to re-open degrade to fewer samples, never to an error.
    """
    captures = [(seed_bundle.dom, seed_bundle.ax_tree)]
    for _ in range(max(config.auto_mask_samples, 0) - 1):
        try:
            again = ports.crawler.open(seed_url)
        except StateScoutError:
            break
        captures.append((again.dom, again.ax_tree))
    if ports.network is not None:
        ports.network.drain()  # re-captures are not caused by a click
    if len(captures) < 2:
        return config
    known = set(config.volatility_patterns)
    learned: list[str] = []
    for suggestion in suggest_masks(captures):
        if suggestion.pattern in known:
            continue
        try:
            re.compile(suggestion.pattern)
        except re.error:
            continue
        known.add(suggestion.pattern)
        learned.append(suggestion.pattern)
        stats.masks.append(
            {
                "path": suggestion.path,
                "pattern": suggestion.pattern[:120],
                "change_rate": suggestion.change_rate,
                "samples": len(suggestion.samples),
            }
        )
    for pattern in _TRANSIENT_MASKS:
        if pattern not in known:
            known.add(pattern)
            learned.append(pattern)
            stats.masks.append(
                {"path": "*", "pattern": pattern, "change_rate": 1.0, "samples": len(captures)}
            )
    candidate = config.model_copy(
        update={"volatility_patterns": (*config.volatility_patterns, *learned)}
    )
    # Free-text numbers (prices, %, clocks, counters) churn on live pages, and a few quick
    # samples can land between ticks, so this is applied unconditionally under auto_mask.
    if _NUMERIC_MASK not in known:
        learned.append(_NUMERIC_MASK)
        stats.masks.append(
            {"path": "*", "pattern": _NUMERIC_MASK, "change_rate": 1.0, "samples": len(captures)}
        )
        candidate = config.model_copy(
            update={"volatility_patterns": (*config.volatility_patterns, *learned)}
        )
    log.emit("startup", "masks_learned", count=len(learned), captures=len(captures))
    return candidate if learned else config


def explore(
    ports: Ports,
    seed_url: str,
    policy: ExpectationSet,
    config: OrchestratorConfig,
    *,
    run_id: str | None = None,
    log: Logger | None = None,
    checkpointer: BaseCheckpointSaver[str] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> ExplorationResult:
    """Crawl breadth-first from `seed_url`, auditing every state once.

    Signature-compatible with `explore.explore`, plus an optional `checkpointer`
    — the whole point of the port. Never raises for an application-level failure:
    a dead link, a stale control, or an unreplayable path is a recorded skip. The
    only error termination is a seed that cannot be opened.
    """
    run_id = run_id or config.new_run_id()
    log = log or Logger.discard(run_id)
    started = time.perf_counter()

    def elapsed() -> float:
        return round((time.perf_counter() - started) * 1000, 3)

    log.emit("startup", "started", seed=seed_url, role=config.role)

    try:
        seed_bundle: CaptureBundle = ports.crawler.open(seed_url)
    except StateScoutError as exc:
        log.emit("startup", "failed", reason=str(exc))
        ports.crawler.close()
        return ExplorationResult(
            run_id=run_id,
            seed_url=seed_url,
            role=config.role,
            termination_reason="error",
            duration_ms=elapsed(),
        )

    try:
        dynamic = (
            DynamicStats(network_available=ports.network is not None)
            if config.probabilistic_states
            else None
        )
        if dynamic is not None and config.auto_mask:
            config = learn_masks(ports, seed_url, seed_bundle, config, dynamic, log)
        runner = build_graph(ports, policy, config, checkpointer, log, should_stop)
        start_state = initial_state(run_id, seed_url, role=config.role)
        start_state["current_bundle"] = seed_bundle
        if dynamic is not None:
            start_state["dynamic"] = dynamic
            if ports.network is not None:
                ports.network.drain()

        # `invoke` is typed as returning the output schema loosely; the compiled
        # graph is parameterised on ExplorationState, so this cast is a formality.
        final = cast(
            "ExplorationState",
            runner.invoke(
                start_state,
                config={
                    "configurable": {"thread_id": run_id},
                    "recursion_limit": recursion_limit(config),
                },
            ),
        )
    finally:
        ports.crawler.close()

    reason = _terminal_reason(final, config, should_stop) or "frontier_exhausted"
    log.emit(
        "shutdown",
        "finished",
        reason=reason,
        states=len(final["seen"]),
        edges=final["edges"],
        pairs=final["visited_pairs"],
        skipped=len(final["skipped"]),
        replays=final["replays"],
        replay_steps=final["replay_steps"],
    )

    return ExplorationResult(
        run_id=run_id,
        seed_url=seed_url,
        role=config.role,
        termination_reason=reason,
        order=tuple(final["order"]),
        states=len(final["seen"]),
        edges=final["edges"],
        visited_pairs=final["visited_pairs"],
        replays=final["replays"],
        replay_steps=final["replay_steps"],
        violations=tuple(final["violations"]),
        skipped=tuple(final["skipped"]),
        duration_ms=elapsed(),
        dynamic=final["dynamic"],
    )
