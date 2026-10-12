"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import version

from fastapi import FastAPI

from evidenceguard_api.auth import Authenticator, DatabaseAuthenticator
from evidenceguard_api.database import AppDatabase
from evidenceguard_api.me import router as me_router
from evidenceguard_api.middleware import RequestContextMiddleware
from evidenceguard_api.problems import install_problem_handlers
from evidenceguard_api.readiness import DatabaseReadiness, Readiness
from evidenceguard_api.readiness import router as readiness_router
from evidenceguard_api.vendors import DatabaseVendorStore, VendorStore
from evidenceguard_api.vendors import router as vendors_router
from evidenceguard_domain.health import HealthStatus


def create_app(
    *,
    authenticator: Authenticator | None = None,
    vendor_store: VendorStore | None = None,
    readiness: Readiness | None = None,
    database: AppDatabase | None = None,
) -> FastAPI:
    """Build the API application. Importing this module does not start a server.

    The factory adds request-ID middleware and problem+json error handlers. It does not
    configure logging handlers; ``eg-api`` does that once per process.

    Injection seams: ``authenticator``, ``vendor_store`` and ``readiness`` replace the
    database-backed defaults (tests pass doubles). Any default that is used shares one
    ``AppDatabase``: the ``database`` passed in, which the caller owns and closes, or else one
    the app creates and disposes on shutdown. The database starts lazily, so building the app,
    starting it and serving ``/healthz`` never read settings or connect.
    """
    shared = database if database is not None else AppDatabase()
    owns_database = database is None

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if owns_database:
                shared.close()

    app = FastAPI(
        title="EvidenceGuard API",
        version=version("evidenceguard"),
        summary="Auditable vendor-risk review (pre-alpha).",
        lifespan=lifespan,
    )
    app.state.database = shared
    # Only None selects a default: an injected component is kept even if it is falsy.
    app.state.authenticator = (
        authenticator if authenticator is not None else DatabaseAuthenticator(shared)
    )
    app.state.vendor_store = (
        vendor_store if vendor_store is not None else DatabaseVendorStore(shared)
    )
    app.state.readiness = readiness if readiness is not None else DatabaseReadiness(shared)
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

    app.include_router(readiness_router)
    app.include_router(me_router)
    app.include_router(vendors_router)
    return app
