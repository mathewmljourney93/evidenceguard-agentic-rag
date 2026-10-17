"""Trusted snapshot capture and snapshot-relative hybrid retrieval (M4d, ADR-0016).

Both seams are **trusted internal programming interfaces**: no endpoint calls them and no
snapshot is deserialized from untrusted input. The tenant comes only from the trusted
``ActorContext``, whose role must be reviewer or approver.

**Transactions.** Each seam runs one short transaction through the unchanged
``document_views.read_snapshot`` helper: ``SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ
ONLY`` first, then its single ``SELECT clock_timestamp()``, which establishes the REPEATABLE READ
snapshot. The seam then runs ``SET LOCAL statement_timeout = 30000`` (per statement, not a
deadline) and its data statements, all reading that snapshot. Both settings are
transaction-local, so a pooled connection returns with its defaults. Nothing is written,
enqueued or locked explicitly (no ``FOR UPDATE``/``FOR SHARE``), and indexing is never
triggered.

**Capture** (``capture_snapshot``) examines the whole selected set in phases, so the error never
depends on row order: scope, selection (``LIMIT 101``), emptiness, revision bound, consistency,
readiness, chunk bound, then the pending/processing exclusion record. Any active revision without
a chunk set or a ready index for the pinned profile refuses the capture.

**Retrieval** (``retrieve_with_vectors``) receives a precomputed query batch and no provider. It
validates the batch independently (identity, ``query`` input type, count, numbers and canonical
float32 conversion), which cannot prove the vectors came from the claimed query strings. In one
transaction it then rechecks every immutable binding against the database (never the current
revision ``status``), runs the lexical and exact-vector channel statements, each repeating the
complete eligibility joins before its ``LIMIT 20``, fuses them in Python and loads the evidence of
the final chunks, verifying each text digest.

**Failure boundary.** The transaction body returns a result or a ``SemanticOutcome`` (one of the
fixed semantic codes); it never infers one from an exception. Any ordinary ``Exception`` from the
body is recorded as **operational**, and any ordinary ``Exception`` from session creation, the
helper's statements or cleanup is recorded as such a failure. After both ``try`` statements,
outside every handler, the seam returns the result or raises a **fresh** fixed error: the
recorded semantic error, otherwise ``RetrievalDatabaseError``. A recorded body outcome stays
primary when cleanup also fails; a successful body followed by a cleanup failure raises
``RetrievalDatabaseError``. No original exception, message, statement, parameter, cause or context
is kept. ``BaseException`` subclasses that are not ``Exception`` (process control) propagate
unconverted, also when cleanup fails while they propagate: the session handed to the unchanged
helper records any process-control exception raised by its calls, including the helper's two setup
statements, and that same exception is re-raised. This recovery records only process control; it
never classifies semantic outcomes. Nothing retries and nothing logs.
"""

import hashlib
from collections.abc import Callable, Iterable, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from functools import partial
from typing import Any, cast
from uuid import UUID

from sqlalchemy import Select, Table, and_, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_domain.embedding_storage import StoredVector, profile_id
from evidenceguard_domain.embedding_storage import (
    require_storable_identity as _require_storable_identity,
)
from evidenceguard_domain.embeddings import EmbeddingBatch, EmbeddingIdentity
from evidenceguard_domain.errors import PermissionDeniedError
from evidenceguard_domain.evidence import Authenticity, SourceType
from evidenceguard_domain.retrieval import (
    CHANNEL_LIMIT,
    LEXICAL,
    MAX_EXCLUSION_IDS,
    MAX_SNAPSHOT_CHUNKS,
    MAX_SNAPSHOT_REVISIONS,
    RETRIEVAL_CONFIG_V1,
    VECTOR,
    Channel,
    ChannelList,
    ChunkEvidence,
    EmptySnapshotError,
    FusedChunk,
    InvalidRetrievalRequestError,
    PendingExclusions,
    RetrievalConfig,
    RetrievalDatabaseError,
    RetrievalError,
    RetrievalProviderError,
    RetrievalRequest,
    RetrievalResult,
    RetrievalScopeError,
    RetrievalSnapshot,
    RetrievedChunk,
    RevisionBinding,
    SnapshotBoundsError,
    SnapshotInconsistentError,
    SnapshotNotReadyError,
    SourceSpan,
    fuse,
    query_vectors,
    revalidate_request,
    revalidate_snapshot,
    vector_skipped,
)
from evidenceguard_persistence.chunks import CHUNK_SETS
from evidenceguard_persistence.document_views import read_snapshot
from evidenceguard_persistence.documents import DOCUMENTS, REVISIONS, vendor_statement
from evidenceguard_persistence.embeddings import INDEXES, PROFILES, READY
from evidenceguard_persistence.models import Vendor

