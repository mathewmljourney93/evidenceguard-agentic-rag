"""The M5e planner and whole-history rules (``StageHistory`` V1-V12, ``plan_stage`` T0-T9;
``evidenceguard_domain.review_stages``, ADR-0023), without a database or network.

An independent oracle, written here from the accepted tables (``docs/plan.md`` M5e-D), decides
validity and the expected plan. The enumeration covers every call of every kind, basis, state,
outcome, rejection mapping, digest choice and attempt assignment as a one-step extension of every
valid history of up to two calls, at current attempts 1-3, so every history of up to three calls
whose proper prefixes are valid is checked; a history with an invalid proper prefix is invalid
by the same rules and is covered by the targeted cases below.
"""

import socket
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import product
from typing import Any
from uuid import UUID

import pytest

from evidenceguard_domain.model_calls import CallOutcome, ModelUsage
from evidenceguard_domain.provenance import RejectionReason
from evidenceguard_domain.review_stages import (
    CallKind,
    CallRecord,
    CallRejection,
    InvalidStageHistoryError,
    InvalidStageValueError,
    PlanDispatch,
    PlanExhausted,
    PlanInFlight,
    PlanReuse,
    RequestBasis,
    ReservationState,
    StageHistory,
    StageKind,
    StageOutcome,
    StagePlan,
    StageRecord,
    UnresolvedReason,
    plan_stage,
    plan_without_stage,
)

TENANT = UUID("11111111-1111-4111-8111-111111111111")
REVIEW = UUID("88888888-8888-4888-8888-888888888888")
JOB = UUID("77777777-7777-4777-8777-777777777777")
QUESTION = "ENC-01"
ORIGINAL = "a" * 64
REPAIRED = "b" * 64
EVIDENCE = "e" * 64
T0 = datetime(2026, 10, 23, 9, 0, tzinfo=UTC)

CITATION = CallRejection(
    stage=StageKind.VERIFICATION,
    reason=RejectionReason.QUOTE_NOT_FOUND,
    item_index=0,
    citation_index=0,
    rejected_count=1,
)
AGGREGATE = CallRejection(
    stage=StageKind.VERIFICATION,
    reason=RejectionReason.VERDICT_UNSUPPORTED,
    item_index=None,
    citation_index=None,
    rejected_count=1,
)


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("a test attempted network access")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


# --- call construction ----------------------------------------------------------------------------


@dataclass(frozen=True)
class Spec:
    """A test-owned description of one call; ``outcome`` ``None`` means ``started``."""

    kind: CallKind
    basis: RequestBasis
    digest: str
    attempt: int
    outcome: CallOutcome | None = None
    rejection: CallRejection | None = None

    @property
    def success(self) -> bool:
        return self.outcome is CallOutcome.COMPLETED and self.rejection is None

    @property
    def repair_trigger(self) -> bool:
        return self.outcome is CallOutcome.INVALID_OUTPUT or self.rejection is not None


def build(spec: Spec, sequence: int) -> CallRecord:
    values: dict[str, Any] = {
        "tenant_id": TENANT,
        "review_id": REVIEW,
        "job_id": JOB,
        "question_id": QUESTION,
        "stage": StageKind.VERIFICATION,
        "sequence": sequence,
        "call_kind": spec.kind,
        "request_basis": spec.basis,
        "request_sha256": spec.digest,
        "prompt_sha256": "1" * 64,
        "model_requested": "fake-scripted-v1",
        "max_output_tokens": 4096,
        "timeout_ms": 60_000,
        "evidence_sha256": EVIDENCE,
        "dependency_sha256": None,
        "job_attempt": spec.attempt,
        "state": ReservationState.STARTED,
        # deliberately decreasing wall-clock readings: no ordering is required (V12)
        "started_at": T0 - timedelta(minutes=sequence),
    }
    if spec.outcome is not None:
        response = spec.outcome not in (CallOutcome.TIMEOUT, CallOutcome.PROVIDER_FAILED)
        mismatch = spec.outcome is CallOutcome.MODEL_MISMATCH
        values.update(
            state=ReservationState.COMPLETED,
            completed_at=T0 - timedelta(hours=sequence),
            outcome=spec.outcome,
            dispatched=True,
            model_used=None if not response else ("other" if mismatch else "fake-scripted-v1"),
            usage=ModelUsage(1, 1) if response else None,
            latency_ms=1,
            rejection=spec.rejection,
        )
    return CallRecord(**values)


