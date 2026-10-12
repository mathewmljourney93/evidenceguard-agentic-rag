"""The worker runtime without a database (M3b, ADR-0008).

A fake ``JobStore`` stands in for PostgreSQL. It records claims, heartbeats and outcomes, keeps
committed effects separate from rolled-back ones, and can block or fail any call on request.
Ordering is controlled with ``threading.Event``; every wait in these tests is bounded, and the
only timeouts that are allowed to expire are the runtime's own short test timings.

Real PostgreSQL behaviour is covered by ``test_worker_postgres.py``.
"""

import json
import logging
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.pool import QueuePool

from evidenceguard_domain import jobs as lifecycle
from evidenceguard_domain.jobs import (
    JobErrorCode,
    JobLeaseToken,
    JobPayload,
    JobSnapshot,
    JobStatus,
    LeaseLostError,
)
from evidenceguard_observability.jsonlog import (
    ALLOWED_FIELDS,
    REVIEWED_EVENTS,
    UNREVIEWED_EVENT,
    JsonFormatter,
)
from evidenceguard_persistence.db import dispose_engine
from evidenceguard_persistence.jobs import FenceClosedError, FencedSession, JobLockTimeoutError
from evidenceguard_worker import runtime
from evidenceguard_worker.context import (
    JobCancelledError,
    JobContext,
    PermanentJobError,
    RetryableJobError,
)
from evidenceguard_worker.registry import DuplicateHandlerError, HandlerRegistry, JobHandler
from evidenceguard_worker.runtime import (
    HandlerStillRunning,
    HeartbeatStillRunning,
    Timings,
    WorkerOutcome,
    WorkerResult,
    run_worker,
)
from evidenceguard_worker.shutdown import StopController

T0 = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)
TENANT = UUID("33333333-3333-4333-8333-333333333333")
WORKER = "worker-test"
WAIT = 10.0  # upper bound for any wait on the test side; never expected to elapse

FAST = Timings(
    idle_poll=0.01,
    backoff_initial=0.01,
    backoff_cap=0.08,
    heartbeat_interval=0.01,
    drain=5.0,
    cancel_grace=5.0,
    lease_loss_grace=0.3,
    heartbeat_join=0.3,
    stop_check=0.005,
)

# Obviously fake markers standing in for private values; never real data.
KEY_MARKER = "private-idempotency-key-marker"
MESSAGE_MARKER = "private exception text marker"


def make_job(*, kind: str = "test_job", attempt: int = 1, max_attempts: int = 3) -> JobSnapshot:
    return JobSnapshot(
        id=uuid4(),
        tenant_id=TENANT,
        kind=kind,
        idempotency_key=KEY_MARKER,
        payload=JobPayload.from_mapping({"revision_id": str(uuid4())}),
        status=JobStatus.RUNNING,
        attempt=attempt,
        max_attempts=max_attempts,
        run_after=T0,
        locked_by=WORKER,
        lease_expires_at=T0 + timedelta(seconds=60),
        created_at=T0,
        updated_at=T0,
    )


class CommitFailed(SQLAlchemyError):
    """Stands in for a failed COMMIT (or a lost acknowledgment)."""


# --- the fake store -----------------------------------------------------------------------


class _PendingSession:
    """The session behind a fake fence: ``add`` stages an effect until commit."""

    def __init__(self, pending: list[object]) -> None:
        self.pending = pending
        self.closed = False

    def add(self, instance: object) -> None:
        self.pending.append(instance)


class FakeFence:
    def __init__(self, store: "FakeStore", token: JobLeaseToken, job: JobSnapshot) -> None:
        self._store = store
        self._token = token
        self._job = job
        self._open = True
        self.pending: list[object] = []
        self.backing = _PendingSession(self.pending)
        self.succeeded = False
        self._session = FencedSession(cast(Any, self.backing), cast(Any, self))

    @property
    def session(self) -> FencedSession:
        return self._session

    @property
    def job(self) -> JobSnapshot:
        return self._job

    def succeed(self) -> JobSnapshot:
        self._require_open()
        if not self._store.owns(self._token):
            raise LeaseLostError()
        self.succeeded = True
        return self._job

    def _require_open(self) -> None:
        if not self._open:
            raise FenceClosedError()


ClaimResult = JobSnapshot | None | Exception | Callable[[], JobSnapshot]


