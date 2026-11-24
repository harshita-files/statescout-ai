"""Two different clauses violated on one page must both be reported.

Findings were deduplicated by (state_id, evidence selector) alone. On DVWA every
navigation link has selector "a", so six genuine violations on a page collapsed
to one and the other five vanished with no record.
"""

from __future__ import annotations

from apps.agent.audit_models import Rule
from apps.agent.contracts import Evidence, ExpectationSet, Violation
from apps.agent.orchestrator.audit_runner import _merge_findings
from apps.agent.orchestrator.dynamic import DynamicStats


def _violation(expectation_id: str, name: str, selector: str = "a") -> Violation:
    return Violation(
        violation_id=f"v-{expectation_id}-{name}",
        state_id="state-1",
        expectation_id=expectation_id,
        clause_type="forbidden_present",
        severity="high",
        rationale=f"Forbidden subject '{expectation_id}' is present.",
        evidence=Evidence(selector=selector, text=name),
    )


def _rules() -> list[Rule]:
    return [
        Rule("d1", "A guest must never see PHP Info.", "user", "high"),
        Rule("d2", "A guest must never see DVWA Security.", "user", "high"),
    ]


def test_two_clauses_sharing_a_selector_are_both_reported() -> None:
    violations = [_violation("d1", "PHP Info"), _violation("d2", "DVWA Security")]
    found = _merge_findings(violations, DynamicStats(), _rules(), ExpectationSet((), ()), {})
    assert {f.rule_id for f in found} == {"d1", "d2"}


def test_the_same_clause_on_the_same_element_is_still_deduplicated() -> None:
    violations = [_violation("d1", "PHP Info"), _violation("d1", "PHP Info")]
    found = _merge_findings(violations, DynamicStats(), _rules(), ExpectationSet((), ()), {})
    assert len(found) == 1


def test_a_generated_rule_duplicating_a_user_rule_is_still_suppressed() -> None:
    rules = [
        Rule("d1", "A guest must never see PHP Info.", "user", "high"),
        Rule("g1", "Auto: PHP Info is exposed.", "generated", "high"),
    ]
    violations = [_violation("g1", "PHP Info"), _violation("d1", "PHP Info")]
    found = _merge_findings(violations, DynamicStats(), rules, ExpectationSet((), ()), {})
    assert [f.rule_id for f in found] == ["d1"]
