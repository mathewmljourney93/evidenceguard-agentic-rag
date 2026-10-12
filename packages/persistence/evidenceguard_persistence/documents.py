"""Tenant-scoped documents and revisions, and fenced revision transitions (M3c, ADR-0009).

Lifecycle rules live in ``evidenceguard_domain.revisions``; this module applies them to locked
rows.

**Creation** (``create_revision``) runs in the **caller's** transaction and never commits, like
``enqueue``, so a revision and its ingestion job (M3e) commit together. The tenant comes only
from the actor. The document row is created if needed (``INSERT … ON CONFLICT DO NOTHING``) and
then locked, which serialises every creation for that document; revision numbers are allocated
from ``latest_revision_no`` under that lock. Identical bytes return the existing revision,
whatever its status; a metadata difference raises a fixed conflict error and changes nothing.

**Fenced transitions** (``start_processing``, ``fail_revision``, ``activate_revision``) run
inside an open M3a fence: they take the fence's ``FencedSession`` and its ``JobSnapshot``, never
open, commit or roll back a transaction, and issue no transaction-control SQL. The revision is
named only by the locked job's ``revision_id`` payload, and every lookup uses the job's tenant.
Each one, in order:

1. reads the revision's (immutable) ``document_id`` without a lock;
2. locks the document row, then the revision rows in ascending ID order (job → document →
   revisions; the job row is already locked by the fence);
3. re-reads all mutable data in those locking statements;
4. re-checks ownership with ``recheck_ownership`` (the locked job row and a fresh
   ``clock_timestamp()``) and requires the job's tenant to match, raising ``LeaseLostError``
   before any write;
5. applies the pure rule with that fresh time and writes the result.

Activation writes the old active revision's demotion first, then the target's promotion, then
the document pointer: the one-active partial unique index is checked statement by statement,
and the intermediate state is never committed. A late older revision writes only its own row; a
duplicate activation writes nothing. A lock wait beyond the fence's ``lock_timeout`` raises the
existing ``JobLockTimeoutError``.

These checks happen at explicit points; they are not atomic with every statement. A transaction
that passes the re-check just before expiry may commit shortly after it (the M3a limit).
"""

from collections.abc import Collection
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import Select, Table, Update, func, insert, select, update
from sqlalchemy.dialects.postgresql import Insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Result
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.sql import Executable

from evidenceguard_domain import revisions as rules
from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_domain.errors import PermissionDeniedError
from evidenceguard_domain.evidence import SourceType
from evidenceguard_domain.jobs import JobSnapshot, LeaseLostError
from evidenceguard_domain.revisions import (
    DocumentSnapshot,
    InconsistentDocumentStateError,
    RevisionContent,
    RevisionFailureCode,
    RevisionSnapshot,
    RevisionStatus,
)
from evidenceguard_persistence.jobs import FencedSession, JobLockTimeoutError, recheck_ownership
from evidenceguard_persistence.models import Document, DocumentRevision, Vendor

DOCUMENTS = cast(Table, Document.__table__)
REVISIONS = cast(Table, DocumentRevision.__table__)
# Revision snapshots never carry content, so ordinary reads never load it.
REVISION_COLUMNS = tuple(column for column in REVISIONS.c if column.name != "content_text")

REVISION_ID_PAYLOAD_KEY = "revision_id"
EDITOR_ROLES = frozenset({Role.REVIEWER, Role.APPROVER})
DOCUMENT_IDENTITY_CONSTRAINT = "uq_documents_tenant_id_vendor_id_document_key"
REVISION_NUMBER_CONSTRAINT = "uq_document_revisions_tenant_id_document_id_revision_no"
REVISION_CONTENT_CONSTRAINT = "uq_document_revisions_tenant_id_document_id_sha256"
LOCK_NOT_AVAILABLE = "55P03"  # PostgreSQL SQLSTATE for lock_timeout


# --- errors (fixed messages; never values or content) --------------------------------------


class VendorNotFoundError(Exception):
    def __init__(self) -> None:
        super().__init__("the vendor was not found in the tenant")


class DocumentConflictError(Exception):
    """The document exists with a different title or source type. Nothing was changed."""

    def __init__(self) -> None:
        super().__init__("the document exists with different metadata")


