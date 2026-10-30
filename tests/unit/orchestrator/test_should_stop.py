"""A stop or deadline ends the run at once; it never drains the queued frontier."""

from __future__ import annotations

from apps.agent.orchestrator import graph_runner
from apps.agent.orchestrator.deps import Ports
from apps.agent.orchestrator.fakes import DEFAULT_POLICY, FakeCrawler, FakeGraph, FakePerception
from tests.unit.orchestrator.test_graph_runner import LOGIN, config


def _ports() -> Ports:
    return Ports(crawler=FakeCrawler(), perception=FakePerception(), graph=FakeGraph())


def test_should_stop_ends_the_run_as_stopped_without_draining() -> None:
    calls = {"n": 0}

    def stop_after_first_check() -> bool:
        calls["n"] += 1
        return calls["n"] > 1

    ports = _ports()
    result = graph_runner.explore(
        ports, LOGIN, DEFAULT_POLICY, config(), run_id="s", should_stop=stop_after_first_check
    )
    assert result.termination_reason == "stopped"
    assert result.skipped == ()  # nothing was drained as skips


def test_no_should_stop_behaves_as_before() -> None:
    result = graph_runner.explore(_ports(), LOGIN, DEFAULT_POLICY, config(), run_id="s")
    assert result.termination_reason != "stopped"


def test_run_audit_deadline_stops_promptly() -> None:
    import time

    from apps.agent.audit_models import AuditConfig
    from apps.agent.orchestrator.audit_runner import run_audit

    started = time.monotonic()
    report = run_audit(
        AuditConfig(url=LOGIN, max_seconds=0, auto_rules=False, probabilistic=False),
        _ports(),
        DEFAULT_POLICY,
    )
    assert report.status == "stopped"
    assert time.monotonic() - started < 5
    assert report.stats.get("skipped", 0) == 0
