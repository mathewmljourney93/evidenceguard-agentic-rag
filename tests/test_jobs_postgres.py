"""PostgreSQL integration tests for the durable job core (M3a, ADR-0007).

They use the guarded disposable-database fixtures from ``conftest.py`` and are skipped without
``EG_TEST_DATABASE_URL`` (required in CI). Concurrency tests use separate connections (``NullPool``
gives every session its own), explicit synchronisation and bounded waits; every connection also
carries a server-side ``statement_timeout``, so a failure cannot hang the run. Lease expiry is
simulated by moving ``lease_expires_at`` into the past through SQL, except in the one test that
must observe a lease expiring during a real lock wait. One test holds a row lock past the real
5-second ``lock_timeout``; its waits are bounded well below the 20-second statement timeout.
"""

import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import (
    Engine,
    Interval,
    create_engine,
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

from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_domain.jobs import (
    LOCK_TIMEOUT_SECONDS,
    JobErrorCode,
    JobIdempotencyConflictError,
    JobLeaseToken,
    JobPayload,
    JobSnapshot,
    JobStatus,
    LeaseLostError,
)
from evidenceguard_persistence import jobs as store
from evidenceguard_persistence.db import create_session_factory, transaction
from evidenceguard_persistence.models import Job, Tenant, Vendor

pytestmark = pytest.mark.integration

FOREIGN_KEY_VIOLATION = "23503"
UNIQUE_VIOLATION = "23505"
CHECK_VIOLATION = "23514"
WAIT_SECONDS = 10
REVISION = "2b2b2b2b-2222-4222-8222-22222222abcd"


@pytest.fixture
def engine(migrated: Engine, test_database_url: URL) -> Iterator[Engine]:
    """The migrated disposable database, with every statement bounded server-side."""
    bounded = create_engine(
        test_database_url,
        poolclass=NullPool,
        hide_parameters=True,
        connect_args={"options": "-c statement_timeout=20000"},
    )
    try:
        yield bounded
    finally:
        bounded.dispose()


@pytest.fixture
def factory(engine: Engine) -> sessionmaker[Session]:
    return create_session_factory(engine)


# --- helpers -------------------------------------------------------------------------------


def _tenant(engine: Engine, slug: str = "tenant-a") -> ActorContext:
    tenant_id = uuid4()
    with engine.begin() as connection:
        connection.execute(insert(Tenant).values(id=tenant_id, slug=slug, name=slug.title()))
    return ActorContext(tenant_id=tenant_id, actor_id=uuid4(), role=Role.REVIEWER)


def _enqueue(
    factory: sessionmaker[Session], actor: ActorContext, key: str = "key-1", **kwargs: Any
) -> JobSnapshot:
    with transaction(factory) as session:
        return store.enqueue(session, actor, kind="test_job", idempotency_key=key, **kwargs)


def _row(engine: Engine, job_id: UUID) -> dict[str, Any]:
    with engine.connect() as connection:
        row = connection.execute(select(Job.__table__).where(Job.id == job_id)).one()
    return dict(row._mapping)


def _set(engine: Engine, job_id: UUID, **values: Any) -> None:
    with engine.begin() as connection:
        connection.execute(update(Job).where(Job.id == job_id).values(**values))


def _interval(seconds: int) -> Any:
    return literal_column(f"interval '{seconds} seconds'", type_=Interval)


def _seconds_ago(seconds: int) -> Any:
    """A database-time expression ``seconds`` before (or, if negative, after) now."""
    return func.clock_timestamp() - _interval(seconds)


def _expire(engine: Engine, job_id: UUID) -> None:
    _set(engine, job_id, lease_expires_at=_seconds_ago(1))


def _make_due(engine: Engine, job_id: UUID) -> None:
    _set(engine, job_id, run_after=_seconds_ago(1))


def _claim_one(factory: sessionmaker[Session], worker: str = "worker-a") -> JobSnapshot:
    claimed = store.claim(factory, worker)
    assert claimed is not None
    return claimed


def _insert_raw(engine: Engine, tenant_id: UUID, **overrides: Any) -> UUID:
    values: dict[str, Any] = {
        "id": uuid4(),
        "tenant_id": tenant_id,
        "kind": "test_job",
        "idempotency_key": str(uuid4()),
        "payload": {},
        "status": "queued",
        "attempt": 0,
        "max_attempts": 3,
        "run_after": func.clock_timestamp(),
    }
    values.update(overrides)
    with engine.begin() as connection:
        connection.execute(insert(Job).values(**values))
    job_id: UUID = values["id"]
    return job_id


def _outcome(fn: Callable[[], Any]) -> Callable[[], Any]:
    """Run ``fn``, returning its result or the exception it raised (never leaking it)."""

    def run() -> Any:
        try:
            return fn()
        except Exception as error:
            return error

    return run


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


def _sqlstate(error: IntegrityError) -> str | None:
    return getattr(error.orig, "sqlstate", None)


# --- schema --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "paused"},
        {"kind": "Bad-Kind"},
        {"idempotency_key": ""},
        {"payload": ["not", "an", "object"]},
        {"attempt": 4, "max_attempts": 3},
        {"attempt": -1},
        {"max_attempts": 11},
        {"max_attempts": 0, "attempt": 0},
        {"locked_by": "worker-a"},  # queued with a lease owner
        {"status": "running", "attempt": 1},  # running without a lease
        {
            "status": "running",
            "attempt": 0,
            "locked_by": "worker-a",
            "lease_expires_at": func.clock_timestamp(),
        },
        {"status": "succeeded", "attempt": 1},  # terminal without finished_at
        {"finished_at": func.clock_timestamp()},  # queued with finished_at
        {"last_error": "Free text with spaces"},
    ],
)
def test_check_constraints_reject_invalid_rows(engine: Engine, overrides: dict[str, Any]) -> None:
    actor = _tenant(engine)

    with pytest.raises(IntegrityError) as exc_info:
        _insert_raw(engine, actor.tenant_id, **overrides)
    assert _sqlstate(exc_info.value) == CHECK_VIOLATION


