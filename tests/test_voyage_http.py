"""The standard-library HTTPS transport (``evidenceguard_worker.voyage_http``, M4f, ADR-0018)
with fake connections, responses, sockets and clocks.

No socket is created: the transport is always built with a fake ``connection_factory`` (the
default factory is only constructed, never connected), and an autouse guard makes any socket
connection or name lookup fail the test. The fakes fail on any attribute they do not define, so
a private-attribute or socket traversal would be visible. Clocks are deterministic sequences:
a fake that "returns late" only shows the cooperative elapsed checks; it does **not** show
that a real blocked socket operation is interrupted, and no such claim is made. Nothing here
validates live Voyage compatibility.
"""

import http.client
import json
import logging
import math
import socket
import ssl
import traceback
from collections.abc import Callable
from typing import Any, cast

import pytest
from pydantic import SecretStr

from evidenceguard_retrieval.voyage import (
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
    VoyageEmbedder,
    VoyageError,
    VoyageErrorCode,
    VoyageResponse,
)
from evidenceguard_worker import voyage_http
from evidenceguard_worker.voyage_http import HttpsVoyageTransport

C = VoyageErrorCode
KEY_TEXT = "test-only-not-a-real-key"
KEY = SecretStr(KEY_TEXT)
CANARY = "synthetic-private-canary-41c9"
BODY = b'{"input":["x"]}'


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: object, **kwargs: object) -> Any:
        raise AssertionError("a test attempted network access")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


# --- fakes ---------------------------------------------------------------------------------------


class Guarded:
    """Records, and fails on, any attribute the fake does not define."""

    def __init__(self) -> None:
        self.forbidden: list[str] = []

    def __getattr__(self, name: str) -> Any:
        if name == "forbidden":
            raise AttributeError(name)
        self.forbidden.append(name)
        raise AssertionError(f"unexpected attribute access: {name}")


class FakeSocket(Guarded):
    def __init__(self) -> None:
        super().__init__()
        self.timeouts: list[float] = []

    def settimeout(self, value: float) -> None:
        self.timeouts.append(value)


class FakeHeaders(Guarded):
    def __init__(self, pairs: list[tuple[str, str]]) -> None:
        super().__init__()
        self.pairs = pairs

    def get_all(self, name: str, failobj: Any = None) -> Any:
        values = [value for key, value in self.pairs if key.lower() == name.lower()]
        return values or failobj


class FakeResponse(Guarded):
    """Serves ``data`` honouring each requested size, or scripted ``pieces`` exactly."""

    def __init__(
        self,
        status: int = 200,
        data: bytes = b"",
        headers: list[tuple[str, str]] | None = None,
        pieces: list[Any] | None = None,
        forbid_read: bool = False,
    ) -> None:
        super().__init__()
        self.status = status
        self.data = data
        self.headers = FakeHeaders(
            headers if headers is not None else [("Content-Length", str(len(data)))]
        )
        self.pieces = pieces
        self.forbid_read = forbid_read
        self.reads: list[int] = []
        self.closed = 0
        self.errors: dict[str, BaseException] = {}
        self.on_read: Callable[[], None] | None = None

    def read(self, amount: int) -> Any:
        self.reads.append(amount)
        if self.forbid_read:
            raise AssertionError("read() must not be called")
        if "read" in self.errors:
            raise self.errors.pop("read")
        if self.on_read is not None:
            self.on_read()
        if self.pieces is not None:
            return self.pieces.pop(0) if self.pieces else b""
        piece, self.data = self.data[:amount], self.data[amount:]
        return piece

    def close(self) -> None:
        self.closed += 1
        if "close" in self.errors:
            raise self.errors.pop("close")


class FakeConnection(Guarded):
    def __init__(self, response: FakeResponse | None = None, *, release: bool = False) -> None:
        super().__init__()
        self.response = response if response is not None else ok_response()
        self.release = release
        self.sock: FakeSocket | None = None
        self.socket_seen: FakeSocket | None = None
        self.calls: list[str] = []
        self.requests: list[tuple[str, str, Any, Any]] = []
        self.errors: dict[str, BaseException] = {}
        self.debug_levels: list[int] = []

    def _maybe_raise(self, name: str) -> None:
        if name in self.errors:
            raise self.errors.pop(name)

    def connect(self) -> None:
        self.calls.append("connect")
        self._maybe_raise("connect")
        self.sock = self.socket_seen = FakeSocket()

    def request(self, method: str, url: str, body: Any = None, headers: Any = None) -> None:
        self.calls.append("request")
        self.requests.append((method, url, body, headers))
        self._maybe_raise("request")

    def getresponse(self) -> FakeResponse:
        self.calls.append("getresponse")
        self._maybe_raise("getresponse")
        if self.release:  # like http.client when the response will close
            self.sock = None
        return self.response

    def close(self) -> None:
        self.calls.append("close")
        self._maybe_raise("close")

    def set_debuglevel(self, level: int) -> None:
        self.debug_levels.append(level)


class Factory:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection
        self.calls: list[tuple[str, float, ssl.SSLContext]] = []

    def __call__(self, host: str, timeout: float, context: ssl.SSLContext) -> FakeConnection:
        self.calls.append((host, timeout, context))
        return self.connection


