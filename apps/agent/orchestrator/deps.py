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
from typing import Any

from apps.agent.contracts import CrawlerPort, GraphPort, PerceptionPort, Role
from apps.agent.crawler.safety import SafetyPolicy
from apps.agent.orchestrator.config import OrchestratorConfig
from apps.agent.orchestrator.dynamic import NetworkObservations
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
    network: NetworkObservations | None = None


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
    if live:
        return live_ports(
            role=config.role, limiter=limiter, probabilistic_states=config.probabilistic_states
        )
    return fake_ports(role=config.role, limiter=limiter)


def _make_graph(mode: str) -> GraphPort:
    """memory | neo4j | auto (neo4j, falling back to memory if unreachable)."""
    from apps.agent.graph.memory_graph import MemoryGraph

    if mode == "memory":
        return MemoryGraph()
    if mode not in ("neo4j", "auto"):
        raise ValueError(f"graph must be 'memory', 'neo4j' or 'auto', not {mode!r}")
    try:
        from apps.agent.graph.neo4j_graph import Neo4jGraph

        return Neo4jGraph()
    except Exception:
        if mode == "neo4j":
            raise
        return MemoryGraph()


def live_ports(
    *,
    role: Role = "guest",
    limiter: RateLimiter | None = None,
    probabilistic_states: bool = False,
    safety: SafetyPolicy | None = None,
    graph: str = "auto",
) -> Ports:
    """Real ports from the other tracks' modules.

    Imports are deliberately local: `--fake` must keep working on a machine where
    Playwright, a VLM key, and Neo4j are all absent.

    Args:
        safety: optional crawl politeness/safety policy for the crawler.
        graph: "neo4j", "memory", or "auto" (Neo4j if reachable, else memory).

    Raises:
        NotImplementedError: while a required module cannot be imported. The
            message names what is missing.
    """
    missing: list[str] = []

    try:
        from apps.agent.crawler import PlaywrightCrawler
    except ImportError:
        missing.append("apps.agent.crawler.PlaywrightCrawler (Track A)")

    try:
        from apps.agent.perception import VLMPerception
    except ImportError:
        missing.append("apps.agent.perception.VLMPerception (Track C)")

    if graph == "neo4j":
        try:
            import apps.agent.graph.neo4j_graph  # noqa: F401
        except ImportError:
            missing.append("apps.agent.graph.Neo4jGraph (Track D)")

    if missing:
        raise NotImplementedError(
            "live mode needs implementations that do not exist yet: "
            + "; ".join(missing)
            + ". Run with --fake until they land."
        )

    kwargs: dict[str, Any] = {"role": role}
    if probabilistic_states:
        kwargs["probabilistic_states"] = True
    if safety is not None:
        kwargs["safety"] = safety
    crawler = PlaywrightCrawler(**kwargs)
    return Ports(
        crawler=crawler,
        network=crawler if probabilistic_states else None,
        perception=_throttled(VLMPerception(), limiter),
        graph=_make_graph(graph),
    )
