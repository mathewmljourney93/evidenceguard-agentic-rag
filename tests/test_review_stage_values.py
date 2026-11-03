"""M5e values, canonical encodings and bounded strict decoders
(``evidenceguard_domain.review_stages``, ADR-0023), without a database or network.

Expected canonical bytes are built here from test-owned dictionaries with ``json.dumps`` (never
with the implementation's encoder), and their SHA-256 digests are pinned literals computed once
from those dictionaries. The maximal-size bounds are derived twice, independently: by encoding
test-owned maximal dictionaries and by byte arithmetic without ``json``.
"""

import dataclasses
import hashlib
import json
import socket
import warnings
from datetime import UTC, date, datetime, timedelta, timezone
from fractions import Fraction
from typing import Any
from uuid import UUID, uuid4

import pytest

from evidenceguard_domain import review_stages as rs
from evidenceguard_domain.agent_outputs import (
    AnalystOutput,
    ClaimOutput,
    FindingOutput,
    QuoteRef,
    VerifierOutput,
)
from evidenceguard_domain.evidence import (
    Authenticity,
    Citation,
    EvidenceQuestion,
    EvidenceStatus,
    Severity,
    SourceType,
    Verdict,
    Verification,
)
from evidenceguard_domain.model_calls import (
    CallOutcome,
    ModelPurpose,
    ModelUsage,
    StructuredResult,
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
    analyze_question,
    verify_question,
)
from evidenceguard_domain.retrieval import (
    RETRIEVAL_CONFIG_V1,
    ChannelHit,
    ChunkEvidence,
    PendingExclusions,
    RetrievalResult,
    RetrievalSnapshot,
    RetrievedChunk,
    RevisionBinding,
    SourceSpan,
)
from evidenceguard_domain.review_stages import (
    CallKind,
    CallRecord,
    CallRejection,
    EvidenceRecord,
    InvalidStageValueError,
    PlannedQuestionSet,
    RequestBasis,
    ReservationState,
    StageKind,
    StageOutcome,
    StageRecord,
    StageShape,
    UnresolvedReason,
)
from evidenceguard_retrieval.embeddings import HASH_IDENTITY

TENANT = UUID("11111111-1111-4111-8111-111111111111")
VENDOR = UUID("22222222-2222-4222-8222-222222222222")
REV_A = UUID("33333333-3333-4333-8333-333333333333")
DOC_A = UUID("44444444-4444-4444-8444-444444444444")
INDEX_A = UUID("5b7601bd-c104-574b-afc4-8e43c3da8ecc")
REVIEW = UUID("88888888-8888-4888-8888-888888888888")
JOB = UUID("77777777-7777-4777-8777-777777777777")
C1 = UUID(int=1)
TEXT = "Customer data is encrypted at rest with AES-256."
QUESTION_ID = "ENC-01"
QUESTION_TEXT = "Is customer data encrypted at rest?"
SECRET = "SECRET-QUESTION-TEXT"
STARTED = datetime(2026, 10, 23, 9, 0, tzinfo=UTC)

# Digests of test-owned dictionaries (``.local`` derivation, independent of the encoder).
SNAPSHOT_SHA = "d8c55280a2ed53ed79337b6e71779b8516029db2bd0b2a2cdf0a36f35f43c4fe"
PLAN_SHA = "b0a77b0681d9609dd76efb61c2dc18d53e1d9f1e6d9a881f7d19517033d3d996"
EVIDENCE_SHA = "15c2c854e41d025f1562a3cee36480e160f0bd65e989e8ee3420168cb95b53aa"
VERIFIED_SHA = "71055fdc64f41e66e195f95b0f0c94786c015a3526a04f75929bae2837247871"
ANALYZED_SHA = "75482c059dcd40daca7fd39c787970cf6c189b6ec2bab9568f115e0b1c0e20fc"
DEPENDENCY_SHA = "98ea404e66a8662d147aa0b2ed69e56543fb9d56021feb36038b239c3cea0b20"
DEPENDENCY_UNRESOLVED_SHA = "77e30571cd3a5055cb4312eee0ac7af708e447c07b339895065442e06f7a9f66"
FINDING_ID = UUID("94754c8e-9757-50c6-b036-f76366a1293c")
MAX_VERIFIED = 1_135_720
MAX_ANALYZED = 3_090_153


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("a test attempted network access")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


