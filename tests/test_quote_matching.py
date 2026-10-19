"""Segment-wise NFD quote matching (``evidenceguard_domain.provenance.match_quote``, M5b,
ADR-0020), without a database or network.

Expected offsets, originals and counts below are written by hand from the accepted rules
(``docs/plan.md`` M5b-C and M5b-C1), not computed by the module under test. The rule is
deliberately limited: it is **not** Unicode canonical equivalence, and the pinned limitation
tests below record where canonically equivalent spellings match differently.
"""

import dataclasses
import hashlib
import socket
import sys
import unicodedata
from typing import Any
from uuid import UUID

import pytest

from evidenceguard_domain.evidence import Authenticity, Citation, SourceType
from evidenceguard_domain.provenance import (
    MATCH_RULES,
    InvalidProvenanceInputError,
    InvalidProvenanceValueError,
    QuoteMatch,
    QuoteSpanKind,
    RejectionReason,
    match_quote,
)
from evidenceguard_domain.retrieval import ChunkEvidence, SourceSpan

CHUNK = UUID(int=1)
HEADER_SOURCE = 10
BODY_SOURCE = 100
CANARY = "CANARY-QUOTE-5K2"

R = RejectionReason
BODY = QuoteSpanKind.BODY
HEADER = QuoteSpanKind.HEADER


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("a test attempted network access")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


def chunk(body: str, header: str | None = None) -> ChunkEvidence:
    text = body if header is None else header + body
    header_span = (
        None if header is None else SourceSpan(1, 1, HEADER_SOURCE, HEADER_SOURCE + len(header))
    )
    return ChunkEvidence(
        CHUNK,
        text,
        hashlib.sha256(text.encode("utf-8")).hexdigest(),
        0,
        ("Controls",),
        header is not None,
        SourceSpan(3, 9, BODY_SOURCE, BODY_SOURCE + len(body)),
        header_span,
        "security-controls",
        "Security Controls",
        1,
        None,
        None,
        SourceType.VENDOR_STATEMENT,
        Authenticity.NOT_ESTABLISHED,
    )


def body_match(start: int, end: int, quote: str, occurrences: int = 1) -> QuoteMatch:
    """Expected body match in a chunk without a header."""
    return QuoteMatch(
        kind=BODY,
        text_start=start,
        text_end=end,
        source_char_start=BODY_SOURCE + start,
        source_char_end=BODY_SOURCE + end,
        quote=quote,
        occurrences=occurrences,
    )


# --- environment pins --------------------------------------------------------------------------


def test_match_rules_identifier() -> None:
    assert MATCH_RULES == "eg-quote-match-v1"


def test_unicode_data_version_is_pinned() -> None:
    """Matching depends on the interpreter's Unicode tables; an upgrade must be deliberate."""
    assert sys.version_info[:2] == (3, 12)
    assert unicodedata.unidata_version == "15.0.0"


def test_maximum_nfd_expansion_over_the_code_space() -> None:
    longest = max(
        len(unicodedata.normalize("NFD", chr(code)))
        for code in range(0x110000)
        if not 0xD800 <= code <= 0xDFFF
    )
    assert longest == 4


# --- whitespace ----------------------------------------------------------------------------------


def test_reflowed_whitespace_matches_and_stores_the_original() -> None:
    body = "Data is encrypted\n  at rest."
    assert match_quote(chunk(body), "Data is encrypted at rest.") == body_match(0, 28, body)


@pytest.mark.parametrize("space", ["\t", "\r\n", "\xa0", "\u2028", "\u3000", " \n\t "])
def test_whitespace_runs_collapse(space: str) -> None:
    body = f"alpha{space}bravo charlie"
    end = 10 + len(space)
    assert match_quote(chunk(body), "alpha bravo") == body_match(0, end, f"alpha{space}bravo")


def test_quote_edges_are_ignored() -> None:
    assert match_quote(chunk("alpha bravo"), " \n alpha  bravo\t ") == body_match(
        0, 11, "alpha bravo"
    )


