"""An image's `alt` text is its accessible name, on the DOM side too.

The DOM side named elements from aria-label, text or id only. An image with
`alt="Cat"` therefore had an empty DOM name, could not be paired with its
accessibility-tree node by name, and its DOM half was reported as an image with
no accessible name. On the W3C demo's accessible pages, which have no image
missing `alt`, this produced three to five spurious faults per page.
"""

from __future__ import annotations

from apps.agent.audit_models import Rule
from apps.agent.contracts import CaptureBundle
from apps.agent.negation.checks import check_a11y
from apps.agent.perception.correlate import _dom_name
from apps.agent.perception.dom import extract_dom_elements
from apps.agent.perception.semantic_map import build_semantic_map

RULE = Rule("p5", "Every icon-only control must have an accessible name.", "user", "high", "a11y")


def _img(html: str):  # type: ignore[no-untyped-def]
    return next(e for e in extract_dom_elements(html) if e.tag == "img")


def test_alt_text_names_an_image() -> None:
    assert _dom_name(_img('<p><img src="c.jpg" alt="A cat"></p>')) == "A cat"


def test_aria_label_takes_precedence_over_alt() -> None:
    assert _dom_name(_img('<p><img src="c" alt="x" aria-label="Logo"></p>')) == "Logo"


def test_a_labelled_image_is_not_reported() -> None:
    bundle = CaptureBundle(
        url="http://app.test/",
        title="t",
        dom='<main><p><img src="c.jpg" alt="A cat"></p></main>',
        ax_tree={"nodes": [{"role": {"value": "image"}, "name": {"value": "A cat"}}]},
    )
    smap = build_semantic_map(bundle, "guest", "s1")
    assert check_a11y(RULE, [smap]) == []


def test_an_image_with_no_alt_is_still_reported() -> None:
    bundle = CaptureBundle(
        url="http://app.test/",
        title="t",
        dom='<main><p><img src="c.jpg"></p></main>',
        ax_tree={"nodes": [{"role": {"value": "image"}, "name": {"value": ""}}]},
    )
    smap = build_semantic_map(bundle, "guest", "s1")
    assert len(check_a11y(RULE, [smap])) == 1
