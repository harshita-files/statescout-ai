"""StateScout agent — graph module (Track D).

State fingerprinting, the Redis visited set, and Neo4j persistence.

``Neo4jGraph`` is published here — Track D's half of the live-integration
handshake with ``apps/agent/orchestrator/deps.py::live_ports``. That file still
does ``from apps.agent.graph import Neo4jGraph  # type: ignore[attr-defined]``
and lists Track D as missing; both are now stale now that this import resolves.
Track B needs to drop that ignore and the "Track D missing" branch (and the
matching assertion in ``tests/unit/orchestrator/test_skeleton.py``) in the same
PR — until then this branch's ``mypy apps/agent`` and that one Track B test are
expected to be red on files this track does not own. See ADR-001 action items
D-4 / the state_id (C-3) resolution this was waiting on.
"""

from apps.agent.graph.neo4j_graph import Neo4jGraph

__all__ = ["Neo4jGraph"]
