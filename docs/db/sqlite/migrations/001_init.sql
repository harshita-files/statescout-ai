-- StateScout — SQLite 001: run manifests and the checkpoint store's neighbours.
--
--   sqlite3 .statescout/statescout.db < docs/db/sqlite/migrations/001_init.sql
--
-- This database sits next to the LangGraph checkpointer in `checkpoint_dir`.
-- LangGraph creates and owns its own tables there (checkpoints, writes, and its
-- internal migration bookkeeping). Do not hand-manage those — the library
-- migrates them, and a manual ALTER is how a resume stops working. Everything
-- below is ours.

PRAGMA journal_mode = WAL;      -- the API reads while the orchestrator writes
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;

-- ---------------------------------------------------------------------------
-- run_manifest — M4-P2
-- ---------------------------------------------------------------------------
-- An index over the per-run JSON manifests, not a replacement for them.
--
-- The JSON file in `<checkpoint_dir>/<run_id>/manifest.json` is the artifact of
-- record: human-readable, greppable, and it survives losing this database. This
-- table exists so "list the runs" and "which runs were stopped early" are one
-- query instead of a directory walk and N file reads.

CREATE TABLE IF NOT EXISTS run_manifest (
    run_id              TEXT PRIMARY KEY,

    -- what was asked for
    target_url          TEXT    NOT NULL,
    role                TEXT    NOT NULL,
    policy_hash         TEXT,            -- so two runs can be compared on policy
    config_snapshot     TEXT    NOT NULL, -- JSON. Credentials redacted (NFR-11)
    git_sha             TEXT,

    -- what happened
    status              TEXT    NOT NULL
                        CHECK (status IN ('running','completed','failed','stopped')),
    termination_reason  TEXT
                        CHECK (termination_reason IS NULL OR termination_reason IN
                               ('frontier_exhausted','depth_limit','max_states',
                                'stopped','error')),
    started_at          TEXT    NOT NULL, -- ISO-8601 UTC
    finished_at         TEXT,

    -- counts, mirroring ExplorationResult
    state_count         INTEGER NOT NULL DEFAULT 0,
    edge_count          INTEGER NOT NULL DEFAULT 0,
    violation_count     INTEGER NOT NULL DEFAULT 0,
    skipped_count       INTEGER NOT NULL DEFAULT 0,
    replay_count        INTEGER NOT NULL DEFAULT 0,
    replay_steps        INTEGER NOT NULL DEFAULT 0,
    perception_calls    INTEGER NOT NULL DEFAULT 0,
    perception_wait_ms  INTEGER NOT NULL DEFAULT 0,
    duration_ms         INTEGER,

    -- A screenshot-less run is a smoke test, not an audit (ADR-001 decision 7).
    -- Recorded so nobody reads one as a completed audit.
    perception_mode     TEXT    NOT NULL DEFAULT 'full'
                        CHECK (perception_mode IN ('full','dom_only_smoke_test')),

    -- where the artifacts are
    manifest_path       TEXT    NOT NULL,
    checkpoint_thread   TEXT,            -- LangGraph thread_id; = run_id today

    -- resume bookkeeping
    resumed_from        TEXT REFERENCES run_manifest(run_id),
    resume_count        INTEGER NOT NULL DEFAULT 0
) STRICT;

CREATE INDEX IF NOT EXISTS run_manifest_started  ON run_manifest(started_at DESC);
CREATE INDEX IF NOT EXISTS run_manifest_status   ON run_manifest(status);
CREATE INDEX IF NOT EXISTS run_manifest_target   ON run_manifest(target_url, role);

-- ---------------------------------------------------------------------------
-- run_skip — the coverage gaps, kept queryable
-- ---------------------------------------------------------------------------
-- Every skipped action, with its reason. In the run log too, but logs get
-- rotated and "which actions did we never manage to try" is a question that
-- outlives them.
--
-- This is the honest half of the coverage claim: `state_count` says what was
-- reached, this table says what was not.

CREATE TABLE IF NOT EXISTS run_skip (
    run_id        TEXT    NOT NULL REFERENCES run_manifest(run_id) ON DELETE CASCADE,
    from_state_id TEXT    NOT NULL,
    action_id     TEXT    NOT NULL,
    reason        TEXT    NOT NULL,
    -- 'unreplayable' is the interesting one: a subtree behind a side-effecting
    -- action that we refused to reach by re-submitting a form.
    category      TEXT    NOT NULL
                  CHECK (category IN ('unreplayable','replay_failed',
                                      'replay_diverged','action_failed')),
    recorded_at   TEXT    NOT NULL,
    PRIMARY KEY (run_id, from_state_id, action_id)
) STRICT;

CREATE INDEX IF NOT EXISTS run_skip_category ON run_skip(run_id, category);

-- ---------------------------------------------------------------------------
-- schema_migration
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS schema_migration (
    id          TEXT PRIMARY KEY,
    applied_at  TEXT NOT NULL,
    description TEXT NOT NULL
) STRICT;

INSERT OR IGNORE INTO schema_migration (id, applied_at, description)
VALUES ('001_init', datetime('now'), 'run_manifest and run_skip');

-- ---------------------------------------------------------------------------
-- Views
-- ---------------------------------------------------------------------------

-- Runs whose coverage claim needs qualifying: cut short by a limit, stopped by
-- an operator, crashed, or missing a subtree they refused to reach.
CREATE VIEW IF NOT EXISTS incomplete_run AS
SELECT m.run_id,
       m.target_url,
       m.role,
       m.termination_reason,
       m.skipped_count,
       (SELECT count(*) FROM run_skip s
         WHERE s.run_id = m.run_id AND s.category = 'unreplayable') AS unreplayable_count
FROM run_manifest m
WHERE m.termination_reason IS NULL
   OR m.termination_reason <> 'frontier_exhausted'
   OR m.skipped_count > 0;

-- How much of each run was re-navigation rather than exploration. A ratio well
-- above 1 means path replay, not perception, is the bottleneck.
CREATE VIEW IF NOT EXISTS run_replay_cost AS
SELECT run_id,
       edge_count,
       replay_steps,
       CASE WHEN edge_count > 0
            THEN round(CAST(replay_steps AS REAL) / edge_count, 2)
       END AS steps_per_useful_action
FROM run_manifest;
