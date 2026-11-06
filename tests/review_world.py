"""A synthetic, in-memory world for the M5g handler tests (no database, no network).

It is **not** a test module (no ``test_`` prefix); M5g test modules import it. It provides:

- a trusted review built from the **pinned** M5c template and prompts with synthetic tenant,
  vendor, snapshot and evidence values (the M5e value-test fixtures);
- ``FakeDatabase``: a transactional fake of the M5e and M5g persistence calls the handler makes.
  Every stored value is built by the real domain constructors (``CallRecord``, ``StageRecord``,
  ``StageHistory``, ``StageState``, ``TrustedStages``), so an illegal write sequence fails loudly.
  Its sessions run inside the **real** ``evidenceguard_persistence.db.transaction`` helper, so
  commit, rollback and close (and the G15 selection rule) are the production code paths; each can
  be scripted to fail through named fault points;
- a fence opener and a ``JobStore`` for the real ``JobContext`` and ``run_worker``;
- model-output builders for the scripted fake provider.

Faults are deterministic: an action registered for the n-th hit of a named event raises a given
exception or calls a function (for example to latch cancellation). Nothing sleeps.
"""

import dataclasses
import json
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

import pytest

from evidenceguard_agents.prompts import PromptSpec, load_prompt
from evidenceguard_agents.scripted import (
    FAKE_MODEL_ID,
    Respond,
    ScriptedFakeProvider,
    Step,
)
from evidenceguard_agents.templates import ReviewTemplate, TemplateRef, load_template
from evidenceguard_domain import jobs as lifecycle
from evidenceguard_domain.context import ActorContext
from evidenceguard_domain.evidence import EvidenceQuestion
from evidenceguard_domain.jobs import (
    JobErrorCode,
    JobLeaseToken,
    JobPayload,
    JobSnapshot,
    JobStatus,
    LeaseLostError,
)
from evidenceguard_domain.model_calls import CallOutcome, StructuredRequest, StructuredResult
from evidenceguard_domain.provenance import (
    AnalyzedQuestion,
    ProvenanceRejection,
    QuestionEvidence,
    VerifiedQuestion,
)
from evidenceguard_domain.retrieval import (
    RETRIEVAL_CONFIG_V1,
    ChunkEvidence,
    RetrievalRequest,
    RetrievalResult,
    RetrievalSnapshot,
)
from evidenceguard_domain.review_outputs import (
    ReviewOutput,
    ReviewOutputWrite,
    StoredReviewOutput,
)
from evidenceguard_domain.review_stages import (
    CallKind,
    CallRecord,
    CallRejection,
    EvidenceRecord,
    PlanDispatch,
    PlannedQuestionSet,
    RequestBasis,
    ReservationState,
    StageHistory,
    StageKind,
    StageOutcome,
    StageRecord,
    StageState,
    TrustedQuestionStages,
    TrustedStages,
    UnresolvedReason,
    dependency_sha256,
    plan_stage,
)
from evidenceguard_domain.reviews import ReviewConfiguration, ReviewRequest, TrustedReview
from evidenceguard_domain.reviews import request_sha256 as review_request_sha256
from evidenceguard_persistence.db import transaction
from evidenceguard_persistence.review_outputs import (
    ReviewOutputConflictError,
    ReviewOutputIncompleteError,
)
from evidenceguard_persistence.review_stages import (
    EvidenceTooLargeError,
    StageBindingError,
    StageCallAbandonedError,
    StageCallInFlightError,
    StageConflictError,
    StagePlanMismatchError,
)
from evidenceguard_retrieval.embeddings import HASH_IDENTITY
from evidenceguard_worker import review as review_module
from evidenceguard_worker.context import AttemptState, JobContext
from evidenceguard_worker.registry import JobHandler
from evidenceguard_worker.review_seams import ResolvedReview

if TYPE_CHECKING:
    import test_review_stage_values as old
else:
    from tests import test_review_stage_values as old

