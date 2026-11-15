from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from apps.agent.llm.base import LLMProvider, ProviderConfig, ProviderError
from apps.agent.llm.registry import build_provider, default_config_from_env, describe_providers

SECRET = "sk-super-secret-123"


class _Server:
    def __init__(self, routes: dict[str, tuple[int, object]]) -> None:
        self.requests: list[tuple[str, str, dict[str, str], object]] = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def _do(self) -> None:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n)) if n else None
                outer.requests.append(
                    (self.command, self.path, {k.lower(): v for k, v in self.headers.items()}, body)
                )
                code, payload = routes.get(self.path, (404, {"error": "nope"}))
                raw = json.dumps(payload).encode()
                self.send_response(code)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            do_GET = do_POST = _do

            def log_message(self, *a: object) -> None:
                pass

        self.httpd = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def serve():
    servers: list[_Server] = []

    def make(routes: dict[str, tuple[int, object]]) -> _Server:
        s = _Server(routes)
        servers.append(s)
        return s

    yield make
    for s in servers:
        s.close()


def _cfg(kind, srv, key=None):
    return ProviderConfig(provider=kind, model="m", base_url=srv.url, api_key=key, timeout_s=5)


def test_ollama(serve):
    srv = serve(
        {
            "/api/chat": (200, {"message": {"content": "hi"}}),
            "/api/tags": (200, {"models": [{"name": "llava:7b"}]}),
        }
    )
    p = build_provider(_cfg("ollama", srv))
    assert isinstance(p, LLMProvider)
    assert p.complete("q", system="s", images=(b"\x89PNG",), json_mode=True) == "hi"
    body = srv.requests[0][3]
    assert body["stream"] is False and body["format"] == "json"
    assert body["messages"][0] == {"role": "system", "content": "s"}
    assert body["messages"][1]["images"] == ["iVBORw=="]
    assert p.list_models() == ["llava:7b"]
    assert p.ping() is True


def test_openai_compat_vision_and_auth(serve):
    srv = serve(
        {
            "/v1/chat/completions": (200, {"choices": [{"message": {"content": "ok"}}]}),
            "/v1/models": (200, {"data": [{"id": "gpt-x"}]}),
        }
    )
    p = build_provider(_cfg("openai", srv, SECRET))
    assert p.complete("q", images=(b"abc",), json_mode=True) == "ok"
    _, _, headers, body = srv.requests[0]
    assert headers["authorization"] == f"Bearer {SECRET}"
    parts = body["messages"][0]["content"]
    assert parts[0]["image_url"]["url"].startswith("data:image/png;base64,")
    assert parts[1] == {"type": "text", "text": "q"}
    assert body["response_format"] == {"type": "json_object"}
    assert p.list_models() == ["gpt-x"]


def test_openai_base_url_with_v1_suffix(serve):
    srv = serve({"/v1/models": (200, {"data": []})})
    p = build_provider(
        ProviderConfig(provider="openai", model="m", base_url=srv.url + "/v1", timeout_s=5)
    )
    assert p.ping() is True


def test_anthropic(serve):
    srv = serve(
        {
            "/v1/messages": (
                200,
                {"content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]},
            ),
            "/v1/models": (200, {"data": [{"id": "claude-x"}]}),
        }
    )
    p = build_provider(_cfg("anthropic", srv, SECRET))
    assert p.complete("q", system="s", images=(b"abc",)) == "ab"
    _, _, headers, body = srv.requests[0]
    assert headers["x-api-key"] == SECRET and "anthropic-version" in headers
    assert body["system"] == "s"
    assert body["messages"][0]["content"][0]["type"] == "image"
    assert p.list_models() == ["claude-x"]


def test_gemini_rest(serve):
    srv = serve(
        {
            "/v1beta/models/m:generateContent": (
                200,
                {"candidates": [{"content": {"parts": [{"text": "g"}]}}]},
            ),
            "/v1beta/models": (200, {"models": [{"name": "models/gem-1"}]}),
        }
    )
    p = build_provider(_cfg("gemini", srv, SECRET))
    p._sdk_checked = True  # type: ignore[attr-defined]  # force REST even if SDK installed
    assert p.complete("q", images=(b"x",), json_mode=True) == "g"
    _, _, headers, body = srv.requests[0]
    assert headers["x-goog-api-key"] == SECRET
    assert body["contents"][0]["parts"][0]["inline_data"]["mime_type"] == "image/png"
    assert body["generationConfig"] == {"responseMimeType": "application/json"}
    assert p.list_models() == ["gem-1"]


def test_http_error_does_not_leak_key(serve):
    srv = serve({"/v1/chat/completions": (401, {"error": "bad key"})})
    p = build_provider(_cfg("openai", srv, SECRET))
    with pytest.raises(ProviderError) as ei:
        p.complete("q")
    assert "401" in str(ei.value) and SECRET not in str(ei.value) and SECRET not in repr(ei.value)
    assert p.ping() is False
    assert SECRET not in repr(p.config)


def test_unreachable_raises_provider_error():
    p = build_provider(
        ProviderConfig(provider="ollama", model="m", base_url="http://127.0.0.1:1", timeout_s=2)
    )
    with pytest.raises(ProviderError):
        p.complete("q")
    assert p.ping() is False


def test_bad_shape_raises(serve):
    srv = serve({"/api/chat": (200, {"oops": 1})})
    with pytest.raises(ProviderError):
        build_provider(_cfg("ollama", srv)).complete("q")


def test_default_config_from_env(monkeypatch):
    for k in (
        "STATESCOUT_LLM_PROVIDER",
        "STATESCOUT_LLM_MODEL",
        "STATESCOUT_LLM_BASE_URL",
        "STATESCOUT_VLM_PROVIDER",
        "STATESCOUT_VLM_MODEL",
        "STATESCOUT_VLM_BASE_URL",
        "OLLAMA_HOST",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
    ):
        monkeypatch.delenv(k, raising=False)
    c = default_config_from_env("llm")
    assert c.provider == "ollama" and c.api_key is None
    monkeypatch.setenv("OLLAMA_HOST", "box:11434")
    assert default_config_from_env("vlm").base_url == "http://box:11434"
    monkeypatch.setenv("STATESCOUT_LLM_PROVIDER", "openai")
    monkeypatch.setenv("STATESCOUT_LLM_MODEL", "gpt-z")
    monkeypatch.setenv("STATESCOUT_LLM_BASE_URL", "http://lm:1234/v1")
    monkeypatch.setenv("OPENAI_API_KEY", SECRET)
    c = default_config_from_env("llm")
    assert (c.provider, c.model, c.base_url, c.api_key) == (
        "openai",
        "gpt-z",
        "http://lm:1234/v1",
        SECRET,
    )
    monkeypatch.setenv("STATESCOUT_VLM_MODEL", "vis")
    assert default_config_from_env("vlm").model == "vis"
    monkeypatch.setenv("STATESCOUT_LLM_PROVIDER", "bogus")
    with pytest.raises(ProviderError):
        default_config_from_env("llm")


def test_describe_providers_is_secret_free(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", SECRET)
    d = describe_providers()
    assert {x["name"] for x in d} == {"ollama", "openai", "anthropic", "gemini"}
    assert SECRET not in json.dumps(d)
    assert next(x for x in d if x["name"] == "ollama")["needs_key"] is False
    assert next(x for x in d if x["name"] == "openai")["needs_key"] is True
    assert all({"name", "needs_key", "default_base_url", "default_models"} <= x.keys() for x in d)
