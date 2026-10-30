# Proposal for Track D: edge statistics, Endpoint nodes, Redis counters, report fields

- **Owner:** Track D (`apps/agent/graph/`, `services/api/`, `infra/`). Drafted by Track B, which does not write there.
- **Status:** Proposal. Cites `docs/adr-002-probabilistic-network-state-model.md` (Proposed). It follows ADR-002 decisions: traversal edges stay append-only, aggregates sit beside them, visited pairs stay claims, `contracts.py` is not changed.
- **Basis:** read-only inspection of the uncommitted diff in `apps/agent/graph/`, `services/api/`, tests under `tests/unit/graph/`, and `apps/agent/orchestrator/dynamic.py`. Nothing was run.

## Problem

Today the graph has no counts: `:ACTION` is always CREATEd (one relationship per traversal, `graph_store._ACTION_EDGE`), Redis visited keys are `session:{scan_id}:visited:{state_id}:{action_id} = 1`, and nothing records endpoints. The orchestrator now computes transition counts, endpoint counts and confidence in memory (`DynamicStats`) and the checkpoint holds them. Track D must make them queryable and part of the report without changing the cyclic, append-only evidence model.

## What the pending diff already does (read from the diff)

| Area | Change in diff | Gap against ADR-002 |
| --- | --- | --- |
| `graph_store.persist_dynamic_report(run_id, report)` | `MERGE (r:DynamicReport {run_id}) SET r.report_json = <json string>` with `allow_nan=False`; `get_dynamic_report` reads and decodes; `None` if missing. | One opaque JSON blob per run, overwritten at the end. Not queryable by edge/endpoint; no schema version; no constraint on `DynamicReport.run_id`; unbounded size; not idempotent per event (overwrite is idempotent, but a mid-run crash leaves nothing). |
| `Neo4jGraph` | thin delegates for both methods | Methods are not on `GraphPort` (contract frozen); the runner reaches them via `getattr`/duck typing (to confirm in `runner.py`, below). |
| `services/api/models.py` | `StartScanRequest.probabilistic_states`, `volatility_patterns` (regex-validated); `ScanReportResponse.dynamic: dict[str, Any] | None`. | `dynamic` is an untyped dict. Regex validator accepts catastrophic-backtracking patterns (ReDoS, uncertain: not tested). |
| `services/api/main.py` | passes the options to `run_scan`; `get_scan_report` reads `get_dynamic_report` inside `contextlib.suppress(Exception)` and returns `None` on any error. | A Neo4j failure is indistinguishable from "no report" in the response. |
| `services/api/runner.py` | `Ports(..., network=live.network)`; builds `OrchestratorConfig` inside the `try`; after the run, `persist_dynamic_report(scan_id, asdict(result.dynamic))` with errors logged. | Persist happens only after completion. The `scan_id` is used as the `run_id` key; if the orchestrator `run_id` differs, joins are ambiguous (uncertain, to verify). |
| Tests | `tests/unit/graph/test_dynamic_report.py` (new), additions in `test_api_month2.py`, `test_runner.py` (by names: round trip, legacy/invalid report, forward options, network preserved). | Unit/mocked only; Neo4j behavior unverified. |

Not in the diff: any change to `_ACTION_EDGE`, Endpoint nodes, Redis counters, constraints or migrations, any `infra/` change.

## Exact change requested (Track D)

1. **Keep** the append-only `(:StateNode)-[:ACTION]->(:StateNode)` traversal edges exactly as they are. Do not MERGE them.
2. **Add an aggregate relationship** beside it, one per `(from, to, action_id)`:

```cypher
MERGE (a:StateNode {fingerprint: $from_fp})
MERGE (b:StateNode {fingerprint: $to_fp})
MERGE (a)-[t:TRANSITION {action_id: $aid, run_id: $run_id}]->(b)
ON CREATE SET t.count = 1, t.replay_count = $replay, t.first_seen = timestamp(), t.last_seen = timestamp()
ON MATCH  SET t.count = t.count + 1, t.replay_count = t.replay_count + $replay, t.last_seen = timestamp()
```

   Name chosen so it cannot be confused with `:ACTION`. Include `run_id` in the key so runs stay separate (the code today keys states by fingerprint only; confirm with Track B whether state nodes are shared across runs).
3. **Endpoint nodes** keyed `(run_id, endpoint)`:

```cypher
MERGE (e:Endpoint {run_id: $run_id, label: $label})   // label = "GET /users/:id"
ON CREATE SET e.calls = $calls, e.actions = 1, e.clicks = $clicks, e.replay_calls = $rc, e.replay_clicks = $rcl
ON MATCH  SET e.calls = e.calls + $calls, e.actions = e.actions + 1, e.clicks = e.clicks + $clicks,
              e.replay_calls = e.replay_calls + $rc, e.replay_clicks = e.replay_clicks + $rcl
WITH e
MATCH (a:StateNode {fingerprint: $from_fp})
MERGE (a)-[c:CALLS {action_id: $aid, run_id: $run_id}]->(e)
ON CREATE SET c.calls = $calls, c.actions = 1
ON MATCH  SET c.calls = c.calls + $calls, c.actions = c.actions + 1
```

   Counter names mirror `DynamicStats.endpoints` so that "non-replay = total - replay" holds (ADR-002). Label strings must be validated against the same whitelist the orchestrator applies before write (defense in depth, NFR-11); never store queries or raw URLs.
