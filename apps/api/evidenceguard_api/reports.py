"""Report approval-gate and export endpoints (M6, ADR-0028).

- ``GET /v1/reports/{report_id}`` returns the report (``report_id`` is the review ID), creating
  it from the stored review output on first access.
- ``POST /v1/reports/{report_id}/revisions`` adds a revision (201). It requires exactly one
  ``If-Match: "r{n}-{sha256}"`` naming the current revision: missing is 428, malformed is 422,
  a stale number or hash is 409.
- ``POST /v1/reports/{report_id}/approval`` approves or rejects the exact current revision.
- ``POST /v1/reports/{report_id}/finalize`` finalizes the exact current, approved revision.
- ``GET /v1/reports/{report_id}/export?format=md|json`` downloads a finalized report rendered
  from its stored bytes, and records the export in the audit log before responding.

Every successful response carries a strong ``ETag`` ``"r{n}-{sha256}"`` of the current revision.
The tenant always comes from the API key. Reviewers and approvers may read, revise and export;
only approvers may approve, reject or finalize, and never a revision they authored (409).
Administrators get 403 on every route. Another tenant's report, an unknown review and a review
without output are 404. Database, configuration and stored-record failures are a generic 503.
"""

import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any, Literal, Protocol, Self
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy.exc import SQLAlchemyError

from evidenceguard_agents.report_export import render_export_json, render_export_markdown
from evidenceguard_api.auth import authenticated_actor
from evidenceguard_api.database import AppDatabase
from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_domain.errors import (
    ContentHashMismatchError,
    InvalidTransitionError,
    PermissionDeniedError,
    StaleRevisionError,
    TenantMismatchError,
)
from evidenceguard_domain.report import Decision
from evidenceguard_domain.review_report_approval import (
    Disposition,
    ExportInput,
    ExportResult,
    FindingDisposition,
    InvalidRevisionContentError,
)
from evidenceguard_domain.reviews import ReviewNotFoundError
from evidenceguard_persistence import reports as store
from evidenceguard_persistence.review_outputs import (
    ReviewOutputDatabaseError,
    ReviewOutputNotFoundError,
    ReviewOutputRecordInconsistentError,
)
from evidenceguard_persistence.settings import DatabaseConfigurationError

READER_ROLES = frozenset({Role.REVIEWER, Role.APPROVER})
IF_MATCH = re.compile(r'"r([1-9][0-9]{0,2})-([0-9a-f]{64})"\Z')
SHA256_PATTERN = r"^[0-9a-f]{64}$"
MAX_IF_MATCH_LENGTH = 128

_PROBLEM: dict[str, Any] = {"application/problem+json": {}}
_ETAG = {"ETag": {"description": 'The current revision, as "r{n}-{sha256}".'}}


# --- request and response models -----------------------------------------------------------------


def _no_null(value: str | None) -> str | None:
    if value is not None and "\x00" in value:
        raise ValueError("text must not contain a null character")
    return value


class DispositionIn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    finding_id: UUID
    disposition: Literal["open", "accepted", "dismissed"]
    note: str | None = Field(default=None, min_length=1, max_length=2000)

    @model_validator(mode="after")
    def _check(self) -> Self:
        _no_null(self.note)
        if self.disposition == "dismissed" and self.note is None:
            raise ValueError("a dismissal requires a note")
        return self


class ReportRevise(BaseModel):
    """A new revision: one disposition per wrapper finding, in wrapper order, and notes."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    dispositions: list[DispositionIn] = Field(max_length=200)
    notes: str | None = Field(default=None, min_length=1, max_length=4000)
    reason: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def _check(self) -> Self:
        _no_null(self.notes)
        _no_null(self.reason)
        return self


class ApprovalRequest(BaseModel):
    """Approve or reject the exact current revision. A rejection requires a comment."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    revision_no: int = Field(ge=1, le=100)
    content_sha256: str = Field(pattern=SHA256_PATTERN)
    decision: Literal["approve", "reject"]
    comment: str | None = Field(default=None, min_length=1, max_length=2000)

    @model_validator(mode="after")
    def _check(self) -> Self:
        _no_null(self.comment)
        if self.decision == "reject" and self.comment is None:
            raise ValueError("a rejection requires a comment")
        return self


class FinalizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    revision_no: int = Field(ge=1, le=100)
    content_sha256: str = Field(pattern=SHA256_PATTERN)


class FindingView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    finding_id: UUID
    title: str
    severity: str
    evidence_status: str
    question_ids: list[str]
    disposition: Literal["open", "accepted", "dismissed"]
    note: str | None


