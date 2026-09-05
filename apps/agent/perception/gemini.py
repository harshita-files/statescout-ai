"""Gemini-backed implementation of `PerceptionPort` (M1-P1 / M1-P4).

Where `semantic_map.py` builds `S_current` from rules alone, this module asks
Gemini 2.5 Flash to *interpret* the same capture — screenshot + AX tree — and
merges its judgement onto the deterministic element list rather than
replacing it.

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
from collections.abc import Sequence

from google import genai
from google.genai import types

from apps.agent.contracts import (
    CaptureBundle,
    ExpectationSet,
    PerceptionError,
    Role,
    SemanticUIMap,
    UIElement,
    Violation,
)
from apps.agent.negation.audit import audit as _deterministic_audit
from apps.agent.perception.semantic_map import build_semantic_map

__all__ = ["GeminiPerception", "VLMPerception"]

log = logging.getLogger(__name__)

#: See module docstring — replaced by the orchestrator once fingerprint()
#: has run. Deliberately not a plausible-looking id, so a forgotten overwrite
#: fails loudly instead of quietly joining to the wrong graph node.
_PENDING_STATE_ID = "PENDING-STATE-ID-SEE-ADR-001-C3"

_MODEL = "gemini-3.6-flash"

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
# uses, so Gemini's tags and the rule-based tags stay comparable.
_CAPABILITY_HINTS = (
    "delete-user (destructive action removing a user/account)",
    "admin-access (visible only to administrators)",
    "export-data (downloading or exporting data)",
)


class VLMPerception:
    """`PerceptionPort` backed by Gemini 2.5 Flash, degrading gracefully.

    `client` is injectable for tests; production code leaves it `None` and
    lets the client read `GEMINI_API_KEY` from the environment on first use,
    so importing this module never requires a key to be present (`--fake`
    runs must not need one).
    """

    def __init__(self, *, client: genai.Client | None = None) -> None:
        self._client = client
        self._client_error: str | None = None

    def _get_client(self) -> genai.Client:
        if self._client is not None:
            return self._client
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise PerceptionError(
                "GEMINI_API_KEY is not set. Export it or add it to .env "
                "before running in --live mode."
            )
        self._client = genai.Client(api_key=api_key)
        return self._client

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

        client = self._get_client()
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

        contents: Sequence[types.Part | str] = [
            types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
            prompt,
        ]
        response = client.models.generate_content(model=_MODEL, contents=contents)

        return self._parse_capabilities(response.text or "")

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
        client = self._get_client()
        try:
            response = client.models.generate_content(model=_MODEL, contents=prompt)
        except Exception as exc:  # pragma: no cover - network/SDK failure
            raise PerceptionError(f"Gemini complete_text() call failed: {exc}") from exc
        return response.text or ""


#: `deps.py` imports `VLMPerception` by exactly this name (see
#: `orchestrator/deps.py::live_ports`). `GeminiPerception` is kept as an
#: explicit alias so provider-swap code (NFR-08 — the InternVL drop-in) can
#: refer to "the Gemini one" by name without a comment explaining why the
#: class named after the interface is Gemini-specific today.
GeminiPerception = VLMPerception
