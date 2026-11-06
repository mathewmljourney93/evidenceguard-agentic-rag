"""The ``run_review`` handler factory, bounded stage orchestration and render-consistent output
reads (M5g, ADR-0025).

Implements M5g-A to M5g-I of the specification accepted in Prompt 217 (``docs/plan.md``). The
handler is **not registered in production** (``production_registry`` is unchanged, W8); only test
registries register it. No setting, endpoint, command or enqueue path builds it, and it has no
default model provider: the caller must pass one.

One attempt, in order (the first failing step decides):

1. **Job and payload** (pure): kind ``run_review``, payload exactly ``{"review_id": <canonical
   lowercase UUID>}``, idempotency key equal to it, ``max_attempts == 3``.
2. **Actor** (G1): ``REVIEW_WORKER_ACTOR_ID`` with role reviewer and the job's tenant. It is
   internal to the handler and claims no human approval; authorization rests on canonical-job
   ownership, which every fenced write re-proves.
3. **Trusted review** through the M5d loader with the pinned M5c artifacts; it must name this job
   and tenant.
4. **Plan** with the M5c planner, then one fenced ``record_planned_questions`` (identical replay
   is a no-op).
5. **Trusted stage reload** (M5e); every resume decision starts from it.
6. **Questions** in planned order, Verification then owner-only Analysis (``shared=()``), with no
   in-handler concurrency. The M5e planner ``plan_stage`` is the only budget algorithm; the loop
   is bounded (5 Verification and 4 Analysis iterations).
7. **Completion**: a second trusted reload, the M5f build, its source-bound recheck and the
   pinned render, then ``write_review_output`` inside ``ctx.fenced(finish=True)``, so the output
   and the job's success commit together or not at all.

Retrieval uses only ``search_snapshot`` over the review's stored snapshot; nothing recaptures,
searches current revisions or loads unpinned artifacts. Reservations commit before dispatch;
``ctx.check()`` runs after each reservation fence exits and before every provider call, and after
each call; no provider call runs inside a database transaction.

**Failures.** Control flow (``JobCancelledError``, ``LeaseLostError``, ``FenceClosedError``) and
process control propagate as the same objects. Outside fenced blocks, a step's ordinary failure is
classified by class only after ``ctx.check()`` (M5g-E). Inside fenced blocks only an escaping
object that **is** the body's own fixed error is classified, after leaving the context and after
``ctx.check()`` (G17); every other ordinary failure leaving the context is replaced by the fixed
``ReviewFenceExitError`` (G22), which the runtime records as ``unexpected_error``. Errors raised
here are fresh, outside every handler, with no cause or context; nothing logs.
"""

import hashlib
import time
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from types import MappingProxyType
from typing import ClassVar, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy.orm import Session, sessionmaker

from evidenceguard_agents.artifact_errors import RequestTooLargeError, ReviewArtifactError
from evidenceguard_agents.assembly import (
    AnalystRequestInputs,
    ModelSettings,
    RepairReason,
    VerifierRequestInputs,
    assemble_analyst_request,
    assemble_repair_request,
    assemble_verifier_request,
)
from evidenceguard_agents.planner import PlannedQuestion, plan_review
from evidenceguard_agents.providers import ModelProvider, call_validated
from evidenceguard_agents.report import (
    build_report_content,
    recheck_report_content,
    render_report_markdown,
)
from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_domain.embedding_storage import require_storable_identity
from evidenceguard_domain.errors import PermissionDeniedError
from evidenceguard_domain.evidence import EvidenceQuestion
from evidenceguard_domain.jobs import JobErrorCode, LeaseLostError
from evidenceguard_domain.model_calls import (
    CallOutcome,
    InvalidModelRequestError,
    InvalidModelValueError,
    ModelClockError,
    PromptRef,
    StructuredRequest,
    StructuredResult,
)
from evidenceguard_domain.provenance import (
    AnalyzedQuestion,
    ProvenanceError,
    ProvenanceRejection,
    QuestionEvidence,
    VerifiedQuestion,
    analyze_question,
    verify_question,
)
from evidenceguard_domain.report_content import ReportContentError
from evidenceguard_domain.retrieval import (
    EmptySnapshotError,
    InvalidRetrievalRequestError,
    InvalidSnapshotError,
    RetrievalDatabaseError,
    RetrievalProviderError,
    RetrievalScopeError,
    SnapshotBoundsError,
    SnapshotInconsistentError,
    SnapshotNotReadyError,
)
from evidenceguard_domain.review_outputs import (
    InvalidStoredOutputError,
    ReviewOutput,
    ReviewOutputValueError,
    StoredReviewOutput,
    revalidated_stored,
)
from evidenceguard_domain.review_stages import (
    CallKind,
    CallRecord,
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
    StageRecord,
    StageShape,
    StageState,
    TrustedQuestionStages,
    TrustedStages,
    UnresolvedReason,
    dependency_sha256,
    plan_stage,
)
from evidenceguard_domain.reviews import (
    REVIEW_JOB_KIND,
    REVIEW_JOB_MAX_ATTEMPTS,
    InvalidReviewRequestError,
    InvalidReviewValueError,
    ReviewArtifactsUnavailableError,
    ReviewDatabaseError,
    ReviewNotFoundError,
    ReviewRecordInconsistentError,
)
from evidenceguard_persistence.jobs import FenceClosedError
from evidenceguard_persistence.review_outputs import (
    InvalidOutputRequestError,
    ReviewOutputBindingError,
    ReviewOutputConflictError,
    ReviewOutputDatabaseError,
    ReviewOutputFenceMismatchError,
    ReviewOutputIncompleteError,
    load_review_output,
    write_review_output,
)
from evidenceguard_persistence.review_stages import (
    EvidenceTooLargeError,
    InvalidStageRequestError,
    StageBindingError,
    StageBudgetExhaustedError,
    StageCallAbandonedError,
    StageCallInFlightError,
    StageConflictError,
    StageDatabaseError,
    StageDependencyError,
    StageFenceMismatchError,
    StageNotPlannedError,
    StagePlanMismatchError,
    StageRecordInconsistentError,
    commit_analyzed,
    commit_unresolved,
    commit_verified,
    complete_failed_call,
    load_trusted_stages,
    read_stage_state,
    record_evidence,
    record_planned_questions,
    reserve_call,
)
from evidenceguard_retrieval.embeddings import EmbeddingProvider
from evidenceguard_worker.context import (
    HandlerFence,
    JobCancelledError,
    JobContext,
    PermanentJobError,
    RetryableJobError,
)
from evidenceguard_worker.indexing import SUPPORTED_PROVIDERS, ProviderFactory
from evidenceguard_worker.registry import JobHandler
from evidenceguard_worker.retrieval import search_snapshot
from evidenceguard_worker.review_seams import ResolvedReview, load_trusted_review

