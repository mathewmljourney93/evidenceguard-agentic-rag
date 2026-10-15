"""PostgreSQL integration tests for the M3e document API (ADR-0011).

They use the guarded disposable-database fixtures from ``conftest.py`` and are skipped without
``EG_TEST_DATABASE_URL`` (required in CI). The app runs with an in-memory authenticator and the
real ``DatabaseDocumentStore`` on the disposable engine; every connection carries a server-side
``statement_timeout``.

Interleavings are deterministic, never timing-based:

- ``before_statement`` hooks the app engine's ``before_cursor_execute`` and, just before a named
  statement of one production operation, runs a competing operation to commit on a **separate**
  engine (``other``), so it is not intercepted and holds no lock the operation needs;
- concurrent uploads meet at a two-party ``threading.Barrier`` (bounded wait) at the document
  ``INSERT`` and are then serialised by PostgreSQL's unique index and the document lock.

Every hook is removed in ``finally``, and every test asserts that its hook actually fired.
"""

import threading
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import (
    Engine,
    Interval,
    create_engine,
    delete,
    event,
    func,
    insert,
    literal_column,
    select,
    text,
)
from sqlalchemy import update as sql_update
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool, QueuePool

from evidenceguard_api.app import create_app
from evidenceguard_api.database import AppDatabase
from evidenceguard_domain.chunks import ExpectedChunkSet, batches
from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_domain.jobs import JobSnapshot
from evidenceguard_domain.revisions import RevisionContent, RevisionFailureCode
from evidenceguard_persistence import chunks as chunk_store
from evidenceguard_persistence import document_views, jobs
from evidenceguard_persistence import documents as revision_store
from evidenceguard_persistence.credentials import generate_api_key
from evidenceguard_persistence.db import create_session_factory
from evidenceguard_persistence.document_views import read_snapshot
from evidenceguard_persistence.models import (
    Chunk,
    ChunkSet,
    Document,
    DocumentRevision,
    Job,
    Tenant,
    Vendor,
)
from evidenceguard_retrieval.chunking import chunk_revision
from evidenceguard_worker.handlers import production_registry
from evidenceguard_worker.ingest import INGEST_REVISION_KIND
from evidenceguard_worker.runtime import DatabaseJobStore, Timings, run_worker

pytestmark = pytest.mark.integration

BOUNDARY = "eg-pg-boundary"
MULTIPART = {"Content-Type": f"multipart/form-data; boundary={BOUNDARY}"}
MARKDOWN = "text/markdown"
WAIT_SECONDS = 10
TEXT = (
    b"# Retention\n\nCustomer data is kept for 90 days.\n\n## Backups\n\nBackups are encrypted.\n"
)
# 450 chunks: batches of 200, 200 and 50 (M3d's batch bound).
MANY = "".join(f"# Section {index}\n\nParagraph {index}.\n\n" for index in range(450)).encode()
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
TABLES = (Document, DocumentRevision, Job, ChunkSet, Chunk)
REVISION_READ = "FROM document_revisions LEFT OUTER JOIN jobs ON"


def _bounded(url: URL, **kwargs: Any) -> Engine:
    return create_engine(
        url,
        hide_parameters=True,
        connect_args={"options": "-c statement_timeout=20000"},
        **kwargs,
    )


@pytest.fixture
def engine(migrated: Engine, test_database_url: URL) -> Iterator[Engine]:
    """The app's engine: hooks attach here."""
    bounded = _bounded(test_database_url, poolclass=NullPool)
    try:
        yield bounded
    finally:
        bounded.dispose()


@pytest.fixture
def other(migrated: Engine, test_database_url: URL) -> Iterator[sessionmaker[Session]]:
    """A separate engine for competing commits, never intercepted by the app engine's hooks."""
    bounded = _bounded(test_database_url, poolclass=NullPool)
    try:
        yield create_session_factory(bounded)
    finally:
        bounded.dispose()


@pytest.fixture
def factory(engine: Engine) -> sessionmaker[Session]:
    return create_session_factory(engine)


class Keys:
    def __init__(self) -> None:
        self.known: dict[str, ActorContext] = {}

    def __call__(self, credential: str) -> ActorContext | None:
        return self.known.get(credential)

    def header(self, actor: ActorContext) -> dict[str, str]:
        key = generate_api_key().plaintext.get_secret_value()
        self.known[key] = actor
        return {"Authorization": f"Bearer {key}"}


