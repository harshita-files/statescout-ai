/**
 * StateScout VS Code extension — Track A.
 *
 * Connects the editor to the local StateScout FastAPI backend (`http://127.0.0.1:8000`)
 * over the `/audits` REST + SSE endpoints while preserving the frozen contract helpers
 * from `@statescout/shared-types`.
 */

import {
  extractConfidenceLabel,
  isAuditTerminal,
  type AuditFinding,
  type AuditReport,
  type ConfidenceLabel,
  type ReportResponse,
  type ScanRun,
  type Severity,
  type StartAuditRequest,
} from "@statescout/shared-types";

/** Commands this extension contributes, kept in sync with `package.json`. */
export const COMMANDS = {
  startScan: "statescout.startScan",
  stopScan: "statescout.stopScan",
  openConsole: "statescout.openConsole",
} as const;

export const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";

const SEVERITY_ORDER: Record<Severity, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
};

/** One-line status text for the editor status bar (legacy ScanRun model). */
export function describeRun(run: ScanRun): string {
  if (run.status === "running") {
    return `StateScout: ${run.counts.states} states, ${run.counts.violations} violations`;
  }
  return `StateScout: ${run.status}`;
}

/** One-line status text for the editor status bar (dynamic AuditReport model). */
export function describeAudit(report: AuditReport): string {
  const states =
    typeof report.stats?.["states"] === "number"
      ? report.stats["states"]
      : (report.graph?.nodes?.length ?? 0);
  const findingsCount = report.findings.length;
  if (report.status === "running") {
    return `StateScout: ${states} states, ${findingsCount} findings (running)`;
  }
  return `StateScout: ${report.status} (${states} states, ${findingsCount} findings)`;
}

/** Violations ordered the way a QA engineer wants to read them. */
export function rankViolations(
  report: ReportResponse,
): ReportResponse["violations"] {
  return [...report.violations].sort(
    (a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity],
  );
}

/** Dynamic audit findings ordered by severity first, then descending confidence. */
export function rankFindings(
  findings: readonly AuditFinding[],
): AuditFinding[] {
  return [...findings].sort((a, b) => {
    const sevDiff = SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity];
    if (sevDiff !== 0) return sevDiff;
    return b.confidence - a.confidence;
  });
}

export interface AuditFormInput {
  url: string;
  policyText?: string;
  allowPrivate?: boolean;
  probabilistic?: boolean;
  probeForms?: boolean;
  respectRobots?: boolean;
  maxStates?: number;
  depthLimit?: number;
}

