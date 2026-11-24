"""The parser hyphenates a multi-word subject; the matcher must not care.

Arm A4 of the paper patched this in-process and it was never shipped, so every
multi-word policy subject was unmatchable on every application.
"""

from __future__ import annotations

from apps.agent.contracts import ExpectationNode, ExpectationSet, SemanticUIMap, UIElement
from apps.agent.negation.audit import audit


def _map(name: str) -> SemanticUIMap:
    return SemanticUIMap(
        state_id="s1",
        url="http://app.test/owners/find",
        role="guest",
        summary="",
        elements=(UIElement(role="link", name=name, selector="a#x"),),
        capabilities=(),
    )


def _forbid(subject: str) -> ExpectationSet:
    return ExpectationSet(
        forbidden=(
            ExpectationNode(
                expectation_id="e1",
                polarity="must_not_exist",
                subject=subject,
                roles=("guest",),
            ),
        ),
        required=(),
    )


def test_hyphenated_subject_matches_a_spaced_accessible_name() -> None:
    violations = audit(_map("Add Owner"), _forbid("add-owner"))
    assert len(violations) == 1


def test_spaced_subject_matches_a_spaced_accessible_name() -> None:
    violations = audit(_map("Add Owner"), _forbid("add owner"))
    assert len(violations) == 1


def test_case_and_separator_run_are_ignored() -> None:
    violations = audit(_map("PHP  Info"), _forbid("php-info"))
    assert len(violations) == 1


def test_a_genuinely_different_subject_still_does_not_match() -> None:
    violations = audit(_map("Add Owner"), _forbid("delete-owner"))
    assert violations == ()
