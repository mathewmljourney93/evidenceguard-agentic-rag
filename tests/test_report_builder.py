"""M5f source-bound construction from committed trusted values, without a database."""

import dataclasses
from typing import TYPE_CHECKING, Any
from uuid import UUID

import pytest

from evidenceguard_agents import report as builder
from evidenceguard_agents.templates import ReviewTemplate, TemplateRef
from evidenceguard_domain import report_content as rc
from evidenceguard_domain.evidence import EvidenceStatus, Finding, Severity, Verdict
from evidenceguard_domain.model_calls import CallOutcome
from evidenceguard_domain.provenance import (
    AnalyzedQuestion,
    FindingKind,
    QuestionEvidence,
    VerifiedQuestion,
    finding_id,
)
from evidenceguard_domain.review_stages import (
    PlannedQuestionSet,
    StageHistory,
    StageKind,
    StageShape,
    TrustedQuestionStages,
    TrustedStages,
    UnresolvedReason,
    dependency_sha256,
    plan_question_sha256,
)
from evidenceguard_domain.reviews import ReviewRequest, TrustedReview, request_sha256

if TYPE_CHECKING:
    import test_review_stage_values as old
    from test_report_content import bypass, configuration, fixed
else:
    from tests import test_review_stage_values as old
    from tests.test_report_content import bypass, configuration, fixed


def world(
    counts: tuple[int, ...] = (1,),
    *,
    documentary: bool = False,
    unresolved_analysis: bool = False,
    unresolved_verification: bool = False,
    text: str | None = None,
    verification_shape: StageShape = StageShape.S1,
    retain_evidence: bool | None = None,
) -> tuple[TrustedReview, ReviewTemplate, PlannedQuestionSet, TrustedStages]:
    # unresolved_verification is the closed U4/U3 world; verification_shape also allows the
    # U1 refusal (one call) and U5 (no call) Verification shapes, each followed by U3 Analysis.
    # retain_evidence defaults to M5e E7: retained for every Verification shape except U4.
    vshape = StageShape.U4 if unresolved_verification else verification_shape
    assert vshape in (StageShape.S1, StageShape.U1, StageShape.U4, StageShape.U5)
    retained = vshape is not StageShape.U4 if retain_evidence is None else retain_evidence
    config = configuration()
    request = ReviewRequest(
        vendor_id=old.VENDOR,
        idempotency_key="report-test",
        identity=old.snapshot().identity,
        config=old.snapshot().config,
        configuration=config,
    )
    review = TrustedReview(
        tenant_id=old.TENANT,
        review_id=old.REVIEW,
        job_id=old.JOB,
        request=request,
        request_sha256=request_sha256(request, tenant_id=old.TENANT),
        snapshot=old.snapshot(),
    )
    entries = []
    for pos, count in enumerate(counts):
        q = old.question(
            question_id=f"QQ-{pos + 1:02}",
            requires_documentary_support=documentary,
            **({} if text is None else {"text": text}),
        )
        original = old.verified()
        owner = VerifiedQuestion(
            tenant_id=old.TENANT,
            review_id=old.REVIEW,
            question_id=q.question_id,
            snapshot_sha256=old.SNAPSHOT_SHA,
            request_sha256="a" * 64,
            match_rules=original.match_rules,
            verification=original.verification.model_copy(update={"question_id": q.question_id}),
            claims=original.claims,
            provenance=original.provenance,
        )
        ev = QuestionEvidence(
            tenant_id=old.TENANT,
            review_id=old.REVIEW,
            snapshot_sha256=old.SNAPSHOT_SHA,
            question=q,
            result=old.result(),
        )
        ehash = old.record(question=q).evidence_sha256
        v = old.stage(
            vshape,
            question_id=q.question_id,
            content=owner if vshape is StageShape.S1 else None,
            evidence_sha256=None if vshape is StageShape.U4 else ehash,
            **({"unresolved_reason": UnresolvedReason.REFUSAL} if vshape is StageShape.U1 else {}),
        )
        dep = dependency_sha256(
            tenant_id=old.TENANT,
            review_id=old.REVIEW,
            question_id=q.question_id,
            question_sha256=plan_question_sha256(q),
            owner_outcome=v.outcome,
            owner_content_sha256=v.content_sha256,
            owner_reason=v.unresolved_reason,
        )
        findings = tuple(
            Finding(
                tenant_id=old.TENANT,
                finding_id=finding_id(
                    old.TENANT, old.REVIEW, q.question_id, FindingKind.ANALYST, n
                ),
                question_ids=(q.question_id,),
                title=f"Finding {n}",
                statement="Statement",
                severity=Severity.LOW,
                evidence_status=EvidenceStatus.VENDOR_CLAIM,
                citations=owner.verification.citations,
            )
            for n in range(count)
        )
        analyzed = AnalyzedQuestion(
            tenant_id=old.TENANT,
            review_id=old.REVIEW,
            question_id=q.question_id,
            request_sha256="b" * 64,
            findings=findings,
            follow_up_questions=tuple(("Follow up?",) for _ in findings),
        )
        ashape = (
            StageShape.U3
            if vshape is not StageShape.S1
            else StageShape.U1
            if unresolved_analysis
            else StageShape.S2
        )
        a = old.stage(
            ashape,
            **({"analysis": True} if ashape is StageShape.U1 else {}),
            question_id=q.question_id,
            content=analyzed if ashape is StageShape.S2 else None,
            dependency_sha256=dep,
            request_sha256=None if ashape is StageShape.U3 else "b" * 64,
            **({"unresolved_reason": UnresolvedReason.REFUSAL} if ashape is StageShape.U1 else {}),
        )

        def history(kind: StageKind, record: Any, question_id: str = q.question_id) -> StageHistory:
            calls = (
                ()
                if record.call_sequence is None
                else (
                    old.call(
                        question_id=question_id,
                        stage=kind,
                        prompt_sha256="1" * 64 if kind is StageKind.VERIFICATION else "2" * 64,
                        request_sha256=record.request_sha256,
                        evidence_sha256=record.evidence_sha256,
                        dependency_sha256=record.dependency_sha256,
                        **old.completion(
                            CallOutcome.REFUSAL
                            if record.shape is StageShape.U1
                            else CallOutcome.COMPLETED
                        ),
                    ),
                )
            )
            return StageHistory(
                tenant_id=old.TENANT,
                review_id=old.REVIEW,
                job_id=old.JOB,
                question_id=question_id,
                stage=kind,
                current_attempt=1,
                calls=calls,
                committed=record,
            )

        entries.append(
            TrustedQuestionStages(
                question=q,
                evidence=ev if retained else None,
                verification=v,
                analysis=a,
                verification_history=history(StageKind.VERIFICATION, v),
                analysis_history=history(StageKind.ANALYSIS, a),
            )
        )
    questions = tuple(e.question for e in entries)
    template = ReviewTemplate(
        ref=TemplateRef(
            template_id=config.template_id,
            version=config.template_version,
            sha256=config.template_sha256,
        ),
        title="Review report",
        questions=questions,
    )
    plan = PlannedQuestionSet(tenant_id=old.TENANT, review_id=old.REVIEW, questions=questions)
    stages = TrustedStages(
        tenant_id=old.TENANT,
        review_id=old.REVIEW,
        job_id=old.JOB,
        job_attempt=1,
        questions=tuple(entries),
    )
    return review, template, plan, stages


