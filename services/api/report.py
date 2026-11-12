# ruff: noqa: E501
"""Report generation: JSON, Markdown and a self-contained HTML report.

Pure functions of an :class:`AuditReport`. No API keys can appear: the report
model carries none, and ``api_key`` keys are stripped defensively.
"""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import html
import json
import math
from typing import Any

from apps.agent.audit_models import AuditReport

SEV_COLOR = {"critical": "#b42318", "high": "#d9480f", "medium": "#b7791f", "low": "#2f6fb0"}


def _clean(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return _clean(dataclasses.asdict(obj))
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items() if k not in ("api_key", "apiKey")}
    if isinstance(obj, (list, tuple, set)):
        return [_clean(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


IMAGE_SUFFIXES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}
_EMBED_MAX_BYTES = 400_000
_EMBED_MAX_IMAGES = 12


def shot_token(path: str) -> str:
    """Opaque id for a screenshot path, so the API never exposes or accepts raw paths."""
    return hashlib.sha256(path.encode()).hexdigest()[:16]


def image_media_type(path: str) -> str | None:
    """Media type for a servable screenshot file, else None (not an image / missing)."""
    from pathlib import Path

    p = Path(path)
    return IMAGE_SUFFIXES.get(p.suffix.lower()) if p.is_file() else None


def screenshot_paths(report: AuditReport) -> list[str]:
    """Local screenshot files this audit references (findings + graph nodes)."""
    raw = [f.screenshot for f in report.findings] + [
        n.get("screenshot") for n in report.graph.get("nodes", []) if isinstance(n, dict)
    ]
    return sorted({r for r in raw if isinstance(r, str) and not r.startswith("data:")})


def report_to_dict(report: AuditReport) -> dict[str, Any]:
    d: dict[str, Any] = _clean(report)
    return d


def to_json(report: AuditReport) -> str:
    return json.dumps(report_to_dict(report), indent=2)


# ---- graph helpers -------------------------------------------------------- #


def _nid(n: Any) -> str:
    if isinstance(n, dict):
        return str(n.get("id", n.get("state_id", "")))
    return str(n)


def _edge(e: dict[str, Any]) -> tuple[str, str, float]:
    s = e.get("source", e.get("from", e.get("src", "")))
    t = e.get("target", e.get("to", e.get("dst", "")))
    p = e.get("probability", e.get("p", e.get("weight", 1.0)))
    try:
        pf = max(0.0, min(1.0, float(p)))
    except (TypeError, ValueError):
        pf = 1.0
    return str(s), str(t), pf


def layout(
    ids: list[str], edges: list[tuple[str, str, float]], w: int = 800, h: int = 480
) -> dict[str, tuple[float, float]]:
    """Deterministic small force layout (Fruchterman-Reingold style)."""
    n = len(ids)
    if n == 0:
        return {}
    pos = {
        i: [
            w / 2 + (w / 3) * math.cos(2 * math.pi * k / n),
            h / 2 + (h / 3) * math.sin(2 * math.pi * k / n),
        ]
        for k, i in enumerate(ids)
    }
    if n == 1:
        return {ids[0]: (w / 2, h / 2)}
    area_k = math.sqrt(w * h / n) * 0.8
    temp = w / 10
    for _ in range(120):
        disp = {i: [0.0, 0.0] for i in ids}
        for a in range(n):
            for b in range(a + 1, n):
                pa, pb = pos[ids[a]], pos[ids[b]]
                dx, dy = pa[0] - pb[0], pa[1] - pb[1]
                d = math.hypot(dx, dy) or 0.01
                f = area_k * area_k / d
                disp[ids[a]][0] += dx / d * f
                disp[ids[a]][1] += dy / d * f
                disp[ids[b]][0] -= dx / d * f
                disp[ids[b]][1] -= dy / d * f
        for s, t, _p in edges:
            if s == t or s not in pos or t not in pos:
                continue
            dx, dy = pos[s][0] - pos[t][0], pos[s][1] - pos[t][1]
            d = math.hypot(dx, dy) or 0.01
            f = d * d / area_k
            disp[s][0] -= dx / d * f
            disp[s][1] -= dy / d * f
            disp[t][0] += dx / d * f
            disp[t][1] += dy / d * f
        for i in ids:
            dx, dy = disp[i]
            d = math.hypot(dx, dy) or 0.01
            pos[i][0] = min(w - 30, max(30, pos[i][0] + dx / d * min(d, temp)))
            pos[i][1] = min(h - 30, max(30, pos[i][1] + dy / d * min(d, temp)))
        temp *= 0.96
    return {i: (p[0], p[1]) for i, p in pos.items()}


def graph_svg(report: AuditReport, w: int = 800, h: int = 480) -> str:
    g = report.graph or {}
    nodes = [_nid(n) for n in g.get("nodes", [])]
    edges = [_edge(e) for e in g.get("edges", []) if isinstance(e, dict)]
    for s, t, _ in edges:
        for end in (s, t):
            if end and end not in nodes:
                nodes.append(end)
    if not nodes:
        return '<p class="muted">No graph recorded.</p>'
    labels = {
        _nid(n): str(n.get("label") or n.get("url") or _nid(n))
        for n in g.get("nodes", [])
        if isinstance(n, dict)
    }
    bad = {f.state_id for f in report.findings} | {
        _nid(n) for n in g.get("nodes", []) if isinstance(n, dict) and n.get("violation")
    }
    pos = layout(nodes, edges, w, h)
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" role="img" '
        'aria-label="State transition graph" class="graph">',
        '<defs><marker id="ar" viewBox="0 0 10 10" refX="16" refY="5" markerWidth="6" '
        'markerHeight="6" orient="auto-start-reverse"><path d="M0,0L10,5L0,10z" '
        'fill="#7a8794"/></marker></defs>',
    ]
    for s, t, p in edges:
        if s not in pos or t not in pos:
            continue
        x1, y1 = pos[s]
        x2, y2 = pos[t]
        sw = 1 + 4 * p
        op = 0.25 + 0.75 * p
        title = f"<title>{html.escape(s)} to {html.escape(t)}: p={p:.2f}</title>"
        if s == t:
            out.append(
                f'<path d="M{x1:.1f},{y1 - 8:.1f} c-26,-38 26,-38 0,0" fill="none" '
                f'stroke="#7a8794" stroke-width="{sw:.1f}" opacity="{op:.2f}" '
                f'marker-end="url(#ar)">{title}</path>'
            )
        else:
            out.append(
                f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                f'stroke="#7a8794" stroke-width="{sw:.1f}" opacity="{op:.2f}" '
                f'marker-end="url(#ar)">{title}</line>'
            )
    for nid in nodes:
        x, y = pos[nid]
        fill = "#d9480f" if nid in bad else "#3b82c4"
        lab = html.escape(labels.get(nid, nid))[:40]
        out.append(
            f'<g><circle cx="{x:.1f}" cy="{y:.1f}" r="{11 if nid in bad else 8}" '
            f'fill="{fill}" stroke="#fff" stroke-width="2"><title>{html.escape(nid)}'
            f"{' (violation)' if nid in bad else ''}</title></circle>"
            f'<text x="{x:.1f}" y="{y + 24:.1f}" font-size="10" text-anchor="middle" '
            f'fill="#555">{lab}</text></g>'
        )
    out.append("</svg>")
    return "".join(out)