VENDORS = cast(Table, Vendor.__table__)
RETRIEVAL_ROLES = frozenset({Role.REVIEWER, Role.APPROVER})
STATEMENT_TIMEOUT_MS = 30_000
"""Per statement, transaction-local (R7). Read at call time; tests may lower it locally."""
ACTIVE = "active"
EXCLUDED_STATUSES = ("pending", "processing")
SELECTION_LIMIT = MAX_SNAPSHOT_REVISIONS + 1  # detects excess; a truncated set is never used


# --- semantic outcomes ---------------------------------------------------------------------------

_SEMANTIC_ERRORS: dict[str, type[RetrievalError]] = {
    error.code: error
    for error in (
        RetrievalScopeError,
        EmptySnapshotError,
        SnapshotBoundsError,
        SnapshotInconsistentError,
        SnapshotNotReadyError,
    )
}


@dataclass(frozen=True)
class SemanticOutcome:
    """A semantic failure found by the seam's own checks, returned as a value (never inferred
    from an exception)."""

    code: str

    def __post_init__(self) -> None:
        if self.code not in _SEMANTIC_ERRORS:
            raise ValueError("unknown semantic outcome")


SCOPE = SemanticOutcome(RetrievalScopeError.code)
EMPTY = SemanticOutcome(EmptySnapshotError.code)
BOUNDS = SemanticOutcome(SnapshotBoundsError.code)
INCONSISTENT = SemanticOutcome(SnapshotInconsistentError.code)
NOT_READY = SemanticOutcome(SnapshotNotReadyError.code)


@dataclass
class _Pending[T]:
    value: T | None = None
    succeeded: bool = False
    semantic: str | None = None
    operational: bool = False
    control: BaseException | None = None

    def record_control(self, control: BaseException) -> None:
        """Keep the first process-control exception; it is re-raised, never classified."""
        if self.control is None:
            self.control = control


class _ControlRecordingSession:
    """Delegates the session calls ``read_snapshot`` and the bodies make (``execute``,
    ``rollback``, ``close``) and records any process-control exception they raise, so that one
    raised by the helper's setup statements still propagates when an ordinary cleanup failure
    replaces it. Ordinary exceptions pass through untouched and are never inspected."""

    def __init__(self, session: Session, pending: _Pending[Any]) -> None:
        self._session = session
        self._pending = pending

    def _call[R](self, method: Callable[..., R], *args: Any, **kwargs: Any) -> R:
        try:
            return method(*args, **kwargs)
        except Exception:
            raise
        except BaseException as control:
            self._pending.record_control(control)
            raise

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        return self._call(self._session.execute, *args, **kwargs)

    def rollback(self) -> None:
        self._call(self._session.rollback)

    def close(self) -> None:
        self._call(self._session.close)


