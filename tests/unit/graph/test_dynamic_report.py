"""Optional dynamic snapshots: mocked store delegation and Neo4j persistence."""

import json
from unittest.mock import MagicMock, patch

import pytest

from apps.agent.graph.graph_store import GraphStore
from apps.agent.graph.neo4j_graph import Neo4jGraph


@pytest.fixture
def report():
    return {
        "transitions": [{"from": "a", "to": "b", "count": 2}],
        "replay_transitions": 1,
        "exact_hashes": ["hash-a", "hash-b"],
        "endpoints": ["/café"],
        "audits": {"a": 3},
        "hits": {"a": 1},
        "confidence": 0.75,
        "network_available": False,
    }


def test_graph_delegates_explicit_run_id_to_store(report):
    store = MagicMock()
    visited = MagicMock()
    graph = Neo4jGraph(scan_id="different-scan", store=store, visited=visited)
    store.assert_not_called()
    assert store.method_calls == []
    visited.reset_mock()
    store.get_dynamic_report.return_value = report

    graph.persist_dynamic_report("run-1", report)
    assert graph.get_dynamic_report("run-1") == report

    store.persist_dynamic_report.assert_called_once_with("run-1", report)
    store.get_dynamic_report.assert_called_once_with("run-1")
    assert visited.mock_calls == []


def test_graph_returns_none_for_missing_report():
    store = MagicMock()
    store.get_dynamic_report.return_value = None
    graph = Neo4jGraph(store=store, visited=MagicMock())
    assert graph.get_dynamic_report("missing") is None


@pytest.fixture
def store_session():
    with patch("apps.agent.graph.graph_store.GraphDatabase.driver") as driver:
        store = GraphStore()
        session = driver.return_value.session.return_value.__enter__.return_value
        yield store, session


def test_snapshot_write_is_parameterized_and_overwrites_by_run(store_session, report):
    store, session = store_session
    run_id = "run-'quoted'"
    store.persist_dynamic_report(run_id, report)
    first = session.run.call_args
    replacement = {**report, "hits": {}, "transitions": []}
    store.persist_dynamic_report(run_id, replacement)
    second = session.run.call_args

    assert first.args == second.args
    query = second.args[0]
    assert "MERGE (r:DynamicReport {run_id: $run_id})" in query
    assert "SET r.report_json = $report_json" in query
    assert "ON CREATE" not in query
    assert "ACTION" not in query
    assert "VisitedPair" not in query
    assert run_id not in query
    assert second.kwargs["run_id"] == run_id
    assert json.loads(first.kwargs["report_json"]) == report
    assert json.loads(second.kwargs["report_json"]) == replacement


def test_read_decodes_full_snapshot_and_scopes_by_run(store_session, report):
    store, session = store_session
    session.run.return_value.single.return_value = {"report_json": json.dumps(report)}
    assert store.get_dynamic_report("run-2") == report
    query = session.run.call_args.args[0]
    assert "MATCH (r:DynamicReport {run_id: $run_id})" in query
    assert session.run.call_args.kwargs == {"run_id": "run-2"}


@pytest.mark.parametrize("record", [None, {"report_json": None}])
def test_missing_snapshot_returns_none(store_session, record):
    store, session = store_session
    session.run.return_value.single.return_value = record
    assert store.get_dynamic_report("missing") is None


def test_empty_snapshot_is_distinct_from_missing(store_session):
    store, session = store_session
    session.run.return_value.single.return_value = {"report_json": "{}"}
    assert store.get_dynamic_report("empty") == {}


def test_non_json_report_fails_before_writing(store_session):
    store, session = store_session
    with pytest.raises(TypeError):
        store.persist_dynamic_report("run", {"hits": object()})
    session.run.assert_not_called()
