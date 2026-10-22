"""Atomic review creation and trusted reload (M5d, ADR-0022).

Both seams are **trusted internal programming interfaces**: no endpoint, command, production
worker path or handler calls them (W8). The tenant comes only from the validated
``ActorContext``, whose role must be reviewer or approver.

**Creation** (``create_review``) runs at most three attempts. Each attempt is one fresh session
and transaction: ``SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ WRITE`` first, then the
single ``SELECT clock_timestamp()`` that establishes the MVCC snapshot (its value is recorded as
``captured_at``; it is not an ordering proof), transaction-local statement and lock timeouts, the
replay lookup by ``(tenant_id, idempotency_key)``, ``capture_in_transaction``, a fresh review ID,
the ``run_review`` job (enqueued and validated before the review insert), the review, its
bindings and exclusions, then ``COMMIT``. Everything commits together or not at all.

**Commit state and cleanup** (the accepted M5d-B1 contract with the Prompt 188 clarification).
Each attempt tracks ``not_entered``, ``entered``, ``rejected`` or ``committed`` independently of
any exception in flight. During ``COMMIT`` only exactly ``40001`` or ``40P01`` is a recognized
retryable rejection; every other ordinary ``COMMIT`` failure is an unknown outcome
(``ReviewCommitOutcomeUnknownError``) and is never retried automatically. Cleanup calls each of
``rollback``, ``close`` and ``invalidate`` at most once: after ``not_entered`` or ``rejected``,
``rollback`` then (only if it returned) ``close``, with one fallback ``invalidate`` if either
raised; after ``entered``, ``invalidate`` only; after ``committed``, ``close`` with one fallback
``invalidate``. An automatic retry happens only when the normal ``rollback`` and ``close`` both
returned; a later successful ``invalidate`` never restores it. ``Session.invalidate`` reaches only
connections still associated with the session's transaction, so its normal return does not prove
that the original connection was invalidated: no physical disposal or pool quarantine is claimed.

**Process control** (``BaseException`` that is not ``Exception``): the first object observed in an
attempt stays primary, is re-raised as the same object after bounded best-effort cleanup, and no
further attempt runs; later ordinary or process-control failures during cleanup are suppressed.

**Reload** (``load_review``) runs one transaction through the public ``read_snapshot`` helper with
its own failure boundary, rebuilds every stored value through its constructor, recomputes the
snapshot, profile, configuration and request digests and validates the job association.

Errors are the fixed ``evidenceguard_domain.reviews`` errors (and the unchanged M4d capture errors
for semantic capture outcomes), raised fresh after leaving every handler with no cause or context.
No raw exception, SQL, parameter or idempotency key is retained. Nothing retries without a fresh
transaction, nothing sleeps and nothing logs. Per-statement and lock timeouts bound individual
waits only; there is no end-to-end deadline.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import Table, func, insert, select, text
from sqlalchemy.orm import Session, sessionmaker

from evidenceguard_domain.context import ActorContext
from evidenceguard_domain.embedding_storage import profile_id
from evidenceguard_domain.embeddings import EmbeddingIdentity
from evidenceguard_domain.errors import PermissionDeniedError
from evidenceguard_domain.jobs import (
    JobIdempotencyConflictError,
    JobPayload,
    JobSnapshot,
    JobStatus,
)
from evidenceguard_domain.model_calls import PromptRef
from evidenceguard_domain.retrieval import (
    RETRIEVAL_CONFIG_V1,
    EmptySnapshotError,
    PendingExclusions,
    RetrievalError,
    RetrievalScopeError,
    RetrievalSnapshot,
    RevisionBinding,
    SnapshotBoundsError,
    SnapshotInconsistentError,
    SnapshotNotReadyError,
)
from evidenceguard_domain.reviews import (
    REVIEW_JOB_KIND,
    REVIEW_JOB_MAX_ATTEMPTS,
    CreatedReview,
    InvalidReviewRequestError,
    ReviewCommitOutcomeUnknownError,
    ReviewConfiguration,
    ReviewConflictRetryableError,
    ReviewDatabaseError,
    ReviewIdempotencyConflictError,
    ReviewJobConflictError,
    ReviewNotFoundError,
    ReviewRecordInconsistentError,
    ReviewRequest,
    TrustedReview,
    rebuilt_request,
    request_sha256,
)
from evidenceguard_persistence import jobs as job_store
from evidenceguard_persistence.database_failures import (
    RETRYABLE_CATEGORIES,
    CommitFailureResolution,
    classify_commit_failure,
    classify_database_failure,
)
from evidenceguard_persistence.document_views import read_snapshot
from evidenceguard_persistence.models import Review, ReviewBinding, ReviewExcludedRevision
from evidenceguard_persistence.retrieval import (
    RETRIEVAL_ROLES,
    CaptureFailure,
    SemanticOutcome,
    capture_in_transaction,
)

REVIEWS = cast(Table, Review.__table__)
REVIEW_BINDINGS = cast(Table, ReviewBinding.__table__)
REVIEW_EXCLUSIONS = cast(Table, ReviewExcludedRevision.__table__)

CREATE_TRANSACTION_SQL = "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ WRITE"
STATEMENT_TIMEOUT_MS = 30_000
LOCK_TIMEOUT_MS = 5_000
MAX_CREATION_ATTEMPTS = 3

_SEMANTIC_ERRORS: dict[str, type[RetrievalError]] = {
    error.code: error
    for error in (
        RetrievalScopeError,
        EmptySnapshotError,
        SnapshotBoundsError,
        SnapshotInconsistentError,
        SnapshotNotReadyError,
    )
}


class CommitState(StrEnum):
    NOT_ENTERED = "not_entered"
    ENTERED = "entered"
    REJECTED = "rejected"
    COMMITTED = "committed"


class _Refusal(Exception):
    """Private: a fixed refusal decided by this module's own checks (never a database error)."""

    def __init__(self, error: type[Exception]) -> None:
        super().__init__()
        self.error = error


