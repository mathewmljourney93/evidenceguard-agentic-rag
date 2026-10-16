"""Canonical stored embedding values (M4b, ADR-0014).

Pure values and functions, standard library only. Provider output is first validated against
the M4a contract (``evidenceguard_domain.embeddings``); this module then converts it to the
**storage contract**: what PostgreSQL's ``vector(1024)`` column holds and what every equality,
replay and digest comparison uses.

- **Canonicalization:** each coordinate is rounded to IEEE-754 float32 with
  ``struct.pack('>f', x)``, and ``-0.0`` becomes ``0.0``. The rounded vector is then validated
  again: finite, zero exactly when the provider vector was zero, zero only when the profile
  permits it, otherwise an L2 norm (in float64 over the float32 values) within the absolute
  ``NORM_TOLERANCE`` of 1. Nothing is renormalized and the tolerance is not widened. Provider
  validity therefore does not guarantee storage validity: a norm of ``0.999999001`` passes M4a
  but rounds to ``0.9999989867210388`` and is rejected here.
- **Wire bytes:** ``struct.pack(WIRE_FORMAT, 1024, 0, *coordinates)``, identical to pgvector's
  binary send format (int16 dimensions, int16 zero, big-endian float4). ``sha256`` is the
  SHA-256 hex digest of those bytes; the database CHECK recomputes it from the stored vector.
- **Text literal:** ``[c0,c1,…]`` with Python ``repr`` of each float32-exact double. pgvector
  parses it with ``strtof``, which returns exactly that float32.
- **IDs:** ``uuid5(PROFILE_ID_NAMESPACE, f"{tenant_id}:{fingerprint}")`` and
  ``uuid5(INDEX_ID_NAMESPACE, f"{tenant_id}:{revision_id}:{chunker_version}:{profile_id}")``,
  with canonical lowercase hyphenated UUIDs. Both namespaces are fixed literals.
- **Vector manifest:** SHA-256 of ASCII lines
  ``f"{ordinal}:{chunk_id}:{content_sha256}:{vector_sha256}\\n"`` in ascending ordinal order.

Equality concerns canonical stored float32 values, never the provider's float64 values; no
float64 round trip is promised. Every failure raises M4a's fixed ``InvalidEmbeddingError``,
outside any exception handler, and representations never show coordinates.
"""

import hashlib
import math
import re
import struct
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from uuid import UUID, uuid5

from evidenceguard_domain.chunks import validate_chunker_version
from evidenceguard_domain.embeddings import (
    EmbeddingBatch,
    EmbeddingIdentity,
    InvalidEmbeddingError,
    Vector,
    validate_identity,
    validate_result,
)

STORED_DIMS = 1024
NORM_TOLERANCE = 1e-6
MAX_WRITE_BATCH = 32
WIRE_FORMAT = f">HH{STORED_DIMS}f"
WIRE_SIZE = struct.calcsize(WIRE_FORMAT)
OFFLINE_PROVIDER_ID = "offline"

PROFILE_ID_NAMESPACE = UUID("b6e99a93-0055-5a05-970d-26eb33f56723")
"""``uuid5(NAMESPACE_URL, "https://evidenceguard.invalid/namespaces/embedding-profile-id/v1")``,
fixed."""

INDEX_ID_NAMESPACE = UUID("5adfc50a-fb67-5caa-a6ca-81c69eaf4285")
"""``uuid5(NAMESPACE_URL, "https://evidenceguard.invalid/namespaces/embedding-index-id/v1")``,
fixed."""

_SHA256 = re.compile(r"[0-9a-f]{64}", re.ASCII)
_FLOAT32 = struct.Struct(">f")


def _require(condition: bool) -> None:
    if not condition:
        raise InvalidEmbeddingError()


def _is_sha256(value: object) -> bool:
    return type(value) is str and _SHA256.fullmatch(value) is not None


# --- identity-derived values --------------------------------------------------------------------


def allows_zero_vectors(identity: EmbeddingIdentity) -> bool:
    """Only the offline provider may store zero vectors (M4a's zero-vector policy)."""
    return validate_identity(identity).provider_id == OFFLINE_PROVIDER_ID


