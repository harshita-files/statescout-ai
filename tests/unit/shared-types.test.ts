import { describe, expect, it } from "bun:test";

import {
  extractConfidenceLabel,
  isAuditTerminal,
  isBlocking,
  isTerminal,
  type AuditFinding,
  type AuditReport,
  type ScanRun,
  type Violation,
} from "../../packages/shared-types/index";
import {
  activate,
  AuditApiClient,
  buildAuditPayload,
  COMMANDS,
  deactivate,
  describeAudit,
  describeRun,
  rankFindings,
  rankViolations,
  renderAuditWebviewHtml,
  type ExtensionContext,
  type VscodeHostApi,
} from "../../apps/vscode-extension/src/extension";

const run = (status: ScanRun["status"]): ScanRun => ({
  runId: "run-1",
  targetUrl: "http://localhost:4173",
  role: "guest",
  status,
  startedAt: "2026-01-01T00:00:00Z",
  finishedAt: null,
  terminationReason: null,
  counts: { states: 6, edges: 11, violations: 4, skippedActions: 0 },
});

const violation = (severity: Violation["severity"]): Violation => ({
  violationId: "v-1",
  stateId: "s-1",
  expectationId: "e-1",
  clauseType: "forbidden_present",
  severity,
  rationale: "admin-link visible to guest",
  evidence: { selector: "#admin-link", text: "Admin", screenshotPath: null },
  detectedAt: "2026-01-01T00:00:00Z",
});

const finding = (
  severity: AuditFinding["severity"],
  confidence: number,
  evidence: string[] = ["observation: stable"],
): AuditFinding => ({
  finding_id: `f-${severity}-${confidence}`,
  rule_id: "r-1",
  state_id: "eq-1",
  url: "http://127.0.0.1:8765/",
  severity,
  title: "Guests must not see admin controls",
  rationale: "Forbidden subject 'admin-access' is present for role 'guest'.",
  confidence,
  screenshot: "/audits/a1/screenshots/s1.png",
  evidence,
  group_key: "g-1",
});

const auditReport = (status: AuditReport["status"]): AuditReport => ({
  audit_id: "audit-1",
  url: "http://127.0.0.1:8765/",
  status,
  rules: [],
  findings: [finding("high", 0.8, ["observation: insufficient_evidence"])],
  blocked: [],
  graph: { nodes: [{ id: "s1" }, { id: "s2" }], edges: [] },
  stats: { states: 40, transitions: 39 },
  error: null,
});

describe("shared-types", () => {
  it("treats completed and failed runs as terminal", () => {
    expect(isTerminal(run("completed"))).toBe(true);
    expect(isTerminal(run("failed"))).toBe(true);
  });

  it("keeps polling runs that are still in flight", () => {
    expect(isTerminal(run("queued"))).toBe(false);
    expect(isTerminal(run("running"))).toBe(false);
    expect(isTerminal(run("stopping"))).toBe(false);
  });

  it("blocks only on high and critical violations", () => {
    expect(isBlocking(violation("critical"))).toBe(true);
    expect(isBlocking(violation("high"))).toBe(true);
    expect(isBlocking(violation("medium"))).toBe(false);
    expect(isBlocking(violation("low"))).toBe(false);
  });

  it("identifies terminal dynamic audit statuses", () => {
    expect(isAuditTerminal(auditReport("running"))).toBe(false);
    expect(isAuditTerminal(auditReport("done"))).toBe(true);
    expect(isAuditTerminal(auditReport("stopped"))).toBe(true);
    expect(isAuditTerminal(auditReport("error"))).toBe(true);
  });

  it("extracts Beta confidence labels from finding evidence", () => {
    expect(extractConfidenceLabel(finding("high", 1.0, ["observation: stable"]))).toBe("stable");
    expect(extractConfidenceLabel(finding("high", 0.1, ["observation: flaky"]))).toBe("flaky");
    expect(
      extractConfidenceLabel(finding("high", 0.8, ["observation: insufficient_evidence"])),
    ).toBe("insufficient_evidence");
  });
});

describe("vscode-extension", () => {
  it("describes both legacy ScanRun and dynamic AuditReport statuses", () => {
    expect(describeRun(run("running"))).toBe("StateScout: 6 states, 4 violations");
    expect(describeRun(run("completed"))).toBe("StateScout: completed");
    expect(describeAudit(auditReport("running"))).toBe(
      "StateScout: 40 states, 1 findings (running)",
    );
    expect(describeAudit(auditReport("done"))).toBe(
      "StateScout: done (40 states, 1 findings)",
    );
  });

  it("ranks violations and findings by severity then confidence", () => {
    const rankedV = rankViolations({
      run: run("completed"),
      expectations: [],
      violations: [violation("low"), violation("critical"), violation("high")],
    });
    expect(rankedV.map((v) => v.severity)).toEqual(["critical", "high", "low"]);

    const rankedF = rankFindings([
      finding("medium", 1.0),
      finding("high", 0.5),
      finding("high", 1.0),
    ]);
    expect(rankedF.map((f) => `${f.severity}:${f.confidence}`)).toEqual([
      "high:1",
      "high:0.5",
      "medium:1",
    ]);
  });

  it("builds a clean StartAuditRequest payload and renders webview HTML", () => {
    const payload = buildAuditPayload({
      url: " http://127.0.0.1:8765/ ",
      policyText: "Rule 1\n\nRule 2\n",
      probabilistic: true,
      probeForms: true,
    });
    expect(payload.url).toBe("http://127.0.0.1:8765/");
    expect(payload.rules).toEqual(["Rule 1", "Rule 2"]);
    expect(payload.probabilistic).toBe(true);
    expect(payload.probe_forms).toBe(true);

    const html = renderAuditWebviewHtml("http://127.0.0.1:8000", auditReport("done"));
    expect(html).toContain("Guests must not see admin controls");
    expect(html).toContain("insufficient_evidence");
  });

  it("registers commands and drives AuditApiClient on activate", async () => {
    const registered: Record<string, (...args: unknown[]) => unknown> = {};
    const statusBar = {
      text: "",
      show: () => {},
      dispose: () => {},
    };
    const host: VscodeHostApi = {
      commands: {
        registerCommand: (cmd, cb) => {
          registered[cmd] = cb;
          return { dispose: () => {} };
        },
      },
      window: {
        createStatusBarItem: () => statusBar,
        createWebviewPanel: () => ({
          webview: { html: "" },
          reveal: () => {},
          dispose: () => {},
        }),
        showInformationMessage: () => {},
        showErrorMessage: () => {},
      },
    };
    const ctx: ExtensionContext = { subscriptions: [] };
    const fakeFetch = (async (url: string | URL | Request) => {
      const target = String(url);
      if (target.endsWith("/audits")) {
        return new Response(JSON.stringify({ audit_id: "audit-1" }), { status: 200 });
      }
      return new Response(JSON.stringify(auditReport("done")), { status: 200 });
    }) as typeof fetch;

    activate(ctx, host, new AuditApiClient("http://127.0.0.1:8000", fakeFetch));
    expect(Object.keys(registered)).toContain(COMMANDS.startScan);
    expect(Object.keys(registered)).toContain(COMMANDS.stopScan);
    await registered[COMMANDS.startScan]?.({ url: "http://127.0.0.1:8765/" });
    expect(statusBar.text).toContain("40 states");
    deactivate();
  });
});
