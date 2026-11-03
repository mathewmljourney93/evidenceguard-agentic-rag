"""Stage and call-reservation values, canonical encodings and the pure planner (M5e, ADR-0023).

Implements the M5e specification accepted in Prompt 199 (``docs/plan.md``, M5e-B to M5e-D, E1-E20
with clarifications A and B): the fixed enumerations, the planned-question set, question evidence,
call and stage records, ``StageHistory`` with the whole-history rules V1-V12, the four plan
variants and the total planner ``plan_stage`` (T0-T9), the in-run and trusted-reload results, and
the five canonical encodings with bounded strict decoders.

Every value is a frozen dataclass with a validating keyword-only constructor: exact types (a
``bool`` is never an ``int``; tuples only; ``UUID`` objects only), unknown keywords rejected,
nested values rebuilt through their own constructors and required to equal the input (no silent
normalization), derived fields computed and never accepted, ``dataclasses.replace`` running the
same constructor, datetimes timezone-aware and stored in UTC. Construction failures are a fresh
``InvalidStageValueError`` (``InvalidStageHistoryError`` for a history), raised after leaving the
handler with no cause or context; process control propagates as the same object. ``repr``/``str``
show identifiers, enumerations, sequence numbers, counts and digests only, never question text,
evidence text, quotes, claims, rationales, findings or prompts. Nothing here logs, touches a
database or proves that a value came from one.

**Canonical encodings** (M5e-B2): ``json.dumps(obj, sort_keys=True, separators=(",", ":"),
ensure_ascii=True, allow_nan=False)`` encoded as ASCII, digests the lowercase SHA-256 of those
bytes. Every integer is in ``0 … 2,147,483,647``; floats are ``float.hex()`` strings; fused scores
are recomputed from the hits; optional keys are always present. ``EvidenceRecord`` and
``StageRecord`` refuse inherited integers above the bound (an admission narrowing: such values
cannot come from PostgreSQL ``integer`` columns). Decoders check the size cap before parsing,
printable ASCII, duplicate keys, JSON floats and constants, integer lexical and magnitude bounds,
exact key sets and value types, rebuild the domain values, require a byte-identical re-encoding
and the stored digest.

**Timestamps** are wall-clock audit values only (V12): no ordering between them is required
anywhere. Ordering and abandonment are decided by ``sequence`` and ``job_attempt`` alone.
"""

import hashlib
import json
import math
import re
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum
from fractions import Fraction
from itertools import pairwise
from typing import Any, ClassVar, NoReturn
from uuid import UUID

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
from evidenceguard_domain.jobs import MAX_MAX_ATTEMPTS
from evidenceguard_domain.model_calls import (
    LATENCY_MS_BOUND,
    MAX_OUTPUT_TOKENS,
    MAX_TIMEOUT_MS,
    MIN_TIMEOUT_MS,
    CallOutcome,
    ModelPurpose,
    ModelUsage,
    StructuredRequest,
    StructuredResult,
    is_model_id,
    is_question_id,
)
from evidenceguard_domain.provenance import (
    AcceptedCitation,
    AnalyzedQuestion,
    ProvenanceRejection,
    QuestionEvidence,
    QuoteMatch,
    QuoteSpanKind,
    RejectionReason,
    RejectionStage,
    ValidatedClaim,
    VerifiedQuestion,
)
from evidenceguard_domain.retrieval import (
    RRF_CONSTANT,
    ChannelHit,
    ChunkEvidence,
    RetrievalResult,
    RetrievalSnapshot,
    RetrievedChunk,
    SourceSpan,
    revalidate_snapshot,
)

PLAN_QUESTION_CANONICAL = "eg-review-plan-question-v1"
EVIDENCE_CANONICAL = "eg-review-question-evidence-v1"
VERIFIED_CANONICAL = "eg-review-stage-verified-v1"
ANALYZED_CANONICAL = "eg-review-stage-analyzed-v1"
DEPENDENCY_CANONICAL = "eg-review-stage-dependency-v1"

MAX_CANONICAL_INT = 2_147_483_647
MAX_EVIDENCE_BYTES = 4_194_304
MAX_VERIFIED_BYTES = 2_097_152
MAX_ANALYZED_BYTES = 4_194_304
MAX_CALLS = 3
MAX_PLANNED_QUESTIONS = 100
MAX_JOB_ATTEMPT = MAX_MAX_ATTEMPTS
MAX_EVIDENCE_ITEMS = 20
PLACEHOLDER_QUESTION_ID = "AA-00"
"""A valid question ID used only to validate a ``CallRejection`` against M5b (never stored)."""

_SHA256 = re.compile(r"[0-9a-f]{64}", re.ASCII)
_PRINTABLE = re.compile(rb"[\x20-\x7e]*")
_FLOAT = re.compile(r"-?0x[01]\.[0-9a-f]+p[+-][0-9]+", re.ASCII)
_DIGITS = re.compile(r"[0-9]{1,10}", re.ASCII)


# --- errors (fixed messages: the message is the code) ---------------------------------------------


class ReviewStageError(Exception):
    """Base of the fixed M5e errors. Never carries submitted values, content or causes."""

    code: ClassVar[str] = "review_stage_error"

    def __init__(self) -> None:
        super().__init__(self.code)


class InvalidStageValueError(ReviewStageError):
    """Invalid construction, replacement, encoding or decoding of an M5e value."""

    code = "invalid_stage_value"


class InvalidStageHistoryError(ReviewStageError):
    """A ``StageHistory`` that violates V1-V12, or a planner argument that is not one."""

    code = "invalid_stage_history"


# --- helpers --------------------------------------------------------------------------------------


class _Invalid(Exception):
    """Private: a failed check inside a guarded operation."""


def _require(condition: bool) -> None:
    if not condition:
        raise _Invalid


def _fail() -> NoReturn:
    raise _Invalid


def _run[T](build: Callable[[], T], error: type[ReviewStageError]) -> T:
    """Run one whole operation; any ordinary failure becomes a fresh ``error`` raised after the
    handler (no cause or context). Process control propagates as the same object."""
    built: list[T] = []
    with suppress(Exception):
        built.append(build())
    if not built:
        raise error()
    return built[0]


def _is_int(value: object, low: int, high: int) -> bool:
    return type(value) is int and low <= value <= high


def _is_sha256(value: object) -> bool:
    return type(value) is str and _SHA256.fullmatch(value) is not None


def _is_optional_sha256(value: object) -> bool:
    return value is None or _is_sha256(value)


def _admitted(value: int) -> bool:
    """The canonical integer range (M5e-B2)."""
    return 0 <= value <= MAX_CANONICAL_INT


def _utc(value: object) -> datetime:
    _require(type(value) is datetime)
    assert isinstance(value, datetime)
    _require(value.tzinfo is not None and value.utcoffset() is not None)
    return value.astimezone(UTC)


def _optional_utc(value: object) -> datetime | None:
    return None if value is None else _utc(value)


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _same[T](value: object, kind: type[T], rebuild: Callable[[T], T]) -> T:
    """Rebuild ``value`` (exactly of ``kind``) through its constructor and require the rebuilt
    value to equal it, so a value altered after construction or a normalizing rebuild is
    refused rather than silently changed."""
    _require(type(value) is kind)
    assert isinstance(value, kind)
    rebuilt = rebuild(value)
    _require(rebuilt == value)
    return rebuilt


def _question(value: object) -> EvidenceQuestion:
    """An exactly typed planned question, rebuilt through the ``EvidenceQuestion`` validation.

    Every field's exact type is checked first, by attribute reads only, before any operation
    that could normalize or serialize it (``model_copy``/``model_dump`` would coerce an ``int``
    flag to ``bool`` and warn with a malformed value's text): an exact ``str`` ID and text, an
    exact ``tuple`` of exact ``str`` queries and an exact ``bool`` flag. The rebuilt fields must
    then equal the inputs in value and type, so padding the model would strip is refused rather
    than changed."""
    _require(type(value) is EvidenceQuestion)
    assert isinstance(value, EvidenceQuestion)
    question_id = value.question_id
    text = value.text
    queries = value.search_queries
    documentary = value.requires_documentary_support
    _require(type(question_id) is str and type(text) is str and type(documentary) is bool)
    _require(type(queries) is tuple and all(type(query) is str for query in queries))
    rebuilt = EvidenceQuestion(
        question_id=question_id,
        text=text,
        search_queries=queries,
        requires_documentary_support=documentary,
    )
    _require(type(rebuilt.question_id) is str and rebuilt.question_id == question_id)
    _require(type(rebuilt.text) is str and rebuilt.text == text)
    _require(type(rebuilt.search_queries) is tuple and rebuilt.search_queries == queries)
    _require(all(type(query) is str for query in rebuilt.search_queries))
    _require(rebuilt.requires_documentary_support is documentary)
    return rebuilt


def _question_evidence(value: object) -> QuestionEvidence:
    """A supplied ``QuestionEvidence`` rebuilt through its constructor from exactly typed,
    rebuilt fields (its question through ``_question``, its result through the M4d
    constructor)."""
    _require(type(value) is QuestionEvidence)
    assert isinstance(value, QuestionEvidence)
    tenant_id, review_id = value.tenant_id, value.review_id
    _require(type(tenant_id) is UUID and type(review_id) is UUID)
    _require(_is_sha256(value.snapshot_sha256))
    return QuestionEvidence(
        tenant_id=tenant_id,
        review_id=review_id,
        snapshot_sha256=value.snapshot_sha256,
        question=_question(value.question),
        result=_retrieval_result(value.result),
    )


def _structured_result(value: object) -> StructuredResult:
    return _same(
        value,
        StructuredResult,
        lambda r: StructuredResult(
            request_sha256=r.request_sha256,
            purpose=r.purpose,
            question_id=r.question_id,
            outcome=r.outcome,
            dispatched=r.dispatched,
            output=r.output,
            model_requested=r.model_requested,
            model_used=r.model_used,
            usage=r.usage,
            latency_ms=r.latency_ms,
        ),
    )


def _structured_request(value: object) -> StructuredRequest:
    return _same(
        value,
        StructuredRequest,
        lambda r: StructuredRequest(
            purpose=r.purpose,
            prompt=r.prompt,
            model_id=r.model_id,
            question_id=r.question_id,
            system_text=r.system_text,
            user_text=r.user_text,
            max_output_tokens=r.max_output_tokens,
            timeout_ms=r.timeout_ms,
        ),
    )


def _provenance_rejection(value: object) -> ProvenanceRejection:
    return _same(
        value,
        ProvenanceRejection,
        lambda r: ProvenanceRejection(
            stage=r.stage,
            question_id=r.question_id,
            reason=r.reason,
            item_index=r.item_index,
            citation_index=r.citation_index,
            rejected_count=r.rejected_count,
        ),
    )