TENANT = old.TENANT
VENDOR = old.VENDOR
REVIEW = old.REVIEW
JOB = old.JOB
CHUNK = old.C1
WORKER = "worker-review-test"
T0 = datetime(2026, 11, 6, 9, 0, tzinfo=UTC)
CLAIM_AT = T0 + timedelta(days=1)
TEXT = old.TEXT  # "Customer data is encrypted at rest with AES-256."
QUOTE = "encrypted at rest"


# --- artifacts and the trusted review --------------------------------------------------------


def pinned() -> tuple[ReviewTemplate, tuple[PromptSpec, str], tuple[PromptSpec, str]]:
    return (
        load_template("vendor_security_review", 1),
        load_prompt("verifier", 1),
        load_prompt("risk_analyst", 1),
    )


def configuration(template: ReviewTemplate | None = None, **changes: Any) -> ReviewConfiguration:
    pinned_template, verifier, analyst = pinned()
    ref = (template or pinned_template).ref
    values: dict[str, Any] = {
        "template_id": ref.template_id,
        "template_version": ref.version,
        "template_sha256": ref.sha256,
        "verifier_prompt": verifier[0].ref,
        "analyst_prompt": analyst[0].ref,
        "model_id": FAKE_MODEL_ID,
    }
    values.update(changes)
    return ReviewConfiguration(**values)


def snapshot() -> RetrievalSnapshot:
    return old.snapshot()


def trusted_review(config: ReviewConfiguration | None = None) -> TrustedReview:
    request = ReviewRequest(
        vendor_id=VENDOR,
        idempotency_key="m5g-review",
        identity=HASH_IDENTITY,
        config=RETRIEVAL_CONFIG_V1,
        configuration=config or configuration(),
    )
    return TrustedReview(
        review_id=REVIEW,
        tenant_id=TENANT,
        request=request,
        request_sha256=review_request_sha256(request, tenant_id=TENANT),
        snapshot=snapshot(),
        job_id=JOB,
    )


def resolved(template: ReviewTemplate | None = None) -> ResolvedReview:
    pinned_template, verifier, analyst = pinned()
    chosen = template or pinned_template
    return ResolvedReview(
        review=trusted_review(configuration(chosen)),
        template=chosen,
        verifier=verifier[0],
        verifier_system_text=verifier[1],
        analyst=analyst[0],
        analyst_system_text=analyst[1],
    )


def synthetic_template(count: int) -> ReviewTemplate:
    """A template that is **not** registered (for limits beyond the pinned eight questions)."""
    questions = tuple(
        EvidenceQuestion(
            question_id=f"SYN-{n:02}",
            text=f"Synthetic question {n}?",
            search_queries=("synthetic query one", "synthetic query two"),
        )
        for n in range(1, count + 1)
    )
    return ReviewTemplate(
        ref=TemplateRef(template_id="synthetic_review", version=1, sha256="5" * 64),
        title="Synthetic review",
        questions=questions,
    )


def chunk(text: str = TEXT, *, title: str = "Security Overview") -> ChunkEvidence:
    return old.chunk(text=text, title=title)


def result(evidence: ChunkEvidence | None = None) -> RetrievalResult:
    return old.result(evidence)


# --- model outputs -----------------------------------------------------------------------------


def verifier_json(
    *, quote: str = QUOTE, rationale: str = "Based on the cited passages.", claim: str = "Stated."
) -> str:
    return json.dumps(
        {
            "verdict": "supported",
            "claims": [{"text": claim, "citations": [{"chunk_id": str(CHUNK), "quote": quote}]}],
            "rationale": rationale,
        }
    )


def analyst_json(
    question_id: str,
    *,
    count: int = 1,
    quote: str = QUOTE,
    statement: str = "The vendor states it.",
    title: str = "Vendor statement only",
) -> str:
    return json.dumps(
        {
            "findings": [
                {
                    "question_ids": [question_id],
                    "title": f"{title} {n}",
                    "severity": "low",
                    "statement": statement,
                    "citations": [{"chunk_id": str(CHUNK), "quote": quote}],
                    "follow_up_questions": ["Which evidence supports it?"],
                }
                for n in range(count)
            ]
        }
    )


