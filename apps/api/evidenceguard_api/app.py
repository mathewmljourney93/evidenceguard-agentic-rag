"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import version

from fastapi import FastAPI

from evidenceguard_api.auth import Authenticator, DatabaseAuthenticator
from evidenceguard_api.me import router as me_router
from evidenceguard_api.middleware import RequestContextMiddleware
from evidenceguard_api.problems import install_problem_handlers
from evidenceguard_domain.health import HealthStatus


def create_app(*, authenticator: Authenticator | None = None) -> FastAPI:
    """Build the API application. Importing this module does not start a server.

    The factory adds request-ID middleware and problem+json error handlers. It does not
    configure logging handlers; ``eg-api`` does that once per process.

    ``authenticator`` is the injection seam for authentication. When omitted, the app owns a
    ``DatabaseAuthenticator``: it reads database settings and creates its engine only when the
    first well-formed credential arrives, and the app disposes the engine on shutdown. Building
    the app and serving ``/healthz`` never read settings or connect to a database.
    """
    owned = DatabaseAuthenticator() if authenticator is None else None

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if owned is not None:
                owned.close()

    app = FastAPI(
        title="EvidenceGuard API",
        version=version("evidenceguard"),
        summary="Auditable vendor-risk review (pre-alpha).",
        lifespan=lifespan,
    )
    app.state.authenticator = owned if owned is not None else authenticator
    app.add_middleware(RequestContextMiddleware)
    install_problem_handlers(app)

    @app.get(
        "/healthz",
        response_model=HealthStatus,
        tags=["health"],
        summary="Process liveness",
        description=(
            "Returns 200 while the API process is serving requests. "
            "It does not check databases or any other dependency."
        ),
    )
    def healthz() -> HealthStatus:
        return HealthStatus()

    app.include_router(me_router)
    return app
