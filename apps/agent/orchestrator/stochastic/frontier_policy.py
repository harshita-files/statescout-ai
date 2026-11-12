"""Opt-in frontier orderings. Default stays FIFO/BFS.

Both functions are **pure reorderings**: the returned list holds exactly the
same `PendingAction` objects (duplicates included) as the input. They never add
a pair, never drop one, and never decide termination -- loop prevention remains
the visited `(state_id, action_id)` set, and `graph_runner` still pops from the
front of whatever order it is given.

`ucb_priority` ranks by expected novelty, in three tiers:

0. **Unvisited** -- the model has zero observations of `(state_class, action_id)`.
1. **Re-sample** -- observed before, but fewer than `max_resamples` re-samples
   have happened. Ranked by an exploration bonus
   `entropy / sqrt(n)` (high-entropy transitions are worth looking at again;
   the `1/sqrt(n)` decay is the UCB-style shrinkage).
2. **Capped** -- `max_resamples` re-samples already spent. Demoted to the back
   (FIFO among themselves), not removed, so the cap bounds how often a
   non-novel pair can jump the queue.

Ties break on shallower depth, then `action_id`, then `from_state_id`, then the
original index, so the order is a deterministic function of the input.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from apps.agent.orchestrator.state import PendingAction

__all__ = ["EntropySource", "UcbConfig", "bfs_priority", "ucb_priority"]


class EntropySource(Protocol):
    """What the policy needs from a transition model (structural, no import)."""

    def entropy(self, state_class: str, action_id: str) -> float: ...

    def total_observations(self, state_class: str, action_id: str) -> int: ...


@dataclass(frozen=True, slots=True)
class UcbConfig:
    #: Scale of the entropy bonus. Only matters relative to other re-samples.
    exploration_c: float = 1.0
    #: Re-samples of one `(state_class, action_id)` allowed to out-rank
    #: unobserved-elsewhere work. `n` observations means `n - 1` re-samples done.
    max_resamples: int = 3

    def __post_init__(self) -> None:
        if self.max_resamples < 0:
            raise ValueError("max_resamples must be >= 0")
        if not math.isfinite(self.exploration_c) or self.exploration_c < 0:
            raise ValueError("exploration_c must be finite and >= 0")


def bfs_priority(frontier: Sequence[PendingAction]) -> list[PendingAction]:
    """FIFO: the default. Returns a new list in the given order."""
    return list(frontier)


def _clean(value: float) -> float:
    """Entropy is a bonus: NaN, infinities and negatives are treated as 0."""
    return value if math.isfinite(value) and value > 0.0 else 0.0


def ucb_priority(
    frontier: Sequence[PendingAction],
    source: EntropySource,
    *,
    state_class_of: Callable[[str], str] = lambda state_id: state_id,
    config: UcbConfig | None = None,
) -> list[PendingAction]:
    """Reorder `frontier` by expected novelty. See the module docstring."""
    cfg = config or UcbConfig()

    def rank(indexed: tuple[int, PendingAction]) -> tuple[object, ...]:
        index, item = indexed
        state_class = state_class_of(item.from_state_id)
        action_id = item.action.action_id
        n = source.total_observations(state_class, action_id)
        if n <= 0:
            tier, score = 0, 0.0
        elif n <= cfg.max_resamples:
            bonus = cfg.exploration_c * _clean(source.entropy(state_class, action_id))
            tier, score = 1, round(bonus / math.sqrt(n), 12)
        else:
            tier, score = 2, 0.0
        if tier == 2:
            # Capped pairs keep arrival order: no entropy, depth or id tie-break.
            return (tier, 0.0, 0, "", "", index)
        return (tier, -score, item.depth, action_id, item.from_state_id, index)

    return [item for _, item in sorted(enumerate(frontier), key=rank)]
