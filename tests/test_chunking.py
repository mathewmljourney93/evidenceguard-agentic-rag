"""The deterministic chunker ``text-md-v1`` (M3d, ADR-0010): pure tests, no database.

The normative examples are those of the accepted specification (``docs/plan.md``, M3d section
A); examples 4 and 8 lower ``TARGET_CHARS`` exactly as the specification's illustrations do.
Every test that produces segments also checks the provenance mapping and the coverage
invariant: only a leading BOM, LF and CRLF terminators and spaces and tabs may be absent from
the ordered body spans, and every other character appears in exactly one of them.
"""

import random
from collections.abc import Sequence
from uuid import UUID

import pytest

from evidenceguard_domain.chunks import MAX_CHUNK_CHARS, MAX_CHUNKS_PER_REVISION, chunk_id
from evidenceguard_domain.revisions import MediaType, RevisionContent
from evidenceguard_retrieval.chunking import (
    CHUNKER_VERSION,
    MAX_HEADER_REPEAT_CHARS,
    TARGET_CHARS,
    ChunkLimitExceededError,
    EmptyDocumentError,
    Segment,
    chunk_revision,
    segment,
)

MD = MediaType.TEXT_MARKDOWN
PLAIN = MediaType.TEXT_PLAIN
TENANT_A = UUID("11111111-1111-4111-8111-111111111111")
TENANT_B = UUID("33333333-3333-4333-8333-333333333333")
REVISION = UUID("22222222-2222-4222-8222-222222222222")
# Obviously fake marker standing in for private document text.
CONTENT_MARKER = "synthetic-private-content-marker"


def _check(text: str, pieces: Sequence[Segment], *, target: int = TARGET_CHARS) -> None:
    """Reconstruction, bounds, line numbers and the coverage invariant."""
    covered: set[int] = set()
    previous_end = 0
    for piece in pieces:
        assert piece.char_start >= previous_end  # disjoint and in ascending source order
        previous_end = piece.char_end
        body = text[piece.char_start : piece.char_end]
        if piece.header_char_start is None:
            assert piece.text == body
            assert len(piece.text) <= target
        else:
            assert piece.is_table
            assert piece.header_char_end is not None
            header = text[piece.header_char_start : piece.header_char_end]
            assert piece.text == header + body
            assert len(header) <= MAX_HEADER_REPEAT_CHARS
            assert piece.header_char_end <= piece.char_start
            assert piece.header_line_end is not None and piece.header_line_end < piece.line_start
        assert 1 <= len(piece.text) <= MAX_CHUNK_CHARS
        assert piece.line_start == _line_of(text, piece.char_start)
        assert piece.line_end == _line_of(text, piece.char_end - 1)
        covered.update(range(piece.char_start, piece.char_end))
    for index, character in enumerate(text):
        if index in covered:
            assert not (index == 0 and character == "\ufeff")
            continue
        permitted = (
            (index == 0 and character == "\ufeff")
            or character == "\n"
            or (character == "\r" and text[index + 1 : index + 2] == "\n")
            or character in " \t"
        )
        assert permitted, f"a non-permitted character at offset {index} is in no chunk"


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _run(text: str, media: MediaType = MD, *, target: int = TARGET_CHARS) -> tuple[Segment, ...]:
    pieces = segment(text, media, target_chars=target)
    _check(text, pieces, target=target)
    return pieces


def _spans(pieces: Sequence[Segment]) -> list[tuple[int, int]]:
    return [(piece.char_start, piece.char_end) for piece in pieces]


# --- the normative examples --------------------------------------------------------------------


def test_example_1_headings() -> None:
    text = (
        "# Retention\n\nCustomer data is kept for 90 days.\n\n## Backups\n\n"
        "Backups are encrypted.\n"
    )
    assert len(text) == 84

    first, second = _run(text)

    assert (first.section_path, first.line_start, first.line_end) == (("Retention",), 1, 3)
    assert _spans([first]) == [(0, 47)]
    assert first.text == "# Retention\n\nCustomer data is kept for 90 days."
    assert (second.section_path, second.line_start, second.line_end) == (
        ("Retention", "Backups"),
        5,
        7,
    )
    assert _spans([second]) == [(49, 83)]
    assert second.text == "## Backups\n\nBackups are encrypted."


