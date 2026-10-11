"""ASGI middleware: request IDs and one structured completion log per request."""

import logging
import time
from typing import Any
from uuid import UUID

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from evidenceguard_observability.context import bound_request_id, new_request_id, parse_request_id
from evidenceguard_observability.jsonlog import REQUEST_COMPLETED, log_event

REQUEST_ID_HEADER = "X-Request-ID"
STATE_KEY = "request_id"

_logger = logging.getLogger("evidenceguard.request")
_KNOWN_METHODS = frozenset(
    {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE", "CONNECT"}
)


def _incoming_request_id(scope: Scope) -> UUID:
    values = [
        value.decode("latin-1")
        for name, value in scope.get("headers", [])
        if name.lower() == b"x-request-id"
    ]
    return parse_request_id(values) or new_request_id()


def _route_template(scope: Scope) -> str | None:
    """The matched route's path template, or ``None``. Never the raw request path."""
    path = getattr(scope.get("route"), "path", None)
    return path if isinstance(path, str) else None


class RequestContextMiddleware:
    """Assigns a request ID, returns it in ``X-Request-ID`` and logs request completion.

    The ID is stored in ``request.state.request_id`` and bound to the current context for
    handlers and logging. Responses produced by Starlette's outermost error middleware
    (unexpected 500s) bypass this middleware's ``send``, so the 500 handler sets the header
    itself from ``request.state``. Exceptions are logged by class name only and re-raised.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _incoming_request_id(scope)
        scope.setdefault("state", {})[STATE_KEY] = request_id
        status: dict[str, int] = {}
        started = time.perf_counter()

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = str(request_id)
            await send(message)

        fields: dict[str, Any] = {"request_id": str(request_id)}
        with bound_request_id(request_id):
            try:
                await self.app(scope, receive, send_with_request_id)
            except Exception as exc:
                fields["error_type"] = type(exc).__name__
                status.setdefault("code", 500)
                raise
            finally:
                method = scope.get("method", "")
                log_event(
                    _logger,
                    REQUEST_COMPLETED,
                    level=logging.ERROR if "error_type" in fields else logging.INFO,
                    method=method if method in _KNOWN_METHODS else "OTHER",
                    route=_route_template(scope),
                    status=status.get("code"),
                    duration_ms=round((time.perf_counter() - started) * 1000, 3),
                    **fields,
                )
