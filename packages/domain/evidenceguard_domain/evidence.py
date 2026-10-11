"""Typed evidence contracts: questions, citations, verifications, findings and report content.

Verdicts and evidence statuses
------------------------------
The verdict is the Verifier's judgment about a question. The evidence status says what kind
of support the cited passages give. Only these combinations are valid:

=======================  ===========================  =========================================
verdict                  evidence_status              citation rule
=======================  ===========================  =========================================
supported                vendor_claim                 at least one; every one a vendor_statement
supported                documentary_support          at least one; at least one contract or
                                                      third_party_report
contradicted             conflicting                  at least two distinct quotations (the
                                                      same chunk may supply both)
insufficient_evidence    missing                      any number, including none (an incomplete
                                                      policy may still be cited)
=======================  ===========================  =========================================

Findings follow the same status/citation rules without a verdict, so a finding cannot claim
support or conflict unless it carries the citations to back it.

Exact duplicate citations (same chunk and quotation) are always rejected. For ``conflicting``,
quotations with identical text count once even if they come from different chunks, because
identical text cannot express two sides of a disagreement. Counting distinct quotations is a
structural check only: it does not prove that the passages actually contradict each other.

Question coverage
-----------------
Every question in ``ReportContent`` must be accounted for. A question counts as resolved
when at least one finding about it has status ``vendor_claim``, ``documentary_support`` or
``conflicting`` (reporting a conflict accounts for the question). Two exceptions:

- a ``missing`` finding never resolves a question;
- a ``vendor_claim`` finding does not resolve a question with
  ``requires_documentary_support``. The vendor claim can still be shown as a finding.

A question must be listed in ``unresolved_question_ids`` when either:

- no finding resolves it; or
- **any** finding with status ``missing`` references it, even if another finding supports it.
  A missing-evidence finding always leaves every question it names open.

Any other question may still be listed as unresolved, because partial evidence can coexist
with an open question.

What these contracts do not prove
---------------------------------
Validating a ``Citation`` checks only its shape. It does **not** show that the tenant may see
the chunk, that the quote actually occurs in the chunk, that the passage supports any claim,
or that the document is authentic. Retrieval and provenance checks in later milestones cover
authorization and quote membership; semantic support needs model judgment plus human review;
authenticity is ``not_established`` throughout v1.
"""

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Annotated, Self
from uuid import UUID

from pydantic import Field, StringConstraints, model_validator

from evidenceguard_domain._base import DomainModel

QuestionId = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9]{1,9}-[0-9]{2,3}$")]
ShortText = Annotated[str, StringConstraints(min_length=1, max_length=200)]
LongText = Annotated[str, StringConstraints(min_length=1, max_length=2000)]
Quote = Annotated[str, StringConstraints(min_length=1, max_length=1000)]


