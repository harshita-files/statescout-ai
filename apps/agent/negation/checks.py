"""Rule-kind checks beyond presence/absence: consistency, numeric, content, a11y.

Pure and deterministic. Each check takes a Rule (kind + params) and the observed
SemanticUIMaps (plus optional per-state page text) and yields ``Violation``s with
evidence. ``clause_type`` is fixed by the frozen contract; all of these are
"forbidden_present" style findings except required-content, which is
"required_absent".

Params by kind:
- consistency: ``subject`` (optional label, e.g. "AAPL"); without it every
  "<label> ... $N" pair is compared across states. ``mode`` selects a
  specialised comparison: ``sign`` (an absolute change and its percentage must
  share a sign), ``ticker`` (the price of one symbol must agree across views,
  ``tolerance`` relative, default 1%), ``sum`` (a "Total" must equal the sum of
  the row values on the same page, ``tolerance`` default 0.5%).
- numeric: ``min`` / ``max`` (default min=0), ``pattern`` (optional regex with a
  numeric group 1 restricting what is checked; default: any currency/quantity).
- content: ``forbid_pattern`` (regex, violation if found) and/or
  ``require_pattern`` (regex, violation if no state matches); ``flags`` ignored,
  matching is case-insensitive.
- a11y: flags visible interactive elements with an empty accessible name.
"""

from __future__ import annotations

import html as _html
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from statistics import median
from urllib.parse import parse_qs, urlparse

from apps.agent.audit_models import Rule
from apps.agent.contracts import ClauseType, Evidence, SemanticUIMap, Violation

_NUM = r"-?\$?\s?-?\d[\d,]*(?:\.\d+)?"
_INTERACTIVE = {"button", "link", "textbox", "input", "checkbox", "combobox", "img", "image"}


_BLOCK = re.compile(
    r"</?(?:p|div|section|article|main|header|footer|nav|aside|ul|ol|li|tr|table|thead|tbody|"
    r"h[1-6]|br|form|label|option|select|button)\b[^>]*>",
    re.I,
)