def test_example_2_crlf_and_bom() -> None:
    (crlf,) = _run("Line one\r\nLine two\r\n", PLAIN)
    assert (crlf.line_start, crlf.line_end, crlf.text) == (1, 2, "Line one\r\nLine two")
    assert _spans([crlf]) == [(0, 18)]

    (bom,) = _run("\ufeffTitle line\n", PLAIN)
    assert (bom.line_start, bom.line_end, bom.text) == (1, 1, "Title line")
    assert _spans([bom]) == [(1, 11)]


def test_example_3_long_text() -> None:
    text = " ".join(["alpha"] * 1000)
    assert len(text) == 5999

    pieces = _run(text, PLAIN)

    assert _spans(pieces) == [(0, 2495), (2496, 4991), (4992, 5999)]
    assert all((piece.line_start, piece.line_end) == (1, 1) for piece in pieces)
    assert text[2495] == text[4991] == " "


def test_example_4_table_rows_and_a_repeated_header() -> None:
    text = "| Region | Provider |\n|---|---|\n| EU | Alpha |\n| US | Beta |\n| APAC | Gamma |\n"

    first, second, third = _run(text, target=48)

    assert all(piece.is_table for piece in (first, second, third))
    assert (_spans([first]), first.line_start, first.line_end) == ([(0, 46)], 1, 3)
    assert first.header_char_start is None
    assert (second.header_char_start, second.header_char_end) == (0, 32)
    assert (second.header_line_start, second.header_line_end) == (1, 2)
    assert (_spans([second]), second.line_start, second.line_end) == ([(47, 60)], 4, 4)
    assert second.text == "| Region | Provider |\n|---|---|\n| US | Beta |"
    assert (third.header_char_start, third.header_char_end) == (0, 32)
    assert (_spans([third]), third.line_start) == ([(61, 77)], 5)


def test_example_5_heading_directly_after_prose() -> None:
    first, second = _run("Intro text.\n# Scope\nOnly EU data.\n")

    assert (first.section_path, first.line_start, first.line_end) == ((), 1, 1)
    assert (_spans([first]), first.text) == ([(0, 11)], "Intro text.")
    assert (second.section_path, second.line_start, second.line_end) == (("Scope",), 2, 3)
    assert (_spans([second]), second.text) == ([(12, 33)], "# Scope\nOnly EU data.")


def test_example_6_consecutive_headings() -> None:
    (with_body,) = _run("# A\n\n## B\n\nBody.\n")
    assert (with_body.section_path, with_body.line_start, with_body.line_end) == (("A", "B"), 1, 5)
    assert _spans([with_body]) == [(0, 16)]

    (alone,) = _run("# A\n## B\n")
    assert (alone.section_path, alone.line_start, alone.line_end) == (("A", "B"), 1, 2)
    assert _spans([alone]) == [(0, 8)]


def test_example_7_oversized_heading() -> None:
    text = "# " + " ".join(["word"] * 600)
    assert len(text) == 3001

    pieces = _run(text)

    assert _spans(pieces) == [(0, 2496), (2497, 3001)]
    expected = " ".join(["word"] * 40)
    assert len(expected) == 199
    assert all(piece.section_path == (expected,) for piece in pieces)


def test_example_8_oversized_and_header_only_tables() -> None:
    (header_only,) = _run("| a | b |\n|---|---|\n")
    assert header_only.is_table and _spans([header_only]) == [(0, 19)]
    assert (header_only.line_start, header_only.line_end) == (1, 2)

    text = "| Region | Provider |\n|---|---|\n| EU | Alpha |\n"
    pieces = _run(text, target=20)
    assert _spans(pieces) == [(0, 19), (20, 21), (22, 31), (32, 46)]
    assert [piece.text for piece in pieces] == [
        "| Region | Provider",
        "|",
        "|---|---|",
        "| EU | Alpha |",
    ]
    assert all(piece.is_table and piece.header_char_start is None for piece in pieces)


@pytest.mark.parametrize("text", [" \t\r\n\n  \n", "\ufeff\n  \n"])
def test_example_9_whitespace_only_sources_are_empty(text: str) -> None:
    for media in (MD, PLAIN):
        with pytest.raises(EmptyDocumentError):
            segment(text, media)


