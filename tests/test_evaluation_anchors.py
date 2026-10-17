"""Anchor location, chunk mapping, ``parts`` and manifest verification for retrieval evaluation
(``evidenceguard_retrieval.evaluation.anchors``; M4e, ADR-0017). Hand-built spans plus the
offline ``text-md-v1`` chunker; no database."""

import json
from dataclasses import replace
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from evidenceguard_domain.chunks import Chunk, chunks_manifest_sha256
from evidenceguard_domain.revisions import MediaType, RevisionContent
from evidenceguard_retrieval.chunking import chunk_revision
from evidenceguard_retrieval.evaluation.anchors import (
    MAX_MAPPING_ENTRIES,
    ChunkSpan,
    StoredChunkRow,
    chunk_set,
    locate,
    offline_spans,
    resolve_anchor,
    revalidate,
    spans_from_chunks,
    validate_suite,
    verify_manifest,
)
from evidenceguard_retrieval.evaluation.corpus import (
    Anchor,
    AnchorRef,
    EvaluationError,
    Part,
    RevisionRef,
    build_suite,
)

REF = AnchorRef(RevisionRef("halverson-freight", "lumenvale-cloud", "policy", 1), "a")
TENANT, REVISION = UUID(int=1), UUID(int=2)
A, B, C = UUID(int=10), UUID(int=11), UUID(int=12)


def anchor(quote: str, occurrence: int | None = None, parts: list[Part] | None = None) -> Anchor:
    return Anchor(REF, quote, occurrence, None if parts is None else tuple(parts))


def code_of(call: object) -> str:
    assert callable(call)
    with pytest.raises(EvaluationError) as raised:
        call()
    return raised.value.code


def chunks_of(text: str, media: MediaType = MediaType.TEXT_MARKDOWN) -> list[Chunk]:
    content = RevisionContent.from_bytes(text.encode("utf-8"), media)
    return list(chunk_revision(content, tenant_id=TENANT, revision_id=REVISION))


# --- exact location ------------------------------------------------------------------------------


def test_locate_counts_non_overlapping_matches_left_to_right() -> None:
    assert locate("aaaa", "aa", 1) == (0, 2)
    assert locate("aaaa", "aa", 2) == (2, 4)
    assert code_of(lambda: locate("aaaa", "aa", 3)) == "anchor_occurrence_out_of_range"
    assert code_of(lambda: locate("aaaa", "aa", None)) == "anchor_ambiguous"
    assert locate("xaay", "aa", None) == (1, 3)
    assert code_of(lambda: locate("abc", "zz", None)) == "anchor_not_found"
    assert code_of(lambda: locate("abc", "zz", None, part=True)) == "anchor_part_not_found"
    assert locate("ab ab ab", "ab", None, start=2, end=5) == (3, 5)


def test_locate_does_not_normalize() -> None:
    assert code_of(lambda: locate("Café", "Café", None)) == "anchor_not_found"
    assert code_of(lambda: locate("a  b", "a b", None)) == "anchor_not_found"
    assert code_of(lambda: locate("Term", "term", None)) == "anchor_not_found"
    assert code_of(lambda: locate("a\nb", "a b", None)) == "anchor_not_found"
    assert locate("x \U0001d538 y", "\U0001d538", None) == (2, 3)  # code points, not UTF-16


# --- mapping ---------------------------------------------------------------------------------


def test_an_anchor_maps_to_every_containing_body_and_header_span() -> None:
    text = "0123456789" * 3
    chunks = [ChunkSpan(A, 0, 12), ChunkSpan(B, 10, 20), ChunkSpan(C, 20, 30, 0, 5)]
    entries = resolve_anchor(anchor("234", occurrence=1), text, chunks)
    assert [(e.chunk_id, e.route) for e in entries] == [(A, "body"), (C, "header")]
    assert chunk_set(entries) == {A, C}
    overlap = resolve_anchor(anchor("01", occurrence=2), text, chunks)
    assert chunk_set(overlap) == {A, B}
    assert all(e.part_index is None and (e.char_start, e.char_end) == (10, 12) for e in overlap)


def test_a_quote_crossing_a_boundary_needs_parts() -> None:
    text = "First sentence.\n\nSecond sentence."
    chunks = [ChunkSpan(A, 0, 15), ChunkSpan(B, 17, 33)]
    whole = "First sentence.\n\nSecond sentence."
    assert code_of(lambda: resolve_anchor(anchor(whole), text, chunks)) == (
        "anchor_crosses_chunk_boundary"
    )
    parts = [Part("First sentence.", None), Part("Second sentence.", None)]
    entries = resolve_anchor(anchor(whole, parts=parts), text, chunks)
    assert [(e.chunk_id, e.part_index) for e in entries] == [(A, 0), (B, 1)]
    single = [ChunkSpan(A, 0, 33)]
    assert code_of(lambda: resolve_anchor(anchor(whole, parts=parts), text, single)) == (
        "anchor_parts_unnecessary"
    )


