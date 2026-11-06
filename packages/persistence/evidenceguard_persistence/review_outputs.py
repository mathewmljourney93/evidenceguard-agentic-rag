"""Fenced review-output writer, output reads and the W15 status projection (M5g, ADR-0025).

Implements M5g-F2, F4, G2 and G3 of the specification accepted in Prompt 217 (``docs/plan.md``).
These are **trusted internal programming interfaces**: no endpoint, command, production handler or
registry entry calls them, and ``run_review`` stays unregistered.

**Writer** (``write_review_output``) composes into the **caller's** fenced transaction (intended:
the ``finish=True`` fence that records the job's success, so the output and the success are
durable together or not at all). It never commits, rolls back, closes, retries or logs. Order, the
first failure deciding: arguments (``InvalidOutputRequestError``), fence association
(``ReviewOutputFenceMismatchError``), binding (``ReviewOutputBindingError``), completeness
(``ReviewOutputIncompleteError``), replay or conflict (``ReviewOutputConflictError``), insert, then
the final ownership recheck. An identical stored row is returned with ``replayed=True`` and nothing
is written; this deliberate recovery case is never a normal handler path (M5g-G2).

**Reads** (``load_review_output``, ``load_review_status``) rebuild the actor before any role check
or SQL, then run one read-only REPEATABLE READ transaction through ``read_snapshot`` with recording
wrappers (the first process-control object stays primary even when cleanup fails). Missing-review
and non-canonical-job precedence come first; then one shared lifecycle/presence table (M5g-F4)
decides before any output decoding. Neither read writes, and neither adds a conclusion from stage
rows: the rows are compared by digest only.

**Errors** are fixed and text-free, raised fresh after every handler with no cause or context.
``LeaseLostError``, ``FenceClosedError`` and ``JobLockTimeoutError`` pass through the writer
unchanged; process control propagates as the same object (on fenced paths within the caller's
transaction helper). A unique or primary-key violation (possible only through a fence bypass) is
``ReviewOutputConflictError``; every other ordinary database failure is
``ReviewOutputDatabaseError``.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar, NoReturn, cast
from uuid import UUID

from sqlalchemy import Table, insert, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_domain.errors import PermissionDeniedError
from evidenceguard_domain.jobs import (
    InvalidJobTransitionError,
    JobErrorCode,
    JobLeaseToken,
    JobPayload,
    JobSnapshot,
    JobStatus,
    LeaseLostError,
)
from evidenceguard_domain.review_outputs import (
    ReviewOutput,
    ReviewOutputWrite,
    ReviewStatus,
    StoredReviewOutput,
    decode_stored_review_output,
)
from evidenceguard_domain.reviews import (
    REVIEW_JOB_KIND,
    REVIEW_JOB_MAX_ATTEMPTS,
    ReviewNotFoundError,
)
from evidenceguard_persistence.document_views import read_snapshot
from evidenceguard_persistence.jobs import (
    JOBS,
    FenceClosedError,
    FencedSession,
    JobLockTimeoutError,
    recheck_ownership,
)
from evidenceguard_persistence.models import (
    Review,
    ReviewOutputRow,
    ReviewPlanQuestion,
    ReviewStageResult,
)
from evidenceguard_persistence.review_stages import StageFence

__all__ = [
    "InvalidOutputRequestError",
    "ReviewOutputBindingError",
    "ReviewOutputConflictError",
    "ReviewOutputDatabaseError",
    "ReviewOutputError",
    "ReviewOutputFenceMismatchError",
    "ReviewOutputIncompleteError",
    "ReviewOutputNotFoundError",
    "ReviewOutputRecordInconsistentError",
    "StageFence",
    "load_review_output",
    "load_review_status",
    "write_review_output",
]

REVIEWS = cast(Table, Review.__table__)
OUTPUTS = cast(Table, ReviewOutputRow.__table__)
PLAN_QUESTIONS = cast(Table, ReviewPlanQuestion.__table__)
STAGE_RESULTS = cast(Table, ReviewStageResult.__table__)

READ_STATEMENT_TIMEOUT_MS = 30_000
"""Per statement, transaction-local, for the reads (not an end-to-end deadline)."""
UNIQUE_VIOLATION = "23505"
READ_ROLES = frozenset({Role.REVIEWER, Role.APPROVER})
STAGE_NAMES = ("verification", "analysis")


# --- errors (fixed codes and messages) -----------------------------------------------------------


class ReviewOutputError(Exception):
    """Base of the fixed M5g persistence errors."""

    code: ClassVar[str] = "review_output_error"
    message: ClassVar[str] = "the review output operation failed"

    def __init__(self) -> None:
        super().__init__(self.message)


class InvalidOutputRequestError(ReviewOutputError):
    """Invalid argument types or values, including bypass-built actors, fences or outputs."""

    code = "invalid_review_output_request"
    message = "the review output request is invalid"


class ReviewOutputFenceMismatchError(ReviewOutputError):
    """The fence's job is not the review's canonical ``run_review`` job, holds no lease token,
    or the review is missing for the job's tenant or names another job."""

    code = "review_output_fence_mismatch"
    message = "the fence is not the review's canonical job"


