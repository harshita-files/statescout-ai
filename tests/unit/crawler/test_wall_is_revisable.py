"""A wall recorded from one capture must not outlive the evidence for it.

An Angular application captured before it has rendered its own controls looks
like a consent gate: the banner markup is there and almost nothing else is. The
seed is captured several times (the volatility mask samples it), so a single
early capture permanently blocked OWASP Juice Shop even though every later
capture showed seven usable controls.
"""

from __future__ import annotations

from typing import Any

from apps.agent.contracts import CaptureBundle
from apps.agent.crawler.playwright_crawler import PlaywrightCrawler
from apps.agent.crawler.safety import SafetyPolicy

_BANNER = (
    '<div role="dialog" aria-label="cookieconsent" class="cc-window">'
    "<span>This website uses cookies.</span></div>"
)


def _ax(n: int) -> dict[str, Any]:
    return {"nodes": [{"role": {"value": "button"}, "name": {"value": f"c{i}"}} for i in range(n)]}


def _crawler(policy: SafetyPolicy) -> PlaywrightCrawler:
    c = PlaywrightCrawler.__new__(PlaywrightCrawler)
    c._safety = policy
    c._walled = frozenset()
    c._usable = frozenset()
    return c


def _bundle(actionable: int) -> CaptureBundle:
    return CaptureBundle(
        url="http://app.test/", title="App", dom=f"<body>{_BANNER}</body>", ax_tree=_ax(actionable)
    )


def test_a_later_usable_capture_clears_an_earlier_wall() -> None:
    policy = SafetyPolicy(respect_robots=False, requests_per_second=100)
    crawler = _crawler(policy)

    crawler._screen(_bundle(0))  # pre-render: banner and nothing else
    assert "http://app.test/" in crawler._walled

    crawler._screen(_bundle(7))  # rendered: seven controls underneath the banner
    assert "http://app.test/" not in crawler._walled
    assert [n.reason for n in policy.blocked_notes()] == []


def test_a_wall_that_stays_a_wall_is_kept() -> None:
    policy = SafetyPolicy(respect_robots=False, requests_per_second=100)
    crawler = _crawler(policy)

    crawler._screen(_bundle(0))
    crawler._screen(_bundle(1))
    assert "http://app.test/" in crawler._walled
    assert [n.reason for n in policy.blocked_notes()] == ["consent_wall"]


def test_a_page_already_seen_usable_is_not_rewalled_by_a_sparser_capture() -> None:
    """Juice Shop: nine captures showed 6-7 controls, the last two showed 4."""
    policy = SafetyPolicy(respect_robots=False, requests_per_second=100)
    crawler = _crawler(policy)

    crawler._screen(_bundle(7))  # rendered
    crawler._screen(_bundle(4))  # a sparser capture of the same page

    assert "http://app.test/" not in crawler._walled
    assert [n.reason for n in policy.blocked_notes()] == []


def test_a_login_wall_appearing_later_is_still_recorded() -> None:
    """Usability evidence only excuses a consent element, never a login gate."""
    policy = SafetyPolicy(respect_robots=False, requests_per_second=100)
    crawler = _crawler(policy)

    crawler._screen(_bundle(7))
    crawler._screen(
        CaptureBundle(
            url="http://app.test/",
            title="Sign in",
            dom="<body><p>Please log in</p><input type='password' name='p'></body>",
            ax_tree=_ax(2),
        )
    )
    assert "http://app.test/" in crawler._walled
    assert [n.reason for n in policy.blocked_notes()] == ["login_wall"]
