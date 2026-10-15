# StateScout AI: project state handoff

Written 2026-10-14 from a read-only survey of the repo (branch `chore/B-research-paper-agents`, latest commit `4487574`). Nothing here was run. Claims about "built" and "stubbed" come from reading code and docs, not from executing them.

## 1. What this is and why

StateScout is a policy-aware UI auditing engine (Team 46, final-year project, Dept. of CSE, Amrita Vishwa Vidyapeetham). It explores a web app autonomously, builds a graph of UI states, extracts semantic information from each state, and flags states that violate a natural-language policy.

The motivating problem is frontend RBAC leakage: an admin link visible to a guest, a debug panel in production, role-rendering inconsistencies. The backend may reject the request, but the UI exposure is already the leak. Normal tests check that expected workflows succeed; StateScout checks what should NOT exist ("state-space auditing").

Stack: Python 3.11+ (uv), LangGraph, Playwright, FastAPI, Neo4j, Redis, a VLM (inference only), TypeScript on Bun.

## 2. Architecture

Loop: Scan → Reason → Act → Observe, with a BFS frontier.

- Orchestrator (`apps/agent/orchestrator`): the LangGraph loop.
- Crawler (`apps/agent/crawler`): Playwright capture of DOM, accessibility tree and screenshot.
- Perception (`apps/agent/perception`): builds a `SemanticUIMap` per state. Negation (`apps/agent/negation`): deterministic audit.
- Graph (`apps/agent/graph`): fingerprint, dedup, Neo4j and Redis. API (`services/api`): FastAPI run control and reporting.

Three stores (see `docs/db/README.md`):
- Neo4j: the graph and findings.
- Redis: the visited set, status and stop signal. Not just a cache.
- SQLite: LangGraph checkpoints, run manifests, `run_skip` coverage gaps.

Ordering per step: `mark_visited` (Redis) → `act` → `persist_edge` (Neo4j). The frontier lives in the LangGraph checkpoint.

Other directories: `test-apps/` (deliberately broken ground-truth apps with `violations.json`), `research/` (finetune and benchmark; isolated, cuttable, nothing in `apps/` or `services/` may import it), `infra/docker-compose.yml` (Neo4j :7687, Redis :6379).

## 3. Tracks and ownership

| Path | Track |
| --- | --- |
| `apps/agent/crawler/`, `apps/vscode-extension/`, `packages/shared-types/` | A |
| `apps/agent/orchestrator/`, `apps/agent/skeleton.py` | B |
| `apps/agent/perception/`, `apps/agent/negation/`, `research/` | C |
| `apps/agent/graph/`, `services/api/`, `infra/` | D |

Cross-module calls go only through the typed interfaces in `apps/agent/contracts.py`. A `PreToolUse` hook (`.claude/hooks/track_b_paths.py`) blocks writes outside the active track's paths; the track comes from `.claude/track.local` or `STATESCOUT_TRACK`.

Git: branches `<type>/<TRACK>-<slug>`, PRs to `staging`, only `staging` merges to `main`, Conventional Commits with the module as scope.

## 4. Built versus stubbed

