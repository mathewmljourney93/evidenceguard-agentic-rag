"""PostgreSQL integration tests for M5e stage and call-reservation persistence (ADR-0023).

They use the guarded disposable-database fixtures from ``conftest.py`` and are skipped without
``EG_TEST_DATABASE_URL`` (required in CI). Revisions are ingested and indexed through the real
worker and M4c paths (offline hash profile); the review is created through M5d; the
``run_review`` job is claimed through the M3 ``claim`` so every write runs in a real M3 fence.
Model results are scripted values (no provider, no network); Verifier and Analyst content comes
from the real M5b conversions. Lease loss is simulated by moving ``lease_expires_at`` into the
past through SQL, except in the one test that must observe a lease expiring during a real lock
wait (the accepted M3 precedent: a two-second lease and bounded polling). Interleavings use
``threading.Event`` handshakes and bounded waits; listeners are removed in ``finally`` blocks.
Tampered rows are written directly only to prove that the reload refuses them.
"""

import contextlib
import hashlib
import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from fractions import Fraction
from typing import Any
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import (
    Engine,
    Interval,
    create_engine,
    delete,
    event,
    func,
    insert,
    literal_column,
    select,
    text,
    update,
)
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from evidenceguard_domain.agent_outputs import (
    AnalystOutput,
    ClaimOutput,
    FindingOutput,
    QuoteRef,
    VerifierOutput,
)
from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_domain.evidence import EvidenceQuestion, Severity, SourceType, Verdict
from evidenceguard_domain.jobs import JobPayload, JobSnapshot, LeaseLostError
from evidenceguard_domain.model_calls import (
    CallOutcome,
    ModelPurpose,
    ModelUsage,
    PromptRef,
    StructuredRequest,
    StructuredResult,
)
from evidenceguard_domain.provenance import (
    AnalyzedQuestion,
    ProvenanceRejection,
    QuestionEvidence,
    RejectionReason,
    RejectionStage,
    VerifiedQuestion,
    analyze_question,
    verify_question,
)
from evidenceguard_domain.retrieval import (
    ChannelHit,
    RetrievalRequest,
    RetrievalResult,
    RetrievedChunk,
)
from evidenceguard_domain.review_stages import (
    CallKind,
    EvidenceRecord,
    PlanDispatch,
    PlannedQuestionSet,
    RequestBasis,
    StageKind,
    StageShape,
    UnresolvedReason,
)
from evidenceguard_domain.reviews import ReviewConfiguration, ReviewRequest, TrustedReview
from evidenceguard_domain.revisions import RevisionContent
from evidenceguard_persistence import documents as revision_store
from evidenceguard_persistence import indexing, reviews
from evidenceguard_persistence import jobs as job_store
from evidenceguard_persistence import review_stages as stages
from evidenceguard_persistence.db import create_session_factory, transaction
from evidenceguard_persistence.models import (
    EmbeddingIndex,
    Job,
    ReviewPlanQuestion,
    ReviewQuestionEvidence,
    ReviewStageCall,
    ReviewStageResult,
    Tenant,
    Vendor,
)
from evidenceguard_persistence.retrieval import capture_snapshot
from evidenceguard_persistence.review_stages import (
    EvidenceTooLargeError,
    InvalidStageRequestError,
    StageBindingError,
    StageBudgetExhaustedError,
    StageCallAbandonedError,
    StageCallInFlightError,
    StageConflictError,
    StageDependencyError,
    StageNotPlannedError,
    StagePlanMismatchError,
    StageRecordInconsistentError,
)
from evidenceguard_retrieval.embeddings import HASH_IDENTITY, HashingEmbedder
from evidenceguard_worker.handlers import production_registry
from evidenceguard_worker.ingest import INGEST_REVISION_KIND, ingest_revision
from evidenceguard_worker.registry import HandlerRegistry
from evidenceguard_worker.retrieval import search_snapshot
from evidenceguard_worker.runtime import DatabaseJobStore, Timings, WorkerResult, run_worker

pytestmark = pytest.mark.integration

WAIT_SECONDS = 10
MARKDOWN = "text/markdown"
TIMINGS = Timings(
    idle_poll=0.05,
    backoff_initial=0.05,
    backoff_cap=0.2,
    heartbeat_interval=0.2,
    drain=5.0,
    cancel_grace=5.0,
    lease_loss_grace=5.0,
    heartbeat_join=5.0,
    stop_check=0.01,
)
INGEST_ONLY = HandlerRegistry([(INGEST_REVISION_KIND, ingest_revision)])
VERIFIER_SYSTEM = "Test verifier system text (synthetic)."
ANALYST_SYSTEM = "Test analyst system text (synthetic)."


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


VERIFIER_PROMPT = PromptRef(prompt_id="verifier", version=1, sha256=_sha(VERIFIER_SYSTEM))
ANALYST_PROMPT = PromptRef(prompt_id="risk_analyst", version=1, sha256=_sha(ANALYST_SYSTEM))
CONFIGURATION = ReviewConfiguration(
    template_id="vendor_security_review",
    template_version=1,
    template_sha256="26fcbe26dcc47f5991da5b741475c736cec27b1f2bd6ab515ec07ac59895786a",
    verifier_prompt=VERIFIER_PROMPT,
    analyst_prompt=ANALYST_PROMPT,
    model_id="fake-scripted-v1",
)
BODY = "Customer data is encrypted at rest with AES-256.\n"
QUOTE = "encrypted at rest"
Q1 = EvidenceQuestion(
    question_id="ENC-01",
    text="Is customer data encrypted at rest?",
    search_queries=("encrypted at rest",),
)
Q2 = EvidenceQuestion(
    question_id="RET-01",
    text="How long is customer data retained?",
    search_queries=("data retention",),
)
STAGE_TABLES = {
    "review_plan_questions",
    "review_question_evidence",
    "review_stage_calls",
    "review_stage_results",
}
V = StageKind.VERIFICATION
A = StageKind.ANALYSIS


# --- engines and corpus (as in test_reviews_postgres.py) ------------------------------------------


def _engine(url: URL, **options: Any) -> Engine:
    options.setdefault("poolclass", NullPool)
    return create_engine(
        url,
        hide_parameters=True,
        connect_args={"options": "-c statement_timeout=20000"},
        **options,
    )


@pytest.fixture
def engine(migrated: Engine, test_database_url: URL) -> Iterator[Engine]:
    bounded = _engine(test_database_url)
    try:
        yield bounded
    finally:
        bounded.dispose()


@pytest.fixture
def factory(engine: Engine) -> sessionmaker[Session]:
    return create_session_factory(engine)


def _tenant(engine: Engine, slug: str) -> ActorContext:
    tenant_id = uuid4()
    with engine.begin() as connection:
        connection.execute(insert(Tenant).values(id=tenant_id, slug=slug, name=slug.title()))
    return ActorContext(tenant_id=tenant_id, actor_id=uuid4(), role=Role.REVIEWER)


def _vendor(engine: Engine, tenant_id: UUID, slug: str) -> UUID:
    vendor_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            insert(Vendor).values(id=vendor_id, tenant_id=tenant_id, slug=slug, name=slug)
        )
    return vendor_id


def _work(factory: sessionmaker[Session], registry: HandlerRegistry) -> WorkerResult:
    return run_worker(
        DatabaseJobStore(factory), registry, worker_id="w-test", timings=TIMINGS, once=True
    )


def _job_row(engine: Engine, job_id: UUID) -> Any:
    with engine.connect() as connection:
        return connection.execute(select(Job.__table__).where(Job.id == job_id)).one()


def _complete(
    factory: sessionmaker[Session], engine: Engine, registry: HandlerRegistry, job_id: UUID
) -> None:
    """Run the worker until the **target** job has succeeded (bounded by the queued jobs)."""
    with engine.connect() as connection:
        others = connection.execute(
            select(Job.id).where(
                Job.status == "queued", Job.kind.in_(sorted(registry.kinds)), Job.id != job_id
            )
        ).all()
    for _ in range(len(others) + 1):
        assert _work(factory, registry).exit_code == 0
        job = _job_row(engine, job_id)
        if job.status == "succeeded":
            return
        assert job.status == "queued" and job.attempt == 0
    pytest.fail(f"target job {job_id} did not complete within {len(others) + 1} worker runs")


