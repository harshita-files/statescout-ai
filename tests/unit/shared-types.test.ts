import { describe, expect, it } from "bun:test";

import {
  isBlocking,
  isTerminal,
  type ScanRun,
  type Violation,
} from "../../packages/shared-types/index";

const run = (status: ScanRun["status"]): ScanRun => ({
  runId: "run-1",
  targetUrl: "http://localhost:4173",
  role: "guest",
  status,
  startedAt: "2026-01-01T00:00:00Z",
  finishedAt: null,
  terminationReason: null,
  counts: { states: 0, edges: 0, violations: 0, skippedActions: 0 },
});

const violation = (severity: Violation["severity"]): Violation => ({
  violationId: "v-1",
  stateId: "s-1",
  expectationId: "e-1",
  severity,
  rationale: "admin-link visible to guest",
  evidence: { selector: "#admin-link", text: "Admin", screenshotPath: null },
  detectedAt: "2026-01-01T00:00:00Z",
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
});
