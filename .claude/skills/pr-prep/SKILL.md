---
name: pr-prep
description: Prepare a Track B branch for PR to staging. Use when the user says "prep this for PR" or "ready to merge".
---

# PR preparation

Mechanical checklist. Stop at the first step that fails and tell the user why —
do not work around it.

1. Invoke the **test-runner** subagent. All green, or stop.
2. Invoke the **fresh-eyes-reviewer** subagent. Resolve every REQUEST CHANGES
   finding before continuing.
3. `git diff staging...HEAD --stat` — confirm every file is inside Track B scope
   (`apps/agent/orchestrator/`, `apps/agent/skeleton.py`, `tests/*/orchestrator/`).
   If not, STOP and tell the user which file escaped.
4. Rebase on the latest `staging`. If the rebase touched code, rerun step 1.
5. Squash fixup commits. Conventional-commit messages, scope `orchestrator`.
6. Draft the PR description and **print it for the user to post** — do not open
   the PR yourself. Cover:
   - what changed and why
   - how it was tested
   - contract changes (should be none — call it out loudly if not)
   - risks, and the one thing a reviewer should look hardest at

Branch names are `<type>/B-<slug>`. PRs target `staging`; only `staging` merges
into `main`.
