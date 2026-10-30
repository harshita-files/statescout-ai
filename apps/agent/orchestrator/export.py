"""Graph export for a UI to draw. Cycles, self-loops and back-edges are kept as-is.

Edges come from the run's empirical transition counts, one edge per observed
`(source, action, target)`, with its probability. Nothing is pruned or deduplicated
across actions, so a self-loop (`source == target`) is an ordinary edge.
"""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from apps.agent.orchestrator.dynamic import DynamicStats
from apps.agent.orchestrator.state import ExplorationResult

__all__ = ["export_graph"]


def export_graph(result: ExplorationResult, dynamic: DynamicStats | None) -> dict[str, Any]:
    stats = dynamic if dynamic is not None else result.dynamic
    visits = Counter(result.order)
    violations = Counter(v.state_id for v in result.violations)
    meta = stats.nodes if stats is not None else {}

    ids = list(dict.fromkeys([*result.order, *meta]))
    edges: list[dict[str, Any]] = []
    if stats is not None:
        for key, counts in stats.transitions.items():
            source, action = json.loads(key)
            probs = stats.transition_probabilities.get(key, {})
            total = sum(counts.values())
            for target, count in counts.items():
                edges.append(
                    {
                        "source": source,
                        "target": target,
                        "action": action,
                        "label": stats.edge_labels.get(key, action),
                        "probability": probs.get(target, count / total),
                        "count": count,
                    }
                )
                for node in (source, target):
                    if node not in ids:
                        ids.append(node)

    nodes = [
        {
            "id": sid,
            "url": meta.get(sid, {}).get("url", ""),
            "title": meta.get(sid, {}).get("title", ""),
            "depth": meta.get(sid, {}).get("depth", 0),
            "visits": visits.get(sid, 0),
            "violation_count": violations.get(sid, 0),
        }
        for sid in ids
    ]
    return {
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "states": result.states,
            "edges": result.edges,
            "visited_pairs": result.visited_pairs,
            "replays": result.replays,
            "replay_steps": result.replay_steps,
            "skipped": len(result.skipped),
            "termination_reason": result.termination_reason,
            "cycles": sum(1 for e in edges if e["source"] == e["target"]),
            "masks": list(stats.masks) if stats is not None else [],
        },
    }
