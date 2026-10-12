"""The persistence job core (``evidenceguard_persistence.jobs``) without a database.

Compiled-SQL checks pin the claim, sweep and fence statements. A scripted session double replays
database answers and records every statement, commit, rollback and close, so the fence protocol
(lock, then a separate fresh-time check, then effects) and transaction ownership are verified on
every outcome. Real PostgreSQL behaviour is tested in ``test_jobs_postgres.py``.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import OperationalError

from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_domain.jobs import (
    JobErrorCode,
    JobIdempotencyConflictError,
    JobLeaseToken,
    JobPayload,
    JobStatus,
    LeaseLostError,
)
from evidenceguard_persistence import jobs as store
from evidenceguard_persistence.jobs import (
    FenceClosedError,
    FencedSession,
    JobEnqueueRaceError,
    JobLockTimeoutError,
)

_DIALECT = postgresql.dialect()  # type: ignore[no-untyped-call]
T0 = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)
TENANT = UUID("11111111-1111-4111-8111-111111111111")
ACTOR = ActorContext(tenant_id=TENANT, actor_id=uuid4(), role=Role.REVIEWER)
REVISION = "22222222-2222-4222-8222-222222222222"
WORKER = "worker-a"


def _sql(statement: Any) -> str:
    return " ".join(str(statement.compile(dialect=_DIALECT)).split())


# --- statements ----------------------------------------------------------------------------


def test_claim_statement_is_deterministic_bounded_and_skips_locked_rows() -> None:
    sql = _sql(store.claim_statement())

    assert "jobs.attempt < jobs.max_attempts" in sql
    assert "jobs.status = %(status_1)s::VARCHAR AND jobs.run_after <= clock_timestamp()" in sql
    assert (
        "jobs.status = %(status_2)s::VARCHAR AND jobs.lease_expires_at <= clock_timestamp()" in sql
    )
    assert "ORDER BY jobs.run_after, jobs.id" in sql
    assert sql.endswith("LIMIT %(param_1)s::INTEGER FOR UPDATE SKIP LOCKED")
    assert "now()" not in sql and "CURRENT_TIMESTAMP" not in sql


def test_sweep_statement_is_bounded_to_ten_rows_and_skips_locked_rows() -> None:
    statement = store.sweep_statement()
    sql = _sql(statement)

    assert "jobs.lease_expires_at <= clock_timestamp()" in sql
    assert "jobs.attempt >= jobs.max_attempts" in sql
    assert sql.endswith("LIMIT %(param_1)s::INTEGER FOR UPDATE SKIP LOCKED")
    assert statement.compile(dialect=_DIALECT).params["param_1"] == 10


def test_fence_locks_first_then_reads_fresh_time_separately() -> None:
    token = JobLeaseToken(job_id=uuid4(), worker_id=WORKER, attempt=1)
    lock = _sql(store.lock_statement(token))
    state = _sql(store.current_state_statement(token))

    assert lock == "SELECT jobs.id FROM jobs WHERE jobs.id = %(id_1)s::UUID FOR UPDATE"
    assert "clock_timestamp() AS db_now" in state and "FOR UPDATE" not in state
    assert store.LOCK_TIMEOUT_SQL == "SET LOCAL lock_timeout = '5s'"
    assert _sql(store.fresh_time_statement()) == "SELECT clock_timestamp() AS clock_timestamp_1"


def test_worker_ids_are_unique_and_name_no_host() -> None:
    first, second = store.new_worker_id(), store.new_worker_id()

    assert first != second and first.startswith("worker-")
    assert len(first) <= 128


# --- a scripted session ----------------------------------------------------------------------


class _Row:
    def __init__(self, mapping: dict[str, Any]) -> None:
        self._mapping = mapping


class _Result:
    def __init__(self, rows: list[dict[str, Any]] | None = None, scalar: Any = None) -> None:
        self._rows = rows or []
        self._scalar = scalar

    def first(self) -> _Row | None:
        return _Row(self._rows[0]) if self._rows else None

    def scalar_one(self) -> Any:
        return self._scalar

    def __iter__(self) -> Any:
        return iter(_Row(row) for row in self._rows)


def _job_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": uuid4(),
        "tenant_id": TENANT,
        "kind": "test_job",
        "idempotency_key": "key-1",
        "payload": {},
        "status": "queued",
        "attempt": 0,
        "max_attempts": 3,
        "run_after": T0,
        "locked_by": None,
        "lease_expires_at": None,
        "last_error": None,
        "created_at": T0,
        "updated_at": T0,
        "finished_at": None,
    }
    row.update(overrides)
    return row


def _running_row(**overrides: Any) -> dict[str, Any]:
    running: dict[str, Any] = {
        "status": "running",
        "attempt": 1,
        "locked_by": WORKER,
        "lease_expires_at": T0 + timedelta(seconds=60),
    }
    return _job_row(**{**running, **overrides})


Responder = Callable[[str, Any], _Result]


class _Session:
    """Records statements and transaction calls; ``respond`` scripts the database's answers."""

    def __init__(self, respond: Responder) -> None:
        self.respond = respond
        self.sql: list[str] = []
        self.params: list[dict[str, Any]] = []
        self.events: list[str] = []
        self.commit_error: Exception | None = None

    def execute(self, statement: Any, params: Any = None) -> _Result:
        sql = _sql(statement)
        self.sql.append(sql)
        self.params.append(dict(statement.compile(dialect=_DIALECT).params))
        return self.respond(sql, statement)

    def scalar(self, statement: Any, params: Any = None) -> Any:
        return self.execute(statement, params).scalar_one()

    def commit(self) -> None:
        self.events.append("commit")
        if self.commit_error is not None:
            raise self.commit_error

    def rollback(self) -> None:
        self.events.append("rollback")

    def close(self) -> None:
        self.events.append("close")

    def add(self, instance: object) -> None:
        self.events.append("add")

    def flush(self) -> None:
        self.events.append("flush")


