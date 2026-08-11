#!/usr/bin/env python3
"""PreToolUse hook: block writes outside the active track's owned paths.

CLAUDE.md rules are suggestions the model weighs. This is enforced by the
harness and cannot be talked out of. It is the difference between "please don't
edit a teammate's module" and "you cannot".

Contract with Claude Code
-------------------------
stdin   JSON: {"tool_name": ..., "tool_input": {"file_path": ...}, "cwd": ...}
exit 0  allow the tool call
exit 2  block it; stderr is fed back to Claude as the reason

Registered for ``Edit|Write|MultiEdit|NotebookEdit`` in ``.claude/settings.json``.
Reads are never blocked — reading a teammate's module is how you learn the
contract; writing to it is how you cause a merge conflict.

Choosing the active track
-------------------------
1. ``STATESCOUT_TRACK`` in the environment, else
2. the first line of ``.claude/track.local`` (gitignored), else
3. ``B``.

Teammates on another track write their letter into ``.claude/track.local`` once.
To disable the guard for a session — the deliberate, human-only escape hatch —
launch Claude Code with ``STATESCOUT_TRACK_GUARD=off``.

The schema this parses is the part most likely to drift between Claude Code
releases. ``tests/unit/orchestrator/test_path_guard.py`` pins it, so drift
surfaces as a red test rather than a guardrail that silently stopped guarding.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

ALLOW, BLOCK = 0, 2

# Write surface of each track. Everything else is someone else's merge conflict.
TRACK_PATHS: dict[str, tuple[str, ...]] = {
    "A": (
        "apps/agent/crawler/",
        "apps/vscode-extension/",
        "packages/shared-types/",
        "tests/unit/crawler/",
        "tests/integration/crawler/",
        "tests/fixtures/crawler/",
    ),
    "B": (
        "apps/agent/orchestrator/",
        "apps/agent/skeleton.py",
        "tests/unit/orchestrator/",
        "tests/integration/orchestrator/",
        "tests/fixtures/orchestrator/",
    ),
    "C": (
        "apps/agent/perception/",
        "apps/agent/negation/",
        "research/",
        "tests/unit/perception/",
        "tests/unit/negation/",
        "tests/integration/perception/",
        "tests/fixtures/perception/",
    ),
    "D": (
        "apps/agent/graph/",
        "services/api/",
        "infra/",
        "tests/unit/graph/",
        "tests/integration/graph/",
        "tests/fixtures/graph/",
    ),
}

# No single owner: docs, ground-truth apps, scratch notes.
SHARED_PATHS: tuple[str, ...] = (
    "docs/",
    "test-apps/",
    "tests/e2e/",
    "NOTES.md",
    "README.md",
)

# Cross-track files any track may draft until the team freezes them. Create the
# sentinel to enforce the freeze:  touch .claude/frozen/contracts
FREEZABLE: dict[str, str] = {
    "apps/agent/contracts.py": ".claude/frozen/contracts",
}

# The guard may not rewrite the guard. Overriding this is a human decision made
# at launch time, not one the model can make mid-session.
SELF_PROTECTED: tuple[str, ...] = (
    ".claude/hooks/",
    ".claude/settings.json",
)

WRITE_TOOLS = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})
PATH_KEYS = ("file_path", "notebook_path", "path")


def active_track() -> str:
    """Which track this session is working as."""
    from_env = os.environ.get("STATESCOUT_TRACK", "").strip().upper()
    if from_env in TRACK_PATHS:
        return from_env

    track_file = REPO_ROOT / ".claude" / "track.local"
    if track_file.is_file():
        from_file = track_file.read_text(encoding="utf-8").strip().upper()
        if from_file in TRACK_PATHS:
            return from_file

    return "B"


def target_path(payload: dict[str, object]) -> Path | None:
    """The file the tool wants to write, absolute. None when undeterminable."""
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None

    raw = next(
        (tool_input[key] for key in PATH_KEYS if isinstance(tool_input.get(key), str)),
        None,
    )
    if raw is None:
        return None

    cwd = payload.get("cwd")
    base = Path(cwd) if isinstance(cwd, str) and cwd else Path.cwd()
    return (base / raw).resolve() if not Path(raw).is_absolute() else Path(raw).resolve()


def _matches(relative: str, patterns: tuple[str, ...]) -> bool:
    """A pattern ending in `/` is a prefix; otherwise an exact file match."""
    return any(
        relative.startswith(pattern) if pattern.endswith("/") else relative == pattern
        for pattern in patterns
    )


def check(relative: str, track: str) -> str | None:
    """None to allow, otherwise the one-line reason to show Claude."""
    if _matches(relative, SELF_PROTECTED):
        return (
            f"{relative} is the path guard itself and cannot be edited from inside a "
            "guarded session. Ask the user to relaunch with STATESCOUT_TRACK_GUARD=off."
        )

    if _matches(relative, TRACK_PATHS[track]) or _matches(relative, SHARED_PATHS):
        return None

    for path, sentinel in FREEZABLE.items():
        if relative == path:
            if (REPO_ROOT / sentinel).exists():
                return (
                    f"{relative} was frozen after team review ({sentinel} exists). "
                    "Changing it is a cross-track decision — raise it with the owners."
                )
            return None

    owners = sorted(letter for letter, paths in TRACK_PATHS.items() if _matches(relative, paths))
    owned_by = f" That path belongs to Track {'/'.join(owners)}." if owners else ""
    return (
        f"Track {track} may not write {relative}.{owned_by} "
        f"Writable here: {', '.join(TRACK_PATHS[track])}"
    )


def main() -> int:
    if os.environ.get("STATESCOUT_TRACK_GUARD", "").strip().lower() == "off":
        return ALLOW

    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        # Fail open: an unparseable payload means the harness schema moved, not
        # that Claude did something wrong. The pinned tests catch real drift.
        print("track-guard: could not parse hook payload; allowing.", file=sys.stderr)
        return ALLOW

    if not isinstance(payload, dict) or payload.get("tool_name") not in WRITE_TOOLS:
        return ALLOW

    path = target_path(payload)
    if path is None:
        return ALLOW

    try:
        relative = path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        print(f"track-guard: {path} is outside the repository.", file=sys.stderr)
        return BLOCK

    reason = check(relative, active_track())
    if reason is None:
        return ALLOW

    print(f"track-guard: {reason}", file=sys.stderr)
    return BLOCK


if __name__ == "__main__":
    sys.exit(main())
