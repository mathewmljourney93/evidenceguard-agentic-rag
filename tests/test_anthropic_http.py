"""M5h (ADR-0026): the standard-library HTTPS transport over fake connections. No network.

Two kinds of fake are used:

- scripted connections and responses, which control every phase, the clock and cleanup;
- a real ``http.client.HTTPSConnection`` subclass whose socket is an in-memory buffer, so the
  request bytes (including the framing headers ``http.client`` generates) and the response
  parsing go through the real standard-library machinery without any network access.

The key is an obviously fake placeholder. Expected values are written out explicitly.
"""

import functools
import http.client
import io
import math
import ssl
from collections.abc import Callable
from typing import Any, cast

import pytest
from pydantic import SecretStr

import evidenceguard_worker.anthropic_http as anthropic_http
from evidenceguard_agents.anthropic import (
    AnthropicError,
    AnthropicErrorCode,
    AnthropicResponse,
    parse_response,
)
from evidenceguard_agents.providers import ModelCallTimeout
from evidenceguard_worker.anthropic_http import HttpsAnthropicTransport

C = AnthropicErrorCode
KEY = "test-placeholder-key-not-real-0000"
SENTINEL = "sentinel-p228-transport"
BODY = b'{"x":1}'


def assert_fixed(error: BaseException, code: AnthropicErrorCode) -> None:
    assert type(error) is AnthropicError and error.code is code
    assert str(error) == code.value and error.args == (code.value,)
    assert error.__cause__ is None and error.__context__ is None
    for text in (str(error), repr(error)):
        assert KEY not in text and SENTINEL not in text


def fails(code: AnthropicErrorCode, action: Callable[[], object]) -> AnthropicError:
    with pytest.raises(AnthropicError) as info:
        action()
    assert_fixed(info.value, code)
    return info.value


def headers(*pairs: tuple[str, str]) -> http.client.HTTPMessage:
    raw = b"".join(f"{name}: {value}\r\n".encode() for name, value in pairs) + b"\r\n"
    return http.client.parse_headers(io.BytesIO(raw))


# --- scripted fakes ----------------------------------------------------------------------------


class Clock:
    """A deterministic clock: ``step`` seconds per reading, switchable to failure modes."""

    def __init__(self, step: float = 0.0) -> None:
        self.now = 0.0
        self.step = step
        self.mode = "ok"
        self.calls = 0
        self.control: BaseException | None = None
        self.last = 0.0

    def __call__(self) -> object:
        self.calls += 1
        if self.mode == "raise":
            raise RuntimeError(SENTINEL)
        if self.mode == "control":
            assert self.control is not None
            raise self.control
        if self.mode == "bool":
            return True
        if self.mode == "nan":
            return math.nan
        if self.mode == "string":
            return "0.0"
        if self.mode == "backwards":
            return self.last - 1.0
        if self.mode == "huge":
            return 2**60
        value = self.now
        self.last = value
        self.now += self.step
        return value

    def spend(self, seconds: float) -> None:
        self.now += seconds


class Socket:
    def __init__(self) -> None:
        self.timeouts: list[float] = []

    def settimeout(self, value: float) -> None:
        self.timeouts.append(value)


class Response:
    """A scripted ``http.client.HTTPResponse`` stand-in."""

    def __init__(
        self,
        status: object = 200,
        header_pairs: tuple[tuple[str, str], ...] = (),
        reads: tuple[object, ...] = (),
    ) -> None:
        self.status = status
        self.headers = headers(*header_pairs)
        self.reads = list(reads)
        self.requested: list[int] = []
        self.closes = 0
        self.close_error: BaseException | None = None

    def read(self, amount: int) -> object:
        self.requested.append(amount)
        if not self.reads:
            return b""
        item = self.reads.pop(0)
        if isinstance(item, BaseException):
            raise item
        if callable(item):
            return item(amount)
        return item

    def close(self) -> None:
        self.closes += 1
        if self.close_error is not None:
            raise self.close_error


class Connection:
    """A scripted connection. ``hooks`` run inside the named operation."""

    def __init__(self, response: Response | BaseException | None = None) -> None:
        self.response = response if response is not None else Response()
        self.sock: Socket | None = Socket()
        self.auto_open = 1
        self.calls: list[str] = []
        self.requests: list[tuple[str, str, bytes, dict[str, str]]] = []
        self.hooks: dict[str, Callable[[], object]] = {}
        self.errors: dict[str, BaseException] = {}
        self.closes = 0

    def _run(self, name: str) -> None:
        self.calls.append(name)
        if name in self.hooks:
            self.hooks[name]()
        if name in self.errors:
            raise self.errors[name]

    def connect(self) -> None:
        self._run("connect")

    def request(self, method: str, path: str, body: bytes, headers: dict[str, str]) -> None:
        self.requests.append((method, path, body, dict(headers)))
        self._run("request")

    def getresponse(self) -> Response:
        self._run("getresponse")
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response

    def close(self) -> None:
        self.closes += 1
        self._run("close")

    def set_debuglevel(self, level: int) -> None:  # must never be called
        self.calls.append("set_debuglevel")


class Factory:
    def __init__(self, connection: object) -> None:
        self.connection = connection
        self.calls: list[tuple[str, float, ssl.SSLContext]] = []

    def __call__(self, host: str, timeout: float, context: ssl.SSLContext) -> object:
        self.calls.append((host, timeout, context))
        if isinstance(self.connection, BaseException):
            raise self.connection
        return self.connection