class SequenceClock:
    """Returns the scripted values in order, then repeats the last; counts calls."""

    def __init__(self, *values: Any) -> None:
        self.values = list(values) or [0.0]
        self.calls = 0

    def __call__(self) -> Any:
        self.calls += 1
        value = self.values.pop(0) if len(self.values) > 1 else self.values[0]
        if isinstance(value, BaseException):
            raise value
        return value


def document_bytes() -> bytes:
    vector = [0.0] * 1024
    vector[0] = 1.0
    return json.dumps(
        {
            "object": "list",
            "data": [{"object": "embedding", "embedding": vector, "index": 0}],
            "model": "voyage-4-lite",
            "usage": {"total_tokens": 1},
        }
    ).encode()


def ok_response(data: bytes = b'{"ok":1}', **kwargs: Any) -> FakeResponse:
    return FakeResponse(200, data, **kwargs)


def transport(
    connection: FakeConnection, clock: Any = None, **options: Any
) -> tuple[HttpsVoyageTransport, Factory]:
    factory = Factory(connection)
    built = HttpsVoyageTransport(
        KEY,
        connection_factory=cast(Any, factory),
        clock=clock or SequenceClock(0.0),
        **options,
    )
    return built, factory


def post_error(connection: FakeConnection, clock: Any = None, **options: Any) -> VoyageError:
    built, _ = transport(connection, clock, **options)
    with pytest.raises(VoyageError) as raised:
        built.post(BODY)
    assert_private(raised.value)
    return raised.value


def assert_private(error: BaseException) -> None:
    rendered = [
        str(error),
        repr(error),
        repr(error.args),
        "".join(traceback.format_exception(error)),
    ]
    for secret in (CANARY, KEY_TEXT):
        assert all(secret not in text for text in rendered)
    assert error.__cause__ is None and error.__context__ is None


# --- request formation and TLS -------------------------------------------------------------------


def test_one_exchange_sends_the_exact_request_and_returns_the_body() -> None:
    connection = FakeConnection(ok_response())
    built, factory = transport(connection)
    result = built.post(BODY)

    assert result == VoyageResponse(200, b'{"ok":1}')
    ((host, timeout, context),) = factory.calls
    assert (host, timeout) == ("api.voyageai.com", 10.0)
    assert context.verify_mode is ssl.CERT_REQUIRED and context.check_hostname
    assert context.minimum_version >= ssl.TLSVersion.TLSv1_2
    assert connection.requests == [
        (
            "POST",
            "/v1/embeddings",
            BODY,
            {
                "Authorization": f"Bearer {KEY_TEXT}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "User-Agent": "evidenceguard-voyage-http-v1",
            },
        )
    ]
    assert connection.calls == ["connect", "request", "getresponse", "close"]
    assert connection.response.closed == 1 and connection.response.reads == [8]
    assert connection.socket_seen is not None and connection.socket_seen.timeouts == [30.0] * 3
    assert connection.debug_levels == [] and connection.forbidden == []


def test_the_default_factory_builds_an_unconnected_https_connection() -> None:
    context = ssl.create_default_context()
    built = voyage_http._https_connection("api.voyageai.com", 5.0, context)
    assert isinstance(built, http.client.HTTPSConnection)
    assert (built.host, built.port, built.timeout, built.sock) == (
        "api.voyageai.com",
        443,
        5.0,
        None,
    )
    assert built.debuglevel == 0


def test_the_adapter_and_transport_together_return_a_validated_batch() -> None:
    connection = FakeConnection(ok_response(document_bytes()))
    built, _ = transport(connection)
    batch = VoyageEmbedder(built).embed(("one",), "document")
    assert batch.vectors[0][0] == 1.0 and batch.usage.input_tokens == 1
    sent = json.loads(connection.requests[0][2])
    assert sent["input"] == ["one"] and sent["model"] == "voyage-4-lite"


@pytest.mark.parametrize("status", [301, 302, 307, 308])
def test_redirects_are_never_followed(status: int) -> None:
    response = FakeResponse(status, headers=[("Location", "https://elsewhere.invalid/")])
    response.forbid_read = True
    connection = FakeConnection(response)
    built, factory = transport(connection)
    assert built.post(BODY) == VoyageResponse(status, b"")
    assert len(factory.calls) == 1 and connection.calls.count("request") == 1
    assert response.reads == []
    with pytest.raises(VoyageError) as raised:
        VoyageEmbedder(transport(FakeConnection(FakeResponse(status, forbid_read=True)))[0]).embed(
            ("one",), "document"
        )
    assert raised.value.code is C.UNEXPECTED_STATUS


# --- phase failures ------------------------------------------------------------------------------