@pytest.mark.parametrize("quote", [" ", "   ", "\n\t", "\u3000"])
def test_whitespace_only_quote_is_blank(quote: str) -> None:
    assert match_quote(chunk("alpha bravo"), quote) is R.QUOTE_BLANK


def test_a_match_never_ends_inside_a_whitespace_run() -> None:
    # The quote "a b" ends at a unit boundary; "a b " would need the run to be split.
    assert match_quote(chunk("a  b"), "a b") == body_match(0, 4, "a  b")


# --- common Latin and complete Hangul ----------------------------------------------------------


def test_precomposed_quote_matches_decomposed_evidence() -> None:
    body = "cafe\u0301 menu"
    assert match_quote(chunk(body), "caf\xe9") == body_match(0, 5, "cafe\u0301")


def test_decomposed_quote_matches_precomposed_evidence() -> None:
    body = "caf\xe9 menu"
    assert match_quote(chunk(body), "cafe\u0301") == body_match(0, 4, "caf\xe9")


def test_marks_in_another_canonical_order_within_one_segment() -> None:
    body = "xq\u0323\u0307 y"
    assert match_quote(chunk(body), "xq\u0307\u0323") == body_match(0, 4, "xq\u0323\u0307")


def test_a_quote_without_the_mark_is_not_found() -> None:
    assert match_quote(chunk("caf\xe9"), "cafe") is R.QUOTE_NOT_FOUND
    assert match_quote(chunk("cafe\u0301"), "cafe") is R.QUOTE_NOT_FOUND
    assert match_quote(chunk("na\xefve"), "nai") is R.QUOTE_NOT_FOUND
    assert match_quote(chunk("nai\u0308ve"), "nai") is R.QUOTE_NOT_FOUND
    assert match_quote(chunk("nai\u0308ve"), "na") == body_match(0, 2, "na")


def test_complete_hangul_syllable_matches_both_spellings() -> None:
    assert match_quote(chunk("\uac01 x"), "\u1100\u1161\u11a8") == body_match(0, 1, "\uac01")
    assert match_quote(chunk("\u1100\u1161\u11a8 x"), "\uac01") == body_match(
        0, 3, "\u1100\u1161\u11a8"
    )


def test_supplementary_characters_use_code_point_offsets() -> None:
    body = "key \U0001d504 rotated \U0001f510 yearly"
    quote = "\U0001d504 rotated \U0001f510"
    assert match_quote(chunk(body), quote) == body_match(4, 15, quote)


@pytest.mark.parametrize(
    ("body", "quote"),
    [
        ("\ufb01le", "file"),  # ligature: no compatibility folding
        ("\uff21\uff22\uff23", "ABC"),  # full-width forms
        ("x\xb2", "x2"),  # superscript
        ("MFA enabled", "mfa enabled"),  # no case folding
        ("\u201cquoted\u201d", '"quoted"'),  # no quotation-mark folding
        ("2020\u20132026", "2020-2026"),  # no dash folding
        ("pass\u200bword", "password"),  # zero-width space kept
        ("pass\xadword", "password"),  # soft hyphen kept
        ("wait\u2026", "wait..."),  # no ellipsis folding
        ("alpha bravo charlie", "alpha ... charlie"),  # no matching across elided text
    ],
)
def test_no_other_folding(body: str, quote: str) -> None:
    assert match_quote(chunk(body), quote) is R.QUOTE_NOT_FOUND


def test_literal_ellipsis_matches_only_itself() -> None:
    body = "wait\u2026 then"
    assert match_quote(chunk(body), "wait\u2026") == body_match(0, 5, "wait\u2026")


# --- disclosed limitations (M5b-C1) ------------------------------------------------------------


