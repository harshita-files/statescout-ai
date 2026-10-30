"""The generated consent rule fires only on evidence of tracking, not on every page."""

from __future__ import annotations

import pytest

from apps.agent.audit_models import Rule
from apps.agent.contracts import SemanticUIMap
from apps.agent.negation.checks import TRACKER_MARKUP, check_rules
from apps.agent.rules.generator import generate_rules


def smap(sid: str = "a") -> SemanticUIMap:
    return SemanticUIMap(sid, f"http://t/{sid}", "guest", summary="Welcome")


CONDITIONAL = Rule(
    "c1",
    "The site must show a cookie or privacy consent banner",
    "generated",
    "low",
    "content",
    {"require_pattern": r"cookie|consent", "when_markup": TRACKER_MARKUP},
)
UNCONDITIONAL = Rule(
    "c2", "Must show a cookie banner", "user", "low", "content", {"require_pattern": "cookie"}
)


def run(rule: Rule, markup: str, text: str = "Welcome") -> int:
    maps = [smap()]
    return len(check_rules([rule], maps, {"a": text}, {"a": markup}))


def test_static_page_without_trackers_is_not_flagged() -> None:
    assert run(CONDITIONAL, "<html><body><p>This domain is for examples.</p></body></html>") == 0


@pytest.mark.parametrize(
    "markup",
    [
        "<script src='https://www.googletagmanager.com/gtm.js?id=G-1'></script>",
        "<script>gtag('config','G-1')</script><script src='/gtag/js?id=G-1'></script>",
        "<img src='/track.gif' width=1 height=1>",
        "<img src='https://x.test/pixel.png?uid=1'>",
        "<script>document.cookie = 'uid=1; path=/'</script>",
        "<script async src='https://connect.facebook.net/en_US/fbevents.js'></script>",
    ],
)
def test_tracking_markup_without_a_consent_notice_is_flagged(markup: str) -> None:
    assert run(CONDITIONAL, f"<html><body>{markup}</body></html>") == 1


def test_tracking_with_a_consent_notice_is_fine() -> None:
    page = "<img src='/track.gif'>"
    assert run(CONDITIONAL, page, text="We use cookies. Accept") == 0


def test_finding_names_the_tracker_as_evidence() -> None:
    vs = check_rules([CONDITIONAL], [smap()], {"a": "Welcome"}, {"a": "<img src='/track.gif'>"})
    assert "track.gif" in (vs[0].evidence.text or "")
    assert "tracking" in vs[0].rationale.lower()


def test_user_written_rule_stays_unconditional() -> None:
    assert run(UNCONDITIONAL, "<html><body><p>plain</p></body></html>") == 1


def test_generator_makes_the_consent_rule_conditional() -> None:
    page = SemanticUIMap("a", "http://t/", "guest", summary="Welcome to a plain page")
    consent = [r for r in generate_rules([page], None) if "consent" in r.text.lower()]
    assert consent and consent[0].params.get("when_markup") == TRACKER_MARKUP
