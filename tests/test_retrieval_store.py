"""Snapshot capture, retrieval statements and the database failure boundary without a database
(``evidenceguard_persistence.retrieval``, M4d, ADR-0016).

Sessions are scripted doubles: statements are compiled for PostgreSQL and recorded, rows are
plain objects and failures are injected at session creation, the helper's statements, data
statements, row conversion and cleanup. These tests prove the seams' control flow, phase
precedence and error normalization. They do not prove SQL semantics; ``test_retrieval_postgres.py``
covers those against a real database.
"""

import hashlib
import logging
import traceback
from collections.abc import Callable
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import OperationalError
from sqlalchemy.sql.elements import TextClause

from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_domain.embedding_storage import index_id, profile_id
from evidenceguard_domain.embeddings import EmbeddingBatch, EmbeddingIdentity, EmbeddingUsage
from evidenceguard_domain.errors import PermissionDeniedError
from evidenceguard_domain.retrieval import (
    RETRIEVAL_CONFIG_V1,
    EmptySnapshotError,
    InvalidRetrievalRequestError,
    InvalidSnapshotError,
    PendingExclusions,
    RetrievalConfig,
    RetrievalDatabaseError,
    RetrievalError,
    RetrievalProviderError,
    RetrievalRequest,
    RetrievalScopeError,
    RetrievalSnapshot,
    RevisionBinding,
    SnapshotBoundsError,
    SnapshotInconsistentError,
    SnapshotNotReadyError,
)
from evidenceguard_persistence import retrieval as store
from evidenceguard_persistence.document_views import READ_SNAPSHOT_SQL
from evidenceguard_persistence.retrieval import capture_snapshot, retrieve_with_vectors
from evidenceguard_retrieval.embeddings import HASH_IDENTITY, HashingEmbedder

NOW = datetime(2026, 10, 17, 9, 30, 0, 123456, tzinfo=UTC)
TENANT = uuid4()
VENDOR = uuid4()
VERSION = "text-md-v1"
PROFILE = profile_id(TENANT, HASH_IDENTITY.fingerprint)
REVIEWER = ActorContext(tenant_id=TENANT, actor_id=uuid4(), role=Role.REVIEWER)
APPROVER = ActorContext(tenant_id=TENANT, actor_id=uuid4(), role=Role.APPROVER)
ADMIN = ActorContext(tenant_id=TENANT, actor_id=uuid4(), role=Role.ADMIN)
OUTSIDER = ActorContext(tenant_id=uuid4(), actor_id=uuid4(), role=Role.REVIEWER)
LIVE = EmbeddingIdentity("voyage", "voyage-4-lite", "adapter-v1", 1024, "l2")
MARKER = "PRIVATE-MARKER-c41d"


def sql(statement: Any) -> str:
    if isinstance(statement, TextClause):
        return statement.text
    return str(statement.compile(dialect=postgresql.dialect()))  # type: ignore[no-untyped-call]


def kind(text: str) -> str:
    if text == READ_SNAPSHOT_SQL:
        return "set_transaction"
    if "clock_timestamp" in text:
        return "clock"
    if text.startswith("SET LOCAL statement_timeout"):
        return "timeout"
    if "AS verified" in text:
        return "recheck"
    if "websearch_to_tsquery" in text:
        return "lexical"
    if "<=>" in text:
        return "vector"
    if "ANY(CAST(:chunk_ids" in text:
        return "evidence"
    if "FROM vendors" in text:
        return "vendor"
    if "pointer_id" in text:
        return "selection"
    if "count(*)" in text:
        return "excluded_count"
    if "ORDER BY document_revisions.id" in text:
        return "excluded_ids"
    raise AssertionError("unexpected statement")


class Result:
    def __init__(self, rows: list[Any] | None = None, scalar: Any = None) -> None:
        self.rows = rows or []
        self.scalar = scalar

    def first(self) -> Any:
        return self.rows[0] if self.rows else None

    def all(self) -> list[Any]:
        return list(self.rows)

    def scalar_one(self) -> Any:
        return self.scalar

    def scalars(self) -> Any:
        return iter(self.rows)


Responder = Callable[[str, dict[str, Any]], Result]


