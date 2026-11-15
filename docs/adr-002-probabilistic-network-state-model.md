# ADR-002 — Probabilistic network state model

- **Status:** Proposed; pending review by owning Tracks A, B, C and D.
- **Date:** 2026-10-15
- **Owners:** A — capture and telemetry; B — orchestration and checkpoints;
  C — perception and audit; D — identity and graph/report persistence.
- **Scope:** Opt-in experimental equivalence and empirical observation statistics.
- **Contract impact:** Extensions below are proposals only, not enacted.
  `apps/agent/contracts.py` remains frozen. No new dependencies are proposed.

## Context and verified baseline

The handoff in `docs/handoff/PROJECT_STATE.md` describes dynamic DOM churn,
replay divergence, incomplete capture readiness and missing endpoint metrics.
Its historical observations are context, not evidence that live integration works.
This proposal was checked against the frozen contracts, ADR-001, and the working
copies of `orchestrator/dynamic.py`, `config.py`, `state.py` and `graph_runner.py`.

The inspected helper defines equivalence hashes, raw-content hashes, transition
counts, endpoint counts and recurrence/reproducibility/confidence containers.
Configuration defaults `probabilistic_states` to false with empty
`volatility_patterns`. The runner now integrates dynamic statistics and audits
original captures on revisits and known-state replay captures. Graph, API and
crawler implementation is ongoing; final integration and acceptance validation
remain pending. Code inspection does not establish live capture readiness,
durable crash recovery, security recall or calibrated probabilities.

## Proposed decisions

### Equivalence is separate from observation evidence

Use application-specific, explicitly configured volatility regex masks only for
exploration equivalence. In the inspected `identity()` helper, patterns replace
matching text in DOM and recursive AX string values; the identity includes the
role and unmasked URL. AX keys and numeric values are not masked. Title and
screenshot are not part of this identity. No automatic inference that arbitrary
numbers, controls or attributes are volatile is justified.

Keep the original `CaptureBundle` for perception and evidence; never send the
masked representation to the audit. Maintain the association between each
equivalence class and its observations. `record_capture()` currently retains
unique hashes of URL, DOM and AX, not the full raw captures, screenshots or an
observation history. A hash alone cannot reconstruct evidence. Evidence retention
and observation references therefore need explicit ownership and validation.

Audit the original capture on **every observation**, including seed opens,
replay opens, intermediate replay captures and revisits to equivalent states.
Pass the full `ExpectationSet` so forbidden presence and required absence remain
covered. Equivalence may suppress duplicate exploration work, never auditing.
Record audit failures as coverage gaps; they must not become clean verdicts or
successful audit denominators. Masking can still hide actions from exploration
when equivalent observations expose different controls, so auditing alone is not
a proof that masks preserve reachability or recall.

The current replay implementation audits captures whose identity is already in
`seen`, including replay opens and intermediate known states. Unknown replay
captures are hash-recorded but are not audited by that path; unknown divergent
replay destinations are logged/skipped as coverage gaps. The every-observation
rule above is the proposed audit objective, not a claim that unknown replay
observations are already covered.

### Empirical transitions, with replay visible

For source equivalence state `s`, action `a` and target `t`, record observed
successful transitions and estimate:

```
P_hat(t | s, a) = N(s, a, t) / sum_u N(s, a, u)
```

The inspected helper's `transitions` includes replay; `replay_transitions` is a
subset counter. Thus exploration-only counts are total minus replay, not total
plus replay. Reports must label all-observation, replay-only and exploration-only
distributions and expose their denominators. An unobserved pair has no empirical
estimate; the helper's returned zero for an empty denominator is a computational
fallback, not proof that a transition is impossible. Failed actions without a
target are not target observations and need separate failure accounting.

Statistics may prioritize unknown or uncertain pairs within a BFS depth, but
must not discard actions, reopen visited claims or schedule repeated actions
solely to improve estimates. Replay observations arise from restoring paths and
are not independent randomized trials.

A learned alternate replay destination may retarget the pending action only when
its empirical probability, evaluated using **pre-replay statistics**, is at least
`config.replay_min_probability` (default `0.05`), the landed state is already
known, and enumeration of that live capture contains an exactly equal `Action`.
Matching only an action ID or label is insufficient. The probability is for the
last replay step's actual source/action leading to the landed target. Observations
from the replay being evaluated cannot authorize their own first-time surprise.
After retargeting, recheck the landed `(state_id, action_id)` visited pair before
claiming/executing it, and use the actual landed source for the pending action,
transition statistics and persisted edge. Unknown or otherwise disallowed
divergence is logged/skipped. This guard does not establish side-effect safety.

