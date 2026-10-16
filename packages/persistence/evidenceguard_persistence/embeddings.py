"""Embedding profiles, indexes, fenced vector writes and readiness (M4b, ADR-0014).

**Metadata** (``ensure_profile``, ``create_index``) runs in the **caller's** transaction and
never commits, like ``create_revision`` and ``enqueue``, so M4c can create an index and its
``index_revision`` job together. Neither writes vectors or readiness. M4b wires no caller.

**Vector writes and readiness** (``write_embeddings``, ``mark_index_ready``) take M3a's
``FencedSession`` and the fence's ``JobSnapshot``; they never commit, roll back or issue
transaction-control SQL. Each one, in order:

1. binds the job: kind ``index_revision`` and a payload of exactly ``index_id`` (already a
   canonical UUID under M3a's payload validation), or the fixed ``IndexJobMismatchError``;
2. locks that index row ``FOR UPDATE``, looked up only by ``(job.tenant_id, index_id)``; a row
   missing from the job's tenant raises the fixed ``IndexNotFoundError``. Lock order is job row
   (held by the fence) → index row. No document, revision, chunk-set or chunk row is locked:
   everything else read here is immutable;
3. does its work under that lock;
4. on **every** successful path, including idempotent no-ops, re-checks ownership with
   ``recheck_ownership`` after the last lock or unique-index wait and requires the job's
   tenant, raising ``LeaseLostError`` otherwise.

A write batch is revalidated in full (1 to 32 canonical rows, distinct chunks, the zero policy)
**before any SQL**. Rows are inserted with ``ON CONFLICT DO NOTHING``; for each row not inserted
the stored ``content_sha256``, ``vector_sha256`` and ``is_zero`` are compared and any difference
raises ``EmbeddingConflictError``. Nothing is ever updated or deleted, and a ready index refuses
writes. ``mark_index_ready`` runs ``require_complete_index`` and then sets ``ready`` with a fresh
``clock_timestamp()``; called inside M3a's fence with ``fence.succeed()`` (the worker's
``ctx.fenced(finish=True)``), readiness and job success commit or roll back together.

**Completeness** (``require_complete_index``) checks the profile's stored identity and
fingerprint, the chunk set and its rebuilt manifest (reusing ``chunks.chunk_set_statement``,
``chunks.manifest_rows_statement``, ``MANIFEST_COLUMNS`` and the domain manifest helpers; it does
not call M3's activation callback), exact chunk membership with matching text digests, the row
count and the vector manifest. Stored vectors are verified through their CHECK-bound digests, so
coordinates are never transferred. Trusting stored values relies on the database constraints
and the application's write-once invariant; it adds no protection against privileged direct
database modification.

Errors carry fixed messages: never vectors, text, digests or IDs. A database rejection of an
insert is reported as the fixed ``EmbeddingStorageRejectedError`` without the driver error,
whose detail may contain row values.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import Select, Table, Update, and_, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Result
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.sql import Executable

from evidenceguard_domain.chunks import ExpectedChunkSet, manifest_entry, manifest_sha256
from evidenceguard_domain.embedding_storage import (
    STORED_DIMS,
    StoredEmbedding,
    allows_zero_vectors,
    index_id,
    profile_id,
    require_storable_identity,
    revalidate_rows,
    vector_manifest_sha256,
)
from evidenceguard_domain.embeddings import EmbeddingIdentity, InvalidEmbeddingError
from evidenceguard_domain.jobs import JobSnapshot, LeaseLostError
from evidenceguard_persistence.chunks import (
    CHUNKS,
    MANIFEST_COLUMNS,
    chunk_set_statement,
    manifest_rows_statement,
)
from evidenceguard_persistence.documents import REVISIONS
from evidenceguard_persistence.jobs import (
    LOCK_NOT_AVAILABLE,
    FencedSession,
    JobLockTimeoutError,
    recheck_ownership,
)
from evidenceguard_persistence.models import (
    EMBEDDING_PRIMARY_KEY,
    INDEX_SOURCE_KEY,
    PROFILE_FINGERPRINT_KEY,
    ChunkEmbedding,
    EmbeddingIndex,
    EmbeddingProfile,
)

PROFILES = cast(Table, EmbeddingProfile.__table__)
INDEXES = cast(Table, EmbeddingIndex.__table__)
EMBEDDINGS = cast(Table, ChunkEmbedding.__table__)
INDEX_REVISION_KIND = "index_revision"
INDEX_ID_PAYLOAD_KEY = "index_id"
BUILDING = "building"
READY = "ready"

PROFILE_FIELDS = (
    "id",
    "tenant_id",
    "provider_id",
    "model_id",
    "algorithm_version",
    "dims",
    "normalization",
    "fingerprint",
    "allows_zero_vectors",
)
INDEX_BINDING_FIELDS = (
    "id",
    "tenant_id",
    "revision_id",
    "chunker_version",
    "chunk_count",
    "manifest_sha256",
    "profile_id",
    "dims",
    "allows_zero_vectors",
)
INDEX_FIELDS = (*INDEX_BINDING_FIELDS, "status", "vector_manifest_sha256", "ready_at")
COMPARED_EMBEDDING_FIELDS = ("content_sha256", "vector_sha256", "is_zero")


# --- errors (fixed messages) -------------------------------------------------------------------


class EmbeddingProfileConflictError(Exception):
    """A stored profile differs from the expected identity. Nothing was changed."""

    def __init__(self) -> None:
        super().__init__("the stored embedding profile conflicts with the expected identity")


class IndexSourceNotEligibleError(Exception):
    """The revision is missing from the tenant, never activated, or has no chunk set."""

    def __init__(self) -> None:
        super().__init__("the revision is not eligible for an embedding index")


class IndexConflictError(Exception):
    """A stored index differs from the expected binding. Nothing was changed."""

    def __init__(self) -> None:
        super().__init__("the stored embedding index conflicts with the expected binding")


class IndexJobMismatchError(Exception):
    """The job is not an ``index_revision`` job with exactly an ``index_id`` payload."""

    def __init__(self) -> None:
        super().__init__("the job does not name an embedding index")


class IndexNotFoundError(Exception):
    """The job's index does not exist in the job's tenant."""

    def __init__(self) -> None:
        super().__init__("the embedding index was not found")


class EmbeddingProfileMismatchError(Exception):
    """The index's stored profile is not the caller's embedding identity."""

    def __init__(self) -> None:
        super().__init__("the embedding index uses a different profile")


class EmbeddingWriteRefusedError(Exception):
    """The index is already ready. Nothing was written."""

    def __init__(self) -> None:
        super().__init__("the embedding index is ready; no embeddings were written")


class EmbeddingSourceMismatchError(Exception):
    """A row names a chunk outside the index's revision, or with a different text digest."""

    def __init__(self) -> None:
        super().__init__("an embedding does not match a chunk of the indexed revision")