def test_tibetan_reordering_across_segments_does_not_match() -> None:
    """U+0F73 is a starter that decomposes to non-starters, so the canonically equivalent
    spellings have different segment-wise keys and do not match in either direction."""
    original = "\u0f40\u0f74\u0f73"
    full_nfd = "\u0f40\u0f71\u0f72\u0f74"
    assert unicodedata.normalize("NFD", original) == full_nfd
    assert match_quote(chunk(original), full_nfd) is R.QUOTE_NOT_FOUND
    assert match_quote(chunk(full_nfd), original) is R.QUOTE_NOT_FOUND
    # each spelling still matches itself
    assert match_quote(chunk(original), original) == body_match(0, 3, original)


def test_partial_hangul_syllable_depends_on_the_evidence_spelling() -> None:
    assert match_quote(chunk("\uac01"), "\uac00") is R.QUOTE_NOT_FOUND
    assert match_quote(chunk("\u1100\u1161\u11a8"), "\uac00") == body_match(0, 2, "\u1100\u1161")


def test_an_initial_run_of_non_starters_is_one_segment() -> None:
    """Both the span and the quote begin with U+0323 U+0307 (in different orders). As one
    segment, each run is reordered by NFD and the keys agree; one segment per non-starter would
    not match."""
    body = "\u0323\u0307x rest"
    assert match_quote(chunk(body), "\u0307\u0323x") == body_match(0, 3, "\u0323\u0307x")
    # a quote starting inside that initial unit is not found
    assert match_quote(chunk(body), "\u0307x") is R.QUOTE_NOT_FOUND


# --- header and body ---------------------------------------------------------------------------

HEADER_TEXT = "| Control | Status |"  # 20 code points
BODY_TEXT = "| MFA | On |"


def test_header_and_body_offsets() -> None:
    evidence = chunk(BODY_TEXT, HEADER_TEXT)
    assert match_quote(evidence, "Status |") == QuoteMatch(
        kind=HEADER,
        text_start=12,
        text_end=20,
        source_char_start=HEADER_SOURCE + 12,
        source_char_end=HEADER_SOURCE + 20,
        quote="Status |",
        occurrences=1,
    )
    assert match_quote(evidence, "MFA") == QuoteMatch(
        kind=BODY,
        text_start=22,
        text_end=25,
        source_char_start=BODY_SOURCE + 2,
        source_char_end=BODY_SOURCE + 5,
        quote="MFA",
        occurrences=1,
    )


def test_offsets_select_the_quote_in_text_and_source() -> None:
    evidence = chunk(BODY_TEXT, HEADER_TEXT)
    source = (
        " " * HEADER_SOURCE + HEADER_TEXT + " " * (BODY_SOURCE - HEADER_SOURCE - 20) + BODY_TEXT
    )
    for quote in ("Control", "Status |", "MFA", "| On |"):
        found = match_quote(evidence, quote)
        assert isinstance(found, QuoteMatch)
        assert evidence.text[found.text_start : found.text_end] == quote
        assert source[found.source_char_start : found.source_char_end] == quote


def test_a_quote_across_the_header_body_boundary_is_not_found() -> None:
    evidence = chunk(BODY_TEXT, HEADER_TEXT)
    assert "Status || MFA" in evidence.text
    assert match_quote(evidence, "Status || MFA") is R.QUOTE_NOT_FOUND
    assert match_quote(evidence, "Status | | MFA") is R.QUOTE_NOT_FOUND


def test_header_occurrence_comes_first() -> None:
    evidence = chunk("| MFA | Status |", HEADER_TEXT)
    found = match_quote(evidence, "Status |")
    assert isinstance(found, QuoteMatch)
    assert (found.kind, found.text_start, found.occurrences) == (HEADER, 12, 2)


def test_non_table_chunk_has_only_a_body_span() -> None:
    found = match_quote(chunk("alpha bravo"), "bravo")
    assert found == body_match(6, 11, "bravo")


# --- repetition, overlap, cap and selection ----------------------------------------------------


def test_first_occurrence_original_is_stored() -> None:
    body = "rotated yearly. rotated\nyearly."
    assert match_quote(chunk(body), "rotated yearly") == body_match(0, 14, "rotated yearly", 2)
    body = "rotated\nyearly. rotated yearly."
    assert match_quote(chunk(body), "rotated yearly") == body_match(0, 14, "rotated\nyearly", 2)


