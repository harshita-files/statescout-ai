"""
Pydantic models for Track D's API contract.

Month 1: StartScanRequest, ScanStatusResponse, ViolationRecord, ScanReportResponse
Month 2: CrawlStateUpdate (Track B integration), ViolationReport (Track C integration),
         LiveEvent (WebSocket push)

Per handbook Section 1.4 — shapes are frozen once published. Internal changes are fine;
field renames or type changes require cross-track coordination.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


class StartScanRequest(BaseModel):
    """Payload sent by the VS Code extension to initiate a new crawl/audit.

    Contract evolution (additive / loosening, backward compatible): `url` and
    `policy` were required; they are now optional so a caller may pass a saved
    `project_id` instead. Exactly one of (url + policy) or project_id is required
    — enforced below, so a caller that omits both still gets a 422.
    """

    url: str = Field(
        default="",
        description="Starting URL for the crawl. Required unless project_id is given.",
        examples=["https://app.local/dashboard"],
    )
    policy: str = Field(
        default="",
        description="Plain-English policy rule to audit. Required unless project_id is given.",
        examples=["guest must never see an Admin link"],
    )
    role: str = Field(
        default="guest",
        description="Role the crawler browses as. One role per run (ADR-001 decision 5). "
        "Ignored when project_id is given (the project's role wins).",
        examples=["guest", "admin"],
    )
    project_id: str | None = Field(
        default=None,
        description="Run a saved project. url / policy / role are taken from it.",
    )

    @model_validator(mode="after")
    def _url_and_policy_or_project(self) -> StartScanRequest:
        if not self.project_id and not (self.url and self.policy):
            raise ValueError("provide url + policy, or project_id")
        return self


class ProjectRequest(BaseModel):
    """Create / update a saved scan target (POST /projects, PUT /projects/{id})."""

    name: str = Field(..., description="Human label for the project", examples=["Staging — guest"])
    url: str = Field(..., description="Starting URL", examples=["https://staging.app.local"])
    policy: str = Field(..., description="Plain-English policy rule")
    role: str = Field(default="guest", description="Role the crawler browses as")


class CrawlStateUpdate(BaseModel):
    """Payload Track B sends to POST /crawl/state-visit for each state it visits.

    Track D receives raw capture data and fingerprints it internally using
    apps.agent.graph.fingerprint, matching the GraphPort.fingerprint(bundle)
    contract (ADR-001 decision 2).  Track B does NOT pre-compute the fingerprint.

    Edge fields (prev_state_fingerprint, action_id, is_back_edge) are omitted on
    the first call per scan (the initial open() navigation).
    """

    scan_id: str = Field(..., description="Scan session this state belongs to")
    url: str = Field(..., description="URL of the captured state")
    dom: str = Field(..., description="Full HTML of the page at this state")
    ax_tree: Any = Field(
        ...,
        description="Accessibility tree (JSON) captured by Track A via CDP",
    )
    screenshot_path: str | None = Field(
        default=None,
        description="Absolute path to screenshot saved by Track A (None in smoke-test mode)",
    )
    title: str = Field(default="", description="Page title")
    # Edge fields — present when triggered by an action, absent for the initial navigate
    prev_state_fingerprint: str | None = Field(
        default=None,
        description="Fingerprint of the state the crawler came from. "
        "None for the root state (initial open()).",
    )
    action_id: str | None = Field(
        default=None,
        description="Content-addressed action_id that led here (ADR-001 decision 1). "
        "None for the root state.",
    )
    action_label: str = Field(
        default="",
        description="Human-readable label, e.g. 'click \"Admin settings\"'",
    )
    is_back_edge: bool = Field(
        default=False,
        description="True when this edge closes a cycle in the state graph (back-edge).",
    )


class ViolationReport(BaseModel):
    """Payload Track C sends to POST /violations/report when the VLM confirms a violation.

    Field names map 1-to-1 to contracts.Violation so Track C can build this
    directly from the Violation dataclass without a translation layer.
    """

    scan_id: str = Field(..., description="Scan session this violation belongs to")
    violation_id: str = Field(..., description="Globally unique violation identifier")
    state_fingerprint: str = Field(
        ...,
        description="state_id of the state where the violation was found",
    )
    expectation_id: str = Field(
        ...,
        description="ID of the ExpectationNode clause that was broken",
    )
    clause_type: str = Field(
        ...,
        description="'forbidden_present' (FR-18) or 'required_absent' (FR-19)",
    )
    severity: str = Field(..., description="low | medium | high | critical")
    rationale: str = Field(
        ...,
        description="Plain-English explanation of why this is a violation",
    )
    url: str = Field(..., description="URL at which the violation occurred")
    policy_violated: str = Field(
        ...,
        description="The source_text of the ExpectationNode clause violated",
    )
    evidence_selector: str | None = Field(default=None)
    evidence_text: str | None = Field(default=None)
    evidence_screenshot_path: str | None = Field(default=None)


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class ScanStatusResponse(BaseModel):
    """Current status of an in-progress or completed scan."""

    scan_id: str = Field(..., description="Unique identifier for this scan run")
    status: str = Field(
        ...,
        description="Lifecycle state: queued | running | completed | failed",
    )
    states_explored: int = Field(
        default=0,
        description="Number of unique UI states visited so far",
    )
    violations_found: int = Field(
        default=0,
        description="Number of policy violations detected so far",
    )
    message: str | None = Field(
        default=None,
        description="Human-readable status message or error detail",
    )


class ViolationRecord(BaseModel):
    """A single policy violation in a scan report."""

    violation_id: str = Field(..., description="Unique ID for this violation record")
    state_fingerprint: str = Field(
        ...,
        description="SHA-256 fingerprint of the violating UI state",
    )
    url: str = Field(..., description="URL at which the violation occurred")
    policy_violated: str = Field(
        ...,
        description="The plain-English policy rule that was violated",
    )
    clause_type: str = Field(
        default="forbidden_present",
        description="'forbidden_present' (FR-18) or 'required_absent' (FR-19)",
    )
    severity: str = Field(default="high")
    rationale: str = Field(default="")
    evidence_summary: str | None = Field(
        default=None,
        description="Evidence summary; full evidence-chain assembled in Month 3 via Neo4j.",
    )


class ScanReportResponse(BaseModel):
    """Full report returned once a scan is completed."""

    scan_id: str = Field(..., description="Scan run identifier")
    url_scanned: str = Field(..., description="The root URL that was crawled")
    policy: str = Field(..., description="The policy that was audited")
    total_states: int = Field(
        default=0,
        description="Total number of unique UI states explored",
    )
    violations: list[ViolationRecord] = Field(
        default_factory=list,
        description="All violations found during this scan",
    )
    scan_duration_seconds: float = Field(
        default=0.0,
        description="Wall-clock duration of the scan in seconds",
    )


class ProjectResponse(BaseModel):
    """A saved scan target."""

    project_id: str
    name: str
    url: str
    policy: str
    role: str
    created_at: int | None = Field(default=None, description="epoch ms")
    updated_at: int | None = Field(default=None, description="epoch ms")


class LiveEvent(BaseModel):
    """WebSocket push payload sent to connected clients on each crawl event.

    event values:
      'state_visited'   — Track B visited a new state
      'violation_found' — Track C confirmed a violation
      'scan_stopping'   — a graceful stop was requested; loop is winding down
      'scan_stopped'    — crawl ended early on a stop request
      'scan_completed'  — crawl finished normally (frontier exhausted / limit hit)
      'scan_failed'     — crawl aborted with an error
    """

    event: str = Field(
        ...,
        description=(
            "state_visited | violation_found | scan_stopping | scan_stopped | "
            "scan_completed | scan_failed"
        ),
    )
    scan_id: str = Field(..., description="Scan this event belongs to")
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Event-specific data. "
            "state_visited: {url, fingerprint, states_explored}. "
            "violation_found: {violation_id, url, rationale, severity}. "
            "scan_complete: {total_states, total_violations}."
        ),
    )
