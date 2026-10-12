"""Vendor endpoints without a database: injected authenticator and in-memory store doubles.

The in-memory store keeps vendors per tenant and records every call, so the tests can check
that the API passes only the authenticated actor (never a submitted tenant) to the store.
"""

import json
import logging
from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from evidenceguard_api.app import create_app
from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_observability.jsonlog import JsonFormatter
from evidenceguard_persistence.credentials import generate_api_key
from evidenceguard_persistence.settings import DatabaseConfigurationError
from evidenceguard_persistence.vendors import DuplicateVendorSlugError, VendorPage, VendorRecord

PROBLEM = "application/problem+json"
SUBMITTED_MARKER = "submitted-marker-value"
FAILURE_MARKER = "fake-internal-failure-marker"
TENANT_A, TENANT_B = uuid4(), uuid4()


class FakeAuthenticator:
    def __init__(self) -> None:
        self.known: dict[str, ActorContext] = {}

    def add(self, actor: ActorContext) -> str:
        key = generate_api_key().plaintext.get_secret_value()
        self.known[key] = actor
        return key

    def __call__(self, credential: str) -> ActorContext | None:
        return self.known.get(credential)


class InMemoryVendorStore:
    """Tenant-scoped like the database store: every lookup is by the actor's tenant."""

    def __init__(self) -> None:
        self.rows: dict[UUID, list[VendorRecord]] = {}
        self.calls: list[tuple[str, UUID]] = []
        self.error: Exception | None = None

    def _check(self, op: str, actor: ActorContext) -> list[VendorRecord]:
        self.calls.append((op, actor.tenant_id))
        if self.error is not None:
            raise self.error
        return self.rows.setdefault(actor.tenant_id, [])

    def create(self, actor: ActorContext, *, slug: str, name: str) -> VendorRecord:
        rows = self._check("create", actor)
        if any(row.slug == slug for row in rows):
            raise DuplicateVendorSlugError()
        record = VendorRecord(id=uuid4(), slug=slug, name=name)
        rows.append(record)
        return record

    def list(self, actor: ActorContext, *, limit: int, offset: int) -> VendorPage:
        rows = sorted(self._check("list", actor), key=lambda r: (r.slug, str(r.id)))
        return VendorPage(items=tuple(rows[offset : offset + limit]), total=len(rows))

    def get(self, actor: ActorContext, vendor_id: UUID) -> VendorRecord | None:
        rows = self._check("get", actor)
        return next((row for row in rows if row.id == vendor_id), None)


class Harness:
    def __init__(self) -> None:
        self.auth = FakeAuthenticator()
        self.store = InMemoryVendorStore()
        self.keys = {
            (tenant, role): self.auth.add(
                ActorContext(tenant_id=tenant, actor_id=uuid4(), role=role)
            )
            for tenant in (TENANT_A, TENANT_B)
            for role in Role
        }

    def headers(self, tenant: UUID = TENANT_A, role: Role = Role.REVIEWER) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.keys[(tenant, role)]}"}


@pytest.fixture
def harness() -> Harness:
    return Harness()


@pytest.fixture
def client(harness: Harness) -> Iterator[TestClient]:
    app = create_app(authenticator=harness.auth, vendor_store=harness.store)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def _create(client: TestClient, harness: Harness, slug: str, **kwargs: Any) -> Any:
    tenant = kwargs.pop("tenant", TENANT_A)
    role = kwargs.pop("role", Role.REVIEWER)
    body = {"slug": slug, "name": kwargs.pop("name", slug.replace("-", " ").title())}
    return client.post("/v1/vendors", json=body, headers=harness.headers(tenant, role))


def _assert_problem(response: Any, status: int) -> None:
    assert response.status_code == status
    assert response.headers["content-type"] == PROBLEM
    body = response.json()
    assert body["status"] == status
    assert body["request_id"] == response.headers["X-Request-ID"]


# --- authorization -------------------------------------------------------------------------


