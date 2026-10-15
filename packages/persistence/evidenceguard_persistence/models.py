"""The schema: tenants, users, API keys and vendors (M2a), durable jobs (M3a, ADR-0007),
documents with their revisions (M3c, ADR-0009), and chunk sets with their chunks (M3d, ADR-0010).

These models are the single source of the schema. Migrations are written to match them, and
``alembic check`` (run by the PostgreSQL integration tests) fails if they drift apart.

Tenancy rules:

- ``tenants`` is the root table.
- Every tenant-scoped table has ``tenant_id`` referencing ``tenants`` and a unique
  ``(tenant_id, id)``, so other tables can reference it in a tenant-safe way.
- ``api_keys`` references ``users`` through ``(tenant_id, user_id)``, so a key can never belong
  to a user in another tenant.

API keys store only a lookup prefix (unique across all tenants, so lookup is unambiguous) and
the SHA-256 hex digest of the secret. Plaintext secrets are never stored.

``jobs`` holds durable work items. PostgreSQL enforces their structural invariants (status values,
attempt bounds, lease fields exactly while running, ``finished_at`` exactly for terminal jobs,
identifier formats, a JSON *object* payload). The finer payload rules (identifier keys, canonical
UUID values, no tenant field, the 4,096-byte canonical cap) are enforced by application
validation in ``evidenceguard_domain.jobs``, not by the database.

``chunk_sets`` and ``chunks`` (M3d, ADR-0010) hold a revision's verified chunks. A chunk set is
keyed by ``(tenant_id, revision_id)`` (it has no ``id`` column) and references the revision through
``(tenant_id, revision_id)``; each chunk references its set through ``(tenant_id, revision_id,
chunker_version)``, so the two can never disagree on the version. PostgreSQL enforces the length,
ordinal, span and header checks; immutability (no update or delete) is an application invariant.

``documents`` and ``document_revisions`` reference vendors and documents through composite
tenant keys. The active pointer and the supersession link reference ``(tenant_id, document_id,
id)``, so they can only name a revision of the same document in the same tenant. PostgreSQL
enforces the status/field pairing (named checks) and at most one active revision per document
(a partial unique index). The failure-code check enforces only the fixed-code pattern; limiting
codes to ``RevisionFailureCode`` is application validation. Trusted application transitions in
``evidenceguard_persistence.documents`` enforce the rest: that the pointer names the revision
whose status is ``active``, the transition graph, revision-number allocation and immutability.
There are no triggers.
"""

from datetime import date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from evidenceguard_domain.chunks import (
    CHUNKER_VERSION_MAX_LENGTH,
    CHUNKER_VERSION_PATTERN,
    MAX_CHUNK_CHARS,
    MAX_CHUNKS_PER_REVISION,
    MAX_SECTION_DEPTH,
)
from evidenceguard_domain.evidence import Authenticity, SourceType
from evidenceguard_domain.jobs import (
    ERROR_CODE_MAX_LENGTH,
    IDEMPOTENCY_KEY_MAX_LENGTH,
    KIND_MAX_LENGTH,
    KIND_PATTERN,
    MAX_MAX_ATTEMPTS,
    MIN_MAX_ATTEMPTS,
    TERMINAL_STATUSES,
    WORKER_ID_MAX_LENGTH,
    JobStatus,
)
from evidenceguard_domain.revisions import (
    DOCUMENT_KEY_MAX_LENGTH,
    DOCUMENT_KEY_PATTERN,
    FAILURE_CODE_PATTERN,
    SHA256_PATTERN,
    TITLE_MAX_LENGTH,
    VERSION_LABEL_MAX_LENGTH,
    MediaType,
    RevisionStatus,
)

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class UserRole(StrEnum):
    """Roles stored for users. ``admin`` grants no approval rights (see ADR-0004)."""

    REVIEWER = "reviewer"
    APPROVER = "approver"
    ADMIN = "admin"


ROLE_CHECK = "role IN ({})".format(", ".join(f"'{role.value}'" for role in UserRole))
SECRET_SHA256_CHECK = "secret_sha256 ~ '^[0-9a-f]{64}$'"


def _sql_list(values: Any) -> str:
    return ", ".join(f"'{value}'" for value in sorted(str(v) for v in values))


