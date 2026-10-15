"""Bounded multipart upload parsing for ``POST /v1/vendors/{id}/documents`` (M3e, ADR-0011).

The request body is read only by ``read_upload``, through an async iterator of raw chunks (the
route passes ``request.stream()``). It is never parsed by FastAPI, so authentication, the role
check and the vendor lookup all finish before the first body byte is read.

**Caps** (initial engineering defaults, not measured): 2 MiB of file bytes; 2 MiB plus 64 KiB
for the whole body; at most 8 parts; at most 8 KiB of headers per part (and 8,192 bytes per
header line); 1 KiB per text field. Every byte cap is enforced on the streamed count, never on
``Content-Length``, and the file bytes are kept in one bounded in-memory buffer: **no temporary
file is ever created**.

**Parsing** uses ``python-multipart``'s low-level streaming ``MultipartParser`` only. Its
``finalize()`` does not verify that the message ended (in 0.0.32 it is a no-op), so completion is
tracked here: a body is complete only when the parser reported the closing boundary
(``on_end``) and every begun part ended. The parser's own ``logger`` is replaced by a disabled
one, because its warnings can quote submitted bytes.

**Error precedence**, in three phases:

1. before the body (in the route and ``check_request_headers``): 400 for an invalid
   ``Content-Length``, 413 when it exceeds the total cap, 415 for a request ``Content-Type`` that
   is not ``multipart/form-data`` with a valid boundary;
2. while streaming, **the first error in byte order wins** and reading stops at once: 413 for a
   cap, 422 for a parser error, 422 for a structural error found at a part's headers (missing or
   invalid ``Content-Disposition``, an unknown or repeated part, a second file, a filename on a
   text part). A client disconnect (raised by the
   chunk iterator) aborts. Bytes after the error are never examined;
3. after a normally completed stream, in order: 400 for a ``Content-Length`` that differs from
   the received length; 422 for an incomplete body; 422 for a missing required field; 415 for
   the file's media type; 422 for field values; 422 for the content.

**Byte order, not receive boundaries, decides.** Each received chunk is fed to the parser in
bounded slices, and the total cap is applied at the exact byte where it is crossed: the bytes
before that position are parsed first, so an earlier parser or structural error always wins over
a later cap. Per-part counts are kept in the parser callbacks, which the parser calls in byte
order; the parser's header counters persist across writes, so its limits do not depend on how
the body is partitioned. The per-part header cap counts the raw bytes of each part's header
region as they are fed (see ``_Feeder``), never reconstructed names and values.

**Header parameters** (the request and part ``Content-Type`` and the part
``Content-Disposition``) are parsed by ``parse_parameters``, which keeps every parameter,
including extended (``name*``) and repeated ones. ``python_multipart.parse_options_header``
drops extended parameters and keeps only the last of repeated names, so it is not used: a
dropped ``filename*`` or an overwritten ``charset`` could otherwise pass the rules.

Errors carry fixed codes only: never submitted values, unknown part names, filenames or parser
messages.
"""

import logging
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import MultipartParser, MultipartState

from evidenceguard_domain.evidence import SourceType
from evidenceguard_domain.revisions import (
    InvalidRevisionContentError,
    MediaType,
    RevisionContent,
    validate_document_key,
    validate_title,
    validate_version_label,
)

MAX_UPLOAD_BYTES = 2_097_152  # 2 MiB of file content
MAX_REQUEST_BYTES = 2_162_688  # 2 MiB plus 64 KiB for headers and fields
MAX_PARTS = 8
MAX_PART_HEADER_BYTES = 8_192
MAX_HEADER_LINE_BYTES = 8_192
MAX_TEXT_FIELD_BYTES = 1_024
FEED_SLICE_BYTES = 65_536
# A header line needs at least 3 bytes ("a:" and LF), so the raw header-region cap is always
# reached before the parser's header-count limit; the limit is kept only as a backstop.
_PARSER_MAX_HEADER_COUNT = MAX_PART_HEADER_BYTES

