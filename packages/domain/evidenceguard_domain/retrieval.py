"""Snapshot and retrieval contracts, canonical digests and pure RRF fusion (M4d, ADR-0016).

Pure values and functions, standard library and domain only. Persistence
(``evidenceguard_persistence.retrieval``) captures snapshots and runs the channel queries; the
worker (``evidenceguard_worker.retrieval``) calls the embedding provider. Both use the values,
the query-vector conversion and ``fuse`` defined here.

- **Values** are frozen dataclasses whose constructors validate exact types (``type(x) is …``:
  no coercion, no ``bool`` for ``int``, tuples only, no ``str`` for a ``UUID``), reject unknown
  keyword arguments, never strip or normalize text and raise fixed errors outside any ``except``
  block. ``dataclasses.replace`` revalidates through the constructor. Derived identifiers and
  digests are computed by the constructor and are never accepted as arguments. ``repr`` and
  ``str`` show identifiers and counts only: never query text, chunk text, section paths or
  vectors.
- **Canonical encoding** ``eg-retrieval-canonical-v1``: ``json.dumps(value, sort_keys=True,
  separators=(",", ":"), ensure_ascii=True, allow_nan=False)`` encoded as ASCII, hashed with
  SHA-256 (lowercase hex). Only JSON objects with string keys, arrays, strings, integers and
  booleans are encodable; anything else (floats, ``None``, tuples, other objects) is rejected
  rather than stringified. UUIDs are ``str(uuid)``; ``captured_at`` is UTC with exactly six
  fractional digits and a ``Z`` suffix.
- **Fusion** is reciprocal-rank fusion with constant 60, summed exactly as ``Fraction`` values,
  ordered by fused score descending and chunk UUID ascending.

A digest or timestamp is neither authorization nor proof of past eligibility, and it is not a
unique capture identifier: identical encoded fields give the same digest, and anyone can
recompute it.
"""

import hashlib
import json
import math
import re
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from fractions import Fraction
from functools import partial
from itertools import pairwise
from typing import Any, ClassVar, Literal
from uuid import UUID

from evidenceguard_domain.chunks import (
    MAX_CHUNK_CHARS,
    MAX_CHUNKS_PER_REVISION,
    MAX_SECTION_DEPTH,
    content_sha256,
    validate_chunker_version,
)
from evidenceguard_domain.embedding_storage import (
    StoredVector,
    allows_zero_vectors,
    canonical_vector,
    index_id,
    profile_id,
    require_storable_identity,
)
from evidenceguard_domain.embeddings import (
    LEXICAL_HASH_LABEL,
    EmbeddingBatch,
    EmbeddingIdentity,
    InvalidEmbeddingError,
    validate_result,
)
from evidenceguard_domain.evidence import Authenticity, SourceType

CANONICAL_ENCODING = "eg-retrieval-canonical-v1"
MAX_QUERIES = 8
MAX_QUERY_CHARS = 4000
MAX_QUERY_BYTES = 16_000
MAX_SNAPSHOT_REVISIONS = 100
MAX_SNAPSHOT_CHUNKS = 100_000
MAX_EXCLUSION_IDS = 100
CHANNEL_LIMIT = 20
RRF_CONSTANT = 60
DEFAULT_K = 8
MAX_K = 20
PROVIDER_EMBEDDINGS_LABEL = "provider embeddings"

Channel = Literal["lexical", "vector"]
LEXICAL: Channel = "lexical"
VECTOR: Channel = "vector"
_CHANNELS = (LEXICAL, VECTOR)
_SHA256 = re.compile(r"[0-9a-f]{64}", re.ASCII)
_MAX_ENCODING_DEPTH = 8


# --- errors (fixed messages: the message is the code) ------------------------------------------


class RetrievalError(Exception):
    """Base of the fixed M4d errors. Never carries submitted values, content or causes."""

    code: ClassVar[str] = "retrieval_error"

    def __init__(self) -> None:
        super().__init__(self.code)


class InvalidRetrievalRequestError(RetrievalError):
    """A malformed request, ``k``, vendor ID, identity, configuration or result value."""

    code = "invalid_retrieval_request"


class InvalidSnapshotError(RetrievalError):
    """A structurally invalid snapshot value from a caller."""

    code = "invalid_snapshot"


class RetrievalScopeError(RetrievalError):
    """A missing or foreign vendor at capture, or an actor outside the snapshot's tenant."""

    code = "retrieval_scope"


class EmptySnapshotError(RetrievalError):
    """The vendor has no active revision."""

    code = "snapshot_empty"


class SnapshotBoundsError(RetrievalError):
    """More than 100 active revisions or more than 100,000 eligible chunks."""

    code = "snapshot_bounds_exceeded"


class SnapshotNotReadyError(RetrievalError):
    """An active revision lacks a chunk set or a ready index for the profile (no IDs given)."""

    code = "snapshot_not_ready"


class SnapshotInconsistentError(RetrievalError):
    """A failed binding recheck, a non-active pointer, an invalid value built from rows, a text
    digest mismatch or a non-finite score."""

    code = "snapshot_inconsistent"


class RetrievalProviderError(RetrievalError):
    """Provider identity, embedding, batch validation or canonical query conversion failed."""

    code = "retrieval_provider_failed"


class RetrievalDatabaseError(RetrievalError):
    """An operational database failure, including timeouts and cleanup failures."""

    code = "retrieval_database_failed"


# --- helpers -------------------------------------------------------------------------------------


