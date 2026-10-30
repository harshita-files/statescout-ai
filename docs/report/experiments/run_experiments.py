"""Reproducible experiments backing the StateScout paper draft.

    PYTHONDONTWRITEBYTECODE=1 uv run --no-sync python docs/report/experiments/run_experiments.py

Read-only with respect to the repository: it imports the real modules, reads the
ground-truth app, and writes JSON results only under docs/report/data/.

E1  Perception ablation on test-apps/broken-admin: the oracle (tag-reading)
    perception vs. the deterministic DOM/AX Semantic UI Map builder, both
    feeding the real negation engine (apps/agent/negation/audit.py).
E2  Fingerprint stability: inject volatile noise (session/CSRF tokens,
    timestamps, generated ids, CDP node ids) into each page K times and count
    distinct state ids under the normalizing fingerprint vs. a naive hash.
E3  Two-clause-type necessity: rerun E1's oracle arm with the `required`
    half of the policy dropped (intersection-only audit) and count what is lost.
E4  Subject-grounding ablation: rerun E1's deterministic arm with a lexical
    normalizer (hyphen/underscore -> space) patched into the negation engine's
    matcher, in-process only, to measure how much of the E1 gap is vocabulary.

Added in revision 2 (E1-E4 code and values are unchanged; verified by diff):

E5  Loop-level counters (graph_runner.explore with the in-memory fakes, no
    browser, no Neo4j/Redis): executed pairs, duplicates, replays, replayed
    steps, revisit edges, termination; discovery-order invariance; an injected
    fill/submit; and simulated crash/resume using LangGraph's InMemorySaver.
E6  The fake's oracle semantic maps fed to the REAL negation.audit.audit.
E7  Perturbed perceivers (under- and over-reporting) through the real audit,
    per-polarity error counts; tests the monotonicity observation (an elementary
    property of the two set operations, not a research result).
E8  Fingerprint sensitivity / over-merge tests on single, targeted edits.
E9  Mutants of broken-admin generated in memory (nothing is written to
    test-apps/), scored by three arms including a hand-written DOM-invariant
    baseline that is OUR OWN re-implementation, not Crawljax or ATUSA.

Added in revision 3 (values of E1-E9 unchanged; verified by diff):

E10 Independent XPath-subset baseline over element types, link targets and
    visible text (not data-tag), run on copies of the fixture and mutants whose
    data-tag attributes are stripped; results per mutant family.
E11 Two-seed-action fixture variant for the crash/resume qualification.

Added in revision 4:

E12 Three further in-repo apps (test-apps/broken-rbac-demo, missing-consent-demo,
    broken-feature-flag-demo), read-only: policy and ground truth derived from
    each README first (ordering is an authorial statement the artifact cannot evidence); arms A3 and an XPath script written after reading the HTML (in-sample).
    E11's field second_run_attempts_of_claimed_pairs now snapshots the claimed set
    (it previously depended on PYTHONHASHSEED; no other E11/E5 value changed).
E13 Label renames of the fixture reported per variant.

Added in revision 5:

E14 Four generated, unannotated apps (tests/fixtures/orchestrator/paper-subjects/, read only):
    invariants written from the policy files only (hash and UTC timestamp recorded),
    A3 subjects verbatim from policy.expected.json; per-clause and per-polarity results.
"""

from __future__ import annotations

import dataclasses
import hashlib
import html.parser
import inspect
import json
import platform
import random
import re
import subprocess
import sys
import types
from collections import Counter
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

# `apps.agent.perception.__init__` eagerly imports the Gemini client, whose SDK
# is not installed in every environment. Register the package as a bare
# namespace so the deterministic submodules import without it.
_pkg = types.ModuleType("apps.agent.perception")
_pkg.__path__ = [str(ROOT / "apps/agent/perception")]
sys.modules["apps.agent.perception"] = _pkg

from apps.agent.contracts import CaptureBundle, ExpectationNode, ExpectationSet  # noqa: E402
from apps.agent.graph.fingerprint import fingerprint_bundle  # noqa: E402
from apps.agent.negation.audit import audit  # noqa: E402
from apps.agent.orchestrator.fakes import FakePerception  # noqa: E402
from apps.agent.perception.semantic_map import build_semantic_map  # noqa: E402
from tests.fixtures.orchestrator import testapp  # noqa: E402

APP_DIR = ROOT / "test-apps" / "broken-admin"
OUT = ROOT / "docs" / "report" / "data"


def pages() -> dict[str, str]:
    found = {"/index.html": (APP_DIR / "index.html").read_text(encoding="utf-8")}
    for path in sorted((APP_DIR / "pages").glob("*.html")):
        found[f"/pages/{path.name}"] = path.read_text(encoding="utf-8")
    return found


def score(found: set[tuple[str, str, str]], planted: set[tuple[str, str, str]]) -> dict[str, object]:
    tp = len(found & planted)
    fp = len(found - planted)
    fn = len(planted - found)
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "false_positives": sorted(map(list, found - planted)),
        "missed": sorted(map(list, planted - found)),
    }


def run_audit(arm: str, policy: ExpectationSet, role: str) -> set[tuple[str, str, str]]:
    fake = FakePerception()
    found: set[tuple[str, str, str]] = set()
    for page, html in pages().items():
        bundle = CaptureBundle(url=page, dom=html, ax_tree=None, title=page)
        if arm == "oracle":
            smap = fake.analyze(bundle, role)
            violations = fake.audit(smap, policy)
        else:
            smap = build_semantic_map(bundle, role, state_id=page)
            violations = audit(smap, policy)
        found |= {(page, v.expectation_id, v.clause_type) for v in violations}
    return found


# ---------------------------------------------------------------------------


def e1_e3() -> dict[str, object]:
    app = testapp.load("broken-admin")
    planted = {v.key for v in app.expected}
    intersection_only = ExpectationSet(forbidden=app.policy.forbidden, required=())

    results = {
        "planted": len(planted),
        "pages": len(pages()),
        "E1_oracle_perception": score(run_audit("oracle", app.policy, app.role), planted),
        "E1_deterministic_dom_perception": score(
            run_audit("deterministic", app.policy, app.role), planted
        ),
        "E3_oracle_intersection_only": score(
            run_audit("oracle", intersection_only, app.role), planted
        ),
    }
    # E4 -- patch the matcher's normalizer for this process only.
    import re

    import apps.agent.negation.audit as engine

    original = engine._normalize
    engine._normalize = lambda v: re.sub(r"[\s_-]+", " ", v).strip().lower()
    try:
        results["E4_deterministic_lexical_grounding"] = score(
            run_audit("deterministic", app.policy, app.role), planted
        )
    finally:
        engine._normalize = original
    return results


# ---------------------------------------------------------------------------


def _noisy(html: str, rng: random.Random) -> str:
    """The same logical page, re-rendered with per-request volatile values."""
    token = "".join(rng.choices("abcdef0123456789", k=12))
    stamp = str(1_700_000_000_000 + rng.randrange(10**9))
    gen_id = "".join(rng.choices("abcdef0123456789", k=10))
    extra = (
        f'<div data-session="sess_{token}" data-csrf="csrf_{token}"></div>'
        f'<span id="{gen_id}" data-request-id="req_{token}">rendered at {stamp}</span>'
    )
    return html.replace("<body>", "<body>" + extra, 1)


def _noisy_ax(rng: random.Random) -> dict[str, object]:
    """A CDP-shaped AX tree whose node ids differ on every capture."""
    base = rng.randrange(10**6)
    return {
        "nodes": [
            {"nodeId": str(base), "backendDOMNodeId": base, "childIds": [str(base + 1)],
             "role": {"value": "RootWebArea"}, "name": {"value": "page"}},
            {"nodeId": str(base + 1), "parentId": str(base), "backendDOMNodeId": base + 1,
             "role": {"value": "link"}, "name": {"value": "Back"}},
        ]
    }


