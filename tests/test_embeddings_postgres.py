"""PostgreSQL integration tests for embedding persistence (M4b, ADR-0014).

They use the guarded disposable-database fixtures from ``conftest.py`` and are skipped without
``EG_TEST_DATABASE_URL`` (required in CI). Every connection carries a server-side
``statement_timeout``. Revisions are ingested by the real worker; vector writes and readiness
run only inside real ``enqueue`` → ``claim`` → ``fenced_transaction`` fences of kind
``index_revision`` (no handler is registered). Races use separate connections (``NullPool``),
assert that the competing operation was actually observed waiting on a lock, and use bounded
waits.
"""

import hashlib
import math
import struct
import time
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import (
    Engine,
    Interval,
    Table,
    create_engine,
    delete,
    func,
    insert,
    literal_column,
    select,
    text,
)
from sqlalchemy import update as sql_update
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_domain.embedding_storage import (
    STORED_DIMS,
    StoredEmbedding,
    StoredVector,
    canonical_vector,
    decode_wire,
    stored_embeddings,
    vector_manifest_sha256,
)
from evidenceguard_domain.embeddings import (
    EmbeddingBatch,
    EmbeddingIdentity,
    EmbeddingUsage,
    InvalidEmbeddingError,
)
from evidenceguard_domain.evidence import SourceType
from evidenceguard_domain.jobs import JobPayload, JobSnapshot, JobStatus, LeaseLostError
from evidenceguard_domain.revisions import RevisionContent
from evidenceguard_persistence import documents as revision_store
from evidenceguard_persistence import embeddings as store
from evidenceguard_persistence import jobs as job_store
from evidenceguard_persistence.db import create_session_factory, transaction
from evidenceguard_persistence.models import (
    Chunk as ChunkRow,
)
from evidenceguard_persistence.models import (
    ChunkEmbedding,
    EmbeddingIndex,
    EmbeddingProfile,
    Job,
    Tenant,
    Vendor,
)
from evidenceguard_retrieval.embeddings import HASH_IDENTITY, HashingEmbedder
from evidenceguard_worker.handlers import production_registry
from evidenceguard_worker.runtime import DatabaseJobStore, Timings, run_worker

pytestmark = pytest.mark.integration

NOT_NULL_VIOLATION = "23502"
FOREIGN_KEY_VIOLATION = "23503"
CHECK_VIOLATION = "23514"
WAIT_SECONDS = 10
MARKDOWN = "text/markdown"
TEXT = "# Retention\n\nCustomer data is kept for 90 days.\n\n## Backups\n\nBackups are encrypted.\n"
OTHER_TEXT = "# Access\n\nAccess reviews happen quarterly.\n\n## Logging\n\nLogs are kept.\n"
LIVE = EmbeddingIdentity("voyage", "voyage-4-lite", "adapter-v1", 1024, "l2")
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
def revision(factory: sessionmaker[Session], engine: Engine, actor: ActorContext) -> UUID:
    """An active revision with two verified chunks, ingested by the real worker."""
    return _ingest(factory, engine, actor, "data-retention", TEXT)


# --- helpers -------------------------------------------------------------------------------


def _tenant(engine: Engine, slug: str) -> ActorContext:
    tenant_id = uuid4()
    with engine.begin() as connection:
        connection.execute(insert(Tenant).values(id=tenant_id, slug=slug, name=slug.title()))
        connection.execute(
            insert(Vendor).values(id=uuid4(), tenant_id=tenant_id, slug="lumenvale", name="L")
        )
    return ActorContext(tenant_id=tenant_id, actor_id=uuid4(), role=Role.REVIEWER)


def _vendor(engine: Engine, tenant_id: UUID) -> UUID:
    with engine.connect() as connection:
        vendor: UUID = connection.execute(
            select(Vendor.id).where(Vendor.tenant_id == tenant_id)
        ).scalar_one()
    return vendor


def _ingest(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, key: str, text_: str
) -> UUID:
    with transaction(factory) as session:
        created = revision_store.create_revision(
            session,
            actor,
            vendor_id=_vendor(engine, actor.tenant_id),
            document_key=key,
            title=key.replace("-", " ").title(),
            source_type=SourceType.VENDOR_STATEMENT,
            content=RevisionContent.from_bytes(text_.encode(), MARKDOWN),
        )
        job_store.enqueue(
            session,
            actor,
            kind="ingest_revision",
            idempotency_key=str(created.revision.id),
            payload=JobPayload.from_mapping({"revision_id": str(created.revision.id)}),
        )
    run_worker(
        DatabaseJobStore(factory),
        production_registry(),
        worker_id="w-ingest",
        timings=TIMINGS,
        once=True,
    )
    return created.revision.id


