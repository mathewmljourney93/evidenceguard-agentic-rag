"""Chunks: the chunk_sets and chunks tables.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-13

Written to match ``evidenceguard_persistence.models.ChunkSet`` and ``Chunk``; the integration
tests run ``alembic check`` against PostgreSQL to detect drift. The constraint text is spelled
out here rather than imported, so this revision stays fixed if the application constants change
later.

Upgrade creates ``chunk_sets`` (keyed by ``(tenant_id, revision_id)``, referencing the revision),
then ``chunks`` (referencing its set through ``(tenant_id, revision_id, chunker_version)``).
There are no circular references. Downgrade drops ``chunks``, then ``chunk_sets``. No extension,
trigger or embedding table is created, and no existing table is changed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chunk_sets",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("chunker_version", sa.String(length=32), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("manifest_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "chunker_version ~ '^[a-z0-9][a-z0-9.-]{0,31}$'",
            name=op.f("ck_chunk_sets_chunker_version"),
        ),
        sa.CheckConstraint(
            "chunk_count BETWEEN 1 AND 4096", name=op.f("ck_chunk_sets_chunk_count")
        ),
        sa.CheckConstraint(
            "manifest_sha256 ~ '^[0-9a-f]{64}$'", name=op.f("ck_chunk_sets_manifest_sha256")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_chunk_sets_tenant_id_tenants")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "revision_id"],
            ["document_revisions.tenant_id", "document_revisions.id"],
            name=op.f("fk_chunk_sets_tenant_id_revision_id_document_revisions"),
        ),
        sa.PrimaryKeyConstraint("tenant_id", "revision_id", name="pk_chunk_sets"),
        sa.UniqueConstraint(
            "tenant_id",
            "revision_id",
            "chunker_version",
            name=op.f("uq_chunk_sets_tenant_id_revision_id_chunker_version"),
        ),
    )
    op.create_table(
        "chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("chunker_version", sa.String(length=32), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "section_path",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("is_table", sa.Boolean(), nullable=False),
        sa.Column("line_start", sa.Integer(), nullable=False),
        sa.Column("line_end", sa.Integer(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("header_line_start", sa.Integer(), nullable=True),
        sa.Column("header_line_end", sa.Integer(), nullable=True),
        sa.Column("header_char_start", sa.Integer(), nullable=True),
        sa.Column("header_char_end", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("ordinal BETWEEN 0 AND 4095", name=op.f("ck_chunks_ordinal")),
        sa.CheckConstraint(
            "char_length(text) BETWEEN 1 AND 4000", name=op.f("ck_chunks_text_length")
        ),
        sa.CheckConstraint(
            "content_sha256 ~ '^[0-9a-f]{64}$'", name=op.f("ck_chunks_content_sha256")
        ),
        sa.CheckConstraint(
            "cardinality(section_path) <= 6", name=op.f("ck_chunks_section_path_depth")
        ),
        sa.CheckConstraint(
            "line_start >= 1 AND line_end >= line_start", name=op.f("ck_chunks_lines")
        ),
        sa.CheckConstraint(
            "char_start >= 0 AND char_end > char_start", name=op.f("ck_chunks_chars")
        ),
        sa.CheckConstraint(
            "(header_line_start IS NULL AND header_line_end IS NULL AND header_char_start IS NULL "
            "AND header_char_end IS NULL) OR (header_line_start IS NOT NULL AND header_line_end "
            "IS NOT NULL AND header_char_start IS NOT NULL AND header_char_end IS NOT NULL)",
            name=op.f("ck_chunks_header_all_or_none"),
        ),
        sa.CheckConstraint(
            "header_char_start IS NULL OR is_table", name=op.f("ck_chunks_header_only_tables")
        ),
        sa.CheckConstraint(
            "header_char_start IS NULL OR (header_char_start >= 0 AND header_char_end > "
            "header_char_start AND header_char_end <= char_start AND header_line_start >= 1 AND "
            "header_line_end >= header_line_start AND header_line_end < line_start)",
            name=op.f("ck_chunks_header_before_body"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_chunks_tenant_id_tenants")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "revision_id", "chunker_version"],
            ["chunk_sets.tenant_id", "chunk_sets.revision_id", "chunk_sets.chunker_version"],
            name=op.f("fk_chunks_tenant_id_revision_id_chunker_version_chunk_sets"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chunks")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_chunks_tenant_id_id")),
        sa.UniqueConstraint(
            "tenant_id",
            "revision_id",
            "chunker_version",
            "ordinal",
            name=op.f("uq_chunks_tenant_id_revision_id_chunker_version_ordinal"),
        ),
    )


def downgrade() -> None:
    op.drop_table("chunks")
    op.drop_table("chunk_sets")
