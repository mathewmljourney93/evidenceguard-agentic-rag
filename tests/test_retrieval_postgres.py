"""PostgreSQL integration tests for M4d snapshot capture and retrieval (ADR-0016).

They use the guarded disposable-database fixtures from ``conftest.py`` and are skipped without
``EG_TEST_DATABASE_URL`` (required in CI). Every connection carries a server-side
``statement_timeout``. Revisions are ingested by the real worker; indexes are built through the
real M4c ``enqueue`` → ``claim`` → fence path, with the production registry (offline hash
profile) or with test-owned registries whose fixture provider returns hand-chosen vectors.

Interleavings are positioned relative to the real snapshot establishment: a test-owned
``after_cursor_execute`` listener on a dedicated capture engine pauses the capture connection
right after a chosen helper statement, with ``threading.Event`` handshakes and bounded waits,
never sleeps.

One fixture is a lower-level exception, approved at review in Prompt 135 solely for testing
capture's metadata-based chunk-count arithmetic (see ADR-0016): ``_chunk_heavy_vendor`` marks
revisions active and indexes ready directly, with chunk sets that declare 4,096 chunks but store
none, to exercise the 100,000-chunk capture bound without inserting 100,000 chunks and vectors.
It bypasses ingestion completeness and indexing readiness verification and proves neither
ingestion/indexing correctness nor stored-vector completeness. Every other test here uses the
real ingestion and indexing paths.
"""

import dataclasses
import math
import threading
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from fractions import Fraction
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, create_engine, event, func, insert, select, text, update
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool, QueuePool

from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_domain.embedding_storage import canonical_vector, index_id, profile_id
from evidenceguard_domain.embeddings import (
    EmbeddingBatch,
    EmbeddingIdentity,
    EmbeddingUsage,
    InputType,
)
from evidenceguard_domain.evidence import Authenticity, SourceType
from evidenceguard_domain.jobs import JobPayload
from evidenceguard_domain.retrieval import (
    EmptySnapshotError,
    RetrievalDatabaseError,
    RetrievalRequest,
    RetrievalResult,
    RetrievalScopeError,
    RetrievalSnapshot,
    RevisionBinding,
    SnapshotBoundsError,
    SnapshotInconsistentError,
    SnapshotNotReadyError,
)
from evidenceguard_domain.revisions import RevisionContent
from evidenceguard_persistence import documents as revision_store
from evidenceguard_persistence import embeddings as embedding_store
from evidenceguard_persistence import indexing
from evidenceguard_persistence import jobs as job_store
from evidenceguard_persistence import retrieval as retrieval_store
from evidenceguard_persistence.db import create_session_factory, transaction
from evidenceguard_persistence.models import Chunk as ChunkRow
from evidenceguard_persistence.models import (
    ChunkEmbedding,
    ChunkSet,
    Document,
    DocumentRevision,
    EmbeddingIndex,
    Job,
    Tenant,
    Vendor,
)
from evidenceguard_persistence.retrieval import capture_snapshot
from evidenceguard_retrieval.chunking import CHUNKER_VERSION
from evidenceguard_retrieval.embeddings import HASH_IDENTITY, HashingEmbedder
from evidenceguard_worker.handlers import production_registry
from evidenceguard_worker.indexing import INDEX_REVISION_KIND, make_index_revision_handler
from evidenceguard_worker.ingest import INGEST_REVISION_KIND, ingest_revision
from evidenceguard_worker.registry import HandlerRegistry
from evidenceguard_worker.retrieval import search_snapshot
from evidenceguard_worker.runtime import DatabaseJobStore, Timings, WorkerResult, run_worker

pytestmark = pytest.mark.integration

WAIT_SECONDS = 10
MARKDOWN = "text/markdown"
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
INGEST_ONLY = HandlerRegistry([(INGEST_REVISION_KIND, ingest_revision)])
FIXTURE = EmbeddingIdentity("fixture", "axis-v1", "hand-chosen-v1", 1024, "l2")
KAPPA_SECTIONS = "".join(f"# Kappa {n}\n\nkappa kappa kappa.\n\n" for n in range(25))
TABLE = (
    "# Table\n\n| Key | Value |\n|---|---|\n"
    + "\n".join(
        f"| r{i} | value {i} padding padding padding padding padding padding padding |"
        for i in range(60)
    )
    + "\n"
)


def _vector(x: float, y: float) -> tuple[float, ...]:
    return (x, y, *([0.0] * 1022))


E0, E1 = _vector(1.0, 0.0), _vector(0.0, 1.0)
NEAR_E0, NEAR_E1 = _vector(0.8, 0.6), _vector(0.6, 0.8)


# --- engines and fixtures ------------------------------------------------------------------------


def _engine(url: URL, **options: Any) -> Engine:
    options.setdefault("poolclass", NullPool)
    return create_engine(
        url,
        hide_parameters=True,
        connect_args={"options": "-c statement_timeout=20000"},
        **options,
    )


@pytest.fixture
def engine(migrated: Engine, test_database_url: URL) -> Iterator[Engine]:
    bounded = _engine(test_database_url)
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
    return _vendor(engine, actor.tenant_id, "lumenvale")


# --- helpers -------------------------------------------------------------------------------------


def _tenant(engine: Engine, slug: str, role: Role = Role.REVIEWER) -> ActorContext:
    tenant_id = uuid4()
    with engine.begin() as connection:
        connection.execute(insert(Tenant).values(id=tenant_id, slug=slug, name=slug.title()))
    return ActorContext(tenant_id=tenant_id, actor_id=uuid4(), role=role)


def _vendor(engine: Engine, tenant_id: UUID, slug: str) -> UUID:
    vendor_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            insert(Vendor).values(id=vendor_id, tenant_id=tenant_id, slug=slug, name=slug)
        )
    return vendor_id


def _create(
    factory: sessionmaker[Session], actor: ActorContext, vendor: UUID, key: str, body: str
) -> UUID:
    """Create a revision and its canonical ingestion job, without running the worker."""
    with transaction(factory) as session:
        created = revision_store.create_revision(
            session,
            actor,
            vendor_id=vendor,
            document_key=key,
            title=key.replace("-", " ").title(),
            source_type=SourceType.VENDOR_STATEMENT,
            content=RevisionContent.from_bytes(body.encode(), MARKDOWN),
        )
        job_store.enqueue(
            session,
            actor,
            kind=INGEST_REVISION_KIND,
            idempotency_key=str(created.revision.id),
            payload=JobPayload.from_mapping({"revision_id": str(created.revision.id)}),
        )
    return created.revision.id


def _work(factory: sessionmaker[Session], registry: HandlerRegistry) -> WorkerResult:
    return run_worker(
        DatabaseJobStore(factory), registry, worker_id="w-test", timings=TIMINGS, once=True
    )


def _ingest(
    factory: sessionmaker[Session], actor: ActorContext, vendor: UUID, key: str, body: str
) -> UUID:
    revision = _create(factory, actor, vendor, key, body)
    assert _work(factory, INGEST_ONLY).exit_code == 0
    return revision


