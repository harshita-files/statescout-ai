"""Screenshots are viewport-sized by default so a VLM call has a bounded token cost."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from apps.agent.crawler.capture import extract_page_state


def _page(calls: list[dict[str, Any]]) -> Any:
    page = MagicMock()
    page.title.return_value = "t"
    page.content.return_value = "<html></html>"
    page.screenshot.side_effect = lambda **kw: calls.append(kw)
    return page


def test_screenshot_is_viewport_only_by_default(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("STATESCOUT_FULL_PAGE_SCREENSHOTS", raising=False)
    calls: list[dict[str, Any]] = []
    extract_page_state(_page(calls), "http://a.test/", str(tmp_path))
    assert calls and calls[0]["full_page"] is False


def test_full_page_is_opt_in(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STATESCOUT_FULL_PAGE_SCREENSHOTS", "1")
    calls: list[dict[str, Any]] = []
    extract_page_state(_page(calls), "http://a.test/", str(tmp_path))
    assert calls[0]["full_page"] is True
