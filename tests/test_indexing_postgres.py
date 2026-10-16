"""PostgreSQL integration tests for M4c indexing (ADR-0015).

They use the guarded disposable-database fixtures from ``conftest.py`` and are skipped without
``EG_TEST_DATABASE_URL`` (required in CI). Every connection carries a server-side
``statement_timeout``. Revisions are ingested by the real worker with an ingest-only registry;
indexing runs through the real ``enqueue`` → ``claim`` → fence path, either with the production
registry or with test-owned registries whose providers are injected through
``make_index_revision_handler``. Races use deterministic events (a provider double that blocks
until released), observed lock waits and bounded waits, and assert that the intended
interleaving occurred.
"""

import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, Interval, create_engine, func, insert, literal_column, select, text
from sqlalchemy import update as sql_update
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_domain.embedding_storage import (
    STORED_DIMS,
    StoredEmbedding,
    StoredVector,
    index_id,
    profile_id,
    stored_embeddings,
)
from evidenceguard_domain.embeddings import EmbeddingBatch, EmbeddingIdentity, InputType
from evidenceguard_domain.evidence import SourceType
from evidenceguard_domain.jobs import JobIdempotencyConflictError, JobPayload, JobStatus
from evidenceguard_domain.revisions import RevisionContent
from evidenceguard_persistence import documents as revision_store
from evidenceguard_persistence import embeddings as embedding_store
from evidenceguard_persistence import indexing
from evidenceguard_persistence import jobs as job_store
from evidenceguard_persistence.db import create_session_factory, transaction
from evidenceguard_persistence.embeddings import IndexSourceNotEligibleError
from evidenceguard_persistence.indexing import BackfillOutcome, EnqueueOutcome
from evidenceguard_persistence.models import Chunk as ChunkRow
from evidenceguard_persistence.models import (
    ChunkEmbedding,
    DocumentRevision,
    EmbeddingIndex,
    Job,
    Tenant,
    Vendor,
)
from evidenceguard_retrieval.chunking import CHUNKER_VERSION
from evidenceguard_retrieval.embeddings import HASH_IDENTITY, HashingEmbedder
from evidenceguard_worker.context import JobContext
from evidenceguard_worker.handlers import production_registry
from evidenceguard_worker.indexing import INDEX_REVISION_KIND, make_index_revision_handler
from evidenceguard_worker.ingest import INGEST_REVISION_KIND, ingest_revision
from evidenceguard_worker.registry import HandlerRegistry
from evidenceguard_worker.runtime import DatabaseJobStore, Timings, WorkerResult, run_worker
from evidenceguard_worker.shutdown import StopController

pytestmark = pytest.mark.integration

WAIT_SECONDS = 10
MARKDOWN = "text/markdown"
TEXT = "# Retention\n\nCustomer data is kept for 90 days.\n\n## Backups\n\nBackups are encrypted.\n"
OTHER = "# Access\n\nAccess reviews happen quarterly.\n\n## Logging\n\nLogs are kept.\n"
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
FAST_CANCEL = Timings(
    idle_poll=0.05,
    backoff_initial=0.05,
    backoff_cap=0.2,
    heartbeat_interval=0.2,
    drain=0.1,
    cancel_grace=5.0,
    lease_loss_grace=5.0,
    heartbeat_join=5.0,
    stop_check=0.01,
)
INGEST_ONLY = HandlerRegistry([(INGEST_REVISION_KIND, ingest_revision)])


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
    return _ingest(factory, engine, actor, "data-retention", TEXT)


# --- helpers -------------------------------------------------------------------------------