def scripts(
    questions: tuple[EvidenceQuestion, ...],
    overrides: Mapping[tuple[str, str], tuple[Step, ...]] | None = None,
) -> dict[tuple[str, str], tuple[Step, ...]]:
    """One successful Verifier and Analyst step per question, with per-key overrides."""
    values: dict[tuple[str, str], tuple[Step, ...]] = {}
    for question in questions:
        values[("verifier", question.question_id)] = (Respond(verifier_json()),)
        values[("risk_analyst", question.question_id)] = (
            Respond(analyst_json(question.question_id)),
        )
    values.update(overrides or {})
    return values


class HookedProvider:
    """Wraps a provider: ``before``/``after`` run around each ``generate`` (synchronous)."""

    def __init__(self, inner: Any, *, before: Callable[[StructuredRequest], None] | None = None):
        self.inner = inner
        self.before = before
        self.requests: list[StructuredRequest] = []

    @property
    def provider_id(self) -> str:
        return cast(str, self.inner.provider_id)

    def generate(self, request: StructuredRequest) -> Any:
        self.requests.append(request)
        if self.before is not None:
            self.before(request)
        return self.inner.generate(request)


# --- the fake database ---------------------------------------------------------------------------


def make_job(*, status: JobStatus = JobStatus.QUEUED, attempt: int = 0) -> JobSnapshot:
    return JobSnapshot(
        id=JOB,
        tenant_id=TENANT,
        kind="run_review",
        idempotency_key=str(REVIEW),
        payload=JobPayload.from_mapping({"review_id": str(REVIEW)}),
        status=status,
        attempt=attempt,
        max_attempts=3,
        run_after=T0,
        locked_by=WORKER if status is JobStatus.RUNNING else None,
        lease_expires_at=T0 + timedelta(seconds=60) if status is JobStatus.RUNNING else None,
        created_at=T0,
        updated_at=T0,
    )


Key = tuple[str, StageKind]


@dataclass
class State:
    job: JobSnapshot
    planned: tuple[tuple[int, str, str], ...] | None = None
    evidence: dict[str, EvidenceRecord] = field(default_factory=dict)
    calls: dict[Key, tuple[CallRecord, ...]] = field(default_factory=dict)
    stages: dict[Key, StageRecord] = field(default_factory=dict)
    output: StoredReviewOutput | None = None

    def copy(self) -> "State":
        return dataclasses.replace(
            self,
            evidence=dict(self.evidence),
            calls=dict(self.calls),
            stages=dict(self.stages),
        )


Action = BaseException | Callable[[], None]


class FakeSession:
    """One transaction's working copy. ``commit`` publishes it; ``rollback`` drops it."""

    def __init__(self, db: "FakeDatabase") -> None:
        self.db = db
        self.state = db.state.copy()
        self.ops: list[str] = []
        db.hit("session")
        db.sessions.append(self)
        self.calls: list[str] = []

    def commit(self) -> None:
        self.calls.append("commit")
        self.db.hit("commit")
        self.db.state = self.state
        self.db.commits += 1
        self.db.hit("commit.after")
        for op in self.ops:
            self.db.hit(f"committed.{op}")

    def rollback(self) -> None:
        self.calls.append("rollback")
        self.db.rollbacks += 1
        self.db.hit("rollback")

    def close(self) -> None:
        self.calls.append("close")
        self.db.hit("close")


class FakeFence:
    def __init__(self, session: FakeSession, job: JobSnapshot) -> None:
        self.session = session
        self.job = job

    def succeed(self) -> JobSnapshot:
        db = self.session.db
        db.hit("succeed")
        state = self.session.state
        db.require_owner(state, self.job.lease_token())
        state.job = lifecycle.succeed(state.job, self.job.lease_token(), now=T0)
        return state.job