FILE_FIELD = "file"
REQUIRED_TEXT_FIELDS = ("document_key", "title", "source_type")
OPTIONAL_TEXT_FIELDS = ("version_label", "effective_date")
TEXT_FIELDS = frozenset(REQUIRED_TEXT_FIELDS + OPTIONAL_TEXT_FIELDS)
KNOWN_FIELDS = TEXT_FIELDS | {FILE_FIELD}

# The two parser messages that report a header cap (python-multipart 0.0.32); every other
# parser error is malformed input.
_HEADER_CAP_MESSAGES = frozenset({"Maximum header size exceeded", "Maximum header count exceeded"})
# Parser states in which bytes are part data or the ignored epilogue (fed in bulk slices).
_BULK_STATES = frozenset({MultipartState.PART_DATA, MultipartState.END})
# Parser states that consume a part's header region (see ``_Feeder``).
_HEADER_STATES = frozenset(
    {
        MultipartState.HEADER_FIELD_START,
        MultipartState.HEADER_FIELD,
        MultipartState.HEADER_VALUE_START,
        MultipartState.HEADER_VALUE,
        MultipartState.HEADER_VALUE_ALMOST_DONE,
        MultipartState.HEADERS_ALMOST_DONE,
    }
)

_BOUNDARY = re.compile(r"[0-9A-Za-z'()+_,\-./:=? ]{0,69}[0-9A-Za-z'()+_,\-./:=?]")
# RFC 9110 header parameter syntax (token, OWS and quoted-string; obs-text allowed in quotes).
_TOKEN = re.compile(rb"[!#$%&'*+.^_`|~0-9A-Za-z-]+")
_OWS = re.compile(rb"[ \t]*")
_QUOTED_STRING = re.compile(
    rb'"((?:[\t\x20\x21\x23-\x5b\x5d-\x7e\x80-\xff]|\\[\t\x20-\x7e\x80-\xff])*)"'
)
_QUOTED_PAIR = re.compile(rb"\\([\t\x20-\x7e\x80-\xff])")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_MEDIA_TYPES = {"text/plain": MediaType.TEXT_PLAIN, "text/markdown": MediaType.TEXT_MARKDOWN}

# A logger that drops everything, for the parser (its warnings can quote submitted bytes).
_SILENT_LOGGER = logging.Logger("evidenceguard.api.multipart.silenced")
_SILENT_LOGGER.disabled = True
_SILENT_LOGGER.propagate = False


# --- errors ------------------------------------------------------------------------------------


class UploadRejected(Exception):
    """The upload is refused. ``errors`` (for 422 only) are ``(loc, type)`` pairs whose
    locations come from a fixed allowlist."""

    def __init__(self, status: int, errors: tuple[tuple[tuple[str, ...], str], ...] = ()) -> None:
        super().__init__("the upload was refused")
        self.status = status
        self.errors = errors


def _unprocessable(loc: tuple[str, ...], kind: str) -> UploadRejected:
    return UploadRejected(422, ((loc, kind),))


def _too_large() -> UploadRejected:
    return UploadRejected(413)


def _unsupported() -> UploadRejected:
    return UploadRejected(415)


# --- results -----------------------------------------------------------------------------------


@dataclass(frozen=True, repr=False)
class ParsedUpload:
    """A fully validated upload. ``repr`` never shows the content or field values."""

    document_key: str
    title: str
    source_type: SourceType
    version_label: str | None
    effective_date: date | None
    content: RevisionContent

    def __repr__(self) -> str:
        return f"ParsedUpload(media_type={self.content.media_type.value!r})"


# --- header parameters ---------------------------------------------------------------------------


class _HeaderSyntaxError(Exception):
    """A header value does not match the parameter grammar (callers map it to a fixed error)."""


