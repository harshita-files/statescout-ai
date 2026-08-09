---
name: orchestrator-conventions
description: StateScout orchestrator design conventions. Use whenever writing or modifying LangGraph nodes, edges, state schemas, or the exploration loop in apps/agent/orchestrator/.
---

# Orchestrator conventions

## State

- **One** `TypedDict` state schema, defined once in `orchestrator/state.py`.
- Nodes take state and return **partial updates** — never mutate in place, never
  reach for a module-level global.
- Anything a node needs that is not state is a dependency, and dependencies are
  injected (below).

## Nodes

- Nodes are **pure with respect to I/O**. Every crawler, VLM, and graph call goes
  through the injected ports object (`orchestrator/deps.py`), never an imported
  client. This is the single decision that makes the loop testable with fakes.
- A node does one thing. If you are writing "and then" in the docstring, it is
  two nodes.

## Edges

- Conditional edges return one of the string literals `"clean"`, `"violated"`,
  `"terminal"`. Nothing else. Map them explicitly in `build_graph()` — no
  computed edge names.

## The frontier

- A deque of `(state_id, action)` pairs.
- An action is enqueued **only after** the visited-set check
  (`GraphPort.is_visited(state_id, action_id)`).
- Every dequeue either executes the action or logs why it was skipped. Silent
  drops are bugs, and they are the kind you find three weeks later.

## The graph

- **Cycles are preserved.** The exploration graph is cyclic; a back-edge is data.
- Edges are **always** persisted.
- Deduplication applies to **node creation only**, keyed by fingerprint.

## Durability

- Checkpoint after every completed iteration via the LangGraph checkpointer.
- The run must be resumable from the last checkpoint with the frontier and the
  visited set intact, and must not re-execute the last completed action.

## Observability

- Every run gets a `run_id`.
- Every log line is structured JSON carrying `run_id`, `node`, `state_id`.
- No `print()` anywhere in the module.
- Redact anything resembling a credential before it reaches a log or a manifest.

## Configuration

- Depth limit, max states, rate caps, checkpoint directory, and the `run_id`
  strategy all come from `orchestrator/config.py` (pydantic-settings).
- Environment always overrides defaults. Nothing is hardcoded at a call site.

## Testing

- Failing test first. Watch it fail for the *expected* reason, then implement.
- Unit tests use `orchestrator/fakes.py` — no browser, no model, no database.
- A behavior described in a docstring but not asserted in a test does not exist.
