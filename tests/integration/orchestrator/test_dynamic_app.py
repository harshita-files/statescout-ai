"""The orchestrator against a seeded SIMULATED dynamic web app (not a real browser).

These tests pin what the experiment in `docs/report/experiments/dynamic_app_results.md`
actually found, including the parts that did not go the hoped way:

* `suggest_masks` output alone (config B) does not change coverage on this app;
  attribute churn needs extra, hand-written patterns (config B+).
* The flaky violation is labelled `stable` inside a crawl, because its presence is part
  of the state identity; only an independent calibration sample labels it `flaky`.

Everything runs on `FakePerception` / `FakeGraph` and a simulated crawler.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from collections import Counter
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from apps.agent.contracts import CrawlerPort
from apps.agent.orchestrator.stochastic.insights import violation_confidences

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "orchestrator" / "dynamic-app"


def _load(name: str, filename: str) -> ModuleType:
    key = f"dynamic_app_test_{name}"
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, FIXTURE / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


exp: Any = _load("experiment", "experiment.py")
sim: Any = exp.sim
EXPECTED: dict[str, Any] = json.loads((FIXTURE / "expected.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def calibration() -> Any:
    return exp.calibrate()


@pytest.fixture(scope="module")
def runs(calibration: Any) -> dict[str, Any]:
    result: dict[str, Any] = exp.run_all(calibration)
    return result


# ---------------------------------------------------------------------------
# The simulated app itself
# ---------------------------------------------------------------------------


def _act(app: Any, bundle: Any, name: str) -> Any:
    action = next(a for a in app.enumerate_actions(bundle) if a.label.endswith(f'"{name}"'))
    return app.act(action)


def test_app_implements_the_crawler_port() -> None:
    assert isinstance(sim.DynamicApp(), CrawlerPort)


def test_expected_json_matches_the_app() -> None:
    assert tuple(s["name"] for s in EXPECTED["logical_states"]) == sim.LOGICAL_STATES
    assert EXPECTED["logical_state_count"] == len(sim.LOGICAL_STATES) == 9
    assert EXPECTED["seed"] == sim.SEED == 7
    assert set(EXPECTED["endpoints"]["by_action"]) == set(sim.action_labels().values())


def test_same_seed_is_reproducible_and_other_seeds_differ() -> None:
    def dom(seed: int) -> str:
        return str(sim.DynamicApp(seed=seed).open(sim.SEED_URL).dom)

    assert dom(7) == dom(7)
    assert dom(7) != dom(8)


def test_every_visit_to_the_same_page_renders_differently() -> None:
    app = sim.DynamicApp()
    doms = [app.open(sim.SEED_URL).dom for _ in range(30)]
    assert len(set(doms)) == len(doms)
    assert len(set(re.findall(r"Sponsored: [A-Za-z ]+", " ".join(doms)))) > 1  # rotating ad
    assert len(set(re.findall(r"\d+ people online", " ".join(doms)))) > 5  # visitor counter
    assert len(set(re.findall(r"Updated \d+ minutes ago", " ".join(doms)))) > 5  # relative time
    assert len(set(re.findall(r'class="([^"]+)"', " ".join(doms)))) > 30  # random classes


def test_feed_items_differ_per_visit_and_load_more_appends() -> None:
    app = sim.DynamicApp()
    first = app.open(f"{sim.BASE_URL}/feed")
    second = app.open(f"{sim.BASE_URL}/feed")
    items = re.compile(r"<li>([^<]+)</li>")
    assert items.findall(first.dom) != items.findall(second.dom)
    more = _act(app, second, "Load more")
    assert more.url == second.url
    assert len(items.findall(more.dom)) == len(items.findall(second.dom)) + sim.FEED_BATCH
    assert items.findall(more.dom)[: sim.FEED_BATCH] == items.findall(second.dom)


def test_modal_opens_at_an_unchanged_url_and_closes_back() -> None:
    app = sim.DynamicApp()
    home = app.open(sim.SEED_URL)
    modal = _act(app, home, "Help")
    assert modal.url == home.url
    assert 'role="dialog"' in modal.dom and 'role="dialog"' not in home.dom
    assert sim.logical_of(modal) == "home-modal"
    assert [a.label for a in app.enumerate_actions(modal)] == ['click "Close"']
    assert sim.logical_of(_act(app, modal, "Close")) == "home"


def test_planted_violation_rates() -> None:
    app = sim.DynamicApp()
    flaky = sum(
        'data-tag="admin-link"' in app.open(f"{sim.BASE_URL}/products").dom for _ in range(500)
    )
    assert 0.3 < flaky / 500 < 0.5  # planted at 0.4
    assert app.products_renders == 500
    assert app.products_renders_with_flaky == flaky
    assert all(
        'data-tag="debug-panel"' in app.open(f"{sim.BASE_URL}/settings").dom for _ in range(50)
    )
    assert all('data-tag="debug-panel"' not in app.open(sim.SEED_URL).dom for _ in range(20))


def test_stochastic_outcomes_follow_their_planted_probabilities() -> None:
    app = sim.DynamicApp()
    for _ in range(2000):
        _act(app, app.open(f"{sim.BASE_URL}/products"), "Add to cart")
        _act(app, app.open(f"{sim.BASE_URL}/cart"), "Checkout")
    counts = Counter(app.outcomes)
    add = counts[("Add to cart", "cart")] + counts[("Add to cart", "sold-out")]
    checkout = counts[("Checkout", "thanks")] + counts[("Checkout", "error")]
    assert add == checkout == 2000
    assert 0.66 < counts[("Add to cart", "cart")] / add < 0.74  # planted 0.70
    assert 0.03 < counts[("Checkout", "error")] / checkout < 0.07  # planted 0.05


def test_normalise_endpoint() -> None:
    assert sim.normalise_endpoint("GET /api/orders/48213?expand=items") == "GET /api/orders/{id}"
    assert sim.normalise_endpoint("POST /api/cart") == "POST /api/cart"
    assert sim.normalise_endpoint("GET /api/feed?cursor=2") == "GET /api/feed"


def test_every_control_makes_the_expected_normalised_calls() -> None:
    by_action = EXPECTED["endpoints"]["by_action"]
    conditional = EXPECTED["endpoints"]["conditional"]
    app = sim.DynamicApp()
    checked = set()
    for logical in sim.LOGICAL_STATES:
        for control in sim.CONTROLS[logical]:
            for _ in range(8):  # several draws, so Checkout is seen on both paths
                bundle = app.open(f"{sim.BASE_URL}{sim._URLS[logical]}")
                if logical == "home-modal":
                    bundle = _act(app, bundle, "Help")
                app.drain()
                _act(app, bundle, control.name)
                got = Counter(app.drain())
                want = Counter(by_action[control.name])
                optional = set(conditional.get(control.name, {}))
                for endpoint in optional:
                    if endpoint not in got:
                        del want[endpoint]
                assert got == want, (control.name, got, want)
                checked.add(control.name)
    assert checked == set(by_action)


# ---------------------------------------------------------------------------
# The experiment
# ---------------------------------------------------------------------------


def test_mask_approval_is_explicit_and_safe(calibration: Any) -> None:
    reviewed = calibration.reviewed
    assert reviewed
    assert any(not r.approved for r in reviewed)
    assert any(r.approved for r in reviewed)
    protected = [c.name for cs in sim.CONTROLS.values() for c in cs] + ["Admin console"]
    for pattern in calibration.approved_patterns:
        compiled = re.compile(pattern)
        assert not any(compiled.search(term) for term in protected), pattern
    rejected_protected = [r for r in reviewed if "protected" in r.reason]
    assert any("Admin console" in r.reason for r in rejected_protected)


def test_calibration_labels_the_flaky_element_flaky_and_the_stable_one_stable(
    calibration: Any,
) -> None:
    labels = {k: v[4] for k, v in exp.calibration_confidence(calibration).items()}
    assert labels == {"admin-link@products": "flaky", "debug-panel@settings": "stable"}


def test_nothing_unplanted_is_reported(runs: dict[str, Any]) -> None:
    for name, run in runs.items():
        assert run.unplanted() == [], name


def test_no_config_exceeds_max_states_and_the_cap_is_enforced_under_churn(
    runs: dict[str, Any],
) -> None:
    for name, run in runs.items():
        assert run.result.states <= exp.MAX_STATES, name
    capped = exp.run_config("capped", None, max_states=2, depth_limit=5)
    assert capped.result.termination_reason == "max_states"
    assert capped.result.states == 2


def test_b_stays_within_the_state_cap(runs: dict[str, Any]) -> None:
    for name in ("A", "B0", "B", "B+"):
        assert runs[name].result.states <= exp.MAX_STATES


def test_suggest_masks_alone_recovers_coverage_over_the_baseline(runs: dict[str, Any]) -> None:
    """B uses only reviewer-approved `suggest_masks` output (no hand-written pattern).

    Control B0 (flag on, no patterns) must stay equal to A, so the gain comes from the
    masks and not from the flag. Simulated app; see the report for caveats.
    """
    a, b0, b = runs["A"], runs["B0"], runs["B"]
    assert set(b0.states_per_logical()) == set(a.states_per_logical())
    assert len(b.states_per_logical()) > len(a.states_per_logical())
    assert b.replay_diverged() < a.replay_diverged()
    assert b.found()["V-STABLE"] is True
    assert a.found()["V-STABLE"] is False


def test_baseline_loses_coverage_through_replay_divergence(runs: dict[str, Any]) -> None:
    a = runs["A"]
    assert a.replay_diverged() > 0
    assert len(a.states_per_logical()) < EXPECTED["logical_state_count"]
    assert a.found()["V-STABLE"] is False


def test_approved_plus_handwritten_masks_recover_coverage_and_the_stable_violation(
    runs: dict[str, Any],
) -> None:
    a, bp = runs["A"], runs["B+"]
    assert len(bp.states_per_logical()) > len(a.states_per_logical())
    assert bp.replay_diverged() < a.replay_diverged()
    assert bp.found()["V-STABLE"] is True
    assert set(bp.states_per_logical()) >= {"home", "home-modal", "products", "settings"}


def test_infinite_scroll_is_bounded_by_depth_not_by_equivalence(runs: dict[str, Any]) -> None:
    feed_states = runs["B+"].states_per_logical().get("feed", 0)
    assert 1 < feed_states <= exp.DEPTH_LIMIT + 1


def test_cycles_and_back_edges_survive_in_probabilistic_mode(runs: dict[str, Any]) -> None:
    bp = runs["B+"]
    assert bp.graph.back_edges()
    assert len(bp.graph.edges) == bp.result.edges
    # NFR-05: one claim per (state, action) pair, nothing re-fired by the visited set.
    assert len(bp.graph.visited) == bp.result.visited_pairs


def test_transition_counts_are_proper_distributions(runs: dict[str, Any]) -> None:
    stats = runs["B+"].stats
    assert stats is not None
    assert stats.transitions
    for key, probs in stats.transition_probabilities.items():
        assert sum(probs.values()) == pytest.approx(1.0)
        counts = stats.transitions[key]
        replay = stats.replay_transitions.get(key, {})
        assert all(replay.get(t, 0) <= n for t, n in counts.items())


def test_flaky_element_shows_up_as_a_state_split(runs: dict[str, Any]) -> None:
    run = runs["B+"]
    assert len([s for s in run.tap.ids.values() if s == "products"]) >= 2
    splits = [
        probs
        for key, probs in run.stats.transition_probabilities.items()
        if json.loads(key)[1]
        == next(c for c in sim.CONTROLS["home"] if c.name == "Products").action_id
        and len(probs) > 1
    ]
    assert splits


def test_endpoint_accounting_matches_ground_truth(runs: dict[str, Any]) -> None:
    run = runs["B+"]
    compared, bad = exp.endpoint_mismatches(run)
    assert compared > 0
    assert bad == []
    stats = run.stats
    assert stats is not None
    load_more = next(c for c in sim.CONTROLS["feed"] if c.name == "Load more").action_id
    feed_counts = [
        per["GET /api/feed"]
        for key, per in stats.action_endpoints.items()
        if json.loads(key)[1] == load_more
    ]
    assert feed_counts
    assert all(c["calls"] == 2 * c["actions"] == 2 * c["clicks"] for c in feed_counts)
    # Every endpoint total is the sum of its per-pair counts.
    for endpoint, totals in stats.endpoints.items():
        assert totals["calls"] == sum(
            per[endpoint]["calls"] for per in stats.action_endpoints.values() if endpoint in per
        )
    assert "GET /api/orders/{id}" in stats.endpoints  # templated, no raw ids


def test_no_raw_ids_or_queries_reach_the_statistics(runs: dict[str, Any]) -> None:
    for run in (runs["B"], runs["B+"]):
        for endpoint in run.stats.endpoints:
            assert "?" not in endpoint and not re.search(r"\d", endpoint), endpoint


def test_violation_confidence_flaky_is_not_detected_inside_a_crawl(runs: dict[str, Any]) -> None:
    """The hoped-for 'flaky label' does NOT happen in-crawl: presence is part of identity."""
    run = runs["B+"]
    stats = run.stats
    assert stats is not None
    states = {v.violation_id: v.state_id for v in run.result.violations}
    conf = violation_confidences(stats, states)
    by_expectation = {v.expectation_id: conf[v.violation_id] for v in run.result.violations}
    assert set(by_expectation) == {"e-admin-link", "e-debug-panel"}
    # ... but the split halves reproducibility, so the runner's product ranks it lower.
    flaky_id = next(
        v.violation_id for v in run.result.violations if v.expectation_id == "e-admin-link"
    )
    stable_id = next(
        v.violation_id for v in run.result.violations if v.expectation_id == "e-debug-panel"
    )
    assert stats.reproducibility[flaky_id] < stats.reproducibility[stable_id]


# ---------------------------------------------------------------------------
# Flag off: baseline behaviour is unchanged
# ---------------------------------------------------------------------------


def test_flag_off_collects_no_dynamic_statistics(runs: dict[str, Any]) -> None:
    assert runs["A"].result.dynamic is None
    assert runs["A"].config.probabilistic_states is False


def test_flag_off_ignores_volatility_patterns(calibration: Any, runs: dict[str, Any]) -> None:
    patterned = exp.run_config(
        "A-patterns", None, volatility_patterns=calibration.approved_patterns
    )
    assert patterned.config.probabilistic_states is False
    assert patterned.result.order == runs["A"].result.order
    assert patterned.result.states == runs["A"].result.states
    assert patterned.result.dynamic is None


def test_flag_off_matches_the_plain_python_reference_and_is_deterministic(
    runs: dict[str, Any],
) -> None:
    ref = exp.run_config("ref", None, use_reference=True)
    again = exp.run_config("again", None)
    a = runs["A"].result
    for other in (ref.result, again.result):
        assert other.order == a.order
        assert (other.states, other.edges, other.visited_pairs) == (
            a.states,
            a.edges,
            a.visited_pairs,
        )
        assert (other.replays, other.replay_steps) == (a.replays, a.replay_steps)
        assert other.termination_reason == a.termination_reason
        assert [v.violation_id for v in other.violations] == [v.violation_id for v in a.violations]
        assert [(s.from_state_id, s.action_id, s.reason) for s in other.skipped] == [
            (s.from_state_id, s.action_id, s.reason) for s in a.skipped
        ]


def test_b_plus_is_not_an_outlier_across_seeds(calibration: Any) -> None:
    rows, _ = exp.sweep(calibration.approved_patterns)
    by = {(r.seed, r.config): r for r in rows}
    for seed in exp.SWEEP_SEEDS:
        assert by[(seed, "B+")].max_states_hit is False
        assert by[(seed, "B+")].logical >= by[(seed, "A")].logical
        assert by[(seed, "B+")].stable_found is True
        assert by[(seed, "A")].stable_found is False
