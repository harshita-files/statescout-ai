"""Ollama backend (REST: /api/chat, /api/tags)."""

from __future__ import annotations

from apps.agent.llm._http import b64, request_json
from apps.agent.llm.base import ProviderConfig, ProviderError

DEFAULT_BASE_URL = "http://localhost:11434"


class OllamaProvider:
    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self._base = (config.base_url or DEFAULT_BASE_URL).rstrip("/")

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        images: tuple[bytes, ...] = (),
        json_mode: bool = False,
    ) -> str:
        messages: list[dict[str, object]] = []
        if system:
            messages.append({"role": "system", "content": system})
        user: dict[str, object] = {"role": "user", "content": prompt}
        if images:
            user["images"] = [b64(i) for i in images]
        messages.append(user)
        body: dict[str, object] = {
            "model": self.config.model,
            "messages": messages,
            "stream": False,
        }
        if json_mode:
            body["format"] = "json"
        data = request_json(
            "POST", f"{self._base}/api/chat", body=body, timeout=self.config.timeout_s
        )
        try:
            return str(data["message"]["content"])
        except (KeyError, TypeError):
            raise ProviderError("unexpected Ollama response shape") from None

    def list_models(self) -> list[str]:
        data = request_json("GET", f"{self._base}/api/tags", timeout=min(self.config.timeout_s, 15))
        try:
            return [str(m["name"]) for m in data["models"]]
        except (KeyError, TypeError):
            raise ProviderError("unexpected Ollama response shape") from None

    def ping(self) -> bool:
        try:
            self.list_models()
        except ProviderError:
            return False
        return True
