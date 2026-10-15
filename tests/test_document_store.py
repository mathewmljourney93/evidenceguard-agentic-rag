"""Document and revision persistence (``evidenceguard_persistence.documents``) without a database.

A scripted database double answers the module's statements (compiled for PostgreSQL) from
in-memory rows and records every statement, so the tests can check tenant scoping, the lock
order, the fresh ownership re-check after the locks and the write order. A fake job store built
on the same double drives the real worker runtime through the two uncertain-commit cases and the
permanent-failure seam, using controlled commit failures.

These are simulations: real PostgreSQL behaviour (constraints, locks, rollback) is covered by
``test_documents_postgres.py``, which runs only in CI.
"""

import copy
import hashlib
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from evidenceguard_domain import jobs as lifecycle
from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_domain.errors import PermissionDeniedError
from evidenceguard_domain.evidence import SourceType
from evidenceguard_domain.jobs import (
    JobErrorCode,
    JobLeaseToken,
    JobPayload,
    JobSnapshot,
    JobStatus,
    LeaseLostError,
)
from evidenceguard_domain.revisions import (
    RevisionContent,
    RevisionFailureCode,
    RevisionStatus,
)
from evidenceguard_persistence import documents as store
from evidenceguard_persistence.jobs import FencedSession, JobLockTimeoutError
from evidenceguard_persistence.models import DocumentRevision
from evidenceguard_worker.context import JobContext, PermanentJobError
from evidenceguard_worker.registry import HandlerRegistry
from evidenceguard_worker.runtime import Timings, WorkerOutcome, run_worker

_DIALECT = postgresql.dialect()  # type: ignore[no-untyped-call]
T0 = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)
TENANT = UUID("66666666-6666-4666-8666-666666666666")
OTHER_TENANT = UUID("77777777-7777-4777-8777-777777777777")
WORKER = "worker-test"
REVIEWER = ActorContext(tenant_id=TENANT, actor_id=uuid4(), role=Role.REVIEWER)
# Obviously fake marker standing in for private document text.
CONTENT_MARKER = "synthetic-private-content-marker"


def _sql(statement: Any) -> str:
    return " ".join(str(statement.compile(dialect=_DIALECT)).split())


def _content(text: str = "policy text v1\n") -> RevisionContent:
    return RevisionContent.from_bytes(text.encode(), "text/markdown")


class CommitFailed(SQLAlchemyError):
    """Stands in for a failed COMMIT or a lost commit acknowledgment."""


# --- the scripted database ---------------------------------------------------------------------


class _Row:
    def __init__(self, data: dict[str, Any]) -> None:
        self._mapping = data


class _Result:
    def __init__(self, rows: list[dict[str, Any]] | None = None, scalar: Any = None) -> None:
        self._rows = rows or []
        self._scalar = scalar

    def first(self) -> _Row | None:
        return _Row(self._rows[0]) if self._rows else None

    def one(self) -> _Row:
        assert len(self._rows) == 1
        return _Row(self._rows[0])

    def scalar(self) -> Any:
        if self._scalar is not None:
            return self._scalar
        return next(iter(self._rows[0].values())) if self._rows else None

    def __iter__(self) -> Iterator[_Row]:
        return iter(_Row(row) for row in self._rows)