def require_storable_identity(identity: EmbeddingIdentity) -> EmbeddingIdentity:
    """Revalidate ``identity`` and require the fixed 1024-dimensional ``l2`` column."""
    checked = validate_identity(identity)
    _require(checked.dims == STORED_DIMS and checked.normalization == "l2")
    return checked


def profile_id(tenant_id: UUID, fingerprint: str) -> UUID:
    _require(type(tenant_id) is UUID and _is_sha256(fingerprint))
    return uuid5(PROFILE_ID_NAMESPACE, f"{tenant_id}:{fingerprint}")


def index_id(tenant_id: UUID, revision_id: UUID, chunker_version: str, profile: UUID) -> UUID:
    _require(type(tenant_id) is UUID and type(revision_id) is UUID and type(profile) is UUID)
    validate_chunker_version(chunker_version)
    return uuid5(INDEX_ID_NAMESPACE, f"{tenant_id}:{revision_id}:{chunker_version}:{profile}")


# --- stored vectors -------------------------------------------------------------------------


def _round(coordinate: int | float) -> float:
    """``coordinate`` rounded to float32, or ``nan`` when it cannot be packed."""
    try:
        value: float = _FLOAT32.unpack(_FLOAT32.pack(coordinate))[0]
    except (OverflowError, struct.error, TypeError):
        return math.nan
    return 0.0 if value == 0.0 else value  # -0.0 → 0.0


@dataclass(frozen=True, init=False, repr=False)
class StoredVector:
    """A canonical float32 vector exactly as stored. Construct with ``canonical_vector`` (from
    provider values) or ``StoredVector(coordinates, allows_zero=…)`` (from canonical values);
    both validate the storage contract."""

    coordinates: tuple[float, ...]
    is_zero: bool
    sha256: str

    def __init__(self, coordinates: tuple[float, ...], *, allows_zero: bool) -> None:
        _require(type(allows_zero) is bool)
        _require(type(coordinates) is tuple and len(coordinates) == STORED_DIMS)
        for value in coordinates:
            _require(type(value) is float and math.isfinite(value))
            _require(_round(value) == value)  # exactly representable as float32
            _require(value != 0.0 or math.copysign(1.0, value) > 0)  # no -0.0
        is_zero = all(value == 0.0 for value in coordinates)
        if is_zero:
            _require(allows_zero)
        else:
            _require(
                math.isclose(math.hypot(*coordinates), 1.0, rel_tol=0.0, abs_tol=NORM_TOLERANCE)
            )
        object.__setattr__(self, "coordinates", coordinates)
        object.__setattr__(self, "is_zero", is_zero)
        object.__setattr__(self, "sha256", hashlib.sha256(_wire(coordinates)).hexdigest())

    def wire_bytes(self) -> bytes:
        return _wire(self.coordinates)

    def literal(self) -> str:
        """The pgvector text literal: ``repr`` of each float32-exact double, no spaces."""
        return "[" + ",".join(repr(value) for value in self.coordinates) + "]"

    def __repr__(self) -> str:
        return "StoredVector()"

    __str__ = __repr__


def _wire(coordinates: tuple[float, ...]) -> bytes:
    return struct.pack(WIRE_FORMAT, STORED_DIMS, 0, *coordinates)


def canonical_vector(vector: Vector, *, allows_zero: bool) -> StoredVector:
    """Round a provider vector to the storage contract, or raise ``InvalidEmbeddingError``.

    The provider vector must already satisfy M4a. A nonzero vector that rounds to all zeros, a
    coordinate that overflows float32 and a rounded norm outside the tolerance are rejected.
    """
    _require(type(vector) is tuple and len(vector) == STORED_DIMS)
    _require(all(type(value) in (int, float) for value in vector))
    rounded = tuple(_round(value) for value in vector)
    source_zero = all(value == 0 for value in vector)
    _require(all(math.isfinite(value) for value in rounded))
    _require(source_zero == all(value == 0.0 for value in rounded))
    return StoredVector(rounded, allows_zero=allows_zero)


