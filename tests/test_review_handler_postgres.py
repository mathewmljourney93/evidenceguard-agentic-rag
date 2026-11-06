"""PostgreSQL integration tests for the M5g ``run_review`` handler (ADR-0025).

Skipped without ``EG_TEST_DATABASE_URL`` (required in CI). Revisions are ingested and indexed
through the real worker; the review is created through M5d with the pinned artifacts; the handler
runs through ``run_worker`` with a **test** registry, or on a real ``JobContext`` over the M3
fence when an interruption must be placed exactly. Model results are scripted (no network).
"""

import hashlib
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, func, select, text
from sqlalchemy.engine import URL

from evidenceguard_agents.report import render_report_markdown
from evidenceguard_agents.scripted import Timeout
from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_domain.review_outputs import ReviewStatus
from evidenceguard_persistence import jobs as job_store
from evidenceguard_persistence.models import (
    ReviewOutputRow,
    ReviewQuestionEvidence,
    ReviewStageCall,
    ReviewStageResult,
)
from evidenceguard_persistence.review_outputs import load_review_status
from evidenceguard_worker import review as review_module
from evidenceguard_worker.context import AttemptState, JobContext
from evidenceguard_worker.handlers import production_registry
from evidenceguard_worker.review import load_trusted_review_output

if TYPE_CHECKING:
    import review_postgres_world as pw
else:
    from tests import review_postgres_world as pw

pytestmark = pytest.mark.integration


@pytest.fixture
def world(migrated: Engine, test_database_url: URL) -> Iterator[pw.ReviewWorld]:
    built = pw.review_world(migrated, test_database_url)
    try:
        yield built
    finally:
        built.engine.dispose()


def _count(engine: Engine, table: Any) -> int:
    with engine.connect() as connection:
        found: int = connection.execute(select(func.count()).select_from(table)).scalar_one()
    return found


def test_a_review_runs_end_to_end_and_commits_its_output_with_success(
    world: pw.ReviewWorld,
) -> None:
    model = pw.provider(world.chunk_id)
    assert world.run(model).exit_code == 0
    assert world.job().status == "succeeded"
    assert _count(world.engine, ReviewOutputRow) == 1
    assert _count(world.engine, ReviewStageResult) == 16 and len(model.history) == 16
    approver = ActorContext(tenant_id=world.actor.tenant_id, actor_id=uuid4(), role=Role.APPROVER)
    assert load_review_status(world.factory, approver, world.review_id) is ReviewStatus.COMPLETED
    trusted = load_trusted_review_output(world.factory, approver, world.review_id)
    assert trusted.markdown == render_report_markdown(trusted.stored.output.content)
    digest = hashlib.sha256(trusted.markdown.encode("utf-8")).hexdigest()
    assert digest == trusted.stored.output.markdown_sha256
    assert "run_review" not in production_registry().kinds