class EmbeddingConflictError(Exception):
    """A stored embedding differs from the expected one. Nothing was overwritten."""

    def __init__(self) -> None:
        super().__init__("stored embeddings conflict with the expected embeddings")


class EmbeddingStorageRejectedError(Exception):
    """PostgreSQL rejected an embedding insert (a constraint). Nothing was written."""

    def __init__(self) -> None:
        super().__init__("the database rejected the embeddings; nothing was written")


class IndexIncompleteError(Exception):
    """The index's stored state is incomplete or inconsistent. Nothing changed."""

    def __init__(self) -> None:
        super().__init__("the embedding index is incomplete or inconsistent")


# --- snapshots ----------------------------------------------------------------------------


@dataclass(frozen=True)
class ProfileSnapshot:
    id: UUID
    tenant_id: UUID
    provider_id: str
    model_id: str
    algorithm_version: str
    dims: int
    normalization: str
    fingerprint: str
    allows_zero_vectors: bool


@dataclass(frozen=True)
class IndexSnapshot:
    id: UUID
    tenant_id: UUID
    revision_id: UUID
    chunker_version: str
    chunk_count: int
    manifest_sha256: str
    profile_id: UUID
    dims: int
    allows_zero_vectors: bool
    status: str
    vector_manifest_sha256: str | None
    ready_at: datetime | None


def _profile(row: Any) -> ProfileSnapshot:
    return ProfileSnapshot(**{name: row._mapping[name] for name in PROFILE_FIELDS})


def _index(row: Any) -> IndexSnapshot:
    return IndexSnapshot(**{name: row._mapping[name] for name in INDEX_FIELDS})


# --- statements ----------------------------------------------------------------------------


