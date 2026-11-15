# SQLite — checkpoints and run manifests

The smallest of the three stores, and the only one the orchestrator owns
outright. It lives in `OrchestratorConfig.checkpoint_dir`
(default `.statescout/checkpoints`), which is gitignored.

Two unrelated things share the file:

1. **LangGraph's checkpointer.** The library creates and migrates its own tables.
2. **`run_manifest` and `run_skip`** (M4-P2), defined in
   [`migrations/001_init.sql`](./migrations/001_init.sql).

## Do not hand-manage the checkpoint tables

`langgraph-checkpoint-sqlite` creates its own schema on first use and migrates it
between releases. Track B's job is to point it at the right file and never touch
the tables. A manual `ALTER` there is how a resume stops working after a library
upgrade — and it fails by returning an *empty frontier*, which the loop reads as
"the crawl finished". The worst kind of bug: it looks like success.

Anything we want to query lives in our own tables, joined on `run_id`.

> **Not yet a dependency.** `graph_runner.explore()` takes a `checkpointer`
> argument and defaults to `InMemorySaver`. Swapping in the SQLite saver is M4-P1;
> the schema is here first so the manifest design does not have to be invented
> under time pressure that month.

## Why a manifest *file* and a manifest *table*

M4-P2 wants a per-run manifest written at start and finalised at end. The file is
the artifact of record:

```
.statescout/checkpoints/<run_id>/manifest.json
```

Human-readable, greppable, diffable, attachable to a bug report, and it survives
losing this database. The `run_manifest` table is an **index over those files**,
not a replacement — it exists so that "list the last twenty runs" and "which runs
were stopped early" are one query rather than a directory walk and N file reads.

If the two disagree, the file wins. `manifest_path` on every row makes that
checkable.

## `run_skip` is the honest half of the coverage claim

`state_count` says what the crawl reached. `run_skip` says what it did not, and
why:

| `category` | Meaning |
| --- | --- |
| `unreplayable` | The path back to this action goes through a side-effecting control. Refused rather than re-submitted |
| `replay_failed` | Re-navigation itself errored |
| `replay_diverged` | Replaying the path landed on a different state — non-deterministic app, or an unstable fingerprint |
| `action_failed` | The control was stale or detached |

`unreplayable` is the one to watch. It is the coverage StateScout deliberately
gives up in exchange for never re-submitting a form against the application under
test, and it should appear in a report rather than being inferred from a gap.

The `incomplete_run` view exists so that "was this a complete audit?" is a single
question with a single answer.

## Redaction

`config_snapshot` is a JSON dump of `OrchestratorConfig`. That object does not
carry credentials today — provider keys reach the VLM through Track C's
environment, not through ours — but NFR-11 makes redaction the writer's
responsibility regardless. The snapshot is written by the manifest writer, and
the manifest writer redacts. Do not serialise arbitrary environment state into
this column.

## Operational notes

- `journal_mode = WAL` so the API can read a manifest while a crawl writes one.
- `busy_timeout = 5000` rather than default-zero: WAL still serialises writers,
  and a checkpoint write colliding with a manifest update should wait, not fail.
- `STRICT` tables — SQLite otherwise accepts a string in an INTEGER column, and a
  count that is silently `"6"` instead of `6` breaks arithmetic downstream.
- One database file per machine, not per run. Run isolation is `run_id`.
