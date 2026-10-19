"""``ScriptedFakeProvider``: a deterministic, test-owned model provider (M5a, ADR-0019).

Scripts map ``(prompt_id, question_id)`` to a non-empty tuple of steps, consumed in order:

- ``Respond(text, usage)``: an ``end_turn`` response with ``text`` verbatim (it may be invalid
  JSON on purpose);
- ``Refuse()``, ``StopMaxTokens(text)``, ``StopOther()``: the corresponding stop kinds;
- ``Timeout()``: raises ``ModelCallTimeout``;
- ``Fail()``: raises a plain ``RuntimeError`` with a fixed message;
- ``WrongModel(model_used, text)``: an ``end_turn`` response naming another model.

Bounds: at most 256 keys, 16 steps per key, 65,536 UTF-8 bytes per text and 4 MiB of script
text in total. The constructor copies the configuration into immutable tuples; anything else,
including an ordinary failure while reading the supplied mapping, raises a fresh
``InvalidModelValueError``.

**Memory.** Scripts hold raw response text by design: they are test fixtures, and the fake is
held for a test-owned lifetime. Production code never constructs it. Its call history records
only ``(prompt_id, question_id, request_sha256, step_index)`` and is capped at 4,096 entries.

**Selection.** Under one lock each call takes its key's next step index and appends the history
entry; the step then runs outside the lock. Every step is consumed exactly once. A missing key,
an exhausted script (the last step is never repeated) or a full history raises the fixed
``ScriptedFakeError`` without recording. Sequential calls are fully deterministic; concurrent
calls each receive a distinct step in lock-acquisition order, which the history records.

The fake never reads files, the environment, the network or ground truth, never blocks, and its
``repr`` shows the model ID and counts only, never script text. Its outputs are contract
fixtures, never quality evidence.
"""

import threading
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from types import MappingProxyType

from evidenceguard_agents.providers import ModelCallTimeout
from evidenceguard_domain.model_calls import (
    MAX_OUTPUT_TEXT_BYTES,
    InvalidModelValueError,
    ModelUsage,
    ProviderResponse,
    StopKind,
    StructuredRequest,
    is_model_id,
    is_prompt_id,
    is_question_id,
    utf8_size,
)

FAKE_PROVIDER_ID = "scripted-fake"
FAKE_MODEL_ID = "fake-scripted-v1"
MAX_SCRIPT_KEYS = 256
MAX_STEPS_PER_KEY = 16
MAX_SCRIPT_TEXT_BYTES = 4 * 1024 * 1024
MAX_HISTORY = 4_096


class ScriptedFakeError(RuntimeError):
    """A missing key, an exhausted script or a full history. Carries nothing."""

    def __init__(self) -> None:
        super().__init__("scripted_fake_unavailable")


def _check(condition: bool) -> None:
    if not condition:
        raise InvalidModelValueError()


def _script_text(value: object) -> str:
    size = utf8_size(value)
    _check(size is not None and size <= MAX_OUTPUT_TEXT_BYTES)
    assert isinstance(value, str)
    return value


def _text_bytes(value: str) -> int:
    return len(value.encode("utf-8"))


# --- steps ----------------------------------------------------------------------------------------


@dataclass(frozen=True, init=False, repr=False)
class Respond:
    text: str
    usage: ModelUsage

    def __init__(self, text: str, usage: ModelUsage | None = None, **unknown: object) -> None:
        _check(not unknown)
        checked_usage = ModelUsage(0, 0) if usage is None else usage
        _check(type(checked_usage) is ModelUsage)
        object.__setattr__(self, "text", _script_text(text))
        object.__setattr__(
            self, "usage", ModelUsage(checked_usage.input_tokens, checked_usage.output_tokens)
        )

    def __repr__(self) -> str:
        return "Respond()"


@dataclass(frozen=True, init=False, repr=False)
class Refuse:
    def __init__(self, **unknown: object) -> None:
        _check(not unknown)

    def __repr__(self) -> str:
        return "Refuse()"


@dataclass(frozen=True, init=False, repr=False)
class StopMaxTokens:
    text: str

    def __init__(self, text: str, **unknown: object) -> None:
        _check(not unknown)
        object.__setattr__(self, "text", _script_text(text))

    def __repr__(self) -> str:
        return "StopMaxTokens()"


@dataclass(frozen=True, init=False, repr=False)
class StopOther:
    def __init__(self, **unknown: object) -> None:
        _check(not unknown)

    def __repr__(self) -> str:
        return "StopOther()"


@dataclass(frozen=True, init=False, repr=False)
class Timeout:
    def __init__(self, **unknown: object) -> None:
        _check(not unknown)

    def __repr__(self) -> str:
        return "Timeout()"


@dataclass(frozen=True, init=False, repr=False)
class Fail:
    def __init__(self, **unknown: object) -> None:
        _check(not unknown)

    def __repr__(self) -> str:
        return "Fail()"


@dataclass(frozen=True, init=False, repr=False)
class WrongModel:
    model_used: str
    text: str

    def __init__(self, model_used: str, text: str, **unknown: object) -> None:
        _check(not unknown)
        _check(is_model_id(model_used))
        object.__setattr__(self, "model_used", model_used)
        object.__setattr__(self, "text", _script_text(text))

    def __repr__(self) -> str:
        return f"WrongModel(model_used={self.model_used!r})"


