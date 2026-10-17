"""Provider orchestration for retrieval (``evidenceguard_worker.retrieval``, M4d, ADR-0016) with
provider and session doubles, without a database.

They prove ordering and the provider failure boundary: pure checks before any provider or SQL
call, the identity read before embedding, no session open while the provider runs, capture
before the provider call in ``search_current``, and fixed errors that retain no provider
exception. Embeddings come from the offline ``HashingEmbedder`` (no network or external provider).
"""

import hashlib
import traceback
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.elements import TextClause

from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_domain.embedding_storage import index_id, profile_id
from evidenceguard_domain.embeddings import (
    EmbeddingBatch,
    EmbeddingIdentity,
    EmbeddingUsage,
    InputType,
)
from evidenceguard_domain.errors import PermissionDeniedError
from evidenceguard_domain.retrieval import (
    RETRIEVAL_CONFIG_V1,
    InvalidRetrievalRequestError,
    InvalidSnapshotError,
    PendingExclusions,
    RetrievalProviderError,
    RetrievalRequest,
    RetrievalScopeError,
    RetrievalSnapshot,
    RevisionBinding,
)
from evidenceguard_persistence.document_views import READ_SNAPSHOT_SQL
from evidenceguard_retrieval.embeddings import HASH_IDENTITY, HashingEmbedder
from evidenceguard_worker.retrieval import search_current, search_snapshot

NOW = datetime(2026, 10, 17, 10, 0, tzinfo=UTC)
TENANT = uuid4()
VENDOR = uuid4()
VERSION = "text-md-v1"
PROFILE = profile_id(TENANT, HASH_IDENTITY.fingerprint)
REVIEWER = ActorContext(tenant_id=TENANT, actor_id=uuid4(), role=Role.REVIEWER)
ADMIN = ActorContext(tenant_id=TENANT, actor_id=uuid4(), role=Role.ADMIN)
OUTSIDER = ActorContext(tenant_id=uuid4(), actor_id=uuid4(), role=Role.APPROVER)
OTHER = EmbeddingIdentity("offline", "fake-hash-v2", "ascii-word-sha256-v1", 1024, "l2")
MARKER = "PRIVATE-MARKER-9e2b"
CHUNK = UUID(int=7)


class Log:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.open = 0


class Session:
    def __init__(self, log: Log, snapshot_rows: list[Any] | None, bindings: int) -> None:
        self.log = log
        self.snapshot_rows = snapshot_rows
        self.bindings = bindings
        log.open += 1
        log.events.append("session")

    def execute(self, statement: Any, params: dict[str, Any] | None = None) -> Any:
        if isinstance(statement, TextClause):
            text = statement.text
        else:
            text = str(statement.compile(dialect=postgresql.dialect()))  # type: ignore[no-untyped-call]
        rows: list[Any] = []
        scalar: Any = None
        if "clock_timestamp" in text:
            scalar = NOW
        elif text == READ_SNAPSHOT_SQL or text.startswith("SET LOCAL"):
            pass
        elif "FROM vendors" in text:
            rows = [SimpleNamespace(id=VENDOR)]
        elif "pointer_id" in text:
            rows = list(self.snapshot_rows or [])
        elif "count(*)" in text and "verified" not in text:
            scalar = 0
        elif "ORDER BY document_revisions.id" in text:
            rows = []
        elif "AS verified" in text:
            scalar = self.bindings
        elif "websearch_to_tsquery" in text:
            rows = [SimpleNamespace(chunk_id=CHUNK, score=0.5)]
        elif "<=>" in text:
            rows = [SimpleNamespace(chunk_id=CHUNK, score=0.2)]
        else:  # evidence
            assert params is not None
            rows = [_evidence_row(params["revision_ids"][0], params["document_ids"][0])]
        return SimpleNamespace(
            first=lambda: rows[0] if rows else None,
            all=lambda: rows,
            scalar_one=lambda: scalar,
            scalars=lambda: iter(rows),
        )

    def rollback(self) -> None:
        pass

    def close(self) -> None:
        self.log.open -= 1
        self.log.events.append("closed")