class ReviewOutputBindingError(ReviewOutputError):
    """The output's tenant, vendor, job, digests or planned questions differ from the review."""

    code = "review_output_binding_mismatch"
    message = "the review output does not match the review"


class ReviewOutputIncompleteError(ReviewOutputError):
    """A planned question lacks a committed stage, or a stored stage differs from the output."""

    code = "review_output_incomplete"
    message = "the review stages are incomplete or differ"


class ReviewOutputConflictError(ReviewOutputError):
    """A different output is stored, or a key violation (only possible through a bypass)."""

    code = "review_output_conflict"
    message = "a different review output exists"


class ReviewOutputNotFoundError(ReviewOutputError):
    """The review exists but has no output, and its job has not succeeded."""

    code = "review_output_not_found"
    message = "the review has no output"


class ReviewOutputRecordInconsistentError(ReviewOutputError):
    """The stored output, its job or its lifecycle combination is inconsistent."""

    code = "review_output_record_inconsistent"
    message = "the stored review output is inconsistent"


class ReviewOutputDatabaseError(ReviewOutputError):
    """Any other database or session failure (including a statement or lock timeout)."""

    code = "review_output_database_error"
    message = "the review output could not be read or written"


# --- refusals and the failure boundary -----------------------------------------------------------


class _Refusal(Exception):
    """Private: a fixed refusal decided by this module's own checks (never a database error)."""

    def __init__(self, error: type[ReviewOutputError] | type[ReviewNotFoundError]) -> None:
        super().__init__()
        self.error = error


def _refuse(error: type[ReviewOutputError] | type[ReviewNotFoundError]) -> NoReturn:
    raise _Refusal(error)


def _require(condition: bool, error: type[ReviewOutputError]) -> None:
    if not condition:
        raise _Refusal(error)


def _holds(check: Callable[[], bool]) -> bool:
    """A pure comparison over rows already read; any ordinary failure counts as ``False``."""
    held: list[bool] = []
    with suppress(Exception):
        held.append(bool(check()))
    return bool(held) and held[0]


def _arguments[T](make: Callable[[], T]) -> T:
    """Argument checks before any role check or SQL: any ordinary failure is a fresh
    ``InvalidOutputRequestError`` raised after the handler."""
    built: list[T] = []
    with suppress(Exception):
        built.append(make())
    if not built:
        raise InvalidOutputRequestError()
    return built[0]


def _sqlstate(error: object) -> str | None:
    """The exact ``str`` SQLSTATE of a ``DBAPIError``'s driver error, or ``None``. Only the
    attribute is read, inside one guard; messages and chains are never read."""
    if not isinstance(error, DBAPIError):
        return None
    found: list[str] = []
    try:
        value = getattr(error.orig, "sqlstate")  # noqa: B009 - attribute access is guarded
        if type(value) is str:
            found.append(value)
    except Exception:  # missing or raising diagnostics: conservative fallback
        pass
    return found[0] if found else None


