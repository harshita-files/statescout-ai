"""Gemini-backed implementation of `PerceptionPort` (M1-P1 / M1-P4).

Where `semantic_map.py` builds `S_current` from rules alone, this module asks
a VLM (Gemini by default; any `LLMProvider`) to *interpret* the
same capture (screenshot + AX tree) and merges its judgement onto the
deterministic element list rather than replacing it.

Why merge instead of trust the VLM outright
--------------------------------------------
VLMs are known to struggle specifically at negation: confirming an element is
genuinely *absent* rather than just unmentioned (this is the project's
highest-risk assumption per the handbook's risk register). So the ground
truth for *which elements exist* stays with the deterministic DOM/AX
pipeline, which cannot hallucinate an element into or out of existence.
Gemini's job here is narrower and safer: attach semantic tags/capabilities
to elements the deterministic pipeline already found, using image context
(color, prominence, icons) that DOM/AX text alone does not carry.

`audit()` and `complete_text()` do not touch Gemini's perceptual judgement at
all — `audit()` delegates straight to `negation.audit.audit()`, the
deterministic cross-check the whole design leans on.

state_id (ADR-001, decision 8 — open, C-3)
-------------------------------------------
`PerceptionPort.analyze()` is not passed a `state_id`, so this class cannot
mint the one `GraphPort.fingerprint()` will eventually assign to the same
capture. Rather than silently invent a hash that risks disagreeing with the
graph's fingerprint, `_PENDING_STATE_ID` is used as an explicit, greppable
placeholder and the orchestrator is expected to overwrite `state_id` once it
has fingerprinted the bundle. This is a stand-in for the real fix, not the
real fix — see the ADR for the two clean resolutions.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from apps.agent.contracts import (
    CaptureBundle,
    ExpectationSet,
    PerceptionError,
    Role,
    SemanticUIMap,
    UIElement,
    Violation,
)
from apps.agent.llm.base import LLMProvider, ProviderConfig, ProviderError
from apps.agent.negation.audit import audit as _deterministic_audit
from apps.agent.perception.semantic_map import build_semantic_map

__all__ = ["GeminiPerception", "VLMPerception"]

log = logging.getLogger(__name__)

#: See module docstring — replaced by the orchestrator once fingerprint()
#: has run. Deliberately not a plausible-looking id, so a forgotten overwrite
#: fails loudly instead of quietly joining to the wrong graph node.
_PENDING_STATE_ID = "PENDING-STATE-ID-SEE-ADR-001-C3"

#: Used only when no provider/model is injected and no env override is set.
_DEFAULT_MODEL = "gemini-2.5-flash"

_PROMPT_TEMPLATE = """You are assisting a UI auditing tool. Below is a screenshot of a web \
application state, plus a list of interactive elements already extracted \
deterministically from the page's DOM and accessibility tree.

For EACH element in the list, decide whether it exposes any of these \
capabilities, based on what you see in the screenshot (icon, color, \
placement, surrounding context) as well as its name:
{capability_hints}

Respond with ONLY a JSON array, one object per input element, in the same \
order, each shaped exactly like:
{{"index": <int>, "capabilities": ["<capability>", ...]}}

Use an empty list when nothing applies. Do not add elements, remove \
elements, or reorder them — the array length must match the input exactly.

