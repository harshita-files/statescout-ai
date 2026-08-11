"""Structured run logging.

One JSON object per line, every line carrying the `run_id`. Provisional: M4-P2
replaces this with the full orchestrator-wide logger and the run manifest. The
record shape is already the one that module will use, so the migration is a swap
rather than a rewrite.

Not the stdlib `logging` module and deliberately not built on it: these lines are
machine-read by CI and by the reporting API, so a handler configured somewhere
else must not be able to reformat, filter, or swallow them.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import IO, Any

__all__ = ["Logger"]


class Logger:
    """Writes JSON lines to `stream`, or discards them when `stream` is None."""

    def __init__(self, run_id: str, stream: IO[str] | None) -> None:
        self.run_id = run_id
        self.stream = stream

    @classmethod
    def discard(cls, run_id: str = "-") -> Logger:
        """For tests and library use, where the caller owns the output."""
        return cls(run_id, None)

    def emit(self, node: str, event: str, **fields: Any) -> None:
        if self.stream is None:
            return
        record = {
            "ts": datetime.now(UTC).isoformat(),
            "run_id": self.run_id,
            "node": node,
            "event": event,
            **fields,
        }
        self.stream.write(json.dumps(record, default=str) + "\n")
        self.stream.flush()
