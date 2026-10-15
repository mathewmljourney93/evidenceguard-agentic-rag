"""The bounded multipart reader (M3e B), without HTTP or a database.

Bodies are fed through controlled async iterators, so the tests decide exactly how the bytes are
partitioned into receive messages and can see how much of a stream was consumed.
"""

import asyncio
import logging
import random
from collections.abc import AsyncIterator, Sequence
from datetime import date
from itertools import pairwise

import pytest

from evidenceguard_api.uploads import (
    MAX_PART_HEADER_BYTES,
    MAX_PARTS,
    MAX_REQUEST_BYTES,
    MAX_TEXT_FIELD_BYTES,
    MAX_UPLOAD_BYTES,
    ParsedUpload,
    UploadRejected,
    _Collector,
    check_request_headers,
    read_upload,
)
from evidenceguard_domain.evidence import SourceType
from evidenceguard_domain.revisions import MediaType

BOUNDARY = b"eg-test-boundary-7d1f"
SUBMITTED_MARKER = "submitted-marker-value"
OK = "ok"


# --- body builders -------------------------------------------------------------------------------


def part(
    name: str,
    value: bytes,
    *,
    filename: str | None = None,
    content_type: str | None = None,
    extra: Sequence[bytes] = (),
) -> bytes:
    disposition = f'Content-Disposition: form-data; name="{name}"'
    if filename is not None:
        disposition += f'; filename="{filename}"'
    lines = [b"--" + BOUNDARY, disposition.encode()]
    if content_type is not None:
        lines.append(f"Content-Type: {content_type}".encode())
    lines.extend(extra)
    return b"\r\n".join(lines) + b"\r\n\r\n" + value + b"\r\n"


def file_part(
    value: bytes = b"# Policy\n\nData is encrypted at rest.\n",
    content_type: str | None = "text/markdown",
) -> bytes:
    return part("file", value, filename="policy.md", content_type=content_type)


def fields(**overrides: bytes) -> bytes:
    values = {"document_key": b"security-policy", "title": b"Security policy"}
    values["source_type"] = b"vendor_statement"
    values.update(overrides)
    return b"".join(part(name, value) for name, value in values.items())


CLOSE = b"--" + BOUNDARY + b"--\r\n"


def valid_body(**overrides: bytes) -> bytes:
    return fields(**overrides) + file_part() + CLOSE


# --- drivers -------------------------------------------------------------------------------------


class Stream:
    """Yields the given chunks and records how many were consumed."""

    def __init__(self, chunks: Sequence[bytes]) -> None:
        self.chunks = list(chunks)
        self.consumed = 0

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self.chunks:
            self.consumed += 1
            yield chunk


def parse(chunks: Sequence[bytes] | bytes, *, declared_length: int | None = None) -> ParsedUpload:
    stream = Stream([chunks] if isinstance(chunks, bytes) else chunks)
    return asyncio.run(
        read_upload(stream.__aiter__(), boundary=BOUNDARY, declared_length=declared_length)
    )


def outcome(chunks: Sequence[bytes] | bytes, *, declared_length: int | None = None) -> int | str:
    try:
        parse(chunks, declared_length=declared_length)
    except UploadRejected as error:
        return error.status
    return OK


def rejection(body: bytes, **kwargs: int | None) -> UploadRejected:
    with pytest.raises(UploadRejected) as caught:
        parse(body, **kwargs)
    return caught.value


def split_at(body: bytes, *offsets: int) -> list[bytes]:
    cuts = [0, *sorted(offsets), len(body)]
    return [body[a:b] for a, b in pairwise(cuts) if b > a]


def every(body: bytes, size: int) -> list[bytes]:
    return [body[i : i + size] for i in range(0, len(body), size)]


