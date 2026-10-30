"""Weak models copy prompt placeholders and echo topic hints; neither may become a rule."""

import json

from apps.agent.rules.generator import generate_rules
from apps.agent.rules.parser import parse_rules
from tests.unit.rules.test_parser import FakeLLM

PLACEHOLDER = "short-hyphenated-ui-element-or-capability"


def _clause(subject: str, kind: str = "presence") -> str:
    return json.dumps(
        {"kind": kind, "subject": subject, "roles": ["guest"], "severity": "low", "params": {}}
    )


def test_parser_rejects_a_subject_unrelated_to_the_rule_text() -> None:
    """A 3B model answered 'login exposure' with the schema's placeholder subject."""
    llm = FakeLLM([_clause(PLACEHOLDER)] * 2)
    exp, _ = parse_rules(["login exposure"], llm, "guest")
    subjects = {n.subject for n in (*exp.required, *exp.forbidden)}
    assert PLACEHOLDER not in subjects


def test_parser_still_accepts_a_related_subject() -> None:
    llm = FakeLLM([_clause("admin-link", "absence")])
    exp, _ = parse_rules(["Guests must not see the admin link"], llm, "guest")
    assert llm.calls == 1
    assert {n.subject for n in exp.forbidden} == {"admin-link"}


def _rules_reply(*texts: str) -> str:
    return json.dumps(
        {"rules": [{"text": t, "kind": "content", "severity": "low", "params": {}} for t in texts]}
    )


def test_generator_rejects_topic_labels_that_are_not_policy_sentences() -> None:
    topics = ["login exposure", "missing consent banner", "negative or invalid numbers"]
    llm = FakeLLM([_rules_reply(*topics)] * 2)
    got = generate_rules(["Prices and a login form"], llm)
    assert got and all(r.text not in topics for r in got)  # fell back to sentence templates
    assert all(len(r.text.split()) >= 3 for r in got)


def test_generator_keeps_real_sentences_and_drops_only_the_labels() -> None:
    good = "Guests must not see the admin link on any page"
    llm = FakeLLM([_rules_reply("login exposure", good)])
    got = generate_rules(["Prices"], llm)
    assert [r.text for r in got] == [good]


def test_parser_accepts_a_canonical_synonym_subject() -> None:
    """'sign out' shares no word with 'logout', but logout is a canonical capability."""
    llm = FakeLLM([_clause("logout")])
    exp, _ = parse_rules(["Users must always be able to sign out"], llm, "user")
    assert llm.calls == 1 and {n.subject for n in exp.required} == {"logout"}


def _kinded(text: str, kind: str = "presence") -> str:
    return json.dumps({"rules": [{"text": text, "kind": kind, "severity": "low", "params": {}}]})


def test_generator_rederives_kind_from_text_instead_of_trusting_the_model() -> None:
    """A 3B model labelled everything 'presence', which turns checks into 'must exist' clauses."""
    from apps.agent.negation.checks import TRACKER_MARKUP

    texts = [
        "The site must show a cookie or privacy consent banner",
        "Interactive controls must have an accessible label",
        "Pages must not show broken-link or error content",
    ]
    llm = FakeLLM(
        [
            json.dumps(
                {
                    "rules": [
                        {"text": t, "kind": "presence", "severity": "low", "params": {}}
                        for t in texts
                    ]
                }
            )
        ]
    )
    by_text = {r.text: r for r in generate_rules(["page"], llm)}
    consent = by_text[texts[0]]
    assert consent.kind == "content" and consent.params.get("when_markup") == TRACKER_MARKUP
    assert by_text[texts[1]].kind == "a11y"
    assert by_text[texts[2]].kind == "content"


def test_generator_keeps_the_models_kind_when_text_is_not_a_known_check() -> None:
    sentence = "Guests must not see the admin link on any page"
    got = generate_rules(["page"], FakeLLM([_kinded(sentence, "absence")]))
    assert got[0].kind == "absence"
