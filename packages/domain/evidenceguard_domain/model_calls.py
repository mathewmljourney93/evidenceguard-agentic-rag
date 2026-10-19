"""Model-call request, response and result values (M5a, ADR-0019).

Pure values, standard library and domain only. The provider protocol, the validating call
boundary and the scripted fake live in ``evidenceguard_agents``; the strict output schemas and
their parser live in ``evidenceguard_domain.agent_outputs``.

- **Values** are frozen dataclasses whose constructors validate exact types (``type(x) is …``:
  no coercion, no ``bool`` for ``int``), reject unknown keyword arguments, never strip or
  normalize text and raise fixed errors outside any ``except`` block. ``dataclasses.replace``
  revalidates through the constructor. Derived fields (``output_schema``, ``request_sha256``)
  are computed by the constructor and never accepted as arguments. ``repr`` and ``str`` show
  purpose, question and prompt identifiers, model IDs, outcome, counts and digests only: never
  system or user text, output text or model output.
- **Canonical request encoding** ``eg-model-call-canonical-v1``: ``json.dumps(value,
  sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)`` encoded as ASCII
  and hashed with SHA-256 (lowercase hex). Texts enter only as the SHA-256 of their exact UTF-8
  bytes; ``timeout_ms`` is excluded. The digest identifies request content for reuse and audit.
  It is not authorization, not proof that a call was made and not proof of any past state.
- **Dependency arrangement.** ``agent_outputs`` imports this module (for ``ModelPurpose``, the
  schema identifiers and ``InvalidModelValueError``). ``StructuredResult`` needs the output
  classes only to check an ``output`` value, so it imports ``agent_outputs`` locally inside that
  check; there is no import cycle at module load.
"""

import hashlib
import json
import re
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from evidenceguard_domain.agent_outputs import AnalystOutput, VerifierOutput

CANONICAL_ENCODING = "eg-model-call-canonical-v1"
MAX_SYSTEM_TEXT_BYTES = 64_000
MAX_USER_TEXT_BYTES = 400_000
MAX_OUTPUT_TEXT_BYTES = 65_536
MAX_OUTPUT_TOKENS = 8_192
MIN_TIMEOUT_MS = 1_000
MAX_TIMEOUT_MS = 120_000
DEFAULT_TIMEOUT_MS = 60_000
MAX_USAGE_TOKENS = 10_000_000
MAX_PROMPT_VERSION = 999
CLOCK_READING_BOUND = 2**53
LATENCY_MS_BOUND = 86_400_000

# The same pattern as ``evidenceguard_domain.evidence.QuestionId`` (pinned by a test); it is
# repeated here so this module stays independent of Pydantic.
QUESTION_ID_PATTERN = r"^[A-Z][A-Z0-9]{1,9}-[0-9]{2,3}$"
PROMPT_ID_PATTERN = r"^[a-z][a-z0-9_]{0,31}$"
MODEL_ID_PATTERN = r"^[a-z0-9][a-z0-9.-]{0,63}$"
PROVIDER_ID_PATTERN = r"^[a-z][a-z0-9-]{0,31}$"

_QUESTION_ID = re.compile(QUESTION_ID_PATTERN, re.ASCII)
_PROMPT_ID = re.compile(PROMPT_ID_PATTERN, re.ASCII)
_MODEL_ID = re.compile(MODEL_ID_PATTERN, re.ASCII)
_PROVIDER_ID = re.compile(PROVIDER_ID_PATTERN, re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}", re.ASCII)


# --- errors (fixed messages: the message is the code) ------------------------------------------


class ModelCallError(Exception):
    """Base of the fixed M5a errors. Never carries submitted values, content or causes."""

    code: ClassVar[str] = "model_call_error"

    def __init__(self) -> None:
        super().__init__(self.code)


class InvalidModelRequestError(ModelCallError):
    """An invalid ``StructuredRequest`` construction or invalid ``call_validated`` arguments."""

    code = "invalid_model_request"


class InvalidModelValueError(ModelCallError):
    """Any other invalid M5a value, including output types."""

    code = "invalid_model_value"


class ModelClockError(ModelCallError):
    """The start-time clock reading was unusable; no provider call was made."""

    code = "model_clock_failed"


# --- enums ----------------------------------------------------------------------------------------


class ModelPurpose(StrEnum):
    VERIFIER = "verifier"
    RISK_ANALYST = "risk_analyst"


class StopKind(StrEnum):
    """Provider stop reasons, as mapped by an adapter. Only ``end_turn`` can complete."""

    END_TURN = "end_turn"
    REFUSAL = "refusal"
    MAX_TOKENS = "max_tokens"
    OTHER = "other"


