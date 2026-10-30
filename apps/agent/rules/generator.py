# ruff: noqa: E501
"""Auto-propose audit rules from observed pages (LLM when given, else heuristics)."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from apps.agent.audit_models import Rule
from apps.agent.contracts import SemanticUIMap
from apps.agent.llm.base import LLMProvider
from apps.agent.negation.checks import TRACKER_MARKUP, state_text
from apps.agent.rules.parser import _infer_kind

PageSummary = SemanticUIMap | str | Mapping[str, Any]
_KINDS = {"presence", "absence", "consistency", "numeric", "a11y", "content"}


def _is_consent(text: str) -> bool:
    return bool(re.search(r"\bconsent\b|\bcookie", text, re.I))


_SEVS = {"low", "medium", "high", "critical"}


def _page_text(p: PageSummary) -> str:
    if isinstance(p, str):
        return p
    if isinstance(p, SemanticUIMap):
        return (
            state_text(p)
            + "\n"
            + " ".join(p.capabilities)
            + " "
            + " ".join(t for e in p.elements for t in e.tags)
        )
    return " ".join(str(p.get(k, "")) for k in ("url", "title", "summary", "text"))


def _unlabeled(p: PageSummary) -> bool:
    return isinstance(p, SemanticUIMap) and any(
        e.visible
        and e.role.lower() in {"button", "link", "textbox", "input", "img", "image"}
        and not e.name.strip()
        for e in p.elements
    )


def _heuristic(pages: Sequence[PageSummary]) -> list[Rule]:
    blob = "\n".join(_page_text(p) for p in pages)
    low = blob.lower()
    out: list[tuple[str, str, str, dict[str, Any]]] = []  # text, kind, severity, params

    if re.search(r"log ?in|sign ?in|password", low):
        out.append(
            (
                "Login pages must not expose credentials, API keys or debug details in page content",
                "content",
                "high",
                {"forbid_pattern": r"(api[_-]?key|secret|password\s*[=:]\s*\S+|stack ?trace)"},
            )
        )
    out.append(
        (
            "Guests must not see admin controls",
            "absence",
            "critical",
            {"subject": "admin-access", "roles": ["guest"]},
        )
    )
    if re.search(r"\$\s?\d", blob):
        out.append(
            (
                "The same price or amount must be consistent across every view that shows it",
                "consistency",
                "high",
                {},
            )
        )
    if re.search(r"\d", blob):
        out.append(
            (
                "Numbers such as prices and quantities must never be negative",
                "numeric",
                "high",
                {"min": 0},
            )
        )
    out.append(
        (
            "The site must show a cookie or privacy consent banner",
            "content",
            "low",
            {"require_pattern": r"cookie|consent", "when_markup": TRACKER_MARKUP},
        )
    )
    out.append(
        (
            "Interactive controls must have an accessible label",
            "a11y",
            "medium" if any(_unlabeled(p) for p in pages) else "low",
            {},
        )
    )
    out.append(
        (
            "Pages must not show broken-link or error content",
            "content",
            "medium",
            {
                "forbid_pattern": r"\b404\b|page not found|something went wrong|internal server error"
            },
        )
    )
    return [
        Rule(f"gen-{i}", t, "generated", sev, kind, params)  # type: ignore[arg-type]
        for i, (t, kind, sev, params) in enumerate(out, 1)
    ]


_SYSTEM = (
    "You are a web QA auditor. Given summaries of a site's pages, propose audit rules. Reply with strict JSON only: "
    '{"rules":[{"text":"...","kind":"presence|absence|consistency|numeric|a11y|content",'
    '"severity":"low|medium|high|critical","params":{}}]}. '
    "Consider: login exposure, admin controls visible to guests, price/number consistency across views, "
    "missing consent banner, unlabeled controls, broken links, negative or invalid numbers. Max 10 rules. "
    "Each rule text must be a full sentence saying what must or must not be true, such as "
    "'Guests must not see the admin link', never a bare topic name."
)


_MODAL = re.compile(
    r"\b(must|should|shall|never|always|ensure|verify|check|require[sd]?|cannot|not|no)\b", re.I
)


def _is_policy_sentence(text: str) -> bool:
    """A rule states what must or must not hold. Topic labels ('login exposure') are not."""
    return len(text.split()) >= 3 and bool(_MODAL.search(text))


def _from_llm(pages: Sequence[PageSummary], llm: LLMProvider) -> list[Rule] | None:
    summary = "\n---\n".join(_page_text(p)[:1500] for p in pages[:20])
    prompt = f"Page summaries:\n{summary}"
    for _ in range(2):
        try:
            raw = llm.complete(prompt, system=_SYSTEM, json_mode=True)
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
            data = json.loads(raw)
            items = data["rules"] if isinstance(data, dict) else data
            rules: list[Rule] = []
            for i, it in enumerate(items, 1):
                if it["kind"] not in _KINDS or not str(it["text"]).strip():
                    raise ValueError("bad rule entry")
                sev = it.get("severity", "medium")
                params = it.get("params", {})
                if sev not in _SEVS or not isinstance(params, dict):
                    raise ValueError("bad severity/params")
                text = str(it["text"]).strip()
                if not params and it["kind"] in {"consistency", "numeric", "content"}:
                    inferred = _infer_kind(text)  # fill the params the check needs
                    if inferred and inferred[0] == it["kind"]:
                        params = dict(inferred[1])
                if it["kind"] == "content" and "require_pattern" in params and _is_consent(text):
                    params = {**params, "when_markup": TRACKER_MARKUP}
                rules.append(Rule(f"gen-{i}", text, "generated", sev, it["kind"], params))
            sentences = [r for r in rules if _is_policy_sentence(r.text)]
            if sentences:
                return [
                    Rule(f"gen-{n}", r.text, "generated", r.severity, r.kind, r.params)
                    for n, r in enumerate(sentences, 1)
                ]
            raise ValueError("rule texts must be full policy sentences, not topic labels")
        except Exception as exc:
            prompt = f"Page summaries:\n{summary}\nPrevious reply invalid ({exc}). Reply with valid JSON only."
    return None


def generate_rules(
    page_summaries: Sequence[PageSummary], llm: LLMProvider | None = None
) -> list[Rule]:
    """Propose rules (source='generated'); falls back to heuristics if the LLM fails."""
    if llm is not None:
        got = _from_llm(page_summaries, llm)
        if got is not None:
            return got
    return _heuristic(page_summaries)