class RevisionConflictError(Exception):
    """The same content exists for this document with different metadata. Nothing changed."""

    def __init__(self) -> None:
        super().__init__("this content exists for the document with different metadata")


class RevisionCreateRaceError(Exception):
    """The document or revision row is not visible to this transaction (for example under
    REPEATABLE READ), or a concurrent writer won a unique constraint. The caller may retry in a
    new transaction."""

    def __init__(self) -> None:
        super().__init__("the revision could not be created consistently; retry")


class RevisionNotFoundError(Exception):
    """No revision of the job's tenant matches the job's ``revision_id`` payload."""

    def __init__(self) -> None:
        super().__init__("the job's revision was not found in its tenant")


# --- results -------------------------------------------------------------------------------


@dataclass(frozen=True)
class RevisionCreation:
    document: DocumentSnapshot
    revision: RevisionSnapshot
    created: bool


@dataclass(frozen=True)
class ActivationResult:
    """``revision`` is the target after settling; ``superseded`` is the previously active
    revision this activation demoted, if any."""

    revision: RevisionSnapshot
    superseded: RevisionSnapshot | None


# --- statements (built here so tests can inspect their SQL) --------------------------------


def vendor_statement(tenant_id: UUID, vendor_id: UUID) -> Select[Any]:
    return select(Vendor.id).where(Vendor.tenant_id == tenant_id, Vendor.id == vendor_id)


def insert_document_statement(
    tenant_id: UUID, vendor_id: UUID, document_key: str, title: str, source_type: SourceType
) -> Insert:
    return (
        pg_insert(DOCUMENTS)
        .values(
            id=uuid4(),
            tenant_id=tenant_id,
            vendor_id=vendor_id,
            document_key=document_key,
            title=title,
            source_type=source_type.value,
        )
        .on_conflict_do_nothing(constraint=DOCUMENT_IDENTITY_CONSTRAINT)
    )


def lock_document_by_key_statement(
    tenant_id: UUID, vendor_id: UUID, document_key: str
) -> Select[Any]:
    return (
        select(DOCUMENTS)
        .where(
            DOCUMENTS.c.tenant_id == tenant_id,
            DOCUMENTS.c.vendor_id == vendor_id,
            DOCUMENTS.c.document_key == document_key,
        )
        .with_for_update()
    )


def revision_by_content_statement(tenant_id: UUID, document_id: UUID, sha256: str) -> Select[Any]:
    return select(*REVISION_COLUMNS).where(
        REVISIONS.c.tenant_id == tenant_id,
        REVISIONS.c.document_id == document_id,
        REVISIONS.c.sha256 == sha256,
    )


def allocate_statement(tenant_id: UUID, document_id: UUID, revision_no: int) -> Update:
    return (
        update(DOCUMENTS)
        .where(DOCUMENTS.c.tenant_id == tenant_id, DOCUMENTS.c.id == document_id)
        .values(latest_revision_no=revision_no, updated_at=_now())
        .returning(*DOCUMENTS.c)
    )


def insert_revision_statement(
    tenant_id: UUID,
    document_id: UUID,
    revision_no: int,
    content: RevisionContent,
    version_label: str | None,
    effective_date: date | None,
) -> Any:
    return (
        insert(REVISIONS)
        .values(
            id=uuid4(),
            tenant_id=tenant_id,
            document_id=document_id,
            revision_no=revision_no,
            version_label=version_label,
            effective_date=effective_date,
            status=RevisionStatus.PENDING.value,
            sha256=content.sha256,
            media_type=content.media_type.value,
            byte_size=content.byte_size,
            content_text=content.text,
        )
        .returning(*REVISION_COLUMNS)
    )


def revision_document_statement(tenant_id: UUID, revision_id: UUID) -> Select[Any]:
    """Step 1: the revision's immutable ``document_id``, read without a lock."""
    return select(REVISIONS.c.document_id).where(
        REVISIONS.c.tenant_id == tenant_id, REVISIONS.c.id == revision_id
    )


def lock_document_statement(tenant_id: UUID, document_id: UUID) -> Select[Any]:
    """Step 2: lock the document row (after the job row, before any revision row)."""
    return (
        select(DOCUMENTS)
        .where(DOCUMENTS.c.tenant_id == tenant_id, DOCUMENTS.c.id == document_id)
        .with_for_update()
    )


