# Track B — progress through Month 2

Status of the orchestrator against the Track B handbook. Updated at the end of
each milestone; the evidence column names the test that proves the claim, so this
page cannot quietly drift from reality.

## Where things stand

| Month | Deliverables | Status |
| --- | --- | --- |
| 0 | Path-guard hook · CLAUDE.md · four subagents · two skills | ✅ done |
| 1 | `contracts.py` · `fakes.py` · walking skeleton · LangGraph PoC | ✅ done |
| 2 | Plain BFS loop · config + rate limiter · LangGraph port at parity | ✅ done |
| 3 | Extraction prompt · `policy.py` · FR-04/16 confirmation gate | ⬜ not started |
| 4 | Graceful stop · checkpoint-resume · structured logs + manifest | ⬜ not started |

## Done-criteria, with evidence

### Month 1 — "skeleton detects the planted violation; PoC runs in CI"

| Criterion | Evidence |
| --- | --- |
| Skeleton runs end to end in `--fake` | `uv run python -m apps.agent.skeleton --fake` → exit 1 |
| It detects a planted violation | `test_skeleton.py::test_violation_exits_one` |
| `contracts.py` frozen and circulated | `docs/adr-001-cross-track-contract-review.md` |
| Fakes honour their Protocols | `test_fakes.py::test_fake_signatures_match_the_contract` |
| PoC graph runs iterations in CI | `test_poc.py::test_three_iterations_walk_login_dashboard_login` |

`--live` is blocked on Tracks A, C, and D. `live_ports()` fails with a message
naming all three rather than an import error for whichever comes first
alphabetically.

### Month 2 — "autonomous crawl terminates; cyclic graph; 0% duplicate pairs"

| Criterion | Evidence |
| --- | --- |
| Autonomous crawl of the multi-page test-app terminates | `test_ground_truth.py::test_the_crawl_terminates_on_its_own` — by frontier exhaustion, not a cap |
| Every state discovered | `test_ground_truth.py::test_every_state_is_discovered` — 6 of 6 |
| Cyclic graph, back-edges preserved | `test_ground_truth.py::test_the_persisted_graph_is_cyclic` |
| 0% duplicate `(state, action)` — NFR-05 | `test_ground_truth.py::test_zero_duplicate_state_action_pairs` |
| Config + rate limiter, env-overridable | `test_config.py` — 38 cases incl. precedence |
| LangGraph port at test parity | `test_explore.py` — the whole M2-P1 suite runs against both implementations |

"Cyclic graph visible in Neo4j" is verified against `GraphPort`, not against a
running Neo4j: Track D owns the driver. The orchestrator's obligation is to
*emit* back-edges and never prune them, and that is what is asserted.

## What exists

```
apps/agent/
├── contracts.py        frozen cross-track interfaces
├── skeleton.py         walking skeleton driver (--fake / --live)
└── orchestrator/
    ├── config.py       pydantic-settings; depth, states, rate, run-id strategy
    ├── deps.py         injected ports container; throttling wired here
    ├── explore.py      plain-Python BFS — deprecated, kept as the parity oracle
    ├── fakes.py        in-memory Crawler/Perception/Graph
    ├── graph_runner.py the LangGraph port — what the product runs
    ├── poc.py          M1-P4 scaffold, superseded by graph_runner
    ├── ratelimit.py    token bucket + ThrottledPerception
    ├── runlog.py       structured JSON logging
    └── state.py        the one TypedDict, frontier entries, results
```

## Decisions worth knowing before Month 3

1. **Replay is how breadth is achieved, and it is bounded by action kind.** One
   browser can only act on the page it is looking at, so reaching a queued action
   means re-opening the seed and replaying the path. Replay re-fires actions,
   which conflicts with at-most-once — resolved by allowing only navigation kinds
   to be replayed. Paths through a `submit` are skipped with a reason and their
   subtrees reported unexplored. See the `explore.py` docstring.

2. **Two limits, and neither implies the other.** `depth_limit` bounds a deep
   chain; `max_states` bounds fan-out and is the only backstop against an
   unstable fingerprint. Both are tested against adversarial fixtures.

3. **`explore.py` is deprecated but not deletable.** It is the oracle the port is
   held to. A change there without the same change in `graph_runner.py` is a
   failing test, by design.

## Open, and blocking

| # | Item | Owner |
| --- | --- | --- |
| ADR-001 C-3 / D-4 | Who mints `SemanticUIMap.state_id`. Blocks the contracts freeze. | C, D |
| ADR-001 A-2 | `clauseType` missing from the TypeScript mirror; tracked in `PENDING_TS_SYNC`. | A |
| New | `ExpectationNode` has no scope predicate, so FR-19 cannot express "every *signed-in* page". See `test-apps/broken-admin/README.md`. | C + SRS |
| New | `.env.example` does not document `STATESCOUT_ROLE`, `STATESCOUT_RUN_ID_STRATEGY`, `STATESCOUT_RUN_ID`. The settings work; the example lags. | B (needs write access outside track paths) |

## Not started, and deliberately so

Nothing in `orchestrator/` calls an LLM yet. The policy pipeline is Month 3, and
`PerceptionPort.complete_text()` exists precisely so it will not need a second
model client when it arrives.
