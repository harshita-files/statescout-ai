"""The fakes must honour their Protocols — and the decisions behind them.

M1-P2 asks for "tests proving each fake honors its Protocol". `isinstance` against
a `runtime_checkable` Protocol only proves the method *names* exist, which is a
low bar: a fake whose `audit()` took the wrong arguments would sail through it.
So conformance here is checked structurally, signature by signature, against the
contract.

The rest of the file tests the scripted world itself. Every M1 and M2 test rests
on these fakes, so a wrong fake is a whole month of tests that pass while proving
nothing.
"""

from __future__ import annotations

import inspect
from typing import Protocol, get_type_hints

import pytest

from apps.agent.contracts import (
    Action,
    ActionError,
    CaptureBundle,
    CrawlerPort,
    ExpectationNode,
    ExpectationSet,
    GraphPort,
    NavigationError,
    PerceptionPort,
    StateEdge,
    StateNode,
)
from apps.agent.orchestrator.fakes import (
    DEFAULT_APP,
    DEFAULT_POLICY,
    FakeCrawler,
    FakeGraph,
    FakeLink,
    FakePage,
    FakePerception,
)

PAIRS: list[tuple[type[Protocol], type]] = [
    (CrawlerPort, FakeCrawler),
    (PerceptionPort, FakePerception),
    (GraphPort, FakeGraph),
]


def _protocol_methods(protocol: type) -> list[str]:
    return sorted(
        name
        for name in vars(protocol)
        if not name.startswith("_") and callable(getattr(protocol, name))
    )


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("protocol", "fake"), PAIRS, ids=lambda v: v.__name__)
def test_fake_satisfies_isinstance(protocol: type, fake: type) -> None:
    assert isinstance(fake(), protocol)


@pytest.mark.parametrize(("protocol", "fake"), PAIRS, ids=lambda v: v.__name__)
def test_fake_implements_every_protocol_method(protocol: type, fake: type) -> None:
    missing = [name for name in _protocol_methods(protocol) if not hasattr(fake, name)]
    assert not missing, f"{fake.__name__} is missing {missing}"


@pytest.mark.parametrize(("protocol", "fake"), PAIRS, ids=lambda v: v.__name__)
def test_fake_signatures_match_the_contract(protocol: type, fake: type) -> None:
    """The check `isinstance` cannot do.

    A fake whose `audit()` still took `negative_expectations` would satisfy
    `runtime_checkable` and then fail against the real port. Parameter names and
    resolved annotations both have to line up.
    """
    for name in _protocol_methods(protocol):
        expected = inspect.signature(getattr(protocol, name))
        actual = inspect.signature(getattr(fake, name))
        assert list(actual.parameters) == list(expected.parameters), (
            f"{fake.__name__}.{name} parameters differ from {protocol.__name__}"
        )

        expected_hints = get_type_hints(getattr(protocol, name))
        actual_hints = get_type_hints(getattr(fake, name))
        for param, hint in expected_hints.items():
            assert actual_hints.get(param) == hint, (
                f"{fake.__name__}.{name}({param}) is {actual_hints.get(param)}, "
                f"contract says {hint}"
            )


# ---------------------------------------------------------------------------
# The scripted app
# ---------------------------------------------------------------------------


def test_default_app_contains_the_mandated_cycle() -> None:
    """M1-P2 requires at least one cycle. Loop prevention is the whole point of
    the visited set, and a cycle-free fixture would never exercise it."""
    login_targets = {link.to for link in DEFAULT_APP["/login"].transitions}
    register_targets = {link.to for link in DEFAULT_APP["/register"].transitions}
    assert "/register" in login_targets
    assert "/login" in register_targets


def test_every_transition_points_at_a_real_page() -> None:
    for path, page in DEFAULT_APP.items():
        for link in page.transitions:
            assert link.to in DEFAULT_APP, f"{path} links to missing page {link.to}"


def test_open_returns_a_capture_of_that_page() -> None:
    crawler = FakeCrawler()
    bundle = crawler.open("http://fake.test/login")
    assert bundle.url.endswith("/login")
    assert bundle.title == "Sign in"
    assert bundle.screenshot_path is not None


def test_open_accepts_a_bare_path() -> None:
    assert FakeCrawler().open("/dashboard").title == "Dashboard"


