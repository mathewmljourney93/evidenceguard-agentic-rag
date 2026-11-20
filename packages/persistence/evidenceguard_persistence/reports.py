"""Report persistence: lazy creation, compare-and-set mutations, export and audit (M6, ADR-0028).

Identity and creation
---------------------
A report's ID equals its review's ID (a CHECK enforces it). The report is created lazily, on the
first access through any report operation, from the write-once ``review_outputs`` row: first
``load_review_output`` runs the full M5g read checks, then, inside the operation's own
transaction, the output row is re-read ``FOR SHARE`` and must carry the same wrapper digest.
Revision 1 is a pure function of that row, so every creator produces the same revision bytes;
``INSERT ... ON CONFLICT DO NOTHING`` makes creation idempotent and race-safe. When the report
already exists no stage or plan row is read.

Mutations
---------
Each mutation is one transaction: create if absent, ``SELECT ... FOR UPDATE`` on ``reports``,
rebuild the ``WrapperReport`` from its rows (decoding every stored revision against its digest
and the wrapper against the report's base digest), apply the pure transition, insert the new
history rows, update the report's status and current-revision pointers and insert one audit
event. An identical retry returns the unchanged report and writes nothing. Times come from the
database clock (``clock_timestamp()``).

Reads
-----
``load_report`` reads in one REPEATABLE READ, READ ONLY snapshot after the optional creation.
``export_report`` reads only report, revision, decision, finalization and output rows, calls the
supplied ``render`` callback (the persistence package may not import the renderers) and records
the export's format and body digest in the same transaction, committed before it returns.

Every operation checks the actor's role against ``READ_ROLES`` before any SQL and filters every
query by the actor's tenant. Rows that do not rebuild into a valid report raise
``ReportRecordInconsistentError``.
"""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, cast
from uuid import UUID

from sqlalchemy import Table, func, insert, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, sessionmaker

from evidenceguard_domain.context import ActorContext
from evidenceguard_domain.errors import PermissionDeniedError
from evidenceguard_domain.report import Decision, ReportStatus
from evidenceguard_domain.report_content import ReviewReportContent, decode_review_report
from evidenceguard_domain.review_outputs import StoredReviewOutput
from evidenceguard_domain.review_report_approval import (
    ExportInput,
    ExportResult,
    FindingDisposition,
    WrapperApprovalDecision,
    WrapperFinalization,
    WrapperReport,
    WrapperRevision,
    approve,
    decode_revision_content,
    exportable_revision,
    finalize,
    open_report,
    reject,
    revise,
    revision_canonical_bytes,
)
from evidenceguard_persistence.db import transaction
from evidenceguard_persistence.document_views import read_snapshot
from evidenceguard_persistence.models import (
    AuditEvent,
    ReportDecisionRow,
    ReportFinalizationRow,
    ReportRevisionRow,
    ReportRow,
    ReviewOutputRow,
)
from evidenceguard_persistence.review_outputs import (
    READ_ROLES,
    ReviewOutputRecordInconsistentError,
    load_review_output,
)

__all__ = [
    "ExportInput",
    "ExportResult",
    "ReportNotFoundError",
    "ReportRecordInconsistentError",
    "ReportState",
    "decide_report",
    "export_report",
    "finalize_report",
    "load_report",
    "revise_report",
]

REPORTS = cast(Table, ReportRow.__table__)
REVISIONS = cast(Table, ReportRevisionRow.__table__)
DECISIONS = cast(Table, ReportDecisionRow.__table__)
FINALIZATIONS = cast(Table, ReportFinalizationRow.__table__)
AUDIT = cast(Table, AuditEvent.__table__)
OUTPUTS = cast(Table, ReviewOutputRow.__table__)

STATEMENT_TIMEOUT_MS = 30_000
"""Per statement, transaction-local (as in ``review_outputs``), including row-lock waits."""

