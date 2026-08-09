"""In-memory implementations of the three ports (M1-P2).

Track B cannot wait for a browser, a VLM, and a Neo4j cluster to exist before
writing the loop that uses them. These fakes are the whole parallelism strategy:
they satisfy the `Protocol`s in `apps/agent/contracts.py`, so the exploration
loop that passes tests here is the same loop that will drive the real crawler.

They are **fakes**, not mocks — working implementations of a tiny scripted world,
not recorded call expectations. A test that asserts "the loop visited every state
exactly once" is a test about the loop; a test that asserts "the loop called
`analyze` three times" is a test about the fake, and will break for no reason.

Rules these obey
----------------
* Deterministic. Same input, same output, every run. No clock, no randomness, no
  network, no docker.
* Honest about the contract. Where ADR-001 made a decision — content-addressed
  action ids, normalization inside `fingerprint`, claim-before-execute — the
  fakes implement the decided behaviour, so a loop that passes against them is
  not relying on semantics the real thing will not provide.
* Cheap to inspect. Each fake exposes its recorded state as plain attributes so
  tests assert on outcomes rather than on call sequences.

Known gap surfaced while building these
---------------------------------------
`PerceptionPort.analyze()` returns a `SemanticUIMap` carrying a `state_id`, but
`GraphPort.fingerprint()` is what actually mints state ids, and `analyze()` never
receives one. Nothing in the contract says the two must agree, and if they
disagree every violation is filed against a state the graph does not have. The
fakes make them agree by construction. **Follow-up for Tracks C + D** — either
`analyze()` takes the `state_id`, or `SemanticUIMap` drops the field.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from apps.agent.contracts import (
    Action,
    ActionError,
    CaptureBundle,
    Evidence,
    ExpectationNode,
    ExpectationSet,
    JSONValue,
    NavigationError,
    Role,
    SemanticUIMap,
    StateEdge,
    StateNode,
    UIElement,
    Violation,
)

__all__ = [
    "DEFAULT_APP",
    "DEFAULT_POLICY",
    "FakeCrawler",
    "FakeGraph",
    "FakeLink",
    "FakePage",
    "FakePerception",
]

BASE_URL = "http://fake.test"


# ---------------------------------------------------------------------------
# The scripted web app
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FakeLink:
    """One control on a page, and where activating it leads."""

    name: str
    to: str
    #: ARIA role of the control. Feeds the action id, per ADR-001 decision 1.
    role: str = "link"


@dataclass(frozen=True, slots=True)
class FakePage:
    """One state of the scripted app."""

    title: str
    #: Semantic tags present in this state, e.g. `admin-link`, `debug-panel`.
    #: These are what the policy's `subject` matches against.
    elements: tuple[str, ...] = ()
    transitions: tuple[FakeLink, ...] = ()


#: A four-page app with two cycles, small enough to reason about exhaustively.
#:
#:     /login  <-->  /register          the mandated login <-> register cycle
#:     /login   -->  /dashboard  --> /admin --> /dashboard
#:     /dashboard --> /login             logout closes a second, longer cycle
#:
#: `/dashboard` carries `admin-link`, which the default policy forbids for guests.
#: That is the planted violation: the ground truth every M1 test asserts against.
DEFAULT_APP: Mapping[str, FakePage] = {
    "/login": FakePage(
        title="Sign in",
        elements=("login-form",),
        transitions=(
            FakeLink(name="Create an account", to="/register"),
            FakeLink(name="Sign in", to="/dashboard", role="button"),
        ),
    ),
    "/register": FakePage(
        title="Create account",
        elements=("register-form",),
        # Closes the login <-> register cycle. The loop must record this edge and
        # must not traverse it forever.
        transitions=(FakeLink(name="Back to sign in", to="/login"),),
    ),
    "/dashboard": FakePage(
        title="Dashboard",
        elements=("admin-link", "reports"),
        transitions=(
            FakeLink(name="Admin", to="/admin"),
            FakeLink(name="Log out", to="/login", role="button"),
        ),
    ),
    "/admin": FakePage(
        title="Admin",
        elements=("admin-panel", "delete-user"),
        transitions=(
            FakeLink(name="Back", to="/dashboard"),
            FakeLink(name="Log out", to="/login", role="button"),
        ),
    ),
}


#: The planted policy. `admin-link` forbidden for guests is the M1 demo
#: violation; `logout-button` required everywhere exercises FR-19, which the
#: forbidden-only reading of `audit()` would have silently dropped (ADR-001 #6).
DEFAULT_POLICY = ExpectationSet(
    forbidden=(
        ExpectationNode(
            expectation_id="e-admin-link",
            polarity="must_not_exist",
            subject="admin-link",
            roles=("guest",),
            source_text="A guest must never see the admin link.",
        ),
        ExpectationNode(
            expectation_id="e-delete-user",
            polarity="must_not_exist",
            subject="delete-user",
            roles=("guest",),
            source_text="A guest must never be able to delete a user.",
        ),
    ),
    required=(
        ExpectationNode(
            expectation_id="e-logout",
            polarity="must_exist",
            subject="logout-button",
            source_text="Every signed-in page must offer a way to log out.",
        ),
    ),
)


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _selector(link: FakeLink) -> str:
    """Stable across pages: the same 'Log out' button gets the same selector."""
    return f"#{_slug(link.name)}"


def _action_id(link: FakeLink) -> str:
    """Content-addressed id: hash of role + accessible name + selector.

    ADR-001 decision 1. Deliberately *not* positional — the same control yields
    the same id on every page and after any re-render, which is what makes replay
    after a checkpoint safe. Dedup is still scoped per state by the caller, using
    `(state_id, action_id)`.
    """
    material = f"{link.role}|{link.name}|{_selector(link)}"
    return hashlib.sha256(material.encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Crawler
# ---------------------------------------------------------------------------


class FakeCrawler:
    """A browser that is really a dict.

    Pinned to one role for its lifetime (ADR-001 decision 5). The role is baked
    into the rendered DOM, so a role-gated app produces different fingerprints
    for different roles with no contract change — which is precisely the argument
    decision 5 rests on.
    """

    def __init__(
        self,
        app: Mapping[str, FakePage] = DEFAULT_APP,
        *,
        role: Role = "guest",
        base_url: str = BASE_URL,
    ) -> None:
        self.app = app
        self.role = role
        self.base_url = base_url
        self.current: str | None = None
        self.closed = False
        #: Recorded for tests that care about traversal order.
        self.opened: list[str] = []
        self.acted: list[str] = []

    # -- helpers ----------------------------------------------------------

    def _path(self, url: str) -> str:
        return url[len(self.base_url) :] if url.startswith(self.base_url) else url

    def _render(self, path: str, page: FakePage) -> CaptureBundle:
        elements = "".join(f'<div data-tag="{tag}"></div>' for tag in page.elements)
        controls = "".join(
            f'<a id="{_slug(link.name)}" role="{link.role}">{link.name}</a>'
            for link in page.transitions
        )
        # The nonce is deliberate: it changes on every render, so a naive
        # fingerprint would mint a new state per page load. FakeGraph normalizes
        # it away, exercising ADR-001 decision 2 in every test that touches it.
        nonce = hashlib.sha256(f"{path}{len(self.opened)}{len(self.acted)}".encode()).hexdigest()
        dom = (
            f'<html data-nonce="{nonce}"><head><title>{page.title}</title></head>'
            f'<body data-role="{self.role}">{elements}{controls}</body></html>'
        )
        children: list[JSONValue] = [
            {"role": link.role, "name": link.name, "selector": _selector(link)}
            for link in page.transitions
        ]
        ax_tree: JSONValue = {"role": "document", "name": page.title, "children": children}
        return CaptureBundle(
            url=f"{self.base_url}{path}",
            dom=dom,
            ax_tree=ax_tree,
            screenshot_path=f"/fake/screenshots{path}.png",
            title=page.title,
        )

    # -- CrawlerPort ------------------------------------------------------

    def open(self, url: str) -> CaptureBundle:
        if self.closed:
            raise NavigationError("crawler is closed")
        path = self._path(url)
        page = self.app.get(path)
        if page is None:
            raise NavigationError(f"no such page: {url}")
        self.current = path
        self.opened.append(path)
        return self._render(path, page)

    def act(self, action: Action) -> CaptureBundle:
        if self.closed:
            raise ActionError("crawler is closed")
        if self.current is None:
            raise ActionError(f"cannot act before opening a page: {action.action_id}")

        page = self.app[self.current]
        link = next((c for c in page.transitions if _action_id(c) == action.action_id), None)
        if link is None:
            # The real crawler's stale-element case: the control the orchestrator
            # remembered is not on the page it is now looking at.
            raise ActionError(f"{action.action_id} is not available from {self.current}")

        destination = self.app.get(link.to)
        if destination is None:
            raise NavigationError(f"{link.name} leads nowhere: {link.to}")

        self.current = link.to
        self.acted.append(action.action_id)
        return self._render(link.to, destination)

    def enumerate_actions(self, bundle: CaptureBundle) -> tuple[Action, ...]:
        page = self.app.get(self._path(bundle.url))
        if page is None:
            return ()
        # Declaration order, which is stable across runs. A resumed run must
        # rebuild the same frontier as the run it resumed.
        return tuple(
            Action(
                action_id=_action_id(link),
                kind="click" if link.role == "button" else "navigate",
                target=_selector(link),
                label=f'{"click" if link.role == "button" else "follow"} "{link.name}"',
            )
            for link in page.transitions
        )

    def close(self) -> None:
        self.closed = True


# ---------------------------------------------------------------------------
# Perception
# ---------------------------------------------------------------------------


class FakePerception:
    """Canned semantics and a real set-algebra `audit()`.

    `analyze()` is canned — it reads the tags the fake crawler rendered rather
    than looking at pixels. `audit()` is genuinely implemented, because the loop's
    behaviour depends on *which* clause fired and a stub returning a fixed list
    would let a broken clean/violated edge pass its tests.
    """

    def __init__(self, *, scripted_completions: Mapping[str, str] | None = None) -> None:
        self.scripted_completions = scripted_completions or {}
        self.analyzed: list[str] = []
        self.audited: list[str] = []
        self.prompts: list[str] = []

    def analyze(self, bundle: CaptureBundle, role: Role) -> SemanticUIMap:
        tags = tuple(re.findall(r'data-tag="([^"]+)"', bundle.dom))
        controls = re.findall(r'<a id="([^"]+)" role="([^"]+)">([^<]+)</a>', bundle.dom)

        elements = tuple(
            UIElement(role="generic", name=tag, tags=(tag,), selector=f'[data-tag="{tag}"]')
            for tag in tags
        ) + tuple(
            UIElement(
                role=control_role,
                name=name,
                # A logout control is tagged so the FR-19 `required` clause has
                # something to match; this is the fake standing in for the VLM's
                # judgement that "Log out" is a logout affordance.
                tags=("logout-button",) if _slug(name) == "log-out" else (),
                selector=f"#{selector_id}",
            )
            for selector_id, control_role, name in controls
        )

        state_id = _fingerprint(bundle)
        self.analyzed.append(state_id)
        return SemanticUIMap(
            state_id=state_id,
            url=bundle.url,
            role=role,
            summary=f"{bundle.title} as {role}",
            elements=elements,
            capabilities=tags,
        )

    def audit(
        self,
        s_current: SemanticUIMap,
        expectations: ExpectationSet,
    ) -> tuple[Violation, ...]:
        """`S ∩ forbidden` unioned with `required \\ S` — ADR-001 decision 6."""
        self.audited.append(s_current.state_id)
        # Last element wins on a duplicate tag; deterministic, and no clause in
        # practice cares which of two identical affordances it points at.
        by_subject = {tag: element for element in s_current.elements for tag in element.tags}
        present = set(by_subject)

        violations: list[Violation] = []

        for clause in expectations.forbidden:
            if not _applies(clause, s_current.role) or clause.subject not in present:
                continue
            element = by_subject[clause.subject]
            violations.append(
                Violation(
                    violation_id=f"v-{s_current.state_id}-{clause.expectation_id}",
                    state_id=s_current.state_id,
                    expectation_id=clause.expectation_id,
                    clause_type="forbidden_present",
                    severity="critical",
                    rationale=f"{clause.subject} is present for role={s_current.role}",
                    evidence=Evidence(
                        selector=element.selector,
                        text=element.name,
                        screenshot_path=None,
                    ),
                )
            )

        for clause in expectations.required:
            if not _applies(clause, s_current.role) or clause.subject in present:
                continue
            violations.append(
                Violation(
                    violation_id=f"v-{s_current.state_id}-{clause.expectation_id}",
                    state_id=s_current.state_id,
                    expectation_id=clause.expectation_id,
                    clause_type="required_absent",
                    severity="medium",
                    rationale=f"{clause.subject} is missing for role={s_current.role}",
                )
            )

        return tuple(violations)

    def complete_text(self, prompt: str) -> str:
        self.prompts.append(prompt)
        for needle, completion in self.scripted_completions.items():
            if needle in prompt:
                return completion
        # Deterministic and obviously synthetic, so a test that accidentally
        # depends on real model output fails loudly instead of subtly.
        return '{"forbidden": [], "required": [], "ambiguities": []}'


def _applies(clause: ExpectationNode, role: Role) -> bool:
    """An expectation with no roles applies to every role."""
    return not clause.roles or role in clause.roles


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

#: Volatile markup that must not affect a state's identity (ADR-001 decision 2).
#: A raw-DOM hash without this mints a new state on every page load and the
#: exploration never terminates.
_VOLATILE = (
    re.compile(r'\b(?:data-nonce|nonce|csrf[-_]?token|session[-_]?id)="[^"]*"', re.I),
    re.compile(r"\b\d{4}-\d{2}-\d{2}T[\d:.]+Z?"),
    re.compile(r"\b\d{10,13}\b"),
)


def _normalize(dom: str) -> str:
    for pattern in _VOLATILE:
        dom = pattern.sub("", dom)
    return dom


def _fingerprint(bundle: CaptureBundle) -> str:
    """Shared by `FakeGraph` and `FakePerception` so their state ids agree.

    See the module docstring: the real contract does not guarantee this, and it
    is an open question for Tracks C and D.
    """
    return "s-" + hashlib.sha256(_normalize(bundle.dom).encode()).hexdigest()[:12]


@dataclass
class FakeGraph:
    """Fingerprinting, the visited set, and persistence — all in dicts.

    Attributes are public because tests assert on the graph that was built, not
    on the calls that built it.
    """

    #: `(state_id, action_id)` pairs claimed via `mark_visited`.
    visited: set[tuple[str, str]] = field(default_factory=set)
    #: Deduplicated by `state_id` — node creation is the only thing deduped.
    states: dict[str, StateNode] = field(default_factory=dict)
    #: Append-only. Edges are never deduplicated and never pruned, because a
    #: back-edge is evidence about the app's navigation structure.
    edges: list[StateEdge] = field(default_factory=list)
    violations: list[Violation] = field(default_factory=list)

    def fingerprint(self, bundle: CaptureBundle) -> str:
        return _fingerprint(bundle)

    def is_visited(self, state_id: str, action_id: str) -> bool:
        return (state_id, action_id) in self.visited

    def mark_visited(self, state_id: str, action_id: str) -> None:
        """Idempotent by construction — it is a set."""
        self.visited.add((state_id, action_id))

    def persist_state(self, state: StateNode) -> None:
        # First write wins: `depth` must stay the depth at which the state was
        # *first* reached, or a cycle would keep rewriting it deeper.
        self.states.setdefault(state.state_id, state)

    def persist_edge(self, edge: StateEdge) -> None:
        self.edges.append(edge)

    def persist_violation(self, violation: Violation) -> None:
        self.violations.append(violation)

    # -- conveniences for tests ------------------------------------------

    def edges_from(self, state_id: str) -> Sequence[StateEdge]:
        return [edge for edge in self.edges if edge.from_state_id == state_id]

    def back_edges(self) -> Sequence[StateEdge]:
        return [edge for edge in self.edges if edge.is_back_edge]
