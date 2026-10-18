"""Standard-library HTTPS transport for the Voyage adapter (M4f, ADR-0018).

``HttpsVoyageTransport`` is constructed explicitly by trusted code with a ``SecretStr`` key;
nothing registers it, and it reads no environment variable, setting or file. One ``post`` is
one HTTPS exchange with ``api.voyageai.com`` (verified TLS, no redirect, proxy, cookie,
decompression or retry; ``http.client`` debugging is never enabled):

1. connection and TLS, 2. request sending, 3. response headers, 4. the status, and for 200
   only 5. strict framing checks and bounded body reads, 6. a final elapsed-time check.

- **Status before body.** A non-200 response body is never read or drained: ``post`` returns a
  status-only ``VoyageResponse(status, b"")``.
- **200 framing.** Exactly one digit-only ``Content-Length`` (at most the cap) or a sole
  ``chunked`` ``Transfer-Encoding`` (decoded by ``http.client``); ``Content-Encoding`` absent or
  ``identity``. Reads request at most 64 KiB and never more than the remaining declared length;
  a body shorter than declared is detected explicitly (an empty read), not left to
  ``IncompleteRead``.
- **Cooperative timing, not a hard deadline.** Before each phase the remaining elapsed budget
  is computed (a phase is never started once it is spent) and the socket timeout is set to the
  smaller of the phase timeout and the remaining budget, through the public ``connection.sock``
  only while it exists (``getresponse()`` may release it). Elapsed time is rechecked after each
  phase and before success. A blocked standard-library call is not interrupted; DNS, several
  connection attempts, TLS, header parsing and internal read loops can overrun the budget, and
  cleanup has no deadline. No hard wall-clock maximum is established.
- **Cleanup and errors.** The response and the connection are closed separately. The first
  process-control exception that escapes into this code is re-raised as the same object after
  cleanup. Ordinary failures are classified by their own type (``TimeoutError`` →
  ``voyage_timeout``, anything else → ``voyage_transport_failed``), never by their chain, and
  become fresh fixed ``VoyageError``s raised outside every handler. An ordinary cleanup failure
  never changes the outcome. A process-control exception that ``http.client`` has already
  replaced internally cannot be recovered.

The key, headers, texts and bodies never appear in a public error, default representation or
log; trusted code inspecting frame locals or the held key is out of scope.
"""

import http.client
import math
import ssl
import time
from collections.abc import Callable
from typing import Any

from pydantic import SecretStr

from evidenceguard_retrieval.voyage import (
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
    VOYAGE_HOST,
    VOYAGE_PATH,
    VoyageError,
    VoyageErrorCode,
    VoyageResponse,
)

PIECE = 64 * 1024
MAX_SECONDS = 600
MAX_KEY_LENGTH = 256
USER_AGENT = "evidenceguard-voyage-http-v1"
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

    def __init__(self, code: VoyageErrorCode) -> None:
        super().__init__(code.value)
        self.code = code


def _refuse_unless(condition: bool, code: VoyageErrorCode) -> None:
    if not condition:
        raise _Refusal(code)


def _seconds(value: object) -> bool:
    if type(value) is int:
        return 0 < value <= MAX_SECONDS
    return type(value) is float and math.isfinite(value) and 0 < value <= MAX_SECONDS


def _key(value: object) -> bool:
    if type(value) is not SecretStr:
        return False
    secret = value.get_secret_value()
    return (
        type(secret) is str
        and 1 <= len(secret) <= MAX_KEY_LENGTH
        and all(0x21 <= ord(character) <= 0x7E for character in secret)
    )


def _classify(error: Exception) -> VoyageErrorCode:
    """By the exception's own type only; its cause and context are never inspected."""
    if isinstance(error, _Refusal):  # this module's own fixed refusals
        return error.code
    if isinstance(error, TimeoutError):  # includes socket.timeout
        return VoyageErrorCode.TIMEOUT
    return VoyageErrorCode.TRANSPORT_FAILED


def _private_tls_context() -> ssl.SSLContext:
    """The verifying TLS context, with ordinary setup failures as fresh fixed errors
    (``TimeoutError`` → ``voyage_timeout``, anything else → ``voyage_transport_failed``), raised
    outside the handler. Process control propagates as the same object; there is no fallback."""
    contexts: list[ssl.SSLContext] = []
    failure: VoyageErrorCode | None = None
    try:
        contexts.append(_tls_context())
    except Exception as error:  # classified by its own type only; never by its chain
        failure = _classify(error)
    if failure is not None or not contexts:
        raise VoyageError(failure or VoyageErrorCode.TRANSPORT_FAILED)
    return contexts[0]


