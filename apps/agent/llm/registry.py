"""Provider factory, env-driven defaults, and a UI-safe provider catalogue."""

from __future__ import annotations

import os
from typing import Any, Literal, cast, get_args

from apps.agent.llm import anthropic, gemini, ollama, openai_compat
from apps.agent.llm.anthropic import AnthropicProvider
from apps.agent.llm.base import LLMProvider, ProviderConfig, ProviderError, ProviderName
from apps.agent.llm.gemini import GeminiProvider
from apps.agent.llm.ollama import OllamaProvider
from apps.agent.llm.openai_compat import OpenAICompatProvider

_DEFAULT_MODELS: dict[str, dict[str, list[str]]] = {
    "ollama": {"llm": ["llama3.1", "qwen2.5"], "vlm": ["llava", "qwen2.5vl", "llama3.2-vision"]},
    "openai": {"llm": ["gpt-4o-mini", "gpt-4o"], "vlm": ["gpt-4o", "gpt-4o-mini"]},
    "anthropic": {
        "llm": ["claude-sonnet-4-5", "claude-haiku-4-5"],
        "vlm": ["claude-sonnet-4-5", "claude-haiku-4-5"],
    },
    "gemini": {
        "llm": ["gemini-2.5-flash", "gemini-2.5-pro"],
        "vlm": ["gemini-2.5-flash", "gemini-2.5-pro"],
    },
}
_BASE_URLS: dict[str, str] = {
    "ollama": ollama.DEFAULT_BASE_URL,
    "openai": openai_compat.DEFAULT_BASE_URL,
    "anthropic": anthropic.DEFAULT_BASE_URL,
    "gemini": gemini.DEFAULT_BASE_URL,
}
_KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
}
_DEFAULT_PROVIDER: ProviderName = "ollama"


def build_provider(cfg: ProviderConfig) -> LLMProvider:
    if cfg.provider == "ollama":
        return OllamaProvider(cfg)
    if cfg.provider == "openai":
        return OpenAICompatProvider(cfg)
    if cfg.provider == "anthropic":
        return AnthropicProvider(cfg)
    if cfg.provider == "gemini":
        return GeminiProvider(cfg)
    raise ProviderError(f"unknown provider: {cfg.provider!r}")


def default_config_from_env(kind: Literal["llm", "vlm"]) -> ProviderConfig:
    """Config from env. `kind` selects STATESCOUT_{LLM,VLM}_* variable names,
    falling back to the shared STATESCOUT_LLM_* names for the VLM."""
    prefix = f"STATESCOUT_{kind.upper()}"

    def env(suffix: str) -> str | None:
        return os.environ.get(f"{prefix}_{suffix}") or os.environ.get(f"STATESCOUT_LLM_{suffix}")

    name = (env("PROVIDER") or _DEFAULT_PROVIDER).lower()
    if name not in get_args(ProviderName):
        raise ProviderError(f"unknown provider: {name!r}")
    provider = cast(ProviderName, name)
    model = env("MODEL") or _DEFAULT_MODELS[provider][kind][0]
    base_url = env("BASE_URL")
    if base_url is None and provider == "ollama":
        base_url = os.environ.get("OLLAMA_HOST")
        if base_url and "://" not in base_url:
            base_url = f"http://{base_url}"
    api_key = os.environ.get(_KEY_ENV[provider]) if provider in _KEY_ENV else None
    return ProviderConfig(
        provider=provider, model=model, base_url=base_url, api_key=api_key or None
    )


def describe_providers() -> list[dict[str, Any]]:
    """UI-safe catalogue: never contains keys or key presence of any value."""
    return [
        {
            "name": name,
            "needs_key": name in _KEY_ENV,
            "default_base_url": _BASE_URLS[name],
            "default_models": {k: list(v) for k, v in _DEFAULT_MODELS[name].items()},
        }
        for name in get_args(ProviderName)
    ]
