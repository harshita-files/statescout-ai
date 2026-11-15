"""A VLM request must fit a small context window: bounded image, bounded prompt, explicit ctx."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, ClassVar

from apps.agent.contracts import UIElement
from apps.agent.llm.base import ProviderConfig
from apps.agent.llm.ollama import OllamaProvider
from apps.agent.perception.gemini import VLMPerception


class _Echo(BaseHTTPRequestHandler):
    bodies: ClassVar[list[dict[str, Any]]] = []

    def do_POST(self) -> None:
        n = int(self.headers.get("Content-Length", 0))
        self.bodies.append(json.loads(self.rfile.read(n)))
        out = json.dumps({"message": {"content": "[]"}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a: Any) -> None:
        pass


def test_ollama_requests_set_an_explicit_context_window() -> None:
    _Echo.bodies = []
    srv = HTTPServer(("127.0.0.1", 0), _Echo)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        cfg = ProviderConfig("ollama", "m", base_url=f"http://127.0.0.1:{srv.server_port}")
        OllamaProvider(cfg).complete("hi", images=(b"\x89PNG",))
    finally:
        srv.shutdown()
    options = _Echo.bodies[0]["options"]
    assert 4096 < options["num_ctx"] <= 32768  # above Ollama's 4096 default, below a VRAM hog
    # JSON-mode decoding on a small model can run on until the client times out (2 minutes
    # per call); a generation cap makes it end.
    assert 64 <= options["num_predict"] <= 4096


class _Spy:
    config = ProviderConfig("ollama", "m")
    prompt = ""

    def complete(self, prompt: str, **_: Any) -> str:
        self.prompt = prompt
        return "[]"

    def list_models(self) -> list[str]:
        return []

    def ping(self) -> bool:
        return True


def _el(_i: int, name: str) -> UIElement:
    return UIElement(role="link", name=name)


def test_capability_prompt_dedupes_and_caps_the_element_list(tmp_path: Any) -> None:
    shot = tmp_path / "s.png"
    shot.write_bytes(b"\x89PNG")
    spy = _Spy()
    elements = tuple(_el(i, f"AAPL {i % 5}") for i in range(300))  # 300 rows, 5 distinct names
    VLMPerception(provider=spy)._gemini_capabilities(str(shot), elements)
    listed = [ln for ln in spy.prompt.splitlines() if ln[:1].isdigit() and "role=" in ln]
    assert 0 < len(listed) <= 5  # duplicates collapsed

    many = tuple(_el(i, f"unique link {i}") for i in range(300))
    VLMPerception(provider=spy)._gemini_capabilities(str(shot), many)
    listed = [ln for ln in spy.prompt.splitlines() if ln[:1].isdigit() and "role=" in ln]
    assert len(listed) <= 80


def test_circuit_breaker_stops_calling_a_failing_vlm(tmp_path: Any) -> None:
    """After 3 straight failures, stop paying the timeout on every remaining state."""
    from apps.agent.contracts import CaptureBundle
    from apps.agent.llm.base import ProviderError

    class Broken(_Spy):
        calls = 0

        def complete(self, prompt: str, **_: Any) -> str:
            Broken.calls += 1
            raise ProviderError("500 out of memory")

    shot = tmp_path / "s.png"
    shot.write_bytes(b"\x89PNG")
    ax = {"role": "RootWebArea", "name": "p", "children": [{"role": "link", "name": "Home"}]}
    bundle = CaptureBundle("http://a.test/", "<a href='/'>Home</a>", ax, str(shot))
    perception = VLMPerception(provider=Broken())
    for _ in range(10):
        assert perception.analyze(bundle, "guest").elements  # crawl continues, DOM-only
    assert Broken.calls == 3
    assert perception.degraded_calls == 10


def test_a_success_resets_the_breaker(tmp_path: Any) -> None:
    from apps.agent.contracts import CaptureBundle
    from apps.agent.llm.base import ProviderError

    class Flaky(_Spy):
        n = 0

        def complete(self, prompt: str, **_: Any) -> str:
            Flaky.n += 1
            if Flaky.n % 3 != 0:  # fail, fail, succeed, fail, fail, succeed ...
                raise ProviderError("blip")
            return "[]"

    shot = tmp_path / "s.png"
    shot.write_bytes(b"\x89PNG")
    ax = {"role": "RootWebArea", "name": "p", "children": [{"role": "link", "name": "Home"}]}
    bundle = CaptureBundle("http://a.test/", "<a href='/'>Home</a>", ax, str(shot))
    perception = VLMPerception(provider=Flaky())
    for _ in range(9):
        perception.analyze(bundle, "guest")
    assert Flaky.n == 9  # never tripped: no 3 consecutive failures
