# `graph/` — Track D

State fingerprinting, hash-based deduplication, and Neo4j persistence of the
exploration graph (states, edges, violations).

**Owner:** Track D. Track B calls `GraphPort` from
[`apps/agent/contracts.py`](../contracts.py) — `fingerprint`, `is_visited`,
`persist_state`, `persist_edge`, `persist_violation`. Track D owns the schema
that `ExpectationNode`s serialize into; Track B reads that schema, never redefines it.

The stored graph is a **cyclic** directed graph. Nothing here may prune a
back-edge to make it acyclic.
