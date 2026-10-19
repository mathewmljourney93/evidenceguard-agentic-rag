"""M5a model-call values, canonical encoding and the ``call_validated`` boundary (ADR-0019).

No test here touches the network: an autouse guard makes any socket connection or name lookup
fail. Providers are in-process stubs or the scripted fake.
"""

import dataclasses
import hashlib
import json
import logging
import socket
import traceback
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from evidenceguard_agents.providers import ModelCallTimeout, call_validated, usable_reading
from evidenceguard_agents.scripted import Respond, ScriptedFakeProvider
from evidenceguard_domain.agent_outputs import (
    AnalystOutput,
    ClaimOutput,
    FindingOutput,
    QuoteRef,
    VerifierOutput,
)
from evidenceguard_domain.evidence import EvidenceQuestion, Severity, Verdict
from evidenceguard_domain.model_calls import (
    CLOCK_READING_BOUND,
    LATENCY_MS_BOUND,
    QUESTION_ID_PATTERN,
    CallOutcome,
    InvalidModelRequestError,
    InvalidModelValueError,
    ModelCallError,
    ModelClockError,
    ModelPurpose,
    ModelUsage,
    PromptRef,
    ProviderResponse,
    StopKind,
    StructuredRequest,
    StructuredResult,
)

CANARY = "EG-M5A-CANARY-7731"
MODEL = "fake-scripted-v1"
CHUNK = "00000000-0000-0000-0000-000000000001"
VERIFIER_JSON = json.dumps(
    {
        "verdict": "supported",
        "claims": [{"text": "c", "citations": [{"chunk_id": CHUNK, "quote": "q"}]}],
        "rationale": "r",
    }
)
ANALYST_JSON = json.dumps(
    {
        "findings": [
            {
                "question_ids": ["RET-01"],
                "title": "t",
                "severity": "high",
                "statement": "s",
            }
        ]
    }
)

# Computed outside the project code from the literal canonical JSON below.
PINNED_CANONICAL = (
    b'{"canonical":"eg-model-call-canonical-v1","kind":"model_request","max_output_tokens":2048,'
    b'"model_id":"fake-scripted-v1","output_schema":"verifier_output_v1","prompt":{"id":"verifier",'
    b'"sha256":"1111111111111111111111111111111111111111111111111111111111111111","version":1},'
    b'"purpose":"verifier","question_id":"RET-01",'
    b'"system_sha256":"bbc5e661e106c6dcd8dc6dd186454c2fcba3c710fb4d8e71a60c93eaf077f073",'
    b'"user_sha256":"04f8996da763b7a969b1028ee3007569eaf3a635486ddab211d512c85b9df8fb"}'
)
PINNED_SHA256 = "20dcc59a564e16ff0069090555c0d14a4fbd5981beaa674f53c27002d64faf3d"


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: object, **kwargs: object) -> Any:
        raise AssertionError("a test attempted network access")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


# --- helpers -------------------------------------------------------------------------------------


def prompt(**overrides: Any) -> PromptRef:
    values: dict[str, Any] = {"prompt_id": "verifier", "version": 1, "sha256": "1" * 64}
    values.update(overrides)
    return PromptRef(**values)


def request(**overrides: Any) -> StructuredRequest:
    values: dict[str, Any] = {
        "purpose": ModelPurpose.VERIFIER,
        "prompt": prompt(),
        "model_id": MODEL,
        "question_id": "RET-01",
        "system_text": "system",
        "user_text": "user",
        "max_output_tokens": 2048,
    }
    values.update(overrides)
    return StructuredRequest(**values)


def response(**overrides: Any) -> ProviderResponse:
    values: dict[str, Any] = {
        "stop_kind": StopKind.END_TURN,
        "output_text": VERIFIER_JSON,
        "model_used": MODEL,
        "usage": ModelUsage(3, 4),
    }
    values.update(overrides)
    return ProviderResponse(**values)


