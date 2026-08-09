# `@statescout/shared-types`

TypeScript definitions for the API contract between `services/api` (Track D) and
`apps/vscode-extension` (Track A). Repurposed from the old `graph-core` package.

Types only. If you find yourself wanting to add behaviour here, it belongs in the
consumer instead — the two exported predicates (`isTerminal`, `isBlocking`) are
the deliberate ceiling.

These mirror the Python dataclasses in `apps/agent/contracts.py`. **The two
definitions must change in the same PR**; a drift between them is an outage the
type checker on neither side can see.

```ts
import type { ScanRun, Violation } from "@statescout/shared-types";
```
