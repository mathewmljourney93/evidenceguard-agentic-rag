"""Provenance checks, quote matching and status derivation (M5b, ADR-0020).

Pure values and functions, standard library and domain only: no persistence, network, prompts,
orchestration or provider calls. This module implements the M5b specification accepted in Prompt
176 (``docs/plan.md``, M5b-B1 to M5b-F and P1-P16).

What a check here proves, and what it does not
----------------------------------------------
An accepted citation proves **provenance only**: the stored quote is an exact, contiguous substring
of one span of a chunk in the trusted retrieval result supplied for that question, with exact
chunk-text and source offsets, and its tenant, revision, source type and authenticity come from
that evidence. It does not prove that the passage supports the claim (semantic entailment is a
model judgment, measured in M7), that the document is authentic (always ``not_established``), or
that the retrieval result was really retrieved for this review and question (M5d/M5g supply it
from trusted paths). Nothing here resists malicious trusted Python or direct database writes.

Quote matching (``eg-quote-match-v1``)
--------------------------------------
**Segment-wise NFD matching**, a deliberately limited rule; it is **not** Unicode canonical
equivalence. Header and body spans are matched separately. A *segment* is a starter (canonical
combining class 0) followed by the non-starters after it; an initial run of non-starters is one
segment. Each maximal run of single-code-point whitespace segments is one unit with key ``" "``;
every other segment is one unit keyed by its NFD form. A match must start and end on unit
boundaries; the first occurrence (header before body) is selected without fallback, and
occurrences are counted up to 64. Canonically equivalent spellings can match differently (for
example Tibetan U+0F73 across segments, and partial Hangul syllables); see ADR-0020.

Errors and privacy
------------------
Every public operation (constructors, ``dataclasses.replace`` and functions) runs as one guarded
operation: any ordinary failure becomes a fresh ``InvalidProvenanceValueError`` (values) or
``InvalidProvenanceInputError`` (functions), raised after leaving the handler so no cause, context
or text is retained. Process control propagates as the same object. Model-caused failures never
raise; they return a text-free ``ProvenanceRejection`` or, from ``match_quote``, a
``RejectionReason``. ``repr``/``str`` show identifiers, reasons, offsets, counts and digests only.
Nothing here logs.
"""

import re
import unicodedata
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar
from uuid import UUID, uuid5

from evidenceguard_domain.agent_outputs import (
    AnalystOutput,
    FindingOutput,
    QuoteRef,
    VerifierOutput,
)
from evidenceguard_domain.chunks import MAX_CHUNK_CHARS
from evidenceguard_domain.evidence import (
    Authenticity,
    Citation,
    EvidenceQuestion,
    EvidenceStatus,
    Finding,
    Severity,
    SourceType,
    Verdict,
    Verification,
)
from evidenceguard_domain.model_calls import (
    CallOutcome,
    ModelPurpose,
    StructuredResult,
    is_question_id,
    utf8_size,
)
from evidenceguard_domain.retrieval import (
    ChunkEvidence,
    RetrievalResult,
    RetrievedChunk,
)

MATCH_RULES = "eg-quote-match-v1"
MAX_QUOTE_CHARS = 1_000
MAX_OCCURRENCES = 64
MAX_CLAIMS = 10
MAX_CLAIM_TEXT_CHARS = 1_000
MAX_REFERENCES_PER_ITEM = 8
MAX_QUESTION_CITATIONS = MAX_CLAIMS * MAX_REFERENCES_PER_ITEM
MAX_FINDINGS = 20
MAX_FOLLOW_UPS = 5
MAX_FOLLOW_UP_CHARS = 500
MAX_SHARED_QUESTIONS = 19

FINDING_ID_NAMESPACE = UUID("56b13512-9167-5c9e-95c5-c6915da4cba6")
"""``uuid5(NAMESPACE_URL, "https://evidenceguard.invalid/namespaces/finding-id/v1")``, fixed."""

DOCUMENTARY_GAP_TITLE = "Documentary evidence required"
DOCUMENTARY_GAP_STATEMENT = (
    "Only vendor statements support this answer; the question requires a contract or "
    "third-party report."
)
DOCUMENTARY_GAP_SEVERITY = Severity.MEDIUM

_SHA256 = re.compile(r"[0-9a-f]{64}", re.ASCII)


# --- errors (fixed messages: the message is the code) ------------------------------------------


class ProvenanceError(Exception):
    """Base of the fixed M5b errors. Never carries submitted values, content or causes."""

    code: ClassVar[str] = "provenance_error"

    def __init__(self) -> None:
        super().__init__(self.code)


class InvalidProvenanceInputError(ProvenanceError):
    """Bad caller or trusted input to an M5b function, including a failed reload check."""

    code = "invalid_provenance_input"


class InvalidProvenanceValueError(ProvenanceError):
    """An invalid M5b value, or an internal inconsistency that should be unreachable."""

    code = "invalid_provenance_value"


class _Invalid(Exception):
    """Private: a failed check inside a guarded operation (never escapes the module)."""


class _Internal(Exception):
    """Private: an internal inconsistency, reported as ``InvalidProvenanceValueError``."""


def _require(condition: bool) -> None:
    if not condition:
        raise _Invalid


def _run[T](build: Callable[[], T], error: type[ProvenanceError]) -> T:
    """Run one whole public operation. Any ordinary failure becomes a fresh ``error`` (or
    ``InvalidProvenanceValueError`` for an internal inconsistency), raised after leaving the
    handler so no cause or context is retained. Only ``Exception`` is caught; process control
    propagates as the same object. Exception chains are never inspected."""
    built: list[T] = []
    internal = False
    try:
        built.append(build())
    except _Internal:
        internal = True
    except Exception:  # translated into a fixed error below
        pass
    if not built:
        raise (InvalidProvenanceValueError if internal else error)()
    return built[0]


def _internal[T](make: Callable[[], T]) -> T:
    """Build a value that must always be valid here; failure is an internal inconsistency."""
    built: list[T] = []
    with suppress(Exception):
        built.append(make())
    if not built:
        raise _Internal
    return built[0]


# --- enums ----------------------------------------------------------------------------------------


class QuoteSpanKind(StrEnum):
    HEADER = "header"
    BODY = "body"


class FindingKind(StrEnum):
    ANALYST = "analyst"
    DOCUMENTARY_SUPPORT_REQUIRED = "documentary_support_required"


class RejectionStage(StrEnum):
    VERIFICATION = "verification"
    ANALYSIS = "analysis"


