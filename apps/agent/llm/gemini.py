"""Gemini backend: google-genai SDK if installed (lazy), else REST."""

from __future__ import annotations

from typing import Any

from apps.agent.llm._http import b64, request_json
from apps.agent.llm.base import ProviderConfig, ProviderError

DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com"


class GeminiProvider:
    """`client` may be injected (a google-genai Client) to force the SDK path."""

    def __init__(self, config: ProviderConfig, *, client: Any = None) -> None:
        self.config = config
        self._base = (config.base_url or DEFAULT_BASE_URL).rstrip("/")
        self._client = client
        self._sdk_checked = client is not None

    def _sdk(self) -> Any:
        if not self._sdk_checked:
            self._sdk_checked = True
            try:
                from google import genai  # type: ignore[import-not-found,unused-ignore]

                if self.config.api_key:
                    self._client = genai.Client(api_key=self.config.api_key)
            except ImportError:
                self._client = None
        return self._client

    def _headers(self) -> dict[str, str]:
        return {"x-goog-api-key": self.config.api_key} if self.config.api_key else {}

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        images: tuple[bytes, ...] = (),
        json_mode: bool = False,
    ) -> str:
        client = self._sdk()
        if client is not None:
            return self._complete_sdk(client, prompt, system, images, json_mode)
        parts: list[dict[str, object]] = [
            {"inline_data": {"mime_type": "image/png", "data": b64(i)}} for i in images
        ]
        parts.append({"text": prompt})
        body: dict[str, object] = {"contents": [{"role": "user", "parts": parts}]}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if json_mode:
            body["generationConfig"] = {"responseMimeType": "application/json"}
        data = request_json(
            "POST",
            f"{self._base}/v1beta/models/{self.config.model}:generateContent",
            headers=self._headers(),
            body=body,
            timeout=self.config.timeout_s,
        )
        try:
            return "".join(
                str(p.get("text", "")) for p in data["candidates"][0]["content"]["parts"]
            )
        except (KeyError, IndexError, TypeError, AttributeError):
            raise ProviderError("unexpected Gemini response shape") from None

    def _complete_sdk(
        self,
        client: Any,
        prompt: str,
        system: str | None,
        images: tuple[bytes, ...],
        json_mode: bool,
    ) -> str:
        from google.genai import types  # type: ignore[import-not-found,unused-ignore]

        contents: list[Any] = [types.Part.from_bytes(data=i, mime_type="image/png") for i in images]
        contents.append(prompt)
        cfg = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json" if json_mode else None,
        )
        try:
            resp = client.models.generate_content(
                model=self.config.model, contents=contents, config=cfg
            )
        except Exception as exc:
            raise ProviderError(f"Gemini call failed: {type(exc).__name__}") from None
        return str(resp.text or "")

    def list_models(self) -> list[str]:
        data = request_json(
            "GET",
            f"{self._base}/v1beta/models",
            headers=self._headers(),
            timeout=min(self.config.timeout_s, 15),
        )
        try:
            return [str(m["name"]).removeprefix("models/") for m in data["models"]]
        except (KeyError, TypeError):
            raise ProviderError("unexpected Gemini response shape") from None

    def ping(self) -> bool:
        try:
            self.list_models()
        except ProviderError:
            return False
        return True
