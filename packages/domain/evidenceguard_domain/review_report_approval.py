"""Hash-bound revisions, approval and finalization over the M5f review report (M6, ADR-0028).

F11 forbids feeding the M5f wrapper digest into the legacy ``approval.py``/``report.py`` values
(which bind ``evidenceguard.report-content.v1``), so this module defines its own
schema-dispatched values. The legacy module is unchanged.

What a revision is
------------------
A revision never edits the machine conclusions (findings, statuses, quotes, unresolved reasons):
those live in the hashed wrapper. It holds one disposition per wrapper finding, in wrapper
finding order, an optional note per finding and optional report notes, and it binds tenant,
report, review, the wrapper's schema and renderer, and the exact wrapper SHA-256. The revision
hash therefore covers the wrapper hash: approving revision n approves the exact wrapper bytes.

What is hashed
--------------
``revision_sha256`` is the SHA-256 hex digest of::

    json.dumps({"schema": REVISION_SCHEMA, "content": content.model_dump(mode="json")},
               sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)

encoded as ASCII. ``decode_revision_content`` accepts only bytes that re-encode to themselves.

Transitions
-----------
Pure functions with the legacy check order (tenant, role, finalized state, revision and hash,
then the request), the legacy retry rules (an identical retry returns the same report object; a
changed request for a decision already in effect is ``DecisionConflictError``), plus separation
of duties: an approver may not approve, reject or finalize a revision they authored. They do not
provide database atomicity; persistence serialises them under a row lock.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Final, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from evidenceguard_domain._base import DomainModel
from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_domain.errors import (
    ContentHashMismatchError,
    DecisionConflictError,
    DomainError,
    InvalidTransitionError,
    NotExportableError,
    PermissionDeniedError,
    StaleRevisionError,
    TenantMismatchError,
)
from evidenceguard_domain.evidence import LongText
from evidenceguard_domain.report import Decision, ReportStatus, Sha256Hex
from evidenceguard_domain.report_content import (
    RENDERER,
    SCHEMA,
    ReviewReportContent,
    review_report_sha256,
)

__all__ = [
    "BASE_RENDERER",
    "BASE_SCHEMA",
    "MAX_DISPOSITIONS",
    "MAX_REVISIONS",
    "MAX_REVISION_BYTES",
    "REVISION_SCHEMA",
    "Disposition",
    "ExportInput",
    "ExportResult",
    "FindingDisposition",
    "InvalidRevisionContentError",
    "RevisionContent",
    "RevisionDigestMismatchError",
    "RevisionEncodingError",
    "WrapperApprovalDecision",
    "WrapperFinalization",
    "WrapperReport",
    "WrapperRevision",
    "approve",
    "decode_revision_content",
    "exportable_revision",
    "finalize",
    "initial_content",
    "open_report",
    "reject",
    "revise",
    "revision_canonical_bytes",
    "revision_sha256",
]

REVISION_SCHEMA: Final = "evidenceguard.review-report-revision.v1"
BASE_SCHEMA: Final = "evidenceguard.review-report-content.v1"
BASE_RENDERER: Final = "evidenceguard.review-report-markdown.v1"
if (BASE_SCHEMA, BASE_RENDERER) != (SCHEMA, RENDERER):  # pinned literals must not drift
    raise ImportError("the M6 base literals differ from the M5f wrapper schema and renderer")
MAX_REVISIONS = 100
MAX_DISPOSITIONS = 200
MAX_REVISION_BYTES = 1_048_576
AUTHOR_MESSAGE = "approver authored this revision"

# Role.ADMIN is in neither set (ADR-0005): administering accounts grants no report rights.
_EDITORS = frozenset({Role.REVIEWER, Role.APPROVER})
_APPROVERS = frozenset({Role.APPROVER})

FindingNote = Annotated[str, StringConstraints(min_length=1, max_length=2000)]
ReportNotes = Annotated[str, StringConstraints(min_length=1, max_length=4000)]


class InvalidRevisionContentError(DomainError):
    """The requested dispositions or notes do not form a valid revision of this report (for
    example a finding is missing, repeated or out of order, or the bytes exceed the cap)."""


class RevisionEncodingError(ValueError):
    """Stored revision bytes are not the canonical encoding of a valid revision."""


class RevisionDigestMismatchError(ValueError):
    """Stored revision bytes do not hash to the expected digest."""


class Disposition(StrEnum):
    OPEN = "open"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"


class FindingDisposition(DomainModel):
    """A reviser's disposition of one wrapper finding. A dismissal must explain itself."""

    finding_id: UUID
    disposition: Disposition
    note: FindingNote | None = None

    @model_validator(mode="after")
    def _check_note(self) -> Self:
        if self.disposition is Disposition.DISMISSED and self.note is None:
            raise ValueError("a dismissal requires a note")
        return self


