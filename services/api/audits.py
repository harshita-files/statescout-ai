"""Product API: user-facing audits (no Neo4j / Docker required).

Routes (all behind the optional ``X-API-Key`` guard):

    POST /audits                 start an audit            -> {audit_id}
    GET  /audits                 list audits
    GET  /audits/{id}            AuditReport JSON
    GET  /audits/{id}/events     SSE progress stream
    POST /audits/{id}/stop       request a stop
    GET  /audits/{id}/report     ?format=json|md|html
    GET  /providers              catalogue + live Ollama models
    POST /providers/test         ping a provider config
    POST /rules/generate         draft rules from a site

API keys are accepted per request, live only inside the running audit thread's
closure, and are never logged, echoed, persisted or put in a report (NFR-11).

Seams: everything that touches the other tracks' (concurrently built) modules
goes through :class:`ApiDeps`. Defaults import lazily; tests inject fakes.
"""

from __future__ import annotations

import dataclasses
import ipaddress
import json
import socket
import threading
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from apps.agent.audit_models import AuditConfig, AuditReport, Rule
from apps.agent.llm.base import ProviderConfig
from services.api import report as report_mod
from services.api.auth import require_api_key

MAX_RULES = 50
MAX_RULE_LEN = 500
TERMINAL = {"done", "error", "stopped"}


# --------------------------------------------------------------------------- #
# Secret hygiene
# --------------------------------------------------------------------------- #


def scrub(text: str, secrets: list[str | None]) -> str:
    """Remove any known secret value from an error string (NFR-11)."""
    for s in secrets:
        if s and len(s) >= 4:
            text = text.replace(s, "[redacted]")
    return text


# --------------------------------------------------------------------------- #
# URL validation
# --------------------------------------------------------------------------- #

Resolver = Callable[[str], list[str]]


def default_resolver(host: str) -> list[str]:
    try:
        return sorted({str(i[4][0]) for i in socket.getaddrinfo(host, None)})
    except OSError:
        return []


_resolver: Resolver = default_resolver


def set_resolver(fn: Resolver) -> None:
    """Test hook: replace DNS resolution."""
    global _resolver
    _resolver = fn


