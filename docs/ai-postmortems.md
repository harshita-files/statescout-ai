# AI postmortems

A running log of what Claude Code got wrong, so the setup compounds instead of
repeating itself. Every entry should end as a new CLAUDE.md rule, a new line in a
skill, or a new test — otherwise it is just a complaint.

Keep entries short. Newest first.

## Template

```
### YYYY-MM-DD — one-line symptom
**What happened:** the wrong output, in one or two sentences.
**Why:** the missing constraint, not the model's mood.
**Fixed by:** the rule / test / skill line that now prevents it.
```

---

### 2026-08-09 — the path guard was going to lock the author out of `contracts.py`

**What happened:** The handbook's `track_b_paths.py` allowlist covers
`apps/agent/orchestrator/` and the orchestrator test directories only, but Track
B's own Month 1 work also writes `apps/agent/contracts.py` (M1-P1) and
`apps/agent/skeleton.py` (M1-P3). Installing the allowlist verbatim would have
blocked the next two milestones.

**Why:** The handbook describes the allowlist as it should look *after* the
contracts freeze, not during it. A guardrail written for the end state is wrong
for every day before it.

**Fixed by:** `skeleton.py` added to the Track B allowlist; `contracts.py` made
writable until `.claude/frozen/contracts` exists, which encodes "frozen after
team review" as a state the hook can actually observe. Tested in
`tests/unit/orchestrator/test_path_guard.py`.
