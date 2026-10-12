"""Pure job contracts and lifecycle rules (``evidenceguard_domain.jobs``), without a database."""

from datetime import UTC, datetime, timedelta, timezone, tzinfo
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from evidenceguard_domain import jobs
from evidenceguard_domain.jobs import (
    DEFAULT_MAX_ATTEMPTS,
    LEASE_SECONDS,
    PAYLOAD_MAX_BYTES,
    InvalidJobPayloadError,
    InvalidJobTransitionError,
    JobErrorCode,
    JobIdempotencyConflictError,
    JobLeaseToken,
    JobPayload,
    JobRequest,
    JobSnapshot,
    JobStatus,
    LeaseLostError,
)

T0 = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)
TENANT = UUID("11111111-1111-4111-8111-111111111111")
REVISION = "2b2b2b2b-2222-4222-8222-22222222abcd"
WORKER = "worker-a"
OTHER_WORKER = "worker-b"
SECRET_MARKER = "secret-marker-value"


def _queued(**overrides: Any) -> JobSnapshot:
    values: dict[str, Any] = {
        "id": uuid4(),
        "tenant_id": TENANT,
        "kind": "test_job",
        "idempotency_key": "key-1",
        "payload": JobPayload(),
        "status": JobStatus.QUEUED,
        "attempt": 0,
        "max_attempts": DEFAULT_MAX_ATTEMPTS,
        "run_after": T0,
        "created_at": T0,
        "updated_at": T0,
    }
    values.update(overrides)
    return JobSnapshot(**values)


def _running(attempt: int = 1, *, worker: str = WORKER, max_attempts: int = 3) -> JobSnapshot:
    return jobs.claim(
        _queued(attempt=attempt - 1, max_attempts=max_attempts), worker_id=worker, now=T0
    )


# --- defaults and backoff ----------------------------------------------------------------


def test_accepted_defaults() -> None:
    assert jobs.LEASE_SECONDS == 60
    assert jobs.HEARTBEAT_INTERVAL_SECONDS == 20
    assert jobs.DEFAULT_MAX_ATTEMPTS == 3
    assert (jobs.MIN_MAX_ATTEMPTS, jobs.MAX_MAX_ATTEMPTS) == (1, 10)
    assert jobs.LOCK_TIMEOUT_SECONDS == 5
    assert jobs.SWEEP_LIMIT == 10
    assert jobs.PAYLOAD_MAX_BYTES == 4096
    assert (jobs.KIND_MAX_LENGTH, jobs.IDEMPOTENCY_KEY_MAX_LENGTH) == (64, 128)


@pytest.mark.parametrize(
    ("attempt", "seconds"), [(1, 5), (2, 10), (3, 20), (4, 40), (5, 60), (6, 60), (10, 60)]
)
def test_backoff_doubles_from_five_seconds_and_caps_at_sixty(attempt: int, seconds: int) -> None:
    assert jobs.backoff_seconds(attempt) == seconds


def test_backoff_rejects_attempt_zero() -> None:
    with pytest.raises(ValueError):
        jobs.backoff_seconds(0)


# --- payload -----------------------------------------------------------------------------


def test_payload_is_canonical_and_order_independent() -> None:
    a = JobPayload.from_mapping({"revision_id": REVISION, "document_id": str(TENANT)})
    b = JobPayload.from_mapping({"document_id": str(TENANT), "revision_id": REVISION})

    assert a == b
    assert a.canonical_bytes() == b.canonical_bytes()
    assert a.canonical_bytes() == (
        b'{"document_id":"11111111-1111-4111-8111-111111111111",'
        b'"revision_id":"2b2b2b2b-2222-4222-8222-22222222abcd"}'
    )
    assert a.as_dict() == {"document_id": str(TENANT), "revision_id": REVISION}


def test_empty_payload_is_allowed() -> None:
    assert JobPayload().as_dict() == {}
    assert JobPayload.from_mapping({}).canonical_bytes() == b"{}"


