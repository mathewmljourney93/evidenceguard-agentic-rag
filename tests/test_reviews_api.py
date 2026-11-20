"""W8 review endpoints without a database (ADR-0027): an injected authenticator and a fake
``ReviewService`` that is tenant-scoped like the database service and records every call."""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from evidenceguard_agents.templates import load_template
from evidenceguard_api import reviews as review_api
from evidenceguard_api.app import create_app
from evidenceguard_api.database import AppDatabase
from evidenceguard_api.problems import PublicMessage
from evidenceguard_api.reviews import (
    DatabaseReviewService,
    ExcludedPendingOut,
    ReviewAccepted,
    ReviewCreated,
    ReviewDetail,
    ReviewResult,
    ReviewsNotConfiguredError,
    TemplateSummary,
    UnknownReviewTemplateError,
)
from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_domain.retrieval import (
    EmptySnapshotError,
    RetrievalScopeError,
    SnapshotBoundsError,
    SnapshotInconsistentError,
    SnapshotNotReadyError,
)
from evidenceguard_domain.review_outputs import ReviewStatus
from evidenceguard_domain.reviews import (
    ReviewArtifactsUnavailableError,
    ReviewCommitOutcomeUnknownError,
    ReviewConflictRetryableError,
    ReviewIdempotencyConflictError,
    ReviewLimitReachedError,
    ReviewNotFoundError,
)
from evidenceguard_persistence.credentials import generate_api_key
from evidenceguard_persistence.review_outputs import ReviewOutputNotFoundError
from evidenceguard_persistence.settings import (
    REVIEW_MODEL_ENV,
    REVIEW_PROVIDER_ENV,
    ReviewConfigurationError,
    ReviewProvider,
    ReviewSettings,
)

PROBLEM = "application/problem+json"
TENANT_A, TENANT_B = uuid4(), uuid4()
KEY = "w8-review-key-0001"
KEY_MARKER = "idem-marker-value-7f3a"  # appears in no fixed response text
MODEL = "claude-example-20990101"  # synthetic
T0 = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
SHA = "a" * 64


def _accepted(review_id: UUID | None = None) -> ReviewAccepted:
    return ReviewAccepted(
        review_id=review_id or uuid4(),
        job_id=uuid4(),
        status=ReviewStatus.QUEUED,
        revision_ids=[uuid4(), uuid4()],
        excluded_pending=ExcludedPendingOut(count=1, revision_ids=[uuid4()], truncated=False),
    )


class FakeReviewService:
    """Reviews per tenant; the request (vendor, template, version) is compared on replay."""

    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []
        self.error: Exception | None = None
        self.by_key: dict[tuple[UUID, str], tuple[tuple[Any, ...], ReviewAccepted]] = {}
        self.details: dict[tuple[UUID, UUID], ReviewDetail] = {}
        self.results: dict[tuple[UUID, UUID], ReviewResult] = {}
        self.vendors: dict[UUID, set[UUID]] = {}

    def _check(self, *call: Any) -> None:
        self.calls.append(call)
        if self.error is not None:
            raise self.error

    def create(
        self,
        actor: ActorContext,
        vendor_id: UUID,
        template_id: str,
        template_version: int,
        idempotency_key: str,
    ) -> ReviewCreated:
        self._check(
            "create", actor.tenant_id, vendor_id, template_id, template_version, idempotency_key
        )
        if vendor_id not in self.vendors.get(actor.tenant_id, set()):
            raise RetrievalScopeError()
        request = (vendor_id, template_id, template_version)
        existing = self.by_key.get((actor.tenant_id, idempotency_key))
        if existing is not None:
            if existing[0] != request:
                raise ReviewIdempotencyConflictError()
            return ReviewCreated(accepted=existing[1], replayed=True)
        accepted = _accepted()
        self.by_key[(actor.tenant_id, idempotency_key)] = (request, accepted)
        self.details[(actor.tenant_id, accepted.review_id)] = ReviewDetail(
            id=accepted.review_id,
            vendor_id=vendor_id,
            job_id=accepted.job_id,
            status=ReviewStatus.QUEUED,
            captured_at=T0,
            template_id=template_id,
            template_version=template_version,
            model_id=MODEL,
            revision_ids=accepted.revision_ids,
            excluded_pending=accepted.excluded_pending,
            snapshot_sha256=SHA,
            configuration_sha256="b" * 64,
        )
        return ReviewCreated(accepted=accepted, replayed=False)

    def detail(self, actor: ActorContext, review_id: UUID) -> ReviewDetail:
        self._check("detail", actor.tenant_id, review_id)
        found = self.details.get((actor.tenant_id, review_id))
        if found is None:
            raise ReviewNotFoundError()
        return found

    def result(self, actor: ActorContext, review_id: UUID) -> ReviewResult:
        self._check("result", actor.tenant_id, review_id)
        if (actor.tenant_id, review_id) not in self.details:
            raise ReviewNotFoundError()
        found = self.results.get((actor.tenant_id, review_id))
        if found is None:
            raise ReviewOutputNotFoundError()
        return found

    def templates(self) -> list[TemplateSummary]:
        self._check("templates")
        return [
            TemplateSummary(
                template_id="vendor_security_review",
                version=1,
                title="Vendor security review",
                question_count=8,
                sha256=SHA,
            )
        ]


