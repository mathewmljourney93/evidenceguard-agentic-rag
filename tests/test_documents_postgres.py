"""PostgreSQL integration tests for documents, revisions and fenced activation (M3c, ADR-0009).

They use the guarded disposable-database fixtures from ``conftest.py`` and are skipped without
``EG_TEST_DATABASE_URL`` (required in CI). Every connection carries a server-side
``statement_timeout``; concurrency uses separate connections (``NullPool``), explicit
synchronisation (events, barriers and observed lock waits) and bounded waits. One test holds a
document lock past the real 5-second ``lock_timeout``; its waits stay well below the 20-second
statement timeout. Handlers here are test-only: M3c adds no production ingestion handler.
"""

import hashlib
import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Any
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
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
from evidenceguard_domain.evidence import SourceType
from evidenceguard_domain.jobs import (
    LOCK_TIMEOUT_SECONDS,
    JobErrorCode,
    JobPayload,
    JobSnapshot,
    JobStatus,
    LeaseLostError,
)
from evidenceguard_domain.revisions import (
    RevisionContent,
    RevisionFailureCode,
    RevisionStatus,
)
from evidenceguard_persistence import documents as store
from evidenceguard_persistence import jobs as job_store
from evidenceguard_persistence.db import create_session_factory, transaction
from evidenceguard_persistence.models import Document, DocumentRevision, Job, Tenant, Vendor
from evidenceguard_worker.context import JobContext, PermanentJobError
from evidenceguard_worker.registry import HandlerRegistry
from evidenceguard_worker.runtime import DatabaseJobStore, Timings, WorkerOutcome, run_worker

pytestmark = pytest.mark.integration

FOREIGN_KEY_VIOLATION = "23503"
UNIQUE_VIOLATION = "23505"
CHECK_VIOLATION = "23514"
WAIT_SECONDS = 10
KIND = "test_ingest"
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


@pytest.fixture
def actor(engine: Engine) -> ActorContext:
    return _tenant(engine, "tenant-a")


@pytest.fixture
def vendor(engine: Engine, actor: ActorContext) -> UUID:
    return _vendor(engine, actor.tenant_id)


# --- helpers -------------------------------------------------------------------------------


def _tenant(engine: Engine, slug: str) -> ActorContext:
    tenant_id = uuid4()
    with engine.begin() as connection:
        connection.execute(insert(Tenant).values(id=tenant_id, slug=slug, name=slug.title()))
    return ActorContext(tenant_id=tenant_id, actor_id=uuid4(), role=Role.REVIEWER)


def _vendor(engine: Engine, tenant_id: UUID, slug: str = "lumenvale") -> UUID:
    vendor_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            insert(Vendor).values(id=vendor_id, tenant_id=tenant_id, slug=slug, name=slug.title())
        )
    return vendor_id


def _content(text_: str = "Synthetic retention policy v1\n") -> RevisionContent:
    return RevisionContent.from_bytes(text_.encode(), "text/markdown")


def _create_in(
    session: Session,
    actor: ActorContext,
    vendor_id: UUID,
    content: RevisionContent,
    **kwargs: Any,
) -> store.RevisionCreation:
    args: dict[str, Any] = {
        "vendor_id": vendor_id,
        "document_key": "data-retention",
        "title": "Data retention",
        "source_type": SourceType.VENDOR_STATEMENT,
        "content": content,
    }
    args.update(kwargs)
    return store.create_revision(session, actor, **args)


def _create(
    factory: sessionmaker[Session],
    actor: ActorContext,
    vendor_id: UUID,
    content: RevisionContent | None = None,
    **kwargs: Any,
) -> store.RevisionCreation:
    with transaction(factory) as session:
        return _create_in(session, actor, vendor_id, content or _content(), **kwargs)


def _enqueue_in(session: Session, actor: ActorContext, revision_id: UUID) -> JobSnapshot:
    return job_store.enqueue(
        session,
        actor,
        kind=KIND,
        idempotency_key=str(uuid4()),
        payload=JobPayload.from_mapping({"revision_id": str(revision_id)}),
    )


def _claimed_job(
    factory: sessionmaker[Session], actor: ActorContext, revision_id: UUID, worker: str = "w-a"
) -> JobSnapshot:
    with transaction(factory) as session:
        queued = _enqueue_in(session, actor, revision_id)
    claimed = job_store.claim(factory, worker, kinds=[KIND])
    assert claimed is not None and claimed.id == queued.id
    return claimed


def _process(factory: sessionmaker[Session], job: JobSnapshot) -> None:
    with job_store.fenced_transaction(factory, job.lease_token()) as fence:
        store.start_processing(fence.session, fence.job)


