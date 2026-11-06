"""PostgreSQL integration tests for M5g output persistence, reads and constraints (ADR-0025).

Skipped without ``EG_TEST_DATABASE_URL`` (required in CI). A valid output row is produced by one
real handler run; constraint, binding, lifecycle and tampering cases then change single columns
or the job's lifecycle fields directly through SQL, only to prove that the database or the reads
refuse them. The writer is called inside a real M3 fence for the deliberate replay and conflict
cases (M5g-G2), which no normal handler path reaches.
"""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, delete, insert, select, text, update
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError

from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_domain.review_outputs import ReviewOutput, ReviewStatus
from evidenceguard_domain.reviews import ReviewNotFoundError
from evidenceguard_persistence import jobs as job_store
from evidenceguard_persistence.db import transaction
from evidenceguard_persistence.models import Job, Review, ReviewOutputRow, ReviewStageResult
from evidenceguard_persistence.review_outputs import (
    ReviewOutputConflictError,
    ReviewOutputFenceMismatchError,
    ReviewOutputIncompleteError,
    ReviewOutputNotFoundError,
    ReviewOutputRecordInconsistentError,
    load_review_output,
    load_review_status,
    write_review_output,
)
from evidenceguard_worker.review import ReviewRendererDriftError, load_trusted_review_output

if TYPE_CHECKING:
    import review_postgres_world as pw
else:
    from tests import review_postgres_world as pw

pytestmark = pytest.mark.integration

CHECK_VIOLATION = "23514"
FOREIGN_KEY_VIOLATION = "23503"
UNIQUE_VIOLATION = "23505"


@pytest.fixture
def done(migrated: Engine, test_database_url: URL) -> Iterator[pw.ReviewWorld]:
    world = pw.review_world(migrated, test_database_url)
    try:
        assert world.run(pw.provider(world.chunk_id)).exit_code == 0
        assert world.job().status == "succeeded"
        yield world
    finally:
        world.engine.dispose()


def _reader(world: pw.ReviewWorld) -> ActorContext:
    return ActorContext(tenant_id=world.actor.tenant_id, actor_id=uuid4(), role=Role.REVIEWER)


def _row(world: pw.ReviewWorld) -> dict[str, Any]:
    with world.engine.connect() as connection:
        return dict(connection.execute(select(ReviewOutputRow.__table__)).one()._mapping)


def _sqlstate(error: IntegrityError) -> str | None:
    return getattr(error.orig, "sqlstate", None)


def _refused(engine: Engine, statement: Any) -> tuple[str | None, str]:
    with pytest.raises(IntegrityError) as raised, engine.begin() as connection:
        connection.execute(statement)
    diag = getattr(raised.value.orig, "diag", None)
    return _sqlstate(raised.value), str(getattr(diag, "constraint_name", ""))


# --- constraints ---------------------------------------------------------------------------------

VIOLATIONS: list[tuple[str, dict[str, Any]]] = [
    ("schema_id", {"schema_id": "other"}),
    ("renderer_id", {"renderer_id": "other"}),
    ("mode", {"mode": "live"}),
    ("wrapper_ascii", {"wrapper_canonical": "café"}),
    ("wrapper_printable", {"wrapper_canonical": "line\nbreak"}),
    ("wrapper_size", {"wrapper_canonical": ""}),
    ("wrapper_sha256", {"wrapper_sha256": "X" * 64}),
    ("legacy_sha256", {"legacy_sha256": "x"}),
    ("review_request_sha256", {"review_request_sha256": "x"}),
    ("snapshot_sha256", {"snapshot_sha256": "x"}),
    ("configuration_sha256", {"configuration_sha256": "x"}),
    ("markdown_sha256", {"markdown_sha256": "x"}),
    ("question_count", {"question_count": 0}),
    ("finding_count", {"finding_count": 201}),
    ("unresolved_count", {"unresolved_count": 9}),
    ("markdown_bytes", {"markdown_bytes": 0}),
    ("job_attempt", {"job_attempt": 11}),
]