def enc(value: dict[str, Any]) -> bytes:
    """The test's own canonical JSON (the M5e-B2 rule, written independently)."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def assert_fixed(error: BaseException, kind: type[Exception]) -> None:
    assert type(error) is kind
    assert error.__cause__ is None and error.__context__ is None
    assert str(error) == kind.code  # type: ignore[attr-defined]


# --- fixtures -------------------------------------------------------------------------------------


def snapshot() -> RetrievalSnapshot:
    return RetrievalSnapshot(
        TENANT,
        VENDOR,
        HASH_IDENTITY,
        RETRIEVAL_CONFIG_V1,
        (RevisionBinding(REV_A, DOC_A, INDEX_A, "md-v1", 2, "a" * 64, "b" * 64),),
        PendingExclusions(0, (), False),
        datetime(2026, 10, 17, 9, 30, tzinfo=UTC),
    )


def question(**changes: Any) -> EvidenceQuestion:
    values: dict[str, Any] = {
        "question_id": QUESTION_ID,
        "text": QUESTION_TEXT,
        "search_queries": ("encryption at rest", "stored data encryption"),
    }
    values.update(changes)
    return EvidenceQuestion(**values)


def chunk(
    *,
    text: str = TEXT,
    revision_no: int = 1,
    char_start: int = 200,
    title: str = "Security Overview",
) -> ChunkEvidence:
    return ChunkEvidence(
        C1,
        text,
        hashlib.sha256(text.encode()).hexdigest(),
        0,
        ("Security", "Encryption"),
        False,
        SourceSpan(5, 5, char_start, char_start + len(text)),
        None,
        "security-overview",
        title,
        revision_no,
        "2026.1",
        date(2026, 1, 15),
        SourceType.VENDOR_STATEMENT,
        Authenticity.NOT_ESTABLISHED,
    )


def result(evidence: ChunkEvidence | None = None) -> RetrievalResult:
    hits = (
        ChannelHit(0, "lexical", 1, 0.5),
        ChannelHit(0, "vector", 2, -0.0),
        ChannelHit(1, "lexical", 3, 0.25),
    )
    item = RetrievedChunk(
        C1,
        REV_A,
        DOC_A,
        1,
        Fraction(1, 61) + Fraction(1, 62) + Fraction(1, 63),
        hits,
        evidence or chunk(),
    )
    return RetrievalResult(snapshot(), 2, 8, (1,), (item,))


def record(**changes: Any) -> EvidenceRecord:
    values: dict[str, Any] = {
        "tenant_id": TENANT,
        "review_id": REVIEW,
        "question": question(),
        "result": result(),
    }
    values.update(changes)
    return EvidenceRecord(**values)


def completed(purpose: ModelPurpose, output: Any, digest: str) -> StructuredResult:
    return StructuredResult(
        request_sha256=digest,
        purpose=purpose,
        question_id=QUESTION_ID,
        outcome=CallOutcome.COMPLETED,
        dispatched=True,
        output=output,
        model_requested="fake-scripted-v1",
        model_used="fake-scripted-v1",
        usage=ModelUsage(10, 20),
        latency_ms=5,
    )


def trusted() -> QuestionEvidence:
    return QuestionEvidence(
        tenant_id=TENANT,
        review_id=REVIEW,
        snapshot_sha256=SNAPSHOT_SHA,
        question=question(),
        result=result(),
    )


def verified() -> VerifiedQuestion:
    output = VerifierOutput(
        verdict=Verdict.SUPPORTED,
        claims=(
            ClaimOutput(
                text="Encrypted at rest.",
                citations=(QuoteRef(chunk_id=str(C1), quote="encrypted at rest"),),
            ),
        ),
        rationale="Based on the cited passages.",
    )
    value = verify_question(trusted(), completed(ModelPurpose.VERIFIER, output, "a" * 64))
    assert type(value) is VerifiedQuestion
    return value


def analyzed() -> AnalyzedQuestion:
    finding = FindingOutput(
        question_ids=(QUESTION_ID,),
        title="Encryption at rest",
        severity=Severity.LOW,
        statement="Data is encrypted at rest.",
        citations=(QuoteRef(chunk_id=str(C1), quote="encrypted at rest"),),
        follow_up_questions=("Which keys?",),
    )
    value = analyze_question(
        verified(),
        question(),
        completed(ModelPurpose.RISK_ANALYST, AnalystOutput(findings=(finding,)), "b" * 64),
    )
    assert type(value) is AnalyzedQuestion
    return value


CITATION = {
    "document_revision_id": str(REV_A),
    "chunk_id": str(C1),
    "source_type": "vendor_statement",
    "quote": "encrypted at rest",
    "authenticity": "not_established",
}


def expected_plan() -> dict[str, Any]:
    return {
        "canonical": "eg-review-plan-question-v1",
        "question_id": QUESTION_ID,
        "text": QUESTION_TEXT,
        "search_queries": ["encryption at rest", "stored data encryption"],
        "requires_documentary_support": False,
    }


def expected_evidence() -> dict[str, Any]:
    return {
        "canonical": "eg-review-question-evidence-v1",
        "tenant_id": str(TENANT),
        "review_id": str(REVIEW),
        "question_id": QUESTION_ID,
        "question_sha256": PLAN_SHA,
        "snapshot_sha256": SNAPSHOT_SHA,
        "query_count": 2,
        "k": 8,
        "vector_skipped": [1],
        "items": [
            {
                "chunk_id": str(C1),
                "revision_id": str(REV_A),
                "document_id": str(DOC_A),
                "fused_rank": 1,
                "hits": [
                    {
                        "channel": "lexical",
                        "query_position": 0,
                        "rank": 1,
                        "score": "0x1.0000000000000p-1",
                    },
                    {"channel": "vector", "query_position": 0, "rank": 2, "score": "-0x0.0p+0"},
                    {
                        "channel": "lexical",
                        "query_position": 1,
                        "rank": 3,
                        "score": "0x1.0000000000000p-2",
                    },
                ],
                "evidence": {
                    "text": TEXT,
                    "content_sha256": hashlib.sha256(TEXT.encode()).hexdigest(),
                    "ordinal": 0,
                    "section_path": ["Security", "Encryption"],
                    "is_table": False,
                    "body": {
                        "line_start": 5,
                        "line_end": 5,
                        "char_start": 200,
                        "char_end": 200 + len(TEXT),
                    },
                    "header": None,
                    "document_key": "security-overview",
                    "title": "Security Overview",
                    "revision_no": 1,
                    "version_label": "2026.1",
                    "effective_date": "2026-01-15",
                    "source_type": "vendor_statement",
                    "authenticity": "not_established",
                },
            }
        ],
    }


def expected_verified() -> dict[str, Any]:
    return {
        "canonical": "eg-review-stage-verified-v1",
        "tenant_id": str(TENANT),
        "review_id": str(REVIEW),
        "question_id": QUESTION_ID,
        "snapshot_sha256": SNAPSHOT_SHA,
        "request_sha256": "a" * 64,
        "match_rules": "eg-quote-match-v1",
        "verification": {
            "verdict": "supported",
            "evidence_status": "vendor_claim",
            "rationale": "Based on the cited passages.",
        },
        "claims": [{"text": "Encrypted at rest.", "citation_indexes": [0]}],
        "citations": [
            {
                **CITATION,
                "document_id": str(DOC_A),
                "match": {
                    "kind": "body",
                    "text_start": 17,
                    "text_end": 34,
                    "source_char_start": 217,
                    "source_char_end": 234,
                    "occurrences": 1,
                },
            }
        ],
    }


def expected_analyzed() -> dict[str, Any]:
    return {
        "canonical": "eg-review-stage-analyzed-v1",
        "tenant_id": str(TENANT),
        "review_id": str(REVIEW),
        "question_id": QUESTION_ID,
        "request_sha256": "b" * 64,
        "findings": [
            {
                "finding_id": str(FINDING_ID),
                "question_ids": [QUESTION_ID],
                "title": "Encryption at rest",
                "severity": "low",
                "statement": "Data is encrypted at rest.",
                "evidence_status": "vendor_claim",
                "citations": [CITATION],
                "follow_up_questions": ["Which keys?"],
            }
        ],
    }


# --- enumerations ---------------------------------------------------------------------------------


def test_enumerations_carry_the_accepted_values() -> None:
    assert [k.value for k in StageKind] == ["verification", "analysis"]
    assert StageKind.VERIFICATION.purpose is ModelPurpose.VERIFIER
    assert StageKind.ANALYSIS.purpose is ModelPurpose.RISK_ANALYST
    assert StageKind.VERIFICATION.rejection_stage is RejectionStage.VERIFICATION
    assert StageKind.ANALYSIS.rejection_stage is RejectionStage.ANALYSIS
    assert [k.value for k in CallKind] == ["initial", "retry", "repair"]
    assert [b.value for b in RequestBasis] == ["original", "repaired"]
    assert [s.value for s in ReservationState] == ["started", "completed"]
    assert [o.value for o in StageOutcome] == ["verified", "analyzed", "unresolved"]
    assert [r.value for r in UnresolvedReason] == [
        "refusal",
        "max_tokens",
        "unexpected_stop",
        "model_mismatch",
        "invalid_output",
        "citation_rejected",
        "timeout",
        "provider_failed",
        "call_abandoned",
        "request_too_large",
        "repair_request_too_large",
        "evidence_too_large",
        "verification_unresolved",
    ]
    assert len(rs.AFTER_CALL_REASONS) == 8 and len(rs.EXHAUSTED_REASONS) == 9
    assert (rs.MAX_CANONICAL_INT, rs.MAX_EVIDENCE_BYTES) == (2_147_483_647, 4_194_304)
    assert (rs.MAX_VERIFIED_BYTES, rs.MAX_ANALYZED_BYTES) == (2_097_152, 4_194_304)


# --- planned questions ----------------------------------------------------------------------------


def test_plan_question_encoding_is_pinned() -> None:
    expected = enc(expected_plan())
    assert expected == (
        b'{"canonical":"eg-review-plan-question-v1","question_id":"ENC-01",'
        b'"requires_documentary_support":false,"search_queries":["encryption at rest",'
        b'"stored data encryption"],"text":"Is customer data encrypted at rest?"}'
    )
    assert sha(expected) == PLAN_SHA
    assert rs.plan_question_canonical(question()) == expected
    assert rs.plan_question_sha256(question()) == PLAN_SHA


def test_planned_question_set_rules() -> None:
    planned = PlannedQuestionSet(tenant_id=TENANT, review_id=REVIEW, questions=(question(),))
    assert planned.question_sha256s == (PLAN_SHA,) and planned.position(QUESTION_ID) == 0
    assert planned.position("ZZ-99") is None
    hundred = tuple(question(question_id=f"Q{index:02d}-01") for index in range(100))
    assert (
        len(PlannedQuestionSet(tenant_id=TENANT, review_id=REVIEW, questions=hundred).questions)
        == 100
    )
    whitespace = EvidenceQuestion.model_construct(
        question_id=QUESTION_ID, text=" padded ", search_queries=("q",)
    )
    for bad in (
        {"questions": ()},
        {"questions": (*hundred, question(question_id="QX-01"))},
        {"questions": (question(), question())},
        {"questions": [question()]},
        {"questions": (whitespace,)},  # no silent normalization
        {"tenant_id": str(TENANT)},
        {"surplus": 1},
    ):
        values: dict[str, Any] = {
            "tenant_id": TENANT,
            "review_id": REVIEW,
            "questions": (question(),),
        }
        values.update(bad)
        with pytest.raises(InvalidStageValueError) as caught:
            PlannedQuestionSet(**values)
        assert_fixed(caught.value, InvalidStageValueError)
    with pytest.raises(InvalidStageValueError):
        dataclasses.replace(planned, questions=())
    assert QUESTION_TEXT not in repr(planned) and QUESTION_ID not in repr(planned)


# --- evidence -------------------------------------------------------------------------------------


def test_evidence_encoding_is_pinned_and_decodes_back() -> None:
    expected = enc(expected_evidence())
    assert sha(expected) == EVIDENCE_SHA and len(expected) == 1315
    value = record()
    assert value.canonical == expected and value.evidence_sha256 == EVIDENCE_SHA
    assert (value.question_id, value.question_sha256) == (QUESTION_ID, PLAN_SHA)
    assert (value.snapshot_sha256, value.item_count, value.fits_storage) == (SNAPSHOT_SHA, 1, True)
    decoded = rs.decode_evidence(
        expected, evidence_sha256=EVIDENCE_SHA, snapshot=snapshot(), question=question()
    )
    assert decoded == value
    assert decoded.result.items[0].fused_score == Fraction(1, 61) + Fraction(1, 62) + Fraction(
        1, 63
    )
    assert str(decoded.result.items[0].hits[1].score) == "-0.0"
    assert TEXT not in repr(value) and QUESTION_TEXT not in repr(value)


def test_evidence_record_cross_field_rules_and_admission_range() -> None:
    with pytest.raises(InvalidStageValueError):  # the result's tenant must be the record's
        record(tenant_id=uuid4())
    with pytest.raises(InvalidStageValueError):  # query_count must match the question
        record(question=question(search_queries=("only one",)))
    record(result=result(chunk(revision_no=2_147_483_647)))  # the bound is admitted
    for evidence in (
        chunk(revision_no=2_147_483_648),
        chunk(char_start=2_147_483_647),  # char_end beyond the bound
    ):
        with pytest.raises(InvalidStageValueError) as caught:
            record(result=result(evidence))
        assert_fixed(caught.value, InvalidStageValueError)


def test_an_oversized_evidence_record_is_valid_but_does_not_fit() -> None:
    oversized = record(result=result(chunk(title="t" * rs.MAX_EVIDENCE_BYTES)))
    assert not oversized.fits_storage and len(oversized.canonical) > rs.MAX_EVIDENCE_BYTES
    with pytest.raises(InvalidStageValueError):  # the decoder's cap applies before parsing
        rs.decode_evidence(
            oversized.canonical,
            evidence_sha256=oversized.evidence_sha256,
            snapshot=snapshot(),
            question=question(),
        )


def test_evidence_decoding_requires_the_trusted_snapshot_question_and_digest() -> None:
    data = enc(expected_evidence())
    for kwargs in (
        {"evidence_sha256": "0" * 64},
        {"question": question(text="Another question?")},
        {"question": question(question_id="ENC-02")},
    ):
        values: dict[str, Any] = {
            "evidence_sha256": EVIDENCE_SHA,
            "snapshot": snapshot(),
            "question": question(),
        }
        values.update(kwargs)
        with pytest.raises(InvalidStageValueError):
            rs.decode_evidence(data, **values)
    tampered = expected_evidence()
    tampered["items"][0]["evidence"]["title"] = "Changed"
    with pytest.raises(InvalidStageValueError):  # content digest is the chunk text only
        rs.decode_evidence(
            enc(tampered), evidence_sha256=EVIDENCE_SHA, snapshot=snapshot(), question=question()
        )


# --- floats ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (1.0, "0x1.0000000000000p+0"),
        (0.1, "0x1.999999999999ap-4"),
        (5e-324, "0x0.0000000000001p-1022"),
        (-0.0, "-0x0.0p+0"),
        (1.7976931348623157e308, "0x1.fffffffffffffp+1023"),
        (-2.5, "-0x1.4000000000000p+1"),
    ],
)
def test_float_strings_are_bit_exact(value: float, text: str) -> None:
    assert rs._float_text(value) == text
    decoded = rs._decoded_float(text)
    assert decoded == value and str(decoded) == str(value)


@pytest.mark.parametrize(
    "text",
    ["0x1.0p+0", "0X1.0000000000000P+0", "1.0", "inf", "nan", "0x1p+0", " 0x1.0000000000000p+0"],
)
def test_non_canonical_float_spellings_are_refused(text: str) -> None:
    with pytest.raises(rs._Invalid):
        rs._decoded_float(text)
    with pytest.raises(rs._Invalid):
        rs._float_text(float("inf"))


# --- strict decoding ------------------------------------------------------------------------------


def verified_bytes() -> bytes:
    return enc(expected_verified())


@pytest.mark.parametrize(
    "mutate",
    [
        lambda b: b.replace(b'"occurrences":1', b'"occurrences":1.0'),  # JSON float
        lambda b: b.replace(b'"occurrences":1', b'"occurrences":1e0'),
        lambda b: b.replace(b'"occurrences":1', b'"occurrences":-1'),  # a sign
        lambda b: b.replace(b'"occurrences":1', b'"occurrences":NaN'),  # constants
        lambda b: b.replace(b'"occurrences":1', b'"occurrences":Infinity'),
        lambda b: b.replace(b'"occurrences":1', b'"occurrences":12345678901'),  # 11 digits
        lambda b: b.replace(b'"occurrences":1', b'"occurrences":2147483648'),  # 10, magnitude
        lambda b: b.replace(b'"occurrences":1', b'"occurrences":9007199254740992'),  # 16
        lambda b: b.replace(b'"text_start":17', b'"text_start":17,"text_start":17'),  # duplicate
        lambda b: b.replace(b'"occurrences":1', b'"occurrences":1,"extra":1'),  # unknown key
        lambda b: b.replace(b'"occurrences":1,', b""),  # missing key
        lambda b: b.replace(b'"verdict":"supported"', b'"verdict":"maybe"'),
        lambda b: b.replace(b'"citation_indexes":[0]', b'"citation_indexes":["0"]'),
        lambda b: b.replace(b",", b", ", 1),  # non-canonical bytes
        lambda b: b.replace(b"Encrypted", b"Encrypt\xc3\xa9d"),  # non-ASCII
        lambda b: b.replace(b"Encrypted", b"Encrypted\x01"),  # control byte
        lambda b: b[:-1],
        lambda b: b"[" * 200_000,  # deep nesting
        lambda b: b"null",
    ],
)
def test_strict_decoding_refusals(mutate: Any) -> None:
    data = mutate(verified_bytes())
    with pytest.raises(InvalidStageValueError) as caught:
        rs.decode_verified(data, content_sha256=sha(data))
    assert_fixed(caught.value, InvalidStageValueError)


def test_integer_boundaries_round_trip_and_magnitude_is_checked() -> None:
    assert rs._parse_int("0") == 0 and rs._parse_int("2147483647") == 2_147_483_647
    for text in ("2147483648", "9999999999", "12345678901", "-0", "+1", "\uff11"):
        with pytest.raises(rs._Invalid):
            rs._parse_int(text)


def test_oversize_input_is_refused_before_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    def never(*args: object, **kwargs: object) -> None:
        raise AssertionError("parsed before the size check")

    monkeypatch.setattr(json, "loads", never)
    data = b" " * (rs.MAX_VERIFIED_BYTES + 1)
    with pytest.raises(InvalidStageValueError):
        rs.decode_verified(data, content_sha256=sha(data))
    data = b" " * (rs.MAX_ANALYZED_BYTES + 1)
    with pytest.raises(InvalidStageValueError):
        rs.decode_analyzed(data, content_sha256=sha(data))


def test_decoding_propagates_process_control_as_the_same_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = KeyboardInterrupt()

    def interrupted(*args: object, **kwargs: object) -> None:
        raise marker

    monkeypatch.setattr(json, "loads", interrupted)
    with pytest.raises(KeyboardInterrupt) as caught:
        rs.decode_verified(verified_bytes(), content_sha256=VERIFIED_SHA)
    assert caught.value is marker


# --- stage content --------------------------------------------------------------------------------


def test_verified_and_analyzed_encodings_are_pinned_and_decode_back() -> None:
    value = verified()
    assert sha(verified_bytes()) == VERIFIED_SHA
    assert rs.encode_verified(value) == verified_bytes()
    assert rs.decode_verified(verified_bytes(), content_sha256=VERIFIED_SHA) == value
    content = analyzed()
    expected = enc(expected_analyzed())
    assert sha(expected) == ANALYZED_SHA
    assert rs.encode_analyzed(content) == expected
    assert rs.decode_analyzed(expected, content_sha256=ANALYZED_SHA) == content
    with pytest.raises(InvalidStageValueError):
        rs.decode_analyzed(expected, content_sha256=VERIFIED_SHA)


def manual_verified(source_start: int) -> VerifiedQuestion:
    quote = "encrypted at rest"
    citation = Citation(
        tenant_id=TENANT,
        document_revision_id=REV_A,
        chunk_id=C1,
        source_type=SourceType.VENDOR_STATEMENT,
        quote=quote,
    )
    match = QuoteMatch(
        kind=QuoteSpanKind.BODY,
        text_start=17,
        text_end=34,
        source_char_start=source_start,
        source_char_end=source_start + len(quote),
        quote=quote,
        occurrences=1,
    )
    return VerifiedQuestion(
        tenant_id=TENANT,
        review_id=REVIEW,
        question_id=QUESTION_ID,
        snapshot_sha256=SNAPSHOT_SHA,
        request_sha256="a" * 64,
        match_rules="eg-quote-match-v1",
        verification=Verification(
            tenant_id=TENANT,
            question_id=QUESTION_ID,
            verdict=Verdict.SUPPORTED,
            evidence_status=EvidenceStatus.VENDOR_CLAIM,
            citations=(citation,),
            rationale="Rationale.",
        ),
        claims=(ValidatedClaim(text="Claim.", citation_indexes=(0,)),),
        provenance=(AcceptedCitation(citation=citation, document_id=DOC_A, match=match),),
    )


def test_inherited_quote_offsets_are_narrowed_to_the_admission_range() -> None:
    at_bound = manual_verified(2_147_483_647 - len("encrypted at rest"))
    assert (
        rs.decode_verified(
            rs.encode_verified(at_bound), content_sha256=sha(rs.encode_verified(at_bound))
        )
        == at_bound
    )
    beyond = manual_verified(2_147_483_647)  # accepted by M5b, refused by M5e
    for refusal in (
        lambda: rs.encode_verified(beyond),
        lambda: rs.revalidated_verified(beyond),
        lambda: stage(StageShape.S1, content=beyond),
    ):
        with pytest.raises(InvalidStageValueError) as caught:
            refusal()
        assert_fixed(caught.value, InvalidStageValueError)


# --- maximal sizes (two independent derivations) --------------------------------------------------

ASTRAL = "\U0001f600"
MAX_INT = 2_147_483_647


def maximal_dicts() -> tuple[dict[str, Any], dict[str, Any]]:
    uuid = "00000000-0000-0000-0000-000000000000"
    qid = "ABCDEFGHIJ-999"
    citation = {
        "authenticity": "not_established",
        "chunk_id": uuid,
        "document_revision_id": uuid,
        "quote": ASTRAL * 1000,
        "source_type": "third_party_report",
    }
    verified_max = {
        "canonical": "eg-review-stage-verified-v1",
        "tenant_id": uuid,
        "review_id": uuid,
        "question_id": qid,
        "snapshot_sha256": "0" * 64,
        "request_sha256": "0" * 64,
        "match_rules": "eg-quote-match-v1",
        "verification": {
            "verdict": "insufficient_evidence",
            "evidence_status": "documentary_support",
            "rationale": ASTRAL * 2000,
        },
        "claims": [{"text": ASTRAL * 1000, "citation_indexes": [79] * 8} for _ in range(10)],
        "citations": [
            {
                **citation,
                "document_id": uuid,
                "match": {
                    "kind": "header",
                    "text_start": 3999,
                    "text_end": 4000,
                    "source_char_start": MAX_INT,
                    "source_char_end": MAX_INT,
                    "occurrences": 64,
                },
            }
            for _ in range(80)
        ],
    }
    analyzed_max = {
        "canonical": "eg-review-stage-analyzed-v1",
        "tenant_id": uuid,
        "review_id": uuid,
        "question_id": qid,
        "request_sha256": "0" * 64,
        "findings": [
            {
                "finding_id": uuid,
                "question_ids": [qid] * 20,
                "title": ASTRAL * 200,
                "severity": "medium",
                "statement": ASTRAL * 2000,
                "evidence_status": "documentary_support",
                "citations": [citation] * 8,
                "follow_up_questions": [ASTRAL * 500] * 5,
            }
            for _ in range(20)
        ],
    }
    return verified_max, analyzed_max


def arithmetic_bounds() -> tuple[int, int]:
    """The same maximal objects by byte counting only (no ``json``)."""

    def s(n: int) -> int:
        return n + 2

    def obj(entries: dict[str, int]) -> int:
        return 2 + sum(s(len(k)) + 1 + v for k, v in entries.items()) + len(entries) - 1

    def arr(sizes: list[int]) -> int:
        return 2 + sum(sizes) + max(len(sizes) - 1, 0)

    uuid, digest, qid, astral = s(36), s(64), s(14), 12
    citation = {
        "authenticity": s(15),
        "chunk_id": uuid,
        "document_revision_id": uuid,
        "quote": s(1000 * astral),
        "source_type": s(18),
    }
    match = obj(
        {
            "kind": s(6),
            "text_start": 4,
            "text_end": 4,
            "source_char_start": 10,
            "source_char_end": 10,
            "occurrences": 2,
        }
    )
    verified_max = obj(
        {
            "canonical": s(27),
            "tenant_id": uuid,
            "review_id": uuid,
            "question_id": qid,
            "snapshot_sha256": digest,
            "request_sha256": digest,
            "match_rules": s(17),
            "verification": obj(
                {"verdict": s(21), "evidence_status": s(19), "rationale": s(2000 * astral)}
            ),
            "claims": arr([obj({"text": s(1000 * astral), "citation_indexes": arr([2] * 8)})] * 10),
            "citations": arr([obj({**citation, "document_id": uuid, "match": match})] * 80),
        }
    )
    finding = obj(
        {
            "finding_id": uuid,
            "question_ids": arr([qid] * 20),
            "title": s(200 * astral),
            "severity": s(6),
            "statement": s(2000 * astral),
            "evidence_status": s(19),
            "citations": arr([obj(citation)] * 8),
            "follow_up_questions": arr([s(500 * astral)] * 5),
        }
    )
    analyzed_max = obj(
        {
            "canonical": s(27),
            "tenant_id": uuid,
            "review_id": uuid,
            "question_id": qid,
            "request_sha256": digest,
            "findings": arr([finding] * 20),
        }
    )
    return verified_max, analyzed_max


def test_maximal_admitted_content_sizes_match_both_derivations_and_fit_the_caps() -> None:
    verified_max, analyzed_max = maximal_dicts()
    assert len(enc(verified_max)) == MAX_VERIFIED
    assert len(enc(analyzed_max)) == MAX_ANALYZED
    assert arithmetic_bounds() == (MAX_VERIFIED, MAX_ANALYZED)
    assert MAX_VERIFIED < rs.MAX_VERIFIED_BYTES and MAX_ANALYZED < rs.MAX_ANALYZED_BYTES


# --- call rejections ------------------------------------------------------------------------------


REJECTIONS = [
    (
        RejectionStage.VERIFICATION,
        RejectionReason.CHUNK_NOT_RETRIEVED,
        0,
        0,
        1,
        "citation_rejected",
    ),
    (RejectionStage.VERIFICATION, RejectionReason.QUOTE_BLANK, 9, 7, 80, "citation_rejected"),
    (RejectionStage.VERIFICATION, RejectionReason.QUOTE_NOT_FOUND, 1, 2, 3, "citation_rejected"),
    (RejectionStage.VERIFICATION, RejectionReason.QUOTE_TOO_LONG, 1, 2, 3, "citation_rejected"),
    (RejectionStage.VERIFICATION, RejectionReason.QUOTE_NOT_EXACT, 1, 2, 3, "citation_rejected"),
    (RejectionStage.VERIFICATION, RejectionReason.CLAIM_UNCITED, 4, None, 10, "citation_rejected"),
    (
        RejectionStage.VERIFICATION,
        RejectionReason.VERDICT_UNSUPPORTED,
        None,
        None,
        2,
        "invalid_output",
    ),
    (RejectionStage.VERIFICATION, RejectionReason.RATIONALE_BLANK, None, None, 1, "invalid_output"),
    (RejectionStage.ANALYSIS, RejectionReason.FOREIGN_QUESTION, 19, None, 20, "invalid_output"),
    (RejectionStage.ANALYSIS, RejectionReason.CITATION_NOT_VALIDATED, 0, 7, 1, "citation_rejected"),
    (RejectionStage.ANALYSIS, RejectionReason.CITATION_NOT_SHARED, 0, 0, 1, "citation_rejected"),
    (RejectionStage.ANALYSIS, RejectionReason.MIXED_VERDICTS, 0, None, 1, "invalid_output"),
    (
        RejectionStage.ANALYSIS,
        RejectionReason.FINDING_STATUS_UNSUPPORTED,
        0,
        None,
        1,
        "invalid_output",
    ),
    (RejectionStage.ANALYSIS, RejectionReason.FINDING_TEXT_BLANK, 0, None, 1, "invalid_output"),
]


@pytest.mark.parametrize(("stage", "reason", "item", "citation", "count", "mapped"), REJECTIONS)
def test_call_rejections_round_trip_every_m5b_reason(
    stage: RejectionStage,
    reason: RejectionReason,
    item: int | None,
    citation: int | None,
    count: int,
    mapped: str,
) -> None:
    original = ProvenanceRejection(
        stage=stage,
        question_id=QUESTION_ID,
        reason=reason,
        item_index=item,
        citation_index=citation,
        rejected_count=count,
    )
    stored = CallRejection.from_rejection(original)
    assert stored.stage.value == stage.value and stored.reason is reason
    assert (stored.item_index, stored.citation_index, stored.rejected_count) == (
        item,
        citation,
        count,
    )
    assert stored.to_rejection(QUESTION_ID) == original
    assert stored.stage_reason.value == mapped == original.provenance_check
    assert {f.name for f in dataclasses.fields(stored)} == {
        "stage",
        "reason",
        "item_index",
        "citation_index",
        "rejected_count",
    }


def test_call_rejection_refusals() -> None:
    with pytest.raises(InvalidStageValueError):  # analysis reason on a verification stage
        CallRejection(
            stage=StageKind.VERIFICATION,
            reason=RejectionReason.MIXED_VERDICTS,
            item_index=0,
            citation_index=None,
            rejected_count=1,
        )
    rejection = CallRejection(
        stage=StageKind.VERIFICATION,
        reason=RejectionReason.CLAIM_UNCITED,
        item_index=0,
        citation_index=None,
        rejected_count=1,
    )
    for bad in ("bad", 1):
        with pytest.raises(InvalidStageValueError):
            rejection.to_rejection(bad)  # type: ignore[arg-type]
    with pytest.raises(InvalidStageValueError):
        CallRejection.from_rejection("rejection")  # type: ignore[arg-type]


# --- call records ---------------------------------------------------------------------------------


def call(**changes: Any) -> CallRecord:
    values: dict[str, Any] = {
        "tenant_id": TENANT,
        "review_id": REVIEW,
        "job_id": JOB,
        "question_id": QUESTION_ID,
        "stage": StageKind.VERIFICATION,
        "sequence": 1,
        "call_kind": CallKind.INITIAL,
        "request_basis": RequestBasis.ORIGINAL,
        "request_sha256": "a" * 64,
        "prompt_sha256": "1" * 64,
        "model_requested": "fake-scripted-v1",
        "max_output_tokens": 4096,
        "timeout_ms": 60_000,
        "evidence_sha256": "e" * 64,
        "dependency_sha256": None,
        "job_attempt": 1,
        "state": ReservationState.STARTED,
        "started_at": STARTED,
    }
    values.update(changes)
    return CallRecord(**values)


def completion(outcome: CallOutcome, **changes: Any) -> dict[str, Any]:
    response = outcome not in (CallOutcome.TIMEOUT, CallOutcome.PROVIDER_FAILED)
    values: dict[str, Any] = {
        "state": ReservationState.COMPLETED,
        "completed_at": STARTED + timedelta(seconds=1),
        "outcome": outcome,
        "dispatched": True,
        "model_used": (
            None
            if not response
            else ("other-model" if outcome is CallOutcome.MODEL_MISMATCH else "fake-scripted-v1")
        ),
        "usage": ModelUsage(1, 2) if response else None,
        "latency_ms": 10,
    }
    values.update(changes)
    return values


@pytest.mark.parametrize("outcome", list(CallOutcome))
def test_call_records_follow_the_adr_0019_table(outcome: CallOutcome) -> None:
    record_ = call(**completion(outcome))
    assert record_.state is ReservationState.COMPLETED and record_.outcome is outcome
    assert record_.is_success == (outcome is CallOutcome.COMPLETED)


def test_call_record_rules() -> None:
    assert call().completed_at is None and not call().is_success
    # clock regression: completed_at before started_at is accepted (V12)
    early = call(**completion(CallOutcome.TIMEOUT, completed_at=STARTED - timedelta(hours=1)))
    assert early.completed_at is not None and early.completed_at < early.started_at
    offset = call(started_at=datetime(2026, 10, 23, 11, 0, tzinfo=timezone(timedelta(hours=2))))
    assert offset.started_at == STARTED and offset.started_at.tzinfo is UTC
    provider_failed = call(
        **completion(CallOutcome.PROVIDER_FAILED, dispatched=False, latency_ms=None)
    )
    assert provider_failed.dispatched is False
    rejection = CallRejection(
        stage=StageKind.VERIFICATION,
        reason=RejectionReason.QUOTE_NOT_FOUND,
        item_index=0,
        citation_index=0,
        rejected_count=1,
    )
    assert call(**completion(CallOutcome.COMPLETED), rejection=rejection).rejection == rejection
    analysis_rejection = dataclasses.replace(
        rejection, stage=StageKind.ANALYSIS, reason=RejectionReason.CITATION_NOT_VALIDATED
    )
    for bad in (
        {"sequence": 2},  # initial must be sequence 1
        {"call_kind": CallKind.RETRY},
        {"call_kind": CallKind.REPAIR, "sequence": 2},  # repair needs the repaired basis
        {"evidence_sha256": None},
        {"dependency_sha256": "d" * 64},
        {"stage": StageKind.ANALYSIS},  # evidence present on analysis
        {"job_attempt": 0},
        {"job_attempt": 11},
        {"job_attempt": True},
        {"sequence": 4},
        {"max_output_tokens": 8193},
        {"timeout_ms": 999},
        {"model_requested": "Model"},
        {"started_at": datetime(2026, 10, 23, 9, 0)},  # naive
        {"outcome": CallOutcome.TIMEOUT},  # started with a completion field
        {**completion(CallOutcome.COMPLETED), "model_used": None},
        {**completion(CallOutcome.COMPLETED), "model_used": "other-model"},
        {**completion(CallOutcome.MODEL_MISMATCH), "model_used": "fake-scripted-v1"},
        {**completion(CallOutcome.TIMEOUT), "usage": ModelUsage(1, 1)},
        {**completion(CallOutcome.PROVIDER_FAILED), "dispatched": False},  # latency present
        {**completion(CallOutcome.REFUSAL), "rejection": rejection},
        {**completion(CallOutcome.COMPLETED), "rejection": analysis_rejection},
        {**completion(CallOutcome.COMPLETED), "completed_at": None},
        {"surplus": 1},
    ):
        with pytest.raises(InvalidStageValueError) as caught:
            call(**bad)
        assert_fixed(caught.value, InvalidStageValueError)
    with pytest.raises(InvalidStageValueError):
        dataclasses.replace(call(), sequence=2)
    assert "fake-scripted-v1" not in repr(call()) or "a" * 64 in repr(call())


# --- stage records --------------------------------------------------------------------------------


def stage(shape: StageShape, **changes: Any) -> StageRecord:
    verification = shape in (StageShape.S1, StageShape.U4) or (
        shape in (StageShape.U1, StageShape.U2, StageShape.U5, StageShape.U6)
        and changes.pop("analysis", False) is False
    )
    reasons = {
        StageShape.U1: UnresolvedReason.TIMEOUT,
        StageShape.U2: UnresolvedReason.CALL_ABANDONED,
        StageShape.U3: UnresolvedReason.VERIFICATION_UNRESOLVED,
        StageShape.U4: UnresolvedReason.EVIDENCE_TOO_LARGE,
        StageShape.U5: UnresolvedReason.REQUEST_TOO_LARGE,
        StageShape.U6: UnresolvedReason.REPAIR_REQUEST_TOO_LARGE,
    }
    with_call = shape in (StageShape.S1, StageShape.S2, StageShape.U1, StageShape.U2, StageShape.U6)
    kind = StageKind.VERIFICATION if verification else StageKind.ANALYSIS
    if shape is StageShape.S2:
        kind = StageKind.ANALYSIS
    outcome = {
        StageShape.S1: StageOutcome.VERIFIED,
        StageShape.S2: StageOutcome.ANALYZED,
    }.get(shape, StageOutcome.UNRESOLVED)
    content: Any = None
    if shape is StageShape.S1:
        content = verified()
    elif shape is StageShape.S2:
        content = analyzed()
    values: dict[str, Any] = {
        "tenant_id": TENANT,
        "review_id": REVIEW,
        "job_id": JOB,
        "question_id": QUESTION_ID,
        "stage": kind,
        "outcome": outcome,
        "unresolved_reason": reasons.get(shape),
        "call_sequence": 1 if with_call else None,
        "request_sha256": (content.request_sha256 if content is not None else "a" * 64)
        if with_call
        else None,
        "evidence_sha256": (
            "e" * 64 if kind is StageKind.VERIFICATION and shape is not StageShape.U4 else None
        ),
        "dependency_sha256": "d" * 64 if kind is StageKind.ANALYSIS else None,
        "content": content,
        "job_attempt": 1,
        "committed_at": STARTED,
    }
    values.update(changes)
    return StageRecord(**values)


@pytest.mark.parametrize("shape", list(StageShape))
def test_every_stage_shape_is_constructible(shape: StageShape) -> None:
    built = stage(shape)
    assert built.shape is shape
    assert (built.content_canonical is None) == (shape not in (StageShape.S1, StageShape.S2))
    if shape is StageShape.S1:
        assert built.content_sha256 == VERIFIED_SHA
    if shape is StageShape.S2:
        assert built.content_sha256 == ANALYZED_SHA
    assert "Encrypted" not in repr(built) and "Data is" not in repr(built)


@pytest.mark.parametrize("shape", [StageShape.U1, StageShape.U2, StageShape.U5, StageShape.U6])
def test_unresolved_shapes_exist_for_analysis_too(shape: StageShape) -> None:
    assert stage(shape, analysis=True).stage is StageKind.ANALYSIS


@pytest.mark.parametrize(
    ("shape", "changes"),
    [
        (StageShape.S1, {"content": None}),
        (StageShape.S1, {"evidence_sha256": None}),
        (StageShape.S1, {"call_sequence": None, "request_sha256": None}),
        (StageShape.S1, {"request_sha256": "f" * 64}),  # content's request differs
        (StageShape.S1, {"question_id": "ENC-02"}),
        (StageShape.S1, {"unresolved_reason": UnresolvedReason.TIMEOUT}),
        (StageShape.S1, {"dependency_sha256": "d" * 64}),
        (StageShape.S2, {"evidence_sha256": "e" * 64}),
        (StageShape.S2, {"stage": StageKind.VERIFICATION}),
        (StageShape.U1, {"call_sequence": None, "request_sha256": None}),
        (StageShape.U1, {"content": None, "outcome": StageOutcome.VERIFIED}),
        (StageShape.U1, {"unresolved_reason": None}),
        (StageShape.U3, {"stage": StageKind.VERIFICATION, "dependency_sha256": None}),
        (StageShape.U3, {"call_sequence": 1, "request_sha256": "a" * 64}),
        (StageShape.U4, {"evidence_sha256": "e" * 64}),
        (StageShape.U4, {"call_sequence": 1, "request_sha256": "a" * 64}),
        (StageShape.U4, {"stage": StageKind.ANALYSIS, "dependency_sha256": "d" * 64}),
        (StageShape.U5, {"call_sequence": 1, "request_sha256": "a" * 64}),
        (StageShape.U5, {"evidence_sha256": None}),
        (StageShape.U6, {"call_sequence": None, "request_sha256": None}),
        (StageShape.U1, {"job_attempt": 0}),
        (StageShape.U1, {"call_sequence": 4}),
        (StageShape.U1, {"committed_at": datetime(2026, 10, 23)}),
        (StageShape.U1, {"surplus": 1}),
    ],
)
def test_one_field_deviations_are_refused(shape: StageShape, changes: dict[str, Any]) -> None:
    with pytest.raises(InvalidStageValueError) as caught:
        stage(shape, **changes)
    assert_fixed(caught.value, InvalidStageValueError)


# --- dependency digests ---------------------------------------------------------------------------


def test_dependency_digest_is_pinned_and_requires_a_well_formed_owner() -> None:
    common: dict[str, Any] = {
        "tenant_id": TENANT,
        "review_id": REVIEW,
        "question_id": QUESTION_ID,
        "question_sha256": PLAN_SHA,
    }
    verified_owner = rs.dependency_sha256(
        **common,
        owner_outcome=StageOutcome.VERIFIED,
        owner_content_sha256="c" * 64,
        owner_reason=None,
    )
    assert verified_owner == DEPENDENCY_SHA
    unresolved_owner = rs.dependency_sha256(
        **common,
        owner_outcome=StageOutcome.UNRESOLVED,
        owner_content_sha256=None,
        owner_reason=UnresolvedReason.TIMEOUT,
    )
    assert unresolved_owner == DEPENDENCY_UNRESOLVED_SHA
    for owner in (
        (StageOutcome.VERIFIED, None, None),
        (StageOutcome.VERIFIED, "c" * 64, UnresolvedReason.TIMEOUT),
        (StageOutcome.UNRESOLVED, "c" * 64, UnresolvedReason.TIMEOUT),
        (StageOutcome.UNRESOLVED, None, None),
        (StageOutcome.UNRESOLVED, None, UnresolvedReason.VERIFICATION_UNRESOLVED),
        (StageOutcome.ANALYZED, "c" * 64, None),
    ):
        with pytest.raises(InvalidStageValueError):
            rs.dependency_sha256(
                **common,
                owner_outcome=owner[0],
                owner_content_sha256=owner[1],
                owner_reason=owner[2],
            )


# --- fixed errors and process control in constructors ---------------------------------------------


def test_constructor_process_control_propagates_as_the_same_object() -> None:
    marker = SystemExit()

    class Exploding:
        def __eq__(self, other: object) -> bool:
            raise marker

        __hash__ = object.__hash__

    with pytest.raises(SystemExit) as caught:
        rs._same(Exploding(), Exploding, lambda value: value)
    assert caught.value is marker


# --- Prompt 201 Finding A: exact question validation before normalization -----------------------


class Text(str):
    """A ``str`` subclass: equal to its value, but not an exact ``str``."""


def constructed(**changes: Any) -> EvidenceQuestion:
    """A question built with ``model_construct`` (no validation), as the reviewer's probe did."""
    values: dict[str, Any] = {
        "question_id": QUESTION_ID,
        "text": QUESTION_TEXT,
        "search_queries": ("encryption at rest", "stored data encryption"),
        "requires_documentary_support": False,
    }
    values.update(changes)
    return EvidenceQuestion.model_construct(**values)


