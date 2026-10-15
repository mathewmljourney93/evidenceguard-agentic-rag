"""PostgreSQL integration tests for chunk storage and the ``ingest_revision`` handler (M3d,
ADR-0010).

They use the guarded disposable-database fixtures from ``conftest.py`` and are skipped without
``EG_TEST_DATABASE_URL`` (required in CI). Every connection carries a server-side
``statement_timeout``; concurrency uses separate connections (``NullPool``), observed lock waits
and bounded waits. The races hold the document lock in the main thread's open fence while the
competing operation waits for it in a worker thread, then release it by committing.
"""

import hashlib
import time
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, Interval, create_engine, func, insert, literal_column, select, text
from sqlalchemy import update as sql_update
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from evidenceguard_domain.chunks import Chunk, ExpectedChunkSet, batches, chunk_id
from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_domain.evidence import SourceType
from evidenceguard_domain.jobs import JobPayload, JobSnapshot, JobStatus, LeaseLostError
from evidenceguard_domain.revisions import RevisionContent, RevisionFailureCode
from evidenceguard_persistence import chunks as chunk_store
from evidenceguard_persistence import documents as revision_store
from evidenceguard_persistence import jobs as job_store
from evidenceguard_persistence.db import create_session_factory, transaction
from evidenceguard_persistence.models import (
    Chunk as ChunkRow,
)
from evidenceguard_persistence.models import (
    ChunkSet,
    DocumentRevision,
    Job,
    Tenant,
    Vendor,
)
from evidenceguard_retrieval.chunking import CHUNKER_VERSION, chunk_revision
from evidenceguard_worker.handlers import production_registry
from evidenceguard_worker.ingest import INGEST_REVISION_KIND
from evidenceguard_worker.runtime import DatabaseJobStore, Timings, run_worker

pytestmark = pytest.mark.integration

FOREIGN_KEY_VIOLATION = "23503"
UNIQUE_VIOLATION = "23505"
CHECK_VIOLATION = "23514"
WAIT_SECONDS = 10
MARKDOWN = "text/markdown"
TEXT = "# Retention\n\nCustomer data is kept for 90 days.\n\n## Backups\n\nBackups are encrypted.\n"
MANY = "".join(f"# Section {index}\n\nParagraph {index}.\n\n" for index in range(450))
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


def _content(text_: str = TEXT) -> RevisionContent:
    return RevisionContent.from_bytes(text_.encode(), MARKDOWN)


def _create(
    factory: sessionmaker[Session], actor: ActorContext, vendor_id: UUID, text_: str = TEXT
) -> UUID:
    with transaction(factory) as session:
        created = revision_store.create_revision(
            session,
            actor,
            vendor_id=vendor_id,
            document_key="data-retention",
            title="Data retention",
            source_type=SourceType.VENDOR_STATEMENT,
            content=_content(text_),
        )
    return created.revision.id


def _enqueue(
    factory: sessionmaker[Session], actor: ActorContext, revision_id: UUID, key: str | None = None
) -> JobSnapshot:
    with transaction(factory) as session:
        return job_store.enqueue(
            session,
            actor,
            kind=INGEST_REVISION_KIND,
            idempotency_key=key or str(revision_id),
            payload=JobPayload.from_mapping({"revision_id": str(revision_id)}),
        )


def _claimed(
    factory: sessionmaker[Session],
    actor: ActorContext,
    revision_id: UUID,
    *,
    key: str | None = None,
    worker: str = "w-a",
) -> JobSnapshot:
    queued = _enqueue(factory, actor, revision_id, key)
    claimed = job_store.claim(factory, worker, kinds=[INGEST_REVISION_KIND])
    assert claimed is not None and claimed.id == queued.id
    return claimed


def _start(factory: sessionmaker[Session], job: JobSnapshot) -> None:
    with job_store.fenced_transaction(factory, job.lease_token()) as fence:
        revision_store.start_processing(fence.session, fence.job)


