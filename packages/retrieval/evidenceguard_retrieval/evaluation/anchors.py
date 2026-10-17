"""Anchor-to-chunk resolution and manifest verification (M4e, ADR-0017).

Pure code: inputs are revision text and chunk span values supplied by the caller (stored rows,
or the offline chunker in tests). Nothing here reads files or a database.

- A quote is located by exact code-point matching, counting non-overlapping matches left to
  right. A part is located only inside its parent's selected range.
- An anchor maps to **every** chunk whose body span contains the matched range (route
  ``body``) and every chunk whose repeated header span contains it (route ``header``). A quote
  crossing a chunk boundary needs ``parts``, which must cover the parent exactly, with only
  spaces, tabs and line terminators between consecutive parts.
- ``verify_manifest`` requires the pinned ``text-md-v1`` chunker and equality of the stored
  manifest, the manifest rebuilt from stored rows and the offline chunker's manifest.
- ``validate_suite`` is the complete pure validation (Prompt 145): ``build_suite``, then every
  defined anchor located and mapped against its selected variant's text chunked offline by the
  pinned chunker. ``revalidate`` re-derives a suite from its own ``source_files`` and requires
  equality, so a caller-supplied ``Suite`` value is never trusted. Stored-manifest verification
  at evaluation time remains separate.

Failures raise ``EvaluationError`` with fixed codes; no text is ever included.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from evidenceguard_domain.chunks import (
    Chunk,
    chunks_manifest_sha256,
    manifest_entry,
    manifest_sha256,
)
from evidenceguard_domain.revisions import MediaType, RevisionContent
from evidenceguard_retrieval.chunking import CHUNKER_VERSION, chunk_revision
from evidenceguard_retrieval.evaluation.corpus import (
    Anchor,
    EvaluationError,
    RevisionRef,
    Suite,
    build_suite,
)

MAX_MAPPING_ENTRIES = 64
# Chunk spans do not depend on the tenant or revision ID (only chunk IDs do), so offline
# validation chunks every text under one fixed placeholder identity.
_OFFLINE_ID = UUID(int=1)
_GAP_CHARACTERS = frozenset(" \t\n")

Route = Literal["body", "header"]


@dataclass(frozen=True)
class ChunkSpan:
    """One chunk's source spans (half-open code-point ranges)."""

    chunk_id: UUID
    body_start: int
    body_end: int
    header_start: int | None = None
    header_end: int | None = None


@dataclass(frozen=True)
class MappingEntry:
    """One route by which an anchor (``part_index`` ``None``) or one of its parts is contained
    in a chunk; ``char_start``/``char_end`` are the matched source range."""

    chunk_id: UUID
    part_index: int | None
    route: Route
    char_start: int
    char_end: int

    def sort_key(self) -> tuple[UUID, int, str]:
        return (self.chunk_id, -1 if self.part_index is None else self.part_index, self.route)


@dataclass(frozen=True)
class StoredChunkRow:
    """The manifest fields of one stored chunk (never its text)."""

    id: UUID
    ordinal: int
    content_sha256: str
    section_path: tuple[str, ...]
    is_table: bool
    line_start: int
    line_end: int
    char_start: int
    char_end: int
    header_line_start: int | None
    header_line_end: int | None
    header_char_start: int | None
    header_char_end: int | None

    def span(self) -> ChunkSpan:
        return ChunkSpan(
            self.id, self.char_start, self.char_end, self.header_char_start, self.header_char_end
        )


def spans_from_chunks(chunks: Sequence[Chunk]) -> tuple[ChunkSpan, ...]:
    """Spans of offline ``chunk_revision`` output (tests and manifest checks)."""
    return tuple(
        ChunkSpan(c.id, c.char_start, c.char_end, c.header_char_start, c.header_char_end)
        for c in chunks
    )


def locate(
    text: str,
    quote: str,
    occurrence: int | None,
    *,
    start: int = 0,
    end: int | None = None,
    part: bool = False,
) -> tuple[int, int]:
    """The ``[s, e)`` range of the selected non-overlapping occurrence of ``quote`` inside
    ``text[start:end]``."""
    stop = len(text) if end is None else end
    prefix = "anchor_part_" if part else "anchor_"
    matches: list[int] = []
    position = start
    while True:
        found = text.find(quote, position, stop)
        if found < 0:
            break
        matches.append(found)
        position = found + len(quote)
    if not matches:
        raise EvaluationError(prefix + "not_found")
    if occurrence is None:
        if len(matches) > 1:
            raise EvaluationError(prefix + "ambiguous")
        index = 0
    else:
        if occurrence > len(matches):
            raise EvaluationError(prefix + "occurrence_out_of_range")
        index = occurrence - 1
    return matches[index], matches[index] + len(quote)


def containing(
    chunks: Sequence[ChunkSpan], start: int, end: int, part_index: int | None = None
) -> list[MappingEntry]:
    """Every body or repeated-header span containing ``[start, end)``."""
    entries: list[MappingEntry] = []
    for chunk in chunks:
        if chunk.body_start <= start and end <= chunk.body_end:
            entries.append(MappingEntry(chunk.chunk_id, part_index, "body", start, end))
        if (
            chunk.header_start is not None
            and chunk.header_end is not None
            and chunk.header_start <= start
            and end <= chunk.header_end
        ):
            entries.append(MappingEntry(chunk.chunk_id, part_index, "header", start, end))
    return entries