JOB_STATUS_CHECK = f"status IN ({_sql_list(JobStatus)})"
JOB_KIND_CHECK = f"kind ~ '{KIND_PATTERN}'"
JOB_IDEMPOTENCY_KEY_CHECK = "char_length(idempotency_key) >= 1"
JOB_PAYLOAD_CHECK = "jsonb_typeof(payload) = 'object'"
JOB_ATTEMPT_CHECK = "attempt >= 0 AND attempt <= max_attempts"
JOB_MAX_ATTEMPTS_CHECK = f"max_attempts BETWEEN {MIN_MAX_ATTEMPTS} AND {MAX_MAX_ATTEMPTS}"
JOB_LEASE_CHECK = (
    "(status = 'running' AND locked_by IS NOT NULL AND lease_expires_at IS NOT NULL "
    "AND attempt >= 1) OR "
    "(status <> 'running' AND locked_by IS NULL AND lease_expires_at IS NULL)"
)
JOB_FINISHED_CHECK = (
    f"(status IN ({_sql_list(TERMINAL_STATUSES)}) AND finished_at IS NOT NULL) OR "
    f"(status NOT IN ({_sql_list(TERMINAL_STATUSES)}) AND finished_at IS NULL)"
)
JOB_LAST_ERROR_CHECK = f"last_error IS NULL OR last_error ~ '{KIND_PATTERN}'"
JOB_QUEUED_INDEX_WHERE = "status = 'queued'"
JOB_RUNNING_INDEX_WHERE = "status = 'running'"

DOCUMENT_KEY_CHECK = f"document_key ~ '{DOCUMENT_KEY_PATTERN}'"
DOCUMENT_TITLE_CHECK = "char_length(btrim(title)) >= 1"
DOCUMENT_SOURCE_TYPE_CHECK = f"source_type IN ({_sql_list(SourceType)})"
DOCUMENT_AUTHENTICITY_CHECK = f"authenticity = '{Authenticity.NOT_ESTABLISHED.value}'"
DOCUMENT_LATEST_REVISION_NO_CHECK = "latest_revision_no >= 0"
REVISION_STATUS_CHECK = f"status IN ({_sql_list(RevisionStatus)})"
REVISION_NO_CHECK = "revision_no >= 1"
REVISION_VERSION_LABEL_CHECK = "version_label IS NULL OR char_length(btrim(version_label)) >= 1"
REVISION_FAILURE_REASON_CODE_CHECK = (
    f"failure_reason IS NULL OR failure_reason ~ '{FAILURE_CODE_PATTERN}'"
)
REVISION_SHA256_CHECK = f"sha256 ~ '{SHA256_PATTERN}'"
REVISION_MEDIA_TYPE_CHECK = f"media_type IN ({_sql_list(MediaType)})"
REVISION_BYTE_SIZE_CHECK = "byte_size >= 1"
REVISION_FAILURE_REASON_WHEN_FAILED_CHECK = "(status = 'failed') = (failure_reason IS NOT NULL)"
REVISION_FAILED_AT_WHEN_FAILED_CHECK = "(status = 'failed') = (failed_at IS NOT NULL)"
REVISION_SUPERSEDED_AT_WHEN_SUPERSEDED_CHECK = (
    "(status = 'superseded') = (superseded_at IS NOT NULL)"
)
REVISION_SUPERSEDED_BY_WHEN_SUPERSEDED_CHECK = (
    "(status = 'superseded') = (superseded_by_revision_id IS NOT NULL)"
)
REVISION_ACTIVATED_AT_WHEN_ACTIVE_CHECK = "status <> 'active' OR activated_at IS NOT NULL"
REVISION_NO_ACTIVATED_AT_BEFORE_SETTLED_CHECK = (
    "status NOT IN ('pending', 'processing', 'failed') OR activated_at IS NULL"
)
REVISION_NOT_SUPERSEDED_BY_SELF_CHECK = (
    "superseded_by_revision_id IS NULL OR superseded_by_revision_id <> id"
)
REVISION_ONE_ACTIVE_INDEX = "uq_document_revisions_one_active"
REVISION_ONE_ACTIVE_WHERE = "status = 'active'"
DOCUMENT_ACTIVE_REVISION_FK = "fk_documents_active_revision"
REVISION_SUPERSEDED_BY_FK = "fk_document_revisions_superseded_by"

