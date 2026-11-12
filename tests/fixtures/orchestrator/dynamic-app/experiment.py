# ruff: noqa: E501  (generated report prose is written as long f-string lines)
"""Crawl the simulated dynamic app under baseline and probabilistic configurations.

Run it for real (writes `docs/report/experiments/dynamic_app_results.md`)::

    uv run python tests/fixtures/orchestrator/dynamic-app/experiment.py

Configurations (identical seed, depth limit and `max_states` cap):

* A  - baseline: `probabilistic_states=False` (graph fingerprint, no statistics).
* B0 - `probabilistic_states=True`, no masks (control: the flag alone).
* B  - `probabilistic_states=True`, `volatility_patterns` = the HUMAN-APPROVED subset
       of `insights.suggest_masks` over repeated captures of each logical state.
* B+ - B plus two patterns written by the reviewer by hand (supplementary; written with
       knowledge of how the simulator formats class names and timestamps, so B+ is an oracle
       upper bound, not a result a user would get without that knowledge).

Everything here runs on a SIMULATED app, not a real browser.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

from apps.agent.contracts import (
    Action,
    CaptureBundle,
    ExpectationSet,
    Violation,
)
from apps.agent.orchestrator import explore as reference
from apps.agent.orchestrator import graph_runner
from apps.agent.orchestrator.config import OrchestratorConfig
from apps.agent.orchestrator.deps import Ports
from apps.agent.orchestrator.dynamic import DynamicStats, identity
from apps.agent.orchestrator.fakes import FakeGraph, FakePerception
from apps.agent.orchestrator.state import ExplorationResult
from apps.agent.orchestrator.stochastic.confidence import ConfidenceLabel, observation_confidence
from apps.agent.orchestrator.stochastic.insights import (
    MaskSuggestion,
    suggest_masks,
    violation_confidences,
)

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
RESULTS_PATH = REPO_ROOT / "docs" / "report" / "experiments" / "dynamic_app_results.md"
EXPECTED_PATH = HERE / "expected.json"

DEPTH_LIMIT = 5
MAX_STATES = 30
CALIBRATION_CAPTURES = 40

#: Hand-written by the reviewer (NOT produced by suggest_masks). Documented in the report.
HUMAN_PATTERNS: tuple[str, ...] = (
    r'(?<=class=")[a-z]+-[a-z0-9]{6}(?=")',
    r"Updated\ \d+\ minutes\ ago",
)


def _load(name: str, filename: str) -> ModuleType:
    key = f"dynamic_app_sim_{name}"
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, HERE / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


sim: Any = _load("app", "app.py")


def load_expected() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))
    return loaded


# ---------------------------------------------------------------------------
# Calibration and the simulated human-approval step
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Reviewed:
    suggestion: MaskSuggestion
    logical: str
    approved: bool
    reason: str


@dataclass(slots=True)
class Calibration:
    reviewed: list[Reviewed] = field(default_factory=list)
    raw_doms: list[str] = field(default_factory=list)
    flaky_presence: dict[str, tuple[int, int]] = field(default_factory=dict)

    @property
    def approved_patterns(self) -> tuple[str, ...]:
        return tuple(sorted({r.suggestion.pattern for r in self.reviewed if r.approved}))


def _protected_terms() -> tuple[str, ...]:
    names = {c.name for controls in sim.CONTROLS.values() for c in controls}
    return (*sorted(names), "Admin console", "Debug panel", "admin-link", "debug-panel")


def review(
    suggestion: MaskSuggestion, raw_doms: list[str], protected: tuple[str, ...]
) -> tuple[bool, str]:
    """The reviewer's rules, applied mechanically so the run is reproducible.

    Reject a suggestion if (1) it never matches the raw markup (it cannot help), or
    (2) its samples or its match could touch a control label or a policy-relevant
    string (masking those could hide a reachable action or a violation).
    """
    try:
        compiled = re.compile(suggestion.pattern)
    except re.error as exc:
        return False, f"invalid regex: {exc}"
    if not any(compiled.search(dom) for dom in raw_doms):
        return False, "dead pattern: does not occur in the raw markup"
    for term in protected:
        if any(term.lower() in sample.lower() for sample in suggestion.samples):
            return False, f"samples contain protected text {term!r}"
        if compiled.search(term):
            return False, f"pattern matches protected text {term!r}"
    return True, "volatile content only"


def calibrate() -> Calibration:
    """Capture each logical state repeatedly, ask `suggest_masks`, simulate approval."""
    app = sim.DynamicApp(seed=sim.SEED)
    out = Calibration()
    protected = _protected_terms()
    samples = {name: app.sample(name, CALIBRATION_CAPTURES) for name in sim.LOGICAL_STATES}
    out.raw_doms = [dom for per in samples.values() for dom, _ in per]
    for logical, captures in samples.items():
        for suggestion in suggest_masks(captures):
            ok, reason = review(suggestion, out.raw_doms, protected)
            out.reviewed.append(Reviewed(suggestion, logical, ok, reason))
        present = sum('data-tag="admin-link"' in dom for dom, _ in captures)
        if logical == "products":
            out.flaky_presence["admin-link@products"] = (present, len(captures))
        if logical == "settings":
            out.flaky_presence["debug-panel@settings"] = (
                sum('data-tag="debug-panel"' in dom for dom, _ in captures),
                len(captures),
            )
    return out


# ---------------------------------------------------------------------------
# Running one configuration
# ---------------------------------------------------------------------------


def make_config(patterns: tuple[str, ...] | None, **overrides: Any) -> OrchestratorConfig:
    settings: dict[str, Any] = {
        "role": "guest",
        "depth_limit": DEPTH_LIMIT,
        "max_states": MAX_STATES,
        "perception_rate_per_min": 0,
    }
    settings.update(overrides)
    if patterns is not None:
        settings["probabilistic_states"] = True
        settings["volatility_patterns"] = patterns
    return OrchestratorConfig(_env_file=None, **settings)  # type: ignore[call-arg]


class Tap:
    """Pass-through crawler that records the logical state behind every state id.

    Ground truth only: ids are computed exactly as the runner computes them (graph
    fingerprint, or `dynamic.identity` in probabilistic mode), so replay-landed states
    that the runner never persists can still be labelled in reports.
    """

    def __init__(self, app: Any, config: OrchestratorConfig, graph: FakeGraph) -> None:
        self.app = app
        self._config = config
        self._graph = graph
        self.ids: dict[str, str] = {}

    @property
    def last_capture_ready(self) -> bool | None:
        ready: bool | None = self.app.last_capture_ready
        return ready

    def _note(self, bundle: CaptureBundle) -> CaptureBundle:
        state_id = (
            identity(bundle, self._config)
            if self._config.probabilistic_states
            else self._graph.fingerprint(bundle)
        )
        self.ids[state_id] = sim.logical_of(bundle)
        return bundle

    def open(self, url: str) -> CaptureBundle:
        return self._note(self.app.open(url))

    def act(self, action: Action) -> CaptureBundle:
        return self._note(self.app.act(action))

    def enumerate_actions(self, bundle: CaptureBundle) -> tuple[Action, ...]:
        actions: tuple[Action, ...] = self.app.enumerate_actions(bundle)
        return actions

    def close(self) -> None:
        self.app.close()

    def drain(self) -> tuple[str, ...]:
        calls: tuple[str, ...] = self.app.drain()
        return calls


@dataclass(slots=True)
class Run:
    name: str
    config: OrchestratorConfig
    result: ExplorationResult
    graph: FakeGraph
    app: Any
    tap: Tap

    @property
    def stats(self) -> DynamicStats | None:
        return self.result.dynamic

    def logical(self, state_id: str) -> str:
        return self.tap.ids.get(state_id, "?")

    def states_per_logical(self) -> dict[str, int]:
        counts = Counter(self.logical(sid) for sid in self.graph.states)
        return {name: counts[name] for name in sim.LOGICAL_STATES if counts[name]}

    def skip_categories(self) -> dict[str, int]:
        cats: Counter[str] = Counter()
        for skip in self.result.skipped:
            cats[re.split(r"[:(]", skip.reason, maxsplit=1)[0].strip()] += 1
        return dict(sorted(cats.items()))

    def found(self) -> dict[str, bool]:
        """Planted violation id -> found at least once."""
        planted = load_expected()["planted_violations"]
        keys = {(self.logical(v.state_id), v.expectation_id) for v in self.result.violations}
        return {p["id"]: (p["logical_state"], p["expectation_id"]) in keys for p in planted}

    def unplanted(self) -> list[Violation]:
        planted = {
            (p["logical_state"], p["expectation_id"]) for p in load_expected()["planted_violations"]
        }
        return [
            v
            for v in self.result.violations
            if (self.logical(v.state_id), v.expectation_id) not in planted
        ]

    def max_states_hit(self) -> bool:
        return self.result.termination_reason == "max_states"

    def replay_diverged(self) -> int:
        return sum(s.reason.startswith("replay diverged") for s in self.result.skipped)


def run_config(
    name: str,
    patterns: tuple[str, ...] | None,
    *,
    seed: int = sim.SEED,
    use_reference: bool = False,
    policy: ExpectationSet | None = None,
    **overrides: Any,
) -> Run:
    app = sim.DynamicApp(seed=seed)
    graph = FakeGraph()
    config = make_config(patterns, **overrides)
    tap = Tap(app, config, graph)
    ports = Ports(
        crawler=tap,
        perception=FakePerception(),
        graph=graph,
        network=tap if patterns is not None else None,
    )
    explore = reference.explore if use_reference else graph_runner.explore
    result = explore(ports, sim.SEED_URL, policy or sim.policy(), config, run_id=f"dyn-{name}")
    return Run(name, config, result, graph, app, tap)


def run_all(calibration: Calibration | None = None) -> dict[str, Run]:
    calibration = calibration or calibrate()
    approved = calibration.approved_patterns
    return {
        "A": run_config("A", None),
        "B0": run_config("B0", ()),
        "B": run_config("B", approved),
        "B+": run_config("B+", (*approved, *HUMAN_PATTERNS)),
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def short(run: Run, state_id: str) -> str:
    return f"{run.logical(state_id)}#{state_id[-4:]}"


def transition_rows(run: Run) -> list[tuple[str, str, str, int, float, int]]:
    stats = run.stats
    if stats is None:
        return []
    labels: dict[str, str] = sim.action_labels()
    rows: list[tuple[str, str, str, int, float, int]] = []
    for key, counts in stats.transitions.items():
        source, action = json.loads(key)
        total = sum(counts.values())
        for target, n in counts.items():
            replay_n = stats.replay_transitions.get(key, {}).get(target, 0)
            rows.append(
                (
                    short(run, source),
                    labels.get(action, action),
                    short(run, target),
                    n,
                    n / total,
                    replay_n,
                )
            )
    return sorted(rows)


def endpoint_rows(run: Run) -> list[tuple[str, dict[str, int]]]:
    stats = run.stats
    return sorted(stats.endpoints.items()) if stats else []


def confidence_rows(
    run: Run,
) -> list[tuple[str, str, int, int, float, float, ConfidenceLabel, float]]:
    stats = run.stats
    if stats is None:
        return []
    states = {v.violation_id: v.state_id for v in run.result.violations}
    conf = violation_confidences(stats, states)
    rows = []
    for vid, c in sorted(conf.items()):
        state = states[vid]
        expectation = next(v.expectation_id for v in run.result.violations if v.violation_id == vid)
        rows.append(
            (
                f"{expectation}@{short(run, state)}",
                vid,
                c.n_present,
                c.n_observations,
                c.mean,
                c.lower_bound,
                c.label,
                stats.confidence.get(vid, float("nan")),
            )
        )
    return rows


def calibration_confidence(
    cal: Calibration,
) -> dict[str, tuple[int, int, float, float, ConfidenceLabel]]:
    out = {}
    for key, (k, n) in cal.flaky_presence.items():
        c = observation_confidence(k, n)
        out[key] = (k, n, c.mean, c.lower_bound, c.label)
    return out


def endpoint_mismatches(run: Run) -> tuple[int, list[tuple[str, str, float, float]]]:
    """Per (state, action) pair: calls-per-window versus `expected.json`.

    Returns the number of (pair, endpoint) cells compared and the disagreeing ones.
    """
    stats = run.stats
    if stats is None:
        return 0, []
    expected = load_expected()["endpoints"]["by_action"]
    labels: dict[str, str] = sim.action_labels()
    compared = 0
    bad: list[tuple[str, str, float, float]] = []
    for key, per_endpoint in stats.action_endpoints.items():
        _, action = json.loads(key)
        label = labels[action]
        for endpoint, counts in per_endpoint.items():
            want = expected[label].get(endpoint)
            observed = counts["calls"] / counts["actions"]
            compared += 1
            if want is None or observed != want:
                bad.append((label, endpoint, observed, float(want or 0)))
    return compared, bad


# ---------------------------------------------------------------------------
# Supplementary: the same comparison over several app seeds
# ---------------------------------------------------------------------------

SWEEP_SEEDS = tuple(range(20))


@dataclass(frozen=True, slots=True)
class SweepRow:
    seed: int
    config: str
    states: int
    logical: int
    max_states_hit: bool
    diverged: int
    stable_found: bool
    flaky_found: bool


def sweep(approved: tuple[str, ...]) -> tuple[list[SweepRow], Counter[tuple[str, str]]]:
    rows: list[SweepRow] = []
    pooled: Counter[tuple[str, str]] = Counter()
    labels: dict[str, str] = sim.action_labels()
    for seed in SWEEP_SEEDS:
        for name, patterns in (
            ("A", None),
            ("B", approved),
            ("B+", (*approved, *HUMAN_PATTERNS)),
        ):
            run = run_config(name, patterns, seed=seed)
            found = run.found()
            rows.append(
                SweepRow(
                    seed,
                    name,
                    run.result.states,
                    len(run.states_per_logical()),
                    run.max_states_hit(),
                    run.replay_diverged(),
                    found["V-STABLE"],
                    found["V-FLAKY"],
                )
            )
            if name == "B+" and run.stats is not None:
                for key, counts in run.stats.transitions.items():
                    action = json.loads(key)[1]
                    if labels[action] in ("Add to cart", "Checkout"):
                        for target, n in counts.items():
                            pooled[(labels[action], run.logical(target))] += n
    return rows, pooled


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------


def _table(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


def _yn(flag: bool) -> str:
    return "yes" if flag else "no"


def render(
    calibration: Calibration,
    runs: dict[str, Run],
    rows: list[SweepRow],
    pooled: Counter[tuple[str, str]],
) -> str:
    expected = load_expected()
    total = expected["logical_state_count"]
    out: list[str] = []
    w = out.append

    w("# Dynamic-app experiment: baseline vs probabilistic states\n")
    w(
        "> **Simulated app, not a real browser.** Every number below comes from a seeded,"
        " stdlib-only simulation (`tests/fixtures/orchestrator/dynamic-app/app.py`) driving"
        " `graph_runner.explore` through the repo's `Ports` with `FakePerception` and `FakeGraph`."
        " Perception is a tag lookup, not a VLM; there is no Playwright, DOM engine, layout,"
        " network stack or real timing. The results show how the orchestrator's identity,"
        " replay and statistics logic behaves on this one synthetic app. They do not"
        " measure recall or state counts on real sites.\n"
    )
    w("This file is generated by the command below; do not edit it by hand.\n")
    w("## Commands\n")
    w(
        "```\n"
        "uv run python tests/fixtures/orchestrator/dynamic-app/experiment.py   # regenerates this file\n"
        "uv run pytest tests/integration/orchestrator/test_dynamic_app.py -q    # asserts what holds\n"
        "uv run pytest tests/integration/orchestrator tests/unit/orchestrator -q\n"
        "```\n"
    )

    w("## Setup\n")
    w(
        f"* App seed `{sim.SEED}` (render stream and outcome stream both derived from it)."
        f" Role `guest`, depth limit {DEPTH_LIMIT}, `max_states` {MAX_STATES},"
        " `perception_rate_per_min` 0, FakePerception + FakeGraph."
    )
    w(
        f"* Ground truth (`expected.json`): {total} logical states, 2 planted violations"
        " (`V-STABLE`: `debug-panel` on `/settings`, every render; `V-FLAKY`: `admin-link`"
        f" on `/products`, rendered with probability {sim.FLAKY_RENDER_PROBABILITY}),"
        " a 70/30 action (`Add to cart`), a 5% action (`Checkout` -> error page), an SPA modal"
        " at `/`, and back-edges (e.g. products -> home -> products)."
    )
    w("* Configurations:\n")
    w(
        _table(
            ["Config", "probabilistic_states", "volatility_patterns"],
            [
                ["A", "False", "none (baseline: `GraphPort.fingerprint`)"],
                ["B0", "True", "none (control: the flag alone)"],
                [
                    "B",
                    "True",
                    f"{len(calibration.approved_patterns)} patterns: the human-approved subset of"
                    " `insights.suggest_masks`",
                ],
                [
                    "B+",
                    "True",
                    f"B plus {len(HUMAN_PATTERNS)} patterns the reviewer wrote by hand"
                    " (supplementary, see below)",
                ],
            ],
        )
        + "\n"
    )

    w("## Mask suggestion and the simulated human-approval step\n")
    n_sug = len(calibration.reviewed)
    n_ok = sum(r.approved for r in calibration.reviewed)
    w(
        f"Each of the {len(sim.LOGICAL_STATES)} logical states was captured"
        f" {CALIBRATION_CAPTURES} times from a separate app instance (same seed) and passed to"
        f" `suggest_masks`. It returned {n_sug} suggestions. No human was in the loop at run time;"
        " the approval is a documented, mechanical reviewer (`experiment.review`) so the run is"
        f" reproducible. It approved {n_ok} and rejected {n_sug - n_ok}. Rules: reject a pattern that"
        " (1) never occurs in the raw markup (it cannot help), or (2) could touch a control label or"
        " policy-relevant text (`Admin console`, `Debug panel`, any button/link name)."
        " Rejections by reason:\n"
    )
    reasons = Counter(
        re.sub(r"'.*'", "'...'", r.reason) for r in calibration.reviewed if not r.approved
    )
    w(_table(["Reason", "Count"], [[k, str(v)] for k, v in sorted(reasons.items())]) + "\n")
    w(
        "Approved patterns (union over states, "
        f"{len(calibration.approved_patterns)} distinct):\n\n```\n"
        + "\n".join(calibration.approved_patterns)
        + "\n```\n"
    )
    w(
        "Reviewer-written patterns used only in B+ (NOT from `suggest_masks`):\n\n```\n"
        + "\n".join(HUMAN_PATTERNS)
        + "\n```\n"
    )
    w(
        "`suggest_masks` emits text patterns from the RAW text of regions whose raw text varies"
        " and attribute patterns for random class/id suffixes. Each is checked to occur in the raw"
        " markup (the string `dynamic.identity` hashes) and to keep at least two or three literal"
        " letters, so a bare `\\d+` can never be suggested. B+ adds two hand-written patterns on top"
        " as an oracle upper bound.\n"
    )

    w(f"## Headline (seed {sim.SEED})\n")
    head = []
    for name, run in runs.items():
        found = run.found()
        head.append(
            [
                name,
                run.result.termination_reason,
                _yn(run.max_states_hit()),
                f"{run.result.states} / cap {MAX_STATES}",
                f"{len(run.states_per_logical())} / {total}",
                str(run.replay_diverged()),
                str(len(run.result.skipped)),
                str(run.result.edges),
                str(run.result.replays),
                f"{_yn(found['V-STABLE'])}",
                f"{_yn(found['V-FLAKY'])}",
                str(len(run.unplanted())),
            ]
        )
    w(
        _table(
            [
                "Config",
                "Termination",
                "max_states hit",
                "Distinct states",
                "Logical states covered",
                "Replay-diverged skips",
                "All skips",
                "Edges",
                "Replays",
                "V-STABLE found",
                "V-FLAKY found",
                "Unplanted findings",
            ],
            head,
        )
        + "\n"
    )
    for name, run in runs.items():
        w(
            f"* {name}: states per logical state = `{run.states_per_logical()}`;"
            f" skips = `{run.skip_categories()}`;"
            f" outcomes drawn = `{run.app.outcomes}`;"
            f" products renders with flaky element = {run.app.products_renders_with_flaky}"
            f" / {run.app.products_renders}."
        )
    w("")
    w(
        "Violation recall is 'found at least once, at the right logical state'. Logical coverage is"
        " computed from the ground-truth marker on each discovered state, not from the number of ids.\n"
    )

    for name in ("B", "B+"):
        run = runs[name]
        w(f"## Config {name}: transition probabilities (empirical counts)\n")
        trows = transition_rows(run)
        w(
            _table(
                ["Source", "Action", "Target", "N (all)", "P_hat", "N (replay)"],
                [[a, b, c, str(n), f"{p:.2f}", str(rn)] for a, b, c, n, p, rn in trows],
            )
            + "\n"
        )
        w(
            "`N (all)` includes replay observations (`dynamic.observe_transition`); replay"
            " re-executes path steps and is not an independent trial. `#xxxx` is the last four"
            " characters of the state id.\n"
        )
        w(f"## Config {name}: endpoints (sanitised, calls and clicks)\n")
        w(
            _table(
                [
                    "Endpoint",
                    "calls",
                    "action windows",
                    "click windows",
                    "replay calls",
                    "replay clicks",
                ],
                [
                    [
                        e,
                        str(c["calls"]),
                        str(c["actions"]),
                        str(c["clicks"]),
                        str(c["replay_calls"]),
                        str(c["replay_clicks"]),
                    ]
                    for e, c in endpoint_rows(run)
                ],
            )
            + "\n"
        )
        compared, bad = endpoint_mismatches(run)
        w(
            f"Per-(state, action) calls-per-window versus `expected.json`: {compared} cells"
            f" compared, {len(bad)} disagree.\n"
        )
        w(f"## Config {name}: violation confidence\n")
        crow = confidence_rows(run)
        if crow:
            w(
                _table(
                    [
                        "Violation",
                        "present",
                        "audits",
                        "Beta mean",
                        "Beta lower 5%",
                        "Label",
                        "runner recurrence x reproducibility",
                    ],
                    [
                        [a, str(k), str(n), f"{m:.2f}", f"{lo:.2f}", lab, f"{conf:.2f}"]
                        for a, _, k, n, m, lo, lab, conf in crow
                    ],
                )
                + "\n"
            )
        else:
            w("No violation was recorded in this run.\n")

    w("## Independent calibration sample (not part of any crawl)\n")
    w(
        _table(
            ["Element", "present", "captures", "Beta mean", "Beta lower 5%", "Label"],
            [
                [k, str(a), str(b), f"{m:.2f}", f"{lo:.2f}", lab]
                for k, (a, b, m, lo, lab) in sorted(calibration_confidence(calibration).items())
            ],
        )
        + "\n"
    )

    w(f"## Supplementary: {len(SWEEP_SEEDS)} app seeds (same configs, same cap)\n")
    w("Seed 7 is the headline; this table checks that it is not an outlier.\n")
    agg = []
    for name in ("A", "B", "B+"):
        sel = [r for r in rows if r.config == name]
        agg.append(
            [
                name,
                f"{sum(r.states for r in sel) / len(sel):.1f}",
                f"{sum(r.logical for r in sel) / len(sel):.1f} / {total}",
                f"{sum(r.max_states_hit for r in sel)} / {len(sel)}",
                f"{sum(r.diverged for r in sel) / len(sel):.1f}",
                f"{sum(r.stable_found for r in sel)} / {len(sel)}",
                f"{sum(r.flaky_found for r in sel)} / {len(sel)}",
            ]
        )
    w(
        _table(
            [
                "Config",
                "mean states",
                "mean logical covered",
                "max_states hit",
                "mean replay-diverged",
                "V-STABLE found",
                "V-FLAKY found",
            ],
            agg,
        )
        + "\n"
    )
    w(
        "Pooled B+ target counts for the stochastic actions across all seeds (independent runs, includes replay):\n"
    )
    prow = []
    for action in ("Add to cart", "Checkout"):
        tot = sum(n for (a, _), n in pooled.items() if a == action)
        for (a, target), n in sorted(pooled.items()):
            if a == action:
                prow.append([action, target, str(n), f"{n / tot:.2f}"])
    w(_table(["Action", "Target", "N", "share"], prow) + "\n")
    w(narrative(runs, rows, calibration))
    return "\n".join(out) + "\n"


def narrative(runs: dict[str, Run], rows: list[SweepRow], calibration: Calibration) -> str:
    a, b, bp = runs["A"], runs["B"], runs["B+"]
    flaky_key = "admin-link@products"
    k, n = calibration.flaky_presence[flaky_key]
    bp_found = bp.found()
    return f"""## What this does and does not show

