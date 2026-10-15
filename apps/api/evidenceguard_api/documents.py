"""Document upload and read endpoints (M3e, ADR-0011).

- ``POST /v1/vendors/{vendor_id}/documents`` uploads one revision as bounded multipart
  (``uploads.py``): 202 with a new revision and its ingestion job, 200 for identical bytes and
  metadata (the existing revision, as observed).
- ``GET /v1/vendors/{vendor_id}/documents`` lists the vendor's documents.
- ``GET /v1/documents/{document_id}`` returns one document with its active and latest revisions.
- ``GET /v1/documents/{document_id}/revisions`` lists its revisions, newest first.
- ``GET /v1/documents/{document_id}/revisions/{revision_no}/chunks`` lists a revision's chunks.
- ``GET /v1/jobs/{job_id}`` returns an ingestion job's reviewed fields.

The tenant always comes from the API key; reviewers and approvers may use these routes and
administrators get a generic 403. Objects of another tenant are not found (404).

**Upload.** The route declares no body parameters, so FastAPI never reads the body: the
authentication and role dependencies, then the tenant-scoped vendor lookup and the request
header checks, all finish before ``read_upload`` reads the first byte. Creation is one write
transaction (``create_upload``) that commits before its observation is returned. Both database
steps run in the threadpool; the route itself is ``async`` only to stream the body.

**Reads** are synchronous routes (run in a worker thread). Each is one REPEATABLE READ, READ
ONLY transaction (``read_snapshot``) whose result is converted to immutable records before the
transaction ends, which is before the response is serialized.

Database or configuration failures are a generic 503. Responses never contain revision content
(``content_text``), job payloads, idempotency keys, worker identifiers or tenant IDs; chunk views
intentionally contain chunk text.
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from typing import Annotated, Any, Protocol
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError
from starlette.requests import ClientDisconnect

from evidenceguard_api.auth import authenticated_actor
from evidenceguard_api.database import AppDatabase
from evidenceguard_api.uploads import (
    FILE_FIELD,
    MAX_TEXT_FIELD_BYTES,
    MAX_UPLOAD_BYTES,
    ParsedUpload,
    UploadRejected,
    check_request_headers,
    read_upload,
)
from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_domain.errors import PermissionDeniedError
from evidenceguard_domain.evidence import SourceType
from evidenceguard_domain.ingestion import IngestionState
from evidenceguard_domain.jobs import JobErrorCode, JobIdempotencyConflictError, JobStatus
from evidenceguard_domain.revisions import MediaType, RevisionFailureCode, RevisionStatus
from evidenceguard_observability.jsonlog import DOCUMENT_UPLOAD_INCONSISTENT, log_event
from evidenceguard_persistence import document_views
from evidenceguard_persistence.db import transaction
from evidenceguard_persistence.document_views import (
    ChunkPageRecord,
    ChunkRecord,
    DocumentDetailRecord,
    DocumentPageRecord,
    DocumentRecord,
    JobSummaryRecord,
    JobViewRecord,
    RevisionPageRecord,
    RevisionRecord,
    UploadRecord,
    read_snapshot,
)
from evidenceguard_persistence.documents import (
    DocumentConflictError,
    RevisionConflictError,
    RevisionCreateRaceError,
    VendorNotFoundError,
)
from evidenceguard_persistence.jobs import JobEnqueueRaceError
from evidenceguard_persistence.settings import DatabaseConfigurationError

DEFAULT_LIMIT = 20
MAX_LIMIT = 100
MAX_OFFSET = 10_000
DEFAULT_CHUNK_LIMIT = 50
MAX_CHUNK_LIMIT = 200
MAX_CHUNK_OFFSET = 4_095
MAX_REVISION_NO = 2_147_483_647
DOCUMENT_ROLES = frozenset({Role.REVIEWER, Role.APPROVER})

LOGGER = logging.getLogger("evidenceguard.documents")
_PROBLEM: dict[str, Any] = {"application/problem+json": {}}


# --- response models (extra fields forbidden; never content_text, payloads or tenant IDs) ----


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class JobSummaryOut(_Out):
    id: UUID
    status: JobStatus
    attempt: int
    max_attempts: int
    lease_expires_at: datetime | None = Field(description="Set only while the job is running.")
    lease_expired: bool | None = Field(
        description=(
            "While running: whether the lease had expired at the response's database time. "
            "Otherwise null."
        )
    )


class RevisionOut(_Out):
    id: UUID
    revision_no: int
    version_label: str | None
    effective_date: date | None
    media_type: MediaType
    byte_size: int
    sha256: str
    status: RevisionStatus = Field(description="The stored, authoritative revision status.")
    failure_reason: RevisionFailureCode | None
    activated_at: datetime | None
    failed_at: datetime | None
    superseded_at: datetime | None
    superseded_by_revision_id: UUID | None
    created_at: datetime
    updated_at: datetime
    ingestion_state: IngestionState = Field(
        description="Derived at read time from the status and the canonical ingestion job."
    )
    ingestion_job: JobSummaryOut | None


class DocumentSummaryOut(_Out):
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


class DocumentDetailOut(DocumentSummaryOut):
    active_revision: RevisionOut | None
    latest_revision: RevisionOut | None


class DocumentPageOut(_Out):
    """One page, ordered by ``document_key`` then ``id``. Not a snapshot across requests."""

    items: list[DocumentSummaryOut]
    total: int
    limit: int
    offset: int


class RevisionPageOut(_Out):
    """One page, newest first (``revision_no`` descending, then ``id``). Not a snapshot across
    requests."""

    items: list[RevisionOut]
    total: int
    limit: int
    offset: int


class SpanOut(_Out):
    line_start: int
    line_end: int
    char_start: int
    char_end: int


class ChunkOut(_Out):
    id: UUID
    ordinal: int
    text: str = Field(
        description=(
            "With a repeated header, the header slice followed by the body slice: not one "
            "contiguous source passage. Only `source` identifies the cited passage."
        )
    )
    content_sha256: str
    section_path: list[str]
    is_table: bool
    source: SpanOut
    repeated_header: SpanOut | None
    contiguous: bool


class ChunkSetOut(_Out):
    chunker_version: str
    chunk_count: int = Field(description="The count recorded by the writing attempt.")
    stored_count: int
    verified_complete: bool = Field(
        description="True only for an active or superseded revision (verified at activation)."
    )


class ChunkPageOut(_Out):
    """Ordered by ``ordinal``. Stable for a settled revision; may change between requests while
    an unsettled revision is still being written."""

    chunk_set: ChunkSetOut | None
    items: list[ChunkOut]
    total: int
    limit: int
    offset: int


class JobViewOut(_Out):
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


class UploadResultOut(_Out):
    """The state observed inside the creation transaction, sent after its commit. A worker can
    change it immediately afterwards."""

    created: bool
    document_id: UUID
    revision_id: UUID
    revision_no: int
    revision_status: RevisionStatus
    ingestion_state: IngestionState
    job: JobSummaryOut | None


# --- the store -----------------------------------------------------------------------------------


class DocumentStore(Protocol):
    def vendor_exists(self, actor: ActorContext, vendor_id: UUID) -> bool: ...

    def create_upload(
        self, actor: ActorContext, vendor_id: UUID, upload: ParsedUpload
    ) -> UploadRecord: ...

    def list_documents(
        self, actor: ActorContext, vendor_id: UUID, *, limit: int, offset: int
    ) -> DocumentPageRecord | None: ...

    def get_document(
        self, actor: ActorContext, document_id: UUID
    ) -> DocumentDetailRecord | None: ...

    def list_revisions(
        self, actor: ActorContext, document_id: UUID, *, limit: int, offset: int
    ) -> RevisionPageRecord | None: ...

    def list_chunks(
        self, actor: ActorContext, document_id: UUID, revision_no: int, *, limit: int, offset: int
    ) -> ChunkPageRecord | None: ...

    def get_job(self, actor: ActorContext, job_id: UUID) -> JobViewRecord | None: ...


class DatabaseDocumentStore:
    """Document operations on the app's shared database: one read snapshot per read, one write
    transaction per upload."""

    def __init__(self, database: AppDatabase) -> None:
        self._database = database

    def vendor_exists(self, actor: ActorContext, vendor_id: UUID) -> bool:
        with read_snapshot(self._database.session_factory()) as (session, _now):
            return document_views.vendor_exists(session, actor, vendor_id)

    def create_upload(
        self, actor: ActorContext, vendor_id: UUID, upload: ParsedUpload
    ) -> UploadRecord:
        with transaction(self._database.session_factory()) as session:
            record = document_views.create_upload(
                session,
                actor,
                vendor_id=vendor_id,
                document_key=upload.document_key,
                title=upload.title,
                source_type=upload.source_type,
                content=upload.content,
                version_label=upload.version_label,
                effective_date=upload.effective_date,
            )
        return record  # only after a successful commit

    def list_documents(
        self, actor: ActorContext, vendor_id: UUID, *, limit: int, offset: int
    ) -> DocumentPageRecord | None:
        with read_snapshot(self._database.session_factory()) as (session, _now):
            return document_views.list_documents(
                session, actor, vendor_id, limit=limit, offset=offset
            )

    def get_document(self, actor: ActorContext, document_id: UUID) -> DocumentDetailRecord | None:
        with read_snapshot(self._database.session_factory()) as (session, now):
            return document_views.get_document(session, actor, document_id, now=now)

    def list_revisions(
        self, actor: ActorContext, document_id: UUID, *, limit: int, offset: int
    ) -> RevisionPageRecord | None:
        with read_snapshot(self._database.session_factory()) as (session, now):
            return document_views.list_revisions(
                session, actor, document_id, limit=limit, offset=offset, now=now
            )

    def list_chunks(
        self, actor: ActorContext, document_id: UUID, revision_no: int, *, limit: int, offset: int
    ) -> ChunkPageRecord | None:
        with read_snapshot(self._database.session_factory()) as (session, _now):
            return document_views.list_chunks(
                session, actor, document_id, revision_no, limit=limit, offset=offset
            )

    def get_job(self, actor: ActorContext, job_id: UUID) -> JobViewRecord | None:
        with read_snapshot(self._database.session_factory()) as (session, now):
            return document_views.get_job_view(session, actor, job_id, now=now)


# --- helpers -------------------------------------------------------------------------------------


def document_actor(
    actor: Annotated[ActorContext, Depends(authenticated_actor)],
) -> ActorContext:
    """Authenticated (401 otherwise) and allowed to use documents (generic 403 otherwise)."""
    if actor.role not in DOCUMENT_ROLES:
        raise HTTPException(status_code=403)
    return actor


def _store(request: Request) -> DocumentStore:
    store: DocumentStore = request.app.state.document_store
    return store


@contextmanager
def _database_errors_as_503() -> Iterator[None]:
    try:
        yield
    except (DatabaseConfigurationError, SQLAlchemyError):
        raise HTTPException(status_code=503) from None


def _not_found() -> HTTPException:
    return HTTPException(status_code=404)


def _rejected(error: UploadRejected) -> Exception:
    if error.status == 422:
        return RequestValidationError([{"loc": loc, "type": kind} for loc, kind in error.errors])
    return HTTPException(status_code=error.status)


def _job_summary(record: JobSummaryRecord | None) -> JobSummaryOut | None:
    if record is None:
        return None
    return JobSummaryOut(
        id=record.id,
        status=record.status,
        attempt=record.attempt,
        max_attempts=record.max_attempts,
        lease_expires_at=record.lease_expires_at,
        lease_expired=record.lease_expired,
    )


def _revision(record: RevisionRecord) -> RevisionOut:
    return RevisionOut(
        id=record.id,
        revision_no=record.revision_no,
        version_label=record.version_label,
        effective_date=record.effective_date,
        media_type=record.media_type,
        byte_size=record.byte_size,
        sha256=record.sha256,
        status=record.status,
        failure_reason=record.failure_reason,
        activated_at=record.activated_at,
        failed_at=record.failed_at,
        superseded_at=record.superseded_at,
        superseded_by_revision_id=record.superseded_by_revision_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
        ingestion_state=record.ingestion_state,
        ingestion_job=_job_summary(record.ingestion_job),
    )


def _document_fields(record: DocumentRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "vendor_id": record.vendor_id,
        "document_key": record.document_key,
        "title": record.title,
        "source_type": record.source_type,
        "authenticity": record.authenticity,
        "latest_revision_no": record.latest_revision_no,
        "active_revision_id": record.active_revision_id,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def _chunk(record: ChunkRecord) -> ChunkOut:
    header = None
    if record.header_line_start is not None:
        assert record.header_line_end is not None
        assert record.header_char_start is not None and record.header_char_end is not None
        header = SpanOut(
            line_start=record.header_line_start,
            line_end=record.header_line_end,
            char_start=record.header_char_start,
            char_end=record.header_char_end,
        )
    return ChunkOut(
        id=record.id,
        ordinal=record.ordinal,
        text=record.text,
        content_sha256=record.content_sha256,
        section_path=list(record.section_path),
        is_table=record.is_table,
        source=SpanOut(
            line_start=record.line_start,
            line_end=record.line_end,
            char_start=record.char_start,
            char_end=record.char_end,
        ),
        repeated_header=header,
        contiguous=header is None,
    )


# --- routes --------------------------------------------------------------------------------------

_UPLOAD_BODY: dict[str, Any] = {
    "required": True,
    "content": {
        "multipart/form-data": {
            "schema": {
                "type": "object",
                "required": [FILE_FIELD, "document_key", "title", "source_type"],
                "additionalProperties": False,
                "properties": {
                    FILE_FIELD: {
                        "type": "string",
                        "format": "binary",
                        "description": (
                            f"Strict UTF-8 text without NUL, 1 to {MAX_UPLOAD_BYTES} bytes. The "
                            "part's Content-Type (text/plain or text/markdown, optionally "
                            "charset=utf-8) decides the media type; any filename is ignored."
                        ),
                    },
                    "document_key": {"type": "string", "minLength": 1, "maxLength": 64},
                    "title": {"type": "string", "minLength": 1, "maxLength": 200},
                    "source_type": {"type": "string", "enum": [item.value for item in SourceType]},
                    "version_label": {"type": "string", "minLength": 1, "maxLength": 64},
                    "effective_date": {"type": "string", "format": "date"},
                },
                "description": (
                    f"Each field is one part; text fields are at most {MAX_TEXT_FIELD_BYTES} "
                    "bytes. Repeated or unknown parts are rejected."
                ),
            },
            "encoding": {FILE_FIELD: {"contentType": "text/plain, text/markdown"}},
        }
    },
}

router = APIRouter(
    responses={
        401: {
            "description": "Missing, malformed, unknown or revoked credentials.",
            "content": _PROBLEM,
        },
        403: {"description": "The caller's role may not use documents.", "content": _PROBLEM},
        404: {"description": "No such object in the caller's tenant.", "content": _PROBLEM},
        422: {"description": "Invalid parameters or fields.", "content": _PROBLEM},
        503: {"description": "The database is unavailable.", "content": _PROBLEM},
    },
)


@router.post(
    "/v1/vendors/{vendor_id}/documents",
    tags=["documents"],
    status_code=202,
    response_model=UploadResultOut,
    summary="Upload a document revision",
    description=(
        "Uploads one text/plain or text/markdown revision as multipart/form-data and queues its "
        "ingestion. 202 for a new revision; 200 with the existing revision for identical bytes "
        "and metadata. The response is the state observed when the upload committed."
    ),
    openapi_extra={"requestBody": _UPLOAD_BODY},
    responses={
        200: {"description": "Identical existing revision.", "model": UploadResultOut},
        400: {"description": "Invalid or mismatched Content-Length.", "content": _PROBLEM},
        409: {"description": "Conflicting document or revision metadata.", "content": _PROBLEM},
        413: {"description": "A size or part-count cap was exceeded.", "content": _PROBLEM},
        415: {"description": "Unsupported request or file media type.", "content": _PROBLEM},
    },
)
async def upload(
    vendor_id: UUID,
    request: Request,
    response: Response,
    actor: Annotated[ActorContext, Depends(document_actor)],
) -> UploadResultOut:
    store = _store(request)
    with _database_errors_as_503():
        found = await run_in_threadpool(store.vendor_exists, actor, vendor_id)
    if not found:
        raise _not_found()
    try:
        boundary, declared = check_request_headers(request.headers.raw)
        parsed = await read_upload(request.stream(), boundary=boundary, declared_length=declared)
    except UploadRejected as error:
        raise _rejected(error) from None
    except ClientDisconnect:
        # Nothing was written; the client may not receive this response.
        raise HTTPException(status_code=400) from None
    try:
        with _database_errors_as_503():
            record = await run_in_threadpool(store.create_upload, actor, vendor_id, parsed)
    except VendorNotFoundError:
        raise _not_found() from None
    except PermissionDeniedError:
        raise HTTPException(status_code=403) from None
    except (DocumentConflictError, RevisionConflictError):
        raise HTTPException(status_code=409) from None
    except (RevisionCreateRaceError, JobEnqueueRaceError):
        raise HTTPException(status_code=503) from None
    except JobIdempotencyConflictError:
        log_event(LOGGER, DOCUMENT_UPLOAD_INCONSISTENT, logging.ERROR)
        raise HTTPException(status_code=500) from None
    response.status_code = 202 if record.created else 200
    return UploadResultOut(
        created=record.created,
        document_id=record.document_id,
        revision_id=record.revision_id,
        revision_no=record.revision_no,
        revision_status=record.revision_status,
        ingestion_state=record.ingestion_state,
        job=_job_summary(record.job),
    )


@router.get(
    "/v1/vendors/{vendor_id}/documents",
    tags=["documents"],
    response_model=DocumentPageOut,
    summary="List a vendor's documents",
    description=(
        "Lists the vendor's documents ordered by document key, then ID. Offset pagination is "
        "not a snapshot: concurrent changes can shift later pages."
    ),
)
def list_documents(
    vendor_id: UUID,
    request: Request,
    actor: Annotated[ActorContext, Depends(document_actor)],
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0, le=MAX_OFFSET)] = 0,
) -> DocumentPageOut:
    with _database_errors_as_503():
        page = _store(request).list_documents(actor, vendor_id, limit=limit, offset=offset)
    if page is None:
        raise _not_found()
    return DocumentPageOut(
        items=[DocumentSummaryOut(**_document_fields(item)) for item in page.items],
        total=page.total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/v1/documents/{document_id}",
    tags=["documents"],
    response_model=DocumentDetailOut,
    summary="Get a document",
    description="One document with its active and latest revisions, from one read snapshot.",
)
def get_document(
    document_id: UUID,
    request: Request,
    actor: Annotated[ActorContext, Depends(document_actor)],
) -> DocumentDetailOut:
    with _database_errors_as_503():
        detail = _store(request).get_document(actor, document_id)
    if detail is None:
        raise _not_found()
    return DocumentDetailOut(
        **_document_fields(detail.document),
        active_revision=None
        if detail.active_revision is None
        else _revision(detail.active_revision),
        latest_revision=None
        if detail.latest_revision is None
        else _revision(detail.latest_revision),
    )


@router.get(
    "/v1/documents/{document_id}/revisions",
    tags=["documents"],
    response_model=RevisionPageOut,
    summary="List a document's revisions",
    description=(
        "Lists the document's revisions, newest first. Offset pagination is not a snapshot "
        "across requests."
    ),
)
def list_revisions(
    document_id: UUID,
    request: Request,
    actor: Annotated[ActorContext, Depends(document_actor)],
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0, le=MAX_OFFSET)] = 0,
) -> RevisionPageOut:
    with _database_errors_as_503():
        page = _store(request).list_revisions(actor, document_id, limit=limit, offset=offset)
    if page is None:
        raise _not_found()
    return RevisionPageOut(
        items=[_revision(item) for item in page.items],
        total=page.total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/v1/documents/{document_id}/revisions/{revision_no}/chunks",
    tags=["documents"],
    response_model=ChunkPageOut,
    summary="List a revision's chunks",
    description=(
        "Lists the chunks stored for one revision, by ordinal. `verified_complete` is true only "
        "for an active or superseded revision; other revisions' chunks may be partial."
    ),
)
def list_chunks(
    document_id: UUID,
    revision_no: Annotated[int, Path(ge=1, le=MAX_REVISION_NO)],
    request: Request,
    actor: Annotated[ActorContext, Depends(document_actor)],
    limit: Annotated[int, Query(ge=1, le=MAX_CHUNK_LIMIT)] = DEFAULT_CHUNK_LIMIT,
    offset: Annotated[int, Query(ge=0, le=MAX_CHUNK_OFFSET)] = 0,
) -> ChunkPageOut:
    with _database_errors_as_503():
        page = _store(request).list_chunks(
            actor, document_id, revision_no, limit=limit, offset=offset
        )
    if page is None:
        raise _not_found()
    chunk_set = page.chunk_set
    return ChunkPageOut(
        chunk_set=None
        if chunk_set is None
        else ChunkSetOut(
            chunker_version=chunk_set.chunker_version,
            chunk_count=chunk_set.chunk_count,
            stored_count=chunk_set.stored_count,
            verified_complete=chunk_set.verified_complete,
        ),
        items=[_chunk(item) for item in page.items],
        total=page.total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/v1/jobs/{job_id}",
    tags=["jobs"],
    response_model=JobViewOut,
    summary="Get an ingestion job",
    description=(
        "The reviewed fields of an ingestion job: never its payload, idempotency key or worker."
    ),
)
def get_job(
    job_id: UUID,
    request: Request,
    actor: Annotated[ActorContext, Depends(document_actor)],
) -> JobViewOut:
    with _database_errors_as_503():
        job = _store(request).get_job(actor, job_id)
    if job is None:
        raise _not_found()
    return JobViewOut(
        id=job.id,
        kind=job.kind,
        status=job.status,
        attempt=job.attempt,
        max_attempts=job.max_attempts,
        run_after=job.run_after,
        last_error=job.last_error,
        lease_expires_at=job.lease_expires_at,
        lease_expired=job.lease_expired,
        created_at=job.created_at,
        updated_at=job.updated_at,
        finished_at=job.finished_at,
    )