def _verified(value: object) -> VerifiedQuestion:
    return _same(
        value,
        VerifiedQuestion,
        lambda v: VerifiedQuestion(
            tenant_id=v.tenant_id,
            review_id=v.review_id,
            question_id=v.question_id,
            snapshot_sha256=v.snapshot_sha256,
            request_sha256=v.request_sha256,
            match_rules=v.match_rules,
            verification=v.verification,
            claims=v.claims,
            provenance=v.provenance,
        ),
    )


def _analyzed(value: object) -> AnalyzedQuestion:
    return _same(
        value,
        AnalyzedQuestion,
        lambda a: AnalyzedQuestion(
            tenant_id=a.tenant_id,
            review_id=a.review_id,
            question_id=a.question_id,
            request_sha256=a.request_sha256,
            findings=a.findings,
            follow_up_questions=a.follow_up_questions,
        ),
    )


def _retrieval_result(value: object) -> RetrievalResult:
    return _same(
        value,
        RetrievalResult,
        lambda r: RetrievalResult(r.snapshot, r.query_count, r.k, r.vector_skipped, r.items),
    )


def revalidated_result(value: object) -> StructuredResult:
    """A supplied ``StructuredResult`` rebuilt through its constructor (``InvalidStageValueError``
    otherwise)."""
    return _run(lambda: _structured_result(value), InvalidStageValueError)


def revalidated_request(value: object) -> StructuredRequest:
    return _run(lambda: _structured_request(value), InvalidStageValueError)


def revalidated_rejection(value: object) -> ProvenanceRejection:
    return _run(lambda: _provenance_rejection(value), InvalidStageValueError)


def revalidated_verified(value: object) -> VerifiedQuestion:
    """A supplied ``VerifiedQuestion`` rebuilt, with its inherited integers in the admission
    range (``InvalidStageValueError`` otherwise)."""

    def build() -> VerifiedQuestion:
        checked = _verified(value)
        _require(_verified_admitted(checked))
        return checked

    return _run(build, InvalidStageValueError)


def revalidated_analyzed(value: object) -> AnalyzedQuestion:
    return _run(lambda: _analyzed(value), InvalidStageValueError)


def revalidated_question(value: object) -> EvidenceQuestion:
    return _run(lambda: _question(value), InvalidStageValueError)


# --- enumerations ---------------------------------------------------------------------------------


class StageKind(StrEnum):
    VERIFICATION = "verification"
    ANALYSIS = "analysis"

    @property
    def purpose(self) -> ModelPurpose:
        if self is StageKind.VERIFICATION:
            return ModelPurpose.VERIFIER
        return ModelPurpose.RISK_ANALYST

    @property
    def rejection_stage(self) -> RejectionStage:
        if self is StageKind.VERIFICATION:
            return RejectionStage.VERIFICATION
        return RejectionStage.ANALYSIS


class CallKind(StrEnum):
    INITIAL = "initial"
    RETRY = "retry"
    REPAIR = "repair"


class RequestBasis(StrEnum):
    ORIGINAL = "original"
    REPAIRED = "repaired"


class ReservationState(StrEnum):
    STARTED = "started"
    COMPLETED = "completed"


class StageOutcome(StrEnum):
    VERIFIED = "verified"
    ANALYZED = "analyzed"
    UNRESOLVED = "unresolved"


class UnresolvedReason(StrEnum):
    # after a completed call
    REFUSAL = "refusal"
    MAX_TOKENS = "max_tokens"
    UNEXPECTED_STOP = "unexpected_stop"
    MODEL_MISMATCH = "model_mismatch"
    INVALID_OUTPUT = "invalid_output"
    CITATION_REJECTED = "citation_rejected"
    TIMEOUT = "timeout"
    PROVIDER_FAILED = "provider_failed"
    # after abandoned calls
    CALL_ABANDONED = "call_abandoned"
    # pre-dispatch
    REQUEST_TOO_LARGE = "request_too_large"
    REPAIR_REQUEST_TOO_LARGE = "repair_request_too_large"
    EVIDENCE_TOO_LARGE = "evidence_too_large"
    # dependency
    VERIFICATION_UNRESOLVED = "verification_unresolved"


AFTER_CALL_REASONS = frozenset(
    {
        UnresolvedReason.REFUSAL,
        UnresolvedReason.MAX_TOKENS,
        UnresolvedReason.UNEXPECTED_STOP,
        UnresolvedReason.MODEL_MISMATCH,
        UnresolvedReason.INVALID_OUTPUT,
        UnresolvedReason.CITATION_REJECTED,
        UnresolvedReason.TIMEOUT,
        UnresolvedReason.PROVIDER_FAILED,
    }
)
EXHAUSTED_REASONS = AFTER_CALL_REASONS | {UnresolvedReason.CALL_ABANDONED}
_CALL_REFERENCED = EXHAUSTED_REASONS | {UnresolvedReason.REPAIR_REQUEST_TOO_LARGE}
_RETRYABLE = frozenset({CallOutcome.TIMEOUT, CallOutcome.PROVIDER_FAILED})
_TERMINAL = frozenset(
    {
        CallOutcome.REFUSAL,
        CallOutcome.MAX_TOKENS,
        CallOutcome.UNEXPECTED_STOP,
        CallOutcome.MODEL_MISMATCH,
    }
)
_RESPONSE_OUTCOMES = frozenset(
    {
        CallOutcome.COMPLETED,
        CallOutcome.REFUSAL,
        CallOutcome.MAX_TOKENS,
        CallOutcome.UNEXPECTED_STOP,
        CallOutcome.INVALID_OUTPUT,
    }
)


def _rejection_stage_kind(stage: RejectionStage) -> StageKind:
    return StageKind.VERIFICATION if stage is RejectionStage.VERIFICATION else StageKind.ANALYSIS


# --- canonical integers, floats and dates ---------------------------------------------------------


def _float_text(value: float) -> str:
    _require(type(value) is float and math.isfinite(value))
    return value.hex()


def _decoded_float(value: object) -> float:
    _require(type(value) is str)
    assert isinstance(value, str)
    _require(_FLOAT.fullmatch(value) is not None)
    number = float.fromhex(value)
    _require(math.isfinite(number) and number.hex() == value)
    return number


def _decoded_date(value: object) -> date:
    _require(type(value) is str)
    assert isinstance(value, str)
    parsed = date.fromisoformat(value)
    _require(parsed.isoformat() == value)
    return parsed


def _decoded_uuid(value: object) -> UUID:
    _require(type(value) is str)
    assert isinstance(value, str)
    parsed = UUID(value)
    _require(str(parsed) == value)
    return parsed


# --- planned questions ----------------------------------------------------------------------------


def _plan_question_object(question: EvidenceQuestion) -> dict[str, Any]:
    return {
        "canonical": PLAN_QUESTION_CANONICAL,
        "question_id": question.question_id,
        "text": question.text,
        "search_queries": list(question.search_queries),
        "requires_documentary_support": question.requires_documentary_support,
    }


def plan_question_canonical(question: EvidenceQuestion) -> bytes:
    """The ``eg-review-plan-question-v1`` bytes of a planned question."""
    return _run(
        lambda: _canonical(_plan_question_object(_question(question))), InvalidStageValueError
    )


def plan_question_sha256(question: EvidenceQuestion) -> str:
    return _sha256(plan_question_canonical(question))


@dataclass(frozen=True, init=False, repr=False)
class PlannedQuestionSet:
    """A review's planned questions in template order (position = tuple index). Construction
    cannot prove that the questions came from the pinned template (a worker obligation)."""

    tenant_id: UUID
    review_id: UUID
    questions: tuple[EvidenceQuestion, ...]
    question_sha256s: tuple[str, ...] = field(init=False)

    def __init__(
        self,
        *,
        tenant_id: UUID,
        review_id: UUID,
        questions: tuple[EvidenceQuestion, ...],
        **unknown: object,
    ) -> None:
        def build() -> None:
            _require(not unknown and type(tenant_id) is UUID and type(review_id) is UUID)
            _require(type(questions) is tuple)
            _require(1 <= len(questions) <= MAX_PLANNED_QUESTIONS)
            checked = tuple(_question(question) for question in questions)
            identifiers = [question.question_id for question in checked]
            _require(len(set(identifiers)) == len(identifiers))
            digests = tuple(
                _sha256(_canonical(_plan_question_object(question))) for question in checked
            )
            object.__setattr__(self, "tenant_id", tenant_id)
            object.__setattr__(self, "review_id", review_id)
            object.__setattr__(self, "questions", checked)
            object.__setattr__(self, "question_sha256s", digests)

        _run(build, InvalidStageValueError)

    def position(self, question_id: str) -> int | None:
        for index, question in enumerate(self.questions):
            if question.question_id == question_id:
                return index
        return None

    def __repr__(self) -> str:
        return f"PlannedQuestionSet(review_id={self.review_id}, questions={len(self.questions)})"

    __str__ = __repr__


def _planned(value: object) -> PlannedQuestionSet:
    return _same(
        value,
        PlannedQuestionSet,
        lambda p: PlannedQuestionSet(
            tenant_id=p.tenant_id, review_id=p.review_id, questions=p.questions
        ),
    )


def revalidated_planned(value: object) -> PlannedQuestionSet:
    return _run(lambda: _planned(value), InvalidStageValueError)


# --- question evidence ----------------------------------------------------------------------------


def _span_admitted(span: SourceSpan) -> bool:
    return all(
        _admitted(value)
        for value in (span.line_start, span.line_end, span.char_start, span.char_end)
    )


def _result_admitted(result: RetrievalResult) -> bool:
    values: list[int] = [result.query_count, result.k, *result.vector_skipped]
    for item in result.items:
        evidence = item.evidence
        values += [item.fused_rank, evidence.ordinal, evidence.revision_no]
        values += [value for hit in item.hits for value in (hit.query_position, hit.rank)]
        if not _span_admitted(evidence.body):
            return False
        if evidence.header is not None and not _span_admitted(evidence.header):
            return False
    return all(_admitted(value) for value in values)


def _span_object(span: SourceSpan | None) -> dict[str, int] | None:
    if span is None:
        return None
    return {
        "line_start": span.line_start,
        "line_end": span.line_end,
        "char_start": span.char_start,
        "char_end": span.char_end,
    }


