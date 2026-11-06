"""M5f hash-covered report values and strict codec (ADR-0024).

These are supported-input boundaries, not proof of database origin or an in-process sandbox.
Legacy report bytes/approval semantics are unchanged. Source payload digests are references.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import types
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum, StrEnum
from fractions import Fraction
from typing import (
    Any,
    ClassVar,
    Literal,
    TypeAliasType,
    Union,
    cast,
    get_args,
    get_origin,
    get_type_hints,
)
from uuid import UUID

from evidenceguard_domain._base import DomainModel
from evidenceguard_domain.evidence import (
    Citation,
    EvidenceQuestion,
    EvidenceStatus,
    Finding,
    ReportContent,
    Severity,
    Verdict,
    Verification,
)
from evidenceguard_domain.model_calls import PromptRef
from evidenceguard_domain.provenance import (
    DOCUMENTARY_GAP_STATEMENT,
    DOCUMENTARY_GAP_TITLE,
    FindingKind,
    ValidatedClaim,
    derive_status,
    finding_id,
)
from evidenceguard_domain.report import canonical_content_bytes
from evidenceguard_domain.review_stages import (
    StageOutcome,
    StageShape,
    UnresolvedReason,
    dependency_sha256,
    plan_question_sha256,
)
from evidenceguard_domain.reviews import ReviewConfiguration

SCHEMA = "evidenceguard.review-report-content.v1"
RENDERER = "evidenceguard.review-report-markdown.v1"
LEGACY_SCHEMA = "evidenceguard.report-content.v1"
MAX_CONTENT_BYTES = 16_777_216
MAX_LEGACY_BYTES = 16_777_216
MAX_DEPTH = 16
MAX_TOKENS = 500_000
MAX_MARKDOWN_BYTES = 33_554_432
MAX_INTEGER = 2_147_483_647
_SHA = re.compile(r"[0-9a-f]{64}\Z")


class ReportContentError(ValueError):
    code: ClassVar[str] = "report_content_error"

    def __init__(self) -> None:
        super().__init__(self.code)


class InvalidReportInputError(ReportContentError):
    code = "invalid_report_input"


class InvalidReportValueError(ReportContentError):
    code = "invalid_report_value"


class ReportBindingMismatchError(ReportContentError):
    code = "report_binding_mismatch"


class IncompleteReportStagesError(ReportContentError):
    code = "incomplete_report_stages"


class ReportFindingConflictError(ReportContentError):
    code = "report_finding_conflict"


class ReportLimitExceededError(ReportContentError):
    code = "report_limit_exceeded"


class InvalidReportEncodingError(ReportContentError):
    code = "invalid_report_encoding"


class UnsupportedReportSchemaError(ReportContentError):
    code = "unsupported_report_schema"


class ReportDigestMismatchError(ReportContentError):
    code = "report_digest_mismatch"


class ReportRenderError(ReportContentError):
    code = "report_render_failed"


class ReportRenderLimitError(ReportContentError):
    code = "report_render_limit_exceeded"


class _Failure(Exception):
    def __init__(self, kind: type[ReportContentError]) -> None:
        self.kind = kind


def _require(ok: bool) -> None:
    if not ok:
        raise ValueError


def _fail(kind: type[ReportContentError]) -> None:
    raise _Failure(kind)


def _run[T](fn: Callable[[], T], default: type[ReportContentError]) -> T:
    kind = default
    try:
        return fn()
    except _Failure as error:
        kind = error.kind
    except ReportLimitExceededError:
        kind = ReportLimitExceededError
    except Exception:
        pass
    # Deliberately outside handlers: no original context/cause, text, warnings or logging.
    raise kind()


def _digest(value: object) -> bool:
    return type(value) is str and _SHA.fullmatch(value) is not None


def _text(value: object, low: int, high: int, *, stripped: bool = False) -> None:
    _require(type(value) is str)
    assert isinstance(value, str)
    _require(low <= len(value) <= high and "\x00" not in value)
    _require(not any(0xD800 <= ord(c) <= 0xDFFF for c in value))
    _require(not stripped or value == value.strip())


def _integer(value: object, low: int, high: int) -> None:
    _require(type(value) is int and low <= value <= high)


def _tuple(value: object, low: int, high: int) -> None:
    _require(type(value) is tuple and low <= len(cast(tuple[object, ...], value)) <= high)


def _model_texts(value: object) -> None:
    if type(value) is str:
        _text(value, 0, MAX_CONTENT_BYTES, stripped=True)
    elif type(value) is tuple:
        for item in value:
            _model_texts(item)


def _exact(value: object, annotation: Any, active: set[int]) -> None:
    """Preflight declared fields before calling any coercing/rebuilding serializer.

    Existing dataclass/Pydantic annotations are the type source. Their own constructors
    subsequently enforce bounds/cross-field rules. Only exact instances enter this walker.
    """
    if isinstance(annotation, TypeAliasType):
        annotation = annotation.__value__
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is Literal:
        _require(any(type(value) is type(v) and value == v for v in args))
        return
    if origin in (Union, types.UnionType):
        for option in args:
            try:
                _exact(value, option, active)
                return
            except (ValueError, TypeError):
                continue
        raise ValueError
    if origin is tuple:
        _require(type(value) is tuple)
        for i, item in enumerate(cast(tuple[object, ...], value)):
            _exact(item, args[0] if len(args) == 2 and args[1] is Ellipsis else args[i], active)
        if not (len(args) == 2 and args[1] is Ellipsis):
            _require(len(cast(tuple[object, ...], value)) == len(args))
        return
    if origin in (frozenset, list, dict):
        _require(type(value) is origin)
        if origin is dict:
            for key, item in cast(dict[object, object], value).items():
                _exact(key, args[0], active)
                _exact(item, args[1], active)
        else:
            for item in cast(list[object], value):
                _exact(item, args[0], active)
        return
    _require(annotation is not Any and type(value) is annotation)
    if annotation is str:
        _text(value, 0, MAX_CONTENT_BYTES)
    elif annotation is int:
        _integer(value, 0, MAX_INTEGER)
    elif isinstance(value, DomainModel) or dataclasses.is_dataclass(value):
        identity = id(value)
        _require(identity not in active)
        active.add(identity)
        hints = get_type_hints(type(value))
        names = (
            type(value).model_fields
            if isinstance(value, DomainModel)
            else {f.name: f for f in dataclasses.fields(value)}
        )
        for name in names:
            if isinstance(value, DomainModel):
                _model_texts(getattr(value, name))
            _exact(getattr(value, name), hints[name], active)
        active.remove(identity)
    else:
        _require(
            annotation in (UUID, bool, bytes, float, date, datetime, Fraction, type(None))
            or isinstance(value, Enum)
        )


def _preflight(value: object, kind: type[Any]) -> None:
    _exact(value, kind, set())


def _rebuild_model[M: DomainModel](value: M, kind: type[M]) -> M:
    _preflight(value, kind)
    values: dict[str, Any] = {}
    for name in kind.model_fields:
        item = getattr(value, name)
        if type(item) is tuple:
            item = tuple(
                _rebuild_model(v, type(v)) if isinstance(v, DomainModel) else v for v in item
            )
        elif isinstance(item, DomainModel):
            item = _rebuild_model(item, type(item))
        if type(item) is str:
            _require(item == item.strip())
        values[name] = item
    checked = kind(**values)
    _require(checked == value)
    return checked


def _configuration(value: ReviewConfiguration) -> ReviewConfiguration:
    _preflight(value, ReviewConfiguration)
    checked = ReviewConfiguration(
        **{f.name: getattr(value, f.name) for f in dataclasses.fields(value) if f.init}
    )
    _require(checked == value)
    return checked


def _init(
    value: object, data: dict[str, Any], unknown: dict[str, object], check: Callable[[], None]
) -> None:
    def build() -> None:
        _require(not unknown)
        hints = get_type_hints(type(value))
        for key, item in data.items():
            _exact(item, hints[key], set())
        check()
        for key, item in data.items():
            object.__setattr__(value, key, item)

    _run(build, InvalidReportValueError)


class ReportMode(StrEnum):
    CONTRACT = "contract"


@dataclass(frozen=True, init=False, repr=False)
class ReportBinding:
    tenant_id: UUID
    review_id: UUID
    vendor_id: UUID
    job_id: UUID
    review_request_sha256: str
    snapshot_sha256: str
    configuration: ReviewConfiguration

    def __init__(
        self,
        *,
        tenant_id: UUID,
        review_id: UUID,
        vendor_id: UUID,
        job_id: UUID,
        review_request_sha256: str,
        snapshot_sha256: str,
        configuration: ReviewConfiguration,
        **unknown: object,
    ) -> None:
        data = dict(
            tenant_id=tenant_id,
            review_id=review_id,
            vendor_id=vendor_id,
            job_id=job_id,
            review_request_sha256=review_request_sha256,
            snapshot_sha256=snapshot_sha256,
            configuration=configuration,
        )

        def check() -> None:
            _require(_digest(review_request_sha256) and _digest(snapshot_sha256))
            data["configuration"] = _configuration(configuration)

        _init(self, data, unknown, check)

    @property
    def configuration_sha256(self) -> str:
        return self.configuration.configuration_sha256

    def __repr__(self) -> str:
        return f"ReportBinding(review_id={self.review_id}, snapshot_sha256={self.snapshot_sha256})"

    __str__ = __repr__


@dataclass(frozen=True, init=False, repr=False)
class ReportVerification:
    verdict: Verdict
    evidence_status: EvidenceStatus
    rationale: str
    citations: tuple[Citation, ...]
    claims: tuple[ValidatedClaim, ...]

    def __init__(
        self,
        *,
        verdict: Verdict,
        evidence_status: EvidenceStatus,
        rationale: str,
        citations: tuple[Citation, ...],
        claims: tuple[ValidatedClaim, ...],
        **unknown: object,
    ) -> None:
        data = dict(
            verdict=verdict,
            evidence_status=evidence_status,
            rationale=rationale,
            citations=citations,
            claims=claims,
        )

        def check() -> None:
            _text(rationale, 1, 2000, stripped=True)
            _tuple(citations, 0, 80)
            _tuple(claims, 0, 10)
            cs = tuple(_rebuild_model(c, Citation) for c in citations)
            rebuilt = tuple(
                ValidatedClaim(text=c.text, citation_indexes=c.citation_indexes) for c in claims
            )
            seen: set[int] = set()
            for claim in rebuilt:
                for index in claim.citation_indexes:
                    _require(index < len(cs))
                    if index not in seen:
                        _require(index == len(seen))
                        seen.add(index)
                _require(verdict is Verdict.INSUFFICIENT_EVIDENCE or bool(claim.citation_indexes))
            _require(len(seen) == len(cs))
            _require(derive_status(verdict, cs) is evidence_status)
            # M1 supplies duplicate-citation, same-tenant and verdict/status validation.
            Verification(
                tenant_id=cs[0].tenant_id if cs else UUID(int=0),
                question_id="QX-01",
                verdict=verdict,
                evidence_status=evidence_status,
                rationale=rationale,
                citations=cs,
            )
            data.update(citations=cs, claims=rebuilt)

        _init(self, data, unknown, check)

    def __repr__(self) -> str:
        return (
            f"ReportVerification(verdict={self.verdict.value}, "
            f"citations={len(self.citations)}, claims={len(self.claims)})"
        )

    __str__ = __repr__


@dataclass(frozen=True, init=False, repr=False)
class ReportStage:
    shape: StageShape
    outcome: StageOutcome
    unresolved_reason: UnresolvedReason | None
    request_sha256: str | None
    content_sha256: str | None
    evidence_sha256: str | None
    dependency_sha256: str | None
    value: ReportVerification | None

    def __init__(
        self,
        *,
        shape: StageShape,
        outcome: StageOutcome,
        unresolved_reason: UnresolvedReason | None,
        request_sha256: str | None,
        content_sha256: str | None,
        evidence_sha256: str | None,
        dependency_sha256: str | None,
        value: ReportVerification | None,
        **unknown: object,
    ) -> None:
        data = dict(
            shape=shape,
            outcome=outcome,
            unresolved_reason=unresolved_reason,
            request_sha256=request_sha256,
            content_sha256=content_sha256,
            evidence_sha256=evidence_sha256,
            dependency_sha256=dependency_sha256,
            value=value,
        )

        def check() -> None:
            for digest in (request_sha256, content_sha256, evidence_sha256, dependency_sha256):
                _require(digest is None or _digest(digest))
            ver = evidence_sha256 is not None
            dep = dependency_sha256 is not None
            call = request_sha256 is not None
            if shape in (StageShape.S1, StageShape.S2):
                s1 = shape is StageShape.S1
                _require(outcome is (StageOutcome.VERIFIED if s1 else StageOutcome.ANALYZED))
                _require(unresolved_reason is None and call and content_sha256 is not None)
                _require(ver == s1 and dep != s1)
                _require((value is not None) == s1)
            else:
                _require(outcome is StageOutcome.UNRESOLVED and unresolved_reason is not None)
                _require(content_sha256 is None and value is None)
                special = {
                    StageShape.U2: UnresolvedReason.CALL_ABANDONED,
                    StageShape.U3: UnresolvedReason.VERIFICATION_UNRESOLVED,
                    StageShape.U4: UnresolvedReason.EVIDENCE_TOO_LARGE,
                    StageShape.U5: UnresolvedReason.REQUEST_TOO_LARGE,
                    StageShape.U6: UnresolvedReason.REPAIR_REQUEST_TOO_LARGE,
                }
                if shape is StageShape.U1:
                    _require(unresolved_reason not in special.values())
                else:
                    _require(unresolved_reason is special[shape])
                _require(call == (shape in (StageShape.U1, StageShape.U2, StageShape.U6)))
                if shape is StageShape.U4:
                    _require(not ver and not dep)
                elif shape is StageShape.U3:
                    _require(not ver and dep)
                else:
                    _require(ver != dep)
            if value is not None:
                data["value"] = _copy(value)

        _init(self, data, unknown, check)

    def __repr__(self) -> str:
        return f"ReportStage(shape={self.shape.value}, outcome={self.outcome.value})"

    __str__ = __repr__


@dataclass(frozen=True, init=False, repr=False)
class ReportFindingRef:
    kind: FindingKind
    index: int
    finding_id: UUID
    follow_up_questions: tuple[str, ...]

    def __init__(
        self,
        *,
        kind: FindingKind,
        index: int,
        finding_id: UUID,
        follow_up_questions: tuple[str, ...],
        **unknown: object,
    ) -> None:
        data = dict(
            kind=kind, index=index, finding_id=finding_id, follow_up_questions=follow_up_questions
        )

        def check() -> None:
            _integer(index, 0, 19 if kind is FindingKind.ANALYST else 0)
            _tuple(follow_up_questions, 0, 5 if kind is FindingKind.ANALYST else 0)
            for text in follow_up_questions:
                _text(text, 1, 500)

        _init(self, data, unknown, check)

    def __repr__(self) -> str:
        return (
            f"ReportFindingRef(kind={self.kind.value}, index={self.index}, "
            f"finding_id={self.finding_id}, follow_ups={len(self.follow_up_questions)})"
        )

    __str__ = __repr__


@dataclass(frozen=True, init=False, repr=False)
class ReportQuestion:
    question_id: str
    position: int
    plan_question_sha256: str
    verification: ReportStage
    analysis: ReportStage
    findings: tuple[ReportFindingRef, ...]

    def __init__(
        self,
        *,
        question_id: str,
        position: int,
        plan_question_sha256: str,
        verification: ReportStage,
        analysis: ReportStage,
        findings: tuple[ReportFindingRef, ...],
        **unknown: object,
    ) -> None:
        data = dict(
            question_id=question_id,
            position=position,
            plan_question_sha256=plan_question_sha256,
            verification=verification,
            analysis=analysis,
            findings=findings,
        )

        def check() -> None:
            _require(re.fullmatch(r"[A-Z][A-Z0-9]{1,9}-[0-9]{2,3}", question_id) is not None)
            _integer(position, 0, 99)
            _require(_digest(plan_question_sha256))
            _tuple(findings, 0, 21)
            v, a = _copy(verification), _copy(analysis)
            _require(v.shape in (StageShape.S1, StageShape.U4) or v.evidence_sha256 is not None)
            _require(a.dependency_sha256 is not None)
            _require((v.outcome is StageOutcome.UNRESOLVED) == (a.shape is StageShape.U3))
            refs = tuple(_copy(f) for f in findings)
            analysts = tuple(f for f in refs if f.kind is FindingKind.ANALYST)
            _require(not analysts or a.shape is StageShape.S2)
            _require(tuple(f.index for f in analysts) == tuple(range(len(analysts))))
            _require(
                tuple(f.kind for f in refs)
                in (
                    (FindingKind.ANALYST,) * len(analysts),
                    (FindingKind.DOCUMENTARY_SUPPORT_REQUIRED,)
                    + (FindingKind.ANALYST,) * len(analysts),
                )
            )
            data.update(verification=v, analysis=a, findings=refs)

        _init(self, data, unknown, check)

    def __repr__(self) -> str:
        return (
            f"ReportQuestion(question_id={self.question_id!r}, position={self.position}, "
            f"findings={len(self.findings)})"
        )

    __str__ = __repr__


@dataclass(frozen=True, init=False, repr=False)
class ReviewReportContent:
    binding: ReportBinding
    mode: ReportMode
    content: ReportContent
    questions: tuple[ReportQuestion, ...]

    def __init__(
        self,
        *,
        binding: ReportBinding,
        mode: ReportMode,
        content: ReportContent,
        questions: tuple[ReportQuestion, ...],
        **unknown: object,
    ) -> None:
        data = dict(binding=binding, mode=mode, content=content, questions=questions)

        def check() -> None:
            b = _copy(binding)
            _tuple(questions, 1, 100)
            _require(len(content.questions) == len(questions))
            if len(content.findings) > 200:
                _fail(ReportLimitExceededError)
            # Bound all nested arrays before Pydantic constructors or JSON serializers.
            for question in content.questions:
                _tuple(question.search_queries, 1, 5)
                _require(len(set(question.search_queries)) == len(question.search_queries))
            for finding in content.findings:
                _tuple(finding.citations, 0, 80)
            c = _rebuild_model(content, ReportContent)
            qs = tuple(_copy(q) for q in questions)
            _require(c.tenant_id == b.tenant_id)
            ordered: list[UUID] = []
            unresolved: list[str] = []
            by_id = {f.finding_id: f for f in c.findings}
            for position, (q, source) in enumerate(zip(qs, c.questions, strict=True)):
                _require(q.position == position and q.question_id == source.question_id)
                _require(q.plan_question_sha256 == plan_question_sha256(source))
                v, a = q.verification, q.analysis
                _require(
                    a.dependency_sha256
                    == dependency_sha256(
                        tenant_id=b.tenant_id,
                        review_id=b.review_id,
                        question_id=q.question_id,
                        question_sha256=q.plan_question_sha256,
                        owner_outcome=v.outcome,
                        owner_content_sha256=v.content_sha256,
                        owner_reason=v.unresolved_reason,
                    )
                )
                value = v.value
                rule = (
                    value is not None
                    and source.requires_documentary_support
                    and (value.evidence_status is EvidenceStatus.VENDOR_CLAIM)
                )
                _require(
                    bool(
                        q.findings
                        and q.findings[0].kind is FindingKind.DOCUMENTARY_SUPPORT_REQUIRED
                    )
                    == rule
                )
                if value is not None:
                    _require(all(x.tenant_id == b.tenant_id for x in value.citations))
                    Verification(
                        tenant_id=b.tenant_id,
                        question_id=q.question_id,
                        verdict=value.verdict,
                        evidence_status=value.evidence_status,
                        rationale=value.rationale,
                        citations=value.citations,
                    )
                for ref in q.findings:
                    _require(
                        ref.finding_id
                        == finding_id(b.tenant_id, b.review_id, q.question_id, ref.kind, ref.index)
                    )
                    _require(ref.finding_id in by_id and ref.finding_id not in ordered)
                    f = by_id[ref.finding_id]
                    _require(f.question_ids == (q.question_id,))
                    assert value is not None
                    if ref.kind is FindingKind.DOCUMENTARY_SUPPORT_REQUIRED:
                        _require(
                            f.title == DOCUMENTARY_GAP_TITLE
                            and f.statement == DOCUMENTARY_GAP_STATEMENT
                            and f.severity is Severity.MEDIUM
                            and f.evidence_status is EvidenceStatus.MISSING
                            and f.citations == value.citations
                        )
                    else:
                        _tuple(f.citations, 0, 8)
                        _require(all(x in value.citations for x in f.citations))
                        status = (
                            EvidenceStatus.MISSING
                            if not f.citations or value.verdict is Verdict.INSUFFICIENT_EVIDENCE
                            else derive_status(value.verdict, f.citations)
                        )
                        _require(status is f.evidence_status)
                    ordered.append(ref.finding_id)
                if _unresolved(source, q, tuple(by_id[r.finding_id] for r in q.findings)):
                    unresolved.append(q.question_id)
            _require(tuple(ordered) == tuple(f.finding_id for f in c.findings))
            _require(tuple(unresolved) == c.unresolved_question_ids)
            data.update(binding=b, content=c, questions=qs)
            legacy = _bounded_json(
                {"schema": LEGACY_SCHEMA, "content": c.model_dump(mode="json")},
                MAX_LEGACY_BYTES,
                ascii_only=False,
            )
            _require(legacy == canonical_content_bytes(c))

        _init(self, data, unknown, check)
        # Include the wrapper cap in constructor validation, without recursive revalidation.
        _run(lambda: _encoded(self), InvalidReportValueError)

    @property
    def schema(self) -> str:
        return SCHEMA

    @property
    def renderer(self) -> str:
        return RENDERER

    @property
    def legacy_sha256(self) -> str:
        return hashlib.sha256(canonical_content_bytes(self.content)).hexdigest()

    def __repr__(self) -> str:
        return (
            f"ReviewReportContent(schema={SCHEMA!r}, review_id={self.binding.review_id}, "
            f"questions={len(self.questions)}, findings={len(self.content.findings)})"
        )

    __str__ = __repr__


def _copy[T](value: T) -> T:
    return type(value)(**{f.name: getattr(value, f.name) for f in dataclasses.fields(value)})  # type: ignore[arg-type]


def _unresolved(
    question: EvidenceQuestion, item: ReportQuestion, findings: tuple[Finding, ...]
) -> bool:
    return bool(unresolved_causes(question, item, findings))


def unresolved_causes(
    question: EvidenceQuestion, item: ReportQuestion, findings: tuple[Finding, ...]
) -> tuple[str, ...]:
    """Fixed presentation labels, derived exclusively from validated hash-covered fields."""
    conditions = (
        ("verification_unresolved", item.verification.outcome is StageOutcome.UNRESOLVED),
        ("analysis_unresolved", item.analysis.outcome is StageOutcome.UNRESOLVED),
        (
            "documentary_support_required",
            any(r.kind is FindingKind.DOCUMENTARY_SUPPORT_REQUIRED for r in item.findings),
        ),
        (
            "missing_evidence_finding",
            any(f.evidence_status is EvidenceStatus.MISSING for f in findings),
        ),
        (
            "no_resolving_finding",
            not any(
                f.evidence_status
                in (EvidenceStatus.DOCUMENTARY_SUPPORT, EvidenceStatus.CONFLICTING)
                or (
                    f.evidence_status is EvidenceStatus.VENDOR_CLAIM
                    and not question.requires_documentary_support
                )
                for f in findings
            ),
        ),
    )
    return tuple(label for label, condition in conditions if condition)


def _bounded_json(value: object, cap: int, *, ascii_only: bool = True) -> bytes:
    result = bytearray()
    encoder = json.JSONEncoder(
        sort_keys=True, separators=(",", ":"), ensure_ascii=ascii_only, allow_nan=False
    )
    for piece in encoder.iterencode(value):
        raw = piece.encode("ascii" if ascii_only else "utf-8")
        if len(result) + len(raw) > cap:
            _fail(ReportLimitExceededError)
        result.extend(raw)
    return bytes(result)


def _object(value: object) -> Any:
    if isinstance(value, Enum):
        return value.value
    if type(value) is UUID:
        return str(value)
    if isinstance(value, DomainModel):
        return value.model_dump(mode="json")
    if type(value) is tuple:
        return [_object(v) for v in value]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: _object(getattr(value, f.name)) for f in dataclasses.fields(value)}
    return value


def _encoded(value: ReviewReportContent) -> bytes:
    b = value.binding
    obj = {
        "schema": SCHEMA,
        "renderer": RENDERER,
        "mode": value.mode.value,
        "binding": {
            **{
                k: _object(getattr(b, k))
                for k in (
                    "tenant_id",
                    "review_id",
                    "vendor_id",
                    "job_id",
                    "review_request_sha256",
                    "snapshot_sha256",
                )
            },
            "configuration": b.configuration.canonical_object(),
            "configuration_sha256": b.configuration_sha256,
        },
        "legacy": {"schema": LEGACY_SCHEMA, "content": _object(value.content)},
        "legacy_sha256": value.legacy_sha256,
        "questions": _object(value.questions),
    }
    raw = _bounded_json(obj, MAX_CONTENT_BYTES)
    _lex(raw)
    return raw


def revalidate_review_report(value: ReviewReportContent) -> ReviewReportContent:
    def build() -> ReviewReportContent:
        _preflight(value, ReviewReportContent)
        return _copy(value)

    return _run(build, InvalidReportValueError)


def review_report_bytes(content: ReviewReportContent) -> bytes:
    return _run(lambda: _encoded(revalidate_review_report(content)), InvalidReportValueError)


def review_report_sha256(content: ReviewReportContent) -> str:
    return _run(
        lambda: hashlib.sha256(review_report_bytes(content)).hexdigest(), InvalidReportValueError
    )


def _lex(data: bytes) -> None:
    """Bounded pre-parse scan: strings/escapes do not affect structural counts or depth."""
    if len(data) > MAX_CONTENT_BYTES:
        _fail(ReportLimitExceededError)
    _require(data.isascii() and not data.startswith(b"\xef\xbb\xbf"))
    depth = tokens = i = 0
    while i < len(data):
        c = data[i]
        if c in (123, 91):
            depth += 1
            tokens += 1
        elif c in (125, 93):
            depth -= 1
            _require(depth >= 0)
        elif c == 34:
            tokens += 1
            i += 1
            while i < len(data) and data[i] != 34:
                _require(data[i] >= 32)
                if data[i] == 92:
                    i += 1
                    _require(i < len(data) and data[i] in b'"\\/bfnrtu')
                    if data[i] == 117:
                        _require(
                            i + 4 < len(data)
                            and all(x in b"0123456789abcdefABCDEF" for x in data[i + 1 : i + 5])
                        )
                        i += 4
                i += 1
            _require(i < len(data))
        elif c in b"-0123456789":
            end = i + 1
            while end < len(data) and data[end] not in b",]}: \t\r\n":
                end += 1
            literal = data[i:end]
            _require(len(literal) <= 10 and re.fullmatch(rb"0|[1-9][0-9]*", literal) is not None)
            _require(int(literal) <= MAX_INTEGER)
            tokens += 1
            i = end - 1
        elif c in b"tfn":
            word = b"true" if c == 116 else b"false" if c == 102 else b"null"
            _require(data[i : i + len(word)] == word)
            tokens += 1
            i += len(word) - 1
        else:
            _require(c in b",:")
        if depth > MAX_DEPTH or tokens > MAX_TOKENS:
            _fail(ReportLimitExceededError)
        i += 1
    _require(depth == 0)


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def _keys(value: Any, keys: set[str]) -> dict[str, Any]:
    _require(type(value) is dict and set(value) == keys)
    return cast(dict[str, Any], value)


def _decode(value: Any, annotation: Any) -> Any:
    origin, args = get_origin(annotation), get_args(annotation)
    if origin in (Union, types.UnionType):
        if value is None and type(None) in args:
            return None
        return _decode(value, next(a for a in args if a is not type(None)))
    if origin is tuple:
        _require(type(value) is list)
        return tuple(_decode(v, args[0]) for v in value)
    if annotation is UUID:
        _require(type(value) is str)
        parsed = UUID(value)
        _require(str(parsed) == value)
        return parsed
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        _require(type(value) is str)
        return annotation(value)
    if annotation in (str, int, bool):
        _require(type(value) is annotation)
        return value
    hints = get_type_hints(annotation)
    names = (
        set(annotation.model_fields)
        if issubclass(annotation, DomainModel)
        else {f.name for f in dataclasses.fields(annotation) if f.init}
    )
    obj = _keys(value, names)
    fields = {k: _decode(v, hints[k]) for k, v in obj.items()}
    if issubclass(annotation, DomainModel):
        for item in fields.values():
            _model_texts(item)
    return annotation(**fields)


def _decode_configuration(value: Any) -> ReviewConfiguration:
    obj = _keys(
        value,
        {
            "canonical",
            "kind",
            "template",
            "verifier_prompt",
            "analyst_prompt",
            "model",
            "retrieval_k",
        },
    )
    _require(
        obj["canonical"] == "eg-review-configuration-v1" and obj["kind"] == "review_configuration"
    )
    refs = [
        _keys(obj[k], {"id", "version", "sha256"})
        for k in ("template", "verifier_prompt", "analyst_prompt")
    ]
    model = _keys(obj["model"], {"model_id", "max_output_tokens", "timeout_ms"})

    def prompt(ref: dict[str, Any]) -> PromptRef:
        return PromptRef(prompt_id=ref["id"], version=ref["version"], sha256=ref["sha256"])

    c = ReviewConfiguration(
        template_id=refs[0]["id"],
        template_version=refs[0]["version"],
        template_sha256=refs[0]["sha256"],
        verifier_prompt=prompt(refs[1]),
        analyst_prompt=prompt(refs[2]),
        retrieval_k=obj["retrieval_k"],
        **model,
    )
    _require(c.canonical_object() == obj)
    return c


def decode_review_report(data: bytes, *, expected_sha256: str) -> ReviewReportContent:
    def build() -> ReviewReportContent:
        if type(data) is not bytes or not _digest(expected_sha256):
            _fail(InvalidReportInputError)
        _lex(data)
        obj = json.loads(data, object_pairs_hook=_pairs)
        # Bare legacy envelopes have an explicitly unsupported version rather than an upgrade.
        _require(type(obj) is dict)
        if set(obj) == {"schema", "content"} and obj["schema"] == LEGACY_SCHEMA:
            _fail(UnsupportedReportSchemaError)
        _keys(
            obj, {"schema", "renderer", "mode", "binding", "legacy", "legacy_sha256", "questions"}
        )
        if obj["schema"] != SCHEMA or obj["renderer"] != RENDERER:
            _fail(UnsupportedReportSchemaError)
        binding = _keys(
            obj["binding"],
            {
                "tenant_id",
                "review_id",
                "vendor_id",
                "job_id",
                "review_request_sha256",
                "snapshot_sha256",
                "configuration",
                "configuration_sha256",
            },
        )
        config = _decode_configuration(binding["configuration"])
        _require(config.configuration_sha256 == binding["configuration_sha256"])
        b = ReportBinding(
            **{
                k: _decode(binding[k], UUID)
                for k in ("tenant_id", "review_id", "vendor_id", "job_id")
            },
            review_request_sha256=binding["review_request_sha256"],
            snapshot_sha256=binding["snapshot_sha256"],
            configuration=config,
        )
        legacy = _keys(obj["legacy"], {"schema", "content"})
        _require(legacy["schema"] == LEGACY_SCHEMA)
        if (
            type(legacy["content"]) is dict
            and type(legacy["content"].get("findings")) is list
            and len(legacy["content"]["findings"]) > 200
        ):
            _fail(ReportLimitExceededError)
        value = ReviewReportContent(
            binding=b,
            mode=_decode(obj["mode"], ReportMode),
            content=_decode(legacy["content"], ReportContent),
            questions=_decode(obj["questions"], tuple[ReportQuestion, ...]),
        )
        _require(value.legacy_sha256 == obj["legacy_sha256"])
        encoded = _encoded(value)
        _require(encoded == data)
        if hashlib.sha256(encoded).hexdigest() != expected_sha256:
            _fail(ReportDigestMismatchError)
        return value

    return _run(build, InvalidReportEncodingError)
