"""The exploration vocabulary: state schema, frontier entries, and results.

One `TypedDict` for the whole orchestrator, defined once, here. Nodes receive it
and return **partial updates**; LangGraph merges them. Nothing mutates it in
place, and nothing keeps loop state outside it, because anything outside it is
invisible to the checkpointer and therefore lost on resume.

Everything in here must survive a serialize/deserialize round trip. That is the
real constraint on this file: a field you cannot checkpoint is a field that
silently breaks crash-resume in Month 4. Collections are lists rather than sets
and deques for exactly that reason — membership is O(n), but n is bounded by
`max_states` and correctness after a crash is worth more than the constant.

`explore.py` and `graph_runner.py` both import from here. That shared vocabulary
is what makes their parity checkable rather than merely claimed.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TypedDict

from apps.agent.contracts import (
    Action,
    ActionKind,
    CaptureBundle,
    Role,
    TerminationReason,
    Verdict,
    Violation,
)

__all__ = [
    "REPLAY_SAFE_KINDS",
    "ExplorationResult",
    "ExplorationState",
    "PendingAction",
    "SkippedAction",
    "initial_state",
]

#: Kinds with no side effect on the application under test, and therefore the
#: only ones a replay may re-fire. Deliberately conservative: a `click` on a
#: control that turns out to mutate is a bug report for Track A's enumeration,
#: not a reason to widen this set. See `explore.py` on why replay and
#: at-most-once have to be reconciled at all.
REPLAY_SAFE_KINDS: frozenset[ActionKind] = frozenset({"navigate", "click", "back"})


@dataclass(frozen=True, slots=True)
class PendingAction:
    """One frontier entry: an action, the state it is valid from, and the way back.

    `from_state_id` is not decoration. An action enumerated on `/dashboard`
    cannot be executed while the browser is sitting on `/login`, so the frontier
    has to remember where each action belongs — and `path` is how the loop gets
    back there.
    """

    from_state_id: str
    action: Action
    #: Depth of the state this action leads *to*, for the depth limit (FR-10).
    depth: int
    #: Actions from the seed to `from_state_id`, replayed to return there.
    path: tuple[Action, ...] = ()

    def __post_init__(self) -> None:
        # The checkpointer round-trips tuples as lists. Without this coercion a
        # resumed frontier entry would not compare equal to the identical entry
        # built in memory, and the annotation above would quietly be a lie.
        # Unconditional: `tuple(t)` on a tuple returns it unchanged.
        object.__setattr__(self, "path", tuple(self.path))

    @property
    def replayable(self) -> bool:
        """False when returning here would re-fire something with side effects."""
        return all(step.kind in REPLAY_SAFE_KINDS for step in self.path)


@dataclass(frozen=True, slots=True)
class SkippedAction:
    """An action the loop chose not to complete, and why.

    Every skip is recorded. A silent drop is the bug you find three weeks later,
    when the coverage number is wrong and nothing says which action went missing.
    """

    from_state_id: str
    action_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class ExplorationResult:
    """What one run produced. The graph itself lives in the `GraphPort`.

    Both implementations return this, field for field. It is the parity surface.
    """

    run_id: str
    seed_url: str
    role: Role
    termination_reason: TerminationReason
    #: State ids in scan order. Repeats are expected: a repeat is a closed cycle.
    order: tuple[str, ...] = ()
    states: int = 0
    edges: int = 0
    visited_pairs: int = 0
    #: How many times the loop had to re-navigate to reach a state.
    replays: int = 0
    #: Actions re-fired during those replays — the actual cost of breadth. A run
    #: where this dwarfs `visited_pairs` is one where path replay, not perception,
    #: is the bottleneck.
    replay_steps: int = 0
    violations: tuple[Violation, ...] = ()
    skipped: tuple[SkippedAction, ...] = ()
    duration_ms: float = 0.0


class ExplorationState(TypedDict):
    """Everything one run knows, in its entirety, serializable.

    Used by `graph_runner.py`. `explore.py` keeps the same information in local
    variables — which is precisely why it cannot be resumed, and why the port
    exists.
    """

    run_id: str
    role: Role
    seed_url: str

    # -- where the browser is ------------------------------------------------
    #: The capture currently being reasoned about.
    current_bundle: CaptureBundle | None
    current_state_id: str | None
    #: Actions from the seed to the current state, for replaying back to it.
    #: A `Sequence`, not a `tuple`: the checkpointer hands it back as a list, and
    #: an annotation that says otherwise is a trap for whoever writes the resume.
    current_path: Sequence[Action]
    #: Depth of the current state. First-discovery depth, never rewritten.
    depth: int
    #: Set by `scan`; `reason` audits only when it is true.
    first_visit: bool

    # -- the in-flight action ------------------------------------------------
    pending: PendingAction | None
    #: Produced by `act`, consumed by `observe`. None when the action was skipped.
    next_bundle: CaptureBundle | None
    #: False when `act` skipped, which routes `observe` back to `act` instead of
    #: on to `scan` — a skip must not add a phantom entry to `order`.
    acted: bool

    # -- accumulated ---------------------------------------------------------
    frontier: list[PendingAction]
    seen: list[str]
    order: list[str]
    violations: list[Violation]
    skipped: list[SkippedAction]

    edges: int
    visited_pairs: int
    replays: int
    replay_steps: int

    verdict: Verdict | None
    termination_reason: TerminationReason | None


def initial_state(
    run_id: str,
    seed_url: str,
    *,
    role: Role = "guest",
) -> ExplorationState:
    """A run that has not started yet.

    Every key is present from the outset. A `TypedDict` with holes in it turns
    every node into a defensive `.get()` and hides real bugs behind defaults.
    Limits are not here — they live in `OrchestratorConfig`, which the graph
    closes over, because a limit that can drift mid-run is a limit that will.
    """
    return ExplorationState(
        run_id=run_id,
        role=role,
        seed_url=seed_url,
        current_bundle=None,
        current_state_id=None,
        current_path=(),
        depth=0,
        first_visit=False,
        pending=None,
        next_bundle=None,
        acted=False,
        frontier=[],
        seen=[],
        order=[],
        violations=[],
        skipped=[],
        edges=0,
        visited_pairs=0,
        replays=0,
        replay_steps=0,
        verdict=None,
        termination_reason=None,
    )
