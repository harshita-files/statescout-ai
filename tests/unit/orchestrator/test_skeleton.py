"""The walking skeleton, end to end against the fakes.

Two kinds of test here. Most drive `main()` in-process and read the captured
streams — fast, and the failure output is readable. A handful go through a real
subprocess, because exit codes and stream separation are the skeleton's actual
contract with CI and an in-process test cannot prove `python -m` works at all.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from apps.agent.contracts import ExpectationSet, NavigationError
from apps.agent.orchestrator.deps import Ports, fake_ports, live_ports
from apps.agent.orchestrator.fakes import FakeCrawler, FakeGraph, FakePerception
from apps.agent.skeleton import (
    EXIT_CLEAN,
    EXIT_ERROR,
    EXIT_VIOLATION,
    SKELETON_POLICY,
    Logger,
    main,
    run_once,
)

REPO_ROOT = Path(__file__).resolve().parents[3]

VIOLATING_URL = "http://fake.test/dashboard"  # admin-link visible to a guest
CLEAN_URL = "http://fake.test/login"  # nothing the skeleton policy forbids


def quiet_log() -> Logger:
    """A logger that goes nowhere, for tests asserting on effects not output."""
    return Logger("r", io.StringIO())


def read_report(capsys: pytest.CaptureFixture[str]) -> tuple[dict, list[dict]]:
    """Split the two streams the way a CI job would: stdout is the result,
    stderr is the log."""
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    logs = [json.loads(line) for line in captured.err.splitlines() if line.strip()]
    return report, logs


# ---------------------------------------------------------------------------
# Exit codes — the part CI actually consumes
# ---------------------------------------------------------------------------


def test_violation_exits_one(capsys: pytest.CaptureFixture[str]) -> None:
    """The M1 demo in one assertion: a planted violation reaches a failing exit
    code without anyone parsing output."""
    assert main(["--fake", "--url", VIOLATING_URL, "--run-id", "r1"]) == EXIT_VIOLATION
    report, _ = read_report(capsys)
    assert [v["expectation_id"] for v in report["violations"]] == ["e-admin-link"]


def test_clean_state_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--fake", "--url", CLEAN_URL, "--run-id", "r2"]) == EXIT_CLEAN
    report, _ = read_report(capsys)
    assert report["violations"] == []


def test_unreachable_url_exits_two(capsys: pytest.CaptureFixture[str]) -> None:
    """A port failure is not a clean run and not a violation. Collapsing it into
    either would make CI lie."""
    assert main(["--fake", "--url", "http://fake.test/ghost", "--run-id", "r3"]) == EXIT_ERROR
    captured = capsys.readouterr()
    assert captured.out == ""  # no report was produced
    assert any(json.loads(line)["event"] == "failed" for line in captured.err.splitlines())


def test_live_mode_exits_two_with_a_useful_reason(capsys: pytest.CaptureFixture[str]) -> None:
    """Until Tracks A, C, and D land, `--live` must fail by naming what is
    missing rather than raising three import errors at once."""
    assert main(["--live", "--url", "https://example.com", "--run-id", "r4"]) == EXIT_ERROR
    captured = capsys.readouterr()
    assert captured.out == ""
    reasons = [
        json.loads(line)["reason"]
        for line in captured.err.splitlines()
        if json.loads(line)["event"] == "failed"
    ]
    assert len(reasons) == 1
    assert "do not exist yet" in reasons[0]


def test_live_mode_names_every_missing_implementation() -> None:
    with pytest.raises(NotImplementedError) as exc:
        live_ports()
    message = str(exc.value)
    assert "Track A" in message
    assert "Track C" in message
    assert "Track D" in message
    assert "--fake" in message


def test_live_without_url_exits_two(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--live", "--run-id", "r5"]) == EXIT_ERROR
    assert capsys.readouterr().out == ""


def test_a_mode_must_be_chosen() -> None:
    """Defaulting to `--live` would surprise; defaulting to `--fake` would let a
    CI job silently audit a scripted app instead of the real one."""
    with pytest.raises(SystemExit):
        main(["--url", VIOLATING_URL])


# ---------------------------------------------------------------------------
# The report on stdout
# ---------------------------------------------------------------------------


def test_report_is_a_single_json_document(capsys: pytest.CaptureFixture[str]) -> None:
    main(["--fake", "--url", VIOLATING_URL, "--run-id", "r6"])
    report, _ = read_report(capsys)
    assert report["run_id"] == "r6"
    assert report["mode"] == "fake"
    assert report["url"] == VIOLATING_URL
    assert report["role"] == "guest"
    assert report["state_id"].startswith("s-")


def test_report_counts_one_state_and_no_edges(capsys: pytest.CaptureFixture[str]) -> None:
    """The skeleton audits a single state. An edge here would mean someone
    started building the loop in the wrong file."""
    main(["--fake", "--url", VIOLATING_URL, "--run-id", "r7"])
    report, _ = read_report(capsys)
    assert report["counts"] == {"states": 1, "edges": 0, "violations": 1}


def test_report_carries_the_full_violation_record(capsys: pytest.CaptureFixture[str]) -> None:
    main(["--fake", "--url", VIOLATING_URL, "--run-id", "r8"])
    report, _ = read_report(capsys)
    violation = report["violations"][0]
    assert violation["clause_type"] == "forbidden_present"
    assert violation["severity"] == "critical"
    assert violation["evidence"]["selector"] is not None


def test_role_reaches_the_report_and_the_audit(capsys: pytest.CaptureFixture[str]) -> None:
    """`admin-link` is forbidden for guests only, so the same page is clean for
    an admin. If the role were dropped anywhere in the chain this would fail."""
    assert main(["--fake", "--url", VIOLATING_URL, "--role", "admin", "--run-id", "r9"]) == (
        EXIT_CLEAN
    )
    report, _ = read_report(capsys)
    assert report["role"] == "admin"
    assert report["violations"] == []


# ---------------------------------------------------------------------------
# Structured logging
# ---------------------------------------------------------------------------


def test_every_log_line_is_json_carrying_the_run_id(capsys: pytest.CaptureFixture[str]) -> None:
    main(["--fake", "--url", VIOLATING_URL, "--run-id", "r10"])
    _, logs = read_report(capsys)
    assert logs
    for record in logs:
        assert record["run_id"] == "r10"
        assert {"ts", "node", "event"} <= set(record)


def test_the_log_walks_all_five_stages(capsys: pytest.CaptureFixture[str]) -> None:
    """Order matters: this is the sequence `explore.py` will wrap in a frontier,
    and decision 3 pins fingerprint-then-persist ahead of any action."""
    main(["--fake", "--url", VIOLATING_URL, "--run-id", "r11"])
    _, logs = read_report(capsys)
    nodes = [r["node"] for r in logs]
    for stage in ("capture", "fingerprint", "persist", "perceive", "audit"):
        assert stage in nodes
    assert nodes.index("capture") < nodes.index("fingerprint") < nodes.index("persist")
    assert nodes.index("persist") < nodes.index("perceive") < nodes.index("audit")


def test_each_violation_is_logged_not_only_reported(
    capsys: pytest.CaptureFixture[str],
) -> None:
    main(["--fake", "--url", VIOLATING_URL, "--run-id", "r12"])
    _, logs = read_report(capsys)
    found = [r for r in logs if r["event"] == "violation"]
    assert len(found) == 1
    assert found[0]["expectation_id"] == "e-admin-link"


def test_run_id_is_generated_when_not_supplied(capsys: pytest.CaptureFixture[str]) -> None:
    main(["--fake", "--url", CLEAN_URL])
    report, logs = read_report(capsys)
    assert report["run_id"].startswith("run-")
    assert all(r["run_id"] == report["run_id"] for r in logs)


def test_two_runs_get_different_ids(capsys: pytest.CaptureFixture[str]) -> None:
    main(["--fake", "--url", CLEAN_URL])
    first, _ = read_report(capsys)
    main(["--fake", "--url", CLEAN_URL])
    second, _ = read_report(capsys)
    assert first["run_id"] != second["run_id"]


def test_logger_writes_one_object_per_line() -> None:
    stream = io.StringIO()
    log = Logger("r-x", stream)
    log.emit("capture", "captured", url="/a")
    log.emit("audit", "audited", violations=0)
    lines = stream.getvalue().splitlines()
    assert len(lines) == 2
    assert [json.loads(line)["node"] for line in lines] == ["capture", "audit"]


# ---------------------------------------------------------------------------
# The stages themselves
# ---------------------------------------------------------------------------


def test_run_once_persists_exactly_one_state() -> None:
    graph = FakeGraph()
    ports = Ports(crawler=FakeCrawler(), perception=FakePerception(), graph=graph)
    violations, bundle = run_once(ports, VIOLATING_URL, "guest", SKELETON_POLICY, quiet_log())

    assert len(graph.states) == 1
    assert graph.edges == []  # the skeleton never acts
    assert next(iter(graph.states)) == graph.fingerprint(bundle)
    assert len(violations) == 1


def test_run_once_persists_the_violation_to_the_graph() -> None:
    graph = FakeGraph()
    ports = Ports(crawler=FakeCrawler(), perception=FakePerception(), graph=graph)
    run_once(ports, VIOLATING_URL, "guest", SKELETON_POLICY, quiet_log())
    assert len(graph.violations) == 1


def test_run_once_records_state_at_depth_zero() -> None:
    graph = FakeGraph()
    ports = Ports(crawler=FakeCrawler(), perception=FakePerception(), graph=graph)
    run_once(ports, CLEAN_URL, "guest", SKELETON_POLICY, quiet_log())
    assert next(iter(graph.states.values())).depth == 0


def test_run_once_never_calls_act() -> None:
    """One state. The moment this file starts traversing, it stops being a
    skeleton and starts being a second, untested exploration loop."""
    crawler = FakeCrawler()
    ports = Ports(crawler=crawler, perception=FakePerception(), graph=FakeGraph())
    run_once(ports, VIOLATING_URL, "guest", SKELETON_POLICY, quiet_log())
    assert crawler.acted == []


def test_run_once_propagates_port_failures() -> None:
    ports = fake_ports()
    with pytest.raises(NavigationError):
        run_once(ports, "http://fake.test/ghost", "guest", SKELETON_POLICY, quiet_log())


def test_an_empty_policy_finds_nothing() -> None:
    graph = FakeGraph()
    ports = Ports(crawler=FakeCrawler(), perception=FakePerception(), graph=graph)
    violations, _ = run_once(ports, VIOLATING_URL, "guest", ExpectationSet(), quiet_log())
    assert violations == []


@pytest.mark.parametrize("url", [VIOLATING_URL, "http://fake.test/ghost"])
def test_the_crawler_is_always_closed(
    url: str,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Including when the run fails — a live run leaks a browser process
    otherwise, and the failing path is the one nobody exercises by hand."""
    crawler = FakeCrawler()
    ports = Ports(crawler=crawler, perception=FakePerception(), graph=FakeGraph())
    monkeypatch.setattr("apps.agent.skeleton.fake_ports", lambda **_: ports)

    main(["--fake", "--url", url, "--run-id", "r13"])
    capsys.readouterr()
    assert crawler.closed


# ---------------------------------------------------------------------------
# As a subprocess — the contract CI relies on
# ---------------------------------------------------------------------------


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "apps.agent.skeleton", *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )


@pytest.mark.parametrize(
    ("url", "expected"),
    [(VIOLATING_URL, EXIT_VIOLATION), (CLEAN_URL, EXIT_CLEAN)],
)
def test_module_entry_point_returns_the_right_exit_code(url: str, expected: int) -> None:
    assert run_cli("--fake", "--url", url).returncode == expected


def test_streams_are_separated_for_piping() -> None:
    """`... | jq` must work. A log line on stdout would break every consumer."""
    result = run_cli("--fake", "--url", VIOLATING_URL, "--run-id", "cli-1")
    report = json.loads(result.stdout)
    assert report["run_id"] == "cli-1"
    assert all(json.loads(line)["run_id"] == "cli-1" for line in result.stderr.splitlines())
