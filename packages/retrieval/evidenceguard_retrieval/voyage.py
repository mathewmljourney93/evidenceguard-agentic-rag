"""Voyage embedding adapter behind the M4a provider contract, with no I/O (M4f, ADR-0018).

``VoyageEmbedder`` builds one deterministic request body, hands it to an injected
``VoyageTransport`` and validates the response completely before the existing M4a checks. It
never sees the key, headers, host or timeouts; the standard-library HTTPS transport lives in
``evidenceguard_worker.voyage_http``. Nothing here reads the environment, files or network.

- **Identity.** ``VOYAGE_IDENTITY`` names the *requested* model ``voyage-4-lite`` at 1024
  dimensions; no upstream immutability is claimed. The request options, encoding and
  validation rules are covered by ``algorithm_version``: any change needs a new version.
- **Calls.** An invalid request makes zero transport calls; otherwise ``embed`` makes at most
  one ``post`` call. There is no retry, pagination or splitting.
- **Validation.** A complete ``VoyageResponse`` first (exact types; a non-200 value must be
  status-only), then the status, size, strict JSON (no ``NaN``/``Infinity``, no duplicate
  keys), shape, exact model echo, row cardinality and indexes (rows are placed by ``index``),
  finite coordinates and usage, and finally M4a's ``EmbeddingBatch`` rules. Nothing is
  renormalized, rounded or substituted; zero vectors are rejected by M4a.
- **Errors.** ``VoyageError`` carries one fixed code (also its message) and nothing else:
  public errors are created fresh outside every ``except`` block, so they have no cause or
  context. Invalid embedding *requests* (texts, ``input_type``, ``count``) raise M4a's
  ``InvalidEmbeddingError``. Only ``Exception`` is caught; process control propagates.
"""

import json
import math
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol, cast

from evidenceguard_domain.embeddings import (
    EmbeddingBatch,
    EmbeddingIdentity,
    EmbeddingUsage,
    InputType,
    InvalidEmbeddingError,
    Vector,
    validate_request,
)

VOYAGE_MODEL = "voyage-4-lite"
VOYAGE_IDENTITY = EmbeddingIdentity("voyage", VOYAGE_MODEL, "voyage-http-v1", 1024, "l2")
VOYAGE_HOST = "api.voyageai.com"
VOYAGE_PATH = "/v1/embeddings"
MAX_REQUEST_BYTES = 1_048_576
MAX_RESPONSE_BYTES = 4_194_304
MAX_USAGE_TOKENS = 2**63 - 1
MAX_TEXTS = 32


class VoyageErrorCode(StrEnum):
    CONFIGURATION = "voyage_configuration"
    AUTHENTICATION = "voyage_authentication"
    REQUEST_REJECTED = "voyage_request_rejected"
    RATE_LIMITED = "voyage_rate_limited"
    SERVER_ERROR = "voyage_server_error"
    UNEXPECTED_STATUS = "voyage_unexpected_status"
    TIMEOUT = "voyage_timeout"
    TRANSPORT_FAILED = "voyage_transport_failed"
    RESPONSE_TOO_LARGE = "voyage_response_too_large"
    MALFORMED_RESPONSE = "voyage_malformed_response"
    INVALID_VECTOR = "voyage_invalid_vector"


RETRYABLE_CODES = frozenset(
    {
        VoyageErrorCode.RATE_LIMITED,
        VoyageErrorCode.SERVER_ERROR,
        VoyageErrorCode.TIMEOUT,
        VoyageErrorCode.TRANSPORT_FAILED,
    }
)


class VoyageError(Exception):
    """A fixed, private adapter or transport failure. The message is the code."""

    def __init__(self, code: VoyageErrorCode) -> None:
        if type(code) is not VoyageErrorCode:
            raise TypeError("code must be a VoyageErrorCode")
        super().__init__(code.value)
        self.code = code

    @property
    def retryable(self) -> bool:
        return self.code in RETRYABLE_CODES


def _require(condition: bool, code: VoyageErrorCode) -> None:
    if not condition:
        raise VoyageError(code)


