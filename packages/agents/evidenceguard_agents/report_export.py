"""Finalized-report export renderers (M6, ADR-0028).

Pure functions over an ``ExportInput`` that persistence built from stored, digest-checked bytes:
the finalized revision and the M5f wrapper. No database, clock, network or randomness. Every
reviewer-supplied value (dispositions, notes) and every identifier is emitted as an escaped JSON
literal, as ``render_report_markdown`` does, so no submitted text becomes Markdown or HTML.
"""

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from evidenceguard_agents.report import render_report_markdown
from evidenceguard_domain.report_content import RENDERER, SCHEMA, review_report_bytes
from evidenceguard_domain.review_report_approval import (
    REVISION_SCHEMA,
    ExportInput,
    ExportResult,
    revision_canonical_bytes,
)

__all__ = [
    "EXPORT_DISCLAIMER",
    "EXPORT_JSON_SCHEMA",
    "EXPORT_MD_RENDERER",
    "JSON_MEDIA_TYPE",
    "MARKDOWN_MEDIA_TYPE",
    "render_export_json",
    "render_export_markdown",
]

EXPORT_MD_RENDERER = "evidenceguard.report-export-markdown.v1"
EXPORT_JSON_SCHEMA = "evidenceguard.report-export.v1"
MARKDOWN_MEDIA_TYPE = "text/markdown; charset=utf-8"
JSON_MEDIA_TYPE = "application/json"
EXPORT_DISCLAIMER = (
    "AI-assisted review output, finalized by a human approver. Citations prove provenance "
    "only (the quoted text exists in the cited document revision); they do not prove that the "
    "text entails the finding, nor that the document is authentic. This export is not legal "
    "advice and not a certification."
)


def _scalar(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if type(value) is UUID:
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _literal(value: Any) -> str:
    """The same escaped JSON literal ``render_report_markdown`` emits for every field."""
    literal = json.dumps(_scalar(value), ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    for char, escape in (("<", r"\u003c"), (">", r"\u003e"), ("&", r"\u0026")):
        literal = literal.replace(char, escape)
    return literal


def _binding(i: ExportInput) -> list[tuple[str, Any]]:
    revision = i.revision
    return [
        ("Export renderer", EXPORT_MD_RENDERER),
        ("Report ID", i.report.report_id),
        ("Review ID", i.report.review_id),
        ("Revision number", revision.revision_number),
        ("Revision schema", REVISION_SCHEMA),
        ("Revision SHA-256", revision.content_sha256),
        ("Wrapper schema", SCHEMA),
        ("Wrapper renderer", RENDERER),
        ("Wrapper SHA-256", i.wrapper_sha256),
        ("Approved by", i.approval.decided_by),
        ("Approved at", i.approval.decided_at),
        ("Finalized by", i.finalization.finalized_by),
        ("Finalized at", i.finalization.finalized_at),
    ]


def render_export_markdown(i: ExportInput) -> ExportResult:
    """Header with the binding, the disclaimer, dispositions and notes, then the M5f report."""
    lines: list[str] = ["# EvidenceGuard finalized report export", ""]

    def field(label: str, value: Any) -> None:
        lines.extend((label + ":", "", "    " + _literal(value), ""))

    lines.extend(("## Binding", ""))
    for label, value in _binding(i):
        field(label, value)
    lines.extend(("## Disclaimer", "", EXPORT_DISCLAIMER, ""))
    content = i.revision.content
    lines.extend(("## Dispositions", ""))
    field("Count", len(content.dispositions))
    for number, item in enumerate(content.dispositions, start=1):
        lines.extend((f"### Disposition {number}", ""))
        field("Finding ID", item.finding_id)
        field("Disposition", item.disposition)
        field("Note (JSON literal; decode once for original text)", item.note)
    lines.extend(("## Report notes", ""))
    field("Notes (JSON literal; decode once for original text)", content.notes)
    lines.extend(("## Review report", ""))
    text = "\n".join(lines) + "\n" + render_report_markdown(i.wrapper)
    body = text.encode("utf-8")
    return ExportResult(
        body=body, media_type=MARKDOWN_MEDIA_TYPE, export_sha256=hashlib.sha256(body).hexdigest()
    )


def render_export_json(i: ExportInput) -> ExportResult:
    """Canonical JSON: the binding, the disclaimer, and the decoded revision and wrapper."""
    obj: dict[str, Any] = {
        "schema": EXPORT_JSON_SCHEMA,
        "disclaimer": EXPORT_DISCLAIMER,
        "report_id": str(i.report.report_id),
        "review_id": str(i.report.review_id),
        "revision_no": i.revision.revision_number,
        "revision_schema": REVISION_SCHEMA,
        "content_sha256": i.revision.content_sha256,
        "wrapper_schema": SCHEMA,
        "wrapper_renderer": RENDERER,
        "wrapper_sha256": i.wrapper_sha256,
        "approved_by": str(i.approval.decided_by),
        "approved_at": i.approval.decided_at.isoformat(),
        "finalized_by": str(i.finalization.finalized_by),
        "finalized_at": i.finalization.finalized_at.isoformat(),
        "revision": json.loads(revision_canonical_bytes(i.revision.content)),
        "wrapper": json.loads(review_report_bytes(i.wrapper)),
    }
    body = json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")
    return ExportResult(
        body=body, media_type=JSON_MEDIA_TYPE, export_sha256=hashlib.sha256(body).hexdigest()
    )
