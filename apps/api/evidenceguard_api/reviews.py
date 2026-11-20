"""Review endpoints (W8, ADR-0027).

- ``POST /v1/reviews`` starts a review of one vendor with a required ``Idempotency-Key`` header:
  202 with the new review, its job and its snapshot; 200 with the original review when the same
  key is replayed with the same request.
- ``GET /v1/reviews/{review_id}`` returns the review's pinned configuration, snapshot and status.
- ``GET /v1/reviews/{review_id}/result`` returns the stored report once the review completed.
- ``GET /v1/review-templates`` lists the pinned templates a review may use.

The tenant always comes from the API key; reviewers and approvers may use these routes and
administrators get a generic 403. The request body accepts only ``vendor_id``, ``template_id`` and
``template_version``; any other field, including ``tenant_id``, is a 422. A review or vendor of
another tenant is not found (404).

**Fail closed.** Reviews are on only when ``EG_REVIEW_PROVIDER`` and ``EG_REVIEW_MODEL`` are both
set. The settings are read on every POST, never when the app is built: when they are unset,
partial or invalid, POST is a 503 (``REVIEWS_NOT_CONFIGURED``) and nothing is queued. The API never
reads the model provider key and never calls a model; the worker runs the queued job.

**Creation** loads the pinned template and both prompts through the M5c loaders before any
database work, pins the configured model id into the review's configuration digest, and creates
the review through the M5d ``create_review`` seam with the offline embedding profile, so the
review and its job commit together. Changing ``EG_REVIEW_MODEL`` changes the digest, so replaying
a key afterwards is a 409.

**Spend bound.** A tenant may have at most ``EG_REVIEW_MAX_IN_FLIGHT`` reviews (default 2) queued
or running. ``create_review`` checks the cap in the creation transaction, serialised per tenant;
over the cap POST is a 429 (``REVIEW_LIMIT_REACHED``) with ``Retry-After: 60``. A replay of an
existing key is never refused by the cap.

Routes are synchronous, so FastAPI runs them, and their database work, in a worker thread. Errors
are fixed problem responses: the idempotency key, submitted values and exception text are never
echoed or logged.
"""

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any, Protocol
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError

from evidenceguard_agents.prompts import load_prompt
from evidenceguard_agents.templates import load_template
from evidenceguard_api.auth import authenticated_actor
from evidenceguard_api.database import AppDatabase
from evidenceguard_api.problems import PublicHTTPException, PublicMessage
from evidenceguard_domain.context import ActorContext
from evidenceguard_domain.errors import PermissionDeniedError
from evidenceguard_domain.retrieval import (
    EmptySnapshotError,
    RetrievalScopeError,
    RetrievalSnapshot,
    SnapshotBoundsError,
    SnapshotInconsistentError,
    SnapshotNotReadyError,
)
from evidenceguard_domain.review_outputs import ReviewStatus
from evidenceguard_domain.reviews import (
    IDEMPOTENCY_KEY_PATTERN,
    MAX_ARTIFACT_VERSION,
    TEMPLATE_ID_PATTERN,
    InvalidReviewRequestError,
    InvalidReviewValueError,
    ReviewArtifactsUnavailableError,
    ReviewCommitOutcomeUnknownError,
    ReviewConfiguration,
    ReviewConflictRetryableError,
    ReviewDatabaseError,
    ReviewIdempotencyConflictError,
    ReviewJobConflictError,
    ReviewLimitReachedError,
    ReviewNotFoundError,
    ReviewRecordInconsistentError,
    ReviewRequest,
    TrustedReview,
)
from evidenceguard_persistence.retrieval import RETRIEVAL_ROLES
from evidenceguard_persistence.review_outputs import (
    InvalidOutputRequestError,
    ReviewOutputDatabaseError,
    ReviewOutputNotFoundError,
    ReviewOutputRecordInconsistentError,
    load_review_output,
    load_review_status,
)
from evidenceguard_persistence.reviews import create_review, load_review
from evidenceguard_persistence.settings import (
    DatabaseConfigurationError,
    ReviewConfigurationError,
    ReviewSettings,
    load_review_settings,
)
from evidenceguard_retrieval.embeddings import HASH_IDENTITY

