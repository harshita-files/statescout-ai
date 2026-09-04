"""The interfaces between StateScout's four tracks.

This is the only module every track imports. It contains **types and nothing
else**: frozen dataclasses for the data that crosses a boundary, `Protocol`
classes for the three services the orchestrator consumes, and the exceptions
those services are allowed to raise. No logic, no I/O, no third-party imports.

Why it is shaped this way
-------------------------
The orchestrator (Track B) is a *consumer* of three implementations owned by
other people, none of which exist yet. Coding against `Protocol`s rather than
concrete classes is what lets four people build in parallel: Track B runs the
real loop against `orchestrator/fakes.py` from day one, and the day Track A's
crawler lands, nothing in the loop changes.

The freeze
----------
After team review this file is frozen: the path guard blocks writes once
``.claude/frozen/contracts`` exists. Changing a signature afterwards is a
cross-track decision, not a local fix. If a contract looks wrong while you are
using it, stop and raise it with the owning track.

Review decisions — 2026-08-09
-----------------------------
Seven semantics were underspecified in the parent handbook. All are now decided;
``docs/adr-001-cross-track-contract-review.md`` carries the full reasoning and
the per-track action items. Summarised here because this is the file people read.

1. **Action identity — content-addressed id, per-state dedup.** `action_id` is a
   stable hash of ``role + accessible name + normalized selector``, **never** a
   DOM index, so the same "Logout" link carries the same id on every page.
   Deduplication is nonetheless scoped per state, keyed ``(state_id, action_id)``.
   The two are separable and we want both: global-once dedup would break the
   audit mission, because a Delete button may be forbidden in one state and fine
   in another, and FR-06/FR-07 coverage only holds if every state's occurrence is
   checked independently. → Track A implements the hash rule.

2. **`fingerprint` hashes a normalized `CaptureBundle`.** The signature stays as
   the handbook has it — Track D is not coupled to Track C's semantic map. But
   keeping the signature must not mean keeping a naive hash: `fingerprint()`
   normalizes away timestamps, CSRF/nonce tokens, and session ids *before*
   hashing. State explosion from an over-sensitive fingerprint is already on the
   project risk register. Interface clean, fix internal. → Track D.

3. **`mark_visited` is called BEFORE the action executes.** This gives
   at-most-once semantics against the application under test, which is generally
   not idempotent: a form submit re-fired on crash-resume can corrupt the very
   app being audited, which is worse than skipping one action. `persist_edge`
   fires only *after* the action succeeds. A crash between the two leaves a
   "visited, no edge" gap, which resume treats as done-but-unrecorded: logged,
   never retried. This ordering is load-bearing for Month 4 checkpoint-resume.
   → Track D confirms the ordering, not merely the method.

4. **`capture()` is split into `open()` and `act()`.** Navigation and action
   execution have different failure modes, so they get different methods and
   different error types (`NavigationError`, `ActionError`). The orchestrator can
   then branch — retry-with-backoff on a nav timeout, mark-failed-and-skip on a
   stale element — without runtime type-sniffing a union. → Track A, proposed as
   a concrete diff in the ADR.

5. **One role per run; no mid-run role switching.** `role` is a field in
   `orchestrator/config.py`; multi-role coverage is multiple full runs. This needs
   no contract change: a role-gated element yields a different DOM, therefore a
   different fingerprint, therefore a different `StateNode`. → Note for Track D:
   cross-role comparison ("what does guest see vs. admin at this URL") is a
   reporting-layer concern for FR-31, not a crawl-layer one.

6. **`audit` takes the full `ExpectationSet`, not just the forbidden clauses.**
   The narrow reading would have silently dropped FR-19 (required element absent
   = violation), which is High priority in the SRS. FR-18 and FR-19 are different
   set operations and one intersection call cannot express both:

       FR-18   S ∩ forbidden      (a forbidden thing is present)
       FR-19   required \\ S       (a required thing is missing)
       result  the union of the two

   Every `Violation` is tagged with the `ClauseType` it came from, which NFR-14's
   "policy constraint violated" report field needs anyway. → Track C.

7. **`screenshot_path` stays optional, with a guardrail.** DOM-only capture is
   useful for CI speed, but a screenshot-less run is not a real audit: the VLM
   exists precisely to catch visually-ambiguous elements (a styled ``<div>`` with
   no DOM role) that DOM/AX analysis structurally cannot see. Track C documents
   `analyze()`'s behaviour when `screenshot_path is None` — reject or degrade —
   and Track B's Month 4 run manifest tags such runs
   ``perception_mode: "dom_only_smoke_test"`` so nobody reads one as a completed
   audit. → Track A confirms optionality; Track C documents the degrade path.

Mirror
------
The wire-facing types here are mirrored in TypeScript at
``packages/shared-types/index.ts`` (Track A's file). The two must change in the
same PR; ``tests/unit/orchestrator/test_contracts.py`` fails when one drifts, and
carries an explicit allowlist for syncs still awaiting the owning track.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol, TypeAlias, runtime_checkable

__all__ = [
    "Action",
    "ActionError",
    "ActionKind",
    "CaptureBundle",
    "ClauseType",
    "CrawlerError",
    "CrawlerPort",
    "Evidence",
    "ExpectationNode",
    "ExpectationSet",
    "GraphError",
    "GraphPort",
    "JSONValue",
    "NavigationError",
    "PerceptionError",
    "PerceptionPort",
    "Polarity",
    "Role",
    "SemanticUIMap",
    "Severity",
    "StateEdge",
    "StateNode",
    "StateScoutError",
    "TerminationReason",
    "UIElement",
    "Verdict",
    "Violation",
]

# ---------------------------------------------------------------------------
# Aliases
# ---------------------------------------------------------------------------

JSONValue: TypeAlias = "str | int | float | bool | list[JSONValue] | dict[str, JSONValue] | None"

#: A role the crawler browses as. Free-form: the policy author names them.
#: One role is pinned per run (decision 5).
Role: TypeAlias = str

#: What the crawler can do to a page. Deliberately small — an action the crawler
#: cannot reliably replay after a resume does not belong here.
ActionKind: TypeAlias = Literal["click", "fill", "select", "navigate", "back", "submit"]

Severity: TypeAlias = Literal["low", "medium", "high", "critical"]

#: Outcome of checking one observed state against the policy.
Verdict: TypeAlias = Literal["clean", "violated"]

#: Whether a policy clause asserts presence or absence. `must_not_exist` is the
#: negation case StateScout exists to catch.
Polarity: TypeAlias = Literal["must_exist", "must_not_exist"]

#: Which set operation produced a violation (decision 6). `forbidden_present` is
#: FR-18, `required_absent` is FR-19. Reports must distinguish them (NFR-14).
ClauseType: TypeAlias = Literal["forbidden_present", "required_absent"]

#: Why a run ended. `frontier_exhausted` is the only one that means "complete".
TerminationReason: TypeAlias = Literal[
    "frontier_exhausted",
    "depth_limit",
    "max_states",
    "stopped",
    "error",
]


# ---------------------------------------------------------------------------
# Data crossing track boundaries
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CaptureBundle:
    """Everything Track A observed about one UI state at one moment.

    The unit of currency in this system: perception reads it, the graph
    fingerprints it, the orchestrator carries it between nodes. Frozen because
    it is a record of an observation — if you want a different one, capture again.
    """

    url: str
    dom: str
    #: Accessibility tree as parsed JSON. The orchestrator does not interpret
    #: this; it hands it to perception and to action enumeration.
    ax_tree: JSONValue
    #: `None` in DOM-only capture mode, which is a smoke test and not an audit
    #: (decision 7).
    screenshot_path: str | None = None
    title: str = ""


@dataclass(frozen=True, slots=True)
class Action:
    """One thing the crawler can do from a given state.

    `action_id` is a **content-addressed** hash of the control's role, accessible
    name, and normalized selector — never a DOM index (decision 1). Two
    consequences the whole loop depends on:

    * Replay after a checkpoint is safe, because the same control yields the same
      id even if the DOM reordered around it.
    * The same "Logout" link carries one id across every page, which makes
      cross-state analytics possible — while dedup stays scoped to
      `(state_id, action_id)`, so each state's occurrence is audited separately.
    """

    action_id: str
    kind: ActionKind
    #: How Track A locates the control — a selector, an AX-tree ref, whatever the
    #: crawler needs. Opaque to the orchestrator.
    target: str
    #: Human-readable, for logs and reports: `click "Admin settings"`.
    label: str = ""
    #: Payload for `fill` / `select`; ignored by other kinds.
    value: str | None = None


@dataclass(frozen=True, slots=True)
class UIElement:
    """One semantically meaningful thing perception found in a state."""

    #: Semantic role, e.g. `link`, `button`, `heading`, `dialog`.
    role: str
    name: str
    #: Free-form tags the negation engine matches policy subjects against,
    #: e.g. `admin-link`, `debug-panel`.
    tags: tuple[str, ...] = ()
    selector: str | None = None
    visible: bool = True
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class SemanticUIMap:
    """Track C's reading of a capture: what a user in this role can see and do.

    This is `S` in the negation engine's set algebra.
    """

    state_id: str
    url: str
    role: Role
    #: One-line description of the state, for reports.
    summary: str = ""
    elements: tuple[UIElement, ...] = ()
    #: Capabilities the state exposes, e.g. `delete-user`, `export-data`.
    capabilities: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ExpectationNode:
    """One machine-checkable clause extracted from the QA engineer's policy.

    Serialized into Track D's schema; the orchestrator produces these from
    English in Month 3 and never invents the storage format.
    """

    expectation_id: str
    polarity: Polarity
    #: The UI element or capability the clause is about.
    subject: str
    #: Roles the clause applies to. Empty means every role.
    roles: tuple[Role, ...] = ()
    #: The QA engineer's original sentence, kept so a report can quote it back.
    source_text: str = ""


@dataclass(frozen=True, slots=True)
class ExpectationSet:
    """The policy, split by the set operation each half requires (decision 6).

    `forbidden` clauses have polarity `must_not_exist` and are checked by
    intersection (FR-18). `required` clauses have polarity `must_exist` and are
    checked by difference (FR-19). Passing only the forbidden half would silently
    drop FR-19, so `audit()` takes the whole thing.
    """

    forbidden: tuple[ExpectationNode, ...] = ()
    required: tuple[ExpectationNode, ...] = ()


@dataclass(frozen=True, slots=True)
class Evidence:
    """Why a violation is believed to be real, in a form a human can check."""

    selector: str | None = None
    text: str | None = None
    screenshot_path: str | None = None


@dataclass(frozen=True, slots=True)
class Violation:
    """A state that breaks a policy clause. The product's actual output."""

    violation_id: str
    state_id: str
    expectation_id: str
    #: Which set operation caught this — the "policy constraint violated" field
    #: every report carries (NFR-14).
    clause_type: ClauseType
    severity: Severity
    #: Why the engine believes this is a violation, in plain language.
    rationale: str
    evidence: Evidence = field(default_factory=Evidence)


