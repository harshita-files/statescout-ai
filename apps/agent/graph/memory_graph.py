"""In-memory `GraphPort` for runs without Neo4j/Redis.

Cyclic edges are preserved (append-only, never pruned); fingerprints come from
`apps.agent.graph.fingerprint`. `export()` yields a JSON-friendly graph.
"""

from __future__ import annotations

import threading
from dataclasses import asdict
from typing import Any

from apps.agent.contracts import CaptureBundle, StateEdge, StateNode, Violation
from apps.agent.graph.fingerprint import fingerprint_bundle

__all__ = ["MemoryGraph"]


class MemoryGraph:
    def __init__(self) -> None:
        self.visited: set[tuple[str, str]] = set()
        self.states: dict[str, StateNode] = {}
        self.edges: list[StateEdge] = []
        self.violations: list[Violation] = []
        self._lock = threading.Lock()

    def fingerprint(self, bundle: CaptureBundle) -> str:
        return fingerprint_bundle(bundle)

    def is_visited(self, state_id: str, action_id: str) -> bool:
        return (state_id, action_id) in self.visited

    def mark_visited(self, state_id: str, action_id: str) -> None:
        with self._lock:
            self.visited.add((state_id, action_id))

    def persist_state(self, state: StateNode) -> None:
        with self._lock:
            self.states.setdefault(state.state_id, state)  # depth: first write wins

    def persist_edge(self, edge: StateEdge) -> None:
        with self._lock:
            self.edges.append(edge)

    def persist_violation(self, violation: Violation) -> None:
        with self._lock:
            self.violations.append(violation)

    def export(self) -> dict[str, Any]:
        with self._lock:
            return {
                "nodes": [asdict(s) for s in self.states.values()],
                "edges": [asdict(e) for e in self.edges],
                "violations": [asdict(v) for v in self.violations],
            }

    def close(self) -> None:
        return None