class Harness:
    def __init__(self, service: Any = None) -> None:
        self.known: dict[str, ActorContext] = {}
        self.keys = {
            (tenant, role): self._add(ActorContext(tenant_id=tenant, actor_id=uuid4(), role=role))
            for tenant in (TENANT_A, TENANT_B)
            for role in Role
        }
        self.service = service if service is not None else FakeReviewService()
        self.vendor = uuid4()
        if isinstance(self.service, FakeReviewService):
            self.service.vendors[TENANT_A] = {self.vendor}
        self.client = TestClient(
            create_app(authenticator=self._authenticate, review_service=self.service),
            raise_server_exceptions=False,
        )

    def _authenticate(self, credential: str) -> ActorContext | None:
        return self.known.get(credential)

    def _add(self, actor: ActorContext) -> str:
        key = generate_api_key().plaintext.get_secret_value()
        self.known[key] = actor
        return key

    def headers(
        self, tenant: UUID = TENANT_A, role: Role = Role.REVIEWER, key: str | None = KEY
    ) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.keys[(tenant, role)]}"}
        if key is not None:
            headers["Idempotency-Key"] = key
        return headers

    def post(self, body: Any = None, **kwargs: Any) -> Any:
        payload = {"vendor_id": str(self.vendor)} if body is None else body
        return self.client.post("/v1/reviews", json=payload, headers=self.headers(**kwargs))


@pytest.fixture
def harness() -> Iterator[Harness]:
    yield Harness()


def _problem(response: Any, status: int, detail: str | None = None) -> dict[str, Any]:
    assert response.status_code == status
    assert response.headers["content-type"] == PROBLEM
    body: dict[str, Any] = response.json()
    if detail is not None:
        assert body["detail"] == detail
    return body


def _forbidden_engine() -> Any:
    raise AssertionError("the database must not be used")


# --- POST /v1/reviews -----------------------------------------------------------------------------


def test_create_review_returns_202_with_snapshot_ids(harness: Harness) -> None:
    response = harness.post()

    assert response.status_code == 202
    body = response.json()
    assert set(body) == {"review_id", "job_id", "status", "revision_ids", "excluded_pending"}
    assert body["status"] == "queued"
    assert len(body["revision_ids"]) == 2
    assert set(body["excluded_pending"]) == {"count", "revision_ids", "truncated"}
    assert harness.service.calls == [
        ("create", TENANT_A, harness.vendor, "vendor_security_review", 1, KEY)
    ]


def test_replayed_key_returns_200_and_the_original_review(harness: Harness) -> None:
    first = harness.post()
    second = harness.post()

    assert (first.status_code, second.status_code) == (202, 200)
    assert second.json() == first.json()
    other_key = harness.post(key="w8-review-key-0002")
    assert other_key.status_code == 202
    assert other_key.json()["review_id"] != first.json()["review_id"]


@pytest.mark.parametrize(
    "key", [None, "", "has space", "-leading-dash", "k" * 129, "semi;colon", "slash/key"]
)
def test_missing_or_invalid_idempotency_key_is_422(harness: Harness, key: str | None) -> None:
    headers = harness.headers(key=None)
    if key is not None:
        headers["Idempotency-Key"] = key
    response = harness.client.post(
        "/v1/reviews", json={"vendor_id": str(harness.vendor)}, headers=headers
    )

    body = _problem(response, 422)
    assert {"loc": ["header", "Idempotency-Key"], "type": body["errors"][0]["type"]} in body[
        "errors"
    ]
    assert harness.service.calls == []


