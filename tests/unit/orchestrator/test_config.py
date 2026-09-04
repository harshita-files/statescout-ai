"""Config precedence, validation, and the perception throttle (M2-P3).

Every test constructs `OrchestratorConfig` with `_env_file=None`. Without it a
developer who happens to have a `.env` gets different results from CI, and the
failure looks like a flaky test rather than a leaked environment.

The rate-limiter tests drive a fake clock. A test that really sleeps four seconds
to prove a four-second wait is a test somebody eventually deletes.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from apps.agent.contracts import CaptureBundle, ExpectationSet, PerceptionPort, SemanticUIMap
from apps.agent.orchestrator.config import OrchestratorConfig
from apps.agent.orchestrator.deps import build_ports, fake_ports
from apps.agent.orchestrator.fakes import FakePerception
from apps.agent.orchestrator.ratelimit import RateLimiter, ThrottledPerception


def config(**overrides: object) -> OrchestratorConfig:
    return OrchestratorConfig(_env_file=None, **overrides)  # type: ignore[arg-type]


class Clock:
    """A hand-cranked monotonic clock. `sleep` advances it, nothing waits."""

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds

    def advance(self, seconds: float) -> None:
        self.now += seconds


def limiter(per_minute: int, clock: Clock, **kwargs: object) -> RateLimiter:
    return RateLimiter(per_minute, clock=clock, sleep=clock.sleep, **kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Defaults and precedence
# ---------------------------------------------------------------------------


def test_defaults_match_the_documented_table() -> None:
    """The module docstring is the contract other tracks read. If it drifts from
    the code, the docstring is the thing people will believe."""
    settings = config()
    assert settings.role == "guest"
    assert settings.depth_limit == 5
    assert settings.max_states == 200
    assert settings.perception_rate_per_min == 15
    assert settings.checkpoint_dir == Path(".statescout/checkpoints")
    assert settings.log_level == "INFO"
    assert settings.run_id_strategy == "uuid"


def test_environment_overrides_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STATESCOUT_DEPTH_LIMIT", "2")
    monkeypatch.setenv("STATESCOUT_ROLE", "admin")
    settings = config()
    assert settings.depth_limit == 2
    assert settings.role == "admin"


def test_explicit_arguments_beat_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """A test or a CLI flag has to be able to win, or `--depth-limit` becomes a
    suggestion on a machine with the variable exported."""
    monkeypatch.setenv("STATESCOUT_DEPTH_LIMIT", "2")
    assert config(depth_limit=9).depth_limit == 9


def test_the_prefix_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    """`DEPTH_LIMIT` in the environment belongs to somebody else."""
    monkeypatch.setenv("DEPTH_LIMIT", "99")
    assert config().depth_limit == 5


def test_unrelated_variables_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STATESCOUT_NOT_A_SETTING", "x")
    assert config().depth_limit == 5


def test_a_dotenv_file_is_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = tmp_path / ".env"
    env.write_text("STATESCOUT_MAX_STATES=7\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert OrchestratorConfig().max_states == 7


def test_the_environment_beats_a_dotenv_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".env").write_text("STATESCOUT_MAX_STATES=7\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("STATESCOUT_MAX_STATES", "11")
    assert OrchestratorConfig().max_states == 11


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("depth_limit", -1),
        ("max_states", 0),
        ("perception_rate_per_min", -1),
        ("log_level", "LOUD"),
        ("run_id_strategy", "vibes"),
    ],
)
def test_invalid_values_are_rejected_at_construction(field: str, value: object) -> None:
    """Fail at startup, not three hours into a crawl."""
    with pytest.raises(ValidationError):
        config(**{field: value})


def test_depth_limit_zero_is_legal() -> None:
    """Audit only the seed state. Useful, and not the same thing as a mistake."""
    assert config(depth_limit=0).depth_limit == 0


def test_rate_zero_is_legal_and_means_unlimited() -> None:
    assert config(perception_rate_per_min=0).perception_rate_per_min == 0


def test_config_is_frozen() -> None:
    """A value that changes mid-run makes a resumed run diverge from the run it
    resumed, and the checkpoint has no record of what it used to be."""
    settings = config()
    with pytest.raises(ValidationError):
        settings.depth_limit = 1  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Run ids
# ---------------------------------------------------------------------------


def test_uuid_strategy_gives_unique_ids() -> None:
    settings = config()
    assert settings.new_run_id() != settings.new_run_id()
    assert settings.new_run_id().startswith("run-")


def test_timestamp_strategy_is_sortable() -> None:
    settings = config(run_id_strategy="timestamp")
    assert settings.new_run_id().startswith("run-")
    assert settings.new_run_id() == settings.new_run_id()  # same second


def test_fixed_strategy_reuses_the_id() -> None:
    settings = config(run_id_strategy="fixed", run_id="run-repro")
    assert settings.new_run_id() == "run-repro"
    assert settings.new_run_id() == "run-repro"


def test_fixed_strategy_without_an_id_is_rejected() -> None:
    """Silently falling back to uuid would make a 'reproducible' run irreproducible."""
    with pytest.raises(ValidationError, match="requires run_id"):
        config(run_id_strategy="fixed")


# ---------------------------------------------------------------------------
# The token bucket
# ---------------------------------------------------------------------------


def test_a_full_bucket_does_not_wait() -> None:
    clock = Clock()
    bucket = limiter(60, clock)
    for _ in range(60):
        assert bucket.acquire() == 0.0
    assert clock.slept == []


def test_an_empty_bucket_waits_for_one_token() -> None:
    """60/min is one token per second."""
    clock = Clock()
    bucket = limiter(60, clock, burst=1)
    bucket.acquire()
    assert bucket.acquire() == pytest.approx(1.0)
    assert clock.slept == [pytest.approx(1.0)]


def test_the_wait_scales_with_the_rate() -> None:
    clock = Clock()
    bucket = limiter(15, clock, burst=1)  # Track C's default: 15/min = 4s apart
    bucket.acquire()
    assert bucket.acquire() == pytest.approx(4.0)


def test_idle_time_banks_credit() -> None:
    """The reason this is a bucket and not a fixed sleep: a burst after a quiet
    stretch should be free, because the average is still under the limit."""
    clock = Clock()
    bucket = limiter(60, clock, burst=10)
    for _ in range(10):
        bucket.acquire()

    clock.advance(5.0)  # five seconds of idle = five tokens back
    for _ in range(5):
        assert bucket.acquire() == 0.0
    assert clock.slept == []


def test_banked_credit_is_capped_at_the_burst() -> None:
    """An hour of idling must not buy an hour-long spike at the provider."""
    clock = Clock()
    bucket = limiter(60, clock, burst=5)
    clock.advance(3600.0)
    for _ in range(5):
        assert bucket.acquire() == 0.0
    assert bucket.acquire() > 0.0


def test_the_average_rate_is_held_over_a_long_run() -> None:
    clock = Clock()
    bucket = limiter(30, clock, burst=1)
    for _ in range(31):
        bucket.acquire()
    # 1 free token, then 30 waits of 2s each.
    assert clock.now == pytest.approx(60.0)


def test_zero_means_unlimited() -> None:
    clock = Clock()
    bucket = limiter(0, clock)
    for _ in range(1000):
        assert bucket.acquire() == 0.0
    assert bucket.unlimited
    assert clock.slept == []


def test_a_negative_rate_is_rejected() -> None:
    with pytest.raises(ValueError, match=">= 0"):
        RateLimiter(-1)


def test_total_wait_is_recorded_for_the_manifest() -> None:
    """ "The crawl took an hour" and "the crawl waited 55 minutes" are different
    findings, and M4-P2's manifest has to be able to tell them apart."""
    clock = Clock()
    bucket = limiter(60, clock, burst=1)
    for _ in range(4):
        bucket.acquire()
    assert bucket.total_wait == pytest.approx(3.0)
    assert bucket.acquisitions == 4


