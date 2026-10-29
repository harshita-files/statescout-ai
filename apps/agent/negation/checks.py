"""Rule-kind checks beyond presence/absence: consistency, numeric, content, a11y.

Pure and deterministic. Each check takes a Rule (kind + params) and the observed
SemanticUIMaps (plus optional per-state page text) and yields ``Violation``s with
evidence. ``clause_type`` is fixed by the frozen contract; all of these are
"forbidden_present" style findings except required-content, which is
"required_absent".

Params by kind:
- consistency: ``subject`` (optional label, e.g. "AAPL"); without it every
  "<label> ... $N" pair is compared across states.
- numeric: ``min`` / ``max`` (default min=0), ``pattern`` (optional regex with a
  numeric group 1 restricting what is checked; default: any currency/quantity).
- content: ``forbid_pattern`` (regex, violation if found) and/or
  ``require_pattern`` (regex, violation if no state matches); ``flags`` ignored,
  matching is case-insensitive.
- a11y: flags visible interactive elements with an empty accessible name.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence

from apps.agent.audit_models import Rule
from apps.agent.contracts import ClauseType, Evidence, SemanticUIMap, Violation

_NUM = r"-?\$?\s?-?\d[\d,]*(?:\.\d+)?"
_INTERACTIVE = {"button", "link", "textbox", "input", "checkbox", "combobox", "img", "image"}


def state_text(smap: SemanticUIMap, texts: Mapping[str, str] | None = None) -> str:
    parts = [smap.summary, *(e.name for e in smap.elements)]
    if texts and smap.state_id in texts:
        parts.append(texts[smap.state_id])
    return "\n".join(p for p in parts if p)


def _to_float(raw: str) -> float | None:
    s = raw.replace("$", "").replace(",", "").replace(" ", "")
    try:
        return float(s)
    except ValueError:
        return None


def _snippet(text: str, start: int, end: int, pad: int = 30) -> str:
    return " ".join(text[max(0, start - pad) : end + pad].split())


def _v(
    rule: Rule,
    smap: SemanticUIMap,
    suffix: str,
    rationale: str,
    evidence: Evidence,
    clause: ClauseType = "forbidden_present",
) -> Violation:
    return Violation(
        violation_id=f"v-{smap.state_id}-{rule.rule_id}-{suffix}",
        state_id=smap.state_id,
        expectation_id=rule.rule_id,
        clause_type=clause,
        severity=rule.severity,
        rationale=rationale,
        evidence=evidence,
    )


def check_consistency(
    rule: Rule, maps: Sequence[SemanticUIMap], texts: Mapping[str, str] | None = None
) -> list[Violation]:
    subject = str(rule.params.get("subject") or "").strip()
    if subject:
        pair = re.compile(
            rf"(?P<label>{re.escape(subject)})\b[^\d\n$-]{{0,25}}\$?\s?(?P<num>{_NUM})", re.I
        )
    else:
        pair = re.compile(
            r"(?P<label>[A-Za-z][A-Za-z0-9 ]{0,24}?)\s*[:\-]?\s*(?P<num>\$\s?\d[\d,]*(?:\.\d+)?)"
        )
    seen: dict[str, tuple[float, str, str]] = {}  # label -> (value, state_id, snippet)
    out: list[Violation] = []
    reported: set[tuple[str, str]] = set()
    for smap in maps:
        text = state_text(smap, texts)
        for m in pair.finditer(text):
            label = " ".join(m.group("label").lower().split())
            val = _to_float(m.group("num"))
            if val is None or not label:
                continue
            snip = _snippet(text, m.start(), m.end())
            if label not in seen:
                seen[label] = (val, smap.state_id, snip)
            elif seen[label][0] != val and (label, smap.state_id) not in reported:
                reported.add((label, smap.state_id))
                first = seen[label]
                out.append(
                    _v(
                        rule,
                        smap,
                        re.sub(r"\W+", "-", label),
                        f"'{label}' shows {val:g} here but {first[0]:g} in state {first[1]}.",
                        Evidence(text=f"{snip} | vs ({first[1]}): {first[2]}"),
                    )
                )
    return out


def check_numeric(
    rule: Rule, maps: Sequence[SemanticUIMap], texts: Mapping[str, str] | None = None
) -> list[Violation]:
    lo = rule.params.get("min", 0)
    hi = rule.params.get("max")
    custom = rule.params.get("pattern")
    pat = (
        re.compile(str(custom), re.I)
        if custom
        else re.compile(
            r"(?<![\w.])(?:-\$?|\$-)\d[\d,]*(?:\.\d+)?|(?<![\w.-])\$?\d[\d,]*(?:\.\d+)?"
        )
    )
    out: list[Violation] = []
    for smap in maps:
        text = state_text(smap, texts)
        for i, m in enumerate(pat.finditer(text)):
            raw = m.group(1) if custom and m.re.groups else m.group(0)
            val = _to_float(raw)
            if val is None:
                continue
            bad = (lo is not None and val < float(lo)) or (hi is not None and val > float(hi))
            if bad:
                out.append(
                    _v(
                        rule,
                        smap,
                        f"n{i}",
                        f"Value {val:g} is outside the allowed range (min={lo}, max={hi}).",
                        Evidence(text=_snippet(text, m.start(), m.end())),
                    )
                )
    return out


def check_content(
    rule: Rule, maps: Sequence[SemanticUIMap], texts: Mapping[str, str] | None = None
) -> list[Violation]:
    out: list[Violation] = []
    forbid = rule.params.get("forbid_pattern")
    require = rule.params.get("require_pattern")
    if forbid:
        pat = re.compile(str(forbid), re.I)
        for smap in maps:
            text = state_text(smap, texts)
            m = pat.search(text)
            if m:
                out.append(
                    _v(
                        rule,
                        smap,
                        "forbid",
                        f"Forbidden content /{forbid}/ found.",
                        Evidence(text=_snippet(text, m.start(), m.end())),
                    )
                )
    if require and maps:
        pat = re.compile(str(require), re.I)
        if not any(pat.search(state_text(s, texts)) for s in maps):
            first = maps[0]
            out.append(
                _v(
                    rule,
                    first,
                    "require",
                    f"Required content /{require}/ never appears in any observed state.",
                    Evidence(),
                    "required_absent",
                )
            )
    return out


def check_a11y(
    rule: Rule, maps: Sequence[SemanticUIMap], texts: Mapping[str, str] | None = None
) -> list[Violation]:
    out: list[Violation] = []
    for smap in maps:
        for i, el in enumerate(smap.elements):
            if el.visible and el.role.lower() in _INTERACTIVE and not el.name.strip():
                out.append(
                    _v(
                        rule,
                        smap,
                        f"e{i}",
                        f"Visible {el.role} has no accessible name.",
                        Evidence(selector=el.selector, text=el.role),
                    )
                )
    return out


_CHECKS = {
    "consistency": check_consistency,
    "numeric": check_numeric,
    "content": check_content,
    "a11y": check_a11y,
}


def check_rules(
    rules: Iterable[Rule], maps: Sequence[SemanticUIMap], texts: Mapping[str, str] | None = None
) -> tuple[Violation, ...]:
    """Run every non presence/absence rule over all observed states."""
    out: list[Violation] = []
    for rule in rules:
        fn = _CHECKS.get(rule.kind)
        if fn is not None:
            out.extend(fn(rule, maps, texts))
    return tuple(out)