def _item_object(item: RetrievedChunk) -> dict[str, Any]:
    evidence = item.evidence
    return {
        "chunk_id": str(item.chunk_id),
        "revision_id": str(item.revision_id),
        "document_id": str(item.document_id),
        "fused_rank": item.fused_rank,
        "hits": [
            {
                "channel": hit.channel,
                "query_position": hit.query_position,
                "rank": hit.rank,
                "score": _float_text(hit.score),
            }
            for hit in item.hits
        ],
        "evidence": {
            "text": evidence.text,
            "content_sha256": evidence.content_sha256,
            "ordinal": evidence.ordinal,
            "section_path": list(evidence.section_path),
            "is_table": evidence.is_table,
            "body": _span_object(evidence.body),
            "header": _span_object(evidence.header),
            "document_key": evidence.document_key,
            "title": evidence.title,
            "revision_no": evidence.revision_no,
            "version_label": evidence.version_label,
            "effective_date": (
                None if evidence.effective_date is None else evidence.effective_date.isoformat()
            ),
            "source_type": evidence.source_type.value,
            "authenticity": evidence.authenticity.value,
        },
    }


def _evidence_object(
    tenant_id: UUID, review_id: UUID, question: EvidenceQuestion, question_sha: str, result: Any
) -> dict[str, Any]:
    return {
        "canonical": EVIDENCE_CANONICAL,
        "tenant_id": str(tenant_id),
        "review_id": str(review_id),
        "question_id": question.question_id,
        "question_sha256": question_sha,
        "snapshot_sha256": result.snapshot_sha256,
        "query_count": result.query_count,
        "k": result.k,
        "vector_skipped": list(result.vector_skipped),
        "items": [_item_object(item) for item in result.items],
    }


@dataclass(frozen=True, init=False, repr=False)
class EvidenceRecord:
    """One question's retrieval result with its ``eg-review-question-evidence-v1`` encoding. An
    oversized record is a valid value with ``fits_storage`` false; it cannot be stored (U4)."""

    tenant_id: UUID
    review_id: UUID
    question: EvidenceQuestion
    result: RetrievalResult
    question_id: str = field(init=False)
    question_sha256: str = field(init=False)
    snapshot_sha256: str = field(init=False)
    item_count: int = field(init=False)
    canonical: bytes = field(init=False)
    evidence_sha256: str = field(init=False)
    fits_storage: bool = field(init=False)

    def __init__(
        self,
        *,
        tenant_id: UUID,
        review_id: UUID,
        question: EvidenceQuestion,
        result: RetrievalResult,
        **unknown: object,
    ) -> None:
        def build() -> None:
            _require(not unknown and type(tenant_id) is UUID and type(review_id) is UUID)
            checked_question = _question(question)
            checked_result = _retrieval_result(result)
            _require(checked_result.tenant_id == tenant_id)
            _require(checked_result.query_count == len(checked_question.search_queries))
            _require(_result_admitted(checked_result))
            question_sha = _sha256(_canonical(_plan_question_object(checked_question)))
            canonical = _canonical(
                _evidence_object(
                    tenant_id, review_id, checked_question, question_sha, checked_result
                )
            )
            object.__setattr__(self, "tenant_id", tenant_id)
            object.__setattr__(self, "review_id", review_id)
            object.__setattr__(self, "question", checked_question)
            object.__setattr__(self, "result", checked_result)
            object.__setattr__(self, "question_id", checked_question.question_id)
            object.__setattr__(self, "question_sha256", question_sha)
            object.__setattr__(self, "snapshot_sha256", checked_result.snapshot_sha256)
            object.__setattr__(self, "item_count", len(checked_result.items))
            object.__setattr__(self, "canonical", canonical)
            object.__setattr__(self, "evidence_sha256", _sha256(canonical))
            object.__setattr__(self, "fits_storage", len(canonical) <= MAX_EVIDENCE_BYTES)

        _run(build, InvalidStageValueError)

    def __repr__(self) -> str:
        return (
            f"EvidenceRecord(review_id={self.review_id}, question_id={self.question_id!r}, "
            f"items={self.item_count}, fits_storage={self.fits_storage}, "
            f"evidence_sha256={self.evidence_sha256!r})"
        )

    __str__ = __repr__


def _evidence_record(value: object) -> EvidenceRecord:
    return _same(
        value,
        EvidenceRecord,
        lambda e: EvidenceRecord(
            tenant_id=e.tenant_id, review_id=e.review_id, question=e.question, result=e.result
        ),
    )


def revalidated_evidence(value: object) -> EvidenceRecord:
    return _run(lambda: _evidence_record(value), InvalidStageValueError)


# --- call rejections ------------------------------------------------------------------------------


@dataclass(frozen=True, init=False, repr=False)
class CallRejection:
    """A text-free M5b rejection stored on a call, without its question ID (checked by the
    caller, binding rule B6). Valid iff the matching ``ProvenanceRejection`` is valid. A pure
    domain value: it never builds an ``evidenceguard_agents`` value."""

    stage: StageKind
    reason: RejectionReason
    item_index: int | None
    citation_index: int | None
    rejected_count: int

    def __init__(
        self,
        *,
        stage: StageKind,
        reason: RejectionReason,
        item_index: int | None,
        citation_index: int | None,
        rejected_count: int,
        **unknown: object,
    ) -> None:
        def build() -> None:
            _require(not unknown and type(stage) is StageKind and type(reason) is RejectionReason)
            ProvenanceRejection(
                stage=stage.rejection_stage,
                question_id=PLACEHOLDER_QUESTION_ID,
                reason=reason,
                item_index=item_index,
                citation_index=citation_index,
                rejected_count=rejected_count,
            )
            object.__setattr__(self, "stage", stage)
            object.__setattr__(self, "reason", reason)
            object.__setattr__(self, "item_index", item_index)
            object.__setattr__(self, "citation_index", citation_index)
            object.__setattr__(self, "rejected_count", rejected_count)

        _run(build, InvalidStageValueError)

    @classmethod
    def from_rejection(cls, rejection: ProvenanceRejection) -> "CallRejection":
        """Take the stage, reason, positions and count of a ``ProvenanceRejection``; its question
        ID is dropped (the caller must already have checked it)."""

        def build() -> CallRejection:
            checked = _provenance_rejection(rejection)
            return cls(
                stage=_rejection_stage_kind(checked.stage),
                reason=checked.reason,
                item_index=checked.item_index,
                citation_index=checked.citation_index,
                rejected_count=checked.rejected_count,
            )

        return _run(build, InvalidStageValueError)

    def to_rejection(self, question_id: str) -> ProvenanceRejection:
        """The M5b ``ProvenanceRejection`` for ``question_id`` (domain to domain)."""

        def build() -> ProvenanceRejection:
            _require(is_question_id(question_id))
            return ProvenanceRejection(
                stage=self.stage.rejection_stage,
                question_id=question_id,
                reason=self.reason,
                item_index=self.item_index,
                citation_index=self.citation_index,
                rejected_count=self.rejected_count,
            )

        return _run(build, InvalidStageValueError)

    @property
    def stage_reason(self) -> UnresolvedReason:
        """The M5b-F mapping: ``citation_rejected`` or ``invalid_output``."""
        check = self.to_rejection(PLACEHOLDER_QUESTION_ID).provenance_check
        return UnresolvedReason(check)

    def __repr__(self) -> str:
        return (
            f"CallRejection(stage={self.stage.value!r}, reason={self.reason.value!r}, "
            f"item_index={self.item_index}, citation_index={self.citation_index}, "
            f"rejected_count={self.rejected_count})"
        )

    __str__ = __repr__


def _call_rejection(value: object) -> CallRejection:
    return _same(
        value,
        CallRejection,
        lambda r: CallRejection(
            stage=r.stage,
            reason=r.reason,
            item_index=r.item_index,
            citation_index=r.citation_index,
            rejected_count=r.rejected_count,
        ),
    )


# --- call records ---------------------------------------------------------------------------------


def _usage(value: object) -> ModelUsage:
    return _same(value, ModelUsage, lambda u: ModelUsage(u.input_tokens, u.output_tokens))


def completion_shape_holds(
    *,
    model_requested: str,
    outcome: CallOutcome,
    dispatched: bool,
    model_used: str | None,
    usage: ModelUsage | None,
    latency_ms: int | None,
) -> bool:
    """The ADR-0019 field combination of ``outcome`` (output aside)."""
    has_response = model_used is not None and usage is not None
    if (model_used is None) != (usage is None):
        return False
    if outcome in _RESPONSE_OUTCOMES:
        return dispatched and has_response and model_used == model_requested
    if outcome is CallOutcome.MODEL_MISMATCH:
        return dispatched and has_response and model_used != model_requested
    if outcome is CallOutcome.TIMEOUT:
        return dispatched and not has_response
    return not has_response and (dispatched or latency_ms is None)


