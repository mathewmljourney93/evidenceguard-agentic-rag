"""Provider protocol and offline lexical-hash baseline, with no I/O (ADR-0013)."""

import hashlib
import math
import re
from dataclasses import dataclass
from itertools import pairwise
from typing import Protocol

from evidenceguard_domain.embeddings import (
    LEXICAL_HASH_LABEL,
    EmbeddingBatch,
    EmbeddingIdentity,
    EmbeddingUsage,
    InputType,
    InvalidEmbeddingError,
    validate_identity,
    validate_request,
    validate_result,
)

HASH_IDENTITY = EmbeddingIdentity("offline", "fake-hash-v1", "ascii-word-sha256-v1", 1024, "l2")
_WORDS = re.compile(r"[A-Za-z0-9]+", re.ASCII)


class EmbeddingProvider(Protocol):
    @property
    def identity(self) -> EmbeddingIdentity: ...

    def embed(self, texts: tuple[str, ...], input_type: InputType) -> EmbeddingBatch: ...


def embed_validated(
    provider: EmbeddingProvider, texts: tuple[str, ...], input_type: InputType
) -> EmbeddingBatch:
    """Call a provider and distrust both its output and its exceptions.

    Capture the expected identity before the call; a changed provider property
    cannot retroactively change the request's identity. No raw exception escapes.
    """
    validate_request(texts, input_type)
    failed = False
    try:
        identity = validate_identity(provider.identity)
        result = provider.embed(texts, input_type)
        checked = validate_result(
            result, identity=identity, input_type=input_type, count=len(texts)
        )
    except Exception:
        failed = True
    if failed:
        raise InvalidEmbeddingError()
    return checked


@dataclass(frozen=True, repr=False)
class HashingEmbedder:
    """lexical-hash baseline — not semantic. No environment, network or random seed."""

    @property
    def identity(self) -> EmbeddingIdentity:
        return HASH_IDENTITY

    @property
    def label(self) -> str:
        return LEXICAL_HASH_LABEL

    def embed(self, texts: tuple[str, ...], input_type: InputType) -> EmbeddingBatch:
        validate_request(texts, input_type)
        vectors = tuple(_hash_text(text) for text in texts)
        return EmbeddingBatch(self.identity, input_type, vectors, EmbeddingUsage(None))

    def __repr__(self) -> str:
        return f"HashingEmbedder(label={self.label!r})"


def _hash_text(text: str) -> tuple[float, ...]:
    tokens = [match.group().lower() for match in _WORDS.finditer(text)]
    features = [f"u:{token}" for token in tokens]
    features.extend(f"b:{left} {right}" for left, right in pairwise(tokens))
    counts = [0] * 1024
    for feature in features:
        digest = hashlib.sha256(feature.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:8], "big") % 1024
        counts[bucket] += 1 if digest[8] % 2 == 0 else -1
    norm = math.sqrt(sum(count * count for count in counts))
    return tuple(count / norm if norm else 0.0 for count in counts)
