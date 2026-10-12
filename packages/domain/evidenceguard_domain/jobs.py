"""Durable job contracts and lifecycle rules (M3a, ADR-0007).

Everything here is pure: callers pass the current time explicitly, and nothing reads a clock or a
database. The persistence layer supplies fresh PostgreSQL ``clock_timestamp()`` values and
applies these rules to locked rows.

Lifecycle:

- ``queued`` → ``running`` on a claim, which increments ``attempt`` and creates a lease;
- ``running`` → ``running`` on a heartbeat (lease extended) or a reclaim of an expired lease
  (``attempt`` incremented, new owner);
- ``running`` → ``succeeded``, ``failed`` (permanent handler failure), ``queued`` (retryable
  failure with attempts left, after a backoff) or ``dead`` (retryable failure, or an abandoned
  lease, with the attempt cap reached).

``succeeded``, ``failed`` and ``dead`` are terminal: they clear the lease, set ``finished_at``
and are never claimed or reset again. ``attempt`` never exceeds ``max_attempts``.

The fencing token is ``(job_id, worker_id, attempt)``. Because every claim increments
``attempt``, a reclaim invalidates the previous owner even when the same worker ID reclaims.

Times are timezone-aware. Snapshot timestamps use Pydantic's ``AwareDatetime``, and every
public time-dependent function rejects a naive ``now`` (or one whose ``utcoffset()`` is ``None``)
with a fixed ``ValueError``; a naive value is never assumed to be UTC. Aware values with any
offset are compared by their actual instants.

Errors carry fixed messages only: never payload values, SQL or other exception text.
"""

import json
import re
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, field_validator, model_validator

from evidenceguard_domain._base import DomainModel
from evidenceguard_domain.errors import DomainError

# --- accepted M3a defaults (engineering defaults, not measured performance claims) ----------

LEASE_SECONDS = 60
HEARTBEAT_INTERVAL_SECONDS = 20  # used by the M3b worker; M3a has no timer
DEFAULT_MAX_ATTEMPTS = 3
MIN_MAX_ATTEMPTS = 1
MAX_MAX_ATTEMPTS = 10
BACKOFF_BASE_SECONDS = 5
BACKOFF_CAP_SECONDS = 60
LOCK_TIMEOUT_SECONDS = 5
SWEEP_LIMIT = 10
PAYLOAD_MAX_BYTES = 4096
KIND_MAX_LENGTH = 64
IDEMPOTENCY_KEY_MAX_LENGTH = 128
WORKER_ID_MAX_LENGTH = 128
ERROR_CODE_MAX_LENGTH = 64

# A lowercase identifier: a letter, then letters, digits or underscores (at most 64 in all).
KIND_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"
PAYLOAD_KEY_PATTERN = KIND_PATTERN
ERROR_CODE_PATTERN = KIND_PATTERN
WORKER_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"

_KIND = re.compile(KIND_PATTERN)
_PAYLOAD_KEY = re.compile(PAYLOAD_KEY_PATTERN)
_WORKER_ID = re.compile(WORKER_ID_PATTERN)
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DEAD = "dead"


TERMINAL_STATUSES = frozenset({JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.DEAD})


class JobErrorCode(StrEnum):
    """Fixed diagnostic codes stored in ``last_error``. Never free text."""

    RETRYABLE_FAILURE = "retryable_failure"
    PERMANENT_FAILURE = "permanent_failure"
    LEASE_EXPIRED = "lease_expired"
    # Recorded by the M3b worker runtime (ADR-0008).
    UNKNOWN_JOB_KIND = "unknown_job_kind"
    UNEXPECTED_ERROR = "unexpected_error"
    WORKER_SHUTDOWN = "worker_shutdown"


# --- errors ------------------------------------------------------------------------------


class LeaseLostError(DomainError):
    """This worker no longer holds a valid lease on the job. Nothing was changed."""

    def __init__(self) -> None:
        super().__init__("the job lease is not held by this worker")


class JobIdempotencyConflictError(DomainError):
    """A job with this idempotency key exists with a different payload or configuration."""

    def __init__(self) -> None:
        super().__init__("a different job already uses this idempotency key")


class InvalidJobTransitionError(DomainError):
    """The job's state does not allow this transition."""

    def __init__(self) -> None:
        super().__init__("the job's state does not allow this transition")