ExportFormat = Literal["md", "json"]


class ReportNotFoundError(Exception):
    """The report does not exist in the actor's tenant (another tenant's is indistinguishable)."""

    def __init__(self) -> None:
        super().__init__("the report was not found")


class ReportRecordInconsistentError(Exception):
    """Stored report rows do not rebuild into a valid report bound to its stored output."""

    def __init__(self) -> None:
        super().__init__("the stored report is inconsistent")


@dataclass(frozen=True)
class ReportState:
    """A report rebuilt from its rows, with the wrapper decoded from its stored bytes."""

    report: WrapperReport
    wrapper: ReviewReportContent
    wrapper_sha256: str

    @property
    def etag(self) -> str:
        current = self.report.current_revision
        return f'"r{current.revision_number}-{current.content_sha256}"'


# --- helpers -------------------------------------------------------------------------------------


def _require_reader(actor: ActorContext) -> None:
    if actor.role not in READ_ROLES:
        raise PermissionDeniedError()


def _timeout(session: Session) -> None:
    session.execute(text(f"SET LOCAL statement_timeout = {int(STATEMENT_TIMEOUT_MS)}"))


def _now(session: Session) -> datetime:
    now: datetime = session.execute(select(func.clock_timestamp())).scalar_one()
    return now


def _report_exists(
    session_factory: sessionmaker[Session], tenant_id: UUID, report_id: UUID
) -> bool:
    with read_snapshot(session_factory) as (session, _now_unused):
        _timeout(session)
        found = session.execute(
            select(REPORTS.c.id).where(REPORTS.c.tenant_id == tenant_id, REPORTS.c.id == report_id)
        ).first()
    return found is not None


def _source(
    session_factory: sessionmaker[Session], actor: ActorContext, report_id: UUID
) -> StoredReviewOutput | None:
    """The stored output to create the report from, or ``None`` when the report exists.
    ``load_review_output`` raises its own not-found, inconsistency and database errors."""
    if _report_exists(session_factory, actor.tenant_id, report_id):
        return None
    return load_review_output(session_factory, actor, report_id)


def _create_if_absent(session: Session, stored: StoredReviewOutput) -> None:
    output = stored.output
    locked = session.execute(
        select(OUTPUTS.c.wrapper_sha256)
        .where(OUTPUTS.c.tenant_id == output.tenant_id, OUTPUTS.c.review_id == output.review_id)
        .with_for_update(read=True)
    ).first()
    if locked is None or locked.wrapper_sha256 != output.wrapper_sha256:
        raise ReviewOutputRecordInconsistentError()
    report = open_report(output.content, wrapper_sha256=output.wrapper_sha256, now=_now(session))
    revision = report.current_revision
    created = session.execute(
        pg_insert(REPORTS)
        .values(
            tenant_id=report.tenant_id,
            id=report.report_id,
            review_id=report.review_id,
            base_schema_id=revision.content.base_schema_id,
            base_renderer_id=revision.content.base_renderer_id,
            base_wrapper_sha256=report.base_wrapper_sha256,
            status=report.status.value,
            current_revision_no=revision.revision_number,
            current_content_sha256=revision.content_sha256,
            created_at=revision.created_at,
            updated_at=revision.created_at,
        )
        # No conflict target: a simultaneous creator may meet either unique of ``reports`` first.
        .on_conflict_do_nothing()
        .returning(REPORTS.c.id)
    ).first()
    if created is not None:
        _insert_revision(session, report, revision, reason=None)


def _insert_revision(
    session: Session, report: WrapperReport, revision: WrapperRevision, *, reason: str | None
) -> None:
    session.execute(
        insert(REVISIONS).values(
            tenant_id=report.tenant_id,
            report_id=report.report_id,
            revision_no=revision.revision_number,
            schema_id=revision.schema_id,
            base_wrapper_sha256=report.base_wrapper_sha256,
            content_canonical=revision_canonical_bytes(revision.content).decode("ascii"),
            content_sha256=revision.content_sha256,
            origin="generated" if revision.created_by is None else "revised",
            created_by=revision.created_by,
            reason=reason,
            created_at=revision.created_at,
        )
    )