@pytest.mark.parametrize(("name", "values"), VIOLATIONS)
def test_each_named_check_refuses_one_violating_row(
    done: pw.ReviewWorld, name: str, values: dict[str, Any]
) -> None:
    state, constraint = _refused(done.engine, update(ReviewOutputRow).values(**values))
    assert state == CHECK_VIOLATION and constraint == f"ck_review_outputs_{name}"


CATALOGUE_SQL = text(
    """
    SELECT c.conname,
           c.contype,
           ARRAY(SELECT a.attname FROM unnest(c.conkey) WITH ORDINALITY k(num, ord)
                 JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.num
                 ORDER BY k.ord) AS columns,
           c.confrelid::regclass::text AS referenced,
           ARRAY(SELECT a.attname FROM unnest(c.confkey) WITH ORDINALITY k(num, ord)
                 JOIN pg_attribute a ON a.attrelid = c.confrelid AND a.attnum = k.num
                 ORDER BY k.ord) AS referenced_columns,
           c.confupdtype, c.confdeltype, c.confmatchtype, c.condeferrable
    FROM pg_constraint c
    WHERE c.conrelid = CAST(:table AS regclass) AND c.contype IN ('p', 'u', 'f')
    """
)


def _keys(engine: Engine, table: str) -> dict[str, Any]:
    with engine.connect() as connection:
        return {row.conname: row for row in connection.execute(CATALOGUE_SQL, {"table": table})}


def test_the_catalogue_records_the_exact_keys_and_foreign_keys(done: pw.ReviewWorld) -> None:
    keys = _keys(done.engine, "review_outputs")
    shape = {
        name: (row.contype, list(row.columns), row.referenced, list(row.referenced_columns))
        for name, row in keys.items()
    }
    assert shape == {
        "pk_review_outputs": ("p", ["tenant_id", "review_id"], "-", []),
        "uq_review_outputs_tenant_id_job_id": ("u", ["tenant_id", "job_id"], "-", []),
        "fk_review_outputs_review": (
            "f",
            ["tenant_id", "review_id"],
            "reviews",
            ["tenant_id", "id"],
        ),
        "fk_review_outputs_job": ("f", ["tenant_id", "job_id"], "jobs", ["tenant_id", "id"]),
        "fk_review_outputs_review_job": (
            "f",
            ["tenant_id", "review_id", "job_id"],
            "reviews",
            ["tenant_id", "id", "run_review_job_id"],
        ),
    }
    for name, row in keys.items():
        assert not row.condeferrable, name  # checked immediately, never deferred
        if row.contype == "f":
            # NO ACTION ('a') on update and delete: nothing cascades, nulls or defaults; the
            # default MATCH SIMPLE ('s').
            assert (row.confupdtype, row.confdeltype, row.confmatchtype) == ("a", "a", "s"), name
    target = _keys(done.engine, "reviews")["uq_reviews_tenant_id_id_run_review_job_id"]
    assert (target.contype, list(target.columns)) == ("u", ["tenant_id", "id", "run_review_job_id"])


def _insert_refused(world: pw.ReviewWorld, values: dict[str, Any]) -> tuple[str | None, str]:
    """Insert ``values`` into ``review_outputs`` after deleting the stored output **in the same
    transaction**, so neither key of the stored row can interfere; the failed statement rolls the
    whole transaction back and the stored output is unchanged afterwards."""
    with pytest.raises(IntegrityError) as raised, world.engine.begin() as connection:
        connection.execute(delete(ReviewOutputRow))
        connection.execute(insert(ReviewOutputRow).values(**values))
    diag = getattr(raised.value.orig, "diag", None)
    return _sqlstate(raised.value), str(getattr(diag, "constraint_name", ""))


def _other_job(world: pw.ReviewWorld) -> UUID:
    """An existing job of the same tenant that is not the review's canonical job."""
    with transaction(world.factory) as session:
        job = job_store.enqueue(
            session, world.actor, kind="run_review", idempotency_key="m5g-unrelated-job"
        )
    return job.id


