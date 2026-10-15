# Proposal for Track C: observation confidence, tag vocabulary, scope predicate

- **Owner:** Track C (`apps/agent/perception/`, `apps/agent/negation/`). Drafted by Track B, which does not write there.
- **Status:** Proposal. Cites `docs/adr-002-probabilistic-network-state-model.md` (Proposed): audit the original capture on every observation, record audit failures as coverage gaps, confidence = reproducibility-weighted recurrence, not correctness. `contracts.py` stays frozen; anything below that needs a contract field is marked and requires a new ADR.
- **Basis:** read of `negation/audit.py`, `perception/semantic_map.py`, `contracts.py`, `orchestrator/dynamic.py`. No Track C file has a pending diff (`git status` shows none). Nothing was run.

## Problem

1. **Confidence and counts are computed by Track B outside the audit.** `Violation` (frozen) has no field for hit counts, audit counts or confidence. `DynamicStats` keeps them keyed by `violation_id` and `state_id`. The `violation_id` is minted in `audit.py` as `v-{state_id}-{expectation_id}`, so it is stable per (state, clause), but the `state_id` in `SemanticUIMap` is whatever the perception call was given or minted (ADR-001 C-3/D-4 is still open). If the audit's `state_id` is not the orchestrator's equivalence/fingerprint id, hits and audits are keyed inconsistently and the report join fails.
2. **Tag vocabulary mismatch.** `perception/semantic_map.py` emits element tags from `_TAG_RULES`: `admin`, `delete`, `debug`, `export`, `logout`, `login`, and capabilities from `_CAPABILITY_RULES` (`admin-access`, `delete-user`, ...). `negation/audit.py::_matches_subject` normalizes and compares a policy subject for equality (`"deliberately don't do substring matching"`) against capabilities, tags and element names. The handoff and paper material use policy subjects like `admin-link` (and the contract docstring example is `admin-link`, `debug-panel`). `admin-link` equals neither tag `admin` nor capability `admin-access`, so a real VLM/DOM perception run will not match a policy phrased `admin-link`; only the hand-written `FakePerception` tags do. `_element_capabilities` maps tag `admin` to capability `admin-access`, so a subject `admin-access` works, `admin-link` does not. Result: the 4/4 recall reported in the paper holds for the fake path only (as the handoff already says).
3. **No scope predicate.** `ExpectationNode` has `roles` but no page/state scope (URL pattern, state tag). A clause "admin link must not exist" applies to every state, and "logout must exist" (required) fails on any state that legitimately has no logout (login page, error page), producing `required_absent` violations that are really scope errors. `policy.json` severities are ignored by `audit.py` (`_severity_for` is fixed by polarity).
4. **Audit failures.** ADR-002 requires audit exceptions to be coverage gaps, not clean verdicts. How `PerceptionPort.analyze` and `audit` signal failure is not specified in the contract beyond raising `StateScoutError` subclasses (to verify).

## Exact change requested

### 1. Carry observation counts (no contract change needed first)
Keep the confidence computation in Track B (`audit_capture`), but ask Track C to guarantee, and test, these audit properties:
- `violation_id` is a pure function of `(state_id, expectation_id)`; the same capture audited twice yields the same set of ids (idempotent and order independent).
- At most one `Violation` per `(state_id, expectation_id)` per call (needed for "at most one hit per violation per observation").
- `audit()` is total and non-raising for any well-formed `SemanticUIMap`; analysis failures raise a typed error (not return an empty tuple) so B can count a coverage gap rather than a clean audit.

### 2. Optional, requires new ADR (not enacted)
Add to `Violation` (Python and TS mirror, owners A/C/B/D):

```python
observations: int = 0       # successful audits of this state
hits: int = 0               # audits where this violation fired
confidence: float | None = None   # reproducibility-weighted recurrence, never "correctness"
```

   Alternative that avoids touching the frozen dataclass: a side record `ViolationStats(violation_id, hits, audits, recurrence, reproducibility, confidence)` emitted by B and stored by D (see `track-D-edge-stats.md`). Recommended as the first step because it needs no ADR.

### 3. Tag vocabulary (Track C decision, choose one)
- (a) **Normalize at the matcher.** In `audit._matches_subject`, also compare against a canonical alias map: `admin-link`, `admin-access`, `admin` -> `admin`; `debug-panel`, `debug-access`, `debug` -> `debug`; etc. Deterministic, no substring matching.
- (b) **Emit both** in `semantic_map`: tag `admin` and `admin-link` (role=link) so the existing equality check matches.
- (c) **Normalize the policy side** (Track B `policy.py`, not yet built) to the perception vocabulary. This moves the burden to Track B and should be agreed in an ADR.

   Prefer (a) with one shared vocabulary table in `perception/` and a test that every tag in `_TAG_RULES` and every capability in `_CAPABILITY_RULES` is reachable from at least one documented policy subject. Also fix `gemini.py`'s prompt vocabulary (`admin-access` ...) to the same table.

### 4. Scope predicate
Add an optional scope to the clause. Since `ExpectationNode` is frozen, a contract extension (ADR) is required:

```python
scope: str = ""   # "" = every state; otherwise e.g. "url:/admin/*" or "tag:dashboard"
```

   Until then, a no-contract workaround: Track B filters expectations per state before calling `audit()` (needs a scope source, so it is not available without the field).

### 5. Severity
Make `audit.py` read the clause severity (needs `ExpectationNode.severity`, another contract change) or keep the fixed polarity mapping and say so in `policy.json` docs. Out of scope here except as noted.

## Interface sketch

```python
# negation/audit.py (Track C)
def audit(semantic_map: SemanticUIMap, expectations: ExpectationSet) -> tuple[Violation, ...]: ...  # unchanged

# perception/vocabulary.py (new, Track C)
CANONICAL: dict[str, str]          # alias -> canonical tag
def canonical(subject: str) -> str: ...
```

## Tests (failing first, Track C)

- Table test: for each alias in `CANONICAL`, a map containing the real tag produced by `semantic_map` is flagged by a clause with that alias (forbidden) and satisfies it (required).
- Regression: the old exact-match behavior for current tags is unchanged.
- Property: auditing the same map twice returns equal tuples; `violation_id` stable; no duplicate ids.
- Failure: `analyze` error propagates as a typed error, and an empty map is not reported as a clean audit by B (cross-track test lives with B).
- Scope (after the ADR): a required `logout` clause with scope `tag:dashboard` does not fire on the login page.
- Real-perception check on at least one `test-apps/*` page with the live DOM+AX path, not only `FakePerception`.

## Risk

- Alias map can create false positives (`admin` word in a harmless label) because the existing rules are already keyword based; the VLM only merges tags, never removes elements.
- Contract additions (items 2, 4, 5) touch the frozen file and the TS mirror, and `PENDING_TS_SYNC` already carries `clauseType` debt.
- `violation_id` embeds `state_id`; if the state-id minting question (ADR-001 C-3) resolves toward an equivalence id, all stored ids change.
- Confidence products are not calibrated (ADR-002); do not display as probability of correctness.

## Effort

About 3 to 4 working days without contract changes (vocabulary + audit guarantees + tests + live-path check 2 to 3, side-record coordination 0.5 to 1). Scope predicate and severity add 2 to 3 days including the ADR, TS mirror and migration of `policy.json`.