def visible_text(markup: str) -> str:
    """Readable text of an HTML document: one line per block, cells space-separated."""
    s = re.sub(r"(?is)<(script|style|noscript|head|svg)\b.*?</\1>|<!--.*?-->", " ", markup)
    s = re.sub(r"\s+", " ", s)  # source newlines are not line breaks
    s = _BLOCK.sub("\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = _html.unescape(s).replace("\xa0", " ")
    lines = (re.sub(r"[ \t]+", " ", ln).strip() for ln in s.splitlines())
    return "\n".join(ln for ln in lines if ln)


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


_CHANGE = re.compile(r"(?<![\w.])([+-]\s?\d[\d,]*(?:\.\d+)?)\s+\(?([+-]\s?\d[\d,]*(?:\.\d+)?)\s?%")


def _check_sign(
    rule: Rule, maps: Sequence[SemanticUIMap], texts: Mapping[str, str] | None
) -> list[Violation]:
    out: list[Violation] = []
    for smap in maps:
        text = state_text(smap, texts)
        done: set[str] = set()
        for m in _CHANGE.finditer(text):
            absolute, pct = _to_float(m.group(1)), _to_float(m.group(2))
            if not absolute or not pct or (absolute > 0) == (pct > 0):
                continue
            line_start = text.rfind("\n", 0, m.start()) + 1
            snip = " ".join(text[line_start : m.end()].split())[-70:]
            if snip in done:
                continue
            done.add(snip)
            out.append(
                _v(
                    rule,
                    smap,
                    f"sign{len(done)}",
                    f"Absolute change {m.group(1)} and percentage change {m.group(2)}% have "
                    "opposite signs.",
                    Evidence(text=snip),
                )
            )
    return out


_SYMBOL_PRICE = re.compile(r"\b([A-Z]{2,5})\b[ \t][A-Za-z.&' -]{0,30}?(\d{1,6}\.\d{2})\b")
_TICKET_PRICE = re.compile(r"price[^\d\n]{0,20}\n?\s*\$?(\d{1,6}\.\d{2})\b", re.I)


def _check_ticker(
    rule: Rule, maps: Sequence[SemanticUIMap], texts: Mapping[str, str] | None
) -> list[Violation]:
    """Within one page, every price shown for a symbol (ticker tape, table row, order
    ticket) must agree. Cross-page comparison is deliberately avoided: live prices
    legitimately move between captures."""
    tol = float(rule.params.get("tolerance", 0.01))
    out: list[Violation] = []
    for smap in maps:
        text = state_text(smap, texts)
        seen: dict[str, list[tuple[float, str, bool]]] = defaultdict(list)
        for m in _SYMBOL_PRICE.finditer(text):
            seen[m.group(1)].append(
                (float(m.group(2)), _snippet(text, m.start(), m.end(), 10), False)
            )
        sym = (parse_qs(urlparse(smap.url).query).get("symbol") or [""])[0].upper()
        t = _TICKET_PRICE.search(text)
        if sym and t:
            seen[sym].append((float(t.group(1)), _snippet(text, t.start(), t.end(), 10), True))
        for sym, obs in seen.items():
            ticket = [o for o in obs if o[2]]
            others = [o for o in obs if not o[2]]
            for val, snip, _ in ticket if others else ():
                ref = median(v for v, _, _ in others)
                if ref and abs(val - ref) / ref > tol:
                    out.append(
                        _v(
                            rule,
                            smap,
                            f"tk-{sym}",
                            f"The order ticket prices {sym} at {val:g} but the same page "
                            f"shows {ref:g} elsewhere.",
                            Evidence(text=f"{sym}: {snip}"),
                        )
                    )
            prices = [v for v, _, _ in others]
            spread = max(prices) / min(prices) - 1 if len(prices) > 1 and min(prices) > 0 else 0
            if not ticket and spread > tol:
                out.append(
                    _v(
                        rule,
                        smap,
                        f"tk-{sym}",
                        f"{sym} is shown with different prices on the same page "
                        f"({min(prices):g} and {max(prices):g}).",
                        Evidence(text=f"{sym}: {others[0][1]}"),
                    )
                )
    return out


_TOTAL = re.compile(r"\btotal\b[^\d\n]{0,25}\$?\s?(\d[\d,]*\.\d{2})\b", re.I)
_ROW_VALUE = re.compile(r"\b[A-Z]{2,5}\b[^\n]*?[+-]\d[\d,]*\.\d+%[ \t]+(\d[\d,]*\.\d{2})\b")


def _check_sum(
    rule: Rule, maps: Sequence[SemanticUIMap], texts: Mapping[str, str] | None
) -> list[Violation]:
    tol = float(rule.params.get("tolerance", 0.005))
    out: list[Violation] = []
    for smap in maps:
        text = state_text(smap, texts)
        total = _TOTAL.search(text)
        rows = [_to_float(m.group(1)) for m in _ROW_VALUE.finditer(text)]
        values = [v for v in rows if v is not None]
        amount = _to_float(total.group(1)) if total else None
        if amount is None or not values:
            continue
        got = sum(values)
        if abs(amount - got) > tol * max(abs(amount), 1.0):
            out.append(
                _v(
                    rule,
                    smap,
                    "sum",
                    f"Total shows {amount:,.2f} but the {len(values)} listed values add up to "
                    f"{got:,.2f} (difference {amount - got:,.2f}).",
                    Evidence(text=_snippet(text, total.start(), total.end(), 10)),  # type: ignore[union-attr]
                )
            )
    return out


_MODES = {"sign": _check_sign, "ticker": _check_ticker, "sum": _check_sum}


def check_consistency(
    rule: Rule, maps: Sequence[SemanticUIMap], texts: Mapping[str, str] | None = None
) -> list[Violation]:
    mode = str(rule.params.get("mode") or "")
    if mode in _MODES:
        return _MODES[mode](rule, maps, texts)
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


_CHANGE_TAIL = re.compile(r"\s+[+-]\s?\d[\d,]*(?:\.\d+)?\s?%")


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
            if not custom and (
                text[m.end() : m.end() + 1] == "%" or _CHANGE_TAIL.match(text, m.end())
            ):
                continue  # a signed price/percentage change is legitimate
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