@dataclass(frozen=True, init=False, repr=False)
class CallRecord:
    """One reservation of a stage's provider call, ``started`` before dispatch and
    ``completed`` afterwards. Raw model output is never part of it."""

    tenant_id: UUID
    review_id: UUID
    job_id: UUID
    question_id: str
    stage: StageKind
    sequence: int
    call_kind: CallKind
    request_basis: RequestBasis
    request_sha256: str
    prompt_sha256: str
    model_requested: str
    max_output_tokens: int
    timeout_ms: int
    evidence_sha256: str | None
    dependency_sha256: str | None
    job_attempt: int
    state: ReservationState
    started_at: datetime
    completed_at: datetime | None
    outcome: CallOutcome | None
    dispatched: bool | None
    model_used: str | None
    usage: ModelUsage | None
    latency_ms: int | None
    rejection: CallRejection | None

    def __init__(
        self,
        *,
        tenant_id: UUID,
        review_id: UUID,
        job_id: UUID,
        question_id: str,
        stage: StageKind,
        sequence: int,
        call_kind: CallKind,
        request_basis: RequestBasis,
        request_sha256: str,
        prompt_sha256: str,
        model_requested: str,
        max_output_tokens: int,
        timeout_ms: int,
        evidence_sha256: str | None,
        dependency_sha256: str | None,
        job_attempt: int,
        state: ReservationState,
        started_at: datetime,
        completed_at: datetime | None = None,
        outcome: CallOutcome | None = None,
        dispatched: bool | None = None,
        model_used: str | None = None,
        usage: ModelUsage | None = None,
        latency_ms: int | None = None,
        rejection: CallRejection | None = None,
        **unknown: object,
    ) -> None:
        def build() -> None:
            _require(not unknown)
            _require(all(type(v) is UUID for v in (tenant_id, review_id, job_id)))
            _require(is_question_id(question_id) and type(stage) is StageKind)
            _require(_is_int(sequence, 1, MAX_CALLS))
            _require(type(call_kind) is CallKind and type(request_basis) is RequestBasis)
            _require((sequence == 1) == (call_kind is CallKind.INITIAL))
            _require(call_kind is not CallKind.INITIAL or request_basis is RequestBasis.ORIGINAL)
            _require(call_kind is not CallKind.REPAIR or request_basis is RequestBasis.REPAIRED)
            _require(_is_sha256(request_sha256) and _is_sha256(prompt_sha256))
            _require(is_model_id(model_requested))
            _require(_is_int(max_output_tokens, 1, MAX_OUTPUT_TOKENS))
            _require(_is_int(timeout_ms, MIN_TIMEOUT_MS, MAX_TIMEOUT_MS))
            _require(_is_optional_sha256(evidence_sha256))
            _require(_is_optional_sha256(dependency_sha256))
            _require((evidence_sha256 is not None) == (stage is StageKind.VERIFICATION))
            _require((dependency_sha256 is not None) == (stage is StageKind.ANALYSIS))
            _require(_is_int(job_attempt, 1, MAX_JOB_ATTEMPT))
            _require(type(state) is ReservationState)
            started = _utc(started_at)
            completed = _optional_utc(completed_at)
            checked_usage = None if usage is None else _usage(usage)
            checked_rejection = None if rejection is None else _call_rejection(rejection)
            if state is ReservationState.STARTED:
                _require(
                    completed is None
                    and outcome is None
                    and dispatched is None
                    and model_used is None
                    and usage is None
                    and latency_ms is None
                    and rejection is None
                )
            else:
                _require(completed is not None and type(outcome) is CallOutcome)
                _require(type(dispatched) is bool)
                _require(model_used is None or is_model_id(model_used))
                _require(latency_ms is None or _is_int(latency_ms, 0, LATENCY_MS_BOUND))
                assert isinstance(outcome, CallOutcome) and isinstance(dispatched, bool)
                _require(
                    completion_shape_holds(
                        model_requested=model_requested,
                        outcome=outcome,
                        dispatched=dispatched,
                        model_used=model_used,
                        usage=checked_usage,
                        latency_ms=latency_ms,
                    )
                )
                if checked_rejection is not None:
                    _require(outcome is CallOutcome.COMPLETED)
                    _require(checked_rejection.stage is stage)
            for name, value in (
                ("tenant_id", tenant_id),
                ("review_id", review_id),
                ("job_id", job_id),
                ("question_id", question_id),
                ("stage", stage),
                ("sequence", sequence),
                ("call_kind", call_kind),
                ("request_basis", request_basis),
                ("request_sha256", request_sha256),
                ("prompt_sha256", prompt_sha256),
                ("model_requested", model_requested),
                ("max_output_tokens", max_output_tokens),
                ("timeout_ms", timeout_ms),
                ("evidence_sha256", evidence_sha256),
                ("dependency_sha256", dependency_sha256),
                ("job_attempt", job_attempt),
                ("state", state),
                ("started_at", started),
                ("completed_at", completed),
                ("outcome", outcome),
                ("dispatched", dispatched),
                ("model_used", model_used),
                ("usage", checked_usage),
                ("latency_ms", latency_ms),
                ("rejection", checked_rejection),
            ):
                object.__setattr__(self, name, value)

        _run(build, InvalidStageValueError)

    @property
    def is_success(self) -> bool:
        return (
            self.state is ReservationState.COMPLETED
            and self.outcome is CallOutcome.COMPLETED
            and self.rejection is None
        )

    def __repr__(self) -> str:
        outcome = None if self.outcome is None else self.outcome.value
        return (
            f"CallRecord(question_id={self.question_id!r}, stage={self.stage.value!r}, "
            f"sequence={self.sequence}, call_kind={self.call_kind.value!r}, "
            f"state={self.state.value!r}, outcome={outcome!r}, job_attempt={self.job_attempt}, "
            f"request_sha256={self.request_sha256!r})"
        )

    __str__ = __repr__


def _call(value: object) -> CallRecord:
    return _same(
        value,
        CallRecord,
        lambda c: CallRecord(
            tenant_id=c.tenant_id,
            review_id=c.review_id,
            job_id=c.job_id,
            question_id=c.question_id,
            stage=c.stage,
            sequence=c.sequence,
            call_kind=c.call_kind,
            request_basis=c.request_basis,
            request_sha256=c.request_sha256,
            prompt_sha256=c.prompt_sha256,
            model_requested=c.model_requested,
            max_output_tokens=c.max_output_tokens,
            timeout_ms=c.timeout_ms,
            evidence_sha256=c.evidence_sha256,
            dependency_sha256=c.dependency_sha256,
            job_attempt=c.job_attempt,
            state=c.state,
            started_at=c.started_at,
            completed_at=c.completed_at,
            outcome=c.outcome,
            dispatched=c.dispatched,
            model_used=c.model_used,
            usage=c.usage,
            latency_ms=c.latency_ms,
            rejection=c.rejection,
        ),
    )


# --- stage content encodings ----------------------------------------------------------------------


def _citation_object(citation: Citation) -> dict[str, Any]:
    return {
        "document_revision_id": str(citation.document_revision_id),
        "chunk_id": str(citation.chunk_id),
        "source_type": citation.source_type.value,
        "quote": citation.quote,
        "authenticity": citation.authenticity.value,
    }


def _verified_object(verified: VerifiedQuestion) -> dict[str, Any]:
    verification = verified.verification
    return {
        "canonical": VERIFIED_CANONICAL,
        "tenant_id": str(verified.tenant_id),
        "review_id": str(verified.review_id),
        "question_id": verified.question_id,
        "snapshot_sha256": verified.snapshot_sha256,
        "request_sha256": verified.request_sha256,
        "match_rules": verified.match_rules,
        "verification": {
            "verdict": verification.verdict.value,
            "evidence_status": verification.evidence_status.value,
            "rationale": verification.rationale,
        },
        "claims": [
            {"text": claim.text, "citation_indexes": list(claim.citation_indexes)}
            for claim in verified.claims
        ],
        "citations": [
            {
                **_citation_object(accepted.citation),
                "document_id": str(accepted.document_id),
                "match": {
                    "kind": accepted.match.kind.value,
                    "text_start": accepted.match.text_start,
                    "text_end": accepted.match.text_end,
                    "source_char_start": accepted.match.source_char_start,
                    "source_char_end": accepted.match.source_char_end,
                    "occurrences": accepted.match.occurrences,
                },
            }
            for accepted in verified.provenance
        ],
    }


def _analyzed_object(analyzed: AnalyzedQuestion) -> dict[str, Any]:
    return {
        "canonical": ANALYZED_CANONICAL,
        "tenant_id": str(analyzed.tenant_id),
        "review_id": str(analyzed.review_id),
        "question_id": analyzed.question_id,
        "request_sha256": analyzed.request_sha256,
        "findings": [
            {
                "finding_id": str(finding.finding_id),
                "question_ids": list(finding.question_ids),
                "title": finding.title,
                "severity": finding.severity.value,
                "statement": finding.statement,
                "evidence_status": finding.evidence_status.value,
                "citations": [_citation_object(citation) for citation in finding.citations],
                "follow_up_questions": list(follow_ups),
            }
            for finding, follow_ups in zip(
                analyzed.findings, analyzed.follow_up_questions, strict=True
            )
        ],
    }


def _verified_admitted(verified: VerifiedQuestion) -> bool:
    return all(
        _admitted(accepted.match.source_char_start) and _admitted(accepted.match.source_char_end)
        for accepted in verified.provenance
    )


def encode_verified(verified: VerifiedQuestion) -> bytes:
    """The ``eg-review-stage-verified-v1`` bytes (``InvalidStageValueError`` for an invalid value
    or an inherited integer outside the admission range)."""

    def build() -> bytes:
        checked = _verified(verified)
        _require(_verified_admitted(checked))
        return _canonical(_verified_object(checked))

    return _run(build, InvalidStageValueError)


def encode_analyzed(analyzed: AnalyzedQuestion) -> bytes:
    """The ``eg-review-stage-analyzed-v1`` bytes."""
    return _run(lambda: _canonical(_analyzed_object(_analyzed(analyzed))), InvalidStageValueError)


def dependency_canonical(
    *,
    tenant_id: UUID,
    review_id: UUID,
    question_id: str,
    question_sha256: str,
    owner_outcome: StageOutcome,
    owner_content_sha256: str | None,
    owner_reason: UnresolvedReason | None,
) -> bytes:
    """The ``eg-review-stage-dependency-v1`` bytes: the owner verification is ``verified`` with
    a content digest and no reason, or ``unresolved`` with a reason and no digest; ``shared`` is
    always empty in v1 (P9)."""

    def build() -> bytes:
        _require(type(tenant_id) is UUID and type(review_id) is UUID)
        _require(is_question_id(question_id) and _is_sha256(question_sha256))
        _require(type(owner_outcome) is StageOutcome)
        if owner_outcome is StageOutcome.VERIFIED:
            _require(_is_sha256(owner_content_sha256) and owner_reason is None)
        else:
            _require(owner_outcome is StageOutcome.UNRESOLVED and owner_content_sha256 is None)
            _require(type(owner_reason) is UnresolvedReason)
            _require(owner_reason is not UnresolvedReason.VERIFICATION_UNRESOLVED)
        return _canonical(
            {
                "canonical": DEPENDENCY_CANONICAL,
                "tenant_id": str(tenant_id),
                "review_id": str(review_id),
                "question_id": question_id,
                "question_sha256": question_sha256,
                "owner": {
                    "outcome": owner_outcome.value,
                    "content_sha256": owner_content_sha256,
                    "unresolved_reason": None if owner_reason is None else owner_reason.value,
                },
                "shared": [],
            }
        )

    return _run(build, InvalidStageValueError)


def dependency_sha256(
    *,
    tenant_id: UUID,
    review_id: UUID,
    question_id: str,
    question_sha256: str,
    owner_outcome: StageOutcome,
    owner_content_sha256: str | None,
    owner_reason: UnresolvedReason | None,
) -> str:
    return _sha256(
        dependency_canonical(
            tenant_id=tenant_id,
            review_id=review_id,
            question_id=question_id,
            question_sha256=question_sha256,
            owner_outcome=owner_outcome,
            owner_content_sha256=owner_content_sha256,
            owner_reason=owner_reason,
        )
    )


# --- stage records --------------------------------------------------------------------------------


class StageShape(StrEnum):
    """The M5e-C shapes; derived from a ``StageRecord``'s fields."""

    S1 = "S1"
    S2 = "S2"
    U1 = "U1"
    U2 = "U2"
    U3 = "U3"
    U4 = "U4"
    U5 = "U5"
    U6 = "U6"


