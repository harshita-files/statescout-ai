"""LIVE integration — the Month 2 demo, asserted against real Neo4j + Redis.

Requires the stack:

    docker compose -f infra/docker-compose.yml up -d

Run:

    uv run pytest -m live tests/integration/graph/test_live_crawl.py -v

Excluded from the default CI gate (`pytest -m "not live"`). If the stack is not
reachable the whole module skips rather than errors.

It drives Track B's real exploration loop over the scripted 4-page cyclic app
(`orchestrator/fakes.DEFAULT_APP`) with the **real** `Neo4jGraph` + Redis
`VisitedCache`, then queries Neo4j directly to check the graph the crawl built:

  - the crawl terminates (`frontier_exhausted`)
  - nodes are deduped by fingerprint — 4 states, though cycles revisit them (NFR-05)
  - back-edges are recorded, never pruned (the graph stays cyclic)
  - every `:ACTION` traversal is persisted (`edges == result.edges`)
  - 0 duplicate `(state, action)` exploration (NFR-05)
  - the whole `services.api.runner.run_scan` path stamps the PolicyContext

Cleanup deletes everything the scan's `PolicyContext` reaches; on a shared Neo4j
that could touch `StateNode`s another scan also links. Use a throwaway database.
"""

from __future__ import annotations

import contextlib
import uuid

import pytest

pytestmark = pytest.mark.live

SEED = "http://fake.test/login"


@pytest.fixture
def scan_id() -> str:
    return f"itest-{uuid.uuid4().hex[:12]}"


@pytest.fixture
def stack(scan_id: str):
    """Real `GraphStore` + `Neo4jGraph` + a PolicyContext for this scan.

    Skips the module if Neo4j/Redis are down. Tears down everything the scan
    wrote (nodes via CONTAINS, its violations, its Redis keys).
    """
    store = None
    try:
        from apps.agent.graph.graph_store import GraphStore
        from apps.agent.graph.neo4j_graph import Neo4jGraph

        store = GraphStore()
        graph = Neo4jGraph(scan_id=scan_id, store=store)
    except Exception as exc:  # ServiceUnavailable, ConnectionError, OSError, ...
        if store is not None:
            with contextlib.suppress(Exception):
                store.close()
        pytest.skip(f"Neo4j/Redis not reachable ({exc}) — run docker compose up")

    store.create_policy_context(scan_id, SEED, "a guest must never see the admin link", "guest")
    try:
        yield store, graph
    finally:
        with store.driver.session() as session:
            session.run(
                "MATCH (p:PolicyContext {scan_id: $sid}) "
                "OPTIONAL MATCH (p)-[:CONTAINS]->(s:StateNode) "
                "OPTIONAL MATCH (s)-[:HAS_VIOLATION]->(v:ViolationNode) "
                "DETACH DELETE p, s, v",
                sid=scan_id,
            )
            # ViolationNodes minted by FakePerception aren't linked to any state
            # (see the xfail on test_violations_link_to_their_state) — sweep them,
            # and the ExpectationNodes persist_violation MERGEd alongside.
            session.run(
                "MATCH (v:ViolationNode) WHERE v.violation_id STARTS WITH 'v-s-' DETACH DELETE v"
            )
            session.run(
                "MATCH (e:ExpectationNode) WHERE NOT (e)<-[:HAS_EXPECTATION]-() DETACH DELETE e"
            )
        graph._visited.clear()
        store.close()


def _graph_counts(store, scan_id: str) -> dict[str, int]:
    """Shape of the graph this scan built. Separate one-hop queries — stacking
    several OPTIONAL MATCHes over :ACTION in one statement cross-multiplies rows."""
    with store.driver.session() as session:
        nodes = session.run(
            "MATCH (:PolicyContext {scan_id: $sid})-[:CONTAINS]->(s:StateNode) "
            "RETURN count(DISTINCT s) AS n",
            sid=scan_id,
        ).single()["n"]
        edge_rec = session.run(
            "MATCH (:PolicyContext {scan_id: $sid})-[:CONTAINS]->(s:StateNode) "
            "MATCH (s)-[e:ACTION]->() "
            "RETURN count(e) AS edges, "
            "       count(CASE WHEN e.is_back_edge THEN 1 END) AS back_edges",
            sid=scan_id,
        ).single()
        violations = session.run(
            "MATCH (:PolicyContext {scan_id: $sid})-[:CONTAINS]->(:StateNode)"
            "-[h:HAS_VIOLATION]->() RETURN count(h) AS n",
            sid=scan_id,
        ).single()["n"]
    return {
        "nodes": nodes,
        "edges": edge_rec["edges"],
        "back_edges": edge_rec["back_edges"],
        "violations": violations,
    }