# ---------------------------------------------------------------------------
# The throttled port
# ---------------------------------------------------------------------------


def test_throttled_perception_is_still_a_perception_port() -> None:
    throttled = ThrottledPerception(FakePerception(), RateLimiter(0))
    assert isinstance(throttled, PerceptionPort)


@pytest.mark.parametrize("method", ["analyze", "audit", "complete_text"])
def test_every_method_spends_a_token(method: str) -> None:
    """Including `audit`. Which methods reach a model is Track C's business, and
    the contract says this port is the only door to one."""
    clock = Clock()
    bucket = limiter(60, clock)
    throttled = ThrottledPerception(FakePerception(), bucket)
    bundle = fake_ports().crawler.open("/dashboard")

    calls = {
        "analyze": lambda: throttled.analyze(bundle, "guest"),
        "audit": lambda: throttled.audit(
            SemanticUIMap(state_id="s", url="/", role="guest"), ExpectationSet()
        ),
        "complete_text": lambda: throttled.complete_text("hello"),
    }
    calls[method]()
    assert bucket.acquisitions == 1


def test_throttling_does_not_change_the_result() -> None:
    inner = FakePerception()
    throttled = ThrottledPerception(inner, RateLimiter(0))
    bundle = fake_ports().crawler.open("/dashboard")
    assert throttled.analyze(bundle, "guest") == inner.analyze(bundle, "guest")


def test_a_slow_bucket_actually_delays_the_loop() -> None:
    clock = Clock()
    bucket = limiter(15, clock, burst=1)
    throttled = ThrottledPerception(FakePerception(), bucket)
    bundle = fake_ports().crawler.open("/dashboard")

    throttled.analyze(bundle, "guest")
    throttled.analyze(bundle, "guest")
    assert clock.now == pytest.approx(4.0)


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------


def test_build_ports_throttles_when_a_rate_is_configured() -> None:
    ports = build_ports(config(perception_rate_per_min=15))
    assert isinstance(ports.perception, ThrottledPerception)


def test_build_ports_skips_the_wrapper_when_unlimited() -> None:
    """No wrapper at all rather than a wrapper that never waits: one less frame
    in every traceback, and the fakes stay honest about what they are."""
    ports = build_ports(config(perception_rate_per_min=0))
    assert not isinstance(ports.perception, ThrottledPerception)


def test_build_ports_passes_the_role_through() -> None:
    ports = build_ports(config(role="admin"))
    bundle: CaptureBundle = ports.crawler.open("/dashboard")
    assert 'data-role="admin"' in bundle.dom


def test_build_ports_live_still_reports_missing_implementations() -> None:
    with pytest.raises(NotImplementedError):
        build_ports(config(), live=True)
