"""The authenticated API boundary: ``GET /v1/me``, Bearer parsing, 401s and failure paths.

An explicit authenticator double is injected through ``create_app(authenticator=...)``, so
no database is configured or contacted. Keys are generated at run time; none is stored here.
"""

import json
import logging
from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.exc import OperationalError

from evidenceguard_api import auth as api_auth
from evidenceguard_api import database as api_database
from evidenceguard_api.app import create_app
from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_observability.jsonlog import JsonFormatter
from evidenceguard_persistence.credentials import generate_api_key
from evidenceguard_persistence.db import dispose_engine
from evidenceguard_persistence.settings import DATABASE_URL_ENV, DatabaseConfigurationError

PROBLEM = "application/problem+json"
FAILURE_MARKER = "fake-internal-failure-marker"


def _new_key() -> str:
    return generate_api_key().plaintext.get_secret_value()


class FakeAuthenticator:
    """Maps known credentials to principals and records every credential it is asked about."""

    def __init__(self, known: dict[str, ActorContext] | None = None) -> None:
        self.known = dict(known or {})
        self.calls: list[str] = []
        self.error: Exception | None = None

    def __call__(self, credential: str) -> ActorContext | None:
        self.calls.append(credential)
        if self.error is not None:
            raise self.error
        return self.known.get(credential)


@pytest.fixture
def key() -> str:
    return _new_key()


@pytest.fixture
def principal() -> ActorContext:
    return ActorContext(tenant_id=uuid4(), actor_id=uuid4(), role=Role.APPROVER)


@pytest.fixture
def authenticator(key: str, principal: ActorContext) -> FakeAuthenticator:
    return FakeAuthenticator({key: principal})


@pytest.fixture
def client(authenticator: FakeAuthenticator) -> Iterator[TestClient]:
    with TestClient(create_app(authenticator=authenticator)) as test_client:
        yield test_client


def _bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


# --- successful authentication ----------------------------------------------------------


def test_me_returns_only_the_authenticated_principal(
    client: TestClient, key: str, principal: ActorContext
) -> None:
    response = client.get("/v1/me", headers=_bearer(key))

    assert response.status_code == 200
    assert response.json() == {
        "tenant_id": str(principal.tenant_id),
        "actor_id": str(principal.actor_id),
        "role": "approver",
    }
    assert response.headers["Cache-Control"] == "no-store"
    assert key not in response.text


@pytest.mark.parametrize("role", list(Role))
def test_me_reports_each_role(role: Role) -> None:
    key = _new_key()
    actor = ActorContext(tenant_id=uuid4(), actor_id=uuid4(), role=role)
    with TestClient(create_app(authenticator=FakeAuthenticator({key: actor}))) as client:
        assert client.get("/v1/me", headers=_bearer(key)).json()["role"] == role.value


def test_bearer_scheme_name_is_case_insensitive(client: TestClient, key: str) -> None:
    assert client.get("/v1/me", headers={"Authorization": f"bearer {key}"}).status_code == 200


def test_tenant_headers_and_query_cannot_override_the_authenticated_scope(
    client: TestClient, key: str, principal: ActorContext
) -> None:
    other_tenant, other_actor = str(uuid4()), str(uuid4())
    response = client.get(
        "/v1/me",
        params={"tenant_id": other_tenant, "actor_id": other_actor, "role": "admin"},
        headers={
            **_bearer(key),
            "X-Tenant-ID": other_tenant,
            "X-EvidenceGuard-Tenant": other_tenant,
            "X-Actor-ID": other_actor,
            "X-Role": "admin",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "tenant_id": str(principal.tenant_id),
        "actor_id": str(principal.actor_id),
        "role": "approver",
    }


# --- rejected credentials ---------------------------------------------------------------


def _assert_generic_401(response: Any) -> None:
    assert response.status_code == 401
    assert response.headers["content-type"] == PROBLEM
    assert response.headers["WWW-Authenticate"] == "Bearer"
    request_id = response.headers["X-Request-ID"]
    assert response.json() == {
        "type": "about:blank",
        "title": "Unauthorized",
        "status": 401,
        "detail": "Authentication is required.",
        "request_id": request_id,
    }


def test_missing_credentials_get_a_generic_401(
    client: TestClient, authenticator: FakeAuthenticator
) -> None:
    _assert_generic_401(client.get("/v1/me"))
    assert authenticator.calls == []


@pytest.mark.parametrize(
    "value",
    [
        "Basic {key}",
        "Token {key}",
        "Bearer",
        "Bearer ",
        "Bearer  {key}",
        "Bearer {key} ",
        "Bearer {key} extra",
        "Bearer\t{key}",
        "{key}",
        "Bearer {key}" + "A" * 100,
    ],
)
def test_malformed_authorization_headers_get_a_generic_401(
    client: TestClient, authenticator: FakeAuthenticator, key: str, value: str
) -> None:
    _assert_generic_401(client.get("/v1/me", headers={"Authorization": value.format(key=key)}))
    assert authenticator.calls == []


def test_oversized_authorization_header_is_rejected_unparsed(
    client: TestClient, authenticator: FakeAuthenticator
) -> None:
    _assert_generic_401(client.get("/v1/me", headers={"Authorization": "Bearer " + "a" * 5000}))
    assert authenticator.calls == []


def test_non_ascii_authorization_header_is_rejected(
    client: TestClient, authenticator: FakeAuthenticator
) -> None:
    response = client.get("/v1/me", headers=[(b"Authorization", "Bearer été".encode("latin-1"))])
    _assert_generic_401(response)
    assert authenticator.calls == []


def test_duplicate_authorization_headers_are_rejected(
    client: TestClient, authenticator: FakeAuthenticator, key: str
) -> None:
    response = client.get(
        "/v1/me", headers=[("Authorization", f"Bearer {key}"), ("Authorization", f"Bearer {key}")]
    )

    _assert_generic_401(response)
    assert authenticator.calls == []


@pytest.mark.parametrize("credential", ["unknown", "wrong-secret", "revoked"])
def test_rejected_keys_get_the_same_generic_401(
    client: TestClient, authenticator: FakeAuthenticator, credential: str
) -> None:
    # The double returns None for any key it does not know, as the real authenticator does
    # for unknown prefixes, wrong secrets and revoked keys alike.
    presented = _new_key()
    response = client.get("/v1/me", headers=_bearer(presented))

    _assert_generic_401(response)
    assert authenticator.calls == [presented]
    assert presented not in response.text


def test_401_request_id_matches_the_incoming_request_id(client: TestClient) -> None:
    incoming = "550e8400-e29b-41d4-a716-446655440000"
    response = client.get("/v1/me", headers={"X-Request-ID": incoming})

    _assert_generic_401(response)
    assert response.headers["X-Request-ID"] == incoming
    assert response.json()["request_id"] == incoming


# --- failure paths ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "error",
    [
        OperationalError("SELECT", {}, Exception(FAILURE_MARKER)),
        DatabaseConfigurationError(f"{DATABASE_URL_ENV} is not set"),
    ],
)
def test_database_failures_return_a_generic_503(
    client: TestClient, authenticator: FakeAuthenticator, key: str, error: Exception
) -> None:
    authenticator.error = error
    response = client.get("/v1/me", headers=_bearer(key))

    assert response.status_code == 503
    assert response.headers["content-type"] == PROBLEM
    assert response.json()["detail"] == "The server could not complete the request."
    for secret in (FAILURE_MARKER, DATABASE_URL_ENV, key):
        assert secret not in response.text


