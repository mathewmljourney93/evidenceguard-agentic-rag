"""The sequential worker runtime (M3b, ADR-0008).

``run_worker`` polls for jobs, runs **at most one handler at a time** and records outcomes only
through M3a's fence. The main thread supervises; each job gets a daemon handler thread and a
daemon heartbeat thread. No SQLAlchemy ``Session`` is shared between threads: every M3a
operation opens and closes its own session.

Ordering rules (see ``docs/plan.md`` and ADR-0008):

- The local lease deadline starts at the monotonic time captured **before** the claim, plus the
  lease. Only a confirmed heartbeat moves it, from that heartbeat's pre-call time. PostgreSQL
  decides actual validity through the fence.
- A stop requested while a claim is in flight is checked after the claim returns: an acquired job
  starts **no handler** and gets only the fenced ``worker_shutdown`` retry.
- After a job's handler exits, the heartbeat thread is stopped and joined for a bounded time,
  and the runtime checks that it **actually** stopped before recording any outcome.
- On lease loss, cancellation is requested, renewal stops and the handler gets a bounded grace.
  No stale outcome is recorded.
- If a handler or heartbeat thread is still alive after its bounded wait, the runtime takes the
  **abnormal** path: it records nothing more, never claims again and returns an abnormal
  result. The threads may keep running while the process lives; the CLI ends the process.
- An unexpected startup or supervisor failure records no outcome. Cancellation is latched,
  future heartbeats stop, and only the threads that actually started are joined for a bounded
  time. A thread still alive makes the result abnormal; otherwise the failure is re-raised, so
  no further claim is made.

Limits: ``claim`` and outcome recording are synchronous calls on the main thread. If one
blocks, the timed checks are not reached until it returns, and signals do not cancel it. There
is no total shutdown deadline. Waits here are bounded supervisor waits; the connect, pool and
lock timeouts do not bound every database operation.
"""

import logging
import threading
import time
from collections.abc import Callable, Collection
from contextlib import AbstractContextManager
from dataclasses import dataclass, fields
from enum import StrEnum
from functools import partial
from typing import Any, Protocol

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from evidenceguard_domain.jobs import (
    HEARTBEAT_INTERVAL_SECONDS,
    LEASE_SECONDS,
    JobErrorCode,
    JobLeaseToken,
    JobSnapshot,
    JobStatus,
    LeaseLostError,
    validate_worker_id,
)
from evidenceguard_observability.jsonlog import log_event
from evidenceguard_persistence import jobs as job_store
from evidenceguard_persistence.jobs import JobLockTimeoutError, new_worker_id
from evidenceguard_worker.context import (
    AttemptState,
    FenceHandle,
    FinishState,
    JobCancelledError,
    JobContext,
    PermanentJobError,
    RetryableJobError,
)
from evidenceguard_worker.heartbeat import run_heartbeats
from evidenceguard_worker.registry import HandlerRegistry, JobHandler
from evidenceguard_worker.shutdown import StopController

LOGGER = logging.getLogger("evidenceguard.worker")

# Accepted initial engineering defaults (Prompt 59), not measured guarantees.
IDLE_POLL_SECONDS = 2.0
POLL_BACKOFF_INITIAL_SECONDS = 1.0
POLL_BACKOFF_CAP_SECONDS = 30.0
DRAIN_SECONDS = 30.0
CANCEL_GRACE_SECONDS = 5.0
LEASE_LOSS_GRACE_SECONDS = 5.0
HEARTBEAT_JOIN_SECONDS = 10.0
# Implementation detail: the longest the main thread waits before re-checking stop flags, which
# signal handlers set without waking anything.
STOP_CHECK_SECONDS = 0.1


