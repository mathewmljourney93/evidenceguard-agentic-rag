"""Provenance checks, status derivation, Analyst findings and reload validation
(``evidenceguard_domain.provenance``, M5b, ADR-0020), without a database or network.

Expected statuses, positions, counts, offsets and finding IDs are written by hand from the
accepted rules (``docs/plan.md`` M5b-B1 to M5b-F); finding IDs are pinned literals computed
independently with ``uuid5``. Accepted citations prove provenance only (a quote exists in a
supplied chunk), not that the passage supports a claim or that the document is authentic.
"""

import dataclasses
import hashlib
import socket
from datetime import UTC, datetime
from fractions import Fraction
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest

from evidenceguard_domain import provenance
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
    Finding,
    ReportContent,
    Severity,
    SourceType,
    Verdict,
    Verification,
)
from evidenceguard_domain.model_calls import CallOutcome, ModelPurpose, ModelUsage, StructuredResult
from evidenceguard_domain.provenance import (
    DOCUMENTARY_GAP_SEVERITY,
    DOCUMENTARY_GAP_STATEMENT,
    DOCUMENTARY_GAP_TITLE,
    FINDING_ID_NAMESPACE,
    MATCH_RULES,
    AnalyzedQuestion,
    FindingKind,
    InvalidProvenanceInputError,
    InvalidProvenanceValueError,
    ProvenanceRejection,
    QuestionEvidence,
    QuoteMatch,
    QuoteSpanKind,
    RejectionReason,
    RejectionStage,
    ValidatedClaim,
    VerifiedQuestion,
    analyze_question,
    derive_status,
    documentary_gap_finding,
    finding_id,
    recheck_analyzed,
    recheck_verified,
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
from evidenceguard_retrieval.embeddings import HASH_IDENTITY

R = RejectionReason
S = EvidenceStatus
V = Verdict

# Snapshot constants shared with tests/test_retrieval_contracts.py (index IDs derived there).
TENANT = UUID("11111111-1111-4111-8111-111111111111")
VENDOR = UUID("22222222-2222-4222-8222-222222222222")
REV_A = UUID("33333333-3333-4333-8333-333333333333")
DOC_A = UUID("44444444-4444-4444-8444-444444444444")
REV_B = UUID("55555555-5555-4555-8555-555555555555")
DOC_B = UUID("66666666-6666-4666-8666-666666666666")
INDEX_A = UUID("5b7601bd-c104-574b-afc4-8e43c3da8ecc")
INDEX_B = UUID("8eaf5c5b-c8a6-5fda-af5a-7d2071c6a86d")
REVIEW = UUID("88888888-8888-4888-8888-888888888888")
OTHER_REVIEW = UUID("99999999-9999-4999-8999-999999999999")
OTHER_TENANT = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")

C1 = UUID(int=1)  # vendor statement, revision A
C2 = UUID(int=2)  # contract, revision B
C3 = UUID(int=3)  # third-party report, revision B
C4 = UUID(int=4)  # vendor statement, revision B, repeats C1's first sentence
FOREIGN = UUID(int=99)  # never retrieved (forged, another tenant's or another question's chunk)

TEXT_1 = "Customer data is encrypted at rest with AES-256.\nKeys rotate yearly."
TEXT_2 = "The supplier shall encrypt customer data at rest."
TEXT_3 = "Auditors observed that backups are not encrypted."
TEXT_4 = "Customer data is encrypted at rest with AES-256."
BODY_SOURCE = 200

QUESTION_ID = "ENC-01"
OTHER_ID = "OTH-01"
CANARY = "CANARY-PROVENANCE-7Q"
DIGEST_A = "a" * 64
DIGEST_B = "b" * 64

# uuid5(UUID("56b13512-9167-5c9e-95c5-c6915da4cba6"), f"{TENANT}:{REVIEW}:ENC-01:{kind}:{i}"),
# computed independently with the standard library.
ANALYST_ID_0 = UUID("94754c8e-9757-50c6-b036-f76366a1293c")
ANALYST_ID_1 = UUID("79604212-0fce-5bb2-a375-8c597b8f30c3")
RULE_ID = UUID("1044b44d-2726-56ee-891c-1f6f1a3307be")


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("a test attempted network access")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


# --- fixtures ------------------------------------------------------------------------------------


def snapshot() -> RetrievalSnapshot:
    return RetrievalSnapshot(
        tenant_id=TENANT,
        vendor_id=VENDOR,
        identity=HASH_IDENTITY,
        config=RETRIEVAL_CONFIG_V1,
        bindings=(
            RevisionBinding(REV_A, DOC_A, INDEX_A, "md-v1", 2, "a" * 64, "b" * 64),
            RevisionBinding(REV_B, DOC_B, INDEX_B, "md-v1", 3, "c" * 64, "d" * 64),
        ),
        exclusions=PendingExclusions(0, (), False),
        captured_at=datetime(2026, 10, 17, 9, 30, tzinfo=UTC),
    )


SOURCES = {
    C1: (TEXT_1, SourceType.VENDOR_STATEMENT, REV_A, DOC_A),
    C2: (TEXT_2, SourceType.CONTRACT, REV_B, DOC_B),
    C3: (TEXT_3, SourceType.THIRD_PARTY_REPORT, REV_B, DOC_B),
    C4: (TEXT_4, SourceType.VENDOR_STATEMENT, REV_B, DOC_B),
}


def evidence_for(chunk_id: UUID, text: str | None = None) -> ChunkEvidence:
    body, source_type, _, _ = SOURCES[chunk_id]
    body = body if text is None else text
    return ChunkEvidence(
        chunk_id,
        body,
        hashlib.sha256(body.encode("utf-8")).hexdigest(),
        0,
        ("Encryption",),
        False,
        SourceSpan(5, 6, BODY_SOURCE, BODY_SOURCE + len(body)),
        None,
        "security-overview",
        "Security Overview",
        1,
        None,
        None,
        source_type,
        Authenticity.NOT_ESTABLISHED,
    )


def retrieved(*chunk_ids: UUID, texts: dict[UUID, str] | None = None) -> RetrievalResult:
    texts = texts or {}
    items = tuple(
        RetrievedChunk(
            chunk_id=chunk_id,
            revision_id=SOURCES[chunk_id][2],
            document_id=SOURCES[chunk_id][3],
            fused_rank=rank,
            fused_score=Fraction(1, 61),
            hits=(ChannelHit(0, "lexical", 1, 1.0),),
            evidence=evidence_for(chunk_id, texts.get(chunk_id)),
        )
        for rank, chunk_id in enumerate(sorted(chunk_ids), start=1)
    )
    return RetrievalResult(snapshot(), 1, 8, (), items)


def question(question_id: str = QUESTION_ID, *, documentary: bool = False) -> EvidenceQuestion:
    return EvidenceQuestion(
        question_id=question_id,
        text="Is customer data encrypted at rest?",
        search_queries=("encryption at rest",),
        requires_documentary_support=documentary,
    )


def trusted(
    *chunk_ids: UUID,
    question_id: str = QUESTION_ID,
    documentary: bool = False,
    review_id: UUID = REVIEW,
    texts: dict[UUID, str] | None = None,
) -> QuestionEvidence:
    result = retrieved(*(chunk_ids or (C1, C2, C3, C4)), texts=texts)
    return QuestionEvidence(
        tenant_id=TENANT,
        review_id=review_id,
        snapshot_sha256=result.snapshot_sha256,
        question=question(question_id, documentary=documentary),
        result=result,
    )


Ref = tuple[UUID, str]


def claim(text: str, *refs: Ref) -> ClaimOutput:
    return ClaimOutput(
        text=text, citations=tuple(QuoteRef(chunk_id=str(c), quote=q) for c, q in refs)
    )


def verifier_result(
    verdict: Verdict,
    *claims: ClaimOutput,
    rationale: str = "Based on the cited passages.",
    question_id: str = QUESTION_ID,
    request_sha256: str = DIGEST_A,
) -> StructuredResult:
    output = VerifierOutput(verdict=verdict, claims=claims, rationale=rationale)
    return completed(ModelPurpose.VERIFIER, output, question_id, request_sha256)


def completed(
    purpose: ModelPurpose,
    output: VerifierOutput | AnalystOutput,
    question_id: str,
    request_sha256: str,
) -> StructuredResult:
    return StructuredResult(
        request_sha256=request_sha256,
        purpose=purpose,
        question_id=question_id,
        outcome=CallOutcome.COMPLETED,
        dispatched=True,
        output=output,
        model_requested="fake-scripted-v1",
        model_used="fake-scripted-v1",
        usage=ModelUsage(0, 0),
        latency_ms=None,
    )


def verified(
    verdict: Verdict = V.SUPPORTED,
    *claims: ClaimOutput,
    evidence: QuestionEvidence | None = None,
    question_id: str = QUESTION_ID,
) -> VerifiedQuestion:
    claims = claims or (claim("Encrypted at rest.", (C1, "encrypted at rest")),)
    value = verify_question(
        evidence or trusted(question_id=question_id),
        verifier_result(verdict, *claims, question_id=question_id),
    )
    assert type(value) is VerifiedQuestion
    return value


def finding_output(
    *refs: Ref,
    question_ids: tuple[str, ...] = (QUESTION_ID,),
    title: str = "Encryption at rest",
    statement: str = "Data is encrypted at rest.",
    follow_ups: tuple[str, ...] = (),
) -> FindingOutput:
    return FindingOutput(
        question_ids=question_ids,
        title=title,
        severity=Severity.LOW,
        statement=statement,
        citations=tuple(QuoteRef(chunk_id=str(c), quote=q) for c, q in refs),
        follow_up_questions=follow_ups,
    )


def analyst_result(
    *findings: FindingOutput, question_id: str = QUESTION_ID, request_sha256: str = DIGEST_B
) -> StructuredResult:
    return completed(
        ModelPurpose.RISK_ANALYST, AnalystOutput(findings=findings), question_id, request_sha256
    )


def rejection(
    reason: RejectionReason,
    item: int | None,
    citation: int | None,
    count: int,
    stage: RejectionStage = RejectionStage.VERIFICATION,
) -> ProvenanceRejection:
    return ProvenanceRejection(
        stage=stage,
        question_id=QUESTION_ID,
        reason=reason,
        item_index=item,
        citation_index=citation,
        rejected_count=count,
    )


def cite(chunk_id: UUID, quote: str, tenant: UUID = TENANT) -> Citation:
    return Citation(
        tenant_id=tenant,
        document_revision_id=SOURCES[chunk_id][2],
        chunk_id=chunk_id,
        source_type=SOURCES[chunk_id][1],
        quote=quote,
    )


# --- verification: accepted values ---------------------------------------------------------------


def test_supported_vendor_statement_gives_vendor_claim() -> None:
    value = verified()
    assert value.tenant_id == TENANT and value.review_id == REVIEW
    assert value.question_id == QUESTION_ID and value.match_rules == MATCH_RULES
    assert value.request_sha256 == DIGEST_A
    assert value.snapshot_sha256 == retrieved(C1).snapshot_sha256
    verification = value.verification
    assert (verification.verdict, verification.evidence_status) == (V.SUPPORTED, S.VENDOR_CLAIM)
    assert verification.citations == (cite(C1, "encrypted at rest"),)
    assert verification.citations[0].authenticity is Authenticity.NOT_ESTABLISHED
    assert value.claims == (ValidatedClaim(text="Encrypted at rest.", citation_indexes=(0,)),)
    accepted = value.provenance[0]
    assert accepted.document_id == DOC_A
    assert accepted.match == QuoteMatch(
        kind=QuoteSpanKind.BODY,
        text_start=17,
        text_end=34,
        source_char_start=BODY_SOURCE + 17,
        source_char_end=BODY_SOURCE + 34,
        quote="encrypted at rest",
        occurrences=1,
    )


def test_metadata_comes_only_from_trusted_evidence() -> None:
    """The model supplies a chunk ID and a quote; tenant, revision, document, source type and
    authenticity come from the retrieved item."""
    value = verified(V.SUPPORTED, claim("c", (C2, "shall encrypt customer data")))
    citation = value.verification.citations[0]
    assert (citation.tenant_id, citation.document_revision_id) == (TENANT, REV_B)
    assert citation.source_type is SourceType.CONTRACT
    assert value.provenance[0].document_id == DOC_B
    assert value.verification.evidence_status is S.DOCUMENTARY_SUPPORT


def test_rationale_is_stored_stripped() -> None:
    value = verify_question(
        trusted(),
        verifier_result(
            V.SUPPORTED, claim("c", (C1, "encrypted at rest")), rationale="  Reasoned.\n"
        ),
    )
    assert isinstance(value, VerifiedQuestion)
    assert value.verification.rationale == "Reasoned."


def test_stored_quote_is_the_exact_original() -> None:
    value = verified(V.SUPPORTED, claim("c", (C1, "AES-256.   Keys rotate")))
    assert value.verification.citations[0].quote == "AES-256.\nKeys rotate"


# --- status table (M5b-D) ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("verdict", "refs", "expected"),
    [
        (V.SUPPORTED, [(C1, "encrypted at rest")], S.VENDOR_CLAIM),
        (V.SUPPORTED, [(C1, "encrypted at rest"), (C4, "AES-256")], S.VENDOR_CLAIM),
        (V.SUPPORTED, [(C1, "encrypted at rest"), (C2, "shall encrypt")], S.DOCUMENTARY_SUPPORT),
        (V.SUPPORTED, [(C3, "backups are not encrypted")], S.DOCUMENTARY_SUPPORT),
        (V.CONTRADICTED, [(C1, "encrypted at rest"), (C3, "not encrypted")], S.CONFLICTING),
        (V.CONTRADICTED, [(C1, "encrypted at rest"), (C1, "Keys rotate yearly")], S.CONFLICTING),
        (V.INSUFFICIENT_EVIDENCE, [(C1, "Keys rotate yearly")], S.MISSING),
        (V.INSUFFICIENT_EVIDENCE, [], S.MISSING),
    ],
)
def test_status_rows(verdict: Verdict, refs: list[Ref], expected: EvidenceStatus) -> None:
    claims = (claim("c", *refs),) if refs else ()
    value = verify_question(trusted(), verifier_result(verdict, *claims))
    assert isinstance(value, VerifiedQuestion)
    assert value.verification.evidence_status is expected
    assert len(value.verification.citations) == len(refs)