class FakeStore:
    """A ``JobStore`` double. ``owns`` is the fake database fence: ownership belongs to one
    attempt, ``(job_id, attempt)``, so a reclaim of the same job is a new owner."""

    def __init__(self, claims: Sequence[ClaimResult] = ()) -> None:
        self._claims = list(claims)
        self.jobs: dict[UUID, JobSnapshot] = {}
        self.claim_kinds: list[frozenset[str]] = []
        self.claim_hook: Callable[[int], None] | None = None
        self.heartbeat_hook: Callable[[JobLeaseToken], None] | None = None
        self.heartbeat_calls = 0
        self.heartbeat_returned = 0
        self.heartbeat_refusals = 0
        self.outcomes: list[tuple[str, JobErrorCode | None]] = []
        self.outcome_error: Exception | None = None
        self.effects: list[object] = []
        self.ended: set[tuple[UUID, int]] = set()  # attempts that no longer own their job
        self.commit_mode = "ok"  # or "raise_after_commit", "raise_without_commit"
        self.after_commit: Callable[[], None] | None = None
        self.on_open: Callable[[], None] | None = None  # runs while a fence acquires its lock
        self.tokens: list[JobLeaseToken] = []
        self.fences: list[FakeFence] = []
        self.events: list[str] = []

    def owns(self, token: JobLeaseToken) -> bool:
        current = self.jobs.get(token.job_id)
        return (
            (token.job_id, token.attempt) not in self.ended
            and current is not None
            and current.status is JobStatus.RUNNING
            and current.attempt == token.attempt
        )

    def lose(self, job: JobSnapshot) -> None:
        self.ended.add((job.id, job.attempt))

    def claim(self, worker_id: str, kinds: Any) -> JobSnapshot | None:
        assert worker_id == WORKER
        self.claim_kinds.append(frozenset(kinds))
        self.events.append("claim")
        if self.claim_hook is not None:
            self.claim_hook(len(self.claim_kinds))
        result = self._claims.pop(0) if self._claims else None
        if isinstance(result, Exception):
            raise result
        if callable(result):
            result = result()
        if result is not None:
            self.jobs[result.id] = result
            self.tokens.append(result.lease_token())
        return result

    def heartbeat(self, token: JobLeaseToken) -> JobSnapshot:
        self.heartbeat_calls += 1
        if self.heartbeat_hook is not None:
            self.heartbeat_hook(token)
        self.heartbeat_returned += 1
        if not self.owns(token):
            self.heartbeat_refusals += 1
            raise LeaseLostError()
        return self.jobs[token.job_id]

    def _write(
        self,
        name: str,
        token: JobLeaseToken,
        code: JobErrorCode | None,
        rule: Callable[[JobSnapshot], JobSnapshot],
    ) -> JobSnapshot:
        self.events.append(name)
        if self.outcome_error is not None:
            raise self.outcome_error
        if not self.owns(token):
            raise LeaseLostError()
        written = rule(self.jobs[token.job_id])
        self.outcomes.append((name, code))
        self.ended.add((token.job_id, token.attempt))
        self.jobs[token.job_id] = written
        return written

    def complete(self, token: JobLeaseToken) -> JobSnapshot:
        return self._write(
            "complete", token, None, lambda job: lifecycle.succeed(job, token, now=T0)
        )

    def fail_retryable(self, token: JobLeaseToken, code: JobErrorCode) -> JobSnapshot:
        return self._write(
            "fail_retryable",
            token,
            code,
            lambda job: lifecycle.fail_retryably(job, token, now=T0, code=code),
        )

    def fail_permanent(self, token: JobLeaseToken, code: JobErrorCode) -> JobSnapshot:
        return self._write(
            "fail_permanent",
            token,
            code,
            lambda job: lifecycle.fail_permanently(job, token, now=T0, code=code),
        )

    @contextmanager
    def fenced(self, token: JobLeaseToken) -> Iterator[FakeFence]:
        if not self.owns(token):
            raise LeaseLostError()
        if self.on_open is not None:
            self.on_open()  # the lock wait: the supervisor may latch something meanwhile
        fence = FakeFence(self, token, self.jobs[token.job_id])
        self.fences.append(fence)
        try:
            yield fence
        finally:
            fence._open = False
        # The block finished: commit.
        if self.commit_mode == "raise_without_commit":
            raise CommitFailed("commit failed")
        self.effects.extend(fence.pending)
        if fence.succeeded:
            self.ended.add((token.job_id, token.attempt))
            self.jobs[token.job_id] = lifecycle.succeed(self.jobs[token.job_id], token, now=T0)
            self.outcomes.append(("finish", None))
        if self.after_commit is not None:
            self.after_commit()
        if self.commit_mode == "raise_after_commit":
            raise CommitFailed("commit acknowledgment lost")


# --- helpers --------------------------------------------------------------------------------


class WorkerRun:
    """``run_worker`` in a background thread (the main thread stays free for the test)."""

    def __init__(
        self,
        store: FakeStore,
        handlers: dict[str, JobHandler],
        *,
        stop: StopController | None = None,
        timings: Timings = FAST,
        once: bool = False,
    ) -> None:
        self.stop = stop if stop is not None else StopController()
        self.results: list[WorkerResult] = []
        self.errors: list[BaseException] = []
        registry = HandlerRegistry(handlers.items())

        def target() -> None:
            try:
                self.results.append(
                    run_worker(
                        store,
                        registry,
                        stop=self.stop,
                        worker_id=WORKER,
                        timings=timings,
                        once=once,
                    )
                )
            except BaseException as error:  # handed to the test by ``result()``
                self.errors.append(error)

        self.thread = threading.Thread(target=target, daemon=True)
        self.thread.start()

    def result(self, timeout: float = WAIT) -> WorkerResult:
        self.thread.join(timeout)
        assert not self.thread.is_alive(), "the worker did not return in time"
        if self.errors:
            raise self.errors[0]
        return self.results[0]


def wait_until(condition: Callable[[], bool], timeout: float = WAIT) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "condition not reached in time"
        time.sleep(0.002)


def run_once(store: FakeStore, handler: JobHandler, **kwargs: Any) -> WorkerResult:
    return WorkerRun(store, {"test_job": handler}, once=True, **kwargs).result()


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def logs() -> Iterator[_ListHandler]:
    """Capture worker records directly, independent of propagation settings."""
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


def rendered(logs: _ListHandler) -> list[dict[str, Any]]:
    formatter = JsonFormatter()
    return [json.loads(formatter.format(record)) for record in logs.records]


def events(logs: _ListHandler) -> list[str]:
    return [entry["event"] for entry in rendered(logs)]


def returns() -> JobHandler:
    return lambda ctx: None


def waits_for(event: threading.Event) -> JobHandler:
    def handler(ctx: JobContext) -> None:
        assert event.wait(WAIT)

    return handler


def checks_until_stopped(seen: list[BaseException]) -> JobHandler:
    """A cooperative handler: calls ``check()`` until it raises, and re-raises."""

    def handler(ctx: JobContext) -> None:
        try:
            while True:
                ctx.check()
                time.sleep(0.002)
        except BaseException as error:
            seen.append(error)
            raise

    return handler


# --- registry -------------------------------------------------------------------------------


def test_registry_is_validated_and_immutable() -> None:
    def handler(ctx: JobContext) -> None:
        return None

    registry = HandlerRegistry([("test_job", handler)])

    assert registry.kinds == frozenset({"test_job"})
    assert registry["test_job"] is handler
    assert dict(registry) == {"test_job": handler}
    assert not hasattr(registry, "__setitem__")
    with pytest.raises(ValueError):
        HandlerRegistry([("Not A Kind", handler)])
    with pytest.raises(DuplicateHandlerError):
        HandlerRegistry([("test_job", handler), ("test_job", handler)])
    with pytest.raises(TypeError):
        HandlerRegistry([("test_job", cast(Any, "not callable"))])


def test_handler_errors_accept_only_fixed_codes() -> None:
    assert RetryableJobError().code is JobErrorCode.RETRYABLE_FAILURE
    assert PermanentJobError().code is JobErrorCode.PERMANENT_FAILURE
    with pytest.raises(TypeError):
        RetryableJobError(cast(Any, "free text"))
    with pytest.raises(TypeError):
        PermanentJobError(cast(Any, "free text"))