Elements:
{element_list}
"""

# Same capability vocabulary semantic_map.py's deterministic path already
# uses, so the VLM's tags and the rule-based tags stay comparable.
_CAPABILITY_HINTS = (
    "delete-user (destructive action removing a user/account)",
    "admin-access (visible only to administrators)",
    "export-data (downloading or exporting data)",
)


class VLMPerception:
    """`PerceptionPort` backed by an injected `LLMProvider`, degrading gracefully.

    With no arguments, a Gemini provider is built lazily from the environment
    (`GEMINI_API_KEY`, optional `STATESCOUT_VLM_MODEL`), so importing this
    module never requires a key (`--fake` runs must not need one). Pass
    `provider=` to use any backend, or `model=` to pick a Gemini model.
    `client` (a google-genai client) is kept for test injection.
    """

    def __init__(
        self,
        *,
        provider: LLMProvider | None = None,
        model: str | None = None,
        client: Any = None,
    ) -> None:
        self._provider = provider
        self._model = model
        self._client = client

    def _get_provider(self) -> LLMProvider:
        if self._provider is not None:
            return self._provider
        from apps.agent.llm.gemini import GeminiProvider

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key and self._client is None:
            raise PerceptionError(
                "GEMINI_API_KEY is not set. Export it or add it to .env "
                "before running in --live mode."
            )
        model = self._model or os.environ.get("STATESCOUT_VLM_MODEL") or _DEFAULT_MODEL
        cfg = ProviderConfig(provider="gemini", model=model, api_key=api_key)
        self._provider = GeminiProvider(cfg, client=self._client)
        return self._provider

    def analyze(self, bundle: CaptureBundle, role: Role) -> SemanticUIMap:
        """Deterministic elements + Gemini's capability judgement, merged.

        Screenshot-less bundles (`screenshot_path is None`, decision 7 /
        action item C-2) skip the Gemini call entirely and fall through to
        the pure deterministic path — this is the "dom_only_smoke_test"
        mode Track B's run manifest tags separately, and it should never
        silently spend a rate-limit token for no visual signal.
        """
        semantic_map = build_semantic_map(bundle, role, _PENDING_STATE_ID)

        if bundle.screenshot_path is None:
            log.info("analyze(): no screenshot_path, skipping Gemini (DOM-only smoke test)")
            return semantic_map

        try:
            extra_capabilities = self._gemini_capabilities(
                bundle.screenshot_path, semantic_map.elements
            )
        except PerceptionError:
            raise
        except Exception as exc:  # pragma: no cover - defensive: never crash a crawl
            raise PerceptionError(f"Gemini analyze() call failed: {exc}") from exc

        if not extra_capabilities:
            return semantic_map

        merged = tuple(sorted(set(semantic_map.capabilities) | extra_capabilities))
        return SemanticUIMap(
            state_id=semantic_map.state_id,
            url=semantic_map.url,
            role=semantic_map.role,
            summary=semantic_map.summary,
            elements=semantic_map.elements,
            capabilities=merged,
        )

    def _gemini_capabilities(
        self, screenshot_path: str, elements: tuple[UIElement, ...]
    ) -> frozenset[str]:
        if not elements:
            return frozenset()

        provider = self._get_provider()
        element_list = "\n".join(
            f"{i}. role={e.role!r} name={e.name!r} tags={list(e.tags)}"
            for i, e in enumerate(elements)
        )
        prompt = _PROMPT_TEMPLATE.format(
            capability_hints="\n".join(f"- {hint}" for hint in _CAPABILITY_HINTS),
            element_list=element_list,
        )

        with open(screenshot_path, "rb") as fh:
            image_bytes = fh.read()

        try:
            text = provider.complete(prompt, images=(image_bytes,))
        except ProviderError as exc:
            raise PerceptionError(f"VLM call failed: {exc}") from exc

        return self._parse_capabilities(text)

    @staticmethod
    def _parse_capabilities(text: str) -> frozenset[str]:
        # Gemini sometimes wraps JSON in a ```json fence despite instructions
        # not to; strip it rather than fail the whole analyze() call over it.
        cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise PerceptionError(f"Gemini returned non-JSON output: {exc}") from exc

        capabilities: set[str] = set()
        if isinstance(parsed, list):
            for entry in parsed:
                if isinstance(entry, dict):
                    for cap in entry.get("capabilities", []):
                        if isinstance(cap, str):
                            capabilities.add(cap)
        return frozenset(capabilities)

    def audit(
        self,
        s_current: SemanticUIMap,
        expectations: ExpectationSet,
    ) -> tuple[Violation, ...]:
        """Delegates to the deterministic negation engine — no VLM call here.

        This is the design's whole point (handbook §3.1, §7): whether an
        element is present or absent is decided by DOM/AX ground truth, not
        by asking a model to notice an absence.
        """
        return _deterministic_audit(s_current, expectations)

    def complete_text(self, prompt: str) -> str:
        """Generic text completion, e.g. for Month 3 policy-parsing calls."""
        provider = self._get_provider()
        try:
            return provider.complete(prompt)
        except ProviderError as exc:
            raise PerceptionError(f"complete_text() call failed: {exc}") from exc


#: `deps.py` imports `VLMPerception` by exactly this name (see
#: `orchestrator/deps.py::live_ports`). `GeminiPerception` is kept as an
#: explicit alias so provider-swap code (NFR-08 — the InternVL drop-in) can
#: refer to "the Gemini one" by name without a comment explaining why the
#: class named after the interface is Gemini-specific today.
GeminiPerception = VLMPerception
