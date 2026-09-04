# `services/api` — FastAPI reporting backend (Track D)

Serves scan runs, exploration graphs, and violation reports to the VS Code
extension, and exposes the run-control endpoints (`/start`, `/stop`, `/status`)
that the orchestrator honours.

**Owner:** Track D. Track B depends only on the run-control contract: a stop
signal must let the in-flight iteration finish, write a run manifest, checkpoint,
and exit cleanly (M4-P1).
