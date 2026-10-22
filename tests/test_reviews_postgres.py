"""PostgreSQL integration tests for M5d atomic review creation and trusted reload (ADR-0022).

They use the guarded disposable-database fixtures from ``conftest.py`` and are skipped without
``EG_TEST_DATABASE_URL`` (required in CI). Revisions are ingested and indexed through the real
worker and M4c paths (offline hash profile). Interleavings are positioned with a test-owned
``after_cursor_execute`` listener on a dedicated engine and ``threading.Event`` handshakes with
bounded waits, never sleeps. Tampered rows are written directly only to prove that the trusted
reload refuses them.
"""

import threading
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, event, insert, select, text, update
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool, QueuePool

from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_domain.evidence import SourceType
from evidenceguard_domain.jobs import JobPayload
from evidenceguard_domain.model_calls import PromptRef
from evidenceguard_domain.retrieval import EmptySnapshotError, RetrievalScopeError
from evidenceguard_domain.reviews import (
    ReviewCommitOutcomeUnknownError,
    ReviewConfiguration,
    ReviewDatabaseError,
    ReviewIdempotencyConflictError,
    ReviewJobConflictError,
    ReviewNotFoundError,
    ReviewRecordInconsistentError,
    ReviewRequest,
    request_sha256,
)
from evidenceguard_domain.revisions import RevisionContent
from evidenceguard_persistence import documents as revision_store
from evidenceguard_persistence import indexing, reviews
from evidenceguard_persistence import jobs as job_store
from evidenceguard_persistence.db import create_session_factory, transaction
from evidenceguard_persistence.models import (
    DocumentRevision,
    EmbeddingIndex,
    Job,
    Review,
    ReviewBinding,
    ReviewExcludedRevision,
    Tenant,
    Vendor,
)
from evidenceguard_retrieval.embeddings import HASH_IDENTITY
from evidenceguard_worker.handlers import production_registry
from evidenceguard_worker.ingest import INGEST_REVISION_KIND, ingest_revision
from evidenceguard_worker.registry import HandlerRegistry
from evidenceguard_worker.review_seams import create_review_with_artifacts, load_trusted_review
from evidenceguard_worker.runtime import DatabaseJobStore, Timings, WorkerResult, run_worker

pytestmark = pytest.mark.integration

WAIT_SECONDS = 10
MARKDOWN = "text/markdown"
TIMINGS = Timings(
    idle_poll=0.05,
    backoff_initial=0.05,
    backoff_cap=0.2,
    heartbeat_interval=0.2,
    drain=5.0,
    cancel_grace=5.0,
    lease_loss_grace=5.0,
    heartbeat_join=5.0,
    stop_check=0.01,
)
INGEST_ONLY = HandlerRegistry([(INGEST_REVISION_KIND, ingest_revision)])
CONFIGURATION = ReviewConfiguration(
    template_id="vendor_security_review",
    template_version=1,
    template_sha256="26fcbe26dcc47f5991da5b741475c736cec27b1f2bd6ab515ec07ac59895786a",
    verifier_prompt=PromptRef(
        prompt_id="verifier",
        version=1,
        sha256="629f8f972a0f5d6247a54364da59f04d53a1a023472fa00830ebedfe106b007d",
    ),
    analyst_prompt=PromptRef(
        prompt_id="risk_analyst",
        version=1,
        sha256="f8e485998dc2ff79c839100c27326a6e119135788060237a9fcbe5fed0051b29",
    ),
    model_id="fake-scripted-v1",
)
REVIEW_TABLES = {"reviews", "review_bindings", "review_excluded_revisions"}


def _request(vendor: UUID, key: str = "review-2026-10-22.a", **changes: Any) -> ReviewRequest:
    configuration = CONFIGURATION
    if changes:
        values = {
            "template_id": CONFIGURATION.template_id,
            "template_version": CONFIGURATION.template_version,
            "template_sha256": CONFIGURATION.template_sha256,
            "verifier_prompt": CONFIGURATION.verifier_prompt,
            "analyst_prompt": CONFIGURATION.analyst_prompt,
            "model_id": CONFIGURATION.model_id,
            **changes,
        }
        configuration = ReviewConfiguration(**values)
    return ReviewRequest(
        vendor_id=vendor, idempotency_key=key, identity=HASH_IDENTITY, configuration=configuration
    )


