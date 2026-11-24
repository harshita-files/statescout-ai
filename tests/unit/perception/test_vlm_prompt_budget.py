"""Icon-only controls must reach the VLM even on a page with a long menu.

The VLM may only tag elements it is shown, and it is shown the first 80 distinct
elements in page order. On AdminLTE's project-edit page a 400-element sidebar
used the whole budget, so five icon-only trash buttons were never offered; the
model's reasoning noted the trash icons in the screenshot and that the element
list did not contain them. Icon-only controls are where the DOM says nothing and
vision is the only evidence, so they must be offered first.
"""

from __future__ import annotations

from apps.agent.contracts import UIElement
from apps.agent.perception.gemini import _MAX_PROMPT_ELEMENTS, _prompt_elements


def _page() -> tuple[UIElement, ...]:
    menu = tuple(UIElement(role="link", name=f"Menu item {i}") for i in range(300))
    trash = UIElement(role="link", name="")  # Font Awesome trash glyph
    blank = UIElement(role="button", name="")
    return (*menu, trash, blank)


def _offered(elements: tuple[UIElement, ...]) -> list[UIElement]:
    return [e for _, e in _prompt_elements(elements)]


def test_icon_only_controls_are_offered_past_a_long_menu() -> None:
    offered = _offered(_page())
    names = {e.name for e in offered}
    assert "" in names
    assert "" in names


def test_the_budget_is_still_respected() -> None:
    assert len(_offered(_page())) == _MAX_PROMPT_ELEMENTS


def test_tagged_elements_still_come_first() -> None:
    tagged = UIElement(role="button", name="Delete user", tags=("delete",))
    elements = (*_page(), tagged)
    assert tagged in _offered(elements)


def test_original_indices_are_kept_in_page_order() -> None:
    picked = _prompt_elements(_page())
    indices = [i for i, _ in picked]
    assert indices == sorted(indices)
    assert 300 in indices  # the trash link keeps its real index for the reply


def test_a_named_control_is_not_treated_as_icon_only() -> None:
    elements = (*_page()[:300], UIElement(role="link", name="Home"))
    assert "Home" not in {e.name for e in _offered(elements)}