def e2(k: int = 50, seed: int = 7) -> dict[str, object]:
    rng = random.Random(seed)
    per_page = {}
    total_norm: set[str] = set()
    total_naive: set[str] = set()
    for page, html in pages().items():
        norm, naive = set(), set()
        for _ in range(k):
            bundle = CaptureBundle(url=page, dom=_noisy(html, rng), ax_tree=_noisy_ax(rng))
            norm.add(fingerprint_bundle(bundle))
            naive.add(
                hashlib.sha256(
                    (page + bundle.dom + json.dumps(bundle.ax_tree, sort_keys=True)).encode()
                ).hexdigest()
            )
        per_page[page] = {"normalized": len(norm), "naive": len(naive)}
        total_norm |= norm
        total_naive |= naive

    # Sensitivity check: a genuine UI change must still change the id.
    admin = pages()["/pages/admin.html"]
    without_delete = admin.replace('<button data-tag="delete-user">Delete user</button>', "")
    sensitive = fingerprint_bundle(
        CaptureBundle(url="/pages/admin.html", dom=admin, ax_tree=None)
    ) != fingerprint_bundle(CaptureBundle(url="/pages/admin.html", dom=without_delete, ax_tree=None))

    return {
        "captures_per_page": k,
        "logical_states": len(per_page),
        "distinct_ids_normalized": len(total_norm),
        "distinct_ids_naive": len(total_naive),
        "per_page": per_page,
        "real_change_detected": sensitive,
    }



# ===========================================================================
# Revision 2 additions (E5-E9). Everything below is new; E1-E4 are untouched.
# ===========================================================================

from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402

from apps.agent.contracts import SemanticUIMap, UIElement  # noqa: E402
from apps.agent.orchestrator import graph_runner  # noqa: E402
from apps.agent.orchestrator.config import OrchestratorConfig  # noqa: E402
from apps.agent.orchestrator.deps import Ports  # noqa: E402
from apps.agent.orchestrator.explore import explore as reference_explore  # noqa: E402
from apps.agent.orchestrator.fakes import FakeCrawler, FakeGraph, FakeLink, FakePage  # noqa: E402
from apps.agent.orchestrator.state import initial_state  # noqa: E402

Triple = tuple[str, str, str]


def _config(app) -> OrchestratorConfig:
    return OrchestratorConfig(
        _env_file=None,  # type: ignore[call-arg]
        role=app.role,
        depth_limit=10,
        max_states=50,
        perception_rate_per_min=0,
    )


def _split(found: set[Triple], planted: set[Triple]) -> dict[str, int]:
    """Error counts split by clause type (F = forbidden_present, R = required_absent)."""
    out = {"tp_F": 0, "fp_F": 0, "fn_F": 0, "tp_R": 0, "fp_R": 0, "fn_R": 0}
    for kind, tag in (("forbidden_present", "F"), ("required_absent", "R")):
        f = {t for t in found if t[2] == kind}
        p = {t for t in planted if t[2] == kind}
        out[f"tp_{tag}"] = len(f & p)
        out[f"fp_{tag}"] = len(f - p)
        out[f"fn_{tag}"] = len(p - f)
    return out


# ---------------------------------------------------------------------------
# E6 -- real negation.audit.audit on the fake's oracle semantic maps (F-01)
# ---------------------------------------------------------------------------


def _audit_with(arm: str, pages_: dict[str, str], policy: ExpectationSet, role: str) -> set[Triple]:
    fake = FakePerception()
    found: set[Triple] = set()
    for page, html_text in pages_.items():
        bundle = CaptureBundle(url=page, dom=html_text, ax_tree=None, title=page)
        if arm == "fake_algebra":  # oracle maps + the fake's own audit (E1 arm)
            violations = fake.audit(fake.analyze(bundle, role), policy)
        elif arm == "oracle_maps_real_audit":  # oracle maps + production audit
            violations = audit(fake.analyze(bundle, role), policy)
        elif arm == "dom_channel_real_audit":  # production semantic-map builder + audit
            violations = audit(build_semantic_map(bundle, role, state_id=page), policy)
        else:
            raise ValueError(arm)
        found |= {(page, v.expectation_id, v.clause_type) for v in violations}
    return found


def e6() -> dict[str, object]:
    app = testapp.load("broken-admin")
    planted = {v.key for v in app.expected}
    intersection_only = ExpectationSet(forbidden=app.policy.forbidden, required=())
    pg = pages()
    return {
        "fake_algebra": score(_audit_with("fake_algebra", pg, app.policy, app.role), planted),
        "oracle_maps_real_audit": score(
            _audit_with("oracle_maps_real_audit", pg, app.policy, app.role), planted
        ),
        "oracle_maps_real_audit_forbidden_only": score(
            _audit_with("oracle_maps_real_audit", pg, intersection_only, app.role), planted
        ),
        "arms_agree": _audit_with("fake_algebra", pg, app.policy, app.role)
        == _audit_with("oracle_maps_real_audit", pg, app.policy, app.role),
    }


# ---------------------------------------------------------------------------
# E5 -- loop-level counters, order invariance, injected fill/submit, crash/resume
# ---------------------------------------------------------------------------


class _CountingGraph(FakeGraph):
    """FakeGraph that remembers the last claim, so the crawler can tell a
    frontier execution (immediately after a claim) from a replay re-fire."""

    def __init__(self) -> None:
        super().__init__()
        self.pending_claim: tuple[str, str] | None = None
        self.crash_after_claim: int | None = None  # n-th claim, fail in crawler.act
        self.crash_in_edge: int | None = None  # n-th edge, fail in persist_edge

    def mark_visited(self, state_id: str, action_id: str) -> None:
        super().mark_visited(state_id, action_id)
        self.pending_claim = (state_id, action_id)

    def persist_edge(self, edge) -> None:  # type: ignore[no-untyped-def]
        if self.crash_in_edge is not None and len(self.edges) + 1 == self.crash_in_edge:
            self.crash_in_edge = None
            raise _Crash("simulated crash while persisting an edge")
        super().persist_edge(edge)


class _Crash(RuntimeError):
    """Deliberately NOT a StateScoutError, so the loop does not absorb it."""


class _CountingCrawler(FakeCrawler):
    def __init__(self, graph: _CountingGraph, *a, **k) -> None:  # type: ignore[no-untyped-def]
        super().__init__(*a, **k)
        self.graph = graph
        self.frontier_attempts: Counter[tuple[str, str]] = Counter()
        self.all_attempts: Counter[tuple[str | None, str]] = Counter()
        self.replay_attempts = 0

    def act(self, action):  # type: ignore[no-untyped-def]
        g = self.graph
        self.all_attempts[(self.current, action.action_id)] += 1
        if g.pending_claim is not None:
            pair = g.pending_claim
            g.pending_claim = None
            self.frontier_attempts[pair] += 1
            if g.crash_after_claim is not None and len(g.visited) == g.crash_after_claim:
                g.crash_after_claim = None
                raise _Crash("simulated crash after the claim, inside the action")
        else:
            self.replay_attempts += 1
        return super().act(action)


def _crawl(app, pages_=None, *, loop=graph_runner.explore):
    graph = _CountingGraph()
    crawler = _CountingCrawler(graph, pages_ or app.pages, role=app.role, base_url="")
    ports = Ports(crawler=crawler, perception=FakePerception(), graph=graph)
    result = loop(ports, app.seed, app.policy, _config(app), run_id="e5")
    return result, graph, crawler


def _counters(result, graph: _CountingGraph, crawler: _CountingCrawler) -> dict[str, object]:
    pairs = crawler.all_attempts
    return {
        "termination": result.termination_reason,
        "max_state_depth": max((n.depth for n in graph.states.values()), default=0),
        "states": result.states,
        "edges": result.edges,
        "pairs_executed": result.visited_pairs,
        "distinct_pairs_claimed": len(graph.visited),
        "duplicate_frontier_executions": sum(v - 1 for v in crawler.frontier_attempts.values()),
        "replays": result.replays,
        "replayed_steps": result.replay_steps,
        "replayed_steps_per_pair": round(result.replay_steps / max(result.visited_pairs, 1), 2),
        "revisit_edges_persisted": len(graph.back_edges()),
        "tree_edges": len(graph.edges) - len(graph.back_edges()),
        "total_crawler_act_calls": sum(pairs.values()),
        "max_executions_of_one_pair_incl_replay": max(pairs.values()) if pairs else 0,
        "pairs_executed_more_than_once_incl_replay": sum(1 for v in pairs.values() if v > 1),
        "skipped": len(result.skipped),
        "violations": len(result.violations),
    }


