"""Pure report-approval transitions.

Each function validates its inputs, returns a new ``Report`` (or the same one when a repeated
request changes nothing) and never mutates its arguments. Checks run in this order: tenant,
role, finalized state, revision and hash, then the request itself (for example a rejection's
comment). Only then is a retry recognised.

Retries
-------
An **identical retry** has the same decision, revision, hash, actor and comment (or, for
finalization, the same revision, hash and actor). It returns the report unchanged, so the
original decision time and attribution are kept. A **changed request** for a decision that is
already in effect (another actor or another comment) raises ``DecisionConflictError``. It is
neither treated as a retry nor recorded as a second decision, so no information is silently
dropped.

These are pure functions. They do not provide database atomicity or protect against two
concurrent requests; persistence must enforce that (for example with a row lock or a
compare-and-set on revision number and hash).
"""

from datetime import datetime
from uuid import UUID

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
from evidenceguard_domain.report import (
    ApprovalDecision,
    Decision,
    Finalization,
    Report,
    ReportRevision,
    ReportStatus,
)
from evidenceguard_domain.report import (
    content_sha256 as compute_content_sha256,
)

_EDITORS = frozenset({Role.REVIEWER, Role.APPROVER})
_APPROVERS = frozenset({Role.APPROVER})


def _require_tenant(tenant_id: UUID, ctx: ActorContext) -> None:
    if ctx.tenant_id != tenant_id:
        raise TenantMismatchError("the actor's tenant does not own this report")


def _require_role(ctx: ActorContext, allowed: frozenset[Role], action: str) -> None:
    if ctx.role not in allowed:
        raise PermissionDeniedError(f"role {ctx.role.value!r} may not {action}")


def _require_not_finalized(report: Report, action: str) -> None:
    if report.status is ReportStatus.FINALIZED:
        raise InvalidTransitionError(f"cannot {action} a finalized report")


def _require_exact_current(report: Report, revision_number: int, sha: str) -> None:
    current = report.current_revision
    if revision_number != current.revision_number:
        raise StaleRevisionError(
            f"revision {revision_number} is not the current revision ({current.revision_number})"
        )
    if sha != current.content_sha256:
        raise ContentHashMismatchError("content hash does not match the current revision")


def _rebuild(
    report: Report,
    *,
    status: ReportStatus,
    revisions: tuple[ReportRevision, ...] | None = None,
    decisions: tuple[ApprovalDecision, ...] | None = None,
    finalization: Finalization | None = None,
) -> Report:
    """Build a new, fully validated report from an existing one plus changes."""
    return Report(
        tenant_id=report.tenant_id,
        report_id=report.report_id,
        status=status,
        revisions=report.revisions if revisions is None else revisions,
        decisions=report.decisions if decisions is None else decisions,
        finalization=finalization,
    )


def create_draft(
    ctx: ActorContext, *, report_id: UUID, content: ReportContent, now: datetime
) -> Report:
    """Create a report whose first revision is a draft."""
    _require_tenant(content.tenant_id, ctx)
    _require_role(ctx, _EDITORS, "create a report")
    revision = ReportRevision.create(
        report_id=report_id,
        revision_number=1,
        content=content,
        created_by=ctx.actor_id,
        created_at=now,
    )
    return Report(
        tenant_id=ctx.tenant_id,
        report_id=report_id,
        status=ReportStatus.DRAFT,
        revisions=(revision,),
    )


def approve(
    report: Report,
    ctx: ActorContext,
    *,
    revision_number: int,
    content_sha256: str,
    now: datetime,
    comment: str | None = None,
) -> Report:
    """Approve the exact current revision. An identical retry changes nothing."""
    _require_tenant(report.tenant_id, ctx)
    _require_role(ctx, _APPROVERS, "approve")
    _require_not_finalized(report, "approve")
    _require_exact_current(report, revision_number, content_sha256)
    decision = ApprovalDecision(
        tenant_id=report.tenant_id,
        report_id=report.report_id,
        revision_number=revision_number,
        content_sha256=content_sha256,
        decision=Decision.APPROVE,
        decided_by=ctx.actor_id,
        decided_at=now,
        comment=comment,
    )
    existing = report.effective_approval
    if existing is not None:
        if existing.same_request_as(decision):
            return report
        raise DecisionConflictError(
            "this revision is already approved by a different actor or with a different comment"
        )
    if report.status is ReportStatus.CHANGES_REQUESTED:
        raise InvalidTransitionError("this revision was rejected; revise it before approving")
    return _rebuild(report, status=ReportStatus.APPROVED, decisions=(*report.decisions, decision))