def _refuse(error: type[Exception]) -> _Refusal:
    return _Refusal(error)


def _require(condition: bool, error: type[Exception]) -> None:
    if not condition:
        raise _refuse(error)


# --- validation (pure; before any database work) -------------------------------------------------


def _checked_actor(actor: object) -> ActorContext:
    if type(actor) is not ActorContext:
        raise InvalidReviewRequestError()
    assert isinstance(actor, ActorContext)
    return actor


def _require_role(actor: ActorContext) -> None:
    if actor.role not in RETRIEVAL_ROLES:
        raise PermissionDeniedError()


# --- creation steps (module functions so the control flow can be tested with fakes) -----------


def _begin(session: Session) -> datetime:
    """Steps 1-3: isolation first, the snapshot-establishing clock read, then the timeouts."""
    session.execute(text(CREATE_TRANSACTION_SQL))
    captured_at: datetime = session.execute(select(func.clock_timestamp())).scalar_one()
    session.execute(text(f"SET LOCAL statement_timeout = {int(STATEMENT_TIMEOUT_MS)}"))
    session.execute(text(f"SET LOCAL lock_timeout = {int(LOCK_TIMEOUT_MS)}"))
    return captured_at


def _valid_job(job: Any, tenant_id: UUID, review_id: UUID) -> bool:
    """The stored association of a review with its ``run_review`` job; lifecycle fields
    (status, attempt, lease, error) may be anything."""
    return bool(
        job is not None
        and job.tenant_id == tenant_id
        and job.kind == REVIEW_JOB_KIND
        and job.idempotency_key == str(review_id)
        and job.payload == {"review_id": str(review_id)}
        and job.max_attempts == REVIEW_JOB_MAX_ATTEMPTS
    )


def _job_row(session: Session, tenant_id: UUID, job_id: UUID) -> Any:
    return session.execute(
        select(job_store.JOBS).where(
            job_store.JOBS.c.tenant_id == tenant_id, job_store.JOBS.c.id == job_id
        )
    ).first()