def status_code(status: int) -> VoyageErrorCode:
    """The fixed code for a non-200 HTTP status."""
    if status in (401, 403):
        return VoyageErrorCode.AUTHENTICATION
    if status == 429:
        return VoyageErrorCode.RATE_LIMITED
    if 400 <= status <= 499:
        return VoyageErrorCode.REQUEST_REJECTED
    if 500 <= status <= 599:
        return VoyageErrorCode.SERVER_ERROR
    return VoyageErrorCode.UNEXPECTED_STATUS


@dataclass(frozen=True, init=False, repr=False)
class VoyageResponse:
    """One transport result: a status, and the body for status 200 only (``b""`` otherwise)."""

    status: int
    body: bytes

    def __init__(self, status: int, body: bytes) -> None:
        _require(type(status) is int and 100 <= status <= 599, VoyageErrorCode.MALFORMED_RESPONSE)
        _require(type(body) is bytes, VoyageErrorCode.MALFORMED_RESPONSE)
        _require(status == 200 or body == b"", VoyageErrorCode.MALFORMED_RESPONSE)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "body", body)

    def __repr__(self) -> str:
        return f"VoyageResponse(status={self.status})"

    __str__ = __repr__


def _revalidated(response: object) -> VoyageResponse:
    """Reconstruct ``response`` from its fields to reject bypassed or foreign values."""
    _require(type(response) is VoyageResponse, VoyageErrorCode.MALFORMED_RESPONSE)
    return VoyageResponse(getattr(response, "status", None), getattr(response, "body", None))  # type: ignore[arg-type]


class VoyageTransport(Protocol):
    def post(self, body: bytes) -> VoyageResponse: ...


# --- request -------------------------------------------------------------------------------------


def build_request_body(texts: tuple[str, ...], input_type: InputType) -> bytes:
    """The deterministic ASCII request body, or M4a's ``InvalidEmbeddingError`` for an invalid
    request."""
    validate_request(texts, input_type)
    payload = {
        "input": list(texts),
        "input_type": input_type,
        "model": VOYAGE_MODEL,
        "output_dimension": VOYAGE_IDENTITY.dims,
        "output_dtype": "float",
        "truncation": False,
    }
    body = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")
    _require(len(body) <= MAX_REQUEST_BYTES, VoyageErrorCode.CONFIGURATION)
    return body


# --- response ------------------------------------------------------------------------------------


def _reject_constant(name: str) -> object:
    raise ValueError("non-finite JSON constant")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    document: dict[str, Any] = {}
    for key, value in pairs:
        if key in document:
            raise ValueError("duplicate JSON key")
        document[key] = value
    return document


def _decode(body: bytes) -> object:
    failed = False
    document: object = None
    try:
        document = json.loads(
            body.decode("utf-8", errors="strict"),
            parse_constant=_reject_constant,
            object_pairs_hook=_unique_object,
        )
    except Exception:  # UnicodeDecodeError, ValueError, RecursionError: fixed and private
        failed = True
    _require(not failed, VoyageErrorCode.MALFORMED_RESPONSE)
    return document


def _is_text(value: object, expected: str) -> bool:
    return type(value) is str and value == expected


def _finite(value: object) -> bool:
    if type(value) is float:
        return math.isfinite(value)
    if type(value) is not int:
        return False
    converted = math.inf
    with suppress(OverflowError):  # too large for a float: rejected, outside any handler
        converted = float(value)
    return math.isfinite(converted)


def _extract(document: object, count: int) -> tuple[tuple[Vector, ...], EmbeddingUsage]:
    malformed = VoyageErrorCode.MALFORMED_RESPONSE
    _require(type(document) is dict, malformed)
    top = cast(dict[str, Any], document)
    data, usage = top.get("data"), top.get("usage")
    _require(_is_text(top.get("object"), "list"), malformed)
    _require(type(data) is list and type(usage) is dict, malformed)
    _require(_is_text(top.get("model"), VOYAGE_MODEL), malformed)
    rows, totals = cast(list[Any], data), cast(dict[str, Any], usage)
    _require(len(rows) == count, malformed)
    slots: list[Vector | None] = [None] * count
    for item in rows:
        _require(type(item) is dict, malformed)
        row = cast(dict[str, Any], item)
        _require(_is_text(row.get("object"), "embedding"), malformed)
        index: Any = row.get("index")
        embedding: Any = row.get("embedding")
        _require(type(index) is int and 0 <= index < count, malformed)
        _require(slots[index] is None, malformed)
        _require(type(embedding) is list and len(embedding) == VOYAGE_IDENTITY.dims, malformed)
        _require(all(_finite(value) for value in embedding), malformed)
        slots[index] = tuple(embedding)
    tokens = totals.get("total_tokens")
    _require(type(tokens) is int and 0 <= tokens <= MAX_USAGE_TOKENS, malformed)
    vectors = tuple(vector for vector in slots if vector is not None)
    _require(len(vectors) == count, malformed)
    return vectors, EmbeddingUsage(tokens)