4. **Idempotence.** `ON MATCH count = count + 1` is NOT idempotent under retry or crash-resume (ADR-002: stable event IDs, no double counting). Either (a) write counters only from a checkpointed snapshot using `SET t.count = $absolute` (last-writer-wins, recommended first step, matches the current `DynamicReport` overwrite semantics), or (b) store an `event_id` on a small `:Observation` node and increment only when its MERGE creates it. Decide with Track B; option (a) is far simpler.
5. **Redis.** Keep `session:{scan_id}:visited:...` as a claim (value 1, `mark_visited` unchanged, idempotent). Put counters in separate keys, for example `session:{scan_id}:trans:{state_id}:{action_id}` (hash: target -> count) and `session:{scan_id}:endpoint` (hash: label -> calls). Use `HINCRBY`. Counters share the visited TTL (`set_ttl`) and `clear()` pattern; extend `_session_pattern` handling so `clear()` removes them. Redis is a cache for reads during the run, not the source of truth.
6. **Report fields.** Replace `dict[str, Any]` with a typed pydantic model, version it, and mirror it in `packages/shared-types` (Track A owns that mirror; synchronized Python/TS review needed):

```python
class EdgeStat(BaseModel):  from_state: str; action_id: str; to_state: str; count: int; replay_count: int; probability: float
class EndpointStat(BaseModel):  label: str; calls: int; actions: int; clicks: int; replay_calls: int; replay_clicks: int
class DynamicReport(BaseModel):
    schema_version: int
    probabilistic_states: bool
    network_available: bool          # absent producer != zero calls
    readiness: dict[str, int]
    edges: list[EdgeStat]; endpoints: list[EndpointStat]
    violations: list[ViolationConfidence]   # see track-C-confidence.md
    truncated: bool                   # retention caps
```

   Also expose denominators (sum of counts per source/action) so a reader can recompute probabilities, and label all-observation vs replay vs exploration-only (ADR-002).
7. **Errors.** In `get_scan_report`, distinguish "no dynamic report" (`dynamic: null`) from "store error" (HTTP 200 with `dynamic_error` string, or 5xx). Do not swallow all exceptions silently.
8. **Constraints and migration.**

```cypher
CREATE CONSTRAINT endpoint_key IF NOT EXISTS FOR (e:Endpoint) REQUIRE (e.run_id, e.label) IS UNIQUE;
CREATE CONSTRAINT dynamic_report_run IF NOT EXISTS FOR (r:DynamicReport) REQUIRE r.run_id IS UNIQUE;
CREATE INDEX transition_run IF NOT EXISTS FOR ()-[t:TRANSITION]-() ON (t.run_id);
```

   Add as `docs/db/neo4j/migrations/002_dynamic_stats.cypher` (next to `001_init.cypher`) and run through whatever migration path Track D uses. Existing graphs need no data migration: new relationship types and labels are additive and old reports simply have `dynamic: null`. Caveat: `docs/db/neo4j/migrations/001_init.cypher` uses labels `State`, `Run`, `Violation`, while the code writes `StateNode`, `ViolationNode`, `PolicyContext`. The handoff notes the `docs/db` Neo4j files were never executed against a real Neo4j. Resolve which schema is real before writing 002.

## Interface sketch

```python
# GraphStore (Track D); NOT added to GraphPort (frozen). Orchestrator reaches it via an optional,
# separately injected "StatsSink" protocol (needs an ADR-002 decision; not enacted).
class StatsSink(Protocol):
    def persist_dynamic_snapshot(self, run_id: str, snapshot: DynamicReport) -> None: ...
```

## Tests (failing first)

- Unit (mocked session): the Cypher uses parameters only; `MERGE ... ON CREATE/ON MATCH` text asserted; absolute-set variant is idempotent when called twice.
- Integration (real Neo4j via `infra/docker-compose.yml`, marked so it is skippable): two traversals of one edge give 2 `:ACTION` relationships and one `:TRANSITION` with `count=2`; a cycle (A->B->A) is preserved; Endpoint counters add up; constraint rejects duplicate Endpoint; label with query string rejected.
- Redis: `HINCRBY` counters, TTL applied, `clear()` removes them, `mark_visited` unaffected and still idempotent.
- API: typed model validation; `dynamic: null` vs error; invalid regex rejected; pathological regex has a length/complexity cap.
- Resume: persisting the same snapshot twice does not double counts.

## Risk

- Increment counters can double count on retry (item 4).
- Per-run Endpoint/edge nodes grow with exploration; needs caps and a `truncated` flag (ADR-002).
- Duplicating state across Neo4j (`DynamicReport` blob and live counters) may disagree; pick one source of truth (the checkpointed snapshot).
- Typed report is an API change visible to the extension (Track A mirror).
- ReDoS from user-supplied `volatility_patterns` evaluated in the orchestrator thread (uncertain, untested).

## Effort

About 4 to 6 working days: Cypher + migration 1 to 1.5, Redis counters 0.5 to 1, typed report + API 1, idempotence design with B 0.5 to 1, real-Neo4j integration tests 1.5. Needs a working Neo4j; the earlier unverified `docs/db` schema may add 1 day.