class TestLiveCrawl:
    def test_loop_builds_a_correct_deduped_cyclic_graph(self, stack, scan_id):
        store, graph = stack
        from apps.agent.orchestrator import graph_runner
        from apps.agent.orchestrator.config import OrchestratorConfig
        from apps.agent.orchestrator.deps import Ports
        from apps.agent.orchestrator.fakes import DEFAULT_POLICY, FakeCrawler, FakePerception

        config = OrchestratorConfig(
            _env_file=None,
            role="guest",
            perception_rate_per_min=0,
            max_states=50,
            depth_limit=10,
        )
        ports = Ports(
            crawler=FakeCrawler(role="guest"),
            perception=FakePerception(),
            graph=graph,
        )

        result = graph_runner.explore(ports, SEED, DEFAULT_POLICY, config, run_id=scan_id)

        # 1. it terminates, and cleanly
        assert result.termination_reason == "frontier_exhausted"

        db = _graph_counts(store, scan_id)

        # 2. deduped by fingerprint: the scripted app has exactly 4 distinct
        #    states even though the crawl revisits them through cycles
        assert db["nodes"] == 4
        assert len(result.order) > db["nodes"], "expected revisits — cycles were not walked"

        # 3. every traversal recorded, nothing pruned
        assert db["edges"] == result.edges

        # 4. the graph stayed cyclic — a back-edge was kept, not dropped
        assert db["back_edges"] >= 1

        # 5. NFR-05 — 0 duplicate (state, action) exploration
        keys = graph._visited.r.keys(f"session:{scan_id}:visited:*")
        assert len(keys) == result.visited_pairs
        assert len(set(keys)) == len(keys)

        # 6. the loop detects the planted violation …
        assert any(v.expectation_id == "e-admin-link" for v in result.violations)
        # … and persist_violation writes a ViolationNode
        with store.driver.session() as session:
            vnodes = session.run("MATCH (v:ViolationNode) RETURN count(v) AS n").single()["n"]
        assert vnodes >= 1

        # 7. the chunk-1 fix: live state counts traverse CONTAINS
        counts = store.get_scan_counts(scan_id)
        assert counts["states_explored"] == 4

    @pytest.mark.xfail(
        reason="ADR-001 #8 / action C-3 (open): FakePerception mints SemanticUIMap.state_id "
        "with fakes._fingerprint ('s-…') while the real Neo4jGraph mints SHA-256, so "
        "persist_violation's MATCH (s:StateNode {fingerprint: violation.state_id}) finds "
        "nothing and no (:StateNode)-[:HAS_VIOLATION]->(:ViolationNode) edge is created. "
        "Resolved once analyze() takes the state_id or SemanticUIMap drops it.",
        strict=True,
    )
    def test_violations_link_to_their_state(self, stack, scan_id):
        store, graph = stack
        from apps.agent.orchestrator import graph_runner
        from apps.agent.orchestrator.config import OrchestratorConfig
        from apps.agent.orchestrator.deps import Ports
        from apps.agent.orchestrator.fakes import DEFAULT_POLICY, FakeCrawler, FakePerception

        config = OrchestratorConfig(
            _env_file=None, role="guest", perception_rate_per_min=0, max_states=50, depth_limit=10
        )
        ports = Ports(crawler=FakeCrawler(role="guest"), perception=FakePerception(), graph=graph)
        graph_runner.explore(ports, SEED, DEFAULT_POLICY, config, run_id=scan_id)

        assert store.get_scan_counts(scan_id)["violations_found"] >= 1

    def test_run_scan_stamps_the_policy_context(self, stack, scan_id):
        store, _ = stack
        from services.api import runner

        events: list[tuple] = []
        runner.run_scan(
            scan_id=scan_id,
            seed_url=SEED,
            policy_text="a guest must never see the admin link",
            role="guest",
            graph_store=store,
            emit=lambda *a: events.append(a),
            stop_check=lambda: False,
        )

        scan = store.get_scan(scan_id)
        assert scan is not None
        assert scan["status"] == "completed"
        assert scan["mode"] == "degraded"  # Track A/C not landed → scripted fakes
        assert scan["termination_reason"] == "frontier_exhausted"
        assert scan["states_explored"] == 4
        assert [e[1] for e in events][-1] == "scan_completed"

        # visited keys were given a TTL on completion, not left to leak
        cache = runner.VisitedCache(scan_id)
        ttls = [cache.r.ttl(k) for k in cache.r.keys(f"session:{scan_id}:*")]
        assert ttls and all(t > 0 for t in ttls)

    def test_project_crud_and_link(self, stack, scan_id):
        store, _ = stack
        pid = f"itest-proj-{scan_id}"
        try:
            store.create_project(pid, "live test", "http://fake.test/login", "no admin", "guest")
            assert store.get_project(pid)["name"] == "live test"
            assert any(p["project_id"] == pid for p in store.list_projects())
            assert store.update_project(pid, name="renamed") is True
            assert store.get_project(pid)["name"] == "renamed"

            store.create_policy_context(scan_id, "http://fake.test/login", "no admin", "guest")
            store.link_scan_to_project(pid, scan_id)
            with store.driver.session() as s:
                linked = s.run(
                    "MATCH (:Project {project_id: $pid})-[:HAS_SCAN]->(pc:PolicyContext) "
                    "RETURN pc.scan_id AS sid",
                    pid=pid,
                ).single()
            assert linked["sid"] == scan_id

            assert store.delete_project(pid) is True
            assert store.get_project(pid) is None
            assert store.delete_project(pid) is False
        finally:
            with store.driver.session() as s:
                s.run("MATCH (p:Project {project_id: $pid}) DETACH DELETE p", pid=pid)