def make(
    connection: object, clock: Clock | None = None, **options: Any
) -> tuple[HttpsAnthropicTransport, Factory, Clock]:
    factory = Factory(connection)
    used = clock or Clock()
    transport = HttpsAnthropicTransport(
        SecretStr(KEY), connection_factory=cast(Any, factory), clock=cast(Any, used), **options
    )
    return transport, factory, used


def ok_response(body: bytes = b'{"ok":true}', status: int = 200) -> Response:
    return Response(status, (("Content-Length", str(len(body))),), (body,))


# --- real http.client over an in-memory socket -------------------------------------------------


class BufferSocket:
    def __init__(self, response: bytes) -> None:
        self.sent = bytearray()
        self.response = response
        self.timeouts: list[float] = []
        self.closes = 0

    def sendall(self, data: bytes) -> None:
        self.sent += data

    def makefile(self, mode: str, *args: object, **kwargs: object) -> io.BytesIO:
        assert mode == "rb"
        return io.BytesIO(self.response)

    def settimeout(self, value: float) -> None:
        self.timeouts.append(value)

    def close(self) -> None:
        self.closes += 1


class BufferConnection(http.client.HTTPSConnection):
    """The real ``http.client`` request and response machinery; ``connect`` only attaches an
    in-memory socket (no DNS, TCP or TLS)."""

    def __init__(self, response: bytes, host: str, timeout: float, context: ssl.SSLContext):
        super().__init__(host, 443, timeout=timeout, context=context)
        self.buffer = BufferSocket(response)
        self.connects = 0

    def connect(self) -> None:
        self.connects += 1
        self.sock = cast(Any, self.buffer)


class BufferFactory:
    def __init__(self, response: bytes) -> None:
        self.response = response
        self.connections: list[BufferConnection] = []

    def __call__(self, host: str, timeout: float, context: ssl.SSLContext) -> BufferConnection:
        connection = BufferConnection(self.response, host, timeout, context)
        self.connections.append(connection)
        return connection


def over_buffer(response: bytes, **options: Any) -> tuple[HttpsAnthropicTransport, BufferFactory]:
    factory = BufferFactory(response)
    transport = HttpsAnthropicTransport(
        SecretStr(KEY), connection_factory=cast(Any, factory), clock=cast(Any, Clock()), **options
    )
    return transport, factory


def http_response(status_line: str, header_lines: tuple[str, ...], body: bytes = b"") -> bytes:
    head = "".join(f"{line}\r\n" for line in header_lines)
    return f"HTTP/1.1 {status_line}\r\n{head}\r\n".encode() + body


# --- constructor ---------------------------------------------------------------------------------


def test_a_valid_transport_builds_a_verified_tls_context_and_a_safe_representation() -> None:
    connection = Connection(ok_response())
    transport, factory, _ = make(connection)
    assert repr(transport) == str(transport) == "HttpsAnthropicTransport()"
    assert factory.calls == []  # never called during construction
    transport.post(BODY, timeout_ms=30_000)
    context = factory.calls[0][2]
    assert type(context) is ssl.SSLContext
    assert context.verify_mode is ssl.CERT_REQUIRED and context.check_hostname is True
    assert context.minimum_version is ssl.TLSVersion.TLSv1_2


@pytest.mark.parametrize(
    "key",
    [
        "x",
        "!" * 256,
        "~" * 10,
    ],
)
def test_printable_ascii_keys_of_1_to_256_characters_are_accepted(key: str) -> None:
    HttpsAnthropicTransport(SecretStr(key))


@pytest.mark.parametrize(
    "key",
    [
        KEY,
        SecretStr(""),
        SecretStr("k" * 257),
        SecretStr("has space"),
        SecretStr("café"),
        SecretStr("tab\there"),
        SecretStr("nul\x00"),
        SecretStr("del\x7f"),
        None,
    ],
    ids=["plain-str", "empty", "257", "space", "non-ascii", "tab", "nul", "del", "none"],
)
def test_an_invalid_key_is_a_configuration_error(key: object) -> None:
    fails(C.CONFIGURATION, lambda: HttpsAnthropicTransport(key))  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [1, 0.001, 10.0, 120, 120.0])
def test_connect_timeouts_within_bounds_are_accepted(value: object) -> None:
    HttpsAnthropicTransport(SecretStr(KEY), connect_timeout=value)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "options",
    [
        {"connect_timeout": 0},
        {"connect_timeout": -1.0},
        {"connect_timeout": 120.0001},
        {"connect_timeout": 121},
        {"connect_timeout": True},
        {"connect_timeout": math.nan},
        {"connect_timeout": math.inf},
        {"connect_timeout": "10"},
        {"max_response_bytes": 0},
        {"max_response_bytes": 1_048_577},
        {"max_response_bytes": True},
        {"max_response_bytes": 1.0},
        {"connection_factory": None},
        {"clock": 0.0},
        {"retries": 2},
        {"base_url": "https://example.invalid"},
    ],
)
def test_invalid_options_are_a_configuration_error(options: dict[str, object]) -> None:
    fails(C.CONFIGURATION, lambda: HttpsAnthropicTransport(SecretStr(KEY), **cast(Any, options)))


@pytest.mark.parametrize("value", [1, 1_048_576])
def test_response_caps_at_the_bounds_are_accepted(value: int) -> None:
    HttpsAnthropicTransport(SecretStr(KEY), max_response_bytes=value)


