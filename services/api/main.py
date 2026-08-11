"""
FastAPI backend for StateScout AI — Track D.

Month 2 Scope
-------------
- POST /crawl/state-visit     — Track B sends raw CaptureBundle fields; Track D fingerprints
- POST /violations/report     — Track C sends confirmed violations
- WS   /scan/{id}/live        — WebSocket live event stream (violations + state visits)
- GET  /scan/{id}/status      — Real counts from Neo4j (not in-memory zeros)
- GET  /scan/{id}/report      — ViolationNodes from Neo4j (stub, full in Month 3)
- BackgroundTasks             — crawl launch does not block the HTTP response
- Structured logging          — JSON-friendly log lines throughout

Replaced in Month 2
-------------------
- in_memory_scans dict  →  Neo4j PolicyContext nodes
- zero counts           →  graph_store.get_scan_counts()

Run locally:
    uvicorn services.api.main:app --reload
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any

import redis as redis_lib
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.background import BackgroundTasks

from apps.agent.graph.graph_store import GraphStore
from services.api.models import (
    CrawlStateUpdate,
    LiveEvent,
    ScanReportResponse,
    ScanStatusResponse,
    StartScanRequest,
    ViolationRecord,
    ViolationReport,
)

# ---------------------------------------------------------------------------
# Logging — structured, one line per event
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("statescout.api")


# ---------------------------------------------------------------------------
# WebSocket connection manager
# ---------------------------------------------------------------------------


class ConnectionManager:
    """Tracks active WebSocket connections per scan_id.

    Uses asyncio.Queue per scan — simple and process-local.
    Replaced by Redis pub/sub in Month 3 if multi-worker deployment is needed.
    """

    def __init__(self) -> None:
        # scan_id -> list of active WebSocket connections
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, scan_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.setdefault(scan_id, []).append(ws)
        logger.info('"WebSocket connected for scan %s"', scan_id)

    def disconnect(self, scan_id: str, ws: WebSocket) -> None:
        conns = self._connections.get(scan_id, [])
        if ws in conns:
            conns.remove(ws)
        logger.info('"WebSocket disconnected for scan %s"', scan_id)

    async def broadcast(self, scan_id: str, event: LiveEvent) -> None:
        """Send event to all subscribers of this scan. Dead connections are pruned."""
        conns = list(self._connections.get(scan_id, []))
        dead: list[WebSocket] = []
        payload = event.model_dump_json()
        for ws in conns:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(scan_id, ws)


manager = ConnectionManager()


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open and close Neo4j + Redis connections around the app's lifetime."""
    import os

    # Skip real connections if state was pre-injected (e.g. by unit-test fixtures).
    _injected = hasattr(app.state, "graph") and app.state.graph is not None
    if not _injected:
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
        app.state.graph = GraphStore()
        app.state.redis = redis_lib.from_url(redis_url, decode_responses=True)  # type: ignore[no-untyped-call]
    logger.info('"StateScout API started"')
    yield
    if not _injected:
        app.state.graph.close()
    logger.info('"StateScout API shut down"')



# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="StateScout AI",
    description=(
        "Autonomous Vision-Language Agent for Logical UI Auditing.\n\n"
        "Track D — Data, API & Reporting backend.\n"
        "API contract frozen per handbook Section 1.4."
    ),
    version="0.2.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _graph(request: Any) -> GraphStore:
    """Access the shared GraphStore from a request's app state."""
    return request.app.state.graph


# ---------------------------------------------------------------------------
# Ops
# ---------------------------------------------------------------------------


@app.get("/health", tags=["ops"])
async def health_check() -> dict[str, str]:
    """Liveness probe. Returns 200 as long as the process is alive."""
    return {"status": "ok", "version": "0.2.0"}


# ---------------------------------------------------------------------------
# Scan lifecycle
# ---------------------------------------------------------------------------