def run_read[T](
    session_factory: sessionmaker[Session],
    body: Callable[[Session, datetime], T | SemanticOutcome],
) -> T:
    """Run ``body`` inside ``read_snapshot`` behind the fixed database failure boundary (see the
    module docstring)."""
    pending: _Pending[T] = _Pending()
    environment_failed = False

    def recording_factory() -> Session:
        return cast(Session, _ControlRecordingSession(session_factory(), pending))

    try:
        with read_snapshot(cast(sessionmaker[Session], recording_factory)) as (session, now):
            try:
                outcome = body(session, now)
            except Exception:
                pending.operational = True
            except BaseException as control:
                pending.record_control(control)  # process control: propagate, never normalize
                raise
            else:
                if isinstance(outcome, SemanticOutcome):
                    pending.semantic = outcome.code
                else:
                    pending.value = outcome
                    pending.succeeded = True
    except Exception:
        environment_failed = True  # session creation, the helper's statements or cleanup
    if pending.control is not None:
        # Cleanup failed while process control propagated (from setup, the body or a session
        # call): re-raise that same control exception, unconverted.
        interrupted, pending.control = pending.control, None
        raise interrupted
    if pending.semantic is not None:
        raise _SEMANTIC_ERRORS[pending.semantic]()
    if pending.operational or environment_failed or not pending.succeeded:
        raise RetrievalDatabaseError()
    return cast(T, pending.value)


def _build[T](make: Callable[[], T]) -> T | SemanticOutcome:
    """Construct a domain value from database rows; its fixed validation error is the semantic
    ``snapshot_inconsistent`` outcome. Any other exception propagates (operational)."""
    built: list[T] = []
    failed = False
    try:
        built.append(make())
    except RetrievalError:
        failed = True
    if failed:
        return INCONSISTENT
    return built[0]


def _set_timeout(session: Session) -> None:
    session.execute(text(f"SET LOCAL statement_timeout = {int(STATEMENT_TIMEOUT_MS)}"))


# --- input validation (pure; before any database work) -------------------------------------------


def _require_actor(actor: ActorContext) -> None:
    if not isinstance(actor, ActorContext):
        raise TypeError("actor must be an ActorContext")


def _require_role(actor: ActorContext) -> None:
    if actor.role not in RETRIEVAL_ROLES:
        raise PermissionDeniedError()


def _capture_inputs(
    vendor_id: object, identity: object, config: object
) -> tuple[UUID, EmbeddingIdentity]:
    if type(vendor_id) is not UUID:
        raise InvalidRetrievalRequestError()
    checked: list[EmbeddingIdentity] = []
    with suppress(ValueError):  # the fixed InvalidEmbeddingError
        checked.append(_require_storable_identity(cast(EmbeddingIdentity, identity)))
    if not checked:
        raise InvalidRetrievalRequestError()
    if type(config) is not RetrievalConfig or config != RETRIEVAL_CONFIG_V1:
        raise InvalidRetrievalRequestError()
    return vendor_id, checked[0]


def check_retrieval_access(
    actor: ActorContext, snapshot: RetrievalSnapshot, request: RetrievalRequest
) -> tuple[RetrievalSnapshot, RetrievalRequest]:
    """Pure checks shared by every retrieval seam, in precedence order: actor type, request and
    snapshot structure (revalidated through their constructors), role, then the actor's tenant
    against the snapshot's."""
    _require_actor(actor)
    checked_request = revalidate_request(request)
    checked_snapshot = revalidate_snapshot(snapshot)
    _require_role(actor)
    if actor.tenant_id != checked_snapshot.tenant_id:
        raise RetrievalScopeError()
    return checked_snapshot, checked_request


def checked_query_vectors(
    batch: EmbeddingBatch, snapshot: RetrievalSnapshot, request: RetrievalRequest
) -> tuple[StoredVector, ...]:
    """``query_vectors`` against the snapshot identity; any failure is the fixed
    ``RetrievalProviderError``, raised outside the handler."""
    vectors: list[tuple[StoredVector, ...]] = []
    with suppress(Exception):
        vectors.append(
            query_vectors(batch, identity=snapshot.identity, query_count=len(request.queries))
        )
    if not vectors:
        raise RetrievalProviderError()
    return vectors[0]


# --- capture -------------------------------------------------------------------------------------