REVIEW_ROLES = RETRIEVAL_ROLES
DEFAULT_TEMPLATE_ID = "vendor_security_review"
DEFAULT_TEMPLATE_VERSION = 1
REVIEW_TEMPLATES: tuple[tuple[str, int], ...] = ((DEFAULT_TEMPLATE_ID, DEFAULT_TEMPLATE_VERSION),)
"""The templates a review may use, each with its pinned version."""
IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"
MAX_TEMPLATE_ID_LENGTH = 32
RETRY_AFTER_SECONDS = 60
"""The ``Retry-After`` value of a 429 when the tenant's in-flight cap is reached."""

_PROBLEM: dict[str, Any] = {"application/problem+json": {}}


# --- errors raised by the service ----------------------------------------------------------------


class ReviewsNotConfiguredError(Exception):
    """Reviews are off: ``EG_REVIEW_PROVIDER`` and ``EG_REVIEW_MODEL`` are unset."""


class UnknownReviewTemplateError(Exception):
    """The template ID and version are not in ``REVIEW_TEMPLATES``."""


# --- request and response models (extra fields forbidden) ----------------------------------------


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ReviewCreate(_Model):
    """A new review. Only these three fields are accepted; the tenant cannot be supplied."""

    vendor_id: UUID
    template_id: str = Field(
        default=DEFAULT_TEMPLATE_ID,
        min_length=1,
        max_length=MAX_TEMPLATE_ID_LENGTH,
        pattern=TEMPLATE_ID_PATTERN,
        description="A template listed by GET /v1/review-templates.",
    )
    template_version: int = Field(
        default=DEFAULT_TEMPLATE_VERSION, ge=1, le=MAX_ARTIFACT_VERSION, strict=True
    )


class ExcludedPendingOut(_Model):
    count: int = Field(description="Pending or processing revisions left out of the snapshot.")
    revision_ids: list[UUID] = Field(description="At most 100, ascending.")
    truncated: bool


class ReviewAccepted(_Model):
    review_id: UUID
    job_id: UUID
    status: ReviewStatus
    revision_ids: list[UUID] = Field(description="The active revisions the review will read.")
    excluded_pending: ExcludedPendingOut


class ReviewDetail(_Model):
    id: UUID
    vendor_id: UUID
    job_id: UUID
    status: ReviewStatus
    captured_at: datetime
    template_id: str
    template_version: int
    model_id: str
    revision_ids: list[UUID]
    excluded_pending: ExcludedPendingOut
    snapshot_sha256: str
    configuration_sha256: str


class ReviewResult(_Model):
    review_id: UUID
    job_attempt: int
    created_at: datetime
    wrapper_sha256: str = Field(description="SHA-256 of the canonical report wrapper bytes.")
    markdown_sha256: str
    markdown_bytes: int
    question_count: int
    finding_count: int
    unresolved_count: int
    report: dict[str, Any] = Field(description="The canonical report wrapper, parsed.")


class TemplateSummary(_Model):
    template_id: str
    version: int
    title: str
    question_count: int
    sha256: str


@dataclass(frozen=True)
class ReviewCreated:
    """The accepted review and whether it was an idempotent replay."""

    accepted: ReviewAccepted
    replayed: bool


# --- the service ---------------------------------------------------------------------------------


class ReviewService(Protocol):
    def create(
        self,
        actor: ActorContext,
        vendor_id: UUID,
        template_id: str,
        template_version: int,
        idempotency_key: str,
    ) -> ReviewCreated: ...

    def detail(self, actor: ActorContext, review_id: UUID) -> ReviewDetail: ...

    def result(self, actor: ActorContext, review_id: UUID) -> ReviewResult: ...

    def templates(self) -> list[TemplateSummary]: ...


def _excluded(snapshot: RetrievalSnapshot) -> ExcludedPendingOut:
    exclusions = snapshot.exclusions
    return ExcludedPendingOut(
        count=exclusions.count,
        revision_ids=list(exclusions.revision_ids),
        truncated=exclusions.truncated,
    )


