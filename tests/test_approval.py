from collections.abc import Callable
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from evidenceguard_domain.approval import (
    approve,
    create_draft,
    exportable_revision,
    finalize,
    reject,
    revise,
)
from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_domain.errors import (
    ContentHashMismatchError,
    DecisionConflictError,
    InvalidTransitionError,
    NotExportableError,
    PermissionDeniedError,
    StaleRevisionError,
    TenantMismatchError,
)
from evidenceguard_domain.evidence import ReportContent
from evidenceguard_domain.report import ApprovalDecision, Decision, Report, ReportStatus

# --- helpers: act on the report's current revision ------------------------------------


def _approve(report: Report, ctx: ActorContext, now: datetime) -> Report:
    current = report.current_revision
    return approve(
        report,
        ctx,
        revision_number=current.revision_number,
        content_sha256=current.content_sha256,
        now=now,
    )


def _reject(report: Report, ctx: ActorContext, now: datetime) -> Report:
    current = report.current_revision
    return reject(
        report,
        ctx,
        revision_number=current.revision_number,
        content_sha256=current.content_sha256,
        now=now,
        comment="Missing incident-notification timeframe.",
    )


def _finalize(report: Report, ctx: ActorContext, now: datetime) -> Report:
    current = report.current_revision
    return finalize(
        report,
        ctx,
        revision_number=current.revision_number,
        content_sha256=current.content_sha256,
        now=now,
    )


def _revise(report: Report, ctx: ActorContext, now: datetime, title: str) -> Report:
    content = report.current_revision.content.model_copy(update={"title": title})
    return revise(
        report,
        ctx,
        expected_revision_number=report.current_revision.revision_number,
        content=content,
        now=now,
    )


@pytest.fixture
def draft(reviewer: ActorContext, content: ReportContent, now: datetime) -> Report:
    return create_draft(reviewer, report_id=uuid4(), content=content, now=now)


# --- creating drafts --------------------------------------------------------------------


def test_create_draft_starts_at_revision_one(draft: Report, content: ReportContent) -> None:
    assert draft.status is ReportStatus.DRAFT
    assert draft.current_revision.revision_number == 1
    assert draft.current_revision.content == content
    assert draft.effective_approval is None


def test_create_draft_rejects_another_tenants_content(
    other_tenant_approver: ActorContext, content: ReportContent, now: datetime
) -> None:
    with pytest.raises(TenantMismatchError):
        create_draft(other_tenant_approver, report_id=uuid4(), content=content, now=now)


# --- approving the exact current revision -----------------------------------------------


def test_approver_approves_the_exact_current_revision(
    draft: Report, approver: ActorContext, now: datetime
) -> None:
    approved = _approve(draft, approver, now)

    assert approved.status is ReportStatus.APPROVED
    approval = approved.effective_approval
    assert approval is not None
    assert approval.tenant_id == draft.tenant_id
    assert approval.report_id == draft.report_id
    assert approval.revision_number == 1
    assert approval.content_sha256 == draft.current_revision.content_sha256
    assert approval.decided_by == approver.actor_id


def test_approving_a_stale_revision_fails(
    draft: Report, approver: ActorContext, reviewer: ActorContext, now: datetime
) -> None:
    revised = _revise(draft, reviewer, now, "Revised title")

    with pytest.raises(StaleRevisionError):
        approve(
            revised,
            approver,
            revision_number=1,
            content_sha256=draft.current_revision.content_sha256,
            now=now,
        )


def test_approving_with_the_wrong_hash_fails(
    draft: Report, approver: ActorContext, now: datetime
) -> None:
    with pytest.raises(ContentHashMismatchError):
        approve(draft, approver, revision_number=1, content_sha256="f" * 64, now=now)


def test_another_reports_approval_cannot_be_used(
    draft: Report,
    approver: ActorContext,
    reviewer: ActorContext,
    content: ReportContent,
    now: datetime,
) -> None:
    other = _approve(
        create_draft(reviewer, report_id=uuid4(), content=content, now=now), approver, now
    )
    foreign_decision = other.decisions[0]

    with pytest.raises(ValidationError, match="another report"):
        Report(
            tenant_id=draft.tenant_id,
            report_id=draft.report_id,
            status=ReportStatus.APPROVED,
            revisions=draft.revisions,
            decisions=(foreign_decision,),
        )
    with pytest.raises(InvalidTransitionError):
        _finalize(draft, approver, now)