class ScriptedDb:
    """In-memory rows answering exactly the statements of the documents module and the fence
    re-check. ``log`` records a short name for every statement, in order."""

    def __init__(self) -> None:
        self.vendors: set[tuple[UUID, UUID]] = set()
        self.documents: dict[UUID, dict[str, Any]] = {}
        self.revisions: dict[UUID, dict[str, Any]] = {}
        self.jobs: dict[UUID, JobSnapshot] = {}
        self.now = T0
        self.log: list[str] = []
        self.params: list[dict[str, Any]] = []
        self.fail_on: dict[str, Exception] = {}
        self.hide_documents = False
        self.activations = 0

    # Seeding helpers -----------------------------------------------------------------------

    def vendor(self, tenant_id: UUID = TENANT) -> UUID:
        vendor_id = uuid4()
        self.vendors.add((tenant_id, vendor_id))
        return vendor_id

    def document(self, tenant_id: UUID = TENANT, **overrides: Any) -> UUID:
        document_id = uuid4()
        row: dict[str, Any] = {
            "id": document_id,
            "tenant_id": tenant_id,
            "vendor_id": uuid4(),
            "document_key": "policy",
            "title": "Policy",
            "source_type": "vendor_statement",
            "authenticity": "not_established",
            "latest_revision_no": 0,
            "active_revision_id": None,
            "created_at": T0,
            "updated_at": T0,
        }
        row.update(overrides)
        self.documents[document_id] = row
        return document_id

    def revision(
        self, document_id: UUID, revision_no: int, status: str = "processing", **overrides: Any
    ) -> UUID:
        revision_id = uuid4()
        tenant_id = self.documents[document_id]["tenant_id"]
        row: dict[str, Any] = {
            "id": revision_id,
            "tenant_id": tenant_id,
            "document_id": document_id,
            "revision_no": revision_no,
            "version_label": None,
            "effective_date": None,
            "status": status,
            "failure_reason": None,
            "sha256": hashlib.sha256(str(revision_id).encode()).hexdigest(),
            "media_type": "text/markdown",
            "byte_size": 10,
            "content_text": "x" * 10,
            "activated_at": T0 if status == "active" else None,
            "failed_at": None,
            "superseded_at": None,
            "superseded_by_revision_id": None,
            "created_at": T0,
            "updated_at": T0,
        }
        row.update(overrides)
        self.revisions[revision_id] = row
        doc = self.documents[document_id]
        doc["latest_revision_no"] = max(doc["latest_revision_no"], revision_no)
        if status == "active":
            doc["active_revision_id"] = revision_id
        return revision_id

    def job(
        self, revision_id: UUID, tenant_id: UUID = TENANT, *, running: bool = True
    ) -> JobSnapshot:
        job = JobSnapshot(
            id=uuid4(),
            tenant_id=tenant_id,
            kind="test_ingest",
            idempotency_key=str(revision_id),
            payload=JobPayload.from_mapping({"revision_id": str(revision_id)}),
            status=JobStatus.QUEUED,
            attempt=0,
            max_attempts=3,
            run_after=T0 - timedelta(seconds=1),
            created_at=T0,
            updated_at=T0,
        )
        if running:
            job = lifecycle.claim(job, worker_id=WORKER, now=self.now)
        self.jobs[job.id] = job
        return job

    # Answering statements ------------------------------------------------------------------

    def execute(self, statement: Any) -> _Result:
        compiled = statement.compile(dialect=_DIALECT)
        sql = " ".join(str(compiled).split())
        params = dict(compiled.params)
        name = self._classify(sql)
        self.log.append(name)
        self.params.append(params)
        if name in self.fail_on:
            raise self.fail_on[name]
        return cast(_Result, getattr(self, f"_{name}")(params))

    @staticmethod
    def _classify(sql: str) -> str:
        if sql.startswith("SELECT vendors.id"):
            return "vendor"
        if sql.startswith("INSERT INTO documents"):
            return "insert_document"
        if sql.startswith("INSERT INTO document_revisions"):
            return "insert_revision"
        if sql.startswith("UPDATE documents SET latest_revision_no"):
            return "allocate"
        if sql.startswith("UPDATE documents SET active_revision_id"):
            return "update_pointer"
        if sql.startswith("UPDATE document_revisions"):
            return "update_revision"
        if sql.startswith("SELECT document_revisions.document_id"):
            return "revision_document"
        if sql.startswith("SELECT document_revisions.status"):
            return "read_status"
        if "AS db_now" in sql:
            return "recheck"
        if "FROM documents" in sql and "documents.document_key =" in sql:
            assert sql.endswith("FOR UPDATE")
            return "lock_document_by_key"
        if "FROM documents" in sql:
            assert sql.endswith("FOR UPDATE")
            return "lock_document"
        if "FROM document_revisions" in sql and "document_revisions.sha256 =" in sql:
            return "revision_by_content"
        if "FROM document_revisions" in sql:
            assert "ORDER BY document_revisions.id FOR UPDATE" in sql
            return "lock_revisions"
        raise AssertionError(f"unexpected statement: {sql[:80]}")

    def _vendor(self, p: dict[str, Any]) -> _Result:
        found = (p["tenant_id_1"], p["id_1"]) in self.vendors
        return _Result([{"id": p["id_1"]}] if found else [])

    def _insert_document(self, p: dict[str, Any]) -> _Result:
        if not any(
            (d["tenant_id"], d["vendor_id"], d["document_key"])
            == (p["tenant_id"], p["vendor_id"], p["document_key"])
            for d in self.documents.values()
        ):
            self.documents[p["id"]] = {
                **{k: p[k] for k in ("id", "tenant_id", "vendor_id", "document_key", "title")},
                "source_type": p["source_type"],
                "authenticity": "not_established",
                "latest_revision_no": 0,
                "active_revision_id": None,
                "created_at": self.now,
                "updated_at": self.now,
            }
        return _Result()

    def _lock_document_by_key(self, p: dict[str, Any]) -> _Result:
        if self.hide_documents:
            return _Result()
        rows = [
            dict(d)
            for d in self.documents.values()
            if (d["tenant_id"], d["vendor_id"], d["document_key"])
            == (p["tenant_id_1"], p["vendor_id_1"], p["document_key_1"])
        ]
        return _Result(rows)

    def _revision_by_content(self, p: dict[str, Any]) -> _Result:
        rows = [
            _without_content(r)
            for r in self.revisions.values()
            if (r["tenant_id"], r["document_id"], r["sha256"])
            == (p["tenant_id_1"], p["document_id_1"], p["sha256_1"])
        ]
        return _Result(rows)

    def _allocate(self, p: dict[str, Any]) -> _Result:
        doc = self.documents[p["id_1"]]
        assert doc["tenant_id"] == p["tenant_id_1"]
        doc.update(latest_revision_no=p["latest_revision_no"], updated_at=self.now)
        return _Result([dict(doc)])

    def _insert_revision(self, p: dict[str, Any]) -> _Result:
        row = {
            **p,
            "failure_reason": None,
            "activated_at": None,
            "failed_at": None,
            "superseded_at": None,
            "superseded_by_revision_id": None,
            "created_at": self.now,
            "updated_at": self.now,
        }
        self.revisions[p["id"]] = row
        return _Result([_without_content(row)])

    def _revision_document(self, p: dict[str, Any]) -> _Result:
        r = self.revisions.get(p["id_1"])
        if r is None or r["tenant_id"] != p["tenant_id_1"]:
            return _Result()
        return _Result([{"document_id": r["document_id"]}])

    def _lock_document(self, p: dict[str, Any]) -> _Result:
        d = self.documents.get(p["id_1"])
        return _Result([dict(d)] if d is not None and d["tenant_id"] == p["tenant_id_1"] else [])

    def _lock_revisions(self, p: dict[str, Any]) -> _Result:
        ids = p["id_1"]
        assert list(ids) == sorted(ids), "revisions must be locked in ascending ID order"
        rows = [
            _without_content(self.revisions[i])
            for i in ids
            if i in self.revisions
            and self.revisions[i]["tenant_id"] == p["tenant_id_1"]
            and self.revisions[i]["document_id"] == p["document_id_1"]
        ]
        return _Result(rows)

    def _recheck(self, p: dict[str, Any]) -> _Result:
        job = self.jobs.get(p["id_1"])
        if job is None:
            return _Result()
        data = job.model_dump()
        data["payload"] = job.payload.as_dict()
        data["db_now"] = self.now
        return _Result([data])

    def _update_revision(self, p: dict[str, Any]) -> _Result:
        row = self.revisions[p["id_1"]]
        assert row["tenant_id"] == p["tenant_id_1"]
        if p["status"] == "active" and row["status"] != "active":
            self.activations += 1
        row.update({k: v for k, v in p.items() if k in row})
        return _Result()

    def _update_pointer(self, p: dict[str, Any]) -> _Result:
        doc = self.documents[p["id_1"]]
        doc.update(active_revision_id=p["active_revision_id"], updated_at=p["updated_at"])
        return _Result()

    def _read_status(self, p: dict[str, Any]) -> _Result:
        r = self.revisions[p["id_1"]]
        assert r["tenant_id"] == p["tenant_id_1"]
        return _Result([{"status": r["status"]}])

    # Transactions (for the fake job store) ------------------------------------------------------

    def snapshot(self) -> tuple[Any, ...]:
        return copy.deepcopy((self.documents, self.revisions, self.jobs, self.activations))

    def restore(self, state: tuple[Any, ...]) -> None:
        self.documents, self.revisions, self.jobs, self.activations = copy.deepcopy(state)


