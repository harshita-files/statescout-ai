"""
Neo4j graph persistence layer for StateScout AI — Track D.

Month 2: Implements the full GraphPort protocol from apps.agent.contracts,
replacing FakeGraph as Track B's persistence backend.

Graph schema
------------
Nodes:
  StateNode       — one per unique UI state, deduped by fingerprint (MERGE)
  ViolationNode   — one per confirmed violation, deduped by violation_id (MERGE)
  PolicyContext   — one per scan session, deduped by scan_id (MERGE)
  ExpectationNode — one per policy clause, deduped by expectation_id (MERGE)

Relationships:
  (StateNode)-[:ACTION {action_id, label, is_back_edge, recorded_at}]->(StateNode)
                                            CREATE — every traversal recorded, cycles preserved
  (StateNode)-[:HAS_VIOLATION]->(ViolationNode)          MERGE
  (ViolationNode)-[:VIOLATES]->(ExpectationNode)         MERGE
  (PolicyContext)-[:HAS_EXPECTATION]->(ExpectationNode)  MERGE — persist_expectation(_set)
  (PolicyContext)-[:CONTAINS]->(StateNode)               MERGE — attach_state_to_scan /
                                                        the orchestrator's Neo4jGraph.persist_state

Scan scoping (Month 2)
----------------------
A state, and therefore its violations, belongs to a scan iff
``(:PolicyContext {scan_id})-[:CONTAINS]->(:StateNode)`` exists. `get_scan_counts`
and `get_violations_for_scan` traverse that edge — the Month 1 versions filtered
on a ``s.scan_id`` property that nothing ever wrote, so they always returned zero.

Design rules (handbook Sections 1.4, 2.1; ADR-001):
  - StateNode  writes use MERGE (dedup by fingerprint — NFR-05).
  - ActionEdge writes use CREATE — every traversal is recorded, cycles preserved.
  - ViolationNode / ExpectationNode use MERGE (idempotent by their stable ids).
  - PolicyContext uses MERGE on scan_id.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from neo4j import GraphDatabase

if TYPE_CHECKING:
    from apps.agent.contracts import ExpectationNode, ExpectationSet

logger = logging.getLogger(__name__)

#: Default password for a throwaway, localhost-bound dev container only. Any
#: shared or network-exposed deployment MUST set NEO4J_PASSWORD (in .env, which is
#: git-ignored — NFR-11). Kept in sync with infra/docker-compose.yml.
_DEV_NEO4J_PASSWORD = "devsecret"

# The one definition of a StateNode write, shared by GraphStore.persist_state and
# the orchestrator's Neo4jGraph. `_CONTAINS_TAIL` is appended when a scan_id is
# supplied (idiomatic Cypher "MERGE only if the OPTIONAL MATCH found a row").
_STATE_UPSERT = """
MERGE (s:StateNode {fingerprint: $fp})
ON CREATE SET s.created_at = timestamp()
SET s.url = $url,
    s.role = $role,
    s.title = $title,
    s.screenshot_path = $sp,
    s.depth = coalesce(s.depth, $depth)
"""

_CONTAINS_TAIL = """
WITH s
OPTIONAL MATCH (p:PolicyContext {scan_id: $sid})
FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END |
    MERGE (p)-[:CONTAINS]->(s))
