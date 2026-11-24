"""Regression tests from the DVWA independent-subject run.

A capability describes what a control *does*. Prose that merely mentions the
word must not create one: DVWA served 13 translated README files, and every one
of them was reported as exposing admin access to a guest.
"""

from __future__ import annotations

from typing import Any

from apps.agent.contracts import CaptureBundle, SemanticUIMap
from apps.agent.perception.semantic_map import build_semantic_map

_README = (
    "DAMN VULNERABLE WEB APPLICATION. Default username is admin. "
    "You can also use this to reset the administrator credentials, "
    "export the logs to a file, remove the database, or debug the setup."
)


def _map(dom: str, ax: dict[str, Any]) -> SemanticUIMap:
    return build_semantic_map(
        CaptureBundle(url="http://app.test/README.md", title="README", dom=dom, ax_tree=ax),
        "guest",
        "state-1",
    )


def test_prose_mentioning_admin_does_not_create_a_capability() -> None:
    result = _map(
        f"<main><pre>{_README}</pre></main>",
        {"nodes": [{"role": {"value": "generic"}, "name": {"value": ""}}]},
    )
    assert result.capabilities == ()


def test_paragraph_text_does_not_create_a_capability() -> None:
    result = _map(
        f"<main><p>{_README}</p><td>Server Administrator</td></main>",
        {"nodes": [{"role": {"value": "paragraph"}, "name": {"value": ""}}]},
    )
    assert "admin-access" not in result.capabilities
    assert "delete-user" not in result.capabilities
    assert "export-data" not in result.capabilities
    assert "debug-access" not in result.capabilities


def test_an_actual_admin_control_still_creates_the_capability() -> None:
    result = _map(
        '<main><a id="admin-link" href="/admin">Admin Panel</a></main>',
        {"nodes": [{"role": {"value": "link"}, "name": {"value": "Admin Panel"}}]},
    )
    assert "admin-access" in result.capabilities


def test_an_actual_delete_button_still_creates_the_capability() -> None:
    result = _map(
        '<main><button id="del">Delete All Records</button></main>',
        {"nodes": [{"role": {"value": "button"}, "name": {"value": "Delete All Records"}}]},
    )
    assert "delete-user" in result.capabilities
