"""Pinned field order/JSON literal presentation, never a live-model quality check."""

import dataclasses
import json
from typing import TYPE_CHECKING, Any

import pytest

from evidenceguard_agents import report as renderer
from evidenceguard_domain import report_content as rc

if TYPE_CHECKING:
    from test_report_builder import world
    from test_report_content import canonical, digest, report_fixture, wire_fixture
else:
    from tests.test_report_builder import world
    from tests.test_report_content import canonical, digest, report_fixture, wire_fixture


def golden_markdown() -> str:
    """A test-owned declarative specimen, not rendered from implementation values.

    All field labels, ordering and values below are written from the accepted emission
    table; only standard-library JSON/hash operations supply literal encodings.
    """
    w = wire_fixture()
    b = w["binding"]
    v = w["questions"][0]["verification"]
    a = w["questions"][0]["analysis"]
    specimen: list[str | tuple[str, Any]] = [
        "# EvidenceGuard review",
        "## Contract and binding",
        ("Contract mode stamp", "NOT a quality measurement of Claude or semantic retrieval"),
        ("Mode", "contract"),
        ("Renderer", "evidenceguard.review-report-markdown.v1"),
        ("Wrapper SHA-256", "747854fd509b011bd50eef44273eed292a82e1e004ba3af1be406acd03fe020e"),
        ("Legacy SHA-256", "6e09cecf85b937ebb34380d36a21834e16a4021e443d2b4bd082ddf7ece41731"),
        ("Tenant ID", b["tenant_id"]),
        ("Review ID", b["review_id"]),
        ("Vendor ID", b["vendor_id"]),
        ("Job ID", b["job_id"]),
        ("Review request SHA-256", "a" * 64),
        ("Snapshot SHA-256", "b" * 64),
        ("Configuration SHA-256", digest(canonical(b["configuration"]))),
        ("Template ID", "report_test"),
        ("Template version", 1),
        ("Template SHA-256", "f" * 64),
        ("Verifier prompt ID", "verifier"),
        ("Verifier prompt version", 1),
        ("Verifier prompt SHA-256", "1" * 64),
        ("Analyst prompt ID", "analyst"),
        ("Analyst prompt version", 1),
        ("Analyst prompt SHA-256", "2" * 64),
        ("Model ID", "fake-scripted-v1"),
        ("Max output tokens", 4096),
        ("Timeout ms", 60000),
        ("Retrieval k", 8),
        ("Report title", "Report \u03a9"),
        "## Questions",
        ("Count", 1),
        "### Question 1",
        ("Question ID", "QQ-01"),
        ("Question text", "Question?"),
        ("Requires documentary support", False),
        ("Plan question SHA-256", w["questions"][0]["plan_question_sha256"]),
        ("Search query count", 1),
        ("Search query 1", "query"),
        "#### Verification",
        ("Shape", "U4"),
        ("Outcome", "unresolved"),
        ("Unresolved reason", "evidence_too_large"),
        ("Request SHA-256", None),
        ("Content SHA-256", None),
        ("Evidence SHA-256", None),
        ("Dependency SHA-256", v["dependency_sha256"]),
        "#### Analysis",
        ("Shape", "U3"),
        ("Outcome", "unresolved"),
        ("Unresolved reason", "verification_unresolved"),
        ("Request SHA-256", None),
        ("Content SHA-256", None),
        ("Evidence SHA-256", None),
        ("Dependency SHA-256", a["dependency_sha256"]),
        ("Report unresolved", True),
        ("Unresolved cause count", 3),
        ("Unresolved cause 1", "verification_unresolved"),
        ("Unresolved cause 2", "analysis_unresolved"),
        ("Unresolved cause 3", "no_resolving_finding"),
        "#### Findings",
        ("Count", 0),
        "## Unresolved questions",
        ("Count", 1),
        ("Question ID 1", "QQ-01"),
    ]
    pieces = []
    for row in specimen:
        if isinstance(row, str):
            pieces.append(row + "\n\n")
        else:
            pieces.append(row[0] + ":\n\n    " + json.dumps(row[1], ensure_ascii=True) + "\n\n")
    return "".join(pieces)[:-1]


def test_exact_markdown_bytes_from_independent_specimen() -> None:
    expected = golden_markdown()
    assert (
        digest(expected.encode("ascii"))
        == "caae6e2534baf776661056de4c45f962186afd40ec1773b3f4f2c7792c35ce6c"
    )
    assert renderer.render_report_markdown(report_fixture()) == expected