def _ready(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, vendor: UUID, key: str
) -> UUID:
    """An active revision with a ready hash-profile index, through the real paths."""
    with transaction(factory) as session:
        created = revision_store.create_revision(
            session,
            actor,
            vendor_id=vendor,
            document_key=key,
            title=key.title(),
            source_type=SourceType.VENDOR_STATEMENT,
            content=RevisionContent.from_bytes(BODY.encode(), MARKDOWN),
        )
        ingest = job_store.enqueue(
            session,
            actor,
            kind=INGEST_REVISION_KIND,
            idempotency_key=str(created.revision.id),
            payload=JobPayload.from_mapping({"revision_id": str(created.revision.id)}),
        )
    _complete(factory, engine, INGEST_ONLY, ingest.id)
    with transaction(factory) as session:
        result = indexing.enqueue_index_revision(
            session, actor, revision_id=created.revision.id, identity=HASH_IDENTITY
        )
    if result.outcome is not indexing.EnqueueOutcome.READY:
        assert result.job is not None
        _complete(factory, engine, production_registry(), result.job.id)
    with engine.connect() as connection:
        status = connection.execute(
            select(EmbeddingIndex.status).where(EmbeddingIndex.id == result.index.id)
        ).scalar_one()
    assert status == "ready"
    return created.revision.id


def _interval(seconds: float) -> Any:
    return literal_column(f"interval '{seconds} seconds'", type_=Interval)


def _set_job(engine: Engine, job_id: UUID, **values: Any) -> None:
    with engine.begin() as connection:
        connection.execute(update(Job).where(Job.id == job_id).values(**values))


def _wait_until(condition: Callable[[], bool], timeout: float = WAIT_SECONDS) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            pytest.fail("timed out waiting for the expected database state")
        time.sleep(0.05)


def _someone_waits_for_a_lock(engine: Engine) -> bool:
    with engine.connect() as connection:
        waiting = connection.execute(
            text(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE datname = current_database() AND wait_event_type = 'Lock'"
            )
        ).scalar_one()
    return bool(waiting)


def _rows(engine: Engine) -> dict[str, list[dict[str, Any]]]:
    """Every M5e row, ordered, for byte-identity assertions."""
    with engine.connect() as connection:
        return {
            name: [dict(row._mapping) for row in connection.execute(statement)]
            for name, statement in (
                (
                    "plans",
                    select(ReviewPlanQuestion.__table__).order_by(
                        ReviewPlanQuestion.review_id, ReviewPlanQuestion.position
                    ),
                ),
                (
                    "evidence",
                    select(ReviewQuestionEvidence.__table__).order_by(
                        ReviewQuestionEvidence.review_id, ReviewQuestionEvidence.question_id
                    ),
                ),
                (
                    "calls",
                    select(ReviewStageCall.__table__).order_by(
                        ReviewStageCall.review_id,
                        ReviewStageCall.question_id,
                        ReviewStageCall.stage,
                        ReviewStageCall.sequence,
                    ),
                ),
                (
                    "stages",
                    select(ReviewStageResult.__table__).order_by(
                        ReviewStageResult.review_id,
                        ReviewStageResult.question_id,
                        ReviewStageResult.stage,
                    ),
                ),
            )
        }


def _tamper(engine: Engine, *statements: Any) -> None:
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(statement)


# --- the review world -----------------------------------------------------------------------------


@dataclass
class World:
    factory: sessionmaker[Session]
    engine: Engine
    actor: ActorContext
    review: TrustedReview
    planned: PlannedQuestionSet
    token: Any
    results: dict[str, RetrievalResult]

    @property
    def review_id(self) -> UUID:
        return self.review.review_id

    def fenced[T](self, operation: Callable[[Any], T]) -> T:
        with job_store.fenced_transaction(self.factory, self.token) as fence:
            return operation(fence)

    def reclaim(self) -> JobSnapshot:
        """Expire the lease through SQL and claim the canonical job again (next attempt)."""
        _set_job(
            self.engine,
            self.review.job_id,
            lease_expires_at=func.clock_timestamp() - _interval(1),
        )
        claimed = job_store.claim(self.factory, "w-reclaim", kinds=["run_review"])
        assert claimed is not None and claimed.id == self.review.job_id
        self.token = claimed.lease_token()
        return claimed

    def result(self, question: EvidenceQuestion, k: int = 8) -> RetrievalResult:
        key = f"{question.question_id}:{k}"
        if key not in self.results:
            self.results[key] = search_snapshot(
                self.factory,
                self.actor,
                self.review.snapshot,
                RetrievalRequest(question.search_queries, k),
                HashingEmbedder(),
            )
        return self.results[key]

    def evidence(self, question: EvidenceQuestion) -> EvidenceRecord:
        return EvidenceRecord(
            tenant_id=self.actor.tenant_id,
            review_id=self.review_id,
            question=question,
            result=self.result(question),
        )

    def plan(self) -> None:
        self.fenced(lambda f: stages.record_planned_questions(f, self.planned))

    def record(self, question: EvidenceQuestion) -> None:
        self.fenced(lambda f: stages.record_evidence(f, self.evidence(question)))

    def request(
        self, stage: StageKind, question: EvidenceQuestion, user: str = "user", **changes: Any
    ) -> StructuredRequest:
        verification = stage is V
        values: dict[str, Any] = {
            "purpose": ModelPurpose.VERIFIER if verification else ModelPurpose.RISK_ANALYST,
            "prompt": VERIFIER_PROMPT if verification else ANALYST_PROMPT,
            "model_id": CONFIGURATION.model_id,
            "question_id": question.question_id,
            "system_text": VERIFIER_SYSTEM if verification else ANALYST_SYSTEM,
            "user_text": user,
            "max_output_tokens": CONFIGURATION.max_output_tokens,
            "timeout_ms": CONFIGURATION.timeout_ms,
        }
        values.update(changes)
        return StructuredRequest(**values)

    def reserve(
        self,
        stage: StageKind,
        question: EvidenceQuestion,
        sequence: int = 1,
        kind: CallKind = CallKind.INITIAL,
        basis: RequestBasis = RequestBasis.ORIGINAL,
        request: StructuredRequest | None = None,
    ) -> Any:
        chosen = request or self.request(stage, question)
        return self.fenced(
            lambda f: stages.reserve_call(
                f,
                self.review_id,
                question.question_id,
                stage,
                sequence=sequence,
                call_kind=kind,
                request_basis=basis,
                request=chosen,
            )
        )

    def question_evidence(self, question: EvidenceQuestion) -> QuestionEvidence:
        return QuestionEvidence(
            tenant_id=self.actor.tenant_id,
            review_id=self.review_id,
            snapshot_sha256=self.review.snapshot.sha256,
            question=question,
            result=self.result(question),
        )

    def chunk(self, question: EvidenceQuestion) -> UUID:
        return self.result(question).items[0].chunk_id

    def verifier_result(
        self,
        question: EvidenceQuestion,
        request: StructuredRequest,
        rationale: str = "The cited passage states it.",
        **changes: Any,
    ) -> StructuredResult:
        if question is Q1:
            output = VerifierOutput(
                verdict=Verdict.SUPPORTED,
                claims=(
                    ClaimOutput(
                        text="Encrypted at rest.",
                        citations=(QuoteRef(chunk_id=str(self.chunk(question)), quote=QUOTE),),
                    ),
                ),
                rationale=rationale,
            )
        else:
            output = VerifierOutput(
                verdict=Verdict.INSUFFICIENT_EVIDENCE, claims=(), rationale="Nothing found."
            )
        return completed(request, output, **changes)

    def analyst_result(
        self, question: EvidenceQuestion, request: StructuredRequest
    ) -> StructuredResult:
        finding = FindingOutput(
            question_ids=(question.question_id,),
            title="Encryption at rest",
            severity=Severity.LOW,
            statement="Data is encrypted at rest.",
            citations=(QuoteRef(chunk_id=str(self.chunk(question)), quote=QUOTE),),
            follow_up_questions=("Which keys are used?",),
        )
        return completed(request, AnalystOutput(findings=(finding,)))

    def verified(self, question: EvidenceQuestion, result: StructuredResult) -> VerifiedQuestion:
        value = verify_question(self.question_evidence(question), result)
        assert type(value) is VerifiedQuestion
        return value

    def analyzed(
        self, owner: VerifiedQuestion, question: EvidenceQuestion, result: StructuredResult
    ) -> AnalyzedQuestion:
        value = analyze_question(owner, question, result)
        assert type(value) is AnalyzedQuestion
        return value


