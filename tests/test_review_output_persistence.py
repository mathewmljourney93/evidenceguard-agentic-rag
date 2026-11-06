"""The real M5g persistence boundaries over scripted sessions (no database; ADR-0025).

Every test calls the actual ``write_review_output``, ``load_review_output``,
``load_review_status`` or ``load_trusted_review_output``. Only the SQLAlchemy session is
replaced: a scripted session answers each statement by the table it names, with rows built from
a real M5f wrapper, and can raise at a named point (session construction, ``execute``, result
consumption, row attribute access, ``rollback`` or ``close``). The production read boundary
(``read_snapshot``, the recording session and result wrappers) and the writer's real fence
(``Fence``/``FencedSession`` and ``recheck_ownership``) run unchanged. This is not PostgreSQL
evidence: SQL is matched by text, never executed.
"""

from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_domain.jobs import JobSnapshot, LeaseLostError
from evidenceguard_domain.review_outputs import ReviewOutput, ReviewStatus, StoredReviewOutput
from evidenceguard_domain.reviews import ReviewNotFoundError
from evidenceguard_persistence.jobs import Fence, FenceClosedError, JobLockTimeoutError
from evidenceguard_persistence.review_outputs import (
    ReviewOutputBindingError,
    ReviewOutputConflictError,
    ReviewOutputDatabaseError,
    ReviewOutputFenceMismatchError,
    ReviewOutputIncompleteError,
    ReviewOutputNotFoundError,
    ReviewOutputRecordInconsistentError,
    load_review_output,
    load_review_status,
    write_review_output,
)
from evidenceguard_worker import review as worker
from evidenceguard_worker.review import load_trusted_review_output

if TYPE_CHECKING:
    import test_review_output_values as values
    import test_review_stage_values as old
else:
    from tests import test_review_output_values as values
    from tests import test_review_stage_values as old

T = values.T
SENTINEL = "SELECT secret FROM vendor_documents WHERE token = 'sentinel-p219'"
CONTROLS: tuple[type[BaseException], ...] = (KeyboardInterrupt, SystemExit, GeneratorExit)
READER = ActorContext(tenant_id=old.TENANT, actor_id=UUID(int=11), role=Role.REVIEWER)


# --- scripted rows and sessions ------------------------------------------------------------------


class Row:
    """A result row: attribute access and ``_mapping``; attribute access can be scripted."""

    def __init__(self, session: "Session", kind: str, data: dict[str, Any]) -> None:
        object.__setattr__(self, "_session", session)
        object.__setattr__(self, "_kind", kind)
        object.__setattr__(self, "_data", data)

    @property
    def _mapping(self) -> dict[str, Any]:
        return dict(self._data)

    def __getattr__(self, name: str) -> Any:
        self._session.hit(f"row:{self._kind}")
        try:
            return self._data[name]
        except KeyError:
            raise AttributeError(name) from None


class Result:
    def __init__(self, session: "Session", kind: str, rows: list[Row], scalar: Any = None):
        self.session, self.kind, self.rows, self.scalar = session, kind, rows, scalar

    def first(self) -> Row | None:
        self.session.hit(f"consume:{self.kind}")
        return self.rows[0] if self.rows else None

    def scalar_one(self) -> Any:
        self.session.hit(f"consume:{self.kind}")
        return self.scalar

    def __iter__(self) -> Iterator[Row]:
        self.session.hit(f"consume:{self.kind}")
        return iter(self.rows)


def kind_of(sql: str) -> str:
    for marker, kind in (
        ("INSERT INTO review_outputs", "insert"),
        ("FROM jobs", "job"),
        ("FROM review_outputs", "output"),
        ("FROM review_plan_questions", "plans"),
        ("FROM review_stage_results", "stages"),
        ("FROM reviews", "review"),
        ("clock_timestamp", "clock"),
        ("SET ", "set"),
    ):
        if marker in sql:
            return kind
    raise AssertionError(f"unexpected statement: {sql}")


