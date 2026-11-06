"""Review outputs and the review-and-job unique constraint.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-06

Written to match ``evidenceguard_persistence.models`` (M5g, ADR-0025); the integration tests run
``alembic check`` against PostgreSQL to detect drift. The constraint text is spelled out here
rather than imported, so this revision stays fixed if the application constants change later.

Upgrade first adds the unique constraint ``uq_reviews_tenant_id_id_run_review_job_id`` on
``reviews (tenant_id, id, run_review_job_id)`` (no existing column, constraint or row changes),
then creates ``review_outputs`` with its 17 named checks, primary key, ``(tenant_id, job_id)``
unique and three composite foreign keys, the last of which references that new unique. Every
foreign key uses the default ``MATCH SIMPLE`` and ``NO ACTION`` (no cascades). Downgrade drops
exactly ``review_outputs`` (and with it its constraints), then the new ``reviews`` unique. Every
statement is plain DDL, so offline (``--sql``) rendering needs no database.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SHA256 = "'^[0-9a-f]{64}$'"
REVIEW_JOB_UNIQUE = "uq_reviews_tenant_id_id_run_review_job_id"
REVIEW_OUTPUT_CHECKS: tuple[tuple[str, str], ...] = (
    ("schema_id", "schema_id = 'evidenceguard.review-report-content.v1'"),
    ("renderer_id", "renderer_id = 'evidenceguard.review-report-markdown.v1'"),
    ("mode", "mode = 'contract'"),
    ("wrapper_ascii", "octet_length(wrapper_canonical) = char_length(wrapper_canonical)"),
    ("wrapper_printable", "wrapper_canonical !~ '[^ -~]'"),
    ("wrapper_size", "octet_length(wrapper_canonical) BETWEEN 1 AND 16777216"),
    ("wrapper_sha256", f"wrapper_sha256 ~ {SHA256}"),
    ("legacy_sha256", f"legacy_sha256 ~ {SHA256}"),
    ("review_request_sha256", f"review_request_sha256 ~ {SHA256}"),
    ("snapshot_sha256", f"snapshot_sha256 ~ {SHA256}"),
    ("configuration_sha256", f"configuration_sha256 ~ {SHA256}"),
    ("markdown_sha256", f"markdown_sha256 ~ {SHA256}"),
    ("question_count", "question_count BETWEEN 1 AND 100"),
    ("finding_count", "finding_count BETWEEN 0 AND 200"),
    ("unresolved_count", "unresolved_count BETWEEN 0 AND question_count"),
    ("markdown_bytes", "markdown_bytes BETWEEN 1 AND 33554432"),
    ("job_attempt", "job_attempt BETWEEN 1 AND 10"),
)


def upgrade() -> None:
    op.create_unique_constraint(
        REVIEW_JOB_UNIQUE, "reviews", ["tenant_id", "id", "run_review_job_id"]
    )
    op.create_table(
        "review_outputs",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("review_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("schema_id", sa.String(length=64), nullable=False),
        sa.Column("renderer_id", sa.String(length=64), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("wrapper_canonical", sa.Text(), nullable=False),
        sa.Column("wrapper_sha256", sa.String(length=64), nullable=False),
        sa.Column("legacy_sha256", sa.String(length=64), nullable=False),
        sa.Column("review_request_sha256", sa.String(length=64), nullable=False),
        sa.Column("snapshot_sha256", sa.String(length=64), nullable=False),
        sa.Column("configuration_sha256", sa.String(length=64), nullable=False),
        sa.Column("question_count", sa.SmallInteger(), nullable=False),
        sa.Column("finding_count", sa.SmallInteger(), nullable=False),
        sa.Column("unresolved_count", sa.SmallInteger(), nullable=False),
        sa.Column("markdown_sha256", sa.String(length=64), nullable=False),
        sa.Column("markdown_bytes", sa.Integer(), nullable=False),
        sa.Column("job_attempt", sa.SmallInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        *(
            sa.CheckConstraint(check, name=op.f(f"ck_review_outputs_{name}"))
            for name, check in REVIEW_OUTPUT_CHECKS
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "review_id"],
            ["reviews.tenant_id", "reviews.id"],
            name="fk_review_outputs_review",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "job_id"], ["jobs.tenant_id", "jobs.id"], name="fk_review_outputs_job"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "review_id", "job_id"],
            ["reviews.tenant_id", "reviews.id", "reviews.run_review_job_id"],
            name="fk_review_outputs_review_job",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "review_id", name=op.f("pk_review_outputs")),
        sa.UniqueConstraint("tenant_id", "job_id", name=op.f("uq_review_outputs_tenant_id_job_id")),
    )


def downgrade() -> None:
    op.drop_table("review_outputs")
    op.drop_constraint(REVIEW_JOB_UNIQUE, "reviews", type_="unique")
