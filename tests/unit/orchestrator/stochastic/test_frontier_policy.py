"""The frontier ordering policies. They may only reorder, never add or drop."""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Mapping

from apps.agent.contracts import Action
from apps.agent.orchestrator.state import PendingAction
from apps.agent.orchestrator.stochastic.frontier_policy import (
    UcbConfig,
    bfs_priority,
    ucb_priority,
)


class FakeSource:
    """Structural stand-in for the transition model."""

    def __init__(
        self,
        entropy: Mapping[tuple[str, str], float] | None = None,
        observations: Mapping[tuple[str, str], int] | None = None,
    ) -> None:
        self._entropy = dict(entropy or {})
        self._obs = dict(observations or {})

    def entropy(self, state_class: str, action_id: str) -> float:
        return self._entropy.get((state_class, action_id), 0.0)

    def total_observations(self, state_class: str, action_id: str) -> int:
        return self._obs.get((state_class, action_id), 0)


def pa(state: str, action_id: str, depth: int = 1) -> PendingAction:
    return PendingAction(
        from_state_id=state,
        action=Action(action_id=action_id, kind="click", target=f"#{action_id}"),
        depth=depth,
    )


def key(items: list[PendingAction]) -> list[tuple[str, str]]:
    return [(i.from_state_id, i.action.action_id) for i in items]


def test_bfs_priority_is_identity_and_returns_a_new_list() -> None:
    frontier = [pa("s2", "b"), pa("s1", "a"), pa("s3", "c")]
    out = bfs_priority(frontier)
    assert out == frontier
    assert out is not frontier


def test_ucb_empty_frontier() -> None:
    assert ucb_priority([], FakeSource()) == []


def test_unvisited_pairs_come_before_resamples() -> None:
    src = FakeSource(entropy={("s1", "seen"): 5.0}, observations={("s1", "seen"): 1})
    frontier = [pa("s1", "seen"), pa("s1", "fresh")]
    assert key(ucb_priority(frontier, src)) == [("s1", "fresh"), ("s1", "seen")]


def test_higher_entropy_resample_first() -> None:
    src = FakeSource(
        entropy={("s", "calm"): 0.1, ("s", "noisy"): 1.5},
        observations={("s", "calm"): 2, ("s", "noisy"): 2},
    )
    out = ucb_priority([pa("s", "calm"), pa("s", "noisy")], src)
    assert key(out) == [("s", "noisy"), ("s", "calm")]


def test_depth_breaks_ties_shallow_first_then_action_id() -> None:
    src = FakeSource()
    frontier = [pa("s", "b", depth=2), pa("s", "z", depth=1), pa("s", "a", depth=2)]
    assert key(ucb_priority(frontier, src)) == [("s", "z"), ("s", "a"), ("s", "b")]


def test_resample_cap_demotes_but_never_removes() -> None:
    cfg = UcbConfig(max_resamples=2)
    src = FakeSource(
        entropy={("s", "capped"): 9.0, ("s", "ok"): 0.1},
        observations={("s", "capped"): 3, ("s", "ok"): 2},
    )
    out = ucb_priority([pa("s", "capped"), pa("s", "ok")], src, config=cfg)
    assert key(out) == [("s", "ok"), ("s", "capped")]


def test_cap_boundary() -> None:
    cfg = UcbConfig(max_resamples=2)
    # n=2 means one re-sample already happened: still under the cap of 2.
    # n=3 means two re-samples happened: capped.
    src = FakeSource(
        entropy={("s", "n2"): 0.0, ("s", "n3"): 9.0},
        observations={("s", "n2"): 2, ("s", "n3"): 3},
    )
    assert key(ucb_priority([pa("s", "n3"), pa("s", "n2")], src, config=cfg)) == [
        ("s", "n2"),
        ("s", "n3"),
    ]


def test_zero_cap_demotes_every_observed_pair() -> None:
    cfg = UcbConfig(max_resamples=0)
    src = FakeSource(entropy={("s", "seen"): 9.0}, observations={("s", "seen"): 1})
    out = ucb_priority([pa("s", "seen"), pa("s", "new")], src, config=cfg)
    assert key(out) == [("s", "new"), ("s", "seen")]


def test_state_class_mapping_is_used() -> None:
    src = FakeSource(
        entropy={("cls", "a"): 2.0},
        observations={("cls", "a"): 1},
    )
    frontier = [pa("s1", "a"), pa("s2", "b")]
    out = ucb_priority(frontier, src, state_class_of=lambda s: "cls" if s == "s1" else s)
    assert key(out) == [("s2", "b"), ("s1", "a")]


def test_reorders_only_multiset_preserved_including_duplicates() -> None:
    rng = random.Random(7)
    frontier = [
        pa(f"s{rng.randrange(4)}", f"a{rng.randrange(5)}", rng.randrange(1, 4)) for _ in range(40)
    ]
    frontier.append(frontier[0])
    src = FakeSource(
        entropy={(f"s{i}", f"a{j}"): rng.random() for i in range(4) for j in range(5)},
        observations={(f"s{i}", f"a{j}"): rng.randrange(0, 6) for i in range(4) for j in range(5)},
    )
    before = list(frontier)
    out = ucb_priority(frontier, src)
    assert frontier == before  # input untouched
    assert len(out) == len(before)
    assert Counter(key(out)) == Counter(key(before))
    assert all(any(o is b for b in before) for o in out)  # same objects, none minted


def test_deterministic_regardless_of_input_order_for_distinct_pairs() -> None:
    src = FakeSource(
        entropy={("s", "a"): 0.5, ("s", "b"): 0.5, ("s", "c"): 1.0},
        observations={("s", "a"): 1, ("s", "b"): 1, ("s", "c"): 1},
    )
    items = [pa("s", "a"), pa("s", "b"), pa("s", "c"), pa("s", "d")]
    expected = key(ucb_priority(items, src))
    for seed in range(10):
        shuffled = list(items)
        random.Random(seed).shuffle(shuffled)
        assert key(ucb_priority(shuffled, src)) == expected


def test_bad_entropy_values_are_treated_as_zero() -> None:
    src = FakeSource(
        entropy={("s", "nan"): float("nan"), ("s", "neg"): -3.0, ("s", "inf"): float("inf")},
        observations={("s", "nan"): 1, ("s", "neg"): 1, ("s", "inf"): 1},
    )
    out = ucb_priority([pa("s", "nan"), pa("s", "neg"), pa("s", "inf")], src)
    assert sorted(key(out)) == [("s", "inf"), ("s", "nan"), ("s", "neg")]
    assert key(out) == [("s", "inf"), ("s", "nan"), ("s", "neg")]  # all tie -> action_id


def test_repeated_application_is_a_fixed_point() -> None:
    src = FakeSource(
        entropy={("s", "a"): 1.0, ("s", "b"): 0.2},
        observations={("s", "a"): 1, ("s", "b"): 2},
    )
    once = ucb_priority([pa("s", "b"), pa("s", "a"), pa("s", "c")], src)
    assert key(ucb_priority(once, src)) == key(once)