# ---- Markdown ------------------------------------------------------------- #


def _md(s: Any) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


_BULKY_STATS = {"finding_groups", "confidence_labels", "masks"}


def _groups(report: AuditReport) -> list[dict[str, Any]]:
    got = report.stats.get("finding_groups")
    return [g for g in got if isinstance(g, dict)] if isinstance(got, list) else []


def to_markdown(report: AuditReport) -> str:
    L = [f"# StateScout audit: {report.url}", ""]
    L.append(f"- Audit: `{report.audit_id}`  \n- Status: **{report.status}**")
    for k, v in sorted(report.stats.items()):
        if k not in _BULKY_STATS:
            L.append(f"- {k}: {v}")
    if report.error:
        L.append(f"- Error: {report.error}")
    L += ["", "## Rules", ""]
    L += [f"- ({r.source}, {r.severity}) {r.text}" for r in report.rules] or ["_None_"]
    L += ["", f"## Violations ({len(report.findings)})", ""]
    groups = _groups(report)
    if groups:
        L += ["### Distinct issues", ""]
        L += [f"- {g.get('count', 1)}x ({g.get('severity')}) {_md(g.get('title'))}" for g in groups]
        L.append("")
    if report.findings:
        L += ["| Severity | Confidence | Title | URL | Rationale |", "|---|---|---|---|---|"]
        for f in report.findings:
            L.append(
                f"| {f.severity} | {f.confidence:.2f} | {_md(f.title)} | {_md(f.url)} | "
                f"{_md(f.rationale)} |"
            )
        for f in report.findings:
            if f.evidence:
                L += ["", f"**{f.title}** evidence:"] + [f"- {e}" for e in f.evidence]
    else:
        L.append("_No violations found._")
    L += ["", "## Blocked pages", ""]
    L += [f"- {b.reason}: {b.url}" for b in report.blocked] or ["_None_"]
    g = report.graph or {}
    L += [
        "",
        f"## Graph\n\n{len(g.get('nodes', []))} states, {len(g.get('edges', []))} transitions.",
    ]
    return "\n".join(L) + "\n"


# ---- HTML ----------------------------------------------------------------- #

