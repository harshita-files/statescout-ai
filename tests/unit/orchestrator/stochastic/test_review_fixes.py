"""Regression tests for the independent review of the stochastic modules."""

from __future__ import annotations

import re

from apps.agent.orchestrator.stochastic.endpoints import normalise_endpoint
from apps.agent.orchestrator.stochastic.insights import suggest_masks
from apps.agent.orchestrator.stochastic.volatility import (
    VolatilityEstimator,
    split_regions,
)

AX: dict[str, object] = {"role": "WebArea", "children": []}


def _page(body: str) -> str:
    return f"<html><body>{body}</body></html>"


# --- volatility: rates and masking scope -----------------------------------


def test_change_rate_never_exceeds_one() -> None:
    est = VolatilityEstimator()
    est.observe(_page("<ul></ul>"), AX)
    est.observe(_page("<ul><li>a</li><li>b</li><li>c</li></ul>"), AX)
    est.observe(_page("<ul><li>a</li><li>b</li><li>c</li></ul>"), AX)
    est.observe(_page("<ul></ul>"), AX)
    for path in split_regions(_page("<ul><li>a</li></ul>"), AX):
        assert est.change_rate(path) <= 1.0


def test_a_toast_under_body_does_not_mask_the_whole_page() -> None:
    est = VolatilityEstimator()
    plain = _page("<h1>Orders</h1>")
    for i in range(9):
        toast = "<div role='alert'>Saved</div><div role='alert'>Sent</div>" if i == 4 else ""
        est.observe(_page(toast + "<h1>Orders</h1>"), AX)

    safe = est.skeleton_id(plain, AX)
    hostile = est.skeleton_id(_page("<h1>ADMIN PANEL delete all users</h1>"), AX)

    assert safe != hostile


# --- volatility: state-bearing attributes must distinguish states ----------


def test_hidden_and_visible_dialog_are_different_regions() -> None:
    hidden = _page("<dialog hidden>Confirm</dialog>")
    shown = _page("<dialog>Confirm</dialog>")
    assert split_regions(hidden, AX) != split_regions(shown, AX)


def test_checked_and_unchecked_checkbox_differ() -> None:
    on = _page("<input type='checkbox' checked>")
    off = _page("<input type='checkbox'>")
    assert split_regions(on, AX) != split_regions(off, AX)


def test_disabled_and_enabled_button_differ() -> None:
    assert split_regions(_page("<button disabled>Go</button>"), AX) != split_regions(
        _page("<button>Go</button>"), AX
    )


def test_aria_expanded_differs() -> None:
    a = _page("<button aria-expanded='true'>Menu</button>")
    b = _page("<button aria-expanded='false'>Menu</button>")
    assert split_regions(a, AX) != split_regions(b, AX)


def test_ax_checked_and_expanded_properties_differ() -> None:
    on: dict[str, object] = {"role": "checkbox", "name": "Admin", "checked": True}
    off: dict[str, object] = {"role": "checkbox", "name": "Admin", "checked": False}
    assert split_regions(_page(""), on) != split_regions(_page(""), off)


# --- suggest_masks: patterns must be safe and must hit the raw markup ------


def _raw(i: int, count: int = 100) -> str:
    return _page(
        f"<div class='ad-{i:03d}xq'>sponsor {i}</div>"
        f"<main><h1>Orders</h1><p>Visitors online: {count + i}</p><b>{100 + i}</b></main>"
    )


def test_no_bare_numeric_pattern_is_ever_suggested() -> None:
    captures = [(_raw(i), AX) for i in range(6)]
    for s in suggest_masks(captures):
        assert s.pattern not in {r"\d+", r"\d", ""}
        literal = re.sub(r"\\d\+|\\.", "", s.pattern)
        assert len(literal) >= 2


def test_every_suggestion_matches_raw_markup() -> None:
    captures = [(_raw(i), AX) for i in range(6)]
    suggestions = suggest_masks(captures)
    assert suggestions
    for s in suggestions:
        regex = re.compile(s.pattern)
        assert any(regex.search(dom) for dom, _ in captures), s.pattern


def test_random_class_names_get_an_attribute_pattern() -> None:
    def page(i: int) -> str:
        suffix = ["a1b2c3", "z9y8x7", "k4m5n6", "q1w2e3", "r7t8y9", "u3i4o5"][i]
        return _page(f"<div class='box-{suffix}'>Static</div><div class='card-{suffix}'>Hi</div>")

    captures = [(page(i), AX) for i in range(6)]
    patterns = [s.pattern for s in suggest_masks(captures)]

    assert patterns
    assert any(re.search(p, page(0)) for p in patterns)
    assert not any(re.search(p, "<h1>Static</h1>") for p in patterns)


# --- endpoints: no credential survives, output matches dynamic's grammar ---

_RUNNER_GRAMMAR = re.compile(r"(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS) /[A-Za-z0-9_/{}:.-]*")


def test_encoded_query_pair_does_not_leak() -> None:
    out = normalise_endpoint("GET", "https://x.test/a?tok%3DSECRET")
    assert "SECRET" not in out


def test_path_parameters_are_dropped() -> None:
    out = normalise_endpoint("GET", "https://x.test/x;jsessionid=A1B2C3D4E5F6")
    assert "A1B2" not in out
    assert "jsessionid" not in out


def test_data_urls_do_not_carry_payload() -> None:
    out = normalise_endpoint("GET", "data:text/plain;base64,SGVsbG9TZWNyZXQ=")
    assert "SGVsbG9" not in out


def test_long_lowercase_token_segment_is_a_placeholder() -> None:
    out = normalise_endpoint("GET", "/reset/abcdefghijklmnopqrstuvwxyz")
    assert out == "GET /reset/{token}"


def test_mid_length_mixed_token_is_a_placeholder() -> None:
    out = normalise_endpoint("GET", "/s/aB3dE5fG7hJ9kL1mN")
    assert out == "GET /s/{token}"


def test_output_always_fits_the_runner_grammar() -> None:
    for url in [
        "/api/users/42?x=1&y=2",
        "https://h.test/a/b?tok%3DSECRET",
        "/x;jsessionid=AB12",
        "/files/report.pdf",
        "/a%20b/c",
    ]:
        assert _RUNNER_GRAMMAR.fullmatch(normalise_endpoint("get", url)), url
