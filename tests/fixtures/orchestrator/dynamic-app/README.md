# dynamic-app: a seeded simulation of a dynamic web app

**This is a simulation, not a browser.** `app.py` is a stdlib-only class that implements
`CrawlerPort` (plus the experimental `NetworkObservations.drain()`), so it plugs into the
orchestrator's `Ports` next to `FakePerception` and `FakeGraph`. Nothing here exercises
Playwright, a real DOM engine, a VLM or timing.

All randomness comes from `random.Random` streams seeded from **7** (one stream for rendering,
one for stochastic outcomes), so a crawl is reproducible.

## Files

| File | Purpose |
| --- | --- |
| `app.py` | The simulated app (`DynamicApp`), policy, endpoint normaliser. |
| `expected.json` | Ground truth: 9 logical states, planted violations, stochastic outcomes, expected normalised endpoints per action. |
| `experiment.py` | Calibration, simulated approval of `suggest_masks` output, the A / B0 / B / B+ crawls, the report writer. |

## Dynamic features

Rotating ad block; live visitor counter; relative timestamps; infinite-scroll feed whose
appended items differ per visit; randomised CSS class names; an SPA modal at an unchanged URL
(`/`); cycles with back-edges (products -> home -> products, home <-> modal, cart <-> products,
...); `Add to cart` with a 70/30 outcome (cart / sold-out); `Checkout` with a ~5% outcome
(error page); a **flaky** forbidden element (`admin-link` on `/products`, rendered ~40% of the
time); a **stable** forbidden element (`debug-panel` on `/settings`, every render).

A capture names its logical state only through `screenshot_path`
(`/sim/screenshots/<logical>.png`). That is ground truth for reports; the orchestrator never
reads it.

## Run

```
uv run python tests/fixtures/orchestrator/dynamic-app/experiment.py   # writes docs/report/experiments/dynamic_app_results.md
uv run pytest tests/integration/orchestrator/test_dynamic_app.py -q
```

## Reading the ground truth

* `logical_state_count` is 9: a state counts once however many distinct DOMs it renders.
  `feed` is one logical state however many batches are loaded.
* `sold-out` and `error` are reachable only by chance (30% / 5% per execution); a given run
  may never see them.
* `endpoints.by_action` is the number of calls per action window after sanitising (query
  dropped, numeric segments become `{id}`). Every action also refreshes the visitor counter.
  `GET /api/orders/{id}` after `Checkout` happens only on the `thanks` outcome.
