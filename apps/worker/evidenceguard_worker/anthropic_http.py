"""Standard-library HTTPS transport for the Anthropic adapter (M5h, ADR-0026).

``HttpsAnthropicTransport`` is constructed explicitly by trusted code with a ``SecretStr`` key;
nothing registers it, and it reads no environment variable, setting or file. One ``post`` is one
HTTPS exchange with ``api.anthropic.com`` (verified TLS with a TLS 1.2 minimum, no redirect,
proxy, cookie, decompression, retry or implicit reconnect; ``http.client`` debugging is never
enabled). It mirrors the accepted M4f transport except where the M5h contract says otherwise:

0. argument checks, before any clock reading or network activity;
1. one start reading of the cooperative budget ``timeout_ms / 1000``;
2. connection and TLS, then ``auto_open`` is switched off;
3. request sending, with the socket required;
4. response headers, with the socket required;
5. the status, validated **before** the post-header elapsed check (clarification B);
6. for 200: the post-header check, strict framing, bounded reads and a final check, each failure
   replacing the status; for any other status the status is **kept**: any ordinary failure in the
   post-header check, framing or bounded reads (cap ``MAX_ERROR_BODY_BYTES``), including a clock
   failure, yields a freshly built status-only ``AnthropicResponse(status, b"")``.

- **Clock.** Every reading must be an exact ``int`` or finite ``float`` within +/-2**53, never
  earlier than the previous reading of the same call. Otherwise, before a valid status and on the
  200 path, ``anthropic_clock_failed``.
- **Cooperative timing, not a hard deadline.** A blocked standard-library call is not
  interrupted; DNS, several connection attempts, TLS, header parsing and internal read loops can
  overrun the budget, and cleanup has no deadline. No hard wall-clock maximum is established.
- **Cleanup and errors.** The response and the connection are closed separately, each at most
  once. The first process-control exception that escapes into this code is re-raised as the same
  object after both closes were attempted. Ordinary failures are classified by their own type
  (``TimeoutError`` -> ``anthropic_timeout``, anything else -> ``anthropic_transport_failed``),
  never by their chain, and become fresh fixed ``AnthropicError``s raised outside every handler.
  An ordinary cleanup failure never changes the outcome. A process-control exception that
  ``http.client`` has already replaced internally cannot be recovered. Nothing here claims
  physical disposal of the socket.

The key, headers, texts and bodies never appear in a public error, representation or log;
trusted code inspecting frame locals or the held key is out of scope.
"""

import http.client
import math
import ssl
import time
from collections.abc import Callable
from typing import Any

from pydantic import SecretStr

from evidenceguard_agents.anthropic import (
    ANTHROPIC_API_VERSION,
    ANTHROPIC_HOST,
    ANTHROPIC_PATH,
    MAX_ERROR_BODY_BYTES,
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
    AnthropicError,
    AnthropicErrorCode,
    AnthropicResponse,
)
from evidenceguard_domain.model_calls import (
    CLOCK_READING_BOUND,
    MAX_TIMEOUT_MS,
    MIN_TIMEOUT_MS,
)

PIECE = 64 * 1024
MAX_CONNECT_SECONDS = 120
MAX_KEY_LENGTH = 256
USER_AGENT = "evidenceguard-anthropic-http-v1"
_DIGITS = frozenset("0123456789")

ConnectionFactory = Callable[[str, float, ssl.SSLContext], http.client.HTTPSConnection]
Clock = Callable[[], float]


def _https_connection(
    host: str, timeout: float, context: ssl.SSLContext
) -> http.client.HTTPSConnection:
    """The default factory: an unconnected connection to ``host`` on port 443."""
    return http.client.HTTPSConnection(host, 443, timeout=timeout, context=context)


def _tls_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


class _Refusal(Exception):
    """Internal control flow carrying a fixed code; never escapes this module."""

    def __init__(self, code: AnthropicErrorCode) -> None:
        super().__init__(code.value)
        self.code = code


def _refuse_unless(condition: bool, code: AnthropicErrorCode) -> None:
    if not condition:
        raise _Refusal(code)


def _seconds(value: object) -> bool:
    if type(value) is int:
        return 0 < value <= MAX_CONNECT_SECONDS
    return type(value) is float and math.isfinite(value) and 0 < value <= MAX_CONNECT_SECONDS


def _key(value: object) -> bool:
    if type(value) is not SecretStr:
        return False
    secret = value.get_secret_value()
    return (
        type(secret) is str
        and 1 <= len(secret) <= MAX_KEY_LENGTH
        and all(0x21 <= ord(character) <= 0x7E for character in secret)
    )


def _usable(value: object) -> bool:
    if type(value) is int:
        return -CLOCK_READING_BOUND <= value <= CLOCK_READING_BOUND
    return (
        type(value) is float
        and math.isfinite(value)
        and -CLOCK_READING_BOUND <= value <= CLOCK_READING_BOUND
    )


