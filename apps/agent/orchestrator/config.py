"""Run configuration (M2-P3).

Every tunable the orchestrator has, in one place. Nothing in `orchestrator/`
hardcodes a limit at a call site — a depth cap buried in `explore.py` is a cap
nobody can change without a deploy, and a cap that differs between `explore.py`
and `graph_runner.py` is a parity bug that only shows up under load.

Precedence, highest first
-------------------------
1. Explicit keyword arguments — `OrchestratorConfig(depth_limit=2)`
2. Environment variables, prefixed `STATESCOUT_`
3. A `.env` file in the working directory
4. The defaults below

Environment variables
---------------------
=============================== ======= ==================================
Variable                        Default Meaning
=============================== ======= ==================================
STATESCOUT_ROLE                 guest   Role to browse as. One per run
                                        (ADR-001 decision 5); multi-role
                                        coverage is multiple runs.
STATESCOUT_DEPTH_LIMIT          5       Max BFS depth (FR-10). 0 audits
                                        only the seed state.
STATESCOUT_MAX_STATES           200     Hard cap on distinct states.
STATESCOUT_PERCEPTION_RATE_PER_MIN 15   VLM calls per minute. 0 disables
                                        throttling entirely.
STATESCOUT_CHECKPOINT_DIR       .statescout/checkpoints
STATESCOUT_LOG_LEVEL            INFO
STATESCOUT_RUN_ID_STRATEGY      uuid    uuid | timestamp | fixed
STATESCOUT_RUN_ID               unset   Required when strategy is `fixed`.
=============================== ======= ==================================

Two limits, not one
-------------------
`depth_limit` and `max_states` bound different failure modes and neither implies
the other. A shallow app with fan-out 50 blows past `max_states` at depth 2; an
infinite-scroll page walks to depth 200 while producing four distinct states.
Termination needs both.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from apps.agent.contracts import Role

__all__ = ["OrchestratorConfig", "RunIdStrategy"]

RunIdStrategy = Literal["uuid", "timestamp", "fixed"]


class OrchestratorConfig(BaseSettings):
    """Immutable for the lifetime of a run.

    Frozen on purpose: a config that changes mid-run makes a resumed run behave
    differently from the run it resumed, and the checkpoint carries no record of
    what the values were at the time.
    """

    model_config = SettingsConfigDict(
        env_prefix="STATESCOUT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    role: Role = "guest"

    #: FR-10. Depth of the *state*, not of the action; 0 audits the seed alone.
    depth_limit: int = Field(default=5, ge=0)

    #: Distinct states, not visits. A cycle revisiting one state forever would
    #: never trip this, which is why the visited-pair set exists separately.
    max_states: int = Field(default=200, ge=1)

    #: Track C's provider throttle, enforced from our side too. 0 means unlimited
    #: — correct for the fakes, wrong for anything holding a real API key.
    perception_rate_per_min: int = Field(default=15, ge=0)

    checkpoint_dir: Path = Path(".statescout/checkpoints")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    run_id_strategy: RunIdStrategy = "uuid"
    #: Set this to make a run reproducible, or to resume a specific one.
    run_id: str | None = None

    @model_validator(mode="after")
    def _fixed_strategy_needs_an_id(self) -> OrchestratorConfig:
        if self.run_id_strategy == "fixed" and not self.run_id:
            raise ValueError(
                "run_id_strategy='fixed' requires run_id "
                "(set STATESCOUT_RUN_ID, or pick 'uuid' / 'timestamp')"
            )
        return self

    def new_run_id(self) -> str:
        """Mint an id for a run.

        `uuid` is the default and the only one safe for concurrent runs.
        `timestamp` is sortable and readable, and collides if two runs start in
        the same second. `fixed` reuses `run_id`, which is what resume and
        reproducible tests need — and what will silently overwrite a previous
        run's graph if you forget you set it.
        """
        if self.run_id_strategy == "fixed":
            assert self.run_id is not None  # enforced by the validator
            return self.run_id
        if self.run_id_strategy == "timestamp":
            return "run-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        return f"run-{uuid.uuid4().hex[:12]}"