def insert_profile_statement(tenant_id: UUID, identity: EmbeddingIdentity) -> Any:
    fingerprint = identity.fingerprint
    return (
        pg_insert(PROFILES)
        .values(
            id=profile_id(tenant_id, fingerprint),
            tenant_id=tenant_id,
            provider_id=identity.provider_id,
            model_id=identity.model_id,
            algorithm_version=identity.algorithm_version,
            dims=identity.dims,
            normalization=identity.normalization,
            fingerprint=fingerprint,
            allows_zero_vectors=allows_zero_vectors(identity),
        )
        .on_conflict_do_nothing(constraint=PROFILE_FINGERPRINT_KEY)
        .returning(PROFILES.c.id)
    )


def profile_by_fingerprint_statement(tenant_id: UUID, fingerprint: str) -> Select[Any]:
    return select(*(PROFILES.c[name] for name in PROFILE_FIELDS)).where(
        PROFILES.c.tenant_id == tenant_id, PROFILES.c.fingerprint == fingerprint
    )


def profile_statement(tenant_id: UUID, profile: UUID) -> Select[Any]:
    return select(*(PROFILES.c[name] for name in PROFILE_FIELDS)).where(
        PROFILES.c.tenant_id == tenant_id, PROFILES.c.id == profile
    )


def revision_activation_statement(tenant_id: UUID, revision_id: UUID) -> Select[Any]:
    """The revision's ``activated_at``, which is never cleared once set. Read without a lock."""
    return select(REVISIONS.c.activated_at).where(
        REVISIONS.c.tenant_id == tenant_id, REVISIONS.c.id == revision_id
    )


def insert_index_statement(values: dict[str, Any]) -> Any:
    return (
        pg_insert(INDEXES)
        .values(**values)
        .on_conflict_do_nothing(constraint=INDEX_SOURCE_KEY)
        .returning(INDEXES.c.id)
    )


def index_statement(tenant_id: UUID, index: UUID) -> Select[Any]:
    return select(*(INDEXES.c[name] for name in INDEX_FIELDS)).where(
        INDEXES.c.tenant_id == tenant_id, INDEXES.c.id == index
    )


def lock_index_statement(tenant_id: UUID, index: UUID) -> Select[Any]:
    return index_statement(tenant_id, index).with_for_update()


def chunk_digests_statement(index: IndexSnapshot, chunk_ids: Sequence[UUID]) -> Select[Any]:
    return select(CHUNKS.c.id, CHUNKS.c.content_sha256).where(
        CHUNKS.c.tenant_id == index.tenant_id,
        CHUNKS.c.revision_id == index.revision_id,
        CHUNKS.c.chunker_version == index.chunker_version,
        CHUNKS.c.id.in_(sorted(chunk_ids)),
    )


def insert_embeddings_statement(index: IndexSnapshot, rows: Sequence[StoredEmbedding]) -> Any:
    return (
        pg_insert(EMBEDDINGS)
        .values([_embedding_values(index, row) for row in rows])
        .on_conflict_do_nothing(constraint=EMBEDDING_PRIMARY_KEY)
        .returning(EMBEDDINGS.c.chunk_id)
    )


def stored_embeddings_statement(index: IndexSnapshot, chunk_ids: Sequence[UUID]) -> Select[Any]:
    return select(
        EMBEDDINGS.c.chunk_id, *(EMBEDDINGS.c[name] for name in COMPARED_EMBEDDING_FIELDS)
    ).where(
        EMBEDDINGS.c.tenant_id == index.tenant_id,
        EMBEDDINGS.c.index_id == index.id,
        EMBEDDINGS.c.chunk_id.in_(sorted(chunk_ids)),
    )


def membership_statement(index: IndexSnapshot) -> Select[Any]:
    """Every chunk of the index's revision and chunker version, in ordinal order, with this
    index's embedding for it (if any). Never the text or the vector."""
    joined = CHUNKS.outerjoin(
        EMBEDDINGS,
        and_(
            EMBEDDINGS.c.tenant_id == CHUNKS.c.tenant_id,
            EMBEDDINGS.c.index_id == index.id,
            EMBEDDINGS.c.chunk_id == CHUNKS.c.id,
        ),
    )
    return (
        select(
            CHUNKS.c.ordinal,
            CHUNKS.c.id,
            CHUNKS.c.content_sha256,
            EMBEDDINGS.c.chunk_id.label("embedded_chunk_id"),
            EMBEDDINGS.c.content_sha256.label("embedded_content_sha256"),
            EMBEDDINGS.c.vector_sha256,
        )
        .select_from(joined)
        .where(
            CHUNKS.c.tenant_id == index.tenant_id,
            CHUNKS.c.revision_id == index.revision_id,
            CHUNKS.c.chunker_version == index.chunker_version,
        )
        .order_by(CHUNKS.c.ordinal)
    )


