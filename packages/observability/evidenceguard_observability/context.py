"""The current request's correlation ID.

The ID is stored in a ``ContextVar``, so each concurrently running request (each asyncio task
or thread context) sees only its own value. It is a correlation identifier only: it must never
be used for authentication, authorization or as evidence of who made a request.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import UUID, uuid4

_request_id: ContextVar[UUID | None] = ContextVar("evidenceguard_request_id", default=None)

_MAX_HEADER_LENGTH = 64


def parse_request_id(values: list[str]) -> UUID | None:
    """Return the normalized UUID from exactly one ``X-Request-ID`` value, or ``None``.

    Anything else (no header, several headers, an over-long value or a non-UUID) is rejected,
    so the caller generates a fresh ID instead of trusting client input.
    """
    if len(values) != 1 or len(values[0]) > _MAX_HEADER_LENGTH:
        return None
    try:
        return UUID(values[0].strip())
    except ValueError:
        return None


def new_request_id() -> UUID:
    return uuid4()


def current_request_id() -> UUID | None:
    """The request ID bound to the current context, if any."""
    return _request_id.get()


@contextmanager
def bound_request_id(request_id: UUID) -> Iterator[UUID]:
    """Bind ``request_id`` for the duration of the block, then restore the previous value."""
    token = _request_id.set(request_id)
    try:
        yield request_id
    finally:
        _request_id.reset(token)
