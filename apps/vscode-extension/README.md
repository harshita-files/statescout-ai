# `apps/vscode-extension` — QA engineer UI (Track A)

Where a QA engineer writes an English policy, starts a scan, watches the
exploration graph grow, and reads the violation report directly inside VS Code.

> **New to setting up the extension?** See [**`DEVELOPER_SETUP.md`**](./DEVELOPER_SETUP.md) for step-by-step installation, sidebar usage, and local backend instructions.

**Owner:** Track A. Consumes the `/audits` API (`POST /audits`, `GET /audits/{id}`,
`POST /audits/{id}/stop`, `GET /audits/{id}/report`) served by `services/api`.
A stop lets the in-flight iteration finish and exit cleanly; it is not a kill.

Contract types come from [`@statescout/shared-types`](../../packages/shared-types).

## Activity Bar & Commands

* **Left Sidebar Icon (`StateScout AI`):** Opens the `StateScout AI Console` view in the Activity Bar with quick actions (`Open Audit Console`, `Start New Audit`).
* `StateScout: Start Scan` (`statescout.startScan`) — Launch a dynamic UI audit against a target URL.
* `StateScout: Stop Scan` (`statescout.stopScan`) — Request a graceful stop of the active audit run.
* `StateScout: Open Audit Console` (`statescout.openConsole`) — Open the interactive StateScout Webview console with the Exploration Graph, Progress telemetry, and ranked Violations table.

## Building & Packaging (`.vsix`)

```bash
node apps/vscode-extension/scripts/package-vsix.mjs
code --install-extension apps/vscode-extension/statescout-vscode-0.2.0.vsix --force
```