class FakeSession:
    """Records ``(kind, sql, params)``; ``responses`` answer data statements by kind."""

    def __init__(
        self,
        responses: dict[str, Any],
        *,
        fail_on: str | None = None,
        failure: BaseException | None = None,
        rollback_failure: BaseException | None = None,
        close_failure: BaseException | None = None,
    ) -> None:
        self.responses = responses
        self.fail_on = fail_on
        self.failure = failure
        self.rollback_failure = rollback_failure
        self.close_failure = close_failure
        self.executed: list[tuple[str, str, dict[str, Any]]] = []
        self.events: list[str] = []

    def execute(self, statement: Any, params: dict[str, Any] | None = None) -> Result:
        text = sql(statement)
        name = kind(text)
        self.executed.append((name, text, dict(params or {})))
        if name == self.fail_on:
            assert self.failure is not None
            raise self.failure
        if name == "clock":
            return Result(scalar=NOW)
        if name in ("set_transaction", "timeout"):
            return Result()
        response = self.responses[name]
        if callable(response):
            return response(text, params or {})  # type: ignore[no-any-return]
        if isinstance(response, list):
            if response and isinstance(response[0], Result):  # one result per call
                return response.pop(0)  # type: ignore[no-any-return]
            return Result(rows=response)
        return Result(scalar=response)

    def rollback(self) -> None:
        self.events.append("rollback")
        if self.rollback_failure is not None:
            raise self.rollback_failure

    def close(self) -> None:
        self.events.append("close")
        if self.close_failure is not None:
            raise self.close_failure

    @property
    def kinds(self) -> list[str]:
        return [name for name, _, _ in self.executed]


class Factory:
    def __init__(self, session: FakeSession | None = None, failure: Exception | None = None):
        self.session = session
        self.failure = failure
        self.calls = 0

    def __call__(self) -> FakeSession:
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        assert self.session is not None
        return self.session


# --- capture rows ------------------------------------------------------------------------------


def capture_row(revision: UUID | None = None, **changes: Any) -> SimpleNamespace:
    revision = revision or uuid4()
    document = uuid4()
    values: dict[str, Any] = {
        "document_id": document,
        "pointer_id": revision,
        "revision_id": revision,
        "revision_document_id": document,
        "revision_status": "active",
        "set_chunker_version": VERSION,
        "set_chunk_count": 2,
        "set_manifest_sha256": "a" * 64,
        "profile_id": PROFILE,
        "profile_provider_id": HASH_IDENTITY.provider_id,
        "profile_model_id": HASH_IDENTITY.model_id,
        "profile_algorithm_version": HASH_IDENTITY.algorithm_version,
        "profile_dims": 1024,
        "profile_normalization": "l2",
        "profile_fingerprint": HASH_IDENTITY.fingerprint,
        "index_id": index_id(TENANT, revision, VERSION, PROFILE),
        "index_status": "ready",
        "index_chunker_version": VERSION,
        "index_chunk_count": 2,
        "index_manifest_sha256": "a" * 64,
        "index_vector_manifest_sha256": "b" * 64,
    }
    values.update(changes)
    return SimpleNamespace(**values)


def capture_session(rows: list[Any], **options: Any) -> FakeSession:
    responses: dict[str, Any] = {
        "vendor": [SimpleNamespace(id=VENDOR)],
        "selection": sorted(rows, key=lambda row: row.pointer_id) if rows else [],
        "excluded_count": 0,
        "excluded_ids": [],
    }
    responses.update(options.pop("responses", {}))
    return FakeSession(responses, **options)


def capture(session: FakeSession, actor: ActorContext = REVIEWER, **kwargs: Any) -> Any:
    values: dict[str, Any] = {"vendor_id": VENDOR, "identity": HASH_IDENTITY}
    values.update(kwargs)
    return capture_snapshot(Factory(session), actor, **values)  # type: ignore[arg-type]