def test_an_ordinary_tls_context_failure_is_a_fresh_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing() -> ssl.SSLContext:
        raise ssl.SSLError(SENTINEL)

    monkeypatch.setattr(ssl, "create_default_context", failing)
    factory = Factory(Connection())
    fails(
        C.CONFIGURATION,
        lambda: HttpsAnthropicTransport(SecretStr(KEY), connection_factory=cast(Any, factory)),
    )
    assert factory.calls == []


def test_process_control_from_the_tls_context_propagates_as_the_same_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    interrupt = KeyboardInterrupt()

    def interrupted() -> ssl.SSLContext:
        raise interrupt

    monkeypatch.setattr(ssl, "create_default_context", interrupted)
    with pytest.raises(KeyboardInterrupt) as info:
        HttpsAnthropicTransport(SecretStr(KEY))
    assert info.value is interrupt


def test_the_default_factory_returns_an_unconnected_connection_to_port_443() -> None:
    context = ssl.create_default_context()
    connection = anthropic_http._https_connection("api.anthropic.com", 5.0, context)
    assert type(connection) is http.client.HTTPSConnection
    assert (connection.host, connection.port, connection.timeout) == ("api.anthropic.com", 443, 5.0)
    assert connection.sock is None


# --- post arguments ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body, options",
    [
        ("{}", {"timeout_ms": 30_000}),
        (bytearray(b"{}"), {"timeout_ms": 30_000}),
        (b"", {"timeout_ms": 30_000}),
        (b"x" * 4_194_305, {"timeout_ms": 30_000}),
        (BODY, {"timeout_ms": True}),
        (BODY, {"timeout_ms": 999}),
        (BODY, {"timeout_ms": 120_001}),
        (BODY, {"timeout_ms": 30_000.0}),
        (BODY, {"timeout_ms": 30_000, "stream": True}),
    ],
    ids=["str", "bytearray", "empty", "over-cap", "bool", "999", "120001", "float", "unknown"],
)
def test_invalid_post_arguments_touch_neither_clock_nor_network(
    body: object, options: dict[str, object]
) -> None:
    transport, factory, clock = make(Connection())
    fails(C.CONFIGURATION, lambda: transport.post(cast(Any, body), **cast(Any, options)))
    assert factory.calls == [] and clock.calls == 0


def test_post_accepts_the_argument_bounds() -> None:
    transport, _, _ = make(Connection(ok_response()))
    assert transport.post(b"x" * 4_194_304, timeout_ms=1_000).status == 200
    transport, _, _ = make(Connection(ok_response()))
    assert transport.post(b"x", timeout_ms=120_000).status == 200


# --- headers and framing through the real http.client ---------------------------------------------


def test_the_exact_request_bytes_including_generated_framing_headers() -> None:
    transport, factory = over_buffer(
        http_response("200 OK", ("Content-Type: application/json", "Content-Length: 2"), b"{}")
    )
    response = transport.post(BODY, timeout_ms=30_000)
    assert (response.status, response.body) == (200, b"{}")
    connection = factory.connections[0]
    assert connection.buffer.sent == (
        b"POST /v1/messages HTTP/1.1\r\n"
        b"Host: api.anthropic.com\r\n"
        b"Content-Length: 7\r\n"
        b"x-api-key: test-placeholder-key-not-real-0000\r\n"
        b"anthropic-version: 2026-10-21\r\n"
        b"content-type: application/json\r\n"
        b"accept: application/json\r\n"
        b"accept-encoding: identity\r\n"
        b"user-agent: evidenceguard-anthropic-http-v1\r\n"
        b"\r\n" + BODY
    )
    assert connection.connects == 1 and connection.auto_open == 0
    assert connection.debuglevel == 0
    assert connection.timeout == 10.0  # min(connect_timeout 10, budget 30)


def test_the_six_application_headers_are_passed_exactly() -> None:
    connection = Connection(ok_response())
    transport, _, _ = make(connection)
    transport.post(BODY, timeout_ms=30_000)
    assert connection.requests == [
        (
            "POST",
            "/v1/messages",
            BODY,
            {
                "x-api-key": KEY,
                "anthropic-version": "2026-10-21",
                "content-type": "application/json",
                "accept": "application/json",
                "accept-encoding": "identity",
                "user-agent": "evidenceguard-anthropic-http-v1",
            },
        )
    ]
    assert "set_debuglevel" not in connection.calls


@pytest.mark.parametrize(
    "header_lines, body, expected",
    [
        (("Content-Length: 2",), b"{}", b"{}"),
        (("Content-Length:  2 ",), b"{}", b"{}"),
        (("Content-Length: 0",), b"", b""),
        (("Content-Encoding: identity", "Content-Length: 2"), b"{}", b"{}"),
        (("Content-Encoding: IDENTITY ", "Content-Length: 2"), b"{}", b"{}"),
        (("Transfer-Encoding: chunked",), b"1\r\n{\r\n1\r\n}\r\n0\r\n\r\n", b"{}"),
        (("Transfer-Encoding: Chunked",), b"2\r\n{}\r\n0\r\n\r\n", b"{}"),
        (("Connection: close", "Content-Length: 2"), b"{}", b"{}"),
    ],
    ids=[
        "length",
        "padded-length",
        "zero",
        "identity",
        "identity-case",
        "chunked",
        "chunked-case",
        "close",
    ],
)
def test_accepted_framing_over_real_http_client(
    header_lines: tuple[str, ...], body: bytes, expected: bytes
) -> None:
    for status_line, status in (("200 OK", 200), ("429 Too Many Requests", 429)):
        transport, _ = over_buffer(http_response(status_line, header_lines, body))
        response = transport.post(BODY, timeout_ms=30_000)
        assert (response.status, response.body) == (status, expected)