def test_timings_must_be_positive() -> None:
    with pytest.raises(ValueError):
        Timings(drain=0)
    assert Timings().idle_poll == 2.0
    assert (Timings().backoff_initial, Timings().backoff_cap) == (1.0, 30.0)
    assert (Timings().drain, Timings().cancel_grace) == (30.0, 5.0)
    assert (Timings().lease_loss_grace, Timings().heartbeat_join) == (5.0, 10.0)
    assert (Timings().heartbeat_interval, Timings().lease) == (20.0, 60.0)


# --- polling --------------------------------------------------------------------------------


def test_backoff_doubles_to_the_cap_resets_after_a_claim_and_idle_waits_two_seconds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = OperationalError("SELECT", {}, Exception("db down"))
    store = FakeStore([failure] * 7 + [None, JobLockTimeoutError()])
    stop = StopController()
    waits: list[float] = []

    def record(self: Any, seconds: float) -> None:
        waits.append(seconds)
        if len(waits) == 9:
            stop.request()

    monkeypatch.setattr(runtime._Worker, "_sleep", record)

    result = run_worker(
        store, HandlerRegistry([("test_job", returns())]), stop=stop, worker_id=WORKER
    )

    assert result.outcome is WorkerOutcome.STOPPED
    assert waits == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0, 2.0, 1.0]


def test_claims_pass_exactly_the_registered_kinds() -> None:
    store = FakeStore()

    run_once(store, returns())

    assert store.claim_kinds == [frozenset({"test_job"})]


def test_a_stop_ends_an_idle_wait_promptly() -> None:
    store = FakeStore()
    run = WorkerRun(store, {"test_job": returns()}, timings=replace(FAST, idle_poll=60.0))
    wait_until(lambda: len(store.claim_kinds) == 1)

    run.stop.request()

    assert run.result().outcome is WorkerOutcome.STOPPED
    assert len(store.claim_kinds) == 1


def test_once_with_nothing_claimable_exits_without_waiting() -> None:
    store = FakeStore()
    started = time.monotonic()

    result = run_once(store, returns(), timings=replace(FAST, idle_poll=60.0))

    assert (result.outcome, result.exit_code) == (WorkerOutcome.STOPPED, 0)
    assert len(store.claim_kinds) == 1
    assert time.monotonic() - started < WAIT


def test_once_with_a_claim_database_error_exits_one_without_retrying(
    logs: _ListHandler,
) -> None:
    store = FakeStore([OperationalError("SELECT", {}, Exception("db down")), make_job()])

    result = run_once(store, returns(), timings=replace(FAST, backoff_initial=60.0))

    assert (result.outcome, result.exit_code) == (WorkerOutcome.CLAIM_FAILED, 1)
    assert len(store.claim_kinds) == 1
    (failure,) = [e for e in rendered(logs) if e["event"] == "worker.poll_failed"]
    assert failure["error_type"] == "OperationalError"


def test_once_processes_at_most_one_job() -> None:
    store = FakeStore([make_job(), make_job()])

    assert run_once(store, returns()).outcome is WorkerOutcome.STOPPED
    assert len(store.claim_kinds) == 1
    assert store.outcomes == [("complete", None)]


# --- a stop while a claim is in flight ------------------------------------------------------


def _blocking_claim(store: FakeStore) -> tuple[threading.Event, threading.Event]:
    entered, release = threading.Event(), threading.Event()

    def hook(call: int) -> None:
        if call == 1:
            entered.set()
            assert release.wait(WAIT)

    store.claim_hook = hook
    return entered, release


def test_a_job_claimed_after_a_stop_starts_no_handler_and_gets_a_shutdown_retry(
    logs: _ListHandler,
) -> None:
    job = make_job()
    store = FakeStore([job, make_job()])
    entered, release = _blocking_claim(store)
    started: list[UUID] = []
    run = WorkerRun(store, {"test_job": lambda ctx: started.append(ctx.job.id)})
    assert entered.wait(WAIT)

    run.stop.request()
    time.sleep(0.05)
    assert run.thread.is_alive()  # the claim call is synchronous; the stop does not cancel it
    release.set()

    assert run.result().outcome is WorkerOutcome.STOPPED
    assert started == []
    assert store.outcomes == [("fail_retryable", JobErrorCode.WORKER_SHUTDOWN)]
    assert len(store.claim_kinds) == 1
    assert "job.cancelled" in events(logs)


def test_a_claim_returning_nothing_after_a_stop_ends_without_waiting() -> None:
    store = FakeStore()
    entered, release = _blocking_claim(store)
    run = WorkerRun(store, {"test_job": returns()}, timings=replace(FAST, idle_poll=60.0))
    assert entered.wait(WAIT)

    run.stop.request()
    release.set()

    assert run.result().outcome is WorkerOutcome.STOPPED
    assert store.outcomes == [] and len(store.claim_kinds) == 1


def test_a_blocked_outcome_call_delays_shutdown_until_it_returns() -> None:
    store = FakeStore([make_job()])
    entered, release = threading.Event(), threading.Event()
    original = store.complete

    def blocking_complete(token: JobLeaseToken) -> JobSnapshot:
        entered.set()
        assert release.wait(WAIT)
        return original(token)

    store.complete = blocking_complete  # type: ignore[method-assign]
    run = WorkerRun(store, {"test_job": returns()})
    assert entered.wait(WAIT)

    run.stop.request()
    run.stop.request()  # even an immediate stop cannot interrupt the synchronous call
    time.sleep(0.05)
    assert run.thread.is_alive()
    release.set()

    assert run.result().outcome is WorkerOutcome.STOPPED
    assert store.outcomes == [("complete", None)]


# --- outcomes -------------------------------------------------------------------------------


def _raises(error: BaseException) -> JobHandler:
    def handler(ctx: JobContext) -> None:
        raise error

    return handler


