"""Tenant-scoped document read models and atomic upload creation (M3e, ADR-0011).

**Reads.** Every read operation runs inside ``read_snapshot``: one short transaction whose
**first statement** is ``SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY``, followed by
one ``clock_timestamp()`` read. Every query of one response therefore sees the same snapshot, and
every ``lease_expired`` in it is computed against that single database time. The setting is
transaction-scoped: PostgreSQL discards it at the end of the transaction, so a pooled connection
keeps its defaults (READ COMMITTED, read-write). The snapshot is consistent **within one
response** only, never across separate requests. Results are immutable values built inside the
transaction, which always ends (rolled back: nothing was written) before the caller returns.

Every statement is filtered by the actor's tenant, and every child lookup is filtered by its
parent: vendor → document → revision → chunk set → chunks. A parent outside the tenant yields
``None``, which the API reports as 404. Revision reads never select ``content_text``. No read
creates jobs, changes revisions or repairs anything.

**Upload creation** (``create_upload``) runs in the **caller's** write transaction, at the
default READ COMMITTED isolation: ``create_revision``, then ``enqueue`` of the canonical
ingestion job (for a new revision, or idempotently for an unsettled duplicate), then **one**
statement observing the revision, its canonical job and the database time. The caller commits
and only then returns that observation; nothing is re-read after the commit.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import Select, String, Table, and_, func, select, text
from sqlalchemy import cast as sql_cast
from sqlalchemy.orm import Session, sessionmaker

from evidenceguard_domain.context import ActorContext
from evidenceguard_domain.evidence import SourceType
from evidenceguard_domain.ingestion import (
    INGEST_REVISION_KIND,
    IngestionState,
    derive_ingestion_state,
    lease_expired,
)
from evidenceguard_domain.jobs import JobErrorCode, JobPayload, JobStatus
from evidenceguard_domain.revisions import (
    MediaType,
    RevisionContent,
    RevisionFailureCode,
    RevisionStatus,
)
from evidenceguard_persistence.documents import create_revision
from evidenceguard_persistence.jobs import enqueue
from evidenceguard_persistence.models import Chunk as ChunkRow
from evidenceguard_persistence.models import ChunkSet as ChunkSetRow
from evidenceguard_persistence.models import Document, DocumentRevision, Job, Vendor

DOCUMENTS = cast(Table, Document.__table__)
REVISIONS = cast(Table, DocumentRevision.__table__)
JOBS = cast(Table, Job.__table__)
CHUNK_SETS = cast(Table, ChunkSetRow.__table__)
CHUNKS = cast(Table, ChunkRow.__table__)
VENDORS = cast(Table, Vendor.__table__)

READ_SNAPSHOT_SQL = "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
REVISION_ID_PAYLOAD_KEY = "revision_id"
# Job kinds whose status may be shown through the API (reviewed fields only).
VIEWABLE_JOB_KINDS = frozenset({INGEST_REVISION_KIND})
UNSETTLED_STATUSES = frozenset({RevisionStatus.PENDING, RevisionStatus.PROCESSING})
VERIFIED_SET_STATUSES = frozenset({RevisionStatus.ACTIVE, RevisionStatus.SUPERSEDED})

# Revision columns for views: everything except the content.
_REVISION_VIEW_COLUMNS = tuple(column for column in REVISIONS.c if column.name != "content_text")


# --- values (immutable; never content except ChunkRecord.text) ----------------------------------


@dataclass(frozen=True)
class JobSummaryRecord:
    id: UUID
    status: JobStatus
    attempt: int
    max_attempts: int
    lease_expires_at: datetime | None
    lease_expired: bool | None


@dataclass(frozen=True)
class RevisionRecord:
    id: UUID
    revision_no: int
    version_label: str | None
    effective_date: date | None
    media_type: MediaType
    byte_size: int
    sha256: str
    status: RevisionStatus
    failure_reason: RevisionFailureCode | None
    activated_at: datetime | None
    failed_at: datetime | None
    superseded_at: datetime | None
    superseded_by_revision_id: UUID | None
    created_at: datetime
    updated_at: datetime
    ingestion_state: IngestionState
    ingestion_job: JobSummaryRecord | None


@dataclass(frozen=True)
class DocumentRecord:
    id: UUID
    vendor_id: UUID
    document_key: str
    title: str
    source_type: SourceType
    authenticity: str
    latest_revision_no: int
    active_revision_id: UUID | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class DocumentDetailRecord:
    document: DocumentRecord
    active_revision: RevisionRecord | None
    latest_revision: RevisionRecord | None


@dataclass(frozen=True)
class DocumentPageRecord:
    items: tuple[DocumentRecord, ...]
    total: int


@dataclass(frozen=True)
class RevisionPageRecord:
    items: tuple[RevisionRecord, ...]
    total: int


@dataclass(frozen=True)
class ChunkSetRecord:
    chunker_version: str
    chunk_count: int
    stored_count: int
    verified_complete: bool


@dataclass(frozen=True, repr=False)
class ChunkRecord:
    id: UUID
    ordinal: int
    text: str
    content_sha256: str
    section_path: tuple[str, ...]
    is_table: bool
    line_start: int
    line_end: int
    char_start: int
    char_end: int
    header_line_start: int | None
    header_line_end: int | None
    header_char_start: int | None
    header_char_end: int | None

    def __repr__(self) -> str:  # never the text or section path
        return f"ChunkRecord(id={self.id}, ordinal={self.ordinal}, chars={len(self.text)})"


@dataclass(frozen=True)
class ChunkPageRecord:
    chunk_set: ChunkSetRecord | None
    items: tuple[ChunkRecord, ...]
    total: int


@dataclass(frozen=True)
class JobViewRecord:
    id: UUID
    kind: str
    status: JobStatus
    attempt: int
    max_attempts: int
    run_after: datetime
    last_error: JobErrorCode | None
    lease_expires_at: datetime | None
    lease_expired: bool | None
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None


@dataclass(frozen=True)
class UploadRecord:
    """What the creation transaction observed, after its writes and before its commit."""

    created: bool
    document_id: UUID
    revision_id: UUID
    revision_no: int
    revision_status: RevisionStatus
    ingestion_state: IngestionState
    job: JobSummaryRecord | None


# --- the read snapshot -------------------------------------------------------------------------


@contextmanager
def read_snapshot(session_factory: sessionmaker[Session]) -> Iterator[tuple[Session, datetime]]:
    """A REPEATABLE READ, READ ONLY transaction and its single database time.

    ``SET TRANSACTION`` is the transaction's first statement; the second reads
    ``clock_timestamp()``. The transaction is always rolled back and the session closed when the
    block ends, so nothing is held open while a response is sent.
    """
    session = session_factory()
    try:
        session.execute(text(READ_SNAPSHOT_SQL))
        now: datetime = session.execute(select(func.clock_timestamp())).scalar_one()
        yield session, now
    finally:
        try:
            session.rollback()
        finally:
            session.close()


# --- statements --------------------------------------------------------------------------------


def _canonical_job_join() -> Any:
    return and_(
        JOBS.c.tenant_id == REVISIONS.c.tenant_id,
        JOBS.c.kind == INGEST_REVISION_KIND,
        JOBS.c.idempotency_key == sql_cast(REVISIONS.c.id, String),
    )


def revisions_with_job_statement() -> Select[Any]:
    """Revision view columns with the canonical job's reviewed fields (left join)."""
    return select(
        *_REVISION_VIEW_COLUMNS,
        JOBS.c.id.label("job_id"),
        JOBS.c.status.label("job_status"),
        JOBS.c.attempt.label("job_attempt"),
        JOBS.c.max_attempts.label("job_max_attempts"),
        JOBS.c.lease_expires_at.label("job_lease_expires_at"),
    ).select_from(REVISIONS.outerjoin(JOBS, _canonical_job_join()))


