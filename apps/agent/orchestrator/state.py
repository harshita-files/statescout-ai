"""The exploration state schema — defined once, here.

One `TypedDict` for the whole orchestrator. Nodes receive it and return **partial
updates**; LangGraph merges them. Nothing mutates it in place, and nothing keeps
loop state outside it, because anything outside it is invisible to the
checkpointer and therefore lost on resume.

Everything in here must survive a serialize/deserialize round trip. That is the
real constraint on this file: a field you cannot checkpoint is a field that
silently breaks crash-resume in Month 4.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

from apps.agent.contracts import (
    Action,
    CaptureBundle,
    Role,
    TerminationReason,
    Verdict,
    Violation,
)

__all__ = ["ExplorationState", "PendingAction", "initial_state"]


@dataclass(frozen=True, slots=True)
class PendingAction:
    """One frontier entry: an action, and the state it is valid from.

    The `from_state_id` is not decoration. An action enumerated on `/dashboard`
    cannot be executed while the browser is sitting on `/login`, so the frontier
    has to remember where each action belongs.
    """

    from_state_id: str
    action: Action
    #: Depth of the state this action leads *to*, for the depth limit (FR-10).
    depth: int


class ExplorationState(TypedDict):
    """Everything one run knows. Serializable, in its entirety."""

    run_id: str
    role: Role
    seed_url: str

    #: The capture currently being reasoned about.
    current_bundle: CaptureBundle | None
    current_state_id: str | None
    #: Set by `act`, consumed by `scan` to persist the edge once the destination
    #: has been fingerprinted.
    previous_state_id: str | None
    last_action: Action | None
    #: Produced by `act`, promoted to `current_bundle` by `observe`.
    next_bundle: CaptureBundle | None

    #: Actions enqueued and not yet executed. A list, not a deque, because it is
    #: checkpointed.
    frontier: list[PendingAction]
    #: State ids in the order they were scanned. Repeats are expected and correct
    #: — revisiting a state is how a cycle gets recorded.
    visited: list[str]
    violations: list[Violation]
    skipped: list[str]

    depth: int
    depth_limit: int
    iterations: int
    max_iterations: int

    verdict: Verdict | None
    termination_reason: TerminationReason | None


def initial_state(
    run_id: str,
    seed_url: str,
    *,
    role: Role = "guest",
    depth_limit: int = 5,
    max_iterations: int = 25,
) -> ExplorationState:
    """A run that has not started yet.

    Every key is present from the outset. A `TypedDict` with holes in it turns
    every node into a defensive `.get()` and hides real bugs behind defaults.
    """
    return ExplorationState(
        run_id=run_id,
        role=role,
        seed_url=seed_url,
        current_bundle=None,
        current_state_id=None,
        previous_state_id=None,
        last_action=None,
        next_bundle=None,
        frontier=[],
        visited=[],
        violations=[],
        skipped=[],
        depth=0,
        depth_limit=depth_limit,
        iterations=0,
        max_iterations=max_iterations,
        verdict=None,
        termination_reason=None,
    )