def _write[T](body: Callable[[], T]) -> T:
    """The writer's failure boundary: a refusal raises its fixed error; the M3 fence errors pass
    through unchanged; a unique violation is ``ReviewOutputConflictError``; every other ordinary
    exception is ``ReviewOutputDatabaseError``. Raised after the handler (no cause or context).
    Process control propagates as the same object."""
    done: list[T] = []
    error: type[Exception] | None = None
    try:
        done.append(body())
    except _Refusal as refusal:
        error = refusal.error
    except (LeaseLostError, FenceClosedError, JobLockTimeoutError):
        raise
    except Exception as failure:  # classified here; the exception is not retained
        if _sqlstate(failure) == UNIQUE_VIOLATION:
            error = ReviewOutputConflictError
        else:
            error = ReviewOutputDatabaseError
    if error is not None:
        raise error()
    return done[0]


# --- argument rebuilding (G24) -------------------------------------------------------------------


def _rebuilt_job(job: object) -> JobSnapshot:
    """A ``JobSnapshot`` with exact field types, rebuilt through its constructor and equal to the
    input; ``model_construct``/``object.__new__`` values and coerced fields are refused."""
    if type(job) is not JobSnapshot:
        raise TypeError
    assert isinstance(job, JobSnapshot)
    values = {name: getattr(job, name) for name in JobSnapshot.model_fields}
    for name in ("id", "tenant_id"):
        if type(values[name]) is not UUID:
            raise TypeError
    for name in ("kind", "idempotency_key"):
        if type(values[name]) is not str:
            raise TypeError
    for name in ("attempt", "max_attempts"):
        if type(values[name]) is not int:
            raise TypeError
    if type(values["status"]) is not JobStatus or type(values["payload"]) is not JobPayload:
        raise TypeError
    payload = values["payload"]
    values["payload"] = JobPayload(entries=payload.entries)
    if values["payload"] != payload:
        raise ValueError
    for name in ("run_after", "created_at", "updated_at"):
        if type(values[name]) is not datetime:
            raise TypeError
    for name in ("lease_expires_at", "finished_at"):
        if values[name] is not None and type(values[name]) is not datetime:
            raise TypeError
    if values["locked_by"] is not None and type(values["locked_by"]) is not str:
        raise TypeError
    if values["last_error"] is not None and type(values["last_error"]) is not JobErrorCode:
        raise TypeError
    rebuilt = JobSnapshot(**values)
    if rebuilt != job:
        raise ValueError
    return rebuilt


def _fence_parts(fence: object) -> tuple[FencedSession, JobSnapshot]:
    """The fence's session and job, each read once (the M5e pattern) and the job rebuilt."""

    def build() -> tuple[FencedSession, JobSnapshot]:
        session = getattr(fence, "session")  # noqa: B009 - structural protocol access
        job = getattr(fence, "job")  # noqa: B009
        if type(session) is not FencedSession:
            raise TypeError
        return session, _rebuilt_job(job)

    return _arguments(build)


def _rebuilt_actor(actor: object) -> ActorContext:
    """An ``ActorContext`` with exact field types, rebuilt and equal to the input."""

    def build() -> ActorContext:
        if type(actor) is not ActorContext:
            raise TypeError
        assert isinstance(actor, ActorContext)
        tenant_id, actor_id, role = actor.tenant_id, actor.actor_id, actor.role
        if type(tenant_id) is not UUID or type(actor_id) is not UUID or type(role) is not Role:
            raise TypeError
        rebuilt = ActorContext(tenant_id=tenant_id, actor_id=actor_id, role=role)
        if rebuilt != actor:
            raise ValueError
        return rebuilt

    return _arguments(build)


def _checked_review_id(review_id: object) -> UUID:
    def build() -> UUID:
        if type(review_id) is not UUID:
            raise TypeError
        assert isinstance(review_id, UUID)
        return review_id

    return _arguments(build)


# --- shared comparisons (writer and reads; pure over rows already read) --------------------------


def _canonical_job(job: Any, tenant_id: UUID, review_id: UUID) -> bool:
    """The stored or fenced job is the review's canonical ``run_review`` job (kind, idempotency
    key, payload and max attempts); its lifecycle fields may be anything."""
    payload = job.payload
    if isinstance(payload, JobPayload):
        payload = payload.as_dict()
    return bool(
        job.tenant_id == tenant_id
        and job.kind == REVIEW_JOB_KIND
        and job.idempotency_key == str(review_id)
        and payload == {"review_id": str(review_id)}
        and job.max_attempts == REVIEW_JOB_MAX_ATTEMPTS
    )


