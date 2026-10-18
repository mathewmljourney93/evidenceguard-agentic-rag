"""The pure Voyage adapter (``evidenceguard_retrieval.voyage``, M4f, ADR-0018) with fake
transports, plus mocked integration with the existing M4c indexing and M4d retrieval seams.

No test here touches the network: an autouse guard makes any socket connection or name lookup
fail the test, and every transport is an in-memory fake. These tests establish request
formation, validation, call bounds, error mapping and privacy only; they make no claim about
live Voyage compatibility, semantic quality, latency, cost or production readiness.
"""

import hashlib
import json
import logging
import socket
import traceback
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_domain.embedding_storage import index_id, profile_id, stored_embeddings
from evidenceguard_domain.embeddings import EmbeddingBatch, InvalidEmbeddingError
from evidenceguard_domain.jobs import (
    JobErrorCode,
    JobPayload,
    JobSnapshot,
    JobStatus,
    LeaseLostError,
)
from evidenceguard_domain.retrieval import (
    RETRIEVAL_CONFIG_V1,
    PendingExclusions,
    RetrievalProviderError,
    RetrievalRequest,
    RetrievalSnapshot,
    RevisionBinding,
)
from evidenceguard_persistence import embeddings as embedding_store
from evidenceguard_persistence import indexing as index_store
from evidenceguard_persistence.embeddings import IndexSnapshot, ProfileSnapshot
from evidenceguard_persistence.indexing import PendingChunk
from evidenceguard_persistence.jobs import FencedSession
from evidenceguard_retrieval import voyage
from evidenceguard_retrieval.embeddings import HASH_IDENTITY, HashingEmbedder, embed_validated
from evidenceguard_retrieval.voyage import (
    MAX_RESPONSE_BYTES,
    VOYAGE_IDENTITY,
    VoyageEmbedder,
    VoyageError,
    VoyageErrorCode,
    VoyageResponse,
    build_request_body,
    parse_response,
)
from evidenceguard_worker import indexing
from evidenceguard_worker import retrieval as orchestration
from evidenceguard_worker.context import (
    HandlerFence,
    JobCancelledError,
    JobContext,
    PermanentJobError,
)

C = VoyageErrorCode
CANARY = "synthetic-private-canary-7f3a"
DIMS = 1024
# SHA-256 of the literal canonical identity JSON, computed outside the project code:
# {"algorithm_version":"voyage-http-v1","dims":1024,"model_id":"voyage-4-lite",
#  "normalization":"l2","provider_id":"voyage"}
FINGERPRINT = "827fb43a08091171e8eea7b14f6943506646aff6e4dafe7e6fd47cca643cc109"


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: object, **kwargs: object) -> Any:
        raise AssertionError("a test attempted network access")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


# --- helpers -------------------------------------------------------------------------------------


def axis(position: int, value: float = 1.0) -> list[float]:
    vector = [0.0] * DIMS
    vector[position] = value
    return vector