def _chunks(engine: Engine, revision_id: UUID) -> list[Any]:
    with engine.connect() as connection:
        return list(
            connection.execute(
                select(
                    ChunkRow.id,
                    ChunkRow.ordinal,
                    ChunkRow.text,
                    ChunkRow.content_sha256,
                    ChunkRow.chunker_version,
                )
                .where(ChunkRow.revision_id == revision_id)
                .order_by(ChunkRow.ordinal)
            )
        )


def _rows(engine: Engine, revision_id: UUID) -> tuple[StoredEmbedding, ...]:
    chunks = _chunks(engine, revision_id)
    batch = HashingEmbedder().embed(tuple(chunk.text for chunk in chunks), "document")
    return stored_embeddings(
        batch,
        identity=HASH_IDENTITY,
        chunks=[(chunk.id, chunk.content_sha256) for chunk in chunks],
    )


def _index(
    factory: sessionmaker[Session],
    actor: ActorContext,
    revision_id: UUID,
    identity: EmbeddingIdentity = HASH_IDENTITY,
) -> store.IndexSnapshot:
    with transaction(factory) as session:
        profile = store.ensure_profile(session, actor.tenant_id, identity)
        return store.create_index(session, actor.tenant_id, revision_id, profile)


def _job(
    factory: sessionmaker[Session],
    actor: ActorContext,
    *,
    kind: str = store.INDEX_REVISION_KIND,
    payload: dict[str, str],
    key: str | None = None,
    worker: str = "w-index",
) -> JobSnapshot:
    with transaction(factory) as session:
        queued = job_store.enqueue(
            session,
            actor,
            kind=kind,
            idempotency_key=key or str(uuid4()),
            payload=JobPayload.from_mapping(payload),
        )
    claimed = job_store.claim(factory, worker, kinds=[kind])
    assert claimed is not None and claimed.id == queued.id
    return claimed


def _index_job(
    factory: sessionmaker[Session], actor: ActorContext, index: store.IndexSnapshot, **kw: Any
) -> JobSnapshot:
    return _job(factory, actor, payload={"index_id": str(index.id)}, **kw)


def _write(
    factory: sessionmaker[Session],
    job: JobSnapshot,
    rows: Sequence[StoredEmbedding],
    identity: EmbeddingIdentity = HASH_IDENTITY,
) -> None:
    with job_store.fenced_transaction(factory, job.lease_token()) as fence:
        store.write_embeddings(fence.session, fence.job, identity, rows)


def _ready(
    factory: sessionmaker[Session], job: JobSnapshot, *, succeed: bool = False
) -> store.IndexSnapshot:
    with job_store.fenced_transaction(factory, job.lease_token()) as fence:
        result = store.mark_index_ready(fence.session, fence.job, HASH_IDENTITY)
        if succeed:
            fence.succeed()
    return result


def _embedding_rows(engine: Engine, index_id: UUID) -> list[dict[str, Any]]:
    table = ChunkEmbedding.__table__
    with engine.connect() as connection:
        rows = connection.execute(
            select(
                table.c.chunk_id,
                table.c.content_sha256,
                table.c.vector_sha256,
                table.c.is_zero,
                func.vector_send(table.c.embedding).label("wire"),
                func.vector_norm(table.c.embedding).label("norm"),
                func.encode(func.sha256(func.vector_send(table.c.embedding)), "hex").label(
                    "db_sha256"
                ),
            )
            .where(table.c.index_id == index_id)
            .order_by(table.c.chunk_id)
        ).all()
    return [dict(row._mapping) for row in rows]


def _index_row(engine: Engine, index_id: UUID) -> dict[str, Any]:
    with engine.connect() as connection:
        row = connection.execute(
            select(EmbeddingIndex.__table__).where(EmbeddingIndex.id == index_id)
        ).one()
    return dict(row._mapping)


def _job_row(engine: Engine, job_id: UUID) -> dict[str, Any]:
    with engine.connect() as connection:
        row = connection.execute(select(Job.__table__).where(Job.id == job_id)).one()
    return dict(row._mapping)


def _state(engine: Engine, index_id: UUID) -> tuple[Any, ...]:
    return _index_row(engine, index_id), _embedding_rows(engine, index_id)


def _extensions(engine: Engine) -> dict[str, str]:
    with engine.connect() as connection:
        rows = connection.execute(text("SELECT extname, extversion FROM pg_extension")).all()
    return {row.extname: row.extversion for row in rows}


def _tables(engine: Engine) -> set[str]:
    with engine.connect() as connection:
        return set(
            connection.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            ).scalars()
        )


def _sqlstate(error: DBAPIError) -> str | None:
    return getattr(error.orig, "sqlstate", None)