def _without_content(row: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if k != "content_text"}


class ScriptedSession:
    """A session double: statements go to the scripted database; transaction calls are recorded
    so tests can show the module never commits or rolls back."""

    def __init__(self, db: ScriptedDb) -> None:
        self.db = db
        self.events: list[str] = []

    def execute(self, statement: Any, params: Any = None) -> _Result:
        return self.db.execute(statement)

    def scalar(self, statement: Any, params: Any = None) -> Any:
        return self.db.execute(statement).scalar()

    def commit(self) -> None:
        self.events.append("commit")

    def rollback(self) -> None:
        self.events.append("rollback")


class _OpenFence:
    def _require_open(self) -> None:
        return None


def fenced(db: ScriptedDb) -> tuple[FencedSession, ScriptedSession]:
    session = ScriptedSession(db)
    return FencedSession(cast(Any, session), cast(Any, _OpenFence())), session


# --- statements ----------------------------------------------------------------------------------


def test_every_statement_is_tenant_scoped_and_locks_in_order() -> None:
    tenant, other = uuid4(), uuid4()
    for statement in (
        store.vendor_statement(tenant, other),
        store.lock_document_by_key_statement(tenant, other, "key"),
        store.revision_by_content_statement(tenant, other, "a" * 64),
        store.allocate_statement(tenant, other, 1),
        store.revision_document_statement(tenant, other),
        store.lock_document_statement(tenant, other),
        store.lock_revisions_statement(tenant, other, {other}),
    ):
        assert "tenant_id = %(tenant_id_1)s::UUID" in _sql(statement)
    assert _sql(store.lock_document_statement(tenant, other)).endswith("FOR UPDATE")
    assert _sql(store.lock_revisions_statement(tenant, other, {other})).endswith(
        "ORDER BY document_revisions.id FOR UPDATE"
    )
    assert "content_text" not in _sql(store.lock_revisions_statement(tenant, other, {other}))
    assert "now()" not in _sql(store.lock_document_statement(tenant, other))


