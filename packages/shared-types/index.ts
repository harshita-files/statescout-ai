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

/** True when the run has reached a state the UI should stop polling. */
export function isTerminal(run: ScanRun): boolean {
  return run.status === "completed" || run.status === "failed";
}

/** Violations worth interrupting the QA engineer for. */
export function isBlocking(violation: Violation): boolean {
  return violation.severity === "high" || violation.severity === "critical";
}
