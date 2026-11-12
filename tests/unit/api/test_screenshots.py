"""Screenshots: served per audit from an allowlist, never by arbitrary path."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from apps.agent.audit_models import AuditReport
from services.api.report import to_html
from tests.unit.api.test_audits import build, make_report, wait

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _runner(shot: Path) -> Any:
    def run(cfg: Any, ctx: Any) -> AuditReport:
        rep = make_report(cfg.url)
        finding = replace(rep.findings[0], screenshot=str(shot))
        graph = {"nodes": [{"id": "s1", "screenshot": str(shot)}], "edges": []}
        return replace(rep, findings=(finding,), graph=graph)

    return run


def _audit(tmp_path: Path) -> tuple[TestClient, str, Path]:
    shot = tmp_path / "capture_1.png"
    shot.write_bytes(PNG)
    c, _ = build(_runner(shot))
    aid = c.post("/audits", json={"url": "https://example.com"}).json()["audit_id"]
    return c, aid, shot


def test_api_exposes_a_url_not_the_local_path(tmp_path: Path) -> None:
    c, aid, _ = _audit(tmp_path)
    f = wait(c, aid, {"done"})["findings"][0]
    assert f["screenshot"].startswith(f"/audits/{aid}/screenshots/")
    assert str(tmp_path) not in f["screenshot"]


def test_screenshot_is_served_as_an_image(tmp_path: Path) -> None:
    c, aid, _ = _audit(tmp_path)
    url = wait(c, aid, {"done"})["findings"][0]["screenshot"]
    r = c.get(url)
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert r.content == PNG


def test_unknown_token_and_other_audit_get_404(tmp_path: Path) -> None:
    c, aid, _ = _audit(tmp_path)
    wait(c, aid, {"done"})
    assert c.get(f"/audits/{aid}/screenshots/deadbeefdeadbeef").status_code == 404
    assert c.get(f"/audits/{aid}/screenshots/..%2F..%2Fetc%2Fpasswd").status_code == 404


def test_non_image_path_in_a_report_is_never_served(tmp_path: Path) -> None:
    secret = tmp_path / "secrets.txt"
    secret.write_text("nope")
    c, _ = build(_runner(secret))
    aid = c.post("/audits", json={"url": "https://example.com"}).json()["audit_id"]
    f = wait(c, aid, {"done"})["findings"][0]
    assert f["screenshot"] is None or "/screenshots/" not in f["screenshot"]


def test_html_report_embeds_screenshots(tmp_path: Path) -> None:
    shot = tmp_path / "s.png"
    shot.write_bytes(PNG)
    rep = make_report("https://e.com")
    rep = replace(rep, findings=(replace(rep.findings[0], screenshot=str(shot)),))
    assert "data:image/png;base64," in to_html(rep)


def test_html_report_embeds_a_shared_screenshot_once_and_hides_local_paths(tmp_path: Path) -> None:
    shot = tmp_path / "s.png"
    shot.write_bytes(PNG)
    big = tmp_path / "big.png"
    big.write_bytes(PNG + b"\x00" * 500_000)  # over the embed cap
    rep = make_report("https://e.com")
    first = replace(rep.findings[0], screenshot=str(shot))
    findings = (
        first,
        replace(first, finding_id="f2"),
        replace(first, finding_id="f3", screenshot=str(big)),
    )
    out = to_html(replace(rep, findings=findings))
    assert out.count("base64,") == 1
    assert str(tmp_path) not in out and "big.png" in out