def presentations(body: bytes) -> dict[str, list[bytes]]:
    """The same bytes as one message, as many messages, and split inside a part's headers, a
    boundary and the file data."""
    header = body.find(b"Content-Disposition") + 9
    boundary = body.find(b"--" + BOUNDARY, 1) + 5
    data = body.find(b"\r\n\r\n", body.find(b'name="file"')) + 6
    shapes = {
        "one message": [body],
        "4 KiB messages": every(body, 4096),
        "64 KiB + 1 messages": every(body, 65_537),
        "inside headers": split_at(body, header),
        "inside a boundary": split_at(body, boundary),
        "inside file data": split_at(body, max(data, 1)),
        "all three": split_at(body, header, boundary, max(data, 1)),
    }
    if len(body) < 20_000:
        shapes["7-byte messages"] = every(body, 7)
        shapes["1-byte messages"] = every(body, 1)
    return shapes


# --- success -------------------------------------------------------------------------------------


def test_a_valid_upload_parses_every_field() -> None:
    body = (
        fields(version_label=b"v2.1", effective_date=b"2026-09-30")
        + file_part(content_type="text/plain; charset=UTF-8")
        + CLOSE
    )
    parsed = parse(body)

    assert parsed.document_key == "security-policy"
    assert parsed.title == "Security policy"
    assert parsed.source_type is SourceType.VENDOR_STATEMENT
    assert parsed.version_label == "v2.1"
    assert parsed.effective_date == date(2026, 9, 30)
    assert parsed.content.media_type is MediaType.TEXT_PLAIN
    assert SUBMITTED_MARKER not in repr(parsed) and "Security" not in repr(parsed)


@pytest.mark.parametrize("name", ["one message", "7-byte messages", "1-byte messages"])
def test_partitioning_does_not_change_a_valid_upload(name: str) -> None:
    body = valid_body()
    parsed = parse(presentations(body)[name])
    assert parsed.content.text.startswith("# Policy")


def test_bom_crlf_and_whitespace_only_content_are_kept_exactly() -> None:
    for content in (b"\xef\xbb\xbfLine one\r\nLine two\r\n", b"   \n\t\n"):
        parsed = parse(fields() + file_part(content) + CLOSE)
        assert parsed.content.text.encode("utf-8") == content


def test_the_filename_is_ignored_and_an_epilogue_is_discarded() -> None:
    body = fields() + part("file", b"x", filename="../../etc/passwd", content_type="text/plain")
    parsed = parse(body + CLOSE + b"epilogue")
    assert parsed.content.media_type is MediaType.TEXT_PLAIN


def test_caps_allow_their_exact_limits() -> None:
    title = b"T" * 200
    parsed = parse(fields(title=title) + file_part(b"a" * MAX_UPLOAD_BYTES) + CLOSE)
    assert parsed.content.byte_size == MAX_UPLOAD_BYTES
    # A 1 KiB text field is within its byte cap (then fails only value validation).
    assert rejection(valid_body(title=b"T" * MAX_TEXT_FIELD_BYTES)).status == 422


# --- request headers (phase 1) -------------------------------------------------------------------


def _headers(content_type: bytes | None, *lengths: bytes) -> list[tuple[bytes, bytes]]:
    headers = [(b"content-length", value) for value in lengths]
    if content_type is not None:
        headers.append((b"content-type", content_type))
    return headers


def test_request_headers_accept_quoted_and_token_boundaries() -> None:
    for value in (b'multipart/form-data; boundary="a b:c"', b"Multipart/Form-Data; boundary=abc"):
        boundary, declared = check_request_headers(_headers(value, b"12"))
        assert boundary in (b"a b:c", b"abc") and declared == 12
    assert check_request_headers(_headers(b"multipart/form-data; boundary=x"))[1] is None