class RevisionContent(DomainModel):
    """Everything a revision says. This, and only this, is covered by the revision hash."""

    tenant_id: UUID
    report_id: UUID
    review_id: UUID
    base_schema_id: Literal["evidenceguard.review-report-content.v1"]
    base_renderer_id: Literal["evidenceguard.review-report-markdown.v1"]
    base_wrapper_sha256: Sha256Hex
    dispositions: Annotated[tuple[FindingDisposition, ...], Field(max_length=MAX_DISPOSITIONS)]
    notes: ReportNotes | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.report_id != self.review_id:
            raise ValueError("the report ID must equal the review ID")
        ids = [d.finding_id for d in self.dispositions]
        if len(set(ids)) != len(ids):
            raise ValueError("each finding may have only one disposition")
        return self


# --- codec ---------------------------------------------------------------------------------------


def _payload(content: RevisionContent) -> dict[str, Any]:
    return {"schema": REVISION_SCHEMA, "content": content.model_dump(mode="json")}


def _dumps(value: object) -> bytes:
    text = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    )
    return text.encode("ascii")


def revision_canonical_bytes(content: RevisionContent) -> bytes:
    """The exact bytes ``revision_sha256`` hashes (see the module docstring)."""
    return _dumps(_payload(content))


def revision_sha256(content: RevisionContent) -> str:
    return hashlib.sha256(revision_canonical_bytes(content)).hexdigest()


def decode_revision_content(data: bytes, *, expected_sha256: str) -> RevisionContent:
    """Strictly decode stored revision bytes: printable ASCII, the revision schema, a valid
    ``RevisionContent``, re-encoding to exactly the same bytes, and the expected digest."""
    if type(data) is not bytes or not 1 <= len(data) <= MAX_REVISION_BYTES:
        raise RevisionEncodingError("revision bytes are missing or too large")
    if any(byte < 0x20 or byte > 0x7E for byte in data):
        raise RevisionEncodingError("revision bytes are not printable ASCII")
    try:
        obj = json.loads(data)
        if type(obj) is not dict or set(obj) != {"schema", "content"}:
            raise ValueError("unexpected revision envelope")
        if obj["schema"] != REVISION_SCHEMA:
            raise ValueError("unsupported revision schema")
        content = RevisionContent.model_validate(obj["content"])
    except ValueError:
        raise RevisionEncodingError("revision bytes are not a valid revision") from None
    if revision_canonical_bytes(content) != data:
        raise RevisionEncodingError("revision bytes are not canonical")
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise RevisionDigestMismatchError("revision bytes do not match the expected digest")
    return content


def _finding_ids(wrapper: ReviewReportContent) -> tuple[UUID, ...]:
    return tuple(f.finding_id for f in wrapper.content.findings)