class InvalidJobPayloadError(DomainError, ValueError):
    """The payload is not an allowed M3a payload. The message never contains its values."""

    def __init__(self) -> None:
        super().__init__(
            "a job payload must be a flat JSON object of lowercase identifier keys and "
            f"canonical UUID strings, without tenant fields, at most {PAYLOAD_MAX_BYTES} bytes"
        )


# --- payload -----------------------------------------------------------------------------


def _is_canonical_uuid(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return str(UUID(value)) == value
    except ValueError:
        return False


def _valid_entry(key: object, value: object) -> bool:
    return (
        isinstance(key, str)
        and _PAYLOAD_KEY.fullmatch(key) is not None
        and "tenant" not in key
        and _is_canonical_uuid(value)
    )


def canonical_json(mapping: dict[str, str]) -> bytes:
    """Sorted keys, compact separators, UTF-8. Used for the size cap and for identity."""
    return json.dumps(mapping, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _validated_entries(value: Any) -> tuple[tuple[str, str], ...]:
    """The sorted pairs of a valid payload. Raises ``InvalidJobPayloadError`` otherwise."""
    if not isinstance(value, list | tuple):
        raise InvalidJobPayloadError()
    pairs: list[tuple[str, str]] = []
    for item in value:
        if not isinstance(item, list | tuple) or len(item) != 2:
            raise InvalidJobPayloadError()
        key, entry = item
        if not _valid_entry(key, entry):
            raise InvalidJobPayloadError()
        pairs.append((key, entry))
    if len({key for key, _ in pairs}) != len(pairs):
        raise InvalidJobPayloadError()
    if len(canonical_json(dict(pairs))) > PAYLOAD_MAX_BYTES:
        raise InvalidJobPayloadError()
    return tuple(sorted(pairs))


class JobPayload(DomainModel):
    """An M3a job payload: a flat object of identifier keys and canonical UUID strings.

    Stored as a sorted tuple of ``(key, value)`` pairs, so the value is immutable and two
    payloads that differ only in key order are equal. Kind-specific schemas arrive with their
    handlers in later slices. Invalid input is rejected, never rewritten.
    """

    entries: tuple[tuple[str, str], ...] = ()

    @field_validator("entries", mode="before")
    @classmethod
    def _check_entries(cls, value: Any) -> tuple[tuple[str, str], ...]:
        return _validated_entries(value)

    @classmethod
    def from_mapping(cls, mapping: object) -> "JobPayload":
        """Validate a decoded JSON value; raise ``InvalidJobPayloadError`` unless it is a flat
        object of allowed pairs within the size cap."""
        if not isinstance(mapping, dict):
            raise InvalidJobPayloadError()
        return cls(entries=_validated_entries(tuple(mapping.items())))

    def as_dict(self) -> dict[str, str]:
        """A new, plain dictionary (for JSON storage)."""
        return dict(self.entries)

    def canonical_bytes(self) -> bytes:
        return canonical_json(self.as_dict())


# --- request and snapshot ------------------------------------------------------------------


def validate_kind(value: Any) -> str:
    """Raise ``ValueError`` unless ``value`` is an allowed job kind; return it."""
    if not isinstance(value, str) or _KIND.fullmatch(value) is None:
        raise ValueError("kind must be a lowercase identifier of at most 64 characters")
    return value


def _check_idempotency_key(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= IDEMPOTENCY_KEY_MAX_LENGTH
        or value != value.strip()
        or _CONTROL.search(value) is not None
    ):
        raise ValueError(
            "idempotency_key must be 1-128 characters, without surrounding whitespace or "
            "control characters"
        )
    return value


def validate_worker_id(value: Any) -> str:
    """Raise ``ValueError`` unless ``value`` is an allowed worker ID; return it."""
    if not isinstance(value, str) or _WORKER_ID.fullmatch(value) is None:
        raise ValueError("worker_id must be 1-128 letters, digits or . _ : -")
    return value


class JobRequest(DomainModel):
    """What a caller asks to enqueue. Its identity is the payload and ``max_attempts``."""

    tenant_id: UUID
    kind: str
    idempotency_key: str
    payload: JobPayload = Field(default_factory=JobPayload)
    max_attempts: int = Field(
        default=DEFAULT_MAX_ATTEMPTS, ge=MIN_MAX_ATTEMPTS, le=MAX_MAX_ATTEMPTS
    )

    @field_validator("kind", mode="before")
    @classmethod
    def _validate_kind(cls, value: Any) -> str:
        return validate_kind(value)

    @field_validator("idempotency_key", mode="before")
    @classmethod
    def _validate_key(cls, value: Any) -> str:
        return _check_idempotency_key(value)

    def matches(self, job: "JobSnapshot") -> bool:
        """True when ``job`` was created by an identical request (same key and identity)."""
        return (
            job.tenant_id == self.tenant_id
            and job.kind == self.kind
            and job.idempotency_key == self.idempotency_key
            and job.payload == self.payload
            and job.max_attempts == self.max_attempts
        )


class JobLeaseToken(DomainModel):
    """The fencing token. A write is allowed only while all three still match the row."""

    job_id: UUID
    worker_id: str
    attempt: int = Field(ge=1, le=MAX_MAX_ATTEMPTS)

    @field_validator("worker_id", mode="before")
    @classmethod
    def _validate_worker(cls, value: Any) -> str:
        return validate_worker_id(value)


class JobSnapshot(DomainModel):
    """A job as read from the database: an immutable value, never a session-bound object."""

    id: UUID
    tenant_id: UUID
    kind: str
    idempotency_key: str
    payload: JobPayload
    status: JobStatus
    attempt: int = Field(ge=0, le=MAX_MAX_ATTEMPTS)
    max_attempts: int = Field(ge=MIN_MAX_ATTEMPTS, le=MAX_MAX_ATTEMPTS)
    run_after: AwareDatetime
    locked_by: str | None = None
    lease_expires_at: AwareDatetime | None = None
    last_error: JobErrorCode | None = None
    created_at: AwareDatetime
    updated_at: AwareDatetime
    finished_at: AwareDatetime | None = None

    @field_validator("kind", mode="before")
    @classmethod
    def _validate_kind(cls, value: Any) -> str:
        return validate_kind(value)

    @field_validator("idempotency_key", mode="before")
    @classmethod
    def _validate_key(cls, value: Any) -> str:
        return _check_idempotency_key(value)

    @field_validator("locked_by", mode="before")
    @classmethod
    def _validate_locked_by(cls, value: Any) -> str | None:
        return None if value is None else validate_worker_id(value)

    @model_validator(mode="after")
    def _check_invariants(self) -> Self:
        if self.attempt > self.max_attempts:
            raise ValueError("attempt must not exceed max_attempts")
        running = self.status is JobStatus.RUNNING
        leased = self.locked_by is not None and self.lease_expires_at is not None
        unleased = self.locked_by is None and self.lease_expires_at is None
        if (running and not leased) or (not running and not unleased):
            raise ValueError("lease fields are set exactly while the job is running")
        if running and self.attempt < 1:
            raise ValueError("a running job has started at least one attempt")
        if (self.status in TERMINAL_STATUSES) != (self.finished_at is not None):
            raise ValueError("finished_at is set exactly for terminal jobs")
        return self

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    def lease_token(self) -> JobLeaseToken:
        """The token of the current owner. Only a running job has one."""
        if self.status is not JobStatus.RUNNING or self.locked_by is None:
            raise InvalidJobTransitionError()
        return JobLeaseToken(job_id=self.id, worker_id=self.locked_by, attempt=self.attempt)


# --- pure rules ----------------------------------------------------------------------------

NAIVE_TIME_MESSAGE = "now must be a timezone-aware datetime"


def require_aware(now: datetime) -> datetime:
    """Return ``now`` if it is timezone-aware; otherwise raise a fixed ``ValueError``.

    A value without ``tzinfo``, or whose ``utcoffset()`` is ``None``, is rejected rather than
    assumed to be UTC. The message never contains the value.
    """
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError(NAIVE_TIME_MESSAGE)
    return now


def backoff_seconds(failed_attempt: int) -> int:
    """Delay after failed attempt ``n`` (1-based): ``min(5 * 2^(n - 1), 60)``. No jitter."""
    if failed_attempt < 1:
        raise ValueError("failed_attempt starts at 1")
    exponent = min(failed_attempt - 1, 4)  # 5 * 2^4 = 80 already exceeds the cap
    return min(BACKOFF_BASE_SECONDS * (1 << exponent), BACKOFF_CAP_SECONDS)


def lease_expired(job: JobSnapshot, *, now: datetime) -> bool:
    """A lease is valid strictly before ``lease_expires_at`` and expired from that instant."""
    require_aware(now)
    return job.lease_expires_at is not None and job.lease_expires_at <= now


def is_claimable(job: JobSnapshot, *, now: datetime) -> bool:
    """Due queued jobs and abandoned running jobs, while attempts remain."""
    require_aware(now)
    if job.attempt >= job.max_attempts:
        return False
    if job.status is JobStatus.QUEUED:
        return job.run_after <= now
    return job.status is JobStatus.RUNNING and lease_expired(job, now=now)


def is_exhausted_abandoned(job: JobSnapshot, *, now: datetime) -> bool:
    """A running job whose lease expired with no attempts left: it can only become dead."""
    require_aware(now)
    return (
        job.status is JobStatus.RUNNING
        and lease_expired(job, now=now)
        and job.attempt >= job.max_attempts
    )


def holds_lease(job: JobSnapshot, token: JobLeaseToken, *, now: datetime) -> bool:
    """The strict ownership check: running, matching token and an unexpired lease."""
    require_aware(now)
    return (
        job.id == token.job_id
        and job.status is JobStatus.RUNNING
        and job.locked_by == token.worker_id
        and job.attempt == token.attempt
        and job.lease_expires_at is not None
        and now < job.lease_expires_at
    )


def claim(job: JobSnapshot, *, worker_id: str, now: datetime) -> JobSnapshot:
    """Claim a due job or reclaim an abandoned one: the next attempt, owned by ``worker_id``."""
    require_aware(now)
    validate_worker_id(worker_id)
    if not is_claimable(job, now=now):
        raise InvalidJobTransitionError()
    reclaimed = job.status is JobStatus.RUNNING
    return job.model_copy(
        update={
            "status": JobStatus.RUNNING,
            "attempt": job.attempt + 1,
            "locked_by": worker_id,
            "lease_expires_at": now + timedelta(seconds=LEASE_SECONDS),
            "last_error": JobErrorCode.LEASE_EXPIRED if reclaimed else job.last_error,
            "updated_at": now,
        }
    )


def expire_exhausted(job: JobSnapshot, *, now: datetime) -> JobSnapshot:
    """An abandoned lease with no attempts left becomes ``dead``; ``attempt`` is unchanged."""
    require_aware(now)
    if not is_exhausted_abandoned(job, now=now):
        raise InvalidJobTransitionError()
    return _finish(job, JobStatus.DEAD, JobErrorCode.LEASE_EXPIRED, now)


def heartbeat(job: JobSnapshot, token: JobLeaseToken, *, now: datetime) -> JobSnapshot:
    """Extend a valid lease. An expired lease is never revived."""
    require_aware(now)
    _require_lease(job, token, now)
    return job.model_copy(
        update={"lease_expires_at": now + timedelta(seconds=LEASE_SECONDS), "updated_at": now}
    )


def succeed(job: JobSnapshot, token: JobLeaseToken, *, now: datetime) -> JobSnapshot:
    require_aware(now)
    _require_lease(job, token, now)
    return _finish(job, JobStatus.SUCCEEDED, job.last_error, now)


def fail_permanently(
    job: JobSnapshot,
    token: JobLeaseToken,
    *,
    now: datetime,
    code: JobErrorCode = JobErrorCode.PERMANENT_FAILURE,
) -> JobSnapshot:
    """A non-retryable handler failure: the job ends ``failed``."""
    require_aware(now)
    _require_lease(job, token, now)
    return _finish(job, JobStatus.FAILED, code, now)


def fail_retryably(
    job: JobSnapshot,
    token: JobLeaseToken,
    *,
    now: datetime,
    code: JobErrorCode = JobErrorCode.RETRYABLE_FAILURE,
) -> JobSnapshot:
    """Re-queue after the backoff while attempts remain; otherwise the job ends ``dead``."""
    require_aware(now)
    _require_lease(job, token, now)
    if job.attempt >= job.max_attempts:
        return _finish(job, JobStatus.DEAD, code, now)
    return job.model_copy(
        update={
            "status": JobStatus.QUEUED,
            "locked_by": None,
            "lease_expires_at": None,
            "run_after": now + timedelta(seconds=backoff_seconds(job.attempt)),
            "last_error": code,
            "updated_at": now,
        }
    )


def _require_lease(job: JobSnapshot, token: JobLeaseToken, now: datetime) -> None:
    if not holds_lease(job, token, now=now):
        raise LeaseLostError()


def _finish(
    job: JobSnapshot, status: JobStatus, code: JobErrorCode | None, now: datetime
) -> JobSnapshot:
    return job.model_copy(
        update={
            "status": status,
            "locked_by": None,
            "lease_expires_at": None,
            "last_error": code,
            "finished_at": now,
            "updated_at": now,
        }
    )
