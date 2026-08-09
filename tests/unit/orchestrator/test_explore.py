"""The exploration loop (M2-P1), run against every implementation of it.

The three definition-of-done tests come first and are marked as such. Everything
after them is the termination reasoning made executable: the loop's job is to
finish, and every way it could fail to finish deserves a test that would catch it.

Written before `explore.py` existed, and watched fail.

Parity (M2-P2)
--------------
The `run` fixture is parameterised over both implementations, so every assertion
below executes twice — once against the plain-Python reference and once against
the compiled LangGraph port. That is what makes "behaviour must be test-identical"
a fact rather than a claim: there is no separate LangGraph suite that could drift,
and a divergence fails the test that describes the behaviour, naming the
implementation that broke it.

Add a test here and both implementations must satisfy it. That is the point.
"""

from __future__ import annotations

from typing import Protocol

import pytest

from apps.agent.contracts import ActionError, ExpectationSet, NavigationError
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
from apps.agent.orchestrator.state import ExplorationResult
from apps.agent.skeleton import SKELETON_POLICY

LOGIN = "http://fake.test/login"

#: Every implementation of the same loop. Both must satisfy every test below.
IMPLEMENTATIONS = {
    "reference": reference.explore,
    "langgraph": graph_runner.explore,
}


def config(**overrides: object) -> OrchestratorConfig:
    defaults: dict[str, object] = {"perception_rate_per_min": 0}
    return OrchestratorConfig(_env_file=None, **{**defaults, **overrides})  # type: ignore[arg-type]


def ports_for(app: dict[str, FakePage] | None = None, *, role: str = "guest") -> Ports:
    crawler = FakeCrawler(app, role=role) if app else FakeCrawler(role=role)
    return Ports(crawler=crawler, perception=FakePerception(), graph=FakeGraph())


class Run(Protocol):
    def __call__(
        self,
        ports: Ports,
        *,
        seed: str = ...,
        policy: ExpectationSet = ...,
        **settings: object,
    ) -> ExplorationResult: ...


@pytest.fixture(params=list(IMPLEMENTATIONS), ids=list(IMPLEMENTATIONS))
def run(request: pytest.FixtureRequest) -> Run:
    """One of the two loops, behind the identical call signature."""
    implementation = IMPLEMENTATIONS[request.param]

    def _run(
        ports: Ports,
        *,
        seed: str = LOGIN,
        policy: ExpectationSet = SKELETON_POLICY,
        **settings: object,
    ) -> ExplorationResult:
        return implementation(ports, seed, policy, config(**settings), run_id="test-run")

    return _run


# ===========================================================================
# Definition of done — the three M2-P1 acceptance tests
# ===========================================================================


def test_dod_a_the_loop_terminates_on_an_app_with_cycles(run: Run) -> None:
    """(a) It stops.

    `DEFAULT_APP` has two cycles. With no iteration cap and no depth cap in play,
    the only thing that can end this run is the frontier emptying — so if the
    visited-pair check is wrong in either direction, this hangs rather than fails.
    """
    result = run(ports_for(), depth_limit=99, max_states=99)
    assert result.termination_reason == "frontier_exhausted"


def test_dod_b_every_state_action_pair_executes_exactly_once(run: Run) -> None:
    """(b) Coverage without repetition.

    Four states with 2 + 1 + 2 + 2 = 7 outgoing actions. Every pair runs once:
    fewer means coverage was silently dropped, more means the visited set leaks.
    """
    ports = ports_for()
    result = run(ports, depth_limit=99, max_states=99)
    crawler: FakeCrawler = ports.crawler  # type: ignore[assignment]
    graph: FakeGraph = ports.graph  # type: ignore[assignment]

    assert result.states == 4
    assert result.visited_pairs == 7

    # `visited_pairs` counts executions, `graph.visited` is a set of pairs. They
    # can only be equal if no pair was executed twice — that equality *is* the
    # exactly-once property, and it is what the visited-set check exists to buy.
    assert result.visited_pairs == len(graph.visited) == 7

    # `crawler.acted` is larger, and that is not a coverage failure: replay
    # re-fires navigation to get back to a state before acting on it. The gap
    # between the two numbers is the cost of breadth with one browser.
    assert len(crawler.acted) == 7 + result.replay_steps


