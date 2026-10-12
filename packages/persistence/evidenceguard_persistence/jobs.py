"""The durable PostgreSQL job core (M3a, ADR-0007).

Lifecycle rules live in ``evidenceguard_domain.jobs``; this module applies them to locked rows,
always with a fresh PostgreSQL ``clock_timestamp()``, never worker time, ``now()`` or
``CURRENT_TIMESTAMP``. Functions return immutable ``JobSnapshot`` values, never session-bound
ORM objects.

Transaction ownership:

- ``enqueue`` runs inside the **caller's** transaction and never commits, so a job commits
  together with the work that created it.
- ``claim`` owns one short transaction. It is a trusted, system-level operation across tenants.
- ``fenced_transaction`` owns one transaction for an ownership-checked unit of work.
  ``heartbeat``, ``complete``, ``fail_retryable`` and ``fail_permanent`` are each one such
  transaction.

The fence, in order, within a single transaction:

1. ``SET LOCAL lock_timeout`` to 5 seconds, so a lock wait fails rather than hangs.
2. Lock the job row by ID (``SELECT … FOR UPDATE``), waiting if necessary.
3. In a **separate statement**, read the row and a fresh ``clock_timestamp()`` and require a
   running job, the matching ``(job_id, worker_id, attempt)`` token and an unexpired lease. No
   value read before the lock wait is reused. Otherwise ``LeaseLostError``, with no effect.
4. Run the caller's effects through ``Fence.session`` and any lifecycle transition through the
   ``Fence`` methods, each of which re-checks ownership with fresh time first.
5. Commit when the block finishes; roll back on any uncaught error, including a failed commit;
   always close the session. The fence closes after its block, and after a transition that ends
   or re-queues the attempt.

The guarantee: while a transaction holds the row lock after a valid check, no claimant can
reclaim the job, because claims use ``SKIP LOCKED``. The check and the effects are therefore
atomic with respect to reclaim. A transaction that passed its check just before the lease
expired may still **commit shortly after** expiry. Keep fenced transactions short and never make
provider or network calls while the lock is held.

The guarantee assumes the caller preserves the fence's transaction and lock. Handlers are
trusted application code. ``FencedSession`` omits ``commit``, ``rollback`` and ``close`` to
discourage ending the transaction by accident, but it is **not a sandbox**: ``execute`` accepts
arbitrary SQL, and Python exposes the underlying objects. Handlers must not issue
transaction-control SQL (``COMMIT``, ``ROLLBACK``, ``SAVEPOINT`` handling or similar), must not
reach into the underlying session, transaction or connection, and must not modify the job's
ownership fields directly.
"""

from collections.abc import Callable, Collection, Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import Select, Table, and_, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Result, ScalarResult
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.sql import Executable

from evidenceguard_domain import jobs as lifecycle
from evidenceguard_domain.context import ActorContext
from evidenceguard_domain.jobs import (
    DEFAULT_MAX_ATTEMPTS,
    LOCK_TIMEOUT_SECONDS,
    SWEEP_LIMIT,
    JobErrorCode,
    JobIdempotencyConflictError,
    JobLeaseToken,
    JobPayload,
    JobRequest,
    JobSnapshot,
    JobStatus,
    LeaseLostError,
)
from evidenceguard_persistence.db import transaction
from evidenceguard_persistence.models import Job

JOBS = cast(Table, Job.__table__)
IDEMPOTENCY_CONSTRAINT = "uq_jobs_tenant_id_kind_idempotency_key"
LOCK_TIMEOUT_SQL = f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT_SECONDS}s'"
LOCK_NOT_AVAILABLE = "55P03"  # PostgreSQL SQLSTATE for lock_timeout


class JobLockTimeoutError(Exception):
    """The job row stayed locked longer than the lock timeout. Nothing was changed."""

    def __init__(self) -> None:
        super().__init__("the job row could not be locked in time")


class JobEnqueueRaceError(Exception):
    """The conflicting job is not visible to this transaction (for example under REPEATABLE
    READ). Nothing was changed; the caller may retry in a new transaction."""

    def __init__(self) -> None:
        super().__init__("the existing job for this idempotency key is not visible")


class FenceClosedError(Exception):
    """The fence no longer permits work: its block ended or the job left this attempt."""

    def __init__(self) -> None:
        super().__init__("the job fence is closed")


def new_worker_id() -> str:
    """A unique worker ID per process start. Not a secret, and it names no host or user."""
    return f"worker-{uuid4()}"


# --- statements (built here so tests can inspect their SQL) --------------------------------


def fresh_time_statement() -> Select[Any]:
    return select(func.clock_timestamp())