def test_open_on_an_unknown_url_raises_navigation_error() -> None:
    with pytest.raises(NavigationError):
        FakeCrawler().open("/nope")


def test_act_follows_the_transition() -> None:
    crawler = FakeCrawler()
    bundle = crawler.open("/login")
    register = next(a for a in crawler.enumerate_actions(bundle) if "Create" in a.label)
    assert crawler.act(register).title == "Create account"


def test_act_before_open_raises_action_error() -> None:
    with pytest.raises(ActionError):
        FakeCrawler().act(Action(action_id="whatever", kind="click", target="#x"))


def test_act_with_an_action_from_another_page_raises_action_error() -> None:
    """The stale-element case: the orchestrator remembered a control that is not
    on the page the browser is now looking at."""
    crawler = FakeCrawler()
    dashboard = crawler.open("/dashboard")
    admin_link = next(a for a in crawler.enumerate_actions(dashboard) if "Admin" in a.label)

    crawler.open("/login")
    with pytest.raises(ActionError):
        crawler.act(admin_link)


def test_navigation_and_action_errors_are_distinguishable() -> None:
    """ADR-001 decision 4: the orchestrator branches on these, so the fake must
    raise the same two types the real crawler will."""
    crawler = FakeCrawler()
    with pytest.raises(NavigationError):
        crawler.open("/missing")
    with pytest.raises(ActionError):
        crawler.act(Action(action_id="x", kind="click", target="#x"))


def test_a_closed_crawler_stays_closed() -> None:
    crawler = FakeCrawler()
    crawler.close()
    crawler.close()  # idempotent
    with pytest.raises(NavigationError):
        crawler.open("/login")


# ---------------------------------------------------------------------------
# Action enumeration — ADR-001 decision 1
# ---------------------------------------------------------------------------


def test_enumeration_order_is_deterministic() -> None:
    """A resumed run must rebuild the same frontier as the run it resumed."""
    first = FakeCrawler().open("/dashboard")
    second = FakeCrawler().open("/dashboard")
    crawler = FakeCrawler()
    assert [a.action_id for a in crawler.enumerate_actions(first)] == [
        a.action_id for a in crawler.enumerate_actions(second)
    ]


def test_action_ids_are_content_addressed_not_positional() -> None:
    """The same 'Log out' control carries one id wherever it appears.

    A positional id (`button-1` on /dashboard, `button-2` on /admin) would make
    cross-state analytics meaningless and would break replay after a re-render.
    """
    crawler = FakeCrawler()
    dashboard = crawler.enumerate_actions(crawler.open("/dashboard"))
    admin = crawler.enumerate_actions(crawler.open("/admin"))

    logout_on_dashboard = next(a for a in dashboard if "Log out" in a.label)
    logout_on_admin = next(a for a in admin if "Log out" in a.label)
    assert logout_on_dashboard.action_id == logout_on_admin.action_id

    # ...and it is genuinely not positional: 'Log out' is index 1 on /dashboard
    # and index 1 on /admin, so also check a control that moved.
    assert dashboard[0].action_id != admin[0].action_id


def test_different_controls_get_different_ids() -> None:
    crawler = FakeCrawler()
    ids = [a.action_id for a in crawler.enumerate_actions(crawler.open("/dashboard"))]
    assert len(ids) == len(set(ids))


def test_enumeration_of_an_unknown_page_is_empty_not_an_error() -> None:
    bundle = CaptureBundle(url="http://fake.test/ghost", dom="<html/>", ax_tree=None)
    assert FakeCrawler().enumerate_actions(bundle) == ()


# ---------------------------------------------------------------------------
# Fingerprinting — ADR-001 decisions 2 and 5
# ---------------------------------------------------------------------------


def test_fingerprint_is_stable_across_reloads() -> None:
    """The fake app stamps a changing nonce into every render on purpose. A naive
    DOM hash mints a new state per page load and the crawl never terminates."""
    graph = FakeGraph()
    crawler = FakeCrawler()
    first = graph.fingerprint(crawler.open("/dashboard"))
    crawler.open("/login")
    second = graph.fingerprint(crawler.open("/dashboard"))
    assert first == second