def _shape(
    stage: StageKind,
    outcome: StageOutcome,
    reason: UnresolvedReason | None,
    has_call: bool,
    has_evidence: bool,
    has_dependency: bool,
    content: object,
) -> StageShape:
    """The one M5e-C shape these fields satisfy, or ``_Invalid``."""
    verification = stage is StageKind.VERIFICATION
    _require(has_dependency == (not verification))
    if outcome is StageOutcome.VERIFIED:
        _require(verification and reason is None and has_call and has_evidence)
        _require(type(content) is VerifiedQuestion)
        return StageShape.S1
    if outcome is StageOutcome.ANALYZED:
        _require(not verification and reason is None and has_call and not has_evidence)
        _require(type(content) is AnalyzedQuestion)
        return StageShape.S2
    _require(outcome is StageOutcome.UNRESOLVED and type(reason) is UnresolvedReason)
    _require(content is None)
    if reason is UnresolvedReason.EVIDENCE_TOO_LARGE:
        _require(verification and not has_call and not has_evidence)
        return StageShape.U4
    if reason is UnresolvedReason.VERIFICATION_UNRESOLVED:
        _require(not verification and not has_call and not has_evidence)
        return StageShape.U3
    _require(has_evidence == verification)
    if reason is UnresolvedReason.REQUEST_TOO_LARGE:
        _require(not has_call)
        return StageShape.U5
    _require(has_call)
    if reason is UnresolvedReason.REPAIR_REQUEST_TOO_LARGE:
        return StageShape.U6
    if reason is UnresolvedReason.CALL_ABANDONED:
        return StageShape.U2
    return StageShape.U1


@dataclass(frozen=True, init=False, repr=False)
class StageRecord:
    """A committed stage: a success with its content (S1/S2) or an unresolved outcome (U1-U6).
    The only reusable success; never overwritten."""

    tenant_id: UUID
    review_id: UUID
    job_id: UUID
    question_id: str
    stage: StageKind
    outcome: StageOutcome
    unresolved_reason: UnresolvedReason | None
    call_sequence: int | None
    request_sha256: str | None
    evidence_sha256: str | None
    dependency_sha256: str | None
    content: VerifiedQuestion | AnalyzedQuestion | None
    job_attempt: int
    committed_at: datetime
    shape: StageShape = field(init=False)
    content_canonical: bytes | None = field(init=False)
    content_sha256: str | None = field(init=False)

    def __init__(
        self,
        *,
        tenant_id: UUID,
        review_id: UUID,
        job_id: UUID,
        question_id: str,
        stage: StageKind,
        outcome: StageOutcome,
        unresolved_reason: UnresolvedReason | None,
        call_sequence: int | None,
        request_sha256: str | None,
        evidence_sha256: str | None,
        dependency_sha256: str | None,
        content: VerifiedQuestion | AnalyzedQuestion | None,
        job_attempt: int,
        committed_at: datetime,
        **unknown: object,
    ) -> None:
        def build() -> None:
            _require(not unknown)
            _require(all(type(v) is UUID for v in (tenant_id, review_id, job_id)))
            _require(is_question_id(question_id))
            _require(type(stage) is StageKind and type(outcome) is StageOutcome)
            _require(unresolved_reason is None or type(unresolved_reason) is UnresolvedReason)
            _require(call_sequence is None or _is_int(call_sequence, 1, MAX_CALLS))
            _require((call_sequence is None) == (request_sha256 is None))
            _require(_is_optional_sha256(request_sha256))
            _require(_is_optional_sha256(evidence_sha256))
            _require(_is_optional_sha256(dependency_sha256))
            _require(_is_int(job_attempt, 1, MAX_JOB_ATTEMPT))
            stamp = _utc(committed_at)
            shape = _shape(
                stage,
                outcome,
                unresolved_reason,
                call_sequence is not None,
                evidence_sha256 is not None,
                dependency_sha256 is not None,
                content,
            )
            checked: VerifiedQuestion | AnalyzedQuestion | None = None
            canonical: bytes | None = None
            if shape is StageShape.S1:
                verified = _verified(content)
                _require(_verified_admitted(verified))
                canonical = _canonical(_verified_object(verified))
                _require(len(canonical) <= MAX_VERIFIED_BYTES)
                checked = verified
            elif shape is StageShape.S2:
                analyzed = _analyzed(content)
                canonical = _canonical(_analyzed_object(analyzed))
                _require(len(canonical) <= MAX_ANALYZED_BYTES)
                checked = analyzed
            if checked is not None:
                _require(checked.tenant_id == tenant_id and checked.review_id == review_id)
                _require(checked.question_id == question_id)
                _require(checked.request_sha256 == request_sha256)
            for name, value in (
                ("tenant_id", tenant_id),
                ("review_id", review_id),
                ("job_id", job_id),
                ("question_id", question_id),
                ("stage", stage),
                ("outcome", outcome),
                ("unresolved_reason", unresolved_reason),
                ("call_sequence", call_sequence),
                ("request_sha256", request_sha256),
                ("evidence_sha256", evidence_sha256),
                ("dependency_sha256", dependency_sha256),
                ("content", checked),
                ("job_attempt", job_attempt),
                ("committed_at", stamp),
                ("shape", shape),
                ("content_canonical", canonical),
                ("content_sha256", None if canonical is None else _sha256(canonical)),
            ):
                object.__setattr__(self, name, value)

        _run(build, InvalidStageValueError)

    def __repr__(self) -> str:
        reason = None if self.unresolved_reason is None else self.unresolved_reason.value
        return (
            f"StageRecord(question_id={self.question_id!r}, stage={self.stage.value!r}, "
            f"shape={self.shape.value!r}, outcome={self.outcome.value!r}, "
            f"unresolved_reason={reason!r}, call_sequence={self.call_sequence}, "
            f"content_sha256={self.content_sha256!r})"
        )

    __str__ = __repr__


def _stage_record(value: object) -> StageRecord:
    return _same(
        value,
        StageRecord,
        lambda s: StageRecord(
            tenant_id=s.tenant_id,
            review_id=s.review_id,
            job_id=s.job_id,
            question_id=s.question_id,
            stage=s.stage,
            outcome=s.outcome,
            unresolved_reason=s.unresolved_reason,
            call_sequence=s.call_sequence,
            request_sha256=s.request_sha256,
            evidence_sha256=s.evidence_sha256,
            dependency_sha256=s.dependency_sha256,
            content=s.content,
            job_attempt=s.job_attempt,
            committed_at=s.committed_at,
        ),
    )


def revalidated_stage(value: object) -> StageRecord:
    return _run(lambda: _stage_record(value), InvalidStageValueError)


# --- plans ----------------------------------------------------------------------------------------


@dataclass(frozen=True, init=False, repr=False)
class PlanReuse:
    """T0: the committed stage is reused; no call."""

    stage: StageRecord

    def __init__(self, *, stage: StageRecord, **unknown: object) -> None:
        def build() -> None:
            _require(not unknown)
            object.__setattr__(self, "stage", _stage_record(stage))

        _run(build, InvalidStageValueError)

    def __repr__(self) -> str:
        return f"PlanReuse(stage={self.stage!r})"

    __str__ = __repr__


@dataclass(frozen=True, init=False, repr=False)
class PlanDispatch:
    """T1, T3, T5, T7: the next reservation the budget allows."""

    sequence: int
    call_kind: CallKind
    request_basis: RequestBasis
    predecessor: int | None
    trigger: int | None
    required_request_sha256: str | None
    original_request_sha256: str | None

    def __init__(
        self,
        *,
        sequence: int,
        call_kind: CallKind,
        request_basis: RequestBasis,
        predecessor: int | None,
        trigger: int | None,
        required_request_sha256: str | None,
        original_request_sha256: str | None,
        **unknown: object,
    ) -> None:
        def build() -> None:
            _require(not unknown and _is_int(sequence, 1, MAX_CALLS))
            _require(type(call_kind) is CallKind and type(request_basis) is RequestBasis)
            _require(_is_optional_sha256(required_request_sha256))
            _require(_is_optional_sha256(original_request_sha256))
            if call_kind is CallKind.INITIAL:
                _require(sequence == 1 and request_basis is RequestBasis.ORIGINAL)
                _require(predecessor is None and trigger is None)
                _require(required_request_sha256 is None and original_request_sha256 is None)
            elif call_kind is CallKind.RETRY:
                _require(sequence >= 2 and predecessor == sequence - 1)
                _require(required_request_sha256 is not None and original_request_sha256 is None)
                if request_basis is RequestBasis.REPAIRED:
                    _require(_is_int(trigger, 1, sequence - 2))
                else:
                    _require(trigger is None)
            else:
                _require(sequence >= 2 and request_basis is RequestBasis.REPAIRED)
                _require(predecessor == sequence - 1 and trigger == sequence - 1)
                _require(required_request_sha256 is None and original_request_sha256 is not None)
            object.__setattr__(self, "sequence", sequence)
            object.__setattr__(self, "call_kind", call_kind)
            object.__setattr__(self, "request_basis", request_basis)
            object.__setattr__(self, "predecessor", predecessor)
            object.__setattr__(self, "trigger", trigger)
            object.__setattr__(self, "required_request_sha256", required_request_sha256)
            object.__setattr__(self, "original_request_sha256", original_request_sha256)

        _run(build, InvalidStageValueError)

    def __repr__(self) -> str:
        return (
            f"PlanDispatch(sequence={self.sequence}, call_kind={self.call_kind.value!r}, "
            f"request_basis={self.request_basis.value!r}, predecessor={self.predecessor}, "
            f"trigger={self.trigger})"
        )

    __str__ = __repr__


@dataclass(frozen=True, init=False, repr=False)
class PlanInFlight:
    """T2: the last call is ``started`` by the current attempt."""

    sequence: int
    request_sha256: str

    def __init__(self, *, sequence: int, request_sha256: str, **unknown: object) -> None:
        def build() -> None:
            _require(not unknown and _is_int(sequence, 1, MAX_CALLS))
            _require(_is_sha256(request_sha256))
            object.__setattr__(self, "sequence", sequence)
            object.__setattr__(self, "request_sha256", request_sha256)

        _run(build, InvalidStageValueError)

    def __repr__(self) -> str:
        return f"PlanInFlight(sequence={self.sequence}, request_sha256={self.request_sha256!r})"

    __str__ = __repr__


