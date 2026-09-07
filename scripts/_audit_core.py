"""Shared engine for the two StateScout demo consoles (audit_app / local_audit_app).

Real stack, ~60% of the finished system:
  - PlaywrightCrawler (Track A) — real headless Chromium, selector fix included
  - VLMPerception (Track C) — real Gemini vision + deterministic negation engine
  - Neo4jGraph (Track D) — real Neo4j + Redis
  - graph_runner.explore (Track B) — the real BFS loop

Local stand-ins, all surfaced in the UI:
  - ADR-001 C-3: analyze() has no state_id param, so this overwrites SemanticUIMap
    .state_id with the real fingerprint (the fix proposed as ADR resolution 1)
  - NL policy -> ExpectationSet: a small Gemini-backed parser standing in for
    Track B's unbuilt FR-04 parser
  - gemini.py hardcodes gemini-3.6-flash (20 req/day free tier) and ignores
    GEMINI_MODEL — defaulted here to a flash-lite model with a larger quota
"""

from __future__ import annotations

import base64
import dataclasses
import http.server
import json
import os
import pathlib
import socket
import threading
import traceback
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

from apps.agent.contracts import Action, CaptureBundle, ExpectationNode, ExpectationSet, NavigationError
from apps.agent.graph.cache import VisitedCache
from apps.agent.graph.fingerprint import fingerprint_bundle
from apps.agent.graph.graph_store import GraphStore
from apps.agent.graph.neo4j_graph import Neo4jGraph
from apps.agent.negation.audit import audit as negation_audit
from apps.agent.orchestrator import graph_runner
from apps.agent.orchestrator.config import OrchestratorConfig
from apps.agent.orchestrator.deps import Ports
from apps.agent.perception import gemini as _gemini_mod
from apps.agent.perception.gemini import VLMPerception
from apps.agent.perception.semantic_map import build_semantic_map

# Load <repo-root>/.env into the process environment (keys already set win), so
# the console works no matter how it was launched.
def _load_dotenv() -> None:
    env_path = pathlib.Path(__file__).resolve().parent.parent / ".env"
    if not env_path.is_file():
        return
    for raw in env_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        os.environ.setdefault(key, val.strip().strip("\"").strip("'"))


_load_dotenv()

# gemini.py hardcodes gemini-3.6-flash (a tiny 20/day free-tier quota). Pin a
# flash-lite model instead (bigger quota, still vision-capable). Not read from
# GEMINI_MODEL on purpose: the gemini-2.x names 404 on this API.
_gemini_mod._MODEL = "gemini-3.5-flash-lite"

SHOT_DIR = "/tmp/statescout-demo-shots"

# ---------------------------------------------------------------------------
# NL policy -> ExpectationSet  (stand-in for Track B's FR-04 parser)
# ---------------------------------------------------------------------------

CAPS = ["admin-access", "debug-access", "export-data", "delete-user", "logout", "login"]

_KEYWORDS = {
    "admin-access": ("admin", "administrator", "admin panel", "admin area"),
    "debug-access": ("debug", "developer tools", "debug console", "diagnostics"),
    "export-data": ("export", "download all", "download records", "bulk export", "download data"),
    "delete-user": ("delete user", "remove user", "delete account", "destroy", "wipe"),
    "logout": ("logout", "log out", "sign out"),
    "login": ("login", "log in", "sign in"),
}
_FORBID_HINTS = ("must not", "must never", "never", "should not", "shouldn't", "cannot", "can't", "no ")
_REQUIRE_HINTS = ("must have", "must always", "must be able", "should have", "should be able", "always")


