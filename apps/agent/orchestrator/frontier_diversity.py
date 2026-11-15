"""Prefer unseen kinds of page over more of a kind already seen.

A breadth-first crawl of a site with ten `/stock/*` pages spends its state budget on those
ten before reaching `/trade` or `/portfolio`. Pages that share a URL pattern are one *kind*;
this reorders the frontier so kinds visited least come first. It only reorders: no pair is
ever dropped (the visited `(state, action)` set remains the sole loop-prevention).
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Sequence
from urllib.parse import parse_qsl, urlsplit

from apps.agent.orchestrator.state import PendingAction

#: Path segments that are identifiers (tickers, ids, hashes), not page names.
_ID_SEGMENT = re.compile(r"^(?:[A-Z0-9][A-Z0-9.\-_]{0,7}|\d+|[0-9a-f]{8,})$")


def url_template(url: str) -> str:
    """`/stock/AAPL` -> `/stock/*`; query values are dropped, query keys kept."""
    parts = urlsplit(url)
    segments = ["*" if _ID_SEGMENT.match(s) else s for s in parts.path.split("/") if s]
    path = "/" + "/".join(segments)
    keys = sorted({k for k, _ in parse_qsl(parts.query, keep_blank_values=True)})
    return path + ("?" + "&".join(keys) if keys else "")


def _target_url(item: PendingAction) -> str | None:
    t = item.action.target
    return t if item.action.kind == "navigate" and t.startswith(("http://", "https://")) else None


def diversify(frontier: Sequence[PendingAction], seen_urls: Iterable[str]) -> list[PendingAction]:
    """Stable reorder: by depth, then by how often the target's page kind was already seen.

    Actions whose destination URL is unknown (clicks) are never penalised.
    """
    visits = Counter(url_template(u) for u in seen_urls)

    def key(item: PendingAction) -> tuple[int, int]:
        url = _target_url(item)
        return (item.depth, visits[url_template(url)] if url else 0)

    return sorted(frontier, key=key)