def test_example_9_nbsp_is_not_whitespace() -> None:
    (piece,) = _run("\u00a0\n")
    assert _spans([piece]) == [(0, 1)]


# --- lines, BOM and the whitespace predicate ---------------------------------------------------


def test_output_is_deterministic() -> None:
    text = _generated_document(random.Random(7))
    content = RevisionContent.from_bytes(text.encode(), MD)

    first = chunk_revision(content, tenant_id=TENANT_A, revision_id=REVISION)
    second = chunk_revision(content, tenant_id=TENANT_A, revision_id=REVISION)

    assert first == second
    assert segment(text, MD) == segment(text, MD)


def test_crlf_and_lf_give_the_same_lines_and_structure() -> None:
    lf = _generated_document(random.Random(11))
    crlf = lf.replace("\n", "\r\n")

    lf_pieces, crlf_pieces = _run(lf), _run(crlf)

    assert [(p.line_start, p.line_end, p.section_path, p.is_table) for p in lf_pieces] == [
        (p.line_start, p.line_end, p.section_path, p.is_table) for p in crlf_pieces
    ]


def test_a_lone_cr_is_an_ordinary_character() -> None:
    text = "one\rtwo\nthree\r"
    (piece,) = _run(text, PLAIN)
    assert piece.text == text and (piece.line_start, piece.line_end) == (1, 2)


def test_a_bom_only_first_line_is_blank() -> None:
    first, second = _run("\ufeff\nAlpha.\n\n# Beta\n")
    assert first.text == "Alpha." and first.line_start == 2
    assert second.section_path == ("Beta",)


def test_a_bom_is_excluded_and_line_one_starts_after_it() -> None:
    (piece,) = _run("\ufeff# Title\nBody\n")
    assert piece.char_start == 1 and piece.section_path == ("Title",)


@pytest.mark.parametrize("character", ["\u00a0", "\u3000", "\u2028", "\r", "\x0b", "\x0c"])
def test_other_characters_are_not_whitespace(character: str) -> None:
    # No LF follows, so even a CR is a lone CR here (CR before LF is a terminator).
    (piece,) = _run(character, PLAIN)
    assert piece.text == character


@pytest.mark.parametrize("character", ["\u00a0", "\r"])
def test_split_points_use_only_spaces_and_tabs(character: str) -> None:
    text = "x" * 1300 + character + "y" * 1600
    pieces = _run(text, PLAIN)
    assert _spans(pieces) == [(0, 2500), (2500, len(text))]  # a hard cut, nothing omitted


# --- Markdown blocks -------------------------------------------------------------------------


def test_a_fence_keeps_blank_lines_and_heading_like_lines() -> None:
    text = "```python\nx = 1\n\n# not a heading\n```\nAfter.\n"
    (piece,) = _run(text)
    assert piece.section_path == () and piece.text == text.rstrip("\n")


@pytest.mark.parametrize(
    "line",
    ["``` info", "``", "~~~", "    ```", "```x"],
    ids=["info-string", "short-run", "other-character", "deep-indent", "trailing-text"],
)
def test_lines_that_do_not_close_a_fence(line: str) -> None:
    text = f"```\ncode\n{line}\n# still code\n"
    (piece,) = _run(text)
    assert piece.section_path == ()  # the heading-like line is inside the unclosed fence
    assert piece.text == text.rstrip("\n")


def test_a_closing_fence_may_be_longer_indented_and_followed_by_whitespace() -> None:
    first, second = _run("~~~~\ncode\n   ~~~~~~ \t\n# After\n")
    assert first.text == "~~~~\ncode\n   ~~~~~~ \t"
    assert second.section_path == ("After",)


def test_an_unclosed_fence_runs_to_the_end_without_trailing_blank_lines() -> None:
    (piece,) = _run("```\nopen\n\n  \n")
    assert piece.text == "```\nopen" and piece.line_end == 2


def test_a_backtick_info_string_with_a_backtick_is_not_a_fence() -> None:
    first, second = _run("``` a`b\n# Heading\n")
    assert first.section_path == () and first.text == "``` a`b"
    assert second.section_path == ("Heading",)


@pytest.mark.parametrize(
    ("follower", "expected_table"),
    [("# Next", False), ("| a | b |\n|---|---|", True)],
)
def test_a_paragraph_stops_before_a_heading_or_table(follower: str, expected_table: bool) -> None:
    pieces = _run(f"Prose line.\n{follower}\n")
    assert pieces[0].text == "Prose line."
    assert pieces[1].is_table is expected_table
    assert len(pieces) == 2


