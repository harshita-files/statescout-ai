# ADR-001 — Cross-track contract review

- **Status:** Accepted (Track B). Action items open with Tracks A, C, D.
- **Date:** 2026-08-09
- **Affects:** `apps/agent/contracts.py`, `packages/shared-types/index.ts`
- **Blocks:** the contracts freeze (`.claude/frozen/contracts`)

## Context

`contracts.py` (M1-P1) is frozen after team review, so every semantic it leaves
implicit becomes a semantic four people will each guess differently. Seven were
underspecified in the parent handbook. They are decided below.

Three of them changed the file: **1** (action identity), **3** (visited-set
ordering), and **6** (what `audit` receives). The rest confirmed the existing
shape or added documentation obligations.

**Do not create `.claude/frozen/contracts` until A-1…A-3, C-1, C-2, and D-1…D-3
are acknowledged.** After that, changes need a new ADR.

---

## Decisions

### 1. Action identity — content-addressed id, per-state dedup

Two separable axes, and we want a specific answer on each:

| Axis | Decision |
| --- | --- |
| How `action_id` is computed | Stable content hash of `role + accessible name + normalized selector` |
| How dedup is scoped | Per state — the key is `(state_id, action_id)` |

Global-once dedup would break the audit mission. A Delete button can be
forbidden in one state and perfectly fine in another; FR-06/FR-07's coverage
claim only holds if **every state's occurrence of an action is checked
independently**. Content addressing is still worth having on top of that: the
same "Logout" link carries one id across every page, which makes cross-state
analytics possible and makes the id predictable for Track A to implement.

A DOM-index id (`button-3`) fails both goals — it is unstable across a re-render
and meaningless across pages.

### 2. `fingerprint` hashes a normalized `CaptureBundle`

The signature stays as the handbook specifies. Fingerprinting the `SemanticUIMap`
instead would be stabler but would couple Track D to Track C, and that price is
not worth paying.

Keeping the signature must not quietly mean keeping a naive hash. State explosion
from an over-sensitive fingerprint is already on the project risk register, and a
raw-DOM hash walks straight into it: one timestamp or CSRF token per page load
and the graph grows without bound. `fingerprint()` **normalizes before hashing** —
strips timestamps, CSRF/nonce tokens, session ids. Interface clean, fix internal
to Track D.

### 3. `mark_visited` is called *before* the action executes

The handbook specified `is_visited()` with no writer. The gap is not just "add a
method" — the **ordering** is the decision:

```
mark_visited(state_id, action_id)     # Redis, Track D  — claim first
act(action)                           # the app under test
persist_edge(edge)                    # Neo4j, Track D  — record only on success
```

Marking first gives **at-most-once** semantics against the application under
test, which is generally not idempotent. A form submit re-fired on crash-resume
can corrupt the very app being audited — strictly worse than skipping one action.

The cost is a "visited, no edge" gap when a crash lands between the two calls.
Resume treats such a pair as done-but-unrecorded: **logged, never retried**.

This is load-bearing for M4-P1 (checkpoint-resume). Track D is asked to confirm
the *ordering*, not merely the method's existence.

### 4. `capture()` splits into `open()` and `act()`

Navigation and action execution have different failure modes, so they get
different methods and different error types. The orchestrator branches on the
exception class — retry-with-backoff on a nav timeout, mark-failed-and-skip on a
stale element — instead of type-sniffing a `str | Action` union at runtime. Fakes
get simpler too.

```python
class CrawlerPort(Protocol):
    def open(self, url: str) -> CaptureBundle: ...          # raises NavigationError
    def act(self, action: Action) -> CaptureBundle: ...     # raises ActionError
    def enumerate_actions(self, bundle: CaptureBundle) -> tuple[Action, ...]: ...
    def close(self) -> None: ...

class CrawlerError(StateScoutError): ...
class NavigationError(CrawlerError): ...
class ActionError(CrawlerError): ...
```

