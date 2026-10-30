# ruff: noqa: E501
"""Natural-language rules -> ExpectationSet + structured Rule hints.

LLM path asks for strict JSON, validates, retries once, then falls back to the
deterministic heuristic parser (also used directly when ``llm`` is None).
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from typing import Any

from apps.agent.audit_models import Rule
from apps.agent.contracts import ExpectationNode, ExpectationSet
from apps.agent.llm.base import LLMProvider

_KINDS = {"presence", "absence", "consistency", "numeric", "a11y", "content"}
_SEVERITIES = {"low", "medium", "high", "critical"}
_ROLES = ("guest", "anonymous", "user", "admin", "customer", "member", "visitor")

# Phrase -> canonical capability/tag used by the semantic-map builder.
_SYNONYMS = {
    "admin": "admin-access",
    "admin link": "admin-access",
    "admin panel": "admin-access",
    "admin page": "admin-access",
    "admin controls": "admin-access",
    "delete": "delete-user",
    "delete button": "delete-user",
    "debug": "debug-access",
    "debug panel": "debug-access",
    "export": "export-data",
    "export button": "export-data",
    "logout": "logout",
    "logout button": "logout",
    "logout link": "logout",
    "login button": "login",
    "log out": "logout",
    "login": "login",
    "log in": "login",
    "login form": "login",
    "sign in": "login",
}

_NEG = r"(?:must\s+not|should\s+not|shall\s+not|cannot|can\s?not|can't|mustn't|shouldn't|must\s+never|should\s+never|never)"
_VERB = r"(?:see|view|show|display|expose|reveal|access|contain|include|have|render|list)"
_POS = r"(?:must|should|shall|needs?\s+to)\s+(?:always\s+)?(?:have|show|display|contain|include|see|expose|render|offer)"

_ROLE_NEG = re.compile(
    rf"^(?:an?\s+|the\s+)?(?P<role>[\w-]+?)s?\s+{_NEG}\s+(?:be\s+able\s+to\s+)?{_VERB}\s+(?P<subj>.+)$",
    re.I,
)
_NEG_SHOW = re.compile(
    rf"^(?P<ctx>.*?)\b{_NEG}\s+(?:be\s+able\s+to\s+)?{_VERB}\s+(?P<subj>.+)$", re.I
)
_NEG_SUBJ_VERB = re.compile(
    rf"^(?:the\s+)?(?P<subj>.+?)\s+{_NEG}\s+(?:be\s+)?(?:visible|shown|displayed|present|exposed|accessible)"
    r"(?:\s+to\s+(?:an?\s+|the\s+)?(?P<role>[\w-]+?)s?)?$",
    re.I,
)
_POS_SHOW = re.compile(rf"^(?P<ctx>.*?)\b{_POS}\s+(?P<subj>.+)$", re.I)
_ROLE_POS = re.compile(rf"^(?:an?\s+|the\s+)?(?P<role>[\w-]+?)s?\s+{_POS}\s+(?P<subj>.+)$", re.I)


def _clean_subject(raw: str) -> str:
    s = raw.strip().strip(".!;:\"'`").strip()
    s = re.sub(
        r"\s+(?:to|for|on|in)\s+(?:any\s+|all\s+)?(?:the\s+)?(?:guests?|users?|visitors?|anonymous).*$",
        "",
        s,
        flags=re.I,
    )
    s = re.sub(r"\s+(?:on|in|at)\s+(?:any|every|all|the)\s+.*$", "", s, flags=re.I)
    s = re.sub(r"^(?:any|an?|the|its|their|some)\s+", "", s, flags=re.I).strip()
    key = re.sub(r"\s+", " ", s.lower())
    if key in _SYNONYMS:
        return _SYNONYMS[key]
    if len(key) > 24:  # long compound subjects: map the capability they name
        if re.search(r"\badmin\b", key):
            return "admin-access"
        if re.search(r"\bdelete\b", key):
            return "delete-user"
    return re.sub(r"[^a-z0-9]+", "-", key).strip("-")


def _role_of(token: str | None) -> tuple[str, ...]:
    if not token:
        return ()
    t = token.lower().strip()
    if t in {"anonymous", "visitor", "guest"}:
        return ("guest",)
    if t in _ROLES:
        return (t,)
    return ()


def _ctx_roles(ctx: str) -> tuple[str, ...]:
    found = [r for r in re.findall(r"[a-z]+", ctx.lower()) if r in _ROLES]
    return _role_of(found[0]) if found else ()


_NAN_PATTERN = r"\bNaN\b|\bundefined\b|\bnull\b"
_NOT_FOUND_PATTERN = r"\b404\b|page not found"
_CONSENT_PATTERN = r"cookie|consent"


def _infer_kind(text: str) -> tuple[str, dict[str, Any]] | None:
    """Map a sentence onto a structured check kind plus the params the check needs."""
    t = text.lower()
    if re.search(r"\bnan\b|\bundefined\b|\bnull\b", t):
        return "content", {"forbid_pattern": _NAN_PATTERN}
    if re.search(r"\bsum of\b|\badd(?:s|ed)? up\b", t) and re.search(r"\btotal\b", t):
        return "consistency", {"mode": "sum"}
    if re.search(r"\bsign of\b", t) and re.search(r"%|percent", t):
        return "consistency", {"mode": "sign"}
    if re.search(r"\b(same|consistent|consistency|match|equal|differ)\b", t) and re.search(
        r"\b(ticker|stock|symbol)s?\b", t
    ):
        return "consistency", {"mode": "ticker"}
    if re.search(r"\b(same|consistent|consistency|match|differ)\b", t) and re.search(
        r"\b(price|total|amount|value|number|count|balance|view|page|across)\b", t
    ):
        return "consistency", {}
    if re.search(r"\bbroken (link|image)|\b404\b|lead to an existing page", t):
        return "content", {"forbid_pattern": _NOT_FOUND_PATTERN}
    if re.search(r"\bconsent\b|\bcookie\b|\bbanner\b|tracking", t):
        return "content", {"require_pattern": _CONSENT_PATTERN}
    if re.search(
        r"\bnegative\b|\binvalid (number|quantity|price)|\bmust be (positive|non-negative)", t
    ):
        return "numeric", {"min": 0}
    if re.search(r"\b(label|alt text|aria|a11y|unlabeled)\b|\baccessib", t):
        return "a11y", {}
    return None


def _heuristic(rule: Rule, role: str) -> tuple[Rule, ExpectationNode | None, bool]:
    """Return (enriched rule, expectation, is_forbidden)."""
    text = " ".join(rule.text.split())
    body = text.rstrip(".!")
    inferred = _infer_kind(body)
    if inferred is not None:
        kind, defaults = inferred
        return (
            Rule(
                rule.rule_id,
                rule.text,
                rule.source,
                rule.severity,
                kind,
                {**defaults, **rule.params},
            ),
            None,
            False,
        )

    polarity: str | None = None
    subj: str | None = None
    roles: tuple[str, ...] = ()
    for pat, pol in (
        (_NEG_SUBJ_VERB, "neg"),
        (_ROLE_NEG, "neg"),
        (_NEG_SHOW, "neg"),
        (_ROLE_POS, "pos"),
        (_POS_SHOW, "pos"),
    ):
        m = pat.match(body)
        if not m:
            continue
        gd = m.groupdict()
        if gd.get("role"):
            roles = _role_of(gd["role"])
            if not roles:
                continue  # "role" group captured junk; try next pattern
        elif gd.get("ctx"):
            roles = _ctx_roles(gd["ctx"])
        polarity, subj = pol, gd.get("subj")
        break
    if polarity is None or not subj:
        return rule, None, False
    subject = _clean_subject(subj)
    if not subject:
        return rule, None, False
    forbidden = polarity == "neg"
    node = ExpectationNode(
        expectation_id=rule.rule_id,
        polarity="must_not_exist" if forbidden else "must_exist",
        subject=subject,
        roles=roles,
        source_text=rule.text,
    )
    params = {**rule.params, "subject": subject, "roles": list(roles)}
    new = Rule(
        rule.rule_id,
        rule.text,
        rule.source,
        rule.severity,
        "absence" if forbidden else "presence",
        params,
    )
    return new, node, forbidden


_SYSTEM = (
    "You convert a QA policy sentence into strict JSON. Reply with JSON only, shape: "
    '{"kind":"presence|absence|consistency|numeric|a11y|content",'
    '"subject":"short-hyphenated-ui-element-or-capability",'
    '"roles":["guest"],"severity":"low|medium|high|critical","params":{}}. '
    "Use kind=absence when something must NOT be visible, presence when it must be. "
    "roles is empty when the rule applies to everyone."
)


def _extract_json(raw: str) -> dict[str, Any]:
    s = raw.strip()
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s)
    data = json.loads(s)
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    return data


_PLACEHOLDER_SUBJECT = "short-hyphenated-ui-element-or-capability"  # the schema example in _SYSTEM


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _subject_is_plausible(subject: str, text: str) -> bool:
    """Small models copy the schema example or invent a subject. Accept the subject if it is
    not the placeholder and either shares a word with the sentence (admin-link <- "the admin
    link") or is a canonical name the perception layer knows (logout <- "sign out")."""
    from apps.agent.perception.semantic_map import _CAPABILITY_RULES, _TAG_RULES

    subject = subject.strip()
    if subject == _PLACEHOLDER_SUBJECT:
        return False
    known = {name for name, _ in (*_CAPABILITY_RULES, *_TAG_RULES)}
    return subject.lower() in known or bool(_words(subject) & _words(text))


def _validate(data: dict[str, Any], text: str = "") -> dict[str, Any]:
    kind = data.get("kind")
    if kind not in _KINDS:
        raise ValueError(f"kind must be one of {sorted(_KINDS)}")
    sev = data.get("severity", "high")
    if sev not in _SEVERITIES:
        raise ValueError("invalid severity")
    roles = data.get("roles", [])
    if not isinstance(roles, list) or not all(isinstance(r, str) for r in roles):
        raise ValueError("roles must be a list of strings")
    params = data.get("params", {})
    if not isinstance(params, dict):
        raise ValueError("params must be an object")
    subject = data.get("subject", "")
    if kind in {"presence", "absence"} and (not isinstance(subject, str) or not subject.strip()):
        raise ValueError("subject required for presence/absence")
    if kind in {"presence", "absence"} and text and not _subject_is_plausible(str(subject), text):
        raise ValueError(f"subject {subject!r} is not about the policy sentence")
    return {
        "kind": kind,
        "severity": sev,
        "roles": roles,
        "params": params,
        "subject": str(subject).strip(),
    }


def _via_llm(rule: Rule, llm: LLMProvider) -> tuple[Rule, ExpectationNode | None, bool] | None:
    prompt = f"Policy sentence: {rule.text!r}"
    for _ in range(2):
        try:
            raw = llm.complete(prompt, system=_SYSTEM, json_mode=True)
            v = _validate(_extract_json(raw), rule.text)
        except Exception as exc:
            prompt = f"Policy sentence: {rule.text!r}\nYour previous reply was invalid ({exc}). Reply with valid JSON only."
            continue
        kind = v["kind"]
        subject = _clean_subject(v["subject"]) if v["subject"] else ""
        roles = tuple(r.lower() for r in v["roles"])
        params = {**rule.params, **v["params"]}
        if subject:
            params["subject"] = subject
        new = Rule(rule.rule_id, rule.text, rule.source, v["severity"], kind, params)
        if kind in {"presence", "absence"}:
            forbidden = kind == "absence"
            node = ExpectationNode(
                expectation_id=rule.rule_id,
                polarity="must_not_exist" if forbidden else "must_exist",
                subject=subject,
                roles=roles,
                source_text=rule.text,
            )
            return new, node, forbidden
        return new, None, False
    return None


def parse_rules(
    texts_or_rules: Sequence[str | Rule],
    llm: LLMProvider | None = None,
    role: str = "guest",
) -> tuple[ExpectationSet, list[Rule]]:
    """Convert NL rules into an ExpectationSet and structured Rules.

    ``role`` is the default role for clauses that name none... except that an
    unscoped clause is kept role-agnostic (empty roles) so it applies everywhere.
    """
    forbidden: list[ExpectationNode] = []
    required: list[ExpectationNode] = []
    rules: list[Rule] = []
    for i, item in enumerate(texts_or_rules, start=1):
        rule = item if isinstance(item, Rule) else Rule(rule_id=f"rule-{i}", text=item)
        if not rule.text.strip():
            continue
        res = _via_llm(rule, llm) if llm is not None else None
        if res is None:
            res = _heuristic(rule, role)
        new, node, is_forb = res
        rules.append(new)
        if node is not None:
            (forbidden if is_forb else required).append(node)
    return ExpectationSet(tuple(forbidden), tuple(required)), rules