def selection_statement(tenant_id: UUID, vendor_id: UUID, fingerprint: str) -> Select[Any]:
    """The vendor's active pointers with their revision, chunk set, the tenant's profile for the
    fingerprint and that profile's index for the revision (left joins), by revision ID."""
    revision = and_(
        REVISIONS.c.tenant_id == DOCUMENTS.c.tenant_id,
        REVISIONS.c.id == DOCUMENTS.c.active_revision_id,
    )
    chunk_set = and_(
        CHUNK_SETS.c.tenant_id == REVISIONS.c.tenant_id,
        CHUNK_SETS.c.revision_id == REVISIONS.c.id,
    )
    profile = and_(PROFILES.c.tenant_id == tenant_id, PROFILES.c.fingerprint == fingerprint)
    index = and_(
        INDEXES.c.tenant_id == tenant_id,
        INDEXES.c.revision_id == REVISIONS.c.id,
        INDEXES.c.profile_id == PROFILES.c.id,
    )
    joined = (
        DOCUMENTS.outerjoin(REVISIONS, revision)
        .outerjoin(CHUNK_SETS, chunk_set)
        .outerjoin(PROFILES, profile)
        .outerjoin(INDEXES, index)
    )
    return (
        select(
            DOCUMENTS.c.id.label("document_id"),
            DOCUMENTS.c.active_revision_id.label("pointer_id"),
            REVISIONS.c.id.label("revision_id"),
            REVISIONS.c.document_id.label("revision_document_id"),
            REVISIONS.c.status.label("revision_status"),
            CHUNK_SETS.c.chunker_version.label("set_chunker_version"),
            CHUNK_SETS.c.chunk_count.label("set_chunk_count"),
            CHUNK_SETS.c.manifest_sha256.label("set_manifest_sha256"),
            PROFILES.c.id.label("profile_id"),
            PROFILES.c.provider_id.label("profile_provider_id"),
            PROFILES.c.model_id.label("profile_model_id"),
            PROFILES.c.algorithm_version.label("profile_algorithm_version"),
            PROFILES.c.dims.label("profile_dims"),
            PROFILES.c.normalization.label("profile_normalization"),
            PROFILES.c.fingerprint.label("profile_fingerprint"),
            INDEXES.c.id.label("index_id"),
            INDEXES.c.status.label("index_status"),
            INDEXES.c.chunker_version.label("index_chunker_version"),
            INDEXES.c.chunk_count.label("index_chunk_count"),
            INDEXES.c.manifest_sha256.label("index_manifest_sha256"),
            INDEXES.c.vector_manifest_sha256.label("index_vector_manifest_sha256"),
        )
        .select_from(joined)
        .where(
            DOCUMENTS.c.tenant_id == tenant_id,
            DOCUMENTS.c.vendor_id == vendor_id,
            DOCUMENTS.c.active_revision_id.is_not(None),
        )
        .order_by(DOCUMENTS.c.active_revision_id)
        .limit(SELECTION_LIMIT)
    )


def _excluded_revisions(tenant_id: UUID, vendor_id: UUID) -> Any:
    documents = and_(
        DOCUMENTS.c.tenant_id == REVISIONS.c.tenant_id,
        DOCUMENTS.c.id == REVISIONS.c.document_id,
    )
    return REVISIONS.join(DOCUMENTS, documents), and_(
        REVISIONS.c.tenant_id == tenant_id,
        DOCUMENTS.c.vendor_id == vendor_id,
        REVISIONS.c.status.in_(EXCLUDED_STATUSES),
    )


def exclusion_count_statement(tenant_id: UUID, vendor_id: UUID) -> Select[Any]:
    joined, condition = _excluded_revisions(tenant_id, vendor_id)
    return select(func.count()).select_from(joined).where(condition)


def exclusion_ids_statement(tenant_id: UUID, vendor_id: UUID) -> Select[Any]:
    joined, condition = _excluded_revisions(tenant_id, vendor_id)
    return (
        select(REVISIONS.c.id)
        .select_from(joined)
        .where(condition)
        .order_by(REVISIONS.c.id)
        .limit(MAX_EXCLUSION_IDS)
    )