class HttpsVoyageTransport:
    """A ``VoyageTransport`` over ``http.client`` (see the module docstring)."""

    def __init__(
        self,
        api_key: SecretStr,
        *,
        connect_timeout: float = 10.0,
        io_timeout: float = 30.0,
        elapsed_budget: float = 60.0,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
        connection_factory: ConnectionFactory = _https_connection,
        clock: Clock = time.monotonic,
    ) -> None:
        valid = (
            _key(api_key)
            and _seconds(connect_timeout)
            and _seconds(io_timeout)
            and _seconds(elapsed_budget)
            and type(max_response_bytes) is int
            and 1 <= max_response_bytes <= MAX_RESPONSE_BYTES
            and callable(connection_factory)
            and callable(clock)
        )
        if not valid:
            raise VoyageError(VoyageErrorCode.CONFIGURATION)
        self._api_key = api_key
        self._connect_timeout = connect_timeout
        self._io_timeout = io_timeout
        self._budget = elapsed_budget
        self._cap = max_response_bytes
        self._factory = connection_factory
        self._clock = clock
        self._context = _private_tls_context()

    def __repr__(self) -> str:
        return "HttpsVoyageTransport()"

    __str__ = __repr__

    def post(self, body: bytes) -> VoyageResponse:
        """One exchange (see the module docstring); raises a fixed ``VoyageError`` or propagates
        process control as the same object."""
        if not (type(body) is bytes and len(body) <= MAX_REQUEST_BYTES):
            raise VoyageError(VoyageErrorCode.CONFIGURATION)
        exchange = _Exchange(self)
        control: BaseException | None = None
        failure: VoyageErrorCode | None = None
        result: VoyageResponse | None = None
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
            raise VoyageError(failure or VoyageErrorCode.TRANSPORT_FAILED)
        return result


class _Exchange:
    """The state of one ``post``: the timed phases and the objects to close."""

    def __init__(self, transport: HttpsVoyageTransport) -> None:
        self._transport = transport
        self._start = 0.0
        self.connection: Any = None
        self.response: Any = None

    # --- timing ----------------------------------------------------------------------------------

    def _now(self) -> float:
        value = self._transport._clock()
        valid = type(value) is int or (type(value) is float and math.isfinite(value))
        _refuse_unless(valid, VoyageErrorCode.CONFIGURATION)
        return value

    def _remaining(self) -> float:
        return self._transport._budget - (self._now() - self._start)

    def _before(self) -> float:
        """The remaining budget; a spent budget means the phase is not started."""
        remaining = self._remaining()
        _refuse_unless(remaining > 0, VoyageErrorCode.TIMEOUT)
        return remaining

    def _after(self) -> None:
        _refuse_unless(self._remaining() > 0, VoyageErrorCode.TIMEOUT)

    def _io_timeout(self, remaining: float, *, required: bool) -> None:
        """Set the socket timeout through the public ``connection.sock`` if it exists."""
        sock = self.connection.sock
        if sock is None:
            # Before sending or reading headers a missing socket would make ``http.client``
            # reconnect on its own; refuse instead. After the headers it is expected.
            _refuse_unless(not required, VoyageErrorCode.TRANSPORT_FAILED)
            return
        sock.settimeout(min(self._transport._io_timeout, remaining))

    # --- phases ----------------------------------------------------------------------------------

    def run(self, body: bytes) -> VoyageResponse:
        transport = self._transport
        self._start = self._now()

        remaining = self._before()  # 1. connection and TLS
        self.connection = transport._factory(
            VOYAGE_HOST, min(transport._connect_timeout, remaining), transport._context
        )
        self.connection.connect()
        self._after()

        remaining = self._before()  # 2. request sending
        self._io_timeout(remaining, required=True)
        self.connection.request("POST", VOYAGE_PATH, body=body, headers=self._headers())
        self._after()

        remaining = self._before()  # 3. response headers
        self._io_timeout(remaining, required=True)
        self.response = self.connection.getresponse()
        expired = self._remaining() <= 0

        status = self.response.status  # 4. status: a non-200 body is never read
        _refuse_unless(
            type(status) is int and 100 <= status <= 599, VoyageErrorCode.MALFORMED_RESPONSE
        )
        if status != 200:
            return VoyageResponse(status, b"")  # kept even after expiry (N4)
        _refuse_unless(not expired, VoyageErrorCode.TIMEOUT)

        declared = self._framing()  # 5. framing, then bounded reads
        payload = self._read_body(declared)

        self._after()  # 6. no success once the budget is spent
        return VoyageResponse(200, payload)

    def _headers(self) -> dict[str, str]:
        secret = self._transport._api_key.get_secret_value()
        return {
            "Authorization": f"Bearer {secret}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "User-Agent": USER_AGENT,
        }

    def _framing(self) -> int | None:
        """The declared ``Content-Length``, or ``None`` for chunked framing."""
        malformed = VoyageErrorCode.MALFORMED_RESPONSE
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
        _refuse_unless(declared <= self._transport._cap, VoyageErrorCode.RESPONSE_TOO_LARGE)
        return declared

    def _read_body(self, declared: int | None) -> bytes:
        cap = self._transport._cap
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
            self._io_timeout(remaining, required=False)
            piece = self.response.read(wanted)
            self._after()
            _refuse_unless(
                type(piece) is bytes and len(piece) <= wanted, VoyageErrorCode.TRANSPORT_FAILED
            )
            if piece == b"":
                # Early EOF before the declared length; for chunked framing, the end of body.
                _refuse_unless(declared is None, VoyageErrorCode.TRANSPORT_FAILED)
                break
            total += len(piece)
            _refuse_unless(total <= cap, VoyageErrorCode.RESPONSE_TOO_LARGE)
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
