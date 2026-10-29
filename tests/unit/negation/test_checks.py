from apps.agent.audit_models import Rule
from apps.agent.contracts import ExpectationSet, SemanticUIMap, UIElement
from apps.agent.negation.audit import audit_rules
from apps.agent.negation.checks import check_rules


def m(sid: str, summary: str = "", elements: tuple[UIElement, ...] = ()) -> SemanticUIMap:
    return SemanticUIMap(sid, f"http://t/{sid}", "guest", summary=summary, elements=elements)


def test_consistency_ticker_mismatch() -> None:
    rule = Rule("c1", "t", kind="consistency", params={"subject": "AAPL"})
    vs = check_rules([rule], [m("a", "AAPL $190.10"), m("b", "AAPL $191.00")])
    assert len(vs) == 1 and vs[0].state_id == "b"
    assert "190.1" in vs[0].rationale and vs[0].evidence.text


def test_consistency_generic_and_ok() -> None:
    rule = Rule("c1", "t", kind="consistency")
    assert check_rules([rule], [m("a", "Total: $5.00"), m("b", "Total: $5.00")]) == ()
    assert len(check_rules([rule], [m("a", "Total: $5.00"), m("b", "Total: $6.00")])) == 1


def test_numeric_negative() -> None:
    rule = Rule("n1", "t", kind="numeric", params={"min": 0})
    vs = check_rules([rule], [m("a", "Quantity: -3 in cart, date 2024-05-01, price $4")])
    assert len(vs) == 1 and "-3" in (vs[0].evidence.text or "")


def test_numeric_texts_and_max() -> None:
    rule = Rule("n1", "t", kind="numeric", params={"pattern": r"qty=(\d+)", "max": 10})
    vs = check_rules([rule], [m("a")], {"a": "qty=99 qty=2"})
    assert len(vs) == 1


def test_content_forbid_and_require() -> None:
    forbid = Rule("f", "t", kind="content", params={"forbid_pattern": "404"})
    req = Rule("r", "t", kind="content", params={"require_pattern": "cookie"})
    vs = check_rules([forbid, req], [m("a", "Error 404"), m("b", "hello")])
    assert {(v.expectation_id, v.clause_type) for v in vs} == {
        ("f", "forbidden_present"),
        ("r", "required_absent"),
    }
    assert check_rules([req], [m("a", "We use Cookies")]) == ()


def test_a11y_unlabeled() -> None:
    rule = Rule("a", "t", kind="a11y")
    vs = check_rules(
        [rule],
        [m("a", elements=(UIElement("button", "", selector="#x"), UIElement("button", "OK")))],
    )
    assert len(vs) == 1 and vs[0].evidence.selector == "#x"


def test_audit_rules_combines() -> None:
    from apps.agent.contracts import ExpectationNode

    exp = ExpectationSet(forbidden=(ExpectationNode("e1", "must_not_exist", "admin"),))
    maps = [m("a", elements=(UIElement("link", "Admin", tags=("admin",)),))]
    vs = audit_rules(maps, exp, [Rule("n", "t", kind="numeric")], None)
    assert [v.expectation_id for v in vs] == ["e1"]
