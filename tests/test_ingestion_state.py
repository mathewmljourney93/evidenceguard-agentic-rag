"""The derived ``ingestion_state`` projection (M3d section E, M3e), from pure inputs."""

from datetime import UTC, datetime, timedelta

import pytest

from evidenceguard_domain.ingestion import (
    INGEST_REVISION_KIND,
    IngestionState,
    derive_ingestion_state,
    lease_expired,
)
from evidenceguard_domain.jobs import JobStatus
from evidenceguard_domain.revisions import RevisionStatus
from evidenceguard_worker.ingest import INGEST_REVISION_KIND as WORKER_KIND

NOW = datetime(2026, 10, 15, 9, 30, tzinfo=UTC)
UNSETTLED = (RevisionStatus.PENDING, RevisionStatus.PROCESSING)
SETTLED = (RevisionStatus.ACTIVE, RevisionStatus.SUPERSEDED, RevisionStatus.FAILED)


@pytest.mark.parametrize("status", SETTLED)
@pytest.mark.parametrize("job", [None, *JobStatus])
def test_a_settled_status_wins_over_any_job(status: RevisionStatus, job: JobStatus | None) -> None:
    assert derive_ingestion_state(status, job) == IngestionState(status.value)


@pytest.mark.parametrize("status", UNSETTLED)
@pytest.mark.parametrize(
    ("job", "state"),
    [
        (JobStatus.QUEUED, IngestionState.QUEUED),
        (JobStatus.RUNNING, IngestionState.IN_PROGRESS),
        (JobStatus.DEAD, IngestionState.STALLED),
        (JobStatus.FAILED, IngestionState.STALLED),
        (JobStatus.SUCCEEDED, IngestionState.STALLED),
        (None, IngestionState.STALLED),
    ],
)
def test_an_unsettled_status_follows_the_canonical_job(
    status: RevisionStatus, job: JobStatus | None, state: IngestionState
) -> None:
    assert derive_ingestion_state(status, job) is state


def test_lease_expiry_is_reported_only_for_running_jobs() -> None:
    assert lease_expired(JobStatus.RUNNING, NOW - timedelta(seconds=1), now=NOW) is True
    assert lease_expired(JobStatus.RUNNING, NOW, now=NOW) is True  # expired at its expiry (M3a)
    assert lease_expired(JobStatus.RUNNING, NOW + timedelta(seconds=1), now=NOW) is False
    for status in (None, JobStatus.QUEUED, JobStatus.DEAD, JobStatus.SUCCEEDED):
        assert lease_expired(status, NOW - timedelta(days=1), now=NOW) is None
    assert lease_expired(JobStatus.RUNNING, None, now=NOW) is None


def test_lease_expiry_requires_an_aware_time() -> None:
    with pytest.raises(ValueError):
        lease_expired(JobStatus.RUNNING, NOW, now=NOW.replace(tzinfo=None))


def test_the_projection_uses_the_workers_kind() -> None:
    assert INGEST_REVISION_KIND == WORKER_KIND