@app.post("/scan/start", response_model=ScanStatusResponse, tags=["scan"])
async def start_scan(
    request_body: StartScanRequest,
    background_tasks: BackgroundTasks,
    request: Any = None,
) -> ScanStatusResponse:
    """Initiate a new crawl/audit.

    Returns immediately with scan_id and status=queued.
    The crawl is launched as a BackgroundTask so this endpoint never blocks.

    Month 2: PolicyContext is persisted to Neo4j; in_memory_scans is gone.
    """
    scan_id = str(uuid.uuid4())

    # Persist the scan session to Neo4j
    # (request is injected by FastAPI; we need app.state)
    # We access graph via app.state directly since we can't use Depends here easily
    graph: GraphStore = app.state.graph
    graph.create_policy_context(
        scan_id=scan_id,
        url=request_body.url,
        policy=request_body.policy,
        role=request_body.role,
    )

    # BackgroundTask placeholder — Track B's orchestrator drives the real crawl
    # once it integrates. For now this just marks the scan as running.
    async def _mark_running(sid: str) -> None:
        await asyncio.sleep(0)  # yield to event loop
        app.state.graph.update_scan_status(sid, "running")
        logger.info('"scan_started" {"scan_id": "%s"}', sid)

    background_tasks.add_task(_mark_running, scan_id)

    logger.info('"scan_queued" {"scan_id": "%s", "url": "%s"}', scan_id, request_body.url)

    return ScanStatusResponse(
        scan_id=scan_id,
        status="queued",
        states_explored=0,
        violations_found=0,
        message=(
            f"Scan {scan_id} queued. "
            "Track B's orchestrator will drive the crawl loop (Month 2 integration)."
        ),
    )


@app.get("/scan/{scan_id}/status", response_model=ScanStatusResponse, tags=["scan"])
async def get_scan_status(scan_id: str) -> ScanStatusResponse:
    """Poll scan progress. Returns real counts from Neo4j (Month 2).

    Returns status=failed with a message for unknown scan_ids rather than
    raising HTTP 404 — keeps the VS Code extension polling logic simple.
    """
    try:
        counts = app.state.graph.get_scan_counts(scan_id)
    except Exception as exc:
        logger.error('"get_scan_status_error" {"scan_id": "%s", "error": "%s"}', scan_id, exc)
        return ScanStatusResponse(
            scan_id=scan_id,
            status="failed",
            message=f"Failed to query scan status: {exc}",
        )

    if counts["states_explored"] == 0 and counts["violations_found"] == 0:
        # Could be a valid queued scan or an unknown id — return queued
        return ScanStatusResponse(
            scan_id=scan_id,
            status="queued",
            states_explored=0,
            violations_found=0,
        )

    return ScanStatusResponse(
        scan_id=scan_id,
        status="running",
        states_explored=counts["states_explored"],
        violations_found=counts["violations_found"],
    )


@app.get("/scan/{scan_id}/report", response_model=ScanReportResponse, tags=["scan"])
async def get_scan_report(scan_id: str) -> ScanReportResponse:
    """Retrieve the full audit report for a completed scan.

    Month 2: ViolationNodes are queried from Neo4j.
    Month 3: Full evidence-chain assembly via Cypher path queries.
    """
    try:
        counts = app.state.graph.get_scan_counts(scan_id)
        raw_violations = app.state.graph.get_violations_for_scan(scan_id)
    except Exception as exc:
        logger.error('"get_scan_report_error" {"scan_id": "%s", "error": "%s"}', scan_id, exc)
        return ScanReportResponse(
            scan_id=scan_id,
            url_scanned="unknown",
            policy="unknown",
        )

    violations = [
        ViolationRecord(
            violation_id=v.get("violation_id", ""),
            state_fingerprint=v.get("state_fingerprint", ""),
            url=v.get("url", ""),
            policy_violated=v.get("policy_violated", ""),
            clause_type=v.get("clause_type", "forbidden_present"),
            severity=v.get("severity", "high"),
            rationale=v.get("rationale", ""),
            evidence_summary=v.get("evidence_text"),
        )
        for v in raw_violations
    ]

    return ScanReportResponse(
        scan_id=scan_id,
        url_scanned="",  # Month 3: query from PolicyContext node
        policy="",  # Month 3: query from PolicyContext node
        total_states=counts["states_explored"],
        violations=violations,
        scan_duration_seconds=0.0,  # Month 3: store started_at and compute elapsed
    )


# ---------------------------------------------------------------------------
# Crawl integration — Track B
# ---------------------------------------------------------------------------


