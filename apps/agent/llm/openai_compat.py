"""OpenAI-compatible backend (OpenAI, OpenRouter, LM Studio, vLLM via base_url)."""

from __future__ import annotations

from apps.agent.llm._http import b64, request_json
from apps.agent.llm.base import ProviderConfig, ProviderError

DEFAULT_BASE_URL = "https://api.openai.com/v1"


class OpenAICompatProvider:
    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        base = (config.base_url or DEFAULT_BASE_URL).rstrip("/")
        # Accept both ".../v1" and a bare host such as http://localhost:1234.
        self._base = base if base.endswith("/v1") or "/v1/" in base else base + "/v1"

    def _headers(self) -> dict[str, str]:
        key = self.config.api_key
        return {"Authorization": f"Bearer {key}"} if key else {}

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
        content: object = prompt
        if images:
            parts: list[dict[str, object]] = [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64(i)}"},
                }
                for i in images
            ]
            parts.append({"type": "text", "text": prompt})
            content = parts
        messages.append({"role": "user", "content": content})
        body: dict[str, object] = {"model": self.config.model, "messages": messages}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        data = request_json(
            "POST",
            f"{self._base}/chat/completions",
            headers=self._headers(),
            body=body,
            timeout=self.config.timeout_s,
        )
        try:
            return str(data["choices"][0]["message"]["content"] or "")
        except (KeyError, IndexError, TypeError):
            raise ProviderError("unexpected chat/completions response shape") from None

    def list_models(self) -> list[str]:
        data = request_json(
            "GET",
            f"{self._base}/models",
            headers=self._headers(),
            timeout=min(self.config.timeout_s, 15),
        )
        try:
            return [str(m["id"]) for m in data["data"]]
        except (KeyError, TypeError):
            raise ProviderError("unexpected /models response shape") from None

    def ping(self) -> bool:
        try:
            self.list_models()
        except ProviderError:
            return False
        return True
