# Getting started

## Prerequisites

- [uv](https://docs.astral.sh/uv/) for the Python toolchain (Python 3.11+)
- [Bun](https://bun.sh) for the TypeScript workspaces
- Docker, for Neo4j and Redis

## Install

```bash
git clone https://github.com/harshita-files/statescout-ai.git
cd statescout-ai
cp .env.example .env            # fill in provider keys

uv sync --all-groups            # Python toolchain
uv run playwright install chromium
bun install                     # TypeScript workspaces

docker compose -f infra/docker-compose.yml up -d   # Neo4j :7687, Redis :6379
```

## Everyday commands

| Task | Command |
| --- | --- |
| Python tests | `uv run pytest` |
| Lint | `uv run ruff check apps services tests` |
| Types | `uv run mypy apps/agent` |
| TypeScript tests | `bun test tests/unit` |
| TypeScript types | `bun run typecheck` |
| Services up / down | `docker compose -f infra/docker-compose.yml up -d` / `down` |
| Offline demo | `./demo.sh` |
| Reporting API | `uv run uvicorn services.api.main:app --reload` |
| This documentation site | `uv run --group docs mkdocs serve` |

## Repository layout

```
statescout-ai/
├── apps/
│   ├── vscode-extension/   # TypeScript - QA engineer UI              (Track A)
│   └── agent/              # Python - LangGraph + Playwright + VLM
│       ├── contracts.py    # frozen cross-track interfaces
│       ├── crawler/        # Playwright capture + actions              (A)
│       ├── orchestrator/   # LangGraph loop + conditional edges        (B)
│       ├── perception/     # VLM provider + semantic UI map            (C)
│       ├── negation/       # negation engine                           (C)
│       └── graph/          # fingerprint + dedup + Neo4j + Redis       (D)
├── services/api/           # FastAPI reporting backend                 (D)
├── packages/shared-types/  # TypeScript API contract types             (A)
├── research/               # InternVL fine-tuning + benchmark          (C)
├── infra/                  # Docker Compose: Neo4j + Redis             (D)
├── test-apps/              # deliberately broken ground-truth apps
├── tests/                  # unit / integration / e2e
└── docs/                   # design records, data model, this site
```

## Contributing

Branches are `<type>/<TRACK>-<slug>` - for example `feature/B-bfs-loop`. Pull
requests target `staging`; only `staging` merges into `main`. Commits follow
[Conventional Commits](https://www.conventionalcommits.org/) with the module as
scope, e.g. `feat(orchestrator): add BFS frontier`. Each track writes only its own
directories; cross-track calls go through `apps/agent/contracts.py`.