def test_fingerprint_distinguishes_different_pages() -> None:
    graph = FakeGraph()
    crawler = FakeCrawler()
    assert graph.fingerprint(crawler.open("/login")) != graph.fingerprint(crawler.open("/admin"))


def test_fingerprint_distinguishes_roles() -> None:
    """ADR-001 decision 5 rests on this: a role-gated app yields different DOM,
    therefore different fingerprints, therefore separate StateNodes — with no
    mid-run role switching needed."""
    graph = FakeGraph()
    as_guest = FakeCrawler(role="guest").open("/dashboard")
    as_admin = FakeCrawler(role="admin").open("/dashboard")
    assert graph.fingerprint(as_guest) != graph.fingerprint(as_admin)


def test_perception_and_graph_agree_on_state_id() -> None:
    """Otherwise every violation is filed against a state the graph does not have.
    See the module docstring in fakes.py — the real contract does not guarantee
    this, and it is an open question for Tracks C and D."""
    bundle = FakeCrawler().open("/dashboard")
    assert FakePerception().analyze(bundle, "guest").state_id == FakeGraph().fingerprint(bundle)


# ---------------------------------------------------------------------------
# Perception
# ---------------------------------------------------------------------------


def test_analyze_surfaces_the_page_tags() -> None:
    ui_map = FakePerception().analyze(FakeCrawler().open("/dashboard"), "guest")
    tags = {tag for element in ui_map.elements for tag in element.tags}
    assert "admin-link" in tags
    assert ui_map.role == "guest"


def test_audit_flags_a_forbidden_element_present() -> None:
    """The planted M1 violation: admin-link visible to a guest."""
    perception = FakePerception()
    ui_map = perception.analyze(FakeCrawler(role="guest").open("/dashboard"), "guest")
    violations = perception.audit(ui_map, DEFAULT_POLICY)

    admin = [v for v in violations if v.expectation_id == "e-admin-link"]
    assert len(admin) == 1
    assert admin[0].clause_type == "forbidden_present"
    assert admin[0].state_id == ui_map.state_id
    assert admin[0].evidence.selector is not None


def test_audit_respects_the_role_scope_of_a_clause() -> None:
    """`admin-link` is forbidden for guests only. Flagging it for an admin would
    be a false positive, which is the failure mode that makes an auditor useless."""
    perception = FakePerception()
    ui_map = perception.analyze(FakeCrawler(role="admin").open("/dashboard"), "admin")
    assert not [
        v for v in perception.audit(ui_map, DEFAULT_POLICY) if v.expectation_id == "e-admin-link"
    ]


def test_audit_flags_a_required_element_absent() -> None:
    """FR-19. This is the case the forbidden-only reading of `audit()` would have
    silently dropped (ADR-001 decision 6) — /login has no logout button."""
    perception = FakePerception()
    ui_map = perception.analyze(FakeCrawler().open("/login"), "guest")
    violations = perception.audit(ui_map, DEFAULT_POLICY)

    missing = [v for v in violations if v.expectation_id == "e-logout"]
    assert len(missing) == 1
    assert missing[0].clause_type == "required_absent"


def test_audit_is_quiet_when_the_required_element_is_present() -> None:
    perception = FakePerception()
    ui_map = perception.analyze(FakeCrawler().open("/admin"), "guest")
    assert not [
        v for v in perception.audit(ui_map, DEFAULT_POLICY) if v.expectation_id == "e-logout"
    ]


def test_audit_returns_both_clause_types_from_one_call() -> None:
    """One call computes an intersection and a difference — that is the whole
    reason `audit()` takes an ExpectationSet rather than a list."""
    perception = FakePerception()
    ui_map = perception.analyze(FakeCrawler().open("/admin"), "guest")
    policy = ExpectationSet(
        forbidden=DEFAULT_POLICY.forbidden,
        required=(
            ExpectationNode(expectation_id="e-ghost", polarity="must_exist", subject="ghost"),
        ),
    )
    kinds = {v.clause_type for v in perception.audit(ui_map, policy)}
    assert kinds == {"forbidden_present", "required_absent"}


def test_audit_of_a_clean_state_returns_nothing() -> None:
    perception = FakePerception()
    ui_map = perception.analyze(FakeCrawler().open("/register"), "guest")
    assert perception.audit(ui_map, ExpectationSet(forbidden=DEFAULT_POLICY.forbidden)) == ()


