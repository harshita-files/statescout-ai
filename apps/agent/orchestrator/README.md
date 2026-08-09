# `orchestrator/` — Track B

The brain. Drives the Scan → Reason → Act → Observe loop, decides where to go
next, decides when to stop, and turns a QA engineer's English policy into
machine-checkable constraints.

## Planned surface

| File | Milestone | What it is |
| --- | --- | --- |
| `fakes.py` | M1-P2 | In-memory `CrawlerPort` / `PerceptionPort` / `GraphPort` so the loop is testable with no browser, no model, no database |
| `poc.py` | M1-P4 | Minimal compiled LangGraph — four nodes, one conditional edge, in-memory checkpointer |
| `config.py` | M2-P3 | `pydantic-settings` config: depth limit, max states, perception rate cap, checkpoint dir |
| `explore.py` | M2-P1 | Plain-Python BFS exploration loop — the reference implementation for the LangGraph port |
| `graph_runner.py` | M2-P2 | The LangGraph port of `explore.py`, held to test parity |
| `policy.py` | M3-P2 | English policy → `InterpretedPolicy`, FR-04/FR-16 confirmation gate |
| `state.py` | M2-P2 | The single `TypedDict` state schema |
| `deps.py` | M1-P4 | Injected ports container — the reason nodes are testable |

## Invariants this module must never break

- **Cycles are preserved.** The exploration graph is a cyclic directed graph, not
  a DAG. Loop prevention is done with a visited `(state_id, action_id)` set — never
  by refusing to traverse a back-edge.
- **Nodes are pure w.r.t. I/O.** Every crawler / VLM / graph call goes through the
  injected ports object. No module-level clients, no hidden globals.
- **No silent drops.** Every dequeued action either executes or logs why it was
  skipped.
- **Dedup applies to node creation only.** Edges are always persisted.

See [`.claude/skills/orchestrator-conventions`](../../../.claude/skills/orchestrator-conventions)
for the full conventions.