def document(
    count: int = 2,
    *,
    order: list[int] | None = None,
    model: object = "voyage-4-lite",
    tokens: object = 7,
    vectors: list[list[Any]] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    chosen = vectors if vectors is not None else [axis(i) for i in range(count)]
    indexes = order if order is not None else list(range(len(chosen)))
    data = [{"object": "embedding", "embedding": chosen[i], "index": i} for i in indexes]
    value: dict[str, Any] = {
        "object": "list",
        "data": data,
        "model": model,
        "usage": {"total_tokens": tokens},
    }
    value.update(extra or {})
    return value


def ok(value: dict[str, Any] | bytes) -> VoyageResponse:
    body = value if isinstance(value, bytes) else json.dumps(value).encode()
    return VoyageResponse(200, body)


class FakeTransport:
    """Records every body and returns, or raises, the scripted outcome."""

    def __init__(self, outcome: Any = None, factory: Callable[[bytes], Any] | None = None):
        self.outcome = outcome
        self.factory = factory
        self.bodies: list[bytes] = []

    def post(self, body: bytes) -> Any:
        self.bodies.append(body)
        if self.factory is not None:
            return self.factory(body)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


def echo(body: bytes) -> VoyageResponse:
    """A valid response for any request: offline-hash unit vectors, in reversed row order."""
    request = json.loads(body)
    texts = tuple(request["input"])
    batch = HashingEmbedder().embed(texts, request["input_type"])
    assert all(any(vector) for vector in batch.vectors), "the fixture needs nonzero vectors"
    vectors = [list(vector) for vector in batch.vectors]
    order = list(reversed(range(len(texts))))
    return ok(document(vectors=vectors, order=order, tokens=len(texts)))


def embed(transport: Any, texts: tuple[str, ...] = ("alpha", "beta")) -> EmbeddingBatch:
    return VoyageEmbedder(transport).embed(texts, "document")


def code_of(raised: pytest.ExceptionInfo[VoyageError]) -> VoyageErrorCode:
    return raised.value.code


def assert_private(error: BaseException, *secrets: str) -> None:
    rendered = [
        str(error),
        repr(error),
        repr(error.args),
        "".join(traceback.format_exception(error)),
    ]
    for secret in (CANARY, *secrets):
        assert all(secret not in text for text in rendered)
    assert error.__cause__ is None and error.__context__ is None


# --- identity and request ------------------------------------------------------------------------


def test_the_identity_and_its_fingerprint_are_pinned() -> None:
    assert (
        VOYAGE_IDENTITY.provider_id,
        VOYAGE_IDENTITY.model_id,
        VOYAGE_IDENTITY.algorithm_version,
        VOYAGE_IDENTITY.dims,
        VOYAGE_IDENTITY.normalization,
    ) == ("voyage", "voyage-4-lite", "voyage-http-v1", 1024, "l2")
    literal = (
        b'{"algorithm_version":"voyage-http-v1","dims":1024,"model_id":"voyage-4-lite",'
        b'"normalization":"l2","provider_id":"voyage"}'
    )
    assert hashlib.sha256(literal).hexdigest() == FINGERPRINT
    assert VOYAGE_IDENTITY.fingerprint == FINGERPRINT
    assert VoyageEmbedder(FakeTransport()).identity == VOYAGE_IDENTITY


@pytest.mark.parametrize("input_type", ["document", "query"])
def test_the_request_bytes_are_exact(input_type: str) -> None:
    expected = (
        (
            '{"input":["Retention policy"],"input_type":"INPUT_TYPE","model":"voyage-4-lite",'
            '"output_dimension":1024,"output_dtype":"float","truncation":false}'
        )
        .replace("INPUT_TYPE", input_type)
        .encode()
    )
    assert build_request_body(("Retention policy",), input_type) == expected  # type: ignore[arg-type]


def test_non_ascii_supplementary_control_and_duplicate_texts_are_escaped_in_order() -> None:
    body = build_request_body(("é😀\tx\ny\x01", "dup", "dup"), "document")
    assert body.isascii()
    assert body.startswith(b'{"input":["\\u00e9\\ud83d\\ude00\\tx\\ny\\u0001","dup","dup"],')
    assert json.loads(body)["input"] == ["é😀\tx\ny\x01", "dup", "dup"]


def test_thirty_two_texts_are_one_request_in_order() -> None:
    texts = tuple(f"text {n}" for n in range(32))
    transport = FakeTransport(factory=echo)
    batch = VoyageEmbedder(transport).embed(texts, "query")
    assert len(transport.bodies) == 1 and json.loads(transport.bodies[0])["input"] == list(texts)
    assert batch.vectors == HashingEmbedder().embed(texts, "query").vectors


@pytest.mark.parametrize(
    ("texts", "input_type"),
    [
        ((), "document"),
        (tuple("x" for _ in range(33)), "document"),
        (("",), "document"),
        ((" \t",), "document"),
        (("a\x00b",), "document"),
        (("x" * 4001,), "document"),
        (("\ud800",), "document"),
        (["list"], "document"),
        (("ok",), "other"),
        (("ok",), None),
        ((b"bytes",), "document"),
        (tuple("😀" * 4000 for _ in range(9)), "document"),  # 144,000 bytes > 128,000
    ],
)
def test_an_invalid_request_raises_the_m4a_error_with_zero_transport_calls(
    texts: Any, input_type: Any
) -> None:
    transport = FakeTransport(factory=echo)
    with pytest.raises(InvalidEmbeddingError):
        VoyageEmbedder(transport).embed(texts, input_type)
    with pytest.raises(InvalidEmbeddingError):
        build_request_body(texts, input_type)
    assert transport.bodies == []


# --- valid responses -----------------------------------------------------------------------------


def test_a_valid_response_becomes_the_batch_with_usage_and_one_call() -> None:
    transport = FakeTransport(ok(document(2)))
    batch = embed(transport)
    assert len(transport.bodies) == 1
    assert batch.identity == VOYAGE_IDENTITY and batch.input_type == "document"
    assert batch.vectors == (tuple(axis(0)), tuple(axis(1)))
    assert batch.usage.input_tokens == 7
    assert batch.label == "provider embeddings"


def test_reordered_rows_are_placed_by_their_index() -> None:
    vectors = [axis(5), axis(6), axis(7)]
    batch = embed(FakeTransport(ok(document(vectors=vectors, order=[2, 0, 1]))), ("a", "b", "c"))
    assert batch.vectors == tuple(tuple(vector) for vector in vectors)


def test_integer_coordinates_and_unknown_fields_are_accepted_without_retention() -> None:
    vector: list[Any] = [0] * DIMS
    vector[3] = 1
    value = document(1, vectors=[vector], extra={"unknown": CANARY})
    value["data"][0]["unknown"] = CANARY
    batch = embed(FakeTransport(ok(value)), ("only",))
    assert batch.vectors == (tuple(vector),) and type(batch.vectors[0][3]) is int
    assert CANARY not in repr(batch)


def test_through_embed_validated_the_m4a_boundary_accepts_a_valid_batch() -> None:
    batch = embed_validated(VoyageEmbedder(FakeTransport(factory=echo)), ("one",), "document")
    assert batch.identity == VOYAGE_IDENTITY


# --- malformed responses -------------------------------------------------------------------------


def _with(change: Callable[[dict[str, Any]], None]) -> bytes:
    value = document(2)
    change(value)
    return json.dumps(value).encode()


def _replace_first_coordinate(literal: str) -> bytes:
    text = json.dumps(document(2))
    return text.replace("[1.0, 0.0", f"[{literal}, 0.0", 1).encode()


MALFORMED: dict[str, bytes] = {
    "not json": b"not json",
    "invalid utf-8": b'{"object": "list\xff"}',
    "bom": b"\xef\xbb\xbf" + json.dumps(document(2)).encode(),
    "NaN": _replace_first_coordinate("NaN"),
    "Infinity": _replace_first_coordinate("Infinity"),
    "-Infinity": _replace_first_coordinate("-Infinity"),
    "1e400": _replace_first_coordinate("1e400"),
    "huge integer": _replace_first_coordinate("1" + "0" * 400),
    "over-long integer": _replace_first_coordinate("1" * 5000),
    "duplicate top key": json.dumps(document(2)).encode()[:-1] + b', "model": "voyage-4-lite"}',
    "duplicate item key": json.dumps(document(2))
    .replace('"index": 0', '"index": 0, "index": 0')
    .encode(),
    "deep nesting": b"[" * 100_000,
    "top-level list": b"[]",
    "object marker": _with(lambda v: v.update(object="embedding")),
    "missing object": _with(lambda v: v.pop("object")),
    "data not list": _with(lambda v: v.update(data={})),
    "usage not object": _with(lambda v: v.update(usage=[])),
    "missing usage": _with(lambda v: v.pop("usage")),
    "wrong model": _with(lambda v: v.update(model="voyage-4")),
    "model case": _with(lambda v: v.update(model="Voyage-4-lite")),
    "missing model": _with(lambda v: v.pop("model")),
    "too few rows": _with(lambda v: v["data"].pop()),
    "too many rows": _with(lambda v: v["data"].append(dict(v["data"][0], index=2))),
    "duplicate index": _with(lambda v: v["data"][1].update(index=0)),
    "out-of-range index": _with(lambda v: v["data"][1].update(index=2)),
    "negative index": _with(lambda v: v["data"][1].update(index=-1)),
    "bool index": _with(lambda v: v["data"][1].update(index=True)),
    "string index": _with(lambda v: v["data"][1].update(index="1")),
    "missing index": _with(lambda v: v["data"][1].pop("index")),
    "item not object": _with(lambda v: v["data"].__setitem__(1, [])),
    "item marker": _with(lambda v: v["data"][1].update(object="list")),
    "embedding not list": _with(lambda v: v["data"][1].update(embedding={})),
    "dimension 1023": _with(lambda v: v["data"][1].update(embedding=axis(1)[:-1])),
    "dimension 1025": _with(lambda v: v["data"][1].update(embedding=[*axis(1), 0.0])),
    "string coordinate": _with(lambda v: v["data"][1]["embedding"].__setitem__(1, "1.0")),
    "null coordinate": _with(lambda v: v["data"][1]["embedding"].__setitem__(0, None)),
    "bool coordinate": _with(lambda v: v["data"][1]["embedding"].__setitem__(0, False)),
    "negative usage": _with(lambda v: v["usage"].update(total_tokens=-1)),
    "bool usage": _with(lambda v: v["usage"].update(total_tokens=True)),
    "float usage": _with(lambda v: v["usage"].update(total_tokens=7.0)),
    "string usage": _with(lambda v: v["usage"].update(total_tokens="7")),
    "missing usage tokens": _with(lambda v: v["usage"].pop("total_tokens")),
    "usage above 2^63-1": _with(lambda v: v["usage"].update(total_tokens=2**63)),
}


@pytest.mark.parametrize("case", sorted(MALFORMED))
def test_a_malformed_response_is_a_fixed_private_error(case: str) -> None:
    transport = FakeTransport(ok(MALFORMED[case]))
    with pytest.raises(VoyageError) as raised:
        embed(transport)
    assert code_of(raised) is C.MALFORMED_RESPONSE and not raised.value.retryable
    assert len(transport.bodies) == 1
    assert_private(raised.value)


def test_the_largest_usage_value_is_accepted() -> None:
    assert embed(FakeTransport(ok(document(2, tokens=2**63 - 1)))).usage.input_tokens == 2**63 - 1


@pytest.mark.parametrize(
    "vector",
    [
        axis(0, 0.5),
        axis(0, 1.0 + 2e-6),
        [0.0] * DIMS,
        [0] * DIMS,
    ],
    ids=["half", "over-tolerance", "zero-float", "zero-int"],
)
def test_non_unit_and_zero_vectors_are_invalid_vectors_never_corrected(vector: list[Any]) -> None:
    with pytest.raises(VoyageError) as raised:
        embed(FakeTransport(ok(document(vectors=[axis(1), vector]))))
    assert code_of(raised) is C.INVALID_VECTOR


def test_an_m4a_valid_vector_that_fails_float32_storage_is_rejected_by_storage() -> None:
    batch = embed(FakeTransport(ok(document(vectors=[axis(0, 0.999999001)]))), ("one",))
    assert batch.vectors[0][0] == 0.999999001  # no renormalization in the adapter
    with pytest.raises(InvalidEmbeddingError):
        stored_embeddings(batch, identity=VOYAGE_IDENTITY, chunks=[(UUID(int=1), "a" * 64)])


def test_an_oversized_200_body_is_too_large() -> None:
    with pytest.raises(VoyageError) as raised:
        embed(FakeTransport(ok(b" " * (MAX_RESPONSE_BYTES + 1))))
    assert code_of(raised) is C.RESPONSE_TOO_LARGE


# --- statuses ------------------------------------------------------------------------------------

STATUSES = {
    400: C.REQUEST_REJECTED,
    401: C.AUTHENTICATION,
    403: C.AUTHENTICATION,
    404: C.REQUEST_REJECTED,
    413: C.REQUEST_REJECTED,
    422: C.REQUEST_REJECTED,
    429: C.RATE_LIMITED,
    499: C.REQUEST_REJECTED,
    500: C.SERVER_ERROR,
    502: C.SERVER_ERROR,
    503: C.SERVER_ERROR,
    504: C.SERVER_ERROR,
    599: C.SERVER_ERROR,
    100: C.UNEXPECTED_STATUS,
    204: C.UNEXPECTED_STATUS,
    301: C.UNEXPECTED_STATUS,
    302: C.UNEXPECTED_STATUS,
    399: C.UNEXPECTED_STATUS,
}


@pytest.mark.parametrize("status", sorted(STATUSES))
def test_each_status_maps_to_its_fixed_code(status: int) -> None:
    transport = FakeTransport(VoyageResponse(status, b""))
    with pytest.raises(VoyageError) as raised:
        embed(transport)
    assert code_of(raised) is STATUSES[status] and len(transport.bodies) == 1
    retryable = STATUSES[status] in (C.RATE_LIMITED, C.SERVER_ERROR)
    assert raised.value.retryable is retryable


def test_the_retryable_codes_are_exactly_the_transient_ones() -> None:
    transient = {C.RATE_LIMITED, C.SERVER_ERROR, C.TIMEOUT, C.TRANSPORT_FAILED}
    assert transient == voyage.RETRYABLE_CODES
    assert all(VoyageError(code).retryable is (code in transient) for code in C)
    error = VoyageError(C.TIMEOUT)
    assert error.args == ("voyage_timeout",) and str(error) == "voyage_timeout"
    with pytest.raises(TypeError):
        VoyageError("voyage_timeout")  # type: ignore[arg-type]


# --- direct calls and configuration (C2) ---------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (True, b""),
        (False, b""),
        (200.0, b""),
        ("200", b""),
        (None, b""),
        (99, b""),
        (600, b""),
        (200, bytearray(b"{}")),
        (200, "{}"),
        (200, memoryview(b"{}")),
        (200, None),
        (429, b"detail"),
        (503, b" "),
    ],
)
def test_an_invalid_voyage_response_value_is_malformed(status: Any, body: Any) -> None:
    with pytest.raises(VoyageError) as raised:
        VoyageResponse(status, body)
    assert code_of(raised) is C.MALFORMED_RESPONSE


