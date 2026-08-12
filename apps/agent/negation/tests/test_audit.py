from apps.agent.contracts import (
    ExpectationNode,
    ExpectationSet,
    SemanticUIMap,
    UIElement,
)
from apps.agent.negation.audit import audit


def make_map(
    *,
    elements=(),
    capabilities=(),
) -> SemanticUIMap:
    return SemanticUIMap(
        state_id="state-1",
        url="http://test/",
        role="guest",
        elements=elements,
        capabilities=capabilities,
    )


def test_forbidden_present_is_violation() -> None:
    semantic_map = make_map(
        elements=(
            UIElement(
                role="button",
                name="Delete All Records",
                tags=("delete",),
                selector="#delete",
            ),
        ),
        capabilities=("delete-user",),
    )

    policy = ExpectationSet(
        forbidden=(
            ExpectationNode(
                expectation_id="e-delete",
                polarity="must_not_exist",
                subject="delete-user",
                roles=("guest",),
            ),
        ),
    )

    violations = audit(semantic_map, policy)

    assert len(violations) == 1
    assert violations[0].clause_type == "forbidden_present"
    assert violations[0].expectation_id == "e-delete"
    assert violations[0].evidence.selector == "#delete"


def test_required_absent_is_violation() -> None:
    semantic_map = make_map()

    policy = ExpectationSet(
        required=(
            ExpectationNode(
                expectation_id="e-logout",
                polarity="must_exist",
                subject="logout",
                roles=("guest",),
            ),
        ),
    )

    violations = audit(semantic_map, policy)

    assert len(violations) == 1
    assert violations[0].clause_type == "required_absent"


def test_present_required_element_is_clean() -> None:
    semantic_map = make_map(
        elements=(
            UIElement(
                role="button",
                name="Log out",
                tags=("logout",),
                selector="#logout",
            ),
        ),
        capabilities=("logout",),
    )

    policy = ExpectationSet(
        required=(
            ExpectationNode(
                expectation_id="e-logout",
                polarity="must_exist",
                subject="logout",
            ),
        ),
    )

    assert audit(semantic_map, policy) == ()


def test_role_restricted_policy_does_not_apply() -> None:
    semantic_map = make_map(
        capabilities=("delete-user",),
    )

    policy = ExpectationSet(
        forbidden=(
            ExpectationNode(
                expectation_id="e-delete",
                polarity="must_not_exist",
                subject="delete-user",
                roles=("admin",),
            ),
        ),
    )

    assert audit(semantic_map, policy) == ()