@dataclass(frozen=True)
class Timings:
    """Runtime waits in seconds. Only tests change them; they are not CLI or environment
    settings. ``lease`` is the local view of M3a's 60-second lease, used for local deadlines
    only; the database lease is always M3a's."""

    idle_poll: float = IDLE_POLL_SECONDS
    backoff_initial: float = POLL_BACKOFF_INITIAL_SECONDS
    backoff_cap: float = POLL_BACKOFF_CAP_SECONDS
    heartbeat_interval: float = float(HEARTBEAT_INTERVAL_SECONDS)
    lease: float = float(LEASE_SECONDS)
    drain: float = DRAIN_SECONDS
    cancel_grace: float = CANCEL_GRACE_SECONDS
    lease_loss_grace: float = LEASE_LOSS_GRACE_SECONDS
    heartbeat_join: float = HEARTBEAT_JOIN_SECONDS
    stop_check: float = STOP_CHECK_SECONDS

    def __post_init__(self) -> None:
        for item in fields(self):
            value = getattr(self, item.name)
            if not isinstance(value, int | float) or not value > 0:
                raise ValueError("every worker timing must be a positive number of seconds")


# --- the job store --------------------------------------------------------------------------


class JobStore(Protocol):
    """The M3a operations the runtime uses. Each call owns its own session and transaction."""

    def claim(self, worker_id: str, kinds: Collection[str]) -> JobSnapshot | None: ...

    def heartbeat(self, token: JobLeaseToken) -> JobSnapshot: ...

    def complete(self, token: JobLeaseToken) -> JobSnapshot: ...

    def fail_retryable(self, token: JobLeaseToken, code: JobErrorCode) -> JobSnapshot: ...

    def fail_permanent(self, token: JobLeaseToken, code: JobErrorCode) -> JobSnapshot: ...

    def fenced(self, token: JobLeaseToken) -> AbstractContextManager[FenceHandle]: ...