def parse_parameters(raw: bytes, *, media_type: bool) -> tuple[bytes, list[tuple[bytes, bytes]]]:
    """Strictly parse ``value *( OWS ";" OWS name "=" ( token / quoted-string ) ) OWS``.

    ``value`` is a ``type/subtype`` when ``media_type`` is set, otherwise a token; it and every
    parameter name are lowercased. Unlike ``python_multipart.parse_options_header``, nothing is
    dropped or merged: extended names (``filename*``) and repeated names are returned as they
    appear, in order, so callers can reject them. Anything else raises ``_HeaderSyntaxError``.
    """
    position = _OWS.match(raw).end()  # type: ignore[union-attr]
    match = _TOKEN.match(raw, position)
    if match is None:
        raise _HeaderSyntaxError
    value, position = match.group(), match.end()
    if media_type:
        subtype = _TOKEN.match(raw, position + 1) if raw[position : position + 1] == b"/" else None
        if subtype is None:
            raise _HeaderSyntaxError
        value, position = value + b"/" + subtype.group(), subtype.end()
    parameters: list[tuple[bytes, bytes]] = []
    while True:
        position = _OWS.match(raw, position).end()  # type: ignore[union-attr]
        if position == len(raw):
            return value.lower(), parameters
        if raw[position : position + 1] != b";":
            raise _HeaderSyntaxError
        position = _OWS.match(raw, position + 1).end()  # type: ignore[union-attr]
        name = _TOKEN.match(raw, position)
        if name is None or raw[name.end() : name.end() + 1] != b"=":
            raise _HeaderSyntaxError
        position = name.end() + 1
        quoted = _QUOTED_STRING.match(raw, position)
        if quoted is not None:
            parameter, position = _QUOTED_PAIR.sub(rb"\1", quoted.group(1)), quoted.end()
        else:
            token = _TOKEN.match(raw, position)
            if token is None:
                raise _HeaderSyntaxError
            parameter, position = token.group(), token.end()
        parameters.append((name.group().lower(), parameter))


# --- request headers (phase 1) -----------------------------------------------------------------


def check_request_headers(headers: list[tuple[bytes, bytes]]) -> tuple[bytes, int | None]:
    """Validate the request's framing headers before any body byte is read.

    Returns the multipart boundary and the declared ``Content-Length`` (or ``None``). Raises
    ``UploadRejected`` with 400, 413 or 415.
    """
    lengths = [value for name, value in headers if name.lower() == b"content-length"]
    declared: int | None = None
    if lengths:
        if len(lengths) != 1 or not lengths[0].isdigit() or len(lengths[0]) > 12:
            raise UploadRejected(400)
        declared = int(lengths[0])
        if declared > MAX_REQUEST_BYTES:
            raise _too_large()
    types = [value for name, value in headers if name.lower() == b"content-type"]
    if len(types) != 1:
        raise _unsupported()
    try:
        media, params = parse_parameters(types[0], media_type=True)
    except _HeaderSyntaxError:  # an unparsable header is an unsupported content type
        raise _unsupported() from None
    if media != b"multipart/form-data":
        raise _unsupported()
    if any(name == b"boundary*" for name, _value in params):
        raise _unsupported()
    boundaries = [value for name, value in params if name == b"boundary"]
    if len(boundaries) != 1:  # missing or repeated: never pick one of several
        raise _unsupported()
    boundary = boundaries[0]
    try:
        text = boundary.decode("ascii")
    except UnicodeDecodeError:
        raise _unsupported() from None
    if _BOUNDARY.fullmatch(text) is None:
        raise _unsupported()
    return boundary, declared


# --- streaming (phase 2) -----------------------------------------------------------------------


@dataclass
class _Part:
    headers: list[tuple[str, bytes]] = field(default_factory=list)
    field_buffer: bytearray = field(default_factory=bytearray)
    value_buffer: bytearray = field(default_factory=bytearray)
    name: str | None = None
    content_type: bytes | None = None
    data: bytearray = field(default_factory=bytearray)
    ended: bool = False


