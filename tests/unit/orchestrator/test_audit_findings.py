"""run_audit: readable titles, rule-kind checks, de-duplication and grouping."""

from apps.agent.audit_models import AuditConfig, Rule
from apps.agent.contracts import Evidence, ExpectationSet, Violation
from apps.agent.orchestrator.audit_runner import (
    _drop_duplicate_rules,
    _merge_findings,
    run_audit,
)
from apps.agent.orchestrator.deps import Ports
from apps.agent.orchestrator.dynamic import DynamicStats
from apps.agent.orchestrator.fakes import DEFAULT_POLICY, FakeCrawler, FakeGraph, FakePerception
from apps.agent.rules import parse_rules

LOGIN = "http://fake.test/login"


def _viol(vid: str, rule: str, sel: str = "#admin") -> Violation:
    return Violation(
        vid,
        "s1",
        rule,
        "forbidden_present",
        "high",
        "Forbidden subject present.",
        Evidence(selector=sel, text="Admin"),
    )


def test_user_rule_wins_over_generated_on_same_element_and_title_is_rule_text() -> None:
    rules = [
        Rule("gen-2", "Guests must not see admin controls", "generated", "critical"),
        Rule("user-1", "Guests must not see the admin link", "user", "high"),
    ]
    stats = DynamicStats()
    got = _merge_findings(
        [_viol("v-gen", "gen-2"), _viol("v-user", "user-1")],
        stats,
        rules,
        ExpectationSet(),
        {"s1": "http://x/"},
    )
    assert [f.rule_id for f in got] == ["user-1"]
    assert got[0].title == "Guests must not see the admin link"
    assert got[0].group_key and "Seen at http://x/" in got[0].rationale


def test_group_key_is_stable_across_states() -> None:
    rules = [Rule("r", "t", "user")]
    a = _viol("v1", "r")
    b = Violation(
        "v2", "s2", "r", "forbidden_present", "high", "x", Evidence(selector="#admin", text="Admin")
    )
    got = _merge_findings([a, b], DynamicStats(), rules, ExpectationSet(), {})
    assert len(got) == 2 and got[0].group_key == got[1].group_key


def test_generated_rule_duplicating_user_clause_is_dropped() -> None:
    _, rules = parse_rules(
        [
            Rule("u1", "Guests must not see the admin link", "user"),
            Rule("g1", "Guests must not see admin controls", "generated"),
            Rule("g2", "Numbers must never be negative", "generated"),
        ],
        None,
    )
    kept, dropped = _drop_duplicate_rules(rules)
    assert dropped == ["g1"] and [r.rule_id for r in kept] == ["u1", "g2"]


def test_run_audit_uses_rule_text_as_title() -> None:
    _, rules = parse_rules([Rule("u1", "A guest must never see the admin link.", "user")], None)
    cfg = AuditConfig(
        url=LOGIN,
        rules=tuple(rules),
        depth_limit=20,
        max_states=40,
        volatility_patterns=(r'data-nonce="[^"]*"',),
    )
    report = run_audit(cfg, Ports(FakeCrawler(), FakePerception(), FakeGraph()), DEFAULT_POLICY)
    assert report.findings
    assert all(not f.title.startswith("forbidden_present") for f in report.findings)
    assert report.stats["finding_groups"]