def test_a_bypassed_or_foreign_response_is_malformed_before_any_status_mapping() -> None:
    class Subclass(VoyageResponse):
        pass

    bypassed = VoyageResponse(429, b"")
    object.__setattr__(bypassed, "body", f"detail {CANARY}".encode())  # non-200 with a body
    retyped = VoyageResponse(200, b"{}")
    object.__setattr__(retyped, "status", "200")
    for value in (bypassed, retyped, Subclass(200, b"{}"), None, {}, (200, b"{}"), object()):
        with pytest.raises(VoyageError) as raised:
            parse_response(value, input_type="document", count=1)  # type: ignore[arg-type]
        assert code_of(raised) is C.MALFORMED_RESPONSE
        with pytest.raises(VoyageError) as through:
            embed(FakeTransport(value), ("one",))
        assert code_of(through) is C.MALFORMED_RESPONSE
        assert_private(through.value)


@pytest.mark.parametrize(
    ("input_type", "count"),
    [
        ("other", 1),
        (None, 1),
        ("document", True),
        ("document", 0),
        ("document", 33),
        ("query", 1.0),
        ("query", "1"),
    ],
)
def test_invalid_parse_arguments_raise_the_m4a_error(input_type: Any, count: Any) -> None:
    with pytest.raises(InvalidEmbeddingError):
        parse_response(ok(document(1)), input_type=input_type, count=count)


