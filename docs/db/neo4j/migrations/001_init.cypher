// StateScout — Neo4j 001: constraints and indexes.
//
// Idempotent. Safe to re-run; every statement is IF NOT EXISTS.
//
//   docker exec -i statescout-neo4j cypher-shell -u neo4j -p statescout \
//     < docs/db/neo4j/migrations/001_init.cypher
//
// Targets Neo4j 5.x **Community**. Two consequences that shape everything below:
//
//   1. Composite node-key constraints are an Enterprise feature. Run scoping is
//      therefore done with a synthetic single-property `uid` of the form
//      "<run_id>:<natural_id>", which Community can enforce as unique.
//   2. Property-existence constraints are also Enterprise. Required fields are
//      enforced in Track D's writer, not by the database. The schema reference
//      in ../schema.md marks which fields are mandatory; treat that as the
//      contract the writer has to keep.

// ---------------------------------------------------------------------------
// Uniqueness
// ---------------------------------------------------------------------------

CREATE CONSTRAINT run_id_unique IF NOT EXISTS
FOR (r:Run) REQUIRE r.run_id IS UNIQUE;

// `uid` = "<run_id>:<state_id>". The same page in two runs is two nodes, so a
// second run cannot mutate the first one's graph. Cross-run comparison is done
// by joining on the shared `state_id` at query time — see ../queries.cypher.
CREATE CONSTRAINT state_uid_unique IF NOT EXISTS
FOR (s:State) REQUIRE s.uid IS UNIQUE;

CREATE CONSTRAINT expectation_uid_unique IF NOT EXISTS
FOR (e:Expectation) REQUIRE e.uid IS UNIQUE;

CREATE CONSTRAINT violation_uid_unique IF NOT EXISTS
FOR (v:Violation) REQUIRE v.uid IS UNIQUE;

// Derived, and optional — built by a post-run projection, never on the write
// path. See ../schema.md, "Control".
CREATE CONSTRAINT control_action_id_unique IF NOT EXISTS
FOR (c:Control) REQUIRE c.action_id IS UNIQUE;

// ---------------------------------------------------------------------------
// Node indexes
// ---------------------------------------------------------------------------

// Almost every read is scoped to one run, so this is the index that matters.
CREATE INDEX state_run IF NOT EXISTS FOR (s:State) ON (s.run_id);
CREATE INDEX violation_run IF NOT EXISTS FOR (v:Violation) ON (v.run_id);
CREATE INDEX expectation_run IF NOT EXISTS FOR (e:Expectation) ON (e.run_id);

// Cross-run joins: "what does the guest run see that the admin run does not".
CREATE INDEX state_fingerprint IF NOT EXISTS FOR (s:State) ON (s.state_id);

// Report ordering and the extension's run list.
CREATE INDEX violation_severity IF NOT EXISTS FOR (v:Violation) ON (v.severity);
CREATE INDEX run_started IF NOT EXISTS FOR (r:Run) ON (r.started_at);
CREATE INDEX run_status IF NOT EXISTS FOR (r:Run) ON (r.status);

// Coverage questions are asked per URL far more often than per fingerprint.
CREATE INDEX state_run_url IF NOT EXISTS FOR (s:State) ON (s.run_id, s.url);

// ---------------------------------------------------------------------------
// Relationship indexes
// ---------------------------------------------------------------------------

// `action_id` is a content hash of role + accessible name + selector, so it is
// the *same* value wherever a control appears (ADR-001 decision 1). This index
// is what turns that property into the answer to "every place Log out exists".
CREATE INDEX transition_action IF NOT EXISTS
FOR ()-[t:TRANSITIONS_TO]-() ON (t.action_id);

// Cycle queries filter on this constantly, and back-edges are a minority of
// edges, so the index earns its keep.
CREATE INDEX transition_back_edge IF NOT EXISTS
FOR ()-[t:TRANSITIONS_TO]-() ON (t.is_back_edge);

// ---------------------------------------------------------------------------
// Full-text — optional, for the extension's search box
// ---------------------------------------------------------------------------

CREATE FULLTEXT INDEX state_text IF NOT EXISTS
FOR (s:State) ON EACH [s.url, s.title];

CREATE FULLTEXT INDEX violation_text IF NOT EXISTS
FOR (v:Violation) ON EACH [v.rationale, v.evidence_text];

// ---------------------------------------------------------------------------
// Migration bookkeeping
// ---------------------------------------------------------------------------

CREATE CONSTRAINT migration_id_unique IF NOT EXISTS
FOR (m:SchemaMigration) REQUIRE m.id IS UNIQUE;

MERGE (m:SchemaMigration {id: '001_init'})
ON CREATE SET m.applied_at = datetime(),
              m.description = 'Constraints and indexes for Run/State/Expectation/Violation';
