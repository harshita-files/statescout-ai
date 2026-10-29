"""Network-endpoint normalisation and per-(state class, action) endpoint counts.

Raw URLs are useless as statistics (`/api/users/41`, `/api/users/42`, ... are
one endpoint) and dangerous in logs (query values and path tokens are where
credentials live). `normalise_endpoint` collapses the first and removes the
second: scheme, host, userinfo, fragment, and every query *value* are dropped,
and identifier-like path segments become placeholders.

Pure functions and plain data only. Nothing here performs I/O, logs, or decides
whether exploration continues.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit

__all__ = ["EndpointCounter", "NetworkCall", "normalise_endpoint"]

_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[T ]\d{2}[:\-]?\d{2}(?:[:\-]?\d{2})?[0-9:.Zz+\-]*)?$")
_NUMERIC = re.compile(r"^\d+$")
_HEX = re.compile(r"^[0-9a-f]{16,}$", re.I)
_UNSAFE = re.compile(r"[^A-Za-z0-9_.:-]")
_PLACEHOLDERS = frozenset({"{id}", "{uuid}", "{date}", "{hex}", "{token}"})
_OPAQUE_SCHEMES = frozenset({"data", "blob", "javascript", "about"})

#: A segment this long that mixes letters and digits is an opaque token (session id,
#: JWT fragment, base64 blob); so is a long run of letters with no separator, since
#: real route words are shorter. Over-templating is the safe direction here.
_MIXED_TOKEN_MIN_LEN = 12
_ALPHA_TOKEN_MIN_LEN = 20


def _placeholder(segment: str) -> str:
    """Map one decoded path segment to itself or a placeholder."""
    if segment in _PLACEHOLDERS:
        return segment
    if _UUID.match(segment):
        return "{uuid}"
    if _DATE.match(segment):
        return "{date}"
    if _NUMERIC.match(segment):
        return "{id}"
    if _HEX.match(segment):
        return "{hex}"
    has_digit = any(ch.isdigit() for ch in segment)
    has_alpha = any(ch.isalpha() for ch in segment)
    if len(segment) >= _MIXED_TOKEN_MIN_LEN and has_digit and has_alpha:
        return "{token}"
    if len(segment) >= _ALPHA_TOKEN_MIN_LEN and segment.isalpha():
        return "{token}"
    return _UNSAFE.sub("_", segment)


def normalise_endpoint(method: str, url: str) -> str:
    """Return `'METHOD /path/{id}'` for a request, safe to store and to log.

    * Method is upper-cased; path case is preserved (paths are case-sensitive).
    * Host, scheme, port, userinfo, **query (keys and values), fragment and path
      parameters (`;jsessionid=...`)** are all dropped. Credentials live in those
      places, and the runner only accepts `METHOD /path` labels anyway.
    * `data:`, `blob:` and `javascript:` URLs collapse to `/<scheme>` with no payload.
    * Segments are percent-decoded, then numeric ids, UUIDs, ISO dates, hex strings
      and long tokens become `{id}`, `{uuid}`, `{date}`, `{hex}` and `{token}`; any
      character outside `[A-Za-z0-9_.:-]` becomes `_`. Empty segments vanish.
    """
    verb = method.strip().upper()
    parts = urlsplit(url.strip())
    if parts.scheme.lower() in _OPAQUE_SCHEMES:
        return f"{verb} /{parts.scheme.lower()}"
    segments = [
        _placeholder(unquote(s).split(";", 1)[0]) for s in parts.path.split("/") if s.split(";")[0]
    ]
    return f"{verb} /" + "/".join(segments)


@dataclass(frozen=True, slots=True)
class NetworkCall:
    """One observed request. The URL may be raw; the counter normalises it."""

    method: str
    url: str
    status: int


class EndpointCounter:
    """`(state_class, action_id) -> normalised endpoint -> count`.

    Mutable accumulator with a pure `merge` and a JSON-safe `to_dict` /
    `from_dict` round trip so it can live in a checkpoint.
    """

    def __init__(self) -> None:
        self._data: dict[str, dict[str, dict[str, int]]] = {}

    def record(self, state_class: str, action_id: str, endpoint: str, count: int = 1) -> None:
        """Add `count` hits of an already-normalised endpoint."""
        if count < 1:
            raise ValueError(f"count must be >= 1, got {count}")
        bucket = self._data.setdefault(state_class, {}).setdefault(action_id, {})
        bucket[endpoint] = bucket.get(endpoint, 0) + count

    def record_calls(self, state_class: str, action_id: str, calls: Iterable[NetworkCall]) -> None:
        """Normalise and count each call."""
        for call in calls:
            self.record(state_class, action_id, normalise_endpoint(call.method, call.url))

    def counts(self, state_class: str, action_id: str) -> dict[str, int]:
        """A copy of the endpoint counts for one pair (empty if unseen)."""
        return dict(self._data.get(state_class, {}).get(action_id, {}))

    def top_k(self, state_class: str, action_id: str, k: int) -> list[tuple[str, int]]:
        """The `k` most frequent endpoints; ties broken by endpoint text."""
        if k < 0:
            raise ValueError(f"k must be >= 0, got {k}")
        ranked = sorted(self.counts(state_class, action_id).items(), key=lambda e: (-e[1], e[0]))
        return ranked[:k]

    def merge(self, other: EndpointCounter) -> EndpointCounter:
        """A new counter holding the sum of both; neither input is modified."""
        merged = EndpointCounter.from_dict(self.to_dict())
        for cls, by_action in other._data.items():
            for action_id, by_endpoint in by_action.items():
                for endpoint, n in by_endpoint.items():
                    merged.record(cls, action_id, endpoint, n)
        return merged

    def to_dict(self) -> dict[str, dict[str, dict[str, int]]]:
        """Deep, JSON-safe copy: `{state_class: {action_id: {endpoint: n}}}`."""
        return {
            cls: {a: dict(eps) for a, eps in by_action.items()}
            for cls, by_action in self._data.items()
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Mapping[str, Mapping[str, int]]]) -> EndpointCounter:
        counter = cls()
        for state_class, by_action in data.items():
            for action_id, by_endpoint in by_action.items():
                for endpoint, n in by_endpoint.items():
                    counter.record(state_class, action_id, endpoint, n)
        return counter

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, EndpointCounter):
            return NotImplemented
        return self._data == other._data

    __hash__ = None  # type: ignore[assignment]