def test_payload_is_immutable_and_round_trips_through_serialization() -> None:
    payload = JobPayload.from_mapping({"revision_id": REVISION})
    as_dict = payload.as_dict()
    as_dict["revision_id"] = str(uuid4())

    assert payload.as_dict() == {"revision_id": REVISION}
    with pytest.raises(ValidationError):
        payload.entries = ()  # type: ignore[misc]
    assert JobPayload.model_validate_json(payload.model_dump_json()) == payload
    assert JobPayload.model_validate(payload.model_dump()) == payload


@pytest.mark.parametrize(
    "value",
    [
        [],
        "text",
        None,
        {"revision_id": REVISION.upper()},  # not canonical: uppercase
        {"revision_id": REVISION.replace("-", "")},  # not canonical: no hyphens
        {"revision_id": f"{{{REVISION}}}"},  # not canonical: braces
        {"revision_id": " " + REVISION},
        {"revision_id": "not-a-uuid"},
        {"revision_id": 7},
        {"revision_id": None},
        {"revision_id": True},
        {"revision_id": [REVISION]},  # arrays
        {"revision_id": {"nested": REVISION}},  # nesting
        {"tenant_id": REVISION},  # tenant field
        {"owner_tenant": REVISION},
        {"Revision": REVISION},  # key not a lowercase identifier
        {"": REVISION},
        {"1revision": REVISION},
        {"k" * 65: REVISION},
        {"text": SECRET_MARKER},  # document text or secrets are not UUIDs
    ],
)
def test_invalid_payloads_are_rejected(value: object) -> None:
    with pytest.raises(InvalidJobPayloadError) as exc_info:
        JobPayload.from_mapping(value)
    assert SECRET_MARKER not in str(exc_info.value)
    assert REVISION not in str(exc_info.value)


def test_duplicate_payload_keys_are_rejected() -> None:
    with pytest.raises(ValidationError):
        JobPayload(entries=(("revision_id", REVISION), ("revision_id", str(TENANT))))


def _payload_of_size(target: int) -> dict[str, str]:
    """A payload whose canonical encoding is exactly ``target`` bytes."""
    mapping: dict[str, str] = {}
    index = 0
    while True:
        size = len(jobs.canonical_json(mapping))
        remaining = target - size - (1 if mapping else 0)  # comma before the next entry
        # One entry costs len(key) + 41 bytes ("key":"<36-char uuid>").
        if remaining - 41 <= 64:
            key_length = remaining - 41
            assert 1 <= key_length <= 64
            key = ("z" + f"{index:03d}" + "a" * 64)[:key_length]
            mapping[key] = str(UUID(int=index))
            assert len(jobs.canonical_json(mapping)) == target
            return mapping
        mapping["k" + f"{index:03d}" + "a" * 60] = str(UUID(int=index))
        index += 1


def test_payload_size_cap_is_exact_in_canonical_bytes() -> None:
    at_cap = _payload_of_size(PAYLOAD_MAX_BYTES)
    over_cap = _payload_of_size(PAYLOAD_MAX_BYTES + 1)

    assert len(JobPayload.from_mapping(at_cap).canonical_bytes()) == PAYLOAD_MAX_BYTES
    with pytest.raises(InvalidJobPayloadError):
        JobPayload.from_mapping(over_cap)


# --- requests and snapshots --------------------------------------------------------------


@pytest.mark.parametrize("kind", ["Test", "1job", "job-name", "", "j" * 65, " job"])
def test_invalid_kinds_are_rejected(kind: str) -> None:
    with pytest.raises(ValidationError):
        JobRequest(tenant_id=TENANT, kind=kind, idempotency_key="k")


@pytest.mark.parametrize("key", ["", " key", "key ", "a\x00b", "a\nb", "k" * 129])
def test_invalid_idempotency_keys_are_rejected_not_rewritten(key: str) -> None:
    with pytest.raises(ValidationError):
        JobRequest(tenant_id=TENANT, kind="test_job", idempotency_key=key)


