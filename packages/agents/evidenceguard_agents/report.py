"""Pure M5f construction/source recheck and the pinned JSON-literal Markdown renderer.

No artifact loader, provider, database, clock, randomness or runtime wiring (ADR-0024).
"""

from __future__ import annotations

import dataclasses
import json
from enum import Enum
from typing import Any
from uuid import UUID

from evidenceguard_agents.templates import ReviewTemplate
from evidenceguard_domain.evidence import Citation, Finding, ReportContent
from evidenceguard_domain.provenance import (
    AnalyzedQuestion,
    FindingKind,
    VerifiedQuestion,
    documentary_gap_finding,
    recheck_analyzed,
    recheck_verified,
)
from evidenceguard_domain.report_content import (
    MAX_MARKDOWN_BYTES,
    RENDERER,
    IncompleteReportStagesError,
    InvalidReportInputError,
    ReportBinding,
    ReportBindingMismatchError,
    ReportFindingConflictError,
    ReportFindingRef,
    ReportLimitExceededError,
    ReportMode,
    ReportQuestion,
    ReportRenderError,
    ReportRenderLimitError,
    ReportStage,
    ReportVerification,
    ReviewReportContent,
    _fail,
    _preflight,
    _require,
    _run,
    revalidate_review_report,
    review_report_bytes,
    review_report_sha256,
    unresolved_causes,
)
from evidenceguard_domain.review_stages import (
    EvidenceRecord,
    PlannedQuestionSet,
    StageRecord,
    StageShape,
    TrustedStages,
    dependency_sha256,
    plan_question_sha256,
)
from evidenceguard_domain.reviews import TrustedReview

CONTRACT_STAMP = "NOT a quality measurement of Claude or semantic retrieval"


def _rebuilt[T](value: T, kind: type[T]) -> T:
    _preflight(value, kind)
    checked = kind(**{f.name: getattr(value, f.name) for f in dataclasses.fields(value) if f.init})  # type: ignore[arg-type]
    _require(checked == value)
    return checked


def _stage(record: StageRecord) -> ReportStage:
    v = record.content
    value = None
    if type(v) is VerifiedQuestion:
        value = ReportVerification(
            verdict=v.verification.verdict,
            evidence_status=v.verification.evidence_status,
            rationale=v.verification.rationale,
            citations=v.verification.citations,
            claims=v.claims,
        )
    return ReportStage(
        shape=record.shape,
        outcome=record.outcome,
        unresolved_reason=record.unresolved_reason,
        request_sha256=record.request_sha256,
        content_sha256=record.content_sha256,
        evidence_sha256=record.evidence_sha256,
        dependency_sha256=record.dependency_sha256,
        value=value,
    )