def test_jobs_reference_an_existing_tenant(engine: Engine) -> None:
    with pytest.raises(IntegrityError) as exc_info:
        _insert_raw(engine, uuid4())
    assert _sqlstate(exc_info.value) == FOREIGN_KEY_VIOLATION


def test_idempotency_key_is_unique_within_a_tenant_and_kind(engine: Engine) -> None:
    actor = _tenant(engine)
    _insert_raw(engine, actor.tenant_id, idempotency_key="same")
    _insert_raw(engine, actor.tenant_id, idempotency_key="same", kind="other_job")

    with pytest.raises(IntegrityError) as exc_info:
        _insert_raw(engine, actor.tenant_id, idempotency_key="same")
    assert _sqlstate(exc_info.value) == UNIQUE_VIOLATION


# --- enqueue -------------------------------------------------------------------------------


def test_enqueue_creates_a_due_queued_job_from_the_actors_tenant(
    engine: Engine, factory: sessionmaker[Session]
) -> None:
    actor = _tenant(engine)

    job = _enqueue(factory, actor, payload=JobPayload.from_mapping({"revision_id": REVISION}))

    assert job.tenant_id == actor.tenant_id
    assert (job.status, job.attempt, job.max_attempts) == (JobStatus.QUEUED, 0, 3)
    assert _row(engine, job.id)["payload"] == {"revision_id": REVISION}


def test_identical_retry_returns_the_same_job_unchanged(
    engine: Engine, factory: sessionmaker[Session]
) -> None:
    actor = _tenant(engine)
    payload = JobPayload.from_mapping({"revision_id": REVISION, "document_id": str(UUID(int=1))})
    first = _enqueue(factory, actor, payload=payload)
    before = _row(engine, first.id)

    reordered = JobPayload.from_mapping({"document_id": str(UUID(int=1)), "revision_id": REVISION})
    again = _enqueue(factory, actor, payload=reordered)

    assert again == first
    assert _row(engine, first.id) == before
    with engine.connect() as connection:
        assert connection.execute(select(func.count()).select_from(Job)).scalar_one() == 1