class Session:
    """A scripted session. ``faults`` maps an event to the exception raised at its first hit."""

    def __init__(self, world: "World") -> None:
        self.world = world
        self.calls: list[str] = []

    def hit(self, event: str) -> None:
        self.world.events.append(event)
        error = self.world.faults.pop(event, None)
        if error is not None:
            raise error

    def execute(self, statement: Any, params: Any = None) -> Result:
        sql = str(statement)
        kind = kind_of(sql)
        self.calls.append(kind)
        self.world.statements.append(sql)
        self.hit(f"execute:{kind}")
        return self.world.answer(self, kind)

    def commit(self) -> None:  # never called by the code under test
        self.calls.append("commit")

    def rollback(self) -> None:
        self.calls.append("rollback")
        self.hit("rollback")

    def close(self) -> None:
        self.calls.append("close")
        self.hit("close")


def plan_rows(output: ReviewOutput) -> list[dict[str, Any]]:
    return [
        {
            "position": q.position,
            "question_id": q.question_id,
            "question_sha256": q.plan_question_sha256,
            "job_id": output.job_id,
        }
        for q in output.content.questions
    ]


def stage_rows(output: ReviewOutput) -> list[dict[str, Any]]:
    rows = []
    for q in output.content.questions:
        for name, stage in (("verification", q.verification), ("analysis", q.analysis)):
            reason = stage.unresolved_reason
            rows.append(
                {
                    "question_id": q.question_id,
                    "stage": name,
                    "outcome": stage.outcome.value,
                    "unresolved_reason": None if reason is None else reason.value,
                    "request_sha256": stage.request_sha256,
                    "content_sha256": stage.content_sha256,
                    "evidence_sha256": stage.evidence_sha256,
                    "dependency_sha256": stage.dependency_sha256,
                    "job_id": output.job_id,
                }
            )
    return rows


class World:
    """The rows a completed review would have, and what each statement returns."""

    def __init__(self) -> None:
        self.output = values.output()
        o = self.output
        self.review: dict[str, Any] | None = {
            "tenant_id": o.tenant_id,
            "id": o.review_id,
            "run_review_job_id": o.job_id,
            "vendor_id": o.content.binding.vendor_id,
            "request_sha256": o.review_request_sha256,
            "snapshot_sha256": o.snapshot_sha256,
            "configuration_sha256": o.configuration_sha256,
        }
        self.job_row: dict[str, Any] | None = {
            "tenant_id": o.tenant_id,
            "id": o.job_id,
            "kind": "run_review",
            "idempotency_key": str(o.review_id),
            "payload": {"review_id": str(o.review_id)},
            "max_attempts": 3,
            "status": "succeeded",
            "attempt": 1,
        }
        self.stored: dict[str, Any] | None = values.row(o)
        self.plans = plan_rows(o)
        self.stage_rows = stage_rows(o)
        self.fence_job: JobSnapshot | None = None
        self.owner_rows: list[dict[str, Any]] = []  # one per ownership recheck, in order
        self.faults: dict[str, BaseException] = {}
        self.events: list[str] = []
        self.statements: list[str] = []
        self.sessions: list[Session] = []

    def factory(self) -> Session:
        self.events.append("factory")
        error = self.faults.pop("factory", None)
        if error is not None:
            raise error
        session = Session(self)
        self.sessions.append(session)
        return session

    def answer(self, session: Session, kind: str) -> Result:
        def rows(*items: dict[str, Any] | None) -> list[Row]:
            return [Row(session, kind, item) for item in items if item is not None]

        if kind == "clock":
            return Result(session, kind, [], T)
        if kind == "set":
            return Result(session, kind, [])
        if kind == "review":
            return Result(session, kind, rows(self.review))
        if kind == "job":
            if self.fence_job is not None:  # an ownership recheck inside the writer's fence
                data = self.owner_rows.pop(0) if self.owner_rows else self.owner()
                return Result(session, kind, rows(data))
            return Result(session, kind, rows(self.job_row))
        if kind == "output":
            return Result(session, kind, rows(self.stored))
        if kind == "plans":
            return Result(session, kind, rows(*self.plans))
        if kind == "stages":
            return Result(session, kind, rows(*self.stage_rows))
        assert kind == "insert"
        return Result(session, kind, [], T + timedelta(seconds=1))

    def owner(self, **changes: Any) -> dict[str, Any]:
        """The fenced job row with a fresh database time inside its lease."""
        job = self.fence_job
        assert job is not None
        data = {**job.model_dump(), "payload": job.payload.as_dict()}
        data["status"] = job.status.value
        data["db_now"] = T
        data.update(changes)
        return data

    def lost(self) -> dict[str, Any]:
        return self.owner(locked_by="worker-someone-else")

    def calls(self) -> list[str]:
        return [call for session in self.sessions for call in session.calls]


