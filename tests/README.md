# `tests/`

| Directory | What lives here |
| --- | --- |
| `unit/` | Fast, no I/O. Ports are faked. Track-scoped subdirectories (`unit/orchestrator/`). |
| `integration/` | Real module wiring, still no browser/model/network. Fakes at the edges only. |
| `e2e/` | Full stack against a `test-apps/` target. Marked `live`; excluded from the default run. |
| `fixtures/` | Generated and hand-written test data, track-scoped (`fixtures/orchestrator/`). |

```bash
uv run pytest                 # unit + integration (the default gate)
uv run pytest -m live         # e2e; needs docker compose up and a browser
bun test                      # TypeScript: extension + shared-types
```

Track B's tests live in `unit/orchestrator/`, `integration/orchestrator/`, and
`fixtures/orchestrator/`. The path-guard hook blocks writes outside those.
