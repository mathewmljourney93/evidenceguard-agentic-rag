"""The model-provider protocol and the shared validating call boundary (M5a, ADR-0019).

``call_validated`` is the only way later slices call a model. In order:

1. **Arguments:** ``request`` must be exactly a ``StructuredRequest``; it is rebuilt through its
   constructor and its derived ``output_schema`` and ``request_sha256`` compared with the stored
   ones; ``clock`` must be callable. Failure → ``InvalidModelRequestError``, no provider call.
2. **Start time:** an unusable reading → ``ModelClockError``, no provider call.
3. **Provider identity:** ``provider_id`` read once; it must be exactly a ``str`` matching
   ``^[a-z][a-z0-9-]{0,31}$``, otherwise ``provider_failed`` without dispatch.
4. **Dispatch:** ``generate`` called exactly once. ``ModelCallTimeout`` → ``timeout``; any other
   ordinary ``Exception`` (including a malformed ``ProviderResponse`` constructed inside
   ``generate``) → ``provider_failed``.
5. **End time:** read immediately afterwards; an unusable reading, backwards time, an
   out-of-bound latency or any ordinary failure while calculating leaves ``latency_ms`` absent
   and never changes the outcome. A latency is never clamped or invented.
6. **Response:** exactly a ``ProviderResponse`` with exactly a ``ModelUsage``, both rebuilt
   through their constructors; otherwise ``provider_failed`` with no accounting fields.
7. **Classification:** a model mismatch wins over every stop kind; then refusal, ``max_tokens``,
   other stop (``unexpected_stop``); ``end_turn`` is parsed strictly (``invalid_output`` or
   ``completed``).

There is no retry, repair or hard deadline here: ``timeout_ms`` is passed to the adapter inside
the request, and a synchronous boundary cannot interrupt a call by checking elapsed time
afterwards. Only ordinary ``Exception`` subclasses are caught; process control
(``KeyboardInterrupt``, ``SystemExit`` and other ``BaseException`` subclasses) from ``clock``,
``provider_id`` or ``generate`` propagates as the same object. Failure flags are set inside
handlers and acted on after them, so no exception, message, cause or context is retained.
Nothing here logs. The boundary knows nothing about jobs; later handlers check cancellation and
lease loss after it returns or raises.
"""

import dataclasses
import math
import time
from collections.abc import Callable
from typing import Protocol

from evidenceguard_domain.agent_outputs import OutputType, parse_output
from evidenceguard_domain.model_calls import (
    CLOCK_READING_BOUND,
    LATENCY_MS_BOUND,
    CallOutcome,
    InvalidModelRequestError,
    ModelClockError,
    ModelUsage,
    ProviderResponse,
    StopKind,
    StructuredRequest,
    StructuredResult,
    is_usable_provider_id,
)


class ModelProvider(Protocol):
    """A model provider. Adapters map their stop reasons onto ``StopKind`` and raise
    ``ModelCallTimeout`` for a timeout; they make no hidden retries."""

    @property
    def provider_id(self) -> str: ...

    def generate(self, request: StructuredRequest) -> ProviderResponse: ...


class ModelCallTimeout(Exception):
    """Raised by an adapter when its call timed out. Carries nothing."""

    def __init__(self) -> None:
        super().__init__("model_call_timeout")


Clock = Callable[[], float]


def usable_reading(value: object) -> float | None:
    """A bounded, finite clock reading as a ``float``, or ``None``.

    Integers are checked with integer comparisons before conversion, so a huge integer is
    rejected without ``OverflowError``; ``bool`` and every other type are rejected."""
    if type(value) is int:
        if -CLOCK_READING_BOUND <= value <= CLOCK_READING_BOUND:
            return float(value)
        return None
    if (
        type(value) is float
        and math.isfinite(value)
        and -CLOCK_READING_BOUND <= value <= CLOCK_READING_BOUND
    ):
        return value
    return None


def _read(clock: Clock) -> float | None:
    reading: float | None = None
    try:
        reading = usable_reading(clock())
    except Exception:
        reading = None
    return reading


def _latency(start: float, end: float | None) -> int | None:
    if end is None:
        return None
    latency: int | None = None
    try:
        delta = end - start
        if delta >= 0:
            ms = delta * 1000.0
            if math.isfinite(ms) and ms <= LATENCY_MS_BOUND:
                latency = int(ms)
    except Exception:
        latency = None
    return latency


def _revalidated_request(request: object) -> StructuredRequest | None:
    if type(request) is not StructuredRequest:
        return None
    rebuilt: StructuredRequest | None = None
    try:
        candidate = dataclasses.replace(request)
        if (
            candidate.output_schema == request.output_schema
            and candidate.request_sha256 == request.request_sha256
        ):
            rebuilt = candidate
    except Exception:
        rebuilt = None
    return rebuilt


def _revalidated_response(value: object) -> ProviderResponse | None:
    if type(value) is not ProviderResponse:
        return None
    response: ProviderResponse | None = None
    try:
        if type(value.usage) is ModelUsage:
            usage = dataclasses.replace(value.usage)
            response = dataclasses.replace(value, usage=usage)
    except Exception:
        response = None
    return response


def call_validated(
    provider: ModelProvider, request: StructuredRequest, *, clock: Clock = time.monotonic
) -> StructuredResult:
    """Call ``provider`` at most once for ``request`` and classify the outcome (see the module
    docstring for the exact order and precedence)."""
    checked = _revalidated_request(request)
    if checked is None or not callable(clock):
        raise InvalidModelRequestError()

    start = _read(clock)
    if start is None:
        raise ModelClockError()

    def result(
        outcome: CallOutcome,
        *,
        dispatched: bool,
        response: ProviderResponse | None = None,
        output: OutputType | None = None,
        latency_ms: int | None = None,
    ) -> StructuredResult:
        return StructuredResult(
            request_sha256=checked.request_sha256,
            purpose=checked.purpose,
            question_id=checked.question_id,
            outcome=outcome,
            dispatched=dispatched,
            output=output,
            model_requested=checked.model_id,
            model_used=None if response is None else response.model_used,
            usage=None if response is None else response.usage,
            latency_ms=latency_ms,
        )

    identified = False
    try:
        identified = is_usable_provider_id(provider.provider_id)
    except Exception:
        identified = False
    if not identified:
        return result(CallOutcome.PROVIDER_FAILED, dispatched=False)

    returned: object = None
    raised: CallOutcome | None = None
    try:
        returned = provider.generate(checked)
    except ModelCallTimeout:
        raised = CallOutcome.TIMEOUT
    except Exception:
        raised = CallOutcome.PROVIDER_FAILED
    latency = _latency(start, _read(clock))

    if raised is not None:
        return result(raised, dispatched=True, latency_ms=latency)
    response = _revalidated_response(returned)
    if response is None:
        return result(CallOutcome.PROVIDER_FAILED, dispatched=True, latency_ms=latency)

    output: OutputType | None = None
    if response.model_used != checked.model_id:
        outcome = CallOutcome.MODEL_MISMATCH
    elif response.stop_kind is StopKind.REFUSAL:
        outcome = CallOutcome.REFUSAL
    elif response.stop_kind is StopKind.MAX_TOKENS:
        outcome = CallOutcome.MAX_TOKENS
    elif response.stop_kind is StopKind.OTHER:
        outcome = CallOutcome.UNEXPECTED_STOP
    else:
        output = parse_output(checked.purpose, response.output_text)
        outcome = CallOutcome.INVALID_OUTPUT if output is None else CallOutcome.COMPLETED
    return result(outcome, dispatched=True, response=response, output=output, latency_ms=latency)
