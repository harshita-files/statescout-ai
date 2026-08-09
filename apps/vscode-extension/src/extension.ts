/**
 * StateScout VS Code extension — Track A.
 *
 * Placeholder entry point. The real activation wiring (webview panel, run
 * lifecycle, violation tree view) is Track A's Month 1+ work. What is fixed
 * already is the shape of the data it renders: see `@statescout/shared-types`.
 */

import type { ReportResponse, ScanRun } from "@statescout/shared-types";

/** Commands this extension contributes, kept in sync with `package.json`. */
export const COMMANDS = {
  startScan: "statescout.startScan",
  stopScan: "statescout.stopScan",
} as const;

/** One-line status text for the editor status bar. */
export function describeRun(run: ScanRun): string {
  if (run.status === "running") {
    return `StateScout: ${run.counts.states} states, ${run.counts.violations} violations`;
  }
  return `StateScout: ${run.status}`;
}

/** Violations ordered the way a QA engineer wants to read them. */
export function rankViolations(report: ReportResponse): ReportResponse["violations"] {
  const order = { critical: 0, high: 1, medium: 2, low: 3 } as const;
  return [...report.violations].sort((a, b) => order[a.severity] - order[b.severity]);
}