def _is_private(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip.split("%")[0])
    except ValueError:
        return False
    if addr.is_loopback:
        return False  # loopback == localhost, allowed
    return bool(
        addr.is_private
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def validate_url(url: str, *, allow_private: bool = False) -> str:
    """Return the normalised URL or raise ValueError. http/https only."""
    url = url.strip()
    parts = urlsplit(url)
    if parts.scheme.lower() not in ("http", "https"):
        raise ValueError("only http and https URLs are allowed")
    host = parts.hostname
    if not host:
        raise ValueError("URL has no host")
    if parts.username or parts.password:
        raise ValueError("credentials in the URL are not allowed")
    if host.lower() == "localhost" or host.lower().endswith(".localhost"):
        return url
    try:
        ips = [host]
        ipaddress.ip_address(host)
    except ValueError:
        ips = _resolver(host)
        if host.lower().endswith((".local", ".internal", ".lan")):
            ips = [*ips, "10.0.0.0"]
    if not allow_private and any(_is_private(ip) for ip in ips):
        raise ValueError(
            "target resolves to a private/internal address; "
            "set allow_private=true only for sites you own or are authorized to test"
        )
    return url


# --------------------------------------------------------------------------- #
# Request models
# --------------------------------------------------------------------------- #


class ProviderIn(BaseModel):
    provider: Literal["ollama", "gemini", "openai", "anthropic"]
    model: str = Field(min_length=1, max_length=200)
    base_url: str | None = Field(default=None, max_length=500)
    api_key: str | None = Field(default=None, max_length=500, repr=False)

    def to_config(self) -> ProviderConfig:
        return ProviderConfig(
            provider=self.provider,
            model=self.model,
            base_url=self.base_url or None,
            api_key=self.api_key or None,
        )


class Caps(BaseModel):
    max_states: int = Field(default=40, ge=1, le=500)
    depth_limit: int = Field(default=3, ge=0, le=10)
    max_seconds: int = Field(default=300, ge=5, le=3600)
    requests_per_second: float = Field(default=1.0, gt=0, le=20)


class AuditRequest(BaseModel):
    url: str
    rules: list[str] = Field(default_factory=list)
    auto_rules: bool = True
    llm: ProviderIn | None = None
    vlm: ProviderIn | None = None
    caps: Caps = Field(default_factory=Caps)
    respect_robots: bool = True
    probabilistic: bool = True
    allow_private: bool = False


class ProviderTestRequest(ProviderIn):
    pass


class GenerateRulesRequest(BaseModel):
    url: str
    llm: ProviderIn | None = None
    allow_private: bool = False


# --------------------------------------------------------------------------- #
# Seams
# --------------------------------------------------------------------------- #


@dataclass
class RunContext:
    """What a runner receives. ``log`` has ``emit(node, event, **fields)``."""

    audit_id: str
    log: Any
    stop: threading.Event
    progress: Callable[[Any], None]


Runner = Callable[[AuditConfig, RunContext], AuditReport]


def default_runner(config: AuditConfig, ctx: RunContext) -> AuditReport:  # pragma: no cover
    """Adapter onto the orchestrator (imported lazily; built by another track).

    Seam: expected signatures are ``parse_rules(texts, llm) -> (expectations,
    rules)``, ``live_ports(graph="memory", ...)`` and
    ``run_audit(config, ports, expectations, log, stop=..., progress=...)``.
    """
    from apps.agent.crawler.safety import SafetyPolicy
    from apps.agent.llm.registry import build_provider
    from apps.agent.orchestrator.audit_runner import run_audit
    from apps.agent.orchestrator.deps import live_ports
    from apps.agent.perception import VLMPerception
    from apps.agent.rules import generate_rules, parse_rules

    llm = build_provider(config.llm) if config.llm else None
    # No VLM configured -> DOM-only perception (never silently falls back to a paid API).
    perception = (
        VLMPerception(provider=build_provider(config.vlm), dom_only=False)
        if config.vlm
        else VLMPerception(dom_only=True)
    )
    texts: list[Any] = list(config.rules)
    if config.auto_rules:
        generated = generate_rules([{"url": config.url, "text": _fetch_text(config.url)}], llm)
        known = {getattr(t, "text", t) for t in texts}
        texts += [r for r in generated if r.text not in known]
    expectations, parsed = parse_rules(texts, llm)
    config = dataclasses.replace(config, rules=tuple(parsed))
    safety = SafetyPolicy(
        respect_robots=config.respect_robots,
        requests_per_second=config.requests_per_second,
        max_pages=config.max_states,
        max_seconds=float(config.max_seconds),
        allow_destructive=config.allow_destructive,
    )
    ports = live_ports(
        graph="memory",
        probabilistic_states=config.probabilistic,
        safety=safety,
        perception=perception,
    )
    return run_audit(
        config, ports, expectations, ctx.log, stop=ctx.stop.is_set, progress=ctx.progress
    )


def _fetch_text(url: str, limit: int = 20000) -> str:
    """Best-effort visible text of the landing page (stdlib; failures give '')."""
    import re
    import urllib.request

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "StateScout/0.2"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read(200_000).decode("utf-8", "replace")
    except Exception:
        return ""
    raw = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw))[:limit]


def default_generate(url: str, llm_cfg: ProviderConfig | None) -> list[str]:  # pragma: no cover
    from apps.agent.llm.registry import build_provider
    from apps.agent.rules import generate_rules

    llm = build_provider(llm_cfg) if llm_cfg else None
    out = generate_rules([{"url": url, "text": _fetch_text(url)}], llm)
    return [r.text if hasattr(r, "text") else str(r) for r in out]


def default_build_provider(cfg: ProviderConfig) -> Any:  # pragma: no cover
    from apps.agent.llm.registry import build_provider

    return build_provider(cfg)


def default_describe() -> list[dict[str, Any]]:  # pragma: no cover
    from apps.agent.llm.registry import describe_providers

    return describe_providers()


def default_ollama_default() -> ProviderConfig:  # pragma: no cover
    from apps.agent.llm.registry import default_config_from_env

    cfg = default_config_from_env("llm")
    return ProviderConfig(provider="ollama", model=cfg.model, base_url=cfg.base_url)


