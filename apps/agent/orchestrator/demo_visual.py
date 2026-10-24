# ruff: noqa: E501  (embedded HTML/CSS template)
"""Render the demo crawl as a single self-contained HTML page (inline SVG).

    uv run python -m apps.agent.orchestrator.demo_visual [out.html]

Same crawl as `docs/demo_crawl.py` (real loop, real ground truth, scripted
fakes); this only draws the result. No dependencies, no network, no JS.
"""

from __future__ import annotations

import html
import sys
import tempfile
from pathlib import Path
from typing import Any

from apps.agent.orchestrator.config import OrchestratorConfig
from apps.agent.orchestrator.deps import Ports
from apps.agent.orchestrator.fakes import FakeGraph, FakePerception
from apps.agent.orchestrator.graph_runner import explore
from tests.fixtures.orchestrator import testapp

COL_W, ROW_H, PAD, NODE_W, NODE_H = 240, 120, 60, 170, 56


def _crawl() -> tuple[Any, FakeGraph, Any]:
    app = testapp.load("broken-admin")
    ports = Ports(crawler=app.crawler(), perception=FakePerception(), graph=FakeGraph())
    config = OrchestratorConfig(
        _env_file=None,  # type: ignore[call-arg]
        role=app.role,
        depth_limit=10,
        max_states=50,
        perception_rate_per_min=0,
    )
    result = explore(ports, app.seed, app.policy, config, run_id="demo-visual")
    graph: FakeGraph = ports.graph  # type: ignore[assignment]
    return app, graph, result