class CallOutcome(StrEnum):
    COMPLETED = "completed"
    REFUSAL = "refusal"
    MAX_TOKENS = "max_tokens"
    UNEXPECTED_STOP = "unexpected_stop"
    INVALID_OUTPUT = "invalid_output"
    MODEL_MISMATCH = "model_mismatch"
    TIMEOUT = "timeout"
    PROVIDER_FAILED = "provider_failed"


OUTPUT_SCHEMA_IDS: dict[ModelPurpose, str] = {
    ModelPurpose.VERIFIER: "verifier_output_v1",
    ModelPurpose.RISK_ANALYST: "risk_analyst_output_v1",
}

# Outcomes whose response came from the requested model (``model_used == model_requested``).
_RESPONSE_OUTCOMES = frozenset(
    {
        CallOutcome.COMPLETED,
        CallOutcome.REFUSAL,
        CallOutcome.MAX_TOKENS,
        CallOutcome.UNEXPECTED_STOP,
        CallOutcome.INVALID_OUTPUT,
    }
)


# --- helpers -------------------------------------------------------------------------------------


def _check(condition: bool, error: type[ModelCallError]) -> None:
    if not condition:
        raise error()


def _rebuild[T](make: Callable[[], T], error: type[ModelCallError]) -> T:
    """Run a constructor and map any ordinary failure to ``error``, raised outside the handler
    so no cause or context is retained."""
    built: list[T] = []
    with suppress(Exception):
        built.append(make())
    if not built:
        raise error()
    return built[0]


def _matches(pattern: re.Pattern[str], value: object) -> bool:
    return type(value) is str and pattern.fullmatch(value) is not None


def _is_int(value: object, low: int, high: int) -> bool:
    return type(value) is int and low <= value <= high


def utf8_size(value: object) -> int | None:
    """The strict UTF-8 byte length of a ``str``, or ``None`` for any other value or a string
    that cannot be encoded (lone surrogates)."""
    if type(value) is not str:
        return None
    try:
        return len(value.encode("utf-8", errors="strict"))
    except UnicodeEncodeError:
        return None