class DecisionView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    decision: Literal["approve", "reject"]
    revision_no: int
    content_sha256: str
    decided_by: UUID
    decided_at: datetime
    comment: str | None


class FinalizationView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    revision_no: int
    content_sha256: str
    finalized_by: UUID
    finalized_at: datetime


class ReportView(BaseModel):
    """The report's current revision over its hash-bound review output."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    report_id: UUID
    review_id: UUID
    status: Literal["draft", "changes_requested", "approved", "finalized"]
    revision_no: int
    content_sha256: str
    wrapper_sha256: str
    findings: list[FindingView]
    notes: str | None
    unresolved_question_ids: list[str]
    approval: DecisionView | None = Field(
        description="The latest decision on the current revision, if any."
    )
    finalization: FinalizationView | None


# --- store ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ReportExport:
    body: bytes
    media_type: str
    revision_no: int
    etag: str


class ReportStore(Protocol):
    def load(self, actor: ActorContext, report_id: UUID) -> store.ReportState: ...

    def revise(
        self,
        actor: ActorContext,
        report_id: UUID,
        *,
        expected_revision_number: int,
        expected_sha256: str,
        dispositions: tuple[FindingDisposition, ...],
        notes: str | None,
        reason: str | None,
    ) -> store.ReportState: ...

    def decide(
        self,
        actor: ActorContext,
        report_id: UUID,
        *,
        revision_number: int,
        content_sha256: str,
        decision: Decision,
        comment: str | None,
    ) -> store.ReportState: ...

    def finalize(
        self, actor: ActorContext, report_id: UUID, *, revision_number: int, content_sha256: str
    ) -> store.ReportState: ...

    def export(
        self, actor: ActorContext, report_id: UUID, *, export_format: Literal["md", "json"]
    ) -> ReportExport: ...


class DatabaseReportStore:
    """Report operations on the app's shared database (``evidenceguard_persistence.reports``)."""

    def __init__(self, database: AppDatabase) -> None:
        self._database = database

    def load(self, actor: ActorContext, report_id: UUID) -> store.ReportState:
        return store.load_report(self._database.session_factory(), actor, report_id)

    def revise(
        self,
        actor: ActorContext,
        report_id: UUID,
        *,
        expected_revision_number: int,
        expected_sha256: str,
        dispositions: tuple[FindingDisposition, ...],
        notes: str | None,
        reason: str | None,
    ) -> store.ReportState:
        return store.revise_report(
            self._database.session_factory(),
            actor,
            report_id,
            expected_revision_number=expected_revision_number,
            expected_sha256=expected_sha256,
            dispositions=dispositions,
            notes=notes,
            reason=reason,
        )

    def decide(
        self,
        actor: ActorContext,
        report_id: UUID,
        *,
        revision_number: int,
        content_sha256: str,
        decision: Decision,
        comment: str | None,
    ) -> store.ReportState:
        return store.decide_report(
            self._database.session_factory(),
            actor,
            report_id,
            revision_number=revision_number,
            content_sha256=content_sha256,
            decision=decision,
            comment=comment,
        )

    def finalize(
        self, actor: ActorContext, report_id: UUID, *, revision_number: int, content_sha256: str
    ) -> store.ReportState:
        return store.finalize_report(
            self._database.session_factory(),
            actor,
            report_id,
            revision_number=revision_number,
            content_sha256=content_sha256,
        )

    def export(
        self, actor: ActorContext, report_id: UUID, *, export_format: Literal["md", "json"]
    ) -> ReportExport:
        renderer = render_export_markdown if export_format == "md" else render_export_json
        seen: list[ExportInput] = []

        def render(i: ExportInput) -> ExportResult:
            seen.append(i)
            return renderer(i)

        result = store.export_report(
            self._database.session_factory(),
            actor,
            report_id,
            export_format=export_format,
            render=render,
        )
        revision = seen[0].revision
        return ReportExport(
            body=result.body,
            media_type=result.media_type,
            revision_no=revision.revision_number,
            etag=f'"r{revision.revision_number}-{revision.content_sha256}"',
        )


# --- dependencies and error mapping --------------------------------------------------------------


def report_reader(actor: Annotated[ActorContext, Depends(authenticated_actor)]) -> ActorContext:
    """Authenticated (401) and a reviewer or approver (generic 403 otherwise)."""
    if actor.role not in READER_ROLES:
        raise HTTPException(status_code=403)
    return actor


def report_approver(actor: Annotated[ActorContext, Depends(authenticated_actor)]) -> ActorContext:
    """Authenticated (401) and an approver (generic 403 otherwise)."""
    if actor.role is not Role.APPROVER:
        raise HTTPException(status_code=403)
    return actor


