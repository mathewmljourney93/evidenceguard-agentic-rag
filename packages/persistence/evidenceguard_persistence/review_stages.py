"""Fenced stage and call-reservation persistence and the trusted reload (M5e, ADR-0023).

Implements the persistence half of the M5e specification accepted in Prompt 199 (``docs/plan.md``,
M5e-E to M5e-K, with clarifications A and B). These are **trusted internal programming
interfaces**: no endpoint, command, production handler or registry entry calls them (W8), and
``run_review`` stays unregistered.

**Transaction ownership.** Every write API composes into the **caller's** fenced transaction. Its
first argument is a ``StageFence`` (structurally the worker's ``HandlerFence`` or the M3 ``Fence``:
``.session`` and ``.job``). An API never commits, rolls back, closes, sets isolation, uses
savepoints or retries. It may already have executed statements when it raises, so a failed
operation must **escape** the caller's fenced block, whose fence then rolls back; suppressing an
M5e error inside the block can commit partial effects. Only ``load_trusted_stages`` owns a
(read-only) transaction.

**Fence association** (every write API, after the argument checks): the job is the review's
canonical ``run_review`` job (kind and idempotency key); its lease token comes from
``fence.job.lease_token()``; ``recheck_ownership`` runs at entry and **again after the last write**,
because inserts, the guarded update and their foreign-key checks can wait on locks while the lease
clock runs; the review row must name the job. Statements may still execute after expiry; they are
rolled back when the final check fails and its error escapes (the accepted M3 limit).

**Checks and replay.** Argument types and values (``InvalidStageRequestError``), fence association,
the operation's ordered checks (the shared evidence sequence E1-E8, the completion binding rule
B1-B9, or the per-API rules), then replay (an identical record is returned and nothing is written;
a different one is ``StageConflictError``), then the mutation preconditions M1-M3, the writes and
the final ownership check. The first failing check decides. The successful-completion APIs take
an explicit ``question_id`` and a stage fixed by the API (clarification A); the selected call is
never derived from the result or the content. A well-formed U4 stage (no evidence row, no calls)
is a valid closed state; its identical replay is a no-op and ``record_evidence`` cannot reopen it
(clarification B). Allocation is not replayable.

**Errors** are fixed and text-free, raised fresh after every handler. ``LeaseLostError``,
``FenceClosedError`` and ``JobLockTimeoutError`` pass through unchanged (the M3 runtime interprets
them). A unique-key or one-repair index violation (possible only through a fence bypass) is
``StageConflictError``; every other ordinary database failure is ``StageDatabaseError``. Process
control propagates as the same object. Nothing logs.

**Reload** (``load_trusted_stages``) runs one read-only REPEATABLE READ transaction through the
public ``read_snapshot`` helper with M5d's recording wrappers, decodes and rebuilds every stored
value, validates every history, shape, setting, digest and dependency, rechecks the evidence
against trusted database chunks with ``recheck_evidence_in_transaction`` and the content with
``recheck_verified``/``recheck_analyzed``. It cannot prove template origin, original retrieval
execution, request reassembly (a worker obligation), the U5/U6 size assertions, or a U4 stage's
discarded bytes and their original binding; it makes no entailment, authenticity or
injection-resistance claim.
"""

import hashlib
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from typing import Any, NoReturn, Protocol, cast
from uuid import UUID

from sqlalchemy import Table, func, insert, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from evidenceguard_domain.context import ActorContext
from evidenceguard_domain.errors import PermissionDeniedError
from evidenceguard_domain.jobs import (
    InvalidJobTransitionError,
    JobLeaseToken,
    JobSnapshot,
    LeaseLostError,
)
from evidenceguard_domain.model_calls import (
    CallOutcome,
    ModelUsage,
    StructuredRequest,
    StructuredResult,
    is_question_id,
)
from evidenceguard_domain.provenance import (
    AnalyzedQuestion,
    ProvenanceRejection,
    QuestionEvidence,
    RejectionReason,
    VerifiedQuestion,
    recheck_analyzed,
    recheck_verified,
)
from evidenceguard_domain.review_stages import (
    AFTER_CALL_REASONS,
    CallKind,
    CallRecord,
    CallRejection,
    EvidenceRecord,
    PlanDispatch,
    PlanExhausted,
    PlanInFlight,
    PlannedQuestionSet,
    PlanReuse,
    RequestBasis,
    ReservationState,
    ReviewStageError,
    StageHistory,
    StageKind,
    StageOutcome,
    StageRecord,
    StageShape,
    StageState,
    TrustedQuestionStages,
    TrustedStages,
    UnresolvedReason,
    decode_analyzed,
    decode_evidence,
    decode_verified,
    dependency_sha256,
    encode_verified,
    plan_stage,
    plan_without_stage,
    revalidated_analyzed,
    revalidated_evidence,
    revalidated_planned,
    revalidated_rejection,
    revalidated_request,
    revalidated_result,
    revalidated_verified,
)
from evidenceguard_domain.reviews import REVIEW_JOB_KIND, TrustedReview
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
    ReviewPlanQuestion,
    ReviewQuestionEvidence,
    ReviewStageCall,
    ReviewStageResult,
)
from evidenceguard_persistence.retrieval import (
    RETRIEVAL_ROLES,
    EvidenceRecheckFailure,
    SemanticOutcome,
    recheck_evidence_in_transaction,
)

REVIEWS = cast(Table, Review.__table__)
PLAN_QUESTIONS = cast(Table, ReviewPlanQuestion.__table__)
QUESTION_EVIDENCE = cast(Table, ReviewQuestionEvidence.__table__)
STAGE_CALLS = cast(Table, ReviewStageCall.__table__)
STAGE_RESULTS = cast(Table, ReviewStageResult.__table__)

RELOAD_STATEMENT_TIMEOUT_MS = 30_000
"""Per statement, transaction-local, for the reload (not an end-to-end deadline)."""
UNIQUE_VIOLATION = "23505"


# --- errors (fixed messages: the message is the code) ---------------------------------------------


class InvalidStageRequestError(ReviewStageError):
    """Invalid arguments: types, values (including an inherited integer outside the admission
    range), a fence that is not structurally a ``StageFence`` or an inconsistent combination."""

    code = "invalid_stage_request"


class StageFenceMismatchError(ReviewStageError):
    """The fence's job is not the review's canonical ``run_review`` job, holds no lease token,
    or the review is missing for the job's tenant."""

    code = "stage_fence_mismatch"


class StageNotPlannedError(ReviewStageError):
    """The question is not among the review's stored planned questions."""

    code = "stage_not_planned"


class StageBindingError(ReviewStageError):
    """A tenant, review, question, configuration, request or snapshot mismatch."""

    code = "stage_binding_mismatch"


class StageDependencyError(ReviewStageError):
    """A missing, unresolved, foreign or digest-changed dependency (evidence or owner)."""

    code = "stage_dependency_mismatch"


class StagePlanMismatchError(ReviewStageError):
    """The requested operation does not match the stored history's plan or shape."""

    code = "stage_plan_mismatch"


class StageCallInFlightError(ReviewStageError):
    """The last call is still ``started`` by the current attempt."""

    code = "stage_call_in_flight"


class StageCallAbandonedError(ReviewStageError):
    """The call was allocated by an earlier attempt and can no longer be completed."""

    code = "stage_call_abandoned"


class StageBudgetExhaustedError(ReviewStageError):
    """The three-reservation budget (or the single repair) is used up."""

    code = "stage_budget_exhausted"


class StageConflictError(ReviewStageError):
    """A differing replay, a committed or completed record, or a key violation."""

    code = "stage_conflict"


class EvidenceTooLargeError(ReviewStageError):
    """``record_evidence`` with a record whose encoding exceeds the cap (use U4)."""

    code = "evidence_too_large"


class StageRecordInconsistentError(ReviewStageError):
    """Stored rows fail decoding, reconstruction or a history, shape or digest rule."""

    code = "stage_record_inconsistent"


class StageDatabaseError(ReviewStageError):
    """Any other database or session failure (including a statement or lock timeout)."""

    code = "stage_database_error"


# --- fences, refusals and the failure boundary ----------------------------------------------------