def _factory(session: _Session) -> Any:
    return lambda: session


def _fence_responder(
    row: dict[str, Any] | None,
    now: datetime,
    *,
    lock_error: Exception | None = None,
    after_lock: Callable[[], None] | None = None,
) -> Responder:
    def respond(sql: str, statement: Any) -> _Result:
        if sql.startswith("SET LOCAL"):
            return _Result()
        if sql.startswith("SELECT jobs.id FROM jobs") and sql.endswith("FOR UPDATE"):
            if lock_error is not None:
                raise lock_error
            if after_lock is not None:
                after_lock()
            return _Result([{"id": row["id"]}] if row else [])
        if "AS db_now" in sql:
            return _Result([{**row, "db_now": now}] if row else [])
        if sql.startswith("UPDATE jobs"):
            return _Result()
        return _Result()

    return respond


def _token(row: dict[str, Any]) -> JobLeaseToken:
    return JobLeaseToken(job_id=row["id"], worker_id=row["locked_by"], attempt=row["attempt"])


# --- the fence ------------------------------------------------------------------------------


def test_fence_sets_lock_timeout_locks_then_checks_then_commits() -> None:
    row = _running_row()
    session = _Session(_fence_responder(row, T0 + timedelta(seconds=10)))

    with store.fenced_transaction(_factory(session), _token(row)) as fence:
        assert fence.job.status is JobStatus.RUNNING

    assert session.sql[0] == "SET LOCAL lock_timeout = '5s'"
    assert session.sql[1].startswith("SELECT jobs.id FROM jobs") and "FOR UPDATE" in session.sql[1]
    assert "AS db_now" in session.sql[2]
    assert session.events == ["commit", "close"]


