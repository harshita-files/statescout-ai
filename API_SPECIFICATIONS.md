# StateScout AI — API Reference

**Owner:** Track D (Data, API & Reporting) · **Framework:** FastAPI · **Version:** `0.2.0`
**Base URL (local dev):** `http://localhost:8000`
**Interactive docs (auto-generated, live from this same code):** `/docs` (Swagger UI), `/redoc`

This document describes the API **as currently implemented**. It is verified against
`services/api/main.py` and `services/api/models.py`. Anything not yet wired end to end
is called out inline (see *Known gaps*).

---

## Table of contents

1. [Ops](#ops) — `GET /health`
2. [Projects](#projects) — CRUD for saved scan targets
3. [Scan lifecycle](#scan-lifecycle) — `start` / `status` / `stop` / `report`
4. [Crawl integration](#crawl-integration--called-by-track-b) — `POST /crawl/state-visit`
5. [Violation reporting](#violation-reporting--called-by-track-c) — `POST /violations/report`
6. [Live events (WebSocket)](#live-events--websocket)
7. [Data models](#data-models)
8. [Technology stack justification](#technology-stack-justification)


## Ops

### `GET /health`
Liveness probe. Always open — no auth, ever (the Docker healthcheck hits this).

**Response `200`**
```json
{ "status": "ok", "version": "0.2.0", "auth_required": false }
```

| Field | Type | Description |
|---|---|---|
| `status` | string | Always `"ok"` while the process is up |
| `version` | string | API version |
| `auth_required` | boolean | `true` when `STATESCOUT_API_KEY` is set |

---

## Projects

A **Project** is a saved `(name, url, policy, role)` scan target, so a QA engineer can
re-run the same audit by id instead of retyping it. All project routes are protected
by the optional `X-API-Key`.

### `POST /projects`
Create a project. Returns **`ProjectResponse`** with a freshly minted `project_id` (UUID).

**Request body — `ProjectRequest`**
```json
{
  "name": "Staging — guest",
  "url": "https://staging.app.local",
  "policy": "A guest must never see an Admin link.",
  "role": "guest"
}
```
`role` defaults to `"guest"`; `name`, `url`, `policy` are required.

**Response `200` — `ProjectResponse`**
```json
{
  "project_id": "b1c2d3e4-...",
  "name": "Staging — guest",
  "url": "https://staging.app.local",
  "policy": "A guest must never see an Admin link.",
  "role": "guest",
  "created_at": 1735689600000,
  "updated_at": null
}
```

### `GET /projects`
List all saved projects. Returns `ProjectResponse[]`.

### `GET /projects/{project_id}`
Fetch one project. **`404`** if unknown.

### `PUT /projects/{project_id}`
Update a project's `name` / `url` / `policy` / `role` (body is a `ProjectRequest`).
Returns the updated `ProjectResponse`. **`404`** if unknown.

### `DELETE /projects/{project_id}`
Delete a project. **`204`** on success, **`404`** if unknown.

---

## Scan lifecycle

A **scan** is one crawl + audit run, identified by a fresh `scan_id` (UUID) minted on
`POST /scan/start`. The crawl runs as a FastAPI `BackgroundTask`
(`services.api.runner.run_scan`, which drives Track B's exploration loop against this
scan's `Neo4jGraph`). The endpoint returns immediately with `status: "queued"`; the
caller polls `GET /scan/{id}/status` or subscribes to the WebSocket for progress.

### `POST /scan/start`
Start a new crawl / audit.

**Request body — `StartScanRequest`.** Provide **either** `project_id`, **or**
`url` + `policy` (plus optional `role`, default `"guest"`):
```json
{ "url": "https://app.local/dashboard", "policy": "guest must never see an Admin link", "role": "guest" }
```
or
```json
{ "project_id": "b1c2d3e4-..." }
```

| Code | Condition |
|---|---|
| `200` | Scan accepted and queued |
| `404` | `project_id` was given but no such project exists |
| `422` | Neither `project_id` nor a complete `url` + `policy` was supplied (Pydantic validator) |
| `401` | Auth enabled and `X-API-Key` missing / wrong |

**Response `200` — `ScanStatusResponse`**
```json
{
  "scan_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "status": "queued",
  "states_explored": 0,
  "violations_found": 0,
  "message": "Scan f47ac10b-58cc-4372-a567-0e02b2c3d479 queued; the crawl is starting."
}
```

When `project_id` is used, the scan is linked to that project in Neo4j
(`(:Project)-[:HAS_SCAN]->(:PolicyContext)`) and the project's `url` / `policy` /
`role` win over anything else in the body.

### `GET /scan/{scan_id}/status`
Poll progress. Counts (`states_explored`, `violations_found`) are read live from Neo4j
by graph traversal, not cached in-process.

**Response `200` — `ScanStatusResponse`.** `status` is one of
`queued | running | stopping | stopped | completed | failed`.

- The `PolicyContext` node's own lifecycle status is returned when available.
- Otherwise the status is inferred from counts: `0` states + `0` violations →
  `queued` (this is also what an **unknown `scan_id`** returns — the endpoint does
  **not** 404, and does **not** report `failed` for an unknown id); any states seen →
  `running`.
- `failed` is only returned here when the Neo4j query itself throws (with a `message`).

This soft-response design is deliberate: the polling client always parses the body and
never has to branch on the HTTP status code for this route.

### `POST /scan/{scan_id}/stop`
Request a **graceful** stop. Records intent only — the in-flight crawl iteration is
allowed to finish before the loop exits with `termination_reason="stopped"`.

| Scan state when called | Effect | Response `status` |
|---|---|---|
| `queued` | finalised immediately (nothing is running) | `stopped` |
| `running` | status → `stopping`; the run's Redis visited-keys get a **1-hour grace TTL** instead of being deleted now; a `scan_stopping` event is broadcast | `stopping` |
| already terminal (`completed` / `failed` / `stopped`) | idempotent no-op | its existing terminal status, message `"Scan already ended."` |
| unknown `scan_id` | soft failure (no 404) | `failed`, message `"Unknown scan '<id>'."` |

**Response `200` — `ScanStatusResponse`.**

### `GET /scan/{scan_id}/report`
Full report for a scan. Returns **`ScanReportResponse`**.

```json
{
  "scan_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "url_scanned": "https://app.local/dashboard",
  "policy": "guest must never see an Admin link",
  "total_states": 6,
  "violations": [
    {
      "violation_id": "v-<state_id>-<expectation_id>",
      "state_fingerprint": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "url": "https://app.local/admin.html",
      "policy_violated": "A guest must never see an Admin link.",
      "clause_type": "forbidden_present",
      "severity": "high",
      "rationale": "Forbidden subject 'admin-access' is present for role 'guest'.",
      "evidence_summary": "Admin panel"
    }
  ],
  "scan_duration_seconds": 12.4
}
```

- `url_scanned`, `policy` and `scan_duration_seconds` are read back from the scan's
  `PolicyContext` node (`create_policy_context` writes `url_scanned` / `policy`;
  `record_scan_result` writes `duration_ms` once the run ends — reported here in
  seconds). A still-running scan shows `scan_duration_seconds: 0.0`.
- An **unknown `scan_id`** returns the same shape with `url_scanned: ""`, `policy: ""`,
  `total_states: 0`, `violations: []`, `scan_duration_seconds: 0.0` (a Neo4j error
  returns `url_scanned: "unknown"`, `policy: "unknown"`).
- `violations` is populated from `(:StateNode)-[:HAS_VIOLATION]->(:ViolationNode)`
  traversal. See *Known gaps* for the C-3 caveat on a live crawl.

---

## Crawl integration — called by Track B (the orchestrator)

### `POST /crawl/state-visit`
Track B (running out of process) calls this for **every** state the BFS loop visits.

**Request body — `CrawlStateUpdate`**
```json
{
  "scan_id": "f47ac10b-...",
  "url": "https://app.local/dashboard",
  "dom": "<html>...</html>",
  "ax_tree": { "...": "raw CDP accessibility-tree JSON" },
  "screenshot_path": "/tmp/shots/abc123.png",
  "title": "Dashboard",
  "depth": 0,
  "prev_state_fingerprint": null,
  "action_id": null,
  "action_label": "",
  "is_back_edge": false
}
```
`prev_state_fingerprint` / `action_id` are `null` on the first call of a scan (the
initial `open()` navigation) and populated on every subsequent call that followed an
action. `depth` is the BFS depth at which the state was first reached.

**What Track D does with it, in order:**
1. Fingerprints the raw `dom` + `url` + `ax_tree` server-side — **the caller never
   pre-computes the fingerprint** (centralising it here is the point).
2. Upserts (`MERGE`) the `StateNode`, deduplicated by fingerprint, and links it into
   this scan's `PolicyContext` (`:CONTAINS`).
3. If the edge fields are present, records (`CREATE`) the `ACTION` edge — never
   deduplicated, so cycles and repeat traversals are preserved (`is_back_edge` is
   stored on the relationship).
4. Broadcasts a `state_visited` event to any WebSocket subscribers on this `scan_id`.

**Response `200`**
```json
{ "accepted": true, "state_fingerprint": "e3b0c442..." }
```
On a persistence error: `{ "accepted": false, "error": "<detail>" }` (still HTTP 200).

---

## Violation reporting — called by Track C (perception + negation engine)

### `POST /violations/report`
Called once the deterministic negation engine confirms a violation for a state.

**Request body — `ViolationReport`** (field names map 1:1 onto the shared
`Violation` dataclass in `apps/agent/contracts.py`, so Track C builds this directly —
no translation layer):
```json
{
  "scan_id": "f47ac10b-...",
  "violation_id": "v-<state_id>-<expectation_id>",
  "state_fingerprint": "e3b0c442...",
  "expectation_id": "e-admin-access-forbidden",
  "clause_type": "forbidden_present",
  "severity": "high",
  "rationale": "Forbidden subject 'admin-access' is present for role 'guest'.",
  "url": "https://app.local/admin.html",
  "policy_violated": "A guest must never see an Admin link.",
  "evidence_selector": "role=link[name=\"Admin panel\"] >> nth=0",
  "evidence_text": "Admin panel",
  "evidence_screenshot_path": "/tmp/shots/abc123.png"
}
```

Persists a `ViolationNode` (`MERGE` on `violation_id`), links it to its `StateNode`
(`:HAS_VIOLATION`) and to an `ExpectationNode` (`:VIOLATES`), and broadcasts a
`violation_found` event.

**Response `200`**
```json
{ "recorded": true, "violation_id": "v-<state_id>-<expectation_id>" }
```
On a persistence error: `{ "recorded": false, "error": "<detail>" }` (still HTTP 200).

---

## Live events — WebSocket

### `WS /scan/{scan_id}/live`
The VS Code extension (or the demo console) connects here to receive push events as
the crawl runs. If auth is enabled, the handshake must carry a matching `X-API-Key`
header or the socket is closed with code **`1008`**.

Every message is a **`LiveEvent`**: `{ "event": <name>, "scan_id": <id>, "payload": {...} }`.

| `event` | Sent when | `payload` |
|---|---|---|
| `state_visited` | a new state is recorded (`/crawl/state-visit`) | `{ url, fingerprint, states_explored }` |
| `violation_found` | a violation is recorded (`/violations/report`) | `{ violation_id, url, rationale, severity, clause_type }` |
| `scan_stopping` | a graceful stop was requested | `{}` |
| `scan_stopped` | the crawl ended early on a stop request | `{ states, violations, termination_reason }` |
| `scan_completed` | the crawl finished normally | `{ states, violations, termination_reason }` |
| `scan_failed` | the crawl aborted with an error | `{ error }` or `{ states, violations, termination_reason }` depending on where it failed |

---

## Data models

Pydantic models, defined in `services/api/models.py`. **All request / response shapes
are frozen once published** (Execution Handbook §1.4) — a field rename or type change
is a cross-track decision, mirroring how `apps/agent/contracts.py` is frozen for the
internal ports.

### `StartScanRequest` — `POST /scan/start` body
| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `url` | string | conditional | `""` | required unless `project_id` is given |
| `policy` | string | conditional | `""` | required unless `project_id` is given |
| `role` | string | no | `"guest"` | ignored when `project_id` is given |
| `project_id` | string \| null | no | `null` | run a saved project; its url/policy/role win |

Validator: at least one of `project_id` **or** (`url` **and** `policy`) — else `422`.

### `ProjectRequest` — `POST /projects`, `PUT /projects/{id}` body
| Field | Type | Required | Default |
|---|---|---|---|
| `name` | string | yes | — |
| `url` | string | yes | — |
| `policy` | string | yes | — |
| `role` | string | no | `"guest"` |

### `ProjectResponse`
| Field | Type | Notes |
|---|---|---|
| `project_id` | string | UUID |
| `name`, `url`, `policy`, `role` | string | |
| `created_at` | int \| null | epoch ms |
| `updated_at` | int \| null | epoch ms |

### `ScanStatusResponse` — `POST /scan/start`, `GET /scan/{id}/status`, `POST /scan/{id}/stop`
| Field | Type | Default | Notes |
|---|---|---|---|
| `scan_id` | string | — | |
| `status` | string | — | `queued \| running \| stopping \| stopped \| completed \| failed` |
| `states_explored` | integer | `0` | live count from Neo4j |
| `violations_found` | integer | `0` | live count from Neo4j |
| `message` | string \| null | `null` | human-readable detail |

### `CrawlStateUpdate` — `POST /crawl/state-visit` body
| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `scan_id` | string | yes | — | |
| `url` | string | yes | — | |
| `dom` | string | yes | — | full page HTML |
| `ax_tree` | any (JSON) | yes | — | raw CDP accessibility tree |
| `screenshot_path` | string \| null | no | `null` | `null` in DOM-only smoke-test mode |
| `title` | string | no | `""` | |
| `depth` | integer ≥ 0 | no | `0` | BFS depth of first reach |
| `prev_state_fingerprint` | string \| null | no | `null` | omitted on the root state |
| `action_id` | string \| null | no | `null` | omitted on the root state |
| `action_label` | string | no | `""` | e.g. `click "Admin settings"` |
| `is_back_edge` | boolean | no | `false` | edge closes a cycle |

### `ViolationReport` — `POST /violations/report` body
| Field | Type | Required | Notes |
|---|---|---|---|
| `scan_id` | string | yes | |
| `violation_id` | string | yes | |
| `state_fingerprint` | string | yes | `state_id` of the violating state |
| `expectation_id` | string | yes | the `ExpectationNode` clause broken |
| `clause_type` | string | yes | `forbidden_present` (FR-18) or `required_absent` (FR-19) |
| `severity` | string | yes | `low \| medium \| high \| critical` |
| `rationale` | string | yes | plain-English explanation |
| `url` | string | yes | where the violation occurred |
| `policy_violated` | string | yes | the clause's `source_text` |
| `evidence_selector` | string \| null | no | |
| `evidence_text` | string \| null | no | |
| `evidence_screenshot_path` | string \| null | no | |

### `ViolationRecord` — nested in `ScanReportResponse.violations`
| Field | Type | Default | Notes |
|---|---|---|---|
| `violation_id` | string | — | |
| `state_fingerprint` | string | — | SHA-256 hex of the violating state |
| `url` | string | — | |
| `policy_violated` | string | — | |
| `clause_type` | string | `"forbidden_present"` | |
| `severity` | string | `"high"` | |
| `rationale` | string | `""` | |
| `evidence_summary` | string \| null | `null` | evidence text from the `ViolationNode` |

### `ScanReportResponse` — `GET /scan/{id}/report`
| Field | Type | Default | Notes |
|---|---|---|---|
| `scan_id` | string | — | |
| `url_scanned` | string | — | from the `PolicyContext` node |
| `policy` | string | — | from the `PolicyContext` node |
| `total_states` | integer | `0` | |
| `violations` | `ViolationRecord[]` | `[]` | |
| `scan_duration_seconds` | float | `0.0` | `duration_ms / 1000` once the run ends |

### `LiveEvent` — WebSocket push
| Field | Type | Notes |
|---|---|---|
| `event` | string | one of the six event names above |
| `scan_id` | string | |
| `payload` | object | event-specific, see the WebSocket table |

---

## Technology stack justification

### FastAPI
- **Async-native (ASGI / Starlette):** every endpoint is `async def`, so awaiting
  Neo4j / Redis I/O and the crawl's background work never blocks the HTTP server.
- **Pydantic integration:** request parsing, validation and response serialisation
  come from the type annotations — no manual `request.json()` / `jsonify()`.
- **OpenAPI auto-generation:** an accurate OpenAPI 3.x schema is produced from the
  type hints at no extra cost; the VS Code extension can consume it directly.
- **Lifespan hook:** the `lifespan` context manager opens and closes the Neo4j and
  Redis connections cleanly, so pools are never leaked between restarts or test runs.
- **`BackgroundTasks`:** `POST /scan/start` returns immediately and the crawl runs in
  the background — no long-held request, no extra worker/queue infrastructure for v1.

### Pydantic v2
- **Validation at the boundary:** invalid requests get an automatic structured `422`
  with field-level detail before the handler runs — no guard code.
- **Type safety at runtime:** `pydantic-core` (Rust) enforces the declared types,
  catching mismatches that would otherwise only surface at serialisation.
- **Single-file contract:** the canonical shapes live in `services/api/models.py`; any
  change is a visible diff to that one file, so contract drift is hard to miss.
- **`Field()` metadata:** each field's `description` / `examples` flow straight into
  the OpenAPI spec and Swagger UI.

### Neo4j
- **Cyclic directed graphs are native:** UI states are nodes, user actions are edges.
  A relational store needs recursive adjacency tables and CTEs; Neo4j stores this as
  `(:StateNode)-[:ACTION]->(:StateNode)` directly.
- **Cypher for traversal:** "every path from login that reaches a state with an Admin
  link" is a natural Cypher query and is optimised by the graph engine.
- **`MERGE` for node dedup:** `MERGE (s:StateNode {fingerprint: $fp})` is one atomic
  upsert — a revisited state (via a cycle) changes nothing. Matches the SHA-256
  fingerprint deduplication invariant exactly.
- **`CREATE` for edges:** every traversal is recorded as a distinct `:ACTION` edge,
  even a repeat — full cycle information is preserved for Track B's termination logic.

### Redis
- **O(1) membership check:** the `(state_id, action_id)` visited-set is a constant-time
  lookup regardless of how many states have been seen.
- **Cross-process:** the crawl worker and the API can be separate processes; an
  in-process `set` would be invisible across that boundary, and lost on restart.
- **Session-scoped TTL:** keys are namespaced per `scan_id` and expire on any terminal
  scan status (or get a 1-hour grace TTL on a graceful stop) — no explicit cleanup.
- **`flushdb()` for tests:** `VisitedCache.clear()` gives `fakeredis`-backed unit tests
  a guaranteed blank slate in one call.