def _check(condition: bool, error: type[RetrievalError]) -> None:
    if not condition:
        raise error()


def _rebuild[T](make: Callable[[], T], error: type[RetrievalError]) -> T:
    """Run a nested constructor and map its fixed error to ``error``, raised outside the
    handler so no cause or context is retained."""
    built: list[T] = []
    with suppress(RetrievalError, InvalidEmbeddingError, ValueError, TypeError):
        built.append(make())
    if not built:
        raise error()
    return built[0]


def _is_uuid(value: object) -> bool:
    return type(value) is UUID


def _is_sha256(value: object) -> bool:
    return type(value) is str and _SHA256.fullmatch(value) is not None


def _is_int(value: object, low: int, high: int | None = None) -> bool:
    return type(value) is int and value >= low and (high is None or value <= high)


def _is_chunker_version(value: object) -> bool:
    if type(value) is not str:
        return False
    try:
        validate_chunker_version(value)
    except ValueError:
        return False
    return True


def _is_query(value: object) -> bool:
    if type(value) is not str:
        return False
    if not 1 <= len(value) <= MAX_QUERY_CHARS or "\x00" in value or value.isspace():
        return False
    try:
        size = len(value.encode("utf-8", errors="strict"))
    except UnicodeEncodeError:
        return False
    return size <= MAX_QUERY_BYTES


def _is_finite_float(value: object) -> bool:
    return type(value) is float and math.isfinite(value)


def _strictly_ascending(values: tuple[Any, ...]) -> bool:
    return all(left < right for left, right in pairwise(values))


# --- canonical encoding --------------------------------------------------------------------------


def _encodable(value: object, depth: int = 0) -> bool:
    if depth > _MAX_ENCODING_DEPTH:
        return False
    if type(value) is dict:
        return all(type(key) is str and _encodable(item, depth + 1) for key, item in value.items())
    if type(value) is list:
        return all(_encodable(item, depth + 1) for item in value)
    return type(value) in (str, int, bool)