def parse_policy(text: str, role: str) -> tuple[ExpectationSet, list[str]]:
    notes: list[str] = []
    clauses = _parse_with_gemini(text)
    if clauses is None:
        notes.append("Gemini parse unavailable — used keyword matching.")
        clauses = _parse_with_keywords(text)
    forbidden, required = [], []
    for c in clauses:
        node = ExpectationNode(
            expectation_id=f"e-{c['subject']}-{c['polarity']}",
            polarity="must_not_exist" if c["polarity"] == "forbidden" else "must_exist",
            subject=c["subject"],
            roles=(role,),
            source_text=text.strip(),
        )
        (forbidden if c["polarity"] == "forbidden" else required).append(node)
    if not forbidden and not required:
        notes.append(
            f"No clause matched the engine's capability vocabulary ({', '.join(CAPS)}). "
            "The crawl still builds the full graph."
        )
    return ExpectationSet(forbidden=tuple(forbidden), required=tuple(required)), notes


def _parse_with_keywords(text: str) -> list[dict]:
    low = f" {text.lower()} "
    polarity = "forbidden"
    if any(h in low for h in _REQUIRE_HINTS) and not any(h in low for h in _FORBID_HINTS):
        polarity = "required"
    return [{"subject": cap, "polarity": polarity} for cap, kws in _KEYWORDS.items() if any(k in low for k in kws)]


def _parse_with_gemini(text: str) -> list[dict] | None:
    try:
        prompt = (
            "You convert a plain-English UI access policy into structured clauses.\n"
            f"The only subjects allowed are exactly: {CAPS}\n"
            'Return ONLY a JSON array. Each item: {"subject": <one of the allowed>, '
            '"polarity": "forbidden" | "required"}.\n'
            '"forbidden" = the user must NOT see/do it; "required" = they MUST have it. '
            "Omit anything that maps to no allowed subject.\n\n"
            f"Policy: {text.strip()}"
        )
        raw = VLMPerception().complete_text(prompt).strip()
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        out = []
        for item in json.loads(raw):
            if isinstance(item, dict) and item.get("subject") in CAPS and item.get("polarity") in ("forbidden", "required"):
                out.append({"subject": item["subject"], "polarity": item["polarity"]})
        return out or None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Port wrappers (local, disclosed)
# ---------------------------------------------------------------------------


class OriginBoundCrawler:
    """PlaywrightCrawler kept on the seed's origin — off-origin = recorded dead end."""

    def __init__(self, seed_url: str, role: str, output_dir: str) -> None:
        from apps.agent.crawler.playwright_crawler import PlaywrightCrawler

        self._inner = PlaywrightCrawler(role=role, output_dir=output_dir)
        self._origin = urlparse(seed_url).netloc

    def _check(self, b: CaptureBundle) -> CaptureBundle:
        if urlparse(b.url).netloc != self._origin:
            raise NavigationError(f"off-origin: {b.url}")
        return b

    def open(self, url: str) -> CaptureBundle:
        return self._check(self._inner.open(url))

    def act(self, action: Action) -> CaptureBundle:
        return self._check(self._inner.act(action))

    def enumerate_actions(self, bundle: CaptureBundle) -> tuple[Action, ...]:
        return self._inner.enumerate_actions(bundle)

    def close(self) -> None:
        self._inner.close()


class VLMBackedPerception:
    """Real VLMPerception + deterministic map. Local fixes: state_id -> real
    fingerprint (ADR C-3 res. 1); a failed/rate-limited Gemini call degrades to
    the deterministic map for that state instead of failing the whole audit."""

    def __init__(self, use_vision: bool = True) -> None:
        self._inner = VLMPerception()
        self._use_vision = use_vision
        self.vision_calls = 0
        self.vision_failed = 0
        self.vision_error: str | None = None
        self.vision_added: list[dict] = []

    def analyze(self, bundle: CaptureBundle, role: str):
        real_id = fingerprint_bundle(bundle)
        det = build_semantic_map(bundle, role, real_id)
        if not self._use_vision or not bundle.screenshot_path:
            return dataclasses.replace(det, state_id=real_id)
        try:
            ui_map = self._inner.analyze(bundle, role)
            self.vision_calls += 1
            extra = sorted(set(ui_map.capabilities) - set(det.capabilities))
            if extra:
                self.vision_added.append({"url": bundle.url, "caps": extra})
            return dataclasses.replace(ui_map, state_id=real_id)
        except Exception as exc:  # noqa: BLE001
            self.vision_failed += 1
            self.vision_error = str(exc).split(".")[0][:200]
            return dataclasses.replace(det, state_id=real_id)

    def audit(self, s_current, expectations):
        return negation_audit(s_current, expectations)

    def complete_text(self, prompt: str) -> str:
        return self._inner.complete_text(prompt)