def fixed(error: BaseException, kind: type[BaseException]) -> None:
    assert type(error) is kind
    assert error.__cause__ is None and error.__context__ is None
    for text in (str(error), repr(error)):
        assert "sentinel" not in text and "SELECT" not in text


def no_writes(world: World) -> None:
    assert "commit" not in world.calls()
    assert not any(
        s.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for s in world.statements
    )


LOADERS: list[Callable[..., Any]] = [load_review_output, load_review_status]


# --- reads: results, precedence and the lifecycle/presence table ---------------------------------


def test_a_completed_review_reads_through_the_real_boundary_without_writing() -> None:
    world = World()
    stored = load_review_output(cast(Any, world.factory), READER, old.REVIEW)
    assert type(stored) is StoredReviewOutput and stored.output == world.output
    status = load_review_status(cast(Any, world.factory), READER, old.REVIEW)
    assert status is ReviewStatus.COMPLETED
    no_writes(world)
    assert all(s.calls[-2:] == ["rollback", "close"] for s in world.sessions)
    assert world.statements[0].startswith("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")


@pytest.mark.parametrize("load", LOADERS)
def test_a_missing_review_is_not_found_before_the_job_is_read(load: Any) -> None:
    world = World()
    world.review = None
    with pytest.raises(ReviewNotFoundError) as raised:
        load(world.factory, READER, old.REVIEW)
    assert raised.value.__cause__ is None and raised.value.__context__ is None
    assert "job" not in world.calls()


@pytest.mark.parametrize("load", LOADERS)
@pytest.mark.parametrize(
    "job",
    [
        None,
        {"max_attempts": 5},
        {"kind": "index_revision"},
        {"idempotency_key": "other"},
        {"payload": {"review_id": str(UUID(int=99))}},
        {"tenant_id": UUID(int=98)},
    ],
)
def test_a_missing_or_non_canonical_job_is_inconsistent_before_presence(
    load: Any, job: dict[str, Any] | None
) -> None:
    world = World()
    assert world.job_row is not None
    world.job_row = None if job is None else {**world.job_row, **job}
    world.stored = None  # absent + any status would otherwise be "not found"
    with pytest.raises(ReviewOutputRecordInconsistentError) as raised:
        load(world.factory, READER, old.REVIEW)
    fixed(raised.value, ReviewOutputRecordInconsistentError)


