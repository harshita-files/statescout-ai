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
from apps.agent.perception.dom import extract_dom_elements


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
    tags = [
        tag
        for tag, keywords in _TAG_RULES
        if any(keyword in text for keyword in keywords)
    ]
    return tuple(sorted(set(tags)))


def _capabilities_for(element: CorrelatedElement) -> tuple[str, ...]:
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
    )


def build_semantic_map(
    bundle: CaptureBundle,
    role: Role,
    state_id: str,
) -> SemanticUIMap:
    """Build a deterministic SemanticUIMap from a CaptureBundle."""

    dom_elements = extract_dom_elements(bundle.dom)
    correlated = correlate(dom_elements, bundle.ax_tree)

    elements = tuple(
        _ui_element(element)
        for element in correlated
        if element.name or element.dom is not None
    )

    capabilities = sorted(
        {
            capability
            for element in correlated
            for capability in _capabilities_for(element)
        }
    )

    meaningful = [
        element.name
        for element in elements
        if element.name
    ]

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
