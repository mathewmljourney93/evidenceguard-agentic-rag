"""The ``ingest_revision`` handler's branch table with scripted doubles (M3d, ADR-0010).

A fake ``JobContext`` records every fenced block (open, commit or rollback) and every
``check()``; the persistence functions the handler calls are replaced with recorders. The tests
check the accepted protocol: the status read, the settled and failed branches, parsing outside
every fence, the write order, the bound completeness callback, the two-transaction permanent
failure, the refusal re-read, and that cancellation, lease loss and uncertain commits propagate
untouched. Real PostgreSQL execution is in ``test_ingestion_postgres.py`` (CI only).
"""

import functools
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError

from evidenceguard_domain.chunks import Chunk, ExpectedChunkSet
from evidenceguard_domain.jobs import (
    JobErrorCode,
    JobPayload,
    JobSnapshot,
    JobStatus,
    LeaseLostError,
)
from evidenceguard_domain.revisions import (
    InvalidRevisionContentError,
    InvalidRevisionTransitionError,
    MediaType,
    RevisionContent,
    RevisionFailureCode,
    RevisionSnapshot,
    RevisionStatus,
)
from evidenceguard_persistence import chunks as chunk_store
from evidenceguard_persistence import documents as revision_store
from evidenceguard_persistence.chunks import RevisionSource
from evidenceguard_persistence.jobs import FencedSession, JobLockTimeoutError
from evidenceguard_retrieval import chunking
from evidenceguard_worker import ingest
from evidenceguard_worker.context import (
    HandlerFence,
    JobCancelledError,
    JobContext,
    PermanentJobError,
    RetryableJobError,
)

T0 = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
TENANT = UUID("66666666-6666-4666-8666-666666666666")
REVISION = UUID("22222222-2222-4222-8222-222222222222")
TEXT = "# Retention\n\nCustomer data is kept for 90 days.\n\n## Backups\n\nEncrypted.\n"


class CommitFailed(SQLAlchemyError):
    """Stands in for a failed COMMIT or a lost commit acknowledgment."""


def _job(payload: dict[str, str] | None = None) -> JobSnapshot:
    return JobSnapshot(
        id=uuid4(),
        tenant_id=TENANT,
        kind=ingest.INGEST_REVISION_KIND,
        idempotency_key=str(REVISION),
        payload=JobPayload.from_mapping(
            payload if payload is not None else {"revision_id": str(REVISION)}
        ),
        status=JobStatus.RUNNING,
        attempt=1,
        max_attempts=3,
        run_after=T0,
        locked_by="worker-test",
        lease_expires_at=T0 + timedelta(seconds=60),
        created_at=T0,
        updated_at=T0,
    )


def _processing_revision() -> RevisionSnapshot:
    return RevisionSnapshot(
        id=REVISION,
        tenant_id=TENANT,
        document_id=uuid4(),
        revision_no=1,
        status=RevisionStatus.PROCESSING,
        sha256="a" * 64,
        media_type=MediaType.TEXT_MARKDOWN,
        byte_size=10,
        created_at=T0,
        updated_at=T0,
    )


@dataclass
class Script:
    """What the doubles answer, and everything they saw."""

    statuses: list[RevisionStatus] = field(default_factory=lambda: [RevisionStatus.PENDING])
    text: str = TEXT
    events: list[str] = field(default_factory=list)
    in_fence: bool = False
    fail_codes: list[RevisionFailureCode] = field(default_factory=list)
    batches: list[tuple[Chunk, ...]] = field(default_factory=list)
    before_settle: Any = None
    errors: dict[str, BaseException] = field(default_factory=dict)
    commit_error_on_finish: BaseException | None = None
    cancel_on_check: int | None = None
    checks: int = 0
    parsed: int = 0

    def raise_for(self, name: str) -> None:
        error = self.errors.pop(name, None)
        if error is not None:
            raise error


class FakeContext:
    def __init__(self, script: Script, job: JobSnapshot) -> None:
        self._script = script
        self.job = job

    def check(self) -> None:
        self._script.checks += 1
        self._script.events.append("check")
        if self._script.cancel_on_check == self._script.checks:
            raise JobCancelledError()

    @contextmanager
    def fenced(self, *, finish: bool = False) -> Iterator[HandlerFence]:
        script = self._script
        self.check()
        script.events.append("open_finish" if finish else "open")
        script.in_fence = True
        try:
            yield HandlerFence(cast(FencedSession, object()), self.job)
        except BaseException:
            script.events.append("rollback")
            raise
        finally:
            script.in_fence = False
        if finish and script.commit_error_on_finish is not None:
            script.events.append("commit_failed")
            raise script.commit_error_on_finish
        script.events.append("commit")


