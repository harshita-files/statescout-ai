"""The injected ports container.

Every crawler, VLM, and graph call in the orchestrator goes through one of these
three attributes. Nothing in `orchestrator/` imports a concrete implementation —
that single rule is what makes the loop testable with `fakes.py` and what keeps
Track B from accidentally depending on another track's internals.

Assembly happens here and nowhere else: `build_ports(config)` for anything
driven by configuration, `fake_ports()` / `live_ports()` when a test wants to
choose directly.

Perception is wrapped in `ThrottledPerception` whenever a limiter is supplied, so
the nodes hold an already-throttled port and cannot forget to wait for a token.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.agent.contracts import CrawlerPort, GraphPort, PerceptionPort, Role
from apps.agent.orchestrator.config import OrchestratorConfig
from apps.agent.orchestrator.ratelimit import RateLimiter, ThrottledPerception

__all__ = ["Ports", "build_ports", "fake_ports", "live_ports"]


@dataclass(frozen=True, slots=True)
class Ports:
    """The three services the orchestrator consumes.

    Frozen: swapping a port mid-run would make a resumed run behave differently
    from the run it resumed.
    """

    crawler: CrawlerPort
    perception: PerceptionPort
    graph: GraphPort


def _throttled(perception: PerceptionPort, limiter: RateLimiter | None) -> PerceptionPort:
    return perception if limiter is None else ThrottledPerception(perception, limiter)


def fake_ports(*, role: Role = "guest", limiter: RateLimiter | None = None) -> Ports:
    """In-memory ports over the scripted app. No network, no docker, no browser."""
    from apps.agent.orchestrator.fakes import FakeCrawler, FakeGraph, FakePerception

    return Ports(
        crawler=FakeCrawler(role=role),
        perception=_throttled(FakePerception(), limiter),
        graph=FakeGraph(),
    )


def build_ports(config: OrchestratorConfig, *, live: bool = False) -> Ports:
    """The configured entry point: role and throttle both come from `config`.

    A rate limiter is attached only when `perception_rate_per_min` is non-zero,
    so the fakes stay instantaneous by default and a real key never does.
    """
    limiter = (
        RateLimiter(config.perception_rate_per_min) if config.perception_rate_per_min else None
    )
    build = live_ports if live else fake_ports
    return build(role=config.role, limiter=limiter)


def live_ports(*, role: Role = "guest", limiter: RateLimiter | None = None) -> Ports:
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
        from apps.agent.crawler import PlaywrightCrawler
    except ImportError:
        missing.append("apps.agent.crawler.PlaywrightCrawler (Track A)")

    try:  # pragma: no cover - exercised only once Track C lands
        from apps.agent.perception import VLMPerception
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
        perception=_throttled(VLMPerception(), limiter),
        graph=Neo4jGraph(),
    )