@pytest.mark.parametrize(
    ("headers", "status"),
    [
        (_headers(b"multipart/form-data; boundary=x", b"-1"), 400),
        (_headers(b"multipart/form-data; boundary=x", b"1e3"), 400),
        (_headers(b"multipart/form-data; boundary=x", b""), 400),
        (_headers(b"multipart/form-data; boundary=x", b"5", b"5"), 400),
        (_headers(b"multipart/form-data; boundary=x", str(MAX_REQUEST_BYTES + 1).encode()), 413),
        (_headers(b"application/json", b"5"), 415),
        (_headers(None, b"5"), 415),
        (_headers(b"multipart/form-data", b"5"), 415),
        (_headers(b"multipart/mixed; boundary=x", b"5"), 415),
        (_headers(b'multipart/form-data; boundary=""', b"5"), 415),
        (_headers(b"multipart/form-data; boundary=" + b"b" * 71, b"5"), 415),
        (_headers(b'multipart/form-data; boundary="ends in space "', b"5"), 415),
        (_headers(b'multipart/form-data; boundary="semi;colon"', b"5"), 415),
        (_headers(b"multipart/form-data; boundary=\xff", b"5"), 415),
    ],
)
def test_request_header_errors(headers: list[tuple[bytes, bytes]], status: int) -> None:
    with pytest.raises(UploadRejected) as caught:
        check_request_headers(headers)
    assert caught.value.status == status


def test_a_70_character_boundary_is_accepted() -> None:
    value = b"multipart/form-data; boundary=" + b"b" * 70
    assert check_request_headers(_headers(value))[0] == b"b" * 70


def test_an_invalid_content_length_wins_over_an_unsupported_type() -> None:
    with pytest.raises(UploadRejected) as caught:
        check_request_headers(_headers(b"text/plain", b"x"))
    assert caught.value.status == 400


# --- caps while streaming ------------------------------------------------------------------------


def test_file_cap() -> None:
    assert rejection(fields() + file_part(b"a" * (MAX_UPLOAD_BYTES + 1)) + CLOSE).status == 413


def test_text_field_cap() -> None:
    assert rejection(valid_body(title=b"T" * (MAX_TEXT_FIELD_BYTES + 1))).status == 413


def test_total_cap_without_a_declared_length() -> None:
    body = valid_body() + b"x" * (2 * MAX_REQUEST_BYTES)  # an oversized epilogue
    stream = Stream(every(body, 65_536))
    with pytest.raises(UploadRejected) as caught:
        asyncio.run(read_upload(stream.__aiter__(), boundary=BOUNDARY, declared_length=None))
    assert caught.value.status == 413
    assert stream.consumed < len(stream.chunks)  # reading stopped at the cap


def test_a_small_declared_length_never_allows_an_unbounded_read() -> None:
    body = valid_body() + b"x" * MAX_REQUEST_BYTES
    assert outcome(every(body, 65_536), declared_length=10) == 413


def test_a_single_header_line_over_its_cap() -> None:
    long_header = b"X-Padding: " + b"p" * MAX_PART_HEADER_BYTES
    body = part("title", b"T", extra=[long_header]) + CLOSE
    assert {outcome(chunks) for chunks in presentations(body).values()} == {413}


def test_aggregate_part_headers_over_their_cap() -> None:
    headers = [b"X-Padding-%d: %s" % (i, b"p" * 200) for i in range(50)]
    body = part("title", b"T", extra=headers) + CLOSE
    assert {outcome(chunks) for chunks in presentations(body).values()} == {413}


def test_part_count_cap() -> None:
    collector = _Collector()
    for _ in range(MAX_PARTS):
        collector.on_part_begin()
        collector.on_part_end()
    with pytest.raises(UploadRejected) as caught:
        collector.on_part_begin()
    assert caught.value.status == 413


