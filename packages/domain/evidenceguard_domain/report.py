"""Immutable report revisions, content hashing and the report aggregate.

What is hashed
--------------
``content_sha256`` is the SHA-256 hex digest of UTF-8 bytes produced as follows:

1. ``ReportContent.model_dump(mode="json")``: UUIDs become strings, enums their values,
   tuples JSON arrays (array order is meaningful and kept).
2. Wrap it as ``{"schema": "evidenceguard.report-content.v1", "content": <step 1>}``.
3. ``json.dumps`` with ``sort_keys=True``, ``separators=(",", ":")``, ``ensure_ascii=False``
   and ``allow_nan=False``.

Object keys are sorted, so the digest does not depend on dict insertion order. Strings are
whitespace-stripped during validation, so surrounding padding is not substantive. Report ID,
revision number, author, timestamps and approval decisions are **not** part of the content;
decisions bind to them separately.
"""

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, PositiveInt, StringConstraints, model_validator

from evidenceguard_domain._base import DomainModel
from evidenceguard_domain.evidence import LongText, ReportContent

CONTENT_HASH_SCHEMA = "evidenceguard.report-content.v1"

Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


def canonical_content_bytes(content: ReportContent) -> bytes:
    """Return the exact bytes that ``content_sha256`` hashes (see module docstring)."""
    payload = {"schema": CONTENT_HASH_SCHEMA, "content": content.model_dump(mode="json")}
    text = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return text.encode("utf-8")


def content_sha256(content: ReportContent) -> str:
    return hashlib.sha256(canonical_content_bytes(content)).hexdigest()


class ReportStatus(StrEnum):
    DRAFT = "draft"
    CHANGES_REQUESTED = "changes_requested"
    APPROVED = "approved"
    FINALIZED = "finalized"


class Decision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


class ReportRevision(DomainModel):
    """One immutable version of a report's content. The stored hash must match the content."""

    report_id: UUID
    revision_number: PositiveInt
    content: ReportContent
    content_sha256: Sha256Hex
    created_by: UUID
    created_at: AwareDatetime

    @model_validator(mode="after")
    def _check_hash(self) -> Self:
        if self.content_sha256 != content_sha256(self.content):
            raise ValueError("content_sha256 does not match the revision content")
        return self

    @classmethod
    def create(
        cls,
        *,
        report_id: UUID,
        revision_number: int,
        content: ReportContent,
        created_by: UUID,
        created_at: datetime,
    ) -> Self:
        return cls(
            report_id=report_id,
            revision_number=revision_number,
            content=content,
            content_sha256=content_sha256(content),
            created_by=created_by,
            created_at=created_at,
        )


class ApprovalDecision(DomainModel):
    """An approver's decision, bound to one tenant, report, revision number and content hash.

    A rejection must explain itself: ``comment`` is required (and non-blank) for ``reject``.
    """

    tenant_id: UUID
    report_id: UUID
    revision_number: PositiveInt
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

    def same_request_as(self, other: "ApprovalDecision") -> bool:
        """True when ``other`` repeats this decision: same decision, binding, actor and comment.

        The timestamp is ignored, so a retry keeps the original decision time.
        """
        return (
            self.decision is other.decision
            and self.tenant_id == other.tenant_id
            and self.report_id == other.report_id
            and self.revision_number == other.revision_number
            and self.content_sha256 == other.content_sha256
            and self.decided_by == other.decided_by
            and self.comment == other.comment
        )


class Finalization(DomainModel):
    """Record that one exact approved revision was finalized."""

    tenant_id: UUID
    report_id: UUID
    revision_number: PositiveInt
    content_sha256: Sha256Hex
    finalized_by: UUID
    finalized_at: AwareDatetime


class Report(DomainModel):
    """A report, its revision history and its approval history.

    ``status`` is stored but must equal the status derived from the history, so a report
    cannot be built as approved or finalized without the matching decision or finalization.
    """

    tenant_id: UUID
    report_id: UUID
    status: ReportStatus
    revisions: Annotated[tuple[ReportRevision, ...], Field(min_length=1)]
    decisions: tuple[ApprovalDecision, ...] = ()
    finalization: Finalization | None = None

    @property
    def current_revision(self) -> ReportRevision:
        return self.revisions[-1]

    @property
    def effective_approval(self) -> ApprovalDecision | None:
        """The approval that currently counts: the latest decision, if it approves the current
        revision and hash. A later revision or rejection means there is none."""
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
    ) -> None:
        if tenant_id != self.tenant_id:
            raise ValueError(f"{kind} belongs to another tenant")
        if report_id != self.report_id:
            raise ValueError(f"{kind} belongs to another report")
        if not 1 <= revision_number <= len(self.revisions):
            raise ValueError(f"{kind} refers to an unknown revision")
        if sha != self.revisions[revision_number - 1].content_sha256:
            raise ValueError(f"{kind} hash does not match revision {revision_number}")

    @model_validator(mode="after")
    def _check_history(self) -> Self:
        for number, revision in enumerate(self.revisions, start=1):
            if revision.revision_number != number:
                raise ValueError("revisions must be numbered 1..n in order")
            if revision.report_id != self.report_id:
                raise ValueError("revision belongs to another report")
            if revision.content.tenant_id != self.tenant_id:
                raise ValueError("revision content belongs to another tenant")

        previous = 0
        for decision in self.decisions:
            self._check_binding(
                "decision",
                decision.tenant_id,
                decision.report_id,
                decision.revision_number,
                decision.content_sha256,
            )
            if decision.revision_number < previous:
                raise ValueError("decisions must follow revision order")
            previous = decision.revision_number

        if self.finalization is not None:
            final = self.finalization
            self._check_binding(
                "finalization",
                final.tenant_id,
                final.report_id,
                final.revision_number,
                final.content_sha256,
            )
            approval = self.effective_approval
            if approval is None or approval.revision_number != final.revision_number:
                raise ValueError("finalization requires an approval of the current revision")

        expected = self._derived_status()
        if self.status is not expected:
            raise ValueError(
                f"status {self.status.value!r} does not match history ({expected.value!r})"
            )
        return self
