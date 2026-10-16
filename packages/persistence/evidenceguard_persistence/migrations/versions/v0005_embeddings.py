"""Embeddings: pgvector, the lexical representation and the three embedding tables.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-16

Written to match ``evidenceguard_persistence.models`` (M4b, ADR-0014); the integration tests run
``alembic check`` against PostgreSQL to detect drift. The constraint text is spelled out here
rather than imported, so this revision stays fixed if the application constants change later.

Upgrade, in order:

1. ``CREATE EXTENSION IF NOT EXISTS vector``: this is the first migration that needs it;
2. two FK-target unique keys on existing tables (``uq_chunk_sets_binding`` and
   ``uq_chunks_membership``), which change no data;
3. ``chunks.search_vector``, a stored generated ``to_tsvector('simple'::regconfig, text)``,
   and its GIN index (this rewrites ``chunks``; chunk text, IDs and spans are unchanged);
4. ``embedding_profiles``, ``embedding_indexes``, then ``chunk_embeddings``.

Downgrade removes exactly this revision's objects in the reverse dependency order: the three
tables, the GIN index and the generated column, then the two unique keys. It **always leaves
the vector extension installed**, whether this revision created it or it was preinstalled: an
extension is database-wide and may serve unrelated objects, so removing it is an explicit
administrative operation outside Alembic. There is no extension-drop logic, ownership marker or
``CASCADE``. Every statement is plain DDL, so offline (``--sql``) rendering needs no database.
No HNSW or IVFFlat index and no trigger is created.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.types import UserDefinedType

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

IDENTIFIER = "'^[a-z][a-z0-9._-]{0,63}$'"
SHA256 = "'^[0-9a-f]{64}$'"


class _Vector1024(UserDefinedType[str]):
    """``vector(1024)`` DDL only; defined here so this revision does not depend on the models."""

    cache_ok = True

    def get_col_spec(self, **kw: object) -> str:
        return "VECTOR(1024)"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_unique_constraint(
        "uq_chunk_sets_binding",
        "chunk_sets",
        ["tenant_id", "revision_id", "chunker_version", "chunk_count", "manifest_sha256"],
    )
    op.create_unique_constraint(
        "uq_chunks_membership",
        "chunks",
        ["tenant_id", "revision_id", "chunker_version", "id", "content_sha256"],
    )
    op.add_column(
        "chunks",
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('simple'::regconfig, text)", persisted=True),
            nullable=True,
        ),
    )
    op.create_index("ix_chunks_search_vector", "chunks", ["search_vector"], postgresql_using="gin")

    op.create_table(
        "embedding_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("provider_id", sa.String(length=64), nullable=False),
        sa.Column("model_id", sa.String(length=64), nullable=False),
        sa.Column("algorithm_version", sa.String(length=64), nullable=False),
        sa.Column("dims", sa.Integer(), nullable=False),
        sa.Column("normalization", sa.String(length=16), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("allows_zero_vectors", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            f"provider_id ~ {IDENTIFIER}", name=op.f("ck_embedding_profiles_provider_id")
        ),
        sa.CheckConstraint(f"model_id ~ {IDENTIFIER}", name=op.f("ck_embedding_profiles_model_id")),
        sa.CheckConstraint(
            f"algorithm_version ~ {IDENTIFIER}",
            name=op.f("ck_embedding_profiles_algorithm_version"),
        ),
        sa.CheckConstraint("dims = 1024", name=op.f("ck_embedding_profiles_dims")),
        sa.CheckConstraint(
            "normalization = 'l2'", name=op.f("ck_embedding_profiles_normalization")
        ),
        sa.CheckConstraint(
            f"fingerprint ~ {SHA256}", name=op.f("ck_embedding_profiles_fingerprint")
        ),
        sa.CheckConstraint(
            "allows_zero_vectors = (provider_id = 'offline')",
            name=op.f("ck_embedding_profiles_zero_policy"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_embedding_profiles_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_embedding_profiles")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_embedding_profiles_tenant_id_id")),
        sa.UniqueConstraint(
            "tenant_id", "fingerprint", name="uq_embedding_profiles_tenant_id_fingerprint"
        ),
        sa.UniqueConstraint(
            "tenant_id", "id", "dims", "allows_zero_vectors", name="uq_embedding_profiles_binding"
        ),
    )
    op.create_table(
        "embedding_indexes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("chunker_version", sa.String(length=32), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("manifest_sha256", sa.String(length=64), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("dims", sa.Integer(), nullable=False),
        sa.Column("allows_zero_vectors", sa.Boolean(), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'building'"), nullable=False
        ),
        sa.Column("vector_manifest_sha256", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('building', 'ready')", name=op.f("ck_embedding_indexes_status")
        ),
        sa.CheckConstraint("dims = 1024", name=op.f("ck_embedding_indexes_dims")),
        sa.CheckConstraint(
            f"vector_manifest_sha256 IS NULL OR vector_manifest_sha256 ~ {SHA256}",
            name=op.f("ck_embedding_indexes_vector_manifest_sha256"),
        ),
        sa.CheckConstraint(
            "(status = 'ready') = (ready_at IS NOT NULL)",
            name=op.f("ck_embedding_indexes_ready_at_when_ready"),
        ),
        sa.CheckConstraint(
            "(status = 'ready') = (vector_manifest_sha256 IS NOT NULL)",
            name=op.f("ck_embedding_indexes_manifest_when_ready"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_embedding_indexes_tenant_id_tenants")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "revision_id", "chunker_version", "chunk_count", "manifest_sha256"],
            [
                "chunk_sets.tenant_id",
                "chunk_sets.revision_id",
                "chunk_sets.chunker_version",
                "chunk_sets.chunk_count",
                "chunk_sets.manifest_sha256",
            ],
            name="fk_embedding_indexes_chunk_set",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "profile_id", "dims", "allows_zero_vectors"],
            [
                "embedding_profiles.tenant_id",
                "embedding_profiles.id",
                "embedding_profiles.dims",
                "embedding_profiles.allows_zero_vectors",
            ],
            name="fk_embedding_indexes_profile",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_embedding_indexes")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_embedding_indexes_tenant_id_id")),
        sa.UniqueConstraint(
            "tenant_id",
            "revision_id",
            "chunker_version",
            "profile_id",
            name="uq_embedding_indexes_source",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            "revision_id",
            "chunker_version",
            "allows_zero_vectors",
            name="uq_embedding_indexes_binding",
        ),
    )
    op.create_index(
        "ix_embedding_indexes_eligibility",
        "embedding_indexes",
        ["tenant_id", "profile_id", "status"],
    )
    op.create_table(
        "chunk_embeddings",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("index_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("chunker_version", sa.String(length=32), nullable=False),
        sa.Column("allows_zero_vectors", sa.Boolean(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("embedding", _Vector1024(), nullable=False),
        sa.Column("vector_sha256", sa.String(length=64), nullable=False),
        sa.Column("is_zero", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "vector_sha256 = encode(sha256(vector_send(embedding)), 'hex')",
            name=op.f("ck_chunk_embeddings_vector_sha256"),
        ),
        sa.CheckConstraint(
            "is_zero = (vector_norm(embedding) = 0)", name=op.f("ck_chunk_embeddings_is_zero")
        ),
        sa.CheckConstraint(
            "NOT is_zero OR allows_zero_vectors", name=op.f("ck_chunk_embeddings_zero_policy")
        ),
        sa.CheckConstraint(
            "is_zero OR abs(vector_norm(embedding) - 1) <= 1e-6",
            name=op.f("ck_chunk_embeddings_unit_norm"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_chunk_embeddings_tenant_id_tenants")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "index_id", "revision_id", "chunker_version", "allows_zero_vectors"],
            [
                "embedding_indexes.tenant_id",
                "embedding_indexes.id",
                "embedding_indexes.revision_id",
                "embedding_indexes.chunker_version",
                "embedding_indexes.allows_zero_vectors",
            ],
            name="fk_chunk_embeddings_index",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "revision_id", "chunker_version", "chunk_id", "content_sha256"],
            [
                "chunks.tenant_id",
                "chunks.revision_id",
                "chunks.chunker_version",
                "chunks.id",
                "chunks.content_sha256",
            ],
            name="fk_chunk_embeddings_chunk",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "index_id", "chunk_id", name="pk_chunk_embeddings"),
    )


def downgrade() -> None:
    op.drop_table("chunk_embeddings")
    op.drop_index("ix_embedding_indexes_eligibility", table_name="embedding_indexes")
    op.drop_table("embedding_indexes")
    op.drop_table("embedding_profiles")
    op.drop_index("ix_chunks_search_vector", table_name="chunks", postgresql_using="gin")
    op.drop_column("chunks", "search_vector")
    op.drop_constraint("uq_chunks_membership", "chunks", type_="unique")
    op.drop_constraint("uq_chunk_sets_binding", "chunk_sets", type_="unique")
    # The vector extension is deliberately left installed (see the module docstring).