def _store(request: Request) -> ReportStore:
    report_store: ReportStore = request.app.state.report_store
    return report_store


@contextmanager
def _mapped_errors() -> Iterator[None]:
    try:
        yield
    except (
        TenantMismatchError,
        store.ReportNotFoundError,
        ReviewNotFoundError,
        ReviewOutputNotFoundError,
    ):
        raise HTTPException(status_code=404) from None
    except PermissionDeniedError:
        raise HTTPException(status_code=403) from None
    except (StaleRevisionError, ContentHashMismatchError, InvalidTransitionError):
        raise HTTPException(status_code=409) from None
    except InvalidRevisionContentError:
        raise HTTPException(status_code=422) from None
    except (
        ReviewOutputRecordInconsistentError,
        store.ReportRecordInconsistentError,
        ReviewOutputDatabaseError,
        DatabaseConfigurationError,
        SQLAlchemyError,
    ):
        raise HTTPException(status_code=503) from None


def _call[T](operation: Callable[[], T]) -> T:
    with _mapped_errors():
        return operation()


def _if_match(request: Request) -> tuple[int, str]:
    values = [
        value for name, value in request.scope.get("headers", []) if name.lower() == b"if-match"
    ]
    if not values:
        raise HTTPException(status_code=428)
    if len(values) != 1 or len(values[0]) > MAX_IF_MATCH_LENGTH:
        raise HTTPException(status_code=422)
    try:
        raw = values[0].decode("ascii").strip()
    except UnicodeDecodeError:
        raise HTTPException(status_code=422) from None
    match = IF_MATCH.match(raw)
    if match is None:
        raise HTTPException(status_code=422)
    return int(match.group(1)), match.group(2)


def _view(state: store.ReportState) -> ReportView:
    report = state.report
    current = report.current_revision
    by_id = {d.finding_id: d for d in current.content.dispositions}
    findings = [
        FindingView(
            finding_id=f.finding_id,
            title=f.title,
            severity=f.severity.value,
            evidence_status=f.evidence_status.value,
            question_ids=list(f.question_ids),
            disposition=by_id[f.finding_id].disposition.value,
            note=by_id[f.finding_id].note,
        )
        for f in state.wrapper.content.findings
    ]
    latest = report.decisions[-1] if report.decisions else None
    approval = None
    if latest is not None and latest.revision_number == current.revision_number:
        approval = DecisionView(
            decision=latest.decision.value,
            revision_no=latest.revision_number,
            content_sha256=latest.content_sha256,
            decided_by=latest.decided_by,
            decided_at=latest.decided_at,
            comment=latest.comment,
        )
    final = report.finalization
    return ReportView(
        report_id=report.report_id,
        review_id=report.review_id,
        status=report.status.value,
        revision_no=current.revision_number,
        content_sha256=current.content_sha256,
        wrapper_sha256=state.wrapper_sha256,
        findings=findings,
        notes=current.content.notes,
        unresolved_question_ids=list(state.wrapper.content.unresolved_question_ids),
        approval=approval,
        finalization=None
        if final is None
        else FinalizationView(
            revision_no=final.revision_number,
            content_sha256=final.content_sha256,
            finalized_by=final.finalized_by,
            finalized_at=final.finalized_at,
        ),
    )


def _respond(state: store.ReportState, response: Response) -> ReportView:
    response.headers["ETag"] = state.etag
    response.headers["Cache-Control"] = "no-store"
    return _view(state)


# --- routes --------------------------------------------------------------------------------------

router = APIRouter(
    prefix="/v1/reports",
    tags=["reports"],
    responses={
        401: {
            "description": "Missing, malformed, unknown or revoked credentials.",
            "content": _PROBLEM,
        },
        403: {"description": "The caller's role may not perform this action.", "content": _PROBLEM},
        404: {
            "description": "No such review with a stored output in the caller's tenant.",
            "content": _PROBLEM,
        },
        422: {"description": "Invalid path, query, header or body.", "content": _PROBLEM},
        503: {
            "description": "The database or a stored record is unavailable.",
            "content": _PROBLEM,
        },
    },
)

_CONFLICT: dict[int | str, dict[str, Any]] = {
    409: {
        "description": (
            "Stale revision or hash, finalized report, separation of duties, or a conflicting "
            "or invalid transition."
        ),
        "content": _PROBLEM,
    }
}