def completed(request: StructuredRequest, output: Any, **changes: Any) -> StructuredResult:
    values: dict[str, Any] = {
        "request_sha256": request.request_sha256,
        "purpose": request.purpose,
        "question_id": request.question_id,
        "outcome": CallOutcome.COMPLETED,
        "dispatched": True,
        "output": output,
        "model_requested": request.model_id,
        "model_used": request.model_id,
        "usage": ModelUsage(100, 50),
        "latency_ms": 25,
    }
    values.update(changes)
    return StructuredResult(**values)


def failed(request: StructuredRequest, outcome: CallOutcome, **changes: Any) -> StructuredResult:
    response = outcome not in (CallOutcome.TIMEOUT, CallOutcome.PROVIDER_FAILED)
    values: dict[str, Any] = {
        "request_sha256": request.request_sha256,
        "purpose": request.purpose,
        "question_id": request.question_id,
        "outcome": outcome,
        "dispatched": True,
        "output": None,
        "model_requested": request.model_id,
        "model_used": request.model_id if response else None,
        "usage": ModelUsage(1, 1) if response else None,
        "latency_ms": 10,
    }
    values.update(changes)
    return StructuredResult(**values)


def complete_failed(
    world: World,
    stage: StageKind,
    question: EvidenceQuestion,
    result: StructuredResult,
    sequence: int = 1,
    rejection: ProvenanceRejection | None = None,
) -> Any:
    return world.fenced(
        lambda f: stages.complete_failed_call(
            f,
            world.review_id,
            question.question_id,
            stage,
            sequence=sequence,
            result=result,
            rejection=rejection,
        )
    )


def unresolved(
    world: World,
    stage: StageKind,
    question: EvidenceQuestion,
    reason: UnresolvedReason,
    evidence: EvidenceRecord | None = None,
) -> Any:
    return world.fenced(
        lambda f: stages.commit_unresolved(
            f, world.review_id, question.question_id, stage, reason=reason, evidence=evidence
        )
    )


def reload(world: World) -> Any:
    return stages.load_trusted_stages(world.factory, world.actor, world.review, world.planned)


def _create_review(
    factory: sessionmaker[Session], actor: ActorContext, vendor: UUID, key: str
) -> TrustedReview:
    created = reviews.create_review(
        factory,
        actor,
        ReviewRequest(
            vendor_id=vendor,
            idempotency_key=key,
            identity=HASH_IDENTITY,
            configuration=CONFIGURATION,
        ),
    )
    return reviews.load_review(factory, actor, created.review_id)


@pytest.fixture
def world(factory: sessionmaker[Session], engine: Engine) -> World:
    actor = _tenant(engine, "tenant-a")
    vendor = _vendor(engine, actor.tenant_id, "lumenvale")
    _ready(factory, engine, actor, vendor, "security")
    review = _create_review(factory, actor, vendor, "review-m5e.a")
    claimed = job_store.claim(factory, "w-1", kinds=["run_review"])
    assert claimed is not None and claimed.id == review.job_id and claimed.attempt == 1
    planned = PlannedQuestionSet(
        tenant_id=actor.tenant_id, review_id=review.review_id, questions=(Q1, Q2)
    )
    return World(factory, engine, actor, review, planned, claimed.lease_token(), {})


# --- the complete path and the trusted reload -----------------------------------------------------


def test_a_complete_question_commits_and_reloads_as_trusted(world: World) -> None:
    world.plan()
    world.record(Q1)
    request = world.request(V, Q1)
    world.reserve(V, Q1, request=request)
    result = world.verifier_result(Q1, request)
    owner = world.verified(Q1, result)
    world.fenced(
        lambda f: stages.commit_verified(
            f, world.review_id, "ENC-01", sequence=1, result=result, verified=owner
        )
    )
    analyst_request = world.request(A, Q1)
    world.reserve(A, Q1, request=analyst_request)
    analyst = world.analyst_result(Q1, analyst_request)
    content = world.analyzed(owner, Q1, analyst)
    stored = world.fenced(
        lambda f: stages.commit_analyzed(
            f,
            world.review_id,
            Q1.question_id,
            sequence=1,
            result=analyst,
            analyzed=content,
            owner=owner,
        )
    )
    assert stored.shape is StageShape.S2 and stored.content == content
    trusted = reload(world)
    assert (trusted.job_attempt, len(trusted.questions)) == (1, 2)
    first, second = trusted.questions
    assert first.verification is not None and first.verification.shape is StageShape.S1
    assert first.verification.content == owner
    assert first.analysis is not None and first.analysis.content == content
    assert first.evidence is not None and first.evidence.result == world.result(Q1)
    assert second.verification is None and second.evidence is None
    assert second.verification_history.calls == ()
    rows = _rows(world.engine)
    assert [len(rows[name]) for name in ("plans", "evidence", "calls", "stages")] == [2, 1, 2, 2]
    assert all(row["completed_at"] is not None for row in rows["calls"])


def test_a_review_whose_job_was_never_claimed_reloads_empty(
    factory: sessionmaker[Session], engine: Engine
) -> None:
    actor = _tenant(engine, "tenant-c")
    vendor = _vendor(engine, actor.tenant_id, "never")
    _ready(factory, engine, actor, vendor, "security")
    review = _create_review(factory, actor, vendor, "review-m5e.unclaimed")
    planned = PlannedQuestionSet(
        tenant_id=actor.tenant_id, review_id=review.review_id, questions=(Q1,)
    )
    trusted = stages.load_trusted_stages(factory, actor, review, planned)
    assert (trusted.job_attempt, trusted.questions) == (0, ())


def test_planned_questions_replay_identically_and_conflict_otherwise(world: World) -> None:
    world.plan()
    before = _rows(world.engine)
    world.plan()
    assert _rows(world.engine) == before
    other = PlannedQuestionSet(
        tenant_id=world.actor.tenant_id, review_id=world.review_id, questions=(Q2, Q1)
    )
    with pytest.raises(StageConflictError):
        world.fenced(lambda f: stages.record_planned_questions(f, other))
    assert _rows(world.engine) == before


# --- stale fences ---------------------------------------------------------------------------------


def _expire_inside(fence: Any) -> None:
    """Move the held job row's lease into the past inside the fence's own transaction (it is
    rolled back with the fence)."""
    fence.session.execute(
        update(Job)
        .where(Job.id == fence.job.id)
        .values(lease_expires_at=func.clock_timestamp() - _interval(1))
    )


def _ready_for(world: World, operation: str) -> Callable[[Any], Any]:
    """Prepare the state an operation needs and return it as a fenced call."""
    if operation != "plan":
        world.plan()
    if operation not in ("plan", "evidence"):
        world.record(Q1)
    request = world.request(V, Q1)
    if operation in ("failed", "verified", "analyzed"):
        world.reserve(V, Q1, request=request)
    if operation == "plan":
        return lambda f: stages.record_planned_questions(f, world.planned)
    if operation == "evidence":
        return lambda f: stages.record_evidence(f, world.evidence(Q1))
    if operation == "reserve":
        return lambda f: stages.reserve_call(
            f,
            world.review_id,
            "ENC-01",
            V,
            sequence=1,
            call_kind=CallKind.INITIAL,
            request_basis=RequestBasis.ORIGINAL,
            request=request,
        )
    if operation == "failed":
        return lambda f: stages.complete_failed_call(
            f,
            world.review_id,
            "ENC-01",
            V,
            sequence=1,
            result=failed(request, CallOutcome.TIMEOUT),
            rejection=None,
        )
    result = world.verifier_result(Q1, request)
    owner = world.verified(Q1, result)
    if operation == "verified":
        return lambda f: stages.commit_verified(
            f, world.review_id, "ENC-01", sequence=1, result=result, verified=owner
        )
    if operation == "analyzed":
        world.fenced(
            lambda f: stages.commit_verified(
                f, world.review_id, "ENC-01", sequence=1, result=result, verified=owner
            )
        )
        analyst_request = world.request(A, Q1)
        world.reserve(A, Q1, request=analyst_request)
        analyst = world.analyst_result(Q1, analyst_request)
        content = world.analyzed(owner, Q1, analyst)
        return lambda f: stages.commit_analyzed(
            f,
            world.review_id,
            "ENC-01",
            sequence=1,
            result=analyst,
            analyzed=content,
            owner=owner,
        )
    return lambda f: stages.commit_unresolved(
        f, world.review_id, "ENC-01", V, reason=UnresolvedReason.REQUEST_TOO_LARGE
    )


