# `perception/` — Track C

Vision-language model provider interface (inference only) and Semantic UI Map
extraction. Turns a `CaptureBundle` plus a role into a structured description of
what a user in that role can actually see and do.

**Owner:** Track C. Track B calls `PerceptionPort.analyze()` / `.audit()` from
[`apps/agent/contracts.py`](../contracts.py) and never reimplements them.
Provider calls are rate-limited; the orchestrator respects that budget from its
side too (see `orchestrator/config.py`).