class NonCallablePost:
    post = 3


@pytest.mark.parametrize("transport", [object(), None, NonCallablePost()])
def test_an_embedder_needs_a_transport_with_a_callable_post(transport: Any) -> None:
    with pytest.raises(VoyageError) as raised:
        VoyageEmbedder(transport)
    assert code_of(raised) is C.CONFIGURATION


def test_a_raising_post_attribute_is_a_configuration_error() -> None:
    class Raising:
        @property
        def post(self) -> Any:
            raise RuntimeError(CANARY)

    with pytest.raises(VoyageError) as raised:
        VoyageEmbedder(Raising())
    assert code_of(raised) is C.CONFIGURATION
    assert_private(raised.value)


# --- transport failures and process control ------------------------------------------------------


@pytest.mark.parametrize("code", [C.RATE_LIMITED, C.TIMEOUT, C.AUTHENTICATION, C.TRANSPORT_FAILED])
def test_a_voyage_error_from_the_transport_is_re_raised_fresh_with_its_code(
    code: VoyageErrorCode,
) -> None:
    original = VoyageError(code)
    transport = FakeTransport(original)
    with pytest.raises(VoyageError) as raised:
        embed(transport)
    assert raised.value is not original and code_of(raised) is code
    assert len(transport.bodies) == 1
    assert_private(raised.value)


