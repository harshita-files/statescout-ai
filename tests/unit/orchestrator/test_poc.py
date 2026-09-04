"""The compiled LangGraph scaffold (M1-P4).

The PoC exists to prove four things before Month 2 commits to it: the graph
compiles with a cycle in it, the conditional edge routes, the checkpointer
actually saves, and a state can be revisited without the loop running forever.
Everything here tests one of those.

Deliberately *not* tested: exploration quality. This walks depth-first and knows
it (see the `poc.py` docstring). Asserting a breadth-first order here would lock
in the wrong behaviour before M2-P1 gets to make that decision.
"""

from __future__ import annotations

from typing import Any

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from apps.agent.contracts import ActionError, ExpectationSet
from apps.agent.orchestrator.deps import Ports, fake_ports
from apps.agent.orchestrator.fakes import FakeCrawler, FakeGraph, FakeLink, FakePage, FakePerception
from apps.agent.orchestrator.poc import build_graph
from apps.agent.orchestrator.poc import initial_poc_state as initial_state
from apps.agent.skeleton import SKELETON_POLICY

LOGIN = "http://fake.test/login"


def run(
    ports: Ports,
    *,
    seed: str = LOGIN,
    max_iterations: int = 3,
    depth_limit: int = 5,
    policy: ExpectationSet = SKELETON_POLICY,
    checkpointer: InMemorySaver | None = None,
    thread: str = "t-1",
) -> dict[str, Any]:
    app = build_graph(ports, policy, checkpointer)
    return dict(
        app.invoke(
            initial_state(thread, seed, max_iterations=max_iterations, depth_limit=depth_limit),
            config={"configurable": {"thread_id": thread}},
        )
    )


# ---------------------------------------------------------------------------
# The visited sequence — M1-P4's stated acceptance test
# ---------------------------------------------------------------------------


def test_three_iterations_walk_login_dashboard_login() -> None:
    """The exact sequence, not just its length.

    `/login -> /dashboard -> /login` is the whole point: the third entry is a
    *revisit*, which is what a cyclic exploration graph looks like and what a
    DAG-shaped implementation would have refused to produce.
    """
    ports = fake_ports()
    final = run(ports)

    login, dashboard, again = final["visited"]
    assert login == again
    assert login != dashboard
    assert final["iterations"] == 3


def test_a_revisited_state_is_stored_once() -> None:
    """Three visits, two nodes. Dedup applies to node creation only."""
    ports = fake_ports()
    final = run(ports)
    graph: FakeGraph = ports.graph  # type: ignore[assignment]

    assert len(final["visited"]) == 3
    assert len(graph.states) == 2


def test_the_cycle_is_recorded_as_a_back_edge() -> None:
    """Both edges are kept. Pruning the return edge would erase the evidence that
    the app can loop, which is exactly what a state-space audit is looking for."""
    ports = fake_ports()
    run(ports)
    graph: FakeGraph = ports.graph  # type: ignore[assignment]

    assert len(graph.edges) == 2
    assert len(graph.back_edges()) == 1
    forward, back = graph.edges
    assert (forward.from_state_id, forward.to_state_id) == (back.to_state_id, back.from_state_id)


def test_the_planted_violation_is_found_and_persisted() -> None:
    ports = fake_ports()
    final = run(ports)
    graph: FakeGraph = ports.graph  # type: ignore[assignment]

    assert [v.expectation_id for v in final["violations"]] == ["e-admin-link"]
    assert len(graph.violations) == 1


def test_a_violation_does_not_stop_the_crawl() -> None:
    """Coverage is the point: the run continues past the violated state, or a
    single early finding would hide everything behind it."""
    ports = fake_ports()
    final = run(ports)
    violated_at = final["visited"][1]
    assert final["visited"][2] != violated_at  # kept going


# ---------------------------------------------------------------------------
# Termination
# ---------------------------------------------------------------------------


def test_max_iterations_stops_the_loop() -> None:
    for limit in (1, 2, 3, 4):
        final = run(fake_ports(), max_iterations=limit, thread=f"t-{limit}")
        assert final["iterations"] == limit
        assert len(final["visited"]) == limit


