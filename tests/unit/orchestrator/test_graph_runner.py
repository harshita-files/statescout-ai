"""What only the LangGraph port can do (M2-P2).

Behavioural equivalence is proved in `test_explore.py`, where the whole M2-P1
suite runs against both implementations. This file covers the two things that
file cannot: a direct field-by-field comparison of the two results, and the
durability the port exists for — a checkpointed state schema that a crashed run
can be resumed from.

The topology and checkpointing assertions here replace the ones that were aimed
at `poc.py`. Those proved a scaffold compiled; these prove the real runner does.
"""

from __future__ import annotations

import dataclasses

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from apps.agent.contracts import Action, ExpectationSet
from apps.agent.orchestrator import explore as reference
from apps.agent.orchestrator import graph_runner
from apps.agent.orchestrator.config import OrchestratorConfig
from apps.agent.orchestrator.deps import Ports
from apps.agent.orchestrator.fakes import (
    DEFAULT_POLICY,
    FakeCrawler,
    FakeGraph,
    FakeLink,
    FakePage,
    FakePerception,
)
from apps.agent.orchestrator.state import ExplorationResult, PendingAction

LOGIN = "http://fake.test/login"

#: Apps that exercise different shapes of the loop: cycles, a self-loop, a
#: diamond, and a path the loop refuses to replay.
FIXTURES: dict[str, tuple[dict[str, FakePage] | None, str]] = {
    "default": (None, LOGIN),
    "self_loop": (
        {"/one": FakePage(title="One", transitions=(FakeLink("Refresh", "/one"),))},
        "/one",
    ),
    "diamond": (
        {
            "/a": FakePage(title="A", transitions=(FakeLink("b", "/b"), FakeLink("c", "/c"))),
            "/b": FakePage(title="B", transitions=(FakeLink("d", "/d"), FakeLink("a", "/a"))),
            "/c": FakePage(title="C", transitions=(FakeLink("d", "/d"), FakeLink("a", "/a"))),
            "/d": FakePage(title="D", transitions=(FakeLink("b", "/b"), FakeLink("c", "/c"))),
        },
        "/a",
    ),
    "unreplayable": (
        {
            "/form": FakePage(
                title="Form",
                transitions=(
                    FakeLink("Submit", "/done", role="button", kind="submit"),
                    FakeLink("Help", "/help"),
                ),
            ),
            "/done": FakePage(title="Done", transitions=(FakeLink("More", "/more"),)),
            "/more": FakePage(title="More"),
            "/help": FakePage(title="Help"),
        },
        "/form",
    ),
}


def config(**overrides: object) -> OrchestratorConfig:
    defaults: dict[str, object] = {
        "perception_rate_per_min": 0,
        "depth_limit": 99,
        "max_states": 99,
    }
    return OrchestratorConfig(_env_file=None, **{**defaults, **overrides})  # type: ignore[arg-type]


def ports_for(app: dict[str, FakePage] | None) -> Ports:
    crawler = FakeCrawler(app) if app else FakeCrawler()
    return Ports(crawler=crawler, perception=FakePerception(), graph=FakeGraph())


def comparable(result: ExplorationResult) -> dict[str, object]:
    """Everything except the two fields that legitimately differ per run."""
    fields = dataclasses.asdict(result)
    fields.pop("duration_ms")
    return fields


# ---------------------------------------------------------------------------
# Parity, head to head
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fixture", list(FIXTURES), ids=list(FIXTURES))
def test_both_implementations_return_identical_results(fixture: str) -> None:
    """Not "similar" — equal, field for field, including the scan order and the
    skip reasons. A port that gets the counts right but visits states in a
    different order has changed the crawl, and Month 4's resume would inherit
    the difference."""
    app, seed = FIXTURES[fixture]
    settings = config()

    first = reference.explore(ports_for(app), seed, DEFAULT_POLICY, settings, run_id="parity")
    second = graph_runner.explore(ports_for(app), seed, DEFAULT_POLICY, settings, run_id="parity")

    assert comparable(first) == comparable(second)