def _processing(
    factory: sessionmaker[Session],
    actor: ActorContext,
    vendor_id: UUID,
    text_: str,
) -> tuple[UUID, JobSnapshot]:
    """A new revision with ``text_``, moved to ``processing`` by its own claimed job."""
    revision_id = _create(factory, actor, vendor_id, _content(text_)).revision.id
    job = _claimed_job(factory, actor, revision_id)
    _process(factory, job)
    return revision_id, job


def _activate_and_succeed(factory: sessionmaker[Session], job: JobSnapshot) -> Any:
    with job_store.fenced_transaction(factory, job.lease_token()) as fence:
        result = store.activate_revision(fence.session, fence.job)
        fence.succeed()
    return result


def _revisions(engine: Engine, document_id: UUID) -> dict[UUID, dict[str, Any]]:
    with engine.connect() as connection:
        rows = connection.execute(
            select(DocumentRevision.__table__).where(DocumentRevision.document_id == document_id)
        ).all()
    return {row.id: dict(row._mapping) for row in rows}


def _document(engine: Engine, document_id: UUID) -> dict[str, Any]:
    with engine.connect() as connection:
        row = connection.execute(select(Document.__table__).where(Document.id == document_id)).one()
    return dict(row._mapping)


def _document_of(engine: Engine, revision_id: UUID) -> UUID:
    with engine.connect() as connection:
        document_id: UUID = connection.execute(
            select(DocumentRevision.document_id).where(DocumentRevision.id == revision_id)
        ).scalar_one()
    return document_id


def _job_row(engine: Engine, job_id: UUID) -> dict[str, Any]:
    with engine.connect() as connection:
        row = connection.execute(select(Job.__table__).where(Job.id == job_id)).one()
    return dict(row._mapping)


def _state(engine: Engine, document_id: UUID) -> tuple[Any, ...]:
    return (_document(engine, document_id), _revisions(engine, document_id))


def _interval(seconds: int) -> Any:
    return literal_column(f"interval '{seconds} seconds'", type_=Interval)


def _outcome(fn: Callable[[], Any]) -> Callable[[], Any]:
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


def _lock_waiters(engine: Engine) -> int:
    with engine.connect() as connection:
        waiting: int = connection.execute(
            text(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE datname = current_database() AND wait_event_type = 'Lock'"
            )
        ).scalar_one()
    return waiting


def _sqlstate(error: IntegrityError) -> str | None:
    return getattr(error.orig, "sqlstate", None)


def _constraint(error: IntegrityError) -> str | None:
    return getattr(getattr(error.orig, "diag", None), "constraint_name", None)


def _raw_document(engine: Engine, tenant_id: UUID, vendor_id: UUID, **overrides: Any) -> UUID:
    values: dict[str, Any] = {
        "id": uuid4(),
        "tenant_id": tenant_id,
        "vendor_id": vendor_id,
        "document_key": f"doc-{uuid4().hex[:8]}",
        "title": "Synthetic document",
        "source_type": "vendor_statement",
    }
    values.update(overrides)
    with engine.begin() as connection:
        connection.execute(insert(Document).values(**values))
    document_id: UUID = values["id"]
    return document_id


def _raw_revision(engine: Engine, tenant_id: UUID, document_id: UUID, **overrides: Any) -> UUID:
    values: dict[str, Any] = {
        "id": uuid4(),
        "tenant_id": tenant_id,
        "document_id": document_id,
        "revision_no": 1,
        "status": "pending",
        "sha256": hashlib.sha256(uuid4().bytes).hexdigest(),
        "media_type": "text/plain",
        "byte_size": 4,
        "content_text": "text",
    }
    values.update(overrides)
    with engine.begin() as connection:
        connection.execute(insert(DocumentRevision).values(**values))
    revision_id: UUID = values["id"]
    return revision_id


# --- migration --------------------------------------------------------------------------------


def test_downgrading_0003_with_linked_rows_and_upgrading_again(
    engine: Engine,
    factory: sessionmaker[Session],
    actor: ActorContext,
    vendor: UUID,
    config: Config,
) -> None:
    """The circular pointer must be dropped before the tables, even with data present."""
    _, job = _processing(factory, actor, vendor, "linked rows\n")
    _activate_and_succeed(factory, job)

    command.downgrade(config, "0002")
    with engine.connect() as connection:
        tables = set(
            connection.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            ).scalars()
        )
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert not {"documents", "document_revisions"} & tables
    assert {"jobs", "vendors"} <= tables and version == "0002"

    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM documents")).scalar_one() == 0


def test_the_documents_schema_has_no_triggers(engine: Engine) -> None:
    with engine.connect() as connection:
        count = connection.execute(
            text(
                "SELECT count(*) FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
                "WHERE c.relname IN ('documents', 'document_revisions') AND NOT t.tgisinternal"
            )
        ).scalar_one()
    assert count == 0


