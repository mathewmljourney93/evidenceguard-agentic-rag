"""The M4c enqueue/backfill seams and handler reads (``evidenceguard_persistence.indexing``),
without a database (ADR-0015).

M4b's ``ensure_profile``/``create_index`` and M3a's ``enqueue`` are replaced by recorders, and
a session-factory double stands in for transactions. These are **protocol** tests: input
validation before any transaction, the observed outcomes, per-item rollback and propagation,
cursor semantics, and statement scoping. Atomicity, concurrency and constraints are covered by
``test_indexing_postgres.py`` against a real database (CI only).
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import postgresql

from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_domain.embedding_storage import index_id, profile_id
from evidenceguard_domain.embeddings import EmbeddingIdentity, InvalidEmbeddingError
from evidenceguard_domain.errors import PermissionDeniedError
from evidenceguard_domain.jobs import (
    JobIdempotencyConflictError,
    JobPayload,
    JobSnapshot,
    JobStatus,
)
from evidenceguard_persistence import embeddings as embedding_store
from evidenceguard_persistence import indexing
from evidenceguard_persistence.embeddings import (
    EmbeddingProfileConflictError,
    IndexConflictError,
    IndexJobMismatchError,
    IndexNotFoundError,
    IndexSnapshot,
    IndexSourceNotEligibleError,
    ProfileSnapshot,
)
from evidenceguard_persistence.indexing import (
    BackfillOutcome,
    EnqueueOutcome,
    InvalidBackfillRequestError,
    PendingChunk,
)
from evidenceguard_retrieval.embeddings import HASH_IDENTITY

_DIALECT = postgresql.dialect()  # type: ignore[no-untyped-call]
T0 = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
TENANT = UUID("66666666-6666-4666-8666-666666666666")
REVISION = UUID("22222222-2222-4222-8222-222222222222")
VERSION = "text-md-v1"
PROFILE = profile_id(TENANT, HASH_IDENTITY.fingerprint)
INDEX = index_id(TENANT, REVISION, VERSION, PROFILE)
ACTOR = ActorContext(tenant_id=TENANT, actor_id=uuid4(), role=Role.ADMIN)
TEXT_MARKER = "synthetic-private-chunk-text-marker"


def _sql(statement: Any) -> str:
    return " ".join(str(statement.compile(dialect=_DIALECT)).split())


def _index(status: str = "building", tenant: UUID = TENANT) -> IndexSnapshot:
    return IndexSnapshot(
        id=INDEX,
        tenant_id=tenant,
        revision_id=REVISION,
        chunker_version=VERSION,
        chunk_count=2,
        manifest_sha256="a" * 64,
        profile_id=PROFILE,
        dims=1024,
        allows_zero_vectors=True,
        status=status,
        vector_manifest_sha256="f" * 64 if status == "ready" else None,
        ready_at=T0 if status == "ready" else None,
    )


def _profile() -> ProfileSnapshot:
    return ProfileSnapshot(
        id=PROFILE,
        tenant_id=TENANT,
        provider_id="offline",
        model_id="fake-hash-v1",
        algorithm_version="ascii-word-sha256-v1",
        dims=1024,
        normalization="l2",
        fingerprint=HASH_IDENTITY.fingerprint,
        allows_zero_vectors=True,
    )


def _job(
    status: JobStatus = JobStatus.QUEUED,
    kind: str = "index_revision",
    payload: dict[str, str] | None = None,
) -> JobSnapshot:
    running = status is JobStatus.RUNNING
    terminal = status in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.DEAD)
    return JobSnapshot(
        id=uuid4(),
        tenant_id=TENANT,
        kind=kind,
        idempotency_key=str(INDEX),
        payload=JobPayload.from_mapping(payload or {"index_id": str(INDEX)}),
        status=status,
        attempt=1 if running or terminal else 0,
        max_attempts=3,
        run_after=T0,
        locked_by="worker-test" if running else None,
        lease_expires_at=T0 + timedelta(seconds=60) if running else None,
        created_at=T0,
        updated_at=T0,
        finished_at=T0 if terminal else None,
    )


@dataclass
class Seams:
    events: list[str] = field(default_factory=list)
    index_status: str = "building"
    job_status: JobStatus = JobStatus.QUEUED
    enqueue_calls: list[dict[str, Any]] = field(default_factory=list)
    create_error: Exception | None = None
    enqueue_error: Exception | None = None


@pytest.fixture
def seams(monkeypatch: pytest.MonkeyPatch) -> Seams:
    state = Seams()

    def ensure_profile(session: Any, tenant_id: UUID, identity: EmbeddingIdentity) -> Any:
        state.events.append("ensure_profile")
        assert tenant_id == ACTOR.tenant_id
        return _profile()

    def create_index(session: Any, tenant_id: UUID, revision_id: UUID, profile: Any) -> Any:
        state.events.append("create_index")
        if state.create_error is not None:
            raise state.create_error
        return _index(state.index_status)

    def enqueue(session: Any, actor: ActorContext, **kwargs: Any) -> JobSnapshot:
        state.events.append("enqueue")
        state.enqueue_calls.append(kwargs)
        if state.enqueue_error is not None:
            raise state.enqueue_error
        return _job(state.job_status)

    monkeypatch.setattr(indexing, "ensure_profile", ensure_profile)
    monkeypatch.setattr(indexing, "create_index", create_index)
    monkeypatch.setattr(indexing, "enqueue", enqueue)
    return state


def _enqueue(identity: EmbeddingIdentity = HASH_IDENTITY) -> indexing.IndexEnqueueResult:
    return indexing.enqueue_index_revision(
        cast(Any, object()), ACTOR, revision_id=REVISION, identity=identity
    )


# --- enqueue -----------------------------------------------------------------------------------


def test_a_building_index_enqueues_the_canonical_job(seams: Seams) -> None:
    result = _enqueue()

    assert seams.events == ["ensure_profile", "create_index", "enqueue"]
    (call,) = seams.enqueue_calls
    assert call["kind"] == "index_revision"
    assert call["idempotency_key"] == str(INDEX)
    assert call["payload"] == JobPayload.from_mapping({"index_id": str(INDEX)})
    assert "max_attempts" not in call  # the existing default of three attempts
    assert result.outcome is EnqueueOutcome.PENDING and result.job is not None


@pytest.mark.parametrize("status", [JobStatus.QUEUED, JobStatus.RUNNING])
def test_a_queued_or_running_job_is_pending(seams: Seams, status: JobStatus) -> None:
    seams.job_status = status
    assert _enqueue().outcome is EnqueueOutcome.PENDING


@pytest.mark.parametrize("status", [JobStatus.FAILED, JobStatus.DEAD, JobStatus.SUCCEEDED])
def test_a_terminal_job_for_a_building_index_is_stalled_and_returned_unchanged(
    seams: Seams, status: JobStatus
) -> None:
    seams.job_status = status
    result = _enqueue()
    assert result.outcome is EnqueueOutcome.STALLED
    assert result.job is not None and result.job.status is status


def test_a_ready_index_enqueues_nothing(seams: Seams) -> None:
    seams.index_status = "ready"
    result = _enqueue()
    assert result.outcome is EnqueueOutcome.READY and result.job is None
    assert "enqueue" not in seams.events


@pytest.mark.parametrize(
    "error",
    [
        JobIdempotencyConflictError(),
        IndexSourceNotEligibleError(),
        IndexConflictError(),
    ],
)
def test_conflicts_and_ineligibility_propagate(seams: Seams, error: Exception) -> None:
    if isinstance(error, JobIdempotencyConflictError):
        seams.enqueue_error = error
    else:
        seams.create_error = error
    with pytest.raises(type(error)):
        _enqueue()


def test_the_actor_and_identity_are_validated_before_any_write(seams: Seams) -> None:
    forged = ActorContext.model_construct(
        tenant_id=TENANT, actor_id=uuid4(), role=cast(Any, "owner")
    )
    with pytest.raises(PermissionDeniedError):
        indexing.enqueue_index_revision(
            cast(Any, object()), forged, revision_id=REVISION, identity=HASH_IDENTITY
        )
    with pytest.raises(TypeError):
        indexing.enqueue_index_revision(
            cast(Any, object()), cast(Any, "actor"), revision_id=REVISION, identity=HASH_IDENTITY
        )
    with pytest.raises(TypeError):
        indexing.enqueue_index_revision(
            cast(Any, object()), ACTOR, revision_id=cast(Any, str(REVISION)), identity=HASH_IDENTITY
        )
    small = EmbeddingIdentity("offline", "fake-hash-v1", "ascii-word-sha256-v1", 8, "l2")
    with pytest.raises(InvalidEmbeddingError):
        _enqueue(small)
    assert seams.events == []


@pytest.mark.parametrize("role", list(Role))
def test_every_existing_role_may_enqueue(seams: Seams, role: Role) -> None:
    actor = ActorContext(tenant_id=TENANT, actor_id=uuid4(), role=role)
    indexing.enqueue_index_revision(
        cast(Any, object()), actor, revision_id=REVISION, identity=HASH_IDENTITY
    )


# --- backfill --------------------------------------------------------------------------------


class FakeSession:
    def __init__(self, factory: "FakeFactory") -> None:
        self._factory = factory

    def scalars(self, statement: Any) -> list[UUID]:
        self._factory.sql.append(_sql(statement))
        return list(self._factory.selected)

    def commit(self) -> None:
        self._factory.log.append("commit")

    def rollback(self) -> None:
        self._factory.log.append("rollback")

    def close(self) -> None:
        self._factory.log.append("close")


@dataclass
class FakeFactory:
    selected: list[UUID] = field(default_factory=list)
    log: list[str] = field(default_factory=list)
    sql: list[str] = field(default_factory=list)
    opened: int = 0

    def __call__(self) -> FakeSession:
        self.opened += 1
        self.log.append("open")
        return FakeSession(self)


def _backfill(factory: FakeFactory, **kwargs: Any) -> indexing.BackfillPage:
    return indexing.backfill_index_revisions(
        cast(Any, factory), ACTOR, identity=HASH_IDENTITY, **kwargs
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"limit": 0},
        {"limit": 101},
        {"limit": True},
        {"limit": "5"},
        {"limit": 5.0},
        {"after": str(uuid4())},
        {"after": 7},
    ],
)
def test_invalid_backfill_requests_open_no_transaction(kwargs: dict[str, Any]) -> None:
    factory = FakeFactory()
    with pytest.raises(InvalidBackfillRequestError):
        _backfill(factory, **kwargs)
    assert factory.opened == 0


def test_an_invalid_actor_or_identity_opens_no_transaction() -> None:
    factory = FakeFactory()
    small = EmbeddingIdentity("offline", "fake-hash-v1", "ascii-word-sha256-v1", 8, "l2")
    with pytest.raises(InvalidEmbeddingError):
        indexing.backfill_index_revisions(cast(Any, factory), ACTOR, identity=small)
    with pytest.raises(TypeError):
        indexing.backfill_index_revisions(
            cast(Any, factory), cast(Any, None), identity=HASH_IDENTITY
        )
    assert factory.opened == 0


def test_the_selection_is_tenant_scoped_active_ordered_and_bounded() -> None:
    after = uuid4()
    statement = indexing.backfill_selection_statement(TENANT, PROFILE, limit=7, after=after)
    sql = _sql(statement)
    assert "document_revisions.tenant_id = " in sql
    assert "document_revisions.status = " in sql
    assert "JOIN chunk_sets ON chunk_sets.tenant_id = document_revisions.tenant_id" in sql
    assert "NOT (EXISTS (SELECT" in sql and "embedding_indexes.status = " in sql
    assert "embedding_indexes.profile_id = " in sql
    assert "document_revisions.id > " in sql
    assert sql.endswith("ORDER BY document_revisions.id LIMIT %(param_1)s::INTEGER")
    params = statement.compile(dialect=_DIALECT).params
    assert TENANT in params.values() and PROFILE in params.values() and "active" in params.values()
    assert after in params.values() and 7 in params.values()
    assert "document_revisions.id > " not in _sql(
        indexing.backfill_selection_statement(TENANT, PROFILE, limit=7, after=None)
    )


def _scripted(monkeypatch: pytest.MonkeyPatch, outcomes: dict[UUID, Any]) -> list[UUID]:
    seen: list[UUID] = []

    def enqueue_index_revision(
        session: Any, actor: ActorContext, *, revision_id: UUID, identity: Any
    ) -> indexing.IndexEnqueueResult:
        seen.append(revision_id)
        outcome = outcomes[revision_id]
        if isinstance(outcome, BaseException):
            raise outcome
        return indexing.IndexEnqueueResult(index=_index(), job=None, outcome=outcome)

    monkeypatch.setattr(indexing, "enqueue_index_revision", enqueue_index_revision)
    return seen


def test_each_item_commits_or_rolls_back_on_its_own(monkeypatch: pytest.MonkeyPatch) -> None:
    ids = [UUID(int=i) for i in range(1, 6)]
    factory = FakeFactory(selected=ids)
    _scripted(
        monkeypatch,
        {
            ids[0]: EnqueueOutcome.PENDING,
            ids[1]: IndexSourceNotEligibleError(),
            ids[2]: JobIdempotencyConflictError(),
            ids[3]: EmbeddingProfileConflictError(),
            ids[4]: EnqueueOutcome.STALLED,
        },
    )

    page = _backfill(factory, limit=5)

    assert [(item.revision_id, item.outcome) for item in page.items] == [
        (ids[0], BackfillOutcome.PENDING),
        (ids[1], BackfillOutcome.INELIGIBLE),
        (ids[2], BackfillOutcome.CONFLICT),
        (ids[3], BackfillOutcome.CONFLICT),
        (ids[4], BackfillOutcome.STALLED),
    ]
    assert [item.index_id is None for item in page.items] == [False, True, True, True, False]
    # One selection transaction, then one transaction per item.
    assert factory.opened == 6
    assert factory.log.count("rollback") == 3 and factory.log.count("commit") == 3
    assert page.next_after == ids[-1]  # a full page: the cursor covers failed items too


def test_a_short_page_has_no_next_cursor(monkeypatch: pytest.MonkeyPatch) -> None:
    ids = [UUID(int=1)]
    _scripted(monkeypatch, {ids[0]: EnqueueOutcome.READY})
    page = _backfill(FakeFactory(selected=ids), limit=2)
    assert page.next_after is None and page.items[0].outcome is BackfillOutcome.READY


def test_an_unexpected_failure_propagates_after_earlier_items_committed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ids = [UUID(int=i) for i in range(1, 4)]
    factory = FakeFactory(selected=ids)
    seen = _scripted(
        monkeypatch,
        {
            ids[0]: EnqueueOutcome.PENDING,
            ids[1]: RuntimeError("boom"),
            ids[2]: EnqueueOutcome.PENDING,
        },
    )

    with pytest.raises(RuntimeError):
        _backfill(factory, limit=3)

    assert seen == ids[:2]  # the third item is never attempted
    assert factory.log.count("commit") == 2  # the selection and the first item
    assert factory.log.count("rollback") == 1


def test_an_empty_selection_writes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _scripted(monkeypatch, {})
    page = _backfill(FakeFactory(), limit=50)
    assert page.items == () and page.next_after is None and seen == []


# --- handler reads ---------------------------------------------------------------------------


def test_pending_chunks_are_scoped_and_exclude_embedded_chunks() -> None:
    sql = _sql(indexing.pending_chunks_statement(_index(), after_ordinal=5))
    for predicate in (
        "chunks.tenant_id = ",
        "chunks.revision_id = ",
        "chunks.chunker_version = ",
        "chunks.ordinal > ",
        "NOT (EXISTS (SELECT",
        "chunk_embeddings.index_id = ",
        "chunk_embeddings.chunk_id = chunks.id",
    ):
        assert predicate in sql
    assert sql.endswith("ORDER BY chunks.ordinal LIMIT %(param_1)s::INTEGER")


@pytest.mark.parametrize(
    "job",
    [
        _job(kind="ingest_revision"),
        _job(payload={"revision_id": str(REVISION)}),
        _job(payload={"index_id": str(INDEX), "revision_id": str(REVISION)}),
        _job(payload={"index_id": str(uuid4())}),
    ],
)
def test_reads_require_the_jobs_own_index(job: JobSnapshot) -> None:
    with pytest.raises(IndexJobMismatchError):
        indexing.pending_chunks(cast(Any, object()), job, _index(), after_ordinal=-1)


def test_reads_refuse_another_tenants_index() -> None:
    with pytest.raises(IndexJobMismatchError):
        indexing.pending_chunks(
            cast(Any, object()), _job(), _index(tenant=uuid4()), after_ordinal=-1
        )


class _Row:
    def __init__(self, data: dict[str, Any]) -> None:
        self._mapping = data


class _ReadSession:
    def __init__(
        self, index_row: dict[str, Any] | None, profile_row: dict[str, Any] | None
    ) -> None:
        self.rows = [index_row, profile_row]
        self.sql: list[str] = []

    def execute(self, statement: Any) -> Any:
        self.sql.append(_sql(statement))
        row = self.rows.pop(0)

        class Result:
            def first(self_inner) -> _Row | None:
                return None if row is None else _Row(row)

        return Result()


def test_the_target_is_read_within_the_jobs_tenant_without_a_lock() -> None:
    index, profile = _index(), _profile()
    session = _ReadSession(
        {name: getattr(index, name) for name in embedding_store.INDEX_FIELDS},
        {name: getattr(profile, name) for name in embedding_store.PROFILE_FIELDS},
    )
    read_index, read_profile = indexing.load_index_target(cast(Any, session), _job())
    assert read_index == index and read_profile == profile
    assert all("FOR UPDATE" not in sql for sql in session.sql)
    assert "embedding_indexes.tenant_id = " in session.sql[0]


def test_a_missing_target_is_not_found() -> None:
    with pytest.raises(IndexNotFoundError):
        indexing.load_index_target(cast(Any, _ReadSession(None, None)), _job())


def test_pending_chunk_representations_never_show_text() -> None:
    chunk = PendingChunk(ordinal=3, id=UUID(int=9), text=TEXT_MARKER, content_sha256="a" * 64)
    assert TEXT_MARKER not in repr(chunk) and TEXT_MARKER not in str(chunk)
    assert repr(chunk) == f"PendingChunk(ordinal=3, id={UUID(int=9)})"