class RecordingGraph:
    def __init__(self, inner: Neo4jGraph) -> None:
        self._inner = inner
        self.shots: dict[str, str] = {}
        self.urls: dict[str, str] = {}
        self.edges: list[dict] = []

    def fingerprint(self, b):
        return self._inner.fingerprint(b)

    def is_visited(self, s, a):
        return self._inner.is_visited(s, a)

    def mark_visited(self, s, a):
        return self._inner.mark_visited(s, a)

    def persist_edge(self, e):
        self.edges.append({
            "from": e.from_state_id, "to": e.to_state_id,
            "label": getattr(e, "label", "") or "",
            "back": bool(getattr(e, "is_back_edge", False)),
        })
        return self._inner.persist_edge(e)

    def persist_violation(self, v):
        return self._inner.persist_violation(v)

    def persist_state(self, state):
        if state.screenshot_path:
            self.shots[state.state_id] = state.screenshot_path
        self.urls[state.state_id] = state.url
        return self._inner.persist_state(state)


# ---------------------------------------------------------------------------
# Serving + helpers
# ---------------------------------------------------------------------------


def free_port() -> int:
    sk = socket.socket()
    sk.bind(("127.0.0.1", 0))
    port = sk.getsockname()[1]
    sk.close()
    return port


def serve_dir(directory: str, port: int) -> http.server.ThreadingHTTPServer:
    handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(*a, directory=directory, **kw)  # noqa: E731
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def b64(path: str | None) -> str | None:
    if not path or not os.path.isfile(path):
        return None
    with open(path, "rb") as fh:
        return "data:image/png;base64," + base64.b64encode(fh.read()).decode()


def reset_scan(store: GraphStore, scan_id: str) -> None:
    try:
        with store.driver.session() as s:
            s.run(
                "MATCH (p:PolicyContext {scan_id:$sid}) OPTIONAL MATCH (p)-[:CONTAINS]->(n) "
                "DETACH DELETE p, n",
                sid=scan_id,
            )
    except Exception:
        pass
    try:
        VisitedCache(scan_id).clear()
    except Exception:
        pass


def purge_target(store: GraphStore, url_prefix: str) -> int:
    """Delete every StateNode (and its edges + violations) previously crawled
    under `url_prefix`, so an audit rebuilds that target's graph instead of
    piling parallel ACTION edges onto it run after run. Returns nodes removed."""
    if not url_prefix:
        return 0
    try:
        with store.driver.session() as s:
            rec = s.run(
                "MATCH (n:StateNode) WHERE n.url STARTS WITH $p RETURN count(n) AS c",
                p=url_prefix,
            ).single()
            removed = int(rec["c"]) if rec else 0
            s.run(
                "MATCH (n:StateNode) WHERE n.url STARTS WITH $p "
                "OPTIONAL MATCH (n)-[:HAS_VIOLATION]->(v:ViolationNode) "
                "DETACH DELETE n, v",
                p=url_prefix,
            )
            return removed
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Job runner
# ---------------------------------------------------------------------------

JOBS: dict[str, dict[str, Any]] = {}


class _ProgressLogger:
    def __init__(self, job_id: str) -> None:
        self.run_id = job_id
        self._job = JOBS[job_id]

    def emit(self, node: str, event: str, **f: Any) -> None:
        j = self._job
        if node == "scan" and event == "scanned":
            j["log"].append(f"visited state {str(f.get('state_id',''))[:12]} (depth {f.get('depth','?')})")
        elif node == "act" and event == "acted":
            j["log"].append("followed an action to a new state")
        elif node == "audit" and event == "violation":
            j["log"].append(f"VIOLATION: {f.get('clause_type')} / {f.get('expectation_id')}")
        elif node == "skip":
            j["log"].append(f"skipped an action ({f.get('reason', 'dead end')})")