def _classify(error: Exception) -> AnthropicErrorCode:
    """By the exception's own type only; its cause and context are never inspected."""
    if isinstance(error, _Refusal):  # this module's own fixed refusals
        return error.code
    if isinstance(error, TimeoutError):  # includes socket.timeout
        return AnthropicErrorCode.TIMEOUT
    return AnthropicErrorCode.TRANSPORT_FAILED


class HttpsAnthropicTransport:
    """An ``AnthropicTransport`` over ``http.client`` (see the module docstring)."""

    def __init__(
        self,
        api_key: SecretStr,
        *,
        connect_timeout: float = 10.0,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
        connection_factory: ConnectionFactory = _https_connection,
        clock: Clock = time.monotonic,
        **unknown: object,
    ) -> None:
        valid = False
        try:
            valid = (
                not unknown
                and _key(api_key)
                and _seconds(connect_timeout)
                and type(max_response_bytes) is int
                and 1 <= max_response_bytes <= MAX_RESPONSE_BYTES
                and callable(connection_factory)
                and callable(clock)
            )
        except Exception:  # e.g. a raising secret accessor: a fixed configuration error below
            valid = False
        if not valid:
            raise AnthropicError(AnthropicErrorCode.CONFIGURATION)
        context: ssl.SSLContext | None = None
        try:
            context = _tls_context()
        except Exception:  # an ordinary TLS-context failure: fresh configuration error below
            context = None
        if context is None:
            raise AnthropicError(AnthropicErrorCode.CONFIGURATION)
        self._api_key = api_key
        self._connect_timeout = connect_timeout
        self._cap = max_response_bytes
        self._factory = connection_factory
        self._clock = clock
        self._context = context

    def __repr__(self) -> str:
        return "HttpsAnthropicTransport()"

    __str__ = __repr__

    def post(self, body: bytes, *, timeout_ms: int, **unknown: object) -> AnthropicResponse:
        """One exchange (see the module docstring); raises a fixed ``AnthropicError`` or
        propagates process control as the same object."""
        valid = (
            not unknown
            and type(body) is bytes
            and 1 <= len(body) <= MAX_REQUEST_BYTES
            and type(timeout_ms) is int
            and MIN_TIMEOUT_MS <= timeout_ms <= MAX_TIMEOUT_MS
        )
        if not valid:
            raise AnthropicError(AnthropicErrorCode.CONFIGURATION)
        exchange = _Exchange(self, timeout_ms / 1000)
        control: BaseException | None = None
        failure: AnthropicErrorCode | None = None
        result: tuple[int, bytes] | None = None
        try:
            result = exchange.run(body)
        except Exception as error:  # an operation failure, classified by its own type
            failure = _classify(error)
        except BaseException as error:  # process control: kept as the same object
            control = error
        for close in (exchange.close_response, exchange.close_connection):
            try:
                close()
            except Exception:  # an ordinary cleanup failure never changes the outcome
                pass
            except BaseException as error:
                if control is None:
                    control = error
        if control is not None:
            raise control
        if failure is not None or result is None:
            raise AnthropicError(failure or AnthropicErrorCode.TRANSPORT_FAILED)
        return AnthropicResponse(result[0], result[1])