def _part(name: str, value: bytes, ctype: str | None = None) -> bytes:
    disposition = f'Content-Disposition: form-data; name="{name}"'
    if ctype is not None:
        disposition += f'; filename="upload.md"\r\nContent-Type: {ctype}'
    return f"--{BOUNDARY}\r\n{disposition}\r\n\r\n".encode() + value + b"\r\n"


class World:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.keys = Keys()
        self.app = create_app(authenticator=self.keys, database=AppDatabase(lambda: engine))
        self.client = TestClient(self.app)
        self.a = self._tenant("tenant-a")
        self.b = self._tenant("tenant-b")
        self.vendor_a = self._vendor(self.a.tenant_id)
        self.vendor_b = self._vendor(self.b.tenant_id)
        self.headers_a = self.keys.header(self.a)
        self.headers_b = self.keys.header(self.b)

    def _tenant(self, slug: str) -> ActorContext:
        tenant_id = uuid4()
        with self.engine.begin() as connection:
            connection.execute(insert(Tenant).values(id=tenant_id, slug=slug, name=slug.title()))
        return ActorContext(tenant_id=tenant_id, actor_id=uuid4(), role=Role.REVIEWER)

    def _vendor(self, tenant_id: UUID) -> UUID:
        vendor_id = uuid4()
        with self.engine.begin() as connection:
            connection.execute(
                insert(Vendor).values(
                    id=vendor_id, tenant_id=tenant_id, slug="lumenvale", name="Lumenvale"
                )
            )
        return vendor_id

    def upload(
        self,
        content: bytes = TEXT,
        *,
        vendor: UUID | None = None,
        client: TestClient | None = None,
        **fields: bytes,
    ) -> Any:
        values = {
            "document_key": b"data-retention",
            "title": b"Data retention",
            "source_type": b"vendor_statement",
            **fields,
        }
        body = b"".join(_part(name, value) for name, value in values.items())
        body += _part("file", content, ctype=MARKDOWN) + f"--{BOUNDARY}--\r\n".encode()
        return (client or self.client).post(
            f"/v1/vendors/{vendor or self.vendor_a}/documents",
            content=body,
            headers={**self.headers_a, **MULTIPART},
        )

    def get(self, path: str, headers: dict[str, str] | None = None) -> Any:
        return self.client.get(path, headers=headers or self.headers_a)

    def rows(self, *models: Any) -> dict[str, list[dict[str, Any]]]:
        with self.engine.connect() as connection:
            return {
                model.__tablename__: [
                    dict(row._mapping)
                    for row in connection.execute(
                        select(model.__table__).order_by(*model.__table__.primary_key.columns)
                    ).all()
                ]
                for model in models or TABLES
            }

    def jobs_for(self, revision_id: str) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(Job.__table__).where(Job.idempotency_key == revision_id)
            ).all()
        return [dict(row._mapping) for row in rows]

    def run_worker(self) -> None:
        run_worker(
            DatabaseJobStore(create_session_factory(self.engine)),
            production_registry(),
            worker_id="w-api",
            timings=TIMINGS,
            once=True,
        )


@pytest.fixture
def world(engine: Engine) -> World:
    return World(engine)


# --- helpers -------------------------------------------------------------------------------------


@contextmanager
def before_statement(
    engine: Engine, matches: Callable[[str], bool], action: Callable[[], None]
) -> Iterator[list[str]]:
    """Run ``action`` once, just before the first app statement that ``matches``."""
    fired: list[str] = []

    def hook(*args: Any) -> None:
        statement = args[2]
        if not fired and matches(statement):
            fired.append(statement)
            action()

    event.listen(engine, "before_cursor_execute", hook)
    try:
        yield fired
    finally:
        event.remove(engine, "before_cursor_execute", hook)


def _claim(factory: sessionmaker[Session], worker: str = "w-test") -> JobSnapshot:
    claimed = jobs.claim(factory, worker, kinds=[INGEST_REVISION_KIND])
    assert claimed is not None
    return claimed


def _start(factory: sessionmaker[Session], job: JobSnapshot) -> None:
    with jobs.fenced_transaction(factory, job.lease_token()) as fence:
        revision_store.start_processing(fence.session, fence.job)