# --- constraints ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"document_key": "Not A Key"},
        {"title": "   "},
        {"source_type": "brochure"},
        {"authenticity": "established"},
        {"latest_revision_no": -1},
    ],
)
def test_document_checks_reject_invalid_rows(
    engine: Engine, actor: ActorContext, vendor: UUID, overrides: dict[str, Any]
) -> None:
    with pytest.raises(IntegrityError) as error:
        _raw_document(engine, actor.tenant_id, vendor, **overrides)
    assert _sqlstate(error.value) == CHECK_VIOLATION


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "paused"},
        {"revision_no": 0},
        {"version_label": "  "},
        {"sha256": "A" * 64},
        {"sha256": "abc"},
        {"media_type": "text/html"},
        {"byte_size": 0},
        {"status": "failed"},  # without its reason and time
        {"status": "failed", "failure_reason": "ingestion_failed"},  # without failed_at
        {"failure_reason": "ingestion_failed", "failed_at": func.now()},  # not failed
        {"status": "failed", "failure_reason": "Not-A-Code", "failed_at": func.now()},
        {"status": "active"},  # without activated_at
        {"activated_at": func.now()},  # pending with an activation time
        {"status": "superseded", "superseded_at": func.now()},  # without the successor
    ],
)
def test_revision_checks_reject_partial_or_invalid_state(
    engine: Engine, actor: ActorContext, vendor: UUID, overrides: dict[str, Any]
) -> None:
    document_id = _raw_document(engine, actor.tenant_id, vendor)

    with pytest.raises(IntegrityError) as error:
        _raw_revision(engine, actor.tenant_id, document_id, **overrides)
    assert _sqlstate(error.value) == CHECK_VIOLATION


def test_the_database_accepts_any_failure_code_matching_the_pattern(
    engine: Engine, actor: ActorContext, vendor: UUID
) -> None:
    """The CHECK enforces the fixed-code pattern, not ``RevisionFailureCode`` membership: an
    unknown but well-formed code is stored. Only the application restricts codes to the enum."""
    document_id = _raw_document(engine, actor.tenant_id, vendor)
    assert "parser_crashed" not in {code.value for code in RevisionFailureCode}

    revision_id = _raw_revision(
        engine,
        actor.tenant_id,
        document_id,
        status="failed",
        failure_reason="parser_crashed",
        failed_at=func.now(),
    )

    assert _revisions(engine, document_id)[revision_id]["failure_reason"] == "parser_crashed"


def test_a_successor_without_superseded_status_is_rejected(
    engine: Engine, actor: ActorContext, vendor: UUID
) -> None:
    document_id = _raw_document(engine, actor.tenant_id, vendor)
    successor = _raw_revision(engine, actor.tenant_id, document_id, revision_no=2)

    with pytest.raises(IntegrityError) as error:
        _raw_revision(engine, actor.tenant_id, document_id, superseded_by_revision_id=successor)
    assert _sqlstate(error.value) == CHECK_VIOLATION


def test_a_document_cannot_reference_another_tenants_vendor(
    engine: Engine, actor: ActorContext
) -> None:
    other = _tenant(engine, "tenant-b")
    foreign_vendor = _vendor(engine, other.tenant_id)

    with pytest.raises(IntegrityError) as error:
        _raw_document(engine, actor.tenant_id, foreign_vendor)
    assert _sqlstate(error.value) == FOREIGN_KEY_VIOLATION


def test_a_revision_cannot_belong_to_another_tenants_document(
    engine: Engine, actor: ActorContext, vendor: UUID
) -> None:
    other = _tenant(engine, "tenant-b")
    document_id = _raw_document(engine, actor.tenant_id, vendor)

    with pytest.raises(IntegrityError) as error:
        _raw_revision(engine, other.tenant_id, document_id)
    assert _sqlstate(error.value) == FOREIGN_KEY_VIOLATION


def test_the_active_pointer_must_name_a_revision_of_the_same_document(
    engine: Engine, actor: ActorContext, vendor: UUID
) -> None:
    first = _raw_document(engine, actor.tenant_id, vendor)
    second = _raw_document(engine, actor.tenant_id, vendor)
    foreign = _raw_revision(engine, actor.tenant_id, second)

    with pytest.raises(IntegrityError) as error, engine.begin() as connection:
        connection.execute(
            update(Document).where(Document.id == first).values(active_revision_id=foreign)
        )
    assert _sqlstate(error.value) == FOREIGN_KEY_VIOLATION
    assert _constraint(error.value) == "fk_documents_active_revision"


def test_the_successor_must_be_a_revision_of_the_same_document(
    engine: Engine, actor: ActorContext, vendor: UUID
) -> None:
    first = _raw_document(engine, actor.tenant_id, vendor)
    second = _raw_document(engine, actor.tenant_id, vendor)
    foreign = _raw_revision(engine, actor.tenant_id, second)

    with pytest.raises(IntegrityError) as error:
        _raw_revision(
            engine,
            actor.tenant_id,
            first,
            status="superseded",
            superseded_at=func.now(),
            superseded_by_revision_id=foreign,
        )
    assert _sqlstate(error.value) == FOREIGN_KEY_VIOLATION
    assert _constraint(error.value) == "fk_document_revisions_superseded_by"