@pytest.mark.parametrize("max_attempts", [0, 11, -1])
def test_max_attempts_range_is_one_to_ten(max_attempts: int) -> None:
    with pytest.raises(ValidationError):
        JobRequest(
            tenant_id=TENANT, kind="test_job", idempotency_key="k", max_attempts=max_attempts
        )


def test_request_defaults_and_identity() -> None:
    request = JobRequest(tenant_id=TENANT, kind="test_job", idempotency_key="key-1")
    job = _queued()

    assert request.max_attempts == 3 and request.payload == JobPayload()
    assert request.matches(job)
    assert not request.model_copy(update={"max_attempts": 4}).matches(job)
    changed = request.model_copy(
        update={"payload": JobPayload.from_mapping({"revision_id": REVISION})}
    )
    assert not changed.matches(job)
    assert request.matches(job.model_copy(update={"status": JobStatus.QUEUED}))


@pytest.mark.parametrize(
    "overrides",
    [
        {"attempt": 4, "max_attempts": 3},
        {"status": JobStatus.QUEUED, "locked_by": WORKER},
        {"status": JobStatus.QUEUED, "lease_expires_at": T0},
        {"status": JobStatus.RUNNING, "attempt": 1},  # running without a lease
        {"status": JobStatus.RUNNING, "attempt": 0, "locked_by": WORKER, "lease_expires_at": T0},
        {"status": JobStatus.SUCCEEDED, "attempt": 1},  # terminal without finished_at
        {"status": JobStatus.QUEUED, "finished_at": T0},
        {"locked_by": "bad worker id", "status": JobStatus.RUNNING, "attempt": 1},
    ],
)
def test_snapshot_invariants_are_enforced(overrides: dict[str, Any]) -> None:
    if "lease_expires_at" not in overrides and overrides.get("locked_by"):
        overrides = {**overrides, "lease_expires_at": T0}
    with pytest.raises(ValidationError):
        _queued(**overrides)


# --- claim and reclaim -------------------------------------------------------------------


def test_claim_increments_attempt_and_creates_a_sixty_second_lease() -> None:
    job = jobs.claim(_queued(), worker_id=WORKER, now=T0)

    assert job.status is JobStatus.RUNNING
    assert job.attempt == 1
    assert job.locked_by == WORKER
    assert job.lease_expires_at == T0 + timedelta(seconds=LEASE_SECONDS)
    assert job.lease_token() == JobLeaseToken(job_id=job.id, worker_id=WORKER, attempt=1)


def test_a_queued_job_is_claimable_only_when_due() -> None:
    later = _queued(run_after=T0 + timedelta(seconds=1))

    assert not jobs.is_claimable(later, now=T0)
    assert jobs.is_claimable(later, now=T0 + timedelta(seconds=1))
    with pytest.raises(InvalidJobTransitionError):
        jobs.claim(later, worker_id=WORKER, now=T0)


def test_an_expired_lease_is_reclaimed_by_a_new_attempt() -> None:
    job = _running()
    expiry = job.lease_expires_at
    assert expiry is not None

    assert not jobs.is_claimable(job, now=expiry - timedelta(microseconds=1))
    reclaimed = jobs.claim(job, worker_id=OTHER_WORKER, now=expiry)

    assert reclaimed.attempt == 2 and reclaimed.locked_by == OTHER_WORKER
    assert reclaimed.last_error is JobErrorCode.LEASE_EXPIRED


def test_attempt_never_exceeds_max_attempts() -> None:
    job = _running(attempt=3, max_attempts=3)
    expiry = job.lease_expires_at
    assert expiry is not None

    assert not jobs.is_claimable(job, now=expiry)
    with pytest.raises(InvalidJobTransitionError):
        jobs.claim(job, worker_id=OTHER_WORKER, now=expiry)

    dead = jobs.expire_exhausted(job, now=expiry)
    assert dead.status is JobStatus.DEAD and dead.attempt == 3
    assert dead.last_error is JobErrorCode.LEASE_EXPIRED
    assert (dead.locked_by, dead.lease_expires_at, dead.finished_at) == (None, None, expiry)


