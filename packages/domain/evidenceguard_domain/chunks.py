"""The chunk contract shared by the parser and the chunk store (M3d, ADR-0010).

Pure values and functions, with no I/O. The parser (``evidenceguard_retrieval.chunking``) builds
``Chunk`` values; the store (``evidenceguard_persistence.chunks``) writes and verifies them. Both
use the same deterministic IDs and the same canonical manifest encoding defined here, so the
final completeness check can rebuild the manifest from stored fields alone.

- **Chunk IDs:** ``uuid5(CHUNK_ID_NAMESPACE, f"{tenant_id}:{revision_id}:{chunker_version}:
  {ordinal}")``, with canonical lowercase hyphenated UUIDs and a decimal ordinal. The namespace
  is a fixed literal.
- **Manifest:** a JSON array with one object per chunk, in ascending ordinal order, each with
  exactly ``MANIFEST_KEYS``. It is encoded with sorted keys, no whitespace and ASCII-only
  escapes (``ensure_ascii``), then hashed with SHA-256. UUIDs are lowercase hyphenated strings,
  absent header fields are ``null`` and ``section_path`` is an array of strings.

A ``Chunk`` never shows its text or section path in ``repr``: both are document content.
"""

import hashlib
import json
import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid5

CHUNK_ID_NAMESPACE = UUID("973dffe5-e145-5fd2-833e-6793460ee3be")
"""``uuid5(NAMESPACE_URL, "https://evidenceguard.invalid/namespaces/chunk-id/v1")``, fixed."""

CHUNKER_VERSION_PATTERN = r"^[a-z0-9][a-z0-9.-]{0,31}$"
CHUNKER_VERSION_MAX_LENGTH = 32
MAX_CHUNK_CHARS = 4000
MAX_CHUNKS_PER_REVISION = 4096
MAX_SECTION_DEPTH = 6
MAX_BATCH_CHUNKS = 200
MAX_BATCH_CHARS = 512_000

MANIFEST_KEYS = (
    "char_end",
    "char_start",
    "content_sha256",
    "header_char_end",
    "header_char_start",
    "header_line_end",
    "header_line_start",
    "id",
    "is_table",
    "line_end",
    "line_start",
    "ordinal",
    "section_path",
)

_CHUNKER_VERSION = re.compile(CHUNKER_VERSION_PATTERN)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class InvalidChunkError(ValueError):
    """A chunk value breaks the chunk contract. The message never contains its content."""

    def __init__(self) -> None:
        super().__init__("the chunk does not satisfy the chunk contract")


def validate_chunker_version(value: Any) -> str:
    if not isinstance(value, str) or _CHUNKER_VERSION.fullmatch(value) is None:
        raise ValueError("chunker_version must match the chunker version pattern")
    return value


def chunk_id(tenant_id: UUID, revision_id: UUID, chunker_version: str, ordinal: int) -> UUID:
    """The deterministic chunk ID. The same bytes under two tenants get disjoint IDs."""
    validate_chunker_version(chunker_version)
    if isinstance(ordinal, bool) or not isinstance(ordinal, int) or ordinal < 0:
        raise ValueError("ordinal must be a non-negative integer")
    return uuid5(CHUNK_ID_NAMESPACE, f"{tenant_id}:{revision_id}:{chunker_version}:{ordinal}")


def content_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True, repr=False)
class Chunk:
    """One verbatim chunk of a revision, with its provenance.

    ``char_start``/``char_end`` and ``line_start``/``line_end`` are the **body** span. For a table
    continuation chunk with a repeated header, the four ``header_*`` fields give the header's own
    span, and ``text`` is the header slice followed by the body slice. Otherwise they are
    ``None`` and ``text`` is exactly the body slice.
    """

    id: UUID
    tenant_id: UUID
    revision_id: UUID
    chunker_version: str
    ordinal: int
    text: str
    section_path: tuple[str, ...]
    is_table: bool
    line_start: int
    line_end: int
    char_start: int
    char_end: int
    header_line_start: int | None = None
    header_line_end: int | None = None
    header_char_start: int | None = None
    header_char_end: int | None = None
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "content_sha256", content_sha256(self.text))
        header = (
            self.header_line_start,
            self.header_line_end,
            self.header_char_start,
            self.header_char_end,
        )
        try:
            expected_id = chunk_id(
                self.tenant_id, self.revision_id, self.chunker_version, self.ordinal
            )
        except ValueError:
            raise InvalidChunkError() from None
        valid = (
            self.id == expected_id
            and self.ordinal < MAX_CHUNKS_PER_REVISION
            and 1 <= len(self.text) <= MAX_CHUNK_CHARS
            and isinstance(self.section_path, tuple)
            and len(self.section_path) <= MAX_SECTION_DEPTH
            and all(isinstance(part, str) for part in self.section_path)
            and isinstance(self.is_table, bool)
            and 1 <= self.line_start <= self.line_end
            and 0 <= self.char_start < self.char_end
        )
        if all(value is None for value in header):
            valid = valid and len(self.text) == self.char_end - self.char_start
        else:
            hls, hle, hcs, hce = header
            valid = (
                valid
                and self.is_table
                and None not in header
                and hls is not None
                and hle is not None
                and hcs is not None
                and hce is not None
                and 1 <= hls <= hle < self.line_start
                and 0 <= hcs < hce <= self.char_start
                and len(self.text) == (hce - hcs) + (self.char_end - self.char_start)
            )
        if not valid:
            raise InvalidChunkError()

    @property
    def has_repeated_header(self) -> bool:
        return self.header_char_start is not None

    def manifest_entry(self) -> dict[str, Any]:
        return manifest_entry(
            id=self.id,
            ordinal=self.ordinal,
            content_sha256=self.content_sha256,
            section_path=self.section_path,
            is_table=self.is_table,
            line_start=self.line_start,
            line_end=self.line_end,
            char_start=self.char_start,
            char_end=self.char_end,
            header_line_start=self.header_line_start,
            header_line_end=self.header_line_end,
            header_char_start=self.header_char_start,
            header_char_end=self.header_char_end,
        )

    def __repr__(self) -> str:
        return (
            f"Chunk(id={self.id}, revision_id={self.revision_id}, ordinal={self.ordinal}, "
            f"chars={len(self.text)}, is_table={self.is_table})"
        )

    __str__ = __repr__