@dataclass
class ApiDeps:
    runner: Runner = default_runner
    generate: Callable[[str, ProviderConfig | None], list[str]] = default_generate
    build_provider: Callable[[ProviderConfig], Any] = default_build_provider
    describe: Callable[[], list[dict[str, Any]]] = default_describe
    ollama_config: Callable[[], ProviderConfig] = default_ollama_default


# --------------------------------------------------------------------------- #
# Audit records
# --------------------------------------------------------------------------- #


class _StreamLog:
    """Minimal Logger look-alike: JSON-lines to events, never sees secrets."""

    def __init__(self, rec: AuditRecord) -> None:
        self._rec = rec

    def emit(self, node: str, event: str, **fields: Any) -> None:
        self._rec.add_event("log", {"node": node, "event": event, **fields})

    # Logger(stream=...) compatibility for runners that write lines.
    def write(self, line: str) -> int:
        for part in line.splitlines():
            if part.strip():
                try:
                    data = json.loads(part)
                except ValueError:
                    data = {"message": part}
                self._rec.add_event("log", data if isinstance(data, dict) else {"message": part})
        return len(line)

    def flush(self) -> None:
        return None


@dataclass
class AuditRecord:
    audit_id: str
    url: str
    created_at: str
    status: str = "running"
    report: AuditReport | None = None
    partial: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    stop: threading.Event = field(default_factory=threading.Event)
    cond: threading.Condition = field(default_factory=threading.Condition)
    secrets: list[str | None] = field(default_factory=list)
    rules: tuple[Rule, ...] = ()

    def add_event(self, kind: str, data: dict[str, Any]) -> None:
        text = json.dumps(data, default=str)
        text = scrub(text, self.secrets)
        with self.cond:
            self.events.append({"id": len(self.events), "type": kind, "data": json.loads(text)})
            self.cond.notify_all()

    def current_report(self) -> AuditReport:
        if self.report is not None:
            return self.report
        return AuditReport(
            audit_id=self.audit_id,
            url=self.url,
            status=self.status,  # type: ignore[arg-type]
            rules=self.rules,
            graph=self.partial.get("graph", {}),
            stats=self.partial.get("stats", {}),
            findings=tuple(self.partial.get("findings", ())),
            error=self.error,
        )


class AuditManager:
    def __init__(self, deps: ApiDeps) -> None:
        self.deps = deps
        self._records: dict[str, AuditRecord] = {}
        self._lock = threading.Lock()
        self._threads: dict[str, threading.Thread] = {}

    def start(self, config: AuditConfig) -> AuditRecord:
        aid = uuid.uuid4().hex[:12]
        secrets = [c.api_key for c in (config.llm, config.vlm) if c]
        rec = AuditRecord(
            audit_id=aid,
            url=config.url,
            created_at=datetime.now(UTC).isoformat(),
            secrets=secrets,
            rules=config.rules,
        )
        with self._lock:
            self._records[aid] = rec
        t = threading.Thread(target=self._run, args=(rec, config), daemon=True, name=f"audit-{aid}")
        self._threads[aid] = t
        rec.add_event("status", {"status": "running"})
        t.start()
        return rec

    def _run(self, rec: AuditRecord, config: AuditConfig) -> None:
        def progress(update: Any) -> None:
            if isinstance(update, dict):
                for key in ("graph", "stats", "findings"):
                    if key in update:
                        rec.partial[key] = update[key]
                rec.add_event("progress", _jsonable(update))
            else:
                rec.add_event("progress", {"message": str(update)})

        ctx = RunContext(rec.audit_id, _StreamLog(rec), rec.stop, progress)
        try:
            rep = self.deps.runner(config, ctx)
            status = "stopped" if rec.stop.is_set() and rep.status != "error" else rep.status
            if status == "running":
                status = "done"
            rec.report = dataclasses.replace(
                rep,
                audit_id=rec.audit_id,
                status=status,
                error=scrub(rep.error, rec.secrets) if rep.error else None,
            )
            rec.status = status
        except Exception as exc:
            msg = scrub(f"{type(exc).__name__}: {exc}", rec.secrets)
            rec.error = msg
            rec.status = "error"
            rec.report = AuditReport(
                audit_id=rec.audit_id,
                url=rec.url,
                status="error",
                rules=rec.rules,
                graph=rec.partial.get("graph", {}),
                stats=rec.partial.get("stats", {}),
                error=msg,
            )
        finally:
            rec.secrets = []  # drop key material as soon as the run ends
            rec.add_event("status", {"status": rec.status, "error": rec.error})

    def get(self, aid: str) -> AuditRecord:
        rec = self._records.get(aid)
        if rec is None:
            raise HTTPException(404, "audit not found")
        return rec

    def list(self) -> list[AuditRecord]:
        return sorted(self._records.values(), key=lambda r: r.created_at, reverse=True)

    def join(self, aid: str, timeout: float = 5.0) -> None:
        t = self._threads.get(aid)
        if t:
            t.join(timeout)