_CSS = """
:root{--bg:#fff;--fg:#1c2530;--mut:#667;--card:#f6f8fa;--bd:#d8dee4}
@media(prefers-color-scheme:dark){:root{--bg:#10151b;--fg:#e6edf3;--mut:#9aa7b4;--card:#18202a;--bd:#2b3643}}
body{margin:0;padding:24px;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif;max-width:1000px;margin-inline:auto}
h1{font-size:1.5rem}.muted{color:var(--mut)}table{border-collapse:collapse;width:100%}
th,td{border-bottom:1px solid var(--bd);padding:8px;text-align:left;vertical-align:top}
.card{background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:12px;margin:12px 0}
.sev{color:#fff;border-radius:6px;padding:1px 8px;font-size:.8rem}svg.graph{width:100%;height:auto}
img.shot,div.shot{width:240px;border:1px solid var(--bd);border-radius:6px}div.shot{height:150px;background-size:cover;background-position:top}
"""


def _embed(path: str, embedded: dict[str, str]) -> str | None:
    """CSS class of a small local screenshot, embedding each unique file only once."""
    from pathlib import Path

    if path in embedded:
        return embedded[path]
    media = image_media_type(path)
    if media is None or len(embedded) >= _EMBED_MAX_IMAGES:
        return None
    p = Path(path)
    if p.stat().st_size > _EMBED_MAX_BYTES:
        return None
    embedded[path] = f"s{len(embedded) + 1}"
    return embedded[path]


def _embed_css(embedded: dict[str, str]) -> str:
    from pathlib import Path

    rules = []
    for path, cls in embedded.items():
        data = base64.b64encode(Path(path).read_bytes()).decode()
        rules.append(f".{cls}{{background-image:url(data:{image_media_type(path)};base64,{data})}}")
    return "".join(rules)


def to_html(report: AuditReport) -> str:
    e = html.escape
    embedded: dict[str, str] = {}
    rows = []
    for f in report.findings:
        shot = ""
        if f.screenshot and f.screenshot.startswith("data:image/"):
            shot = f'<br><img class="shot" alt="screenshot" src="{e(f.screenshot, quote=True)}">'
        elif f.screenshot:
            cls = _embed(f.screenshot, embedded)
            if cls:
                shot = f'<br><div class="shot {cls}" role="img" aria-label="screenshot of the page"></div>'
            else:
                name = f.screenshot.replace("\\", "/").rsplit("/", 1)[-1]
                shot = f'<br><span class="muted">screenshot not embedded: {e(name)}</span>'
        ev = "".join(f"<li>{e(x)}</li>" for x in f.evidence)
        rows.append(
            f'<tr><td><span class="sev" style="background:{SEV_COLOR.get(f.severity, "#555")}">'
            f"{e(f.severity)}</span></td><td>{f.confidence:.2f}</td>"
            f"<td><strong>{e(f.title)}</strong><br>{e(f.rationale)}"
            f"{'<ul>' + ev + '</ul>' if ev else ''}{shot}</td><td>{e(f.url)}</td></tr>"
        )
    table = (
        "<table><thead><tr><th>Severity</th><th>Confidence</th><th>Finding</th><th>URL</th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table>"
        if rows
        else '<p class="muted">No violations found.</p>'
    )
    rules = "".join(
        f"<li>{e(r.text)} <span class='muted'>({e(r.source)})</span></li>" for r in report.rules
    )
    blocked = "".join(f"<li>{e(b.reason)}: {e(b.url)}</li>" for b in report.blocked)
    stats = " &middot; ".join(
        f"{e(str(k))}: {e(str(v))}"
        for k, v in sorted(report.stats.items())
        if k not in _BULKY_STATS
    )
    issues = "".join(
        f"<li>{e(str(g.get('count', 1)))}x <strong>{e(str(g.get('title')))}</strong> "
        f"<span class='muted'>({e(str(g.get('severity')))})</span></li>"
        for g in _groups(report)
    )
    err = f'<p class="card">Error: {e(report.error)}</p>' if report.error else ""
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>StateScout report</title><style>{_CSS}{_embed_css(embedded)}</style></head><body>"
        f"<h1>StateScout audit</h1><p>{e(report.url)}<br><span class='muted'>"
        f"{e(report.audit_id)} &middot; {e(report.status)} &middot; {stats}</span></p>{err}"
        f"<h2>Violations ({len(report.findings)})</h2>"
        f"{'<h3>Distinct issues</h3><ul>' + issues + '</ul>' if issues else ''}{table}"
        f"<h2>Blocked pages</h2>{'<ul>' + blocked + '</ul>' if blocked else '<p class=muted>None</p>'}"
        f"<h2>Rules</h2>{'<ul>' + rules + '</ul>' if rules else '<p class=muted>None</p>'}"
        f"<h2>Exploration graph</h2><div class='card'>{graph_svg(report)}</div>"
        "</body></html>"
    )