class StageFence(Protocol):
    """The attributes an M5e write API needs; the worker's ``HandlerFence`` and the M3 ``Fence``
    already expose exactly these. No new seam."""

    @property
    def session(self) -> FencedSession: ...

    @property
    def job(self) -> JobSnapshot: ...


class _Refusal(Exception):
    """Private: a fixed refusal decided by this module's own checks (never a database error)."""

    def __init__(self, error: type[ReviewStageError]) -> None:
        super().__init__()
        self.error = error


def _refuse(error: type[ReviewStageError]) -> NoReturn:
    raise _Refusal(error)


def _require(condition: bool, error: type[ReviewStageError]) -> None:
    if not condition:
        raise _Refusal(error)


def _guarded[T](make: Callable[[], T], error: type[ReviewStageError]) -> T:
    """Run a pure step; any ordinary failure is the fixed ``error`` (a ``_Refusal``)."""
    built: list[T] = []
    with suppress(Exception):
        built.append(make())
    if not built:
        _refuse(error)
    return built[0]


def _arguments[T](make: Callable[[], T]) -> T:
    """Argument checks before any database work: any ordinary failure is a fresh
    ``InvalidStageRequestError`` raised after the handler."""
    built: list[T] = []
    with suppress(Exception):
        built.append(make())
    if not built:
        raise InvalidStageRequestError()
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
    """The failure boundary of a write API: a refusal raises its fixed error; the M3 fence
    errors pass through unchanged; a unique violation is ``StageConflictError``; every other
    ordinary exception is ``StageDatabaseError``. Raised after the handler (no cause or
    context). Process control propagates as the same object."""
    done: list[T] = []
    error: type[ReviewStageError] | None = None
    try:
        done.append(body())
    except _Refusal as refusal:
        error = refusal.error
    except (LeaseLostError, FenceClosedError, JobLockTimeoutError):
        raise
    except Exception as failure:  # classified here; the exception is not retained
        error = StageConflictError if _sqlstate(failure) == UNIQUE_VIOLATION else StageDatabaseError
    if error is not None:
        raise error()
    return done[0]


# --- fence association ----------------------------------------------------------------------------


@dataclass
class _Context:
    session: FencedSession
    job: JobSnapshot
    token: JobLeaseToken
    review_id: UUID
    review: Any

    @property
    def tenant_id(self) -> UUID:
        return self.job.tenant_id

    @property
    def current_attempt(self) -> int:
        return self.token.attempt


def _fence_parts(fence: object) -> tuple[FencedSession, JobSnapshot]:
    """The fence's session and job (an argument check: ``InvalidStageRequestError``)."""

    def build() -> tuple[FencedSession, JobSnapshot]:
        session = getattr(fence, "session")  # noqa: B009 - structural protocol access
        job = getattr(fence, "job")  # noqa: B009
        if type(session) is not FencedSession or type(job) is not JobSnapshot:
            raise TypeError
        return session, job

    return _arguments(build)


def _associate(session: FencedSession, job: JobSnapshot, review_id: UUID) -> _Context:
    """Steps 1-4: canonical job, lease token, ownership recheck, review row."""
    _require(
        job.kind == REVIEW_JOB_KIND and job.idempotency_key == str(review_id),
        StageFenceMismatchError,
    )
    tokens: list[JobLeaseToken] = []
    with suppress(InvalidJobTransitionError):
        tokens.append(job.lease_token())
    _require(bool(tokens), StageFenceMismatchError)
    token = tokens[0]
    owned, _ = recheck_ownership(session, token)
    _require(owned.tenant_id == job.tenant_id and owned.id == job.id, StageFenceMismatchError)
    review = session.execute(
        select(REVIEWS).where(REVIEWS.c.tenant_id == job.tenant_id, REVIEWS.c.id == review_id)
    ).first()
    _require(review is not None and review.run_review_job_id == job.id, StageFenceMismatchError)
    return _Context(session=session, job=job, token=token, review_id=review_id, review=review)


def _final(context: _Context) -> None:
    """Step 6: the ownership recheck after the last write (``LeaseLostError`` escapes)."""
    owned, _ = recheck_ownership(context.session, context.token)
    _require(owned.tenant_id == context.tenant_id, StageFenceMismatchError)


# --- reads ----------------------------------------------------------------------------------------


def _key(table: Table, context: _Context, question_id: str) -> Any:
    return (
        (table.c.tenant_id == context.tenant_id)
        & (table.c.review_id == context.review_id)
        & (table.c.question_id == question_id)
    )


def _plan_row(context: _Context, question_id: str) -> Any:
    return context.session.execute(
        select(PLAN_QUESTIONS).where(_key(PLAN_QUESTIONS, context, question_id))
    ).first()


def _evidence_digest(context: _Context, question_id: str) -> Any:
    return context.session.execute(
        select(QUESTION_EVIDENCE.c.evidence_sha256, QUESTION_EVIDENCE.c.job_id).where(
            _key(QUESTION_EVIDENCE, context, question_id)
        )
    ).first()


def _call_rows(context: _Context, question_id: str, stage: StageKind) -> list[Any]:
    return list(
        context.session.execute(
            select(STAGE_CALLS)
            .where(_key(STAGE_CALLS, context, question_id), STAGE_CALLS.c.stage == stage.value)
            .order_by(STAGE_CALLS.c.sequence)
        )
    )


def _stage_row(context: _Context, question_id: str, stage: StageKind) -> Any:
    return context.session.execute(
        select(STAGE_RESULTS).where(
            _key(STAGE_RESULTS, context, question_id), STAGE_RESULTS.c.stage == stage.value
        )
    ).first()


# --- row conversion (pure; any failure is StageRecordInconsistentError) ---------------------------


def _call_from_row(row: Any) -> CallRecord:
    stage = StageKind(row.stage)
    usage = (
        None
        if row.input_tokens is None and row.output_tokens is None
        else ModelUsage(row.input_tokens, row.output_tokens)
    )
    rejection = (
        None
        if row.rejection_reason is None
        else CallRejection(
            stage=stage,
            reason=RejectionReason(row.rejection_reason),
            item_index=row.rejection_item_index,
            citation_index=row.rejection_citation_index,
            rejected_count=row.rejection_count,
        )
    )
    return CallRecord(
        tenant_id=row.tenant_id,
        review_id=row.review_id,
        job_id=row.job_id,
        question_id=row.question_id,
        stage=stage,
        sequence=row.sequence,
        call_kind=CallKind(row.call_kind),
        request_basis=RequestBasis(row.request_basis),
        request_sha256=row.request_sha256,
        prompt_sha256=row.prompt_sha256,
        model_requested=row.model_requested,
        max_output_tokens=row.max_output_tokens,
        timeout_ms=row.timeout_ms,
        evidence_sha256=row.evidence_sha256,
        dependency_sha256=row.dependency_sha256,
        job_attempt=row.job_attempt,
        state=ReservationState(row.state),
        started_at=row.started_at,
        completed_at=row.completed_at,
        outcome=None if row.outcome is None else CallOutcome(row.outcome),
        dispatched=row.dispatched,
        model_used=row.model_used,
        usage=usage,
        latency_ms=row.latency_ms,
        rejection=rejection,
    )


def _content_bytes(row: Any) -> bytes:
    stored = row.content_canonical
    if type(stored) is not str:
        raise TypeError
    return stored.encode("ascii")


def _stage_from_row(row: Any) -> StageRecord:
    outcome = StageOutcome(row.outcome)
    content: VerifiedQuestion | AnalyzedQuestion | None = None
    if outcome is StageOutcome.VERIFIED:
        content = decode_verified(_content_bytes(row), content_sha256=row.content_sha256)
    elif outcome is StageOutcome.ANALYZED:
        content = decode_analyzed(_content_bytes(row), content_sha256=row.content_sha256)
    record = StageRecord(
        tenant_id=row.tenant_id,
        review_id=row.review_id,
        job_id=row.job_id,
        question_id=row.question_id,
        stage=StageKind(row.stage),
        outcome=outcome,
        unresolved_reason=(
            None if row.unresolved_reason is None else UnresolvedReason(row.unresolved_reason)
        ),
        call_sequence=row.call_sequence,
        request_sha256=row.request_sha256,
        evidence_sha256=row.evidence_sha256,
        dependency_sha256=row.dependency_sha256,
        content=content,
        job_attempt=row.job_attempt,
        committed_at=row.committed_at,
    )
    if record.content_sha256 != row.content_sha256:
        raise ValueError
    return record


