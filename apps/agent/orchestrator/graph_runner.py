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

import time
from typing import Literal, cast

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from apps.agent.contracts import (
    CaptureBundle,
    CrawlerError,
    ExpectationSet,
    StateEdge,
    StateNode,
    StateScoutError,
    TerminationReason,
)
from apps.agent.orchestrator.config import OrchestratorConfig
from apps.agent.orchestrator.deps import Ports
from apps.agent.orchestrator.runlog import Logger
from apps.agent.orchestrator.state import (
    ExplorationResult,
    ExplorationState,
    PendingAction,
    SkippedAction,
    initial_state,
)

__all__ = ["Route", "build_graph", "explore", "recursion_limit"]

Route = Literal["clean", "violated", "terminal"]
AfterAct = Literal["progressed", "skipped", "terminal"]

Runner = CompiledStateGraph[ExplorationState, None, ExplorationState, ExplorationState]


def recursion_limit(config: OrchestratorConfig) -> int:
    """A backstop, not a policy. Four supersteps per candidate, a generous
    fan-out allowance per state, and a floor for tiny runs."""
    return max(100, 40 * config.max_states + 100)


def _terminal_reason(
    state: ExplorationState, config: OrchestratorConfig
) -> TerminationReason | None:
    """The `while` head of `explore.py`, verbatim.

    Order matters and matches the reference: an empty frontier is
    `frontier_exhausted` even when the state cap has been reached, because the
    run genuinely finished rather than being cut short.
    """
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

    # -- nodes ------------------------------------------------------------

    def scan(state: ExplorationState) -> dict[str, object]:
        """Fingerprint, persist the node, and enqueue what leads out of it."""
        bundle = state["current_bundle"]
        assert bundle is not None  # the seed is opened before the graph runs
        state_id = ports.graph.fingerprint(bundle)
        first_visit = state_id not in state["seen"]

        emit("scan", "scanned", state_id=state_id, depth=state["depth"], first_visit=first_visit)

        update: dict[str, object] = {
            "current_state_id": state_id,
            "order": [*state["order"], state_id],
            "first_visit": first_visit,
        }
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

    def reason(state: ExplorationState) -> dict[str, object]:
        """Analyze and audit — once per state, not once per visit."""
        if not state["first_visit"]:
            return {"verdict": "clean"}

        bundle = state["current_bundle"]
        assert bundle is not None
        state_id = state["current_state_id"]
        assert state_id is not None

        ui_map = ports.perception.analyze(bundle, config.role)
        found = ports.perception.audit(ui_map, policy)
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

        return {
            "violations": [*state["violations"], *found],
            "verdict": "violated" if found else "clean",
        }

    def act(state: ExplorationState) -> dict[str, object]:
        """Return to the candidate's state, claim the pair, execute the action."""
        frontier = list(state["frontier"])
        candidate = frontier.pop(0)
        base: dict[str, object] = {"frontier": frontier, "pending": candidate, "acted": False}

        # -- get back to where the action is valid ------------------------
        landed_at = state["current_state_id"]
        path = state["current_path"]
        replays = state["replays"]
        replay_steps = state["replay_steps"]

        if landed_at != candidate.from_state_id:
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
                bundle = ports.crawler.open(state["seed_url"])
                for step in candidate.path:
                    bundle = ports.crawler.act(step)
                    replay_steps += 1
            except StateScoutError as exc:
                return {
                    **base,
                    "replay_steps": replay_steps,
                    "skipped": skip(state, candidate, f"replay failed: {exc}"),
                }

            replays += 1
            landed_at = ports.graph.fingerprint(bundle)
            path = candidate.path
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

        # ADR-001 decision 3: claim before executing. A crash between here and
        # the edge in `observe` leaves a claimed pair with no edge, which resume
        # treats as done-but-unrecorded rather than re-firing the action.
        ports.graph.mark_visited(candidate.from_state_id, candidate.action.action_id)
        visited_pairs = state["visited_pairs"] + 1

        try:
            next_bundle = ports.crawler.act(candidate.action)
        except CrawlerError as exc:
            return {
                **base,
                "visited_pairs": visited_pairs,
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

        to_state_id = ports.graph.fingerprint(bundle)
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
            "edges": state["edges"] + 1,
            "current_bundle": bundle,
            "next_bundle": None,
            "depth": candidate.depth,
            "current_path": (*candidate.path, candidate.action),
        }

    # -- edges ------------------------------------------------------------

    def route(state: ExplorationState) -> Route:
        if _terminal_reason(state, config) is not None:
            return "terminal"
        return "violated" if state["verdict"] == "violated" else "clean"

    def route_after_act(state: ExplorationState) -> AfterAct:
        if state["acted"]:
            return "progressed"
        return "terminal" if _terminal_reason(state, config) is not None else "skipped"

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


def explore(
    ports: Ports,
    seed_url: str,
    policy: ExpectationSet,
    config: OrchestratorConfig,
    *,
    run_id: str | None = None,
    log: Logger | None = None,
    checkpointer: BaseCheckpointSaver[str] | None = None,
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

    runner = build_graph(ports, policy, config, checkpointer, log)
    start_state = initial_state(run_id, seed_url, role=config.role)
    start_state["current_bundle"] = seed_bundle

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

    reason = _terminal_reason(final, config) or "frontier_exhausted"
    ports.crawler.close()
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
    )