def test_dod_c_the_login_register_cycle_records_its_back_edge(run: Run) -> None:
    """(c) The cycle is in the graph, not pruned out of it."""
    ports = ports_for()
    run(ports, depth_limit=99, max_states=99)
    graph: FakeGraph = ports.graph  # type: ignore[assignment]

    login = graph.fingerprint(FakeCrawler().open("/login"))
    register = graph.fingerprint(FakeCrawler().open("/register"))

    forward = [e for e in graph.edges if (e.from_state_id, e.to_state_id) == (login, register)]
    back = [e for e in graph.edges if (e.from_state_id, e.to_state_id) == (register, login)]

    assert len(forward) == 1
    assert len(back) == 1
    assert back[0].is_back_edge is True


# ===========================================================================
# Termination — every way the loop could fail to stop
# ===========================================================================


def test_a_self_loop_terminates(run: Run) -> None:
    """One page linking to itself. The pair check is the only thing stopping this."""
    app = {"/one": FakePage(title="One", transitions=(FakeLink(name="Refresh", to="/one"),))}
    result = run(ports_for(app), seed="/one", depth_limit=99, max_states=99)
    assert result.termination_reason == "frontier_exhausted"
    assert result.visited_pairs == 1


def test_two_interleaved_cycles_terminate(run: Run) -> None:
    """A diamond with both diagonals — every state reaches every other."""
    app = {
        "/a": FakePage(title="A", transitions=(FakeLink("to B", "/b"), FakeLink("to C", "/c"))),
        "/b": FakePage(title="B", transitions=(FakeLink("to D", "/d"), FakeLink("to A", "/a"))),
        "/c": FakePage(title="C", transitions=(FakeLink("to D", "/d"), FakeLink("to A", "/a"))),
        "/d": FakePage(title="D", transitions=(FakeLink("to B", "/b"), FakeLink("to C", "/c"))),
    }
    result = run(ports_for(app), seed="/a", depth_limit=99, max_states=99)
    assert result.termination_reason == "frontier_exhausted"
    assert result.states == 4
    assert result.visited_pairs == 8


def test_depth_limit_terminates_a_deep_chain(run: Run) -> None:
    """FR-10. A hundred-page chain, explored three deep."""
    app = {
        f"/p{i}": FakePage(title=f"P{i}", transitions=(FakeLink("next", f"/p{i + 1}"),))
        for i in range(100)
    }
    app["/p99"] = FakePage(title="P99")
    result = run(ports_for(app), seed="/p0", depth_limit=3, max_states=99)

    assert result.termination_reason == "frontier_exhausted"
    assert result.states == 4  # depths 0, 1, 2, 3


def test_depth_zero_audits_only_the_seed(run: Run) -> None:
    result = run(ports_for(), depth_limit=0, max_states=99)
    assert result.states == 1
    assert result.visited_pairs == 0


def test_max_states_stops_a_fan_out_explosion(run: Run) -> None:
    """Fifty distinct children at depth 1. `depth_limit` alone would not stop this,
    which is why both limits exist."""
    app: dict[str, FakePage] = {
        "/hub": FakePage(
            title="Hub", transitions=tuple(FakeLink(f"item {i}", f"/i{i}") for i in range(50))
        )
    }
    for i in range(50):
        app[f"/i{i}"] = FakePage(title=f"Item {i}")

    result = run(ports_for(app), seed="/hub", depth_limit=99, max_states=10)
    assert result.termination_reason == "max_states"
    assert result.states <= 10


def test_an_unstable_fingerprint_is_caught_by_max_states(run: Run) -> None:
    """The failure mode ADR-001 decision 2 is about.

    A self-loop plus a fingerprint that never repeats is the worst case: the loop
    is always already in the right state, so no replay happens and nothing
    diverges — it just walks forever discovering "new" states. `depth_limit` does
    not help, because a self-loop stays at one depth. `max_states` is the only
    thing standing between a Track D regression and an unbounded crawl.
    """
    app = {"/one": FakePage(title="One", transitions=(FakeLink(name="Refresh", to="/one"),))}
    ports = ports_for(app)
    counter = iter(range(10_000))
    ports.graph.fingerprint = lambda _bundle: f"s-{next(counter)}"  # type: ignore[method-assign]

    result = run(ports, seed="/one", depth_limit=99, max_states=8)
    assert result.termination_reason == "max_states"
    assert result.states == 8


