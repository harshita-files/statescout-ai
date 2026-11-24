"""A consent banner over a working page is a notice, not a wall.

OWASP Juice Shop renders a floating `cc-window cc-type-info` banner above a fully
usable page: seven actions were enumerable underneath it, yet the crawl stopped
at one state. A consent *interstitial*, where accepting is the only thing on
offer, must still stop the crawl.
"""

from __future__ import annotations

from typing import Any

from apps.agent.contracts import CaptureBundle
from apps.agent.crawler.safety import SafetyPolicy

_BANNER = (
    '<div role="dialog" aria-label="cookieconsent" class="cc-window cc-floating">'
    '<span class="cc-message">This website uses cookies.</span>'
    '<a class="cc-btn">Got it!</a></div>'
)


def _ax(*names: str) -> dict[str, Any]:
    return {"nodes": [{"role": {"value": "link"}, "name": {"value": n}} for n in names]}


def _policy() -> SafetyPolicy:
    return SafetyPolicy(respect_robots=False, requests_per_second=100)


def test_banner_over_a_usable_page_is_not_a_wall() -> None:
    bundle = CaptureBundle(
        url="http://shop.test/",
        title="Shop",
        dom=f"<body><nav><a href='/basket'>Basket</a></nav>{_BANNER}</body>",
        ax_tree=_ax("Basket", "Account", "Search", "Deals", "Contact", "About"),
    )
    assert _policy().detect_wall(bundle) is None


def test_consent_interstitial_with_nothing_else_is_still_a_wall() -> None:
    bundle = CaptureBundle(
        url="http://gate.test/",
        title="Before you continue",
        dom=f"<body>{_BANNER}</body>",
        ax_tree=_ax("Accept all", "Reject all"),
    )
    assert _policy().detect_wall(bundle) == "consent_wall"


def test_a_login_wall_is_unaffected_by_page_richness() -> None:
    bundle = CaptureBundle(
        url="http://app.test/login",
        title="Sign in",
        dom="<body><p>Please log in</p><input type='password' name='p'></body>",
        ax_tree=_ax("Home", "Help", "Register", "Terms", "Privacy", "Contact"),
    )
    assert _policy().detect_wall(bundle) == "login_wall"