@pytest.fixture
def script(monkeypatch: pytest.MonkeyPatch) -> Script:
    s = Script()

    def read_status(session: Any, job: JobSnapshot) -> RevisionStatus:
        assert s.in_fence
        s.events.append("read_status")
        s.raise_for("read_status")
        return s.statuses.pop(0) if len(s.statuses) > 1 else s.statuses[0]

    def start(session: Any, job: JobSnapshot) -> None:
        s.events.append("start_processing")
        s.raise_for("start_processing")

    def load(session: Any, job: JobSnapshot) -> RevisionSource:
        s.events.append("load_source")
        s.raise_for("load_source")
        content = RevisionContent.from_bytes(s.text.encode(), "text/markdown")
        return RevisionSource(
            revision_id=REVISION, status=RevisionStatus.PROCESSING, content=content
        )

    def write_set(session: Any, job: JobSnapshot, expected: ExpectedChunkSet) -> None:
        assert s.in_fence
        s.events.append("write_set")
        s.raise_for("write_set")

    def write_chunks(session: Any, job: JobSnapshot, batch: tuple[Chunk, ...]) -> None:
        assert s.in_fence
        s.events.append("write_chunks")
        s.raise_for("write_chunks")
        s.batches.append(batch)

    def activate(session: Any, job: JobSnapshot, *, before_settle: Any = None) -> None:
        assert s.in_fence
        s.events.append("activate" if before_settle else "activate_duplicate")
        s.before_settle = before_settle
        s.raise_for("activate")
        if before_settle is not None:
            before_settle(session, _processing_revision())

    def fail(session: Any, job: JobSnapshot, code: RevisionFailureCode) -> None:
        assert s.in_fence
        s.events.append("fail_revision")
        s.raise_for("fail_revision")
        s.fail_codes.append(code)

    def require(session: Any, revision: Any, *, expected: ExpectedChunkSet) -> None:
        s.events.append("require_complete")
        s.raise_for("require_complete")

    real_chunk_revision = chunking.chunk_revision

    def parse(content: RevisionContent, **kwargs: Any) -> tuple[Chunk, ...]:
        assert not s.in_fence, "parsing must happen outside every transaction"
        s.events.append("parse")
        s.parsed += 1
        s.raise_for("parse")
        return real_chunk_revision(content, **kwargs)

    monkeypatch.setattr(chunk_store, "read_revision_status", read_status)
    monkeypatch.setattr(chunk_store, "load_revision_source", load)
    monkeypatch.setattr(chunk_store, "write_chunk_set", write_set)
    monkeypatch.setattr(chunk_store, "write_chunks", write_chunks)
    monkeypatch.setattr(chunk_store, "require_complete_chunk_set", require)
    monkeypatch.setattr(revision_store, "start_processing", start)
    monkeypatch.setattr(revision_store, "activate_revision", activate)
    monkeypatch.setattr(revision_store, "fail_revision", fail)
    monkeypatch.setattr(chunking, "chunk_revision", parse)
    return s


def _run(script: Script, job: JobSnapshot | None = None) -> None:
    ingest.ingest_revision(cast(JobContext, FakeContext(script, job or _job())))


def _calls(script: Script) -> list[str]:
    return [event for event in script.events if event != "check"]


# --- the happy path --------------------------------------------------------------------------


def test_a_pending_revision_is_parsed_written_and_activated_in_order(script: Script) -> None:
    _run(script)

    assert _calls(script) == [
        "open",
        "read_status",
        "start_processing",
        "load_source",
        "commit",
        "parse",
        "open",
        "write_set",
        "commit",
        "open",
        "write_chunks",
        "commit",
        "open_finish",
        "activate",
        "require_complete",
        "commit",
    ]
    assert script.fail_codes == []


def test_parsing_is_bracketed_by_checks_and_every_write_by_a_check(script: Script) -> None:
    _run(script)
    events = script.events
    parse = events.index("parse")
    assert events[parse - 1] == "check" and events[parse + 1] == "check"
    for index, event in enumerate(events):
        if event in ("open", "open_finish"):
            assert events[index - 1] == "check"


def test_the_finish_is_bound_to_this_attempts_expected_set(script: Script) -> None:
    _run(script)

    content = RevisionContent.from_bytes(TEXT.encode(), "text/markdown")
    chunks = chunking.chunk_revision(content, tenant_id=TENANT, revision_id=REVISION)
    callback = script.before_settle
    assert isinstance(callback, functools.partial)
    assert callback.func is chunk_store.require_complete_chunk_set
    assert callback.keywords == {"expected": ExpectedChunkSet.of(chunks)}
    assert [chunk for batch in script.batches for chunk in batch] == list(chunks)