@dataclass(frozen=True, slots=True)
class StateNode:
    """A node in the exploration graph: one distinct UI state."""

    state_id: str
    url: str
    role: Role
    #: BFS depth at which this state was *first* reached.
    depth: int
    title: str = ""
    screenshot_path: str | None = None


@dataclass(frozen=True, slots=True)
class StateEdge:
    """Performing `action_id` in `from_state_id` led to `to_state_id`.

    `is_back_edge` marks an edge that closes a cycle. It is recorded, never
    pruned: the exploration graph is a cyclic directed graph, and a back-edge is
    evidence about the application's navigation structure.
    """

    from_state_id: str
    to_state_id: str
    action_id: str
    label: str = ""
    is_back_edge: bool = False


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class StateScoutError(Exception):
    """Base for every failure a port is allowed to surface to the orchestrator.

    Ports raise these; the orchestrator decides whether a failure is fatal, a
    retry, or a logged skip. Anything else escaping a port is a bug in that port.
    """


class CrawlerError(StateScoutError):
    """Track A failed. Prefer one of the two subclasses — they branch differently."""


class NavigationError(CrawlerError):
    """`open()` failed: DNS, timeout, unreachable host, non-navigable URL.

    Usually transient and usually worth a retry with backoff (decision 4).
    """


