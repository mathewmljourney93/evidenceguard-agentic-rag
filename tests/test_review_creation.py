"""Atomic review creation, cleanup and trusted reload control flow
(``evidenceguard_persistence.reviews``, M5d-B/D, ADR-0022), with session doubles and no database.

The creation steps are module functions replaced here by recording fakes, so these tests prove the
accepted commit-state and cleanup contract (Prompt 188 clarification): exact call order and counts,
retry eligibility, unknown ``COMMIT`` outcomes, process-control identity, the three-attempt bound,
input and role precedence and fixed errors. Real SQL behaviour is covered by
``tests/test_reviews_postgres.py``.
"""

import logging
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import OperationalError
from sqlalchemy.sql.elements import TextClause

from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_domain.embedding_storage import index_id, profile_id
from evidenceguard_domain.errors import PermissionDeniedError
from evidenceguard_domain.jobs import JobIdempotencyConflictError, JobPayload, JobStatus
from evidenceguard_domain.model_calls import PromptRef
from evidenceguard_domain.retrieval import (
    RETRIEVAL_CONFIG_V1,
    EmptySnapshotError,
    InvalidRetrievalRequestError,
    PendingExclusions,
    RetrievalScopeError,
    RetrievalSnapshot,
    RevisionBinding,
)
from evidenceguard_domain.reviews import (
    CreatedReview,
    InvalidReviewRequestError,
    InvalidReviewValueError,
    ReviewArtifactsUnavailableError,
    ReviewCommitOutcomeUnknownError,
    ReviewConfiguration,
    ReviewConflictRetryableError,
    ReviewDatabaseError,
    ReviewIdempotencyConflictError,
    ReviewJobConflictError,
    ReviewNotFoundError,
    ReviewRecordInconsistentError,
    ReviewRequest,
    request_sha256,
)
from evidenceguard_persistence import jobs as job_store
from evidenceguard_persistence import retrieval as retrieval_store
from evidenceguard_persistence import reviews
from evidenceguard_persistence.database_failures import (
    REVIEW_KEY_CONSTRAINT,
    DatabaseFailureCategory,
)
from evidenceguard_persistence.retrieval import (
    CaptureFailure,
    SemanticOutcome,
    capture_in_transaction,
)
from evidenceguard_retrieval.embeddings import HASH_IDENTITY

TENANT = UUID("11111111-1111-4111-8111-111111111111")
VENDOR = UUID("22222222-2222-4222-8222-222222222222")
REV = UUID("33333333-3333-4333-8333-333333333333")
DOC = UUID("44444444-4444-4444-8444-444444444444")
EXCLUDED = UUID("66666666-6666-4666-8666-666666666666")
REVIEW_ID = UUID("77777777-7777-4777-8777-777777777777")
JOB_ID = UUID("88888888-8888-4888-8888-888888888888")
CAPTURED = datetime(2026, 10, 22, 9, 30, 0, 123456, tzinfo=UTC)
KEY = "review-2026-10-22.a"
REVIEWER = ActorContext(tenant_id=TENANT, actor_id=UUID(int=1), role=Role.REVIEWER)
APPROVER = ActorContext(tenant_id=TENANT, actor_id=UUID(int=2), role=Role.APPROVER)
ADMIN = ActorContext(tenant_id=TENANT, actor_id=UUID(int=3), role=Role.ADMIN)

CONFIGURATION = ReviewConfiguration(
    template_id="vendor_security_review",
    template_version=1,
    template_sha256="26fcbe26dcc47f5991da5b741475c736cec27b1f2bd6ab515ec07ac59895786a",
    verifier_prompt=PromptRef(prompt_id="verifier", version=1, sha256="a" * 64),
    analyst_prompt=PromptRef(prompt_id="risk_analyst", version=1, sha256="b" * 64),
    model_id="fake-scripted-v1",
)
REQUEST = ReviewRequest(
    vendor_id=VENDOR, idempotency_key=KEY, identity=HASH_IDENTITY, configuration=CONFIGURATION
)
DIGEST = request_sha256(REQUEST, tenant_id=TENANT)
PROFILE = profile_id(TENANT, HASH_IDENTITY.fingerprint)
SNAPSHOT = RetrievalSnapshot(
    TENANT,
    VENDOR,
    HASH_IDENTITY,
    RETRIEVAL_CONFIG_V1,
    (
        RevisionBinding(
            REV, DOC, index_id(TENANT, REV, "md-v1", PROFILE), "md-v1", 2, "c" * 64, "d" * 64
        ),
    ),
    PendingExclusions(1, (EXCLUDED,), False),
    CAPTURED,
)


class Stop(KeyboardInterrupt):
    pass


class Later(SystemExit):
    pass


class DriverError(Exception):
    def __init__(self, sqlstate: object, constraint: object = None) -> None:
        super().__init__("PRIVATE-DRIVER-TEXT")
        self.sqlstate = sqlstate
        self.diag = SimpleNamespace(constraint_name=constraint)


def failure(sqlstate: object, constraint: object = None) -> OperationalError:
    return OperationalError(
        "PRIVATE-SQL", {"p": "PRIVATE-PARAM"}, DriverError(sqlstate, constraint)
    )


def assert_fixed(error: BaseException, kind: type[Exception]) -> None:
    assert type(error) is kind
    assert error.__cause__ is None and error.__context__ is None
    assert "PRIVATE" not in str(error) and KEY not in str(error)


# --- doubles -------------------------------------------------------------------------------------


class FakeSession:
    """Records ``commit``/``rollback``/``close``/``invalidate``; each may be scripted to raise."""

    def __init__(self, log: list[str], raises: dict[str, BaseException]) -> None:
        self.log = log
        self.raises = raises

    def _call(self, name: str) -> None:
        self.log.append(name)
        if name in self.raises:
            raise self.raises[name]

    def commit(self) -> None:
        self._call("commit")

    def rollback(self) -> None:
        self._call("rollback")

    def close(self) -> None:
        self._call("close")

    def invalidate(self) -> None:
        self._call("invalidate")