def test_the_check_uses_time_read_after_the_lock_wait() -> None:
    """The lease is valid when the wait starts but expired when the lock arrives."""
    row = _running_row()
    clock = {"now": T0 + timedelta(seconds=30)}

    def lock_arrives_late() -> None:
        clock["now"] = T0 + timedelta(seconds=61)

    def respond(sql: str, statement: Any) -> _Result:
        if "AS db_now" in sql:
            return _Result([{**row, "db_now": clock["now"]}])
        return _fence_responder(row, clock["now"], after_lock=lock_arrives_late)(sql, statement)

    session = _Session(respond)
    with pytest.raises(LeaseLostError), store.fenced_transaction(_factory(session), _token(row)):
        pytest.fail("the block must not run")  # pragma: no cover

    assert session.events == ["rollback", "close"]
    assert not any(sql.startswith("UPDATE") for sql in session.sql)


@pytest.mark.parametrize(
    ("row", "token_change"),
    [
        (None, {}),  # missing job
        (_running_row(), {"worker_id": "worker-b"}),
        (_running_row(), {"attempt": 2}),
        (_job_row(status="succeeded", attempt=1, finished_at=T0), {}),
        (_running_row(lease_expires_at=T0), {}),  # expired exactly now
    ],
)
def test_fence_refuses_missing_mismatched_terminal_or_expired_ownership(
    row: dict[str, Any] | None, token_change: dict[str, Any]
) -> None:
    base = row or _running_row()
    token = JobLeaseToken(
        job_id=base["id"], worker_id=base["locked_by"] or WORKER, attempt=base["attempt"] or 1
    ).model_copy(update=token_change)
    session = _Session(_fence_responder(row, T0))

    with pytest.raises(LeaseLostError), store.fenced_transaction(_factory(session), token):
        pytest.fail("the block must not run")  # pragma: no cover

    assert session.events == ["rollback", "close"]
    assert not any(sql.startswith("UPDATE") for sql in session.sql)


def test_lock_timeout_becomes_a_fixed_error_and_rolls_back() -> None:
    class _Driver(Exception):
        sqlstate = "55P03"

    error = OperationalError("SELECT", {}, _Driver("internal lock detail"))
    row = _running_row()
    session = _Session(_fence_responder(row, T0, lock_error=error))

    with (
        pytest.raises(JobLockTimeoutError) as exc_info,
        store.fenced_transaction(_factory(session), _token(row)),
    ):
        pass  # pragma: no cover

    assert "internal lock detail" not in str(exc_info.value)
    assert exc_info.value.__cause__ is None
    assert session.events == ["rollback", "close"]


def test_a_failing_effect_rolls_back_everything() -> None:
    row = _running_row()
    session = _Session(_fence_responder(row, T0))

    with (
        pytest.raises(RuntimeError),
        store.fenced_transaction(_factory(session), _token(row)) as fence,
    ):
        fence.session.add(object())
        fence.succeed()
        raise RuntimeError("handler failed")

    assert session.events == ["add", "rollback", "close"]


def test_a_failing_commit_rolls_back_and_closes() -> None:
    row = _running_row()
    session = _Session(_fence_responder(row, T0))
    session.commit_error = OperationalError("COMMIT", {}, Exception("connection lost"))

    with (
        pytest.raises(OperationalError),
        store.fenced_transaction(_factory(session), _token(row)) as fence,
    ):
        fence.succeed()

    assert session.events == ["commit", "rollback", "close"]


def test_fenced_session_omits_direct_transaction_methods() -> None:
    """Only the ordinary methods are absent. ``execute`` still accepts arbitrary SQL, so this is
    a guard against accidents by trusted handler code, not a sandbox (ADR-0007)."""
    assert not hasattr(FencedSession, "commit")
    assert not hasattr(FencedSession, "rollback")
    assert not hasattr(FencedSession, "close")


def test_the_fence_closes_after_its_block_and_after_ending_the_attempt() -> None:
    row = _running_row()
    session = _Session(_fence_responder(row, T0))

    with store.fenced_transaction(_factory(session), _token(row)) as fence:
        done = fence.succeed()
        assert done.status is JobStatus.SUCCEEDED
        with pytest.raises(FenceClosedError):
            fence.session.add(object())
        with pytest.raises(FenceClosedError):
            fence.heartbeat()
    with pytest.raises(FenceClosedError):
        fence.session.flush()