class _Exchange:
    """The state of one ``post``: the timed phases and the objects to close."""

    def __init__(self, transport: HttpsAnthropicTransport, budget: float) -> None:
        self._transport = transport
        self._budget = budget
        self._start = 0.0
        self._last: float | None = None
        self.connection: Any = None
        self.response: Any = None

    # --- timing ----------------------------------------------------------------------------------

    def _now(self) -> float:
        """A usable reading not earlier than the previous one, else ``clock_failed``."""
        value: object = None
        failed = False
        try:
            value = self._transport._clock()
        except Exception:  # an ordinarily raising clock; process control propagates
            failed = True
        _refuse_unless(not failed and _usable(value), AnthropicErrorCode.CLOCK_FAILED)
        reading = float(value)  # type: ignore[arg-type]
        _refuse_unless(self._last is None or reading >= self._last, AnthropicErrorCode.CLOCK_FAILED)
        self._last = reading
        return reading

    def _remaining(self) -> float:
        return self._budget - (self._now() - self._start)

    def _before(self) -> float:
        """The remaining budget; a spent budget means the phase is not started."""
        remaining = self._remaining()
        _refuse_unless(remaining > 0, AnthropicErrorCode.TIMEOUT)
        return remaining

    def _after(self) -> None:
        _refuse_unless(self._remaining() > 0, AnthropicErrorCode.TIMEOUT)

    def _socket_timeout(self, timeout: float, *, required: bool) -> None:
        """Set the socket timeout through the public ``connection.sock`` if it exists."""
        sock = self.connection.sock
        if sock is None:
            # Before sending or reading headers a missing socket would let ``http.client``
            # reconnect on its own; refuse instead. After the headers it is expected.
            _refuse_unless(not required, AnthropicErrorCode.TRANSPORT_FAILED)
            return
        sock.settimeout(timeout)

    # --- phases ----------------------------------------------------------------------------------

    def run(self, body: bytes) -> tuple[int, bytes]:
        transport = self._transport
        self._start = self._now()  # 1. start

        remaining = self._before()  # 2. connection and TLS
        self.connection = transport._factory(
            ANTHROPIC_HOST, min(transport._connect_timeout, remaining), transport._context
        )
        self.connection.connect()
        self.connection.auto_open = 0  # no implicit reconnect inside http.client
        self._after()

        remaining = self._before()  # 3. request sending
        self._socket_timeout(remaining, required=True)
        self.connection.request("POST", ANTHROPIC_PATH, body=body, headers=self._headers())
        self._after()

        remaining = self._before()  # 4. response headers
        self._socket_timeout(remaining, required=True)
        self.response = self.connection.getresponse()

        status = self.response.status  # 5. the status, before the post-header check
        _refuse_unless(
            type(status) is int and 100 <= status <= 599, AnthropicErrorCode.MALFORMED_RESPONSE
        )
        if status != 200:
            return status, self._error_body()

        self._after()  # 6. the 200 path: post-header check, framing, reads, final check
        declared = self._framing(transport._cap)
        payload = self._read_body(declared, transport._cap)
        self._after()
        return 200, payload

    def _error_body(self) -> bytes:
        """The error body within ``MAX_ERROR_BODY_BYTES``, or ``b""`` after any ordinary
        failure: a known non-200 status is never replaced (clarification B)."""
        cap = min(self._transport._cap, MAX_ERROR_BODY_BYTES)
        payload = b""
        try:
            self._after()
            declared = self._framing(cap)
            payload = self._read_body(declared, cap)
        except Exception:  # process control propagates; anything else keeps the status
            payload = b""
        return payload

    def _headers(self) -> dict[str, str]:
        secret = self._transport._api_key.get_secret_value()
        return {
            "x-api-key": secret,
            "anthropic-version": ANTHROPIC_API_VERSION,
            "content-type": "application/json",
            "accept": "application/json",
            "accept-encoding": "identity",
            "user-agent": USER_AGENT,
        }

    def _framing(self, cap: int) -> int | None:
        """The declared ``Content-Length``, or ``None`` for chunked framing."""
        malformed = AnthropicErrorCode.MALFORMED_RESPONSE
        headers = self.response.headers
        encodings = list(headers.get_all("Content-Encoding") or ())
        transfer = list(headers.get_all("Transfer-Encoding") or ())
        lengths = list(headers.get_all("Content-Length") or ())
        _refuse_unless(
            not encodings or (len(encodings) == 1 and _token(encodings[0]) == "identity"),
            malformed,
        )
        if transfer:
            _refuse_unless(len(transfer) == 1 and _token(transfer[0]) == "chunked", malformed)
            _refuse_unless(not lengths, malformed)
            return None
        _refuse_unless(len(lengths) == 1, malformed)
        value = str(lengths[0]).strip(" \t")
        _refuse_unless(1 <= len(value) <= 20 and set(value) <= _DIGITS, malformed)
        declared = int(value)
        _refuse_unless(declared <= cap, AnthropicErrorCode.RESPONSE_TOO_LARGE)
        return declared

    def _read_body(self, declared: int | None, cap: int) -> bytes:
        total = 0
        pieces: list[bytes] = []
        while True:
            if declared is not None:
                wanted = min(PIECE, declared - total)
                if wanted == 0:
                    break  # the declared length is reached: no further read
            else:
                wanted = min(PIECE, cap + 1 - total)
            remaining = self._before()
            self._socket_timeout(remaining, required=False)
            piece = self.response.read(wanted)
            self._after()
            _refuse_unless(
                type(piece) is bytes and len(piece) <= wanted, AnthropicErrorCode.TRANSPORT_FAILED
            )
            if piece == b"":
                # Early EOF before the declared length; for chunked framing, the end of body.
                _refuse_unless(declared is None, AnthropicErrorCode.TRANSPORT_FAILED)
                break
            total += len(piece)
            _refuse_unless(total <= cap, AnthropicErrorCode.RESPONSE_TOO_LARGE)
            pieces.append(piece)
        return b"".join(pieces)

    # --- cleanup ---------------------------------------------------------------------------------

    def close_response(self) -> None:
        if self.response is not None:
            self.response.close()

    def close_connection(self) -> None:
        if self.connection is not None:
            self.connection.close()


def _token(value: object) -> str:
    return str(value).strip(" \t").lower()
