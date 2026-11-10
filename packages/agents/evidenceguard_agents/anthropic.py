"""The Anthropic Messages adapter behind the M5a ``ModelProvider`` protocol (M5h, ADR-0026).

``AnthropicProvider`` is constructed explicitly by trusted code with an injected
``AnthropicTransport``; nothing registers it, and it reads no setting, environment variable or
file. This module performs no network access: the HTTPS transport lives in
``evidenceguard_worker.anthropic_http``. The accepted contract is the M5h specification in
``docs/plan.md`` (accepted in Prompt 227, with binding clarifications A-C).

``generate`` runs, in order:

1. **Request revalidation.** Exactly a ``StructuredRequest``, rebuilt through its constructor,
   with the stored ``output_schema`` and ``request_sha256`` unchanged; otherwise
   ``anthropic_invalid_request`` and zero transport calls.
2. **Body.** The canonical JSON body (no sampling, thinking, tools, caching, fallbacks or betas),
   at most ``MAX_REQUEST_BYTES``; otherwise ``anthropic_request_too_large`` and zero calls.
3. **Dispatch.** ``transport.post`` exactly once. No retry and no state between calls.
4. **Transport failures** are classified by their own type only: process control propagates as
   the same object, a timeout becomes a fresh ``ModelCallTimeout``, a kept transport code is
   kept, and anything else is ``anthropic_transport_failed``.
5. **Response.** ``parse_response``: admission first (clarification A), then the status and
   error-envelope rules, then the ordered 200 validation.

The adapter never parses model output: it extracts the single ``end_turn`` text block and M5a's
``parse_output`` decides ``completed`` or ``invalid_output``. ``model_used`` is the response
``model`` verbatim, so M5a's mismatch precedence applies unchanged. Every failure is a fixed
``AnthropicError`` (or ``ModelCallTimeout``) raised outside every ``except`` block, so no cause,
context, provider message, request ID, header, body or model text is retained.
"""

import dataclasses
import json
import math
import re
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from evidenceguard_agents.providers import ModelCallTimeout
from evidenceguard_domain.model_calls import (
    MAX_OUTPUT_TEXT_BYTES,
    MAX_USAGE_TOKENS,
    MODEL_ID_PATTERN,
    ModelUsage,
    ProviderResponse,
    StopKind,
    StructuredRequest,
    utf8_size,
)

ANTHROPIC_PROVIDER_ID = "anthropic"
ANTHROPIC_API_VERSION = "2026-10-21"
ANTHROPIC_HOST = "api.anthropic.com"
ANTHROPIC_PATH = "/v1/messages"
MAX_REQUEST_BYTES = 4_194_304
MAX_RESPONSE_BYTES = 1_048_576
MAX_ERROR_BODY_BYTES = 65_536
MAX_JSON_DEPTH = 16
MAX_JSON_INTEGER_DIGITS = 20
MAX_CONTENT_BLOCKS = 64

_MODEL_ID = re.compile(MODEL_ID_PATTERN, re.ASCII)
_TOKEN = re.compile(r"[a-z_]{1,64}", re.ASCII)
_JSON_SPECIAL = re.compile(r'["\\\[\]{}]')
_BOM = b"\xef\xbb\xbf"


class AnthropicErrorCode(StrEnum):
    CONFIGURATION = "anthropic_configuration"
    INVALID_REQUEST = "anthropic_invalid_request"
    REQUEST_TOO_LARGE = "anthropic_request_too_large"
    CLOCK_FAILED = "anthropic_clock_failed"
    TIMEOUT = "anthropic_timeout"
    TRANSPORT_FAILED = "anthropic_transport_failed"
    MALFORMED_RESPONSE = "anthropic_malformed_response"
    RESPONSE_TOO_LARGE = "anthropic_response_too_large"
    OUTPUT_TOO_LARGE = "anthropic_output_too_large"
    REQUEST_REJECTED = "anthropic_request_rejected"
    AUTHENTICATION = "anthropic_authentication"
    BILLING = "anthropic_billing"
    PERMISSION = "anthropic_permission"
    NOT_FOUND = "anthropic_not_found"
    CONFLICT = "anthropic_conflict"
    PAYLOAD_TOO_LARGE = "anthropic_payload_too_large"
    RATE_LIMITED = "anthropic_rate_limited"
    SERVER_ERROR = "anthropic_server_error"
    UNEXPECTED_STATUS = "anthropic_unexpected_status"