class RejectionReason(StrEnum):
    # verification, phase 1 (references), in precedence order
    CHUNK_NOT_RETRIEVED = "chunk_not_retrieved"
    QUOTE_BLANK = "quote_blank"
    QUOTE_NOT_FOUND = "quote_not_found"
    QUOTE_TOO_LONG = "quote_too_long"
    QUOTE_NOT_EXACT = "quote_not_exact"
    # verification, phase 2 (claim coverage)
    CLAIM_UNCITED = "claim_uncited"
    # verification, phase 3 (aggregate), in precedence order
    VERDICT_UNSUPPORTED = "verdict_unsupported"
    RATIONALE_BLANK = "rationale_blank"
    # analysis (per finding), in precedence order
    FOREIGN_QUESTION = "foreign_question"
    CITATION_NOT_VALIDATED = "citation_not_validated"
    CITATION_NOT_SHARED = "citation_not_shared"
    MIXED_VERDICTS = "mixed_verdicts"
    FINDING_STATUS_UNSUPPORTED = "finding_status_unsupported"
    FINDING_TEXT_BLANK = "finding_text_blank"


_PHASE_1 = frozenset(
    {
        RejectionReason.CHUNK_NOT_RETRIEVED,
        RejectionReason.QUOTE_BLANK,
        RejectionReason.QUOTE_NOT_FOUND,
        RejectionReason.QUOTE_TOO_LONG,
        RejectionReason.QUOTE_NOT_EXACT,
    }
)
_PHASE_3 = frozenset({RejectionReason.VERDICT_UNSUPPORTED, RejectionReason.RATIONALE_BLANK})
_ANALYSIS = frozenset(
    {
        RejectionReason.FOREIGN_QUESTION,
        RejectionReason.CITATION_NOT_VALIDATED,
        RejectionReason.CITATION_NOT_SHARED,
        RejectionReason.MIXED_VERDICTS,
        RejectionReason.FINDING_STATUS_UNSUPPORTED,
        RejectionReason.FINDING_TEXT_BLANK,
    }
)
_CITATION_REASONS = frozenset(
    {RejectionReason.CITATION_NOT_VALIDATED, RejectionReason.CITATION_NOT_SHARED}
)
_MATCH_REASONS = (
    RejectionReason.QUOTE_BLANK,
    RejectionReason.QUOTE_NOT_FOUND,
    RejectionReason.QUOTE_TOO_LONG,
    RejectionReason.QUOTE_NOT_EXACT,
)


# --- small checks ---------------------------------------------------------------------------------


def _is_int(value: object, low: int, high: int) -> bool:
    return type(value) is int and low <= value <= high


def _is_uuid(value: object) -> bool:
    return type(value) is UUID


def _is_sha256(value: object) -> bool:
    return type(value) is str and _SHA256.fullmatch(value) is not None


def _is_plain(value: object, low: int, high: int) -> bool:
    """Exactly a ``str`` of ``low``-``high`` code points, without NUL or lone surrogates."""
    return (
        type(value) is str
        and low <= len(value) <= high
        and "\x00" not in value
        and utf8_size(value) is not None
    )


def _rebuilt_citation(value: object) -> Citation:
    _require(type(value) is Citation)
    assert isinstance(value, Citation)
    return value.model_copy()


def _rebuilt_question(value: object) -> EvidenceQuestion:
    _require(type(value) is EvidenceQuestion)
    assert isinstance(value, EvidenceQuestion)
    return value.model_copy()


def _rebuilt_evidence(value: object) -> ChunkEvidence:
    _require(type(value) is ChunkEvidence)
    assert isinstance(value, ChunkEvidence)
    return ChunkEvidence(
        value.chunk_id,
        value.text,
        value.content_sha256,
        value.ordinal,
        value.section_path,
        value.is_table,
        value.body,
        value.header,
        value.document_key,
        value.title,
        value.revision_no,
        value.version_label,
        value.effective_date,
        value.source_type,
        value.authenticity,
    )


def _rebuilt_result(value: object) -> RetrievalResult:
    _require(type(value) is RetrievalResult)
    assert isinstance(value, RetrievalResult)
    return RetrievalResult(
        value.snapshot, value.query_count, value.k, value.vector_skipped, value.items
    )


def _rebuilt_call(value: object, purpose: ModelPurpose) -> StructuredResult:
    _require(type(value) is StructuredResult)
    assert isinstance(value, StructuredResult)
    rebuilt = StructuredResult(
        request_sha256=value.request_sha256,
        purpose=value.purpose,
        question_id=value.question_id,
        outcome=value.outcome,
        dispatched=value.dispatched,
        output=value.output,
        model_requested=value.model_requested,
        model_used=value.model_used,
        usage=value.usage,
        latency_ms=value.latency_ms,
    )
    _require(rebuilt.outcome is CallOutcome.COMPLETED and rebuilt.purpose is purpose)
    return rebuilt


# --- quote matching -------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Form:
    """A span's or quote's units: the concatenated keys and the unit boundaries in both the
    key string and the original text. Transient; never returned, stored or logged."""

    keys: str
    unit_keys: tuple[str, ...]  # unit index -> key
    key_starts: dict[int, int]  # key offset -> unit index
    key_ends: dict[int, int]  # key end offset -> unit index
    starts: tuple[int, ...]  # unit index -> original start
    ends: tuple[int, ...]  # unit index -> original end
    spaces: tuple[bool, ...]  # unit index -> whitespace unit


def _segments(text: str) -> list[tuple[int, int]]:
    """Split before every starter; an initial run of non-starters is one segment."""
    bounds: list[tuple[int, int]] = []
    start = 0
    for index in range(1, len(text)):
        if unicodedata.combining(text[index]) == 0:
            bounds.append((start, index))
            start = index
    if text:
        bounds.append((start, len(text)))
    return bounds


def _form(text: str) -> _Form:
    keys: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    spaces: list[bool] = []
    for start, end in _segments(text):
        segment = text[start:end]
        if end - start == 1 and segment.isspace():
            if spaces and spaces[-1]:
                ends[-1] = end
                continue
            keys.append(" ")
            spaces.append(True)
        else:
            keys.append(unicodedata.normalize("NFD", segment))
            spaces.append(False)
        starts.append(start)
        ends.append(end)
    key_starts: dict[int, int] = {}
    key_ends: dict[int, int] = {}
    offset = 0
    for unit, key in enumerate(keys):
        key_starts[offset] = unit
        offset += len(key)
        key_ends[offset] = unit
    return _Form(
        "".join(keys),
        tuple(keys),
        key_starts,
        key_ends,
        tuple(starts),
        tuple(ends),
        tuple(spaces),
    )


def _quote_key(quote: str) -> str:
    """The quote form ``Q``: unit keys without leading or trailing whitespace units ("" if
    nothing is left)."""
    form = _form(quote)
    first, last = 0, len(form.spaces)
    while first < last and form.spaces[first]:
        first += 1
    while last > first and form.spaces[last - 1]:
        last -= 1
    return "".join(form.unit_keys[first:last])


