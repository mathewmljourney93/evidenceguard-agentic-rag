"""Review-creation values, canonical identity and fixed errors (M5d, ADR-0022).

Implements the accepted M5d specification (``docs/plan.md``, M5d-A1 and M5d-E): the pinned
``ReviewConfiguration``, the tenant-free ``ReviewRequest`` whose digest takes the tenant
explicitly, and the ``CreatedReview`` and ``TrustedReview`` results, with the
``eg-review-configuration-v1`` and ``eg-review-request-v1`` canonical encodings.

Every value is a frozen dataclass with a validating keyword-only constructor: exact types (a
``bool`` is never an ``int``), unknown keywords rejected, nested values rebuilt through their own
constructors, ``dataclasses.replace`` running the same constructor, and representations that show
identifiers, versions, counts and digests only (never the idempotency key). Construction failures
are a fresh ``InvalidReviewValueError`` raised after leaving the handler, with no cause or context;
process control propagates as the same object. Nothing here logs, touches a database or proves
that a value came from one.
"""

import hashlib
import json
import re
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, ClassVar
from uuid import UUID

from evidenceguard_domain.embedding_storage import require_storable_identity
from evidenceguard_domain.embeddings import EmbeddingIdentity
from evidenceguard_domain.model_calls import (
    DEFAULT_TIMEOUT_MS,
    MAX_OUTPUT_TOKENS,
    MAX_TIMEOUT_MS,
    MIN_TIMEOUT_MS,
    PromptRef,
    is_model_id,
)
from evidenceguard_domain.retrieval import (
    MAX_K,
    RETRIEVAL_CONFIG_V1,
    RetrievalConfig,
    RetrievalSnapshot,
    revalidate_snapshot,
)

CONFIGURATION_CANONICAL = "eg-review-configuration-v1"
REQUEST_CANONICAL = "eg-review-request-v1"
REVIEW_JOB_KIND = "run_review"
REVIEW_JOB_MAX_ATTEMPTS = 3
DEFAULT_MAX_OUTPUT_TOKENS = 4_096
DEFAULT_RETRIEVAL_K = 8
MAX_ARTIFACT_VERSION = 999

TEMPLATE_ID_PATTERN = r"^[a-z][a-z0-9_]{0,31}$"
IDEMPOTENCY_KEY_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
_TEMPLATE_ID = re.compile(TEMPLATE_ID_PATTERN, re.ASCII)
_IDEMPOTENCY_KEY = re.compile(IDEMPOTENCY_KEY_PATTERN, re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}", re.ASCII)


# --- errors (fixed messages: the message is the code) ------------------------------------------


class ReviewError(Exception):
    """Base of the fixed M5d errors. Never carries submitted values, keys, content or causes."""

    code: ClassVar[str] = "review_error"

    def __init__(self) -> None:
        super().__init__(self.code)


class InvalidReviewRequestError(ReviewError):
    """Invalid seam arguments: actor type, request, review ID or tenant parameter."""

    code = "invalid_review_request"


class InvalidReviewValueError(ReviewError):
    """Invalid construction or replacement of an M5d value."""

    code = "invalid_review_value"


class ReviewIdempotencyConflictError(ReviewError):
    """The idempotency key exists for the tenant with a different request digest."""

    code = "review_idempotency_conflict"


class ReviewJobConflictError(ReviewError):
    """An existing or unexpected ``run_review`` job for a new review (never retried)."""

    code = "review_job_conflict"


class ReviewConflictRetryableError(ReviewError):
    """An already classified retryable failure after three attempts, or whose normal rollback or
    close failed; a later fresh call may succeed."""

    code = "review_conflict_retryable"


class ReviewCommitOutcomeUnknownError(ReviewError):
    """``COMMIT`` failed without a recognized retryable rejection: creation may or may not have
    happened. Never retried automatically; a replay with the same key discovers the result."""

    code = "review_commit_outcome_unknown"


class ReviewDatabaseError(ReviewError):
    """Any other database or session failure (including a statement timeout)."""

    code = "review_database_error"


class ReviewNotFoundError(ReviewError):
    """No review with that ID for the actor's tenant (also another tenant's ID)."""

    code = "review_not_found"


class ReviewRecordInconsistentError(ReviewError):
    """Stored review rows or the job association fail reconstruction or comparison."""

    code = "review_record_inconsistent"


class ReviewArtifactsUnavailableError(ReviewError):
    """A pinned template or prompt is unknown or fails its integrity check."""

    code = "review_artifacts_unavailable"


# --- helpers -------------------------------------------------------------------------------------