def verifier_output() -> VerifierOutput:
    return VerifierOutput(
        verdict=Verdict.SUPPORTED,
        claims=(ClaimOutput(text="c", citations=(QuoteRef(chunk_id=CHUNK, quote="q"),)),),
        rationale="r",
    )


def analyst_output() -> AnalystOutput:
    finding = FindingOutput(
        question_ids=("RET-01",), title="t", severity=Severity.HIGH, statement="s"
    )
    return AnalystOutput(findings=(finding,))


def result(**overrides: Any) -> StructuredResult:
    values: dict[str, Any] = {
        "request_sha256": "a" * 64,
        "purpose": ModelPurpose.VERIFIER,
        "question_id": "RET-01",
        "outcome": CallOutcome.COMPLETED,
        "dispatched": True,
        "output": verifier_output(),
        "model_requested": MODEL,
        "model_used": MODEL,
        "usage": ModelUsage(1, 2),
        "latency_ms": 5,
    }
    values.update(overrides)
    return StructuredResult(**values)


def assert_fixed(error: BaseException, kind: type[ModelCallError]) -> None:
    assert type(error) is kind
    assert str(error) == kind.code
    assert error.__cause__ is None and error.__context__ is None
    assert error.__suppress_context__ is False


class Clock:
    """A clock returning scripted readings in order."""

    def __init__(self, *readings: object) -> None:
        self._readings: Iterator[object] = iter(readings)
        self.calls = 0

    def __call__(self) -> Any:
        self.calls += 1
        value = next(self._readings)
        if isinstance(value, BaseException):
            raise value
        return value


class Stub:
    """A provider stub counting ``generate`` calls."""

    def __init__(
        self,
        result: Callable[[StructuredRequest], ProviderResponse] | None = None,
        provider_id: object = "stub-provider",
    ) -> None:
        self._result = result or (lambda _request: response())
        self._provider_id = provider_id
        self.calls = 0
        self.received: list[StructuredRequest] = []

    @property
    def provider_id(self) -> str:
        if isinstance(self._provider_id, BaseException):
            raise self._provider_id
        return self._provider_id  # type: ignore[return-value]

    def generate(self, request: StructuredRequest) -> ProviderResponse:
        self.calls += 1
        self.received.append(request)
        return self._result(request)


def raising(error: BaseException) -> Callable[[StructuredRequest], ProviderResponse]:
    def generate(_request: StructuredRequest) -> ProviderResponse:
        raise error

    return generate


def returning(value: object) -> Callable[[StructuredRequest], ProviderResponse]:
    return lambda _request: value  # type: ignore[return-value]


# --- PromptRef and ModelUsage --------------------------------------------------------------------


def test_prompt_ref_bounds() -> None:
    assert prompt(prompt_id="a").prompt_id == "a"
    assert prompt(prompt_id="v" + "x" * 31).version == 1
    assert prompt(version=999).version == 999
    for overrides in (
        {"prompt_id": "Verifier"},
        {"prompt_id": "1verifier"},
        {"prompt_id": "v" + "x" * 32},
        {"prompt_id": "verifier\n"},
        {"prompt_id": b"verifier"},
        {"version": 0},
        {"version": 1000},
        {"version": True},
        {"version": 1.0},
        {"version": "1"},
        {"sha256": "A" * 64},
        {"sha256": "1" * 63},
        {"extra": 1},
    ):
        with pytest.raises(InvalidModelValueError) as caught:
            prompt(**overrides)
        assert_fixed(caught.value, InvalidModelValueError)


def test_model_usage_bounds() -> None:
    assert ModelUsage(0, 10_000_000).output_tokens == 10_000_000
    for args in ((-1, 0), (0, 10_000_001), (True, 0), (0, 1.0), ("1", 0)):
        with pytest.raises(InvalidModelValueError):
            ModelUsage(*args)
    with pytest.raises(InvalidModelValueError):
        ModelUsage(1, 2, extra=3)