def test_at_most_one_revision_of_a_document_is_active(
    engine: Engine, actor: ActorContext, vendor: UUID
) -> None:
    document_id = _raw_document(engine, actor.tenant_id, vendor)
    _raw_revision(engine, actor.tenant_id, document_id, status="active", activated_at=func.now())

    with pytest.raises(IntegrityError) as error:
        _raw_revision(
            engine,
            actor.tenant_id,
            document_id,
            revision_no=2,
            status="active",
            activated_at=func.now(),
        )
    assert _sqlstate(error.value) == UNIQUE_VIOLATION
    assert _constraint(error.value) == "uq_document_revisions_one_active"
    # Another document may have its own active revision.
    other = _raw_document(engine, actor.tenant_id, vendor)
    _raw_revision(engine, actor.tenant_id, other, status="active", activated_at=func.now())


def test_identical_bytes_are_unique_per_document_only(
    engine: Engine, actor: ActorContext, vendor: UUID
) -> None:
    sha = "a" * 64
    first = _raw_document(engine, actor.tenant_id, vendor)
    second = _raw_document(engine, actor.tenant_id, vendor)
    _raw_revision(engine, actor.tenant_id, first, sha256=sha)
    _raw_revision(engine, actor.tenant_id, second, sha256=sha)

    with pytest.raises(IntegrityError) as error:
        _raw_revision(engine, actor.tenant_id, first, revision_no=2, sha256=sha)
    assert _sqlstate(error.value) == UNIQUE_VIOLATION


# --- creation --------------------------------------------------------------------------------


def test_creation_stores_the_exact_bytes_and_their_hash(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext, vendor: UUID
) -> None:
    raw = "\ufeffLine one\r\n  caf\u00e9 \u2014 e\u0301  \r\n".encode()
    content = RevisionContent.from_bytes(raw, "text/plain")

    created = _create(
        factory, actor, vendor, content, version_label="v1", effective_date=date(2026, 1, 1)
    )

    with engine.connect() as connection:
        row = connection.execute(
            select(
                DocumentRevision.content_text,
                DocumentRevision.sha256,
                DocumentRevision.byte_size,
                func.octet_length(DocumentRevision.content_text),
                func.encode(
                    func.sha256(func.convert_to(DocumentRevision.content_text, "UTF8")), "hex"
                ),
            ).where(DocumentRevision.id == created.revision.id)
        ).one()
    assert row[0].encode() == raw
    assert row[1] == row[4] == hashlib.sha256(raw).hexdigest()
    assert row[2] == row[3] == len(raw)
    assert created.created and created.revision.revision_no == 1
    assert created.revision.status is RevisionStatus.PENDING
    stored = RevisionContent.from_stored(
        media_type="text/plain", content_text=row[0], sha256=row[1], byte_size=row[2]
    )
    assert stored == content
    document = _document(engine, created.document.id)
    assert document["latest_revision_no"] == 1 and document["active_revision_id"] is None


def test_new_bytes_get_the_next_number_and_identical_bytes_return_the_revision(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext, vendor: UUID
) -> None:
    first = _create(factory, actor, vendor, _content("one\n"))
    second = _create(factory, actor, vendor, _content("two\n"))
    before = _state(engine, first.document.id)

    again = _create(factory, actor, vendor, _content("one\n"))

    assert second.revision.revision_no == 2
    assert not again.created and again.revision.id == first.revision.id
    assert _state(engine, first.document.id) == before


def test_identical_bytes_return_a_failed_revision(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext, vendor: UUID
) -> None:
    revision_id, job = _processing(factory, actor, vendor, "will fail\n")
    with job_store.fenced_transaction(factory, job.lease_token()) as fence:
        store.fail_revision(fence.session, fence.job, RevisionFailureCode.INGESTION_FAILED)

    again = _create(factory, actor, vendor, _content("will fail\n"))

    assert not again.created and again.revision.id == revision_id
    assert again.revision.status is RevisionStatus.FAILED


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"title": "Renamed"}, store.DocumentConflictError),
        ({"source_type": SourceType.CONTRACT}, store.DocumentConflictError),
        ({"version_label": "v2"}, store.RevisionConflictError),
    ],
)
def test_metadata_conflicts_commit_nothing(
    engine: Engine,
    factory: sessionmaker[Session],
    actor: ActorContext,
    vendor: UUID,
    monkeypatch: pytest.MonkeyPatch,
    overrides: dict[str, Any],
    error: type[Exception],
) -> None:
    first = _create(factory, actor, vendor, version_label="v1")
    before = _state(engine, first.document.id)
    arguments: dict[str, Any] = {"version_label": "v1"}
    arguments.update(overrides)
    raised: list[type[Exception]] = []
    real = store.create_revision

    def recording(*args: Any, **kwargs: Any) -> store.RevisionCreation:
        try:
            return real(*args, **kwargs)
        except Exception as caught:
            raised.append(type(caught))
            raise

    monkeypatch.setattr(store, "create_revision", recording)
    with pytest.raises(error):
        _create(factory, actor, vendor, **arguments)

    assert raised == [error]  # the persistence operation itself raised the conflict
    assert _state(engine, first.document.id) == before


