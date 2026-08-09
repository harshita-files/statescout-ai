"""Plain-Python BFS exploration (M2-P1). **Deprecated for production use.**

`graph_runner.py` is the implementation the product runs: parity was proven in
M2-P2, and only the LangGraph version can be checkpointed and resumed. Nothing
outside the tests imports this module.

It is kept, not deleted, because it is the **parity oracle**. Every test in
`tests/unit/orchestrator/test_explore.py` runs against both, so this file is what
stops the port from drifting into behaviour nobody chose — a framework-free
statement of the exploration policy that can be read in one sitting and does not
require reasoning about superstep scheduling to verify.

Delete it when that suite is retired, and not before. Until then, a change here
without the same change in `graph_runner.py` is a failing test, by design.

The termination invariant
=========================
The loop terminates on any application, cyclic or not, finite or not.

**Claim.** Every iteration of the `while` loop removes exactly one candidate from
the frontier, and the total number of candidates ever enqueued is finite.

*One removal per iteration.* Every path through the body — replay failure, action
failure, success — reaches the bottom having popped exactly one item and pushed
only candidates from a freshly discovered state. Nothing re-enqueues the item it
just took.

*Finitely many enqueues.* A candidate `(state_id, action_id)` is enqueued only
when all four hold:

1. its state is being visited for the **first time** (`state_id not in seen`),
2. `GraphPort.is_visited(state_id, action_id)` is false,
3. the pair is not already queued,
4. the state's depth is below `depth_limit`.

Condition 1 alone bounds enqueues at `|states| x |actions per state|`, because a
state is scanned-for-the-first-time exactly once. Conditions 2 and 3 make that
bound hold across a resumed run too, where `seen` starts empty but the graph's
visited set does not.

*Finitely many states.* `|states|` is bounded by `config.max_states`, checked at
the top of every iteration. This is the backstop that matters: if
`GraphPort.fingerprint` stops normalising (ADR-001 decision 2) then every page
load looks like a new state and `depth_limit` alone will not save the run.
`depth_limit` bounds a different shape — a deep chain with low fan-out — and
neither limit implies the other.

Therefore the frontier strictly shrinks except on finitely many iterations, and
the loop halts. ∎

*What this does not claim.* It does not claim full coverage. An action whose path
cannot be replayed (below) is reported as skipped, and states reachable only
through it are never visited. Coverage is reported, never assumed.

Breadth costs re-navigation
===========================
One browser can only act on the page it is looking at. BFS dequeues the oldest
candidate, which usually belongs to some other state, so the loop must first get
back there: it re-opens the seed and replays the action path. That is the price
of breadth, and `ExplorationResult.replays` makes it visible.

Replay conflicts with at-most-once, and the conflict is resolved by kind
=======================================================================
ADR-001 decision 3 gives at-most-once semantics against a target application that
is probably not idempotent. Replay re-fires every action on a path, which
directly contradicts that — replaying `submit order` three times creates three
orders.

The resolution is that at-most-once protects *effects*, not calls. Only
`REPLAY_SAFE_KINDS` — pure navigation — may be re-fired. A path containing a
`fill`, `select`, or `submit` is unreplayable: the candidate behind it is skipped
with a reason, and its subtree is reported as unexplored rather than being
reached by quietly re-submitting a form.

This refines decision 3 rather than breaking it, and Month 4's checkpoint-resume
inherits the same rule.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field

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
from apps.agent.orchestrator.runlog import Logger
from apps.agent.orchestrator.state import (
    ExplorationResult,
    PendingAction,
    SkippedAction,
)

__all__ = ["ExplorationResult", "SkippedAction", "explore"]


@dataclass
class _Run:
    """Mutable bookkeeping for one exploration. Deliberately not the checkpointed
    state — that is `state.py`, and M2-P2 is what has to serialize it."""

    frontier: deque[PendingAction] = field(default_factory=deque)
    queued: set[tuple[str, str]] = field(default_factory=set)
    seen: set[str] = field(default_factory=set)
    order: list[str] = field(default_factory=list)
    violations: list[Violation] = field(default_factory=list)
    skipped: list[SkippedAction] = field(default_factory=list)
    edges = 0
    pairs = 0
    replays = 0
    replay_steps = 0
    current_state_id: str | None = None
    current_path: tuple[Action, ...] = ()


def explore(
    ports: Ports,
    seed_url: str,
    policy: ExpectationSet,
    config: OrchestratorConfig,
    *,
    run_id: str | None = None,
    log: Logger | None = None,
) -> ExplorationResult:
    """Crawl breadth-first from `seed_url`, auditing every state once.

    Never raises for an application-level failure: a dead link, a stale control,
    or an unreplayable path is a recorded skip, not an aborted run. The only
    error termination is a seed that cannot be opened, because there is nothing
    to explore.
    """
    run_id = run_id or config.new_run_id()
    log = log or Logger.discard(run_id)
    started = time.perf_counter()
    run = _Run()

    def finish(reason: TerminationReason) -> ExplorationResult:
        ports.crawler.close()
        log.emit(
            "shutdown",
            "finished",
            reason=reason,
            states=len(run.seen),
            edges=run.edges,
            pairs=run.pairs,
            skipped=len(run.skipped),
            replays=run.replays,
            replay_steps=run.replay_steps,
        )
        return ExplorationResult(
            run_id=run_id or "",
            seed_url=seed_url,
            role=config.role,
            termination_reason=reason,
            order=tuple(run.order),
            states=len(run.seen),
            edges=run.edges,
            visited_pairs=run.pairs,
            replays=run.replays,
            replay_steps=run.replay_steps,
            violations=tuple(run.violations),
            skipped=tuple(run.skipped),
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
        )

    def scan(bundle: CaptureBundle, depth: int, path: tuple[Action, ...]) -> str:
        """Fingerprint, persist, audit, and enqueue — the skeleton's five stages,
        wrapped so the frontier can call them repeatedly."""
        state_id = ports.graph.fingerprint(bundle)
        run.order.append(state_id)
        run.current_state_id = state_id
        run.current_path = path

        first_visit = state_id not in run.seen
        log.emit("scan", "scanned", state_id=state_id, depth=depth, first_visit=first_visit)
        if not first_visit:
            # Everything below is idempotent by state, so a revisit does no work.
            # The revisit itself is already recorded: `order` grew, and the edge
            # that brought us here was persisted as a back-edge.
            return state_id

        run.seen.add(state_id)
        ports.graph.persist_state(
            StateNode(
                state_id=state_id,
                url=bundle.url,
                role=config.role,
                depth=depth,
                title=bundle.title,
                screenshot_path=bundle.screenshot_path,
            )
        )

        ui_map = ports.perception.analyze(bundle, config.role)
        for violation in ports.perception.audit(ui_map, policy):
            run.violations.append(violation)
            ports.graph.persist_violation(violation)
            log.emit(
                "audit",
                "violation",
                state_id=state_id,
                expectation_id=violation.expectation_id,
                clause_type=violation.clause_type,
                severity=violation.severity,
            )

        if depth < config.depth_limit:
            for action in ports.crawler.enumerate_actions(bundle):
                pair = (state_id, action.action_id)
                if pair in run.queued or ports.graph.is_visited(*pair):
                    continue
                run.queued.add(pair)
                run.frontier.append(PendingAction(state_id, action, depth + 1, path))

        return state_id

    def reach(candidate: PendingAction) -> bool:
        """Put the browser back on `candidate.from_state_id`. False means skip."""
        if run.current_state_id == candidate.from_state_id:
            return True

        if not candidate.replayable:
            _skip(candidate, "unreplayable path: it contains a side-effecting action")
            return False

        try:
            bundle = ports.crawler.open(seed_url)
            for step in candidate.path:
                bundle = ports.crawler.act(step)
                run.replay_steps += 1
        except StateScoutError as exc:
            _skip(candidate, f"replay failed: {exc}")
            return False

        run.replays += 1
        landed = ports.graph.fingerprint(bundle)
        if landed != candidate.from_state_id:
            # The same path led somewhere else. The application is not
            # deterministic, or a fingerprint is unstable. Either way, acting here
            # would attribute an edge to the wrong state.
            _skip(candidate, f"replay diverged: expected {candidate.from_state_id}, got {landed}")
            run.current_state_id = landed
            run.current_path = candidate.path
            return False

        run.current_state_id = landed
        run.current_path = candidate.path
        log.emit("replay", "replayed", state_id=landed, steps=len(candidate.path))
        return True

    def _skip(candidate: PendingAction, reason: str) -> None:
        run.skipped.append(
            SkippedAction(candidate.from_state_id, candidate.action.action_id, reason)
        )
        log.emit(
            "act",
            "skipped",
            state_id=candidate.from_state_id,
            action_id=candidate.action.action_id,
            reason=reason,
        )

    # -- the loop ---------------------------------------------------------
    log.emit("startup", "started", seed=seed_url, role=config.role)

    try:
        seed_bundle = ports.crawler.open(seed_url)
    except StateScoutError as exc:
        log.emit("startup", "failed", reason=str(exc))
        ports.crawler.close()
        return ExplorationResult(
            run_id=run_id,
            seed_url=seed_url,
            role=config.role,
            termination_reason="error",
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
        )

    scan(seed_bundle, depth=0, path=())

    while run.frontier:
        if len(run.seen) >= config.max_states:
            return finish("max_states")

        candidate = run.frontier.popleft()
        if not reach(candidate):
            continue

        # ADR-001 decision 3: claim the pair before executing it. A crash between
        # here and the edge below leaves a claimed pair with no edge, which resume
        # treats as done-but-unrecorded rather than re-firing the action.
        ports.graph.mark_visited(candidate.from_state_id, candidate.action.action_id)
        run.pairs += 1

        try:
            landed = ports.crawler.act(candidate.action)
        except CrawlerError as exc:
            _skip(candidate, str(exc))
            continue

        to_state_id = ports.graph.fingerprint(landed)
        ports.graph.persist_edge(
            StateEdge(
                from_state_id=candidate.from_state_id,
                to_state_id=to_state_id,
                action_id=candidate.action.action_id,
                label=candidate.action.label,
                # A cycle closed. Recorded, never pruned.
                is_back_edge=to_state_id in run.seen,
            )
        )
        run.edges += 1

        scan(landed, candidate.depth, (*candidate.path, candidate.action))

    return finish("frontier_exhausted")
