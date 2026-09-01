"""StateScout agent — graph module (Track D).

State fingerprinting, the Redis visited set, and Neo4j persistence.

Import the port implementation directly:

    from apps.agent.graph.neo4j_graph import Neo4jGraph

It is deliberately **not** re-exported from this package. Track B's
``apps/agent/orchestrator/deps.py`` reaches for ``from apps.agent.graph import
Neo4jGraph`` behind three ``# type: ignore[attr-defined]`` lines that also cover
Track A and Track C — the placeholders for "live mode isn't wired yet". Adding
the re-export now would make that ignore unused (failing ``mypy apps/agent`` in
CI) and flip ``tests/unit/orchestrator/test_skeleton.py`` red for asserting
Track D is still missing. Both are Track B's to update in the live-integration
PR, at which point this becomes a one-line ``from .neo4j_graph import Neo4jGraph``.
"""