Built and merged:
- Track B (through Month 2, per `docs/track-b-progress.md`): `contracts.py`, `fakes.py`, walking skeleton, LangGraph proof of concept, plain-Python BFS `explore.py` (kept as the parity oracle), `graph_runner.py` (what actually runs), `config.py`, `ratelimit.py`, `runlog.py`. 372 tests passing when `docs/meeting.md` was written. `test_ground_truth.py` shows frontier-exhaustion termination, 6/6 states, a cyclic graph, zero duplicate pairs.
- Track A: `PlaywrightCrawler` (PR #17).
- Track C: UI extraction and DOM+AX correlation (PR #12), Gemini provider (PR #15), deterministic `negation/audit.py`.
- Track D: Neo4j graph store, fingerprint normalisation, Redis cache, crawl-driving API with run control and auth (PR #13).

Not built or stubbed:
- Track B Months 3-4: `policy.py` (NL policy to `ExpectationSet`; `policy.json` is hand-written today), the FR-04/16 confirmation gate, graceful stop, checkpoint-resume, run manifest. Nothing in `orchestrator/` calls an LLM yet.
- The Gemini path exists but is not wired into the orchestrator and carries a `state_id` placeholder.
- `research/finetune` and `research/benchmark` are README-only.
- `--live` mode: `live_ports` was updated for Track A (`24c2b7f`); whether the end-to-end live pipeline works was not checked.
- The Neo4j files in `docs/db/` were never executed against a real Neo4j. Only the SQLite migration was tested.

## 5. Key decisions and why

- **The graph is CYCLIC.** Never call it a DAG; back-edges (`is_back_edge`) are persisted, never pruned. "You can reach admin from three paths" is itself a finding. Dedup applies to node creation only, by fingerprint.
- **Loop prevention is the visited `(state_id, action_id)` set, nothing else.** Dedup is per state because a Delete button can be forbidden in one state and fine in another. `action_id` is a content hash of role + accessible name + normalised selector, never a DOM index. NFR-05: zero duplicate pairs.
- **`contracts.py` is frozen.** If a contract seems wrong, stop and raise it with the owning track. Changes after the freeze need a new ADR.
- **ADR-001** (`docs/adr-001-cross-track-contract-review.md`):
  1. content-addressed action ids, per-state dedup;
  2. `fingerprint()` normalises the bundle before hashing (strips timestamps, CSRF/nonce, session ids), SHA-256 over normalised URL | DOM | AX;
  3. `mark_visited` before `act` gives at-most-once execution; a crash in between leaves a logged, never-retried pair;
  4. `capture()` splits into `open()` (raises `NavigationError`) and `act()` (raises `ActionError`);
  5. one role per run, no mid-run switching (cross-role comparison is FR-31 reporting);
  6. `audit()` gets the full `ExpectationSet`: FR-18 is `S ∩ forbidden`, FR-19 is `required \ S`;
  7. `screenshot_path` optional, screenshot-less runs tagged `dom_only_smoke_test`;
  8. OPEN: who mints `SemanticUIMap.state_id` (blocks the freeze; Track B leans toward passing the id into `analyze()`).
- **Replay.** One browser can only act on the page it is on, so reaching a queued action reopens the seed and replays its path. `REPLAY_SAFE_KINDS = {navigate, click, back}` (`orchestrator/state.py:48`). Paths through `fill`/`select`/`submit` are skipped, recorded in `run_skip`, and their subtrees reported as unexplored.
- **Two limits**, `depth_limit` (default 5) and `max_states` (default 200); `max_states` is the only backstop against an unstable fingerprint.
- **Absence is judged deterministically.** The VLM only merges tags onto the DOM+AX element list; it never adds or removes elements, because VLMs are weak at negation.
- **Orchestrator style.** A single `TypedDict` state, nodes return partial updates, all I/O via injected ports (`deps.py`), structured JSON logs, no `print()`, config via pydantic-settings.

## 6. How the code actually identifies and records states

- `state_id` = `ports.graph.fingerprint(bundle)` (`graph_runner.py:147`, again after every act at `:307`).
- `fingerprint_bundle` (`graph/fingerprint.py`) = sha256(url | normalised DOM | normalised AX). It strips nonce/CSRF/session-like attributes, hex-looking ids, long digit runs, and volatile AX keys.
- `CaptureBundle` (`contracts.py:174-191`) has `url`, `dom`, `ax_tree`, `screenshot_path`, `title`. No network data.
- Neo4j: nodes `StateNode`, `VisitedPair`, `ViolationNode`, `ExpectationNode`, `PolicyContext`, `Project`; relationship `(StateNode)-[:ACTION {action_id, label, is_back_edge, recorded_at}]->(StateNode)`. Every traversal CREATEs a new relationship.
- Redis: key `session:{scan_id}:visited:{state_id}:{action_id}` set to 1, no counters.

## 7. The panel's critique, mapped to the code

The panel said the system suits static sites and will fail on dynamic ones, that it should count clicks toward API endpoints, and that it should use a probabilistic graph model.

Where dynamic sites break it today:
- Whole-DOM hashing makes feed items, ads, counters, relative times and randomised CSS-in-JS classes into "new states". Infinite scroll is stopped only by `max_states` (`config.py` already names it as the intended catch).
- Replay requires an exact fingerprint match, so non-determinism becomes "replay diverged" skips and silent coverage loss.
- Capture waits for `networkidle` with a 5s timeout, suppressed on failure (`capture.py:105`, `actions.py:198,206`), so XHR-driven content can be captured half-loaded.
- No network interception anywhere (`page.on("request"/"response")`, HAR, `route()` absent), so API endpoints are invisible.
- SPA: the URL is not identity ("an SPA shows many states at one URL", `docs/db/neo4j/schema.md:64`), but a modal at a fixed URL is just another DOM hash with no modal concept.
- Edges carry no counts or probabilities, and there is no click-count metric.
- Crawler gaps: `fill`/`select`/`submit`/`back` are not implemented in `_perform_action`; `enumerate_actions` does not return form fields; the `[data-backend-node-id]` selector does not exist in the real DOM; click is treated as replay-safe, so a state-mutating one-click action would be re-fired on replay (flagged in `docs/report/paper/sections/model.tex` and `discussion.tex`).

Where statistics could attach: `:ACTION` relationships (switch to `MERGE ... ON MATCH SET n = n + 1`), the Redis visited key (boolean to counter), `StateEdge` (frozen, needs a contract change), `CaptureBundle` (frozen; network data would be captured in `extract_page_state`).

## 8. Constraints any new work must respect

- Cyclic graph; never prune back-edges.
- Loop prevention stays the visited set. A probabilistic layer may change ordering and identity, not termination.
- `contracts.py` is frozen: contract changes go through a new ADR and the owning track.
- No new dependencies without asking.
- TDD: failing test first. Conventional commits. Never commit to `main`.
- Never log secrets (NFR-11).
- Track-specific rules live in each module's `CLAUDE.md`.

## 9. Docs and tooling

- Ground truth: `test-apps/broken-admin` (6 states, 4 cycles, 4 planted violations: 3 forbidden-present, 1 required-absent); other demos `broken-feature-flag-demo`, `broken-rbac-demo`, `missing-consent-demo`.
- Demo: `docs/meeting.md` (18-minute script), `docs/mentor-speech.md`, `docs/demo_crawl.py`.
- Paper: `docs/report/` (IEEE and LaTeX drafts, experiments in `docs/report/experiments/run_experiments.py`, novelty analysis, Springer audit/revision files). The claim is to unify and formalise a polarity-typed, role-scoped oracle over a cyclic, side-effect-aware crawl, not to be first. The 4/4 recall holds only against `FakePerception` and a scripted crawler.
- Known paper caveats: real perception tags (`admin`) mismatch policy subjects (`admin-link`); no page-scope predicate on clauses; `policy.json` severities are ignored by `audit.py`.
- `.claude/`: agents `fixture-forge`, `fresh-eyes-reviewer`, `langgraph-scout`, `test-runner`, `research-paper-auditor`, `research-paper-writer`; skills `orchestrator-conventions`, `pr-prep`.

## 10. Open items

- ADR-001 C-3/D-4: who mints `state_id`.
- A-2: `clauseType` missing from the TypeScript mirror (`PENDING_TS_SYNC`).
- `ExpectationNode` has no scope predicate.
- `.env.example` lacks `STATESCOUT_ROLE`, `STATESCOUT_RUN_ID_STRATEGY`, `STATESCOUT_RUN_ID`.
- Redis compose uses `--save 60 1`, too weak for the at-most-once guarantee; AOF `everysec` with eviction off is recommended.
- The panel critique above: dynamic sites, endpoint/click statistics, probabilistic model (this is the work being started next).

## 11. Test layout

`tests/unit/{orchestrator,crawler,graph}`, `tests/integration/{orchestrator,graph}`, fixtures in `tests/fixtures/orchestrator`, plus tests inside `apps/agent/{perception,negation,crawler}/tests/`. Commands: `uv run pytest`, `bun test tests/unit`, `uv run ruff check apps services tests`, `uv run mypy apps/agent`.