@pytest.mark.parametrize(
    "operation", ["plan", "evidence", "reserve", "failed", "verified", "analyzed", "unresolved"]
)
def test_a_stale_fence_changes_nothing_for_every_write_class(world: World, operation: str) -> None:
    call = _ready_for(world, operation)
    before = _rows(world.engine)
    job_before = _job_row(world.engine, world.review.job_id)

    def stale(fence: Any) -> Any:
        _expire_inside(fence)
        return call(fence)

    with pytest.raises(LeaseLostError):
        world.fenced(stale)
    assert _rows(world.engine) == before
    assert _job_row(world.engine, world.review.job_id) == job_before
    world.fenced(call)  # the same operation succeeds under the valid lease


def test_a_reclaimed_attempts_old_token_cannot_open_a_fence(world: World) -> None:
    world.plan()
    old = world.token
    world.reclaim()
    with (
        pytest.raises(LeaseLostError),
        job_store.fenced_transaction(world.factory, old) as fence,
    ):
        stages.record_evidence(fence, world.evidence(Q1))


def test_a_lease_expiring_during_a_lock_wait_fails_the_final_recheck(world: World) -> None:
    world.plan()
    world.record(Q1)
    before = _rows(world.engine)
    lease_seconds = 2
    holder = world.engine.connect()
    try:
        holder.begin()
        # A conflicting lock on the referenced plan row: the call insert's foreign-key check
        # (FOR KEY SHARE) waits behind it while the lease clock runs.
        holder.execute(
            select(ReviewPlanQuestion.question_id)
            .where(
                ReviewPlanQuestion.review_id == world.review_id,
                ReviewPlanQuestion.question_id == Q1.question_id,
            )
            .with_for_update()
        )
        _set_job(
            world.engine,
            world.review.job_id,
            lease_expires_at=func.clock_timestamp() + _interval(lease_seconds),
        )

        def attempt() -> BaseException | None:
            try:
                world.reserve(V, Q1)
            except BaseException as error:  # the outcome is asserted below
                return error
            return None

        with ThreadPoolExecutor(max_workers=1) as pool:
            waiter = pool.submit(attempt)
            _wait_until(lambda: _someone_waits_for_a_lock(world.engine))

            def lease_has_expired() -> bool:
                with world.engine.connect() as connection:
                    expired: bool = connection.execute(
                        select(Job.lease_expires_at <= func.clock_timestamp()).where(
                            Job.id == world.review.job_id
                        )
                    ).scalar_one()
                return expired

            _wait_until(lease_has_expired, timeout=lease_seconds + 3)
            holder.rollback()  # releases the lock without changing the row
            outcome = waiter.result(timeout=WAIT_SECONDS)
    finally:
        holder.close()
    assert isinstance(outcome, LeaseLostError)
    assert _rows(world.engine) == before


# --- reservations ---------------------------------------------------------------------------------


def test_allocation_identity_and_retry_digests(world: World) -> None:
    world.plan()
    world.record(Q1)
    request = world.request(V, Q1)
    world.reserve(V, Q1, request=request)
    with pytest.raises(StageCallInFlightError):  # not replayable: the plan moved on
        world.reserve(V, Q1, request=request)
    complete_failed(world, V, Q1, failed(request, CallOutcome.TIMEOUT))
    other = world.request(V, Q1, user="different user text")
    for kind, basis, chosen in (
        (CallKind.REPAIR, RequestBasis.REPAIRED, request),
        (CallKind.RETRY, RequestBasis.REPAIRED, request),
        (CallKind.RETRY, RequestBasis.ORIGINAL, other),  # a retry must repeat the digest
    ):
        with pytest.raises(StagePlanMismatchError):
            world.reserve(V, Q1, 2, kind, basis, chosen)
    with pytest.raises(StagePlanMismatchError):
        world.reserve(V, Q1, 3, CallKind.RETRY, RequestBasis.ORIGINAL, request)
    record = world.reserve(V, Q1, 2, CallKind.RETRY, RequestBasis.ORIGINAL, request)
    assert (record.sequence, record.request_sha256) == (2, request.request_sha256)


def test_the_budget_and_the_single_repair_survive_job_attempts(world: World) -> None:
    world.plan()
    world.record(Q1)
    request = world.request(V, Q1)
    world.reserve(V, Q1, request=request)
    complete_failed(world, V, Q1, failed(request, CallOutcome.INVALID_OUTPUT))
    repair = world.request(V, Q1, user="repair request")
    with pytest.raises(StagePlanMismatchError):  # a repair must differ from the original
        world.reserve(V, Q1, 2, CallKind.REPAIR, RequestBasis.REPAIRED, request)
    world.reserve(V, Q1, 2, CallKind.REPAIR, RequestBasis.REPAIRED, repair)
    world.reclaim()  # the started repair is abandoned by attempt 2
    state = world.fenced(lambda f: stages.read_stage_state(f, world.review_id, "ENC-01", V))
    assert isinstance(state.plan, PlanDispatch)
    assert (state.plan.call_kind, state.plan.request_basis, state.plan.trigger) == (
        CallKind.RETRY,
        RequestBasis.REPAIRED,
        1,
    )
    world.reserve(V, Q1, 3, CallKind.RETRY, RequestBasis.REPAIRED, repair)
    complete_failed(world, V, Q1, failed(repair, CallOutcome.INVALID_OUTPUT), sequence=3)
    with pytest.raises(StageBudgetExhaustedError):
        world.reserve(V, Q1, 3, CallKind.RETRY, RequestBasis.REPAIRED, repair)
    stage = unresolved(world, V, Q1, UnresolvedReason.INVALID_OUTPUT)
    assert stage.shape is StageShape.U1 and stage.call_sequence == 3
    with pytest.raises(StageConflictError):  # a committed stage is reused, never reserved
        world.reserve(V, Q1, 1, CallKind.INITIAL, RequestBasis.ORIGINAL, request)


def test_concurrent_allocation_is_serialized_by_the_job_lock(world: World) -> None:
    world.plan()
    world.record(Q1)
    reserved, release = threading.Event(), threading.Event()

    def first() -> None:
        def body(fence: Any) -> None:
            stages.reserve_call(
                fence,
                world.review_id,
                "ENC-01",
                V,
                sequence=1,
                call_kind=CallKind.INITIAL,
                request_basis=RequestBasis.ORIGINAL,
                request=world.request(V, Q1),
            )
            reserved.set()
            if not release.wait(WAIT_SECONDS):
                raise RuntimeError("never released")

        world.fenced(body)

    def second() -> BaseException | None:
        try:
            world.reserve(V, Q1)
        except BaseException as error:  # the outcome is asserted below
            return error
        return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        holder = pool.submit(first)
        try:
            assert reserved.wait(WAIT_SECONDS)
            waiter = pool.submit(second)
            _wait_until(lambda: _someone_waits_for_a_lock(world.engine))
        finally:
            release.set()
        holder.result(timeout=WAIT_SECONDS)
        outcome = waiter.result(timeout=WAIT_SECONDS)
    assert isinstance(outcome, StageCallInFlightError)
    assert len(_rows(world.engine)["calls"]) == 1