def _history(
    *,
    tenant_id: UUID,
    review_id: UUID,
    job_id: UUID,
    question_id: str,
    stage: StageKind,
    current_attempt: int,
    calls: list[Any],
    stage_row: Any,
) -> StageHistory:
    def build() -> StageHistory:
        return StageHistory(
            tenant_id=tenant_id,
            review_id=review_id,
            job_id=job_id,
            question_id=question_id,
            stage=stage,
            current_attempt=current_attempt,
            calls=tuple(_call_from_row(row) for row in calls),
            committed=None if stage_row is None else _stage_from_row(stage_row),
        )

    return _guarded(build, StageRecordInconsistentError)


def _evidence_state_holds(
    evidence: str | None, calls: tuple[CallRecord, ...], stage: StageRecord | None
) -> bool:
    """E7 (clarification B) for a verification stage: a well-formed U4 has no evidence row and
    no calls; calls without evidence, a non-U4 stage without evidence and a U4 with calls or
    evidence are inconsistent; every reference must equal the stored evidence digest."""
    if calls and evidence is None:
        return False
    if any(call.evidence_sha256 != evidence for call in calls):
        return False
    if stage is None:
        return True
    if stage.shape is StageShape.U4:
        return not calls and evidence is None
    return evidence is not None and stage.evidence_sha256 == evidence


def _state(
    context: _Context, question_id: str, stage: StageKind
) -> tuple[StageHistory, str | None]:
    """The stored history of one stage with the canonical job and current attempt, and (for
    verification) the stored evidence digest, checked against E7."""
    calls = _call_rows(context, question_id, stage)
    stage_row = _stage_row(context, question_id, stage)
    evidence_row = (
        _evidence_digest(context, question_id) if stage is StageKind.VERIFICATION else None
    )
    _require(
        all(row.job_id == context.job.id for row in calls)
        and (stage_row is None or stage_row.job_id == context.job.id),
        StageRecordInconsistentError,
    )
    history = _history(
        tenant_id=context.tenant_id,
        review_id=context.review_id,
        job_id=context.job.id,
        question_id=question_id,
        stage=stage,
        current_attempt=context.current_attempt,
        calls=calls,
        stage_row=stage_row,
    )
    evidence = None if evidence_row is None else evidence_row.evidence_sha256
    if stage is StageKind.VERIFICATION:
        _require(
            _evidence_state_holds(evidence, history.calls, history.committed),
            StageRecordInconsistentError,
        )
    return history, evidence


def _owner_dependency(context: _Context, question_id: str, plan: Any) -> tuple[Any, str | None]:
    """The owner verification row of ``question_id`` and the dependency digest derived from it
    (``None`` if no verification stage is committed)."""
    owner = _stage_row(context, question_id, StageKind.VERIFICATION)
    if owner is None:
        return None, None

    def derive() -> str:
        outcome = StageOutcome(owner.outcome)
        return dependency_sha256(
            tenant_id=context.tenant_id,
            review_id=context.review_id,
            question_id=question_id,
            question_sha256=plan.question_sha256,
            owner_outcome=outcome,
            owner_content_sha256=(
                owner.content_sha256 if outcome is StageOutcome.VERIFIED else None
            ),
            owner_reason=(
                None
                if owner.unresolved_reason is None
                else UnresolvedReason(owner.unresolved_reason)
            ),
        )

    return owner, _guarded(derive, StageRecordInconsistentError)


# --- planned questions ----------------------------------------------------------------------------


def record_planned_questions(fence: StageFence, planned: PlannedQuestionSet) -> PlannedQuestionSet:
    """Store the review's planned questions once (positions and ``eg-review-plan-question-v1``
    digests). An identical stored set is a replay; any other stored row is a conflict.
    Persistence cannot prove that the set came from the pinned template."""
    session, job = _fence_parts(fence)
    checked = _arguments(lambda: revalidated_planned(planned))

    def body() -> PlannedQuestionSet:
        context = _associate(session, job, checked.review_id)
        _require(checked.tenant_id == context.tenant_id, StageBindingError)
        rows = list(
            session.execute(
                select(PLAN_QUESTIONS)
                .where(
                    PLAN_QUESTIONS.c.tenant_id == context.tenant_id,
                    PLAN_QUESTIONS.c.review_id == context.review_id,
                )
                .order_by(PLAN_QUESTIONS.c.position)
            )
        )
        expected = [
            (position, question.question_id, digest)
            for position, (question, digest) in enumerate(
                zip(checked.questions, checked.question_sha256s, strict=True)
            )
        ]
        if rows:
            stored = [(row.position, row.question_id, row.question_sha256) for row in rows]
            _require(stored == expected, StageConflictError)
        else:
            session.execute(
                insert(PLAN_QUESTIONS).values(
                    [
                        {
                            "tenant_id": context.tenant_id,
                            "review_id": context.review_id,
                            "job_id": job.id,
                            "question_id": question_id,
                            "position": position,
                            "question_sha256": digest,
                            "job_attempt": context.current_attempt,
                        }
                        for position, question_id, digest in expected
                    ]
                )
            )
        _final(context)
        return checked

    return _write(body)


# --- in-run read ----------------------------------------------------------------------------------


def _checked_identity(review_id: object, question_id: object, stage: object) -> StageKind:
    def build() -> StageKind:
        if type(review_id) is not UUID or not is_question_id(question_id):
            raise TypeError
        if type(stage) is not StageKind:
            raise TypeError
        return stage

    return _arguments(build)


def read_stage_state(
    fence: StageFence, review_id: UUID, question_id: str, stage: StageKind
) -> StageState:
    """The stored history (with ``current_attempt`` from the fence), its plan and the digest
    references for M5g's in-run decisions. Constructor-validated and digest-checked; not
    provenance-trusted. Writes nothing."""
    session, job = _fence_parts(fence)
    kind = _checked_identity(review_id, question_id, stage)

    def body() -> StageState:
        context = _associate(session, job, review_id)
        plan = _plan_row(context, question_id)
        _require(plan is not None, StageNotPlannedError)
        history, evidence = _state(context, question_id, kind)
        dependency: str | None = None
        if kind is StageKind.ANALYSIS:
            _, dependency = _owner_dependency(context, question_id, plan)
        return _guarded(
            lambda: StageState(
                history=history,
                plan=plan_stage(history),
                evidence_sha256=evidence,
                dependency_sha256=dependency,
            ),
            StageRecordInconsistentError,
        )

    return _write(body)


# --- evidence (the shared evidence sequence E1-E8) ------------------------------------------------


def _evidence_bindings(context: _Context, record: EvidenceRecord) -> None:
    """E3-E6 against the review row and the stored plan."""
    review = context.review
    result = record.result
    _require(
        record.tenant_id == context.tenant_id and record.review_id == context.review_id,
        StageBindingError,
    )
    plan = _plan_row(context, record.question_id)
    _require(plan is not None, StageNotPlannedError)
    _require(plan.question_sha256 == record.question_sha256, StageBindingError)
    _require(
        result.snapshot_sha256 == review.snapshot_sha256
        and result.tenant_id == review.tenant_id
        and result.vendor_id == review.vendor_id
        and result.snapshot.profile_id == review.profile_id
        and result.profile_fingerprint == review.fingerprint
        and result.config_sha256 == review.retrieval_config_sha256,
        StageBindingError,
    )
    _require(
        result.k == review.retrieval_k
        and result.query_count == len(record.question.search_queries),
        StageBindingError,
    )


