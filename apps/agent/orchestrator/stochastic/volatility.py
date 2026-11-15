"""Region signatures and volatility learning for dynamic pages.

A DOM string and an AX tree are split into path-keyed regions, each with a digest of
its normalised content.  A :class:`VolatilityEstimator` watches repeated captures of
one state, learns which region paths keep changing, and yields a ``skeleton_id`` that
ignores them.  ``content_id`` is the exact hash of the raw capture.

Deterministic and stdlib-only.  Nothing here decides termination.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from html.parser import HTMLParser

DEFAULT_MAX_DEPTH = 3

_VOID = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "source",
        "track",
        "wbr",
    }
)
_SKIP_TEXT = frozenset({"script", "style"})
_KEEP_ATTRS = (
    "id",
    "role",
    "name",
    "type",
    "href",
    "aria-label",
    "alt",
    "placeholder",
    "for",
    # State-bearing attributes: a modal shown vs hidden, a box ticked vs not, a
    # control enabled vs disabled are different UI states and must never merge.
    "hidden",
    "disabled",
    "checked",
    "selected",
    "open",
    "readonly",
    "required",
    "value",
    "aria-hidden",
    "aria-disabled",
    "aria-checked",
    "aria-expanded",
    "aria-selected",
    "aria-pressed",
    "aria-current",
)
_AX_KEYS = (
    "name",
    "value",
    "description",
    "checked",
    "expanded",
    "disabled",
    "selected",
    "pressed",
    "hidden",
    "required",
    "readonly",
)

_REL_AGO = re.compile(
    r"\b(?:just now|yesterday|(?:an?|\d+)\s*(?:seconds?|secs?|minutes?|mins?|hours?|hrs?|"
    r"days?|weeks?|wks?|months?|years?|yrs?|s|m|h|d|w|mo|y)\s+ago|in\s+(?:an?|\d+)\s*"
    r"(?:seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|weeks?|months?|years?)\b)",
    re.IGNORECASE,
)
_ISO_TS = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?Z?")
_CLOCK = re.compile(r"\b\d{1,2}:\d{2}:\d{2}\b")
_WS = re.compile(r"\s+")
_SEP = re.compile(r"[-_]")


def _random_segment(seg: str) -> bool:
    if len(seg) < 4:
        return False
    if len(seg) >= 5 and any(c.isdigit() for c in seg):
        return True
    if seg.isdigit():
        return True
    uppers = sum(c.isupper() for c in seg)
    lowers = sum(c.islower() for c in seg)
    return len(seg) >= 5 and uppers >= 2 and lowers >= 2


def _is_random_token(token: str) -> bool:
    return any(_random_segment(seg) for seg in _SEP.split(token))


def normalise_text(text: str) -> str:
    """Collapse whitespace and replace relative / absolute timestamps with placeholders."""
    text = _ISO_TS.sub("<TS>", text)
    text = _CLOCK.sub("<TS>", text)
    text = _REL_AGO.sub("<REL>", text)
    return _WS.sub(" ", text).strip()


@dataclass(slots=True)
class _Node:
    tag: str
    attrs: tuple[tuple[str, str], ...] = ()
    text: list[str] = field(default_factory=list)
    children: list[_Node] = field(default_factory=list)


def _stable_attrs(raw: Iterable[tuple[str, str | None]]) -> tuple[tuple[str, str], ...]:
    out: list[tuple[str, str]] = []
    for key, value in raw:
        v = value or ""
        if key == "class":
            kept = " ".join(t for t in v.split() if not _is_random_token(t))
            if kept:
                out.append(("class", kept))
        elif key in _KEEP_ATTRS:
            if key == "id" and _is_random_token(v):
                continue
            if key == "href":
                v = re.split(r"[?#]", v, maxsplit=1)[0]
            out.append((key, v))
    return tuple(sorted(out))


class _DomBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("#root")
        self._stack: list[_Node] = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = _Node(tag, _stable_attrs(attrs))
        self._stack[-1].children.append(node)
        if tag not in _VOID:
            self._stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._stack[-1].children.append(_Node(tag, _stable_attrs(attrs)))

    def handle_endtag(self, tag: str) -> None:
        for i in range(len(self._stack) - 1, 0, -1):
            if self._stack[i].tag == tag:
                del self._stack[i:]
                return

    def handle_data(self, data: str) -> None:
        if self._stack[-1].tag not in _SKIP_TEXT:
            self._stack[-1].text.append(data)


def _parse_dom(dom: str) -> _Node:
    builder = _DomBuilder()
    builder.feed(dom)
    builder.close()
    root = builder.root
    # descend through <html> to <body> (or the lone wrapper) so paths start at body
    for child in root.children:
        if child.tag == "html":
            for sub in child.children:
                if sub.tag == "body":
                    return sub
            return child
        if child.tag == "body":
            return child
    return root


def _ax_node(value: object) -> _Node:
    if isinstance(value, dict):
        role = str(value.get("role", "node"))
        attrs = tuple(
            sorted(
                (k, normalise_text(str(value[k])))
                for k in _AX_KEYS
                if value.get(k) not in (None, "")
            )
        )
        node = _Node(role, attrs)
        kids = value.get("children")
        if isinstance(kids, list):
            node.children = [_ax_node(k) for k in kids]
        return node
    if isinstance(value, list):
        return _Node("list", children=[_ax_node(k) for k in value])
    return _Node("text", text=[str(value)])


def _parse_ax(ax: object) -> _Node:
    if isinstance(ax, str):
        try:
            return _ax_node(json.loads(ax))
        except ValueError:
            return _Node("text", text=[ax])
    return _ax_node(ax)


def _own(node: _Node) -> str:
    text = normalise_text(" ".join(node.text))
    return f"{node.tag}|{node.attrs!r}|{text}"


def _subtree(node: _Node) -> str:
    return f"({_own(node)}[{','.join(_subtree(c) for c in node.children)}])"


def _digest(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _walk(node: _Node, path: str, depth: int, max_depth: int, out: dict[str, str]) -> None:
    if depth >= max_depth or not node.children:
        out[path] = _digest(_subtree(node))
        return
    out[path] = _digest(_own(node))
    seen: Counter[str] = Counter()
    for child in node.children:
        idx = seen[child.tag]
        seen[child.tag] += 1
        _walk(child, f"{path}/{child.tag}[{idx}]", depth + 1, max_depth, out)


def split_regions(dom: str, ax: object, max_depth: int = DEFAULT_MAX_DEPTH) -> dict[str, str]:
    """Return ``{region_path: digest}`` for the DOM (``dom:`` keys) and AX tree (``ax:`` keys).

    Regions are tag-path keyed with sibling indices, down to ``max_depth``; deeper
    content is folded into its depth-``max_depth`` ancestor.  Randomised class names and
    ids, relative timestamps and whitespace are normalised away before hashing.
    """
    if max_depth < 1:
        raise ValueError("max_depth must be >= 1")
    out: dict[str, str] = {}
    dom_root = _parse_dom(dom)
    _walk(
        dom_root, "dom:body" if dom_root.tag == "body" else f"dom:{dom_root.tag}", 0, max_depth, out
    )
    ax_root = _parse_ax(ax)
    _walk(ax_root, f"ax:{ax_root.tag}", 0, max_depth, out)
    return out


def _text_of(node: _Node, raw: bool) -> str:
    parts = [" ".join(node.text), *(_text_of(c, raw) for c in node.children)]
    joined = " ".join(p for p in parts if p)
    return _WS.sub(" ", joined).strip() if raw else normalise_text(joined)


def _collect_texts(
    node: _Node, path: str, depth: int, max_depth: int, out: dict[str, str], raw: bool
) -> None:
    out[path] = _text_of(node, raw)
    if depth >= max_depth:
        return
    seen: Counter[str] = Counter()
    for child in node.children:
        idx = seen[child.tag]
        seen[child.tag] += 1
        _collect_texts(child, f"{path}/{child.tag}[{idx}]", depth + 1, max_depth, out, raw)


def region_texts(
    dom: str, max_depth: int = DEFAULT_MAX_DEPTH, *, raw: bool = False
) -> dict[str, str]:
    """Return ``{region_path: visible text}`` using the same paths as split_regions.

    ``raw=True`` keeps timestamps and relative times as they appear in the markup
    (only whitespace is collapsed): that is what ``dynamic.identity`` hashes, so it
    is the text a mask pattern has to match.
    """
    root = _parse_dom(dom)
    start = "dom:body" if root.tag == "body" else f"dom:{root.tag}"
    out: dict[str, str] = {}
    _collect_texts(root, start, 0, max_depth, out, raw)
    return out


def _ax_text(ax: object) -> str:
    if isinstance(ax, str):
        return ax
    return json.dumps(ax, sort_keys=True, separators=(",", ":"), default=str)


def content_id(dom: str, ax: object) -> str:
    """Exact identity of a raw capture (no normalisation, no masking)."""
    return hashlib.sha256(f"{dom}\x00{_ax_text(ax)}".encode()).hexdigest()


def _is_masked(path: str, volatile: frozenset[str]) -> bool:
    return any(path == v or path.startswith(v + "/") for v in volatile)


class VolatilityEstimator:
    """Learns which region paths of one state change between captures.

    Feed it repeated captures of the *same* state with :meth:`observe`.  Consecutive
    captures are compared; a path that changed, appeared or disappeared counts as a
    change for itself and for its parent (so appended feed items make the feed
    volatile).  A path is volatile once ``changes / comparisons >= threshold`` with at
    least ``min_observations`` captures seen.  Volatile paths and everything under
    them are masked out of :meth:`skeleton_id`.
    """

    __slots__ = ("_changes", "_comparisons", "_last", "_max_depth", "_min_obs", "_n", "_threshold")

    def __init__(
        self,
        threshold: float = 0.25,
        min_observations: int = 2,
        max_depth: int = DEFAULT_MAX_DEPTH,
    ) -> None:
        if not 0.0 < threshold <= 1.0:
            raise ValueError("threshold must be in (0, 1]")
        if min_observations < 2:
            raise ValueError("min_observations must be >= 2")
        if max_depth < 1:
            raise ValueError("max_depth must be >= 1")
        self._threshold = threshold
        self._min_obs = min_observations
        self._max_depth = max_depth
        self._changes: Counter[str] = Counter()
        self._comparisons = 0
        self._n = 0
        self._last: dict[str, str] | None = None

    @property
    def observations(self) -> int:
        return self._n

    def observe(self, dom: str, ax: object) -> None:
        sig = split_regions(dom, ax, self._max_depth)
        prev = self._last
        if prev is not None:
            self._comparisons += 1
            changed: set[str] = set()
            for path in prev.keys() | sig.keys():
                if prev.get(path) == sig.get(path):
                    continue
                changed.add(path)
                if (path in prev) != (path in sig) and "/" in path:
                    changed.add(path.rsplit("/", 1)[0])
            for path in changed:
                self._changes[path] += 1
        self._last = sig
        self._n += 1

    def change_rate(self, path: str) -> float:
        """Fraction of comparisons in which ``path`` changed (0.0 before any comparison)."""
        if self._comparisons == 0:
            return 0.0
        return self._changes[path] / self._comparisons

    def volatile_paths(self) -> frozenset[str]:
        if self._n < self._min_obs or self._comparisons == 0:
            return frozenset()
        # Roots (``dom:body``, ``ax:<role>``) are never masked: masking one would
        # collapse every state of the page into a single skeleton.
        return frozenset(
            p
            for p, c in self._changes.items()
            if "/" in p and c / self._comparisons >= self._threshold
        )

    def masked_signature(self, dom: str, ax: object) -> dict[str, str]:
        """Region signature with volatile regions removed."""
        volatile = self.volatile_paths()
        return {
            p: d
            for p, d in split_regions(dom, ax, self._max_depth).items()
            if not _is_masked(p, volatile)
        }

    def skeleton_id(self, dom: str, ax: object) -> str:
        """Identity that ignores volatile regions."""
        sig = self.masked_signature(dom, ax)
        return hashlib.sha256(
            "\n".join(f"{p}={d}" for p, d in sorted(sig.items())).encode()
        ).hexdigest()


@dataclass(frozen=True, slots=True)
class MergeReport:
    """Several distinct ``content_id`` values that collapsed to one ``skeleton_id``."""

    skeleton_id: str
    content_ids: tuple[str, ...]
    differing_paths: tuple[str, ...]


def merge_audit(
    estimator: VolatilityEstimator, captures: Sequence[tuple[str, object]]
) -> tuple[MergeReport, ...]:
    """Report every skeleton that merged more than one distinct content.

    ``differing_paths`` lists the region paths whose digest differs between the merged
    captures, so each merge can be inspected and, if wrong, the threshold tightened.
    """
    groups: dict[str, dict[str, dict[str, str]]] = {}
    for dom, ax in captures:
        sid = estimator.skeleton_id(dom, ax)
        groups.setdefault(sid, {})[content_id(dom, ax)] = split_regions(
            dom, ax, estimator._max_depth
        )
    reports: list[MergeReport] = []
    for sid, members in groups.items():
        if len(members) < 2:
            continue
        sigs = list(members.values())
        paths = sorted(
            p for p in set().union(*(s.keys() for s in sigs)) if len({s.get(p) for s in sigs}) > 1
        )
        reports.append(MergeReport(sid, tuple(sorted(members)), tuple(paths)))
    return tuple(sorted(reports, key=lambda r: r.skeleton_id))
