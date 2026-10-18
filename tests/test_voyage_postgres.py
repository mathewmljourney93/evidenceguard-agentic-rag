"""PostgreSQL integration tests for the Voyage adapter with a mocked transport (M4f, ADR-0018).

They use the guarded disposable-database fixtures from ``conftest.py`` and are skipped without
``EG_TEST_DATABASE_URL`` (required in CI). The Voyage provider is the real ``VoyageEmbedder``
over an in-memory transport that answers with the offline hash vectors of each input (nonzero,
unit length, rows returned in reversed order), so the adapter's validation, the M4c handler,
M4b storage with ``allows_zero_vectors = false``, M4d capture and retrieval all run for a
non-offline profile against real pgvector. They prove storage and retrieval wiring only: the
transport is in memory (no ``HttpsVoyageTransport``, network, key or live provider), and nothing
here measures live Voyage behaviour.
"""

import json
from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, create_engine, func, insert, select
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_domain.embedding_storage import stored_embeddings
from evidenceguard_domain.evidence import SourceType
from evidenceguard_domain.jobs import JobPayload
from evidenceguard_domain.retrieval import RetrievalRequest
from evidenceguard_domain.revisions import RevisionContent
from evidenceguard_persistence import documents as revision_store
from evidenceguard_persistence import indexing
from evidenceguard_persistence import jobs as job_store
from evidenceguard_persistence.db import create_session_factory, transaction
from evidenceguard_persistence.models import Chunk as ChunkRow
from evidenceguard_persistence.models import (
    ChunkEmbedding,
    EmbeddingIndex,
    EmbeddingProfile,
    Job,
    Tenant,
    Vendor,
)
from evidenceguard_persistence.retrieval import capture_snapshot
from evidenceguard_retrieval.embeddings import HASH_IDENTITY, HashingEmbedder
from evidenceguard_retrieval.voyage import VOYAGE_IDENTITY, VoyageEmbedder, VoyageResponse
from evidenceguard_worker.indexing import INDEX_REVISION_KIND, make_index_revision_handler
from evidenceguard_worker.ingest import INGEST_REVISION_KIND, ingest_revision
from evidenceguard_worker.registry import HandlerRegistry
from evidenceguard_worker.retrieval import search_snapshot
from evidenceguard_worker.runtime import DatabaseJobStore, Timings, run_worker

pytestmark = pytest.mark.integration

MARKDOWN = "text/markdown"
TEXT = (
    "# Retention\n\nCustomer data is kept for 90 days.\n\n"
    "## Backups\n\nBackups are encrypted and kept for 30 days.\n"
)
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