def test_the_revision_lock_lists_ids_in_ascending_order() -> None:
    ids = [uuid4() for _ in range(5)]
    params = (
        store.lock_revisions_statement(TENANT, uuid4(), set(ids)).compile(dialect=_DIALECT).params
    )

    assert params["id_1"] == sorted(ids)


def test_lifecycle_updates_write_only_mutable_fields() -> None:
    sql = _sql(store.update_revision_statement(_snapshot_of(_seeded_revision())))

    for immutable in ("content_text", "sha256", "revision_no", "version_label", "document_id"):
        assert f"{immutable}=" not in sql


def _seeded_revision() -> dict[str, Any]:
    db = ScriptedDb()
    doc = db.document()
    return db.revisions[db.revision(doc, 1)]


def _snapshot_of(row: dict[str, Any]) -> Any:
    from evidenceguard_domain.revisions import RevisionSnapshot

    return RevisionSnapshot.model_validate(_without_content(row))


# --- creation ---------------------------------------------------------------------------------


def _create(db: ScriptedDb, session: ScriptedSession, vendor_id: UUID, **overrides: Any) -> Any:
    args: dict[str, Any] = {
        "vendor_id": vendor_id,
        "document_key": "data-retention",
        "title": "Data retention",
        "source_type": SourceType.VENDOR_STATEMENT,
        "content": _content(),
    }
    args.update(overrides)
    actor = args.pop("actor", REVIEWER)
    return store.create_revision(cast(Any, session), actor, **args)


def test_creation_locks_the_document_before_allocating_and_never_commits() -> None:
    db = ScriptedDb()
    session = ScriptedSession(db)
    vendor = db.vendor()

    result = _create(db, session, vendor, version_label=" v1 ", effective_date=date(2026, 1, 1))

    assert db.log == [
        "vendor",
        "insert_document",
        "lock_document_by_key",
        "revision_by_content",
        "allocate",
        "insert_revision",
    ]
    assert result.created and result.revision.revision_no == 1
    assert result.revision.status is RevisionStatus.PENDING
    assert result.revision.version_label == " v1 "  # kept exactly
    assert result.document.latest_revision_no == 1
    stored = db.revisions[result.revision.id]
    assert stored["content_text"] == "policy text v1\n"
    assert session.events == []


def test_new_content_gets_the_next_number_and_identical_content_returns_the_revision() -> None:
    db = ScriptedDb()
    session = ScriptedSession(db)
    vendor = db.vendor()
    first = _create(db, session, vendor)
    second = _create(db, session, vendor, content=_content("policy text v2\n"))
    db.log.clear()

    again = _create(db, session, vendor)

    assert second.revision.revision_no == 2
    assert not again.created and again.revision.id == first.revision.id
    assert "allocate" not in db.log and "insert_revision" not in db.log