@pytest.mark.parametrize(
    ("handler", "job", "expected", "event"),
    [
        (returns(), make_job(), [("complete", None)], "job.succeeded"),
        (
            _raises(RetryableJobError()),
            make_job(),
            [("fail_retryable", JobErrorCode.RETRYABLE_FAILURE)],
            "job.retry_scheduled",
        ),
        (
            _raises(RetryableJobError()),
            make_job(attempt=3, max_attempts=3),
            [("fail_retryable", JobErrorCode.RETRYABLE_FAILURE)],
            "job.dead",
        ),
        (
            _raises(PermanentJobError()),
            make_job(),
            [("fail_permanent", JobErrorCode.PERMANENT_FAILURE)],
            "job.failed",
        ),
        (
            _raises(RuntimeError(MESSAGE_MARKER)),
            make_job(),
            [("fail_retryable", JobErrorCode.UNEXPECTED_ERROR)],
            "job.retry_scheduled",
        ),
        (
            # Not requested by the runtime, so it is not a shutdown.
            _raises(JobCancelledError()),
            make_job(),
            [("fail_retryable", JobErrorCode.UNEXPECTED_ERROR)],
            "job.retry_scheduled",
        ),
        (_raises(LeaseLostError()), make_job(), [], "job.lease_lost"),
        (
            returns(),
            make_job(kind="unregistered_kind"),
            [("fail_permanent", JobErrorCode.UNKNOWN_JOB_KIND)],
            "job.failed",
        ),
    ],
)
def test_each_handler_result_records_exactly_one_fenced_outcome(
    handler: JobHandler,
    job: JobSnapshot,
    expected: list[tuple[str, JobErrorCode | None]],
    event: str,
    logs: _ListHandler,
) -> None:
    store = FakeStore([job])

    assert run_once(store, handler).outcome is WorkerOutcome.STOPPED
    assert store.outcomes == expected
    assert event in events(logs)


def test_an_outcome_refused_by_the_fence_is_logged_as_lease_lost(logs: _ListHandler) -> None:
    job = make_job()
    store = FakeStore([job])

    def lose_then_return(ctx: JobContext) -> None:
        store.lose(job)

    run_once(store, lose_then_return, timings=replace(FAST, heartbeat_interval=60.0))

    assert store.outcomes == []
    assert "job.lease_lost" in events(logs)


def test_a_failed_outcome_write_is_logged_and_the_worker_continues(logs: _ListHandler) -> None:
    store = FakeStore([make_job()])
    store.outcome_error = OperationalError("UPDATE", {}, Exception("db down"))

    assert run_once(store, returns()).outcome is WorkerOutcome.STOPPED
    (entry,) = [e for e in rendered(logs) if e["event"] == "job.outcome_failed"]
    assert entry["error_type"] == "OperationalError"


# --- heartbeats and lease loss ----------------------------------------------------------------


def test_a_heartbeat_stuck_beyond_the_join_deadline_records_nothing_and_claims_nothing(
    logs: _ListHandler,
) -> None:
    store = FakeStore([make_job(), make_job()])
    in_heartbeat, release = threading.Event(), threading.Event()

    def stuck(token: JobLeaseToken) -> None:
        in_heartbeat.set()
        release.wait(WAIT)

    store.heartbeat_hook = stuck
    try:
        run = WorkerRun(store, {"test_job": waits_for(in_heartbeat)})
        result = run.result()

        assert result.outcome is WorkerOutcome.ABNORMAL
        assert result.abnormal_reason is HeartbeatStillRunning
        assert result.exit_code == 5
        assert store.outcomes == []
        assert len(store.claim_kinds) == 1
        (entry,) = [e for e in rendered(logs) if e["event"] == "worker.abnormal_stop"]
        assert entry["error_type"] == "HeartbeatStillRunning"
    finally:
        release.set()


def test_cooperative_lease_loss_records_no_outcome_and_claims_only_after_threads_stop(
    logs: _ListHandler,
) -> None:
    job = make_job()
    store = FakeStore([job, None])
    seen: list[BaseException] = []
    store.lose(job)  # the first heartbeat is refused
    order: list[str] = []
    store.claim_hook = lambda call: order.append(f"claim-{call}")

    def handler(ctx: JobContext) -> None:
        try:
            checks_until_stopped(seen)(ctx)
        finally:
            order.append("handler-exited")

    run = WorkerRun(store, {"test_job": handler})
    wait_until(lambda: len(store.claim_kinds) >= 2)
    run.stop.request()

    assert run.result().outcome is WorkerOutcome.STOPPED
    assert [type(error) for error in seen] == [LeaseLostError]
    assert store.outcomes == []
    assert order[:3] == ["claim-1", "handler-exited", "claim-2"]
    assert "job.lease_lost" in events(logs)


def test_an_uncooperative_handler_after_lease_loss_is_abnormal_and_claims_nothing() -> None:
    job = make_job()
    store = FakeStore([job, make_job()])
    store.lose(job)
    release = threading.Event()
    try:
        result = WorkerRun(store, {"test_job": waits_for(release)}).result()

        assert (result.outcome, result.abnormal_reason) == (
            WorkerOutcome.ABNORMAL,
            HandlerStillRunning,
        )
        assert store.outcomes == []
        assert len(store.claim_kinds) == 1
    finally:
        release.set()


def test_presumed_loss_at_the_local_deadline_without_any_renewal() -> None:
    store = FakeStore([make_job()])
    seen: list[BaseException] = []

    run_once(
        store,
        checks_until_stopped(seen),
        timings=replace(FAST, lease=0.1, heartbeat_interval=60.0),
    )

    assert [type(error) for error in seen] == [LeaseLostError]
    assert store.outcomes == []
    assert store.heartbeat_calls == 0


def test_confirmed_renewals_keep_a_short_local_lease_alive() -> None:
    store = FakeStore([make_job()])
    renewals = threading.Event()

    def handler(ctx: JobContext) -> None:
        started = time.monotonic()
        wait_until(lambda: time.monotonic() - started > 0.6 and store.heartbeat_calls >= 5)
        renewals.set()
        ctx.check()  # still held: every confirmed renewal moved the local deadline

    run_once(store, handler, timings=replace(FAST, lease=0.2, heartbeat_interval=0.005))

    assert renewals.is_set()
    assert store.outcomes == [("complete", None)]