def render() -> str:
    app, graph, result = _crawl()
    pages = {sid: path for path, sid in app.state_ids(graph.fingerprint).items()}
    planted = {v.key for v in app.expected}
    found = {(pages[v.state_id], v.expectation_id, v.clause_type) for v in result.violations}

    by_depth: dict[int, list[str]] = {}
    for sid, node in graph.states.items():
        by_depth.setdefault(node.depth, []).append(sid)
    for ids in by_depth.values():
        ids.sort(key=lambda s: pages[s])

    tallest = max(len(v) for v in by_depth.values())
    height = tallest * ROW_H + 2 * PAD
    width = (max(by_depth) + 1) * COL_W + PAD
    pos: dict[str, tuple[float, float]] = {}
    for depth, ids in by_depth.items():
        top = (height - len(ids) * ROW_H) / 2 + ROW_H / 2
        for i, sid in enumerate(ids):
            pos[sid] = (PAD + depth * COL_W + NODE_W / 2, top + i * ROW_H)

    bad_pages: dict[str, list[str]] = {}
    for page, exp, clause in sorted(found):
        bad_pages.setdefault(page, []).append(f"{exp} ({clause.replace('_', ' ')})")

    svg: list[str] = []
    for e in graph.edges:
        (x1, y1), (x2, y2) = pos[e.from_state_id], pos[e.to_state_id]
        back = e.is_back_edge
        # Leave/enter on the node sides; curve bidirectional pairs apart.
        sx = x1 + (NODE_W / 2 if x2 > x1 else -NODE_W / 2 if x2 < x1 else 0)
        ex = x2 + (-NODE_W / 2 if x2 > x1 else NODE_W / 2 if x2 < x1 else 0)
        sy = y1 + (NODE_H / 2 if x2 == x1 and y2 > y1 else -NODE_H / 2 if x2 == x1 else 0)
        ey = y2 + (-NODE_H / 2 if x2 == x1 and y2 > y1 else NODE_H / 2 if x2 == x1 else 0)
        bend = -70 if back else 0
        mx, my = (sx + ex) / 2, (sy + ey) / 2 + bend
        cls = "back" if back else "fwd"
        svg.append(
            f'<path class="edge {cls}" d="M{sx:.0f},{sy:.0f} Q{mx:.0f},{my:.0f} {ex:.0f},{ey:.0f}" '
            f'marker-end="url(#arrow-{cls})"/>'
        )

    for sid, (cx, cy) in pos.items():
        page = pages[sid]
        bad = page in bad_pages
        x, y = cx - NODE_W / 2, cy - NODE_H / 2
        svg.append(
            f'<g class="node{" bad" if bad else ""}"><rect x="{x:.0f}" y="{y:.0f}" '
            f'width="{NODE_W}" height="{NODE_H}" rx="10"/>'
            f'<text x="{cx:.0f}" y="{cy - 4:.0f}" class="page">{html.escape(page)}</text>'
            f'<text x="{cx:.0f}" y="{cy + 14:.0f}" class="meta">depth {graph.states[sid].depth}'
            f'{" · " + str(len(bad_pages[page])) + " violation(s)" if bad else ""}</text></g>'
        )

    rows = []
    for v in sorted(app.expected, key=lambda v: v.id):
        hit = v.key in found
        rows.append(
            f'<tr class="{"ok" if hit else "miss"}"><td>{"✔ FOUND" if hit else "✘ MISSED"}</td>'
            f"<td>{html.escape(v.id)}</td><td>{html.escape(v.clause_type)}</td>"
            f"<td>{html.escape(v.expectation_id)}</td><td>{html.escape(v.page)}</td></tr>"
        )
    exact = found == planted
    stats = [
        ("States", f"{result.states} (expected {app.expected_states})"),
        ("Edges", result.edges),
        ("Cycles (back-edges)", len(graph.back_edges())),
        ("Pairs executed / distinct", f"{result.visited_pairs} / {len(graph.visited)}"),
        ("Violations", f"{len(result.violations)} found / {len(app.expected)} planted"),
    ]
    stat_html = "".join(f"<div><b>{html.escape(str(v))}</b><span>{k}</span></div>" for k, v in stats)

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>StateScout AI — exploration graph</title>
<style>
:root{{--bg:#0f1419;--fg:#e6e9ee;--mut:#8b95a3;--card:#18202a;--line:#3b82f6;--cyc:#f59e0b;--bad:#ef4444;--ok:#22c55e}}
@media (prefers-color-scheme:light){{:root{{--bg:#f6f7f9;--fg:#15191f;--mut:#5b6572;--card:#fff}}}}
body{{margin:0;padding:24px 16px;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}}
main{{max-width:1100px;margin:0 auto}} h1{{margin:0 0 4px;font-size:24px}} p.sub{{margin:0 0 20px;color:var(--mut)}}
.card{{background:var(--card);border-radius:12px;padding:16px;margin-bottom:20px;overflow-x:auto}}
.stats{{display:flex;flex-wrap:wrap;gap:12px}} .stats div{{flex:1 1 150px;background:var(--card);border-radius:12px;padding:12px 16px}}
.stats b{{display:block;font-size:20px}} .stats span{{color:var(--mut);font-size:13px}}
svg{{display:block;min-width:{width}px}} .edge{{fill:none;stroke-width:2}} .fwd{{stroke:var(--line)}}
.back{{stroke:var(--cyc);stroke-dasharray:6 5}} .node rect{{fill:var(--card);stroke:var(--line);stroke-width:2}}
.node.bad rect{{stroke:var(--bad);stroke-width:3;fill:rgba(239,68,68,.14)}}
text{{text-anchor:middle;fill:var(--fg)}} .page{{font:600 14px system-ui}} .meta{{font:12px system-ui;fill:var(--mut)}}
.legend{{display:flex;flex-wrap:wrap;gap:18px;color:var(--mut);font-size:13px;margin-top:8px}}
table{{border-collapse:collapse;width:100%}} td{{padding:8px 10px;border-bottom:1px solid rgba(128,128,128,.25)}}
tr.ok td:first-child{{color:var(--ok);font-weight:600}} tr.miss td:first-child{{color:var(--bad);font-weight:600}}
.verdict{{font-weight:700;color:{"var(--ok)" if exact else "var(--bad)"}}}
</style></head><body><main>
<h1>StateScout AI — exploration graph</h1>
<p class="sub">test-apps/{html.escape(app.name)} · role {html.escape(app.role)} ·
<span class="verdict">{"EXACT MATCH — every planted violation found, nothing invented" if exact else "MISMATCH"}</span></p>
<div class="stats">{stat_html}</div><br>
<div class="card"><svg viewBox="0 0 {width} {height:.0f}" width="{width}" height="{height:.0f}" role="img"
aria-label="Exploration graph of {len(pos)} states">
<defs>
<marker id="arrow-fwd" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#3b82f6"/></marker>
<marker id="arrow-back" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#f59e0b"/></marker>
</defs>{"".join(svg)}</svg>
<div class="legend"><span><b style="color:var(--line)">━▶</b> forward edge</span>
<span><b style="color:var(--cyc)">╍▶</b> back-edge (cycle closed — kept, never pruned)</span>
<span><b style="color:var(--bad)">▢</b> page with a policy violation</span></div></div>
<div class="card"><table>{"".join(rows)}</table></div>
</main></body></html>"""


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir()) / "statescout-demo.html"
    out.write_text(render(), encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
