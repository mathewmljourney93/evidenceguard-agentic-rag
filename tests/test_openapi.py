from typing import Any

from fastapi.testclient import TestClient

from evidenceguard_api.app import create_app


def _openapi() -> dict[str, Any]:
    response = TestClient(create_app()).get("/openapi.json")
    assert response.status_code == 200
    schema: dict[str, Any] = response.json()
    return schema


def test_openapi_lists_healthz_and_me() -> None:
    assert list(_openapi()["paths"]) == ["/healthz", "/v1/me"]


def test_openapi_documents_the_bearer_api_key_scheme() -> None:
    schema = _openapi()
    scheme = schema["components"]["securitySchemes"]["ApiKey"]

    assert scheme["type"] == "http"
    assert scheme["scheme"] == "bearer"
    assert scheme["bearerFormat"].startswith("egk_<prefix>_<secret>")
    me = schema["paths"]["/v1/me"]["get"]
    assert me["security"] == [{"ApiKey": []}]
    assert "security" not in schema["paths"]["/healthz"]["get"]
    assert set(me["responses"]) == {"200", "401", "503"}
    assert "application/problem+json" in me["responses"]["401"]["content"]
    assert "parameters" not in me  # no tenant or other inputs are accepted


def test_openapi_principal_has_only_tenant_actor_and_role() -> None:
    principal = _openapi()["components"]["schemas"]["Principal"]

    assert set(principal["properties"]) == {"tenant_id", "actor_id", "role"}
    assert principal["additionalProperties"] is False


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