def _constraint(error: DBAPIError) -> str | None:
    return getattr(getattr(error.orig, "diag", None), "constraint_name", None)


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


def _literal(values: Sequence[float]) -> str:
    return "[" + ",".join(repr(value) for value in values) + "]"


def _axis(value: float, index: int = 0) -> tuple[float, ...]:
    return tuple(value if i == index else 0.0 for i in range(STORED_DIMS))


def _unit(*leading: float) -> tuple[float, ...]:
    values = list(leading) + [0.0] * (STORED_DIMS - len(leading))
    norm = math.hypot(*values)
    return tuple(value / norm for value in values)


# --- migration and the extension lifecycle --------------------------------------------------


def test_extension_lifecycle_absent_head_retained_after_downgrade_and_reupgrade(
    empty_database: Engine, config: Config
) -> None:
    assert set(_extensions(empty_database)) == {"plpgsql"}  # fresh reset database

    command.upgrade(config, "head")
    extensions = _extensions(empty_database)
    assert set(extensions) == {"plpgsql", "vector"}
    assert extensions["vector"] == "0.8.7"  # the pinned CI image

    command.downgrade(config, "0004")
    assert set(_extensions(empty_database)) == {"plpgsql", "vector"}  # deliberately retained
    tables = _tables(empty_database)
    assert not {"embedding_profiles", "embedding_indexes", "chunk_embeddings"} & tables
    with empty_database.connect() as connection:
        columns = set(
            connection.execute(
                text(
                    "SELECT column_name FROM information_schema.columns WHERE table_name = 'chunks'"
                )
            ).scalars()
        )
        constraints = set(connection.execute(text("SELECT conname FROM pg_constraint")).scalars())
        indexes = set(connection.execute(text("SELECT indexname FROM pg_indexes")).scalars())
    assert "search_vector" not in columns
    assert not {"uq_chunks_membership", "uq_chunk_sets_binding"} & constraints
    assert "ix_chunks_search_vector" not in indexes

    command.upgrade(config, "head")  # IF NOT EXISTS with the retained extension
    assert {"embedding_profiles", "embedding_indexes", "chunk_embeddings"} <= _tables(
        empty_database
    )


def test_a_preinstalled_extension_and_unrelated_vector_objects_survive(
    empty_database: Engine, config: Config
) -> None:
    with empty_database.begin() as connection:
        connection.execute(text("CREATE EXTENSION vector"))
        connection.execute(text("CREATE TABLE unrelated_probe (v vector(3) NOT NULL)"))
        connection.execute(text("INSERT INTO unrelated_probe VALUES ('[1,2,3]')"))

    command.upgrade(config, "head")
    command.downgrade(config, "0004")
    with empty_database.connect() as connection:
        survived = connection.execute(text("SELECT v::text FROM unrelated_probe")).scalars().all()
    assert survived == ["[1,2,3]"]
    assert "vector" in _extensions(empty_database)

    command.upgrade(config, "head")
    command.downgrade(config, "base")
    with empty_database.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM unrelated_probe")).scalar_one() == 1
    assert "vector" in _extensions(empty_database)


# --- generated full text --------------------------------------------------------------------


def test_search_vector_is_the_simple_tsvector_of_the_exact_text(
    engine: Engine, revision: UUID
) -> None:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT search_vector::text = to_tsvector('simple'::regconfig, text)::text, "
                "search_vector @@ to_tsquery('simple', 'customer') "
                "FROM chunks WHERE revision_id = :revision ORDER BY ordinal"
            ),
            {"revision": revision},
        ).all()
    assert [row[0] for row in rows] == [True, True]
    assert [row[1] for row in rows] == [True, False]


# --- metadata -----------------------------------------------------------------------------


def test_profiles_and_indexes_are_idempotent_and_start_building(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, revision: UUID
) -> None:
    first = _index(factory, actor, revision)
    again = _index(factory, actor, revision)
    assert first == again
    row = _index_row(engine, first.id)
    assert row["status"] == "building"
    assert row["ready_at"] is None and row["vector_manifest_sha256"] is None
    with engine.connect() as connection:
        assert connection.execute(select(func.count()).select_from(EmbeddingProfile)).scalar() == 1


def test_an_index_needs_an_activated_revision(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext
) -> None:
    with transaction(factory) as session:
        pending = revision_store.create_revision(
            session,
            actor,
            vendor_id=_vendor(engine, actor.tenant_id),
            document_key="never-ingested",
            title="Never ingested",
            source_type=SourceType.VENDOR_STATEMENT,
            content=RevisionContent.from_bytes(TEXT.encode(), MARKDOWN),
        ).revision.id
    with pytest.raises(store.IndexSourceNotEligibleError), transaction(factory) as session:
        profile = store.ensure_profile(session, actor.tenant_id, HASH_IDENTITY)
        store.create_index(session, actor.tenant_id, pending, profile)


