"""M5g output values, the strict stored-row decoder, the fixed error table, the offline
migration ``0008`` SQL and the persistence argument boundaries (ADR-0025). No database.

Expected digests come from the accepted M5f codec (``review_report_bytes`` and the M5f
renderer), which these values do not implement, and from ``hashlib``; constraint names are
literals from the accepted M5g-F table.
"""

import dataclasses
import hashlib
import io
import re
from datetime import UTC, datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

import pytest
from alembic import command
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from evidenceguard_agents import report as builder
from evidenceguard_domain import review_outputs as ro
from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_domain.errors import PermissionDeniedError
from evidenceguard_domain.jobs import JobPayload, JobSnapshot, JobStatus
from evidenceguard_domain.report_content import ReviewReportContent, review_report_bytes
from evidenceguard_domain.review_outputs import (
    REVIEW_OUTPUT_COLUMNS,
    InvalidReviewOutputError,
    InvalidStoredOutputError,
    ReviewOutput,
    ReviewOutputWrite,
    ReviewStatus,
    StoredReviewOutput,
    decode_stored_review_output,
)
from evidenceguard_persistence import review_outputs as store
from evidenceguard_persistence.jobs import Fence, FencedSession
from evidenceguard_persistence.migration_config import alembic_config
from evidenceguard_persistence.models import ReviewOutputRow
from evidenceguard_persistence.review_outputs import (
    InvalidOutputRequestError,
    ReviewOutputRecordInconsistentError,
    load_review_output,
    load_review_status,
    write_review_output,
)
from evidenceguard_persistence.settings import DATABASE_URL_ENV
from evidenceguard_worker import review as worker

if TYPE_CHECKING:
    import test_report_builder as rb
    import test_review_stage_values as old
    from test_report_content import bypass
else:
    from tests import test_report_builder as rb
    from tests import test_review_stage_values as old
    from tests.test_report_content import bypass

T = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)


def content() -> ReviewReportContent:
    return builder.build_report_content(*rb.world((1, 2), documentary=True))


def markdown_meta(value: ReviewReportContent) -> tuple[str, int]:
    rendered = builder.render_report_markdown(value).encode("utf-8")
    return hashlib.sha256(rendered).hexdigest(), len(rendered)


def output(**changes: Any) -> ReviewOutput:
    value = content()
    digest, size = markdown_meta(value)
    binding = value.binding
    values: dict[str, Any] = {
        "tenant_id": binding.tenant_id,
        "review_id": binding.review_id,
        "job_id": binding.job_id,
        "content": value,
        "markdown_sha256": digest,
        "markdown_bytes": size,
    }
    values.update(changes)
    return ReviewOutput(**values)


def fixed(error: BaseException, kind: type[BaseException]) -> None:
    assert type(error) is kind
    assert error.__cause__ is None and error.__context__ is None


# --- ReviewOutput ---------------------------------------------------------------------------------


def test_review_output_recomputes_every_derived_field() -> None:
    value = output()
    wrapper = review_report_bytes(value.content)
    assert value.wrapper_canonical == wrapper
    assert value.wrapper_sha256 == hashlib.sha256(wrapper).hexdigest()
    assert value.schema_id == "evidenceguard.review-report-content.v1"
    assert value.renderer_id == "evidenceguard.review-report-markdown.v1"
    assert value.mode == "contract"
    assert value.legacy_sha256 == value.content.legacy_sha256
    binding = value.content.binding
    assert value.review_request_sha256 == binding.review_request_sha256
    assert value.snapshot_sha256 == binding.snapshot_sha256
    assert value.configuration_sha256 == binding.configuration.configuration_sha256
    assert (value.question_count, value.finding_count) == (2, 5)  # 3 analyst + 2 documentary
    assert value.unresolved_count == len(value.content.content.unresolved_question_ids)


def test_review_output_repr_shows_identifiers_digests_and_counts_only() -> None:
    value = output()
    shown = repr(value)
    assert shown == (
        f"ReviewOutput(review_id={value.review_id}, wrapper_sha256={value.wrapper_sha256!r}, "
        f"questions=2, findings=5, unresolved={value.unresolved_count})"
    )
    assert str(value) == shown
    for secret in ("Finding 0", "Statement", "Follow up", "encrypted at rest", "Review report"):
        assert secret not in shown