class EchoTransport:
    """Answers each request with the offline hash vectors of its inputs, in reversed rows."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def post(self, body: bytes) -> VoyageResponse:
        request = json.loads(body)
        self.requests.append(request)
        texts = tuple(request["input"])
        batch = HashingEmbedder().embed(texts, request["input_type"])
        if not all(any(vector) for vector in batch.vectors):
            raise AssertionError("the fixture texts must hash to nonzero vectors")
        rows = [
            {"object": "embedding", "embedding": list(vector), "index": index}
            for index, vector in enumerate(batch.vectors)
        ]
        document = {
            "object": "list",
            "data": list(reversed(rows)),
            "model": "voyage-4-lite",
            "usage": {"total_tokens": len(texts)},
        }
        return VoyageResponse(200, json.dumps(document).encode())


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


def _tenant_and_vendor(engine: Engine) -> tuple[ActorContext, UUID]:
    tenant_id, vendor_id = uuid4(), uuid4()
    with engine.begin() as connection:
        connection.execute(insert(Tenant).values(id=tenant_id, slug="tenant-v", name="Tenant V"))
        connection.execute(
            insert(Vendor).values(id=vendor_id, tenant_id=tenant_id, slug="lumenvale", name="L")
        )
    return ActorContext(tenant_id=tenant_id, actor_id=uuid4(), role=Role.REVIEWER), vendor_id


def _ingest(factory: sessionmaker[Session], actor: ActorContext, vendor: UUID) -> UUID:
    with transaction(factory) as session:
        created = revision_store.create_revision(
            session,
            actor,
            vendor_id=vendor,
            document_key="data-retention",
            title="Data Retention",
            source_type=SourceType.VENDOR_STATEMENT,
            content=RevisionContent.from_bytes(TEXT.encode(), MARKDOWN),
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


def _index_with_voyage(
    factory: sessionmaker[Session], actor: ActorContext, revision: UUID, transport: EchoTransport
) -> indexing.IndexEnqueueResult:
    with transaction(factory) as session:
        enqueued = indexing.enqueue_index_revision(
            session, actor, revision_id=revision, identity=VOYAGE_IDENTITY
        )
    handler = make_index_revision_handler(
        {VOYAGE_IDENTITY.fingerprint: lambda: VoyageEmbedder(transport)}
    )
    registry = HandlerRegistry([(INDEX_REVISION_KIND, handler)])
    result = run_worker(
        DatabaseJobStore(factory), registry, worker_id="w-voyage", timings=TIMINGS, once=True
    )
    assert result.exit_code == 0
    return enqueued


def test_a_revision_is_indexed_through_the_mocked_voyage_adapter_into_pgvector(
    factory: sessionmaker[Session], engine: Engine
) -> None:
    actor, vendor = _tenant_and_vendor(engine)
    revision = _ingest(factory, actor, vendor)
    transport = EchoTransport()
    enqueued = _index_with_voyage(factory, actor, revision, transport)
    assert enqueued.job is not None

    with engine.connect() as connection:
        index = connection.execute(
            select(EmbeddingIndex.__table__).where(EmbeddingIndex.id == enqueued.index.id)
        ).one()
        profile = connection.execute(
            select(EmbeddingProfile.__table__).where(EmbeddingProfile.id == index.profile_id)
        ).one()
        job = connection.execute(select(Job.status).where(Job.id == enqueued.job.id)).scalar_one()
        chunks = connection.execute(
            select(ChunkRow.id, ChunkRow.text, ChunkRow.content_sha256)
            .where(ChunkRow.revision_id == revision)
            .order_by(ChunkRow.ordinal)
        ).all()
        stored = {
            row.chunk_id: row
            for row in connection.execute(
                select(
                    ChunkEmbedding.chunk_id,
                    ChunkEmbedding.vector_sha256,
                    ChunkEmbedding.is_zero,
                    func.vector_send(ChunkEmbedding.embedding).label("wire"),
                ).where(ChunkEmbedding.index_id == enqueued.index.id)
            )
        }

    assert index.status == "ready" and index.allows_zero_vectors is False
    assert (profile.provider_id, profile.model_id, profile.fingerprint) == (
        "voyage",
        "voyage-4-lite",
        VOYAGE_IDENTITY.fingerprint,
    )
    assert profile.allows_zero_vectors is False and job == "succeeded"
    assert len(stored) == index.chunk_count == len(chunks)
    expected = stored_embeddings(  # the same float values, canonicalized independently
        HashingEmbedder().embed(tuple(chunk.text for chunk in chunks), "document"),
        identity=HASH_IDENTITY,
        chunks=[(chunk.id, chunk.content_sha256) for chunk in chunks],
    )
    for row in expected:
        assert bytes(stored[row.chunk_id].wire) == row.vector.wire_bytes()
        assert stored[row.chunk_id].vector_sha256 == row.vector.sha256
        assert stored[row.chunk_id].is_zero is False
    assert [request["input_type"] for request in transport.requests] == ["document"]


def test_capture_and_search_snapshot_run_with_the_mocked_voyage_provider(
    factory: sessionmaker[Session], engine: Engine
) -> None:
    actor, vendor = _tenant_and_vendor(engine)
    revision = _ingest(factory, actor, vendor)
    _index_with_voyage(factory, actor, revision, EchoTransport())

    snapshot = capture_snapshot(factory, actor, vendor_id=vendor, identity=VOYAGE_IDENTITY)
    assert snapshot.identity == VOYAGE_IDENTITY
    assert [binding.revision_id for binding in snapshot.bindings] == [revision]

    transport = EchoTransport()
    result = search_snapshot(
        factory,
        actor,
        snapshot,
        RetrievalRequest(("backups encrypted", "customer data retention"), 3),
        VoyageEmbedder(transport),
    )
    assert [request["input_type"] for request in transport.requests] == ["query"]
    assert 1 <= len(result.items) <= 3
    assert {item.revision_id for item in result.items} == {revision}
    assert any(hit.key[1] == "vector" for item in result.items for hit in item.hits)
