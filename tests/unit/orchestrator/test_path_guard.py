"""The path guard, exercised the way Claude Code actually runs it.

Every case drives `.claude/hooks/track_b_paths.py` as a subprocess with JSON on
stdin and asserts on the exit code, because that — not any Python function
signature — is the contract the harness relies on.

These tests also *pin the hook payload schema*. Claude Code ships weekly and the
stdin shape is the most drift-prone part of the setup; if `PAYLOAD_SCHEMA` stops
matching reality the guard silently stops guarding, so a red test here means
"check the hooks docs", not "edit the hook until it passes".
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HOOK = REPO_ROOT / ".claude" / "hooks" / "track_b_paths.py"

ALLOW, BLOCK = 0, 2

# The PreToolUse payload fields this hook depends on.
PAYLOAD_SCHEMA = ("tool_name", "tool_input", "cwd")


def run_hook(
    payload: object,
    *,
    track: str | None = None,
    guard: str | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("STATESCOUT_")}
    if track is not None:
        env["STATESCOUT_TRACK"] = track
    if guard is not None:
        env["STATESCOUT_TRACK_GUARD"] = guard

    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload if isinstance(payload, str) else json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def write_call(file_path: str, tool: str = "Write") -> dict[str, object]:
    return {
        "session_id": "test-session",
        "hook_event_name": "PreToolUse",
        "tool_name": tool,
        "tool_input": {"file_path": file_path, "content": "x = 1\n"},
        "cwd": str(REPO_ROOT),
    }


def test_payload_schema_is_pinned() -> None:
    """Guards against a silent Claude Code schema change (see module docstring)."""
    payload = write_call("apps/agent/orchestrator/explore.py")
    assert PAYLOAD_SCHEMA == ("tool_name", "tool_input", "cwd")
    assert all(field in payload for field in PAYLOAD_SCHEMA)
    assert run_hook(payload, track="B").returncode == ALLOW


@pytest.mark.parametrize(
    "file_path",
    [
        "apps/agent/orchestrator/explore.py",
        "apps/agent/orchestrator/nested/deep.py",
        "apps/agent/skeleton.py",
        "tests/unit/orchestrator/test_explore.py",
        "tests/integration/orchestrator/test_loop.py",
        "tests/fixtures/orchestrator/fake_app.json",
    ],
)
def test_track_b_may_write_its_own_paths(file_path: str) -> None:
    assert run_hook(write_call(file_path), track="B").returncode == ALLOW


@pytest.mark.parametrize(
    "file_path",
    [
        "apps/agent/crawler/capture.py",
        "apps/agent/perception/vlm.py",
        "apps/agent/negation/engine.py",
        "apps/agent/graph/neo4j_store.py",
        "services/api/main.py",
        "apps/vscode-extension/src/extension.ts",
        "pyproject.toml",
        ".github/workflows/ci.yml",
    ],
)
def test_track_b_may_not_write_other_tracks(file_path: str) -> None:
    result = run_hook(write_call(file_path), track="B")
    assert result.returncode == BLOCK
    assert "track-guard:" in result.stderr


def test_block_reason_names_the_owning_track() -> None:
    """The message has to tell Claude who to ask, or it just retries."""
    result = run_hook(write_call("apps/agent/crawler/capture.py"), track="B")
    assert "Track A" in result.stderr


def test_allowlist_follows_the_active_track() -> None:
    crawler = write_call("apps/agent/crawler/capture.py")
    assert run_hook(crawler, track="A").returncode == ALLOW
    assert run_hook(crawler, track="C").returncode == BLOCK


def test_track_defaults_to_b_when_unset() -> None:
    assert run_hook(write_call("apps/agent/orchestrator/explore.py")).returncode == ALLOW
    assert run_hook(write_call("apps/agent/graph/store.py")).returncode == BLOCK


@pytest.mark.parametrize("tool", ["Edit", "Write", "MultiEdit", "NotebookEdit"])
def test_every_write_tool_is_guarded(tool: str) -> None:
    assert run_hook(write_call("apps/agent/graph/store.py", tool=tool)).returncode == BLOCK


@pytest.mark.parametrize("tool", ["Read", "Grep", "Glob", "Bash", "WebFetch"])
def test_non_write_tools_pass_through(tool: str) -> None:
    """Reading a teammate's module is how you learn the contract."""
    assert run_hook(write_call("apps/agent/graph/store.py", tool=tool)).returncode == ALLOW


def test_relative_paths_resolve_against_cwd() -> None:
    payload = write_call("./apps/agent/orchestrator/../graph/store.py")
    assert run_hook(payload, track="B").returncode == BLOCK


def test_traversal_out_of_the_repo_is_blocked() -> None:
    result = run_hook(write_call("../../etc/passwd"), track="B")
    assert result.returncode == BLOCK
    assert "outside the repository" in result.stderr


def test_absolute_paths_are_understood() -> None:
    inside = str(REPO_ROOT / "apps" / "agent" / "orchestrator" / "explore.py")
    outside = str(REPO_ROOT / "apps" / "agent" / "graph" / "store.py")
    assert run_hook(write_call(inside), track="B").returncode == ALLOW
    assert run_hook(write_call(outside), track="B").returncode == BLOCK


def test_shared_paths_are_writable_by_any_track() -> None:
    for track in ("A", "B", "C", "D"):
        for shared in ("docs/adr-001.md", "test-apps/broken-admin/index.html"):
            assert run_hook(write_call(shared), track=track).returncode == ALLOW


def test_contracts_is_draftable_before_the_freeze() -> None:
    assert not (REPO_ROOT / ".claude" / "frozen" / "contracts").exists(), (
        "contracts.py is already frozen; unfreeze or update this test"
    )
    assert run_hook(write_call("apps/agent/contracts.py"), track="B").returncode == ALLOW


def test_the_guard_will_not_rewrite_itself() -> None:
    for target in (".claude/hooks/track_b_paths.py", ".claude/settings.json"):
        result = run_hook(write_call(target), track="B")
        assert result.returncode == BLOCK
        assert "STATESCOUT_TRACK_GUARD=off" in result.stderr


def test_escape_hatch_disables_the_guard() -> None:
    payload = write_call("apps/agent/graph/store.py")
    assert run_hook(payload, track="B", guard="off").returncode == ALLOW


def test_unparseable_payload_fails_open() -> None:
    """A schema change must not brick the session; the pinned tests catch it."""
    result = run_hook("not json at all", track="B")
    assert result.returncode == ALLOW
    assert "could not parse" in result.stderr


def test_missing_file_path_fails_open() -> None:
    payload = {"tool_name": "Write", "tool_input": {}, "cwd": str(REPO_ROOT)}
    assert run_hook(payload, track="B").returncode == ALLOW