def build_report_content(
    review: TrustedReview,
    template: ReviewTemplate,
    planned: PlannedQuestionSet,
    stages: TrustedStages,
    *,
    mode: ReportMode = ReportMode.CONTRACT,
) -> ReviewReportContent:
    def build() -> ReviewReportContent:
        # Exact-field preflight precedes constructors, dumps, normalization and comparisons.
        _preflight(mode, ReportMode)
        r = _rebuilt(review, TrustedReview)
        t = _rebuilt(template, ReviewTemplate)
        p = _rebuilt(planned, PlannedQuestionSet)
        s = _rebuilt(stages, TrustedStages)
        config = r.request.configuration
        if not (
            r.tenant_id == p.tenant_id == s.tenant_id
            and r.review_id == p.review_id == s.review_id
            and r.job_id == s.job_id
            and (t.ref.template_id, t.ref.version, t.ref.sha256)
            == (config.template_id, config.template_version, config.template_sha256)
            and t.questions == p.questions == tuple(i.question for i in s.questions)
        ):
            _fail(ReportBindingMismatchError)
        if any(i.verification is None or i.analysis is None for i in s.questions):
            _fail(IncompleteReportStagesError)
        # Finish all stage/owner checks before finding-conflict/limit checks.
        owners: list[VerifiedQuestion | None] = []
        analyses: list[AnalyzedQuestion | None] = []
        for item in s.questions:
            assert item.verification is not None and item.analysis is not None
            v_record, a_record = item.verification, item.analysis
            _require(
                a_record.dependency_sha256
                == dependency_sha256(
                    tenant_id=r.tenant_id,
                    review_id=r.review_id,
                    question_id=item.question.question_id,
                    question_sha256=plan_question_sha256(item.question),
                    owner_outcome=v_record.outcome,
                    owner_content_sha256=v_record.content_sha256,
                    owner_reason=v_record.unresolved_reason,
                )
            )
            _require((v_record.content is None) == (a_record.shape is StageShape.U3))
            # M5e E7 (clarification B) for every committed Verification shape, successful or
            # unresolved: closed U4 discarded its evidence bytes, so none may be retained (and
            # none is inferred); every other shape requires retained evidence bound to it.
            evidence = item.evidence
            if v_record.shape is StageShape.U4:
                _require(evidence is None)
            else:
                _require(evidence is not None)
                assert evidence is not None
                _require(evidence.snapshot_sha256 == r.snapshot.sha256)
                _require(evidence.result.k == config.retrieval_k)
                _require(
                    v_record.evidence_sha256
                    == EvidenceRecord(
                        tenant_id=r.tenant_id,
                        review_id=r.review_id,
                        question=item.question,
                        result=evidence.result,
                    ).evidence_sha256
                )
            for history, prompt in (
                (item.verification_history, config.verifier_prompt),
                (item.analysis_history, config.analyst_prompt),
            ):
                for call in history.calls:
                    _require(
                        (
                            call.prompt_sha256,
                            call.model_requested,
                            call.max_output_tokens,
                            call.timeout_ms,
                        )
                        == (
                            prompt.sha256,
                            config.model_id,
                            config.max_output_tokens,
                            config.timeout_ms,
                        )
                    )
            owner = item.verification.content
            analyzed = item.analysis.content
            if type(owner) is VerifiedQuestion:
                _require(item.evidence is not None)
                owner = recheck_verified(owner, item.evidence)  # type: ignore[arg-type]
                _require(owner.snapshot_sha256 == r.snapshot.sha256)
                _require(item.verification.request_sha256 == owner.request_sha256)
                if type(analyzed) is AnalyzedQuestion:
                    analyzed = recheck_analyzed(analyzed, owner, item.question, shared=())
                    _require(
                        all(
                            f.question_ids == (item.question.question_id,)
                            for f in analyzed.findings
                        )
                    )
                    _require(item.analysis.request_sha256 == analyzed.request_sha256)
            else:
                _require(owner is None and analyzed is None)
            _require(owner is None or type(owner) is VerifiedQuestion)
            assert owner is None or isinstance(owner, VerifiedQuestion)
            owners.append(owner)
            _require(analyzed is None or type(analyzed) is AnalyzedQuestion)
            assert analyzed is None or isinstance(analyzed, AnalyzedQuestion)
            analyses.append(analyzed)
        findings: list[Finding] = []
        questions: list[ReportQuestion] = []
        seen: set[UUID] = set()
        unresolved: list[str] = []
        for position, (item, owner, analyzed) in enumerate(
            zip(s.questions, owners, analyses, strict=True)
        ):
            assert item.verification is not None and item.analysis is not None
            owned: list[Finding] = []
            refs: list[ReportFindingRef] = []
            rule = None if owner is None else documentary_gap_finding(owner, item.question)
            if rule is not None:
                owned.append(rule)
                refs.append(
                    ReportFindingRef(
                        kind=FindingKind.DOCUMENTARY_SUPPORT_REQUIRED,
                        index=0,
                        finding_id=rule.finding_id,
                        follow_up_questions=(),
                    )
                )
            if analyzed is not None:
                for index, (finding, follow) in enumerate(
                    zip(analyzed.findings, analyzed.follow_up_questions, strict=True)
                ):
                    owned.append(finding)
                    refs.append(
                        ReportFindingRef(
                            kind=FindingKind.ANALYST,
                            index=index,
                            finding_id=finding.finding_id,
                            follow_up_questions=follow,
                        )
                    )
            for finding in owned:
                if finding.finding_id in seen:
                    _fail(ReportFindingConflictError)
                seen.add(finding.finding_id)
            question = ReportQuestion(
                question_id=item.question.question_id,
                position=position,
                plan_question_sha256=plan_question_sha256(item.question),
                verification=_stage(item.verification),
                analysis=_stage(item.analysis),
                findings=tuple(refs),
            )
            if unresolved_causes(item.question, question, tuple(owned)):
                unresolved.append(item.question.question_id)
            questions.append(question)
            findings.extend(owned)
        if len(findings) > 200:
            _fail(ReportLimitExceededError)
        content = ReportContent(
            tenant_id=r.tenant_id,
            title=t.title,
            questions=t.questions,
            findings=tuple(findings),
            unresolved_question_ids=tuple(unresolved),
        )
        return ReviewReportContent(
            binding=ReportBinding(
                tenant_id=r.tenant_id,
                review_id=r.review_id,
                vendor_id=r.request.vendor_id,
                job_id=r.job_id,
                review_request_sha256=r.request_sha256,
                snapshot_sha256=r.snapshot.sha256,
                configuration=config,
            ),
            mode=mode,
            content=content,
            questions=tuple(questions),
        )

    return _run(build, InvalidReportInputError)