def _profile_matches(row: Any, tenant_id: UUID, identity: EmbeddingIdentity) -> bool:
    return bool(
        row.profile_id == profile_id(tenant_id, identity.fingerprint)
        and row.profile_provider_id == identity.provider_id
        and row.profile_model_id == identity.model_id
        and row.profile_algorithm_version == identity.algorithm_version
        and row.profile_dims == identity.dims
        and row.profile_normalization == identity.normalization
        and row.profile_fingerprint == identity.fingerprint
    )


def _ready(row: Any) -> bool:
    return (
        row.set_chunker_version is not None
        and row.profile_id is not None
        and row.index_id is not None
        and row.index_status == READY
        and row.index_chunker_version == row.set_chunker_version
        and row.index_chunk_count == row.set_chunk_count
        and row.index_manifest_sha256 == row.set_manifest_sha256
        and row.index_vector_manifest_sha256 is not None
    )


def evaluate_selection(
    rows: Sequence[Any], tenant_id: UUID, identity: EmbeddingIdentity
) -> tuple[RevisionBinding, ...] | SemanticOutcome:
    """Capture phases 3 to 7 over the **whole** selected set, so the outcome never depends on row
    order: emptiness, revision bound, consistency, readiness, chunk bound. Returns the bindings
    or the semantic outcome."""
    if not rows:
        return EMPTY
    if len(rows) > MAX_SNAPSHOT_REVISIONS:
        return BOUNDS
    for row in rows:
        if (
            row.revision_id is None
            or row.revision_id != row.pointer_id
            or row.revision_status != ACTIVE
            or row.revision_document_id != row.document_id
            or (row.profile_id is not None and not _profile_matches(row, tenant_id, identity))
        ):
            return INCONSISTENT
    if not all(_ready(row) for row in rows):
        return NOT_READY
    counts = [row.set_chunk_count for row in rows]
    if not all(type(count) is int for count in counts):
        return INCONSISTENT
    if sum(counts) > MAX_SNAPSHOT_CHUNKS:
        return BOUNDS
    bindings: list[RevisionBinding] = []
    for row in rows:
        binding = _build(
            partial(
                RevisionBinding,
                row.revision_id,
                row.document_id,
                row.index_id,
                row.set_chunker_version,
                row.set_chunk_count,
                row.set_manifest_sha256,
                row.index_vector_manifest_sha256,
            )
        )
        if isinstance(binding, SemanticOutcome):
            return binding
        bindings.append(binding)
    return tuple(bindings)


def _capture_body(
    actor: ActorContext, vendor_id: UUID, identity: EmbeddingIdentity
) -> Callable[[Session, datetime], RetrievalSnapshot | SemanticOutcome]:
    tenant_id = actor.tenant_id

    def body(session: Session, now: datetime) -> RetrievalSnapshot | SemanticOutcome:
        _set_timeout(session)
        if session.execute(vendor_statement(tenant_id, vendor_id)).first() is None:
            return SCOPE
        rows = session.execute(
            selection_statement(tenant_id, vendor_id, identity.fingerprint)
        ).all()
        bindings = evaluate_selection(rows, tenant_id, identity)
        if isinstance(bindings, SemanticOutcome):
            return bindings
        count = session.execute(exclusion_count_statement(tenant_id, vendor_id)).scalar_one()
        excluded = tuple(session.execute(exclusion_ids_statement(tenant_id, vendor_id)).scalars())
        return _build(
            lambda: RetrievalSnapshot(
                tenant_id,
                vendor_id,
                identity,
                RETRIEVAL_CONFIG_V1,
                bindings,
                PendingExclusions(count, excluded, count > MAX_EXCLUSION_IDS),
                now,
            )
        )

    return body


