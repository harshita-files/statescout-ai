# StateScout AI

Autonomous web-UI auditor. A LangGraph orchestrator drives a Playwright crawler,
a VLM perceives each UI state, a negation engine flags states that violate a
natural-language policy. The exploration graph is persisted in Neo4j; Redis
caches visited pairs.

## Stack & commands

- Python ≥3.11 via uv (local venv is 3.13) · TypeScript via Bun
- Test: `uv run pytest` · `bun test tests/unit`
- Lint: `uv run ruff check apps services tests` · Types: `uv run mypy apps/agent`
- Services: `docker compose -f infra/docker-compose.yml up -d` (Neo4j :7687, Redis :6379)

## Ownership — the module boundary is the ownership boundary

| Path | Track |
| --- | --- |
| `apps/agent/crawler/`, `apps/vscode-extension/`, `packages/shared-types/` | A |
| `apps/agent/orchestrator/`, `apps/agent/skeleton.py` | B |
| `apps/agent/perception/`, `apps/agent/negation/`, `research/` | C |
| `apps/agent/graph/`, `services/api/`, `infra/` | D |

Cross-module calls go through the typed interfaces in `apps/agent/contracts.py`.
Never import another track's internals directly. A `PreToolUse` hook enforces
this — see `.claude/hooks/README.md`.

## Project-wide rules

- **The exploration graph is CYCLIC.** Never call it a DAG, never prune a
  back-edge to make it acyclic. Loop prevention is a visited `(state_id, action_id)`
  set, nothing else.
- `contracts.py` is the frozen interface. If a contract seems wrong, STOP and
  raise it with the owning track — do not adjust it to make your code work.
- TDD: write the failing test first, watch it fail, then implement.
- Conventional commits, module as scope: `feat(orchestrator): add BFS frontier`.
- Branches `<type>/<TRACK>-<slug>` (`feature/B-bfs-loop`). PRs to `staging`;
  only `staging` merges to `main`. Never commit to `main` directly.
- No new dependencies without asking first.
- Never print secrets or anything resembling a credential into logs (NFR-11).

Track-specific rules live in that module's `CLAUDE.md` and load when you work there.