MALFORMED_QUESTIONS: dict[str, dict[str, Any]] = {
    "flag_int_1": {"requires_documentary_support": 1},
    "flag_int_0": {"requires_documentary_support": 0},
    "queries_list": {"search_queries": ["PRIVATE-CANARY-SEARCH"]},
    "id_str_subclass": {"question_id": Text(QUESTION_ID)},
    "text_str_subclass": {"text": Text(QUESTION_TEXT)},
    "query_str_subclass": {
        "search_queries": (Text("encryption at rest"), "stored data encryption")
    },
    "padded_text": {"text": f"  {QUESTION_TEXT}  "},
}


def empty_history(kind: StageKind, attempt: int = 1) -> rs.StageHistory:
    return rs.StageHistory(
        tenant_id=TENANT,
        review_id=REVIEW,
        job_id=JOB,
        question_id=QUESTION_ID,
        stage=kind,
        current_attempt=attempt,
        calls=(),
        committed=None,
    )


def question_entry_points() -> dict[str, Any]:
    """Every public M5e entry point that takes a planned question."""
    return {
        "revalidated_question": lambda q: rs.revalidated_question(q),
        "plan_question_canonical": lambda q: rs.plan_question_canonical(q),
        "planned_set": lambda q: PlannedQuestionSet(
            tenant_id=TENANT, review_id=REVIEW, questions=(q,)
        ),
        "evidence_record": lambda q: record(question=q),
        "trusted_question": lambda q: rs.TrustedQuestionStages(
            question=q,
            evidence=None,
            verification=None,
            analysis=None,
            verification_history=empty_history(StageKind.VERIFICATION),
            analysis_history=empty_history(StageKind.ANALYSIS),
        ),
    }