def capture_snapshot(
    session_factory: sessionmaker[Session],
    actor: ActorContext,
    *,
    vendor_id: UUID,
    identity: EmbeddingIdentity,
    config: RetrievalConfig = RETRIEVAL_CONFIG_V1,
) -> RetrievalSnapshot:
    """Capture the vendor's eligible revisions for ``identity`` in one read transaction (see
    the module docstring). Error precedence: input, role, scope, emptiness, revision bound,
    consistency, readiness, chunk bound; database failures are ``RetrievalDatabaseError``."""
    _require_actor(actor)
    checked_vendor, checked_identity = _capture_inputs(vendor_id, identity, config)
    _require_role(actor)
    return run_read(session_factory, _capture_body(actor, checked_vendor, checked_identity))


# --- retrieval statements ------------------------------------------------------------------------

_BINDINGS = """unnest(
    CAST(:revision_ids AS uuid[]), CAST(:document_ids AS uuid[]),
    CAST(:index_ids AS uuid[]), CAST(:chunker_versions AS text[])
) AS b(revision_id, document_id, index_id, chunker_version)"""

_ELIGIBILITY_JOINS = """
JOIN documents AS d
  ON d.tenant_id = :tenant_id AND d.id = b.document_id AND d.vendor_id = :vendor_id
JOIN document_revisions AS r
  ON r.tenant_id = :tenant_id AND r.id = b.revision_id AND r.document_id = d.id
 AND r.activated_at IS NOT NULL
JOIN embedding_indexes AS i
  ON i.tenant_id = :tenant_id AND i.id = b.index_id AND i.revision_id = r.id
 AND i.chunker_version = b.chunker_version AND i.status = 'ready' AND i.profile_id = :profile_id
JOIN chunk_embeddings AS e
  ON e.tenant_id = :tenant_id AND e.index_id = i.id
 AND e.revision_id = i.revision_id AND e.chunker_version = i.chunker_version"""

_CHUNK_JOIN = """
JOIN chunks AS c
  ON c.tenant_id = :tenant_id AND c.id = e.chunk_id AND c.revision_id = e.revision_id
 AND c.chunker_version = e.chunker_version AND c.content_sha256 = e.content_sha256"""

BINDING_RECHECK_SQL = """SELECT count(*) AS verified
FROM unnest(
    CAST(:revision_ids AS uuid[]), CAST(:document_ids AS uuid[]),
    CAST(:index_ids AS uuid[]), CAST(:chunker_versions AS text[]),
    CAST(:chunk_counts AS integer[]), CAST(:manifests AS text[]),
    CAST(:vector_manifests AS text[])
) AS b(revision_id, document_id, index_id, chunker_version, chunk_count, manifest_sha256,
       vector_manifest_sha256)
JOIN vendors AS v
  ON v.tenant_id = :tenant_id AND v.id = :vendor_id
JOIN documents AS d
  ON d.tenant_id = :tenant_id AND d.id = b.document_id AND d.vendor_id = v.id
JOIN document_revisions AS r
  ON r.tenant_id = :tenant_id AND r.id = b.revision_id AND r.document_id = d.id
 AND r.activated_at IS NOT NULL
JOIN chunk_sets AS s
  ON s.tenant_id = :tenant_id AND s.revision_id = r.id
 AND s.chunker_version = b.chunker_version AND s.chunk_count = b.chunk_count
 AND s.manifest_sha256 = b.manifest_sha256
JOIN embedding_indexes AS i
  ON i.tenant_id = :tenant_id AND i.id = b.index_id AND i.revision_id = r.id
 AND i.chunker_version = s.chunker_version AND i.chunk_count = s.chunk_count
 AND i.manifest_sha256 = s.manifest_sha256 AND i.status = 'ready'
 AND i.profile_id = :profile_id AND i.vector_manifest_sha256 = b.vector_manifest_sha256
JOIN embedding_profiles AS p
  ON p.tenant_id = :tenant_id AND p.id = i.profile_id
 AND p.provider_id = :provider_id AND p.model_id = :model_id
 AND p.algorithm_version = :algorithm_version AND p.dims = :dims
 AND p.normalization = :normalization AND p.fingerprint = :fingerprint"""

