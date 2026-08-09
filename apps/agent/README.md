# `apps/agent` — the StateScout agent

One Python package, five modules, four owners. The module boundary *is* the
ownership boundary: nobody edits a module they do not own. Cross-module calls go
through the typed interfaces in [`contracts.py`](./contracts.py), never through
direct imports of another module's internals.

| Module | Owner | Responsibility |
| --- | --- | --- |
| [`crawler/`](./crawler) | Track A | Playwright capture (DOM, AX tree, screenshot) + action execution |
| [`orchestrator/`](./orchestrator) | Track B | LangGraph loop, BFS exploration, policy pipeline, robustness |
| [`perception/`](./perception) | Track C | VLM provider interface, Semantic UI Map extraction |
| [`negation/`](./negation) | Track C | Negation engine — `S ∩ C` + cross-check |
| [`graph/`](./graph) | Track D | State fingerprinting, hash dedup, Neo4j persistence |

## The three contracts

The orchestrator is a *consumer* of three interfaces. They are frozen after
team review; a change to any of them is a cross-track decision, not a local one.

1. **Capture** (Track A) — `capture(url_or_action) -> {dom, ax_tree, screenshot_path, url}`
2. **Perception** (Track C) — `analyze(bundle, role) -> SemanticUIMap`, `audit(S_current, C_negative) -> list[Violation]`
3. **Persistence** (Track D) — `fingerprint(bundle) -> str`, `is_visited(state_id, action_id) -> bool`, `persist_state/edge/violation(...)`

Until the real implementations land, every track codes against
`orchestrator/fakes.py`. That is what lets four people work in parallel.

## Commands

```bash
uv run pytest                  # unit + integration
uv run ruff check apps/agent
uv run mypy apps/agent
```