@pytest.mark.parametrize("role", [Role.REVIEWER, Role.APPROVER])
def test_reviewers_and_approvers_can_use_every_route(
    client: TestClient, harness: Harness, role: Role
) -> None:
    created = _create(client, harness, "lumenvale-cloud", role=role)
    assert created.status_code == 201
    vendor_id = created.json()["id"]
    headers = harness.headers(role=role)

    assert client.get("/v1/vendors", headers=headers).status_code == 200
    assert client.get(f"/v1/vendors/{vendor_id}", headers=headers).status_code == 200


def test_admin_gets_a_generic_403_on_every_route(client: TestClient, harness: Harness) -> None:
    headers = harness.headers(role=Role.ADMIN)
    responses = [
        client.post("/v1/vendors", json={"slug": "x", "name": "X"}, headers=headers),
        client.get("/v1/vendors", headers=headers),
        client.get(f"/v1/vendors/{uuid4()}", headers=headers),
    ]

    for response in responses:
        _assert_problem(response, 403)
        assert response.json()["detail"] == "The request could not be completed."
    assert harness.store.calls == []


@pytest.mark.parametrize(
    ("method", "path"),
    [("post", "/v1/vendors"), ("get", "/v1/vendors"), ("get", f"/v1/vendors/{uuid4()}")],
)
def test_missing_or_invalid_credentials_get_the_generic_401(
    client: TestClient, harness: Harness, method: str, path: str
) -> None:
    for headers in ({}, {"Authorization": "Bearer not-a-key"}):
        response = client.request(method, path, json={"slug": "x", "name": "X"}, headers=headers)
        _assert_problem(response, 401)
        assert response.headers["WWW-Authenticate"] == "Bearer"
    assert harness.store.calls == []


def test_unauthenticated_invalid_body_is_401_not_422(client: TestClient, harness: Harness) -> None:
    response = client.post("/v1/vendors", json={"tenant_id": str(TENANT_B)})
    _assert_problem(response, 401)


# --- tenant scope --------------------------------------------------------------------------


def test_create_list_and_get_are_scoped_to_the_callers_tenant(
    client: TestClient, harness: Harness
) -> None:
    a = _create(client, harness, "alpha", tenant=TENANT_A).json()
    b = _create(client, harness, "bravo", tenant=TENANT_B).json()

    page_a = client.get("/v1/vendors", headers=harness.headers(TENANT_A)).json()
    page_b = client.get("/v1/vendors", headers=harness.headers(TENANT_B)).json()

    assert [item["slug"] for item in page_a["items"]] == ["alpha"] and page_a["total"] == 1
    assert [item["slug"] for item in page_b["items"]] == ["bravo"] and page_b["total"] == 1
    assert (
        client.get(f"/v1/vendors/{a['id']}", headers=harness.headers(TENANT_A)).status_code == 200
    )
    assert {tenant for _, tenant in harness.store.calls} == {TENANT_A, TENANT_B}
    assert b["id"] != a["id"]


def test_foreign_and_nonexistent_ids_return_identical_404s(
    client: TestClient, harness: Harness
) -> None:
    foreign = _create(client, harness, "bravo", tenant=TENANT_B).json()["id"]

    responses = [
        client.get(f"/v1/vendors/{vendor_id}", headers=harness.headers(TENANT_A))
        for vendor_id in (foreign, str(uuid4()))
    ]

    for response in responses:
        _assert_problem(response, 404)
    bodies = [{k: v for k, v in r.json().items() if k != "request_id"} for r in responses]
    assert bodies[0] == bodies[1]
    assert {k: v for k, v in responses[0].headers.items() if k.lower() != "x-request-id"} == {
        k: v for k, v in responses[1].headers.items() if k.lower() != "x-request-id"
    }


@pytest.mark.parametrize("field", ["tenant_id", "actor_id", "role", "id", "owner"])
def test_extra_body_fields_are_rejected_with_422(
    client: TestClient, harness: Harness, field: str
) -> None:
    body = {"slug": "alpha", "name": "Alpha", field: str(TENANT_B)}
    response = client.post("/v1/vendors", json=body, headers=harness.headers())

    _assert_problem(response, 422)
    assert harness.store.calls == []
    assert str(TENANT_B) not in response.text