def test_capture_runs_the_helper_then_the_timeout_then_read_only_phases() -> None:
    rows = [capture_row(), capture_row()]
    excluded = sorted(uuid4() for _ in range(3))
    session = capture_session(rows, responses={"excluded_count": 3, "excluded_ids": list(excluded)})

    snapshot = capture(session)

    assert session.kinds == [
        "set_transaction",
        "clock",
        "timeout",
        "vendor",
        "selection",
        "excluded_count",
        "excluded_ids",
    ]
    assert session.executed[2][1] == "SET LOCAL statement_timeout = 30000"
    assert session.events == ["rollback", "close"]
    joined = " ".join(text for _, text, _ in session.executed).upper()
    for forbidden in ("FOR UPDATE", "FOR SHARE", "INSERT", "UPDATE ", "DELETE", "SET SESSION"):
        assert forbidden not in joined
    assert snapshot.captured_at == NOW and snapshot.tenant_id == TENANT
    assert [b.revision_id for b in snapshot.bindings] == sorted(r.revision_id for r in rows)
    assert snapshot.exclusions == PendingExclusions(3, tuple(excluded), False)
    assert snapshot.config == RETRIEVAL_CONFIG_V1 and snapshot.total_chunks == 4


def test_the_selection_is_tenant_vendor_scoped_and_bounded_at_101() -> None:
    statement = store.selection_statement(TENANT, VENDOR, HASH_IDENTITY.fingerprint)
    compiled = statement.compile(dialect=postgresql.dialect())  # type: ignore[no-untyped-call]
    text = str(compiled)
    assert "documents.active_revision_id IS NOT NULL" in text
    assert "ORDER BY documents.active_revision_id" in text
    assert compiled.params["param_1"] == 101
    assert TENANT in compiled.params.values() and VENDOR in compiled.params.values()
    for join in ("LEFT OUTER JOIN document_revisions", "LEFT OUTER JOIN chunk_sets"):
        assert join in text
    assert "LEFT OUTER JOIN embedding_profiles" in text
    assert "LEFT OUTER JOIN embedding_indexes" in text


def test_exclusions_record_an_exact_count_and_at_most_100_ascending_ids() -> None:
    excluded = sorted(uuid4() for _ in range(100))
    session = capture_session(
        [capture_row()], responses={"excluded_count": 250, "excluded_ids": list(excluded)}
    )
    snapshot = capture(session)
    assert snapshot.exclusions.count == 250 and snapshot.exclusions.truncated
    assert snapshot.exclusions.revision_ids == tuple(excluded)
    statement = sql(store.exclusion_ids_statement(TENANT, VENDOR))
    assert "IN (__[POSTCOMPILE_status_1])" in statement and "LIMIT" in statement


@pytest.mark.parametrize(
    ("rows", "error", "in_phases"),
    [
        ([], EmptySnapshotError, True),
        ([capture_row() for _ in range(101)], SnapshotBoundsError, True),
        ([capture_row(revision_status="superseded")], SnapshotInconsistentError, True),
        ([capture_row(revision_document_id=uuid4())], SnapshotInconsistentError, True),
        ([capture_row(revision_id=None)], SnapshotInconsistentError, True),
        ([capture_row(profile_model_id="other")], SnapshotInconsistentError, True),
        ([capture_row(index_id=None)], SnapshotNotReadyError, True),
        ([capture_row(index_status="building")], SnapshotNotReadyError, True),
        ([capture_row(index_manifest_sha256="c" * 64)], SnapshotNotReadyError, True),
        ([capture_row(set_chunker_version=None)], SnapshotNotReadyError, True),
        ([capture_row(profile_id=None, index_id=None)], SnapshotNotReadyError, True),
        ([capture_row(index_vector_manifest_sha256=None)], SnapshotNotReadyError, True),
        (
            [capture_row(set_chunk_count=4000, index_chunk_count=4000) for _ in range(26)],
            SnapshotBoundsError,
            True,
        ),
        # Not the derived index ID: the snapshot constructor rejects it after the phases.
        ([capture_row(index_id=uuid4())], SnapshotInconsistentError, False),
    ],
)
def test_capture_phase_outcomes(
    rows: list[Any], error: type[RetrievalError], in_phases: bool
) -> None:
    session = capture_session(rows)
    with pytest.raises(error) as raised:
        capture(session)
    assert raised.value.__cause__ is None and raised.value.__context__ is None
    assert ("excluded_count" in session.kinds) is not in_phases
    assert session.events == ["rollback", "close"]


def test_the_scope_phase_runs_before_selection_and_hides_missing_or_foreign_vendors() -> None:
    session = capture_session([capture_row()], responses={"vendor": []})
    with pytest.raises(RetrievalScopeError):
        capture(session)
    assert session.kinds == ["set_transaction", "clock", "timeout", "vendor"]


