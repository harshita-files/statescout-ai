"""A clause nothing could satisfy must say so instead of staying silent.

A forbidden clause that never fires reads exactly like a clause that was
satisfied, so a tester whose subject does not exist in the application's
vocabulary sees a clean report and believes the page was checked. Writing
"a PHP Info link" rather than "PHP Info" was enough to produce this.
"""

from __future__ import annotations

from apps.agent.contracts import ExpectationNode, ExpectationSet, SemanticUIMap, UIElement
from apps.agent.orchestrator.audit_runner import unmatchable_clauses


def _node(subject: str, eid: str) -> ExpectationNode:
    return ExpectationNode(expectation_id=eid, polarity="must_not_exist", subject=subject)


def _maps() -> dict[str, SemanticUIMap]:
    return {
        "s1": SemanticUIMap(
            state_id="s1",
            url="http://app.test/",
            role="guest",
            elements=(UIElement(role="link", name="PHP Info"),),
            capabilities=("admin-access",),
        )
    }


def test_a_subject_present_in_the_vocabulary_is_not_reported() -> None:
    exp = ExpectationSet(forbidden=(_node("php-info", "d1"),), required=())
    assert unmatchable_clauses(exp, _maps()) == ()


def test_a_capability_subject_is_not_reported() -> None:
    exp = ExpectationSet(forbidden=(_node("admin-access", "d2"),), required=())
    assert unmatchable_clauses(exp, _maps()) == ()


def test_a_subject_absent_from_the_vocabulary_is_reported() -> None:
    exp = ExpectationSet(forbidden=(_node("php-info-link", "d3"),), required=())
    assert unmatchable_clauses(exp, _maps()) == ("d3",)


def test_nothing_is_reported_when_no_state_was_observed() -> None:
    exp = ExpectationSet(forbidden=(_node("php-info-link", "d4"),), required=())
    assert unmatchable_clauses(exp, {}) == ()