@pytest.mark.parametrize("action", [_approve, _reject, _finalize])
def test_reviewer_cannot_approve_reject_or_finalize(
    draft: Report,
    approver: ActorContext,
    reviewer: ActorContext,
    now: datetime,
    action: Callable[[Report, ActorContext, datetime], Report],
) -> None:
    report = _approve(draft, approver, now) if action is _finalize else draft

    with pytest.raises(PermissionDeniedError):
        action(report, reviewer, now)


def test_other_tenant_cannot_act_on_or_export_the_report(
    draft: Report, approver: ActorContext, other_tenant_approver: ActorContext, now: datetime
) -> None:
    finalized = _finalize(_approve(draft, approver, now), approver, now)

    with pytest.raises(TenantMismatchError):
        _approve(draft, other_tenant_approver, now)
    with pytest.raises(TenantMismatchError):
        _revise(draft, other_tenant_approver, now, "Foreign edit")
    with pytest.raises(TenantMismatchError):
        exportable_revision(finalized, other_tenant_approver)


def test_revision_cannot_carry_another_tenants_content(
    draft: Report, reviewer: ActorContext, tenant_b: UUID, now: datetime
) -> None:
    foreign_content = draft.current_revision.content.model_copy(
        update={
            "tenant_id": tenant_b,
            "findings": (),
            "unresolved_question_ids": ("RET-01", "BCP-01"),
        }
    )

    with pytest.raises(TenantMismatchError):
        revise(draft, reviewer, expected_revision_number=1, content=foreign_content, now=now)


# --- revisions invalidate approval -------------------------------------------------------


def test_revision_after_approval_blocks_finalization_until_reapproved(
    draft: Report, approver: ActorContext, reviewer: ActorContext, now: datetime
) -> None:
    approved = _approve(draft, approver, now)
    revised = _revise(approved, reviewer, now + timedelta(minutes=5), "Revised title")

    assert revised.status is ReportStatus.DRAFT
    assert revised.effective_approval is None
    assert len(revised.decisions) == 1  # the old approval stays in history
    with pytest.raises(InvalidTransitionError):
        _finalize(revised, approver, now)

    reapproved = _approve(revised, approver, now)
    finalized = _finalize(reapproved, approver, now)

    assert finalized.status is ReportStatus.FINALIZED
    assert finalized.finalization is not None
    assert finalized.finalization.revision_number == 2


def test_revise_requires_the_expected_current_revision(
    draft: Report, reviewer: ActorContext, now: datetime
) -> None:
    revised = _revise(draft, reviewer, now, "Second")

    with pytest.raises(StaleRevisionError):
        revise(
            revised,
            reviewer,
            expected_revision_number=1,
            content=draft.current_revision.content,
            now=now,
        )


def test_revise_rejects_identical_content(
    draft: Report, reviewer: ActorContext, now: datetime
) -> None:
    with pytest.raises(InvalidTransitionError, match="identical"):
        revise(
            draft,
            reviewer,
            expected_revision_number=1,
            content=draft.current_revision.content,
            now=now,
        )


# --- rejection --------------------------------------------------------------------------


def test_rejection_removes_approval_and_blocks_finalization(
    draft: Report, approver: ActorContext, now: datetime
) -> None:
    rejected = _reject(_approve(draft, approver, now), approver, now)

    assert rejected.status is ReportStatus.CHANGES_REQUESTED
    assert rejected.effective_approval is None
    assert [d.decision for d in rejected.decisions] == [Decision.APPROVE, Decision.REJECT]
    with pytest.raises(InvalidTransitionError):
        _finalize(rejected, approver, now)
    with pytest.raises(InvalidTransitionError, match="revise"):
        _approve(rejected, approver, now)


def test_rejected_report_can_be_revised_and_approved(
    draft: Report, approver: ActorContext, reviewer: ActorContext, now: datetime
) -> None:
    rejected = _reject(draft, approver, now)
    revised = _revise(rejected, reviewer, now, "Addressed rejection")

    finalized = _finalize(_approve(revised, approver, now), approver, now)

    assert finalized.status is ReportStatus.FINALIZED


# --- finalization and export --------------------------------------------------------------


def test_finalize_without_approval_fails(
    draft: Report, approver: ActorContext, now: datetime
) -> None:
    with pytest.raises(InvalidTransitionError, match="approval"):
        _finalize(draft, approver, now)