def test_an_unstable_fingerprint_shows_up_as_replay_divergence(run: Run) -> None:
    """When a replay *is* needed, instability is caught directly and named.

    Landing somewhere other than the state a path is supposed to reach means the
    app is non-deterministic or a fingerprint is unstable. Acting anyway would
    attribute the edge to the wrong state, so the loop skips and says which two
    ids disagreed — a far better diagnostic than a run that silently stops at the
    state cap.
    """
    ports = ports_for()
    counter = iter(range(10_000))
    ports.graph.fingerprint = lambda _bundle: f"s-{next(counter)}"  # type: ignore[method-assign]

    result = run(ports, depth_limit=99, max_states=99)
    assert result.termination_reason == "frontier_exhausted"
    assert any("replay diverged" in skip.reason for skip in result.skipped)


# ===========================================================================
# Breadth, and the cost of achieving it
# ===========================================================================


def test_states_are_discovered_in_breadth_first_order(run: Run) -> None:
    """A chain of depth 3 hanging off a hub with a shallow sibling: breadth-first
    reaches the sibling before the bottom of the chain, depth-first does not."""
    app = {
        "/hub": FakePage(
            title="Hub", transitions=(FakeLink("deep", "/d1"), FakeLink("wide", "/w"))
        ),
        "/d1": FakePage(title="D1", transitions=(FakeLink("deeper", "/d2"),)),
        "/d2": FakePage(title="D2", transitions=(FakeLink("deepest", "/d3"),)),
        "/d3": FakePage(title="D3"),
        "/w": FakePage(title="W"),
    }
    ports = ports_for(app)
    result = run(ports, seed="/hub", depth_limit=99, max_states=99)
    graph: FakeGraph = ports.graph  # type: ignore[assignment]

    depths = {node.title: node.depth for node in graph.states.values()}
    assert depths == {"Hub": 0, "D1": 1, "W": 1, "D2": 2, "D3": 3}

    titles = [graph.states[state_id].title for state_id in dict.fromkeys(result.order)]
    assert titles.index("W") < titles.index("D2")


def test_reaching_a_state_replays_the_path_from_the_seed(run: Run) -> None:
    """One browser cannot act on a page it is not looking at. Breadth therefore
    costs re-navigation, and that cost should be visible rather than mysterious."""
    ports = ports_for()
    result = run(ports, depth_limit=99, max_states=99)
    crawler: FakeCrawler = ports.crawler  # type: ignore[assignment]

    assert len(crawler.opened) > 1
    assert result.replays > 0


def test_no_replay_when_already_in_the_right_state(run: Run) -> None:
    """A chain explored front to back never needs to re-navigate."""
    app = {
        "/a": FakePage(title="A", transitions=(FakeLink("next", "/b"),)),
        "/b": FakePage(title="B"),
    }
    ports = ports_for(app)
    result = run(ports, seed="/a", depth_limit=99, max_states=99)
    assert result.replays == 0


def test_a_side_effecting_action_is_never_replayed(run: Run) -> None:
    """ADR-001 decision 3 says at-most-once against a non-idempotent app. Replay
    re-fires the actions on a path, so a path containing a submit cannot be
    replayed — the subtree behind it is reported as skipped, not silently lost."""
    app = {
        "/form": FakePage(
            title="Form",
            transitions=(
                FakeLink("Submit order", "/done", role="button", kind="submit"),
                FakeLink("Help", "/help"),
            ),
        ),
        "/done": FakePage(title="Done", transitions=(FakeLink("More", "/more"),)),
        "/more": FakePage(title="More"),
        "/help": FakePage(title="Help"),
    }
    ports = ports_for(app)
    probe = FakeCrawler(app)
    submit_id = next(
        a.action_id for a in probe.enumerate_actions(probe.open("/form")) if a.kind == "submit"
    )

    result = run(ports, seed="/form", depth_limit=99, max_states=99)
    crawler: FakeCrawler = ports.crawler  # type: ignore[assignment]

    # Fired once, from the state the loop was already standing in — and never
    # again, even though /more sits behind it.
    assert crawler.acted.count(submit_id) == 1
    assert any("unreplayable" in skip.reason for skip in result.skipped)

    # The subtree behind the submit is reported unexplored, not quietly reached.
    graph: FakeGraph = ports.graph  # type: ignore[assignment]
    assert "More" not in {node.title for node in graph.states.values()}
    assert result.termination_reason == "frontier_exhausted"


