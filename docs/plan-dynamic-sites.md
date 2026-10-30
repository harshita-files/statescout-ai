# Auditing dynamic websites (stock tickers, feeds, live dashboards)

Live pages break the usual "same page = same state" assumption: prices tick, clocks run,
promo modals appear at random, endpoints flake. StateScout treats the exploration graph as
**cyclic and probabilistic** instead of trying to make it deterministic.

## Pipeline

```
URL + rules + provider config  ->  POST /audits
  rules:     user rules  +  generated rules (LLM, or heuristic templates with no LLM)
  crawl:     Playwright, polite + bounded (SafetyPolicy), role+name action selectors
  identity:  state_id = hash(role, url, masked DOM, masked AX tree)
  graph:     cyclic; edges carry observed transition counts and probabilities
  audit:     expectation clauses + consistency/numeric/a11y/content checks
  output:    findings (with confidence), blocked pages, graph JSON, HTML/MD/JSON report
```

## Handling volatility

| Problem | Mechanism | Where |
| --- | --- | --- |
| Prices, clocks, counters change every tick | numeric mask applied to state identity (`auto_mask`) | `orchestrator/graph_runner.py::learn_masks` |
| Flash/highlight and up/down classes toggle per tick | transient-class masks (tag-scoped) | same |
| Per-load random class/id suffixes | learned attribute masks from repeated seed captures | `orchestrator/stochastic/insights.py` |
| CDP node ids differ per load | stripped before hashing | `orchestrator/dynamic.py::identity` |
| Clicking after a reload | role+name selectors, not node ids | `crawler/playwright_crawler.py` |
| Non-deterministic outcomes of one action | counts per `(state, action) -> target`; probability = frequency | `orchestrator/dynamic.py` |
| Frontier explosion | UCB re-sampling of uncertain pairs (reorders, never drops) | `stochastic/frontier_policy.py` |
| Flaky vs real violations | `confidence = recurrence x reproducibility`, labelled stable/flaky/insufficient | `stochastic/confidence.py` |

Rules that stay true: loop prevention is the visited `(state_id, action_id)` set only, and
back-edges are never pruned.

Masks are recorded in the report (`stats.masks`) so a reviewer can see exactly what was
treated as noise. Masking numbers means two pages that differ only by a number share a
state (their URL still separates them); disable `auto_mask` if that matters for a target.

## After the crawl: probes

A crawl visits each page once. Some defects only show up with more than one look, so the
audit runner has post-crawl phases (`orchestrator/probes.py`), all run while the browser
is still open:

| Phase | Catches | How |
| --- | --- | --- |
| Resample | intermittent defects (an endpoint that fails 1 load in 10) | reload each kind of page a few times; pages making background requests of their own get many more (`resamples`, `resamples_dynamic`). A finding's confidence is the share of re-observations that showed it. |
| Liveness | a "Last updated" stamp that stays put while the data moves | readings of one page in time order: several readings sharing a timestamp but showing different values |
| Form probing | forms that accept a value they must refuse | submit a negative and a huge number to eligible forms and read the response. **Opt-in, local/private targets only** (the API rejects it for public sites). Never touches password/file/card fields, off-origin actions, or buttons that pay, delete, send or sign in. |

The crawl itself also prefers unseen *kinds* of page (URL patterns) over more of a kind
already seen, so ten `/stock/*` pages do not use up the budget before `/trade`.

## Real sites (google.com, youtube.com, ...)

Polite and bounded by default: robots.txt respected, per-host rate limit, page/time caps
counted on distinct URLs, same-origin scope, destructive actions (log out, delete, buy, ...)
never clicked, honest `StateScoutAuditor/0.1` user agent. CAPTCHA, login and consent walls
are **reported as blocked pages, never bypassed**. Expect shallow results on large sites;
that is the intended behaviour. Only disable robots for sites you own or are authorised
to test.

## Providers

`LLMProvider` (`apps/agent/llm/base.py`) with Ollama, Gemini, OpenAI-compatible (OpenAI,
OpenRouter, LM Studio, vLLM via `base_url`) and Anthropic backends; the LLM (rules) and VLM
(screenshots) are configured separately. With no VLM configured, perception is DOM-only
and never silently calls a paid API. Keys live in memory for the duration of an audit and
are never logged, persisted or included in reports.

## Demo target

`test-apps/stockwatch/` is a deliberately flawed live stock-market app with ten seeded
flaws and ground truth in `expected.json`. `python test-apps/stockwatch/server.py --port 8765`.

## Running

```
uv run uvicorn services.api.main:app        # UI at http://localhost:8000/
```

Neo4j/Redis are optional: without them audits run on the in-memory graph.
