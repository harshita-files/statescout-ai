# `.claude/hooks`

Deterministic guardrails. CLAUDE.md *persuades* the model; a hook is enforced by
the harness and cannot be talked out of.

## `track_b_paths.py`

A `PreToolUse` hook on `Edit|Write|MultiEdit|NotebookEdit`. Blocks writes outside
the active track's owned paths (exit 2, reason on stderr). Reads are never
blocked — reading a teammate's module is how you learn the contract.

```bash
# see it work
echo '{"tool_name":"Write","tool_input":{"file_path":"apps/agent/crawler/x.py"},"cwd":"'"$PWD"'"}' \
  | python3 .claude/hooks/track_b_paths.py; echo "exit=$?"
# track-guard: Track B may not write apps/agent/crawler/x.py. That path belongs to Track A. ...
# exit=2
```

### Picking your track

Defaults to **B**. On another track, write your letter once:

```bash
echo C > .claude/track.local     # gitignored
```

Or set `STATESCOUT_TRACK=C` in the environment.

### Turning it off

```bash
STATESCOUT_TRACK_GUARD=off claude
```

Human-only, and deliberately so: the hook refuses edits to itself and to
`.claude/settings.json`, so a session cannot quietly widen its own permissions.
That is one step stricter than the Track B handbook, which allows the model to
edit `settings.json`. Turning a guardrail off should cost a relaunch.

### Freezing a cross-track file

`apps/agent/contracts.py` is writable until the team reviews it, then:

```bash
mkdir -p .claude/frozen && touch .claude/frozen/contracts
```

After that the hook blocks writes to it and says why.

### Schema drift

The stdin JSON shape is the part of this setup most likely to change between
Claude Code releases. `tests/unit/orchestrator/test_path_guard.py` pins it and
drives the hook as a real subprocess, so drift shows up as a failing test rather
than a guard that silently stopped guarding. If those tests go red after an
upgrade, check the hooks page in the docs before editing anything.