def test_another_tenants_revision_is_not_eligible(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, revision: UUID
) -> None:
    other = _tenant(engine, "tenant-b")
    with pytest.raises(store.IndexSourceNotEligibleError), transaction(factory) as session:
        profile = store.ensure_profile(session, other.tenant_id, HASH_IDENTITY)
        store.create_index(session, other.tenant_id, revision, profile)


# --- fenced writes, replay and readiness -------------------------------------------------


def test_write_replay_and_readiness_with_atomic_job_success(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, revision: UUID
) -> None:
    index = _index(factory, actor, revision)
    job = _index_job(factory, actor, index)
    rows = _rows(engine, revision)

    _write(factory, job, rows[:1])
    partial = _index_row(engine, index.id)
    assert partial["status"] == "building"
    with pytest.raises(store.IndexIncompleteError):
        _ready(factory, job)
    assert _index_row(engine, index.id) == partial  # partial stays building

    _write(factory, job, rows)  # the first row is an identical replay
    _write(factory, job, rows)  # a full identical replay is a no-op
    stored = _embedding_rows(engine, index.id)
    assert len(stored) == 2

    result = _ready(factory, job, succeed=True)
    row = _index_row(engine, index.id)
    assert result.status == row["status"] == "ready" and row["ready_at"] is not None
    chunks = _chunks(engine, revision)
    by_id = {row.chunk_id: row for row in rows}
    assert row["vector_manifest_sha256"] == vector_manifest_sha256(
        (c.ordinal, c.id, c.content_sha256, by_id[c.id].vector.sha256) for c in chunks
    )
    assert _job_row(engine, job.id)["status"] == JobStatus.SUCCEEDED.value


def test_a_conflicting_replay_never_overwrites(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, revision: UUID
) -> None:
    index = _index(factory, actor, revision)
    job = _index_job(factory, actor, index)
    rows = _rows(engine, revision)
    _write(factory, job, rows)
    before = _state(engine, index.id)

    changed = StoredEmbedding(
        rows[0].chunk_id, rows[0].content_sha256, StoredVector(_axis(1.0, 7), allows_zero=True)
    )
    with pytest.raises(store.EmbeddingConflictError):
        _write(factory, job, [changed])
    assert _state(engine, index.id) == before


def test_a_ready_index_refuses_writes_and_readiness_is_an_idempotent_no_op(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, revision: UUID
) -> None:
    index = _index(factory, actor, revision)
    job = _index_job(factory, actor, index)
    rows = _rows(engine, revision)
    _write(factory, job, rows)
    _ready(factory, job)
    ready = _state(engine, index.id)

    with pytest.raises(store.EmbeddingWriteRefusedError):
        _write(factory, job, rows)
    assert _ready(factory, job).status == "ready"
    assert _state(engine, index.id) == ready  # nothing changes, ready_at included


def test_readiness_rolls_back_with_a_failed_job_success(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, revision: UUID
) -> None:
    index = _index(factory, actor, revision)
    job = _index_job(factory, actor, index)
    _write(factory, job, _rows(engine, revision))

    with (
        pytest.raises(LeaseLostError),
        job_store.fenced_transaction(factory, job.lease_token()) as fence,
    ):
        store.mark_index_ready(fence.session, fence.job, HASH_IDENTITY)
        # Test-only: expire this attempt's lease inside the same transaction, so the fence's
        # own fresh-time check in ``succeed`` fails after readiness was written.
        fence.session.execute(
            sql_update(Job)
            .where(Job.id == job.id)
            .values(lease_expires_at=func.clock_timestamp() - _interval(1))
        )
        fence.succeed()
    assert _index_row(engine, index.id)["status"] == "building"  # rolled back together
    assert _job_row(engine, job.id)["status"] == JobStatus.RUNNING.value


def test_an_error_after_a_write_rolls_the_batch_back(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, revision: UUID
) -> None:
    index = _index(factory, actor, revision)
    job = _index_job(factory, actor, index)
    with (
        pytest.raises(RuntimeError),
        job_store.fenced_transaction(factory, job.lease_token()) as fence,
    ):
        store.write_embeddings(fence.session, fence.job, HASH_IDENTITY, _rows(engine, revision))
        raise RuntimeError("simulated failure after the write")
    assert _embedding_rows(engine, index.id) == []