def test_many_chunks_are_written_in_bounded_batches_with_a_check_before_each(
    script: Script,
) -> None:
    script.text = "".join(f"# H{index}\n\nP{index}\n\n" for index in range(450))
    _run(script)

    assert [len(batch) for batch in script.batches] == [200, 200, 50]
    assert _calls(script).count("write_chunks") == 3


def test_a_processing_revision_resumes_with_the_same_writes(script: Script) -> None:
    script.statuses = [RevisionStatus.PROCESSING]
    _run(script)
    assert "start_processing" in script.events and "activate" in script.events


# --- settled and failed branches -------------------------------------------------------------


def test_an_already_failed_revision_fails_the_job_without_parsing(script: Script) -> None:
    """The permanent-failure crash gap: the revision failure committed, the job did not."""
    script.statuses = [RevisionStatus.FAILED]

    with pytest.raises(PermanentJobError) as info:
        _run(script)

    assert info.value.code is JobErrorCode.PERMANENT_FAILURE
    assert _calls(script) == ["open", "read_status", "commit"]
    assert script.parsed == 0 and script.fail_codes == []


@pytest.mark.parametrize("status", [RevisionStatus.ACTIVE, RevisionStatus.SUPERSEDED])
def test_a_settled_revision_completes_as_a_duplicate_without_parsing(
    script: Script, status: RevisionStatus
) -> None:
    script.statuses = [status]

    _run(script)

    assert _calls(script) == [
        "open",
        "read_status",
        "commit",
        "open_finish",
        "activate_duplicate",
        "commit",
    ]
    assert script.parsed == 0


@pytest.mark.parametrize(
    ("fresh", "expected_tail"),
    [
        (RevisionStatus.FAILED, ["open", "read_status", "commit"]),
        (
            RevisionStatus.ACTIVE,
            ["open", "read_status", "commit", "open_finish", "activate_duplicate", "commit"],
        ),
    ],
)
@pytest.mark.parametrize("refused_at", ["write_set", "write_chunks"])
def test_a_refused_write_rereads_the_status_and_never_fails_the_revision(
    script: Script, fresh: RevisionStatus, expected_tail: list[str], refused_at: str
) -> None:
    script.statuses = [RevisionStatus.PENDING, fresh]
    script.errors[refused_at] = chunk_store.ChunkWriteRefusedError()

    if fresh is RevisionStatus.FAILED:
        with pytest.raises(PermanentJobError):
            _run(script)
    else:
        _run(script)

    calls = _calls(script)
    refused = calls.index(refused_at)
    assert calls[refused + 1] == "rollback"
    assert calls[refused + 2 :] == expected_tail
    assert "fail_revision" not in calls and "activate" not in calls


def test_a_refused_activation_rereads_the_status(script: Script) -> None:
    """A revision failed by another job before this activation: settle refuses it."""
    script.statuses = [RevisionStatus.PENDING, RevisionStatus.FAILED]
    script.errors["activate"] = InvalidRevisionTransitionError()

    with pytest.raises(PermanentJobError):
        _run(script)
    assert _calls(script)[-3:] == ["open", "read_status", "commit"]


def test_a_failure_racing_a_settlement_rereads_instead_of_failing_again(script: Script) -> None:
    script.text = "   \n\t\n"  # empty: the handler tries to fail the revision
    script.statuses = [RevisionStatus.PENDING, RevisionStatus.ACTIVE]
    script.errors["fail_revision"] = InvalidRevisionTransitionError()

    _run(script)

    calls = _calls(script)
    assert calls.count("fail_revision") == 1
    assert calls[calls.index("fail_revision") + 1] == "rollback"
    assert calls[-3:] == ["open_finish", "activate_duplicate", "commit"]


def test_a_fresh_read_that_still_says_processing_is_retried_not_guessed(script: Script) -> None:
    script.statuses = [RevisionStatus.PENDING, RevisionStatus.PROCESSING]
    script.errors["write_chunks"] = chunk_store.ChunkWriteRefusedError()
    with pytest.raises(RetryableJobError) as info:
        _run(script)
    assert info.value.code is JobErrorCode.RETRYABLE_FAILURE


# --- permanent failures: two transactions --------------------------------------------------------


