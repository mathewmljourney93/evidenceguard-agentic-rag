"""Reports, their revision, decision and finalization history, and the audit log.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-20

Written to match ``evidenceguard_persistence.models`` (M6, ADR-0028); the integration tests run
``alembic check`` against PostgreSQL to detect drift. The constraint text is spelled out here
rather than imported, so this revision stays fixed if the application constants change later.

Upgrade adds the unique ``uq_review_outputs_tenant_id_review_id_wrapper_sha256`` on
``review_outputs (tenant_id, review_id, wrapper_sha256)`` (no existing column, constraint or row
changes), then creates ``reports``, ``report_revisions``, ``report_decisions``,
``report_finalizations`` and ``audit_events`` with their named checks, keys and composite foreign
keys (all ``NO ACTION``, no cascades). It then creates the trigger function
``eg_reject_append_only_change()`` (fixed ``search_path``, schema-qualified, ``SECURITY
INVOKER``) and triggers that reject UPDATE, DELETE and TRUNCATE on the four history tables and
DELETE and TRUNCATE on ``reports`` with SQLSTATE 23001 (``restrict_violation``). Triggers are not
visible to autogenerate, so ``alembic check`` does not compare them.

Downgrade drops the triggers and the function, then the tables in reverse foreign-key order,
then the new ``review_outputs`` unique. It deletes every report and audit row; once reports exist,
fix forward with a new migration instead. Every statement is plain DDL, so offline (``--sql``)
rendering needs no database.
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SHA256 = "'^[0-9a-f]{64}$'"
OUTPUT_UNIQUE = "uq_review_outputs_tenant_id_review_id_wrapper_sha256"
FUNCTION = "eg_reject_append_only_change"
HISTORY_TABLES = ("report_revisions", "report_decisions", "report_finalizations", "audit_events")

REPORT_CHECKS: tuple[tuple[str, str], ...] = (
    ("id_is_review", "id = review_id"),
    ("base_schema_id", "base_schema_id = 'evidenceguard.review-report-content.v1'"),
    ("base_renderer_id", "base_renderer_id = 'evidenceguard.review-report-markdown.v1'"),
    ("base_wrapper_sha256", f"base_wrapper_sha256 ~ {SHA256}"),
    ("status", "status IN ('approved', 'changes_requested', 'draft', 'finalized')"),
    ("current_revision_no", "current_revision_no BETWEEN 1 AND 100"),
    ("current_content_sha256", f"current_content_sha256 ~ {SHA256}"),
)
REPORT_REVISION_CHECKS: tuple[tuple[str, str], ...] = (
    ("schema_id", "schema_id = 'evidenceguard.review-report-revision.v1'"),
    ("revision_no", "revision_no BETWEEN 1 AND 100"),
    ("origin", "origin IN ('generated', 'revised')"),
    ("generated_author", "(origin = 'generated') = (created_by IS NULL)"),
    ("generated_first", "(origin = 'generated') = (revision_no = 1)"),
    ("content_ascii", "octet_length(content_canonical) = char_length(content_canonical)"),
    ("content_printable", "content_canonical !~ '[^ -~]'"),
    ("content_size", "octet_length(content_canonical) BETWEEN 1 AND 1048576"),
    ("content_sha256", f"content_sha256 ~ {SHA256}"),
    ("base_wrapper_sha256", f"base_wrapper_sha256 ~ {SHA256}"),
    ("reason", "reason IS NULL OR char_length(reason) BETWEEN 1 AND 500"),
)
REPORT_DECISION_CHECKS: tuple[tuple[str, str], ...] = (
    ("decision_no", "decision_no BETWEEN 1 AND 1000"),
    ("revision_no", "revision_no BETWEEN 1 AND 100"),
    ("content_sha256", f"content_sha256 ~ {SHA256}"),
    ("decision", "decision IN ('approve', 'reject')"),
    ("comment", "comment IS NULL OR char_length(comment) BETWEEN 1 AND 2000"),
    ("reject_comment", "decision <> 'reject' OR (comment IS NOT NULL AND btrim(comment) <> '')"),
)
REPORT_FINALIZATION_CHECKS: tuple[tuple[str, str], ...] = (
    ("decision_no", "decision_no BETWEEN 1 AND 1000"),
    ("revision_no", "revision_no BETWEEN 1 AND 100"),
    ("content_sha256", f"content_sha256 ~ {SHA256}"),
)
AUDIT_EVENT_CHECKS: tuple[tuple[str, str], ...] = (
    ("action", "action IN ('approve', 'export', 'finalize', 'reject', 'revise')"),
    ("revision_no", "revision_no BETWEEN 1 AND 100"),
    ("content_sha256", f"content_sha256 ~ {SHA256}"),
    (
        "export_pairing",
        "(action = 'export') = (export_format IS NOT NULL AND export_sha256 IS NOT NULL)",
    ),
    ("export_format", "export_format IS NULL OR export_format IN ('json', 'md')"),
    ("export_sha256", f"export_sha256 IS NULL OR export_sha256 ~ {SHA256}"),
)

CREATE_FUNCTION = f"""\
CREATE FUNCTION public.{FUNCTION}() RETURNS trigger
    LANGUAGE plpgsql
    SECURITY INVOKER
    SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
    RAISE EXCEPTION USING
        MESSAGE = 'rows of ' || TG_TABLE_NAME || ' cannot be changed or removed',
        ERRCODE = 'restrict_violation';