# ===========================================================================
# Persistence rules
# ===========================================================================


def test_nodes_are_deduplicated_and_edges_are_not(run: Run) -> None:
    ports = ports_for()
    result = run(ports, depth_limit=99, max_states=99)
    graph: FakeGraph = ports.graph  # type: ignore[assignment]

    assert len(graph.states) == 4
    assert len(graph.edges) == result.visited_pairs
    assert len(result.order) > len(graph.states)  # states were revisited


def test_depth_is_the_depth_of_first_discovery(run: Run) -> None:
    """A cycle reaches a state again at greater depth. If the later write won,
    `depth_limit` would stop meaning anything."""
    ports = ports_for()
    run(ports, depth_limit=99, max_states=99)
    graph: FakeGraph = ports.graph  # type: ignore[assignment]
    login = graph.fingerprint(FakeCrawler().open("/login"))
    assert graph.states[login].depth == 0


def test_a_pair_is_claimed_before_the_action_runs(run: Run) -> None:
    ports = ports_for()
    result = run(ports, depth_limit=99, max_states=99)
    graph: FakeGraph = ports.graph  # type: ignore[assignment]
    assert len(graph.visited) == result.visited_pairs


def test_violations_are_found_once_per_state_not_once_per_visit(run: Run) -> None:
    """`/login` is scanned repeatedly as cycles close. Auditing it every time
    would triple-count the same finding in the report."""
    ports = ports_for()
    result = run(ports, policy=DEFAULT_POLICY, depth_limit=99, max_states=99)
    graph: FakeGraph = ports.graph  # type: ignore[assignment]

    per_state = [(v.state_id, v.expectation_id) for v in result.violations]
    assert len(per_state) == len(set(per_state))
    assert len(graph.violations) == len(per_state)


# ===========================================================================
# Failure handling
# ===========================================================================


def test_a_failed_action_is_skipped_not_dropped(monkeypatch: pytest.MonkeyPatch, run: Run) -> None:
    ports = ports_for()
    original = ports.crawler.act
    calls = {"n": 0}

    def flaky(action: object) -> object:
        calls["n"] += 1
        if calls["n"] == 2:
            raise ActionError("stale element")
        return original(action)  # type: ignore[arg-type]

    monkeypatch.setattr(ports.crawler, "act", flaky)
    result = run(ports, depth_limit=99, max_states=99)

    assert any("stale element" in skip.reason for skip in result.skipped)
    assert result.termination_reason == "frontier_exhausted"


def test_an_unreachable_seed_ends_the_run_with_an_error(run: Run) -> None:
    result = run(ports_for(), seed="/ghost")
    assert result.termination_reason == "error"
    assert result.states == 0


def test_a_navigation_failure_mid_run_is_skipped(monkeypatch: pytest.MonkeyPatch, run: Run) -> None:
    """A dead link is one lost subtree, not a lost run."""
    ports = ports_for()
    original = ports.crawler.act
    calls = {"n": 0}

    def flaky(action: object) -> object:
        calls["n"] += 1
        if calls["n"] == 2:
            raise NavigationError("timeout")
        return original(action)  # type: ignore[arg-type]

    monkeypatch.setattr(ports.crawler, "act", flaky)
    result = run(ports, depth_limit=99, max_states=99)
    assert any("timeout" in skip.reason for skip in result.skipped)


def test_the_crawler_is_closed_when_the_run_ends(run: Run) -> None:
    ports = ports_for()
    run(ports, depth_limit=99, max_states=99)
    crawler: FakeCrawler = ports.crawler  # type: ignore[assignment]
    assert crawler.closed


# ===========================================================================
# Determinism
# ===========================================================================


def test_two_runs_over_the_same_app_agree(run: Run) -> None:
    """A resumed run has to rebuild the same frontier as the run it resumed, so
    the traversal cannot depend on set iteration order or anything else unstable."""
    first = run(ports_for(), depth_limit=99, max_states=99)
    second = run(ports_for(), depth_limit=99, max_states=99)
    assert first.order == second.order
    assert first.visited_pairs == second.visited_pairs
