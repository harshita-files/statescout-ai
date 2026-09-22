# Database schemas

Three stores, three jobs. The split is not incidental — each one holds the thing
it is good at, and losing any of them fails differently.

| Store | Holds | If you lose it |
| --- | --- | --- |
| **[Neo4j](./neo4j/)** | The exploration graph and every finding | The audit is gone. This is the product's output |
| **[Redis](./redis/)** | The visited set, live status, the stop signal | A resumed run may re-fire an action. **Not just a cache** — see below |
| **[SQLite](./sqlite/)** | LangGraph checkpoints, run manifests, coverage gaps | A crashed run restarts instead of resuming |

```
                 ┌──────────────┐
   the crawl ───▶│    Redis     │  claim a (state, action) pair BEFORE acting
                 └──────────────┘
                        │  then act on the target app
                        ▼
                 ┌──────────────┐
                 │    Neo4j     │  record the edge AFTER it succeeds
                 └──────────────┘
                        │
                 ┌──────────────┐
                 │    SQLite    │  checkpoint every superstep; manifest at the end
                 └──────────────┘
```

That ordering is [ADR-001 decision 3](../adr-001-cross-track-contract-review.md)
and it is load-bearing, not stylistic. Claiming before acting gives at-most-once
execution against an application that is probably not idempotent — a form submit
re-fired on resume can corrupt the app being audited. The cost is that a crash
between the two leaves a claimed pair with no edge; resume treats that as
done-but-unrecorded and logs it, rather than retrying.

## Ownership — read this first

**Track D owns Neo4j and Redis** (`apps/agent/graph/`, `services/api/`, `infra/`).
**Track B owns SQLite** (the checkpoint directory is orchestrator config).

Everything here was written by Track B and should land as a **proposal to Track
D**, not as a decision already made. The reason it was written from this side:
the orchestrator produces every one of these writes, so the shapes have to match
`apps/agent/contracts.py`, and the ordering constraints come from the loop. Track
D owns the driver, transaction boundaries, connection handling, and any deviation
from what is written here.

## Layout

```
docs/db/
├── README.md                              this file
├── neo4j/
│   ├── schema.md                          nodes, relationships, run scoping
│   ├── migrations/001_init.cypher         constraints + indexes, idempotent
│   ├── queries.cypher                     the queries the API actually needs
│   └── seed_broken_admin.cypher           a real crawl, as example data
├── redis/
│   └── keyspace.md                        keys, TTLs, and the durability requirement
└── sqlite/
    ├── schema.md                          why a manifest file *and* a table
    └── migrations/001_init.sql            run_manifest, run_skip, views
```

> **Location note.** These belong at `db/` in the repo root. They are in `docs/`
> because the Track B path guard blocks writes outside Track B's directories and
> `db/` is not on any allowlist. Moving them is a `git mv` plus one line in
> `.claude/hooks/track_b_paths.py`.

## Applying them

```bash
docker compose -f infra/docker-compose.yml up -d

# Neo4j: constraints and indexes, then optional example data
docker exec -i statescout-neo4j cypher-shell -u neo4j -p statescout \
  < docs/db/neo4j/migrations/001_init.cypher
docker exec -i statescout-neo4j cypher-shell -u neo4j -p statescout \
  < docs/db/neo4j/seed_broken_admin.cypher

# SQLite
sqlite3 .statescout/statescout.db < docs/db/sqlite/migrations/001_init.sql

# Redis needs no schema — but it does need the config change below
```

Then open <http://localhost:7474>, log in, and run:

```cypher
MATCH (n)-[r]->(m) RETURN n, r, m
```

You get the six-state graph with its cycles drawn. That is the fastest way to see
that the exploration graph really is cyclic.

## Verification status — what has and has not been run

| File | Verified how |
| --- | --- |
| `sqlite/migrations/001_init.sql` | ✅ Applied to a real SQLite database, re-applied to confirm idempotence, CHECK constraints confirmed to reject bad values |
| `neo4j/seed_broken_admin.cypher` | ⚠️ **Generated from a real crawl**, so the data is exact. Delimiter-balance checked. **Not executed against Neo4j** |
| `neo4j/migrations/001_init.cypher` | ⚠️ Delimiter-balance checked only. **Not executed** |
| `neo4j/queries.cypher` | ⚠️ Delimiter-balance checked only. **Not executed** |

The Neo4j image could not be pulled in the environment these were written in.
**Run `001_init.cypher` against a real 5.x Community instance before relying on
it** — the likeliest breakages are the relationship indexes and the full-text
index syntax, both of which changed shape across Neo4j 4 → 5.

### Regenerating the seed

Never hand-edit it. It is generated so that the example can never describe a
graph the orchestrator would not actually produce:

```bash
uv run python - <<'PY' > docs/db/neo4j/seed_broken_admin.cypher
# see the header comment in that file; the generator lives in the commit that
# introduced it and can be recovered with `git log -p -- docs/db/neo4j/`
PY
```

## Two things Track D should decide before the first real target

**1. Redis persistence is currently too weak for the at-most-once guarantee.**

`infra/docker-compose.yml` runs Redis with `--save 60 1` — RDB snapshots only, so
an unclean shutdown can lose up to sixty seconds of claimed pairs. Every lost
claim is an action that gets executed twice on resume. Recommended change and the
reasoning are in [`redis/keyspace.md`](./redis/keyspace.md#durability--read-this-before-configuring-redis);
the short version is `--appendonly yes --appendfsync everysec`, which bounds the
window to one second.

Also: eviction must be off for the visited set. An `allkeys-lru` policy silently
converts at-most-once into at-least-once.

**2. Retention.** Nothing here expires except the Redis keys. A crawl of a real
application is thousands of nodes, and runs accumulate per commit if this ends up
in CI. A starting point:

| Data | Keep |
| --- | --- |
| Runs with violations | Indefinitely — they are the findings |
| Clean runs | 30 days |
| Redis run keys | 7 days (already set) |
| Checkpoints for completed runs | Delete on completion; they only exist to enable resume |
| Screenshots | Tied to their run |

The delete query is in [`queries.cypher`](./neo4j/queries.cypher) and batches its
transactions, because detach-deleting a large run in one statement will exhaust
the default transaction memory.

## Design decisions worth knowing

- **Run scoping uses a synthetic `uid`.** The same page in two runs produces the
  same fingerprint, so keying on `state_id` alone would silently merge runs.
  `uid = "<run_id>:<state_id>"`, with `state_id` kept as an indexed property so
  cross-run comparison (FR-31) is still a join. Full reasoning in
  [`neo4j/schema.md`](./neo4j/schema.md#run-scoping--the-decision-to-read-before-implementing).
- **A composite node key would be cleaner and is Enterprise-only.** So is
  property-existence. Required fields are enforced in Track D's writer; the
  schema reference marks which ones.
- **Actions are relationship properties, not nodes** — with an optional
  `:Control` projection built *after* a run for the cross-state analytics that
  content-addressed action ids make possible. Analytics should not slow the
  write path.
- **The frontier is not in Redis.** It lives in the LangGraph checkpoint, so a
  resumed run rebuilds the exact queue it had rather than a plausible one.
- **Coverage gaps are stored, not inferred.** `run_skip` records every action the
  crawl declined to complete and why. A report that says "6 states audited"
  without saying "and one subtree was unreachable behind a form submit" is
  overclaiming.