def canonical_bytes(value: dict[str, Any]) -> bytes:
    """The ``eg-retrieval-canonical-v1`` bytes of a JSON object, or ``InvalidSnapshotError``."""
    _check(type(value) is dict and _encodable(value), InvalidSnapshotError)
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def canonical_sha256(value: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def canonical_timestamp(value: datetime) -> str:
    """``YYYY-MM-DDTHH:MM:SS.ffffffZ`` in UTC, or ``InvalidSnapshotError``."""
    utc = _utc(value)
    return (
        f"{utc.year:04d}-{utc.month:02d}-{utc.day:02d}T"
        f"{utc.hour:02d}:{utc.minute:02d}:{utc.second:02d}.{utc.microsecond:06d}Z"
    )


def _utc(value: object) -> datetime:
    _check(type(value) is datetime, InvalidSnapshotError)
    assert isinstance(value, datetime)
    _check(value.tzinfo is not None and value.utcoffset() is not None, InvalidSnapshotError)
    converted: list[datetime] = []
    with suppress(OverflowError, ValueError):
        converted.append(value.astimezone(UTC))
    _check(bool(converted), InvalidSnapshotError)
    return converted[0]


# --- configuration -------------------------------------------------------------------------------

_CONFIG_V1: dict[str, str | int] = {
    "version": "hybrid-rrf-v1",
    "text_search_config": "simple",
    "lexical_query": "websearch_to_tsquery",
    "lexical_score": "ts_rank_cd",
    "lexical_normalization": 0,
    "vector_operator": "cosine_distance",
    "channel_limit": CHANNEL_LIMIT,
    "rrf_constant": RRF_CONSTANT,
    "default_k": DEFAULT_K,
    "max_k": MAX_K,
}


@dataclass(frozen=True, init=False, repr=False)
class RetrievalConfig:
    """The retrieval configuration. Exactly one value is accepted: ``RETRIEVAL_CONFIG_V1``."""

    version: str
    text_search_config: str
    lexical_query: str
    lexical_score: str
    lexical_normalization: int
    vector_operator: str
    channel_limit: int
    rrf_constant: int
    default_k: int
    max_k: int
    config_sha256: str = field(init=False)

    def __init__(
        self,
        *,
        version: str = "hybrid-rrf-v1",
        text_search_config: str = "simple",
        lexical_query: str = "websearch_to_tsquery",
        lexical_score: str = "ts_rank_cd",
        lexical_normalization: int = 0,
        vector_operator: str = "cosine_distance",
        channel_limit: int = CHANNEL_LIMIT,
        rrf_constant: int = RRF_CONSTANT,
        default_k: int = DEFAULT_K,
        max_k: int = MAX_K,
        **unknown: object,
    ) -> None:
        _check(not unknown, InvalidRetrievalRequestError)
        values: dict[str, object] = {
            "version": version,
            "text_search_config": text_search_config,
            "lexical_query": lexical_query,
            "lexical_score": lexical_score,
            "lexical_normalization": lexical_normalization,
            "vector_operator": vector_operator,
            "channel_limit": channel_limit,
            "rrf_constant": rrf_constant,
            "default_k": default_k,
            "max_k": max_k,
        }
        for name, expected in _CONFIG_V1.items():
            value = values[name]
            _check(
                type(value) is type(expected) and value == expected, InvalidRetrievalRequestError
            )
        for name, value in values.items():
            object.__setattr__(self, name, value)
        object.__setattr__(self, "config_sha256", canonical_sha256(self.canonical_object()))

    def canonical_object(self) -> dict[str, Any]:
        fields = {name: getattr(self, name) for name in _CONFIG_V1}
        return {"canonical": CANONICAL_ENCODING, "kind": "retrieval_config", **fields}

    def __repr__(self) -> str:
        return f"RetrievalConfig(version={self.version!r})"

    __str__ = __repr__


RETRIEVAL_CONFIG_V1 = RetrievalConfig()


def _revalidate_config(config: object) -> RetrievalConfig:
    _check(type(config) is RetrievalConfig, InvalidRetrievalRequestError)
    assert isinstance(config, RetrievalConfig)
    return RetrievalConfig(
        version=config.version,
        text_search_config=config.text_search_config,
        lexical_query=config.lexical_query,
        lexical_score=config.lexical_score,
        lexical_normalization=config.lexical_normalization,
        vector_operator=config.vector_operator,
        channel_limit=config.channel_limit,
        rrf_constant=config.rrf_constant,
        default_k=config.default_k,
        max_k=config.max_k,
    )


# --- request -------------------------------------------------------------------------------------


@dataclass(frozen=True, init=False, repr=False)
class RetrievalRequest:
    """1 to 8 distinct verbatim queries and ``k`` (1 to 20, default 8)."""

    queries: tuple[str, ...]
    k: int

    def __init__(self, queries: tuple[str, ...], k: int = DEFAULT_K, **unknown: object) -> None:
        error = InvalidRetrievalRequestError
        _check(not unknown, error)
        _check(type(queries) is tuple and 1 <= len(queries) <= MAX_QUERIES, error)
        _check(all(_is_query(query) for query in queries), error)
        _check(len(set(queries)) == len(queries), error)  # exact code-point equality
        _check(_is_int(k, 1, MAX_K), error)
        object.__setattr__(self, "queries", queries)
        object.__setattr__(self, "k", k)

    def __repr__(self) -> str:
        return f"RetrievalRequest(queries={len(self.queries)}, k={self.k})"

    __str__ = __repr__


def revalidate_request(request: object) -> RetrievalRequest:
    _check(type(request) is RetrievalRequest, InvalidRetrievalRequestError)
    assert isinstance(request, RetrievalRequest)
    return RetrievalRequest(request.queries, request.k)


# --- snapshot ------------------------------------------------------------------------------------


@dataclass(frozen=True, init=False, repr=False)
class PendingExclusions:
    """Pending and processing revisions at capture: the exact ``count``, at most 100 ascending
    ``revision_ids`` and ``truncated`` exactly when ``count`` exceeds 100. Provenance only."""

    count: int
    revision_ids: tuple[UUID, ...]
    truncated: bool

    def __init__(
        self, count: int, revision_ids: tuple[UUID, ...], truncated: bool, **unknown: object
    ) -> None:
        error = InvalidSnapshotError
        _check(not unknown and _is_int(count, 0) and type(truncated) is bool, error)
        _check(type(revision_ids) is tuple and all(map(_is_uuid, revision_ids)), error)
        _check(_strictly_ascending(revision_ids), error)
        _check(len(revision_ids) == min(count, MAX_EXCLUSION_IDS), error)
        _check(truncated == (count > MAX_EXCLUSION_IDS), error)
        object.__setattr__(self, "count", count)
        object.__setattr__(self, "revision_ids", revision_ids)
        object.__setattr__(self, "truncated", truncated)

    def __repr__(self) -> str:
        return f"PendingExclusions(count={self.count}, truncated={self.truncated})"

    __str__ = __repr__


def _revalidate_exclusions(value: object) -> PendingExclusions:
    _check(type(value) is PendingExclusions, InvalidSnapshotError)
    assert isinstance(value, PendingExclusions)
    return PendingExclusions(value.count, value.revision_ids, value.truncated)


@dataclass(frozen=True, init=False, repr=False)
class RevisionBinding:
    """One captured revision: its document, verified chunk set and ready index."""

    revision_id: UUID
    document_id: UUID
    index_id: UUID
    chunker_version: str
    chunk_count: int
    manifest_sha256: str
    vector_manifest_sha256: str

    def __init__(
        self,
        revision_id: UUID,
        document_id: UUID,
        index_id: UUID,
        chunker_version: str,
        chunk_count: int,
        manifest_sha256: str,
        vector_manifest_sha256: str,
        **unknown: object,
    ) -> None:
        error = InvalidSnapshotError
        _check(not unknown, error)
        _check(_is_uuid(revision_id) and _is_uuid(document_id) and _is_uuid(index_id), error)
        _check(_is_chunker_version(chunker_version), error)
        _check(_is_int(chunk_count, 1, MAX_CHUNKS_PER_REVISION), error)
        _check(_is_sha256(manifest_sha256) and _is_sha256(vector_manifest_sha256), error)
        object.__setattr__(self, "revision_id", revision_id)
        object.__setattr__(self, "document_id", document_id)
        object.__setattr__(self, "index_id", index_id)
        object.__setattr__(self, "chunker_version", chunker_version)
        object.__setattr__(self, "chunk_count", chunk_count)
        object.__setattr__(self, "manifest_sha256", manifest_sha256)
        object.__setattr__(self, "vector_manifest_sha256", vector_manifest_sha256)

    def canonical_object(self) -> dict[str, Any]:
        return {
            "revision_id": str(self.revision_id),
            "document_id": str(self.document_id),
            "chunker_version": self.chunker_version,
            "chunk_count": self.chunk_count,
            "manifest_sha256": self.manifest_sha256,
            "index_id": str(self.index_id),
            "vector_manifest_sha256": self.vector_manifest_sha256,
        }

    def __repr__(self) -> str:
        return (
            f"RevisionBinding(revision_id={self.revision_id}, index_id={self.index_id}, "
            f"chunk_count={self.chunk_count})"
        )

    __str__ = __repr__


def _revalidate_binding(value: object) -> RevisionBinding:
    _check(type(value) is RevisionBinding, InvalidSnapshotError)
    assert isinstance(value, RevisionBinding)
    return RevisionBinding(
        value.revision_id,
        value.document_id,
        value.index_id,
        value.chunker_version,
        value.chunk_count,
        value.manifest_sha256,
        value.vector_manifest_sha256,
    )


@dataclass(frozen=True, init=False, repr=False)
class RetrievalSnapshot:
    """An immutable, trusted in-process snapshot (see ADR-0016's trust model).

    ``profile_id``, ``total_chunks`` and ``sha256`` are derived. Invariants: 1 to 100 bindings in
    strictly ascending ``revision_id`` order; one binding per document; each ``index_id``
    derived from the tenant, revision, chunker version and profile; at most 100,000 chunks; no
    excluded revision among the bindings; a timezone-aware ``captured_at`` (stored in UTC).
    """

    tenant_id: UUID
    vendor_id: UUID
    identity: EmbeddingIdentity
    config: RetrievalConfig
    bindings: tuple[RevisionBinding, ...]
    exclusions: PendingExclusions
    captured_at: datetime
    profile_id: UUID = field(init=False)
    total_chunks: int = field(init=False)
    sha256: str = field(init=False)

    def __init__(
        self,
        tenant_id: UUID,
        vendor_id: UUID,
        identity: EmbeddingIdentity,
        config: RetrievalConfig,
        bindings: tuple[RevisionBinding, ...],
        exclusions: PendingExclusions,
        captured_at: datetime,
        **unknown: object,
    ) -> None:
        error = InvalidSnapshotError
        _check(not unknown, error)
        _check(_is_uuid(tenant_id) and _is_uuid(vendor_id), error)
        checked_identity = _rebuild(lambda: require_storable_identity(identity), error)
        checked_config = _rebuild(lambda: _revalidate_config(config), error)
        _check(type(bindings) is tuple, error)
        _check(1 <= len(bindings) <= MAX_SNAPSHOT_REVISIONS, error)
        checked_bindings = tuple(
            _rebuild(partial(_revalidate_binding, value), error) for value in bindings
        )
        checked_exclusions = _rebuild(lambda: _revalidate_exclusions(exclusions), error)
        stamp = _utc(captured_at)

        profile = profile_id(tenant_id, checked_identity.fingerprint)
        revisions = tuple(binding.revision_id for binding in checked_bindings)
        _check(_strictly_ascending(revisions), error)
        documents = {binding.document_id for binding in checked_bindings}
        _check(len(documents) == len(checked_bindings), error)
        for binding in checked_bindings:
            expected = index_id(tenant_id, binding.revision_id, binding.chunker_version, profile)
            _check(binding.index_id == expected, error)
        total = sum(binding.chunk_count for binding in checked_bindings)
        _check(total <= MAX_SNAPSHOT_CHUNKS, error)
        _check(not set(revisions) & set(checked_exclusions.revision_ids), error)

        object.__setattr__(self, "tenant_id", tenant_id)
        object.__setattr__(self, "vendor_id", vendor_id)
        object.__setattr__(self, "identity", checked_identity)
        object.__setattr__(self, "config", checked_config)
        object.__setattr__(self, "bindings", checked_bindings)
        object.__setattr__(self, "exclusions", checked_exclusions)
        object.__setattr__(self, "captured_at", stamp)
        object.__setattr__(self, "profile_id", profile)
        object.__setattr__(self, "total_chunks", total)
        object.__setattr__(self, "sha256", canonical_sha256(self.canonical_object()))

    def canonical_object(self) -> dict[str, Any]:
        identity = self.identity
        return {
            "canonical": CANONICAL_ENCODING,
            "kind": "retrieval_snapshot",
            "tenant_id": str(self.tenant_id),
            "vendor_id": str(self.vendor_id),
            "captured_at": canonical_timestamp(self.captured_at),
            "config_sha256": self.config.config_sha256,
            "profile": {
                "provider_id": identity.provider_id,
                "model_id": identity.model_id,
                "algorithm_version": identity.algorithm_version,
                "dims": identity.dims,
                "normalization": identity.normalization,
                "fingerprint": identity.fingerprint,
                "profile_id": str(self.profile_id),
            },
            "bindings": [binding.canonical_object() for binding in self.bindings],
            "total_chunks": self.total_chunks,
            "exclusions": {
                "count": self.exclusions.count,
                "revision_ids": [str(value) for value in self.exclusions.revision_ids],
                "truncated": self.exclusions.truncated,
            },
        }

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.canonical_object())

    @property
    def profile_label(self) -> str:
        return _label(self.identity)

    def __repr__(self) -> str:
        return (
            f"RetrievalSnapshot(tenant_id={self.tenant_id}, vendor_id={self.vendor_id}, "
            f"revisions={len(self.bindings)}, total_chunks={self.total_chunks}, "
            f"excluded={self.exclusions.count})"
        )

    __str__ = __repr__


