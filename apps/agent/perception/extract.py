"""Deterministic extraction of UI elements from a CaptureBundle."""

from __future__ import annotations

from typing import Any

from apps.agent.contracts import CaptureBundle, UIElement


# Structural AX roles that aren't useful as UI elements for our semantic map.
_STRUCTURAL_ROLES = {
    "none",
    "generic",
    "RootWebArea",
    "WebArea",
}


def _ax_nodes(ax_tree: Any) -> list[dict[str, Any]]:
    """Return the nodes from a Chrome CDP full AX-tree response."""
    if not isinstance(ax_tree, dict):
        return []

    nodes = ax_tree.get("nodes", [])
    if not isinstance(nodes, list):
        return []

    return [node for node in nodes if isinstance(node, dict)]


def _value(field: Any) -> str:
    """Extract the value from a CDP AX computed-property object."""
    if isinstance(field, dict):
        value = field.get("value")
        return str(value) if value is not None else ""

    return str(field) if field is not None else ""


def _ax_role(node: dict[str, Any]) -> str:
    return _value(node.get("role"))


def _ax_name(node: dict[str, Any]) -> str:
    return _value(node.get("name"))


def _ax_bool(
    node: dict[str, Any],
    property_name: str,
    default: bool,
) -> bool:
    """Read a boolean property from the AX node."""
    properties = node.get("properties", [])

    if not isinstance(properties, list):
        return default

    for prop in properties:
        if not isinstance(prop, dict):
            continue

        if prop.get("name") != property_name:
            continue

        return bool(_value(prop.get("value")))

    return default


def extract_ui_elements(bundle: CaptureBundle) -> tuple[UIElement, ...]:
    """Extract browser-grounded UI elements from the accessibility tree.

    The AX tree is currently the source of truth for:
      - semantic role
      - accessible name
      - ignored/visible state
      - disabled/enabled state

    DOM information will be used later to enrich elements with reliable
    selectors and source-level evidence.
    """
    elements: list[UIElement] = []

    for node in _ax_nodes(bundle.ax_tree):
        # Ignored AX nodes are not exposed through the accessibility layer.
        if node.get("ignored", False):
            continue

        role = _ax_role(node)
        name = _ax_name(node)

        if not role or role in _STRUCTURAL_ROLES:
            continue

        disabled = _ax_bool(node, "disabled", False)

        elements.append(
            UIElement(
                role=role,
                name=name,
                tags=(),
                selector=None,
                visible=True,
                enabled=not disabled,
            )
        )

    return tuple(elements)