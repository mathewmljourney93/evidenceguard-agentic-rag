"""Contract for the process-liveness response."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class HealthStatus(BaseModel):
    """Reports that the API process is running and answering requests.

    It says nothing about database readiness or any other dependency.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["ok"] = "ok"
