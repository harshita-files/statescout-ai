"""Deterministic Semantic UI Map construction.

This is the baseline Track C perception implementation.

It does not attempt to replace the eventual VLM. Instead it converts the
available DOM + AX evidence into the frozen SemanticUIMap contract so the
rest of StateScout can already operate without a model.
"""

from __future__ import annotations

import re

from apps.agent.contracts import CaptureBundle, Role, SemanticUIMap, UIElement
from apps.agent.perception.correlate import CorrelatedElement, correlate
from apps.agent.perception.dom import extract_dom_elements, is_form_field

_CAPABILITY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("delete-user", ("delete", "remove", "destroy", "wipe")),
    ("admin-access", ("admin", "administrator")),
    ("debug-access", ("debug", "developer tools")),
    ("export-data", ("export", "download data", "download records")),
    ("logout", ("logout", "log out", "sign out", "signoff")),
    ("login", ("login", "log in", "sign in")),
)

_TAG_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("admin", ("admin", "administrator")),
    ("delete", ("delete", "remove", "destroy", "wipe")),
    ("debug", ("debug",)),
    ("export", ("export",)),
    ("logout", ("logout", "log out", "sign out")),
    ("login", ("login", "log in", "sign in")),
)


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def _semantic_text(element: CorrelatedElement) -> str:
    parts = [
        element.name,
        element.role,
    ]

    if element.dom is not None:
        parts.extend(
            [
                element.dom.element_id or "",
                " ".join(element.dom.classes),
                element.dom.text or "",
                element.dom.aria_label or "",
            ]
        )

    return _normalize(" ".join(part for part in parts if part))


def _tags_for(element: CorrelatedElement) -> tuple[str, ...]:
    text = _semantic_text(element)
    tags = [tag for tag, keywords in _TAG_RULES if any(keyword in text for keyword in keywords)]
    return tuple(sorted(set(tags)))


#: A capability describes what a *control* does. Keyword-matching the whole
#: element text makes any prose that mentions "admin" or "delete" look like an
#: exposed capability, so only interactive elements may carry one.
_INTERACTIVE_ROLES = frozenset(
    {
        "button",
        "link",
        "menuitem",
        "menuitemcheckbox",
        "menuitemradio",
        "textbox",
        "searchbox",
        "checkbox",
        "radio",
        "combobox",
        "listbox",
        "option",
        "switch",
        "tab",
        "slider",
        "spinbutton",
        "treeitem",
    }
)
_INTERACTIVE_TAGS = frozenset({"a", "button", "input", "select", "textarea", "option", "summary"})


def _is_interactive(element: CorrelatedElement) -> bool:
    role = (element.role or "").strip().lower()
    if role:
        return role in _INTERACTIVE_ROLES
    tag = (element.dom.tag or "").strip().lower() if element.dom is not None else ""
    return tag in _INTERACTIVE_TAGS


def _capabilities_for(element: CorrelatedElement) -> tuple[str, ...]:
    if not _is_interactive(element):
        return ()
    text = _semantic_text(element)
    capabilities = [
        capability
        for capability, keywords in _CAPABILITY_RULES
        if any(keyword in text for keyword in keywords)
    ]
    return tuple(sorted(set(capabilities)))


def _ui_element(element: CorrelatedElement) -> UIElement:
    dom = element.dom

    return UIElement(
        role=element.role or (dom.tag if dom else "unknown"),
        name=element.name,
        tags=_tags_for(element),
        selector=element.selector,
        visible=True if dom is None else not dom.hidden,
        enabled=True if dom is None else not dom.disabled,
        decorative=bool(dom is not None and dom.decorative),
    )


#: Control roles the browser can report with an empty name that the DOM side
#: cannot see: the DOM parser never records an element that nests another one,
#: so an icon-only `<button><svg aria-hidden="true">...</svg></button>` or an
#: empty `<a href="/"><span></span></a>` exists only in the accessibility tree.
_AX_ONLY_CONTROLS = ("link", "button")

#: Roles the browser gives form fields.
_FIELD_ROLES = frozenset(
    {"textbox", "searchbox", "spinbutton", "checkbox", "radio", "combobox", "slider", "listbox"}
)


def _kept(correlated: tuple[CorrelatedElement, ...]) -> list[CorrelatedElement]:
    """Correlated evidence that belongs in the map.

    Anything named, or backed by a DOM element, is kept as before. A control the
    browser names with nothing is kept too: the browser's name computation is
    authoritative, so an empty name is a fault by definition. To avoid counting a
    fault twice, unnamed accessibility-only controls of a role are kept only
    beyond the number of unnamed DOM elements of that role already present (an
    empty `<button></button>` has no children, so the DOM side records it).
    """
    kept: list[CorrelatedElement] = []
    ax_only: dict[str, list[CorrelatedElement]] = {r: [] for r in _AX_ONLY_CONTROLS}
    dom_unnamed: dict[str, int] = dict.fromkeys(_AX_ONLY_CONTROLS, 0)
    for element in correlated:
        role = (element.role or "").strip().lower()
        if element.name or element.dom is not None:
            kept.append(element)
            if element.dom is not None and not element.name.strip() and role in dom_unnamed:
                dom_unnamed[role] += 1
        elif element.ax_node is not None and role in ax_only:
            ax_only[role].append(element)
    for role, nodes in ax_only.items():
        kept.extend(nodes[dom_unnamed[role] :])
    return _fields_the_browser_shows(kept, correlated)


def _fields_the_browser_shows(
    kept: list[CorrelatedElement], correlated: tuple[CorrelatedElement, ...]
) -> list[CorrelatedElement]:
    """Drop unnamed DOM-only form fields beyond those the browser shows unnamed.

    A field hidden by a stylesheet, or one the browser names itself (a file
    input is a button called "Choose File"), has no unnamed accessibility node.
    The DOM side cannot see either, so an unnamed DOM field counts as a fault
    only up to the number of unnamed fields in the accessibility tree.
    """
    budget = sum(
        1
        for e in correlated
        if e.dom is None
        and e.ax_node is not None
        and not e.name.strip()
        and (e.role or "").lower() in _FIELD_ROLES
    )
    out: list[CorrelatedElement] = []
    for element in kept:
        dom = element.dom
        unnamed_field = (
            dom is not None
            and element.ax_node is None
            and not dom.hidden
            and is_form_field(dom)
            and not element.name.strip()
        )
        if unnamed_field:
            if budget <= 0:
                continue
            budget -= 1
        out.append(element)
    return out


def build_semantic_map(
    bundle: CaptureBundle,
    role: Role,
    state_id: str,
) -> SemanticUIMap:
    """Build a deterministic SemanticUIMap from a CaptureBundle."""

    dom_elements = extract_dom_elements(bundle.dom)
    correlated = correlate(dom_elements, bundle.ax_tree)

    elements = tuple(_ui_element(element) for element in _kept(correlated))

    capabilities = sorted(
        {capability for element in correlated for capability in _capabilities_for(element)}
    )

    meaningful = [element.name for element in elements if element.name]

    if meaningful:
        preview = ", ".join(meaningful[:5])
        summary = f"Observed {len(elements)} UI elements: {preview}"
    else:
        summary = f"Observed {len(elements)} UI elements."

    return SemanticUIMap(
        state_id=state_id,
        url=bundle.url,
        role=role,
        summary=summary,
        elements=elements,
        capabilities=tuple(capabilities),
    )