# --- malformed and incomplete bodies -------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(b"", id="empty"),
        pytest.param(valid_body()[: -len(CLOSE)], id="no closing boundary"),
        pytest.param(valid_body()[:-4], id="closing boundary without dashes"),
        pytest.param(valid_body()[:40], id="truncated part headers"),
        pytest.param(fields() + file_part()[:-8], id="truncated file data"),
    ],
)
def test_incomplete_bodies_are_never_accepted(body: bytes) -> None:
    for chunks in presentations(body).values():
        with pytest.raises(UploadRejected) as caught:
            parse(chunks)
        assert caught.value.status == 422
        assert caught.value.errors == ((("body",), "incomplete"),)


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(b"not multipart at all", id="garbage"),
        pytest.param(b"preamble\r\n" + valid_body(), id="preamble"),
        pytest.param(valid_body().replace(b"\r\n", b"\n"), id="bare LF"),
        pytest.param(b"--" + BOUNDARY + b"xx\r\n" + valid_body(), id="bad boundary line"),
        pytest.param(b"--" + BOUNDARY + b"\r\nNoColon\r\n\r\nx\r\n" + CLOSE, id="header no colon"),
    ],
)
def test_malformed_bodies(body: bytes) -> None:
    for chunks in presentations(body).values():
        with pytest.raises(UploadRejected) as caught:
            parse(chunks)
        assert caught.value.status == 422
        assert caught.value.errors == ((("body",), "malformed"),)


# --- structural errors ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "errors"),
    [
        (
            b"--" + BOUNDARY + b"\r\nContent-Type: text/plain\r\n\r\nx\r\n" + CLOSE,
            ((("body",), "invalid_part_headers"),),
        ),
        (
            b"--" + BOUNDARY + b"\r\nContent-Disposition: form-data\r\n\r\nx\r\n" + CLOSE,
            ((("body",), "invalid_part_headers"),),
        ),
        (
            b"--"
            + BOUNDARY
            + b'\r\nContent-Disposition: attachment; name="title"\r\n\r\nx\r\n'
            + CLOSE,
            ((("body",), "invalid_part_headers"),),
        ),
        (
            fields() + part("tenant_id", b"x") + file_part() + CLOSE,
            ((("body",), "extra_forbidden"),),
        ),
        (part(SUBMITTED_MARKER, b"x") + CLOSE, ((("body",), "extra_forbidden"),)),
        (fields() + part("title", b"Again") + CLOSE, ((("body",), "duplicate_part"),)),
        (fields() + file_part() + file_part() + CLOSE, ((("body",), "duplicate_part"),)),
        (
            part("title", b"T", filename="t.txt") + CLOSE,
            ((("body", "title"), "filename_not_allowed"),),
        ),
    ],
)
def test_structural_errors(body: bytes, errors: tuple[tuple[tuple[str, ...], str], ...]) -> None:
    for chunks in presentations(body).values():
        with pytest.raises(UploadRejected) as caught:
            parse(chunks)
        assert (caught.value.status, caught.value.errors) == (422, errors)


def test_case_insensitive_disposition_and_token_name() -> None:
    body = (
        b"--"
        + BOUNDARY
        + b"\r\ncontent-disposition: FORM-DATA; name=title\r\n\r\nT\r\n"
        + part("document_key", b"k")
        + part("source_type", b"contract")
        + file_part()
        + CLOSE
    )
    assert parse(body).title == "T"


# --- deferred checks after a completed stream (phase 3) ------------------------------------------


def test_declared_length_must_match_a_completed_stream() -> None:
    body = valid_body()
    assert outcome(body, declared_length=len(body)) == OK
    assert outcome(body, declared_length=len(body) - 1) == 400
    assert outcome(body, declared_length=len(body) + 1) == 400


def test_missing_required_fields() -> None:
    assert rejection(fields() + CLOSE).errors == ((("body", "file"), "missing"),)
    body = part("title", b"T") + part("source_type", b"contract") + file_part() + CLOSE
    assert rejection(body).errors == ((("body", "document_key"), "missing"),)


@pytest.mark.parametrize(
    "content_type",
    [None, "text/html", "text/plain; charset=latin-1", "text/plain; format=flowed", "image/png"],
)
def test_unsupported_file_media_types(content_type: str | None) -> None:
    body = fields() + part("file", b"x", filename="f", content_type=content_type) + CLOSE
    assert rejection(body).status == 415


