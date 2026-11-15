# StateScout AI

StateScout AI is a policy-aware UI auditing engine that autonomously explores web
applications and detects forbidden or logically invalid interface states.

It shifts automation from workflow testing to logical state verification.

**Documentation:** <https://harshita-files.github.io/statescout-ai/>

## The problem

Modern web applications rely on backend role-based access control (RBAC) to
protect sensitive actions. Frontend logic errors can still expose restricted
interface components, such as:

- admin dashboards visible to non-admin users;
- debug panels exposed in production;
- role-based rendering inconsistencies;
- unintended state transitions.

Even if backend APIs block execution, UI exposure itself can violate access
policies or compliance rules. StateScout detects such logical UI exposure
automatically.

## Core idea

Instead of validating predefined test scripts, StateScout:

1. explores the interface autonomously;
2. constructs a directed state graph of navigation paths;
3. extracts semantic information from UI states;
4. applies negation-aware policy evaluation;
5. flags forbidden or logically invalid UI states.

It focuses on *what should not exist* rather than simply verifying expected
workflows.

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
└── docs/                   # design records, data model, documentation site
```

The module boundary is the ownership boundary. Cross-module calls go through the
typed interfaces in `apps/agent/contracts.py`, never through direct imports of
another track's internals.

## Getting started

**Prerequisites:** [uv](https://docs.astral.sh/uv/), [Bun](https://bun.sh),
Docker (for Neo4j and Redis).

```bash
git clone https://github.com/harshita-files/statescout-ai.git
cd statescout-ai
cp .env.example .env            # fill in provider keys

uv sync --all-groups            # Python toolchain
uv run playwright install chromium
bun install                     # TypeScript workspaces

docker compose -f infra/docker-compose.yml up -d   # Neo4j :7687, Redis :6379
```

### Everyday commands

| Task | Command |
| --- | --- |
| Python tests | `uv run pytest` |
| Lint | `uv run ruff check apps services tests` |
| Types | `uv run mypy apps/agent` |
| TypeScript tests | `bun test tests/unit` |
| TypeScript types | `bun run typecheck` |
| Services up / down | `docker compose -f infra/docker-compose.yml up -d` / `down` |
| Offline demo | `./demo.sh` |
| Documentation site | `uv run --group docs mkdocs serve` |

## System architecture

1. **Orchestration and control** (`apps/agent/orchestrator`): session lifecycle,
   the Scan, Reason, Act, Observe loop, BFS frontier management, policy injection,
   and exploration termination.
2. **Browser interaction** (`apps/agent/crawler`): Playwright navigation, DOM
   extraction, accessibility tree parsing, screenshots.
3. **Perception and reasoning** (`apps/agent/perception`, `apps/agent/negation`):
   vision-language model (inference only), UI semantic interpretation, and
   negation-based violation detection.
4. **State and graph management** (`apps/agent/graph`): UI state fingerprinting,
   directed navigation graph construction, loop prevention via a visited
   `(state, action)` set, and state consistency validation.
5. **Persistence and reporting** (`services/api`): graph-backed storage, session
   tracking, structured violation reporting.

The exploration graph is a **cyclic** directed graph; never call it a DAG.
Back-edges are data, not noise, and nothing may prune them.

## What makes it different

Traditional testing tools validate predefined workflows. GUI agents focus on
completing tasks. StateScout audits logical UI exposure: it detects forbidden
interface states and verifies state-space consistency across navigation paths.

It reframes UI testing as a state-space auditing problem.

## Tech stack

Python 3.11+ · LangGraph · Playwright · FastAPI · Neo4j · Redis · multimodal
vision-language models (inference only) · TypeScript · Bun

## Contributing

Branches are `<type>/<TRACK>-<slug>`, for example `feature/B-bfs-loop`. Types:
`feature`, `fix`, `hotfix`, `release`, `chore`, `docs`. PRs target `staging`;
only `staging` merges into `main`. CI enforces both.

Commits are [Conventional Commits](https://www.conventionalcommits.org/) with the
module as scope, e.g. `feat(orchestrator): add BFS frontier`.

## Project status

Under active development as an 8-month strategic software project. Current focus:
autonomous UI exploration, state graph construction, policy-aware negation
evaluation, and end-to-end violation reporting.

## Team

Team 46 · Department of Computer Science & Engineering · Amrita Vishwa Vidyapeetham

| Track | Member | Role |
| --- | --- | --- |
| A | Jai Subiksha T | Integration, extension & DevOps |
| B | Kavinraj S | Agent & orchestration |
| C | Sanjay AR | Vision, negation & research |
| D | Harshita R | Data, API & reporting |

## License

[MIT](./LICENSE) © 2026 StateScout AI, Team 46