def test_only_expired_exhausted_jobs_can_be_expired() -> None:
    with pytest.raises(InvalidJobTransitionError):
        jobs.expire_exhausted(_running(attempt=1), now=T0 + timedelta(hours=1))
    exhausted = _running(attempt=3)
    with pytest.raises(InvalidJobTransitionError):
        jobs.expire_exhausted(exhausted, now=T0)  # lease still valid


@pytest.mark.parametrize("status", [JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.DEAD])
def test_terminal_jobs_are_never_claimable(status: JobStatus) -> None:
    job = _queued(status=status, attempt=1, finished_at=T0)

    assert not jobs.is_claimable(job, now=T0 + timedelta(days=1))
    with pytest.raises(InvalidJobTransitionError):
        jobs.claim(job, worker_id=WORKER, now=T0 + timedelta(days=1))


def test_invalid_worker_ids_are_rejected() -> None:
    for worker in ("", " w", "w w", "w" * 129, "w/1"):
        with pytest.raises(ValueError):
            jobs.claim(_queued(), worker_id=worker, now=T0)


# --- ownership -----------------------------------------------------------------------------


def test_ownership_requires_status_token_and_an_unexpired_lease() -> None:
    job = _running()
    token = job.lease_token()
    expiry = job.lease_expires_at
    assert expiry is not None

    assert jobs.holds_lease(job, token, now=T0)
    assert jobs.holds_lease(job, token, now=expiry - timedelta(microseconds=1))
    assert not jobs.holds_lease(job, token, now=expiry)  # expired from that instant
    assert not jobs.holds_lease(job, token.model_copy(update={"worker_id": "x"}), now=T0)
    assert not jobs.holds_lease(job, token.model_copy(update={"attempt": 2}), now=T0)
    assert not jobs.holds_lease(job, token.model_copy(update={"job_id": uuid4()}), now=T0)


def test_same_worker_with_a_newer_attempt_fences_the_older_attempt() -> None:
    first = _running(attempt=1)
    old_token = first.lease_token()
    expiry = first.lease_expires_at
    assert expiry is not None
    second = jobs.claim(first, worker_id=WORKER, now=expiry)

    assert not jobs.holds_lease(second, old_token, now=expiry)
    with pytest.raises(LeaseLostError):
        jobs.heartbeat(second, old_token, now=expiry)
    assert jobs.holds_lease(second, second.lease_token(), now=expiry)


def test_heartbeat_extends_but_never_revives() -> None:
    job = _running()
    token = job.lease_token()
    later = T0 + timedelta(seconds=30)

    extended = jobs.heartbeat(job, token, now=later)
    assert extended.lease_expires_at == later + timedelta(seconds=LEASE_SECONDS)
    assert extended.attempt == 1

    expiry = job.lease_expires_at
    assert expiry is not None
    with pytest.raises(LeaseLostError):
        jobs.heartbeat(job, token, now=expiry)


@pytest.mark.parametrize(
    "operation",
    [
        lambda job, token, now: jobs.heartbeat(job, token, now=now),
        lambda job, token, now: jobs.succeed(job, token, now=now),
        lambda job, token, now: jobs.fail_retryably(job, token, now=now),
        lambda job, token, now: jobs.fail_permanently(job, token, now=now),
    ],
)
def test_every_owned_operation_refuses_expired_or_stale_ownership(operation: Any) -> None:
    job = _running()
    token = job.lease_token()
    expiry = job.lease_expires_at
    assert expiry is not None

    with pytest.raises(LeaseLostError):
        operation(job, token, expiry)
    with pytest.raises(LeaseLostError):
        operation(job, token.model_copy(update={"attempt": 2}), T0)
    terminal = jobs.succeed(job, token, now=T0)
    with pytest.raises(LeaseLostError):
        operation(terminal, token, T0)