/** Build a `POST /audits` request payload from the extension config panel. */
export function buildAuditPayload(input: AuditFormInput): StartAuditRequest {
  const rawLines = (input.policyText ?? "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0);

  return {
    url: input.url.trim(),
    allow_private: input.allowPrivate ?? true,
    rules: rawLines,
    auto_rules: true,
    max_states: input.maxStates ?? 40,
    depth_limit: input.depthLimit ?? 3,
    max_seconds: 300,
    requests_per_second: 1.0,
    respect_robots: input.respectRobots ?? true,
    probabilistic: input.probabilistic ?? true,
    probe_forms: input.probeForms ?? false,
  };
}

/** HTTP client wrapping the local FastAPI `/audits` endpoints. */
export class AuditApiClient {
  readonly baseUrl: string;
  private readonly fetchImpl: typeof fetch;

  constructor(
    baseUrl: string = DEFAULT_API_BASE_URL,
    fetchImpl: typeof fetch = fetch,
  ) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
    this.fetchImpl = fetchImpl;
  }

  async startAudit(payload: StartAuditRequest): Promise<{ audit_id: string }> {
    const res = await this.fetchImpl(`${this.baseUrl}/audits`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      throw new Error(`POST /audits failed with HTTP ${res.status}`);
    }
    return (await res.json()) as { audit_id: string };
  }

  async getAudit(auditId: string): Promise<AuditReport> {
    const res = await this.fetchImpl(
      `${this.baseUrl}/audits/${encodeURIComponent(auditId)}`,
    );
    if (!res.ok) {
      throw new Error(`GET /audits/${auditId} failed with HTTP ${res.status}`);
    }
    return (await res.json()) as AuditReport;
  }

  async stopAudit(auditId: string): Promise<void> {
    const res = await this.fetchImpl(
      `${this.baseUrl}/audits/${encodeURIComponent(auditId)}/stop`,
      { method: "POST" },
    );
    if (!res.ok) {
      throw new Error(
        `POST /audits/${auditId}/stop failed with HTTP ${res.status}`,
      );
    }
  }
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/** Render the self-contained HTML for the VS Code Webview panel. */
export function renderAuditWebviewHtml(
  apiBaseUrl: string = DEFAULT_API_BASE_URL,
  report: AuditReport | null = null,
): string {
  const cleanBase = escapeHtml(apiBaseUrl.replace(/\/+$/, ""));
  const ranked = report ? rankFindings(report.findings) : [];
  const rowsHtml = ranked
    .map((f) => {
      const label: ConfidenceLabel = extractConfidenceLabel(f);
      const pct = `${Math.round(f.confidence * 100)}%`;
      const shotLink = f.screenshot
        ? f.screenshot.startsWith("data:")
          ? "Screenshot attached"
          : `<a href="${cleanBase}${escapeHtml(f.screenshot)}" target="_blank" rel="noopener">View screenshot</a>`
        : "—";
      return `<tr>
        <td><span class="sev sev-${escapeHtml(f.severity)}">${escapeHtml(f.severity)}</span></td>
        <td><strong>${pct}</strong> <span class="badge badge-${label}">${label}</span></td>
        <td>
          <div><strong>${escapeHtml(f.title)}</strong></div>
          <div class="muted">${escapeHtml(f.rationale)}</div>
          <div class="url">${escapeHtml(f.url)}</div>
        </td>
        <td>${shotLink}</td>
      </tr>`;
    })
    .join("\n");

  const summaryText = report
    ? escapeHtml(describeAudit(report))
    : "StateScout: ready — connect to local API or open full Audit Console";
  const initialReportJson = JSON.stringify(report).replace(/</g, "\\u003c");

  return `<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>StateScout AI — VS Code Audit Console</title>
  <style>
    :root{--bg:#f5f7fa;--panel:#fff;--fg:#1c2530;--mut:#5d6b7a;--bd:#d8dee6;--acc:#2563eb;--accfg:#fff;--bad:#d9480f;--ok:#15803d;--warn:#92400e;--warnbg:#fef3c7;--edge:#7a8794}
    :root[data-theme=dark]{--bg:#0e1319;--panel:#161d26;--fg:#e6edf3;--mut:#94a3b3;--bd:#2a3542;--acc:#5b9bff;--accfg:#06101f;--bad:#ff8a5c;--ok:#4ade80;--warn:#fcd34d;--warnbg:#3a2f0b;--edge:#8a98a8}
    *{box-sizing:border-box}
    body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
    .top{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 16px;padding:14px 16px;max-width:1360px;margin:auto}
    .top h1{margin:0;font-size:1.35rem}.top h1 span{color:var(--acc)}.sub{margin:0;color:var(--mut);flex:1}
    .layout{display:grid;grid-template-columns:minmax(290px,390px) minmax(0,1fr);gap:16px;max-width:1360px;margin:auto;padding:0 16px 32px}
    @media(max-width:900px){.layout{grid-template-columns:1fr}}
    .panel{background:var(--panel);border:1px solid var(--bd);border-radius:12px;padding:14px;margin-bottom:14px}
    h2{font-size:1.02rem;margin:0 0 8px}h3{font-size:.88rem;margin:14px 0 6px;color:var(--mut);text-transform:uppercase;letter-spacing:.04em}
    label{display:block;font-size:.82rem;color:var(--mut);margin-top:8px}
    input,select,textarea,button{font:inherit}
    input[type=url],input[type=text],input[type=password],input[type=number],input:not([type]),select,textarea{width:100%;padding:7px 9px;border:1px solid var(--bd);border-radius:8px;background:var(--bg);color:var(--fg);margin-top:2px}
    textarea{resize:vertical}
    .check{display:flex;gap:8px;align-items:center;color:var(--fg);font-size:.85rem;margin-top:6px}
    button,.btn-link{padding:7px 13px;border-radius:8px;border:1px solid var(--acc);background:var(--acc);color:var(--accfg);cursor:pointer;font-weight:600;text-decoration:none;display:inline-block;font-size:.85rem}
    button.secondary,.btn-link.secondary{background:transparent;color:var(--acc)}
    button.danger{background:transparent;border-color:var(--bad);color:var(--bad)}
    button:disabled{opacity:.45;cursor:not-allowed}
    .row{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:10px}.between{justify-content:space-between;margin-top:0}
    .grid4{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}
    .note{font-size:.78rem;color:var(--mut);margin:5px 0}.note.warn{background:var(--warnbg);color:var(--warn);padding:6px 8px;border-radius:8px}
    .error{color:var(--bad);font-weight:600}
    .chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
    .chip{font-size:.75rem;padding:2px 9px;border-radius:99px;border:1px solid var(--bd);display:inline-flex;gap:6px;align-items:center}
    .chip.generated{border-color:var(--acc);color:var(--acc)}
    .chip b{font-weight:600;font-size:.66rem;text-transform:uppercase;opacity:.8}
    .badge{padding:2px 9px;border-radius:99px;background:var(--bg);border:1px solid var(--bd);font-size:.78rem}
    .badge.running{color:var(--acc)}.badge.done,.badge-stable{color:var(--ok)}.badge.error{color:var(--bad)}.badge.stopped,.badge-flaky{color:var(--warn)}.badge-insufficient_evidence{color:var(--mut)}
    .stats{display:flex;gap:14px;flex-wrap:wrap;color:var(--mut);font-size:.84rem;margin-bottom:8px}.stats b{color:var(--fg)}
    .log{height:130px;overflow:auto;background:var(--bg);border:1px solid var(--bd);border-radius:8px;padding:8px;margin:0;font:11.5px/1.4 ui-monospace,monospace;white-space:pre-wrap}
    .graphwrap{position:relative}
    #graph{width:100%;height:auto;background:var(--bg);border:1px solid var(--bd);border-radius:8px;touch-action:none}
    #graph .edge{stroke:var(--edge);fill:none;cursor:pointer}#graph .edge:hover,#graph .edge.sel{stroke:var(--acc)}
    #graph .node{fill:var(--acc);stroke:var(--panel);stroke-width:2;cursor:grab}#graph .node.bad{fill:var(--bad)}
    #graph .node.sel{stroke:var(--fg)}#graph text{fill:var(--mut);font-size:10px;text-anchor:middle;pointer-events:none}
    .tip{position:absolute;pointer-events:none;background:var(--panel);border:1px solid var(--bd);border-radius:8px;padding:4px 8px;font-size:.76rem;max-width:260px;box-shadow:0 2px 8px #0003}
    .tablewrap{overflow:auto}table{border-collapse:collapse;width:100%;font-size:.84rem}
    th,td{border-bottom:1px solid var(--bd);padding:8px;text-align:left;vertical-align:top}
    td:nth-child(n+3){overflow-wrap:anywhere}th:nth-child(-n+2),td:nth-child(-n+2){white-space:nowrap}th{color:var(--mut);font-weight:600}
    .sev{display:inline-block;padding:1px 8px;border-radius:6px;font-size:.73rem;font-weight:700;color:#fff;text-transform:uppercase}
    .sev.critical,.sev-critical{background:#b42318}.sev.high,.sev-high{background:#d9480f}.sev.medium,.sev-medium{background:#b7791f}.sev.low,.sev-low{background:#2f6fb0}
    .shot{max-width:150px;cursor:zoom-in;border-radius:6px;border:1px solid var(--bd)}
    .blk{margin-top:10px;padding:8px 10px;border-radius:8px;background:var(--warnbg);color:var(--warn);font-size:.82rem}
    .muted{color:var(--mut);font-size:.8rem;margin-top:2px}
    .url{color:var(--acc);font-size:.76rem;margin-top:2px}
  </style>
</head>
<body>
  <header class="top">
    <h1>StateScout <span>AI</span></h1>
    <p class="sub" id="status-banner">${summaryText}</p>
    <button id="theme" type="button" class="secondary">Theme</button>
    <a class="btn-link secondary" href="${cleanBase}/" target="_blank" rel="noopener">Browser UI (${cleanBase})</a>
  </header>

  <main id="main" class="layout">
    <form id="form" class="panel" autocomplete="off">
      <h2>Audit setup</h2>
      <label for="url">Site URL</label>
      <input id="url" type="url" required placeholder="https://example.com" value="${escapeHtml(report?.url ?? "")}" />
      <label class="check"><input id="allow_private" type="checkbox" /> Allow private/internal IP range (my own network only)</label>

      <h3>Rules</h3>
      <label for="rules">One rule per line, in plain language</label>
      <textarea id="rules" rows="5" placeholder="Guests must never see an admin link&#10;Cart total must match the sum of items"></textarea>
      <div class="row">
        <button id="gen" type="button" class="secondary">Generate rules from site</button>
        <label class="check"><input id="auto_rules" type="checkbox" checked /> Auto-generate if none</label>
      </div>
      <div id="chips" class="chips" aria-live="polite"></div>

      <h3>Models</h3>
      <div class="grid2" style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
        <fieldset class="prov" data-kind="llm" style="border:1px solid var(--bd);border-radius:10px;padding:8px 10px 12px;min-width:0"><legend style="padding:0 6px;font-weight:600;font-size:.82rem">LLM (reasoning)</legend>
          <label>Provider <select class="p-provider"></select></label>
          <label>Model <input class="p-model" list="models-llm" placeholder="model name" /></label>
          <datalist id="models-llm"></datalist>
          <label>Base URL <input class="p-base" type="url" placeholder="default" /></label>
          <label>API key <input class="p-key" type="password" autocomplete="new-password" placeholder="kept in memory only" /></label>
          <button type="button" class="secondary p-test" style="margin-top:8px">Test connection</button>
          <span class="p-status note" role="status"></span>
        </fieldset>
        <fieldset class="prov" data-kind="vlm" style="border:1px solid var(--bd);border-radius:10px;padding:8px 10px 12px;min-width:0"><legend style="padding:0 6px;font-weight:600;font-size:.82rem">VLM (vision)</legend>
          <label>Provider <select class="p-provider"></select></label>
          <label>Model <input class="p-model" list="models-vlm" placeholder="model name" /></label>
          <datalist id="models-vlm"></datalist>
          <label>Base URL <input class="p-base" type="url" placeholder="default" /></label>
          <label>API key <input class="p-key" type="password" autocomplete="new-password" placeholder="kept in memory only" /></label>
          <button type="button" class="secondary p-test" style="margin-top:8px">Test connection</button>
          <span class="p-status note" role="status"></span>
        </fieldset>
      </div>
      <p class="note">API keys are sent only with your request, held in memory, never logged, stored or included in reports.</p>

      <h3>Crawl limits</h3>
      <div class="grid4">
        <label>Max states <input id="max_states" type="number" min="1" max="500" value="40" /></label>
        <label>Depth <input id="depth_limit" type="number" min="0" max="10" value="3" /></label>
        <label>Max seconds <input id="max_seconds" type="number" min="5" max="3600" value="300" /></label>
        <label>Req/sec <input id="rps" type="number" min="0.1" max="20" step="0.1" value="1" /></label>
      </div>
      <label class="check"><input id="robots" type="checkbox" checked /> Respect robots.txt</label>
      <p class="note warn">Only audit sites you own or are authorized to test. Disabling robots.txt is for those sites only.</p>
      <label class="check"><input id="prob" type="checkbox" checked /> Probabilistic mode (transition probabilities and confidence)</label>
      <label class="check"><input id="probe_forms" type="checkbox" /> Submit invalid values to forms</label>
      <p class="note warn">Sends a negative and a huge number to numeric forms to check they are rejected. It submits data, so it only runs against localhost or your own network, never public sites.</p>

      <div class="row">
        <button id="start" type="submit">Start audit</button>
        <button id="stop" type="button" class="danger" disabled>Stop</button>
      </div>
      <p id="err" class="error" role="alert" hidden></p>
    </form>

    <section class="results">
      <div class="panel">
        <div class="row between"><h2>Progress</h2><span id="status" class="badge">${escapeHtml(report?.status ?? "idle")}</span></div>
        <div id="stats" class="stats"></div>
        <pre id="log" class="log" tabindex="0" aria-live="polite"></pre>
      </div>

      <div class="panel">
        <div class="row between"><h2>Exploration graph</h2><span class="note">Edge weight = transition probability</span></div>
        <div class="graphwrap">
          <svg id="graph" viewBox="0 0 800 440" role="img" aria-label="Interactive state graph"></svg>
          <div id="tip" class="tip" hidden></div>
        </div>
        <div id="detail" class="note">Hover or click a node or edge for details. Drag nodes to move them.</div>
      </div>

      <div class="panel">
        <div class="row between">
          <h2>Violations</h2>
          <div class="row">
            <button type="button" class="secondary exp" data-f="html">HTML</button>
            <button type="button" class="secondary exp" data-f="json">JSON</button>
            <button type="button" class="secondary exp" data-f="md">Markdown</button>
          </div>
        </div>
        <div class="tablewrap">
          <table id="vtable">
            <thead>
              <tr><th>Severity</th><th>Confidence</th><th>Finding</th><th>Evidence</th><th>Screenshot</th></tr>
            </thead>
            <tbody id="findings-body">
              ${rowsHtml || '<tr><td colspan="5" class="muted">No violations found.</td></tr>'}
            </tbody>
          </table>
        </div>
        <div id="blocked"></div>
      </div>
    </section>
  </main>

  <script>
    (() => {
      const API_BASE = "${cleanBase}";
      const INITIAL_REPORT = ${initialReportJson};
      const $ = (s, r = document) => r.querySelector(s);
      const $$ = (s, r = document) => [...r.querySelectorAll(s)];
      const NS = "http://www.w3.org/2000/svg";
      const state = { auditId: INITIAL_REPORT ? INITIAL_REPORT.audit_id : null, generated: [], abort: null, report: INITIAL_REPORT };
      const BLOCK_TEXT = { robots: "Blocked by robots.txt", captcha: "CAPTCHA wall", login_wall: "Login wall", consent_wall: "Consent wall", rate_limit: "Rate limited", cap: "Crawl cap reached" };

      async function api(path, opts = {}) {
        const url = path.startsWith("http") ? path : API_BASE + path;
        const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
        const r = await fetch(url, { ...opts, headers });
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
        const p = $("#log");
        if (!p) return;
        p.textContent += msg + "\\n";
        p.scrollTop = p.scrollHeight;
      };
      const showErr = (m) => {
        const e = $("#err");
        if (!e) return;
        e.textContent = m || "";
        e.hidden = !m;
      };

      $("#theme")?.addEventListener("click", () => {
        const cur = document.documentElement.dataset.theme || "dark";
        document.documentElement.dataset.theme = cur === "dark" ? "light" : "dark";
      });

      const userRules = () => ($("#rules")?.value || "").split("\\n").map((s) => s.trim()).filter(Boolean);
      function renderChips(rep) {
        const box = $("#chips");
        if (!box) return;
        box.replaceChildren();
        const rulesList = rep && rep.rules && rep.rules.length
          ? rep.rules
          : userRules().map((r) => ({ text: r, source: state.generated.includes(r) ? "generated" : "user", kind: "" }));
        rulesList.forEach((r) => {
          const isGen = r.source === "generated";
          const c = el("span", { class: "chip" + (isGen ? " generated" : "") });
          c.appendChild(el("b", {}, isGen ? "generated" : "user"));
          c.appendChild(document.createTextNode(r.text));
          box.appendChild(c);
        });
      }
      $("#rules")?.addEventListener("input", () => renderChips(null));

      function provCfg(fs) {
        if (!fs) return null;
        const provider = $(".p-provider", fs)?.value;
        if (!provider) return null;
        const model = ($(".p-model", fs)?.value || "").trim();
        if (!model) return null;
        const c = { provider, model };
        const b = ($(".p-base", fs)?.value || "").trim();
        if (b) c.base_url = b;
        const k = $(".p-key", fs)?.value;
        if (k) c.api_key = k;
        return c;
      }

      async function initProviders() {
        let data = { providers: [], ollama: {} };
        try { data = await (await api("/providers")).json(); } catch {}
        const providers = data.providers || [];
        const ollamaModels = (data.ollama && data.ollama.models) || [];
        $$(".prov").forEach((fs) => {
          const sel = $(".p-provider", fs);
          if (!sel) return;
          sel.replaceChildren();
          const names = providers.length ? providers.map((p) => p.name) : ["ollama", "gemini", "openai", "anthropic"];
          sel.appendChild(el("option", { value: "" }, "None (built-in heuristics)"));
          names.forEach((n) => sel.appendChild(el("option", { value: n }, n)));
          sel.value = "";
          const updateModels = () => {
            const kind = fs.dataset.kind;
            const p = providers.find((x) => x.name === sel.value);
            let models = (p && p.default_models && p.default_models[kind]) || [];
            if (sel.value === "ollama" && ollamaModels.length) models = ollamaModels;
            const dl = $("datalist", fs);
            if (dl) { dl.replaceChildren(); models.forEach((m) => dl.appendChild(el("option", { value: m }))); }
            const inp = $(".p-model", fs);
            if (inp && !inp.value && models[0]) inp.value = models[0];
          };
          sel.addEventListener("change", () => {
            const inp = $(".p-model", fs);
            if (inp) inp.value = "";
            updateModels();
          });
          updateModels();
          $(".p-test", fs)?.addEventListener("click", async () => {
            const st = $(".p-status", fs);
            if (st) st.textContent = "Testing...";
            const cfg = provCfg(fs) || { provider: sel.value, model: "x" };
            try {
              const r = await (await api("/providers/test", { method: "POST", body: JSON.stringify(cfg) })).json();
              if (st) st.textContent = r.ok ? "Connected (" + (r.models?.length || 0) + " models)" : "Failed: " + (r.error || "unreachable");
            } catch (e) {
              if (st) st.textContent = "Failed: " + e.message;
            }
          });
        });
      }

      $("#gen")?.addEventListener("click", async () => {
        showErr("");
        const url = $("#url").value.trim();
        if (!url) return showErr("Enter a URL first.");
        const b = $("#gen");
        b.disabled = true;
        b.textContent = "Generating...";
        try {
          const body = { url, allow_private: $("#allow_private").checked };
          const llm = provCfg($('.prov[data-kind="llm"]'));
          if (llm) body.llm = llm;
          const r = await (await api("/rules/generate", { method: "POST", body: JSON.stringify(body) })).json();
          const have = new Set(userRules());
          const add = (r.rules || []).filter((x) => !have.has(x));
          state.generated.push(...add);
          $("#rules").value = [...userRules(), ...add].join("\\n");
          renderChips(null);
          log("Generated " + add.length + " rule(s) from target site.");
        } catch (e) {
          showErr("Rule generation failed: " + e.message);
        }
        b.disabled = false;
        b.textContent = "Generate rules from site";
      });

      function setStatus(s) {
        const b = $("#status");
        if (b) { b.textContent = s; b.className = "badge " + s; }
        const running = s === "running" || s === "stopping";
        if ($("#start")) $("#start").disabled = running;
        if ($("#stop")) $("#stop").disabled = !running;
      }

      $("#form")?.addEventListener("submit", async (ev) => {
        ev.preventDefault();
        showErr("");
        $("#log").textContent = "";
        const body = {
          url: $("#url").value.trim(),
          rules: userRules(),
          auto_rules: $("#auto_rules").checked,
          caps: {
            max_states: +$("#max_states").value,
            depth_limit: +$("#depth_limit").value,
            max_seconds: +$("#max_seconds").value,
            requests_per_second: +$("#rps").value,
          },
          respect_robots: $("#robots").checked,
          probabilistic: $("#prob").checked,
          probe_forms: $("#probe_forms").checked,
          allow_private: $("#allow_private").checked,
        };
        const llm = provCfg($('.prov[data-kind="llm"]'));
        const vlm = provCfg($('.prov[data-kind="vlm"]'));
        if (llm) body.llm = llm;
        if (vlm) body.vlm = vlm;
        try {
          const r = await (await api("/audits", { method: "POST", body: JSON.stringify(body) })).json();
          state.auditId = r.audit_id;
          setStatus("running");
          log("Audit " + r.audit_id + " started against " + body.url);
          stream(r.audit_id);
        } catch (e) {
          showErr(e.message);
        }
      });

      $("#stop")?.addEventListener("click", async () => {
        if (!state.auditId) return;
        try {
          await api("/audits/" + state.auditId + "/stop", { method: "POST" });
          setStatus("stopping");
          log("Stop requested...");
        } catch (e) {
          showErr(e.message);
        }
      });

      async function stream(id) {
        const ctl = new AbortController();
        state.abort = ctl;
        try {
          const res = await fetch(API_BASE + "/audits/" + id + "/events", { signal: ctl.signal });
          const reader = res.body.getReader(), dec = new TextDecoder();
          let buf = "";
          for (;;) {
            const { value, done } = await reader.read();
            if (done) break;
            buf += dec.decode(value, { stream: true });
            let i;
            while ((i = buf.indexOf("\\n\\n")) >= 0) {
              handleEvent(buf.slice(0, i));
              buf = buf.slice(i + 2);
            }
          }
        } catch (e) {
          if (e.name !== "AbortError") log("Stream note: " + e.message);
        }
        await refresh(id);
      }

      let lastPoll = 0;
      function handleEvent(raw) {
        let type = "message", data = "";
        raw.split("\\n").forEach((l) => {
          if (l.startsWith("event: ")) type = l.slice(7);
          else if (l.startsWith("data: ")) data += l.slice(6);
        });
        if (!data) return;
        let d;
        try { d = JSON.parse(data); } catch { return; }
        if (type === "status") {
          setStatus(d.status);
          log("Status: " + d.status + (d.error ? " (" + d.error + ")" : ""));
        } else if (type === "log") {
          log([d.node, d.event, d.message].filter(Boolean).join(" "));
        } else {
          log("progress " + (d.message || JSON.stringify(d.stats || d).slice(0, 140)));
          if (Date.now() - lastPoll > 1200) {
            lastPoll = Date.now();
            refresh(state.auditId, true);
          }
        }
      }

      async function refresh(id, quiet) {
        try {
          const rep = await (await api("/audits/" + id)).json();
          applyReport(rep, quiet);
        } catch (e) {
          if (!quiet) showErr(e.message);
        }
      }

      function applyReport(rep, quiet) {
        if (!rep) return;
        state.report = rep;
        state.auditId = rep.audit_id || state.auditId;
        renderStats(rep);
        renderChips(rep);
        renderGraph(rep);
        renderFindings(rep);
        if (!quiet) setStatus(rep.status || "done");
        const banner = $("#status-banner");
        if (banner) {
          const stCount = (rep.graph?.nodes || []).length;
          const fnCount = (rep.findings || []).length;
          banner.textContent = "StateScout: " + rep.status + " (" + stCount + " states, " + fnCount + " findings)";
        }
      }

      function renderStats(rep) {
        const s = $("#stats");
        if (!s || !rep) return;
        s.replaceChildren();
        const items = {
          states: (rep.graph?.nodes || []).length,
          transitions: (rep.graph?.edges || []).length,
          violations: (rep.findings || []).length,
          ...(rep.stats || {}),
        };
        for (const [k, raw] of Object.entries(items)) {
          const v = Array.isArray(raw) ? raw.length + " item(s)" : raw && typeof raw === "object" ? Object.keys(raw).length + " entries" : raw;
          const sp = el("span");
          sp.append(k + ": ");
          sp.appendChild(el("b", {}, String(v)));
          s.appendChild(sp);
        }
      }

      function renderFindings(rep) {
        const tb = $("#findings-body");
        if (!tb || !rep) return;
        tb.replaceChildren();
        $("#blocked")?.replaceChildren();
        if (!rep.findings || !rep.findings.length) {
          const tr = el("tr");
          tr.appendChild(el("td", { colspan: "5" }, rep.status === "running" ? "Waiting for results..." : "No violations found."));
          tb.appendChild(tr);
          return;
        }
        const SEV = { low: 0, medium: 1, high: 2, critical: 3 };
        const groups = new Map();
        rep.findings.forEach((f) => {
          const key = f.group_key || f.title + "|" + ((f.evidence && f.evidence[0]) || "");
          if (!groups.has(key)) groups.set(key, []);
          groups.get(key).push(f);
        });
        const short = (t, n) => (t && t.length > n ? t.slice(0, n) + "..." : (t || ""));
        [...groups.values()]
          .sort((x, y) => (SEV[y[0].severity] || 0) - (SEV[x[0].severity] || 0) || y.length - x.length)
          .forEach((list) => {
            const f = list.reduce((w, c) => ((SEV[c.severity] || 0) > (SEV[w.severity] || 0) ? c : w), list[0]);
            const tr = el("tr");
            const t1 = el("td");
            t1.appendChild(el("span", { class: "sev " + f.severity }, f.severity));
            tr.appendChild(t1);
            const pct = (Math.max(...list.map((x) => x.confidence ?? 1)) * 100).toFixed(0) + "%";
            const m = /\\[(stable|flaky|insufficient_evidence)\\]/.exec(f.rationale || "");
            const lbl = m ? m[1] : "stable";
            const t2 = el("td");
            t2.appendChild(el("strong", {}, pct + " "));
            t2.appendChild(el("span", { class: "badge badge-" + lbl }, lbl));
            tr.appendChild(t2);
            const t3 = el("td");
            t3.appendChild(el("strong", {}, f.title));
            if (list.length > 1) t3.appendChild(el("span", { class: "note" }, "  x" + list.length + " pages"));
            t3.appendChild(el("div", { class: "muted" }, short(f.rationale, 260)));
            const det = el("details");
            det.appendChild(el("summary", { class: "note" }, list.length > 1 ? "Show all " + list.length + " pages" : f.url));
            list.forEach((x) => det.appendChild(el("div", { class: "url" }, x.url)));
            t3.appendChild(det);
            tr.appendChild(t3);
            const t4 = el("td");
            const ul = el("ul");
            (f.evidence || []).slice(0, 4).forEach((x) => ul.appendChild(el("li", {}, short(x, 140))));
            t4.appendChild(ul);
            tr.appendChild(t4);
            const t5 = el("td");
            if (f.screenshot && f.screenshot.startsWith("data:image/")) {
              const img = el("img", { class: "shot", alt: "Screenshot for " + f.title, src: f.screenshot });
              img.addEventListener("click", () => window.open(f.screenshot, "_blank", "noopener"));
              t5.appendChild(img);
            } else if (f.screenshot && f.screenshot.startsWith("/audits/")) {
              const fullShot = API_BASE + f.screenshot;
              const img = el("img", { class: "shot", alt: "Screenshot for " + f.title, src: fullShot });
              img.addEventListener("click", () => window.open(fullShot, "_blank", "noopener"));
              t5.appendChild(img);
            } else {
              t5.appendChild(el("span", { class: "note" }, "no screenshot"));
            }
            tr.appendChild(t5);
            tb.appendChild(tr);
            tr.addEventListener("mouseenter", () => highlight(f.state_id));
          });
        (rep.blocked || []).forEach((b) => $("#blocked")?.appendChild(el("div", { class: "blk" }, (BLOCK_TEXT[b.reason] || b.reason) + ": " + b.url)));
        if (rep.error) $("#blocked")?.appendChild(el("div", { class: "blk" }, "Error: " + rep.error));
      }

      const W = 800, H = 440;
      let sim = null;
      function highlight(id) { $$("#graph .node").forEach((n) => n.classList.toggle("sel", n.dataset.id === id)); }
      function renderGraph(rep) {
        const svg = $("#graph");
        if (!svg) return;
        svg.replaceChildren();
        if (sim) cancelAnimationFrame(sim.raf);
        sim = null;
        if (!rep) return;
        const g = rep.graph || {}, bad = new Set((rep.findings || []).map((f) => f.state_id));
        const nodes = new Map();
        const add = (id, label, v) => {
          if (!nodes.has(id)) {
            const a = nodes.size * 2.4;
            nodes.set(id, { id, label: label || id, x: W / 2 + 120 * Math.cos(a) * (1 + nodes.size / 20), y: H / 2 + 120 * Math.sin(a) * (1 + nodes.size / 20), vx: 0, vy: 0, bad: bad.has(id) || !!v });
          }
        };
        (g.nodes || []).forEach((n) => typeof n === "object" ? add(String(n.id ?? n.state_id), n.label || n.url, n.violation) : add(String(n)));
        const edges = (g.edges || []).map((e) => ({ s: String(e.source ?? e.from ?? e.src), t: String(e.target ?? e.to ?? e.dst), p: Math.max(0, Math.min(1, +(e.probability ?? e.p ?? e.weight ?? 1))), a: e.action || e.action_id || "" }));
        edges.forEach((e) => { add(e.s); add(e.t); });
        if (!nodes.size) {
          const t = document.createElementNS(NS, "text");
          t.setAttribute("x", W / 2);
          t.setAttribute("y", H / 2);
          t.textContent = "No graph yet";
          svg.appendChild(t);
          return;
        }
        const defs = document.createElementNS(NS, "defs");
        defs.innerHTML = '<marker id="arr" viewBox="0 0 10 10" refX="18" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0,0L10,5L0,10z" fill="#7a8794"/></marker>';
        svg.appendChild(defs);
        const list = [...nodes.values()];
        const eEls = edges.map((e) => {
          const p = document.createElementNS(NS, "path");
          p.setAttribute("class", "edge");
          p.setAttribute("stroke-width", (1 + 4 * e.p).toFixed(1));
          p.setAttribute("opacity", (0.25 + 0.75 * e.p).toFixed(2));
          p.setAttribute("marker-end", "url(#arr)");
          svg.appendChild(p);
          const info = e.s + " → " + e.t + " | p=" + e.p.toFixed(2) + (e.s === e.t ? " (self-loop)" : "") + (e.a ? " | " + e.a : "");
          p.addEventListener("click", () => { $("#detail").textContent = "Transition: " + info; });
          return { e, p };
        });
        const nEls = list.map((n) => {
          const gEl = document.createElementNS(NS, "g"), c = document.createElementNS(NS, "circle"), t = document.createElementNS(NS, "text");
          c.setAttribute("class", "node" + (n.bad ? " bad" : ""));
          c.setAttribute("r", n.bad ? 12 : 8);
          c.dataset.id = n.id;
          t.textContent = n.label.length > 28 ? n.label.slice(0, 27) + "..." : n.label;
          gEl.appendChild(c);
          gEl.appendChild(t);
          svg.appendChild(gEl);
          const finds = (rep.findings || []).filter((f) => f.state_id === n.id);
          const info = n.label + (n.bad ? " | violation" : "") + (finds.length ? ": " + finds.map((f) => f.title).join("; ") : "");
          c.addEventListener("click", () => { highlight(n.id); $("#detail").textContent = "State " + n.id + " | " + info; });
          return { n, gEl, c, t };
        });
        const byId = nodes;
        function step() {
          const k = Math.sqrt((W * H) / list.length) * 0.7;
          for (let i = 0; i < list.length; i++) for (let j = i + 1; j < list.length; j++) {
            const a = list[i], b = list[j];
            let dx = a.x - b.x, dy = a.y - b.y, d = Math.hypot(dx, dy) || 0.1;
            const f = (k * k) / d / d * 0.5;
            a.vx += dx * f; a.vy += dy * f; b.vx -= dx * f; b.vy -= dy * f;
          }
          edges.forEach((e) => {
            if (e.s === e.t) return;
            const a = byId.get(e.s), b = byId.get(e.t);
            const dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy) || 0.1;
            const f = (d - k) / d * 0.04 * (0.4 + e.p);
            a.vx += dx * f; a.vy += dy * f; b.vx -= dx * f; b.vy -= dy * f;
          });
          list.forEach((n) => {
            n.vx += (W / 2 - n.x) * 0.004;
            n.vy += (H / 2 - n.y) * 0.004;
            n.x = Math.max(24, Math.min(W - 24, n.x + n.vx));
            n.y = Math.max(24, Math.min(H - 24, n.y + n.vy));
            n.vx *= 0.82;
            n.vy *= 0.82;
          });
        }
        for (let i = 0; i < 220; i++) step();
        nEls.forEach(({ n, c, t }) => { c.setAttribute("cx", n.x); c.setAttribute("cy", n.y); t.setAttribute("x", n.x); t.setAttribute("y", n.y + 24); });
        eEls.forEach(({ e, p }) => {
          const a = byId.get(e.s), b = byId.get(e.t);
          if (e.s === e.t) p.setAttribute("d", "M" + (a.x - 5) + "," + (a.y - 9) + " C" + (a.x - 40) + "," + (a.y - 55) + " " + (a.x + 40) + "," + (a.y - 55) + " " + (a.x + 5) + "," + (a.y - 9));
          else {
            const mx = (a.x + b.x) / 2 - (b.y - a.y) * 0.08, my = (a.y + b.y) / 2 + (b.x - a.x) * 0.08;
            p.setAttribute("d", "M" + a.x + "," + a.y + " Q" + mx + "," + my + " " + b.x + "," + b.y);
          }
        });
      }

      $$(".exp").forEach((b) => b.addEventListener("click", async () => {
        if (!state.auditId) return showErr("Run an audit first.");
        try {
          const r = await api("/audits/" + state.auditId + "/report?format=" + b.dataset.f);
          const blob = await r.blob(), a = el("a", { href: URL.createObjectURL(blob), download: "statescout-" + state.auditId + "." + b.dataset.f });
          document.body.appendChild(a); a.click(); a.remove();
        } catch (e) { showErr(e.message); }
      }));

      // Boot with initial report if explicitly provided, otherwise start clean in idle state
      initProviders();
      if (INITIAL_REPORT) {
        applyReport(INITIAL_REPORT, false);
      } else {
        setStatus("idle");
        renderGraph(null);
        renderChips(null);
      }
    })();
  </script>
</body>
</html>`;
}

// ---------------------------------------------------------------------------
// Minimal structural types for the VS Code extension host
// ---------------------------------------------------------------------------

export interface Disposable {
  dispose(): void;
}

export interface StatusBarItem extends Disposable {
  text: string;
  tooltip?: string;
  command?: string;
  show(): void;
}

export interface Webview {
  html: string;
  options?: { enableScripts?: boolean };
  onDidReceiveMessage?: (listener: (msg: unknown) => void) => Disposable;
}

export interface WebviewView {
  webview: Webview;
}

export interface WebviewPanel extends Disposable {
  webview: Webview;
  reveal(): void;
  onDidDispose?: (listener: () => void) => Disposable;
}

export interface ExtensionContext {
  subscriptions: Disposable[];
}

export interface VscodeHostApi {
  commands: {
    registerCommand(
      command: string,
      callback: (...args: unknown[]) => unknown,
    ): Disposable;
  };
  window: {
    createStatusBarItem(alignment?: number, priority?: number): StatusBarItem;
    createWebviewPanel(
      viewType: string,
      title: string,
      showOptions: number,
      options: { enableScripts: boolean },
    ): WebviewPanel;
    registerWebviewViewProvider?(
      viewId: string,
      provider: { resolveWebviewView(webviewView: WebviewView): void },
    ): Disposable;
    showInformationMessage(message: string): void;
    showErrorMessage(message: string): void;
  };
  workspace?: {
    workspaceFolders?: ReadonlyArray<{ uri: { fsPath: string } }>;
  };
}

let activeAuditId: string | null = null;
let activePanel: WebviewPanel | null = null;
let pollTimer: ReturnType<typeof setInterval> | null = null;

function resolveNodeRequire(): ((id: string) => unknown) | undefined {
  try {
    if (typeof require === "function") return require as unknown as (id: string) => unknown;
    return eval("require") as (id: string) => unknown;
  } catch {
    return undefined;
  }
}

function resolveVscodeHost(): VscodeHostApi | undefined {
  try {
    const req = resolveNodeRequire();
    return req ? (req("vscode") as VscodeHostApi) : undefined;
  } catch {
    return undefined;
  }
}

async function ensureLocalServersRunning(host: VscodeHostApi, apiBaseUrl: string): Promise<void> {
  try {
    const root = host.workspace?.workspaceFolders?.[0]?.uri?.fsPath;
    if (!root) return;
    const req = resolveNodeRequire();
    if (!req) return;
    const fs = req("fs") as { existsSync(p: string): boolean };
    const path = req("path") as { join(...parts: string[]): string };
    const cp = req("child_process") as {
      spawn(
        cmd: string,
        args: string[],
        opts: Record<string, unknown>,
      ): { unref(): void };
    };
    const pyWin = path.join(root, ".venv", "Scripts", "python.exe");
    const pyUnix = path.join(root, ".venv", "bin", "python");
    const pythonExe = fs.existsSync(pyWin) ? pyWin : fs.existsSync(pyUnix) ? pyUnix : null;
    if (!pythonExe) return;

    const checkUrl = async (u: string): Promise<boolean> => {
      try {
        const res = await fetch(u);
        return res.ok;
      } catch {
        return false;
      }
    };

    if (!(await checkUrl("http://127.0.0.1:8765/"))) {
      cp.spawn(pythonExe, ["test-apps/stockwatch/server.py", "--port", "8765", "--seed", "7"], {
        cwd: root,
        detached: true,
        stdio: "ignore",
        windowsHide: true,
      }).unref();
    }
    if (!(await checkUrl("http://127.0.0.1:4173/"))) {
      cp.spawn(pythonExe, ["test-apps/stockwatch/server.py", "--port", "4173", "--seed", "7"], {
        cwd: root,
        detached: true,
        stdio: "ignore",
        windowsHide: true,
      }).unref();
    }
    if (!(await checkUrl(`${apiBaseUrl.replace(/\/+$/, "")}/health`))) {
      cp.spawn(
        pythonExe,
        ["-m", "uvicorn", "services.api.main:app", "--host", "127.0.0.1", "--port", "8000"],
        {
          cwd: root,
          detached: true,
          stdio: "ignore",
          windowsHide: true,
        },
      ).unref();
    }
  } catch {
    // Best-effort local server bootstrap
  }
}

/** Activate the extension in the VS Code host. */
export function activate(
  context: ExtensionContext,
  host?: VscodeHostApi,
  client: AuditApiClient = new AuditApiClient(),
): void {
  const resolvedHost = host ?? resolveVscodeHost();
  if (!resolvedHost) return;

  if (!host) {
    void ensureLocalServersRunning(resolvedHost, client.baseUrl);
  }

  const statusBar = resolvedHost.window.createStatusBarItem(1, 100);
  statusBar.text = "$(shield) StateScout: idle";
  statusBar.tooltip = "Click to open StateScout AI Audit Console";
  statusBar.command = COMMANDS.openConsole;
  statusBar.show();

  const stopPolling = (): void => {
    if (pollTimer !== null) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  };

  const openPanel = (report: AuditReport | null = null): WebviewPanel => {
    if (!activePanel) {
      activePanel = resolvedHost.window.createWebviewPanel(
        "statescoutAuditConsole",
        "StateScout AI Audit Console",
        1,
        { enableScripts: true },
      );
      activePanel.onDidDispose?.(() => {
        activePanel = null;
      });
      activePanel.webview.onDidReceiveMessage?.((msg: unknown) => {
        if (!msg || typeof msg !== "object") return;
        const m = msg as Record<string, unknown>;
        if (m["type"] === "startAudit") {
          void runStartScan({
            url: typeof m["url"] === "string" ? m["url"] : undefined,
            policyText: typeof m["policyText"] === "string" ? m["policyText"] : undefined,
          });
        } else if (m["type"] === "stopAudit") {
          void runStopScan();
        }
      });
    }
    activePanel.webview.html = renderAuditWebviewHtml(client.baseUrl, report);
    activePanel.reveal();
    return activePanel;
  };

  const runStartScan = async (input?: Partial<AuditFormInput>): Promise<void> => {
    try {
      if (!host) {
        await ensureLocalServersRunning(resolvedHost, client.baseUrl);
      }
      const payload = buildAuditPayload({
        url: input?.url ?? "http://127.0.0.1:8765/",
        policyText: input?.policyText,
        allowPrivate: input?.allowPrivate ?? true,
        probabilistic: input?.probabilistic ?? true,
        probeForms: input?.probeForms ?? false,
      });
      const { audit_id } = await client.startAudit(payload);
      activeAuditId = audit_id;
      statusBar.text = `$(sync~spin) StateScout: running (${audit_id})`;
      const report = await client.getAudit(audit_id);
      statusBar.text = `$(shield) ${describeAudit(report)}`;
      openPanel(report);
      if (isAuditTerminal(report)) {
        activeAuditId = null;
        stopPolling();
      } else if (!host) {
        stopPolling();
        pollTimer = setInterval(async () => {
          if (!activeAuditId) {
            stopPolling();
            return;
          }
          try {
            const latest = await client.getAudit(activeAuditId);
            statusBar.text = `$(shield) ${describeAudit(latest)}`;
            if (activePanel) {
              activePanel.webview.html = renderAuditWebviewHtml(client.baseUrl, latest);
            }
            if (isAuditTerminal(latest)) {
              activeAuditId = null;
              stopPolling();
            }
          } catch {
            stopPolling();
          }
        }, 2000);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      statusBar.text = "$(error) StateScout: error";
      resolvedHost.window.showErrorMessage(`StateScout scan failed: ${msg}`);
    }
  };

  const runStopScan = async (): Promise<void> => {
    if (!activeAuditId) {
      resolvedHost.window.showInformationMessage("StateScout: No active audit running.");
      return;
    }
    try {
      await client.stopAudit(activeAuditId);
      statusBar.text = "$(shield) StateScout: stopped";
      activeAuditId = null;
      stopPolling();
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      resolvedHost.window.showErrorMessage(`StateScout stop failed: ${msg}`);
    }
  };

  const startDisp = resolvedHost.commands.registerCommand(
    COMMANDS.startScan,
    async (input?: Partial<AuditFormInput>) => {
      await runStartScan(input);
    },
  );

  const stopDisp = resolvedHost.commands.registerCommand(COMMANDS.stopScan, async () => {
    await runStopScan();
  });

  const openDisp = resolvedHost.commands.registerCommand(COMMANDS.openConsole, () => {
    openPanel(null);
  });

  if (resolvedHost.window.registerWebviewViewProvider) {
    const sidebarDisp = resolvedHost.window.registerWebviewViewProvider("statescout.sidebarView", {
      resolveWebviewView(webviewView: WebviewView): void {
        if (webviewView.webview.options) {
          webviewView.webview.options = { enableScripts: true };
        }
        webviewView.webview.html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <style>
    body { font-family: system-ui, -apple-system, sans-serif; padding: 12px; margin: 0; color: var(--vscode-foreground, #e6edf3); background: transparent; }
    .card { border: 1px solid var(--vscode-panel-border, #2a3542); border-radius: 8px; padding: 12px; margin-bottom: 12px; background: rgba(255,255,255,0.03); }
    h3 { margin: 0 0 6px; font-size: 13px; }
    p { margin: 4px 0; font-size: 12px; opacity: 0.85; }
    button { width: 100%; padding: 8px 10px; margin-top: 8px; border-radius: 6px; border: none; background: #2563eb; color: #fff; font-weight: 600; cursor: pointer; font-size: 12.5px; }
    button.sec { background: transparent; border: 1px solid #2563eb; color: #5b9bff; }
    .pill { display: inline-block; padding: 2px 8px; border-radius: 99px; font-size: 11px; font-weight: 600; background: rgba(59,130,246,0.18); color: #93c5fd; margin-top: 4px; }
  </style>
</head>
<body>
  <div class="card">
    <h3>StateScout AI</h3>
    <p>Autonomous Logical UI Auditor</p>
    <div class="pill">Idle · Ready to audit</div>
    <button id="open-btn" type="button">Open Audit Console</button>
    <button id="scan-btn" class="sec" type="button">Start New Audit</button>
  </div>
  <script>
    const vscode = typeof acquireVsCodeApi === "function" ? acquireVsCodeApi() : null;
    document.getElementById("open-btn")?.addEventListener("click", () => vscode?.postMessage({ type: "openConsole" }));
    document.getElementById("scan-btn")?.addEventListener("click", () => vscode?.postMessage({ type: "openConsole" }));
  </script>
</body>
</html>`;
        webviewView.webview.onDidReceiveMessage?.((msg: unknown) => {
          if (!msg || typeof msg !== "object") return;
          const m = msg as Record<string, unknown>;
          if (m["type"] === "openConsole") {
            openPanel(null);
          } else if (m["type"] === "startAudit") {
            void runStartScan();
          }
        });
        openPanel(null);
      },
    });
    context.subscriptions.push(sidebarDisp);
  }

  context.subscriptions.push(statusBar, startDisp, stopDisp, openDisp);
}

export function deactivate(): void {
  if (pollTimer !== null) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
  activeAuditId = null;
  activePanel = null;
}