@pytest.mark.parametrize(
    ("verdict", "claims"),
    [
        (V.SUPPORTED, ()),
        (V.CONTRADICTED, (claim("c", (C1, "encrypted at rest")),)),
        # the same quote text from two chunks counts once
        (
            V.CONTRADICTED,
            (
                claim(
                    "c",
                    (C1, "encrypted at rest with AES-256"),
                    (C4, "encrypted at rest with AES-256"),
                ),
            ),
        ),
        (V.CONTRADICTED, ()),
    ],
)
def test_unsupported_verdicts(verdict: Verdict, claims: tuple[ClaimOutput, ...]) -> None:
    value = verify_question(trusted(), verifier_result(verdict, *claims))
    assert value == rejection(R.VERDICT_UNSUPPORTED, None, None, 1)


def test_insufficient_evidence_keeps_citations_and_uncited_claims() -> None:
    value = verify_question(
        trusted(),
        verifier_result(
            V.INSUFFICIENT_EVIDENCE,
            claim("cited", (C1, "Keys rotate yearly")),
            claim("uncited"),
        ),
    )
    assert isinstance(value, VerifiedQuestion)
    assert value.verification.citations == (cite(C1, "Keys rotate yearly"),)
    assert [c.citation_indexes for c in value.claims] == [(0,), ()]


# --- deduplication --------------------------------------------------------------------------------