def manifest_entry(
    *,
    id: UUID,
    ordinal: int,
    content_sha256: str,
    section_path: Sequence[str],
    is_table: bool,
    line_start: int,
    line_end: int,
    char_start: int,
    char_end: int,
    header_line_start: int | None,
    header_line_end: int | None,
    header_char_start: int | None,
    header_char_end: int | None,
) -> dict[str, Any]:
    """One manifest object, from a ``Chunk`` or from a stored row's fields (never its text)."""
    return {
        "char_end": char_end,
        "char_start": char_start,
        "content_sha256": content_sha256,
        "header_char_end": header_char_end,
        "header_char_start": header_char_start,
        "header_line_end": header_line_end,
        "header_line_start": header_line_start,
        "id": str(id),
        "is_table": is_table,
        "line_end": line_end,
        "line_start": line_start,
        "ordinal": ordinal,
        "section_path": list(section_path),
    }


def manifest_bytes(entries: Iterable[Mapping[str, Any]]) -> bytes:
    """The canonical manifest bytes. Entries must already be in ascending ordinal order."""
    ordered = [dict(entry) for entry in entries]
    if [entry["ordinal"] for entry in ordered] != list(range(len(ordered))):
        raise ValueError("manifest entries must have ordinals 0, 1, ... in order")
    if any(tuple(sorted(entry)) != MANIFEST_KEYS for entry in ordered):
        raise ValueError("manifest entries must have exactly the manifest keys")
    return json.dumps(
        ordered, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def manifest_sha256(entries: Iterable[Mapping[str, Any]]) -> str:
    return hashlib.sha256(manifest_bytes(entries)).hexdigest()


def chunks_manifest_sha256(chunks: Sequence[Chunk]) -> str:
    return manifest_sha256(chunk.manifest_entry() for chunk in chunks)


@dataclass(frozen=True)
class ExpectedChunkSet:
    """What the current attempt computed from its own parse: the final activation check must
    find exactly this set stored."""

    chunker_version: str
    chunk_count: int
    manifest_sha256: str

    def __post_init__(self) -> None:
        validate_chunker_version(self.chunker_version)
        if (
            isinstance(self.chunk_count, bool)
            or not isinstance(self.chunk_count, int)
            or not 1 <= self.chunk_count <= MAX_CHUNKS_PER_REVISION
        ):
            raise ValueError("chunk_count is out of range")
        if not isinstance(self.manifest_sha256, str) or not _SHA256.fullmatch(self.manifest_sha256):
            raise ValueError("manifest_sha256 must be 64 lowercase hexadecimal characters")

    @classmethod
    def of(cls, chunks: Sequence[Chunk]) -> "ExpectedChunkSet":
        """The expectation for a complete parse: one chunker version, ordinals 0..n-1."""
        if not chunks:
            raise ValueError("a chunk set has at least one chunk")
        versions = {chunk.chunker_version for chunk in chunks}
        owners = {(chunk.tenant_id, chunk.revision_id) for chunk in chunks}
        if len(versions) != 1 or len(owners) != 1:
            raise ValueError("a chunk set belongs to one revision and one chunker version")
        return cls(
            chunker_version=chunks[0].chunker_version,
            chunk_count=len(chunks),
            manifest_sha256=chunks_manifest_sha256(chunks),
        )


def batches(chunks: Sequence[Chunk]) -> Iterator[tuple[Chunk, ...]]:
    """Consecutive batches of at most ``MAX_BATCH_CHUNKS`` chunks and ``MAX_BATCH_CHARS`` code
    points of text, whichever limit comes first. A chunk is at most 4,000 code points, so every
    batch holds at least one chunk."""
    batch: list[Chunk] = []
    size = 0
    for chunk in chunks:
        if batch and (len(batch) == MAX_BATCH_CHUNKS or size + len(chunk.text) > MAX_BATCH_CHARS):
            yield tuple(batch)
            batch, size = [], 0
        batch.append(chunk)
        size += len(chunk.text)
    if batch:
        yield tuple(batch)


def within_batch_bounds(batch: Sequence[Chunk]) -> bool:
    return (
        1 <= len(batch) <= MAX_BATCH_CHUNKS
        and sum(len(chunk.text) for chunk in batch) <= MAX_BATCH_CHARS
    )