def history(
    specs: tuple[Spec, ...], current: int, committed: StageRecord | None = None
) -> StageHistory:
    return StageHistory(
        tenant_id=TENANT,
        review_id=REVIEW,
        job_id=JOB,
        question_id=QUESTION,
        stage=StageKind.VERIFICATION,
        current_attempt=current,
        calls=tuple(build(spec, index) for index, spec in enumerate(specs, start=1)),
        committed=committed,
    )


# --- the independent oracle -----------------------------------------------------------------------

RETRYABLE = {CallOutcome.TIMEOUT, CallOutcome.PROVIDER_FAILED}
TERMINAL = {
    CallOutcome.REFUSAL,
    CallOutcome.MAX_TOKENS,
    CallOutcome.UNEXPECTED_STOP,
    CallOutcome.MODEL_MISMATCH,
}


def oracle_valid(specs: tuple[Spec, ...], current: int) -> bool:
    """V3-V10 for histories without a committed stage, from the accepted text."""
    if any(spec.attempt > current for spec in specs):
        return False
    for index in range(1, len(specs)):
        previous, call = specs[index - 1], specs[index]
        if previous.attempt > call.attempt:
            return False
        if previous.outcome is None or previous.outcome in RETRYABLE:
            if previous.outcome is None and previous.attempt >= call.attempt:
                return False
            if call.kind is not CallKind.RETRY or call.basis is not previous.basis:
                return False
            if call.digest != previous.digest:
                return False
        elif previous.repair_trigger and not any(s.kind is CallKind.REPAIR for s in specs[:index]):
            if call.kind is not CallKind.REPAIR or call.digest == specs[0].digest:
                return False
        else:
            return False
    originals = {s.digest for s in specs if s.basis is RequestBasis.ORIGINAL}
    repaired = {s.digest for s in specs if s.basis is RequestBasis.REPAIRED}
    if len(originals) > 1 or len(repaired) > 1 or originals & repaired:
        return False
    return not any(spec.success for spec in specs)  # V9: a success needs its stage


def oracle_reason(spec: Spec) -> UnresolvedReason:
    if spec.rejection is not None:
        return UnresolvedReason(spec.rejection.stage_reason.value)
    assert spec.outcome is not None
    return UnresolvedReason(spec.outcome.value)


def oracle_plan(specs: tuple[Spec, ...], current: int) -> tuple[Any, ...]:
    """T1-T9 as a comparable tuple."""
    n = len(specs)
    if n == 0:
        return ("dispatch", 1, CallKind.INITIAL, RequestBasis.ORIGINAL, None, None, None, None)
    last = specs[-1]

    def retry() -> tuple[Any, ...]:
        trigger = None
        if last.basis is RequestBasis.REPAIRED:
            trigger = next(i for i, s in enumerate(specs, start=1) if s.kind is CallKind.REPAIR) - 1
        return ("dispatch", n + 1, CallKind.RETRY, last.basis, n, trigger, last.digest, None)

    if last.outcome is None:
        if last.attempt == current:
            return ("in_flight", n, last.digest)
        if n < 3:
            return retry()
        return ("exhausted", UnresolvedReason.CALL_ABANDONED, n, last.digest)
    if last.outcome in RETRYABLE:
        return retry() if n < 3 else ("exhausted", oracle_reason(last), n, last.digest)
    if last.repair_trigger:
        if n < 3 and not any(s.kind is CallKind.REPAIR for s in specs):
            return (
                "dispatch",
                n + 1,
                CallKind.REPAIR,
                RequestBasis.REPAIRED,
                n,
                n,
                None,
                specs[0].digest,
            )
        return ("exhausted", oracle_reason(last), n, last.digest)
    assert last.outcome in TERMINAL
    return ("exhausted", oracle_reason(last), n, last.digest)


def as_tuple(plan: StagePlan) -> tuple[Any, ...]:
    if isinstance(plan, PlanDispatch):
        return (
            "dispatch",
            plan.sequence,
            plan.call_kind,
            plan.request_basis,
            plan.predecessor,
            plan.trigger,
            plan.required_request_sha256,
            plan.original_request_sha256,
        )
    if isinstance(plan, PlanInFlight):
        return ("in_flight", plan.sequence, plan.request_sha256)
    if isinstance(plan, PlanExhausted):
        return ("exhausted", plan.reason, plan.sequence, plan.request_sha256)
    return ("reuse", plan.stage)