@dataclass(frozen=True, slots=True)
class _ChunkForms:
    evidence: ChunkEvidence
    spans: tuple[tuple[QuoteSpanKind, str, int, int, _Form], ...]  # kind, text, base, source, form


def _chunk_forms(evidence: ChunkEvidence) -> _ChunkForms:
    spans: list[tuple[QuoteSpanKind, str, int, int, _Form]] = []
    header_text = evidence.header_text
    if evidence.header is not None and header_text is not None:
        spans.append(
            (QuoteSpanKind.HEADER, header_text, 0, evidence.header.char_start, _form(header_text))
        )
    base = 0 if evidence.header is None else evidence.header.length
    body_text = evidence.body_text
    spans.append((QuoteSpanKind.BODY, body_text, base, evidence.body.char_start, _form(body_text)))
    return _ChunkForms(evidence, tuple(spans))


def _match(forms: _ChunkForms, quote: str) -> "QuoteMatch | RejectionReason":
    key = _quote_key(quote)
    if not key:
        return RejectionReason.QUOTE_BLANK
    found: list[tuple[QuoteSpanKind, str, int, int, int, int]] = []
    for kind, text, base, source, form in forms.spans:
        position = form.keys.find(key)
        while position != -1 and len(found) < MAX_OCCURRENCES:
            end = position + len(key)
            if position in form.key_starts and end in form.key_ends:
                first, last = form.key_starts[position], form.key_ends[end]
                found.append((kind, text, base, source, form.starts[first], form.ends[last]))
            position = form.keys.find(key, position + 1)
        if len(found) >= MAX_OCCURRENCES:
            break
    if not found:
        return RejectionReason.QUOTE_NOT_FOUND
    kind, text, base, source, start, end = found[0]  # the first occurrence; no fallback
    original = text[start:end]
    if len(original) > MAX_QUOTE_CHARS:
        return RejectionReason.QUOTE_TOO_LONG
    if original != original.strip():
        return RejectionReason.QUOTE_NOT_EXACT
    return QuoteMatch(
        kind=kind,
        text_start=base + start,
        text_end=base + end,
        source_char_start=source + start,
        source_char_end=source + end,
        quote=original,
        occurrences=len(found),
    )


@dataclass(frozen=True, init=False, repr=False)
class QuoteMatch:
    """The exact original quotation selected in one span of a chunk, and its offsets.

    ``text_start``/``text_end`` are code-point offsets in ``ChunkEvidence.text``;
    ``source_char_start``/``source_char_end`` in the revision text. ``occurrences`` counts the
    occurrences found in both spans, capped at 64.
    """

    kind: QuoteSpanKind
    text_start: int
    text_end: int
    source_char_start: int
    source_char_end: int
    quote: str
    occurrences: int

    def __init__(
        self,
        *,
        kind: QuoteSpanKind,
        text_start: int,
        text_end: int,
        source_char_start: int,
        source_char_end: int,
        quote: str,
        occurrences: int,
        **unknown: object,
    ) -> None:
        def build() -> None:
            _require(not unknown and type(kind) is QuoteSpanKind)
            _require(_is_int(text_start, 0, MAX_CHUNK_CHARS - 1))
            _require(_is_int(text_end, text_start + 1, MAX_CHUNK_CHARS))
            _require(type(source_char_start) is int and source_char_start >= 0)
            _require(type(source_char_end) is int)
            _require(_is_plain(quote, 1, MAX_QUOTE_CHARS) and quote == quote.strip())
            length = len(quote)
            _require(text_end - text_start == length)
            _require(source_char_end - source_char_start == length)
            _require(_is_int(occurrences, 1, MAX_OCCURRENCES))
            for name, value in (
                ("kind", kind),
                ("text_start", text_start),
                ("text_end", text_end),
                ("source_char_start", source_char_start),
                ("source_char_end", source_char_end),
                ("quote", quote),
                ("occurrences", occurrences),
            ):
                object.__setattr__(self, name, value)

        _run(build, InvalidProvenanceValueError)

    def __repr__(self) -> str:
        return (
            f"QuoteMatch(kind={self.kind.value!r}, text={self.text_start}-{self.text_end}, "
            f"source={self.source_char_start}-{self.source_char_end}, "
            f"occurrences={self.occurrences})"
        )

    __str__ = __repr__


def _rebuilt_match(value: object) -> QuoteMatch:
    _require(type(value) is QuoteMatch)
    assert isinstance(value, QuoteMatch)
    return QuoteMatch(
        kind=value.kind,
        text_start=value.text_start,
        text_end=value.text_end,
        source_char_start=value.source_char_start,
        source_char_end=value.source_char_end,
        quote=value.quote,
        occurrences=value.occurrences,
    )


def match_quote(evidence: ChunkEvidence, quote: str) -> QuoteMatch | RejectionReason:
    """Match ``quote`` in ``evidence`` under ``eg-quote-match-v1``.

    Returns a ``QuoteMatch`` or one of ``quote_blank``, ``quote_not_found``, ``quote_too_long``
    and ``quote_not_exact`` (checked in that order). An invalid ``evidence`` or a ``quote`` that
    is not a plain ``str`` of 1-1000 code points raises ``InvalidProvenanceInputError``.
    """

    def build() -> QuoteMatch | RejectionReason:
        checked = _rebuilt_evidence(evidence)
        _require(_is_plain(quote, 1, MAX_QUOTE_CHARS))
        return _match(_chunk_forms(checked), quote)

    return _run(build, InvalidProvenanceInputError)


# --- status derivation ----------------------------------------------------------------------------


def _derive(verdict: Verdict, citations: tuple[Citation, ...]) -> EvidenceStatus | None:
    if verdict is Verdict.INSUFFICIENT_EVIDENCE:
        return EvidenceStatus.MISSING
    if verdict is Verdict.SUPPORTED:
        if not citations:
            return None
        if all(c.source_type is SourceType.VENDOR_STATEMENT for c in citations):
            return EvidenceStatus.VENDOR_CLAIM
        return EvidenceStatus.DOCUMENTARY_SUPPORT
    if len({c.quote for c in citations}) >= 2:
        return EvidenceStatus.CONFLICTING
    return None


def derive_status(verdict: Verdict, citations: tuple[Citation, ...]) -> EvidenceStatus | None:
    """The accepted M5b-D status table: ``supported`` → ``vendor_claim`` (every citation a
    vendor statement) or ``documentary_support`` (at least one contract or third-party report),
    ``None`` without citations; ``contradicted`` → ``conflicting`` with at least two distinct
    quote texts, otherwise ``None``; ``insufficient_evidence`` → ``missing``."""

    def build() -> EvidenceStatus | None:
        _require(type(verdict) is Verdict and type(citations) is tuple)
        return _derive(verdict, tuple(_rebuilt_citation(c) for c in citations))

    return _run(build, InvalidProvenanceInputError)


