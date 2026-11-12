# `apps/vscode-extension` — QA engineer UI (Track A)

Where a QA engineer writes an English policy, starts a scan, watches the
exploration graph grow, and reads the violation report directly inside VS Code.

**Owner:** Track A. Consumes the `/audits` API (`POST /audits`, `GET /audits/{id}`,
`POST /audits/{id}/stop`, `GET /audits/{id}/report`) served by `services/api`.
A stop lets the in-flight iteration finish and exit cleanly; it is not a kill.

Contract types come from [`@statescout/shared-types`](../../packages/shared-types).

## Commands

* `StateScout: Start Scan` (`statescout.startScan`) — Launch a dynamic UI audit against the target URL (`http://127.0.0.1:8765/` by default).
* `StateScout: Stop Scan` (`statescout.stopScan`) — Request a graceful stop of the active audit run.
* `StateScout: Open Audit Console` (`statescout.openConsole`) — Open the StateScout Webview panel with ranked findings (`stable` / `flaky` / `insufficient_evidence` confidence badges) and screenshot links.

## Building & Packaging (`.vsix`)

```bash
node apps/vscode-extension/scripts/package-vsix.mjs
code --install-extension apps/vscode-extension/statescout-vscode-0.1.0.vsix
```
