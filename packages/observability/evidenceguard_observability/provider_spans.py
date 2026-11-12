"""Closed, ephemeral provider-call spans (accepted M5 completion contract, Prompt 234).

Only trusted correlation metadata is admitted. These leaf spans are not durable reservations,
provider receipts or proof of stage persistence. No payload, exception or arbitrary tag is kept.
"""

import re
from dataclasses import dataclass, replace
from threading import Lock
from typing import Literal, Protocol
from uuid import UUID, uuid5

Stage = Literal["verification", "analysis"]
TimingStatus = Literal["ok", "start_unavailable", "end_unavailable", "invalid_interval"]
SpanOutcome = Literal[
    "completed",
    "refusal",
    "timeout",
    "invalid_output",
    "provider_failed",
    "model_mismatch",
    "max_tokens",
    "unexpected_stop",
]
ExitKind = Literal[
    "returned", "cancelled", "lease_lost", "fence_closed", "process_control", "local_error"
]
_TRACE_NAMESPACE = UUID("30000000-0000-4000-8000-000000000001")
_SPAN_NAMESPACE = UUID("30000000-0000-4000-8000-000000000002")
_QUESTION = re.compile(r"[A-Z][A-Z0-9]{1,9}-[0-9]{2,3}", re.ASCII)
_HASH = re.compile(r"[0-9a-f]{64}", re.ASCII)
_NS_BOUND = 2**63 - 1
_OUTCOMES = frozenset(
    {
        "completed",
        "refusal",
        "timeout",
        "invalid_output",
        "provider_failed",
        "model_mismatch",
        "max_tokens",
        "unexpected_stop",
    }
)
_EXITS = frozenset(
    {"returned", "cancelled", "lease_lost", "fence_closed", "process_control", "local_error"}
)


def _require(condition: bool) -> None:
    if not condition:
        raise ValueError("invalid_provider_call_span")


def _reading(value: object) -> bool:
    return type(value) is int and 0 <= value <= _NS_BOUND


def provider_call_ids(
    *,
    tenant_id: UUID,
    review_id: UUID,
    job_id: UUID,
    question_id: str,
    stage: Stage,
    sequence: int,
    job_attempt: int,
) -> tuple[UUID, UUID]:
    """Return deterministic (trace, leaf-span) IDs for a validated reserved-call identity."""
    _require(all(type(v) is UUID for v in (tenant_id, review_id, job_id)))
    _require(type(question_id) is str and _QUESTION.fullmatch(question_id) is not None)
    _require(type(stage) is str and stage in ("verification", "analysis"))
    _require(type(sequence) is int and 1 <= sequence <= 3)
    _require(type(job_attempt) is int and 1 <= job_attempt <= 3)
    return (
        uuid5(_TRACE_NAMESPACE, tenant_id.hex + ":" + review_id.hex),
        uuid5(
            _SPAN_NAMESPACE,
            ":".join(
                (
                    tenant_id.hex,
                    review_id.hex,
                    job_id.hex,
                    question_id,
                    stage,
                    str(sequence),
                    str(job_attempt),
                )
            ),
        ),
    )