def _graph_signature(graph: FakeGraph) -> tuple[object, ...]:
    return (
        frozenset(
            (e.from_state_id, e.action_id, e.to_state_id, e.is_back_edge) for e in graph.edges
        ),
        frozenset(graph.states),
        frozenset((v.state_id, v.expectation_id, v.clause_type) for v in graph.violations),
    )


def _with_link_kind(pages_, page: str, name: str, kind: str):  # type: ignore[no-untyped-def]
    out = dict(pages_)
    spec = out[page]
    out[page] = dataclasses.replace(
        spec,
        transitions=tuple(
            dataclasses.replace(link, kind=kind) if link.name == name else link
            for link in spec.transitions
        ),
    )
    return out


def _resume_sweep(app, where: str, fresh_crawler: bool, baseline_sig, pages_=None, n_positions: int = 11) -> dict[str, object]:  # type: ignore[no-untyped-def]
    """Crash at each of the 11 claims (where='act') or edge writes (where='edge')
    and resume from the in-memory LangGraph checkpoint."""
    rows = []
    pages_ = pages_ or app.pages
    for n in range(1, n_positions + 1):
        graph = _CountingGraph()
        if where == "act":
            graph.crash_after_claim = n
        else:
            graph.crash_in_edge = n
        crawler = _CountingCrawler(graph, pages_, role=app.role, base_url="")
        ports = Ports(crawler=crawler, perception=FakePerception(), graph=graph)
        saver = InMemorySaver()
        cfg = _config(app)
        runner = graph_runner.build_graph(ports, app.policy, cfg, saver)
        start = initial_state("e5-resume", app.seed, role=app.role)
        start["current_bundle"] = crawler.open(app.seed)
        conf = {
            "configurable": {"thread_id": "e5-resume"},
            "recursion_limit": graph_runner.recursion_limit(cfg),
        }
        try:
            runner.invoke(start, config=conf)
            raise AssertionError("injected crash did not fire")
        except _Crash:
            pass
        attempts = Counter(crawler.frontier_attempts)
        if fresh_crawler:  # browser lost: a new crawler that has not opened any page
            crawler = _CountingCrawler(graph, pages_, role=app.role, base_url="")
            crawler.frontier_attempts = attempts
            runner = graph_runner.build_graph(
                Ports(crawler=crawler, perception=FakePerception(), graph=graph),
                app.policy,
                cfg,
                saver,
            )
        final = runner.invoke(None, config=conf)
        rows.append(
            {
                "crash_at": n,
                "max_attempts_of_a_claimed_pair": max(crawler.frontier_attempts.values()),
                "pairs_attempted_twice": sum(1 for v in crawler.frontier_attempts.values() if v > 1),
                "skipped_after_resume": len(final["skipped"]),
                "graph_equals_uninterrupted": _graph_signature(graph) == baseline_sig,
            }
        )
    return {
        "positions": len(rows),
        "positions_with_a_pair_attempted_twice": sum(1 for r in rows if r["pairs_attempted_twice"]),
        "positions_with_skips": sum(1 for r in rows if r["skipped_after_resume"]),
        "positions_graph_equals_uninterrupted": sum(1 for r in rows if r["graph_equals_uninterrupted"]),
        "rows": rows,
    }


def _claim_set_restart(app, pages_=None, n_positions: int = 11, full_edges: int = 11) -> dict[str, object]:
    """No checkpoint, only the persisted claim set: start a NEW run on the same graph."""
    out = []
    pages_ = pages_ or app.pages
    for n in range(1, n_positions + 1):
        graph = _CountingGraph()
        graph.crash_after_claim = n
        crawler = _CountingCrawler(graph, pages_, role=app.role, base_url="")
        ports = Ports(crawler=crawler, perception=FakePerception(), graph=graph)
        try:
            graph_runner.explore(ports, app.seed, app.policy, _config(app), run_id="e5-a")
        except _Crash:
            pass
        claimed_snapshot = set(graph.visited)  # set order is hash-seed dependent; snapshot, don't slice
        claimed_before = len(claimed_snapshot)
        edges_before = len(graph.edges)
        crawler2 = _CountingCrawler(graph, pages_, role=app.role, base_url="")
        second = graph_runner.explore(
            Ports(crawler=crawler2, perception=FakePerception(), graph=graph),
            app.seed, app.policy, _config(app), run_id="e5-b",
        )
        out.append(
            {
                "crash_at_claim": n,
                "claimed_at_crash": claimed_before,
                "edges_at_crash": edges_before,
                "second_run_pairs": second.visited_pairs,
                "second_run_states": second.states,
                "second_run_attempts_of_claimed_pairs": sum(
                    crawler2.frontier_attempts[p] for p in claimed_snapshot
                ),
                "total_edges_after": len(graph.edges),
                "total_states_after": len(graph.states),
            }
        )
    return {
        "positions": len(out),
        "max_second_run_pairs": max(r["second_run_pairs"] for r in out),
        "min_total_edges_after": min(r["total_edges_after"] for r in out),
        "max_total_edges_after": max(r["total_edges_after"] for r in out),
        "full_graph_edges": full_edges,
        "rows": out,
    }


def e5() -> dict[str, object]:
    app = testapp.load("broken-admin")

    result, graph, crawler = _crawl(app)
    base = _counters(result, graph, crawler)
    base_sig = _graph_signature(graph)

    # The framework-free reference loop must agree field for field.
    ref_result, ref_graph, ref_crawler = _crawl(app, loop=reference_explore)
    parity = {
        "counters_equal": _counters(ref_result, ref_graph, ref_crawler) == base,
        "graph_equal": _graph_signature(ref_graph) == base_sig,
    }

    # Discovery-order invariance: shuffle every page's link order, 25 seeded shuffles.
    rng = random.Random(7)
    shuffles = []
    for _ in range(25):
        shuffled = {
            path: dataclasses.replace(
                page, transitions=tuple(rng.sample(page.transitions, len(page.transitions)))
            )
            for path, page in app.pages.items()
        }
        r, g, c = _crawl(app, shuffled)
        shuffles.append(_counters(r, g, c) | {"violation_set_ok": {
            (v.expectation_id, v.clause_type) for v in r.violations} == {
            (v.expectation_id, v.clause_type) for v in result.violations}})
    order = {
        "runs": len(shuffles),
        "revisit_edges_values": sorted({s["revisit_edges_persisted"] for s in shuffles}),
        "tree_edges_values": sorted({s["tree_edges"] for s in shuffles}),
        "states_values": sorted({s["states"] for s in shuffles}),
        "duplicate_frontier_executions_max": max(s["duplicate_frontier_executions"] for s in shuffles),
        "replays_values": sorted({s["replays"] for s in shuffles}),
        "replayed_steps_range": [min(s["replayed_steps"] for s in shuffles),
                                 max(s["replayed_steps"] for s in shuffles)],
        "all_frontier_exhausted": all(s["termination"] == "frontier_exhausted" for s in shuffles),
        "violation_sets_equal": all(s["violation_set_ok"] for s in shuffles),
    }

    # Injected side-effecting action on the login -> dashboard step.
    injected = {}
    for kind in ("submit", "fill"):
        pg = _with_link_kind(app.pages, "/pages/login.html", "Sign in", kind)
        r, g, c = _crawl(app, pg)
        injected[kind] = _counters(r, g, c) | {
            "skip_reasons": sorted({s.reason.split(":")[0] for s in r.skipped}),
            "planted_found": len({(v.expectation_id, v.clause_type) for v in r.violations}
                                 & {(p.expectation_id, p.clause_type) for p in app.expected}),
        }

    resume = {
        "crash_in_action_after_claim__same_crawler": _resume_sweep(app, "act", False, base_sig),
        "crash_in_action_after_claim__fresh_crawler": _resume_sweep(app, "act", True, base_sig),
        "crash_in_edge_write__same_crawler": _resume_sweep(app, "edge", False, base_sig),
        "crash_in_edge_write__fresh_crawler": _resume_sweep(app, "edge", True, base_sig),
        "restart_from_claim_set_only": _claim_set_restart(app),
    }
    return {
        "uninterrupted": base,
        "reference_loop_parity": parity,
        "order_invariance": order,
        "injected_side_effecting_step": injected,
        "resume": resume,
    }


# ---------------------------------------------------------------------------
# E7 -- under-/over-reporting perceivers through the real audit (F-08)
# ---------------------------------------------------------------------------