Everything below is about a simulated app (see the banner). Statements are limited to what the
tables above contain.

**What held**

* `max_states` ({MAX_STATES}) was hit by {sum(r.max_states_hit for r in rows)} of {len(rows)} sweep runs. The
  headline runs ended with A: `{a.result.termination_reason}`, B: `{b.result.termination_reason}`,
  B+: `{bp.result.termination_reason}`. The cap was not the binding limit on this app, so the
  experiment does not demonstrate state-explosion protection.
* Baseline A did not explode. It lost coverage silently: {a.result.states} distinct states,
  {len(a.states_per_logical())} of {runs_total()} logical states, {a.replay_diverged()} replay-diverged skips.
  Every re-open of `/` produced a new fingerprint (ad, counter, classes), so replayed paths
  diverged. `V-STABLE` found: {a.found()["V-STABLE"]}.
* Config B (only the approved `suggest_masks` output, no hand-written pattern):
  {b.result.states} states, {len(b.states_per_logical())} of {runs_total()} logical, {b.replay_diverged()} replay-diverged skips,
  `V-STABLE` found: {b.found()["V-STABLE"]}, `V-FLAKY` found: {b.found()["V-FLAKY"]}. Control B0 (flag on, no
  masks) stays equal to A, so the change comes from the masks and not from the flag. Over the
  sweep B covered {sum(r.logical for r in rows if r.config == "B") / len(SWEEP_SEEDS):.1f} of {runs_total()} logical states on average
  versus {sum(r.logical for r in rows if r.config == "A") / len(SWEEP_SEEDS):.1f} for A, and found `V-STABLE` in
  {sum(r.stable_found for r in rows if r.config == "B")} of {len(SWEEP_SEEDS)} seeds versus {sum(r.stable_found for r in rows if r.config == "A")} for A.
  An earlier run of this experiment, before `suggest_masks` was changed to validate against raw
  markup and to cover attributes, showed B equal to A; that negative result is why it changed.
