"""The derived ingestion state of a revision (M3d section E, implemented in M3e; ADR-0011).

Pure rules, no I/O. The stored revision ``status`` stays authoritative and is never rewritten;
``ingestion_state`` is derived at read time from that status and the revision's **canonical
ingestion job**: the job with ``kind = INGEST_REVISION_KIND`` and ``idempotency_key`` equal to the
canonical revision ID, in the revision's tenant. At most one such job exists (a unique index).

| Revision status                 | Canonical job                      | ``ingestion_state``      |
|---------------------------------|------------------------------------|--------------------------|
| ``active``/``superseded``/``failed`` | any, or none                  | equal to the status      |
| ``pending``/``processing``      | ``queued``                         | ``queued``               |
| ``pending``/``processing``      | ``running`` (lease current or not) | ``in_progress``          |
| ``pending``/``processing``      | ``dead``/``failed``/``succeeded``  | ``stalled``              |
| ``pending``/``processing``      | none                               | ``stalled``              |

``in_progress`` is **not** a progress guarantee: ``lease_expired`` reports, against one database
time, whether the running attempt's lease has already expired and awaits reclaim.
"""

from datetime import datetime
from enum import StrEnum

from evidenceguard_domain.jobs import JobStatus, require_aware
from evidenceguard_domain.revisions import RevisionStatus

INGEST_REVISION_KIND = "ingest_revision"
"""The job kind of revision ingestion (M3d); equal to the worker's registered kind."""


class IngestionState(StrEnum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    STALLED = "stalled"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    FAILED = "failed"


_SETTLED = {
    RevisionStatus.ACTIVE: IngestionState.ACTIVE,
    RevisionStatus.SUPERSEDED: IngestionState.SUPERSEDED,
    RevisionStatus.FAILED: IngestionState.FAILED,
}


def derive_ingestion_state(
    revision_status: RevisionStatus, job_status: JobStatus | None
) -> IngestionState:
    """The table above, checked in order: a settled status wins over any job."""
    settled = _SETTLED.get(RevisionStatus(revision_status))
    if settled is not None:
        return settled
    if job_status is JobStatus.QUEUED:
        return IngestionState.QUEUED
    if job_status is JobStatus.RUNNING:
        return IngestionState.IN_PROGRESS
    return IngestionState.STALLED  # dead, failed, succeeded, or no canonical job


def lease_expired(
    job_status: JobStatus | None, lease_expires_at: datetime | None, *, now: datetime
) -> bool | None:
    """``True``/``False`` only for a running job, compared with ``now`` (a database time);
    ``None`` otherwise. A lease is expired at or after its expiry, as in M3a's lease rule."""
    require_aware(now)
    if job_status is not JobStatus.RUNNING or lease_expires_at is None:
        return None
    return lease_expires_at <= now
