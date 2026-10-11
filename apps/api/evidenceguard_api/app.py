"""FastAPI application factory."""

from importlib.metadata import version

from fastapi import FastAPI

from evidenceguard_api.middleware import RequestContextMiddleware
from evidenceguard_api.problems import install_problem_handlers
from evidenceguard_domain.health import HealthStatus


def create_app() -> FastAPI:
    """Build the API application. Importing this module does not start a server.

    The factory adds request-ID middleware and problem+json error handlers. It does not
    configure logging handlers; ``eg-api`` does that once per process.
    """
    app = FastAPI(
        title="EvidenceGuard API",
        version=version("evidenceguard"),
        summary="Auditable vendor-risk review (pre-alpha).",
    )
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

    return app
