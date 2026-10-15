"""Immutable embedding contracts and privacy-safe validation (ADR-0013).

Like the chunk contract, these are frozen dataclasses. ``dataclasses.replace``
revalidates through constructors. Deserialization must also use constructors;
the caller boundary reconstructs even already-instantiated provider values.
"""

import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Literal

InputType = Literal["query", "document"]
Vector = tuple[int | float, ...]
LEXICAL_HASH_LABEL = "lexical-hash baseline — not semantic"
_IDENTIFIER = re.compile(r"[a-z][a-z0-9._-]{0,63}", re.ASCII)


class InvalidEmbeddingError(ValueError):
    """Fixed error boundary; never attach submitted values or provider errors."""

    def __init__(self) -> None:
        super().__init__("invalid_embedding")


def _require(condition: bool) -> None:
    if not condition:
        raise InvalidEmbeddingError()


@dataclass(frozen=True, init=False, repr=False)
class EmbeddingIdentity:
    provider_id: str
    model_id: str
    algorithm_version: str
    dims: int
    normalization: Literal["l2"]

    def __init__(
        self,
        provider_id: str,
        model_id: str,
        algorithm_version: str,
        dims: int,
        normalization: Literal["l2"],
        **unknown: object,
    ) -> None:
        _require(not unknown)
        for value in (provider_id, model_id, algorithm_version):
            _require(type(value) is str and _IDENTIFIER.fullmatch(value) is not None)
        _require(type(dims) is int and 1 <= dims <= 4096)
        _require(type(normalization) is str and normalization == "l2")
        object.__setattr__(self, "provider_id", provider_id)
        object.__setattr__(self, "model_id", model_id)
        object.__setattr__(self, "algorithm_version", algorithm_version)
        object.__setattr__(self, "dims", dims)
        object.__setattr__(self, "normalization", normalization)

    @property
    def fingerprint(self) -> str:
        data = {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "algorithm_version": self.algorithm_version,
            "dims": self.dims,
            "normalization": self.normalization,
        }
        canonical = json.dumps(
            data, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
        ).encode("ascii")
        return hashlib.sha256(canonical).hexdigest()

    def __repr__(self) -> str:
        return "EmbeddingIdentity()"


@dataclass(frozen=True, init=False, repr=False)
class EmbeddingUsage:
    input_tokens: int | None

    def __init__(self, input_tokens: int | None, **unknown: object) -> None:
        _require(not unknown)
        _require(input_tokens is None or (type(input_tokens) is int and input_tokens >= 0))
        object.__setattr__(self, "input_tokens", input_tokens)

    def __repr__(self) -> str:
        return "EmbeddingUsage()"


def validate_identity(identity: EmbeddingIdentity) -> EmbeddingIdentity:
    """Reconstruct to reject forged/bypassed values at trust boundaries."""
    _require(type(identity) is EmbeddingIdentity)
    return EmbeddingIdentity(
        identity.provider_id,
        identity.model_id,
        identity.algorithm_version,
        identity.dims,
        identity.normalization,
    )


def validate_request(texts: tuple[str, ...], input_type: InputType) -> None:
    _require(type(input_type) is str and input_type in ("query", "document"))
    _require(type(texts) is tuple and 1 <= len(texts) <= 32)
    total = 0
    for text in texts:
        _require(type(text) is str)
        _require(1 <= len(text) <= 4000 and "\x00" not in text and not text.isspace())
        invalid_utf8 = False
        try:
            size = len(text.encode("utf-8", errors="strict"))
        except UnicodeEncodeError:
            invalid_utf8 = True
            size = 0
        if invalid_utf8:
            raise InvalidEmbeddingError()
        _require(size <= 16000)
        total += size
    _require(total <= 128000)


def _validate_vectors(identity: EmbeddingIdentity, vectors: tuple[Vector, ...]) -> None:
    _require(type(vectors) is tuple and 1 <= len(vectors) <= 32)
    for vector in vectors:
        _require(type(vector) is tuple and len(vector) == identity.dims)
        for coordinate in vector:
            _require(type(coordinate) in (int, float))
        # hypot avoids squared-coordinate overflow/underflow. Huge Python ints can
        # still overflow conversion; report only the fixed error, outside except.
        invalid_numeric = False
        try:
            norm = math.hypot(*vector)
        except (OverflowError, ValueError, TypeError):
            invalid_numeric = True
            norm = math.inf
        if invalid_numeric:
            raise InvalidEmbeddingError()
        _require(math.isfinite(norm))
        _require(
            (norm == 0 and identity.provider_id == "offline")
            or math.isclose(norm, 1.0, rel_tol=0.0, abs_tol=1e-6)
        )


@dataclass(frozen=True, init=False, repr=False)
class EmbeddingBatch:
    identity: EmbeddingIdentity
    input_type: InputType
    vectors: tuple[Vector, ...]
    usage: EmbeddingUsage

    def __init__(
        self,
        identity: EmbeddingIdentity,
        input_type: InputType,
        vectors: tuple[Vector, ...],
        usage: EmbeddingUsage,
        **unknown: object,
    ) -> None:
        _require(not unknown)
        validate_identity(identity)
        _require(type(input_type) is str and input_type in ("query", "document"))
        _require(type(usage) is EmbeddingUsage)
        EmbeddingUsage(usage.input_tokens)
        _validate_vectors(identity, vectors)
        object.__setattr__(self, "identity", identity)
        object.__setattr__(self, "input_type", input_type)
        object.__setattr__(self, "vectors", vectors)
        object.__setattr__(self, "usage", usage)

    @property
    def label(self) -> str:
        return (
            LEXICAL_HASH_LABEL if self.identity.provider_id == "offline" else "provider embeddings"
        )

    def __repr__(self) -> str:
        return f"EmbeddingBatch(label={self.label!r})"


def validate_result(
    batch: EmbeddingBatch,
    *,
    identity: EmbeddingIdentity,
    input_type: InputType,
    count: int,
) -> EmbeddingBatch:
    """Validate untrusted provider output against the caller's original request."""
    validate_identity(identity)
    _require(type(input_type) is str and input_type in ("query", "document"))
    _require(type(count) is int and 1 <= count <= 32)
    _require(type(batch) is EmbeddingBatch)
    checked = EmbeddingBatch(batch.identity, batch.input_type, batch.vectors, batch.usage)
    _require(checked.identity == identity and checked.input_type == input_type)
    _require(len(checked.vectors) == count)
    return checked