class Factory:
    def __init__(self, log: Log, snapshot_rows: list[Any] | None = None, bindings: int = 1):
        self.log = log
        self.snapshot_rows = snapshot_rows
        self.bindings = bindings
        self.calls = 0

    def __call__(self) -> Session:
        self.calls += 1
        return Session(self.log, self.snapshot_rows, self.bindings)


def _evidence_row(revision: UUID, document: UUID) -> Any:
    text = "retention period ninety days"
    return SimpleNamespace(
        chunk_id=CHUNK,
        revision_id=revision,
        document_id=document,
        ordinal=0,
        text=text,
        content_sha256=hashlib.sha256(text.encode()).hexdigest(),
        section_path=[],
        is_table=False,
        line_start=1,
        line_end=1,
        char_start=0,
        char_end=len(text),
        header_line_start=None,
        header_line_end=None,
        header_char_start=None,
        header_char_end=None,
        document_key="retention",
        title="Retention",
        source_type="vendor_statement",
        authenticity="not_established",
        revision_no=1,
        version_label="v1",
        effective_date=None,
    )


def _snapshot() -> RetrievalSnapshot:
    revision = uuid4()
    binding = RevisionBinding(
        revision,
        uuid4(),
        index_id(TENANT, revision, VERSION, PROFILE),
        VERSION,
        1,
        "a" * 64,
        "b" * 64,
    )
    return RetrievalSnapshot(
        TENANT,
        VENDOR,
        HASH_IDENTITY,
        RETRIEVAL_CONFIG_V1,
        (binding,),
        PendingExclusions(0, (), False),
        NOW,
    )


def _capture_row() -> Any:
    revision, document = uuid4(), uuid4()
    return SimpleNamespace(
        document_id=document,
        pointer_id=revision,
        revision_id=revision,
        revision_document_id=document,
        revision_status="active",
        set_chunker_version=VERSION,
        set_chunk_count=1,
        set_manifest_sha256="a" * 64,
        profile_id=PROFILE,
        profile_provider_id="offline",
        profile_model_id="fake-hash-v1",
        profile_algorithm_version="ascii-word-sha256-v1",
        profile_dims=1024,
        profile_normalization="l2",
        profile_fingerprint=HASH_IDENTITY.fingerprint,
        index_id=index_id(TENANT, revision, VERSION, PROFILE),
        index_status="ready",
        index_chunker_version=VERSION,
        index_chunk_count=1,
        index_manifest_sha256="a" * 64,
        index_vector_manifest_sha256="b" * 64,
    )


class Provider:
    """The offline embedder with observable identity reads and embed calls."""

    def __init__(self, log: Log, identities: list[Any] | None = None) -> None:
        self.log = log
        self.identities = identities or []
        self.identity_reads = 0
        self.calls = 0
        self.result: Any = None
        self.failure: BaseException | None = None
        self.open_during_embed: int | None = None

    @property
    def identity(self) -> EmbeddingIdentity:
        self.identity_reads += 1
        self.log.events.append("identity")
        if self.identities:
            value = self.identities.pop(0)
            if isinstance(value, BaseException):
                raise value
            return value  # type: ignore[no-any-return]
        return HASH_IDENTITY

    def embed(self, texts: tuple[str, ...], input_type: InputType) -> EmbeddingBatch:
        self.calls += 1
        self.log.events.append("embed")
        self.open_during_embed = self.log.open
        if self.failure is not None:
            raise self.failure
        if self.result is not None:
            return self.result  # type: ignore[no-any-return]
        return HashingEmbedder().embed(texts, input_type)


def assert_private(error: BaseException) -> None:
    assert MARKER not in str(error) and MARKER not in repr(error)
    assert error.__cause__ is None and error.__context__ is None
    assert MARKER not in "".join(traceback.format_exception(error))


REQUEST = RetrievalRequest(("retention period",))