def _scope(table: Table, tenant_id: UUID, report_id: UUID) -> Any:
    return (table.c.tenant_id == tenant_id) & (table.c.report_id == report_id)


def _rebuild(session: Session, tenant_id: UUID, report_id: UUID, *, lock: bool) -> ReportState:
    """The report rebuilt from its rows (``FOR UPDATE`` on the report row when ``lock``)."""
    statement = select(REPORTS).where(REPORTS.c.tenant_id == tenant_id, REPORTS.c.id == report_id)
    row = session.execute(statement.with_for_update() if lock else statement).first()
    if row is None:
        raise ReportNotFoundError()
    output = session.execute(
        select(OUTPUTS.c.wrapper_canonical).where(
            OUTPUTS.c.tenant_id == tenant_id,
            OUTPUTS.c.review_id == row.review_id,
            OUTPUTS.c.wrapper_sha256 == row.base_wrapper_sha256,
        )
    ).first()
    revisions = session.execute(
        select(REVISIONS)
        .where(_scope(REVISIONS, tenant_id, report_id))
        .order_by(REVISIONS.c.revision_no)
    ).all()
    decisions = session.execute(
        select(DECISIONS)
        .where(_scope(DECISIONS, tenant_id, report_id))
        .order_by(DECISIONS.c.decision_no)
    ).all()
    final = session.execute(
        select(FINALIZATIONS).where(_scope(FINALIZATIONS, tenant_id, report_id))
    ).first()
    try:
        if output is None:
            raise ValueError("the report's output row is missing")
        wrapper = decode_review_report(
            output.wrapper_canonical.encode("ascii"), expected_sha256=row.base_wrapper_sha256
        )
        built: list[WrapperRevision] = []
        for r in revisions:
            if r.base_wrapper_sha256 != row.base_wrapper_sha256:
                raise ValueError("revision bound to another wrapper")
            if (r.origin == "generated") != (r.created_by is None):
                raise ValueError("revision origin and author disagree")
            content = decode_revision_content(
                r.content_canonical.encode("ascii"), expected_sha256=r.content_sha256
            )
            built.append(
                WrapperRevision(
                    schema_id=r.schema_id,
                    report_id=report_id,
                    revision_number=r.revision_no,
                    content=content,
                    content_sha256=r.content_sha256,
                    created_by=r.created_by,
                    created_at=r.created_at,
                )
            )
        for number, d in enumerate(decisions, start=1):
            if d.decision_no != number:
                raise ValueError("decision numbers have a gap")
        report = WrapperReport(
            tenant_id=tenant_id,
            report_id=report_id,
            review_id=row.review_id,
            base_wrapper_sha256=row.base_wrapper_sha256,
            finding_ids=tuple(f.finding_id for f in wrapper.content.findings),
            status=ReportStatus(row.status),
            revisions=tuple(built),
            decisions=tuple(
                WrapperApprovalDecision(
                    tenant_id=tenant_id,
                    report_id=report_id,
                    revision_number=d.revision_no,
                    content_sha256=d.content_sha256,
                    decision=Decision(d.decision),
                    decided_by=d.decided_by,
                    decided_at=d.decided_at,
                    comment=d.comment,
                )
                for d in decisions
            ),
            finalization=None
            if final is None
            else WrapperFinalization(
                tenant_id=tenant_id,
                report_id=report_id,
                revision_number=final.revision_no,
                content_sha256=final.content_sha256,
                finalized_by=final.finalized_by,
                finalized_at=final.finalized_at,
            ),
        )
        current = report.current_revision
        if (
            current.revision_number != row.current_revision_no
            or current.content_sha256 != row.current_content_sha256
            or (final is not None and final.decision_no != report.effective_approval_number)
        ):
            raise ValueError("report pointers disagree with the history")
    except ValueError:  # includes validation, decoding and encoding failures
        raise ReportRecordInconsistentError() from None
    return ReportState(report=report, wrapper=wrapper, wrapper_sha256=row.base_wrapper_sha256)


