"""Deterministic correlation between DOM evidence and AX-tree semantics.

Track C deliberately treats DOM/AX correlation as an evidence-matching
problem rather than assuming that serialized DOM and AX nodes have a perfect
one-to-one relationship.

Matching priority:
1. Browser-provided DOM identifiers when both sides expose them.
2. Role + accessible name.
3. Accessible name/text.
4. Unmatched evidence is preserved rather than force-merged.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from apps.agent.perception.dom import DOMElement, is_form_field


@dataclass(frozen=True, slots=True)
class CorrelatedElement:
    """DOM/AX evidence believed to describe the same UI element."""

    role: str
    name: str
    dom: DOMElement | None = None
    ax_node: dict[str, Any] | None = None
    match_type: str = "unmatched"

    @property
    def selector(self) -> str | None:
        if self.dom is None:
            return None

        if self.dom.element_id:
            return f"#{self.dom.element_id}"

        if self.dom.tag:
            return self.dom.tag

        return None


def _value(value: Any) -> str:
    """Extract Chrome AX values such as {'value': 'Delete'}."""
    if isinstance(value, dict):
        value = value.get("value", "")
    return str(value or "").strip()


def ax_role(node: dict[str, Any]) -> str:
    return _value(node.get("role")).lower()


def ax_name(node: dict[str, Any]) -> str:
    return _value(node.get("name"))


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def _dom_name(element: DOMElement) -> str:
    if is_form_field(element):
        # A field's name comes from its label. Its `id` is not announced, and a
        # text field's value is what the user typed.
        return element.aria_label or element.label or ""
    # For an image, `alt` is the accessible name after aria-label. Without it a
    # labelled image could not be paired with its accessibility node by name.
    alt = element.alt if element.tag == "img" else None
    if element.tag == "input":
        # A button-like input is named by its value (an image button by its alt);
        # a text field's value is what the user typed, so it is never the name.
        if element.input_type in {"submit", "button", "reset"}:
            alt = element.value
        elif element.input_type == "image":
            alt = element.alt
    return element.aria_label or alt or element.text or element.element_id or ""


def _same_name(left: str, right: str) -> bool:
    return bool(left and right and _normalize(left) == _normalize(right))


#: The role the browser gives each `<input type>`; anything else is a textbox.
_INPUT_ROLES: dict[str, set[str]] = {
    "checkbox": {"checkbox"},
    "radio": {"radio"},
    "submit": {"button"},
    "button": {"button"},
    "reset": {"button"},
    "image": {"button"},
    "file": {"button"},
    "search": {"searchbox", "textbox"},
    "number": {"spinbutton"},
    "range": {"slider"},
}


def _same_role(ax: str, dom: DOMElement) -> bool:
    if not ax:
        return True

    dom_role = (dom.role or "").lower()

    if dom_role:
        return dom_role == ax

    if dom.tag.lower() == "input":
        return ax in _INPUT_ROLES.get(dom.input_type or "", {"textbox"})

    # Native HTML semantics.
    native_roles = {
        "button": {"button"},
        "a": {"link"},
        "input": {"textbox"},
        "textarea": {"textbox"},
        "select": {"combobox"},
        "h1": {"heading"},
        "h2": {"heading"},
        "h3": {"heading"},
        "h4": {"heading"},
        "h5": {"heading"},
        "h6": {"heading"},
    }

    return ax in native_roles.get(dom.tag.lower(), set())


def _ax_nodes(ax_tree: Any) -> list[dict[str, Any]]:
    """Handle both Chrome's {'nodes': [...]} form and a single AX node."""
    if not isinstance(ax_tree, dict):
        return []

    nodes = ax_tree.get("nodes")
    if isinstance(nodes, list):
        return [n for n in nodes if isinstance(n, dict)]

    if "role" in ax_tree:
        result = [ax_tree]
        children = ax_tree.get("children", [])
        if isinstance(children, list):
            for child in children:
                if isinstance(child, dict):
                    result.extend(_ax_nodes(child))
        return result

    return []


def correlate(
    dom_elements: Sequence[DOMElement],
    ax_tree: Any,
) -> tuple[CorrelatedElement, ...]:
    """Correlate semantic AX nodes with DOM evidence.

    Ambiguous matches are not guessed. An AX node gets at most one DOM
    candidate, and a DOM element is not consumed twice.
    """

    ax_nodes = _ax_nodes(ax_tree)
    unused_dom = list(dom_elements)
    result: list[CorrelatedElement] = []

    for node in ax_nodes:
        role = ax_role(node)
        name = ax_name(node)

        # Ignore the document/root structure unless it has a meaningful name.
        if role in {"", "none", "generic", "document", "rootwebarea"} and not name:
            continue

        candidates = [element for element in unused_dom if _same_role(role, element)]

        # Strong semantic match: role + accessible name.
        strong = [element for element in candidates if _same_name(name, _dom_name(element))]

        if len(strong) == 1:
            element = strong[0]
            unused_dom.remove(element)
            result.append(
                CorrelatedElement(
                    role=role or (element.role or element.tag),
                    name=name or _dom_name(element),
                    dom=element,
                    ax_node=node,
                    match_type="role_name",
                )
            )
            continue

        # If role is absent/weak, name-only matching is acceptable only when
        # there is exactly one candidate.
        name_matches = [element for element in unused_dom if _same_name(name, _dom_name(element))]

        if len(name_matches) == 1:
            element = name_matches[0]
            unused_dom.remove(element)
            result.append(
                CorrelatedElement(
                    role=role or (element.role or element.tag),
                    name=name or _dom_name(element),
                    dom=element,
                    ax_node=node,
                    match_type="name",
                )
            )
            continue

        # Preserve AX evidence even when no safe DOM match exists.
        result.append(
            CorrelatedElement(
                role=role,
                name=name,
                dom=None,
                ax_node=node,
                match_type="unmatched",
            )
        )

    # DOM elements not represented by AX remain useful evidence. In
    # particular, hidden elements may deliberately be absent from the AX tree.
    for element in unused_dom:
        result.append(
            CorrelatedElement(
                role=element.role or element.tag,
                name=_dom_name(element),
                dom=element,
                ax_node=None,
                match_type="dom_only",
            )
        )

    return tuple(result)