def _tenant(engine: Engine, slug: str, role: Role = Role.REVIEWER) -> ActorContext:
    tenant_id = uuid4()
    with engine.begin() as connection:
        connection.execute(insert(Tenant).values(id=tenant_id, slug=slug, name=slug.title()))
        connection.execute(
            insert(Vendor).values(id=uuid4(), tenant_id=tenant_id, slug="lumenvale", name="L")
        )
    return ActorContext(tenant_id=tenant_id, actor_id=uuid4(), role=role)


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
            kind=INGEST_REVISION_KIND,
            idempotency_key=str(created.revision.id),
            payload=JobPayload.from_mapping({"revision_id": str(created.revision.id)}),
        )
    result = run_worker(
        DatabaseJobStore(factory), INGEST_ONLY, worker_id="w-ingest", timings=TIMINGS, once=True
    )
    assert result.exit_code == 0
    return created.revision.id


def _enqueue(
    factory: sessionmaker[Session],
    actor: ActorContext,
    revision_id: UUID,
    identity: EmbeddingIdentity = HASH_IDENTITY,
) -> indexing.IndexEnqueueResult:
    with transaction(factory) as session:
        return indexing.enqueue_index_revision(
            session, actor, revision_id=revision_id, identity=identity
        )


def _chunks(engine: Engine, revision_id: UUID) -> list[Any]:
    with engine.connect() as connection:
        return list(
            connection.execute(
                select(ChunkRow.id, ChunkRow.ordinal, ChunkRow.text, ChunkRow.content_sha256)
                .where(ChunkRow.revision_id == revision_id)
                .order_by(ChunkRow.ordinal)
            )
        )


def _index_row(engine: Engine, index: UUID) -> dict[str, Any] | None:
    with engine.connect() as connection:
        row = connection.execute(
            select(EmbeddingIndex.__table__).where(EmbeddingIndex.id == index)
        ).first()
    return None if row is None else dict(row._mapping)


def _job_row(engine: Engine, job_id: UUID) -> dict[str, Any]:
    with engine.connect() as connection:
        row = connection.execute(select(Job.__table__).where(Job.id == job_id)).one()
    return dict(row._mapping)


def _index_jobs(engine: Engine, tenant_id: UUID) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        rows = connection.execute(
            select(Job.__table__).where(Job.tenant_id == tenant_id, Job.kind == INDEX_REVISION_KIND)
        ).all()
    return [dict(row._mapping) for row in rows]


def _stored(engine: Engine, index: UUID) -> dict[UUID, dict[str, Any]]:
    table = ChunkEmbedding.__table__
    with engine.connect() as connection:
        rows = connection.execute(
            select(
                table.c.chunk_id,
                table.c.vector_sha256,
                table.c.created_at,
                func.vector_send(table.c.embedding).label("wire"),
            ).where(table.c.index_id == index)
        ).all()
    return {row.chunk_id: dict(row._mapping) for row in rows}


def _interval(seconds: int) -> Any:
    return literal_column(f"interval '{seconds} seconds'", type_=Interval)


def _wait_until(condition: Callable[[], bool], timeout: float = WAIT_SECONDS) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            pytest.fail("timed out waiting for the expected state")
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


def _axis(value: float, position: int) -> tuple[float, ...]:
    return tuple(value if i == position else 0.0 for i in range(STORED_DIMS))


