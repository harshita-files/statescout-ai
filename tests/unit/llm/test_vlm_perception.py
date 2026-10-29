from __future__ import annotations

import pytest

from apps.agent.contracts import PerceptionError
from apps.agent.llm.base import ProviderConfig, ProviderError
from apps.agent.perception.gemini import VLMPerception


class Fake:
    config = ProviderConfig(provider="ollama", model="fake")

    def __init__(self, reply="pong", err=False):
        self.reply, self.err, self.calls = reply, err, []

    def complete(self, prompt, *, system=None, images=(), json_mode=False):
        self.calls.append(prompt)
        if self.err:
            raise ProviderError("boom")
        return self.reply

    def list_models(self):
        return []

    def ping(self):
        return True


def test_complete_text_uses_injected_provider():
    f = Fake()
    assert VLMPerception(provider=f).complete_text("hello") == "pong"
    assert f.calls == ["hello"]


def test_complete_text_wraps_provider_error():
    with pytest.raises(PerceptionError):
        VLMPerception(provider=Fake(err=True)).complete_text("x")


def test_parse_capabilities():
    assert VLMPerception._parse_capabilities('```json\n[{"capabilities":["a"]}]\n```') == {"a"}


def test_no_key_raises_perception_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(PerceptionError):
        VLMPerception().complete_text("x")