@dataclass(frozen=True, init=False, repr=False)
class PlanExhausted:
    """T4, T6, T8, T9: the stage must be committed ``unresolved`` with ``reason``."""

    reason: UnresolvedReason
    sequence: int
    request_sha256: str

    def __init__(
        self, *, reason: UnresolvedReason, sequence: int, request_sha256: str, **unknown: object
    ) -> None:
        def build() -> None:
            _require(not unknown and type(reason) is UnresolvedReason)
            _require(reason in EXHAUSTED_REASONS and _is_int(sequence, 1, MAX_CALLS))
            _require(_is_sha256(request_sha256))
            object.__setattr__(self, "reason", reason)
            object.__setattr__(self, "sequence", sequence)
            object.__setattr__(self, "request_sha256", request_sha256)

        _run(build, InvalidStageValueError)

    def __repr__(self) -> str:
        return (
            f"PlanExhausted(reason={self.reason.value!r}, sequence={self.sequence}, "
            f"request_sha256={self.request_sha256!r})"
        )

    __str__ = __repr__


type StagePlan = PlanReuse | PlanDispatch | PlanInFlight | PlanExhausted


def _exhausted_reason(last: CallRecord) -> UnresolvedReason:
    """The stage reason for a terminal last call (M5e-B, M5b-F)."""
    if last.rejection is not None:
        return last.rejection.stage_reason
    assert last.outcome is not None
    return UnresolvedReason(last.outcome.value)


def _plan_calls(calls: tuple[CallRecord, ...], current_attempt: int) -> StagePlan:
    """The transition table T1-T9 over calls without a committed stage. A success without a
    stage has no row (V9 refuses it); ``_Invalid`` here is unreachable for a valid history."""
    n = len(calls)
    if n == 0:
        return PlanDispatch(
            sequence=1,
            call_kind=CallKind.INITIAL,
            request_basis=RequestBasis.ORIGINAL,
            predecessor=None,
            trigger=None,
            required_request_sha256=None,
            original_request_sha256=None,
        )
    last = calls[-1]
    if last.state is ReservationState.STARTED:
        if last.job_attempt == current_attempt:
            return PlanInFlight(sequence=last.sequence, request_sha256=last.request_sha256)
        _require(last.job_attempt < current_attempt)
        if n < MAX_CALLS:
            return _retry(calls)
        return PlanExhausted(
            reason=UnresolvedReason.CALL_ABANDONED,
            sequence=last.sequence,
            request_sha256=last.request_sha256,
        )
    outcome = last.outcome
    if outcome in _RETRYABLE:
        if n < MAX_CALLS:
            return _retry(calls)
        return PlanExhausted(
            reason=_exhausted_reason(last),
            sequence=last.sequence,
            request_sha256=last.request_sha256,
        )
    if outcome is CallOutcome.INVALID_OUTPUT or last.rejection is not None:
        repaired = any(call.call_kind is CallKind.REPAIR for call in calls)
        if not repaired and n < MAX_CALLS:
            return PlanDispatch(
                sequence=n + 1,
                call_kind=CallKind.REPAIR,
                request_basis=RequestBasis.REPAIRED,
                predecessor=n,
                trigger=n,
                required_request_sha256=None,
                original_request_sha256=calls[0].request_sha256,
            )
        return PlanExhausted(
            reason=_exhausted_reason(last),
            sequence=last.sequence,
            request_sha256=last.request_sha256,
        )
    _require(outcome in _TERMINAL)
    return PlanExhausted(
        reason=_exhausted_reason(last), sequence=last.sequence, request_sha256=last.request_sha256
    )


def _retry(calls: tuple[CallRecord, ...]) -> PlanDispatch:
    last = calls[-1]
    trigger: int | None = None
    if last.request_basis is RequestBasis.REPAIRED:
        repair = next(call for call in calls if call.call_kind is CallKind.REPAIR)
        trigger = repair.sequence - 1
    return PlanDispatch(
        sequence=len(calls) + 1,
        call_kind=CallKind.RETRY,
        request_basis=last.request_basis,
        predecessor=len(calls),
        trigger=trigger,
        required_request_sha256=last.request_sha256,
        original_request_sha256=None,
    )


# --- stage history --------------------------------------------------------------------------------


def _check_history(
    tenant_id: UUID,
    review_id: UUID,
    job_id: UUID,
    question_id: str,
    stage: StageKind,
    current_attempt: int,
    calls: tuple[CallRecord, ...],
    committed: StageRecord | None,
) -> None:
    """V1-V12 (M5e-D). V1 (rebuilding) happens in the caller; V12 imposes no timestamp order."""
    n = len(calls)
    # V2 identity
    for record in (*calls, *(() if committed is None else (committed,))):
        _require(record.tenant_id == tenant_id and record.review_id == review_id)
        _require(record.job_id == job_id and record.question_id == question_id)
        _require(record.stage is stage)
    # V3 sequences
    _require([call.sequence for call in calls] == list(range(1, n + 1)))
    # V4 attempts
    _require(all(call.job_attempt <= current_attempt for call in calls))
    for previous, following in pairwise(calls):
        _require(previous.job_attempt <= following.job_attempt)
        if previous.state is ReservationState.STARTED:
            _require(previous.job_attempt < following.job_attempt)
    if committed is not None:
        _require(all(committed.job_attempt >= call.job_attempt for call in calls))
        _require(committed.job_attempt <= current_attempt)
    # V5/V6 kinds, bases and repair triggers: every call is what the plan of its prefix allowed
    for index in range(1, n):
        plan = _plan_calls(calls[:index], calls[index].job_attempt)
        _require(type(plan) is PlanDispatch)
        assert isinstance(plan, PlanDispatch)
        call = calls[index]
        _require(plan.sequence == call.sequence and plan.call_kind is call.call_kind)
        _require(plan.request_basis is call.request_basis)
        if plan.required_request_sha256 is not None:
            _require(call.request_sha256 == plan.required_request_sha256)
        if plan.original_request_sha256 is not None:
            _require(call.request_sha256 != plan.original_request_sha256)
    _require(sum(call.call_kind is CallKind.REPAIR for call in calls) <= 1)
    # V7 digests
    originals = {c.request_sha256 for c in calls if c.request_basis is RequestBasis.ORIGINAL}
    repaired = {c.request_sha256 for c in calls if c.request_basis is RequestBasis.REPAIRED}
    _require(len(originals) <= 1 and len(repaired) <= 1 and not originals & repaired)
    # V8 pinned settings and digests
    for attribute in (
        "model_requested",
        "max_output_tokens",
        "timeout_ms",
        "prompt_sha256",
        "evidence_sha256",
        "dependency_sha256",
    ):
        _require(len({getattr(call, attribute) for call in calls}) <= 1)
    # V10 rejections
    for call in calls:
        if call.rejection is not None:
            _require(call.outcome is CallOutcome.COMPLETED and call.rejection.stage is stage)
    # V9 success placement
    successes = [index for index, call in enumerate(calls) if call.is_success]
    _require(not successes or successes == [n - 1])
    if successes:
        _require(committed is not None)
        assert committed is not None
        _require(committed.shape in (StageShape.S1, StageShape.S2))
    if committed is None:
        return
    last = calls[-1] if calls else None
    if committed.shape in (StageShape.S1, StageShape.S2):
        _require(last is not None and last.is_success)
    # references and V11 committed unresolved shapes
    shape = committed.shape
    if shape in (StageShape.U3, StageShape.U4, StageShape.U5):
        _require(n == 0)
        return
    _require(last is not None)
    assert last is not None
    _require(committed.call_sequence == last.sequence)
    _require(committed.request_sha256 == last.request_sha256)
    _require(committed.evidence_sha256 == last.evidence_sha256)
    _require(committed.dependency_sha256 == last.dependency_sha256)
    if shape in (StageShape.S1, StageShape.S2):
        return
    plan = _plan_calls(calls, current_attempt)
    if shape is StageShape.U1:
        _require(last.state is ReservationState.COMPLETED and type(plan) is PlanExhausted)
        assert isinstance(plan, PlanExhausted)
        _require(plan.reason is committed.unresolved_reason)
    elif shape is StageShape.U2:
        _require(n == MAX_CALLS and last.state is ReservationState.STARTED)
        _require(committed.job_attempt > last.job_attempt)
    else:  # U6
        _require(type(plan) is PlanDispatch)
        assert isinstance(plan, PlanDispatch)
        _require(plan.call_kind is CallKind.REPAIR and plan.trigger == last.sequence)


@dataclass(frozen=True, init=False, repr=False)
class StageHistory:
    """One stage's reservations (0-3) and its committed stage, with the canonical job's
    ``current_attempt`` (1-10). Construction enforces V1-V12; failure is
    ``InvalidStageHistoryError``."""

    tenant_id: UUID
    review_id: UUID
    job_id: UUID
    question_id: str
    stage: StageKind
    current_attempt: int
    calls: tuple[CallRecord, ...]
    committed: StageRecord | None

    def __init__(
        self,
        *,
        tenant_id: UUID,
        review_id: UUID,
        job_id: UUID,
        question_id: str,
        stage: StageKind,
        current_attempt: int,
        calls: tuple[CallRecord, ...],
        committed: StageRecord | None,
        **unknown: object,
    ) -> None:
        def build() -> None:
            _require(not unknown)
            _require(all(type(v) is UUID for v in (tenant_id, review_id, job_id)))
            _require(is_question_id(question_id) and type(stage) is StageKind)
            _require(_is_int(current_attempt, 1, MAX_JOB_ATTEMPT))
            _require(type(calls) is tuple and len(calls) <= MAX_CALLS)
            checked_calls = tuple(_call(call) for call in calls)  # V1
            checked_stage = None if committed is None else _stage_record(committed)
            _check_history(
                tenant_id,
                review_id,
                job_id,
                question_id,
                stage,
                current_attempt,
                checked_calls,
                checked_stage,
            )
            object.__setattr__(self, "tenant_id", tenant_id)
            object.__setattr__(self, "review_id", review_id)
            object.__setattr__(self, "job_id", job_id)
            object.__setattr__(self, "question_id", question_id)
            object.__setattr__(self, "stage", stage)
            object.__setattr__(self, "current_attempt", current_attempt)
            object.__setattr__(self, "calls", checked_calls)
            object.__setattr__(self, "committed", checked_stage)

        _run(build, InvalidStageHistoryError)

    def __repr__(self) -> str:
        committed = None if self.committed is None else self.committed.shape.value
        return (
            f"StageHistory(question_id={self.question_id!r}, stage={self.stage.value!r}, "
            f"current_attempt={self.current_attempt}, calls={len(self.calls)}, "
            f"committed={committed!r})"
        )

    __str__ = __repr__


def _history(value: object) -> StageHistory:
    _require(type(value) is StageHistory)
    assert isinstance(value, StageHistory)
    return StageHistory(
        tenant_id=value.tenant_id,
        review_id=value.review_id,
        job_id=value.job_id,
        question_id=value.question_id,
        stage=value.stage,
        current_attempt=value.current_attempt,
        calls=value.calls,
        committed=value.committed,
    )