### 5. One role per run; no mid-run role switching

`role` becomes a field in `orchestrator/config.py`. Multi-role coverage is
multiple full runs.

This resolves for free — no contract change. A role-gated element yields a
different DOM → a different fingerprint → a different `StateNode`.

Note for Track D: cross-role comparison ("what does guest see versus admin at the
same URL") is a **reporting-layer** concern for whenever FR-31 is built, not a
crawl-layer one.

### 6. `audit` takes the full `ExpectationSet`

The narrow reading — pass only the `must_not_exist` clauses — silently drops
**FR-19** (required element absent = violation), which is High priority in the
SRS. That is not an edge case to trim.

FR-18 and FR-19 are different set operations, and one intersection call cannot
express both:

| | Operation | Meaning |
| --- | --- | --- |
| FR-18 | `S ∩ forbidden` | a forbidden thing is present |
| FR-19 | `required \ S` | a required thing is missing |

`audit()` therefore receives both halves and returns the union, with each
`Violation` tagged by the `ClauseType` that produced it — which NFR-14's "policy
constraint violated" report field needs regardless.

```python
def audit(self, s_current: SemanticUIMap,
          expectations: ExpectationSet) -> tuple[Violation, ...]: ...
```

### 7. `screenshot_path` stays optional, with a guardrail

DOM-only capture is worth keeping for CI speed. But a screenshot-less run is not
a real audit: the VLM exists precisely to catch visually-ambiguous elements — a
styled `<div>` with no DOM role — that DOM/AX analysis structurally cannot see.

Two obligations follow. Track C documents `analyze()`'s behaviour when
`screenshot_path is None` (reject, or degrade to DOM/AX-only). Track B's Month 4
run manifest tags such runs `perception_mode: "dom_only_smoke_test"`, so nobody
reads one as a completed audit.

---

## Action items

| ID | Owner | Item |
| --- | --- | --- |
| A-1 | Track A | Implement `action_id` as a stable hash of `role + accessible name + normalized selector`. Never a DOM index. (Decision 1) |
| A-2 | Track A | Add `clauseType` to the `Violation` interface in `packages/shared-types/index.ts`. Tracked as debt in `PENDING_TS_SYNC`. (Decision 6) |
| A-3 | Track A | Accept the `open()` / `act()` split and the two error types. (Decision 4) |
| A-4 | Track A | Confirm `screenshot_path` is genuinely optional; if the crawler always produces one, tighten to `str`. (Decision 7) |
| C-1 | Track C | Implement `audit()` as `(S ∩ forbidden) ∪ (required \ S)`, tagging each `Violation` with its `ClauseType`. (Decision 6) |
| C-2 | Track C | Document `analyze()`'s behaviour when `screenshot_path is None`. (Decision 7) |
| D-1 | Track D | Normalize timestamps, CSRF/nonce tokens, and session ids inside `fingerprint()` before hashing. (Decision 2) |
| D-2 | Track D | Confirm the `mark_visited` → `act` → `persist_edge` ordering, and that `mark_visited` is idempotent. (Decision 3) |
| D-3 | Track D | Note only: cross-role comparison is reporting-layer (FR-31), not crawl-layer. (Decision 5) |
| B-1 | Track B | Month 4 run manifest tags screenshot-less runs `perception_mode: "dom_only_smoke_test"`. (Decision 7) |
| B-2 | Track B | Create `.claude/frozen/contracts` once A/C/D acknowledge. |

## Concrete diff for A-2

```diff
 export interface Violation {
   violationId: string;
   stateId: string;
   expectationId: string;
+  /** Which set operation caught this: FR-18 vs FR-19. Mirrors ClauseType in contracts.py. */
+  clauseType: "forbidden_present" | "required_absent";
   severity: Severity;
   rationale: string;
```

Track B's `test_pending_typescript_syncs_are_still_pending` goes red the moment
this lands, as a reminder to delete the allowlist entry.
