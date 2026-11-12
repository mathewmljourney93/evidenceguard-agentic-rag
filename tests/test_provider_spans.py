"""Pure values/collector tests for the accepted M5 completion span contract; no database."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, fields, replace
from typing import Any
from uuid import UUID, uuid5

import pytest

from evidenceguard_observability.provider_spans import (
    BoundedSpanCollector,
    ProviderCallSpan,
    provider_call_ids,
)

BOUND = 2**63 - 1


def values(**changes: Any) -> dict[str, Any]:
    identity: dict[str, Any] = {
        "tenant_id": UUID(int=1),
        "review_id": UUID(int=2),
        "job_id": UUID(int=3),
        "question_id": "SEC-01",
        "stage": "verification",
        "sequence": 1,
        "job_attempt": 1,
    }
    trace, span = provider_call_ids(**identity)
    return (
        dict(
            identity,
            trace_id=trace,
            span_id=span,
            request_sha256="a" * 64,
            started_ns=10,
            ended_ns=15,
            duration_ns=5,
            timing_status="ok",
            call_outcome="completed",
            exit_kind="returned",
        )
        | changes
    )


def test_ids_have_exact_namespaces_names_and_reservation_correlation() -> None:
    v = values()
    assert v["trace_id"] == uuid5(
        UUID("30000000-0000-4000-8000-000000000001"), UUID(int=1).hex + ":" + UUID(int=2).hex
    )
    assert v["span_id"] == uuid5(
        UUID("30000000-0000-4000-8000-000000000002"),
        ":".join(
            (UUID(int=1).hex, UUID(int=2).hex, UUID(int=3).hex, "SEC-01", "verification", "1", "1")
        ),
    )
    identity = {
        k: v[k]
        for k in (
            "tenant_id",
            "review_id",
            "job_id",
            "question_id",
            "stage",
            "sequence",
            "job_attempt",
        )
    }
    for key, value in {
        "tenant_id": UUID(int=9),
        "review_id": UUID(int=9),
        "job_id": UUID(int=9),
        "question_id": "SEC-02",
        "stage": "analysis",
        "sequence": 2,
        "job_attempt": 2,
    }.items():
        trace, span = provider_call_ids(**(identity | {key: value}))
        assert span != v["span_id"]
        assert (trace != v["trace_id"]) == (key in {"tenant_id", "review_id"})


@pytest.mark.parametrize(
    ("start", "end", "status", "duration"),
    [
        (None, None, "start_unavailable", None),
        (None, 0, "start_unavailable", None),
        (None, BOUND, "start_unavailable", None),
        (0, None, "end_unavailable", None),
        (BOUND, None, "end_unavailable", None),
        (1, 0, "invalid_interval", None),
        (BOUND, 0, "invalid_interval", None),
        (0, 0, "ok", 0),
        (0, BOUND, "ok", BOUND),
        (BOUND, BOUND, "ok", 0),
        (10, 15, "ok", 5),
    ],
)
def test_complete_timing_validation_table(
    start: int | None, end: int | None, status: str, duration: int | None
) -> None:
    data = values(started_ns=start, ended_ns=end, timing_status=status, duration_ns=duration)
    assert replace(ProviderCallSpan(**data)) == ProviderCallSpan(**data)
    for contradictory in {"ok", "start_unavailable", "end_unavailable", "invalid_interval"} - {
        status
    }:
        with pytest.raises(ValueError, match=r"^invalid_provider_call_span$"):
            ProviderCallSpan(**(data | {"timing_status": contradictory}))
    with pytest.raises(ValueError, match=r"^invalid_provider_call_span$"):
        ProviderCallSpan(**(data | {"duration_ns": 17}))


@pytest.mark.parametrize("field", ["started_ns", "ended_ns", "duration_ns"])
@pytest.mark.parametrize("bad", [True, False, -1, BOUND + 1, 1.0, "1", float("nan"), object()])
def test_unusable_external_readings_are_rejected_not_coerced(field: str, bad: object) -> None:
    with pytest.raises(ValueError, match=r"^invalid_provider_call_span$") as caught:
        ProviderCallSpan(**values(**{field: bad}))
    assert caught.value.__cause__ is None and caught.value.__context__ is None


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("schema_version", "unknown"),
        ("trace_id", UUID(int=9)),
        ("span_id", UUID(int=9)),
        ("tenant_id", "1"),
        ("review_id", None),
        ("job_id", 3),
        ("question_id", "secret text"),
        ("question_id", "SEC-01\n"),
        ("stage", "other"),
        ("sequence", True),
        ("sequence", 0),
        ("sequence", 4),
        ("job_attempt", False),
        ("job_attempt", 4),
        ("request_sha256", "A" * 64),
        ("request_sha256", "a" * 63),
        ("call_outcome", "cancelled"),
        ("exit_kind", "unknown"),
        ("call_outcome", None),
        ("prompt", "submitted text"),
    ],
)
def test_closed_value_rejects_invalid_metadata_and_unknown_fields(field: str, bad: object) -> None:
    with pytest.raises(ValueError, match=r"^invalid_provider_call_span$"):
        ProviderCallSpan(**values(**{field: bad}))


@pytest.mark.parametrize(
    "outcome",
    [
        "completed",
        "refusal",
        "timeout",
        "invalid_output",
        "provider_failed",
        "model_mismatch",
        "max_tokens",
        "unexpected_stop",
    ],
)
@pytest.mark.parametrize(
    "exit_kind",
    ["returned", "cancelled", "lease_lost", "fence_closed", "process_control", "local_error"],
)
def test_all_classified_outcomes_and_exit_kinds(outcome: str, exit_kind: str) -> None:
    assert (
        ProviderCallSpan(**values(call_outcome=outcome, exit_kind=exit_kind)).call_outcome
        == outcome
    )


@pytest.mark.parametrize(
    "exit_kind", ["cancelled", "lease_lost", "fence_closed", "process_control", "local_error"]
)
def test_interrupted_boundary_can_have_no_observed_outcome(exit_kind: str) -> None:
    assert ProviderCallSpan(**values(call_outcome=None, exit_kind=exit_kind)).call_outcome is None


def test_value_is_immutable_closed_and_does_not_render_content() -> None:
    span = ProviderCallSpan(**values())
    assert len(fields(span)) == 17 and not hasattr(span, "__dict__")
    with pytest.raises(FrozenInstanceError):
        span.question_id = "SEC-02"  # type: ignore[misc]
    assert "SEC-01" not in repr(span) and "a" * 64 not in repr(span)

    class Subclass(ProviderCallSpan):
        pass

    with pytest.raises(ValueError, match=r"^invalid_provider_call_span$"):
        Subclass(**values())


@pytest.mark.parametrize("capacity", [True, 0, -1, 4097, 1.0, None])
def test_collector_rejects_invalid_capacity(capacity: Any) -> None:
    with pytest.raises(ValueError, match=r"^invalid_provider_call_span$"):
        BoundedSpanCollector(capacity=capacity)


def test_collector_revalidates_copies_preserves_prefix_and_counts_drops() -> None:
    sink = BoundedSpanCollector(capacity=1)
    original = ProviderCallSpan(**values())
    sink.emit(original)
    object.__setattr__(original, "request_sha256", "private mutation")
    assert sink.snapshot()[0].request_sha256 == "a" * 64
    with pytest.raises(ValueError, match=r"^invalid_provider_call_span$"):
        sink.emit(original)
    with pytest.raises(ValueError, match=r"^invalid_provider_call_span$"):
        sink.emit({"prompt": "not a span"})  # type: ignore[arg-type]
    sink.emit(ProviderCallSpan(**values(call_outcome="refusal")))
    assert len(sink.snapshot()) == 1 and sink.dropped_count == 1
    assert sink.snapshot()[0].call_outcome == "completed"


def test_collector_is_bounded_under_concurrent_emitters() -> None:
    sink = BoundedSpanCollector(capacity=17)
    span = ProviderCallSpan(**values())
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(sink.emit, [span] * 256))
    assert sink.snapshot() == (span,) * 17 and sink.dropped_count == 239
    # Two tenants concurrently share a collector, without changing either trace identity.
    other_values = values(tenant_id=UUID(int=9))
    other_values["trace_id"], other_values["span_id"] = provider_call_ids(
        **{
            name: other_values[name]
            for name in (
                "tenant_id",
                "review_id",
                "job_id",
                "question_id",
                "stage",
                "sequence",
                "job_attempt",
            )
        }
    )
    other = ProviderCallSpan(**other_values)
    shared = BoundedSpanCollector(capacity=256)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(shared.emit, [span, other] * 128))
    records = shared.snapshot()
    assert len(records) == 256 and shared.dropped_count == 0
    assert {s.trace_id for s in records} == {span.trace_id, other.trace_id}
    assert sum(s.tenant_id == span.tenant_id for s in records) == 128
    assert sum(s.tenant_id == other.tenant_id for s in records) == 128
