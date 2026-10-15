"""Document read models and upload creation without a database (M3e D).

Statements are compiled for PostgreSQL and inspected; sessions are recording doubles. The SQL's
behaviour against real rows is covered by ``test_document_api_postgres.py``.
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import postgresql

from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_domain.evidence import SourceType
from evidenceguard_domain.ingestion import IngestionState
from evidenceguard_domain.jobs import JobStatus
from evidenceguard_domain.revisions import MediaType, RevisionContent, RevisionStatus
from evidenceguard_persistence import document_views
from evidenceguard_persistence.document_views import (
    READ_SNAPSHOT_SQL,
    read_snapshot,
    revisions_with_job_statement,
    upload_observation_statement,
)

NOW = datetime(2026, 10, 15, 9, 30, tzinfo=UTC)
ACTOR = ActorContext(tenant_id=uuid4(), actor_id=uuid4(), role=Role.REVIEWER)


def sql(statement: Any) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))  # type: ignore[no-untyped-call]


# --- the read snapshot ---------------------------------------------------------------------------


class RecordingSession:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.events: list[str] = []

    def execute(self, statement: Any, *args: Any) -> Any:
        self.statements.append(sql(statement))
        return SimpleNamespace(scalar_one=lambda: NOW)

    def rollback(self) -> None:
        self.events.append("rollback")

    def close(self) -> None:
        self.events.append("close")


def test_set_transaction_is_the_first_statement_then_one_clock_read() -> None:
    session = RecordingSession()
    with read_snapshot(lambda: session) as (yielded, now):  # type: ignore[arg-type]
        assert yielded is session and now == NOW  # type: ignore[comparison-overlap]
    assert session.statements[0] == READ_SNAPSHOT_SQL
    assert READ_SNAPSHOT_SQL == "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
    assert "clock_timestamp()" in session.statements[1]
    assert len(session.statements) == 2
    assert session.events == ["rollback", "close"]


def test_the_snapshot_always_ends_even_on_error() -> None:
    session = RecordingSession()
    with pytest.raises(RuntimeError), read_snapshot(lambda: session):  # type: ignore[arg-type]
        raise RuntimeError("boom")
    assert session.events == ["rollback", "close"]


def test_no_session_level_isolation_settings() -> None:
    source = document_views.__loader__.get_source(document_views.__name__)  # type: ignore[union-attr]
    assert source is not None
    for forbidden in ("SET SESSION", "default_transaction_isolation", "isolation_level="):
        assert forbidden not in source


# --- statement shapes ----------------------------------------------------------------------------


def test_revision_views_never_select_content_and_join_the_canonical_job() -> None:
    text = sql(revisions_with_job_statement())
    assert "content_text" not in text
    assert "LEFT OUTER JOIN jobs ON" in text
    assert "jobs.tenant_id = document_revisions.tenant_id" in text
    assert "jobs.kind = %(kind_1)s" in text
    assert "jobs.idempotency_key = CAST(document_revisions.id AS VARCHAR)" in text
    for hidden in ("payload", "locked_by", "jobs.idempotency_key AS", "last_error"):
        assert hidden not in text.split(" FROM ")[0]


def test_the_upload_observation_is_one_statement_with_the_database_time() -> None:
    tenant, revision_id = uuid4(), uuid4()
    statement = upload_observation_statement(tenant, revision_id)
    text = sql(statement)
    assert text.count("SELECT") == 1
    assert "clock_timestamp() AS db_now" in text
    assert "document_revisions.tenant_id = %(tenant_id_1)s" in text
    assert "content_text" not in text


def test_every_read_statement_is_tenant_filtered() -> None:
    captured: list[str] = []

    class Session:
        def execute(self, statement: Any) -> Any:
            captured.append(sql(statement))
            return SimpleNamespace(first=lambda: None)

    session: Any = Session()
    document_id = uuid4()
    assert document_views.vendor_exists(session, ACTOR, uuid4()) is False
    assert document_views.list_documents(session, ACTOR, uuid4(), limit=1, offset=0) is None
    assert document_views.get_document(session, ACTOR, document_id, now=NOW) is None
    assert (
        document_views.list_revisions(session, ACTOR, document_id, limit=1, offset=0, now=NOW)
        is None
    )
    assert document_views.get_revision_by_no(session, ACTOR, document_id, 1, now=NOW) is None
    assert document_views.list_chunks(session, ACTOR, document_id, 1, limit=1, offset=0) is None
    assert document_views.get_job_view(session, ACTOR, uuid4(), now=NOW) is None
    assert len(captured) == 7
    for text in captured:
        assert ".tenant_id = %(tenant_id_1)s" in text


# --- upload creation -----------------------------------------------------------------------------


def observation(status: RevisionStatus, job: JobStatus | None, **extra: Any) -> SimpleNamespace:
    running = job is JobStatus.RUNNING
    return SimpleNamespace(
        id=extra.get("id", uuid4()),
        revision_no=3,
        status=status.value,
        job_id=None if job is None else uuid4(),
        job_status=None if job is None else job.value,
        job_attempt=1,
        job_max_attempts=3,
        job_lease_expires_at=NOW - timedelta(seconds=5) if running else None,
        db_now=NOW,
    )


class UploadSession:
    def __init__(self, row: SimpleNamespace) -> None:
        self.row = row
        self.statements: list[str] = []

    def execute(self, statement: Any) -> Any:
        self.statements.append(sql(statement))
        return SimpleNamespace(one=lambda: self.row)


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, Any]]:
    state: dict[str, Any] = {"enqueued": []}

    def fake_create_revision(session: Any, actor: ActorContext, **kwargs: Any) -> Any:
        state["create_kwargs"] = kwargs
        return SimpleNamespace(
            created=state["created"],
            document=SimpleNamespace(id=state["document_id"]),
            revision=SimpleNamespace(id=state["revision_id"], status=state["status"]),
        )

    def fake_enqueue(session: Any, actor: ActorContext, **kwargs: Any) -> None:
        state["enqueued"].append(kwargs)

    monkeypatch.setattr(document_views, "create_revision", fake_create_revision)
    monkeypatch.setattr(document_views, "enqueue", fake_enqueue)
    yield state


def _upload(
    calls: dict[str, Any], created: bool, status: RevisionStatus, job: JobStatus | None
) -> Any:
    calls.update(created=created, status=status, document_id=uuid4(), revision_id=uuid4())
    session = UploadSession(observation(status, job, id=calls["revision_id"]))
    content = RevisionContent.from_bytes(b"Data is encrypted.\n", MediaType.TEXT_PLAIN)
    record = document_views.create_upload(
        session,  # type: ignore[arg-type]
        ACTOR,
        vendor_id=uuid4(),
        document_key="security-policy",
        title="Security policy",
        source_type=SourceType.CONTRACT,
        content=content,
    )
    return record, session


def test_a_new_revision_enqueues_its_canonical_job(calls: dict[str, Any]) -> None:
    record, session = _upload(calls, True, RevisionStatus.PENDING, JobStatus.QUEUED)
    (enqueued,) = calls["enqueued"]
    revision_id = str(calls["revision_id"])
    assert enqueued["kind"] == "ingest_revision"
    assert enqueued["idempotency_key"] == revision_id
    assert enqueued["payload"].as_dict() == {"revision_id": revision_id}
    assert "max_attempts" not in enqueued  # the M3a default
    assert (record.created, record.ingestion_state) == (True, IngestionState.QUEUED)
    assert len(session.statements) == 1  # one observation statement after the writes


@pytest.mark.parametrize(
    ("status", "job", "enqueues", "state"),
    [
        (RevisionStatus.PROCESSING, JobStatus.RUNNING, True, IngestionState.IN_PROGRESS),
        (RevisionStatus.PENDING, JobStatus.DEAD, True, IngestionState.STALLED),
        (RevisionStatus.PENDING, None, True, IngestionState.STALLED),
        (RevisionStatus.ACTIVE, JobStatus.SUCCEEDED, False, IngestionState.ACTIVE),
        (RevisionStatus.SUPERSEDED, None, False, IngestionState.SUPERSEDED),
        (RevisionStatus.FAILED, JobStatus.SUCCEEDED, False, IngestionState.FAILED),
    ],
)
def test_duplicates_report_the_observed_state(
    calls: dict[str, Any],
    status: RevisionStatus,
    job: JobStatus | None,
    enqueues: bool,
    state: IngestionState,
) -> None:
    record, _session = _upload(calls, False, status, job)
    assert bool(calls["enqueued"]) is enqueues  # never for a settled revision
    assert (record.created, record.revision_status, record.ingestion_state) == (
        False,
        status,
        state,
    )
    if job is JobStatus.RUNNING:
        assert record.job.lease_expired is True
        assert record.job.lease_expires_at is not None
    if job is None:
        assert record.job is None


def test_upload_record_identity_comes_from_the_observation(calls: dict[str, Any]) -> None:
    record, _session = _upload(calls, True, RevisionStatus.PENDING, JobStatus.QUEUED)
    assert record.revision_id == calls["revision_id"]
    assert record.document_id == calls["document_id"]
    assert record.revision_no == 3
    assert isinstance(record.revision_id, UUID)
