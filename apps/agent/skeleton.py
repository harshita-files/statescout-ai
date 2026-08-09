"""The walking skeleton (M1-P3).

A linear script — no LangGraph, no BFS, no frontier — that wires all five stages
end to end for **one** state:

    open -> fingerprint -> persist -> analyze -> audit -> report

Its job is to prove the seams fit. A walking skeleton that runs is worth more
than a clever loop that cannot reach a database, because every later milestone
adds machinery *between* these stages rather than replacing them. `explore.py`
(M2-P1) keeps this exact order and wraps it in a frontier.

What it is not
--------------
Not the orchestrator. It deliberately has no visited set, no cycle handling, no
checkpointing, and it never calls `act()`. One state, one report, exit.

It also contains **no port logic**. Every capture, judgement, and write belongs
to another track; this file only sequences them.

Usage
-----
    uv run python -m apps.agent.skeleton --fake
    uv run python -m apps.agent.skeleton --fake --url http://fake.test/login
    uv run python -m apps.agent.skeleton --live --url https://app.example.com

Streams and exit codes are CI-shaped: the JSON report goes to **stdout**, the
structured log to **stderr**, and a detected violation is exit 1 so a pipeline
step fails on it without parsing anything.

    0  clean
    1  at least one violation found
    2  the run could not complete (bad URL, missing implementation, port failure)
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
import uuid
from collections.abc import Sequence

from apps.agent.contracts import (
    CaptureBundle,
    ExpectationNode,
    ExpectationSet,
    Role,
    StateNode,
    StateScoutError,
    Violation,
)
from apps.agent.orchestrator.deps import Ports, fake_ports, live_ports
from apps.agent.orchestrator.runlog import Logger

__all__ = [
    "EXIT_CLEAN",
    "EXIT_ERROR",
    "EXIT_VIOLATION",
    "SKELETON_POLICY",
    "Logger",
    "main",
    "run_once",
]

EXIT_CLEAN = 0
EXIT_VIOLATION = 1
EXIT_ERROR = 2

DEFAULT_FAKE_URL = "http://fake.test/dashboard"

#: One hardcoded rule, per M1-P3. The real policy pipeline is Month 3; until then
#: this single clause is enough to prove a violation can travel from a rendered
#: page all the way to a non-zero exit code.
SKELETON_POLICY = ExpectationSet(
    forbidden=(
        ExpectationNode(
            expectation_id="e-admin-link",
            polarity="must_not_exist",
            subject="admin-link",
            roles=("guest",),
            source_text="A guest must never see the admin link.",
        ),
    )
)


def run_once(
    ports: Ports,
    url: str,
    role: Role,
    policy: ExpectationSet,
    log: Logger,
) -> tuple[list[Violation], CaptureBundle]:
    """The five stages, in the order every later milestone preserves.

    Raises:
        StateScoutError: any port failure. The caller turns it into exit 2 —
            deciding what a failure *means* is the orchestrator's job, not a
            port's, and certainly not this script's.
    """
    started = time.perf_counter()

    # 1. Capture -----------------------------------------------------------
    bundle = ports.crawler.open(url)
    log.emit("capture", "captured", url=bundle.url, title=bundle.title)

    # 2. Fingerprint -------------------------------------------------------
    state_id = ports.graph.fingerprint(bundle)
    log.emit("fingerprint", "fingerprinted", state_id=state_id)

    # 3. Persist -----------------------------------------------------------
    ports.graph.persist_state(
        StateNode(
            state_id=state_id,
            url=bundle.url,
            role=role,
            depth=0,
            title=bundle.title,
            screenshot_path=bundle.screenshot_path,
        )
    )
    log.emit("persist", "state_persisted", state_id=state_id, depth=0)

    # 4. Perceive ----------------------------------------------------------
    ui_map = ports.perception.analyze(bundle, role)
    state_id_matches = ui_map.state_id == state_id
    log.emit(
        "perceive",
        "analyzed",
        state_id=state_id,
        elements=len(ui_map.elements),
        # ADR-001 decision 8: nothing guarantees these agree, so say so out loud
        # rather than discovering it when a report joins to zero rows.
        state_id_matches_fingerprint=state_id_matches,
    )
    if not state_id_matches:
        raise StateScoutError(
            f"perception returned state_id={ui_map.state_id} but fingerprint={state_id}"
        )

    # 5. Audit -------------------------------------------------------------
    violations = list(ports.perception.audit(ui_map, policy))
    for violation in violations:
        ports.graph.persist_violation(violation)
        log.emit(
            "audit",
            "violation",
            state_id=state_id,
            expectation_id=violation.expectation_id,
            clause_type=violation.clause_type,
            severity=violation.severity,
        )

    log.emit(
        "audit",
        "audited",
        state_id=state_id,
        violations=len(violations),
        duration_ms=round((time.perf_counter() - started) * 1000, 3),
    )
    return violations, bundle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="statescout-skeleton",
        description="Walking skeleton: audit exactly one UI state, end to end.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--fake",
        action="store_true",
        help="use the in-memory scripted app; no browser, model, or database",
    )
    mode.add_argument(
        "--live",
        action="store_true",
        help="use the real crawler, VLM, and graph (once those tracks land)",
    )
    parser.add_argument(
        "--url",
        help=f"state to audit; defaults to {DEFAULT_FAKE_URL} with --fake, required with --live",
    )
    parser.add_argument("--role", default="guest", help="role to browse as (default: guest)")
    parser.add_argument(
        "--run-id",
        help="override the generated run id; use it to make a run reproducible",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    run_id = args.run_id or f"run-{uuid.uuid4().hex[:12]}"
    log = Logger(run_id, sys.stderr)

    url = args.url or (DEFAULT_FAKE_URL if args.fake else None)
    if url is None:
        log.emit("startup", "failed", reason="--live requires --url")
        return EXIT_ERROR

    mode = "fake" if args.fake else "live"
    log.emit("startup", "started", mode=mode, url=url, role=args.role)

    try:
        ports = fake_ports(role=args.role) if args.fake else live_ports(role=args.role)
    except NotImplementedError as exc:
        log.emit("startup", "failed", reason=str(exc))
        return EXIT_ERROR

    try:
        violations, bundle = run_once(ports, url, args.role, SKELETON_POLICY, log)
    except StateScoutError as exc:
        log.emit("run", "failed", error_type=type(exc).__name__, reason=str(exc))
        return EXIT_ERROR
    finally:
        ports.crawler.close()

    report = {
        "run_id": run_id,
        "mode": mode,
        "url": bundle.url,
        "role": args.role,
        "state_id": ports.graph.fingerprint(bundle),
        "violations": [dataclasses.asdict(v) for v in violations],
        "counts": {"states": 1, "edges": 0, "violations": len(violations)},
    }
    sys.stdout.write(json.dumps(report, indent=2) + "\n")

    exit_code = EXIT_VIOLATION if violations else EXIT_CLEAN
    log.emit("shutdown", "finished", violations=len(violations), exit_code=exit_code)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