class _Collector:
    """Parser callbacks: per-part caps, structure checks and completion tracking."""

    def __init__(self) -> None:
        self.parts = 0
        self.current: _Part | None = None
        self.fields: dict[str, bytearray] = {}
        self.file: bytearray | None = None
        self.file_type: bytes | None = None
        self.complete = False
        self.open_part = False

    # Callbacks (called by the parser in byte order) --------------------------------------------

    def on_part_begin(self) -> None:
        self.parts += 1
        if self.parts > MAX_PARTS:
            raise _too_large()
        self.current = _Part()
        self.open_part = True

    # Header bytes are buffered here, but the header-byte cap is enforced on the raw bytes by
    # ``_Feeder``: the parser does not report every header byte (leading value whitespace, the
    # colon and line endings are consumed silently).

    def on_header_field(self, data: bytes, start: int, end: int) -> None:
        self._part().field_buffer += data[start:end]

    def on_header_value(self, data: bytes, start: int, end: int) -> None:
        self._part().value_buffer += data[start:end]

    def on_header_end(self) -> None:
        part = self._part()
        name = bytes(part.field_buffer).decode("latin-1").lower()
        part.headers.append((name, bytes(part.value_buffer).strip(b" \t")))
        part.field_buffer.clear()
        part.value_buffer.clear()

    def on_headers_finished(self) -> None:
        part = self._part()
        dispositions = [value for name, value in part.headers if name == "content-disposition"]
        if len(dispositions) != 1:
            raise _unprocessable(("body",), "invalid_part_headers")
        try:
            kind, params = parse_parameters(dispositions[0], media_type=False)
        except _HeaderSyntaxError:
            raise _unprocessable(("body",), "invalid_part_headers") from None
        names = [parameter for parameter, _value in params]
        # Repeated parameters are ambiguous, and an extended ``name*`` is not a plain name.
        if kind != b"form-data" or len(set(names)) != len(names) or b"name*" in names:
            raise _unprocessable(("body",), "invalid_part_headers")
        raw_name = dict(params).get(b"name")
        if raw_name is None:
            raise _unprocessable(("body",), "invalid_part_headers")
        try:
            name = raw_name.decode("ascii")
        except UnicodeDecodeError:
            raise _unprocessable(("body",), "extra_forbidden") from None
        if name not in KNOWN_FIELDS:
            raise _unprocessable(("body",), "extra_forbidden")  # never echo the unknown name
        if name in self.fields or (name == FILE_FIELD and self.file is not None):
            raise _unprocessable(("body",), "duplicate_part")
        has_filename = b"filename" in names or b"filename*" in names
        if name != FILE_FIELD and has_filename:
            raise _unprocessable(("body", name), "filename_not_allowed")
        part.name = name
        if name == FILE_FIELD:
            types = [value for header, value in part.headers if header == "content-type"]
            part.content_type = types[0] if len(types) == 1 else None
            self.file = part.data
            self.file_type = part.content_type
        else:
            self.fields[name] = part.data

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        part = self._part()
        part.data += data[start:end]
        limit = MAX_UPLOAD_BYTES if part.name == FILE_FIELD else MAX_TEXT_FIELD_BYTES
        if len(part.data) > limit:
            raise _too_large()

    def on_part_end(self) -> None:
        self._part().ended = True
        self.open_part = False
        self.current = None

    def on_end(self) -> None:
        self.complete = True

    # Helpers -------------------------------------------------------------------------------------

    def _part(self) -> _Part:
        if self.current is None:  # the parser never calls a part callback outside a part
            raise _unprocessable(("body",), "malformed")
        return self.current

    def callbacks(self) -> dict[str, Any]:
        return {
            "on_part_begin": self.on_part_begin,
            "on_header_field": self.on_header_field,
            "on_header_value": self.on_header_value,
            "on_header_end": self.on_header_end,
            "on_headers_finished": self.on_headers_finished,
            "on_part_data": self.on_part_data,
            "on_part_end": self.on_part_end,
            "on_end": self.on_end,
        }