# --- engines and fixtures ------------------------------------------------------------------------


def _engine(url: URL, **options: Any) -> Engine:
    options.setdefault("poolclass", NullPool)
    return create_engine(
        url,
        hide_parameters=True,
        connect_args={"options": "-c statement_timeout=20000"},
        **options,
    )


@pytest.fixture
def engine(migrated: Engine, test_database_url: URL) -> Iterator[Engine]:
    bounded = _engine(test_database_url)
    try:
        yield bounded
    finally:
        bounded.dispose()


@pytest.fixture
def factory(engine: Engine) -> sessionmaker[Session]:
    return create_session_factory(engine)


@pytest.fixture
def actor(engine: Engine) -> ActorContext:
    return _tenant(engine, "tenant-a")


@pytest.fixture
def vendor(engine: Engine, actor: ActorContext) -> UUID:
    return _vendor(engine, actor.tenant_id, "lumenvale")


def _tenant(engine: Engine, slug: str, role: Role = Role.REVIEWER) -> ActorContext:
    tenant_id = uuid4()
    with engine.begin() as connection:
        connection.execute(insert(Tenant).values(id=tenant_id, slug=slug, name=slug.title()))
    return ActorContext(tenant_id=tenant_id, actor_id=uuid4(), role=role)


def _vendor(engine: Engine, tenant_id: UUID, slug: str) -> UUID:
    vendor_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            insert(Vendor).values(id=vendor_id, tenant_id=tenant_id, slug=slug, name=slug)
        )
    return vendor_id


def _create(
    factory: sessionmaker[Session], actor: ActorContext, vendor: UUID, key: str, body: str
) -> UUID:
    with transaction(factory) as session:
        created = revision_store.create_revision(
            session,
            actor,
            vendor_id=vendor,
            document_key=key,
            title=key.replace("-", " ").title(),
            source_type=SourceType.VENDOR_STATEMENT,
            content=RevisionContent.from_bytes(body.encode(), MARKDOWN),
        )
        job_store.enqueue(
            session,
            actor,
            kind=INGEST_REVISION_KIND,
            idempotency_key=str(created.revision.id),
            payload=JobPayload.from_mapping({"revision_id": str(created.revision.id)}),
        )
    return created.revision.id


def _work(factory: sessionmaker[Session], registry: HandlerRegistry) -> WorkerResult:
    return run_worker(
        DatabaseJobStore(factory), registry, worker_id="w-test", timings=TIMINGS, once=True
    )


def _ingest(
    factory: sessionmaker[Session], actor: ActorContext, vendor: UUID, key: str, body: str
) -> UUID:
    revision = _create(factory, actor, vendor, key, body)
    assert _work(factory, INGEST_ONLY).exit_code == 0
    return revision


def _ready(
    factory: sessionmaker[Session],
    engine: Engine,
    actor: ActorContext,
    vendor: UUID,
    key: str,
    body: str,
) -> UUID:
    revision = _ingest(factory, actor, vendor, key, body)
    with transaction(factory) as session:
        result = indexing.enqueue_index_revision(
            session, actor, revision_id=revision, identity=HASH_IDENTITY
        )
    if result.outcome is not indexing.EnqueueOutcome.READY:
        assert _work(factory, production_registry()).exit_code == 0
    with engine.connect() as connection:
        status = connection.execute(
            select(EmbeddingIndex.status).where(EmbeddingIndex.id == result.index.id)
        ).scalar_one()
    assert status == "ready"
    return revision


def _count(engine: Engine, table: Any, **where: Any) -> int:
    statement = select(table)
    for name, value in where.items():
        statement = statement.where(getattr(table, name) == value)
    with engine.connect() as connection:
        return len(connection.execute(statement).all())


def _review_jobs(engine: Engine) -> list[Any]:
    with engine.connect() as connection:
        return list(connection.execute(select(Job.__table__).where(Job.kind == "run_review")))


def _pause_after(
    engine: Engine, marker: str
) -> tuple[threading.Event, threading.Event, Callable[..., None]]:
    """Pause the first statement containing ``marker`` on ``engine`` until released."""
    paused, release = threading.Event(), threading.Event()

    def listener(*args: Any) -> None:
        statement: str = args[2]
        if marker in statement and not paused.is_set():
            paused.set()
            if not release.wait(WAIT_SECONDS):
                raise RuntimeError("the test never released the paused statement")

    event.listen(engine, "after_cursor_execute", listener)
    return paused, release, listener