@pytest.mark.parametrize(
    "change",
    [
        {"payload": JobPayload.from_mapping({"revision_id": str(UUID(int=7))})},
        {"max_attempts": 5},
    ],
)
def test_changed_request_conflicts_and_leaves_the_row_unchanged(
    engine: Engine, factory: sessionmaker[Session], change: dict[str, Any]
) -> None:
    actor = _tenant(engine)
    first = _enqueue(factory, actor, payload=JobPayload.from_mapping({"revision_id": REVISION}))
    before = _row(engine, first.id)
    request: dict[str, Any] = {"payload": JobPayload.from_mapping({"revision_id": REVISION})}
    request.update(change)

    with pytest.raises(JobIdempotencyConflictError) as exc_info:
        _enqueue(factory, actor, **request)

    assert REVISION not in str(exc_info.value)
    assert _row(engine, first.id) == before


@pytest.mark.parametrize("terminal", ["succeeded", "failed", "dead"])
def test_retrying_a_terminal_job_returns_it_without_requeueing(
    engine: Engine, factory: sessionmaker[Session], terminal: str
) -> None:
    actor = _tenant(engine)
    job = _enqueue(factory, actor, max_attempts=1)
    token = _claim_one(factory).lease_token()
    if terminal == "succeeded":
        store.complete(factory, token)
    elif terminal == "failed":
        store.fail_permanent(factory, token)
    else:
        store.fail_retryable(factory, token)  # attempt 1 of 1: dead
    before = _row(engine, job.id)

    again = _enqueue(factory, actor, max_attempts=1)

    assert again.status.value == terminal and again.id == job.id
    assert _row(engine, job.id) == before
    assert store.claim(factory, "worker-a") is None


def test_the_same_key_in_another_tenant_is_a_separate_job(
    engine: Engine, factory: sessionmaker[Session]
) -> None:
    a = _tenant(engine, "tenant-a")
    b = _tenant(engine, "tenant-b")

    job_a = _enqueue(factory, a)
    job_b = _enqueue(factory, b)

    assert job_a.id != job_b.id
    assert (job_a.tenant_id, job_b.tenant_id) == (a.tenant_id, b.tenant_id)


@pytest.mark.parametrize("conflicting", [False, True])
def test_concurrent_enqueues_resolve_through_the_unique_constraint(
    engine: Engine, factory: sessionmaker[Session], conflicting: bool
) -> None:
    actor = _tenant(engine)
    inserted = threading.Event()
    release = threading.Event()
    first_payload = JobPayload.from_mapping({"revision_id": REVISION})
    second_payload = (
        JobPayload.from_mapping({"revision_id": str(UUID(int=9))}) if conflicting else first_payload
    )

    def first() -> JobSnapshot:
        with transaction(factory) as session:
            job = store.enqueue(
                session, actor, kind="test_job", idempotency_key="key-1", payload=first_payload
            )
            inserted.set()
            assert release.wait(WAIT_SECONDS)
            return job  # commits on exit

    def second() -> JobSnapshot:
        assert inserted.wait(WAIT_SECONDS)
        return _enqueue(factory, actor, payload=second_payload)  # waits for the first commit

    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future = pool.submit(_outcome(first))
        second_future = pool.submit(_outcome(second))
        assert inserted.wait(WAIT_SECONDS)
        _wait_until(lambda: _someone_waits_for_a_lock(engine))
        release.set()
        first_result = first_future.result(timeout=WAIT_SECONDS * 3)
        second_result = second_future.result(timeout=WAIT_SECONDS * 3)

    assert isinstance(first_result, JobSnapshot)
    if conflicting:
        assert isinstance(second_result, JobIdempotencyConflictError)
    else:
        assert second_result == first_result
    with engine.connect() as connection:
        assert connection.execute(select(func.count()).select_from(Job)).scalar_one() == 1


# --- claiming ------------------------------------------------------------------------------