class ActionError(CrawlerError):
    """`act()` failed: stale element, detached node, action not replayable.

    Usually permanent for that `(state, action)` pair — mark failed and skip
    rather than retry (decision 4).
    """


class PerceptionError(StateScoutError):
    """The provider failed, was rate-limited, or returned unusable output."""


class GraphError(StateScoutError):
    """Persistence failed. May be transient — the store can be down."""


# ---------------------------------------------------------------------------
# Ports
# ---------------------------------------------------------------------------


@runtime_checkable
class CrawlerPort(Protocol):
    """Track A — Playwright capture and action execution.

    One instance is pinned to one role for the lifetime of a run (decision 5).
    """

    def open(self, url: str) -> CaptureBundle:
        """Navigate to `url` and capture the resulting state.

        Raises:
            NavigationError: the page could not be reached or rendered.
        """
        ...

    def act(self, action: Action) -> CaptureBundle:
        """Perform `action` against the current page and capture what follows.

        Raises:
            ActionError: the control was stale, detached, or not replayable.
            NavigationError: the action triggered navigation that then failed.
        """
        ...

    def enumerate_actions(self, bundle: CaptureBundle) -> tuple[Action, ...]:
        """Every action worth trying from this state, derived from the AX tree.

        Order must be deterministic — the BFS frontier's shape, and therefore a
        resumed run's behaviour, depends on it. Each `Action.action_id` is
        content-addressed per decision 1.
        """
        ...

    def close(self) -> None:
        """Release the browser. Safe to call twice."""
        ...


