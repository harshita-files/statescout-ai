# StateScout — panel-review demo (local-site audit)

Branch `panel-review-demo` = `staging` + the Track A crawler selector fix + this
demo. It is **not** meant to merge back into `staging`; it exists so the team can
pull one branch and run the pipeline end to end.

## What it does

Point it at a **folder of static HTML** on your machine (an `index.html` plus
linked pages). It serves the folder locally, the real crawler explores it, and a
deterministic negation engine (plus an optional Gemini vision pass) checks every
page against a plain-English policy you type. You get: the exploration graph,
per-page screenshots, and every policy violation with its evidence.

Real components exercised: the Playwright crawler (Track A), the DOM/AX semantic
map + negation engine (Track C), Neo4j + Redis (Track D), and the LangGraph BFS
loop (Track B). Local stand-ins, shown in the UI: the ADR-001 C-3 `state_id` fix
and a small Gemini-backed policy parser filling in for Track B's FR-04 parser.

## Setup

```bash
git checkout panel-review-demo

docker compose -f infra/docker-compose.yml up -d      # Neo4j :7687, Redis :6379
uv sync --extra perception
uv run python -m playwright install chromium
```

Optional — for the Gemini vision pass, put a key in a `.env` file at the repo
root (git-ignored), or export it in your shell:

```
GEMINI_API_KEY=your-key-here
```

Without a key the demo still works; the vision pass is skipped.

## Run

```bash
./run_local.sh
```

Then open **http://127.0.0.1:8081**.

- Uses port **8081** for the console and **8090** for the static file server —
  both must be free.
- The form has a **bundled examples** row: 5 test sites under `demo-inputs/`
  (four with a planted policy violation, one clean). Click one to fill the path.
- Regenerate the test sites any time with `python scripts/generate_sites.py`.

## Example

| Folder | Policy to type | Expected |
| --- | --- | --- |
| `demo-inputs/shopfast`    | A guest must never open the admin panel.   | 2 violations (FR-18) |
| `demo-inputs/teamhub`     | A guest must never see debug tools.        | 1 violation (FR-18) |
| `demo-inputs/datavault`   | A guest must never export all records.     | 1 violation (FR-18) |
| `demo-inputs/securelogin` | A guest must always have a logout control. | 3 violations (FR-19, required absent) |
| `demo-inputs/cleanapp`    | (either of the above)                      | 0 violations — control |

The exploration graph is also in Neo4j — open http://localhost:7474
(`neo4j` / `devsecret`) and run
`MATCH (s:StateNode)-[a:ACTION]->(t) RETURN *`.

## Notes

- Re-running the same folder **replaces** that target's graph in Neo4j rather
  than piling on — the static server uses a fixed port so URLs (and therefore
  fingerprints) are stable, and each run purges the target's previous nodes.
- One audit runs at a time (the console serialises them).
- The negation engine recognises these policy subjects:
  `admin-access, debug-access, export-data, delete-user, logout, login`.