class CountingProvider:
    """The offline embedder, recording every batch of texts it was asked to embed."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    @property
    def identity(self) -> EmbeddingIdentity:
        return HASH_IDENTITY

    def embed(self, texts: tuple[str, ...], input_type: InputType) -> EmbeddingBatch:
        self.calls.append(texts)
        return HashingEmbedder().embed(texts, input_type)


class BlockingProvider(CountingProvider):
    """Signals ``entered`` and blocks until ``release`` (bounded), then embeds."""

    def __init__(self) -> None:
        super().__init__()
        self.entered = threading.Event()
        self.release = threading.Event()

    def embed(self, texts: tuple[str, ...], input_type: InputType) -> EmbeddingBatch:
        self.entered.set()
        if not self.release.wait(WAIT_SECONDS):
            raise RuntimeError("the test never released the provider")
        return super().embed(texts, input_type)


def _registry(provider: Any) -> HandlerRegistry:
    handler = make_index_revision_handler({HASH_IDENTITY.fingerprint: lambda: provider})
    return HandlerRegistry([(INDEX_REVISION_KIND, handler)])


def _work(
    factory: sessionmaker[Session],
    registry: HandlerRegistry,
    *,
    stop: StopController | None = None,
    timings: Timings = TIMINGS,
    worker: str = "w-index",
) -> WorkerResult:
    return run_worker(
        DatabaseJobStore(factory), registry, stop=stop, worker_id=worker, timings=timings, once=True
    )


def _canonical(engine: Engine, revision_id: UUID) -> dict[UUID, StoredEmbedding]:
    chunks = _chunks(engine, revision_id)
    batch = HashingEmbedder().embed(tuple(chunk.text for chunk in chunks), "document")
    rows = stored_embeddings(
        batch, identity=HASH_IDENTITY, chunks=[(c.id, c.content_sha256) for c in chunks]
    )
    return {row.chunk_id: row for row in rows}


def _write_other(
    factory: sessionmaker[Session], actor: ActorContext, index: UUID, chunk: Any, position: int
) -> StoredEmbedding:
    """Commit a different valid vector for ``chunk`` through a separate, valid job and fence."""
    with transaction(factory) as session:
        other = job_store.enqueue(
            session,
            actor,
            kind=INDEX_REVISION_KIND,
            idempotency_key=f"competing-{uuid4()}",
            payload=JobPayload.from_mapping({"index_id": str(index)}),
        )
    claimed = job_store.claim(factory, "w-competing", kinds=[INDEX_REVISION_KIND])
    assert claimed is not None and claimed.id == other.id
    row = StoredEmbedding(
        chunk.id, chunk.content_sha256, StoredVector(_axis(1.0, position), allows_zero=True)
    )
    with job_store.fenced_transaction(factory, claimed.lease_token()) as fence:
        embedding_store.write_embeddings(fence.session, fence.job, HASH_IDENTITY, [row])
    job_store.fail_permanent(factory, claimed.lease_token())  # this helper job is done
    return row


# --- enqueue -----------------------------------------------------------------------------------


def test_enqueue_creates_the_index_and_its_job_atomically(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, revision: UUID
) -> None:
    with pytest.raises(RuntimeError), transaction(factory) as session:
        rolled = indexing.enqueue_index_revision(
            session, actor, revision_id=revision, identity=HASH_IDENTITY
        )
        raise RuntimeError("the caller's transaction fails")
    assert _index_row(engine, rolled.index.id) is None
    assert _index_jobs(engine, actor.tenant_id) == []

    result = _enqueue(factory, actor, revision)
    assert result.outcome is EnqueueOutcome.PENDING
    expected = index_id(
        actor.tenant_id,
        revision,
        CHUNKER_VERSION,
        profile_id(actor.tenant_id, HASH_IDENTITY.fingerprint),
    )
    assert result.index.id == expected and result.index.status == "building"
    (job,) = _index_jobs(engine, actor.tenant_id)
    assert job["idempotency_key"] == str(expected)
    assert job["payload"] == {"index_id": str(expected)} and job["max_attempts"] == 3
    assert job["status"] == "queued"


def test_enqueue_is_idempotent(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, revision: UUID
) -> None:
    first, second = _enqueue(factory, actor, revision), _enqueue(factory, actor, revision)
    assert first.index == second.index
    assert first.job is not None and second.job is not None and first.job.id == second.job.id
    assert second.outcome is EnqueueOutcome.PENDING
    assert len(_index_jobs(engine, actor.tenant_id)) == 1


def test_concurrent_enqueues_observe_one_index_and_one_job(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, revision: UUID
) -> None:
    session = factory()
    try:
        held = indexing.enqueue_index_revision(
            session, actor, revision_id=revision, identity=HASH_IDENTITY
        )
        with ThreadPoolExecutor(max_workers=1) as pool:
            competing = pool.submit(_enqueue, factory, actor, revision)
            _wait_until(lambda: _lock_waiters(engine) >= 1)  # observed waiting on a unique key
            assert not competing.done()
            session.commit()
            result = competing.result(timeout=WAIT_SECONDS)
    finally:
        session.close()
    assert result.index.id == held.index.id
    assert result.job is not None and held.job is not None and result.job.id == held.job.id
    assert len(_index_jobs(engine, actor.tenant_id)) == 1


def test_enqueue_is_tenant_scoped_and_requires_an_activated_revision(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, revision: UUID
) -> None:
    other = _tenant(engine, "tenant-b")
    with pytest.raises(IndexSourceNotEligibleError):
        _enqueue(factory, other, revision)
    with transaction(factory) as session:
        pending = revision_store.create_revision(
            session,
            actor,
            vendor_id=_vendor(engine, actor.tenant_id),
            document_key="never-ingested",
            title="Never ingested",
            source_type=SourceType.VENDOR_STATEMENT,
            content=RevisionContent.from_bytes(OTHER.encode(), MARKDOWN),
        ).revision.id
    with pytest.raises(IndexSourceNotEligibleError):
        _enqueue(factory, actor, pending)
    assert _index_jobs(engine, other.tenant_id) == []


def test_a_terminal_canonical_job_is_reported_stalled_and_never_changed(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, revision: UUID
) -> None:
    first = _enqueue(factory, actor, revision)
    assert first.job is not None
    claimed = job_store.claim(factory, "w-a", kinds=[INDEX_REVISION_KIND])
    assert claimed is not None and claimed.id == first.job.id
    job_store.fail_permanent(factory, claimed.lease_token())
    before = _job_row(engine, first.job.id)

    again = _enqueue(factory, actor, revision)
    assert again.outcome is EnqueueOutcome.STALLED
    assert again.job is not None and again.job.status is JobStatus.FAILED
    assert _job_row(engine, first.job.id) == before
    assert len(_index_jobs(engine, actor.tenant_id)) == 1


def test_an_explicit_enqueue_may_index_a_superseded_revision_but_backfill_skips_it(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, revision: UUID
) -> None:
    newer = _ingest(factory, engine, actor, "data-retention", OTHER)  # supersedes ``revision``
    with engine.connect() as connection:
        status = connection.execute(
            select(DocumentRevision.status).where(DocumentRevision.id == revision)
        ).scalar_one()
    assert status == "superseded"

    page = indexing.backfill_index_revisions(factory, actor, identity=HASH_IDENTITY)
    assert [item.revision_id for item in page.items] == [newer]
    assert _enqueue(factory, actor, revision).outcome is EnqueueOutcome.PENDING


# --- backfill --------------------------------------------------------------------------------


def test_backfill_pages_are_bounded_ordered_and_resumable(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, revision: UUID
) -> None:
    revisions = sorted(
        [revision]
        + [_ingest(factory, engine, actor, f"doc-{n}", f"# Doc {n}\n\nText {n}.\n") for n in (1, 2)]
    )
    first = indexing.backfill_index_revisions(factory, actor, identity=HASH_IDENTITY, limit=2)
    assert [item.revision_id for item in first.items] == revisions[:2]
    assert {item.outcome for item in first.items} == {BackfillOutcome.PENDING}
    assert first.next_after == revisions[1]

    rest = indexing.backfill_index_revisions(
        factory, actor, identity=HASH_IDENTITY, limit=2, after=first.next_after
    )
    assert [item.revision_id for item in rest.items] == revisions[2:]
    assert rest.next_after is None

    again = indexing.backfill_index_revisions(factory, actor, identity=HASH_IDENTITY, limit=50)
    assert [item.outcome for item in again.items] == [BackfillOutcome.PENDING] * 3
    assert len(_index_jobs(engine, actor.tenant_id)) == 3


def test_backfill_partial_progress_survives_an_unexpected_failure(
    factory: sessionmaker[Session],
    engine: Engine,
    actor: ActorContext,
    revision: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    second = _ingest(factory, engine, actor, "doc-two", OTHER)
    first_id, failing = sorted([revision, second])
    real = indexing.enqueue_index_revision

    def enqueue(session: Session, actor_: ActorContext, **kwargs: Any) -> Any:
        if kwargs["revision_id"] == failing:
            raise RuntimeError("injected infrastructure failure")
        return real(session, actor_, **kwargs)

    monkeypatch.setattr(indexing, "enqueue_index_revision", enqueue)
    with pytest.raises(RuntimeError):
        indexing.backfill_index_revisions(factory, actor, identity=HASH_IDENTITY)

    jobs = _index_jobs(engine, actor.tenant_id)
    assert len(jobs) == 1  # the first item committed; nothing for the failing one
    with engine.connect() as connection:
        indexed = set(
            connection.execute(
                select(EmbeddingIndex.revision_id).where(
                    EmbeddingIndex.tenant_id == actor.tenant_id
                )
            ).scalars()
        )
    assert indexed == {first_id}


def test_a_conflicting_canonical_job_is_a_conflict_item_with_no_index(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, revision: UUID
) -> None:
    expected = index_id(
        actor.tenant_id,
        revision,
        CHUNKER_VERSION,
        profile_id(actor.tenant_id, HASH_IDENTITY.fingerprint),
    )
    with transaction(factory) as session:
        job_store.enqueue(
            session,
            actor,
            kind=INDEX_REVISION_KIND,
            idempotency_key=str(expected),
            payload=JobPayload.from_mapping({"index_id": str(expected)}),
            max_attempts=5,  # a different identity under the canonical key
        )
    page = indexing.backfill_index_revisions(factory, actor, identity=HASH_IDENTITY)
    (item,) = page.items
    assert item.outcome is BackfillOutcome.CONFLICT and item.index_id is None
    assert _index_row(engine, expected) is None  # the item's transaction rolled back
    with pytest.raises(JobIdempotencyConflictError):
        _enqueue(factory, actor, revision)


# --- the production handler ------------------------------------------------------------------


def test_the_production_worker_indexes_with_atomic_readiness_and_job_success(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, revision: UUID
) -> None:
    result = _enqueue(factory, actor, revision)
    assert result.job is not None

    assert _work(factory, production_registry()).exit_code == 0

    index = _index_row(engine, result.index.id)
    assert index is not None and index["status"] == "ready" and index["ready_at"] is not None
    assert _job_row(engine, result.job.id)["status"] == "succeeded"
    stored = _stored(engine, result.index.id)
    expected = _canonical(engine, revision)
    assert len(stored) == index["chunk_count"] == len(expected)
    for chunk_id, row in expected.items():
        assert bytes(stored[chunk_id]["wire"]) == row.vector.wire_bytes()
        assert stored[chunk_id]["vector_sha256"] == row.vector.sha256
    again = _enqueue(factory, actor, revision)
    assert again.outcome is EnqueueOutcome.READY and again.job is None


def test_committed_rows_are_reused_without_recomputation_and_stay_unchanged(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, revision: UUID
) -> None:
    # Commit a row for chunk 0 before the canonical job exists, so the helper's competing job is
    # the only queued job when it claims. Then enqueue creates the missing canonical job.
    with transaction(factory) as session:
        profile = embedding_store.ensure_profile(session, actor.tenant_id, HASH_IDENTITY)
        index = embedding_store.create_index(session, actor.tenant_id, revision, profile)
    chunks = _chunks(engine, revision)
    prior = _write_other(factory, actor, index.id, chunks[0], position=5)
    before = _stored(engine, index.id)[chunks[0].id]
    result = _enqueue(factory, actor, revision)
    assert result.outcome is EnqueueOutcome.PENDING and result.index.id == index.id

    provider = CountingProvider()
    assert _work(factory, _registry(provider)).exit_code == 0

    assert provider.calls == [tuple(chunk.text for chunk in chunks[1:])]
    after = _stored(engine, result.index.id)
    assert after[chunks[0].id] == before and before["vector_sha256"] == prior.vector.sha256
    ready = _index_row(engine, result.index.id)
    assert ready is not None and ready["status"] == "ready"


def test_a_competing_writer_between_read_and_write_is_a_permanent_conflict(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, revision: UUID
) -> None:
    result = _enqueue(factory, actor, revision)
    assert result.job is not None
    chunks = _chunks(engine, revision)
    provider = BlockingProvider()

    with ThreadPoolExecutor(max_workers=1) as pool:
        running = pool.submit(_work, factory, _registry(provider))
        try:
            assert provider.entered.wait(WAIT_SECONDS)  # this attempt selected chunk 0 and blocked
            competing = _write_other(factory, actor, result.index.id, chunks[0], position=9)
        finally:
            provider.release.set()
        assert running.result(timeout=WAIT_SECONDS).exit_code == 0

    job = _job_row(engine, result.job.id)
    assert job["status"] == "failed" and job["last_error"] == "permanent_failure"
    stored = _stored(engine, result.index.id)
    assert set(stored) == {chunks[0].id}  # this attempt's batch rolled back
    assert stored[chunks[0].id]["vector_sha256"] == competing.vector.sha256  # not overwritten
    index = _index_row(engine, result.index.id)
    assert index is not None and index["status"] == "building"


def test_lease_loss_while_the_provider_blocks_writes_nothing_and_records_nothing(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, revision: UUID
) -> None:
    result = _enqueue(factory, actor, revision)
    assert result.job is not None
    provider = BlockingProvider()

    with ThreadPoolExecutor(max_workers=1) as pool:
        running = pool.submit(_work, factory, _registry(provider))
        try:
            assert provider.entered.wait(WAIT_SECONDS)
            with engine.begin() as connection:  # no fence is open during provider work
                connection.execute(
                    sql_update(Job)
                    .where(Job.id == result.job.id)
                    .values(lease_expires_at=func.clock_timestamp() - _interval(1))
                )
        finally:
            provider.release.set()
        running.result(timeout=WAIT_SECONDS * 2)

    assert _stored(engine, result.index.id) == {}
    job = _job_row(engine, result.job.id)
    assert (
        job["status"] == "running" and job["last_error"] is None
    )  # the stale worker recorded nothing
    index = _index_row(engine, result.index.id)
    assert index is not None and index["status"] == "building"


def test_cancellation_while_the_provider_blocks_records_worker_shutdown_and_writes_nothing(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, revision: UUID
) -> None:
    result = _enqueue(factory, actor, revision)
    assert result.job is not None
    provider = BlockingProvider()
    stop = StopController()
    contexts: list[JobContext] = []
    inner = make_index_revision_handler({HASH_IDENTITY.fingerprint: lambda: provider})

    def capturing(ctx: JobContext) -> None:  # test-owned wrapper: observes the real attempt
        contexts.append(ctx)
        inner(ctx)

    registry = HandlerRegistry([(INDEX_REVISION_KIND, capturing)])
    with ThreadPoolExecutor(max_workers=1) as pool:
        running = pool.submit(_work, factory, registry, stop=stop, timings=FAST_CANCEL)
        try:
            assert provider.entered.wait(WAIT_SECONDS)  # blocked inside provider work
            (ctx,) = contexts
            assert not ctx.cancel_requested
            stop.request()
            # The runtime requests cancellation after its drain period: observe the latch on
            # this attempt's own state rather than assuming a duration.
            _wait_until(lambda: ctx.cancel_requested)
            assert ctx.cancel_requested and not ctx.lease_lost
        finally:
            provider.release.set()  # never leave the worker blocked, even if a wait failed
        running.result(timeout=WAIT_SECONDS * 2)

    assert _stored(engine, result.index.id) == {}
    job = _job_row(engine, result.job.id)
    assert job["status"] == "queued" and job["last_error"] == "worker_shutdown"
    index = _index_row(engine, result.index.id)
    assert index is not None and index["status"] == "building"


def test_a_failure_at_the_finish_leaves_neither_readiness_nor_success(
    factory: sessionmaker[Session],
    engine: Engine,
    actor: ActorContext,
    revision: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _enqueue(factory, actor, revision)
    assert result.job is not None
    real = embedding_store.mark_index_ready

    def mark_then_fail(session: Any, job: Any, identity: Any) -> Any:
        real(session, job, identity)
        raise RuntimeError("injected failure inside the finishing transaction")

    monkeypatch.setattr(embedding_store, "mark_index_ready", mark_then_fail)
    _work(factory, _registry(CountingProvider()))

    index = _index_row(engine, result.index.id)
    assert index is not None and index["status"] == "building" and index["ready_at"] is None
    job = _job_row(engine, result.job.id)
    assert job["status"] == "queued" and job["last_error"] == "unexpected_error"
    assert len(_stored(engine, result.index.id)) == index["chunk_count"]  # pages stayed committed


def test_a_450_chunk_revision_is_indexed_in_bounded_pages(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext
) -> None:
    revision_id = _ingest(factory, engine, actor, "many-sections", MANY)
    result = _enqueue(factory, actor, revision_id)
    provider = CountingProvider()

    assert _work(factory, _registry(provider)).exit_code == 0

    assert all(1 <= len(call) <= 32 for call in provider.calls)
    assert sum(len(call) for call in provider.calls) == 450
    assert len(provider.calls) == 15  # ceil(450 / 32): these chunks are far below the byte cap
    index = _index_row(engine, result.index.id)
    assert index is not None and index["status"] == "ready"
    assert len(_stored(engine, result.index.id)) == 450


# --- backfill exclusions through the real lifecycle (Prompt 126) -----------------------------


def _expire_lease(engine: Engine, job_id: UUID) -> None:
    """Simulate an abandoned worker: the running attempt's lease passes in database time."""
    with engine.begin() as connection:
        connection.execute(
            sql_update(Job)
            .where(Job.id == job_id, Job.status == "running")
            .values(lease_expires_at=func.clock_timestamp() - _interval(1))
        )