class FixtureProvider:
    """Hand-chosen unit vectors keyed by exact chunk or query text (no I/O)."""

    def __init__(self, vectors: dict[str, tuple[float, ...]]) -> None:
        self.vectors = vectors

    @property
    def identity(self) -> EmbeddingIdentity:
        return FIXTURE

    def embed(self, texts: tuple[str, ...], input_type: InputType) -> EmbeddingBatch:
        vectors = tuple(self.vectors[text_] for text_ in texts)
        return EmbeddingBatch(FIXTURE, input_type, vectors, EmbeddingUsage(None))


class ConstantProvider(FixtureProvider):
    """One hand-chosen unit vector for every text; optionally fails on the n-th ``embed`` call
    (a later page), so earlier pages stay committed and the index stays ``building``."""

    def __init__(self, vector: tuple[float, ...], fail_on_call: int | None = None) -> None:
        super().__init__({})
        self.vector = vector
        self.fail_on_call = fail_on_call
        self.calls = 0

    def embed(self, texts: tuple[str, ...], input_type: InputType) -> EmbeddingBatch:
        self.calls += 1
        if self.calls == self.fail_on_call:
            raise RuntimeError("injected provider failure on a later page")
        vectors = tuple(self.vector for _ in texts)
        return EmbeddingBatch(FIXTURE, input_type, vectors, EmbeddingUsage(None))


def _index(
    factory: sessionmaker[Session],
    engine: Engine,
    actor: ActorContext,
    revision: UUID,
    provider: FixtureProvider | None = None,
) -> UUID:
    """Index ``revision`` through the real M4c enqueue → claim → fence path."""
    identity = HASH_IDENTITY if provider is None else FIXTURE
    with transaction(factory) as session:
        result = indexing.enqueue_index_revision(
            session, actor, revision_id=revision, identity=identity
        )
    if result.outcome is not indexing.EnqueueOutcome.READY:
        if provider is None:
            registry = production_registry()
        else:
            handler = make_index_revision_handler({FIXTURE.fingerprint: lambda: provider})
            registry = HandlerRegistry([(INDEX_REVISION_KIND, handler)])
        assert _work(factory, registry).exit_code == 0
    assert _index_status(engine, result.index.id) == "ready"
    return result.index.id


def _ready(
    factory: sessionmaker[Session],
    engine: Engine,
    actor: ActorContext,
    vendor: UUID,
    key: str,
    body: str,
) -> UUID:
    revision = _ingest(factory, actor, vendor, key, body)
    _index(factory, engine, actor, revision)
    return revision


def _index_status(engine: Engine, index: UUID) -> str | None:
    with engine.connect() as connection:
        status: str | None = connection.execute(
            select(EmbeddingIndex.status).where(EmbeddingIndex.id == index)
        ).scalar_one_or_none()
    return status


def _chunks(engine: Engine, revision: UUID) -> list[Any]:
    with engine.connect() as connection:
        return list(
            connection.execute(
                select(ChunkRow.__table__)
                .where(ChunkRow.revision_id == revision)
                .order_by(ChunkRow.ordinal)
            )
        )


def _status(engine: Engine, revision: UUID) -> str:
    with engine.connect() as connection:
        status: str = connection.execute(
            select(DocumentRevision.status).where(DocumentRevision.id == revision)
        ).scalar_one()
    return status


def _capture(factory: sessionmaker[Session], actor: ActorContext, vendor: UUID, **kw: Any) -> Any:
    kw.setdefault("identity", HASH_IDENTITY)
    return capture_snapshot(factory, actor, vendor_id=vendor, **kw)


def _search(
    factory: sessionmaker[Session],
    actor: ActorContext,
    snapshot: RetrievalSnapshot,
    *queries: str,
    provider: Any = None,
    k: int = 20,
) -> RetrievalResult:
    return search_snapshot(
        factory, actor, snapshot, RetrievalRequest(queries, k), provider or HashingEmbedder()
    )


def _hits(result: RetrievalResult, channel: str, position: int = 0) -> dict[UUID, Any]:
    return {
        item.chunk_id: hit
        for item in result.items
        for hit in item.hits
        if hit.channel == channel and hit.query_position == position
    }


def _revisions_of(result: RetrievalResult) -> set[UUID]:
    return {item.revision_id for item in result.items}


def _rows(engine: Engine) -> dict[str, list[dict[str, Any]]]:
    """Every row of the tables capture and retrieval must not change (vectors as bytes)."""
    tables: dict[str, Any] = {
        "documents": select(Document.__table__).order_by(Document.id),
        "revisions": select(DocumentRevision.__table__).order_by(DocumentRevision.id),
        "jobs": select(Job.__table__).order_by(Job.id),
        "chunk_sets": select(ChunkSet.__table__).order_by(ChunkSet.revision_id),
        "indexes": select(EmbeddingIndex.__table__).order_by(EmbeddingIndex.id),
        "embeddings": select(
            ChunkEmbedding.index_id,
            ChunkEmbedding.chunk_id,
            ChunkEmbedding.vector_sha256,
            func.vector_send(ChunkEmbedding.embedding).label("wire"),
        ).order_by(ChunkEmbedding.index_id, ChunkEmbedding.chunk_id),
    }
    with engine.connect() as connection:
        return {
            name: [dict(row._mapping) for row in connection.execute(statement)]
            for name, statement in tables.items()
        }


def _pause_after(
    engine: Engine, marker: str
) -> tuple[threading.Event, threading.Event, Callable[..., None]]:
    """Pause the first statement containing ``marker`` on ``engine`` until released."""
    paused, release = threading.Event(), threading.Event()

    def listener(*args: Any) -> None:
        statement: str = args[2]
        if marker in statement and not paused.is_set():
            paused.set()
            if not release.wait(WAIT_SECONDS):
                raise RuntimeError("the test never released the paused statement")

    event.listen(engine, "after_cursor_execute", listener)
    return paused, release, listener


def _hash_distance(query: str, chunk_text: str) -> float:
    """Exact cosine distance between canonical float32 hash vectors, computed in Python."""
    batch = HashingEmbedder().embed((query, chunk_text), "query")
    a, b = (canonical_vector(v, allows_zero=True).coordinates for v in batch.vectors)
    dot = math.fsum(x * y for x, y in zip(a, b, strict=True))
    return 1.0 - dot / (math.hypot(*a) * math.hypot(*b))


# --- capture -------------------------------------------------------------------------------------


def test_capture_binds_the_vendors_ready_active_revisions_exactly(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, vendor: UUID
) -> None:
    first = _ready(factory, engine, actor, vendor, "retention", "Retention is ninety days.\n")
    second = _ready(factory, engine, actor, vendor, "backups", "# Backups\n\nEncrypted.\n")
    pending = _create(factory, actor, vendor, "unsettled", "Still pending.\n")

    snapshot = _capture(factory, actor, vendor)

    profile = profile_id(actor.tenant_id, HASH_IDENTITY.fingerprint)
    assert snapshot.profile_id == profile
    assert [b.revision_id for b in snapshot.bindings] == sorted([first, second])
    with engine.connect() as connection:
        sets = {row.revision_id: row for row in connection.execute(select(ChunkSet.__table__))}
        indexes = {
            row.revision_id: row
            for row in connection.execute(
                select(EmbeddingIndex.__table__).where(EmbeddingIndex.profile_id == profile)
            )
        }
    for binding in snapshot.bindings:
        stored = sets[binding.revision_id]
        assert (binding.chunker_version, binding.chunk_count, binding.manifest_sha256) == (
            stored.chunker_version,
            stored.chunk_count,
            stored.manifest_sha256,
        )
        index = indexes[binding.revision_id]
        assert binding.index_id == index.id
        assert binding.index_id == index_id(
            actor.tenant_id, binding.revision_id, CHUNKER_VERSION, profile
        )
        assert binding.vector_manifest_sha256 == index.vector_manifest_sha256
    assert snapshot.total_chunks == sum(sets[r].chunk_count for r in (first, second))
    assert snapshot.exclusions.count == 1 and snapshot.exclusions.revision_ids == (pending,)
    assert not snapshot.exclusions.truncated
    assert snapshot.captured_at.tzinfo is not None