def test_a_vendor_of_another_tenant_is_not_found(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext
) -> None:
    other = _tenant(engine, "tenant-b")
    foreign_vendor = _vendor(engine, other.tenant_id)

    with pytest.raises(store.VendorNotFoundError):
        _create(factory, actor, foreign_vendor)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM documents")).scalar_one() == 0


def test_a_revision_and_its_job_commit_or_roll_back_together(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext, vendor: UUID
) -> None:
    with pytest.raises(RuntimeError), transaction(factory) as session:
        created = _create_in(session, actor, vendor, _content())
        _enqueue_in(session, actor, created.revision.id)
        raise RuntimeError("the request failed after both writes")
    with engine.connect() as connection:
        for table in ("documents", "document_revisions", "jobs"):
            assert connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0

    with transaction(factory) as session:
        created = _create_in(session, actor, vendor, _content())
        job = _enqueue_in(session, actor, created.revision.id)
    assert _job_row(engine, job.id)["payload"] == {"revision_id": str(created.revision.id)}
    assert created.revision.id in _revisions(engine, created.document.id)


def test_concurrent_distinct_bytes_get_distinct_consecutive_numbers(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext, vendor: UUID
) -> None:
    texts = ["second\n", "third\n", "fourth\n"]

    def creator(text_: str) -> Callable[[], Any]:
        return _outcome(lambda: _create(factory, actor, vendor, _content(text_)))

    with ThreadPoolExecutor(max_workers=len(texts)) as pool:
        # The holder's uncommitted creation blocks the others until it commits.
        with transaction(factory) as holder:
            held = _create_in(holder, actor, vendor, _content("first\n"))
            futures = [pool.submit(creator(t)) for t in texts]
            _wait_until(lambda: _lock_waiters(engine) >= len(texts))
        results = [future.result(timeout=WAIT_SECONDS) for future in futures]

    assert held.revision.revision_no == 1
    assert all(isinstance(r, store.RevisionCreation) and r.created for r in results), results
    assert sorted(r.revision.revision_no for r in results) == [2, 3, 4]
    assert _document(engine, held.document.id)["latest_revision_no"] == 4


@pytest.mark.parametrize("holder_commits", [True, False])
def test_concurrent_identical_bytes_resolve_to_one_revision(
    engine: Engine,
    factory: sessionmaker[Session],
    actor: ActorContext,
    vendor: UUID,
    holder_commits: bool,
) -> None:
    held_id: UUID | None = None
    with ThreadPoolExecutor(max_workers=1) as pool:
        holder = factory()
        try:
            held_id = _create_in(holder, actor, vendor, _content()).revision.id
            waiter = pool.submit(_outcome(lambda: _create(factory, actor, vendor, _content())))
            _wait_until(lambda: _lock_waiters(engine) >= 1)
            if holder_commits:
                holder.commit()
            else:
                holder.rollback()
        finally:
            holder.close()
        result = waiter.result(timeout=WAIT_SECONDS)

    assert isinstance(result, store.RevisionCreation), result
    if holder_commits:
        assert not result.created and result.revision.id == held_id
    else:
        assert result.created and result.revision.revision_no == 1
    assert len(_revisions(engine, result.document.id)) == 1


# --- lifecycle and activation -----------------------------------------------------------------


def test_first_activation_and_job_success_commit_together(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext, vendor: UUID
) -> None:
    revision_id, job = _processing(factory, actor, vendor, "one\n")

    result = _activate_and_succeed(factory, job)

    document_id = _document_of(engine, revision_id)
    row = _revisions(engine, document_id)[revision_id]
    assert row["status"] == "active" and row["activated_at"] is not None
    assert _document(engine, document_id)["active_revision_id"] == revision_id
    assert result.superseded is None
    assert _job_row(engine, job.id)["status"] == "succeeded"
    assert job_store.claim(factory, "w-b", kinds=[KIND]) is None  # never reclaimed


def test_a_failed_replacement_keeps_the_active_revision(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext, vendor: UUID
) -> None:
    first, job = _processing(factory, actor, vendor, "one\n")
    _activate_and_succeed(factory, job)
    second, replacement = _processing(factory, actor, vendor, "two\n")

    with job_store.fenced_transaction(factory, replacement.lease_token()) as fence:
        store.fail_revision(fence.session, fence.job, RevisionFailureCode.INGESTION_FAILED)

    document_id = _document_of(engine, first)
    rows = _revisions(engine, document_id)
    assert rows[first]["status"] == "active"
    assert (rows[second]["status"], rows[second]["failure_reason"]) == (
        "failed",
        "ingestion_failed",
    )
    assert _document(engine, document_id)["active_revision_id"] == first


