# `apps/vscode-extension` — QA engineer UI (Track A)

Where a QA engineer writes an English policy, starts a scan, watches the
exploration graph grow, and reads the violation report.

**Owner:** Track A. Track B's only interface to it is the run-control contract —
start, stop, status — served by `services/api`. A stop must let the in-flight
iteration finish and exit cleanly; it is not a kill.

Contract types come from [`@statescout/shared-types`](../../packages/shared-types).
Not published or packaged yet; scaffolding only.