@pytest.mark.parametrize("reverse", [False, True])
def test_phase_precedence_does_not_depend_on_row_order(reverse: bool) -> None:
    def ordered(rows: list[Any]) -> list[Any]:
        return list(reversed(rows)) if reverse else rows

    def outcome(rows: list[Any]) -> type[RetrievalError] | None:
        result = store.evaluate_selection(ordered(rows), TENANT, HASH_IDENTITY)
        if isinstance(result, store.SemanticOutcome):
            return store._SEMANTIC_ERRORS[result.code]
        return None

    unready, broken = capture_row(index_status="building"), capture_row(revision_status="failed")
    heavy = [capture_row(set_chunk_count=4000, index_chunk_count=4000) for _ in range(26)]
    assert outcome([unready, broken]) is SnapshotInconsistentError
    assert outcome([*heavy, unready]) is SnapshotNotReadyError
    assert outcome([broken, *[capture_row() for _ in range(100)]]) is SnapshotBoundsError
    assert outcome([*heavy, broken]) is SnapshotInconsistentError


def test_capture_validates_inputs_then_role_before_any_database_work() -> None:
    def refused(actor: Any, error: type[Exception], **kwargs: Any) -> None:
        factory = Factory(capture_session([capture_row()]))
        values: dict[str, Any] = {"vendor_id": VENDOR, "identity": HASH_IDENTITY}
        values.update(kwargs)
        with pytest.raises(error):
            capture_snapshot(factory, actor, **values)  # type: ignore[arg-type]
        assert factory.calls == 0

    refused(object(), TypeError)
    refused(REVIEWER, InvalidRetrievalRequestError, vendor_id=str(VENDOR))
    refused(
        REVIEWER, InvalidRetrievalRequestError, identity=LIVE.__class__("a", "b", "c", 512, "l2")
    )
    refused(REVIEWER, InvalidRetrievalRequestError, identity="offline")
    refused(REVIEWER, InvalidRetrievalRequestError, config=object())
    refused(ADMIN, PermissionDeniedError)
    refused(ADMIN, InvalidRetrievalRequestError, vendor_id=None)  # input before role
    assert isinstance(capture(capture_session([capture_row()]), APPROVER), RetrievalSnapshot)
    assert RetrievalConfig() == RETRIEVAL_CONFIG_V1


# --- retrieval ---------------------------------------------------------------------------------


def make_snapshot(count: int = 2) -> RetrievalSnapshot:
    revisions = sorted(uuid4() for _ in range(count))
    bindings = tuple(
        RevisionBinding(
            revision,
            uuid4(),
            index_id(TENANT, revision, VERSION, PROFILE),
            VERSION,
            2,
            "a" * 64,
            "b" * 64,
        )
        for revision in revisions
    )
    return RetrievalSnapshot(
        TENANT,
        VENDOR,
        HASH_IDENTITY,
        RETRIEVAL_CONFIG_V1,
        bindings,
        PendingExclusions(0, (), False),
        NOW,
    )


def evidence_row(snapshot: RetrievalSnapshot, chunk: UUID, text: str = "alpha bravo") -> Any:
    binding = snapshot.bindings[0]
    return SimpleNamespace(
        chunk_id=chunk,
        revision_id=binding.revision_id,
        document_id=binding.document_id,
        ordinal=0,
        text=text,
        content_sha256=hashlib.sha256(text.encode()).hexdigest(),
        section_path=["Retention"],
        is_table=False,
        line_start=1,
        line_end=1,
        char_start=0,
        char_end=len(text),
        header_line_start=None,
        header_line_end=None,
        header_char_start=None,
        header_char_end=None,
        document_key="data-retention",
        title="Data Retention",
        source_type="vendor_statement",
        authenticity="not_established",
        revision_no=1,
        version_label=None,
        effective_date=None,
    )


def hit_row(chunk: UUID, score: float) -> Any:
    return SimpleNamespace(chunk_id=chunk, score=score)


def batch(*queries: str) -> EmbeddingBatch:
    return HashingEmbedder().embed(queries, "query")


def retrieval_session(snapshot: RetrievalSnapshot, **responses: Any) -> FakeSession:
    a, b = sorted([uuid4(), uuid4()])
    values: dict[str, Any] = {
        "recheck": len(snapshot.bindings),
        "lexical": [hit_row(a, 0.5), hit_row(b, 0.25)],
        "vector": [hit_row(b, 0.1)],
        "evidence": lambda _text, params: Result(
            rows=[evidence_row(snapshot, chunk) for chunk in params["chunk_ids"]]
        ),
    }
    values.update(responses)
    return FakeSession(values)