@pytest.mark.parametrize("phase", ["connect", "request", "getresponse", "read"])
@pytest.mark.parametrize(
    ("error", "code"),
    [
        (TimeoutError(CANARY), C.TIMEOUT),
        (TimeoutError(CANARY), C.TIMEOUT),
        (OSError(CANARY), C.TRANSPORT_FAILED),
        (ConnectionResetError(CANARY), C.TRANSPORT_FAILED),
        (ssl.SSLError(CANARY), C.TRANSPORT_FAILED),
        (http.client.HTTPException(CANARY), C.TRANSPORT_FAILED),
        (http.client.IncompleteRead(CANARY.encode()), C.TRANSPORT_FAILED),
        (RuntimeError(CANARY), C.TRANSPORT_FAILED),
        (VoyageError(C.RATE_LIMITED), C.TRANSPORT_FAILED),  # a foreign raise: its own type only
    ],
)
def test_a_failure_in_each_phase_is_classified_by_its_own_type(
    phase: str, error: Exception, code: VoyageErrorCode
) -> None:
    connection = FakeConnection(ok_response())
    if phase == "read":
        connection.response.errors["read"] = error
    else:
        connection.errors[phase] = error
    assert post_error(connection).code is code
    assert connection.calls[-1] == "close"


def test_a_failing_factory_is_a_transport_failure() -> None:
    def factory(host: str, timeout: float, context: ssl.SSLContext) -> Any:
        raise RuntimeError(CANARY)

    built = HttpsVoyageTransport(KEY, connection_factory=factory, clock=SequenceClock(0.0))
    with pytest.raises(VoyageError) as raised:
        built.post(BODY)
    assert raised.value.code is C.TRANSPORT_FAILED
    assert_private(raised.value)


# --- status before body --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (429, C.RATE_LIMITED),
        (401, C.AUTHENTICATION),
        (503, C.SERVER_ERROR),
        (400, C.REQUEST_REJECTED),
    ],
)
@pytest.mark.parametrize(
    "headers",
    [
        [("Content-Length", "10")],
        [("Content-Length", "999999999999")],
        [("Content-Length", "not-a-number")],
        [("Transfer-Encoding", "chunked")],
        [("Content-Encoding", "gzip"), ("Content-Length", "5")],
        [],
    ],
    ids=["plain", "huge", "malformed", "chunked", "gzip", "none"],
)
def test_a_non_200_status_wins_without_any_body_read(
    status: int, code: VoyageErrorCode, headers: list[tuple[str, str]]
) -> None:
    response = FakeResponse(status, f'{{"detail": "{CANARY}"}}'.encode(), headers, forbid_read=True)
    connection = FakeConnection(response)
    built, _ = transport(connection)
    assert built.post(BODY) == VoyageResponse(status, b"")
    assert response.reads == [] and response.closed == 1 and connection.calls[-1] == "close"

    response2 = FakeResponse(status, f"{CANARY}".encode(), headers, forbid_read=True)
    built2, _ = transport(FakeConnection(response2))
    with pytest.raises(VoyageError) as raised:
        VoyageEmbedder(built2).embed(("one",), "document")
    assert raised.value.code is code and response2.reads == []
    assert_private(raised.value)


@pytest.mark.parametrize("status", [0, 99, 600, True, "200", None])
def test_an_invalid_status_from_the_connection_is_malformed(status: Any) -> None:
    response = FakeResponse(200, b"{}")
    response.status = status
    response.forbid_read = True
    assert post_error(FakeConnection(response)).code is C.MALFORMED_RESPONSE
    assert response.reads == []


# --- 200 framing and size ------------------------------------------------------------------------

FRAMING: dict[str, tuple[list[tuple[str, str]], VoyageErrorCode]] = {
    "missing length": ([], C.MALFORMED_RESPONSE),
    "repeated equal length": (
        [("Content-Length", "8"), ("Content-Length", "8")],
        C.MALFORMED_RESPONSE,
    ),
    "empty length": ([("Content-Length", "")], C.MALFORMED_RESPONSE),
    "signed length": ([("Content-Length", "+8")], C.MALFORMED_RESPONSE),
    "negative length": ([("Content-Length", "-8")], C.MALFORMED_RESPONSE),
    "non-digit length": ([("Content-Length", "8a")], C.MALFORMED_RESPONSE),
    "unicode digit": ([("Content-Length", "٨")], C.MALFORMED_RESPONSE),
    "21 digits": ([("Content-Length", "1" * 21)], C.MALFORMED_RESPONSE),
    "chunked with length": (
        [("Transfer-Encoding", "chunked"), ("Content-Length", "8")],
        C.MALFORMED_RESPONSE,
    ),
    "gzip transfer": ([("Transfer-Encoding", "gzip")], C.MALFORMED_RESPONSE),
    "chunked list": ([("Transfer-Encoding", "gzip, chunked")], C.MALFORMED_RESPONSE),
    "two transfer headers": (
        [("Transfer-Encoding", "chunked"), ("Transfer-Encoding", "chunked")],
        C.MALFORMED_RESPONSE,
    ),
    "gzip encoding": (
        [("Content-Encoding", "gzip"), ("Content-Length", "8")],
        C.MALFORMED_RESPONSE,
    ),
    "two encodings": (
        [
            ("Content-Encoding", "identity"),
            ("Content-Encoding", "identity"),
            ("Content-Length", "8"),
        ],
        C.MALFORMED_RESPONSE,
    ),
    "length above cap": ([("Content-Length", str(MAX_RESPONSE_BYTES + 1))], C.RESPONSE_TOO_LARGE),
}