# --- trusted inputs and accepted values -----------------------------------------------------------


@dataclass(frozen=True, init=False, repr=False)
class QuestionEvidence:
    """The trusted inputs for one question: tenant, review, snapshot digest, the planned
    question and the retrieval result M5g obtained for it. Construction checks consistency
    only; it cannot prove the result was retrieved for this question."""

    tenant_id: UUID
    review_id: UUID
    snapshot_sha256: str
    question: EvidenceQuestion
    result: RetrievalResult

    def __init__(
        self,
        *,
        tenant_id: UUID,
        review_id: UUID,
        snapshot_sha256: str,
        question: EvidenceQuestion,
        result: RetrievalResult,
        **unknown: object,
    ) -> None:
        def build() -> None:
            _require(not unknown and _is_uuid(tenant_id) and _is_uuid(review_id))
            _require(_is_sha256(snapshot_sha256))
            checked_question = _rebuilt_question(question)
            checked_result = _rebuilt_result(result)
            _require(checked_result.tenant_id == tenant_id)
            _require(checked_result.snapshot_sha256 == snapshot_sha256)
            object.__setattr__(self, "tenant_id", tenant_id)
            object.__setattr__(self, "review_id", review_id)
            object.__setattr__(self, "snapshot_sha256", snapshot_sha256)
            object.__setattr__(self, "question", checked_question)
            object.__setattr__(self, "result", checked_result)

        _run(build, InvalidProvenanceValueError)

    def __repr__(self) -> str:
        return (
            f"QuestionEvidence(review_id={self.review_id}, "
            f"question_id={self.question.question_id!r}, items={len(self.result.items)}, "
            f"snapshot_sha256={self.snapshot_sha256!r})"
        )

    __str__ = __repr__


def _rebuilt_question_evidence(value: object) -> QuestionEvidence:
    _require(type(value) is QuestionEvidence)
    assert isinstance(value, QuestionEvidence)
    return QuestionEvidence(
        tenant_id=value.tenant_id,
        review_id=value.review_id,
        snapshot_sha256=value.snapshot_sha256,
        question=value.question,
        result=value.result,
    )


@dataclass(frozen=True, init=False, repr=False)
class AcceptedCitation:
    """An accepted ``Citation``, the document it belongs to and the exact match behind it."""

    citation: Citation
    document_id: UUID
    match: QuoteMatch

    def __init__(
        self, *, citation: Citation, document_id: UUID, match: QuoteMatch, **unknown: object
    ) -> None:
        def build() -> None:
            _require(not unknown and _is_uuid(document_id))
            checked_citation = _rebuilt_citation(citation)
            checked_match = _rebuilt_match(match)
            _require(checked_match.quote == checked_citation.quote)
            _require(checked_citation.authenticity is Authenticity.NOT_ESTABLISHED)
            object.__setattr__(self, "citation", checked_citation)
            object.__setattr__(self, "document_id", document_id)
            object.__setattr__(self, "match", checked_match)

        _run(build, InvalidProvenanceValueError)

    def __repr__(self) -> str:
        return (
            f"AcceptedCitation(chunk_id={self.citation.chunk_id}, "
            f"document_id={self.document_id}, match={self.match!r})"
        )

    __str__ = __repr__


def _rebuilt_accepted(value: object) -> AcceptedCitation:
    _require(type(value) is AcceptedCitation)
    assert isinstance(value, AcceptedCitation)
    return AcceptedCitation(
        citation=value.citation, document_id=value.document_id, match=value.match
    )


@dataclass(frozen=True, init=False, repr=False)
class ValidatedClaim:
    """A Verifier claim (model text, unstripped) and the indexes of its citations in the
    question's ``Verification.citations``."""

    text: str
    citation_indexes: tuple[int, ...]

    def __init__(self, *, text: str, citation_indexes: tuple[int, ...], **unknown: object) -> None:
        def build() -> None:
            _require(not unknown and _is_plain(text, 1, MAX_CLAIM_TEXT_CHARS))
            _require(type(citation_indexes) is tuple)
            _require(len(citation_indexes) <= MAX_REFERENCES_PER_ITEM)
            _require(all(_is_int(i, 0, MAX_QUESTION_CITATIONS - 1) for i in citation_indexes))
            _require(len(set(citation_indexes)) == len(citation_indexes))
            object.__setattr__(self, "text", text)
            object.__setattr__(self, "citation_indexes", citation_indexes)

        _run(build, InvalidProvenanceValueError)

    def __repr__(self) -> str:
        return f"ValidatedClaim(citations={len(self.citation_indexes)})"

    __str__ = __repr__


def _rebuilt_claim(value: object) -> ValidatedClaim:
    _require(type(value) is ValidatedClaim)
    assert isinstance(value, ValidatedClaim)
    return ValidatedClaim(text=value.text, citation_indexes=value.citation_indexes)


def _canonical_indexes(claims: tuple[ValidatedClaim, ...], count: int) -> bool:
    """Reading claims in order, the first appearances of indexes are exactly 0 … count-1."""
    seen: set[int] = set()
    for claim in claims:
        for index in claim.citation_indexes:
            if index not in seen:
                if index != len(seen):
                    return False
                seen.add(index)
    return len(seen) == count


