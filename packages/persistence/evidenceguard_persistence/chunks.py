"""Fenced, idempotent chunk writes and the completeness check (M3d, ADR-0010).

Every function takes M3a's ``FencedSession`` and the fence's ``JobSnapshot``, scopes every
statement by the job's tenant, and never commits, rolls back or issues transaction-control SQL.
The revision is named only by the locked job's ``revision_id`` payload.

**The write protocol** (``write_chunk_set`` and ``write_chunks``), in one fenced transaction:

1. ``lock_revision_for_job`` (job → document → revision, with a fresh ownership re-check after
   the waits), then require the re-read revision to be ``processing``; otherwise the fixed
   ``ChunkWriteRefusedError``, before any insert;
2. ``INSERT … ON CONFLICT DO NOTHING RETURNING`` the key;
3. for every expected row not returned, read the stored row by its natural key and compare every
   immutable field. A missing row (the suppressed conflict was on another key) or any difference
   raises the fixed ``ChunkConflictError``. Nothing is ever overwritten, and ``created_at`` is
   never compared;
4. ``recheck_ownership`` again, after any unique-index waits and before the block commits.

Chunk writes, ``activate_revision`` and ``fail_revision`` all take the same document lock first,
so whichever holds it first finishes before the other proceeds, and no chunk or chunk-set row is
inserted after the revision settles.

**Completeness** (``require_complete_chunk_set``) runs as ``activate_revision``'s
``before_settle`` callback, bound to the current attempt's ``ExpectedChunkSet``. It reads stored
digests and spans, never the text. Trusting a stored digest relies on the application's
write-once invariant (each row was compared field by field, text included, when written); it adds
no protection against privileged direct database modification.

Errors carry fixed messages: never content, digests or IDs.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from sqlalchemy import Select, Table, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from evidenceguard_domain.chunks import (
    Chunk,
    ExpectedChunkSet,
    manifest_entry,
    manifest_sha256,
    within_batch_bounds,
)
from evidenceguard_domain.jobs import JobSnapshot, LeaseLostError
from evidenceguard_domain.revisions import (
    RevisionContent,
    RevisionSnapshot,
    RevisionStatus,
)
from evidenceguard_persistence.documents import (
    REVISIONS,
    RevisionNotFoundError,
    lock_revision_for_job,
)
from evidenceguard_persistence.jobs import FencedSession, recheck_ownership
from evidenceguard_persistence.models import CHUNK_SET_PRIMARY_KEY
from evidenceguard_persistence.models import Chunk as ChunkRow
from evidenceguard_persistence.models import ChunkSet as ChunkSetRow

CHUNK_SETS = cast(Table, ChunkSetRow.__table__)
CHUNKS = cast(Table, ChunkRow.__table__)
REVISION_ID_PAYLOAD_KEY = "revision_id"

# Every immutable chunk field compared on an idempotent retry (``created_at`` is metadata).
COMPARED_CHUNK_FIELDS = (
    "id",
    "chunker_version",
    "ordinal",
    "text",
    "content_sha256",
    "section_path",
    "is_table",
    "line_start",
    "line_end",
    "char_start",
    "char_end",
    "header_line_start",
    "header_line_end",
    "header_char_start",
    "header_char_end",
)
MANIFEST_COLUMNS = (
    "id",
    "ordinal",
    "content_sha256",
    "section_path",
    "is_table",
    "line_start",
    "line_end",
    "char_start",
    "char_end",
    "header_line_start",
    "header_line_end",
    "header_char_start",
    "header_char_end",
)


# --- errors (fixed messages) -------------------------------------------------------------------


class ChunkWriteRefusedError(Exception):
    """The revision is no longer ``processing`` (it settled or failed). Nothing was written."""

    def __init__(self) -> None:
        super().__init__("the revision is not being processed; no chunks were written")


class ChunkConflictError(Exception):
    """A stored chunk or chunk set differs from the expected one, or the expected row is missing
    after a suppressed conflict. Nothing was overwritten."""

    def __init__(self) -> None:
        super().__init__("stored chunks conflict with the expected chunks; nothing was changed")


class ChunkSetIncompleteError(Exception):
    """The stored chunk set is incomplete or differs from this attempt's expected set."""

    def __init__(self) -> None:
        super().__init__("the revision's chunk set is incomplete or differs from the expected set")


# --- source --------------------------------------------------------------------------------


@dataclass(frozen=True, repr=False)
class RevisionSource:
    """A revision's verified content for parsing. ``repr`` never shows the content."""

    revision_id: UUID
    status: RevisionStatus
    content: RevisionContent

    def __repr__(self) -> str:
        return (
            f"RevisionSource(revision_id={self.revision_id}, status={self.status.value!r}, "
            f"media_type={self.content.media_type.value!r}, byte_size={self.content.byte_size})"
        )

    __str__ = __repr__


def payload_revision_id(job: JobSnapshot) -> UUID:
    value = job.payload.as_dict().get(REVISION_ID_PAYLOAD_KEY)
    if value is None:
        raise RevisionNotFoundError()
    return UUID(value)


