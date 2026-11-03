"""M5e persistence control flow without a database (``evidenceguard_persistence.review_stages``,
ADR-0023): argument and fence-association precedence, the write failure boundary, M3 error
pass-through, and the reload's precedence, failure mapping and process-control precedence.

Sessions are scripted doubles; they prove control flow, not SQL semantics
(``test_review_stages_postgres.py`` covers those against PostgreSQL).
"""

import socket
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.sql.elements import TextClause

from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_domain.embedding_storage import index_id, profile_id
from evidenceguard_domain.errors import PermissionDeniedError
from evidenceguard_domain.evidence import EvidenceQuestion
from evidenceguard_domain.jobs import JobPayload, JobSnapshot, JobStatus, LeaseLostError
from evidenceguard_domain.model_calls import (
    CallOutcome,
    ModelPurpose,
    PromptRef,
    StructuredRequest,
    StructuredResult,
)
from evidenceguard_domain.retrieval import (
    RETRIEVAL_CONFIG_V1,
    PendingExclusions,
    RetrievalSnapshot,
    RevisionBinding,
)
from evidenceguard_domain.review_stages import (
    CallKind,
    PlannedQuestionSet,
    RequestBasis,
    StageKind,
    UnresolvedReason,
)
from evidenceguard_domain.reviews import (
    ReviewConfiguration,
    ReviewRequest,
    TrustedReview,
    request_sha256,
)
from evidenceguard_persistence import review_stages as stages
from evidenceguard_persistence.document_views import READ_SNAPSHOT_SQL
from evidenceguard_persistence.jobs import FenceClosedError, FencedSession
from evidenceguard_persistence.review_stages import (
    InvalidStageRequestError,
    StageConflictError,
    StageDatabaseError,
    StageFenceMismatchError,
    StageRecordInconsistentError,
)
from evidenceguard_retrieval.embeddings import HASH_IDENTITY

TENANT = UUID("11111111-1111-4111-8111-111111111111")
REVIEW = uuid4()
JOB = uuid4()
VENDOR = uuid4()
NOW = datetime(2026, 10, 23, 9, 0, tzinfo=UTC)
REVIEWER = ActorContext(tenant_id=TENANT, actor_id=uuid4(), role=Role.REVIEWER)
ADMIN = ActorContext(tenant_id=TENANT, actor_id=uuid4(), role=Role.ADMIN)
OUTSIDER = ActorContext(tenant_id=uuid4(), actor_id=uuid4(), role=Role.REVIEWER)
QUESTION = EvidenceQuestion(question_id="ENC-01", text="Encrypted?", search_queries=("enc",))
PROMPT = PromptRef(prompt_id="verifier", version=1, sha256="1" * 64)


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("a test attempted network access")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


class Stop(KeyboardInterrupt):
    pass


class Later(SystemExit):
    pass


class DriverError(Exception):
    def __init__(self, sqlstate: str) -> None:
        super().__init__("PRIVATE-DRIVER-TEXT")
        self.sqlstate = sqlstate


def assert_fixed(error: BaseException, kind: type[Exception]) -> None:
    assert type(error) is kind
    assert error.__cause__ is None and error.__context__ is None
    assert "PRIVATE" not in str(error)


def sql(statement: Any) -> str:
    if isinstance(statement, TextClause):
        return statement.text
    return str(statement.compile(dialect=postgresql.dialect()))  # type: ignore[no-untyped-call]


# --- fences ---------------------------------------------------------------------------------------


