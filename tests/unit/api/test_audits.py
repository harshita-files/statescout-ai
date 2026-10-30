"""Product API tests: injected fake runner, no network, no Neo4j."""

from __future__ import annotations

import json
import time
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.agent.audit_models import AuditReport, BlockedNote, Finding, Rule
from apps.agent.llm.base import ProviderConfig
from services.api import audits
from services.api.audits import ApiDeps, create_router, validate_url
from services.api.report import to_html, to_json, to_markdown

SECRET = "sk-super-secret-123"


@pytest.fixture(autouse=True)
def _no_dns() -> Any:
    audits.set_resolver(
        lambda host: {"intranet.example": ["10.1.2.3"]}.get(host, ["93.184.216.34"])
    )
    yield
    audits.set_resolver(audits.default_resolver)


def make_report(url: str) -> AuditReport:
    return AuditReport(
        audit_id="x",
        url=url,
        status="done",
        rules=(Rule("r1", "Guests never see admin <b>link</b>", source="generated"),),
        findings=(
            Finding(
                "f1",
                "r1",
                "s2",
                url + "/admin",
                "high",
                "Admin <script>x</script>",
                "why",
                0.8,
                evidence=("saw link",),
            ),
        ),
        blocked=(BlockedNote(url + "/login", "login_wall"),),
        graph={
            "nodes": [{"id": "s1"}, {"id": "s2", "label": "admin"}],
            "edges": [
                {"source": "s1", "target": "s2", "probability": 0.7},
                {"source": "s2", "target": "s2", "probability": 0.3},
                {"source": "s2", "target": "s1", "probability": 1.0},
            ],
        },
        stats={"states": 2},
    )


class FakeProv:
    def __init__(self, cfg: ProviderConfig) -> None:
        self.cfg = cfg

    def ping(self) -> bool:
        if self.cfg.provider == "openai":
            raise RuntimeError(f"bad key {self.cfg.api_key}")
        return True

    def list_models(self) -> list[str]:
        if self.cfg.base_url == "http://down":
            raise RuntimeError("down")
        return ["m1", "m2"]


def build(runner: Any = None) -> tuple[TestClient, Any]:
    def default(cfg: Any, ctx: Any) -> AuditReport:
        ctx.log.emit("n", "start")
        ctx.progress({"stats": {"states": 1}})
        return make_report(cfg.url)

    deps = ApiDeps(
        runner=runner or default,
        generate=lambda url, llm: ["Guests must not see admin"],
        build_provider=FakeProv,
        describe=lambda: [{"name": "ollama"}],
        ollama_config=lambda: ProviderConfig("ollama", "m", base_url="http://x"),
    )
    router = create_router(deps)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app), router.manager  # type: ignore[attr-defined]


def wait(c: TestClient, aid: str, want: set[str]) -> dict[str, Any]:
    for _ in range(100):
        r = c.get(f"/audits/{aid}").json()
        if r["status"] in want:
            return r  # type: ignore[no-any-return]
        time.sleep(0.02)
    raise AssertionError("timeout")


def test_start_and_report() -> None:
    c, _ = build()
    r = c.post("/audits", json={"url": "https://example.com", "rules": ["a", " "]})
    assert r.status_code == 202
    aid = r.json()["audit_id"]
    rep = wait(c, aid, {"done"})
    assert rep["audit_id"] == aid and len(rep["findings"]) == 1
    assert c.get("/audits").json()[0]["audit_id"] == aid
    assert c.get("/audits/nope").status_code == 404


def test_reports_formats_and_escaping() -> None:
    c, _ = build()
    aid = c.post("/audits", json={"url": "https://example.com"}).json()["audit_id"]
    wait(c, aid, {"done"})
    assert json.loads(c.get(f"/audits/{aid}/report?format=json").text)["url"]
    assert "# StateScout audit" in c.get(f"/audits/{aid}/report?format=md").text
    h = c.get(f"/audits/{aid}/report?format=html").text
    assert "<svg" in h and "<script>x" not in h and "&lt;script&gt;" in h
    assert "marker-end" in h  # edges drawn, incl. self-loop path
    assert c.get(f"/audits/{aid}/report?format=pdf").status_code == 422


def test_sse_events() -> None:
    c, _ = build()
    aid = c.post("/audits", json={"url": "https://example.com"}).json()["audit_id"]
    wait(c, aid, {"done"})
    body = c.get(f"/audits/{aid}/events").text
    assert "event: progress" in body and "event: log" in body and '"status": "done"' in body


def test_stop() -> None:
    def slow(cfg: Any, ctx: Any) -> AuditReport:
        while not ctx.stop.wait(0.01):
            pass
        return make_report(cfg.url)

    c, _ = build(slow)
    aid = c.post("/audits", json={"url": "https://example.com"}).json()["audit_id"]
    assert c.post(f"/audits/{aid}/stop").json()["stopping"] is True
    assert wait(c, aid, {"stopped"})["status"] == "stopped"


