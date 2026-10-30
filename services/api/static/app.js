"use strict";
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const NS = "http://www.w3.org/2000/svg";
  const state = { auditId: null, generated: [], providers: [], ollama: [], abort: null, report: null };
  const BLOCK_TEXT = { robots: "Blocked by robots.txt", captcha: "CAPTCHA wall", login_wall: "Login wall",
    consent_wall: "Consent wall", rate_limit: "Rate limited", cap: "Crawl cap reached" };

  // ---- helpers ---------------------------------------------------------
  const apiKey = () => { try { return sessionStorage.getItem("ss_api_key") || ""; } catch { return ""; } };
  async function api(path, opts = {}) {
    const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
    if (apiKey()) headers["X-API-Key"] = apiKey();
    let r = await fetch(path, { ...opts, headers });
    if (r.status === 401) {
      const k = prompt("This server requires an API key (X-API-Key):");
      if (k) { try { sessionStorage.setItem("ss_api_key", k); } catch {} return api(path, opts); }
    }
    if (!r.ok) {
      let d = r.statusText;
      try { const j = await r.json(); d = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch {}
      throw new Error(d);
    }
    return r;
  }
  const el = (tag, attrs = {}, text) => {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    if (text !== undefined) e.textContent = text;
    return e;
  };
  const log = (msg) => {
    const p = $("#log"); p.textContent += msg + "\n"; p.scrollTop = p.scrollHeight;
  };
  const showErr = (m) => { const e = $("#err"); e.textContent = m || ""; e.hidden = !m; };

  // ---- theme -----------------------------------------------------------
  $("#theme").addEventListener("click", () => {
    const cur = document.documentElement.dataset.theme ||
      (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    const next = cur === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("ss_theme", next); } catch {}
  });
  try { const t = localStorage.getItem("ss_theme"); if (t) document.documentElement.dataset.theme = t; } catch {}

  // ---- providers -------------------------------------------------------
  const DEF_BASE = {};
  function provCfg(fs) {
    const provider = $(".p-provider", fs).value;
    if (!provider) return null; // "None": built-in heuristics / DOM-only perception
    const model = $(".p-model", fs).value.trim();
    if (!model) return null;
    const c = { provider, model };
    const b = $(".p-base", fs).value.trim(); if (b) c.base_url = b;
    const k = $(".p-key", fs).value; if (k) c.api_key = k;
    return c;
  }
  function fillModels(fs, models) {
    const dl = $("datalist", fs); dl.replaceChildren();
    models.forEach((m) => dl.appendChild(el("option", { value: m })));
  }
  function defaultModels(fs, name) {
    const kind = fs.dataset.kind;
    const p = state.providers.find((x) => x.name === name);
    let models = (p && p.default_models && p.default_models[kind]) || [];
    if (name === "ollama" && state.ollama.length) models = state.ollama;
    fillModels(fs, models);
    const inp = $(".p-model", fs);
    if (!inp.value && models[0]) inp.value = models[0];
    $(".p-base", fs).placeholder = (p && p.default_base_url) || "default";
  }
  async function initProviders() {
    let data = { providers: [], ollama: {} };
    try { data = await (await api("/providers")).json(); } catch (e) { log("Could not load providers: " + e.message); }
    state.providers = data.providers || [];
    state.ollama = (data.ollama && data.ollama.models) || [];
    $$(".prov").forEach((fs) => {
      const sel = $(".p-provider", fs);
      const names = state.providers.length ? state.providers.map((p) => p.name) : ["ollama", "gemini", "openai", "anthropic"];
      sel.appendChild(el("option", { value: "" }, "None (built-in heuristics)"));
      names.forEach((n) => sel.appendChild(el("option", { value: n }, n)));
      sel.value = "";
      sel.addEventListener("change", () => { $(".p-model", fs).value = ""; defaultModels(fs, sel.value); });
      defaultModels(fs, sel.value);
      $(".p-test", fs).addEventListener("click", async () => {
        const st = $(".p-status", fs); st.className = "p-status"; st.textContent = "Testing...";
        const cfg = provCfg(fs) || { provider: sel.value, model: "x" };
        try {
          const r = await (await api("/providers/test", { method: "POST", body: JSON.stringify(cfg) })).json();
          if (r.ok) { st.className = "p-status ok"; st.textContent = "Connected (" + r.models.length + " models)"; if (r.models.length) fillModels(fs, r.models); }
          else { st.className = "p-status bad"; st.textContent = "Failed: " + (r.error || "unreachable"); }
        } catch (e) { st.className = "p-status bad"; st.textContent = "Failed: " + e.message; }
      });
    });
  }

  // ---- rules -----------------------------------------------------------
  const userRules = () => $("#rules").value.split("\n").map((s) => s.trim()).filter(Boolean);
  function renderChips() {
    const box = $("#chips"); box.replaceChildren();
    const gen = new Set(state.generated);
    userRules().forEach((r) => {
      const c = el("span", { class: "chip" + (gen.has(r) ? " generated" : "") });
      c.appendChild(el("b", {}, gen.has(r) ? "generated" : "user")); c.appendChild(document.createTextNode(r));
      box.appendChild(c);
    });
  }
  $("#rules").addEventListener("input", renderChips);
  $("#gen").addEventListener("click", async () => {
    showErr("");
    const url = $("#url").value.trim(); if (!url) return showErr("Enter a URL first.");
    const b = $("#gen"); b.disabled = true; b.textContent = "Generating...";
    try {
      const body = { url, allow_private: $("#allow_private").checked };
      const llm = provCfg($('.prov[data-kind="llm"]')); if (llm) body.llm = llm;
      const r = await (await api("/rules/generate", { method: "POST", body: JSON.stringify(body) })).json();
      const have = new Set(userRules());
      const add = r.rules.filter((x) => !have.has(x));
      state.generated.push(...add);
      $("#rules").value = [...userRules(), ...add].join("\n");
      renderChips(); log("Generated " + add.length + " rule(s).");
    } catch (e) { showErr("Rule generation failed: " + e.message); }
    b.disabled = false; b.textContent = "Generate rules from site";
  });

  // ---- run -------------------------------------------------------------
  function setStatus(s) {
    const b = $("#status"); b.textContent = s; b.className = "badge " + s;
    const running = s === "running" || s === "stopping";
    $("#start").disabled = running; $("#stop").disabled = !running;
  }
  $("#form").addEventListener("submit", async (ev) => {
    ev.preventDefault(); showErr("");
    $("#log").textContent = ""; renderGraph(null); renderFindings(null);
    const body = {
      url: $("#url").value.trim(), rules: userRules(), auto_rules: $("#auto_rules").checked,
      caps: { max_states: +$("#max_states").value, depth_limit: +$("#depth_limit").value,
        max_seconds: +$("#max_seconds").value, requests_per_second: +$("#rps").value },
      respect_robots: $("#robots").checked, probabilistic: $("#prob").checked,
      allow_private: $("#allow_private").checked,
    };
    const llm = provCfg($('.prov[data-kind="llm"]')), vlm = provCfg($('.prov[data-kind="vlm"]'));
    if (llm) body.llm = llm; if (vlm) body.vlm = vlm;
    try {
      const r = await (await api("/audits", { method: "POST", body: JSON.stringify(body) })).json();
      state.auditId = r.audit_id; setStatus("running"); log("Audit " + r.audit_id + " started.");
      stream(r.audit_id);
    } catch (e) { showErr(e.message); }
  });
  $("#stop").addEventListener("click", async () => {
    if (!state.auditId) return;
    try { await api("/audits/" + state.auditId + "/stop", { method: "POST" }); setStatus("stopping"); log("Stop requested..."); }
    catch (e) { showErr(e.message); }
  });

  async function stream(id) {
    // fetch-based SSE so the X-API-Key header can be sent (EventSource cannot).
    const ctl = new AbortController(); state.abort = ctl;
    try {
      const headers = apiKey() ? { "X-API-Key": apiKey() } : {};
      const res = await fetch("/audits/" + id + "/events", { headers, signal: ctl.signal });
      const reader = res.body.getReader(), dec = new TextDecoder(); let buf = "";
      for (;;) {
        const { value, done } = await reader.read(); if (done) break;
        buf += dec.decode(value, { stream: true });
        let i; while ((i = buf.indexOf("\n\n")) >= 0) { handleEvent(buf.slice(0, i)); buf = buf.slice(i + 2); }
      }
    } catch (e) { if (e.name !== "AbortError") log("Stream interrupted: " + e.message); }
    await refresh(id);
  }
  let lastPoll = 0;
  function handleEvent(raw) {
    let type = "message", data = "";
    raw.split("\n").forEach((l) => { if (l.startsWith("event: ")) type = l.slice(7); else if (l.startsWith("data: ")) data += l.slice(6); });
    if (!data) return;
    let d; try { d = JSON.parse(data); } catch { return; }
    if (type === "status") { setStatus(d.status); log("Status: " + d.status + (d.error ? " (" + d.error + ")" : "")); }
    else if (type === "log") log([d.node, d.event, d.message].filter(Boolean).join(" "));
    else { log("progress " + (d.message || JSON.stringify(d.stats || d).slice(0, 140))); if (Date.now() - lastPoll > 1500) { lastPoll = Date.now(); refresh(state.auditId, true); } }
  }
  async function refresh(id, quiet) {
    try {
      const rep = await (await api("/audits/" + id)).json();
      state.report = rep; renderStats(rep); renderGraph(rep); renderFindings(rep);
      if (!quiet) setStatus(rep.status);
    } catch (e) { if (!quiet) showErr(e.message); }
  }
  function renderStats(rep) {
    const s = $("#stats"); s.replaceChildren();
    const items = { states: (rep.graph.nodes || []).length, transitions: (rep.graph.edges || []).length, violations: rep.findings.length, ...rep.stats };
    for (const [k, raw] of Object.entries(items)) {
      const v = Array.isArray(raw) ? raw.length + " item(s)" : raw && typeof raw === "object" ? Object.keys(raw).length + " entries" : raw;
      const sp = el("span"); sp.append(k + ": "); sp.appendChild(el("b", {}, String(v))); s.appendChild(sp);
    }
  }

  // ---- findings --------------------------------------------------------
  function renderFindings(rep) {
    const tb = $("#vtable tbody"); tb.replaceChildren(); $("#blocked").replaceChildren();
    if (!rep) return;
    if (!rep.findings.length) { const tr = el("tr"); const td = el("td", { colspan: 5 }, rep.status === "running" ? "Waiting for results..." : "No violations found."); tr.appendChild(td); tb.appendChild(tr); }
    const SEV = { low: 0, medium: 1, high: 2, critical: 3 };
    const groups = new Map();
    rep.findings.forEach((f) => {
      const key = f.group_key || f.title + "|" + (f.evidence[0] || "");
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(f);
    });
    const short = (t, n) => (t.length > n ? t.slice(0, n) + "..." : t);
    [...groups.values()]
      .sort((x, y) => (SEV[y[0].severity] || 0) - (SEV[x[0].severity] || 0) || y.length - x.length)
      .forEach((list) => {
        const f = list.reduce((w, c) => ((SEV[c.severity] || 0) > (SEV[w.severity] || 0) ? c : w), list[0]);
        const tr = el("tr");
        const t1 = el("td"); t1.appendChild(el("span", { class: "sev " + f.severity }, f.severity)); tr.appendChild(t1);
        tr.appendChild(el("td", {}, (Math.max(...list.map((x) => x.confidence)) * 100).toFixed(0) + "%"));
        const t3 = el("td"); t3.appendChild(el("strong", {}, f.title));
        if (list.length > 1) t3.appendChild(el("span", { class: "note" }, "  x" + list.length + " pages"));
        t3.appendChild(el("div", {}, short(f.rationale, 240)));
        const det = el("details"); det.appendChild(el("summary", { class: "note" }, list.length > 1 ? "Show all " + list.length + " pages" : f.url));
        list.forEach((x) => det.appendChild(el("div", { class: "note" }, x.url)));
        t3.appendChild(det); tr.appendChild(t3);
        const t4 = el("td"); const ul = el("ul"); f.evidence.slice(0, 4).forEach((x) => ul.appendChild(el("li", {}, short(x, 140)))); t4.appendChild(ul); tr.appendChild(t4);
        const t5 = el("td");
        if (f.screenshot && f.screenshot.startsWith("data:image/")) t5.appendChild(el("img", { class: "shot", alt: "Screenshot for " + f.title, src: f.screenshot }));
        else if (f.screenshot) t5.appendChild(el("span", { class: "note" }, f.screenshot));
        tr.appendChild(t5); tb.appendChild(tr);
        tr.addEventListener("mouseenter", () => highlight(f.state_id));
      });
    rep.blocked.forEach((b) => $("#blocked").appendChild(el("div", { class: "blk" }, (BLOCK_TEXT[b.reason] || b.reason) + ": " + b.url)));
    if (rep.error) $("#blocked").appendChild(el("div", { class: "blk" }, "Error: " + rep.error));
  }
  $$(".exp").forEach((b) => b.addEventListener("click", async () => {
    if (!state.auditId) return showErr("Run an audit first.");
    try {
      const r = await api("/audits/" + state.auditId + "/report?format=" + b.dataset.f);
      const blob = await r.blob(), a = el("a", { href: URL.createObjectURL(blob), download: "statescout-" + state.auditId + "." + b.dataset.f });
      document.body.appendChild(a); a.click(); a.remove();
    } catch (e) { showErr(e.message); }
  }));

  // ---- force graph -----------------------------------------------------
  const W = 800, H = 460;
  let sim = null;
  function highlight(id) { $$("#graph .node").forEach((n) => n.classList.toggle("sel", n.dataset.id === id)); }
  function renderGraph(rep) {
    const svg = $("#graph"); svg.replaceChildren(); if (sim) cancelAnimationFrame(sim.raf); sim = null;
    if (!rep) return;
    const g = rep.graph || {}, bad = new Set(rep.findings.map((f) => f.state_id));
    const nodes = new Map();
    const add = (id, label, v) => { if (!nodes.has(id)) { const a = nodes.size * 2.4; nodes.set(id, { id, label: label || id, x: W / 2 + 120 * Math.cos(a) * (1 + nodes.size / 20), y: H / 2 + 120 * Math.sin(a) * (1 + nodes.size / 20), vx: 0, vy: 0, bad: bad.has(id) || !!v }); } };
    (g.nodes || []).forEach((n) => typeof n === "object" ? add(String(n.id ?? n.state_id), n.label || n.url, n.violation) : add(String(n)));
    const edges = (g.edges || []).map((e) => ({ s: String(e.source ?? e.from ?? e.src), t: String(e.target ?? e.to ?? e.dst), p: Math.max(0, Math.min(1, +(e.probability ?? e.p ?? e.weight ?? 1))), a: e.action || e.action_id || "" }));
    edges.forEach((e) => { add(e.s); add(e.t); });
    if (!nodes.size) { const t = document.createElementNS(NS, "text"); t.setAttribute("x", W / 2); t.setAttribute("y", H / 2); t.textContent = "No graph yet"; svg.appendChild(t); return; }
    const defs = document.createElementNS(NS, "defs");
    defs.innerHTML = '<marker id="arr" viewBox="0 0 10 10" refX="18" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0,0L10,5L0,10z" fill="#7a8794"/></marker>';
    svg.appendChild(defs);
    const list = [...nodes.values()];
    const eEls = edges.map((e) => {
      const p = document.createElementNS(NS, "path"); p.setAttribute("class", "edge");
      p.setAttribute("stroke-width", (1 + 4 * e.p).toFixed(1)); p.setAttribute("opacity", (0.25 + 0.75 * e.p).toFixed(2));
      p.setAttribute("marker-end", "url(#arr)"); svg.appendChild(p);
      const info = e.s + " to " + e.t + " | p=" + e.p.toFixed(2) + (e.s === e.t ? " (self-loop)" : "") + (e.a ? " | " + e.a : "");
      p.addEventListener("mouseenter", (ev) => tip(ev, info)); p.addEventListener("mouseleave", () => tip());
      p.addEventListener("click", () => { $("#detail").textContent = "Transition " + info; });
      return { e, p };
    });
    const nEls = list.map((n) => {
      const gEl = document.createElementNS(NS, "g"), c = document.createElementNS(NS, "circle"), t = document.createElementNS(NS, "text");
      c.setAttribute("class", "node" + (n.bad ? " bad" : "")); c.setAttribute("r", n.bad ? 12 : 8); c.dataset.id = n.id;
      c.setAttribute("tabindex", "0"); c.setAttribute("aria-label", "State " + n.label + (n.bad ? " (violation)" : ""));
      t.textContent = n.label.length > 28 ? n.label.slice(0, 27) + "..." : n.label;
      gEl.appendChild(c); gEl.appendChild(t); svg.appendChild(gEl);
      const finds = rep.findings.filter((f) => f.state_id === n.id);
      const info = n.label + (n.bad ? " | violation" : "") + (finds.length ? ": " + finds.map((f) => f.title).join("; ") : "");
      c.addEventListener("mouseenter", (ev) => tip(ev, info)); c.addEventListener("mouseleave", () => tip());
      const pick = () => { highlight(n.id); $("#detail").textContent = "State " + n.id + " | " + info; };
      c.addEventListener("click", pick); c.addEventListener("keydown", (ev) => { if (ev.key === "Enter") pick(); });
      c.addEventListener("pointerdown", (ev) => { n.drag = true; c.setPointerCapture(ev.pointerId); sim.heat = 60; });
      c.addEventListener("pointermove", (ev) => { if (n.drag) { const pt = svgPt(svg, ev); n.x = pt.x; n.y = pt.y; n.vx = n.vy = 0; } });
      c.addEventListener("pointerup", () => { n.drag = false; });
      return { n, gEl, c, t };
    });
    const byId = nodes; sim = { heat: 300, raf: 0 };
    function step() {
      const k = Math.sqrt((W * H) / list.length) * 0.7;
      for (let i = 0; i < list.length; i++) for (let j = i + 1; j < list.length; j++) {
        const a = list[i], b = list[j]; let dx = a.x - b.x, dy = a.y - b.y, d = Math.hypot(dx, dy) || 0.1;
        const f = (k * k) / d / d * 0.5; a.vx += dx * f; a.vy += dy * f; b.vx -= dx * f; b.vy -= dy * f;
      }
      edges.forEach((e) => { if (e.s === e.t) return; const a = byId.get(e.s), b = byId.get(e.t); const dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy) || 0.1; const f = (d - k) / d * 0.04 * (0.4 + e.p); a.vx += dx * f; a.vy += dy * f; b.vx -= dx * f; b.vy -= dy * f; });
      list.forEach((n) => { n.vx += (W / 2 - n.x) * 0.004; n.vy += (H / 2 - n.y) * 0.004; if (!n.drag) { n.x = Math.max(24, Math.min(W - 24, n.x + n.vx)); n.y = Math.max(24, Math.min(H - 24, n.y + n.vy)); } n.vx *= 0.82; n.vy *= 0.82; });
    }
    function draw() {
      nEls.forEach(({ n, c, t }) => { c.setAttribute("cx", n.x); c.setAttribute("cy", n.y); t.setAttribute("x", n.x); t.setAttribute("y", n.y + 24); });
      eEls.forEach(({ e, p }) => {
        const a = byId.get(e.s), b = byId.get(e.t);
        if (e.s === e.t) p.setAttribute("d", `M${a.x - 5},${a.y - 9} C${a.x - 40},${a.y - 55} ${a.x + 40},${a.y - 55} ${a.x + 5},${a.y - 9}`);
        else { const mx = (a.x + b.x) / 2 - (b.y - a.y) * 0.08, my = (a.y + b.y) / 2 + (b.x - a.x) * 0.08; p.setAttribute("d", `M${a.x},${a.y} Q${mx},${my} ${b.x},${b.y}`); }
      });
    }
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) { for (let i = 0; i < 250; i++) step(); sim.heat = 0; draw(); return; }
    (function loop() { if (sim.heat > 0) { step(); sim.heat--; } draw(); sim.raf = requestAnimationFrame(loop); })();
  }
  function svgPt(svg, ev) { const pt = svg.createSVGPoint(); pt.x = ev.clientX; pt.y = ev.clientY; return pt.matrixTransform(svg.getScreenCTM().inverse()); }
  function tip(ev, text) {
    const t = $("#tip"); if (!text) { t.hidden = true; return; }
    const r = $(".graphwrap").getBoundingClientRect();
    t.textContent = text; t.hidden = false; t.style.left = Math.min(ev.clientX - r.left + 12, r.width - 200) + "px"; t.style.top = (ev.clientY - r.top + 12) + "px";
  }

  // ---- boot ------------------------------------------------------------
  setStatus("idle"); renderFindings(null); renderGraph(null); initProviders();
})();
