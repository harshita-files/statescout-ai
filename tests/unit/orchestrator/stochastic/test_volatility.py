"""Tests for region signatures and the VolatilityEstimator."""

from __future__ import annotations

import pytest

from apps.agent.orchestrator.stochastic.volatility import (
    VolatilityEstimator,
    content_id,
    merge_audit,
    split_regions,
)

AX: dict[str, object] = {
    "role": "WebArea",
    "name": "Home",
    "children": [
        {"role": "navigation", "name": "Main", "children": [{"role": "link", "name": "Home"}]},
        {"role": "main", "name": "", "children": [{"role": "heading", "name": "Welcome"}]},
    ],
}


def page(
    ad: str = "Buy A",
    counter: str = "100 viewers",
    stamp: str = "3 min ago",
    items: int = 2,
    cls: str = "css-1a2b3c",
) -> str:
    feed = "".join(f"<li>post {i}</li>" for i in range(items))
    return (
        f'<html><body><header><nav><a href="/">Home</a></nav></header>'
        f'<main class="{cls}"><h1>Welcome</h1><p>{stamp}</p>'
        f"<span>{counter}</span><ul>{feed}</ul></main>"
        f"<aside><div>{ad}</div></aside><footer>fixed</footer></body></html>"
    )


def test_split_regions_is_path_keyed_and_deterministic() -> None:
    a = split_regions(page(), AX)
    assert a == split_regions(page(), AX)
    assert any(k.startswith("dom:body/header") for k in a)
    assert any(k.startswith("ax:") for k in a)


def test_split_regions_localises_a_change() -> None:
    a = split_regions(page(ad="A"), AX)
    b = split_regions(page(ad="B"), AX)
    changed = {k for k in a.keys() | b.keys() if a.get(k) != b.get(k)}
    assert changed
    assert all("aside" in k for k in changed)


def test_randomised_class_names_do_not_change_regions() -> None:
    assert split_regions(page(cls="css-1a2b3c"), AX) == split_regions(page(cls="css-9z8y7x"), AX)


def test_relative_timestamps_are_normalised() -> None:
    a = split_regions(page(stamp="3 min ago"), AX)
    assert a == split_regions(page(stamp="17 hours ago"), AX)


def test_content_id_is_exact() -> None:
    assert content_id(page(), AX) == content_id(page(), AX)
    assert content_id(page(ad="A"), AX) != content_id(page(ad="B"), AX)
    assert content_id(page(cls="css-1a2b3c"), AX) != content_id(page(cls="css-9z8y7x"), AX)


def test_rotating_ad_and_live_counter_masked_after_learning() -> None:
    est = VolatilityEstimator()
    for i in range(4):
        est.observe(page(ad=f"Ad {i}", counter=f"{100 + i} viewers"), AX)
    a = page(ad="Ad 90", counter="555 viewers")
    b = page(ad="Ad 91", counter="556 viewers")
    assert content_id(a, AX) != content_id(b, AX)
    assert est.skeleton_id(a, AX) == est.skeleton_id(b, AX)


def test_appended_feed_items_masked() -> None:
    est = VolatilityEstimator()
    for n in (2, 3, 4, 5):
        est.observe(page(items=n), AX)
    assert est.skeleton_id(page(items=9), AX) == est.skeleton_id(page(items=10), AX)


def test_stable_changes_still_distinguish_states() -> None:
    est = VolatilityEstimator()
    for i in range(4):
        est.observe(page(ad=f"Ad {i}"), AX)
    other = page().replace("fixed", "different footer")
    assert est.skeleton_id(other, AX) != est.skeleton_id(page(), AX)


def test_no_observations_masks_nothing() -> None:
    est = VolatilityEstimator()
    assert est.volatile_paths() == frozenset()
    assert est.skeleton_id(page(ad="A"), AX) != est.skeleton_id(page(ad="B"), AX)


def test_threshold_and_min_observations() -> None:
    est = VolatilityEstimator(threshold=0.9, min_observations=3)
    est.observe(page(ad="A"), AX)
    est.observe(page(ad="B"), AX)
    assert est.volatile_paths() == frozenset()  # fewer than 3 observations
    est.observe(page(ad="C"), AX)
    assert est.volatile_paths()
    with pytest.raises(ValueError):
        VolatilityEstimator(threshold=0.0)
    with pytest.raises(ValueError):
        VolatilityEstimator(min_observations=1)


def test_occasional_change_below_threshold_not_masked() -> None:
    est = VolatilityEstimator(threshold=0.5)
    for ad in ("A", "A", "A", "A", "A", "B"):
        est.observe(page(ad=ad), AX)
    assert est.volatile_paths() == frozenset()


def test_merge_audit_reports_collapsed_content_ids() -> None:
    est = VolatilityEstimator()
    for i in range(3):
        est.observe(page(ad=f"Ad {i}"), AX)
    captures = [
        (page(ad="X"), AX),
        (page(ad="Y"), AX),
        (page(ad="X"), AX),
        (page().replace("fixed", "other"), AX),
    ]
    reports = merge_audit(est, captures)
    assert len(reports) == 1
    r = reports[0]
    assert len(r.content_ids) == 2
    assert r.skeleton_id == est.skeleton_id(page(ad="X"), AX)
    assert r.differing_paths
    assert all("aside" in p for p in r.differing_paths)


def test_merge_audit_empty_when_no_collapse() -> None:
    est = VolatilityEstimator()
    assert merge_audit(est, [(page(ad="X"), AX), (page(ad="Y"), AX)]) == ()