def plan_stage(history: StageHistory) -> StagePlan:
    """The pure, total planner over valid histories (T0-T9). It never allocates; an argument
    that is not exactly a valid ``StageHistory`` is ``InvalidStageHistoryError``."""
    checked = _run(lambda: _history(history), InvalidStageHistoryError)
    if checked.committed is not None:
        return PlanReuse(stage=checked.committed)
    return _run(
        lambda: _plan_calls(checked.calls, checked.current_attempt), InvalidStageHistoryError
    )


def plan_without_stage(history: StageHistory) -> StagePlan:
    """The plan of ``history``'s calls as if no stage were committed (the M5e-C shape rule)."""
    checked = _run(lambda: _history(history), InvalidStageHistoryError)
    return _run(
        lambda: _plan_calls(checked.calls, checked.current_attempt), InvalidStageHistoryError
    )


def _plan(value: object) -> StagePlan:
    """A supplied plan rebuilt through its own constructor (exact variant types only)."""
    if type(value) is PlanReuse:
        assert isinstance(value, PlanReuse)
        return PlanReuse(stage=value.stage)
    if type(value) is PlanDispatch:
        assert isinstance(value, PlanDispatch)
        return PlanDispatch(
            sequence=value.sequence,
            call_kind=value.call_kind,
            request_basis=value.request_basis,
            predecessor=value.predecessor,
            trigger=value.trigger,
            required_request_sha256=value.required_request_sha256,
            original_request_sha256=value.original_request_sha256,
        )
    if type(value) is PlanInFlight:
        assert isinstance(value, PlanInFlight)
        return PlanInFlight(sequence=value.sequence, request_sha256=value.request_sha256)
    _require(type(value) is PlanExhausted)
    assert isinstance(value, PlanExhausted)
    return PlanExhausted(
        reason=value.reason, sequence=value.sequence, request_sha256=value.request_sha256
    )


# --- in-run state and trusted results -------------------------------------------------------------


@dataclass(frozen=True, init=False, repr=False)
class StageState:
    """The in-run read: the history, its plan and the digest references. Constructor-validated
    and digest-checked; **not** provenance-trusted."""

    history: StageHistory
    plan: StagePlan
    evidence_sha256: str | None
    dependency_sha256: str | None

    def __init__(
        self,
        *,
        history: StageHistory,
        plan: StagePlan,
        evidence_sha256: str | None,
        dependency_sha256: str | None,
        **unknown: object,
    ) -> None:
        def build() -> None:
            _require(not unknown)
            checked = _history(history)
            rebuilt_plan = _plan(plan)
            _require(rebuilt_plan == plan_stage(checked))
            _require(_is_optional_sha256(evidence_sha256))
            _require(_is_optional_sha256(dependency_sha256))
            committed = checked.committed
            if checked.stage is StageKind.VERIFICATION:
                _require(dependency_sha256 is None)
                _require(all(call.evidence_sha256 == evidence_sha256 for call in checked.calls))
                if committed is not None:
                    if committed.shape is StageShape.U4:
                        _require(evidence_sha256 is None)
                    else:
                        _require(committed.evidence_sha256 == evidence_sha256)
            else:
                _require(evidence_sha256 is None)
                _require(all(call.dependency_sha256 == dependency_sha256 for call in checked.calls))
                if committed is not None:
                    _require(committed.dependency_sha256 == dependency_sha256)
            object.__setattr__(self, "history", checked)
            object.__setattr__(self, "plan", rebuilt_plan)
            object.__setattr__(self, "evidence_sha256", evidence_sha256)
            object.__setattr__(self, "dependency_sha256", dependency_sha256)

        _run(build, InvalidStageValueError)

    def __repr__(self) -> str:
        return f"StageState(history={self.history!r}, plan={self.plan!r})"

    __str__ = __repr__


@dataclass(frozen=True, init=False, repr=False)
class TrustedQuestionStages:
    """One planned question after the trusted reload: its evidence (rechecked against database
    chunks) and both stages with content replaced by the ``recheck_verified`` /
    ``recheck_analyzed`` results."""

    question: EvidenceQuestion
    evidence: QuestionEvidence | None
    verification: StageRecord | None
    analysis: StageRecord | None
    verification_history: StageHistory
    analysis_history: StageHistory

    def __init__(
        self,
        *,
        question: EvidenceQuestion,
        evidence: QuestionEvidence | None,
        verification: StageRecord | None,
        analysis: StageRecord | None,
        verification_history: StageHistory,
        analysis_history: StageHistory,
        **unknown: object,
    ) -> None:
        def build() -> None:
            _require(not unknown)
            checked_question = _question(question)
            verifying = _history(verification_history)
            analyzing = _history(analysis_history)
            _require(verifying.stage is StageKind.VERIFICATION)
            _require(analyzing.stage is StageKind.ANALYSIS)
            for history in (verifying, analyzing):
                _require(history.question_id == checked_question.question_id)
            checked_verification = None if verification is None else _stage_record(verification)
            checked_analysis = None if analysis is None else _stage_record(analysis)
            _require(checked_verification == verifying.committed)
            _require(checked_analysis == analyzing.committed)
            checked_evidence = None if evidence is None else _question_evidence(evidence)
            if checked_evidence is not None:
                _require(checked_evidence.question == checked_question)
                _require(checked_evidence.tenant_id == verifying.tenant_id)
                _require(checked_evidence.review_id == verifying.review_id)
            object.__setattr__(self, "question", checked_question)
            object.__setattr__(self, "evidence", checked_evidence)
            object.__setattr__(self, "verification", verifying.committed)
            object.__setattr__(self, "analysis", analyzing.committed)
            object.__setattr__(self, "verification_history", verifying)
            object.__setattr__(self, "analysis_history", analyzing)

        _run(build, InvalidStageValueError)

    def __repr__(self) -> str:
        def shape(record: StageRecord | None) -> str | None:
            return None if record is None else record.shape.value

        return (
            f"TrustedQuestionStages(question_id={self.question.question_id!r}, "
            f"verification={shape(self.verification)!r}, analysis={shape(self.analysis)!r})"
        )

    __str__ = __repr__


def _trusted_question(value: object) -> TrustedQuestionStages:
    """A supplied ``TrustedQuestionStages`` rebuilt through its constructor, so every nested
    value is validated again rather than retained after an exact-class check."""
    _require(type(value) is TrustedQuestionStages)
    assert isinstance(value, TrustedQuestionStages)
    return TrustedQuestionStages(
        question=value.question,
        evidence=value.evidence,
        verification=value.verification,
        analysis=value.analysis,
        verification_history=value.verification_history,
        analysis_history=value.analysis_history,
    )


@dataclass(frozen=True, init=False, repr=False)
class TrustedStages:
    """The trusted reload of a review's M5e rows. The constructor checks consistency only; it
    cannot prove that the values came from the database (only ``load_trusted_stages`` builds
    it)."""

    tenant_id: UUID
    review_id: UUID
    job_id: UUID
    job_attempt: int
    questions: tuple[TrustedQuestionStages, ...]

    def __init__(
        self,
        *,
        tenant_id: UUID,
        review_id: UUID,
        job_id: UUID,
        job_attempt: int,
        questions: tuple[TrustedQuestionStages, ...],
        **unknown: object,
    ) -> None:
        def build() -> None:
            _require(not unknown)
            _require(all(type(v) is UUID for v in (tenant_id, review_id, job_id)))
            _require(_is_int(job_attempt, 0, MAX_JOB_ATTEMPT))
            _require(type(questions) is tuple and len(questions) <= MAX_PLANNED_QUESTIONS)
            checked = tuple(_trusted_question(item) for item in questions)
            identifiers = [item.question.question_id for item in checked]
            _require(len(set(identifiers)) == len(identifiers))
            for item in checked:
                for history in (item.verification_history, item.analysis_history):
                    _require(history.tenant_id == tenant_id and history.review_id == review_id)
                    _require(history.job_id == job_id)
                    _require(history.current_attempt == job_attempt)
            object.__setattr__(self, "tenant_id", tenant_id)
            object.__setattr__(self, "review_id", review_id)
            object.__setattr__(self, "job_id", job_id)
            object.__setattr__(self, "job_attempt", job_attempt)
            object.__setattr__(self, "questions", checked)

        _run(build, InvalidStageValueError)

    def __repr__(self) -> str:
        return (
            f"TrustedStages(review_id={self.review_id}, job_attempt={self.job_attempt}, "
            f"questions={len(self.questions)})"
        )

    __str__ = __repr__


# --- bounded strict decoding ----------------------------------------------------------------------


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    keys = [key for key, _ in pairs]
    _require(len(set(keys)) == len(keys))
    return dict(pairs)


def _no_float(_: str) -> NoReturn:
    _fail()


def _no_constant(_: str) -> NoReturn:
    _fail()


def _parse_int(text: str) -> int:
    _require(_DIGITS.fullmatch(text) is not None)
    value = int(text)
    _require(value <= MAX_CANONICAL_INT)
    return value


def _load(data: object, cap: int) -> dict[str, Any]:
    """Steps 1-3: cap before parsing, printable ASCII, then a strict parse."""
    _require(type(data) is bytes)
    assert isinstance(data, bytes)
    _require(len(data) <= cap)
    _require(_PRINTABLE.fullmatch(data) is not None)
    parsed = json.loads(
        data.decode("ascii"),
        object_pairs_hook=_pairs,
        parse_float=_no_float,
        parse_int=_parse_int,
        parse_constant=_no_constant,
    )
    _require(type(parsed) is dict)
    assert isinstance(parsed, dict)
    return parsed


def _object(value: object, keys: frozenset[str]) -> dict[str, Any]:
    _require(type(value) is dict)
    assert isinstance(value, dict)
    _require(frozenset(value) == keys)
    return value


def _text(value: object) -> str:
    _require(type(value) is str)
    assert isinstance(value, str)
    return value


def _optional_text(value: object) -> str | None:
    return None if value is None else _text(value)


def _integer(value: object) -> int:
    _require(type(value) is int)
    assert isinstance(value, int)
    return value


def _boolean(value: object) -> bool:
    _require(type(value) is bool)
    assert isinstance(value, bool)
    return value


def _array(value: object) -> list[Any]:
    _require(type(value) is list)
    assert isinstance(value, list)
    return value


def _member[E: StrEnum](kind: type[E], value: object) -> E:
    text = _text(value)
    for member in kind:
        if member.value == text:
            return member
    _fail()