@pytest.mark.parametrize("case", sorted(FRAMING))
def test_invalid_200_framing_is_refused_before_any_read(case: str) -> None:
    headers, code = FRAMING[case]
    response = ok_response(f"{CANARY}...".encode()[:8], headers=headers)
    connection = FakeConnection(response)
    assert post_error(connection).code is code
    assert response.reads == [] and response.closed == 1


@pytest.mark.parametrize(
    "headers",
    [
        [("Content-Length", " 8 ")],
        [("content-length", "8"), ("Content-Encoding", "identity")],
        [("Content-Encoding", "IDENTITY"), ("Content-Length", "8")],
        [("Transfer-Encoding", "Chunked")],
    ],
)
def test_accepted_framing_variants_succeed(headers: list[tuple[str, str]]) -> None:
    built, _ = transport(FakeConnection(ok_response(headers=headers)))
    assert built.post(BODY) == VoyageResponse(200, b'{"ok":1}')


def test_a_chunked_body_over_the_cap_is_too_large_after_cap_plus_one_bytes() -> None:
    response = ok_response(b"x" * 25, headers=[("Transfer-Encoding", "chunked")])
    assert post_error(FakeConnection(response), max_response_bytes=10).code is C.RESPONSE_TOO_LARGE
    assert response.reads == [11]


def test_a_chunked_body_at_the_cap_is_accepted_and_ends_at_the_decoded_eof() -> None:
    response = ok_response(b"y" * 10, headers=[("Transfer-Encoding", "chunked")])
    built, _ = transport(FakeConnection(response), max_response_bytes=10)
    assert built.post(BODY).body == b"y" * 10
    assert response.reads == [11, 1]


def test_a_declared_length_at_the_cap_is_accepted() -> None:
    response = ok_response(b"z" * 10)
    built, _ = transport(FakeConnection(response), max_response_bytes=10)
    assert built.post(BODY).body == b"z" * 10 and response.reads == [10]


# --- short bodies (explicit detection) -----------------------------------------------------------


def test_a_declared_five_with_three_bytes_then_eof_fails_without_incomplete_read() -> None:
    response = ok_response(headers=[("Content-Length", "5")], pieces=[b"abc", b""])
    assert post_error(FakeConnection(response)).code is C.TRANSPORT_FAILED
    assert response.reads == [5, 2]


def test_early_eof_on_the_first_read_fails() -> None:
    response = ok_response(headers=[("Content-Length", "5")], pieces=[b""])
    assert post_error(FakeConnection(response)).code is C.TRANSPORT_FAILED
    assert response.reads == [5]


def test_several_short_reads_supplying_the_exact_length_succeed_with_no_extra_read() -> None:
    response = ok_response(headers=[("Content-Length", "6")], pieces=[b"ab", b"cd", b"ef", b"!!"])
    built, _ = transport(FakeConnection(response))
    assert built.post(BODY).body == b"abcdef"
    assert response.reads == [6, 4, 2]  # nothing after the declared length is reached


def test_each_read_requests_at_most_64_kib_and_the_remaining_length() -> None:
    response = ok_response(b"q" * 70_000)
    built, _ = transport(FakeConnection(response))
    assert len(built.post(BODY).body) == 70_000
    assert response.reads == [65_536, 4_464]


@pytest.mark.parametrize(
    "piece", [b"abcdef", bytearray(b"abc"), memoryview(b"abc"), "abc", None], ids=repr
)
def test_a_read_returning_too_much_or_a_non_bytes_value_fails(piece: Any) -> None:
    response = ok_response(headers=[("Content-Length", "5")], pieces=[piece])
    assert post_error(FakeConnection(response)).code is C.TRANSPORT_FAILED


def test_a_raised_incomplete_read_maps_to_the_same_code() -> None:
    response = ok_response(b"abcde")
    response.errors["read"] = http.client.IncompleteRead(b"ab", 3)
    assert post_error(FakeConnection(response)).code is C.TRANSPORT_FAILED


def test_the_budget_is_checked_before_and_after_every_read() -> None:
    clock = SequenceClock(0.0)
    response = ok_response(headers=[("Content-Length", "6")], pieces=[b"ab", b"cd", b"ef"])
    built, _ = transport(FakeConnection(response), clock)
    built.post(BODY)
    # start; connect before/after; send before/after; headers before/after; 3 reads before/after;
    # the final check before success
    assert clock.calls == 1 + 2 + 2 + 2 + 3 * 2 + 1


# --- socket ownership after the headers ----------------------------------------------------------


@pytest.mark.parametrize(
    ("headers", "pieces"),
    [
        ([("Content-Length", "8"), ("Connection", "close")], [b'{"ok"', b":1}"]),
        ([("Transfer-Encoding", "chunked"), ("Connection", "close")], [b'{"ok"', b":1}", b""]),
    ],
    ids=["content-length", "chunked"],
)
def test_a_released_connection_socket_is_tolerated_without_reconnect_or_traversal(
    headers: list[tuple[str, str]], pieces: list[bytes]
) -> None:
    response = ok_response(headers=headers, pieces=list(pieces))
    connection = FakeConnection(response, release=True)
    built, factory = transport(connection)
    assert built.post(BODY) == VoyageResponse(200, b'{"ok":1}')
    assert connection.sock is None and connection.socket_seen is not None
    assert connection.socket_seen.timeouts == [30.0, 30.0]  # send and headers only
    assert len(factory.calls) == 1 and connection.calls.count("connect") == 1
    assert connection.forbidden == [] and response.forbidden == []