class Verdict(StrEnum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class EvidenceStatus(StrEnum):
    VENDOR_CLAIM = "vendor_claim"
    DOCUMENTARY_SUPPORT = "documentary_support"
    CONFLICTING = "conflicting"
    MISSING = "missing"


class SourceType(StrEnum):
    """What the uploader says a document is. This is a label, not a verification."""

    VENDOR_STATEMENT = "vendor_statement"
    CONTRACT = "contract"
    THIRD_PARTY_REPORT = "third_party_report"


class Authenticity(StrEnum):
    """v1 has no way to establish authenticity, so only one value exists."""

    NOT_ESTABLISHED = "not_established"


class Severity(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


ALLOWED_STATUSES: Mapping[Verdict, frozenset[EvidenceStatus]] = MappingProxyType(
    {
        Verdict.SUPPORTED: frozenset(
            {EvidenceStatus.VENDOR_CLAIM, EvidenceStatus.DOCUMENTARY_SUPPORT}
        ),
        Verdict.CONTRADICTED: frozenset({EvidenceStatus.CONFLICTING}),
        Verdict.INSUFFICIENT_EVIDENCE: frozenset({EvidenceStatus.MISSING}),
    }
)


class EvidenceQuestion(DomainModel):
    """One bounded question from a review template."""

    question_id: QuestionId
    text: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    search_queries: Annotated[tuple[ShortText, ...], Field(min_length=1, max_length=5)]
    requires_documentary_support: bool = False


class Citation(DomainModel):
    """A quotation from one chunk of one document revision (shape only; see module docstring)."""

    tenant_id: UUID
    document_revision_id: UUID
    chunk_id: UUID
    source_type: SourceType
    quote: Quote
    authenticity: Authenticity = Authenticity.NOT_ESTABLISHED


def _check_citations(
    tenant_id: UUID, status: EvidenceStatus, citations: tuple[Citation, ...]
) -> None:
    """Apply the tenant, duplicate and status/citation rules for verifications and findings."""
    if any(citation.tenant_id != tenant_id for citation in citations):
        raise ValueError("every citation must belong to the same tenant")
    if len({(c.chunk_id, c.quote) for c in citations}) != len(citations):
        raise ValueError("duplicate citations are not allowed")

    if status is EvidenceStatus.MISSING:
        return
    if not citations:
        raise ValueError(f"evidence status {status.value!r} requires citations")
    vendor_only = all(c.source_type is SourceType.VENDOR_STATEMENT for c in citations)
    if status is EvidenceStatus.VENDOR_CLAIM and not vendor_only:
        raise ValueError("vendor_claim citations must all be vendor statements")
    if status is EvidenceStatus.DOCUMENTARY_SUPPORT and vendor_only:
        raise ValueError(
            "documentary_support needs at least one contract or third_party_report citation"
        )
    if status is EvidenceStatus.CONFLICTING and len({c.quote for c in citations}) < 2:
        raise ValueError("conflicting evidence needs at least two distinct quotations")


class Verification(DomainModel):
    """The Verifier's assessment of one question, with the citations it relied on."""

    tenant_id: UUID
    question_id: QuestionId
    verdict: Verdict
    evidence_status: EvidenceStatus
    citations: tuple[Citation, ...] = ()
    rationale: LongText

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.evidence_status not in ALLOWED_STATUSES[self.verdict]:
            raise ValueError(
                f"verdict {self.verdict.value!r} does not allow "
                f"evidence status {self.evidence_status.value!r}"
            )
        _check_citations(self.tenant_id, self.evidence_status, self.citations)
        return self


class Finding(DomainModel):
    """A risk finding about one or more questions."""

    tenant_id: UUID
    finding_id: UUID
    question_ids: Annotated[tuple[QuestionId, ...], Field(min_length=1, max_length=20)]
    title: ShortText
    severity: Severity
    statement: LongText
    evidence_status: EvidenceStatus
    citations: tuple[Citation, ...] = ()

    @model_validator(mode="after")
    def _check(self) -> Self:
        if len(set(self.question_ids)) != len(self.question_ids):
            raise ValueError("a finding must not list the same question twice")
        _check_citations(self.tenant_id, self.evidence_status, self.citations)
        return self


class ReportContent(DomainModel):
    """Everything a report says. This, and only this, is covered by the content hash."""

    tenant_id: UUID
    title: ShortText
    questions: Annotated[tuple[EvidenceQuestion, ...], Field(min_length=1, max_length=100)]
    findings: Annotated[tuple[Finding, ...], Field(max_length=200)] = ()
    unresolved_question_ids: tuple[QuestionId, ...] = ()

    @model_validator(mode="after")
    def _check(self) -> Self:
        known = [q.question_id for q in self.questions]
        if len(set(known)) != len(known):
            raise ValueError("question IDs must be unique")
        if len({f.finding_id for f in self.findings}) != len(self.findings):
            raise ValueError("finding IDs must be unique")
        for finding in self.findings:
            if finding.tenant_id != self.tenant_id:
                raise ValueError("every finding must belong to the report's tenant")
            unknown = set(finding.question_ids) - set(known)
            if unknown:
                raise ValueError(f"finding references unknown questions: {sorted(unknown)}")
        if len(set(self.unresolved_question_ids)) != len(self.unresolved_question_ids):
            raise ValueError("unresolved question IDs must be unique")
        unknown_unresolved = set(self.unresolved_question_ids) - set(known)
        if unknown_unresolved:
            raise ValueError(f"unknown unresolved questions: {sorted(unknown_unresolved)}")

        named_by_missing = {
            question_id
            for f in self.findings
            if f.evidence_status is EvidenceStatus.MISSING
            for question_id in f.question_ids
        }
        unaccounted = [
            q.question_id
            for q in self.questions
            if (not self._is_resolved(q) or q.question_id in named_by_missing)
            and q.question_id not in self.unresolved_question_ids
        ]
        if unaccounted:
            raise ValueError(
                "questions without a resolving finding, or named by a missing-evidence finding, "
                f"must be listed as unresolved: {unaccounted}"
            )
        return self

    def _is_resolved(self, question: EvidenceQuestion) -> bool:
        """Whether any finding resolves the question (see "Question coverage" above)."""
        resolving = {EvidenceStatus.DOCUMENTARY_SUPPORT, EvidenceStatus.CONFLICTING}
        if not question.requires_documentary_support:
            resolving.add(EvidenceStatus.VENDOR_CLAIM)
        return any(
            question.question_id in f.question_ids and f.evidence_status in resolving
            for f in self.findings
        )