def retrieve(
    session: FakeSession,
    snapshot: RetrievalSnapshot,
    request: RetrievalRequest,
    query_batch: EmbeddingBatch,
    actor: Any = REVIEWER,
) -> Any:
    return retrieve_with_vectors(Factory(session), actor, snapshot, request, query_batch)  # type: ignore[arg-type]


def test_retrieval_rechecks_bindings_then_runs_channels_then_loads_evidence() -> None:
    snapshot = make_snapshot()
    request = RetrievalRequest(("retention period", "éü"), k=8)  # the second query is all-zero
    session = retrieval_session(snapshot)

    result = retrieve(session, snapshot, request, batch(*request.queries))

    assert session.kinds == [
        "set_transaction",
        "clock",
        "timeout",
        "recheck",
        "lexical",
        "vector",
        "lexical",  # position 1 is vector-skipped: no vector statement
        "evidence",
    ]
    assert session.events == ["rollback", "close"]
    assert result.vector_skipped == (1,) and result.query_count == 2
    assert result.snapshot_sha256 == snapshot.sha256 and len(result.items) == 2
    lexical = [params for name, _, params in session.executed if name == "lexical"]
    assert [params["query"] for params in lexical] == list(request.queries)  # bound, verbatim
    (vector,) = [params for name, _, params in session.executed if name == "vector"]
    assert vector["query_vector"].startswith("[") and len(vector["query_vector"]) > 1024
    recheck = session.executed[3][2]
    assert recheck["revision_ids"] == [b.revision_id for b in snapshot.bindings]
    assert recheck["tenant_id"] == TENANT and recheck["profile_id"] == snapshot.profile_id
    assert recheck["fingerprint"] == HASH_IDENTITY.fingerprint
    top = result.items[0]  # in both lists: fused first
    # The double returns the same lexical rows for both queries.
    assert [h.key for h in top.hits] == [(0, "lexical"), (0, "vector"), (1, "lexical")]


def test_channel_statements_repeat_eligibility_and_never_test_current_status() -> None:
    for statement in (store.LEXICAL_SQL, store.VECTOR_SQL, store.EVIDENCE_SQL):
        assert "r.activated_at IS NOT NULL" in statement
        assert "i.status = 'ready'" in statement and "i.profile_id = :profile_id" in statement
        assert "d.vendor_id = :vendor_id" in statement and "r.status" not in statement
        assert statement.count(":tenant_id") >= 4  # d, r, i and e are each tenant-scoped
    assert store.LEXICAL_SQL.rstrip().endswith("LIMIT 20")
    assert store.VECTOR_SQL.rstrip().endswith("LIMIT 20")
    assert "CAST('simple' AS regconfig)" in store.LEXICAL_SQL
    assert "ts_rank_cd(c.search_vector, q.tsq, 0) > 0" in store.LEXICAL_SQL
    assert "ORDER BY score DESC, c.id ASC" in store.LEXICAL_SQL
    assert "NOT e.is_zero" in store.VECTOR_SQL
    assert "ORDER BY score ASC, e.chunk_id ASC" in store.VECTOR_SQL
    assert "CAST(:query_vector AS vector(1024))" in store.VECTOR_SQL
    assert "r.status" not in store.BINDING_RECHECK_SQL
    assert "i.vector_manifest_sha256 = b.vector_manifest_sha256" in store.BINDING_RECHECK_SQL
    assert "p.fingerprint = :fingerprint" in store.BINDING_RECHECK_SQL


def test_a_failed_binding_recheck_is_inconsistent_and_runs_no_channel_query() -> None:
    snapshot = make_snapshot(3)
    for verified in (2, 4, None, "3"):
        session = retrieval_session(snapshot, recheck=verified)
        with pytest.raises(SnapshotInconsistentError):
            retrieve(session, snapshot, RetrievalRequest(("a",)), batch("a"))
        assert session.kinds[-1] == "recheck"