def _binding_holds(review: Any, output: ReviewOutput) -> bool:
    """The review row's tenant, vendor, job and the three binding digests against the output."""
    binding = output.content.binding
    return bool(
        review.tenant_id == output.tenant_id
        and review.id == output.review_id
        and review.run_review_job_id == output.job_id
        and review.vendor_id == binding.vendor_id
        and review.request_sha256 == output.review_request_sha256
        and review.snapshot_sha256 == output.snapshot_sha256
        and review.configuration_sha256 == output.configuration_sha256
    )


def _plan_holds(plans: list[Any], output: ReviewOutput) -> bool:
    """The stored planned questions, by position and plan digest, equal the wrapper's."""
    stored = [(row.position, row.question_id, row.question_sha256) for row in plans]
    expected = [
        (question.position, question.question_id, question.plan_question_sha256)
        for question in output.content.questions
    ]
    return stored == expected and all(row.job_id == output.job_id for row in plans)


def _row_shape(row: Any) -> str:
    """The M5e-C shape of a stored stage row from its outcome and reason (shape names only)."""
    if row.outcome == "verified":
        return "S1"
    if row.outcome == "analyzed":
        return "S2"
    return {
        "evidence_too_large": "U4",
        "verification_unresolved": "U3",
        "request_too_large": "U5",
        "repair_request_too_large": "U6",
        "call_abandoned": "U2",
    }.get(row.unresolved_reason, "U1")


def _stage_row_holds(row: Any, stage: Any, job_id: UUID) -> bool:
    reason = stage.unresolved_reason
    return bool(
        row.job_id == job_id
        and _row_shape(row) == stage.shape.value
        and row.outcome == stage.outcome.value
        and row.unresolved_reason == (None if reason is None else reason.value)
        and row.request_sha256 == stage.request_sha256
        and row.content_sha256 == stage.content_sha256
        and row.evidence_sha256 == stage.evidence_sha256
        and row.dependency_sha256 == stage.dependency_sha256
    )


def _complete(stages: list[Any], output: ReviewOutput) -> bool:
    """Every planned question has both committed stage rows, each equal to the wrapper's
    ``ReportStage`` (shape, outcome, reason and the request, content, evidence and dependency
    digests), and there is no other stage row."""
    by_key = {(row.question_id, row.stage): row for row in stages}
    if len(by_key) != len(stages) or len(stages) != 2 * len(output.content.questions):
        return False
    for question in output.content.questions:
        for name, stage in zip(
            STAGE_NAMES, (question.verification, question.analysis), strict=True
        ):
            row = by_key.get((question.question_id, name))
            if row is None or not _stage_row_holds(row, stage, output.job_id):
                return False
    return True


def _stage_keys_present(stages: list[Any], output: ReviewOutput) -> bool:
    keys = {(row.question_id, row.stage) for row in stages}
    return all(
        (question.question_id, name) in keys
        for question in output.content.questions
        for name in STAGE_NAMES
    )


def _same_output(stored: StoredReviewOutput, incoming: ReviewOutput) -> bool:
    """M5g-G2: the must-match and recomputed sets (audit fields are excluded)."""
    current = stored.output
    return bool(
        current.tenant_id == incoming.tenant_id
        and current.review_id == incoming.review_id
        and current.job_id == incoming.job_id
        and current.schema_id == incoming.schema_id
        and current.renderer_id == incoming.renderer_id
        and current.mode == incoming.mode
        and current.wrapper_canonical == incoming.wrapper_canonical
        and current.wrapper_sha256 == incoming.wrapper_sha256
        and current.markdown_sha256 == incoming.markdown_sha256
        and current.markdown_bytes == incoming.markdown_bytes
        and current.legacy_sha256 == incoming.legacy_sha256
        and current.review_request_sha256 == incoming.review_request_sha256
        and current.snapshot_sha256 == incoming.snapshot_sha256
        and current.configuration_sha256 == incoming.configuration_sha256
        and current.question_count == incoming.question_count
        and current.finding_count == incoming.finding_count
        and current.unresolved_count == incoming.unresolved_count
    )


def _row_values(row: Any) -> dict[str, Any]:
    return {str(key): value for key, value in row._mapping.items()}


# --- the writer ----------------------------------------------------------------------------------


@dataclass
class _Context:
    session: FencedSession
    job: JobSnapshot
    token: JobLeaseToken
    review: Any