def initial_content(wrapper: ReviewReportContent, *, wrapper_sha256: str) -> RevisionContent:
    """Revision 1: every wrapper finding ``open``, no notes, report ID equal to the review ID."""
    if review_report_sha256(wrapper) != wrapper_sha256:
        raise ValueError("the wrapper digest does not match the wrapper")
    binding = wrapper.binding
    return RevisionContent(
        tenant_id=binding.tenant_id,
        report_id=binding.review_id,
        review_id=binding.review_id,
        base_schema_id=BASE_SCHEMA,
        base_renderer_id=BASE_RENDERER,
        base_wrapper_sha256=wrapper_sha256,
        dispositions=tuple(
            FindingDisposition(finding_id=fid, disposition=Disposition.OPEN)
            for fid in _finding_ids(wrapper)
        ),
    )


# --- aggregate -----------------------------------------------------------------------------------


class WrapperRevision(DomainModel):
    """One immutable revision. Revision 1 is generated (no author); later ones are revised."""

    schema_id: Literal["evidenceguard.review-report-revision.v1"] = REVISION_SCHEMA
    report_id: UUID
    revision_number: Annotated[int, Field(ge=1, le=MAX_REVISIONS)]
    content: RevisionContent
    content_sha256: Sha256Hex
    created_by: UUID | None
    created_at: AwareDatetime

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.content_sha256 != revision_sha256(self.content):
            raise ValueError("content_sha256 does not match the revision content")
        if self.content.report_id != self.report_id:
            raise ValueError("revision content belongs to another report")
        if (self.created_by is None) != (self.revision_number == 1):
            raise ValueError("only revision 1 is generated, and it has no author")
        if len(revision_canonical_bytes(self.content)) > MAX_REVISION_BYTES:
            raise ValueError("revision content is too large")
        return self

    @classmethod
    def create(
        cls,
        *,
        revision_number: int,
        content: RevisionContent,
        created_by: UUID | None,
        created_at: datetime,
    ) -> Self:
        return cls(
            report_id=content.report_id,
            revision_number=revision_number,
            content=content,
            content_sha256=revision_sha256(content),
            created_by=created_by,
            created_at=created_at,
        )


class WrapperApprovalDecision(DomainModel):
    """An approver's decision bound to one tenant, report, revision number and revision hash."""

    schema_id: Literal["evidenceguard.review-report-revision.v1"] = REVISION_SCHEMA
    tenant_id: UUID
    report_id: UUID
    revision_number: Annotated[int, Field(ge=1, le=MAX_REVISIONS)]
    content_sha256: Sha256Hex
    decision: Decision
    decided_by: UUID
    decided_at: AwareDatetime
    comment: LongText | None = None

    @model_validator(mode="after")
    def _check_comment(self) -> Self:
        if self.decision is Decision.REJECT and self.comment is None:
            raise ValueError("a rejection requires a comment")
        return self

    def same_request_as(self, other: "WrapperApprovalDecision") -> bool:
        """Same decision, binding, actor and comment; the timestamp is ignored."""
        return (
            self.decision is other.decision
            and self.tenant_id == other.tenant_id
            and self.report_id == other.report_id
            and self.revision_number == other.revision_number
            and self.content_sha256 == other.content_sha256
            and self.decided_by == other.decided_by
            and self.comment == other.comment
        )


class WrapperFinalization(DomainModel):
    """Record that one exact approved revision was finalized."""

    schema_id: Literal["evidenceguard.review-report-revision.v1"] = REVISION_SCHEMA
    tenant_id: UUID
    report_id: UUID
    revision_number: Annotated[int, Field(ge=1, le=MAX_REVISIONS)]
    content_sha256: Sha256Hex
    finalized_by: UUID
    finalized_at: AwareDatetime