def _processing(
    factory: sessionmaker[Session], actor: ActorContext, vendor_id: UUID, text_: str = TEXT
) -> tuple[UUID, JobSnapshot, tuple[Chunk, ...]]:
    """A new ``processing`` revision, its claimed job and this attempt's parsed chunks."""
    revision_id = _create(factory, actor, vendor_id, text_)
    job = _claimed(factory, actor, revision_id)
    _start(factory, job)
    chunks = chunk_revision(_content(text_), tenant_id=actor.tenant_id, revision_id=revision_id)
    return revision_id, job, chunks


def _write_set(factory: sessionmaker[Session], job: JobSnapshot, chunks: Sequence[Chunk]) -> None:
    with job_store.fenced_transaction(factory, job.lease_token()) as fence:
        chunk_store.write_chunk_set(fence.session, fence.job, ExpectedChunkSet.of(chunks))


def _write(factory: sessionmaker[Session], job: JobSnapshot, batch: Sequence[Chunk]) -> None:
    with job_store.fenced_transaction(factory, job.lease_token()) as fence:
        chunk_store.write_chunks(fence.session, fence.job, batch)


def _write_all(factory: sessionmaker[Session], job: JobSnapshot, chunks: Sequence[Chunk]) -> None:
    _write_set(factory, job, chunks)
    for batch in batches(chunks):
        _write(factory, job, batch)


def _activate(
    factory: sessionmaker[Session], job: JobSnapshot, expected: ExpectedChunkSet | None
) -> Any:
    with job_store.fenced_transaction(factory, job.lease_token()) as fence:
        check = (
            None
            if expected is None
            else partial(chunk_store.require_complete_chunk_set, expected=expected)
        )
        result = revision_store.activate_revision(fence.session, fence.job, before_settle=check)
        fence.succeed()
    return result


def _fail(factory: sessionmaker[Session], job: JobSnapshot, code: RevisionFailureCode) -> None:
    with job_store.fenced_transaction(factory, job.lease_token()) as fence:
        revision_store.fail_revision(fence.session, fence.job, code)


def _chunk_rows(engine: Engine, revision_id: UUID) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        rows = connection.execute(
            select(ChunkRow.__table__)
            .where(ChunkRow.revision_id == revision_id)
            .order_by(ChunkRow.ordinal)
        ).all()
    return [dict(row._mapping) for row in rows]


def _set_row(engine: Engine, revision_id: UUID) -> dict[str, Any] | None:
    with engine.connect() as connection:
        row = connection.execute(
            select(ChunkSet.__table__).where(ChunkSet.revision_id == revision_id)
        ).first()
    return None if row is None else dict(row._mapping)


def _revision_row(engine: Engine, revision_id: UUID) -> dict[str, Any]:
    with engine.connect() as connection:
        row = connection.execute(
            select(DocumentRevision.__table__).where(DocumentRevision.id == revision_id)
        ).one()
    return dict(row._mapping)


def _job_row(engine: Engine, job_id: UUID) -> dict[str, Any]:
    with engine.connect() as connection:
        row = connection.execute(select(Job.__table__).where(Job.id == job_id)).one()
    return dict(row._mapping)


def _state(engine: Engine, revision_id: UUID) -> tuple[Any, ...]:
    return (
        _revision_row(engine, revision_id),
        _set_row(engine, revision_id),
        _chunk_rows(engine, revision_id),
    )


def _interval(seconds: int) -> Any:
    return literal_column(f"interval '{seconds} seconds'", type_=Interval)


def _expire(engine: Engine, job_id: UUID) -> None:
    with engine.begin() as connection:
        connection.execute(
            sql_update(Job)
            .where(Job.id == job_id)
            .values(lease_expires_at=func.clock_timestamp() - _interval(1))
        )


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


def _run_worker(factory: sessionmaker[Session]) -> Any:
    return run_worker(
        DatabaseJobStore(factory),
        production_registry(),
        worker_id="w-run",
        timings=TIMINGS,
        once=True,
    )


# --- migration and schema ---------------------------------------------------------------------