def _associate(session: FencedSession, job: JobSnapshot, output: ReviewOutput) -> _Context:
    """Step 2: canonical job, lease token, ownership recheck at entry, review row naming the job."""
    _require(
        _holds(lambda: _canonical_job(job, job.tenant_id, output.review_id)),
        ReviewOutputFenceMismatchError,
    )
    tokens: list[JobLeaseToken] = []
    with suppress(InvalidJobTransitionError):
        tokens.append(job.lease_token())
    _require(bool(tokens), ReviewOutputFenceMismatchError)
    token = tokens[0]
    owned, _ = recheck_ownership(session, token)
    _require(
        owned.tenant_id == job.tenant_id and owned.id == job.id, ReviewOutputFenceMismatchError
    )
    review = session.execute(
        select(REVIEWS).where(
            REVIEWS.c.tenant_id == job.tenant_id, REVIEWS.c.id == output.review_id
        )
    ).first()
    _require(
        review is not None and review.run_review_job_id == job.id, ReviewOutputFenceMismatchError
    )
    return _Context(session=session, job=job, token=token, review=review)


def _final(context: _Context) -> None:
    """Step 7: the ownership recheck after the last statement (``LeaseLostError`` escapes)."""
    owned, _ = recheck_ownership(context.session, context.token)
    _require(owned.tenant_id == context.job.tenant_id, ReviewOutputFenceMismatchError)


def _review_scope(table: Table, tenant_id: UUID, review_id: UUID) -> Any:
    return (table.c.tenant_id == tenant_id) & (table.c.review_id == review_id)


def _plans(session: Any, tenant_id: UUID, review_id: UUID) -> list[Any]:
    return list(
        session.execute(
            select(PLAN_QUESTIONS)
            .where(_review_scope(PLAN_QUESTIONS, tenant_id, review_id))
            .order_by(PLAN_QUESTIONS.c.position)
        )
    )


def _stages(session: Any, tenant_id: UUID, review_id: UUID) -> list[Any]:
    return list(
        session.execute(
            select(STAGE_RESULTS)
            .where(_review_scope(STAGE_RESULTS, tenant_id, review_id))
            .order_by(STAGE_RESULTS.c.question_id, STAGE_RESULTS.c.stage)
        )
    )


def _output_row(session: Any, tenant_id: UUID, review_id: UUID) -> Any:
    return session.execute(
        select(OUTPUTS).where(_review_scope(OUTPUTS, tenant_id, review_id))
    ).first()


def _decoded_or_none(row: Any) -> StoredReviewOutput | None:
    decoded: list[StoredReviewOutput] = []
    with suppress(Exception):
        decoded.append(decode_stored_review_output(_row_values(row)))
    return decoded[0] if decoded else None


