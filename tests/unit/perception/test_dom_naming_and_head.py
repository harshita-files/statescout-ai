"""Document metadata is not UI, and buttons are named the way browsers name them.

The DOM parser recorded `<link rel="stylesheet">` from the document head, and the
correlator turned the *tag* `link` into the accessibility *role* `link`. Every
page that loads a stylesheet therefore carried one unnamed hyperlink: one
spurious accessibility fault per page on every subject, all seventeen of Spring
PetClinic's included.

Separately, `<input type="submit" value="Go">` is named by its value, which the
DOM side ignored.
"""

from __future__ import annotations

from apps.agent.audit_models import Rule
from apps.agent.contracts import CaptureBundle
from apps.agent.negation.checks import check_a11y
from apps.agent.perception.correlate import _dom_name
from apps.agent.perception.dom import extract_dom_elements
from apps.agent.perception.semantic_map import build_semantic_map

RULE = Rule("p5", "Every icon-only control must have an accessible name.", "user", "high", "a11y")


def test_head_metadata_is_not_recorded() -> None:
    html = (
        '<html><head><title>T</title><link rel="stylesheet" href="m.css">'
        '<meta charset="utf-8"><base href="/"></head>'
        '<body><a href="/x">Home</a></body></html>'
    )
    tags = [e.tag for e in extract_dom_elements(html)]
    assert "link" not in tags and "meta" not in tags and "base" not in tags
    assert "a" in tags


def test_a_page_with_a_stylesheet_has_no_phantom_unnamed_link() -> None:
    bundle = CaptureBundle(
        url="http://app.test/",
        title="t",
        dom='<html><head><link rel="stylesheet" href="m.css"></head><body><p>Hi</p></body></html>',
        ax_tree={"nodes": []},
    )
    assert check_a11y(RULE, [build_semantic_map(bundle, "guest", "s1")]) == []


def _input(html: str):  # type: ignore[no-untyped-def]
    return next(e for e in extract_dom_elements(html) if e.tag == "input")


def test_a_submit_button_is_named_by_its_value() -> None:
    assert _dom_name(_input('<form><input type="submit" value="Go"></form>')) == "Go"


def test_an_image_button_is_named_by_its_alt() -> None:
    assert (
        _dom_name(_input('<form><input type="image" src="g.png" alt="Search"></form>')) == "Search"
    )


def test_a_text_field_is_not_named_by_its_value() -> None:
    """A text field's value is what the user typed, not its label."""
    assert _dom_name(_input('<form><input type="text" value="hello"></form>')) == ""


def test_a_hidden_input_is_not_visible() -> None:
    assert _input('<form><input type="hidden" name="t" value="x"></form>').hidden is True