# --- the enumeration ------------------------------------------------------------------------------

COMPLETIONS: list[tuple[CallOutcome | None, CallRejection | None]] = [
    (None, None),
    *((outcome, None) for outcome in CallOutcome),
    (CallOutcome.COMPLETED, CITATION),
    (CallOutcome.COMPLETED, AGGREGATE),
]
KINDS = [
    (CallKind.RETRY, RequestBasis.ORIGINAL),
    (CallKind.RETRY, RequestBasis.REPAIRED),
    (CallKind.REPAIR, RequestBasis.REPAIRED),
]


def candidates(sequence: int) -> list[Spec]:
    kinds = [(CallKind.INITIAL, RequestBasis.ORIGINAL)] if sequence == 1 else KINDS
    return [
        Spec(kind, basis, digest, attempt, outcome, rejection)
        for (kind, basis), digest, attempt, (outcome, rejection) in product(
            kinds, (ORIGINAL, REPAIRED), (1, 2), COMPLETIONS
        )
    ]


def accepted(specs: tuple[Spec, ...], current: int) -> StageHistory | None:
    try:
        return history(specs, current)
    except InvalidStageHistoryError:
        return None


def test_exhaustive_histories_match_the_oracle() -> None:
    checked = valid = 0
    plans: set[str] = set()
    frontier: list[tuple[Spec, ...]] = [()]
    for sequence in range(1, 4):
        extended: list[tuple[Spec, ...]] = []
        for prefix in frontier:
            for spec in candidates(sequence):
                specs = (*prefix, spec)
                ever_valid = False
                for current in (1, 2, 3):
                    built = accepted(specs, current)
                    expected = oracle_valid(specs, current)
                    assert (built is not None) == expected, (specs, current)
                    checked += 1
                    if built is not None:
                        valid += 1
                        ever_valid = True
                        plan = plan_stage(built)
                        assert as_tuple(plan) == oracle_plan(specs, current), (specs, current)
                        assert plan == plan_without_stage(built)
                        plans.add(type(plan).__name__)
                if ever_valid:
                    extended.append(specs)
        frontier = extended
    assert checked > 50_000 and valid > 500
    assert plans == {"PlanDispatch", "PlanInFlight", "PlanExhausted"}
    empty = history((), 1)
    assert as_tuple(plan_stage(empty)) == oracle_plan((), 1)


# --- targeted cases -------------------------------------------------------------------------------


def started(attempt: int, kind: CallKind = CallKind.INITIAL, **changes: Any) -> Spec:
    basis = RequestBasis.REPAIRED if kind is CallKind.REPAIR else RequestBasis.ORIGINAL
    digest = REPAIRED if basis is RequestBasis.REPAIRED else ORIGINAL
    values: dict[str, Any] = {"kind": kind, "basis": basis, "digest": digest, "attempt": attempt}
    values.update(changes)
    return Spec(**values)


def done(spec: Spec, outcome: CallOutcome, rejection: CallRejection | None = None) -> Spec:
    return Spec(spec.kind, spec.basis, spec.digest, spec.attempt, outcome, rejection)


def test_the_same_started_history_is_in_flight_or_abandoned_by_the_current_attempt() -> None:
    one = (started(1),)
    assert as_tuple(plan_stage(history(one, 1))) == ("in_flight", 1, ORIGINAL)
    assert as_tuple(plan_stage(history(one, 2))) == (
        "dispatch",
        2,
        CallKind.RETRY,
        RequestBasis.ORIGINAL,
        1,
        None,
        ORIGINAL,
        None,
    )
    three = (
        done(started(1), CallOutcome.TIMEOUT),
        started(1, CallKind.RETRY),
        started(2, CallKind.RETRY),
    )
    assert as_tuple(plan_stage(history(three, 2))) == ("in_flight", 3, ORIGINAL)
    assert as_tuple(plan_stage(history(three, 3))) == (
        "exhausted",
        UnresolvedReason.CALL_ABANDONED,
        3,
        ORIGINAL,
    )