def job(**changes: Any) -> JobSnapshot:
    values: dict[str, Any] = {
        "id": JOB,
        "tenant_id": TENANT,
        "kind": "run_review",
        "idempotency_key": str(REVIEW),
        "payload": JobPayload.from_mapping({"review_id": str(REVIEW)}),
        "status": JobStatus.RUNNING,
        "attempt": 1,
        "max_attempts": 3,
        "run_after": NOW,
        "locked_by": "w-1",
        "lease_expires_at": NOW + timedelta(seconds=60),
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(changes)
    return JobSnapshot(**values)


class Row(SimpleNamespace):
    @property
    def _mapping(self) -> dict[str, Any]:
        return dict(vars(self))


class FenceSession:
    """The session behind a ``FencedSession``: answers the ownership recheck and the review row,
    then raises ``after`` (if given) at the first other statement."""

    def __init__(
        self,
        *,
        owner: JobSnapshot | None = None,
        review: Any = "default",
        after: BaseException | None = None,
    ) -> None:
        self.owner = owner if owner is not None else job()
        self.review = (
            SimpleNamespace(run_review_job_id=JOB, tenant_id=TENANT)
            if review == "default"
            else review
        )
        self.after = after
        self.statements: list[str] = []

    def execute(self, statement: Any, params: Any = None) -> Any:
        text = sql(statement)
        self.statements.append(text)
        if "clock_timestamp() AS db_now" in text:
            if self.owner is None:
                return SimpleNamespace(first=lambda: None)
            mapping = {**self.owner.model_dump(), "db_now": NOW}
            mapping["payload"] = self.owner.payload.as_dict()
            return SimpleNamespace(first=lambda: Row(**mapping))
        if "FROM reviews" in text:
            return SimpleNamespace(first=lambda: self.review)
        if self.after is not None:
            raise self.after
        return SimpleNamespace(first=lambda: None, all=lambda: [], scalar_one=lambda: None)


class Gate:
    def __init__(self, open_: bool = True) -> None:
        self.open = open_

    def _require_open(self) -> None:
        if not self.open:
            raise FenceClosedError()


def fence(session: FenceSession, *, job_: JobSnapshot | None = None, open_: bool = True) -> Any:
    return SimpleNamespace(
        session=FencedSession(session, Gate(open_)),  # type: ignore[arg-type]
        job=job_ if job_ is not None else job(),
    )


# --- argument checks before any statement ---------------------------------------------------------


def structured_request() -> StructuredRequest:
    return StructuredRequest(
        purpose=ModelPurpose.VERIFIER,
        prompt=PROMPT,
        model_id="fake-scripted-v1",
        question_id="ENC-01",
        system_text="system",
        user_text="user",
        max_output_tokens=4096,
    )


def failed_result() -> StructuredResult:
    return StructuredResult(
        request_sha256="a" * 64,
        purpose=ModelPurpose.VERIFIER,
        question_id="ENC-01",
        outcome=CallOutcome.TIMEOUT,
        dispatched=True,
        output=None,
        model_requested="fake-scripted-v1",
        model_used=None,
        usage=None,
        latency_ms=None,
    )


loose: Any = stages  # deliberately ill-typed calls below
ARGUMENT_CASES: list[Any] = [
    lambda f: loose.record_planned_questions(f, "planned"),
    lambda f: loose.read_stage_state(f, str(REVIEW), "ENC-01", StageKind.VERIFICATION),
    lambda f: loose.read_stage_state(f, REVIEW, "enc-01", StageKind.VERIFICATION),
    lambda f: loose.read_stage_state(f, REVIEW, "ENC-01", "verification"),
    lambda f: loose.record_evidence(f, "evidence"),
    lambda f: loose.reserve_call(
        f,
        REVIEW,
        "ENC-01",
        StageKind.VERIFICATION,
        sequence=0,
        call_kind=CallKind.INITIAL,
        request_basis=RequestBasis.ORIGINAL,
        request=structured_request(),
    ),
    lambda f: loose.reserve_call(
        f,
        REVIEW,
        "ENC-01",
        StageKind.VERIFICATION,
        sequence=1,
        call_kind="initial",
        request_basis=RequestBasis.ORIGINAL,
        request=structured_request(),
    ),
    lambda f: loose.reserve_call(
        f,
        REVIEW,
        "ENC-01",
        StageKind.VERIFICATION,
        sequence=True,
        call_kind=CallKind.INITIAL,
        request_basis=RequestBasis.ORIGINAL,
        request=structured_request(),
    ),
    lambda f: loose.complete_failed_call(
        f,
        REVIEW,
        "ENC-01",
        StageKind.VERIFICATION,
        sequence=1,
        result=failed_result(),
        rejection="rejection",
    ),
    lambda f: loose.commit_verified(
        f,
        REVIEW,
        "ENC-01",
        sequence=1,
        result=failed_result(),
        verified="verified",
    ),
    lambda f: loose.commit_verified(
        f,
        REVIEW,
        None,
        sequence=1,
        result=failed_result(),
        verified="verified",
    ),
    lambda f: loose.commit_analyzed(
        f,
        REVIEW,
        "ENC-01",
        sequence=1,
        result=failed_result(),
        analyzed="a",
        owner="o",
    ),
    lambda f: loose.commit_unresolved(
        f, REVIEW, "ENC-01", StageKind.VERIFICATION, reason=UnresolvedReason.EVIDENCE_TOO_LARGE
    ),
    lambda f: loose.commit_unresolved(
        f, REVIEW, "ENC-01", StageKind.ANALYSIS, reason=UnresolvedReason.EVIDENCE_TOO_LARGE
    ),
    lambda f: loose.commit_unresolved(
        f,
        REVIEW,
        "ENC-01",
        StageKind.VERIFICATION,
        reason=UnresolvedReason.VERIFICATION_UNRESOLVED,
    ),
    lambda f: loose.commit_unresolved(
        f,
        REVIEW,
        "ENC-01",
        StageKind.VERIFICATION,
        reason="timeout",
    ),
]


@pytest.mark.parametrize("case", ARGUMENT_CASES)
def test_argument_errors_precede_any_statement(case: Any) -> None:
    session = FenceSession()
    with pytest.raises(InvalidStageRequestError) as caught:
        case(fence(session))
    assert_fixed(caught.value, InvalidStageRequestError)
    assert session.statements == []


def test_a_fence_that_is_not_structurally_a_stage_fence_is_an_argument_error() -> None:
    for bad in (None, SimpleNamespace(session="s", job=job()), SimpleNamespace(job=job())):
        with pytest.raises(InvalidStageRequestError):
            stages.read_stage_state(bad, REVIEW, "ENC-01", StageKind.VERIFICATION)  # type: ignore[arg-type]


# --- fence association ----------------------------------------------------------------------------


def read(f: Any, review: UUID = REVIEW) -> Any:
    return stages.read_stage_state(f, review, "ENC-01", StageKind.VERIFICATION)


@pytest.mark.parametrize(
    "job_",
    [
        job(kind="index_revision"),
        job(idempotency_key=str(uuid4())),
        job(status=JobStatus.QUEUED, locked_by=None, lease_expires_at=None, attempt=0),
    ],
)
def test_a_foreign_or_non_running_job_is_a_fence_mismatch_before_any_statement(
    job_: JobSnapshot,
) -> None:
    session = FenceSession()
    with pytest.raises(StageFenceMismatchError) as caught:
        read(fence(session, job_=job_))
    assert_fixed(caught.value, StageFenceMismatchError)
    assert session.statements == []


def test_a_review_that_does_not_name_the_job_is_a_fence_mismatch() -> None:
    for review in (None, SimpleNamespace(run_review_job_id=uuid4(), tenant_id=TENANT)):
        session = FenceSession(review=review)
        with pytest.raises(StageFenceMismatchError):
            read(fence(session))
        assert len(session.statements) == 2  # ownership recheck, review row


def test_lease_loss_and_a_closed_fence_pass_through_unchanged() -> None:
    lost = FenceSession(owner=job(locked_by="w-2"))
    with pytest.raises(LeaseLostError):
        read(fence(lost))
    marker = LeaseLostError()

    def raising(session: Any, token: Any) -> Any:
        raise marker

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(stages, "recheck_ownership", raising)
        with pytest.raises(LeaseLostError) as caught:
            read(fence(FenceSession()))
    assert caught.value is marker
    with pytest.raises(FenceClosedError):
        read(fence(FenceSession(), open_=False))


@pytest.mark.parametrize(
    ("failure", "error"),
    [
        (OperationalError("PRIVATE", {}, DriverError("57014")), StageDatabaseError),
        (OperationalError("PRIVATE", {}, DriverError("55P03")), StageDatabaseError),
        (IntegrityError("PRIVATE", {}, DriverError("23503")), StageDatabaseError),
        (IntegrityError("PRIVATE", {}, DriverError("23505")), StageConflictError),
        (RuntimeError("PRIVATE"), StageDatabaseError),
    ],
)
def test_ordinary_failures_after_association_are_fixed(
    failure: Exception, error: type[Exception]
) -> None:
    with pytest.raises(error) as caught:
        read(fence(FenceSession(after=failure)))
    assert_fixed(caught.value, error)


def test_process_control_in_a_write_api_propagates_as_the_same_object() -> None:
    marker = Stop()
    with pytest.raises(Stop) as caught:
        read(fence(FenceSession(after=marker)))
    assert caught.value is marker


def test_the_failure_boundary_maps_refusals_and_keeps_m3_errors() -> None:
    def refused() -> None:
        stages._refuse(StageRecordInconsistentError)

    with pytest.raises(StageRecordInconsistentError) as caught:
        stages._write(refused)
    assert_fixed(caught.value, StageRecordInconsistentError)
    closed = FenceClosedError()

    def closing() -> None:
        raise closed

    with pytest.raises(FenceClosedError) as kept:
        stages._write(closing)
    assert kept.value is closed


# --- reload precedence ----------------------------------------------------------------------------


def trusted_review() -> TrustedReview:
    profile = profile_id(TENANT, HASH_IDENTITY.fingerprint)
    revision, document = sorted([uuid4(), uuid4()])
    snapshot = RetrievalSnapshot(
        TENANT,
        VENDOR,
        HASH_IDENTITY,
        RETRIEVAL_CONFIG_V1,
        (
            RevisionBinding(
                revision,
                document,
                index_id(TENANT, revision, "md-v1", profile),
                "md-v1",
                1,
                "a" * 64,
                "b" * 64,
            ),
        ),
        PendingExclusions(0, (), False),
        NOW,
    )
    request = ReviewRequest(
        vendor_id=VENDOR,
        idempotency_key="review-1",
        identity=HASH_IDENTITY,
        configuration=ReviewConfiguration(
            template_id="vendor_security_review",
            template_version=1,
            template_sha256="2" * 64,
            verifier_prompt=PROMPT,
            analyst_prompt=PromptRef(prompt_id="risk_analyst", version=1, sha256="3" * 64),
            model_id="fake-scripted-v1",
        ),
    )
    return TrustedReview(
        review_id=REVIEW,
        tenant_id=TENANT,
        request=request,
        request_sha256=request_sha256(request, tenant_id=TENANT),
        snapshot=snapshot,
        job_id=JOB,
    )


REVIEW_VALUE = trusted_review()
PLANNED = PlannedQuestionSet(tenant_id=TENANT, review_id=REVIEW, questions=(QUESTION,))


def test_reload_precedence_runs_before_any_session() -> None:
    def factory() -> Any:
        raise AssertionError("a session was opened")

    other_plan = PlannedQuestionSet(tenant_id=TENANT, review_id=uuid4(), questions=(QUESTION,))
    cases: list[tuple[Any, Any, Any, type[Exception]]] = [
        ("actor", REVIEW_VALUE, PLANNED, InvalidStageRequestError),
        (REVIEWER, "review", PLANNED, InvalidStageRequestError),
        (REVIEWER, REVIEW_VALUE, "planned", InvalidStageRequestError),
        (ADMIN, REVIEW_VALUE, PLANNED, PermissionDeniedError),
        (OUTSIDER, REVIEW_VALUE, PLANNED, InvalidStageRequestError),
        (REVIEWER, REVIEW_VALUE, other_plan, InvalidStageRequestError),
    ]
    for actor, review, planned, error in cases:
        with pytest.raises(error):
            stages.load_trusted_stages(factory, actor, review, planned)  # type: ignore[arg-type]


# --- reload failure mapping and process control ---------------------------------------------------


class ReloadSession:
    """A reload session: ``read_snapshot``'s setup, then scripted data statements and cleanup.

    ``clock`` raises from the clock result's ``scalar_one()``; ``execute_clock`` from ``execute``;
    ``body`` from the first data statement; ``row`` from attribute access on the review row;
    ``rollback`` from cleanup. Without a script the data statements return empty results."""

    def __init__(self, script: dict[str, BaseException], log: list[str]) -> None:
        self.script = script
        self.log = log

    def execute(self, statement: Any, params: Any = None) -> Any:
        text = sql(statement)
        if text == READ_SNAPSHOT_SQL:
            self.log.append("set")
            return SimpleNamespace()
        if "clock_timestamp" in text and "FROM" not in text:
            self.log.append("clock")
            if "execute_clock" in self.script:
                raise self.script["execute_clock"]
            raising = self.script.get("clock")

            def scalar_one() -> datetime:
                if raising is not None:
                    raise raising
                return NOW

            return SimpleNamespace(scalar_one=scalar_one)
        if text.startswith("SET LOCAL statement_timeout"):
            self.log.append("timeout")
            return SimpleNamespace()
        self.log.append("select")
        if "body" in self.script:
            raise self.script["body"]
        if "row" in self.script and ("FROM reviews" in text or "FROM jobs" in text):
            error = self.script["row"]

            class Raising:
                def __getattr__(self, name: str) -> Any:
                    raise error

            return SimpleNamespace(first=lambda: Raising())
        return SimpleNamespace(first=lambda: None, __iter__=lambda: iter(()))

    def rollback(self) -> None:
        self.log.append("rollback")
        if "rollback" in self.script:
            raise self.script["rollback"]

    def close(self) -> None:
        self.log.append("close")


class Empty:
    """``list(result)`` over the reload's multi-row statements."""

    def __iter__(self) -> Any:
        return iter(())


def run_reload(script: dict[str, BaseException]) -> tuple[BaseException, list[str]]:
    log: list[str] = []

    class Session(ReloadSession):
        def execute(self, statement: Any, params: Any = None) -> Any:
            result = super().execute(statement, params)
            if isinstance(result, SimpleNamespace) and hasattr(result, "__iter__"):
                return (
                    Empty()
                    if "FROM review" in sql(statement) and "reviews" not in sql(statement)
                    else result
                )
            return result

    with pytest.raises(BaseException) as caught:
        stages.load_trusted_stages(
            lambda: Session(script, log),  # type: ignore[arg-type]
            REVIEWER,
            REVIEW_VALUE,
            PLANNED,
        )
    return caught.value, log


CONTROL_KINDS = [KeyboardInterrupt, SystemExit, GeneratorExit]
CLEANUPS = ["normal", "ordinary_failure", "later_interrupt"]


def cleanup_script(cleanup: str) -> dict[str, BaseException]:
    if cleanup == "ordinary_failure":
        return {"rollback": OSError("cleanup failed")}
    if cleanup == "later_interrupt":
        return {"rollback": Later()}
    return {}


@pytest.mark.parametrize("cleanup", CLEANUPS)
@pytest.mark.parametrize("kind", CONTROL_KINDS)
@pytest.mark.parametrize("where", ["clock", "execute_clock", "body", "row"])
def test_reload_process_control_survives_cleanup_by_identity(
    where: str, kind: type[BaseException], cleanup: str
) -> None:
    marker = kind()
    raised, log = run_reload({where: marker, **cleanup_script(cleanup)})
    assert raised is marker
    assert log[-2:] == ["rollback", "close"]


def test_reload_cleanup_interrupt_alone_propagates() -> None:
    marker = Stop()
    raised, log = run_reload({"rollback": marker})
    assert raised is marker and log[-2:] == ["rollback", "close"]


def test_reload_ordinary_failures_are_fixed_database_errors() -> None:
    scripts: list[dict[str, BaseException]] = [
        {"clock": OSError("PRIVATE setup")},
        {"clock": OSError("PRIVATE setup"), "rollback": OSError("cleanup")},
        {"body": OperationalError("PRIVATE", {}, DriverError("57014"))},
    ]
    for script in scripts:
        raised, _ = run_reload(script)
        assert_fixed(raised, StageDatabaseError)
    raised, _ = run_reload({"row": RuntimeError("PRIVATE row")})
    assert_fixed(raised, StageRecordInconsistentError)


def test_reload_without_review_rows_is_inconsistent() -> None:
    raised, log = run_reload({})
    assert_fixed(raised, StageRecordInconsistentError)
    assert log[:3] == ["set", "clock", "timeout"]


# --- migration 0007 against the models (offline SQL; no database) ---------------------------------


def test_offline_migration_0007_renders_the_model_tables_constraints_and_index() -> None:
    import io
    import re

    from alembic import command
    from sqlalchemy.schema import CreateIndex, CreateTable

    from evidenceguard_persistence.migration_config import alembic_config
    from evidenceguard_persistence.models import (
        ReviewPlanQuestion,
        ReviewQuestionEvidence,
        ReviewStageCall,
        ReviewStageResult,
    )

    buffer = io.StringIO()
    command.upgrade(alembic_config(output_buffer=buffer), "0006:0007", sql=True)
    rendered = buffer.getvalue()
    tables = re.findall(r"CREATE TABLE (\w+)", rendered)
    assert tables == [
        "review_plan_questions",
        "review_question_evidence",
        "review_stage_calls",
        "review_stage_results",
    ]
    models = (ReviewPlanQuestion, ReviewQuestionEvidence, ReviewStageCall, ReviewStageResult)
    dialect = postgresql.dialect()  # type: ignore[no-untyped-call]
    model_ddl = "".join(
        str(CreateTable(model.__table__).compile(dialect=dialect))  # type: ignore[arg-type]
        for model in models
    )
    names = set(re.findall(r"CONSTRAINT (\w+)", rendered))
    assert names == set(re.findall(r"CONSTRAINT (\w+)", model_ddl))
    assert len(names) == 81 and all(len(name) <= 63 for name in names)
    (index,) = ReviewStageCall.__table__.indexes  # type: ignore[attr-defined]
    model_index = str(CreateIndex(index).compile(dialect=dialect))
    assert "CREATE UNIQUE INDEX uq_review_stage_calls_one_repair" in rendered
    assert "WHERE call_kind = 'repair'" in rendered and "WHERE call_kind = 'repair'" in model_index
    assert "ON DELETE" not in rendered and "CASCADE" not in rendered
    assert "output" not in " ".join(tables)  # E7: no output table
    for column in ("started_at", "completed_at", "created_at", "committed_at"):
        assert f"{column} >" not in rendered and f"{column} <" not in rendered  # V12
    buffer = io.StringIO()
    command.downgrade(alembic_config(output_buffer=buffer), "0007:0006", sql=True)
    assert re.findall(r"DROP TABLE (\w+)", buffer.getvalue()) == list(reversed(tables))


# --- the E7 evidence-state classification (clarification B) ---------------------------------------


def test_the_evidence_state_rule_accepts_a_well_formed_u4_and_refuses_inconsistent_states() -> None:
    from datetime import UTC
    from datetime import datetime as moment

    from evidenceguard_domain.review_stages import (
        CallRecord,
        ReservationState,
        StageOutcome,
        StageRecord,
    )

    when = moment(2026, 10, 23, tzinfo=UTC)
    call = CallRecord(
        tenant_id=TENANT,
        review_id=REVIEW,
        job_id=JOB,
        question_id="ENC-01",
        stage=StageKind.VERIFICATION,
        sequence=1,
        call_kind=CallKind.INITIAL,
        request_basis=RequestBasis.ORIGINAL,
        request_sha256="a" * 64,
        prompt_sha256="1" * 64,
        model_requested="fake-scripted-v1",
        max_output_tokens=4096,
        timeout_ms=60_000,
        evidence_sha256="e" * 64,
        dependency_sha256=None,
        job_attempt=1,
        state=ReservationState.STARTED,
        started_at=when,
    )

    def stage(reason: UnresolvedReason, evidence: str | None) -> StageRecord:
        return StageRecord(
            tenant_id=TENANT,
            review_id=REVIEW,
            job_id=JOB,
            question_id="ENC-01",
            stage=StageKind.VERIFICATION,
            outcome=StageOutcome.UNRESOLVED,
            unresolved_reason=reason,
            call_sequence=None,
            request_sha256=None,
            evidence_sha256=evidence,
            dependency_sha256=None,
            content=None,
            job_attempt=1,
            committed_at=when,
        )

    u4 = stage(UnresolvedReason.EVIDENCE_TOO_LARGE, None)
    u5 = stage(UnresolvedReason.REQUEST_TOO_LARGE, "e" * 64)
    holds = stages._evidence_state_holds
    assert holds(None, (), None) and holds("e" * 64, (), None)
    assert holds("e" * 64, (call,), None)
    assert holds(None, (), u4)  # a well-formed U4: no evidence row and no calls
    assert holds("e" * 64, (), u5)
    assert not holds(None, (call,), None)  # verification calls without an evidence row
    assert not holds(None, (), u5)  # a non-U4 stage without an evidence row
    assert not holds("e" * 64, (), u4)  # a U4 with an evidence row
    assert not holds(None, (call,), u4)  # a U4 with calls
    assert not holds("f" * 64, (call,), None)  # a call naming other evidence
    assert not holds("f" * 64, (), u5)  # a stage naming other evidence


# --- Prompt 201 Finding A at the persistence boundary --------------------------------------------


def _malformed_question(**changes: Any) -> EvidenceQuestion:
    values: dict[str, Any] = {
        "question_id": "ENC-01",
        "text": "Encrypted?",
        "search_queries": ("enc",),
        "requires_documentary_support": False,
    }
    values.update(changes)
    return EvidenceQuestion.model_construct(**values)


@pytest.mark.parametrize(
    "changes",
    [
        {"requires_documentary_support": 1},
        {"requires_documentary_support": 0},
        {"search_queries": ["PRIVATE-CANARY-SEARCH"]},
    ],
)
def test_question_boundary_planned_questions_are_refused_before_sql(
    changes: dict[str, Any],
) -> None:
    import warnings

    planned = PlannedQuestionSet(tenant_id=TENANT, review_id=REVIEW, questions=(QUESTION,))
    object.__setattr__(planned, "questions", (_malformed_question(**changes),))
    session = FenceSession()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with pytest.raises(InvalidStageRequestError) as refused:
            stages.record_planned_questions(fence(session), planned)
    assert_fixed(refused.value, InvalidStageRequestError)
    assert session.statements == [] and [str(w.message) for w in caught] == []


def test_question_boundary_valid_planned_questions_reach_the_fence() -> None:
    planned = PlannedQuestionSet(
        tenant_id=TENANT, review_id=REVIEW, questions=(_malformed_question(),)
    )
    session = FenceSession(after=RuntimeError("PRIVATE stop after association"))
    with pytest.raises(StageDatabaseError):
        stages.record_planned_questions(fence(session), planned)
    assert len(session.statements) == 3  # ownership recheck, review row, then the plan rows