def _replay(
    session: Session, tenant_id: UUID, request: ReviewRequest, digest: str
) -> CreatedReview | None:
    """Step 4: a visible review with this key is a matching replay (returned with
    ``replayed=True``) or an idempotency conflict. Nothing is written."""
    row = session.execute(
        select(REVIEWS).where(
            REVIEWS.c.tenant_id == tenant_id,
            REVIEWS.c.idempotency_key == request.idempotency_key,
        )
    ).first()
    if row is None:
        return None
    _require(row.request_sha256 == digest, ReviewIdempotencyConflictError)
    job = _job_row(session, tenant_id, row.run_review_job_id)
    _require(_valid_job(job, tenant_id, row.id), ReviewRecordInconsistentError)
    built: list[CreatedReview] = []
    with suppress(Exception):
        built.append(
            CreatedReview(
                review_id=row.id,
                tenant_id=tenant_id,
                vendor_id=row.vendor_id,
                request_sha256=row.request_sha256,
                snapshot_sha256=row.snapshot_sha256,
                configuration_sha256=row.configuration_sha256,
                captured_at=row.captured_at,
                job_id=row.run_review_job_id,
                replayed=True,
            )
        )
    _require(bool(built), ReviewRecordInconsistentError)
    return built[0]


def _create_job(session: Session, actor: ActorContext, review_id: UUID) -> JobSnapshot:
    """Step 6: refuse an already visible job for the new key, enqueue, and require exactly the
    expected new queued job."""
    key = str(review_id)
    existing = session.execute(
        select(job_store.JOBS.c.id).where(
            job_store.JOBS.c.tenant_id == actor.tenant_id,
            job_store.JOBS.c.kind == REVIEW_JOB_KIND,
            job_store.JOBS.c.idempotency_key == key,
        )
    ).first()
    _require(existing is None, ReviewJobConflictError)
    refused = False
    job: JobSnapshot | None = None
    try:
        job = job_store.enqueue(
            session,
            actor,
            kind=REVIEW_JOB_KIND,
            idempotency_key=key,
            payload=JobPayload.from_mapping({"review_id": key}),
            max_attempts=REVIEW_JOB_MAX_ATTEMPTS,
        )
    except (JobIdempotencyConflictError, job_store.JobEnqueueRaceError):
        refused = True
    _require(not refused and job is not None, ReviewJobConflictError)
    assert job is not None
    _require(
        job.tenant_id == actor.tenant_id
        and job.kind == REVIEW_JOB_KIND
        and job.idempotency_key == key
        and job.payload.as_dict() == {"review_id": key}
        and job.max_attempts == REVIEW_JOB_MAX_ATTEMPTS
        and job.status is JobStatus.QUEUED
        and job.attempt == 0,
        ReviewJobConflictError,
    )
    return job