def test_backfill_excludes_a_ready_index_for_the_same_profile(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, revision: UUID
) -> None:
    other = _ingest(factory, engine, actor, "doc-other", OTHER)
    ready = _enqueue(factory, actor, revision)
    assert _work(factory, production_registry()).exit_code == 0  # the real worker finishes it
    index = _index_row(engine, ready.index.id)
    assert index is not None and index["status"] == "ready"

    page = indexing.backfill_index_revisions(factory, actor, identity=HASH_IDENTITY)

    assert [item.revision_id for item in page.items] == [other]  # the ready one is excluded
    assert page.items[0].outcome is BackfillOutcome.PENDING


def test_backfill_reports_a_dead_canonical_job_as_stalled_and_leaves_it_unchanged(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, revision: UUID
) -> None:
    first = _enqueue(factory, actor, revision)
    assert first.job is not None
    # The real lifecycle: three abandoned attempts exhaust the job, then a claim's sweep marks
    # it dead. Only the running lease is expired; no terminal row is edited.
    for attempt in (1, 2, 3):
        claimed = job_store.claim(factory, f"w-{attempt}", kinds=[INDEX_REVISION_KIND])
        assert claimed is not None and claimed.id == first.job.id and claimed.attempt == attempt
        _expire_lease(engine, first.job.id)
    assert job_store.claim(factory, "w-sweep", kinds=[INDEX_REVISION_KIND]) is None
    dead = _job_row(engine, first.job.id)
    assert dead["status"] == "dead"

    page = indexing.backfill_index_revisions(factory, actor, identity=HASH_IDENTITY)

    (item,) = page.items
    assert item.revision_id == revision and item.outcome is BackfillOutcome.STALLED
    assert item.index_id == first.index.id
    assert _job_row(engine, first.job.id) == dead  # never reset, rescheduled or replaced
    assert len(_index_jobs(engine, actor.tenant_id)) == 1
    index = _index_row(engine, first.index.id)
    assert index is not None and index["status"] == "building"
