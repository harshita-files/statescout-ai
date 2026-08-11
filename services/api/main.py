"""
FastAPI backend for StateScout AI — Track D.

Month 1 Scope
-------------
- Accepts scan requests and returns a scan_id immediately (no real crawl yet)
- In-memory scan store (dict) — replaces with Neo4j in Month 2
- No auth (added in Month 4, local-first only per handbook Section 2.1)

Month 2+
--------
- Replace in_memory_scans with Neo4j-backed persistence
- Use BackgroundTasks to run crawl loop without blocking the HTTP response
- Add WebSocket endpoint for live violation streaming

Endpoints
---------
GET  /health                       — liveness probe
POST /scan/start                   — start a new scan
GET  /scan/{scan_id}/status        — poll scan progress
GET  /scan/{scan_id}/report        — retrieve completed scan report

Run locally:
    python -m services.api.main
    # or:
    uvicorn services.api.main:app --reload
"""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from services.api.models import (
    ScanReportResponse,
    ScanStatusResponse,
    StartScanRequest,
)

# ---------------------------------------------------------------------------
# In-memory scan store (Month 1 placeholder)
# Replaced by Neo4j queries in Month 2.
# ---------------------------------------------------------------------------
in_memory_scans: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup / shutdown hook.
    Month 1: nothing to initialise or clean up.
    Month 2: open Neo4j + Redis connections here; close on shutdown.
    """
    print("StateScout API starting up...")
    yield
    print("StateScout API shutting down...")


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="StateScout AI",
    description=(
        "Autonomous Vision-Language Agent for Logical UI Auditing.\n\n"
        "Track D — Data, API & Reporting backend.\n"
        "API contract is frozen per handbook Section 1.4; shape changes require "
        "team coordination."
    ),
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health", tags=["ops"])
async def health_check() -> dict[str, str]:
    """
    Liveness probe.

    Returns 200 OK as long as the process is running.
    In Month 2, this will also check Neo4j + Redis connectivity.
    """
    return {"status": "ok", "version": "0.1.0"}


@app.post("/scan/start", response_model=ScanStatusResponse, tags=["scan"])
async def start_scan(request: StartScanRequest) -> ScanStatusResponse:
    """
    Initiate a new crawl / audit.

    Returns immediately with a ``scan_id`` and ``status: queued``.

    **Month 1 behaviour:** The scan record is stored in memory only; no actual
    crawl is performed.  Track B's orchestrator will trigger the real crawl
    once it is ready (Month 2).
    """
    scan_id = str(uuid.uuid4())
    in_memory_scans[scan_id] = {
        "url": request.url,
        "policy": request.policy,
        "status": "queued",
        "started_at": time.time(),
        "states_explored": 0,
        "violations_found": 0,
    }
    return ScanStatusResponse(
        scan_id=scan_id,
        status="queued",
        states_explored=0,
        violations_found=0,
        message=(
            f"Scan {scan_id} queued. "
            "Crawl will begin when Track B's orchestrator is integrated (Month 2)."
        ),
    )


@app.get("/scan/{scan_id}/status", response_model=ScanStatusResponse, tags=["scan"])
async def get_scan_status(scan_id: str) -> ScanStatusResponse:
    """
    Poll the status of a running or completed scan.

    Returns 404-equivalent (status=failed with a message) for unknown scan ids
    rather than raising an HTTP exception, so the VS Code extension can handle
    it without error-branch logic.
    """
    scan = in_memory_scans.get(scan_id)
    if not scan:
        return ScanStatusResponse(
            scan_id=scan_id,
            status="failed",
            message=f"Scan '{scan_id}' not found. It may have been created in a previous "
                    "server session (Month 1 uses in-memory storage).",
        )
    return ScanStatusResponse(
        scan_id=scan_id,
        status=scan["status"],
        states_explored=scan["states_explored"],
        violations_found=scan["violations_found"],
    )


@app.get("/scan/{scan_id}/report", response_model=ScanReportResponse, tags=["scan"])
async def get_scan_report(scan_id: str) -> ScanReportResponse:
    """
    Retrieve the full report for a completed scan.

    **Month 1 behaviour:** Returns an empty violations list regardless of scan
    state.  Full evidence-chain assembly from Neo4j is implemented in Month 3.
    """
    scan = in_memory_scans.get(scan_id)
    if not scan:
        return ScanReportResponse(
            scan_id=scan_id,
            url_scanned="unknown",
            policy="unknown",
            total_states=0,
            violations=[],
            scan_duration_seconds=0.0,
        )
    elapsed = time.time() - scan.get("started_at", time.time())
    return ScanReportResponse(
        scan_id=scan_id,
        url_scanned=scan.get("url", ""),
        policy=scan.get("policy", ""),
        total_states=scan.get("states_explored", 0),
        violations=[],   # Placeholder — Month 3 assembles evidence chains from Neo4j
        scan_duration_seconds=round(elapsed, 3),
    )


# ---------------------------------------------------------------------------
# Entry point (for `python -m services.api.main`)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "services.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