# --- completion and failure ----------------------------------------------------------------


def test_success_is_terminal_and_clears_the_lease() -> None:
    job = _running()
    done = jobs.succeed(job, job.lease_token(), now=T0 + timedelta(seconds=1))

    assert done.status is JobStatus.SUCCEEDED and done.is_terminal
    assert (done.locked_by, done.lease_expires_at) == (None, None)
    assert done.finished_at == T0 + timedelta(seconds=1)


def test_permanent_failure_ends_failed() -> None:
    job = _running()
    failed = jobs.fail_permanently(job, job.lease_token(), now=T0)

    assert failed.status is JobStatus.FAILED and failed.finished_at == T0
    assert failed.last_error is JobErrorCode.PERMANENT_FAILURE
    assert failed.attempt == 1


def test_retryable_failure_requeues_after_backoff_then_reaches_dead() -> None:
    job = _running(attempt=1, max_attempts=3)
    retried = jobs.fail_retryably(job, job.lease_token(), now=T0)

    assert retried.status is JobStatus.QUEUED
    assert (retried.locked_by, retried.lease_expires_at, retried.finished_at) == (None, None, None)
    assert retried.run_after == T0 + timedelta(seconds=5)
    assert retried.last_error is JobErrorCode.RETRYABLE_FAILURE

    second = jobs.claim(retried, worker_id=WORKER, now=retried.run_after)
    retried_again = jobs.fail_retryably(second, second.lease_token(), now=retried.run_after)
    assert retried_again.run_after == retried.run_after + timedelta(seconds=10)

    third = jobs.claim(retried_again, worker_id=WORKER, now=retried_again.run_after)
    dead = jobs.fail_retryably(third, third.lease_token(), now=retried_again.run_after)
    assert dead.status is JobStatus.DEAD and dead.attempt == 3
    assert dead.finished_at == retried_again.run_after
    assert not jobs.is_claimable(dead, now=dead.finished_at + timedelta(days=1))


# --- errors ----------------------------------------------------------------------------------


def test_errors_have_fixed_messages() -> None:
    assert str(LeaseLostError()) == "the job lease is not held by this worker"
    assert str(JobIdempotencyConflictError()) == (
        "a different job already uses this idempotency key"
    )
    assert str(InvalidJobTransitionError()) == "the job's state does not allow this transition"
    assert REVISION not in str(InvalidJobPayloadError())


# --- timezone-aware time -------------------------------------------------------------------


class _NoOffset(tzinfo):
    """A tzinfo whose ``utcoffset()`` is ``None``: not a usable aware time."""

    def utcoffset(self, dt: datetime | None) -> timedelta | None:
        return None

    def dst(self, dt: datetime | None) -> timedelta | None:
        return None

    def tzname(self, dt: datetime | None) -> str:
        return "no-offset"


NAIVE = datetime(2026, 10, 12, 12, 0)
NO_OFFSET = datetime(2026, 10, 12, 12, 0, tzinfo=_NoOffset())
INDIA = timezone(timedelta(hours=5, minutes=30))
PACIFIC = timezone(timedelta(hours=-8))


@pytest.mark.parametrize("bad", [NAIVE, NO_OFFSET])
@pytest.mark.parametrize(
    ("field", "base"),
    [
        ("run_after", {}),
        ("created_at", {}),
        ("updated_at", {}),
        ("lease_expires_at", {"status": JobStatus.RUNNING, "attempt": 1, "locked_by": WORKER}),
        ("finished_at", {"status": JobStatus.SUCCEEDED, "attempt": 1}),
    ],
)
def test_every_snapshot_timestamp_must_be_aware(
    field: str, base: dict[str, Any], bad: datetime
) -> None:
    valid = {"lease_expires_at": T0} if field != "lease_expires_at" and "locked_by" in base else {}
    if field != "finished_at" and base.get("status") is JobStatus.SUCCEEDED:
        valid["finished_at"] = T0
    _queued(**{**base, **valid, field: T0})  # the same snapshot is valid with an aware value

    with pytest.raises(ValidationError):
        _queued(**{**base, **valid, field: bad})