def test_an_app_with_no_actions_terminates_immediately() -> None:
    """Frontier exhaustion, not a limit. The loop has to be able to finish on its
    own or `max_iterations` is load-bearing in production, which it must not be."""
    app = {"/dead-end": FakePage(title="Dead end")}
    ports = Ports(crawler=FakeCrawler(app), perception=FakePerception(), graph=FakeGraph())
    final = run(ports, seed="/dead-end", max_iterations=99)

    assert len(final["visited"]) == 1
    assert final["frontier"] == []


def test_a_self_loop_does_not_spin_forever() -> None:
    """One page linking to itself. The pair check stops it after one traversal;
    a naive "have I seen this state" check would have stopped it after zero, and
    a missing check would never stop at all."""
    app = {"/one": FakePage(title="One", transitions=(FakeLink(name="Refresh", to="/one"),))}
    ports = Ports(crawler=FakeCrawler(app), perception=FakePerception(), graph=FakeGraph())
    final = run(ports, seed="/one", max_iterations=99)

    assert final["visited"] == [final["visited"][0]] * 2
    graph: FakeGraph = ports.graph  # type: ignore[assignment]
    assert len(graph.back_edges()) == 1


def test_depth_limit_stops_enqueueing() -> None:
    """FR-10. At depth 0 with a limit of 0, nothing is ever enqueued."""
    ports = fake_ports()
    final = run(ports, depth_limit=0, max_iterations=99)

    assert final["frontier"] == []
    assert len(final["visited"]) == 1


# ---------------------------------------------------------------------------
# The visited set
# ---------------------------------------------------------------------------


def test_a_pair_is_claimed_before_the_action_runs() -> None:
    """ADR-001 decision 3. Two actions executed, two pairs claimed."""
    ports = fake_ports()
    run(ports)
    graph: FakeGraph = ports.graph  # type: ignore[assignment]
    crawler: FakeCrawler = ports.crawler  # type: ignore[assignment]

    assert len(crawler.acted) == 2
    assert len(graph.visited) == 2


def test_a_claimed_pair_is_never_re_enqueued() -> None:
    ports = fake_ports()
    final = run(ports, max_iterations=6)
    graph: FakeGraph = ports.graph  # type: ignore[assignment]

    queued = {(item.from_state_id, item.action.action_id) for item in final["frontier"]}
    assert not (queued & graph.visited)


def test_a_failed_action_is_recorded_not_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    """Silent drops are the bug you find three weeks later, when coverage numbers
    are wrong and nothing in the log says why."""
    ports = fake_ports()

    def boom(_action: object) -> None:
        raise ActionError("stale element")

    monkeypatch.setattr(ports.crawler, "act", boom)
    final = run(ports, max_iterations=2)

    assert len(final["skipped"]) == 1
    assert "stale element" in final["skipped"][0]


def test_a_failed_action_still_claims_its_pair(monkeypatch: pytest.MonkeyPatch) -> None:
    """At-most-once means at-most-once even when the action blew up: retrying it
    on resume could be the write that succeeded before the crash."""
    ports = fake_ports()
    monkeypatch.setattr(
        ports.crawler, "act", lambda _action: (_ for _ in ()).throw(ActionError("boom"))
    )
    run(ports, max_iterations=2)
    graph: FakeGraph = ports.graph  # type: ignore[assignment]
    assert len(graph.visited) == 1


# ---------------------------------------------------------------------------
# Graph topology and checkpointing
# ---------------------------------------------------------------------------


def test_the_compiled_graph_has_the_four_nodes_and_a_cycle() -> None:
    compiled = build_graph(fake_ports(), SKELETON_POLICY)
    drawn = compiled.get_graph()
    names = set(drawn.nodes)

    assert {"scan", "reason", "act", "observe"} <= names
    edges = {(e.source, e.target) for e in drawn.edges}
    assert ("scan", "reason") in edges
    assert ("act", "observe") in edges
    # The cycle: without this edge the graph is a pipeline, not an explorer.
    assert ("observe", "scan") in edges