def test_downgrading_0004_with_chunk_rows_and_upgrading_again(
    engine: Engine,
    factory: sessionmaker[Session],
    actor: ActorContext,
    vendor: UUID,
    config: Config,
) -> None:
    revision_id, job, chunks = _processing(factory, actor, vendor)
    _write_all(factory, job, chunks)

    command.downgrade(config, "0003")
    with engine.connect() as connection:
        tables = set(
            connection.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            ).scalars()
        )
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert not {"chunks", "chunk_sets"} & tables
    assert {"documents", "document_revisions", "jobs"} <= tables and version == "0003"
    assert _revision_row(engine, revision_id)["status"] == "processing"

    command.upgrade(config, "head")
    assert _chunk_rows(engine, revision_id) == [] and _set_row(engine, revision_id) is None


def test_the_chunk_tables_have_no_triggers(engine: Engine) -> None:
    with engine.connect() as connection:
        triggers = connection.execute(
            text(
                "SELECT count(*) FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
                "WHERE c.relname IN ('chunks', 'chunk_sets') AND NOT t.tgisinternal"
            )
        ).scalar_one()
    assert triggers == 0


def _raw_set(engine: Engine, tenant_id: UUID, revision_id: UUID, **overrides: Any) -> None:
    values: dict[str, Any] = {
        "tenant_id": tenant_id,
        "revision_id": revision_id,
        "chunker_version": CHUNKER_VERSION,
        "chunk_count": 1,
        "manifest_sha256": "a" * 64,
    }
    values.update(overrides)
    with engine.begin() as connection:
        connection.execute(insert(ChunkSet).values(**values))


def _raw_chunk(engine: Engine, tenant_id: UUID, revision_id: UUID, **overrides: Any) -> UUID:
    values: dict[str, Any] = {
        "id": uuid4(),
        "tenant_id": tenant_id,
        "revision_id": revision_id,
        "chunker_version": CHUNKER_VERSION,
        "ordinal": 0,
        "text": "Synthetic chunk.",
        "content_sha256": hashlib.sha256(b"Synthetic chunk.").hexdigest(),
        "section_path": [],
        "is_table": False,
        "line_start": 1,
        "line_end": 1,
        "char_start": 0,
        "char_end": 16,
    }
    values.update(overrides)
    with engine.begin() as connection:
        connection.execute(insert(ChunkRow).values(**values))
    chunk: UUID = values["id"]
    return chunk


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"chunker_version": "Bad Version"}, "ck_chunk_sets_chunker_version"),
        ({"chunk_count": 0}, "ck_chunk_sets_chunk_count"),
        ({"chunk_count": 4097}, "ck_chunk_sets_chunk_count"),
        ({"manifest_sha256": "A" * 64}, "ck_chunk_sets_manifest_sha256"),
    ],
)
def test_chunk_set_checks_reject_invalid_rows(
    engine: Engine,
    factory: sessionmaker[Session],
    actor: ActorContext,
    vendor: UUID,
    overrides: dict[str, Any],
    constraint: str,
) -> None:
    revision_id = _create(factory, actor, vendor)
    with pytest.raises(IntegrityError) as info:
        _raw_set(engine, actor.tenant_id, revision_id, **overrides)
    assert (_sqlstate(info.value), _constraint(info.value)) == (CHECK_VIOLATION, constraint)


_HEADER = {
    "is_table": True,
    "header_line_start": 1,
    "header_line_end": 2,
    "header_char_start": 0,
    "header_char_end": 10,
    "line_start": 3,
    "line_end": 3,
    "char_start": 12,
    "char_end": 28,
}


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"ordinal": -1}, "ck_chunks_ordinal"),
        ({"ordinal": 4096}, "ck_chunks_ordinal"),
        ({"text": ""}, "ck_chunks_text_length"),
        ({"text": "x" * 4001}, "ck_chunks_text_length"),
        ({"content_sha256": "not-hex"}, "ck_chunks_content_sha256"),
        ({"section_path": ["a"] * 7}, "ck_chunks_section_path_depth"),
        ({"line_start": 0, "line_end": 0}, "ck_chunks_lines"),
        ({"line_start": 3, "line_end": 2}, "ck_chunks_lines"),
        ({"char_start": -1}, "ck_chunks_chars"),
        ({"char_end": 0}, "ck_chunks_chars"),
        ({**_HEADER, "header_char_end": None}, "ck_chunks_header_all_or_none"),
        ({**_HEADER, "is_table": False}, "ck_chunks_header_only_tables"),
        ({**_HEADER, "header_char_end": 13}, "ck_chunks_header_before_body"),
        ({**_HEADER, "header_line_end": 3}, "ck_chunks_header_before_body"),
    ],
)
def test_chunk_checks_reject_invalid_rows(
    engine: Engine,
    factory: sessionmaker[Session],
    actor: ActorContext,
    vendor: UUID,
    overrides: dict[str, Any],
    constraint: str,
) -> None:
    revision_id = _create(factory, actor, vendor)
    _raw_set(engine, actor.tenant_id, revision_id)
    with pytest.raises(IntegrityError) as info:
        _raw_chunk(engine, actor.tenant_id, revision_id, **overrides)
    assert (_sqlstate(info.value), _constraint(info.value)) == (CHECK_VIOLATION, constraint)