def test_a_late_successful_heartbeat_does_not_revive_a_cancelled_attempt() -> None:
    store = FakeStore([make_job()])
    in_flight, release_heartbeat = threading.Event(), threading.Event()
    contexts: list[JobContext] = []
    deadlines: list[float] = []
    seen: list[BaseException] = []

    def slow_heartbeat(token: JobLeaseToken) -> None:
        in_flight.set()
        assert release_heartbeat.wait(WAIT)

    store.heartbeat_hook = slow_heartbeat

    def handler(ctx: JobContext) -> None:
        contexts.append(ctx)
        wait_until(lambda: ctx.lease_lost)  # presumed loss while the heartbeat is in flight
        deadlines.append(ctx._state.deadline)
        release_heartbeat.set()  # the in-flight heartbeat now succeeds
        wait_until(lambda: store.heartbeat_returned >= 1)
        try:
            with ctx.fenced():
                pass
        except BaseException as error:
            seen.append(error)
            raise

    run = WorkerRun(
        store,
        {"test_job": handler},
        once=True,
        timings=replace(
            FAST,
            lease=0.2,
            heartbeat_interval=0.01,
            heartbeat_join=WAIT,
            lease_loss_grace=WAIT,
        ),
    )
    assert in_flight.wait(WAIT)

    assert run.result().outcome is WorkerOutcome.STOPPED
    (ctx,) = contexts
    # The heartbeat thread was joined, so its successful renewal has been processed.
    assert ctx.lease_lost and ctx.cancel_requested
    assert ctx._state.deadline == deadlines[0]
    assert [type(error) for error in seen] == [LeaseLostError]
    assert store.outcomes == []


# --- atomic finish ------------------------------------------------------------------------------


def test_a_committed_finish_followed_by_an_exception_records_nothing_more(
    logs: _ListHandler,
) -> None:
    store = FakeStore([make_job()])
    after: list[BaseException] = []

    def handler(ctx: JobContext) -> None:
        with ctx.fenced(finish=True) as fence:
            fence.session.add("effect")
        assert ctx.finished
        for attempt in (ctx.check, lambda: ctx.fenced().__enter__()):
            try:
                attempt()
            except FenceClosedError as error:
                after.append(error)
        raise RuntimeError(MESSAGE_MARKER)

    run_once(store, handler)

    assert store.outcomes == [("finish", None)]
    assert store.effects == ["effect"]
    assert len(after) == 2
    (entry,) = [e for e in rendered(logs) if e["event"] == "job.post_finish_error"]
    assert entry["error_type"] == "RuntimeError"


def test_a_finish_block_that_raises_rolls_back_and_maps_the_error() -> None:
    store = FakeStore([make_job()])
    finished: list[bool] = []

    def handler(ctx: JobContext) -> None:
        try:
            with ctx.fenced(finish=True) as fence:
                fence.session.add("effect")
                raise RetryableJobError()
        finally:
            finished.append(ctx.finished)

    run_once(store, handler)

    assert finished == [False]
    assert store.effects == []
    assert store.outcomes == [("fail_retryable", JobErrorCode.RETRYABLE_FAILURE)]


def test_a_commit_that_succeeded_but_lost_its_acknowledgment_is_never_reported_as_success(
    logs: _ListHandler,
) -> None:
    store = FakeStore([make_job()])
    store.commit_mode = "raise_after_commit"
    states: list[str] = []

    def handler(ctx: JobContext) -> None:
        try:
            with ctx.fenced(finish=True) as fence:
                fence.session.add("effect")
        finally:
            states.append(ctx._state.finish.value)

    run_once(store, handler, timings=replace(FAST, heartbeat_interval=60.0))

    assert states == ["uncertain"]
    # The fence refused the runtime's retry: exactly one committed outcome exists.
    assert store.outcomes == [("finish", None)]
    assert store.effects == ["effect"]
    logged = events(logs)
    assert "job.outcome_unknown" in logged and "job.succeeded" not in logged


def test_a_commit_that_did_not_succeed_is_retried_through_the_fence_and_stays_idempotent(
    logs: _ListHandler,
) -> None:
    first = make_job(attempt=1)
    store = FakeStore()

    def reclaim() -> JobSnapshot:
        # The fenced retry re-queued the job; after its backoff it is claimed again: the same
        # job ID, tenant, kind and payload, with the next attempt as the new owner.
        requeued = store.jobs[first.id]
        assert requeued.status is JobStatus.QUEUED
        return lifecycle.claim(requeued, worker_id=WORKER, now=T0 + timedelta(seconds=10))

    store._claims = [first, reclaim]
    states: list[str] = []

    def handler(ctx: JobContext) -> None:
        effect = f"effect-{ctx.job.id}"  # keyed by job ID, so applying it is idempotent
        try:
            with ctx.fenced(finish=True) as fence:
                if effect not in store.effects:
                    fence.session.add(effect)
        finally:
            states.append(ctx._state.finish.value)
            store.commit_mode = "ok"

    store.commit_mode = "raise_without_commit"
    run_once(store, handler, timings=replace(FAST, heartbeat_interval=60.0))
    run_once(store, handler, timings=replace(FAST, heartbeat_interval=60.0))

    first_token, second_token = store.tokens
    assert first_token.job_id == second_token.job_id == first.id
    assert (first_token.attempt, second_token.attempt) == (1, 2)
    second = store.jobs[first.id]
    assert (second.tenant_id, second.kind, second.payload) == (
        first.tenant_id,
        first.kind,
        first.payload,
    )
    assert states == ["uncertain", "committed"]
    assert store.outcomes == [("fail_retryable", JobErrorCode.UNEXPECTED_ERROR), ("finish", None)]
    assert second.status is JobStatus.SUCCEEDED and second.attempt == 2
    assert store.effects == [f"effect-{first.id}"]  # exactly one durable effect
    assert "job.outcome_unknown" not in events(logs)


def test_a_heartbeat_refused_by_a_committed_finish_is_not_lease_loss(logs: _ListHandler) -> None:
    store = FakeStore([make_job()])

    def handler(ctx: JobContext) -> None:
        with ctx.fenced(finish=True):
            pass
        wait_until(lambda: store.heartbeat_refusals >= 1)

    run_once(store, handler)

    assert store.outcomes == [("finish", None)]
    logged = events(logs)
    assert "job.lease_lost" not in logged and "job.succeeded" in logged