class FakeDatabase:
    """The fake rows (``state``) plus scripted faults and call counters."""

    def __init__(self, world: "World") -> None:
        self.world = world
        self.state = State(job=make_job())
        self.counts: dict[str, int] = {}
        self.faults: dict[tuple[str, int], list[Action]] = {}
        self.sessions: list[FakeSession] = []
        self.commits = 0
        self.rollbacks = 0
        self.ops: list[str] = []
        self.searches: list[RetrievalRequest] = []
        self.reloads = 0
        self.reclaimed = False

    # faults -------------------------------------------------------------------------------------

    def on(self, event: str, action: Action, *, nth: int = 1) -> None:
        self.faults.setdefault((event, nth), []).append(action)

    def next(self, event: str, action: Action) -> None:
        """Register ``action`` for the next hit of ``event``."""
        self.on(event, action, nth=self.counts.get(event, 0) + 1)

    def hit(self, event: str) -> None:
        self.counts[event] = self.counts.get(event, 0) + 1
        for action in self.faults.pop((event, self.counts[event]), []):
            if isinstance(action, BaseException):
                raise action
            action()

    # ownership ----------------------------------------------------------------------------------

    def require_owner(self, state: State, token: JobLeaseToken) -> None:
        job = state.job
        if (
            self.reclaimed
            or job.status is not JobStatus.RUNNING
            or job.attempt != token.attempt
            or job.locked_by != token.worker_id
        ):
            raise LeaseLostError()

    def session_factory(self) -> FakeSession:
        return FakeSession(self)

    @contextmanager
    def open_fence(self, token: JobLeaseToken) -> Iterator[FakeFence]:
        self.hit("fence.enter")
        with transaction(cast(Any, self.session_factory)) as session:
            fake = cast(FakeSession, session)
            self.require_owner(fake.state, token)
            self.hit("fence.locked")
            yield FakeFence(fake, fake.state.job)

    # views --------------------------------------------------------------------------------------

    def calls(self, question_id: str, stage: StageKind) -> tuple[CallRecord, ...]:
        return self.state.calls.get((question_id, stage), ())

    def stage(self, question_id: str, stage: StageKind) -> StageRecord | None:
        return self.state.stages.get((question_id, stage))


def _session(fence: Any) -> FakeSession:
    session = fence.session
    assert type(session) is FakeSession
    return session