def lock_revisions_statement(
    tenant_id: UUID, document_id: UUID, revision_ids: Collection[UUID]
) -> Select[Any]:
    """Step 3: lock the revision rows in ascending ID order and re-read them."""
    return (
        select(*REVISION_COLUMNS)
        .where(
            REVISIONS.c.tenant_id == tenant_id,
            REVISIONS.c.document_id == document_id,
            REVISIONS.c.id.in_(sorted(revision_ids)),
        )
        .order_by(REVISIONS.c.id)
        .with_for_update()
    )


def update_revision_statement(revision: RevisionSnapshot) -> Update:
    """Write only the mutable lifecycle fields; content and metadata never change."""
    return (
        update(REVISIONS)
        .where(REVISIONS.c.tenant_id == revision.tenant_id, REVISIONS.c.id == revision.id)
        .values(
            status=revision.status.value,
            failure_reason=None
            if revision.failure_reason is None
            else revision.failure_reason.value,
            activated_at=revision.activated_at,
            failed_at=revision.failed_at,
            superseded_at=revision.superseded_at,
            superseded_by_revision_id=revision.superseded_by_revision_id,
            updated_at=revision.updated_at,
        )
    )


def update_pointer_statement(document: DocumentSnapshot) -> Update:
    return (
        update(DOCUMENTS)
        .where(DOCUMENTS.c.tenant_id == document.tenant_id, DOCUMENTS.c.id == document.id)
        .values(active_revision_id=document.active_revision_id, updated_at=document.updated_at)
    )


def _now() -> Any:
    """Audit timestamps use ordinary transaction time (ADR-0007)."""
    return func.now()


# --- creation (caller-owned transaction) ---------------------------------------------------


def create_revision(
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
) -> RevisionCreation:
    """Create a ``pending`` revision of the actor's document, or return the identical one.

    Runs in the caller's transaction and never commits. Raises ``PermissionDeniedError`` for
    roles other than reviewer and approver, and validation errors, before any SQL;
    ``VendorNotFoundError`` for a vendor outside the actor's tenant; ``DocumentConflictError`` or
    ``RevisionConflictError`` for metadata differences (nothing is changed by this call).
    """
    if actor.role not in EDITOR_ROLES:
        raise PermissionDeniedError()
    key = rules.validate_document_key(document_key)
    title = rules.validate_title(title)
    label = rules.validate_version_label(version_label)
    source = SourceType(source_type)
    if not isinstance(content, RevisionContent):
        raise TypeError("content must be a RevisionContent")
    if effective_date is not None and (
        not isinstance(effective_date, date) or isinstance(effective_date, datetime)
    ):
        raise ValueError("effective_date must be a date")
    tenant_id = actor.tenant_id

    if session.execute(vendor_statement(tenant_id, vendor_id)).first() is None:
        raise VendorNotFoundError()
    session.execute(insert_document_statement(tenant_id, vendor_id, key, title, source))
    locked = session.execute(lock_document_by_key_statement(tenant_id, vendor_id, key)).first()
    if locked is None:
        raise RevisionCreateRaceError()
    document = _document(locked)
    if document.title != title or document.source_type is not source:
        raise DocumentConflictError()

    existing = session.execute(
        revision_by_content_statement(tenant_id, document.id, content.sha256)
    ).first()
    if existing is not None:
        revision = _revision(existing)
        same = (revision.media_type, revision.byte_size, revision.version_label) == (
            content.media_type,
            content.byte_size,
            label,
        ) and revision.effective_date == effective_date
        if not same:
            raise RevisionConflictError()
        return RevisionCreation(document=document, revision=revision, created=False)

    number = rules.next_revision_no(document)
    allocated = session.execute(allocate_statement(tenant_id, document.id, number)).one()
    try:
        inserted = session.execute(
            insert_revision_statement(
                tenant_id, document.id, number, content, label, effective_date
            )
        ).one()
    except IntegrityError as error:
        if _constraint(error) in {REVISION_NUMBER_CONSTRAINT, REVISION_CONTENT_CONSTRAINT}:
            raise RevisionCreateRaceError() from None
        raise
    return RevisionCreation(
        document=_document(allocated), revision=_revision(inserted), created=True
    )


# --- fenced transitions ---------------------------------------------------------------------


