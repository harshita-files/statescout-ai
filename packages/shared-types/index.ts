/**
 * StateScout AI — shared API contract types.
 *
 * The single source of truth for the JSON that crosses the wire between the
 * FastAPI reporting backend (Track D) and the VS Code extension (Track A).
 * These mirror the Python dataclasses in `apps/agent/contracts.py`; when one
 * side changes, both change in the same PR.
 *
 * Types only — no runtime logic beyond the narrow helpers at the bottom.
 */

/** A role the crawler can browse as. Free-form: the policy author names them. */
export type Role = string;

/** How a run ended. Mirrors the orchestrator's termination reasons. */
export type TerminationReason =
  | "frontier_exhausted"
  | "depth_limit"
  | "max_states"
  | "stopped"
  | "error";

/** Outcome of evaluating one policy clause against one observed state. */
export type Verdict = "clean" | "violated";

/** Severity of a detected violation, as reported to the QA engineer. */
export type Severity = "low" | "medium" | "high" | "critical";

/** Which set operation produced a violation (ADR-001 decision 6). */
export type ClauseType = "forbidden_present" | "required_absent";

/** Observation stability label from the Beta-Binomial confidence model (ADR-002). */
export type ConfidenceLabel = "stable" | "flaky" | "insufficient_evidence";

/** Origin of an audit rule (`user` typed or `generated` from site inspection). */
export type RuleSource = "user" | "generated";

/** Rule verification category in the dynamic audit engine. */
export type RuleKind =
  | "presence"
  | "absence"
  | "consistency"
  | "numeric"
  | "a11y"
  | "content";

/** A node in the exploration graph: one distinct UI state. */
export interface StateNode {
  /** Content fingerprint. Stable across re-visits; the graph's primary key. */
  stateId: string;
  url: string;
  title: string;
  role: Role;
  /** BFS depth at which this state was first reached. */
  depth: number;
  screenshotPath: string | null;
  firstSeenAt: string;
}

/** A directed edge: performing `actionId` in `fromStateId` led to `toStateId`. */
export interface StateEdge {
  fromStateId: string;
  toStateId: string;
  actionId: string;
  /** Human-readable label, e.g. `click "Admin settings"`. */
  label: string;
  /** True when the edge closes a cycle. Cycles are kept, never pruned. */
  isBackEdge: boolean;
}

/** A policy clause the UI must not violate. */
export interface ExpectationNode {
  expectationId: string;
  /** `must_not_exist` is the negation case StateScout exists to catch. */
  polarity: "must_exist" | "must_not_exist";
  /** The UI element or capability the clause is about. */
  subject: string;
  /** Roles the clause applies to. Empty means "all roles". */
  roles: Role[];
  /** The QA engineer's original sentence, kept for report traceability. */
  sourceText: string;
}

/** A detected policy violation, anchored to a state and an expectation. */
export interface Violation {
  violationId: string;
  stateId: string;
  expectationId: string;
  /** Which set operation caught the violation (ADR-001 decision 6). */
  clauseType?: ClauseType;
  severity: Severity;
  /** Why the engine thinks this is a violation. */
  rationale: string;
  /** The offending element, as located in the semantic UI map. */
  evidence: {
    selector: string | null;
    text: string | null;
    screenshotPath: string | null;
  };
  detectedAt: string;
}

/** Everything the extension needs to render one completed (or running) scan. */
export interface ScanRun {
  runId: string;
  targetUrl: string;
  role: Role;
  status: "queued" | "running" | "stopping" | "completed" | "failed";
  startedAt: string;
  finishedAt: string | null;
  terminationReason: TerminationReason | null;
  counts: {
    states: number;
    edges: number;
    violations: number;
    skippedActions: number;
  };
}

/** `GET /runs/{runId}/graph` */
export interface GraphResponse {
  runId: string;
  states: StateNode[];
  edges: StateEdge[];
}

/** `GET /runs/{runId}/report` */
export interface ReportResponse {
  run: ScanRun;
  expectations: ExpectationNode[];
  violations: Violation[];
}

/** `POST /runs` */
export interface StartRunRequest {
  targetUrl: string;
  role: Role;
  /** The QA engineer's free-form English policy. */
  policyText: string;
  depthLimit?: number;
}

/** Uniform error envelope for every non-2xx API response. */
export interface ApiError {
  error: string;
  detail: string | null;
}

// ---------------------------------------------------------------------------
// Dynamic Audit API contracts (`services/api/audits.py` & `audit_models.py`)
// ---------------------------------------------------------------------------

/** A plain-language or auto-generated audit rule (`apps/agent/audit_models.py::Rule`). */
export interface AuditRule {
  rule_id: string;
  text: string;
  source?: RuleSource;
  severity?: Severity;
  kind?: RuleKind | string;
  params?: Record<string, unknown>;
}

/** A finding emitted by the dynamic audit runner (`apps/agent/audit_models.py::Finding`). */
export interface AuditFinding {
  finding_id: string;
  rule_id: string | null;
  state_id: string;
  url: string;
  severity: Severity;
  title: string;
  rationale: string;
  /** Recurrence x reproducibility in probabilistic mode (0.0 to 1.0). */
  confidence: number;
  screenshot: string | null;
  evidence: string[];
  group_key: string;
}

/** A page skipped due to safety policy (`robots`, `captcha`, `login_wall`, `rate_limit`). */
export interface BlockedNote {
  url: string;
  reason: string;
}

/** `GET /audits/{id}` — complete dynamic audit report. */
export interface AuditReport {
  audit_id: string;
  url: string;
  status: "running" | "done" | "error" | "stopped";
  rules: AuditRule[];
  findings: AuditFinding[];
  blocked: BlockedNote[];
  graph: {
    nodes?: Array<Record<string, unknown>>;
    edges?: Array<Record<string, unknown>>;
  };
  stats: Record<string, unknown>;
  error: string | null;
}

/** `POST /audits` — start a dynamic audit run. */
export interface StartAuditRequest {
  url: string;
  allow_private?: boolean;
  rules?: Array<string | { text: string; severity?: Severity; source?: RuleSource }>;
  auto_rules?: boolean;
  max_states?: number;
  depth_limit?: number;
  max_seconds?: number;
  requests_per_second?: number;
  respect_robots?: boolean;
  probabilistic?: boolean;
  probe_forms?: boolean;
}

/** True when the run has reached a state the UI should stop polling. */
export function isTerminal(run: ScanRun): boolean {
  return run.status === "completed" || run.status === "failed";
}

/** True when a dynamic audit report has reached a terminal status. */
export function isAuditTerminal(report: Pick<AuditReport, "status">): boolean {
  return (
    report.status === "done" ||
    report.status === "error" ||
    report.status === "stopped"
  );
}

/** Violations worth interrupting the QA engineer for. */
export function isBlocking(violation: Violation): boolean {
  return violation.severity === "high" || violation.severity === "critical";
}

/** Extract the Beta-Binomial observation label (`stable`, `flaky`, `insufficient_evidence`) from finding evidence. */
export function extractConfidenceLabel(
  finding: Pick<AuditFinding, "evidence" | "confidence">,
): ConfidenceLabel {
  for (const item of finding.evidence) {
    if (item.includes("observation: stable")) return "stable";
    if (item.includes("observation: flaky")) return "flaky";
    if (item.includes("observation: insufficient_evidence")) {
      return "insufficient_evidence";
    }
  }
  return finding.confidence >= 0.6 ? "stable" : "flaky";
}
