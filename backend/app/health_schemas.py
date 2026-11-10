from typing import Literal

from pydantic import BaseModel, ConfigDict


class WorkerSignal(BaseModel):
    """Informational worker liveness from the freshest heartbeat; never gates readiness."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "stale", "unknown"]
    last_seen_seconds: int | None = None


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "unavailable"]
    worker: WorkerSignal | None = None