def test_success_and_source_recheck() -> None:
    inputs = world((2, 1))
    value = builder.build_report_content(*inputs)
    assert tuple(q.question_id for q in value.questions) == ("QQ-01", "QQ-02")
    assert len(value.content.findings) == 3 and not value.content.unresolved_question_ids
    rebuilt = builder.recheck_report_content(
        value, review=inputs[0], template=inputs[1], planned=inputs[2], stages=inputs[3]
    )
    assert rebuilt == value and rebuilt is not value
    changed = dataclasses.replace(
        value, content=value.content.model_copy(update={"title": "Another title"})
    )
    with pytest.raises(rc.ReportBindingMismatchError) as caught:
        builder.recheck_report_content(
            changed, review=inputs[0], template=inputs[1], planned=inputs[2], stages=inputs[3]
        )
    fixed(caught.value, rc.ReportBindingMismatchError)


def test_p11_survives_analysis_failure_and_preserves_verification() -> None:
    inputs = world(documentary=True, unresolved_analysis=True)
    value = builder.build_report_content(*inputs)
    v = value.questions[0].verification.value
    assert v is not None and v.verdict is Verdict.SUPPORTED
    assert (
        v.rationale == old.verified().verification.rationale and v.claims == old.verified().claims
    )
    assert v.citations == old.verified().verification.citations
    (f,) = value.content.findings
    assert f.title == "Documentary evidence required" and f.severity is Severity.MEDIUM
    assert f.statement == (
        "Only vendor statements support this answer; "
        "the question requires a contract or third-party report."
    )
    assert f.evidence_status is EvidenceStatus.MISSING and f.citations == v.citations
    assert value.content.unresolved_question_ids == ("QQ-01",)
    assert value.questions[0].findings[0].follow_up_questions == ()
    raw = rc.review_report_bytes(value)
    assert rc.decode_review_report(raw, expected_sha256=rc.review_report_sha256(value)) == value