def _perturb(smap: SemanticUIMap, subjects: set[str], rng: random.Random, p: float, mode: str):
    if mode == "under":  # drop policy-relevant elements and capabilities: S_hat subset of S
        dropped = {t for el in smap.elements for t in el.tags if t in subjects and rng.random() < p}
        elements = tuple(el for el in smap.elements if not (set(el.tags) & dropped))
        caps = tuple(c for c in smap.capabilities if c not in dropped)
        return dataclasses.replace(smap, elements=elements, capabilities=caps)
    present = {t for el in smap.elements for t in el.tags} | set(smap.capabilities)
    spurious = [s for s in sorted(subjects - present) if rng.random() < p]  # S_hat superset of S
    elements = smap.elements + tuple(
        UIElement(role="generic", name=s, tags=(s,), selector=f'[data-spurious="{s}"]')
        for s in spurious
    )
    return dataclasses.replace(smap, elements=elements, capabilities=smap.capabilities + tuple(spurious))


def e7(trials: int = 200, seed: int = 7) -> dict[str, object]:
    app = testapp.load("broken-admin")
    planted = {v.key for v in app.expected}
    subjects = {c.subject for c in (*app.policy.forbidden, *app.policy.required)}
    fake = FakePerception()
    maps = {
        page: fake.analyze(CaptureBundle(url=page, dom=h, ax_tree=None, title=page), app.role)
        for page, h in pages().items()
    }
    out: dict[str, object] = {"trials_per_setting": trials, "seed": seed}
    for mode in ("under", "over"):
        for p in (0.25, 0.5, 1.0):
            rng = random.Random(seed)
            n = 1 if p == 1.0 else trials
            sums = Counter()
            violated = {"under": 0, "over": 0}
            for _ in range(n):
                found: set[Triple] = set()
                for page, smap in maps.items():
                    pert = _perturb(smap, subjects, rng, p, mode)
                    found |= {(page, v.expectation_id, v.clause_type)
                              for v in audit(pert, app.policy)}
                c = _split(found, planted)
                sums.update(c)
                if mode == "under" and (c["fp_F"] or c["fn_R"]):
                    violated["under"] += 1
                if mode == "over" and (c["fn_F"] or c["fp_R"]):
                    violated["over"] += 1
            out[f"{mode}_p{p}"] = {
                "trials": n,
                **{k: round(v / n, 2) for k, v in sorted(sums.items())},
                "trials_violating_prediction": violated[mode],
            }
    out["prediction"] = (
        "under-reporting (S_hat subset of S): fp_F = 0 and fn_R = 0 in every trial; "
        "over-reporting (S_hat superset of S): fn_F = 0 and fp_R = 0 in every trial"
    )
    return out


# ---------------------------------------------------------------------------
# E8 -- fingerprint sensitivity and over-merge tests (F-10)
# ---------------------------------------------------------------------------

_ADMIN_BTN = '<button data-tag="delete-user">Delete user</button>'


def e8() -> dict[str, object]:
    pg = pages()
    admin = pg["/pages/admin.html"]
    dash = pg["/pages/dashboard.html"]

    def fp(url: str, dom: str, ax=None) -> str:
        return fingerprint_bundle(CaptureBundle(url=url, dom=dom, ax_tree=ax))

    base_admin = fp("/pages/admin.html", admin)
    with_number = admin.replace("User administration.", "User administration. Call 5551234567.")
    with_record = admin.replace("User administration.", 'User administration. <i id="user-1234">x</i>')
    with_token_word = admin.replace("User administration.", "User administration. Status: req_approved")
    cases = [
        # (label, mutated DOM, url, ax, expected-by-design: should the id change?)
        ("remove the Delete-user button (visible element removed)", admin.replace(_ADMIN_BTN, ""), None, True),
        ("add a new visible control (Export data)", admin.replace(_ADMIN_BTN, _ADMIN_BTN + '<button data-tag="export-data">Export data</button>'), None, True),
        ("rename a visible label (Delete user -> Remove user)", admin.replace("Delete user", "Remove user"), None, True),
        ("swap the order of two links", admin.replace('<a href="dashboard.html" role="link">Back</a>', "@@A@@").replace('<a href="login.html" role="button" data-tag="logout-button">Log out</a>', '<a href="dashboard.html" role="link">Back</a>').replace("@@A@@", '<a href="login.html" role="button" data-tag="logout-button">Log out</a>'), None, True),
        ("add an element hidden with the hidden attribute", admin.replace(_ADMIN_BTN, _ADMIN_BTN + '<div hidden>x</div>'), None, "debatable"),
        ("edit only an HTML comment", admin.replace("PLANTED V-03", "NOTE"), None, "debatable"),
        ("whitespace-only change", admin.replace("<main id=\"main\">", "<main id=\"main\">\n\n   "), None, False),
        ("change a visible 10+ digit number (phone 5551234567 -> 5559876543)", with_number.replace("5551234567", "5559876543"), None, True),
        ("change a visible word with a token-like prefix (req_approved -> req_denied)", with_token_word.replace("req_approved", "req_denied"), None, True),
        ("change an identifier-like id value (user-1234 -> user-5678)", with_record.replace("user-1234", "user-5678"), None, True),
    ]
    rows = []
    # Pairs for the digit / token / id cases are compared against their own baseline.
    bases = {
        "change a visible 10+ digit number (phone 5551234567 -> 5559876543)": with_number,
        "change a visible word with a token-like prefix (req_approved -> req_denied)": with_token_word,
        "change an identifier-like id value (user-1234 -> user-5678)": with_record,
    }
    for label, mutated, ax, should_change in cases:
        reference = bases.get(label, admin)
        changed = fp("/pages/admin.html", mutated, ax) != fp("/pages/admin.html", reference, ax)
        rows.append({"edit": label, "id_changed": changed,
                     "a_state_change_that_should_split": should_change})
    # URL and AX-only edits.
    rows.append({"edit": "change only the URL query string (?page=1 -> ?page=2)",
                 "id_changed": fp("/pages/admin.html?page=1", admin) != fp("/pages/admin.html?page=2", admin),
                 "a_state_change_that_should_split": True})
    ax1 = {"role": "document", "name": "Admin", "children": [{"role": "button", "name": "Delete user"}]}
    ax2 = {"role": "document", "name": "Admin", "children": [{"role": "button", "name": "Remove user"}]}
    rows.append({"edit": "change only an accessible name in the AX tree",
                 "id_changed": fp("/pages/admin.html", admin, ax1) != fp("/pages/admin.html", admin, ax2),
                 "a_state_change_that_should_split": True})
    return {
        "base_page": "/pages/admin.html",
        "n_edits": len(rows),
        "edits": rows,
        "not_detected": [r["edit"] for r in rows if not r["id_changed"]],
        "detected": sum(1 for r in rows if r["id_changed"]),
    }


# ---------------------------------------------------------------------------
# E9 -- mutants of broken-admin (in memory) and a hand-written invariant baseline
# ---------------------------------------------------------------------------

_SNIPPETS = {
    "e-admin-link": '<a href="admin.html" role="link" data-tag="admin-link">Admin</a>',
    "e-delete-user": '<button data-tag="delete-user">Delete user</button>',
    "e-debug-panel": '<section data-tag="debug-panel"><h2>Debug</h2></section>',
}
_SUBJECT_OF = {"e-admin-link": "admin-link", "e-delete-user": "delete-user", "e-debug-panel": "debug-panel"}
_SKIP = '<a href="#main" data-tag="skip-to-content" class="skip">Skip to content</a>'
_PLANTED_ANCHOR = {  # how to delete each originally planted forbidden element
    ("/pages/dashboard.html", "e-admin-link"): '<a href="admin.html" role="link" data-tag="admin-link">Admin</a>',
    ("/pages/reports.html", "e-debug-panel"): '<section data-tag="debug-panel">\n      <h2>Debug</h2>\n      <pre>build=prod flags=verbose</pre>\n    </section>',
    ("/pages/admin.html", "e-delete-user"): _ADMIN_BTN,
}