class _Feeder:
    """Feeds the parser so that its detection order is the body's byte order.

    ``python-multipart`` 0.0.32 checks a header-name span against the line-size limit *before*
    validating its characters, and the span runs to the next colon or to the end of the write.
    A large write could therefore report a later size crossing (413) ahead of an earlier invalid
    character (422). So everything outside part data (boundaries, part headers, the closing
    boundary) is fed **one byte at a time**, and part data is fed in bounded slices that stop
    just before each possible delimiter (``CRLF--boundary``). A possible partial delimiter at
    the end of a received chunk is held back until the next chunk, so the slices do not depend
    on how the body was received. Per-byte feeding is bounded by the header caps (measured at
    about 2 microseconds per byte locally: tens of milliseconds per request at most).

    **The per-part header cap counts raw bytes.** A part's *header region* is every byte the
    parser consumes in a header state (``_HEADER_STATES``): from the first byte after the
    boundary line's line ending, through the line ending of the empty line that ends the
    headers, inclusive. That is every header name, colon, whitespace, value and line ending as
    received. Because header regions are fed one byte at a time, the parser's state before each
    byte says whether that byte is in a region, and the byte that would make the region exceed
    ``MAX_PART_HEADER_BYTES`` is refused (413) before the parser sees it. Earlier bytes have
    already been parsed, so an earlier malformed byte still wins (422). The parser's callbacks
    are not used for this count, because it consumes some header bytes (leading value
    whitespace, the colon, line endings) without reporting them.
    """

    def __init__(self, parser: MultipartParser, boundary: bytes) -> None:
        self._parser = parser
        self._delimiter = b"\r\n--" + boundary
        self._carry = b""
        self._bytewise = 0  # bytes still to be fed one at a time (a delimiter and its CRLF)
        self._in_header_region = False
        self._header_bytes = 0  # raw bytes of the current part's header region so far

    def feed(self, data: bytes, *, final: bool = False) -> None:
        buffer = self._carry + data
        self._carry = b""
        position = 0
        while position < len(buffer):
            state = self._parser.state
            in_data = state in _BULK_STATES
            if self._bytewise > 0 or not in_data:
                self._count_header_byte(state)
                self._write(buffer[position : position + 1])
                position += 1
                self._bytewise = max(0, self._bytewise - 1)
                continue
            found = buffer.find(self._delimiter, position)
            if found == position:
                self._bytewise = len(self._delimiter) + 2
                continue
            if found == -1:
                # Hold back a possible partial delimiter unless the stream ended.
                end = len(buffer) if final else len(buffer) - (len(self._delimiter) - 1)
                if end <= position:
                    break
            else:
                end = found
            for offset in range(position, end, FEED_SLICE_BYTES):
                self._write(buffer[offset : min(offset + FEED_SLICE_BYTES, end)])
            position = end
        self._carry = buffer[position:]

    def _count_header_byte(self, state: MultipartState) -> None:
        """Count one byte about to be fed in ``state``; refuse it if it exceeds the cap."""
        if state not in _HEADER_STATES:
            self._in_header_region = False
            return
        if not self._in_header_region:  # a new part's header region starts with this byte
            self._in_header_region = True
            self._header_bytes = 0
        self._header_bytes += 1
        if self._header_bytes > MAX_PART_HEADER_BYTES:
            raise _too_large()

    def _write(self, data: bytes) -> None:
        try:
            self._parser.write(data)
        except UploadRejected:
            raise
        except MultipartParseError as error:
            if str(error) in _HEADER_CAP_MESSAGES:
                raise _too_large() from None
            raise _unprocessable(("body",), "malformed") from None