def test_transitions_recheck_ownership_with_fresh_time() -> None:
    row = _running_row()
    times = iter([T0, T0 + timedelta(seconds=61)])  # valid at entry, expired at the transition

    def respond(sql: str, statement: Any) -> _Result:
        if "AS db_now" in sql:
            return _Result([{**row, "db_now": next(times)}])
        return _fence_responder(row, T0)(sql, statement)

    session = _Session(respond)
    with (
        pytest.raises(LeaseLostError),
        store.fenced_transaction(_factory(session), _token(row)) as fence,
    ):
        fence.heartbeat()

    assert not any(sql.startswith("UPDATE") for sql in session.sql)
    assert session.events == ["rollback", "close"]


@pytest.mark.parametrize(
    ("operation", "status"),
    [
        (store.heartbeat, JobStatus.RUNNING),
        (store.complete, JobStatus.SUCCEEDED),
        (store.fail_retryable, JobStatus.QUEUED),
        (store.fail_permanent, JobStatus.FAILED),
    ],
)
def test_single_purpose_operations_write_once_and_commit(operation: Any, status: JobStatus) -> None:
    row = _running_row()
    session = _Session(_fence_responder(row, T0 + timedelta(seconds=5)))

    result = operation(_factory(session), _token(row))

    assert result.status is status
    assert sum(sql.startswith("UPDATE jobs") for sql in session.sql) == 1
    assert session.events == ["commit", "close"]


def test_retryable_failure_on_the_last_attempt_is_dead() -> None:
    row = _running_row(attempt=3)
    session = _Session(_fence_responder(row, T0))

    result = store.fail_retryable(_factory(session), _token(row), JobErrorCode.RETRYABLE_FAILURE)

    assert result.status is JobStatus.DEAD and result.attempt == 3


# --- claim ----------------------------------------------------------------------------------


def _claim_responder(
    exhausted: list[dict[str, Any]], candidate: dict[str, Any] | None, now: datetime
) -> Responder:
    def respond(sql: str, statement: Any) -> _Result:
        if "jobs.attempt >= jobs.max_attempts" in sql:
            return _Result(exhausted)
        if "jobs.attempt < jobs.max_attempts" in sql:
            return _Result([candidate] if candidate else [])
        if sql.startswith("SELECT clock_timestamp()"):
            return _Result(scalar=now)
        return _Result()

    return respond


def test_claim_sweeps_exhausted_rows_then_claims_with_fresh_time() -> None:
    expired = T0 - timedelta(seconds=1)
    exhausted = _running_row(attempt=3, lease_expires_at=expired)
    candidate = _job_row()
    session = _Session(_claim_responder([exhausted], candidate, T0))

    claimed = store.claim(_factory(session), WORKER)

    assert claimed is not None
    assert (claimed.status, claimed.attempt, claimed.locked_by) == (JobStatus.RUNNING, 1, WORKER)
    assert claimed.lease_expires_at == T0 + timedelta(seconds=60)
    kinds = [
        "sweep"
        if "jobs.attempt >= jobs.max_attempts" in sql
        else "select"
        if "jobs.attempt < jobs.max_attempts" in sql
        else "time"
        if sql.startswith("SELECT clock_timestamp()")
        else "update"
        if sql.startswith("UPDATE jobs")
        else sql
        for sql in session.sql
    ]
    # Sweep, fresh time, mark dead; then select, fresh time, claim.
    assert kinds == ["sweep", "time", "update", "select", "time", "update"]
    dead_update, claim_update = (
        p for k, p in zip(kinds, session.params, strict=True) if k == "update"
    )
    assert dead_update["status"] == "dead" and dead_update["attempt"] == 3
    assert claim_update["status"] == "running" and claim_update["attempt"] == 1
    assert session.events == ["commit", "close"]