def test_identical_content_returns_a_failed_revision_too() -> None:
    db = ScriptedDb()
    session = ScriptedSession(db)
    vendor = db.vendor()
    first = _create(db, session, vendor)
    db.revisions[first.revision.id].update(
        status="failed", failure_reason="ingestion_failed", failed_at=T0
    )

    again = _create(db, session, vendor)

    assert not again.created and again.revision.status is RevisionStatus.FAILED


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"title": "Another title"}, store.DocumentConflictError),
        ({"source_type": SourceType.CONTRACT}, store.DocumentConflictError),
        ({"version_label": "v9"}, store.RevisionConflictError),
        ({"effective_date": date(2030, 1, 1)}, store.RevisionConflictError),
    ],
)
def test_metadata_differences_are_conflicts_that_change_nothing(
    overrides: dict[str, Any], error: type[Exception]
) -> None:
    db = ScriptedDb()
    session = ScriptedSession(db)
    vendor = db.vendor()
    _create(db, session, vendor)
    before = db.snapshot()
    db.log.clear()

    with pytest.raises(error):
        _create(db, session, vendor, **overrides)

    assert "allocate" not in db.log and "insert_revision" not in db.log
    assert db.snapshot() == before


def test_a_vendor_outside_the_tenant_is_not_found() -> None:
    db = ScriptedDb()
    other_vendor = db.vendor(OTHER_TENANT)

    with pytest.raises(store.VendorNotFoundError):
        _create(db, ScriptedSession(db), other_vendor)
    assert db.log == ["vendor"]


def test_an_invisible_document_row_is_a_fixed_race_error() -> None:
    db = ScriptedDb()
    db.hide_documents = True

    with pytest.raises(store.RevisionCreateRaceError):
        _create(db, ScriptedSession(db), db.vendor())


@pytest.mark.parametrize(
    "overrides",
    [
        {"actor": ActorContext(tenant_id=TENANT, actor_id=uuid4(), role=Role.ADMIN)},
        {"document_key": "Not A Key"},
        {"title": "   "},
        {"version_label": ""},
        {"source_type": "brochure"},
        {"content": "raw text"},
        {"effective_date": datetime(2026, 1, 1, tzinfo=UTC)},
    ],
)
def test_invalid_requests_are_refused_before_any_sql(overrides: dict[str, Any]) -> None:
    db = ScriptedDb()

    with pytest.raises((PermissionDeniedError, ValueError, TypeError)):
        _create(db, ScriptedSession(db), db.vendor(), **overrides)
    assert db.log == []


# --- fenced transitions -------------------------------------------------------------------------


def test_start_processing_locks_then_rechecks_with_fresh_time_then_writes() -> None:
    db = ScriptedDb()
    doc = db.document()
    rid = db.revision(doc, 1, "pending")
    job = db.job(rid)
    db.now = T0 + timedelta(seconds=7)
    session, raw = fenced(db)

    updated = store.start_processing(session, job)

    assert db.log == [
        "revision_document",
        "lock_document",
        "lock_revisions",
        "recheck",
        "update_revision",
    ]
    assert updated.status is RevisionStatus.PROCESSING
    assert updated.updated_at == db.now  # the re-check's time, not the snapshot's
    assert raw.events == []


def test_repeating_start_processing_writes_nothing() -> None:
    db = ScriptedDb()
    rid = db.revision(db.document(), 1, "processing")

    store.start_processing(fenced(db)[0], db.job(rid))

    assert "update_revision" not in db.log


def test_an_expired_lease_at_the_recheck_refuses_before_any_write() -> None:
    db = ScriptedDb()
    rid = db.revision(db.document(), 1, "processing")
    job = db.job(rid)
    db.now = job.lease_expires_at or T0  # expired exactly at the re-check

    with pytest.raises(LeaseLostError):
        store.activate_revision(fenced(db)[0], job)
    assert db.log[-1] == "recheck"
    assert db.revisions[rid]["status"] == "processing"


def test_a_reclaimed_attempt_is_refused_at_the_recheck() -> None:
    db = ScriptedDb()
    rid = db.revision(db.document(), 1, "processing")
    stale = db.job(rid)
    db.jobs[stale.id] = stale.model_copy(update={"attempt": 2, "locked_by": "worker-b"})

    with pytest.raises(LeaseLostError):
        store.activate_revision(fenced(db)[0], stale)
    assert "update_revision" not in db.log