def test_a_valid_repeated_header_row_is_accepted(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext, vendor: UUID
) -> None:
    revision_id = _create(factory, actor, vendor)
    _raw_set(engine, actor.tenant_id, revision_id)
    _raw_chunk(engine, actor.tenant_id, revision_id, **_HEADER)
    assert len(_chunk_rows(engine, revision_id)) == 1


def test_composite_foreign_keys_reject_cross_tenant_and_cross_revision_rows(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext, vendor: UUID
) -> None:
    revision_id = _create(factory, actor, vendor)
    intruder = _tenant(engine, "tenant-b")

    with pytest.raises(IntegrityError) as foreign_set:
        _raw_set(engine, intruder.tenant_id, revision_id)
    assert _sqlstate(foreign_set.value) == FOREIGN_KEY_VIOLATION

    _raw_set(engine, actor.tenant_id, revision_id)
    with pytest.raises(IntegrityError) as foreign_chunk:
        _raw_chunk(engine, intruder.tenant_id, revision_id)
    assert _sqlstate(foreign_chunk.value) == FOREIGN_KEY_VIOLATION
    with pytest.raises(IntegrityError) as other_version:
        _raw_chunk(engine, actor.tenant_id, revision_id, chunker_version="text-md-v2")
    assert _constraint(other_version.value) == (
        "fk_chunks_tenant_id_revision_id_chunker_version_chunk_sets"
    )
    other_revision = _create(factory, actor, vendor, "Another revision.\n")
    with pytest.raises(IntegrityError) as no_set:
        _raw_chunk(engine, actor.tenant_id, other_revision)
    assert _sqlstate(no_set.value) == FOREIGN_KEY_VIOLATION


def test_uniqueness_of_sets_ordinals_and_ids(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext, vendor: UUID
) -> None:
    revision_id = _create(factory, actor, vendor)
    _raw_set(engine, actor.tenant_id, revision_id)
    with pytest.raises(IntegrityError) as second_set:
        _raw_set(engine, actor.tenant_id, revision_id, manifest_sha256="b" * 64)
    # Both unique keys of chunk_sets cover this row; either may be reported first.
    assert _sqlstate(second_set.value) == UNIQUE_VIOLATION
    assert _constraint(second_set.value) in {
        "pk_chunk_sets",
        "uq_chunk_sets_tenant_id_revision_id_chunker_version",
    }
    first = _raw_chunk(engine, actor.tenant_id, revision_id)
    with pytest.raises(IntegrityError) as same_ordinal:
        _raw_chunk(engine, actor.tenant_id, revision_id)
    assert _constraint(same_ordinal.value) == (
        "uq_chunks_tenant_id_revision_id_chunker_version_ordinal"
    )
    with pytest.raises(IntegrityError) as same_id:
        _raw_chunk(engine, actor.tenant_id, revision_id, id=first, ordinal=1)
    assert (_sqlstate(same_id.value), _constraint(same_id.value)) == (UNIQUE_VIOLATION, "pk_chunks")


# --- writes -----------------------------------------------------------------------------------