def test_claim_with_nothing_eligible_returns_none_and_commits() -> None:
    session = _Session(_claim_responder([], None, T0))

    assert store.claim(_factory(session), WORKER) is None
    assert session.events == ["commit", "close"]


def test_claim_rejects_an_invalid_worker_id_before_touching_the_database() -> None:
    session = _Session(_claim_responder([], None, T0))

    with pytest.raises(ValueError):
        store.claim(_factory(session), "not a worker id")
    assert session.sql == [] and session.events == []


# --- enqueue --------------------------------------------------------------------------------


def _enqueue_responder(
    inserted: dict[str, Any] | None, existing: dict[str, Any] | None
) -> Responder:
    def respond(sql: str, statement: Any) -> _Result:
        if sql.startswith("INSERT INTO jobs"):
            return _Result([inserted] if inserted else [])
        if sql.startswith("SELECT"):
            return _Result([existing] if existing else [])
        return _Result()

    return respond


def test_enqueue_inserts_with_on_conflict_and_never_commits() -> None:
    row = _job_row(payload={"revision_id": REVISION})
    session = _Session(_enqueue_responder(row, None))

    job = store.enqueue(
        session,  # type: ignore[arg-type]
        ACTOR,
        kind="test_job",
        idempotency_key="key-1",
        payload=JobPayload.from_mapping({"revision_id": REVISION}),
    )

    assert job.payload.as_dict() == {"revision_id": REVISION}
    insert = session.sql[0]
    assert "ON CONFLICT ON CONSTRAINT uq_jobs_tenant_id_kind_idempotency_key DO NOTHING" in insert
    assert "RETURNING" in insert and "clock_timestamp()" in insert
    assert session.events == []  # the caller owns the transaction


def test_enqueue_returns_an_identical_existing_job_including_terminal() -> None:
    existing = _job_row(payload={"revision_id": REVISION}, status="dead", attempt=3, finished_at=T0)
    session = _Session(_enqueue_responder(None, existing))

    job = store.enqueue(
        session,  # type: ignore[arg-type]
        ACTOR,
        kind="test_job",
        idempotency_key="key-1",
        payload=JobPayload.from_mapping({"revision_id": REVISION}),
    )

    assert job.status is JobStatus.DEAD and job.id == existing["id"]
    assert not any(sql.startswith("UPDATE") for sql in session.sql)


@pytest.mark.parametrize(
    "change",
    [{"payload": {"revision_id": str(UUID(int=1))}}, {"max_attempts": 5}],
)
def test_enqueue_conflicts_on_a_changed_request_without_values(change: dict[str, Any]) -> None:
    existing = _job_row(payload={"revision_id": REVISION})
    session = _Session(_enqueue_responder(None, existing))
    payload = change.get("payload", {"revision_id": REVISION})

    with pytest.raises(JobIdempotencyConflictError) as exc_info:
        store.enqueue(
            session,  # type: ignore[arg-type]
            ACTOR,
            kind="test_job",
            idempotency_key="key-1",
            payload=JobPayload.from_mapping(payload),
            max_attempts=change.get("max_attempts", 3),
        )

    assert REVISION not in str(exc_info.value) and "key-1" not in str(exc_info.value)
    assert not any(sql.startswith("UPDATE") for sql in session.sql)


def test_enqueue_reports_an_invisible_conflict_with_a_fixed_error() -> None:
    session = _Session(_enqueue_responder(None, None))

    with pytest.raises(JobEnqueueRaceError):
        store.enqueue(session, ACTOR, kind="test_job", idempotency_key="key-1")  # type: ignore[arg-type]


def test_enqueue_takes_the_tenant_only_from_the_actor() -> None:
    row = _job_row()
    session = _Session(_enqueue_responder(row, None))

    store.enqueue(session, ACTOR, kind="test_job", idempotency_key="key-1")  # type: ignore[arg-type]

    params = session.params[0]
    assert params["tenant_id"] == TENANT
    assert (params["status"], params["attempt"], params["max_attempts"]) == ("queued", 0, 3)
