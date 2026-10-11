from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, field_validator

from evidenceguard_api.app import create_app
from evidenceguard_api.problems import (
    GENERIC_CLIENT_ERROR_DETAIL,
    GENERIC_SERVER_ERROR_DETAIL,
    PublicHTTPException,
    PublicMessage,
)

# Obviously fake marker standing in for sensitive submitted input; not a credential.
SUBMITTED_MARKER = "submitted-marker-value"
EXCEPTION_TEXT = "internal failure detail that must stay private"


class _Submission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int
    note: str

    @field_validator("note")
    @classmethod
    def _reject(cls, value: str) -> str:
        raise ValueError(f"rejected note {value!r}")


def _app_with_test_routes() -> FastAPI:
    app = create_app()

    @app.get("/test-only/items/{item_id}")
    def item(item_id: int, limit: int = 10) -> dict[str, int]:
        return {"item_id": item_id, "limit": limit}

    @app.post("/test-only/submissions")
    def submit(submission: _Submission) -> dict[str, int]:
        return {"count": submission.count}

    @app.get("/test-only/protected")
    def protected() -> None:
        raise PublicHTTPException(
            401,
            PublicMessage.AUTHENTICATION_REQUIRED,
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.get("/test-only/rate-limited")
    def rate_limited(user: str) -> None:
        # Deliberately unsafe application code: submitted input in an ordinary detail string.
        raise HTTPException(
            status_code=429,
            detail=f"Too many requests from {user}",
            headers={"Retry-After": "30"},
        )

    @app.get("/test-only/unavailable")
    def unavailable() -> None:
        raise HTTPException(status_code=503, detail=EXCEPTION_TEXT)

    @app.get("/test-only/structured-detail")
    def structured_detail() -> None:
        raise HTTPException(status_code=409, detail={"internal": EXCEPTION_TEXT})

    @app.get("/test-only/boom")
    def boom() -> None:
        raise RuntimeError(EXCEPTION_TEXT)

    return app


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(_app_with_test_routes(), raise_server_exceptions=False) as test_client:
        yield test_client


def _problem(response: Any, status: int) -> dict[str, Any]:
    assert response.status_code == status
    assert response.headers["content-type"] == "application/problem+json"
    body: dict[str, Any] = response.json()
    assert body["type"] == "about:blank"
    assert body["status"] == status
    assert isinstance(body["title"], str) and body["title"]
    assert body["request_id"] == response.headers["X-Request-ID"]
    return body


def test_healthz_success_is_unchanged(client: TestClient) -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"status": "ok"}


def test_unknown_route_is_a_404_problem(client: TestClient) -> None:
    body = _problem(client.get(f"/no-such-route/{SUBMITTED_MARKER}"), 404)

    assert body["title"] == "Not Found"
    assert body["detail"] == GENERIC_CLIENT_ERROR_DETAIL
    assert SUBMITTED_MARKER not in str(body)


def test_method_not_allowed_keeps_the_allow_header(client: TestClient) -> None:
    response = client.post("/healthz")

    _problem(response, 405)
    assert response.headers["allow"] == "GET"


def test_public_http_exception_shows_its_reviewed_message(client: TestClient) -> None:
    response = client.get("/test-only/protected")

    body = _problem(response, 401)
    assert response.headers["www-authenticate"] == "Bearer"
    assert body["detail"] == PublicMessage.AUTHENTICATION_REQUIRED.value


def test_ordinary_http_exception_detail_string_is_not_published(client: TestClient) -> None:
    supplied = "6ba7b810-9dad-11d1-80b4-00c04fd430c8"

    response = client.get(
        "/test-only/rate-limited",
        params={"user": SUBMITTED_MARKER},
        headers={"X-Request-ID": supplied},
    )

    body = _problem(response, 429)
    assert response.headers["X-Request-ID"] == supplied
    assert body["request_id"] == supplied
    assert response.headers["retry-after"] == "30"
    assert body["detail"] == GENERIC_CLIENT_ERROR_DETAIL
    assert SUBMITTED_MARKER not in response.text
    assert "Too many requests from" not in response.text


def test_server_side_http_exception_gets_generic_detail(client: TestClient) -> None:
    response = client.get("/test-only/unavailable")

    body = _problem(response, 503)
    assert body["detail"] == GENERIC_SERVER_ERROR_DETAIL
    assert EXCEPTION_TEXT not in response.text


def test_non_string_http_exception_detail_is_not_exposed(client: TestClient) -> None:
    response = client.get("/test-only/structured-detail")

    body = _problem(response, 409)
    assert body["detail"] == GENERIC_CLIENT_ERROR_DETAIL
    assert EXCEPTION_TEXT not in response.text


def test_validation_problem_lists_locations_without_input(client: TestClient) -> None:
    response = client.get(
        f"/test-only/items/{SUBMITTED_MARKER}", params={"limit": SUBMITTED_MARKER}
    )

    body = _problem(response, 422)
    assert {(tuple(e["loc"]), e["type"]) for e in body["errors"]} == {
        (("path", "item_id"), "int_parsing"),
        (("query", "limit"), "int_parsing"),
    }
    assert all(set(error) == {"loc", "type"} for error in body["errors"])
    assert SUBMITTED_MARKER not in response.text


def test_body_validation_does_not_echo_values_or_messages(client: TestClient) -> None:
    response = client.post(
        "/test-only/submissions",
        json={"count": SUBMITTED_MARKER, "note": SUBMITTED_MARKER, "token": SUBMITTED_MARKER},
    )

    body = _problem(response, 422)
    assert {e["type"] for e in body["errors"]} == {"int_parsing", "value_error", "extra_forbidden"}
    assert SUBMITTED_MARKER not in response.text
    assert "rejected note" not in response.text


def test_validation_errors_are_bounded(client: TestClient) -> None:
    payload = {
        "count": 1,
        "note": "x",
        **{f"field_{index:03d}" + "x" * 100: 1 for index in range(50)},
    }

    body = _problem(client.post("/test-only/submissions", json=payload), 422)

    assert len(body["errors"]) == 20
    assert all(len(str(part)) <= 64 for error in body["errors"] for part in error["loc"])


def test_unexpected_error_is_a_generic_500(client: TestClient) -> None:
    response = client.get("/test-only/boom")

    body = _problem(response, 500)
    assert body["detail"] == "An unexpected error occurred."
    assert EXCEPTION_TEXT not in response.text
    assert "RuntimeError" not in response.text
    assert "Traceback" not in response.text


def test_unexpected_error_is_not_suppressed() -> None:
    with pytest.raises(RuntimeError, match=EXCEPTION_TEXT):
        TestClient(_app_with_test_routes()).get("/test-only/boom")