@pytest.mark.parametrize("entry", list(question_entry_points()))
@pytest.mark.parametrize("malformed", list(MALFORMED_QUESTIONS))
def test_question_boundary_refuses_malformed_fields_silently(
    entry: str,
    malformed: str,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    value = constructed(**MALFORMED_QUESTIONS[malformed])
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with pytest.raises(InvalidStageValueError) as refused:
            question_entry_points()[entry](value)
    assert_fixed(refused.value, InvalidStageValueError)
    assert [str(w.message) for w in caught] == []  # no Pydantic serialization warning
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == "" and caplog.records == []


@pytest.mark.parametrize("entry", list(question_entry_points()))
@pytest.mark.parametrize("flag", [True, False])
def test_question_boundary_valid_controls_keep_exact_types(entry: str, flag: bool) -> None:
    value = constructed(requires_documentary_support=flag)
    if entry != "evidence_record":  # the record fixture's question has the flag False
        question_entry_points()[entry](value)
    rebuilt = rs.revalidated_question(value)
    assert rebuilt.requires_documentary_support is flag
    assert type(rebuilt.question_id) is str and type(rebuilt.text) is str
    assert type(rebuilt.search_queries) is tuple
    assert all(type(query) is str for query in rebuilt.search_queries)
    assert rebuilt == question(requires_documentary_support=flag)


def test_question_boundary_evidence_record_valid_control() -> None:
    assert record(question=constructed()).question == question()


def test_question_boundary_process_control_propagates_as_the_same_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = KeyboardInterrupt()

    def interrupted(self: object, **data: object) -> None:
        raise marker

    monkeypatch.setattr(EvidenceQuestion, "__init__", interrupted)
    with pytest.raises(KeyboardInterrupt) as caught:
        rs.revalidated_question(constructed())
    assert caught.value is marker


# --- Prompt 201 Finding B: nested aggregate values are rebuilt ----------------------------------


def bypass(value: Any, **changes: object) -> Any:
    """A copy of a valid value with fields replaced without validation (constructor probing)."""
    copied = object.__new__(type(value))
    for name in value.__dataclass_fields__:
        object.__setattr__(copied, name, getattr(value, name))
    for name, change in changes.items():
        object.__setattr__(copied, name, change)
    return copied


def trusted_question(**changes: Any) -> rs.TrustedQuestionStages:
    values: dict[str, Any] = {
        "question": question(),
        "evidence": changes["evidence"] if "evidence" in changes else trusted(),
        "verification": None,
        "analysis": None,
        "verification_history": empty_history(StageKind.VERIFICATION),
        "analysis_history": empty_history(StageKind.ANALYSIS),
    }
    values.update(changes)
    return rs.TrustedQuestionStages(**values)


def trusted_stages(*questions: rs.TrustedQuestionStages) -> rs.TrustedStages:
    return rs.TrustedStages(
        tenant_id=TENANT, review_id=REVIEW, job_id=JOB, job_attempt=1, questions=questions
    )


def test_nested_aggregate_valid_controls_construct() -> None:
    item = trusted_question()
    assert item.evidence == trusted()
    assert trusted_question(evidence=None).evidence is None
    stages_ = trusted_stages(item)
    assert stages_.questions == (item,)
    replaced = dataclasses.replace(stages_, questions=(trusted_question(evidence=None),))
    assert replaced.questions[0].evidence is None


@pytest.mark.parametrize(
    "evidence",
    [
        lambda: bypass(trusted(), result="invalid result"),  # the reviewer's probe
        lambda: bypass(trusted(), question=constructed(requires_documentary_support=1)),
        lambda: bypass(trusted(), tenant_id=str(TENANT)),
        lambda: bypass(trusted(), snapshot_sha256="0" * 64),  # inconsistent with the result
        lambda: "evidence",
    ],
)
def test_nested_aggregate_trusted_question_rebuilds_its_evidence(evidence: Any) -> None:
    bad = evidence()
    with pytest.raises(InvalidStageValueError) as caught:
        trusted_question(evidence=bad)
    assert_fixed(caught.value, InvalidStageValueError)
    with pytest.raises(InvalidStageValueError):  # the replacement path runs the constructor
        dataclasses.replace(trusted_question(), evidence=bad)


@pytest.mark.parametrize(
    "item",
    [
        lambda: bypass(trusted_question(), evidence=bypass(trusted(), result="invalid")),  # probe
        lambda: bypass(trusted_question(), evidence="evidence"),
        lambda: bypass(trusted_question(), question=constructed(requires_documentary_support=1)),
        lambda: bypass(trusted_question(), verification_history="history"),
        lambda: "item",
    ],
)
def test_nested_aggregate_trusted_stages_rebuild_every_question(item: Any) -> None:
    bad = item()
    with pytest.raises(InvalidStageValueError) as caught:
        trusted_stages(bad)
    assert_fixed(caught.value, InvalidStageValueError)
    with pytest.raises(InvalidStageValueError):
        dataclasses.replace(trusted_stages(trusted_question()), questions=(bad,))


def in_flight_history() -> rs.StageHistory:
    return rs.StageHistory(
        tenant_id=TENANT,
        review_id=REVIEW,
        job_id=JOB,
        question_id=QUESTION_ID,
        stage=StageKind.VERIFICATION,
        current_attempt=1,
        calls=(call(),),
        committed=None,
    )


def test_nested_aggregate_stage_state_rebuilds_its_plan() -> None:
    history = in_flight_history()
    plan = rs.plan_stage(history)
    assert isinstance(plan, rs.PlanInFlight)
    state = rs.StageState(
        history=history, plan=plan, evidence_sha256="e" * 64, dependency_sha256=None
    )
    assert state.plan == plan
    assert isinstance(state.plan, rs.PlanInFlight) and type(state.plan.sequence) is int
    bad_plans: list[Any] = [
        bypass(plan, sequence=True),  # equal to the computed plan, but not an exact int
        bypass(plan, request_sha256="f" * 64),
        "plan",
    ]
    for bad in bad_plans:
        with pytest.raises(InvalidStageValueError) as caught:
            rs.StageState(
                history=history, plan=bad, evidence_sha256="e" * 64, dependency_sha256=None
            )
        assert_fixed(caught.value, InvalidStageValueError)
        with pytest.raises(InvalidStageValueError):
            dataclasses.replace(state, plan=bad)


def test_nested_aggregate_trusted_question_rebuilds_supplied_stages() -> None:
    malformed = bypass(empty_history(StageKind.VERIFICATION), current_attempt=True)
    with pytest.raises(InvalidStageValueError):
        trusted_question(verification_history=malformed)
    with pytest.raises(InvalidStageValueError):
        trusted_question(verification="stage")


def test_nested_aggregate_process_control_propagates_as_the_same_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = SystemExit()
    valid = trusted()

    def interrupted(self: object, **data: object) -> None:
        raise marker

    monkeypatch.setattr(QuestionEvidence, "__init__", interrupted)
    with pytest.raises(SystemExit) as caught:
        trusted_question(evidence=valid)
    assert caught.value is marker