### Endpoint calls and distinct triggering clicks

Associate sanitized `METHOD /template` labels with bounded action windows.
Count every request to an endpoint as a call, but count one triggering action
window per endpoint, and one triggering click window only when its action kind
is `click`. A click making three requests to one endpoint contributes three
calls, one action and one click. A second execution contributes another click;
this is not a count of unique control IDs, visited pairs or human users.

The helper currently records total `calls`, `actions`, `clicks`, and replay
subsets `replay_calls` and `replay_clicks`. Non-replay calls/clicks can be derived
by subtraction; a replay-action subtotal is not currently represented. Drain
telemetry after failed actions too: requests can precede an execution failure.
An absent producer means unavailable telemetry, not zero network activity.
Define window boundaries for opens, background requests, retries and late
responses before presenting these associations as causal attribution.

### Bounded capture readiness

Track A should provide a configurable finite deadline and an explicit readiness
outcome, using documented signals such as navigation completion, an application
ready selector and a bounded DOM/network quiet interval. Persistent polling or
streaming must not cause an unbounded wait. A timeout must be distinguishable
from a ready capture and from navigation/action failure. Record the signals,
elapsed time and deadline outcome so partial captures are visible to audits and
reports. The frozen `CaptureBundle` has no readiness metadata; this ADR does not
claim that this protocol or browser behavior is implemented.

### Default off, checkpointed statistics and recurrence confidence

Keep the feature default off. Opt-in runs must identify the identity/mask version,
role, configuration and sampling policy. Preserve the established behavior when
disabled. Incompatible identity settings must not silently reuse a checkpoint's
visited pairs or statistics.

Track B should checkpoint transition and replay counts, exact-hash associations,
endpoint counters and availability, audit denominators, violation hits and any
derived recurrence, reproducibility and confidence values together with frontier/run progress. Snapshot updates
must not mutate earlier checkpoints. Validate serialization and resume without
loss or double counting; merely placing `DynamicStats` in state does not prove
durability or transactional consistency with Redis and Neo4j. Version the
statistics schema and define migration/rejection and bounded retention policies.

The current runner computes the following per recorded violation `v`, with state
`t = v.state_id`:

```
recurrence(v) = (hits[v] + 1) / (audits[t] + 2)
I(t) = {(s, a) : N(s, a, t) > 0}
reproducibility(t) = sum_(s,a in I(t)) N(s, a, t)
                     / sum_(s,a in I(t)) sum_u N(s, a, u)
confidence(v) = recurrence(v) * reproducibility(t)
```

Recurrence is a smoothed empirical hit fraction: hits are keyed by violation ID
and successful audits by state ID. Include clean successful audits in the
denominator and require at most one hit per violation per observation.
Reproducibility is the sample-count-weighted target fraction among incoming
state-action distributions that have observed this target; their denominators
include alternate outcomes too. It is not an unweighted average or the chance of
reaching the state from the seed. With no incoming distribution, the current
calculation uses `1.0` as a neutral factor, not evidence of perfect reproducibility.
Transition totals include replay, so disclose replay composition and sample counts.

The confidence product means **reproducibility-weighted recurrence**, NOT
correctness. Neither the smoothing nor this product yields a calibrated security
probability. Report both components and their denominators alongside the product;
never infer application safety from absent findings or suppress a finding because
its score is low. `DynamicStats` stores these components; `audit_capture()` in the
runner computes them. Validation of stable violation IDs, duplicate-hit handling
and sparse-sample behavior remains part of acceptance.

### Cycles, visited claims and termination stay intact

The exploration graph remains cyclic. Preserve all traversal edges and back-edge
flags; do not replace append-only `StateEdge` evidence with an aggregate upsert
or prune cycles to fit a probability model. Store statistical aggregates beside
traversal evidence. Redis visited pairs remain claims, not sample counters.

Keep `(state_id, action_id)` visited checks and `mark_visited` before exploration
execution, then persist the edge after success. Preserve the done-but-unrecorded
crash gap semantics from ADR-001. Path replay is separate from new exploration
claims and can execute previously used controls; at-most-once claiming is not a
guarantee of globally at-most-once browser effects.

Visited pairs prevent repeated exploration of a pair; `depth_limit` bounds path
depth and `max_states` bounds distinct-state growth. Probabilities do not replace
any of these termination controls. Preserve `frontier_exhausted`, `depth_limit`,
`max_states`, `stopped` and `error` reporting. Exhaustion is relative to the
configured frontier and recorded gaps, not proof of complete application coverage.

## Frozen contract extensions for owning-track review — not enacted

