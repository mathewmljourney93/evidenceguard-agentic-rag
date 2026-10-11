"""FastAPI application factory."""

from importlib.metadata import version

from fastapi import FastAPI

from evidenceguard_domain.health import HealthStatus


def create_app() -> FastAPI:
    """Build the API application. Importing this module does not start a server."""
    app = FastAPI(
        title="EvidenceGuard API",
        version=version("evidenceguard"),
        summary="Auditable vendor-risk review (pre-alpha).",
    )

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