def revalidate_snapshot(snapshot: object) -> RetrievalSnapshot:
    """Reconstruct a snapshot through its constructor and require it to equal the original, so
    a value altered after construction is rejected."""
    _check(type(snapshot) is RetrievalSnapshot, InvalidSnapshotError)
    assert isinstance(snapshot, RetrievalSnapshot)
    rebuilt = RetrievalSnapshot(
        snapshot.tenant_id,
        snapshot.vendor_id,
        snapshot.identity,
        snapshot.config,
        snapshot.bindings,
        snapshot.exclusions,
        snapshot.captured_at,
    )
    _check(rebuilt == snapshot, InvalidSnapshotError)
    return rebuilt


def _label(identity: EmbeddingIdentity) -> str:
    return LEXICAL_HASH_LABEL if allows_zero_vectors(identity) else PROVIDER_EMBEDDINGS_LABEL


# --- query vectors -------------------------------------------------------------------------------


def query_vectors(
    batch: EmbeddingBatch, *, identity: EmbeddingIdentity, query_count: int
) -> tuple[StoredVector, ...]:
    """Validate a query batch against ``identity`` and convert each vector to the canonical
    float32 storage contract (existing tolerance and zero policy; no renormalization).

    Pure; raises the fixed ``InvalidEmbeddingError``. A zero result marks its position as
    vector-skipped (see ``vector_skipped``).
    """
    checked_identity = require_storable_identity(identity)
    if not _is_int(query_count, 1, MAX_QUERIES):
        raise InvalidEmbeddingError()
    if type(batch) is not EmbeddingBatch:
        raise InvalidEmbeddingError()
    checked = validate_result(
        batch, identity=checked_identity, input_type="query", count=query_count
    )
    zero_ok = allows_zero_vectors(checked_identity)
    return tuple(canonical_vector(vector, allows_zero=zero_ok) for vector in checked.vectors)