def _insert(
    session: Session,
    *,
    tenant_id: UUID,
    review_id: UUID,
    request: ReviewRequest,
    digest: str,
    snapshot: RetrievalSnapshot,
    job_id: UUID,
) -> None:
    """Step 7: the review row (plain insert, no ``ON CONFLICT``), then its bindings in snapshot
    order and its listed excluded revisions."""
    configuration = request.configuration
    identity = request.identity
    session.execute(
        insert(REVIEWS).values(
            id=review_id,
            tenant_id=tenant_id,
            vendor_id=request.vendor_id,
            idempotency_key=request.idempotency_key,
            request_sha256=digest,
            configuration_sha256=configuration.configuration_sha256,
            snapshot_sha256=snapshot.sha256,
            captured_at=snapshot.captured_at,
            provider_id=identity.provider_id,
            embedding_model_id=identity.model_id,
            algorithm_version=identity.algorithm_version,
            dims=identity.dims,
            normalization=identity.normalization,
            fingerprint=identity.fingerprint,
            profile_id=snapshot.profile_id,
            retrieval_config_version=request.config.version,
            retrieval_config_sha256=request.config.config_sha256,
            exclusion_count=snapshot.exclusions.count,
            exclusions_truncated=snapshot.exclusions.truncated,
            template_id=configuration.template_id,
            template_version=configuration.template_version,
            template_sha256=configuration.template_sha256,
            verifier_prompt_id=configuration.verifier_prompt.prompt_id,
            verifier_prompt_version=configuration.verifier_prompt.version,
            verifier_prompt_sha256=configuration.verifier_prompt.sha256,
            analyst_prompt_id=configuration.analyst_prompt.prompt_id,
            analyst_prompt_version=configuration.analyst_prompt.version,
            analyst_prompt_sha256=configuration.analyst_prompt.sha256,
            model_id=configuration.model_id,
            max_output_tokens=configuration.max_output_tokens,
            timeout_ms=configuration.timeout_ms,
            retrieval_k=configuration.retrieval_k,
            run_review_job_id=job_id,
        )
    )
    session.execute(
        insert(REVIEW_BINDINGS),
        [
            {
                "tenant_id": tenant_id,
                "review_id": review_id,
                "ordinal": ordinal,
                "revision_id": binding.revision_id,
                "document_id": binding.document_id,
                "index_id": binding.index_id,
                "chunker_version": binding.chunker_version,
                "chunk_count": binding.chunk_count,
                "manifest_sha256": binding.manifest_sha256,
                "vector_manifest_sha256": binding.vector_manifest_sha256,
            }
            for ordinal, binding in enumerate(snapshot.bindings)
        ],
    )
    if snapshot.exclusions.revision_ids:
        session.execute(
            insert(REVIEW_EXCLUSIONS),
            [
                {"tenant_id": tenant_id, "review_id": review_id, "revision_id": revision}
                for revision in snapshot.exclusions.revision_ids
            ],
        )


# --- one attempt ---------------------------------------------------------------------------------


@dataclass
class _Attempt:
    """The outcome of one creation attempt, decided before cleanup and never changed by it."""

    state: CommitState = CommitState.NOT_ENTERED
    result: CreatedReview | None = None
    error: type[Exception] | None = None
    retryable: bool = False
    normal_cleanup: bool = False
    control: BaseException | None = field(default=None, repr=False)

    def record_control(self, control: BaseException) -> None:
        if self.control is None:  # the first process-control object stays primary
            self.control = control


def _run_body(
    attempt: _Attempt,
    session: Session,
    actor: ActorContext,
    request: ReviewRequest,
    digest: str,
) -> None:
    """Steps 1-8 of one attempt. Records its result, error or retryability on ``attempt``."""
    captured_at = _begin(session)
    replay = _replay(session, actor.tenant_id, request, digest)
    if replay is not None:
        attempt.result = replay
        return
    outcome = capture_in_transaction(
        session,
        captured_at,
        actor,
        vendor_id=request.vendor_id,
        identity=request.identity,
        config=request.config,
    )
    if isinstance(outcome, SemanticOutcome):
        attempt.error = _SEMANTIC_ERRORS[outcome.code]
        return
    if isinstance(outcome, CaptureFailure):
        if outcome.category in RETRYABLE_CATEGORIES:
            attempt.retryable = True
        else:
            attempt.error = ReviewDatabaseError
        return
    snapshot = outcome
    review_id = uuid4()
    job = _create_job(session, actor, review_id)
    _insert(
        session,
        tenant_id=actor.tenant_id,
        review_id=review_id,
        request=request,
        digest=digest,
        snapshot=snapshot,
        job_id=job.id,
    )
    created = CreatedReview(
        review_id=review_id,
        tenant_id=actor.tenant_id,
        vendor_id=request.vendor_id,
        request_sha256=digest,
        snapshot_sha256=snapshot.sha256,
        configuration_sha256=request.configuration.configuration_sha256,
        captured_at=snapshot.captured_at,
        job_id=job.id,
        replayed=False,
    )
    attempt.state = CommitState.ENTERED
    resolution: CommitFailureResolution | None = None
    try:
        session.commit()
    except Exception as error:  # classified here; the exception is not retained
        resolution = classify_commit_failure(error)
    if resolution is None:
        attempt.state = CommitState.COMMITTED
        attempt.result = created
    elif resolution is CommitFailureResolution.REJECTED_RETRYABLE:
        attempt.state = CommitState.REJECTED
        attempt.retryable = True
    else:
        attempt.error = ReviewCommitOutcomeUnknownError