def test_activation_compares_with_the_active_revision_not_the_latest_upload(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext, vendor: UUID
) -> None:
    first, job_1 = _processing(factory, actor, vendor, "one\n")
    _activate_and_succeed(factory, job_1)
    second, job_2 = _processing(factory, actor, vendor, "two\n")
    third = _create(factory, actor, vendor, _content("three\n")).revision.id  # still pending

    _activate_and_succeed(factory, job_2)

    document_id = _document_of(engine, first)
    rows = _revisions(engine, document_id)
    assert rows[second]["status"] == "active" and rows[third]["status"] == "pending"
    assert (rows[first]["status"], rows[first]["superseded_by_revision_id"]) == (
        "superseded",
        second,
    )
    assert rows[first]["superseded_at"] == rows[second]["activated_at"]
    assert _document(engine, document_id)["active_revision_id"] == second


def test_an_older_revision_finishing_late_supersedes_only_itself(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext, vendor: UUID
) -> None:
    older, older_job = _processing(factory, actor, vendor, "one\n")
    newer, newer_job = _processing(factory, actor, vendor, "two\n")
    _activate_and_succeed(factory, newer_job)
    document_id = _document_of(engine, older)
    document_before = _document(engine, document_id)
    newer_before = _revisions(engine, document_id)[newer]

    _activate_and_succeed(factory, older_job)

    rows = _revisions(engine, document_id)
    assert rows[newer] == newer_before
    assert (rows[older]["status"], rows[older]["superseded_by_revision_id"]) == (
        "superseded",
        newer,
    )
    assert rows[older]["activated_at"] is None
    assert _document(engine, document_id) == document_before


def test_concurrent_activations_leave_one_consistent_active_revision(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext, vendor: UUID
) -> None:
    first, job_1 = _processing(factory, actor, vendor, "one\n")
    second, job_2 = _processing(factory, actor, vendor, "two\n")
    barrier = threading.Barrier(2, timeout=WAIT_SECONDS)

    def activation(job: JobSnapshot) -> Callable[[], Any]:
        def run() -> Any:
            barrier.wait()
            return _activate_and_succeed(factory, job)

        return _outcome(run)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(activation(job_1)), pool.submit(activation(job_2))]
        results = [future.result(timeout=WAIT_SECONDS) for future in futures]

    assert all(isinstance(r, store.ActivationResult) for r in results), results
    document_id = _document_of(engine, first)
    rows = _revisions(engine, document_id)
    assert [r["status"] for r in rows.values()].count("active") == 1
    assert rows[second]["status"] == "active"
    assert (rows[first]["status"], rows[first]["superseded_by_revision_id"]) == (
        "superseded",
        second,
    )
    assert _document(engine, document_id)["active_revision_id"] == second