def test_configuration_is_bound_by_value_including_the_timeout(world: World) -> None:
    world.plan()
    world.record(Q1)
    base = world.request(V, Q1)
    shorter = world.request(V, Q1, timeout_ms=30_000)
    assert shorter.request_sha256 == base.request_sha256  # M5a excludes timeout_ms
    for changed in (
        shorter,
        world.request(V, Q1, model_id="other-model"),
        world.request(V, Q1, max_output_tokens=1024),
        world.request(V, Q1, system_text="Another system text."),
        world.request(V, Q1, prompt=ANALYST_PROMPT, system_text=ANALYST_SYSTEM),
        world.request(V, Q2),  # another question
        world.request(A, Q1),  # another purpose
    ):
        with pytest.raises(StageBindingError):
            world.reserve(V, Q1, request=changed)
    assert _rows(world.engine)["calls"] == []


def test_dependencies_are_required_and_bound(world: World) -> None:
    world.plan()
    world.record(Q1)
    world.record(Q2)
    with pytest.raises(StageDependencyError):  # no owner verification
        world.reserve(A, Q1)
    unresolved(world, V, Q2, UnresolvedReason.REQUEST_TOO_LARGE)
    with pytest.raises(StageDependencyError):  # the owner is unresolved
        world.reserve(A, Q2)
    with pytest.raises(StageDependencyError):  # U3 needs an unresolved owner
        unresolved(world, A, Q1, UnresolvedReason.VERIFICATION_UNRESOLVED)
    stage = unresolved(world, A, Q2, UnresolvedReason.VERIFICATION_UNRESOLVED)
    assert stage.shape is StageShape.U3 and stage.dependency_sha256 is not None


def test_verification_reservations_require_stored_evidence(world: World) -> None:
    world.plan()
    with pytest.raises(StageDependencyError):
        world.reserve(V, Q1)
    with pytest.raises(StageNotPlannedError):
        world.reserve(V, EvidenceQuestion(question_id="ZZZ-01", text="x", search_queries=("x",)))


# --- completion binding (clarification A) and replay ----------------------------------------------


def test_completion_replay_after_reclaim_is_a_no_op_and_a_different_one_conflicts(
    world: World,
) -> None:
    world.plan()
    world.record(Q1)
    world.record(Q2)
    request = world.request(V, Q1)
    world.reserve(V, Q1, request=request)
    result = world.verifier_result(Q1, request)
    owner = world.verified(Q1, result)
    world.fenced(
        lambda f: stages.commit_verified(
            f, world.review_id, "ENC-01", sequence=1, result=result, verified=owner
        )
    )
    retention = world.request(V, Q2)
    world.reserve(V, Q2, request=retention)
    timeout = failed(retention, CallOutcome.TIMEOUT)
    complete_failed(world, V, Q2, timeout)
    before = _rows(world.engine)
    world.reclaim()  # attempt 2 replays attempt 1's committed completions
    replayed = world.fenced(
        lambda f: stages.commit_verified(
            f, world.review_id, "ENC-01", sequence=1, result=result, verified=owner
        )
    )
    assert replayed.job_attempt == 1 and replayed.content == owner
    assert complete_failed(world, V, Q2, timeout).job_attempt == 1
    assert _rows(world.engine) == before
    different = world.verifier_result(Q1, request, latency_ms=26)
    with pytest.raises(StageConflictError):
        world.fenced(
            lambda f: stages.commit_verified(
                f, world.review_id, "ENC-01", sequence=1, result=different, verified=owner
            )
        )
    with pytest.raises(StageConflictError):
        complete_failed(world, V, Q2, failed(retention, CallOutcome.PROVIDER_FAILED))
    assert _rows(world.engine) == before


def test_completing_an_abandoned_call_is_refused(world: World) -> None:
    world.plan()
    world.record(Q1)
    request = world.request(V, Q1)
    world.reserve(V, Q1, request=request)
    world.reclaim()
    with pytest.raises(StageCallAbandonedError):
        complete_failed(world, V, Q1, failed(request, CallOutcome.TIMEOUT))
    result = world.verifier_result(Q1, request)
    owner = world.verified(Q1, result)
    with pytest.raises(StageCallAbandonedError):
        world.fenced(
            lambda f: stages.commit_verified(
                f, world.review_id, "ENC-01", sequence=1, result=result, verified=owner
            )
        )


@pytest.mark.parametrize("replay", [False, True])
def test_the_named_binding_cases_on_first_completion_and_replay(world: World, replay: bool) -> None:
    world.plan()
    world.record(Q1)
    world.record(Q2)
    request = world.request(V, Q1)
    world.reserve(V, Q1, request=request)
    world.reserve(V, Q2)  # another planned question with a call at the same sequence
    result = world.verifier_result(Q1, request)
    owner = world.verified(Q1, result)
    if replay:
        world.fenced(
            lambda f: stages.commit_verified(
                f, world.review_id, "ENC-01", sequence=1, result=result, verified=owner
            )
        )
    before = _rows(world.engine)

    def commit(question_id: str, value: StructuredResult, content: Any) -> Any:
        return world.fenced(
            lambda f: stages.commit_verified(
                f, world.review_id, question_id, sequence=1, result=value, verified=content
            )
        )

    # (a) B4: the result names the other question but keeps the selected call's digest; the
    # call is selected from the explicit question_id, never from the result.
    renamed = completed(world.request(V, Q2), result.output, request_sha256=request.request_sha256)
    with pytest.raises(StageBindingError):
        commit("ENC-01", renamed, owner)
    # (c) B7: content of another question
    q2_result = world.verifier_result(Q2, world.request(V, Q2))
    with pytest.raises(StageBindingError):
        commit("ENC-01", result, world.verified(Q2, q2_result))
    # (c) B1: a malformed content value
    with pytest.raises(InvalidStageRequestError):
        commit("ENC-01", result, "content")
    # B3: an unknown explicit question
    with pytest.raises(StagePlanMismatchError):
        commit("ZZZ-01", result, owner)
    # (b) B6: a rejection naming another question, other fields identical
    rejection = ProvenanceRejection(
        stage=RejectionStage.VERIFICATION,
        question_id="RET-01",
        reason=RejectionReason.QUOTE_NOT_FOUND,
        item_index=0,
        citation_index=0,
        rejected_count=1,
    )
    with pytest.raises(StageBindingError):
        complete_failed(world, V, Q1, result, rejection=rejection)
    assert _rows(world.engine) == before


def test_analysis_owner_identity_is_checked_at_b8(world: World) -> None:
    world.plan()
    world.record(Q1)
    world.record(Q2)
    request = world.request(V, Q1)
    world.reserve(V, Q1, request=request)
    result = world.verifier_result(Q1, request)
    owner = world.verified(Q1, result)
    world.fenced(
        lambda f: stages.commit_verified(
            f, world.review_id, "ENC-01", sequence=1, result=result, verified=owner
        )
    )
    analyst_request = world.request(A, Q1)
    world.reserve(A, Q1, request=analyst_request)
    analyst = world.analyst_result(Q1, analyst_request)
    content = world.analyzed(owner, Q1, analyst)
    q2_owner = world.verified(Q2, world.verifier_result(Q2, world.request(V, Q2)))
    changed = world.verified(Q1, world.verifier_result(Q1, request, rationale="Another reason."))
    assert changed.question_id == owner.question_id and changed != owner
    before = _rows(world.engine)
    for wrong in (q2_owner, changed):

        def with_owner(fence: Any, chosen: VerifiedQuestion = wrong) -> Any:
            return stages.commit_analyzed(
                fence,
                world.review_id,
                "ENC-01",
                sequence=1,
                result=analyst,
                analyzed=content,
                owner=chosen,
            )

        with pytest.raises(StageDependencyError):
            world.fenced(with_owner)
    assert _rows(world.engine) == before


def test_a_failed_analysis_leaves_the_verification_byte_identical(world: World) -> None:
    world.plan()
    world.record(Q1)
    request = world.request(V, Q1)
    world.reserve(V, Q1, request=request)
    result = world.verifier_result(Q1, request)
    owner = world.verified(Q1, result)
    world.fenced(
        lambda f: stages.commit_verified(
            f, world.review_id, "ENC-01", sequence=1, result=result, verified=owner
        )
    )
    verification = [r for r in _rows(world.engine)["stages"] if r["stage"] == "verification"]
    analyst_request = world.request(A, Q1)
    world.reserve(A, Q1, request=analyst_request)
    complete_failed(world, A, Q1, failed(analyst_request, CallOutcome.REFUSAL))
    unresolved(world, A, Q1, UnresolvedReason.REFUSAL)
    after = [r for r in _rows(world.engine)["stages"] if r["stage"] == "verification"]
    assert after == verification


