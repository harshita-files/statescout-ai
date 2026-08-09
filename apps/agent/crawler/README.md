# `crawler/` — Track A

Playwright-backed capture and action execution. Produces the `CaptureBundle`
(DOM, accessibility tree, screenshot path, URL) that every other module consumes,
and executes the actions the orchestrator chooses.

**Owner:** Track A. Track B calls it through `CrawlerPort` in
[`apps/agent/contracts.py`](../contracts.py) and never imports from here directly.
The capture format is frozen after Month 1.
