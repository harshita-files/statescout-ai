from apps.agent.perception.correlate import correlate
from apps.agent.perception.dom import extract_dom_elements


def test_correlates_button_by_role_and_name() -> None:
    dom = """
    <button id="delete-btn">Delete All Records</button>
    """

    elements = extract_dom_elements(dom)

    ax = {
        "nodes": [
            {
                "role": {"value": "button"},
                "name": {"value": "Delete All Records"},
            }
        ]
    }

    result = correlate(elements, ax)

    assert len(result) == 1
    assert result[0].match_type == "role_name"
    assert result[0].dom is not None
    assert result[0].selector == "#delete-btn"


def test_preserves_unmatched_ax_evidence() -> None:
    result = correlate(
        [],
        {
            "nodes": [
                {
                    "role": {"value": "button"},
                    "name": {"value": "Invisible control"},
                }
            ]
        },
    )

    assert len(result) == 1
    assert result[0].match_type == "unmatched"
    assert result[0].dom is None


def test_preserves_dom_only_evidence() -> None:
    elements = extract_dom_elements(
        '<button id="hidden" style="display:none">Hidden</button>'
    )

    result = correlate(elements, {"nodes": []})

    assert len(result) == 1
    assert result[0].match_type == "dom_only"
    assert result[0].dom is not None