def _cleanup_call(attempt: _Attempt, call: Callable[[], object]) -> bool:
    """One best-effort cleanup call: ``True`` only if it returned normally. Ordinary failures
    are suppressed; a process-control object is recorded only if it is the first."""
    try:
        call()
    except Exception:  # suppressed: cleanup never changes the attempt result
        return False
    except BaseException as control:
        attempt.record_control(control)
        return False
    return True


def _cleanup(attempt: _Attempt, session: Session) -> None:
    if attempt.state in (CommitState.NOT_ENTERED, CommitState.REJECTED):
        if _cleanup_call(attempt, session.rollback):
            if _cleanup_call(attempt, session.close):
                attempt.normal_cleanup = True
            else:
                _cleanup_call(attempt, session.invalidate)
        else:  # skip the normal close
            _cleanup_call(attempt, session.invalidate)
    elif attempt.state is CommitState.ENTERED:  # unknown outcome: no rollback
        _cleanup_call(attempt, session.invalidate)
    else:  # committed
        if not _cleanup_call(attempt, session.close):
            _cleanup_call(attempt, session.invalidate)


def _attempt(
    session_factory: sessionmaker[Session],
    actor: ActorContext,
    request: ReviewRequest,
    digest: str,
) -> _Attempt:
    attempt = _Attempt()
    session: Session | None = None
    try:
        session = session_factory()
        _run_body(attempt, session, actor, request, digest)
    except _Refusal as refusal:
        attempt.error = refusal.error
    except Exception as error:  # body failure before COMMIT: classified, not retained
        category = None
        try:
            category = classify_database_failure(error)
        except BaseException as control:  # process control during diagnostic access
            attempt.record_control(control)
        if category in RETRYABLE_CATEGORIES:
            attempt.retryable = True
        else:
            attempt.error = ReviewDatabaseError
    except BaseException as control:
        attempt.record_control(control)
    if session is not None:
        _cleanup(attempt, session)
    return attempt


def create_review(
    session_factory: sessionmaker[Session], actor: ActorContext, request: ReviewRequest
) -> CreatedReview:
    """Create a review atomically, or return a matching replay (see the module docstring).

    Precedence: actor type and request (``InvalidReviewRequestError``), role
    (``PermissionDeniedError``), then the database attempts."""
    checked_actor = _checked_actor(actor)
    checked = rebuilt_request(request)
    _require_role(checked_actor)
    digest = request_sha256(checked, tenant_id=checked_actor.tenant_id)
    for _ in range(MAX_CREATION_ATTEMPTS):
        attempt = _attempt(session_factory, checked_actor, checked, digest)
        if attempt.control is not None:
            raise attempt.control  # the same object; no further attempt
        if attempt.result is not None:
            return attempt.result
        if attempt.error is not None:
            raise attempt.error()
        if not attempt.normal_cleanup:
            raise ReviewConflictRetryableError()
    raise ReviewConflictRetryableError()


# --- reload --------------------------------------------------------------------------------------


@dataclass
class _Load:
    result: TrustedReview | None = None
    error: type[Exception] | None = None
    environment_failed: bool = False
    control: BaseException | None = field(default=None, repr=False)

    def record_control(self, control: BaseException) -> None:
        if self.control is None:
            self.control = control