"""

#: The one definition of an ActionEdge write. Endpoints MERGEd, relationship
#: CREATEd (never deduped — cycles / parallel edges preserved).
_ACTION_EDGE = """
MERGE (a:StateNode {fingerprint: $from_fp})
MERGE (b:StateNode {fingerprint: $to_fp})
CREATE (a)-[:ACTION {
    action_id: $aid,
    label: $label,
    is_back_edge: $ibe,
    recorded_at: timestamp()
}]->(b)
"""


class GraphStore:
    """Neo4j-backed implementation of the GraphPort protocol.

    Reads connection settings from the environment (NFR-11):
        NEO4J_URI      — Bolt connection string  (default: bolt://localhost:7687)
        NEO4J_USER     — Database username        (default: neo4j)
        NEO4J_PASSWORD — Database password        (default: a dev-only placeholder)
    """

    def __init__(self) -> None:
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", _DEV_NEO4J_PASSWORD)

        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.driver.verify_connectivity()
        logger.info("GraphStore connected to Neo4j at %s", uri)

    # ------------------------------------------------------------------
    # GraphPort — fingerprinting
    # ------------------------------------------------------------------

    def fingerprint(self, bundle: object) -> str:
        """Return a stable content hash for a CaptureBundle (ADR-001 decision 2).

        Delegates to apps.agent.graph.fingerprint.fingerprint_bundle which
        normalizes volatile attributes before hashing.
        """
        from apps.agent.graph.fingerprint import fingerprint_bundle

        return fingerprint_bundle(bundle)

    # ------------------------------------------------------------------
    # GraphPort — visited set  (ADR-001 decision 3: mark BEFORE executing)
    # ------------------------------------------------------------------

    def is_visited(self, state_id: str, action_id: str) -> bool:
        """Return True if (state_id, action_id) has already been claimed."""
        with self.driver.session() as session:
            result = session.run(
                "MATCH (v:VisitedPair {state_id: $sid, action_id: $aid}) RETURN v LIMIT 1",
                sid=state_id,
                aid=action_id,
            )
            return result.single() is not None

    def mark_visited(self, state_id: str, action_id: str) -> None:
        """Claim a (state_id, action_id) pair before the action executes.

        Uses MERGE so the call is idempotent (ADR-001 decision 3).
        """
        with self.driver.session() as session:
            session.run(
                "MERGE (v:VisitedPair {state_id: $sid, action_id: $aid}) "
                "ON CREATE SET v.claimed_at = timestamp()",
                sid=state_id,
                aid=action_id,
            )

    # ------------------------------------------------------------------
    # GraphPort — state persistence
    # ------------------------------------------------------------------

    def persist_state(self, state: object, scan_id: str | None = None) -> None:
        """Upsert a StateNode, deduplicated by fingerprint (NFR-05).

        Idempotent: mutable fields (url, role, title, screenshot) are set on every
        write; ``depth`` is first-write-wins via ``coalesce`` so a cycle revisiting
        the state cannot rewrite it deeper, and so a bare node stubbed by
        ``persist_edge`` gets its real depth when it is finally scanned.

        Pass ``scan_id`` to also link the node into that scan's PolicyContext
        (``:CONTAINS``) in the same round trip — the orchestrator's Neo4jGraph and
        POST /crawl/state-visit both do. A no-op if the PolicyContext is absent.
        """
        state_id: str = getattr(state, "state_id", "")
        url: str = getattr(state, "url", "")
        role: str = getattr(state, "role", "")
        depth: int = getattr(state, "depth", 0)
        title: str = getattr(state, "title", "")
        screenshot_path: str | None = getattr(state, "screenshot_path", None)

        query = _STATE_UPSERT + (_CONTAINS_TAIL if scan_id is not None else "")
        with self.driver.session() as session:
            session.run(
                query,
                fp=state_id,
                url=url,
                role=role,
                depth=depth,
                title=title,
                sp=screenshot_path,
                sid=scan_id,
            )
        logger.debug("persist_state: %s @ %s (depth=%d)", state_id[:8], url, depth)

    # ------------------------------------------------------------------
    # GraphPort — edge persistence
    # ------------------------------------------------------------------

    def persist_edge(self, edge: object) -> None:
        """Record a directed transition from one state to another.

        The `:ACTION` relationship is always **CREATEd** — every traversal is a
        distinct record, cycles and parallel edges preserved (ADR-001: a
        back-edge is evidence, not an error). Endpoints are MERGEd so an edge to a
        state not yet persisted (the orchestrator writes the edge before scanning
        the state it landed on) still lands; ``persist_state`` fills the stub in.
        """
        from_fp: str = getattr(edge, "from_state_id", "")
        to_fp: str = getattr(edge, "to_state_id", "")
        action_id: str = getattr(edge, "action_id", "")
        label: str = getattr(edge, "label", "")
        is_back_edge: bool = getattr(edge, "is_back_edge", False)

        with self.driver.session() as session:
            session.run(
                _ACTION_EDGE,
                from_fp=from_fp,
                to_fp=to_fp,
                aid=action_id,
                label=label,
                ibe=is_back_edge,
            )
        logger.debug(
            "persist_edge: %s --[%s]--> %s%s",
            from_fp[:8],
            action_id[:8],
            to_fp[:8],
            " [BACK]" if is_back_edge else "",
        )

    # ------------------------------------------------------------------
    # GraphPort — violation persistence
    # ------------------------------------------------------------------

    def persist_violation(self, violation: object) -> None:
        """Record a violation against its state.

        Writes a ViolationNode (MERGE on violation_id), an ExpectationNode
        (MERGE on expectation_id), and the two relationships.
        """
        vid: str = getattr(violation, "violation_id", "")
        state_id: str = getattr(violation, "state_id", "")
        exp_id: str = getattr(violation, "expectation_id", "")
        clause_type: str = getattr(violation, "clause_type", "")
        severity: str = getattr(violation, "severity", "high")
        rationale: str = getattr(violation, "rationale", "")
        evidence = getattr(violation, "evidence", None)
        ev_selector: str | None = getattr(evidence, "selector", None) if evidence else None
        ev_text: str | None = getattr(evidence, "text", None) if evidence else None
        ev_screenshot: str | None = getattr(evidence, "screenshot_path", None) if evidence else None

        with self.driver.session() as session:
            # 1. Upsert the ViolationNode
            session.run(
                "MERGE (v:ViolationNode {violation_id: $vid}) "
                "ON CREATE SET "
                "  v.state_fingerprint = $sfp, "
                "  v.expectation_id = $eid, "
                "  v.clause_type = $ct, "
                "  v.severity = $sev, "
                "  v.rationale = $rat, "
                "  v.evidence_selector = $esel, "
                "  v.evidence_text = $etxt, "
                "  v.evidence_screenshot = $esc, "
                "  v.detected_at = timestamp()",
                vid=vid,
                sfp=state_id,
                eid=exp_id,
                ct=clause_type,
                sev=severity,
                rat=rationale,
                esel=ev_selector,
                etxt=ev_text,
                esc=ev_screenshot,
            )
            # 2. Link ViolationNode to its StateNode
            session.run(
                "MATCH (s:StateNode {fingerprint: $sfp}), "
                "      (v:ViolationNode {violation_id: $vid}) "
                "MERGE (s)-[:HAS_VIOLATION]->(v)",
                sfp=state_id,
                vid=vid,
            )
            # 3. Upsert ExpectationNode and link violation to it
            session.run(
                "MERGE (e:ExpectationNode {expectation_id: $eid}) "
                "WITH e "
                "MATCH (v:ViolationNode {violation_id: $vid}) "
                "MERGE (v)-[:VIOLATES]->(e)",
                eid=exp_id,
                vid=vid,
            )
        logger.info("persist_violation: %s (%s) on state %s", vid, clause_type, state_id[:8])

    # ------------------------------------------------------------------
    # Month 2 extras — scan lifecycle
    # ------------------------------------------------------------------

    def create_policy_context(
        self, scan_id: str, url: str, policy: str, role: str = "guest"
    ) -> None:
        """Upsert a PolicyContext node for this scan session."""
        with self.driver.session() as session:
            session.run(
                "MERGE (p:PolicyContext {scan_id: $sid}) "
                "ON CREATE SET "
                "  p.url_scanned = $url, "
                "  p.policy = $policy, "
                "  p.role = $role, "
                "  p.status = 'queued', "
                "  p.started_at = timestamp(), "
                "  p.updated_at = timestamp()",
                sid=scan_id,
                url=url,
                policy=policy,
                role=role,
            )

    #: Statuses that mean the run is over. Reaching one stamps ``finished_at``.
    TERMINAL_STATUSES = ("completed", "failed", "stopped")

    def update_scan_status(self, scan_id: str, status: str) -> None:
        """Update the lifecycle status of a PolicyContext node.

        A terminal status (see ``TERMINAL_STATUSES``) also stamps ``finished_at``.
        """
        with self.driver.session() as session:
            session.run(
                "MATCH (p:PolicyContext {scan_id: $sid}) "
                "SET p.status = $status, p.updated_at = timestamp() "
                "FOREACH (_ IN CASE WHEN $status IN $terminal THEN [1] ELSE [] END | "
                "  SET p.finished_at = timestamp())",
                sid=scan_id,
                status=status,
                terminal=list(self.TERMINAL_STATUSES),
            )

    def record_scan_mode(self, scan_id: str, tags: dict[str, str]) -> None:
        """Stamp how a run was wired (``mode: live|degraded``, crawler/perception
        impls) onto the PolicyContext, so a fake-driven crawl is never read as a
        real audit."""
        with self.driver.session() as session:
            session.run(
                "MATCH (p:PolicyContext {scan_id: $sid}) "
                "SET p += $tags, p.updated_at = timestamp()",
                sid=scan_id,
                tags=tags,
            )

    def record_scan_result(
        self,
        scan_id: str,
        *,
        states: int,
        edges: int,
        visited_pairs: int,
        violations: int,
        skipped: int,
        termination_reason: str,
        duration_ms: float,
    ) -> None:
        """Persist an ExplorationResult summary onto the PolicyContext.

        Counts here are the loop's own final tally; `get_scan_counts` still
        computes live figures by graph traversal. `termination_reason` and
        `duration_ms` are what the graph alone cannot answer.
        """
        with self.driver.session() as session:
            session.run(
                "MATCH (p:PolicyContext {scan_id: $sid}) "
                "SET p.states_explored = $states, "
                "    p.edges = $edges, "
                "    p.visited_pairs = $pairs, "
                "    p.violations_found = $violations, "
                "    p.skipped = $skipped, "
                "    p.termination_reason = $reason, "
                "    p.duration_ms = $duration, "
                "    p.updated_at = timestamp()",
                sid=scan_id,
                states=states,
                edges=edges,
                pairs=visited_pairs,
                violations=violations,
                skipped=skipped,
                reason=termination_reason,
                duration=duration_ms,
            )

    def get_scan(self, scan_id: str) -> dict[str, object] | None:
        """Return a PolicyContext node's properties, or None if the scan is unknown."""
        with self.driver.session() as session:
            record = session.run(
                "MATCH (p:PolicyContext {scan_id: $sid}) RETURN p",
                sid=scan_id,
            ).single()
            return dict(record["p"]) if record is not None else None

    def is_stop_requested(self, scan_id: str) -> bool:
        """True once POST /scan/{id}/stop has run — the loop polls this between
        iterations and exits cleanly (run-control contract, services/api/README)."""
        scan = self.get_scan(scan_id)
        return bool(scan and scan.get("status") in ("stopping", "stopped"))

    def attach_state_to_scan(self, scan_id: str, fingerprint: str) -> None:
        """Link a persisted StateNode into its scan's PolicyContext.

        Call *after* persist_state. A no-op if the PolicyContext does not exist
        (an orchestrator run started without going through POST /scan/start).
        The (:PolicyContext)-[:CONTAINS]->(:StateNode) edge is what
        get_scan_counts / get_violations_for_scan traverse.
        """
        with self.driver.session() as session:
            session.run(
                "MATCH (p:PolicyContext {scan_id: $sid}) "
                "MATCH (s:StateNode {fingerprint: $fp}) "
                "MERGE (p)-[:CONTAINS]->(s)",
                sid=scan_id,
                fp=fingerprint,
            )

    def persist_expectation(self, scan_id: str, expectation: ExpectationNode) -> None:
        """Serialize one policy clause and link it to the scan (FR-04 storage).

        Track B produces ExpectationNodes from English in Month 3; Track D owns
        the schema they land in. Deduped by expectation_id.
        """
        with self.driver.session() as session:
            session.run(
                "MERGE (e:ExpectationNode {expectation_id: $eid}) "
                "ON CREATE SET "
                "  e.polarity = $pol, "
                "  e.subject = $subj, "
                "  e.roles = $roles, "
                "  e.source_text = $src "
                "WITH e "
                "MATCH (p:PolicyContext {scan_id: $sid}) "
                "MERGE (p)-[:HAS_EXPECTATION]->(e)",
                eid=getattr(expectation, "expectation_id", ""),
                pol=getattr(expectation, "polarity", ""),
                subj=getattr(expectation, "subject", ""),
                roles=list(getattr(expectation, "roles", ()) or ()),
                src=getattr(expectation, "source_text", ""),
                sid=scan_id,
            )

    def persist_expectation_set(self, scan_id: str, policy: ExpectationSet) -> None:
        """Persist every clause of a policy — both halves of the ExpectationSet."""
        for expectation in (*policy.forbidden, *policy.required):
            self.persist_expectation(scan_id, expectation)

    def get_scan_counts(self, scan_id: str) -> dict[str, int]:
        """Live states_explored / violations_found for a scan.

        Traverses (:PolicyContext)-[:CONTAINS]->(:StateNode)-[:HAS_VIOLATION]->…
        Used by GET /scan/{id}/status.
        """
        with self.driver.session() as session:
            result = session.run(
                "MATCH (p:PolicyContext {scan_id: $sid}) "
                "OPTIONAL MATCH (p)-[:CONTAINS]->(s:StateNode) "
                "OPTIONAL MATCH (s)-[:HAS_VIOLATION]->(v:ViolationNode) "
                "RETURN count(DISTINCT s) AS states, count(DISTINCT v) AS violations",
                sid=scan_id,
            )
            record = result.single()
            if record is None:
                return {"states_explored": 0, "violations_found": 0}
            return {
                "states_explored": record["states"],
                "violations_found": record["violations"],
            }

    def get_violations_for_scan(self, scan_id: str) -> list[dict[str, object]]:
        """Every violation found in this scan, each merged with its state's URL."""
        with self.driver.session() as session:
            result = session.run(
                "MATCH (p:PolicyContext {scan_id: $sid})-[:CONTAINS]->(s:StateNode) "
                "MATCH (s)-[:HAS_VIOLATION]->(v:ViolationNode) "
                "RETURN v, s.url AS state_url",
                sid=scan_id,
            )
            return [{**dict(record["v"]), "url": record["state_url"]} for record in result]

    # ------------------------------------------------------------------
    # Projects — reusable (url + policy + role) scan targets
    # ------------------------------------------------------------------

    def create_project(self, project_id: str, name: str, url: str, policy: str, role: str) -> None:
        """Upsert a Project node, deduped by project_id."""
        with self.driver.session() as session:
            session.run(
                "MERGE (p:Project {project_id: $pid}) "
                "ON CREATE SET p.created_at = timestamp() "
                "SET p.name = $name, p.url = $url, p.policy = $policy, "
                "    p.role = $role, p.updated_at = timestamp()",
                pid=project_id,
                name=name,
                url=url,
                policy=policy,
                role=role,
            )

    def get_project(self, project_id: str) -> dict[str, object] | None:
        with self.driver.session() as session:
            record = session.run(
                "MATCH (p:Project {project_id: $pid}) RETURN p", pid=project_id
            ).single()
            return dict(record["p"]) if record is not None else None

    def list_projects(self) -> list[dict[str, object]]:
        with self.driver.session() as session:
            result = session.run("MATCH (p:Project) RETURN p ORDER BY p.created_at DESC")
            return [dict(record["p"]) for record in result]

    def update_project(self, project_id: str, **fields: str) -> bool:
        """Patch a Project's name/url/policy/role. False if the id is unknown."""
        with self.driver.session() as session:
            record = session.run(
                "MATCH (p:Project {project_id: $pid}) "
                "SET p += $fields, p.updated_at = timestamp() "
                "RETURN p",
                pid=project_id,
                fields=fields,
            ).single()
            return record is not None

    def delete_project(self, project_id: str) -> bool:
        """Delete a Project (its past scans/graph stay). False if unknown."""
        with self.driver.session() as session:
            record = session.run(
                "MATCH (p:Project {project_id: $pid}) DETACH DELETE p RETURN 1 AS ok",
                pid=project_id,
            ).single()
            return record is not None

    def link_scan_to_project(self, project_id: str, scan_id: str) -> None:
        """Record that a scan was run for a project: (Project)-[:HAS_SCAN]->(PolicyContext)."""
        with self.driver.session() as session:
            session.run(
                "MATCH (p:Project {project_id: $pid}) "
                "MATCH (pc:PolicyContext {scan_id: $sid}) "
                "MERGE (p)-[:HAS_SCAN]->(pc)",
                pid=project_id,
                sid=scan_id,
            )

    # ------------------------------------------------------------------
    # Month 1 compat — direct writes (used by scripts/)
    # ------------------------------------------------------------------

    def create_state_node(self, fp: str, url: str) -> None:
        """Month 1 direct write — kept for script compatibility."""
        with self.driver.session() as session:
            session.run(
                "MERGE (s:StateNode {fingerprint: $fp}) "
                "ON CREATE SET s.url = $url, s.created_at = timestamp()",
                fp=fp,
                url=url,
            )

    def create_action_edge(self, from_fp: str, to_fp: str, action: str) -> None:
        """Month 1 direct write — kept for script compatibility."""
        with self.driver.session() as session:
            session.run(
                "MATCH (a:StateNode {fingerprint: $from_fp}), "
                "      (b:StateNode {fingerprint: $to_fp}) "
                "CREATE (a)-[:ACTION {type: $action, recorded_at: timestamp()}]->(b)",
                from_fp=from_fp,
                to_fp=to_fp,
                action=action,
            )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Release the underlying driver connection pool."""
        self.driver.close()
        logger.info("GraphStore disconnected from Neo4j")