def _finish[T](data: bytes, sha256: object, value: T, encoded: bytes) -> T:
    """Steps 6-7: a byte-identical re-encoding and the stored digest."""
    _require(encoded == data)
    _require(_is_sha256(sha256) and _sha256(data) == sha256)
    return value


_SPAN_KEYS = frozenset({"line_start", "line_end", "char_start", "char_end"})
_HIT_KEYS = frozenset({"channel", "query_position", "rank", "score"})
_EVIDENCE_KEYS = frozenset(
    {
        "text",
        "content_sha256",
        "ordinal",
        "section_path",
        "is_table",
        "body",
        "header",
        "document_key",
        "title",
        "revision_no",
        "version_label",
        "effective_date",
        "source_type",
        "authenticity",
    }
)
_ITEM_KEYS = frozenset({"chunk_id", "revision_id", "document_id", "fused_rank", "hits", "evidence"})
_RECORD_KEYS = frozenset(
    {
        "canonical",
        "tenant_id",
        "review_id",
        "question_id",
        "question_sha256",
        "snapshot_sha256",
        "query_count",
        "k",
        "vector_skipped",
        "items",
    }
)


def _decoded_span(value: object) -> SourceSpan:
    span = _object(value, _SPAN_KEYS)
    return SourceSpan(
        _integer(span["line_start"]),
        _integer(span["line_end"]),
        _integer(span["char_start"]),
        _integer(span["char_end"]),
    )


def _decoded_item(value: object) -> RetrievedChunk:
    item = _object(value, _ITEM_KEYS)
    chunk_id = _decoded_uuid(item["chunk_id"])
    hits: list[ChannelHit] = []
    for raw in _array(item["hits"]):
        hit = _object(raw, _HIT_KEYS)
        channel = _text(hit["channel"])
        _require(channel in ("lexical", "vector"))
        hits.append(
            ChannelHit(
                _integer(hit["query_position"]),
                "lexical" if channel == "lexical" else "vector",
                _integer(hit["rank"]),
                _decoded_float(hit["score"]),
            )
        )
    evidence = _object(item["evidence"], _EVIDENCE_KEYS)
    header = evidence["header"]
    chunk = ChunkEvidence(
        chunk_id,
        _text(evidence["text"]),
        _text(evidence["content_sha256"]),
        _integer(evidence["ordinal"]),
        tuple(_text(part) for part in _array(evidence["section_path"])),
        _boolean(evidence["is_table"]),
        _decoded_span(evidence["body"]),
        None if header is None else _decoded_span(header),
        _text(evidence["document_key"]),
        _text(evidence["title"]),
        _integer(evidence["revision_no"]),
        _optional_text(evidence["version_label"]),
        None if evidence["effective_date"] is None else _decoded_date(evidence["effective_date"]),
        _member(SourceType, evidence["source_type"]),
        _member(Authenticity, evidence["authenticity"]),
    )
    score = sum((Fraction(1, RRF_CONSTANT + hit.rank) for hit in hits), Fraction(0))
    return RetrievedChunk(
        chunk_id,
        _decoded_uuid(item["revision_id"]),
        _decoded_uuid(item["document_id"]),
        _integer(item["fused_rank"]),
        score,
        tuple(hits),
        chunk,
    )


def decode_evidence(
    data: bytes,
    *,
    evidence_sha256: str,
    snapshot: RetrievalSnapshot,
    question: EvidenceQuestion,
) -> EvidenceRecord:
    """Decode a stored ``eg-review-question-evidence-v1`` object. The snapshot is not encoded:
    it comes from the trusted review and must have the stored digest; the question is the
    planned one and must have the stored question digest. Any failure is
    ``InvalidStageValueError``."""

    def build() -> EvidenceRecord:
        record = _object(_load(data, MAX_EVIDENCE_BYTES), _RECORD_KEYS)
        _require(record["canonical"] == EVIDENCE_CANONICAL)
        checked_snapshot = revalidate_snapshot(snapshot)
        checked_question = _question(question)
        _require(_text(record["snapshot_sha256"]) == checked_snapshot.sha256)
        _require(_text(record["question_id"]) == checked_question.question_id)
        _require(_is_sha256(record["question_sha256"]))
        items = tuple(_decoded_item(item) for item in _array(record["items"]))
        result = RetrievalResult(
            checked_snapshot,
            _integer(record["query_count"]),
            _integer(record["k"]),
            tuple(_integer(position) for position in _array(record["vector_skipped"])),
            items,
        )
        rebuilt = EvidenceRecord(
            tenant_id=_decoded_uuid(record["tenant_id"]),
            review_id=_decoded_uuid(record["review_id"]),
            question=checked_question,
            result=result,
        )
        _require(rebuilt.question_sha256 == record["question_sha256"])
        assert isinstance(data, bytes)
        return _finish(data, evidence_sha256, rebuilt, rebuilt.canonical)

    return _run(build, InvalidStageValueError)


_CITATION_KEYS = frozenset(
    {"document_revision_id", "chunk_id", "source_type", "quote", "authenticity"}
)
_MATCH_KEYS = frozenset(
    {"kind", "text_start", "text_end", "source_char_start", "source_char_end", "occurrences"}
)
_VERIFIED_KEYS = frozenset(
    {
        "canonical",
        "tenant_id",
        "review_id",
        "question_id",
        "snapshot_sha256",
        "request_sha256",
        "match_rules",
        "verification",
        "claims",
        "citations",
    }
)
_ANALYZED_KEYS = frozenset(
    {"canonical", "tenant_id", "review_id", "question_id", "request_sha256", "findings"}
)
_FINDING_KEYS = frozenset(
    {
        "finding_id",
        "question_ids",
        "title",
        "severity",
        "statement",
        "evidence_status",
        "citations",
        "follow_up_questions",
    }
)


def _decoded_citation(value: dict[str, Any], tenant_id: UUID) -> Citation:
    return Citation(
        tenant_id=tenant_id,
        document_revision_id=_decoded_uuid(value["document_revision_id"]),
        chunk_id=_decoded_uuid(value["chunk_id"]),
        source_type=_member(SourceType, value["source_type"]),
        quote=_text(value["quote"]),
        authenticity=_member(Authenticity, value["authenticity"]),
    )


def decode_verified(data: bytes, *, content_sha256: str) -> VerifiedQuestion:
    """Decode a stored ``eg-review-stage-verified-v1`` object (``InvalidStageValueError``)."""

    def build() -> VerifiedQuestion:
        record = _object(_load(data, MAX_VERIFIED_BYTES), _VERIFIED_KEYS)
        _require(record["canonical"] == VERIFIED_CANONICAL)
        tenant_id = _decoded_uuid(record["tenant_id"])
        question_id = _text(record["question_id"])
        provenance: list[AcceptedCitation] = []
        for raw in _array(record["citations"]):
            entry = _object(raw, _CITATION_KEYS | {"document_id", "match"})
            citation = _decoded_citation(entry, tenant_id)
            match = _object(entry["match"], _MATCH_KEYS)
            provenance.append(
                AcceptedCitation(
                    citation=citation,
                    document_id=_decoded_uuid(entry["document_id"]),
                    match=QuoteMatch(
                        kind=_member(QuoteSpanKind, match["kind"]),
                        text_start=_integer(match["text_start"]),
                        text_end=_integer(match["text_end"]),
                        source_char_start=_integer(match["source_char_start"]),
                        source_char_end=_integer(match["source_char_end"]),
                        quote=citation.quote,
                        occurrences=_integer(match["occurrences"]),
                    ),
                )
            )
        claims = tuple(
            ValidatedClaim(
                text=_text(claim["text"]),
                citation_indexes=tuple(
                    _integer(index) for index in _array(claim["citation_indexes"])
                ),
            )
            for claim in (
                _object(raw, frozenset({"text", "citation_indexes"}))
                for raw in _array(record["claims"])
            )
        )
        verification = _object(
            record["verification"], frozenset({"verdict", "evidence_status", "rationale"})
        )
        verified = VerifiedQuestion(
            tenant_id=tenant_id,
            review_id=_decoded_uuid(record["review_id"]),
            question_id=question_id,
            snapshot_sha256=_text(record["snapshot_sha256"]),
            request_sha256=_text(record["request_sha256"]),
            match_rules=_text(record["match_rules"]),
            verification=Verification(
                tenant_id=tenant_id,
                question_id=question_id,
                verdict=_member(Verdict, verification["verdict"]),
                evidence_status=_member(EvidenceStatus, verification["evidence_status"]),
                citations=tuple(item.citation for item in provenance),
                rationale=_text(verification["rationale"]),
            ),
            claims=claims,
            provenance=tuple(provenance),
        )
        _require(_verified_admitted(verified))
        assert isinstance(data, bytes)
        return _finish(data, content_sha256, verified, _canonical(_verified_object(verified)))

    return _run(build, InvalidStageValueError)


def decode_analyzed(data: bytes, *, content_sha256: str) -> AnalyzedQuestion:
    """Decode a stored ``eg-review-stage-analyzed-v1`` object (``InvalidStageValueError``)."""

    def build() -> AnalyzedQuestion:
        record = _object(_load(data, MAX_ANALYZED_BYTES), _ANALYZED_KEYS)
        _require(record["canonical"] == ANALYZED_CANONICAL)
        tenant_id = _decoded_uuid(record["tenant_id"])
        findings: list[Finding] = []
        follow_ups: list[tuple[str, ...]] = []
        for raw in _array(record["findings"]):
            entry = _object(raw, _FINDING_KEYS)
            findings.append(
                Finding(
                    tenant_id=tenant_id,
                    finding_id=_decoded_uuid(entry["finding_id"]),
                    question_ids=tuple(_text(q) for q in _array(entry["question_ids"])),
                    title=_text(entry["title"]),
                    severity=_member(Severity, entry["severity"]),
                    statement=_text(entry["statement"]),
                    evidence_status=_member(EvidenceStatus, entry["evidence_status"]),
                    citations=tuple(
                        _decoded_citation(_object(c, _CITATION_KEYS), tenant_id)
                        for c in _array(entry["citations"])
                    ),
                )
            )
            follow_ups.append(tuple(_text(q) for q in _array(entry["follow_up_questions"])))
        analyzed = AnalyzedQuestion(
            tenant_id=tenant_id,
            review_id=_decoded_uuid(record["review_id"]),
            question_id=_text(record["question_id"]),
            request_sha256=_text(record["request_sha256"]),
            findings=tuple(findings),
            follow_up_questions=tuple(follow_ups),
        )
        assert isinstance(data, bytes)
        return _finish(data, content_sha256, analyzed, _canonical(_analyzed_object(analyzed)))

    return _run(build, InvalidStageValueError)