def test_claim_takes_only_due_jobs_in_run_after_then_id_order(
    engine: Engine, factory: sessionmaker[Session]
) -> None:
    actor = _tenant(engine)
    later = _insert_raw(engine, actor.tenant_id, run_after=_seconds_ago(-3600))
    tied = sorted(uuid4() for _ in range(2))
    for job_id in tied:
        _insert_raw(
            engine,
            actor.tenant_id,
            id=job_id,
            run_after=datetime(2026, 1, 1, tzinfo=UTC),
        )
    earliest = _insert_raw(engine, actor.tenant_id, run_after=datetime(2025, 1, 1, tzinfo=UTC))

    order = [_claim_one(factory).id for _ in range(3)]

    assert order == [earliest, *tied]
    assert store.claim(factory, "worker-a") is None  # `later` is not due
    assert _row(engine, later)["status"] == "queued"


def test_claim_creates_a_sixty_second_lease_from_database_time(
    engine: Engine, factory: sessionmaker[Session]
) -> None:
    _enqueue(factory, _tenant(engine))

    job = _claim_one(factory)

    assert job.lease_expires_at is not None
    assert (job.lease_expires_at - job.updated_at).total_seconds() == 60
    assert (job.attempt, job.locked_by) == (1, "worker-a")


@pytest.mark.parametrize("jobs", [1, 2])
def test_two_concurrent_claimers_never_share_a_job(
    engine: Engine, factory: sessionmaker[Session], jobs: int
) -> None:
    actor = _tenant(engine)
    for index in range(jobs):
        _enqueue(factory, actor, key=f"key-{index}")
    barrier = threading.Barrier(2, timeout=WAIT_SECONDS)

    def claimer(worker: str) -> Callable[[], Any]:
        def run() -> JobSnapshot | None:
            barrier.wait()
            return store.claim(factory, worker)

        return run

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_outcome(claimer(w))) for w in ("worker-a", "worker-b")]
        results = [future.result(timeout=WAIT_SECONDS * 3) for future in futures]

    claimed = [result for result in results if isinstance(result, JobSnapshot)]
    assert all(isinstance(result, JobSnapshot) or result is None for result in results)
    assert len(claimed) == jobs
    assert len({job.id for job in claimed}) == jobs  # one owner per job
    with engine.connect() as connection:
        owners = connection.execute(select(Job.id, Job.locked_by, Job.attempt)).all()
    assert all(attempt == 1 for _, _, attempt in owners)


@pytest.mark.parametrize("exhausted_count", [1, 15])
def test_exhausted_leases_never_block_an_eligible_job(
    engine: Engine, factory: sessionmaker[Session], exhausted_count: int
) -> None:
    actor = _tenant(engine)
    exhausted = [
        _insert_raw(
            engine,
            actor.tenant_id,
            status="running",
            attempt=3,
            max_attempts=3,
            locked_by="worker-gone",
            lease_expires_at=_seconds_ago(10),
            run_after=datetime(2025, 1, 1, tzinfo=UTC),  # ahead of the queued job
        )
        for _ in range(exhausted_count)
    ]
    queued = _insert_raw(engine, actor.tenant_id, run_after=_seconds_ago(1))

    claimed = _claim_one(factory)

    assert claimed.id == queued
    statuses = [_row(engine, job_id)["status"] for job_id in exhausted]
    assert statuses.count("dead") == min(exhausted_count, 10)  # one bounded sweep
    assert all(_row(engine, job_id)["attempt"] == 3 for job_id in exhausted)

    assert store.claim(factory, "worker-a") is None  # sweeps the rest; nothing eligible
    for job_id in exhausted:
        row = _row(engine, job_id)
        assert (row["status"], row["attempt"], row["last_error"]) == ("dead", 3, "lease_expired")
        assert row["finished_at"] is not None and row["locked_by"] is None


# --- ownership and fencing -----------------------------------------------------------------


def _refused_everywhere(factory: sessionmaker[Session], token: JobLeaseToken) -> None:
    for operation in (store.heartbeat, store.complete, store.fail_retryable, store.fail_permanent):
        with pytest.raises(LeaseLostError):
            operation(factory, token)
    with pytest.raises(LeaseLostError), store.fenced_transaction(factory, token):
        pytest.fail("a refused fence must not run its block")  # pragma: no cover


