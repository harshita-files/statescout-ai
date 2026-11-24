"""A form field is named by its label, never by its `id`.

On the GOV.UK accessibility audit page the DOM side named a field by its `id`
when it had no label, so `<input id="nationality_irish">` counted as named and
every unlabelled field was missed. It also ignored a label wrapped around its
field, so `<label>Name <input></label>` could not be paired with the browser's
textbox "Name", and its DOM half was reported as a field with no name.
"""

from __future__ import annotations

from apps.agent.audit_models import Rule
from apps.agent.contracts import CaptureBundle
from apps.agent.negation.checks import check_a11y
from apps.agent.perception.correlate import _dom_name
from apps.agent.perception.dom import extract_dom_elements
from apps.agent.perception.semantic_map import build_semantic_map

RULE = Rule("p5", "Every icon-only control must have an accessible name.", "user", "high", "a11y")


def _fields(html: str):  # type: ignore[no-untyped-def]
    return [e for e in extract_dom_elements(html) if e.tag in {"input", "select", "textarea"}]


def _findings(dom: str, ax_nodes: list[dict]) -> int:  # type: ignore[type-arg]
    bundle = CaptureBundle(url="http://app.test/", title="t", dom=dom, ax_tree={"nodes": ax_nodes})
    return len(check_a11y(RULE, [build_semantic_map(bundle, "guest", "s1")]))


def _ax(role: str, name: str) -> dict:  # type: ignore[type-arg]
    return {"role": {"value": role}, "name": {"value": name}}


# --- naming -------------------------------------------------------------------


def test_an_id_is_not_a_field_name() -> None:
    (field,) = _fields('<form><input id="nationality_irish" type="checkbox"></form>')
    assert _dom_name(field) == ""


def test_a_label_for_names_its_field() -> None:
    (field,) = _fields('<form><label for="q">Search</label><input id="q" type="text"></form>')
    assert _dom_name(field) == "Search"


def test_a_wrapping_label_names_its_field() -> None:
    (field,) = _fields('<form><label>\n  Name\n  <input name="name" type="text"/>\n</label></form>')
    assert _dom_name(field) == "Name"


def test_a_label_for_a_different_id_names_nothing() -> None:
    (field,) = _fields('<form><label for="x">Name</label><input id="y" type="text"></form>')
    assert _dom_name(field) == ""


def test_an_empty_label_names_nothing() -> None:
    (field,) = _fields('<form><label for="e"></label><input id="e" type="text" value=""></form>')
    assert _dom_name(field) == ""


def test_placeholder_and_title_are_fallback_names() -> None:
    # The browser computes a name from these, so they are not "no name".
    (a,) = _fields('<form><input type="search" placeholder="Search"></form>')
    (b,) = _fields('<form><input type="text" title="Postcode"></form>')
    assert (_dom_name(a), _dom_name(b)) == ("Search", "Postcode")


def test_aria_labelledby_names_its_field() -> None:
    (field,) = _fields('<form><span id="l">Town</span><input aria-labelledby="l"></form>')
    assert _dom_name(field) == "Town"


def test_a_submit_button_is_still_named_by_its_value() -> None:
    (field,) = _fields('<form><input id="go" type="submit" value="Search"></form>')
    assert _dom_name(field) == "Search"


# --- what the accessibility check reports -------------------------------------


def test_unassociated_checkbox_labels_are_reported() -> None:
    dom = (
        "<form><fieldset><legend>Nationality</legend>"
        '<label>British</label><input id="b" type="checkbox" />'
        '<label>Irish</label><input id="i" type="checkbox" />'
        "</fieldset></form>"
    )
    assert (
        _findings(dom, [_ax("group", "Nationality"), _ax("checkbox", ""), _ax("checkbox", "")]) == 2
    )


def test_fields_inside_their_labels_are_not_reported() -> None:
    dom = (
        '<form><label>Name <input name="name" type="text"/></label>'
        '<label>Surname <input name="surname" type="text"/></label></form>'
    )
    assert _findings(dom, [_ax("textbox", "Name"), _ax("textbox", "Surname")]) == 0


def test_a_labelled_checkbox_is_not_reported() -> None:
    dom = '<form><input id="t" type="checkbox"><label for="t">I agree</label></form>'
    assert _findings(dom, [_ax("checkbox", "I agree")]) == 0


def test_only_the_unlabelled_parts_of_a_date_are_reported() -> None:
    dom = (
        '<form><label for="d">Date of birth</label><p>'
        '<input id="d" type="text"/><input id="m" type="text"/><input id="y" type="text"/>'
        "</p></form>"
    )
    ax = [_ax("textbox", "Date of birth"), _ax("textbox", ""), _ax("textbox", "")]
    assert _findings(dom, ax) == 2


# --- void elements as the browser serialises them -----------------------------


def test_every_unclosed_input_is_recorded() -> None:
    # The browser writes `<input ...>` with no slash. Each one used to be dropped
    # when another element followed it, so only the last field on a page existed.
    html = (
        '<form><label>British</label><input id="b" type="checkbox">'
        '<label>Irish</label><input id="i" type="checkbox">'
        '<label>Other</label><input id="o" type="checkbox"></form>'
    )
    assert [e.element_id for e in _fields(html)] == ["b", "i", "o"]


def test_every_unclosed_image_is_recorded() -> None:
    html = '<main><img src="a.png"><p>text</p><img src="b.png" alt="B"></main>'
    assert [e.alt for e in extract_dom_elements(html) if e.tag == "img"] == [None, "B"]


def test_text_after_an_image_does_not_become_its_name() -> None:
    (img,) = [
        e for e in extract_dom_elements('<a href="/"><img src="h.png"> Home</a>') if e.tag == "img"
    ]
    assert _dom_name(img) == ""


# --- fields the browser does not show ------------------------------------------


def test_a_field_hidden_by_inline_visibility_is_not_reported() -> None:
    dom = '<form><input id="a" size="1"><input style="visibility: hidden" id="b" size="1"></form>'
    assert _findings(dom, [_ax("textbox", "")]) == 1


def test_a_field_the_browser_omits_is_not_reported() -> None:
    # Hidden by a stylesheet class, which the DOM side cannot see: the browser
    # leaves it out of the accessibility tree, and the browser is authoritative.
    dom = '<form><input class="collapsed" type="text"></form>'
    assert _findings(dom, [_ax("button", "Search")]) == 0


def test_a_file_input_named_by_the_browser_is_not_reported() -> None:
    dom = '<form><input name="uploaded" type="file"><input type="submit" value="Upload"></form>'
    assert _findings(dom, [_ax("button", "Choose File"), _ax("button", "Upload")]) == 0


def test_unnamed_fields_are_reported_up_to_the_browsers_count() -> None:
    dom = "<form><input id='u' type='text'><input id='p' type='password'></form>"
    assert _findings(dom, [_ax("textbox", ""), _ax("textbox", "")]) == 2
