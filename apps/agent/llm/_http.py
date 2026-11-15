"""Tiny stdlib JSON-over-HTTP helper shared by the REST providers.

Blocking by design; callers run it in a worker thread. Error messages never
include request headers, so API keys cannot leak (NFR-11).
"""

from __future__ import annotations

import base64
import contextlib
import json
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

from apps.agent.llm.base import ProviderError


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def request_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    timeout: float = 120.0,
) -> Any:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    hdrs = {"Content-Type": "application/json", "Accept": "application/json"}
    hdrs.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        detail = ""
        with contextlib.suppress(Exception):
            detail = exc.read().decode("utf-8", "replace")[:300]
        raise ProviderError(f"HTTP {exc.code} from {_host(url)}: {detail}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ProviderError(f"cannot reach {_host(url)}: {type(exc).__name__}") from None
    try:
        return json.loads(raw)
    except ValueError:
        raise ProviderError(f"non-JSON response from {_host(url)}") from None


def _host(url: str) -> str:
    return urlparse(url).netloc
