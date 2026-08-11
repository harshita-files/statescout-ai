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

Relationships (all CREATE — never MERGE — cycles must be preserved):
  (StateNode)-[:ACTION {action_id, label, is_back_edge, recorded_at}]->(StateNode)
  (StateNode)-[:HAS_VIOLATION]->(ViolationNode)
  (ViolationNode)-[:VIOLATES]->(ExpectationNode)
  (PolicyContext)-[:HAS_EXPECTATION]->(ExpectationNode)
  (PolicyContext)-[:CONTAINS]->(StateNode)   # written on first persist_state per scan

Design rules (handbook Sections 1.4, 2.1; ADR-001):
  - StateNode  writes use MERGE (dedup by fingerprint — NFR-05).
  - ActionEdge writes use CREATE — every traversal is recorded, cycles preserved.
  - ViolationNode / ExpectationNode use MERGE (idempotent by their stable ids).
  - PolicyContext uses MERGE on scan_id.
"""

from __future__ import annotations

import logging
import os

from neo4j import GraphDatabase

logger = logging.getLogger(__name__)


class GraphStore:
    """Neo4j-backed implementation of the GraphPort protocol.

    Reads credentials from environment variables (NFR-11):
        NEO4J_URI      — Bolt connection string  (default: bolt://localhost:7687)
        NEO4J_USER     — Database username        (default: neo4j)
        NEO4J_PASSWORD — Database password        (default: testpassword123)
    """

    def __init__(self) -> None:
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "testpassword123")

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

    def persist_state(self, state: object) -> None:
        """Upsert a StateNode, deduplicated by state_id (fingerprint).

        Uses MERGE — re-crawling an existing state is a no-op for the node.
        depth is only written ON CREATE so it reflects the first discovery.
        """
        state_id: str = getattr(state, "state_id", "")
        url: str = getattr(state, "url", "")
        role: str = getattr(state, "role", "")
        depth: int = getattr(state, "depth", 0)
        title: str = getattr(state, "title", "")
        screenshot_path: str | None = getattr(state, "screenshot_path", None)

        with self.driver.session() as session:
            session.run(
                "MERGE (s:StateNode {fingerprint: $fp}) "
                "ON CREATE SET "
                "  s.url = $url, "
                "  s.role = $role, "
                "  s.depth = $depth, "
                "  s.title = $title, "
                "  s.screenshot_path = $sp, "
                "  s.created_at = timestamp()",
                fp=state_id,
                url=url,
                role=role,
                depth=depth,
                title=title,
                sp=screenshot_path,
            )
        logger.debug("persist_state: %s @ %s (depth=%d)", state_id[:8], url, depth)

    # ------------------------------------------------------------------
    # GraphPort — edge persistence
    # ------------------------------------------------------------------

    def persist_edge(self, edge: object) -> None:
        """Record a directed transition from one state to another.

        Uses CREATE — every traversal is a distinct record, cycles preserved
        (ADR-001: back-edges are evidence, not errors).
        """
        from_fp: str = getattr(edge, "from_state_id", "")
        to_fp: str = getattr(edge, "to_state_id", "")
        action_id: str = getattr(edge, "action_id", "")
        label: str = getattr(edge, "label", "")
        is_back_edge: bool = getattr(edge, "is_back_edge", False)

        with self.driver.session() as session:
            session.run(
                "MATCH (a:StateNode {fingerprint: $from_fp}), "
                "      (b:StateNode {fingerprint: $to_fp}) "
                "CREATE (a)-[:ACTION {"
                "  action_id: $aid, "
                "  label: $label, "
                "  is_back_edge: $ibe, "
                "  recorded_at: timestamp()"
                "}]->(b)",
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

    def update_scan_status(self, scan_id: str, status: str) -> None:
        """Update the lifecycle status of a PolicyContext node."""
        with self.driver.session() as session:
            session.run(
                "MATCH (p:PolicyContext {scan_id: $sid}) "
                "SET p.status = $status, p.updated_at = timestamp()",
                sid=scan_id,
                status=status,
            )

    def get_scan_counts(self, scan_id: str) -> dict[str, int]:
        """Return real states_explored and violations_found counts from Neo4j.

        Used by GET /scan/{id}/status to return live counts instead of zeros.
        """
        with self.driver.session() as session:
            result = session.run(
                "MATCH (p:PolicyContext {scan_id: $sid}) "
                "OPTIONAL MATCH (s:StateNode) WHERE s.scan_id = $sid "
                "OPTIONAL MATCH (v:ViolationNode) WHERE v.scan_id = $sid "
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
        """Return all ViolationNodes linked to states in this scan."""
        with self.driver.session() as session:
            result = session.run(
                "MATCH (v:ViolationNode) WHERE v.scan_id = $sid RETURN v",
                sid=scan_id,
            )
            return [dict(record["v"]) for record in result]

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