@pytest.mark.parametrize(
    ("text", "parts", "code"),
    [
        ("One. Two.", [Part("Two.", None), Part("One.", None)], "anchor_parts_gap"),
        ("One. Two.", [Part("One.", None), Part("One.", None)], "anchor_parts_order"),
        ("One. Two.", [Part("One", None), Part("Two.", None)], "anchor_parts_gap"),
        ("One. Two.", [Part("ne.", None), Part("Two.", None)], "anchor_parts_gap"),
        ("One. Two.", [Part("One.", None), Part("Two", None)], "anchor_parts_gap"),
        ("One. Two.", [Part("One.", None), Part("Three.", None)], "anchor_part_not_found"),
        ("One. Two.", [Part("One.", None), Part("Two.", 2)], "anchor_part_occurrence_out_of_range"),
        ("a a. a", [Part("a", None), Part("a.", None)], "anchor_part_ambiguous"),
    ],
)
def test_invalid_parts(text: str, parts: list[Part], code: str) -> None:
    chunks = [ChunkSpan(A, 0, 4), ChunkSpan(B, 4, len(text))]
    assert code_of(lambda: resolve_anchor(anchor(text, parts=parts), text, chunks)) == code


def test_parts_are_located_only_inside_the_parent_range() -> None:
    text = "Two. One. Two."
    chunks = [ChunkSpan(A, 0, 9), ChunkSpan(B, 9, 14)]
    parts = [Part("One.", None), Part("Two.", None)]
    entries = resolve_anchor(anchor("One. Two.", parts=parts), text, chunks)
    assert [(e.part_index, e.char_start) for e in entries] == [(0, 5), (1, 10)]


def test_a_part_that_no_chunk_contains_is_unmapped() -> None:
    text = "One. Two."
    chunks = [ChunkSpan(A, 0, 4), ChunkSpan(B, 6, 9)]
    parts = [Part("One.", None), Part("Two.", None)]
    assert code_of(lambda: resolve_anchor(anchor(text, parts=parts), text, chunks)) == (
        "anchor_part_unmapped"
    )


def test_gaps_allow_crlf_but_not_a_lone_carriage_return() -> None:
    chunks = [ChunkSpan(A, 0, 4), ChunkSpan(B, 6, 10)]
    parts = [Part("One.", None), Part("Two.", None)]
    assert resolve_anchor(anchor("One.\r\nTwo.", parts=parts), "One.\r\nTwo.", chunks)
    assert code_of(
        lambda: resolve_anchor(anchor("One.\r Two.", parts=parts), "One.\r Two.", chunks)
    ) == ("anchor_parts_gap")


def test_the_mapping_size_is_bounded() -> None:
    text = "needle"
    many = [ChunkSpan(UUID(int=n), 0, 6) for n in range(MAX_MAPPING_ENTRIES + 1)]
    assert code_of(lambda: resolve_anchor(anchor("needle"), text, many)) == (
        "anchor_mapping_too_large"
    )
    assert len(resolve_anchor(anchor("needle"), text, many[:MAX_MAPPING_ENTRIES])) == 64


def test_mapping_entries_are_sorted_by_chunk_part_and_route() -> None:
    text = "header row\nbody"
    chunks = [ChunkSpan(C, 0, 15), ChunkSpan(A, 11, 15, 0, 10), ChunkSpan(B, 0, 10)]
    entries = resolve_anchor(anchor("header"), text, chunks)
    assert [(e.chunk_id, e.route) for e in entries] == [(A, "header"), (B, "body"), (C, "body")]


# --- real chunker -------------------------------------------------------------------------------


def _long_table() -> str:
    rows = "".join(
        f"| Vendor {n:03d} | Region {n:03d} | Purpose number {n:03d} |\n" for n in range(120)
    )
    return "# Subprocessors\n\n| Name | Region | Purpose |\n| --- | --- | --- |\n" + rows