@pytest.mark.parametrize(
    ("specs", "reason"),
    [
        (  # third reservation after timeout
            (
                done(started(1), CallOutcome.TIMEOUT),
                done(started(1, CallKind.RETRY), CallOutcome.TIMEOUT),
                done(started(1, CallKind.RETRY), CallOutcome.TIMEOUT),
            ),
            UnresolvedReason.TIMEOUT,
        ),
        (  # third reservation after provider_failed
            (
                done(started(1), CallOutcome.PROVIDER_FAILED),
                done(started(2, CallKind.RETRY), CallOutcome.TIMEOUT),
                done(started(3, CallKind.RETRY), CallOutcome.PROVIDER_FAILED),
            ),
            UnresolvedReason.PROVIDER_FAILED,
        ),
        (  # invalid output after two retries: no budget for a repair
            (
                done(started(1), CallOutcome.TIMEOUT),
                done(started(1, CallKind.RETRY), CallOutcome.TIMEOUT),
                done(started(1, CallKind.RETRY), CallOutcome.INVALID_OUTPUT),
            ),
            UnresolvedReason.INVALID_OUTPUT,
        ),
        (  # a rejection after two retries
            (
                done(started(1), CallOutcome.TIMEOUT),
                done(started(1, CallKind.RETRY), CallOutcome.PROVIDER_FAILED),
                done(started(1, CallKind.RETRY), CallOutcome.COMPLETED, CITATION),
            ),
            UnresolvedReason.CITATION_REJECTED,
        ),
        (  # a rejection, then an invalid output after the repair (E4: no second repair)
            (
                done(started(1), CallOutcome.COMPLETED, CITATION),
                done(started(1, CallKind.REPAIR), CallOutcome.INVALID_OUTPUT),
            ),
            UnresolvedReason.INVALID_OUTPUT,
        ),
        (  # an aggregate rejection maps to invalid_output (M5b-F)
            (
                done(started(1), CallOutcome.INVALID_OUTPUT),
                done(started(1, CallKind.REPAIR), CallOutcome.COMPLETED, AGGREGATE),
            ),
            UnresolvedReason.INVALID_OUTPUT,
        ),
        (  # terminal outcomes end the stage at once
            (done(started(1), CallOutcome.MODEL_MISMATCH),),
            UnresolvedReason.MODEL_MISMATCH,
        ),
        (  # abandoned repair at sequence 3
            (
                done(started(1), CallOutcome.TIMEOUT),
                done(started(1, CallKind.RETRY), CallOutcome.INVALID_OUTPUT),
                started(1, CallKind.REPAIR),
            ),
            UnresolvedReason.CALL_ABANDONED,
        ),
    ],
)
def test_budget_boundaries_end_the_stage(specs: tuple[Spec, ...], reason: UnresolvedReason) -> None:
    plan = plan_stage(history(specs, 2 if specs[-1].outcome is None else 3))
    assert isinstance(plan, PlanExhausted) and plan.reason is reason
    assert plan.sequence == len(specs)


def test_a_rejection_uses_the_single_repair_and_an_abandoned_repair_is_retried_once() -> None:
    rejected = (done(started(1), CallOutcome.COMPLETED, CITATION),)
    assert as_tuple(plan_stage(history(rejected, 1))) == (
        "dispatch",
        2,
        CallKind.REPAIR,
        RequestBasis.REPAIRED,
        1,
        1,
        None,
        ORIGINAL,
    )
    abandoned = (*rejected, started(1, CallKind.REPAIR))
    assert as_tuple(plan_stage(history(abandoned, 2))) == (
        "dispatch",
        3,
        CallKind.RETRY,
        RequestBasis.REPAIRED,
        2,
        1,
        REPAIRED,
        None,
    )


def test_the_installed_wheel_scenario() -> None:
    specs = (done(started(1), CallOutcome.INVALID_OUTPUT), started(1, CallKind.REPAIR))
    plan = plan_stage(history(specs, 2))
    assert isinstance(plan, PlanDispatch)
    assert (plan.call_kind, plan.request_basis, plan.sequence) == (
        CallKind.RETRY,
        RequestBasis.REPAIRED,
        3,
    )