def test_a_missing_review_is_refused_by_the_review_references(done: pw.ReviewWorld) -> None:
    before = _row(done)
    state, constraint = _insert_refused(done, {**before, "review_id": uuid4()})
    # Both references naming the review fail for a missing review; either may be reported.
    assert state == FOREIGN_KEY_VIOLATION
    assert constraint in {"fk_review_outputs_review", "fk_review_outputs_review_job"}
    assert _row(done) == before


def test_a_missing_job_is_refused_by_the_job_references(done: pw.ReviewWorld) -> None:
    before = _row(done)
    state, constraint = _insert_refused(done, {**before, "job_id": uuid4()})
    # The job reference and the review/job binding both fail for a missing job.
    assert state == FOREIGN_KEY_VIOLATION
    assert constraint in {"fk_review_outputs_job", "fk_review_outputs_review_job"}
    assert _row(done) == before


def test_an_existing_review_with_another_existing_job_is_refused_by_the_binding_alone(
    done: pw.ReviewWorld,
) -> None:
    # The review exists (fk_review holds) and the job exists in the tenant (fk_job holds), the
    # (tenant, job) pair is unused (the unique holds) and the primary key is free, so only the
    # composite review/job binding can refuse the row.
    before = _row(done)
    other = _other_job(done)
    state, constraint = _insert_refused(done, {**before, "job_id": other})
    assert (state, constraint) == (FOREIGN_KEY_VIOLATION, "fk_review_outputs_review_job")
    assert _row(done) == before


def test_the_primary_key_refuses_a_second_output_for_one_review(done: pw.ReviewWorld) -> None:
    # Same (tenant, review) with another existing, unused job: the (tenant, job) unique holds.
    # The review/job binding would also refuse this row, but PostgreSQL checks non-deferrable
    # primary keys and uniques while inserting the row and foreign keys afterwards (row
    # triggers), so the key is reported; the catalogue test pins that none is deferrable.
    before = _row(done)
    other = _other_job(done)
    state, constraint = _refused(
        done.engine, insert(ReviewOutputRow).values(**{**before, "job_id": other})
    )
    assert (state, constraint) == (UNIQUE_VIOLATION, "pk_review_outputs")
    assert _row(done) == before


def test_the_tenant_job_unique_refuses_one_job_for_two_reviews(done: pw.ReviewWorld) -> None:
    # A second real review whose output slot is free (the primary key holds) reusing the first
    # review's job: the (tenant, job) unique is checked at insertion, before the review/job
    # binding that would also refuse it.
    before = _row(done)
    second, second_job = pw.second_review(done)
    values = {**before, "review_id": second}
    state, constraint = _refused(done.engine, insert(ReviewOutputRow).values(**values))
    assert (state, constraint) == (UNIQUE_VIOLATION, "uq_review_outputs_tenant_id_job_id")
    # Positive control: the same row with the second review's own job satisfies every key and
    # reference (the database cannot prove the wrapper belongs to that review; the writer does).
    with done.engine.begin() as connection:
        connection.execute(insert(ReviewOutputRow).values(**{**values, "job_id": second_job}))
    with done.engine.connect() as connection:
        count = connection.execute(text("SELECT count(*) FROM review_outputs")).scalar_one()
    assert count == 2


def _references_to(engine: Engine, table: str) -> set[str]:
    with engine.connect() as connection:
        return set(
            connection.execute(
                text(
                    "SELECT conname FROM pg_constraint "
                    "WHERE contype = 'f' AND confrelid = CAST(:table AS regclass)"
                ),
                {"table": table},
            ).scalars()
        )


def _counts(engine: Engine) -> dict[str, int]:
    tables = (
        "reviews",
        "review_outputs",
        "review_bindings",
        "review_plan_questions",
        "review_stage_results",
        "jobs",
    )
    with engine.connect() as connection:
        return {
            t: connection.execute(text(f"SELECT count(*) FROM {t}")).scalar_one() for t in tables
        }


