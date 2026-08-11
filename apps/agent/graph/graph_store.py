"""
Neo4j graph persistence layer for StateScout AI — Track D.

Manages the cyclic directed state graph:

    StateNode  -[:ACTION]->  StateNode

Design rules (from handbook Sections 1.4, 2.1):
  - StateNode writes use MERGE (dedup by fingerprint).
  - ActionEdge writes use CREATE, never MERGE — every traversal is recorded,
    preserving cycles.  This is critical for the crawl's termination proof.
  - No module reasons about data it didn't produce; Track D receives what
    Track A captures and Track C interprets.
"""

import os

from neo4j import GraphDatabase


class GraphStore:
    """
    Thin wrapper around the Neo4j driver exposing only the writes Track D owns.

    Reads credentials from environment variables (NFR-11):
        NEO4J_URI      — Bolt connection string  (default: bolt://localhost:7687)
        NEO4J_USER     — Database username        (default: neo4j)
        NEO4J_PASSWORD — Database password        (default: password)
    """

    def __init__(self) -> None:
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "password")

        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.driver.verify_connectivity()

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def create_state_node(self, fp: str, url: str) -> None:
        """
        Upsert a StateNode keyed on its SHA-256 fingerprint.

        Uses MERGE so that re-crawling a state that already exists in the graph
        is a no-op — it is idempotent by design.  ``created_at`` is only set
        on first creation.
        """
        with self.driver.session() as session:
            session.run(
                "MERGE (s:StateNode {fingerprint: $fp}) "
                "ON CREATE SET s.url = $url, s.created_at = timestamp()",
                fp=fp,
                url=url,
            )

    def create_action_edge(self, from_fp: str, to_fp: str, action: str) -> None:
        """
        Record a directed transition from one state to another.

        Uses CREATE (not MERGE) — every traversal is a distinct record.
        This preserves cycle information in the graph, which is essential for
        the crawl's loop-detection proof.
        """
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