def test_search_snapshot_embeds_with_no_session_open_then_retrieves() -> None:
    log = Log()
    factory, provider = Factory(log), Provider(log)
    result = search_snapshot(factory, REVIEWER, _snapshot(), REQUEST, provider)  # type: ignore[arg-type]
    assert provider.calls == 1 and provider.open_during_embed == 0
    assert log.events[:3] == ["identity", "identity", "embed"]  # ours, then embed_validated's
    assert log.events[3:] == ["session", "closed"]
    assert [item.chunk_id for item in result.items] == [CHUNK]
    assert [h.key for h in result.items[0].hits] == [(0, "lexical"), (0, "vector")]


@pytest.mark.parametrize(
    ("actor", "snapshot", "request_", "error"),
    [
        (object(), "snapshot", REQUEST, TypeError),
        (REVIEWER, "snapshot", ("retention",), InvalidRetrievalRequestError),
        (REVIEWER, "forged", REQUEST, InvalidSnapshotError),
        (ADMIN, "snapshot", REQUEST, PermissionDeniedError),
        (OUTSIDER, "snapshot", REQUEST, RetrievalScopeError),
    ],
)
def test_pure_checks_precede_any_provider_or_sql_call(
    actor: Any, snapshot: str, request_: Any, error: type[Exception]
) -> None:
    log = Log()
    factory, provider = Factory(log), Provider(log)
    value = _snapshot()
    if snapshot == "forged":
        object.__setattr__(value, "sha256", "0" * 64)
    with pytest.raises(error):
        search_snapshot(factory, actor, value, request_, provider)  # type: ignore[arg-type]
    assert provider.identity_reads == 0 and provider.calls == 0 and factory.calls == 0


def test_an_identity_getter_exception_is_a_fixed_error_with_no_embedding_call() -> None:
    log = Log()
    factory = Factory(log)
    provider = Provider(log, [RuntimeError(f"credential {MARKER}")])
    with pytest.raises(RetrievalProviderError) as raised:
        search_snapshot(factory, REVIEWER, _snapshot(), REQUEST, provider)  # type: ignore[arg-type]
    assert_private(raised.value)
    assert provider.calls == 0 and factory.calls == 0


@pytest.mark.parametrize("identity", [OTHER, "offline", None])
def test_an_identity_mismatch_or_invalid_identity_stops_before_embedding(identity: Any) -> None:
    log = Log()
    factory, provider = Factory(log), Provider(log, [identity])
    with pytest.raises(RetrievalProviderError):
        search_snapshot(factory, REVIEWER, _snapshot(), REQUEST, provider)  # type: ignore[arg-type]
    assert provider.calls == 0 and factory.calls == 0


def test_an_identity_changing_after_the_first_read_is_rejected_at_conversion() -> None:
    # First read: the snapshot identity. embed_validated then reads OTHER and the provider
    # returns a batch under OTHER, which embed_validated accepts; the conversion against the
    # snapshot identity rejects it.
    log = Log()
    factory = Factory(log)
    provider = Provider(log, [HASH_IDENTITY, OTHER])
    texts = REQUEST.queries
    provider.result = EmbeddingBatch(
        OTHER, "query", HashingEmbedder().embed(texts, "query").vectors, EmbeddingUsage(None)
    )
    with pytest.raises(RetrievalProviderError) as raised:
        search_snapshot(factory, REVIEWER, _snapshot(), REQUEST, provider)  # type: ignore[arg-type]
    assert provider.calls == 1 and factory.calls == 0
    assert_private(raised.value)


def _axis() -> tuple[float, ...]:
    return tuple(1.0 if i == 0 else 0.0 for i in range(1024))


@pytest.mark.parametrize("case", ["count", "type", "dims", "document", "norm", "exception"])
def test_malformed_provider_results_and_exceptions_are_fixed_errors(case: str) -> None:
    log = Log()
    factory, provider = Factory(log), Provider(log)
    if case == "count":
        provider.result = HashingEmbedder().embed(("a", "b"), "query")
    elif case == "type":
        provider.result = [_axis()]
    elif case == "dims":
        short = EmbeddingIdentity("offline", "fake-hash-v1", "ascii-word-sha256-v1", 3, "l2")
        provider.result = EmbeddingBatch(short, "query", ((1.0, 0.0, 0.0),), EmbeddingUsage(None))
    elif case == "document":
        provider.result = HashingEmbedder().embed(REQUEST.queries, "document")
    elif case == "norm":
        batch = HashingEmbedder().embed(REQUEST.queries, "query")
        object.__setattr__(batch, "vectors", (tuple(0.5 for _ in range(1024)),))
        provider.result = batch
    else:
        provider.failure = ConnectionError(f"provider said {MARKER}")
    with pytest.raises(RetrievalProviderError) as raised:
        search_snapshot(factory, REVIEWER, _snapshot(), REQUEST, provider)  # type: ignore[arg-type]
    assert_private(raised.value)
    assert factory.calls == 0  # never reaches the database


