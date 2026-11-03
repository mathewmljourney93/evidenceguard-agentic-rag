"""The extracted evidence recheck (``recheck_evidence_in_transaction``, M5e-J1, ADR-0023)
without a database: precedence, the shared steps reused by M4d retrieval, comparison, failure
normalization and process control.

Sessions are scripted doubles that record statements; they prove control flow and statement
identity, not SQL semantics (``test_review_stages_postgres.py`` and
``test_retrieval_postgres.py`` cover those against PostgreSQL).
"""

import dataclasses
import hashlib
import socket
from collections.abc import Callable
from datetime import UTC, date, datetime
from fractions import Fraction
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.sql.elements import TextClause

from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_domain.embedding_storage import index_id, profile_id
from evidenceguard_domain.errors import PermissionDeniedError
from evidenceguard_domain.evidence import Authenticity, SourceType
from evidenceguard_domain.retrieval import (
    RETRIEVAL_CONFIG_V1,
    ChannelHit,
    ChunkEvidence,
    InvalidRetrievalRequestError,
    PendingExclusions,
    RetrievalScopeError,
    RetrievalSnapshot,
    RetrievedChunk,
    RevisionBinding,
    SourceSpan,
)
from evidenceguard_persistence import retrieval as store
from evidenceguard_persistence.database_failures import DatabaseFailureCategory
from evidenceguard_persistence.retrieval import (
    INCONSISTENT,
    EvidenceRecheckFailure,
    RetrievedEvidenceRow,
    SemanticOutcome,
    recheck_evidence_in_transaction,
)
from evidenceguard_retrieval.embeddings import HASH_IDENTITY

TENANT = uuid4()
VENDOR = uuid4()
VERSION = "text-md-v1"
PROFILE = profile_id(TENANT, HASH_IDENTITY.fingerprint)
REVIEWER = ActorContext(tenant_id=TENANT, actor_id=uuid4(), role=Role.REVIEWER)
APPROVER = ActorContext(tenant_id=TENANT, actor_id=uuid4(), role=Role.APPROVER)
ADMIN = ActorContext(tenant_id=TENANT, actor_id=uuid4(), role=Role.ADMIN)
OUTSIDER = ActorContext(tenant_id=uuid4(), actor_id=uuid4(), role=Role.REVIEWER)


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("a test attempted network access")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


def make_snapshot() -> RetrievalSnapshot:
    revision, document = sorted([uuid4(), uuid4()])
    return RetrievalSnapshot(
        TENANT,
        VENDOR,
        HASH_IDENTITY,
        RETRIEVAL_CONFIG_V1,
        (
            RevisionBinding(
                revision,
                document,
                index_id(TENANT, revision, VERSION, PROFILE),
                VERSION,
                2,
                "a" * 64,
                "b" * 64,
            ),
        ),
        PendingExclusions(0, (), False),
        datetime(2026, 10, 17, 9, 30, tzinfo=UTC),
    )


SNAPSHOT = make_snapshot()
BINDING = SNAPSHOT.bindings[0]


def evidence(chunk: UUID, text: str = "alpha bravo", **changes: Any) -> ChunkEvidence:
    values: dict[str, Any] = {
        "chunk_id": chunk,
        "text": text,
        "content_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "ordinal": 0,
        "section_path": ("Retention",),
        "is_table": False,
        "body": SourceSpan(1, 1, 0, len(text)),
        "header": None,
        "document_key": "data-retention",
        "title": "Data Retention",
        "revision_no": 1,
        "version_label": "v1",
        "effective_date": date(2026, 1, 1),
        "source_type": SourceType.VENDOR_STATEMENT,
        "authenticity": Authenticity.NOT_ESTABLISHED,
    }
    values.update(changes)
    return ChunkEvidence(**values)


def item(chunk: UUID, rank: int = 1, **changes: Any) -> RetrievedChunk:
    return RetrievedChunk(
        chunk,
        BINDING.revision_id,
        BINDING.document_id,
        rank,
        Fraction(1, 61),
        (ChannelHit(0, "lexical", 1, 1.0),),
        evidence(chunk, **changes),
    )


def row(value: RetrievedChunk, **changes: Any) -> SimpleNamespace:
    ev = value.evidence
    values: dict[str, Any] = {
        "chunk_id": value.chunk_id,
        "revision_id": value.revision_id,
        "document_id": value.document_id,
        "ordinal": ev.ordinal,
        "text": ev.text,
        "content_sha256": ev.content_sha256,
        "section_path": list(ev.section_path),
        "is_table": ev.is_table,
        "line_start": ev.body.line_start,
        "line_end": ev.body.line_end,
        "char_start": ev.body.char_start,
        "char_end": ev.body.char_end,
        "header_line_start": None,
        "header_line_end": None,
        "header_char_start": None,
        "header_char_end": None,
        "document_key": ev.document_key,
        "title": ev.title,
        "source_type": ev.source_type.value,
        "authenticity": ev.authenticity.value,
        "revision_no": ev.revision_no,
        "version_label": ev.version_label,
        "effective_date": ev.effective_date,
    }
    values.update(changes)
    return SimpleNamespace(**values)