def test_call_values_are_frozen_and_replace_revalidates() -> None:
    value = request()
    with pytest.raises(dataclasses.FrozenInstanceError):
        value.user_text = "other"  # type: ignore[misc]
    replaced = dataclasses.replace(value, user_text="other")
    assert replaced.user_text == "other" and replaced.request_sha256 != value.request_sha256
    with pytest.raises(InvalidModelRequestError):
        dataclasses.replace(value, max_output_tokens=0)
    with pytest.raises(InvalidModelValueError):
        dataclasses.replace(ModelUsage(1, 1), input_tokens=-1)
    with pytest.raises(InvalidModelValueError):
        dataclasses.replace(prompt(), version=0)
    with pytest.raises(ValueError):  # derived fields cannot be supplied
        dataclasses.replace(value, request_sha256="0" * 64)


# --- StructuredRequest ---------------------------------------------------------------------------


def test_request_accepts_its_bounds() -> None:
    assert request(system_text="é" * 32_000).system_text  # exactly 64,000 bytes
    assert request(user_text="\U0001d11e" * 100_000).user_text  # exactly 400,000 bytes
    assert request(max_output_tokens=1).max_output_tokens == 1
    assert request(max_output_tokens=8192).max_output_tokens == 8192
    assert request(timeout_ms=1000).timeout_ms == 1000
    assert request(timeout_ms=120_000).timeout_ms == 120_000
    assert request().timeout_ms == 60_000
    assert request(model_id="a").model_id == "a"
    assert request(model_id="a" * 64).model_id == "a" * 64
    assert request(question_id="ENC-123").question_id == "ENC-123"
    assert request(system_text="  padded  ").system_text == "  padded  "  # never stripped


@pytest.mark.parametrize(
    "overrides",
    [
        {"purpose": "verifier"},
        {"prompt": {"prompt_id": "verifier", "version": 1, "sha256": "1" * 64}},
        {"model_id": "Fake"},
        {"model_id": ".fake"},
        {"model_id": "a" * 65},
        {"model_id": "fake model"},
        {"question_id": "ret-01"},
        {"question_id": "R-01"},
        {"question_id": "RET-1"},
        {"system_text": ""},
        {"system_text": "é" * 32_000 + "x"},
        {"system_text": "a\x00b"},
        {"system_text": "\ud800"},
        {"system_text": b"system"},
        {"user_text": ""},
        {"user_text": "x" * 400_001},
        {"user_text": "\udfff"},
        {"max_output_tokens": 0},
        {"max_output_tokens": 8193},
        {"max_output_tokens": True},
        {"max_output_tokens": 2048.0},
        {"timeout_ms": 999},
        {"timeout_ms": 120_001},
        {"timeout_ms": True},
        {"output_schema": "verifier_output_v1"},
        {"request_sha256": "0" * 64},
        {"unknown": 1},
    ],
)
def test_request_rejects_invalid_fields(overrides: dict[str, Any]) -> None:
    with pytest.raises(InvalidModelRequestError) as caught:
        request(**overrides)
    assert_fixed(caught.value, InvalidModelRequestError)


def test_request_revalidates_a_bypassed_prompt() -> None:
    bad = prompt()
    object.__setattr__(bad, "version", 0)
    with pytest.raises(InvalidModelRequestError):
        request(prompt=bad)


def test_output_schema_follows_purpose() -> None:
    assert request().output_schema == "verifier_output_v1"
    analyst = request(purpose=ModelPurpose.RISK_ANALYST)
    assert analyst.output_schema == "risk_analyst_output_v1"


def test_question_id_pattern_matches_the_domain_contract() -> None:
    metadata = EvidenceQuestion.model_fields["question_id"].metadata
    patterns = [getattr(item, "pattern", None) for item in metadata]
    assert QUESTION_ID_PATTERN in patterns


# --- canonical encoding --------------------------------------------------------------------------