def record_evidence(fence: StageFence, evidence: EvidenceRecord) -> EvidenceRecord:
    """Store a planned question's evidence before its first verification reservation (E1-E8).
    An identical stored record is a replay; a committed U4 stage is closed
    (``StageConflictError``); an oversized record is ``EvidenceTooLargeError`` after the same
    binding checks (use U4)."""
    session, job = _fence_parts(fence)
    record = _arguments(lambda: revalidated_evidence(evidence))  # E1

    def body() -> EvidenceRecord:
        context = _associate(session, job, record.review_id)  # E2
        _evidence_bindings(context, record)  # E3-E6
        history, stored = _state(context, record.question_id, StageKind.VERIFICATION)  # E7
        if stored is not None:
            canonical = session.execute(
                select(QUESTION_EVIDENCE.c.evidence_canonical).where(
                    _key(QUESTION_EVIDENCE, context, record.question_id)
                )
            ).scalar_one()
            _require(
                type(canonical) is str and canonical.encode("ascii") == record.canonical,
                StageConflictError,
            )
            _final(context)
            return record
        committed = history.committed
        _require(committed is None or committed.shape is not StageShape.U4, StageConflictError)
        _require(committed is None, StageRecordInconsistentError)
        _require(record.fits_storage, EvidenceTooLargeError)  # E8
        session.execute(
            insert(QUESTION_EVIDENCE).values(
                tenant_id=context.tenant_id,
                review_id=context.review_id,
                job_id=job.id,
                question_id=record.question_id,
                question_sha256=record.question_sha256,
                snapshot_sha256=record.snapshot_sha256,
                evidence_sha256=record.evidence_sha256,
                evidence_canonical=record.canonical.decode("ascii"),
                item_count=record.item_count,
                job_attempt=context.current_attempt,
            )
        )
        _final(context)
        return record

    return _write(body)


# --- reservation ----------------------------------------------------------------------------------


def _configuration_holds(review: Any, stage: StageKind, question_id: str, request: Any) -> bool:
    """M5e-G: the request against the review row, by value (``timeout_ms`` included, which the
    M5a digest excludes)."""
    if stage is StageKind.VERIFICATION:
        prompt = (
            review.verifier_prompt_id,
            review.verifier_prompt_version,
            review.verifier_prompt_sha256,
        )
    else:
        prompt = (
            review.analyst_prompt_id,
            review.analyst_prompt_version,
            review.analyst_prompt_sha256,
        )
    reference = request.prompt
    return bool(
        request.purpose is stage.purpose
        and request.question_id == question_id
        and request.model_id == review.model_id
        and request.max_output_tokens == review.max_output_tokens
        and request.timeout_ms == review.timeout_ms
        and (reference.prompt_id, reference.version, reference.sha256) == prompt
        and _text_sha256(request.system_text) == reference.sha256
    )


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def reserve_call(
    fence: StageFence,
    review_id: UUID,
    question_id: str,
    stage: StageKind,
    *,
    sequence: int,
    call_kind: CallKind,
    request_basis: RequestBasis,
    request: StructuredRequest,
) -> CallRecord:
    """Plan under the job lock and insert the ``started`` reservation only if it equals
    ``PlanDispatch``. Not replayable: a second call for the same sequence finds the plan moved
    on (``StageCallInFlightError``, ``StageConflictError`` or ``StageBudgetExhaustedError``)."""
    session, job = _fence_parts(fence)
    kind = _checked_identity(review_id, question_id, stage)

    def arguments() -> StructuredRequest:
        if type(sequence) is not int or type(call_kind) is not CallKind:
            raise TypeError
        if type(request_basis) is not RequestBasis or not 1 <= sequence <= 3:
            raise TypeError
        return revalidated_request(request)

    checked = _arguments(arguments)

    def body() -> CallRecord:
        context = _associate(session, job, review_id)
        plan_row = _plan_row(context, question_id)
        _require(plan_row is not None, StageNotPlannedError)
        history, evidence = _state(context, question_id, kind)
        plan = _guarded(lambda: plan_stage(history), StageRecordInconsistentError)
        if isinstance(plan, PlanReuse):
            _refuse(StageConflictError)
        if isinstance(plan, PlanInFlight):
            _refuse(StageCallInFlightError)
        if isinstance(plan, PlanExhausted):
            _refuse(StageBudgetExhaustedError)
        assert isinstance(plan, PlanDispatch)
        _require(
            plan.sequence == sequence
            and plan.call_kind is call_kind
            and plan.request_basis is request_basis,
            StagePlanMismatchError,
        )
        if plan.required_request_sha256 is not None:
            _require(checked.request_sha256 == plan.required_request_sha256, StagePlanMismatchError)
        if plan.original_request_sha256 is not None:
            _require(checked.request_sha256 != plan.original_request_sha256, StagePlanMismatchError)
        _require(
            _configuration_holds(context.review, kind, question_id, checked), StageBindingError
        )
        dependency: str | None = None
        if kind is StageKind.VERIFICATION:
            _require(evidence is not None, StageDependencyError)
        else:
            owner, dependency = _owner_dependency(context, question_id, plan_row)
            _require(
                owner is not None and owner.outcome == StageOutcome.VERIFIED.value,
                StageDependencyError,
            )
            _require(
                all(call.dependency_sha256 == dependency for call in history.calls),
                StageRecordInconsistentError,
            )
        started = session.execute(
            insert(STAGE_CALLS)
            .values(
                tenant_id=context.tenant_id,
                review_id=context.review_id,
                job_id=job.id,
                question_id=question_id,
                stage=kind.value,
                call_kind=call_kind.value,
                request_basis=request_basis.value,
                state=ReservationState.STARTED.value,
                sequence=sequence,
                request_sha256=checked.request_sha256,
                prompt_sha256=checked.prompt.sha256,
                model_requested=checked.model_id,
                max_output_tokens=checked.max_output_tokens,
                timeout_ms=checked.timeout_ms,
                job_attempt=context.current_attempt,
                evidence_sha256=evidence,
                dependency_sha256=dependency,
            )
            .returning(STAGE_CALLS.c.started_at)
        ).scalar_one()
        record = _guarded(
            lambda: CallRecord(
                tenant_id=context.tenant_id,
                review_id=context.review_id,
                job_id=job.id,
                question_id=question_id,
                stage=kind,
                sequence=sequence,
                call_kind=call_kind,
                request_basis=request_basis,
                request_sha256=checked.request_sha256,
                prompt_sha256=checked.prompt.sha256,
                model_requested=checked.model_id,
                max_output_tokens=checked.max_output_tokens,
                timeout_ms=checked.timeout_ms,
                evidence_sha256=evidence,
                dependency_sha256=dependency,
                job_attempt=context.current_attempt,
                state=ReservationState.STARTED,
                started_at=started,
            ),
            StageRecordInconsistentError,
        )
        _final(context)
        return record

    return _write(body)


# --- completion (the shared binding rule B1-B9) ---------------------------------------------------


@dataclass(frozen=True)
class _Completion:
    """The derived completion metadata (B9): the only values compared on replay or written."""

    outcome: CallOutcome
    dispatched: bool
    model_used: str | None
    usage: ModelUsage | None
    latency_ms: int | None
    rejection: CallRejection | None

    def values(self) -> dict[str, Any]:
        rejection = self.rejection
        return {
            "outcome": self.outcome.value,
            "dispatched": self.dispatched,
            "model_used": self.model_used,
            "input_tokens": None if self.usage is None else self.usage.input_tokens,
            "output_tokens": None if self.usage is None else self.usage.output_tokens,
            "latency_ms": self.latency_ms,
            "rejection_reason": None if rejection is None else rejection.reason.value,
            "rejection_item_index": None if rejection is None else rejection.item_index,
            "rejection_citation_index": None if rejection is None else rejection.citation_index,
            "rejection_count": None if rejection is None else rejection.rejected_count,
        }


def _derived(result: StructuredResult, rejection: CallRejection | None) -> _Completion:
    return _Completion(
        outcome=result.outcome,
        dispatched=result.dispatched,
        model_used=result.model_used,
        usage=result.usage,
        latency_ms=result.latency_ms,
        rejection=rejection,
    )


def _stored(call: CallRecord) -> _Completion | None:
    if call.state is ReservationState.STARTED:
        return None
    assert call.outcome is not None and call.dispatched is not None
    return _Completion(
        outcome=call.outcome,
        dispatched=call.dispatched,
        model_used=call.model_used,
        usage=call.usage,
        latency_ms=call.latency_ms,
        rejection=call.rejection,
    )