def test_renderer_deterministic_and_reversible_adversarial_text() -> None:
    text = "Question?\n# forged\n<script>&</script> https://example.invalid/ ``` \u202e"
    r, t, p, s = world(text=text)
    value = renderer.build_report_content(r, t, p, s)
    rendered = renderer.render_report_markdown(value)
    assert rendered == renderer.render_report_markdown(rc.revalidate_review_report(value))
    assert rendered.isascii() and rendered.endswith("\n") and not rendered.endswith("\n\n")
    assert "\r" not in rendered and "<script>" not in rendered
    assert "\\u003cscript\\u003e" in rendered and "\\u202e" in rendered
    fields = rendered.splitlines()
    index = fields.index("Question text:")
    assert json.loads(fields[index + 2].strip()) == text
    assert fields[:3] == ["# EvidenceGuard review", "", "## Contract and binding"]
    assert '    "NOT a quality measurement of Claude or semantic retrieval"' in fields
    assert (
        rendered.index("#### Verification")
        < rendered.index("#### Analysis")
        < rendered.index("#### Findings")
    )
    quote_index = fields.index("Accepted quote (JSON literal; decode once for original text):")
    v = value.questions[0].verification.value
    assert v is not None
    assert json.loads(fields[quote_index + 2].strip()) == v.citations[0].quote


def test_unresolved_output_does_not_discard_successful_verification() -> None:
    value = renderer.build_report_content(*world(documentary=True, unresolved_analysis=True))
    text = renderer.render_report_markdown(value)
    for label in [
        '"supported"',
        '"vendor_claim"',
        '"refusal"',
        '"Documentary evidence required"',
        '"not_established"',
        '"documentary_support_required"',
    ]:
        assert label in text
    assert "http" not in text


def test_render_cap_exact_boundary_and_process_control(monkeypatch: pytest.MonkeyPatch) -> None:
    value = report_fixture()
    text = renderer.render_report_markdown(value)
    monkeypatch.setattr(renderer, "MAX_MARKDOWN_BYTES", len(text))
    assert renderer.render_report_markdown(value) == text
    monkeypatch.setattr(renderer, "MAX_MARKDOWN_BYTES", len(text) - 1)
    with pytest.raises(rc.ReportRenderLimitError) as caught:
        renderer.render_report_markdown(value)
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    control = KeyboardInterrupt()

    def stop(*a: Any, **kw: Any) -> Any:
        raise control

    monkeypatch.setattr(renderer, "review_report_sha256", stop)
    with pytest.raises(KeyboardInterrupt) as caught_control:
        renderer.render_report_markdown(value)
    assert caught_control.value is control


def test_privacy_safe_representations_for_every_nested_report_value() -> None:
    value = renderer.build_report_content(*world())
    v = value.questions[0].verification.value
    assert v is not None
    sentinels = [
        "REPORT-TITLE-SENTINEL",
        "QUESTION-TEXT-SENTINEL",
        "QUERY-SENTINEL",
        "QUOTE-SENTINEL",
        "RATIONALE-SENTINEL",
        "CLAIM-SENTINEL",
        "FINDING-TITLE-SENTINEL",
        "FINDING-STATEMENT-SENTINEL",
        "FOLLOW-UP-SENTINEL",
    ]
    # Replace each textual field consistently using the real constructors. Source rechecking
    # would (correctly) refuse this changed report; structural construction should preserve it.
    quote = v.citations[0].model_copy(update={"quote": sentinels[3]})
    verification = dataclasses.replace(
        v,
        rationale=sentinels[4],
        citations=(quote,),
        claims=(dataclasses.replace(v.claims[0], text=sentinels[5]),),
    )
    item = value.questions[0]
    from evidenceguard_domain.review_stages import plan_question_sha256

    q = value.content.questions[0].model_copy(
        update={"text": sentinels[1], "search_queries": (sentinels[2],)}
    )
    from evidenceguard_domain.review_stages import dependency_sha256

    vs = dataclasses.replace(item.verification, value=verification)
    dep = dependency_sha256(
        tenant_id=value.binding.tenant_id,
        review_id=value.binding.review_id,
        question_id=q.question_id,
        question_sha256=plan_question_sha256(q),
        owner_outcome=vs.outcome,
        owner_content_sha256=vs.content_sha256,
        owner_reason=vs.unresolved_reason,
    )
    ref = dataclasses.replace(item.findings[0], follow_up_questions=(sentinels[8],))
    item = dataclasses.replace(
        item,
        plan_question_sha256=plan_question_sha256(q),
        verification=vs,
        analysis=dataclasses.replace(item.analysis, dependency_sha256=dep),
        findings=(ref,),
    )
    f = value.content.findings[0].model_copy(
        update={"title": sentinels[6], "statement": sentinels[7], "citations": (quote,)}
    )
    value = dataclasses.replace(
        value,
        questions=(item,),
        content=value.content.model_copy(
            update={"title": sentinels[0], "questions": (q,), "findings": (f,)}
        ),
    )
    for obj in [
        value,
        value.binding,
        item,
        vs,
        verification,
        item.analysis,
        ref,
        rc.ReportMode.CONTRACT,
    ]:
        for representation in [repr(obj), str(obj)]:
            assert all(secret not in representation for secret in sentinels)
    raw = rc.review_report_bytes(value).decode("ascii")
    rendered = renderer.render_report_markdown(value)
    assert all(secret in raw and secret in rendered for secret in sentinels)