@pytest.mark.parametrize(
    "flags", [{"unresolved_verification": True}, {"unresolved_analysis": True}, {}]
)
def test_zero_finding_success_or_committed_unresolved(flags: dict[str, bool]) -> None:
    value = builder.build_report_content(
        *world(
            (0,),
            unresolved_analysis=flags.get("unresolved_analysis", False),
            unresolved_verification=flags.get("unresolved_verification", False),
        )
    )
    assert value.content.unresolved_question_ids == ("QQ-01",)
    assert not value.content.findings


@pytest.mark.parametrize("total", [199, 200, 201])
def test_global_bound_without_truncation(total: int) -> None:
    counts = (20,) * 9 + (total - 190,)
    inputs = world(
        counts, documentary=True
    )  # 10 mandatory rules + 180 + remainder Analyst findings
    if total > 200:
        with pytest.raises(rc.ReportLimitExceededError) as caught:
            builder.build_report_content(*inputs)
        fixed(caught.value, rc.ReportLimitExceededError)
    else:
        value = builder.build_report_content(*inputs)
        assert len(value.content.findings) == total


def test_incomplete_is_not_committed_unresolved() -> None:
    r, t, p, s = world(unresolved_verification=True)
    item = s.questions[0]
    vh = dataclasses.replace(item.verification_history, committed=None)
    ah = dataclasses.replace(item.analysis_history, committed=None)
    missing = dataclasses.replace(
        s,
        questions=(
            dataclasses.replace(
                item, verification=None, analysis=None, verification_history=vh, analysis_history=ah
            ),
        ),
    )
    with pytest.raises(rc.IncompleteReportStagesError):
        builder.build_report_content(r, t, p, missing)


@pytest.mark.parametrize("which", [0, 1, 2, 3])
def test_binding_mismatches(which: int) -> None:
    r, t, p, s = world((1, 1))
    if which == 0:
        r = dataclasses.replace(r, review_id=UUID(int=999))
    if which == 1:
        t = dataclasses.replace(t, title="Changed", questions=tuple(reversed(t.questions)))
    if which == 2:
        p = dataclasses.replace(p, questions=tuple(reversed(p.questions)))
    if which == 3:
        s = dataclasses.replace(s, questions=tuple(reversed(s.questions)))
    with pytest.raises(rc.ReportBindingMismatchError):
        builder.build_report_content(r, t, p, s)


def test_nested_bool_plan_and_process_control(monkeypatch: pytest.MonkeyPatch) -> None:
    r, t, p, s = world()
    bad = bypass(s, job_attempt=True)
    with pytest.raises(rc.InvalidReportInputError) as caught:
        builder.build_report_content(r, t, p, bad)
    fixed(caught.value, rc.InvalidReportInputError)
    control = SystemExit()

    def stop(*args: Any, **kwargs: Any) -> Any:
        raise control

    monkeypatch.setattr(builder, "recheck_verified", stop)
    with pytest.raises(SystemExit) as caught_control:
        builder.build_report_content(r, t, p, s)
    assert caught_control.value is control


def test_tampered_citation_metadata_and_binding_references_are_refused() -> None:
    r, t, p, s = world()
    item = s.questions[0]
    a = item.analysis
    assert a is not None and type(a.content) is AnalyzedQuestion
    f = a.content.findings[0]
    changed_citation = f.citations[0].model_copy(update={"document_revision_id": UUID(int=888)})
    changed_finding = f.model_copy(update={"citations": (changed_citation,)})
    changed_analysis = dataclasses.replace(
        a, content=dataclasses.replace(a.content, findings=(changed_finding,))
    )
    ah = dataclasses.replace(item.analysis_history, committed=changed_analysis)
    wrong = dataclasses.replace(
        s, questions=(dataclasses.replace(item, analysis=changed_analysis, analysis_history=ah),)
    )
    with pytest.raises(rc.InvalidReportInputError):
        builder.build_report_content(r, t, p, wrong)
    for field in ["evidence_sha256", "dependency_sha256"]:
        # Rebuild both record and matching history/call so refusal exercises the report's
        # source binding, not an intentionally inconsistent StageHistory fixture.
        target = item.verification if field == "evidence_sha256" else item.analysis
        assert target is not None
        history = item.verification_history if field == "evidence_sha256" else item.analysis_history
        digest_change: dict[str, Any] = {field: "0" * 64}
        bad = dataclasses.replace(target, **digest_change)
        history = dataclasses.replace(
            history,
            committed=bad,
            calls=tuple(dataclasses.replace(c, **digest_change) for c in history.calls),
        )
        change: dict[str, Any] = (
            {"verification": bad, "verification_history": history}
            if field == "evidence_sha256"
            else {"analysis": bad, "analysis_history": history}
        )
        wrong = dataclasses.replace(s, questions=(dataclasses.replace(item, **change),))
        with pytest.raises(rc.InvalidReportInputError):
            builder.build_report_content(r, t, p, wrong)