def test_more_than_100_pending_revisions_are_counted_and_truncated(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, vendor: UUID
) -> None:
    _ready(factory, engine, actor, vendor, "retention", "Retention is ninety days.\n")
    with transaction(factory) as session:
        created = [
            revision_store.create_revision(
                session,
                actor,
                vendor_id=vendor,
                document_key=f"pending-{n}",
                title=f"Pending {n}",
                source_type=SourceType.CONTRACT,
                content=RevisionContent.from_bytes(f"Pending {n}.\n".encode(), MARKDOWN),
            ).revision.id
            for n in range(105)
        ]
    snapshot = _capture(factory, actor, vendor)
    assert snapshot.exclusions.count == 105 and snapshot.exclusions.truncated
    assert snapshot.exclusions.revision_ids == tuple(sorted(created)[:100])


def test_a_processing_revision_is_excluded_and_recorded(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, vendor: UUID
) -> None:
    active = _ready(factory, engine, actor, vendor, "retention", "Retention is ninety days.\n")
    held = _create(factory, actor, vendor, "retention", "Retention is thirty days.\n")
    claimed = job_store.claim(factory, "w-held", kinds=[INGEST_REVISION_KIND])
    assert claimed is not None
    with job_store.fenced_transaction(factory, claimed.lease_token()) as fence:
        revision_store.start_processing(fence.session, fence.job)
    assert _status(engine, held) == "processing"

    snapshot = _capture(factory, actor, vendor)
    assert [b.revision_id for b in snapshot.bindings] == [active]
    assert snapshot.exclusions.revision_ids == (held,)


@pytest.mark.parametrize("state", ["unindexed", "building", "other_profile_only"])
def test_an_active_revision_without_a_ready_index_refuses_capture(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, vendor: UUID, state: str
) -> None:
    _ready(factory, engine, actor, vendor, "retention", "Retention is ninety days.\n")
    revision = _ingest(factory, actor, vendor, "access", "Access reviews happen quarterly.\n")
    if state == "building":
        with transaction(factory) as session:
            indexing.enqueue_index_revision(
                session, actor, revision_id=revision, identity=HASH_IDENTITY
            )
    elif state == "other_profile_only":
        chunk = _chunks(engine, revision)[0]
        _index(factory, engine, actor, revision, FixtureProvider({chunk.text: E0}))
    before = _rows(engine)
    with pytest.raises(SnapshotNotReadyError) as raised:
        _capture(factory, actor, vendor)
    assert str(raised.value) == "snapshot_not_ready" and str(revision) not in str(raised.value)
    assert _rows(engine) == before  # capture never enqueues or indexes


def test_empty_vendors_are_an_explicit_error(
    factory: sessionmaker[Session], actor: ActorContext, vendor: UUID
) -> None:
    with pytest.raises(EmptySnapshotError):
        _capture(factory, actor, vendor)
    _create(factory, actor, vendor, "pending-only", "Pending.\n")  # no active pointer
    with pytest.raises(EmptySnapshotError):
        _capture(factory, actor, vendor)


def test_missing_and_foreign_vendors_are_indistinguishable(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, vendor: UUID
) -> None:
    other = _tenant(engine, "tenant-b")
    foreign_vendor = _vendor(engine, other.tenant_id, "lumenvale")
    _ready(factory, engine, other, foreign_vendor, "retention", "Retention.\n")
    errors = []
    for target in (foreign_vendor, uuid4()):
        with pytest.raises(RetrievalScopeError) as raised:
            _capture(factory, actor, target)
        errors.append((type(raised.value), str(raised.value)))
    assert errors[0] == errors[1] == (RetrievalScopeError, "retrieval_scope")


def test_101_active_revisions_exceed_the_revision_bound_before_readiness(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, vendor: UUID
) -> None:
    for n in range(101):
        _create(factory, actor, vendor, f"doc-{n}", f"Document {n}.\n")
    for _ in range(101):
        assert _work(factory, INGEST_ONLY).exit_code == 0
    with engine.connect() as connection:
        active = connection.execute(
            select(func.count()).where(DocumentRevision.status == "active")
        ).scalar_one()
    assert active == 101
    # None is indexed, so readiness would also fail: the revision bound takes precedence.
    with pytest.raises(SnapshotBoundsError):
        _capture(factory, actor, vendor)


def _chunk_heavy_vendor(
    factory: sessionmaker[Session],
    actor: ActorContext,
    vendor: UUID,
    *,
    start: int,
    count: int,
) -> None:
    """Lower-level fixture (exception approved in Prompt 135 for this bound test only, see the
    module docstring): ``count`` new active revisions numbered from ``start``, each a distinct
    document and content, with a chunk set declaring 4,096 chunks (none stored) and a ready
    index."""
    with transaction(factory) as session:
        profile = embedding_store.ensure_profile(session, actor.tenant_id, HASH_IDENTITY)
    for n in range(start, start + count):
        with transaction(factory) as session:
            revision = revision_store.create_revision(
                session,
                actor,
                vendor_id=vendor,
                document_key=f"heavy-{n}",
                title=f"Heavy {n}",
                source_type=SourceType.CONTRACT,
                content=RevisionContent.from_bytes(f"Heavy {n}.\n".encode(), MARKDOWN),
            ).revision
            session.execute(
                update(DocumentRevision)
                .where(DocumentRevision.id == revision.id)
                .values(status="active", activated_at=func.clock_timestamp())
            )
            session.execute(
                update(Document)
                .where(Document.id == revision.document_id)
                .values(active_revision_id=revision.id)
            )
            session.execute(
                insert(ChunkSet).values(
                    tenant_id=actor.tenant_id,
                    revision_id=revision.id,
                    chunker_version=CHUNKER_VERSION,
                    chunk_count=4096,
                    manifest_sha256=f"{n:064x}",
                )
            )
            index = embedding_store.create_index(session, actor.tenant_id, revision.id, profile)
            session.execute(
                update(EmbeddingIndex)
                .where(EmbeddingIndex.id == index.id)
                .values(
                    status="ready", ready_at=func.clock_timestamp(), vector_manifest_sha256="e" * 64
                )
            )


