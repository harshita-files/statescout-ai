"""Scan runner — Track D, Month 2 integration checkpoint.

`POST /scan/start` schedules `run_scan`, which drives Track B's compiled
exploration loop (`apps.agent.orchestrator.graph_runner.explore`) end to end and
persists the crawl into the scan's graph.

Wiring
------
* **graph** — always the real `Neo4jGraph(scan_id=…)`, so nodes/edges land in
  this scan's `PolicyContext` (`get_scan_counts` traverses `:CONTAINS`).
* **crawler / perception** — Track A's Playwright crawler and Track C's VLM when
  those modules exist; otherwise the scripted fakes from
  `orchestrator/fakes.py`. `build_scan_ports` reports which via a `mode` tag
  stamped on the `PolicyContext` (`live` vs `degraded`) so a fake-driven crawl is
  never mistaken for a real audit.

Stop
----
`POST /scan/{id}/stop` sets an in-process flag; the injected logger raises
`_StopRequested` at the next `scan` boundary (the previous iteration's edge is
already persisted), and the run ends as `stopped`.

Streaming
---------
The same logger bridges `scan → scanned` and `audit → violation` events to the
`emit` callback the API hands in, which pushes them to WebSocket subscribers.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from apps.agent.graph.cache import VisitedCache
from apps.agent.graph.neo4j_graph import Neo4jGraph

if TYPE_CHECKING:
    from apps.agent.contracts import ExpectationSet
    from apps.agent.orchestrator.config import OrchestratorConfig
    from apps.agent.orchestrator.deps import Ports

logger = logging.getLogger("statescout.api.runner")

#: Redis visited keys get this TTL once a run reaches any terminal state, so they
#: expire instead of accumulating (a short window covers any final reads).
VISITED_TTL_TERMINAL_SECONDS = 300

EmitFn = Callable[[str, str, dict[str, Any]], None]
StopCheck = Callable[[], bool]


class _StopRequested(Exception):
    """Raised out of the loop's logger when a graceful stop has been requested."""


# ---------------------------------------------------------------------------
# Redis / lifecycle helpers — the single place the visited TTL is set
# ---------------------------------------------------------------------------


def set_visited_ttl(scan_id: str, seconds: int) -> None:
    """Expire a scan's Redis visited keys after `seconds`. Best effort."""
    with contextlib.suppress(Exception):
        VisitedCache(scan_id).set_ttl(seconds)


def finalize_scan_sync(graph_store: Any, scan_id: str, status: str) -> None:
    """Terminal transition: stamp the PolicyContext status, expire visited keys."""
    with contextlib.suppress(Exception):
        graph_store.update_scan_status(scan_id, status)
    set_visited_ttl(scan_id, VISITED_TTL_TERMINAL_SECONDS)


# ---------------------------------------------------------------------------
# Ports assembly
# ---------------------------------------------------------------------------


def build_scan_ports(scan_id: str, config: OrchestratorConfig) -> tuple[Ports, dict[str, str]]:
    """Real `Neo4jGraph` + real crawler/perception when available, else fakes.

    Returns the `Ports` and a tag dict describing what was actually wired.
    """
    from apps.agent.orchestrator.deps import Ports, build_ports

    graph = Neo4jGraph(scan_id=scan_id)
    try:
        live = build_ports(config, live=True)
    except NotImplementedError as exc:
        logger.info('"scan_degraded" {"scan_id": "%s", "reason": "%s"}', scan_id, exc)
        from apps.agent.orchestrator.fakes import FakeCrawler, FakePerception

        ports = Ports(
            crawler=FakeCrawler(role=config.role),
            perception=FakePerception(),
            graph=graph,
        )
        return ports, {"mode": "degraded", "crawler": "fake", "perception": "fake"}

    ports = Ports(crawler=live.crawler, perception=live.perception, graph=graph)
    return ports, {"mode": "live", "crawler": "playwright", "perception": "vlm"}


def _parse_policy(policy_text: str) -> ExpectationSet:
    """NL policy → ExpectationSet.

    Month 2 stub: no clauses. Track B's parser (FR-04) lands in Month 3; until
    then the crawl still builds the full graph, it just reports no violations.
    """
    from apps.agent.contracts import ExpectationSet

    return ExpectationSet()


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


def _make_logger(scan_id: str, emit: EmitFn, stop_check: StopCheck) -> Any:
    from apps.agent.orchestrator.runlog import Logger

    class _RunLogger(Logger):
        def __init__(self) -> None:
            super().__init__(scan_id, None)

        def emit(self, node: str, event: str, **fields: Any) -> None:
            if node == "scan" and event == "scanned":
                if stop_check():
                    raise _StopRequested
                emit(
                    scan_id,
                    "state_visited",
                    {"state_id": fields.get("state_id"), "depth": fields.get("depth")},
                )
            elif node == "audit" and event == "violation":
                emit(scan_id, "violation_found", dict(fields))

    return _RunLogger()


def run_scan(
    *,
    scan_id: str,
    seed_url: str,
    policy_text: str,
    role: str,
    graph_store: Any,
    emit: EmitFn,
    stop_check: StopCheck,
) -> None:
    """Drive one crawl to completion. Runs in a worker thread; never raises."""
    from apps.agent.orchestrator import graph_runner
    from apps.agent.orchestrator.config import OrchestratorConfig

    graph_store.update_scan_status(scan_id, "running")
    # Other knobs (depth_limit, max_states, perception_rate_per_min) come from
    # STATESCOUT_* env vars via pydantic-settings.
    config = OrchestratorConfig(role=role)

    try:
        ports, tags = build_scan_ports(scan_id, config)
    except Exception as exc:  # ports failed to assemble — nothing to run
        logger.exception('"scan_ports_error" {"scan_id": "%s"}', scan_id)
        finalize_scan_sync(graph_store, scan_id, "failed")
        emit(scan_id, "scan_failed", {"error": str(exc)})
        return

    with contextlib.suppress(Exception):
        graph_store.record_scan_mode(scan_id, tags)

    log = _make_logger(scan_id, emit, stop_check)
    result = None
    status = "failed"
    try:
        result = graph_runner.explore(
            ports, seed_url, _parse_policy(policy_text), config, run_id=scan_id, log=log
        )
        status = "completed" if result.termination_reason != "error" else "failed"
    except _StopRequested:
        status = "stopped"
        logger.info('"scan_stopped" {"scan_id": "%s"}', scan_id)
    except Exception:
        status = "failed"
        logger.exception('"scan_run_error" {"scan_id": "%s"}', scan_id)
    finally:
        with contextlib.suppress(Exception):
            ports.crawler.close()
        # GraphPort has no close(); Neo4jGraph does.
        graph_close = getattr(ports.graph, "close", None)
        if callable(graph_close):
            with contextlib.suppress(Exception):
                graph_close()

    if result is not None:
        with contextlib.suppress(Exception):
            graph_store.record_scan_result(
                scan_id,
                states=result.states,
                edges=result.edges,
                visited_pairs=result.visited_pairs,
                violations=len(result.violations),
                skipped=len(result.skipped),
                termination_reason=result.termination_reason,
                duration_ms=result.duration_ms,
            )

    finalize_scan_sync(graph_store, scan_id, status)
    emit(
        scan_id,
        f"scan_{status}",
        {
            "states": result.states if result is not None else 0,
            "violations": len(result.violations) if result is not None else 0,
            "termination_reason": result.termination_reason if result is not None else "error",
        },
    )