@pytest.mark.parametrize(
    "extra",
    [
        {"tenant_id": str(TENANT_B)},
        {"actor_id": str(uuid4())},
        {"model_id": MODEL},
        {"role": "approver"},
        {"unexpected": 1},
    ],
)
def test_tenant_or_extra_fields_in_body_are_422(harness: Harness, extra: dict[str, Any]) -> None:
    response = harness.post({"vendor_id": str(harness.vendor), **extra})

    body = _problem(response, 422)
    assert [error["type"] for error in body["errors"]] == ["extra_forbidden"]
    assert harness.service.calls == []


def test_tenant_headers_and_query_are_ignored(harness: Harness) -> None:
    headers = {**harness.headers(), "X-Tenant-ID": str(TENANT_B)}
    response = harness.client.post(
        f"/v1/reviews?tenant_id={TENANT_B}",
        json={"vendor_id": str(harness.vendor)},
        headers=headers,
    )

    assert response.status_code == 202
    assert harness.service.calls[0][1] == TENANT_A


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"vendor_id": "not-a-uuid"},
        {"vendor_id": str(uuid4()), "template_id": "Upper"},
        {"vendor_id": str(uuid4()), "template_version": 0},
        {"vendor_id": str(uuid4()), "template_version": True},
    ],
)
def test_invalid_body_fields_are_422(harness: Harness, body: dict[str, Any]) -> None:
    _problem(harness.post(body), 422)
    assert harness.service.calls == []


def test_admin_gets_403_and_anonymous_401(harness: Harness) -> None:
    review_id = uuid4()
    for method, path in (
        ("POST", "/v1/reviews"),
        ("GET", f"/v1/reviews/{review_id}"),
        ("GET", f"/v1/reviews/{review_id}/result"),
        ("GET", "/v1/review-templates"),
    ):
        admin = harness.client.request(
            method,
            path,
            json={"vendor_id": str(harness.vendor)},
            headers=harness.headers(role=Role.ADMIN),
        )
        _problem(admin, 403)
        anonymous = harness.client.request(
            method, path, json={"vendor_id": str(harness.vendor)}, headers={"Idempotency-Key": KEY}
        )
        body = _problem(anonymous, 401, PublicMessage.AUTHENTICATION_REQUIRED.value)
        assert anonymous.headers["www-authenticate"] == "Bearer"
        assert "request_id" in body
    assert harness.service.calls == []


def test_approver_may_create_reviews(harness: Harness) -> None:
    assert harness.post(role=Role.APPROVER).status_code == 202


def test_unconfigured_reviews_return_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unconfigured() -> ReviewSettings | None:
        return None

    def partial() -> ReviewSettings | None:
        raise ReviewConfigurationError("EG_REVIEW_MODEL is not set")

    for loader in (unconfigured, partial):
        service = DatabaseReviewService(AppDatabase(_forbidden_engine), settings_loader=loader)
        harness = Harness(service)
        _problem(harness.post(), 503, PublicMessage.REVIEWS_NOT_CONFIGURED.value)

    # The default loader reads the environment per request: unset and partial are both 503.
    monkeypatch.delenv(REVIEW_PROVIDER_ENV, raising=False)
    monkeypatch.delenv(REVIEW_MODEL_ENV, raising=False)
    harness = Harness(DatabaseReviewService(AppDatabase(_forbidden_engine)))
    _problem(harness.post(), 503, PublicMessage.REVIEWS_NOT_CONFIGURED.value)
    monkeypatch.setenv(REVIEW_PROVIDER_ENV, "anthropic")
    _problem(harness.post(), 503, PublicMessage.REVIEWS_NOT_CONFIGURED.value)
    # A fake service reporting the same condition is mapped identically.
    fake = Harness()
    fake.service.error = ReviewsNotConfiguredError()
    _problem(fake.post(), 503, PublicMessage.REVIEWS_NOT_CONFIGURED.value)


def test_settings_are_not_read_when_the_app_is_built() -> None:
    def forbidden() -> ReviewSettings | None:
        raise AssertionError("settings must not be read at app build")

    app = create_app(review_service=DatabaseReviewService(AppDatabase(), settings_loader=forbidden))
    assert TestClient(app).get("/healthz").status_code == 200


def _configured() -> ReviewSettings:
    return ReviewSettings(review_provider=ReviewProvider.ANTHROPIC, review_model=MODEL)