@dataclass(frozen=True)
class _Locked:
    document: DocumentSnapshot
    target: RevisionSnapshot
    active: RevisionSnapshot | None
    now: datetime


def start_processing(session: FencedSession, job: JobSnapshot) -> RevisionSnapshot:
    """``pending`` → ``processing``; a no-op while already ``processing``."""
    locked = _lock(session, job, include_active=False)
    updated = rules.start_processing(locked.target, now=locked.now)
    if updated != locked.target:
        session.execute(update_revision_statement(updated))
    return updated


def fail_revision(
    session: FencedSession, job: JobSnapshot, code: RevisionFailureCode
) -> RevisionSnapshot:
    """Record a permanent ingestion failure. The previously active revision is untouched.

    With the existing worker interface the job fails in a **separate** transaction: commit this
    one in a fenced block that does not raise, then raise
    ``PermanentJobError(JobErrorCode.PERMANENT_FAILURE)`` outside it (ADR-0009).
    """
    if not isinstance(code, RevisionFailureCode):
        raise TypeError("code must be a RevisionFailureCode")
    locked = _lock(session, job, include_active=False)
    updated = rules.fail(locked.target, code, now=locked.now)
    if updated != locked.target:
        session.execute(update_revision_statement(updated))
    return updated


def activate_revision(session: FencedSession, job: JobSnapshot) -> ActivationResult:
    """Settle the job's ``processing`` revision against the document's active revision.

    Writes, in order: demote the old active revision, promote the target, update the pointer.
    """
    locked = _lock(session, job, include_active=True)
    settlement = rules.settle(locked.document, locked.target, locked.active, now=locked.now)
    if settlement.changed:
        if settlement.demoted is not None:
            session.execute(update_revision_statement(settlement.demoted))
        session.execute(update_revision_statement(settlement.target))
        if settlement.document is not None:
            session.execute(update_pointer_statement(settlement.document))
    return ActivationResult(revision=settlement.target, superseded=settlement.demoted)


def _lock(session: FencedSession, job: JobSnapshot, *, include_active: bool) -> _Locked:
    tenant_id = job.tenant_id
    revision_id = _payload_revision_id(job)

    document_id = session.scalar(revision_document_statement(tenant_id, revision_id))
    if document_id is None:
        raise RevisionNotFoundError()
    document_row = _locking(session, lock_document_statement(tenant_id, document_id)).first()
    if document_row is None:
        raise RevisionNotFoundError()
    document = _document(document_row)

    wanted = {revision_id}
    if include_active and document.active_revision_id is not None:
        wanted.add(document.active_revision_id)
    rows = _locking(session, lock_revisions_statement(tenant_id, document_id, wanted))
    locked = {revision.id: revision for revision in (_revision(row) for row in rows)}
    target = locked.get(revision_id)
    if target is None:
        raise RevisionNotFoundError()
    active = None
    if include_active and document.active_revision_id is not None:
        active = locked.get(document.active_revision_id)
        if active is None:
            raise InconsistentDocumentStateError()

    fresh_job, now = recheck_ownership(session, job.lease_token())
    if fresh_job.tenant_id != tenant_id or document.tenant_id != tenant_id:
        raise LeaseLostError()
    return _Locked(document=document, target=target, active=active, now=now)


def _payload_revision_id(job: JobSnapshot) -> UUID:
    value = job.payload.as_dict().get(REVISION_ID_PAYLOAD_KEY)
    if value is None:
        raise RevisionNotFoundError()
    return UUID(value)


def _locking(session: FencedSession, statement: Executable) -> Result[Any]:
    try:
        return session.execute(statement)
    except OperationalError as error:
        if getattr(error.orig, "sqlstate", None) == LOCK_NOT_AVAILABLE:
            raise JobLockTimeoutError() from None
        raise


# --- row conversion ---------------------------------------------------------------------------


def _document(row: Any) -> DocumentSnapshot:
    return DocumentSnapshot.model_validate(dict(row._mapping))


def _revision(row: Any) -> RevisionSnapshot:
    data = {str(key): value for key, value in row._mapping.items() if key != "content_text"}
    return RevisionSnapshot.model_validate(data)


def _constraint(error: IntegrityError) -> str | None:
    diag = getattr(error.orig, "diag", None)
    name = getattr(diag, "constraint_name", None)
    return name if isinstance(name, str) else None