__all__ = [
    "MAX_ITERATIONS",
    "REVIEW_WORKER_ACTOR_ID",
    "ReviewFenceExitError",
    "ReviewRendererDriftError",
    "TrustedReviewOutput",
    "UnsupportedEmbeddingProfileError",
    "load_trusted_review_output",
    "make_run_review_handler",
]

REVIEW_WORKER_ACTOR_ID = uuid5(NAMESPACE_URL, "https://evidenceguard.invalid/actors/run-review/v1")
"""The fixed internal worker actor (G1). It is not a person and claims no approval."""

MAX_ITERATIONS: Mapping[StageKind, int] = MappingProxyType(
    {StageKind.VERIFICATION: 5, StageKind.ANALYSIS: 4}
)
"""The derived per-stage loop bounds (M5g-C4, G18)."""

PAYLOAD_KEY = "review_id"
_HEX = frozenset("0123456789abcdef")


# --- errors (fixed codes and messages) -----------------------------------------------------------


class ReviewWorkerError(Exception):
    """Base of the fixed M5g worker errors."""

    code: ClassVar[str] = "review_worker_error"
    message: ClassVar[str] = "the review operation failed"

    def __init__(self) -> None:
        super().__init__(self.message)


class UnsupportedEmbeddingProfileError(ReviewWorkerError):
    """No supported provider for the review's stored embedding identity (B2). Permanent."""

    code = "unsupported_embedding_profile"
    message = "the review's embedding profile is not supported"


class ReviewRendererDriftError(ReviewWorkerError):
    """A stored output's Markdown digest or size no longer matches the pinned renderer (F3).
    Read paths only; drift is reported, never repaired."""

    code = "review_renderer_drift"
    message = "the stored review output does not match its renderer"


class ReviewFenceExitError(ReviewWorkerError):
    """Internal privacy normalization of an unclassified ordinary failure leaving a fenced block
    (lifecycle, commit, cleanup, replacement or lock timeout at entry). It claims nothing about
    the cause; the runtime records ``unexpected_error`` (G22)."""

    code = "review_fence_exit_failed"
    message = "a fenced review operation did not complete"


class ReviewStepError(ReviewWorkerError):
    """Internal privacy normalization of an unrecognized ordinary failure of a guarded step
    outside fenced blocks (M5g-E precedence rule 5). No semantic classification: the runtime
    records ``unexpected_error``."""

    code = "review_step_failed"
    message = "a review step did not complete"


class ReviewCompositionError(Exception):
    """Private: a reconstruction, binding, settings or bound check failed (permanent)."""

    def __init__(self) -> None:
        super().__init__()


class _InFlightCompositionError(ReviewCompositionError):
    """Private: a stage plan that belongs to an out-of-band or stale state (``PlanInFlight``,
    G6). Retryable: a later attempt plans it as abandoned."""


# --- classification ------------------------------------------------------------------------------

CONTROL_FLOW_ERRORS: tuple[type[Exception], ...] = (
    JobCancelledError,
    LeaseLostError,
    FenceClosedError,
)
_RETRYABLE_STEP_ERRORS: tuple[type[Exception], ...] = (
    RetrievalProviderError,
    RetrievalDatabaseError,
    ReviewDatabaseError,
    StageDatabaseError,
    ReviewOutputDatabaseError,
    ModelClockError,
    _InFlightCompositionError,
)
_PERMANENT_STEP_ERRORS: tuple[type[Exception], ...] = (
    InvalidReviewRequestError,
    InvalidReviewValueError,
    ReviewNotFoundError,
    ReviewRecordInconsistentError,
    ReviewArtifactsUnavailableError,
    PermissionDeniedError,
    InvalidRetrievalRequestError,
    InvalidSnapshotError,
    RetrievalScopeError,
    EmptySnapshotError,
    SnapshotBoundsError,
    SnapshotNotReadyError,
    SnapshotInconsistentError,
    UnsupportedEmbeddingProfileError,
    ReviewCompositionError,
    InvalidModelRequestError,
    InvalidModelValueError,
    ReportContentError,
    ReviewOutputValueError,
    ReviewStageError,
    ReviewArtifactError,
    ProvenanceError,
)
_RETRYABLE_BODY_ERRORS: tuple[type[Exception], ...] = (
    StageDatabaseError,
    StageCallInFlightError,
    ReviewOutputDatabaseError,
)
FIXED_BODY_ERRORS: tuple[type[Exception], ...] = (
    *_RETRYABLE_BODY_ERRORS,
    StageFenceMismatchError,
    StageConflictError,
    StageBindingError,
    StageDependencyError,
    StagePlanMismatchError,
    StageNotPlannedError,
    StageRecordInconsistentError,
    EvidenceTooLargeError,
    StageBudgetExhaustedError,
    StageCallAbandonedError,
    InvalidStageRequestError,
    InvalidOutputRequestError,
    ReviewOutputFenceMismatchError,
    ReviewOutputBindingError,
    ReviewOutputIncompleteError,
    ReviewOutputConflictError,
)
"""The M5e and output-writer fixed classes a fenced body may raise (identity-confirmed only)."""