@dataclass(frozen=True, init=False, repr=False)
class VerifiedQuestion:
    """One question's derived ``Verification``, its claims and the provenance of each citation
    (``provenance[i]`` belongs to ``verification.citations[i]``)."""

    tenant_id: UUID
    review_id: UUID
    question_id: str
    snapshot_sha256: str
    request_sha256: str
    match_rules: str
    verification: Verification
    claims: tuple[ValidatedClaim, ...]
    provenance: tuple[AcceptedCitation, ...]

    def __init__(
        self,
        *,
        tenant_id: UUID,
        review_id: UUID,
        question_id: str,
        snapshot_sha256: str,
        request_sha256: str,
        match_rules: str,
        verification: Verification,
        claims: tuple[ValidatedClaim, ...],
        provenance: tuple[AcceptedCitation, ...],
        **unknown: object,
    ) -> None:
        def build() -> None:
            _require(not unknown and _is_uuid(tenant_id) and _is_uuid(review_id))
            _require(is_question_id(question_id))
            _require(_is_sha256(snapshot_sha256) and _is_sha256(request_sha256))
            _require(type(match_rules) is str and match_rules == MATCH_RULES)
            _require(type(verification) is Verification)
            checked = verification.model_copy()
            _require(checked.tenant_id == tenant_id and checked.question_id == question_id)
            _require(type(claims) is tuple and len(claims) <= MAX_CLAIMS)
            checked_claims = tuple(_rebuilt_claim(claim) for claim in claims)
            _require(type(provenance) is tuple and len(provenance) <= MAX_QUESTION_CITATIONS)
            checked_provenance = tuple(_rebuilt_accepted(item) for item in provenance)
            _require(len(checked_provenance) == len(checked.citations))
            _require(
                all(
                    item.citation == citation
                    for item, citation in zip(checked_provenance, checked.citations, strict=True)
                )
            )
            _require(_canonical_indexes(checked_claims, len(checked_provenance)))
            if checked.verdict in (Verdict.SUPPORTED, Verdict.CONTRADICTED):
                _require(all(claim.citation_indexes for claim in checked_claims))
            status = _derive(checked.verdict, checked.citations)
            _require(status is not None and status is checked.evidence_status)
            object.__setattr__(self, "tenant_id", tenant_id)
            object.__setattr__(self, "review_id", review_id)
            object.__setattr__(self, "question_id", question_id)
            object.__setattr__(self, "snapshot_sha256", snapshot_sha256)
            object.__setattr__(self, "request_sha256", request_sha256)
            object.__setattr__(self, "match_rules", match_rules)
            object.__setattr__(self, "verification", checked)
            object.__setattr__(self, "claims", checked_claims)
            object.__setattr__(self, "provenance", checked_provenance)

        _run(build, InvalidProvenanceValueError)

    def __repr__(self) -> str:
        return (
            f"VerifiedQuestion(question_id={self.question_id!r}, "
            f"verdict={self.verification.verdict.value!r}, "
            f"evidence_status={self.verification.evidence_status.value!r}, "
            f"claims={len(self.claims)}, citations={len(self.provenance)}, "
            f"request_sha256={self.request_sha256!r})"
        )

    __str__ = __repr__


def _rebuilt_verified(value: object) -> VerifiedQuestion:
    _require(type(value) is VerifiedQuestion)
    assert isinstance(value, VerifiedQuestion)
    return VerifiedQuestion(
        tenant_id=value.tenant_id,
        review_id=value.review_id,
        question_id=value.question_id,
        snapshot_sha256=value.snapshot_sha256,
        request_sha256=value.request_sha256,
        match_rules=value.match_rules,
        verification=value.verification,
        claims=value.claims,
        provenance=value.provenance,
    )


# --- finding identity -----------------------------------------------------------------------------


def _finding_id(
    tenant_id: UUID, review_id: UUID, question_id: str, kind: FindingKind, index: int
) -> UUID:
    _require(_is_uuid(tenant_id) and _is_uuid(review_id) and is_question_id(question_id))
    _require(type(kind) is FindingKind)
    if kind is FindingKind.ANALYST:
        _require(_is_int(index, 0, MAX_FINDINGS - 1))
    else:
        _require(_is_int(index, 0, 0))
    return uuid5(
        FINDING_ID_NAMESPACE, f"{tenant_id}:{review_id}:{question_id}:{kind.value}:{index}"
    )


def finding_id(
    tenant_id: UUID, review_id: UUID, question_id: str, kind: FindingKind, index: int
) -> UUID:
    """``uuid5(FINDING_ID_NAMESPACE, "{tenant}:{review}:{question}:{kind}:{index}")``. ``index``
    is 0-19 for ``analyst`` and exactly 0 for ``documentary_support_required``."""
    return _run(
        lambda: _finding_id(tenant_id, review_id, question_id, kind, index),
        InvalidProvenanceInputError,
    )


# --- analyzed question ----------------------------------------------------------------------------


@dataclass(frozen=True, init=False, repr=False)
class AnalyzedQuestion:
    """One question's Analyst findings, with each finding's follow-up questions (verbatim) in
    the parallel tuple ``follow_up_questions``."""

    tenant_id: UUID
    review_id: UUID
    question_id: str
    request_sha256: str
    findings: tuple[Finding, ...]
    follow_up_questions: tuple[tuple[str, ...], ...]

    def __init__(
        self,
        *,
        tenant_id: UUID,
        review_id: UUID,
        question_id: str,
        request_sha256: str,
        findings: tuple[Finding, ...],
        follow_up_questions: tuple[tuple[str, ...], ...],
        **unknown: object,
    ) -> None:
        def build() -> None:
            _require(not unknown and _is_uuid(tenant_id) and _is_uuid(review_id))
            _require(is_question_id(question_id) and _is_sha256(request_sha256))
            _require(type(findings) is tuple and len(findings) <= MAX_FINDINGS)
            _require(all(type(finding) is Finding for finding in findings))
            checked = tuple(finding.model_copy() for finding in findings)
            _require(type(follow_up_questions) is tuple)
            _require(len(follow_up_questions) == len(checked))
            for questions in follow_up_questions:
                _require(type(questions) is tuple and len(questions) <= MAX_FOLLOW_UPS)
                _require(all(_is_plain(q, 1, MAX_FOLLOW_UP_CHARS) for q in questions))
            for position, finding in enumerate(checked):
                _require(finding.tenant_id == tenant_id)
                _require(question_id in finding.question_ids)
                _require(len(finding.citations) <= MAX_REFERENCES_PER_ITEM)
                expected = _finding_id(
                    tenant_id, review_id, question_id, FindingKind.ANALYST, position
                )
                _require(finding.finding_id == expected)
            object.__setattr__(self, "tenant_id", tenant_id)
            object.__setattr__(self, "review_id", review_id)
            object.__setattr__(self, "question_id", question_id)
            object.__setattr__(self, "request_sha256", request_sha256)
            object.__setattr__(self, "findings", checked)
            object.__setattr__(self, "follow_up_questions", follow_up_questions)

        _run(build, InvalidProvenanceValueError)

    def __repr__(self) -> str:
        return (
            f"AnalyzedQuestion(question_id={self.question_id!r}, "
            f"findings={len(self.findings)}, request_sha256={self.request_sha256!r})"
        )

    __str__ = __repr__


def _rebuilt_analyzed(value: object) -> AnalyzedQuestion:
    _require(type(value) is AnalyzedQuestion)
    assert isinstance(value, AnalyzedQuestion)
    return AnalyzedQuestion(
        tenant_id=value.tenant_id,
        review_id=value.review_id,
        question_id=value.question_id,
        request_sha256=value.request_sha256,
        findings=value.findings,
        follow_up_questions=value.follow_up_questions,
    )


# --- rejections -----------------------------------------------------------------------------------


