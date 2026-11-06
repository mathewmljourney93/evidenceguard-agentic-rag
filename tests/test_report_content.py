"""M5f values/codec: test-owned wire fixtures and independent literal digests."""

import dataclasses
import hashlib
import json
import warnings
from typing import Any
from uuid import UUID

import pytest

from evidenceguard_domain import report_content as rc
from evidenceguard_domain.evidence import EvidenceQuestion, ReportContent
from evidenceguard_domain.model_calls import PromptRef
from evidenceguard_domain.provenance import FindingKind
from evidenceguard_domain.review_stages import StageOutcome, StageShape, UnresolvedReason
from evidenceguard_domain.reviews import ReviewConfiguration

TENANT, REVIEW, VENDOR, JOB = (UUID(int=n) for n in (1, 2, 3, 4))


def canonical(obj: Any, *, ascii_only: bool = True) -> bytes:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=ascii_only, allow_nan=False
    ).encode("ascii" if ascii_only else "utf-8")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def wire_fixture() -> dict[str, Any]:
    """Written from the accepted schema, without any new implementation call."""
    cfg = {
        "canonical": "eg-review-configuration-v1",
        "kind": "review_configuration",
        "template": {"id": "report_test", "version": 1, "sha256": "f" * 64},
        "verifier_prompt": {"id": "verifier", "version": 1, "sha256": "1" * 64},
        "analyst_prompt": {"id": "analyst", "version": 1, "sha256": "2" * 64},
        "model": {"model_id": "fake-scripted-v1", "max_output_tokens": 4096, "timeout_ms": 60000},
        "retrieval_k": 8,
    }
    q = {
        "question_id": "QQ-01",
        "text": "Question?",
        "search_queries": ["query"],
        "requires_documentary_support": False,
    }
    plan = {"canonical": "eg-review-plan-question-v1", **q}
    psha = digest(canonical(plan))
    dep = {
        "canonical": "eg-review-stage-dependency-v1",
        "tenant_id": str(TENANT),
        "review_id": str(REVIEW),
        "question_id": "QQ-01",
        "question_sha256": psha,
        "owner": {
            "outcome": "unresolved",
            "content_sha256": None,
            "unresolved_reason": "evidence_too_large",
        },
        "shared": [],
    }
    legacy = {
        "schema": "evidenceguard.report-content.v1",
        "content": {
            "tenant_id": str(TENANT),
            "title": "Report \u03a9",
            "questions": [q],
            "findings": [],
            "unresolved_question_ids": ["QQ-01"],
        },
    }

    def stage(shape: str, reason: str, dependency: str | None) -> dict[str, Any]:
        return {
            "shape": shape,
            "outcome": "unresolved",
            "unresolved_reason": reason,
            "request_sha256": None,
            "content_sha256": None,
            "evidence_sha256": None,
            "dependency_sha256": dependency,
            "value": None,
        }

    return {
        "schema": "evidenceguard.review-report-content.v1",
        "renderer": "evidenceguard.review-report-markdown.v1",
        "mode": "contract",
        "binding": {
            "tenant_id": str(TENANT),
            "review_id": str(REVIEW),
            "vendor_id": str(VENDOR),
            "job_id": str(JOB),
            "review_request_sha256": "a" * 64,
            "snapshot_sha256": "b" * 64,
            "configuration": cfg,
            "configuration_sha256": digest(canonical(cfg)),
        },
        "legacy": legacy,
        "legacy_sha256": digest(canonical(legacy, ascii_only=False)),
        "questions": [
            {
                "question_id": "QQ-01",
                "position": 0,
                "plan_question_sha256": psha,
                "verification": stage("U4", "evidence_too_large", None),
                "analysis": stage("U3", "verification_unresolved", digest(canonical(dep))),
                "findings": [],
            }
        ],
    }


def configuration() -> ReviewConfiguration:
    return ReviewConfiguration(
        template_id="report_test",
        template_version=1,
        template_sha256="f" * 64,
        verifier_prompt=PromptRef(prompt_id="verifier", version=1, sha256="1" * 64),
        analyst_prompt=PromptRef(prompt_id="analyst", version=1, sha256="2" * 64),
        model_id="fake-scripted-v1",
    )