* Config B+ (B plus two oracle patterns): {bp.result.states} states, {len(bp.states_per_logical())} of {runs_total()} logical,
  {bp.replay_diverged()} replay-diverged skips, `V-STABLE` found: {bp_found["V-STABLE"]}, `V-FLAKY` found:
  {bp_found["V-FLAKY"]}, no unplanted findings. Sweep average coverage
  {sum(r.logical for r in rows if r.config == "B+") / len(SWEEP_SEEDS):.1f} of {runs_total()}; `V-STABLE` in
  {sum(r.stable_found for r in rows if r.config == "B+")} of {len(SWEEP_SEEDS)} seeds.
* Endpoint accounting matched `expected.json` in every compared (state, action) cell. This check
  is CIRCULAR: the simulator's own small normaliser produces the labels and `expected.json` was
  written for it. It exercises the runner's counting (calls vs actions vs clicks), not
  `stochastic/endpoints.py`, which is not wired into this crawl.
* The transition counts expose the flaky element: `home --Products-->` splits between two
  `products` classes (element rendered or not), which is a state split, not a navigation outcome.

**What did NOT hold, or is weaker than hoped**

* "B discovers fewer states than A" is false here. B equals A, and B+ discovers MORE ({bp.result.states} vs
  {a.result.states}) because A's small count is lost coverage. A lower distinct-state count is not evidence of
  better behaviour on this app. The only true bound is `states <= max_states`.