@pytest.mark.parametrize(
    ("present", "status", "output_error", "projected"),
    [
        (True, "succeeded", None, ReviewStatus.COMPLETED),
        (True, "queued", ReviewOutputRecordInconsistentError, None),
        (True, "running", ReviewOutputRecordInconsistentError, None),
        (True, "failed", ReviewOutputRecordInconsistentError, None),
        (True, "dead", ReviewOutputRecordInconsistentError, None),
        (False, "succeeded", ReviewOutputRecordInconsistentError, None),
        (False, "queued", ReviewOutputNotFoundError, ReviewStatus.QUEUED),
        (False, "running", ReviewOutputNotFoundError, ReviewStatus.RUNNING),
        (False, "failed", ReviewOutputNotFoundError, ReviewStatus.FAILED),
        (False, "dead", ReviewOutputNotFoundError, ReviewStatus.FAILED),
    ],
)
def test_every_lifecycle_presence_row_through_all_three_loaders(
    monkeypatch: pytest.MonkeyPatch,
    present: bool,
    status: str,
    output_error: type[Exception] | None,
    projected: ReviewStatus | None,
) -> None:
    renders: list[int] = []
    real = getattr(worker, "render_report_markdown")  # noqa: B009 - patched below

    def counting(content: Any) -> str:
        renders.append(1)
        return str(real(content))

    monkeypatch.setattr(worker, "render_report_markdown", counting)

    def world() -> World:
        built = World()
        assert built.job_row is not None
        built.job_row["status"] = status
        if not present:
            built.stored = None
        return built

    if projected is None:
        with pytest.raises(ReviewOutputRecordInconsistentError):
            load_review_status(cast(Any, world().factory), READER, old.REVIEW)
    else:
        assert load_review_status(cast(Any, world().factory), READER, old.REVIEW) is projected
    for loader in (load_review_output, load_trusted_review_output):
        if output_error is None:
            assert loader(cast(Any, world().factory), READER, old.REVIEW) is not None
        else:
            with pytest.raises(output_error) as raised:
                loader(cast(Any, world().factory), READER, old.REVIEW)
            fixed(raised.value, output_error)
    # The trusted reader renders only after the strict loader succeeded (F3 inherits F4).
    assert renders == ([1] if output_error is None else [])


@pytest.mark.parametrize(
    "tamper",
    [
        lambda w: w.stored.update(finding_count=w.stored["finding_count"] + 1),
        lambda w: w.stored.update(job_attempt=2),  # later than the job's attempt 1
        lambda w: w.review.update(request_sha256="0" * 64),
        lambda w: w.review.update(vendor_id=UUID(int=97)),
        lambda w: w.plans.reverse(),
        lambda w: w.stage_rows.pop(),
        lambda w: w.stage_rows[0].update(content_sha256="0" * 64),
        lambda w: w.stage_rows[0].update(job_id=UUID(int=96)),
    ],
)
def test_tampered_rows_are_inconsistent_through_the_real_loader(tamper: Any) -> None:
    world = World()
    tamper(world)
    with pytest.raises(ReviewOutputRecordInconsistentError) as raised:
        load_review_output(cast(Any, world.factory), READER, old.REVIEW)
    fixed(raised.value, ReviewOutputRecordInconsistentError)


# --- reads: ordinary failures and process control ----------------------------------------------


ORDINARY_POINTS = [
    "factory",
    "execute:set",
    "consume:clock",
    "execute:review",
    "consume:review",
    "row:review",
    "consume:job",
    "consume:output",
    "consume:plans",
    "consume:stages",
    "rollback",
    "close",
]


@pytest.mark.parametrize("load", LOADERS)
@pytest.mark.parametrize("point", ORDINARY_POINTS)
def test_ordinary_failures_anywhere_are_the_fixed_database_error(load: Any, point: str) -> None:
    world = World()
    world.faults[point] = OperationalError(SENTINEL, {"token": "sentinel"}, Exception(SENTINEL))
    expected_reached = load is load_review_output or point not in (
        "consume:plans",
        "consume:stages",
    )
    if not expected_reached:  # the status read never reads plans or stages
        assert load(world.factory, READER, old.REVIEW) is ReviewStatus.COMPLETED
        return
    with pytest.raises(ReviewOutputDatabaseError) as raised:
        load(world.factory, READER, old.REVIEW)
    fixed(raised.value, ReviewOutputDatabaseError)
    no_writes(world)
    if point != "factory":
        calls = world.calls()
        assert calls.count("close") == 1 and calls.count("rollback") == 1


INTERRUPT_POINTS = ["consume:clock", "consume:review", "consume:plans", "row:review", "row:job"]
LATER = {KeyboardInterrupt: SystemExit, SystemExit: GeneratorExit, GeneratorExit: KeyboardInterrupt}