def report_fixture() -> rc.ReviewReportContent:
    wire = wire_fixture()
    q = EvidenceQuestion(question_id="QQ-01", text="Question?", search_queries=("query",))

    def stage(data: dict[str, Any]) -> rc.ReportStage:
        return rc.ReportStage(
            **{
                **data,
                "shape": StageShape(data["shape"]),
                "outcome": StageOutcome(data["outcome"]),
                "unresolved_reason": UnresolvedReason(data["unresolved_reason"]),
            }
        )

    view = wire["questions"][0]
    return rc.ReviewReportContent(
        binding=rc.ReportBinding(
            tenant_id=TENANT,
            review_id=REVIEW,
            vendor_id=VENDOR,
            job_id=JOB,
            review_request_sha256="a" * 64,
            snapshot_sha256="b" * 64,
            configuration=configuration(),
        ),
        mode=rc.ReportMode.CONTRACT,
        content=ReportContent(
            tenant_id=TENANT,
            title="Report \u03a9",
            questions=(q,),
            findings=(),
            unresolved_question_ids=("QQ-01",),
        ),
        questions=(
            rc.ReportQuestion(
                question_id="QQ-01",
                position=0,
                plan_question_sha256=view["plan_question_sha256"],
                verification=stage(view["verification"]),
                analysis=stage(view["analysis"]),
                findings=(),
            ),
        ),
    )


def bypass(value: Any, **changes: Any) -> Any:
    if hasattr(type(value), "model_fields"):
        return (
            value.model_copy(update=changes)
            if not changes
            else type(value).model_construct(
                **{**{k: getattr(value, k) for k in type(value).model_fields}, **changes}
            )
        )
    copy = object.__new__(type(value))
    for field in dataclasses.fields(value):
        object.__setattr__(copy, field.name, changes.get(field.name, getattr(value, field.name)))
    return copy


def fixed(error: BaseException, kind: type[rc.ReportContentError]) -> None:
    assert type(error) is kind
    assert str(error) == kind.code
    assert error.__cause__ is None and error.__context__ is None


def test_independent_canonical_fixture_and_legacy_unicode() -> None:
    from evidenceguard_domain.report import canonical_content_bytes, content_sha256

    wire = wire_fixture()
    report = report_fixture()
    raw = canonical(wire)
    # Independently derived once from the test-owned JSON object with hashlib, not the codec.
    assert digest(raw) == "747854fd509b011bd50eef44273eed292a82e1e004ba3af1be406acd03fe020e"
    assert rc.review_report_bytes(report) == raw
    assert rc.review_report_sha256(report) == digest(raw)
    legacy = canonical(wire["legacy"], ascii_only=False)
    assert digest(legacy) == "6e09cecf85b937ebb34380d36a21834e16a4021e443d2b4bd082ddf7ece41731"
    assert canonical_content_bytes(report.content) == legacy
    assert content_sha256(report.content) == digest(legacy) == report.legacy_sha256
    assert rc.review_report_sha256(report) != content_sha256(report.content)
    decoded = rc.decode_review_report(raw, expected_sha256=digest(raw))
    assert decoded == report and decoded is not report
    assert decoded.questions[0] is not report.questions[0]


@pytest.mark.parametrize(
    "field,value",
    [
        ("position", True),
        ("position", -1),
        ("position", 100),
        ("findings", []),
        ("question_id", 1),
        ("plan_question_sha256", "A" * 64),
    ],
)
def test_exact_nested_fields_refuse_without_coercion(field: str, value: Any) -> None:
    original = report_fixture()
    bad = bypass(original, questions=(bypass(original.questions[0], **{field: value}),))
    with pytest.raises(rc.InvalidReportValueError) as caught:
        rc.review_report_bytes(bad)
    fixed(caught.value, rc.InvalidReportValueError)