def write_review_output(fence: StageFence, output: ReviewOutput) -> ReviewOutputWrite:
    """Store ``output`` once inside the caller's fence (M5g-F2), or replay an identical stored
    row (M5g-G2). See the module docstring for the order and the errors."""

    def arguments() -> tuple[FencedSession, JobSnapshot, ReviewOutput]:
        if type(output) is not ReviewOutput:
            raise TypeError
        assert isinstance(output, ReviewOutput)
        rebuilt = ReviewOutput(
            tenant_id=output.tenant_id,
            review_id=output.review_id,
            job_id=output.job_id,
            content=output.content,
            markdown_sha256=output.markdown_sha256,
            markdown_bytes=output.markdown_bytes,
        )
        if rebuilt != output:
            raise ValueError
        return (*_fence_parts(fence), rebuilt)

    session, job, checked = _arguments(arguments)

    def body() -> ReviewOutputWrite:
        context = _associate(session, job, checked)  # step 2
        tenant_id, review_id = job.tenant_id, checked.review_id
        _require(  # step 3
            checked.tenant_id == tenant_id and checked.job_id == job.id,
            ReviewOutputBindingError,
        )
        _require(_holds(lambda: _binding_holds(context.review, checked)), ReviewOutputBindingError)
        plans = _plans(session, tenant_id, review_id)
        _require(_holds(lambda: _plan_holds(plans, checked)), ReviewOutputBindingError)
        stages = _stages(session, tenant_id, review_id)  # step 4
        _require(_holds(lambda: _complete(stages, checked)), ReviewOutputIncompleteError)
        existing = _output_row(session, tenant_id, review_id)  # step 5
        if existing is not None:
            stored = _decoded_or_none(existing)
            _require(
                stored is not None and _holds(lambda: _same_output(cast(Any, stored), checked)),
                ReviewOutputConflictError,
            )
            assert stored is not None
            _final(context)
            return _built_write(stored, replayed=True)
        attempt = context.token.attempt  # step 6: from the fence, never from the caller
        created_at = session.execute(
            insert(OUTPUTS)
            .values(
                tenant_id=tenant_id,
                review_id=review_id,
                job_id=job.id,
                schema_id=checked.schema_id,
                renderer_id=checked.renderer_id,
                mode=checked.mode,
                wrapper_canonical=checked.wrapper_canonical.decode("ascii"),
                wrapper_sha256=checked.wrapper_sha256,
                legacy_sha256=checked.legacy_sha256,
                review_request_sha256=checked.review_request_sha256,
                snapshot_sha256=checked.snapshot_sha256,
                configuration_sha256=checked.configuration_sha256,
                question_count=checked.question_count,
                finding_count=checked.finding_count,
                unresolved_count=checked.unresolved_count,
                markdown_sha256=checked.markdown_sha256,
                markdown_bytes=checked.markdown_bytes,
                job_attempt=attempt,
            )
            .returning(OUTPUTS.c.created_at)
        ).scalar_one()
        stored = _built_stored(checked, attempt, created_at)
        _final(context)  # step 7
        return _built_write(stored, replayed=False)

    return _write(body)


def _built_stored(output: ReviewOutput, attempt: int, created_at: object) -> StoredReviewOutput:
    built: list[StoredReviewOutput] = []
    with suppress(Exception):
        built.append(
            StoredReviewOutput(
                output=output, job_attempt=attempt, created_at=cast(datetime, created_at)
            )
        )
    _require(bool(built), ReviewOutputDatabaseError)
    return built[0]


def _built_write(stored: StoredReviewOutput, *, replayed: bool) -> ReviewOutputWrite:
    built: list[ReviewOutputWrite] = []
    with suppress(Exception):
        built.append(ReviewOutputWrite(stored=stored, replayed=replayed))
    _require(bool(built), ReviewOutputDatabaseError)
    return built[0]


# --- reads: one snapshot with recording wrappers -------------------------------------------------


@dataclass
class _Load:
    output: StoredReviewOutput | None = None
    status: ReviewStatus | None = None
    error: type[Exception] | None = None
    environment_failed: bool = False
    control: BaseException | None = field(default=None, repr=False)

    def record_control(self, control: BaseException) -> None:
        if self.control is None:  # the first process-control object stays primary
            self.control = control