def test_writes_store_exact_rows_and_repeat_idempotently(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext, vendor: UUID
) -> None:
    revision_id, job, chunks = _processing(factory, actor, vendor)

    _write_all(factory, job, chunks)
    first = _state(engine, revision_id)
    _write_all(factory, job, chunks)

    assert _state(engine, revision_id) == first  # including created_at: nothing rewritten
    rows = first[2]
    assert [row["id"] for row in rows] == [chunk.id for chunk in chunks]
    assert [row["text"] for row in rows] == [chunk.text for chunk in chunks]
    assert [tuple(row["section_path"]) for row in rows] == [chunk.section_path for chunk in chunks]
    assert rows[0]["id"] == chunk_id(actor.tenant_id, revision_id, CHUNKER_VERSION, 0)
    stored_set = first[1]
    assert stored_set is not None
    assert (stored_set["chunk_count"], stored_set["manifest_sha256"]) == (
        len(chunks),
        ExpectedChunkSet.of(chunks).manifest_sha256,
    )
    assert _revision_row(engine, revision_id)["sha256"] == hashlib.sha256(TEXT.encode()).hexdigest()


def test_conflicting_chunks_and_sets_are_refused_and_nothing_is_overwritten(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext, vendor: UUID
) -> None:
    revision_id, job, chunks = _processing(factory, actor, vendor)
    _write_all(factory, job, chunks)
    before = _state(engine, revision_id)
    other = chunk_revision(
        _content(TEXT.replace("90", "30")), tenant_id=actor.tenant_id, revision_id=revision_id
    )

    with pytest.raises(chunk_store.ChunkConflictError):
        _write(factory, job, other)
    with pytest.raises(chunk_store.ChunkConflictError):
        _write_set(factory, job, other)

    assert _state(engine, revision_id) == before


def test_a_suppressed_conflict_on_the_id_whose_tuple_has_no_row_is_a_conflict(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext, vendor: UUID
) -> None:
    """ON CONFLICT DO NOTHING suppresses the primary-key conflict; the expected ordinal has no
    row, which must never count as an idempotent success."""
    revision_id, job, chunks = _processing(factory, actor, vendor)
    _write_set(factory, job, chunks)
    _raw_chunk(engine, actor.tenant_id, revision_id, id=chunks[0].id, ordinal=5)
    before = _chunk_rows(engine, revision_id)

    with pytest.raises(chunk_store.ChunkConflictError):
        _write(factory, job, chunks[:1])

    assert _chunk_rows(engine, revision_id) == before
    assert [row["ordinal"] for row in before] == [5]


def test_a_refused_batch_rolls_back_entirely(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext, vendor: UUID
) -> None:
    revision_id, job, chunks = _processing(factory, actor, vendor, MANY)
    _write_set(factory, job, chunks)
    _raw_chunk(
        engine,
        actor.tenant_id,
        revision_id,
        id=chunks[5].id,
        ordinal=5,
        text="Changed.",
        content_sha256=hashlib.sha256(b"Changed.").hexdigest(),
        char_end=8,
    )

    with pytest.raises(chunk_store.ChunkConflictError):
        _write(factory, job, chunks[:10])  # 0-4 and 6-9 are new; 5 conflicts

    assert [row["ordinal"] for row in _chunk_rows(engine, revision_id)] == [5]


@pytest.mark.parametrize("settled", ["active", "superseded", "failed"])
def test_no_chunk_or_set_is_inserted_after_settlement(
    engine: Engine,
    factory: sessionmaker[Session],
    actor: ActorContext,
    vendor: UUID,
    settled: str,
) -> None:
    revision_id, job, chunks = _processing(factory, actor, vendor)
    if settled == "active":
        _activate(factory, job, None)
    elif settled == "failed":
        _fail(factory, job, RevisionFailureCode.INGESTION_FAILED)
    else:
        _, newer_job, _ = _processing(factory, actor, vendor, "Newer bytes.\n")
        _activate(factory, newer_job, None)
        _activate(factory, job, None)  # the older revision finishes late: superseded
    assert _revision_row(engine, revision_id)["status"] == settled
    writer = _claimed(factory, actor, revision_id, key=str(uuid4()), worker="w-b")
    before = _state(engine, revision_id)

    with pytest.raises(chunk_store.ChunkWriteRefusedError):
        _write_set(factory, writer, chunks)
    with pytest.raises(chunk_store.ChunkWriteRefusedError):
        _write(factory, writer, chunks)

    assert _state(engine, revision_id) == before
    assert before[1] is None and before[2] == []