@pytest.mark.parametrize(
    "change",
    [
        lambda w: w.update(extra=None),
        lambda w: w.pop("mode"),
        lambda w: w["questions"][0].update(position=True),
        lambda w: w["questions"][0]["analysis"].pop("value"),
        lambda w: w["legacy"]["content"]["questions"][0].update(requires_documentary_support=1),
        lambda w: w["legacy"]["content"]["questions"][0].update(search_queries=["query", "query"]),
        lambda w: w["binding"].update(tenant_id="00000000-0000-0000-0000-00000000000A"),
        lambda w: w["binding"]["configuration"]["model"].update(max_output_tokens=True),
        lambda w: w.update(legacy_sha256="0" * 64),
        lambda w: w["questions"][0]["analysis"].update(dependency_sha256="0" * 64),
        lambda w: w["legacy"]["content"].update(title="\ud800"),
        lambda w: w["legacy"]["content"].update(title="\x00"),
    ],
)
def test_structural_tampering(change: Any) -> None:
    w = wire_fixture()
    change(w)
    raw = canonical(w)
    with pytest.raises(rc.InvalidReportEncodingError) as caught:
        rc.decode_review_report(raw, expected_sha256=digest(raw))
    fixed(caught.value, rc.InvalidReportEncodingError)


@pytest.mark.parametrize(
    "raw",
    [
        b"{} ",
        b'{"a":1,"a":2}',
        b'{"x":01}',
        b'{"x":-0}',
        b'{"x":1.0}',
        b'{"x":1e2}',
        b'{"x":2147483648}',
        b'{"x":12345678901}',
        b'{"x":NaN}',
        b'{"x":"bad\\q"}',
        b'{"x":"unterminated}',
        b"\xef\xbb\xbf{}",
    ],
)
def test_lexical_refusals(raw: bytes) -> None:
    with pytest.raises(rc.InvalidReportEncodingError) as caught:
        rc.decode_review_report(raw, expected_sha256=digest(raw))
    fixed(caught.value, rc.InvalidReportEncodingError)


@pytest.mark.parametrize("key,value", [("schema", "unknown"), ("renderer", "unknown")])
def test_unknown_versions(key: str, value: str) -> None:
    w = wire_fixture()
    w[key] = value
    raw = canonical(w)
    with pytest.raises(rc.UnsupportedReportSchemaError):
        rc.decode_review_report(raw, expected_sha256=digest(raw))


def test_expected_digest_last_and_canonical_equality() -> None:
    raw = canonical(wire_fixture())
    with pytest.raises(rc.ReportDigestMismatchError) as caught:
        rc.decode_review_report(raw, expected_sha256="0" * 64)
    fixed(caught.value, rc.ReportDigestMismatchError)
    for other in [
        raw + b"\n",
        raw.replace(b'"position":0', b'"position": 0'),
        raw.replace(b"Question?", b"\\u0051uestion?"),
    ]:
        with pytest.raises(rc.InvalidReportEncodingError):
            rc.decode_review_report(other, expected_sha256=digest(other))
    with pytest.raises(rc.InvalidReportInputError):
        rc.decode_review_report(raw, expected_sha256="G" * 64)


def test_real_lexical_engineering_limits_before_json(monkeypatch: pytest.MonkeyPatch) -> None:
    def never(*args: Any, **kw: Any) -> None:
        raise AssertionError("general JSON parser reached")

    monkeypatch.setattr(json, "loads", never)
    for raw in [
        b"[" * 17 + b"0" + b"]" * 17,
        b"[" + b"0," * 500000 + b"0]",
        b'"' + b"x" * rc.MAX_CONTENT_BYTES + b'"',
    ]:
        with pytest.raises(rc.ReportLimitExceededError) as caught:
            rc.decode_review_report(raw, expected_sha256=digest(raw))
        fixed(caught.value, rc.ReportLimitExceededError)


def test_content_and_legacy_cap_boundaries(monkeypatch: pytest.MonkeyPatch) -> None:
    value = report_fixture()
    raw = rc.review_report_bytes(value)
    monkeypatch.setattr(rc, "MAX_CONTENT_BYTES", len(raw))
    assert rc.review_report_bytes(value) == raw
    monkeypatch.setattr(rc, "MAX_CONTENT_BYTES", len(raw) - 1)
    with pytest.raises(rc.ReportLimitExceededError):
        rc.review_report_bytes(value)
    monkeypatch.setattr(rc, "MAX_CONTENT_BYTES", 16777216)
    legacy = canonical(wire_fixture()["legacy"], ascii_only=False)
    monkeypatch.setattr(rc, "MAX_LEGACY_BYTES", len(legacy))
    assert rc.review_report_bytes(value) == raw
    monkeypatch.setattr(rc, "MAX_LEGACY_BYTES", len(legacy) - 1)
    with pytest.raises(rc.ReportLimitExceededError):
        rc.review_report_bytes(value)