@pytest.mark.parametrize(
    "changes",
    [
        {"markdown_bytes": True},  # bool is not int
        {"markdown_bytes": 0},
        {"markdown_bytes": 33_554_433},
        {"markdown_sha256": "A" * 64},
        {"markdown_sha256": "a" * 63},
        {"tenant_id": str(old.TENANT)},
        {"review_id": UUID(int=1)},  # differs from the content binding
        {"job_id": UUID(int=2)},
        {"wrapper_sha256": "0" * 64},  # a derived field is never accepted
        {"unknown": 1},
    ],
)
def test_review_output_refuses_inexact_mismatched_or_derived_arguments(
    changes: dict[str, Any],
) -> None:
    with pytest.raises(InvalidReviewOutputError) as raised:
        output(**changes)
    fixed(raised.value, InvalidReviewOutputError)
    assert str(raised.value) == "the review output is invalid"


def test_a_missing_keyword_is_the_fixed_error() -> None:
    value = output()
    with pytest.raises(InvalidReviewOutputError) as raised:
        ReviewOutput(tenant_id=value.tenant_id, review_id=value.review_id, job_id=value.job_id)
    fixed(raised.value, InvalidReviewOutputError)


class _Str(str):
    pass


def test_bypass_built_nested_content_and_subclasses_are_refused() -> None:
    value = content()
    for bad in (
        bypass(value, mode="contract"),  # object.__new__ with a str in place of the enum
        bypass(value, questions=list(value.questions)),
        object.__new__(ReviewReportContent),
    ):
        with pytest.raises(InvalidReviewOutputError):
            output(content=bad)
    with pytest.raises(InvalidReviewOutputError):
        output(markdown_sha256=_Str("a" * 64))


def test_replace_runs_the_same_constructor() -> None:
    value = output()
    with pytest.raises(InvalidReviewOutputError):
        dataclasses.replace(value, markdown_bytes=0)
    same = dataclasses.replace(value, markdown_bytes=value.markdown_bytes)
    assert same == value and same.wrapper_sha256 == value.wrapper_sha256


# --- StoredReviewOutput and ReviewOutputWrite -----------------------------------------------------


def test_stored_output_normalizes_an_offset_timestamp_to_utc_and_refuses_naive() -> None:
    value = output()
    plus_two = timezone(timedelta(hours=2))
    stored = StoredReviewOutput(
        output=value, job_attempt=2, created_at=datetime(2026, 11, 6, 14, 0, tzinfo=plus_two)
    )
    assert stored.created_at == T and stored.created_at.tzinfo is UTC
    assert repr(stored) == f"StoredReviewOutput(output={value!r}, job_attempt=2)"
    for bad in (
        {"created_at": datetime(2026, 11, 6, 12, 0)},  # naive
        {"created_at": "2026-11-06T12:00:00Z"},
        {"job_attempt": 0},
        {"job_attempt": 11},
        {"job_attempt": True},
        {"output": object.__new__(ReviewOutput)},
        {"output": bypass(value, markdown_bytes=0)},
        {"extra": 1},
    ):
        values: dict[str, Any] = {"output": value, "job_attempt": 1, "created_at": T, **bad}
        with pytest.raises(InvalidStoredOutputError) as raised:
            StoredReviewOutput(**values)
        fixed(raised.value, InvalidStoredOutputError)


def test_the_write_result_carries_an_exact_replay_flag() -> None:
    stored = StoredReviewOutput(output=output(), job_attempt=1, created_at=T)
    written = ReviewOutputWrite(stored=stored, replayed=True)
    assert repr(written) == f"ReviewOutputWrite(review_id={old.REVIEW}, replayed=True)"
    for bad in ({"replayed": 1}, {"replayed": None}, {"stored": stored.output}):
        with pytest.raises(InvalidStoredOutputError):
            ReviewOutputWrite(**cast(Any, {"stored": stored, "replayed": False, **bad}))


def test_review_status_values() -> None:
    assert [s.value for s in ReviewStatus] == ["queued", "running", "completed", "failed"]


# --- the strict stored-row decoder --------------------------------------------------------------


