"""M6 export renderers over a finalized report (ADR-0028). No database."""

import hashlib
import json
from datetime import timedelta
from typing import TYPE_CHECKING

from evidenceguard_agents import report_export as export
from evidenceguard_agents.report import render_report_markdown
from evidenceguard_domain import review_report_approval as ra
from evidenceguard_domain.context import Role
from evidenceguard_domain.report_content import review_report_bytes, review_report_sha256

if TYPE_CHECKING:
    from test_review_report_approval import A1, A2, T0, actor, opened
else:
    from tests.test_review_report_approval import A1, A2, T0, actor, opened

HOSTILE = "<script>alert(1)</script> & **bold** [x](javascript:x)\n# heading \u03a9"


def finalized_input() -> ra.ExportInput:
    report, w = opened()
    author = actor(report, Role.REVIEWER)
    approver = actor(report, Role.APPROVER, A1)
    finalizer = actor(report, Role.APPROVER, A2)
    current = report.current_revision
    marks = (ra.Disposition.ACCEPTED, ra.Disposition.DISMISSED, ra.Disposition.OPEN)
    draft = ra.revise(
        report,
        author,
        expected_revision_number=1,
        expected_sha256=current.content_sha256,
        dispositions=tuple(
            ra.FindingDisposition(finding_id=fid, disposition=d, note=HOSTILE)
            for fid, d in zip(report.finding_ids, marks, strict=True)
        ),
        notes=HOSTILE,
        now=T0,
    )
    r2 = draft.current_revision
    ok = ra.approve(draft, approver, revision_number=2, content_sha256=r2.content_sha256, now=T0)
    done = ra.finalize(
        ok,
        finalizer,
        revision_number=2,
        content_sha256=r2.content_sha256,
        now=T0 + timedelta(minutes=5),
    )
    assert done.effective_approval is not None and done.finalization is not None
    return ra.ExportInput(
        report=done,
        wrapper=w,
        wrapper_sha256=review_report_sha256(w),
        revision=done.current_revision,
        approval=done.effective_approval,
        finalization=done.finalization,
    )


def test_markdown_is_deterministic_and_carries_the_binding_and_disclaimer() -> None:
    i = finalized_input()
    first, second = export.render_export_markdown(i), export.render_export_markdown(i)
    assert first == second
    assert first.media_type == "text/markdown; charset=utf-8"
    assert first.export_sha256 == hashlib.sha256(first.body).hexdigest()
    text = first.body.decode("utf-8")
    assert text.startswith("# EvidenceGuard finalized report export\n")
    for value in (
        str(i.report.report_id),
        i.revision.content_sha256,
        i.wrapper_sha256,
        str(A1),
        str(A2),
        ra.REVISION_SCHEMA,
        export.EXPORT_MD_RENDERER,
    ):
        assert str(value) in text
    assert export.EXPORT_DISCLAIMER in text
    assert "not legal advice" in export.EXPORT_DISCLAIMER
    assert "provenance only" in export.EXPORT_DISCLAIMER
    assert text.endswith(render_report_markdown(i.wrapper))
    assert text.index(export.EXPORT_DISCLAIMER) < text.index("## Dispositions")


def test_reviewer_text_is_rendered_as_escaped_literals() -> None:
    text = export.render_export_markdown(finalized_input()).body.decode("utf-8")
    header = text[: text.index("## Review report")]
    assert "<" not in header and ">" not in header and "&" not in header
    assert "<script>" not in header and "\n# heading" not in header
    literal = json.dumps(HOSTILE, ensure_ascii=True, separators=(",", ":"))
    for char, escape in (("<", r"\u003c"), (">", r"\u003e"), ("&", r"\u0026")):
        literal = literal.replace(char, escape)
    assert header.count("    " + literal) == 4  # three finding notes and the report notes
    assert '    "dismissed"' in header and '    "accepted"' in header


def test_json_is_canonical_and_embeds_the_decoded_revision_and_wrapper() -> None:
    i = finalized_input()
    result = export.render_export_json(i)
    assert result == export.render_export_json(i)
    assert result.media_type == "application/json"
    assert result.export_sha256 == hashlib.sha256(result.body).hexdigest()
    obj = json.loads(result.body)
    canonical = json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")
    assert canonical == result.body
    assert obj["schema"] == export.EXPORT_JSON_SCHEMA
    assert obj["disclaimer"] == export.EXPORT_DISCLAIMER
    assert obj["revision_no"] == 2 and obj["content_sha256"] == i.revision.content_sha256
    assert obj["approved_by"] == str(A1) and obj["finalized_by"] == str(A2)
    assert obj["wrapper_sha256"] == i.wrapper_sha256
    revision_bytes = json.dumps(
        obj["revision"], sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    assert hashlib.sha256(revision_bytes).hexdigest() == i.revision.content_sha256
    wrapper_bytes = json.dumps(
        obj["wrapper"], sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    assert wrapper_bytes == review_report_bytes(i.wrapper)
    assert hashlib.sha256(wrapper_bytes).hexdigest() == i.wrapper_sha256