def test_tenant_headers_and_query_parameters_are_ignored(
    client: TestClient, harness: Harness
) -> None:
    spoof = {"X-Tenant-ID": str(TENANT_B), "X-EvidenceGuard-Tenant": str(TENANT_B)}
    headers = {**harness.headers(TENANT_A), **spoof}
    created = client.post(
        "/v1/vendors",
        params={"tenant_id": str(TENANT_B)},
        json={"slug": "alpha", "name": "Alpha"},
        headers=headers,
    )
    listed = client.get("/v1/vendors", params={"tenant_id": str(TENANT_B)}, headers=headers)

    assert created.status_code == 201
    assert listed.json()["total"] == 1
    assert {tenant for _, tenant in harness.store.calls} == {TENANT_A}
    assert harness.store.rows.get(TENANT_B, []) == []


# --- duplicates ----------------------------------------------------------------------------


def test_duplicate_slug_in_one_tenant_is_a_generic_409(
    client: TestClient, harness: Harness
) -> None:
    assert _create(client, harness, "alpha").status_code == 201

    response = _create(client, harness, "alpha", name=SUBMITTED_MARKER)

    _assert_problem(response, 409)
    assert response.json()["detail"] == "The request could not be completed."
    assert SUBMITTED_MARKER not in response.text and "alpha" not in response.text


def test_same_slug_in_another_tenant_is_allowed(client: TestClient, harness: Harness) -> None:
    assert _create(client, harness, "alpha", tenant=TENANT_A).status_code == 201
    assert _create(client, harness, "alpha", tenant=TENANT_B).status_code == 201


# --- validation ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {"slug": "Alpha", "name": "A"},
        {"slug": "alpha_beta", "name": "A"},
        {"slug": "-alpha", "name": "A"},
        {"slug": "alpha-", "name": "A"},
        {"slug": "al--pha", "name": "A"},
        {"slug": "al pha", "name": "A"},
        {"slug": "", "name": "A"},
        {"slug": "a" * 65, "name": "A"},
        {"slug": "alpha", "name": ""},
        {"slug": "alpha", "name": "   "},
        {"slug": "alpha", "name": "x" * 201},
        {"slug": "alpha"},
        {"name": "A"},
        {"slug": 7, "name": "A"},
        {"slug": "alpha", "name": ["A"]},
    ],
)
def test_invalid_bodies_are_rejected_without_truncation(
    client: TestClient, harness: Harness, body: dict[str, Any]
) -> None:
    response = client.post("/v1/vendors", json=body, headers=harness.headers())

    _assert_problem(response, 422)
    assert harness.store.calls == []


def test_name_with_a_null_character_is_rejected_before_the_store(
    client: TestClient, harness: Harness
) -> None:
    name = f"Lumenvale{SUBMITTED_MARKER}\x00Cloud"
    response = client.post(
        "/v1/vendors", json={"slug": "lumenvale", "name": name}, headers=harness.headers()
    )

    _assert_problem(response, 422)
    assert harness.store.calls == []
    assert SUBMITTED_MARKER not in response.text and "Lumenvale" not in response.text


def test_unicode_name_is_accepted_unchanged(client: TestClient, harness: Harness) -> None:
    name = "Ålesund Nordlys Café 東雲 Ωmega"
    response = _create(client, harness, "alesund-nordlys", name=name)

    assert response.status_code == 201
    assert response.json()["name"] == name
    assert [row.name for row in harness.store.rows[TENANT_A]] == [name]


def test_boundary_lengths_are_accepted_exactly(client: TestClient, harness: Harness) -> None:
    slug, name = "a" * 64, "N" * 200
    response = _create(client, harness, slug, name=name)

    assert response.status_code == 201
    assert response.json()["slug"] == slug and response.json()["name"] == name