# --- atomicity and the caller obligation ----------------------------------------------------------


def _fail_before(engine: Engine, marker: str) -> Any:
    def listener(*args: Any) -> None:
        statement: str = args[2]
        if marker in statement:
            raise RuntimeError(f"injected failure before {marker}")

    event.listen(engine, "before_cursor_execute", listener)
    return listener


def _prepared_success(world: World) -> Callable[[Any], Any]:
    world.plan()
    world.record(Q1)
    request = world.request(V, Q1)
    world.reserve(V, Q1, request=request)
    result = world.verifier_result(Q1, request)
    owner = world.verified(Q1, result)
    return lambda f: stages.commit_verified(
        f, world.review_id, "ENC-01", sequence=1, result=result, verified=owner
    )


def test_a_failure_after_the_call_update_rolls_the_success_back(world: World) -> None:
    commit = _prepared_success(world)
    before = _rows(world.engine)
    listener = _fail_before(world.engine, "INSERT INTO review_stage_results")
    try:
        with pytest.raises(stages.StageDatabaseError):
            world.fenced(commit)
    finally:
        event.remove(world.engine, "before_cursor_execute", listener)
    assert _rows(world.engine) == before
    assert [row["state"] for row in before["calls"]] == ["started"]
    world.fenced(commit)  # nothing was half-written: the commit can still succeed


def test_a_suppressed_error_inside_the_fence_commits_a_partial_effect(world: World) -> None:
    """The documented caller obligation: an M5e error must escape the fenced block."""
    commit = _prepared_success(world)
    listener = _fail_before(world.engine, "INSERT INTO review_stage_results")

    def suppressing(fence: Any) -> None:
        with contextlib.suppress(stages.StageDatabaseError):  # wrong: commits a partial effect
            commit(fence)

    try:
        world.fenced(suppressing)
    finally:
        event.remove(world.engine, "before_cursor_execute", listener)
    rows = _rows(world.engine)
    assert [row["state"] for row in rows["calls"]] == ["completed"] and rows["stages"] == []
    with pytest.raises(StageRecordInconsistentError):
        world.fenced(lambda f: stages.read_stage_state(f, world.review_id, "ENC-01", V))


# --- evidence and the U4 rules (clarification B) --------------------------------------------------


def oversized(world: World, question: EvidenceQuestion) -> EvidenceRecord:
    """A domain-valid result whose metadata makes the encoding exceed the cap."""
    stored = world.result(question)
    item = stored.items[0]
    huge = RetrievedChunk(
        item.chunk_id,
        item.revision_id,
        item.document_id,
        1,
        Fraction(1, 61),
        (ChannelHit(0, "lexical", 1, 1.0),),
        type(item.evidence)(
            item.evidence.chunk_id,
            item.evidence.text,
            item.evidence.content_sha256,
            item.evidence.ordinal,
            item.evidence.section_path,
            item.evidence.is_table,
            item.evidence.body,
            item.evidence.header,
            item.evidence.document_key,
            "t" * 4_200_000,
            item.evidence.revision_no,
            item.evidence.version_label,
            item.evidence.effective_date,
            item.evidence.source_type,
            item.evidence.authenticity,
        ),
    )
    record = EvidenceRecord(
        tenant_id=world.actor.tenant_id,
        review_id=world.review_id,
        question=question,
        result=RetrievalResult(stored.snapshot, stored.query_count, stored.k, (), (huge,)),
    )
    assert not record.fits_storage
    return record


def test_the_shared_evidence_sequence_refuses_bindings_for_both_paths(
    world: World, factory: sessionmaker[Session]
) -> None:
    world.plan()
    unplanned = EvidenceQuestion(question_id="ZZZ-01", text="x", search_queries=("x",))
    changed = EvidenceQuestion(
        question_id="ENC-01", text="A changed question?", search_queries=("encrypted at rest",)
    )
    recapture = capture_snapshot(
        factory, world.actor, vendor_id=world.review.snapshot.vendor_id, identity=HASH_IDENTITY
    )
    assert recapture.sha256 != world.review.snapshot.sha256  # another capture time
    another_snapshot = search_snapshot(
        factory, world.actor, recapture, RetrievalRequest(Q1.search_queries, 8), HashingEmbedder()
    )
    cases: list[tuple[Any, type[Exception]]] = [
        (
            EvidenceRecord(
                tenant_id=world.actor.tenant_id,
                review_id=world.review_id,
                question=unplanned,
                result=search_snapshot(
                    factory,
                    world.actor,
                    world.review.snapshot,
                    RetrievalRequest(("x",), 8),
                    HashingEmbedder(),
                ),
            ),
            StageNotPlannedError,
        ),
        (
            EvidenceRecord(
                tenant_id=world.actor.tenant_id,
                review_id=world.review_id,
                question=changed,
                result=world.result(Q1),
            ),
            StageBindingError,
        ),
        (
            EvidenceRecord(
                tenant_id=world.actor.tenant_id,
                review_id=world.review_id,
                question=Q1,
                result=another_snapshot,
            ),
            StageBindingError,
        ),
        (
            EvidenceRecord(
                tenant_id=world.actor.tenant_id,
                review_id=world.review_id,
                question=Q1,
                result=world.result(Q1, k=5),
            ),
            StageBindingError,
        ),
    ]
    for record, error in cases:

        def store(fence: Any, chosen: EvidenceRecord = record) -> Any:
            return stages.record_evidence(fence, chosen)

        with pytest.raises(error):
            world.fenced(store)
    # an oversized record fails the same binding check as a storable one (U4 and record_evidence)
    wrong_k = EvidenceRecord(
        tenant_id=world.actor.tenant_id,
        review_id=world.review_id,
        question=Q1,
        result=RetrievalResult(world.review.snapshot, 1, 5, (), oversized(world, Q1).result.items),
    )
    assert not wrong_k.fits_storage
    with pytest.raises(StageBindingError):
        world.fenced(lambda f: stages.record_evidence(f, wrong_k))
    with pytest.raises(StageBindingError):
        unresolved(world, V, Q1, UnresolvedReason.EVIDENCE_TOO_LARGE, wrong_k)
    with pytest.raises(EvidenceTooLargeError):
        world.fenced(lambda f: stages.record_evidence(f, oversized(world, Q1)))
    with pytest.raises(StagePlanMismatchError):  # U4 for a storable record
        unresolved(world, V, Q1, UnresolvedReason.EVIDENCE_TOO_LARGE, world.evidence(Q1))
    assert _rows(world.engine)["evidence"] == [] and _rows(world.engine)["stages"] == []


def test_record_evidence_replays_identically_and_conflicts_otherwise(world: World) -> None:
    world.plan()
    world.record(Q1)
    before = _rows(world.engine)
    world.record(Q1)
    assert _rows(world.engine) == before
    with pytest.raises(StageConflictError):
        world.fenced(
            lambda f: stages.record_evidence(
                f,
                EvidenceRecord(
                    tenant_id=world.actor.tenant_id,
                    review_id=world.review_id,
                    question=Q1,
                    result=RetrievalResult(world.review.snapshot, 1, 8, (), ()),
                ),
            )
        )


