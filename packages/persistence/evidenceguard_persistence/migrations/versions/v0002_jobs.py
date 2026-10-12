"""Durable job core: the jobs table.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-12

Written to match ``evidenceguard_persistence.models.Job``; the integration tests run
``alembic check`` against PostgreSQL to detect drift. The constraint text is spelled out here
rather than imported, so this revision stays fixed if the application constants change later.
No extension is created and no existing table is changed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("run_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_by", sa.String(length=128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('dead', 'failed', 'queued', 'running', 'succeeded')",
            name=op.f("ck_jobs_status"),
        ),
        sa.CheckConstraint("kind ~ '^[a-z][a-z0-9_]{0,63}$'", name=op.f("ck_jobs_kind")),
        sa.CheckConstraint(
            "char_length(idempotency_key) >= 1", name=op.f("ck_jobs_idempotency_key")
        ),
        sa.CheckConstraint("jsonb_typeof(payload) = 'object'", name=op.f("ck_jobs_payload_object")),
        sa.CheckConstraint(
            "attempt >= 0 AND attempt <= max_attempts", name=op.f("ck_jobs_attempt_bounds")
        ),
        sa.CheckConstraint(
            "max_attempts BETWEEN 1 AND 10", name=op.f("ck_jobs_max_attempts_range")
        ),
        sa.CheckConstraint(
            "(status = 'running' AND locked_by IS NOT NULL AND lease_expires_at IS NOT NULL "
            "AND attempt >= 1) OR "
            "(status <> 'running' AND locked_by IS NULL AND lease_expires_at IS NULL)",
            name=op.f("ck_jobs_lease_while_running"),
        ),
        sa.CheckConstraint(
            "(status IN ('dead', 'failed', 'succeeded') AND finished_at IS NOT NULL) OR "
            "(status NOT IN ('dead', 'failed', 'succeeded') AND finished_at IS NULL)",
            name=op.f("ck_jobs_finished_when_terminal"),
        ),
        sa.CheckConstraint(
            "last_error IS NULL OR last_error ~ '^[a-z][a-z0-9_]{0,63}$'",
            name=op.f("ck_jobs_last_error_code"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_jobs_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_jobs_tenant_id_id")),
        sa.UniqueConstraint(
            "tenant_id",
            "kind",
            "idempotency_key",
            name=op.f("uq_jobs_tenant_id_kind_idempotency_key"),
        ),
    )
    op.create_index(
        "ix_jobs_queued_run_after",
        "jobs",
        ["run_after", "id"],
        unique=False,
        postgresql_where=sa.text("status = 'queued'"),
    )
    op.create_index(
        "ix_jobs_running_lease_expires_at",
        "jobs",
        ["lease_expires_at"],
        unique=False,
        postgresql_where=sa.text("status = 'running'"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_jobs_running_lease_expires_at",
        table_name="jobs",
        postgresql_where=sa.text("status = 'running'"),
    )
    op.drop_index(
        "ix_jobs_queued_run_after",
        table_name="jobs",
        postgresql_where=sa.text("status = 'queued'"),
    )
    op.drop_table("jobs")