FRAMING_DEFECTS: dict[str, tuple[tuple[str, ...], bytes, AnthropicErrorCode]] = {
    "length-absent": (("Content-Type: application/json",), b"{}", C.MALFORMED_RESPONSE),
    "length-duplicate": (("Content-Length: 2", "Content-Length: 2"), b"{}", C.MALFORMED_RESPONSE),
    "length-conflict": (("Content-Length: 2", "Content-Length: 3"), b"{}", C.MALFORMED_RESPONSE),
    "length-plus": (("Content-Length: +2",), b"{}", C.MALFORMED_RESPONSE),
    "length-inner-space": (("Content-Length: 1 1",), b"{}", C.MALFORMED_RESPONSE),
    "length-negative": (("Content-Length: -1",), b"{}", C.MALFORMED_RESPONSE),
    "length-21-digits": (("Content-Length: " + "1" * 21,), b"{}", C.MALFORMED_RESPONSE),
    "length-hex": (("Content-Length: 0x2",), b"{}", C.MALFORMED_RESPONSE),
    "length-and-chunked": (
        ("Content-Length: 2", "Transfer-Encoding: chunked"),
        b"2\r\n{}\r\n0\r\n\r\n",
        C.MALFORMED_RESPONSE,
    ),
    "gzip-chunked": (("Transfer-Encoding: gzip, chunked",), b"{}", C.MALFORMED_RESPONSE),
    "chunked-duplicate": (
        ("Transfer-Encoding: chunked", "Transfer-Encoding: chunked"),
        b"2\r\n{}\r\n0\r\n\r\n",
        C.MALFORMED_RESPONSE,
    ),
    "transfer-identity": (("Transfer-Encoding: identity",), b"{}", C.MALFORMED_RESPONSE),
    "gzip": (("Content-Encoding: gzip", "Content-Length: 2"), b"{}", C.MALFORMED_RESPONSE),
    "identity-duplicate": (
        ("Content-Encoding: identity", "Content-Encoding: identity", "Content-Length: 2"),
        b"{}",
        C.MALFORMED_RESPONSE,
    ),
    "encoding-list": (
        ("Content-Encoding: identity, gzip", "Content-Length: 2"),
        b"{}",
        C.MALFORMED_RESPONSE,
    ),
    "early-eof": (("Content-Length: 10",), b"{}", C.TRANSPORT_FAILED),
    "chunk-truncated": (("Transfer-Encoding: chunked",), b"5\r\n{}", C.TRANSPORT_FAILED),
    "chunk-size-bad": (
        ("Transfer-Encoding: chunked",),
        b"zz\r\n{}\r\n0\r\n\r\n",
        C.TRANSPORT_FAILED,
    ),
}


@pytest.mark.parametrize("name", sorted(FRAMING_DEFECTS))
def test_framing_defects_replace_a_200_and_keep_an_error_status(name: str) -> None:
    header_lines, body, code = FRAMING_DEFECTS[name]
    transport, _ = over_buffer(http_response("200 OK", header_lines, body))
    fails(code, lambda: transport.post(BODY, timeout_ms=30_000))
    for status_line, status in (("429 Too Many Requests", 429), ("504 Gateway Timeout", 504)):
        transport, _ = over_buffer(http_response(status_line, header_lines, body))
        response = transport.post(BODY, timeout_ms=30_000)
        assert type(response) is AnthropicResponse
        assert (response.status, response.body) == (status, b"")


def test_the_response_cap_is_exact_for_declared_and_chunked_bodies() -> None:
    cap = 10
    exact, over = b"x" * cap, b"x" * (cap + 1)
    for body, expected in ((exact, exact), (b"", b"")):
        transport, _ = over_buffer(
            http_response("200 OK", (f"Content-Length: {len(body)}",), body), max_response_bytes=cap
        )
        assert transport.post(BODY, timeout_ms=30_000).body == expected
    transport, _ = over_buffer(
        http_response("200 OK", ("Content-Length: 11",), over), max_response_bytes=cap
    )
    fails(C.RESPONSE_TOO_LARGE, lambda: transport.post(BODY, timeout_ms=30_000))
    chunked_exact = b"a\r\n" + exact + b"\r\n0\r\n\r\n"
    chunked_over = b"b\r\n" + over + b"\r\n0\r\n\r\n"
    transport, _ = over_buffer(
        http_response("200 OK", ("Transfer-Encoding: chunked",), chunked_exact),
        max_response_bytes=cap,
    )
    assert transport.post(BODY, timeout_ms=30_000).body == exact
    transport, _ = over_buffer(
        http_response("200 OK", ("Transfer-Encoding: chunked",), chunked_over),
        max_response_bytes=cap,
    )
    fails(C.RESPONSE_TOO_LARGE, lambda: transport.post(BODY, timeout_ms=30_000))


def test_a_chunked_body_over_the_cap_is_detected_one_byte_past_it() -> None:
    response = Response(200, (("Transfer-Encoding", "chunked"),), (b"x" * 10, b"y"))
    transport, _, _ = make(Connection(response), max_response_bytes=10)
    fails(C.RESPONSE_TOO_LARGE, lambda: transport.post(BODY, timeout_ms=30_000))
    assert response.requested == [11, 1]


def test_reads_never_ask_for_more_than_64_kib_or_the_remaining_length() -> None:
    body = b"x" * 140_000
    response = Response(
        200,
        (("Content-Length", str(len(body))),),
        (body[:65_536], body[65_536:131_072], body[131_072:]),
    )
    transport, _, _ = make(Connection(response))
    assert transport.post(BODY, timeout_ms=30_000).body == body
    assert response.requested == [65_536, 65_536, 8_928]