def test_a_stale_attempt_is_refused_at_writes_and_at_activation(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext, vendor: UUID
) -> None:
    revision_id, stale, chunks = _processing(factory, actor, vendor)
    _expire(engine, stale.id)
    reclaimed = job_store.claim(factory, "w-b", kinds=[INGEST_REVISION_KIND])
    assert reclaimed is not None and reclaimed.attempt == 2
    before = _state(engine, revision_id)

    with pytest.raises(LeaseLostError):
        _write_set(factory, stale, chunks)
    with pytest.raises(LeaseLostError):
        _write(factory, stale, chunks)
    with pytest.raises(LeaseLostError):
        _activate(factory, stale, ExpectedChunkSet.of(chunks))

    assert _state(engine, revision_id) == before


def test_a_lease_expiring_during_the_writers_document_lock_wait_is_refused(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext, vendor: UUID
) -> None:
    revision_id, job, chunks = _processing(factory, actor, vendor)
    _write_set(factory, job, chunks)
    lease_seconds = 2
    with engine.begin() as connection:
        connection.execute(
            sql_update(Job)
            .where(Job.id == job.id)
            .values(lease_expires_at=func.clock_timestamp() + _interval(lease_seconds))
        )
    document_id = _revision_row(engine, revision_id)["document_id"]
    before = _state(engine, revision_id)

    holder = engine.connect()
    try:
        holder.begin()
        holder.execute(
            text("SELECT id FROM documents WHERE id = :id FOR UPDATE"), {"id": document_id}
        )
        with ThreadPoolExecutor(max_workers=1) as pool:
            waiter = pool.submit(_outcome(lambda: _write(factory, job, chunks)))
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
    assert _state(engine, revision_id) == before


# --- races with settlement (two different valid jobs for one revision) -------------------------


def test_a_writer_holding_the_lock_commits_its_batch_before_activation(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext, vendor: UUID
) -> None:
    revision_id, writer, chunks = _processing(factory, actor, vendor, MANY)
    groups = list(batches(chunks))
    _write_set(factory, writer, chunks)
    for batch in groups[:-1]:
        _write(factory, writer, batch)
    activator = _claimed(factory, actor, revision_id, key=str(uuid4()), worker="w-b")
    expected = ExpectedChunkSet.of(chunks)

    with ThreadPoolExecutor(max_workers=1) as pool:
        with job_store.fenced_transaction(factory, writer.lease_token()) as fence:
            chunk_store.write_chunks(fence.session, fence.job, groups[-1])
            waiter = pool.submit(_outcome(lambda: _activate(factory, activator, expected)))
            _wait_until(lambda: _lock_waiters(engine) >= 1)
        result = waiter.result(timeout=WAIT_SECONDS)

    assert not isinstance(result, Exception), result
    assert _revision_row(engine, revision_id)["status"] == "active"
    assert len(_chunk_rows(engine, revision_id)) == len(chunks)
    assert _job_row(engine, activator.id)["status"] == JobStatus.SUCCEEDED.value


def test_a_writer_waiting_behind_activation_is_refused_and_writes_nothing(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext, vendor: UUID
) -> None:
    revision_id, writer, chunks = _processing(factory, actor, vendor)
    _write_all(factory, writer, chunks)
    activator = _claimed(factory, actor, revision_id, key=str(uuid4()), worker="w-b")
    expected = ExpectedChunkSet.of(chunks)
    before_rows = _chunk_rows(engine, revision_id)

    with ThreadPoolExecutor(max_workers=1) as pool:
        with job_store.fenced_transaction(factory, activator.lease_token()) as fence:
            revision_store.activate_revision(
                fence.session,
                fence.job,
                before_settle=partial(chunk_store.require_complete_chunk_set, expected=expected),
            )
            fence.succeed()
            waiter = pool.submit(_outcome(lambda: _write(factory, writer, chunks)))
            _wait_until(lambda: _lock_waiters(engine) >= 1)
        result = waiter.result(timeout=WAIT_SECONDS)

    assert isinstance(result, chunk_store.ChunkWriteRefusedError), result
    assert _revision_row(engine, revision_id)["status"] == "active"
    assert _chunk_rows(engine, revision_id) == before_rows