def sweep_statement() -> Select[Any]:
    """Expired leases with no attempts left, at most ``SWEEP_LIMIT``, skipping locked rows."""
    return (
        select(JOBS)
        .where(
            JOBS.c.status == JobStatus.RUNNING.value,
            JOBS.c.lease_expires_at <= func.clock_timestamp(),
            JOBS.c.attempt >= JOBS.c.max_attempts,
        )
        .order_by(JOBS.c.lease_expires_at, JOBS.c.id)
        .limit(SWEEP_LIMIT)
        .with_for_update(skip_locked=True)
    )


def claim_statement(kinds: Collection[str] | None = None) -> Select[Any]:
    """The oldest claimable job by ``(run_after, id)``. Exhausted rows are never candidates.

    With ``kinds``, only jobs of those (already validated, non-empty) kinds are candidates.
    """
    due = and_(
        JOBS.c.status == JobStatus.QUEUED.value,
        JOBS.c.run_after <= func.clock_timestamp(),
    )
    abandoned = and_(
        JOBS.c.status == JobStatus.RUNNING.value,
        JOBS.c.lease_expires_at <= func.clock_timestamp(),
    )
    statement = select(JOBS).where(JOBS.c.attempt < JOBS.c.max_attempts, or_(due, abandoned))
    if kinds is not None:
        statement = statement.where(JOBS.c.kind.in_(sorted(kinds)))
    return (
        statement.order_by(JOBS.c.run_after, JOBS.c.id).limit(1).with_for_update(skip_locked=True)
    )


def lock_statement(token: JobLeaseToken) -> Select[Any]:
    """Step 2 of the fence: wait for and take the row lock. Checks nothing."""
    return select(JOBS.c.id).where(JOBS.c.id == token.job_id).with_for_update()


def current_state_statement(token: JobLeaseToken) -> Select[Any]:
    """Step 3 of the fence: the row and a fresh database time, read after the lock is held."""
    return select(JOBS, func.clock_timestamp().label("db_now")).where(JOBS.c.id == token.job_id)


# --- row conversion ------------------------------------------------------------------------


def _snapshot(row: Mapping[Any, Any]) -> JobSnapshot:
    data = {str(key): value for key, value in row.items()}
    data["payload"] = JobPayload.from_mapping(data["payload"])
    return JobSnapshot.model_validate(data)


def _write(session: Session, job: JobSnapshot) -> None:
    """Store a transition of a row this transaction has locked."""
    session.execute(
        update(JOBS)
        .where(JOBS.c.id == job.id)
        .values(
            status=job.status.value,
            attempt=job.attempt,
            run_after=job.run_after,
            locked_by=job.locked_by,
            lease_expires_at=job.lease_expires_at,
            last_error=None if job.last_error is None else job.last_error.value,
            updated_at=job.updated_at,
            finished_at=job.finished_at,
        )
    )


def _fresh_time(session: Session) -> datetime:
    """A fresh ``clock_timestamp()``, read now rather than at transaction start."""
    now: datetime = session.execute(fresh_time_statement()).scalar_one()
    return now


def _sqlstate(error: OperationalError) -> str | None:
    value = getattr(error.orig, "sqlstate", None)
    return value if isinstance(value, str) else None


# --- enqueue -------------------------------------------------------------------------------