class WrapperReport(DomainModel):
    """A report over one stored review output: its revisions, decisions and finalization.

    ``status`` must equal the status derived from the history (as in the legacy ``Report``).
    Every revision binds this tenant, report, review and base wrapper, and lists exactly
    ``finding_ids`` in order. Decisions and the finalization never come from the revision's own
    author.
    """

    tenant_id: UUID
    report_id: UUID
    review_id: UUID
    base_wrapper_sha256: Sha256Hex
    finding_ids: Annotated[tuple[UUID, ...], Field(max_length=MAX_DISPOSITIONS)]
    status: ReportStatus
    revisions: Annotated[tuple[WrapperRevision, ...], Field(min_length=1, max_length=MAX_REVISIONS)]
    decisions: tuple[WrapperApprovalDecision, ...] = ()
    finalization: WrapperFinalization | None = None

    @property
    def current_revision(self) -> WrapperRevision:
        return self.revisions[-1]

    @property
    def effective_approval(self) -> WrapperApprovalDecision | None:
        """The latest decision, if it approves the current revision and hash."""
        if not self.decisions:
            return None
        latest = self.decisions[-1]
        current = self.current_revision
        if (
            latest.decision is Decision.APPROVE
            and latest.revision_number == current.revision_number
            and latest.content_sha256 == current.content_sha256
        ):
            return latest
        return None

    @property
    def effective_approval_number(self) -> int | None:
        """The 1-based decision number of ``effective_approval``."""
        return len(self.decisions) if self.effective_approval is not None else None

    def _derived_status(self) -> ReportStatus:
        if self.finalization is not None:
            return ReportStatus.FINALIZED
        if self.decisions and self.decisions[-1].revision_number == len(self.revisions):
            if self.decisions[-1].decision is Decision.APPROVE:
                return ReportStatus.APPROVED
            return ReportStatus.CHANGES_REQUESTED
        return ReportStatus.DRAFT

    def _check_binding(
        self, kind: str, tenant_id: UUID, report_id: UUID, revision_number: int, sha: str
    ) -> WrapperRevision:
        if tenant_id != self.tenant_id:
            raise ValueError(f"{kind} belongs to another tenant")
        if report_id != self.report_id:
            raise ValueError(f"{kind} belongs to another report")
        if not 1 <= revision_number <= len(self.revisions):
            raise ValueError(f"{kind} refers to an unknown revision")
        revision = self.revisions[revision_number - 1]
        if sha != revision.content_sha256:
            raise ValueError(f"{kind} hash does not match revision {revision_number}")
        return revision

    @model_validator(mode="after")
    def _check_history(self) -> Self:
        if self.report_id != self.review_id:
            raise ValueError("the report ID must equal the review ID")
        for number, revision in enumerate(self.revisions, start=1):
            if revision.revision_number != number:
                raise ValueError("revisions must be numbered 1..n in order")
            content = revision.content
            if (
                revision.report_id != self.report_id
                or content.tenant_id != self.tenant_id
                or content.review_id != self.review_id
                or content.base_wrapper_sha256 != self.base_wrapper_sha256
            ):
                raise ValueError("revision is bound to another tenant, report, review or wrapper")
            if tuple(d.finding_id for d in content.dispositions) != self.finding_ids:
                raise ValueError("revision dispositions must list the wrapper findings in order")
            if number > 1 and content == self.revisions[number - 2].content:
                raise ValueError("a revision must differ from the previous one")

        previous = 0
        for decision in self.decisions:
            revision = self._check_binding(
                "decision",
                decision.tenant_id,
                decision.report_id,
                decision.revision_number,
                decision.content_sha256,
            )
            if decision.revision_number < previous:
                raise ValueError("decisions must follow revision order")
            if revision.created_by == decision.decided_by:
                raise ValueError(AUTHOR_MESSAGE)
            previous = decision.revision_number

        if self.finalization is not None:
            final = self.finalization
            revision = self._check_binding(
                "finalization",
                final.tenant_id,
                final.report_id,
                final.revision_number,
                final.content_sha256,
            )
            approval = self.effective_approval
            if approval is None or approval.revision_number != final.revision_number:
                raise ValueError("finalization requires an approval of the current revision")
            if revision.created_by == final.finalized_by:
                raise ValueError(AUTHOR_MESSAGE)

        expected = self._derived_status()
        if self.status is not expected:
            raise ValueError(
                f"status {self.status.value!r} does not match history ({expected.value!r})"
            )
        return self