def _document_statement(tenant_id: UUID, document_id: UUID) -> Select[Any]:
    return select(DOCUMENTS).where(
        DOCUMENTS.c.tenant_id == tenant_id, DOCUMENTS.c.id == document_id
    )


# --- row conversion ----------------------------------------------------------------------------


def _job_summary(row: Any, now: datetime) -> JobSummaryRecord | None:
    if row.job_id is None:
        return None
    status = JobStatus(row.job_status)
    return JobSummaryRecord(
        id=row.job_id,
        status=status,
        attempt=row.job_attempt,
        max_attempts=row.job_max_attempts,
        lease_expires_at=row.job_lease_expires_at if status is JobStatus.RUNNING else None,
        lease_expired=lease_expired(status, row.job_lease_expires_at, now=now),
    )


def _revision(row: Any, now: datetime) -> RevisionRecord:
    status = RevisionStatus(row.status)
    job = _job_summary(row, now)
    return RevisionRecord(
        id=row.id,
        revision_no=row.revision_no,
        version_label=row.version_label,
        effective_date=row.effective_date,
        media_type=MediaType(row.media_type),
        byte_size=row.byte_size,
        sha256=row.sha256,
        status=status,
        failure_reason=(
            None if row.failure_reason is None else RevisionFailureCode(row.failure_reason)
        ),
        activated_at=row.activated_at,
        failed_at=row.failed_at,
        superseded_at=row.superseded_at,
        superseded_by_revision_id=row.superseded_by_revision_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        ingestion_state=derive_ingestion_state(status, None if job is None else job.status),
        ingestion_job=job,
    )