def _revision_ids(snapshot: RetrievalSnapshot) -> list[UUID]:
    return [binding.revision_id for binding in snapshot.bindings]


def _pinned_configuration(template_id: str, version: int, model_id: str) -> ReviewConfiguration:
    """The pinned template and prompts with the configured model. An unknown template is
    ``UnknownReviewTemplateError``; any loader failure is ``ReviewArtifactsUnavailableError``,
    raised after the handler with no cause or context."""
    if (template_id, version) not in REVIEW_TEMPLATES:
        raise UnknownReviewTemplateError()
    loaded: list[ReviewConfiguration] = []
    try:
        template = load_template(template_id, version)
        verifier, _ = load_prompt("verifier", 1)
        analyst, _ = load_prompt("risk_analyst", 1)
        loaded.append(
            ReviewConfiguration(
                template_id=template.ref.template_id,
                template_version=template.ref.version,
                template_sha256=template.ref.sha256,
                verifier_prompt=verifier.ref,
                analyst_prompt=analyst.ref,
                model_id=model_id,
            )
        )
    except Exception:  # an agents or value failure: a fixed error below
        loaded.clear()
    if not loaded:
        raise ReviewArtifactsUnavailableError()
    return loaded[0]


def _template_summaries() -> list[TemplateSummary]:
    summaries: list[TemplateSummary] = []
    try:
        for template_id, version in REVIEW_TEMPLATES:
            template = load_template(template_id, version)
            summaries.append(
                TemplateSummary(
                    template_id=template.ref.template_id,
                    version=template.ref.version,
                    title=template.title,
                    question_count=len(template.questions),
                    sha256=template.ref.sha256,
                )
            )
    except Exception:  # an agents failure: a fixed error below
        summaries.clear()
    if len(summaries) != len(REVIEW_TEMPLATES):
        raise ReviewArtifactsUnavailableError()
    return summaries


class DatabaseReviewService:
    """Review operations on the app's shared database. Settings are read on every POST."""

    def __init__(
        self,
        database: AppDatabase,
        settings_loader: Callable[[], ReviewSettings | None] = load_review_settings,
    ) -> None:
        self._database = database
        self._settings_loader = settings_loader

    def create(
        self,
        actor: ActorContext,
        vendor_id: UUID,
        template_id: str,
        template_version: int,
        idempotency_key: str,
    ) -> ReviewCreated:
        settings = self._settings_loader()
        if settings is None or settings.review_model is None:
            raise ReviewsNotConfiguredError()
        configuration = _pinned_configuration(template_id, template_version, settings.review_model)
        request = ReviewRequest(
            vendor_id=vendor_id,
            idempotency_key=idempotency_key,
            identity=HASH_IDENTITY,
            configuration=configuration,
        )
        factory = self._database.session_factory()
        created = create_review(
            factory, actor, request, max_in_flight=settings.review_max_in_flight
        )
        review = load_review(factory, actor, created.review_id)
        status = load_review_status(factory, actor, created.review_id)
        accepted = ReviewAccepted(
            review_id=review.review_id,
            job_id=review.job_id,
            status=status,
            revision_ids=_revision_ids(review.snapshot),
            excluded_pending=_excluded(review.snapshot),
        )
        return ReviewCreated(accepted=accepted, replayed=created.replayed)

    def detail(self, actor: ActorContext, review_id: UUID) -> ReviewDetail:
        factory = self._database.session_factory()
        review = load_review(factory, actor, review_id)
        status = load_review_status(factory, actor, review_id)
        return _detail(review, status)

    def result(self, actor: ActorContext, review_id: UUID) -> ReviewResult:
        stored = load_review_output(self._database.session_factory(), actor, review_id)
        output = stored.output
        return ReviewResult(
            review_id=output.review_id,
            job_attempt=stored.job_attempt,
            created_at=stored.created_at,
            wrapper_sha256=output.wrapper_sha256,
            markdown_sha256=output.markdown_sha256,
            markdown_bytes=output.markdown_bytes,
            question_count=output.question_count,
            finding_count=output.finding_count,
            unresolved_count=output.unresolved_count,
            report=json.loads(output.wrapper_canonical),
        )

    def templates(self) -> list[TemplateSummary]:
        return _template_summaries()


