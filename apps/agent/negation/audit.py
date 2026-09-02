"""Deterministic negation-aware policy evaluation.

FR-18:
    S ∩ forbidden

FR-19:
    required \\ S

The engine operates over both semantic element tags and capabilities.
"""

from __future__ import annotations

import re

from apps.agent.contracts import (
    Evidence,
    ExpectationNode,
    ExpectationSet,
    SemanticUIMap,
    Violation,
)


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def _applies(expectation: ExpectationNode, role: str) -> bool:
    """An empty role list means the clause applies to every role."""
    return not expectation.roles or role in expectation.roles


def _matches_subject(
    semantic_map: SemanticUIMap,
    subject: str,
) -> tuple[bool, Evidence]:
    """Find the best evidence for a policy subject."""

    wanted = _normalize(subject)

    # Capabilities are stronger evidence than fuzzy text.
    for capability in semantic_map.capabilities:
        if _normalize(capability) == wanted:
            for element in semantic_map.elements:
                if capability in _element_capabilities(element):
                    return True, Evidence(
                        selector=element.selector,
                        text=element.name,
                    )

            return True, Evidence(text=capability)

    for element in semantic_map.elements:
        candidates = (*element.tags, element.name)

        if any(_normalize(value) == wanted for value in candidates):
            return True, Evidence(
                selector=element.selector,
                text=element.name,
            )

    # Deliberately don't do substring matching here. The semantic-map builder
    # is where deterministic interpretation belongs; the policy evaluator
    # should remain predictable.
    return False, Evidence()


def _element_capabilities(element) -> tuple[str, ...]:
    """Map the standard Track C tags back to their capabilities."""
    mapping = {
        "admin": "admin-access",
        "delete": "delete-user",
        "debug": "debug-access",
        "export": "export-data",
        "logout": "logout",
        "login": "login",
    }

    return tuple(capability for tag in element.tags if (capability := mapping.get(tag)) is not None)


def _severity_for(expectation: ExpectationNode) -> str:
    """Baseline severity until policy parsing carries explicit severity.

    ExpectationNode currently has no severity field, so this is deliberately
    centralized rather than scattered through the engine.
    """
    if expectation.polarity == "must_not_exist":
        return "high"

    return "medium"


def _violation(
    semantic_map: SemanticUIMap,
    expectation: ExpectationNode,
    clause_type: str,
    rationale: str,
    evidence: Evidence,
) -> Violation:
    violation_id = f"v-{semantic_map.state_id}-{expectation.expectation_id}"

    return Violation(
        violation_id=violation_id,
        state_id=semantic_map.state_id,
        expectation_id=expectation.expectation_id,
        clause_type=clause_type,
        severity=_severity_for(expectation),
        rationale=rationale,
        evidence=evidence,
    )


def audit(
    semantic_map: SemanticUIMap,
    expectations: ExpectationSet,
) -> tuple[Violation, ...]:
    """Evaluate forbidden and required policy clauses."""

    violations: list[Violation] = []

    # FR-18: S ∩ forbidden
    for expectation in expectations.forbidden:
        if not _applies(expectation, semantic_map.role):
            continue

        present, evidence = _matches_subject(
            semantic_map,
            expectation.subject,
        )

        if present:
            violations.append(
                _violation(
                    semantic_map,
                    expectation,
                    "forbidden_present",
                    (
                        f"Forbidden subject '{expectation.subject}' is "
                        f"present for role '{semantic_map.role}'."
                    ),
                    evidence,
                )
            )

    # FR-19: required \ S
    for expectation in expectations.required:
        if not _applies(expectation, semantic_map.role):
            continue

        present, _ = _matches_subject(
            semantic_map,
            expectation.subject,
        )

        if not present:
            violations.append(
                _violation(
                    semantic_map,
                    expectation,
                    "required_absent",
                    (
                        f"Required subject '{expectation.subject}' is "
                        f"absent for role '{semantic_map.role}'."
                    ),
                    Evidence(),
                )
            )

    return tuple(violations)