END;
$$"""


def _triggers() -> list[tuple[str, str, str]]:
    """(trigger name, table, timing and level) for every trigger 0009 creates."""
    triggers: list[tuple[str, str, str]] = []
    for table in HISTORY_TABLES:
        triggers.append(
            (f"eg_{table}_append_only", table, "BEFORE UPDATE OR DELETE ON {} FOR EACH ROW")
        )
        triggers.append(
            (f"eg_{table}_no_truncate", table, "BEFORE TRUNCATE ON {} FOR EACH STATEMENT")
        )
    triggers.append(("eg_reports_no_delete", "reports", "BEFORE DELETE ON {} FOR EACH ROW"))
    triggers.append(
        ("eg_reports_no_truncate", "reports", "BEFORE TRUNCATE ON {} FOR EACH STATEMENT")
    )
    return triggers


def _timestamp(name: str) -> sa.Column[Any]:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        server_default=sa.text("clock_timestamp()"),
        nullable=False,
    )


def _checks(table: str, checks: tuple[tuple[str, str], ...]) -> list[sa.CheckConstraint]:
    return [sa.CheckConstraint(check, name=op.f(f"ck_{table}_{name}")) for name, check in checks]


def upgrade() -> None:
    op.create_unique_constraint(
        OUTPUT_UNIQUE, "review_outputs", ["tenant_id", "review_id", "wrapper_sha256"]
    )
    op.create_table(
        "reports",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("review_id", sa.Uuid(), nullable=False),
        sa.Column("base_schema_id", sa.String(length=64), nullable=False),
        sa.Column("base_renderer_id", sa.String(length=64), nullable=False),
        sa.Column("base_wrapper_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_revision_no", sa.SmallInteger(), nullable=False),
        sa.Column("current_content_sha256", sa.String(length=64), nullable=False),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        *_checks("reports", REPORT_CHECKS),
        sa.ForeignKeyConstraint(
            ["tenant_id", "review_id", "base_wrapper_sha256"],
            [
                "review_outputs.tenant_id",
                "review_outputs.review_id",
                "review_outputs.wrapper_sha256",
            ],
            name="fk_reports_review_output",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name=op.f("pk_reports")),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            "base_wrapper_sha256",
            name=op.f("uq_reports_tenant_id_id_base_wrapper_sha256"),
        ),
    )
    op.create_table(
        "report_revisions",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("revision_no", sa.SmallInteger(), nullable=False),
        sa.Column("schema_id", sa.String(length=64), nullable=False),
        sa.Column("base_wrapper_sha256", sa.String(length=64), nullable=False),
        sa.Column("content_canonical", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        _timestamp("created_at"),
        *_checks("report_revisions", REPORT_REVISION_CHECKS),
        sa.ForeignKeyConstraint(
            ["tenant_id", "report_id", "base_wrapper_sha256"],
            ["reports.tenant_id", "reports.id", "reports.base_wrapper_sha256"],
            name="fk_report_revisions_report",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id", "report_id", "revision_no", name=op.f("pk_report_revisions")
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "report_id",
            "revision_no",
            "content_sha256",
            name="uq_report_revisions_revision_hash",
        ),
    )
    op.create_table(
        "report_decisions",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("decision_no", sa.SmallInteger(), nullable=False),
        sa.Column("revision_no", sa.SmallInteger(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("decided_by", sa.Uuid(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        _timestamp("decided_at"),
        *_checks("report_decisions", REPORT_DECISION_CHECKS),
        sa.ForeignKeyConstraint(
            ["tenant_id", "report_id", "revision_no", "content_sha256"],
            [
                "report_revisions.tenant_id",
                "report_revisions.report_id",
                "report_revisions.revision_no",
                "report_revisions.content_sha256",
            ],
            name="fk_report_decisions_revision",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id", "report_id", "decision_no", name=op.f("pk_report_decisions")
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "report_id",
            "decision_no",
            "revision_no",
            "content_sha256",
            name="uq_report_decisions_decision_hash",
        ),
    )
    op.create_table(
        "report_finalizations",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("revision_no", sa.SmallInteger(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("decision_no", sa.SmallInteger(), nullable=False),
        sa.Column("finalized_by", sa.Uuid(), nullable=False),
        _timestamp("finalized_at"),
        *_checks("report_finalizations", REPORT_FINALIZATION_CHECKS),
        sa.ForeignKeyConstraint(
            ["tenant_id", "report_id", "decision_no", "revision_no", "content_sha256"],
            [
                "report_decisions.tenant_id",
                "report_decisions.report_id",
                "report_decisions.decision_no",
                "report_decisions.revision_no",
                "report_decisions.content_sha256",
            ],
            name="fk_report_finalizations_decision",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "report_id", name=op.f("pk_report_finalizations")),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("revision_no", sa.SmallInteger(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("export_format", sa.String(length=8), nullable=True),
        sa.Column("export_sha256", sa.String(length=64), nullable=True),
        _timestamp("occurred_at"),
        *_checks("audit_events", AUDIT_EVENT_CHECKS),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_audit_events_tenant_id_tenants")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "report_id", "revision_no", "content_sha256"],
            [
                "report_revisions.tenant_id",
                "report_revisions.report_id",
                "report_revisions.revision_no",
                "report_revisions.content_sha256",
            ],
            name="fk_audit_events_revision",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index(
        "ix_audit_events_report_order", "audit_events", ["tenant_id", "report_id", "id"]
    )
    op.execute(CREATE_FUNCTION)
    for name, table, timing in _triggers():
        op.execute(
            f"CREATE TRIGGER {name} {timing.format(f'public.{table}')} "
            f"EXECUTE FUNCTION public.{FUNCTION}()"
        )


def downgrade() -> None:
    for name, table, _timing in reversed(_triggers()):
        op.execute(f"DROP TRIGGER {name} ON public.{table}")
    op.execute(f"DROP FUNCTION public.{FUNCTION}()")
    op.drop_index("ix_audit_events_report_order", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("report_finalizations")
    op.drop_table("report_decisions")
    op.drop_table("report_revisions")
    op.drop_table("reports")
    op.drop_constraint(OUTPUT_UNIQUE, "review_outputs", type_="unique")