@pytest.mark.parametrize(
    ("overrides", "loc"),
    [
        ({"document_key": b"Not A Key"}, ("body", "document_key")),
        ({"title": b"   "}, ("body", "title")),
        ({"title": b"\xff\xfe"}, ("body", "title")),
        ({"source_type": b"press_release"}, ("body", "source_type")),
        ({"version_label": b""}, ("body", "version_label")),
        ({"effective_date": b"2026-02-30"}, ("body", "effective_date")),
        ({"effective_date": b"20261001"}, ("body", "effective_date")),
        ({"effective_date": b"2026-W40-1"}, ("body", "effective_date")),
    ],
)
def test_invalid_field_values(overrides: dict[str, bytes], loc: tuple[str, ...]) -> None:
    error = rejection(valid_body(**overrides))
    assert (error.status, error.errors) == (422, ((loc, "value_error"),))


@pytest.mark.parametrize("content", [b"", b"a\x00b", b"\xff\xfe bad utf-8"])
def test_invalid_content(content: bytes) -> None:
    error = rejection(fields() + file_part(content) + CLOSE)
    assert (error.status, error.errors) == (422, ((("body", "file"), "invalid_content"),))


def test_phase_three_order() -> None:
    incomplete = valid_body()[: -len(CLOSE)]
    # A length mismatch wins over an incomplete body.
    assert outcome(incomplete, declared_length=len(incomplete) + 5) == 400
    # A missing field wins over the file media type.
    no_title = part("document_key", b"k") + part("source_type", b"contract")
    bad_media = part("file", b"x", filename="f", content_type="text/html")
    assert rejection(no_title + bad_media + CLOSE).errors == ((("body", "title"), "missing"),)
    # The media type wins over field values, which win over the content.
    assert rejection(fields(title=b" ") + bad_media + CLOSE).status == 415
    error = rejection(fields(title=b" ") + file_part(b"") + CLOSE)
    assert error.errors == ((("body", "title"), "value_error"),)


# --- mixed faults under every partition (M3e B) --------------------------------------------------

OVERSIZED_TAIL = b"t" * (MAX_REQUEST_BYTES + 1)
# A part header line without a colon: malformed to the parser. (In mid-body, a boundary followed
# by other bytes is not malformed: the parser treats it as data of the preceding part.)
MALFORMED_PART = b"--" + BOUNDARY + b"\r\nNo colon in this header\r\n"


def _mixed_faults() -> dict[str, tuple[bytes, int | None, int]]:
    """name -> (body, declared length, expected status)."""
    repeated_then_excess = fields() + part("title", b"Again") + part("extra", b"x") * 12 + CLOSE
    malformed_then_tail = fields() + MALFORMED_PART + OVERSIZED_TAIL
    repeated_then_tail = fields() + part("title", b"Again") + OVERSIZED_TAIL
    no_close = fields() + file_part()
    complete = valid_body()
    oversized_then_malformed = (
        fields() + file_part(b"a" * (MAX_UPLOAD_BYTES + 10)) + MALFORMED_PART + CLOSE
    )
    return {
        "repeated field then excess parts": (repeated_then_excess, None, 422),
        "malformed then oversized tail": (malformed_then_tail, None, 422),
        "repeated field then oversized tail": (repeated_then_tail, None, 422),
        "no closing boundary": (no_close, None, 422),
        "declared length too short": (complete, len(complete) - 3, 400),
        "declared length too long": (complete, len(complete) + 3, 400),
        "oversized file then malformed part": (oversized_then_malformed, None, 413),
    }


@pytest.mark.parametrize("name", list(_mixed_faults()))
def test_mixed_faults_are_partition_invariant(name: str) -> None:
    body, declared, expected = _mixed_faults()[name]
    results = {
        shape: outcome(chunks, declared_length=declared)
        for shape, chunks in presentations(body).items()
    }
    assert set(results.values()) == {expected}, results


def test_reading_stops_at_the_first_error_and_the_tail_is_never_read() -> None:
    head = fields() + MALFORMED_PART
    stream = Stream([head, *every(OVERSIZED_TAIL, 65_536)])
    with pytest.raises(UploadRejected) as caught:
        asyncio.run(read_upload(stream.__aiter__(), boundary=BOUNDARY, declared_length=None))
    assert caught.value.status == 422
    assert stream.consumed == 1