def test_finalized_report_cannot_change(
    draft: Report, approver: ActorContext, reviewer: ActorContext, now: datetime
) -> None:
    finalized = _finalize(_approve(draft, approver, now), approver, now)

    with pytest.raises(InvalidTransitionError):
        _revise(finalized, reviewer, now, "Late edit")
    with pytest.raises(InvalidTransitionError):
        _reject(finalized, approver, now)
    with pytest.raises(InvalidTransitionError):
        _approve(finalized, approver, now)


def test_only_finalized_reports_are_exportable(
    draft: Report, approver: ActorContext, reviewer: ActorContext, now: datetime
) -> None:
    approved = _approve(draft, approver, now)
    with pytest.raises(NotExportableError):
        exportable_revision(draft, reviewer)
    with pytest.raises(NotExportableError):
        exportable_revision(approved, reviewer)

    finalized = _finalize(approved, approver, now)

    assert exportable_revision(finalized, reviewer) == finalized.current_revision


# --- idempotency and purity -----------------------------------------------------------------


def test_repeated_identical_requests_are_idempotent(
    draft: Report, approver: ActorContext, now: datetime
) -> None:
    approved = _approve(draft, approver, now)
    assert _approve(approved, approver, now + timedelta(hours=1)) == approved

    rejected = _reject(approved, approver, now)
    assert _reject(rejected, approver, now + timedelta(hours=1)) == rejected

    finalized = _finalize(approved, approver, now)
    assert _finalize(finalized, approver, now + timedelta(hours=1)) == finalized


# --- rejection comments and changed retries --------------------------------------------


@pytest.fixture
def second_approver(tenant_a: UUID) -> ActorContext:
    return ActorContext(tenant_id=tenant_a, actor_id=uuid4(), role=Role.APPROVER)


def _reject_with(report: Report, ctx: ActorContext, now: datetime, comment: str) -> Report:
    current = report.current_revision
    return reject(
        report,
        ctx,
        revision_number=current.revision_number,
        content_sha256=current.content_sha256,
        now=now,
        comment=comment,
    )


@pytest.mark.parametrize("comment", [None, "", "   "])
def test_rejection_decision_requires_a_comment_even_when_built_directly(
    draft: Report, approver: ActorContext, now: datetime, comment: str | None
) -> None:
    current = draft.current_revision

    with pytest.raises(ValidationError):
        ApprovalDecision(
            tenant_id=draft.tenant_id,
            report_id=draft.report_id,
            revision_number=current.revision_number,
            content_sha256=current.content_sha256,
            decision=Decision.REJECT,
            decided_by=approver.actor_id,
            decided_at=now,
            comment=comment,
        )


def test_approval_decision_comment_is_optional(
    draft: Report, approver: ActorContext, now: datetime
) -> None:
    current = draft.current_revision

    decision = ApprovalDecision(
        tenant_id=draft.tenant_id,
        report_id=draft.report_id,
        revision_number=current.revision_number,
        content_sha256=current.content_sha256,
        decision=Decision.APPROVE,
        decided_by=approver.actor_id,
        decided_at=now,
    )

    assert decision.comment is None


@pytest.mark.parametrize("comment", ["", "   "])
def test_reject_with_blank_comment_fails(
    draft: Report, approver: ActorContext, now: datetime, comment: str
) -> None:
    with pytest.raises(ValidationError):
        _reject_with(draft, approver, now, comment)


def test_repeated_rejection_with_blank_comment_does_not_silently_succeed(
    draft: Report, approver: ActorContext, now: datetime
) -> None:
    rejected = _reject(draft, approver, now)

    with pytest.raises(ValidationError):
        _reject_with(rejected, approver, now, "   ")


def test_identical_rejection_retry_keeps_the_original_decision(
    draft: Report, approver: ActorContext, now: datetime
) -> None:
    rejected = _reject(draft, approver, now)

    retried = _reject(rejected, approver, now + timedelta(hours=2))

    assert retried == rejected
    assert len(retried.decisions) == 1
    assert retried.decisions[0].decided_at == now
    assert retried.decisions[0].decided_by == approver.actor_id


def test_rejection_retry_with_a_different_comment_is_a_conflict(
    draft: Report, approver: ActorContext, now: datetime
) -> None:
    rejected = _reject(draft, approver, now)

    with pytest.raises(DecisionConflictError):
        _reject_with(rejected, approver, now, "A different reason.")


