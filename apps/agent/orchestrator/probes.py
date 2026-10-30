"""Post-crawl probes: observations a single visit to each page cannot make.

An intermittent defect (an endpoint that fails 1 load in 12) is invisible to a crawl that
visits each page once, however good the checks are. `resample` re-opens each distinct *kind*
of page a few times so the content checks see several captures, and a finding can say how
often the defect showed up.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace

from apps.agent.audit_models import Rule
from apps.agent.contracts import Evidence, SemanticUIMap, Violation
from apps.agent.negation.checks import check_rules, visible_text
from apps.agent.orchestrator.frontier_diversity import url_template

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Observation:
    """One re-capture of a page, with the background (fetch/XHR) requests it made."""

    url: str
    title: str
    dom: str
    calls: tuple[str, ...] = ()


def distinct_targets(pairs: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
    """One representative `(state_id, url)` per kind of page, in first-seen order."""
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for state_id, url in pairs:
        if not url.startswith(("http://", "https://")):
            continue
        template = url_template(url)
        if template not in seen:
            seen.add(template)
            out.append((state_id, url))
    return out


def _load(crawler: object, url: str) -> Observation:
    """A lean reload when the crawler offers one (DOM only), else a full `open`."""
    observe = getattr(crawler, "observe", None)
    if observe is not None:
        final_url, title, dom, calls = observe(url)
        return Observation(final_url, title, dom, tuple(calls))
    bundle = crawler.open(url)  # type: ignore[attr-defined]
    return Observation(bundle.url, bundle.title, bundle.dom)


def _specific(labels: dict[str, frozenset[str]]) -> set[str]:
    """Targets making a background request that few other kinds of page make.

    A request every page makes (a shared poll) says nothing about one page; one only a few
    kinds make is where that page's own, possibly flaky, backend lives.
    """
    count = {c for calls in labels.values() for c in calls}
    rare = {
        c for c in count if sum(c in calls for calls in labels.values()) <= max(1, len(labels) // 3)
    }
    return {sid for sid, calls in labels.items() if calls & rare}


def resample(
    crawler: object,
    targets: Sequence[tuple[str, str]],
    n: int,
    *,
    dynamic_n: int | None = None,
    cap: int = 40,
    should_stop: Callable[[], bool] | None = None,
) -> dict[str, list[Observation]]:
    """Re-open every target `n` times, and pages with requests of their own `dynamic_n` times.

    Loads are interleaved round-robin and at most `cap` in all. A failed reload is skipped,
    not fatal. Stops as soon as `should_stop()` is true. Intermittent defects need samples
    in proportion to 1/p, so the budget goes where the page's own backend is.
    """
    out: dict[str, list[Observation]] = {state_id: [] for state_id, _ in targets}
    quota = {state_id: n for state_id, _ in targets}
    tried = dict.fromkeys(out, 0)
    labels: dict[str, frozenset[str]] = {}
    loads = 0
    sized = dynamic_n is None
    while True:
        pending = [(sid, url) for sid, url in targets if tried[sid] < quota[sid]]
        if not pending:
            return out
        for sid, url in pending:
            if loads >= cap or (should_stop is not None and should_stop()):
                return out
            loads += 1
            tried[sid] += 1
            try:
                ob = _load(crawler, url)
            except Exception as exc:
                log.warning("resample: reload of %s failed (%s)", url, type(exc).__name__)
                continue
            out[sid].append(ob)
            labels.setdefault(sid, frozenset(ob.calls))
        if not sized and all(t >= 1 for t in tried.values()):
            sized = True  # after one full round we know which pages have requests of their own
            for sid in _specific(labels):
                quota[sid] = max(quota[sid], dynamic_n or 0)


def resample_violations(
    rules: Iterable[Rule],
    maps: Sequence[SemanticUIMap],
    observed: dict[str, list[Observation]],
) -> tuple[list[Violation], dict[str, float]]:
    """Run the forbid/numeric checks over every re-capture.

    Returns one violation per distinct problem per page (attached to the page's original
    state) and its confidence: the share of re-observations in which it appeared.
    """
    checkable = [
        r
        for r in rules
        if (r.kind == "content" and r.params.get("forbid_pattern")) or r.kind == "numeric"
    ]
    by_id = {m.state_id: m for m in maps}
    violations: list[Violation] = []
    confidence: dict[str, float] = {}
    if not checkable:
        return violations, confidence
    for state_id, observations in observed.items():
        base = by_id.get(state_id)
        if base is None or not observations:
            continue
        pseudo, texts, markup = [], {}, {}
        for k, ob in enumerate(observations):
            sid = f"{state_id}~r{k}"
            pseudo.append(replace(base, state_id=sid, url=ob.url, summary="", elements=()))
            texts[sid] = f"{ob.title}\n{visible_text(ob.dom)}"
            markup[sid] = ob.dom
        groups: dict[tuple[str, str], list[Violation]] = {}
        for v in check_rules(checkable, pseudo, texts, markup):
            groups.setdefault((v.expectation_id, v.evidence.text or v.rationale), []).append(v)
        for (rule_id, _), hits in groups.items():
            first = hits[0]
            vid = f"v-{state_id}-{rule_id}-resample-{abs(hash(first.evidence.text)) % 10**6}"
            n = len(observations)
            violations.append(
                replace(
                    first,
                    state_id=state_id,
                    violation_id=vid,
                    rationale=(
                        f"{first.rationale} Seen in {len(hits)} of {n} "
                        "re-observations of this page."
                    ),
                )
            )
            confidence[vid] = len(hits) / n
    return violations, confidence


_TIMESTAMP = re.compile(
    r"(?i)\b(?:last\s+updated|updated(?:\s+at)?|as\s+of)\b\W{0,4}"
    r"(\d{4}-\d\d-\d\d[T ]\d\d:\d\d(?::\d\d)?|\d{1,2}:\d\d(?::\d\d)?)"
)
_VALUE = re.compile(r"\b\d{1,6}\.\d{2}\b")
#: Readings needed before "the timestamp did not move" means anything.
_MIN_LIVENESS_READINGS = 3


def liveness_violations(
    rules: Iterable[Rule],
    maps: Sequence[SemanticUIMap],
    observed: dict[str, list[Observation]],
    base_texts: dict[str, str] | None = None,
) -> list[Violation]:
    """A 'last updated' stamp must move when the data it labels moves.

    Readings of one page are ordered in time (the crawl's own capture first, then the
    reloads). If several readings share one timestamp yet show different values, the stamp
    is stale: the data is being refreshed behind an unchanged "last updated".
    """
    live_rules = [r for r in rules if r.kind == "liveness"]
    by_id = {m.state_id: m for m in maps}
    out: list[Violation] = []
    for rule in live_rules:
        for state_id, observations in observed.items():
            smap = by_id.get(state_id)
            if smap is None:
                continue
            texts = [t for t in [(base_texts or {}).get(state_id)] if t]
            texts += [visible_text(ob.dom) for ob in observations]
            groups: dict[str, list[tuple[str, ...]]] = {}
            for text in texts:
                m = _TIMESTAMP.search(text)
                if m:
                    values = tuple(sorted(set(_VALUE.findall(text.replace(m.group(1), " ")))))
                    groups.setdefault(m.group(1), []).append(values)
            for stamp, readings in groups.items():
                distinct = set(readings)
                if len(readings) >= _MIN_LIVENESS_READINGS and len(distinct) > 1:
                    a, b = sorted(distinct)[0], sorted(distinct)[-1]
                    out.append(
                        Violation(
                            violation_id=f"v-{state_id}-{rule.rule_id}-stale",
                            state_id=state_id,
                            expectation_id=rule.rule_id,
                            clause_type="forbidden_present",
                            severity=rule.severity,
                            rationale=(
                                f"'Last updated' still reads {stamp} across {len(readings)} "
                                "readings while the displayed values changed."
                            ),
                            evidence=Evidence(
                                text=(
                                    f"Last updated: {stamp} unchanged over {len(readings)} "
                                    f"readings; values moved, e.g. {', '.join(a[:3])} -> "
                                    f"{', '.join(b[:3])}"
                                )
                            ),
                        )
                    )
    return out