@dataclass(frozen=True, init=False, repr=False)
class ProvenanceRejection:
    """A text-free stage rejection: the reported reason, its position and the failure count of
    the reported phase (M5b-F)."""

    stage: RejectionStage
    question_id: str
    reason: RejectionReason
    item_index: int | None
    citation_index: int | None
    rejected_count: int

    def __init__(
        self,
        *,
        stage: RejectionStage,
        question_id: str,
        reason: RejectionReason,
        item_index: int | None,
        citation_index: int | None,
        rejected_count: int,
        **unknown: object,
    ) -> None:
        def build() -> None:
            _require(not unknown and type(stage) is RejectionStage)
            _require(is_question_id(question_id) and type(reason) is RejectionReason)
            if reason in _PHASE_1:
                _require(stage is RejectionStage.VERIFICATION)
                _require(_is_int(item_index, 0, MAX_CLAIMS - 1))
                _require(_is_int(citation_index, 0, MAX_REFERENCES_PER_ITEM - 1))
                _require(_is_int(rejected_count, 1, MAX_QUESTION_CITATIONS))
            elif reason is RejectionReason.CLAIM_UNCITED:
                _require(stage is RejectionStage.VERIFICATION)
                _require(_is_int(item_index, 0, MAX_CLAIMS - 1) and citation_index is None)
                _require(_is_int(rejected_count, 1, MAX_CLAIMS))
            elif reason in _PHASE_3:
                _require(stage is RejectionStage.VERIFICATION)
                _require(item_index is None and citation_index is None)
                # rationale_blank is reported only when verdict_unsupported did not fail
                high = 2 if reason is RejectionReason.VERDICT_UNSUPPORTED else 1
                _require(_is_int(rejected_count, 1, high))
            else:
                _require(stage is RejectionStage.ANALYSIS and reason in _ANALYSIS)
                _require(_is_int(item_index, 0, MAX_FINDINGS - 1))
                if reason in _CITATION_REASONS:
                    _require(_is_int(citation_index, 0, MAX_REFERENCES_PER_ITEM - 1))
                else:
                    _require(citation_index is None)
                _require(_is_int(rejected_count, 1, MAX_FINDINGS))
            object.__setattr__(self, "stage", stage)
            object.__setattr__(self, "question_id", question_id)
            object.__setattr__(self, "reason", reason)
            object.__setattr__(self, "item_index", item_index)
            object.__setattr__(self, "citation_index", citation_index)
            object.__setattr__(self, "rejected_count", rejected_count)

        _run(build, InvalidProvenanceValueError)

    @property
    def provenance_check(self) -> str:
        """The §4 ``provenance_check`` value: ``citation_rejected`` or ``invalid_output``."""
        if (
            self.reason in _PHASE_1
            or self.reason is RejectionReason.CLAIM_UNCITED
            or self.reason in _CITATION_REASONS
        ):
            return "citation_rejected"
        return "invalid_output"

    def __repr__(self) -> str:
        return (
            f"ProvenanceRejection(stage={self.stage.value!r}, "
            f"question_id={self.question_id!r}, reason={self.reason.value!r}, "
            f"item_index={self.item_index}, citation_index={self.citation_index}, "
            f"rejected_count={self.rejected_count})"
        )

    __str__ = __repr__


# --- Verifier conversion --------------------------------------------------------------------------


def _verify(
    evidence: QuestionEvidence, call: StructuredResult
) -> VerifiedQuestion | ProvenanceRejection:
    output = call.output
    _require(type(output) is VerifierOutput)
    assert isinstance(output, VerifierOutput)
    question_id = evidence.question.question_id
    _require(call.question_id == question_id)
    items: dict[UUID, RetrievedChunk] = {item.chunk_id: item for item in evidence.result.items}
    forms: dict[UUID, _ChunkForms] = {}

    # Phase 1: every reference, in (claim, reference) order.
    failures: list[tuple[int, int, RejectionReason]] = []
    resolved: list[list[AcceptedCitation]] = []
    for claim_index, claim in enumerate(output.claims):
        accepted: list[AcceptedCitation] = []
        for ref_index, ref in enumerate(claim.citations):
            outcome = _accept(evidence, items, forms, ref)
            if isinstance(outcome, RejectionReason):
                failures.append((claim_index, ref_index, outcome))
            else:
                accepted.append(outcome)
        resolved.append(accepted)
    if failures:
        claim_index, ref_index, reason = failures[0]
        return ProvenanceRejection(
            stage=RejectionStage.VERIFICATION,
            question_id=question_id,
            reason=reason,
            item_index=claim_index,
            citation_index=ref_index,
            rejected_count=len(failures),
        )

    # Deduplication by (chunk, original quote), first appearance across claims.
    keys: dict[tuple[UUID, str], int] = {}
    provenance: list[AcceptedCitation] = []
    claims: list[ValidatedClaim] = []
    for claim, accepted in zip(output.claims, resolved, strict=True):
        indexes: list[int] = []
        for item in accepted:
            key = (item.citation.chunk_id, item.citation.quote)
            if key not in keys:
                keys[key] = len(provenance)
                provenance.append(item)
            if keys[key] not in indexes:
                indexes.append(keys[key])
        claims.append(ValidatedClaim(text=claim.text, citation_indexes=tuple(indexes)))

    # Phase 2: claim coverage (P7).
    if output.verdict in (Verdict.SUPPORTED, Verdict.CONTRADICTED):
        uncited = [index for index, claim in enumerate(claims) if not claim.citation_indexes]
        if uncited:
            return ProvenanceRejection(
                stage=RejectionStage.VERIFICATION,
                question_id=question_id,
                reason=RejectionReason.CLAIM_UNCITED,
                item_index=uncited[0],
                citation_index=None,
                rejected_count=len(uncited),
            )

    # Phase 3: aggregate status and rationale (both evaluated).
    citations = tuple(item.citation for item in provenance)
    status = _derive(output.verdict, citations)
    aggregate: list[RejectionReason] = []
    if status is None:
        aggregate.append(RejectionReason.VERDICT_UNSUPPORTED)
    if not output.rationale.strip():
        aggregate.append(RejectionReason.RATIONALE_BLANK)
    if status is None or aggregate:
        return ProvenanceRejection(
            stage=RejectionStage.VERIFICATION,
            question_id=question_id,
            reason=aggregate[0],
            item_index=None,
            citation_index=None,
            rejected_count=len(aggregate),
        )
    derived: EvidenceStatus = status

    verification = _internal(
        lambda: Verification(
            tenant_id=evidence.tenant_id,
            question_id=question_id,
            verdict=output.verdict,
            evidence_status=derived,
            citations=citations,
            rationale=output.rationale,
        )
    )
    return _internal(
        lambda: VerifiedQuestion(
            tenant_id=evidence.tenant_id,
            review_id=evidence.review_id,
            question_id=question_id,
            snapshot_sha256=evidence.snapshot_sha256,
            request_sha256=call.request_sha256,
            match_rules=MATCH_RULES,
            verification=verification,
            claims=tuple(claims),
            provenance=tuple(provenance),
        )
    )


