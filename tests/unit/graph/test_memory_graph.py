from __future__ import annotations

from apps.agent.contracts import CaptureBundle, StateEdge, StateNode, Violation
from apps.agent.graph.memory_graph import MemoryGraph
from apps.agent.orchestrator.deps import live_ports


def test_cycle_preserved_and_export() -> None:
    g = MemoryGraph()
    g.persist_state(StateNode("a", "u", "guest", 0))
    g.persist_state(StateNode("a", "u", "guest", 5))  # first write wins
    g.persist_state(StateNode("b", "u2", "guest", 1))
    g.persist_edge(StateEdge("a", "b", "x"))
    g.persist_edge(StateEdge("b", "a", "y", is_back_edge=True))
    g.persist_violation(Violation("v", "a", "e", "forbidden", "high", "why"))
    out = g.export()
    assert {n["state_id"]: n["depth"] for n in out["nodes"]} == {"a": 0, "b": 1}
    assert [e["is_back_edge"] for e in out["edges"]] == [False, True]
    assert out["violations"][0]["violation_id"] == "v"


def test_visited_and_fingerprint() -> None:
    g = MemoryGraph()
    assert not g.is_visited("a", "x")
    g.mark_visited("a", "x")
    g.mark_visited("a", "x")
    assert g.is_visited("a", "x")
    bun = CaptureBundle(url="http://a/", dom="<p>hi</p>", ax_tree={})
    assert g.fingerprint(bun) == g.fingerprint(bun) and len(g.fingerprint(bun)) == 64


def test_live_ports_memory_and_auto(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import apps.agent.perception as perc

    monkeypatch.setattr(perc, "VLMPerception", lambda: object(), raising=False)
    assert isinstance(live_ports(graph="memory").graph, MemoryGraph)
    import apps.agent.graph.neo4j_graph as ng

    def boom() -> None:
        raise ConnectionError

    monkeypatch.setattr(ng, "Neo4jGraph", boom)
    assert isinstance(live_ports(graph="auto").graph, MemoryGraph)