@dataclass
class _Selected:
    context: _Context
    row: Any
    call: CallRecord
    history: StageHistory


def _select_call(
    session: FencedSession,
    job: JobSnapshot,
    review_id: UUID,
    question_id: str,
    stage: StageKind,
    sequence: int,
) -> _Selected:
    """B2-B3: association, then the call selected by ``(tenant, review, question_id, stage,
    sequence)`` from the explicit arguments (clarification A), its canonical job and a valid
    history."""
    context = _associate(session, job, review_id)
    row = session.execute(
        select(STAGE_CALLS).where(
            _key(STAGE_CALLS, context, question_id),
            STAGE_CALLS.c.stage == stage.value,
            STAGE_CALLS.c.sequence == sequence,
        )
    ).first()
    _require(row is not None, StagePlanMismatchError)
    assert row is not None
    _require(row.job_id == job.id, StageRecordInconsistentError)
    history, _ = _state(context, question_id, stage)
    call = history.calls[sequence - 1]
    return _Selected(context=context, row=row, call=call, history=history)


def _bind_result(selected: _Selected, result: StructuredResult, stage: StageKind) -> None:
    """B4-B5: the result's question against the selected call, then purpose, digest and
    model. A well-formed result can carry any digest, so B5 never substitutes for B4."""
    call = selected.call
    _require(result.question_id == call.question_id, StageBindingError)
    _require(
        result.purpose is stage.purpose
        and result.request_sha256 == call.request_sha256
        and result.model_requested == call.model_requested,
        StageBindingError,
    )


def _mutation_preconditions(selected: _Selected) -> None:
    """M1-M3, only when no completed call or stage exists for the identity."""
    _require(selected.call.state is ReservationState.STARTED, StageConflictError)
    _require(selected.call.job_attempt == selected.context.current_attempt, StageCallAbandonedError)
    _require(selected.history.committed is None, StageConflictError)


def _complete(selected: _Selected, completion: _Completion) -> Any:
    """The guarded completion update (key, ``started`` and the current attempt)."""
    call = selected.call
    context = selected.context
    row = context.session.execute(
        update(STAGE_CALLS)
        .where(
            _key(STAGE_CALLS, context, call.question_id),
            STAGE_CALLS.c.stage == call.stage.value,
            STAGE_CALLS.c.sequence == call.sequence,
            STAGE_CALLS.c.state == ReservationState.STARTED.value,
            STAGE_CALLS.c.job_attempt == context.current_attempt,
        )
        .values(
            state=ReservationState.COMPLETED.value,
            completed_at=func.clock_timestamp(),
            **completion.values(),
        )
        .returning(*STAGE_CALLS.c)
    ).first()
    _require(row is not None, StageConflictError)
    return row


def complete_failed_call(
    fence: StageFence,
    review_id: UUID,
    question_id: str,
    stage: StageKind,
    *,
    sequence: int,
    result: StructuredResult,
    rejection: ProvenanceRejection | None,
) -> CallRecord:
    """Complete a reservation with a non-success (any outcome other than ``completed``, or
    ``completed`` with a provenance rejection); writes no stage. B1-B9, then replay, then
    M1-M3."""
    session, job = _fence_parts(fence)
    kind = _checked_identity(review_id, question_id, stage)

    def arguments() -> tuple[StructuredResult, ProvenanceRejection | None]:
        if type(sequence) is not int or not 1 <= sequence <= 3:
            raise TypeError
        checked = revalidated_result(result)
        checked_rejection = None if rejection is None else revalidated_rejection(rejection)
        if (checked.outcome is CallOutcome.COMPLETED) != (checked_rejection is not None):
            raise TypeError
        return checked, checked_rejection

    checked_result, checked_rejection = _arguments(arguments)  # B1

    def body() -> CallRecord:
        selected = _select_call(session, job, review_id, question_id, kind, sequence)  # B2-B3
        _bind_result(selected, checked_result, kind)  # B4-B5
        stored_rejection: CallRejection | None = None
        if checked_rejection is not None:  # B6, before conversion
            _require(
                checked_rejection.question_id == selected.call.question_id
                and checked_rejection.stage is kind.rejection_stage,
                StageBindingError,
            )
            stored_rejection = _guarded(
                lambda: CallRejection.from_rejection(checked_rejection), StageBindingError
            )
        completion = _derived(checked_result, stored_rejection)  # B9
        previous = _stored(selected.call)
        if previous is not None:  # replay before mutation preconditions
            _require(previous == completion, StageConflictError)
            _final(selected.context)
            return selected.call
        _mutation_preconditions(selected)
        row = _complete(selected, completion)
        record = _guarded(lambda: _call_from_row(row), StageRecordInconsistentError)
        _final(selected.context)
        return record

    return _write(body)


def _success_arguments(
    review_id: object, question_id: object, sequence: object, result: object
) -> StructuredResult:
    def build() -> StructuredResult:
        if type(review_id) is not UUID or not is_question_id(question_id):
            raise TypeError
        if type(sequence) is not int or not 1 <= sequence <= 3:
            raise TypeError
        checked = revalidated_result(result)
        if checked.outcome is not CallOutcome.COMPLETED:
            raise TypeError
        return checked

    return _arguments(build)


def _commit_success(
    selected: _Selected,
    completion: _Completion,
    *,
    outcome: StageOutcome,
    content: VerifiedQuestion | AnalyzedQuestion,
) -> StageRecord:
    """Replay against a stored stage, or M1-M3 then the call update and the stage insert in the
    caller's transaction."""
    call = selected.call
    context = selected.context
    expected = _guarded(
        lambda: StageRecord(
            tenant_id=context.tenant_id,
            review_id=context.review_id,
            job_id=context.job.id,
            question_id=call.question_id,
            stage=call.stage,
            outcome=outcome,
            unresolved_reason=None,
            call_sequence=call.sequence,
            request_sha256=call.request_sha256,
            evidence_sha256=call.evidence_sha256,
            dependency_sha256=call.dependency_sha256,
            content=content,
            job_attempt=context.current_attempt,
            committed_at=call.started_at,
        ),
        StageBindingError,
    )
    committed = selected.history.committed
    if committed is not None:  # replay: the stage and the referenced call's completion
        _require(
            committed.shape is expected.shape
            and committed.call_sequence == expected.call_sequence
            and committed.request_sha256 == expected.request_sha256
            and committed.evidence_sha256 == expected.evidence_sha256
            and committed.dependency_sha256 == expected.dependency_sha256
            and committed.content_canonical == expected.content_canonical
            and _stored(call) == completion,
            StageConflictError,
        )
        _final(context)
        return committed
    _mutation_preconditions(selected)
    _complete(selected, completion)
    stamp = context.session.execute(
        insert(STAGE_RESULTS)
        .values(
            tenant_id=context.tenant_id,
            review_id=context.review_id,
            job_id=context.job.id,
            question_id=call.question_id,
            stage=call.stage.value,
            outcome=outcome.value,
            job_attempt=context.current_attempt,
            call_sequence=call.sequence,
            request_sha256=call.request_sha256,
            evidence_sha256=expected.evidence_sha256,
            dependency_sha256=expected.dependency_sha256,
            content_sha256=expected.content_sha256,
            content_canonical=cast(bytes, expected.content_canonical).decode("ascii"),
        )
        .returning(STAGE_RESULTS.c.committed_at)
    ).scalar_one()
    record = _guarded(
        lambda: StageRecord(
            tenant_id=context.tenant_id,
            review_id=context.review_id,
            job_id=context.job.id,
            question_id=call.question_id,
            stage=call.stage,
            outcome=outcome,
            unresolved_reason=None,
            call_sequence=call.sequence,
            request_sha256=call.request_sha256,
            evidence_sha256=expected.evidence_sha256,
            dependency_sha256=expected.dependency_sha256,
            content=content,
            job_attempt=context.current_attempt,
            committed_at=stamp,
        ),
        StageRecordInconsistentError,
    )
    _final(context)
    return record