@app.post("/crawl/state-visit", tags=["crawl"])
async def receive_state_visit(update: CrawlStateUpdate) -> dict[str, Any]:
    """Track B calls this for every state the BFS loop visits.

    Track D:
    1. Fingerprints the raw DOM/URL/AX-tree (GraphPort decision 2)
    2. Persists the StateNode (MERGE — dedup by fingerprint, NFR-05)
    3. If edge fields present, persists the ActionEdge (CREATE — cycles preserved)
    4. Broadcasts a 'state_visited' LiveEvent to WebSocket subscribers
    """
    import json as _json

    from apps.agent.contracts import StateEdge, StateNode
    from apps.agent.graph.fingerprint import fingerprint

    ax_str = (
        _json.dumps(update.ax_tree, sort_keys=True, ensure_ascii=False)
        if isinstance(update.ax_tree, (dict, list))
        else str(update.ax_tree)
    )

    state_fp = fingerprint(update.dom, update.url, ax_str)

    graph: GraphStore = app.state.graph

    # Persist state node
    state = StateNode(
        state_id=state_fp,
        url=update.url,
        role="",  # role is on PolicyContext; StateNode is role-agnostic
        depth=0,  # Track B to provide depth in a future field (Month 3)
        title=update.title,
        screenshot_path=update.screenshot_path,
    )
    try:
        graph.persist_state(state)
    except Exception as exc:
        logger.error('"persist_state_error" {"fp": "%s", "error": "%s"}', state_fp[:8], exc)
        return {"accepted": False, "error": str(exc)}

    # Persist edge if this is not the root state
    if update.prev_state_fingerprint and update.action_id:
        edge = StateEdge(
            from_state_id=update.prev_state_fingerprint,
            to_state_id=state_fp,
            action_id=update.action_id,
            label=update.action_label,
            is_back_edge=update.is_back_edge,
        )
        try:
            graph.persist_edge(edge)
        except Exception as exc:
            logger.warning('"persist_edge_error" {"error": "%s"}', exc)

    # Broadcast live event
    counts = {"states_explored": 0, "violations_found": 0}
    with contextlib.suppress(Exception):
        counts = graph.get_scan_counts(update.scan_id)

    event = LiveEvent(
        event="state_visited",
        scan_id=update.scan_id,
        payload={
            "url": update.url,
            "fingerprint": state_fp,
            "states_explored": counts["states_explored"],
        },
    )
    await manager.broadcast(update.scan_id, event)

    logger.info(
        '"state_visited" {"scan_id": "%s", "fp": "%s", "url": "%s"}',
        update.scan_id,
        state_fp[:8],
        update.url,
    )

    return {"accepted": True, "state_fingerprint": state_fp}


# ---------------------------------------------------------------------------
# Violation reporting — Track C
# ---------------------------------------------------------------------------


@app.post("/violations/report", tags=["violations"])
async def receive_violation(report: ViolationReport) -> dict[str, Any]:
    """Track C calls this when the VLM + negation engine confirms a violation.

    Persists a ViolationNode, links it to its StateNode, and broadcasts
    a 'violation_found' LiveEvent to WebSocket subscribers.
    """
    from apps.agent.contracts import Evidence, Violation

    violation = Violation(
        violation_id=report.violation_id,
        state_id=report.state_fingerprint,
        expectation_id=report.expectation_id,
        clause_type=report.clause_type,
        severity=report.severity,
        rationale=report.rationale,
        evidence=Evidence(
            selector=report.evidence_selector,
            text=report.evidence_text,
            screenshot_path=report.evidence_screenshot_path,
        ),
    )

    graph: GraphStore = app.state.graph
    try:
        graph.persist_violation(violation)
    except Exception as exc:
        logger.error(
            '"persist_violation_error" {"vid": "%s", "error": "%s"}', report.violation_id, exc
        )
        return {"recorded": False, "error": str(exc)}

    event = LiveEvent(
        event="violation_found",
        scan_id=report.scan_id,
        payload={
            "violation_id": report.violation_id,
            "url": report.url,
            "rationale": report.rationale,
            "severity": report.severity,
            "clause_type": report.clause_type,
        },
    )
    await manager.broadcast(report.scan_id, event)

    logger.info(
        '"violation_recorded" {"scan_id": "%s", "vid": "%s", "clause": "%s"}',
        report.scan_id,
        report.violation_id,
        report.clause_type,
    )

    return {"recorded": True, "violation_id": report.violation_id}


# ---------------------------------------------------------------------------
# WebSocket — live event stream
# ---------------------------------------------------------------------------


@app.websocket("/scan/{scan_id}/live")
async def websocket_live(websocket: WebSocket, scan_id: str) -> None:
    """WebSocket endpoint for live crawl events.

    The VS Code extension connects here and receives LiveEvent JSON objects
    as Track B visits states and Track C reports violations.
    Connection is kept open until the client disconnects or the scan ends.
    """
    await manager.connect(scan_id, websocket)
    try:
        while True:
            # Keep the connection alive; events are pushed via manager.broadcast
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(scan_id, websocket)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("services.api.main:app", host="0.0.0.0", port=8000, reload=True)