def test_a_long_table_header_maps_to_its_repeated_header_spans() -> None:
    text = _long_table()
    chunks = chunks_of(text)
    continuation = [c for c in chunks if c.header_char_start is not None]
    assert len(continuation) >= 2, "the synthetic table must split"
    entries = resolve_anchor(anchor("| Name | Region | Purpose |"), text, spans_from_chunks(chunks))
    header_ids = {e.chunk_id for e in entries if e.route == "header"}
    assert header_ids == {c.id for c in continuation}
    first_table = next(c for c in chunks if c.is_table)
    assert {e.chunk_id for e in entries if e.route == "body"} == {first_table.id}
    row = resolve_anchor(
        anchor("| Vendor 119 | Region 119 | Purpose number 119 |"), text, spans_from_chunks(chunks)
    )
    assert [e.route for e in row] == ["body"] and row[0].chunk_id == chunks[-1].id


def test_a_quote_across_real_paragraph_chunks_uses_parts() -> None:
    first, second = "A" * 2000 + " end of first.", "Start of second. " + "B" * 2000
    text = f"{first}\n\n{second}\n"
    chunks = spans_from_chunks(chunks_of(text, MediaType.TEXT_PLAIN))
    assert len(chunks) == 2
    quote = "end of first.\n\nStart of second."
    assert code_of(lambda: resolve_anchor(anchor(quote), text, chunks)) == (
        "anchor_crosses_chunk_boundary"
    )
    parts = [Part("end of first.", None), Part("Start of second.", None)]
    assert len(chunk_set(resolve_anchor(anchor(quote, parts=parts), text, chunks))) == 2


# --- manifest verification -------------------------------------------------------------------


def _rows(chunks: list[Chunk]) -> list[StoredChunkRow]:
    return [
        StoredChunkRow(
            c.id,
            c.ordinal,
            c.content_sha256,
            c.section_path,
            c.is_table,
            c.line_start,
            c.line_end,
            c.char_start,
            c.char_end,
            c.header_line_start,
            c.header_line_end,
            c.header_char_start,
            c.header_char_end,
        )
        for c in chunks
    ]


def test_manifest_verification() -> None:
    text = _long_table()
    chunks = chunks_of(text)
    stored = chunks_manifest_sha256(chunks)
    rows = _rows(chunks)

    def verify(**changes: object) -> object:
        arguments: dict[str, object] = {
            "text": text,
            "media_type": MediaType.TEXT_MARKDOWN,
            "tenant_id": TENANT,
            "revision_id": REVISION,
            "chunker_version": "text-md-v1",
            "stored_manifest_sha256": stored,
            "rows": rows,
        }
        arguments.update(changes)
        return verify_manifest(**arguments)  # type: ignore[arg-type]

    spans = verify(rows=list(reversed(rows)))
    assert spans == spans_from_chunks(chunks)
    mismatch = "mapping_manifest_mismatch"
    assert code_of(lambda: verify(chunker_version="text-md-v2")) == mismatch
    assert code_of(lambda: verify(stored_manifest_sha256="0" * 64)) == mismatch
    assert code_of(lambda: verify(rows=rows[:-1])) == mismatch
    assert (
        code_of(lambda: verify(rows=[replace(rows[0], char_end=rows[0].char_end - 1), *rows[1:]]))
        == mismatch
    )
    assert code_of(lambda: verify(rows=[replace(rows[0], id=uuid4()), *rows[1:]])) == mismatch
    assert code_of(lambda: verify(text=text + "| Extra | Row | Here |\n")) == mismatch
    assert code_of(lambda: verify(revision_id=UUID(int=3))) == mismatch
    assert code_of(lambda: verify(media_type=MediaType.TEXT_PLAIN)) == mismatch


# --- complete suite validation (Prompt 145) ----------------------------------------------------

_MINI_CORPUS = """format = "eg-corpus-v1"

[[tenants]]
slug = "halverson-freight"

  [[tenants.vendors]]
  slug = "lumenvale-cloud"
  name = "Lumenvale Cloud"

    [[tenants.vendors.documents]]
    key = "policy"
    title = "Policy"
    source_type = "vendor_statement"
    media_type = "text/plain"

      [[tenants.vendors.documents.revisions]]
      n = 1
"""
_DOC = "documents/halverson-freight/lumenvale-cloud/policy@r1.md"
_INJECTED_DOC = "variants/injected/halverson-freight/lumenvale-cloud/policy@r1.md"
_GT = "ground_truth/halverson-freight.toml"
_REF = "halverson-freight/lumenvale-cloud/policy@r1"


