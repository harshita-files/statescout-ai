import json

from apps.agent.contracts import SemanticUIMap, UIElement
from apps.agent.rules.generator import generate_rules


class FakeLLM:
    def __init__(self, reply: str) -> None:
        self.reply = reply

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        images: tuple[bytes, ...] = (),
        json_mode: bool = False,
    ) -> str:
        return self.reply


def _page() -> SemanticUIMap:
    return SemanticUIMap(
        "s1",
        "http://x/",
        "guest",
        summary="Login page. AAPL $190.10",
        elements=(UIElement("button", ""),),
    )


def test_heuristic_rules_generated() -> None:
    rules = generate_rules([_page()], None)
    kinds = {r.kind for r in rules}
    assert {"absence", "consistency", "numeric", "a11y", "content"} <= kinds
    assert all(r.source == "generated" for r in rules)
    assert len({r.rule_id for r in rules}) == len(rules)


def test_no_prices_no_consistency() -> None:
    rules = generate_rules(["plain page"], None)
    assert "consistency" not in {r.kind for r in rules}


def test_llm_rules() -> None:
    reply = json.dumps(
        {
            "rules": [
                {
                    "text": "No negative stock",
                    "kind": "numeric",
                    "severity": "high",
                    "params": {"min": 0},
                }
            ]
        }
    )
    rules = generate_rules([_page()], FakeLLM(reply))
    assert [r.text for r in rules] == ["No negative stock"] and rules[0].source == "generated"


def test_llm_garbage_falls_back() -> None:
    assert len(generate_rules([_page()], FakeLLM("nope"))) >= 5


def _kinds(summary: str) -> dict[str, str]:
    page = SemanticUIMap("s1", "http://x/", "guest", summary=summary)
    return {r.kind: r.text for r in generate_rules([page], None)}


def test_a_nan_undefined_rule_is_always_proposed() -> None:
    rules = [
        r
        for r in generate_rules([_page()], None)
        if r.kind == "content" and r.params.get("forbid_pattern")
    ]
    assert any("NaN" in r.text and "NaN" in r.params["forbid_pattern"] for r in rules)


def test_a_form_validation_rule_is_proposed_when_the_page_has_order_or_quantity_inputs() -> None:
    got = _kinds("Trade. Quantity [1] Place order. Cash available $10,000.00")
    assert "validation" in got and "rejected" in got["validation"]


def test_no_form_validation_rule_for_a_page_without_quantity_inputs() -> None:
    assert "validation" not in _kinds("Welcome. Read our terms.")


def test_a_ticker_price_consistency_rule_is_proposed_for_pages_that_list_symbols_with_prices() -> (
    None
):
    got = [
        r
        for r in generate_rules(
            [
                SemanticUIMap(
                    "s", "http://x/", "guest", summary="AAPL Apple Inc. 190.10 +1.00 +0.5%"
                )
            ],
            None,
        )
        if r.kind == "consistency" and r.params.get("mode") == "ticker"
    ]
    assert len(got) == 1 and "ticker" in got[0].text.lower() and got[0].source == "generated"


def test_no_ticker_rule_without_symbols_and_prices() -> None:
    page = SemanticUIMap("s", "http://x/", "guest", summary="Welcome to our blog. 3 new posts.")
    assert not [r for r in generate_rules([page], None) if r.params.get("mode") == "ticker"]