# Codes a transport may raise that the adapter keeps (M5h-C step 4); TIMEOUT is converted.
_KEPT_TRANSPORT_CODES = frozenset(
    {
        AnthropicErrorCode.CONFIGURATION,
        AnthropicErrorCode.CLOCK_FAILED,
        AnthropicErrorCode.TRANSPORT_FAILED,
        AnthropicErrorCode.MALFORMED_RESPONSE,
        AnthropicErrorCode.RESPONSE_TOO_LARGE,
    }
)

_STATUS_CODES = {
    400: AnthropicErrorCode.REQUEST_REJECTED,
    401: AnthropicErrorCode.AUTHENTICATION,
    402: AnthropicErrorCode.BILLING,
    403: AnthropicErrorCode.PERMISSION,
    404: AnthropicErrorCode.NOT_FOUND,
    409: AnthropicErrorCode.CONFLICT,
    413: AnthropicErrorCode.PAYLOAD_TOO_LARGE,
    429: AnthropicErrorCode.RATE_LIMITED,
}

_STOP_KINDS = {
    "end_turn": StopKind.END_TURN,
    "refusal": StopKind.REFUSAL,
    "max_tokens": StopKind.MAX_TOKENS,
}


class AnthropicError(Exception):
    """A fixed, private adapter or transport failure. ``str(error)`` is the code string."""

    code: AnthropicErrorCode

    def __init__(self, code: AnthropicErrorCode) -> None:
        if type(code) is not AnthropicErrorCode:
            raise TypeError("code must be an AnthropicErrorCode")
        super().__init__(code.value)
        self.code = code


def _require(condition: bool, code: AnthropicErrorCode) -> None:
    if not condition:
        raise AnthropicError(code)


def _status_code(status: int) -> AnthropicErrorCode:
    """The fixed code for a non-200, non-504 status without a ``timeout_error`` envelope."""
    if status in _STATUS_CODES:
        return _STATUS_CODES[status]
    if 500 <= status <= 599:
        return AnthropicErrorCode.SERVER_ERROR
    return AnthropicErrorCode.UNEXPECTED_STATUS


@dataclass(frozen=True, init=False, repr=False)
class AnthropicResponse:
    """One transport result: an HTTP status and the body bytes (possibly empty)."""

    status: int
    body: bytes

    def __init__(self, status: int, body: bytes) -> None:
        malformed = AnthropicErrorCode.MALFORMED_RESPONSE
        _require(type(status) is int and 100 <= status <= 599, malformed)
        _require(type(body) is bytes, malformed)
        _require(len(body) <= MAX_RESPONSE_BYTES, AnthropicErrorCode.RESPONSE_TOO_LARGE)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "body", body)

    def __repr__(self) -> str:
        return f"AnthropicResponse(status={self.status}, body_bytes={len(self.body)})"

    __str__ = __repr__


class AnthropicTransport(Protocol):
    def post(self, body: bytes, *, timeout_ms: int) -> AnthropicResponse: ...


# --- request -------------------------------------------------------------------------------------


def _revalidated_request(request: object) -> StructuredRequest:
    """M5a's rule: exactly a ``StructuredRequest``, rebuilt with an unchanged schema and digest."""
    rebuilt: StructuredRequest | None = None
    if type(request) is StructuredRequest:
        try:
            candidate = dataclasses.replace(request)
            if (
                candidate.output_schema == request.output_schema
                and candidate.request_sha256 == request.request_sha256
            ):
                rebuilt = candidate
        except Exception:  # an invalid or bypass-built value: fixed code below
            rebuilt = None
    _require(rebuilt is not None, AnthropicErrorCode.INVALID_REQUEST)
    assert rebuilt is not None
    return rebuilt


def _body(request: StructuredRequest) -> bytes:
    payload = {
        "max_tokens": request.max_output_tokens,
        "messages": [{"content": request.user_text, "role": "user"}],
        "model": request.model_id,
        "system": request.system_text,
    }
    body = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")
    _require(len(body) <= MAX_REQUEST_BYTES, AnthropicErrorCode.REQUEST_TOO_LARGE)
    return body


def build_request_body(request: StructuredRequest) -> bytes:
    """The canonical ASCII request body for a revalidated ``request`` (M5h-D)."""
    return _body(_revalidated_request(request))


# --- strict JSON (J1-J7) -------------------------------------------------------------------------


def _reject_constant(name: str) -> object:
    raise ValueError("non-finite JSON constant")


def _finite_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise ValueError("non-finite JSON number")
    return value