@runtime_checkable
class PerceptionPort(Protocol):
    """Track C — the VLM and the negation engine, behind one door.

    The orchestrator owns no model client of its own. Everything that talks to a
    model goes through here, so the rate limit is enforced in one place.
    """

    def analyze(self, bundle: CaptureBundle, role: Role) -> SemanticUIMap:
        """Turn a raw capture into what a user in `role` can see and do.

        Behaviour when `bundle.screenshot_path is None` is Track C's documented
        choice — reject, or degrade to DOM/AX-only. A degraded run is a smoke
        test, not an audit (decision 7).

        Raises:
            PerceptionError: the provider failed or returned unusable output.
        """
        ...

    def audit(
        self,
        s_current: SemanticUIMap,
        expectations: ExpectationSet,
    ) -> tuple[Violation, ...]:
        """Find every clause this state breaks.

        Computes ``S ∩ forbidden`` unioned with ``required \\ S`` — FR-18 and FR-19
        are
        different set operations, so both halves of the `ExpectationSet` are
        required (decision 6). Each returned `Violation` carries the `clause_type`
        that produced it. An empty result means the state is clean.

        Raises:
            PerceptionError: the negation engine could not reach a verdict.
        """
        ...

    def complete_text(self, prompt: str) -> str:
        """Run a text-only LLM completion.

        Exists so the Month 3 policy parser can reach a model without standing up
        a second client and a second rate limit. Returns the raw completion; the
        caller validates it.

        Raises:
            PerceptionError: the provider failed.
        """
        ...


@runtime_checkable
class GraphPort(Protocol):
    """Track D — fingerprinting, the visited set, and Neo4j persistence."""

    def fingerprint(self, bundle: CaptureBundle) -> str:
        """A stable content hash identifying this UI state.

        Implementations **normalize before hashing** — timestamps, CSRF and nonce
        tokens, and session ids are stripped, or the graph explodes with one node
        per page load (decision 2). This is the `state_id` every other type
        refers to.
        """
        ...

    def is_visited(self, state_id: str, action_id: str) -> bool:
        """Has this exact `(state, action)` pair already been claimed?

        The loop-prevention primitive. Note it is a *pair* check: revisiting a
        state is normal and expected, and is how cycles get recorded.
        """
        ...

    def mark_visited(self, state_id: str, action_id: str) -> None:
        """Claim a pair, **before** the action is executed (decision 3).

        Marking first gives at-most-once semantics against the application under
        test, which is generally not idempotent. The cost is that a crash between
        this call and a successful `persist_edge` leaves a claimed pair with no
        edge; resume treats that as done-but-unrecorded and logs it rather than
        re-firing a possibly destructive action.

        Idempotent.
        """
        ...

    def persist_state(self, state: StateNode) -> None:
        """Upsert a state node, deduplicated by `state_id`."""
        ...

    def persist_edge(self, edge: StateEdge) -> None:
        """Append an edge, **after** the action succeeded (decision 3).

        Never deduplicated away, never pruned.
        """
        ...

    def persist_violation(self, violation: Violation) -> None:
        """Record a violation against its state."""
        ...