@pytest.mark.parametrize(
    ("specs", "current"),
    [
        ((started(2),), 1),  # V4 a future attempt
        ((done(started(2), CallOutcome.TIMEOUT), started(1, CallKind.RETRY)), 2),  # decreasing
        ((started(1), started(1, CallKind.RETRY)), 1),  # a started non-last call, same attempt
        ((done(started(1), CallOutcome.TIMEOUT), started(1, CallKind.REPAIR)), 1),  # wrong kind
        (  # wrong basis
            (done(started(1), CallOutcome.TIMEOUT), started(1, CallKind.RETRY, digest=REPAIRED)),
            1,
        ),
        (  # two repairs
            (
                done(started(1), CallOutcome.INVALID_OUTPUT),
                done(started(1, CallKind.REPAIR), CallOutcome.INVALID_OUTPUT),
                started(1, CallKind.REPAIR),
            ),
            1,
        ),
        (  # a retry with a different digest
            (done(started(1), CallOutcome.TIMEOUT), started(1, CallKind.RETRY, digest="c" * 64)),
            1,
        ),
        (  # a repaired digest equal to the original
            (
                done(started(1), CallOutcome.INVALID_OUTPUT),
                started(1, CallKind.REPAIR, digest=ORIGINAL),
            ),
            1,
        ),
        ((done(started(1), CallOutcome.COMPLETED),), 1),  # a success without its stage
        ((done(started(1), CallOutcome.REFUSAL), started(1, CallKind.RETRY)), 1),  # after terminal
    ],
)
def test_invalid_histories_are_refused(specs: tuple[Spec, ...], current: int) -> None:
    with pytest.raises(InvalidStageHistoryError):
        history(specs, current)


def call_with(spec: Spec, sequence: int, **changes: Any) -> CallRecord:
    base = build(spec, sequence)
    values = {name: getattr(base, name) for name in base.__dataclass_fields__}
    values.update(changes)
    return CallRecord(**values)


@pytest.mark.parametrize(
    "changes",
    [
        {"model_requested": "other-model"},
        {"max_output_tokens": 1},
        {"timeout_ms": 1000},
        {"prompt_sha256": "2" * 64},
        {"evidence_sha256": "f" * 64},
        {"question_id": "ENC-02"},
        {"job_id": TENANT},
    ],
)
def test_mixed_settings_or_identity_are_refused(changes: dict[str, Any]) -> None:
    first = build(done(started(1), CallOutcome.TIMEOUT), 1)
    second = call_with(started(1, CallKind.RETRY), 2, **changes)
    with pytest.raises(InvalidStageHistoryError):
        StageHistory(
            tenant_id=TENANT,
            review_id=REVIEW,
            job_id=JOB,
            question_id=QUESTION,
            stage=StageKind.VERIFICATION,
            current_attempt=1,
            calls=(first, second),
            committed=None,
        )


def test_call_sequences_must_be_contiguous() -> None:
    first = build(done(started(1), CallOutcome.TIMEOUT), 1)
    third = build(started(1, CallKind.RETRY), 3)
    with pytest.raises(InvalidStageHistoryError):
        StageHistory(
            tenant_id=TENANT,
            review_id=REVIEW,
            job_id=JOB,
            question_id=QUESTION,
            stage=StageKind.VERIFICATION,
            current_attempt=1,
            calls=(first, third),
            committed=None,
        )


# --- committed stages (V9, V11) -------------------------------------------------------------------


def unresolved(
    reason: UnresolvedReason, last: tuple[int, str] | None, attempt: int, evidence: str | None
) -> StageRecord:
    return StageRecord(
        tenant_id=TENANT,
        review_id=REVIEW,
        job_id=JOB,
        question_id=QUESTION,
        stage=StageKind.VERIFICATION,
        outcome=StageOutcome.UNRESOLVED,
        unresolved_reason=reason,
        call_sequence=None if last is None else last[0],
        request_sha256=None if last is None else last[1],
        evidence_sha256=evidence,
        dependency_sha256=None,
        content=None,
        job_attempt=attempt,
        committed_at=T0 - timedelta(days=1),
    )


TIMED_OUT_3 = (
    done(started(1), CallOutcome.TIMEOUT),
    done(started(1, CallKind.RETRY), CallOutcome.TIMEOUT),
    done(started(1, CallKind.RETRY), CallOutcome.TIMEOUT),
)
ABANDONED_3 = (
    done(started(1), CallOutcome.TIMEOUT),
    done(started(1, CallKind.RETRY), CallOutcome.TIMEOUT),
    started(1, CallKind.RETRY),
)
REPAIRABLE = (done(started(1), CallOutcome.INVALID_OUTPUT),)


