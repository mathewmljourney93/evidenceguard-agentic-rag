from typing import Any

from fastapi.testclient import TestClient

from evidenceguard_api.app import create_app


def _openapi() -> dict[str, Any]:
    response = TestClient(create_app()).get("/openapi.json")
    assert response.status_code == 200
    schema: dict[str, Any] = response.json()
    return schema


def test_openapi_lists_every_route() -> None:
    assert list(_openapi()["paths"]) == [
        "/healthz",
        "/readyz",
        "/v1/me",
        "/v1/vendors",
        "/v1/vendors/{vendor_id}",
        "/v1/vendors/{vendor_id}/documents",
        "/v1/documents/{document_id}",
        "/v1/documents/{document_id}/revisions",
        "/v1/documents/{document_id}/revisions/{revision_no}/chunks",
        "/v1/jobs/{job_id}",
    ]


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


def test_openapi_documents_vendor_routes() -> None:
    schema = _openapi()
    paths = schema["paths"]

    create = paths["/v1/vendors"]["post"]
    assert create["security"] == [{"ApiKey": []}]
    assert set(create["responses"]) == {"201", "401", "403", "409", "422", "503"}
    listing = paths["/v1/vendors"]["get"]
    assert {p["name"] for p in listing["parameters"]} == {"limit", "offset"}
    limit = next(p for p in listing["parameters"] if p["name"] == "limit")["schema"]
    offset = next(p for p in listing["parameters"] if p["name"] == "offset")["schema"]
    assert (limit["minimum"], limit["maximum"], limit["default"]) == (1, 100, 20)
    assert (offset["minimum"], offset["maximum"], offset["default"]) == (0, 10_000, 0)
    assert "not a snapshot" in listing["description"]
    get_one = paths["/v1/vendors/{vendor_id}"]["get"]
    assert {"404", "401", "403"} <= set(get_one["responses"])

    components = schema["components"]["schemas"]
    assert set(components["VendorCreate"]["properties"]) == {"slug", "name"}
    assert components["VendorCreate"]["additionalProperties"] is False
    assert set(components["VendorOut"]["properties"]) == {"id", "slug", "name"}
    assert set(components["VendorPageOut"]["properties"]) == {"items", "total", "limit", "offset"}


def test_openapi_documents_readyz_without_security() -> None:
    schema = _openapi()
    readyz = schema["paths"]["/readyz"]["get"]

    assert "security" not in readyz
    assert set(readyz["responses"]) == {"200", "503"}
    checks = schema["components"]["schemas"]["ReadinessChecks"]["properties"]
    assert set(checks) == {"database", "migrations"}


def test_openapi_documents_document_routes() -> None:
    schema = _openapi()
    paths = schema["paths"]

    upload = paths["/v1/vendors/{vendor_id}/documents"]["post"]
    assert upload["security"] == [{"ApiKey": []}]
    assert {"200", "202", "400", "401", "403", "404", "409", "413", "415", "422", "503"} <= set(
        upload["responses"]
    )
    body = upload["requestBody"]["content"]["multipart/form-data"]["schema"]
    assert set(body["properties"]) == {
        "file",
        "document_key",
        "title",
        "source_type",
        "version_label",
        "effective_date",
    }
    assert set(body["required"]) == {"file", "document_key", "title", "source_type"}
    assert body["additionalProperties"] is False

    chunks = paths["/v1/documents/{document_id}/revisions/{revision_no}/chunks"]["get"]
    params = {p["name"]: p["schema"] for p in chunks["parameters"]}
    assert (params["revision_no"]["minimum"], params["revision_no"]["maximum"]) == (
        1,
        2_147_483_647,
    )
    assert (params["limit"]["minimum"], params["limit"]["maximum"]) == (1, 200)
    assert params["limit"]["default"] == 50
    assert (params["offset"]["minimum"], params["offset"]["maximum"]) == (0, 4_095)

    components = schema["components"]["schemas"]
    assert "content_text" not in components["RevisionOut"]["properties"]
    assert not {"payload", "idempotency_key", "locked_by", "tenant_id"} & set(
        components["JobViewOut"]["properties"]
    )
    for name in ("RevisionOut", "JobViewOut", "ChunkOut", "UploadResultOut", "DocumentDetailOut"):
        assert components[name]["additionalProperties"] is False