def test_the_error_body_cap_is_the_inspection_cap() -> None:
    at_cap = b"e" * 65_536
    transport, _ = over_buffer(
        http_response("429 Too Many Requests", ("Content-Length: 65536",), at_cap)
    )
    assert transport.post(BODY, timeout_ms=30_000).body == at_cap
    transport, _ = over_buffer(
        http_response("429 Too Many Requests", ("Content-Length: 65537",), at_cap + b"e")
    )
    assert transport.post(BODY, timeout_ms=30_000).body == b""
    chunked = b"10001\r\n" + at_cap + b"e\r\n0\r\n\r\n"
    transport, _ = over_buffer(
        http_response("429 Too Many Requests", ("Transfer-Encoding: chunked",), chunked)
    )
    assert transport.post(BODY, timeout_ms=30_000).body == b""
    transport, _ = over_buffer(
        http_response("429 Too Many Requests", ("Content-Length: 11",), b"e" * 11),
        max_response_bytes=10,
    )
    assert transport.post(BODY, timeout_ms=30_000).body == b""  # min(cap, inspection cap)


@pytest.mark.parametrize(
    "reads, code",
    [
        (("{}",), C.TRANSPORT_FAILED),
        ((bytearray(b"{}"),), C.TRANSPORT_FAILED),
        ((None,), C.TRANSPORT_FAILED),
        ((b"{}x",), C.TRANSPORT_FAILED),
        ((TimeoutError(SENTINEL),), C.TIMEOUT),
        ((OSError(SENTINEL),), C.TRANSPORT_FAILED),
        ((http.client.IncompleteRead(b"{"),), C.TRANSPORT_FAILED),
    ],
    ids=["str", "bytearray", "none", "oversized-piece", "timeout", "os-error", "incomplete"],
)
def test_read_anomalies_replace_a_200_and_keep_an_error_status(
    reads: tuple[object, ...], code: AnthropicErrorCode
) -> None:
    pairs = (("Content-Length", "2"),)
    transport, _, _ = make(Connection(Response(200, pairs, reads)))
    fails(code, lambda: transport.post(BODY, timeout_ms=30_000))
    for status in (429, 504):
        transport, _, _ = make(Connection(Response(status, pairs, reads)))
        assert transport.post(BODY, timeout_ms=30_000) == AnthropicResponse(status, b"")


def test_a_real_error_response_reaches_the_parser_with_its_status_kept() -> None:
    envelope = b'{"type":"error","error":{"type":"timeout_error","message":"m"}}'
    transport, _ = over_buffer(
        http_response("429 Too Many Requests", (f"Content-Length: {len(envelope)}",), envelope)
    )
    with pytest.raises(ModelCallTimeout):
        parse_response(transport.post(BODY, timeout_ms=30_000))
    ordinary = b'{"type":"error","error":{"type":"rate_limit_error","message":"m"}}'
    transport, _ = over_buffer(
        http_response("429 Too Many Requests", (f"Content-Length: {len(ordinary)}",), ordinary)
    )
    fails(C.RATE_LIMITED, lambda: parse_response(transport.post(BODY, timeout_ms=30_000)))


@pytest.mark.parametrize(
    "header_lines, body",
    [
        (("Content-Length: 70000",), b"e" * 70_000),
        (("Content-Length: 10",), b"e"),
        (("Transfer-Encoding: chunked",), b"5\r\nee"),
        (("Content-Encoding: gzip", "Content-Length: 2"), b"{}"),
    ],
    ids=["oversized", "early-eof", "truncated-chunk", "gzip"],
)
def test_a_real_504_with_a_failing_body_is_still_a_timeout(
    header_lines: tuple[str, ...], body: bytes
) -> None:
    transport, _ = over_buffer(http_response("504 Gateway Timeout", header_lines, body))
    response = transport.post(BODY, timeout_ms=30_000)
    assert type(response) is AnthropicResponse and (response.status, response.body) == (504, b"")
    with pytest.raises(ModelCallTimeout):
        parse_response(response)


def test_a_redirect_is_not_followed() -> None:
    transport, factory = over_buffer(
        http_response("302 Found", ("Location: https://example.invalid/", "Content-Length: 0"))
    )
    response = transport.post(BODY, timeout_ms=30_000)
    assert (response.status, response.body) == (302, b"")
    assert len(factory.connections) == 1 and factory.connections[0].connects == 1
    fails(C.UNEXPECTED_STATUS, lambda: parse_response(response))


def test_a_malformed_status_line_is_transport_failed() -> None:
    transport, _ = over_buffer(b"NOT-HTTP garbage\r\n\r\n")
    fails(C.TRANSPORT_FAILED, lambda: transport.post(BODY, timeout_ms=30_000))


# --- sockets and reconnects ----------------------------------------------------------------------


def test_a_missing_socket_before_sending_is_refused_without_an_implicit_connect() -> None:
    connection = Connection(ok_response())
    connection.sock = None
    transport, _, _ = make(connection)
    fails(C.TRANSPORT_FAILED, lambda: transport.post(BODY, timeout_ms=30_000))
    assert connection.calls == ["connect", "close"] and connection.requests == []
    assert connection.auto_open == 0


def test_a_missing_socket_before_the_headers_is_refused() -> None:
    connection = Connection(ok_response())

    def drop() -> None:
        connection.sock = None

    connection.hooks["request"] = drop
    transport, _, _ = make(connection)
    fails(C.TRANSPORT_FAILED, lambda: transport.post(BODY, timeout_ms=30_000))
    assert "getresponse" not in connection.calls


