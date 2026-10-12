"""The heartbeat loop and the shared attempt state, without threads or a database (ADR-0008).

``run_heartbeats`` runs synchronously here against a scripted stop event and a scripted clock,
so every interval, deadline and classification is checked deterministically.
"""

import threading
from collections.abc import Callable, Iterator
from typing import Any, cast
from uuid import uuid4

import pytest
from sqlalchemy.exc import OperationalError

from evidenceguard_domain.jobs import JobLeaseToken, LeaseLostError
from evidenceguard_persistence.jobs import FenceClosedError, JobLockTimeoutError
from evidenceguard_worker.context import AttemptState, FinishState, JobCancelledError
from evidenceguard_worker.heartbeat import run_heartbeats
from evidenceguard_worker.runtime import Timings

TOKEN = JobLeaseToken(job_id=uuid4(), worker_id="worker-test", attempt=1)
LEASE = 60.0


class ScriptedStop:
    """``wait`` returns False (keep going) ``rounds`` times, then True (stop)."""

    def __init__(self, rounds: int) -> None:
        self.rounds = rounds
        self.waits: list[float] = []

    def wait(self, timeout: float) -> bool:
        self.waits.append(timeout)
        return len(self.waits) > self.rounds


class Clock:
    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


def _state(clock: Clock, deadline: float = LEASE) -> AttemptState:
    return AttemptState(deadline=deadline, lease_seconds=LEASE, clock=clock)


def _run(
    renew: Callable[[JobLeaseToken], object],
    state: AttemptState,
    stop: ScriptedStop,
    clock: Clock,
    failures: list[BaseException] | None = None,
    interval: float = 20.0,
) -> None:
    run_heartbeats(
        renew=renew,
        token=TOKEN,
        state=state,
        stop=cast(threading.Event, stop),
        interval=interval,
        clock=clock,
        on_failure=(failures if failures is not None else []).append,
    )


def _script(*steps: object, clock: Clock, advance: float = 0.0) -> Callable[[Any], object]:
    """Each call takes the next step: an exception is raised, anything else returned. The clock
    advances by ``advance`` *during* the call, after the runtime read the pre-call time."""
    iterator: Iterator[object] = iter(steps)

    def renew(token: Any) -> object:
        assert token == TOKEN
        clock.now += advance
        step = next(iterator)
        if isinstance(step, BaseException):
            raise step
        return step

    return renew


# --- the loop -------------------------------------------------------------------------------


def test_the_default_interval_is_twenty_seconds() -> None:
    assert Timings().heartbeat_interval == 20.0
    stop = ScriptedStop(rounds=0)
    clock = Clock()

    _run(_script(clock=clock), _state(clock), stop, clock)

    assert stop.waits == [20.0]


def test_a_confirmed_renewal_moves_the_deadline_from_the_pre_call_time() -> None:
    clock = Clock(start=30.0)
    state = _state(clock)

    _run(_script("ok", clock=clock, advance=4.0), state, ScriptedStop(rounds=1), clock)

    assert state.deadline == 30.0 + LEASE  # not 34 + 60: the call's own duration is not credited


def test_transient_failures_are_reported_and_retried_without_moving_the_deadline() -> None:
    clock = Clock(start=10.0)
    state = _state(clock)
    failures: list[BaseException] = []
    renew = _script(
        JobLockTimeoutError(),
        OperationalError("SELECT", {}, Exception("db down")),
        clock=clock,
    )

    _run(renew, state, ScriptedStop(rounds=2), clock, failures)

    assert [type(error) for error in failures] == [JobLockTimeoutError, OperationalError]
    assert state.deadline == LEASE
    assert not state.lease_lost


def test_a_refused_heartbeat_ends_the_loop_and_is_lease_loss_without_a_finish() -> None:
    clock = Clock()
    state = _state(clock)
    stop = ScriptedStop(rounds=5)

    _run(_script(LeaseLostError(), clock=clock), state, stop, clock)

    assert len(stop.waits) == 1
    assert state.lease_lost