# --- export values (pure; built by persistence, rendered by the agents package) ------------------


@dataclass(frozen=True)
class ExportInput:
    """Everything an export renderer may use: the finalized report, the wrapper decoded from its
    stored bytes, the exact revision, its effective approval and the finalization."""

    report: WrapperReport
    wrapper: ReviewReportContent
    wrapper_sha256: str
    revision: WrapperRevision
    approval: WrapperApprovalDecision
    finalization: WrapperFinalization


@dataclass(frozen=True)
class ExportResult:
    body: bytes
    media_type: str
    export_sha256: str


# --- transitions ---------------------------------------------------------------------------------


def _require_report(report: object) -> WrapperReport:
    if type(report) is not WrapperReport:
        raise TypeError("expected a WrapperReport")
    assert isinstance(report, WrapperReport)
    return report


def _require_tenant(tenant_id: UUID, ctx: ActorContext) -> None:
    if ctx.tenant_id != tenant_id:
        raise TenantMismatchError("the actor's tenant does not own this report")


def _require_role(ctx: ActorContext, allowed: frozenset[Role], action: str) -> None:
    if ctx.role not in allowed:
        raise PermissionDeniedError(f"role {ctx.role.value!r} may not {action}")


def _require_not_finalized(report: WrapperReport, action: str) -> None:
    if report.status is ReportStatus.FINALIZED:
        raise InvalidTransitionError(f"cannot {action} a finalized report")


def _require_exact_current(report: WrapperReport, revision_number: int, sha: str) -> None:
    current = report.current_revision
    if revision_number != current.revision_number:
        raise StaleRevisionError(
            f"revision {revision_number} is not the current revision ({current.revision_number})"
        )
    if sha != current.content_sha256:
        raise ContentHashMismatchError("content hash does not match the current revision")


def _require_not_author(report: WrapperReport, ctx: ActorContext) -> None:
    if report.current_revision.created_by == ctx.actor_id:
        raise InvalidTransitionError(AUTHOR_MESSAGE)


def _rebuild(
    report: WrapperReport,
    *,
    status: ReportStatus,
    revisions: tuple[WrapperRevision, ...] | None = None,
    decisions: tuple[WrapperApprovalDecision, ...] | None = None,
    finalization: WrapperFinalization | None = None,
) -> WrapperReport:
    return WrapperReport(
        tenant_id=report.tenant_id,
        report_id=report.report_id,
        review_id=report.review_id,
        base_wrapper_sha256=report.base_wrapper_sha256,
        finding_ids=report.finding_ids,
        status=status,
        revisions=report.revisions if revisions is None else revisions,
        decisions=report.decisions if decisions is None else decisions,
        finalization=finalization,
    )


def open_report(
    wrapper: ReviewReportContent, *, wrapper_sha256: str, now: datetime
) -> WrapperReport:
    """The draft report whose generated revision 1 is a pure function of the wrapper."""
    content = initial_content(wrapper, wrapper_sha256=wrapper_sha256)
    revision = WrapperRevision.create(
        revision_number=1, content=content, created_by=None, created_at=now
    )
    return WrapperReport(
        tenant_id=content.tenant_id,
        report_id=content.report_id,
        review_id=content.review_id,
        base_wrapper_sha256=wrapper_sha256,
        finding_ids=_finding_ids(wrapper),
        status=ReportStatus.DRAFT,
        revisions=(revision,),
    )