def test_documentary_rule_identity_collision_is_not_silently_deduplicated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = world(documentary=True)
    analyst = inputs[3].questions[0].analysis
    assert analyst is not None and type(analyst.content) is AnalyzedQuestion
    monkeypatch.setattr(
        builder, "documentary_gap_finding", lambda *args: analyst.content.findings[0]
    )
    with pytest.raises(rc.ReportFindingConflictError) as caught:
        builder.build_report_content(*inputs)
    fixed(caught.value, rc.ReportFindingConflictError)


# --- Prompt 210: retained evidence bound to retrieval k and to the committed Verification state


def with_retrieval_k(review: TrustedReview, k: int) -> TrustedReview:
    """``review`` with ``retrieval_k`` changed, rebuilt through the validating constructors
    with a recomputed tenant-bound request digest (no bypass)."""
    config = dataclasses.replace(review.request.configuration, retrieval_k=k)
    request = dataclasses.replace(review.request, configuration=config)
    return dataclasses.replace(
        review, request=request, request_sha256=request_sha256(request, tenant_id=review.tenant_id)
    )


def refused(
    inputs: tuple[TrustedReview, ReviewTemplate, PlannedQuestionSet, TrustedStages],
    kind: type[rc.ReportContentError] = rc.InvalidReportInputError,
) -> None:
    with pytest.raises(kind) as caught:
        builder.build_report_content(*inputs)
    fixed(caught.value, kind)


UNRESOLVED_WITH_EVIDENCE = [StageShape.U1, StageShape.U5]  # U1: one refusal call; U5: no call


@pytest.mark.parametrize("shape", [StageShape.S1, *UNRESOLVED_WITH_EVIDENCE])
def test_retained_evidence_k_must_equal_configured_retrieval_k(shape: StageShape) -> None:
    r, t, p, s = world(verification_shape=shape)
    evidence = s.questions[0].evidence
    assert evidence is not None and evidence.result.k == r.request.configuration.retrieval_k == 8
    # Control: an identical rebuild with the matching k is accepted and records it.
    same = with_retrieval_k(r, 8)
    assert same == r
    value = builder.build_report_content(same, t, p, s)
    assert value.binding.configuration.retrieval_k == 8
    assert value.questions[0].verification.shape is shape
    changed = with_retrieval_k(r, 1)
    assert changed.request.configuration.retrieval_k == 1
    assert changed.request_sha256 == request_sha256(changed.request, tenant_id=old.TENANT)
    assert changed.request_sha256 != r.request_sha256
    refused((changed, t, p, s))
    # Binding mismatch keeps precedence over the evidence consistency refusal.
    refused(
        (dataclasses.replace(changed, review_id=UUID(int=999)), t, p, s),
        rc.ReportBindingMismatchError,
    )
    # The source-bound recheck repeats the builder, so it refuses the inconsistent sources.
    with pytest.raises(rc.InvalidReportInputError) as caught:
        builder.recheck_report_content(value, review=changed, template=t, planned=p, stages=s)
    fixed(caught.value, rc.InvalidReportInputError)


def test_closed_u4_must_not_retain_evidence() -> None:
    r, t, p, s = world(unresolved_verification=True)
    assert s.questions[0].evidence is None
    value = builder.build_report_content(r, t, p, s)  # control: valid U4/U3 without evidence
    assert (value.questions[0].verification.shape, value.questions[0].analysis.shape) == (
        StageShape.U4,
        StageShape.U3,
    )
    assert value.questions[0].verification.evidence_sha256 is None
    assert value.content.unresolved_question_ids == ("QQ-01",)
    attached = world(unresolved_verification=True, retain_evidence=True)
    item = attached[3].questions[0]
    assert item.evidence is not None and item.verification is not None
    assert item.verification.shape is StageShape.U4 and not item.verification_history.calls
    refused(attached)
    with pytest.raises(rc.InvalidReportInputError) as caught:
        builder.recheck_report_content(value, review=r, template=t, planned=p, stages=attached[3])
    fixed(caught.value, rc.InvalidReportInputError)


