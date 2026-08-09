# StateScout AI

StateScout AI is a policy-aware UI auditing engine that autonomously explores web
applications and detects forbidden or logically invalid interface states.

It shifts automation from workflow testing to logical state verification.

---

## 🚩 The Problem

Modern web applications rely on backend Role-Based Access Control (RBAC) to
protect sensitive actions.

However, frontend logic errors can still expose restricted interface components,
such as:

- Admin dashboards visible to non-admin users
- Debug panels exposed in production
- Role-based rendering inconsistencies
- Unintended state transitions

Even if backend APIs block execution, UI exposure itself can violate access
policies or compliance rules.

StateScout is designed to detect such logical UI exposure automatically.

---

## 🧠 Core Idea

Instead of validating predefined test scripts, StateScout:

1. Explores the interface autonomously
2. Constructs a directed state graph of navigation paths
3. Extracts semantic information from UI states
4. Applies negation-aware policy evaluation
5. Flags forbidden or logically invalid UI states

It focuses on *what should NOT exist* rather than simply verifying expected
workflows.

---

## 🏗 Repository layout

```
statescout-ai/
├── apps/
│   ├── vscode-extension/   # TypeScript — QA engineer UI              (Track A)
│   └── agent/              # Python — LangGraph + Playwright + VLM  (Tracks A/B/C)
│       ├── crawler/        # Playwright capture + actions              (A)
│       ├── orchestrator/   # LangGraph loop + conditional edges        (B)
│       ├── perception/     # VLM provider iface + Semantic UI Map      (C)
│       ├── negation/       # Negation engine (S ∩ C + cross-check)     (C)
│       └── graph/          # fingerprint + hash dedup + Neo4j calls    (D)
├── services/
│   └── api/                # Python — FastAPI reporting backend        (D)
├── packages/
│   └── shared-types/       # TypeScript — API contract types
├── research/               # Python — isolated, cuttable               (C)
│   ├── finetune/           # InternVL LoRA / QLoRA
│   └── benchmark/          # negation test set + scoped OSWorld eval
├── infra/
│   └── docker-compose.yml  # Neo4j (Bolt :7687) + Redis + api
├── test-apps/              # deliberately-broken demo apps (ground truth)
├── tests/                  # unit / integration / e2e / fixtures
└── .github/workflows/      # path-filtered CI
```

The module boundary is the ownership boundary. Cross-module calls go through the
typed interfaces in `apps/agent/contracts.py` — never through direct imports of
another track's internals.

---

## 🚀 Getting started

**Prerequisites:** [uv](https://docs.astral.sh/uv/), [Bun](https://bun.sh),
Docker (for Neo4j and Redis).

```bash
git clone https://github.com/<org>/statescout-ai.git
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

---

## 🧩 System architecture

### 1️⃣ Orchestration & control — `apps/agent/orchestrator`
Session lifecycle, the Scan → Reason → Act → Observe loop, BFS frontier
management, policy injection, and exploration termination.

### 2️⃣ Browser interaction — `apps/agent/crawler`
Playwright navigation, DOM extraction, accessibility tree parsing, screenshots.

### 3️⃣ Perception & reasoning — `apps/agent/perception`, `apps/agent/negation`
Vision-language model (inference only), UI semantic interpretation, and
negation-based violation detection.

### 4️⃣ State & graph management — `apps/agent/graph`
UI state fingerprinting, directed navigation graph construction, loop prevention
via a visited `(state, action)` set, and state consistency validation.

The exploration graph is a **cyclic** directed graph — never call it a DAG.
Back-edges are data, not noise; nothing may prune them.

### 5️⃣ Persistence & reporting — `services/api`
Graph-backed storage, session tracking, structured violation reporting.

---

## 🔎 What makes it different?

Traditional testing tools validate predefined workflows. GUI agents focus on
completing tasks. StateScout audits logical UI exposure: it detects forbidden
interface states and verifies state-space consistency across navigation paths.

It reframes UI testing as a state-space auditing problem.

---

## 🛠 Tech stack

Python 3.11+ · LangGraph · Playwright · FastAPI · Neo4j · Redis ·
multimodal vision-language models (inference only) · TypeScript · Bun

---

## 🌱 Contributing

Branches are `<type>/<TRACK>-<slug>` — for example `feature/B-bfs-loop`. Types:
`feature`, `fix`, `hotfix`, `release`, `chore`, `docs`. PRs target `staging`;
only `staging` merges into `main`. CI enforces both.

Commits are [Conventional Commits](https://www.conventionalcommits.org/) with the
module as scope, e.g. `feat(orchestrator): add BFS frontier`.

---

## 📈 Project status

Under active development as an 8-month strategic software project. Current focus:
autonomous UI exploration, state graph construction, policy-aware negation
evaluation, and end-to-end violation reporting.

---

## 👥 Team

Team 46
Department of Computer Science & Engineering
Amrita Vishwa Vidyapeetham

---

## 📜 License

[MIT](./LICENSE) © 2026 StateScout AI — Team 46
