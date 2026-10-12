"""Stop requests and signal installation (ADR-0008).

The first stop request asks for a graceful stop and a second one for an immediate stop. Signal
handlers only set plain attributes: they take no locks and call nothing else, so they cannot
deadlock with the thread they interrupt. The runtime polls the flags at least every
``Timings.stop_check`` seconds. Signals do **not** cancel a database call that is in progress.
"""

import signal
import threading
from collections.abc import Callable
from types import FrameType


class StopController:
    """Graceful and immediate stop flags, settable from a signal handler or any thread."""

    def __init__(self) -> None:
        self._requested = False
        self._immediate = False
        self._wakers: list[Callable[[], None]] = []

    @property
    def requested(self) -> bool:
        return self._requested

    @property
    def immediate(self) -> bool:
        return self._immediate

    def request(self) -> None:
        """Escalate like a signal (graceful first, then immediate) and wake the runtime."""
        self._escalate()
        self._wake()

    def request_immediate(self) -> None:
        self._requested = True
        self._immediate = True
        self._wake()

    def add_waker(self, waker: Callable[[], None]) -> None:
        """Called (outside signal handlers) when a stop is requested through the API."""
        self._wakers.append(waker)

    def _escalate(self) -> None:
        # Plain attribute writes only: safe inside a signal handler.
        if self._requested:
            self._immediate = True
        self._requested = True

    def _wake(self) -> None:
        for waker in tuple(self._wakers):
            waker()


def _stop_signals() -> list[signal.Signals]:
    names = ("SIGINT", "SIGTERM", "SIGBREAK")  # SIGBREAK exists only on Windows
    return [getattr(signal, name) for name in names if hasattr(signal, name)]


def install_signal_handlers(stop: StopController) -> Callable[[], None]:
    """Route SIGINT, SIGTERM (where delivered) and Windows SIGBREAK to ``stop``.

    Must run in the main thread. Returns a function that restores the previous handlers.
    """
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("signal handlers can only be installed from the main thread")

    def handle(signum: int, frame: FrameType | None) -> None:
        stop._escalate()

    previous: dict[signal.Signals, Callable[[int, FrameType | None], object] | int | None] = {}
    for stop_signal in _stop_signals():
        previous[stop_signal] = signal.signal(stop_signal, handle)

    def restore() -> None:
        for stop_signal, handler in previous.items():
            signal.signal(stop_signal, signal.SIG_DFL if handler is None else handler)

    return restore