def embedding_count_statement(index: IndexSnapshot) -> Select[Any]:
    return select(func.count()).where(
        EMBEDDINGS.c.tenant_id == index.tenant_id, EMBEDDINGS.c.index_id == index.id
    )


def mark_ready_statement(index: IndexSnapshot, vector_manifest: str) -> Update:
    return (
        update(INDEXES)
        .where(
            INDEXES.c.tenant_id == index.tenant_id,
            INDEXES.c.id == index.id,
            INDEXES.c.status == BUILDING,
        )
        .values(
            status=READY,
            ready_at=func.clock_timestamp(),
            vector_manifest_sha256=vector_manifest,
        )
        .returning(*(INDEXES.c[name] for name in INDEX_FIELDS))
    )


def vector_bytes_statement(tenant_id: UUID, index: UUID, chunk: UUID) -> Select[Any]:
    """The stored vector's exact float32 bytes (``vector_send``), for the read path."""
    return select(func.vector_send(EMBEDDINGS.c.embedding).label("wire")).where(
        EMBEDDINGS.c.tenant_id == tenant_id,
        EMBEDDINGS.c.index_id == index,
        EMBEDDINGS.c.chunk_id == chunk,
    )


def _embedding_values(index: IndexSnapshot, row: StoredEmbedding) -> dict[str, Any]:
    return {
        "tenant_id": index.tenant_id,
        "index_id": index.id,
        "chunk_id": row.chunk_id,
        "revision_id": index.revision_id,
        "chunker_version": index.chunker_version,
        "allows_zero_vectors": index.allows_zero_vectors,
        "content_sha256": row.content_sha256,
        "embedding": row.vector.literal(),
        "vector_sha256": row.vector.sha256,
        "is_zero": row.vector.is_zero,
    }


# --- metadata in the caller's transaction ---------------------------------------------------


def ensure_profile(
    session: Session, tenant_id: UUID, identity: EmbeddingIdentity
) -> ProfileSnapshot:
    """Insert the tenant's profile for ``identity``, or verify the identical existing one."""
    checked = require_storable_identity(identity)
    session.execute(insert_profile_statement(tenant_id, checked))
    row = session.execute(profile_by_fingerprint_statement(tenant_id, checked.fingerprint)).first()
    if row is None:
        raise EmbeddingProfileConflictError()
    stored = _profile(row)
    if stored != _expected_profile(tenant_id, checked):
        raise EmbeddingProfileConflictError()
    return stored


def create_index(
    session: Session, tenant_id: UUID, revision_id: UUID, profile: ProfileSnapshot
) -> IndexSnapshot:
    """Create the ``building`` index for the revision's chunk set and the profile, or verify the
    identical existing one. The revision must exist in the tenant and have been activated."""
    if not isinstance(profile, ProfileSnapshot) or profile.tenant_id != tenant_id:
        raise IndexSourceNotEligibleError()
    activation = session.execute(revision_activation_statement(tenant_id, revision_id)).first()
    if activation is None or activation.activated_at is None:
        raise IndexSourceNotEligibleError()
    chunk_set = session.execute(chunk_set_statement(tenant_id, revision_id)).first()
    if chunk_set is None:
        raise IndexSourceNotEligibleError()
    stored_profile = session.execute(profile_statement(tenant_id, profile.id)).first()
    if stored_profile is None or _profile(stored_profile) != profile:
        raise EmbeddingProfileConflictError()

    binding = {
        "id": index_id(tenant_id, revision_id, chunk_set.chunker_version, profile.id),
        "tenant_id": tenant_id,
        "revision_id": revision_id,
        "chunker_version": chunk_set.chunker_version,
        "chunk_count": chunk_set.chunk_count,
        "manifest_sha256": chunk_set.manifest_sha256,
        "profile_id": profile.id,
        "dims": profile.dims,
        "allows_zero_vectors": profile.allows_zero_vectors,
    }
    session.execute(insert_index_statement(binding))
    row = session.execute(index_statement(tenant_id, binding["id"])).first()
    if row is None:
        raise IndexConflictError()
    stored = _index(row)
    if any(getattr(stored, name) != binding[name] for name in INDEX_BINDING_FIELDS):
        raise IndexConflictError()
    return stored


