"""The injected ports container.

Every crawler, VLM, and graph call in the orchestrator goes through one of these
three attributes. Nothing in `orchestrator/` imports a concrete implementation —
that single rule is what makes the loop testable with `fakes.py` and what keeps
Track B from accidentally depending on another track's internals.

Assembly happens here and nowhere else: `fake_ports()` for tests and the M1 demo,
`live_ports()` once the real modules land.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.agent.contracts import CrawlerPort, GraphPort, PerceptionPort, Role

__all__ = ["Ports", "fake_ports", "live_ports"]


@dataclass(frozen=True, slots=True)
class Ports:
    """The three services the orchestrator consumes.

    Frozen: swapping a port mid-run would make a resumed run behave differently
    from the run it resumed.
    """

    crawler: CrawlerPort
    perception: PerceptionPort
    graph: GraphPort


def fake_ports(*, role: Role = "guest") -> Ports:
    """In-memory ports over the scripted app. No network, no docker, no browser."""
    from apps.agent.orchestrator.fakes import FakeCrawler, FakeGraph, FakePerception

    return Ports(
        crawler=FakeCrawler(role=role),
        perception=FakePerception(),
        graph=FakeGraph(),
    )


def live_ports(*, role: Role = "guest") -> Ports:
    """Real ports from the other tracks' modules.

    Imports are deliberately local: `--fake` must keep working on a machine where
    Playwright, a VLM key, and Neo4j are all absent.

    Raises:
        NotImplementedError: while any of the three modules is still a stub. The
            message names what is missing, because "cannot import name" from
            three tracks at once is not a useful error.
    """
    missing: list[str] = []

    try:  # pragma: no cover - exercised only once Track A lands
        from apps.agent.crawler import PlaywrightCrawler  # type: ignore[attr-defined]
    except ImportError:
        missing.append("apps.agent.crawler.PlaywrightCrawler (Track A)")

    try:  # pragma: no cover - exercised only once Track C lands
        from apps.agent.perception import VLMPerception  # type: ignore[attr-defined]
    except ImportError:
        missing.append("apps.agent.perception.VLMPerception (Track C)")

    try:  # pragma: no cover - exercised only once Track D lands
        from apps.agent.graph import Neo4jGraph  # type: ignore[attr-defined]
    except ImportError:
        missing.append("apps.agent.graph.Neo4jGraph (Track D)")

    if missing:
        raise NotImplementedError(
            "live mode needs implementations that do not exist yet: "
            + "; ".join(missing)
            + ". Run with --fake until they land."
        )

    return Ports(  # pragma: no cover - unreachable until all three land
        crawler=PlaywrightCrawler(role=role),
        perception=VLMPerception(),
        graph=Neo4jGraph(),
    )