def _recorded(load: _Load, method: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Call ``method``; record a process-control exception on ``load`` before re-raising it.
    Ordinary exceptions propagate unchanged (M5d's read-boundary pattern)."""
    try:
        return method(*args, **kwargs)
    except Exception:
        raise
    except BaseException as control:
        load.record_control(control)
        raise


class _RecordingResult:
    """Wraps a result returned by ``execute`` so process control raised while consuming it is
    recorded too; attribute access, method calls and iteration are delegated unchanged."""

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
    """Delegates the calls ``read_snapshot`` and the reads make, and records any process-control
    exception they raise, so the first one still propagates if an ordinary cleanup failure or a
    later interrupt would otherwise replace it."""

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


@contextmanager
def _recording(session_factory: sessionmaker[Session], load: _Load) -> Iterator[Any]:
    def factory() -> Session:
        return cast(Session, _RecordingSession(session_factory(), load))

    with read_snapshot(cast(sessionmaker[Session], factory)) as (session, now):
        yield session, now


_STATUS_BY_JOB = {
    JobStatus.QUEUED.value: ReviewStatus.QUEUED,
    JobStatus.RUNNING.value: ReviewStatus.RUNNING,
    JobStatus.FAILED.value: ReviewStatus.FAILED,
    JobStatus.DEAD.value: ReviewStatus.FAILED,
}


def _lifecycle(job: Any, present: bool) -> ReviewStatus:
    """M5g-F4, the shared lifecycle/presence table (inconsistent rows are refusals)."""
    status = job.status
    if present:
        _require(status == JobStatus.SUCCEEDED.value, ReviewOutputRecordInconsistentError)
        return ReviewStatus.COMPLETED
    _require(
        status != JobStatus.SUCCEEDED.value and status in _STATUS_BY_JOB,
        ReviewOutputRecordInconsistentError,
    )
    return _STATUS_BY_JOB[status]


def _read_body(
    load: _Load, session: Any, tenant_id: UUID, review_id: UUID, *, decode: bool
) -> None:
    session.execute(text(f"SET LOCAL statement_timeout = {int(READ_STATEMENT_TIMEOUT_MS)}"))
    review = session.execute(
        select(REVIEWS).where(REVIEWS.c.tenant_id == tenant_id, REVIEWS.c.id == review_id)
    ).first()
    if review is None:
        _refuse(ReviewNotFoundError)
    job = session.execute(
        select(JOBS).where(JOBS.c.tenant_id == tenant_id, JOBS.c.id == review.run_review_job_id)
    ).first()
    _require(
        job is not None and _holds(lambda: _canonical_job(job, tenant_id, review_id)),
        ReviewOutputRecordInconsistentError,
    )
    row = _output_row(session, tenant_id, review_id)
    status = _lifecycle(job, row is not None)
    load.status = status
    if not decode:
        return
    if row is None:
        _refuse(ReviewOutputNotFoundError)
    stored = _decoded_or_none(row)
    _require(stored is not None, ReviewOutputRecordInconsistentError)
    assert stored is not None
    output = stored.output
    plans = _plans(session, tenant_id, review_id)
    stages = _stages(session, tenant_id, review_id)
    _require(
        _holds(
            lambda: (
                output.tenant_id == tenant_id
                and output.review_id == review_id
                and output.job_id == job.id
                and _binding_holds(review, output)
                and _plan_holds(plans, output)
                and _complete(stages, output)
                and stored.job_attempt <= job.attempt
            )
        ),
        ReviewOutputRecordInconsistentError,
    )
    load.output = stored


def _read(
    session_factory: sessionmaker[Session], actor: object, review_id: object, *, decode: bool
) -> _Load:
    checked_actor = _rebuilt_actor(actor)  # step 1: types before any role check or SQL
    checked_id = _checked_review_id(review_id)
    if checked_actor.role not in READ_ROLES:  # step 2
        raise PermissionDeniedError()
    load = _Load()
    try:
        with _recording(session_factory, load) as (session, _now):
            try:
                _read_body(load, session, checked_actor.tenant_id, checked_id, decode=decode)
            except _Refusal as refusal:
                load.error = refusal.error
            except Exception:  # database or session failure inside the body
                load.error = ReviewOutputDatabaseError
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
    if load.environment_failed:
        raise ReviewOutputDatabaseError()
    return load


def load_review_output(
    session_factory: sessionmaker[Session], actor: ActorContext, review_id: UUID
) -> StoredReviewOutput:
    """The stored output of a completed review (M5g-F2, F4). Precedence: actor and review-ID
    types (``InvalidOutputRequestError``), role (``PermissionDeniedError``), then in one read
    snapshot: absent review (``ReviewNotFoundError``; another tenant's review is
    indistinguishable), a missing or non-canonical job and every inconsistent lifecycle/presence
    combination (``ReviewOutputRecordInconsistentError``), an absent output with a job that has
    not succeeded (``ReviewOutputNotFoundError``), then the strict decode and the binding,
    plan, stage-digest and attempt checks. A database failure is ``ReviewOutputDatabaseError``."""
    load = _read(session_factory, actor, review_id, decode=True)
    if load.output is None:
        raise ReviewOutputDatabaseError()
    return load.output


def load_review_status(
    session_factory: sessionmaker[Session], actor: ActorContext, review_id: UUID
) -> ReviewStatus:
    """The W15 read-time status (M5g-G3): the status column of the shared lifecycle/presence
    table, with the same precedence as ``load_review_output`` and no output decoding. It makes no
    writes and no compensation; there is no endpoint."""
    load = _read(session_factory, actor, review_id, decode=False)
    if load.status is None:
        raise ReviewOutputDatabaseError()
    return load.status