@pytest.mark.parametrize("control", CONTROLS)
@pytest.mark.parametrize("point", INTERRUPT_POINTS)
@pytest.mark.parametrize("cleanup", ["clean", "ordinary", "later-interrupt"])
def test_the_first_interrupt_propagates_by_identity_whatever_cleanup_does(
    control: type[BaseException], point: str, cleanup: str
) -> None:
    world = World()
    first = control()
    world.faults[point] = first
    if cleanup == "ordinary":
        world.faults["rollback"] = OperationalError(SENTINEL, {}, Exception(SENTINEL))
    elif cleanup == "later-interrupt":
        world.faults["close"] = LATER[control]()
    with pytest.raises(BaseException) as raised:
        load_review_output(cast(Any, world.factory), READER, old.REVIEW)
    assert raised.value is first
    no_writes(world)
    assert world.calls().count("close") == 1  # cleanup still ran once


@pytest.mark.parametrize("control", CONTROLS)
def test_an_interrupt_during_session_construction_propagates_unchanged(
    control: type[BaseException],
) -> None:
    world = World()
    first = control()
    world.faults["factory"] = first
    for load in LOADERS:
        with pytest.raises(BaseException) as raised:
            load(world.factory, READER, old.REVIEW)
        assert raised.value is first
        world.faults["factory"] = first
    assert world.sessions == []


# --- the writer ----------------------------------------------------------------------------------


def fenced(world: World, *, attempt: int = 1) -> Fence:
    """The real M3 ``Fence`` (and ``FencedSession``) over a scripted session for a running job."""
    job = values._job().model_copy(update={"attempt": attempt})
    world.fence_job = job
    world.job_row = None  # the fence's rechecks answer from ``owner_rows``
    session = world.factory()
    return Fence(cast(Any, session), job.lease_token(), job)


def write(world: World, fence: Fence, output: ReviewOutput | None = None) -> Any:
    return write_review_output(cast(Any, fence), output or world.output)


def test_a_valid_write_inserts_once_rechecks_twice_and_never_ends_the_transaction() -> None:
    world = World()
    world.stored = None
    fence = fenced(world, attempt=2)
    written = write(world, fence)
    assert written.replayed is False and written.stored.job_attempt == 2
    assert world.calls() == ["job", "review", "plans", "stages", "output", "insert", "job"]
    assert not {"commit", "rollback", "close"} & set(world.calls())


def test_an_identical_stored_row_replays_with_its_audit_fields_and_no_insert() -> None:
    world = World()  # stored job_attempt 1 and created_at T
    written = write(world, fenced(world, attempt=3))
    assert written.replayed is True
    assert (written.stored.job_attempt, written.stored.created_at) == (1, T)
    assert "insert" not in world.calls() and world.calls().count("job") == 2


def test_a_different_stored_row_conflicts() -> None:
    world = World()
    assert world.stored is not None
    world.stored["markdown_bytes"] += 1
    with pytest.raises(ReviewOutputConflictError) as raised:
        write(world, fenced(world))
    fixed(raised.value, ReviewOutputConflictError)
    assert "insert" not in world.calls()


@pytest.mark.parametrize(
    "tamper",
    [
        lambda w: w.review.update(request_sha256="0" * 64),
        lambda w: w.review.update(snapshot_sha256="0" * 64),
        lambda w: w.review.update(configuration_sha256="0" * 64),
        lambda w: w.review.update(vendor_id=UUID(int=95)),
        lambda w: w.plans.reverse(),
        lambda w: w.plans[0].update(question_sha256="0" * 64),
    ],
)
def test_a_binding_mismatch_is_refused_before_completeness_and_replay(tamper: Any) -> None:
    world = World()
    tamper(world)
    world.stage_rows.pop()  # also incomplete
    assert world.stored is not None
    world.stored["markdown_bytes"] += 1  # and a conflicting stored row
    with pytest.raises(ReviewOutputBindingError) as raised:
        write(world, fenced(world))
    fixed(raised.value, ReviewOutputBindingError)
    assert "stages" not in world.calls() and "output" not in world.calls()