def row(value: ReviewOutput | None = None, **changes: Any) -> dict[str, Any]:
    value = value or output()
    values: dict[str, Any] = {
        "tenant_id": value.tenant_id,
        "review_id": value.review_id,
        "job_id": value.job_id,
        "schema_id": value.schema_id,
        "renderer_id": value.renderer_id,
        "mode": value.mode,
        "wrapper_canonical": value.wrapper_canonical.decode("ascii"),
        "wrapper_sha256": value.wrapper_sha256,
        "legacy_sha256": value.legacy_sha256,
        "review_request_sha256": value.review_request_sha256,
        "snapshot_sha256": value.snapshot_sha256,
        "configuration_sha256": value.configuration_sha256,
        "question_count": value.question_count,
        "finding_count": value.finding_count,
        "unresolved_count": value.unresolved_count,
        "markdown_sha256": value.markdown_sha256,
        "markdown_bytes": value.markdown_bytes,
        "job_attempt": 1,
        "created_at": T,
    }
    values.update(changes)
    return values


def test_the_decoder_round_trips_a_valid_row() -> None:
    value = output()
    stored = decode_stored_review_output(row(value))
    assert stored.output == value and stored.job_attempt == 1 and stored.created_at == T
    assert set(row()) == REVIEW_OUTPUT_COLUMNS and len(REVIEW_OUTPUT_COLUMNS) == 19


def _mutations() -> list[tuple[str, Any]]:
    value = output()
    wrapper = value.wrapper_canonical.decode("ascii")
    return [
        ("extra", "x"),
        ("tenant_id", str(value.tenant_id)),
        ("question_count", True),
        ("question_count", value.question_count + 1),
        ("finding_count", value.finding_count - 1),
        ("unresolved_count", value.unresolved_count + 1),
        ("schema_id", "evidenceguard.review-report-content.v2"),
        ("renderer_id", "other"),
        ("mode", "live"),
        ("legacy_sha256", "0" * 64),
        ("review_request_sha256", "0" * 64),
        ("snapshot_sha256", "0" * 64),
        ("configuration_sha256", "0" * 64),
        ("wrapper_sha256", "0" * 64),
        ("wrapper_sha256", "A" * 64),
        ("wrapper_canonical", wrapper.replace(":", ": ", 1)),  # not the canonical bytes
        ("wrapper_canonical", wrapper[:-1] + "\t"),  # not printable ASCII
        ("wrapper_canonical", wrapper.encode("ascii")),  # bytes, not str
        ("markdown_bytes", 0),
        ("job_attempt", 0),
        ("created_at", datetime(2026, 11, 6, 12, 0)),
        ("review_id", UUID(int=7)),
    ]


@pytest.mark.parametrize(("column", "value"), _mutations())
def test_the_decoder_refuses_every_tampered_column(column: str, value: Any) -> None:
    with pytest.raises(InvalidStoredOutputError) as raised:
        decode_stored_review_output(row(**{column: value}))
    fixed(raised.value, InvalidStoredOutputError)


def test_the_decoder_refuses_a_missing_key_and_an_oversize_wrapper_before_decoding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing = row()
    del missing["created_at"]
    with pytest.raises(InvalidStoredOutputError):
        decode_stored_review_output(missing)

    def never(*_: Any, **__: Any) -> Any:
        raise AssertionError("decoded")

    monkeypatch.setattr(ro, "decode_review_report", never)
    with pytest.raises(InvalidStoredOutputError):
        decode_stored_review_output(row(wrapper_canonical="a" * 16_777_217))
    with pytest.raises(InvalidStoredOutputError):
        decode_stored_review_output(cast(Any, [("tenant_id", 1)]))


def test_the_decoder_propagates_process_control_as_the_same_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    control = KeyboardInterrupt()

    def interrupt(*_: Any, **__: Any) -> Any:
        raise control

    monkeypatch.setattr(ro, "decode_review_report", interrupt)
    with pytest.raises(KeyboardInterrupt) as raised:
        decode_stored_review_output(row())
    assert raised.value is control


# --- the fixed error table (M5g-F) ---------------------------------------------------------------