@pytest.mark.parametrize(
    ("specs", "committed", "current"),
    [
        (TIMED_OUT_3, unresolved(UnresolvedReason.TIMEOUT, (3, ORIGINAL), 1, EVIDENCE), 1),  # U1
        (ABANDONED_3, unresolved(UnresolvedReason.CALL_ABANDONED, (3, ORIGINAL), 2, EVIDENCE), 2),
        (
            REPAIRABLE,
            unresolved(UnresolvedReason.REPAIR_REQUEST_TOO_LARGE, (1, ORIGINAL), 1, EVIDENCE),
            1,
        ),  # U6
        ((), unresolved(UnresolvedReason.REQUEST_TOO_LARGE, None, 1, EVIDENCE), 1),  # U5
        ((), unresolved(UnresolvedReason.EVIDENCE_TOO_LARGE, None, 1, None), 1),  # U4
    ],
)
def test_committed_unresolved_shapes_are_accepted_and_reused(
    specs: tuple[Spec, ...], committed: StageRecord, current: int
) -> None:
    built = history(specs, current, committed)
    plan = plan_stage(built)
    assert isinstance(plan, PlanReuse) and plan.stage == committed


@pytest.mark.parametrize(
    ("specs", "committed", "current"),
    [
        (TIMED_OUT_3, unresolved(UnresolvedReason.PROVIDER_FAILED, (3, ORIGINAL), 1, EVIDENCE), 1),
        (TIMED_OUT_3, unresolved(UnresolvedReason.TIMEOUT, (2, ORIGINAL), 1, EVIDENCE), 1),
        (TIMED_OUT_3, unresolved(UnresolvedReason.TIMEOUT, (3, ORIGINAL), 1, "f" * 64), 1),
        (TIMED_OUT_3[:2], unresolved(UnresolvedReason.TIMEOUT, (2, ORIGINAL), 1, EVIDENCE), 1),
        (ABANDONED_3, unresolved(UnresolvedReason.CALL_ABANDONED, (3, ORIGINAL), 1, EVIDENCE), 1),
        (
            (*ABANDONED_3[:2], started(1, CallKind.RETRY)),
            unresolved(UnresolvedReason.CALL_ABANDONED, (3, ORIGINAL), 3, EVIDENCE),
            2,
        ),  # committed attempt above the current attempt
        (
            TIMED_OUT_3,
            unresolved(UnresolvedReason.REPAIR_REQUEST_TOO_LARGE, (3, ORIGINAL), 1, EVIDENCE),
            1,
        ),
        (REPAIRABLE, unresolved(UnresolvedReason.REQUEST_TOO_LARGE, None, 1, EVIDENCE), 1),
        (REPAIRABLE, unresolved(UnresolvedReason.EVIDENCE_TOO_LARGE, None, 1, None), 1),
    ],
)
def test_committed_unresolved_shapes_must_match_the_history(
    specs: tuple[Spec, ...], committed: StageRecord, current: int
) -> None:
    with pytest.raises(InvalidStageHistoryError):
        history(specs, current, committed)


def test_planner_argument_must_be_a_stage_history() -> None:
    for value in (None, "history", (), object()):
        with pytest.raises(InvalidStageHistoryError):
            plan_stage(value)  # type: ignore[arg-type]


def test_plan_variants_validate_their_fields() -> None:
    for values in (
        {"sequence": 2, "call_kind": CallKind.INITIAL, "request_basis": RequestBasis.ORIGINAL},
        {
            "sequence": 2,
            "call_kind": CallKind.RETRY,
            "request_basis": RequestBasis.ORIGINAL,
            "predecessor": 1,
        },  # no required digest
        {
            "sequence": 2,
            "call_kind": CallKind.REPAIR,
            "request_basis": RequestBasis.REPAIRED,
            "predecessor": 1,
            "trigger": 1,
        },  # no original digest
        {
            "sequence": 2,
            "call_kind": CallKind.RETRY,
            "request_basis": RequestBasis.REPAIRED,
            "predecessor": 1,
            "required_request_sha256": REPAIRED,
        },  # a repaired retry needs the repair's trigger
    ):
        arguments: dict[str, Any] = {
            "predecessor": None,
            "trigger": None,
            "required_request_sha256": None,
            "original_request_sha256": None,
        }
        arguments.update(values)
        with pytest.raises(InvalidStageValueError):
            PlanDispatch(**arguments)
    with pytest.raises(InvalidStageValueError):
        PlanExhausted(
            reason=UnresolvedReason.REQUEST_TOO_LARGE, sequence=1, request_sha256=ORIGINAL
        )
    with pytest.raises(InvalidStageValueError):
        PlanInFlight(sequence=4, request_sha256=ORIGINAL)