def enqueue(
    session: Session,
    actor: ActorContext,
    *,
    kind: str,
    idempotency_key: str,
    payload: JobPayload | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> JobSnapshot:
    """Create a job in the caller's transaction, or return the identical existing one.

    The tenant comes only from ``actor``. An identical retry (same payload, compared as a
    canonical object, and the same ``max_attempts``) returns the existing job unchanged, even
    when it is terminal: nothing is reset or rescheduled. A different payload or ``max_attempts``
    under the same key raises ``JobIdempotencyConflictError`` and changes nothing.

    Concurrent enqueues resolve through the unique constraint: under READ COMMITTED,
    ``ON CONFLICT DO NOTHING`` waits for a conflicting in-flight insert, and the following read
    sees the committed row.
    """
    request = JobRequest(
        tenant_id=actor.tenant_id,
        kind=kind,
        idempotency_key=idempotency_key,
        payload=payload if payload is not None else JobPayload(),
        max_attempts=max_attempts,
    )
    inserted = session.execute(
        pg_insert(JOBS)
        .values(
            id=uuid4(),
            tenant_id=request.tenant_id,
            kind=request.kind,
            idempotency_key=request.idempotency_key,
            payload=request.payload.as_dict(),
            status=JobStatus.QUEUED.value,
            attempt=0,
            max_attempts=request.max_attempts,
            run_after=func.clock_timestamp(),
        )
        .on_conflict_do_nothing(constraint=IDEMPOTENCY_CONSTRAINT)
        .returning(*JOBS.c)
    ).first()
    if inserted is not None:
        return _snapshot(inserted._mapping)

    existing = session.execute(
        select(JOBS).where(
            JOBS.c.tenant_id == request.tenant_id,
            JOBS.c.kind == request.kind,
            JOBS.c.idempotency_key == request.idempotency_key,
        )
    ).first()
    if existing is None:
        raise JobEnqueueRaceError()
    job = _snapshot(existing._mapping)
    if not request.matches(job):
        raise JobIdempotencyConflictError()
    return job


# --- claim ---------------------------------------------------------------------------------


def _validated_kinds(kinds: Collection[str] | None) -> frozenset[str] | None:
    if kinds is None:
        return None
    if isinstance(kinds, str):  # a string is a collection of characters, never a kind filter
        raise ValueError("kinds must be a collection of job kinds, not a string")
    return frozenset(lifecycle.validate_kind(kind) for kind in kinds)


def claim(
    session_factory: sessionmaker[Session],
    worker_id: str,
    *,
    kinds: Collection[str] | None = None,
) -> JobSnapshot | None:
    """Claim the next due or abandoned job for ``worker_id``, in one short transaction.

    First, at most ``SWEEP_LIMIT`` expired leases with no attempts left are marked ``dead``
    (``attempt`` unchanged). Then the oldest claimable row is taken with ``SKIP LOCKED``.
    Exhausted rows are excluded from that selection, so they never block eligible work.
    Returns ``None`` when nothing is claimable.

    ``kinds`` (M3b, ADR-0008) limits the candidates:

    - ``None`` keeps the behaviour above exactly: any kind;
    - a collection allows only those kinds. Every value is validated before any SQL, and an
      invalid one raises ``ValueError``;
    - an **empty** collection selects no candidate and returns ``None``; it never means "claim
      all". The sweep still runs, because it is global maintenance that never hands out a job.
    """
    lifecycle.validate_worker_id(worker_id)
    allowed = _validated_kinds(kinds)
    with transaction(session_factory) as session:
        exhausted = [_snapshot(row._mapping) for row in session.execute(sweep_statement())]
        if exhausted:
            swept_at = _fresh_time(session)
            for job in exhausted:
                _write(session, lifecycle.expire_exhausted(job, now=swept_at))

        if allowed is not None and not allowed:
            return None
        row = session.execute(claim_statement(allowed)).first()
        if row is None:
            return None
        claimed = lifecycle.claim(
            _snapshot(row._mapping), worker_id=worker_id, now=_fresh_time(session)
        )
        _write(session, claimed)
        return claimed


# --- the fence -----------------------------------------------------------------------------


class FencedSession:
    """The session access a fenced block is given.

    It reads and writes in the fenced transaction and stops working once the fence closes. It
    omits ``commit``, ``rollback`` and ``close`` so that ordinary session calls cannot end the
    transaction, and with it the lock, by accident. This is a convention for trusted handler
    code, not an enforced prohibition: ``execute`` accepts arbitrary SQL, and the underlying
    objects remain reachable from Python. Handlers must not issue transaction-control SQL, use
    the underlying session, transaction or connection, or change the job's ownership fields;
    the fence's guarantee assumes they do not.
    """

    def __init__(self, session: Session, fence: "Fence") -> None:
        self._session = session
        self._fence = fence

    def execute(
        self, statement: Executable, params: Mapping[str, Any] | None = None
    ) -> Result[Any]:
        self._fence._require_open()
        return self._session.execute(statement, params)

    def scalar(self, statement: Executable, params: Mapping[str, Any] | None = None) -> Any:
        self._fence._require_open()
        return self._session.scalar(statement, params)

    def scalars(
        self, statement: Executable, params: Mapping[str, Any] | None = None
    ) -> ScalarResult[Any]:
        self._fence._require_open()
        return self._session.scalars(statement, params)

    def add(self, instance: object) -> None:
        self._fence._require_open()
        self._session.add(instance)

    def flush(self) -> None:
        self._fence._require_open()
        self._session.flush()


class Fence:
    """An ownership-checked unit of work on one job. Created only by ``fenced_transaction``."""

    def __init__(self, session: Session, token: JobLeaseToken, job: JobSnapshot) -> None:
        self._session = session
        self._token = token
        self._job = job
        self._open = True
        self.session = FencedSession(session, self)

    @property
    def job(self) -> JobSnapshot:
        """The job as of the last ownership check or transition in this transaction."""
        return self._job

    @property
    def token(self) -> JobLeaseToken:
        return self._token

    def heartbeat(self) -> JobSnapshot:
        """Extend the lease by 60 seconds from fresh database time. Never revives one."""
        return self._transition(lambda job, now: lifecycle.heartbeat(job, self._token, now=now))

    def succeed(self) -> JobSnapshot:
        return self._finish(lambda job, now: lifecycle.succeed(job, self._token, now=now))

    def fail_retryable(self, code: JobErrorCode = JobErrorCode.RETRYABLE_FAILURE) -> JobSnapshot:
        """Re-queue after the backoff while attempts remain; otherwise ``dead``."""
        return self._finish(
            lambda job, now: lifecycle.fail_retryably(job, self._token, now=now, code=code)
        )

    def fail_permanent(self, code: JobErrorCode = JobErrorCode.PERMANENT_FAILURE) -> JobSnapshot:
        return self._finish(
            lambda job, now: lifecycle.fail_permanently(job, self._token, now=now, code=code)
        )

    def _require_open(self) -> None:
        if not self._open:
            raise FenceClosedError()

    def _close(self) -> None:
        self._open = False

    def _current(self) -> tuple[JobSnapshot, datetime]:
        self._require_open()
        return _checked_state(self._session, self._token)

    def _transition(self, rule: Callable[[JobSnapshot, datetime], JobSnapshot]) -> JobSnapshot:
        job, now = self._current()
        changed = rule(job, now)
        _write(self._session, changed)
        self._job = changed
        return changed

    def _finish(self, rule: Callable[[JobSnapshot, datetime], JobSnapshot]) -> JobSnapshot:
        """A transition that ends this attempt's ownership; the fence then admits no work."""
        changed = self._transition(rule)
        self._close()
        return changed


@contextmanager
def fenced_transaction(
    session_factory: sessionmaker[Session], token: JobLeaseToken
) -> Iterator[Fence]:
    """Run a unit of work only while ``token`` still owns the job (see the module docstring).

    Raises ``LeaseLostError`` (missing, terminal, reassigned or expired ownership) or
    ``JobLockTimeoutError`` before the block runs, with no effect. Any error inside the block
    rolls back every write made through ``Fence.session`` and every transition.
    """
    with transaction(session_factory) as session:
        session.execute(text(LOCK_TIMEOUT_SQL))
        try:
            locked = session.execute(lock_statement(token)).first()
        except OperationalError as error:
            if _sqlstate(error) == LOCK_NOT_AVAILABLE:
                raise JobLockTimeoutError() from None
            raise
        if locked is None:
            raise LeaseLostError()
        job, _ = _checked_state(session, token)
        fence = Fence(session, token, job)
        try:
            yield fence
        finally:
            fence._close()


def _checked_state(session: Session, token: JobLeaseToken) -> tuple[JobSnapshot, datetime]:
    """Read the locked row with a fresh database time and require valid ownership."""
    return _owned_state(session.execute(current_state_statement(token)).first(), token)


def _owned_state(row: Any, token: JobLeaseToken) -> tuple[JobSnapshot, datetime]:
    if row is None:
        raise LeaseLostError()
    data = dict(row._mapping)
    now: datetime = data.pop("db_now")
    job = _snapshot(data)
    if not lifecycle.holds_lease(job, token, now=now):
        raise LeaseLostError()
    return job, now


def recheck_ownership(session: FencedSession, token: JobLeaseToken) -> tuple[JobSnapshot, datetime]:
    """Re-check ownership inside an open fence, after further lock waits (M3c, ADR-0009).

    Re-reads the job row, which this transaction still holds locked, together with a fresh
    ``clock_timestamp()`` in one statement, through the fence's own session. It requires the
    matching token, status ``running`` and an unexpired lease (``holds_lease``), and returns the
    re-read job and that fresh time; otherwise it raises the fixed ``LeaseLostError``.

    It only reads: it adds no transition and never commits or rolls back. The token carries no
    tenant, so callers compare the returned job's ``tenant_id`` with their own scope. A
    transaction that passes this check just before expiry may still commit shortly after it
    (the accepted M3a limit).
    """
    return _owned_state(session.execute(current_state_statement(token)).first(), token)


# --- single-purpose fenced operations ------------------------------------------------------


def heartbeat(session_factory: sessionmaker[Session], token: JobLeaseToken) -> JobSnapshot:
    with fenced_transaction(session_factory, token) as fence:
        return fence.heartbeat()


def complete(session_factory: sessionmaker[Session], token: JobLeaseToken) -> JobSnapshot:
    with fenced_transaction(session_factory, token) as fence:
        return fence.succeed()


def fail_retryable(
    session_factory: sessionmaker[Session],
    token: JobLeaseToken,
    code: JobErrorCode = JobErrorCode.RETRYABLE_FAILURE,
) -> JobSnapshot:
    with fenced_transaction(session_factory, token) as fence:
        return fence.fail_retryable(code)


def fail_permanent(
    session_factory: sessionmaker[Session],
    token: JobLeaseToken,
    code: JobErrorCode = JobErrorCode.PERMANENT_FAILURE,
) -> JobSnapshot:
    with fenced_transaction(session_factory, token) as fence:
        return fence.fail_permanent(code)