def test_u4_is_a_valid_closed_stage_with_identical_replay(world: World) -> None:
    world.plan()
    record = oversized(world, Q1)
    stage = unresolved(world, V, Q1, UnresolvedReason.EVIDENCE_TOO_LARGE, record)
    assert stage.shape is StageShape.U4 and stage.evidence_sha256 is None
    before = _rows(world.engine)
    replayed = unresolved(world, V, Q1, UnresolvedReason.EVIDENCE_TOO_LARGE, record)
    assert replayed == stage and _rows(world.engine) == before
    with pytest.raises(StageConflictError):  # record_evidence cannot reopen the closed stage
        world.record(Q1)
    with pytest.raises(StageConflictError):  # another requested reason for the same stage
        unresolved(world, V, Q1, UnresolvedReason.REQUEST_TOO_LARGE)
    with pytest.raises(StageConflictError):
        world.reserve(V, Q1)  # the plan reuses the committed stage
    assert _rows(world.engine) == before
    trusted = reload(world)
    first = trusted.questions[0]
    assert first.verification is not None and first.verification.shape is StageShape.U4
    assert first.evidence is None and first.verification_history.calls == ()
    world.record(Q2)
    unresolved(world, V, Q2, UnresolvedReason.REQUEST_TOO_LARGE)
    with pytest.raises(StageConflictError):  # U4 requested against another committed stage
        unresolved(world, V, Q2, UnresolvedReason.EVIDENCE_TOO_LARGE, oversized(world, Q2))


def test_a_u4_stage_with_an_evidence_row_is_inconsistent(world: World) -> None:
    world.plan()
    unresolved(world, V, Q1, UnresolvedReason.EVIDENCE_TOO_LARGE, oversized(world, Q1))
    record = world.evidence(Q1)
    _tamper(
        world.engine,
        insert(ReviewQuestionEvidence).values(
            tenant_id=world.actor.tenant_id,
            review_id=world.review_id,
            job_id=world.review.job_id,
            question_id="ENC-01",
            question_sha256=record.question_sha256,
            snapshot_sha256=record.snapshot_sha256,
            evidence_sha256=record.evidence_sha256,
            evidence_canonical=record.canonical.decode("ascii"),
            item_count=record.item_count,
            job_attempt=1,
        ),
    )
    with pytest.raises(StageRecordInconsistentError):
        reload(world)
    with pytest.raises(StageRecordInconsistentError):
        world.record(Q1)
    with pytest.raises(StageRecordInconsistentError):
        unresolved(world, V, Q1, UnresolvedReason.EVIDENCE_TOO_LARGE, oversized(world, Q1))


# --- unresolved shapes ----------------------------------------------------------------------------


def test_every_unresolved_shape_commits_and_reloads(world: World) -> None:
    world.plan()
    world.record(Q1)
    world.record(Q2)
    # U6 on Q1 verification: an invalid output, then an oversized repair request
    request = world.request(V, Q1)
    world.reserve(V, Q1, request=request)
    complete_failed(world, V, Q1, failed(request, CallOutcome.INVALID_OUTPUT))
    with pytest.raises(StagePlanMismatchError):  # the history does not end in U1
        unresolved(world, V, Q1, UnresolvedReason.INVALID_OUTPUT)
    with pytest.raises(StagePlanMismatchError):  # U5 needs a history without calls
        unresolved(world, V, Q1, UnresolvedReason.REQUEST_TOO_LARGE)
    u6 = unresolved(world, V, Q1, UnresolvedReason.REPAIR_REQUEST_TOO_LARGE)
    assert u6.shape is StageShape.U6 and u6.call_sequence == 1
    # U3 on Q1 analysis: its owner is unresolved
    with pytest.raises(StagePlanMismatchError):  # U2 needs three calls
        unresolved(world, A, Q1, UnresolvedReason.CALL_ABANDONED)
    u3 = unresolved(world, A, Q1, UnresolvedReason.VERIFICATION_UNRESOLVED)
    assert u3.shape is StageShape.U3
    # U2 on Q2 verification: three calls, the last two abandoned across attempts
    retention = world.request(V, Q2)
    world.reserve(V, Q2, request=retention)
    complete_failed(world, V, Q2, failed(retention, CallOutcome.TIMEOUT))
    world.reserve(V, Q2, 2, CallKind.RETRY, RequestBasis.ORIGINAL, retention)
    world.reclaim()  # attempt 2
    world.reserve(V, Q2, 3, CallKind.RETRY, RequestBasis.ORIGINAL, retention)
    with pytest.raises(StagePlanMismatchError):  # the last call is still in flight
        unresolved(world, V, Q2, UnresolvedReason.CALL_ABANDONED)
    world.reclaim()  # attempt 3
    u2 = unresolved(world, V, Q2, UnresolvedReason.CALL_ABANDONED)
    assert (u2.shape, u2.call_sequence, u2.job_attempt) == (StageShape.U2, 3, 3)
    # U3 on Q2 analysis as well, then the reload validates everything
    unresolved(world, A, Q2, UnresolvedReason.VERIFICATION_UNRESOLVED)
    trusted = reload(world)
    shapes = [
        (q.verification.shape if q.verification else None, q.analysis.shape if q.analysis else None)
        for q in trusted.questions
    ]
    assert shapes == [(StageShape.U6, StageShape.U3), (StageShape.U2, StageShape.U3)]
    assert trusted.job_attempt == 3


def test_u1_and_u5_commit_and_reload_for_both_stages(world: World) -> None:
    world.plan()
    world.record(Q1)
    world.record(Q2)
    with pytest.raises(StagePlanMismatchError):  # U1 needs a terminal history
        unresolved(world, V, Q2, UnresolvedReason.TIMEOUT)
    u5 = unresolved(world, V, Q2, UnresolvedReason.REQUEST_TOO_LARGE)
    assert u5.shape is StageShape.U5 and u5.evidence_sha256 is not None
    request = world.request(V, Q1)
    world.reserve(V, Q1, request=request)
    result = world.verifier_result(Q1, request)
    owner = world.verified(Q1, result)
    world.fenced(
        lambda f: stages.commit_verified(
            f, world.review_id, "ENC-01", sequence=1, result=result, verified=owner
        )
    )
    analysis_u5 = unresolved(world, A, Q1, UnresolvedReason.REQUEST_TOO_LARGE)
    assert analysis_u5.shape is StageShape.U5 and analysis_u5.dependency_sha256 is not None
    with pytest.raises(StageDependencyError):  # the owner verification is unresolved
        world.reserve(A, Q2)
    trusted = reload(world)
    assert trusted.questions[0].analysis is not None
    assert trusted.questions[1].verification is not None


# --- schema, tampering and isolation --------------------------------------------------------------


def test_database_checks_refuse_out_of_range_hand_written_rows(world: World) -> None:
    world.plan()
    world.record(Q1)
    record = world.evidence(Q1)
    base: dict[str, Any] = {
        "tenant_id": world.actor.tenant_id,
        "review_id": world.review_id,
        "job_id": world.review.job_id,
        "question_id": "ENC-01",
        "stage": "verification",
        "call_kind": "initial",
        "request_basis": "original",
        "state": "started",
        "sequence": 1,
        "request_sha256": "a" * 64,
        "prompt_sha256": VERIFIER_PROMPT.sha256,
        "model_requested": "fake-scripted-v1",
        "max_output_tokens": 4096,
        "timeout_ms": 60_000,
        "job_attempt": 1,
        "evidence_sha256": record.evidence_sha256,
    }
    for change in (
        {"max_output_tokens": 9000},
        {"timeout_ms": 999},
        {"sequence": 4},
        {"job_attempt": 11},
        {"call_kind": "retry"},  # sequence 1 must be initial
        {"dependency_sha256": "d" * 64},  # verification has no dependency
        {"state": "completed"},  # without its completion fields
        {"model_requested": "Model"},
    ):
        with pytest.raises(IntegrityError):
            _tamper(world.engine, insert(ReviewStageCall).values(**{**base, **change}))
    with pytest.raises(IntegrityError):  # a second repair for the same stage (one-repair index)
        _tamper(
            world.engine,
            insert(ReviewStageCall).values(
                **{**base, "sequence": 2, "call_kind": "repair", "request_basis": "repaired"}
            ),
            insert(ReviewStageCall).values(
                **{**base, "sequence": 3, "call_kind": "repair", "request_basis": "repaired"}
            ),
        )