def test_overlapping_occurrences_count() -> None:
    assert match_quote(chunk("aaaa"), "aa") == body_match(0, 2, "aa", 3)


def test_occurrence_count_is_capped_at_64() -> None:
    found = match_quote(chunk("ab " * 100), "ab")
    assert found == body_match(0, 2, "ab", 64)


def test_no_fallback_to_a_later_occurrence() -> None:
    """The first occurrence's original is 1,200 code points (decomposed); the later precomposed
    occurrence would fit, but only the first is checked."""
    body = "e\u0301" * 600 + " " + "\xe9" * 600
    assert match_quote(chunk(body), "\xe9" * 600) is R.QUOTE_TOO_LONG


def test_original_length_bound() -> None:
    accepted = "e\u0301" * 499 + "xy"  # 1,000 code points
    found = match_quote(chunk(accepted), "\xe9" * 499 + "xy")
    assert found == body_match(0, 1000, accepted)
    too_long = "e\u0301" * 500 + "x"  # 1,001 code points
    assert match_quote(chunk(too_long), "\xe9" * 500 + "x") is R.QUOTE_TOO_LONG


def test_degenerate_edge_unit_is_not_exact() -> None:
    """A space carrying a combining mark is one non-whitespace unit; its original starts with
    whitespace, so it cannot be stored exactly."""
    assert match_quote(chunk("a \u0301b"), " \u0301b") is R.QUOTE_NOT_EXACT


def test_maximum_sizes() -> None:
    body = "x" * 3990 + " tail word"
    assert len(body) == 4000
    assert match_quote(chunk(body), "tail word") == body_match(3991, 4000, "tail word")
    quote = "y" * 1000
    assert match_quote(chunk("a " + quote), quote) == body_match(2, 1002, quote)


def test_reason_order_blank_before_not_found() -> None:
    assert match_quote(chunk("alpha"), "  ") is R.QUOTE_BLANK
    assert match_quote(chunk("alpha"), "omega") is R.QUOTE_NOT_FOUND


# --- Citation round trip -----------------------------------------------------------------------


def test_citation_strips_edges_so_originals_never_have_them() -> None:
    def cite(quote: str) -> Citation:
        return Citation(
            tenant_id=UUID(int=7),
            document_revision_id=UUID(int=8),
            chunk_id=CHUNK,
            source_type=SourceType.VENDOR_STATEMENT,
            quote=quote,
        )

    assert cite(" edge ").quote == "edge"  # the M1 contract strips
    found = match_quote(chunk("Data is encrypted\n  at rest."), "encrypted at rest")
    assert isinstance(found, QuoteMatch)
    assert found.quote == "encrypted\n  at rest"
    assert cite(found.quote).quote == found.quote


# --- inputs --------------------------------------------------------------------------------------


class _Text(str):
    pass


@pytest.mark.parametrize(
    "quote",
    ["", "x" * 1001, "a\x00b", "a\ud800b", b"alpha", None, 7, _Text("alpha")],
)
def test_invalid_quote_raises(quote: Any) -> None:
    with pytest.raises(InvalidProvenanceInputError) as raised:
        match_quote(chunk("alpha"), quote)
    assert str(raised.value) == "invalid_provenance_input"
    assert raised.value.__cause__ is None and raised.value.__context__ is None


def test_invalid_evidence_raises() -> None:
    evidence = chunk("alpha")
    with pytest.raises(InvalidProvenanceInputError):
        match_quote("alpha", "alpha")  # type: ignore[arg-type]
    bypassed = chunk("alpha")
    object.__setattr__(bypassed, "text", "omega")  # digest no longer matches
    with pytest.raises(InvalidProvenanceInputError):
        match_quote(bypassed, "omega")
    assert isinstance(match_quote(evidence, "alpha"), QuoteMatch)