def _bounded_int(text: str) -> int:
    if len(text.lstrip("-")) > MAX_JSON_INTEGER_DIGITS:
        raise ValueError("JSON integer too long")
    return int(text)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    document: dict[str, Any] = {}
    for key, value in pairs:
        if key in document:
            raise ValueError("duplicate JSON key")
        document[key] = value
    return document


def _within_depth(text: str) -> bool:
    """A linear pre-scan: container nesting outside strings never exceeds ``MAX_JSON_DEPTH``.

    Only quotes, backslashes and brackets are visited. Inside a string a backslash escapes the
    next character; outside one it cannot occur in valid JSON and is left to the decoder."""
    depth = 0
    in_string = False
    escaped_at = -1
    for match in _JSON_SPECIAL.finditer(text):
        position = match.start()
        character = match.group()
        if in_string:
            if position == escaped_at:
                continue
            if character == "\\":
                escaped_at = position + 1
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            if depth > MAX_JSON_DEPTH:
                return False
        elif character in "]}":
            depth -= 1
    return True


def _decode(body: bytes) -> tuple[bool, object]:
    """J2-J7 on an already size-checked body: ``(True, document)`` or ``(False, None)``."""
    if body.startswith(_BOM):
        return False, None
    document: object = None
    decoded = False
    try:
        text = body.decode("utf-8", errors="strict")
        if _within_depth(text):
            document = json.loads(
                text,
                parse_constant=_reject_constant,
                parse_float=_finite_float,
                parse_int=_bounded_int,
                object_pairs_hook=_unique_object,
            )
            decoded = True
    except Exception:  # UnicodeDecodeError, ValueError, RecursionError: fixed and private
        decoded = False
        document = None
    return decoded, document


# --- response ------------------------------------------------------------------------------------


def _admitted(response: object) -> AnthropicResponse:
    """M5h-G step 1 (clarification A): exact type, then a rebuild through the constructor."""
    _require(type(response) is AnthropicResponse, AnthropicErrorCode.MALFORMED_RESPONSE)
    fields: list[object] = []
    with suppress(Exception):  # a deleted attribute or a raising read: refused below
        fields = [getattr(response, "status"), getattr(response, "body")]  # noqa: B009
    _require(len(fields) == 2, AnthropicErrorCode.MALFORMED_RESPONSE)
    return AnthropicResponse(fields[0], fields[1])  # type: ignore[arg-type]


def _is_timeout_envelope(body: bytes) -> bool:
    """M5h-G step 3.1: only ``type`` and ``error.type`` are inspected; any failure is "no
    envelope", never an error."""
    if not 1 <= len(body) <= MAX_ERROR_BODY_BYTES:
        return False
    decoded, document = _decode(body)
    if not decoded or type(document) is not dict:
        return False
    kind_of_body = document.get("type")
    if type(kind_of_body) is not str or kind_of_body != "error":
        return False
    error = document.get("error")
    if type(error) is not dict:
        return False
    kind = error.get("type")
    if type(kind) is not str or _TOKEN.fullmatch(kind) is None:
        return False
    return kind == "timeout_error"


def _is_usage_count(value: object) -> bool:
    return type(value) is int and 0 <= value <= MAX_USAGE_TOKENS


def _text_is_valid(block: dict[str, Any]) -> bool:
    if type(block.get("text")) is not str:
        return False
    if "citations" not in block:
        return True
    citations = block["citations"]
    return citations is None or (type(citations) is list and not citations)


def _end_turn_text(content: list[dict[str, Any]]) -> str:
    """V6-V8: exactly one valid ``text`` block among skipped thinking blocks."""
    malformed = AnthropicErrorCode.MALFORMED_RESPONSE
    texts: list[str] = []
    for block in content:
        kind = block["type"]
        if kind in ("thinking", "redacted_thinking"):
            continue
        _require(kind == "text" and _text_is_valid(block), malformed)
        texts.append(block["text"])
    _require(len(texts) == 1, malformed)
    size = utf8_size(texts[0])
    _require(size is not None, malformed)  # an escaped lone surrogate
    assert size is not None
    _require(size <= MAX_OUTPUT_TEXT_BYTES, AnthropicErrorCode.OUTPUT_TOO_LARGE)
    return texts[0]