def test_a_norm_that_fails_only_after_float32_rounding_is_a_provider_error() -> None:
    log = Log()
    factory, provider = Factory(log), Provider(log)
    vector = list(_axis())
    vector[0] = 0.999999001  # within the provider tolerance, outside it after rounding
    provider.result = EmbeddingBatch(HASH_IDENTITY, "query", (tuple(vector),), EmbeddingUsage(None))
    with pytest.raises(RetrievalProviderError):
        search_snapshot(factory, REVIEWER, _snapshot(), REQUEST, provider)  # type: ignore[arg-type]
    assert factory.calls == 0


@pytest.mark.parametrize("control", [KeyboardInterrupt, SystemExit])
def test_process_control_from_the_provider_propagates(control: type[BaseException]) -> None:
    log = Log()
    factory, provider = Factory(log), Provider(log)
    provider.failure = control()
    with pytest.raises(control):
        search_snapshot(factory, REVIEWER, _snapshot(), REQUEST, provider)  # type: ignore[arg-type]
    log2 = Log()
    with pytest.raises(control):
        search_snapshot(Factory(log2), REVIEWER, _snapshot(), REQUEST, Provider(log2, [control()]))  # type: ignore[arg-type]


def test_search_current_captures_before_the_provider_call_then_retrieves() -> None:
    log = Log()
    factory = Factory(log, snapshot_rows=[_capture_row()], bindings=1)
    provider = Provider(log)
    snapshot, result = search_current(
        factory,  # type: ignore[arg-type]
        REVIEWER,
        vendor_id=VENDOR,
        request=REQUEST,
        provider=provider,
    )
    assert log.events == [
        "identity",  # pins the profile for capture
        "session",  # capture
        "closed",
        "identity",  # search_snapshot's check
        "identity",  # embed_validated's own read
        "embed",
        "session",  # retrieval
        "closed",
    ]
    assert provider.open_during_embed == 0
    assert result.snapshot_sha256 == snapshot.sha256 and snapshot.captured_at == NOW


@pytest.mark.parametrize(
    ("actor", "vendor", "request_", "error"),
    [
        (object(), VENDOR, REQUEST, TypeError),
        (REVIEWER, VENDOR, ("a",), InvalidRetrievalRequestError),
        (REVIEWER, str(VENDOR), REQUEST, InvalidRetrievalRequestError),
        (ADMIN, VENDOR, REQUEST, PermissionDeniedError),
    ],
)
def test_search_current_pure_checks_precede_the_provider_and_capture(
    actor: Any, vendor: Any, request_: Any, error: type[Exception]
) -> None:
    log = Log()
    factory, provider = Factory(log, snapshot_rows=[_capture_row()]), Provider(log)
    with pytest.raises(error):
        search_current(factory, actor, vendor_id=vendor, request=request_, provider=provider)  # type: ignore[arg-type]
    assert provider.identity_reads == 0 and factory.calls == 0


def test_search_current_refuses_a_provider_identity_before_capture() -> None:
    log = Log()
    factory = Factory(log, snapshot_rows=[_capture_row()])
    provider = Provider(log, [RuntimeError(MARKER)])
    with pytest.raises(RetrievalProviderError) as raised:
        search_current(factory, REVIEWER, vendor_id=VENDOR, request=REQUEST, provider=provider)  # type: ignore[arg-type]
    assert_private(raised.value)
    assert factory.calls == 0 and provider.calls == 0