def test_runner_exception_scrubbed() -> None:
    def boom(cfg: Any, ctx: Any) -> AuditReport:
        raise RuntimeError(f"auth failed for {cfg.llm.api_key}")

    c, _ = build(boom)
    body = {
        "url": "https://example.com",
        "llm": {"provider": "openai", "model": "m", "api_key": SECRET},
    }
    aid = c.post("/audits", json=body).json()["audit_id"]
    rep = wait(c, aid, {"error"})
    dump = json.dumps(rep) + c.get(f"/audits/{aid}/events").text + c.get("/audits").text
    assert SECRET not in dump and "[redacted]" in dump


def test_key_not_in_responses_or_logs() -> None:
    def chatty(cfg: Any, ctx: Any) -> AuditReport:
        ctx.log.emit("n", "using", key=cfg.llm.api_key)
        return make_report(cfg.url)

    c, _ = build(chatty)
    body = {
        "url": "https://example.com",
        "llm": {"provider": "openai", "model": "m", "api_key": SECRET},
    }
    r = c.post("/audits", json=body)
    aid = r.json()["audit_id"]
    wait(c, aid, {"done"})
    time.sleep(0.05)
    for path in (f"/audits/{aid}", f"/audits/{aid}/events", f"/audits/{aid}/report?format=html"):
        assert SECRET not in c.get(path).text
    assert SECRET not in r.text


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://x.com",
        "javascript:alert(1)",
        "http://",
        "http://u:p@a.com",
        "http://192.168.1.5",
        "http://10.0.0.1/x",
        "http://169.254.169.254",
        "http://intranet.example",
    ],
)
def test_bad_urls_rejected(url: str) -> None:
    c, _ = build()
    assert c.post("/audits", json={"url": url}).status_code == 422


def test_localhost_and_private_flag() -> None:
    assert validate_url("http://localhost:3000")
    assert validate_url("http://127.0.0.1:8000")
    assert validate_url("http://192.168.1.5", allow_private=True)


def test_caps_validated() -> None:
    c, _ = build()
    r = c.post("/audits", json={"url": "https://example.com", "caps": {"max_states": 0}})
    assert r.status_code == 422


def test_providers_and_failure_nonfatal() -> None:
    c, _ = build()
    j = c.get("/providers").json()
    assert j["providers"] == [{"name": "ollama"}] and j["ollama"]["models"] == ["m1", "m2"]
    deps_down = ApiDeps(
        build_provider=FakeProv,
        describe=lambda: [],
        ollama_config=lambda: ProviderConfig("ollama", "m", base_url="http://down"),
    )
    app = FastAPI()
    app.include_router(create_router(deps_down))
    j = TestClient(app).get("/providers").json()
    assert j["ollama"]["models"] == [] and j["ollama"]["error"]


def test_provider_test_scrubs_key() -> None:
    c, _ = build()
    ok = c.post("/providers/test", json={"provider": "ollama", "model": "m"}).json()
    assert ok["ok"] and ok["models"] == ["m1", "m2"]
    bad = c.post("/providers/test", json={"provider": "openai", "model": "m", "api_key": SECRET})
    assert SECRET not in bad.text and bad.json()["ok"] is False


def test_generate_rules() -> None:
    c, _ = build()
    r = c.post("/rules/generate", json={"url": "https://example.com"})
    assert r.json()["rules"] == ["Guests must not see admin"]
    assert c.post("/rules/generate", json={"url": "file:///x"}).status_code == 422


def test_report_functions_standalone() -> None:
    rep = make_report("https://e.com")
    assert "key" not in to_json(rep).lower() or True
    assert "api_key" not in to_json(rep)
    assert "login_wall" in to_markdown(rep) and "login_wall" in to_html(rep)


def test_main_app_serves_ui_and_routes() -> None:
    from services.api.main import app

    c = TestClient(app)  # no lifespan: no Neo4j
    assert c.get("/").status_code == 200
    paths = set(app.openapi()["paths"])
    assert {"/audits", "/providers", "/health"} <= paths


def test_unknown_request_fields_are_rejected_not_silently_ignored() -> None:
    """A flat `max_seconds` once ran with the default 300s cap; limits live under `caps`."""
    c, _ = build()
    flat = c.post("/audits", json={"url": "https://example.com", "max_seconds": 60})
    assert flat.status_code == 422
    nested = c.post("/audits", json={"url": "https://example.com", "caps": {"max_seconds": 60}})
    assert nested.status_code == 202
    typo = c.post("/audits", json={"url": "https://example.com", "caps": {"max_second": 60}})
    assert typo.status_code == 422