def _recorded(load: _Load, method: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Call ``method``; record a process-control exception on ``load`` before re-raising it.
    Ordinary exceptions propagate unchanged."""
    try:
        return method(*args, **kwargs)
    except Exception:
        raise
    except BaseException as control:
        load.record_control(control)
        raise


class _RecordingResult:
    """Wraps a result returned by ``execute`` so process control raised while consuming it (for
    example ``read_snapshot``'s ``scalar_one()`` on the clock read, before its block yields) is
    recorded too. Attribute access, method calls and iteration are delegated unchanged."""

    def __init__(self, result: Any, load: _Load) -> None:
        self._result = result
        self._load = load

    def __getattr__(self, name: str) -> Any:
        value = _recorded(self._load, getattr, self._result, name)
        if not callable(value):
            return value

        def call(*args: Any, **kwargs: Any) -> Any:
            return _recorded(self._load, value, *args, **kwargs)

        return call

    def __iter__(self) -> Iterator[Any]:
        iterator = _recorded(self._load, iter, self._result)
        while True:
            try:
                yield _recorded(self._load, next, iterator)
            except StopIteration:
                return


class _RecordingSession:
    """Delegates the calls ``read_snapshot`` and the reload make, and the results they consume,
    and records any process-control exception they raise, so the first one still propagates if
    an ordinary cleanup failure or a later interrupt would otherwise replace it."""

    def __init__(self, session: Session, load: _Load) -> None:
        self._session = session
        self._load = load

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        return _RecordingResult(
            _recorded(self._load, self._session.execute, *args, **kwargs), self._load
        )

    def rollback(self) -> None:
        _recorded(self._load, self._session.rollback)

    def close(self) -> None:
        _recorded(self._load, self._session.close)


def _rebuild(
    row: Any, bindings: list[Any], excluded: list[Any], job: Any, tenant_id: UUID, review_id: UUID
) -> TrustedReview:
    """Rebuild and cross-check every stored value; any failure is ``_Refusal`` (inconsistent)."""
    error = ReviewRecordInconsistentError
    _require(row.tenant_id == tenant_id and row.id == review_id, error)
    _require([b.ordinal for b in bindings] == list(range(len(bindings))), error)
    _require(all(b.tenant_id == tenant_id and b.review_id == review_id for b in bindings), error)
    _require(all(e.tenant_id == tenant_id and e.review_id == review_id for e in excluded), error)
    _require(
        row.retrieval_config_version == RETRIEVAL_CONFIG_V1.version
        and row.retrieval_config_sha256 == RETRIEVAL_CONFIG_V1.config_sha256,
        error,
    )
    identity = EmbeddingIdentity(
        row.provider_id, row.embedding_model_id, row.algorithm_version, row.dims, row.normalization
    )
    _require(identity.fingerprint == row.fingerprint, error)
    configuration = ReviewConfiguration(
        template_id=row.template_id,
        template_version=row.template_version,
        template_sha256=row.template_sha256,
        verifier_prompt=PromptRef(
            prompt_id=row.verifier_prompt_id,
            version=row.verifier_prompt_version,
            sha256=row.verifier_prompt_sha256,
        ),
        analyst_prompt=PromptRef(
            prompt_id=row.analyst_prompt_id,
            version=row.analyst_prompt_version,
            sha256=row.analyst_prompt_sha256,
        ),
        model_id=row.model_id,
        max_output_tokens=row.max_output_tokens,
        timeout_ms=row.timeout_ms,
        retrieval_k=row.retrieval_k,
    )
    _require(configuration.configuration_sha256 == row.configuration_sha256, error)
    request = ReviewRequest(
        vendor_id=row.vendor_id,
        idempotency_key=row.idempotency_key,
        identity=identity,
        config=RETRIEVAL_CONFIG_V1,
        configuration=configuration,
    )
    _require(request_sha256(request, tenant_id=row.tenant_id) == row.request_sha256, error)
    snapshot = RetrievalSnapshot(
        tenant_id,
        row.vendor_id,
        identity,
        RETRIEVAL_CONFIG_V1,
        tuple(
            RevisionBinding(
                b.revision_id,
                b.document_id,
                b.index_id,
                b.chunker_version,
                b.chunk_count,
                b.manifest_sha256,
                b.vector_manifest_sha256,
            )
            for b in bindings
        ),
        PendingExclusions(
            row.exclusion_count, tuple(e.revision_id for e in excluded), row.exclusions_truncated
        ),
        row.captured_at,
    )
    _require(snapshot.sha256 == row.snapshot_sha256, error)
    _require(snapshot.profile_id == row.profile_id, error)
    _require(snapshot.profile_id == profile_id(tenant_id, identity.fingerprint), error)
    _require(_valid_job(job, tenant_id, review_id), error)
    return TrustedReview(
        review_id=review_id,
        tenant_id=tenant_id,
        request=request,
        request_sha256=row.request_sha256,
        snapshot=snapshot,
        job_id=row.run_review_job_id,
    )


def _load_body(load: _Load, session: Session, tenant_id: UUID, review_id: UUID) -> None:
    row = session.execute(
        select(REVIEWS).where(REVIEWS.c.tenant_id == tenant_id, REVIEWS.c.id == review_id)
    ).first()
    if row is None:
        load.error = ReviewNotFoundError
        return
    bindings = list(
        session.execute(
            select(REVIEW_BINDINGS)
            .where(
                REVIEW_BINDINGS.c.tenant_id == tenant_id,
                REVIEW_BINDINGS.c.review_id == review_id,
            )
            .order_by(REVIEW_BINDINGS.c.ordinal)
        )
    )
    excluded = list(
        session.execute(
            select(REVIEW_EXCLUSIONS)
            .where(
                REVIEW_EXCLUSIONS.c.tenant_id == tenant_id,
                REVIEW_EXCLUSIONS.c.review_id == review_id,
            )
            .order_by(REVIEW_EXCLUSIONS.c.revision_id)
        )
    )
    job = _job_row(session, tenant_id, row.run_review_job_id)
    rebuilt: list[TrustedReview] = []
    refused = False
    try:
        rebuilt.append(_rebuild(row, bindings, excluded, job, tenant_id, review_id))
    except Exception:  # any reconstruction or comparison failure (including _Refusal)
        refused = True
    if refused:
        load.error = ReviewRecordInconsistentError
    else:
        load.result = rebuilt[0]


@contextmanager
def _recording(session_factory: sessionmaker[Session], load: _Load) -> Iterator[Any]:
    def factory() -> Session:
        return cast(Session, _RecordingSession(session_factory(), load))

    with read_snapshot(cast(sessionmaker[Session], factory)) as (session, now):
        yield session, now


def load_review(
    session_factory: sessionmaker[Session], actor: ActorContext, review_id: UUID
) -> TrustedReview:
    """Reload a review for the actor's tenant through its trusted reconstruction (M5d-D).

    Precedence: actor and review-ID types (``InvalidReviewRequestError``), role
    (``PermissionDeniedError``), then ``ReviewNotFoundError``, ``ReviewRecordInconsistentError``
    or ``ReviewDatabaseError``."""
    checked_actor = _checked_actor(actor)
    if type(review_id) is not UUID:
        raise InvalidReviewRequestError()
    _require_role(checked_actor)
    load = _Load()
    try:
        with _recording(session_factory, load) as (session, _now):
            try:
                _load_body(load, session, checked_actor.tenant_id, review_id)
            except Exception:  # database or session failure inside the body
                load.error = ReviewDatabaseError
            except BaseException as control:
                load.record_control(control)
                raise
    except Exception:  # session creation, the helper's statements or cleanup
        load.environment_failed = True
    except BaseException as control:
        load.record_control(control)
    if load.control is not None:
        raise load.control
    if load.error is not None:
        raise load.error()
    if load.environment_failed or load.result is None:
        raise ReviewDatabaseError()
    return load.result
