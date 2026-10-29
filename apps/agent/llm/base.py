"""Provider-agnostic LLM/VLM interface. Every provider implements `LLMProvider`.

API keys are held in memory only and must never be logged or echoed (NFR-11).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

ProviderName = Literal["ollama", "gemini", "openai", "anthropic"]


class ProviderError(Exception):
    """Raised when a provider call fails (network, auth, bad response)."""


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    provider: ProviderName
    model: str
    base_url: str | None = None  # ollama: http://localhost:11434; openai: any compatible URL
    api_key: str | None = field(default=None, repr=False)  # never printed
    timeout_s: float = 120.0


@runtime_checkable
class LLMProvider(Protocol):
    config: ProviderConfig

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        images: tuple[bytes, ...] = (),
        json_mode: bool = False,
    ) -> str:
        """Return the model's text reply. `images` are PNG bytes (VLM use)."""
        ...

    def list_models(self) -> list[str]:
        """Models available from this provider (best effort; may raise ProviderError)."""
        ...

    def ping(self) -> bool:
        """True if the provider is reachable and credentials work."""
        ...