def _expire(engine: Engine, job_id: UUID) -> None:
    with engine.begin() as connection:
        connection.execute(
            sql_update(Job)
            .where(Job.id == job_id)
            .values(
                lease_expires_at=func.clock_timestamp()
                - literal_column("interval '1 seconds'", type_=Interval)
            )
        )


def _processing_with_chunks(
    world: World, factory: sessionmaker[Session], content: bytes, *, batches_written: int
) -> tuple[dict[str, Any], JobSnapshot, list[tuple[Any, ...]]]:
    """Upload ``content``, claim and start its job, write the chunk set and some batches."""
    upload = world.upload(content).json()
    job = _claim(factory)
    assert str(job.id) == upload["job"]["id"]
    _start(factory, job)
    parsed = chunk_revision(
        RevisionContent.from_bytes(content, MARKDOWN),
        tenant_id=world.a.tenant_id,
        revision_id=UUID(upload["revision_id"]),
    )
    with jobs.fenced_transaction(factory, job.lease_token()) as fence:
        chunk_store.write_chunk_set(fence.session, fence.job, ExpectedChunkSet.of(parsed))
    all_batches = list(batches(parsed))
    for batch in all_batches[:batches_written]:
        with jobs.fenced_transaction(factory, job.lease_token()) as fence:
            chunk_store.write_chunks(fence.session, fence.job, batch)
    return upload, job, all_batches


def _make_dead(engine: Engine, factory: sessionmaker[Session], job_id: str) -> None:
    """Exhaust every attempt with expired leases; the next claim's sweep marks the job dead."""
    for attempt in range(3):
        claimed = _claim(factory, f"w-dead-{attempt}")
        assert str(claimed.id) == job_id
        _expire(engine, claimed.id)
    assert jobs.claim(factory, "w-sweep", kinds=[INGEST_REVISION_KIND]) is None
    with engine.connect() as connection:
        status = connection.execute(select(Job.status).where(Job.id == UUID(job_id))).scalar_one()
    assert status == "dead"


def _concurrently(world: World, contents: tuple[bytes, bytes]) -> list[Any]:
    """Two uploads that both reach the document ``INSERT`` before either executes it."""
    barrier = threading.Barrier(2, timeout=WAIT_SECONDS)
    lock = threading.Lock()
    arrived: list[str] = []

    def hook(*args: Any) -> None:
        statement = args[2]
        if statement.startswith("INSERT INTO documents"):
            with lock:
                if len(arrived) >= 2:
                    return
                arrived.append(statement)
            barrier.wait()

    event.listen(world.engine, "before_cursor_execute", hook)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(world.upload, content, client=TestClient(world.app))
                for content in contents
            ]
            responses = [future.result(timeout=60) for future in futures]
    finally:
        event.remove(world.engine, "before_cursor_execute", hook)
    assert len(arrived) == 2  # both requests met at the barrier
    return responses


# --- uploads -------------------------------------------------------------------------------------


def test_a_new_upload_commits_revision_and_job_together(world: World) -> None:
    response = world.upload()
    assert response.status_code == 202
    body = response.json()
    assert (body["created"], body["revision_status"], body["ingestion_state"]) == (
        True,
        "pending",
        "queued",
    )
    (job,) = world.jobs_for(body["revision_id"])
    assert job["kind"] == INGEST_REVISION_KIND
    assert job["payload"] == {"revision_id": body["revision_id"]}
    assert job["tenant_id"] == world.a.tenant_id
    assert body["job"]["id"] == str(job["id"])


def test_an_identical_upload_is_a_200_duplicate_without_a_second_job(world: World) -> None:
    first = world.upload().json()
    second = world.upload()
    assert second.status_code == 200
    assert second.json()["revision_id"] == first["revision_id"]
    assert second.json()["created"] is False
    assert len(world.jobs_for(first["revision_id"])) == 1


def test_different_bytes_get_the_next_revision_number(world: World) -> None:
    world.upload()
    second = world.upload(TEXT + b"\nChanged.\n").json()
    assert (second["created"], second["revision_no"]) == (True, 2)


def test_conflicting_metadata_is_a_generic_409(world: World) -> None:
    world.upload()
    response = world.upload(TEXT + b"x", title=b"Another title")
    assert response.status_code == 409
    assert "Another title" not in response.text