@pytest.mark.parametrize(
    ("setup", "code"),
    [
        ({"text": "  \n\t\n"}, RevisionFailureCode.EMPTY_DOCUMENT),
        ({"parse": chunking.ChunkLimitExceededError()}, RevisionFailureCode.CHUNK_LIMIT_EXCEEDED),
        ({"parse": RuntimeError("parser bug")}, RevisionFailureCode.INGESTION_FAILED),
        (
            {"load_source": InvalidRevisionContentError()},
            RevisionFailureCode.CONTENT_INTEGRITY_FAILED,
        ),
        ({"write_chunks": chunk_store.ChunkConflictError()}, RevisionFailureCode.CHUNK_CONFLICT),
        ({"write_set": chunk_store.ChunkConflictError()}, RevisionFailureCode.CHUNK_CONFLICT),
    ],
)
def test_permanent_failures_commit_the_revision_failure_before_failing_the_job(
    script: Script, setup: dict[str, Any], code: RevisionFailureCode
) -> None:
    if "text" in setup:
        script.text = setup["text"]
    else:
        script.errors.update(setup)

    with pytest.raises(PermanentJobError) as info:
        _run(script)

    assert info.value.code is JobErrorCode.PERMANENT_FAILURE
    assert script.fail_codes == [code]
    calls = _calls(script)
    assert calls[-3:] == ["open", "fail_revision", "commit"]  # committed, then raised outside
    assert "activate" not in calls


def test_an_integrity_failure_rolls_back_start_processing_first(script: Script) -> None:
    script.errors["load_source"] = InvalidRevisionContentError()
    with pytest.raises(PermanentJobError):
        _run(script)
    assert _calls(script) == [
        "open",
        "read_status",
        "start_processing",
        "load_source",
        "rollback",
        "open",
        "fail_revision",
        "commit",
    ]


# --- retryable and propagated outcomes ------------------------------------------------------------


def test_an_incomplete_or_different_set_at_activation_is_retryable(script: Script) -> None:
    script.errors["require_complete"] = chunk_store.ChunkSetIncompleteError()

    with pytest.raises(RetryableJobError) as info:
        _run(script)

    assert info.value.code is JobErrorCode.RETRYABLE_FAILURE
    assert _calls(script)[-2:] == ["require_complete", "rollback"]
    assert script.fail_codes == []


def test_a_lock_timeout_is_retryable(script: Script) -> None:
    script.errors["write_set"] = JobLockTimeoutError()
    with pytest.raises(RetryableJobError):
        _run(script)


@pytest.mark.parametrize(
    "payload",
    [{}, {"revision_id": str(REVISION), "other_id": str(uuid4())}, {"document_id": str(REVISION)}],
)
def test_an_invalid_payload_fails_permanently_before_any_fence(
    script: Script, payload: dict[str, str]
) -> None:
    with pytest.raises(PermanentJobError):
        _run(script, _job(payload))
    assert script.events == []


def test_a_revision_missing_from_the_tenant_fails_permanently(script: Script) -> None:
    script.errors["read_status"] = revision_store.RevisionNotFoundError()
    with pytest.raises(PermanentJobError):
        _run(script)
    assert script.parsed == 0 and script.fail_codes == []


def test_cancellation_between_batches_propagates_and_never_activates(script: Script) -> None:
    script.text = "".join(f"# H{index}\n\nP{index}\n\n" for index in range(250))
    # Checks: status-block open (1), before parse (2), after parse (3), before the set (4),
    # its fence (5), before batch 1 (6), its fence (7), before batch 2 (8).
    script.cancel_on_check = 8

    with pytest.raises(JobCancelledError):
        _run(script)

    calls = _calls(script)
    assert calls.count("write_chunks") == 1 and "activate" not in calls
    assert script.fail_codes == []


def test_lease_loss_propagates_untouched(script: Script) -> None:
    script.errors["write_chunks"] = LeaseLostError()
    with pytest.raises(LeaseLostError):
        _run(script)
    assert script.fail_codes == []


def test_an_uncertain_finish_propagates_and_both_outcomes_recover(script: Script) -> None:
    """A lost acknowledgment is never converted: the runtime treats it as uncertain."""
    failure = CommitFailed("lost acknowledgment")
    script.commit_error_on_finish = failure
    with pytest.raises(CommitFailed) as info:
        _run(script)
    assert info.value is failure

    # It did not commit: the next attempt finds the revision processing and finishes once.
    _next_attempt(script, RevisionStatus.PROCESSING)
    _run(script)
    assert _calls(script).count("activate") == 1

    # It did commit: a duplicate job finds the revision active and never parses.
    _next_attempt(script, RevisionStatus.ACTIVE)
    _run(script)
    assert script.parsed == 0 and "activate_duplicate" in script.events


def _next_attempt(script: Script, status: RevisionStatus) -> None:
    """Reset the recorders in place (the doubles are bound to this ``Script``)."""
    script.statuses = [status]
    script.events.clear()
    script.batches.clear()
    script.fail_codes.clear()
    script.errors.clear()
    script.commit_error_on_finish = None
    script.parsed = script.checks = 0
