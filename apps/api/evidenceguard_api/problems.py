"""RFC 9457 ``application/problem+json`` error responses.

Every error body has ``type`` (``about:blank``), ``title`` (the HTTP status phrase) and
``status``, plus the extension member ``request_id``, which matches the ``X-Request-ID``
header. What each kind of error may reveal:

- **HTTP errors** keep their status code and headers (for example ``Allow`` on 405 or
  ``WWW-Authenticate`` on 401). Their ``detail`` is never published as given: an ordinary
  ``HTTPException`` gets a generic sentence for its status class, whatever its ``detail``
  holds. The only way to show a specific message is ``PublicHTTPException`` with a member
  of ``PublicMessage``, a reviewed catalogue of fixed sentences. Submitted values and
  internal exception text must never be added to that catalogue.
- **Validation errors** return 422 with up to ``MAX_VALIDATION_ERRORS`` entries. Each entry
  has only ``loc`` (where the problem is) and ``type`` (Pydantic's error code). The submitted
  value, the message and any context are never returned, because they can echo input.
  ``loc`` uses field names; for an unexpected extra field that name came from the request,
  so each ``loc`` part is capped in length.
- **Unexpected errors** return a generic 500 with no exception text.
"""

from collections.abc import Mapping
from enum import StrEnum
from http import HTTPStatus
from typing import Any
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse, Response

from evidenceguard_api.middleware import REQUEST_ID_HEADER, STATE_KEY
from evidenceguard_observability.context import new_request_id

PROBLEM_MEDIA_TYPE = "application/problem+json"
MAX_VALIDATION_ERRORS = 20
MAX_LOC_PART_LENGTH = 64

GENERIC_CLIENT_ERROR_DETAIL = "The request could not be completed."
GENERIC_SERVER_ERROR_DETAIL = "The server could not complete the request."


class PublicMessage(StrEnum):
    """Reviewed, fixed messages that may be shown to clients in a problem ``detail``.

    Each entry is a constant sentence agreed in review. Never build entries from submitted
    values, identifiers, exception text or other runtime data.
    """

    AUTHENTICATION_REQUIRED = "Authentication is required."


class PublicHTTPException(StarletteHTTPException):
    """An HTTP error that shows one reviewed ``PublicMessage`` as its problem ``detail``."""

    def __init__(
        self,
        status_code: int,
        message: PublicMessage,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=message.value, headers=headers)
        self.public_message = message


def _request_id(request: Request) -> UUID:
    request_id = getattr(request.state, STATE_KEY, None)
    if isinstance(request_id, UUID):
        return request_id
    request_id = new_request_id()
    setattr(request.state, STATE_KEY, request_id)
    return request_id


def _title(status: int) -> str:
    try:
        return HTTPStatus(status).phrase
    except ValueError:
        return "Error"


def problem_response(
    request: Request,
    status: int,
    *,
    detail: str | None = None,
    headers: dict[str, str] | None = None,
    extensions: dict[str, Any] | None = None,
) -> JSONResponse:
    request_id = _request_id(request)
    status = int(status)
    body: dict[str, Any] = {"type": "about:blank", "title": _title(status), "status": status}
    if detail:
        body["detail"] = detail
    body.update(extensions or {})
    body["request_id"] = str(request_id)
    response_headers = dict(headers or {})
    response_headers[REQUEST_ID_HEADER] = str(request_id)
    return JSONResponse(
        body, status_code=status, headers=response_headers, media_type=PROBLEM_MEDIA_TYPE
    )


def _bounded_loc(loc: Any) -> list[str | int]:
    parts = loc if isinstance(loc, list | tuple) else [loc]
    return [p if isinstance(p, int) else str(p)[:MAX_LOC_PART_LENGTH] for p in parts]


async def http_exception_handler(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, StarletteHTTPException)
    headers = dict(exc.headers or {})
    if exc.status_code in {204, 304}:
        return Response(status_code=exc.status_code, headers=headers)
    if isinstance(exc, PublicHTTPException):
        detail = exc.public_message.value
    elif exc.status_code >= 500:
        detail = GENERIC_SERVER_ERROR_DETAIL
    else:
        detail = GENERIC_CLIENT_ERROR_DETAIL
    return problem_response(request, exc.status_code, detail=detail, headers=headers)


async def validation_exception_handler(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, RequestValidationError)
    errors = [
        {"loc": _bounded_loc(error.get("loc", ())), "type": str(error.get("type", "unknown"))}
        for error in exc.errors()[:MAX_VALIDATION_ERRORS]
    ]
    return problem_response(
        request,
        HTTPStatus.UNPROCESSABLE_ENTITY,
        detail="The request did not pass validation.",
        extensions={"errors": errors},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> Response:
    """Generic 500. Starlette still re-raises ``exc`` to the server after this response."""
    return problem_response(
        request, HTTPStatus.INTERNAL_SERVER_ERROR, detail="An unexpected error occurred."
    )


def install_problem_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
