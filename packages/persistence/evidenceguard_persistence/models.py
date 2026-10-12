"""The schema: tenants, users, API keys and vendors (M2a), and durable jobs (M3a, ADR-0007).

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
"""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

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