def _step_error(failed: type[Exception]) -> Exception:
    """A fresh job error for a guarded step's failure class (M5g-H)."""
    if issubclass(failed, _RETRYABLE_STEP_ERRORS):
        return RetryableJobError(JobErrorCode.RETRYABLE_FAILURE)
    if issubclass(failed, _PERMANENT_STEP_ERRORS):
        return PermanentJobError(JobErrorCode.PERMANENT_FAILURE)
    return ReviewStepError()


def _body_error(failed: type[Exception]) -> Exception:
    """A fresh job error for an identity-confirmed fixed body error (M5g-H)."""
    if issubclass(failed, _RETRYABLE_BODY_ERRORS):
        return RetryableJobError(JobErrorCode.RETRYABLE_FAILURE)
    return PermanentJobError(JobErrorCode.PERMANENT_FAILURE)


def _require(condition: bool, *, retryable: bool = False) -> None:
    """A composition check inside a guarded step (classified by the step's boundary)."""
    if not condition:
        raise _InFlightCompositionError() if retryable else ReviewCompositionError()


def _step[T](ctx: JobContext, make: Callable[[], T]) -> T:
    """One guarded pure or remote step (M5g-E): control flow propagates untouched; an ordinary
    failure keeps only its class; ``ctx.check()`` runs after the step whatever happened, so
    latched lease loss, fence closure or cancellation wins over the classification, which is
    raised fresh outside every handler. Process control is never caught."""
    results: list[T] = []
    failed: type[Exception] | None = None
    try:
        results.append(make())
    except CONTROL_FLOW_ERRORS:
        raise
    except Exception as error:  # ordinary only; the object is not retained
        failed = type(error)
    ctx.check()
    if failed is not None:
        raise _step_error(failed)
    return results[0]


def _fenced[T](ctx: JobContext, op: Callable[[HandlerFence], T], *, finish: bool = False) -> T:
    """A fenced write with identity-confirmed classification and privacy normalization
    (M5g-E2, R10, R13; G17, G22)."""
    results: list[T] = []
    body_failure: type[Exception] | None = None  # class of an identity-confirmed body error
    exit_failed = False  # an unclassified ordinary failure left the context
    raised: BaseException | None = None
    try:
        with ctx.fenced(finish=finish) as fence:
            try:
                results.append(op(fence))
            except FIXED_BODY_ERRORS as error:
                raised = error
                raise  # must escape so the fence rolls back and issues no COMMIT
    except CONTROL_FLOW_ERRORS:
        raise  # the same object, untouched
    except Exception as escaped:  # ordinary only; process control is never caught here
        if raised is not None and escaped is raised:
            body_failure = type(raised)
        else:
            exit_failed = True
        raised = None  # drop every reference to the original object
    # No exception is being handled from here on: nothing raised below gains a cause or context.
    if body_failure is not None:
        ctx.check()  # latched cancellation, lease loss or fence closure wins (R10)
        raise _body_error(body_failure)
    if exit_failed:
        raise ReviewFenceExitError()  # privacy normalization only; no ctx.check() (R13)
    return results[0]


# --- the factory ---------------------------------------------------------------------------------


def _has_generate(provider: object) -> bool:
    """The factory's one guarded provider check: ``callable(getattr(provider, "generate"))``.
    An ordinary failure while reading the attribute fails the check; process control raised there
    propagates as the same object. ``provider_id`` is not read here (M5a reads it per call)."""
    usable = False
    try:
        usable = callable(getattr(provider, "generate", None))
    except Exception:  # a raising property: a failed check, nothing retained
        usable = False
    return usable