def test_a_refusal_between_database_commit_and_local_publication_stays_pending(
    logs: _ListHandler,
) -> None:
    store = FakeStore([make_job()])
    committed_in_db, release = threading.Event(), threading.Event()
    contexts: list[JobContext] = []

    def pause_after_commit() -> None:
        committed_in_db.set()
        assert release.wait(WAIT)

    store.after_commit = pause_after_commit

    def handler(ctx: JobContext) -> None:
        contexts.append(ctx)
        with ctx.fenced(finish=True) as fence:
            fence.session.add("effect")

    run = WorkerRun(store, {"test_job": handler}, once=True)
    assert committed_in_db.wait(WAIT)
    wait_until(lambda: store.heartbeat_refusals >= 1)  # refused: the job is already terminal

    (ctx,) = contexts
    # Reading the state does not block: no lock is held across the paused database work.
    assert ctx._state.pending_refusal
    assert not ctx.lease_lost and not ctx.cancel_requested
    assert run.thread.is_alive()
    assert "job.lease_lost" not in events(logs)
    release.set()

    assert run.result().outcome is WorkerOutcome.STOPPED
    assert not ctx._state.pending_refusal and not ctx.lease_lost
    assert store.outcomes == [("finish", None)]
    assert "job.lease_lost" not in events(logs)


# --- shutdown -----------------------------------------------------------------------------------


def test_a_stop_before_any_claim_claims_nothing() -> None:
    store = FakeStore([make_job()])
    stop = StopController()
    stop.request()

    run = WorkerRun(store, {"test_job": returns()}, stop=stop)

    assert run.result().outcome is WorkerOutcome.STOPPED
    assert store.claim_kinds == []


def test_a_drain_lets_the_running_job_finish_normally(logs: _ListHandler) -> None:
    store = FakeStore([make_job(), make_job()])
    started, go = threading.Event(), threading.Event()

    def handler(ctx: JobContext) -> None:
        started.set()
        assert go.wait(WAIT)

    run = WorkerRun(store, {"test_job": handler})
    assert started.wait(WAIT)
    run.stop.request()
    time.sleep(0.05)
    go.set()

    assert run.result().outcome is WorkerOutcome.STOPPED
    assert store.outcomes == [("complete", None)]
    assert len(store.claim_kinds) == 1
    assert "worker.stopping" in events(logs)


def test_a_heartbeat_outage_during_the_drain_takes_the_lease_loss_path(
    logs: _ListHandler,
) -> None:
    store = FakeStore([make_job()])
    seen: list[BaseException] = []
    started = threading.Event()

    def outage(token: JobLeaseToken) -> None:
        raise OperationalError("SELECT", {}, Exception("db down"))

    store.heartbeat_hook = outage

    def handler(ctx: JobContext) -> None:
        started.set()
        checks_until_stopped(seen)(ctx)

    run = WorkerRun(store, {"test_job": handler}, timings=replace(FAST, lease=0.3))
    assert started.wait(WAIT)
    run.stop.request()

    assert run.result().outcome is WorkerOutcome.STOPPED
    assert [type(error) for error in seen] == [LeaseLostError]
    assert store.outcomes == []
    logged = events(logs)
    assert "job.heartbeat_failed" in logged and "job.lease_lost" in logged


def test_cancellation_at_the_drain_deadline_records_a_shutdown_retry(logs: _ListHandler) -> None:
    store = FakeStore([make_job()])
    seen: list[BaseException] = []
    started = threading.Event()

    def handler(ctx: JobContext) -> None:
        started.set()
        checks_until_stopped(seen)(ctx)

    run = WorkerRun(store, {"test_job": handler}, timings=replace(FAST, drain=0.05))
    assert started.wait(WAIT)
    run.stop.request()

    assert run.result().outcome is WorkerOutcome.STOPPED
    assert [type(error) for error in seen] == [JobCancelledError]
    assert store.outcomes == [("fail_retryable", JobErrorCode.WORKER_SHUTDOWN)]
    assert "job.cancelled" in events(logs)


def test_a_handler_ignoring_cancellation_ends_abnormally() -> None:
    store = FakeStore([make_job()])
    started, release = threading.Event(), threading.Event()

    def handler(ctx: JobContext) -> None:
        started.set()
        release.wait(WAIT)

    try:
        run = WorkerRun(
            store, {"test_job": handler}, timings=replace(FAST, drain=0.05, cancel_grace=0.05)
        )
        assert started.wait(WAIT)
        run.stop.request()

        result = run.result()
        assert (result.outcome, result.abnormal_reason) == (
            WorkerOutcome.ABNORMAL,
            HandlerStillRunning,
        )
        assert store.outcomes == []
    finally:
        release.set()


def test_a_second_stop_request_ends_abnormally_while_a_job_runs() -> None:
    store = FakeStore([make_job()])
    started, release = threading.Event(), threading.Event()

    def handler(ctx: JobContext) -> None:
        started.set()
        release.wait(WAIT)

    try:
        run = WorkerRun(store, {"test_job": handler})
        assert started.wait(WAIT)
        run.stop.request()
        run.stop.request()

        result = run.result()
        assert (result.outcome, result.abnormal_reason) == (
            WorkerOutcome.ABNORMAL,
            HandlerStillRunning,
        )
        assert store.outcomes == []
    finally:
        release.set()


def test_a_normal_stop_leaves_no_job_threads_running() -> None:
    store = FakeStore([make_job()])

    run_once(store, returns())

    names = {thread.name for thread in threading.enumerate()}
    assert not names & {"eg-worker-handler", "eg-worker-heartbeat"}


def test_abnormal_shutdown_neither_closes_nor_waits_for_checked_out_sessions() -> None:
    store = FakeStore([make_job()])
    inside, release = threading.Event(), threading.Event()

    def handler(ctx: JobContext) -> None:
        with ctx.fenced():
            inside.set()
            release.wait(WAIT)

    try:
        run = WorkerRun(store, {"test_job": handler})
        assert inside.wait(WAIT)
        run.stop.request()
        run.stop.request()

        assert run.result().outcome is WorkerOutcome.ABNORMAL
        (fence,) = store.fences
        assert fence._open and not fence.backing.closed  # still checked out by the live thread
    finally:
        release.set()


def test_engine_disposal_is_pool_cleanup_and_leaves_checked_out_connections_open(
    tmp_path: Path,
) -> None:
    # A file database uses a QueuePool, like the PostgreSQL engine (in-memory SQLite does not).
    engine = create_engine(f"sqlite:///{tmp_path / 'pool.db'}")
    assert isinstance(engine.pool, QueuePool)
    connection = engine.connect()
    try:
        dispose_engine(engine)

        assert not connection.closed
        assert connection.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        connection.close()