LEXICAL_SQL = f"""SELECT c.id AS chunk_id, ts_rank_cd(c.search_vector, q.tsq, 0) AS score
FROM (
    SELECT websearch_to_tsquery(CAST('simple' AS regconfig), CAST(:query AS text)) AS tsq
) AS q
CROSS JOIN {_BINDINGS}{_ELIGIBILITY_JOINS}{_CHUNK_JOIN}
WHERE c.search_vector @@ q.tsq
  AND ts_rank_cd(c.search_vector, q.tsq, 0) > 0
ORDER BY score DESC, c.id ASC
LIMIT {CHANNEL_LIMIT}"""

VECTOR_SQL = f"""SELECT e.chunk_id AS chunk_id,
       e.embedding <=> CAST(:query_vector AS vector(1024)) AS score
FROM {_BINDINGS}{_ELIGIBILITY_JOINS}
WHERE NOT e.is_zero
ORDER BY score ASC, e.chunk_id ASC
LIMIT {CHANNEL_LIMIT}"""

EVIDENCE_SQL = f"""SELECT c.id AS chunk_id, c.revision_id, d.id AS document_id, c.ordinal, c.text,
       c.content_sha256, c.section_path, c.is_table, c.line_start, c.line_end, c.char_start,
       c.char_end, c.header_line_start, c.header_line_end, c.header_char_start, c.header_char_end,
       d.document_key, d.title, d.source_type, d.authenticity, r.revision_no, r.version_label,
       r.effective_date
FROM {_BINDINGS}{_ELIGIBILITY_JOINS}{_CHUNK_JOIN}
WHERE e.chunk_id = ANY(CAST(:chunk_ids AS uuid[]))"""


def binding_parameters(snapshot: RetrievalSnapshot) -> dict[str, Any]:
    """Bind parameters for the snapshot's bindings, tenant, vendor and pinned profile."""
    bindings = snapshot.bindings
    identity = snapshot.identity
    return {
        "tenant_id": snapshot.tenant_id,
        "vendor_id": snapshot.vendor_id,
        "profile_id": snapshot.profile_id,
        "revision_ids": [binding.revision_id for binding in bindings],
        "document_ids": [binding.document_id for binding in bindings],
        "index_ids": [binding.index_id for binding in bindings],
        "chunker_versions": [binding.chunker_version for binding in bindings],
        "chunk_counts": [binding.chunk_count for binding in bindings],
        "manifests": [binding.manifest_sha256 for binding in bindings],
        "vector_manifests": [binding.vector_manifest_sha256 for binding in bindings],
        "provider_id": identity.provider_id,
        "model_id": identity.model_id,
        "algorithm_version": identity.algorithm_version,
        "dims": identity.dims,
        "normalization": identity.normalization,
        "fingerprint": identity.fingerprint,
    }


def _channel_list(
    position: int, channel: Channel, rows: Iterable[Any]
) -> ChannelList | SemanticOutcome:
    entries = tuple((row.chunk_id, row.score) for row in rows)
    return _build(partial(ChannelList, position, channel, entries))


def _member[E: StrEnum](kind: type[E], value: object) -> E | None:
    """The enum member with this value, or ``None`` (then the evidence value is rejected)."""
    for member in kind:
        if member.value == value:
            return member
    return None


def _evidence(row: Any) -> ChunkEvidence:
    header = (
        None
        if row.header_char_start is None
        else SourceSpan(
            row.header_line_start, row.header_line_end, row.header_char_start, row.header_char_end
        )
    )
    section_path = row.section_path
    return ChunkEvidence(
        row.chunk_id,
        row.text,
        row.content_sha256,
        row.ordinal,
        tuple(section_path) if type(section_path) is list else section_path,
        row.is_table,
        SourceSpan(row.line_start, row.line_end, row.char_start, row.char_end),
        header,
        row.document_key,
        row.title,
        row.revision_no,
        row.version_label,
        row.effective_date,
        cast(SourceType, _member(SourceType, row.source_type)),
        cast(Authenticity, _member(Authenticity, row.authenticity)),
    )


