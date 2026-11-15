# ruff: noqa: E501
import json

from apps.agent.audit_models import Rule
from apps.agent.rules.parser import parse_rules


class FakeLLM:
    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.calls = 0

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        images: tuple[bytes, ...] = (),
        json_mode: bool = False,
    ) -> str:
        self.calls += 1
        return self.replies.pop(0)


def test_heuristic_role_forbidden() -> None:
    exp, rules = parse_rules(["Guests must not see the admin link"], None, "guest")
    n = exp.forbidden[0]
    assert (n.subject, n.roles, n.polarity) == ("admin-access", ("guest",), "must_not_exist")
    assert rules[0].kind == "absence"


def test_heuristic_never_show() -> None:
    exp, _ = parse_rules(["The app must never show debug panel."], None, "guest")
    assert exp.forbidden[0].subject == "debug-access"
    assert exp.forbidden[0].roles == ()


def test_heuristic_required() -> None:
    exp, rules = parse_rules(["The page must have a logout button"], None, "user")
    assert exp.required[0].subject == "logout"
    assert rules[0].kind == "presence"


def test_admin_role_must_not_see() -> None:
    exp, _ = parse_rules(["admin must not see debug panel"], None, "admin")
    assert exp.forbidden[0].roles == ("admin",)


def test_non_presence_kinds() -> None:
    _, rules = parse_rules(
        ["Quantity must never be negative", "Price must be the same across views"], None, "guest"
    )
    assert [r.kind for r in rules] == ["numeric", "consistency"]


def test_rule_objects_preserved_ids() -> None:
    exp, rules = parse_rules([Rule("r9", "Users must not see delete button")], None, "user")
    assert exp.forbidden[0].expectation_id == "r9" and rules[0].rule_id == "r9"


def test_llm_path_valid() -> None:
    reply = json.dumps(
        {
            "kind": "absence",
            "subject": "Admin Link",
            "roles": ["guest"],
            "severity": "critical",
            "params": {},
        }
    )
    llm = FakeLLM([reply])
    exp, rules = parse_rules(["Guests must not see the Admin Link"], llm, "guest")
    assert exp.forbidden[0].subject == "admin-access"
    assert rules[0].severity == "critical" and llm.calls == 1


def test_llm_retry_then_success() -> None:
    good = json.dumps({"kind": "presence", "subject": "logout", "roles": []})
    llm = FakeLLM(["not json", good])
    exp, _ = parse_rules(["x"], llm, "user")
    assert llm.calls == 2 and exp.required[0].subject == "logout"


def test_llm_failure_falls_back() -> None:
    llm = FakeLLM(["bad", '{"kind":"nope"}'])
    exp, _ = parse_rules(["Guests must not see the admin link"], llm, "guest")
    assert exp.forbidden[0].subject == "admin-access"


def test_parser_tags_kinds_and_params_for_check_rules() -> None:
    texts = [
        "The sign of the percentage change must match the sign of the absolute price change.",
        "The portfolio total value must equal the sum of the individual holdings values.",
        "The price shown for a ticker on the order ticket must equal the price on the Markets page.",
        "The page must never display 'NaN', 'undefined' or 'null' to the user.",
        "Every link in the page must lead to an existing page, not a 404 error.",
        "A site that sets tracking cookies must first show a cookie consent banner.",
        "Every icon-only button must have an accessible name.",
        "Guests must never see the Admin navigation item or any admin-only controls such as 'Delete user'.",
    ]
    exp, rules = parse_rules(texts, None)
    got = [(r.kind, r.params.get("mode") or r.params.get("subject")) for r in rules]
    assert got[:3] == [("consistency", "sign"), ("consistency", "sum"), ("consistency", "ticker")]
    assert rules[3].kind == "content" and "NaN" in rules[3].params["forbid_pattern"]
    assert rules[4].kind == "content" and "404" in rules[4].params["forbid_pattern"]
    assert rules[5].kind == "content" and "consent" in rules[5].params["require_pattern"]
    assert rules[6].kind == "a11y"
    assert rules[7].kind == "absence" and rules[7].params["subject"] == "admin-access"
    assert exp.forbidden[0].subject == "admin-access"