def test_a_paragraph_stops_before_a_fence_opening() -> None:
    """Had the paragraph continued, the fence line would be prose and the heading-like line a
    real heading starting a second chunk."""
    text = "Prose line.\n```\n# not a heading\n```\n"
    (piece,) = _run(text)
    assert piece.section_path == () and piece.text == text.rstrip("\n")


def test_setext_underlines_are_ordinary_lines() -> None:
    (piece,) = _run("Title\n=====\nText\n---\n")
    assert piece.section_path == () and not piece.is_table


def test_heading_text_and_closing_sequences() -> None:
    cases = {
        "# Plain": "Plain",
        "#\tTabbed  ": "Tabbed",
        "## Closed ##": "Closed",
        "## Kept#": "Kept#",
        "# a # b ###": "a # b",
        "#": "",
        "# ###": "",
        "   ### Indented": "Indented",
    }
    for line, expected in cases.items():
        (piece,) = _run(f"{line}\n")
        assert piece.section_path[-1] == expected, line
    (seven,) = _run("####### seven\n")
    assert seven.section_path == ()  # seven #s are not a heading
    (nospace,) = _run("#hashtag\n")
    assert nospace.section_path == ()


def test_section_paths_follow_heading_levels() -> None:
    text = "# A\n\nx\n\n### C\n\ny\n\n## B\n\nz\n\n## D\n## E\n\nw\n"
    pieces = _run(text)
    assert [piece.section_path for piece in pieces] == [
        ("A",),
        ("A", "C"),
        ("A", "B"),
        ("A", "E"),
    ]
    assert pieces[3].text == "## D\n## E\n\nw"


def test_table_continuation_stops_at_headings_fences_and_lines_without_pipes() -> None:
    pieces = _run("| a |\n|---|\n| 1 |\nplain\n| b |\n|---|\n# H\n")
    assert [(piece.is_table, piece.text) for piece in pieces] == [
        (True, "| a |\n|---|\n| 1 |"),
        (False, "plain"),
        (True, "| b |\n|---|"),
        (False, "# H"),
    ]


# --- packing and sizes -------------------------------------------------------------------------


def test_prose_packs_up_to_exactly_the_target() -> None:
    first = "a" * 1000
    exact = first + "\n\n" + "b" * (TARGET_CHARS - 1002)
    (piece,) = _run(exact + "\n", PLAIN)
    assert len(piece.text) == TARGET_CHARS

    over = first + "\n\n" + "b" * (TARGET_CHARS - 1001)
    assert [len(piece.text) for piece in _run(over + "\n", PLAIN)] == [1000, TARGET_CHARS - 1001]


def test_an_oversized_paragraph_splits_into_line_runs() -> None:
    lines = [f"{index:04d} " + "z" * 95 for index in range(60)]  # 100 + 1 per line
    pieces = _run("\n".join(lines) + "\n", PLAIN)
    assert [piece.line_start for piece in pieces] == [1, 25, 49]
    assert all(len(piece.text) <= TARGET_CHARS for piece in pieces)


def test_oversized_lines_trim_leading_and_trailing_whitespace() -> None:
    body = " ".join(["word"] * 700)
    text = "  \t" + body + " \t \n"
    pieces = _run(text, PLAIN)
    assert pieces[0].char_start == 3
    assert pieces[-1].char_end == 3 + len(body)
    assert all(piece.text == piece.text.strip(" \t") and piece.text for piece in pieces)


def test_a_line_without_whitespace_in_range_is_cut_hard() -> None:
    text = "q" * 6000
    assert _spans(_run(text, PLAIN)) == [(0, 2500), (2500, 5000), (5000, 6000)]


def test_whitespace_runs_at_a_split_point_are_skipped_whole() -> None:
    text = "a" * 2000 + " \t  " + "b" * 1000
    pieces = _run(text, PLAIN)
    assert _spans(pieces) == [(0, 2000), (2004, 3004)]


def test_split_blocks_are_never_packed_with_neighbours() -> None:
    text = "short before\n\n" + "w " * 1500 + "\n\nshort after\n"
    pieces = _run(text, PLAIN)
    assert pieces[0].text == "short before"
    assert pieces[-1].text == "short after"