def test_canonical_bytes_and_digest_are_pinned() -> None:
    value = request()
    assert value.canonical_bytes() == PINNED_CANONICAL
    assert hashlib.sha256(PINNED_CANONICAL).hexdigest() == PINNED_SHA256
    assert value.request_sha256 == PINNED_SHA256


def test_digest_excludes_timeout_and_changes_with_each_included_field() -> None:
    base = request()
    assert request(timeout_ms=1000).request_sha256 == base.request_sha256
    for overrides in (
        {"purpose": ModelPurpose.RISK_ANALYST},
        {"prompt": prompt(prompt_id="other")},
        {"prompt": prompt(version=2)},
        {"prompt": prompt(sha256="2" * 64)},
        {"model_id": "other-model"},
        {"question_id": "ENC-01"},
        {"system_text": "system2"},
        {"user_text": "user2"},
        {"max_output_tokens": 2047},
    ):
        assert request(**overrides).request_sha256 != base.request_sha256, overrides


def test_canonical_bytes_contain_no_text() -> None:
    value = request(system_text=f"sys {CANARY}", user_text=f"user {CANARY}")
    assert CANARY.encode() not in value.canonical_bytes()
    for text in (repr(value), str(value), repr(value.prompt)):
        assert CANARY not in text


# --- ProviderResponse ----------------------------------------------------------------------------


def test_provider_response_bounds() -> None:
    assert response(output_text="").output_text == ""
    assert response(output_text="x" * 65_536).output_text
    for overrides in (
        {"stop_kind": "end_turn"},
        {"output_text": "x" * 65_537},
        {"output_text": "\ud800"},
        {"output_text": b"{}"},
        {"model_used": "Fake"},
        {"usage": (1, 2)},
        {"extra": 1},
    ):
        with pytest.raises(InvalidModelValueError):
            response(**overrides)
    usage = ModelUsage(1, 1)
    object.__setattr__(usage, "input_tokens", -1)
    with pytest.raises(InvalidModelValueError):
        response(usage=usage)
    shown = repr(response(output_text=json.dumps({"rationale": CANARY})))
    assert CANARY not in shown


# --- StructuredResult ----------------------------------------------------------------------------


def test_every_result_row_constructs() -> None:
    assert result().output == verifier_output()
    assert result(latency_ms=None).latency_ms is None
    analyst = result(purpose=ModelPurpose.RISK_ANALYST, output=analyst_output())
    assert type(analyst.output) is AnalystOutput
    for outcome in (
        CallOutcome.REFUSAL,
        CallOutcome.MAX_TOKENS,
        CallOutcome.UNEXPECTED_STOP,
        CallOutcome.INVALID_OUTPUT,
    ):
        assert result(outcome=outcome, output=None).outcome is outcome
    mismatch = result(outcome=CallOutcome.MODEL_MISMATCH, output=None, model_used="other")
    assert mismatch.model_used == "other"
    timeout = result(outcome=CallOutcome.TIMEOUT, output=None, model_used=None, usage=None)
    assert timeout.latency_ms == 5
    failed = result(outcome=CallOutcome.PROVIDER_FAILED, output=None, model_used=None, usage=None)
    assert failed.dispatched
    undispatched = result(
        outcome=CallOutcome.PROVIDER_FAILED,
        output=None,
        model_used=None,
        usage=None,
        dispatched=False,
        latency_ms=None,
    )
    assert not undispatched.dispatched
    assert result(latency_ms=LATENCY_MS_BOUND).latency_ms == LATENCY_MS_BOUND