def test_an_application_rejected_batch_leaves_the_database_unchanged(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, revision: UUID
) -> None:
    index = _index(factory, actor, revision)
    job = _index_job(factory, actor, index, worker="w-live")
    before = _state(engine, index.id)
    chunk = _chunks(engine, revision)[0]

    provider = EmbeddingBatch(LIVE, "document", (_axis(0.999999001),), EmbeddingUsage(None))
    with pytest.raises(InvalidEmbeddingError):
        stored_embeddings(provider, identity=LIVE, chunks=[(chunk.id, chunk.content_sha256)])

    forged = StoredEmbedding(
        chunk.id, chunk.content_sha256, StoredVector(_axis(1.0), allows_zero=True)
    )
    object.__setattr__(forged.vector, "coordinates", _axis(0.5))
    with pytest.raises(InvalidEmbeddingError):
        _write(factory, job, [forged])
    assert _state(engine, index.id) == before


# --- job binding --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "payload"),
    [
        ("index_other", "index"),
        (store.INDEX_REVISION_KIND, "revision"),
        (store.INDEX_REVISION_KIND, "extra"),
    ],
)
def test_a_job_that_does_not_name_the_index_is_refused(
    factory: sessionmaker[Session],
    engine: Engine,
    actor: ActorContext,
    revision: UUID,
    kind: str,
    payload: str,
) -> None:
    index = _index(factory, actor, revision)
    values = {
        "index": {"index_id": str(index.id)},
        "revision": {"revision_id": str(revision)},
        "extra": {"index_id": str(index.id), "revision_id": str(revision)},
    }[payload]
    job = _job(factory, actor, kind=kind, payload=values)
    before = _state(engine, index.id)
    with pytest.raises(store.IndexJobMismatchError):
        _write(factory, job, _rows(engine, revision))
    with pytest.raises(store.IndexJobMismatchError):
        _ready(factory, job)
    assert _state(engine, index.id) == before


def test_an_unknown_index_is_not_found(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, revision: UUID
) -> None:
    job = _job(factory, actor, payload={"index_id": str(uuid4())})
    with pytest.raises(store.IndexNotFoundError):
        _write(factory, job, _rows(engine, revision))


def test_a_foreign_tenants_index_is_not_found_and_never_locked(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, revision: UUID
) -> None:
    index = _index(factory, actor, revision)
    other = _tenant(engine, "tenant-b")
    foreign_job = _job(factory, other, payload={"index_id": str(index.id)})
    with engine.connect() as holder, holder.begin():
        holder.execute(
            select(EmbeddingIndex.id).where(EmbeddingIndex.id == index.id).with_for_update()
        )
        started = time.monotonic()
        with pytest.raises(store.IndexNotFoundError):
            _ready(factory, foreign_job)
        assert time.monotonic() - started < 2  # no wait on tenant A's locked row


# --- races, leases and lock timeouts -------------------------------------------------------


def test_concurrent_writers_serialise_on_the_index_row(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, revision: UUID
) -> None:
    index = _index(factory, actor, revision)
    first = _index_job(factory, actor, index, worker="w-1")
    second = _index_job(factory, actor, index, worker="w-2")
    rows = _rows(engine, revision)
    changed = StoredEmbedding(
        rows[0].chunk_id, rows[0].content_sha256, StoredVector(_axis(1.0, 9), allows_zero=True)
    )

    with ThreadPoolExecutor(max_workers=1) as pool:
        with job_store.fenced_transaction(factory, first.lease_token()) as fence:
            store.write_embeddings(fence.session, fence.job, HASH_IDENTITY, rows)
            competing = pool.submit(_outcome(lambda: _write(factory, second, [changed])))
            _wait_until(lambda: _lock_waiters(engine) >= 1)  # observed waiting on the lock
            assert not competing.done()
        result = competing.result(timeout=WAIT_SECONDS)
    assert isinstance(result, store.EmbeddingConflictError)  # saw the committed row
    stored = {row["chunk_id"]: row["vector_sha256"] for row in _embedding_rows(engine, index.id)}
    assert stored[rows[0].chunk_id] == rows[0].vector.sha256