@pytest.mark.parametrize(
    "responses",
    [
        {"vector": [hit_row(UUID(int=1), float("nan"))]},  # non-finite distance
        {"lexical": [hit_row(UUID(int=1), 0.1), hit_row(UUID(int=2), 0.9)]},  # wrong order
        {"lexical": [hit_row(UUID(int=1), 0.0)]},  # non-positive lexical score
        {"evidence": []},  # an evidence row is missing
        {"evidence": "tampered"},
        {"evidence": "unknown_source"},
        {"evidence": "duplicate"},
    ],
)
def test_invalid_rows_are_inconsistent(responses: dict[str, Any]) -> None:
    snapshot = make_snapshot()
    if responses.get("evidence") == "tampered":

        def tampered(_text: str, params: dict[str, Any]) -> Result:
            rows = [evidence_row(snapshot, chunk) for chunk in params["chunk_ids"]]
            rows[0].text = "alpha bravX"  # digest mismatch
            return Result(rows=rows)

        responses = {"evidence": tampered}
    elif responses.get("evidence") == "unknown_source":

        def unknown(_text: str, params: dict[str, Any]) -> Result:
            rows = [evidence_row(snapshot, chunk) for chunk in params["chunk_ids"]]
            rows[0].source_type = "rumour"
            return Result(rows=rows)

        responses = {"evidence": unknown}
    elif responses.get("evidence") == "duplicate":

        def duplicate(_text: str, params: dict[str, Any]) -> Result:
            chunk = params["chunk_ids"][0]
            return Result(rows=[evidence_row(snapshot, chunk), evidence_row(snapshot, chunk)])

        responses = {"evidence": duplicate}
    session = retrieval_session(snapshot, **responses)
    with pytest.raises(SnapshotInconsistentError):
        retrieve(session, snapshot, RetrievalRequest(("a",)), batch("a"))


def test_no_candidates_is_an_empty_result_without_an_evidence_statement() -> None:
    snapshot = make_snapshot()
    session = retrieval_session(snapshot, lexical=[], vector=[])
    result = retrieve(session, snapshot, RetrievalRequest(("a",)), batch("a"))
    assert result.items == () and "evidence" not in session.kinds


def test_retrieval_validation_precedes_any_database_work() -> None:
    snapshot = make_snapshot()
    request = RetrievalRequest(("a",))

    def refused(error: type[Exception], *args: Any) -> None:
        factory = Factory(retrieval_session(snapshot))
        actor, snap, req, query_batch = args
        with pytest.raises(error):
            retrieve_with_vectors(factory, actor, snap, req, query_batch)  # type: ignore[arg-type]
        assert factory.calls == 0

    good = batch("a")
    forged = make_snapshot()
    object.__setattr__(forged, "total_chunks", 1)
    refused(TypeError, object(), snapshot, request, good)
    refused(InvalidRetrievalRequestError, REVIEWER, snapshot, ("a",), good)
    refused(InvalidSnapshotError, REVIEWER, forged, request, good)
    refused(PermissionDeniedError, ADMIN, snapshot, request, good)
    refused(InvalidRetrievalRequestError, ADMIN, snapshot, ("a",), good)  # structure first
    refused(RetrievalScopeError, OUTSIDER, snapshot, request, good)
    refused(RetrievalScopeError, OUTSIDER, snapshot, request, batch("a", "b"))  # scope first


@pytest.mark.parametrize("case", ["identity", "document", "count", "numbers", "type"])
def test_standalone_batch_validation_without_a_provider(case: str) -> None:
    snapshot = make_snapshot()
    request = RetrievalRequest(("a",))
    axis = tuple(1.0 if i == 0 else 0.0 for i in range(1024))
    query_batch: Any
    if case == "identity":
        query_batch = EmbeddingBatch(LIVE, "query", (axis,), EmbeddingUsage(None))
    elif case == "document":
        query_batch = HashingEmbedder().embed(("a",), "document")
    elif case == "count":
        query_batch = batch("a", "b")
    elif case == "numbers":
        query_batch = batch("a")
        object.__setattr__(
            query_batch, "vectors", (tuple(2.0 if i == 0 else 0.0 for i in range(1024)),)
        )
    else:
        query_batch = (axis,)
    factory = Factory(retrieval_session(snapshot))
    with pytest.raises(RetrievalProviderError) as raised:
        retrieve_with_vectors(factory, REVIEWER, snapshot, request, query_batch)  # type: ignore[arg-type]
    assert factory.calls == 0
    assert raised.value.__cause__ is None and raised.value.__context__ is None