def _is_fingerprint(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(c in _HEX for c in value)


def _copied_providers(providers: object) -> Mapping[str, ProviderFactory] | None:
    copied: dict[str, ProviderFactory] = {}
    valid = False
    try:
        if isinstance(providers, Mapping):
            for fingerprint, factory in providers.items():
                if not _is_fingerprint(fingerprint) or not callable(factory):
                    raise TypeError
                copied[fingerprint] = factory
            valid = True
    except Exception:  # an ordinary failure while reading the mapping: refused below
        valid = False
    return MappingProxyType(copied) if valid else None


@dataclass(frozen=True)
class _Dependencies:
    provider: ModelProvider
    session_factory: sessionmaker[Session]
    embedding_providers: Mapping[str, ProviderFactory]
    clock: Callable[[], float]


def make_run_review_handler(
    provider: ModelProvider,
    *,
    session_factory: sessionmaker[Session],
    embedding_providers: Mapping[str, Callable[[], EmbeddingProvider]] = SUPPORTED_PROVIDERS,
    clock: Callable[[], float] = time.monotonic,
) -> JobHandler:
    """Build the ``run_review`` handler (M5g-A). Every argument is checked now, before a handler
    exists; a failure is a fresh ``TypeError`` with a fixed message and no cause or context. The
    default embedding providers are the offline M4c mapping. There is no default model provider."""
    if not _has_generate(provider):
        raise TypeError("provider must be a ModelProvider")
    if not isinstance(session_factory, sessionmaker):
        raise TypeError("session_factory must be a sessionmaker")
    providers = _copied_providers(embedding_providers)
    if providers is None:
        raise TypeError("embedding_providers must map fingerprints to provider factories")
    if not callable(clock):
        raise TypeError("clock must be callable")
    dependencies = _Dependencies(provider, session_factory, providers, clock)

    def run_review(ctx: JobContext) -> None:
        """Run one review attempt (see the module docstring)."""
        _Attempt(ctx, dependencies).run()

    return run_review


# --- one attempt ---------------------------------------------------------------------------------


def _checked_review_id(ctx: JobContext) -> UUID:
    """B1: the job and payload checks (pure)."""
    job = ctx.job
    payload = job.payload.as_dict()
    _require(job.kind == REVIEW_JOB_KIND and frozenset(payload) == {PAYLOAD_KEY})
    value = payload[PAYLOAD_KEY]
    review_id = UUID(value)
    _require(str(review_id) == value and job.idempotency_key == value)
    _require(job.max_attempts == REVIEW_JOB_MAX_ATTEMPTS)
    return review_id


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class _Question:
    position: int
    planned: PlannedQuestion
    question_sha256: str

    @property
    def question(self) -> EvidenceQuestion:
        return self.planned.question

    @property
    def question_id(self) -> str:
        return self.planned.question.question_id


@dataclass
class _Progress:
    """The mutable per-stage loop state of one attempt: the latest re-read state, the trusted
    evidence for this question and the trusted owner value (Verification S1 only)."""

    state: StageState
    evidence: QuestionEvidence | None
    owner: VerifiedQuestion | None


class _Attempt:
    """The state of one handler invocation. Never shared across attempts or threads."""

    def __init__(self, ctx: JobContext, dependencies: _Dependencies) -> None:
        self._ctx = ctx
        self._deps = dependencies
        self._embedder: EmbeddingProvider | None = None

    # entry --------------------------------------------------------------------------------------

    def run(self) -> None:
        ctx = self._ctx
        review_id = _step(ctx, lambda: _checked_review_id(ctx))  # B1
        self._review_id = review_id
        self._actor = ActorContext(  # B2 (G1)
            tenant_id=ctx.job.tenant_id, actor_id=REVIEW_WORKER_ACTOR_ID, role=Role.REVIEWER
        )
        ctx.check()  # B3
        resolved = _step(
            ctx, lambda: load_trusted_review(self._deps.session_factory, self._actor, review_id)
        )
        self._resolved = _step(ctx, lambda: self._checked_resolved(resolved))
        review = self._resolved.review
        self._review = review
        configuration = review.request.configuration
        self._settings = _step(
            ctx,
            lambda: ModelSettings(
                model_id=configuration.model_id,
                max_output_tokens=configuration.max_output_tokens,
                timeout_ms=configuration.timeout_ms,
            ),
        )
        planned_questions = _step(  # B4
            ctx, lambda: plan_review(self._resolved.template, k=configuration.retrieval_k)
        )
        planned = _step(
            ctx,
            lambda: PlannedQuestionSet(
                tenant_id=review.tenant_id,
                review_id=review.review_id,
                questions=tuple(item.question for item in planned_questions),
            ),
        )
        self._planned = planned
        _fenced(ctx, lambda fence: record_planned_questions(fence, planned))
        stages = self._reload()  # B5
        questions = tuple(
            _Question(position, item, digest)
            for position, (item, digest) in enumerate(
                zip(planned_questions, planned.question_sha256s, strict=True)
            )
        )
        for item, trusted in zip(questions, stages.questions, strict=True):  # B6, G14
            self._question(item, trusted)
        self._complete()  # B7

    def _checked_resolved(self, resolved: object) -> ResolvedReview:
        _require(type(resolved) is ResolvedReview)
        assert isinstance(resolved, ResolvedReview)
        review = resolved.review
        job = self._ctx.job
        _require(
            review.review_id == self._review_id
            and review.job_id == job.id
            and review.tenant_id == job.tenant_id
        )
        return resolved

    def _reload(self) -> TrustedStages:
        """A trusted stage reload (``ctx.check()`` first); it must cover every planned question
        in order and describe this attempt."""
        ctx = self._ctx
        ctx.check()
        stages = _step(
            ctx,
            lambda: load_trusted_stages(
                self._deps.session_factory, self._actor, self._review, self._planned
            ),
        )

        def checked() -> TrustedStages:
            _require(
                stages.job_id == ctx.job.id
                and tuple(item.question for item in stages.questions) == self._planned.questions
            )
            _require(stages.job_attempt == ctx.job.attempt, retryable=True)
            return stages

        return _step(ctx, checked)

    # one question -------------------------------------------------------------------------------

    def _question(self, item: _Question, trusted: TrustedQuestionStages) -> None:
        verification, owner = self._verification(item, trusted)
        dependency = _step(self._ctx, lambda: self._dependency(item, verification))
        analysis_state = _step(
            self._ctx, lambda: self._entry_state(trusted, StageKind.ANALYSIS, dependency)
        )
        if verification.shape is StageShape.S1:
            assert owner is not None
            self._analysis(item, analysis_state, owner)
            return
        if isinstance(analysis_state.plan, PlanReuse):  # U3 already committed
            return
        # One return iteration (U3): no call; a failed Verification is never altered.
        self._unresolved(item, StageKind.ANALYSIS, UnresolvedReason.VERIFICATION_UNRESOLVED)

    def _dependency(self, item: _Question, owner: StageRecord) -> str:
        return dependency_sha256(
            tenant_id=self._review.tenant_id,
            review_id=self._review.review_id,
            question_id=item.question_id,
            question_sha256=item.question_sha256,
            owner_outcome=owner.outcome,
            owner_content_sha256=owner.content_sha256,
            owner_reason=owner.unresolved_reason,
        )

    def _entry_state(
        self, trusted: TrustedQuestionStages, kind: StageKind, dependency: str | None
    ) -> StageState:
        """The stage's state at entry, rebuilt from the trusted reload (M5g-C4)."""
        if kind is StageKind.VERIFICATION:
            history = trusted.verification_history
            evidence = trusted.evidence
            digest = (
                None
                if evidence is None
                else EvidenceRecord(
                    tenant_id=self._review.tenant_id,
                    review_id=self._review.review_id,
                    question=trusted.question,
                    result=evidence.result,
                ).evidence_sha256
            )
            return StageState(
                history=history,
                plan=plan_stage(history),
                evidence_sha256=digest,
                dependency_sha256=None,
            )
        history = trusted.analysis_history
        return StageState(
            history=history,
            plan=plan_stage(history),
            evidence_sha256=None,
            dependency_sha256=dependency,
        )

    def _verification(
        self, item: _Question, trusted: TrustedQuestionStages
    ) -> tuple[StageRecord, VerifiedQuestion | None]:
        """The Verification loop (M5g-C4). Returns the committed stage and, for S1, the owner
        value: the rechecked reload value or this attempt's ``verify_question`` result (G4)."""
        ctx = self._ctx
        kind = StageKind.VERIFICATION
        state = _step(ctx, lambda: self._entry_state(trusted, kind, None))
        owner: VerifiedQuestion | None = None
        committed = trusted.verification
        if committed is not None and committed.shape is StageShape.S1:
            owner = cast(VerifiedQuestion, committed.content)
        progress = _Progress(state=state, evidence=trusted.evidence, owner=owner)
        for _ in range(MAX_ITERATIONS[kind]):
            done = self._verification_iteration(item, progress)
            if done is not None:
                return done
        return self._exceeded()

    def _verification_iteration(
        self, item: _Question, progress: "_Progress"
    ) -> tuple[StageRecord, VerifiedQuestion | None] | None:
        """One iteration: (a) evidence, (b) dispatch or (c) return (M5g-C4). ``None`` means the
        loop continues with ``progress`` updated by the iteration's re-read."""
        ctx = self._ctx
        kind = StageKind.VERIFICATION
        plan = progress.state.plan
        if isinstance(plan, PlanReuse):  # (c) no write
            reused = plan.stage
            owner = progress.owner if reused.shape is StageShape.S1 else None
            # G4: a committed S1 is reusable only with a trusted owner value (the reload's).
            trusted_owner = reused.shape is not StageShape.S1 or owner is not None
            _step(ctx, lambda: _require(trusted_owner, retryable=True))
            return reused, owner
        if isinstance(plan, PlanExhausted):  # (c) U1 / U2
            return self._unresolved(item, kind, plan.reason), None
        dispatch = self._dispatch_plan(plan)
        if progress.state.evidence_sha256 is None:  # only possible while no call exists
            _step(ctx, lambda: _require(dispatch.call_kind is CallKind.INITIAL))
            record = self._retrieve(item)
            if not record.fits_storage:  # (c) U4
                stage = self._unresolved(
                    item, kind, UnresolvedReason.EVIDENCE_TOO_LARGE, evidence=record
                )
                return stage, None
            progress.state = _fenced(  # (a) evidence and re-read in one transaction
                ctx, lambda fence: self._record_evidence(fence, item, record)
            )
            progress.evidence = _step(ctx, lambda: self._question_evidence(item, record))
            return None
        evidence = _step(ctx, lambda: _present(progress.evidence))
        inputs = _step(ctx, lambda: self._verifier_inputs(evidence))
        history = progress.state.history
        built = _step(ctx, lambda: self._request(kind, item, dispatch, history, inputs))
        if isinstance(built, UnresolvedReason):  # (c) U5 / U6
            return self._unresolved(item, kind, built), None
        result = self._dispatch(item, kind, dispatch, built)  # (b)
        converted: VerifiedQuestion | ProvenanceRejection | None = None
        if result.outcome is CallOutcome.COMPLETED:
            converted = _step(ctx, lambda: verify_question(evidence, result))
        if isinstance(converted, VerifiedQuestion):  # S1, returned in the same iteration
            verified = converted
            stage = _fenced(
                ctx,
                lambda fence: commit_verified(
                    fence,
                    self._review_id,
                    item.question_id,
                    sequence=dispatch.sequence,
                    result=result,
                    verified=verified,
                ),
            )
            return stage, verified
        rejection = converted
        progress.state = _fenced(
            ctx, lambda fence: self._failed_call(fence, item, kind, dispatch, result, rejection)
        )
        return None

    def _analysis(self, item: _Question, state: StageState, owner: VerifiedQuestion) -> StageRecord:
        """The owner-only Analysis loop (M5g-C4, ``shared=()``)."""
        progress = _Progress(state=state, evidence=None, owner=owner)
        for _ in range(MAX_ITERATIONS[StageKind.ANALYSIS]):
            done = self._analysis_iteration(item, progress, owner)
            if done is not None:
                return done
        return self._exceeded()[0]

    def _analysis_iteration(
        self, item: _Question, progress: "_Progress", owner: VerifiedQuestion
    ) -> StageRecord | None:
        ctx = self._ctx
        kind = StageKind.ANALYSIS
        plan = progress.state.plan
        if isinstance(plan, PlanReuse):  # (c) no write
            return plan.stage
        if isinstance(plan, PlanExhausted):  # (c) U1 / U2
            return self._unresolved(item, kind, plan.reason)
        dispatch = self._dispatch_plan(plan)
        inputs = _step(ctx, lambda: self._analyst_inputs(item, owner))
        history = progress.state.history
        built = _step(ctx, lambda: self._request(kind, item, dispatch, history, inputs))
        if isinstance(built, UnresolvedReason):  # (c) U5 / U6
            return self._unresolved(item, kind, built)
        result = self._dispatch(item, kind, dispatch, built)  # (b)
        converted: AnalyzedQuestion | ProvenanceRejection | None = None
        if result.outcome is CallOutcome.COMPLETED:
            converted = _step(
                ctx, lambda: analyze_question(owner, item.question, result, shared=())
            )
        if isinstance(converted, AnalyzedQuestion):  # S2, returned in the same iteration
            analyzed = converted
            return _fenced(
                ctx,
                lambda fence: commit_analyzed(
                    fence,
                    self._review_id,
                    item.question_id,
                    sequence=dispatch.sequence,
                    result=result,
                    analyzed=analyzed,
                    owner=owner,
                ),
            )
        rejection = converted
        progress.state = _fenced(
            ctx, lambda fence: self._failed_call(fence, item, kind, dispatch, result, rejection)
        )
        return None

    def _dispatch_plan(self, plan: object) -> PlanDispatch:
        """``PlanDispatch``, or the defensive ``PlanInFlight`` refusal (retryable, G6): a
        propagated exception ends an attempt, so a current-attempt ``started`` call can come
        only from an out-of-band write; a later attempt plans it as abandoned."""
        _step(self._ctx, lambda: _require(not isinstance(plan, PlanInFlight), retryable=True))
        _step(self._ctx, lambda: _require(isinstance(plan, PlanDispatch)))
        return cast(PlanDispatch, plan)

    def _exceeded(self) -> tuple[StageRecord, None]:
        """The loop bound was exceeded: unreachable for valid histories (G18), permanent."""
        _step(self._ctx, lambda: _require(False))
        raise AssertionError  # pragma: no cover - the step above always raises

    # retrieval (B2) -----------------------------------------------------------------------------

    def _resolved_embedder(self) -> EmbeddingProvider:
        """M5g-B2: at most once per attempt, lazily, before the first retrieval it needs."""
        if self._embedder is not None:
            return self._embedder
        ctx = self._ctx
        ctx.check()
        embedder = _step(ctx, self._resolve_embedder)
        self._embedder = embedder
        return embedder

    def _resolve_embedder(self) -> EmbeddingProvider:
        snapshot_identity = self._review.snapshot.identity
        factory = self._deps.embedding_providers.get(snapshot_identity.fingerprint)
        if factory is None:
            raise UnsupportedEmbeddingProfileError()
        built: list[EmbeddingProvider] = []
        unsupported = False
        try:
            embedder = factory()
            identity = require_storable_identity(embedder.identity)
            if identity == snapshot_identity:
                built.append(embedder)
            else:
                unsupported = True
        except CONTROL_FLOW_ERRORS:
            raise
        except Exception:  # an ordinary factory or identity failure: fixed and private
            unsupported = True
        if unsupported or not built:
            raise UnsupportedEmbeddingProfileError()  # classified by the step after ctx.check()
        return built[0]

    def _retrieve(self, item: _Question) -> EvidenceRecord:
        ctx = self._ctx
        embedder = self._resolved_embedder()
        ctx.check()  # before search_snapshot; the step checks again after it
        result = _step(
            ctx,
            lambda: search_snapshot(
                self._deps.session_factory,
                self._actor,
                self._review.snapshot,
                item.planned.retrieval,
                embedder,
            ),
        )
        return _step(
            ctx,
            lambda: EvidenceRecord(
                tenant_id=self._review.tenant_id,
                review_id=self._review.review_id,
                question=item.question,
                result=result,
            ),
        )

    def _question_evidence(self, item: _Question, record: EvidenceRecord) -> QuestionEvidence:
        return QuestionEvidence(
            tenant_id=self._review.tenant_id,
            review_id=self._review.review_id,
            snapshot_sha256=self._review.snapshot.sha256,
            question=item.question,
            result=record.result,
        )

    # request reconstruction (C3) ----------------------------------------------------------------

    def _verifier_inputs(self, evidence: QuestionEvidence) -> VerifierRequestInputs:
        resolved = self._resolved
        return VerifierRequestInputs(
            evidence=evidence,
            prompt=resolved.verifier,
            system_text=resolved.verifier_system_text,
            settings=self._settings,
        )

    def _analyst_inputs(self, item: _Question, owner: VerifiedQuestion) -> AnalystRequestInputs:
        resolved = self._resolved
        return AnalystRequestInputs(
            owner=owner,
            question=item.question,
            prompt=resolved.analyst,
            system_text=resolved.analyst_system_text,
            settings=self._settings,
        )

    def _request(
        self,
        kind: StageKind,
        item: _Question,
        plan: PlanDispatch,
        history: StageHistory,
        inputs: VerifierRequestInputs | AnalystRequestInputs,
    ) -> StructuredRequest | UnresolvedReason:
        """The request for ``plan`` (M5g-C3), or the U5/U6 reason for an oversize initial or
        repair request. Every other mismatch is a permanent composition error, with no
        dispatch and no fallback to a fresh plan."""
        calls = history.calls
        original = _assembled(lambda: _assemble(inputs))
        if plan.call_kind is CallKind.INITIAL:
            _require(not calls and plan.sequence == 1)
            if original is None:
                return UnresolvedReason.REQUEST_TOO_LARGE  # U5
            request = original
        else:
            _require(bool(calls) and original is not None)  # an earlier identical request fit
            assert original is not None
            first = calls[0].request_sha256
            if plan.call_kind is CallKind.RETRY and plan.request_basis is RequestBasis.ORIGINAL:
                _require(original.request_sha256 == plan.required_request_sha256 == first)
                request = original
            elif plan.call_kind is CallKind.REPAIR:
                _require(original.request_sha256 == plan.original_request_sha256 == first)
                reason = self._repair_reason(kind, item, calls, plan.trigger)
                repaired = _assembled(lambda: assemble_repair_request(original, inputs, reason))
                if repaired is None:
                    return UnresolvedReason.REPAIR_REQUEST_TOO_LARGE  # U6
                _require(repaired.request_sha256 != plan.original_request_sha256)
                request = repaired
            else:
                _require(plan.call_kind is CallKind.RETRY)
                _require(plan.request_basis is RequestBasis.REPAIRED)
                _require(original.request_sha256 == first)
                reason = self._repair_reason(kind, item, calls, plan.trigger)
                repaired = _assembled(lambda: assemble_repair_request(original, inputs, reason))
                _require(repaired is not None)  # the identical repaired request fit before
                assert repaired is not None
                _require(repaired.request_sha256 == plan.required_request_sha256)
                request = repaired
        self._check_settings(kind, item, request)
        return request

    def _repair_reason(
        self,
        kind: StageKind,
        item: _Question,
        calls: tuple[CallRecord, ...],
        trigger: int | None,
    ) -> RepairReason:
        """The reason built from the call numbered ``trigger``: the call that caused the repair,
        never the abandoned or failed repair reservation (M5g-C3)."""
        _require(type(trigger) is int and trigger is not None and 1 <= trigger <= len(calls))
        assert trigger is not None
        call = calls[trigger - 1]
        purpose = kind.purpose
        _require(call.state is ReservationState.COMPLETED)
        _require(call.stage is kind and call.question_id == item.question_id)
        if call.outcome is CallOutcome.INVALID_OUTPUT and call.rejection is None:
            reason = RepairReason.invalid_output(purpose=purpose, question_id=call.question_id)
        else:
            _require(call.outcome is CallOutcome.COMPLETED and call.rejection is not None)
            assert call.rejection is not None
            reason = RepairReason.from_rejection(call.rejection.to_rejection(call.question_id))
        _require(reason.purpose is purpose and reason.question_id == item.question_id)
        return reason

    def _check_settings(self, kind: StageKind, item: _Question, request: StructuredRequest) -> None:
        """Every dispatch kind: the request's settings, prompt and system-text digest equal the
        trusted configuration (``timeout_ms`` explicitly: the M5a digest excludes it)."""
        configuration = self._review.request.configuration
        prompt: PromptRef = (
            configuration.verifier_prompt
            if kind is StageKind.VERIFICATION
            else configuration.analyst_prompt
        )
        _require(
            request.purpose is kind.purpose
            and request.question_id == item.question_id
            and request.model_id == configuration.model_id
            and request.max_output_tokens == configuration.max_output_tokens
            and request.timeout_ms == configuration.timeout_ms
            and request.prompt == prompt
            and _sha256_text(request.system_text) == prompt.sha256
        )

    # dispatch (C2) ------------------------------------------------------------------------------

    def _dispatch(
        self, item: _Question, kind: StageKind, plan: PlanDispatch, request: StructuredRequest
    ) -> StructuredResult:
        """Reserve, then (after the reservation fence exited) ``ctx.check()``, then exactly one
        ``call_validated`` with no transaction open, then ``ctx.check()`` (in the step)."""
        ctx = self._ctx
        _fenced(
            ctx,
            lambda fence: reserve_call(
                fence,
                self._review_id,
                item.question_id,
                kind,
                sequence=plan.sequence,
                call_kind=plan.call_kind,
                request_basis=plan.request_basis,
                request=request,
            ),
        )
        ctx.check()  # R1: the last boundary before the provider
        provider, clock = self._deps.provider, self._deps.clock
        return _step(ctx, lambda: call_validated(provider, request, clock=clock))

    # fenced operations --------------------------------------------------------------------------

    def _record_evidence(
        self, fence: HandlerFence, item: _Question, record: EvidenceRecord
    ) -> StageState:
        record_evidence(fence, record)
        return read_stage_state(fence, self._review_id, item.question_id, StageKind.VERIFICATION)

    def _failed_call(
        self,
        fence: HandlerFence,
        item: _Question,
        kind: StageKind,
        plan: PlanDispatch,
        result: StructuredResult,
        rejection: ProvenanceRejection | None,
    ) -> StageState:
        complete_failed_call(
            fence,
            self._review_id,
            item.question_id,
            kind,
            sequence=plan.sequence,
            result=result,
            rejection=rejection,
        )
        return read_stage_state(fence, self._review_id, item.question_id, kind)

    def _unresolved(
        self,
        item: _Question,
        kind: StageKind,
        reason: UnresolvedReason,
        *,
        evidence: EvidenceRecord | None = None,
    ) -> StageRecord:
        return _fenced(
            self._ctx,
            lambda fence: commit_unresolved(
                fence, self._review_id, item.question_id, kind, reason=reason, evidence=evidence
            ),
        )

    # completion (G) -----------------------------------------------------------------------------

    def _complete(self) -> None:
        """Report and output (M5g-G): reload, build, source-bound recheck, render, then the
        output write and the job's success in one finish transaction."""
        ctx = self._ctx
        stages = self._reload()
        resolved, review, planned = self._resolved, self._review, self._planned
        content = _step(
            ctx, lambda: build_report_content(review, resolved.template, planned, stages)
        )
        _step(
            ctx,
            lambda: recheck_report_content(
                content, review=review, template=resolved.template, planned=planned, stages=stages
            ),
        )
        markdown = _step(ctx, lambda: render_report_markdown(content))
        output = _step(
            ctx,
            lambda: ReviewOutput(
                tenant_id=review.tenant_id,
                review_id=review.review_id,
                job_id=review.job_id,
                content=content,
                markdown_sha256=_sha256_text(markdown),
                markdown_bytes=len(markdown.encode("utf-8")),
            ),
        )
        ctx.check()
        _fenced(ctx, lambda fence: write_review_output(fence, output), finish=True)


def _present[T](value: T | None) -> T:
    _require(value is not None)
    assert value is not None
    return value


def _assemble(inputs: VerifierRequestInputs | AnalystRequestInputs) -> StructuredRequest:
    if type(inputs) is VerifierRequestInputs:
        return assemble_verifier_request(inputs)
    _require(type(inputs) is AnalystRequestInputs)
    return assemble_analyst_request(cast(AnalystRequestInputs, inputs))


def _assembled(make: Callable[[], StructuredRequest]) -> StructuredRequest | None:
    """``None`` for an oversize request (``RequestTooLargeError``); every other failure
    propagates to the enclosing step's boundary (classified by class)."""
    built: list[StructuredRequest] = []
    too_large = False
    try:
        built.append(make())
    except RequestTooLargeError:
        too_large = True
    if too_large:
        return None
    return built[0]


# --- render-consistent output reads (F3) ---------------------------------------------------------


@dataclass(frozen=True, init=False, repr=False)
class TrustedReviewOutput:
    """A stored output with Markdown re-rendered by the pinned renderer and equal in SHA-256 and
    UTF-8 size to the stored metadata. ``repr`` shows the review ID, wrapper digest and size."""

    stored: StoredReviewOutput
    markdown: str

    def __init__(self, *, stored: StoredReviewOutput, markdown: str, **unknown: object) -> None:
        def build() -> StoredReviewOutput:
            if unknown or type(markdown) is not str:
                raise TypeError
            checked = revalidated_stored(stored)
            output = checked.output
            encoded = markdown.encode("utf-8")
            if (
                hashlib.sha256(encoded).hexdigest() != output.markdown_sha256
                or len(encoded) != output.markdown_bytes
            ):
                raise ValueError
            return checked

        built: list[StoredReviewOutput] = []
        with suppress(Exception):
            built.append(build())
        if not built:
            raise InvalidStoredOutputError()
        object.__setattr__(self, "stored", built[0])
        object.__setattr__(self, "markdown", markdown)

    def __repr__(self) -> str:
        output = self.stored.output
        return (
            f"TrustedReviewOutput(review_id={output.review_id}, "
            f"wrapper_sha256={output.wrapper_sha256!r}, markdown_bytes={output.markdown_bytes})"
        )

    __str__ = __repr__


def load_trusted_review_output(
    session_factory: sessionmaker[Session], actor: ActorContext, review_id: UUID
) -> TrustedReviewOutput:
    """``load_review_output`` (its argument, role, missing-review, non-canonical-job and
    lifecycle/presence rules first, errors unchanged), then the pinned render and a SHA-256 and
    UTF-8 length comparison with the stored metadata. A render failure or any mismatch is a fresh
    ``ReviewRendererDriftError``: drift is reported, never repaired; nothing is written and no
    Markdown is returned (G21)."""
    stored = load_review_output(session_factory, actor, review_id)
    rendered: list[TrustedReviewOutput] = []
    with suppress(Exception):
        rendered.append(
            TrustedReviewOutput(
                stored=stored, markdown=render_report_markdown(stored.output.content)
            )
        )
    if not rendered:
        raise ReviewRendererDriftError()
    return rendered[0]
