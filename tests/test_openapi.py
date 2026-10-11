from typing import Any

from fastapi.testclient import TestClient

from evidenceguard_api.app import create_app


def _openapi() -> dict[str, Any]:
    response = TestClient(create_app()).get("/openapi.json")
    assert response.status_code == 200
    schema: dict[str, Any] = response.json()
    return schema


def test_openapi_lists_only_healthz() -> None:
    assert list(_openapi()["paths"]) == ["/healthz"]


def test_openapi_describes_healthz_response() -> None:
    schema = _openapi()
    operation = schema["paths"]["/healthz"]["get"]

    assert operation["summary"] == "Process liveness"
    response_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert response_schema == {"$ref": "#/components/schemas/HealthStatus"}

    health_status = schema["components"]["schemas"]["HealthStatus"]
    assert health_status["additionalProperties"] is False
    assert health_status["properties"]["status"]["const"] == "ok"


def test_openapi_reports_package_version() -> None:
    assert _openapi()["info"]["version"] == "0.1.0.dev0"
