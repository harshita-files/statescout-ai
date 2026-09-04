"""The whole loop against a real broken app, checked against documented truth.

Unit tests prove the loop behaves as designed. This proves the design finds what
it is supposed to find, on an application whose defects were written down before
the crawl ran — and, just as importantly, that it does **not** report anything
that was not planted. An auditor with false positives is one nobody reads.

Both implementations run every assertion, so the ground truth is also a parity
check.
"""

from __future__ import annotations

import pytest

from apps.agent.orchestrator import explore as reference
from apps.agent.orchestrator import graph_runner
from apps.agent.orchestrator.config import OrchestratorConfig
from apps.agent.orchestrator.deps import Ports
from apps.agent.orchestrator.fakes import FakeGraph, FakePerception
from apps.agent.orchestrator.state import ExplorationResult
from tests.fixtures.orchestrator import testapp

IMPLEMENTATIONS = {"reference": reference.explore, "langgraph": graph_runner.explore}


@pytest.fixture(scope="module")
def app() -> testapp.TestApp:
    return testapp.load("broken-admin")


@pytest.fixture(params=list(IMPLEMENTATIONS), ids=list(IMPLEMENTATIONS))
def crawl(request: pytest.FixtureRequest, app: testapp.TestApp) -> tuple[ExplorationResult, Ports]:
    """One full crawl of the demo app, and the ports it ran against."""
    ports = Ports(crawler=app.crawler(), perception=FakePerception(), graph=FakeGraph())
    config = OrchestratorConfig(
        _env_file=None,  # type: ignore[call-arg]
        role=app.role,
        depth_limit=10,
        max_states=50,
        perception_rate_per_min=0,
    )
    result = IMPLEMENTATIONS[request.param](ports, app.seed, app.policy, config, run_id="ground")
    return result, ports


# ---------------------------------------------------------------------------
# Recall and precision against the planted defects
# ---------------------------------------------------------------------------


def found_keys(
    result: ExplorationResult, ports: Ports, app: testapp.TestApp
) -> set[tuple[str, str, str]]:
    """Findings, rekeyed from fingerprints back to page paths."""
    pages = {state_id: path for path, state_id in app.state_ids(ports.graph.fingerprint).items()}
    return {
        (pages[v.state_id], v.expectation_id, v.clause_type)
        for v in result.violations
        if v.state_id in pages
    }


def test_every_planted_violation_is_found(
    crawl: tuple[ExplorationResult, Ports], app: testapp.TestApp
) -> None:
    """Recall. A miss here is the product failing at its one job."""
    result, ports = crawl
    missed = {v.key for v in app.expected} - found_keys(result, ports, app)
    assert not missed, f"planted violations the crawl did not find: {sorted(missed)}"


def test_nothing_unplanted_is_reported(
    crawl: tuple[ExplorationResult, Ports], app: testapp.TestApp
) -> None:
    """Precision. Every extra finding is noise a QA engineer has to triage, and
    enough of them make the report worthless even when the recall is perfect."""
    result, ports = crawl
    extra = found_keys(result, ports, app) - {v.key for v in app.expected}
    assert not extra, f"findings that were never planted: {sorted(extra)}"


def test_the_finding_count_matches_exactly(
    crawl: tuple[ExplorationResult, Ports], app: testapp.TestApp
) -> None:
    result, _ = crawl
    assert len(result.violations) == len(app.expected)


def test_both_clause_types_are_exercised(
    crawl: tuple[ExplorationResult, Ports],
) -> None:
    """FR-18 and FR-19 both fire on this app, which is the point of planting a
    missing element alongside three present ones."""
    result, _ = crawl
    assert {v.clause_type for v in result.violations} == {
        "forbidden_present",
        "required_absent",
    }


def test_a_violation_two_clicks_deep_is_still_found(
    crawl: tuple[ExplorationResult, Ports], app: testapp.TestApp
) -> None:
    """V-03 sits on `/pages/admin.html`, three states from the seed. A crawl that
    only audits the landing page would pass every other test in this file."""
    result, ports = crawl
    admin = app.state_ids(ports.graph.fingerprint)["/pages/admin.html"]
    assert any(
        v.state_id == admin and v.expectation_id == "e-delete-user" for v in result.violations
    )


def test_each_violation_carries_evidence_a_human_can_check(
    crawl: tuple[ExplorationResult, Ports],
) -> None:
    result, _ = crawl
    for violation in result.violations:
        assert violation.rationale
        if violation.clause_type == "forbidden_present":
            assert violation.evidence.selector, f"{violation.expectation_id} has no selector"


# ---------------------------------------------------------------------------
# Month 2 done-criteria
# ---------------------------------------------------------------------------


def test_the_crawl_terminates_on_its_own(crawl: tuple[ExplorationResult, Ports]) -> None:
    """ "Autonomous crawl of the multi-page test-app terminates" — and by frontier
    exhaustion, not by hitting a cap. A cap would mean the crawl was cut short and
    the coverage claim below is unearned."""
    result, _ = crawl
    assert result.termination_reason == "frontier_exhausted"


def test_every_state_is_discovered(
    crawl: tuple[ExplorationResult, Ports], app: testapp.TestApp
) -> None:
    result, _ = crawl
    assert result.states == app.expected_states


def test_zero_duplicate_state_action_pairs(
    crawl: tuple[ExplorationResult, Ports],
) -> None:
    """NFR-05. `visited_pairs` counts executions and the graph's visited set
    counts distinct pairs; they can only be equal if nothing ran twice."""
    result, ports = crawl
    graph: FakeGraph = ports.graph  # type: ignore[assignment]
    assert result.visited_pairs == len(graph.visited)


def test_the_persisted_graph_is_cyclic(crawl: tuple[ExplorationResult, Ports]) -> None:
    """ "Cyclic graph visible in Neo4j". Four cycles are documented in
    violations.json; the crawl must record back-edges rather than prune them into
    a tree."""
    _, ports = crawl
    graph: FakeGraph = ports.graph  # type: ignore[assignment]
    assert len(graph.back_edges()) >= 3


def test_every_state_is_reachable_from_the_seed(
    crawl: tuple[ExplorationResult, Ports], app: testapp.TestApp
) -> None:
    """A node with no inbound edge that is not the seed means the graph is lying
    about how the crawler got there."""
    _, ports = crawl
    graph: FakeGraph = ports.graph  # type: ignore[assignment]
    seed = app.state_ids(ports.graph.fingerprint)[app.seed]

    reachable = {seed}
    for _ in range(len(graph.states)):
        reachable |= {e.to_state_id for e in graph.edges if e.from_state_id in reachable}
    assert reachable == set(graph.states)


def test_nothing_was_skipped(crawl: tuple[ExplorationResult, Ports]) -> None:
    """This app has no side-effecting controls, so full coverage is achievable
    and any skip would be a real coverage hole rather than a documented one."""
    result, _ = crawl
    assert result.skipped == ()