def test_rejection_by_a_different_approver_is_a_conflict(
    draft: Report, approver: ActorContext, second_approver: ActorContext, now: datetime
) -> None:
    rejected = _reject(draft, approver, now)

    with pytest.raises(DecisionConflictError):
        _reject(rejected, second_approver, now)


def test_identical_approval_retry_keeps_the_original_decision(
    draft: Report, approver: ActorContext, now: datetime
) -> None:
    approved = _approve(draft, approver, now)

    retried = _approve(approved, approver, now + timedelta(hours=2))

    assert retried == approved
    approval = retried.effective_approval
    assert approval is not None
    assert approval.decided_at == now
    assert approval.decided_by == approver.actor_id


def test_approval_by_a_different_approver_is_a_conflict(
    draft: Report, approver: ActorContext, second_approver: ActorContext, now: datetime
) -> None:
    approved = _approve(draft, approver, now)

    with pytest.raises(DecisionConflictError):
        _approve(approved, second_approver, now)


def test_approval_retry_with_a_different_comment_is_a_conflict(
    draft: Report, approver: ActorContext, now: datetime
) -> None:
    approved = _approve(draft, approver, now)
    current = approved.current_revision

    with pytest.raises(DecisionConflictError):
        approve(
            approved,
            approver,
            revision_number=current.revision_number,
            content_sha256=current.content_sha256,
            now=now,
            comment="Approved after a second read.",
        )


def test_finalization_by_a_different_approver_is_a_conflict(
    draft: Report, approver: ActorContext, second_approver: ActorContext, now: datetime
) -> None:
    finalized = _finalize(_approve(draft, approver, now), approver, now)

    with pytest.raises(DecisionConflictError):
        _finalize(finalized, second_approver, now)
    finalization = finalized.finalization
    assert finalization is not None
    assert finalization.finalized_by == approver.actor_id


def test_transitions_do_not_mutate_their_inputs(
    draft: Report, approver: ActorContext, reviewer: ActorContext, now: datetime
) -> None:
    before = draft.model_dump()

    approved = _approve(draft, approver, now)
    approved_before = approved.model_dump()
    _revise(approved, reviewer, now, "Changed")
    _reject(approved, approver, now)
    _finalize(approved, approver, now)

    assert draft.model_dump() == before
    assert approved.model_dump() == approved_before


# --- invalid aggregates cannot be constructed ----------------------------------------------


def test_cannot_construct_an_approved_report_without_an_approval(draft: Report) -> None:
    with pytest.raises(ValidationError, match="does not match history"):
        draft.model_copy(update={"status": ReportStatus.APPROVED})


def test_cannot_construct_a_finalized_report_without_a_finalization(
    draft: Report, approver: ActorContext, now: datetime
) -> None:
    approved = _approve(draft, approver, now)

    with pytest.raises(ValidationError, match="does not match history"):
        approved.model_copy(update={"status": ReportStatus.FINALIZED})


def test_cannot_finalize_by_construction_without_an_approval(
    draft: Report, approver: ActorContext, now: datetime
) -> None:
    finalization = _finalize(_approve(draft, approver, now), approver, now).finalization

    with pytest.raises(ValidationError, match="requires an approval"):
        draft.model_copy(update={"status": ReportStatus.FINALIZED, "finalization": finalization})


def test_decision_with_a_mismatched_hash_is_rejected(
    draft: Report, approver: ActorContext, now: datetime
) -> None:
    approved = _approve(draft, approver, now)
    forged = approved.decisions[0].model_copy(update={"content_sha256": "a" * 64})

    with pytest.raises(ValidationError, match="hash does not match"):
        approved.model_copy(update={"decisions": (forged,)})


def test_decision_from_another_tenant_is_rejected(
    draft: Report, approver: ActorContext, tenant_b: UUID, now: datetime
) -> None:
    approved = _approve(draft, approver, now)
    forged = approved.decisions[0].model_copy(update={"tenant_id": tenant_b})

    with pytest.raises(ValidationError, match="another tenant"):
        approved.model_copy(update={"decisions": (forged,)})


def test_admin_role_does_not_exist(tenant_a: UUID) -> None:
    with pytest.raises(ValidationError):
        ActorContext.model_validate({"tenant_id": tenant_a, "actor_id": uuid4(), "role": "admin"})
    assert {role.value for role in Role} == {"reviewer", "approver"}
