"""PostgreSQL integration tests for the worker runtime (M3b, ADR-0008).

They use the guarded disposable-database fixtures from ``conftest.py`` and are skipped without
``EG_TEST_DATABASE_URL`` (required in CI). Every connection carries a server-side
``statement_timeout``; the worker runs with short test-only timings, and every wait on the test
side is bounded. Test handlers are defined here; they write their durable effect to a test-only
table created in the disposable database, keyed by job ID so the effect is idempotent.
"""

import json
import logging
import threading
import time
from collections.abc import Callable, Collection, Iterator
from dataclasses import replace
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, create_engine, func, insert, literal_column, select, text, update
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy.types import Interval

from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_domain.jobs import JobLeaseToken, JobSnapshot, LeaseLostError
from evidenceguard_observability.jsonlog import JsonFormatter
from evidenceguard_persistence import jobs as job_store
from evidenceguard_persistence.db import create_session_factory, transaction
from evidenceguard_persistence.models import Job, Tenant
from evidenceguard_worker.context import JobContext, PermanentJobError, RetryableJobError
from evidenceguard_worker.registry import HandlerRegistry, JobHandler
from evidenceguard_worker.runtime import (
    DatabaseJobStore,
    Timings,
    WorkerOutcome,
    WorkerResult,
    run_worker,
)
from evidenceguard_worker.shutdown import StopController

pytestmark = pytest.mark.integration

WAIT = 15.0
WORKER = "worker-a"
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
INSERT_EFFECT = text(
    "INSERT INTO worker_test_effects (job_id) VALUES (:job_id) ON CONFLICT DO NOTHING"
)


@pytest.fixture
def engine(migrated: Engine, test_database_url: URL) -> Iterator[Engine]:
    """The migrated disposable database, with every statement bounded server-side, plus a
    test-only effect table."""
    bounded = create_engine(
        test_database_url,
        poolclass=NullPool,
        hide_parameters=True,
        connect_args={"options": "-c statement_timeout=20000"},
    )
    with bounded.begin() as connection:
        connection.execute(text("CREATE TABLE worker_test_effects (job_id uuid PRIMARY KEY)"))
    try:
        yield bounded
    finally:
        bounded.dispose()


@pytest.fixture
def factory(engine: Engine) -> sessionmaker[Session]:
    return create_session_factory(engine)


@pytest.fixture
def actor(engine: Engine) -> ActorContext:
    tenant_id = uuid4()
    with engine.begin() as connection:
        connection.execute(insert(Tenant).values(id=tenant_id, slug="tenant-a", name="Tenant A"))
    return ActorContext(tenant_id=tenant_id, actor_id=uuid4(), role=Role.REVIEWER)


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.events: list[str] = []
        self._formatter = JsonFormatter()

    def emit(self, record: logging.LogRecord) -> None:
        self.events.append(json.loads(self._formatter.format(record))["event"])


@pytest.fixture
def logs() -> Iterator[_ListHandler]:
    logger = logging.getLogger("evidenceguard.worker")
    handler = _ListHandler()
    previous = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    try:
        yield handler
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous)