def _message(body: bytes) -> ProviderResponse:
    """V1-V9 for a status 200 body (already admitted and within ``MAX_RESPONSE_BYTES``)."""
    malformed = AnthropicErrorCode.MALFORMED_RESPONSE
    decoded, document = _decode(body)
    _require(decoded and type(document) is dict, malformed)
    assert isinstance(document, dict)
    model = document.get("model")
    stop_reason = document.get("stop_reason")
    content = document.get("content")
    usage = document.get("usage")
    _require(type(document.get("type")) is str and document.get("type") == "message", malformed)
    _require(type(document.get("role")) is str and document.get("role") == "assistant", malformed)
    _require(type(model) is str and _MODEL_ID.fullmatch(model) is not None, malformed)
    _require(type(stop_reason) is str and _TOKEN.fullmatch(stop_reason) is not None, malformed)
    _require(type(content) is list and len(content) <= MAX_CONTENT_BLOCKS, malformed)
    assert isinstance(content, list)
    for block in content:
        _require(type(block) is dict, malformed)
        kind = block.get("type")
        _require(type(kind) is str and _TOKEN.fullmatch(kind) is not None, malformed)
    _require(type(usage) is dict, malformed)
    assert isinstance(usage, dict)
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    _require(_is_usage_count(input_tokens) and _is_usage_count(output_tokens), malformed)

    assert isinstance(stop_reason, str)
    stop_kind = _STOP_KINDS.get(stop_reason, StopKind.OTHER)
    output_text = _end_turn_text(content) if stop_kind is StopKind.END_TURN else ""

    built: list[ProviderResponse] = []
    with suppress(Exception):  # cannot fail for checked values; fixed code if it ever does
        built.append(
            ProviderResponse(
                stop_kind=stop_kind,
                output_text=output_text,
                model_used=model,  # type: ignore[arg-type]
                usage=ModelUsage(input_tokens, output_tokens),  # type: ignore[arg-type]
            )
        )
    _require(len(built) == 1, malformed)
    return built[0]


def parse_response(response: AnthropicResponse) -> ProviderResponse:
    """M5h-G and M5h-H: a ``ProviderResponse``, ``ModelCallTimeout`` or a fixed error."""
    admitted = _admitted(response)
    status = admitted.status
    if status == 200:
        return _message(admitted.body)
    timed_out = status == 504 or _is_timeout_envelope(admitted.body)
    if timed_out:
        raise ModelCallTimeout()
    raise AnthropicError(_status_code(status))


# --- the provider --------------------------------------------------------------------------------


def _transport_failure(error: Exception) -> AnthropicErrorCode | None:
    """By the exception's own type only; ``None`` means a timeout. No chain is inspected."""
    if isinstance(error, ModelCallTimeout):
        return None
    if not isinstance(error, AnthropicError):
        return AnthropicErrorCode.TRANSPORT_FAILED
    codes: list[object] = []
    with suppress(Exception):  # a deleted attribute or a raising property
        codes.append(error.code)
    if len(codes) == 1 and type(codes[0]) is AnthropicErrorCode:
        if codes[0] is AnthropicErrorCode.TIMEOUT:
            return None
        if codes[0] in _KEPT_TRANSPORT_CODES:
            return codes[0]
    return AnthropicErrorCode.TRANSPORT_FAILED


@dataclass(frozen=True, init=False, repr=False)
class AnthropicProvider:
    """A ``ModelProvider`` over an injected ``AnthropicTransport``. It is constructed explicitly
    by trusted code; nothing registers it in production."""

    transport: AnthropicTransport

    def __init__(self, transport: AnthropicTransport, **unknown: object) -> None:
        post: object = None
        try:
            post = getattr(transport, "post", None)
        except Exception:  # a raising attribute is a fixed configuration error below
            post = None
        _require(not unknown and callable(post), AnthropicErrorCode.CONFIGURATION)
        object.__setattr__(self, "transport", transport)

    @property
    def provider_id(self) -> str:
        return ANTHROPIC_PROVIDER_ID

    def generate(self, request: StructuredRequest) -> ProviderResponse:
        rebuilt = _revalidated_request(request)  # zero transport calls if invalid
        body = _body(rebuilt)  # zero transport calls if over the cap
        timeout_ms = rebuilt.timeout_ms
        returned: object = None
        failure: Exception | None = None
        try:
            returned = self.transport.post(body, timeout_ms=timeout_ms)
        except Exception as error:  # kept only as transient state; classified below
            failure = error
        if failure is not None:
            code = _transport_failure(failure)  # outside the handler, so nothing is chained
            failure = None
            if code is None:
                raise ModelCallTimeout()
            raise AnthropicError(code)
        return parse_response(returned)  # type: ignore[arg-type]

    def __repr__(self) -> str:
        return "AnthropicProvider()"

    __str__ = __repr__