@pytest.mark.parametrize("fixture", list(FIXTURES), ids=list(FIXTURES))
def test_both_implementations_build_the_same_graph(fixture: str) -> None:
    """The `ExplorationResult` counts edges; this checks the edges themselves."""
    app, seed = FIXTURES[fixture]
    settings = config()

    left, right = ports_for(app), ports_for(app)
    reference.explore(left, seed, DEFAULT_POLICY, settings, run_id="parity")
    graph_runner.explore(right, seed, DEFAULT_POLICY, settings, run_id="parity")

    assert left.graph.states == right.graph.states  # type: ignore[attr-defined]
    assert left.graph.edges == right.graph.edges  # type: ignore[attr-defined]
    assert left.graph.visited == right.graph.visited  # type: ignore[attr-defined]
    assert left.graph.violations == right.graph.violations  # type: ignore[attr-defined]


def test_an_unreachable_seed_matches_too() -> None:
    settings = config()
    first = reference.explore(ports_for(None), "/ghost", DEFAULT_POLICY, settings, run_id="p")
    second = graph_runner.explore(ports_for(None), "/ghost", DEFAULT_POLICY, settings, run_id="p")
    assert comparable(first) == comparable(second)
    assert first.termination_reason == "error"


# ---------------------------------------------------------------------------
# Topology
# ---------------------------------------------------------------------------


def compiled() -> graph_runner.Runner:
    return graph_runner.build_graph(ports_for(None), DEFAULT_POLICY, config())


def test_the_graph_has_the_four_nodes() -> None:
    assert {"scan", "reason", "act", "observe"} <= set(compiled().get_graph().nodes)


def test_the_graph_contains_the_exploration_cycle() -> None:
    """Without `observe -> scan` this is a pipeline, not an explorer."""
    edges = {(e.source, e.target) for e in compiled().get_graph().edges}
    assert ("scan", "reason") in edges
    assert ("act", "observe") in edges
    assert ("observe", "scan") in edges


def test_a_skip_routes_back_to_act_without_scanning() -> None:
    """The edge that keeps a skipped action from adding a phantom entry to
    `order`. Its absence is a parity failure, which is why it is drawn."""
    edges = {(e.source, e.target) for e in compiled().get_graph().edges}
    assert ("observe", "act") in edges


def test_both_conditional_edges_can_terminate() -> None:
    edges = {(e.source, e.target) for e in compiled().get_graph().edges}
    assert ("reason", "__end__") in edges
    assert ("observe", "__end__") in edges


# ---------------------------------------------------------------------------
# Durability — the reason the port exists
# ---------------------------------------------------------------------------


def test_the_run_is_checkpointed() -> None:
    saver = InMemorySaver()
    ports = ports_for(None)
    result = graph_runner.explore(
        ports, LOGIN, DEFAULT_POLICY, config(), run_id="cp-1", checkpointer=saver
    )
    runner = graph_runner.build_graph(ports, DEFAULT_POLICY, config(), saver)
    saved = runner.get_state({"configurable": {"thread_id": "cp-1"}})

    assert tuple(saved.values["order"]) == result.order
    assert saved.values["visited_pairs"] == result.visited_pairs


def test_every_superstep_is_checkpointed_not_only_the_end() -> None:
    """M4-P1 resumes from the last checkpoint. A single checkpoint at the end
    means a crash mid-crawl loses the whole run."""
    saver = InMemorySaver()
    ports = ports_for(None)
    graph_runner.explore(ports, LOGIN, DEFAULT_POLICY, config(), run_id="cp-2", checkpointer=saver)
    runner = graph_runner.build_graph(ports, DEFAULT_POLICY, config(), saver)
    history = list(runner.get_state_history({"configurable": {"thread_id": "cp-2"}}))
    assert len(history) > 10