def test_a_failure_after_demotion_rolls_back_the_whole_activation(
    engine: Engine,
    factory: sessionmaker[Session],
    actor: ActorContext,
    vendor: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first, job_1 = _processing(factory, actor, vendor, "one\n")
    _activate_and_succeed(factory, job_1)
    _, job_2 = _processing(factory, actor, vendor, "two\n")
    document_id = _document_of(engine, first)
    before = (_state(engine, document_id), _job_row(engine, job_2.id))
    real = store.update_revision_statement
    built: list[str] = []

    def demote_then_fail(revision: Any) -> Any:
        built.append(revision.status.value)
        if len(built) == 2:
            raise RuntimeError("injected after the demotion was written")
        return real(revision)

    monkeypatch.setattr(store, "update_revision_statement", demote_then_fail)
    with pytest.raises(RuntimeError):
        _activate_and_succeed(factory, job_2)

    assert built == ["superseded", "active"]
    assert (_state(engine, document_id), _job_row(engine, job_2.id)) == before


def test_a_failed_pointer_write_or_job_success_rolls_back_the_activation(
    engine: Engine,
    factory: sessionmaker[Session],
    actor: ActorContext,
    vendor: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision_id, job = _processing(factory, actor, vendor, "one\n")
    document_id = _document_of(engine, revision_id)
    before = (_state(engine, document_id), _job_row(engine, job.id))

    def no_pointer(document: Any) -> Any:
        raise RuntimeError("injected pointer failure")

    with monkeypatch.context() as patch:
        patch.setattr(store, "update_pointer_statement", no_pointer)
        with pytest.raises(RuntimeError):
            _activate_and_succeed(factory, job)
    assert (_state(engine, document_id), _job_row(engine, job.id)) == before

    # The final job success fails: the lease is gone by the time it is recorded.
    with (
        pytest.raises(LeaseLostError),
        job_store.fenced_transaction(factory, job.lease_token()) as fence,
    ):
        store.activate_revision(fence.session, fence.job)
        fence.session.execute(
            update(Job)
            .where(Job.id == job.id)
            .values(lease_expires_at=func.clock_timestamp() - _interval(1))
        )
        fence.succeed()
    assert (_state(engine, document_id), _job_row(engine, job.id)) == before


def test_ownership_lost_inside_the_fence_is_refused_before_any_write(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext, vendor: UUID
) -> None:
    revision_id, job = _processing(factory, actor, vendor, "one\n")
    document_id = _document_of(engine, revision_id)
    before = _state(engine, document_id)

    with (
        pytest.raises(LeaseLostError),
        job_store.fenced_transaction(factory, job.lease_token()) as fence,
    ):
        # Expire the lease in the fence's own transaction: only the fresh re-check sees it.
        fence.session.execute(
            update(Job)
            .where(Job.id == job.id)
            .values(lease_expires_at=func.clock_timestamp() - _interval(1))
        )
        store.activate_revision(fence.session, fence.job)

    assert _state(engine, document_id) == before


def test_a_stale_attempt_is_refused_and_changes_nothing(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext, vendor: UUID
) -> None:
    revision_id, stale = _processing(factory, actor, vendor, "one\n")
    with engine.begin() as connection:
        connection.execute(
            update(Job)
            .where(Job.id == stale.id)
            .values(lease_expires_at=func.clock_timestamp() - _interval(1))
        )
    reclaimed = job_store.claim(factory, "w-b", kinds=[KIND])
    assert reclaimed is not None and reclaimed.attempt == 2
    document_id = _document_of(engine, revision_id)
    before = _state(engine, document_id)

    with pytest.raises(LeaseLostError):
        _activate_and_succeed(factory, stale)

    assert _state(engine, document_id) == before
    _activate_and_succeed(factory, reclaimed)
    assert _document(engine, document_id)["active_revision_id"] == revision_id


def test_a_lease_expiring_during_the_document_lock_wait_is_refused(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext, vendor: UUID
) -> None:
    revision_id, job = _processing(factory, actor, vendor, "one\n")
    document_id = _document_of(engine, revision_id)
    lease_seconds = 2
    with engine.begin() as connection:
        connection.execute(
            update(Job)
            .where(Job.id == job.id)
            .values(lease_expires_at=func.clock_timestamp() + _interval(lease_seconds))
        )
    before = (_state(engine, document_id), _job_row(engine, job.id))

    holder = engine.connect()
    try:
        holder.begin()
        # Lock the document without changing it; the fence already holds the job row.
        holder.execute(select(Document.id).where(Document.id == document_id).with_for_update())
        with ThreadPoolExecutor(max_workers=1) as pool:
            waiter = pool.submit(_outcome(lambda: _activate_and_succeed(factory, job)))
            _wait_until(lambda: _lock_waiters(engine) >= 1)

            def lease_has_expired() -> bool:
                with engine.connect() as connection:
                    expired: bool = connection.execute(
                        select(Job.lease_expires_at <= func.clock_timestamp()).where(
                            Job.id == job.id
                        )
                    ).scalar_one()
                return expired

            _wait_until(lease_has_expired, timeout=lease_seconds + 2)
            holder.commit()
            result = waiter.result(timeout=WAIT_SECONDS)
    finally:
        holder.close()

    assert isinstance(result, LeaseLostError), result
    assert (_state(engine, document_id), _job_row(engine, job.id)) == before


def test_a_document_lock_held_beyond_the_lock_timeout_raises_the_fixed_error(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext, vendor: UUID
) -> None:
    revision_id, job = _processing(factory, actor, vendor, "one\n")
    document_id = _document_of(engine, revision_id)
    before = _state(engine, document_id)

    holder = engine.connect()
    try:
        holder.begin()
        holder.execute(select(Document.id).where(Document.id == document_id).with_for_update())
        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=1) as pool:
            waiter = pool.submit(_outcome(lambda: _activate_and_succeed(factory, job)))
            result = waiter.result(timeout=LOCK_TIMEOUT_SECONDS + WAIT_SECONDS)
        waited = time.monotonic() - started
    finally:
        holder.rollback()
        holder.close()

    assert isinstance(result, job_store.JobLockTimeoutError), result
    assert waited >= LOCK_TIMEOUT_SECONDS - 0.5
    assert _state(engine, document_id) == before
    assert _job_row(engine, job.id)["status"] == "running"


def test_a_duplicate_activation_by_a_valid_job_writes_nothing(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext, vendor: UUID
) -> None:
    revision_id, job = _processing(factory, actor, vendor, "one\n")
    _activate_and_succeed(factory, job)
    document_id = _document_of(engine, revision_id)
    before = _state(engine, document_id)
    duplicate = _claimed_job(factory, actor, revision_id, worker="w-b")

    result = _activate_and_succeed(factory, duplicate)

    assert result.revision.status is RevisionStatus.ACTIVE and result.superseded is None
    assert _state(engine, document_id) == before
    assert _job_row(engine, duplicate.id)["status"] == "succeeded"


def test_a_job_naming_another_tenants_revision_finds_nothing(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext, vendor: UUID
) -> None:
    revision_id = _create(factory, actor, vendor).revision.id
    document_id = _document_of(engine, revision_id)
    before = _state(engine, document_id)
    intruder = _tenant(engine, "tenant-b")
    job = _claimed_job(factory, intruder, revision_id)

    with (
        pytest.raises(store.RevisionNotFoundError),
        job_store.fenced_transaction(factory, job.lease_token()) as fence,
    ):
        store.start_processing(fence.session, fence.job)
    assert _state(engine, document_id) == before


# --- the worker runtime with test-only handlers ------------------------------------------------


def _ingest(ctx: JobContext) -> None:
    with ctx.fenced() as fence:
        store.start_processing(fence.session, fence.job)
    with ctx.fenced(finish=True) as fence:
        store.activate_revision(fence.session, fence.job)


def _failing_ingest(ctx: JobContext) -> None:
    """The documented failure seam: commit the revision failure, then fail the job."""
    with ctx.fenced() as fence:
        revision_id = UUID(fence.job.payload.as_dict()["revision_id"])
        status = fence.session.scalar(
            select(DocumentRevision.status).where(
                DocumentRevision.tenant_id == fence.job.tenant_id,
                DocumentRevision.id == revision_id,
            )
        )
        if status != RevisionStatus.FAILED.value:
            store.fail_revision(fence.session, fence.job, RevisionFailureCode.INGESTION_FAILED)
    raise PermanentJobError(JobErrorCode.PERMANENT_FAILURE)


def _run_once(factory: sessionmaker[Session], handler: Callable[[JobContext], None]) -> Any:
    return run_worker(
        DatabaseJobStore(factory),
        HandlerRegistry([(KIND, handler)]),
        worker_id="w-run",
        timings=TIMINGS,
        once=True,
    )


def _queued(factory: sessionmaker[Session], actor: ActorContext, revision_id: UUID) -> UUID:
    with transaction(factory) as session:
        return _enqueue_in(session, actor, revision_id).id


def test_the_worker_activates_and_succeeds_atomically(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext, vendor: UUID
) -> None:
    revision_id = _create(factory, actor, vendor).revision.id
    job_id = _queued(factory, actor, revision_id)

    result = _run_once(factory, _ingest)

    assert result.outcome is WorkerOutcome.STOPPED
    document_id = _document_of(engine, revision_id)
    assert _revisions(engine, document_id)[revision_id]["status"] == "active"
    assert _document(engine, document_id)["active_revision_id"] == revision_id
    assert _job_row(engine, job_id)["status"] == "succeeded"
    assert job_store.claim(factory, "w-b", kinds=[KIND]) is None


def test_the_worker_failure_seam_fails_the_revision_then_the_job(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext, vendor: UUID
) -> None:
    first = _create(factory, actor, vendor, _content("one\n")).revision.id
    _queued(factory, actor, first)
    _run_once(factory, _ingest)
    second = _create(factory, actor, vendor, _content("two\n")).revision.id
    job_id = _queued(factory, actor, second)

    _run_once(factory, _failing_ingest)

    document_id = _document_of(engine, first)
    rows = _revisions(engine, document_id)
    assert (rows[second]["status"], rows[second]["failure_reason"]) == (
        "failed",
        "ingestion_failed",
    )
    assert rows[first]["status"] == "active"
    assert _document(engine, document_id)["active_revision_id"] == first
    job = _job_row(engine, job_id)
    assert (job["status"], job["last_error"]) == (JobStatus.FAILED.value, "permanent_failure")


def test_a_reclaimed_job_whose_revision_already_failed_fails_without_rewriting_it(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext, vendor: UUID
) -> None:
    """The separate-commit gap: the revision failure committed, then the worker crashed."""
    revision_id, job = _processing(factory, actor, vendor, "one\n")
    with job_store.fenced_transaction(factory, job.lease_token()) as fence:
        store.fail_revision(fence.session, fence.job, RevisionFailureCode.INGESTION_FAILED)
    with engine.begin() as connection:
        connection.execute(
            update(Job)
            .where(Job.id == job.id)
            .values(lease_expires_at=func.clock_timestamp() - _interval(1))
        )
    document_id = _document_of(engine, revision_id)
    before = _state(engine, document_id)

    _run_once(factory, _failing_ingest)

    assert _state(engine, document_id) == before
    row = _job_row(engine, job.id)
    assert (row["status"], row["attempt"], row["last_error"]) == ("failed", 2, "permanent_failure")