ATTEMPT = "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ WRITE"  # once per attempt


def _record_statements(engine: Engine, markers: tuple[str, ...]) -> tuple[dict[str, int], Any]:
    """Count **successfully executed** statements on ``engine`` containing each marker
    (test-owned ``after_cursor_execute`` listener; a statement the database rejects never reaches
    that event)."""
    counts = dict.fromkeys(markers, 0)

    def listener(*args: Any) -> None:
        statement: str = args[2]
        for marker in markers:
            if marker in statement:
                counts[marker] += 1

    event.listen(engine, "after_cursor_execute", listener)
    return counts, listener


def _fail_before(engine: Engine, marker: str) -> Any:
    """Raise an ordinary error just before the first statement containing ``marker``."""

    def listener(*args: Any) -> None:
        statement: str = args[2]
        if marker in statement:
            raise RuntimeError(f"injected failure before {marker}")

    event.listen(engine, "before_cursor_execute", listener)
    return listener


def _all_rows(engine: Engine) -> dict[str, list[dict[str, Any]]]:
    with engine.connect() as connection:
        return {
            name: [dict(row._mapping) for row in connection.execute(statement)]
            for name, statement in (
                ("jobs", select(Job.__table__).order_by(Job.id)),
                ("reviews", select(Review.__table__).order_by(Review.id)),
                ("bindings", select(ReviewBinding.__table__)),
                ("excluded", select(ReviewExcludedRevision.__table__)),
            )
        }


def _assert_nothing_created(engine: Engine) -> None:
    assert _count(engine, Review) == 0 and _count(engine, ReviewBinding) == 0
    assert _count(engine, ReviewExcludedRevision) == 0 and _review_jobs(engine) == []


@pytest.fixture
def corpus(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, vendor: UUID
) -> tuple[UUID, UUID]:
    """One ready active revision and one pending (excluded) revision."""
    ready = _ready(factory, engine, actor, vendor, "retention", "Retention is ninety days.\n")
    pending = _create(factory, actor, vendor, "pending", "Pending.\n")
    return ready, pending


# --- creation ------------------------------------------------------------------------------------


def test_creation_commits_the_review_bindings_exclusions_and_job_together(
    factory: sessionmaker[Session],
    engine: Engine,
    actor: ActorContext,
    vendor: UUID,
    corpus: tuple[UUID, UUID],
) -> None:
    ready, pending = corpus
    request = _request(vendor)
    created = create_review_with_artifacts(factory, actor, request)
    assert not created.replayed
    assert created.request_sha256 == request_sha256(request, tenant_id=actor.tenant_id)
    assert created.configuration_sha256 == CONFIGURATION.configuration_sha256
    with engine.connect() as connection:
        row = connection.execute(select(Review.__table__)).one()
        bindings = connection.execute(select(ReviewBinding.__table__)).all()
        excluded = connection.execute(select(ReviewExcludedRevision.__table__)).all()
    assert row.id == created.review_id and row.run_review_job_id == created.job_id
    assert row.captured_at == created.captured_at and row.snapshot_sha256 == created.snapshot_sha256
    assert [(b.ordinal, b.revision_id) for b in bindings] == [(0, ready)]
    assert [e.revision_id for e in excluded] == [pending] and row.exclusion_count == 1
    (job,) = _review_jobs(engine)
    assert job.id == created.job_id and job.tenant_id == actor.tenant_id
    assert job.idempotency_key == str(created.review_id)
    assert job.payload == {"review_id": str(created.review_id)}
    assert (job.status, job.attempt, job.max_attempts) == ("queued", 0, 3)

    resolved = load_trusted_review(factory, actor, created.review_id)
    trusted = resolved.review
    assert trusted.request == request and trusted.job_id == created.job_id
    assert trusted.snapshot.sha256 == created.snapshot_sha256
    assert [b.revision_id for b in trusted.snapshot.bindings] == [ready]
    assert trusted.snapshot.exclusions.revision_ids == (pending,)
    assert resolved.template.ref.sha256 == CONFIGURATION.template_sha256


