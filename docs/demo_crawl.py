"""One command that crawls the demo app and scores itself against ground truth.

    uv run python docs/demo_crawl.py

Lives in `docs/` because it is a presentation aid, not product code — but it
imports the real loop and the real ground-truth loader rather than restating
either, so it cannot show something the test suite does not also prove.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apps.agent.orchestrator.config import OrchestratorConfig  # noqa: E402
from apps.agent.orchestrator.deps import Ports  # noqa: E402
from apps.agent.orchestrator.fakes import FakeGraph, FakePerception  # noqa: E402
from apps.agent.orchestrator.graph_runner import explore  # noqa: E402
from tests.fixtures.orchestrator import testapp  # noqa: E402

BOLD, DIM, GREEN, RED, RESET = "\033[1m", "\033[2m", "\033[32m", "\033[31m", "\033[0m"


def rule(title: str) -> None:
    print(f"\n{BOLD}{title}{RESET}\n{DIM}{'─' * 72}{RESET}")


def main() -> int:
    app = testapp.load("broken-admin")
    ports = Ports(crawler=app.crawler(), perception=FakePerception(), graph=FakeGraph())
    config = OrchestratorConfig(
        _env_file=None,  # type: ignore[call-arg]
        role=app.role,
        depth_limit=10,
        max_states=50,
        perception_rate_per_min=0,
    )

    rule(f"Crawling test-apps/{app.name}  ·  seed {app.seed}  ·  role {app.role}")
    result = explore(ports, app.seed, app.policy, config, run_id="demo")

    graph: FakeGraph = ports.graph  # type: ignore[assignment]
    pages = {sid: path for path, sid in app.state_ids(graph.fingerprint).items()}

    rule("The exploration graph")
    for path, state_id in sorted(app.state_ids(graph.fingerprint).items()):
        node = graph.states[state_id]
        print(f"  {state_id}  depth {node.depth}  {path}")
    print()
    for edge in graph.edges:
        marker = f"{DIM}(back-edge, cycle closed){RESET}" if edge.is_back_edge else ""
        print(f"  {pages[edge.from_state_id]:26} ──▶ {pages[edge.to_state_id]:26} {marker}")

    rule("Findings, scored against test-apps/broken-admin/violations.json")
    found = {(pages[v.state_id], v.expectation_id, v.clause_type) for v in result.violations}
    planted = {v.key: v for v in app.expected}

    for key, expected in sorted(planted.items()):
        hit = key in found
        mark = f"{GREEN}FOUND  {RESET}" if hit else f"{RED}MISSED {RESET}"
        print(f"  {mark} {expected.id}  {expected.clause_type:18} {expected.expectation_id:16} {expected.page}")
    for extra in sorted(found - set(planted)):
        print(f"  {RED}EXTRA  {RESET} (not planted) {extra}")

    rule("Summary")
    stats = [
        ("termination", result.termination_reason),
        ("states", f"{result.states} (expected {app.expected_states})"),
        ("edges", result.edges),
        ("(state, action) pairs executed", result.visited_pairs),
        ("distinct pairs claimed", f"{len(graph.visited)}   <- NFR-05: equal means zero duplicates"),
        ("cycles recorded (back-edges)", len(graph.back_edges())),
        ("re-navigations (path replay)", f"{result.replays} replays / {result.replay_steps} steps"),
        ("actions skipped", len(result.skipped)),
        ("violations", f"{len(result.violations)} found / {len(app.expected)} planted"),
    ]
    for label, value in stats:
        print(f"  {label:32} {value}")

    exact = found == set(planted)
    verdict = (
        f"{GREEN}EXACT MATCH{RESET} — every planted violation found, nothing invented"
        if exact
        else f"{RED}MISMATCH{RESET} — see FOUND/MISSED/EXTRA above"
    )
    print(f"\n  {verdict}\n")
    return 0 if exact else 1


if __name__ == "__main__":
    raise SystemExit(main())