class _Invalid(Exception):
    """Private: a failed check inside a guarded operation."""


def _require(condition: bool) -> None:
    if not condition:
        raise _Invalid


def _run[T](build: Callable[[], T], error: type[ReviewError]) -> T:
    """Run one whole operation; any ordinary failure becomes a fresh ``error`` raised after the
    handler (no cause or context). Process control propagates as the same object."""
    built: list[T] = []
    with suppress(Exception):
        built.append(build())
    if not built:
        raise error()
    return built[0]


def _is_int(value: object, low: int, high: int) -> bool:
    return type(value) is int and low <= value <= high


def _is_sha256(value: object) -> bool:
    return type(value) is str and _SHA256.fullmatch(value) is not None


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    """The retrieval canonical form: sorted keys, compact separators, ASCII, no NaN."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def _rebuilt_prompt(value: object) -> PromptRef:
    _require(type(value) is PromptRef)
    assert isinstance(value, PromptRef)
    return PromptRef(prompt_id=value.prompt_id, version=value.version, sha256=value.sha256)


def _rebuilt_identity(value: object) -> EmbeddingIdentity:
    _require(type(value) is EmbeddingIdentity)
    assert isinstance(value, EmbeddingIdentity)
    return require_storable_identity(value)


def _checked_config(value: object) -> RetrievalConfig:
    """Only ``RETRIEVAL_CONFIG_V1`` is accepted; the canonical instance is stored."""
    _require(type(value) is RetrievalConfig and value == RETRIEVAL_CONFIG_V1)
    return RETRIEVAL_CONFIG_V1


def _utc(value: object) -> datetime:
    _require(type(value) is datetime)
    assert isinstance(value, datetime)
    _require(value.tzinfo is not None and value.utcoffset() is not None)
    return value.astimezone(UTC)


# --- values --------------------------------------------------------------------------------------


@dataclass(frozen=True, init=False, repr=False)
class ReviewConfiguration:
    """The pinned template, prompts, model settings and planner ``k`` of a review. It cannot
    prove that the references name registered, loadable artifacts."""

    template_id: str
    template_version: int
    template_sha256: str
    verifier_prompt: PromptRef
    analyst_prompt: PromptRef
    model_id: str
    max_output_tokens: int
    timeout_ms: int
    retrieval_k: int
    configuration_sha256: str = field(init=False)

    def __init__(
        self,
        *,
        template_id: str,
        template_version: int,
        template_sha256: str,
        verifier_prompt: PromptRef,
        analyst_prompt: PromptRef,
        model_id: str,
        max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        retrieval_k: int = DEFAULT_RETRIEVAL_K,
        **unknown: object,
    ) -> None:
        def build() -> None:
            _require(not unknown)
            _require(type(template_id) is str and _TEMPLATE_ID.fullmatch(template_id) is not None)
            _require(_is_int(template_version, 1, MAX_ARTIFACT_VERSION))
            _require(_is_sha256(template_sha256))
            verifier = _rebuilt_prompt(verifier_prompt)
            analyst = _rebuilt_prompt(analyst_prompt)
            _require(verifier.prompt_id != analyst.prompt_id)
            _require(type(model_id) is str and is_model_id(model_id))
            _require(_is_int(max_output_tokens, 1, MAX_OUTPUT_TOKENS))
            _require(_is_int(timeout_ms, MIN_TIMEOUT_MS, MAX_TIMEOUT_MS))
            _require(_is_int(retrieval_k, 1, MAX_K))
            object.__setattr__(self, "template_id", template_id)
            object.__setattr__(self, "template_version", template_version)
            object.__setattr__(self, "template_sha256", template_sha256)
            object.__setattr__(self, "verifier_prompt", verifier)
            object.__setattr__(self, "analyst_prompt", analyst)
            object.__setattr__(self, "model_id", model_id)
            object.__setattr__(self, "max_output_tokens", max_output_tokens)
            object.__setattr__(self, "timeout_ms", timeout_ms)
            object.__setattr__(self, "retrieval_k", retrieval_k)
            object.__setattr__(
                self, "configuration_sha256", hashlib.sha256(self.canonical_bytes()).hexdigest()
            )

        _run(build, InvalidReviewValueError)

    def canonical_object(self) -> dict[str, Any]:
        def ref(prompt: PromptRef) -> dict[str, Any]:
            return {"id": prompt.prompt_id, "sha256": prompt.sha256, "version": prompt.version}

        return {
            "analyst_prompt": ref(self.analyst_prompt),
            "canonical": CONFIGURATION_CANONICAL,
            "kind": "review_configuration",
            "model": {
                "max_output_tokens": self.max_output_tokens,
                "model_id": self.model_id,
                "timeout_ms": self.timeout_ms,
            },
            "retrieval_k": self.retrieval_k,
            "template": {
                "id": self.template_id,
                "sha256": self.template_sha256,
                "version": self.template_version,
            },
            "verifier_prompt": ref(self.verifier_prompt),
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.canonical_object())

    def __repr__(self) -> str:
        return (
            f"ReviewConfiguration(template_id={self.template_id!r}, "
            f"template_version={self.template_version}, model_id={self.model_id!r}, "
            f"configuration_sha256={self.configuration_sha256!r})"
        )

    __str__ = __repr__


def _rebuilt_configuration(value: object) -> ReviewConfiguration:
    _require(type(value) is ReviewConfiguration)
    assert isinstance(value, ReviewConfiguration)
    return ReviewConfiguration(
        template_id=value.template_id,
        template_version=value.template_version,
        template_sha256=value.template_sha256,
        verifier_prompt=value.verifier_prompt,
        analyst_prompt=value.analyst_prompt,
        model_id=value.model_id,
        max_output_tokens=value.max_output_tokens,
        timeout_ms=value.timeout_ms,
        retrieval_k=value.retrieval_k,
    )


@dataclass(frozen=True, init=False, repr=False)
class ReviewRequest:
    """A tenant-free review-creation request. Its digest takes the tenant explicitly
    (``request_sha256``); it cannot prove that the vendor belongs to any tenant."""

    vendor_id: UUID
    idempotency_key: str
    identity: EmbeddingIdentity
    config: RetrievalConfig
    configuration: ReviewConfiguration

    def __init__(
        self,
        *,
        vendor_id: UUID,
        idempotency_key: str,
        identity: EmbeddingIdentity,
        configuration: ReviewConfiguration,
        config: RetrievalConfig = RETRIEVAL_CONFIG_V1,
        **unknown: object,
    ) -> None:
        def build() -> None:
            _require(not unknown and type(vendor_id) is UUID)
            _require(type(idempotency_key) is str)
            _require(_IDEMPOTENCY_KEY.fullmatch(idempotency_key) is not None)
            checked_identity = _rebuilt_identity(identity)
            checked_config = _checked_config(config)
            checked_configuration = _rebuilt_configuration(configuration)
            object.__setattr__(self, "vendor_id", vendor_id)
            object.__setattr__(self, "idempotency_key", idempotency_key)
            object.__setattr__(self, "identity", checked_identity)
            object.__setattr__(self, "config", checked_config)
            object.__setattr__(self, "configuration", checked_configuration)

        _run(build, InvalidReviewValueError)

    def __repr__(self) -> str:
        return (
            f"ReviewRequest(vendor_id={self.vendor_id}, "
            f"profile={self.identity.fingerprint[:12]!r}, "
            f"configuration_sha256={self.configuration.configuration_sha256!r})"
        )

    __str__ = __repr__


def _rebuilt_request(value: object) -> ReviewRequest:
    _require(type(value) is ReviewRequest)
    assert isinstance(value, ReviewRequest)
    return ReviewRequest(
        vendor_id=value.vendor_id,
        idempotency_key=value.idempotency_key,
        identity=value.identity,
        config=value.config,
        configuration=value.configuration,
    )


def rebuilt_request(value: object) -> ReviewRequest:
    """Revalidate a supplied request; any failure is ``InvalidReviewRequestError``."""
    return _run(lambda: _rebuilt_request(value), InvalidReviewRequestError)


def request_canonical_object(request: ReviewRequest, *, tenant_id: UUID) -> dict[str, Any]:
    """The ``eg-review-request-v1`` object for ``request`` under ``tenant_id``. A non-``UUID``
    tenant or an invalid request is ``InvalidReviewRequestError``."""

    def build() -> dict[str, Any]:
        _require(type(tenant_id) is UUID)
        checked = _rebuilt_request(request)
        identity = checked.identity
        return {
            "canonical": REQUEST_CANONICAL,
            "configuration_sha256": checked.configuration.configuration_sha256,
            "embedding_profile": {
                "algorithm_version": identity.algorithm_version,
                "dims": identity.dims,
                "fingerprint": identity.fingerprint,
                "model_id": identity.model_id,
                "normalization": identity.normalization,
                "provider_id": identity.provider_id,
            },
            "idempotency_key": checked.idempotency_key,
            "kind": "review_request",
            "retrieval_config": {
                "config_sha256": checked.config.config_sha256,
                "version": checked.config.version,
            },
            "tenant_id": str(tenant_id),
            "vendor_id": str(checked.vendor_id),
        }

    return _run(build, InvalidReviewRequestError)


def request_canonical_bytes(request: ReviewRequest, *, tenant_id: UUID) -> bytes:
    return _canonical_bytes(request_canonical_object(request, tenant_id=tenant_id))


def request_sha256(request: ReviewRequest, *, tenant_id: UUID) -> str:
    """The request digest bound to ``tenant_id`` (taken only from a validated actor)."""
    return hashlib.sha256(request_canonical_bytes(request, tenant_id=tenant_id)).hexdigest()


@dataclass(frozen=True, init=False, repr=False)
class CreatedReview:
    """The result of a creation or a matching replay. It cannot prove that the review was
    committed or that it matches any database row."""

    review_id: UUID
    tenant_id: UUID
    vendor_id: UUID
    request_sha256: str
    snapshot_sha256: str
    configuration_sha256: str
    captured_at: datetime
    job_id: UUID
    replayed: bool

    def __init__(
        self,
        *,
        review_id: UUID,
        tenant_id: UUID,
        vendor_id: UUID,
        request_sha256: str,
        snapshot_sha256: str,
        configuration_sha256: str,
        captured_at: datetime,
        job_id: UUID,
        replayed: bool,
        **unknown: object,
    ) -> None:
        def build() -> None:
            _require(not unknown)
            _require(all(type(v) is UUID for v in (review_id, tenant_id, vendor_id, job_id)))
            _require(all(map(_is_sha256, (request_sha256, snapshot_sha256, configuration_sha256))))
            stamp = _utc(captured_at)
            _require(type(replayed) is bool)
            object.__setattr__(self, "review_id", review_id)
            object.__setattr__(self, "tenant_id", tenant_id)
            object.__setattr__(self, "vendor_id", vendor_id)
            object.__setattr__(self, "request_sha256", request_sha256)
            object.__setattr__(self, "snapshot_sha256", snapshot_sha256)
            object.__setattr__(self, "configuration_sha256", configuration_sha256)
            object.__setattr__(self, "captured_at", stamp)
            object.__setattr__(self, "job_id", job_id)
            object.__setattr__(self, "replayed", replayed)

        _run(build, InvalidReviewValueError)

    def __repr__(self) -> str:
        return (
            f"CreatedReview(review_id={self.review_id}, job_id={self.job_id}, "
            f"replayed={self.replayed}, snapshot_sha256={self.snapshot_sha256!r})"
        )

    __str__ = __repr__


@dataclass(frozen=True, init=False, repr=False)
class TrustedReview:
    """A review rebuilt from stored rows. The constructor checks consistency only; it cannot
    prove that the values came from the database or that the rows are authentic (only
    ``load_review`` builds it from rows)."""

    review_id: UUID
    tenant_id: UUID
    request: ReviewRequest
    request_sha256: str
    snapshot: RetrievalSnapshot
    job_id: UUID

    def __init__(
        self,
        *,
        review_id: UUID,
        tenant_id: UUID,
        request: ReviewRequest,
        request_sha256: str,
        snapshot: RetrievalSnapshot,
        job_id: UUID,
        **unknown: object,
    ) -> None:
        def build() -> None:
            _require(not unknown)
            _require(all(type(v) is UUID for v in (review_id, tenant_id, job_id)))
            checked_request = _rebuilt_request(request)
            _require(_is_sha256(request_sha256))
            expected = hashlib.sha256(
                _canonical_bytes(request_canonical_object(checked_request, tenant_id=tenant_id))
            ).hexdigest()
            _require(request_sha256 == expected)
            checked_snapshot = revalidate_snapshot(snapshot)
            _require(checked_snapshot.tenant_id == tenant_id)
            _require(checked_snapshot.vendor_id == checked_request.vendor_id)
            _require(checked_snapshot.identity == checked_request.identity)
            _require(checked_snapshot.config == checked_request.config)
            object.__setattr__(self, "review_id", review_id)
            object.__setattr__(self, "tenant_id", tenant_id)
            object.__setattr__(self, "request", checked_request)
            object.__setattr__(self, "request_sha256", request_sha256)
            object.__setattr__(self, "snapshot", checked_snapshot)
            object.__setattr__(self, "job_id", job_id)

        _run(build, InvalidReviewValueError)

    def __repr__(self) -> str:
        return (
            f"TrustedReview(review_id={self.review_id}, job_id={self.job_id}, "
            f"bindings={len(self.snapshot.bindings)}, snapshot_sha256={self.snapshot.sha256!r})"
        )

    __str__ = __repr__