def _is_text(value: object, low: int, high: int) -> bool:
    size = utf8_size(value)
    return size is not None and low <= size <= high and "\x00" not in str(value)


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_bytes(value: dict[str, Any]) -> bytes:
    """The ``eg-model-call-canonical-v1`` bytes of a JSON object."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


# --- values --------------------------------------------------------------------------------------


@dataclass(frozen=True, init=False, repr=False)
class PromptRef:
    """A prompt identifier, version and SHA-256 (shape only; M5c binds it to an artifact)."""

    prompt_id: str
    version: int
    sha256: str

    def __init__(self, *, prompt_id: str, version: int, sha256: str, **unknown: object) -> None:
        _check(not unknown, InvalidModelValueError)
        _check(_matches(_PROMPT_ID, prompt_id), InvalidModelValueError)
        _check(_is_int(version, 1, MAX_PROMPT_VERSION), InvalidModelValueError)
        _check(_matches(_SHA256, sha256), InvalidModelValueError)
        object.__setattr__(self, "prompt_id", prompt_id)
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "sha256", sha256)

    def __repr__(self) -> str:
        return f"PromptRef(prompt_id={self.prompt_id!r}, version={self.version})"

    __str__ = __repr__


@dataclass(frozen=True, init=False, repr=False)
class ModelUsage:
    """Token counts reported by a provider. Descriptive only; no price."""

    input_tokens: int
    output_tokens: int

    def __init__(self, input_tokens: int, output_tokens: int, **unknown: object) -> None:
        _check(not unknown, InvalidModelValueError)
        _check(_is_int(input_tokens, 0, MAX_USAGE_TOKENS), InvalidModelValueError)
        _check(_is_int(output_tokens, 0, MAX_USAGE_TOKENS), InvalidModelValueError)
        object.__setattr__(self, "input_tokens", input_tokens)
        object.__setattr__(self, "output_tokens", output_tokens)

    def __repr__(self) -> str:
        return f"ModelUsage(input_tokens={self.input_tokens}, output_tokens={self.output_tokens})"

    __str__ = __repr__


@dataclass(frozen=True, init=False, repr=False)
class StructuredRequest:
    """One request for a structured judgment. The output schema follows from ``purpose``."""

    purpose: ModelPurpose
    prompt: PromptRef
    model_id: str
    question_id: str
    system_text: str
    user_text: str
    max_output_tokens: int
    timeout_ms: int
    output_schema: str = field(init=False)
    request_sha256: str = field(init=False)

    def __init__(
        self,
        *,
        purpose: ModelPurpose,
        prompt: PromptRef,
        model_id: str,
        question_id: str,
        system_text: str,
        user_text: str,
        max_output_tokens: int,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        **unknown: object,
    ) -> None:
        _check(not unknown, InvalidModelRequestError)
        _check(type(purpose) is ModelPurpose, InvalidModelRequestError)
        _check(type(prompt) is PromptRef, InvalidModelRequestError)
        checked_prompt = _rebuild(
            lambda: PromptRef(
                prompt_id=prompt.prompt_id, version=prompt.version, sha256=prompt.sha256
            ),
            InvalidModelRequestError,
        )
        _check(_matches(_MODEL_ID, model_id), InvalidModelRequestError)
        _check(_matches(_QUESTION_ID, question_id), InvalidModelRequestError)
        _check(_is_text(system_text, 1, MAX_SYSTEM_TEXT_BYTES), InvalidModelRequestError)
        _check(_is_text(user_text, 1, MAX_USER_TEXT_BYTES), InvalidModelRequestError)
        _check(_is_int(max_output_tokens, 1, MAX_OUTPUT_TOKENS), InvalidModelRequestError)
        _check(_is_int(timeout_ms, MIN_TIMEOUT_MS, MAX_TIMEOUT_MS), InvalidModelRequestError)
        object.__setattr__(self, "purpose", purpose)
        object.__setattr__(self, "prompt", checked_prompt)
        object.__setattr__(self, "model_id", model_id)
        object.__setattr__(self, "question_id", question_id)
        object.__setattr__(self, "system_text", system_text)
        object.__setattr__(self, "user_text", user_text)
        object.__setattr__(self, "max_output_tokens", max_output_tokens)
        object.__setattr__(self, "timeout_ms", timeout_ms)
        object.__setattr__(self, "output_schema", OUTPUT_SCHEMA_IDS[purpose])
        object.__setattr__(
            self, "request_sha256", hashlib.sha256(self.canonical_bytes()).hexdigest()
        )

    def canonical_object(self) -> dict[str, Any]:
        return {
            "canonical": CANONICAL_ENCODING,
            "kind": "model_request",
            "purpose": self.purpose.value,
            "output_schema": OUTPUT_SCHEMA_IDS[self.purpose],
            "prompt": {
                "id": self.prompt.prompt_id,
                "version": self.prompt.version,
                "sha256": self.prompt.sha256,
            },
            "model_id": self.model_id,
            "question_id": self.question_id,
            "max_output_tokens": self.max_output_tokens,
            "system_sha256": _text_sha256(self.system_text),
            "user_sha256": _text_sha256(self.user_text),
        }

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.canonical_object())

    def __repr__(self) -> str:
        return (
            f"StructuredRequest(purpose={self.purpose.value!r}, "
            f"question_id={self.question_id!r}, prompt_id={self.prompt.prompt_id!r}, "
            f"prompt_version={self.prompt.version}, model_id={self.model_id!r}, "
            f"request_sha256={self.request_sha256!r})"
        )

    __str__ = __repr__


@dataclass(frozen=True, init=False, repr=False)
class ProviderResponse:
    """What a provider returns. Untrusted content, even from a fake."""

    stop_kind: StopKind
    output_text: str
    model_used: str
    usage: ModelUsage

    def __init__(
        self,
        *,
        stop_kind: StopKind,
        output_text: str,
        model_used: str,
        usage: ModelUsage,
        **unknown: object,
    ) -> None:
        _check(not unknown, InvalidModelValueError)
        _check(type(stop_kind) is StopKind, InvalidModelValueError)
        size = utf8_size(output_text)
        _check(size is not None and size <= MAX_OUTPUT_TEXT_BYTES, InvalidModelValueError)
        _check(_matches(_MODEL_ID, model_used), InvalidModelValueError)
        _check(type(usage) is ModelUsage, InvalidModelValueError)
        checked_usage = _rebuild(
            lambda: ModelUsage(usage.input_tokens, usage.output_tokens), InvalidModelValueError
        )
        object.__setattr__(self, "stop_kind", stop_kind)
        object.__setattr__(self, "output_text", output_text)
        object.__setattr__(self, "model_used", model_used)
        object.__setattr__(self, "usage", checked_usage)

    def __repr__(self) -> str:
        return (
            f"ProviderResponse(stop_kind={self.stop_kind.value!r}, "
            f"model_used={self.model_used!r}, output_bytes={utf8_size(self.output_text)})"
        )

    __str__ = __repr__


def _check_output(purpose: ModelPurpose, output: object) -> "VerifierOutput | AnalystOutput":
    # Local import: ``agent_outputs`` imports this module (see the module docstring).
    from evidenceguard_domain.agent_outputs import output_schema_for, revalidated_output

    _check(type(output) is output_schema_for(purpose), InvalidModelValueError)
    return revalidated_output(purpose, output)


@dataclass(frozen=True, init=False, repr=False)
class StructuredResult:
    """The classified result of one ``call_validated`` call.

    Field combinations must match exactly one row of the accepted table (ADR-0019): ``output``
    is present only for ``completed``; ``model_used`` and ``usage`` only when a valid response
    was received; ``latency_ms`` is absent when nothing was dispatched.
    """

    request_sha256: str
    purpose: ModelPurpose
    question_id: str
    outcome: CallOutcome
    dispatched: bool
    output: "VerifierOutput | AnalystOutput | None"
    model_requested: str
    model_used: str | None
    usage: ModelUsage | None
    latency_ms: int | None

    def __init__(
        self,
        *,
        request_sha256: str,
        purpose: ModelPurpose,
        question_id: str,
        outcome: CallOutcome,
        dispatched: bool,
        output: "VerifierOutput | AnalystOutput | None",
        model_requested: str,
        model_used: str | None,
        usage: ModelUsage | None,
        latency_ms: int | None,
        **unknown: object,
    ) -> None:
        _check(not unknown, InvalidModelValueError)
        _check(_matches(_SHA256, request_sha256), InvalidModelValueError)
        _check(type(purpose) is ModelPurpose, InvalidModelValueError)
        _check(_matches(_QUESTION_ID, question_id), InvalidModelValueError)
        _check(type(outcome) is CallOutcome, InvalidModelValueError)
        _check(type(dispatched) is bool, InvalidModelValueError)
        _check(_matches(_MODEL_ID, model_requested), InvalidModelValueError)
        _check(model_used is None or _matches(_MODEL_ID, model_used), InvalidModelValueError)
        _check(usage is None or type(usage) is ModelUsage, InvalidModelValueError)
        _check(
            latency_ms is None or _is_int(latency_ms, 0, LATENCY_MS_BOUND), InvalidModelValueError
        )

        has_response = model_used is not None and usage is not None
        _check((model_used is None) == (usage is None), InvalidModelValueError)
        if outcome is CallOutcome.COMPLETED:
            _check(output is not None, InvalidModelValueError)
        else:
            _check(output is None, InvalidModelValueError)
        if outcome in _RESPONSE_OUTCOMES:
            _check(dispatched and has_response, InvalidModelValueError)
            _check(model_used == model_requested, InvalidModelValueError)
        elif outcome is CallOutcome.MODEL_MISMATCH:
            _check(dispatched and has_response, InvalidModelValueError)
            _check(model_used != model_requested, InvalidModelValueError)
        elif outcome is CallOutcome.TIMEOUT:
            _check(dispatched and not has_response, InvalidModelValueError)
        else:  # provider_failed
            _check(not has_response, InvalidModelValueError)
            _check(dispatched or latency_ms is None, InvalidModelValueError)

        checked_usage = (
            None
            if usage is None
            else _rebuild(
                lambda: ModelUsage(usage.input_tokens, usage.output_tokens),
                InvalidModelValueError,
            )
        )
        checked_output = None if output is None else _check_output(purpose, output)

        object.__setattr__(self, "request_sha256", request_sha256)
        object.__setattr__(self, "purpose", purpose)
        object.__setattr__(self, "question_id", question_id)
        object.__setattr__(self, "outcome", outcome)
        object.__setattr__(self, "dispatched", dispatched)
        object.__setattr__(self, "output", checked_output)
        object.__setattr__(self, "model_requested", model_requested)
        object.__setattr__(self, "model_used", model_used)
        object.__setattr__(self, "usage", checked_usage)
        object.__setattr__(self, "latency_ms", latency_ms)

    def __repr__(self) -> str:
        return (
            f"StructuredResult(purpose={self.purpose.value!r}, "
            f"question_id={self.question_id!r}, outcome={self.outcome.value!r}, "
            f"dispatched={self.dispatched}, model_requested={self.model_requested!r}, "
            f"model_used={self.model_used!r}, request_sha256={self.request_sha256!r})"
        )

    __str__ = __repr__


def is_usable_provider_id(value: object) -> bool:
    """Whether ``value`` is exactly a ``str`` matching ``PROVIDER_ID_PATTERN``."""
    return _matches(_PROVIDER_ID, value)


def is_model_id(value: object) -> bool:
    return _matches(_MODEL_ID, value)


def is_prompt_id(value: object) -> bool:
    return _matches(_PROMPT_ID, value)


def is_question_id(value: object) -> bool:
    return _matches(_QUESTION_ID, value)