def revision_status_statement(tenant_id: UUID, revision_id: UUID) -> Select[Any]:
    return select(REVISIONS.c.status).where(
        REVISIONS.c.tenant_id == tenant_id, REVISIONS.c.id == revision_id
    )


def revision_source_statement(tenant_id: UUID, revision_id: UUID) -> Select[Any]:
    return select(
        REVISIONS.c.status,
        REVISIONS.c.media_type,
        REVISIONS.c.content_text,
        REVISIONS.c.sha256,
        REVISIONS.c.byte_size,
    ).where(REVISIONS.c.tenant_id == tenant_id, REVISIONS.c.id == revision_id)


def read_revision_status(session: FencedSession, job: JobSnapshot) -> RevisionStatus:
    """The revision's current status in the job's tenant, read without a lock."""
    value = session.scalar(revision_status_statement(job.tenant_id, payload_revision_id(job)))
    if value is None:
        raise RevisionNotFoundError()
    return RevisionStatus(value)


def load_revision_source(session: FencedSession, job: JobSnapshot) -> RevisionSource:
    """The revision's stored content, re-verified by ``RevisionContent.from_stored`` (hash, size
    and encoding). Takes no lock. A mismatch raises the domain's fixed
    ``InvalidRevisionContentError``."""
    revision_id = payload_revision_id(job)
    row = session.execute(revision_source_statement(job.tenant_id, revision_id)).first()
    if row is None:
        raise RevisionNotFoundError()
    content = RevisionContent.from_stored(
        media_type=row.media_type,
        content_text=row.content_text,
        sha256=row.sha256,
        byte_size=row.byte_size,
    )
    return RevisionSource(
        revision_id=revision_id, status=RevisionStatus(row.status), content=content
    )


# --- statements ----------------------------------------------------------------------------


def insert_chunk_set_statement(
    tenant_id: UUID, revision_id: UUID, expected: ExpectedChunkSet
) -> Any:
    return (
        pg_insert(CHUNK_SETS)
        .values(
            tenant_id=tenant_id,
            revision_id=revision_id,
            chunker_version=expected.chunker_version,
            chunk_count=expected.chunk_count,
            manifest_sha256=expected.manifest_sha256,
        )
        .on_conflict_do_nothing(constraint=CHUNK_SET_PRIMARY_KEY)
        .returning(CHUNK_SETS.c.tenant_id, CHUNK_SETS.c.revision_id)
    )


def chunk_set_statement(tenant_id: UUID, revision_id: UUID) -> Select[Any]:
    return select(
        CHUNK_SETS.c.chunker_version, CHUNK_SETS.c.chunk_count, CHUNK_SETS.c.manifest_sha256
    ).where(CHUNK_SETS.c.tenant_id == tenant_id, CHUNK_SETS.c.revision_id == revision_id)


def insert_chunks_statement(batch: Sequence[Chunk]) -> Any:
    """Without a conflict target, a conflict on **either** unique key (``id``, or
    ``(tenant_id, revision_id, chunker_version, ordinal)``) is suppressed."""
    return (
        pg_insert(CHUNKS)
        .values([_chunk_values(chunk) for chunk in batch])
        .on_conflict_do_nothing()
        .returning(CHUNKS.c.id)
    )


def stored_chunks_statement(
    tenant_id: UUID, revision_id: UUID, chunker_version: str, ordinals: Sequence[int]
) -> Select[Any]:
    return select(*(CHUNKS.c[name] for name in COMPARED_CHUNK_FIELDS)).where(
        CHUNKS.c.tenant_id == tenant_id,
        CHUNKS.c.revision_id == revision_id,
        CHUNKS.c.chunker_version == chunker_version,
        CHUNKS.c.ordinal.in_(sorted(ordinals)),
    )


def manifest_rows_statement(
    tenant_id: UUID, revision_id: UUID, chunker_version: str
) -> Select[Any]:
    """The stored manifest fields, in ordinal order. Never the text."""
    return (
        select(*(CHUNKS.c[name] for name in MANIFEST_COLUMNS))
        .where(
            CHUNKS.c.tenant_id == tenant_id,
            CHUNKS.c.revision_id == revision_id,
            CHUNKS.c.chunker_version == chunker_version,
        )
        .order_by(CHUNKS.c.ordinal)
    )


def _chunk_values(chunk: Chunk) -> dict[str, Any]:
    return {
        "id": chunk.id,
        "tenant_id": chunk.tenant_id,
        "revision_id": chunk.revision_id,
        "chunker_version": chunk.chunker_version,
        "ordinal": chunk.ordinal,
        "text": chunk.text,
        "content_sha256": chunk.content_sha256,
        "section_path": list(chunk.section_path),
        "is_table": chunk.is_table,
        "line_start": chunk.line_start,
        "line_end": chunk.line_end,
        "char_start": chunk.char_start,
        "char_end": chunk.char_end,
        "header_line_start": chunk.header_line_start,
        "header_line_end": chunk.header_line_end,
        "header_char_start": chunk.header_char_start,
        "header_char_end": chunk.header_char_end,
    }


