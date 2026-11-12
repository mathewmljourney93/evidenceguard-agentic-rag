"""PostgreSQL integration tests for the M5g ``run_review`` handler (ADR-0025).

Skipped without ``EG_TEST_DATABASE_URL`` (required in CI). Revisions are ingested and indexed
through the real worker; the review is created through M5d with the pinned artifacts; the handler
runs through ``run_worker`` with a **test** registry, or on a real ``JobContext`` over the M3
fence when an interruption must be placed exactly. Model results are scripted (no network).
"""

import hashlib
import json
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, func, select, text, update
from sqlalchemy.engine import URL

from evidenceguard_agents.report import render_report_markdown
from evidenceguard_agents.scripted import Respond, Timeout
from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_domain.model_calls import CallOutcome, StructuredRequest
from evidenceguard_domain.review_outputs import ReviewStatus
from evidenceguard_observability.provider_spans import BoundedSpanCollector
from evidenceguard_persistence import jobs as job_store
from evidenceguard_persistence.models import (
    Job,
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


def test_a_returned_response_interrupted_before_stage_commit_repeats_once_on_reclaim(
    world: pw.ReviewWorld,
) -> None:
    question = pw.question_ids()[0]
    text_response = pw.verifier_text(world.chunk_id)
    inner = pw.provider(
        world.chunk_id,
        {
            ("verifier", question): (
                Respond(text_response),
                Respond(text_response),
            )
        },
    )
    requests: list[StructuredRequest] = []

    class Recording:
        @property
        def provider_id(self) -> str:
            return inner.provider_id

        def generate(self, request: StructuredRequest) -> Any:
            requests.append(request)
            return inner.generate(request)

    model = Recording()
    sink = BoundedSpanCollector()
    claimed = job_store.claim(world.factory, "w-m5g-interrupted", kinds={"run_review"})
    assert claimed is not None and claimed.id == world.job_id and claimed.attempt == 1
    state = AttemptState(deadline=float("inf"), lease_seconds=60.0, clock=lambda: 0.0)
    ctx = JobContext(
        claimed, state, lambda token: job_store.fenced_transaction(world.factory, token)
    )

    class InterruptedAfterResponse(BaseException):
        pass

    interrupt = InterruptedAfterResponse()
    real = vars(review_module)["call_validated"]

    def after_return(*args: Any, **kwargs: Any) -> Any:
        result = real(*args, **kwargs)
        assert result.question_id == question and result.dispatched is True
        assert result.outcome is CallOutcome.COMPLETED
        assert len(requests) == len(inner.history) == 1
        raise interrupt

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(review_module, "call_validated", after_return)
        with pytest.raises(InterruptedAfterResponse) as caught:
            review_module.make_run_review_handler(
                model, session_factory=world.factory, span_sink=sink
            )(ctx)
    assert caught.value is interrupt

    def target(table: Any) -> Any:
        return select(table.__table__).where(
            table.tenant_id == world.actor.tenant_id,
            table.review_id == world.review_id,
            table.job_id == world.job_id,
            table.question_id == question,
            table.stage == "verification",
        )

    with world.engine.connect() as connection:
        first_call = connection.execute(target(ReviewStageCall)).one()
        assert connection.execute(target(ReviewStageResult)).all() == []
        assert (
            connection.execute(
                select(ReviewOutputRow).where(ReviewOutputRow.review_id == world.review_id)
            ).all()
            == []
        )
    digest = requests[0].request_sha256
    assert (
        first_call.sequence,
        first_call.state,
        first_call.job_attempt,
        first_call.call_kind,
        first_call.request_basis,
    ) == (1, "started", 1, "initial", "original")
    assert first_call.request_sha256 == digest and world.job().status == "running"
    with world.engine.begin() as connection:
        expired = connection.execute(
            update(Job)
            .where(
                Job.id == world.job_id,
                Job.tenant_id == world.actor.tenant_id,
                Job.status == "running",
                Job.attempt == 1,
            )
            .values(lease_expires_at=func.clock_timestamp() - text("interval '1 second'"))
        )
        assert expired.rowcount == 1
    assert world.run(model, span_sink=sink).exit_code == 0
    assert world.job().status == "succeeded" and world.job().attempt == 2
    matching = [
        r for r in requests if r.question_id == question and r.prompt.prompt_id == "verifier"
    ]
    assert len(matching) == 2
    assert (
        len([r for r in inner.history if r.question_id == question and r.prompt_id == "verifier"])
        == 2
    )
    before, after = matching
    assert before.request_sha256 == after.request_sha256 == digest
    for name in (
        "purpose",
        "prompt",
        "model_id",
        "question_id",
        "system_text",
        "user_text",
        "max_output_tokens",
        "timeout_ms",
        "output_schema",
    ):
        assert getattr(before, name) == getattr(after, name)
    assert before.system_text.encode() == after.system_text.encode()
    assert before.user_text.encode() == after.user_text.encode()
    with world.engine.connect() as connection:
        history = connection.execute(
            target(ReviewStageCall).order_by(ReviewStageCall.sequence)
        ).all()
        stage = connection.execute(target(ReviewStageResult)).one()
        all_calls = connection.execute(
            select(ReviewStageCall.__table__).where(
                ReviewStageCall.tenant_id == world.actor.tenant_id,
                ReviewStageCall.review_id == world.review_id,
            )
        ).all()
    assert [
        (r.sequence, r.call_kind, r.request_basis, r.state, r.job_attempt) for r in history
    ] == [
        (1, "initial", "original", "started", 1),
        (2, "retry", "original", "completed", 2),
    ]
    assert all(r.request_sha256 == digest for r in history)
    assert history[1].dispatched is True and history[1].outcome == "completed"
    assert stage.call_sequence == 2 and stage.outcome == "verified"
    verified = json.loads(stage.content_canonical)
    assert verified["verification"]["evidence_status"] == "vendor_claim"
    assert any(
        c["chunk_id"] == str(world.chunk_id) and c["quote"] == pw.QUOTE
        for c in verified["citations"]
    )
    assert all(
        r.sequence == 1 for r in all_calls if (r.question_id, r.stage) != (question, "verification")
    )
    reader = ActorContext(
        tenant_id=world.actor.tenant_id, actor_id=world.actor.actor_id, role=Role.REVIEWER
    )
    assert load_review_status(world.factory, reader, world.review_id) is ReviewStatus.COMPLETED
    trusted = load_trusted_review_output(world.factory, reader, world.review_id)
    assert trusted.markdown == render_report_markdown(trusted.stored.output.content)
    assert (
        hashlib.sha256(trusted.markdown.encode()).hexdigest()
        == trusted.stored.output.markdown_sha256
    )
    report_question = next(
        q for q in trusted.stored.output.content.questions if q.question_id == question
    )
    assert report_question.verification.value is not None
    assert report_question.verification.value.evidence_status.value == "vendor_claim"
    target_spans = [
        s
        for s in sink.snapshot()
        if s.tenant_id == world.actor.tenant_id
        and s.review_id == world.review_id
        and s.question_id == question
        and s.stage == "verification"
        and s.request_sha256 == digest
    ]
    assert len(target_spans) == 2 and target_spans[0].span_id != target_spans[1].span_id
    assert (
        target_spans[0].exit_kind == "process_control" and target_spans[1].exit_kind == "returned"
    )


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
    assert claimed is not None and claimed.id == world.job_id and claimed.attempt == 1
    state = AttemptState(deadline=float("inf"), lease_seconds=60.0, clock=lambda: 0.0)
    store = job_store

    def fence(token: Any) -> Any:
        return store.fenced_transaction(world.factory, token)

    ctx = JobContext(claimed, state, fence)
    model = pw.provider(world.chunk_id)

    class Cancelling:
        """Records every dispatch. ``call_validated`` maps an ordinary provider exception to a
        ``provider_failed`` result, so raising here alone would not prove the absence of a call;
        the recorded list does."""

        provider_id = "scripted-fake"

        def __init__(self) -> None:
            self.calls: list[str] = []

        def generate(self, request: Any) -> Any:
            self.calls.append(request.request_sha256)
            raise AssertionError("dispatched after cancellation")

    cancelling = Cancelling()
    real_reserve = getattr(review_module, "reserve_call")  # noqa: B009 - patched below

    def reserve_then_cancel(*args: Any, **kwargs: Any) -> Any:
        reserved = real_reserve(*args, **kwargs)
        state.request_cancel()  # latched after the reservation, before dispatch
        return reserved

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(review_module, "reserve_call", reserve_then_cancel)
        handler = review_module.make_run_review_handler(cancelling, session_factory=world.factory)
        with pytest.raises(Exception) as raised:
            handler(ctx)
    assert type(raised.value).__name__ == "JobCancelledError"
    assert cancelling.calls == []  # the pre-dispatch boundary stopped the only call
    # The interrupted reservation: exactly one row, the first planned question's initial
    # Verification call, started by attempt 1. Its identity and digest are captured here.
    with world.engine.connect() as connection:
        (interrupted,) = connection.execute(select(ReviewStageCall.__table__)).all()
    first_question = pw.question_ids()[0]  # planned (template) order, not alphabetical order
    assert (
        interrupted.tenant_id,
        interrupted.review_id,
        interrupted.job_id,
        interrupted.question_id,
        interrupted.stage,
        interrupted.sequence,
        interrupted.call_kind,
        interrupted.request_basis,
        interrupted.state,
        interrupted.job_attempt,
    ) == (
        world.actor.tenant_id,
        world.review_id,
        world.job_id,
        first_question,
        "verification",
        1,
        "initial",
        "original",
        "started",
        1,
    )
    digest = interrupted.request_sha256
    job_store.fail_retryable(world.factory, ctx.token)
    with world.engine.begin() as connection:
        connection.execute(text("UPDATE jobs SET run_after = clock_timestamp()"))
    assert world.run(model).exit_code == 0
    assert world.job().status == "succeeded"
    # Only the interrupted stage's own history, ordered by sequence.
    with world.engine.connect() as connection:
        history = connection.execute(
            select(ReviewStageCall.__table__)
            .where(
                ReviewStageCall.tenant_id == interrupted.tenant_id,
                ReviewStageCall.review_id == interrupted.review_id,
                ReviewStageCall.question_id == interrupted.question_id,
                ReviewStageCall.stage == interrupted.stage,
            )
            .order_by(ReviewStageCall.sequence)
        ).all()
    assert [
        (r.sequence, r.call_kind, r.request_basis, r.state, r.job_attempt) for r in history
    ] == [
        (1, "initial", "original", "started", 1),  # abandoned: never completed, still counted
        (2, "retry", "original", "completed", 2),
    ]
    assert [r.request_sha256 for r in history] == [digest, digest]  # the retry reuses it


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
