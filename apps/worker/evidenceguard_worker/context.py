"""What a handler sees: ``JobContext``, ``HandlerFence``, the attempt state and handler errors.

One ``AttemptState`` is shared by the supervisor (main thread), the handler thread and the
heartbeat thread of a single job attempt. Its lock is held only to read or change its fields,
**never across database I/O**, so the supervisor can always read the state and keep observing
its deadlines (ADR-0008).

Latched lease loss and cancellation are **irreversible** for an attempt: a later successful
heartbeat neither clears them nor moves the local lease deadline.

Handlers are trusted application code. ``HandlerFence`` offers no lifecycle transitions, but,
like M3a's ``FencedSession``, it is a convention and **not a sandbox** (ADR-0007).
"""

import threading
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from enum import StrEnum
from typing import Protocol

from evidenceguard_domain.jobs import JobErrorCode, JobLeaseToken, JobSnapshot, LeaseLostError
from evidenceguard_persistence.jobs import FenceClosedError, FencedSession

# --- handler errors ----------------------------------------------------------------------


class RetryableJobError(Exception):
    """Raise from a handler to record a retryable failure with a fixed ``JobErrorCode``.

    M3a's attempt cap and backoff apply: the job is re-queued while attempts remain, otherwise
    it ends ``dead``.
    """

    def __init__(self, code: JobErrorCode = JobErrorCode.RETRYABLE_FAILURE) -> None:
        if not isinstance(code, JobErrorCode):
            raise TypeError("code must be a JobErrorCode")
        super().__init__("the job attempt failed and may be retried")
        self.code = code


class PermanentJobError(Exception):
    """Raise from a handler to end the job ``failed`` with a fixed ``JobErrorCode``."""

    def __init__(self, code: JobErrorCode = JobErrorCode.PERMANENT_FAILURE) -> None:
        if not isinstance(code, JobErrorCode):
            raise TypeError("code must be a JobErrorCode")
        super().__init__("the job failed permanently")
        self.code = code


class JobCancelledError(Exception):
    """The worker asked this attempt to stop (shutdown). Raised by ``JobContext.check``."""

    def __init__(self) -> None:
        super().__init__("the job attempt was cancelled by the worker")


# --- shared attempt state -----------------------------------------------------------------


class FinishState(StrEnum):
    NONE = "none"
    FINISHING = "finishing"
    COMMITTED = "committed"
    UNCERTAIN = "uncertain"