def test_a_late_completion_after_release_is_still_refused() -> None:
    late = {"now": 0.0}
    response = ok_response(headers=[("Content-Length", "8")], pieces=[b'{"ok":1}'])
    response.on_read = lambda: late.update(now=61.0)
    connection = FakeConnection(response, release=True)
    assert post_error(connection, lambda: late["now"]).code is C.TIMEOUT
    assert response.reads == [8] and connection.calls[-1] == "close"


def test_a_missing_socket_before_sending_is_refused_rather_than_reconnected() -> None:
    connection = FakeConnection(ok_response())

    def connect_without_socket() -> None:
        connection.calls.append("connect")

    connection.connect = connect_without_socket  # type: ignore[method-assign]
    assert post_error(connection).code is C.TRANSPORT_FAILED
    assert "request" not in connection.calls


# --- the cooperative budget ----------------------------------------------------------------------

#  clock calls: 1 start, 2 before connect, 3 after connect, 4 before send, 5 after send,
#  6 before headers, 7 after headers, 8 before read, 9 after read, 10 final


@pytest.mark.parametrize(
    ("values", "expected_calls", "reads"),
    [
        ((0.0, 60.0), [], None),
        ((0.0, 0.0, 0.0, 60.0), ["connect", "close"], None),
        ((0.0, 0.0, 0.0, 0.0, 0.0, 60.0), ["connect", "request", "close"], None),
        ((0.0,) * 7 + (60.0,), ["connect", "request", "getresponse", "close"], []),
    ],
    ids=["connection", "sending", "headers", "body"],
)
def test_a_spent_budget_means_the_next_phase_is_never_started(
    values: tuple[float, ...], expected_calls: list[str], reads: list[int] | None
) -> None:
    connection = FakeConnection(ok_response())
    built, factory = transport(connection, SequenceClock(*values))
    with pytest.raises(VoyageError) as raised:
        built.post(BODY)
    assert raised.value.code is C.TIMEOUT
    assert connection.calls == expected_calls
    assert len(factory.calls) == (0 if not expected_calls else 1)
    if reads is not None:
        assert connection.response.reads == reads


@pytest.mark.parametrize(
    ("values", "calls"),
    [
        ((0.0, 0.0, 60.0), ["connect", "close"]),
        ((0.0, 0.0, 0.0, 0.0, 60.0), ["connect", "request", "close"]),
        ((0.0,) * 6 + (60.0,), ["connect", "request", "getresponse", "close"]),
        ((0.0,) * 8 + (60.0,), ["connect", "request", "getresponse", "close"]),
        ((0.0,) * 9 + (60.0,), ["connect", "request", "getresponse", "close"]),
    ],
    ids=["connection", "sending", "headers", "read", "final"],
)
def test_a_phase_returning_after_expiry_never_yields_success(
    values: tuple[float, ...], calls: list[str]
) -> None:
    connection = FakeConnection(ok_response())
    assert post_error(connection, SequenceClock(*values)).code is C.TIMEOUT
    assert connection.calls == calls


def test_a_late_non_200_status_keeps_its_classification() -> None:
    response = FakeResponse(429, forbid_read=True)
    connection = FakeConnection(response)
    built, _ = transport(connection, SequenceClock(*((0.0,) * 6 + (60.0,))))
    assert built.post(BODY) == VoyageResponse(429, b"")
    built2, _ = transport(
        FakeConnection(FakeResponse(429, forbid_read=True)),
        SequenceClock(*((0.0,) * 6 + (60.0,))),
    )
    with pytest.raises(VoyageError) as raised:
        VoyageEmbedder(built2).embed(("one",), "document")
    assert raised.value.code is C.RATE_LIMITED


def test_the_applied_timeouts_are_reduced_by_the_remaining_budget() -> None:
    clock = SequenceClock(0.0, 55.0, 55.0, 58.0, 58.0, 59.0, 59.0, 59.5, 59.5, 59.5)
    connection = FakeConnection(ok_response())
    built, factory = transport(connection, clock)
    built.post(BODY)
    assert factory.calls[0][1] == 5.0  # min(10, 60 - 55)
    assert connection.socket_seen is not None
    assert connection.socket_seen.timeouts == [2.0, 1.0, 0.5]  # send, headers, the read


def test_large_budgets_still_cap_each_wait_at_the_phase_timeout() -> None:
    connection = FakeConnection(ok_response())
    built, factory = transport(connection, connect_timeout=3, io_timeout=4.5, elapsed_budget=600)
    built.post(BODY)
    assert factory.calls[0][1] == 3
    assert connection.socket_seen is not None and connection.socket_seen.timeouts == [4.5] * 3