Step = Respond | Refuse | StopMaxTokens | StopOther | Timeout | Fail | WrongModel
_STEP_TYPES = (Respond, Refuse, StopMaxTokens, StopOther, Timeout, Fail, WrongModel)


def _step_text(step: Step) -> str:
    if isinstance(step, Respond | StopMaxTokens | WrongModel):
        return step.text
    return ""


def _copy_scripts(scripts: object, model_id: str) -> dict[tuple[str, str], tuple[Step, ...]]:
    _check(isinstance(scripts, Mapping))
    assert isinstance(scripts, Mapping)
    items = list(scripts.items())
    _check(1 <= len(items) <= MAX_SCRIPT_KEYS)
    copied: dict[tuple[str, str], tuple[Step, ...]] = {}
    total = 0
    for key, steps in items:
        _check(type(key) is tuple and len(key) == 2)
        prompt_id, question_id = key
        _check(is_prompt_id(prompt_id) and is_question_id(question_id))
        _check(type(steps) is tuple and 1 <= len(steps) <= MAX_STEPS_PER_KEY)
        _check(all(type(step) in _STEP_TYPES for step in steps))
        for step in steps:
            if isinstance(step, WrongModel):
                _check(step.model_used != model_id)
            total += _text_bytes(_step_text(step))
        copied[(prompt_id, question_id)] = tuple(steps)
    _check(total <= MAX_SCRIPT_TEXT_BYTES)
    return copied


def _copied_scripts(scripts: object, model_id: str) -> dict[tuple[str, str], tuple[Step, ...]]:
    """Validate and copy the configuration. Any ordinary failure while reading the supplied
    mapping (its ``items``, iteration or values) becomes a fresh ``InvalidModelValueError``
    raised after the handler, so no original text, cause or context is kept; process control
    propagates as the same object. Error normalization only, not a sandbox (Prompt 172)."""
    copied: list[dict[tuple[str, str], tuple[Step, ...]]] = []
    with suppress(Exception):
        copied.append(_copy_scripts(scripts, model_id))
    if not copied:
        raise InvalidModelValueError()
    return copied[0]


@dataclass(frozen=True)
class CallRecord:
    """One selected step: identifiers, the request digest and the step index. No text."""

    prompt_id: str
    question_id: str
    request_sha256: str
    step_index: int


# --- the fake ------------------------------------------------------------------------------------


class ScriptedFakeProvider:
    """A deterministic ``ModelProvider`` for contract tests (see the module docstring)."""

    def __init__(
        self,
        *,
        scripts: Mapping[tuple[str, str], tuple[Step, ...]],
        model_id: str = FAKE_MODEL_ID,
        **unknown: object,
    ) -> None:
        _check(not unknown)
        _check(is_model_id(model_id))
        copied = _copied_scripts(scripts, model_id)
        self._model_id = model_id
        self._scripts: Mapping[tuple[str, str], tuple[Step, ...]] = MappingProxyType(copied)
        self._lock = threading.Lock()
        self._next: dict[tuple[str, str], int] = {}
        self._history: list[CallRecord] = []

    @property
    def provider_id(self) -> str:
        return FAKE_PROVIDER_ID

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def history(self) -> tuple[CallRecord, ...]:
        with self._lock:
            return tuple(self._history)

    def calls_for(self, prompt_id: str, question_id: str) -> int:
        with self._lock:
            return self._next.get((prompt_id, question_id), 0)

    def _select(self, request: StructuredRequest) -> Step | None:
        key = (request.prompt.prompt_id, request.question_id)
        with self._lock:
            steps = self._scripts.get(key)
            index = self._next.get(key, 0)
            if steps is None or index >= len(steps) or len(self._history) >= MAX_HISTORY:
                return None
            self._next[key] = index + 1
            self._history.append(CallRecord(key[0], key[1], request.request_sha256, index))
            return steps[index]

    def generate(self, request: StructuredRequest) -> ProviderResponse:
        if type(request) is not StructuredRequest:
            raise ScriptedFakeError()
        step = self._select(request)
        if step is None:
            raise ScriptedFakeError()
        if isinstance(step, Timeout):
            raise ModelCallTimeout()
        if isinstance(step, Fail):
            raise RuntimeError("scripted_failure")
        zero = ModelUsage(0, 0)
        if isinstance(step, Respond):
            return self._response(StopKind.END_TURN, step.text, step.usage)
        if isinstance(step, StopMaxTokens):
            return self._response(StopKind.MAX_TOKENS, step.text, zero)
        if isinstance(step, WrongModel):
            return ProviderResponse(
                stop_kind=StopKind.END_TURN,
                output_text=step.text,
                model_used=step.model_used,
                usage=zero,
            )
        kind = StopKind.REFUSAL if isinstance(step, Refuse) else StopKind.OTHER
        return self._response(kind, "", zero)

    def _response(self, kind: StopKind, text: str, usage: ModelUsage) -> ProviderResponse:
        return ProviderResponse(
            stop_kind=kind, output_text=text, model_used=self._model_id, usage=usage
        )

    def __repr__(self) -> str:
        steps = sum(len(steps) for steps in self._scripts.values())
        with self._lock:
            calls = len(self._history)
        return (
            f"ScriptedFakeProvider(model_id={self._model_id!r}, keys={len(self._scripts)}, "
            f"steps={steps}, calls={calls})"
        )

    __str__ = __repr__