def test_a_writer_holding_the_lock_commits_its_batch_before_the_failure(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext, vendor: UUID
) -> None:
    revision_id, writer, chunks = _processing(factory, actor, vendor)
    _write_set(factory, writer, chunks)
    failer = _claimed(factory, actor, revision_id, key=str(uuid4()), worker="w-b")

    with ThreadPoolExecutor(max_workers=1) as pool:
        with job_store.fenced_transaction(factory, writer.lease_token()) as fence:
            chunk_store.write_chunks(fence.session, fence.job, chunks)
            waiter = pool.submit(
                _outcome(lambda: _fail(factory, failer, RevisionFailureCode.INGESTION_FAILED))
            )
            _wait_until(lambda: _lock_waiters(engine) >= 1)
        result = waiter.result(timeout=WAIT_SECONDS)

    assert result is None
    assert _revision_row(engine, revision_id)["status"] == "failed"
    assert len(_chunk_rows(engine, revision_id)) == len(chunks)  # committed before the failure


def test_a_writer_waiting_behind_a_failure_is_refused_and_writes_nothing(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext, vendor: UUID
) -> None:
    revision_id, writer, chunks = _processing(factory, actor, vendor)
    _write_set(factory, writer, chunks)
    failer = _claimed(factory, actor, revision_id, key=str(uuid4()), worker="w-b")

    with ThreadPoolExecutor(max_workers=1) as pool:
        with job_store.fenced_transaction(factory, failer.lease_token()) as fence:
            revision_store.fail_revision(
                fence.session, fence.job, RevisionFailureCode.INGESTION_FAILED
            )
            waiter = pool.submit(_outcome(lambda: _write(factory, writer, chunks)))
            _wait_until(lambda: _lock_waiters(engine) >= 1)
        result = waiter.result(timeout=WAIT_SECONDS)

    assert isinstance(result, chunk_store.ChunkWriteRefusedError), result
    assert _revision_row(engine, revision_id)["status"] == "failed"
    assert _chunk_rows(engine, revision_id) == []


# --- completeness and the atomic finish --------------------------------------------------------


def test_activation_is_refused_while_the_set_is_incomplete(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext, vendor: UUID
) -> None:
    revision_id, job, chunks = _processing(factory, actor, vendor, MANY)
    _write_set(factory, job, chunks)
    _write(factory, job, next(batches(chunks)))
    before = (_state(engine, revision_id), _job_row(engine, job.id))

    with pytest.raises(chunk_store.ChunkSetIncompleteError):
        _activate(factory, job, ExpectedChunkSet.of(chunks))

    assert (_state(engine, revision_id), _job_row(engine, job.id)) == before
    assert before[1]["status"] == "running"


def test_activation_is_refused_when_the_stored_set_differs_from_the_attempts(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext, vendor: UUID
) -> None:
    revision_id, job, chunks = _processing(factory, actor, vendor)
    _write_all(factory, job, chunks)
    other = chunk_revision(
        _content(TEXT + "\nExtra.\n"), tenant_id=actor.tenant_id, revision_id=revision_id
    )
    before = (_state(engine, revision_id), _job_row(engine, job.id))

    with pytest.raises(chunk_store.ChunkSetIncompleteError):
        _activate(factory, job, ExpectedChunkSet.of(other))

    assert (_state(engine, revision_id), _job_row(engine, job.id)) == before


def test_activation_and_job_success_commit_together_or_not_at_all(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext, vendor: UUID
) -> None:
    revision_id, job, chunks = _processing(factory, actor, vendor)
    _write_all(factory, job, chunks)
    expected = ExpectedChunkSet.of(chunks)
    before = (_state(engine, revision_id), _job_row(engine, job.id))

    class Boom(Exception):
        pass

    with (
        pytest.raises(Boom),
        job_store.fenced_transaction(factory, job.lease_token()) as fence,
    ):
        revision_store.activate_revision(
            fence.session,
            fence.job,
            before_settle=partial(chunk_store.require_complete_chunk_set, expected=expected),
        )
        raise Boom()  # fails before the job's success is recorded
    assert (_state(engine, revision_id), _job_row(engine, job.id)) == before

    _activate(factory, job, expected)
    assert _revision_row(engine, revision_id)["status"] == "active"
    assert _job_row(engine, job.id)["status"] == "succeeded"


