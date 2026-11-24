"""Regression tests from the Juice Shop / DVWA independent-subject run.

A consent *banner* is a wall. A stylesheet whose filename happens to contain
"cookieconsent" is not, and must not abort the crawl.
"""

from __future__ import annotations

from apps.agent.contracts import CaptureBundle
from apps.agent.crawler.safety import SafetyPolicy


def _policy() -> SafetyPolicy:
    return SafetyPolicy(respect_robots=False, requests_per_second=100)


def test_consent_library_asset_url_is_not_a_wall() -> None:
    """Observed on OWASP Juice Shop v19.0.0: the only match was a CDN CSS filename."""
    bundle = CaptureBundle(
        url="http://shop.test/",
        title="Shop",
        dom=(
            "<html><head>"
            '<link rel="stylesheet" type="text/css" '
            'href="//cdnjs.cloudflare.com/ajax/libs/cookieconsent2/3.1.0/cookieconsent.min.css">'
            '<script src="//cdnjs.cloudflare.com/ajax/libs/cookieconsent2/3.1.0/'
            'cookieconsent.min.js"></script>'
            '</head><body><h1>Shop</h1><a href="/basket">Basket</a></body></html>'
        ),
        ax_tree={"nodes": []},
    )

    assert _policy().detect_wall(bundle) is None


def test_visible_consent_banner_is_still_a_wall() -> None:
    bundle = CaptureBundle(
        url="http://shop.test/",
        title="Shop",
        dom=(
            '<html><body><div class="cookie-banner">'
            "<p>We use cookies to improve your experience.</p>"
            "<button>Accept</button></div></body></html>"
        ),
        ax_tree={"nodes": []},
    )

    assert _policy().detect_wall(bundle) == "consent_wall"


def test_real_login_page_is_still_a_wall() -> None:
    """DVWA's login page: this one must keep being detected."""
    bundle = CaptureBundle(
        url="http://dvwa.test/login.php",
        title="DVWA Login",
        dom=(
            "<html><body><form><p>Please log in</p>"
            '<input type="text" name="username">'
            '<input type="password" name="password">'
            "</form></body></html>"
        ),
        ax_tree={"nodes": []},
    )

    assert _policy().detect_wall(bundle) == "login_wall"
