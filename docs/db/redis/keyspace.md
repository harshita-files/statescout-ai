# Redis — the running crawl

Redis holds the state a crawl needs *while it is running*. Nothing here is a
report; if Redis were wiped after a completed run, no finding would be lost.

One thing here is an exception to that, and it is the important part of this
document: **the visited set is not a cache.** See "Durability" below.

**Owner: Track D** (the client and connection handling). Track B specifies the
semantics, because the orchestrator is what breaks if they are wrong.

## Key naming

All keys are prefixed `ss:` and, where run-scoped, carry the `run_id` as the
second segment. That makes `SCAN ss:<run_id>:*` a complete cleanup for one run.

| Key | Type | TTL | Written by | Purpose |
| --- | --- | --- | --- | --- |
| `ss:<run_id>:visited` | SET | 7d, refreshed | Orchestrator | Executed `(state_id, action_id)` pairs. Members are `"<state_id>|<action_id>"` |
| `ss:<run_id>:status` | HASH | 7d | Orchestrator | Live counters for the extension's progress view |
| `ss:<run_id>:stop` | STRING | 1h | API | Existence = a graceful stop was requested (M4-P1) |
| `ss:<run_id>:lock` | STRING | 5m, renewed | Orchestrator | Only one worker may drive a run |
| `ss:ratelimit:perception` | HASH | none | Orchestrator | Shared token bucket, when more than one run is live |
| `ss:runs:active` | SET | none | API | Run ids currently running, for the dashboard |

### `ss:<run_id>:visited`

```
SISMEMBER ss:run-demo-0001:visited "s-2e84eeb854c6|87987ee53792"   → is_visited()
SADD      ss:run-demo-0001:visited "s-2e84eeb854c6|87987ee53792"   → mark_visited()
SCARD     ss:run-demo-0001:visited                                 → coverage counter
```

`|` as the separator is safe: both halves are hex digests, never free text.

`SADD` returning 1 means *this call claimed the pair*. Track D should surface
that return value rather than discarding it — it is the cheapest possible
detection of two workers racing on the same run.

### `ss:<run_id>:status`

```
HSET ss:run-demo-0001:status states 6 edges 11 violations 4 \
     skipped 0 replays 9 phase scan updated_at 2026-08-09T12:00:02Z
```

Written every iteration, read by `GET /runs/{id}` for the progress bar. Purely
derived — losing it costs a stale progress bar, nothing more.

### `ss:<run_id>:stop`

The graceful-stop channel for M4-P1. The API `SET`s it; the orchestrator checks
it once per iteration and, if present, finishes the in-flight iteration,
checkpoints, writes the manifest, and exits with
`termination_reason = "stopped"`.

A key rather than a pub/sub message on purpose: a stop must survive the
orchestrator being mid-iteration, briefly disconnected, or not yet started. A
published message delivered to nobody is a stop request that silently did nothing.

### `ss:ratelimit:perception`

Only needed once two runs can be in flight at once. Today `RateLimiter` is
in-process, which is correct for one worker and wrong the moment there are two —
two processes each holding a 15/min bucket send 30/min to a provider that allows
15. When that day comes, this key holds `{tokens, updated_at}` and the refill
happens in a Lua script so check-and-decrement stays atomic.

**Not implemented yet.** Recorded here so the gap is visible rather than
discovered through a 429 storm.

## Durability — read this before configuring Redis

ADR-001 decision 3 gives **at-most-once** execution against the application under
test: a pair is claimed *before* the action runs, so a crash cannot re-fire a
form submit. That guarantee is only as strong as the durability of the visited
set.

The compose file currently runs Redis with:

```yaml
command: ["redis-server", "--save", "60", "1", "--loglevel", "warning"]
```

That is RDB snapshotting: **up to 60 seconds of claims can be lost on an unclean
shutdown.** Every lost claim is an action that will be executed a second time on
resume. On a checkout page, that is a second order.

Recommended, and this is a change to `infra/docker-compose.yml` (Track D):

```yaml
command:
  - redis-server
  - --appendonly
  - "yes"
  - --appendfsync
  - everysec
  - --loglevel
  - warning
```

`everysec` bounds the loss window to one second instead of sixty. `always` would
make it zero at a real throughput cost — not worth it, because the orchestrator
already tolerates the *other* side of the race (a claimed pair with no edge) by
logging rather than retrying.

**Eviction must be off for these keys.** A `maxmemory-policy` of `allkeys-lru`
would let Redis evict the visited set under pressure, which silently converts
at-most-once into at-least-once. If memory pressure is a real concern, use
`noeviction` and let writes fail loudly instead.

## TTLs and cleanup

Run-scoped keys expire after 7 days, refreshed on write while a run is live. The
graph in Neo4j is the durable record; these keys only need to outlast a resume.

```
# every key for one run
SCAN 0 MATCH ss:run-demo-0001:* COUNT 100
```

A run that ends cleanly should delete its own `lock` and `stop` keys. The rest
are left to expire — deleting `visited` immediately would make a late resume
re-explore, and re-exploration is exactly what the set exists to prevent.

## What deliberately is *not* in Redis

- **The frontier.** It lives in the LangGraph checkpoint, so that a resumed run
  rebuilds the exact queue it had rather than a plausible one.
- **Fingerprints.** `fingerprint()` is a pure hash; caching it would add an
  invalidation problem in exchange for microseconds.
- **Violations.** They are findings, and findings go in Neo4j.