def test_unknown_templates_are_422_before_any_database_work() -> None:
    service = DatabaseReviewService(AppDatabase(_forbidden_engine), settings_loader=_configured)
    harness = Harness(service)

    for template in ({"template_id": "other_review"}, {"template_version": 2}):
        response = harness.post({"vendor_id": str(harness.vendor), **template})
        body = _problem(response, 422)
        assert body["errors"] == [{"loc": ["body", "template_id"], "type": "unknown_template"}]
    fake = Harness()
    fake.service.error = UnknownReviewTemplateError()
    _problem(fake.post(), 422)


def test_pinned_artifact_failures_are_500_before_any_database_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(*args: Any) -> Any:
        raise RuntimeError(KEY_MARKER)

    monkeypatch.setattr(review_api, "load_prompt", broken)
    service = DatabaseReviewService(AppDatabase(_forbidden_engine), settings_loader=_configured)

    response = Harness(service).post()

    _problem(response, 500)
    assert KEY_MARKER not in response.text
    with pytest.raises(ReviewArtifactsUnavailableError) as info:
        review_api._pinned_configuration("vendor_security_review", 1, MODEL)
    assert info.value.__cause__ is None and info.value.__context__ is None


def test_pinned_configuration_uses_the_template_prompts_and_configured_model() -> None:
    configuration = review_api._pinned_configuration("vendor_security_review", 1, MODEL)
    template = load_template("vendor_security_review", 1)

    assert configuration.model_id == MODEL
    assert (configuration.template_id, configuration.template_version) == (
        "vendor_security_review",
        1,
    )
    assert configuration.template_sha256 == template.ref.sha256
    assert configuration.verifier_prompt.prompt_id == "verifier"
    assert configuration.analyst_prompt.prompt_id == "risk_analyst"


@pytest.mark.parametrize(
    ("error", "status", "detail"),
    [
        (EmptySnapshotError(), 409, PublicMessage.NO_ACTIVE_REVISIONS.value),
        (SnapshotNotReadyError(), 409, PublicMessage.DOCUMENTS_NOT_READY.value),
        (SnapshotBoundsError(), 422, None),
        (SnapshotInconsistentError(), 500, None),
        (ReviewConflictRetryableError(), 503, None),
    ],
)
def test_snapshot_and_conflict_errors_are_mapped(
    harness: Harness, error: Exception, status: int, detail: str | None
) -> None:
    harness.service.error = error
    _problem(harness.post(), status, detail)


def test_no_active_revisions_409(harness: Harness) -> None:
    harness.service.error = EmptySnapshotError()
    _problem(harness.post(), 409, PublicMessage.NO_ACTIVE_REVISIONS.value)


def test_documents_not_ready_409(harness: Harness) -> None:
    harness.service.error = SnapshotNotReadyError()
    _problem(harness.post(), 409, PublicMessage.DOCUMENTS_NOT_READY.value)


def test_key_reuse_with_different_body_409(harness: Harness) -> None:
    assert harness.post().status_code == 202
    other_vendor = uuid4()
    harness.service.vendors[TENANT_A].add(other_vendor)

    response = harness.post({"vendor_id": str(other_vendor)})

    _problem(response, 409, PublicMessage.IDEMPOTENCY_KEY_REUSED.value)


def test_foreign_or_missing_vendor_404(harness: Harness) -> None:
    _problem(harness.post({"vendor_id": str(uuid4())}), 404)
    _problem(harness.post(tenant=TENANT_B), 404)  # tenant A's vendor, tenant B's key


def test_commit_outcome_unknown_503(harness: Harness) -> None:
    harness.service.error = ReviewCommitOutcomeUnknownError()
    _problem(harness.post(), 503)


def test_review_limit_reached_is_429_with_retry_after(harness: Harness) -> None:
    harness.service.error = ReviewLimitReachedError()

    response = harness.post(key=KEY_MARKER)

    body = _problem(response, 429, PublicMessage.REVIEW_LIMIT_REACHED.value)
    assert response.headers["Retry-After"] == "60"
    assert KEY_MARKER not in response.text and "review_limit_reached" not in response.text
    assert set(body) == {"type", "title", "status", "detail", "request_id"}