| Proposal | Owners | Required decision before implementation |
| --- | --- | --- |
| Telemetry and capture readiness | A/B, D for reporting | Agree a versioned observation envelope or separate port carrying sanitized endpoint templates, action-window IDs, replay/failure attribution, availability, and readiness outcomes/deadlines. Decide bounded-window semantics and late-request handling. The local `NetworkObservations` protocol is experimental, not a frozen cross-track contract. |
| Statistics persistence | B/D | Agree versioned observation/aggregate records, checkpoint ownership, stable event IDs, idempotent export, resume consistency and retention. Add an explicit persistence capability if needed; do not overload visited claims or deduplicate traversal edges. |
| Canonical semantic state ID | B/C/D, A for wire mirror | Resolve ADR-001 C-3/D-4: pass the canonical ID into `analyze`, or remove perception's independently minted ID and associate results in orchestration. Agree how experimental equivalence IDs relate to `GraphPort.fingerprint`, raw observation IDs and violations. Preserve role and identity-version isolation and valid report joins. |

All signature/schema changes require owning-track agreement and synchronized
Python/TypeScript review and tests. This document changes neither contracts nor
their mirror, and selects no final signature unilaterally.

## Risks and mitigations

- **Mask recall:** Broad masks can merge permission changes, controls or distinct
  workflows. Require application-specific masks, original-capture auditing and
  adversarial fixtures; reject configurations that lose known findings or paths.
- **Replay side effects:** `click` is in the current replay-safe kind set, but a
  click can mutate application state. Statistical sampling grants no new replay
  permission. Track A/B must resolve action-level safety or record skipped paths;
  repeat tests only on controlled, resettable subjects.
- **Sparse, biased samples:** One role, bounded exploration, scheduling, failures
  and replay skew distributions. Publish denominators and coverage gaps; avoid
  independence, calibration, generalization or security-guarantee claims.
- **URL secrets:** Full URLs may contain credentials or identifying path segments.
  The helper's endpoint regex rejects queries and malformed labels, but does not
  prove that an accepted path has been templated or stripped of secrets. Sanitize
  at the producer, restrict retained raw evidence and never log authenticated
  URLs. Coordinate identity normalization with D: the inspected equivalence
  helper hashes the unmasked URL, which can also cause session-dependent splits.
- **Unbounded statistics:** Distinct raw hashes and endpoints can grow despite
  `max_states`. Define retention/caps with explicit truncation metadata rather
  than silently treating truncated counts as complete.

## Acceptance validation before adoption

Owning tracks should add failing tests before implementation and then demonstrate:

1. Default-off regression parity; explicit opt-in; configuration/version isolation.
   Dynamic fixtures stabilize only declared volatility while role, URL, modal,
   permission and control changes remain distinguishable as intended.
2. A transient forbidden control and a transient missing required element are
   detected on original observations even within one equivalence class, including
   intermediate replay captures. Failed audits are exposed and excluded from
   recurrence denominators. Compare findings and reachable actions with ground
   truth; fake-only recall does not establish live-perception recall.
3. Known transition sequences yield exact counts and normalized distributions;
   replay totals remain separately recoverable, empty samples are labeled unknown,
   failures do not invent targets, and prioritization preserves BFS depth/fairness.
   Test the smoothed recurrence formula, weighted incoming-target fraction,
   no-incoming fallback and confidence product with known counts and replay.
   Test alternate retargeting at/below the configured threshold using pre-replay
   counts; reject unknown targets and nonidentical live Actions. Verify visited
   rechecks and actual-source attribution, plus logged/skipped unknown divergence.
4. Multiple requests per click, multiple endpoints, non-click actions, replay,
   failures, unavailable telemetry and late/background requests produce documented
   counts. Secret-bearing queries, credentials and path segments never enter
   telemetry persistence or logs.
5. Controlled browser subjects with delayed rendering, persistent polling and
   failed readiness signals terminate capture within a bounded deadline and expose
   readiness outcomes. Partial captures cannot silently become complete audits.
6. Checkpoint serialization and durable resume preserve all counters and original
   snapshots. Crash tests around claim/action/edge/statistic boundaries establish
   the documented gaps and prevent duplicate claims or statistic exports.
7. Cycles and back-edges remain recorded, duplicate exploration claims remain
   absent, and visited/depth/max-state termination remains effective under dynamic
   churn. Unsafe replay paths remain explicit coverage gaps.
8. Every semantic map and violation resolves to the agreed canonical graph state;
   contract/mirror checks pass once approved extensions are separately enacted.

Final validation is pending while graph, API, crawler and orchestrator work
continues. The criteria above are adoption gates, not a completed test report.