@pytest.mark.parametrize(
    "overrides",
    [
        {"output": None},
        {"output": analyst_output()},
        {"purpose": ModelPurpose.RISK_ANALYST},
        {"outcome": CallOutcome.REFUSAL},
        {"outcome": CallOutcome.INVALID_OUTPUT},
        {"model_used": "other"},
        {"model_used": None, "usage": None},
        {"usage": None},
        {"model_used": None},
        {"dispatched": False},
        {"outcome": CallOutcome.MODEL_MISMATCH, "output": None},
        {"outcome": CallOutcome.MODEL_MISMATCH, "output": None, "model_used": None, "usage": None},
        {"outcome": CallOutcome.TIMEOUT, "output": None},
        {
            "outcome": CallOutcome.TIMEOUT,
            "output": None,
            "model_used": None,
            "usage": None,
            "dispatched": False,
        },
        {"outcome": CallOutcome.PROVIDER_FAILED, "output": None},
        {
            "outcome": CallOutcome.PROVIDER_FAILED,
            "output": None,
            "model_used": None,
            "usage": None,
            "dispatched": False,
        },
        {"outcome": "completed"},
        {"dispatched": 1},
        {"latency_ms": -1},
        {"latency_ms": LATENCY_MS_BOUND + 1},
        {"latency_ms": True},
        {"latency_ms": 1.0},
        {"request_sha256": "A" * 64},
        {"question_id": "ret-01"},
        {"model_requested": "Fake"},
        {"usage": (1, 2)},
        {"output": {"verdict": "supported", "rationale": "r"}},
        {"extra": 1},
    ],
)
def test_invalid_result_combinations_are_rejected(overrides: dict[str, Any]) -> None:
    with pytest.raises(InvalidModelValueError) as caught:
        result(**overrides)
    assert_fixed(caught.value, InvalidModelValueError)


def test_result_revalidates_a_bypassed_output() -> None:
    output = verifier_output()
    object.__setattr__(output, "rationale", "")
    with pytest.raises(InvalidModelValueError):
        result(output=output)


def test_result_representation_is_private() -> None:
    output = VerifierOutput(verdict=Verdict.SUPPORTED, rationale=CANARY)
    value = result(output=output)
    assert CANARY not in repr(value) and CANARY not in str(value)


# --- clock readings ------------------------------------------------------------------------------


def test_usable_readings() -> None:
    assert usable_reading(CLOCK_READING_BOUND) == float(CLOCK_READING_BOUND)
    assert usable_reading(-CLOCK_READING_BOUND) == -float(CLOCK_READING_BOUND)
    assert usable_reading(1.5) == 1.5
    assert usable_reading(0) == 0.0
    for value in (
        CLOCK_READING_BOUND + 1,
        -CLOCK_READING_BOUND - 1,
        10**1000,
        -(10**1000),
        1e308,
        -1e308,
        float("nan"),
        float("inf"),
        float("-inf"),
        True,
        False,
        "1",
        None,
        object(),
    ):
        assert usable_reading(value) is None, value


# --- call_validated: arguments -------------------------------------------------------------------


def test_invalid_arguments_raise_before_any_call() -> None:
    stub = Stub()
    for bad in (None, "request", {"purpose": "verifier"}):
        with pytest.raises(InvalidModelRequestError) as caught:
            call_validated(stub, bad)  # type: ignore[arg-type]
        assert_fixed(caught.value, InvalidModelRequestError)
    with pytest.raises(InvalidModelRequestError):
        call_validated(stub, request(), clock=1.0)  # type: ignore[arg-type]
    assert stub.calls == 0


def test_a_bypassed_request_is_revalidated_before_dispatch() -> None:
    stub = Stub()
    changed = request()
    object.__setattr__(changed, "user_text", "changed after construction")
    invalid = request()
    object.__setattr__(invalid, "max_output_tokens", 0)
    relabelled = request()
    object.__setattr__(relabelled, "output_schema", "risk_analyst_output_v1")
    for value in (changed, invalid, relabelled):
        with pytest.raises(InvalidModelRequestError):
            call_validated(stub, value)
    assert stub.calls == 0


def test_the_provider_receives_a_validated_equal_request() -> None:
    stub = Stub()
    value = request()
    call_validated(stub, value)
    assert stub.calls == 1
    assert stub.received[0] == value
    assert stub.received[0].request_sha256 == value.request_sha256


# --- call_validated: provider identity -----------------------------------------------------------


