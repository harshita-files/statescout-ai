"""LangGraph proof of concept (M1-P4).

A compiled `StateGraph` with the four nodes the real orchestrator will keep —
Scan, Reason, Act, Observe — one conditional edge, and an in-memory checkpointer.
It is a **scaffold**: it proves the shape compiles, cycles, and checkpoints. The
real exploration policy is M2-P1 (`explore.py`) and M2-P2 (`graph_runner.py`).

    START -> scan -> reason --clean----> act -> observe --+
                       |  \\--violated--^                  |
                       |                                   |
                       \\--terminal--> END      scan <------+

Node responsibilities
---------------------
scan     fingerprint, persist the node, persist the edge from the previous
         state, enqueue this state's unvisited actions
reason   analyze, audit, persist violations, route
act      claim the pair, execute the action, produce the next capture
observe  promote the capture and close the loop. Thin today; it is where
         M2-P3 puts the rate-limit wait and M4 puts checkpoint metadata.

`clean` and `violated` both route to `act` today — a violation does not stop the
crawl, because coverage is the point. The branch exists because Month 3's policy
gate and Month 4's stop signal make them diverge, and because collapsing it to a
boolean would lose `terminal`.

Known limitation, and it is the real M2-P1 problem
--------------------------------------------------
`act` pops the most recent frontier entry **belonging to the current state**, so
this walks depth-first. True BFS pops the oldest entry globally, which will
usually name an action on a page the browser is no longer sitting on. Breadth
therefore requires either replaying a path from the seed or a crawler that can
re-navigate to an arbitrary state — a decision this scaffold deliberately does
not make. See `explore.py`.
"""

from __future__ import annotations

from typing import Literal

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from apps.agent.contracts import ActionError, ExpectationSet, StateEdge, StateNode
from apps.agent.orchestrator.deps import Ports
from apps.agent.orchestrator.state import ExplorationState, PendingAction

__all__ = ["Route", "build_graph"]

Route = Literal["clean", "violated", "terminal"]


def build_graph(
    ports: Ports,
    policy: ExpectationSet,
    checkpointer: InMemorySaver | None = None,
) -> CompiledStateGraph[ExplorationState, None, ExplorationState, ExplorationState]:
    """Compile the loop.

    Ports and policy are closed over rather than imported, which is the whole
    reason these nodes are testable. `policy` is a parameter and not a module
    constant because M3-P2 replaces the hardcoded clause with a parsed one, and
    a constant here would become an import the policy pipeline has to fight.
    """

    def scan(state: ExplorationState) -> dict[str, object]:
        bundle = state["current_bundle"] or ports.crawler.open(state["seed_url"])
        state_id = ports.graph.fingerprint(bundle)

        ports.graph.persist_state(
            StateNode(
                state_id=state_id,
                url=bundle.url,
                role=state["role"],
                depth=state["depth"],
                title=bundle.title,
                screenshot_path=bundle.screenshot_path,
            )
        )

        previous = state["previous_state_id"]
        action = state["last_action"]
        if previous is not None and action is not None:
            ports.graph.persist_edge(
                StateEdge(
                    from_state_id=previous,
                    to_state_id=state_id,
                    action_id=action.action_id,
                    label=action.label,
                    # A cycle. Recorded, never pruned.
                    is_back_edge=state_id in state["visited"],
                )
            )

        frontier = list(state["frontier"])
        if state["depth"] < state["depth_limit"]:
            queued = {(item.from_state_id, item.action.action_id) for item in frontier}
            for candidate in ports.crawler.enumerate_actions(bundle):
                pair = (state_id, candidate.action_id)
                if pair in queued or ports.graph.is_visited(*pair):
                    continue
                frontier.append(PendingAction(state_id, candidate, state["depth"] + 1))

        return {
            "current_bundle": bundle,
            "current_state_id": state_id,
            "visited": [*state["visited"], state_id],
            # An iteration is one state scanned. Counting here rather than in
            # `observe` means `max_iterations=3` yields exactly three scanned
            # states, instead of three act/observe cycles plus a fourth scan.
            "iterations": state["iterations"] + 1,
            "frontier": frontier,
            "previous_state_id": None,
            "last_action": None,
        }

    def reason(state: ExplorationState) -> dict[str, object]:
        bundle = state["current_bundle"]
        assert bundle is not None  # scan always sets it
        ui_map = ports.perception.analyze(bundle, state["role"])
        found = ports.perception.audit(ui_map, policy)
        for violation in found:
            ports.graph.persist_violation(violation)

        return {
            "violations": [*state["violations"], *found],
            "verdict": "violated" if found else "clean",
        }

    def route(state: ExplorationState) -> Route:
        """The one conditional edge. Terminal wins over any verdict."""
        if state["iterations"] >= state["max_iterations"]:
            return "terminal"
        if _next_index(state) is None:
            return "terminal"
        return "violated" if state["verdict"] == "violated" else "clean"

    def act(state: ExplorationState) -> dict[str, object]:
        index = _next_index(state)
        assert index is not None  # route() checked
        frontier = list(state["frontier"])
        item = frontier.pop(index)

        # ADR-001 decision 3: claim before executing. At-most-once against an
        # application that is probably not idempotent.
        ports.graph.mark_visited(item.from_state_id, item.action.action_id)

        try:
            next_bundle = ports.crawler.act(item.action)
        except ActionError as exc:
            # Never a silent drop: the pair stays claimed and the skip is recorded.
            return {
                "frontier": frontier,
                "skipped": [*state["skipped"], f"{item.action.action_id}: {exc}"],
                "next_bundle": state["current_bundle"],
            }

        return {
            "frontier": frontier,
            "next_bundle": next_bundle,
            "previous_state_id": item.from_state_id,
            "last_action": item.action,
            "depth": item.depth,
        }

    def observe(state: ExplorationState) -> dict[str, object]:
        return {"current_bundle": state["next_bundle"], "next_bundle": None}

    graph: StateGraph[ExplorationState, None, ExplorationState, ExplorationState] = StateGraph(
        ExplorationState
    )
    graph.add_node("scan", scan)
    graph.add_node("reason", reason)
    graph.add_node("act", act)
    graph.add_node("observe", observe)

    graph.add_edge(START, "scan")
    graph.add_edge("scan", "reason")
    graph.add_conditional_edges(
        "reason",
        route,
        # Mapped explicitly. A computed edge name is a runtime failure that
        # compiles fine.
        {"clean": "act", "violated": "act", "terminal": END},
    )
    graph.add_edge("act", "observe")
    graph.add_edge("observe", "scan")

    return graph.compile(checkpointer=checkpointer or InMemorySaver())


def _next_index(state: ExplorationState) -> int | None:
    """Index of the most recent frontier entry valid from the current state.

    An index rather than the entry itself, so removal survives a checkpoint round
    trip — after deserialization the object in the list is a different instance
    and identity comparison would silently remove nothing.

    See the module docstring on why "most recent" makes this depth-first, and why
    breadth is M2-P1's problem rather than this scaffold's.
    """
    current = state["current_state_id"]
    for index in range(len(state["frontier"]) - 1, -1, -1):
        if state["frontier"][index].from_state_id == current:
            return index
    return None