# --- the database failure boundary ---------------------------------------------------------------


def backend_error() -> OperationalError:
    """A SQLAlchemy error carrying the marker in its statement, parameters, driver error and
    chained cause."""
    driver = psycopg.errors.QueryCanceled(f"canceling statement due to timeout {MARKER}")
    error = OperationalError(f"SELECT '{MARKER}'", {"query": MARKER}, driver)
    error.__cause__ = RuntimeError(MARKER)
    return error


def assert_private(error: BaseException) -> None:
    assert MARKER not in str(error) and MARKER not in repr(error)
    assert error.__cause__ is None and error.__context__ is None
    assert MARKER not in "".join(traceback.format_exception(error))


def run_capture(session: FakeSession) -> RetrievalError:
    with pytest.raises(RetrievalError) as raised:
        capture(session)
    return raised.value


@pytest.mark.parametrize(
    "fail_on", ["set_transaction", "clock", "timeout", "vendor", "selection", "excluded_ids"]
)
def test_backend_failures_at_every_statement_are_fixed_database_errors(
    fail_on: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    session = capture_session([capture_row()], fail_on=fail_on, failure=backend_error())
    error = run_capture(session)
    assert type(error) is RetrievalDatabaseError
    assert_private(error)
    assert session.events == ["rollback", "close"]
    assert session.kinds.count(fail_on) == 1  # no retry
    assert caplog.records == []  # nothing logs


def test_a_connection_failure_during_acquisition_is_a_database_error() -> None:
    factory = Factory(failure=psycopg.OperationalError(f"connection refused {MARKER}"))
    with pytest.raises(RetrievalDatabaseError) as raised:
        capture_snapshot(factory, REVIEWER, vendor_id=VENDOR, identity=HASH_IDENTITY)  # type: ignore[arg-type]
    assert_private(raised.value)
    assert factory.calls == 1


def test_a_row_conversion_failure_is_operational() -> None:
    broken = SimpleNamespace(pointer_id=uuid4())  # missing attributes
    session = capture_session([broken])
    error = run_capture(session)
    assert type(error) is RetrievalDatabaseError
    assert_private(error)


def test_a_semantic_error_found_in_a_backend_chain_stays_operational() -> None:
    chained = backend_error()
    chained.__cause__ = SnapshotInconsistentError()
    chained.__context__ = RetrievalScopeError()
    for failure in (chained, SnapshotInconsistentError(), EmptySnapshotError()):
        session = capture_session([capture_row()], fail_on="selection", failure=failure)
        error = run_capture(session)
        assert type(error) is RetrievalDatabaseError  # the seam did not record it
        assert error.__cause__ is None and error.__context__ is None


@pytest.mark.parametrize(
    ("rows", "responses", "fail_on", "expected"),
    [
        ([], {}, None, EmptySnapshotError),  # semantic, then cleanup fails
        ([capture_row()], {"vendor": []}, None, RetrievalScopeError),
        ([capture_row()], {}, "selection", RetrievalDatabaseError),  # operational, then cleanup
        ([capture_row()], {}, None, RetrievalDatabaseError),  # success, then cleanup fails
    ],
)
def test_the_body_outcome_stays_primary_when_cleanup_fails(
    rows: list[Any], responses: dict[str, Any], fail_on: str | None, expected: type[Exception]
) -> None:
    session = capture_session(
        rows,
        responses=responses,
        fail_on=fail_on,
        failure=backend_error() if fail_on else None,
        rollback_failure=OperationalError(MARKER, {}, RuntimeError(MARKER)),
    )
    error = run_capture(session)
    assert type(error) is expected
    assert_private(error)
    assert session.events == ["rollback", "close"]  # the helper still closes


def test_success_followed_by_a_cleanup_failure_returns_no_result_for_retrieval() -> None:
    snapshot = make_snapshot()
    session = retrieval_session(snapshot)
    session.rollback_failure = RuntimeError(MARKER)
    with pytest.raises(RetrievalDatabaseError) as raised:
        retrieve(session, snapshot, RetrievalRequest(("a",)), batch("a"))
    assert_private(raised.value)


def test_retrieval_statement_timeouts_are_database_errors_never_empty_results() -> None:
    snapshot = make_snapshot()
    for fail_on in ("recheck", "lexical", "vector", "evidence"):
        session = retrieval_session(snapshot)
        session.fail_on, session.failure = fail_on, backend_error()
        with pytest.raises(RetrievalDatabaseError) as raised:
            retrieve(session, snapshot, RetrievalRequest(("alpha",)), batch("alpha"))
        assert_private(raised.value)
        assert session.kinds.count(fail_on) == 1


@pytest.mark.parametrize("control", [KeyboardInterrupt, SystemExit])
def test_process_control_propagates_unconverted(control: type[BaseException]) -> None:
    session = capture_session([capture_row()], fail_on="selection", failure=control())
    with pytest.raises(control):
        capture(session)
    assert session.events == ["rollback", "close"]

    # Also when cleanup fails while the control exception propagates.
    session = capture_session(
        [capture_row()],
        fail_on="selection",
        failure=control(),
        rollback_failure=RuntimeError(MARKER),
    )
    with pytest.raises(control):
        capture(session)
    assert session.events == ["rollback", "close"]

    # And when cleanup itself raises process control after a successful body.
    session = capture_session([capture_row()], rollback_failure=control())
    with pytest.raises(control):
        capture(session)


# Regression matrix (Prompt 135): process control raised by the helper's setup statements, the
# body or cleanup, with an ordinary rollback or close failure (or none) while it propagates.
PHASES = ["set_transaction", "clock", "selection"]
CLEANUP = ["none", "rollback", "close", "both"]


def _cleanup_failures(cleanup: str) -> dict[str, BaseException]:
    failures: dict[str, BaseException] = {}
    if cleanup in ("rollback", "both"):
        failures["rollback_failure"] = OperationalError(MARKER, {}, RuntimeError(MARKER))
    if cleanup in ("close", "both"):
        failures["close_failure"] = RuntimeError(MARKER)
    return failures


@pytest.mark.parametrize("cleanup", CLEANUP)
@pytest.mark.parametrize("phase", PHASES)
@pytest.mark.parametrize("control", [KeyboardInterrupt, SystemExit])
def test_process_control_matrix_escapes_as_the_same_object(
    control: type[BaseException], phase: str, cleanup: str
) -> None:
    raised = control()
    session = capture_session(
        [capture_row()], fail_on=phase, failure=raised, **_cleanup_failures(cleanup)
    )
    with pytest.raises(control) as caught:
        capture(session)
    assert caught.value is raised  # the same object, never RetrievalDatabaseError
    assert session.events == ["rollback", "close"]  # cleanup was attempted
    assert session.kinds[-1] == phase  # nothing ran after it


@pytest.mark.parametrize("cleanup", CLEANUP)
@pytest.mark.parametrize("phase", ["set_transaction", "clock"])
def test_process_control_matrix_ordinary_setup_failures_stay_private_database_errors(
    phase: str, cleanup: str
) -> None:
    session = capture_session(
        [capture_row()], fail_on=phase, failure=backend_error(), **_cleanup_failures(cleanup)
    )
    with pytest.raises(RetrievalDatabaseError) as caught:
        capture(session)
    assert_private(caught.value)
    assert session.events == ["rollback", "close"]


@pytest.mark.parametrize("control", [KeyboardInterrupt, SystemExit])
def test_process_control_matrix_from_cleanup_itself_propagates(
    control: type[BaseException],
) -> None:
    for failures in (
        {"rollback_failure": control()},
        {"close_failure": control()},
        {"rollback_failure": control(), "close_failure": RuntimeError(MARKER)},
    ):
        expected = next(f for f in failures.values() if isinstance(f, control))
        session = capture_session([capture_row()], **failures)
        with pytest.raises(control) as caught:
            capture(session)
        assert caught.value is expected
        assert session.events == ["rollback", "close"]


def test_the_seams_issue_no_session_level_settings() -> None:
    source = store.__loader__.get_source(store.__name__)  # type: ignore[union-attr]
    assert source is not None
    code = source.split('"""', 2)[2]  # without the module docstring
    for forbidden in (
        "SET SESSION",
        "default_transaction",
        "isolation_level=",
        "execution_options",
        "FOR UPDATE",
        "with_for_update",
        "logging",
        "commit(",
    ):
        assert forbidden not in code
