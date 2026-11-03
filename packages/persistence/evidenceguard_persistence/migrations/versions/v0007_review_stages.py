"""Review stages: planned questions, question evidence, call reservations and stage results.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-23

Written to match ``evidenceguard_persistence.models`` (M5e, ADR-0023); the integration tests run
``alembic check`` against PostgreSQL to detect drift. The constraint text is spelled out here
rather than imported, so this revision stays fixed if the application constants change later.

Upgrade creates ``review_plan_questions``, ``review_question_evidence``, ``review_stage_calls``
(with the partial unique index allowing one repair per stage) and ``review_stage_results``. Every
foreign key uses the default ``MATCH SIMPLE`` and ``NO ACTION`` (no cascades); no table stores a
report output (E7: M5f/M5g). No check compares timestamps (V12). Downgrade drops exactly these four
tables in reverse dependency order. Every statement is plain DDL, so offline (``--sql``)
rendering needs no database.
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PLAN_QUESTION_CHECKS: tuple[tuple[str, str], ...] = (
    ("question_id", "question_id ~ '^[A-Z][A-Z0-9]{1,9}-[0-9]{2,3}$'"),
    ("position", "position BETWEEN 0 AND 99"),
    ("question_sha256", "question_sha256 ~ '^[0-9a-f]{64}$'"),
    ("job_attempt", "job_attempt BETWEEN 1 AND 10"),
)
QUESTION_EVIDENCE_CHECKS: tuple[tuple[str, str], ...] = (
    ("question_sha256", "question_sha256 ~ '^[0-9a-f]{64}$'"),
    ("snapshot_sha256", "snapshot_sha256 ~ '^[0-9a-f]{64}$'"),
    ("evidence_sha256", "evidence_sha256 ~ '^[0-9a-f]{64}$'"),
    ("item_count", "item_count BETWEEN 0 AND 20"),
    ("evidence_ascii", "octet_length(evidence_canonical) = char_length(evidence_canonical)"),
    ("evidence_size", "octet_length(evidence_canonical) BETWEEN 2 AND 4194304"),
    ("job_attempt", "job_attempt BETWEEN 1 AND 10"),
)
STAGE_CALL_CHECKS: tuple[tuple[str, str], ...] = (
    ("stage", "stage IN ('analysis', 'verification')"),
    ("call_kind", "call_kind IN ('initial', 'repair', 'retry')"),
    ("request_basis", "request_basis IN ('original', 'repaired')"),
    ("state", "state IN ('completed', 'started')"),
    (
        "outcome",
        (
            "outcome IS NULL OR outcome IN ('completed', 'invalid_output', 'max_tokens', "
            "'model_mismatch', 'provider_failed', 'refusal', 'timeout', 'unexpected_stop')"
        ),
    ),
    (
        "rejection_reason",
        (
            "rejection_reason IS NULL OR rejection_reason IN ('chunk_not_retrieved', "
            "'citation_not_shared', 'citation_not_validated', 'claim_uncited', "
            "'finding_status_unsupported', 'finding_text_blank', 'foreign_question', "
            "'mixed_verdicts', 'quote_blank', 'quote_not_exact', 'quote_not_found', "
            "'quote_too_long', 'rationale_blank', 'verdict_unsupported')"
        ),
    ),
    ("question_id", "question_id ~ '^[A-Z][A-Z0-9]{1,9}-[0-9]{2,3}$'"),
    ("model_requested", "model_requested ~ '^[a-z0-9][a-z0-9.-]{0,63}$'"),
    ("model_used", "model_used IS NULL OR model_used ~ '^[a-z0-9][a-z0-9.-]{0,63}$'"),
    ("request_sha256", "request_sha256 ~ '^[0-9a-f]{64}$'"),
    ("prompt_sha256", "prompt_sha256 ~ '^[0-9a-f]{64}$'"),
    ("evidence_sha256", "evidence_sha256 IS NULL OR evidence_sha256 ~ '^[0-9a-f]{64}$'"),
    ("dependency_sha256", "dependency_sha256 IS NULL OR dependency_sha256 ~ '^[0-9a-f]{64}$'"),
    ("sequence", "sequence BETWEEN 1 AND 3"),
    ("max_output_tokens", "max_output_tokens BETWEEN 1 AND 8192"),
    ("timeout_ms", "timeout_ms BETWEEN 1000 AND 120000"),
    ("job_attempt", "job_attempt BETWEEN 1 AND 10"),
    ("input_tokens", "input_tokens BETWEEN 0 AND 10000000"),
    ("output_tokens", "output_tokens BETWEEN 0 AND 10000000"),
    ("latency_ms", "latency_ms BETWEEN 0 AND 86400000"),
    ("rejection_item_index", "rejection_item_index BETWEEN 0 AND 19"),
    ("rejection_citation_index", "rejection_citation_index BETWEEN 0 AND 7"),
    ("rejection_count", "rejection_count BETWEEN 1 AND 80"),
    ("initial_sequence", "(sequence = 1) = (call_kind = 'initial')"),
    ("initial_basis", "call_kind <> 'initial' OR request_basis = 'original'"),
    ("repair_basis", "call_kind <> 'repair' OR request_basis = 'repaired'"),
    (
        "stage_refs",
        (
            "(evidence_sha256 IS NOT NULL) = (stage = 'verification') AND (dependency_sha256 "
            "IS NOT NULL) = (stage = 'analysis')"
        ),
    ),
    (
        "started_shape",
        (
            "state <> 'started' OR (completed_at IS NULL AND outcome IS NULL AND dispatched "
            "IS NULL AND model_used IS NULL AND input_tokens IS NULL AND output_tokens IS "
            "NULL AND latency_ms IS NULL AND rejection_reason IS NULL AND "
            "rejection_item_index IS NULL AND rejection_citation_index IS NULL AND "
            "rejection_count IS NULL)"
        ),
    ),
    (
        "completed_shape",
        (
            "state <> 'completed' OR (completed_at IS NOT NULL AND outcome IS NOT NULL AND "
            "dispatched IS NOT NULL)"
        ),
    ),
    (
        "response_pair",
        (
            "(model_used IS NULL) = (input_tokens IS NULL) AND (model_used IS NULL) = "
            "(output_tokens IS NULL)"
        ),
    ),
    (
        "outcome_shape",
        (
            "outcome IS NULL OR (outcome IN ('completed', 'refusal', 'max_tokens', "
            "'unexpected_stop', 'invalid_output') AND dispatched AND model_used IS NOT NULL "
            "AND model_used = model_requested) OR (outcome = 'model_mismatch' AND dispatched "
            "AND model_used IS NOT NULL AND model_used <> model_requested) OR (outcome = "
            "'timeout' AND dispatched AND model_used IS NULL) OR (outcome = 'provider_failed' "
            "AND model_used IS NULL AND (dispatched OR latency_ms IS NULL))"
        ),
    ),
    (
        "rejection_shape",
        (
            "(rejection_reason IS NULL) = (rejection_count IS NULL) AND (rejection_reason IS "
            "NULL OR outcome = 'completed') AND (rejection_reason IS NOT NULL OR "
            "(rejection_item_index IS NULL AND rejection_citation_index IS NULL))"
        ),
    ),
    (
        "rejection_stage",
        (
            "rejection_reason IS NULL OR (stage = 'verification') = (rejection_reason IN "
            "('chunk_not_retrieved', 'claim_uncited', 'quote_blank', 'quote_not_exact', "
            "'quote_not_found', 'quote_too_long', 'rationale_blank', 'verdict_unsupported'))"
        ),
    ),
)
STAGE_RESULT_CHECKS: tuple[tuple[str, str], ...] = (
    ("stage", "stage IN ('analysis', 'verification')"),
    ("outcome", "outcome IN ('analyzed', 'unresolved', 'verified')"),
    (
        "unresolved_reason",
        (
            "unresolved_reason IS NULL OR unresolved_reason IN ('call_abandoned', "
            "'citation_rejected', 'evidence_too_large', 'invalid_output', 'max_tokens', "
            "'model_mismatch', 'provider_failed', 'refusal', 'repair_request_too_large', "
            "'request_too_large', 'timeout', 'unexpected_stop', 'verification_unresolved')"
        ),
    ),
    ("call_sequence", "call_sequence BETWEEN 1 AND 3"),
    ("request_sha256", "request_sha256 IS NULL OR request_sha256 ~ '^[0-9a-f]{64}$'"),
    ("evidence_sha256", "evidence_sha256 IS NULL OR evidence_sha256 ~ '^[0-9a-f]{64}$'"),
    ("dependency_sha256", "dependency_sha256 IS NULL OR dependency_sha256 ~ '^[0-9a-f]{64}$'"),
    ("content_sha256", "content_sha256 IS NULL OR content_sha256 ~ '^[0-9a-f]{64}$'"),
    ("question_id", "question_id ~ '^[A-Z][A-Z0-9]{1,9}-[0-9]{2,3}$'"),
    ("job_attempt", "job_attempt BETWEEN 1 AND 10"),
    (
        "stage_outcome",
        (
            "(stage = 'verification' AND outcome IN ('verified', 'unresolved')) OR (stage = "
            "'analysis' AND outcome IN ('analyzed', 'unresolved'))"
        ),
    ),
    ("reason_present", "(outcome = 'unresolved') = (unresolved_reason IS NOT NULL)"),
    (
        "content",
        (
            "(outcome <> 'unresolved') = (content_canonical IS NOT NULL) AND "
            "(content_canonical IS NULL) = (content_sha256 IS NULL)"
        ),
    ),
    (
        "call_ref",
        (
            "(call_sequence IS NULL) = (request_sha256 IS NULL) AND (call_sequence IS NULL) = "
            "(outcome = 'unresolved' AND unresolved_reason IN ('request_too_large', "
            "'evidence_too_large', 'verification_unresolved'))"
        ),
    ),
    (
        "evidence_ref",
        (
            "(evidence_sha256 IS NOT NULL) = (stage = 'verification' AND "
            "coalesce(unresolved_reason, '') <> 'evidence_too_large')"
        ),
    ),
    ("dependency_ref", "(dependency_sha256 IS NOT NULL) = (stage = 'analysis')"),
    (
        "stage_reason",
        (
            "(coalesce(unresolved_reason, '') NOT IN ('evidence_too_large') OR stage = "
            "'verification') AND (coalesce(unresolved_reason, '') NOT IN "
            "('verification_unresolved') OR stage = 'analysis')"
        ),
    ),
    (
        "content_ascii",
        (
            "content_canonical IS NULL OR octet_length(content_canonical) = "
            "char_length(content_canonical)"
        ),
    ),
    (
        "content_size",
        (
            "content_canonical IS NULL OR (stage = 'verification' AND "
            "octet_length(content_canonical) <= 2097152) OR (stage = 'analysis' AND "
            "octet_length(content_canonical) <= 4194304)"
        ),
    ),
)


def _checks(table: str, checks: tuple[tuple[str, str], ...]) -> list[sa.CheckConstraint]:
    return [sa.CheckConstraint(check, name=op.f(f"ck_{table}_{name}")) for name, check in checks]


def _timestamp(name: str) -> sa.Column[Any]:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        server_default=sa.text("clock_timestamp()"),
        nullable=False,
    )


PLAN = (
    ["tenant_id", "review_id", "question_id"],
    [
        "review_plan_questions.tenant_id",
        "review_plan_questions.review_id",
        "review_plan_questions.question_id",
    ],
)
EVIDENCE = (
    ["tenant_id", "review_id", "question_id", "evidence_sha256"],
    [
        "review_question_evidence.tenant_id",
        "review_question_evidence.review_id",
        "review_question_evidence.question_id",
        "review_question_evidence.evidence_sha256",
    ],
)


def _job(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["tenant_id", "job_id"], ["jobs.tenant_id", "jobs.id"], name=f"fk_{table}_job"
    )


def upgrade() -> None:
    op.create_table(
        "review_plan_questions",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("review_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.String(length=14), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("question_sha256", sa.String(length=64), nullable=False),
        sa.Column("job_attempt", sa.SmallInteger(), nullable=False),
        _timestamp("created_at"),
        *_checks("review_plan_questions", PLAN_QUESTION_CHECKS),
        sa.ForeignKeyConstraint(
            ["tenant_id", "review_id"],
            ["reviews.tenant_id", "reviews.id"],
            name="fk_review_plan_questions_review",
        ),
        _job("review_plan_questions"),
        sa.PrimaryKeyConstraint(
            "tenant_id", "review_id", "question_id", name=op.f("pk_review_plan_questions")
        ),
        sa.UniqueConstraint(
            "tenant_id", "review_id", "position", name="uq_review_plan_questions_position"
        ),
    )
    op.create_table(
        "review_question_evidence",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("review_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.String(length=14), nullable=False),
        sa.Column("question_sha256", sa.String(length=64), nullable=False),
        sa.Column("snapshot_sha256", sa.String(length=64), nullable=False),
        sa.Column("evidence_sha256", sa.String(length=64), nullable=False),
        sa.Column("evidence_canonical", sa.Text(), nullable=False),
        sa.Column("item_count", sa.SmallInteger(), nullable=False),
        sa.Column("job_attempt", sa.SmallInteger(), nullable=False),
        _timestamp("created_at"),
        *_checks("review_question_evidence", QUESTION_EVIDENCE_CHECKS),
        sa.ForeignKeyConstraint(*PLAN, name="fk_review_question_evidence_plan"),
        _job("review_question_evidence"),
        sa.PrimaryKeyConstraint(
            "tenant_id", "review_id", "question_id", name=op.f("pk_review_question_evidence")
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "review_id",
            "question_id",
            "evidence_sha256",
            name="uq_review_question_evidence_digest",
        ),
    )
    op.create_table(
        "review_stage_calls",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("review_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.String(length=14), nullable=False),
        sa.Column("stage", sa.String(length=16), nullable=False),
        sa.Column("call_kind", sa.String(length=16), nullable=False),
        sa.Column("request_basis", sa.String(length=16), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("sequence", sa.SmallInteger(), nullable=False),
        sa.Column("request_sha256", sa.String(length=64), nullable=False),
        sa.Column("prompt_sha256", sa.String(length=64), nullable=False),
        sa.Column("model_requested", sa.String(length=64), nullable=False),
        sa.Column("max_output_tokens", sa.Integer(), nullable=False),
        sa.Column("timeout_ms", sa.Integer(), nullable=False),
        sa.Column("job_attempt", sa.SmallInteger(), nullable=False),
        _timestamp("started_at"),
        sa.Column("evidence_sha256", sa.String(length=64), nullable=True),
        sa.Column("dependency_sha256", sa.String(length=64), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.String(length=32), nullable=True),
        sa.Column("rejection_reason", sa.String(length=32), nullable=True),
        sa.Column("dispatched", sa.Boolean(), nullable=True),
        sa.Column("model_used", sa.String(length=64), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("rejection_item_index", sa.SmallInteger(), nullable=True),
        sa.Column("rejection_citation_index", sa.SmallInteger(), nullable=True),
        sa.Column("rejection_count", sa.SmallInteger(), nullable=True),
        *_checks("review_stage_calls", STAGE_CALL_CHECKS),
        sa.ForeignKeyConstraint(*PLAN, name="fk_review_stage_calls_plan"),
        sa.ForeignKeyConstraint(*EVIDENCE, name="fk_review_stage_calls_evidence"),
        _job("review_stage_calls"),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "review_id",
            "question_id",
            "stage",
            "sequence",
            name=op.f("pk_review_stage_calls"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "review_id",
            "question_id",
            "stage",
            "sequence",
            "request_sha256",
            name="uq_review_stage_calls_request",
        ),
    )
    op.create_index(
        "uq_review_stage_calls_one_repair",
        "review_stage_calls",
        ["tenant_id", "review_id", "question_id", "stage"],
        unique=True,
        postgresql_where=sa.text("call_kind = 'repair'"),
    )
    op.create_table(
        "review_stage_results",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("review_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.String(length=14), nullable=False),
        sa.Column("stage", sa.String(length=16), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("job_attempt", sa.SmallInteger(), nullable=False),
        _timestamp("committed_at"),
        sa.Column("unresolved_reason", sa.String(length=32), nullable=True),
        sa.Column("call_sequence", sa.SmallInteger(), nullable=True),
        sa.Column("request_sha256", sa.String(length=64), nullable=True),
        sa.Column("evidence_sha256", sa.String(length=64), nullable=True),
        sa.Column("dependency_sha256", sa.String(length=64), nullable=True),
        sa.Column("content_sha256", sa.String(length=64), nullable=True),
        sa.Column("content_canonical", sa.Text(), nullable=True),
        *_checks("review_stage_results", STAGE_RESULT_CHECKS),
        sa.ForeignKeyConstraint(*PLAN, name="fk_review_stage_results_plan"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "review_id", "question_id", "stage", "call_sequence", "request_sha256"],
            [
                "review_stage_calls.tenant_id",
                "review_stage_calls.review_id",
                "review_stage_calls.question_id",
                "review_stage_calls.stage",
                "review_stage_calls.sequence",
                "review_stage_calls.request_sha256",
            ],
            name="fk_review_stage_results_call",
        ),
        sa.ForeignKeyConstraint(*EVIDENCE, name="fk_review_stage_results_evidence"),
        _job("review_stage_results"),
        sa.PrimaryKeyConstraint(
            "tenant_id", "review_id", "question_id", "stage", name=op.f("pk_review_stage_results")
        ),
    )


def downgrade() -> None:
    op.drop_table("review_stage_results")
    op.drop_index("uq_review_stage_calls_one_repair", table_name="review_stage_calls")
    op.drop_table("review_stage_calls")
    op.drop_table("review_question_evidence")
    op.drop_table("review_plan_questions")
