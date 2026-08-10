from apps.agent.contracts import CaptureBundle
from apps.agent.perception.extract import extract_ui_elements


def test_extract_ui_elements_from_ax_tree() -> None:
    bundle = CaptureBundle(
        url="http://fake.test/dashboard",
        dom="<html><body><button>Delete</button></body></html>",
        ax_tree={
            "nodes": [
                {
                    "nodeId": "1",
                    "ignored": False,
                    "role": {"type": "role", "value": "RootWebArea"},
                    "name": {"type": "computedString", "value": "Dashboard"},
                },
                {
                    "nodeId": "2",
                    "ignored": False,
                    "role": {"type": "role", "value": "button"},
                    "name": {
                        "type": "computedString",
                        "value": "Delete All Records",
                    },
                    "properties": [],
                },
            ]
        },
        screenshot_path=None,
        title="Dashboard",
    )

    elements = extract_ui_elements(bundle)

    assert len(elements) == 1

    element = elements[0]

    assert element.role == "button"
    assert element.name == "Delete All Records"
    assert element.visible is True
    assert element.enabled is True
    assert element.selector is None


def test_disabled_ax_element_is_not_enabled() -> None:
    bundle = CaptureBundle(
        url="http://fake.test/login",
        dom="<html><body><button disabled>Login</button></body></html>",
        ax_tree={
            "nodes": [
                {
                    "nodeId": "1",
                    "ignored": False,
                    "role": {"type": "role", "value": "button"},
                    "name": {"type": "computedString", "value": "Login"},
                    "properties": [
                        {
                            "name": "disabled",
                            "value": {
                                "type": "boolean",
                                "value": True,
                            },
                        }
                    ],
                }
            ]
        },
        screenshot_path=None,
        title="Login",
    )

    elements = extract_ui_elements(bundle)

    assert len(elements) == 1
    assert elements[0].name == "Login"
    assert elements[0].enabled is False


def test_ignored_and_structural_nodes_are_skipped() -> None:
    bundle = CaptureBundle(
        url="http://fake.test",
        dom="",
        ax_tree={
            "nodes": [
                {
                    "ignored": False,
                    "role": {"value": "generic"},
                    "name": {"value": ""},
                },
                {
                    "ignored": True,
                    "role": {"value": "button"},
                    "name": {"value": "Hidden Button"},
                },
                {
                    "ignored": False,
                    "role": {"value": "button"},
                    "name": {"value": "Visible Button"},
                },
            ]
        },
        screenshot_path=None,
        title="Test",
    )

    elements = extract_ui_elements(bundle)

    assert len(elements) == 1
    assert elements[0].name == "Visible Button"