def test_more_than_100000_eligible_chunks_exceed_the_chunk_bound(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, vendor: UUID
) -> None:
    _chunk_heavy_vendor(factory, actor, vendor, start=0, count=24)  # 98,304 chunks: accepted
    first = _capture(factory, actor, vendor)
    assert len(first.bindings) == 24 and first.total_chunks == 98_304
    _chunk_heavy_vendor(factory, actor, vendor, start=24, count=1)  # one more distinct revision

    with engine.connect() as connection:
        documents = connection.execute(
            select(Document.id, Document.active_revision_id).where(Document.vendor_id == vendor)
        ).all()
        revisions = [document.active_revision_id for document in documents]
        sets = connection.execute(
            select(ChunkSet.revision_id, ChunkSet.chunk_count).where(
                ChunkSet.revision_id.in_(revisions)
            )
        ).all()
        indexes = connection.execute(
            select(EmbeddingIndex.revision_id).where(
                EmbeddingIndex.revision_id.in_(revisions), EmbeddingIndex.status == "ready"
            )
        ).all()
    assert len(documents) == len(set(revisions)) == 25 and None not in revisions
    assert len({row.revision_id for row in sets}) == len(sets) == 25
    assert len({row.revision_id for row in indexes}) == len(indexes) == 25
    assert sum(row.chunk_count for row in sets) == 102_400
    with pytest.raises(SnapshotBoundsError):
        _capture(factory, actor, vendor)


def test_an_inconsistent_pointer_takes_precedence_over_an_unready_revision(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, vendor: UUID
) -> None:
    old = _ready(factory, engine, actor, vendor, "retention", "Retention is ninety days.\n")
    new = _ready(factory, engine, actor, vendor, "retention", "Retention is thirty days.\n")
    _ingest(factory, actor, vendor, "access", "Access reviews.\n")  # active, unindexed
    with engine.begin() as connection:  # direct corruption: the pointer names a superseded row
        document = connection.execute(
            select(DocumentRevision.document_id).where(DocumentRevision.id == new)
        ).scalar_one()
        connection.execute(
            update(Document).where(Document.id == document).values(active_revision_id=old)
        )
    with pytest.raises(SnapshotInconsistentError):
        _capture(factory, actor, vendor)


# --- snapshot-relative supersession --------------------------------------------------------------


def test_supersession_is_snapshot_relative(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, vendor: UUID
) -> None:
    old = _ready(factory, engine, actor, vendor, "retention", "Retention is ninety days.\n")
    older_snapshot = _capture(factory, actor, vendor)
    new = _ready(factory, engine, actor, vendor, "retention", "Retention is thirty days.\n")
    assert _status(engine, old) == "superseded"

    # Active at capture, superseded since: still eligible for the older snapshot.
    result = _search(factory, actor, older_snapshot, "retention ninety")
    assert _revisions_of(result) == {old}
    assert set(_hits(result, "lexical")) == {c.id for c in _chunks(engine, old)}

    # Superseded at capture: excluded from a new snapshot; the new revision never enters the
    # older one.
    newer_snapshot = _capture(factory, actor, vendor)
    assert [b.revision_id for b in newer_snapshot.bindings] == [new]
    assert _revisions_of(_search(factory, actor, newer_snapshot, "retention ninety")) == {new}
    assert _revisions_of(_search(factory, actor, older_snapshot, "thirty")) == {old}


# --- lexical semantics ---------------------------------------------------------------------------


@pytest.fixture
def lexical_corpus(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, vendor: UUID
) -> tuple[RetrievalSnapshot, dict[str, UUID]]:
    texts = {
        "retention": "Customer data retention lasts ninety days.\n",
        "backups": "Backups are encrypted by the operator.\n",
        "policy": "Data retention policy for backups.\n",
        "accents": "éàü ñüé\n",  # no ASCII word: the offline hash is the zero vector
    }
    revisions = {
        key: _ready(factory, engine, actor, vendor, key, body) for key, body in texts.items()
    }
    chunks = {key: _chunks(engine, revision)[0].id for key, revision in revisions.items()}
    return _capture(factory, actor, vendor), chunks


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("retention ninety", {"retention"}),  # unquoted words are ANDed
        ('"retention policy"', {"policy"}),  # a quoted phrase
        ("ninety or encrypted", {"retention", "backups"}),  # "or" gives OR
        ("RETENTION", {"retention", "policy"}),  # case folding
        ("backup", set()),  # simple: no stemming
        ("the", {"backups"}),  # simple: no stop words
        ("ñüé", {"accents"}),
    ],
)
def test_lexical_semantics_against_real_postgresql(
    factory: sessionmaker[Session],
    actor: ActorContext,
    lexical_corpus: tuple[RetrievalSnapshot, dict[str, UUID]],
    query: str,
    expected: set[str],
) -> None:
    snapshot, chunks = lexical_corpus
    result = _search(factory, actor, snapshot, query)
    lexical = _hits(result, "lexical")
    assert set(lexical) == {chunks[key] for key in expected}
    assert all(hit.score > 0 for hit in lexical.values())


def test_negation_only_and_punctuation_only_queries_have_no_lexical_candidates(
    factory: sessionmaker[Session],
    actor: ActorContext,
    lexical_corpus: tuple[RetrievalSnapshot, dict[str, UUID]],
) -> None:
    snapshot, _ = lexical_corpus
    negation = _search(factory, actor, snapshot, "-retention")
    assert _hits(negation, "lexical") == {}  # rank 0 matches are not candidates
    punctuation = _search(factory, actor, snapshot, "!!! ???")
    assert punctuation.items == () and punctuation.vector_skipped == (0,)  # no error


def test_zero_vectors_are_never_vector_candidates_and_zero_queries_fall_back_to_lexical(
    factory: sessionmaker[Session],
    engine: Engine,
    actor: ActorContext,
    lexical_corpus: tuple[RetrievalSnapshot, dict[str, UUID]],
) -> None:
    snapshot, chunks = lexical_corpus
    with engine.connect() as connection:
        zero = connection.execute(
            select(ChunkEmbedding.is_zero).where(ChunkEmbedding.chunk_id == chunks["accents"])
        ).scalar_one()
    assert zero  # the offline hash of non-ASCII text is the zero vector
    result = _search(factory, actor, snapshot, "retention data")
    assert chunks["accents"] not in _hits(result, "vector")
    assert len(_hits(result, "vector")) == 3  # every nonzero eligible chunk, ordered
    accents = _search(factory, actor, snapshot, "ñüé")
    assert accents.vector_skipped == (0,)
    assert [item.chunk_id for item in accents.items] == [chunks["accents"]]
    assert [h.channel for h in accents.items[0].hits] == ["lexical"]


def test_vector_scores_are_exact_cosine_distances_of_the_float32_vectors(
    factory: sessionmaker[Session],
    engine: Engine,
    actor: ActorContext,
    lexical_corpus: tuple[RetrievalSnapshot, dict[str, UUID]],
) -> None:
    snapshot, chunks = lexical_corpus
    query = "data retention for customers"
    result = _search(factory, actor, snapshot, query)
    texts = {}
    with engine.connect() as connection:
        for chunk in chunks.values():
            texts[chunk] = connection.execute(
                select(ChunkRow.text).where(ChunkRow.id == chunk)
            ).scalar_one()
    vector = _hits(result, "vector")
    for chunk, hit in vector.items():
        assert hit.score == pytest.approx(_hash_distance(query, texts[chunk]), abs=1e-6)
    ordered = sorted(vector, key=lambda chunk: vector[chunk].rank)
    assert [vector[c].score for c in ordered] == sorted(vector[c].score for c in ordered)