def test_a_stale_lease_after_waiting_on_an_already_ready_index_is_lease_loss(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, revision: UUID
) -> None:
    index = _index(factory, actor, revision)
    job = _index_job(factory, actor, index)
    _write(factory, job, _rows(engine, revision))
    _ready(factory, job)

    # The waiting fence will hold the job row, so shorten the lease *before* it starts: it is
    # valid when the fence opens and expires while the fence waits on the index lock.
    with engine.begin() as connection:
        connection.execute(
            sql_update(Job)
            .where(Job.id == job.id)
            .values(lease_expires_at=func.clock_timestamp() + _interval(2))
        )

    def lease_expired() -> bool:
        with engine.connect() as connection:
            expired: bool = connection.execute(
                select(func.clock_timestamp() > Job.lease_expires_at).where(Job.id == job.id)
            ).scalar_one()
        return expired

    with ThreadPoolExecutor(max_workers=1) as pool:
        with engine.connect() as holder, holder.begin():
            holder.execute(
                select(EmbeddingIndex.id).where(EmbeddingIndex.id == index.id).with_for_update()
            )
            waiting = pool.submit(_outcome(lambda: _ready(factory, job, succeed=True)))
            _wait_until(lambda: _lock_waiters(engine) >= 1)  # the fence is waiting on the index
            _wait_until(lease_expired)  # and its lease has now expired in database time
            assert not waiting.done()
        outcome = waiting.result(timeout=WAIT_SECONDS)
    assert isinstance(outcome, LeaseLostError)  # the already-ready no-op re-checked ownership
    assert _job_row(engine, job.id)["status"] == JobStatus.RUNNING.value


def test_a_lock_wait_past_the_fence_timeout_is_a_lock_timeout(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, revision: UUID
) -> None:
    index = _index(factory, actor, revision)
    job = _index_job(factory, actor, index)
    with engine.connect() as holder, holder.begin():
        holder.execute(
            select(EmbeddingIndex.id).where(EmbeddingIndex.id == index.id).with_for_update()
        )
        with pytest.raises(job_store.JobLockTimeoutError):
            _write(factory, job, _rows(engine, revision))
    assert _embedding_rows(engine, index.id) == []


def test_an_expired_lease_admits_no_write(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, revision: UUID
) -> None:
    index = _index(factory, actor, revision)
    job = _index_job(factory, actor, index)
    _expire(engine, job.id)
    with pytest.raises(LeaseLostError):
        _write(factory, job, _rows(engine, revision))
    assert _embedding_rows(engine, index.id) == []


# --- constraints, by direct SQL (test-only; no production path writes this way) --------------

PROFILES = cast(Table, EmbeddingProfile.__table__)
INDEXES = cast(Table, EmbeddingIndex.__table__)
EMBEDDINGS = cast(Table, ChunkEmbedding.__table__)


def _rejected(engine: Engine, table: Any, values: dict[str, Any]) -> DBAPIError:
    with pytest.raises(DBAPIError) as info, engine.begin() as connection:
        connection.execute(insert(table).values(**values))
    return info.value


def _row_values(
    index: store.IndexSnapshot, chunk: Any, vector: StoredVector, **changes: Any
) -> dict[str, Any]:
    values = {
        "tenant_id": index.tenant_id,
        "index_id": index.id,
        "chunk_id": chunk.id,
        "revision_id": index.revision_id,
        "chunker_version": index.chunker_version,
        "allows_zero_vectors": index.allows_zero_vectors,
        "content_sha256": chunk.content_sha256,
        "embedding": vector.literal(),
        "vector_sha256": vector.sha256,
        "is_zero": vector.is_zero,
    }
    values.update(changes)
    return values


def _profile_values(tenant_id: UUID, **changes: Any) -> dict[str, Any]:
    other = EmbeddingIdentity("other", "model-a", "v1", 1024, "l2")
    values = {
        "id": uuid4(),
        "tenant_id": tenant_id,
        "provider_id": other.provider_id,
        "model_id": other.model_id,
        "algorithm_version": other.algorithm_version,
        "dims": 1024,
        "normalization": "l2",
        "fingerprint": other.fingerprint,
        "allows_zero_vectors": False,
    }
    values.update(changes)
    return values


def _index_values(index: store.IndexSnapshot, **changes: Any) -> dict[str, Any]:
    values = {name: getattr(index, name) for name in store.INDEX_BINDING_FIELDS}
    values["id"] = uuid4()
    values.update(changes)
    return values


def _wire_sha256(values: Sequence[float]) -> str:
    packed = struct.pack(f">HH{len(values)}f", len(values), 0, *values)
    return hashlib.sha256(packed).hexdigest()


@pytest.fixture
def setup(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, revision: UUID
) -> tuple[store.IndexSnapshot, store.IndexSnapshot, list[Any]]:
    """An offline (zero-permitting) and a live index over the same revision, and its chunks."""
    return (
        _index(factory, actor, revision),
        _index(factory, actor, revision, LIVE),
        _chunks(engine, revision),
    )