@pytest.mark.parametrize("target", ["review", "job"])
def test_deleting_a_populated_review_or_its_job_is_refused_and_nothing_cascades(
    done: pw.ReviewWorld, target: str
) -> None:
    # The completed review is referenced by its bindings, planned questions, evidence, calls,
    # stages and output (and its job by those too): any one of those references may be the one
    # PostgreSQL reports. The result is attributed only to the reported constraint, which must
    # be a reference to the deleted table; the output's own references are pinned by the
    # catalogue and the isolated insert tests above.
    before = _counts(done.engine)
    statement = (
        delete(Review).where(Review.id == done.review_id)
        if target == "review"
        else delete(Job).where(Job.id == done.job_id)
    )
    state, constraint = _refused(done.engine, statement)
    assert state == FOREIGN_KEY_VIOLATION
    table = "reviews" if target == "review" else "jobs"
    assert constraint in _references_to(done.engine, table)
    assert {"fk_review_outputs_review", "fk_review_outputs_review_job"} <= _references_to(
        done.engine, "reviews"
    )
    assert _counts(done.engine) == before  # nothing deleted, nothing cascaded


# --- the writer: replay, conflict and precedence --------------------------------------------------


def _stored_output(world: pw.ReviewWorld) -> ReviewOutput:
    return load_review_output(world.factory, _reader(world), world.review_id).output


def _running_again(world: pw.ReviewWorld) -> Any:
    """Make the succeeded job claimable again (a deliberate recovery-test state) and claim it."""
    with world.engine.begin() as connection:
        connection.execute(
            update(Job)
            .where(Job.id == world.job_id)
            .values(status="queued", finished_at=None, run_after=datetime(2026, 1, 1, tzinfo=UTC))
        )
    claimed = job_store.claim(world.factory, "w-m5g", kinds={"run_review"})
    assert claimed is not None and claimed.id == world.job_id
    return claimed


def test_an_identical_stored_row_replays_with_its_original_audit_fields(
    done: pw.ReviewWorld,
) -> None:
    output = _stored_output(done)
    before = _row(done)
    claimed = _running_again(done)
    assert claimed.attempt == before["job_attempt"] + 1
    # Running with a present output is inconsistent: never readable as completed (F4).
    with pytest.raises(ReviewOutputRecordInconsistentError):
        load_review_status(done.factory, _reader(done), done.review_id)
    with job_store.fenced_transaction(done.factory, claimed.lease_token()) as fence:
        written = write_review_output(fence, output)
    assert written.replayed is True
    assert written.stored.job_attempt == before["job_attempt"]
    assert written.stored.created_at == before["created_at"]
    assert _row(done) == before  # nothing was written


def test_a_different_stored_row_is_a_conflict(done: pw.ReviewWorld) -> None:
    output = _stored_output(done)
    with done.engine.begin() as connection:
        connection.execute(update(ReviewOutputRow).values(markdown_bytes=output.markdown_bytes + 1))
    claimed = _running_again(done)
    with (
        pytest.raises(ReviewOutputConflictError),
        job_store.fenced_transaction(done.factory, claimed.lease_token()) as fence,
    ):
        write_review_output(fence, output)


def test_the_writer_refuses_a_fence_for_another_job_and_incomplete_stages(
    done: pw.ReviewWorld,
) -> None:
    output = _stored_output(done)
    with transaction(done.factory) as session:
        other = job_store.enqueue(session, done.actor, kind="run_review", idempotency_key="other")
    claimed = job_store.claim(done.factory, "w-m5g", kinds={"run_review"})
    assert claimed is not None and claimed.id == other.id
    with (
        pytest.raises(ReviewOutputFenceMismatchError),
        job_store.fenced_transaction(done.factory, claimed.lease_token()) as fence,
    ):
        write_review_output(fence, output)
    with done.engine.begin() as connection:
        connection.execute(delete(ReviewOutputRow))
        connection.execute(delete(ReviewStageResult).where(ReviewStageResult.stage == "analysis"))
    again = _running_again(done)
    with (
        pytest.raises(ReviewOutputIncompleteError),
        job_store.fenced_transaction(done.factory, again.lease_token()) as fence,
    ):
        write_review_output(fence, output)


# --- reads: the shared lifecycle/presence table (F4) and tampering --------------------------------