def test_the_frontier_survives_a_checkpoint_round_trip() -> None:
    """`PendingAction` carries an `Action` and a replay path. If those did not
    serialize, a resumed run would come back with an empty frontier and declare
    itself finished — the worst possible failure, because it looks like success."""
    saver = InMemorySaver()
    ports = ports_for(None)
    graph_runner.explore(
        ports,
        LOGIN,
        DEFAULT_POLICY,
        config(max_states=2),
        run_id="cp-3",
        checkpointer=saver,
    )
    runner = graph_runner.build_graph(ports, DEFAULT_POLICY, config(max_states=2), saver)
    frontier = runner.get_state({"configurable": {"thread_id": "cp-3"}}).values["frontier"]

    assert frontier
    item = frontier[0]
    assert item.action.action_id
    assert item.replayable in (True, False)


def test_a_round_tripped_frontier_entry_equals_the_original() -> None:
    """The checkpointer serialises a tuple and hands back a list, so a resumed
    `PendingAction` would not compare equal to the same entry built in memory —
    and a resume that cannot recognise its own frontier re-explores or drops it.
    `PendingAction` coerces the path back to a tuple to close that gap."""
    action = Action(action_id="a-1", kind="navigate", target="#x")
    step = Action(action_id="a-0", kind="click", target="#y")

    from_memory = PendingAction("s-1", action, 1, (step,))
    from_checkpoint = PendingAction("s-1", action, 1, [step])  # type: ignore[arg-type]

    assert from_checkpoint.path == (step,)
    assert from_checkpoint == from_memory


def test_ports_and_config_stay_out_of_the_checkpoint() -> None:
    """Closed over, never stored. A crawler handle or an API key inside a
    checkpoint would be unserializable at best and a leaked credential at worst
    (NFR-11)."""
    saver = InMemorySaver()
    ports = ports_for(None)
    graph_runner.explore(ports, LOGIN, DEFAULT_POLICY, config(), run_id="cp-4", checkpointer=saver)
    runner = graph_runner.build_graph(ports, DEFAULT_POLICY, config(), saver)
    saved = runner.get_state({"configurable": {"thread_id": "cp-4"}}).values

    assert "ports" not in saved
    assert "config" not in saved
    assert "policy" not in saved
    assert "depth_limit" not in saved  # limits live in config, not in state


def test_the_default_checkpointer_is_in_memory() -> None:
    """No argument still means checkpointed, so the loop's behaviour does not
    change when M4 swaps in a durable saver."""
    ports = ports_for(None)
    result = graph_runner.explore(ports, LOGIN, DEFAULT_POLICY, config(), run_id="cp-5")
    assert result.termination_reason == "frontier_exhausted"


# ---------------------------------------------------------------------------
# The recursion limit
# ---------------------------------------------------------------------------


def test_the_recursion_limit_scales_with_max_states() -> None:
    assert graph_runner.recursion_limit(config(max_states=1)) >= 100
    assert graph_runner.recursion_limit(config(max_states=200)) > graph_runner.recursion_limit(
        config(max_states=10)
    )
    assert graph_runner.recursion_limit(config(max_states=200)) > 4000


def test_a_real_run_stays_far_below_the_recursion_limit() -> None:
    """The backstop must never be what stops a crawl. If this ever gets close,
    the termination argument is wrong, not the constant."""
    saver = InMemorySaver()
    ports = ports_for(None)
    settings = config()
    graph_runner.explore(ports, LOGIN, DEFAULT_POLICY, settings, run_id="rl-1", checkpointer=saver)
    runner = graph_runner.build_graph(ports, DEFAULT_POLICY, settings, saver)
    supersteps = len(list(runner.get_state_history({"configurable": {"thread_id": "rl-1"}})))
    assert supersteps < graph_runner.recursion_limit(settings) / 4


def test_a_fifty_way_fan_out_still_fits() -> None:
    """The shape most likely to exhaust supersteps before it exhausts states."""
    app: dict[str, FakePage] = {
        "/hub": FakePage(
            title="Hub", transitions=tuple(FakeLink(f"i{i}", f"/i{i}") for i in range(50))
        )
    }
    for i in range(50):
        app[f"/i{i}"] = FakePage(title=f"I{i}")

    result = graph_runner.explore(ports_for(app), "/hub", ExpectationSet(), config(), run_id="fan")
    assert result.termination_reason == "frontier_exhausted"
    assert result.states == 51