def recheck_report_content(
    content: ReviewReportContent,
    *,
    review: TrustedReview,
    template: ReviewTemplate,
    planned: PlannedQuestionSet,
    stages: TrustedStages,
) -> ReviewReportContent:
    checked = revalidate_review_report(content)
    expected = build_report_content(review, template, planned, stages, mode=checked.mode)

    def check() -> ReviewReportContent:
        if review_report_bytes(checked) != review_report_bytes(expected):
            _fail(ReportBindingMismatchError)
        return expected

    return _run(check, InvalidReportInputError)


def render_report_markdown(content: ReviewReportContent) -> str:
    checked = revalidate_review_report(content)

    def render() -> str:
        lines: list[str] = []
        size = 0

        def emit(*values: str) -> None:
            nonlocal size
            for value in values:
                size += len(value) + 1  # ASCII only; conservative final blank-line accounting.
                if size - 1 > MAX_MARKDOWN_BYTES:
                    _fail(ReportRenderLimitError)
                lines.append(value)

        def heading(value: str) -> None:
            emit(value, "")

        def field(label: str, value: Any) -> None:
            if isinstance(value, Enum):
                value = value.value
            elif type(value) is UUID:
                value = str(value)
            literal = json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
            for char, escape in (("<", r"\u003c"), (">", r"\u003e"), ("&", r"\u0026")):
                literal = literal.replace(char, escape)
            emit(label + ":", "", "    " + literal, "")

        def citation(c: Citation) -> None:
            for label, value in (
                ("Tenant ID", c.tenant_id),
                ("Document revision ID", c.document_revision_id),
                ("Chunk ID", c.chunk_id),
                ("Source type", c.source_type),
                ("Authenticity", c.authenticity),
                ("Accepted quote (JSON literal; decode once for original text)", c.quote),
            ):
                field(label, value)

        def stage(s: ReportStage) -> None:
            for label, value in (
                ("Shape", s.shape),
                ("Outcome", s.outcome),
                ("Unresolved reason", s.unresolved_reason),
                ("Request SHA-256", s.request_sha256),
                ("Content SHA-256", s.content_sha256),
                ("Evidence SHA-256", s.evidence_sha256),
                ("Dependency SHA-256", s.dependency_sha256),
            ):
                field(label, value)

        b, config = checked.binding, checked.binding.configuration
        heading("# EvidenceGuard review")
        heading("## Contract and binding")
        for label, value in (
            ("Contract mode stamp", CONTRACT_STAMP),
            ("Mode", checked.mode),
            ("Renderer", RENDERER),
            ("Wrapper SHA-256", review_report_sha256(checked)),
            ("Legacy SHA-256", checked.legacy_sha256),
            ("Tenant ID", b.tenant_id),
            ("Review ID", b.review_id),
            ("Vendor ID", b.vendor_id),
            ("Job ID", b.job_id),
            ("Review request SHA-256", b.review_request_sha256),
            ("Snapshot SHA-256", b.snapshot_sha256),
            ("Configuration SHA-256", b.configuration_sha256),
            ("Template ID", config.template_id),
            ("Template version", config.template_version),
            ("Template SHA-256", config.template_sha256),
            ("Verifier prompt ID", config.verifier_prompt.prompt_id),
            ("Verifier prompt version", config.verifier_prompt.version),
            ("Verifier prompt SHA-256", config.verifier_prompt.sha256),
            ("Analyst prompt ID", config.analyst_prompt.prompt_id),
            ("Analyst prompt version", config.analyst_prompt.version),
            ("Analyst prompt SHA-256", config.analyst_prompt.sha256),
            ("Model ID", config.model_id),
            ("Max output tokens", config.max_output_tokens),
            ("Timeout ms", config.timeout_ms),
            ("Retrieval k", config.retrieval_k),
            ("Report title", checked.content.title),
        ):
            field(label, value)
        heading("## Questions")
        field("Count", len(checked.questions))
        by_id = {f.finding_id: f for f in checked.content.findings}
        for index, (question, item) in enumerate(
            zip(checked.content.questions, checked.questions, strict=True), 1
        ):
            heading(f"### Question {index}")
            field("Question ID", question.question_id)
            field("Question text", question.text)
            field("Requires documentary support", question.requires_documentary_support)
            field("Plan question SHA-256", item.plan_question_sha256)
            field("Search query count", len(question.search_queries))
            for n, query in enumerate(question.search_queries, 1):
                field(f"Search query {n}", query)
            heading("#### Verification")
            stage(item.verification)
            v = item.verification.value
            if v is not None:
                field("Verdict", v.verdict)
                field("Evidence status", v.evidence_status)
                field("Rationale", v.rationale)
                field("Citation count", len(v.citations))
                for n, c in enumerate(v.citations, 1):
                    heading(f"##### Verification citation {n}")
                    citation(c)
                field("Claim count", len(v.claims))
                for n, claim in enumerate(v.claims, 1):
                    heading(f"##### Claim {n}")
                    field("Text", claim.text)
                    field("Citation index count", len(claim.citation_indexes))
                    for k, ci in enumerate(claim.citation_indexes, 1):
                        field(f"Citation index {k}", ci)
            heading("#### Analysis")
            stage(item.analysis)
            owned = tuple(by_id[r.finding_id] for r in item.findings)
            causes = unresolved_causes(question, item, owned)
            field("Report unresolved", bool(causes))
            field("Unresolved cause count", len(causes))
            for n, cause in enumerate(causes, 1):
                field(f"Unresolved cause {n}", cause)
            heading("#### Findings")
            field("Count", len(item.findings))
            for n, ref in enumerate(item.findings, 1):
                heading(f"##### Finding {n}")
                f = by_id[ref.finding_id]
                for label, value in (
                    ("Kind", ref.kind),
                    ("Index", ref.index),
                    ("Finding ID", f.finding_id),
                    ("Tenant ID", f.tenant_id),
                    ("Question ID", question.question_id),
                    ("Title", f.title),
                    ("Severity", f.severity),
                    ("Evidence status", f.evidence_status),
                    ("Statement", f.statement),
                ):
                    field(label, value)
                field("Citation count", len(f.citations))
                for k, c in enumerate(f.citations, 1):
                    heading(f"###### Finding citation {k}")
                    citation(c)
                field("Follow-up count", len(ref.follow_up_questions))
                for k, follow in enumerate(ref.follow_up_questions, 1):
                    field(f"Follow-up {k}", follow)
        heading("## Unresolved questions")
        field("Count", len(checked.content.unresolved_question_ids))
        for n, qid in enumerate(checked.content.unresolved_question_ids, 1):
            field(f"Question ID {n}", qid)
        return "\n".join(lines[:-1]) + "\n"

    return _run(render, ReportRenderError)