@pytest.mark.parametrize("shape", [StageShape.S1, *UNRESOLVED_WITH_EVIDENCE])
def test_non_u4_verification_requires_retained_evidence(shape: StageShape) -> None:
    inputs = world(verification_shape=shape)
    value = builder.build_report_content(*inputs)  # control: retained evidence is accepted
    stage = value.questions[0].verification
    item = inputs[3].questions[0]
    assert item.verification is not None and stage.shape is shape
    assert stage.evidence_sha256 == item.verification.evidence_sha256 is not None
    assert len(item.verification_history.calls) == (0 if shape is StageShape.U5 else 1)
    if shape is not StageShape.S1:
        assert stage.value is None and value.questions[0].analysis.shape is StageShape.U3
        assert value.content.unresolved_question_ids == ("QQ-01",)
        assert not value.content.findings
    missing = world(verification_shape=shape, retain_evidence=False)
    # The histories still match the committed records; only the retained evidence is absent.
    m = missing[3].questions[0]
    assert m.evidence is None and m.verification == item.verification
    assert m.verification_history == item.verification_history
    refused(missing)
    with pytest.raises(rc.InvalidReportInputError) as caught:
        builder.recheck_report_content(
            value, review=inputs[0], template=inputs[1], planned=inputs[2], stages=missing[3]
        )
    fixed(caught.value, rc.InvalidReportInputError)


def test_unresolved_evidence_digest_must_match_the_retained_evidence() -> None:
    r, t, p, s = world(verification_shape=StageShape.U5)  # no-call unresolved Verification
    item = s.questions[0]
    assert item.verification is not None and not item.verification_history.calls
    bad = dataclasses.replace(item.verification, evidence_sha256="0" * 64)
    history = dataclasses.replace(item.verification_history, committed=bad)
    dependency = dependency_sha256(
        tenant_id=old.TENANT,
        review_id=old.REVIEW,
        question_id=item.question.question_id,
        question_sha256=plan_question_sha256(item.question),
        owner_outcome=bad.outcome,
        owner_content_sha256=bad.content_sha256,
        owner_reason=bad.unresolved_reason,
    )
    assert item.analysis is not None and item.analysis.dependency_sha256 == dependency
    wrong = dataclasses.replace(
        s, questions=(dataclasses.replace(item, verification=bad, verification_history=history),)
    )
    refused((r, t, p, wrong))


def test_incomplete_stages_precede_evidence_consistency() -> None:
    r, t, p, s = world()
    item = s.questions[0]
    # Evidence is recorded before the first Verification reservation (E1), so retained
    # evidence with no committed stages is a valid incomplete state.
    vh = dataclasses.replace(item.verification_history, calls=(), committed=None)
    ah = dataclasses.replace(item.analysis_history, calls=(), committed=None)
    pending = dataclasses.replace(
        s,
        questions=(
            dataclasses.replace(
                item, verification=None, analysis=None, verification_history=vh, analysis_history=ah
            ),
        ),
    )
    assert pending.questions[0].evidence is not None
    refused((r, t, p, pending), rc.IncompleteReportStagesError)
    refused((with_retrieval_k(r, 1), t, p, pending), rc.IncompleteReportStagesError)


def test_evidence_state_refusals_are_quiet_and_keep_process_control(
    monkeypatch: pytest.MonkeyPatch,
    recwarn: pytest.WarningsRecorder,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for inputs in (
        world(unresolved_verification=True, retain_evidence=True),
        world(verification_shape=StageShape.U1, retain_evidence=False),
    ):
        refused(inputs)
    r, t, p, s = world(verification_shape=StageShape.U1)
    refused((with_retrieval_k(r, 1), t, p, s))
    assert not recwarn.list and not caplog.records
    assert capsys.readouterr() == ("", "")
    control = KeyboardInterrupt()

    def stop(*args: Any, **kwargs: Any) -> Any:
        raise control

    # The shared retained-evidence check runs for unresolved Verification too.
    monkeypatch.setattr(builder, "EvidenceRecord", stop)
    with pytest.raises(KeyboardInterrupt) as caught:
        builder.build_report_content(r, t, p, s)
    assert caught.value is control
