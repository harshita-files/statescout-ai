"""A capability finding must cite the control that carries it.

The evidence search mapped element *tags* back to capabilities independently of
perception, so a paragraph whose text contains "administrator" could be offered
as the evidence for an exposed admin capability. On DVWA a correct finding about
a reCAPTCHA admin link cited a paragraph about XAMPP instead.
"""

from __future__ import annotations

from apps.agent.contracts import ExpectationNode, ExpectationSet, SemanticUIMap, UIElement
from apps.agent.negation.audit import audit


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


def _map(*elements: UIElement) -> SemanticUIMap:
    return SemanticUIMap(
        state_id="s1",
        url="http://app.test/",
        role="guest",
        summary="",
        elements=elements,
        capabilities=("admin-access",),
    )


def test_evidence_is_the_control_not_the_prose() -> None:
    prose = UIElement(role="paragraph", name="XAMPP is an Apache distribution", tags=("admin",))
    control = UIElement(role="link", name="Admin Panel", tags=("admin",), selector="a#admin")
    violations = audit(_map(prose, control), _forbid("admin-access"))

    assert len(violations) == 1
    assert violations[0].evidence.text == "Admin Panel"
    assert violations[0].evidence.selector == "a#admin"


def test_a_violation_is_still_raised_when_only_prose_carries_the_tag() -> None:
    """The capability is real; we just cannot point at a control for it."""
    prose = UIElement(role="paragraph", name="reset the administrator password", tags=("admin",))
    violations = audit(_map(prose), _forbid("admin-access"))

    assert len(violations) == 1
    assert violations[0].evidence.selector is None
