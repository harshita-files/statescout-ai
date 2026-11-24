"""Distinct unlabelled elements on one page must be reported distinctly.

Accessibility violations come from AX nodes that often have no DOM selector, so
their evidence signature fell back to the element role. Every unlabelled image on
a page then shared the signature "img" and collapsed into one finding. On the W3C
Before-and-After Demo the inaccessible home page has 38 such violations and the
accessible one has 8, yet the report showed 2 and 3 respectively, inverting the
comparison.
"""

from __future__ import annotations

from apps.agent.audit_models import Rule
from apps.agent.contracts import Evidence, ExpectationSet, Violation
from apps.agent.orchestrator.audit_runner import _merge_findings
from apps.agent.orchestrator.dynamic import DynamicStats

RULE = [Rule("p5", "Every icon-only control must have an accessible name.", "user", "high", "a11y")]


def _v(index: int, role: str = "img") -> Violation:
    """An a11y violation: no selector, evidence text is only the role."""
    return Violation(
        violation_id=f"e{index}",
        state_id="state-1",
        expectation_id="p5",
        clause_type="forbidden_present",
        severity="high",
        rationale=f"Visible {role} has no accessible name.",
        evidence=Evidence(selector=None, text=role),
    )


def _run(violations: list[Violation]) -> list[str]:
    found = _merge_findings(violations, DynamicStats(), RULE, ExpectationSet((), ()), {})
    return [f.finding_id for f in found]


def test_many_unlabelled_images_on_one_page_are_all_reported() -> None:
    assert len(_run([_v(i) for i in range(37)])) == 37


def test_an_identical_repeat_of_one_element_is_still_collapsed() -> None:
    assert len(_run([_v(4), _v(4)])) == 1


def test_different_roles_remain_distinct() -> None:
    assert len(_run([_v(1, "img"), _v(2, "link"), _v(3, "input")])) == 3