def test_a_split_heading_run_keeps_the_runs_path() -> None:
    long_heading = "## " + " ".join(["part"] * 700)
    text = f"# Top\n\n{long_heading}\n\nFollowing text.\n"
    pieces = _run(text)
    assert pieces[0].text == "# Top"
    expected = ("Top", " ".join(["part"] * 700)[:200].rstrip(" \t"))
    assert all(piece.section_path == expected for piece in pieces)
    assert pieces[-1].text == "Following text."


# --- tables -----------------------------------------------------------------------------------


def _table(header_cell: int, rows: Sequence[int]) -> str:
    lines = ["| " + "h" * header_cell + " |", "|---|"]
    lines += ["| " + "r" * size + " |" for size in rows]
    return "\n".join(lines) + "\n"


def test_long_tables_repeat_a_small_header() -> None:
    text = _table(10, [500] * 12)
    pieces = _run(text)
    assert all(piece.is_table for piece in pieces)
    assert pieces[0].header_char_start is None
    assert all(piece.header_char_start == 0 for piece in pieces[1:])
    assert all(len(piece.text) <= TARGET_CHARS for piece in pieces)


def test_a_header_above_the_repeat_limit_is_not_repeated() -> None:
    text = _table(MAX_HEADER_REPEAT_CHARS + 100, [600] * 6)
    pieces = _run(text)
    assert len(pieces) > 1
    assert all(piece.header_char_start is None for piece in pieces)
    assert all(piece.is_table and len(piece.text) <= TARGET_CHARS for piece in pieces)


def test_a_header_above_the_target_splits_as_an_oversized_block() -> None:
    text = _table(TARGET_CHARS + 10, [5, 5])
    pieces = _run(text)
    assert all(piece.is_table and piece.header_char_start is None for piece in pieces)


def test_a_header_only_table_that_does_not_fit_splits_within_the_target() -> None:
    text = "| " + " | ".join(["cell"] * 800) + " |\n|---|\n"
    pieces = _run(text)
    assert len(pieces) > 1 and all(piece.is_table for piece in pieces)


def test_an_oversized_row_is_emitted_with_the_header_within_the_absolute_limit() -> None:
    text = _table(10, [100, 2480, 100])
    pieces = _run(text)
    with_header = [piece for piece in pieces if piece.header_char_start is not None]
    assert any(len(piece.text) > TARGET_CHARS for piece in with_header)
    assert all(len(piece.text) <= MAX_CHUNK_CHARS for piece in pieces)


def test_a_row_too_long_even_for_the_absolute_limit_is_cut_without_the_header() -> None:
    row = "| " + " ".join(["cell"] * 900) + " |"
    text = "| h |\n|---|\n| a |\n" + row + "\n"
    pieces = _run(text)
    row_pieces = [piece for piece in pieces if piece.line_start == 4]
    assert len(row_pieces) > 1
    assert all(piece.header_char_start is None and piece.is_table for piece in row_pieces)


# --- limits and errors -----------------------------------------------------------------------


def _sections(count: int) -> str:
    return "".join(f"# H{index}\n\nP{index}\n\n" for index in range(count))


def test_the_chunk_count_cap() -> None:
    assert len(segment(_sections(MAX_CHUNKS_PER_REVISION), MD)) == MAX_CHUNKS_PER_REVISION
    with pytest.raises(ChunkLimitExceededError):
        segment(_sections(MAX_CHUNKS_PER_REVISION + 1), MD)


def test_invalid_arguments_are_refused() -> None:
    with pytest.raises(TypeError):
        segment(b"bytes", MD)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        segment("text", "text/html")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        segment("text", MD, target_chars=TARGET_CHARS + 1)
    with pytest.raises(TypeError):
        chunk_revision("text", tenant_id=TENANT_A, revision_id=REVISION)  # type: ignore[arg-type]