def _audit(
    session: Session,
    actor: ActorContext,
    report: WrapperReport,
    action: str,
    *,
    revision_number: int,
    content_sha256: str,
    now: datetime,
    export_format: str | None = None,
    export_sha256: str | None = None,
) -> None:
    session.execute(
        insert(AUDIT).values(
            tenant_id=report.tenant_id,
            report_id=report.report_id,
            action=action,
            actor_id=actor.actor_id,
            revision_no=revision_number,
            content_sha256=content_sha256,
            export_format=export_format,
            export_sha256=export_sha256,
            occurred_at=now,
        )
    )


def _persist(
    session: Session,
    old: WrapperReport,
    new: WrapperReport,
    *,
    reason: str | None = None,
) -> None:
    """Insert the history rows ``new`` adds to ``old`` and move the report's pointers."""
    for revision in new.revisions[len(old.revisions) :]:
        _insert_revision(session, new, revision, reason=reason)
    for number, decision in enumerate(new.decisions, start=1):
        if number <= len(old.decisions):
            continue
        session.execute(
            insert(DECISIONS).values(
                tenant_id=new.tenant_id,
                report_id=new.report_id,
                decision_no=number,
                revision_no=decision.revision_number,
                content_sha256=decision.content_sha256,
                decision=decision.decision.value,
                decided_by=decision.decided_by,
                comment=decision.comment,
                decided_at=decision.decided_at,
            )
        )
    if new.finalization is not None and old.finalization is None:
        final = new.finalization
        session.execute(
            insert(FINALIZATIONS).values(
                tenant_id=new.tenant_id,
                report_id=new.report_id,
                revision_no=final.revision_number,
                content_sha256=final.content_sha256,
                decision_no=new.effective_approval_number,
                finalized_by=final.finalized_by,
                finalized_at=final.finalized_at,
            )
        )
    current = new.current_revision
    session.execute(
        update(REPORTS)
        .where(REPORTS.c.tenant_id == new.tenant_id, REPORTS.c.id == new.report_id)
        .values(
            status=new.status.value,
            current_revision_no=current.revision_number,
            current_content_sha256=current.content_sha256,
            updated_at=func.clock_timestamp(),
        )
    )


def _mutate(
    session_factory: sessionmaker[Session],
    actor: ActorContext,
    report_id: UUID,
    change: Callable[[WrapperReport, datetime], WrapperReport],
    action: str,
    *,
    reason: str | None = None,
) -> ReportState:
    _require_reader(actor)
    stored = _source(session_factory, actor, report_id)
    with transaction(session_factory) as session:
        _timeout(session)
        if stored is not None:
            _create_if_absent(session, stored)
        state = _rebuild(session, actor.tenant_id, report_id, lock=True)
        now = _now(session)
        new = change(state.report, now)
        if new is state.report:  # an identical retry: nothing is written
            return state
        _persist(session, state.report, new, reason=reason)
        current = new.current_revision
        _audit(
            session,
            actor,
            new,
            action,
            revision_number=current.revision_number,
            content_sha256=current.content_sha256,
            now=now,
        )
    return ReportState(report=new, wrapper=state.wrapper, wrapper_sha256=state.wrapper_sha256)


# --- operations ----------------------------------------------------------------------------------