def commit_verified(
    fence: StageFence,
    review_id: UUID,
    question_id: str,
    *,
    sequence: int,
    result: StructuredResult,
    verified: VerifiedQuestion,
) -> StageRecord:
    """Complete a verification reservation with its success and insert the S1 stage atomically.
    The call is selected from the explicit ``question_id`` and the fixed stage verification
    (clarification A); B4 then binds the result's question and B7 the content's identity."""
    session, job = _fence_parts(fence)
    checked_result = _success_arguments(review_id, question_id, sequence, result)  # B1
    content = _arguments(lambda: revalidated_verified(verified))
    stage = StageKind.VERIFICATION

    def body() -> StageRecord:
        selected = _select_call(session, job, review_id, question_id, stage, sequence)  # B2-B3
        _bind_result(selected, checked_result, stage)  # B4-B5
        call = selected.call
        _require(  # B7
            content.tenant_id == selected.context.tenant_id
            and content.review_id == review_id
            and content.question_id == call.question_id
            and content.request_sha256 == call.request_sha256
            and content.snapshot_sha256 == selected.context.review.snapshot_sha256,
            StageBindingError,
        )
        completion = _derived(checked_result, None)  # B9
        return _commit_success(selected, completion, outcome=StageOutcome.VERIFIED, content=content)

    return _write(body)


def commit_analyzed(
    fence: StageFence,
    review_id: UUID,
    question_id: str,
    *,
    sequence: int,
    result: StructuredResult,
    analyzed: AnalyzedQuestion,
    owner: VerifiedQuestion,
) -> StageRecord:
    """Complete an analysis reservation with its success and insert the S2 stage atomically. The
    owner must be the committed verification of the same question (B8); ``shared`` is always
    empty (P9). Clarification A applies as for ``commit_verified``."""
    session, job = _fence_parts(fence)
    checked_result = _success_arguments(review_id, question_id, sequence, result)  # B1
    content = _arguments(lambda: revalidated_analyzed(analyzed))
    checked_owner = _arguments(lambda: revalidated_verified(owner))
    stage = StageKind.ANALYSIS

    def body() -> StageRecord:
        selected = _select_call(session, job, review_id, question_id, stage, sequence)  # B2-B3
        _bind_result(selected, checked_result, stage)  # B4-B5
        call = selected.call
        context = selected.context
        _require(  # B7
            content.tenant_id == context.tenant_id
            and content.review_id == review_id
            and content.question_id == call.question_id
            and content.request_sha256 == call.request_sha256,
            StageBindingError,
        )
        _require(  # B8
            checked_owner.tenant_id == content.tenant_id
            and checked_owner.review_id == content.review_id
            and checked_owner.question_id == content.question_id,
            StageDependencyError,
        )
        plan = _plan_row(context, call.question_id)
        _require(plan is not None, StageRecordInconsistentError)
        owner_row, dependency = _owner_dependency(context, call.question_id, plan)
        _require(
            owner_row is not None and owner_row.outcome == StageOutcome.VERIFIED.value,
            StageDependencyError,
        )
        owner_digest = _guarded(lambda: _sha(encode_verified(checked_owner)), StageDependencyError)
        _require(owner_digest == owner_row.content_sha256, StageDependencyError)
        _require(dependency == call.dependency_sha256, StageDependencyError)
        completion = _derived(checked_result, None)  # B9
        return _commit_success(selected, completion, outcome=StageOutcome.ANALYZED, content=content)

    return _write(body)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --- unresolved stages ----------------------------------------------------------------------------


def _expected_unresolved(
    context: _Context,
    question_id: str,
    stage: StageKind,
    reason: UnresolvedReason,
    history: StageHistory,
    evidence: str | None,
    plan_row: Any,
) -> dict[str, Any]:
    """The derived references of the requested shape against the stored history without its
    committed stage (``StagePlanMismatchError`` or ``StageDependencyError`` otherwise)."""
    calls = history.calls
    plan = _guarded(lambda: plan_without_stage(history), StageRecordInconsistentError)
    last = calls[-1] if calls else None
    refs: dict[str, Any] = {
        "call_sequence": None,
        "request_sha256": None,
        "evidence_sha256": None,
        "dependency_sha256": None,
    }
    owner, dependency = (
        _owner_dependency(context, question_id, plan_row)
        if stage is StageKind.ANALYSIS
        else (None, None)
    )
    if reason in AFTER_CALL_REASONS:  # U1
        _require(
            last is not None
            and last.state is ReservationState.COMPLETED
            and isinstance(plan, PlanExhausted)
            and plan.reason is reason,
            StagePlanMismatchError,
        )
    elif reason is UnresolvedReason.CALL_ABANDONED:  # U2
        _require(
            last is not None
            and len(calls) == 3
            and last.state is ReservationState.STARTED
            and last.job_attempt < context.current_attempt,
            StagePlanMismatchError,
        )
    elif reason is UnresolvedReason.REPAIR_REQUEST_TOO_LARGE:  # U6
        _require(
            last is not None
            and isinstance(plan, PlanDispatch)
            and plan.call_kind is CallKind.REPAIR
            and plan.trigger == last.sequence,
            StagePlanMismatchError,
        )
    else:  # U3 and U5: no calls
        _require(not calls, StagePlanMismatchError)
    if last is not None:
        refs["call_sequence"] = last.sequence
        refs["request_sha256"] = last.request_sha256
        refs["evidence_sha256"] = last.evidence_sha256
        refs["dependency_sha256"] = last.dependency_sha256
        return refs
    if reason is UnresolvedReason.VERIFICATION_UNRESOLVED:  # U3
        _require(
            owner is not None and owner.outcome == StageOutcome.UNRESOLVED.value,
            StageDependencyError,
        )
        refs["dependency_sha256"] = dependency
    elif stage is StageKind.VERIFICATION:  # U5 verification
        _require(evidence is not None, StageDependencyError)
        refs["evidence_sha256"] = evidence
    else:  # U5 analysis
        _require(
            owner is not None and owner.outcome == StageOutcome.VERIFIED.value,
            StageDependencyError,
        )
        refs["dependency_sha256"] = dependency
    return refs


def _insert_unresolved(
    context: _Context, question_id: str, stage: StageKind, reason: UnresolvedReason, refs: Any
) -> StageRecord:
    stamp = context.session.execute(
        insert(STAGE_RESULTS)
        .values(
            tenant_id=context.tenant_id,
            review_id=context.review_id,
            job_id=context.job.id,
            question_id=question_id,
            stage=stage.value,
            outcome=StageOutcome.UNRESOLVED.value,
            unresolved_reason=reason.value,
            job_attempt=context.current_attempt,
            **refs,
        )
        .returning(STAGE_RESULTS.c.committed_at)
    ).scalar_one()
    return _guarded(
        lambda: StageRecord(
            tenant_id=context.tenant_id,
            review_id=context.review_id,
            job_id=context.job.id,
            question_id=question_id,
            stage=stage,
            outcome=StageOutcome.UNRESOLVED,
            unresolved_reason=reason,
            content=None,
            job_attempt=context.current_attempt,
            committed_at=stamp,
            **refs,
        ),
        StageRecordInconsistentError,
    )


def _same_unresolved(committed: StageRecord, reason: UnresolvedReason, refs: Any) -> bool:
    return bool(
        committed.outcome is StageOutcome.UNRESOLVED
        and committed.unresolved_reason is reason
        and committed.call_sequence == refs["call_sequence"]
        and committed.request_sha256 == refs["request_sha256"]
        and committed.evidence_sha256 == refs["evidence_sha256"]
        and committed.dependency_sha256 == refs["dependency_sha256"]
    )


def _commit_oversized(context: _Context, record: EvidenceRecord, question_id: str) -> StageRecord:
    """U4 (clarification B): E3-E8 on the supplied record (E8 requires it **not** to fit), then
    identical replay, conflict or the insert of a stage with no references."""
    _require(record.question_id == question_id, StageBindingError)
    _evidence_bindings(context, record)  # E3-E6
    history, evidence = _state(context, question_id, StageKind.VERIFICATION)  # E7
    _require(not record.fits_storage, StagePlanMismatchError)  # E8
    committed = history.committed
    if committed is not None:
        _require(committed.shape is StageShape.U4, StageConflictError)
        _final(context)
        return committed
    _require(evidence is None, StageConflictError)
    _require(not history.calls, StageRecordInconsistentError)
    refs = {
        "call_sequence": None,
        "request_sha256": None,
        "evidence_sha256": None,
        "dependency_sha256": None,
    }
    stage = _insert_unresolved(
        context, question_id, StageKind.VERIFICATION, UnresolvedReason.EVIDENCE_TOO_LARGE, refs
    )
    _final(context)
    return stage