def _mini(
    text: str, anchors: str, *, forbidden: str | None = None, injected: str | None = None
) -> dict[str, bytes]:
    corpus = _MINI_CORPUS
    if injected is not None:
        corpus += f'\n[variants.injected]\nreplaces = ["{_REF}"]\n'
    questions = "questions = []\n"
    body = ""
    if forbidden is not None:
        questions = ""
        body = (
            '\n[[questions]]\nvendor = "lumenvale-cloud"\nid = "BCP-01"\ntext = "Q?"\n'
            'search_queries = ["q"]\n\n  [[questions.cases]]\n  epochs = ["initial", "final"]\n'
            f'  expected_status = "missing"\n  gold = []\n  forbidden = ["{_REF}#{forbidden}"]\n'
            "  acceptable_claims = []\n  wrong_claims = []\n"
        )
    gt = (
        f'format = "eg-ground-truth-v1"\ntenant = "halverson-freight"\n{questions}\n{anchors}{body}'
    )
    files = {"corpus.toml": corpus.encode(), _DOC: text.encode(), _GT: gt.encode()}
    if injected is not None:
        files[_INJECTED_DOC] = injected.encode()
    return files


def _anchor(name: str, quote: str, extra: str = "") -> str:
    return f'[[anchors]]\nref = "{_REF}#{name}"\nquote = {json.dumps(quote)}\n{extra}\n'


def _validation_code(files: dict[str, bytes], variant: str = "clean") -> str:
    with pytest.raises(EvaluationError) as raised:
        validate_suite(variant, files)
    return raised.value.code


def test_validate_suite_accepts_the_committed_corpus_in_both_variants() -> None:
    root = Path(__file__).resolve().parents[1] / "sample_data"
    files = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    for variant in ("clean", "injected"):
        suite = validate_suite(variant, files)
        spans = offline_spans(suite)
        assert len(suite.anchors) == 17
        for ref, value in suite.anchors.items():
            assert chunk_set(resolve_anchor(value, suite.texts[ref.revision], spans[ref.revision]))
        assert revalidate(suite) == suite


@pytest.mark.parametrize(
    ("text", "anchor", "code"),
    [
        ("Old term.\n", _anchor("a", "Missing term."), "anchor_not_found"),
        ("Old term. Old term.\n", _anchor("a", "Old term."), "anchor_ambiguous"),
        (
            "Old term. Old term.\n",
            _anchor("a", "Old term.", "occurrence = 3"),
            "anchor_occurrence_out_of_range",
        ),
        (
            "A" * 2000 + " end.\n\nStart. " + "B" * 2000 + "\n",
            _anchor("a", "end.\n\nStart."),
            "anchor_crosses_chunk_boundary",
        ),
        (
            "A" * 2000 + " end.\n\nStart. " + "B" * 2000 + "\n",
            _anchor("a", "end.\n\nStart.", 'parts = [{ quote = "end" }, { quote = "Start." }]'),
            "anchor_parts_gap",
        ),
        (
            "One sentence. Two sentences.\n",
            _anchor(
                "a", "One sentence. Two", 'parts = [{ quote = "One sentence." }, { quote = "Two" }]'
            ),
            "anchor_parts_unnecessary",
        ),
    ],
    ids=["missing", "ambiguous", "occurrence", "crosses", "parts-gap", "parts-unnecessary"],
)
def test_validate_suite_rejects_unresolvable_anchors(text: str, anchor: str, code: str) -> None:
    files = _mini(text, anchor)
    build_suite("clean", files)  # schema-valid: only the complete validation finds the problem
    assert _validation_code(files) == code


def test_validate_suite_checks_anchors_used_only_as_forbidden_or_unused() -> None:
    forbidden = _mini("Old term.\n", _anchor("a", "Absent."), forbidden="a")
    assert _validation_code(forbidden) == "anchor_not_found"
    unused = _mini("Old term.\n", _anchor("a", "Old term.") + _anchor("b", "Absent."))
    assert _validation_code(unused) == "anchor_not_found"


def test_validate_suite_uses_the_selected_variants_text() -> None:
    clean_text = "First.\n\nSecond.\n"
    injected_text = "First.\n\nInjected paragraph.\n\nSecond.\n"
    files = _mini(clean_text, _anchor("a", "Injected paragraph."), injected=injected_text)
    assert _validation_code(files, "clean") == "anchor_not_found"
    assert validate_suite("injected", files).variant == "injected"


def test_revalidate_rejects_a_tampered_suite() -> None:
    suite = validate_suite("clean", _mini("Old term.\n", _anchor("a", "Old term.")))
    ref = next(iter(suite.texts))
    with pytest.raises(EvaluationError) as raised:
        revalidate(replace(suite, texts={ref: "Other term.\n"}))
    assert raised.value.code == "corpus_invalid"
