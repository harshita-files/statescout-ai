# `services/api` — FastAPI reporting backend (Track D)

Serves scan runs, exploration graphs, and violation reports to the VS Code
extension, and exposes the run-control endpoints (`/scan/start`, `/scan/{id}/stop`,
`/scan/{id}/status`) that the orchestrator honours.

**Owner:** Track D. Track B depends only on the run-control contract: a stop
signal must let the in-flight iteration finish, write a run manifest, checkpoint,
and exit cleanly (M4-P1). `POST /scan/{id}/stop` records the intent; the loop
polls `GraphStore.is_stop_requested(scan_id)` between iterations.

## Endpoints

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| GET | `/health` | none | liveness; reports `auth_required` |
| POST | `/scan/start` | key | create a `PolicyContext`, launch the crawl BackgroundTask |
| GET | `/scan/{id}/status` | key | lifecycle status + live counts from Neo4j |
| POST | `/scan/{id}/stop` | key | request a graceful stop |
| GET | `/scan/{id}/report` | key | violations for the scan (full evidence chains: Month 3) |
| POST | `/crawl/state-visit` | key | Track B → fingerprint + persist a state/edge |
| POST | `/violations/report` | key | Track C → persist a confirmed violation |
| WS | `/scan/{id}/live` | key (handshake) | `LiveEvent` stream |

## Auth (local-first, optional)

Set `STATESCOUT_API_KEY` (in `.env`, git-ignored per NFR-11) to require an
`X-API-Key` header on every route except `/health`; the WebSocket handshake must
carry the same header. **Unset ⇒ auth disabled** — the default for local dev and
CI. Single static key, no sessions, no JWT (handbook §1.2 rules out hosted /
multi-tenant auth for v1). See `auth.py`.

## Run

```bash
docker compose -f infra/docker-compose.yml up -d      # Neo4j + Redis
uv run uvicorn services.api.main:app --reload
```