@pytest.mark.parametrize(
    "provider_id",
    ["", "Scripted", "1fake", "a" * 33, "fake provider", b"fake", None, 7, RuntimeError("x")],
)
def test_an_unusable_provider_id_fails_without_dispatch(provider_id: object) -> None:
    stub = Stub(provider_id=provider_id)
    outcome = call_validated(stub, request(), clock=Clock(1.0))
    assert outcome.outcome is CallOutcome.PROVIDER_FAILED
    assert not outcome.dispatched and outcome.latency_ms is None
    assert outcome.model_used is None and outcome.usage is None
    assert stub.calls == 0


def test_a_str_subclass_provider_id_is_rejected() -> None:
    class Name(str):
        pass

    stub = Stub(provider_id=Name("stub-provider"))
    assert call_validated(stub, request()).outcome is CallOutcome.PROVIDER_FAILED
    assert stub.calls == 0


# --- call_validated: dispatch and responses ------------------------------------------------------


def test_completed_call() -> None:
    stub = Stub()
    outcome = call_validated(stub, request(), clock=Clock(10.0, 10.25))
    assert outcome.outcome is CallOutcome.COMPLETED
    assert outcome.output == verifier_output()
    assert outcome.model_used == MODEL and outcome.usage == ModelUsage(3, 4)
    assert outcome.latency_ms == 250 and outcome.dispatched
    assert outcome.request_sha256 == request().request_sha256
    assert stub.calls == 1


def test_analyst_call_uses_the_analyst_schema() -> None:
    stub = Stub(returning(response(output_text=ANALYST_JSON)))
    outcome = call_validated(stub, request(purpose=ModelPurpose.RISK_ANALYST))
    assert outcome.outcome is CallOutcome.COMPLETED
    assert type(outcome.output) is AnalystOutput
    wrong = call_validated(Stub(returning(response(output_text=ANALYST_JSON))), request())
    assert wrong.outcome is CallOutcome.INVALID_OUTPUT and wrong.output is None


def test_timeouts_and_failures_from_generate() -> None:
    class SlowTimeout(ModelCallTimeout):
        pass

    cases = [
        (ModelCallTimeout(), CallOutcome.TIMEOUT),
        (SlowTimeout(), CallOutcome.TIMEOUT),
        (RuntimeError(CANARY), CallOutcome.PROVIDER_FAILED),
        (ValueError(CANARY), CallOutcome.PROVIDER_FAILED),
        (InvalidModelValueError(), CallOutcome.PROVIDER_FAILED),
    ]
    for error, expected in cases:
        stub = Stub(raising(error))
        outcome = call_validated(stub, request(), clock=Clock(1.0, 2.0))
        assert outcome.outcome is expected
        assert outcome.dispatched and outcome.latency_ms == 1000
        assert outcome.model_used is None and outcome.usage is None and outcome.output is None
        assert stub.calls == 1


def test_a_malformed_response_built_inside_generate_is_provider_failed() -> None:
    def generate(_request: StructuredRequest) -> ProviderResponse:
        return response(output_text="x" * 70_000)

    stub = Stub(generate)
    assert call_validated(stub, request()).outcome is CallOutcome.PROVIDER_FAILED
    assert stub.calls == 1


def test_wrong_return_types_and_invalid_nested_usage_are_provider_failed() -> None:
    mutated_usage = response()
    bad_usage = ModelUsage(1, 1)
    object.__setattr__(bad_usage, "output_tokens", -3)
    object.__setattr__(mutated_usage, "usage", bad_usage)
    wrong_usage_type = response()
    object.__setattr__(wrong_usage_type, "usage", (1, 1))
    mutated_text = response()
    object.__setattr__(mutated_text, "output_text", "x" * 70_000)

    class Subclass(ProviderResponse):
        pass

    for value in (
        None,
        {"stop_kind": "end_turn"},
        mutated_usage,
        wrong_usage_type,
        mutated_text,
        Subclass(
            stop_kind=StopKind.END_TURN, output_text="{}", model_used=MODEL, usage=ModelUsage(0, 0)
        ),
    ):
        stub = Stub(returning(value))
        outcome = call_validated(stub, request())
        assert outcome.outcome is CallOutcome.PROVIDER_FAILED
        assert outcome.dispatched and outcome.model_used is None and outcome.usage is None
        assert stub.calls == 1