# --- configuration (C2) --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key",
    [
        KEY_TEXT,
        None,
        SecretStr(""),
        SecretStr("k" * 257),
        SecretStr("has space"),
        SecretStr("cr\r"),
        SecretStr("lf\n"),
        SecretStr("tab\t"),
        SecretStr("café"),
        SecretStr(123),  # type: ignore[arg-type]
    ],
    ids=["plain-str", "none", "empty", "257", "space", "cr", "lf", "tab", "non-ascii", "non-str"],
)
def test_an_invalid_key_is_a_configuration_error(key: Any) -> None:
    with pytest.raises(VoyageError) as raised:
        HttpsVoyageTransport(key)
    assert raised.value.code is C.CONFIGURATION
    assert_private(raised.value)


def test_the_longest_visible_ascii_key_is_accepted() -> None:
    HttpsVoyageTransport(SecretStr("".join(chr(c) for c in range(0x21, 0x7F)) * 2 + "!" * 68))


@pytest.mark.parametrize("name", ["connect_timeout", "io_timeout", "elapsed_budget"])
@pytest.mark.parametrize(
    "value", [True, 0, 0.0, -1, math.nan, math.inf, -math.inf, 601, 600.5, "10", None, 10**400]
)
def test_an_invalid_timeout_or_budget_is_a_configuration_error(name: str, value: Any) -> None:
    with pytest.raises(VoyageError) as raised:
        HttpsVoyageTransport(KEY, **{name: value})
    assert raised.value.code is C.CONFIGURATION


@pytest.mark.parametrize("name", ["connect_timeout", "io_timeout", "elapsed_budget"])
@pytest.mark.parametrize("value", [1, 0.001, 600, 600.0])
def test_timeouts_within_bounds_are_accepted(name: str, value: Any) -> None:
    HttpsVoyageTransport(KEY, **{name: value})


@pytest.mark.parametrize("value", [True, 0, -1, MAX_RESPONSE_BYTES + 1, 1.0, "10", None])
def test_an_invalid_response_cap_is_a_configuration_error(value: Any) -> None:
    with pytest.raises(VoyageError) as raised:
        HttpsVoyageTransport(KEY, max_response_bytes=value)
    assert raised.value.code is C.CONFIGURATION


@pytest.mark.parametrize("value", [1, MAX_RESPONSE_BYTES])
def test_response_caps_within_bounds_are_accepted(value: int) -> None:
    HttpsVoyageTransport(KEY, max_response_bytes=value)


@pytest.mark.parametrize("name", ["connection_factory", "clock"])
def test_a_non_callable_factory_or_clock_is_a_configuration_error(name: str) -> None:
    with pytest.raises(VoyageError) as raised:
        HttpsVoyageTransport(KEY, **cast(Any, {name: "not callable"}))
    assert raised.value.code is C.CONFIGURATION


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, None, "0", True])
def test_an_invalid_clock_result_is_a_configuration_error_before_any_connection(
    value: Any,
) -> None:
    connection = FakeConnection(ok_response())
    built, factory = transport(connection, SequenceClock(value))
    with pytest.raises(VoyageError) as raised:
        built.post(BODY)
    assert raised.value.code is C.CONFIGURATION and factory.calls == []


@pytest.mark.parametrize(
    "body",
    [bytearray(BODY), "text", None, b"x" * (MAX_REQUEST_BYTES + 1)],
    ids=["bytearray", "str", "none", "over-1-mib"],
)
def test_an_invalid_post_body_is_a_configuration_error_with_no_connection(body: Any) -> None:
    connection = FakeConnection(ok_response())
    built, factory = transport(connection)
    with pytest.raises(VoyageError) as raised:
        built.post(body)
    assert raised.value.code is C.CONFIGURATION and factory.calls == []


# --- TLS-context setup (Prompt 159 correction B) -------------------------------------------------


class TlsSetup:
    """A patched ``_tls_context`` that raises ``failure`` and counts its calls."""

    def __init__(self, failure: BaseException) -> None:
        self.failure = failure
        self.calls = 0

    def __call__(self) -> ssl.SSLContext:
        self.calls += 1
        raise self.failure


@pytest.mark.parametrize(
    ("failure", "code"),
    [
        (OSError(CANARY), C.TRANSPORT_FAILED),
        (ssl.SSLError(CANARY), C.TRANSPORT_FAILED),
        (ValueError(CANARY), C.TRANSPORT_FAILED),
        (TimeoutError(CANARY), C.TIMEOUT),
    ],
    ids=["os-error", "ssl-error", "value-error", "timeout"],
)
def test_an_ordinary_tls_setup_failure_is_a_fresh_fixed_error_before_any_connection(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    failure: Exception,
    code: VoyageErrorCode,
) -> None:
    caplog.set_level(logging.DEBUG)
    setup = TlsSetup(failure)
    monkeypatch.setattr(voyage_http, "_tls_context", setup)
    factory = Factory(FakeConnection())
    with pytest.raises(VoyageError) as raised:
        HttpsVoyageTransport(KEY, connection_factory=cast(Any, factory), clock=SequenceClock(0.0))
    assert raised.value.code is code and setup.calls == 1 and factory.calls == []
    assert_private(raised.value)
    output = capsys.readouterr()
    assert CANARY not in output.out + output.err and not caplog.records