def _committed_world(world: World) -> None:
    world.plan()
    world.record(Q1)
    request = world.request(V, Q1)
    world.reserve(V, Q1, request=request)
    result = world.verifier_result(Q1, request)
    owner = world.verified(Q1, result)
    world.fenced(
        lambda f: stages.commit_verified(
            f, world.review_id, "ENC-01", sequence=1, result=result, verified=owner
        )
    )
    analyst_request = world.request(A, Q1)
    world.reserve(A, Q1, request=analyst_request)
    analyst = world.analyst_result(Q1, analyst_request)
    content = world.analyzed(owner, Q1, analyst)
    world.fenced(
        lambda f: stages.commit_analyzed(
            f,
            world.review_id,
            "ENC-01",
            sequence=1,
            result=analyst,
            analyzed=content,
            owner=owner,
        )
    )


@pytest.mark.parametrize(
    "tamper",
    [
        lambda w: (
            update(ReviewPlanQuestion)
            .where(ReviewPlanQuestion.question_id == "RET-01")
            .values(question_sha256="0" * 64)
        ),
        lambda w: update(ReviewQuestionEvidence).values(item_count=0),
        lambda w: update(ReviewQuestionEvidence).values(
            evidence_canonical=func.replace(
                ReviewQuestionEvidence.evidence_canonical, "Security", "Securitz"
            )
        ),
        lambda w: update(ReviewStageCall).values(timeout_ms=30_000),
        lambda w: (
            update(ReviewStageCall)
            .where(ReviewStageCall.stage == "analysis")
            .values(prompt_sha256=VERIFIER_PROMPT.sha256)
        ),
        lambda w: (
            update(ReviewStageResult)
            .where(ReviewStageResult.stage == "verification")
            .values(
                content_canonical=func.replace(
                    ReviewStageResult.content_canonical, "Encrypted", "Encrypteb"
                )
            )
        ),
        lambda w: update(ReviewStageResult).values(job_attempt=2),
        lambda w: delete(ReviewStageResult).where(ReviewStageResult.stage == "analysis"),
        lambda w: update(Job).where(Job.id == w.review.job_id).values(attempt=0),
    ],
)
def test_the_reload_refuses_tampered_rows(world: World, tamper: Callable[[World], Any]) -> None:
    _committed_world(world)
    reload(world)  # consistent before tampering
    _tamper(world.engine, tamper(world))
    with pytest.raises(StageRecordInconsistentError):
        reload(world)


def test_the_reload_refuses_evidence_inconsistent_with_trusted_chunks(world: World) -> None:
    world.plan()
    stored = world.result(Q1)
    item = stored.items[0]
    # A self-consistent record (its own digests match) whose chunk metadata differs from the
    # database row, and one naming a chunk outside the snapshot: both decode, both fail the
    # trusted recheck.
    renamed = with_title(item, "Another title")
    outside = uuid4()  # a chunk ID the database does not have for this binding
    foreign = RetrievedChunk(
        outside,
        item.revision_id,
        item.document_id,
        1,
        Fraction(1, 61),
        (ChannelHit(0, "lexical", 1, 1.0),),
        type(item.evidence)(
            outside,
            item.evidence.text,
            item.evidence.content_sha256,
            item.evidence.ordinal,
            item.evidence.section_path,
            item.evidence.is_table,
            item.evidence.body,
            item.evidence.header,
            item.evidence.document_key,
            item.evidence.title,
            item.evidence.revision_no,
            item.evidence.version_label,
            item.evidence.effective_date,
            item.evidence.source_type,
            item.evidence.authenticity,
        ),
    )
    for candidate in (renamed, foreign):
        fresh_world_rows(world)
        record = EvidenceRecord(
            tenant_id=world.actor.tenant_id,
            review_id=world.review_id,
            question=Q1,
            result=RetrievalResult(stored.snapshot, stored.query_count, stored.k, (), (candidate,)),
        )

        def store(fence: Any, chosen: EvidenceRecord = record) -> Any:
            return stages.record_evidence(fence, chosen)

        world.fenced(store)
        with pytest.raises(StageRecordInconsistentError):
            reload(world)


def with_title(item: RetrievedChunk, title: str) -> RetrievedChunk:
    evidence = item.evidence
    return RetrievedChunk(
        item.chunk_id,
        item.revision_id,
        item.document_id,
        item.fused_rank,
        item.fused_score,
        item.hits,
        type(evidence)(
            evidence.chunk_id,
            evidence.text,
            evidence.content_sha256,
            evidence.ordinal,
            evidence.section_path,
            evidence.is_table,
            evidence.body,
            evidence.header,
            evidence.document_key,
            title,
            evidence.revision_no,
            evidence.version_label,
            evidence.effective_date,
            evidence.source_type,
            evidence.authenticity,
        ),
    )


def fresh_world_rows(world: World) -> None:
    """Remove the question's evidence row (no call references it) between candidates."""
    _tamper(
        world.engine,
        delete(ReviewQuestionEvidence).where(ReviewQuestionEvidence.review_id == world.review_id),
    )


def _constraints(engine: Engine) -> set[str]:
    with engine.connect() as connection:
        return set(
            connection.execute(
                text(
                    "SELECT conname FROM pg_constraint WHERE conrelid IN "
                    "('review_plan_questions'::regclass, 'review_question_evidence'::regclass, "
                    "'review_stage_calls'::regclass, 'review_stage_results'::regclass)"
                )
            ).scalars()
        )


def test_stage_constraints_and_the_partial_index_carry_their_accepted_names(engine: Engine) -> None:
    names = _constraints(engine)
    assert {
        "pk_review_plan_questions",
        "uq_review_plan_questions_position",
        "fk_review_plan_questions_review",
        "fk_review_plan_questions_job",
        "pk_review_question_evidence",
        "uq_review_question_evidence_digest",
        "fk_review_question_evidence_plan",
        "fk_review_question_evidence_job",
        "pk_review_stage_calls",
        "uq_review_stage_calls_request",
        "fk_review_stage_calls_plan",
        "fk_review_stage_calls_evidence",
        "fk_review_stage_calls_job",
        "pk_review_stage_results",
        "fk_review_stage_results_plan",
        "fk_review_stage_results_call",
        "fk_review_stage_results_evidence",
        "fk_review_stage_results_job",
        "ck_review_stage_calls_outcome_shape",
        "ck_review_stage_results_call_ref",
        "ck_review_question_evidence_evidence_size",
    } <= names
    counts = {
        table: len([name for name in names if name.startswith(f"ck_{table}_")])
        for table in STAGE_TABLES
    }
    assert counts == {
        "review_plan_questions": 4,
        "review_question_evidence": 7,
        "review_stage_calls": 33,
        "review_stage_results": 19,
    }
    assert all(len(name) <= 63 for name in names)
    with engine.connect() as connection:
        definition = connection.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE indexname = 'uq_review_stage_calls_one_repair'"
            )
        ).scalar_one()
        actions = set(
            connection.execute(
                text(
                    "SELECT confdeltype FROM pg_constraint WHERE contype = 'f' AND conrelid IN "
                    "('review_plan_questions'::regclass, 'review_question_evidence'::regclass, "
                    "'review_stage_calls'::regclass, 'review_stage_results'::regclass)"
                )
            ).scalars()
        )
    assert "UNIQUE INDEX" in definition and "WHERE" in definition and "repair" in definition
    assert actions == {"a"}  # NO ACTION: no cascades


def test_migration_0007_downgrades_upgrades_and_matches_the_models(
    migrated: Engine, config: Config
) -> None:
    def tables() -> set[str]:
        with migrated.connect() as connection:
            return set(
                connection.execute(
                    text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                ).scalars()
            )

    def version() -> str:
        with migrated.connect() as connection:
            found: str = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
        return found

    assert tables() >= STAGE_TABLES and version() == "0007"
    try:
        command.downgrade(config, "0006")
        assert not STAGE_TABLES & tables() and version() == "0006"
        assert "reviews" in tables()  # 0006 is untouched
        command.upgrade(config, "0007")
        assert tables() >= STAGE_TABLES and version() == "0007"
    finally:
        command.upgrade(config, "head")
    command.check(config)  # raises AutogenerateDiffsDetected on any difference


def test_the_production_registry_never_claims_the_review_job(world: World) -> None:
    assert "run_review" not in production_registry().kinds
    world.plan()
    _work(world.factory, production_registry())
    job = _job_row(world.engine, world.review.job_id)
    assert (job.status, job.attempt) == ("running", 1)  # still only the test's own claim
