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
        ? `<a href="${cleanBase}${escapeHtml(f.screenshot)}" target="_blank" rel="noopener">View screenshot</a>`
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

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>StateScout AI — VS Code Audit Console</title>
  <style>
    body { font-family: system-ui, -apple-system, sans-serif; margin: 0; padding: 16px; color: #e2e8f0; background: #0f172a; }
    .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
    h1 { font-size: 18px; margin: 0; }
    .card { background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 14px; margin-bottom: 14px; }
    label { display: block; font-size: 12px; font-weight: 600; margin-bottom: 4px; color: #94a3b8; }
    input[type="text"], textarea { width: 100%; box-sizing: border-box; background: #0f172a; color: #f8fafc; border: 1px solid #475569; border-radius: 6px; padding: 8px; margin-bottom: 10px; font-family: inherit; }
    .actions { display: flex; gap: 8px; align-items: center; }
    button, .btn-link { background: #2563eb; color: #fff; border: none; border-radius: 6px; padding: 8px 14px; font-weight: 600; cursor: pointer; text-decoration: none; font-size: 13px; }
    button.stop { background: #dc2626; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { text-align: left; padding: 10px 8px; border-bottom: 1px solid #334155; vertical-align: top; }
    .sev { padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: 700; text-transform: uppercase; }
    .sev-critical, .sev-high { background: #7f1d1d; color: #fecaca; }
    .sev-medium { background: #78350f; color: #fde68a; }
    .sev-low { background: #1e3a8a; color: #bfdbfe; }
    .badge { padding: 2px 6px; border-radius: 4px; font-size: 11px; }
    .badge-stable { background: #14532d; color: #bbf7d0; }
    .badge-flaky { background: #713f12; color: #fef08a; }
    .badge-insufficient_evidence { background: #334155; color: #cbd5e1; }
    .muted { color: #94a3b8; font-size: 12px; margin-top: 2px; }
    .url { color: #38bdf8; font-size: 11px; margin-top: 2px; }
  </style>
</head>
<body>
  <div class="header">
    <h1>StateScout AI — Logical UI Auditor</h1>
    <a class="btn-link" href="${cleanBase}/" target="_blank" rel="noopener">Open Full Console (${cleanBase})</a>
  </div>
  <div class="card">
    <div id="status-banner"><strong>${summaryText}</strong></div>
  </div>
  <div class="card">
    <label for="target-url">Site URL</label>
    <input id="target-url" type="text" value="${escapeHtml(report?.url ?? "http://127.0.0.1:8765/")}" />
    <label for="policy-rules">Rules (one per line, plain English)</label>
    <textarea id="policy-rules" rows="4">Guests must never see the Admin navigation item or any admin-only controls such as 'Delete user'.
A 'Last updated' timestamp must advance whenever the displayed live prices change.
The page must never display 'NaN', 'undefined' or 'null' to the user; missing data must be handled gracefully.</textarea>
    <div class="actions">
      <button id="start-btn" type="button">Start Audit</button>
      <button id="stop-btn" class="stop" type="button">Stop</button>
    </div>
  </div>
  <div class="card">
    <table>
      <thead>
        <tr><th>Severity</th><th>Confidence</th><th>Finding</th><th>Evidence</th></tr>
      </thead>
      <tbody id="findings-body">
        ${rowsHtml || '<tr><td colspan="4" class="muted">No findings loaded yet.</td></tr>'}
      </tbody>
    </table>
  </div>
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
  onDidReceiveMessage?: (listener: (msg: unknown) => void) => Disposable;
}

export interface WebviewPanel extends Disposable {
  webview: Webview;
  reveal(): void;
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
    createStatusBarItem(): StatusBarItem;
    createWebviewPanel(
      viewType: string,
      title: string,
      showOptions: number,
      options: { enableScripts: boolean },
    ): WebviewPanel;
    showInformationMessage(message: string): void;
    showErrorMessage(message: string): void;
  };
}

let activeAuditId: string | null = null;
let activePanel: WebviewPanel | null = null;

/** Activate the extension in the VS Code host. */
export function activate(
  context: ExtensionContext,
  host?: VscodeHostApi,
  client: AuditApiClient = new AuditApiClient(),
): void {
  if (!host) return;

  const statusBar = host.window.createStatusBarItem();
  statusBar.text = "StateScout: idle";
  statusBar.tooltip = "StateScout AI Logical UI Auditor";
  statusBar.command = COMMANDS.openConsole;
  statusBar.show();

  const openPanel = (report: AuditReport | null = null): WebviewPanel => {
    if (!activePanel) {
      activePanel = host.window.createWebviewPanel(
        "statescoutAuditConsole",
        "StateScout AI Audit Console",
        1,
        { enableScripts: true },
      );
    }
    activePanel.webview.html = renderAuditWebviewHtml(client.baseUrl, report);
    activePanel.reveal();
    return activePanel;
  };

  const startDisp = host.commands.registerCommand(
    COMMANDS.startScan,
    async (input?: Partial<AuditFormInput>) => {
      try {
        const payload = buildAuditPayload({
          url: input?.url ?? "http://127.0.0.1:8765/",
          policyText: input?.policyText,
          allowPrivate: input?.allowPrivate ?? true,
          probabilistic: input?.probabilistic ?? true,
          probeForms: input?.probeForms ?? false,
        });
        const { audit_id } = await client.startAudit(payload);
        activeAuditId = audit_id;
        statusBar.text = `StateScout: running (${audit_id})`;
        const report = await client.getAudit(audit_id);
        statusBar.text = describeAudit(report);
        openPanel(report);
        if (isAuditTerminal(report)) {
          activeAuditId = null;
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        statusBar.text = "StateScout: error";
        host.window.showErrorMessage(`StateScout scan failed: ${msg}`);
      }
    },
  );

  const stopDisp = host.commands.registerCommand(COMMANDS.stopScan, async () => {
    if (!activeAuditId) {
      host.window.showInformationMessage("StateScout: No active audit running.");
      return;
    }
    try {
      await client.stopAudit(activeAuditId);
      statusBar.text = "StateScout: stopped";
      activeAuditId = null;
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      host.window.showErrorMessage(`StateScout stop failed: ${msg}`);
    }
  });

  const openDisp = host.commands.registerCommand(COMMANDS.openConsole, () => {
    openPanel(null);
  });

  context.subscriptions.push(statusBar, startDisp, stopDisp, openDisp);
}

export function deactivate(): void {
  activeAuditId = null;
  activePanel = null;
}