def vector_skipped(vectors: tuple[StoredVector, ...]) -> tuple[int, ...]:
    """The ascending query positions whose canonical query vector is zero."""
    return tuple(position for position, vector in enumerate(vectors) if vector.is_zero)


# --- channel lists and fusion --------------------------------------------------------------------


def _is_channel(value: object) -> bool:
    return type(value) is str and value in _CHANNELS


def _in_order(channel: str, left: tuple[UUID, float], right: tuple[UUID, float]) -> bool:
    if left[1] == right[1]:
        return left[0] < right[0]
    return left[1] > right[1] if channel == LEXICAL else left[1] < right[1]


@dataclass(frozen=True, init=False, repr=False)
class ChannelList:
    """One channel's ranked candidates for one query position: 0 to 20 ``(chunk_id, score)``
    pairs with distinct chunks and finite ``float`` scores. Lexical scores are positive and
    non-increasing; vector scores (cosine distances) are non-decreasing; equal scores are in
    ascending chunk-ID order. An entry's rank is its one-based position."""

    query_position: int
    channel: Channel
    entries: tuple[tuple[UUID, float], ...]

    def __init__(
        self,
        query_position: int,
        channel: Channel,
        entries: tuple[tuple[UUID, float], ...],
        **unknown: object,
    ) -> None:
        error = InvalidRetrievalRequestError
        _check(not unknown, error)
        _check(_is_int(query_position, 0, MAX_QUERIES - 1) and _is_channel(channel), error)
        _check(type(entries) is tuple and len(entries) <= CHANNEL_LIMIT, error)
        for entry in entries:
            _check(type(entry) is tuple and len(entry) == 2, error)
            _check(_is_uuid(entry[0]) and _is_finite_float(entry[1]), error)
            _check(channel != LEXICAL or entry[1] > 0, error)
        _check(len({entry[0] for entry in entries}) == len(entries), error)
        _check(all(_in_order(channel, a, b) for a, b in pairwise(entries)), error)
        object.__setattr__(self, "query_position", query_position)
        object.__setattr__(self, "channel", channel)
        object.__setattr__(self, "entries", entries)

    def __repr__(self) -> str:
        return (
            f"ChannelList(query_position={self.query_position}, channel={self.channel!r}, "
            f"entries={len(self.entries)})"
        )

    __str__ = __repr__


def _revalidate_list(value: object) -> ChannelList:
    _check(type(value) is ChannelList, InvalidRetrievalRequestError)
    assert isinstance(value, ChannelList)
    return ChannelList(value.query_position, value.channel, value.entries)


@dataclass(frozen=True, init=False, repr=False)
class ChannelHit:
    """A chunk's rank and score in one (query position, channel) list."""

    query_position: int
    channel: Channel
    rank: int
    score: float

    def __init__(
        self, query_position: int, channel: Channel, rank: int, score: float, **unknown: object
    ) -> None:
        error = InvalidRetrievalRequestError
        _check(not unknown, error)
        _check(_is_int(query_position, 0, MAX_QUERIES - 1) and _is_channel(channel), error)
        _check(_is_int(rank, 1, CHANNEL_LIMIT) and _is_finite_float(score), error)
        _check(channel != LEXICAL or score > 0, error)
        object.__setattr__(self, "query_position", query_position)
        object.__setattr__(self, "channel", channel)
        object.__setattr__(self, "rank", rank)
        object.__setattr__(self, "score", score)

    @property
    def key(self) -> tuple[int, str]:
        return (self.query_position, self.channel)

    def __repr__(self) -> str:
        return (
            f"ChannelHit(query_position={self.query_position}, channel={self.channel!r}, "
            f"rank={self.rank})"
        )

    __str__ = __repr__