@dataclass(frozen=True, slots=True, kw_only=True, init=False, repr=False)
class ProviderCallSpan:
    """One completed leaf interval; construction and revalidation never coerce payloads."""

    schema_version: Literal["evidenceguard.provider-call-span.v1"]
    trace_id: UUID
    span_id: UUID
    tenant_id: UUID
    review_id: UUID
    job_id: UUID
    question_id: str
    stage: Stage
    sequence: int
    job_attempt: int
    request_sha256: str
    started_ns: int | None
    ended_ns: int | None
    duration_ns: int | None
    timing_status: TimingStatus
    call_outcome: SpanOutcome | None
    exit_kind: ExitKind

    def __init__(
        self,
        *,
        trace_id: UUID,
        span_id: UUID,
        tenant_id: UUID,
        review_id: UUID,
        job_id: UUID,
        question_id: str,
        stage: Stage,
        sequence: int,
        job_attempt: int,
        request_sha256: str,
        started_ns: int | None,
        ended_ns: int | None,
        duration_ns: int | None,
        timing_status: TimingStatus,
        call_outcome: SpanOutcome | None,
        exit_kind: ExitKind,
        schema_version: Literal[
            "evidenceguard.provider-call-span.v1"
        ] = "evidenceguard.provider-call-span.v1",
        **unknown: object,
    ) -> None:
        failed = False
        try:
            _require(type(self) is ProviderCallSpan and not unknown)
            _require(
                type(schema_version) is str
                and schema_version == "evidenceguard.provider-call-span.v1"
            )
            ids = provider_call_ids(
                tenant_id=tenant_id,
                review_id=review_id,
                job_id=job_id,
                question_id=question_id,
                stage=stage,
                sequence=sequence,
                job_attempt=job_attempt,
            )
            _require(type(trace_id) is UUID and type(span_id) is UUID)
            _require((trace_id, span_id) == ids)
            _require(type(request_sha256) is str and _HASH.fullmatch(request_sha256) is not None)
            _require(
                all(
                    value is None or _reading(value)
                    for value in (started_ns, ended_ns, duration_ns)
                )
            )
            _require(type(timing_status) is str)
            if started_ns is None:
                _require(timing_status == "start_unavailable" and duration_ns is None)
            elif ended_ns is None:
                _require(timing_status == "end_unavailable" and duration_ns is None)
            elif ended_ns < started_ns:
                _require(timing_status == "invalid_interval" and duration_ns is None)
            else:
                _require(timing_status == "ok" and duration_ns == ended_ns - started_ns)
            _require(
                call_outcome is None or (type(call_outcome) is str and call_outcome in _OUTCOMES)
            )
            _require(type(exit_kind) is str and exit_kind in _EXITS)
            _require(exit_kind != "returned" or call_outcome is not None)
        except Exception:
            failed = True
        if failed:
            raise ValueError("invalid_provider_call_span")
        for name, value in (
            ("schema_version", schema_version),
            ("trace_id", trace_id),
            ("span_id", span_id),
            ("tenant_id", tenant_id),
            ("review_id", review_id),
            ("job_id", job_id),
            ("question_id", question_id),
            ("stage", stage),
            ("sequence", sequence),
            ("job_attempt", job_attempt),
            ("request_sha256", request_sha256),
            ("started_ns", started_ns),
            ("ended_ns", ended_ns),
            ("duration_ns", duration_ns),
            ("timing_status", timing_status),
            ("call_outcome", call_outcome),
            ("exit_kind", exit_kind),
        ):
            object.__setattr__(self, name, value)


def _rebuilt_span(value: object) -> ProviderCallSpan:
    if type(value) is not ProviderCallSpan:
        raise ValueError("invalid_provider_call_span")
    return replace(value)


class SpanSink(Protocol):
    def emit(self, span: ProviderCallSpan) -> None: ...


class BoundedSpanCollector:
    """Thread-safe process-local prefix, dropping new records when full; no backpressure."""

    def __init__(self, *, capacity: int = 256) -> None:
        _require(type(capacity) is int and 1 <= capacity <= 4096)
        self._capacity = capacity
        self._lock = Lock()
        self._records: list[ProviderCallSpan] = []
        self._dropped = 0

    def emit(self, span: ProviderCallSpan) -> None:
        checked = _rebuilt_span(span)
        with self._lock:
            if len(self._records) == self._capacity:
                self._dropped += 1
            else:
                self._records.append(checked)

    def snapshot(self) -> tuple[ProviderCallSpan, ...]:
        with self._lock:
            return tuple(self._records)

    @property
    def dropped_count(self) -> int:
        with self._lock:
            return self._dropped