def test_a_valid_binding_with_incomplete_stages_is_incomplete_before_replay() -> None:
    world = World()
    world.stage_rows.pop()
    assert world.stored is not None
    world.stored["markdown_bytes"] += 1  # a conflict would be reported only after completeness
    with pytest.raises(ReviewOutputIncompleteError) as raised:
        write(world, fenced(world))
    fixed(raised.value, ReviewOutputIncompleteError)
    assert "output" not in world.calls()


def test_a_fence_for_another_job_is_refused_before_binding() -> None:
    world = World()
    assert world.review is not None
    world.review["run_review_job_id"] = UUID(int=94)
    world.review["request_sha256"] = "0" * 64
    with pytest.raises(ReviewOutputFenceMismatchError):
        write(world, fenced(world))


@pytest.mark.parametrize("path", ["insert", "replay"])
def test_ownership_lost_at_the_final_recheck_raises_lease_lost(path: str) -> None:
    world = World()
    if path == "insert":
        world.stored = None
    fence = fenced(world)
    world.owner_rows = [world.owner(), world.lost()]  # entry holds, final check lost
    with pytest.raises(LeaseLostError):
        write(world, fence)
    assert world.calls()[-1] == "job"  # the final recheck was the last statement
    assert ("insert" in world.calls()) is (path == "insert")
    assert not {"commit", "rollback", "close"} & set(world.calls())


def test_ownership_lost_at_entry_writes_nothing() -> None:
    world = World()
    fence = fenced(world)
    world.owner_rows = [world.lost()]
    with pytest.raises(LeaseLostError):
        write(world, fence)
    assert world.calls() == ["job"]


@pytest.mark.parametrize(
    ("event", "error"),
    [
        ("execute:review", LeaseLostError()),
        ("execute:insert", FenceClosedError()),
        ("execute:stages", JobLockTimeoutError()),
    ],
)
def test_lease_fence_and_lock_errors_pass_through_as_the_same_objects(
    event: str, error: Exception
) -> None:
    world = World()
    world.stored = None
    fence = fenced(world)
    world.faults[event] = error
    with pytest.raises(type(error)) as raised:
        write(world, fence)
    assert raised.value is error


def test_a_closed_fence_refuses_before_any_statement() -> None:
    world = World()
    fence = fenced(world)
    fence._close()
    with pytest.raises(FenceClosedError):
        write(world, fence)
    assert world.calls() == []


class _Diagnostics(Exception):
    def __init__(self, sqlstate: str) -> None:
        super().__init__(SENTINEL)
        self.sqlstate = sqlstate


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            IntegrityError(SENTINEL, {"t": "sentinel"}, _Diagnostics("23505")),
            ReviewOutputConflictError,
        ),
        (IntegrityError(SENTINEL, {}, _Diagnostics("23503")), ReviewOutputDatabaseError),
        (OperationalError(SENTINEL, {}, _Diagnostics("57014")), ReviewOutputDatabaseError),
        (RuntimeError(SENTINEL), ReviewOutputDatabaseError),
    ],
)
def test_only_a_unique_violation_is_a_conflict(error: Exception, expected: type[Exception]) -> None:
    world = World()
    world.stored = None
    fence = fenced(world)
    world.faults["execute:insert"] = error
    with pytest.raises(expected) as raised:
        write(world, fence)
    fixed(raised.value, expected)
    assert world.calls().count("insert") == 1  # never retried
    assert not {"commit", "rollback", "close"} & set(world.calls())


@pytest.mark.parametrize("control", CONTROLS)
def test_process_control_in_the_writer_is_the_same_object(control: type[BaseException]) -> None:
    world = World()
    world.stored = None
    fence = fenced(world)
    first = control()
    world.faults["consume:plans"] = first
    with pytest.raises(BaseException) as raised:
        write(world, fence)
    assert raised.value is first