@pytest.mark.parametrize(
    ("stop_kind", "expected"),
    [
        (StopKind.REFUSAL, CallOutcome.REFUSAL),
        (StopKind.MAX_TOKENS, CallOutcome.MAX_TOKENS),
        (StopKind.OTHER, CallOutcome.UNEXPECTED_STOP),
    ],
)
def test_non_success_stop_kinds(stop_kind: StopKind, expected: CallOutcome) -> None:
    outcome = call_validated(Stub(returning(response(stop_kind=stop_kind))), request())
    assert outcome.outcome is expected and outcome.output is None
    assert outcome.model_used == MODEL and outcome.usage == ModelUsage(3, 4)


@pytest.mark.parametrize("stop_kind", list(StopKind))
def test_model_mismatch_wins_over_every_stop_kind(stop_kind: StopKind) -> None:
    stub = Stub(returning(response(stop_kind=stop_kind, model_used="other-model")))
    outcome = call_validated(stub, request())
    assert outcome.outcome is CallOutcome.MODEL_MISMATCH
    assert outcome.model_used == "other-model" and outcome.output is None
    assert outcome.usage == ModelUsage(3, 4)


def test_invalid_output_keeps_accounting_but_no_output() -> None:
    outcome = call_validated(Stub(returning(response(output_text="{not json"))), request())
    assert outcome.outcome is CallOutcome.INVALID_OUTPUT
    assert outcome.output is None and outcome.model_used == MODEL


def test_a_slow_response_past_timeout_ms_is_classified_normally() -> None:
    outcome = call_validated(Stub(), request(timeout_ms=1000), clock=Clock(0.0, 200.0))
    assert outcome.outcome is CallOutcome.COMPLETED and outcome.latency_ms == 200_000


def test_every_outcome_through_the_scripted_fake() -> None:
    from evidenceguard_agents import scripted

    steps = (
        scripted.Respond(VERIFIER_JSON, ModelUsage(5, 6)),
        scripted.Respond("not json"),
        scripted.Refuse(),
        scripted.StopMaxTokens("{"),
        scripted.StopOther(),
        scripted.Timeout(),
        scripted.Fail(),
        scripted.WrongModel("other-model", VERIFIER_JSON),
    )
    fake = ScriptedFakeProvider(scripts={("verifier", "RET-01"): steps})
    expected = [
        CallOutcome.COMPLETED,
        CallOutcome.INVALID_OUTPUT,
        CallOutcome.REFUSAL,
        CallOutcome.MAX_TOKENS,
        CallOutcome.UNEXPECTED_STOP,
        CallOutcome.TIMEOUT,
        CallOutcome.PROVIDER_FAILED,
        CallOutcome.MODEL_MISMATCH,
        CallOutcome.PROVIDER_FAILED,  # exhausted: the last step is never repeated
    ]
    seen = [call_validated(fake, request()).outcome for _ in expected]
    assert seen == expected
    assert fake.calls_for("verifier", "RET-01") == len(steps)


# --- call_validated: clock -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "start",
    [
        -1e308,
        10**1000,
        CLOCK_READING_BOUND + 1,
        float("nan"),
        float("inf"),
        True,
        "now",
        None,
        OverflowError("boom"),
        RuntimeError(CANARY),
    ],
)
def test_an_invalid_start_reading_raises_before_dispatch(start: object) -> None:
    stub = Stub()
    with pytest.raises(ModelClockError) as caught:
        call_validated(stub, request(), clock=Clock(start))
    assert_fixed(caught.value, ModelClockError)
    assert stub.calls == 0
    assert CANARY not in "".join(traceback.format_exception(caught.value))