def test_required_columns_reject_null(engine: Engine, setup: Any, actor: ActorContext) -> None:
    offline, live, chunks = setup
    vector = canonical_vector(_axis(1.0), allows_zero=True)
    _free(engine, live)  # its binding becomes a valid, not-yet-stored index row
    cases: list[tuple[Any, dict[str, Any], tuple[str, ...]]] = [
        (
            PROFILES,
            _profile_values(actor.tenant_id),
            (
                "id",
                "tenant_id",
                "provider_id",
                "model_id",
                "algorithm_version",
                "dims",
                "normalization",
                "fingerprint",
                "allows_zero_vectors",
                "created_at",
            ),
        ),
        (
            INDEXES,
            _index_values(live),
            (
                "id",
                "tenant_id",
                "revision_id",
                "chunker_version",
                "chunk_count",
                "manifest_sha256",
                "profile_id",
                "dims",
                "allows_zero_vectors",
                "status",
                "created_at",
            ),
        ),
        (
            EMBEDDINGS,
            _row_values(offline, chunks[0], vector),
            (
                "tenant_id",
                "index_id",
                "chunk_id",
                "revision_id",
                "chunker_version",
                "allows_zero_vectors",
                "content_sha256",
                "embedding",
                "vector_sha256",
                "is_zero",
                "created_at",
            ),
        ),
    ]
    for table, values, columns in cases:
        with engine.connect() as connection:  # the unchanged row is valid
            connection.execute(insert(table).values(**values))
            connection.rollback()
        for column in columns:
            error = _rejected(engine, table, {**values, column: None})
            assert _sqlstate(error) == NOT_NULL_VIOLATION, (table.name, column)


def _free(engine: Engine, index: store.IndexSnapshot) -> None:
    """Test setup only: remove a fresh, empty index so its source key is free again."""
    with engine.begin() as connection:
        connection.execute(delete(INDEXES).where(INDEXES.c.id == index.id))


def test_a_new_index_has_null_ready_metadata_only(engine: Engine, setup: Any) -> None:
    offline, _, _ = setup
    row = _index_row(engine, offline.id)
    assert row["status"] == "building"
    assert sorted(name for name, value in row.items() if value is None) == [
        "ready_at",
        "vector_manifest_sha256",
    ]


def test_rows_must_belong_to_the_indexs_revision_tenant_and_text(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, setup: Any
) -> None:
    offline, _, chunks = setup
    vector = canonical_vector(_axis(1.0), allows_zero=True)
    other_revision = _ingest(factory, engine, actor, "access-reviews", OTHER_TEXT)
    other_chunk = _chunks(engine, other_revision)[0]
    tenant_b = _tenant(engine, "tenant-b")
    b_revision = _ingest(factory, engine, tenant_b, "data-retention", TEXT)
    b_chunk = _chunks(engine, b_revision)[0]

    for values, constraint in (
        # Another revision's chunk under this index's revision: the membership key fails.
        (_row_values(offline, other_chunk, vector), "fk_chunk_embeddings_chunk"),
        # Claiming the other revision instead breaks the index binding.
        (
            _row_values(offline, other_chunk, vector, revision_id=other_revision),
            "fk_chunk_embeddings_index",
        ),
        # Another tenant's chunk, under this tenant or claiming the other tenant.
        (_row_values(offline, b_chunk, vector), "fk_chunk_embeddings_chunk"),
        (
            _row_values(offline, b_chunk, vector, tenant_id=tenant_b.tenant_id),
            {"fk_chunk_embeddings_index", "fk_chunk_embeddings_chunk"},
        ),
        # A copied text digest that is not the chunk's.
        (
            _row_values(offline, chunks[0], vector, content_sha256="0" * 64),
            "fk_chunk_embeddings_chunk",
        ),
        # Another chunker version.
        (
            _row_values(offline, chunks[0], vector, chunker_version="other-v9"),
            {"fk_chunk_embeddings_index", "fk_chunk_embeddings_chunk"},
        ),
    ):
        error = _rejected(engine, EMBEDDINGS, values)
        assert _sqlstate(error) == FOREIGN_KEY_VIOLATION
        expected = {constraint} if isinstance(constraint, str) else constraint
        assert _constraint(error) in expected  # with two violations, either may be reported


def test_indexes_must_match_their_chunk_set_and_profile(
    engine: Engine, actor: ActorContext, setup: Any
) -> None:
    _, live, _ = setup
    _free(engine, live)  # its source key is free, so only the binding can fail
    other_tenant = _tenant(engine, "tenant-b")
    chunk_set = {"fk_embedding_indexes_chunk_set"}
    for changes, constraints in (
        ({"chunk_count": live.chunk_count + 1}, chunk_set),
        ({"manifest_sha256": "0" * 64}, chunk_set),
        ({"chunker_version": "other-v9"}, chunk_set),
        ({"allows_zero_vectors": True}, {"fk_embedding_indexes_profile"}),  # live forbids zero
        (
            {"tenant_id": other_tenant.tenant_id},
            {"fk_embedding_indexes_chunk_set", "fk_embedding_indexes_profile"},
        ),
    ):
        error = _rejected(engine, INDEXES, _index_values(live, **changes))
        assert _sqlstate(error) == FOREIGN_KEY_VIOLATION
        assert _constraint(error) in constraints
    error = _rejected(engine, INDEXES, _index_values(live, dims=512))
    assert _sqlstate(error) == CHECK_VIOLATION
    with engine.connect() as connection:  # the unchanged binding is valid
        connection.execute(insert(INDEXES).values(**_index_values(live)))
        connection.rollback()


