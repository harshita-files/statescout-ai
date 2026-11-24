"""Regression test from the DVWA independent-subject run.

DVWA serves its own translated README files next to the application. The crawl
followed them and audited 13 Markdown documents as if they were application UI.
"""

from __future__ import annotations

import pytest

from apps.agent.crawler.playwright_crawler import is_document_url


@pytest.mark.parametrize(
    "url",
    [
        "http://app.test/",
        "http://app.test/login.php",
        "http://app.test/index.html",
        "http://app.test/dashboard",
        "http://app.test/vulnerabilities/csrf/",
        "http://app.test/search?q=README.md",  # the extension is in the query, not the path
    ],
)
def test_pages_are_documents(url: str) -> None:
    assert is_document_url(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "http://app.test/README.md",
        "http://app.test/README.ar.md",
        "http://app.test/docs/guide.txt",
        "http://app.test/data/export.csv",
        "http://app.test/api/spec.json",
        "http://app.test/manual.pdf",
        "http://app.test/logo.png",
        "http://app.test/bundle.js",
        "http://app.test/theme.css",
        "http://app.test/archive.zip",
        "http://app.test/README.md?v=2",
        "http://app.test/README.md#top",
    ],
)
def test_non_documents_are_rejected(url: str) -> None:
    assert is_document_url(url) is False