def test_a_tls_setup_failure_with_process_control_in_its_chain_stays_ordinary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = OSError(CANARY)
    failure.__context__ = KeyboardInterrupt()
    failure.__cause__ = SystemExit(1)
    monkeypatch.setattr(voyage_http, "_tls_context", TlsSetup(failure))
    with pytest.raises(VoyageError) as raised:
        HttpsVoyageTransport(KEY)
    assert raised.value.code is C.TRANSPORT_FAILED
    assert_private(raised.value)


@pytest.mark.parametrize("control", [KeyboardInterrupt, SystemExit, GeneratorExit])
def test_process_control_from_tls_setup_propagates_as_the_same_object(
    monkeypatch: pytest.MonkeyPatch, control: type[BaseException]
) -> None:
    signal = control()
    monkeypatch.setattr(voyage_http, "_tls_context", TlsSetup(signal))
    factory = Factory(FakeConnection())
    with pytest.raises(control) as raised:
        HttpsVoyageTransport(KEY, connection_factory=cast(Any, factory))
    assert raised.value is signal and factory.calls == []


def test_configuration_validation_precedes_tls_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    setup = TlsSetup(OSError(CANARY))
    monkeypatch.setattr(voyage_http, "_tls_context", setup)
    with pytest.raises(VoyageError) as raised:
        HttpsVoyageTransport(SecretStr(""))
    assert raised.value.code is C.CONFIGURATION and setup.calls == 0


def test_the_real_tls_context_stays_verifying_with_a_tls_1_2_minimum() -> None:
    context = voyage_http._tls_context()
    assert context.verify_mode is ssl.CERT_REQUIRED and context.check_hostname
    assert context.minimum_version >= ssl.TLSVersion.TLSv1_2
    built, factory = transport(FakeConnection())
    built.post(BODY)
    (_, _, used) = factory.calls[0]
    assert used.verify_mode is ssl.CERT_REQUIRED and used.check_hostname


# --- cleanup precedence (D1) ---------------------------------------------------------------------

CONTROLS = [KeyboardInterrupt, SystemExit]


@pytest.mark.parametrize("where", ["response-close", "connection-close", "both"])
@pytest.mark.parametrize(
    ("error", "code"), [(OSError(CANARY), C.TRANSPORT_FAILED), (TimeoutError(CANARY), C.TIMEOUT)]
)
def test_an_operation_failure_keeps_its_code_through_ordinary_cleanup_failures(
    where: str, error: Exception, code: VoyageErrorCode
) -> None:
    connection = FakeConnection(ok_response())
    connection.response.errors["read"] = error
    if where in ("response-close", "both"):
        connection.response.errors["close"] = RuntimeError(CANARY)
    if where in ("connection-close", "both"):
        connection.errors["close"] = RuntimeError(CANARY)
    assert post_error(connection).code is code
    assert connection.response.closed == 1 and connection.calls[-1] == "close"


@pytest.mark.parametrize("control", CONTROLS)
@pytest.mark.parametrize(
    "where",
    ["connect", "request", "getresponse", "read", "clock", "response-close", "connection-close"],
)
def test_process_control_from_each_boundary_propagates_as_the_same_object(
    control: type[BaseException], where: str
) -> None:
    signal = control()
    connection = FakeConnection(ok_response())
    clock: Any = SequenceClock(0.0)
    if where in ("connect", "request", "getresponse"):
        connection.errors[where] = signal
    elif where == "read":
        connection.response.errors["read"] = signal
    elif where == "clock":
        clock = SequenceClock(0.0, 0.0, 0.0, signal)
    elif where == "response-close":
        connection.response.errors["close"] = signal
    else:
        connection.errors["close"] = signal
    built, _ = transport(connection, clock)
    with pytest.raises(control) as raised:
        built.post(BODY)
    assert raised.value is signal
    assert connection.calls[-1] == "close"  # the connection close is still attempted


@pytest.mark.parametrize("control", CONTROLS)
def test_process_control_survives_both_ordinary_cleanup_failures(
    control: type[BaseException],
) -> None:
    signal = control()
    connection = FakeConnection(ok_response())
    connection.errors["getresponse"] = signal
    connection.errors["close"] = RuntimeError(CANARY)
    built, _ = transport(connection)
    with pytest.raises(control) as raised:
        built.post(BODY)
    assert raised.value is signal

    signal2 = control()
    connection2 = FakeConnection(ok_response())
    connection2.response.errors["read"] = signal2
    connection2.response.errors["close"] = RuntimeError(CANARY)
    connection2.errors["close"] = OSError(CANARY)
    built2, _ = transport(connection2)
    with pytest.raises(control) as raised2:
        built2.post(BODY)
    assert raised2.value is signal2