def test_unexpected_authenticator_error_is_a_generic_500(key: str) -> None:
    authenticator = FakeAuthenticator()
    authenticator.error = RuntimeError(FAILURE_MARKER)
    app = create_app(authenticator=authenticator)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/v1/me", headers=_bearer(key))

    assert response.status_code == 500
    assert FAILURE_MARKER not in response.text and key not in response.text


def test_credentials_never_reach_the_logs(
    client: TestClient, key: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    client.get("/v1/me", headers=_bearer(key))
    client.get("/v1/me", headers=_bearer(_new_key()))
    client.get("/v1/me", headers={"Authorization": f"Basic {key}"})

    formatter = JsonFormatter()
    rendered = [formatter.format(record) for record in caplog.records]
    raw = [repr(record.__dict__) for record in caplog.records]
    assert rendered, "expected request completion logs"
    for text in rendered + raw:
        assert key not in text
        assert key[21:] not in text
    routes = {json.loads(line).get("route") for line in rendered}
    assert "/v1/me" in routes


# --- the default, app-owned database authenticator --------------------------------------


def test_default_app_serves_health_without_database_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(DATABASE_URL_ENV, raising=False)
    with TestClient(create_app()) as client:
        assert client.get("/healthz").status_code == 200
        _assert_generic_401(client.get("/v1/me"))
        _assert_generic_401(client.get("/v1/me", headers={"Authorization": "Bearer not-a-key"}))


def test_default_app_without_database_settings_returns_503_for_a_well_formed_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(DATABASE_URL_ENV, raising=False)
    key = _new_key()
    with TestClient(create_app()) as client:
        response = client.get("/v1/me", headers=_bearer(key))

    assert response.status_code == 503
    assert DATABASE_URL_ENV not in response.text and key not in response.text


def test_default_app_with_an_invalid_database_url_does_not_reveal_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(DATABASE_URL_ENV, f"mysql://someone:{FAILURE_MARKER}@db.invalid/x")
    with TestClient(create_app()) as client:
        response = client.get("/v1/me", headers=_bearer(_new_key()))

    assert response.status_code == 503
    assert FAILURE_MARKER not in response.text and "db.invalid" not in response.text


class _RecordingDelegate:
    def __init__(self, session_factory: Any) -> None:
        self.session_factory = session_factory

    def __call__(self, credential: str) -> ActorContext | None:
        return None


def test_default_app_creates_its_engine_lazily_and_disposes_it_on_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        DATABASE_URL_ENV, f"postgresql://someone:{FAILURE_MARKER}@db.invalid:5432/eg_unit"
    )
    monkeypatch.setattr(api_auth, "ApiKeyAuthenticator", _RecordingDelegate)
    disposed: list[Engine] = []

    def recording_dispose(engine: Engine) -> None:
        disposed.append(engine)
        dispose_engine(engine)

    monkeypatch.setattr(api_database, "dispose_engine", recording_dispose)

    app = create_app()
    assert isinstance(app.state.authenticator, api_auth.DatabaseAuthenticator)
    shared = app.state.database
    assert isinstance(shared, api_database.AppDatabase)
    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200
        assert not shared.started  # not created by construction, startup or /healthz
        _assert_generic_401(client.get("/v1/me", headers=_bearer(_new_key())))
        assert shared.started
        engine = shared.engine()
        assert FAILURE_MARKER not in repr(engine)

    assert disposed == [engine]
    assert not shared.started


def test_injected_authenticator_is_not_closed_by_the_app(key: str) -> None:
    class Closable(FakeAuthenticator):
        closed = False

        def close(self) -> None:
            self.closed = True

    authenticator = Closable()
    with TestClient(create_app(authenticator=authenticator)):
        pass
    assert authenticator.closed is False


def test_principal_ids_are_uuids(client: TestClient, key: str) -> None:
    body = client.get("/v1/me", headers=_bearer(key)).json()
    UUID(body["tenant_id"])
    UUID(body["actor_id"])