def _expected_profile(tenant_id: UUID, identity: EmbeddingIdentity) -> ProfileSnapshot:
    fingerprint = identity.fingerprint
    return ProfileSnapshot(
        id=profile_id(tenant_id, fingerprint),
        tenant_id=tenant_id,
        provider_id=identity.provider_id,
        model_id=identity.model_id,
        algorithm_version=identity.algorithm_version,
        dims=identity.dims,
        normalization=identity.normalization,
        fingerprint=fingerprint,
        allows_zero_vectors=allows_zero_vectors(identity),
    )


# --- fenced writes and readiness ----------------------------------------------------------------


def write_embeddings(
    session: FencedSession,
    job: JobSnapshot,
    identity: EmbeddingIdentity,
    rows: Sequence[StoredEmbedding],
) -> None:
    """Insert one bounded batch of canonical embeddings, verifying any that already exist."""
    checked_identity = require_storable_identity(identity)
    batch = revalidate_rows(rows, allows_zero=allows_zero_vectors(checked_identity))

    index = _bind(session, job)
    if index.status != BUILDING:
        raise EmbeddingWriteRefusedError()
    _require_profile(session, index, checked_identity)

    chunk_ids = [row.chunk_id for row in batch]
    digests = {
        row.id: row.content_sha256
        for row in session.execute(chunk_digests_statement(index, chunk_ids))
    }
    if any(digests.get(row.chunk_id) != row.content_sha256 for row in batch):
        raise EmbeddingSourceMismatchError()

    rejected = False
    try:
        returned = set(session.execute(insert_embeddings_statement(index, batch)).scalars())
    except IntegrityError:
        rejected = True
        returned = set()
    if rejected:  # raised outside the handler, so the driver error is not attached
        raise EmbeddingStorageRejectedError()

    existing = [row for row in batch if row.chunk_id not in returned]
    if existing:
        stored = {
            found.chunk_id: tuple(found._mapping[name] for name in COMPARED_EMBEDDING_FIELDS)
            for found in session.execute(
                stored_embeddings_statement(index, [row.chunk_id for row in existing])
            )
        }
        for row in existing:
            expected = (row.content_sha256, row.vector.sha256, row.vector.is_zero)
            if stored.get(row.chunk_id) != expected:
                raise EmbeddingConflictError()
    _recheck(session, job, index)


def mark_index_ready(
    session: FencedSession, job: JobSnapshot, identity: EmbeddingIdentity
) -> IndexSnapshot:
    """Verify the job's index is complete and mark it ``ready``; a no-op if it already is."""
    checked_identity = require_storable_identity(identity)
    index = _bind(session, job)
    if index.status == READY:
        _require_profile(session, index, checked_identity)
        _recheck(session, job, index)
        return index
    vector_manifest = require_complete_index(session, index, checked_identity)
    row = session.execute(mark_ready_statement(index, vector_manifest)).first()
    if row is None:
        raise IndexIncompleteError()
    _recheck(session, job, index)
    return _index(row)


def require_complete_index(
    session: FencedSession, index: IndexSnapshot, identity: EmbeddingIdentity
) -> str:
    """Return the vector manifest of a complete, consistent index, or raise
    ``IndexIncompleteError``. Call it with the index row locked."""
    checked_identity = require_storable_identity(identity)
    _require_complete_profile(session, index, checked_identity)
    _require_complete_chunk_set(session, index)

    members = list(session.execute(membership_statement(index)))
    if [row.ordinal for row in members] != list(range(index.chunk_count)):
        raise IndexIncompleteError()
    for row in members:
        if row.embedded_chunk_id is None or row.embedded_content_sha256 != row.content_sha256:
            raise IndexIncompleteError()
    if session.scalar(embedding_count_statement(index)) != index.chunk_count:
        raise IndexIncompleteError()
    return vector_manifest_sha256(
        (row.ordinal, row.id, row.content_sha256, row.vector_sha256) for row in members
    )


# --- helpers ---------------------------------------------------------------------------------