# --- exact cosine ordering, ties and fusion with hand-chosen vectors -----------------------------


@pytest.fixture
def axis_corpus(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, vendor: UUID
) -> tuple[RetrievalSnapshot, dict[str, UUID], FixtureProvider]:
    texts = {
        "a": ("Alpha alpha alpha.", E0),
        "b": ("Alpha bravo.", NEAR_E0),
        "b2": ("Bravo twin.", NEAR_E0),  # the same vector as "b": an exact distance tie
        "c": ("Charlie.", NEAR_E1),
        "d": ("Delta.", E1),
    }
    provider = FixtureProvider(
        {text_: vector for text_, vector in texts.values()} | {"alpha": E1, "east": E0}
    )
    chunks: dict[str, UUID] = {}
    for key, (body, _) in texts.items():
        revision = _ingest(factory, actor, vendor, f"axis-{key}", body + "\n")
        (chunk,) = _chunks(engine, revision)
        assert chunk.text == body
        _index(factory, engine, actor, revision, provider)
        chunks[key] = chunk.id
    snapshot = _capture(factory, actor, vendor, identity=FIXTURE)
    return snapshot, chunks, provider


def test_exact_cosine_ordering_with_hand_computed_distances_and_uuid_ties(
    factory: sessionmaker[Session],
    actor: ActorContext,
    axis_corpus: tuple[RetrievalSnapshot, dict[str, UUID], FixtureProvider],
) -> None:
    snapshot, chunks, provider = axis_corpus
    result = _search(factory, actor, snapshot, "east", provider=provider)
    assert _hits(result, "lexical") == {}
    vector = _hits(result, "vector")
    tie = sorted([chunks["b"], chunks["b2"]])
    by_rank = [chunk for chunk, _ in sorted(vector.items(), key=lambda item: item[1].rank)]
    assert by_rank == [chunks["a"], *tie, chunks["c"], chunks["d"]]
    # 1 - cos with float32 coordinates: 0, 1 - 0.8, 1 - 0.6 and 1, by hand.
    expected = {chunks["a"]: 0.0, chunks["b"]: 0.2, chunks["b2"]: 0.2}
    expected |= {chunks["c"]: 0.4, chunks["d"]: 1.0}
    for chunk, distance in expected.items():
        assert vector[chunk].score == pytest.approx(distance, abs=1e-6)
    assert vector[tie[0]].score == vector[tie[1]].score  # an exact tie in the database


def test_fusion_end_to_end_matches_independently_computed_rrf(
    factory: sessionmaker[Session],
    actor: ActorContext,
    axis_corpus: tuple[RetrievalSnapshot, dict[str, UUID], FixtureProvider],
) -> None:
    snapshot, c, provider = axis_corpus
    result = _search(factory, actor, snapshot, "alpha", "east", provider=provider, k=8)

    b_first, b_second = sorted([c["b"], c["b2"]])
    # Lists derived by hand from the fixture (ties by ascending chunk UUID):
    lists = [
        [c["a"], c["b"]],  # q0 lexical "alpha": three occurrences outrank one
        [c["d"], c["c"], b_first, b_second, c["a"]],  # q0 vector e1
        [],  # q1 lexical "east": no lexeme matches
        [c["a"], b_first, b_second, c["c"], c["d"]],  # q1 vector e0
    ]
    expected: dict[UUID, Fraction] = {}
    for ranked in lists:
        for rank, chunk in enumerate(ranked, start=1):
            expected[chunk] = expected.get(chunk, Fraction(0)) + Fraction(1, 60 + rank)
    order = sorted(expected, key=lambda chunk: (-expected[chunk], chunk))

    assert [item.chunk_id for item in result.items] == order
    assert [item.fused_score for item in result.items] == [expected[x] for x in order]
    assert [item.fused_rank for item in result.items] == list(range(1, len(order) + 1))
    lexical = _hits(result, "lexical")
    assert lexical[c["a"]].rank == 1 and lexical[c["b"]].rank == 2
    assert lexical[c["a"]].score > lexical[c["b"]].score


def test_equal_lexical_scores_tie_by_ascending_uuid(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, vendor: UUID
) -> None:
    first = _ready(factory, engine, actor, vendor, "echo-one", "Echo echo.\n")
    second = _ready(factory, engine, actor, vendor, "echo-two", "Echo echo.\n")
    snapshot = _capture(factory, actor, vendor)
    lexical = _hits(_search(factory, actor, snapshot, "echo"), "lexical")
    ids = sorted([_chunks(engine, first)[0].id, _chunks(engine, second)[0].id])
    assert lexical[ids[0]].score == lexical[ids[1]].score
    assert (lexical[ids[0]].rank, lexical[ids[1]].rank) == (1, 2)


# --- filters before limits, isolation and profiles ---------------------------------------------


def test_filters_apply_before_each_channel_limit(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, vendor: UUID
) -> None:
    eligible_text = "kappa lima mike november oscar papa quebec romeo sierra.\n"
    eligible = _ready(factory, engine, actor, vendor, "eligible", eligible_text)
    # 25 higher-scoring chunks in each forbidden place: another tenant, another vendor and a
    # revision superseded before capture.
    other = _tenant(engine, "tenant-b")
    other_vendor = _vendor(engine, other.tenant_id, "lumenvale")
    _ready(factory, engine, other, other_vendor, "kappa", KAPPA_SECTIONS)
    sibling = _vendor(engine, actor.tenant_id, "sibling")
    _ready(factory, engine, actor, sibling, "kappa", KAPPA_SECTIONS)
    superseded = _ready(factory, engine, actor, vendor, "kappa", KAPPA_SECTIONS)
    _ready(factory, engine, actor, vendor, "kappa", "Nothing relevant here.\n")
    assert _status(engine, superseded) == "superseded"
    assert len(_chunks(engine, superseded)) == 25

    snapshot = _capture(factory, actor, vendor)
    result = _search(factory, actor, snapshot, "kappa")

    (target,) = _chunks(engine, eligible)
    lexical, vector = _hits(result, "lexical"), _hits(result, "vector")
    assert set(lexical) == {target.id} and lexical[target.id].rank == 1
    assert target.id in vector and vector[target.id].rank == 1
    bound = {b.revision_id for b in snapshot.bindings}
    assert _revisions_of(result) <= bound and superseded not in bound