def _accept(
    evidence: QuestionEvidence,
    items: dict[UUID, RetrievedChunk],
    forms: dict[UUID, _ChunkForms],
    ref: QuoteRef,
) -> AcceptedCitation | RejectionReason:
    found = items.get(ref.chunk_uuid)
    if found is None:
        return RejectionReason.CHUNK_NOT_RETRIEVED
    item: RetrievedChunk = found
    if item.chunk_id not in forms:
        forms[item.chunk_id] = _chunk_forms(item.evidence)
    outcome = _match(forms[item.chunk_id], ref.quote)
    if isinstance(outcome, RejectionReason):
        return outcome
    match: QuoteMatch = outcome
    citations: list[Citation] = []
    with suppress(Exception):
        citations.append(
            Citation(
                tenant_id=evidence.tenant_id,
                document_revision_id=item.revision_id,
                chunk_id=item.chunk_id,
                source_type=item.evidence.source_type,
                quote=match.quote,
                authenticity=item.evidence.authenticity,
            )
        )
    if not citations or citations[0].quote != match.quote:
        return RejectionReason.QUOTE_NOT_EXACT
    return _internal(
        lambda: AcceptedCitation(citation=citations[0], document_id=item.document_id, match=match)
    )


def verify_question(
    evidence: QuestionEvidence, result: StructuredResult
) -> VerifiedQuestion | ProvenanceRejection:
    """Convert a completed Verifier result for ``evidence.question`` into a ``VerifiedQuestion``
    with derived status and trusted citation metadata, or a ``ProvenanceRejection``.

    Bad trusted or caller input (wrong types, a non-completed or non-Verifier result, a question
    mismatch) raises ``InvalidProvenanceInputError`` before any model content is examined.
    """

    def build() -> VerifiedQuestion | ProvenanceRejection:
        checked = _rebuilt_question_evidence(evidence)
        call = _rebuilt_call(result, ModelPurpose.VERIFIER)
        return _verify(checked, call)

    return _run(build, InvalidProvenanceInputError)


def recheck_verified(verified: VerifiedQuestion, evidence: QuestionEvidence) -> VerifiedQuestion:
    """Revalidate a reloaded ``VerifiedQuestion`` against trusted evidence: identities,
    retrieved membership, trusted metadata and, for every citation, a recomputed ``match_quote``
    equal in every field to the stored match. Any difference raises
    ``InvalidProvenanceInputError``. This detects values inconsistent with the evidence
    supplied; it does not prove which retrieval request originally ran."""

    def build() -> VerifiedQuestion:
        checked = _rebuilt_verified(verified)
        trusted = _rebuilt_question_evidence(evidence)
        _require(checked.tenant_id == trusted.tenant_id)
        _require(checked.review_id == trusted.review_id)
        _require(checked.snapshot_sha256 == trusted.snapshot_sha256)
        _require(checked.question_id == trusted.question.question_id)
        items = {item.chunk_id: item for item in trusted.result.items}
        for accepted in checked.provenance:
            citation = accepted.citation
            item = items.get(citation.chunk_id)
            _require(item is not None)
            assert item is not None
            _require(citation.tenant_id == trusted.tenant_id)
            _require(citation.document_revision_id == item.revision_id)
            _require(accepted.document_id == item.document_id)
            _require(citation.source_type is item.evidence.source_type)
            _require(citation.authenticity is item.evidence.authenticity)
            _require(_match(_chunk_forms(item.evidence), citation.quote) == accepted.match)
        return checked

    return _run(build, InvalidProvenanceInputError)


# --- Risk Analyst findings ------------------------------------------------------------------------


def _checked_shared(owner: VerifiedQuestion, shared: object) -> dict[str, VerifiedQuestion]:
    _require(type(shared) is tuple and len(shared) <= MAX_SHARED_QUESTIONS)
    assert isinstance(shared, tuple)
    by_id: dict[str, VerifiedQuestion] = {}
    for value in shared:
        checked = _rebuilt_verified(value)
        _require(checked.question_id != owner.question_id and checked.question_id not in by_id)
        _require(checked.tenant_id == owner.tenant_id and checked.review_id == owner.review_id)
        _require(checked.snapshot_sha256 == owner.snapshot_sha256)
        by_id[checked.question_id] = checked
    return by_id


def _finding_status(
    verdict: Verdict, citations: tuple[Citation, ...]
) -> EvidenceStatus | RejectionReason:
    if not citations or verdict is Verdict.INSUFFICIENT_EVIDENCE:
        return EvidenceStatus.MISSING
    status = _derive(verdict, citations)
    return RejectionReason.FINDING_STATUS_UNSUPPORTED if status is None else status


def _citations_by_key(verification: Verification) -> dict[tuple[UUID, str], Citation]:
    """A Verification's citations by ``(chunk_id, quote)``, unique by the ``Verification``
    contract (no duplicate chunk and quote)."""
    return {(c.chunk_id, c.quote): c for c in verification.citations}


def _analyze_finding(
    owner: VerifiedQuestion,
    shared: dict[str, VerifiedQuestion],
    resolvable: dict[tuple[UUID, str], Citation],
    index: int,
    output: FindingOutput,
) -> Finding | tuple[RejectionReason, int | None]:
    # 1. question scope
    others = [q for q in output.question_ids if q != owner.question_id]
    if owner.question_id not in output.question_ids or not all(q in shared for q in others):
        return (RejectionReason.FOREIGN_QUESTION, None)
    # 2. citations: whole-quote equivalence to an owner citation, shared by every listed question
    citations: list[Citation] = []
    for ref_index, ref in enumerate(output.citations):
        key = _quote_key(ref.quote)
        citation = resolvable.get((ref.chunk_uuid, key)) if key else None
        if citation is None:
            return (RejectionReason.CITATION_NOT_VALIDATED, ref_index)
        # the full trusted value (tenant, revision, chunk, source type, quote, authenticity)
        if not all(citation in shared[q].verification.citations for q in others):
            return (RejectionReason.CITATION_NOT_SHARED, ref_index)
        if citation not in citations:
            citations.append(citation)
    # 3. status from the common verdict and the finding's own citations
    verdicts = {owner.verification.verdict, *(shared[q].verification.verdict for q in others)}
    if len(verdicts) != 1:
        return (RejectionReason.MIXED_VERDICTS, None)
    derived = _finding_status(owner.verification.verdict, tuple(citations))
    if isinstance(derived, RejectionReason):
        return (derived, None)
    status: EvidenceStatus = derived
    # 4. text
    if not output.title.strip() or not output.statement.strip():
        return (RejectionReason.FINDING_TEXT_BLANK, None)
    # 5. identity
    return _internal(
        lambda: Finding(
            tenant_id=owner.tenant_id,
            finding_id=_finding_id(
                owner.tenant_id, owner.review_id, owner.question_id, FindingKind.ANALYST, index
            ),
            question_ids=output.question_ids,
            title=output.title,
            severity=output.severity,
            statement=output.statement,
            evidence_status=status,
            citations=tuple(citations),
        )
    )


