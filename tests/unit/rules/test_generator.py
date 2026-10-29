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