def test_the_error_table_codes_and_messages() -> None:
    table = [
        (ro.InvalidReviewOutputError, "invalid_review_output", "the review output is invalid"),
        (
            ro.InvalidStoredOutputError,
            "invalid_stored_review_output",
            "the stored review output is invalid",
        ),
        (
            store.InvalidOutputRequestError,
            "invalid_review_output_request",
            "the review output request is invalid",
        ),
        (
            store.ReviewOutputFenceMismatchError,
            "review_output_fence_mismatch",
            "the fence is not the review's canonical job",
        ),
        (
            store.ReviewOutputBindingError,
            "review_output_binding_mismatch",
            "the review output does not match the review",
        ),
        (
            store.ReviewOutputIncompleteError,
            "review_output_incomplete",
            "the review stages are incomplete or differ",
        ),
        (
            store.ReviewOutputConflictError,
            "review_output_conflict",
            "a different review output exists",
        ),
        (store.ReviewOutputNotFoundError, "review_output_not_found", "the review has no output"),
        (
            store.ReviewOutputRecordInconsistentError,
            "review_output_record_inconsistent",
            "the stored review output is inconsistent",
        ),
        (
            store.ReviewOutputDatabaseError,
            "review_output_database_error",
            "the review output could not be read or written",
        ),
        (
            worker.UnsupportedEmbeddingProfileError,
            "unsupported_embedding_profile",
            "the review's embedding profile is not supported",
        ),
        (
            worker.ReviewRendererDriftError,
            "review_renderer_drift",
            "the stored review output does not match its renderer",
        ),
        (
            worker.ReviewFenceExitError,
            "review_fence_exit_failed",
            "a fenced review operation did not complete",
        ),
    ]
    for kind, code, message in table:
        error = kind()
        assert cast(Any, kind).code == code and str(error) == message and error.args == (message,)
    assert str(worker.ReviewCompositionError()) == ""  # private: no code, no text


# --- the offline migration 0008 SQL ---------------------------------------------------------------

CHECK_NAMES = {
    f"ck_review_outputs_{name}"
    for name in (
        "schema_id",
        "renderer_id",
        "mode",
        "wrapper_ascii",
        "wrapper_printable",
        "wrapper_size",
        "wrapper_sha256",
        "legacy_sha256",
        "review_request_sha256",
        "snapshot_sha256",
        "configuration_sha256",
        "markdown_sha256",
        "question_count",
        "finding_count",
        "unresolved_count",
        "markdown_bytes",
        "job_attempt",
    )
}
KEY_NAMES = {
    "pk_review_outputs",
    "uq_review_outputs_tenant_id_job_id",
    "fk_review_outputs_review",
    "fk_review_outputs_job",
    "fk_review_outputs_review_job",
}


def _offline(monkeypatch: pytest.MonkeyPatch, *, upgrade: bool) -> str:
    monkeypatch.delenv(DATABASE_URL_ENV, raising=False)
    buffer = io.StringIO()
    config = alembic_config(output_buffer=buffer)
    if upgrade:
        command.upgrade(config, "0007:0008", sql=True)
    else:
        command.downgrade(config, "0008:0007", sql=True)
    return buffer.getvalue()