def test_the_first_process_control_object_is_kept_when_cleanup_raises_another() -> None:
    first, second, third = KeyboardInterrupt(), SystemExit(), KeyboardInterrupt()
    connection = FakeConnection(ok_response())
    connection.response.errors["read"] = first
    connection.response.errors["close"] = second
    connection.errors["close"] = third
    built, _ = transport(connection)
    with pytest.raises(KeyboardInterrupt) as raised:
        built.post(BODY)
    assert raised.value is first

    early, late = SystemExit(), KeyboardInterrupt()
    connection2 = FakeConnection(ok_response())
    connection2.response.errors["close"] = early
    connection2.errors["close"] = late
    built2, _ = transport(connection2)
    with pytest.raises(SystemExit) as raised2:
        built2.post(BODY)
    assert raised2.value is early


def test_process_control_from_cleanup_beats_an_ordinary_operation_failure() -> None:
    signal = KeyboardInterrupt()
    connection = FakeConnection(ok_response())
    connection.response.errors["read"] = OSError(CANARY)
    connection.errors["close"] = signal
    built, _ = transport(connection)
    with pytest.raises(KeyboardInterrupt) as raised:
        built.post(BODY)
    assert raised.value is signal


@pytest.mark.parametrize("where", ["response-close", "connection-close", "both"])
def test_a_successful_exchange_ignores_ordinary_cleanup_failures(where: str) -> None:
    connection = FakeConnection(ok_response())
    if where in ("response-close", "both"):
        connection.response.errors["close"] = RuntimeError(CANARY)
    if where in ("connection-close", "both"):
        connection.errors["close"] = OSError(CANARY)
    built, _ = transport(connection)
    assert built.post(BODY) == VoyageResponse(200, b'{"ok":1}')
    assert connection.calls[-1] == "close"  # a response-close failure did not stop it


# --- process-control scope (Prompt 156 C, Prompt 157 clarification) -------------------------------


def _chained(control: BaseException, *, as_cause: bool) -> RuntimeError:
    error = RuntimeError(CANARY)
    if as_cause:
        error.__cause__ = control
    else:
        error.__context__ = control
    return error


@pytest.mark.parametrize("control", CONTROLS)
@pytest.mark.parametrize("as_cause", [True, False])
@pytest.mark.parametrize("where", ["getresponse", "read"])
def test_an_ordinary_operation_exception_with_process_control_in_its_chain_stays_ordinary(
    control: type[BaseException], as_cause: bool, where: str
) -> None:
    connection = FakeConnection(ok_response())
    error = _chained(control(), as_cause=as_cause)
    if where == "read":
        connection.response.errors["read"] = error
    else:
        connection.errors["getresponse"] = error
    assert post_error(connection).code is C.TRANSPORT_FAILED


def test_a_getresponse_failure_from_its_own_internal_cleanup_is_that_operations_failure() -> None:
    """Like ``http.client``: ``begin()`` raised process control and its internal close raised an
    ordinary error, which replaced it. Only the escaping ordinary error is observable."""
    connection = FakeConnection(ok_response())
    masked = RuntimeError(CANARY)
    masked.__context__ = KeyboardInterrupt()
    connection.errors["getresponse"] = masked
    assert post_error(connection).code is C.TRANSPORT_FAILED


@pytest.mark.parametrize("control", CONTROLS)
@pytest.mark.parametrize("where", ["response-close", "connection-close"])
def test_an_ordinary_adapter_cleanup_failure_with_process_control_in_its_chain_is_ignored(
    control: type[BaseException], where: str
) -> None:
    def install(connection: FakeConnection) -> None:
        error = _chained(control(), as_cause=False)
        if where == "response-close":
            connection.response.errors["close"] = error
        else:
            connection.errors["close"] = error

    succeeded = FakeConnection(ok_response())
    install(succeeded)
    built, _ = transport(succeeded)
    assert built.post(BODY) == VoyageResponse(200, b'{"ok":1}')

    failed = FakeConnection(ok_response())
    failed.response.errors["read"] = TimeoutError(CANARY)
    install(failed)
    assert post_error(failed).code is C.TIMEOUT


# --- privacy -------------------------------------------------------------------------------------


def test_keys_texts_bodies_and_exception_text_stay_out_of_errors_output_and_logs(
    capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    errors: list[BaseException] = []
    cases: list[FakeConnection] = []
    for phase in ("connect", "request", "getresponse"):
        connection = FakeConnection(ok_response())
        connection.errors[phase] = RuntimeError(f"{CANARY} {KEY_TEXT}")
        cases.append(connection)
    short = ok_response(headers=[("Content-Length", "50")], pieces=[CANARY.encode(), b""])
    cases.append(FakeConnection(short))
    cases.append(FakeConnection(FakeResponse(401, CANARY.encode(), forbid_read=True)))
    for connection in cases:
        built, _ = transport(connection)
        with pytest.raises(VoyageError) as raised:
            VoyageEmbedder(built).embed((f"text {CANARY}",), "query")
        errors.append(raised.value)
    for error in errors:
        assert_private(error)
    built, _ = transport(FakeConnection())
    assert repr(built) == str(built) == "HttpsVoyageTransport()"
    assert KEY_TEXT not in repr(KEY) and KEY_TEXT not in str(KEY)
    output = capsys.readouterr()
    assert CANARY not in output.out + output.err and KEY_TEXT not in output.out + output.err
    assert not caplog.records