def _bound_analysis(
    owner: object, question: object, shared: object
) -> tuple[VerifiedQuestion, EvidenceQuestion, dict[str, VerifiedQuestion]]:
    checked_owner = _rebuilt_verified(owner)
    checked_question = _rebuilt_question(question)
    _require(checked_question.question_id == checked_owner.question_id)
    return checked_owner, checked_question, _checked_shared(checked_owner, shared)


def analyze_question(
    owner: VerifiedQuestion,
    question: EvidenceQuestion,
    result: StructuredResult,
    *,
    shared: tuple[VerifiedQuestion, ...] = (),
) -> AnalyzedQuestion | ProvenanceRejection:
    """Convert a completed Risk Analyst result into findings restricted to citations the
    Verifier already validated, or a ``ProvenanceRejection``. Owner, question, result and shared
    identities are checked before any finding is examined, including for an empty output; a
    rejection never modifies ``owner``. ``owner`` and ``shared`` must come from a trusted path
    that ran ``verify_question`` or ``recheck_verified``; retrieval membership is not
    re-proved here."""

    def build() -> AnalyzedQuestion | ProvenanceRejection:
        checked_owner, _, by_id = _bound_analysis(owner, question, shared)
        call = _rebuilt_call(result, ModelPurpose.RISK_ANALYST)
        _require(call.question_id == checked_owner.question_id)
        output = call.output
        _require(type(output) is AnalystOutput)
        assert isinstance(output, AnalystOutput)
        resolvable: dict[tuple[UUID, str], Citation] = {}
        for citation in checked_owner.verification.citations:
            resolvable.setdefault((citation.chunk_id, _quote_key(citation.quote)), citation)
        findings: list[Finding] = []
        failures: list[tuple[int, RejectionReason, int | None]] = []
        for index, finding_output in enumerate(output.findings):
            outcome = _analyze_finding(checked_owner, by_id, resolvable, index, finding_output)
            if isinstance(outcome, Finding):
                findings.append(outcome)
            else:
                failures.append((index, *outcome))
        if failures:
            index, reason, ref_index = failures[0]
            return ProvenanceRejection(
                stage=RejectionStage.ANALYSIS,
                question_id=checked_owner.question_id,
                reason=reason,
                item_index=index,
                citation_index=ref_index,
                rejected_count=len(failures),
            )
        return _internal(
            lambda: AnalyzedQuestion(
                tenant_id=checked_owner.tenant_id,
                review_id=checked_owner.review_id,
                question_id=checked_owner.question_id,
                request_sha256=call.request_sha256,
                findings=tuple(findings),
                follow_up_questions=tuple(f.follow_up_questions for f in output.findings),
            )
        )

    return _run(build, InvalidProvenanceInputError)


def recheck_analyzed(
    analyzed: AnalyzedQuestion,
    owner: VerifiedQuestion,
    question: EvidenceQuestion,
    *,
    shared: tuple[VerifiedQuestion, ...] = (),
) -> AnalyzedQuestion:
    """Revalidate a reloaded ``AnalyzedQuestion`` against its trusted owner, question and shared
    verifications: outer identities first (even with no findings), then each finding's scope,
    exact citations, re-derived status and ID. Any difference raises
    ``InvalidProvenanceInputError``. The Analyst and Verifier request digests identify
    different calls and are never compared."""

    def build() -> AnalyzedQuestion:
        checked = _rebuilt_analyzed(analyzed)
        checked_owner, checked_question, by_id = _bound_analysis(owner, question, shared)
        _require(checked.tenant_id == checked_owner.tenant_id)
        _require(checked.review_id == checked_owner.review_id)
        _require(checked.question_id == checked_owner.question_id == checked_question.question_id)
        owner_citations = _citations_by_key(checked_owner.verification)
        for finding in checked.findings:
            others = [q for q in finding.question_ids if q != checked_owner.question_id]
            _require(all(q in by_id for q in others))
            trusted: list[Citation] = []
            for citation in finding.citations:
                # resolve to the trusted owner citation and require the full value to be equal,
                # so changed stored metadata cannot pass or manufacture another status
                owner_citation = owner_citations.get((citation.chunk_id, citation.quote))
                _require(owner_citation is not None and citation == owner_citation)
                assert owner_citation is not None
                _require(all(owner_citation in by_id[q].verification.citations for q in others))
                trusted.append(owner_citation)
            verdicts = {
                checked_owner.verification.verdict,
                *(by_id[q].verification.verdict for q in others),
            }
            _require(len(verdicts) == 1)
            status = _finding_status(checked_owner.verification.verdict, tuple(trusted))
            _require(status is finding.evidence_status)
        return checked

    return _run(build, InvalidProvenanceInputError)


# --- documentary-support rule ---------------------------------------------------------------------


def documentary_gap_finding(
    verified: VerifiedQuestion, question: EvidenceQuestion
) -> Finding | None:
    """The deterministic rule finding (P11) for a question requiring documentary support whose
    valid Verification is ``vendor_claim``; otherwise ``None``. Identities are checked first, so
    a mismatch raises ``InvalidProvenanceInputError`` whatever the condition. It must be included
    in the hash-covered report even if analysis fails (an obligation on M5f/M5g)."""

    def build() -> Finding | None:
        checked = _rebuilt_verified(verified)
        checked_question = _rebuilt_question(question)
        _require(checked.question_id == checked_question.question_id)
        verification = checked.verification
        if not (
            checked_question.requires_documentary_support
            and verification.evidence_status is EvidenceStatus.VENDOR_CLAIM
        ):
            return None
        return _internal(
            lambda: Finding(
                tenant_id=checked.tenant_id,
                finding_id=_finding_id(
                    checked.tenant_id,
                    checked.review_id,
                    checked.question_id,
                    FindingKind.DOCUMENTARY_SUPPORT_REQUIRED,
                    0,
                ),
                question_ids=(checked.question_id,),
                title=DOCUMENTARY_GAP_TITLE,
                severity=DOCUMENTARY_GAP_SEVERITY,
                statement=DOCUMENTARY_GAP_STATEMENT,
                evidence_status=EvidenceStatus.MISSING,
                citations=verification.citations,
            )
        )

    return _run(build, InvalidProvenanceInputError)