A, B = sorted([uuid4(), uuid4()])
ITEMS = (item(A, 1), item(B, 2))


class Result:
    def __init__(self, rows: list[Any] | None = None, scalar: Any = None) -> None:
        self.rows = rows or []
        self.scalar = scalar

    def all(self) -> list[Any]:
        return list(self.rows)

    def scalar_one(self) -> Any:
        return self.scalar


class Session:
    """Answers the binding recheck with ``verified`` and the evidence statement with ``rows``;
    records every statement and any transaction-control call."""

    def __init__(
        self,
        verified: Any = 1,
        rows: list[Any] | None = None,
        *,
        raises: dict[str, BaseException] | None = None,
    ) -> None:
        self.verified = verified
        self.rows = [row(value) for value in ITEMS] if rows is None else rows
        self.raises = raises or {}
        self.statements: list[tuple[str, dict[str, Any]]] = []
        self.control: list[str] = []

    def execute(self, statement: Any, params: dict[str, Any] | None = None) -> Result:
        assert isinstance(statement, TextClause)
        name = "recheck" if statement.text == store.BINDING_RECHECK_SQL else "evidence"
        assert name == "recheck" or statement.text == store.EVIDENCE_SQL
        self.statements.append((name, dict(params or {})))
        if name in self.raises:
            raise self.raises[name]
        if name == "recheck":
            return Result(scalar=self.verified)
        return Result(rows=self.rows)

    def __getattr__(self, name: str) -> Callable[[], None]:
        if name in ("commit", "rollback", "close", "begin", "connection"):

            def record() -> None:
                self.control.append(name)

            return record
        raise AttributeError(name)


def recheck(session: Session, *, actor: Any = REVIEWER, items: Any = ITEMS) -> Any:
    return recheck_evidence_in_transaction(session, actor, SNAPSHOT, items)  # type: ignore[arg-type]


def test_matching_items_are_returned_rebuilt_and_only_two_selects_run() -> None:
    session = Session()
    assert recheck(session) == ITEMS
    assert [name for name, _ in session.statements] == ["recheck", "evidence"]
    assert session.statements[0][1] == store.binding_parameters(SNAPSHOT)
    assert session.statements[1][1] == {
        **store.binding_parameters(SNAPSHOT),
        "chunk_ids": [A, B],
    }
    assert session.control == []  # no commit, rollback, close, begin or connection access
    assert recheck(Session(), actor=APPROVER) == ITEMS


def test_empty_items_need_only_the_binding_recheck() -> None:
    session = Session()
    assert recheck(session, items=()) == ()
    assert [name for name, _ in session.statements] == ["recheck"]


def test_precedence_is_actor_items_role_tenant_and_runs_no_statement() -> None:
    other = item(uuid4())
    foreign = dataclasses.replace(other, revision_id=uuid4())
    cases: list[tuple[Any, Any, type[Exception]]] = [
        ("actor", "items", TypeError),
        (ADMIN, (ITEMS[0], ITEMS[0]), InvalidRetrievalRequestError),  # duplicate chunk IDs
        (ADMIN, [ITEMS[0]], InvalidRetrievalRequestError),  # not a tuple
        (ADMIN, (foreign,), InvalidRetrievalRequestError),  # not in a snapshot binding
        (ADMIN, tuple(item(uuid4()) for _ in range(21)), InvalidRetrievalRequestError),
        (ADMIN, ("item",), InvalidRetrievalRequestError),
        (ADMIN, ITEMS, PermissionDeniedError),
        (OUTSIDER, ITEMS, RetrievalScopeError),
    ]
    for actor, items, error in cases:
        session = Session()
        with pytest.raises(error):
            recheck(session, actor=actor, items=items)
        assert session.statements == []
    session = Session()
    with pytest.raises(InvalidRetrievalRequestError):
        recheck_evidence_in_transaction(session, REVIEWER, "snapshot", ITEMS)  # type: ignore[arg-type]
    assert session.statements == []


@pytest.mark.parametrize("verified", [0, 2, None, "1", True])
def test_a_failed_binding_recheck_is_inconsistent_before_the_chunks(verified: Any) -> None:
    session = Session(verified=verified)
    assert recheck(session) == INCONSISTENT
    assert [name for name, _ in session.statements] == ["recheck"]


