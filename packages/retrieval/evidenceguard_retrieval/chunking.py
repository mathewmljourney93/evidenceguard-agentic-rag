"""The deterministic chunker ``text-md-v1`` for ``text/plain`` and ``text/markdown`` (M3d).

Pure code: no I/O, no clock, no locale or environment. The output is a function of
``(content_text, media_type, CHUNKER_VERSION)`` only. The rules are the accepted M3d
specification in ``docs/plan.md`` (section A) and ADR-0010; in brief:

- **Lines** end at LF; a CR immediately before that LF belongs to the terminator. Offsets are
  code-point indices into the stored text. A leading BOM keeps offset 0 but belongs to no chunk,
  and line 1's content starts after it.
- **Whitespace** is only U+0020 and U+0009. A line is blank when its content is empty or only
  whitespace. Every other character (a lone CR, NBSP, U+2028, ...) is non-whitespace.
- **Markdown blocks**, by priority: fence opening, ATX heading, table start, paragraph line. A
  paragraph stops before any of the others even without a blank line. Consecutive headings
  separated only by blank lines form one *heading run*, which starts a section.
- **Chunks** pack whole blocks of one section greedily up to ``TARGET_CHARS``. Tables are never
  packed with prose; long tables split by rows, repeating a header of at most
  ``MAX_HEADER_REPEAT_CHARS``. Oversized blocks split at line boundaries, and oversized lines at
  the last whitespace in ``[TARGET_CHARS/2, TARGET_CHARS]`` of the remaining text, or hard at
  ``TARGET_CHARS``.
- **Only permitted omissions:** a split may omit only LF and CRLF terminators, a leading BOM and
  spaces and tabs. Every other character appears in exactly one chunk's body span, in order.

Errors carry fixed messages and never contain document content. ``Segment`` and ``Chunk`` never
show text or section paths in ``repr``.

This module imports ``evidenceguard_domain`` only.
"""

import re
from dataclasses import dataclass
from enum import Enum
from uuid import UUID

from evidenceguard_domain.chunks import (
    MAX_CHUNK_CHARS,
    MAX_CHUNKS_PER_REVISION,
    Chunk,
    chunk_id,
)
from evidenceguard_domain.revisions import MediaType, RevisionContent

CHUNKER_VERSION = "text-md-v1"
TARGET_CHARS = 2500
MAX_HEADER_REPEAT_CHARS = 1000
SECTION_TEXT_MAX_CHARS = 200

WHITESPACE = " \t"
BOM = "\ufeff"

_ATX_HEADING = re.compile(r" {0,3}(#{1,6})(?:[ \t](.*))?")
_FENCE_OPENING = re.compile(r" {0,3}(`{3,}|~{3,})(.*)")
_DELIMITER_ROW = re.compile(r" {0,3}\|?[ \t]*:?-+:?[ \t]*(\|[ \t]*:?-+:?[ \t]*)*\|?[ \t]*")
_CLOSING_SEQUENCE = re.compile(r"[ \t]+#+\Z")


# --- errors (fixed messages) -------------------------------------------------------------


class EmptyDocumentError(Exception):
    """Every line is blank after a leading BOM: there is nothing to chunk."""

    def __init__(self) -> None:
        super().__init__("the document has no non-whitespace content")


class ChunkLimitExceededError(Exception):
    """The document would produce more than ``MAX_CHUNKS_PER_REVISION`` chunks."""

    def __init__(self) -> None:
        super().__init__("the document produces more chunks than allowed")


# --- values ------------------------------------------------------------------------------------


@dataclass(frozen=True, repr=False)
class Segment:
    """A chunk before it is bound to a tenant and revision. Spans as in ``Chunk``."""

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

    def __repr__(self) -> str:
        return (
            f"Segment(chars=[{self.char_start}, {self.char_end}), "
            f"lines={self.line_start}-{self.line_end}, is_table={self.is_table}, "
            f"repeated_header={self.header_char_start is not None})"
        )

    __str__ = __repr__


@dataclass(frozen=True)
class _Line:
    number: int
    start: int  # first code point of the content (after a BOM on line 1)
    end: int  # end of the content, before the terminator
    next: int  # after the terminator

    @property
    def length(self) -> int:
        return self.end - self.start


class _Kind(Enum):
    PARAGRAPH = "paragraph"
    FENCE = "fence"
    HEADING_RUN = "heading_run"
    TABLE = "table"


@dataclass(frozen=True)
class _Block:
    kind: _Kind
    first: int  # line indices, inclusive; neither is ever a blank line
    last: int
    path: tuple[str, ...]


# --- the chunker -----------------------------------------------------------------------------