class AttemptState:
    """Thread-safe state of one job attempt (see the module docstring)."""

    def __init__(
        self,
        *,
        deadline: float,
        lease_seconds: float,
        clock: Callable[[], float],
        on_change: Callable[[], None] | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._deadline = deadline
        self._lease_seconds = lease_seconds
        self._clock = clock
        self._on_change = on_change
        self._finish = FinishState.NONE
        self._pending_refusal = False
        self._lease_lost = False
        self._cancel_requested = False
        self._outcome_unknown = False

    # Reads ------------------------------------------------------------------------------

    @property
    def finish(self) -> FinishState:
        with self._lock:
            return self._finish

    @property
    def lease_lost(self) -> bool:
        with self._lock:
            return self._lease_lost

    @property
    def cancel_requested(self) -> bool:
        with self._lock:
            return self._cancel_requested

    @property
    def outcome_unknown(self) -> bool:
        """True after an uncertain finish: whether the job committed is not known."""
        with self._lock:
            return self._outcome_unknown

    @property
    def pending_refusal(self) -> bool:
        with self._lock:
            return self._pending_refusal

    @property
    def deadline(self) -> float:
        """The local, conservative lease deadline on the monotonic clock."""
        with self._lock:
            return self._deadline

    # Heartbeat results ----------------------------------------------------------------------

    def renewed(self, called_at: float) -> bool:
        """A heartbeat that started at ``called_at`` was confirmed. Moves the local deadline to
        ``called_at + lease`` unless lease loss or cancellation is already latched; returns
        whether it moved."""
        with self._lock:
            if self._lease_lost or self._cancel_requested:
                return False
            self._deadline = max(self._deadline, called_at + self._lease_seconds)
            return True

    def record_refusal(self) -> None:
        """A heartbeat was refused (or failed unexpectedly). Classified against the finish:

        - ``committed``: the expected refusal of a terminal job, discarded;
        - ``finishing``: kept pending until the finish resolves;
        - ``none``: lease loss;
        - ``uncertain``: lease loss with the outcome unknown.
        """
        with self._lock:
            if self._finish is FinishState.COMMITTED:
                return
            if self._finish is FinishState.FINISHING:
                self._pending_refusal = True
                return
            self._latch_lease_loss_locked()
        self._changed()

    # Finish -------------------------------------------------------------------------------

    def begin_finish(self) -> None:
        with self._lock:
            if self._finish is not FinishState.NONE:
                raise FenceClosedError()
            self._finish = FinishState.FINISHING

    def end_finish(self, result: FinishState) -> None:
        """Publish how the finish ended, then classify any refusal recorded meanwhile."""
        if result is FinishState.FINISHING:
            raise ValueError("a finish ends committed, rolled back (none) or uncertain")
        with self._lock:
            self._finish = result
            if result is FinishState.UNCERTAIN:
                self._outcome_unknown = True
            if self._pending_refusal:
                self._pending_refusal = False
                if result is not FinishState.COMMITTED:
                    self._latch_lease_loss_locked()
        self._changed()

    # Supervisor decisions ---------------------------------------------------------------------

    def refresh(self) -> bool:
        """Latch presumed lease loss once the local deadline has passed without a confirmed
        renewal (unless the finish committed). Returns whether lease loss is latched."""
        now = self._clock()
        with self._lock:
            if (
                not self._lease_lost
                and self._finish is not FinishState.COMMITTED
                and now >= self._deadline
            ):
                self._latch_lease_loss_locked()
            return self._lease_lost

    def latch_lease_loss(self) -> None:
        with self._lock:
            self._latch_lease_loss_locked()
        self._changed()

    def request_cancel(self) -> None:
        with self._lock:
            self._cancel_requested = True
        self._changed()

    def check(self) -> None:
        """Raise unless this attempt may still do fenced work. ``finishing`` is permitted: it is
        the state while a ``finish=True`` block runs."""
        self.refresh()
        with self._lock:
            if self._finish in (FinishState.COMMITTED, FinishState.UNCERTAIN):
                raise FenceClosedError()
            if self._lease_lost:
                raise LeaseLostError()
            if self._cancel_requested:
                raise JobCancelledError()

    def _latch_lease_loss_locked(self) -> None:
        self._lease_lost = True
        if self._finish is FinishState.UNCERTAIN:
            self._outcome_unknown = True

    def _changed(self) -> None:
        if self._on_change is not None:
            self._on_change()


# --- the handler-facing context ------------------------------------------------------------


class FenceHandle(Protocol):
    """What the runtime needs from an open M3a fence (``evidenceguard_persistence.jobs.Fence``)."""

    @property
    def session(self) -> FencedSession: ...

    @property
    def job(self) -> JobSnapshot: ...

    def succeed(self) -> JobSnapshot: ...


FenceOpener = Callable[[JobLeaseToken], AbstractContextManager[FenceHandle]]


class HandlerFence:
    """A fenced transaction as a handler sees it: ``.session`` and ``.job`` only.

    It has no transition methods, so handler code cannot record a lifecycle outcome directly.
    """

    __slots__ = ("_job", "_session")

    def __init__(self, session: FencedSession, job: JobSnapshot) -> None:
        self._session = session
        self._job = job

    @property
    def session(self) -> FencedSession:
        return self._session

    @property
    def job(self) -> JobSnapshot:
        return self._job


class JobContext:
    """Everything a handler gets for one attempt.

    - ``job``: the claimed snapshot. The tenant comes only from ``job.tenant_id``.
    - ``check()``: raises ``FenceClosedError`` after a committed or uncertain finish,
      ``LeaseLostError`` once lease loss is latched or presumed, or ``JobCancelledError`` once
      cancellation was requested. Long handlers should call it between expensive steps.
    - ``fenced(finish=False)``: calls ``check()``, then opens M3a's fenced transaction for this
      attempt's token. With ``finish=True`` the runtime records ``succeeded`` in the **same
      transaction**, just before the commit, so the block's effects and the completion commit
      together or not at all. ``committed`` is published only after the transaction context
      exits without an exception; a commit that raises makes the finish ``uncertain``.

    The database fence remains the final ownership check: local flags only stop a handler
    earlier. Durable effects must go through ``fenced()`` and must be idempotent, because a job
    can run more than once (at-least-once execution).
    """

    def __init__(self, job: JobSnapshot, state: AttemptState, open_fence: FenceOpener) -> None:
        self._job = job
        self._token = job.lease_token()
        self._state = state
        self._open_fence = open_fence

    @property
    def job(self) -> JobSnapshot:
        return self._job

    @property
    def token(self) -> JobLeaseToken:
        return self._token

    @property
    def lease_lost(self) -> bool:
        return self._state.lease_lost

    @property
    def cancel_requested(self) -> bool:
        return self._state.cancel_requested

    @property
    def finished(self) -> bool:
        return self._state.finish is FinishState.COMMITTED

    def check(self) -> None:
        self._state.check()

    @contextmanager
    def fenced(self, *, finish: bool = False) -> Iterator[HandlerFence]:
        """Permission is checked at explicit boundaries only: before the fence opens, again
        after it has acquired its lock (cancellation or lease loss may have been latched during
        the wait), and, with ``finish=True``, once more before ``succeeded`` is recorded. A
        failed check raises inside the transaction, so it rolls back and, at the second
        boundary, the block never runs. These checks are not atomic with every SQL statement,
        and nothing interrupts a statement already in flight; the database fence remains the
        final ownership check. ``check()`` permits the ``finishing`` state."""
        self.check()
        if not finish:
            with self._open_fence(self._token) as fence:
                self.check()
                yield HandlerFence(fence.session, fence.job)
            return

        self._state.begin_finish()
        effects_done = False
        try:
            with self._open_fence(self._token) as fence:
                self.check()
                yield HandlerFence(fence.session, fence.job)
                self.check()
                fence.succeed()
                effects_done = True
        except BaseException:
            # Before the effects finished, the transaction rolled back. After that, only the
            # commit (or the transaction cleanup) can have failed: whether it committed is unknown.
            self._state.end_finish(FinishState.UNCERTAIN if effects_done else FinishState.NONE)
            raise
        self._state.end_finish(FinishState.COMMITTED)