class _TagCollector(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: set[str] = set()

    def handle_starttag(self, tag, attrs):  # type: ignore[no-untyped-def]
        for name, value in attrs:
            if name == "data-tag" and value:
                self.tags.add(value)


def dom_invariant_baseline(page: str, html_text: str) -> set[Triple]:
    """OUR OWN hand-written per-page invariant checker for the four broken-admin
    clauses. It is not Crawljax and not ATUSA; it only mimics what an
    ATUSA-style invariant per clause would assert. It hard-codes the guest role."""
    collector = _TagCollector()
    collector.feed(html_text)
    t = collector.tags
    found: set[Triple] = set()
    if "admin-link" in t:
        found.add((page, "e-admin-link", "forbidden_present"))
    if "delete-user" in t:
        found.add((page, "e-delete-user", "forbidden_present"))
    if "debug-panel" in t:
        found.add((page, "e-debug-panel", "forbidden_present"))
    if "skip-to-content" not in t:
        found.add((page, "e-skip-link", "required_absent"))
    return found


def _apply(op: tuple, pg: dict[str, str], ledger: set[Triple]) -> bool:
    kind, page, clause = op
    text = pg[page]
    if kind == "add_forbidden":
        if _SUBJECT_OF[clause] in text:
            return False
        pg[page] = text.replace('<main id="main">', '<main id="main">\n    ' + _SNIPPETS[clause], 1)
        ledger.add((page, clause, "forbidden_present"))
    elif kind == "remove_forbidden":
        anchor = _PLANTED_ANCHOR.get((page, clause))
        if anchor is None or anchor not in text:
            return False
        pg[page] = text.replace(anchor, "", 1)
        ledger.discard((page, clause, "forbidden_present"))
    elif kind == "remove_skip":
        if _SKIP not in text:
            return False
        pg[page] = text.replace(_SKIP, "", 1)
        ledger.add((page, "e-skip-link", "required_absent"))
    elif kind == "add_skip":
        if "skip-to-content" in text:
            return False
        pg[page] = text.replace('<main id="main">', _SKIP + '\n  <main id="main">', 1)
        ledger.discard((page, "e-skip-link", "required_absent"))
    assert pg[page] != text, op
    return True


def _mutant_ops(pg0: dict[str, str]) -> list[tuple]:
    ops: list[tuple] = []
    for (page, clause) in _PLANTED_ANCHOR:
        ops.append(("remove_forbidden", page, clause))
    for page in pg0:
        for clause in _SNIPPETS:
            if _SUBJECT_OF[clause] not in pg0[page]:
                ops.append(("add_forbidden", page, clause))
        ops.append(("remove_skip", page, "e-skip-link"))
        ops.append(("add_skip", page, "e-skip-link"))
    return ops


def e9(compound: int = 40, seed: int = 7) -> dict[str, object]:
    app = testapp.load("broken-admin")
    base_pg = pages()
    base_truth = {v.key for v in app.expected}
    ops_all = _mutant_ops(base_pg)

    mutants: list[tuple[str, dict[str, str], set[Triple]]] = []
    for op in ops_all:  # exhaustive single-operator mutants (those that apply)
        pg, ledger = dict(base_pg), set(base_truth)
        if _apply(op, pg, ledger):
            mutants.append(("single", pg, ledger))
    n_single = len(mutants)
    rng = random.Random(seed)
    while len(mutants) < n_single + compound:  # seeded compound mutants of 2-3 operators
        pg, ledger = dict(base_pg), set(base_truth)
        applied = 0
        for op in rng.sample(ops_all, rng.choice((2, 3))):
            applied += _apply(op, pg, ledger)
        if applied >= 2:
            mutants.append(("compound", pg, ledger))

    arms = {
        "oracle_maps_real_audit": lambda pg: _audit_with("oracle_maps_real_audit", pg, app.policy, app.role),
        "dom_channel_real_audit": lambda pg: _audit_with("dom_channel_real_audit", pg, app.policy, app.role),
        "own_dom_invariant_baseline": lambda pg: set().union(*(dom_invariant_baseline(p, h) for p, h in pg.items())),
    }
    agg = {name: Counter() for name in arms}
    exact = {name: 0 for name in arms}
    for _, pg, ledger in mutants:
        for name, run in arms.items():
            found = run(pg)
            agg[name].update(_split(found, ledger))
            exact[name] += found == ledger

    # Vocabulary-rename mutants: the defect stays, the data-tag spelling changes.
    renames = {}
    for old, new in (("admin-link", "admin_link"), ("debug-panel", "debug_panel"),
                     ("skip-to-content", "skip_to_content")):
        pg = {p: h.replace(f'data-tag="{old}"', f'data-tag="{new}"') for p, h in base_pg.items()}
        renames[f"{old}->{new}"] = {
            name: {k: score(run(pg), base_truth)[k] for k in ("tp", "fp", "fn", "precision", "recall")}
            for name, run in arms.items()
        }

    # Role scoping: run the same policy as role "admin"; guest-scoped clauses must drop out.
    admin_expected = {t for t in base_truth if t[1] in ("e-debug-panel", "e-skip-link")}
    admin_found = _audit_with("oracle_maps_real_audit", base_pg, app.policy, "admin")

    baseline_src = inspect.getsource(dom_invariant_baseline)
    return {
        "mutants_single": n_single,
        "mutants_compound": compound,
        "mutants_total": len(mutants),
        "ops_available": len(ops_all),
        "pooled_counts": {name: dict(sorted(c.items())) for name, c in agg.items()},
        "mutants_with_exact_match": exact,
        "vocabulary_rename_scores": renames,
        "role_scope_check_admin": {
            "expected": sorted(map(list, admin_expected)),
            "found": sorted(map(list, admin_found)),
            "match": admin_found == admin_expected,
        },
        "spec_effort": {
            "engine_policy_clauses": len(app.policy.forbidden) + len(app.policy.required),
            "baseline_function_source_lines": len(baseline_src.strip().splitlines()),
            "baseline_per_clause_branches": 4,
            "note": "baseline is our own re-implementation; it hard-codes role guest and the data-tag spelling",
        },
    }


# ===========================================================================
# Revision 3 additions (E10-E11, key map). E1-E9 code paths are unchanged.
# ===========================================================================

from xml.etree import ElementTree as ET  # noqa: E402

_VOID = {"meta", "input", "br", "img", "link", "hr", "area", "base", "col", "source", "wbr"}


class _ETBuilder(html.parser.HTMLParser):
    """Parse (possibly not well-formed) HTML into an ElementTree, stdlib only."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = ET.Element("root")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):  # type: ignore[no-untyped-def]
        el = ET.SubElement(self.stack[-1], tag, {k: (v or "") for k, v in attrs})
        if tag not in _VOID:
            self.stack.append(el)

    def handle_endtag(self, tag):  # type: ignore[no-untyped-def]
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):  # type: ignore[no-untyped-def]
        top = self.stack[-1]
        if len(top):
            last = top[-1]
            last.tail = (last.tail or "") + data
        else:
            top.text = (top.text or "") + data


# Invariants over element types, link targets and visible text, written in the XPath
# subset that the standard library's ElementTree supports. They deliberately do NOT read
# data-tag. The authors knew the fixture's labels when writing them; that they were
# written before the first run on stripped pages is an authorial statement the artifact
# cannot evidence. Our own re-implementation, not Crawljax/ATUSA.
XPATH_INVARIANTS = (
    ("e-admin-link", "forbidden_present", ".//a[.='Admin']"),
    ("e-debug-panel", "forbidden_present", ".//section[h2='Debug']"),
    ("e-delete-user", "forbidden_present", ".//button[.='Delete user']"),
    ("e-skip-link", "required_absent", ".//a[@href='#main'][.='Skip to content']"),
)


def xpath_baseline(page: str, html_text: str) -> set[Triple]:
    b = _ETBuilder()
    b.feed(html_text)
    found: set[Triple] = set()
    for clause, kind, query in XPATH_INVARIANTS:
        hit = bool(b.root.findall(query))
        if (kind == "forbidden_present" and hit) or (kind == "required_absent" and not hit):
            found.add((page, clause, kind))
    return found


def _strip_tags(pg: dict[str, str]) -> dict[str, str]:
    return {p: re.sub(r'\sdata-tag="[^"]*"', "", h) for p, h in pg.items()}


def _mutants_with_family(app) -> list[tuple[str, dict[str, str], set[Triple]]]:
    """Same mutants as e9() (same operators, same seed), labelled by family."""
    base_pg = pages()
    base_truth = {v.key for v in app.expected}
    ops_all = _mutant_ops(base_pg)
    out = []
    for op in ops_all:
        pg, ledger = dict(base_pg), set(base_truth)
        if _apply(op, pg, ledger):
            fam = {"remove_forbidden": "remove planted forbidden element",
                   "remove_skip": "remove skip link", "add_skip": "restore skip link"}.get(op[0])
            out.append((fam or f"add forbidden element: {_SUBJECT_OF[op[2]]}", pg, ledger))
    rng = random.Random(7)
    n_single = len(out)
    while len(out) < n_single + 40:
        pg, ledger = dict(base_pg), set(base_truth)
        applied = 0
        for op in rng.sample(ops_all, rng.choice((2, 3))):
            applied += _apply(op, pg, ledger)
        if applied >= 2:
            out.append(("compound (2-3 operations)", pg, ledger))
    # Visible-label renames: the defects stay, the visible text changes.
    renames = {
        "label rename: Admin -> Administration": [(">Admin</a>", ">Administration</a>")],
        "label rename: Delete user -> Remove account": [(">Delete user</button>", ">Remove account</button>")],
        "label rename: Skip to content -> Skip navigation": [(">Skip to content</a>", ">Skip navigation</a>")],
    }
    renames["label rename: all three"] = [r for v in list(renames.values()) for r in v]
    for fam, subs in renames.items():
        pg = dict(base_pg)
        for old, new in subs:
            changed = {p: h.replace(old, new) for p, h in pg.items()}
            assert changed != pg, old
            pg = changed
        out.append(("label rename (text changed, defects kept)", pg, set(base_truth)))
    return out


def e10() -> dict[str, object]:
    app = testapp.load("broken-admin")
    base_pg = pages()
    truth = {v.key for v in app.expected}

    def a2(pg): return _audit_with("oracle_maps_real_audit", pg, app.policy, app.role)
    def a3(pg): return _audit_with("dom_channel_real_audit", pg, app.policy, app.role)
    def a6(pg): return set().union(*(dom_invariant_baseline(p, h) for p, h in pg.items()))
    def a8(pg): return set().union(*(xpath_baseline(p, h) for p, h in pg.items()))
    arms = {
        "A2_tag_oracle_production_audit": (a2, False),
        "A3_dom_channel": (a3, False),
        "A6_tag_script": (a6, False),
        "A8_xpath_roles_text": (a8, False),
        "A2_on_stripped_copy": (a2, True),
        "A3_on_stripped_copy": (a3, True),
        "A8_on_stripped_copy": (a8, True),
    }
    base = {
        name: score((fn(_strip_tags(base_pg)) if stripped else fn(base_pg)), truth)
        for name, (fn, stripped) in arms.items()
    }
    fams: dict[str, dict[str, object]] = {}
    for fam, pg, ledger in _mutants_with_family(app):
        entry = fams.setdefault(fam, {"mutants": 0, "arms": {n: Counter() for n in arms}, "exact": Counter()})
        entry["mutants"] += 1  # type: ignore[operator]
        for name, (fn, stripped) in arms.items():
            found = fn(_strip_tags(pg) if stripped else pg)
            entry["arms"][name].update(_split(found, ledger))  # type: ignore[index]
            entry["exact"][name] += found == ledger  # type: ignore[index]
    out_f = {
        fam: {
            "mutants": e["mutants"],
            "arms": {n: dict(sorted(c.items())) for n, c in e["arms"].items()},  # type: ignore[union-attr]
            "exact_match": dict(e["exact"]),  # type: ignore[arg-type]
        }
        for fam, e in fams.items()
    }
    src = inspect.getsource(xpath_baseline)
    return {
        "fixture_scores": base,
        "xpath_invariants": [list(t) for t in XPATH_INVARIANTS],
        "xpath_spec_lines": len(src.strip().splitlines()) + len(XPATH_INVARIANTS),
        "families": out_f,
        "total_mutants": sum(f["mutants"] for f in out_f.values()),
        "note": "A8 is our own XPath-subset re-implementation reading element types, link targets and visible text; not ATUSA or Crawljax; the authors knew the labels; ordering of writing vs. first run is an authorial statement the artifact cannot evidence",
    }


def e11() -> dict[str, object]:
    """Two-seed-action fixture variant (in memory): index gains a second link."""
    app = testapp.load("broken-admin")
    pg = dict(app.pages)
    pg["/index.html"] = dataclasses.replace(
        pg["/index.html"],
        transitions=(*pg["/index.html"].transitions, FakeLink(name="About", to="/pages/about.html")),
    )
    pg["/pages/about.html"] = FakePage(
        title="About", elements=("skip-to-content",),
        transitions=(FakeLink(name="Home", to="/index.html"),),
    )
    result, graph, crawler = _crawl(app, pg)
    base = _counters(result, graph, crawler)
    sig = _graph_signature(graph)
    n = result.visited_pairs
    resume = {
        "crash_in_action_after_claim__same_crawler": _resume_sweep(app, "act", False, sig, pg, n),
        "crash_in_edge_write__same_crawler": _resume_sweep(app, "edge", False, sig, pg, n),
        "restart_from_claim_set_only": _claim_set_restart(app, pg, n, len(graph.edges)),
    }
    for v in resume.values():
        v.pop("rows", None)
    restart_rows = _claim_set_restart(app, pg, n, len(graph.edges))["rows"]
    return {
        "seed_actions": 2,
        "uninterrupted": base,
        "resume_summary": resume,
        "restart_rows": restart_rows,
    }


KEY_MAP = {
    "RQ1a": ["E1_E3.E1_oracle_perception", "E6_real_audit_on_oracle_maps"],
    "RQ1b": ["E5_loop", "E11_two_seed_variant"],
    "RQ2": ["E1_E3.E1_deterministic_dom_perception", "E1_E3.E4_deterministic_lexical_grounding",
            "E7_perturbed_perceivers"],
    "RQ3": ["E1_E3.E3_oracle_intersection_only", "E6_real_audit_on_oracle_maps"],
    "RQ4": ["E2", "E8_fingerprint_edits"],
    "RQ5": ["E9_mutants_and_baseline", "E10_xpath_baseline", "E12_extra_apps",
            "E13_label_rename_variants", "E14_generated_apps"],
}



# ---------------------------------------------------------------------------
# E12 -- three further in-repo apps (rev. 4). Policy and ground truth below were
# derived from each app's README sentence first (ordering is an authorial statement the artifact cannot evidence) before any arm
# was run, and are recorded in the output. Same-project authorship; tiny,
# single-defect, unannotated (no data-tag). Nothing under test-apps/ is modified.
# ---------------------------------------------------------------------------

EXTRA_APP_DERIVATION = {
    "broken-rbac-demo": {
        "readme_sentence": "Guest users must never see administrative links, nor should they be able to access administrative pages.",
        "role": "guest",
        "clauses": [("e-admin-link", "admin-link", "forbidden_present")],
        "ground_truth": [("dashboard.html", "e-admin-link", "forbidden_present")],
        "derivation_notes": "README names the dashboard sidebar link 'Admin Dashboard' as the UI violation. Reaching admin.html is described as a backend-enforcement violation, which an element-level clause cannot express, so it yields no triple. The README is silent about links on other pages; any other finding is scored as a false positive and discussed.",
    },
    "missing-consent-demo": {
        "readme_sentence": "Every page on first load must display a cookie consent banner or modal, regardless of user role.",
        "role": "guest",
        "clauses": [("e-cookie-consent", "cookie-consent-banner", "required_absent")],
        "ground_truth": [("index.html", "e-cookie-consent", "required_absent")],
        "derivation_notes": "One page, one required clause, banner documented as absent.",
    },
    "broken-feature-flag-demo": {
        "readme_sentence": "Free Tier users must never see or interact with Premium features, specifically the Export Data functionality (policy text also names an Advanced Analytics panel).",
        "role": "free-tier",
        "clauses": [("e-export-data", "export-data-button", "forbidden_present"),
                    ("e-advanced-analytics", "advanced-analytics-panel", "forbidden_present")],
        "ground_truth": [("index.html", "e-export-data", "forbidden_present")],
        "derivation_notes": "README documents only the Export Data button as the violation. If the page also shows an analytics panel, that finding is README-ambiguous: it is scored as a false positive under this README-derived truth and flagged; a truth variant that includes it is also reported.",
    },
}


EXTRA_XPATH = {  # written after reading the scored HTML (in-sample); not edited after the arms were run
    "broken-rbac-demo": [
        ("e-admin-link", "forbidden_present", [".//a[@href='admin.html']"]),
    ],
    "missing-consent-demo": [
        ("e-cookie-consent", "required_absent",
         [".//*[@role='dialog']", ".//*[@id='cookie-banner']", ".//*[@id='cookie-consent']",
          ".//button[.='Accept']", ".//button[.='Accept all']"]),
    ],
    "broken-feature-flag-demo": [
        ("e-export-data", "forbidden_present", [".//button[.='Export Data']"]),
        ("e-advanced-analytics", "forbidden_present", [".//h2[.='Advanced Analytics']"]),
    ],
}
# Post hoc, exploratory (like A4): subjects respelled in the shipped tagger's own
# vocabulary, to ask whether the DOM channel works once the spelling matches.
EXTRA_POSTHOC_SUBJECTS = {
    "broken-rbac-demo": {"e-admin-link": "admin"},
    "broken-feature-flag-demo": {"e-export-data": "export-data"},
}


def _extra_pages(app: str) -> dict[str, str]:
    d = ROOT / "test-apps" / app
    return {p.name: p.read_text(encoding="utf-8", errors="replace") for p in sorted(d.glob("*.html"))}


def _xpath_extra(app: str, pg: dict[str, str]) -> set[Triple]:
    found: set[Triple] = set()
    for page, text in pg.items():
        b = _ETBuilder()
        b.feed(text)
        for clause, kind, queries in EXTRA_XPATH[app]:
            hit = any(b.root.findall(q) for q in queries)
            if (kind == "forbidden_present" and hit) or (kind == "required_absent" and not hit):
                found.add((page, clause, kind))
    return found


def _dom_extra(app: str, pg: dict[str, str], subjects: dict[str, str] | None = None) -> set[Triple]:
    der = EXTRA_APP_DERIVATION[app]
    nodes_f, nodes_r = [], []
    for cid, subj, kind in der["clauses"]:
        subj = (subjects or {}).get(cid, subj)
        node = ExpectationNode(expectation_id=cid,
                               polarity="must_not_exist" if kind == "forbidden_present" else "must_exist",
                               subject=subj, roles=(), source_text=der["readme_sentence"])
        (nodes_f if kind == "forbidden_present" else nodes_r).append(node)
    policy = ExpectationSet(forbidden=tuple(nodes_f), required=tuple(nodes_r))
    found: set[Triple] = set()
    for page, text in pg.items():
        bundle = CaptureBundle(url=page, dom=text, ax_tree=None, title=page)
        smap = build_semantic_map(bundle, der["role"], state_id=page)
        found |= {(page, v.expectation_id, v.clause_type) for v in audit(smap, policy)}
    return found


def e12() -> dict[str, object]:
    out: dict[str, object] = {}
    for app, der in EXTRA_APP_DERIVATION.items():
        pg = _extra_pages(app)
        truth = {tuple(t) for t in der["ground_truth"]}
        arms = {
            "A3_dom_channel_readme_subjects": _dom_extra(app, pg),
            "A8_xpath_in_sample": _xpath_extra(app, pg),
        }
        if app in EXTRA_POSTHOC_SUBJECTS:
            arms["A3_posthoc_tagger_vocabulary_subjects"] = _dom_extra(app, pg, EXTRA_POSTHOC_SUBJECTS[app])
        out[app] = {
            "derivation": {**{k: v for k, v in der.items() if k != "clauses" and k != "ground_truth"},
                           "clauses": [list(c) for c in der["clauses"]],
                           "ground_truth": [list(t) for t in der["ground_truth"]]},
            "pages": sorted(pg),
            "xpath_invariants": [[c, k, q] for c, k, q in EXTRA_XPATH[app]],
            "arms": {n: score(f, truth) for n, f in arms.items()},
        }
    # Control for the single required clause: the same page with a banner inserted in
    # memory. Truth: no violation. A clause that fires here too is vacuous.
    consent = _extra_pages("missing-consent-demo")
    banner = ('<div id="cookie-banner" role="dialog">We use cookies. '
              '<button>Accept</button></div>')
    with_banner = {p: h.replace("<body>", "<body>\n" + banner, 1) for p, h in consent.items()}
    assert with_banner != consent
    out["missing-consent-demo"]["control_with_banner_inserted"] = {
        "truth": [],
        "A3_dom_channel_readme_subjects": sorted(map(list, _dom_extra("missing-consent-demo", with_banner))),
        "A8_xpath_in_sample": sorted(map(list, _xpath_extra("missing-consent-demo", with_banner))),
        "note": "A8's queries include the inserted markup by construction; the informative part is whether A3 can ever stop firing",
    }
    # Truth variant including the README-named Advanced Analytics panel (feature-flag app).
    ff = "broken-feature-flag-demo"
    base_truth = {tuple(t) for t in EXTRA_APP_DERIVATION[ff]["ground_truth"]}
    variant_truth = base_truth | {("index.html", "e-advanced-analytics", "forbidden_present")}
    pg_ff = _extra_pages(ff)
    out[ff]["truth_variant_with_named_analytics_panel"] = {
        "truth": sorted(map(list, variant_truth)),
        "A3_dom_channel_readme_subjects": score(_dom_extra(ff, pg_ff), variant_truth),
        "A8_xpath_in_sample": score(_xpath_extra(ff, pg_ff), variant_truth),
        "note": "A8's exact-heading query misses the analytics panel, so A8 is 1 of 2 under this truth",
    }
    out["missing-consent-demo"]["A8_row_discriminating"] = False
    out["missing-consent-demo"]["A8_row_note"] = ("Any absence-based clause scores 1/1 on a page without a banner, so this row "
                                                  "does not discriminate between arms for A8; the control is circular for A8.")
    out["disclosure"] = ("Same-project apps; tiny, single-defect, unannotated (no data-tag). Static HTML audited "
                         "per page; no crawl, browser or service. Ground truth derived from README sentences "
                         "first; ordering is an authorial statement the artifact cannot evidence. The XPath "
                         "invariants were written after reading the scored HTML, so A8 results here are "
                         "in-sample. Nothing under test-apps/ is modified.")
    return out



def e13() -> dict[str, object]:
    """Label renames reported per variant (the 'all three' variant double-counts)."""
    app = testapp.load("broken-admin")
    base_pg = pages()
    truth = {v.key for v in app.expected}
    variants = {
        "Admin -> Administration": [(">Admin</a>", ">Administration</a>")],
        "Delete user -> Remove account": [(">Delete user</button>", ">Remove account</button>")],
        "Skip to content -> Skip navigation": [(">Skip to content</a>", ">Skip navigation</a>")],
    }
    variants["all three together"] = [r for v in list(variants.values()) for r in v]
    arms = {
        "A2_tag_oracle_production_audit": lambda pg: _audit_with("oracle_maps_real_audit", pg, app.policy, app.role),
        "A3_dom_channel": lambda pg: _audit_with("dom_channel_real_audit", pg, app.policy, app.role),
        "A6_tag_script": lambda pg: set().union(*(dom_invariant_baseline(p, h) for p, h in pg.items())),
        "A8_xpath": lambda pg: set().union(*(xpath_baseline(p, h) for p, h in pg.items())),
    }
    out: dict[str, object] = {}
    for name, subs in variants.items():
        pg = dict(base_pg)
        for old, new in subs:
            pg = {p: h.replace(old, new) for p, h in pg.items()}
        out[name] = {a: _split(fn(pg), truth) for a, fn in arms.items()}
    src = inspect.getsource(_ETBuilder)
    out["parser_helper_lines"] = len(src.strip().splitlines())
    return out



# ===========================================================================
# E14 (rev. 5): four generated, unannotated apps under
# tests/fixtures/orchestrator/paper-subjects/ (read only). Protocol, in order:
#  1. invariants written from policy.txt / policy.expected.json only, saved in
#     e14_invariants.py with its sha256 and a UTC timestamp in e14_invariants.sha256
#     (self-attested ordering; the artifact cannot prove it);
#  2. A3 subjects taken verbatim from policy.expected.json (no tuning);
#  3. only then HTML and ground_truth.json were opened and both arms run.
# Invariants were not edited after results were seen.
# ===========================================================================

E14_ROOT = ROOT / "tests" / "fixtures" / "orchestrator" / "paper-subjects"
E14_APPS = ("shop-hub", "med-clinic", "hr-suite", "config-portal")
_DOUBLE_NEG = re.compile(r"must not fail|never be unable|must not be unable|not be unable", re.I)
_STOP = {"link", "button", "panel", "page", "other", "information", "option", "options"}


def _e14_policy(app: str):
    raw = json.loads((E14_ROOT / app / "policy.expected.json").read_text(encoding="utf-8"))
    def nodes(items, polarity):
        return tuple(ExpectationNode(expectation_id=i["expectation_id"], polarity=polarity,
                                     subject=i["subject"], roles=tuple(i["roles"]),
                                     source_text=i["source_text"]) for i in items)
    return ExpectationSet(forbidden=nodes(raw["forbidden"], "must_not_exist"),
                          required=nodes(raw["required"], "must_exist"))


def _e14_runs(policy) -> list[str]:
    roles = sorted({r for c in (*policy.forbidden, *policy.required) for r in c.roles})
    return roles or ["user"]


def _e14_a3(policy, pg: dict[str, str]) -> set[Triple]:
    found: set[Triple] = set()
    for role in _e14_runs(policy):
        for page, text in pg.items():
            bundle = CaptureBundle(url=page, dom=text, ax_tree=None, title=page)
            smap = build_semantic_map(bundle, role, state_id=page)
            found |= {(page, v.expectation_id, v.clause_type) for v in audit(smap, policy)}
    return found


def _e14_a8(app: str, policy, pg: dict[str, str]) -> set[Triple]:
    from e14_invariants import INVARIANTS  # noqa: PLC0415
    roles_of = {c.expectation_id: c.roles for c in (*policy.forbidden, *policy.required)}
    found: set[Triple] = set()
    trees = {}
    for page, text in pg.items():
        b = _ETBuilder()
        b.feed(text)
        trees[page] = b.root
    for role in _e14_runs(policy):
        for cid, kind, scope, queries in INVARIANTS[app]:
            if roles_of[cid] and role not in roles_of[cid]:
                continue
            for page, root in trees.items():
                if scope == "all_but_login" and page == "login.html":
                    continue
                if scope not in ("all", "all_but_login") and page != scope:
                    continue
                hit = any(root.findall(q) for q in queries)
                if (kind == "forbidden_present" and hit) or (kind == "required_absent" and not hit):
                    found.add((page, cid, kind))
    return found


def e14() -> dict[str, object]:
    import hashlib as _h  # noqa: PLC0415
    here = Path(__file__).resolve().parent
    sha_file = (here / "e14_invariants.sha256").read_text(encoding="utf-8").split()
    current = _h.sha256((here / "e14_invariants.py").read_bytes()).hexdigest()
    out: dict[str, object] = {
        "protocol": {
            "invariants_file": "docs/report/experiments/e14_invariants.py",
            "sha256_recorded_at_creation": sha_file[0],
            "sha256_now": current,
            "unchanged_since_recorded": sha_file[0] == current,
            "utc_timestamp_recorded_at_creation": sha_file[2] if len(sha_file) > 2 else sha_file[-1],
            "ordering": ("Self-attested: invariants were written from policy.txt and policy.expected.json "
                         "(and directory file names) before any .html, ground_truth.json or README.md of these "
                         "apps was opened. The artifact cannot prove this; the hash and timestamp only show the "
                         "invariants file did not change afterwards."),
            "a3_subjects": "verbatim 'subject' strings of policy.expected.json, no tuning",
            "provenance": ("Same-project, AI-generated (fixture-forge), unannotated (no data-tag); they add "
                           "variety and a more blind protocol, not independence."),
            "scoring": ("TP = found triple in ground_truth violations. FP = found triple on a page listed in "
                        "clean_pages for that clause. unlisted = found on a page in neither list (reported, not "
                        "counted as FP). FN = ground-truth violation not found. decoy_adjacent = FP on a clean page "
                        "whose visible text contains a content word (>=4 letters, not in a small stoplist) of the "
                        "clause subject (mechanical definition fixed before running)."),
        },
        "apps": {},
    }
    totals = {a: {"forbidden_present": Counter(), "required_absent": Counter()} for a in ("A3", "A8")}
    for app in E14_APPS:
        policy = _e14_policy(app)
        pg = {p.name: p.read_text(encoding="utf-8", errors="replace") for p in sorted((E14_ROOT / app).glob("*.html"))}
        gt = json.loads((E14_ROOT / app / "ground_truth.json").read_text(encoding="utf-8"))
        truth = {(v["page"], v["expectation_id"], v["clause_type"]) for v in gt["violations"]}
        clean = {(pg_name, cid) for cid, pages_ in gt["clean_pages"].items() for pg_name in pages_}
        kinds = {c.expectation_id: ("forbidden_present" if c.polarity == "must_not_exist" else "required_absent")
                 for c in (*policy.forbidden, *policy.required)}
        subj = {c.expectation_id: c.subject for c in (*policy.forbidden, *policy.required)}
        double_neg = sorted(c.expectation_id for c in (*policy.forbidden, *policy.required)
                            if _DOUBLE_NEG.search(c.source_text))
        arms = {"A3": _e14_a3(policy, pg), "A8": _e14_a8(app, policy, pg)}
        res: dict[str, object] = {}
        for arm, found in arms.items():
            clauses = {}
            for cid, kind in kinds.items():
                f = {t for t in found if t[1] == cid}
                t_ = {t for t in truth if t[1] == cid}
                fp = {t for t in f if (t[0], cid) in clean and t not in t_}
                unl = {t for t in f if t not in t_ and t not in fp}
                words = {w for w in re.findall(r"[a-z]{4,}", subj[cid].lower()) if w not in _STOP}
                decoy = {t for t in fp if any(w in re.sub(r"<[^>]+>", " ", pg[t[0]]).lower() for w in words)}
                entry = {"kind": kind, "tp": len(f & t_), "fn": len(t_ - f), "fp": len(fp),
                         "decoy_adjacent_fp": len(decoy), "unlisted_hits": len(unl),
                         "found_pages": sorted(t[0] for t in f), "truth_pages": sorted(t[0] for t in t_),
                         "missed": sorted(t[0] for t in t_ - f), "fp_pages": sorted(t[0] for t in fp),
                         "decoy_adjacent_fp_pages": sorted(t[0] for t in decoy),
                         "unlisted_pages": sorted(t[0] for t in unl),
                         "double_negation_clause": cid in double_neg}
                clauses[cid] = entry
                for k in ("tp", "fn", "fp", "decoy_adjacent_fp", "unlisted_hits"):
                    totals[arm][kind][k] += entry[k]
            res[arm] = clauses
        out["apps"][app] = {
            "pages": sorted(pg), "roles_run": _e14_runs(policy), "double_negation_clauses": double_neg,
            "truth": sorted(map(list, truth)), "arms": res,
        }
    out["totals_per_polarity"] = {a: {k: dict(c) for k, c in v.items()} for a, v in totals.items()}
    return out



def _meta() -> dict[str, object]:
    def git(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()

    return {
        "python": platform.python_version(),
        "platform": platform.system() + " " + platform.machine(),
        "langgraph": metadata.version("langgraph"),
        "git_head": git("rev-parse", "HEAD"),
        "code_tree_clean_vs_head": git("status", "--porcelain", "--", "apps", "tests", "test-apps",
                                       "services", "infra") == "",
        "seed": 7,
        "note": "E1-E4 read page HTML from test-apps/broken-admin; E5 uses the in-memory fakes; no browser, no network, no Neo4j/Redis",
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    results = {
        "E1_E3": e1_e3(),
        "E2": e2(),
        "E5_loop": e5(),
        "E6_real_audit_on_oracle_maps": e6(),
        "E7_perturbed_perceivers": e7(),
        "E8_fingerprint_edits": e8(),
        "E9_mutants_and_baseline": e9(),
        "meta": _meta(),
        "E10_xpath_baseline": e10(),
        "E11_two_seed_variant": e11(),
        "E12_extra_apps": e12(),
        "E13_label_rename_variants": e13(),
        "E14_generated_apps": e14(),
        "key_map": KEY_MAP,
    }
    (OUT / "experiments.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