async def read_upload(
    chunks: AsyncIterator[bytes], *, boundary: bytes, declared_length: int | None
) -> ParsedUpload:
    """Stream, parse and validate one upload body. See the module docstring for the phases.

    ``chunks`` yields the body as received and ends normally only when the request body
    completed. A client disconnect surfaces from ``chunks`` itself (Starlette raises
    ``ClientDisconnect``) and propagates unchanged; the route aborts without any write.
    """
    collector = _Collector()
    parser = MultipartParser(
        boundary,
        callbacks=collector.callbacks(),  # type: ignore[arg-type]
        max_header_size=MAX_HEADER_LINE_BYTES,
        max_header_count=_PARSER_MAX_HEADER_COUNT,
    )
    parser.logger = _SILENT_LOGGER
    feeder = _Feeder(parser, boundary)
    received = 0
    async for chunk in chunks:
        if not chunk:
            continue
        room = MAX_REQUEST_BYTES - received
        if len(chunk) > room:
            # An earlier error in the bytes before the cap position wins over the cap.
            feeder.feed(chunk[:room], final=True)
            raise _too_large()
        received += len(chunk)
        feeder.feed(chunk)
    feeder.feed(b"", final=True)

    # Phase 3: a normally completed stream.
    if declared_length is not None and declared_length != received:
        raise UploadRejected(400)
    if not collector.complete or collector.open_part:
        raise _unprocessable(("body",), "incomplete")
    return _validate(collector)


# --- validation (phase 3) ------------------------------------------------------------------------


def _validate(collector: _Collector) -> ParsedUpload:
    for name in (FILE_FIELD, *REQUIRED_TEXT_FIELDS):
        if (name == FILE_FIELD and collector.file is None) or (
            name != FILE_FIELD and name not in collector.fields
        ):
            raise _unprocessable(("body", name), "missing")
    media = _file_media_type(collector.file_type)
    values: dict[str, str] = {}
    for name, raw in collector.fields.items():
        try:
            values[name] = bytes(raw).decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            raise _unprocessable(("body", name), "value_error") from None
    document_key = _checked("document_key", values["document_key"], validate_document_key)
    title = _checked("title", values["title"], validate_title)
    try:
        source_type = SourceType(values["source_type"])
    except ValueError:
        raise _unprocessable(("body", "source_type"), "value_error") from None
    version_label = (
        _checked("version_label", values["version_label"], validate_version_label)
        if "version_label" in values
        else None
    )
    effective_date = _date(values["effective_date"]) if "effective_date" in values else None
    assert collector.file is not None
    try:
        content = RevisionContent.from_bytes(bytes(collector.file), media)
    except InvalidRevisionContentError:
        raise _unprocessable(("body", FILE_FIELD), "invalid_content") from None
    return ParsedUpload(
        document_key=document_key,
        title=title,
        source_type=source_type,
        version_label=version_label,
        effective_date=effective_date,
        content=content,
    )


def _file_media_type(raw: bytes | None) -> MediaType:
    if raw is None:
        raise _unsupported()
    try:
        media, params = parse_parameters(raw, media_type=True)
    except _HeaderSyntaxError:
        raise _unsupported() from None
    resolved = _MEDIA_TYPES.get(media.decode("ascii"))  # tokens are ASCII
    if resolved is None:
        raise _unsupported()
    # At most one parameter, and only a plain charset=utf-8. An extended (charset*), repeated
    # or any other parameter is refused rather than dropped or overwritten.
    if len(params) > 1 or any(n != b"charset" or v.lower() != b"utf-8" for n, v in params):
        raise _unsupported()
    return resolved


def _checked(name: str, value: str, rule: Any) -> Any:
    try:
        return rule(value)
    except ValueError:
        raise _unprocessable(("body", name), "value_error") from None


def _date(value: str) -> date:
    if _DATE.fullmatch(value) is None:
        raise _unprocessable(("body", "effective_date"), "value_error")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise _unprocessable(("body", "effective_date"), "value_error") from None
