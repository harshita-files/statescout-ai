"""
Pydantic models for Track D's API contract.

These define the canonical request/response shapes that the VS Code extension
(Track A) will consume.  Per the handbook (Section 1.4), these schemas are
frozen early — once published, changes to request/response shape require
team coordination.  Internal implementation changes are fine.

Pydantic v2 is used throughout (Field, model_config, etc.).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


class StartScanRequest(BaseModel):
    """Payload sent by the VS Code extension to initiate a new crawl/audit."""

    url: str = Field(
        ...,
        description="Starting URL for the crawl (e.g. https://staging.app.local)",
        examples=["https://app.local/dashboard"],
    )
    policy: str = Field(
        ...,
        description="Plain-English policy rule to audit "
                    "(e.g. 'guest must never see an Admin link')",
        examples=["guest must never see an Admin link"],
    )


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
    """A single policy violation with available evidence."""

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
    evidence_summary: str | None = Field(
        default=None,
        description="[Placeholder] Evidence summary; full chain assembled in Month 3 "
                    "via Neo4j evidence-chain queries.",
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