* The approval step is a mechanical reviewer standing in for a person. It rejects patterns that
  match protected text, but a real reviewer is still required: a pattern can match meaningful
  text, and masking can hide differences an auditor needs to see.
* The simulator formats class names as `<prefix>-<6 alphanumerics>` and timestamps as
  `Updated N minutes ago`. Real sites use other schemes (hashed CSS-in-JS, `1h`, locale dates),
  so B's gain here does not transfer automatically.
* The flaky violation is NOT labelled flaky inside the crawl. Its presence is part of the state
  identity, so the state that contains it is only ever audited when it is present:
  `violation_confidences` reports {_label(bp, "e-admin-link")} for it in B+. Only the independent
  calibration sample ({k} of {n} captures, 0.4 planted) labels it `flaky`. The runner's
  recurrence x reproducibility value is lower for the flaky violation than the stable one in B+
  only because the state split halves reproducibility, and both rest on very few audits.
* `V-STABLE` is labelled {_label(bp, "e-debug-panel")} in B+: it was audited
  {_audits(bp, "e-debug-panel")} times, below the default minimum of 5.
* Infinite scroll is bounded by `depth_limit`, not by equivalence: B+ holds
  {bp.states_per_logical().get("feed", 0)} states for the single logical `feed` state, one per number of loaded batches.