def _revalidate_hit(value: object) -> ChannelHit:
    _check(type(value) is ChannelHit, InvalidRetrievalRequestError)
    assert isinstance(value, ChannelHit)
    return ChannelHit(value.query_position, value.channel, value.rank, value.score)


def _checked_hits(hits: object, fused_score: object) -> tuple[ChannelHit, ...]:
    error = InvalidRetrievalRequestError
    _check(type(hits) is tuple and 1 <= len(hits) <= MAX_QUERIES * 2, error)
    assert isinstance(hits, tuple)
    checked = tuple(_rebuild(partial(_revalidate_hit, hit), error) for hit in hits)
    # ascending (query position, channel) with lexical before vector, at most one per key
    _check(_strictly_ascending(tuple(hit.key for hit in checked)), error)
    _check(type(fused_score) is Fraction, error)
    _check(fused_score == sum(_contribution(hit.rank) for hit in checked), error)
    return checked


def _contribution(rank: int) -> Fraction:
    return Fraction(1, RRF_CONSTANT + rank)


@dataclass(frozen=True, init=False, repr=False)
class FusedChunk:
    """One fused candidate: its final rank, exact RRF score and per-list hits."""

    chunk_id: UUID
    fused_rank: int
    fused_score: Fraction
    hits: tuple[ChannelHit, ...]

    def __init__(
        self,
        chunk_id: UUID,
        fused_rank: int,
        fused_score: Fraction,
        hits: tuple[ChannelHit, ...],
        **unknown: object,
    ) -> None:
        error = InvalidRetrievalRequestError
        _check(not unknown and _is_uuid(chunk_id) and _is_int(fused_rank, 1, MAX_K), error)
        checked = _checked_hits(hits, fused_score)
        object.__setattr__(self, "chunk_id", chunk_id)
        object.__setattr__(self, "fused_rank", fused_rank)
        object.__setattr__(self, "fused_score", fused_score)
        object.__setattr__(self, "hits", checked)

    def __repr__(self) -> str:
        return f"FusedChunk(chunk_id={self.chunk_id}, fused_rank={self.fused_rank})"

    __str__ = __repr__


def _checked_positions(values: object, query_count: int) -> tuple[int, ...]:
    error = InvalidRetrievalRequestError
    _check(type(values) is tuple, error)
    assert isinstance(values, tuple)
    _check(all(_is_int(value, 0, query_count - 1) for value in values), error)
    _check(_strictly_ascending(values), error)
    return values


def fuse(
    lists: tuple[ChannelList, ...],
    *,
    query_count: int,
    vector_skipped: tuple[int, ...],
    k: int,
) -> tuple[FusedChunk, ...]:
    """Reciprocal-rank fusion of channel lists (pure and deterministic).

    Every list is revalidated. At most one list per (query position, channel); no list for a
    position at or above ``query_count``; no vector list for a vector-skipped position. A
    chunk's score is the exact sum of ``1 / (60 + rank)`` over the lists containing it. The
    result is ordered by score descending, then chunk UUID ascending, truncated to ``k``, each
    chunk once. No candidates gives an empty tuple.
    """
    error = InvalidRetrievalRequestError
    _check(_is_int(query_count, 1, MAX_QUERIES) and _is_int(k, 1, MAX_K), error)
    skipped = set(_checked_positions(vector_skipped, query_count))
    _check(type(lists) is tuple, error)
    checked = tuple(_rebuild(partial(_revalidate_list, value), error) for value in lists)
    keys = [(item.query_position, item.channel) for item in checked]
    _check(len(set(keys)) == len(keys), error)
    for item in checked:
        _check(item.query_position < query_count, error)
        _check(not (item.channel == VECTOR and item.query_position in skipped), error)

    scores: dict[UUID, Fraction] = {}
    hits: dict[UUID, list[ChannelHit]] = {}
    for item in sorted(checked, key=lambda value: (value.query_position, value.channel)):
        for rank, (chunk, score) in enumerate(item.entries, start=1):
            scores[chunk] = scores.get(chunk, Fraction(0)) + _contribution(rank)
            hits.setdefault(chunk, []).append(
                ChannelHit(item.query_position, item.channel, rank, score)
            )
    ranked = sorted(scores, key=lambda chunk: (-scores[chunk], chunk))[:k]
    return tuple(
        FusedChunk(chunk, rank, scores[chunk], tuple(hits[chunk]))
        for rank, chunk in enumerate(ranked, start=1)
    )


# --- evidence and results ------------------------------------------------------------------------


@dataclass(frozen=True, init=False, repr=False)
class SourceSpan:
    """One-based inclusive lines and a half-open character range in the revision text."""

    line_start: int
    line_end: int
    char_start: int
    char_end: int

    def __init__(
        self, line_start: int, line_end: int, char_start: int, char_end: int, **unknown: object
    ) -> None:
        error = InvalidRetrievalRequestError
        _check(not unknown, error)
        _check(_is_int(line_start, 1) and _is_int(line_end, 1) and line_start <= line_end, error)
        _check(_is_int(char_start, 0) and _is_int(char_end, 0) and char_start < char_end, error)
        object.__setattr__(self, "line_start", line_start)
        object.__setattr__(self, "line_end", line_end)
        object.__setattr__(self, "char_start", char_start)
        object.__setattr__(self, "char_end", char_end)

    @property
    def length(self) -> int:
        return self.char_end - self.char_start

    def __repr__(self) -> str:
        return (
            f"SourceSpan(lines={self.line_start}-{self.line_end}, "
            f"chars={self.char_start}-{self.char_end})"
        )

    __str__ = __repr__