def decode_wire(data: bytes) -> tuple[float, ...]:
    """Decode ``vector_send`` bytes into exact float32 coordinates (the read path)."""
    _require(type(data) is bytes and len(data) == WIRE_SIZE)
    dims, unused, *values = struct.unpack(WIRE_FORMAT, data)
    _require(dims == STORED_DIMS and unused == 0)
    return tuple(values)


# --- rows -----------------------------------------------------------------------------------


@dataclass(frozen=True, init=False, repr=False)
class StoredEmbedding:
    """One row to store: the chunk it embeds, that chunk's text digest and its canonical
    vector."""

    chunk_id: UUID
    content_sha256: str
    vector: StoredVector

    def __init__(self, chunk_id: UUID, content_sha256: str, vector: StoredVector) -> None:
        _require(type(chunk_id) is UUID and _is_sha256(content_sha256))
        _require(type(vector) is StoredVector)
        object.__setattr__(self, "chunk_id", chunk_id)
        object.__setattr__(self, "content_sha256", content_sha256)
        object.__setattr__(self, "vector", vector)

    def __repr__(self) -> str:
        return f"StoredEmbedding(chunk_id={self.chunk_id})"

    __str__ = __repr__


def revalidate_rows(
    rows: Sequence[StoredEmbedding], *, allows_zero: bool
) -> tuple[StoredEmbedding, ...]:
    """Reconstruct a write batch (1 to ``MAX_WRITE_BATCH`` rows, distinct chunks) to reject
    forged or bypassed values before any SQL."""
    _require(isinstance(rows, Sequence) and not isinstance(rows, str | bytes))
    _require(1 <= len(rows) <= MAX_WRITE_BATCH)
    _require(all(type(row) is StoredEmbedding for row in rows))
    checked = tuple(
        StoredEmbedding(
            row.chunk_id,
            row.content_sha256,
            StoredVector(row.vector.coordinates, allows_zero=allows_zero),
        )
        for row in rows
    )
    for row, original in zip(checked, rows, strict=True):
        _require(row.vector.sha256 == original.vector.sha256)
    _require(len({row.chunk_id for row in checked}) == len(checked))
    return checked


def stored_embeddings(
    batch: EmbeddingBatch,
    *,
    identity: EmbeddingIdentity,
    chunks: Sequence[tuple[UUID, str]],
) -> tuple[StoredEmbedding, ...]:
    """Validate a provider batch for ``chunks`` (``(chunk_id, content_sha256)`` in input order)
    and convert **every** vector, or raise ``InvalidEmbeddingError`` and return nothing.

    Order: M4a result validation (document mode, count, identity), the storable 1024/``l2``
    identity, distinct chunks, then canonicalization of the whole batch. A single failing vector
    rejects the batch, so no partial batch can reach a write.
    """
    checked_identity = require_storable_identity(identity)
    _require(type(chunks) in (tuple, list) and 1 <= len(chunks) <= MAX_WRITE_BATCH)
    checked = validate_result(
        batch, identity=checked_identity, input_type="document", count=len(chunks)
    )
    zero_ok = allows_zero_vectors(checked_identity)
    rows = []
    for (chunk, digest), vector in zip(chunks, checked.vectors, strict=True):
        rows.append(StoredEmbedding(chunk, digest, canonical_vector(vector, allows_zero=zero_ok)))
    _require(len({row.chunk_id for row in rows}) == len(rows))
    return tuple(rows)


def vector_manifest_sha256(entries: Iterable[tuple[int, UUID, str, str]]) -> str:
    """The digest of ``(ordinal, chunk_id, content_sha256, vector_sha256)`` entries, which must
    be in strictly ascending ordinal order."""
    digest = hashlib.sha256()
    previous = -1
    for ordinal, chunk, content, vector in entries:
        _require(type(ordinal) is int and ordinal > previous and type(chunk) is UUID)
        _require(_is_sha256(content) and _is_sha256(vector))
        previous = ordinal
        digest.update(f"{ordinal}:{chunk}:{content}:{vector}\n".encode("ascii"))
    return digest.hexdigest()