# --- privacy -------------------------------------------------------------------------------------


def test_errors_and_parser_logs_never_carry_submitted_values(
    caplog: pytest.LogCaptureFixture,
) -> None:
    marker = SUBMITTED_MARKER.encode()
    bodies = [
        part(SUBMITTED_MARKER, marker) + CLOSE,
        fields(title=marker + b"\xff") + file_part() + CLOSE,
        fields() + part("file", marker, filename=SUBMITTED_MARKER, content_type="x/" + "y") + CLOSE,
        marker + b"\r\n--" + BOUNDARY + b"\r\n" + marker,
        b"--" + BOUNDARY + b"\r\n" + marker + b"\r\n\r\n",
        fields() + b"--" + BOUNDARY + marker + b"\r\n" + CLOSE,
    ]
    with caplog.at_level(logging.DEBUG):
        for body in bodies:
            for chunks in (every(body, 1), [body]):
                with pytest.raises(UploadRejected) as caught:
                    parse(chunks)
                assert SUBMITTED_MARKER not in repr(caught.value)
                assert SUBMITTED_MARKER not in str(caught.value.errors)
                assert caught.value.__cause__ is None
    for record in caplog.records:
        assert SUBMITTED_MARKER not in record.getMessage()
    assert not [r for r in caplog.records if r.name.startswith("python_multipart")]


def test_header_name_errors_follow_byte_order_in_large_writes() -> None:
    """python-multipart 0.0.32 checks a header-name span's size before its characters, so a
    single large write once reported an earlier invalid character as a later size crossing."""
    start = b"--" + BOUNDARY + b"\r\n"
    invalid_first = start + b"Bad Name" + b"n" * (2 * MAX_PART_HEADER_BYTES) + b": v\r\n\r\n"
    crossing_first = start + b"N" * (MAX_PART_HEADER_BYTES + 10) + b" bad: v\r\n\r\n"
    for body, expected in ((invalid_first, 422), (crossing_first, 413)):
        assert {outcome(chunks) for chunks in presentations(body).values()} == {expected}


@pytest.mark.parametrize("seed", range(5))
def test_random_partitions_match_one_message(seed: int) -> None:
    rng = random.Random(seed)
    for name, (body, declared, expected) in _mixed_faults().items():
        cuts = sorted(rng.sample(range(1, len(body)), 40))
        assert outcome(split_at(body, *cuts), declared_length=declared) == expected, name


# --- raw header-region counting (Prompt 90) ------------------------------------------------------


def raw_part(lines: Sequence[bytes], value: bytes = b"T") -> bytes:
    """A part built from exact header lines (no normalization)."""
    head = b"".join(line + b"\r\n" for line in lines)
    return b"--" + BOUNDARY + b"\r\n" + head + b"\r\n" + value + b"\r\n"


def region(lines: Sequence[bytes]) -> int:
    """Header-region size: every line with its CRLF, plus the empty line's CRLF."""
    return sum(len(line) + 2 for line in lines) + 2


def title_body(lines: Sequence[bytes]) -> bytes:
    rest = part("document_key", b"k") + part("source_type", b"contract") + file_part()
    return raw_part(lines) + rest + CLOSE


TITLE = b'Content-Disposition: form-data; name="title"'


def padded(total: int, *, prefix: bytes = b"X-Pad:", fill: bytes = b"p") -> list[bytes]:
    """Header lines whose region is exactly ``total`` bytes; the value ends in a visible byte."""
    lines = [TITLE, prefix + b"v"]
    lines[1] = prefix + fill * (total - region(lines)) + b"v"
    assert region(lines) == total
    return lines


def every_outcome(body: bytes) -> set[int | str]:
    return {outcome(chunks) for chunks in presentations(body).values()}


def test_whitespace_heavy_header_values_count_toward_the_cap() -> None:
    lines = [TITLE, b"X-One:" + b" " * 5000 + b"a", b"X-Two:" + b" " * 5000 + b"b"]
    assert region(lines) > 10_000
    assert every_outcome(title_body(lines)) == {413}