class FakeStore:
    """The fake persistence API the handler calls (patched into ``evidenceguard_worker.review``)."""

    def __init__(self, db: FakeDatabase) -> None:
        self.db = db

    def _enter(self, fence: Any, name: str) -> State:
        session = _session(fence)
        session.ops.append(name)
        self.db.ops.append(name)
        self.db.require_owner(session.state, fence.job.lease_token())
        self.db.hit(f"op.{name}")
        return session.state

    def _questions(self, state: State) -> dict[str, tuple[int, str]]:
        assert state.planned is not None
        return {qid: (position, digest) for position, qid, digest in state.planned}

    def _history(self, state: State, question_id: str, kind: StageKind) -> StageHistory:
        return StageHistory(
            tenant_id=TENANT,
            review_id=REVIEW,
            job_id=JOB,
            question_id=question_id,
            stage=kind,
            current_attempt=state.job.attempt,
            calls=state.calls.get((question_id, kind), ()),
            committed=state.stages.get((question_id, kind)),
        )

    def _evidence_digest(self, state: State, question_id: str) -> str | None:
        record = state.evidence.get(question_id)
        return None if record is None else record.evidence_sha256

    def _dependency(self, state: State, question_id: str) -> str | None:
        owner = state.stages.get((question_id, StageKind.VERIFICATION))
        if owner is None:
            return None
        return dependency_sha256(
            tenant_id=TENANT,
            review_id=REVIEW,
            question_id=question_id,
            question_sha256=self._questions(state)[question_id][1],
            owner_outcome=owner.outcome,
            owner_content_sha256=owner.content_sha256,
            owner_reason=owner.unresolved_reason,
        )

    def _stage_state(self, state: State, question_id: str, kind: StageKind) -> StageState:
        history = self._history(state, question_id, kind)
        verification = kind is StageKind.VERIFICATION
        return StageState(
            history=history,
            plan=plan_stage(history),
            evidence_sha256=self._evidence_digest(state, question_id) if verification else None,
            dependency_sha256=None if verification else self._dependency(state, question_id),
        )

    # the patched API ------------------------------------------------------------------------------

    def record_planned_questions(self, fence: Any, planned: PlannedQuestionSet) -> Any:
        state = self._enter(fence, "record_planned_questions")
        rows = tuple(
            (position, question.question_id, digest)
            for position, (question, digest) in enumerate(
                zip(planned.questions, planned.question_sha256s, strict=True)
            )
        )
        if state.planned is None:
            state.planned = rows
        elif state.planned != rows:
            raise StageConflictError()
        return planned

    def read_stage_state(
        self, fence: Any, review_id: UUID, question_id: str, stage: StageKind
    ) -> StageState:
        state = self._enter(fence, "read_stage_state")
        assert review_id == REVIEW
        return self._stage_state(state, question_id, stage)

    def record_evidence(self, fence: Any, record: EvidenceRecord) -> EvidenceRecord:
        state = self._enter(fence, "record_evidence")
        stored = state.evidence.get(record.question_id)
        if stored is not None:
            if stored.canonical != record.canonical:
                raise StageConflictError()
            return record
        if not record.fits_storage:
            raise EvidenceTooLargeError()
        state.evidence[record.question_id] = record
        return record

    def reserve_call(
        self,
        fence: Any,
        review_id: UUID,
        question_id: str,
        stage: StageKind,
        *,
        sequence: int,
        call_kind: CallKind,
        request_basis: RequestBasis,
        request: StructuredRequest,
    ) -> CallRecord:
        state = self._enter(fence, "reserve_call")
        history = self._history(state, question_id, stage)
        plan = plan_stage(history)
        if not isinstance(plan, PlanDispatch):
            raise StageCallInFlightError()
        if (plan.sequence, plan.call_kind, plan.request_basis) != (
            sequence,
            call_kind,
            request_basis,
        ):
            raise StagePlanMismatchError()
        if plan.required_request_sha256 not in (None, request.request_sha256):
            raise StagePlanMismatchError()
        if plan.original_request_sha256 == request.request_sha256:
            raise StagePlanMismatchError()
        config = self.db.world.resolved.review.request.configuration
        prompt = (
            config.verifier_prompt if stage is StageKind.VERIFICATION else config.analyst_prompt
        )
        if (
            request.model_id != config.model_id
            or request.timeout_ms != config.timeout_ms
            or request.max_output_tokens != config.max_output_tokens
            or request.prompt != prompt
        ):
            raise StageBindingError()
        verification = stage is StageKind.VERIFICATION
        call = CallRecord(
            tenant_id=TENANT,
            review_id=REVIEW,
            job_id=JOB,
            question_id=question_id,
            stage=stage,
            sequence=sequence,
            call_kind=call_kind,
            request_basis=request_basis,
            request_sha256=request.request_sha256,
            prompt_sha256=request.prompt.sha256,
            model_requested=request.model_id,
            max_output_tokens=request.max_output_tokens,
            timeout_ms=request.timeout_ms,
            evidence_sha256=self._evidence_digest(state, question_id) if verification else None,
            dependency_sha256=None if verification else self._dependency(state, question_id),
            job_attempt=state.job.attempt,
            state=ReservationState.STARTED,
            started_at=T0,
        )
        state.calls[(question_id, stage)] = (*history.calls, call)
        self._history(state, question_id, stage)  # V1-V12 must still hold
        return call

    def _completed(
        self,
        state: State,
        question_id: str,
        stage: StageKind,
        sequence: int,
        result: StructuredResult,
        rejection: ProvenanceRejection | None,
    ) -> CallRecord:
        calls = state.calls.get((question_id, stage), ())
        if not 1 <= sequence <= len(calls):
            raise StagePlanMismatchError()
        call = calls[sequence - 1]
        if result.request_sha256 != call.request_sha256 or result.question_id != question_id:
            raise StageBindingError()
        if call.state is not ReservationState.STARTED:
            raise StageConflictError()
        if call.job_attempt != state.job.attempt:
            raise StageCallAbandonedError()
        done = dataclasses.replace(
            call,
            state=ReservationState.COMPLETED,
            completed_at=T0 + timedelta(seconds=1),
            outcome=result.outcome,
            dispatched=result.dispatched,
            model_used=result.model_used,
            usage=result.usage,
            latency_ms=result.latency_ms,
            rejection=None if rejection is None else CallRejection.from_rejection(rejection),
        )
        state.calls[(question_id, stage)] = (*calls[: sequence - 1], done, *calls[sequence:])
        return done

    def complete_failed_call(
        self,
        fence: Any,
        review_id: UUID,
        question_id: str,
        stage: StageKind,
        *,
        sequence: int,
        result: StructuredResult,
        rejection: ProvenanceRejection | None,
    ) -> CallRecord:
        state = self._enter(fence, "complete_failed_call")
        assert (result.outcome is CallOutcome.COMPLETED) == (rejection is not None)
        done = self._completed(state, question_id, stage, sequence, result, rejection)
        self._history(state, question_id, stage)
        return done

    def _commit_success(
        self,
        state: State,
        question_id: str,
        stage: StageKind,
        sequence: int,
        result: StructuredResult,
        content: VerifiedQuestion | AnalyzedQuestion,
    ) -> StageRecord:
        call = self._completed(state, question_id, stage, sequence, result, None)
        record = StageRecord(
            tenant_id=TENANT,
            review_id=REVIEW,
            job_id=JOB,
            question_id=question_id,
            stage=stage,
            outcome=StageOutcome.VERIFIED
            if stage is StageKind.VERIFICATION
            else StageOutcome.ANALYZED,
            unresolved_reason=None,
            call_sequence=sequence,
            request_sha256=call.request_sha256,
            evidence_sha256=call.evidence_sha256,
            dependency_sha256=call.dependency_sha256,
            content=content,
            job_attempt=state.job.attempt,
            committed_at=T0,
        )
        state.stages[(question_id, stage)] = record
        self._history(state, question_id, stage)
        return record

    def commit_verified(
        self,
        fence: Any,
        review_id: UUID,
        question_id: str,
        *,
        sequence: int,
        result: StructuredResult,
        verified: VerifiedQuestion,
    ) -> StageRecord:
        state = self._enter(fence, "commit_verified")
        return self._commit_success(
            state, question_id, StageKind.VERIFICATION, sequence, result, verified
        )

    def commit_analyzed(
        self,
        fence: Any,
        review_id: UUID,
        question_id: str,
        *,
        sequence: int,
        result: StructuredResult,
        analyzed: AnalyzedQuestion,
        owner: VerifiedQuestion,
    ) -> StageRecord:
        state = self._enter(fence, "commit_analyzed")
        verified = state.stages[(question_id, StageKind.VERIFICATION)]
        assert verified.content == owner
        return self._commit_success(
            state, question_id, StageKind.ANALYSIS, sequence, result, analyzed
        )

    def commit_unresolved(
        self,
        fence: Any,
        review_id: UUID,
        question_id: str,
        stage: StageKind,
        *,
        reason: UnresolvedReason,
        evidence: EvidenceRecord | None = None,
    ) -> StageRecord:
        state = self._enter(fence, "commit_unresolved")
        existing = state.stages.get((question_id, stage))
        if existing is not None:
            if existing.unresolved_reason is not reason:
                raise StageConflictError()
            return existing
        calls = state.calls.get((question_id, stage), ())
        refs: dict[str, Any] = {
            "call_sequence": None,
            "request_sha256": None,
            "evidence_sha256": None,
            "dependency_sha256": None,
        }
        if calls:
            last = calls[-1]
            refs.update(
                call_sequence=last.sequence,
                request_sha256=last.request_sha256,
                evidence_sha256=last.evidence_sha256,
                dependency_sha256=last.dependency_sha256,
            )
        elif reason is UnresolvedReason.EVIDENCE_TOO_LARGE:
            assert evidence is not None and not evidence.fits_storage
        elif stage is StageKind.VERIFICATION:
            refs["evidence_sha256"] = self._evidence_digest(state, question_id)
        else:
            refs["dependency_sha256"] = self._dependency(state, question_id)
        record = StageRecord(
            tenant_id=TENANT,
            review_id=REVIEW,
            job_id=JOB,
            question_id=question_id,
            stage=stage,
            outcome=StageOutcome.UNRESOLVED,
            unresolved_reason=reason,
            content=None,
            job_attempt=state.job.attempt,
            committed_at=T0,
            **refs,
        )
        state.stages[(question_id, stage)] = record
        self._history(state, question_id, stage)
        return record

    def write_review_output(self, fence: Any, output: ReviewOutput) -> ReviewOutputWrite:
        state = self._enter(fence, "write_review_output")
        assert state.planned is not None
        for _, question_id, _ in state.planned:
            for kind in StageKind:
                if (question_id, kind) not in state.stages:
                    raise ReviewOutputIncompleteError()
        if state.output is not None:
            if state.output.output != output:
                raise ReviewOutputConflictError()
            return ReviewOutputWrite(stored=state.output, replayed=True)
        stored = StoredReviewOutput(output=output, job_attempt=state.job.attempt, created_at=T0)
        state.output = stored
        return ReviewOutputWrite(stored=stored, replayed=False)

    # the trusted loaders (own transactions in production) -----------------------------------------

    def load_trusted_review(
        self, session_factory: Any, actor: ActorContext, review_id: UUID
    ) -> Any:
        self.db.hit("load_review")
        self.db.world.actors.append(actor)
        assert review_id == REVIEW
        return self.db.world.resolved

    def load_trusted_stages(
        self,
        session_factory: Any,
        actor: ActorContext,
        review: TrustedReview,
        planned: PlannedQuestionSet,
    ) -> TrustedStages:
        self.db.hit("reload")
        self.db.reloads += 1
        self.db.world.actors.append(actor)
        state = self.db.state
        questions = []
        if state.planned is not None:
            for question in planned.questions:
                qid = question.question_id
                record = state.evidence.get(qid)
                evidence = (
                    None
                    if record is None
                    else QuestionEvidence(
                        tenant_id=TENANT,
                        review_id=REVIEW,
                        snapshot_sha256=review.snapshot.sha256,
                        question=question,
                        result=record.result,
                    )
                )
                questions.append(
                    TrustedQuestionStages(
                        question=question,
                        evidence=evidence,
                        verification=state.stages.get((qid, StageKind.VERIFICATION)),
                        analysis=state.stages.get((qid, StageKind.ANALYSIS)),
                        verification_history=self._history(state, qid, StageKind.VERIFICATION),
                        analysis_history=self._history(state, qid, StageKind.ANALYSIS),
                    )
                )
        return TrustedStages(
            tenant_id=TENANT,
            review_id=REVIEW,
            job_id=JOB,
            job_attempt=state.job.attempt,
            questions=tuple(questions),
        )

    def search_snapshot(
        self,
        session_factory: Any,
        actor: ActorContext,
        snapshot: RetrievalSnapshot,
        request: RetrievalRequest,
        provider: Any,
    ) -> RetrievalResult:
        self.db.hit("search")
        self.db.searches.append(request)
        self.db.world.actors.append(actor)
        assert snapshot == self.db.world.resolved.review.snapshot
        for question in self.db.world.resolved.template.questions:
            if question.search_queries == request.queries:
                found = self.db.world.results.get(question.question_id)
                return found if found is not None else result()
        raise AssertionError("unknown retrieval request")