def test_created_vendor_returns_only_documented_fields(
    client: TestClient, harness: Harness
) -> None:
    response = _create(client, harness, "alpha", name="Alpha Cloud")

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "slug", "name"}
    UUID(body["id"])
    assert (body["slug"], body["name"]) == ("alpha", "Alpha Cloud")


def test_invalid_vendor_id_is_a_422(client: TestClient, harness: Harness) -> None:
    _assert_problem(client.get("/v1/vendors/not-a-uuid", headers=harness.headers()), 422)


# --- pagination ----------------------------------------------------------------------------


def test_pagination_defaults_bounds_and_order(client: TestClient, harness: Harness) -> None:
    for slug in ["delta", "alpha", "charlie", "bravo", "echo"]:
        assert _create(client, harness, slug).status_code == 201

    default = client.get("/v1/vendors", headers=harness.headers()).json()
    assert (default["limit"], default["offset"], default["total"]) == (20, 0, 5)
    assert [i["slug"] for i in default["items"]] == ["alpha", "bravo", "charlie", "delta", "echo"]

    page = client.get("/v1/vendors?limit=2&offset=2", headers=harness.headers()).json()
    assert [i["slug"] for i in page["items"]] == ["charlie", "delta"]
    assert (page["limit"], page["offset"], page["total"]) == (2, 2, 5)

    beyond = client.get("/v1/vendors?offset=10000", headers=harness.headers()).json()
    assert beyond["items"] == [] and beyond["total"] == 5
    assert client.get("/v1/vendors?limit=100", headers=harness.headers()).status_code == 200


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1", "offset=10001", "limit=x"])
def test_out_of_range_paging_is_a_422(client: TestClient, harness: Harness, query: str) -> None:
    _assert_problem(client.get(f"/v1/vendors?{query}", headers=harness.headers()), 422)
    assert harness.store.calls == []


# --- failures, privacy and request IDs ----------------------------------------------------


@pytest.mark.parametrize(
    "error",
    [
        OperationalError("SELECT", {}, Exception(FAILURE_MARKER)),
        DatabaseConfigurationError("EG_DATABASE_URL is not set"),
    ],
)
def test_database_failures_are_generic_503s(
    client: TestClient, harness: Harness, error: Exception
) -> None:
    harness.store.error = error
    responses = [
        _create(client, harness, "alpha"),
        client.get("/v1/vendors", headers=harness.headers()),
        client.get(f"/v1/vendors/{uuid4()}", headers=harness.headers()),
    ]

    for response in responses:
        _assert_problem(response, 503)
        assert FAILURE_MARKER not in response.text and "EG_DATABASE_URL" not in response.text


def test_submitted_values_never_reach_errors_or_logs(
    client: TestClient, harness: Harness, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    marker_slug = "submitted-marker-value"
    _create(client, harness, marker_slug, name=SUBMITTED_MARKER)
    duplicate = _create(client, harness, marker_slug, name=SUBMITTED_MARKER)
    invalid = client.post(
        "/v1/vendors",
        json={
            "slug": SUBMITTED_MARKER.upper(),
            "name": SUBMITTED_MARKER,
            "tenant_id": SUBMITTED_MARKER,
        },
        headers=harness.headers(),
    )

    assert SUBMITTED_MARKER not in duplicate.text
    assert SUBMITTED_MARKER.upper() not in invalid.text
    rendered = [JsonFormatter().format(record) for record in caplog.records]
    assert rendered
    for text in rendered + [repr(record.__dict__) for record in caplog.records]:
        assert SUBMITTED_MARKER not in text
    routes = {json.loads(line).get("route") for line in rendered}
    assert "/v1/vendors" in routes


def test_vendor_404_carries_the_incoming_request_id(client: TestClient, harness: Harness) -> None:
    incoming = "550e8400-e29b-41d4-a716-446655440000"
    response = client.get(
        f"/v1/vendors/{uuid4()}", headers={**harness.headers(), "X-Request-ID": incoming}
    )

    _assert_problem(response, 404)
    assert response.json()["request_id"] == incoming