def run_audit(
    job_id: str,
    *,
    seed_url: str,
    base_url: str,
    policy_text: str,
    role: str,
    display: Callable[[str | None], str | None],
    label: str,
) -> None:
    """Drive one crawl. `display` maps a served URL to what the UI should show."""
    job = JOBS[job_id]
    store = None
    crawler = None
    try:
        job["log"].append("parsing policy…")
        policy, notes = parse_policy(policy_text, role)
        job["policy_parsed"] = {
            "forbidden": [e.subject for e in policy.forbidden],
            "required": [e.subject for e in policy.required],
            "notes": notes,
        }
        job["log"].append(
            f"policy → forbidden={job['policy_parsed']['forbidden']} required={job['policy_parsed']['required']}"
        )

        store = GraphStore()
        scan_id = f"demo-{job_id[:8]}"
        reset_scan(store, scan_id)
        removed = purge_target(store, base_url)
        if removed:
            job["log"].append(f"cleared {removed} state(s) from a previous audit of this target")
        graph = RecordingGraph(Neo4jGraph(scan_id=scan_id, store=store))
        perception = VLMBackedPerception(use_vision=job["use_vision"])
        crawler = OriginBoundCrawler(seed_url, role, f"{SHOT_DIR}/{job_id[:8]}")
        ports = Ports(crawler=crawler, perception=perception, graph=graph)
        config = OrchestratorConfig(
            _env_file=None, role=role, perception_rate_per_min=0,
            max_states=int(job["max_states"]), depth_limit=int(job["depth_limit"]),
        )

        job["log"].append(f"launching Chromium → {seed_url}")
        job["status"] = "crawling"
        result = graph_runner.explore(ports, seed_url, policy, config, run_id=scan_id, log=_ProgressLogger(job_id))

        if result.termination_reason == "error" and result.states == 0:
            raise RuntimeError(f"Nothing loaded from {label} — check it's reachable / has an index.html.")

        viols = []
        for v in result.violations:
            viols.append({
                "clause_type": v.clause_type,
                "severity": v.severity,
                "rationale": v.rationale,
                "expectation_id": v.expectation_id,
                "evidence_text": v.evidence.text,
                "evidence_selector": v.evidence.selector,
                "url": display(graph.urls.get(v.state_id)),
                "screenshot": b64(graph.shots.get(v.state_id)),
            })

        job["result"] = {
            "target": label,
            "role": role,
            "served_url": seed_url,
            "termination_reason": result.termination_reason,
            "states": result.states,
            "edges": result.edges,
            "visited_pairs": result.visited_pairs,
            "skipped": len(result.skipped),
            "duration_ms": round(result.duration_ms, 1),
            "vision_calls": perception.vision_calls,
            "vision_failed": perception.vision_failed,
            "vision_error": perception.vision_error,
            "vision_added": [{"caps": a["caps"]} for a in perception.vision_added],
            "pages": [
                {"url": display(graph.urls.get(sid, "?")), "screenshot": b64(graph.shots.get(sid))}
                for sid in dict.fromkeys(result.order)
            ],
            "graph_edges": [
                {
                    "from": display(graph.urls.get(x["from"])) or x["from"][:10],
                    "to": display(graph.urls.get(x["to"])) or x["to"][:10],
                    "label": x["label"],
                    "back": x["back"],
                }
                for x in graph.edges
            ],
            "seed": display(graph.urls.get(result.order[0])) if result.order else None,
            "violations": viols,
        }
        job["status"] = "done"
        job["log"].append(f"done — {result.states} states, {len(viols)} violations")
    except Exception as exc:  # noqa: BLE001
        job["status"] = "error"
        job["error"] = f"{type(exc).__name__}: {exc}"
        job["log"].append("ERROR: " + job["error"])
        job["trace"] = traceback.format_exc()
    finally:
        if crawler is not None:
            try:
                crawler.close()
            except Exception:
                pass
        if store is not None:
            try:
                store.close()
            except Exception:
                pass