def _comparable(values: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(
        tuple(values[name]) if name == "section_path" else values[name]
        for name in COMPARED_CHUNK_FIELDS
    )


# --- fenced writes -------------------------------------------------------------------------------


def write_chunk_set(session: FencedSession, job: JobSnapshot, expected: ExpectedChunkSet) -> None:
    """Insert the revision's chunk-set row, or verify the identical existing one."""
    if not isinstance(expected, ExpectedChunkSet):
        raise TypeError("expected must be an ExpectedChunkSet")
    target = _lock_processing(session, job)
    inserted = session.execute(
        insert_chunk_set_statement(job.tenant_id, target.id, expected)
    ).first()
    if inserted is None:
        stored = session.execute(chunk_set_statement(job.tenant_id, target.id)).first()
        if stored is None or (
            stored.chunker_version,
            stored.chunk_count,
            stored.manifest_sha256,
        ) != (expected.chunker_version, expected.chunk_count, expected.manifest_sha256):
            raise ChunkConflictError()
    _recheck(session, job)


def write_chunks(session: FencedSession, job: JobSnapshot, batch: Sequence[Chunk]) -> None:
    """Insert one bounded batch of the revision's chunks, verifying any that already exist."""
    chunks = tuple(batch)
    if not chunks or not all(isinstance(chunk, Chunk) for chunk in chunks):
        raise TypeError("batch must be a non-empty sequence of Chunk values")
    if not within_batch_bounds(chunks):
        raise ValueError("a chunk batch exceeds the batch bounds")
    revision_id = payload_revision_id(job)
    versions = {chunk.chunker_version for chunk in chunks}
    if len(versions) != 1 or any(
        chunk.tenant_id != job.tenant_id or chunk.revision_id != revision_id for chunk in chunks
    ):
        raise ValueError("every chunk in a batch must belong to the job's tenant and revision")
    if len({chunk.ordinal for chunk in chunks}) != len(chunks):
        raise ValueError("a chunk batch must not repeat an ordinal")

    _lock_processing(session, job)
    returned = set(session.execute(insert_chunks_statement(chunks)).scalars())
    existing = [chunk for chunk in chunks if chunk.id not in returned]
    if existing:
        (version,) = versions
        rows = session.execute(
            stored_chunks_statement(
                job.tenant_id, revision_id, version, [chunk.ordinal for chunk in existing]
            )
        )
        stored = {row.ordinal: _comparable(dict(row._mapping)) for row in rows}
        for chunk in existing:
            found = stored.get(chunk.ordinal)
            if found is None or found != _comparable(_chunk_values(chunk)):
                raise ChunkConflictError()
    _recheck(session, job)


def require_complete_chunk_set(
    session: FencedSession, revision: RevisionSnapshot, *, expected: ExpectedChunkSet
) -> None:
    """The ``before_settle`` check: the stored set must be exactly this attempt's expected set.

    Under ``activate_revision``'s locks: the chunk-set row exists with the expected chunker
    version and count; the stored chunks of that version are exactly ordinals ``0 … count-1``;
    the manifest rebuilt from their stored fields hashes to the stored digest; and that digest
    equals the expected one. Otherwise ``ChunkSetIncompleteError``, and nothing settles.
    """
    if not isinstance(expected, ExpectedChunkSet):
        raise TypeError("expected must be an ExpectedChunkSet")
    stored = session.execute(chunk_set_statement(revision.tenant_id, revision.id)).first()
    if (
        stored is None
        or stored.chunker_version != expected.chunker_version
        or stored.chunk_count != expected.chunk_count
    ):
        raise ChunkSetIncompleteError()
    rows = [
        dict(row._mapping)
        for row in session.execute(
            manifest_rows_statement(revision.tenant_id, revision.id, expected.chunker_version)
        )
    ]
    if [row["ordinal"] for row in rows] != list(range(expected.chunk_count)):
        raise ChunkSetIncompleteError()
    rebuilt = manifest_sha256(
        manifest_entry(**{name: row[name] for name in MANIFEST_COLUMNS}) for row in rows
    )
    if rebuilt != stored.manifest_sha256 or rebuilt != expected.manifest_sha256:
        raise ChunkSetIncompleteError()


# --- helpers ---------------------------------------------------------------------------------


def _lock_processing(session: FencedSession, job: JobSnapshot) -> RevisionSnapshot:
    locked = lock_revision_for_job(session, job, include_active=False)
    if locked.target.status is not RevisionStatus.PROCESSING:
        raise ChunkWriteRefusedError()
    return locked.target


def _recheck(session: FencedSession, job: JobSnapshot) -> None:
    """Fresh ownership after any unique-index waits, before the block commits."""
    fresh, _ = recheck_ownership(session, job.lease_token())
    if fresh.tenant_id != job.tenant_id:
        raise LeaseLostError()
