"""Anthropic backend (REST: /v1/messages, /v1/models)."""

from __future__ import annotations

from apps.agent.llm._http import b64, request_json
from apps.agent.llm.base import ProviderConfig, ProviderError

DEFAULT_BASE_URL = "https://api.anthropic.com"
_VERSION = "2023-06-01"


class AnthropicProvider:
    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self._base = (config.base_url or DEFAULT_BASE_URL).rstrip("/")

    def _headers(self) -> dict[str, str]:
        h = {"anthropic-version": _VERSION}
        if self.config.api_key:
            h["x-api-key"] = self.config.api_key
        return h

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        images: tuple[bytes, ...] = (),
        json_mode: bool = False,
    ) -> str:
        blocks: list[dict[str, object]] = [
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": b64(i)},
            }
            for i in images
        ]
        blocks.append({"type": "text", "text": prompt})
        sys_text = system or ""
        if json_mode:
            sys_text = (sys_text + "\n\nRespond with valid JSON only.").strip()
        body: dict[str, object] = {
            "model": self.config.model,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": blocks}],
        }
        if sys_text:
            body["system"] = sys_text
        data = request_json(
            "POST",
            f"{self._base}/v1/messages",
            headers=self._headers(),
            body=body,
            timeout=self.config.timeout_s,
        )
        try:
            return "".join(
                str(b.get("text", "")) for b in data["content"] if b.get("type") == "text"
            )
        except (KeyError, TypeError, AttributeError):
            raise ProviderError("unexpected Anthropic response shape") from None

    def list_models(self) -> list[str]:
        data = request_json(
            "GET",
            f"{self._base}/v1/models",
            headers=self._headers(),
            timeout=min(self.config.timeout_s, 15),
        )
        try:
            return [str(m["id"]) for m in data["data"]]
        except (KeyError, TypeError):
            raise ProviderError("unexpected Anthropic response shape") from None

    def ping(self) -> bool:
        try:
            self.list_models()
        except ProviderError:
            return False
        return True