def test_a_missing_socket_after_the_headers_is_accepted() -> None:
    connection = Connection(ok_response())
    socket = connection.sock

    def drop() -> None:
        connection.sock = None

    connection.hooks["getresponse"] = drop
    transport, _, _ = make(connection)
    assert transport.post(BODY, timeout_ms=30_000).body == b'{"ok":true}'
    assert socket is not None and socket.timeouts == [30.0, 30.0]  # sending and headers only


def test_real_http_client_cannot_reconnect_after_auto_open_is_off() -> None:
    transport, factory = over_buffer(
        http_response("200 OK", ("Connection: close", "Content-Length: 2"), b"{}")
    )
    transport.post(BODY, timeout_ms=30_000)
    connection = factory.connections[0]
    assert connection.auto_open == 0 and connection.sock is None
    with pytest.raises(http.client.NotConnected):
        connection.send(b"again")
    assert connection.connects == 1


# --- timing -------------------------------------------------------------------------------------


def test_each_phase_uses_the_remaining_budget() -> None:
    body = b"x" * 70_000
    response = Response(200, (("Content-Length", str(len(body))),), (body[:65_536], body[65_536:]))
    connection = Connection(response)
    transport, factory, clock = make(connection, Clock(step=1.0), connect_timeout=10.0)
    assert transport.post(BODY, timeout_ms=30_000).body == body
    # Readings: start 0; before connect 1; after 2; before send 3; after 4; before headers 5;
    # post-header 6; before read 7; after 8; before read 9; after 10; final 11.
    assert factory.calls[0][1] == 10.0  # min(10, 29)
    assert connection.sock is not None
    assert connection.sock.timeouts == [27.0, 25.0, 23.0, 21.0]
    assert clock.calls == 12


def test_the_connect_timeout_is_capped_by_the_remaining_budget() -> None:
    transport, factory, _ = make(Connection(ok_response()), connect_timeout=10.0)
    transport.post(BODY, timeout_ms=4_000)
    assert factory.calls[0][1] == 4.0


class Readings:
    """A clock returning fixed readings in order."""

    def __init__(self, *values: float) -> None:
        self.values = list(values)
        self.calls = 0

    def __call__(self) -> float:
        self.calls += 1
        return self.values.pop(0)


def test_a_budget_spent_before_connecting_starts_nothing() -> None:
    factory = Factory(Connection())
    clock = Readings(0.0, 30.0)
    transport = HttpsAnthropicTransport(
        SecretStr(KEY), connection_factory=cast(Any, factory), clock=clock
    )
    fails(C.TIMEOUT, lambda: transport.post(BODY, timeout_ms=30_000))
    assert factory.calls == [] and clock.calls == 2


@pytest.mark.parametrize(
    "phase, expected_calls",
    [
        ("connect", ["connect", "close"]),
        ("request", ["connect", "request", "close"]),
    ],
)
def test_a_budget_spent_in_a_phase_stops_the_next_one(
    phase: str, expected_calls: list[str]
) -> None:
    connection = Connection(ok_response())
    clock = Clock()
    connection.hooks[phase] = lambda: clock.spend(30.0)
    transport, _, _ = make(connection, clock)
    fails(C.TIMEOUT, lambda: transport.post(BODY, timeout_ms=30_000))
    assert connection.calls == expected_calls


def test_a_budget_spent_during_the_headers_replaces_a_200_and_keeps_an_error_status() -> None:
    for status, outcome in (
        (200, None),
        (429, AnthropicResponse(429, b"")),
        (504, AnthropicResponse(504, b"")),
    ):
        response = ok_response(status=status)
        connection = Connection(response)
        clock = Clock()
        connection.hooks["getresponse"] = functools.partial(clock.spend, 30.0)
        transport, _, _ = make(connection, clock)
        if outcome is None:
            fails(C.TIMEOUT, functools.partial(transport.post, BODY, timeout_ms=30_000))
        else:
            assert transport.post(BODY, timeout_ms=30_000) == outcome
        assert response.requested == []  # nothing is read once the budget is spent


def test_a_budget_spent_between_reads_replaces_a_200_and_keeps_an_error_status() -> None:
    for status in (200, 429):
        clock = Clock()

        def piece(amount: int, clock: Clock = clock) -> bytes:
            clock.spend(30.0)
            return b"{"

        response = Response(status, (("Content-Length", "2"),), (piece, b"}"))
        transport, _, _ = make(Connection(response), clock)
        if status == 200:
            fails(C.TIMEOUT, functools.partial(transport.post, BODY, timeout_ms=30_000))
        else:
            assert transport.post(BODY, timeout_ms=30_000) == AnthropicResponse(429, b"")
        assert response.requested == [2]


def test_a_budget_spent_on_the_last_read_fails_the_final_check() -> None:
    clock = Clock()

    def last(amount: int) -> bytes:
        clock.spend(30.0)
        return b"{}"

    transport, _, _ = make(Connection(Response(200, (("Content-Length", "2"),), (last,))), clock)
    fails(C.TIMEOUT, lambda: transport.post(BODY, timeout_ms=30_000))


@pytest.mark.parametrize("phase", ["connect", "request", "getresponse"])
def test_a_timeout_error_before_the_status_is_a_timeout(phase: str) -> None:
    connection = Connection(ok_response())
    connection.errors[phase] = TimeoutError(SENTINEL)
    transport, _, _ = make(connection)
    fails(C.TIMEOUT, lambda: transport.post(BODY, timeout_ms=30_000))


