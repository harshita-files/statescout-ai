# `orchestrator/` — Track B

The brain. Drives the Scan → Reason → Act → Observe loop, decides where to go
next, decides when to stop, and turns a QA engineer's English policy into
machine-checkable constraints.

## What is here

| File | Milestone | What it is |
| --- | --- | --- |
| `state.py` | M2-P2 | The one `TypedDict`, plus frontier entries and results |
| `contracts.py` (in `../`) | M1-P1 | The frozen cross-track interfaces |
| `fakes.py` | M1-P2 | In-memory ports — no browser, no model, no database |
| `deps.py` | M1-P3 | Injected ports container; where throttling is wired in |
| `runlog.py` | M1-P3 | Structured JSON logging, one object per line |
| `config.py` | M2-P3 | `pydantic-settings`: depth, state cap, rate, run-id strategy |
| `ratelimit.py` | M2-P3 | Token bucket + `ThrottledPerception` |
| `explore.py` | M2-P1 | Plain-Python BFS. **Deprecated** — kept as the parity oracle |
| `graph_runner.py` | M2-P2 | The LangGraph port. **This is what runs.** |
| `poc.py` | M1-P4 | The M1 scaffold, superseded by `graph_runner.py` |

Still to come: `policy.py` (M3-P2), graceful stop and resume (M4-P1), the run
manifest (M4-P2).

## Running a crawl

```python
from apps.agent.orchestrator.config import OrchestratorConfig
from apps.agent.orchestrator.deps import build_ports
from apps.agent.orchestrator.graph_runner import explore

config = OrchestratorConfig()  # env-overridable, STATESCOUT_*
ports = build_ports(config)  # live=True once A/C/D land
result = explore(ports, "http://localhost:4173/index.html", policy, config)

print(result.termination_reason, result.states, len(result.violations))
```

One state, end to end, from the shell:

```bash
uv run python -m apps.agent.skeleton --fake      # exit 1 on a violation
```

## Two implementations, one behaviour

`explore.py` and `graph_runner.py` are the same loop. Every test in
`tests/unit/orchestrator/test_explore.py` runs against both, so a change to one
without the other is a failing test rather than a slow divergence. The plain
version is readable in one sitting and needs no reasoning about superstep
scheduling; the LangGraph version is the one that can be checkpointed and
resumed, which is why it is the one that ships.

## Invariants this module must never break

- **Cycles are preserved.** The exploration graph is a cyclic directed graph, not
  a DAG. Loop prevention is a visited `(state_id, action_id)` set — never a
  refusal to traverse a back-edge.
- **Nodes are pure w.r.t. I/O.** Every crawler / VLM / graph call goes through the
  injected ports object. No module-level clients, no hidden globals.
- **No silent drops.** Every dequeued action either executes or records why it was
  skipped, with a reason a human can act on.
- **Dedup applies to node creation only.** Edges are always persisted.
- **Claim before executing.** `mark_visited` runs *before* the action, so a crash
  cannot re-fire something the application under test is not idempotent about.
- **Only navigation is replayable.** Reaching a queued action re-runs its path;
  paths through a side-effecting action are skipped instead.
- **Config is not state.** Limits live in `OrchestratorConfig`, never in the
  checkpointed state, so a resumed run cannot silently run under different rules.

See [`.claude/skills/orchestrator-conventions`](../../../.claude/skills/orchestrator-conventions)
for the full conventions, and [`docs/track-b-progress.md`](../../../docs/track-b-progress.md)
for status and open cross-track questions.