class World:
    """Scripted creation steps: each attempt pops its own script (defaults are the happy path)."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, *scripts: dict[str, Any]) -> None:
        self.scripts = list(scripts)
        self.log: list[str] = []
        self.sessions = 0
        self.current: dict[str, Any] = {}
        monkeypatch.setattr(reviews, "_begin", self._begin)
        monkeypatch.setattr(reviews, "_replay", self._replay)
        monkeypatch.setattr(reviews, "capture_in_transaction", self._capture)
        monkeypatch.setattr(reviews, "_create_job", self._create_job)
        monkeypatch.setattr(reviews, "_insert", self._insert)
        monkeypatch.setattr(reviews, "uuid4", lambda: REVIEW_ID)

    def factory(self) -> Any:
        self.sessions += 1
        self.current = self.scripts.pop(0) if self.scripts else {}
        self.log.append(f"session{self.sessions}")
        if "factory" in self.current:
            raise self.current["factory"]
        return FakeSession(self.log, self.current.get("session", {}))

    def _step(self, name: str, default: Any) -> Any:
        self.log.append(name)
        value = self.current.get(name, default)
        if isinstance(value, BaseException):
            raise value
        return value

    def _begin(self, session: Any) -> datetime:
        return self._step("begin", CAPTURED)  # type: ignore[no-any-return]

    def _replay(self, session: Any, tenant: UUID, request: Any, digest: str) -> Any:
        assert (tenant, request, digest) == (TENANT, REQUEST, DIGEST)
        return self._step("replay", None)

    def _capture(self, session: Any, captured_at: datetime, actor: Any, **kwargs: Any) -> Any:
        assert captured_at == CAPTURED and actor.tenant_id == TENANT
        assert kwargs == {
            "vendor_id": VENDOR,
            "identity": HASH_IDENTITY,
            "config": RETRIEVAL_CONFIG_V1,
        }
        return self._step("capture", SNAPSHOT)

    def _create_job(self, session: Any, actor: Any, review_id: UUID) -> Any:
        assert review_id == REVIEW_ID
        return self._step("job", SimpleNamespace(id=JOB_ID))

    def _insert(self, session: Any, **kwargs: Any) -> None:
        assert kwargs == {
            "tenant_id": TENANT,
            "review_id": REVIEW_ID,
            "request": REQUEST,
            "digest": DIGEST,
            "snapshot": SNAPSHOT,
            "job_id": JOB_ID,
        }
        self._step("insert", None)

    def create(self, actor: Any = REVIEWER, request: Any = REQUEST) -> CreatedReview:
        return reviews.create_review(self.factory, actor, request)  # type: ignore[arg-type]


BODY = ["begin", "replay", "capture", "job", "insert"]


def attempt(n: int, *tail: str) -> list[str]:
    return [f"session{n}", *BODY, *tail]


@pytest.fixture(autouse=True)
def no_logs(caplog: pytest.LogCaptureFixture) -> Iterator[None]:
    caplog.set_level(logging.DEBUG)
    yield
    assert caplog.records == []


# --- results -------------------------------------------------------------------------------------


def test_success_commits_once_and_closes(monkeypatch: pytest.MonkeyPatch) -> None:
    world = World(monkeypatch)
    created = world.create()
    assert world.log == attempt(1, "commit", "close")
    assert created == CreatedReview(
        review_id=REVIEW_ID,
        tenant_id=TENANT,
        vendor_id=VENDOR,
        request_sha256=DIGEST,
        snapshot_sha256=SNAPSHOT.sha256,
        configuration_sha256=CONFIGURATION.configuration_sha256,
        captured_at=CAPTURED,
        job_id=JOB_ID,
        replayed=False,
    )
    assert world.create(APPROVER).review_id == REVIEW_ID


def test_replay_returns_without_writing_or_committing(monkeypatch: pytest.MonkeyPatch) -> None:
    replayed = SimpleNamespace(marker="replay")
    world = World(monkeypatch, {"replay": replayed})
    assert world.create() is replayed  # type: ignore[comparison-overlap]
    assert world.log == ["session1", "begin", "replay", "rollback", "close"]


@pytest.mark.parametrize("error", [EmptySnapshotError, RetrievalScopeError])
def test_semantic_capture_outcomes_raise_the_m4d_error_without_retry(
    monkeypatch: pytest.MonkeyPatch, error: type[Exception]
) -> None:
    world = World(monkeypatch, {"capture": SemanticOutcome(error.code)})  # type: ignore[attr-defined]
    with pytest.raises(error) as caught:
        world.create()
    assert_fixed(caught.value, error)
    assert world.log == ["session1", "begin", "replay", "capture", "rollback", "close"]


@pytest.mark.parametrize(
    ("category", "retried"),
    [
        (DatabaseFailureCategory.SERIALIZATION_FAILURE, True),
        (DatabaseFailureCategory.DEADLOCK_DETECTED, True),
        (DatabaseFailureCategory.LOCK_NOT_AVAILABLE, True),
        (DatabaseFailureCategory.REVIEW_KEY_UNIQUE_VIOLATION, True),
        (DatabaseFailureCategory.QUERY_CANCELED, False),
        (DatabaseFailureCategory.OTHER, False),
    ],
)
def test_capture_failures_retry_only_retryable_categories(
    monkeypatch: pytest.MonkeyPatch, category: DatabaseFailureCategory, retried: bool
) -> None:
    world = World(monkeypatch, {"capture": CaptureFailure(category)})
    failed = ["session1", "begin", "replay", "capture", "rollback", "close"]
    if retried:
        assert world.create().job_id == JOB_ID
        assert world.log == failed + attempt(2, "commit", "close")
    else:
        with pytest.raises(ReviewDatabaseError) as caught:
            world.create()
        assert_fixed(caught.value, ReviewDatabaseError)
        assert world.log == failed


@pytest.mark.parametrize(
    ("error", "retried"),
    [
        (failure("40001"), True),
        (failure("40P01"), True),
        (failure("55P03"), True),
        (failure("23505", REVIEW_KEY_CONSTRAINT), True),
        (failure("23505", "uq_jobs_kind_idempotency_key"), False),
        (failure("57014"), False),
        (failure("08006"), False),
        (RuntimeError("PRIVATE"), False),
    ],
)
def test_body_failures_before_commit_are_classified(
    monkeypatch: pytest.MonkeyPatch, error: Exception, retried: bool
) -> None:
    world = World(monkeypatch, {"insert": error})
    if retried:
        world.create()
        assert world.log == attempt(1, "rollback", "close") + attempt(2, "commit", "close")
    else:
        with pytest.raises(ReviewDatabaseError) as caught:
            world.create()
        assert_fixed(caught.value, ReviewDatabaseError)
        assert world.log == attempt(1, "rollback", "close")


@pytest.mark.parametrize(
    ("step", "error"),
    [
        ("replay", reviews._Refusal(ReviewIdempotencyConflictError)),
        ("replay", reviews._Refusal(ReviewRecordInconsistentError)),
        ("job", reviews._Refusal(ReviewJobConflictError)),
    ],
)
def test_refusals_raise_their_fixed_error_without_retry(
    monkeypatch: pytest.MonkeyPatch, step: str, error: Any
) -> None:
    world = World(monkeypatch, {step: error})
    with pytest.raises(error.error) as caught:
        world.create()
    assert_fixed(caught.value, error.error)
    assert world.log[-2:] == ["rollback", "close"] and world.sessions == 1


def test_at_most_three_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    world = World(monkeypatch, *({"insert": failure("40001")} for _ in range(4)))
    with pytest.raises(ReviewConflictRetryableError) as caught:
        world.create()
    assert_fixed(caught.value, ReviewConflictRetryableError)
    assert world.sessions == 3
    assert world.log == [entry for n in (1, 2, 3) for entry in attempt(n, "rollback", "close")]


# --- COMMIT --------------------------------------------------------------------------------------


@pytest.mark.parametrize("state", ["40001", "40P01"])
def test_rejected_commit_is_rolled_back_closed_and_retried(
    monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    world = World(monkeypatch, {"session": {"commit": failure(state)}})
    assert world.create().review_id == REVIEW_ID
    assert world.log == attempt(1, "commit", "rollback", "close") + attempt(2, "commit", "close")


@pytest.mark.parametrize(
    "error",
    [
        failure("08007"),
        failure("40003"),
        failure("23505", REVIEW_KEY_CONSTRAINT),
        failure("55P03"),
        failure(None),
        RuntimeError("PRIVATE connection lost"),
    ],
)
def test_unknown_commit_outcome_is_invalidated_only_and_never_retried(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    world = World(monkeypatch, {"session": {"commit": error}})
    with pytest.raises(ReviewCommitOutcomeUnknownError) as caught:
        world.create()
    assert_fixed(caught.value, ReviewCommitOutcomeUnknownError)
    assert world.log == attempt(1, "commit", "invalidate")


def test_unknown_commit_with_failing_invalidate_is_still_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = World(monkeypatch, {"session": {"commit": failure("08007"), "invalidate": OSError()}})
    with pytest.raises(ReviewCommitOutcomeUnknownError):
        world.create()
    assert world.log == attempt(1, "commit", "invalidate")


def test_committed_close_failure_falls_back_to_invalidate_and_keeps_the_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = World(monkeypatch, {"session": {"close": OSError(), "invalidate": OSError()}})
    assert world.create().job_id == JOB_ID
    assert world.log == attempt(1, "commit", "close", "invalidate")


# --- cleanup after not_entered or rejected -------------------------------------------------------


@pytest.mark.parametrize("invalidate_fails", [False, True])
def test_rollback_failure_skips_close_invalidates_once_and_blocks_retry(
    monkeypatch: pytest.MonkeyPatch, invalidate_fails: bool
) -> None:
    raises: dict[str, BaseException] = {"rollback": OSError()}
    if invalidate_fails:
        raises["invalidate"] = OSError()
    world = World(monkeypatch, {"insert": failure("40001"), "session": raises})
    with pytest.raises(ReviewConflictRetryableError) as caught:
        world.create()
    assert_fixed(caught.value, ReviewConflictRetryableError)
    # A normally returning invalidate (the simulated detached-transaction case, which may not
    # reach the original connection) never restores retry eligibility.
    assert world.log == attempt(1, "rollback", "invalidate") and world.sessions == 1


def test_close_failure_invalidates_once_and_blocks_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    world = World(monkeypatch, {"insert": failure("40001"), "session": {"close": OSError()}})
    with pytest.raises(ReviewConflictRetryableError):
        world.create()
    assert world.log == attempt(1, "rollback", "close", "invalidate") and world.sessions == 1


def test_rejected_commit_with_failed_cleanup_is_not_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = World(monkeypatch, {"session": {"commit": failure("40001"), "rollback": OSError()}})
    with pytest.raises(ReviewConflictRetryableError):
        world.create()
    assert world.log == attempt(1, "commit", "rollback", "invalidate")


def test_a_decided_error_survives_failed_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    script = {
        "capture": SemanticOutcome(EmptySnapshotError.code),
        "session": {"rollback": OSError()},
    }
    world = World(monkeypatch, script)
    with pytest.raises(EmptySnapshotError):
        world.create()
    assert world.log == ["session1", "begin", "replay", "capture", "rollback", "invalidate"]


def test_session_factory_failure_is_a_database_error_without_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = World(monkeypatch, {"factory": RuntimeError("PRIVATE")})
    with pytest.raises(ReviewDatabaseError):
        world.create()
    assert world.log == ["session1"]


# --- process control -----------------------------------------------------------------------------


@pytest.mark.parametrize("step", ["begin", "replay", "capture", "job", "insert"])
def test_process_control_before_commit_cleans_up_normally_and_propagates(
    monkeypatch: pytest.MonkeyPatch, step: str
) -> None:
    marker = Stop()
    world = World(monkeypatch, {step: marker})
    with pytest.raises(Stop) as caught:
        world.create()
    assert caught.value is marker
    assert world.log[-2:] == ["rollback", "close"] and world.sessions == 1


def test_process_control_during_commit_invalidates_only(monkeypatch: pytest.MonkeyPatch) -> None:
    marker = Stop()
    world = World(monkeypatch, {"session": {"commit": marker}})
    with pytest.raises(Stop) as caught:
        world.create()
    assert caught.value is marker
    assert world.log == attempt(1, "commit", "invalidate")


def test_the_first_process_control_object_stays_primary(monkeypatch: pytest.MonkeyPatch) -> None:
    first, later = Stop(), Later()
    world = World(
        monkeypatch, {"insert": first, "session": {"rollback": later, "invalidate": Later()}}
    )
    with pytest.raises(Stop) as caught:
        world.create()
    assert caught.value is first
    assert world.log == attempt(1, "rollback", "invalidate")


def test_process_control_first_seen_in_cleanup_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    marker = Stop()
    world = World(monkeypatch, {"insert": failure("40001"), "session": {"close": marker}})
    with pytest.raises(Stop) as caught:
        world.create()
    assert caught.value is marker
    assert world.log == attempt(1, "rollback", "close", "invalidate") and world.sessions == 1


def test_process_control_while_classifying_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    marker = Stop()

    class Interrupting(Exception):
        @property
        def sqlstate(self) -> str:
            raise marker

    world = World(monkeypatch, {"insert": OperationalError("x", {}, Interrupting())})
    with pytest.raises(Stop) as caught:
        world.create()
    assert caught.value is marker
    assert world.log == attempt(1, "rollback", "close")


# --- precedence ----------------------------------------------------------------------------------


def test_input_then_role_precedence_before_any_session(monkeypatch: pytest.MonkeyPatch) -> None:
    world = World(monkeypatch)
    for actor, request, error in (
        ("actor", "request", InvalidReviewRequestError),
        (SimpleNamespace(**dict(REVIEWER)), REQUEST, InvalidReviewRequestError),
        (ADMIN, "request", InvalidReviewRequestError),
        (ADMIN, REQUEST, PermissionDeniedError),
    ):
        with pytest.raises(error) as caught:
            world.create(actor, request)
        assert_fixed(caught.value, error)
    assert world.log == [] and world.sessions == 0


def test_the_digest_binds_the_actor_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    other = ActorContext(tenant_id=UUID(int=99), actor_id=UUID(int=1), role=Role.REVIEWER)
    seen: list[str] = []

    def fake_attempt(factory: Any, actor: Any, request: Any, digest: str) -> Any:
        seen.append(digest)
        return reviews._Attempt(error=ReviewDatabaseError)

    monkeypatch.setattr(reviews, "_attempt", fake_attempt)
    for actor in (REVIEWER, other):
        with pytest.raises(ReviewDatabaseError):
            reviews.create_review(lambda: None, actor, REQUEST)  # type: ignore[arg-type]
    assert seen == [DIGEST, request_sha256(REQUEST, tenant_id=UUID(int=99))]
    assert seen[0] != seen[1]


# --- the real steps against recording sessions --------------------------------------------------


def sql(statement: Any) -> str:
    if isinstance(statement, TextClause):
        return statement.text
    return str(statement.compile(dialect=postgresql.dialect()))  # type: ignore[no-untyped-call]


class Recorder:
    def __init__(self, rows: list[Any] | None = None) -> None:
        self.statements: list[str] = []
        self.rows = rows or []

    def execute(self, statement: Any, params: Any = None) -> Any:
        self.statements.append(sql(statement))
        row = self.rows.pop(0) if self.rows else None
        return SimpleNamespace(scalar_one=lambda: CAPTURED, first=lambda: row)


def test_begin_sets_isolation_first_then_the_clock_then_the_timeouts() -> None:
    session = Recorder()
    assert reviews._begin(session) == CAPTURED  # type: ignore[arg-type]
    assert session.statements[0] == "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ WRITE"
    assert "clock_timestamp()" in session.statements[1]
    assert session.statements[2:] == [
        "SET LOCAL statement_timeout = 30000",
        "SET LOCAL lock_timeout = 5000",
    ]


def job_row(**changes: Any) -> SimpleNamespace:
    values: dict[str, Any] = {
        "id": JOB_ID,
        "tenant_id": TENANT,
        "kind": "run_review",
        "idempotency_key": str(REVIEW_ID),
        "payload": {"review_id": str(REVIEW_ID)},
        "max_attempts": 3,
        "status": "failed",
        "attempt": 3,
        "lease_owner": "worker-x",
    }
    values.update(changes)
    return SimpleNamespace(**values)


def test_job_association_ignores_lifecycle_fields_only() -> None:
    assert reviews._valid_job(job_row(), TENANT, REVIEW_ID)
    assert not reviews._valid_job(None, TENANT, REVIEW_ID)
    for changes in (
        {"tenant_id": UUID(int=5)},
        {"kind": "ingest_revision"},
        {"idempotency_key": str(UUID(int=5))},
        {"payload": {"review_id": str(REVIEW_ID), "extra": 1}},
        {"payload": {"review_id": REVIEW_ID}},
        {"max_attempts": 4},
    ):
        assert not reviews._valid_job(job_row(**changes), TENANT, REVIEW_ID)


def queued(**changes: Any) -> SimpleNamespace:
    values: dict[str, Any] = {
        "id": JOB_ID,
        "tenant_id": TENANT,
        "kind": "run_review",
        "idempotency_key": str(REVIEW_ID),
        "payload": JobPayload.from_mapping({"review_id": str(REVIEW_ID)}),
        "max_attempts": 3,
        "status": JobStatus.QUEUED,
        "attempt": 0,
    }
    values.update(changes)
    return SimpleNamespace(**values)


def test_create_job_enqueues_and_validates_exactly_the_expected_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    result: list[Any] = [queued()]

    def enqueue(session: Any, actor: Any, **kwargs: Any) -> Any:
        calls.append(kwargs)
        if isinstance(result[0], BaseException):
            raise result[0]
        return result[0]

    monkeypatch.setattr(job_store, "enqueue", enqueue)
    assert reviews._create_job(Recorder(), REVIEWER, REVIEW_ID).id == JOB_ID  # type: ignore[arg-type]
    assert calls[0]["kind"] == "run_review" and calls[0]["idempotency_key"] == str(REVIEW_ID)
    assert calls[0]["payload"].as_dict() == {"review_id": str(REVIEW_ID)}
    assert calls[0]["max_attempts"] == 3
    with pytest.raises(reviews._Refusal) as existing:
        reviews._create_job(Recorder([SimpleNamespace(id=JOB_ID)]), REVIEWER, REVIEW_ID)  # type: ignore[arg-type]
    assert existing.value.error is ReviewJobConflictError
    for bad in (
        JobIdempotencyConflictError(),
        queued(max_attempts=4),
        queued(status=JobStatus.RUNNING),
        queued(attempt=1),
        queued(tenant_id=UUID(int=5)),
        queued(payload=JobPayload.from_mapping({"review_id": str(UUID(int=5))})),
    ):
        result[0] = bad
        with pytest.raises(reviews._Refusal) as caught:
            reviews._create_job(Recorder(), REVIEWER, REVIEW_ID)  # type: ignore[arg-type]
        assert caught.value.error is ReviewJobConflictError


def stored_row(**changes: Any) -> SimpleNamespace:
    values: dict[str, Any] = {
        "id": REVIEW_ID,
        "tenant_id": TENANT,
        "vendor_id": VENDOR,
        "idempotency_key": KEY,
        "request_sha256": DIGEST,
        "configuration_sha256": CONFIGURATION.configuration_sha256,
        "snapshot_sha256": SNAPSHOT.sha256,
        "captured_at": CAPTURED,
        "provider_id": HASH_IDENTITY.provider_id,
        "embedding_model_id": HASH_IDENTITY.model_id,
        "algorithm_version": HASH_IDENTITY.algorithm_version,
        "dims": HASH_IDENTITY.dims,
        "normalization": HASH_IDENTITY.normalization,
        "fingerprint": HASH_IDENTITY.fingerprint,
        "profile_id": PROFILE,
        "retrieval_config_version": RETRIEVAL_CONFIG_V1.version,
        "retrieval_config_sha256": RETRIEVAL_CONFIG_V1.config_sha256,
        "exclusion_count": 1,
        "exclusions_truncated": False,
        "template_id": CONFIGURATION.template_id,
        "template_version": 1,
        "template_sha256": CONFIGURATION.template_sha256,
        "verifier_prompt_id": "verifier",
        "verifier_prompt_version": 1,
        "verifier_prompt_sha256": "a" * 64,
        "analyst_prompt_id": "risk_analyst",
        "analyst_prompt_version": 1,
        "analyst_prompt_sha256": "b" * 64,
        "model_id": "fake-scripted-v1",
        "max_output_tokens": 4096,
        "timeout_ms": 60000,
        "retrieval_k": 8,
        "run_review_job_id": JOB_ID,
    }
    values.update(changes)
    return SimpleNamespace(**values)


def test_replay_matches_conflicts_or_refuses_inconsistent_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    jobs: list[Any] = [job_row()]
    monkeypatch.setattr(reviews, "_job_row", lambda session, tenant, job_id: jobs[0])
    assert reviews._replay(Recorder(), TENANT, REQUEST, DIGEST) is None  # type: ignore[arg-type]
    replay = reviews._replay(Recorder([stored_row()]), TENANT, REQUEST, DIGEST)  # type: ignore[arg-type]
    assert replay is not None and replay.replayed and replay.review_id == REVIEW_ID
    for row, job, error in (
        (stored_row(request_sha256="f" * 64), job_row(), ReviewIdempotencyConflictError),
        (stored_row(), job_row(max_attempts=2), ReviewRecordInconsistentError),
        (stored_row(), None, ReviewRecordInconsistentError),
        (stored_row(captured_at=datetime(2026, 10, 22)), job_row(), ReviewRecordInconsistentError),
    ):
        jobs[0] = job
        with pytest.raises(reviews._Refusal) as caught:
            reviews._replay(Recorder([row]), TENANT, REQUEST, DIGEST)  # type: ignore[arg-type]
        assert caught.value.error is error


# --- capture_in_transaction failure boundary ----------------------------------------------------


class CaptureSession:
    """Fails at a chosen point; ``commit``/``rollback``/``close`` must never be called."""

    def __init__(self, where: str, error: BaseException) -> None:
        self.where = where
        self.error = error
        self.ended: list[str] = []

    def execute(self, statement: Any, params: Any = None) -> Any:
        if self.where == "execute":
            raise self.error
        error = self.error

        def raising(*args: Any) -> Any:
            raise error

        if self.where == "fetch":
            return SimpleNamespace(first=raising)
        return SimpleNamespace(first=lambda: SimpleNamespace(id=VENDOR), all=raising)

    def commit(self) -> None:
        self.ended.append("commit")

    def rollback(self) -> None:
        self.ended.append("rollback")

    def close(self) -> None:
        self.ended.append("close")


@pytest.mark.parametrize("where", ["execute", "fetch", "selection"])
@pytest.mark.parametrize(
    ("error", "category"),
    [
        (failure("40001"), DatabaseFailureCategory.SERIALIZATION_FAILURE),
        (failure("57014"), DatabaseFailureCategory.QUERY_CANCELED),
        (RuntimeError("PRIVATE"), DatabaseFailureCategory.OTHER),
    ],
)
def test_capture_in_transaction_returns_a_category_and_never_ends_the_transaction(
    where: str, error: Exception, category: DatabaseFailureCategory
) -> None:
    session = CaptureSession(where, error)
    outcome = capture_in_transaction(
        session,  # type: ignore[arg-type]
        CAPTURED,
        REVIEWER,
        vendor_id=VENDOR,
        identity=HASH_IDENTITY,
    )
    assert outcome == CaptureFailure(category) and session.ended == []


def test_capture_in_transaction_precedence_and_process_control() -> None:
    session = CaptureSession("execute", AssertionError("no SQL expected"))
    for kwargs, captured_at, actor, error in (
        ({"vendor_id": str(VENDOR)}, CAPTURED, ADMIN, InvalidRetrievalRequestError),
        ({}, datetime(2026, 10, 22), ADMIN, InvalidRetrievalRequestError),
        ({}, "2026-10-22", REVIEWER, InvalidRetrievalRequestError),
        ({}, CAPTURED, ADMIN, PermissionDeniedError),
    ):
        arguments = {"vendor_id": VENDOR, "identity": HASH_IDENTITY, **kwargs}
        with pytest.raises(error):
            capture_in_transaction(session, captured_at, actor, **arguments)  # type: ignore[arg-type]
    marker = Stop()
    with pytest.raises(Stop) as caught:
        capture_in_transaction(
            CaptureSession("execute", marker),  # type: ignore[arg-type]
            CAPTURED,
            REVIEWER,
            vendor_id=VENDOR,
            identity=HASH_IDENTITY,
        )
    assert caught.value is marker
    with pytest.raises(TypeError):
        capture_in_transaction(session, CAPTURED, "actor", vendor_id=VENDOR, identity=HASH_IDENTITY)  # type: ignore[arg-type]


def test_capture_snapshot_still_reports_a_capture_failure_as_a_database_error() -> None:
    from evidenceguard_domain.retrieval import RetrievalDatabaseError

    class Failing(CaptureSession):
        def execute(self, statement: Any, params: Any = None) -> Any:
            text = sql(statement)
            if text.startswith("SET") or "clock_timestamp" in text:
                return SimpleNamespace(scalar_one=lambda: CAPTURED)
            raise failure("40001")

    with pytest.raises(RetrievalDatabaseError):
        retrieval_store.capture_snapshot(
            lambda: Failing("execute", RuntimeError()),  # type: ignore[arg-type]
            REVIEWER,
            vendor_id=VENDOR,
            identity=HASH_IDENTITY,
        )


# --- trusted reload ------------------------------------------------------------------------------


def binding_rows() -> list[SimpleNamespace]:
    b = SNAPSHOT.bindings[0]
    return [
        SimpleNamespace(
            tenant_id=TENANT,
            review_id=REVIEW_ID,
            ordinal=0,
            revision_id=b.revision_id,
            document_id=b.document_id,
            index_id=b.index_id,
            chunker_version=b.chunker_version,
            chunk_count=b.chunk_count,
            manifest_sha256=b.manifest_sha256,
            vector_manifest_sha256=b.vector_manifest_sha256,
        )
    ]


def excluded_rows() -> list[SimpleNamespace]:
    return [SimpleNamespace(tenant_id=TENANT, review_id=REVIEW_ID, revision_id=EXCLUDED)]


def rebuild(**overrides: Any) -> Any:
    parts: dict[str, Any] = {
        "row": stored_row(),
        "bindings": binding_rows(),
        "excluded": excluded_rows(),
        "job": job_row(),
    }
    parts.update(overrides)
    return reviews._rebuild(
        parts["row"], parts["bindings"], parts["excluded"], parts["job"], TENANT, REVIEW_ID
    )


def test_rebuild_reconstructs_every_value() -> None:
    trusted = rebuild()
    assert trusted.request == REQUEST and trusted.snapshot == SNAPSHOT
    assert trusted.request_sha256 == DIGEST and trusted.job_id == JOB_ID


def tampered_bindings(**changes: Any) -> list[SimpleNamespace]:
    rows = binding_rows()
    vars(rows[0]).update(changes)
    return rows


@pytest.mark.parametrize(
    "overrides",
    [
        {"row": stored_row(tenant_id=UUID(int=5))},
        {"row": stored_row(id=UUID(int=5))},
        {"row": stored_row(request_sha256="0" * 64)},
        {"row": stored_row(configuration_sha256="0" * 64)},
        {"row": stored_row(snapshot_sha256="0" * 64)},
        {"row": stored_row(fingerprint="0" * 64)},
        {"row": stored_row(profile_id=UUID(int=5))},
        {"row": stored_row(retrieval_config_version="hybrid-rrf-v2")},
        {"row": stored_row(retrieval_config_sha256="0" * 64)},
        {"row": stored_row(timeout_ms=30000)},  # configuration digest no longer matches
        {"row": stored_row(idempotency_key="other-key")},  # request digest no longer matches
        {"row": stored_row(captured_at=datetime(2026, 1, 1, tzinfo=UTC))},
        {"row": stored_row(exclusion_count=0)},
        {"row": stored_row(dims=0)},
        {"bindings": tampered_bindings(ordinal=1)},
        {"bindings": tampered_bindings(tenant_id=UUID(int=5))},
        {"bindings": tampered_bindings(chunk_count=3)},
        {"bindings": []},
        {"excluded": []},
        {
            "excluded": [
                SimpleNamespace(tenant_id=TENANT, review_id=UUID(int=5), revision_id=EXCLUDED)
            ]
        },
        {"job": None},
        {"job": job_row(payload={"review_id": "other"})},
    ],
)
def test_rebuild_refuses_any_tampered_or_inconsistent_value(overrides: dict[str, Any]) -> None:
    with pytest.raises(Exception):  # noqa: B017 - any refusal maps to inconsistent in _load_body
        rebuild(**overrides)


class LoadSession:
    def __init__(self, log: list[str], body: Callable[[str], Any] | None = None) -> None:
        self.log = log
        self.body = body

    def execute(self, statement: Any, params: Any = None) -> Any:
        text = sql(statement)
        if text.startswith("SET TRANSACTION") or "clock_timestamp" in text:
            self.log.append("snapshot")
            return SimpleNamespace(scalar_one=lambda: CAPTURED)
        self.log.append("select")
        if self.body is not None:
            return self.body(text)
        return SimpleNamespace(first=lambda: None)

    def rollback(self) -> None:
        self.log.append("rollback")

    def close(self) -> None:
        self.log.append("close")


def test_load_review_precedence_before_any_session() -> None:
    opened: list[str] = []

    def factory() -> Any:
        opened.append("session")
        return LoadSession(opened)

    for actor, review_id, error in (
        ("actor", "review", InvalidReviewRequestError),
        (ADMIN, str(REVIEW_ID), InvalidReviewRequestError),
        (ADMIN, REVIEW_ID, PermissionDeniedError),
    ):
        with pytest.raises(error) as caught:
            reviews.load_review(factory, actor, review_id)  # type: ignore[arg-type]
        assert_fixed(caught.value, error)
    assert opened == []


def test_load_review_not_found_reads_one_read_only_transaction() -> None:
    log: list[str] = []
    with pytest.raises(ReviewNotFoundError) as caught:
        reviews.load_review(lambda: LoadSession(log), REVIEWER, REVIEW_ID)  # type: ignore[arg-type]
    assert_fixed(caught.value, ReviewNotFoundError)
    assert log == ["snapshot", "snapshot", "select", "rollback", "close"]


def test_load_review_maps_inconsistent_rows_and_database_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log: list[str] = []

    def inconsistent(load: Any, session: Any, tenant: UUID, review_id: UUID) -> None:
        load.error = ReviewRecordInconsistentError

    monkeypatch.setattr(reviews, "_load_body", inconsistent)
    with pytest.raises(ReviewRecordInconsistentError) as caught:
        reviews.load_review(lambda: LoadSession(log), REVIEWER, REVIEW_ID)  # type: ignore[arg-type]
    assert_fixed(caught.value, ReviewRecordInconsistentError)

    def failing(load: Any, session: Any, tenant: UUID, review_id: UUID) -> None:
        raise failure("40001")

    monkeypatch.setattr(reviews, "_load_body", failing)
    with pytest.raises(ReviewDatabaseError) as database:
        reviews.load_review(lambda: LoadSession(log), REVIEWER, REVIEW_ID)  # type: ignore[arg-type]
    assert_fixed(database.value, ReviewDatabaseError)

    def factory() -> Any:
        raise RuntimeError("PRIVATE")

    with pytest.raises(ReviewDatabaseError):
        reviews.load_review(factory, REVIEWER, REVIEW_ID)  # type: ignore[arg-type]


def test_load_review_process_control_survives_a_failing_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = Stop()

    def interrupted(load: Any, session: Any, tenant: UUID, review_id: UUID) -> None:
        raise marker

    class FailingCleanup(LoadSession):
        def rollback(self) -> None:
            raise OSError("cleanup failed")

    monkeypatch.setattr(reviews, "_load_body", interrupted)
    with pytest.raises(Stop) as caught:
        reviews.load_review(lambda: FailingCleanup([]), REVIEWER, REVIEW_ID)  # type: ignore[arg-type]
    assert caught.value is marker


def test_load_body_maps_a_rebuild_refusal_to_inconsistent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reviews, "_job_row", lambda session, tenant, job_id: job_row())

    def rows(text: str) -> Any:
        if "FROM reviews" in text:
            return SimpleNamespace(first=lambda: stored_row(timeout_ms=30000))
        if "FROM review_bindings" in text:
            return iter(binding_rows())
        return iter(excluded_rows())

    load = reviews._Load()
    reviews._load_body(load, LoadSession([], rows), TENANT, REVIEW_ID)  # type: ignore[arg-type]
    assert load.error is ReviewRecordInconsistentError and load.result is None
    load = reviews._Load()

    def good(text: str) -> Any:
        if "FROM reviews" in text:
            return SimpleNamespace(first=lambda: stored_row())
        return rows(text)

    reviews._load_body(load, LoadSession([], good), TENANT, REVIEW_ID)  # type: ignore[arg-type]
    assert load.error is None and load.result is not None and load.result.snapshot == SNAPSHOT


# --- worker seams (``evidenceguard_worker.review_seams``) ----------------------------------------

PINNED = ReviewConfiguration(
    template_id="vendor_security_review",
    template_version=1,
    template_sha256="26fcbe26dcc47f5991da5b741475c736cec27b1f2bd6ab515ec07ac59895786a",
    verifier_prompt=PromptRef(
        prompt_id="verifier",
        version=1,
        sha256="629f8f972a0f5d6247a54364da59f04d53a1a023472fa00830ebedfe106b007d",
    ),
    analyst_prompt=PromptRef(
        prompt_id="risk_analyst",
        version=1,
        sha256="f8e485998dc2ff79c839100c27326a6e119135788060237a9fcbe5fed0051b29",
    ),
    model_id="fake-scripted-v1",
)
PINNED_REQUEST = ReviewRequest(
    vendor_id=VENDOR, idempotency_key=KEY, identity=HASH_IDENTITY, configuration=PINNED
)


def test_seam_creation_checks_inputs_role_and_artifacts_before_any_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from evidenceguard_worker import review_seams

    created: list[Any] = []
    monkeypatch.setattr(
        review_seams, "create_review", lambda factory, actor, request: created.append(request)
    )
    for actor, request, error in (
        ("actor", PINNED_REQUEST, InvalidReviewRequestError),
        (ADMIN, "request", InvalidReviewRequestError),
        (ADMIN, PINNED_REQUEST, PermissionDeniedError),
        (REVIEWER, REQUEST, ReviewArtifactsUnavailableError),  # unregistered prompt digests
    ):
        with pytest.raises(error) as caught:
            review_seams.create_review_with_artifacts(lambda: None, actor, request)  # type: ignore[arg-type]
        assert_fixed(caught.value, error)
    assert created == []
    review_seams.create_review_with_artifacts(lambda: None, REVIEWER, PINNED_REQUEST)  # type: ignore[arg-type]
    assert created == [PINNED_REQUEST]


def test_seam_reload_resolves_the_pinned_template_and_prompts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import hashlib

    from evidenceguard_domain.reviews import TrustedReview
    from evidenceguard_worker import review_seams

    trusted = TrustedReview(
        review_id=REVIEW_ID,
        tenant_id=TENANT,
        request=PINNED_REQUEST,
        request_sha256=request_sha256(PINNED_REQUEST, tenant_id=TENANT),
        snapshot=SNAPSHOT,
        job_id=JOB_ID,
    )
    monkeypatch.setattr(review_seams, "load_review", lambda factory, actor, review_id: trusted)
    resolved = review_seams.load_trusted_review(lambda: None, REVIEWER, REVIEW_ID)  # type: ignore[arg-type]
    assert resolved.review == trusted
    assert resolved.template.ref.sha256 == PINNED.template_sha256
    assert resolved.verifier.ref == PINNED.verifier_prompt
    assert resolved.analyst.ref == PINNED.analyst_prompt
    for text_, ref in (
        (resolved.verifier_system_text, PINNED.verifier_prompt),
        (resolved.analyst_system_text, PINNED.analyst_prompt),
    ):
        assert hashlib.sha256(text_.encode("utf-8")).hexdigest() == ref.sha256
    assert KEY not in repr(resolved)
    with pytest.raises(InvalidReviewValueError):  # a system text must match its pinned digest
        review_seams.ResolvedReview(
            review=trusted,
            template=resolved.template,
            verifier=resolved.verifier,
            verifier_system_text=resolved.verifier_system_text + " ",
            analyst=resolved.analyst,
            analyst_system_text=resolved.analyst_system_text,
        )
    with pytest.raises(InvalidReviewValueError):  # prompts in swapped roles
        review_seams.ResolvedReview(
            review=trusted,
            template=resolved.template,
            verifier=resolved.analyst,
            verifier_system_text=resolved.analyst_system_text,
            analyst=resolved.verifier,
            analyst_system_text=resolved.verifier_system_text,
        )


def test_seam_reload_maps_missing_artifacts_and_keeps_precedence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from evidenceguard_domain.reviews import TrustedReview
    from evidenceguard_worker import review_seams

    unpinned = TrustedReview(
        review_id=REVIEW_ID,
        tenant_id=TENANT,
        request=REQUEST,
        request_sha256=DIGEST,
        snapshot=SNAPSHOT,
        job_id=JOB_ID,
    )
    loads: list[UUID] = []

    def load(factory: Any, actor: Any, review_id: UUID) -> Any:
        loads.append(review_id)
        return unpinned

    monkeypatch.setattr(review_seams, "load_review", load)
    with pytest.raises(ReviewArtifactsUnavailableError) as caught:
        review_seams.load_trusted_review(lambda: None, REVIEWER, REVIEW_ID)  # type: ignore[arg-type]
    assert_fixed(caught.value, ReviewArtifactsUnavailableError)
    for actor, review_id, error in (
        ("actor", REVIEW_ID, InvalidReviewRequestError),
        (ADMIN, str(REVIEW_ID), InvalidReviewRequestError),
        (ADMIN, REVIEW_ID, PermissionDeniedError),
    ):
        with pytest.raises(error):
            review_seams.load_trusted_review(lambda: None, actor, review_id)  # type: ignore[arg-type]
    assert loads == [REVIEW_ID]


# --- migration 0006 against the models (offline SQL; no database) --------------------------------


def test_offline_migration_0006_renders_the_model_tables_and_constraint_names() -> None:
    import io
    import re

    from alembic import command
    from sqlalchemy.schema import CreateTable

    from evidenceguard_persistence.migration_config import alembic_config
    from evidenceguard_persistence.models import Review, ReviewBinding, ReviewExcludedRevision

    buffer = io.StringIO()
    command.upgrade(alembic_config(output_buffer=buffer), "0005:0006", sql=True)
    rendered = buffer.getvalue()
    tables = re.findall(r"CREATE TABLE (\w+)", rendered)
    assert tables == ["reviews", "review_bindings", "review_excluded_revisions"]
    model_ddl = "".join(
        str(CreateTable(model.__table__).compile(dialect=postgresql.dialect()))  # type: ignore[arg-type, no-untyped-call]
        for model in (Review, ReviewBinding, ReviewExcludedRevision)
    )
    names = set(re.findall(r"CONSTRAINT (\w+)", rendered))
    assert names == set(re.findall(r"CONSTRAINT (\w+)", model_ddl))
    assert "uq_reviews_tenant_id_idempotency_key" in names and len(names) == 49
    assert "ON CONFLICT" not in rendered


# --- Prompt 190 Finding A: process control while consuming read_snapshot's setup result ----------


class ClockSession:
    """A reload session whose snapshot setup or cleanup can be scripted to raise.

    ``clock`` raises from the clock result's ``scalar_one()`` (after ``execute`` returned);
    ``execute_clock`` raises from ``execute`` itself; ``rollback`` raises from cleanup."""

    def __init__(self, script: dict[str, BaseException], log: list[str]) -> None:
        self.script = script
        self.log = log

    def execute(self, statement: Any, params: Any = None) -> Any:
        text_ = sql(statement)
        if "clock_timestamp" in text_:
            self.log.append("clock")
            if "execute_clock" in self.script:
                raise self.script["execute_clock"]
            raising = self.script.get("clock")

            def scalar_one() -> datetime:
                if raising is not None:
                    raise raising
                return CAPTURED

            return SimpleNamespace(scalar_one=scalar_one)
        self.log.append("set" if text_.startswith("SET") else "select")
        if "body" in self.script and not text_.startswith("SET"):
            raise self.script["body"]
        return SimpleNamespace(first=lambda: None)

    def rollback(self) -> None:
        self.log.append("rollback")
        if "rollback" in self.script:
            raise self.script["rollback"]

    def close(self) -> None:
        self.log.append("close")


CONTROL_KINDS = [KeyboardInterrupt, SystemExit, GeneratorExit]
CLEANUPS = ["normal", "ordinary_failure", "later_interrupt"]


def cleanup_script(cleanup: str) -> dict[str, BaseException]:
    if cleanup == "ordinary_failure":
        return {"rollback": OSError("cleanup failed")}
    if cleanup == "later_interrupt":
        return {"rollback": Later()}
    return {}


def run_load(script: dict[str, BaseException]) -> tuple[BaseException, list[str]]:
    log: list[str] = []
    with pytest.raises(BaseException) as caught:
        reviews.load_review(lambda: ClockSession(script, log), REVIEWER, REVIEW_ID)  # type: ignore[arg-type]
    return caught.value, log


@pytest.mark.parametrize("cleanup", CLEANUPS)
@pytest.mark.parametrize("kind", CONTROL_KINDS)
def test_reload_setup_clock_result_interrupt_propagates_as_the_first_object(
    kind: type[BaseException], cleanup: str
) -> None:
    marker = kind()
    raised, log = run_load({"clock": marker, **cleanup_script(cleanup)})
    assert raised is marker
    # read_snapshot always closes after rolling back; the reload body never ran.
    assert log == ["set", "clock", "rollback", "close"]


@pytest.mark.parametrize("cleanup", CLEANUPS)
@pytest.mark.parametrize("where", ["execute_clock", "body"])
def test_reload_execute_and_body_interrupt_controls(where: str, cleanup: str) -> None:
    marker = Stop()
    raised, _log = run_load({where: marker, **cleanup_script(cleanup)})
    assert raised is marker


def test_reload_cleanup_interrupt_alone_propagates_and_ordinary_setup_failures_stay_fixed() -> None:
    marker = Stop()
    raised, log = run_load({"rollback": marker})
    assert raised is marker and log[-2:] == ["rollback", "close"]
    scripts: tuple[dict[str, BaseException], ...] = (
        {"clock": OSError("PRIVATE setup")},
        {"clock": OSError("PRIVATE setup"), "rollback": OSError("cleanup")},
    )
    for script in scripts:
        raised, _ = run_load(script)
        assert_fixed(raised, ReviewDatabaseError)


# --- Prompt 190 Finding B: timestamp validation failures are normalized -------------------------


class _RaisingZone(tzinfo):
    def __init__(self, error: BaseException) -> None:
        self.error = error

    def utcoffset(self, dt: datetime | None) -> timedelta:
        raise self.error

    def dst(self, dt: datetime | None) -> timedelta:
        raise self.error

    def tzname(self, dt: datetime | None) -> str:
        raise self.error


class NoSQLSession:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append("execute")
        raise AssertionError("no SQL expected")

    def __getattr__(self, name: str) -> Any:
        self.calls.append(name)
        raise AssertionError(name)


def test_capture_timestamp_whose_offset_raises_is_a_fixed_invalid_request() -> None:
    session = NoSQLSession()
    clock = datetime(2026, 10, 22, 9, 30, tzinfo=_RaisingZone(RuntimeError("PRIVATE_CLOCK_MARKER")))
    for actor in (REVIEWER, ADMIN):  # inputs precede the role check
        with pytest.raises(InvalidRetrievalRequestError) as caught:
            capture_in_transaction(
                session,  # type: ignore[arg-type]
                clock,
                actor,
                vendor_id=VENDOR,
                identity=HASH_IDENTITY,
            )
        error = caught.value
        assert type(error) is InvalidRetrievalRequestError
        assert error.__cause__ is None and error.__context__ is None
        assert "PRIVATE_CLOCK_MARKER" not in str(error) and "PRIVATE_CLOCK_MARKER" not in repr(
            error
        )
    assert session.calls == []
    with pytest.raises(TypeError):  # the actor check still comes first
        capture_in_transaction(session, clock, "actor", vendor_id=VENDOR, identity=HASH_IDENTITY)  # type: ignore[arg-type]
    assert session.calls == []


@pytest.mark.parametrize("kind", CONTROL_KINDS)
def test_capture_timestamp_process_control_propagates_as_the_same_object(
    kind: type[BaseException],
) -> None:
    marker = kind()
    session = NoSQLSession()
    clock = datetime(2026, 10, 22, 9, 30, tzinfo=_RaisingZone(marker))
    with pytest.raises(kind) as caught:
        capture_in_transaction(session, clock, REVIEWER, vendor_id=VENDOR, identity=HASH_IDENTITY)  # type: ignore[arg-type]
    assert caught.value is marker and session.calls == []


def test_capture_timestamp_controls_naive_invalid_and_valid() -> None:
    session = NoSQLSession()
    for clock in (datetime(2026, 10, 22, 9, 30), "2026-10-22T09:30:00Z", None):
        with pytest.raises(InvalidRetrievalRequestError):
            capture_in_transaction(
                session,  # type: ignore[arg-type]
                clock,  # type: ignore[arg-type]
                REVIEWER,
                vendor_id=VENDOR,
                identity=HASH_IDENTITY,
            )
    assert session.calls == []
    offset = datetime(2026, 10, 22, 11, 30, tzinfo=timezone(timedelta(hours=2)))
    failing = CaptureSession("execute", failure("40001"))
    outcome = capture_in_transaction(
        failing,  # type: ignore[arg-type]
        offset,
        REVIEWER,
        vendor_id=VENDOR,
        identity=HASH_IDENTITY,
    )
    assert outcome == CaptureFailure(DatabaseFailureCategory.SERIALIZATION_FAILURE)


# --- Prompt 191: process control while reading a row attribute in the reload body ---------------


class RaisingRow:
    """A review row whose every attribute read raises the designated object."""

    def __init__(self, error: BaseException) -> None:
        self._error = error

    def __getattr__(self, name: str) -> Any:
        raise self._error


class RowSession(ClockSession):
    """Normal snapshot setup; the review row raises on attribute access in the reload body."""

    def __init__(self, row_error: BaseException, script: dict[str, BaseException], log: list[str]):
        super().__init__(script, log)
        self.row_error = row_error

    def execute(self, statement: Any, params: Any = None) -> Any:
        text_ = sql(statement)
        if text_.startswith("SET") or "clock_timestamp" in text_:
            return super().execute(statement, params)
        self.log.append("select")
        if "FROM reviews" in text_:
            return SimpleNamespace(first=lambda: RaisingRow(self.row_error))
        return iter(())  # bindings and exclusions


@pytest.mark.parametrize("cleanup", CLEANUPS)
@pytest.mark.parametrize("kind", CONTROL_KINDS)
def test_reload_row_attribute_interrupt_propagates_as_the_first_object(
    kind: type[BaseException], cleanup: str
) -> None:
    marker = kind()
    log: list[str] = []
    with pytest.raises(BaseException) as caught:
        reviews.load_review(
            lambda: RowSession(marker, cleanup_script(cleanup), log),  # type: ignore[arg-type]
            REVIEWER,
            REVIEW_ID,
        )
    assert caught.value is marker
    assert "select" in log and log[-2:] == ["rollback", "close"]