@pytest.mark.parametrize("phase", ["connect", "request", "getresponse"])
@pytest.mark.parametrize(
    "error",
    [
        OSError(SENTINEL),
        ssl.SSLError(SENTINEL),
        http.client.BadStatusLine(SENTINEL),
        RuntimeError(SENTINEL),
    ],
)
def test_an_ordinary_failure_before_the_status_is_transport_failed(
    phase: str, error: Exception
) -> None:
    connection = Connection(ok_response())
    connection.errors[phase] = error
    transport, _, _ = make(connection)
    fails(C.TRANSPORT_FAILED, lambda: transport.post(BODY, timeout_ms=30_000))


@pytest.mark.parametrize("status", [True, 99, 600, "200", None, 200.0])
def test_an_invalid_status_value_is_malformed(status: object) -> None:
    transport, _, _ = make(Connection(Response(status)))
    fails(C.MALFORMED_RESPONSE, lambda: transport.post(BODY, timeout_ms=30_000))


# --- clock failures by phase (clarification B) ---------------------------------------------------

CLOCK_MODES = ["bool", "nan", "string", "huge", "backwards", "raise"]


@pytest.mark.parametrize("mode", [mode for mode in CLOCK_MODES if mode != "backwards"])
def test_an_unusable_first_reading_is_clock_failed_before_any_network(mode: str) -> None:
    clock = Clock()
    clock.mode = mode
    transport, factory, _ = make(Connection(), clock)
    fails(C.CLOCK_FAILED, lambda: transport.post(BODY, timeout_ms=30_000))
    assert factory.calls == []


def test_a_backwards_second_reading_is_clock_failed_before_any_network() -> None:
    factory = Factory(Connection())
    clock = Readings(5.0, 4.0)
    transport = HttpsAnthropicTransport(
        SecretStr(KEY), connection_factory=cast(Any, factory), clock=clock
    )
    fails(C.CLOCK_FAILED, lambda: transport.post(BODY, timeout_ms=30_000))
    assert factory.calls == []


@pytest.mark.parametrize("mode", CLOCK_MODES)
@pytest.mark.parametrize("phase", ["connect", "request"])
def test_a_clock_failure_before_a_valid_status_is_clock_failed(mode: str, phase: str) -> None:
    connection = Connection(ok_response())
    clock = Clock()
    connection.hooks[phase] = lambda: setattr(clock, "mode", mode)
    transport, _, _ = make(connection, clock)
    fails(C.CLOCK_FAILED, lambda: transport.post(BODY, timeout_ms=30_000))


@pytest.mark.parametrize("mode", CLOCK_MODES)
def test_a_clock_failure_after_a_200_status_is_clock_failed(mode: str) -> None:
    response = ok_response()
    connection = Connection(response)
    clock = Clock()
    connection.hooks["getresponse"] = lambda: setattr(clock, "mode", mode)
    transport, _, _ = make(connection, clock)
    fails(C.CLOCK_FAILED, lambda: transport.post(BODY, timeout_ms=30_000))
    assert response.requested == [] and response.closes == 1 and connection.closes == 1


@pytest.mark.parametrize("mode", CLOCK_MODES)
def test_a_clock_failure_during_a_200_read_is_clock_failed(mode: str) -> None:
    clock = Clock()

    def piece(amount: int) -> bytes:
        clock.mode = mode
        return b"{"

    transport, _, _ = make(
        Connection(Response(200, (("Content-Length", "2"),), (piece, b"}"))), clock
    )
    fails(C.CLOCK_FAILED, lambda: transport.post(BODY, timeout_ms=30_000))


@pytest.mark.parametrize("mode", CLOCK_MODES)
@pytest.mark.parametrize(
    "status, check",
    [
        (429, lambda: AnthropicErrorCode.RATE_LIMITED),
        (504, lambda: None),
    ],
    ids=["429", "504"],
)
def test_a_clock_failure_after_an_error_status_keeps_the_status(
    mode: str, status: int, check: Callable[[], AnthropicErrorCode | None]
) -> None:
    for where in ("getresponse", "read"):
        clock = Clock()

        def failing_read(amount: int, clock: Clock = clock) -> bytes:
            clock.mode = mode  # the clock fails from the first error-body read onwards
            return b"{"

        connection_response = Response(status, (("Content-Length", "2"),), (failing_read, b"}"))
        connection = Connection(connection_response)
        if where == "getresponse":
            connection.hooks["getresponse"] = functools.partial(setattr, clock, "mode", mode)
        transport, _, _ = make(connection, clock)
        response = transport.post(BODY, timeout_ms=30_000)
        assert type(response) is AnthropicResponse and response == AnthropicResponse(status, b"")
        expected = check()
        if expected is None:
            with pytest.raises(ModelCallTimeout):
                parse_response(response)
        else:
            fails(expected, functools.partial(parse_response, response))


def test_process_control_from_the_clock_propagates_in_every_phase() -> None:
    for where in ("start", "getresponse-429", "getresponse-200"):
        interrupt = KeyboardInterrupt()
        clock = Clock()
        status = 429 if where.endswith("429") else 200
        response = ok_response(status=status)
        connection = Connection(response)
        if where == "start":
            clock.mode, clock.control = "control", interrupt
        else:

            def arm(clock: Clock = clock, interrupt: KeyboardInterrupt = interrupt) -> None:
                clock.mode, clock.control = "control", interrupt

            connection.hooks["getresponse"] = arm
        transport, _, _ = make(connection, clock)
        with pytest.raises(KeyboardInterrupt) as info:
            transport.post(BODY, timeout_ms=30_000)
        assert info.value is interrupt