def test_a_matching_request_replays_and_a_different_one_conflicts(
    factory: sessionmaker[Session],
    engine: Engine,
    actor: ActorContext,
    vendor: UUID,
    corpus: tuple[UUID, UUID],
) -> None:
    first = reviews.create_review(factory, actor, _request(vendor))
    approver = ActorContext(tenant_id=actor.tenant_id, actor_id=uuid4(), role=Role.APPROVER)
    again = reviews.create_review(factory, approver, _request(vendor))
    assert again.replayed and again.review_id == first.review_id
    assert again.job_id == first.job_id and again.captured_at == first.captured_at
    with pytest.raises(ReviewIdempotencyConflictError):
        reviews.create_review(factory, actor, _request(vendor, timeout_ms=30000))
    assert _count(engine, Review) == 1 and len(_review_jobs(engine)) == 1


def test_semantic_refusals_write_nothing(
    factory: sessionmaker[Session], engine: Engine, actor: ActorContext, vendor: UUID
) -> None:
    with pytest.raises(EmptySnapshotError):
        reviews.create_review(factory, actor, _request(vendor))
    with pytest.raises(RetrievalScopeError):
        reviews.create_review(factory, actor, _request(uuid4()))
    assert _count(engine, Review) == 0 and _review_jobs(engine) == []