class DatabaseJobStore:
    """``JobStore`` backed by ``evidenceguard_persistence.jobs``."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._factory = session_factory

    def claim(self, worker_id: str, kinds: Collection[str]) -> JobSnapshot | None:
        return job_store.claim(self._factory, worker_id, kinds=kinds)

    def heartbeat(self, token: JobLeaseToken) -> JobSnapshot:
        return job_store.heartbeat(self._factory, token)

    def complete(self, token: JobLeaseToken) -> JobSnapshot:
        return job_store.complete(self._factory, token)

    def fail_retryable(self, token: JobLeaseToken, code: JobErrorCode) -> JobSnapshot:
        return job_store.fail_retryable(self._factory, token, code)

    def fail_permanent(self, token: JobLeaseToken, code: JobErrorCode) -> JobSnapshot:
        return job_store.fail_permanent(self._factory, token, code)

    def fenced(self, token: JobLeaseToken) -> AbstractContextManager[FenceHandle]:
        return job_store.fenced_transaction(self._factory, token)


# --- results --------------------------------------------------------------------------------


class AbnormalStop(Exception):
    """Base of the fixed reasons for an abnormal stop. Never raised; logged by class name."""


class HandlerStillRunning(AbnormalStop):
    """A handler thread was still alive after its bounded wait (or at an immediate stop)."""


class HeartbeatStillRunning(AbnormalStop):
    """A heartbeat thread was still alive after its bounded join."""


class WorkerOutcome(StrEnum):
    STOPPED = "stopped"
    CLAIM_FAILED = "claim_failed"
    ABNORMAL = "abnormal"


_EXIT_CODES = {WorkerOutcome.STOPPED: 0, WorkerOutcome.CLAIM_FAILED: 1, WorkerOutcome.ABNORMAL: 5}


@dataclass(frozen=True)
class WorkerResult:
    """How ``run_worker`` ended. After ``ABNORMAL``, threads of the last job may still be
    running in this process, so the caller must not reuse the runtime (the CLI exits)."""

    outcome: WorkerOutcome
    abnormal_reason: type[AbnormalStop] | None = None

    @property
    def exit_code(self) -> int:
        return _EXIT_CODES[self.outcome]


class _HandlerOutcome:
    """Written once by the handler thread before it exits; read only after it has exited."""

    def __init__(self) -> None:
        self.error: BaseException | None = None


# --- the runtime ----------------------------------------------------------------------------


def run_worker(
    store: JobStore,
    registry: HandlerRegistry,
    *,
    stop: StopController | None = None,
    worker_id: str | None = None,
    timings: Timings | None = None,
    clock: Callable[[], float] = time.monotonic,
    once: bool = False,
) -> WorkerResult:
    """Run the worker until a stop is requested (or, with ``once``, after one claim attempt).

    With ``once``: no claimable job returns ``STOPPED`` at once, and a database error from the
    claim returns ``CLAIM_FAILED`` without retrying.
    """
    worker = _Worker(
        store,
        registry,
        stop=stop if stop is not None else StopController(),
        worker_id=validate_worker_id(worker_id) if worker_id is not None else new_worker_id(),
        timings=timings if timings is not None else Timings(),
        clock=clock,
        once=once,
    )
    return worker.run()


class _Worker:
    def __init__(
        self,
        store: JobStore,
        registry: HandlerRegistry,
        *,
        stop: StopController,
        worker_id: str,
        timings: Timings,
        clock: Callable[[], float],
        once: bool,
    ) -> None:
        self._store = store
        self._registry = registry
        self._stop = stop
        self._worker_id = worker_id
        self._timings = timings
        self._clock = clock
        self._once = once
        self._wake = threading.Event()
        self._stopping_logged = False
        stop.add_waker(self._wake.set)

    # Polling ------------------------------------------------------------------------------

    def run(self) -> WorkerResult:
        self._log("worker.started")
        outcome = WorkerOutcome.STOPPED
        backoff: float | None = None
        while not self._stop.requested:
            claim_started = self._clock()
            try:
                job = self._store.claim(self._worker_id, self._registry.kinds)
            except (SQLAlchemyError, JobLockTimeoutError) as error:
                self._log("worker.poll_failed", logging.WARNING, error_type=_class_name(error))
                if self._once:
                    outcome = WorkerOutcome.CLAIM_FAILED
                    break
                backoff = (
                    self._timings.backoff_initial
                    if backoff is None
                    else min(backoff * 2, self._timings.backoff_cap)
                )
                self._sleep(backoff)
                continue
            backoff = None

            if job is None:
                if self._once:
                    break
                self._sleep(self._timings.idle_poll)
                continue

            if self._stop.requested:
                # Post-claim stop check: a stop arrived while the claim was in flight.
                self._log("job.cancelled", job=job, error_code=JobErrorCode.WORKER_SHUTDOWN)
                self._write_outcome(
                    job,
                    partial(self._store.fail_retryable, code=JobErrorCode.WORKER_SHUTDOWN),
                    state=None,
                )
                break

            reason = self._run_job(job, claim_started)
            if reason is not None:
                self._log(
                    "worker.abnormal_stop", logging.ERROR, job=job, error_type=reason.__name__
                )
                return WorkerResult(WorkerOutcome.ABNORMAL, reason)
            if self._once:
                break

        if self._stop.requested:
            self._log_stopping()
        self._log("worker.stopped")
        return WorkerResult(outcome)

    def _sleep(self, seconds: float) -> None:
        """Wait up to ``seconds``, ending early once a stop is requested."""
        deadline = self._clock() + seconds
        while not self._stop.requested:
            remaining = deadline - self._clock()
            if remaining <= 0:
                return
            self._wake.wait(min(remaining, self._timings.stop_check))
            self._wake.clear()

    # One job ------------------------------------------------------------------------------

    def _run_job(self, job: JobSnapshot, claim_started: float) -> type[AbnormalStop] | None:
        """Supervise one attempt. Returns an abnormal reason, or ``None`` when every thread of
        the attempt has been confirmed stopped (so another claim is allowed)."""
        self._log("job.claimed", job=job)
        handler = self._registry.get(job.kind)
        if handler is None:
            # Defensive: the kind filter should prevent this.
            self._write_outcome(
                job,
                partial(self._store.fail_permanent, code=JobErrorCode.UNKNOWN_JOB_KIND),
                state=None,
            )
            return None

        state = AttemptState(
            deadline=claim_started + self._timings.lease,
            lease_seconds=self._timings.lease,
            clock=self._clock,
            on_change=self._wake.set,
        )
        context = JobContext(job, state, self._store.fenced)
        result = _HandlerOutcome()
        heartbeat_stop = threading.Event()
        heartbeat = threading.Thread(
            target=run_heartbeats,
            kwargs={
                "renew": self._store.heartbeat,
                "token": context.token,
                "state": state,
                "stop": heartbeat_stop,
                "interval": self._timings.heartbeat_interval,
                "clock": self._clock,
                "on_failure": lambda error: self._log(
                    "job.heartbeat_failed", logging.WARNING, job=job, error_type=_class_name(error)
                ),
            },
            name="eg-worker-heartbeat",
            daemon=True,
        )
        handler_thread = threading.Thread(
            target=self._call_handler,
            args=(handler, context, result),
            name="eg-worker-handler",
            daemon=True,
        )
        started: list[threading.Thread] = []
        try:
            for thread in (heartbeat, handler_thread):
                thread.start()
                started.append(thread)
            return self._supervise(job, state, result, handler_thread, heartbeat, heartbeat_stop)
        except BaseException:
            # An unexpected startup or supervisor failure: no outcome is recorded. Stop the
            # threads that actually started; if one is still alive, the attempt is abnormal.
            reason = self._clean_up_after_failure(state, heartbeat, heartbeat_stop, started)
            if reason is not None:
                return reason
            raise

    def _supervise(
        self,
        job: JobSnapshot,
        state: AttemptState,
        result: _HandlerOutcome,
        handler_thread: threading.Thread,
        heartbeat: threading.Thread,
        heartbeat_stop: threading.Event,
    ) -> type[AbnormalStop] | None:
        drain_deadline: float | None = None
        cancel_deadline: float | None = None
        while handler_thread.is_alive():
            if state.refresh():
                return self._after_lease_loss(
                    job, state, result, handler_thread, heartbeat, heartbeat_stop
                )
            if self._stop.immediate:
                return self._abandon(state, heartbeat_stop, HandlerStillRunning)
            if self._stop.requested:
                now = self._clock()
                if drain_deadline is None:
                    self._log_stopping(job)
                    drain_deadline = now + self._timings.drain
                elif cancel_deadline is None and now >= drain_deadline:
                    state.request_cancel()
                    cancel_deadline = now + self._timings.cancel_grace
                elif cancel_deadline is not None and now >= cancel_deadline:
                    return self._abandon(state, heartbeat_stop, HandlerStillRunning)
            self._wake.wait(self._timings.stop_check)
            self._wake.clear()

        # The handler exited. Stop renewing and confirm that the heartbeat really stopped.
        heartbeat_stop.set()
        heartbeat.join(self._timings.heartbeat_join)
        if heartbeat.is_alive():
            state.request_cancel()
            return HeartbeatStillRunning
        self._record_outcome(job, state, result)
        return None

    def _after_lease_loss(
        self,
        job: JobSnapshot,
        state: AttemptState,
        result: _HandlerOutcome,
        handler_thread: threading.Thread,
        heartbeat: threading.Thread,
        heartbeat_stop: threading.Event,
    ) -> type[AbnormalStop] | None:
        state.request_cancel()
        heartbeat_stop.set()
        heartbeat.join(self._timings.heartbeat_join)
        handler_thread.join(self._timings.lease_loss_grace)
        if heartbeat.is_alive():
            return HeartbeatStillRunning
        if handler_thread.is_alive():
            return HandlerStillRunning
        self._record_outcome(job, state, result)
        return None

    def _clean_up_after_failure(
        self,
        state: AttemptState,
        heartbeat: threading.Thread,
        heartbeat_stop: threading.Event,
        started: list[threading.Thread],
    ) -> type[AbnormalStop] | None:
        """Latch cancellation, stop future heartbeats and join only the threads that started,
        each for a bounded time. Returns the abnormal reason if one is still alive."""
        state.request_cancel()
        heartbeat_stop.set()
        for thread in started:
            thread.join(
                self._timings.heartbeat_join if thread is heartbeat else self._timings.cancel_grace
            )
        if any(thread is heartbeat and thread.is_alive() for thread in started):
            return HeartbeatStillRunning
        if any(thread.is_alive() for thread in started):
            return HandlerStillRunning
        return None

    def _abandon(
        self, state: AttemptState, heartbeat_stop: threading.Event, reason: type[AbnormalStop]
    ) -> type[AbnormalStop]:
        state.request_cancel()
        heartbeat_stop.set()
        return reason

    def _call_handler(
        self, handler: JobHandler, context: JobContext, result: _HandlerOutcome
    ) -> None:
        try:
            handler(context)
        except BaseException as error:  # recorded and mapped to an outcome by the supervisor
            result.error = error
        finally:
            self._wake.set()

    # Outcomes -----------------------------------------------------------------------------

    def _record_outcome(
        self, job: JobSnapshot, state: AttemptState, result: _HandlerOutcome
    ) -> None:
        """Called only after both threads of the attempt have been confirmed stopped."""
        error = result.error
        if state.finish is FinishState.COMMITTED:
            if error is None:
                self._log("job.succeeded", job=job)
            else:
                self._log(
                    "job.post_finish_error", logging.WARNING, job=job, error_type=_class_name(error)
                )
            return
        if isinstance(error, LeaseLostError):
            state.latch_lease_loss()  # the database fence refused the handler
        if state.lease_lost:
            self._log_ownership_lost(job, state)
            return

        write: Callable[[JobLeaseToken], JobSnapshot]
        error_type: str | None = None
        if error is None:
            write = self._store.complete
        elif isinstance(error, RetryableJobError):
            write = partial(self._store.fail_retryable, code=error.code)
        elif isinstance(error, PermanentJobError):
            write = partial(self._store.fail_permanent, code=error.code)
        elif isinstance(error, JobCancelledError) and state.cancel_requested:
            self._log("job.cancelled", job=job, error_code=JobErrorCode.WORKER_SHUTDOWN)
            write = partial(self._store.fail_retryable, code=JobErrorCode.WORKER_SHUTDOWN)
        else:
            error_type = _class_name(error)
            write = partial(self._store.fail_retryable, code=JobErrorCode.UNEXPECTED_ERROR)
        self._write_outcome(job, write, state=state, error_type=error_type)

    def _write_outcome(
        self,
        job: JobSnapshot,
        write: Callable[[JobLeaseToken], JobSnapshot],
        *,
        state: AttemptState | None,
        error_type: str | None = None,
    ) -> None:
        try:
            written = write(job.lease_token())
        except LeaseLostError:
            self._log_ownership_lost(job, state)
            return
        except Exception as failure:
            self._log(
                "job.outcome_failed", logging.WARNING, job=job, error_type=_class_name(failure)
            )
            return
        event = {
            JobStatus.SUCCEEDED: "job.succeeded",
            JobStatus.QUEUED: "job.retry_scheduled",
            JobStatus.DEAD: "job.dead",
            JobStatus.FAILED: "job.failed",
        }.get(written.status, "job.outcome_failed")
        code = None if written.status is JobStatus.SUCCEEDED else written.last_error
        self._log(event, job=job, error_code=code, error_type=error_type)

    def _log_stopping(self, job: JobSnapshot | None = None) -> None:
        if not self._stopping_logged:
            self._stopping_logged = True
            self._log("worker.stopping", job=job)

    def _log_ownership_lost(self, job: JobSnapshot, state: AttemptState | None) -> None:
        if state is not None and state.outcome_unknown:
            self._log("job.outcome_unknown", logging.WARNING, job=job)
        else:
            self._log("job.lease_lost", logging.WARNING, job=job)

    # Logging --------------------------------------------------------------------------------

    def _log(
        self,
        event: str,
        level: int = logging.INFO,
        *,
        job: JobSnapshot | None = None,
        error_code: JobErrorCode | None = None,
        error_type: str | None = None,
    ) -> None:
        """Every field comes from a validated value: the worker ID pattern, a ``JobSnapshot``
        (UUID, kind pattern, integer attempt), ``JobErrorCode`` or a class name."""
        fields_: dict[str, Any] = {"worker_id": self._worker_id}
        if job is not None:
            fields_.update(job_id=str(job.id), job_kind=job.kind, attempt=job.attempt)
        if error_code is not None:
            fields_["error_code"] = error_code.value
        if error_type is not None:
            fields_["error_type"] = error_type
        log_event(LOGGER, event, level, **fields_)


def _class_name(error: BaseException) -> str:
    return type(error).__name__