# --- the registered production handler ---------------------------------------------------------


def test_the_production_handler_ingests_and_activates_a_revision(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext, vendor: UUID
) -> None:
    revision_id = _create(factory, actor, vendor)
    job = _enqueue(factory, actor, revision_id)

    _run_worker(factory)

    revision = _revision_row(engine, revision_id)
    assert revision["status"] == "active"
    rows = _chunk_rows(engine, revision_id)
    expected = chunk_revision(_content(), tenant_id=actor.tenant_id, revision_id=revision_id)
    assert [(row["id"], row["text"]) for row in rows] == [(c.id, c.text) for c in expected]
    assert _job_row(engine, job.id)["status"] == "succeeded"


def test_a_crash_after_some_batches_is_resumed_by_the_next_attempt(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext, vendor: UUID
) -> None:
    revision_id, job, chunks = _processing(factory, actor, vendor, MANY)
    assert len(list(batches(chunks))) == 3
    _write_set(factory, job, chunks)
    _write(factory, job, next(batches(chunks)))
    _expire(engine, job.id)  # the first attempt crashed after one batch

    _run_worker(factory)

    assert len(_chunk_rows(engine, revision_id)) == len(chunks) == 450
    assert _revision_row(engine, revision_id)["status"] == "active"
    row = _job_row(engine, job.id)
    assert (row["status"], row["attempt"]) == ("succeeded", 2)


def test_an_empty_document_fails_the_revision_then_the_job(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext, vendor: UUID
) -> None:
    revision_id = _create(factory, actor, vendor, " \t\n\n  \n")
    job = _enqueue(factory, actor, revision_id)

    _run_worker(factory)

    revision = _revision_row(engine, revision_id)
    assert (revision["status"], revision["failure_reason"]) == ("failed", "empty_document")
    row = _job_row(engine, job.id)
    assert (row["status"], row["last_error"]) == ("failed", "permanent_failure")
    assert _set_row(engine, revision_id) is None and _chunk_rows(engine, revision_id) == []


def test_the_permanent_failure_crash_gap_is_closed_on_reclaim(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext, vendor: UUID
) -> None:
    """The revision failure committed, then the worker crashed before failing the job."""
    revision_id, job, _ = _processing(factory, actor, vendor)
    _fail(factory, job, RevisionFailureCode.EMPTY_DOCUMENT)
    _expire(engine, job.id)
    before = _state(engine, revision_id)

    _run_worker(factory)

    assert _state(engine, revision_id) == before
    row = _job_row(engine, job.id)
    assert (row["status"], row["attempt"], row["last_error"]) == (
        "failed",
        2,
        "permanent_failure",
    )


def test_a_duplicate_job_for_an_active_revision_succeeds_without_writing(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext, vendor: UUID
) -> None:
    revision_id = _create(factory, actor, vendor)
    _enqueue(factory, actor, revision_id)
    _run_worker(factory)
    before = _state(engine, revision_id)
    duplicate = _enqueue(factory, actor, revision_id, key=str(uuid4()))

    _run_worker(factory)

    assert _state(engine, revision_id) == before
    assert _job_row(engine, duplicate.id)["status"] == "succeeded"


def test_a_job_naming_another_tenants_revision_fails_without_touching_it(
    engine: Engine, factory: sessionmaker[Session], actor: ActorContext, vendor: UUID
) -> None:
    revision_id = _create(factory, actor, vendor)
    before = _state(engine, revision_id)
    intruder = _tenant(engine, "tenant-b")
    job = _enqueue(factory, intruder, revision_id)

    _run_worker(factory)

    assert _state(engine, revision_id) == before
    row = _job_row(engine, job.id)
    assert (row["status"], row["last_error"]) == ("failed", "permanent_failure")