@pytest.mark.parametrize(
    "rows",
    [
        [row(ITEMS[0])],  # a missing chunk
        [row(ITEMS[0]), row(ITEMS[1]), row(ITEMS[1])],  # a duplicate row
        [row(ITEMS[0]), row(ITEMS[1], chunk_id=uuid4())],  # another chunk
        [row(ITEMS[0]), row(ITEMS[1], text="changed")],  # text no longer hashes to its digest
        [row(ITEMS[0]), row(ITEMS[1], source_type="unknown")],  # not constructible
    ],
)
def test_missing_or_unverifiable_rows_are_inconsistent(rows: list[Any]) -> None:
    assert recheck(Session(rows=rows)) == INCONSISTENT


@pytest.mark.parametrize(
    "changes",
    [
        {"revision_id": uuid4()},
        {"document_id": uuid4()},
        {"ordinal": 1},
        {"section_path": ["Other"]},
        {"is_table": True},
        {"line_start": 0},
        {"line_end": 2},
        {"char_start": 1, "char_end": 12},
        {"document_key": "other"},
        {"title": "Other"},
        {"revision_no": 2},
        {"version_label": None},
        {"effective_date": None},
        {"source_type": "contract"},
    ],
)
def test_every_compared_field_detects_a_difference(changes: dict[str, Any]) -> None:
    rows = [row(ITEMS[0]), row(ITEMS[1], **changes)]
    assert recheck(Session(rows=rows)) == INCONSISTENT


def test_ranks_hits_and_scores_are_not_compared() -> None:
    reranked = (
        dataclasses.replace(
            ITEMS[0],
            hits=(ChannelHit(0, "vector", 3, 0.5),),
            fused_score=Fraction(1, 63),
        ),
        ITEMS[1],
    )
    assert recheck(Session(), items=reranked) == reranked


class DriverError(Exception):
    def __init__(self, sqlstate: str) -> None:
        super().__init__("PRIVATE-DRIVER-TEXT")
        self.sqlstate = sqlstate


@pytest.mark.parametrize(
    ("raises", "category"),
    [
        ({"recheck": OperationalError("PRIVATE", {}, DriverError("57014"))}, "query_canceled"),
        (
            {"evidence": OperationalError("PRIVATE", {}, DriverError("40001"))},
            "serialization_failure",
        ),
        ({"evidence": RuntimeError("PRIVATE")}, "other"),
    ],
)
def test_ordinary_failures_are_returned_as_fixed_categories(
    raises: dict[str, BaseException], category: str
) -> None:
    outcome = recheck(Session(raises=raises))
    assert outcome == EvidenceRecheckFailure(DatabaseFailureCategory(category))
    assert "PRIVATE" not in repr(outcome)


class RaisingRow:
    def __init__(self, error: BaseException) -> None:
        self.error = error
        self.chunk_id = A

    def __getattr__(self, name: str) -> Any:
        raise self.error


def test_row_access_and_comparison_failures_are_classified() -> None:
    outcome = recheck(Session(rows=[RaisingRow(RuntimeError("PRIVATE")), row(ITEMS[1])]))
    assert outcome == EvidenceRecheckFailure(DatabaseFailureCategory.OTHER)


@pytest.mark.parametrize("where", ["recheck", "evidence", "row"])
def test_process_control_propagates_as_the_same_object(where: str) -> None:
    marker = KeyboardInterrupt()
    if where == "row":
        session = Session(rows=[RaisingRow(marker), row(ITEMS[1])])
    else:
        session = Session(raises={where: marker})
    with pytest.raises(KeyboardInterrupt) as caught:
        recheck(session)
    assert caught.value is marker


def test_failure_values_are_fixed() -> None:
    with pytest.raises(ValueError):
        EvidenceRecheckFailure("other")  # type: ignore[arg-type]
    with pytest.raises(InvalidRetrievalRequestError):
        RetrievedEvidenceRow(BINDING.revision_id, "document", evidence(A))  # type: ignore[arg-type]
    assert isinstance(INCONSISTENT, SemanticOutcome)


def test_load_snapshot_evidence_builds_rows_in_request_order() -> None:
    session = Session()
    loaded = store.load_snapshot_evidence(session, SNAPSHOT, (B, A))  # type: ignore[arg-type]
    assert isinstance(loaded, dict) and list(loaded) == [B, A]
    assert loaded[A] == RetrievedEvidenceRow(BINDING.revision_id, BINDING.document_id, evidence(A))
    assert session.statements[0][1]["chunk_ids"] == [B, A]
    assert store.recheck_bindings(Session(verified=1), SNAPSHOT) is None  # type: ignore[arg-type]