def test_multiple_profiles_never_duplicate_candidates_and_building_indexes_never_leak(
    factory: sessionmaker[Session],
    engine: Engine,
    actor: ActorContext,
    vendor: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _ready(factory, engine, actor, vendor, "first", "Retention lasts ninety days.\n")
    second = _ready(factory, engine, actor, vendor, "second", "Retention ends after thirty.\n")
    (first_chunk,) = _chunks(engine, first)
    (second_chunk,) = _chunks(engine, second)
    query = "retention"
    # A ready fixture-profile index for the first revision whose vector equals the query's hash
    # vector would rank it at distance 0 if it leaked into the hash-profile channel.
    query_vector = HashingEmbedder().embed((query,), "query").vectors[0]
    provider = FixtureProvider({first_chunk.text: query_vector, second_chunk.text: E1})
    _index(factory, engine, actor, first, provider)
    # A fixture-profile index for the second revision left ``building`` with its embeddings
    # written (the finishing transaction fails), indexed last so no retry is claimed later.
    real = embedding_store.mark_index_ready

    def mark_then_fail(session: Any, job: Any, identity: Any) -> Any:
        real(session, job, identity)
        raise RuntimeError("injected failure inside the finishing transaction")

    monkeypatch.setattr(embedding_store, "mark_index_ready", mark_then_fail)
    with transaction(factory) as session:
        building = indexing.enqueue_index_revision(
            session, actor, revision_id=second, identity=FIXTURE
        ).index.id
    handler = make_index_revision_handler({FIXTURE.fingerprint: lambda: provider})
    _work(factory, HandlerRegistry([(INDEX_REVISION_KIND, handler)]))
    monkeypatch.undo()
    assert _index_status(engine, building) == "building"

    snapshot = _capture(factory, actor, vendor)  # the hash profile: both ready
    result = _search(factory, actor, snapshot, query)  # duplicates would be inconsistent
    lexical, vector = _hits(result, "lexical"), _hits(result, "vector")
    assert set(lexical) == {first_chunk.id, second_chunk.id}
    assert vector[first_chunk.id].score == pytest.approx(
        _hash_distance(query, first_chunk.text), abs=1e-6
    )
    assert vector[first_chunk.id].score > 1e-3  # not the leaked fixture-profile distance 0
    with pytest.raises(SnapshotNotReadyError):  # the fixture profile: one index is building
        _capture(factory, actor, vendor, identity=FIXTURE)


def _sections(prefix: str, count: int) -> str:
    """``count`` one-chunk sections with no word shared with the query ``kappa``."""
    return "".join(
        f"# {prefix.title()} {n}\n\nzulu yankee xray {prefix} {n}.\n\n" for n in range(count)
    )


def test_wrong_profile_and_building_index_candidates_never_displace_the_target(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, vendor: UUID
) -> None:
    query = "kappa"
    query_vector = HashingEmbedder().embed((query,), "query").vectors[0]
    target_text = "kappa lima mike november oscar papa quebec romeo sierra.\n"
    target = _ready(factory, engine, actor, vendor, "target", target_text)
    wrong = _ready(factory, engine, actor, vendor, "wrong-profile", _sections("wrong", 25))
    building = _ready(factory, engine, actor, vendor, "building", _sections("building", 40))
    # Under the fixture profile every stored vector equals the query's hash vector (cosine
    # distance 0), while each eligible hash-profile distance is about 0.76 for the target and at
    # least 1 for the other 65 chunks. If the index, profile or status filter were omitted, these
    # rows (26 ready plus 32 building) would fill the vector limit ahead of the target, and every
    # lexical candidate would appear once per index.
    tempting = ConstantProvider(query_vector)
    wrong_indexes = [_index(factory, engine, actor, r, tempting) for r in (target, wrong)]
    partial = ConstantProvider(query_vector, fail_on_call=2)  # page 1 commits, page 2 fails
    with transaction(factory) as session:
        building_index = indexing.enqueue_index_revision(
            session, actor, revision_id=building, identity=FIXTURE
        ).index.id
    handler = make_index_revision_handler({FIXTURE.fingerprint: lambda: partial})
    _work(factory, HandlerRegistry([(INDEX_REVISION_KIND, handler)]))
    assert partial.calls == 2
    assert _index_status(engine, building_index) == "building"
    with engine.connect() as connection:

        def stored(index: UUID) -> int:
            count: int = connection.execute(
                select(func.count()).where(ChunkEmbedding.index_id == index)
            ).scalar_one()
            return count

        assert [stored(index) for index in wrong_indexes] == [1, 25]
        assert stored(building_index) == 32  # one committed page of 40 chunks: partial
    assert all(_index_status(engine, index) == "ready" for index in wrong_indexes)

    snapshot = _capture(factory, actor, vendor)  # the hash profile
    assert {b.revision_id for b in snapshot.bindings} == {target, wrong, building}
    result = _search(factory, actor, snapshot, query)  # a duplicate would be inconsistent

    (target_chunk,) = _chunks(engine, target)
    lexical, vector = _hits(result, "lexical"), _hits(result, "vector")
    assert set(lexical) == {target_chunk.id} and lexical[target_chunk.id].rank == 1
    assert vector[target_chunk.id].rank == 1
    assert vector[target_chunk.id].score == pytest.approx(
        _hash_distance(query, target_chunk.text), abs=1e-6
    )
    assert len(vector) == 20  # the limit, filled only by hash-profile rows
    assert min(hit.score for hit in vector.values()) > 0.5  # no leaked distance-0 row
    assert len({item.chunk_id for item in result.items}) == len(result.items)


# --- binding recheck ---------------------------------------------------------------------------


def test_forged_bindings_fail_the_database_recheck(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, vendor: UUID
) -> None:
    revision = _ready(factory, engine, actor, vendor, "retention", "Retention is ninety days.\n")
    snapshot = _capture(factory, actor, vendor)
    (binding,) = snapshot.bindings
    profile = snapshot.profile_id
    other = _tenant(engine, "tenant-b")
    other_vendor = _vendor(engine, other.tenant_id, "lumenvale")
    foreign = _ready(factory, engine, other, other_vendor, "foreign", "Foreign text.\n")
    sibling = _vendor(engine, actor.tenant_id, "sibling")
    sibling_revision = _ready(factory, engine, actor, sibling, "sibling", "Sibling text.\n")
    never = _create(factory, actor, vendor, "never", "Never activated.\n")

    def bound(revision_id: UUID, **changes: Any) -> RevisionBinding:
        with engine.connect() as connection:
            document = connection.execute(
                select(DocumentRevision.document_id).where(DocumentRevision.id == revision_id)
            ).scalar_one()
            stored = connection.execute(
                select(ChunkSet.chunk_count, ChunkSet.manifest_sha256).where(
                    ChunkSet.revision_id == revision_id
                )
            ).first()
            vector_manifest = connection.execute(
                select(EmbeddingIndex.vector_manifest_sha256).where(
                    EmbeddingIndex.revision_id == revision_id, EmbeddingIndex.status == "ready"
                )
            ).scalar()
        # The revision's own stored facts where they exist, so each forgery fails the recheck
        # for the condition it names.
        values: dict[str, Any] = {
            "revision_id": revision_id,
            "document_id": document,
            "index_id": index_id(actor.tenant_id, revision_id, CHUNKER_VERSION, profile),
            "chunker_version": binding.chunker_version,
            "chunk_count": binding.chunk_count if stored is None else stored.chunk_count,
            "manifest_sha256": (
                binding.manifest_sha256 if stored is None else stored.manifest_sha256
            ),
            "vector_manifest_sha256": vector_manifest or binding.vector_manifest_sha256,
        }
        values.update(changes)
        return RevisionBinding(**values)

    forgeries = [
        bound(foreign),
        bound(sibling_revision),
        bound(never),
        dataclasses.replace(binding, manifest_sha256="f" * 64),
        dataclasses.replace(binding, chunk_count=binding.chunk_count + 1),
        dataclasses.replace(binding, vector_manifest_sha256="f" * 64),
        bound(
            revision,
            chunker_version="other-v1",
            index_id=index_id(actor.tenant_id, revision, "other-v1", profile),
        ),
    ]
    for forged in forgeries:
        forged_snapshot = dataclasses.replace(snapshot, bindings=(forged,))
        with pytest.raises(SnapshotInconsistentError):
            _search(factory, actor, forged_snapshot, "retention")


def test_the_recheck_cannot_prove_past_eligibility_the_accepted_limitation(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, vendor: UUID
) -> None:
    """R3: a structurally valid snapshot built by trusted in-process code from a revision that
    was superseded **before** capture passes the binding recheck. Only ``capture_snapshot``
    establishes eligibility; M5 must persist and reload captured facts through trusted paths."""
    old = _ready(factory, engine, actor, vendor, "retention", "Retention is ninety days.\n")
    template = _capture(factory, actor, vendor)
    _ready(factory, engine, actor, vendor, "retention", "Retention is thirty days.\n")
    assert _status(engine, old) == "superseded"
    # Claims a capture after the supersession while binding the superseded revision.
    forged = dataclasses.replace(template, captured_at=datetime.now(UTC))
    assert [b.revision_id for b in forged.bindings] == [old]
    assert _revisions_of(_search(factory, actor, forged, "retention")) == {old}


# --- deterministic interleavings -----------------------------------------------------------------


def test_an_activation_committed_after_the_snapshot_is_established_is_invisible(
    factory: sessionmaker[Session],
    engine: Engine,
    actor: ActorContext,
    vendor: UUID,
    test_database_url: URL,
) -> None:
    old = _ready(factory, engine, actor, vendor, "retention", "Retention is ninety days.\n")
    capture_engine = _engine(test_database_url)
    paused, release, listener = _pause_after(capture_engine, "clock_timestamp")
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            running = pool.submit(_capture, create_session_factory(capture_engine), actor, vendor)
            try:
                assert paused.wait(WAIT_SECONDS)  # the snapshot is established and held
                new = _ingest(factory, actor, vendor, "retention", "Retention is thirty days.\n")
                assert _status(engine, old) == "superseded"
            finally:
                release.set()
            snapshot = running.result(timeout=WAIT_SECONDS)
    finally:
        event.remove(capture_engine, "after_cursor_execute", listener)
        capture_engine.dispose()
    assert [b.revision_id for b in snapshot.bindings] == [old]
    assert new not in snapshot.exclusions.revision_ids  # it did not exist in the snapshot
    # Retrieval after the supersession still uses the captured revision.
    assert _revisions_of(_search(factory, actor, snapshot, "retention")) == {old}


def test_an_activation_committed_before_the_snapshot_is_established_is_visible(
    factory: sessionmaker[Session],
    engine: Engine,
    actor: ActorContext,
    vendor: UUID,
    test_database_url: URL,
) -> None:
    _ready(factory, engine, actor, vendor, "retention", "Retention is ninety days.\n")
    capture_engine = _engine(test_database_url)
    paused, release, listener = _pause_after(capture_engine, "SET TRANSACTION ISOLATION LEVEL")
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            running = pool.submit(_capture, create_session_factory(capture_engine), actor, vendor)
            try:
                assert paused.wait(WAIT_SECONDS)  # SET TRANSACTION ran; no snapshot yet
                _ingest(factory, actor, vendor, "retention", "Retention is thirty days.\n")
            finally:
                release.set()
            with pytest.raises(SnapshotNotReadyError):  # active, not yet indexed
                running.result(timeout=WAIT_SECONDS)
    finally:
        event.remove(capture_engine, "after_cursor_execute", listener)
        capture_engine.dispose()


def test_a_replacement_activated_during_retrieval_never_enters_the_snapshot(
    factory: sessionmaker[Session],
    engine: Engine,
    actor: ActorContext,
    vendor: UUID,
    test_database_url: URL,
) -> None:
    old = _ready(factory, engine, actor, vendor, "retention", "Retention is ninety days.\n")
    snapshot = _capture(factory, actor, vendor)
    retrieval_engine = _engine(test_database_url)
    # Pause right after the binding recheck, before any channel statement.
    paused, release, listener = _pause_after(retrieval_engine, "AS verified")
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            running = pool.submit(
                _search, create_session_factory(retrieval_engine), actor, snapshot, "retention"
            )
            try:
                assert paused.wait(WAIT_SECONDS)
                # A replacement, ingested, activated and indexed through the real lifecycle on
                # other connections, commits while retrieval is paused.
                replacement = _ready(
                    factory, engine, actor, vendor, "retention", "Retention is thirty days.\n"
                )
                assert _status(engine, old) == "superseded"
            finally:
                release.set()
            result = running.result(timeout=WAIT_SECONDS)
    finally:
        event.remove(retrieval_engine, "after_cursor_execute", listener)
        retrieval_engine.dispose()
    assert paused.is_set()
    old_chunks = {chunk.id for chunk in _chunks(engine, old)}
    replacement_chunks = {chunk.id for chunk in _chunks(engine, replacement)}
    assert _revisions_of(result) == {old}
    assert set(_hits(result, "lexical")) == old_chunks  # "retention" also matches the new text
    assert set(_hits(result, "vector")) == old_chunks
    assert not replacement_chunks & {item.chunk_id for item in result.items}
    assert {item.evidence.revision_no for item in result.items} == {1}


def test_indexing_completed_during_capture_is_invisible_to_that_capture(
    factory: sessionmaker[Session],
    engine: Engine,
    actor: ActorContext,
    vendor: UUID,
    test_database_url: URL,
) -> None:
    _ready(factory, engine, actor, vendor, "retention", "Retention is ninety days.\n")
    new = _ingest(factory, actor, vendor, "retention", "Retention is thirty days.\n")
    with transaction(factory) as session:
        pending_index = indexing.enqueue_index_revision(
            session, actor, revision_id=new, identity=HASH_IDENTITY
        ).index.id
    capture_engine = _engine(test_database_url)
    paused, release, listener = _pause_after(capture_engine, "clock_timestamp")
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            running = pool.submit(_capture, create_session_factory(capture_engine), actor, vendor)
            try:
                assert paused.wait(WAIT_SECONDS)
                assert _work(factory, production_registry()).exit_code == 0
                assert _index_status(engine, pending_index) == "ready"
            finally:
                release.set()
            with pytest.raises(SnapshotNotReadyError):
                running.result(timeout=WAIT_SECONDS)
    finally:
        event.remove(capture_engine, "after_cursor_execute", listener)
        capture_engine.dispose()
    assert [b.revision_id for b in _capture(factory, actor, vendor).bindings] == [new]


# --- transaction settings, timeouts and side effects ---------------------------------------------


def test_pooled_connections_return_with_their_default_settings(
    factory: sessionmaker[Session],
    engine: Engine,
    actor: ActorContext,
    vendor: UUID,
    test_database_url: URL,
) -> None:
    _ready(factory, engine, actor, vendor, "retention", "Retention is ninety days.\n")
    pooled = _engine(test_database_url, poolclass=QueuePool, pool_size=1, max_overflow=0)
    pids: list[int] = []

    def record(connection: Any, *args: Any) -> None:
        if "clock_timestamp" in args[1]:
            pids.append(connection.connection.dbapi_connection.info.backend_pid)

    event.listen(pooled, "after_cursor_execute", record)
    try:
        pooled_factory = create_session_factory(pooled)
        snapshot = _capture(pooled_factory, actor, vendor)
        _search(pooled_factory, actor, snapshot, "retention")
        with pooled.connect() as connection:
            settings = {
                name: connection.execute(text(f"SHOW {name}")).scalar_one()
                for name in ("transaction_isolation", "transaction_read_only", "statement_timeout")
            }
            pid = connection.execute(text("SELECT pg_backend_pid()")).scalar_one()
    finally:
        event.remove(pooled, "after_cursor_execute", record)
        pooled.dispose()
    assert pids == [pid, pid]  # the same pooled connection served both transactions
    assert settings == {
        "transaction_isolation": "read committed",
        "transaction_read_only": "off",
        "statement_timeout": "20s",
    }


def test_a_statement_exceeding_the_timeout_is_a_database_error(
    factory: sessionmaker[Session],
    engine: Engine,
    actor: ActorContext,
    vendor: UUID,
    test_database_url: URL,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ready(factory, engine, actor, vendor, "retention", "Retention is ninety days.\n")
    snapshot = _capture(factory, actor, vendor)
    monkeypatch.setattr(retrieval_store, "STATEMENT_TIMEOUT_MS", 200)  # test-lowered only
    slow = _engine(test_database_url)

    def stall(_connection: Any, cursor: Any, statement: str, *args: Any) -> None:
        if "AS verified" in statement:  # inside the seam's transaction, after SET LOCAL
            cursor.execute("SELECT pg_sleep(5)")

    event.listen(slow, "before_cursor_execute", stall)
    try:
        with pytest.raises(RetrievalDatabaseError) as raised:
            _search(create_session_factory(slow), actor, snapshot, "retention")
    finally:
        event.remove(slow, "before_cursor_execute", stall)
        slow.dispose()
    assert raised.value.__cause__ is None and raised.value.__context__ is None


def test_capture_and_retrieval_change_no_rows(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, vendor: UUID
) -> None:
    _ready(factory, engine, actor, vendor, "retention", "Retention is ninety days.\n")
    _create(factory, actor, vendor, "pending", "Pending.\n")
    before = _rows(engine)
    snapshot = _capture(factory, actor, vendor)
    _search(factory, actor, snapshot, "retention", "ninety days")
    assert _rows(engine) == before


def test_no_approximate_vector_index_exists(engine: Engine) -> None:
    with engine.connect() as connection:
        methods = set(
            connection.execute(
                text(
                    "SELECT am.amname FROM pg_index AS x "
                    "JOIN pg_class AS t ON t.oid = x.indrelid "
                    "JOIN pg_class AS i ON i.oid = x.indexrelid "
                    "JOIN pg_am AS am ON am.oid = i.relam "
                    "WHERE t.relname = 'chunk_embeddings'"
                )
            ).scalars()
        )
    assert methods and not methods & {"hnsw", "ivfflat"}


# --- evidence ------------------------------------------------------------------------------------


def test_evidence_matches_the_stored_rows_including_a_repeated_header(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, vendor: UUID
) -> None:
    revision = _ready(factory, engine, actor, vendor, "table", TABLE)
    chunks = _chunks(engine, revision)
    continuation = next(c for c in chunks if c.header_char_start is not None)
    last_row = continuation.text.rstrip().splitlines()[-1].split("|")[1].strip()  # e.g. "r59"
    snapshot = _capture(factory, actor, vendor)
    result = _search(factory, actor, snapshot, last_row)

    item = next(item for item in result.items if item.chunk_id == continuation.id)
    evidence = item.evidence
    with engine.connect() as connection:
        content = connection.execute(
            select(DocumentRevision.content_text).where(DocumentRevision.id == revision)
        ).scalar_one()
        document = connection.execute(
            select(Document.__table__).where(Document.active_revision_id == revision)
        ).one()
    assert evidence.text == continuation.text
    assert evidence.content_sha256 == continuation.content_sha256
    assert evidence.ordinal == continuation.ordinal and evidence.is_table
    assert evidence.section_path == tuple(continuation.section_path)
    assert evidence.header is not None
    assert (evidence.header.char_start, evidence.header.char_end) == (
        continuation.header_char_start,
        continuation.header_char_end,
    )
    assert (evidence.header.line_start, evidence.header.line_end) == (
        continuation.header_line_start,
        continuation.header_line_end,
    )
    assert (evidence.body.char_start, evidence.body.char_end) == (
        continuation.char_start,
        continuation.char_end,
    )
    assert (evidence.body.line_start, evidence.body.line_end) == (
        continuation.line_start,
        continuation.line_end,
    )
    header_slice = content[continuation.header_char_start : continuation.header_char_end]
    body_slice = content[continuation.char_start : continuation.char_end]
    assert evidence.header_text == header_slice and evidence.body_text == body_slice
    assert evidence.header.char_end < evidence.body.char_start  # not contiguous in the source
    assert evidence.document_key == document.document_key == "table"
    assert evidence.title == document.title and evidence.revision_no == 1
    assert evidence.source_type is SourceType.VENDOR_STATEMENT
    assert evidence.authenticity is Authenticity.NOT_ESTABLISHED
    assert evidence.version_label is None and evidence.effective_date is None
    assert item.revision_id == revision and item.document_id == document.id
    assert result.snapshot_sha256 == snapshot.sha256


# --- M5d composable capture equivalence (ADR-0022) -----------------------------------------------


def test_capture_in_transaction_matches_capture_snapshot_and_leaves_the_transaction_open(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, vendor: UUID
) -> None:
    from evidenceguard_persistence.retrieval import CaptureFailure, capture_in_transaction

    first = _ready(factory, engine, actor, vendor, "retention", "Retention is ninety days.\n")
    second = _ready(factory, engine, actor, vendor, "encryption", "Data is encrypted at rest.\n")
    pending = _create(factory, actor, vendor, "pending", "Pending.\n")
    before = _rows(engine)
    reference = _capture(factory, actor, vendor)
    with factory() as session:
        session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
        captured_at = session.execute(select(func.clock_timestamp())).scalar_one()
        composed = capture_in_transaction(
            session, captured_at, actor, vendor_id=vendor, identity=HASH_IDENTITY
        )
        assert session.in_transaction()  # the caller still owns the transaction
        assert session.execute(text("SELECT 1")).scalar_one() == 1
        session.rollback()
    assert not isinstance(composed, CaptureFailure)
    assert isinstance(composed, RetrievalSnapshot)
    assert composed.captured_at == captured_at
    assert composed.bindings == reference.bindings
    assert {b.revision_id for b in composed.bindings} == {first, second}
    assert composed.exclusions == reference.exclusions
    assert composed.exclusions.revision_ids == (pending,)
    assert (composed.tenant_id, composed.vendor_id) == (reference.tenant_id, reference.vendor_id)
    assert (composed.identity, composed.config) == (reference.identity, reference.config)
    assert composed.profile_id == reference.profile_id
    assert _rows(engine) == before