def test_an_expectation_with_no_roles_applies_to_every_role() -> None:
    perception = FakePerception()
    policy = ExpectationSet(
        forbidden=(
            ExpectationNode(
                expectation_id="e-all", polarity="must_not_exist", subject="admin-link"
            ),
        )
    )
    for role in ("guest", "admin", "auditor"):
        ui_map = perception.analyze(FakeCrawler(role=role).open("/dashboard"), role)
        assert len(perception.audit(ui_map, policy)) == 1


def test_complete_text_is_scripted_and_deterministic() -> None:
    perception = FakePerception(
        scripted_completions={"admin link": '{"forbidden": ["admin-link"]}'}
    )
    assert (
        perception.complete_text("no guest may see the admin link")
        == '{"forbidden": ["admin-link"]}'
    )
    assert perception.complete_text("something else") == perception.complete_text("something else")


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------


def test_visited_set_tracks_pairs_not_states() -> None:
    """Revisiting a state is normal; it is how cycles get recorded. Only the
    `(state, action)` pair is once-only."""
    graph = FakeGraph()
    graph.mark_visited("s-1", "a-1")
    assert graph.is_visited("s-1", "a-1")
    assert not graph.is_visited("s-1", "a-2")
    assert not graph.is_visited("s-2", "a-1")


def test_mark_visited_is_idempotent() -> None:
    graph = FakeGraph()
    graph.mark_visited("s-1", "a-1")
    graph.mark_visited("s-1", "a-1")
    assert len(graph.visited) == 1


def test_states_are_deduplicated_by_id() -> None:
    graph = FakeGraph()
    graph.persist_state(StateNode(state_id="s-1", url="/a", role="guest", depth=0))
    graph.persist_state(StateNode(state_id="s-1", url="/a", role="guest", depth=7))
    assert len(graph.states) == 1


def test_first_write_wins_so_depth_stays_first_seen() -> None:
    """A cycle revisits a state at a greater depth. If the later write won, depth
    would drift and the depth limit would stop meaning anything."""
    graph = FakeGraph()
    graph.persist_state(StateNode(state_id="s-1", url="/a", role="guest", depth=0))
    graph.persist_state(StateNode(state_id="s-1", url="/a", role="guest", depth=3))
    assert graph.states["s-1"].depth == 0


def test_edges_are_never_deduplicated() -> None:
    """Dedup applies to node creation only. Two traversals of the same transition
    are two facts about the crawl."""
    graph = FakeGraph()
    edge = StateEdge(from_state_id="s-1", to_state_id="s-2", action_id="a-1")
    graph.persist_edge(edge)
    graph.persist_edge(edge)
    assert len(graph.edges) == 2


def test_back_edges_are_kept() -> None:
    """The exploration graph is cyclic. Pruning a back-edge to make it acyclic
    destroys the evidence the audit is built on."""
    graph = FakeGraph()
    graph.persist_edge(StateEdge(from_state_id="s-1", to_state_id="s-2", action_id="a-1"))
    graph.persist_edge(
        StateEdge(from_state_id="s-2", to_state_id="s-1", action_id="a-2", is_back_edge=True)
    )
    assert len(graph.back_edges()) == 1
    assert len(graph.edges_from("s-1")) == 1


def test_graph_instances_do_not_share_state() -> None:
    """A mutable default would leak one test's crawl into the next."""
    first = FakeGraph()
    first.mark_visited("s-1", "a-1")
    first.persist_edge(StateEdge(from_state_id="s-1", to_state_id="s-2", action_id="a-1"))
    second = FakeGraph()
    assert second.visited == set()
    assert second.edges == []


# ---------------------------------------------------------------------------
# Custom apps
# ---------------------------------------------------------------------------


def test_a_custom_app_can_be_supplied() -> None:
    """M2's adversarial fixtures — self-loops, fan-out, diamonds — are just other
    dicts. The fake must not be welded to DEFAULT_APP."""
    app = {
        "/only": FakePage(
            title="Only",
            transitions=(FakeLink(name="Refresh", to="/only"),),  # self-loop
        )
    }
    crawler = FakeCrawler(app)
    bundle = crawler.open("/only")
    action = crawler.enumerate_actions(bundle)[0]
    assert crawler.act(action).title == "Only"