@pytest.mark.parametrize(
    ("prefix", "fill"),
    [(b"X-Pad:", b"p"), (b"X-Pad: ", b"p"), (b"X-Pad:", b" "), (b"X-Pad:", b"\t")],
    ids=["no space", "with space", "spaces", "tabs"],
)
def test_the_header_region_cap_is_exact(prefix: bytes, fill: bytes) -> None:
    at_limit = padded(MAX_PART_HEADER_BYTES, prefix=prefix, fill=fill)
    over = padded(MAX_PART_HEADER_BYTES + 1, prefix=prefix, fill=fill)
    assert every_outcome(title_body(at_limit)) == {OK}
    assert every_outcome(title_body(over)) == {413}


def test_headers_without_the_optional_space_parse() -> None:
    lines = [b'Content-Disposition:form-data; name="title"', b"X-Note:value"]
    assert every_outcome(title_body(lines)) == {OK}
    assert parse(title_body(lines)).title == "T"


def test_many_short_header_lines_count_their_syntax() -> None:
    lines = [TITLE] + [b"X:a"] * ((MAX_PART_HEADER_BYTES - region([TITLE])) // 5)
    assert region(lines) <= MAX_PART_HEADER_BYTES
    assert every_outcome(title_body(lines)) == {OK}
    extra = [*lines, *[b"X:a"] * 2]
    assert region(extra) > MAX_PART_HEADER_BYTES
    assert every_outcome(title_body(extra)) == {413}


def test_a_cap_crossing_before_a_malformed_byte_is_413() -> None:
    lines = [*padded(MAX_PART_HEADER_BYTES - 10), b"X-Late:" + b"q" * 20, b"Bad Name: v"]
    assert every_outcome(title_body(lines)) == {413}


def test_a_malformed_byte_before_the_cap_crossing_is_422() -> None:
    lines = [TITLE, b"Bad Name: v", b"X-Pad:" + b"p" * MAX_PART_HEADER_BYTES]
    body = title_body(lines)
    assert every_outcome(body) == {422}
    assert rejection(body).errors == ((("body",), "malformed"),)


def test_the_cap_is_per_part() -> None:
    near = padded(MAX_PART_HEADER_BYTES)
    key_lines = [b'Content-Disposition: form-data; name="document_key"', near[1]]
    key_lines[1] = key_lines[1][: len(key_lines[1]) - (region(key_lines) - region(near))]
    assert region(key_lines) == MAX_PART_HEADER_BYTES
    body = (
        raw_part(near)
        + raw_part(key_lines, b"k")
        + part("source_type", b"contract")
        + file_part()
        + CLOSE
    )
    assert every_outcome(body) == {OK}


# --- parameters are validated before anything is dropped (Prompt 90) ---------------------------


def disposition_body(disposition: bytes, *, name: str = "title") -> bytes:
    rest = {
        "document_key": part("document_key", b"k"),
        "title": part("title", b"T"),
        "source_type": part("source_type", b"contract"),
    }
    rest.pop(name)
    head = raw_part([b"Content-Disposition: " + disposition])
    return head + b"".join(rest.values()) + file_part() + CLOSE


@pytest.mark.parametrize(
    "disposition",
    [
        b"form-data; name=\"title\"; filename*=UTF-8''t.txt",
        b"form-data; name=\"title\"; FILENAME*=utf-8''t.txt",
        b'form-data; name="title"; filename=""',
    ],
)
def test_text_fields_cannot_carry_any_filename(disposition: bytes) -> None:
    for chunks in presentations(disposition_body(disposition)).values():
        with pytest.raises(UploadRejected) as caught:
            parse(chunks)
        assert caught.value.errors == ((("body", "title"), "filename_not_allowed"),)


@pytest.mark.parametrize(
    "disposition",
    [
        b'form-data; name="title"; name="document_key"',
        b'form-data; name="title"; NAME="title"',
        b"form-data; name*=UTF-8''title",
        b"form-data; name*=UTF-8''title; name=\"title\"",
        b'form-data; name="title"; filename="a"; filename="b"',
        b'form-data; name="title";',
        b"form-data; name=ti tle",
        b'form-data; name="title',
    ],
)
def test_ambiguous_or_invalid_dispositions_are_422(disposition: bytes) -> None:
    for chunks in presentations(disposition_body(disposition)).values():
        with pytest.raises(UploadRejected) as caught:
            parse(chunks)
        assert caught.value.errors == ((("body",), "invalid_part_headers"),)


@pytest.mark.parametrize(
    "disposition",
    [b"form-data; name=title", b'FORM-DATA ;Name="title"', b'form-data;name="title";x-extra=1'],
)
def test_valid_token_and_quoted_dispositions(disposition: bytes) -> None:
    assert every_outcome(disposition_body(disposition)) == {OK}


def test_a_file_part_may_carry_an_extended_filename() -> None:
    disposition = b"form-data; name=\"file\"; filename*=UTF-8''r%C3%A9sum%C3%A9.md"
    file = raw_part([b"Content-Disposition: " + disposition, b"Content-Type: text/plain"], b"x")
    assert every_outcome(fields() + file + CLOSE) == {OK}


def media_body(content_type: bytes) -> bytes:
    disposition = b'Content-Disposition: form-data; name="file"; filename="p.md"'
    return fields() + raw_part([disposition, b"Content-Type: " + content_type], b"x") + CLOSE


@pytest.mark.parametrize(
    "content_type",
    [
        b"text/plain; charset*=utf-8''latin-1",
        b"text/plain; charset*=utf-8''utf-8",
        b"text/plain; charset=latin-1; charset=utf-8",
        b"text/plain; charset=utf-8; charset=latin-1",
        b"text/plain; charset=utf-8; charset=utf-8",
        b"text/plain; charset=utf-8; format=flowed",
        b"text/plain;",
        b"text/plain; charset",
        b'text/plain; charset="utf-8',
        b"text/plain/extra",
    ],
)
def test_lossy_or_ambiguous_media_parameters_are_415(content_type: bytes) -> None:
    assert every_outcome(media_body(content_type)) == {415}


@pytest.mark.parametrize(
    "content_type",
    [
        b"text/plain",
        b"TEXT/Markdown",
        b"text/plain; charset=utf-8",
        b'text/plain; charset="UTF-8"',
        b"text/markdown;charset=Utf-8",
        b"text/plain ; charset=utf-8 ",
    ],
)
def test_valid_media_type_forms(content_type: bytes) -> None:
    assert every_outcome(media_body(content_type)) == {OK}


@pytest.mark.parametrize(
    "value",
    [
        b"multipart/form-data; boundary=a; boundary=b",
        b"multipart/form-data; boundary*=utf-8''abc",
        b"multipart/form-data; boundary*=utf-8''abc; boundary=abc",
        b"multipart/form-data; boundary=abc;",
    ],
)
def test_request_boundary_parameters_must_be_unambiguous(value: bytes) -> None:
    with pytest.raises(UploadRejected) as caught:
        check_request_headers([(b"content-type", value)])
    assert caught.value.status == 415


def test_parameter_errors_never_carry_submitted_text(caplog: pytest.LogCaptureFixture) -> None:
    disposition = f"form-data; name=\"title\"; filename*=UTF-8''{SUBMITTED_MARKER}".encode()
    bodies = [
        disposition_body(disposition),
        media_body(f"text/plain; charset*=utf-8''{SUBMITTED_MARKER}".encode()),
        disposition_body(f'form-data; name="title"; {SUBMITTED_MARKER}="x"; x="y'.encode()),
    ]
    with caplog.at_level(logging.DEBUG):
        for body in bodies:
            error = rejection(body)
            assert SUBMITTED_MARKER not in repr(error) + str(error.errors)
    assert all(SUBMITTED_MARKER not in record.getMessage() for record in caplog.records)
