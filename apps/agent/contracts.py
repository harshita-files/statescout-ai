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

Open questions for the review — resolve these BEFORE freezing
-------------------------------------------------------------
Each of these is a place where the parent handbook underspecifies the semantics.
They are documented rather than guessed, per M1-P1.

1. **Action identity across states** (`Action.action_id`) — is the id stable for
   "the same" control seen on two different pages, or unique per state? The
   visited set is keyed on `(state_id, action_id)`, so a globally stable id means
   a nav-bar link is explored once for the whole run; a per-state id means once
   per page. Track B assumes **per-state**, and `is_visited` is documented that
   way. Track A owns the answer. → Tracks A + B.

2. **What `fingerprint` hashes** — the handbook says it takes a `CaptureBundle`,
   i.e. raw DOM. DOM-level hashing makes a timestamp or a CSRF token look like a
   new state, which inflates the graph without bound. Fingerprinting the
   `SemanticUIMap` instead would be stabler but couples Track D to Track C.
   Signature below follows the handbook; the brittleness is Track D's call. → Track D.

3. **Who marks a pair visited** — the handbook specifies `is_visited` but no
   writer. `mark_visited` is added here so the orchestrator is not forced to
   infer visitation from `persist_edge` (which would break the moment an action
   is attempted but produces no edge). → Track D to confirm.

4. **`capture()` doing two jobs** — navigating to a URL and performing an action
   are different operations with different failure modes. They are one method
   because the handbook specifies `capture(url_or_action)`. Splitting them into
   `open(url)` and `act(action)` would type better. → Tracks A + B.

5. **Role switching** — nothing in the capture contract says how the crawler
   becomes a `guest` versus an `admin`. Track B assumes one crawler instance is
   pinned to one role for a whole run, and that a multi-role audit is multiple
   runs. If Track A intends mid-run role switching, this contract needs a method
   for it. → Tracks A + B.

6. **`audit`'s second argument** — `C_negative` is named
   `negative_expectations` here and documented as *only* the `must_not_exist`
   clauses. If Track C's engine wants the full expectation set so it can also
   check `must_exist`, say so now; the parameter changes meaning. → Track C.

7. **Screenshot optionality** — `screenshot_path` is `str | None` on the
   assumption that a DOM-only capture mode is useful in CI. If Track A always
   produces a screenshot, tighten it to `str`. → Track A.

Mirror
------
The wire-facing types here are mirrored in TypeScript at
``packages/shared-types/index.ts``. The two definitions must change in the same
PR; ``tests/unit/orchestrator/test_contracts.py`` fails when one drifts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol, TypeAlias, runtime_checkable

__all__ = [
    "Action",
    "ActionKind",
    "CaptureBundle",
    "CrawlerError",
    "CrawlerPort",
    "Evidence",
    "ExpectationNode",
    "GraphError",
    "GraphPort",
    "JSONValue",
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
    #: `None` when running in a DOM-only capture mode. See open question 7.
    screenshot_path: str | None = None
    title: str = ""


@dataclass(frozen=True, slots=True)
class Action:
    """One thing the crawler can do from a given state.

    `action_id` must be **deterministic**: replaying a run from a checkpoint
    depends on the same page yielding the same id for the same control. A
    position-derived id (`button-3`) breaks that as soon as the DOM reorders.
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

    This is `S` in the negation engine's `S ∩ C`.
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
    """Navigation failed, an action was not replayable, the page timed out."""


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

    One instance is pinned to one role for the lifetime of a run (open question 5).
    """

    def capture(self, target: str | Action) -> CaptureBundle:
        """Observe a UI state.

        A `str` target is a URL to navigate to; an `Action` is performed against
        the current page and the resulting state is captured. Either way the
        return value describes the state the browser is in afterwards.

        Raises:
            CrawlerError: navigation or action execution failed.
        """
        ...

    def enumerate_actions(self, bundle: CaptureBundle) -> tuple[Action, ...]:
        """Every action worth trying from this state, derived from the AX tree.

        Order must be deterministic — the BFS frontier's shape, and therefore a
        resumed run's behaviour, depends on it.
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

        Raises:
            PerceptionError: the provider failed or returned unusable output.
        """
        ...

    def audit(
        self,
        s_current: SemanticUIMap,
        negative_expectations: tuple[ExpectationNode, ...],
    ) -> tuple[Violation, ...]:
        """Find the clauses this state breaks — the `S ∩ C` intersection.

        `negative_expectations` carries only `must_not_exist` clauses
        (open question 6). An empty result means the state is clean.

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

        Two captures of the same logical state must produce the same string, or
        the graph grows without bound (open question 2). This is the `state_id`
        every other type refers to.
        """
        ...

    def is_visited(self, state_id: str, action_id: str) -> bool:
        """Has this exact `(state, action)` pair already been executed?

        The loop-prevention primitive. Note it is a *pair* check: revisiting a
        state is normal and expected, and is how cycles get recorded.
        """
        ...

    def mark_visited(self, state_id: str, action_id: str) -> None:
        """Record that a pair was executed. Idempotent (open question 3)."""
        ...

    def persist_state(self, state: StateNode) -> None:
        """Upsert a state node, deduplicated by `state_id`."""
        ...

    def persist_edge(self, edge: StateEdge) -> None:
        """Append an edge. Never deduplicated away, never pruned."""
        ...

    def persist_violation(self, violation: Violation) -> None:
        """Record a violation against its state."""
        ...