PATCHED = (
    "record_planned_questions",
    "read_stage_state",
    "record_evidence",
    "reserve_call",
    "complete_failed_call",
    "commit_verified",
    "commit_analyzed",
    "commit_unresolved",
    "write_review_output",
    "load_trusted_review",
    "load_trusted_stages",
    "search_snapshot",
)


# --- the world --------------------------------------------------------------------------------


@dataclass
class Attempt:
    ctx: JobContext
    state: AttemptState
    error: BaseException | None


class World:
    """The synthetic review, the fake database and helpers to run handler attempts."""

    def __init__(
        self, monkeypatch: pytest.MonkeyPatch, *, template: ReviewTemplate | None = None
    ) -> None:
        self.resolved = resolved(template)
        self.questions = self.resolved.template.questions
        self.results: dict[str, RetrievalResult] = {}
        self.actors: list[ActorContext] = []
        self.current: AttemptState | None = None
        self.db = FakeDatabase(self)
        self.store = FakeStore(self.db)
        for name in PATCHED:
            monkeypatch.setattr(review_module, name, getattr(self.store, name))

    def provider(
        self, overrides: Mapping[tuple[str, str], tuple[Step, ...]] | None = None
    ) -> ScriptedFakeProvider:
        return ScriptedFakeProvider(scripts=scripts(self.questions, overrides))

    def handler(self, provider: Any, **kwargs: Any) -> JobHandler:
        return review_module.make_run_review_handler(
            provider, session_factory=cast(Any, _SESSIONMAKER), **kwargs
        )

    def claim(self) -> JobSnapshot:
        """Claim (or reclaim) the job: the next attempt, running."""
        # Each claim is a day after the last: earlier leases have expired and backoffs passed.
        job = self.db.state.job
        now = CLAIM_AT + timedelta(days=job.attempt)  # later than every earlier lease
        claimed = lifecycle.claim(job, worker_id=WORKER, now=now)
        self.db.state.job = claimed
        return claimed

    def attempt(self, handler: JobHandler) -> Attempt:
        """One handler invocation on the real ``JobContext`` (no runtime outcome recording)."""
        job = self.claim()
        state = AttemptState(deadline=float("inf"), lease_seconds=60.0, clock=lambda: 0.0)
        ctx = JobContext(job, state, cast(Any, self.db.open_fence))
        self.current = state
        error: BaseException | None = None
        try:
            handler(ctx)
        except BaseException as caught:  # handed to the test
            error = caught
        return Attempt(ctx=ctx, state=state, error=error)

    def cancel(self) -> None:
        """Latch cancellation on the running attempt (as the supervisor would)."""
        assert self.current is not None
        self.current.request_cancel()

    def lose(self) -> None:
        """Latch lease loss on the running attempt (as the supervisor would)."""
        assert self.current is not None
        self.current.latch_lease_loss()

    def stages(self) -> dict[Key, StageRecord]:
        return dict(self.db.state.stages)


