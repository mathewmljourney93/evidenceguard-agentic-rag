"""Reviews: captured snapshot facts, pinned configuration and the run_review job link.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-22

Written to match ``evidenceguard_persistence.models`` (M5d, ADR-0022); the integration tests run
``alembic check`` against PostgreSQL to detect drift. The constraint text is spelled out here
rather than imported, so this revision stays fixed if the application constants change later.

Upgrade creates ``reviews``, then ``review_bindings`` and ``review_excluded_revisions``. Every
foreign key uses the default ``NO ACTION`` (no cascades). Downgrade drops exactly these three
tables in reverse dependency order. Every statement is plain DDL, so offline (``--sql``)
rendering needs no database.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SHA256 = "'^[0-9a-f]{64}$'"
IDENTIFIER = "'^[a-z][a-z0-9._-]{0,63}$'"
ARTIFACT_ID = "'^[a-z][a-z0-9_]{0,31}$'"
CHUNKER_VERSION = "'^[a-z0-9][a-z0-9.-]{0,31}$'"

HEX_COLUMNS = (
    "request_sha256",
    "configuration_sha256",
    "snapshot_sha256",
    "fingerprint",
    "retrieval_config_sha256",
    "template_sha256",
    "verifier_prompt_sha256",
    "analyst_prompt_sha256",
)
IDENTIFIER_COLUMNS = ("provider_id", "embedding_model_id", "algorithm_version")
ARTIFACT_ID_COLUMNS = ("template_id", "verifier_prompt_id", "analyst_prompt_id")
VERSION_COLUMNS = ("template_version", "verifier_prompt_version", "analyst_prompt_version")


def _review_checks() -> list[sa.CheckConstraint]:
    checks = [
        sa.CheckConstraint(
            "idempotency_key ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'",
            name=op.f("ck_reviews_idempotency_key"),
        )
    ]
    checks += [
        sa.CheckConstraint(f"{c} ~ {SHA256}", name=op.f(f"ck_reviews_{c}")) for c in HEX_COLUMNS
    ]
    checks += [
        sa.CheckConstraint(f"{c} ~ {IDENTIFIER}", name=op.f(f"ck_reviews_{c}"))
        for c in IDENTIFIER_COLUMNS
    ]
    checks += [
        sa.CheckConstraint("dims BETWEEN 1 AND 4096", name=op.f("ck_reviews_dims")),
        sa.CheckConstraint("normalization = 'l2'", name=op.f("ck_reviews_normalization")),
        sa.CheckConstraint(
            "char_length(retrieval_config_version) BETWEEN 1 AND 64",
            name=op.f("ck_reviews_retrieval_config_version"),
        ),
        sa.CheckConstraint("exclusion_count >= 0", name=op.f("ck_reviews_exclusion_count")),
        sa.CheckConstraint(
            "exclusions_truncated = (exclusion_count > 100)",
            name=op.f("ck_reviews_exclusions_truncated"),
        ),
    ]
    checks += [
        sa.CheckConstraint(f"{c} ~ {ARTIFACT_ID}", name=op.f(f"ck_reviews_{c}"))
        for c in ARTIFACT_ID_COLUMNS
    ]
    checks += [
        sa.CheckConstraint(f"{c} BETWEEN 1 AND 999", name=op.f(f"ck_reviews_{c}"))
        for c in VERSION_COLUMNS
    ]
    checks += [
        sa.CheckConstraint(
            "verifier_prompt_id <> analyst_prompt_id", name=op.f("ck_reviews_distinct_prompts")
        ),
        sa.CheckConstraint(
            "model_id ~ '^[a-z0-9][a-z0-9.-]{0,63}$'", name=op.f("ck_reviews_model_id")
        ),
        sa.CheckConstraint(
            "max_output_tokens BETWEEN 1 AND 8192", name=op.f("ck_reviews_max_output_tokens")
        ),
        sa.CheckConstraint(
            "timeout_ms BETWEEN 1000 AND 120000", name=op.f("ck_reviews_timeout_ms")
        ),
        sa.CheckConstraint("retrieval_k BETWEEN 1 AND 20", name=op.f("ck_reviews_retrieval_k")),
    ]
    return checks


def upgrade() -> None:
    op.create_table(
        "reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("vendor_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_sha256", sa.String(length=64), nullable=False),
        sa.Column("configuration_sha256", sa.String(length=64), nullable=False),
        sa.Column("snapshot_sha256", sa.String(length=64), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider_id", sa.String(length=64), nullable=False),
        sa.Column("embedding_model_id", sa.String(length=64), nullable=False),
        sa.Column("algorithm_version", sa.String(length=64), nullable=False),
        sa.Column("dims", sa.Integer(), nullable=False),
        sa.Column("normalization", sa.String(length=16), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("retrieval_config_version", sa.String(length=64), nullable=False),
        sa.Column("retrieval_config_sha256", sa.String(length=64), nullable=False),
        sa.Column("exclusion_count", sa.Integer(), nullable=False),
        sa.Column("exclusions_truncated", sa.Boolean(), nullable=False),
        sa.Column("template_id", sa.String(length=32), nullable=False),
        sa.Column("template_version", sa.Integer(), nullable=False),
        sa.Column("template_sha256", sa.String(length=64), nullable=False),
        sa.Column("verifier_prompt_id", sa.String(length=32), nullable=False),
        sa.Column("verifier_prompt_version", sa.Integer(), nullable=False),
        sa.Column("verifier_prompt_sha256", sa.String(length=64), nullable=False),
        sa.Column("analyst_prompt_id", sa.String(length=32), nullable=False),
        sa.Column("analyst_prompt_version", sa.Integer(), nullable=False),
        sa.Column("analyst_prompt_sha256", sa.String(length=64), nullable=False),
        sa.Column("model_id", sa.String(length=64), nullable=False),
        sa.Column("max_output_tokens", sa.Integer(), nullable=False),
        sa.Column("timeout_ms", sa.Integer(), nullable=False),
        sa.Column("retrieval_k", sa.Integer(), nullable=False),
        sa.Column("run_review_job_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        *_review_checks(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_reviews_tenant_id_tenants")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "vendor_id"],
            ["vendors.tenant_id", "vendors.id"],
            name=op.f("fk_reviews_tenant_id_vendor_id_vendors"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_review_job_id"],
            ["jobs.tenant_id", "jobs.id"],
            name=op.f("fk_reviews_tenant_id_run_review_job_id_jobs"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reviews")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_reviews_tenant_id_id")),
        sa.UniqueConstraint(
            "tenant_id", "idempotency_key", name=op.f("uq_reviews_tenant_id_idempotency_key")
        ),
        sa.UniqueConstraint(
            "tenant_id", "run_review_job_id", name=op.f("uq_reviews_tenant_id_run_review_job_id")
        ),
    )
    op.create_table(
        "review_bindings",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("review_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.SmallInteger(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("index_id", sa.Uuid(), nullable=False),
        sa.Column("chunker_version", sa.String(length=32), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("manifest_sha256", sa.String(length=64), nullable=False),
        sa.Column("vector_manifest_sha256", sa.String(length=64), nullable=False),
        sa.CheckConstraint("ordinal BETWEEN 0 AND 99", name=op.f("ck_review_bindings_ordinal")),
        sa.CheckConstraint(
            f"chunker_version ~ {CHUNKER_VERSION}", name=op.f("ck_review_bindings_chunker_version")
        ),
        sa.CheckConstraint(
            "chunk_count BETWEEN 1 AND 4096", name=op.f("ck_review_bindings_chunk_count")
        ),
        sa.CheckConstraint(
            f"manifest_sha256 ~ {SHA256}", name=op.f("ck_review_bindings_manifest_sha256")
        ),
        sa.CheckConstraint(
            f"vector_manifest_sha256 ~ {SHA256}",
            name=op.f("ck_review_bindings_vector_manifest_sha256"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "review_id"],
            ["reviews.tenant_id", "reviews.id"],
            name="fk_review_bindings_review",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id", "revision_id"],
            [
                "document_revisions.tenant_id",
                "document_revisions.document_id",
                "document_revisions.id",
            ],
            name="fk_review_bindings_revision",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "index_id"],
            ["embedding_indexes.tenant_id", "embedding_indexes.id"],
            name="fk_review_bindings_index",
        ),
        sa.PrimaryKeyConstraint("review_id", "revision_id", name=op.f("pk_review_bindings")),
        sa.UniqueConstraint(
            "review_id", "ordinal", name=op.f("uq_review_bindings_review_id_ordinal")
        ),
        sa.UniqueConstraint(
            "review_id", "document_id", name=op.f("uq_review_bindings_review_id_document_id")
        ),
    )
    op.create_table(
        "review_excluded_revisions",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("review_id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "review_id"],
            ["reviews.tenant_id", "reviews.id"],
            name="fk_review_excluded_revisions_review",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "revision_id"],
            ["document_revisions.tenant_id", "document_revisions.id"],
            name="fk_review_excluded_revisions_revision",
        ),
        sa.PrimaryKeyConstraint(
            "review_id", "revision_id", name=op.f("pk_review_excluded_revisions")
        ),
    )


def downgrade() -> None:
    op.drop_table("review_excluded_revisions")
    op.drop_table("review_bindings")
    op.drop_table("reviews")