def test_an_unexpected_heartbeat_error_is_reported_and_treated_as_a_refusal() -> None:
    clock = Clock()
    state = _state(clock)
    failures: list[BaseException] = []
    stop = ScriptedStop(rounds=5)

    _run(_script(RuntimeError("unexpected"), clock=clock), state, stop, clock, failures)

    assert [type(error) for error in failures] == [RuntimeError]
    assert len(stop.waits) == 1
    assert state.lease_lost


# --- conservative local deadlines -------------------------------------------------------------


def test_presumed_loss_starts_from_the_pre_claim_deadline() -> None:
    clock = Clock(start=59.9)
    state = _state(clock, deadline=LEASE)

    assert not state.refresh()
    clock.now = LEASE
    assert state.refresh()
    with pytest.raises(LeaseLostError):
        state.check()


def test_latched_loss_is_irreversible_and_ignores_late_renewals() -> None:
    clock = Clock()
    state = _state(clock)
    state.latch_lease_loss()

    assert state.renewed(called_at=50.0) is False
    assert state.deadline == LEASE
    assert state.lease_lost
    with pytest.raises(LeaseLostError):
        state.check()


def test_requested_cancellation_is_irreversible_and_ignores_late_renewals() -> None:
    clock = Clock()
    state = _state(clock)
    state.request_cancel()

    assert state.renewed(called_at=50.0) is False
    assert state.deadline == LEASE
    with pytest.raises(JobCancelledError):
        state.check()


def test_a_committed_finish_is_never_presumed_lost() -> None:
    clock = Clock()
    state = _state(clock)
    state.begin_finish()
    state.end_finish(FinishState.COMMITTED)
    clock.now = 10 * LEASE

    assert not state.refresh()
    with pytest.raises(FenceClosedError):
        state.check()


# --- refusals and the finish ---------------------------------------------------------------------


def test_a_refusal_after_a_committed_finish_is_discarded() -> None:
    state = _state(Clock())
    state.begin_finish()
    state.end_finish(FinishState.COMMITTED)

    state.record_refusal()

    assert not state.lease_lost and not state.pending_refusal


@pytest.mark.parametrize(
    ("result", "lease_lost", "unknown"),
    [
        (FinishState.COMMITTED, False, False),
        (FinishState.NONE, True, False),  # rolled back
        (FinishState.UNCERTAIN, True, True),
    ],
)
def test_a_refusal_during_a_finish_stays_pending_until_the_finish_resolves(
    result: FinishState, lease_lost: bool, unknown: bool
) -> None:
    changes: list[str] = []
    state = AttemptState(
        deadline=LEASE, lease_seconds=LEASE, clock=Clock(), on_change=lambda: changes.append("x")
    )
    state.begin_finish()

    state.record_refusal()
    assert state.pending_refusal
    assert not state.lease_lost and not state.cancel_requested and changes == []

    state.end_finish(result)

    assert not state.pending_refusal
    assert (state.lease_lost, state.outcome_unknown) == (lease_lost, unknown)
    assert changes  # the supervisor is woken to re-evaluate


def test_a_refusal_after_an_uncertain_finish_is_lease_loss_with_an_unknown_outcome() -> None:
    state = _state(Clock())
    state.begin_finish()
    state.end_finish(FinishState.UNCERTAIN)

    state.record_refusal()

    assert state.lease_lost and state.outcome_unknown
    with pytest.raises(FenceClosedError):
        state.check()


def test_only_one_finish_can_begin() -> None:
    state = _state(Clock())
    state.begin_finish()

    with pytest.raises(FenceClosedError):
        state.begin_finish()
    with pytest.raises(ValueError):
        state.end_finish(FinishState.FINISHING)


def test_check_permits_a_finish_in_progress_but_not_a_latched_cancellation() -> None:
    state = _state(Clock())
    state.begin_finish()

    state.check()  # ``finishing`` is the legitimate state inside a finish block
    state.request_cancel()
    with pytest.raises(JobCancelledError):
        state.check()
