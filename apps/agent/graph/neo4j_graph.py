"""The orchestrator's `GraphPort` — Track D.

This is the production stand-in for `orchestrator/fakes.py::FakeGraph`: a
no-argument constructor, the same `GraphPort` surface, the same observable
behaviour, so a loop that passes the Track B suite also passes against Neo4j +
Redis (`tests/unit/graph/test_neo4j_graph.py` runs the real loop to prove it).

`apps.agent.orchestrator.deps.live_ports` will pick it up via
``from apps.agent.graph import Neo4jGraph`` once Track B clears the three
``# type: ignore[attr-defined]`` placeholders in that file for live mode — see
``apps/agent/graph/__init__.py`` for why the re-export waits for that PR.

Why this exists instead of exposing `GraphStore` directly
--------------------------------------------------------
`GraphStore` (Neo4j) and `VisitedCache` (Redis) are the two raw stores Track D
owns. Neither is, on its own, the `GraphPort` the orchestrator needs. This class
is a thin adapter: every method delegates, and the only thing it adds is *which*
store each call goes to and the per-run `scan_id`.

* **The visited set belongs in Redis, not Neo4j.** ADR-001 decision 3 and
  handbook §3 both say the `(state_id, action_id)` loop-prevention check is a
  hot-path O(1) lookup — a Neo4j round-trip per candidate is exactly what Redis
  is there to avoid. So `is_visited` / `mark_visited` delegate to `VisitedCache`.

* **Persistence goes to `GraphStore`, scoped to this run.** `persist_state`
  passes `scan_id` so the node is linked into the run's PolicyContext
  (`:CONTAINS`); `GraphStore` also handles the orchestrator's call order (an edge
  written before its destination node — it MERGEs endpoints, `persist_state`
  fills the stub, `depth` first-write-wins via `coalesce`).

`fingerprint`, `persist_violation`, and connection lifecycle delegate unchanged.

Run scoping
-----------
Each instance owns one crawl. `scan_id` (an explicit argument, else
``STATESCOUT_SCAN_ID``, else a generated id) namespaces this run's Redis keys so
two concurrent crawls never share a visited set. Threading Track B's `run_id`
in here is what a Month 4 checkpoint-resume would need; until `deps.py` passes
one, a generated id per process is correct.
"""

from __future__ import annotations

import os
import uuid
from typing import TYPE_CHECKING

from apps.agent.contracts import CaptureBundle, StateEdge, StateNode, Violation
from apps.agent.graph.cache import VisitedCache
from apps.agent.graph.graph_store import GraphStore

if TYPE_CHECKING:
    from apps.agent.contracts import GraphPort

__all__ = ["Neo4jGraph"]


class Neo4jGraph:
    """`GraphPort` over Neo4j (persistence) + Redis (the visited set)."""

    def __init__(
        self,
        scan_id: str | None = None,
        *,
        store: GraphStore | None = None,
        visited: VisitedCache | None = None,
    ) -> None:
        self.scan_id = scan_id or os.getenv("STATESCOUT_SCAN_ID") or f"run-{uuid.uuid4().hex[:12]}"
        self._store = store if store is not None else GraphStore()
        self._visited = visited if visited is not None else VisitedCache(self.scan_id)
        # Fail fast the way GraphStore does for Neo4j: a crawl cannot start
        # without the visited set.
        self._visited.r.ping()

    # -- fingerprinting (delegated) -------------------------------------------

    def fingerprint(self, bundle: CaptureBundle) -> str:
        return self._store.fingerprint(bundle)

    # -- visited set (Redis) ------------------------------------------------

    def is_visited(self, state_id: str, action_id: str) -> bool:
        return self._visited.is_visited(state_id, action_id)

    def mark_visited(self, state_id: str, action_id: str) -> None:
        self._visited.mark_visited(state_id, action_id)

    # -- persistence (Neo4j, via GraphStore) -------------------------------

    def persist_state(self, state: StateNode) -> None:
        self._store.persist_state(state, scan_id=self.scan_id)

    def persist_edge(self, edge: StateEdge) -> None:
        self._store.persist_edge(edge)

    def persist_violation(self, violation: Violation) -> None:
        self._store.persist_violation(violation)

    # -- lifecycle --------------------------------------------------------

    def close(self) -> None:
        """Release the Neo4j driver. Safe to call twice."""
        self._store.close()


if TYPE_CHECKING:
    # Structural conformance, checked by mypy at zero runtime cost.
    def _assert_graphport(g: Neo4jGraph) -> GraphPort:
        return g