def _jsonable(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return _jsonable(dataclasses.asdict(obj))
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items() if k != "api_key"}
    if isinstance(obj, (list, tuple, set)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


def _sse(ev: dict[str, Any]) -> str:
    return f"id: {ev['id']}\nevent: {ev['type']}\ndata: {json.dumps(ev['data'])}\n\n"


# --------------------------------------------------------------------------- #
# Router factory
# --------------------------------------------------------------------------- #


def create_router(deps: ApiDeps | None = None) -> APIRouter:
    deps = deps or ApiDeps()
    mgr = AuditManager(deps)
    router = APIRouter(dependencies=[Depends(require_api_key)])
    router.manager = mgr  # type: ignore[attr-defined]

    def _check_url(url: str, allow_private: bool) -> str:
        try:
            return validate_url(url, allow_private=allow_private)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.post("/audits", status_code=202, tags=["audits"])
    def start_audit(body: AuditRequest) -> dict[str, str]:
        url = _check_url(body.url, body.allow_private)
        texts = [t.strip() for t in body.rules if t and t.strip()]
        if len(texts) > MAX_RULES or any(len(t) > MAX_RULE_LEN for t in texts):
            raise HTTPException(422, f"at most {MAX_RULES} rules of {MAX_RULE_LEN} chars")
        config = AuditConfig(
            url=url,
            rules=tuple(Rule(rule_id=f"user-{i}", text=t) for i, t in enumerate(texts, 1)),
            auto_rules=body.auto_rules,
            llm=body.llm.to_config() if body.llm else None,
            vlm=body.vlm.to_config() if body.vlm else None,
            max_states=body.caps.max_states,
            depth_limit=body.caps.depth_limit,
            max_seconds=body.caps.max_seconds,
            requests_per_second=body.caps.requests_per_second,
            respect_robots=body.respect_robots,
            probabilistic=body.probabilistic,
        )
        rec = mgr.start(config)
        return {"audit_id": rec.audit_id}

    @router.get("/audits", tags=["audits"])
    def list_audits() -> list[dict[str, Any]]:
        out = []
        for r in mgr.list():
            rep = r.current_report()
            out.append(
                {
                    "audit_id": r.audit_id,
                    "url": r.url,
                    "status": r.status,
                    "created_at": r.created_at,
                    "findings": len(rep.findings),
                }
            )
        return out

    @router.get("/audits/{audit_id}", tags=["audits"])
    def get_audit(audit_id: str) -> Any:
        rep = mgr.get(audit_id).current_report()
        data = report_mod.report_to_dict(rep)
        servable = {p for p in report_mod.screenshot_paths(rep) if report_mod.image_media_type(p)}

        def url_for(path: Any) -> Any:
            if not isinstance(path, str) or path.startswith("data:"):
                return path
            if path in servable:
                return f"/audits/{audit_id}/screenshots/{report_mod.shot_token(path)}"
            return None  # not a servable image: never expose a raw local path

        for f in data.get("findings", []):
            f["screenshot"] = url_for(f.get("screenshot"))
        for n in data.get("graph", {}).get("nodes", []):
            if isinstance(n, dict) and "screenshot" in n:
                n["screenshot"] = url_for(n["screenshot"])
        return data

    @router.get("/audits/{audit_id}/screenshots/{token}", tags=["audits"])
    def audit_screenshot(audit_id: str, token: str) -> FileResponse:
        """Serve one of THIS audit's own screenshots; anything else is a 404."""
        rep = mgr.get(audit_id).current_report()
        by_token = {report_mod.shot_token(p): p for p in report_mod.screenshot_paths(rep)}
        path = by_token.get(token)
        media = report_mod.image_media_type(path) if path else None
        if path is None or media is None:
            raise HTTPException(404, "screenshot not found")
        return FileResponse(
            path, media_type=media, headers={"Cache-Control": "private, max-age=3600"}
        )

    @router.get("/audits/{audit_id}/events", tags=["audits"])
    def audit_events(audit_id: str) -> StreamingResponse:
        rec = mgr.get(audit_id)

        def gen() -> Iterator[str]:
            i = 0
            idle = 0.0
            while True:
                with rec.cond:
                    if i >= len(rec.events):
                        if rec.status in TERMINAL:
                            return
                        rec.cond.wait(timeout=1.0)
                    batch = rec.events[i:]
                if batch:
                    idle = 0.0
                    for ev in batch:
                        yield _sse(ev)
                    i += len(batch)
                else:
                    idle += 1.0
                    if idle >= 15:
                        idle = 0.0
                        yield ": keepalive\n\n"

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.post("/audits/{audit_id}/stop", tags=["audits"])
    def stop_audit(audit_id: str) -> dict[str, Any]:
        rec = mgr.get(audit_id)
        if rec.status not in TERMINAL:
            rec.stop.set()
            rec.add_event("status", {"status": "stopping"})
        return {"audit_id": audit_id, "stopping": rec.status not in TERMINAL}

    @router.get("/audits/{audit_id}/report", tags=["audits"])
    def audit_report(audit_id: str, format: Literal["json", "md", "html"] = Query("json")) -> Any:
        rep = mgr.get(audit_id).current_report()
        fname = f"statescout-{audit_id}"
        if format == "html":
            return HTMLResponse(
                report_mod.to_html(rep),
                headers={"Content-Disposition": f'attachment; filename="{fname}.html"'},
            )
        if format == "md":
            return PlainTextResponse(
                report_mod.to_markdown(rep),
                media_type="text/markdown",
                headers={"Content-Disposition": f'attachment; filename="{fname}.md"'},
            )
        return PlainTextResponse(
            report_mod.to_json(rep),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{fname}.json"'},
        )

    @router.get("/providers", tags=["providers"])
    def providers() -> dict[str, Any]:
        cat = deps.describe()
        live: dict[str, Any] = {"models": [], "error": None}
        try:
            cfg = deps.ollama_config()
            live["base_url"] = cfg.base_url
            live["models"] = list(deps.build_provider(cfg).list_models())
        except Exception as exc:
            live["error"] = f"{type(exc).__name__}: {exc}"[:300]
        return {"providers": cat, "ollama": live}

    @router.post("/providers/test", tags=["providers"])
    def test_provider(body: ProviderTestRequest) -> dict[str, Any]:
        cfg = body.to_config()
        try:
            prov = deps.build_provider(cfg)
            ok = bool(prov.ping())
            models: list[str] = []
            try:
                models = list(prov.list_models())
            except Exception:
                models = []
            return {"ok": ok, "models": models, "error": None if ok else "unreachable"}
        except Exception as exc:
            msg = scrub(f"{type(exc).__name__}: {exc}", [body.api_key])[:300]
            return {"ok": False, "models": [], "error": msg}

    @router.post("/rules/generate", tags=["audits"])
    def generate_rules_ep(body: GenerateRulesRequest) -> dict[str, Any]:
        url = _check_url(body.url, body.allow_private)
        key = body.llm.api_key if body.llm else None
        try:
            rules = deps.generate(url, body.llm.to_config() if body.llm else None)
        except Exception as exc:
            raise HTTPException(
                502, scrub(f"rule generation failed: {type(exc).__name__}: {exc}", [key])[:300]
            ) from exc
        return {"rules": [str(r) for r in rules][:MAX_RULES]}

    return router


__all__ = [
    "ApiDeps",
    "AuditManager",
    "RunContext",
    "create_router",
    "scrub",
    "set_resolver",
    "validate_url",
]