@router.get(
    "/{report_id}",
    response_model=ReportView,
    summary="Get a report",
    description=(
        "Returns the report for a completed review (the report ID is the review ID), creating "
        "revision 1 from the stored review output on first access."
    ),
    responses={200: {"headers": _ETAG}},
)
def get_report(
    report_id: UUID,
    request: Request,
    response: Response,
    actor: Annotated[ActorContext, Depends(report_reader)],
) -> ReportView:
    state = _call(lambda: _store(request).load(actor, report_id))
    return _respond(state, response)


@router.post(
    "/{report_id}/revisions",
    status_code=201,
    response_model=ReportView,
    summary="Revise a report",
    description=(
        "Adds a revision with one disposition per finding, in report order. Requires exactly "
        'one If-Match header "r{n}-{sha256}" naming the current revision. A new revision '
        "returns the report to draft; earlier approvals no longer count."
    ),
    responses={
        201: {"headers": _ETAG},
        **_CONFLICT,
        428: {"description": "The If-Match header is missing.", "content": _PROBLEM},
    },
)
def revise_report(
    report_id: UUID,
    body: ReportRevise,
    request: Request,
    response: Response,
    actor: Annotated[ActorContext, Depends(report_reader)],
    if_match: Annotated[
        str | None,
        Header(
            alias="If-Match", description='Exactly one "r{n}-{sha256}" of the current revision.'
        ),
    ] = None,
) -> ReportView:
    del if_match  # documented here; parsed from the raw headers so duplicates are refused
    number, sha = _if_match(request)
    try:
        dispositions = tuple(
            FindingDisposition(
                finding_id=d.finding_id, disposition=Disposition(d.disposition), note=d.note
            )
            for d in body.dispositions
        )
    except ValidationError:
        raise HTTPException(status_code=422) from None
    state = _call(
        lambda: _store(request).revise(
            actor,
            report_id,
            expected_revision_number=number,
            expected_sha256=sha,
            dispositions=dispositions,
            notes=body.notes,
            reason=body.reason,
        )
    )
    return _respond(state, response)


@router.post(
    "/{report_id}/approval",
    response_model=ReportView,
    summary="Approve or reject a revision",
    description=(
        "Approves or rejects the exact current revision and hash. Approvers only, and never "
        "for a revision they authored. An identical repeated request changes nothing."
    ),
    responses={200: {"headers": _ETAG}, **_CONFLICT},
)
def decide_report(
    report_id: UUID,
    body: ApprovalRequest,
    request: Request,
    response: Response,
    actor: Annotated[ActorContext, Depends(report_approver)],
) -> ReportView:
    state = _call(
        lambda: _store(request).decide(
            actor,
            report_id,
            revision_number=body.revision_no,
            content_sha256=body.content_sha256,
            decision=Decision(body.decision),
            comment=body.comment,
        )
    )
    return _respond(state, response)


@router.post(
    "/{report_id}/finalize",
    response_model=ReportView,
    summary="Finalize a report",
    description=(
        "Finalizes the exact current revision, which must carry the effective approval. "
        "Approvers only, and never for a revision they authored. Repeating it changes nothing."
    ),
    responses={200: {"headers": _ETAG}, **_CONFLICT},
)
def finalize_report(
    report_id: UUID,
    body: FinalizeRequest,
    request: Request,
    response: Response,
    actor: Annotated[ActorContext, Depends(report_approver)],
) -> ReportView:
    state = _call(
        lambda: _store(request).finalize(
            actor, report_id, revision_number=body.revision_no, content_sha256=body.content_sha256
        )
    )
    return _respond(state, response)


@router.get(
    "/{report_id}/export",
    summary="Export a finalized report",
    description=(
        "Downloads a finalized report as Markdown or canonical JSON, rendered from the stored "
        "revision and review-output bytes. The export's format and SHA-256 are recorded in the "
        "audit log before the response is sent."
    ),
    response_class=Response,
    responses={
        200: {
            "description": "The export file.",
            "headers": _ETAG,
            "content": {"text/markdown": {}, "application/json": {}},
        },
        409: {"description": "The report is not finalized.", "content": _PROBLEM},
    },
)
def export_report(
    report_id: UUID,
    request: Request,
    actor: Annotated[ActorContext, Depends(report_reader)],
    export_format: Annotated[Literal["md", "json"], Query(alias="format")],
) -> Response:
    exported = _call(lambda: _store(request).export(actor, report_id, export_format=export_format))
    filename = f"report-{report_id}-r{exported.revision_no}.{export_format}"
    return Response(
        content=exported.body,
        media_type=exported.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "ETag": exported.etag,
            "Cache-Control": "no-store",
        },
    )