@pytest.mark.parametrize(
    "error",
    [RuntimeError(CANARY), OSError(CANARY), ValueError(CANARY), KeyError(CANARY)],
)
def test_an_ordinary_transport_exception_is_a_private_transport_failure(error: Exception) -> None:
    transport = FakeTransport(error)
    with pytest.raises(VoyageError) as raised:
        embed(transport)
    assert code_of(raised) is C.TRANSPORT_FAILED and len(transport.bodies) == 1
    assert_private(raised.value)


def test_an_ordinary_exception_with_process_control_in_its_chain_stays_ordinary() -> None:
    error = RuntimeError(CANARY)
    error.__context__ = KeyboardInterrupt()
    error.__cause__ = SystemExit(3)
    with pytest.raises(VoyageError) as raised:
        embed(FakeTransport(error))
    assert code_of(raised) is C.TRANSPORT_FAILED
    assert_private(raised.value)


def test_a_voyage_error_with_a_forged_code_is_a_transport_failure() -> None:
    forged = VoyageError(C.RATE_LIMITED)
    forged.code = "voyage_rate_limited"  # type: ignore[assignment]
    with pytest.raises(VoyageError) as raised:
        embed(FakeTransport(forged))
    assert code_of(raised) is C.TRANSPORT_FAILED


# --- transport error metadata (Prompt 159 correction A) ------------------------------------------


class RaisingCode(VoyageError):
    """A ``VoyageError`` whose ``code`` property raises ``failure`` (set after construction)."""

    failure: BaseException | None = None

    @property
    def code(self) -> VoyageErrorCode:
        if self.failure is not None:
            raise self.failure
        return C.RATE_LIMITED

    @code.setter
    def code(self, value: VoyageErrorCode) -> None:
        pass  # VoyageError.__init__ assigns it; the property ignores the value


def test_a_transport_voyage_error_with_its_code_deleted_is_a_fresh_transport_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    original = VoyageError(C.RATE_LIMITED)
    del original.code
    transport = FakeTransport(original)
    with pytest.raises(VoyageError) as raised:
        embed(transport)
    assert raised.value is not original and code_of(raised) is C.TRANSPORT_FAILED
    assert len(transport.bodies) == 1 and not caplog.records
    assert_private(raised.value)


