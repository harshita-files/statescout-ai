from apps.agent.contracts import CaptureBundle
from apps.agent.perception.semantic_map import build_semantic_map


def test_builds_delete_capability() -> None:
    bundle = CaptureBundle(
        url="http://test/login",
        title="Dashboard",
        dom="""
        <main>
          <button id="delete-db">Delete All Records</button>
        </main>
        """,
        ax_tree={
            "nodes": [
                {
                    "role": {"value": "button"},
                    "name": {"value": "Delete All Records"},
                }
            ]
        },
    )

    result = build_semantic_map(bundle, "guest", "state-123")

    assert result.state_id == "state-123"
    assert result.role == "guest"
    assert "delete-user" in result.capabilities

    button = next(element for element in result.elements if element.name == "Delete All Records")

    assert button.selector == "#delete-db"
    assert "delete" in button.tags
    assert button.enabled is True
    assert button.visible is True


def test_hidden_dom_element_is_not_visible() -> None:
    bundle = CaptureBundle(
        url="http://test/",
        dom='<button style="display:none">Admin</button>',
        ax_tree={"nodes": []},
    )

    result = build_semantic_map(bundle, "guest", "state-1")

    assert len(result.elements) == 1
    assert result.elements[0].visible is False
