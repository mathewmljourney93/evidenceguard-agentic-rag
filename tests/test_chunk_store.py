"""The chunk store (``evidenceguard_persistence.chunks``) and M3c's ``before_settle`` hook,
without a database (M3d, ADR-0010).

A statement-level session double answers the module's statements (compiled for PostgreSQL)
from scripted results and records them in order. The shared lock helper and the ownership
re-check are replaced by recorders, so the tests check the protocol: lock, status check, insert,
verify, re-check. Real PostgreSQL behaviour (constraints, lock waits, rollback, races) is covered
by ``test_ingestion_postgres.py``, which runs only in CI.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import postgresql

from evidenceguard_domain.chunks import Chunk, ExpectedChunkSet, chunk_id
from evidenceguard_domain.evidence import SourceType
from evidenceguard_domain.jobs import JobPayload, JobSnapshot, JobStatus, LeaseLostError
from evidenceguard_domain.revisions import (
    DocumentSnapshot,
    InvalidRevisionContentError,
    RevisionFailureCode,
    RevisionSnapshot,
    RevisionStatus,
)
from evidenceguard_persistence import chunks as store
from evidenceguard_persistence import documents
from evidenceguard_persistence.documents import LockedRevision, RevisionNotFoundError
from evidenceguard_persistence.jobs import FencedSession

_DIALECT = postgresql.dialect()  # type: ignore[no-untyped-call]
T0 = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
TENANT = UUID("66666666-6666-4666-8666-666666666666")
REVISION = UUID("22222222-2222-4222-8222-222222222222")
DOCUMENT = UUID("88888888-8888-4888-8888-888888888888")
VERSION = "text-md-v1"
CONTENT_MARKER = "synthetic-private-content-marker"


def _sql(statement: Any) -> str:
    return " ".join(str(statement.compile(dialect=_DIALECT)).split())


def _job(tenant_id: UUID = TENANT, payload: dict[str, str] | None = None) -> JobSnapshot:
    return JobSnapshot(
        id=uuid4(),
        tenant_id=tenant_id,
        kind="ingest_revision",
        idempotency_key=str(REVISION),
        payload=JobPayload.from_mapping(payload or {"revision_id": str(REVISION)}),
        status=JobStatus.RUNNING,
        attempt=1,
        max_attempts=3,
        run_after=T0,
        locked_by="worker-test",
        lease_expires_at=T0 + timedelta(seconds=60),
        created_at=T0,
        updated_at=T0,
    )


def _revision(status: RevisionStatus) -> RevisionSnapshot:
    values: dict[str, Any] = {
        "id": REVISION,
        "tenant_id": TENANT,
        "document_id": DOCUMENT,
        "revision_no": 1,
        "status": status,
        "sha256": "a" * 64,
        "media_type": "text/markdown",
        "byte_size": 10,
        "created_at": T0,
        "updated_at": T0,
    }
    if status is RevisionStatus.ACTIVE:
        values["activated_at"] = T0
    if status is RevisionStatus.SUPERSEDED:
        values.update(activated_at=T0, superseded_at=T0, superseded_by_revision_id=uuid4())
    if status is RevisionStatus.FAILED:
        values.update(failure_reason=RevisionFailureCode.INGESTION_FAILED, failed_at=T0)
    return RevisionSnapshot.model_validate(values)


def _document(active: UUID | None = None) -> DocumentSnapshot:
    return DocumentSnapshot(
        id=DOCUMENT,
        tenant_id=TENANT,
        vendor_id=uuid4(),
        document_key="data-retention",
        title="Data retention",
        source_type=SourceType.VENDOR_STATEMENT,
        latest_revision_no=1,
        active_revision_id=active,
        created_at=T0,
        updated_at=T0,
    )


def _chunk(ordinal: int, text: str = "Chunk text.") -> Chunk:
    return Chunk(
        id=chunk_id(TENANT, REVISION, VERSION, ordinal),
        tenant_id=TENANT,
        revision_id=REVISION,
        chunker_version=VERSION,
        ordinal=ordinal,
        text=text,
        section_path=("Section",),
        is_table=False,
        line_start=ordinal + 1,
        line_end=ordinal + 1,
        char_start=ordinal * 100,
        char_end=ordinal * 100 + len(text),
    )


def _stored(chunk: Chunk, **changes: Any) -> dict[str, Any]:
    row = {name: getattr(chunk, name) for name in store.COMPARED_CHUNK_FIELDS}
    row["section_path"] = list(chunk.section_path)
    row.update(changes)
    return row


# --- the session double ------------------------------------------------------------------------


class _Row:
    def __init__(self, data: dict[str, Any]) -> None:
        self._mapping = data
        for key, value in data.items():
            setattr(self, key, value)


class _Result:
    def __init__(self, rows: list[dict[str, Any]] | None = None, scalars: Any = ()) -> None:
        self._rows = rows or []
        self._scalars = list(scalars)

    def first(self) -> _Row | None:
        return _Row(self._rows[0]) if self._rows else None

    def scalars(self) -> list[Any]:
        return self._scalars

    def __iter__(self) -> Any:
        return iter(_Row(row) for row in self._rows)


@dataclass
class Db:
    log: list[str] = field(default_factory=list)
    sql: list[str] = field(default_factory=list)
    status: RevisionStatus = RevisionStatus.PROCESSING
    set_inserted: bool = True
    stored_set: dict[str, Any] | None = None
    returned_ids: list[UUID] | None = None  # None: every inserted chunk is returned
    stored_chunks: list[dict[str, Any]] = field(default_factory=list)
    manifest_rows: list[dict[str, Any]] = field(default_factory=list)
    source: dict[str, Any] | None = None
    recheck_error: Exception | None = None
    recheck_tenant: UUID = TENANT
    status_value: str | None = "processing"

    def execute(self, statement: Any, params: Any = None) -> _Result:
        sql = _sql(statement)
        self.sql.append(sql)
        if sql.startswith("INSERT INTO chunk_sets"):
            self.log.append("insert_set")
            row = {"tenant_id": TENANT, "revision_id": REVISION}
            return _Result([row] if self.set_inserted else [])
        if sql.startswith("INSERT INTO chunks"):
            self.log.append("insert_chunks")
            ids = [
                value for key, value in statement.compile().params.items() if key.startswith("id")
            ]
            return _Result(scalars=ids if self.returned_ids is None else self.returned_ids)
        if "FROM chunk_sets" in sql:
            self.log.append("read_set")
            return _Result([self.stored_set] if self.stored_set else [])
        if "FROM chunks" in sql and "ORDER BY chunks.ordinal" in sql:
            self.log.append("read_manifest")
            return _Result(self.manifest_rows)
        if "FROM chunks" in sql:
            self.log.append("read_chunks")
            return _Result(self.stored_chunks)
        if "content_text" in sql:
            self.log.append("read_source")
            return _Result([self.source] if self.source else [])
        raise AssertionError(f"unexpected statement: {sql}")

    def scalar(self, statement: Any, params: Any = None) -> Any:
        self.sql.append(_sql(statement))
        self.log.append("read_status")
        return self.status_value


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> Db:
    database = Db()

    def lock(session: Any, job: JobSnapshot, *, include_active: bool) -> LockedRevision:
        assert include_active is False
        database.log.append("lock")
        return LockedRevision(
            document=_document(), target=_revision(database.status), active=None, now=T0
        )

    def recheck(session: Any, token: Any) -> tuple[JobSnapshot, datetime]:
        database.log.append("recheck")
        if database.recheck_error is not None:
            raise database.recheck_error
        return _job(database.recheck_tenant), T0

    monkeypatch.setattr(store, "lock_revision_for_job", lock)
    monkeypatch.setattr(store, "recheck_ownership", recheck)
    return database


def _session(db: Db) -> FencedSession:
    return cast(FencedSession, db)


# --- write_chunks ------------------------------------------------------------------------------


def test_new_chunks_lock_then_insert_then_recheck(db: Db) -> None:
    store.write_chunks(_session(db), _job(), [_chunk(0), _chunk(1)])

    assert db.log == ["lock", "insert_chunks", "recheck"]
    insert = db.sql[0]
    assert "ON CONFLICT DO NOTHING RETURNING chunks.id" in insert


@pytest.mark.parametrize(
    "status", [RevisionStatus.ACTIVE, RevisionStatus.SUPERSEDED, RevisionStatus.FAILED]
)
def test_writes_after_settlement_are_refused_before_any_insert(
    db: Db, status: RevisionStatus
) -> None:
    db.status = status
    with pytest.raises(store.ChunkWriteRefusedError):
        store.write_chunks(_session(db), _job(), [_chunk(0)])
    with pytest.raises(store.ChunkWriteRefusedError):
        store.write_chunk_set(_session(db), _job(), ExpectedChunkSet.of([_chunk(0)]))
    assert db.log == ["lock", "lock"]


def test_identical_existing_chunks_are_verified_and_accepted(db: Db) -> None:
    chunks = [_chunk(0), _chunk(1)]
    db.returned_ids = [chunks[1].id]
    db.stored_chunks = [_stored(chunks[0])]

    store.write_chunks(_session(db), _job(), chunks)

    assert db.log == ["lock", "insert_chunks", "read_chunks", "recheck"]
    lookup = db.sql[1]
    assert "chunks.tenant_id = " in lookup and "chunks.revision_id = " in lookup
    assert "chunks.chunker_version = " in lookup and "chunks.ordinal IN" in lookup
    assert "created_at" not in lookup  # creation time is metadata, never compared


def test_a_suppressed_conflict_whose_lookup_finds_no_row_is_a_conflict(db: Db) -> None:
    """ON CONFLICT DO NOTHING can suppress a conflict on the other unique key: the expected
    tuple then has no row, which is never an idempotent success."""
    db.returned_ids = []
    db.stored_chunks = []

    with pytest.raises(store.ChunkConflictError) as info:
        store.write_chunks(_session(db), _job(), [_chunk(0)])

    assert "recheck" not in db.log
    assert str(_chunk(0).id) not in str(info.value)


@pytest.mark.parametrize(
    "change",
    [
        {"text": CONTENT_MARKER},
        {"content_sha256": hashlib.sha256(b"other").hexdigest()},
        {"section_path": ["Other"]},
        {"is_table": True},
        {"line_end": 9},
        {"char_start": 1},
        {"header_char_start": 0},
        {"id": uuid4()},
    ],
)
def test_a_differing_immutable_field_is_a_conflict_without_overwrite(
    db: Db, change: dict[str, Any]
) -> None:
    db.returned_ids = []
    db.stored_chunks = [_stored(_chunk(0), **change)]

    with pytest.raises(store.ChunkConflictError) as info:
        store.write_chunks(_session(db), _job(), [_chunk(0)])

    assert not any(sql.startswith("UPDATE") or sql.startswith("DELETE") for sql in db.sql)
    assert CONTENT_MARKER not in str(info.value)


def test_a_lease_lost_at_the_final_recheck_propagates(db: Db) -> None:
    db.recheck_error = LeaseLostError()
    with pytest.raises(LeaseLostError):
        store.write_chunks(_session(db), _job(), [_chunk(0)])
    assert db.log == ["lock", "insert_chunks", "recheck"]


def test_a_tenant_change_at_the_final_recheck_is_lease_loss(db: Db) -> None:
    db.recheck_tenant = uuid4()
    with pytest.raises(LeaseLostError):
        store.write_chunks(_session(db), _job(), [_chunk(0)])


def test_invalid_batches_are_refused_before_any_sql(db: Db) -> None:
    other_tenant = uuid4()
    foreign = Chunk(
        id=chunk_id(other_tenant, REVISION, VERSION, 0),
        tenant_id=other_tenant,
        revision_id=REVISION,
        chunker_version=VERSION,
        ordinal=0,
        text="x",
        section_path=(),
        is_table=False,
        line_start=1,
        line_end=1,
        char_start=0,
        char_end=1,
    )
    for batch, error in (
        ([], TypeError),
        ([_chunk(index, "y") for index in range(201)], ValueError),
        ([foreign], ValueError),
        ([_chunk(0), _chunk(0)], ValueError),
    ):
        with pytest.raises(error):
            store.write_chunks(_session(db), _job(), batch)
    assert db.log == []


# --- write_chunk_set ---------------------------------------------------------------------------


def _expected() -> ExpectedChunkSet:
    return ExpectedChunkSet.of([_chunk(0), _chunk(1)])


def test_a_new_chunk_set_row_is_inserted_on_its_primary_key(db: Db) -> None:
    store.write_chunk_set(_session(db), _job(), _expected())

    assert db.log == ["lock", "insert_set", "recheck"]
    assert "ON CONFLICT ON CONSTRAINT pk_chunk_sets DO NOTHING" in db.sql[0]
    assert "RETURNING chunk_sets.tenant_id, chunk_sets.revision_id" in db.sql[0]


def test_an_identical_chunk_set_row_is_accepted(db: Db) -> None:
    expected = _expected()
    db.set_inserted = False
    db.stored_set = {
        "chunker_version": expected.chunker_version,
        "chunk_count": expected.chunk_count,
        "manifest_sha256": expected.manifest_sha256,
    }
    store.write_chunk_set(_session(db), _job(), expected)
    assert db.log == ["lock", "insert_set", "read_set", "recheck"]


@pytest.mark.parametrize(
    "stored",
    [
        None,
        {"chunker_version": "text-md-v2"},
        {"chunk_count": 3},
        {"manifest_sha256": "f" * 64},
    ],
)
def test_a_differing_or_missing_chunk_set_row_is_a_conflict(
    db: Db, stored: dict[str, Any] | None
) -> None:
    expected = _expected()
    db.set_inserted = False
    if stored is not None:
        db.stored_set = {
            "chunker_version": expected.chunker_version,
            "chunk_count": expected.chunk_count,
            "manifest_sha256": expected.manifest_sha256,
            **stored,
        }
    with pytest.raises(store.ChunkConflictError):
        store.write_chunk_set(_session(db), _job(), expected)
    assert "recheck" not in db.log


# --- completeness -------------------------------------------------------------------------------


def _complete(db: Db, chunks: list[Chunk]) -> ExpectedChunkSet:
    expected = ExpectedChunkSet.of(chunks)
    db.stored_set = {
        "chunker_version": expected.chunker_version,
        "chunk_count": expected.chunk_count,
        "manifest_sha256": expected.manifest_sha256,
    }
    db.manifest_rows = [
        {name: getattr(chunk, name) for name in store.MANIFEST_COLUMNS} for chunk in chunks
    ]
    for row, chunk in zip(db.manifest_rows, chunks, strict=True):
        row["section_path"] = list(chunk.section_path)
    return expected


def _check(db: Db, expected: ExpectedChunkSet) -> None:
    store.require_complete_chunk_set(
        _session(db), _revision(RevisionStatus.PROCESSING), expected=expected
    )


def test_a_complete_set_matching_the_attempt_passes_without_reading_text(db: Db) -> None:
    expected = _complete(db, [_chunk(0), _chunk(1), _chunk(2)])

    _check(db, expected)

    assert db.log == ["read_set", "read_manifest"]
    manifest_sql = db.sql[1]
    assert "chunks.text" not in manifest_sql and "chunks.tenant_id = " in manifest_sql


@pytest.mark.parametrize(
    "damage",
    ["no_set", "version", "count", "missing_ordinal", "stored_digest", "changed_field"],
)
def test_an_incomplete_or_different_set_is_refused(db: Db, damage: str) -> None:
    expected = _complete(db, [_chunk(0), _chunk(1), _chunk(2)])
    assert db.stored_set is not None
    if damage == "no_set":
        db.stored_set = None
    elif damage == "version":
        db.stored_set["chunker_version"] = "text-md-v2"
    elif damage == "count":
        db.stored_set["chunk_count"] = 4
    elif damage == "missing_ordinal":
        del db.manifest_rows[1]
    elif damage == "stored_digest":
        db.stored_set["manifest_sha256"] = "0" * 64
    else:
        db.manifest_rows[2]["line_end"] = 99

    with pytest.raises(store.ChunkSetIncompleteError):
        _check(db, expected)


def test_a_stored_set_differing_from_this_attempts_expectation_is_refused(db: Db) -> None:
    _complete(db, [_chunk(0), _chunk(1)])
    other_attempt = ExpectedChunkSet.of([_chunk(0), _chunk(1, "Different text.")])
    with pytest.raises(store.ChunkSetIncompleteError):
        _check(db, other_attempt)


# --- source and status ---------------------------------------------------------------------------


def _source_row(text: str) -> dict[str, Any]:
    data = text.encode()
    return {
        "status": "processing",
        "media_type": "text/markdown",
        "content_text": text,
        "sha256": hashlib.sha256(data).hexdigest(),
        "byte_size": len(data),
    }


def test_the_source_is_reverified_and_never_shown(db: Db) -> None:
    db.source = _source_row(f"# {CONTENT_MARKER}\n")

    source = store.load_revision_source(_session(db), _job())

    assert source.content.text == f"# {CONTENT_MARKER}\n"
    assert CONTENT_MARKER not in repr(source) and CONTENT_MARKER not in str(source)
    assert "document_revisions.tenant_id = " in db.sql[0]


def test_a_stored_source_whose_hash_does_not_match_is_an_integrity_error(db: Db) -> None:
    row = _source_row("text v1\n")
    row["content_text"] = "text v2\n"
    db.source = row
    with pytest.raises(InvalidRevisionContentError) as info:
        store.load_revision_source(_session(db), _job())
    assert "text v" not in str(info.value)


def test_a_missing_revision_is_not_found(db: Db) -> None:
    with pytest.raises(RevisionNotFoundError):
        store.load_revision_source(_session(db), _job())
    db.status_value = None
    with pytest.raises(RevisionNotFoundError):
        store.read_revision_status(_session(db), _job())


def test_the_status_read_is_tenant_scoped(db: Db) -> None:
    assert store.read_revision_status(_session(db), _job()) is RevisionStatus.PROCESSING
    assert "document_revisions.tenant_id = " in db.sql[0]


# --- before_settle in activate_revision ----------------------------------------------------------


class _Recorder:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, statement: Any, params: Any = None) -> None:
        self.statements.append(_sql(statement))


def _activation(
    monkeypatch: pytest.MonkeyPatch, status: RevisionStatus
) -> tuple[_Recorder, list[str]]:
    events: list[str] = []
    active = status is RevisionStatus.ACTIVE
    target = _revision(status)

    def lock(session: Any, job: JobSnapshot, *, include_active: bool) -> LockedRevision:
        assert include_active is True
        events.append("lock")
        return LockedRevision(
            document=_document(REVISION if active else None),
            target=target,
            active=target if active else None,
            now=T0,
        )

    monkeypatch.setattr(documents, "lock_revision_for_job", lock)
    return _Recorder(), events


def test_before_settle_runs_after_the_locks_and_before_any_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, events = _activation(monkeypatch, RevisionStatus.PROCESSING)

    def check(fenced: Any, revision: RevisionSnapshot) -> None:
        assert revision.id == REVISION
        assert session.statements == []
        events.append("check")

    documents.activate_revision(cast(FencedSession, session), _job(), before_settle=check)

    assert events == ["lock", "check"]
    assert session.statements and session.statements[0].startswith("UPDATE document_revisions")


def test_a_failing_before_settle_prevents_every_write(monkeypatch: pytest.MonkeyPatch) -> None:
    session, _ = _activation(monkeypatch, RevisionStatus.PROCESSING)

    def refuse(fenced: Any, revision: RevisionSnapshot) -> None:
        raise store.ChunkSetIncompleteError()

    with pytest.raises(store.ChunkSetIncompleteError):
        documents.activate_revision(cast(FencedSession, session), _job(), before_settle=refuse)
    assert session.statements == []


def test_a_duplicate_activation_of_a_settled_revision_skips_before_settle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, events = _activation(monkeypatch, RevisionStatus.ACTIVE)

    def never(fenced: Any, revision: RevisionSnapshot) -> None:
        raise AssertionError("before_settle must not run for a settled revision")

    result = documents.activate_revision(cast(FencedSession, session), _job(), before_settle=never)

    assert result.revision.status is RevisionStatus.ACTIVE and session.statements == []
    assert events == ["lock"]