def _revalidate_span(value: object) -> SourceSpan:
    _check(type(value) is SourceSpan, InvalidRetrievalRequestError)
    assert isinstance(value, SourceSpan)
    return SourceSpan(value.line_start, value.line_end, value.char_start, value.char_end)


def _text_digest(text: str) -> str | None:
    try:
        return content_sha256(text)
    except UnicodeEncodeError:
        return None


@dataclass(frozen=True, init=False, repr=False)
class ChunkEvidence:
    """A retrieved chunk's exact text, verified digest, spans and provenance.

    ``body`` is the body span. A table continuation chunk with a repeated header also has a
    ``header`` span that ends before the body; ``text`` is the header slice immediately followed
    by the body slice. The two are **not contiguous** in the source: ``header_text`` and
    ``body_text`` are split at the header length, and a citation must not quote across them.
    """

    chunk_id: UUID
    text: str
    content_sha256: str
    ordinal: int
    section_path: tuple[str, ...]
    is_table: bool
    body: SourceSpan
    header: SourceSpan | None
    document_key: str
    title: str
    revision_no: int
    version_label: str | None
    effective_date: date | None
    source_type: SourceType
    authenticity: Authenticity

    def __init__(
        self,
        chunk_id: UUID,
        text: str,
        content_sha256: str,
        ordinal: int,
        section_path: tuple[str, ...],
        is_table: bool,
        body: SourceSpan,
        header: SourceSpan | None,
        document_key: str,
        title: str,
        revision_no: int,
        version_label: str | None,
        effective_date: date | None,
        source_type: SourceType,
        authenticity: Authenticity,
        **unknown: object,
    ) -> None:
        error = InvalidRetrievalRequestError
        _check(not unknown and _is_uuid(chunk_id), error)
        _check(type(text) is str and 1 <= len(text) <= MAX_CHUNK_CHARS, error)
        _check(_is_sha256(content_sha256) and _text_digest(text) == content_sha256, error)
        _check(_is_int(ordinal, 0, MAX_CHUNKS_PER_REVISION - 1) and type(is_table) is bool, error)
        _check(type(section_path) is tuple and len(section_path) <= MAX_SECTION_DEPTH, error)
        _check(all(type(part) is str for part in section_path), error)
        checked_body = _rebuild(lambda: _revalidate_span(body), error)
        checked_header = (
            None if header is None else _rebuild(lambda: _revalidate_span(header), error)
        )
        if checked_header is None:
            _check(len(text) == checked_body.length, error)
        else:
            _check(is_table, error)
            _check(checked_header.line_end < checked_body.line_start, error)
            _check(checked_header.char_end <= checked_body.char_start, error)
            _check(len(text) == checked_header.length + checked_body.length, error)
        _check(type(document_key) is str and len(document_key) >= 1, error)
        _check(type(title) is str and len(title) >= 1, error)
        _check(_is_int(revision_no, 1), error)
        _check(version_label is None or type(version_label) is str, error)
        _check(effective_date is None or type(effective_date) is date, error)
        _check(type(source_type) is SourceType and type(authenticity) is Authenticity, error)
        object.__setattr__(self, "chunk_id", chunk_id)
        object.__setattr__(self, "text", text)
        object.__setattr__(self, "content_sha256", content_sha256)
        object.__setattr__(self, "ordinal", ordinal)
        object.__setattr__(self, "section_path", section_path)
        object.__setattr__(self, "is_table", is_table)
        object.__setattr__(self, "body", checked_body)
        object.__setattr__(self, "header", checked_header)
        object.__setattr__(self, "document_key", document_key)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "revision_no", revision_no)
        object.__setattr__(self, "version_label", version_label)
        object.__setattr__(self, "effective_date", effective_date)
        object.__setattr__(self, "source_type", source_type)
        object.__setattr__(self, "authenticity", authenticity)

    @property
    def header_text(self) -> str | None:
        return None if self.header is None else self.text[: self.header.length]

    @property
    def body_text(self) -> str:
        return self.text if self.header is None else self.text[self.header.length :]

    def __repr__(self) -> str:
        return (
            f"ChunkEvidence(chunk_id={self.chunk_id}, ordinal={self.ordinal}, "
            f"chars={len(self.text)}, repeated_header={self.header is not None})"
        )

    __str__ = __repr__


def _revalidate_evidence(value: object) -> ChunkEvidence:
    _check(type(value) is ChunkEvidence, InvalidRetrievalRequestError)
    assert isinstance(value, ChunkEvidence)
    return ChunkEvidence(
        value.chunk_id,
        value.text,
        value.content_sha256,
        value.ordinal,
        value.section_path,
        value.is_table,
        value.body,
        value.header,
        value.document_key,
        value.title,
        value.revision_no,
        value.version_label,
        value.effective_date,
        value.source_type,
        value.authenticity,
    )