def commit_unresolved(
    fence: StageFence,
    review_id: UUID,
    question_id: str,
    stage: StageKind,
    *,
    reason: UnresolvedReason,
    evidence: EvidenceRecord | None = None,
) -> StageRecord:
    """Insert an unresolved stage (U1-U6) whose references are all derived from the stored
    history. ``evidence`` is required for, and only for, ``evidence_too_large`` (U4). An
    identical stored stage is a replay; another stored outcome or reason is a conflict. U5 and U6
    are trusted-caller size assertions (M5e-H)."""
    session, job = _fence_parts(fence)
    kind = _checked_identity(review_id, question_id, stage)

    def arguments() -> tuple[UnresolvedReason, EvidenceRecord | None]:
        if type(reason) is not UnresolvedReason:
            raise TypeError
        oversized = reason is UnresolvedReason.EVIDENCE_TOO_LARGE
        if oversized != (evidence is not None):
            raise TypeError
        if oversized and kind is not StageKind.VERIFICATION:
            raise TypeError
        if reason is UnresolvedReason.VERIFICATION_UNRESOLVED and kind is not StageKind.ANALYSIS:
            raise TypeError
        return reason, None if evidence is None else revalidated_evidence(evidence)

    checked_reason, record = _arguments(arguments)

    def body() -> StageRecord:
        context = _associate(session, job, review_id)
        if record is not None:
            _require(record.review_id == review_id, StageBindingError)
            return _commit_oversized(context, record, question_id)
        plan_row = _plan_row(context, question_id)
        _require(plan_row is not None, StageNotPlannedError)
        history, evidence_digest = _state(context, question_id, kind)
        committed = history.committed
        if committed is not None:
            _require(
                committed.outcome is StageOutcome.UNRESOLVED
                and committed.unresolved_reason is checked_reason,
                StageConflictError,
            )
        refs = _expected_unresolved(
            context, question_id, kind, checked_reason, history, evidence_digest, plan_row
        )
        if committed is not None:  # replay: outcome, reason and every derived reference
            _require(_same_unresolved(committed, checked_reason, refs), StageConflictError)
            _final(context)
            return committed
        stored = _insert_unresolved(context, question_id, kind, checked_reason, refs)
        _final(context)
        return stored

    return _write(body)


# --- trusted reload -------------------------------------------------------------------------------


@dataclass
class _Load:
    result: TrustedStages | None = None
    error: type[ReviewStageError] | None = None
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
    """Delegates the calls ``read_snapshot``, the reload and the evidence recheck make, and
    records any process-control exception they raise, so the first one still propagates if an
    ordinary cleanup failure or a later interrupt would otherwise replace it."""

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


@dataclass
class _Rows:
    review: Any
    job: Any
    plans: list[Any]
    evidence: list[Any]
    calls: list[Any]
    stages: list[Any]


def _review_scope(table: Table, tenant_id: UUID, review_id: UUID) -> Any:
    return (table.c.tenant_id == tenant_id) & (table.c.review_id == review_id)


def _read_rows(session: Any, review: TrustedReview) -> _Rows:
    """Steps 1-2: the review row, the canonical job row and every M5e row of the review."""
    tenant_id, review_id = review.tenant_id, review.review_id
    session.execute(text(f"SET LOCAL statement_timeout = {int(RELOAD_STATEMENT_TIMEOUT_MS)}"))
    review_row = session.execute(
        select(REVIEWS).where(REVIEWS.c.tenant_id == tenant_id, REVIEWS.c.id == review_id)
    ).first()
    job_row = session.execute(
        select(JOBS).where(JOBS.c.tenant_id == tenant_id, JOBS.c.id == review.job_id)
    ).first()
    plans = list(
        session.execute(
            select(PLAN_QUESTIONS)
            .where(_review_scope(PLAN_QUESTIONS, tenant_id, review_id))
            .order_by(PLAN_QUESTIONS.c.position)
        )
    )
    evidence = list(
        session.execute(
            select(QUESTION_EVIDENCE)
            .where(_review_scope(QUESTION_EVIDENCE, tenant_id, review_id))
            .order_by(QUESTION_EVIDENCE.c.question_id)
        )
    )
    calls = list(
        session.execute(
            select(STAGE_CALLS)
            .where(_review_scope(STAGE_CALLS, tenant_id, review_id))
            .order_by(STAGE_CALLS.c.question_id, STAGE_CALLS.c.stage, STAGE_CALLS.c.sequence)
        )
    )
    stages = list(
        session.execute(
            select(STAGE_RESULTS)
            .where(_review_scope(STAGE_RESULTS, tenant_id, review_id))
            .order_by(STAGE_RESULTS.c.question_id, STAGE_RESULTS.c.stage)
        )
    )
    return _Rows(review_row, job_row, plans, evidence, calls, stages)


def _settings_hold(call: CallRecord, review_row: Any) -> bool:
    prompt = (
        review_row.verifier_prompt_sha256
        if call.stage is StageKind.VERIFICATION
        else review_row.analyst_prompt_sha256
    )
    return bool(
        call.model_requested == review_row.model_id
        and call.max_output_tokens == review_row.max_output_tokens
        and call.timeout_ms == review_row.timeout_ms
        and call.prompt_sha256 == prompt
    )


def _recheck_items(
    session: Any, actor: ActorContext, review: TrustedReview, record: EvidenceRecord
) -> None:
    """Step 7: the extracted helper on the reload's own session, inside the same snapshot."""
    outcome: Any = None
    failed = False
    try:
        outcome = recheck_evidence_in_transaction(
            cast(Session, session), actor, review.snapshot, record.result.items
        )
    except Exception:  # InvalidRetrievalRequestError, RetrievalScopeError: impossible here
        failed = True
    _require(not failed, StageRecordInconsistentError)
    if isinstance(outcome, EvidenceRecheckFailure):
        _refuse(StageDatabaseError)
    if isinstance(outcome, SemanticOutcome):
        _refuse(StageRecordInconsistentError)
    _require(outcome == record.result.items, StageRecordInconsistentError)


def _owner_digest(review: TrustedReview, plan_row: Any, owner: StageRecord | None) -> str | None:
    if owner is None:
        return None
    return dependency_sha256(
        tenant_id=review.tenant_id,
        review_id=review.review_id,
        question_id=owner.question_id,
        question_sha256=plan_row.question_sha256,
        owner_outcome=owner.outcome,
        owner_content_sha256=owner.content_sha256,
        owner_reason=owner.unresolved_reason,
    )