def chunk_revision(
    content: RevisionContent, *, tenant_id: UUID, revision_id: UUID
) -> tuple[Chunk, ...]:
    """Chunk a revision's verified content into ``Chunk`` values with deterministic IDs.

    Raises ``EmptyDocumentError`` or ``ChunkLimitExceededError`` (fixed messages).
    """
    if not isinstance(content, RevisionContent):
        raise TypeError("content must be a RevisionContent")
    return tuple(
        Chunk(
            id=chunk_id(tenant_id, revision_id, CHUNKER_VERSION, ordinal),
            tenant_id=tenant_id,
            revision_id=revision_id,
            chunker_version=CHUNKER_VERSION,
            ordinal=ordinal,
            text=piece.text,
            section_path=piece.section_path,
            is_table=piece.is_table,
            line_start=piece.line_start,
            line_end=piece.line_end,
            char_start=piece.char_start,
            char_end=piece.char_end,
            header_line_start=piece.header_line_start,
            header_line_end=piece.header_line_end,
            header_char_start=piece.header_char_start,
            header_char_end=piece.header_char_end,
        )
        for ordinal, piece in enumerate(segment(content.text, content.media_type))
    )


def segment(
    text: str, media_type: MediaType, *, target_chars: int = TARGET_CHARS
) -> tuple[Segment, ...]:
    """Split ``text`` into ordered segments.

    ``target_chars`` exists only so the specification's illustrations can lower the target
    (examples 4 and 8); ``text-md-v1`` always uses ``TARGET_CHARS``. The other limits never
    change.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    media = MediaType(media_type)
    if isinstance(target_chars, bool) or not isinstance(target_chars, int):
        raise TypeError("target_chars must be an integer")
    if not 2 <= target_chars <= TARGET_CHARS:
        raise ValueError("target_chars must be between 2 and TARGET_CHARS")
    return _Chunker(text, media, target_chars).run()


class _Chunker:
    def __init__(self, text: str, media_type: MediaType, target: int) -> None:
        self.text = text
        self.media_type = media_type
        self.target = target
        self.lines = _split_lines(text)
        self.out: list[Segment] = []

    # Lines ------------------------------------------------------------------------------------

    def content(self, index: int) -> str:
        line = self.lines[index]
        return self.text[line.start : line.end]

    def blank(self, index: int) -> bool:
        return not self.content(index).strip(WHITESPACE)

    # Driver -------------------------------------------------------------------------------------

    def run(self) -> tuple[Segment, ...]:
        if all(self.blank(index) for index in range(len(self.lines))):
            raise EmptyDocumentError()
        if self.media_type is MediaType.TEXT_MARKDOWN:
            blocks = self.markdown_blocks()
        else:
            blocks = self.plain_blocks()
        self.chunk(blocks)
        return tuple(self.out)

    # Blocks -------------------------------------------------------------------------------------

    def plain_blocks(self) -> list[_Block]:
        blocks: list[_Block] = []
        index = 0
        count = len(self.lines)
        while index < count:
            if self.blank(index):
                index += 1
                continue
            last = index
            while last + 1 < count and not self.blank(last + 1):
                last += 1
            blocks.append(_Block(_Kind.PARAGRAPH, index, last, ()))
            index = last + 1
        return blocks

    def classify(self, index: int) -> _Kind:
        """The kind of a non-blank line outside a fence; the first match wins."""
        content = self.content(index)
        if _fence_opening(content) is not None:
            return _Kind.FENCE
        if _ATX_HEADING.fullmatch(content) is not None:
            return _Kind.HEADING_RUN
        if (
            "|" in content
            and index + 1 < len(self.lines)
            and _is_delimiter_row(self.content(index + 1))
        ):
            return _Kind.TABLE
        return _Kind.PARAGRAPH

    def markdown_blocks(self) -> list[_Block]:
        blocks: list[_Block] = []
        stack: list[tuple[int, str]] = []  # (level, heading text) of the current section path
        path: tuple[str, ...] = ()
        index = 0
        count = len(self.lines)
        while index < count:
            if self.blank(index):
                index += 1
                continue
            kind = self.classify(index)
            if kind is _Kind.FENCE:
                last = self.fence_end(index)
            elif kind is _Kind.HEADING_RUN:
                headings = [index]
                scan = index + 1
                while scan < count:
                    if self.blank(scan):
                        scan += 1
                    elif self.classify(scan) is _Kind.HEADING_RUN:
                        headings.append(scan)
                        scan += 1
                    else:
                        break
                for heading in headings:
                    level, heading_text = _heading(self.content(heading))
                    stack = [entry for entry in stack if entry[0] < level]
                    stack.append((level, heading_text))
                path = tuple(entry[1] for entry in stack)
                last = headings[-1]
            elif kind is _Kind.TABLE:
                last = index + 1  # the delimiter row
                while (
                    last + 1 < count
                    and not self.blank(last + 1)
                    and "|" in self.content(last + 1)
                    and self.classify(last + 1) not in (_Kind.FENCE, _Kind.HEADING_RUN)
                ):
                    last += 1
            else:
                last = index
                while (
                    last + 1 < count
                    and not self.blank(last + 1)
                    and self.classify(last + 1) is _Kind.PARAGRAPH
                ):
                    last += 1
            blocks.append(_Block(kind, index, last, path))
            index = last + 1
        return blocks

    def fence_end(self, index: int) -> int:
        """The closing line's index, or, for an unclosed fence, the last non-blank line of the
        document (a block never ends with a blank line)."""
        opening = _fence_opening(self.content(index))
        assert opening is not None
        character, length = opening
        closer = re.compile(r" {0,3}" + re.escape(character) + "{" + str(length) + r",}[ \t]*")
        for scan in range(index + 1, len(self.lines)):
            if closer.fullmatch(self.content(scan)) is not None:
                return scan
        last = len(self.lines) - 1
        while self.blank(last):
            last -= 1
        return last

    # Chunks -------------------------------------------------------------------------------------

    def chunk(self, blocks: list[_Block]) -> None:
        group: list[_Block] = []
        for block in blocks:
            if block.kind is _Kind.HEADING_RUN:  # a new section
                self.emit_group(group)
                group = []
            if block.kind is _Kind.TABLE:
                self.emit_group(group)
                group = []
                self.table(block)
                continue
            if self.span(block.first, block.last) > self.target:
                self.emit_group(group)
                group = []
                self.split(block.first, block.last, block.path, is_table=False)
                continue
            if group and self.span(group[0].first, block.last) <= self.target:
                group.append(block)
            else:
                self.emit_group(group)
                group = [block]
        self.emit_group(group)

    def span(self, first: int, last: int) -> int:
        return self.lines[last].end - self.lines[first].start

    def emit_group(self, group: list[_Block]) -> None:
        if group:
            self.contiguous(group[0].first, group[-1].last, group[0].path, is_table=False)

    def contiguous(self, first: int, last: int, path: tuple[str, ...], *, is_table: bool) -> None:
        start, end = self.lines[first].start, self.lines[last].end
        self.emit(
            Segment(
                text=self.text[start:end],
                section_path=path,
                is_table=is_table,
                line_start=self.lines[first].number,
                line_end=self.lines[last].number,
                char_start=start,
                char_end=end,
            )
        )

    def split(self, first: int, last: int, path: tuple[str, ...], *, is_table: bool) -> None:
        """An oversized block: greedy runs of whole lines, never starting or ending with a blank
        line; a line longer than the target is cut into pieces of its own."""
        run: tuple[int, int] | None = None
        for index in range(first, last + 1):
            if self.blank(index):
                continue
            if self.lines[index].length > self.target:
                if run is not None:
                    self.contiguous(run[0], run[1], path, is_table=is_table)
                    run = None
                self.pieces(index, path, is_table=is_table)
            elif run is None:
                run = (index, index)
            elif self.span(run[0], index) <= self.target:
                run = (run[0], index)
            else:
                self.contiguous(run[0], run[1], path, is_table=is_table)
                run = (index, index)
        if run is not None:
            self.contiguous(run[0], run[1], path, is_table=is_table)

    def pieces(self, index: int, path: tuple[str, ...], *, is_table: bool) -> None:
        """Cut one oversized line. Leading and trailing spaces and tabs are omitted, so the
        remaining text always starts and ends with a non-whitespace character."""
        line = self.lines[index]
        text = self.text
        start, end = line.start, line.end
        while start < end and text[start] in WHITESPACE:
            start += 1
        while end > start and text[end - 1] in WHITESPACE:
            end -= 1
        lowest = (self.target + 1) // 2  # the smallest index i with TARGET/2 <= i
        position = start
        while end - position > self.target:
            found = None
            for candidate in range(position + self.target, position + lowest - 1, -1):
                if text[candidate] in WHITESPACE:
                    found = candidate
                    break
            if found is None:
                self.piece(line, position, position + self.target, path, is_table)
                position += self.target
                continue
            run_start = found
            while text[run_start - 1] in WHITESPACE:  # stops: text[position] is not whitespace
                run_start -= 1
            run_end = found
            while text[run_end] in WHITESPACE:  # stops: text[end - 1] is not whitespace
                run_end += 1
            self.piece(line, position, run_start, path, is_table)
            position = run_end
        self.piece(line, position, end, path, is_table)

    def piece(
        self, line: _Line, start: int, end: int, path: tuple[str, ...], is_table: bool
    ) -> None:
        self.emit(
            Segment(
                text=self.text[start:end],
                section_path=path,
                is_table=is_table,
                line_start=line.number,
                line_end=line.number,
                char_start=start,
                char_end=end,
            )
        )

    def table(self, block: _Block) -> None:
        header, delimiter, last = block.first, block.first + 1, block.last
        lines = self.lines
        if self.span(header, last) <= self.target:
            self.contiguous(header, last, block.path, is_table=True)
            return
        header_start, header_end = lines[header].start, lines[delimiter].next
        header_length = header_end - header_start
        if header_length > self.target:
            self.split(header, last, block.path, is_table=True)
            return

        included = delimiter
        while included + 1 <= last and self.span(header, included + 1) <= self.target:
            included += 1
        self.contiguous(header, included, block.path, is_table=True)

        repeat = header_length <= MAX_HEADER_REPEAT_CHARS
        row = included + 1
        while row <= last:
            length = lines[row].length
            if repeat and header_length + length > self.target:
                if header_length + length <= MAX_CHUNK_CHARS:
                    self.with_header(header, delimiter, row, row, block.path)
                elif length <= self.target:
                    self.contiguous(row, row, block.path, is_table=True)
                else:
                    self.pieces(row, block.path, is_table=True)
                row += 1
                continue
            if not repeat and length > self.target:
                self.pieces(row, block.path, is_table=True)
                row += 1
                continue
            budget = self.target - (header_length if repeat else 0)
            final = row
            while final + 1 <= last and self.span(row, final + 1) <= budget:
                final += 1
            if repeat:
                self.with_header(header, delimiter, row, final, block.path)
            else:
                self.contiguous(row, final, block.path, is_table=True)
            row = final + 1

    def with_header(
        self, header: int, delimiter: int, first: int, last: int, path: tuple[str, ...]
    ) -> None:
        lines = self.lines
        header_start, header_end = lines[header].start, lines[delimiter].next
        start, end = lines[first].start, lines[last].end
        self.emit(
            Segment(
                text=self.text[header_start:header_end] + self.text[start:end],
                section_path=path,
                is_table=True,
                line_start=lines[first].number,
                line_end=lines[last].number,
                char_start=start,
                char_end=end,
                header_line_start=lines[header].number,
                header_line_end=lines[delimiter].number,
                header_char_start=header_start,
                header_char_end=header_end,
            )
        )

    def emit(self, piece: Segment) -> None:
        if len(self.out) >= MAX_CHUNKS_PER_REVISION:
            raise ChunkLimitExceededError()
        self.out.append(piece)


# --- line-level helpers ----------------------------------------------------------------------


def _split_lines(text: str) -> list[_Line]:
    lines: list[_Line] = []
    position = 0
    length = len(text)
    number = 0
    while position < length:
        number += 1
        start = 1 if position == 0 and text.startswith(BOM) else position
        newline = text.find("\n", position)
        if newline == -1:
            end = following = length
        else:
            end = newline - 1 if newline - 1 >= start and text[newline - 1] == "\r" else newline
            following = newline + 1
        lines.append(_Line(number=number, start=start, end=end, next=following))
        position = following
    return lines


def _fence_opening(content: str) -> tuple[str, int] | None:
    """The fence character and run length, or ``None``. A backtick fence's info string must not
    contain a backtick."""
    match = _FENCE_OPENING.fullmatch(content)
    if match is None:
        return None
    run, info = match.group(1), match.group(2)
    if run[0] == "`" and "`" in info:
        return None
    return run[0], len(run)


def _is_delimiter_row(content: str) -> bool:
    return "|" in content and _DELIMITER_ROW.fullmatch(content) is not None


def _heading(content: str) -> tuple[int, str]:
    """The level and the section-path text of an ATX heading line."""
    match = _ATX_HEADING.fullmatch(content)
    assert match is not None
    level = len(match.group(1))
    heading = (match.group(2) or "").strip(WHITESPACE)
    if heading and set(heading) == {"#"}:
        heading = ""
    else:
        closing = _CLOSING_SEQUENCE.search(heading)
        if closing is not None:
            heading = heading[: closing.start()]
    return level, heading[:SECTION_TEXT_MAX_CHARS].rstrip(WHITESPACE)


__all__ = [
    "CHUNKER_VERSION",
    "MAX_HEADER_REPEAT_CHARS",
    "TARGET_CHARS",
    "ChunkLimitExceededError",
    "EmptyDocumentError",
    "Segment",
    "chunk_revision",
    "segment",
]
