# Orchestrator

Root `CLAUDE.md` still applies.

## Rules

- The ownership boundary is lifted: one maintainer owns every module now. Cross-module
  changes are fine, but keep `apps/agent/contracts.py` changes **additive** (new types/ports,
  no edits to existing ones) so the TS mirror and tests stay valid.
- No new dependencies without asking first.

## Design invariants

- One `TypedDict` state schema, defined once in `orchestrator/state.py`. Nodes
  take state and return **partial updates**. No hidden globals.
- Nodes are pure w.r.t. I/O: every crawler / VLM / graph call goes through the
  injected ports object (`orchestrator/deps.py`), never an imported client. This
  is what makes nodes testable with fakes.
- Conditional edges return one of the literals `"clean"`, `"violated"`,
  `"terminal"`. Map them explicitly in `build_graph()`.
- The frontier is a deque of `(state_id, action)` pairs. An action is enqueued
  **only** after the visited-set check. Every dequeue either executes or logs why
  it was skipped — silent drops are bugs.
- **Cycles are preserved.** Edges are always persisted; dedup applies to node
  creation only, by fingerprint.
- Checkpoint after every completed iteration via the LangGraph checkpointer. The
  run must be resumable from the last checkpoint.
- Every run gets a `run_id`. Every log line is structured JSON with
  `run_id, node, state_id`. No `print()`.
- Config (depth limit, rate caps) comes from `orchestrator/config.py`
  (pydantic-settings), never hardcoded.

## Habits

- Failing test first, then implement. Run the `test-runner` subagent after every
  change; never merge red.
- Ask the `langgraph-scout` subagent before writing LangGraph API calls — do not
  guess method names from memory.
- Run the `fresh-eyes-reviewer` subagent before every PR.