def test_a_job_tenant_that_differs_after_the_locks_is_refused() -> None:
    db = ScriptedDb()
    rid = db.revision(db.document(), 1, "processing")
    job = db.job(rid)
    db.jobs[job.id] = job.model_copy(update={"tenant_id": OTHER_TENANT})

    with pytest.raises(LeaseLostError):
        store.activate_revision(fenced(db)[0], job)
    assert "update_revision" not in db.log


def test_a_payload_naming_another_tenants_revision_is_not_found() -> None:
    db = ScriptedDb()
    rid = db.revision(db.document(OTHER_TENANT), 1, "processing")
    job = db.job(rid, tenant_id=TENANT)

    with pytest.raises(store.RevisionNotFoundError):
        store.activate_revision(fenced(db)[0], job)
    assert db.log == ["revision_document"]


def test_a_lock_timeout_on_the_document_is_the_fixed_error() -> None:
    db = ScriptedDb()
    rid = db.revision(db.document(), 1, "processing")
    timeout = OperationalError("SELECT", {}, Exception("lock"))
    timeout.orig = cast(Any, type("Orig", (), {"sqlstate": "55P03"})())
    db.fail_on["lock_document"] = timeout

    with pytest.raises(JobLockTimeoutError):
        store.activate_revision(fenced(db)[0], db.job(rid))


def test_activation_demotes_then_promotes_then_moves_the_pointer() -> None:
    db = ScriptedDb()
    doc = db.document()
    old = db.revision(doc, 1, "active")
    new = db.revision(doc, 2, "processing")
    db.now = T0 + timedelta(seconds=3)

    result = store.activate_revision(fenced(db)[0], db.job(new))

    writes = [n for n in db.log if n.startswith("update")]
    assert writes == ["update_revision", "update_revision", "update_pointer"]
    revision_updates = [p for n, p in zip(db.log, db.params, strict=True) if n == "update_revision"]
    assert revision_updates[0]["id_1"] == old and revision_updates[0]["status"] == "superseded"
    assert revision_updates[1]["id_1"] == new and revision_updates[1]["status"] == "active"
    assert db.documents[doc]["active_revision_id"] == new
    assert result.superseded is not None and result.superseded.id == old
    assert db.revisions[old]["superseded_at"] == db.revisions[new]["activated_at"] == db.now


def test_an_older_revision_finishing_late_writes_only_its_own_row() -> None:
    db = ScriptedDb()
    doc = db.document()
    newer = db.revision(doc, 3, "active")
    older = db.revision(doc, 2, "processing")
    pointer_before = dict(db.documents[doc])

    store.activate_revision(fenced(db)[0], db.job(older))

    assert [n for n in db.log if n.startswith("update")] == ["update_revision"]
    assert db.revisions[older]["status"] == "superseded"
    assert db.revisions[older]["superseded_by_revision_id"] == newer
    assert db.documents[doc] == pointer_before


@pytest.mark.parametrize("status", ["active", "superseded"])
def test_a_duplicate_activation_writes_nothing(status: str) -> None:
    db = ScriptedDb()
    doc = db.document()
    if status == "active":
        target = db.revision(doc, 1, "active")
    else:
        newer = db.revision(doc, 2, "active")
        target = db.revision(
            doc, 1, "superseded", superseded_at=T0, superseded_by_revision_id=newer
        )

    store.activate_revision(fenced(db)[0], db.job(target))

    assert not [n for n in db.log if n.startswith("update")]


def test_fail_revision_records_the_revision_code_and_leaves_the_active_one() -> None:
    db = ScriptedDb()
    doc = db.document()
    active = db.revision(doc, 1, "active")
    replacement = db.revision(doc, 2, "processing")

    failed = store.fail_revision(
        fenced(db)[0], db.job(replacement), RevisionFailureCode.INGESTION_FAILED
    )

    assert failed.failure_reason is RevisionFailureCode.INGESTION_FAILED
    assert db.revisions[active]["status"] == "active"
    assert db.documents[doc]["active_revision_id"] == active


def test_fail_revision_refuses_a_job_error_code_before_any_sql() -> None:
    db = ScriptedDb()
    rid = db.revision(db.document(), 1, "processing")

    with pytest.raises(TypeError):
        store.fail_revision(fenced(db)[0], db.job(rid), cast(Any, JobErrorCode.PERMANENT_FAILURE))
    assert db.log == []


# --- the worker runtime over the scripted database (controlled commit failures) -----------------