def test_a_reclaimed_stale_owner_is_refused_everything(
    engine: Engine, factory: sessionmaker[Session]
) -> None:
    _enqueue(factory, _tenant(engine))
    stale = _claim_one(factory, "worker-a")
    _expire(engine, stale.id)
    current = _claim_one(factory, "worker-b")
    assert (current.attempt, current.last_error) == (2, JobErrorCode.LEASE_EXPIRED)
    before = _row(engine, stale.id)

    _refused_everywhere(factory, stale.lease_token())

    assert _row(engine, stale.id) == before
    assert store.heartbeat(factory, current.lease_token()).attempt == 2


def test_the_same_worker_with_a_newer_attempt_fences_the_older_attempt(
    engine: Engine, factory: sessionmaker[Session]
) -> None:
    _enqueue(factory, _tenant(engine))
    first = _claim_one(factory, "worker-a")
    _expire(engine, first.id)
    second = _claim_one(factory, "worker-a")
    before = _row(engine, first.id)

    _refused_everywhere(factory, first.lease_token())

    assert _row(engine, first.id) == before
    assert store.complete(factory, second.lease_token()).status is JobStatus.SUCCEEDED


def test_expired_but_unreclaimed_ownership_is_refused_and_not_revived(
    engine: Engine, factory: sessionmaker[Session]
) -> None:
    _enqueue(factory, _tenant(engine))
    job = _claim_one(factory)
    _expire(engine, job.id)
    before = _row(engine, job.id)

    _refused_everywhere(factory, job.lease_token())

    assert _row(engine, job.id) == before
    assert before["status"] == "running"


def test_a_held_fence_prevents_reclaim_until_its_transaction_ends(
    engine: Engine, factory: sessionmaker[Session]
) -> None:
    actor = _tenant(engine)
    _enqueue(factory, actor)
    job = _claim_one(factory, "worker-a")
    vendor_id = uuid4()

    with store.fenced_transaction(factory, job.lease_token()) as fence:
        fence.session.execute(
            insert(Vendor).values(id=vendor_id, tenant_id=actor.tenant_id, slug="v", name="V")
        )
        # The lease expires while the fence holds the row lock: no claimant may take the job.
        fence.session.execute(
            update(Job).where(Job.id == job.id).values(lease_expires_at=_seconds_ago(1))
        )
        assert store.claim(factory, "worker-b") is None  # skips the locked row, without waiting

    # The effect committed after the lease had expired (the documented window).
    with engine.connect() as connection:
        assert connection.execute(select(Vendor.id)).scalars().all() == [vendor_id]
    reclaimed = _claim_one(factory, "worker-b")
    assert (reclaimed.id, reclaimed.attempt) == (job.id, 2)


def test_a_lease_expiring_during_a_lock_wait_is_refused_after_acquisition(
    engine: Engine, factory: sessionmaker[Session]
) -> None:
    _enqueue(factory, _tenant(engine))
    job = _claim_one(factory)
    lease_seconds = 2
    _set(engine, job.id, lease_expires_at=func.clock_timestamp() + _interval(lease_seconds))
    before = _row(engine, job.id)

    holder = engine.connect()
    try:
        holder.begin()
        # Lock the row without modifying it, so nothing re-evaluates the waiter's predicates.
        holder.execute(select(Job.id).where(Job.id == job.id).with_for_update())

        with ThreadPoolExecutor(max_workers=1) as pool:
            waiter = pool.submit(_outcome(lambda: store.heartbeat(factory, job.lease_token())))
            _wait_until(lambda: _someone_waits_for_a_lock(engine))

            def lease_has_expired() -> bool:
                with engine.connect() as connection:
                    expired: bool = connection.execute(
                        select(Job.lease_expires_at <= func.clock_timestamp()).where(
                            Job.id == job.id
                        )
                    ).scalar_one()
                return expired

            _wait_until(lease_has_expired, timeout=lease_seconds + 3)
            holder.commit()  # releases the lock without having changed the row
            result = waiter.result(timeout=WAIT_SECONDS)
    finally:
        holder.close()

    assert isinstance(result, LeaseLostError)
    assert _row(engine, job.id) == before