def reject(
    report: Report,
    ctx: ActorContext,
    *,
    revision_number: int,
    content_sha256: str,
    now: datetime,
    comment: str,
) -> Report:
    """Reject the exact current revision, removing any effective approval.

    The comment is validated (non-blank) before a retry is recognised, so a repeated rejection
    with an invalid comment fails instead of returning the earlier result.
    """
    _require_tenant(report.tenant_id, ctx)
    _require_role(ctx, _APPROVERS, "reject")
    _require_not_finalized(report, "reject")
    _require_exact_current(report, revision_number, content_sha256)
    decision = ApprovalDecision(
        tenant_id=report.tenant_id,
        report_id=report.report_id,
        revision_number=revision_number,
        content_sha256=content_sha256,
        decision=Decision.REJECT,
        decided_by=ctx.actor_id,
        decided_at=now,
        comment=comment,
    )
    if report.status is ReportStatus.CHANGES_REQUESTED:
        if report.decisions[-1].same_request_as(decision):
            return report
        raise DecisionConflictError(
            "this revision is already rejected by a different actor or with a different comment"
        )
    return _rebuild(
        report, status=ReportStatus.CHANGES_REQUESTED, decisions=(*report.decisions, decision)
    )


def revise(
    report: Report,
    ctx: ActorContext,
    *,
    expected_revision_number: int,
    content: ReportContent,
    now: datetime,
) -> Report:
    """Add a new revision. Earlier decisions stay in history but no longer count."""
    _require_tenant(report.tenant_id, ctx)
    _require_role(ctx, _EDITORS, "revise")
    _require_not_finalized(report, "revise")
    current = report.current_revision
    if expected_revision_number != current.revision_number:
        raise StaleRevisionError(
            f"expected revision {expected_revision_number}, "
            f"but the current revision is {current.revision_number}"
        )
    if content.tenant_id != report.tenant_id:
        raise TenantMismatchError("revised content belongs to another tenant")
    if compute_content_sha256(content) == current.content_sha256:
        raise InvalidTransitionError("revised content is identical to the current revision")
    revision = ReportRevision.create(
        report_id=report.report_id,
        revision_number=current.revision_number + 1,
        content=content,
        created_by=ctx.actor_id,
        created_at=now,
    )
    return _rebuild(report, status=ReportStatus.DRAFT, revisions=(*report.revisions, revision))


def finalize(
    report: Report,
    ctx: ActorContext,
    *,
    revision_number: int,
    content_sha256: str,
    now: datetime,
) -> Report:
    """Finalize the exact current revision, which must carry the effective approval."""
    _require_tenant(report.tenant_id, ctx)
    _require_role(ctx, _APPROVERS, "finalize")
    if report.finalization is not None:
        final = report.finalization
        if final.revision_number != revision_number or final.content_sha256 != content_sha256:
            raise InvalidTransitionError("the report is already finalized at another revision")
        if final.finalized_by != ctx.actor_id:
            raise DecisionConflictError("the report was already finalized by a different actor")
        return report
    _require_exact_current(report, revision_number, content_sha256)
    if report.effective_approval is None:
        raise InvalidTransitionError("finalizing requires an approval of the current revision")
    finalization = Finalization(
        tenant_id=report.tenant_id,
        report_id=report.report_id,
        revision_number=revision_number,
        content_sha256=content_sha256,
        finalized_by=ctx.actor_id,
        finalized_at=now,
    )
    return _rebuild(report, status=ReportStatus.FINALIZED, finalization=finalization)


def exportable_revision(report: Report, ctx: ActorContext) -> ReportRevision:
    """Return the finalized revision to export, or raise if the report is not exportable."""
    _require_tenant(report.tenant_id, ctx)
    _require_role(ctx, _EDITORS, "export")
    if report.status is not ReportStatus.FINALIZED:
        raise NotExportableError("only finalized reports can be exported")
    return report.current_revision