# --- cleanup ------------------------------------------------------------------------------------


def test_a_factory_failure_closes_nothing() -> None:
    transport, factory, _ = make(OSError(SENTINEL))
    fails(C.TRANSPORT_FAILED, lambda: transport.post(BODY, timeout_ms=30_000))
    assert len(factory.calls) == 1


@pytest.mark.parametrize(
    "phase, response_closes",
    [("connect", 0), ("request", 0), ("getresponse", 0)],
)
def test_a_phase_failure_closes_the_connection_once(phase: str, response_closes: int) -> None:
    response = ok_response()
    connection = Connection(response)
    connection.errors[phase] = OSError(SENTINEL)
    transport, _, _ = make(connection)
    fails(C.TRANSPORT_FAILED, lambda: transport.post(BODY, timeout_ms=30_000))
    assert connection.closes == 1 and response.closes == response_closes


@pytest.mark.parametrize(
    "response, code",
    [
        (Response("bad"), C.MALFORMED_RESPONSE),
        (Response(200, (("Content-Encoding", "gzip"),)), C.MALFORMED_RESPONSE),
        (Response(200, (("Content-Length", "2"),), (OSError(SENTINEL),)), C.TRANSPORT_FAILED),
    ],
    ids=["status", "framing", "read"],
)
def test_a_failure_after_the_headers_closes_both_once(
    response: Response, code: AnthropicErrorCode
) -> None:
    connection = Connection(response)
    transport, _, _ = make(connection)
    fails(code, lambda: transport.post(BODY, timeout_ms=30_000))
    assert response.closes == 1 and connection.closes == 1


def test_success_and_an_error_response_close_both_once() -> None:
    for status in (200, 429):
        response = ok_response(status=status)
        connection = Connection(response)
        transport, _, _ = make(connection)
        assert transport.post(BODY, timeout_ms=30_000).status == status
        assert response.closes == 1 and connection.closes == 1


def test_ordinary_close_failures_never_change_the_outcome() -> None:
    for status in (200, 429):
        response = ok_response(status=status)
        response.close_error = OSError(SENTINEL)
        connection = Connection(response)
        connection.errors["close"] = RuntimeError(SENTINEL)
        transport, _, _ = make(connection)
        assert transport.post(BODY, timeout_ms=30_000) == AnthropicResponse(status, b'{"ok":true}')
        assert response.closes == 1 and connection.closes == 1
    response = Response(200, (("Content-Length", "2"),), (OSError(SENTINEL),))
    response.close_error = OSError(SENTINEL)
    connection = Connection(response)
    connection.errors["close"] = OSError(SENTINEL)
    transport, _, _ = make(connection)
    fails(C.TRANSPORT_FAILED, lambda: transport.post(BODY, timeout_ms=30_000))


def test_process_control_from_a_phase_is_kept_after_both_closes() -> None:
    interrupt = KeyboardInterrupt()
    response = Response(200, (("Content-Length", "2"),), (interrupt,))
    connection = Connection(response)
    transport, _, _ = make(connection)
    with pytest.raises(KeyboardInterrupt) as info:
        transport.post(BODY, timeout_ms=30_000)
    assert info.value is interrupt
    assert response.closes == 1 and connection.closes == 1


def test_process_control_from_the_response_close_is_raised_after_the_connection_close() -> None:
    exit_ = SystemExit(7)
    response = ok_response()
    response.close_error = exit_
    connection = Connection(response)
    transport, _, _ = make(connection)
    with pytest.raises(SystemExit) as info:
        transport.post(BODY, timeout_ms=30_000)
    assert info.value is exit_ and connection.closes == 1


def test_process_control_from_the_connection_close_is_raised() -> None:
    interrupt = KeyboardInterrupt()
    connection = Connection(ok_response())
    connection.errors["close"] = interrupt
    transport, _, _ = make(connection)
    with pytest.raises(KeyboardInterrupt) as info:
        transport.post(BODY, timeout_ms=30_000)
    assert info.value is interrupt


def test_the_first_process_control_object_wins_and_later_ones_are_suppressed() -> None:
    first, second, third = KeyboardInterrupt(), SystemExit(1), KeyboardInterrupt()
    response = Response(200, (("Content-Length", "2"),), (first,))
    response.close_error = second
    connection = Connection(response)
    connection.errors["close"] = third
    transport, _, _ = make(connection)
    with pytest.raises(BaseException) as info:
        transport.post(BODY, timeout_ms=30_000)
    assert info.value is first
    assert response.closes == 1 and connection.closes == 1
    response = ok_response()
    response.close_error = second
    connection = Connection(response)
    connection.errors["close"] = third
    transport, _, _ = make(connection)
    with pytest.raises(BaseException) as info:
        transport.post(BODY, timeout_ms=30_000)
    assert info.value is second and connection.closes == 1


# --- privacy -------------------------------------------------------------------------------------


def test_the_key_never_appears_in_errors_or_representations() -> None:
    for error in (OSError(KEY), RuntimeError(KEY), ssl.SSLError(KEY)):
        connection = Connection(ok_response())
        connection.errors["request"] = error
        transport, _, _ = make(connection)
        raised = fails(
            C.TRANSPORT_FAILED, functools.partial(transport.post, BODY, timeout_ms=30_000)
        )
        assert KEY not in repr(raised.args)
        assert KEY not in repr(transport) and KEY not in str(transport)