def _batch(
    input_type: InputType, vectors: tuple[Vector, ...], usage: EmbeddingUsage
) -> EmbeddingBatch:
    batches: list[EmbeddingBatch] = []
    with suppress(Exception):  # M4a's InvalidEmbeddingError: dimension, norm or zero vector
        batches.append(EmbeddingBatch(VOYAGE_IDENTITY, input_type, vectors, usage))
    _require(len(batches) == 1, VoyageErrorCode.INVALID_VECTOR)
    return batches[0]


def parse_response(
    response: VoyageResponse, *, input_type: InputType, count: int
) -> EmbeddingBatch:
    """Validate one transport result for a request of ``count`` texts (see the module
    docstring for the order); raise ``VoyageError`` or M4a's ``InvalidEmbeddingError``."""
    if not (type(input_type) is str and input_type in ("query", "document")):
        raise InvalidEmbeddingError()
    if not (type(count) is int and 1 <= count <= MAX_TEXTS):
        raise InvalidEmbeddingError()
    checked = _revalidated(response)
    if checked.status != 200:
        raise VoyageError(status_code(checked.status))
    _require(len(checked.body) <= MAX_RESPONSE_BYTES, VoyageErrorCode.RESPONSE_TOO_LARGE)
    vectors, usage = _extract(_decode(checked.body), count)
    return _batch(input_type, vectors, usage)


# --- the provider --------------------------------------------------------------------------------


@dataclass(frozen=True, init=False, repr=False)
class VoyageEmbedder:
    """An ``EmbeddingProvider`` for ``VOYAGE_IDENTITY`` over an injected transport. It is
    constructed explicitly by trusted code; nothing registers it in production."""

    transport: VoyageTransport

    def __init__(self, transport: VoyageTransport) -> None:
        post: object = None
        try:
            post = getattr(transport, "post", None)
        except Exception:  # a raising attribute is a fixed configuration error below
            post = None
        _require(callable(post), VoyageErrorCode.CONFIGURATION)
        object.__setattr__(self, "transport", transport)

    @property
    def identity(self) -> EmbeddingIdentity:
        return VOYAGE_IDENTITY

    def embed(self, texts: tuple[str, ...], input_type: InputType) -> EmbeddingBatch:
        body = build_request_body(texts, input_type)  # zero transport calls if invalid
        response = self._post(body)  # at most one call; revalidated by parse_response
        return parse_response(
            cast(VoyageResponse, response), input_type=input_type, count=len(texts)
        )

    def _post(self, body: bytes) -> object:
        failed: Exception | None = None
        response: object = None
        try:
            response = self.transport.post(body)
        except Exception as error:  # kept only as transient state; classified below
            failed = error
        if failed is None:
            return response
        code = _transport_code(failed)  # outside the handler, so nothing is chained
        failed = None
        raise VoyageError(code)

    def __repr__(self) -> str:
        return "VoyageEmbedder()"

    __str__ = __repr__


def _transport_code(error: Exception) -> VoyageErrorCode:
    """The fixed code for an ordinary exception from a transport, by its own type only.

    A ``VoyageError`` keeps its code only when that code is a real ``VoyageErrorCode``; a
    missing, invalid or ordinarily raising ``code`` is ``voyage_transport_failed``. Process
    control raised while reading it propagates as the same object. No chain is inspected."""
    if not isinstance(error, VoyageError):
        return VoyageErrorCode.TRANSPORT_FAILED
    codes: list[object] = []
    with suppress(Exception):  # e.g. a deleted attribute or a raising property
        codes.append(error.code)
    if len(codes) == 1 and type(codes[0]) is VoyageErrorCode:
        return codes[0]
    return VoyageErrorCode.TRANSPORT_FAILED