def test_reason_branches_three_ways() -> None:
    compiled = build_graph(fake_ports(), SKELETON_POLICY)
    targets = {e.target for e in compiled.get_graph().edges if e.source == "reason"}
    assert "act" in targets
    assert "__end__" in targets


def test_the_checkpointer_saves_the_run() -> None:
    saver = InMemorySaver()
    ports = fake_ports()
    app = build_graph(ports, SKELETON_POLICY, saver)
    config = {"configurable": {"thread_id": "cp-1"}}

    final = app.invoke(initial_state("cp-1", LOGIN, max_iterations=3), config=config)
    saved = app.get_state(config)

    assert saved.values["visited"] == final["visited"]
    assert saved.values["iterations"] == 3


def test_every_superstep_is_checkpointed() -> None:
    """M4-P1 resumes from the last checkpoint. One checkpoint at the end would
    mean a crash mid-run loses the entire crawl."""
    saver = InMemorySaver()
    app = build_graph(fake_ports(), SKELETON_POLICY, saver)
    config = {"configurable": {"thread_id": "cp-2"}}
    app.invoke(initial_state("cp-2", LOGIN, max_iterations=3), config=config)

    history = list(app.get_state_history(config))
    assert len(history) > 3


def test_state_survives_the_checkpoint_round_trip() -> None:
    """The frontier holds dataclasses. If they did not serialize, resume would
    come back with an empty frontier and call the run complete."""
    saver = InMemorySaver()
    app = build_graph(fake_ports(), SKELETON_POLICY, saver)
    config = {"configurable": {"thread_id": "cp-3"}}
    app.invoke(initial_state("cp-3", LOGIN, max_iterations=2), config=config)

    frontier = app.get_state(config).values["frontier"]
    assert frontier
    assert all(hasattr(item.action, "action_id") for item in frontier)


def test_each_thread_keeps_its_own_checkpoint() -> None:
    saver = InMemorySaver()
    app = build_graph(fake_ports(), SKELETON_POLICY, saver)
    for thread in ("a", "b"):
        app.invoke(
            initial_state(thread, LOGIN, max_iterations=2),
            config={"configurable": {"thread_id": thread}},
        )

    a = app.get_state({"configurable": {"thread_id": "a"}}).values
    b = app.get_state({"configurable": {"thread_id": "b"}}).values
    assert a["run_id"] == "a"
    assert b["run_id"] == "b"


def test_two_runs_over_one_graph_port_share_the_visited_set() -> None:
    """Surprising, correct, and worth pinning.

    The checkpointer isolates *graph state* per `thread_id`, but the ports are
    closed over at compile time — so a second run against the same `GraphPort`
    inherits the first run's claimed pairs and explores somewhere else instead of
    repeating it.

    That is exactly right for resume, and exactly wrong for "run the audit twice
    independently". M4-P1 needs either a fresh GraphPort or a run-scoped
    namespace in Track D's store; a new `thread_id` alone will not do it.
    """
    saver = InMemorySaver()
    ports = fake_ports()
    app = build_graph(ports, SKELETON_POLICY, saver)

    first = app.invoke(
        initial_state("a", LOGIN, max_iterations=2), config={"configurable": {"thread_id": "a"}}
    )
    second = app.invoke(
        initial_state("b", LOGIN, max_iterations=2), config={"configurable": {"thread_id": "b"}}
    )

    assert first["visited"][0] == second["visited"][0]  # same seed
    assert first["visited"][1] != second["visited"][1]  # different second state

    # A genuinely independent run needs a fresh port, not just a fresh thread.
    third = build_graph(fake_ports(), SKELETON_POLICY, InMemorySaver()).invoke(
        initial_state("c", LOGIN, max_iterations=2), config={"configurable": {"thread_id": "c"}}
    )
    assert third["visited"] == first["visited"]


def test_an_empty_policy_finds_nothing_but_still_explores() -> None:
    ports = fake_ports()
    final = run(ports, policy=ExpectationSet())
    assert final["violations"] == []
    assert len(final["visited"]) == 3