@pytest.mark.parametrize(
    "failure",
    [RuntimeError(CANARY), AttributeError(CANARY), ValueError(CANARY), TimeoutError(CANARY)],
    ids=["runtime", "attribute", "value", "timeout"],
)
def test_a_code_property_raising_an_ordinary_error_is_a_fresh_private_transport_failure(
    failure: Exception,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    original = RaisingCode(C.RATE_LIMITED)
    original.failure = failure
    transport = FakeTransport(original)
    with pytest.raises(VoyageError) as raised:
        embed(transport)
    assert type(raised.value) is VoyageError and code_of(raised) is C.TRANSPORT_FAILED
    assert len(transport.bodies) == 1
    assert_private(raised.value)
    output = capsys.readouterr()
    assert CANARY not in output.out + output.err and not caplog.records


def test_a_code_property_raising_with_process_control_in_its_chain_stays_ordinary() -> None:
    failure = RuntimeError(CANARY)
    failure.__context__ = KeyboardInterrupt()
    failure.__cause__ = SystemExit(2)
    original = RaisingCode(C.RATE_LIMITED)
    original.failure = failure
    with pytest.raises(VoyageError) as raised:
        embed(FakeTransport(original))
    assert code_of(raised) is C.TRANSPORT_FAILED
    assert_private(raised.value)


@pytest.mark.parametrize("control", [KeyboardInterrupt, SystemExit])
def test_process_control_from_a_code_property_propagates_as_the_same_object(
    control: type[BaseException],
) -> None:
    signal = control()
    original = RaisingCode(C.RATE_LIMITED)
    original.failure = signal
    transport = FakeTransport(original)
    with pytest.raises(control) as raised:
        embed(transport)
    assert raised.value is signal and len(transport.bodies) == 1


@pytest.mark.parametrize("code", list(C))
def test_every_valid_transport_code_is_preserved_in_a_fresh_error(code: VoyageErrorCode) -> None:
    original = VoyageError(code)
    with pytest.raises(VoyageError) as raised:
        embed(FakeTransport(original))
    assert raised.value is not original and code_of(raised) is code
    assert_private(raised.value)
    working = RaisingCode(C.RATE_LIMITED)  # a subclass with a valid, non-raising code
    with pytest.raises(VoyageError) as subclassed:
        embed(FakeTransport(working))
    assert type(subclassed.value) is VoyageError and code_of(subclassed) is C.RATE_LIMITED


@pytest.mark.parametrize("value", [None, 7, "voyage_timeout", object()])
def test_a_transport_voyage_error_with_an_invalid_code_is_a_transport_failure(value: Any) -> None:
    original = VoyageError(C.TIMEOUT)
    original.code = value
    with pytest.raises(VoyageError) as raised:
        embed(FakeTransport(original))
    assert code_of(raised) is C.TRANSPORT_FAILED
    assert_private(raised.value)


@pytest.mark.parametrize("control", [KeyboardInterrupt, SystemExit, GeneratorExit])
def test_process_control_from_the_transport_propagates_as_the_same_object(
    control: type[BaseException],
) -> None:
    signal = control()
    transport = FakeTransport(signal)
    with pytest.raises(control) as raised:
        embed(transport)
    assert raised.value is signal and len(transport.bodies) == 1


def test_embed_validated_turns_every_voyage_error_into_the_m4a_error() -> None:
    """The unchanged M4a boundary (V11): retryability is not visible past ``embed_validated``."""
    for outcome in (VoyageError(C.RATE_LIMITED), VoyageResponse(503, b""), ok(b"not json")):
        with pytest.raises(InvalidEmbeddingError) as raised:
            embed_validated(VoyageEmbedder(FakeTransport(outcome)), ("one",), "document")
        assert raised.value.__cause__ is None and raised.value.__context__ is None


# --- privacy -------------------------------------------------------------------------------------


def test_texts_bodies_and_exception_text_never_reach_errors_output_or_logs(
    capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    texts = (f"text {CANARY}",)
    failures: list[BaseException] = []
    for outcome in (
        RuntimeError(f"raw {CANARY}"),
        ok(json.dumps(document(1, model=CANARY)).encode()),
        ok(f'{{"detail": "{CANARY}"'.encode()),
        VoyageResponse(429, b""),
    ):
        with pytest.raises(VoyageError) as raised:
            VoyageEmbedder(FakeTransport(outcome)).embed(texts, "query")
        failures.append(raised.value)
    with pytest.raises(InvalidEmbeddingError) as invalid:
        VoyageEmbedder(FakeTransport()).embed((f"{CANARY}\x00",), "query")
    failures.append(invalid.value)
    for error in failures:
        assert_private(error)
    response = ok(f"body {CANARY}".encode())
    assert CANARY not in repr(response) and CANARY not in str(response)
    assert repr(VoyageEmbedder(FakeTransport())) == "VoyageEmbedder()"
    output = capsys.readouterr()
    assert CANARY not in output.out + output.err
    assert all(CANARY not in record.getMessage() for record in caplog.records)
    assert not caplog.records


# --- M4c indexing integration (doubles; no database) ---------------------------------------------

T0 = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
TENANT = UUID("77777777-7777-4777-8777-777777777777")
REVISION = UUID("33333333-3333-4333-8333-333333333333")
VERSION = "text-md-v1"
PROFILE = profile_id(TENANT, FINGERPRINT)
INDEX = index_id(TENANT, REVISION, VERSION, PROFILE)


def _chunk(ordinal: int) -> PendingChunk:
    body = f"Chunk {ordinal} retention backups"
    return PendingChunk(
        ordinal=ordinal,
        id=UUID(int=2000 + ordinal),
        text=body,
        content_sha256=hashlib.sha256(body.encode()).hexdigest(),
    )


@dataclass
class Script:
    chunks: list[PendingChunk] = field(default_factory=lambda: [_chunk(0), _chunk(1)])
    written: list[Any] = field(default_factory=list)
    latched: bool = False
    latch: Callable[[], BaseException] = JobCancelledError
    in_fence: bool = False
    finishes: int = 0
    ready_marks: int = 0


class FakeContext:
    def __init__(self, script: Script) -> None:
        self._script = script
        self.job = JobSnapshot(
            id=UUID(int=9),
            tenant_id=TENANT,
            kind="index_revision",
            idempotency_key=str(INDEX),
            payload=JobPayload.from_mapping({"index_id": str(INDEX)}),
            status=JobStatus.RUNNING,
            attempt=1,
            max_attempts=3,
            run_after=T0,
            locked_by="worker-test",
            lease_expires_at=T0 + timedelta(seconds=60),
            created_at=T0,
            updated_at=T0,
        )

    def check(self) -> None:
        if self._script.latched:  # like JobContext: a latched state raises on every check
            raise self._script.latch()

    @contextmanager
    def fenced(self, *, finish: bool = False) -> Iterator[HandlerFence]:
        self.check()
        if finish:
            self._script.finishes += 1
        self._script.in_fence = True
        try:
            yield HandlerFence(cast(FencedSession, object()), self.job)
        finally:
            self._script.in_fence = False


@pytest.fixture
def script(monkeypatch: pytest.MonkeyPatch) -> Script:
    state = Script()
    index = IndexSnapshot(
        id=INDEX,
        tenant_id=TENANT,
        revision_id=REVISION,
        chunker_version=VERSION,
        chunk_count=2,
        manifest_sha256="a" * 64,
        profile_id=PROFILE,
        dims=1024,
        allows_zero_vectors=False,
        status="building",
        vector_manifest_sha256=None,
        ready_at=None,
    )
    profile = ProfileSnapshot(
        id=PROFILE,
        tenant_id=TENANT,
        provider_id="voyage",
        model_id="voyage-4-lite",
        algorithm_version="voyage-http-v1",
        dims=1024,
        normalization="l2",
        fingerprint=FINGERPRINT,
        allows_zero_vectors=False,
    )

    def pending(session: Any, job: Any, index_: Any, *, after_ordinal: int) -> Any:
        done = {row.chunk_id for batch in state.written for row in batch}
        return tuple(c for c in state.chunks if c.ordinal > after_ordinal and c.id not in done)

    def write(session: Any, job: Any, identity: Any, rows: Any) -> None:
        assert identity == VOYAGE_IDENTITY
        state.written.append(tuple(rows))

    monkeypatch.setattr(index_store, "load_index_target", lambda s, j: (index, profile))
    monkeypatch.setattr(index_store, "pending_chunks", pending)
    monkeypatch.setattr(embedding_store, "write_embeddings", write)

    def mark_ready(session: Any, job: Any, identity: Any) -> Any:
        state.ready_marks += 1
        return index

    monkeypatch.setattr(embedding_store, "mark_index_ready", mark_ready)
    return state


def _index_with(script: Script, transport: Any) -> None:
    handler = indexing.make_index_revision_handler({FINGERPRINT: lambda: VoyageEmbedder(transport)})
    handler(cast(JobContext, FakeContext(script)))


def test_the_m4c_handler_indexes_canonical_rows_through_a_mocked_voyage_provider(
    script: Script,
) -> None:
    transport = FakeTransport(factory=echo)
    _index_with(script, transport)
    assert len(transport.bodies) == 1
    (rows,) = script.written
    texts = tuple(chunk.text for chunk in script.chunks)
    expected = stored_embeddings(  # the same float values, canonicalized under the offline identity
        HashingEmbedder().embed(texts, "document"),
        identity=HASH_IDENTITY,
        chunks=[(c.id, c.content_sha256) for c in script.chunks],
    )
    assert [row.vector.sha256 for row in rows] == [row.vector.sha256 for row in expected]
    assert all(not row.vector.is_zero for row in rows)


@pytest.mark.parametrize(
    "outcome",
    [
        VoyageError(C.RATE_LIMITED),
        VoyageError(C.TIMEOUT),
        VoyageResponse(503, b""),
        VoyageResponse(401, b""),
        ok(b"not json"),
        RuntimeError(CANARY),
    ],
    ids=["rate-limited", "timeout", "server", "auth", "malformed", "raw"],
)
def test_every_voyage_failure_is_a_permanent_m4c_failure_today(
    script: Script, outcome: Any
) -> None:
    """The disclosed retryability gap (V11): even retryable codes end ``permanent_failure``."""
    with pytest.raises(PermanentJobError) as raised:
        _index_with(script, FakeTransport(outcome))
    assert raised.value.code is JobErrorCode.PERMANENT_FAILURE
    assert raised.value.__cause__ is None and raised.value.__context__ is None
    assert script.written == []


def test_a_cancellation_latched_during_the_call_wins_over_classification(script: Script) -> None:
    def cancelled_during(body: bytes) -> Any:
        script.latched = True
        raise VoyageError(C.RATE_LIMITED)

    with pytest.raises(JobCancelledError):
        _index_with(script, FakeTransport(factory=cancelled_during))
    assert script.written == [] and script.finishes == 0 and script.ready_marks == 0


def test_the_successful_path_finishes_once_with_readiness(script: Script) -> None:
    _index_with(script, FakeTransport(factory=echo))
    assert script.finishes == 1 and script.ready_marks == 1


@pytest.mark.parametrize(
    "failure",
    [VoyageError(C.RATE_LIMITED), VoyageError(C.TIMEOUT), RuntimeError(CANARY)],
    ids=["voyage-rate-limited", "voyage-timeout", "ordinary"],
)
def test_lease_loss_during_the_call_wins_over_permanent_classification(
    script: Script, failure: Exception
) -> None:
    """Prompt 159 C: lease loss becomes observable during the mocked Voyage call, which then
    fails; the handler's ``ctx.check()`` before classification raises ``LeaseLostError``
    instead of ``PermanentJobError``, and nothing is written or finished."""

    def lease_lost_during(body: bytes) -> Any:
        script.latch = LeaseLostError
        script.latched = True
        raise failure

    transport = FakeTransport(factory=lease_lost_during)
    with pytest.raises(LeaseLostError) as raised:
        _index_with(script, transport)
    assert type(raised.value) is LeaseLostError and len(transport.bodies) == 1
    assert script.written == [] and script.finishes == 0 and script.ready_marks == 0


# --- M4d retrieval integration (doubles; no database) --------------------------------------------

VENDOR = uuid4()
REVIEWER = ActorContext(tenant_id=TENANT, actor_id=uuid4(), role=Role.REVIEWER)


def _voyage_snapshot() -> RetrievalSnapshot:
    binding = RevisionBinding(REVISION, uuid4(), INDEX, VERSION, 1, "a" * 64, "b" * 64)
    return RetrievalSnapshot(
        TENANT,
        VENDOR,
        VOYAGE_IDENTITY,
        RETRIEVAL_CONFIG_V1,
        (binding,),
        PendingExclusions(0, (), False),
        T0,
    )


def _refusing_factory() -> Any:
    raise AssertionError("no session may open for a provider failure")


def test_search_snapshot_embeds_queries_through_a_mocked_voyage_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[EmbeddingBatch] = []
    sentinel = object()

    def retrieve(factory: Any, actor: Any, snapshot: Any, request: Any, batch: Any) -> Any:
        seen.append(batch)
        return sentinel

    monkeypatch.setattr(orchestration, "retrieve_with_vectors", retrieve)
    transport = FakeTransport(factory=echo)
    request = RetrievalRequest(("retention period", "backups"))
    result = orchestration.search_snapshot(
        _refusing_factory,  # type: ignore[arg-type]
        REVIEWER,
        _voyage_snapshot(),
        request,
        VoyageEmbedder(transport),
    )
    assert result is sentinel and len(transport.bodies) == 1
    assert json.loads(transport.bodies[0])["input_type"] == "query"
    (batch,) = seen
    assert batch.identity == VOYAGE_IDENTITY and len(batch.vectors) == 2


@pytest.mark.parametrize(
    "outcome",
    [VoyageError(C.TIMEOUT), VoyageResponse(429, b""), ok(b"[]"), RuntimeError(CANARY)],
)
def test_every_voyage_failure_is_a_fixed_retrieval_provider_error(outcome: Any) -> None:
    with pytest.raises(RetrievalProviderError) as raised:
        orchestration.search_snapshot(
            _refusing_factory,  # type: ignore[arg-type]
            REVIEWER,
            _voyage_snapshot(),
            RetrievalRequest(("retention",)),
            VoyageEmbedder(FakeTransport(outcome)),
        )
    assert_private(raised.value)


@pytest.mark.parametrize("control", [KeyboardInterrupt, SystemExit])
def test_process_control_through_search_snapshot_propagates(control: type[BaseException]) -> None:
    signal = control()
    with pytest.raises(control) as raised:
        orchestration.search_snapshot(
            _refusing_factory,  # type: ignore[arg-type]
            REVIEWER,
            _voyage_snapshot(),
            RetrievalRequest(("retention",)),
            VoyageEmbedder(FakeTransport(signal)),
        )
    assert raised.value is signal
