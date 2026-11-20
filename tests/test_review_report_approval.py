"""M6 wrapper revisions, approval and finalization (ADR-0028). No database."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, get_args
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from evidenceguard_agents import report as builder
from evidenceguard_domain import review_report_approval as ra
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
from evidenceguard_domain.report import ApprovalDecision, Decision, ReportStatus
from evidenceguard_domain.report_content import (
    RENDERER,
    SCHEMA,
    ReviewReportContent,
    review_report_sha256,
)

if TYPE_CHECKING:
    from test_report_builder import world
else:
    from tests.test_report_builder import world

T0 = datetime(2026, 11, 20, 9, 0, tzinfo=UTC)
A1 = UUID("a1a1a1a1-0000-4000-8000-000000000001")
A2 = UUID("a2a2a2a2-0000-4000-8000-000000000002")
R1 = UUID("b1b1b1b1-0000-4000-8000-000000000001")


def wrapper() -> ReviewReportContent:
    return builder.build_report_content(*world((2, 1)))


def opened() -> tuple[ra.WrapperReport, ReviewReportContent]:
    w = wrapper()
    return ra.open_report(w, wrapper_sha256=review_report_sha256(w), now=T0), w


def actor(report: ra.WrapperReport, role: Role, actor_id: UUID | None = None) -> ActorContext:
    return ActorContext(tenant_id=report.tenant_id, actor_id=actor_id or uuid4(), role=role)


def dispositions(
    report: ra.WrapperReport, *values: ra.Disposition, note: str = "Reviewed."
) -> tuple[ra.FindingDisposition, ...]:
    chosen = values or (ra.Disposition.ACCEPTED,) * len(report.finding_ids)
    return tuple(
        ra.FindingDisposition(finding_id=fid, disposition=d, note=note)
        for fid, d in zip(report.finding_ids, chosen, strict=True)
    )


def revised(
    report: ra.WrapperReport, by: ActorContext, notes: str = "Revised."
) -> ra.WrapperReport:
    current = report.current_revision
    return ra.revise(
        report,
        by,
        expected_revision_number=current.revision_number,
        expected_sha256=current.content_sha256,
        dispositions=dispositions(report),
        notes=notes,
        now=T0 + timedelta(minutes=1),
    )


def approved(report: ra.WrapperReport, by: ActorContext) -> ra.WrapperReport:
    current = report.current_revision
    return ra.approve(
        report,
        by,
        revision_number=current.revision_number,
        content_sha256=current.content_sha256,
        now=T0 + timedelta(minutes=2),
    )


# --- values and codec ----------------------------------------------------------------------------


def test_the_base_literals_name_the_wrapper_schema_and_renderer() -> None:
    fields = ra.RevisionContent.model_fields
    assert get_args(fields["base_schema_id"].annotation) == (SCHEMA,)
    assert get_args(fields["base_renderer_id"].annotation) == (RENDERER,)
    assert ra.REVISION_SCHEMA == "evidenceguard.review-report-revision.v1"


def test_the_initial_revision_is_generated_with_every_finding_open() -> None:
    report, w = opened()
    revision = report.current_revision
    assert report.status is ReportStatus.DRAFT
    assert report.report_id == report.review_id == w.binding.review_id
    assert revision.revision_number == 1 and revision.created_by is None
    assert revision.content.notes is None
    assert [d.disposition for d in revision.content.dispositions] == [ra.Disposition.OPEN] * 3
    assert tuple(d.finding_id for d in revision.content.dispositions) == tuple(
        f.finding_id for f in w.content.findings
    )
    assert revision.content.base_wrapper_sha256 == review_report_sha256(w)
    again = ra.open_report(w, wrapper_sha256=review_report_sha256(w), now=T0 + timedelta(days=1))
    assert again.current_revision.content_sha256 == revision.content_sha256


def test_initial_content_refuses_a_wrong_wrapper_digest() -> None:
    with pytest.raises(ValueError):
        ra.initial_content(wrapper(), wrapper_sha256="0" * 64)


def test_the_revision_hash_matches_an_independent_specimen() -> None:
    content = ra.RevisionContent(
        tenant_id=UUID(int=1),
        report_id=UUID(int=2),
        review_id=UUID(int=2),
        base_schema_id=ra.BASE_SCHEMA,
        base_renderer_id=ra.BASE_RENDERER,
        base_wrapper_sha256="c" * 64,
        dispositions=(
            ra.FindingDisposition(finding_id=UUID(int=3), disposition=ra.Disposition.OPEN),
            ra.FindingDisposition(
                finding_id=UUID(int=4), disposition=ra.Disposition.DISMISSED, note="No \u03a9 <b>"
            ),
        ),
        notes="  Checked.  ",
    )
    specimen = (
        '{"content":{"base_renderer_id":"evidenceguard.review-report-markdown.v1",'
        '"base_schema_id":"evidenceguard.review-report-content.v1",'
        '"base_wrapper_sha256":"' + "c" * 64 + '",'
        '"dispositions":[{"disposition":"open",'
        '"finding_id":"00000000-0000-0000-0000-000000000003","note":null},'
        '{"disposition":"dismissed","finding_id":"00000000-0000-0000-0000-000000000004",'
        '"note":"No \\u03a9 <b>"}],"notes":"Checked.",'
        '"report_id":"00000000-0000-0000-0000-000000000002",'
        '"review_id":"00000000-0000-0000-0000-000000000002",'
        '"tenant_id":"00000000-0000-0000-0000-000000000001"},'
        '"schema":"evidenceguard.review-report-revision.v1"}'
    ).encode("ascii")
    assert ra.revision_canonical_bytes(content) == specimen
    assert ra.revision_sha256(content) == hashlib.sha256(specimen).hexdigest()
    assert ra.decode_revision_content(specimen, expected_sha256=ra.revision_sha256(content)) == (
        content
    )


def test_decode_rejects_noncanonical_bytes_and_a_wrong_digest() -> None:
    report, _ = opened()
    revision = report.current_revision
    data = ra.revision_canonical_bytes(revision.content)
    sha = revision.content_sha256
    assert ra.decode_revision_content(data, expected_sha256=sha) == revision.content
    pretty = json.dumps(json.loads(data), indent=1).encode("ascii")
    obj = json.loads(data)
    reordered = json.dumps(dict(reversed(list(obj.items()))), separators=(",", ":")).encode()
    assert reordered != data
    other_schema = data.replace(ra.REVISION_SCHEMA.encode(), b"evidenceguard.other.v1")
    extra = data[:-1] + b',"extra":1}'
    for bad in (pretty, reordered, other_schema, extra, b"", b"\x00" + data, "x".encode("utf-16")):
        with pytest.raises(ra.RevisionEncodingError):
            ra.decode_revision_content(bad, expected_sha256=sha)
    with pytest.raises(ra.RevisionDigestMismatchError):
        ra.decode_revision_content(data, expected_sha256="0" * 64)


def test_dismissal_needs_a_note_and_notes_are_bounded() -> None:
    with pytest.raises(ValidationError):
        ra.FindingDisposition(finding_id=uuid4(), disposition=ra.Disposition.DISMISSED)
    with pytest.raises(ValidationError):
        ra.FindingDisposition(finding_id=uuid4(), disposition=ra.Disposition.DISMISSED, note="  ")
    with pytest.raises(ValidationError):
        ra.FindingDisposition(finding_id=uuid4(), disposition=ra.Disposition.OPEN, note="x" * 2001)
    assert (
        ra.FindingDisposition(finding_id=uuid4(), disposition=ra.Disposition.ACCEPTED).note is None
    )


def test_dispositions_must_cover_the_wrapper_findings_exactly_once_in_order() -> None:
    report, _ = opened()
    by = actor(report, Role.REVIEWER)
    current = report.current_revision
    full = dispositions(report)
    cases = (full[:-1], (*full, full[0]), (full[1], full[0], full[2]), ())
    for bad in cases:
        with pytest.raises(ra.InvalidRevisionContentError):
            ra.revise(
                report,
                by,
                expected_revision_number=1,
                expected_sha256=current.content_sha256,
                dispositions=bad,
                notes=None,
                now=T0,
            )
    with pytest.raises(ValidationError):  # the aggregate refuses it too
        ra.WrapperReport(
            **{
                **report.model_dump(),
                "finding_ids": report.finding_ids[:-1],
            }
        )


def test_legacy_decisions_and_reports_are_refused() -> None:
    report, _ = opened()
    current = report.current_revision
    legacy = ApprovalDecision(
        tenant_id=report.tenant_id,
        report_id=report.report_id,
        revision_number=1,
        content_sha256=current.content_sha256,
        decision=Decision.APPROVE,
        decided_by=A1,
        decided_at=T0,
    )
    data: dict[str, Any] = {
        "tenant_id": report.tenant_id,
        "report_id": report.report_id,
        "review_id": report.review_id,
        "base_wrapper_sha256": report.base_wrapper_sha256,
        "finding_ids": report.finding_ids,
        "status": ReportStatus.APPROVED,
        "revisions": report.revisions,
        "decisions": (legacy,),
    }
    with pytest.raises(ValidationError):
        ra.WrapperReport(**data)
    with pytest.raises(TypeError):
        ra.approve(
            legacy,  # type: ignore[arg-type]
            actor(report, Role.APPROVER),
            revision_number=1,
            content_sha256=current.content_sha256,
            now=T0,
        )


def test_a_revision_binds_tenant_report_review_and_wrapper() -> None:
    report, _ = opened()
    content = report.current_revision.content
    for change in (
        {"tenant_id": uuid4()},
        {"base_wrapper_sha256": "d" * 64},
    ):
        moved = content.model_copy(update=change)
        revision = ra.WrapperRevision.create(
            revision_number=1, content=moved, created_by=None, created_at=T0
        )
        with pytest.raises(ValidationError):
            ra.WrapperReport(**{**report.model_dump(), "revisions": (revision,)})
    with pytest.raises(ValidationError):
        content.model_copy(update={"report_id": uuid4()})  # report ID must equal review ID
    with pytest.raises(ValidationError):  # tampered hash
        ra.WrapperRevision(**{**report.current_revision.model_dump(), "content_sha256": "0" * 64})
    with pytest.raises(ValidationError):  # revision 1 has no author
        ra.WrapperRevision.create(revision_number=1, content=content, created_by=A1, created_at=T0)
    with pytest.raises(ValidationError):  # later revisions have one
        ra.WrapperRevision.create(
            revision_number=2, content=content, created_by=None, created_at=T0
        )


# --- roles ---------------------------------------------------------------------------------------


def test_a_reviewer_cannot_approve_reject_or_finalize() -> None:
    report, _ = opened()
    reviewer = actor(report, Role.REVIEWER)
    sha = report.current_revision.content_sha256
    with pytest.raises(PermissionDeniedError):
        ra.approve(report, reviewer, revision_number=1, content_sha256=sha, now=T0)
    with pytest.raises(PermissionDeniedError):
        ra.reject(report, reviewer, revision_number=1, content_sha256=sha, now=T0, comment="No.")
    ready = approved(report, actor(report, Role.APPROVER))
    with pytest.raises(PermissionDeniedError):
        ra.finalize(ready, reviewer, revision_number=1, content_sha256=sha, now=T0)
    assert revised(report, reviewer).status is ReportStatus.DRAFT  # a reviewer may revise


def test_an_admin_cannot_revise_approve_finalize_or_export() -> None:
    report, _ = opened()
    admin = actor(report, Role.ADMIN)
    sha = report.current_revision.content_sha256
    with pytest.raises(PermissionDeniedError):
        revised(report, admin)
    with pytest.raises(PermissionDeniedError):
        ra.approve(report, admin, revision_number=1, content_sha256=sha, now=T0)
    with pytest.raises(PermissionDeniedError):
        ra.finalize(report, admin, revision_number=1, content_sha256=sha, now=T0)
    with pytest.raises(PermissionDeniedError):
        ra.exportable_revision(report, admin)


def test_another_tenant_is_refused_first() -> None:
    report, _ = opened()
    stranger = ActorContext(tenant_id=uuid4(), actor_id=A1, role=Role.APPROVER)
    with pytest.raises(TenantMismatchError):
        approved(report, stranger)
    with pytest.raises(TenantMismatchError):
        ra.exportable_revision(report, stranger)


# --- transitions ---------------------------------------------------------------------------------


def test_stale_revision_and_wrong_hash_are_refused() -> None:
    report, _ = opened()
    approver = actor(report, Role.APPROVER)
    sha = report.current_revision.content_sha256
    with pytest.raises(StaleRevisionError):
        ra.approve(report, approver, revision_number=2, content_sha256=sha, now=T0)
    with pytest.raises(ContentHashMismatchError):
        ra.approve(report, approver, revision_number=1, content_sha256="0" * 64, now=T0)
    with pytest.raises(ContentHashMismatchError):
        ra.revise(
            report,
            approver,
            expected_revision_number=1,
            expected_sha256="0" * 64,
            dispositions=dispositions(report),
            notes=None,
            now=T0,
        )


def test_a_revision_after_approval_blocks_finalization_until_reapproved() -> None:
    report, _ = opened()
    first, second = actor(report, Role.APPROVER, A1), actor(report, Role.APPROVER, A2)
    r1 = report.current_revision
    ok = approved(report, first)
    assert ok.status is ReportStatus.APPROVED
    draft = revised(ok, actor(report, Role.REVIEWER))
    assert draft.status is ReportStatus.DRAFT and draft.effective_approval is None
    with pytest.raises(StaleRevisionError):
        ra.finalize(draft, first, revision_number=1, content_sha256=r1.content_sha256, now=T0)
    r2 = draft.current_revision
    with pytest.raises(InvalidTransitionError):
        ra.finalize(draft, first, revision_number=2, content_sha256=r2.content_sha256, now=T0)
    reapproved = approved(draft, second)
    done = ra.finalize(
        reapproved, first, revision_number=2, content_sha256=r2.content_sha256, now=T0
    )
    assert done.status is ReportStatus.FINALIZED
    assert ra.exportable_revision(done, actor(report, Role.REVIEWER)) == r2


def test_an_identical_revision_is_refused_and_the_cap_holds() -> None:
    report, _ = opened()
    by = actor(report, Role.REVIEWER)
    with pytest.raises(InvalidTransitionError):
        ra.revise(
            report,
            by,
            expected_revision_number=1,
            expected_sha256=report.current_revision.content_sha256,
            dispositions=report.current_revision.content.dispositions,
            notes=None,
            now=T0,
        )
    current = report
    for n in range(2, ra.MAX_REVISIONS + 1):
        current = revised(current, by, notes=f"Revision {n}.")
    assert len(current.revisions) == ra.MAX_REVISIONS
    with pytest.raises(InvalidTransitionError):
        revised(current, by, notes="One more.")


def test_an_approver_cannot_approve_reject_or_finalize_their_own_revision() -> None:
    report, _ = opened()
    author = actor(report, Role.APPROVER, A1)
    other = actor(report, Role.APPROVER, A2)
    mine = revised(report, author)
    sha = mine.current_revision.content_sha256
    with pytest.raises(InvalidTransitionError, match="approver authored this revision"):
        ra.approve(mine, author, revision_number=2, content_sha256=sha, now=T0)
    with pytest.raises(InvalidTransitionError, match="approver authored this revision"):
        ra.reject(mine, author, revision_number=2, content_sha256=sha, now=T0, comment="No.")
    ok = approved(mine, other)
    with pytest.raises(InvalidTransitionError, match="approver authored this revision"):
        ra.finalize(ok, author, revision_number=2, content_sha256=sha, now=T0)
    assert ra.finalize(ok, other, revision_number=2, content_sha256=sha, now=T0).finalization


def test_retries_and_conflicts_follow_the_legacy_rules() -> None:
    report, _ = opened()
    first, second = actor(report, Role.APPROVER, A1), actor(report, Role.APPROVER, A2)
    sha = report.current_revision.content_sha256
    ok = approved(report, first)
    assert approved(ok, first) is ok
    with pytest.raises(DecisionConflictError):
        approved(ok, second)
    done = ra.finalize(ok, first, revision_number=1, content_sha256=sha, now=T0)
    assert ra.finalize(done, first, revision_number=1, content_sha256=sha, now=T0) is done
    with pytest.raises(DecisionConflictError):
        ra.finalize(done, second, revision_number=1, content_sha256=sha, now=T0)
    with pytest.raises(InvalidTransitionError):
        revised(done, actor(report, Role.REVIEWER))
    rejected = ra.reject(report, first, revision_number=1, content_sha256=sha, now=T0, comment="No")
    assert rejected.status is ReportStatus.CHANGES_REQUESTED
    assert (
        ra.reject(rejected, first, revision_number=1, content_sha256=sha, now=T0, comment="No")
        is rejected
    )
    with pytest.raises(InvalidTransitionError):
        approved(rejected, second)
    with pytest.raises(NotExportableError):
        ra.exportable_revision(ok, first)


def test_transitions_do_not_mutate_inputs() -> None:
    report, _ = opened()
    before = report.model_dump()
    approver = actor(report, Role.APPROVER)
    ok = approved(report, approver)
    revised(ok, actor(report, Role.REVIEWER))
    ra.reject(
        report,
        approver,
        revision_number=1,
        content_sha256=report.current_revision.content_sha256,
        now=T0,
        comment="No.",
    )
    assert report.model_dump() == before and len(ok.decisions) == 1
