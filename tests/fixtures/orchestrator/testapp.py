"""Load a `test-apps/` app as an in-memory crawler, policy, and ground truth.

The point of loading rather than hand-writing: the app's shape, its policy, and
its planted defects live in one place, next to the HTML, owned by whoever changes
the app. A test that restated any of them in Python would be asserting against a
copy — and a copy that drifted would pass while the product broke.

Today this drives the fakes. When Track A's live crawler lands, `app.json` is the
specification it must reproduce from the real pages; a disagreement between the
two is a genuine finding about one of them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from apps.agent.contracts import ExpectationNode, ExpectationSet, Role
from apps.agent.orchestrator.fakes import FakeCrawler, FakeLink, FakePage

REPO_ROOT = Path(__file__).resolve().parents[3]
TEST_APPS = REPO_ROOT / "test-apps"

__all__ = ["ExpectedViolation", "TestApp", "load"]


@dataclass(frozen=True, slots=True)
class ExpectedViolation:
    """One documented, planted defect."""

    id: str
    page: str
    expectation_id: str
    clause_type: str
    why: str

    @property
    def key(self) -> tuple[str, str, str]:
        """What a found violation must match: page, clause, and polarity."""
        return (self.page, self.expectation_id, self.clause_type)


@dataclass(frozen=True, slots=True)
class TestApp:
    """A loaded app: how to crawl it, what to check, and what should be found."""

    name: str
    seed: str
    role: Role
    pages: dict[str, FakePage]
    policy: ExpectationSet
    expected: tuple[ExpectedViolation, ...]
    expected_states: int

    def crawler(self) -> FakeCrawler:
        return FakeCrawler(self.pages, role=self.role, base_url="")

    def state_ids(self, fingerprint: Any) -> dict[str, str]:
        """Map each page path to the state id a crawl will give it.

        Ground truth is written in page paths, because that is what a human can
        check against the HTML. Findings come back keyed by fingerprint. This is
        the join, and it uses the same `GraphPort` the run used so the two
        cannot disagree about what a state id is.
        """
        probe = self.crawler()
        return {path: fingerprint(probe.open(path)) for path in self.pages}


def _expectations(clauses: list[dict[str, Any]], polarity: str) -> tuple[ExpectationNode, ...]:
    return tuple(
        ExpectationNode(
            expectation_id=clause["id"],
            polarity=polarity,  # type: ignore[arg-type]
            subject=clause["subject"],
            roles=tuple(clause["roles"]),
            source_text=clause["source_text"],
        )
        for clause in clauses
    )


def load(name: str) -> TestApp:
    """Read `test-apps/<name>/{app,policy,violations}.json`."""
    directory = TEST_APPS / name
    app = json.loads((directory / "app.json").read_text(encoding="utf-8"))
    policy = json.loads((directory / "policy.json").read_text(encoding="utf-8"))
    truth = json.loads((directory / "violations.json").read_text(encoding="utf-8"))

    pages = {
        path: FakePage(
            title=spec["title"],
            elements=tuple(spec["elements"]),
            transitions=tuple(
                FakeLink(name=link["name"], to=link["to"], role=link.get("role", "link"))
                for link in spec["links"]
            ),
        )
        for path, spec in app["pages"].items()
    }

    return TestApp(
        name=app["name"],
        seed=app["seed"],
        role=app["role"],
        pages=pages,
        policy=ExpectationSet(
            forbidden=_expectations(policy["forbidden"], "must_not_exist"),
            required=_expectations(policy["required"], "must_exist"),
        ),
        expected=tuple(ExpectedViolation(**entry) for entry in truth["expected"]),
        expected_states=truth["expected_graph"]["states"],
    )
