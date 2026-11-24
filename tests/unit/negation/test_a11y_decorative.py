"""An element its author marked decorative is not an accessibility fault.

`alt=""`, `role="presentation"` or `role="none"`, and `aria-hidden="true"` tell
assistive technology to skip an element. Those were reported as controls missing
a name. On the W3C Before-and-After Demo's inaccessible survey page, 24 images
have no `alt` at all (real faults) and 25 have `alt=""` (correct).

An earlier attempt keyed this on whether the accessibility tree had a node for
the element. That is not the same thing: an image with no `alt` *is* in the tree,
unnamed, but the correlator cannot pair an unnamed node with its DOM element, so
it too arrives as DOM-only evidence. The author's declaration is the reliable
signal, so the check reads that.
"""

from __future__ import annotations

from apps.agent.audit_models import Rule
from apps.agent.contracts import SemanticUIMap, UIElement
from apps.agent.negation.checks import check_a11y
from apps.agent.perception.dom import extract_dom_elements

RULE = Rule("p5", "Every icon-only control must have an accessible name.", "user", "high", "a11y")


def _map(*elements: UIElement) -> SemanticUIMap:
    return SemanticUIMap(
        state_id="s1", url="http://app.test/", role="guest", summary="", elements=elements
    )


def test_a_decorative_image_is_not_a_violation() -> None:
    smap = _map(UIElement(role="img", name="", selector="img", decorative=True))
    assert check_a11y(RULE, [smap]) == []


def test_an_image_with_no_alt_is_a_violation() -> None:
    smap = _map(UIElement(role="img", name="", selector="img"))
    assert len(check_a11y(RULE, [smap])) == 1


def test_a_named_element_is_never_a_violation() -> None:
    smap = _map(UIElement(role="img", name="A cat and a dog"))
    assert check_a11y(RULE, [smap]) == []


def _decorative(html: str) -> list[bool]:
    return [e.decorative for e in extract_dom_elements(html) if e.tag == "img"]


def test_empty_alt_is_decorative_and_missing_alt_is_not() -> None:
    html = '<p><img src="a.gif" alt=""></p><p><img src="b.gif"></p><p><img src="c" alt="Cat"></p>'
    assert _decorative(html) == [True, False, False]


def test_presentation_role_and_aria_hidden_are_decorative() -> None:
    html = (
        '<p><img src="a" role="presentation"></p><p><img src="b" role="none"></p>'
        '<p><img src="c" aria-hidden="true"></p><p><img src="d" aria-hidden="false"></p>'
    )
    assert _decorative(html) == [True, True, True, False]