# --- logging ------------------------------------------------------------------------------------


def test_worker_logs_use_only_reviewed_events_and_validated_fields(logs: _ListHandler) -> None:
    job = make_job()
    store = FakeStore([job])

    run_once(store, _raises(RuntimeError(MESSAGE_MARKER)))

    entries = rendered(logs)
    assert entries
    text_ = json.dumps(entries)
    for private in (
        KEY_MARKER,
        MESSAGE_MARKER,
        str(TENANT),
        *(value for _, value in job.payload.entries),
    ):
        assert private not in text_
    base = {"timestamp", "level", "logger", "event"}
    for entry in entries:
        assert entry["event"] != UNREVIEWED_EVENT
        assert entry["event"] in REVIEWED_EVENTS.values()
        assert set(entry) <= base | ALLOWED_FIELDS
        assert entry["worker_id"] == WORKER
        if "job_id" in entry:
            assert entry["job_id"] == str(job.id)
            assert (entry["job_kind"], entry["attempt"]) == ("test_job", 1)
        if "error_code" in entry:
            assert entry["error_code"] in {code.value for code in JobErrorCode}
    assert {"worker.started", "job.claimed", "job.retry_scheduled", "worker.stopped"} <= {
        entry["event"] for entry in entries
    }


def test_worker_fields_and_events_are_reviewed() -> None:
    assert {"worker_id", "job_id", "job_kind", "attempt", "error_code"} <= ALLOWED_FIELDS
    for event in (
        "worker.started",
        "worker.stopping",
        "worker.stopped",
        "worker.abnormal_stop",
        "worker.poll_failed",
        "worker.no_handlers",
        "worker.config_invalid",
        "job.claimed",
        "job.succeeded",
        "job.post_finish_error",
        "job.retry_scheduled",
        "job.dead",
        "job.failed",
        "job.cancelled",
        "job.lease_lost",
        "job.heartbeat_failed",
        "job.outcome_failed",
        "job.outcome_unknown",
    ):
        assert REVIEWED_EVENTS[event] == event


# --- sessions and threads -------------------------------------------------------------------

_DIALECT = postgresql.dialect()  # type: ignore[no-untyped-call]


class _Row:
    def __init__(self, data: dict[str, Any]) -> None:
        self._mapping = data


class _Result:
    def __init__(self, rows: list[dict[str, Any]] | None = None, scalar: Any = None) -> None:
        self._rows = rows or []
        self._scalar = scalar

    def first(self) -> _Row | None:
        return _Row(self._rows[0]) if self._rows else None

    def scalar_one(self) -> Any:
        return self._scalar

    def __iter__(self) -> Iterator[_Row]:
        return iter(_Row(row) for row in self._rows)