def test_quiet_refusal_and_process_control(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    value = report_fixture()
    for field, replacement in [
        ("text", 12),
        ("requires_documentary_support", 1),
        ("search_queries", "query"),
    ]:
        bad = bypass(
            value,
            content=bypass(
                value.content,
                questions=(bypass(value.content.questions[0], **{field: replacement}),),
            ),
        )
        with (
            warnings.catch_warnings(record=True) as seen,
            pytest.raises(rc.InvalidReportValueError) as caught,
        ):
            rc.review_report_bytes(bad)
        assert not seen
        fixed(caught.value, rc.InvalidReportValueError)
    assert capsys.readouterr() == ("", "") and not caplog.records
    control = KeyboardInterrupt()

    def stop(*args: Any, **kw: Any) -> Any:
        raise control

    monkeypatch.setattr(rc, "_encoded", stop)
    with pytest.raises(KeyboardInterrupt) as caught_control:
        rc.review_report_bytes(value)
    assert caught_control.value is control


@pytest.mark.parametrize(
    "shape,reason,verification,call",
    [
        ("U1", "refusal", True, True),
        ("U1", "provider_failed", False, True),
        ("U2", "call_abandoned", True, True),
        ("U2", "call_abandoned", False, True),
        ("U3", "verification_unresolved", False, False),
        ("U4", "evidence_too_large", True, False),
        ("U5", "request_too_large", True, False),
        ("U5", "request_too_large", False, False),
        ("U6", "repair_request_too_large", True, True),
        ("U6", "repair_request_too_large", False, True),
    ],
)
def test_unresolved_shape_matrix(shape: str, reason: str, verification: bool, call: bool) -> None:
    values: dict[str, Any] = dict(
        shape=StageShape(shape),
        outcome=StageOutcome.UNRESOLVED,
        unresolved_reason=UnresolvedReason(reason),
        request_sha256="a" * 64 if call else None,
        content_sha256=None,
        evidence_sha256="e" * 64 if verification and shape != "U4" else None,
        dependency_sha256=None if verification else "d" * 64,
        value=None,
    )
    stage = rc.ReportStage(**values)
    assert stage.shape.value == shape
    mutations: list[dict[str, Any]] = [
        dict(content_sha256="c" * 64),
        dict(unresolved_reason=None),
        dict(request_sha256=None if call else "a" * 64),
    ]
    for mutation in mutations:
        with pytest.raises(rc.InvalidReportValueError):
            rc.ReportStage(**{**values, **mutation})


def test_exact_subclasses_unknown_fields_and_nested_configuration() -> None:
    class Text(str):
        pass

    original = report_fixture()
    for value in [
        bypass(original.content, title=Text("title")),
        bypass(
            original.content,
            questions=(bypass(original.content.questions[0], search_queries=(" query",)),),
        ),
    ]:
        with pytest.raises(rc.InvalidReportValueError):
            dataclasses.replace(original, content=value)
    config = bypass(original.binding.configuration, max_output_tokens=True)
    with pytest.raises(rc.InvalidReportValueError):
        dataclasses.replace(original, binding=bypass(original.binding, configuration=config))
    with pytest.raises(rc.InvalidReportValueError) as caught:
        rc.ReportFindingRef(
            kind=FindingKind.ANALYST,
            index=0,
            finding_id=UUID(int=1),
            follow_up_questions=(),
            unexpected="PRIVATE",
        )
    fixed(caught.value, rc.InvalidReportValueError)


def test_lex_depth_and_token_caps_at_exact_boundaries() -> None:
    rc._lex(b"[" * 16 + b"0" + b"]" * 16)
    raw = b"[" + b"0," * 499998 + b"0]"
    rc._lex(raw)  # one container plus 499999 scalar tokens
    with pytest.raises(rc._Failure):
        rc._lex(b"[" + b"0," * 499999 + b"0]")
    # Punctuation and escapes inside strings count as one token and never as nesting.
    rc._lex(b'{"x":"' + b"[{" * 10000 + b'\\""}')