@pytest.mark.parametrize("start", [CLOCK_READING_BOUND, -CLOCK_READING_BOUND])
def test_boundary_start_readings_are_usable(start: int) -> None:
    outcome = call_validated(Stub(), request(), clock=Clock(start, start))
    assert outcome.outcome is CallOutcome.COMPLETED and outcome.latency_ms == 0


@pytest.mark.parametrize(
    "end",
    [
        1e308,
        10**1000,
        float("nan"),
        float("inf"),
        True,
        "later",
        OverflowError("boom"),
        ValueError(CANARY),
        0.5,  # backwards from a start of 1.0
        1.0 + LATENCY_MS_BOUND / 1000 + 1,  # elapsed duration above the latency bound
    ],
)
def test_a_post_dispatch_clock_problem_keeps_the_outcome(end: object) -> None:
    stub = Stub()
    outcome = call_validated(stub, request(), clock=Clock(1.0, end))
    assert outcome.outcome is CallOutcome.COMPLETED
    assert outcome.output == verifier_output()
    assert outcome.latency_ms is None
    assert stub.calls == 1


def test_latency_at_the_bound_is_kept() -> None:
    outcome = call_validated(Stub(), request(), clock=Clock(0, LATENCY_MS_BOUND // 1000))
    assert outcome.latency_ms == LATENCY_MS_BOUND


def test_a_post_dispatch_clock_problem_keeps_failure_outcomes_too() -> None:
    stub = Stub(raising(ModelCallTimeout()))
    outcome = call_validated(stub, request(), clock=Clock(1.0, OverflowError()))
    assert outcome.outcome is CallOutcome.TIMEOUT and outcome.latency_ms is None


@pytest.mark.parametrize("error", [KeyboardInterrupt(), SystemExit(3)])
def test_process_control_from_the_clock_propagates_as_the_same_object(
    error: BaseException,
) -> None:
    stub = Stub()
    with pytest.raises(type(error)) as caught:
        call_validated(stub, request(), clock=Clock(error))
    assert caught.value is error and stub.calls == 0
    stub = Stub()
    with pytest.raises(type(error)) as caught:
        call_validated(stub, request(), clock=Clock(1.0, error))
    assert caught.value is error and stub.calls == 1


@pytest.mark.parametrize("error", [KeyboardInterrupt(), SystemExit(3)])
def test_process_control_from_the_provider_propagates_as_the_same_object(
    error: BaseException,
) -> None:
    stub = Stub(provider_id=error)
    with pytest.raises(type(error)) as caught:
        call_validated(stub, request())
    assert caught.value is error and stub.calls == 0
    stub = Stub(raising(error))
    with pytest.raises(type(error)) as caught:
        call_validated(stub, request())
    assert caught.value is error and stub.calls == 1


# --- privacy -------------------------------------------------------------------------------------


def test_nothing_logs_and_no_text_reaches_representations(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    text = json.dumps({"verdict": "supported", "claims": [], "rationale": CANARY})
    value = request(user_text=f"evidence {CANARY}")
    fake = ScriptedFakeProvider(
        scripts={("verifier", "RET-01"): (Respond(text), Respond(f"{CANARY} not json"))}
    )
    completed = call_validated(fake, value)
    invalid = call_validated(fake, value)
    assert completed.outcome is CallOutcome.COMPLETED
    assert invalid.outcome is CallOutcome.INVALID_OUTPUT
    shown = " ".join(
        [repr(value), str(value), repr(completed), str(completed), repr(invalid), repr(fake)]
        + [repr(record) for record in fake.history]
        + [repr(completed.output), str(completed.output)]
    )
    assert CANARY not in shown
    assert not caplog.records


def test_model_call_timeout_carries_nothing() -> None:
    error = ModelCallTimeout()
    assert str(error) == "model_call_timeout" and error.args == ("model_call_timeout",)