def test_content_never_appears_in_reprs_or_errors() -> None:
    text = f"# {CONTENT_MARKER}\n\n{CONTENT_MARKER} body\n"
    content = RevisionContent.from_bytes(text.encode(), MD)
    chunks = chunk_revision(content, tenant_id=TENANT_A, revision_id=REVISION)
    for value in (*chunks, *segment(text, MD)):
        assert CONTENT_MARKER not in repr(value) and CONTENT_MARKER not in str(value)
    for error_text in (f"   \n{CONTENT_MARKER}", _sections(MAX_CHUNKS_PER_REVISION + 1)):
        with pytest.raises((EmptyDocumentError, ChunkLimitExceededError)) as info:
            segment(error_text.replace(CONTENT_MARKER, "  "), MD)
        assert CONTENT_MARKER not in str(info.value)


# --- chunk IDs -------------------------------------------------------------------------------


def test_chunks_carry_deterministic_tenant_scoped_ids() -> None:
    content = RevisionContent.from_bytes(b"# Retention\n\nKept for 90 days.\n", MD)

    in_a = chunk_revision(content, tenant_id=TENANT_A, revision_id=REVISION)
    in_b = chunk_revision(content, tenant_id=TENANT_B, revision_id=REVISION)

    assert in_a[0].id == UUID("a11668be-c537-5f4d-b5d8-7a056099b8a0")
    assert in_b[0].id == UUID("53214eae-4b9a-5805-a6e7-41a8e3b6341c")
    assert not {chunk.id for chunk in in_a} & {chunk.id for chunk in in_b}
    assert [chunk.text for chunk in in_a] == [chunk.text for chunk in in_b]
    for chunk in in_a:
        assert chunk.chunker_version == CHUNKER_VERSION == "text-md-v1"
        assert chunk.id == chunk_id(TENANT_A, REVISION, CHUNKER_VERSION, chunk.ordinal)
    assert [chunk.ordinal for chunk in in_a] == list(range(len(in_a)))


# --- generated documents ---------------------------------------------------------------------


def _generated_document(rng: random.Random) -> str:
    """A seeded, synthetic Markdown document mixing every block kind and odd whitespace."""
    words = ["alpha", "beta", "gamma", "delta", "\u00e9t\u00e9", "\u00a0", "x\ry", "z\tz"]
    parts: list[str] = []
    for _ in range(rng.randint(30, 60)):
        kind = rng.randrange(7)
        if kind == 0:
            parts.append("#" * rng.randint(1, 6) + " " + " ".join(rng.choices(words, k=3)))
        elif kind == 1:
            parts.append("```\n" + "\n".join(rng.choices(words, k=4)) + "\n```")
        elif kind == 2:
            rows = ["| " + " | ".join(rng.choices(words, k=2)) + " |" for _ in range(30)]
            parts.append("| a | b |\n|---|---|\n" + "\n".join(rows))
        elif kind == 3:
            parts.append(" ".join(rng.choices(words, k=rng.randint(400, 900))))
        elif kind == 4:
            parts.append("  \t  ")
        else:
            parts.append(" ".join(rng.choices(words, k=rng.randint(5, 40))))
        parts.append(rng.choice(["\n", "\n\n", "\n \t\n"]))
    return "".join(parts)


@pytest.mark.parametrize("seed", range(12))
@pytest.mark.parametrize("media", [MD, PLAIN])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_generated_documents_keep_every_invariant(
    seed: int, media: MediaType, newline: str
) -> None:
    text = _generated_document(random.Random(seed)).replace("\n", newline)
    if seed % 3 == 0:
        text = "\ufeff" + text
    pieces = _run(text, media)
    assert pieces
    for piece in pieces:
        assert len(piece.section_path) <= 6
        assert all(len(part) <= 200 for part in piece.section_path)


def test_coverage_across_lf_and_crlf_separated_chunks() -> None:
    """The planned coverage case: several chunks separated by LF and CRLF terminators and blank
    lines of spaces and tabs, with a lone CR and NBSP inside chunk text."""
    text = (
        "\ufeff# One\r\n\r\nalpha\u00a0beta\rgamma\r\n \t\r\n# Two\n\n  delta\n\t\n"
        "| a |\r\n|---|\r\n| x\u00a0|\n\n# Three\r\nomega"
    )
    pieces = _run(text)
    assert [piece.section_path for piece in pieces] == [
        ("One",),
        ("Two",),
        ("Two",),
        ("Three",),
    ]
    joined = "".join(text[piece.char_start : piece.char_end] for piece in pieces)
    assert joined.count("\u00a0") == 2 and joined.count("\r") - joined.count("\r\n") == 1