def _job_status(world: pw.ReviewWorld, status: str) -> None:
    finished = None if status in ("queued", "running") else datetime(2026, 11, 6, tzinfo=UTC)
    values: dict[str, Any] = {"status": status, "finished_at": finished}
    if status == "running":
        values.update(locked_by="w-m5g", lease_expires_at=datetime(2099, 1, 1, tzinfo=UTC))
    else:
        values.update(locked_by=None, lease_expires_at=None)
    with world.engine.begin() as connection:
        connection.execute(update(Job).where(Job.id == world.job_id).values(**values))


LOADERS: list[Callable[..., Any]] = [load_review_output, load_review_status]


@pytest.mark.parametrize("status", ["queued", "running", "failed", "dead"])
def test_a_present_output_with_a_job_that_has_not_succeeded_is_inconsistent(
    done: pw.ReviewWorld, status: str
) -> None:
    _job_status(done, status)
    for load in (*LOADERS, load_trusted_review_output):
        with pytest.raises(ReviewOutputRecordInconsistentError):
            load(done.factory, _reader(done), done.review_id)


@pytest.mark.parametrize(
    ("status", "projected"),
    [
        ("queued", ReviewStatus.QUEUED),
        ("running", ReviewStatus.RUNNING),
        ("failed", ReviewStatus.FAILED),
        ("dead", ReviewStatus.FAILED),
        ("succeeded", None),
    ],
)
def test_an_absent_output_follows_the_shared_table(
    done: pw.ReviewWorld, status: str, projected: ReviewStatus | None
) -> None:
    with done.engine.begin() as connection:
        connection.execute(delete(ReviewOutputRow))
    _job_status(done, status)
    reader = _reader(done)
    if projected is None:  # success without an output
        for load in (*LOADERS, load_trusted_review_output):
            with pytest.raises(ReviewOutputRecordInconsistentError):
                load(done.factory, reader, done.review_id)
        return
    assert load_review_status(done.factory, reader, done.review_id) is projected
    for output_loader in (load_review_output, load_trusted_review_output):
        with pytest.raises(ReviewOutputNotFoundError):
            output_loader(done.factory, reader, done.review_id)


def test_tenants_are_isolated_and_a_missing_review_is_not_found(done: pw.ReviewWorld) -> None:
    other = pw.tenant(done.engine, "m5g-other")
    for load in (*LOADERS, load_trusted_review_output):
        with pytest.raises(ReviewNotFoundError):
            load(done.factory, other, done.review_id)
        with pytest.raises(ReviewNotFoundError):
            load(done.factory, _reader(done), uuid4())


@pytest.mark.parametrize(
    "values",
    [
        {"finding_count": 4},
        {"legacy_sha256": "0" * 64},
        {"wrapper_sha256": "0" * 64},
        {"job_attempt": 3},  # later than the job's attempt
    ],
)
def test_tampered_output_rows_are_inconsistent(
    done: pw.ReviewWorld, values: dict[str, Any]
) -> None:
    with done.engine.begin() as connection:
        connection.execute(update(ReviewOutputRow).values(**values))
    with pytest.raises(ReviewOutputRecordInconsistentError):
        load_review_output(done.factory, _reader(done), done.review_id)


def test_a_non_canonical_job_is_inconsistent(done: pw.ReviewWorld) -> None:
    with done.engine.begin() as connection:
        connection.execute(update(Job).where(Job.id == done.job_id).values(max_attempts=5))
    for load in LOADERS:
        with pytest.raises(ReviewOutputRecordInconsistentError):
            load(done.factory, _reader(done), done.review_id)


def test_markdown_drift_is_reported_and_the_row_is_unchanged(done: pw.ReviewWorld) -> None:
    with done.engine.begin() as connection:
        connection.execute(update(ReviewOutputRow).values(markdown_sha256="0" * 64))
    before = _row(done)
    with pytest.raises(ReviewRendererDriftError):
        load_trusted_review_output(done.factory, _reader(done), done.review_id)
    assert _row(done) == before
    # The strict loader itself does not render: the stored metadata is decoded as stored.
    assert load_review_output(
        done.factory, _reader(done), done.review_id
    ).output.markdown_sha256 == ("0" * 64)