def _document(row: Any) -> DocumentRecord:
    return DocumentRecord(
        id=row.id,
        vendor_id=row.vendor_id,
        document_key=row.document_key,
        title=row.title,
        source_type=SourceType(row.source_type),
        authenticity=row.authenticity,
        latest_revision_no=row.latest_revision_no,
        active_revision_id=row.active_revision_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


# --- reads (inside read_snapshot) -----------------------------------------------------------------


def vendor_exists(session: Session, actor: ActorContext, vendor_id: UUID) -> bool:
    found = session.execute(
        select(VENDORS.c.id).where(
            VENDORS.c.tenant_id == actor.tenant_id, VENDORS.c.id == vendor_id
        )
    ).first()
    return found is not None


def list_documents(
    session: Session, actor: ActorContext, vendor_id: UUID, *, limit: int, offset: int
) -> DocumentPageRecord | None:
    """The vendor's documents ordered by ``(document_key, id)``; ``None`` if the vendor is not
    in the tenant."""
    if not vendor_exists(session, actor, vendor_id):
        return None
    scope = and_(DOCUMENTS.c.tenant_id == actor.tenant_id, DOCUMENTS.c.vendor_id == vendor_id)
    total = session.execute(select(func.count()).select_from(DOCUMENTS).where(scope)).scalar_one()
    rows = session.execute(
        select(DOCUMENTS)
        .where(scope)
        .order_by(DOCUMENTS.c.document_key, DOCUMENTS.c.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return DocumentPageRecord(items=tuple(_document(row) for row in rows), total=total)


def _revision_where(tenant_id: UUID, document_id: UUID, *conditions: Any) -> Select[Any]:
    return revisions_with_job_statement().where(
        REVISIONS.c.tenant_id == tenant_id, REVISIONS.c.document_id == document_id, *conditions
    )


def get_document(
    session: Session, actor: ActorContext, document_id: UUID, *, now: datetime
) -> DocumentDetailRecord | None:
    row = session.execute(_document_statement(actor.tenant_id, document_id)).first()
    if row is None:
        return None
    document = _document(row)
    active = None
    if document.active_revision_id is not None:
        active_row = session.execute(
            _revision_where(
                actor.tenant_id, document.id, REVISIONS.c.id == document.active_revision_id
            )
        ).first()
        active = None if active_row is None else _revision(active_row, now)
    latest = None
    if document.latest_revision_no > 0:
        latest_row = session.execute(
            _revision_where(
                actor.tenant_id, document.id, REVISIONS.c.revision_no == document.latest_revision_no
            )
        ).first()
        latest = None if latest_row is None else _revision(latest_row, now)
    return DocumentDetailRecord(document=document, active_revision=active, latest_revision=latest)


def list_revisions(
    session: Session,
    actor: ActorContext,
    document_id: UUID,
    *,
    limit: int,
    offset: int,
    now: datetime,
) -> RevisionPageRecord | None:
    """Newest first: ``(revision_no DESC, id)``. ``None`` if the document is not in the tenant."""
    if session.execute(_document_statement(actor.tenant_id, document_id)).first() is None:
        return None
    total = session.execute(
        select(func.count())
        .select_from(REVISIONS)
        .where(REVISIONS.c.tenant_id == actor.tenant_id, REVISIONS.c.document_id == document_id)
    ).scalar_one()
    rows = session.execute(
        _revision_where(actor.tenant_id, document_id)
        .order_by(REVISIONS.c.revision_no.desc(), REVISIONS.c.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return RevisionPageRecord(items=tuple(_revision(row, now) for row in rows), total=total)


def get_revision_by_no(
    session: Session, actor: ActorContext, document_id: UUID, revision_no: int, *, now: datetime
) -> RevisionRecord | None:
    """One revision by its number, after the document is found in the tenant; ``None`` if the
    document is foreign or missing, or has no such number."""
    if session.execute(_document_statement(actor.tenant_id, document_id)).first() is None:
        return None
    row = session.execute(
        _revision_where(actor.tenant_id, document_id, REVISIONS.c.revision_no == revision_no)
    ).first()
    return None if row is None else _revision(row, now)


def list_chunks(
    session: Session,
    actor: ActorContext,
    document_id: UUID,
    revision_no: int,
    *,
    limit: int,
    offset: int,
) -> ChunkPageRecord | None:
    """A revision's chunks by ``ordinal``. ``None`` if the document is not in the tenant or has
    no such revision number. ``verified_complete`` comes only from the settled status (activation
    verified the exact set under its locks), never from a matching count."""
    if session.execute(_document_statement(actor.tenant_id, document_id)).first() is None:
        return None
    revision = session.execute(
        select(REVISIONS.c.id, REVISIONS.c.status).where(
            REVISIONS.c.tenant_id == actor.tenant_id,
            REVISIONS.c.document_id == document_id,
            REVISIONS.c.revision_no == revision_no,
        )
    ).first()
    if revision is None:
        return None
    chunk_set = session.execute(
        select(CHUNK_SETS.c.chunker_version, CHUNK_SETS.c.chunk_count).where(
            CHUNK_SETS.c.tenant_id == actor.tenant_id, CHUNK_SETS.c.revision_id == revision.id
        )
    ).first()
    if chunk_set is None:
        return ChunkPageRecord(chunk_set=None, items=(), total=0)
    scope = and_(
        CHUNKS.c.tenant_id == actor.tenant_id,
        CHUNKS.c.revision_id == revision.id,
        CHUNKS.c.chunker_version == chunk_set.chunker_version,
    )
    stored = session.execute(select(func.count()).select_from(CHUNKS).where(scope)).scalar_one()
    rows = session.execute(
        select(CHUNKS).where(scope).order_by(CHUNKS.c.ordinal).limit(limit).offset(offset)
    ).all()
    record = ChunkSetRecord(
        chunker_version=chunk_set.chunker_version,
        chunk_count=chunk_set.chunk_count,
        stored_count=stored,
        verified_complete=RevisionStatus(revision.status) in VERIFIED_SET_STATUSES,
    )
    items = tuple(
        ChunkRecord(
            id=row.id,
            ordinal=row.ordinal,
            text=row.text,
            content_sha256=row.content_sha256,
            section_path=tuple(row.section_path),
            is_table=row.is_table,
            line_start=row.line_start,
            line_end=row.line_end,
            char_start=row.char_start,
            char_end=row.char_end,
            header_line_start=row.header_line_start,
            header_line_end=row.header_line_end,
            header_char_start=row.header_char_start,
            header_char_end=row.header_char_end,
        )
        for row in rows
    )
    return ChunkPageRecord(chunk_set=record, items=items, total=stored)


def get_job_view(
    session: Session, actor: ActorContext, job_id: UUID, *, now: datetime
) -> JobViewRecord | None:
    """Reviewed fields of a job of a viewable kind in the tenant; ``None`` otherwise."""
    row = session.execute(
        select(
            JOBS.c.id,
            JOBS.c.kind,
            JOBS.c.status,
            JOBS.c.attempt,
            JOBS.c.max_attempts,
            JOBS.c.run_after,
            JOBS.c.last_error,
            JOBS.c.lease_expires_at,
            JOBS.c.created_at,
            JOBS.c.updated_at,
            JOBS.c.finished_at,
        ).where(
            JOBS.c.tenant_id == actor.tenant_id,
            JOBS.c.id == job_id,
            JOBS.c.kind.in_(sorted(VIEWABLE_JOB_KINDS)),
        )
    ).first()
    if row is None:
        return None
    status = JobStatus(row.status)
    return JobViewRecord(
        id=row.id,
        kind=row.kind,
        status=status,
        attempt=row.attempt,
        max_attempts=row.max_attempts,
        run_after=row.run_after,
        last_error=None if row.last_error is None else JobErrorCode(row.last_error),
        lease_expires_at=row.lease_expires_at if status is JobStatus.RUNNING else None,
        lease_expired=lease_expired(status, row.lease_expires_at, now=now),
        created_at=row.created_at,
        updated_at=row.updated_at,
        finished_at=row.finished_at,
    )


# --- upload creation (caller's write transaction) ----------------------------------------------


def upload_observation_statement(tenant_id: UUID, revision_id: UUID) -> Select[Any]:
    """The upload response state in **one** statement: the revision, its canonical job and the
    database time, all from one statement snapshot."""
    return (
        revisions_with_job_statement()
        .add_columns(func.clock_timestamp().label("db_now"))
        .where(REVISIONS.c.tenant_id == tenant_id, REVISIONS.c.id == revision_id)
    )


def create_upload(
    session: Session,
    actor: ActorContext,
    *,
    vendor_id: UUID,
    document_key: str,
    title: str,
    source_type: SourceType,
    content: RevisionContent,
    version_label: str | None = None,
    effective_date: date | None = None,
) -> UploadRecord:
    """Create (or find) the revision and its canonical ingestion job, then observe them.

    Runs in the caller's transaction and never commits. A new revision always gets its job in
    the same transaction. An identical duplicate that is still unsettled calls ``enqueue``
    idempotently: that creates a missing canonical job and never alters an existing one, even a
    terminal one. A settled duplicate is never re-enqueued. The returned observation is read in
    one statement after these writes; the caller returns it only after committing.
    """
    created = create_revision(
        session,
        actor,
        vendor_id=vendor_id,
        document_key=document_key,
        title=title,
        source_type=source_type,
        content=content,
        version_label=version_label,
        effective_date=effective_date,
    )
    revision = created.revision
    if created.created or revision.status in UNSETTLED_STATUSES:
        enqueue(
            session,
            actor,
            kind=INGEST_REVISION_KIND,
            idempotency_key=str(revision.id),
            payload=JobPayload.from_mapping({REVISION_ID_PAYLOAD_KEY: str(revision.id)}),
        )
    row = session.execute(upload_observation_statement(actor.tenant_id, revision.id)).one()
    status = RevisionStatus(row.status)
    job = _job_summary(row, row.db_now)
    return UploadRecord(
        created=created.created,
        document_id=created.document.id,
        revision_id=row.id,
        revision_no=row.revision_no,
        revision_status=status,
        ingestion_state=derive_ingestion_state(status, None if job is None else job.status),
        job=job,
    )
