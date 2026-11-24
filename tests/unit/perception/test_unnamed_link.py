"""A link the browser names with nothing is an accessibility fault, and must be seen.

Spring PetClinic's logo link is `<a class="navbar-brand" href="/"><span></span></a>`:
no text, no label. The browser lists it as a link with an empty name, but the
semantic map dropped every accessibility node with neither a name nor a DOM
counterpart, and the DOM parser never records an anchor with a nested element.
Before the repairs a phantom stylesheet `<link>` happened to yield a link finding
on the same page, which hid the gap.
"""

from __future__ import annotations

from typing import Any

from apps.agent.audit_models import Rule
from apps.agent.contracts import CaptureBundle
from apps.agent.negation.checks import check_a11y
from apps.agent.perception.semantic_map import build_semantic_map

RULE = Rule("p5", "Every icon-only control must have an accessible name.", "user", "high", "a11y")


def _faults(dom: str, *links: str) -> list[str]:
    ax: dict[str, Any] = {
        "nodes": [{"role": {"value": "link"}, "name": {"value": n}} for n in links]
    }
    bundle = CaptureBundle(url="http://a.test/", title="t", dom=dom, ax_tree=ax)
    smap = build_semantic_map(bundle, "guest", "s")
    return [v.rationale for v in check_a11y(RULE, [smap])]


def test_an_unnamed_link_is_reported() -> None:
    faults = _faults('<nav><a class="navbar-brand" href="/"><span></span></a></nav>', "")
    assert len(faults) == 1 and "link" in faults[0]


def test_a_named_link_is_not_reported() -> None:
    assert _faults('<nav><a href="/">Home</a></nav>', "Home") == []


def test_a_link_named_by_its_image_is_not_reported() -> None:
    dom = '<p><a href="http://www.w3.org/"><img alt="W3C logo" src="w3c.png"></a></p>'
    assert _faults(dom, "W3C logo") == []


def _button_faults(dom: str, *buttons: str) -> list[str]:
    ax: dict[str, Any] = {
        "nodes": [{"role": {"value": "button"}, "name": {"value": n}} for n in buttons]
    }
    bundle = CaptureBundle(url="http://a.test/", title="t", dom=dom, ax_tree=ax)
    smap = build_semantic_map(bundle, "guest", "s")
    return [v.rationale for v in check_a11y(RULE, [smap])]


def test_an_icon_only_button_is_reported() -> None:
    """StockWatch SW-06: an SVG marked aria-hidden is the button's only content."""
    dom = (
        '<div><button type="button" class="icon-btn star">'
        '<svg aria-hidden="true"><path d="M0 0"/></svg></button></div>'
    )
    faults = _button_faults(dom, "")
    assert len(faults) == 1 and "button" in faults[0]


def test_an_empty_button_the_dom_already_reports_is_not_counted_twice() -> None:
    faults = _button_faults("<div><button></button></div>", "")
    assert len(faults) == 1


def test_a_labelled_icon_button_is_not_reported() -> None:
    dom = '<div><button aria-label="Toggle theme"><svg aria-hidden="true"></svg></button></div>'
    assert _button_faults(dom, "Toggle theme") == []
