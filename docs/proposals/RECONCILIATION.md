# Reconciliation: edits outside Track B's paths in the working tree

Branch at survey time: `chore/B-research-paper-agents`. Source: `git status`/`git diff` (read only). Facts come from the diff; items marked (uncertain) were not verified. Nothing was run, no tests were executed, no git state was changed.

Track B may write only `apps/agent/orchestrator/`, `apps/agent/skeleton.py`, and the matching `tests/.../orchestrator/` and `tests/fixtures/orchestrator/` paths (`apps/agent/orchestrator/CLAUDE.md`). The files below are outside that set. All are unstaged unless noted. Related design: ADR-002 (Proposed) and `track-A-network-capture.md`, `track-C-confidence.md`, `track-D-edge-stats.md` in this folder.

## Modified or new files outside Track B

| # | File | What changed (from the diff) | Owner / reviewer | Recommended path |
| --- | --- | --- | --- | --- |
| 1 | `apps/agent/crawler/playwright_crawler.py` (+145) | New `probabilistic_states` flag (default False); fetch/XHR request listeners; `drain()` returning `METHOD /path` labels with numeric and UUID segments templated; bounded readiness wait (200 ms quiet, 2 s budget) setting `last_capture_ready`; `open()`/`act()` use it instead of `networkidle` when on; listener cleanup in `close()`. | Track A | Re-submit as `feature/A-network-capture` by Track A, reviewed against `track-A-network-capture.md`. Do not merge as is. |
| 2 | `apps/agent/crawler/actions.py` (about +35 lines, per diff stat) | `_perform_action(..., wait_network_idle=True)`; `execute_action(..., before_capture=None)` hook; with the hook, no retry after the action completed (post-action timeout breaks). Still no `fill`/`select`/`submit`/`back`. | Track A | Same branch as 1. Check that default path (no hook) is byte-for-byte behavior equal. |
| 3 | `apps/agent/crawler/README.md` (+41) | Documents the optional capture support and the drain protocol. | Track A | Goes with 1 and 2. |
| 4 | `tests/unit/crawler/test_probabilistic.py` (new, untracked) | About 17 test functions (windows, readiness bound, no re-fire, default unchanged, cleanup). Pass/fail unknown. | Track A | Goes with 1. Needs to be run by A; mocks may not reflect real Playwright (uncertain). |
| 5 | `apps/agent/graph/graph_store.py` (+28) | New `persist_dynamic_report` (`MERGE (:DynamicReport {run_id}) SET report_json`) and `get_dynamic_report`; adds `json` and `cast` imports. Existing `:ACTION` CREATE unchanged. | Track D | Re-submit as `feature/D-dynamic-report` by Track D, reviewed against `track-D-edge-stats.md` (no constraint, no schema version, opaque blob). |
| 6 | `apps/agent/graph/neo4j_graph.py` (+8) | Delegating `persist_dynamic_report`/`get_dynamic_report`. Not on the frozen `GraphPort`. | Track D | With 5. |
| 7 | `services/api/models.py` (+19/-1) | `StartScanRequest.probabilistic_states`, `volatility_patterns` with `re.compile` validator; `ScanReportResponse.dynamic: dict[str, Any] | None`. | Track D | With 5. Public API change (extension may read it, Track A mirror, uncertain). Regex validator does not bound complexity (uncertain). |
| 8 | `services/api/main.py` (+9) | Forwards both options to `run_scan`; `get_scan_report` reads `get_dynamic_report` under `contextlib.suppress(Exception)` and adds `dynamic` to the response. | Track D | With 5. Silent exception swallowing hides store errors. |
| 9 | `services/api/runner.py` (+20/-2) | `Ports(..., network=live.network)`; `OrchestratorConfig` built inside `try` with the new options; after the run, `persist_dynamic_report(scan_id, asdict(result.dynamic))`. Imports Track B's `result.dynamic` shape via `getattr`. | Track D, with B interface review | With 5. Depends on Track B's `ExplorationResult.dynamic` and `Ports.network`, which are B-owned and uncommitted. |
| 10 | `tests/unit/graph/test_dynamic_report.py` (new), `test_api_month2.py` (+52), `test_runner.py` (+68) | Tests for report persistence, API forwarding, invalid pattern, round trip, network preserved. Pass/fail unknown. | Track D | With 5. |
| 11 | `.claude/hooks/track_b_paths.py` (+1, staged in the index) | Adds `.claude/agents/` to `SHARED_PATHS` (the enforcement hook itself). | Not assigned in CLAUDE.md (shared infra; team decision) | Review explicitly. It widens the write guard that exists to stop cross-track edits, and is the only staged change. Recommend revert unless the team agrees; then commit alone as `chore(hooks)`. |
| 12 | `.claude/agents/research-paper-auditor.md`, `research-paper-writer.md` (new, untracked) | New subagent definitions. | Team / Track C (paper under `docs/report`, research) (uncertain owner) | Accept after review; separate `chore(agents)` commit, tied to the hook change in 11. |
| 13 | `docs/adr-002-probabilistic-network-state-model.md`, `docs/handoff/`, `docs/research/`, `docs/report/`, `tests/fixtures/orchestrator/paper-subjects/` | New docs and fixtures (the last is under Track B's fixtures path). | Shared docs; B for fixtures | Accept after review; ADR-002 is Proposed and needs A/B/C/D agreement. |

Track B's own working-tree changes (`apps/agent/orchestrator/*`, `tests/unit/orchestrator/*`, new `dynamic.py`, `stochastic/`) are inside B's boundary and are not listed above, but they depend on rows 1, 5, 9: `Ports.network`, `live_ports()` building `PlaywrightCrawler(probabilistic_states=True)` and importing `apps.agent.graph.neo4j_graph` directly (a deep import, not through `apps.agent.graph`).

## Cross-cutting findings

- The edits in rows 1 to 10 were made by another session directly in Tracks A and D, violating the module-boundary rule in `CLAUDE.md` and `apps/agent/orchestrator/CLAUDE.md`. Whether the PreToolUse hook was bypassed or reconfigured is not known; row 11 suggests the hook was edited in the same working tree.
- `live_ports()` (B) imports `apps.agent.graph.neo4j_graph.Neo4jGraph` directly when `probabilistic_states` is on, instead of `apps.agent.graph.Neo4jGraph`. This looks like a cross-track internal import (uncertain which module path is the public one).
- The frozen contracts file `apps/agent/contracts.py` has no diff (good).
- The staged hook change is mixed into the same working tree as unstaged code; committing "everything" would put all of the above on a Track B branch.

## Risks

1. Merging unreviewed cross-track code on a Track B branch: owners lose review, and a later A/D change can conflict silently.
2. Default behavior drift: rows 1 and 2 touch the live crawl path; "default unchanged" is asserted by new tests, not demonstrated (not run).
3. Real-browser behavior (readiness, listeners) and real Neo4j behavior (`DynamicReport`) are unverified; tests appear to be mocks.
4. Label sanitizing is route templating only; secret-bearing path segments may be persisted (see track-A item 6).
5. The hook edit weakens future boundary enforcement.
6. Branch is `chore/B-research-paper-agents` but carries feature work; branch naming `<type>/<TRACK>-<slug>` and "PRs to `staging`" are not met as is.
7. Per-run `DynamicReport` blob is overwritten only at the end; a crash loses it (checkpointed `DynamicStats` is the durable copy, durability itself unvalidated per ADR-002).

## Suggested order

1. Freeze: do not commit rows 1 to 11 on this branch. Keep them in the working tree, or hand to owners as patches from `git diff -- <path>` (read only).
2. Track A and Track D each create their own branch, take the corresponding hunks, write/rerun tests, open PRs to `staging`. Track B lands `dynamic.py` and runner changes after the ports (`NetworkObservations`, optional stats sink) are agreed.
3. Decide on row 11 and 12 with the team.
4. Agree ADR-002 (it is Proposed) before any merge to `staging`.
