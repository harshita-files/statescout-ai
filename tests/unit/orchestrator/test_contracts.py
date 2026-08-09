"""Construction tests and freeze guards for `apps/agent/contracts.py`.

M1-P1 asks for tests that "just construct each type". Construction is the floor,
not the ceiling: the value of this file is that it is *frozen*, so these tests
also pin the three properties a freeze is supposed to buy — no third-party
imports, immutable records, and no drift from the TypeScript mirror.

Nothing here tests behaviour, because there is no behaviour to test. If a test in
this file ever needs a mock, something has been added to `contracts.py` that does
not belong there.
"""

from __future__ import annotations

import ast
import dataclasses
import re
import sys
from pathlib import Path
from typing import get_args

import pytest

from apps.agent import contracts
from apps.agent.contracts import (
    Action,
    CaptureBundle,
    CrawlerError,
    CrawlerPort,
    Evidence,
    ExpectationNode,
    GraphError,
    GraphPort,
    PerceptionError,
    PerceptionPort,
    SemanticUIMap,
    StateEdge,
    StateNode,
    StateScoutError,
    UIElement,
    Violation,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACTS_PY = REPO_ROOT / "apps" / "agent" / "contracts.py"
SHARED_TYPES_TS = REPO_ROOT / "packages" / "shared-types" / "index.ts"

DATACLASSES = [
    Action,
    CaptureBundle,
    Evidence,
    ExpectationNode,
    SemanticUIMap,
    StateEdge,
    StateNode,
    UIElement,
    Violation,
]

PORTS = [CrawlerPort, PerceptionPort, GraphPort]

#: Python dataclass -> the TypeScript interface it must stay in sync with.
WIRE_MIRROR = {
    ExpectationNode: "ExpectationNode",
    StateEdge: "StateEdge",
    StateNode: "StateNode",
    Violation: "Violation",
}


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_capture_bundle_constructs() -> None:
    bundle = CaptureBundle(
        url="http://localhost:4173/dashboard",
        dom="<html><body><a id='admin-link'>Admin</a></body></html>",
        ax_tree={"role": "document", "children": [{"role": "link", "name": "Admin"}]},
        screenshot_path="/tmp/s1.png",
        title="Dashboard",
    )
    assert bundle.url.endswith("/dashboard")
    assert isinstance(bundle.ax_tree, dict)


def test_capture_bundle_allows_dom_only_mode() -> None:
    """Open question 7: screenshots are optional until Track A says otherwise."""
    bundle = CaptureBundle(url="http://x/", dom="<html/>", ax_tree=None)
    assert bundle.screenshot_path is None
    assert bundle.title == ""


def test_action_constructs() -> None:
    action = Action(
        action_id="click:#admin-link",
        kind="click",
        target="#admin-link",
        label='click "Admin"',
    )
    assert action.value is None


def test_fill_action_carries_a_value() -> None:
    action = Action(action_id="fill:#email", kind="fill", target="#email", value="qa@example.com")
    assert action.value == "qa@example.com"


def test_semantic_ui_map_constructs() -> None:
    ui_map = SemanticUIMap(
        state_id="s-abc123",
        url="http://localhost:4173/dashboard",
        role="guest",
        summary="Guest dashboard with an admin link visible",
        elements=(
            UIElement(role="link", name="Admin", tags=("admin-link",), selector="#admin-link"),
            UIElement(role="heading", name="Dashboard"),
        ),
        capabilities=("view-reports",),
    )
    assert len(ui_map.elements) == 2
    assert ui_map.elements[0].tags == ("admin-link",)
    assert ui_map.elements[1].visible is True


def test_expectation_node_constructs() -> None:
    expectation = ExpectationNode(
        expectation_id="e-1",
        polarity="must_not_exist",
        subject="admin-link",
        roles=("guest",),
        source_text="A guest should never see the admin link.",
    )
    assert expectation.polarity == "must_not_exist"


def test_expectation_with_no_roles_means_every_role() -> None:
    expectation = ExpectationNode(
        expectation_id="e-2", polarity="must_not_exist", subject="debug-panel"
    )
    assert expectation.roles == ()


def test_violation_constructs() -> None:
    violation = Violation(
        violation_id="v-1",
        state_id="s-abc123",
        expectation_id="e-1",
        severity="critical",
        rationale="admin-link is visible to role=guest",
        evidence=Evidence(selector="#admin-link", text="Admin", screenshot_path="/tmp/s1.png"),
    )
    assert violation.evidence.selector == "#admin-link"


def test_violation_evidence_defaults_to_empty() -> None:
    """Each Violation must get its own Evidence, not a shared one."""
    first = Violation(
        violation_id="v-1", state_id="s", expectation_id="e", severity="low", rationale=""
    )
    second = Violation(
        violation_id="v-2", state_id="s", expectation_id="e", severity="low", rationale=""
    )
    assert first.evidence == Evidence()
    assert first.evidence is not second.evidence


def test_state_node_constructs() -> None:
    node = StateNode(state_id="s-abc123", url="http://x/", role="guest", depth=2, title="Home")
    assert node.depth == 2
    assert node.screenshot_path is None


def test_state_edge_constructs_and_records_back_edges() -> None:
    forward = StateEdge(from_state_id="s-1", to_state_id="s-2", action_id="a-1", label="login")
    back = StateEdge(
        from_state_id="s-2",
        to_state_id="s-1",
        action_id="a-2",
        label="register -> login",
        is_back_edge=True,
    )
    assert forward.is_back_edge is False
    assert back.is_back_edge is True


@pytest.mark.parametrize("error", [CrawlerError, PerceptionError, GraphError])
def test_port_errors_share_one_base(error: type[Exception]) -> None:
    """The orchestrator catches `StateScoutError` and decides fatal vs. skip."""
    assert issubclass(error, StateScoutError)
    with pytest.raises(StateScoutError):
        raise error("boom")


# ---------------------------------------------------------------------------
# Freeze guards
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", DATACLASSES, ids=lambda c: c.__name__)
def test_records_are_frozen(cls: type) -> None:
    """A capture is a record of an observation; mutating one is a lie."""
    assert dataclasses.is_dataclass(cls)
    assert cls.__dataclass_params__.frozen  # type: ignore[attr-defined]


@pytest.mark.parametrize("cls", DATACLASSES, ids=lambda c: c.__name__)
def test_records_carry_no_behaviour(cls: type) -> None:
    """`contracts.py` is types only. A method here is logic in the wrong module."""
    field_names = {f.name for f in dataclasses.fields(cls)}
    defined = {
        name
        for name, value in vars(cls).items()
        if callable(value) and not name.startswith("__") and name not in field_names
    }
    assert not defined, f"{cls.__name__} defines behaviour: {sorted(defined)}"


def test_frozen_instances_reject_mutation() -> None:
    node = StateNode(state_id="s-1", url="http://x/", role="guest", depth=0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        node.depth = 1  # type: ignore[misc]


def test_no_third_party_imports() -> None:
    """Every track imports this module. It may not drag a dependency along."""
    tree = ast.parse(CONTRACTS_PY.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])

    third_party = roots - sys.stdlib_module_names
    assert not third_party, f"contracts.py imports non-stdlib modules: {sorted(third_party)}"


@pytest.mark.parametrize("port", PORTS, ids=lambda p: p.__name__)
def test_ports_are_runtime_checkable_protocols(port: type) -> None:
    """`fakes.py` proves conformance with `isinstance`; that needs this flag."""
    assert getattr(port, "_is_protocol", False)
    assert getattr(port, "_is_runtime_protocol", False)


def test_protocol_conformance_is_actually_detected() -> None:
    """Guards the guard: a runtime_checkable Protocol that accepts anything is
    worse than none, because the fakes' conformance tests would pass vacuously."""

    class Incomplete:
        def fingerprint(self, bundle: CaptureBundle) -> str:
            return ""

    assert not isinstance(Incomplete(), GraphPort)


def test_every_public_name_is_exported() -> None:
    """`__all__` is the contract's table of contents; a gap hides an interface."""
    public = {
        name
        for name, value in vars(contracts).items()
        if not name.startswith("_") and getattr(value, "__module__", None) == contracts.__name__
    }
    assert public <= set(contracts.__all__), (
        f"missing from __all__: {sorted(public - set(contracts.__all__))}"
    )


# ---------------------------------------------------------------------------
# Drift guard against the TypeScript mirror
# ---------------------------------------------------------------------------


def _camel(snake: str) -> str:
    head, *rest = snake.split("_")
    return head + "".join(part.title() for part in rest)


def _ts_interface_body(name: str) -> str:
    source = SHARED_TYPES_TS.read_text(encoding="utf-8")
    match = re.search(rf"export interface {name} \{{(.*?)^\}}", source, re.S | re.M)
    assert match, f"packages/shared-types/index.ts has no `export interface {name}`"
    return match.group(1)


@pytest.mark.parametrize(
    ("cls", "ts_name"), WIRE_MIRROR.items(), ids=lambda v: getattr(v, "__name__", v)
)
def test_wire_types_mirror_the_typescript_contract(cls: type, ts_name: str) -> None:
    """The extension and the agent describe the same JSON or one of them is broken.

    Neither type checker can see across the boundary, so this is the only place
    the drift shows up before a user does.
    """
    body = _ts_interface_body(ts_name)
    missing = [
        f.name for f in dataclasses.fields(cls) if not re.search(rf"\b{_camel(f.name)}\??:", body)
    ]
    assert not missing, f"{cls.__name__} fields absent from TS `{ts_name}`: {missing}"


@pytest.mark.parametrize(
    ("alias", "ts_name"),
    [("Severity", "Severity"), ("TerminationReason", "TerminationReason"), ("Verdict", "Verdict")],
)
def test_literal_unions_mirror_the_typescript_contract(alias: str, ts_name: str) -> None:
    source = SHARED_TYPES_TS.read_text(encoding="utf-8")
    match = re.search(rf"export type {ts_name} =(.*?);", source, re.S)
    assert match, f"packages/shared-types/index.ts has no `export type {ts_name}`"

    ts_members = set(re.findall(r'"([a-z_]+)"', match.group(1)))
    py_members = set(get_args(getattr(contracts, alias)))
    assert py_members == ts_members, f"{alias} differs: python={py_members} ts={ts_members}"