def _detail(review: TrustedReview, status: ReviewStatus) -> ReviewDetail:
    configuration = review.request.configuration
    return ReviewDetail(
        id=review.review_id,
        vendor_id=review.request.vendor_id,
        job_id=review.job_id,
        status=status,
        captured_at=review.snapshot.captured_at,
        template_id=configuration.template_id,
        template_version=configuration.template_version,
        model_id=configuration.model_id,
        revision_ids=_revision_ids(review.snapshot),
        excluded_pending=_excluded(review.snapshot),
        snapshot_sha256=review.snapshot.sha256,
        configuration_sha256=configuration.configuration_sha256,
    )


# --- error mapping -------------------------------------------------------------------------------

_PUBLIC_ERRORS: dict[type[Exception], tuple[int, PublicMessage]] = {
    ReviewsNotConfiguredError: (503, PublicMessage.REVIEWS_NOT_CONFIGURED),
    ReviewConfigurationError: (503, PublicMessage.REVIEWS_NOT_CONFIGURED),
    EmptySnapshotError: (409, PublicMessage.NO_ACTIVE_REVISIONS),
    SnapshotNotReadyError: (409, PublicMessage.DOCUMENTS_NOT_READY),
    ReviewIdempotencyConflictError: (409, PublicMessage.IDEMPOTENCY_KEY_REUSED),
    ReviewOutputNotFoundError: (409, PublicMessage.RESULT_NOT_READY),
}
_STATUS_ERRORS: dict[type[Exception], int] = {
    PermissionDeniedError: 403,
    RetrievalScopeError: 404,
    ReviewNotFoundError: 404,
    SnapshotBoundsError: 422,
    ReviewConflictRetryableError: 503,
    ReviewCommitOutcomeUnknownError: 503,
    ReviewDatabaseError: 503,
    ReviewOutputDatabaseError: 503,
    DatabaseConfigurationError: 503,
    ReviewRecordInconsistentError: 500,
    ReviewOutputRecordInconsistentError: 500,
    SnapshotInconsistentError: 500,
    ReviewJobConflictError: 500,
    ReviewArtifactsUnavailableError: 500,
    InvalidReviewRequestError: 500,
    InvalidReviewValueError: 500,
    InvalidOutputRequestError: 500,
}
_HANDLED: tuple[type[Exception], ...] = (
    *_PUBLIC_ERRORS,
    *_STATUS_ERRORS,
    ReviewLimitReachedError,
    UnknownReviewTemplateError,
    SQLAlchemyError,
)


def _problem(error: Exception) -> Exception:
    """The fixed HTTP error for ``error``; its text is never used."""
    if isinstance(error, ReviewLimitReachedError):
        return PublicHTTPException(
            429,
            PublicMessage.REVIEW_LIMIT_REACHED,
            headers={"Retry-After": str(RETRY_AFTER_SECONDS)},
        )
    for kind, (status, message) in _PUBLIC_ERRORS.items():
        if isinstance(error, kind):
            return PublicHTTPException(status, message)
    for kind, code in _STATUS_ERRORS.items():
        if isinstance(error, kind):
            return HTTPException(status_code=code)
    if isinstance(error, UnknownReviewTemplateError):
        return RequestValidationError(
            [{"loc": ("body", "template_id"), "type": "unknown_template"}]
        )
    return HTTPException(status_code=503)  # SQLAlchemyError: the database is unavailable


@contextmanager
def _review_errors() -> Iterator[None]:
    """Map service errors to fixed problems, raised after the handler with no context."""
    failure: Exception | None = None
    try:
        yield
    except _HANDLED as error:
        failure = _problem(error)
    if failure is not None:
        raise failure


# --- routes --------------------------------------------------------------------------------------


def review_actor(
    actor: Annotated[ActorContext, Depends(authenticated_actor)],
) -> ActorContext:
    """Authenticated (401 otherwise) and allowed to use reviews (generic 403 otherwise)."""
    if actor.role not in REVIEW_ROLES:
        raise HTTPException(status_code=403)
    return actor