CHUNK_SET_CHUNKER_VERSION_CHECK = f"chunker_version ~ '{CHUNKER_VERSION_PATTERN}'"
CHUNK_SET_CHUNK_COUNT_CHECK = f"chunk_count BETWEEN 1 AND {MAX_CHUNKS_PER_REVISION}"
CHUNK_SET_MANIFEST_SHA256_CHECK = f"manifest_sha256 ~ '{SHA256_PATTERN}'"
CHUNK_ORDINAL_CHECK = f"ordinal BETWEEN 0 AND {MAX_CHUNKS_PER_REVISION - 1}"
CHUNK_TEXT_CHECK = f"char_length(text) BETWEEN 1 AND {MAX_CHUNK_CHARS}"
CHUNK_CONTENT_SHA256_CHECK = f"content_sha256 ~ '{SHA256_PATTERN}'"
CHUNK_SECTION_PATH_CHECK = f"cardinality(section_path) <= {MAX_SECTION_DEPTH}"
CHUNK_LINES_CHECK = "line_start >= 1 AND line_end >= line_start"
CHUNK_CHARS_CHECK = "char_start >= 0 AND char_end > char_start"
CHUNK_HEADER_ALL_OR_NONE_CHECK = (
    "(header_line_start IS NULL AND header_line_end IS NULL AND header_char_start IS NULL "
    "AND header_char_end IS NULL) OR (header_line_start IS NOT NULL AND header_line_end IS NOT "
    "NULL AND header_char_start IS NOT NULL AND header_char_end IS NOT NULL)"
)
CHUNK_HEADER_ONLY_TABLES_CHECK = "header_char_start IS NULL OR is_table"
CHUNK_HEADER_BEFORE_BODY_CHECK = (
    "header_char_start IS NULL OR (header_char_start >= 0 AND header_char_end > "
    "header_char_start AND header_char_end <= char_start AND header_line_start >= 1 AND "
    "header_line_end >= header_line_start AND header_line_end < line_start)"
)
CHUNK_SET_PRIMARY_KEY = "pk_chunk_sets"
# Defined here: inside ``Chunk`` the column attribute ``text`` shadows ``sqlalchemy.text``.
EMPTY_TEXT_ARRAY = text("'{}'")


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        CheckConstraint(ROLE_CHECK, name="role"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"))
    role: Mapped[str] = mapped_column(String(16))


class ApiKey(Base):
    __tablename__ = "api_keys"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(["tenant_id", "user_id"], ["users.tenant_id", "users.id"]),
        CheckConstraint(SECRET_SHA256_CHECK, name="secret_sha256_hex"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"))
    user_id: Mapped[UUID] = mapped_column(Uuid)
    prefix: Mapped[str] = mapped_column(String(32), unique=True)
    secret_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Vendor(Base):
    __tablename__ = "vendors"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "slug"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"))
    slug: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(200))


class Job(Base):
    """A durable job. Every lease and scheduling decision uses PostgreSQL ``clock_timestamp()``."""

    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "kind", "idempotency_key"),
        CheckConstraint(JOB_STATUS_CHECK, name="status"),
        CheckConstraint(JOB_KIND_CHECK, name="kind"),
        CheckConstraint(JOB_IDEMPOTENCY_KEY_CHECK, name="idempotency_key"),
        CheckConstraint(JOB_PAYLOAD_CHECK, name="payload_object"),
        CheckConstraint(JOB_ATTEMPT_CHECK, name="attempt_bounds"),
        CheckConstraint(JOB_MAX_ATTEMPTS_CHECK, name="max_attempts_range"),
        CheckConstraint(JOB_LEASE_CHECK, name="lease_while_running"),
        CheckConstraint(JOB_FINISHED_CHECK, name="finished_when_terminal"),
        CheckConstraint(JOB_LAST_ERROR_CHECK, name="last_error_code"),
        Index(
            "ix_jobs_queued_run_after",
            "run_after",
            "id",
            postgresql_where=text(JOB_QUEUED_INDEX_WHERE),
        ),
        Index(
            "ix_jobs_running_lease_expires_at",
            "lease_expires_at",
            postgresql_where=text(JOB_RUNNING_INDEX_WHERE),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"))
    kind: Mapped[str] = mapped_column(String(KIND_MAX_LENGTH))
    idempotency_key: Mapped[str] = mapped_column(String(IDEMPOTENCY_KEY_MAX_LENGTH))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16))
    attempt: Mapped[int] = mapped_column(Integer)
    max_attempts: Mapped[int] = mapped_column(Integer)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[str | None] = mapped_column(String(WORKER_ID_MAX_LENGTH))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(ERROR_CODE_MAX_LENGTH))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Document(Base):
    """A tenant's document for one vendor, identified by ``(tenant_id, vendor_id, document_key)``.

    ``active_revision_id`` names the single active revision. Its composite foreign key includes
    the tenant and this document, so it can never name another document's or tenant's revision.
    """

    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "vendor_id", "document_key"),
        ForeignKeyConstraint(["tenant_id", "vendor_id"], ["vendors.tenant_id", "vendors.id"]),
        ForeignKeyConstraint(
            ["tenant_id", "id", "active_revision_id"],
            [
                "document_revisions.tenant_id",
                "document_revisions.document_id",
                "document_revisions.id",
            ],
            name=DOCUMENT_ACTIVE_REVISION_FK,
            use_alter=True,
        ),
        CheckConstraint(DOCUMENT_KEY_CHECK, name="document_key"),
        CheckConstraint(DOCUMENT_TITLE_CHECK, name="title"),
        CheckConstraint(DOCUMENT_SOURCE_TYPE_CHECK, name="source_type"),
        CheckConstraint(DOCUMENT_AUTHENTICITY_CHECK, name="authenticity"),
        CheckConstraint(DOCUMENT_LATEST_REVISION_NO_CHECK, name="latest_revision_no"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"))
    vendor_id: Mapped[UUID] = mapped_column(Uuid)
    document_key: Mapped[str] = mapped_column(String(DOCUMENT_KEY_MAX_LENGTH))
    title: Mapped[str] = mapped_column(String(TITLE_MAX_LENGTH))
    source_type: Mapped[str] = mapped_column(String(32))
    authenticity: Mapped[str] = mapped_column(
        String(32), server_default=text(f"'{Authenticity.NOT_ESTABLISHED.value}'")
    )
    latest_revision_no: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    active_revision_id: Mapped[UUID | None] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentRevision(Base):
    """One uploaded revision of a document: its exact content, fingerprint and lifecycle state.

    ``sha256`` and ``byte_size`` describe the bytes exactly as uploaded; ``content_text`` is those
    bytes decoded as strict UTF-8, never normalized (see ``evidenceguard_domain.revisions``).
    """

    __tablename__ = "document_revisions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "document_id", "id"),
        UniqueConstraint("tenant_id", "document_id", "revision_no"),
        UniqueConstraint("tenant_id", "document_id", "sha256"),
        ForeignKeyConstraint(["tenant_id", "document_id"], ["documents.tenant_id", "documents.id"]),
        ForeignKeyConstraint(
            ["tenant_id", "document_id", "superseded_by_revision_id"],
            [
                "document_revisions.tenant_id",
                "document_revisions.document_id",
                "document_revisions.id",
            ],
            name=REVISION_SUPERSEDED_BY_FK,
        ),
        CheckConstraint(REVISION_STATUS_CHECK, name="status"),
        CheckConstraint(REVISION_NO_CHECK, name="revision_no"),
        CheckConstraint(REVISION_VERSION_LABEL_CHECK, name="version_label"),
        CheckConstraint(REVISION_FAILURE_REASON_CODE_CHECK, name="failure_reason_code"),
        CheckConstraint(REVISION_SHA256_CHECK, name="sha256_hex"),
        CheckConstraint(REVISION_MEDIA_TYPE_CHECK, name="media_type"),
        CheckConstraint(REVISION_BYTE_SIZE_CHECK, name="byte_size"),
        CheckConstraint(
            REVISION_FAILURE_REASON_WHEN_FAILED_CHECK, name="failure_reason_when_failed"
        ),
        CheckConstraint(REVISION_FAILED_AT_WHEN_FAILED_CHECK, name="failed_at_when_failed"),
        CheckConstraint(
            REVISION_SUPERSEDED_AT_WHEN_SUPERSEDED_CHECK, name="superseded_at_when_superseded"
        ),
        CheckConstraint(
            REVISION_SUPERSEDED_BY_WHEN_SUPERSEDED_CHECK, name="superseded_by_when_superseded"
        ),
        CheckConstraint(REVISION_ACTIVATED_AT_WHEN_ACTIVE_CHECK, name="activated_at_when_active"),
        CheckConstraint(
            REVISION_NO_ACTIVATED_AT_BEFORE_SETTLED_CHECK, name="no_activated_at_before_settled"
        ),
        CheckConstraint(REVISION_NOT_SUPERSEDED_BY_SELF_CHECK, name="not_superseded_by_self"),
        Index(
            REVISION_ONE_ACTIVE_INDEX,
            "tenant_id",
            "document_id",
            unique=True,
            postgresql_where=text(REVISION_ONE_ACTIVE_WHERE),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"))
    document_id: Mapped[UUID] = mapped_column(Uuid)
    revision_no: Mapped[int] = mapped_column(Integer)
    version_label: Mapped[str | None] = mapped_column(String(VERSION_LABEL_MAX_LENGTH))
    effective_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16))
    failure_reason: Mapped[str | None] = mapped_column(String(64))
    sha256: Mapped[str] = mapped_column(String(64))
    media_type: Mapped[str] = mapped_column(String(32))
    byte_size: Mapped[int] = mapped_column(BigInteger)
    content_text: Mapped[str] = mapped_column(Text)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_by_revision_id: Mapped[UUID | None] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChunkSet(Base):
    """The completeness record of one revision's chunks: the authoritative ``chunker_version``,
    the chunk count and the canonical manifest digest (one row per revision in v1)."""

    __tablename__ = "chunk_sets"
    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "revision_id", name=CHUNK_SET_PRIMARY_KEY),
        UniqueConstraint("tenant_id", "revision_id", "chunker_version"),
        ForeignKeyConstraint(
            ["tenant_id", "revision_id"], ["document_revisions.tenant_id", "document_revisions.id"]
        ),
        CheckConstraint(CHUNK_SET_CHUNKER_VERSION_CHECK, name="chunker_version"),
        CheckConstraint(CHUNK_SET_CHUNK_COUNT_CHECK, name="chunk_count"),
        CheckConstraint(CHUNK_SET_MANIFEST_SHA256_CHECK, name="manifest_sha256"),
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"))
    revision_id: Mapped[UUID] = mapped_column(Uuid)
    chunker_version: Mapped[str] = mapped_column(String(CHUNKER_VERSION_MAX_LENGTH))
    chunk_count: Mapped[int] = mapped_column(Integer)
    manifest_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Chunk(Base):
    """One verbatim chunk of a revision with its source span (see ``evidenceguard_domain.chunks``).

    ``id`` is the deterministic chunk ID. ``(tenant_id, id)`` is unique for later tenant-scoped
    references from embeddings and citations. Rows are never updated or deleted by application
    code.
    """

    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("tenant_id", "revision_id", "chunker_version", "ordinal"),
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "revision_id", "chunker_version"],
            ["chunk_sets.tenant_id", "chunk_sets.revision_id", "chunk_sets.chunker_version"],
        ),
        CheckConstraint(CHUNK_ORDINAL_CHECK, name="ordinal"),
        CheckConstraint(CHUNK_TEXT_CHECK, name="text_length"),
        CheckConstraint(CHUNK_CONTENT_SHA256_CHECK, name="content_sha256"),
        CheckConstraint(CHUNK_SECTION_PATH_CHECK, name="section_path_depth"),
        CheckConstraint(CHUNK_LINES_CHECK, name="lines"),
        CheckConstraint(CHUNK_CHARS_CHECK, name="chars"),
        CheckConstraint(CHUNK_HEADER_ALL_OR_NONE_CHECK, name="header_all_or_none"),
        CheckConstraint(CHUNK_HEADER_ONLY_TABLES_CHECK, name="header_only_tables"),
        CheckConstraint(CHUNK_HEADER_BEFORE_BODY_CHECK, name="header_before_body"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"))
    revision_id: Mapped[UUID] = mapped_column(Uuid)
    chunker_version: Mapped[str] = mapped_column(String(CHUNKER_VERSION_MAX_LENGTH))
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    content_sha256: Mapped[str] = mapped_column(String(64))
    section_path: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=EMPTY_TEXT_ARRAY)
    is_table: Mapped[bool] = mapped_column(Boolean)
    line_start: Mapped[int] = mapped_column(Integer)
    line_end: Mapped[int] = mapped_column(Integer)
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)
    header_line_start: Mapped[int | None] = mapped_column(Integer)
    header_line_end: Mapped[int | None] = mapped_column(Integer)
    header_char_start: Mapped[int | None] = mapped_column(Integer)
    header_char_end: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