def test_a_failure_after_every_insert_before_commit_rolls_everything_back(
    factory: sessionmaker[Session],
    engine: Engine,
    actor: ActorContext,
    vendor: UUID,
    corpus: tuple[UUID, UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_insert = reviews._insert

    def insert_then_fail(session: Session, **kwargs: Any) -> None:
        real_insert(session, **kwargs)
        raise RuntimeError("injected failure after every insert, before COMMIT")

    monkeypatch.setattr(reviews, "_insert", insert_then_fail)
    with pytest.raises(ReviewDatabaseError):
        reviews.create_review(factory, actor, _request(vendor))
    _assert_nothing_created(engine)


def test_a_failure_after_the_job_insert_before_the_review_insert_rolls_back_the_job(
    factory: sessionmaker[Session],
    engine: Engine,
    actor: ActorContext,
    vendor: UUID,
    corpus: tuple[UUID, UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    jobs: list[UUID] = []

    def fail_before_review(session: Session, **kwargs: Any) -> None:
        # The run_review job row was inserted by enqueue in this transaction.
        jobs.append(kwargs["job_id"])
        found = session.execute(select(Job.id).where(Job.id == kwargs["job_id"])).first()
        assert found is not None
        raise RuntimeError("injected failure after the job insert, before the review insert")

    monkeypatch.setattr(reviews, "_insert", fail_before_review)
    with pytest.raises(ReviewDatabaseError):
        reviews.create_review(factory, actor, _request(vendor))
    assert len(jobs) == 1
    _assert_nothing_created(engine)


@pytest.mark.parametrize(
    "marker", ["INSERT INTO review_bindings", "INSERT INTO review_excluded_revisions"]
)
def test_a_failure_after_the_review_insert_before_its_child_rows_rolls_everything_back(
    engine: Engine,
    actor: ActorContext,
    vendor: UUID,
    corpus: tuple[UUID, UUID],
    test_database_url: URL,
    marker: str,
) -> None:
    failing_engine = _engine(test_database_url)
    counts, counter = _record_statements(failing_engine, ("INSERT INTO reviews (",))
    listener = _fail_before(failing_engine, marker)
    try:
        with pytest.raises(ReviewDatabaseError):
            reviews.create_review(create_session_factory(failing_engine), actor, _request(vendor))
    finally:
        event.remove(failing_engine, "before_cursor_execute", listener)
        event.remove(failing_engine, "after_cursor_execute", counter)
        failing_engine.dispose()
    assert counts["INSERT INTO reviews ("] == 1  # the review row had been inserted
    _assert_nothing_created(engine)


def test_an_existing_job_for_the_generated_review_key_is_refused(
    factory: sessionmaker[Session],
    engine: Engine,
    actor: ActorContext,
    vendor: UUID,
    corpus: tuple[UUID, UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixed = UUID("99999999-9999-4999-8999-999999999999")
    with transaction(factory) as session:
        job_store.enqueue(
            session,
            actor,
            kind="run_review",
            idempotency_key=str(fixed),
            payload=JobPayload.from_mapping({"review_id": str(fixed)}),
            max_attempts=3,
        )
    before = _all_rows(engine)
    monkeypatch.setattr(reviews, "uuid4", lambda: fixed)
    with pytest.raises(ReviewJobConflictError):
        reviews.create_review(factory, actor, _request(vendor))
    assert _all_rows(engine) == before  # no review and no job mutation


def test_an_unknown_commit_outcome_is_never_retried_and_a_later_call_replays(
    engine: Engine, actor: ActorContext, vendor: UUID, corpus: tuple[UUID, UUID]
) -> None:
    class CommitThenFail(Session):
        def commit(self) -> None:
            super().commit()
            raise RuntimeError("the acknowledgement was lost")

    failing = cast(
        sessionmaker[Session], sessionmaker(bind=engine, class_=CommitThenFail, autoflush=False)
    )
    with pytest.raises(ReviewCommitOutcomeUnknownError):
        reviews.create_review(failing, actor, _request(vendor))
    assert _count(engine, Review) == 1  # it did commit; the caller cannot know
    replay = reviews.create_review(create_session_factory(engine), actor, _request(vendor))
    assert replay.replayed and len(_review_jobs(engine)) == 1


def test_tenants_are_isolated(
    factory: sessionmaker[Session],
    engine: Engine,
    actor: ActorContext,
    vendor: UUID,
    corpus: tuple[UUID, UUID],
) -> None:
    created = reviews.create_review(factory, actor, _request(vendor))
    outsider = _tenant(engine, "tenant-b", Role.APPROVER)
    with pytest.raises(ReviewNotFoundError):
        reviews.load_review(factory, outsider, created.review_id)
    with pytest.raises(RetrievalScopeError):  # the vendor belongs to another tenant
        reviews.create_review(factory, outsider, _request(vendor))
    other_vendor = _vendor(engine, outsider.tenant_id, "lumenvale")
    _ready(factory, engine, outsider, other_vendor, "retention", "Retention is ninety days.\n")
    theirs = reviews.create_review(factory, outsider, _request(other_vendor))
    assert not theirs.replayed and theirs.review_id != created.review_id
    assert theirs.request_sha256 != created.request_sha256


def test_concurrent_creations_with_one_key_produce_one_review(
    engine: Engine,
    actor: ActorContext,
    vendor: UUID,
    corpus: tuple[UUID, UUID],
    test_database_url: URL,
) -> None:
    """The first creation inserts its review row and pauses before COMMIT; the second reaches
    its own review insert (its snapshot and replay lookup therefore predate the first commit)
    before the first is released, so that insert is attempted and rejected by the review-key
    conflict, and the second retries in a fresh transaction and replays. Attempted statements are
    counted before execution and successful ones after it."""
    first_engine = _engine(test_database_url)
    second_engine = _engine(test_database_url)
    paused, release, pause_listener = _pause_after(first_engine, "INSERT INTO reviews (")
    reached = threading.Event()
    attempted_review_inserts = 0

    def second_reaches_insert(*args: Any) -> None:
        nonlocal attempted_review_inserts
        if "INSERT INTO reviews (" in args[2]:
            attempted_review_inserts += 1
            reached.set()

    event.listen(second_engine, "before_cursor_execute", second_reaches_insert)
    executed, counter = _record_statements(second_engine, (ATTEMPT, "INSERT INTO reviews ("))
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(
                reviews.create_review,
                create_session_factory(first_engine),
                actor,
                _request(vendor),
            )
            try:
                assert paused.wait(WAIT_SECONDS)  # first row inserted, uncommitted
                second = pool.submit(
                    reviews.create_review,
                    create_session_factory(second_engine),
                    actor,
                    _request(vendor),
                )
                assert reached.wait(WAIT_SECONDS)  # second is at its conflicting insert
            finally:
                release.set()
            a, b = first.result(timeout=WAIT_SECONDS), second.result(timeout=WAIT_SECONDS)
    finally:
        event.remove(first_engine, "after_cursor_execute", pause_listener)
        event.remove(second_engine, "before_cursor_execute", second_reaches_insert)
        event.remove(second_engine, "after_cursor_execute", counter)
        first_engine.dispose()
        second_engine.dispose()
    assert not a.replayed and b.replayed and a.review_id == b.review_id
    assert a.job_id == b.job_id
    # The second ran two transactions: the attempt whose review INSERT was attempted and rejected
    # by the conflict (so it never executed successfully), then a fresh replay transaction.
    assert executed[ATTEMPT] == 2
    assert attempted_review_inserts == 1
    assert executed["INSERT INTO reviews ("] == 0
    assert _count(engine, Review) == 1 and len(_review_jobs(engine)) == 1


def test_an_activation_committed_after_the_snapshot_is_established_is_not_bound(
    factory: sessionmaker[Session],
    engine: Engine,
    actor: ActorContext,
    vendor: UUID,
    test_database_url: URL,
) -> None:
    old = _ready(factory, engine, actor, vendor, "retention", "Retention is ninety days.\n")
    held_engine = _engine(test_database_url)
    paused, release, listener = _pause_after(held_engine, "clock_timestamp")
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            running = pool.submit(
                reviews.create_review,
                create_session_factory(held_engine),
                actor,
                _request(vendor),
            )
            try:
                assert paused.wait(WAIT_SECONDS)  # the creation snapshot is established
                _ingest(factory, actor, vendor, "retention", "Retention is thirty days.\n")
                with engine.connect() as connection:
                    status = connection.execute(
                        select(DocumentRevision.status).where(DocumentRevision.id == old)
                    ).scalar_one()
                assert status == "superseded"
            finally:
                release.set()
            created = running.result(timeout=WAIT_SECONDS)
    finally:
        event.remove(held_engine, "after_cursor_execute", listener)
        held_engine.dispose()
    trusted = reviews.load_review(factory, actor, created.review_id)
    assert [b.revision_id for b in trusted.snapshot.bindings] == [old]


def test_creation_returns_its_pooled_connection_with_default_settings(
    actor: ActorContext,
    vendor: UUID,
    corpus: tuple[UUID, UUID],
    test_database_url: URL,
) -> None:
    """A one-connection pool proves the creation connection itself is reused afterwards with
    its defaults: the transaction-local isolation and timeouts did not leak."""
    pooled = _engine(test_database_url, poolclass=QueuePool, pool_size=1, max_overflow=0)
    pids: list[int] = []

    def record(connection: Any, *args: Any) -> None:
        if "clock_timestamp" in args[1]:
            pids.append(connection.connection.dbapi_connection.info.backend_pid)

    event.listen(pooled, "after_cursor_execute", record)
    try:
        created = reviews.create_review(create_session_factory(pooled), actor, _request(vendor))
        with pooled.connect() as connection:
            settings = {
                name: connection.execute(text(f"SHOW {name}")).scalar_one()
                for name in (
                    "transaction_isolation",
                    "transaction_read_only",
                    "statement_timeout",
                    "lock_timeout",
                )
            }
            pid = connection.execute(text("SELECT pg_backend_pid()")).scalar_one()
    finally:
        event.remove(pooled, "after_cursor_execute", record)
        pooled.dispose()
    assert not created.replayed
    assert pids == [pid]  # the same pooled connection served the creation
    assert settings == {
        "transaction_isolation": "read committed",
        "transaction_read_only": "off",
        "statement_timeout": "20s",
        "lock_timeout": "0",
    }


def test_the_production_registry_never_claims_a_review_job(
    factory: sessionmaker[Session],
    engine: Engine,
    actor: ActorContext,
    vendor: UUID,
    corpus: tuple[UUID, UUID],
) -> None:
    created = reviews.create_review(factory, actor, _request(vendor))
    assert "run_review" not in production_registry().kinds
    _work(factory, production_registry())
    (job,) = _review_jobs(engine)
    assert job.id == created.job_id and (job.status, job.attempt) == ("queued", 0)


# --- trusted reload ------------------------------------------------------------------------------


def _tamper(engine: Engine, statement: Any) -> None:
    with engine.begin() as connection:
        connection.execute(statement)


@pytest.mark.parametrize(
    ("change", "replay_refuses"),
    [
        (lambda job_id: update(Review).values(timeout_ms=30000), False),
        (lambda job_id: update(Review).values(snapshot_sha256="0" * 64), False),
        (lambda job_id: update(Review).values(captured_at=datetime(2026, 1, 1, tzinfo=UTC)), False),
        (lambda job_id: update(Review).values(exclusion_count=2), False),
        (lambda job_id: update(ReviewBinding).values(chunk_count=99), False),
        (lambda job_id: update(ReviewBinding).values(manifest_sha256="0" * 64), False),
        (lambda job_id: text("DELETE FROM review_excluded_revisions"), False),
        (lambda job_id: update(Job).where(Job.id == job_id).values(max_attempts=5), True),
        (
            lambda job_id: (
                update(Job).where(Job.id == job_id).values(payload={"review_id": str(uuid4())})
            ),
            True,
        ),
    ],
)
def test_reload_refuses_tampered_rows(
    factory: sessionmaker[Session],
    engine: Engine,
    actor: ActorContext,
    vendor: UUID,
    corpus: tuple[UUID, UUID],
    change: Callable[[UUID], Any],
    replay_refuses: bool,
) -> None:
    created = reviews.create_review(factory, actor, _request(vendor))
    _tamper(engine, change(created.job_id))
    with pytest.raises(ReviewRecordInconsistentError):
        reviews.load_review(factory, actor, created.review_id)
    if replay_refuses:  # the replay lookup validates the job association too
        with pytest.raises(ReviewRecordInconsistentError):
            reviews.create_review(factory, actor, _request(vendor))


def test_reload_ignores_job_lifecycle_fields(
    factory: sessionmaker[Session],
    engine: Engine,
    actor: ActorContext,
    vendor: UUID,
    corpus: tuple[UUID, UUID],
) -> None:
    created = reviews.create_review(factory, actor, _request(vendor))
    _tamper(
        engine,
        update(Job)
        .where(Job.id == created.job_id)
        .values(
            status="failed",
            attempt=3,
            finished_at=datetime(2026, 10, 22, tzinfo=UTC),
            last_error="handler_failed",
        ),
    )
    assert reviews.load_review(factory, actor, created.review_id).job_id == created.job_id


# --- schema --------------------------------------------------------------------------------------


def _constraints(engine: Engine) -> set[str]:
    with engine.connect() as connection:
        return set(
            connection.execute(
                text(
                    "SELECT conname FROM pg_constraint WHERE conrelid IN "
                    "('reviews'::regclass, 'review_bindings'::regclass, "
                    "'review_excluded_revisions'::regclass)"
                )
            ).scalars()
        )


def test_review_constraints_carry_their_accepted_names(engine: Engine) -> None:
    names = _constraints(engine)
    assert {
        "pk_reviews",
        "uq_reviews_tenant_id_id",
        "uq_reviews_tenant_id_idempotency_key",
        "uq_reviews_tenant_id_run_review_job_id",
        "fk_reviews_tenant_id_tenants",
        "fk_reviews_tenant_id_vendor_id_vendors",
        "fk_reviews_tenant_id_run_review_job_id_jobs",
        "ck_reviews_distinct_prompts",
        "pk_review_bindings",
        "uq_review_bindings_review_id_ordinal",
        "uq_review_bindings_review_id_document_id",
        "fk_review_bindings_review",
        "fk_review_bindings_revision",
        "fk_review_bindings_index",
        "pk_review_excluded_revisions",
        "fk_review_excluded_revisions_review",
        "fk_review_excluded_revisions_revision",
    } <= names
    assert len([name for name in names if name.startswith("ck_reviews_")]) == 28
    assert len([name for name in names if name.startswith("ck_review_bindings_")]) == 5


def test_migration_0006_downgrades_upgrades_and_matches_the_models(
    migrated: Engine, config: Config
) -> None:
    def tables() -> set[str]:
        with migrated.connect() as connection:
            return set(
                connection.execute(
                    text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                ).scalars()
            )

    def version() -> str:
        with migrated.connect() as connection:
            found: str = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
        return found

    assert tables() >= REVIEW_TABLES and version() == "0006"
    command.downgrade(config, "0005")
    assert not REVIEW_TABLES & tables() and version() == "0005"
    command.upgrade(config, "head")
    assert tables() >= REVIEW_TABLES and version() == "0006"
    command.check(config)  # raises AutogenerateDiffsDetected on any difference
