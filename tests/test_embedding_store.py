"""The embedding store (``evidenceguard_persistence.embeddings``), without a database (M4b,
ADR-0014).

A statement-level session double answers the module's statements (compiled for PostgreSQL)
from scripted rows and records them in order, and ``recheck_ownership`` is replaced by a
recorder. These are **protocol** tests: job binding, lock → work → re-check order, validation
before SQL, conflict comparison and fixed errors. They are not evidence of constraints, lock
waits, rollback or races; ``test_embeddings_postgres.py`` covers those against a real database
(run only in CI).
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError, OperationalError

from evidenceguard_domain.chunks import Chunk, chunk_id, chunks_manifest_sha256
from evidenceguard_domain.embedding_storage import (
    StoredEmbedding,
    StoredVector,
    index_id,
    profile_id,
    vector_manifest_sha256,
)
from evidenceguard_domain.embeddings import EmbeddingIdentity, InvalidEmbeddingError
from evidenceguard_domain.jobs import JobPayload, JobSnapshot, JobStatus, LeaseLostError
from evidenceguard_persistence import embeddings as store
from evidenceguard_persistence.chunks import MANIFEST_COLUMNS
from evidenceguard_persistence.jobs import FencedSession, JobLockTimeoutError
from evidenceguard_retrieval.embeddings import HASH_IDENTITY

_DIALECT = postgresql.dialect()  # type: ignore[no-untyped-call]
T0 = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
TENANT = UUID("66666666-6666-4666-8666-666666666666")
REVISION = UUID("22222222-2222-4222-8222-222222222222")
VERSION = "text-md-v1"
LIVE = EmbeddingIdentity("voyage", "voyage-4-lite", "adapter-v1", 1024, "l2")
PROFILE = profile_id(TENANT, HASH_IDENTITY.fingerprint)
INDEX = index_id(TENANT, REVISION, VERSION, PROFILE)
CONTENT_MARKER = "synthetic-private-content-marker"


def _sql(statement: Any) -> str:
    return " ".join(str(statement.compile(dialect=_DIALECT)).split())


def _chunk(ordinal: int) -> Chunk:
    text = f"Chunk {ordinal} {CONTENT_MARKER}."
    return Chunk(
        id=chunk_id(TENANT, REVISION, VERSION, ordinal),
        tenant_id=TENANT,
        revision_id=REVISION,
        chunker_version=VERSION,
        ordinal=ordinal,
        text=text,
        section_path=(),
        is_table=False,
        line_start=ordinal + 1,
        line_end=ordinal + 1,
        char_start=ordinal * 100,
        char_end=ordinal * 100 + len(text),
    )


CHUNKS = (_chunk(0), _chunk(1))
MANIFEST = chunks_manifest_sha256(CHUNKS)


def _vector(index: int = 0, value: float = 1.0) -> StoredVector:
    return StoredVector(tuple(value if i == index else 0.0 for i in range(1024)), allows_zero=True)


def _row(chunk: Chunk, vector: StoredVector | None = None) -> StoredEmbedding:
    return StoredEmbedding(chunk.id, chunk.content_sha256, vector or _vector(chunk.ordinal))


def _job(
    tenant_id: UUID = TENANT,
    kind: str = store.INDEX_REVISION_KIND,
    payload: dict[str, str] | None = None,
) -> JobSnapshot:
    return JobSnapshot(
        id=uuid4(),
        tenant_id=tenant_id,
        kind=kind,
        idempotency_key=str(INDEX),
        payload=JobPayload.from_mapping(payload or {"index_id": str(INDEX)}),
        status=JobStatus.RUNNING,
        attempt=1,
        max_attempts=3,
        run_after=T0,
        locked_by="worker-test",
        lease_expires_at=T0 + timedelta(seconds=60),
        created_at=T0,
        updated_at=T0,
    )


def _index_row(**changes: Any) -> dict[str, Any]:
    row = {
        "id": INDEX,
        "tenant_id": TENANT,
        "revision_id": REVISION,
        "chunker_version": VERSION,
        "chunk_count": len(CHUNKS),
        "manifest_sha256": MANIFEST,
        "profile_id": PROFILE,
        "dims": 1024,
        "allows_zero_vectors": True,
        "status": "building",
        "vector_manifest_sha256": None,
        "ready_at": None,
    }
    row.update(changes)
    return row


def _profile_row(**changes: Any) -> dict[str, Any]:
    row = {
        "id": PROFILE,
        "tenant_id": TENANT,
        "provider_id": HASH_IDENTITY.provider_id,
        "model_id": HASH_IDENTITY.model_id,
        "algorithm_version": HASH_IDENTITY.algorithm_version,
        "dims": 1024,
        "normalization": "l2",
        "fingerprint": HASH_IDENTITY.fingerprint,
        "allows_zero_vectors": True,
    }
    row.update(changes)
    return row


def _manifest_row(chunk: Chunk) -> dict[str, Any]:
    entry = dict(chunk.manifest_entry())
    entry["id"] = chunk.id
    entry["section_path"] = list(chunk.section_path)
    return {name: entry[name] for name in MANIFEST_COLUMNS}


def _member(chunk: Chunk, vector: StoredVector | None, **changes: Any) -> dict[str, Any]:
    row = {
        "ordinal": chunk.ordinal,
        "id": chunk.id,
        "content_sha256": chunk.content_sha256,
        "embedded_chunk_id": chunk.id if vector is not None else None,
        "embedded_content_sha256": chunk.content_sha256 if vector is not None else None,
        "vector_sha256": vector.sha256 if vector is not None else None,
    }
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
    index: dict[str, Any] | None = field(default_factory=_index_row)
    profile: dict[str, Any] | None = field(default_factory=_profile_row)
    chunk_digests: list[dict[str, Any]] = field(
        default_factory=lambda: [{"id": c.id, "content_sha256": c.content_sha256} for c in CHUNKS]
    )
    returned_ids: list[UUID] | None = None  # None: every inserted row is returned
    stored_rows: list[dict[str, Any]] = field(default_factory=list)
    insert_error: Exception | None = None
    lock_error: Exception | None = None
    chunk_set: dict[str, Any] | None = field(
        default_factory=lambda: {
            "chunker_version": VERSION,
            "chunk_count": len(CHUNKS),
            "manifest_sha256": MANIFEST,
        }
    )
    manifest_rows: list[dict[str, Any]] = field(
        default_factory=lambda: [_manifest_row(c) for c in CHUNKS]
    )
    members: list[dict[str, Any]] = field(
        default_factory=lambda: [_member(c, _vector(c.ordinal)) for c in CHUNKS]
    )
    count: int = len(CHUNKS)
    ready_row: dict[str, Any] | None = None
    recheck_error: Exception | None = None
    recheck_tenant: UUID = TENANT
    activation: dict[str, Any] | None = field(default_factory=lambda: {"activated_at": T0})
    inserted_profile: bool = True
    stored_index: dict[str, Any] | None = None

    def execute(self, statement: Any, params: Any = None) -> _Result:
        sql = _sql(statement)
        self.sql.append(sql)
        if sql.startswith("INSERT INTO chunk_embeddings"):
            self.log.append("insert")
            if self.insert_error is not None:
                raise self.insert_error
            ids = [
                value
                for key, value in statement.compile().params.items()
                if key.startswith("chunk_id")
            ]
            return _Result(scalars=ids if self.returned_ids is None else self.returned_ids)
        if sql.startswith("INSERT INTO embedding_profiles"):
            self.log.append("insert_profile")
            return _Result(scalars=[PROFILE] if self.inserted_profile else [])
        if sql.startswith("INSERT INTO embedding_indexes"):
            self.log.append("insert_index")
            return _Result(scalars=[INDEX])
        if sql.startswith("UPDATE embedding_indexes"):
            self.log.append("mark_ready")
            ready = self.ready_row or _index_row(
                status="ready", ready_at=T0, vector_manifest_sha256="f" * 64
            )
            return _Result([ready])
        if "FROM embedding_indexes" in sql and "FOR UPDATE" in sql:
            self.log.append("lock_index")
            if self.lock_error is not None:
                raise self.lock_error
            return _Result([self.index] if self.index else [])
        if "FROM embedding_indexes" in sql:
            self.log.append("read_index")
            stored = self.stored_index or self.index
            return _Result([stored] if stored else [])
        if "FROM embedding_profiles" in sql:
            self.log.append("read_profile")
            return _Result([self.profile] if self.profile else [])
        if "LEFT OUTER JOIN chunk_embeddings" in sql:
            self.log.append("read_members")
            return _Result(self.members)
        if "FROM chunk_embeddings" in sql:
            self.log.append("read_stored")
            return _Result(self.stored_rows)
        if "FROM chunk_sets" in sql:
            self.log.append("read_set")
            return _Result([self.chunk_set] if self.chunk_set else [])
        if "FROM chunks" in sql and "ORDER BY chunks.ordinal" in sql:
            self.log.append("read_manifest")
            return _Result(self.manifest_rows)
        if "FROM chunks" in sql:
            self.log.append("read_digests")
            return _Result(self.chunk_digests)
        if "FROM document_revisions" in sql:
            self.log.append("read_revision")
            return _Result([self.activation] if self.activation else [])
        raise AssertionError(f"unexpected statement: {sql}")

    def scalar(self, statement: Any, params: Any = None) -> Any:
        self.sql.append(_sql(statement))
        self.log.append("count")
        return self.count


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> Db:
    database = Db()

    def recheck(session: Any, token: Any) -> tuple[JobSnapshot, datetime]:
        database.log.append("recheck")
        if database.recheck_error is not None:
            raise database.recheck_error
        return _job(database.recheck_tenant), T0

    monkeypatch.setattr(store, "recheck_ownership", recheck)
    return database


def _session(db: Db) -> FencedSession:
    return cast(FencedSession, db)


def _write(db: Db, rows: list[StoredEmbedding] | None = None, **job: Any) -> None:
    store.write_embeddings(_session(db), _job(**job), HASH_IDENTITY, rows or [_row(CHUNKS[0])])


# --- write_embeddings ---------------------------------------------------------------------


def test_new_rows_bind_lock_verify_insert_then_recheck(db: Db) -> None:
    store.write_embeddings(_session(db), _job(), HASH_IDENTITY, [_row(CHUNKS[0]), _row(CHUNKS[1])])

    assert db.log == ["lock_index", "read_profile", "read_digests", "insert", "recheck"]
    lock, _, digests, insert = db.sql[:4]
    assert "embedding_indexes.tenant_id = " in lock and "embedding_indexes.id = " in lock
    assert lock.endswith("FOR UPDATE")
    for predicate in ("chunks.tenant_id = ", "chunks.revision_id = ", "chunks.chunker_version = "):
        assert predicate in digests
    assert "ON CONFLICT ON CONSTRAINT pk_chunk_embeddings DO NOTHING" in insert
    assert "RETURNING chunk_embeddings.chunk_id" in insert
    assert "CAST(" in insert and "AS VECTOR(1024))" in insert


def test_the_vector_is_bound_as_its_canonical_literal(db: Db) -> None:
    row = _row(CHUNKS[0])
    statement = store.insert_embeddings_statement(store._index(_Row(_index_row())), [row])
    params = statement.compile(dialect=_DIALECT).params
    assert row.vector.literal() in params.values()
    assert row.vector.sha256 in params.values()


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [_row(_chunk(0))] * 2,
        [StoredEmbedding(uuid4(), "a" * 64, _vector(0)) for _ in range(33)],
        ["not a row"],
    ],
)
def test_invalid_batches_are_refused_before_any_sql(db: Db, rows: list[Any]) -> None:
    with pytest.raises(InvalidEmbeddingError):
        store.write_embeddings(_session(db), _job(), HASH_IDENTITY, rows)
    assert db.sql == []


def test_zero_vectors_under_a_live_identity_are_refused_before_any_sql(db: Db) -> None:
    zero = StoredEmbedding(CHUNKS[0].id, CHUNKS[0].content_sha256, _vector(0, 0.0))
    with pytest.raises(InvalidEmbeddingError):
        store.write_embeddings(_session(db), _job(), LIVE, [zero])
    assert db.sql == []


def test_a_forged_row_is_refused_before_any_sql(db: Db) -> None:
    row = _row(CHUNKS[0])
    forged = tuple(0.5 if i == 0 else 0.0 for i in range(1024))  # not unit norm
    object.__setattr__(row.vector, "coordinates", forged)
    with pytest.raises(InvalidEmbeddingError):
        _write(db, [row])
    assert db.sql == []


@pytest.mark.parametrize(
    "job",
    [
        {"kind": "ingest_revision"},
        {"payload": {"revision_id": str(REVISION)}},
        {"payload": {"index_id": str(INDEX), "revision_id": str(REVISION)}},
    ],
)
def test_a_job_that_does_not_name_an_index_is_refused_before_any_sql(
    db: Db, job: dict[str, Any]
) -> None:
    with pytest.raises(store.IndexJobMismatchError):
        _write(db, **job)
    with pytest.raises(store.IndexJobMismatchError):
        store.mark_index_ready(_session(db), _job(**job), HASH_IDENTITY)
    assert db.sql == []


def test_a_missing_or_foreign_index_is_not_found(db: Db) -> None:
    db.index = None
    with pytest.raises(store.IndexNotFoundError):
        _write(db, tenant_id=uuid4())
    assert db.log == ["lock_index"]
    db.index = _index_row(tenant_id=uuid4())  # never trusted even if a row came back
    with pytest.raises(store.IndexNotFoundError):
        _write(db)


def test_writes_to_a_ready_index_are_refused_before_any_insert(db: Db) -> None:
    db.index = _index_row(status="ready", ready_at=T0, vector_manifest_sha256="f" * 64)
    with pytest.raises(store.EmbeddingWriteRefusedError):
        _write(db)
    assert db.log == ["lock_index"]


def test_a_different_profile_is_refused_before_any_insert(db: Db) -> None:
    db.profile = _profile_row(fingerprint="0" * 64)
    with pytest.raises(store.EmbeddingProfileMismatchError):
        _write(db)
    assert "insert" not in db.log


@pytest.mark.parametrize(
    "digests",
    [[], [{"id": CHUNKS[0].id, "content_sha256": "0" * 64}]],
)
def test_a_chunk_outside_the_revision_or_with_another_digest_is_refused(
    db: Db, digests: list[dict[str, Any]]
) -> None:
    db.chunk_digests = digests
    with pytest.raises(store.EmbeddingSourceMismatchError):
        _write(db)
    assert "insert" not in db.log


def test_identical_replay_is_verified_and_accepted(db: Db) -> None:
    row = _row(CHUNKS[0])
    db.returned_ids = []
    db.stored_rows = [
        {
            "chunk_id": row.chunk_id,
            "content_sha256": row.content_sha256,
            "vector_sha256": row.vector.sha256,
            "is_zero": False,
        }
    ]
    _write(db, [row])
    assert db.log == [
        "lock_index",
        "read_profile",
        "read_digests",
        "insert",
        "read_stored",
        "recheck",
    ]
    assert "created_at" not in db.sql[4]


@pytest.mark.parametrize(
    "change",
    [
        {"vector_sha256": "0" * 64},
        {"is_zero": True},
        {"content_sha256": "0" * 64},
        None,  # the suppressed conflict has no row
    ],
)
def test_a_differing_replay_is_a_conflict_without_overwrite(
    db: Db, change: dict[str, Any] | None
) -> None:
    row = _row(CHUNKS[0])
    db.returned_ids = []
    if change is not None:
        stored = {
            "chunk_id": row.chunk_id,
            "content_sha256": row.content_sha256,
            "vector_sha256": row.vector.sha256,
            "is_zero": False,
        }
        db.stored_rows = [{**stored, **change}]
    with pytest.raises(store.EmbeddingConflictError) as info:
        _write(db, [row])
    assert "recheck" not in db.log
    assert not any(sql.startswith(("UPDATE", "DELETE")) for sql in db.sql)
    assert str(row.chunk_id) not in str(info.value) and row.vector.sha256 not in str(info.value)


def test_a_database_rejection_is_a_fixed_error_without_the_driver_error(db: Db) -> None:
    db.insert_error = IntegrityError("INSERT", {}, Exception(f"Failing row {CONTENT_MARKER}"))
    with pytest.raises(store.EmbeddingStorageRejectedError) as info:
        _write(db)
    assert CONTENT_MARKER not in str(info.value)
    assert info.value.__cause__ is None and info.value.__context__ is None
    assert "recheck" not in db.log


def test_a_lock_timeout_maps_to_the_job_lock_timeout(db: Db) -> None:
    class Timeout(Exception):
        sqlstate = "55P03"

    db.lock_error = OperationalError("SELECT", {}, Timeout())
    with pytest.raises(JobLockTimeoutError):
        _write(db)


def test_lease_loss_at_the_final_recheck_propagates(db: Db) -> None:
    db.recheck_error = LeaseLostError()
    with pytest.raises(LeaseLostError):
        _write(db)
    assert db.log[-1] == "recheck"


def test_a_tenant_change_at_the_final_recheck_is_lease_loss(db: Db) -> None:
    db.recheck_tenant = uuid4()
    with pytest.raises(LeaseLostError):
        _write(db)


# --- mark_index_ready and completeness ----------------------------------------------------


def _ready(db: Db) -> store.IndexSnapshot:
    return store.mark_index_ready(_session(db), _job(), HASH_IDENTITY)


def test_a_complete_index_is_verified_then_marked_ready_then_rechecked(db: Db) -> None:
    result = _ready(db)

    assert db.log == [
        "lock_index",
        "read_profile",
        "read_set",
        "read_manifest",
        "read_members",
        "count",
        "mark_ready",
        "recheck",
    ]
    update = db.sql[6]
    assert "SET status=" in update and "ready_at=clock_timestamp()" in update
    assert "embedding_indexes.status = " in update  # only a building index transitions
    assert "embedding_indexes.tenant_id = " in update
    members = db.sql[4]
    assert "embedding" not in members.replace("chunk_embeddings", "").replace("embedded_", "")
    assert "chunks.text" not in members
    assert result.status == "ready"


def test_the_recorded_vector_manifest_is_built_from_stored_digests(
    db: Db, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[str] = []
    original = store.mark_ready_statement

    def spy(index: store.IndexSnapshot, manifest: str) -> Any:
        captured.append(manifest)
        return original(index, manifest)

    monkeypatch.setattr(store, "mark_ready_statement", spy)
    _ready(db)
    expected = vector_manifest_sha256(
        (c.ordinal, c.id, c.content_sha256, _vector(c.ordinal).sha256) for c in CHUNKS
    )
    assert captured == [expected]


def test_an_already_ready_index_is_a_rechecked_no_op(db: Db) -> None:
    db.index = _index_row(status="ready", ready_at=T0, vector_manifest_sha256="f" * 64)
    result = _ready(db)
    assert db.log == ["lock_index", "read_profile", "recheck"]
    assert result.status == "ready"


def test_a_stale_lease_on_the_already_ready_no_op_is_lease_loss(db: Db) -> None:
    db.index = _index_row(status="ready", ready_at=T0, vector_manifest_sha256="f" * 64)
    db.recheck_error = LeaseLostError()
    with pytest.raises(LeaseLostError):
        _ready(db)
    assert "mark_ready" not in db.log


def test_an_already_ready_index_with_another_profile_is_refused(db: Db) -> None:
    db.index = _index_row(status="ready", ready_at=T0, vector_manifest_sha256="f" * 64)
    with pytest.raises(store.EmbeddingProfileMismatchError):
        store.mark_index_ready(_session(db), _job(), LIVE)
    assert "recheck" not in db.log


def _incomplete(db: Db) -> None:
    with pytest.raises(store.IndexIncompleteError) as info:
        _ready(db)
    assert "mark_ready" not in db.log and "recheck" not in db.log
    assert str(CHUNKS[0].id) not in str(info.value)


def test_a_missing_embedding_refuses_readiness(db: Db) -> None:
    db.members = [_member(CHUNKS[0], _vector(0)), _member(CHUNKS[1], None)]
    db.count = 1
    _incomplete(db)


def test_an_embedding_with_another_text_digest_refuses_readiness(db: Db) -> None:
    db.members[1] = _member(CHUNKS[1], _vector(1), embedded_content_sha256="0" * 64)
    _incomplete(db)


def test_a_row_count_other_than_the_chunk_count_refuses_readiness(db: Db) -> None:
    db.count = 3
    _incomplete(db)


def test_a_gap_in_member_ordinals_refuses_readiness(db: Db) -> None:
    db.members = [_member(CHUNKS[0], _vector(0))]
    _incomplete(db)


@pytest.mark.parametrize(
    "chunk_set",
    [
        None,
        {"chunker_version": VERSION, "chunk_count": 3, "manifest_sha256": MANIFEST},
        {"chunker_version": VERSION, "chunk_count": 2, "manifest_sha256": "0" * 64},
    ],
)
def test_a_chunk_set_that_differs_from_the_binding_refuses_readiness(
    db: Db, chunk_set: dict[str, Any] | None
) -> None:
    db.chunk_set = chunk_set
    _incomplete(db)


def test_a_manifest_rebuilt_differently_refuses_readiness(db: Db) -> None:
    db.manifest_rows[1] = {**db.manifest_rows[1], "line_end": 99}
    _incomplete(db)


def test_missing_manifest_rows_refuse_readiness(db: Db) -> None:
    db.manifest_rows = db.manifest_rows[:1]
    _incomplete(db)


@pytest.mark.parametrize(
    "change",
    [
        {"fingerprint": "0" * 64},  # stored fields no longer hash to the fingerprint
        {"model_id": "other-model"},
        {"id": uuid4()},  # not the deterministic profile ID
        {"normalization": "none"},
    ],
)
def test_an_inconsistent_profile_refuses_readiness(db: Db, change: dict[str, Any]) -> None:
    db.profile = _profile_row(**change)
    _incomplete(db)


def test_readiness_for_another_identity_is_refused(db: Db) -> None:
    with pytest.raises(store.IndexIncompleteError):
        store.mark_index_ready(_session(db), _job(), LIVE)
    assert "mark_ready" not in db.log


def test_completeness_does_not_call_the_m3_activation_callback(
    db: Db, monkeypatch: pytest.MonkeyPatch
) -> None:
    from evidenceguard_persistence import chunks as chunk_store

    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("require_complete_chunk_set must not be called")

    monkeypatch.setattr(chunk_store, "require_complete_chunk_set", forbidden)
    _ready(db)
    assert not any("document_revisions" in sql for sql in db.sql)  # no revision read or lock


# --- metadata in the caller's transaction ------------------------------------------------


def test_ensure_profile_inserts_then_verifies_the_stored_identity(db: Db) -> None:
    profile = store.ensure_profile(cast(Any, db), TENANT, HASH_IDENTITY)
    assert db.log == ["insert_profile", "read_profile"]
    insert = db.sql[0]
    assert (
        "ON CONFLICT ON CONSTRAINT uq_embedding_profiles_tenant_id_fingerprint DO NOTHING" in insert
    )
    assert profile.id == PROFILE and profile.allows_zero_vectors is True
    assert "recheck" not in db.log  # no fence: the caller's transaction


@pytest.mark.parametrize(
    "change", [{"model_id": "other-model"}, {"allows_zero_vectors": False}, {"id": uuid4()}]
)
def test_ensure_profile_refuses_a_differing_stored_profile(db: Db, change: dict[str, Any]) -> None:
    db.profile = _profile_row(**change)
    with pytest.raises(store.EmbeddingProfileConflictError):
        store.ensure_profile(cast(Any, db), TENANT, HASH_IDENTITY)


def test_ensure_profile_refuses_unstorable_identities_before_any_sql(db: Db) -> None:
    small = EmbeddingIdentity("offline", "fake-hash-v1", "ascii-word-sha256-v1", 8, "l2")
    with pytest.raises(InvalidEmbeddingError):
        store.ensure_profile(cast(Any, db), TENANT, small)
    assert db.sql == []


def _profile_snapshot() -> store.ProfileSnapshot:
    return store.ProfileSnapshot(**_profile_row())


def test_create_index_copies_the_chunk_set_binding(db: Db) -> None:
    index = store.create_index(cast(Any, db), TENANT, REVISION, _profile_snapshot())
    assert db.log == ["read_revision", "read_set", "read_profile", "insert_index", "read_index"]
    insert = db.sql[3]
    assert "ON CONFLICT ON CONSTRAINT uq_embedding_indexes_source DO NOTHING" in insert
    assert index.id == INDEX and index.status == "building" and index.ready_at is None
    assert (index.chunk_count, index.manifest_sha256) == (len(CHUNKS), MANIFEST)


@pytest.mark.parametrize(
    ("activation", "chunk_set"),
    [
        (None, True),  # missing from the tenant
        ({"activated_at": None}, True),  # never activated
        ({"activated_at": T0}, False),  # no chunk set
    ],
)
def test_create_index_requires_an_activated_revision_with_a_chunk_set(
    db: Db, activation: dict[str, Any] | None, chunk_set: bool
) -> None:
    db.activation = activation
    if not chunk_set:
        db.chunk_set = None
    with pytest.raises(store.IndexSourceNotEligibleError):
        store.create_index(cast(Any, db), TENANT, REVISION, _profile_snapshot())
    assert "insert_index" not in db.log


def test_create_index_refuses_a_profile_from_another_tenant(db: Db) -> None:
    foreign = store.ProfileSnapshot(**_profile_row(tenant_id=uuid4()))
    with pytest.raises(store.IndexSourceNotEligibleError):
        store.create_index(cast(Any, db), TENANT, REVISION, foreign)
    assert db.sql == []


def test_create_index_refuses_a_differing_existing_index(db: Db) -> None:
    db.stored_index = _index_row(manifest_sha256="0" * 64)
    with pytest.raises(store.IndexConflictError):
        store.create_index(cast(Any, db), TENANT, REVISION, _profile_snapshot())
