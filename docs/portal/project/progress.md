# Project progress

<!-- TODO(team): update the status column at every review. Keep each "done" claim
     backed by something a reader can open: a merged PR, a test, or a document. -->


## The four-month plan

Each month has a theme and a demonstrable milestone. The plan builds a thin
end-to-end slice first, then thickens it, so integration problems surface early
rather than at the end.

| Month | Theme | Milestone | Status |
| --- | --- | --- | --- |
| 1 | Foundation, walking skeleton, de-risking | A skeleton detects a planted violation on a broken test app | Done |
| 2 | Core autonomy and perception | Autonomous crawl of a multi-page app builds a deduplicated, cyclic graph and terminates | Done |
| 3 | Negation engine, policy, reporting, extension | From VS Code: URL + English policy → scan → violations reported with evidence | In progress |
| 4 | Hardening, benchmarking, production readiness | Install from scratch, run an audit, get a report; benchmark results | In progress |

## By track

### Track A - integration, extension & DevOps

| Deliverable | Status |
| --- | --- |
| Playwright crawler behind the crawler interface (`open` / `act` / `enumerate_actions`) | Done - merged (PR #17) |
| Role-based action selector fix for real-browser clicks | Implemented, awaiting merge |
| Ground-truth test apps with documented violations | Done - `test-apps/broken-admin` and three further demos |
| VS Code extension | Scaffolding only |
| Docker Compose, path-filtered CI | Done |

### Track B - agent & orchestration

| Deliverable | Status |
| --- | --- |
| Frozen cross-track contracts, fakes, walking skeleton, LangGraph proof of concept | Done (Month 1) |
| BFS exploration loop at parity in plain Python and LangGraph; configuration and rate limiter | Done (Month 2) - the ground-truth crawl reaches 6/6 states, terminates on its own, keeps the graph cyclic, and explores no pair twice |
| Opt-in probabilistic model for dynamic applications | In progress - see [Robustness on dynamic applications](robustness.md) |
| Natural-language policy parser and confirmation gate (FR-04 / FR-16) | Not started |
| Graceful stop, checkpoint-resume, run manifest | Not started |

### Track C - vision, negation & research

| Deliverable | Status |
| --- | --- |
| UI extraction and DOM + accessibility correlation | Done - merged (PR #12) |
| Gemini vision-language provider | Done - merged (PR #15) |
| Deterministic negation audit (forbidden present, required absent) | Done |
| Wiring the provider into the live crawl (who mints the state id - ADR-001 C-3) | Open |
| InternVL fine-tuning and benchmark | Not started |

### Track D - data, API & reporting

| Deliverable | Status |
| --- | --- |
| Neo4j graph store, normalised SHA-256 fingerprint, Redis visited set | Done - merged (PR #13) |
| Reporting API with scan run control, projects, live WebSocket stream, optional API key | Done - merged (PR #13) |
| Evidence chain on every violation; summary, timeline and graph report endpoints | Implemented, awaiting merge |
| NFR-01 / NFR-05 performance checks, end-to-end suite, benchmark harness, checkpoint-resume confirmation | Implemented, awaiting merge |

## Research paper

Drafts of the accompanying paper - IEEE and Springer formats, with the novelty
analysis and reproducible experiments - are in
[`docs/report/`](https://github.com/harshita-files/statescout-ai/tree/main/docs/report)
in the repository.
