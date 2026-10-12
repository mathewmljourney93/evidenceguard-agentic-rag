"""The handler registry: an immutable, validated mapping from job kind to handler (ADR-0008)."""

from collections.abc import Callable, Iterable, Iterator, Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING

from evidenceguard_domain.jobs import validate_kind

if TYPE_CHECKING:
    from evidenceguard_worker.context import JobContext

JobHandler = Callable[["JobContext"], None]
"""Trusted application code that runs one job attempt. See ``JobContext`` for the rules."""


class DuplicateHandlerError(ValueError):
    """A kind was registered twice."""

    def __init__(self) -> None:
        super().__init__("a job kind can be registered only once")


class HandlerRegistry(Mapping[str, JobHandler]):
    """Job kind -> handler. Fixed at construction; it cannot be changed afterwards.

    Every kind must match M3a's kind pattern, every handler must be callable, and registering a
    kind twice raises ``DuplicateHandlerError``. Pairs are taken in order, so a duplicate is
    always detected rather than silently replaced.
    """

    def __init__(self, handlers: Iterable[tuple[str, JobHandler]] = ()) -> None:
        entries: dict[str, JobHandler] = {}
        for kind, handler in handlers:
            validate_kind(kind)
            if not callable(handler):
                raise TypeError("a job handler must be callable")
            if kind in entries:
                raise DuplicateHandlerError()
            entries[kind] = handler
        self._handlers: Mapping[str, JobHandler] = MappingProxyType(entries)
        self._kinds = frozenset(entries)

    @property
    def kinds(self) -> frozenset[str]:
        """The kinds this registry can run: the worker's claim filter."""
        return self._kinds

    def __getitem__(self, kind: str) -> JobHandler:
        return self._handlers[kind]

    def __iter__(self) -> Iterator[str]:
        return iter(self._handlers)

    def __len__(self) -> int:
        return len(self._handlers)