class FakeFence:
    def __init__(self, store_: "ScriptedJobStore", token: JobLeaseToken) -> None:
        self._store = store_
        self._token = token
        self._open = True
        self.job = store_.db.jobs[token.job_id]
        self.session = FencedSession(cast(Any, ScriptedSession(store_.db)), cast(Any, self))

    def _require_open(self) -> None:
        if not self._open:
            raise AssertionError("fence closed")

    def succeed(self) -> JobSnapshot:
        return self._store._transition(
            self._token, lambda j: lifecycle.succeed(j, self._token, now=self._store.db.now)
        )


class ScriptedJobStore:
    """A ``JobStore`` over the scripted database, with per-transaction commit modes:
    ``ok``, ``ack_lost`` (applied, then the acknowledgment fails) or ``lost`` (not applied)."""

    def __init__(self, db: ScriptedDb) -> None:
        self.db = db
        self.commit_modes: list[str] = []

    def claim(self, worker_id: str, kinds: Any) -> JobSnapshot | None:
        for job in self.db.jobs.values():
            if lifecycle.is_claimable(job, now=self.db.now):
                claimed = lifecycle.claim(job, worker_id=worker_id, now=self.db.now)
                self.db.jobs[job.id] = claimed
                return claimed
        return None

    def heartbeat(self, token: JobLeaseToken) -> JobSnapshot:
        raise AssertionError("heartbeats are disabled in these tests")

    def _transition(
        self, token: JobLeaseToken, rule: Callable[[JobSnapshot], JobSnapshot]
    ) -> JobSnapshot:
        job = self.db.jobs[token.job_id]
        if not lifecycle.holds_lease(job, token, now=self.db.now):
            raise LeaseLostError()
        changed = rule(job)
        self.db.jobs[token.job_id] = changed
        return changed

    def complete(self, token: JobLeaseToken) -> JobSnapshot:
        return self._transition(token, lambda j: lifecycle.succeed(j, token, now=self.db.now))

    def fail_retryable(self, token: JobLeaseToken, code: JobErrorCode) -> JobSnapshot:
        return self._transition(
            token, lambda j: lifecycle.fail_retryably(j, token, now=self.db.now, code=code)
        )

    def fail_permanent(self, token: JobLeaseToken, code: JobErrorCode) -> JobSnapshot:
        return self._transition(
            token, lambda j: lifecycle.fail_permanently(j, token, now=self.db.now, code=code)
        )

    @contextmanager
    def fenced(self, token: JobLeaseToken) -> Iterator[FakeFence]:
        if not lifecycle.holds_lease(self.db.jobs[token.job_id], token, now=self.db.now):
            raise LeaseLostError()
        mode = self.commit_modes.pop(0) if self.commit_modes else "ok"
        before = self.db.snapshot()
        fence = FakeFence(self, token)
        try:
            yield fence
        except BaseException:
            self.db.restore(before)
            raise
        finally:
            fence._open = False
        if mode == "lost":
            self.db.restore(before)
            raise CommitFailed("commit failed")
        if mode == "ack_lost":
            raise CommitFailed("commit acknowledgment lost")


FAST = Timings(heartbeat_interval=600.0, stop_check=0.005, heartbeat_join=1.0)


def _ingest(ctx: JobContext) -> None:
    """A test-only handler following the M3d seam: processing, then atomic activation."""
    with ctx.fenced() as fence:
        store.start_processing(fence.session, fence.job)
    with ctx.fenced(finish=True) as fence:
        store.activate_revision(fence.session, fence.job)


def _run(job_store: ScriptedJobStore, handler: Callable[[JobContext], None]) -> Any:
    return run_worker(
        job_store,
        HandlerRegistry([("test_ingest", handler)]),
        worker_id=WORKER,
        timings=FAST,
        once=True,
    )


def _queued_revision_job(db: ScriptedDb, status: str = "pending") -> tuple[UUID, UUID, UUID]:
    doc = db.document()
    rid = db.revision(doc, 1, status)
    job = db.job(rid, running=False)
    return doc, rid, job.id


def test_an_activation_committed_with_a_lost_acknowledgment_is_never_repeated() -> None:
    db = ScriptedDb()
    _, rid, job_id = _queued_revision_job(db)
    job_store = ScriptedJobStore(db)
    job_store.commit_modes = ["ok", "ack_lost"]

    assert _run(job_store, _ingest).outcome is WorkerOutcome.STOPPED

    # It committed: the job succeeded, the runtime's later fenced outcome was refused.
    assert db.jobs[job_id].status is JobStatus.SUCCEEDED
    assert db.revisions[rid]["status"] == "active" and db.activations == 1
    # A succeeded job is never reclaimed: the next attempt claims nothing.
    assert job_store.claim(WORKER, ["test_ingest"]) is None
    assert db.activations == 1