def load_report(
    session_factory: sessionmaker[Session], actor: ActorContext, report_id: UUID
) -> ReportState:
    """The report, created from the stored output on first access."""
    _require_reader(actor)
    stored = _source(session_factory, actor, report_id)
    if stored is not None:
        with transaction(session_factory) as session:
            _timeout(session)
            _create_if_absent(session, stored)
    with read_snapshot(session_factory) as (session, _now_unused):
        _timeout(session)
        return _rebuild(session, actor.tenant_id, report_id, lock=False)


def revise_report(
    session_factory: sessionmaker[Session],
    actor: ActorContext,
    report_id: UUID,
    *,
    expected_revision_number: int,
    expected_sha256: str,
    dispositions: tuple[FindingDisposition, ...],
    notes: str | None,
    reason: str | None,
) -> ReportState:
    """Add a revision if ``expected_*`` names the current one (compare-and-set)."""

    def change(report: WrapperReport, now: datetime) -> WrapperReport:
        return revise(
            report,
            actor,
            expected_revision_number=expected_revision_number,
            expected_sha256=expected_sha256,
            dispositions=dispositions,
            notes=notes,
            now=now,
        )

    return _mutate(session_factory, actor, report_id, change, "revise", reason=reason)


def decide_report(
    session_factory: sessionmaker[Session],
    actor: ActorContext,
    report_id: UUID,
    *,
    revision_number: int,
    content_sha256: str,
    decision: Decision,
    comment: str | None,
) -> ReportState:
    """Approve or reject the exact current revision."""

    def change(report: WrapperReport, now: datetime) -> WrapperReport:
        if decision is Decision.APPROVE:
            return approve(
                report,
                actor,
                revision_number=revision_number,
                content_sha256=content_sha256,
                now=now,
                comment=comment,
            )
        if comment is None:
            raise ValueError("a rejection requires a comment")
        return reject(
            report,
            actor,
            revision_number=revision_number,
            content_sha256=content_sha256,
            now=now,
            comment=comment,
        )

    return _mutate(session_factory, actor, report_id, change, decision.value)


def finalize_report(
    session_factory: sessionmaker[Session],
    actor: ActorContext,
    report_id: UUID,
    *,
    revision_number: int,
    content_sha256: str,
) -> ReportState:
    """Finalize the exact current, approved revision."""

    def change(report: WrapperReport, now: datetime) -> WrapperReport:
        return finalize(
            report, actor, revision_number=revision_number, content_sha256=content_sha256, now=now
        )

    return _mutate(session_factory, actor, report_id, change, "finalize")


def export_report(
    session_factory: sessionmaker[Session],
    actor: ActorContext,
    report_id: UUID,
    *,
    export_format: ExportFormat,
    render: Callable[[ExportInput], ExportResult],
) -> ExportResult:
    """Render a finalized report from its stored bytes and record the export in the audit log
    (format and SHA-256 of the exact body) in the same, committed transaction."""
    _require_reader(actor)
    if export_format not in ("md", "json"):
        raise ValueError("unsupported export format")
    stored = _source(session_factory, actor, report_id)
    with transaction(session_factory) as session:
        _timeout(session)
        if stored is not None:
            _create_if_absent(session, stored)
        state = _rebuild(session, actor.tenant_id, report_id, lock=False)
        report = state.report
        revision = exportable_revision(report, actor)
        approval = report.effective_approval
        finalization = report.finalization
        if approval is None or finalization is None:  # guaranteed by the aggregate
            raise ReportRecordInconsistentError()
        result = render(
            ExportInput(
                report=report,
                wrapper=state.wrapper,
                wrapper_sha256=state.wrapper_sha256,
                revision=revision,
                approval=approval,
                finalization=finalization,
            )
        )
        digest = hashlib.sha256(result.body).hexdigest()
        if digest != result.export_sha256:
            raise ValueError("the rendered export digest does not match its body")
        _audit(
            session,
            actor,
            report,
            "export",
            revision_number=revision.revision_number,
            content_sha256=revision.content_sha256,
            now=_now(session),
            export_format=export_format,
            export_sha256=digest,
        )
    return result
