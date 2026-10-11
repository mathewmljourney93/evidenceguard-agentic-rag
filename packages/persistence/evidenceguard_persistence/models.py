"""The M2a schema: tenants, users, API keys and vendors.

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
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    MetaData,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

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
