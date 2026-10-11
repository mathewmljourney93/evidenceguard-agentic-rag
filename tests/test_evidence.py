from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from evidenceguard_domain.evidence import (
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


def _citation(
    tenant_id: UUID,
    source_type: SourceType = SourceType.VENDOR_STATEMENT,
    quote: str = "Data is encrypted in transit using TLS 1.2.",
) -> Citation:
    return Citation(
        tenant_id=tenant_id,
        document_revision_id=uuid4(),
        chunk_id=uuid4(),
        source_type=source_type,
        quote=quote,
    )


def _verification(
    tenant_id: UUID,
    verdict: Verdict,
    status: EvidenceStatus,
    citations: tuple[Citation, ...],
) -> Verification:
    return Verification(
        tenant_id=tenant_id,
        question_id="ENC-01",
        verdict=verdict,
        evidence_status=status,
        citations=citations,
        rationale="Synthetic rationale.",
    )


# --- valid verdict/status combinations -------------------------------------------------


def test_supported_vendor_claim(tenant_a: UUID) -> None:
    result = _verification(
        tenant_a, Verdict.SUPPORTED, EvidenceStatus.VENDOR_CLAIM, (_citation(tenant_a),)
    )

    assert result.evidence_status is EvidenceStatus.VENDOR_CLAIM


def test_supported_documentary_support_needs_a_non_vendor_source(tenant_a: UUID) -> None:
    citations = (_citation(tenant_a), _citation(tenant_a, SourceType.CONTRACT))

    result = _verification(
        tenant_a, Verdict.SUPPORTED, EvidenceStatus.DOCUMENTARY_SUPPORT, citations
    )

    assert {c.source_type for c in result.citations} == {
        SourceType.VENDOR_STATEMENT,
        SourceType.CONTRACT,
    }


def test_contradicted_conflicting_with_two_chunks(tenant_a: UUID) -> None:
    citations = (
        _citation(tenant_a, quote="Retained for ninety (90) days."),
        _citation(tenant_a, SourceType.CONTRACT, quote="Deleted within thirty (30) days."),
    )

    result = _verification(tenant_a, Verdict.CONTRADICTED, EvidenceStatus.CONFLICTING, citations)

    assert len(result.citations) == 2


def test_insufficient_evidence_may_cite_an_incomplete_policy(tenant_a: UUID) -> None:
    partial = _citation(tenant_a, quote="We notify affected customers promptly.")

    result = _verification(
        tenant_a, Verdict.INSUFFICIENT_EVIDENCE, EvidenceStatus.MISSING, (partial,)
    )

    assert result.citations == (partial,)


def test_insufficient_evidence_may_have_no_citations(tenant_a: UUID) -> None:
    result = _verification(tenant_a, Verdict.INSUFFICIENT_EVIDENCE, EvidenceStatus.MISSING, ())

    assert result.citations == ()


# --- invalid combinations and missing citations ------------------------------------------


@pytest.mark.parametrize(
    ("verdict", "status"),
    [
        (Verdict.SUPPORTED, EvidenceStatus.CONFLICTING),
        (Verdict.SUPPORTED, EvidenceStatus.MISSING),
        (Verdict.CONTRADICTED, EvidenceStatus.VENDOR_CLAIM),
        (Verdict.CONTRADICTED, EvidenceStatus.MISSING),
        (Verdict.INSUFFICIENT_EVIDENCE, EvidenceStatus.VENDOR_CLAIM),
        (Verdict.INSUFFICIENT_EVIDENCE, EvidenceStatus.DOCUMENTARY_SUPPORT),
    ],
)
def test_disallowed_verdict_status_pairs_are_rejected(
    tenant_a: UUID, verdict: Verdict, status: EvidenceStatus
) -> None:
    citations = (_citation(tenant_a), _citation(tenant_a, SourceType.CONTRACT))

    with pytest.raises(ValidationError, match="does not allow"):
        _verification(tenant_a, verdict, status, citations)


@pytest.mark.parametrize(
    "status", [EvidenceStatus.VENDOR_CLAIM, EvidenceStatus.DOCUMENTARY_SUPPORT]
)
def test_supported_without_citations_is_rejected(tenant_a: UUID, status: EvidenceStatus) -> None:
    with pytest.raises(ValidationError, match="requires citations"):
        _verification(tenant_a, Verdict.SUPPORTED, status, ())


def test_two_different_quotations_from_one_chunk_can_conflict(tenant_a: UUID) -> None:
    first = _citation(tenant_a, quote="Customer data is deleted within 30 days of termination.")
    second = first.model_copy(update={"quote": "Backups are retained for 180 days."})

    result = _verification(
        tenant_a, Verdict.CONTRADICTED, EvidenceStatus.CONFLICTING, (first, second)
    )

    assert {c.chunk_id for c in result.citations} == {first.chunk_id}
    assert len({c.quote for c in result.citations}) == 2


def test_exact_duplicate_citation_does_not_count_twice(tenant_a: UUID) -> None:
    citation = _citation(tenant_a)

    with pytest.raises(ValidationError):
        _verification(
            tenant_a, Verdict.CONTRADICTED, EvidenceStatus.CONFLICTING, (citation, citation)
        )


def test_same_quotation_from_two_chunks_is_one_quotation(tenant_a: UUID) -> None:
    text = "Data is retained as required."
    citations = (_citation(tenant_a, quote=text), _citation(tenant_a, quote=text))

    with pytest.raises(ValidationError, match="two distinct quotations"):
        _verification(tenant_a, Verdict.CONTRADICTED, EvidenceStatus.CONFLICTING, citations)


def test_contradiction_with_a_single_quotation_is_rejected(tenant_a: UUID) -> None:
    with pytest.raises(ValidationError, match="two distinct quotations"):
        _verification(
            tenant_a, Verdict.CONTRADICTED, EvidenceStatus.CONFLICTING, (_citation(tenant_a),)
        )


def test_vendor_claim_cannot_include_documentary_sources(tenant_a: UUID) -> None:
    citations = (_citation(tenant_a, SourceType.THIRD_PARTY_REPORT),)

    with pytest.raises(ValidationError, match="vendor statements"):
        _verification(tenant_a, Verdict.SUPPORTED, EvidenceStatus.VENDOR_CLAIM, citations)


def test_documentary_support_cannot_rest_on_vendor_statements_alone(tenant_a: UUID) -> None:
    with pytest.raises(ValidationError, match="contract or third_party_report"):
        _verification(
            tenant_a,
            Verdict.SUPPORTED,
            EvidenceStatus.DOCUMENTARY_SUPPORT,
            (_citation(tenant_a),),
        )


def test_duplicate_citations_are_rejected(tenant_a: UUID) -> None:
    citation = _citation(tenant_a)

    with pytest.raises(ValidationError, match="duplicate"):
        _verification(
            tenant_a, Verdict.SUPPORTED, EvidenceStatus.VENDOR_CLAIM, (citation, citation)
        )


# --- citation shape ---------------------------------------------------------------------


@pytest.mark.parametrize("quote", ["", "   "])
def test_citation_quote_must_not_be_blank(tenant_a: UUID, quote: str) -> None:
    with pytest.raises(ValidationError):
        _citation(tenant_a, quote=quote)


def test_citation_authenticity_cannot_be_claimed(tenant_a: UUID) -> None:
    with pytest.raises(ValidationError):
        Citation.model_validate(
            {
                "tenant_id": tenant_a,
                "document_revision_id": uuid4(),
                "chunk_id": uuid4(),
                "source_type": "third_party_report",
                "quote": "SOC 2 Type II report, no exceptions noted.",
                "authenticity": "verified",
            }
        )


def test_unknown_fields_are_rejected(tenant_a: UUID) -> None:
    with pytest.raises(ValidationError):
        Citation.model_validate(
            {
                "tenant_id": tenant_a,
                "document_revision_id": uuid4(),
                "chunk_id": uuid4(),
                "source_type": "vendor_statement",
                "quote": "text",
                "is_verified": True,
            }
        )


@pytest.mark.parametrize("queries", [(), tuple(f"query {i}" for i in range(6))])
def test_question_search_queries_are_bounded(queries: tuple[str, ...]) -> None:
    with pytest.raises(ValidationError):
        EvidenceQuestion(question_id="RET-01", text="Retention?", search_queries=queries)


# --- cross-tenant references ------------------------------------------------------------


def test_verification_rejects_another_tenants_citation(tenant_a: UUID, tenant_b: UUID) -> None:
    with pytest.raises(ValidationError, match="same tenant"):
        _verification(
            tenant_a, Verdict.SUPPORTED, EvidenceStatus.VENDOR_CLAIM, (_citation(tenant_b),)
        )


def test_report_content_rejects_another_tenants_finding(
    content: ReportContent, tenant_b: UUID
) -> None:
    foreign = Finding(
        tenant_id=tenant_b,
        finding_id=uuid4(),
        question_ids=("RET-01",),
        title="Foreign finding",
        severity=Severity.LOW,
        statement="Belongs to tenant B.",
        evidence_status=EvidenceStatus.MISSING,
    )

    with pytest.raises(ValidationError, match="report's tenant"):
        content.model_copy(update={"findings": (*content.findings, foreign)})


# --- findings and report content --------------------------------------------------------


@pytest.mark.parametrize(
    "status",
    [EvidenceStatus.VENDOR_CLAIM, EvidenceStatus.DOCUMENTARY_SUPPORT, EvidenceStatus.CONFLICTING],
)
def test_finding_cannot_assert_support_or_conflict_without_citations(
    tenant_a: UUID, status: EvidenceStatus
) -> None:
    with pytest.raises(ValidationError, match="requires citations"):
        Finding(
            tenant_id=tenant_a,
            finding_id=uuid4(),
            question_ids=("ENC-01",),
            title="Encryption at rest",
            severity=Severity.HIGH,
            statement="Customer data is encrypted at rest.",
            evidence_status=status,
        )


def test_finding_about_missing_evidence_needs_no_citation(tenant_a: UUID) -> None:
    finding = Finding(
        tenant_id=tenant_a,
        finding_id=uuid4(),
        question_ids=("BCP-01",),
        title="No recovery time objective",
        severity=Severity.HIGH,
        statement="No document states a recovery time objective.",
        evidence_status=EvidenceStatus.MISSING,
    )

    assert finding.citations == ()


def test_findings_must_reference_known_questions(content: ReportContent) -> None:
    finding = content.findings[0].model_copy(update={"question_ids": ("ZZZ-99",)})

    with pytest.raises(ValidationError, match="unknown questions"):
        content.model_copy(update={"findings": (finding,)})


def test_unresolved_questions_must_be_known(content: ReportContent) -> None:
    with pytest.raises(ValidationError, match="unknown unresolved"):
        content.model_copy(update={"unresolved_question_ids": ("ZZZ-99",)})


def test_question_ids_must_be_unique(content: ReportContent) -> None:
    with pytest.raises(ValidationError, match="unique"):
        content.model_copy(update={"questions": (*content.questions, content.questions[0])})


def test_content_collections_are_copied_into_tuples(tenant_a: UUID) -> None:
    questions = [
        EvidenceQuestion(question_id="RET-01", text="Retention?", search_queries=("retention",))
    ]
    report = ReportContent.model_validate(
        {
            "tenant_id": tenant_a,
            "title": "Review",
            "questions": questions,
            "unresolved_question_ids": ["RET-01"],
        }
    )

    questions.append(
        EvidenceQuestion(question_id="ENC-01", text="Encryption?", search_queries=("encryption",))
    )

    assert isinstance(report.questions, tuple)
    assert [q.question_id for q in report.questions] == ["RET-01"]


def test_contracts_are_frozen(content: ReportContent) -> None:
    with pytest.raises(ValidationError):
        content.title = "Changed"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        content.findings[0].statement = "Changed"  # type: ignore[misc]


# --- question coverage ------------------------------------------------------------------


def _question(question_id: str, *, requires_documentary_support: bool = False) -> EvidenceQuestion:
    return EvidenceQuestion(
        question_id=question_id,
        text=f"Question {question_id}?",
        search_queries=(question_id.lower(),),
        requires_documentary_support=requires_documentary_support,
    )


def _finding(
    tenant_id: UUID, question_id: str, status: EvidenceStatus, *citations: Citation
) -> Finding:
    return Finding(
        tenant_id=tenant_id,
        finding_id=uuid4(),
        question_ids=(question_id,),
        title=f"Finding for {question_id}",
        severity=Severity.MEDIUM,
        statement="Synthetic finding statement.",
        evidence_status=status,
        citations=citations,
    )


def _content(
    tenant_id: UUID,
    questions: tuple[EvidenceQuestion, ...],
    findings: tuple[Finding, ...] = (),
    unresolved: tuple[str, ...] = (),
) -> ReportContent:
    return ReportContent(
        tenant_id=tenant_id,
        title="Coverage test",
        questions=questions,
        findings=findings,
        unresolved_question_ids=unresolved,
    )


def test_silently_omitted_question_is_rejected(tenant_a: UUID) -> None:
    resolved = _finding(tenant_a, "RET-01", EvidenceStatus.VENDOR_CLAIM, _citation(tenant_a))

    with pytest.raises(ValidationError, match=r"listed as unresolved: \['BCP-01'\]"):
        _content(tenant_a, (_question("RET-01"), _question("BCP-01")), (resolved,))


def test_missing_finding_does_not_resolve_its_question(tenant_a: UUID) -> None:
    partial = _finding(
        tenant_a,
        "INC-01",
        EvidenceStatus.MISSING,
        _citation(tenant_a, quote="We notify affected customers promptly."),
    )

    with pytest.raises(ValidationError, match="INC-01"):
        _content(tenant_a, (_question("INC-01"),), (partial,))

    report = _content(tenant_a, (_question("INC-01"),), (partial,), unresolved=("INC-01",))
    assert report.findings == (partial,)


def test_vendor_claim_does_not_resolve_a_question_needing_documents(tenant_a: UUID) -> None:
    question = _question("CMP-01", requires_documentary_support=True)
    claim = _finding(tenant_a, "CMP-01", EvidenceStatus.VENDOR_CLAIM, _citation(tenant_a))

    with pytest.raises(ValidationError, match="CMP-01"):
        _content(tenant_a, (question,), (claim,))

    report = _content(tenant_a, (question,), (claim,), unresolved=("CMP-01",))
    assert report.findings[0].evidence_status is EvidenceStatus.VENDOR_CLAIM


def test_documentary_support_resolves_a_question_needing_documents(tenant_a: UUID) -> None:
    question = _question("CMP-01", requires_documentary_support=True)
    documented = _finding(
        tenant_a,
        "CMP-01",
        EvidenceStatus.DOCUMENTARY_SUPPORT,
        _citation(tenant_a, SourceType.THIRD_PARTY_REPORT, quote="SOC 2 Type II report."),
    )

    report = _content(tenant_a, (question,), (documented,))

    assert report.unresolved_question_ids == ()


def test_conflicting_finding_accounts_for_its_question(tenant_a: UUID) -> None:
    conflict = _finding(
        tenant_a,
        "RET-01",
        EvidenceStatus.CONFLICTING,
        _citation(tenant_a, quote="Retained for ninety (90) days."),
        _citation(tenant_a, SourceType.CONTRACT, quote="Deleted within thirty (30) days."),
    )

    report = _content(tenant_a, (_question("RET-01"),), (conflict,))

    assert report.unresolved_question_ids == ()


def test_supported_and_missing_findings_still_require_an_unresolved_entry(
    tenant_a: UUID,
) -> None:
    supported = _finding(tenant_a, "INC-01", EvidenceStatus.VENDOR_CLAIM, _citation(tenant_a))
    missing = _finding(tenant_a, "INC-01", EvidenceStatus.MISSING)

    with pytest.raises(ValidationError, match=r"listed as unresolved: \['INC-01'\]"):
        _content(tenant_a, (_question("INC-01"),), (supported, missing))


def test_supported_and_missing_findings_with_unresolved_entry_are_accepted(
    tenant_a: UUID,
) -> None:
    supported = _finding(tenant_a, "INC-01", EvidenceStatus.VENDOR_CLAIM, _citation(tenant_a))
    missing = _finding(tenant_a, "INC-01", EvidenceStatus.MISSING)

    report = _content(
        tenant_a, (_question("INC-01"),), (supported, missing), unresolved=("INC-01",)
    )

    assert report.findings == (supported, missing)
    assert report.unresolved_question_ids == ("INC-01",)


def test_missing_finding_leaves_every_referenced_question_unresolved(tenant_a: UUID) -> None:
    questions = (_question("RET-01"), _question("ENC-01"))
    supported = _finding(tenant_a, "RET-01", EvidenceStatus.VENDOR_CLAIM, _citation(tenant_a))
    missing = Finding(
        tenant_id=tenant_a,
        finding_id=uuid4(),
        question_ids=("RET-01", "ENC-01"),
        title="Deletion and encryption details missing",
        severity=Severity.HIGH,
        statement="No document describes deletion of backups or encryption at rest.",
        evidence_status=EvidenceStatus.MISSING,
    )

    with pytest.raises(ValidationError, match=r"listed as unresolved: \['RET-01'\]"):
        _content(tenant_a, questions, (supported, missing), unresolved=("ENC-01",))
    with pytest.raises(ValidationError, match=r"listed as unresolved: \['ENC-01'\]"):
        _content(tenant_a, questions, (supported, missing), unresolved=("RET-01",))

    report = _content(tenant_a, questions, (supported, missing), unresolved=("RET-01", "ENC-01"))
    assert set(report.unresolved_question_ids) == {"RET-01", "ENC-01"}


def test_question_may_have_partial_evidence_and_stay_unresolved(tenant_a: UUID) -> None:
    claim = _finding(tenant_a, "ENC-01", EvidenceStatus.VENDOR_CLAIM, _citation(tenant_a))

    report = _content(tenant_a, (_question("ENC-01"),), (claim,), unresolved=("ENC-01",))

    assert report.unresolved_question_ids == ("ENC-01",)
    assert report.findings == (claim,)