def _bind(session: FencedSession, job: JobSnapshot) -> IndexSnapshot:
    """Bind the fence's job to its index and lock that row (job → index)."""
    if job.kind != INDEX_REVISION_KIND:
        raise IndexJobMismatchError()
    payload = job.payload.as_dict()
    if set(payload) != {INDEX_ID_PAYLOAD_KEY}:
        raise IndexJobMismatchError()
    row = _locking(
        session, lock_index_statement(job.tenant_id, UUID(payload[INDEX_ID_PAYLOAD_KEY]))
    )
    found = row.first()
    if found is None:
        raise IndexNotFoundError()
    index = _index(found)
    if index.tenant_id != job.tenant_id:
        raise IndexNotFoundError()
    return index


def _require_profile(
    session: FencedSession, index: IndexSnapshot, identity: EmbeddingIdentity
) -> ProfileSnapshot:
    row = session.execute(profile_statement(index.tenant_id, index.profile_id)).first()
    if row is None:
        raise EmbeddingProfileMismatchError()
    profile = _profile(row)
    if profile.fingerprint != identity.fingerprint:
        raise EmbeddingProfileMismatchError()
    return profile


def _require_complete_profile(
    session: FencedSession, index: IndexSnapshot, identity: EmbeddingIdentity
) -> None:
    row = session.execute(profile_statement(index.tenant_id, index.profile_id)).first()
    if row is None:
        raise IndexIncompleteError()
    profile = _profile(row)
    invalid = False
    try:
        stored_identity = EmbeddingIdentity(
            profile.provider_id,
            profile.model_id,
            profile.algorithm_version,
            profile.dims,
            cast(Any, profile.normalization),
        )
    except InvalidEmbeddingError:
        invalid = True
    if invalid:
        raise IndexIncompleteError()
    if (
        stored_identity.fingerprint != profile.fingerprint
        or profile.fingerprint != identity.fingerprint
        or profile.id != profile_id(index.tenant_id, profile.fingerprint)
        or profile.dims != STORED_DIMS
        or index.dims != STORED_DIMS
        or profile.allows_zero_vectors != index.allows_zero_vectors
    ):
        raise IndexIncompleteError()


def _require_complete_chunk_set(session: FencedSession, index: IndexSnapshot) -> None:
    """The index's bound chunk set, verified from stored fields with M3d's public statements
    and the domain manifest helpers. No revision is locked and no ``RevisionSnapshot`` is
    built; M3's activation callback is not called."""
    invalid = False
    try:
        expected = ExpectedChunkSet(
            chunker_version=index.chunker_version,
            chunk_count=index.chunk_count,
            manifest_sha256=index.manifest_sha256,
        )
    except ValueError:
        invalid = True
    if invalid:
        raise IndexIncompleteError()
    stored = session.execute(chunk_set_statement(index.tenant_id, index.revision_id)).first()
    if stored is None or (
        stored.chunker_version,
        stored.chunk_count,
        stored.manifest_sha256,
    ) != (expected.chunker_version, expected.chunk_count, expected.manifest_sha256):
        raise IndexIncompleteError()
    rows = [
        dict(row._mapping)
        for row in session.execute(
            manifest_rows_statement(index.tenant_id, index.revision_id, expected.chunker_version)
        )
    ]
    if [row["ordinal"] for row in rows] != list(range(expected.chunk_count)):
        raise IndexIncompleteError()
    rebuilt = manifest_sha256(
        manifest_entry(**{name: row[name] for name in MANIFEST_COLUMNS}) for row in rows
    )
    if rebuilt != stored.manifest_sha256 or rebuilt != expected.manifest_sha256:
        raise IndexIncompleteError()


def _recheck(session: FencedSession, job: JobSnapshot, index: IndexSnapshot) -> None:
    """Fresh ownership after the lock and any unique-index waits, before the block commits."""
    fresh, _ = recheck_ownership(session, job.lease_token())
    if fresh.tenant_id != job.tenant_id or fresh.tenant_id != index.tenant_id:
        raise LeaseLostError()


def _locking(session: FencedSession, statement: Executable) -> Result[Any]:
    try:
        return session.execute(statement)
    except OperationalError as error:
        if getattr(error.orig, "sqlstate", None) == LOCK_NOT_AVAILABLE:
            raise JobLockTimeoutError() from None
        raise
