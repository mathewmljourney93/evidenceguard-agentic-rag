"""``GET /readyz``: database readiness (ADR-0006).

Unauthenticated. 200 only when the database answers and its applied migrations are exactly the
packaged heads; otherwise 503. The body has fixed check names and states and nothing else: no
URL, revision, SQL or error text. Missing or invalid database settings make the database check
fail. Readiness never migrates, creates tables or installs extensions. ``/healthz`` stays
independent of it.

``create_app(readiness=...)`` accepts any callable returning a ``ReadinessResult`` (the test
seam). The default checks the app's shared ``AppDatabase``. The route is synchronous, so its
database work runs in a worker thread.
"""

from typing import Protocol

from fastapi import APIRouter, Request, Response

from evidenceguard_api.database import AppDatabase
from evidenceguard_domain.health import CheckState, ReadinessChecks, ReadinessStatus
from evidenceguard_persistence.readiness import ReadinessResult, check_readiness
from evidenceguard_persistence.settings import DatabaseConfigurationError


class Readiness(Protocol):
    def __call__(self) -> ReadinessResult: ...


class DatabaseReadiness:
    def __init__(self, database: AppDatabase) -> None:
        self._database = database

    def __call__(self) -> ReadinessResult:
        try:
            engine = self._database.engine()
        except DatabaseConfigurationError:
            return ReadinessResult(database=False, migrations=None)
        return check_readiness(engine)


def _state(value: bool | None) -> CheckState:
    if value is None:
        return "not_checked"
    return "ok" if value else "failed"


router = APIRouter(tags=["health"])


@router.get(
    "/readyz",
    response_model=ReadinessStatus,
    summary="Database readiness",
    description=(
        "200 when the database is reachable and its migrations match this release; 503 "
        "otherwise. Reports only fixed check states. Never changes the database."
    ),
    responses={503: {"model": ReadinessStatus, "description": "Not ready."}},
)
def readyz(request: Request, response: Response) -> ReadinessStatus:
    readiness: Readiness = request.app.state.readiness
    try:
        result = readiness()
    except Exception:  # an unexpected probe failure is "not ready", never an error page
        result = ReadinessResult(database=False, migrations=None)
    response.headers["Cache-Control"] = "no-store"
    if not result.ready:
        response.status_code = 503
    return ReadinessStatus(
        status="ready" if result.ready else "not_ready",
        checks=ReadinessChecks(
            database=_state(result.database), migrations=_state(result.migrations)
        ),
    )