def test_an_activation_that_did_not_commit_is_retried_and_activates_once() -> None:
    db = ScriptedDb()
    doc, rid, job_id = _queued_revision_job(db)
    job_store = ScriptedJobStore(db)
    job_store.commit_modes = ["ok", "lost"]

    _run(job_store, _ingest)

    # Nothing committed: the job was re-queued by the runtime's fenced retry.
    assert db.jobs[job_id].status is JobStatus.QUEUED
    assert db.jobs[job_id].last_error is JobErrorCode.UNEXPECTED_ERROR
    assert db.revisions[rid]["status"] == "processing" and db.activations == 0
    assert db.documents[doc]["active_revision_id"] is None

    db.now = db.now + timedelta(minutes=5)  # past the retry backoff
    _run(job_store, _ingest)

    assert db.jobs[job_id].status is JobStatus.SUCCEEDED and db.jobs[job_id].attempt == 2
    assert db.revisions[rid]["status"] == "active" and db.activations == 1
    assert db.documents[doc]["active_revision_id"] == rid


def _failing_ingest(ctx: JobContext) -> None:
    """The M3d failure seam: commit the revision failure, then fail the job outside the block.
    On a reclaim, an already-failed revision fails the job without processing again."""
    with ctx.fenced() as fence:
        status = fence.session.execute(
            select(DocumentRevision.status).where(
                DocumentRevision.tenant_id == fence.job.tenant_id,
                DocumentRevision.id == UUID(fence.job.payload.as_dict()["revision_id"]),
            )
        ).scalar()
        if status != RevisionStatus.FAILED.value:
            store.fail_revision(fence.session, fence.job, RevisionFailureCode.INGESTION_FAILED)
    raise PermanentJobError(JobErrorCode.PERMANENT_FAILURE)


def test_permanent_failure_commits_the_revision_then_fails_the_job_separately() -> None:
    db = ScriptedDb()
    _, rid, job_id = _queued_revision_job(db, status="processing")

    _run(ScriptedJobStore(db), _failing_ingest)

    assert db.revisions[rid]["status"] == "failed"
    assert db.revisions[rid]["failure_reason"] == "ingestion_failed"
    assert db.jobs[job_id].status is JobStatus.FAILED
    assert db.jobs[job_id].last_error is JobErrorCode.PERMANENT_FAILURE


def test_a_reclaimed_job_finding_its_revision_failed_fails_without_reprocessing() -> None:
    db = ScriptedDb()
    # The crash gap: the revision failure committed, the job is still queued.
    _, rid, job_id = _queued_revision_job(db, status="failed")
    db.revisions[rid].update(failure_reason="ingestion_failed", failed_at=T0)
    db.log.clear()

    _run(ScriptedJobStore(db), _failing_ingest)

    assert "update_revision" not in db.log and "lock_document" not in db.log
    assert db.jobs[job_id].status is JobStatus.FAILED
    assert db.jobs[job_id].last_error is JobErrorCode.PERMANENT_FAILURE


def test_the_two_failure_code_types_are_distinct() -> None:
    # M3c's code plus the four M3d parser and chunk-write codes (ADR-0010).
    assert {c.value for c in RevisionFailureCode} == {
        "ingestion_failed",
        "empty_document",
        "chunk_limit_exceeded",
        "content_integrity_failed",
        "chunk_conflict",
    }
    assert not {c.value for c in RevisionFailureCode} & {c.value for c in JobErrorCode}
    with pytest.raises(TypeError):
        PermanentJobError(cast(Any, RevisionFailureCode.INGESTION_FAILED))


def test_content_never_appears_in_snapshots_or_errors() -> None:
    db = ScriptedDb()
    session = ScriptedSession(db)
    vendor = db.vendor()
    result = _create(db, session, vendor, content=_content(CONTENT_MARKER))

    assert CONTENT_MARKER not in repr(result)
    with pytest.raises(store.RevisionConflictError) as error:
        _create(db, session, vendor, content=_content(CONTENT_MARKER), version_label="v2")
    assert CONTENT_MARKER not in str(error.value)