class _ScriptedDatabase:
    """Answers the M3a statements for one job row and records which threads use each session."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.sessions: list[_RecordingSession] = []
        self.row: dict[str, Any] = {
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

    def factory(self) -> "_RecordingSession":
        session = _RecordingSession(self)
        with self.lock:
            self.sessions.append(session)
        return session

    def respond(self, sql: str, params: dict[str, Any]) -> _Result:
        if "jobs.attempt >= jobs.max_attempts" in sql:
            return _Result()
        if "jobs.attempt < jobs.max_attempts" in sql:
            return _Result([dict(self.row)] if self.row["status"] == "queued" else [])
        if sql.startswith("SELECT clock_timestamp()"):
            return _Result(scalar=T0)
        if "AS db_now" in sql:
            return _Result([{**self.row, "db_now": T0}])
        if sql.startswith("SELECT jobs.id FROM jobs"):
            return _Result([{"id": self.row["id"]}])
        if sql.startswith("UPDATE jobs"):
            self.row.update({key: params[key] for key in params if key in self.row})
        return _Result()


class _RecordingSession:
    def __init__(self, database: _ScriptedDatabase) -> None:
        self._database = database
        self.threads: set[int] = set()

    def _use(self) -> None:
        self.threads.add(threading.get_ident())

    def execute(self, statement: Any, params: Any = None) -> _Result:
        self._use()
        compiled = statement.compile(dialect=_DIALECT)
        with self._database.lock:
            return self._database.respond(" ".join(str(compiled).split()), dict(compiled.params))

    def scalar(self, statement: Any, params: Any = None) -> Any:
        return self.execute(statement, params).scalar_one()

    def commit(self) -> None:
        self._use()

    def rollback(self) -> None:
        self._use()

    def close(self) -> None:
        self._use()


def test_no_session_is_ever_used_from_two_threads() -> None:
    database = _ScriptedDatabase()
    store = runtime.DatabaseJobStore(cast(Any, database.factory))
    handler_threads: list[int] = []

    def handler(ctx: JobContext) -> None:
        handler_threads.append(threading.get_ident())
        with ctx.fenced() as fence:
            fence.session.execute(text("SELECT 1"))
        wait_until(lambda: len(database.sessions) >= 6)  # claim, fence and heartbeats

    result = run_worker(
        store,
        HandlerRegistry([("test_job", handler)]),
        worker_id=WORKER,
        timings=replace(FAST, heartbeat_interval=0.005),
        once=True,
    )

    assert result.outcome is WorkerOutcome.STOPPED
    assert database.row["status"] == "succeeded"
    assert all(len(session.threads) == 1 for session in database.sessions)
    used_by = {thread for session in database.sessions for thread in session.threads}
    assert len(used_by) == 3  # supervisor, handler and heartbeat threads
    assert handler_threads[0] in used_by


# --- cancellation at fence boundaries (Prompt 61) ----------------------------------------------


def _latch_while_opening(store: FakeStore, latch: Callable[[JobContext], None]) -> list[JobContext]:
    """Latch something on the attempt while its fence acquires the lock, after the first check."""
    contexts: list[JobContext] = []
    store.on_open = lambda: latch(contexts[0])
    return contexts


def test_cancellation_while_an_ordinary_fence_opens_skips_the_block_and_rolls_back() -> None:
    store = FakeStore([make_job()])
    contexts = _latch_while_opening(store, lambda ctx: ctx._state.request_cancel())
    body: list[str] = []
    seen: list[BaseException] = []

    def handler(ctx: JobContext) -> None:
        contexts.append(ctx)
        try:
            with ctx.fenced() as fence:
                body.append("ran")
                fence.session.add("effect")
        except BaseException as error:
            seen.append(error)
            raise

    run_once(store, handler, timings=replace(FAST, heartbeat_interval=60.0))

    assert body == [] and store.effects == []
    assert [type(error) for error in seen] == [JobCancelledError]
    (fence,) = store.fences
    assert not fence._open  # the transaction ended without a commit
    assert store.outcomes == [("fail_retryable", JobErrorCode.WORKER_SHUTDOWN)]


def test_lease_loss_while_an_ordinary_fence_opens_skips_the_block(logs: _ListHandler) -> None:
    store = FakeStore([make_job()])
    contexts = _latch_while_opening(store, lambda ctx: ctx._state.latch_lease_loss())
    body: list[str] = []
    seen: list[BaseException] = []

    def handler(ctx: JobContext) -> None:
        contexts.append(ctx)
        try:
            with ctx.fenced() as fence:
                body.append("ran")
                fence.session.add("effect")
        except BaseException as error:
            seen.append(error)
            raise

    run_once(store, handler, timings=replace(FAST, heartbeat_interval=60.0))

    assert body == [] and store.effects == []
    assert [type(error) for error in seen] == [LeaseLostError]
    assert store.outcomes == []
    assert "job.lease_lost" in events(logs)


def test_cancellation_while_a_finish_fence_opens_writes_no_effect_or_completion() -> None:
    store = FakeStore([make_job()])
    contexts = _latch_while_opening(store, lambda ctx: ctx._state.request_cancel())
    body: list[str] = []
    finish_states: list[str] = []

    def handler(ctx: JobContext) -> None:
        contexts.append(ctx)
        try:
            with ctx.fenced(finish=True) as fence:
                body.append("ran")
                fence.session.add("effect")
        finally:
            finish_states.append(ctx._state.finish.value)

    run_once(store, handler, timings=replace(FAST, heartbeat_interval=60.0))

    assert body == [] and store.effects == []
    assert finish_states == ["none"]
    assert ("finish", None) not in store.outcomes
    assert store.outcomes == [("fail_retryable", JobErrorCode.WORKER_SHUTDOWN)]


def test_cancellation_inside_a_finish_block_rolls_back_before_success_is_recorded() -> None:
    store = FakeStore([make_job()])
    finish_states: list[str] = []
    seen: list[BaseException] = []

    def handler(ctx: JobContext) -> None:
        try:
            with ctx.fenced(finish=True) as fence:
                fence.session.add("effect")
                ctx._state.request_cancel()  # latched after the effects, before success
        except BaseException as error:
            seen.append(error)
            raise
        finally:
            finish_states.append(ctx._state.finish.value)

    run_once(store, handler, timings=replace(FAST, heartbeat_interval=60.0))

    assert [type(error) for error in seen] == [JobCancelledError]
    (fence,) = store.fences
    assert not fence.succeeded
    assert store.effects == []
    assert finish_states == ["none"]
    assert store.outcomes == [("fail_retryable", JobErrorCode.WORKER_SHUTDOWN)]


# --- exception-safe job-thread lifecycle (Prompt 61) ------------------------------------------


def _job_threads(threads: list[threading.Thread]) -> list[threading.Thread]:
    return [thread for thread in threads if thread.name.startswith("eg-worker-")]


def test_a_handler_thread_that_fails_to_start_stops_the_started_heartbeat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = FakeStore([make_job(), make_job()])
    started: list[threading.Thread] = []
    original_start = threading.Thread.start

    def start(self: threading.Thread) -> None:
        if self.name == "eg-worker-handler":
            raise RuntimeError("can't start new thread")
        original_start(self)
        started.append(self)

    monkeypatch.setattr(threading.Thread, "start", start)

    with pytest.raises(RuntimeError):
        run_worker(
            store, HandlerRegistry([("test_job", returns())]), worker_id=WORKER, timings=FAST
        )

    (heartbeat,) = _job_threads(started)
    assert heartbeat.name == "eg-worker-heartbeat"
    assert not heartbeat.is_alive()  # stopped and joined
    assert store.outcomes == []
    assert len(store.claim_kinds) == 1  # no further claim


class FailingStop(StopController):
    """Makes the supervisor's next stop check raise, standing in for an unexpected bug."""

    def __init__(self) -> None:
        super().__init__()
        self.fail = threading.Event()

    @property
    def immediate(self) -> bool:
        if self.fail.is_set():
            raise RuntimeError("unexpected supervisor failure")
        return super().immediate


def test_a_supervisor_failure_cancels_a_cooperative_handler_and_reraises() -> None:
    store = FakeStore([make_job(), make_job()])
    stop = FailingStop()
    started = threading.Event()
    seen: list[BaseException] = []

    def handler(ctx: JobContext) -> None:
        started.set()
        checks_until_stopped(seen)(ctx)

    run = WorkerRun(store, {"test_job": handler}, stop=stop)
    assert started.wait(WAIT)
    stop.fail.set()

    with pytest.raises(RuntimeError):
        run.result()
    assert [type(error) for error in seen] == [JobCancelledError]
    assert store.outcomes == []
    assert len(store.claim_kinds) == 1
    assert not _job_threads(threading.enumerate())


def test_a_supervisor_failure_with_a_handler_still_alive_is_abnormal(logs: _ListHandler) -> None:
    store = FakeStore([make_job(), make_job()])
    stop = FailingStop()
    started, release = threading.Event(), threading.Event()

    def handler(ctx: JobContext) -> None:
        started.set()
        release.wait(WAIT)  # ignores cancellation

    try:
        run = WorkerRun(
            store, {"test_job": handler}, stop=stop, timings=replace(FAST, cancel_grace=0.2)
        )
        assert started.wait(WAIT)
        stop.fail.set()

        result = run.result()
        assert (result.outcome, result.abnormal_reason) == (
            WorkerOutcome.ABNORMAL,
            HandlerStillRunning,
        )
        assert store.outcomes == []
        assert len(store.claim_kinds) == 1
        assert "worker.abnormal_stop" in events(logs)
    finally:
        release.set()