def _gap_ok(text: str) -> bool:
    """Only spaces, tabs, LF and CR immediately before LF (the chunker's permitted omissions)."""
    for index, character in enumerate(text):
        if character == "\r":
            if index + 1 >= len(text) or text[index + 1] != "\n":
                return False
        elif character not in _GAP_CHARACTERS:
            return False
    return True


def resolve_anchor(
    anchor: Anchor, text: str, chunks: Sequence[ChunkSpan]
) -> tuple[MappingEntry, ...]:
    """All mapping entries of one anchor, sorted by chunk UUID, part index and route."""
    start, end = locate(text, anchor.quote, anchor.occurrence)
    whole = containing(chunks, start, end)
    if anchor.parts is None:
        if not whole:
            raise EvaluationError("anchor_crosses_chunk_boundary")
        entries = whole
    else:
        if whole:
            raise EvaluationError("anchor_parts_unnecessary")
        entries = []
        previous_end = start
        for index, part in enumerate(anchor.parts):
            part_start, part_end = locate(
                text, part.quote, part.occurrence, start=start, end=end, part=True
            )
            if part_start < previous_end:
                raise EvaluationError("anchor_parts_order")
            if not _gap_ok(text[previous_end:part_start]):
                raise EvaluationError("anchor_parts_gap")
            if index == 0 and part_start != start:
                raise EvaluationError("anchor_parts_gap")
            part_entries = containing(chunks, part_start, part_end, index)
            if not part_entries:
                raise EvaluationError("anchor_part_unmapped")
            entries.extend(part_entries)
            previous_end = part_end
        if previous_end != end:
            raise EvaluationError("anchor_parts_gap")
    if len(entries) > MAX_MAPPING_ENTRIES:
        raise EvaluationError("anchor_mapping_too_large")
    return tuple(sorted(entries, key=MappingEntry.sort_key))


def chunk_set(entries: Sequence[MappingEntry]) -> frozenset[UUID]:
    return frozenset(entry.chunk_id for entry in entries)


def verify_manifest(
    *,
    text: str,
    media_type: MediaType,
    tenant_id: UUID,
    revision_id: UUID,
    chunker_version: str,
    stored_manifest_sha256: str,
    rows: Sequence[StoredChunkRow],
) -> tuple[ChunkSpan, ...]:
    """Check the pinned chunker and the three manifests; return the stored spans."""
    code = "mapping_manifest_mismatch"
    if chunker_version != CHUNKER_VERSION:
        raise EvaluationError(code)
    ordered = sorted(rows, key=lambda row: row.ordinal)
    rebuilt = manifest_sha256(
        manifest_entry(
            id=row.id,
            ordinal=row.ordinal,
            content_sha256=row.content_sha256,
            section_path=row.section_path,
            is_table=row.is_table,
            line_start=row.line_start,
            line_end=row.line_end,
            char_start=row.char_start,
            char_end=row.char_end,
            header_line_start=row.header_line_start,
            header_line_end=row.header_line_end,
            header_char_start=row.header_char_start,
            header_char_end=row.header_char_end,
        )
        for row in ordered
    )
    content = RevisionContent.from_bytes(text.encode("utf-8"), media_type)
    offline = chunks_manifest_sha256(
        chunk_revision(content, tenant_id=tenant_id, revision_id=revision_id)
    )
    if not (stored_manifest_sha256 == rebuilt == offline):
        raise EvaluationError(code)
    return tuple(row.span() for row in ordered)


def offline_spans(suite: Suite) -> dict[RevisionRef, tuple[ChunkSpan, ...]]:
    """Each revision's spans from the pinned chunker over its selected variant's text."""
    spans: dict[RevisionRef, tuple[ChunkSpan, ...]] = {}
    for ref, text in sorted(suite.texts.items()):
        document = suite.corpus.document(ref)
        if document is None:
            raise EvaluationError("unknown_reference")
        content = RevisionContent.from_bytes(text.encode("utf-8"), document.media_type)
        chunks = chunk_revision(content, tenant_id=_OFFLINE_ID, revision_id=_OFFLINE_ID)
        spans[ref] = spans_from_chunks(chunks)
    return spans


def validate_suite(variant: str, files: Mapping[str, bytes]) -> Suite:
    """The complete pure validation, before any database work: ``build_suite``, then every
    defined anchor (gold, forbidden or claim-only alike) located and mapped to offline chunks.
    Raises the anchor's fixed code (``anchor_not_found``, ``anchor_ambiguous``,
    ``anchor_crosses_chunk_boundary``, ...)."""
    suite = build_suite(variant, files)
    spans = offline_spans(suite)
    for ref, anchor in sorted(suite.anchors.items()):
        resolve_anchor(anchor, suite.texts[ref.revision], spans[ref.revision])
    return suite


def revalidate(suite: Suite) -> Suite:
    """Re-derive ``suite`` from its own ``source_files`` through ``validate_suite`` and require
    the result to equal it (``corpus_invalid`` otherwise); returns the re-derived suite."""
    rebuilt = validate_suite(suite.variant, dict(suite.source_files))
    if rebuilt != suite:
        raise EvaluationError("corpus_invalid")
    return rebuilt