# --- QuoteMatch values ---------------------------------------------------------------------------

VALID: dict[str, Any] = {
    "kind": BODY,
    "text_start": 2,
    "text_end": 7,
    "source_char_start": 102,
    "source_char_end": 107,
    "quote": "alpha",
    "occurrences": 1,
}


def test_quote_match_accepts_valid_bounds() -> None:
    assert QuoteMatch(**VALID).quote == "alpha"
    assert QuoteMatch(**{**VALID, "occurrences": 64}).occurrences == 64
    edge = {**VALID, "text_start": 3995, "text_end": 4000}
    assert QuoteMatch(**edge).text_end == 4000


@pytest.mark.parametrize(
    "change",
    [
        {"kind": "body"},
        {"text_start": True},
        {"text_start": -1},
        {"text_end": 2},
        {"text_end": 8},
        {"text_start": 3996, "text_end": 4001, "source_char_end": 107},
        {"source_char_start": -1, "source_char_end": 4},
        {"source_char_end": 108},
        {"source_char_start": 102.0},
        {"quote": " alph", "text_end": 7},
        {"quote": "alph\n", "text_end": 7},
        {"quote": "al\x00ha"},
        {"quote": "x" * 1001, "text_end": 1003, "source_char_end": 1103},
        {"occurrences": 0},
        {"occurrences": 65},
        {"occurrences": False},
        {"extra": 1},
    ],
)
def test_quote_match_rejects_invalid_values(change: dict[str, Any]) -> None:
    with pytest.raises(InvalidProvenanceValueError) as raised:
        QuoteMatch(**{**VALID, **change})
    assert raised.value.__cause__ is None and raised.value.__context__ is None


def test_quote_match_replace_revalidates_and_is_frozen() -> None:
    value = QuoteMatch(**VALID)
    assert dataclasses.replace(value, occurrences=3).occurrences == 3
    with pytest.raises(InvalidProvenanceValueError):
        dataclasses.replace(value, text_end=9)
    with pytest.raises(dataclasses.FrozenInstanceError):
        value.quote = "beta"  # type: ignore[misc]


def test_quote_match_representation_has_no_quote_text() -> None:
    value = QuoteMatch(**{**VALID, "quote": "CANARY", "text_end": 8, "source_char_end": 108})
    for text in (repr(value), str(value)):
        assert "CANARY" not in text
        assert "text=2-8" in text and "occurrences=1" in text


# --- errors, privacy and process control -----------------------------------------------------


SENTINEL = "\u2603"  # the patched normalizer misbehaves only for this one segment
_NORMALIZE = unicodedata.normalize


def test_normalization_failure_becomes_a_fixed_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(form: Any, text: str) -> str:
        if text == SENTINEL:
            raise RuntimeError(CANARY)
        return _NORMALIZE(form, text)

    monkeypatch.setattr(unicodedata, "normalize", broken)
    with pytest.raises(InvalidProvenanceInputError) as raised:
        match_quote(chunk(f"alpha {SENTINEL}"), "alpha")
    assert CANARY not in str(raised.value) and CANARY not in repr(raised.value)
    assert raised.value.__cause__ is None and raised.value.__context__ is None


@pytest.mark.parametrize("control", [KeyboardInterrupt(), SystemExit(3), GeneratorExit()])
def test_process_control_propagates_unchanged(
    monkeypatch: pytest.MonkeyPatch, control: BaseException
) -> None:
    def interrupt(form: Any, text: str) -> str:
        if text == SENTINEL:
            raise control
        return _NORMALIZE(form, text)

    monkeypatch.setattr(unicodedata, "normalize", interrupt)
    with pytest.raises(BaseException) as raised:
        match_quote(chunk(f"alpha {SENTINEL}"), "alpha")
    assert raised.value is control


def test_matching_logs_nothing(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("DEBUG"):
        match_quote(chunk(f"{CANARY} body"), CANARY)
        match_quote(chunk("body"), CANARY)
    assert caplog.records == []