@dataclass(frozen=True, init=False, repr=False)
class RetrievedChunk:
    """One result item: the fused rank and exact score, the per-list hits and the evidence."""

    chunk_id: UUID
    revision_id: UUID
    document_id: UUID
    fused_rank: int
    fused_score: Fraction
    hits: tuple[ChannelHit, ...]
    evidence: ChunkEvidence

    def __init__(
        self,
        chunk_id: UUID,
        revision_id: UUID,
        document_id: UUID,
        fused_rank: int,
        fused_score: Fraction,
        hits: tuple[ChannelHit, ...],
        evidence: ChunkEvidence,
        **unknown: object,
    ) -> None:
        error = InvalidRetrievalRequestError
        _check(not unknown and _is_uuid(chunk_id), error)
        _check(_is_uuid(revision_id) and _is_uuid(document_id), error)
        _check(_is_int(fused_rank, 1, MAX_K), error)
        checked_hits = _checked_hits(hits, fused_score)
        checked_evidence = _rebuild(lambda: _revalidate_evidence(evidence), error)
        _check(checked_evidence.chunk_id == chunk_id, error)
        object.__setattr__(self, "chunk_id", chunk_id)
        object.__setattr__(self, "revision_id", revision_id)
        object.__setattr__(self, "document_id", document_id)
        object.__setattr__(self, "fused_rank", fused_rank)
        object.__setattr__(self, "fused_score", fused_score)
        object.__setattr__(self, "hits", checked_hits)
        object.__setattr__(self, "evidence", checked_evidence)

    @property
    def display_score(self) -> float:
        """The fused score as a ``float``, for display only; comparisons use the ``Fraction``."""
        return float(self.fused_score)

    def __repr__(self) -> str:
        return (
            f"RetrievedChunk(chunk_id={self.chunk_id}, revision_id={self.revision_id}, "
            f"fused_rank={self.fused_rank}, hits={len(self.hits)})"
        )

    __str__ = __repr__


def _revalidate_item(value: object) -> RetrievedChunk:
    _check(type(value) is RetrievedChunk, InvalidRetrievalRequestError)
    assert isinstance(value, RetrievedChunk)
    return RetrievedChunk(
        value.chunk_id,
        value.revision_id,
        value.document_id,
        value.fused_rank,
        value.fused_score,
        value.hits,
        value.evidence,
    )


@dataclass(frozen=True, init=False, repr=False)
class RetrievalResult:
    """A bounded, immutable retrieval result for one snapshot.

    ``tenant_id``, ``vendor_id``, ``snapshot_sha256``, ``profile_fingerprint``,
    ``profile_label`` and ``config_sha256`` are derived from ``snapshot``. ``items`` hold at most
    ``k`` distinct chunks with ``fused_rank`` exactly ``1 … len(items)``, in descending fused
    score with ties by ascending chunk ID. Every hit's query position is below ``query_count``,
    no vector hit has a position in ``vector_skipped``, and each item's revision and document
    belong to one snapshot binding.
    """

    snapshot: RetrievalSnapshot
    query_count: int
    k: int
    vector_skipped: tuple[int, ...]
    items: tuple[RetrievedChunk, ...]
    tenant_id: UUID = field(init=False)
    vendor_id: UUID = field(init=False)
    snapshot_sha256: str = field(init=False)
    profile_fingerprint: str = field(init=False)
    profile_label: str = field(init=False)
    config_sha256: str = field(init=False)

    def __init__(
        self,
        snapshot: RetrievalSnapshot,
        query_count: int,
        k: int,
        vector_skipped: tuple[int, ...],
        items: tuple[RetrievedChunk, ...],
        **unknown: object,
    ) -> None:
        error = InvalidRetrievalRequestError
        _check(not unknown, error)
        checked_snapshot = _rebuild(lambda: revalidate_snapshot(snapshot), error)
        _check(_is_int(query_count, 1, MAX_QUERIES) and _is_int(k, 1, MAX_K), error)
        skipped = _checked_positions(vector_skipped, query_count)
        _check(type(items) is tuple and len(items) <= k, error)
        checked_items = tuple(_rebuild(partial(_revalidate_item, item), error) for item in items)
        _check(len({item.chunk_id for item in checked_items}) == len(checked_items), error)
        _check([item.fused_rank for item in checked_items] == list(range(1, len(items) + 1)), error)
        for left, right in pairwise(checked_items):
            _check(
                left.fused_score > right.fused_score
                or (left.fused_score == right.fused_score and left.chunk_id < right.chunk_id),
                error,
            )
        owners = {
            (binding.revision_id, binding.document_id) for binding in checked_snapshot.bindings
        }
        for item in checked_items:
            _check((item.revision_id, item.document_id) in owners, error)
            for hit in item.hits:
                _check(hit.query_position < query_count, error)
                _check(not (hit.channel == VECTOR and hit.query_position in skipped), error)
        object.__setattr__(self, "snapshot", checked_snapshot)
        object.__setattr__(self, "query_count", query_count)
        object.__setattr__(self, "k", k)
        object.__setattr__(self, "vector_skipped", skipped)
        object.__setattr__(self, "items", checked_items)
        object.__setattr__(self, "tenant_id", checked_snapshot.tenant_id)
        object.__setattr__(self, "vendor_id", checked_snapshot.vendor_id)
        object.__setattr__(self, "snapshot_sha256", checked_snapshot.sha256)
        object.__setattr__(self, "profile_fingerprint", checked_snapshot.identity.fingerprint)
        object.__setattr__(self, "profile_label", checked_snapshot.profile_label)
        object.__setattr__(self, "config_sha256", checked_snapshot.config.config_sha256)

    def __repr__(self) -> str:
        return (
            f"RetrievalResult(snapshot_sha256={self.snapshot_sha256}, "
            f"queries={self.query_count}, k={self.k}, items={len(self.items)})"
        )

    __str__ = __repr__