def test_a_failed_fenced_effect_rolls_back_everything(
    engine: Engine, factory: sessionmaker[Session]
) -> None:
    actor = _tenant(engine)
    _enqueue(factory, actor)
    job = _claim_one(factory)
    before = _row(engine, job.id)

    with (
        pytest.raises(RuntimeError),
        store.fenced_transaction(factory, job.lease_token()) as fence,
    ):
        fence.session.execute(
            insert(Vendor).values(id=uuid4(), tenant_id=actor.tenant_id, slug="v", name="V")
        )
        fence.succeed()
        raise RuntimeError("handler failed after its writes")

    with engine.connect() as connection:
        assert connection.execute(select(func.count()).select_from(Vendor)).scalar_one() == 0
    assert _row(engine, job.id) == before
    assert store.heartbeat(factory, job.lease_token()).status is JobStatus.RUNNING


# --- retries, abandonment and terminal outcomes --------------------------------------------


def test_retryable_failures_back_off_and_reach_dead_at_the_cap(
    engine: Engine, factory: sessionmaker[Session]
) -> None:
    job = _enqueue(factory, _tenant(engine), max_attempts=3)

    for attempt, delay in ((1, 5), (2, 10)):
        claimed = _claim_one(factory)
        assert claimed.attempt == attempt
        retried = store.fail_retryable(factory, claimed.lease_token())
        assert retried.status is JobStatus.QUEUED
        assert (retried.run_after - retried.updated_at).total_seconds() == delay
        assert store.claim(factory, "worker-a") is None  # not due during the backoff
        _make_due(engine, job.id)

    last = _claim_one(factory)
    dead = store.fail_retryable(factory, last.lease_token())

    assert (dead.status, dead.attempt) == (JobStatus.DEAD, 3)
    assert dead.finished_at is not None and dead.locked_by is None
    assert store.claim(factory, "worker-a") is None


def test_abandoned_leases_reach_dead_at_the_cap(
    engine: Engine, factory: sessionmaker[Session]
) -> None:
    job = _enqueue(factory, _tenant(engine), max_attempts=2)

    _claim_one(factory)
    _expire(engine, job.id)
    assert _claim_one(factory).attempt == 2
    _expire(engine, job.id)

    assert store.claim(factory, "worker-a") is None
    row = _row(engine, job.id)
    assert (row["status"], row["attempt"], row["last_error"]) == ("dead", 2, "lease_expired")
    assert row["finished_at"] is not None


def test_a_permanent_failure_ends_failed(engine: Engine, factory: sessionmaker[Session]) -> None:
    _enqueue(factory, _tenant(engine))
    job = _claim_one(factory)

    failed = store.fail_permanent(factory, job.lease_token())

    assert (failed.status, failed.attempt) == (JobStatus.FAILED, 1)
    assert failed.last_error is JobErrorCode.PERMANENT_FAILURE
    assert store.claim(factory, "worker-a") is None


def test_a_lock_held_beyond_the_lock_timeout_raises_the_fixed_error(
    engine: Engine, factory: sessionmaker[Session]
) -> None:
    actor = _tenant(engine)
    _enqueue(factory, actor)
    job = _claim_one(factory)  # a 60-second lease: still valid after the 5-second timeout
    before = _row(engine, job.id)
    block_ran = threading.Event()

    def fenced_effect() -> None:
        with store.fenced_transaction(factory, job.lease_token()) as fence:
            block_ran.set()
            fence.session.execute(
                insert(Vendor).values(id=uuid4(), tenant_id=actor.tenant_id, slug="v", name="V")
            )

    holder = engine.connect()
    try:
        holder.begin()
        holder.execute(select(Job.id).where(Job.id == job.id).with_for_update())
        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=1) as pool:
            waiter = pool.submit(_outcome(fenced_effect))
            result = waiter.result(timeout=LOCK_TIMEOUT_SECONDS + WAIT_SECONDS)
        waited = time.monotonic() - started
    finally:
        holder.rollback()
        holder.close()

    assert isinstance(result, store.JobLockTimeoutError)
    assert str(result) == "the job row could not be locked in time"
    assert waited >= LOCK_TIMEOUT_SECONDS - 0.5  # it really waited for the server-side timeout
    assert not block_ran.is_set()
    with engine.connect() as connection:
        assert connection.execute(select(func.count()).select_from(Vendor)).scalar_one() == 0
    assert _row(engine, job.id) == before