def _sessionmaker() -> Any:
    from sqlalchemy.orm import sessionmaker

    return sessionmaker()


_SESSIONMAKER = _sessionmaker()


class FakeJobStore:
    """A runtime ``JobStore`` over the fake database. Outcome writes run in the real
    ``transaction()`` with the fake session, so their commit and cleanup can be scripted."""

    def __init__(self, world: World) -> None:
        self.world = world
        self.db = world.db
        self.claimed = 0

    def claim(self, worker_id: str, kinds: Any) -> JobSnapshot | None:
        assert worker_id == WORKER and "run_review" in kinds
        if self.db.state.job.status is not JobStatus.QUEUED:
            return None
        self.claimed += 1
        return self.world.claim()

    def heartbeat(self, token: JobLeaseToken) -> JobSnapshot:
        self.db.require_owner(self.db.state, token)
        return self.db.state.job

    def _outcome(
        self, name: str, token: JobLeaseToken, rule: Callable[[JobSnapshot], JobSnapshot]
    ) -> JobSnapshot:
        self.db.hit(f"outcome.{name}")
        with transaction(cast(Any, self.db.session_factory)) as session:
            fake = cast(FakeSession, session)
            fake.ops.append(f"outcome.{name}")
            self.db.require_owner(fake.state, token)
            fake.state.job = rule(fake.state.job)
            return fake.state.job

    def complete(self, token: JobLeaseToken) -> JobSnapshot:
        return self._outcome("complete", token, lambda job: lifecycle.succeed(job, token, now=T0))

    def fail_retryable(self, token: JobLeaseToken, code: JobErrorCode) -> JobSnapshot:
        return self._outcome(
            "fail_retryable",
            token,
            lambda job: lifecycle.fail_retryably(job, token, now=T0, code=code),
        )

    def fail_permanent(self, token: JobLeaseToken, code: JobErrorCode) -> JobSnapshot:
        return self._outcome(
            "fail_permanent",
            token,
            lambda job: lifecycle.fail_permanently(job, token, now=T0, code=code),
        )

    def fenced(self, token: JobLeaseToken) -> Any:
        return self.db.open_fence(token)
