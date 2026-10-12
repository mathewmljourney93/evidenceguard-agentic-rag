"""Documents and revisions: the documents and document_revisions tables.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-12

Written to match ``evidenceguard_persistence.models.Document`` and ``DocumentRevision``; the
integration tests run ``alembic check`` against PostgreSQL to detect drift. The constraint text
is spelled out here rather than imported, so this revision stays fixed if the application
constants change later.

The two tables reference each other, so the order matters:

1. ``documents`` is created without its active-revision foreign key;
2. ``document_revisions`` is created with its foreign keys, including the self-reference;
3. ``fk_documents_active_revision`` is added to ``documents``.

Downgrade drops that foreign key first, then the revisions table, then the documents table. No
extension is created and no existing table is changed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ONE_ACTIVE_WHERE = "status = 'active'"


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("vendor_id", sa.Uuid(), nullable=False),
        sa.Column("document_key", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column(
            "authenticity",
            sa.String(length=32),
            server_default=sa.text("'not_established'"),
            nullable=False,
        ),
        sa.Column("latest_revision_no", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("active_revision_id", sa.Uuid(), nullable=True),
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
        sa.CheckConstraint(
            "document_key ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$'", name=op.f("ck_documents_document_key")
        ),
        sa.CheckConstraint("char_length(btrim(title)) >= 1", name=op.f("ck_documents_title")),
        sa.CheckConstraint(
            "source_type IN ('contract', 'third_party_report', 'vendor_statement')",
            name=op.f("ck_documents_source_type"),
        ),
        sa.CheckConstraint(
            "authenticity = 'not_established'", name=op.f("ck_documents_authenticity")
        ),
        sa.CheckConstraint("latest_revision_no >= 0", name=op.f("ck_documents_latest_revision_no")),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_documents_tenant_id_tenants")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "vendor_id"],
            ["vendors.tenant_id", "vendors.id"],
            name=op.f("fk_documents_tenant_id_vendor_id_vendors"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_documents_tenant_id_id")),
        sa.UniqueConstraint(
            "tenant_id",
            "vendor_id",
            "document_key",
            name=op.f("uq_documents_tenant_id_vendor_id_document_key"),
        ),
    )
    op.create_table(
        "document_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column("version_label", sa.String(length=64), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("failure_reason", sa.String(length=64), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("media_type", sa.String(length=32), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_by_revision_id", sa.Uuid(), nullable=True),
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
        sa.CheckConstraint(
            "status IN ('active', 'failed', 'pending', 'processing', 'superseded')",
            name=op.f("ck_document_revisions_status"),
        ),
        sa.CheckConstraint("revision_no >= 1", name=op.f("ck_document_revisions_revision_no")),
        sa.CheckConstraint(
            "version_label IS NULL OR char_length(btrim(version_label)) >= 1",
            name=op.f("ck_document_revisions_version_label"),
        ),
        sa.CheckConstraint(
            "failure_reason IS NULL OR failure_reason ~ '^[a-z][a-z0-9_]{0,63}$'",
            name=op.f("ck_document_revisions_failure_reason_code"),
        ),
        sa.CheckConstraint(
            "sha256 ~ '^[0-9a-f]{64}$'", name=op.f("ck_document_revisions_sha256_hex")
        ),
        sa.CheckConstraint(
            "media_type IN ('text/markdown', 'text/plain')",
            name=op.f("ck_document_revisions_media_type"),
        ),
        sa.CheckConstraint("byte_size >= 1", name=op.f("ck_document_revisions_byte_size")),
        sa.CheckConstraint(
            "(status = 'failed') = (failure_reason IS NOT NULL)",
            name=op.f("ck_document_revisions_failure_reason_when_failed"),
        ),
        sa.CheckConstraint(
            "(status = 'failed') = (failed_at IS NOT NULL)",
            name=op.f("ck_document_revisions_failed_at_when_failed"),
        ),
        sa.CheckConstraint(
            "(status = 'superseded') = (superseded_at IS NOT NULL)",
            name=op.f("ck_document_revisions_superseded_at_when_superseded"),
        ),
        sa.CheckConstraint(
            "(status = 'superseded') = (superseded_by_revision_id IS NOT NULL)",
            name=op.f("ck_document_revisions_superseded_by_when_superseded"),
        ),
        sa.CheckConstraint(
            "status <> 'active' OR activated_at IS NOT NULL",
            name=op.f("ck_document_revisions_activated_at_when_active"),
        ),
        sa.CheckConstraint(
            "status NOT IN ('pending', 'processing', 'failed') OR activated_at IS NULL",
            name=op.f("ck_document_revisions_no_activated_at_before_settled"),
        ),
        sa.CheckConstraint(
            "superseded_by_revision_id IS NULL OR superseded_by_revision_id <> id",
            name=op.f("ck_document_revisions_not_superseded_by_self"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_document_revisions_tenant_id_tenants")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["documents.tenant_id", "documents.id"],
            name=op.f("fk_document_revisions_tenant_id_document_id_documents"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id", "superseded_by_revision_id"],
            [
                "document_revisions.tenant_id",
                "document_revisions.document_id",
                "document_revisions.id",
            ],
            name="fk_document_revisions_superseded_by",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_revisions")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_document_revisions_tenant_id_id")),
        sa.UniqueConstraint(
            "tenant_id",
            "document_id",
            "id",
            name=op.f("uq_document_revisions_tenant_id_document_id_id"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "document_id",
            "revision_no",
            name=op.f("uq_document_revisions_tenant_id_document_id_revision_no"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "document_id",
            "sha256",
            name=op.f("uq_document_revisions_tenant_id_document_id_sha256"),
        ),
    )
    op.create_index(
        "uq_document_revisions_one_active",
        "document_revisions",
        ["tenant_id", "document_id"],
        unique=True,
        postgresql_where=sa.text(ONE_ACTIVE_WHERE),
    )
    op.create_foreign_key(
        "fk_documents_active_revision",
        "documents",
        "document_revisions",
        ["tenant_id", "id", "active_revision_id"],
        ["tenant_id", "document_id", "id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_documents_active_revision", "documents", type_="foreignkey")
    op.drop_index(
        "uq_document_revisions_one_active",
        table_name="document_revisions",
        postgresql_where=sa.text(ONE_ACTIVE_WHERE),
    )
    op.drop_table("document_revisions")
    op.drop_table("documents")