def test_the_profile_zero_policy_is_bound_to_the_provider(
    engine: Engine, actor: ActorContext
) -> None:
    for changes in ({"provider_id": "offline"}, {"allows_zero_vectors": True}):
        error = _rejected(engine, PROFILES, _profile_values(actor.tenant_id, **changes))
        assert _sqlstate(error) == CHECK_VIOLATION
        assert _constraint(error) == "ck_embedding_profiles_zero_policy"


def test_numeric_checks_reject_invalid_vectors(engine: Engine, setup: Any) -> None:
    offline, live, chunks = setup
    unit = canonical_vector(_axis(1.0), allows_zero=True)
    half = _axis(0.5)
    zero = canonical_vector(_axis(0.0), allows_zero=True)

    for literal in (
        _literal([1.0, 0.0, 0.0]),  # wrong dimension
        "[" + ",".join(["NaN"] + ["0"] * 1023) + "]",
        "[" + ",".join(["Infinity"] + ["0"] * 1023) + "]",
        "[" + ",".join(["1e39"] + ["0"] * 1023) + "]",  # outside float32
    ):
        error = _rejected(
            engine, EMBEDDINGS, _row_values(offline, chunks[0], unit, embedding=literal)
        )
        state = _sqlstate(error) or ""
        assert state.startswith("22"), state  # pgvector input and dimension errors

    for values, constraint in (
        (
            _row_values(
                offline,
                chunks[0],
                unit,
                embedding=_literal(half),
                vector_sha256=_wire_sha256(half),
            ),
            "ck_chunk_embeddings_unit_norm",
        ),
        (
            _row_values(offline, chunks[0], unit, vector_sha256="0" * 64),
            "ck_chunk_embeddings_vector_sha256",
        ),
        (_row_values(offline, chunks[0], unit, is_zero=True), "ck_chunk_embeddings_is_zero"),
        (_row_values(live, chunks[0], zero), "ck_chunk_embeddings_zero_policy"),
    ):
        error = _rejected(engine, EMBEDDINGS, values)
        assert _sqlstate(error) == CHECK_VIOLATION
        assert _constraint(error) == constraint

    # A zero vector claiming a zero-permitting binding under a live index breaks the FK.
    error = _rejected(
        engine, EMBEDDINGS, _row_values(live, chunks[0], zero, allows_zero_vectors=True)
    )
    assert _sqlstate(error) == FOREIGN_KEY_VIOLATION


def test_an_offline_zero_vector_is_stored_with_its_flag(engine: Engine, setup: Any) -> None:
    offline, _, chunks = setup
    zero = canonical_vector(_axis(0.0), allows_zero=True)
    with engine.begin() as connection:
        connection.execute(insert(EMBEDDINGS).values(**_row_values(offline, chunks[0], zero)))
    (stored,) = _embedding_rows(engine, offline.id)
    assert stored["is_zero"] is True and stored["norm"] == 0.0
    assert stored["db_sha256"] == zero.sha256


def test_application_and_database_agree_on_canonical_vectors(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, setup: Any
) -> None:
    offline, _, chunks = setup
    adversarial = canonical_vector(
        _unit(0.1, -0.2, 1e-30, 1.401298464324817e-45, 0.6, 0.3, -1e-7, 1 / 3),
        allows_zero=True,
    )
    hashed = _rows(engine, offline.revision_id)[1].vector
    rows = [
        StoredEmbedding(chunks[0].id, chunks[0].content_sha256, adversarial),
        StoredEmbedding(chunks[1].id, chunks[1].content_sha256, hashed),
    ]
    job = _index_job(factory, actor, offline)
    _write(factory, job, rows)

    stored = {row["chunk_id"]: row for row in _embedding_rows(engine, offline.id)}
    for row in rows:
        found = stored[row.chunk_id]
        assert bytes(found["wire"]) == row.vector.wire_bytes()  # exact stored float32 bytes
        assert decode_wire(bytes(found["wire"])) == row.vector.coordinates
        assert found["db_sha256"] == found["vector_sha256"] == row.vector.sha256
        assert abs(found["norm"] - math.hypot(*row.vector.coordinates)) <= 1e-12
        assert abs(found["norm"] - 1) <= 1e-6
