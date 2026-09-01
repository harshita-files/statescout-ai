"""The scan runner — Track D, Month 2 integration checkpoint.

`POST /scan/start` schedules `services.api.runner.run_scan`, which drives Track
B's compiled exploration loop (`graph_runner.explore`) with:

  - a **real** `Neo4jGraph(scan_id=…)` so the crawl persists to the scan's graph
  - Track A's crawler + Track C's perception when their modules exist, else the
    scripted fakes (`build_scan_ports` reports which)

and, on any terminal outcome, stamps the PolicyContext and expires the run's
Redis visited keys.

Neo4j is mocked, Redis is fakeredis, the crawler/perception are the fakes — so
this exercises the whole wiring without Docker.

Run:  pytest tests/unit/graph/test_runner.py -v
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import fakeredis
import pytest

import apps.agent.graph.cache as cache_module
from services.api import runner


@pytest.fixture
def mock_neo4j():
    with patch("apps.agent.graph.graph_store.GraphDatabase.driver") as mock_cls:
        drv = MagicMock()
        drv.verify_connectivity.return_value = None
        sess = MagicMock()
        drv.session.return_value.__enter__.return_value = sess
        mock_cls.return_value = drv
        yield drv


@pytest.fixture
def fake_redis(monkeypatch):
    fake = fakeredis.FakeStrictRedis(decode_responses=True)
    monkeypatch.setattr(cache_module.redis, "from_url", lambda url, decode_responses=True: fake)
    return fake


@pytest.fixture
def graph_store():
    """A GraphStore stand-in — the runner only calls lifecycle/record methods on it."""
    return MagicMock()


@pytest.fixture
def events():
    sink: list[tuple[str, str, dict]] = []
    return sink


def _emit(events):
    return lambda scan_id, event, payload: events.append((scan_id, event, payload))


class TestBuildScanPorts:
    def test_uses_fakes_and_reports_degraded_when_tracks_missing(self, mock_neo4j, fake_redis):
        from apps.agent.orchestrator.config import OrchestratorConfig

        cfg = OrchestratorConfig(_env_file=None, role="guest", perception_rate_per_min=0)
        with patch(
            "apps.agent.orchestrator.deps.live_ports",
            side_effect=NotImplementedError("Track A / Track C not landed"),
        ):
            ports, tags = runner.build_scan_ports("scan-1", cfg)

        assert tags["mode"] == "degraded"
        # the graph port is the real Neo4jGraph, scoped to this scan
        assert type(ports.graph).__name__ == "Neo4jGraph"
        assert ports.graph.scan_id == "scan-1"


class TestRunScan:
    def _run(self, scan_id, graph_store, events, stop_check=lambda: False):
        with patch("apps.agent.orchestrator.deps.live_ports", side_effect=NotImplementedError()):
            runner.run_scan(
                scan_id=scan_id,
                seed_url="http://fake.test/login",
                policy_text="a guest must never see an admin link",
                role="guest",
                graph_store=graph_store,
                emit=_emit(events),
                stop_check=stop_check,
            )

    def test_completes_and_marks_running_then_completed(
        self, mock_neo4j, fake_redis, graph_store, events
    ):
        self._run("scan-1", graph_store, events)

        statuses = [c.args[1] for c in graph_store.update_scan_status.call_args_list]
        assert statuses[0] == "running"
        assert statuses[-1] == "completed"

    def test_streams_state_visited_events_and_a_terminal_event(
        self, mock_neo4j, fake_redis, graph_store, events
    ):
        self._run("scan-1", graph_store, events)

        kinds = [e[1] for e in events]
        assert "state_visited" in kinds
        assert kinds[-1] == "scan_completed"

    def test_records_the_result_summary(self, mock_neo4j, fake_redis, graph_store, events):
        self._run("scan-1", graph_store, events)

        graph_store.record_scan_result.assert_called_once()
        kw = graph_store.record_scan_result.call_args
        # the scripted app has states and at least the planted admin-link violation path
        assert kw.kwargs["termination_reason"] == "frontier_exhausted"
        assert kw.kwargs["states"] > 0

    def test_expires_the_visited_cache_on_completion(
        self, mock_neo4j, fake_redis, graph_store, events
    ):
        self._run("scan-1", graph_store, events)
        # keys for this scan carry a TTL now
        for key in fake_redis.keys("session:scan-1:*"):
            assert fake_redis.ttl(key) > 0

    def test_stop_request_ends_the_run_as_stopped(
        self, mock_neo4j, fake_redis, graph_store, events
    ):
        calls = {"n": 0}

        def stop_after_first_scan() -> bool:
            calls["n"] += 1
            return calls["n"] > 1  # let the seed scan through, then stop

        self._run("scan-1", graph_store, events, stop_check=stop_after_first_scan)

        assert graph_store.update_scan_status.call_args_list[-1].args[1] == "stopped"
        assert events[-1][1] == "scan_stopped"

    def test_bad_seed_marks_failed(self, mock_neo4j, fake_redis, graph_store, events):
        with patch("apps.agent.orchestrator.deps.live_ports", side_effect=NotImplementedError()):
            runner.run_scan(
                scan_id="scan-x",
                seed_url="http://fake.test/does-not-exist",
                policy_text="",
                role="guest",
                graph_store=graph_store,
                emit=_emit(events),
                stop_check=lambda: False,
            )
        assert graph_store.update_scan_status.call_args_list[-1].args[1] == "failed"