@pytest.mark.parametrize("field", ["run_after", "updated_at", "lease_expires_at"])
def test_a_validated_copy_cannot_introduce_a_naive_timestamp(field: str) -> None:
    job = _running()

    with pytest.raises(ValidationError):
        job.model_copy(update={field: NAIVE})


_TIME_OPERATIONS: list[tuple[str, Any]] = [
    ("lease_expired", lambda job, now: jobs.lease_expired(job, now=now)),
    ("is_claimable", lambda job, now: jobs.is_claimable(job, now=now)),
    ("is_exhausted_abandoned", lambda job, now: jobs.is_exhausted_abandoned(job, now=now)),
    ("holds_lease", lambda job, now: jobs.holds_lease(job, job.lease_token(), now=now)),
    ("claim", lambda job, now: jobs.claim(job, worker_id=OTHER_WORKER, now=now)),
    ("expire_exhausted", lambda job, now: jobs.expire_exhausted(job, now=now)),
    ("heartbeat", lambda job, now: jobs.heartbeat(job, job.lease_token(), now=now)),
    ("succeed", lambda job, now: jobs.succeed(job, job.lease_token(), now=now)),
    ("fail_permanently", lambda job, now: jobs.fail_permanently(job, job.lease_token(), now=now)),
    ("fail_retryably", lambda job, now: jobs.fail_retryably(job, job.lease_token(), now=now)),
]


@pytest.mark.parametrize("bad", [NAIVE, NO_OFFSET], ids=["naive", "no-offset"])
@pytest.mark.parametrize(
    ("name", "operation"), _TIME_OPERATIONS, ids=[n for n, _ in _TIME_OPERATIONS]
)
def test_every_time_dependent_operation_rejects_an_unaware_now(
    name: str, operation: Any, bad: datetime
) -> None:
    job = _running()

    with pytest.raises(ValueError) as exc_info:
        operation(job, bad)

    assert str(exc_info.value) == jobs.NAIVE_TIME_MESSAGE
    assert "2026" not in str(exc_info.value)
    assert not isinstance(exc_info.value, TypeError)


def test_non_utc_offsets_compare_by_instant_at_the_lease_boundary() -> None:
    job = _running()  # lease expires at T0 + 60 s, stored in UTC
    expiry = job.lease_expires_at
    assert expiry is not None
    token = job.lease_token()

    just_before = (expiry - timedelta(microseconds=1)).astimezone(INDIA)
    at_expiry = expiry.astimezone(PACIFIC)

    assert jobs.holds_lease(job, token, now=just_before)
    assert not jobs.lease_expired(job, now=just_before)
    assert not jobs.holds_lease(job, token, now=at_expiry)
    assert jobs.lease_expired(job, now=at_expiry)
    with pytest.raises(LeaseLostError):
        jobs.heartbeat(job, token, now=at_expiry)
    extended = jobs.heartbeat(job, token, now=just_before)
    assert extended.lease_expires_at == expiry - timedelta(microseconds=1) + timedelta(seconds=60)


def test_non_utc_offsets_compare_by_instant_at_the_due_time() -> None:
    due = T0 + timedelta(seconds=30)
    job = _queued(run_after=due.astimezone(PACIFIC))

    assert not jobs.is_claimable(job, now=(due - timedelta(microseconds=1)).astimezone(INDIA))
    claimed = jobs.claim(job, worker_id=WORKER, now=due.astimezone(INDIA))
    assert claimed.status is JobStatus.RUNNING
    assert claimed.lease_expires_at == due + timedelta(seconds=LEASE_SECONDS)