def test_offline_0008_renders_the_model_table_constraints_and_the_reviews_unique(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rendered = _offline(monkeypatch, upgrade=True)
    unique = rendered.index(
        "ALTER TABLE reviews ADD CONSTRAINT uq_reviews_tenant_id_id_run_review_job_id "
        "UNIQUE (tenant_id, id, run_review_job_id)"
    )
    created = rendered.index("CREATE TABLE review_outputs")
    assert unique < created  # the composite foreign key's target exists first
    assert re.findall(r"CREATE TABLE (\w+)", rendered) == ["review_outputs"]
    names = set(re.findall(r"CONSTRAINT (\w+)", rendered))
    assert names == CHECK_NAMES | KEY_NAMES | {"uq_reviews_tenant_id_id_run_review_job_id"}
    model = str(
        CreateTable(ReviewOutputRow.__table__).compile(dialect=postgresql.dialect())  # type: ignore[arg-type, no-untyped-call]
    )
    assert set(re.findall(r"CONSTRAINT (\w+)", model)) == CHECK_NAMES | KEY_NAMES
    assert "ON DELETE" not in rendered and "ON UPDATE" not in rendered  # NO ACTION, no cascade
    assert "wrapper_canonical !~ '[^ -~]'" in rendered
    assert "unresolved_count BETWEEN 0 AND question_count" in rendered
    assert "DEFAULT clock_timestamp()" in rendered
    assert (
        "FOREIGN KEY(tenant_id, review_id, job_id) "
        "REFERENCES reviews (tenant_id, id, run_review_job_id)"
    ) in rendered


def test_offline_0008_downgrade_drops_exactly_the_table_then_the_unique(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rendered = _offline(monkeypatch, upgrade=False)
    statements = [
        line
        for line in rendered.splitlines()
        if line.startswith(("DROP", "ALTER TABLE reviews DROP"))
    ]
    assert statements == [
        "DROP TABLE review_outputs;",
        "ALTER TABLE reviews DROP CONSTRAINT uq_reviews_tenant_id_id_run_review_job_id;",
    ]


# --- persistence argument boundaries before any SQL (G24) ----------------------------------------


class _NoSql:
    def execute(self, *_: Any, **__: Any) -> Any:
        raise AssertionError("SQL ran before the argument checks")


def _job() -> JobSnapshot:
    return JobSnapshot(
        id=old.JOB,
        tenant_id=old.TENANT,
        kind="run_review",
        idempotency_key=str(old.REVIEW),
        payload=JobPayload.from_mapping({"review_id": str(old.REVIEW)}),
        status=JobStatus.RUNNING,
        attempt=1,
        max_attempts=3,
        run_after=T,
        locked_by="worker-test",
        lease_expires_at=T + timedelta(seconds=60),
        created_at=T,
        updated_at=T,
    )


class _Fence:
    def __init__(self, session: Any, job: Any) -> None:
        self.session = session
        self.job = job


def _fenced_session(job: JobSnapshot) -> FencedSession:
    fence = Fence(cast(Any, _NoSql()), job.lease_token(), job)
    return fence.session


class _RaisingFence:
    @property
    def session(self) -> Any:
        raise RuntimeError("SELECT sentinel")

    job = None


def test_the_writer_refuses_bypass_inputs_before_any_sql() -> None:
    job = _job()
    good = output()
    session = _fenced_session(job)
    coerced = JobSnapshot.model_construct(**{**dict(job), "attempt": True})
    for fence, value in (
        (_Fence(session, job), object.__new__(ReviewOutput)),
        (_Fence(session, job), bypass(good, markdown_bytes=0)),
        (_Fence(session, job), cast(Any, good.content)),
        (_Fence(_NoSql(), job), good),  # not a FencedSession
        (_Fence(session, coerced), good),  # an inexact field type
        (_Fence(session, object.__new__(JobSnapshot)), good),
        (_RaisingFence(), good),
    ):
        with pytest.raises(InvalidOutputRequestError) as raised:
            write_review_output(cast(Any, fence), value)
        fixed(raised.value, InvalidOutputRequestError)
        assert "sentinel" not in repr(raised.value)


class _NeverOpened:
    def __call__(self) -> Any:
        raise AssertionError("a session was opened before the argument and role checks")


@pytest.mark.parametrize("load", [load_review_output, load_review_status])
def test_the_reads_check_actor_and_id_types_then_the_role_before_any_session(load: Any) -> None:
    actor = ActorContext(tenant_id=old.TENANT, actor_id=UUID(int=3), role=Role.REVIEWER)
    for bad_actor, review_id in (
        (
            ActorContext.model_construct(
                tenant_id=cast(Any, str(old.TENANT)), actor_id=UUID(int=3), role=Role.REVIEWER
            ),
            old.REVIEW,
        ),
        (
            ActorContext.model_construct(
                tenant_id=old.TENANT, actor_id=UUID(int=3), role=cast(Any, "reviewer")
            ),
            old.REVIEW,
        ),
        (object.__new__(ActorContext), old.REVIEW),
        (actor, str(old.REVIEW)),
        (cast(Any, {"tenant_id": old.TENANT}), old.REVIEW),
    ):
        with pytest.raises(InvalidOutputRequestError):
            load(_NeverOpened(), bad_actor, review_id)
    admin = ActorContext(tenant_id=old.TENANT, actor_id=UUID(int=3), role=Role.ADMIN)
    with pytest.raises(PermissionDeniedError):
        load(_NeverOpened(), admin, old.REVIEW)


def test_the_shared_lifecycle_presence_table() -> None:
    def job(status: str) -> Any:
        return type("Job", (), {"status": status})()

    assert store._lifecycle(job("succeeded"), True) is ReviewStatus.COMPLETED
    assert store._lifecycle(job("queued"), False) is ReviewStatus.QUEUED
    assert store._lifecycle(job("running"), False) is ReviewStatus.RUNNING
    assert store._lifecycle(job("failed"), False) is ReviewStatus.FAILED
    assert store._lifecycle(job("dead"), False) is ReviewStatus.FAILED
    for status, present in (
        ("queued", True),
        ("running", True),  # the deliberate replay state is never readable as completed
        ("failed", True),
        ("dead", True),
        ("succeeded", False),  # success without an output
    ):
        with pytest.raises(store._Refusal) as raised:
            store._lifecycle(job(status), present)
        assert raised.value.error is ReviewOutputRecordInconsistentError
