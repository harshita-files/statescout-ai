from apps.agent.perception.dom import extract_dom_elements


def test_extract_relevant_dom_attributes() -> None:
    dom = """
    <button
        id="btn-delete"
        class="btn btn-danger"
        aria-label="Delete all records"
        disabled
    >
        Delete All Records
    </button>
    """

    elements = extract_dom_elements(dom)

    assert len(elements) == 1

    element = elements[0]

    assert element.tag == "button"
    assert element.element_id == "btn-delete"
    assert element.classes == ("btn", "btn-danger")
    assert element.aria_label == "Delete all records"
    assert element.disabled is True
    assert element.text == "Delete All Records"


def test_extract_link_information() -> None:
    dom = """
    <a id="admin" class="admin-only" href="/admin">
        Admin Dashboard
    </a>
    """

    elements = extract_dom_elements(dom)

    assert len(elements) == 1

    element = elements[0]

    assert element.tag == "a"
    assert element.element_id == "admin"
    assert element.href == "/admin"
    assert element.classes == ("admin-only",)
    assert element.text == "Admin Dashboard"


def test_detect_hidden_element() -> None:
    dom = """
    <button style="display: none">Hidden Admin</button>
    """

    elements = extract_dom_elements(dom)

    assert len(elements) == 1
    assert elements[0].hidden is True
