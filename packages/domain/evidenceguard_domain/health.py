"""Contract for the process-liveness response."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class HealthStatus(BaseModel):
    """Reports that the API process is running and answering requests.

    It says nothing about database readiness or any other dependency.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["ok"] = "ok"


CheckState = Literal["ok", "failed", "not_checked"]


class ReadinessChecks(BaseModel):
    """Fixed check names. ``migrations`` is ``not_checked`` when the database is unreachable."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    database: CheckState
    migrations: CheckState


class ReadinessStatus(BaseModel):
    """Whether the API can serve database-backed requests.

    ``ready`` only when the database answers and its applied migrations are exactly the
    packaged migration heads. Values are fixed; no URL, revision or error text is included.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["ready", "not_ready"]
    checks: ReadinessChecks