def test_deduplication_across_and_within_claims_with_canonical_indexes() -> None:
    value = verified(
        V.SUPPORTED,
        claim("first", (C1, "encrypted at rest"), (C2, "shall encrypt")),
        claim("second", (C2, "shall  encrypt"), (C1, "encrypted\nat rest")),
        claim("third", (C1, "Keys rotate"), (C1, "Keys  rotate")),
    )
    assert value.verification.citations == (
        cite(C1, "encrypted at rest"),
        cite(C2, "shall encrypt"),
        cite(C1, "Keys rotate"),
    )
    assert [c.citation_indexes for c in value.claims] == [(0, 1), (1, 0), (2,)]


def test_span_forms_are_computed_once_per_chunk(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[UUID] = []
    original = provenance._chunk_forms

    def counting(evidence: ChunkEvidence) -> Any:
        calls.append(evidence.chunk_id)
        return original(evidence)

    monkeypatch.setattr(provenance, "_chunk_forms", counting)
    verified(
        V.SUPPORTED,
        claim("a", (C1, "encrypted at rest"), (C1, "Keys rotate"), (C2, "shall encrypt")),
        claim("b", (C1, "AES-256"), (C2, "customer data")),
    )
    assert sorted(calls) == [C1, C2]


# --- claim coverage (P7) -------------------------------------------------------------------------


@pytest.mark.parametrize("verdict", [V.SUPPORTED, V.CONTRADICTED])
def test_every_supported_or_contradicted_claim_must_be_cited(verdict: Verdict) -> None:
    value = verify_question(
        trusted(),
        verifier_result(
            verdict,
            claim("cited", (C1, "encrypted at rest"), (C3, "not encrypted")),
            claim("uncited"),
            claim("also uncited"),
        ),
    )
    assert value == rejection(R.CLAIM_UNCITED, 1, None, 2)


# --- phase 1 failures, precedence and counts -------------------------------------------------


@pytest.mark.parametrize(
    ("ref", "reason"),
    [
        ((FOREIGN, "encrypted at rest"), R.CHUNK_NOT_RETRIEVED),
        ((C1, "   "), R.QUOTE_BLANK),
        ((C1, "decrypted at rest"), R.QUOTE_NOT_FOUND),
        ((C1, "encrypted at rest with AES-256. Keys rotate monthly"), R.QUOTE_NOT_FOUND),
    ],
)
def test_reference_failures(ref: Ref, reason: RejectionReason) -> None:
    value = verify_question(trusted(), verifier_result(V.SUPPORTED, claim("c", ref)))
    assert value == rejection(reason, 0, 0, 1)
    assert not isinstance(value, VerifiedQuestion)


def test_a_chunk_retrieved_only_for_another_question_is_not_retrieved() -> None:
    evidence = trusted(C1)  # this question's result holds C1 only; C2 belongs to another result
    value = verify_question(
        evidence, verifier_result(V.SUPPORTED, claim("c", (C2, "shall encrypt")))
    )
    assert value == rejection(R.CHUNK_NOT_RETRIEVED, 0, 0, 1)


def test_too_long_original_in_a_verification() -> None:
    body = "e\u0301" * 500 + "x"
    evidence = trusted(C1, texts={C1: body})
    value = verify_question(
        evidence, verifier_result(V.SUPPORTED, claim("c", (C1, "\xe9" * 500 + "x")))
    )
    assert value == rejection(R.QUOTE_TOO_LONG, 0, 0, 1)


def test_not_exact_original_in_a_verification() -> None:
    evidence = trusted(C1, texts={C1: "a \u0301b"})
    value = verify_question(evidence, verifier_result(V.SUPPORTED, claim("c", (C1, " \u0301b"))))
    assert value == rejection(R.QUOTE_NOT_EXACT, 0, 0, 1)


def test_simultaneous_failures_report_the_lowest_position_of_the_first_phase() -> None:
    value = verify_question(
        trusted(),
        verifier_result(
            V.SUPPORTED,
            claim("ok then bad", (C1, "encrypted at rest"), (C1, "absent text")),
            claim("forged", (FOREIGN, "anything"), (C2, "shall encrypt")),
            claim("uncited"),
            rationale="   ",
        ),
    )
    assert value == rejection(R.QUOTE_NOT_FOUND, 0, 1, 2)


def test_phase_two_failure_hides_phase_three() -> None:
    value = verify_question(
        trusted(),
        verifier_result(
            V.SUPPORTED, claim("c", (C1, "encrypted at rest")), claim("u"), rationale=" "
        ),
    )
    assert value == rejection(R.CLAIM_UNCITED, 1, None, 1)


def test_phase_three_counts_both_aggregate_failures() -> None:
    assert verify_question(trusted(), verifier_result(V.SUPPORTED, rationale="  ")) == rejection(
        R.VERDICT_UNSUPPORTED, None, None, 2
    )
    value = verify_question(
        trusted(), verifier_result(V.SUPPORTED, claim("c", (C1, "encrypted")), rationale="\n")
    )
    assert value == rejection(R.RATIONALE_BLANK, None, None, 1)


def test_rejection_provenance_check_mapping() -> None:
    assert rejection(R.QUOTE_NOT_FOUND, 0, 0, 1).provenance_check == "citation_rejected"
    assert rejection(R.CLAIM_UNCITED, 0, None, 1).provenance_check == "citation_rejected"
    assert rejection(R.VERDICT_UNSUPPORTED, None, None, 1).provenance_check == "invalid_output"
    analysis = RejectionStage.ANALYSIS
    assert rejection(R.CITATION_NOT_SHARED, 0, 0, 1, analysis).provenance_check == (
        "citation_rejected"
    )
    assert rejection(R.MIXED_VERDICTS, 0, None, 1, analysis).provenance_check == "invalid_output"


# --- trusted input binding -----------------------------------------------------------------------


def test_question_evidence_binding() -> None:
    result = retrieved(C1)
    base: dict[str, Any] = {
        "tenant_id": TENANT,
        "review_id": REVIEW,
        "snapshot_sha256": result.snapshot_sha256,
        "question": question(),
        "result": result,
    }
    assert QuestionEvidence(**base).result == result
    for change in (
        {"tenant_id": OTHER_TENANT},
        {"tenant_id": str(TENANT)},
        {"review_id": None},
        {"snapshot_sha256": "0" * 64},
        {"snapshot_sha256": result.snapshot_sha256.upper()},
        {"question": question().model_dump()},
        {"result": result.items},
        {"extra": 1},
    ):
        with pytest.raises(InvalidProvenanceValueError):
            QuestionEvidence(**{**base, **change})


@pytest.mark.parametrize(
    "result",
    [
        StructuredResult(
            request_sha256=DIGEST_A,
            purpose=ModelPurpose.VERIFIER,
            question_id=QUESTION_ID,
            outcome=CallOutcome.REFUSAL,
            dispatched=True,
            output=None,
            model_requested="fake-scripted-v1",
            model_used="fake-scripted-v1",
            usage=ModelUsage(0, 0),
            latency_ms=None,
        ),
        completed(ModelPurpose.RISK_ANALYST, AnalystOutput(), QUESTION_ID, DIGEST_A),
        verifier_result(V.SUPPORTED, question_id=OTHER_ID),
        "not a result",
    ],
)
def test_verify_rejects_bad_call_input(result: Any) -> None:
    with pytest.raises(InvalidProvenanceInputError) as raised:
        verify_question(trusted(), result)
    assert raised.value.__cause__ is None and raised.value.__context__ is None


def test_verify_rejects_bad_or_bypassed_evidence() -> None:
    call = verifier_result(V.SUPPORTED, claim("c", (C1, "encrypted at rest")))
    with pytest.raises(InvalidProvenanceInputError):
        verify_question("evidence", call)  # type: ignore[arg-type]
    evidence = trusted()
    object.__setattr__(evidence, "snapshot_sha256", "0" * 64)
    with pytest.raises(InvalidProvenanceInputError):
        verify_question(evidence, call)


def test_internal_inconsistency_is_a_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Building the derived Verification cannot fail for supported inputs; if it did, the error
    is ``InvalidProvenanceValueError``, not an input error."""

    def broken(**kwargs: Any) -> Verification:
        raise ValueError(CANARY)

    monkeypatch.setattr(provenance, "Verification", broken)
    with pytest.raises(InvalidProvenanceValueError) as raised:
        verify_question(
            trusted(), verifier_result(V.SUPPORTED, claim("c", (C1, "encrypted at rest")))
        )
    assert CANARY not in str(raised.value) and raised.value.__context__ is None


# --- value invariants (M5b-B1) -------------------------------------------------------------------


def test_validated_claim_bounds() -> None:
    assert ValidatedClaim(text="x" * 1000, citation_indexes=tuple(range(8))).text == "x" * 1000
    assert ValidatedClaim(text=" kept ", citation_indexes=(79,)).text == " kept "
    for text, indexes in (
        ("", ()),
        ("x" * 1001, ()),
        ("a\x00", ()),
        ("ok", (True,)),
        ("ok", (80,)),
        ("ok", (-1,)),
        ("ok", (1, 1)),
        ("ok", tuple(range(9))),
        ("ok", [0]),
    ):
        with pytest.raises(InvalidProvenanceValueError):
            ValidatedClaim(text=text, citation_indexes=indexes)  # type: ignore[arg-type]


def test_accepted_citation_invariants() -> None:
    accepted = verified().provenance[0]
    with pytest.raises(InvalidProvenanceValueError):
        dataclasses.replace(accepted, document_id=str(DOC_A))  # type: ignore[arg-type]
    other = dataclasses.replace(accepted.match, quote="encrypted at resT")
    with pytest.raises(InvalidProvenanceValueError):
        dataclasses.replace(accepted, match=other)
    with pytest.raises(InvalidProvenanceValueError):
        dataclasses.replace(accepted, citation=accepted.citation.model_dump())  # type: ignore[arg-type]


def two_citation_value() -> VerifiedQuestion:
    return verified(
        V.SUPPORTED,
        claim("a", (C1, "encrypted at rest")),
        claim("b", (C1, "Keys rotate yearly")),
    )


def test_verified_question_constructor_invariants() -> None:
    value = two_citation_value()
    assert dataclasses.replace(value) == value
    bad_changes: list[dict[str, Any]] = [
        {"match_rules": "eg-quote-match-v2"},
        {"request_sha256": DIGEST_A.upper()},
        {"snapshot_sha256": "x"},
        {"question_id": OTHER_ID},
        {"question_id": "bad"},
        {"tenant_id": OTHER_TENANT},
        {"review_id": str(REVIEW)},
        {"provenance": tuple(reversed(value.provenance))},
        {"provenance": value.provenance[:1]},
        {"claims": tuple(reversed(value.claims))},  # first appearances 1, 0: not canonical
        {"claims": (ValidatedClaim(text="a", citation_indexes=(0, 1)),) * 11},
        {"claims": (*value.claims, ValidatedClaim(text="u", citation_indexes=()))},
        {"claims": (ValidatedClaim(text="a", citation_indexes=(0,)),)},  # index 1 unreferenced
        {"claims": (ValidatedClaim(text="a", citation_indexes=(0, 2)),)},
        {"claims": list(value.claims)},
        {"verification": value.verification.model_dump()},
    ]
    for change in bad_changes:
        with pytest.raises(InvalidProvenanceValueError):
            dataclasses.replace(value, **change)


def test_verified_question_rejects_more_than_80_citations() -> None:
    value = verified()
    with pytest.raises(InvalidProvenanceValueError):
        dataclasses.replace(value, provenance=value.provenance * 81)


def test_values_are_frozen() -> None:
    value = verified()
    with pytest.raises(dataclasses.FrozenInstanceError):
        value.question_id = OTHER_ID  # type: ignore[misc]
    assert type(value.claims) is tuple and type(value.provenance) is tuple


# --- reload validation (recheck_verified) ----------------------------------------------------


def rebuild(value: VerifiedQuestion, index: int = 0, **citation_changes: Any) -> VerifiedQuestion:
    """A directly constructed variant whose citation ``index`` has other metadata (with the
    status re-derived so the value still constructs)."""
    accepted = value.provenance[index]
    changed = accepted.citation.model_copy(update=citation_changes)
    citations = list(value.verification.citations)
    citations[index] = changed
    status = derive_status(value.verification.verdict, tuple(citations))
    assert status is not None
    verification = value.verification.model_copy(
        update={"citations": tuple(citations), "evidence_status": status}
    )
    provenance_items = list(value.provenance)
    provenance_items[index] = dataclasses.replace(accepted, citation=changed)
    return dataclasses.replace(value, verification=verification, provenance=tuple(provenance_items))


def with_match(value: VerifiedQuestion, **changes: Any) -> VerifiedQuestion:
    accepted = value.provenance[0]
    match = dataclasses.replace(accepted.match, **changes)
    return dataclasses.replace(value, provenance=(dataclasses.replace(accepted, match=match),))


def test_recheck_accepts_the_unaltered_value() -> None:
    value = verified()
    assert recheck_verified(value, trusted()) == value
    two = two_citation_value()
    assert recheck_verified(two, trusted()) == two


@pytest.mark.parametrize(
    "changes",
    [
        {"source_char_start": BODY_SOURCE + 18, "source_char_end": BODY_SOURCE + 35},
        {"text_start": 18, "text_end": 35, "source_char_start": 218, "source_char_end": 235},
        {"kind": QuoteSpanKind.HEADER},
        {"occurrences": 2},
    ],
)
def test_recheck_detects_altered_match_fields(changes: dict[str, Any]) -> None:
    altered = with_match(verified(), **changes)
    with pytest.raises(InvalidProvenanceInputError):
        recheck_verified(altered, trusted())


@pytest.mark.parametrize(
    "changes",
    [
        {"document_revision_id": REV_B},
        {"source_type": SourceType.CONTRACT},
        {"chunk_id": C4},
    ],
)
def test_recheck_detects_altered_metadata(changes: dict[str, Any]) -> None:
    with pytest.raises(InvalidProvenanceInputError):
        recheck_verified(rebuild(verified(), **changes), trusted())


def test_recheck_detects_altered_document() -> None:
    value = verified()
    accepted = dataclasses.replace(value.provenance[0], document_id=DOC_B)
    with pytest.raises(InvalidProvenanceInputError):
        recheck_verified(dataclasses.replace(value, provenance=(accepted,)), trusted())


def test_recheck_detects_bypassed_values() -> None:
    for field_name, bypass in (
        ("match_rules", "eg-quote-match-v2"),
        ("claims", tuple(reversed(two_citation_value().claims))),
        ("provenance", tuple(reversed(two_citation_value().provenance))),
    ):
        value = two_citation_value()
        object.__setattr__(value, field_name, bypass)
        with pytest.raises(InvalidProvenanceInputError):
            recheck_verified(value, trusted())


def test_recheck_detects_identity_and_evidence_changes() -> None:
    value = verified()
    for evidence in (
        trusted(review_id=OTHER_REVIEW),
        trusted(question_id=OTHER_ID),
        trusted(C2, C3, C4),  # C1 no longer retrieved
        trusted(texts={C1: "Prefix. " + TEXT_1}),  # same quote at other offsets
        trusted(texts={C1: TEXT_1 + " Data is encrypted at rest."}),  # occurrence count 2
    ):
        with pytest.raises(InvalidProvenanceInputError):
            recheck_verified(value, evidence)


def test_recheck_uses_the_first_occurrence_of_the_stored_original() -> None:
    """The model quote's whitespace differs from the stored original, yet recomputation from the
    stored original selects the same occurrence."""
    value = verified(V.SUPPORTED, claim("c", (C1, "AES-256. Keys")))
    assert value.verification.citations[0].quote == "AES-256.\nKeys"
    assert recheck_verified(value, trusted()) == value


# --- analysis ------------------------------------------------------------------------------------


def test_finding_from_a_validated_citation() -> None:
    owner = verified()
    value = analyze_question(
        owner,
        question(),
        analyst_result(
            finding_output((C1, "encrypted   at rest"), follow_ups=("Which keys?", " Who? "))
        ),
    )
    assert isinstance(value, AnalyzedQuestion)
    assert (value.tenant_id, value.review_id, value.question_id) == (TENANT, REVIEW, QUESTION_ID)
    assert value.request_sha256 == DIGEST_B  # the Analyst call's own digest
    (finding,) = value.findings
    assert finding.finding_id == ANALYST_ID_0
    assert finding.citations == (cite(C1, "encrypted at rest"),)
    assert finding.evidence_status is S.VENDOR_CLAIM
    assert (finding.title, finding.severity) == ("Encryption at rest", Severity.LOW)
    assert value.follow_up_questions == (("Which keys?", " Who? "),)


def test_finding_ids_follow_positions() -> None:
    value = analyze_question(
        verified(), question(), analyst_result(finding_output(), finding_output())
    )
    assert isinstance(value, AnalyzedQuestion)
    assert [f.finding_id for f in value.findings] == [ANALYST_ID_0, ANALYST_ID_1]
    assert [f.evidence_status for f in value.findings] == [S.MISSING, S.MISSING]


@pytest.mark.parametrize(
    ("verdict", "claims", "refs", "expected"),
    [
        (
            V.SUPPORTED,
            [(C1, "encrypted at rest"), (C2, "shall encrypt")],
            [(C1, "encrypted at rest")],
            S.VENDOR_CLAIM,
        ),
        (
            V.SUPPORTED,
            [(C1, "encrypted at rest"), (C2, "shall encrypt")],
            [(C2, "shall encrypt")],
            S.DOCUMENTARY_SUPPORT,
        ),
        (
            V.CONTRADICTED,
            [(C1, "encrypted at rest"), (C3, "not encrypted")],
            [(C1, "encrypted at rest"), (C3, "not encrypted")],
            S.CONFLICTING,
        ),
        (
            V.INSUFFICIENT_EVIDENCE,
            [(C1, "Keys rotate yearly")],
            [(C1, "Keys rotate yearly")],
            S.MISSING,
        ),
        (V.SUPPORTED, [(C1, "encrypted at rest")], [], S.MISSING),
    ],
)
def test_finding_status_from_verdict_and_own_citations(
    verdict: Verdict, claims: list[Ref], refs: list[Ref], expected: EvidenceStatus
) -> None:
    owner = verified(verdict, claim("c", *claims))
    value = analyze_question(owner, question(), analyst_result(finding_output(*refs)))
    assert isinstance(value, AnalyzedQuestion)
    assert value.findings[0].evidence_status is expected


def analysis_rejection(
    reason: RejectionReason, item: int, citation: int | None = None, count: int = 1
) -> ProvenanceRejection:
    return rejection(reason, item, citation, count, RejectionStage.ANALYSIS)


@pytest.mark.parametrize(
    ("finding", "expected"),
    [
        (
            finding_output(question_ids=(QUESTION_ID, OTHER_ID)),
            analysis_rejection(R.FOREIGN_QUESTION, 0),
        ),
        (finding_output(question_ids=(OTHER_ID,)), analysis_rejection(R.FOREIGN_QUESTION, 0)),
        (finding_output((C2, "shall encrypt")), analysis_rejection(R.CITATION_NOT_VALIDATED, 0, 0)),
        (finding_output((C1, "encrypted at")), analysis_rejection(R.CITATION_NOT_VALIDATED, 0, 0)),
        (
            finding_output((C1, "encrypted at rest"), (C4, "encrypted at rest")),
            analysis_rejection(R.CITATION_NOT_VALIDATED, 0, 1),
        ),
        (finding_output((C1, "  ")), analysis_rejection(R.CITATION_NOT_VALIDATED, 0, 0)),
        (finding_output(title="   "), analysis_rejection(R.FINDING_TEXT_BLANK, 0)),
        (finding_output(statement="\n"), analysis_rejection(R.FINDING_TEXT_BLANK, 0)),
        (
            finding_output(question_ids=(OTHER_ID,), title=" "),
            analysis_rejection(R.FOREIGN_QUESTION, 0),
        ),
    ],
)
def test_finding_rejections(finding: FindingOutput, expected: ProvenanceRejection) -> None:
    assert analyze_question(verified(), question(), analyst_result(finding)) == expected


def test_one_sided_conflict_is_unsupported() -> None:
    owner = verified(V.CONTRADICTED, claim("c", (C1, "encrypted at rest"), (C3, "not encrypted")))
    value = analyze_question(
        owner, question(), analyst_result(finding_output((C1, "encrypted at rest")))
    )
    assert value == analysis_rejection(R.FINDING_STATUS_UNSUPPORTED, 0)


def test_every_finding_is_checked_and_the_lowest_is_reported() -> None:
    value = analyze_question(
        verified(),
        question(),
        analyst_result(
            finding_output((C1, "encrypted at rest")),
            finding_output((C1, "encrypted at rest"), (C2, "shall encrypt")),
            finding_output(question_ids=(OTHER_ID,)),
            finding_output(title=" "),
        ),
    )
    assert value == analysis_rejection(R.CITATION_NOT_VALIDATED, 1, 1, 3)


def shared_owner(verdict: Verdict = V.SUPPORTED, *refs: Ref) -> VerifiedQuestion:
    refs = refs or ((C1, "encrypted at rest"),)
    return verified(
        verdict, claim("c", *refs), evidence=trusted(question_id=OTHER_ID), question_id=OTHER_ID
    )


def test_multi_question_finding_with_shared_citations() -> None:
    value = analyze_question(
        verified(),
        question(),
        analyst_result(
            finding_output((C1, "encrypted at rest"), question_ids=(OTHER_ID, QUESTION_ID))
        ),
        shared=(shared_owner(),),
    )
    assert isinstance(value, AnalyzedQuestion)
    assert value.findings[0].question_ids == (OTHER_ID, QUESTION_ID)
    assert value.findings[0].evidence_status is S.VENDOR_CLAIM


def test_multi_question_citation_must_be_shared() -> None:
    owner = verified(V.SUPPORTED, claim("c", (C1, "encrypted at rest"), (C1, "Keys rotate yearly")))
    value = analyze_question(
        owner,
        question(),
        analyst_result(
            finding_output(
                (C1, "encrypted at rest"),
                (C1, "Keys rotate yearly"),
                question_ids=(QUESTION_ID, OTHER_ID),
            )
        ),
        shared=(shared_owner(),),
    )
    assert value == analysis_rejection(R.CITATION_NOT_SHARED, 0, 1)


def test_mixed_verdicts_are_rejected() -> None:
    other = shared_owner(V.INSUFFICIENT_EVIDENCE, (C1, "encrypted at rest"))
    value = analyze_question(
        verified(),
        question(),
        analyst_result(
            finding_output((C1, "encrypted at rest"), question_ids=(QUESTION_ID, OTHER_ID))
        ),
        shared=(other,),
    )
    assert value == analysis_rejection(R.MIXED_VERDICTS, 0)


def test_analysis_rejection_leaves_the_owner_unchanged() -> None:
    owner = verified()
    before = dataclasses.replace(owner)
    rejected = analyze_question(owner, question(), analyst_result(finding_output((C2, "shall"))))
    assert isinstance(rejected, ProvenanceRejection)
    assert owner == before and recheck_verified(owner, trusted()) == owner


def test_valid_empty_analysis() -> None:
    owner = verified()
    value = analyze_question(owner, question(), analyst_result())
    assert value == AnalyzedQuestion(
        tenant_id=TENANT,
        review_id=REVIEW,
        question_id=QUESTION_ID,
        request_sha256=DIGEST_B,
        findings=(),
        follow_up_questions=(),
    )
    assert recheck_analyzed(value, owner, question()) == value


@pytest.mark.parametrize("findings", [(), (finding_output(),)])
def test_analysis_identity_is_checked_before_findings(findings: tuple[FindingOutput, ...]) -> None:
    owner = verified()
    other_review = verified(evidence=trusted(review_id=OTHER_REVIEW))
    good = analyst_result(*findings)
    cases: list[tuple[Any, Any, Any, Any]] = [
        (owner, question(OTHER_ID), good, ()),
        (owner, question(), analyst_result(*findings, question_id=OTHER_ID), ()),
        (owner, question(), verifier_result(V.SUPPORTED), ()),
        (
            owner,
            question(),
            completed(
                ModelPurpose.RISK_ANALYST, AnalystOutput(findings=findings), QUESTION_ID, DIGEST_B
            ),
            [shared_owner()],
        ),
        (owner, question(), good, (owner,)),
        (owner, question(), good, (shared_owner(), shared_owner())),
        (owner, question(), good, (other_review,)),
        (owner, question(), good, (shared_owner(),) * 20),
        (owner, question().model_dump(), good, ()),
        ("owner", question(), good, ()),
    ]
    for owner_value, question_value, result, shared in cases:
        with pytest.raises(InvalidProvenanceInputError) as raised:
            analyze_question(owner_value, question_value, result, shared=shared)
        assert raised.value.__cause__ is None and raised.value.__context__ is None


def test_shared_values_must_share_review_tenant_and_snapshot() -> None:
    other_review = verify_question(
        trusted(question_id=OTHER_ID, review_id=OTHER_REVIEW),
        verifier_result(V.SUPPORTED, claim("c", (C1, "encrypted at rest")), question_id=OTHER_ID),
    )
    assert isinstance(other_review, VerifiedQuestion)
    with pytest.raises(InvalidProvenanceInputError):
        analyze_question(verified(), question(), analyst_result(), shared=(other_review,))


def test_analyst_digest_is_not_compared_with_the_verifier_digest() -> None:
    owner = verified()
    assert owner.request_sha256 == DIGEST_A
    value = analyze_question(owner, question(), analyst_result(request_sha256="c" * 64))
    assert isinstance(value, AnalyzedQuestion) and value.request_sha256 == "c" * 64


# --- AnalyzedQuestion invariants and recheck_analyzed ---------------------------------------


def analyzed_value() -> AnalyzedQuestion:
    value = analyze_question(
        verified(),
        question(),
        analyst_result(finding_output((C1, "encrypted at rest"), follow_ups=("Which keys?",))),
    )
    assert isinstance(value, AnalyzedQuestion)
    return value


def test_analyzed_question_constructor_invariants() -> None:
    value = analyzed_value()
    finding = value.findings[0]
    assert dataclasses.replace(value) == value
    for change in (
        {"follow_up_questions": ()},
        {"follow_up_questions": (("x" * 501,),)},
        {"follow_up_questions": (("",),)},
        {"follow_up_questions": (("q",) * 6,)},
        {"follow_up_questions": [("q",)]},
        {"findings": (finding.model_copy(update={"finding_id": ANALYST_ID_1}),)},
        {"findings": (finding.model_copy(update={"question_ids": (OTHER_ID,)}),)},
        {"findings": (finding.model_dump(),)},
        {"findings": (finding,) * 21, "follow_up_questions": ((),) * 21},
        {"tenant_id": OTHER_TENANT},
        {"question_id": OTHER_ID},
        {"request_sha256": "B" * 64},
    ):
        with pytest.raises(InvalidProvenanceValueError):
            dataclasses.replace(value, **change)


def test_recheck_analyzed_accepts_the_unaltered_value() -> None:
    value = analyzed_value()
    assert recheck_analyzed(value, verified(), question()) == value


def test_recheck_analyzed_detects_altered_findings() -> None:
    value = analyzed_value()
    finding = value.findings[0]
    altered_status = finding.model_copy(update={"evidence_status": S.MISSING})
    unvalidated = finding.model_copy(
        update={"citations": (cite(C2, "shall encrypt"),), "evidence_status": S.DOCUMENTARY_SUPPORT}
    )
    for findings in ((altered_status,), (unvalidated,)):
        with pytest.raises(InvalidProvenanceInputError):
            recheck_analyzed(dataclasses.replace(value, findings=findings), verified(), question())
    object.__setattr__(
        value, "findings", (finding.model_copy(update={"finding_id": ANALYST_ID_1}),)
    )
    with pytest.raises(InvalidProvenanceInputError):
        recheck_analyzed(value, verified(), question())


@pytest.mark.parametrize(
    "change", [{"tenant_id": OTHER_TENANT}, {"review_id": OTHER_REVIEW}, {"question_id": OTHER_ID}]
)
def test_recheck_analyzed_checks_outer_identity_of_an_empty_value(change: dict[str, Any]) -> None:
    empty = AnalyzedQuestion(
        **{
            "tenant_id": TENANT,
            "review_id": REVIEW,
            "question_id": QUESTION_ID,
            "request_sha256": DIGEST_B,
            "findings": (),
            "follow_up_questions": (),
            **change,
        }
    )
    with pytest.raises(InvalidProvenanceInputError) as raised:
        recheck_analyzed(empty, verified(), question())
    assert raised.value.__cause__ is None and raised.value.__context__ is None


def test_recheck_analyzed_checks_owner_and_question_identity() -> None:
    empty = analyze_question(verified(), question(), analyst_result())
    assert isinstance(empty, AnalyzedQuestion)
    with pytest.raises(InvalidProvenanceInputError):
        recheck_analyzed(empty, verified(), question(OTHER_ID))
    with pytest.raises(InvalidProvenanceInputError):
        recheck_analyzed(empty, shared_owner(), question(OTHER_ID))


def test_recheck_analyzed_with_shared_questions() -> None:
    value = analyze_question(
        verified(),
        question(),
        analyst_result(
            finding_output((C1, "encrypted at rest"), question_ids=(QUESTION_ID, OTHER_ID))
        ),
        shared=(shared_owner(),),
    )
    assert isinstance(value, AnalyzedQuestion)
    assert recheck_analyzed(value, verified(), question(), shared=(shared_owner(),)) == value
    with pytest.raises(InvalidProvenanceInputError):
        recheck_analyzed(value, verified(), question())  # shared question not supplied
    with pytest.raises(InvalidProvenanceInputError):
        recheck_analyzed(
            value, verified(), question(), shared=(shared_owner(V.SUPPORTED, (C1, "Keys")),)
        )


# --- documentary-support rule (P11) -------------------------------------------------------------


def test_documentary_gap_finding() -> None:
    owner = verified()
    finding = documentary_gap_finding(owner, question(documentary=True))
    assert finding == Finding(
        tenant_id=TENANT,
        finding_id=RULE_ID,
        question_ids=(QUESTION_ID,),
        title="Documentary evidence required",
        severity=Severity.MEDIUM,
        statement=(
            "Only vendor statements support this answer; the question requires a contract or "
            "third-party report."
        ),
        evidence_status=S.MISSING,
        citations=owner.verification.citations,
    )
    assert (finding.title, Severity.MEDIUM) == (DOCUMENTARY_GAP_TITLE, DOCUMENTARY_GAP_SEVERITY)
    assert finding.statement == DOCUMENTARY_GAP_STATEMENT


def test_documentary_gap_finding_applies_only_to_vendor_claims_on_required_questions() -> None:
    documentary = verified(V.SUPPORTED, claim("c", (C2, "shall encrypt")))
    assert documentary_gap_finding(documentary, question(documentary=True)) is None
    assert documentary_gap_finding(verified(), question(documentary=False)) is None
    missing = verified(V.INSUFFICIENT_EVIDENCE, claim("c"))
    assert documentary_gap_finding(missing, question(documentary=True)) is None


@pytest.mark.parametrize("documentary", [True, False])
def test_documentary_gap_identity_is_checked_whatever_the_condition(documentary: bool) -> None:
    with pytest.raises(InvalidProvenanceInputError) as raised:
        documentary_gap_finding(verified(), question(OTHER_ID, documentary=documentary))
    assert raised.value.__cause__ is None and raised.value.__context__ is None
    with pytest.raises(InvalidProvenanceInputError):
        documentary_gap_finding("verified", question(documentary=documentary))  # type: ignore[arg-type]


def test_documentary_gap_finding_keeps_the_question_unresolved_in_a_report() -> None:
    owner = verified()
    finding = documentary_gap_finding(owner, question(documentary=True))
    assert finding is not None
    base: dict[str, Any] = {
        "tenant_id": TENANT,
        "title": "Review",
        "questions": (question(documentary=True),),
        "findings": (finding,),
    }
    with pytest.raises(ValueError):
        ReportContent(**base)
    assert ReportContent(**base, unresolved_question_ids=(QUESTION_ID,)).findings == (finding,)


# --- finding IDs and derive_status -------------------------------------------------------------


def test_finding_id_namespace_and_pinned_values() -> None:
    url = "https://evidenceguard.invalid/namespaces/finding-id/v1"
    assert uuid5(NAMESPACE_URL, url) == FINDING_ID_NAMESPACE
    assert UUID("56b13512-9167-5c9e-95c5-c6915da4cba6") == FINDING_ID_NAMESPACE
    assert finding_id(TENANT, REVIEW, QUESTION_ID, FindingKind.ANALYST, 0) == ANALYST_ID_0
    assert finding_id(TENANT, REVIEW, QUESTION_ID, FindingKind.ANALYST, 1) == ANALYST_ID_1
    rule = FindingKind.DOCUMENTARY_SUPPORT_REQUIRED
    assert finding_id(TENANT, REVIEW, QUESTION_ID, rule, 0) == RULE_ID
    assert finding_id(TENANT, REVIEW, QUESTION_ID, FindingKind.ANALYST, 19) == uuid5(
        FINDING_ID_NAMESPACE, f"{TENANT}:{REVIEW}:{QUESTION_ID}:analyst:19"
    )


@pytest.mark.parametrize(
    "args",
    [
        (TENANT, REVIEW, QUESTION_ID, FindingKind.ANALYST, 20),
        (TENANT, REVIEW, QUESTION_ID, FindingKind.ANALYST, -1),
        (TENANT, REVIEW, QUESTION_ID, FindingKind.ANALYST, True),
        (TENANT, REVIEW, QUESTION_ID, FindingKind.DOCUMENTARY_SUPPORT_REQUIRED, 1),
        (TENANT, REVIEW, QUESTION_ID, "analyst", 0),
        (str(TENANT), REVIEW, QUESTION_ID, FindingKind.ANALYST, 0),
        (TENANT, REVIEW, "enc-01", FindingKind.ANALYST, 0),
    ],
)
def test_finding_id_rejects_invalid_arguments(args: tuple[Any, ...]) -> None:
    with pytest.raises(InvalidProvenanceInputError):
        finding_id(*args)


def test_derive_status_inputs() -> None:
    vendor = cite(C1, "encrypted at rest")
    contract = cite(C2, "shall encrypt")
    assert derive_status(V.SUPPORTED, (vendor,)) is S.VENDOR_CLAIM
    assert derive_status(V.SUPPORTED, (vendor, contract)) is S.DOCUMENTARY_SUPPORT
    assert derive_status(V.SUPPORTED, ()) is None
    assert derive_status(V.CONTRADICTED, (vendor, cite(C4, "encrypted at rest"))) is None
    assert derive_status(V.CONTRADICTED, (vendor, contract)) is S.CONFLICTING
    assert derive_status(V.INSUFFICIENT_EVIDENCE, ()) is S.MISSING
    for verdict, citations in (
        ("supported", (vendor,)),
        (V.SUPPORTED, [vendor]),
        (V.SUPPORTED, (vendor.model_dump(),)),
    ):
        with pytest.raises(InvalidProvenanceInputError):
            derive_status(verdict, citations)  # type: ignore[arg-type]


# --- ProvenanceRejection --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "args",
    [
        (R.CHUNK_NOT_RETRIEVED, 9, 7, 80, RejectionStage.VERIFICATION),
        (R.CLAIM_UNCITED, 0, None, 10, RejectionStage.VERIFICATION),
        (R.VERDICT_UNSUPPORTED, None, None, 2, RejectionStage.VERIFICATION),
        (R.RATIONALE_BLANK, None, None, 1, RejectionStage.VERIFICATION),
        (R.CITATION_NOT_VALIDATED, 19, 7, 20, RejectionStage.ANALYSIS),
        (R.FINDING_TEXT_BLANK, 0, None, 1, RejectionStage.ANALYSIS),
    ],
)
def test_rejection_accepts_specified_combinations(args: tuple[Any, ...]) -> None:
    reason, item, citation, count, stage = args
    assert rejection(reason, item, citation, count, stage).reason is reason


@pytest.mark.parametrize(
    "args",
    [
        (R.QUOTE_NOT_FOUND, 0, 0, 1, RejectionStage.ANALYSIS),
        (R.QUOTE_NOT_FOUND, 0, None, 1, RejectionStage.VERIFICATION),
        (R.QUOTE_NOT_FOUND, 10, 0, 1, RejectionStage.VERIFICATION),
        (R.QUOTE_NOT_FOUND, 0, 8, 1, RejectionStage.VERIFICATION),
        (R.QUOTE_NOT_FOUND, 0, 0, 81, RejectionStage.VERIFICATION),
        (R.QUOTE_NOT_FOUND, 0, 0, 0, RejectionStage.VERIFICATION),
        (R.QUOTE_NOT_FOUND, True, 0, 1, RejectionStage.VERIFICATION),
        (R.CLAIM_UNCITED, 0, 0, 1, RejectionStage.VERIFICATION),
        (R.CLAIM_UNCITED, 0, None, 11, RejectionStage.VERIFICATION),
        (R.VERDICT_UNSUPPORTED, 0, None, 1, RejectionStage.VERIFICATION),
        (R.VERDICT_UNSUPPORTED, None, None, 3, RejectionStage.VERIFICATION),
        (R.RATIONALE_BLANK, None, None, 2, RejectionStage.VERIFICATION),
        (R.MIXED_VERDICTS, 0, 0, 1, RejectionStage.ANALYSIS),
        (R.CITATION_NOT_SHARED, 0, None, 1, RejectionStage.ANALYSIS),
        (R.FOREIGN_QUESTION, 20, None, 1, RejectionStage.ANALYSIS),
        (R.FOREIGN_QUESTION, 0, None, 21, RejectionStage.ANALYSIS),
        (R.FOREIGN_QUESTION, 0, None, 1, RejectionStage.VERIFICATION),
        ("foreign_question", 0, None, 1, RejectionStage.ANALYSIS),
    ],
)
def test_rejection_rejects_other_combinations(args: tuple[Any, ...]) -> None:
    reason, item, citation, count, stage = args
    with pytest.raises(InvalidProvenanceValueError):
        rejection(reason, item, citation, count, stage)
    with pytest.raises(InvalidProvenanceValueError):
        ProvenanceRejection(
            stage=RejectionStage.VERIFICATION,
            question_id="bad",
            reason=R.RATIONALE_BLANK,
            item_index=None,
            citation_index=None,
            rejected_count=1,
        )


# --- privacy, logging and process control ---------------------------------------------------


def test_no_content_in_representations_rejections_or_logs(caplog: pytest.LogCaptureFixture) -> None:
    body = f"{CANARY} secret passage. Keys rotate yearly."
    evidence = trusted(C1, texts={C1: body})
    with caplog.at_level("DEBUG"):
        value = verify_question(
            evidence,
            verifier_result(
                V.SUPPORTED, claim(f"claim {CANARY}", (C1, f"{CANARY} secret")), rationale=CANARY
            ),
        )
        rejected = verify_question(
            evidence,
            verifier_result(V.SUPPORTED, claim(CANARY, (C1, f"{CANARY} absent")), rationale=CANARY),
        )
        assert isinstance(value, VerifiedQuestion)
        analyzed = analyze_question(
            value,
            question(),
            analyst_result(
                finding_output(
                    (C1, f"{CANARY} secret"), title=CANARY, statement=CANARY, follow_ups=(CANARY,)
                )
            ),
        )
        analysis_rejected = analyze_question(
            value, question(), analyst_result(finding_output((C1, CANARY), title=CANARY))
        )
    shown = [
        value,
        value.claims[0],
        value.provenance[0],
        value.provenance[0].match,
        evidence,
        rejected,
        analyzed,
        analysis_rejected,
    ]
    for item in shown:
        assert CANARY not in repr(item) and CANARY not in str(item)
    assert caplog.records == []
    assert value.verification.citations[0].quote == f"{CANARY} secret"  # deliberate access


def test_errors_carry_only_their_codes() -> None:
    errors: list[BaseException] = []
    for call in (
        lambda: verify_question(trusted(), CANARY),  # type: ignore[arg-type]
        lambda: ValidatedClaim(text=CANARY, citation_indexes=(CANARY,)),  # type: ignore[arg-type]
        lambda: documentary_gap_finding(verified(), question(OTHER_ID)),
    ):
        with pytest.raises(provenance.ProvenanceError) as raised:
            call()
        errors.append(raised.value)
    assert [str(e) for e in errors] == [
        "invalid_provenance_input",
        "invalid_provenance_value",
        "invalid_provenance_input",
    ]
    for error in errors:
        assert error.__cause__ is None and error.__context__ is None
        assert CANARY not in repr(error)


def test_nested_validation_failure_becomes_a_fixed_error(monkeypatch: pytest.MonkeyPatch) -> None:
    value = verified()

    def broken(self: Verification, **kwargs: Any) -> Verification:
        raise RuntimeError(CANARY)

    monkeypatch.setattr(Verification, "model_copy", broken)
    with pytest.raises(InvalidProvenanceValueError) as raised:
        dataclasses.replace(value)
    assert CANARY not in str(raised.value) and raised.value.__context__ is None
    with pytest.raises(InvalidProvenanceInputError):
        recheck_verified(value, trusted())


@pytest.mark.parametrize("control", [KeyboardInterrupt(), SystemExit(2), GeneratorExit()])
def test_process_control_propagates_from_nested_validation(
    monkeypatch: pytest.MonkeyPatch, control: BaseException
) -> None:
    value = verified()

    def interrupt(self: Any, **kwargs: Any) -> Any:
        raise control

    monkeypatch.setattr(Verification, "model_copy", interrupt)
    for call in (
        lambda: dataclasses.replace(value),
        lambda: recheck_verified(value, trusted()),
        lambda: analyze_question(value, question(), analyst_result()),
        lambda: documentary_gap_finding(value, question()),
    ):
        with pytest.raises(BaseException) as raised:
            call()
        assert raised.value is control


@pytest.mark.parametrize("control", [KeyboardInterrupt(), SystemExit(2), GeneratorExit()])
def test_process_control_propagates_from_traversal(
    monkeypatch: pytest.MonkeyPatch, control: BaseException
) -> None:
    evidence = trusted()
    call = verifier_result(V.SUPPORTED, claim("c", (C1, "encrypted at rest")))

    def interrupt(self: Any, **kwargs: Any) -> Any:
        raise control

    monkeypatch.setattr(EvidenceQuestion, "model_copy", interrupt)
    with pytest.raises(BaseException) as raised:
        verify_question(evidence, call)
    assert raised.value is control


# --- Prompt 178: full citation values during analysis reload ------------------------------------
#
# Reproductions use only ordinary validated constructors and copies (``Citation.model_copy``,
# ``Finding.model_copy``, ``dataclasses.replace``); no bypass is needed. The owner stays valid.


def escalated(**citation_changes: Any) -> AnalyzedQuestion:
    """The reviewer's reproduction: an analysis citing C1 whose stored citation metadata (and,
    where given, status) is changed while chunk and quote stay the same."""
    status = citation_changes.pop("evidence_status", None)
    value = analyzed_value()
    finding = value.findings[0]
    assert finding.evidence_status is S.VENDOR_CLAIM
    changed = finding.citations[0].model_copy(update=citation_changes)
    assert (changed.chunk_id, changed.quote) == (C1, "encrypted at rest")
    update: dict[str, Any] = {"citations": (changed,)}
    if status is not None:
        update["evidence_status"] = status
    return dataclasses.replace(value, findings=(finding.model_copy(update=update),))


@pytest.mark.parametrize(
    "changes",
    [
        {"document_revision_id": REV_B},
        {"source_type": SourceType.CONTRACT, "evidence_status": S.DOCUMENTARY_SUPPORT},
        {
            "document_revision_id": REV_B,
            "source_type": SourceType.CONTRACT,
            "evidence_status": S.DOCUMENTARY_SUPPORT,
        },
    ],
    ids=["revision", "source-type-and-status", "revision-source-type-and-status"],
)
def test_analysis_reload_rejects_changed_citation_metadata(changes: dict[str, Any]) -> None:
    owner = verified()
    with pytest.raises(InvalidProvenanceInputError) as raised:
        recheck_analyzed(escalated(**changes), owner, question())
    assert str(raised.value) == "invalid_provenance_input"
    assert raised.value.__cause__ is None and raised.value.__context__ is None


def test_analysis_reload_accepts_the_unaltered_value() -> None:
    value = analyzed_value()
    assert recheck_analyzed(value, verified(), question()) == value


def test_analysis_reload_errors_are_fixed_and_owner_is_unchanged() -> None:
    owner = verified()
    before = dataclasses.replace(owner)
    altered = escalated(
        document_revision_id=REV_B,
        source_type=SourceType.CONTRACT,
        evidence_status=S.DOCUMENTARY_SUPPORT,
    )
    with pytest.raises(InvalidProvenanceInputError) as raised:
        recheck_analyzed(altered, owner, question())
    assert CANARY not in repr(raised.value) and raised.value.__context__ is None
    assert owner == before
    assert owner.verification.citations == (cite(C1, "encrypted at rest"),)
    assert recheck_verified(owner, trusted()) == owner


def multi_question_analysis(shared: VerifiedQuestion) -> AnalyzedQuestion | ProvenanceRejection:
    return analyze_question(
        verified(),
        question(),
        analyst_result(
            finding_output((C1, "encrypted at rest"), question_ids=(QUESTION_ID, OTHER_ID))
        ),
        shared=(shared,),
    )


def inconsistent_shared() -> VerifiedQuestion:
    """A shared Verification citing the same chunk and quote with other metadata."""
    value = rebuild(shared_owner(), document_revision_id=REV_B)
    citation = value.verification.citations[0]
    assert (citation.chunk_id, citation.quote) == (C1, "encrypted at rest")
    assert citation.document_revision_id == REV_B
    return value


def test_shared_citations_pass_analysis_and_reload() -> None:
    value = multi_question_analysis(shared_owner())
    assert isinstance(value, AnalyzedQuestion)
    assert value.findings[0].citations == (cite(C1, "encrypted at rest"),)
    assert recheck_analyzed(value, verified(), question(), shared=(shared_owner(),)) == value


def test_shared_metadata_inconsistency_is_not_shared_in_analysis() -> None:
    assert multi_question_analysis(inconsistent_shared()) == analysis_rejection(
        R.CITATION_NOT_SHARED, 0, 0
    )


def test_shared_metadata_inconsistency_fails_reload() -> None:
    value = multi_question_analysis(shared_owner())
    assert isinstance(value, AnalyzedQuestion)
    with pytest.raises(InvalidProvenanceInputError) as raised:
        recheck_analyzed(value, verified(), question(), shared=(inconsistent_shared(),))
    assert raised.value.__cause__ is None and raised.value.__context__ is None