def _question_stages(
    session: Any,
    actor: ActorContext,
    review: TrustedReview,
    rows: _Rows,
    plan_row: Any,
    question: Any,
    attempt: int,
) -> TrustedQuestionStages:
    """Steps 5-9 for one planned question."""
    question_id = question.question_id
    review_row = rows.review
    histories: dict[StageKind, StageHistory] = {}
    for kind in StageKind:
        calls = [r for r in rows.calls if r.question_id == question_id and r.stage == kind.value]
        stage_rows = [
            r for r in rows.stages if r.question_id == question_id and r.stage == kind.value
        ]
        _require(len(stage_rows) <= 1, StageRecordInconsistentError)
        histories[kind] = _history(
            tenant_id=review.tenant_id,
            review_id=review.review_id,
            job_id=review.job_id,
            question_id=question_id,
            stage=kind,
            current_attempt=attempt,
            calls=calls,
            stage_row=stage_rows[0] if stage_rows else None,
        )
        _require(
            all(_settings_hold(call, review_row) for call in histories[kind].calls),
            StageRecordInconsistentError,
        )
    verification = histories[StageKind.VERIFICATION]
    analysis = histories[StageKind.ANALYSIS]
    evidence_rows = [r for r in rows.evidence if r.question_id == question_id]
    evidence_row = evidence_rows[0] if evidence_rows else None
    stored_digest = None if evidence_row is None else evidence_row.evidence_sha256
    _require(
        _evidence_state_holds(stored_digest, verification.calls, verification.committed),
        StageRecordInconsistentError,
    )
    trusted_evidence: QuestionEvidence | None = None
    if evidence_row is not None:  # step 6
        record = _guarded(
            lambda: decode_evidence(
                cast(str, evidence_row.evidence_canonical).encode("ascii"),
                evidence_sha256=evidence_row.evidence_sha256,
                snapshot=review.snapshot,
                question=question,
            ),
            StageRecordInconsistentError,
        )
        _require(
            record.tenant_id == review.tenant_id
            and record.review_id == review.review_id
            and record.question_sha256 == plan_row.question_sha256
            and evidence_row.question_sha256 == plan_row.question_sha256
            and evidence_row.snapshot_sha256 == review.snapshot.sha256
            and evidence_row.item_count == record.item_count
            and record.result.k == review_row.retrieval_k
            and record.fits_storage,
            StageRecordInconsistentError,
        )
        _recheck_items(session, actor, review, record)  # step 7
        trusted_evidence = _guarded(
            lambda: QuestionEvidence(
                tenant_id=review.tenant_id,
                review_id=review.review_id,
                snapshot_sha256=review.snapshot.sha256,
                question=question,
                result=record.result,
            ),
            StageRecordInconsistentError,
        )
    verified_stage = verification.committed
    owner_content: VerifiedQuestion | None = None
    if verified_stage is not None and verified_stage.shape is StageShape.S1:  # step 8
        evidence_for_check = trusted_evidence
        _require(evidence_for_check is not None, StageRecordInconsistentError)
        assert evidence_for_check is not None
        owner_content = _guarded(
            lambda: recheck_verified(
                cast(VerifiedQuestion, verified_stage.content), evidence_for_check
            ),
            StageRecordInconsistentError,
        )
    dependency = _guarded(
        lambda: _owner_digest(review, plan_row, verified_stage), StageRecordInconsistentError
    )
    analysis_stage = analysis.committed
    if analysis.calls or analysis_stage is not None:  # step 9
        _require(dependency is not None, StageRecordInconsistentError)
        _require(
            all(call.dependency_sha256 == dependency for call in analysis.calls)
            and (analysis_stage is None or analysis_stage.dependency_sha256 == dependency),
            StageRecordInconsistentError,
        )
        needs_unresolved = analysis_stage is not None and analysis_stage.shape is StageShape.U3
        owner_outcome = None if verified_stage is None else verified_stage.outcome
        expected = StageOutcome.UNRESOLVED if needs_unresolved else StageOutcome.VERIFIED
        _require(owner_outcome is expected, StageRecordInconsistentError)
    if analysis_stage is not None and analysis_stage.shape is StageShape.S2:
        owner_checked = owner_content
        _require(owner_checked is not None, StageRecordInconsistentError)
        assert owner_checked is not None
        _guarded(
            lambda: recheck_analyzed(
                cast(AnalyzedQuestion, analysis_stage.content), owner_checked, question, shared=()
            ),
            StageRecordInconsistentError,
        )
    return _guarded(
        lambda: TrustedQuestionStages(
            question=question,
            evidence=trusted_evidence,
            verification=verification.committed,
            analysis=analysis.committed,
            verification_history=verification,
            analysis_history=analysis,
        ),
        StageRecordInconsistentError,
    )


def _rebuild(
    session: Any,
    actor: ActorContext,
    review: TrustedReview,
    planned: PlannedQuestionSet,
    rows: _Rows,
) -> TrustedStages:
    """Steps 1 and 3-9 over the rows read in one snapshot."""
    review_row, job = rows.review, rows.job
    _require(
        review_row is not None
        and job is not None
        and review_row.run_review_job_id == review.job_id
        and job.id == review.job_id
        and job.kind == REVIEW_JOB_KIND
        and job.idempotency_key == str(review.review_id),
        StageRecordInconsistentError,
    )
    attempt = job.attempt
    _require(type(attempt) is int and 0 <= attempt <= 10, StageRecordInconsistentError)
    every = [*rows.plans, *rows.evidence, *rows.calls, *rows.stages]
    _require(all(row.job_id == review.job_id for row in every), StageRecordInconsistentError)
    if not rows.plans:
        _require(not every, StageRecordInconsistentError)
        return _guarded(
            lambda: TrustedStages(
                tenant_id=review.tenant_id,
                review_id=review.review_id,
                job_id=review.job_id,
                job_attempt=attempt,
                questions=(),
            ),
            StageRecordInconsistentError,
        )
    _require(attempt >= 1, StageRecordInconsistentError)
    stored = [(row.position, row.question_id, row.question_sha256) for row in rows.plans]
    expected = [
        (position, question.question_id, digest)
        for position, (question, digest) in enumerate(
            zip(planned.questions, planned.question_sha256s, strict=True)
        )
    ]
    _require(stored == expected, StageRecordInconsistentError)
    planned_ids = {question.question_id for question in planned.questions}
    _require(all(row.question_id in planned_ids for row in every), StageRecordInconsistentError)
    questions = tuple(
        _question_stages(session, actor, review, rows, plan_row, question, attempt)
        for plan_row, question in zip(rows.plans, planned.questions, strict=True)
    )
    return _guarded(
        lambda: TrustedStages(
            tenant_id=review.tenant_id,
            review_id=review.review_id,
            job_id=review.job_id,
            job_attempt=attempt,
            questions=questions,
        ),
        StageRecordInconsistentError,
    )


def _load_body(
    load: _Load,
    session: Any,
    actor: ActorContext,
    review: TrustedReview,
    planned: PlannedQuestionSet,
) -> None:
    rows = _read_rows(session, review)  # ordinary failures here are database failures
    refused: type[ReviewStageError] | None = None
    try:
        load.result = _rebuild(session, actor, review, planned, rows)
    except _Refusal as refusal:
        refused = refusal.error
    except Exception:  # conversion of rows already read: the evidence helper returns failures
        refused = StageRecordInconsistentError
    if refused is not None:
        load.error = refused


def _checked_reload_arguments(
    actor: object, review: object, planned: object
) -> tuple[ActorContext, TrustedReview, PlannedQuestionSet]:
    def build() -> tuple[ActorContext, TrustedReview, PlannedQuestionSet]:
        if type(actor) is not ActorContext or type(review) is not TrustedReview:
            raise TypeError
        assert isinstance(actor, ActorContext) and isinstance(review, TrustedReview)
        rebuilt = TrustedReview(
            review_id=review.review_id,
            tenant_id=review.tenant_id,
            request=review.request,
            request_sha256=review.request_sha256,
            snapshot=review.snapshot,
            job_id=review.job_id,
        )
        if rebuilt != review:
            raise ValueError
        return actor, rebuilt, revalidated_planned(planned)

    return _arguments(build)


def load_trusted_stages(
    session_factory: sessionmaker[Session],
    actor: ActorContext,
    review: TrustedReview,
    planned: PlannedQuestionSet,
) -> TrustedStages:
    """The trusted reload (M5e-J). Precedence: actor, review and plan types
    (``InvalidStageRequestError``), role (``PermissionDeniedError``), the actor's tenant and the
    plan's tenant and review against the review (``InvalidStageRequestError``); then one
    read-only REPEATABLE READ transaction. A failed check is ``StageRecordInconsistentError``;
    a database or session failure ``StageDatabaseError``; process control propagates as the
    same object, also when cleanup fails afterwards."""
    checked_actor, checked_review, checked_planned = _checked_reload_arguments(
        actor, review, planned
    )
    if checked_actor.role not in RETRIEVAL_ROLES:
        raise PermissionDeniedError()
    if not (
        checked_review.tenant_id == checked_actor.tenant_id
        and checked_planned.tenant_id == checked_review.tenant_id
        and checked_planned.review_id == checked_review.review_id
    ):
        raise InvalidStageRequestError()
    load = _Load()
    try:
        with _recording(session_factory, load) as (session, _now):
            try:
                _load_body(load, session, checked_actor, checked_review, checked_planned)
            except Exception:  # database or session failure inside the body
                load.error = StageDatabaseError
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
        raise StageDatabaseError()
    return load.result