* The 70/30 and 5% outcomes are not estimable inside one seed-7 run: `Add to cart` was executed
  {sum(1 for x in bp.app.outcomes if x[0] == "Add to cart")} time(s) and the 5% error page was never drawn. The pooled table counts
  transitions across sweep crawls, including replay re-executions; they are not independent
  trials and are not used to claim the planted probabilities were recovered.
* `sold-out` and `error` were not reached at seed 7 because the outcome stream did not draw them.

**Caveats**

Simulated app, one topology, one policy; perception is a tag lookup; `FakeGraph` stands in for
Track D; replay safely re-clicks `Add to cart` and `Checkout` because the simulation has no real
side effects. Calibration used the same seed as the crawl. Nothing here supports a claim about
real browsers, real VLM recall or calibrated probabilities.
"""


def runs_total() -> int:
    total: int = load_expected()["logical_state_count"]
    return total


def _violation(run: Run, expectation: str) -> Violation | None:
    return next((v for v in run.result.violations if v.expectation_id == expectation), None)


def _label(run: Run, expectation: str) -> str:
    violation = _violation(run, expectation)
    if violation is None or run.stats is None:
        return "no label (not found)"
    conf = violation_confidences(run.stats, {violation.violation_id: violation.state_id})
    entry = conf.get(violation.violation_id)
    return f"`{entry.label}`" if entry else "no label"


def _audits(run: Run, expectation: str) -> int:
    violation = _violation(run, expectation)
    if violation is None or run.stats is None:
        return 0
    return run.stats.audits.get(violation.state_id, 0)


def main() -> None:
    calibration = calibrate()
    runs = run_all(calibration)
    rows, pooled = sweep(calibration.approved_patterns)
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = render(calibration, runs, rows, pooled)
    RESULTS_PATH.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
