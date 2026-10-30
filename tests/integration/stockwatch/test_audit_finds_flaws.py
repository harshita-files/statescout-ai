"""Ground truth: audit the flawed StockWatch demo and see which seeded flaws are found.

Needs Chromium (Playwright). Detection is judged by a per-flaw predicate over the
findings, never by counting findings. Missed flaws are printed with the reason.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from apps.agent.audit_models import AuditConfig, AuditReport, Finding, Rule
from apps.agent.crawler.safety import SafetyPolicy
from apps.agent.orchestrator.audit_runner import run_audit
from apps.agent.orchestrator.deps import live_ports
from apps.agent.perception import VLMPerception
from apps.agent.rules import generate_rules, parse_rules

pytestmark = pytest.mark.live

APP = Path(__file__).resolve().parents[3] / "test-apps" / "stockwatch"
FLAWS = json.loads((APP / "expected.json").read_text(encoding="utf-8"))["flaws"]
# Measured floor (6/10), not the aspiration. Still missed: SW-02 (needs a /trade?symbol=...
# state to compare against Markets), SW-03 (needs a POST order, which the crawler never
# makes), SW-05 (needs time-ordered observations) and SW-10 (needs the flaky quote call to
# fail at capture time).
MIN_DETECTED = 6
#: `SW_TICK_INTERVAL=0` freezes prices (experiment: how much does live churn cost coverage?).
TICK = (
    ["--tick-interval", os.environ["SW_TICK_INTERVAL"]] if "SW_TICK_INTERVAL" in os.environ else []
)


@pytest.fixture(scope="module")
def base() -> Iterator[str]:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen(
        [sys.executable, str(APP / "server.py"), "--port", str(port), "--seed", "7", *TICK],
        stdout=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(url + "/markets", timeout=2).read()
                break
            except OSError:
                time.sleep(0.1)
        else:
            pytest.fail("StockWatch did not start")
        yield url
    finally:
        proc.terminate()
        proc.wait(timeout=5)


@pytest.fixture(scope="module")
def report(base: str) -> AuditReport:
    user = [Rule(f"{f['id'].lower()}", f["rule_text"], "user", f["severity"]) for f in FLAWS]
    pages = [{"url": base, "text": urllib.request.urlopen(base + "/markets").read().decode()}]
    texts: list[str | Rule] = [*user, *generate_rules(pages, None)]
    expectations, rules = parse_rules(texts, None)
    config = AuditConfig(
        url=base + "/markets",
        rules=tuple(rules),
        max_states=30,
        depth_limit=3,
        max_seconds=240,
        requests_per_second=20,
        respect_robots=False,
        probabilistic=True,
    )
    ports = live_ports(
        graph="memory",
        probabilistic_states=True,
        perception=VLMPerception(dom_only=True),
        safety=SafetyPolicy(
            respect_robots=False, requests_per_second=20, max_pages=40, max_seconds=240
        ),
    )
    return run_audit(config, ports, expectations)


def _by_rule(report: AuditReport, flaw_id: str) -> list[Finding]:
    return [f for f in report.findings if f.rule_id == flaw_id.lower()]


def _ev(f: Finding) -> str:
    return " ".join((f.title, f.rationale, *f.evidence))


# Predicate per flaw: does a finding for that flaw's user rule show the real defect?
CHECKS: dict[str, Callable[[list[Finding]], bool]] = {
    "SW-01": lambda fs: any(re.search(r"admin", _ev(f), re.I) for f in fs),
    "SW-02": lambda fs: any("/trade" in f.url and "order ticket" in f.rationale for f in fs),
    "SW-03": lambda fs: any(
        re.search(r"filled|rejected", f.rationale + " ".join(f.evidence)) for f in fs
    ),
    "SW-04": lambda fs: any("add up" in f.rationale for f in fs),
    "SW-05": lambda fs: any("last updated" in _ev(f).lower() for f in fs),
    "SW-06": lambda fs: any("accessible name" in f.rationale for f in fs),
    "SW-07": lambda fs: any(re.search(r"404|not found", _ev(f), re.I) for f in fs),
    "SW-08": lambda fs: any("never appears" in f.rationale for f in fs),
    "SW-09": lambda fs: any(re.search(r"TSLA|AMD", _ev(f)) for f in fs),
    "SW-10": lambda fs: any(re.search(r"NaN|undefined|null", _ev(f), re.I) for f in fs),
}


def test_audit_finds_seeded_flaws(report: AuditReport) -> None:
    assert report.status in {"done", "stopped"}, report.error
    detected, missed = [], []
    for flaw in FLAWS:
        fs = _by_rule(report, flaw["id"])
        (detected if CHECKS[flaw["id"]](fs) else missed).append(flaw["id"])
    urls = sorted({f.url.split("?")[0].rsplit("/", 1)[-1] for f in report.findings})
    print(f"\nstates={report.stats.get('states')} findings={len(report.findings)} pages={urls}")
    print(f"timed_out={report.stats.get('timed_out')} replays={report.stats.get('replays')}")
    print(f"detected {len(detected)}/10: {detected}")
    for fid in missed:
        n = len(_by_rule(report, fid))
        desc = next(f["description"] for f in FLAWS if f["id"] == fid)
        print(f"  missed {fid} ({n} raw findings): {desc}")
        for f in _by_rule(report, fid)[:3]:
            print(f"      unrelated hit: {f.url} {f.rationale[:140]}")
    assert len(detected) >= MIN_DETECTED


def test_findings_are_readable_and_grouped(report: AuditReport) -> None:
    rule_text = {r.rule_id: r.text for r in report.rules}
    for f in report.findings:
        assert f.title == rule_text.get(f.rule_id or "", f.title)
        assert not f.title.startswith("forbidden_present")
        assert f.group_key
    groups = report.stats["finding_groups"]
    assert sum(g["count"] for g in groups) == len(report.findings)
    # No two findings for the same state share an evidence signature.
    seen: set[tuple[str, str, tuple[str, ...]]] = set()
    for f in report.findings:
        key = (f.state_id, f.group_key, f.evidence)
        assert key not in seen
        seen.add(key)
    # The generated duplicate of the user admin rule is gone.
    assert not any(
        r.source == "generated" and r.params.get("subject") == "admin-access" for r in report.rules
    )