def revise(
    report: WrapperReport,
    ctx: ActorContext,
    *,
    expected_revision_number: int,
    expected_sha256: str,
    dispositions: tuple[FindingDisposition, ...],
    notes: str | None,
    now: datetime,
) -> WrapperReport:
    """Add a revision. Earlier decisions stay in history but no longer count."""
    report = _require_report(report)
    _require_tenant(report.tenant_id, ctx)
    _require_role(ctx, _EDITORS, "revise")
    _require_not_finalized(report, "revise")
    _require_exact_current(report, expected_revision_number, expected_sha256)
    if len(report.revisions) >= MAX_REVISIONS:
        raise InvalidTransitionError("the report has reached its revision limit")
    if tuple(d.finding_id for d in dispositions) != report.finding_ids:
        raise InvalidRevisionContentError(
            "dispositions must list every wrapper finding exactly once, in order"
        )
    current = report.current_revision.content
    try:
        content = RevisionContent(
            tenant_id=current.tenant_id,
            report_id=current.report_id,
            review_id=current.review_id,
            base_schema_id=current.base_schema_id,
            base_renderer_id=current.base_renderer_id,
            base_wrapper_sha256=current.base_wrapper_sha256,
            dispositions=dispositions,
            notes=notes,
        )
    except ValueError:
        raise InvalidRevisionContentError("the revision content is invalid") from None
    if len(revision_canonical_bytes(content)) > MAX_REVISION_BYTES:
        raise InvalidRevisionContentError("the revision content is too large")
    if content == current:
        raise InvalidTransitionError("revised content is identical to the current revision")
    revision = WrapperRevision.create(
        revision_number=len(report.revisions) + 1,
        content=content,
        created_by=ctx.actor_id,
        created_at=now,
    )
    return _rebuild(report, status=ReportStatus.DRAFT, revisions=(*report.revisions, revision))


def approve(
    report: WrapperReport,
    ctx: ActorContext,
    *,
    revision_number: int,
    content_sha256: str,
    now: datetime,
    comment: str | None = None,
) -> WrapperReport:
    """Approve the exact current revision. An identical retry returns the same report."""
    report = _require_report(report)
    _require_tenant(report.tenant_id, ctx)
    _require_role(ctx, _APPROVERS, "approve")
    _require_not_finalized(report, "approve")
    _require_exact_current(report, revision_number, content_sha256)
    _require_not_author(report, ctx)
    decision = WrapperApprovalDecision(
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
    report: WrapperReport,
    ctx: ActorContext,
    *,
    revision_number: int,
    content_sha256: str,
    now: datetime,
    comment: str,
) -> WrapperReport:
    """Reject the exact current revision, removing any effective approval."""
    report = _require_report(report)
    _require_tenant(report.tenant_id, ctx)
    _require_role(ctx, _APPROVERS, "reject")
    _require_not_finalized(report, "reject")
    _require_exact_current(report, revision_number, content_sha256)
    _require_not_author(report, ctx)
    decision = WrapperApprovalDecision(
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


def finalize(
    report: WrapperReport,
    ctx: ActorContext,
    *,
    revision_number: int,
    content_sha256: str,
    now: datetime,
) -> WrapperReport:
    """Finalize the exact current revision, which must carry the effective approval."""
    report = _require_report(report)
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
    _require_not_author(report, ctx)
    if report.effective_approval is None:
        raise InvalidTransitionError("finalizing requires an approval of the current revision")
    finalization = WrapperFinalization(
        tenant_id=report.tenant_id,
        report_id=report.report_id,
        revision_number=revision_number,
        content_sha256=content_sha256,
        finalized_by=ctx.actor_id,
        finalized_at=now,
    )
    return _rebuild(report, status=ReportStatus.FINALIZED, finalization=finalization)


def exportable_revision(report: WrapperReport, ctx: ActorContext) -> WrapperRevision:
    """The finalized revision to export, or ``NotExportableError``."""
    report = _require_report(report)
    _require_tenant(report.tenant_id, ctx)
    _require_role(ctx, _EDITORS, "export")
    if report.status is not ReportStatus.FINALIZED:
        raise NotExportableError("only finalized reports can be exported")
    return report.current_revision