def _service(request: Request) -> ReviewService:
    service: ReviewService = request.app.state.review_service
    return service


router = APIRouter(
    tags=["reviews"],
    responses={
        401: {
            "description": "Missing, malformed, unknown or revoked credentials.",
            "content": _PROBLEM,
        },
        403: {"description": "The caller's role may not use reviews.", "content": _PROBLEM},
        500: {"description": "Stored review data failed its checks.", "content": _PROBLEM},
        503: {"description": "The database is unavailable.", "content": _PROBLEM},
    },
)


@router.post(
    "/v1/reviews",
    status_code=202,
    response_model=ReviewAccepted,
    summary="Start a review",
    description=(
        "Captures the vendor's active revisions and queues a review with the pinned template "
        "and prompts and the configured model. 202 for a new review; 200 with the original "
        "review when the same Idempotency-Key is replayed with the same request. The tenant "
        "cannot be supplied. A tenant may have a limited number of reviews queued or running; "
        "over that limit a new review is a 429, while a replay is still answered."
    ),
    responses={
        200: {"description": "Replay of an earlier request.", "model": ReviewAccepted},
        404: {"description": "No such vendor in the caller's tenant.", "content": _PROBLEM},
        409: {
            "description": (
                "No active revisions, documents not ready, or the key was used for a "
                "different request."
            ),
            "content": _PROBLEM,
        },
        422: {
            "description": "Invalid or missing key, fields or template, or too many revisions.",
            "content": _PROBLEM,
        },
        429: {
            "description": "The tenant already has the allowed number of reviews in progress.",
            "content": _PROBLEM,
            "headers": {
                "Retry-After": {
                    "description": "Seconds to wait before trying again.",
                    "schema": {"type": "integer"},
                }
            },
        },
        503: {
            "description": "Reviews are not configured, or the database is unavailable.",
            "content": _PROBLEM,
        },
    },
)
def create(
    body: ReviewCreate,
    request: Request,
    response: Response,
    actor: Annotated[ActorContext, Depends(review_actor)],
    idempotency_key: Annotated[
        str,
        Header(
            alias=IDEMPOTENCY_KEY_HEADER,
            pattern=IDEMPOTENCY_KEY_PATTERN,
            description="1 to 128 characters: letters, digits, '.', '_', ':' or '-'.",
        ),
    ],
) -> ReviewAccepted:
    with _review_errors():
        created = _service(request).create(
            actor, body.vendor_id, body.template_id, body.template_version, idempotency_key
        )
    response.status_code = 200 if created.replayed else 202
    return created.accepted


@router.get(
    "/v1/reviews/{review_id}",
    response_model=ReviewDetail,
    summary="Get a review",
    description="A review's pinned configuration, snapshot and status.",
    responses={
        404: {"description": "No such review in the caller's tenant.", "content": _PROBLEM},
        422: {"description": "The ID is not a UUID.", "content": _PROBLEM},
    },
)
def get_review(
    review_id: UUID,
    request: Request,
    actor: Annotated[ActorContext, Depends(review_actor)],
) -> ReviewDetail:
    with _review_errors():
        return _service(request).detail(actor, review_id)


@router.get(
    "/v1/reviews/{review_id}/result",
    response_model=ReviewResult,
    summary="Get a review's result",
    description="The stored report of a completed review, with its digests.",
    responses={
        404: {"description": "No such review in the caller's tenant.", "content": _PROBLEM},
        409: {"description": "The review has not completed.", "content": _PROBLEM},
        422: {"description": "The ID is not a UUID.", "content": _PROBLEM},
    },
)
def get_result(
    review_id: UUID,
    request: Request,
    actor: Annotated[ActorContext, Depends(review_actor)],
) -> ReviewResult:
    with _review_errors():
        return _service(request).result(actor, review_id)


@router.get(
    "/v1/review-templates",
    response_model=list[TemplateSummary],
    summary="List review templates",
    description="The pinned templates a review may use.",
)
def list_templates(
    request: Request,
    actor: Annotated[ActorContext, Depends(review_actor)],
) -> list[TemplateSummary]:
    with _review_errors():
        return _service(request).templates()