def _verified_text(row: Any) -> bool:
    """The returned text hashes to its stored digest (detects one class of tampering only)."""
    if type(row.text) is not str:
        return False
    try:
        digest = hashlib.sha256(row.text.encode("utf-8")).hexdigest()
    except UnicodeEncodeError:
        return False
    return bool(digest == row.content_sha256)


def _retrieved(chunk: FusedChunk, row: Any) -> RetrievedChunk:
    return RetrievedChunk(
        chunk.chunk_id,
        row.revision_id,
        row.document_id,
        chunk.fused_rank,
        chunk.fused_score,
        chunk.hits,
        _evidence(row),
    )


def _items(
    fused: tuple[FusedChunk, ...], rows: Sequence[Any]
) -> tuple[RetrievedChunk, ...] | SemanticOutcome:
    by_id = {row.chunk_id: row for row in rows}
    if len(by_id) != len(rows) or set(by_id) != {chunk.chunk_id for chunk in fused}:
        return INCONSISTENT
    if not all(_verified_text(row) for row in rows):
        return INCONSISTENT
    items: list[RetrievedChunk] = []
    for chunk in fused:
        item = _build(partial(_retrieved, chunk, by_id[chunk.chunk_id]))
        if isinstance(item, SemanticOutcome):
            return item
        items.append(item)
    return tuple(items)


def _retrieval_body(
    snapshot: RetrievalSnapshot, request: RetrievalRequest, vectors: tuple[StoredVector, ...]
) -> Callable[[Session, datetime], RetrievalResult | SemanticOutcome]:
    skipped = vector_skipped(vectors)
    parameters = binding_parameters(snapshot)

    def body(session: Session, now: datetime) -> RetrievalResult | SemanticOutcome:
        _set_timeout(session)
        verified = session.execute(text(BINDING_RECHECK_SQL), parameters).scalar_one()
        if type(verified) is not int or verified != len(snapshot.bindings):
            return INCONSISTENT
        lists: list[ChannelList] = []
        for position, query in enumerate(request.queries):
            rows = session.execute(text(LEXICAL_SQL), {**parameters, "query": query}).all()
            lexical = _channel_list(position, LEXICAL, rows)
            if isinstance(lexical, SemanticOutcome):
                return lexical
            lists.append(lexical)
            if position in skipped:
                continue
            literal = vectors[position].literal()
            rows = session.execute(text(VECTOR_SQL), {**parameters, "query_vector": literal}).all()
            vector = _channel_list(position, VECTOR, rows)
            if isinstance(vector, SemanticOutcome):
                return vector
            lists.append(vector)
        fused = _build(
            lambda: fuse(
                tuple(lists), query_count=len(request.queries), vector_skipped=skipped, k=request.k
            )
        )
        if isinstance(fused, SemanticOutcome):
            return fused
        items: tuple[RetrievedChunk, ...] = ()
        if fused:
            evidence_parameters = {**parameters, "chunk_ids": [chunk.chunk_id for chunk in fused]}
            rows = session.execute(text(EVIDENCE_SQL), evidence_parameters).all()
            loaded = _items(fused, rows)
            if isinstance(loaded, SemanticOutcome):
                return loaded
            items = loaded
        return _build(
            partial(RetrievalResult, snapshot, len(request.queries), request.k, skipped, items)
        )

    return body


def retrieve_with_vectors(
    session_factory: sessionmaker[Session],
    actor: ActorContext,
    snapshot: RetrievalSnapshot,
    request: RetrievalRequest,
    query_batch: EmbeddingBatch,
) -> RetrievalResult:
    """Retrieve within ``snapshot`` using a precomputed query batch (trusted internal input; no
    provider object). Validates everything before opening a transaction (see the module
    docstring)."""
    checked_snapshot, checked_request = check_retrieval_access(actor, snapshot, request)
    vectors = checked_query_vectors(query_batch, checked_snapshot, checked_request)
    return run_read(session_factory, _retrieval_body(checked_snapshot, checked_request, vectors))
