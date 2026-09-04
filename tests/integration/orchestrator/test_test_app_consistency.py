"""The demo app's HTML and its machine-readable twin must agree.

`app.json` is what Track B's tests crawl today and what Track A's live crawler
must reproduce from the real pages tomorrow. The moment the two drift, every
ground-truth assertion in this directory is measuring a fiction: the tests would
keep passing against a description of an app that no longer exists.

So the twin is checked, not trusted. Edit `dashboard.html` to remove the admin
link and forget `app.json`, and this file fails immediately instead of three
weeks later when the live crawler finds one fewer violation than the fakes did.

Parsed with regex rather than a HTML parser on purpose: the pages are ours, tiny,
and deliberately plain, and a dependency here would be a dependency in CI.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.fixtures.orchestrator import testapp

APP = "broken-admin"
DIRECTORY = testapp.TEST_APPS / APP

TAG = re.compile(r'data-tag="([^"]+)"')
#: The whole opening tag plus its text, so attributes can be read individually.
#: An `(?:role="...")?` inside one pattern silently matches empty whenever another
#: attribute sits between `href` and `role`, which reads as "role is missing".
ANCHOR = re.compile(r"<a\s+([^>]*)>([^<]*)</a>", re.S)
ATTR = re.compile(r'([a-z-]+)="([^"]*)"')


@pytest.fixture(scope="module")
def app() -> testapp.TestApp:
    return testapp.load(APP)


def html_for(path: str) -> str:
    return (DIRECTORY / path.lstrip("/")).read_text(encoding="utf-8")


def anchors(source: str) -> list[tuple[str, str, str]]:
    """(href, role, text) for every real navigation control.

    In-page anchors are excluded: the skip link is an element to be audited, not
    an action to be explored.
    """
    found = []
    for raw_attrs, text in ANCHOR.findall(source):
        attrs = dict(ATTR.findall(raw_attrs))
        href = attrs.get("href", "")
        if href.startswith("#"):
            continue
        found.append((href, attrs.get("role", "link"), text.strip()))
    return found


def test_every_declared_page_has_a_file(app: testapp.TestApp) -> None:
    for path in app.pages:
        assert (DIRECTORY / path.lstrip("/")).is_file(), f"app.json declares missing {path}"


def test_every_file_is_declared(app: testapp.TestApp) -> None:
    """An undeclared page is a state the crawl will find and the ground truth
    has never heard of."""
    on_disk = {
        "/" + str(file.relative_to(DIRECTORY)).replace("\\", "/")
        for file in DIRECTORY.rglob("*.html")
    }
    assert on_disk == set(app.pages)


@pytest.mark.parametrize("path", list(testapp.load(APP).pages))
def test_titles_match(path: str, app: testapp.TestApp) -> None:
    title = re.search(r"<title>(.*?)</title>", html_for(path), re.S)
    assert title is not None
    assert title.group(1).strip() == app.pages[path].title


@pytest.mark.parametrize("path", list(testapp.load(APP).pages))
def test_element_tags_match(path: str, app: testapp.TestApp) -> None:
    """`elements` is what the policy matches against — a missing tag here is a
    violation that silently stops being findable."""
    assert set(TAG.findall(html_for(path))) == set(app.pages[path].elements)


@pytest.mark.parametrize("path", list(testapp.load(APP).pages))
def test_link_names_and_roles_match(path: str, app: testapp.TestApp) -> None:
    """Names and ARIA roles feed the content-addressed action id (ADR-001
    decision 1), so a mismatch changes the crawl's identity for that control."""
    from_html = {(text, role) for _href, role, text in anchors(html_for(path))}
    from_json = {(link.name, link.role) for link in app.pages[path].transitions}
    assert from_html == from_json


@pytest.mark.parametrize("path", list(testapp.load(APP).pages))
def test_link_destinations_match(path: str, app: testapp.TestApp) -> None:
    """`href` is relative in the HTML and absolute in `app.json`; resolving one
    against the other is what proves the graph shape is the same."""
    base = Path(path).parent
    from_html = {
        (text, "/" + str((base / href).as_posix()).lstrip("/").replace("./", ""))
        for href, _role, text in anchors(html_for(path))
    }
    from_json = {(link.name, link.to) for link in app.pages[path].transitions}
    assert from_html == from_json


def test_the_planted_violations_are_marked_in_the_source(app: testapp.TestApp) -> None:
    """Every defect carries a `PLANTED V-nn` comment where it lives, so someone
    reading the HTML sees it is deliberate and does not "fix" the fixture."""
    for expected in app.expected:
        source = html_for(expected.page)
        assert f"PLANTED {expected.id}" in source or expected.clause_type == "required_absent", (
            f"{expected.id} is not marked in {expected.page}"
        )


def test_the_missing_skip_link_really_is_missing(app: testapp.TestApp) -> None:
    """V-04 is an absence, so it cannot be marked with a comment where it is.
    Assert the absence directly, and assert every other page has it — otherwise
    the fixture is only accidentally right."""
    for path in app.pages:
        has_skip = 'data-tag="skip-to-content"' in html_for(path)
        assert has_skip is (path != "/pages/admin.html"), path


def test_the_policy_only_references_subjects_the_app_can_produce(
    app: testapp.TestApp,
) -> None:
    """A clause about a tag no page ever renders is dead: a `must_not_exist`
    that can never fire looks like a passing audit."""
    rendered = {tag for page in app.pages.values() for tag in page.elements}
    for clause in app.policy.forbidden:
        assert clause.subject in rendered, f"{clause.expectation_id} can never fire"