def test_database_service_passes_the_configured_cap_to_create_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[Any] = []

    def capped(factory: Any, actor: Any, request: Any, *, max_in_flight: Any) -> Any:
        seen.append(max_in_flight)
        raise ReviewLimitReachedError()

    def settings() -> ReviewSettings:
        return ReviewSettings(
            review_provider=ReviewProvider.ANTHROPIC, review_model=MODEL, review_max_in_flight=5
        )

    monkeypatch.setattr(review_api, "create_review", capped)
    database = AppDatabase()
    monkeypatch.setattr(database, "session_factory", lambda: None)
    harness = Harness(DatabaseReviewService(database, settings_loader=settings))

    response = harness.post()

    _problem(response, 429, PublicMessage.REVIEW_LIMIT_REACHED.value)
    assert response.headers["Retry-After"] == "60"
    assert seen == [5]


# --- GET /v1/reviews/{id} and /result -------------------------------------------------------------


def test_review_detail_returns_the_pinned_configuration(harness: Harness) -> None:
    review_id = harness.post().json()["review_id"]

    response = harness.client.get(f"/v1/reviews/{review_id}", headers=harness.headers())

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == review_id and body["model_id"] == MODEL
    assert set(body) == {
        "id",
        "vendor_id",
        "job_id",
        "status",
        "captured_at",
        "template_id",
        "template_version",
        "model_id",
        "revision_ids",
        "excluded_pending",
        "snapshot_sha256",
        "configuration_sha256",
    }


def test_review_detail_404_for_other_tenant(harness: Harness) -> None:
    review_id = harness.post().json()["review_id"]

    for path in (f"/v1/reviews/{review_id}", f"/v1/reviews/{review_id}/result"):
        _problem(harness.client.get(path, headers=harness.headers(tenant=TENANT_B)), 404)
    _problem(harness.client.get(f"/v1/reviews/{uuid4()}", headers=harness.headers()), 404)
    _problem(harness.client.get("/v1/reviews/not-a-uuid", headers=harness.headers()), 422)


def test_result_409_until_completed_then_200_with_digests(harness: Harness) -> None:
    review_id = UUID(harness.post().json()["review_id"])
    path = f"/v1/reviews/{review_id}/result"

    _problem(
        harness.client.get(path, headers=harness.headers()),
        409,
        PublicMessage.RESULT_NOT_READY.value,
    )
    harness.service.results[(TENANT_A, review_id)] = ReviewResult(
        review_id=review_id,
        job_attempt=1,
        created_at=T0,
        wrapper_sha256="c" * 64,
        markdown_sha256="d" * 64,
        markdown_bytes=123,
        question_count=8,
        finding_count=2,
        unresolved_count=1,
        report={"schema": "synthetic"},
    )
    response = harness.client.get(path, headers=harness.headers())

    assert response.status_code == 200
    body = response.json()
    assert (body["wrapper_sha256"], body["markdown_sha256"]) == ("c" * 64, "d" * 64)
    assert body["report"] == {"schema": "synthetic"}
    assert (body["question_count"], body["finding_count"], body["unresolved_count"]) == (8, 2, 1)


# --- GET /v1/review-templates ---------------------------------------------------------------------


def test_review_templates_list_the_pinned_template() -> None:
    harness = Harness(DatabaseReviewService(AppDatabase(_forbidden_engine)))
    template = load_template("vendor_security_review", 1)

    response = harness.client.get("/v1/review-templates", headers=harness.headers())

    assert response.status_code == 200
    assert response.json() == [
        {
            "template_id": "vendor_security_review",
            "version": 1,
            "title": template.title,
            "question_count": 8,
            "sha256": template.ref.sha256,
        }
    ]


# --- the key is never echoed ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "error",
    [
        None,
        ReviewIdempotencyConflictError(),
        ReviewCommitOutcomeUnknownError(),
        EmptySnapshotError(),
        RuntimeError(KEY_MARKER),
    ],
)
def test_problem_bodies_never_echo_the_idempotency_key(
    harness: Harness, error: Exception | None
) -> None:
    harness.service.error = error
    for headers in (
        harness.headers(key=KEY_MARKER),
        harness.headers(key=f"{KEY_MARKER} invalid"),
        harness.headers(role=Role.ADMIN, key=KEY_MARKER),
    ):
        response = harness.client.post(
            "/v1/reviews", json={"vendor_id": str(harness.vendor)}, headers=headers
        )
        assert KEY_MARKER not in response.text
        assert all(KEY_MARKER not in value for value in response.headers.values())
