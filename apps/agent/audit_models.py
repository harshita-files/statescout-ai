"""Shared models for a user-facing audit: rules, config, report. Additive to contracts.py."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from apps.agent.llm.base import ProviderConfig

RuleSource = Literal["user", "generated"]
Severity = Literal["low", "medium", "high", "critical"]


@dataclass(frozen=True, slots=True)
class Rule:
    rule_id: str
    text: str  # natural language, e.g. "Guests must never see an admin link"
    source: RuleSource = "user"
    severity: Severity = "high"
    # Optional structured hints filled by the rules parser.
    kind: str = "presence"  # presence | absence | consistency | numeric | a11y | content
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AuditConfig:
    url: str
    rules: tuple[Rule, ...] = ()
    auto_rules: bool = True
    llm: ProviderConfig | None = None  # text reasoning / rule generation
    vlm: ProviderConfig | None = None  # screenshot perception
    max_states: int = 40
    depth_limit: int = 3
    max_seconds: int = 300
    requests_per_second: float = 1.0
    respect_robots: bool = True  # on by default; only owned/authorized sites should disable
    allow_destructive: bool = False
    probabilistic: bool = True
    volatility_patterns: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Finding:
    finding_id: str
    rule_id: str | None
    state_id: str
    url: str
    severity: Severity
    title: str
    rationale: str
    confidence: float = 1.0  # recurrence x reproducibility in probabilistic mode
    screenshot: str | None = None
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BlockedNote:
    url: str
    reason: str  # robots | captcha | login_wall | consent_wall | rate_limit | cap


@dataclass(frozen=True, slots=True)
class AuditReport:
    audit_id: str
    url: str
    status: Literal["running", "done", "error", "stopped"]
    rules: tuple[Rule, ...] = ()
    findings: tuple[Finding, ...] = ()
    blocked: tuple[BlockedNote, ...] = ()
    graph: dict[str, Any] = field(default_factory=dict)  # {"nodes":[...],"edges":[...]}
    stats: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