def test_an_enqueue_failure_rolls_back_the_revision(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing(*args: Any, **kwargs: Any) -> Any:
        raise jobs.JobEnqueueRaceError()

    monkeypatch.setattr(document_views, "enqueue", failing)
    assert world.upload().status_code == 503
    rows = world.rows()
    assert rows["documents"] == [] and rows["document_revisions"] == [] and rows["jobs"] == []


def test_a_foreign_vendor_is_404(world: World) -> None:
    assert world.upload(vendor=world.vendor_b).status_code == 404
    assert world.rows()["documents"] == []


def test_concurrent_identical_uploads_create_one_revision_and_one_job(world: World) -> None:
    responses = _concurrently(world, (TEXT, TEXT))
    assert sorted(r.status_code for r in responses) == [200, 202]
    bodies = [r.json() for r in responses]
    assert len({body["revision_id"] for body in bodies}) == 1
    assert {body["created"] for body in bodies} == {True, False}
    rows = world.rows(Document, DocumentRevision, Job)
    assert len(rows["documents"]) == 1
    assert len(rows["document_revisions"]) == 1
    assert len(rows["jobs"]) == 1
    assert {body["job"]["id"] for body in bodies} == {str(rows["jobs"][0]["id"])}


def test_concurrent_different_uploads_get_consecutive_revision_numbers(world: World) -> None:
    responses = _concurrently(world, (TEXT, TEXT + b"\nSecond version.\n"))
    assert [r.status_code for r in responses] == [202, 202]
    assert sorted(r.json()["revision_no"] for r in responses) == [1, 2]
    rows = world.rows(Document, DocumentRevision, Job)
    assert len(rows["documents"]) == 1
    assert rows["documents"][0]["latest_revision_no"] == 2
    assert len(rows["document_revisions"]) == 2
    assert {job["idempotency_key"] for job in rows["jobs"]} == {
        r.json()["revision_id"] for r in responses
    }


def test_the_upload_response_is_the_observation_made_before_commit(
    world: World, other: sessionmaker[Session]
) -> None:
    """A worker claims the job right after the commit; the response still reports what the
    creation transaction observed, and the API issues no statement after the commit."""
    state: dict[str, Any] = {"after_commit": False, "claimed": None, "late_statements": 0}

    def after_commit(session: Session) -> None:
        if session.get_bind() is not world.engine or state["after_commit"]:
            return
        state["after_commit"] = True
        state["claimed"] = _claim(other, "w-after-commit")

    def count(*args: Any) -> None:
        if state["after_commit"]:
            state["late_statements"] += 1

    event.listen(Session, "after_commit", after_commit)
    event.listen(world.engine, "before_cursor_execute", count)
    try:
        response = world.upload()
    finally:
        event.remove(Session, "after_commit", after_commit)
        event.remove(world.engine, "before_cursor_execute", count)
    assert state["claimed"] is not None and state["late_statements"] == 0
    body = response.json()
    assert response.status_code == 202
    assert (body["revision_status"], body["ingestion_state"]) == ("pending", "queued")
    assert (body["job"]["status"], body["job"]["attempt"]) == ("queued", 0)
    (job,) = world.jobs_for(body["revision_id"])
    assert (job["status"], job["attempt"]) == ("running", 1)


# --- duplicates against real rows ----------------------------------------------------------------


def _unchanged_duplicate(world: World, content: bytes) -> dict[str, Any]:
    before = world.rows(DocumentRevision, Job)
    response = world.upload(content)
    assert response.status_code == 200
    assert world.rows(DocumentRevision, Job) == before  # nothing reset, nothing created
    body: dict[str, Any] = response.json()
    assert body["created"] is False
    return body


def test_duplicate_of_a_processing_revision(world: World, factory: sessionmaker[Session]) -> None:
    upload = world.upload().json()
    _start(factory, _claim(factory))
    body = _unchanged_duplicate(world, TEXT)
    assert (body["revision_status"], body["ingestion_state"]) == ("processing", "in_progress")
    assert (body["job"]["status"], body["job"]["lease_expired"]) == ("running", False)
    assert body["job"]["lease_expires_at"] is not None
    assert body["revision_id"] == upload["revision_id"]


def test_duplicate_of_a_superseded_revision(world: World) -> None:
    first = world.upload().json()
    world.run_worker()
    world.upload(TEXT + b"\nSecond version.\n")
    world.run_worker()
    body = _unchanged_duplicate(world, TEXT)
    assert body["revision_id"] == first["revision_id"]
    assert (body["revision_status"], body["ingestion_state"]) == ("superseded", "superseded")
    (job,) = world.jobs_for(first["revision_id"])
    assert body["job"]["status"] == job["status"] == "succeeded"


def test_duplicate_of_a_failed_revision(world: World) -> None:
    whitespace = b"   \n\t\n"
    first = world.upload(whitespace).json()
    world.run_worker()
    body = _unchanged_duplicate(world, whitespace)
    assert body["revision_id"] == first["revision_id"]
    assert (body["revision_status"], body["ingestion_state"]) == ("failed", "failed")
    (job,) = world.jobs_for(first["revision_id"])
    assert body["job"]["status"] == job["status"]
    assert job["status"] in {"failed", "dead"}  # terminal: never re-queued


def test_duplicate_of_a_dead_job_revision(world: World, factory: sessionmaker[Session]) -> None:
    first = world.upload().json()
    _make_dead(world.engine, factory, first["job"]["id"])
    body = _unchanged_duplicate(world, TEXT)
    assert (body["revision_status"], body["ingestion_state"]) == ("pending", "stalled")
    assert (body["job"]["status"], body["job"]["lease_expired"]) == ("dead", None)


# --- the missing-job repair: POST only, never GET ------------------------------------------------


def test_get_never_repairs_a_missing_job_and_a_duplicate_post_does(world: World) -> None:
    upload = world.upload().json()
    revision_id, document_id = upload["revision_id"], upload["document_id"]
    with world.engine.begin() as connection:
        connection.execute(delete(Job).where(Job.idempotency_key == revision_id))

    before = world.rows()
    detail = world.get(f"/v1/documents/{document_id}").json()
    assert detail["latest_revision"]["ingestion_state"] == "stalled"
    assert detail["latest_revision"]["ingestion_job"] is None
    (listed,) = world.get(f"/v1/documents/{document_id}/revisions").json()["items"]
    assert (listed["ingestion_state"], listed["ingestion_job"]) == ("stalled", None)
    assert world.get(f"/v1/jobs/{upload['job']['id']}").status_code == 404
    assert world.rows() == before  # GET wrote nothing
    assert world.jobs_for(revision_id) == []

    repaired = world.upload()
    assert repaired.status_code == 200
    body = repaired.json()
    assert (body["ingestion_state"], body["job"]["status"]) == ("queued", "queued")
    (job,) = world.jobs_for(revision_id)
    assert body["job"]["id"] == str(job["id"])


# --- reads and the projection --------------------------------------------------------------------


def test_end_to_end_upload_ingest_and_views(world: World) -> None:
    upload = world.upload().json()
    world.run_worker()
    document_id, revision_id = upload["document_id"], upload["revision_id"]

    detail = world.get(f"/v1/documents/{document_id}").json()
    assert detail["active_revision_id"] == revision_id
    assert detail["active_revision"]["ingestion_state"] == "active"
    assert detail["latest_revision"]["id"] == revision_id
    assert "content_text" not in detail["active_revision"]

    chunks = world.get(f"/v1/documents/{document_id}/revisions/1/chunks").json()
    assert chunks["chunk_set"]["verified_complete"] is True
    assert chunks["chunk_set"]["stored_count"] == chunks["chunk_set"]["chunk_count"]
    assert [item["ordinal"] for item in chunks["items"]] == list(range(len(chunks["items"])))
    assert chunks["items"][0]["source"]["line_start"] >= 1

    job = world.get(f"/v1/jobs/{upload['job']['id']}").json()
    assert (job["status"], job["lease_expires_at"], job["lease_expired"]) == (
        "succeeded",
        None,
        None,
    )
    duplicate = world.upload()
    assert (duplicate.status_code, duplicate.json()["ingestion_state"]) == (200, "active")
    assert len(world.jobs_for(revision_id)) == 1


def test_an_expired_running_lease_reads_in_progress_and_expired(
    world: World, factory: sessionmaker[Session]
) -> None:
    upload = world.upload().json()
    claimed = _claim(factory, "w-stuck")
    _expire(world.engine, claimed.id)
    revisions = world.get(f"/v1/documents/{upload['document_id']}/revisions").json()
    (item,) = revisions["items"]
    assert item["ingestion_state"] == "in_progress"
    assert item["ingestion_job"]["lease_expired"] is True
    job = world.get(f"/v1/jobs/{claimed.id}").json()
    assert (job["status"], job["lease_expired"]) == ("running", True)


@pytest.mark.parametrize("outcome", ["succeeded", "failed"])
def test_a_terminal_job_with_an_unsettled_revision_reads_stalled(
    world: World, factory: sessionmaker[Session], outcome: str
) -> None:
    upload = world.upload().json()
    job = _claim(factory)
    _start(factory, job)
    if outcome == "succeeded":
        jobs.complete(factory, job.lease_token())
    else:
        jobs.fail_permanent(factory, job.lease_token())
    (item,) = world.get(f"/v1/documents/{upload['document_id']}/revisions").json()["items"]
    assert (item["status"], item["ingestion_state"]) == ("processing", "stalled")
    assert item["ingestion_job"]["status"] == outcome


def test_partial_chunks_are_never_verified_complete(
    world: World, factory: sessionmaker[Session]
) -> None:
    upload, job, all_batches = _processing_with_chunks(world, factory, MANY, batches_written=1)
    path = f"/v1/documents/{upload['document_id']}/revisions/1/chunks?limit=200"
    processing = world.get(path).json()
    assert processing["chunk_set"]["chunk_count"] == sum(len(b) for b in all_batches)
    assert processing["chunk_set"]["stored_count"] == processing["total"] == len(all_batches[0])
    assert processing["chunk_set"]["verified_complete"] is False

    with jobs.fenced_transaction(factory, job.lease_token()) as fence:
        revision_store.fail_revision(fence.session, fence.job, RevisionFailureCode.INGESTION_FAILED)
    failed = world.get(path).json()
    assert failed["chunk_set"]["verified_complete"] is False
    assert failed["chunk_set"]["stored_count"] == len(all_batches[0])
    (item,) = world.get(f"/v1/documents/{upload['document_id']}/revisions").json()["items"]
    assert (item["status"], item["ingestion_state"]) == ("failed", "failed")


def test_cross_tenant_reads_are_404(world: World) -> None:
    upload = world.upload().json()
    for path in (
        f"/v1/vendors/{world.vendor_a}/documents",
        f"/v1/documents/{upload['document_id']}",
        f"/v1/documents/{upload['document_id']}/revisions",
        f"/v1/documents/{upload['document_id']}/revisions/1/chunks",
        f"/v1/jobs/{upload['job']['id']}",
    ):
        assert world.get(path, world.headers_b).status_code == 404
        assert world.get(path).status_code == 200


def test_gets_change_no_rows(world: World) -> None:
    upload = world.upload().json()
    before = world.rows()
    for path in (
        f"/v1/vendors/{world.vendor_a}/documents",
        f"/v1/documents/{upload['document_id']}",
        f"/v1/documents/{upload['document_id']}/revisions",
        f"/v1/documents/{upload['document_id']}/revisions/1/chunks",
        f"/v1/jobs/{upload['job']['id']}",
    ):
        assert world.get(path).status_code == 200
    assert world.rows() == before


# --- one snapshot per response (interleavings inside production reads) ---------------------------


def test_an_activation_between_the_pointer_and_revision_reads_is_not_seen(
    world: World, factory: sessionmaker[Session], other: sessionmaker[Session]
) -> None:
    first = world.upload().json()
    world.run_worker()  # revision 1 is active
    second, job, all_batches = _processing_with_chunks(
        world, factory, TEXT + b"\n## Added\n\nMore text.\n", batches_written=99
    )
    assert all_batches

    def activate() -> None:
        with jobs.fenced_transaction(other, job.lease_token()) as fence:
            revision_store.activate_revision(fence.session, fence.job)

    path = f"/v1/documents/{first['document_id']}"
    with before_statement(world.engine, lambda s: REVISION_READ in s, activate) as fired:
        detail = world.get(path).json()
    assert fired
    assert detail["active_revision_id"] == first["revision_id"]
    assert (detail["active_revision"]["id"], detail["active_revision"]["status"]) == (
        first["revision_id"],
        "active",
    )
    assert (detail["latest_revision"]["id"], detail["latest_revision"]["status"]) == (
        second["revision_id"],
        "processing",
    )
    after = world.get(path).json()  # a new response sees the committed activation
    assert after["active_revision_id"] == second["revision_id"]
    assert after["active_revision"]["status"] == "active"


def test_a_job_and_revision_change_mid_read_never_mixes_states(
    world: World, other: sessionmaker[Session]
) -> None:
    upload = world.upload().json()

    def worker_starts() -> None:
        _start(other, _claim(other, "w-mid-read"))

    path = f"/v1/documents/{upload['document_id']}"
    with before_statement(world.engine, lambda s: REVISION_READ in s, worker_starts) as fired:
        detail = world.get(path).json()
    assert fired
    latest = detail["latest_revision"]
    assert (latest["status"], latest["ingestion_state"]) == ("pending", "queued")
    assert latest["ingestion_job"]["status"] == "queued"
    now = world.get(path).json()["latest_revision"]
    assert (now["status"], now["ingestion_state"]) == ("processing", "in_progress")
    assert now["ingestion_job"]["status"] == "running"


def test_a_chunk_batch_between_count_and_page_reads_is_not_seen(
    world: World, factory: sessionmaker[Session], other: sessionmaker[Session]
) -> None:
    upload, job, all_batches = _processing_with_chunks(world, factory, MANY, batches_written=1)

    def write_next_batch() -> None:
        with jobs.fenced_transaction(other, job.lease_token()) as fence:
            chunk_store.write_chunks(fence.session, fence.job, all_batches[1])

    def page_read(statement: str) -> bool:
        return "FROM chunks" in statement and "ORDER BY chunks.ordinal" in statement

    path = f"/v1/documents/{upload['document_id']}/revisions/1/chunks?offset=100&limit=200"
    with before_statement(world.engine, page_read, write_next_batch) as fired:
        page = world.get(path).json()
    assert fired
    stored = len(all_batches[0])
    assert page["chunk_set"]["stored_count"] == page["total"] == stored
    assert [item["ordinal"] for item in page["items"]] == list(range(100, stored))
    later = world.get(path).json()
    assert later["total"] == stored + len(all_batches[1])


def test_a_read_snapshot_ignores_commits_made_after_it_began(
    world: World, factory: sessionmaker[Session]
) -> None:
    world.upload()
    with read_snapshot(factory) as (session, _now):
        first = document_views.list_documents(session, world.a, world.vendor_a, limit=10, offset=0)
        world.upload(TEXT, document_key=b"second-document")  # commits on another connection
        again = document_views.list_documents(session, world.a, world.vendor_a, limit=10, offset=0)
    assert first is not None and again is not None
    assert first.total == again.total == 1
    with read_snapshot(factory) as (session, _now):
        after = document_views.list_documents(session, world.a, world.vendor_a, limit=10, offset=0)
    assert after is not None and after.total == 2


def test_an_upload_after_a_snapshot_on_the_same_pooled_connection_writes(
    world: World, test_database_url: URL
) -> None:
    pooled = _bounded(test_database_url, poolclass=QueuePool, pool_size=1, max_overflow=0)
    checkouts: list[int] = []

    def on_checkout(dbapi_connection: Any, *args: Any) -> None:
        checkouts.append(id(dbapi_connection))

    event.listen(pooled, "checkout", on_checkout)
    try:
        client = TestClient(
            create_app(authenticator=world.keys, database=AppDatabase(lambda: pooled))
        )
        listing = client.get(f"/v1/vendors/{world.vendor_a}/documents", headers=world.headers_a)
        assert listing.status_code == 200  # a REPEATABLE READ, READ ONLY snapshot
        body = {
            "document_key": b"data-retention",
            "title": b"Data retention",
            "source_type": b"vendor_statement",
        }
        payload = b"".join(_part(name, value) for name, value in body.items())
        payload += _part("file", TEXT, ctype=MARKDOWN) + f"--{BOUNDARY}--\r\n".encode()
        upload = client.post(
            f"/v1/vendors/{world.vendor_a}/documents",
            content=payload,
            headers={**world.headers_a, **MULTIPART},
        )
        assert upload.status_code == 202  # a leaked READ ONLY setting would fail the INSERT
        assert len(world.jobs_for(upload.json()["revision_id"])) == 1
        session = create_session_factory(pooled)()
        try:
            isolation = session.execute(text("SHOW transaction_isolation")).scalar_one()
            read_only = session.execute(text("SHOW transaction_read_only")).scalar_one()
        finally:
            session.close()
        assert (isolation, read_only) == ("read committed", "off")
        assert len(checkouts) >= 3 and len(set(checkouts)) == 1  # one physical connection
    finally:
        event.remove(pooled, "checkout", on_checkout)
        pooled.dispose()