def test_an_uncommitted_finish_is_retried_and_reuses_every_stage_with_zero_calls(
    world: pw.ReviewWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    from evidenceguard_persistence.review_outputs import ReviewOutputDatabaseError

    real = getattr(review_module, "write_review_output")  # noqa: B009 - patched below

    def failing(fence: Any, output: Any) -> Any:
        raise ReviewOutputDatabaseError()

    monkeypatch.setattr(review_module, "write_review_output", failing)
    assert world.run(pw.provider(world.chunk_id)).exit_code == 0
    job = world.job()
    assert job.status == "queued" and job.last_error == "retryable_failure"
    assert _count(world.engine, ReviewOutputRow) == 0
    assert _count(world.engine, ReviewStageResult) == 16  # committed stages retained
    monkeypatch.setattr(review_module, "write_review_output", real)
    with world.engine.begin() as connection:  # make the backoff due without waiting
        connection.execute(text("UPDATE jobs SET run_after = clock_timestamp()"))
    again = pw.provider(world.chunk_id)
    assert world.run(again).exit_code == 0
    assert len(again.history) == 0 and world.job().status == "succeeded"
    with world.engine.connect() as connection:
        attempt = connection.execute(select(ReviewOutputRow.job_attempt)).scalar_one()
    assert attempt == 2


def test_a_reservation_abandoned_before_dispatch_is_retried_on_the_next_attempt(
    world: pw.ReviewWorld,
) -> None:
    claimed = job_store.claim(world.factory, "w-m5g", kinds={"run_review"})
    assert claimed is not None and claimed.id == world.job_id
    state = AttemptState(deadline=float("inf"), lease_seconds=60.0, clock=lambda: 0.0)
    store = job_store

    def fence(token: Any) -> Any:
        return store.fenced_transaction(world.factory, token)

    ctx = JobContext(claimed, state, fence)
    model = pw.provider(world.chunk_id)

    class Cancelling:
        provider_id = "scripted-fake"

        def generate(self, request: Any) -> Any:
            raise AssertionError("dispatched after cancellation")

    real_reserve = getattr(review_module, "reserve_call")  # noqa: B009 - patched below

    def reserve_then_cancel(*args: Any, **kwargs: Any) -> Any:
        reserved = real_reserve(*args, **kwargs)
        state.request_cancel()  # latched after the reservation, before dispatch
        return reserved

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(review_module, "reserve_call", reserve_then_cancel)
        handler = review_module.make_run_review_handler(Cancelling(), session_factory=world.factory)
        with pytest.raises(Exception) as raised:
            handler(ctx)
    assert type(raised.value).__name__ == "JobCancelledError"
    with world.engine.connect() as connection:
        rows = connection.execute(select(ReviewStageCall.__table__)).all()
    assert [(r.sequence, r.state, r.job_attempt) for r in rows] == [(1, "started", 1)]
    job_store.fail_retryable(world.factory, ctx.token)
    with world.engine.begin() as connection:
        connection.execute(text("UPDATE jobs SET run_after = clock_timestamp()"))
    assert world.run(model).exit_code == 0
    assert world.job().status == "succeeded"
    with world.engine.connect() as connection:
        first_question = connection.execute(
            select(ReviewStageCall.call_kind, ReviewStageCall.request_sha256)
            .where(ReviewStageCall.stage == "verification")
            .order_by(ReviewStageCall.question_id, ReviewStageCall.sequence)
        ).all()
    retried = [row for row in first_question if row.call_kind == "retry"]
    assert retried and retried[0].request_sha256 == first_question[0].request_sha256


def test_a_replacement_activated_after_creation_is_outside_the_snapshot(
    migrated: Engine, test_database_url: URL
) -> None:
    world = pw.review_world(migrated, test_database_url, slug="m5g-replacement")
    try:
        replacement = pw.ready_revision(
            world.factory,
            world.actor,
            world.vendor_id,
            body="Customer data is encrypted at rest with a replacement cipher.\n",
        )
        assert world.run(pw.provider(world.chunk_id)).exit_code == 0
        assert world.job().status == "succeeded"
        with world.engine.connect() as connection:
            canonicals = connection.execute(
                select(ReviewQuestionEvidence.evidence_canonical)
            ).scalars()
            stored = "".join(canonicals)
        assert str(world.revision_id) in stored  # the superseded bound revision still verifies
        assert str(replacement) not in stored  # never substituted, never recaptured
    finally:
        world.engine.dispose()


def test_a_timeout_exhausted_stage_is_u1_and_the_review_still_completes(
    world: pw.ReviewWorld,
) -> None:
    question = pw.question_ids()[0]
    model = pw.provider(world.chunk_id, {("verifier", question): (Timeout(), Timeout(), Timeout())})
    assert world.run(model).exit_code == 0
    with world.engine.connect() as connection:
        stage = connection.execute(
            select(ReviewStageResult.unresolved_reason).where(
                ReviewStageResult.question_id == question,
                ReviewStageResult.stage == "verification",
            )
        ).scalar_one()
    assert stage == "timeout" and world.job().status == "succeeded"


def test_the_production_registry_never_claims_the_review_job(world: pw.ReviewWorld) -> None:
    assert pw.work(world.factory, production_registry()).exit_code == 0
    assert world.job().status == "queued" and world.job().attempt == 0


def test_migration_0008_downgrades_upgrades_and_matches_the_models(
    migrated: Engine, config: Config
) -> None:
    def tables() -> set[str]:
        with migrated.connect() as connection:
            return set(
                connection.execute(
                    text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                ).scalars()
            )

    def constraints() -> set[str]:
        with migrated.connect() as connection:
            return set(connection.execute(text("SELECT conname FROM pg_constraint")).scalars())

    assert "review_outputs" in tables()
    assert "uq_reviews_tenant_id_id_run_review_job_id" in constraints()
    try:
        command.downgrade(config, "0007")
        assert "review_outputs" not in tables() and "review_stage_results" in tables()
        assert "uq_reviews_tenant_id_id_run_review_job_id" not in constraints()
        assert "uq_reviews_tenant_id_run_review_job_id" in constraints()  # 0006 untouched
        command.upgrade(config, "0008")
        assert "review_outputs" in tables()
    finally:
        command.upgrade(config, "head")
    command.check(config)  # raises AutogenerateDiffsDetected on any difference