class RecordingStore(DatabaseJobStore):
    """The real store, counting claims and confirmed heartbeats."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        super().__init__(session_factory)
        self.claimed: list[UUID | None] = []
        self.renewals = 0
        self.after_claim: Callable[[], None] | None = None

    def claim(self, worker_id: str, kinds: Collection[str]) -> JobSnapshot | None:
        job = super().claim(worker_id, kinds)
        self.claimed.append(None if job is None else job.id)
        if self.after_claim is not None:
            self.after_claim()
        return job

    def heartbeat(self, token: JobLeaseToken) -> JobSnapshot:
        renewed = super().heartbeat(token)
        self.renewals += 1
        return renewed


# --- helpers --------------------------------------------------------------------------------


def _enqueue(
    factory: sessionmaker[Session],
    actor: ActorContext,
    *,
    kind: str = "test_job",
    max_attempts: int = 3,
) -> JobSnapshot:
    with transaction(factory) as session:
        return job_store.enqueue(
            session, actor, kind=kind, idempotency_key=str(uuid4()), max_attempts=max_attempts
        )


def _row(engine: Engine, job_id: UUID) -> dict[str, Any]:
    with engine.connect() as connection:
        row = connection.execute(select(Job.__table__).where(Job.id == job_id)).one()
    return dict(row._mapping)


def _effects(engine: Engine) -> list[UUID]:
    with engine.connect() as connection:
        return list(connection.execute(text("SELECT job_id FROM worker_test_effects")).scalars())


def _wait_until(condition: Callable[[], bool], timeout: float = WAIT) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            pytest.fail("timed out waiting for the expected state")
        time.sleep(0.01)


class Run:
    """``run_worker`` on a background thread with a stop controller the test can use."""

    def __init__(
        self,
        store: DatabaseJobStore,
        handlers: dict[str, JobHandler],
        *,
        once: bool = False,
        timings: Timings = TIMINGS,
    ) -> None:
        self.stop = StopController()
        self.results: list[WorkerResult] = []
        registry = HandlerRegistry(handlers.items())
        self.thread = threading.Thread(
            target=lambda: self.results.append(
                run_worker(
                    store, registry, stop=self.stop, worker_id=WORKER, timings=timings, once=once
                )
            ),
            daemon=True,
        )
        self.thread.start()

    def result(self) -> WorkerResult:
        self.thread.join(WAIT)
        assert not self.thread.is_alive(), "the worker did not return in time"
        return self.results[0]


def _once(
    factory: sessionmaker[Session], handler: JobHandler, *, timings: Timings = TIMINGS
) -> WorkerResult:
    return Run(
        DatabaseJobStore(factory), {"test_job": handler}, once=True, timings=timings
    ).result()


def _finish_with_effect(ctx: JobContext) -> None:
    with ctx.fenced(finish=True) as fence:
        fence.session.execute(INSERT_EFFECT, {"job_id": ctx.job.id})


# --- processing and atomic finish -------------------------------------------------------------


def test_once_processes_a_job_to_succeeded_with_its_effect(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext
) -> None:
    job = _enqueue(factory, actor)

    assert _once(factory, _finish_with_effect).outcome is WorkerOutcome.STOPPED

    row = _row(engine, job.id)
    assert (row["status"], row["attempt"], row["locked_by"]) == ("succeeded", 1, None)
    assert _effects(engine) == [job.id]


def test_a_finish_block_that_raises_rolls_back_the_effect_and_the_completion(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext
) -> None:
    job = _enqueue(factory, actor)

    def handler(ctx: JobContext) -> None:
        with ctx.fenced(finish=True) as fence:
            fence.session.execute(INSERT_EFFECT, {"job_id": ctx.job.id})
            raise RetryableJobError()

    _once(factory, handler)

    row = _row(engine, job.id)
    assert (row["status"], row["last_error"], row["attempt"]) == (
        "queued",
        "retryable_failure",
        1,
    )
    assert _effects(engine) == []


def test_a_committed_finish_followed_by_an_exception_writes_nothing_more(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext, logs: _ListHandler
) -> None:
    job = _enqueue(factory, actor)

    def handler(ctx: JobContext) -> None:
        _finish_with_effect(ctx)
        raise RuntimeError("after the finish")

    _once(factory, handler)

    row = _row(engine, job.id)
    assert (row["status"], row["last_error"]) == ("succeeded", None)
    assert _effects(engine) == [job.id]
    assert "job.post_finish_error" in logs.events
    assert "job.retry_scheduled" not in logs.events


# --- heartbeats and lease loss ----------------------------------------------------------------


def test_heartbeats_extend_the_lease_across_several_intervals(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext
) -> None:
    job = _enqueue(factory, actor)
    store = RecordingStore(factory)
    leases: list[Any] = []

    def handler(ctx: JobContext) -> None:
        leases.append(_row(engine, ctx.job.id)["lease_expires_at"])
        _wait_until(lambda: store.renewals >= 3)
        leases.append(_row(engine, ctx.job.id)["lease_expires_at"])

    run = Run(store, {"test_job": handler}, once=True)

    assert run.result().outcome is WorkerOutcome.STOPPED
    assert leases[1] > leases[0]
    assert _row(engine, job.id)["status"] == "succeeded"


def test_lease_loss_before_a_fenced_write_writes_nothing_and_records_no_outcome(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext, logs: _ListHandler
) -> None:
    job = _enqueue(factory, actor)
    store = RecordingStore(factory)
    entered, go = threading.Event(), threading.Event()
    seen: list[BaseException] = []

    def handler(ctx: JobContext) -> None:
        entered.set()
        assert go.wait(WAIT)
        try:
            with ctx.fenced() as fence:
                fence.session.execute(INSERT_EFFECT, {"job_id": ctx.job.id})
        except BaseException as error:
            seen.append(error)
            raise

    run = Run(store, {"test_job": handler}, timings=replace(TIMINGS, heartbeat_interval=60.0))
    assert entered.wait(WAIT)
    with engine.begin() as connection:
        connection.execute(
            update(Job)
            .where(Job.id == job.id)
            .values(
                lease_expires_at=func.clock_timestamp()
                - literal_column("interval '1 second'", type_=Interval)
            )
        )
    reclaimed = job_store.claim(factory, "worker-b")
    assert reclaimed is not None and reclaimed.id == job.id
    go.set()
    _wait_until(lambda: len(store.claimed) >= 2)  # the stale worker went back to polling
    run.stop.request()

    assert run.result().outcome is WorkerOutcome.STOPPED
    assert [type(error) for error in seen] == [LeaseLostError]
    assert _effects(engine) == []
    row = _row(engine, job.id)
    assert (row["status"], row["locked_by"], row["attempt"]) == ("running", "worker-b", 2)
    assert store.claimed[0] == job.id and set(store.claimed[1:]) == {None}
    assert "job.lease_lost" in logs.events


def test_heartbeats_racing_atomic_completion_never_report_lease_loss(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext, logs: _ListHandler
) -> None:
    jobs = [_enqueue(factory, actor) for _ in range(3)]
    store = RecordingStore(factory)

    def handler(ctx: JobContext) -> None:
        time.sleep(0.05)  # let several heartbeats run first
        _finish_with_effect(ctx)

    run = Run(store, {"test_job": handler}, timings=replace(TIMINGS, heartbeat_interval=0.005))
    _wait_until(lambda: all(_row(engine, job.id)["status"] == "succeeded" for job in jobs))
    run.stop.request()

    assert run.result().outcome is WorkerOutcome.STOPPED
    assert sorted(_effects(engine)) == sorted(job.id for job in jobs)
    assert all(_row(engine, job.id)["attempt"] == 1 for job in jobs)
    assert "job.lease_lost" not in logs.events
    assert logs.events.count("job.succeeded") == 3


# --- shutdown -------------------------------------------------------------------------------


def test_a_cooperative_shutdown_requeues_the_job_with_worker_shutdown(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext
) -> None:
    job = _enqueue(factory, actor)
    started = threading.Event()

    def handler(ctx: JobContext) -> None:
        started.set()
        while True:
            ctx.check()
            time.sleep(0.01)

    run = Run(DatabaseJobStore(factory), {"test_job": handler}, timings=replace(TIMINGS, drain=0.1))
    assert started.wait(WAIT)
    run.stop.request()

    assert run.result().outcome is WorkerOutcome.STOPPED
    row = _row(engine, job.id)
    assert (row["status"], row["last_error"], row["attempt"]) == ("queued", "worker_shutdown", 1)


def test_a_job_claimed_after_a_stop_is_requeued_without_running_its_handler(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext
) -> None:
    job = _enqueue(factory, actor)
    store = RecordingStore(factory)
    started: list[UUID] = []
    stop = StopController()
    store.after_claim = stop.request  # the stop arrives while the claim is in flight

    result = run_worker(
        store,
        HandlerRegistry([("test_job", lambda ctx: started.append(ctx.job.id))]),
        stop=stop,
        worker_id=WORKER,
        timings=TIMINGS,
    )

    assert result.outcome is WorkerOutcome.STOPPED
    assert started == []
    row = _row(engine, job.id)
    assert (row["status"], row["last_error"], row["attempt"]) == ("queued", "worker_shutdown", 1)


# --- error mapping and kinds ----------------------------------------------------------------


def _raise(error: BaseException) -> JobHandler:
    def handler(ctx: JobContext) -> None:
        raise error

    return handler


@pytest.mark.parametrize(
    ("error", "max_attempts", "status", "code"),
    [
        (RetryableJobError(), 3, "queued", "retryable_failure"),
        (RetryableJobError(), 1, "dead", "retryable_failure"),
        (PermanentJobError(), 3, "failed", "permanent_failure"),
        (RuntimeError("unexpected"), 3, "queued", "unexpected_error"),
    ],
)
def test_handler_errors_record_their_fixed_codes(
    error: BaseException,
    max_attempts: int,
    status: str,
    code: str,
    engine: Engine,
    factory: sessionmaker[Session],
    actor: ActorContext,
) -> None:
    job = _enqueue(factory, actor, max_attempts=max_attempts)

    _once(factory, _raise(error))

    row = _row(engine, job.id)
    assert (row["status"], row["last_error"], row["attempt"]) == (status, code, 1)


def test_a_job_of_an_unregistered_kind_stays_queued(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext
) -> None:
    job = _enqueue(factory, actor, kind="other_job")

    assert _once(factory, _finish_with_effect).outcome is WorkerOutcome.STOPPED

    row = _row(engine, job.id)
    assert (row["status"], row["attempt"]) == ("queued", 0)


def test_an_empty_kind_filter_claims_nothing_but_still_sweeps(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext
) -> None:
    queued = _enqueue(factory, actor)
    exhausted_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            insert(Job).values(
                id=exhausted_id,
                tenant_id=actor.tenant_id,
                kind="test_job",
                idempotency_key=str(uuid4()),
                payload={},
                status="running",
                attempt=3,
                max_attempts=3,
                run_after=func.clock_timestamp(),
                locked_by="worker-gone",
                lease_expires_at=func.clock_timestamp()
                - literal_column("interval '1 second'", type_=Interval),
            )
        )

    assert job_store.claim(factory, WORKER, kinds=()) is None

    assert _row(engine, exhausted_id)["status"] == "dead"
    assert _row(engine, queued.id)["status"] == "queued"
