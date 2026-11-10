"""M5h (ADR-0026): the Anthropic adapter over scripted, test-owned transports. No network.

Every body here is synthetic and hand-written; no captured live response is used. Expected
bytes, codes and outcomes are stated explicitly rather than derived from the implementation.
"""

import dataclasses
import json
from collections.abc import Callable
from typing import Any

import pytest

import evidenceguard_agents.anthropic as anthropic
from evidenceguard_agents.anthropic import (
    AnthropicError,
    AnthropicErrorCode,
    AnthropicProvider,
    AnthropicResponse,
    build_request_body,
    parse_response,
)
from evidenceguard_agents.providers import ModelCallTimeout, call_validated
from evidenceguard_domain.model_calls import (
    CallOutcome,
    ModelPurpose,
    ModelUsage,
    PromptRef,
    ProviderResponse,
    StopKind,
    StructuredRequest,
)

C = AnthropicErrorCode
MODEL = "claude-test-model-1"
OTHER_MODEL = "claude-other-model-2"
SENTINEL = "sentinel-p228-do-not-leak"
PROMPT = PromptRef(prompt_id="verifier", version=1, sha256="1" * 64)
VERIFIER_JSON = (
    '{"verdict": "supported", "claims": [{"text": "c", "citations": '
    '[{"chunk_id": "00000000-0000-0000-0000-000000000001", "quote": "q"}]}], "rationale": "r"}'
)


def request(**changes: Any) -> StructuredRequest:
    values: dict[str, Any] = {
        "purpose": ModelPurpose.VERIFIER,
        "prompt": PROMPT,
        "model_id": MODEL,
        "question_id": "RET-01",
        "system_text": "System text.",
        "user_text": "User text.",
        "max_output_tokens": 2048,
        "timeout_ms": 30_000,
    }
    values.update(changes)
    return StructuredRequest(**values)


class Scripted:
    """A test-owned transport: records each call and returns or raises a scripted value."""

    def __init__(self, outcome: object) -> None:
        self.outcome = outcome
        self.calls: list[tuple[bytes, int]] = []

    def post(self, body: bytes, *, timeout_ms: int) -> AnthropicResponse:
        self.calls.append((body, timeout_ms))
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome  # type: ignore[return-value]


def message(**changes: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "id": "msg_synthetic_01",
        "type": "message",
        "role": "assistant",
        "model": MODEL,
        "content": [{"type": "text", "text": VERIFIER_JSON}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 12, "output_tokens": 34},
    }
    document.update(changes)
    return document


def ok(document: object) -> AnthropicResponse:
    return AnthropicResponse(200, json.dumps(document).encode("utf-8"))


def raw(status: int, body: bytes) -> AnthropicResponse:
    return AnthropicResponse(status, body)


def bypass(status: object, body: object) -> AnthropicResponse:
    value = object.__new__(AnthropicResponse)
    object.__setattr__(value, "status", status)
    object.__setattr__(value, "body", body)
    return value


def envelope(kind: str = "api_error", **extra: Any) -> bytes:
    document: dict[str, Any] = {
        "type": "error",
        "error": {"type": kind, "message": "Synthetic message."},
        "request_id": "req_synthetic_01",
    }
    document.update(extra)
    return json.dumps(document).encode("utf-8")


def assert_fixed(error: BaseException, code: AnthropicErrorCode) -> None:
    assert type(error) is AnthropicError
    assert error.code is code
    assert str(error) == code.value and error.args == (code.value,)
    assert error.__cause__ is None and error.__context__ is None
    assert not getattr(error, "__notes__", None)


def fails(code: AnthropicErrorCode, action: Callable[[], object]) -> AnthropicError:
    with pytest.raises(AnthropicError) as info:
        action()
    assert_fixed(info.value, code)
    return info.value


def times_out(action: Callable[[], object]) -> None:
    with pytest.raises(ModelCallTimeout) as info:
        action()
    assert type(info.value) is ModelCallTimeout
    assert info.value.__cause__ is None and info.value.__context__ is None


# --- constants, codes and errors ---------------------------------------------------------------


def test_the_public_constants_are_the_accepted_values() -> None:
    assert anthropic.ANTHROPIC_PROVIDER_ID == "anthropic"
    assert anthropic.ANTHROPIC_API_VERSION == "2026-10-21"
    assert anthropic.ANTHROPIC_HOST == "api.anthropic.com"
    assert anthropic.ANTHROPIC_PATH == "/v1/messages"
    assert anthropic.MAX_REQUEST_BYTES == 4_194_304
    assert anthropic.MAX_RESPONSE_BYTES == 1_048_576
    assert anthropic.MAX_ERROR_BODY_BYTES == 65_536
    assert anthropic.MAX_JSON_DEPTH == 16
    assert anthropic.MAX_JSON_INTEGER_DIGITS == 20
    assert anthropic.MAX_CONTENT_BLOCKS == 64
    assert not hasattr(anthropic, "RETRYABLE_CODES")


def test_the_error_codes_are_exactly_the_accepted_nineteen() -> None:
    assert [(member.name, member.value) for member in AnthropicErrorCode] == [
        ("CONFIGURATION", "anthropic_configuration"),
        ("INVALID_REQUEST", "anthropic_invalid_request"),
        ("REQUEST_TOO_LARGE", "anthropic_request_too_large"),
        ("CLOCK_FAILED", "anthropic_clock_failed"),
        ("TIMEOUT", "anthropic_timeout"),
        ("TRANSPORT_FAILED", "anthropic_transport_failed"),
        ("MALFORMED_RESPONSE", "anthropic_malformed_response"),
        ("RESPONSE_TOO_LARGE", "anthropic_response_too_large"),
        ("OUTPUT_TOO_LARGE", "anthropic_output_too_large"),
        ("REQUEST_REJECTED", "anthropic_request_rejected"),
        ("AUTHENTICATION", "anthropic_authentication"),
        ("BILLING", "anthropic_billing"),
        ("PERMISSION", "anthropic_permission"),
        ("NOT_FOUND", "anthropic_not_found"),
        ("CONFLICT", "anthropic_conflict"),
        ("PAYLOAD_TOO_LARGE", "anthropic_payload_too_large"),
        ("RATE_LIMITED", "anthropic_rate_limited"),
        ("SERVER_ERROR", "anthropic_server_error"),
        ("UNEXPECTED_STATUS", "anthropic_unexpected_status"),
    ]


def test_an_error_carries_only_its_code() -> None:
    error = AnthropicError(C.RATE_LIMITED)
    assert str(error) == "anthropic_rate_limited"
    assert error.args == ("anthropic_rate_limited",)
    assert type(error.args[0]) is str
    assert repr(error) == "AnthropicError('anthropic_rate_limited')"
    assert error.code is C.RATE_LIMITED
    assert set(vars(error)) == {"code"}


@pytest.mark.parametrize("code", ["anthropic_timeout", CallOutcome.TIMEOUT, None, 1])
def test_an_error_refuses_anything_but_a_member(code: object) -> None:
    with pytest.raises(TypeError) as info:
        AnthropicError(code)  # type: ignore[arg-type]
    assert str(info.value) == "code must be an AnthropicErrorCode"


def test_model_call_timeout_keeps_its_m5a_representation() -> None:
    error = ModelCallTimeout()
    assert str(error) == "model_call_timeout"
    assert repr(error) == "ModelCallTimeout('model_call_timeout')"


# --- the request -------------------------------------------------------------------------------


def test_the_request_body_is_the_exact_canonical_bytes() -> None:
    assert build_request_body(request()) == (
        b'{"max_tokens":2048,"messages":[{"content":"User text.","role":"user"}],'
        b'"model":"claude-test-model-1","system":"System text."}'
    )


def test_the_request_body_escapes_to_ascii_and_omits_every_other_field() -> None:
    body = build_request_body(request(system_text="Café\n", user_text="雪 \x01 \U0001f600"))
    assert body == (
        b'{"max_tokens":2048,"messages":[{"content":"\\u96ea \\u0001 \\ud83d\\ude00",'
        b'"role":"user"}],"model":"claude-test-model-1","system":"Caf\\u00e9\\n"}'
    )
    document = json.loads(body)
    assert set(document) == {"max_tokens", "messages", "model", "system"}
    for omitted in ("temperature", "top_p", "top_k", "stream", "tools", "thinking", "metadata"):
        assert omitted.encode() not in body


def test_the_maximal_request_serializes_to_exactly_2784148_bytes() -> None:
    maximal = request(
        model_id="a" * 64,
        system_text="\x01" * 64_000,
        user_text="\x01" * 400_000,
        max_output_tokens=8192,
    )
    assert len(build_request_body(maximal)) == 2_784_148


class _SubRequest(StructuredRequest):
    pass


def _bypass_request() -> StructuredRequest:
    value = request()
    built = object.__new__(StructuredRequest)
    for field in dataclasses.fields(StructuredRequest):
        object.__setattr__(built, field.name, getattr(value, field.name))
    object.__setattr__(built, "system_text", "")  # invalid: rebuilding refuses it
    return built


def _altered_digest() -> StructuredRequest:
    value = request()
    object.__setattr__(value, "request_sha256", "0" * 64)
    return value


@pytest.mark.parametrize(
    "make",
    [
        lambda: {"model_id": MODEL},
        lambda: _SubRequest(
            **{f.name: getattr(request(), f.name) for f in dataclasses.fields(request()) if f.init}
        ),
        _bypass_request,
        _altered_digest,
    ],
    ids=["wrong-type", "subclass", "bypass-built", "altered-digest"],
)
def test_an_invalid_request_is_refused_with_zero_transport_calls(
    make: Callable[[], object],
) -> None:
    transport = Scripted(ok(message()))
    provider = AnthropicProvider(transport)
    fails(C.INVALID_REQUEST, lambda: provider.generate(make()))  # type: ignore[arg-type]
    fails(C.INVALID_REQUEST, lambda: build_request_body(make()))  # type: ignore[arg-type]
    assert transport.calls == []


def test_a_body_over_the_cap_is_refused_before_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = Scripted(ok(message()))
    monkeypatch.setattr(anthropic, "MAX_REQUEST_BYTES", 100)
    fails(C.REQUEST_TOO_LARGE, lambda: AnthropicProvider(transport).generate(request()))
    assert transport.calls == []


def test_a_valid_dispatch_makes_exactly_one_call_with_the_request_timeout() -> None:
    transport = Scripted(ok(message()))
    response = AnthropicProvider(transport).generate(request(timeout_ms=4_321))
    assert len(transport.calls) == 1
    assert transport.calls[0] == (build_request_body(request()), 4_321)
    assert response.stop_kind is StopKind.END_TURN and response.output_text == VERIFIER_JSON


# --- the provider value ------------------------------------------------------------------------


def test_the_provider_has_a_fixed_identity_and_a_safe_representation() -> None:
    provider = AnthropicProvider(Scripted(None))
    assert provider.provider_id == "anthropic"
    assert repr(provider) == str(provider) == "AnthropicProvider()"
    assert [field.name for field in dataclasses.fields(AnthropicProvider)] == ["transport"]


class _RaisingPost:
    def __init__(self, error: BaseException) -> None:
        self.error = error

    @property
    def post(self) -> object:
        raise self.error


@pytest.mark.parametrize(
    "transport, unknown",
    [
        (object(), {}),
        (type("NotCallable", (), {"post": 1})(), {}),
        (_RaisingPost(RuntimeError(SENTINEL)), {}),
        (Scripted(None), {"retries": 2}),
    ],
    ids=["no-post", "not-callable", "raising-attribute", "unknown-argument"],
)
def test_an_invalid_provider_configuration_is_refused(
    transport: object, unknown: dict[str, object]
) -> None:
    error = fails(C.CONFIGURATION, lambda: AnthropicProvider(transport, **unknown))  # type: ignore[arg-type]
    assert SENTINEL not in repr(error)


def test_process_control_while_reading_post_propagates_as_the_same_object() -> None:
    interrupt = KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt) as info:
        AnthropicProvider(_RaisingPost(interrupt))  # type: ignore[arg-type]
    assert info.value is interrupt


# --- transport failures (G1-G3) ----------------------------------------------------------------


class _CustomControl(BaseException):
    pass


@pytest.mark.parametrize("control", [KeyboardInterrupt(), SystemExit(3), _CustomControl()])
def test_process_control_from_the_transport_propagates_as_the_same_object(
    control: BaseException,
) -> None:
    with pytest.raises(BaseException) as info:
        AnthropicProvider(Scripted(control)).generate(request())
    assert info.value is control


@pytest.mark.parametrize("raised", [ModelCallTimeout(), AnthropicError(C.TIMEOUT)])
def test_a_transport_timeout_becomes_a_fresh_model_call_timeout(raised: Exception) -> None:
    with pytest.raises(ModelCallTimeout) as info:
        AnthropicProvider(Scripted(raised)).generate(request())
    assert info.value is not raised
    assert info.value.__cause__ is None and info.value.__context__ is None


@pytest.mark.parametrize(
    "code",
    [
        C.CONFIGURATION,
        C.CLOCK_FAILED,
        C.TRANSPORT_FAILED,
        C.MALFORMED_RESPONSE,
        C.RESPONSE_TOO_LARGE,
    ],
)
def test_a_kept_transport_code_is_kept_in_a_fresh_error(code: AnthropicErrorCode) -> None:
    raised = AnthropicError(code)
    error = fails(code, lambda: AnthropicProvider(Scripted(raised)).generate(request()))
    assert error is not raised


class _UnreadableCode(AnthropicError):
    @property
    def code(self) -> AnthropicErrorCode:
        raise RuntimeError(SENTINEL)

    @code.setter
    def code(self, value: AnthropicErrorCode) -> None:
        pass


def _deleted_code() -> AnthropicError:
    error = AnthropicError(C.CONFIGURATION)
    del error.code
    return error


@pytest.mark.parametrize(
    "make",
    [
        lambda: AnthropicError(C.RATE_LIMITED),
        lambda: AnthropicError(C.OUTPUT_TOO_LARGE),
        lambda: AnthropicError(C.INVALID_REQUEST),
        lambda: _UnreadableCode(C.CONFIGURATION),
        _deleted_code,
        lambda: RuntimeError(SENTINEL),
        lambda: OSError(SENTINEL),
    ],
    ids=["status-code", "output-code", "request-code", "unreadable", "deleted", "runtime", "os"],
)
def test_any_other_transport_failure_is_transport_failed(make: Callable[[], Exception]) -> None:
    error = fails(
        C.TRANSPORT_FAILED, lambda: AnthropicProvider(Scripted(make())).generate(request())
    )
    assert SENTINEL not in repr(error)


# --- response admission (clarification A, G4-G6) -----------------------------------------------


def test_the_response_value_validates_and_represents_safely() -> None:
    response = AnthropicResponse(429, SENTINEL.encode())
    assert repr(response) == str(response) == "AnthropicResponse(status=429, body_bytes=25)"
    assert AnthropicResponse(status=200, body=b"") == AnthropicResponse(200, b"")
    assert len(AnthropicResponse(200, b"x" * 1_048_576).body) == 1_048_576
    fails(C.RESPONSE_TOO_LARGE, lambda: AnthropicResponse(200, b"x" * 1_048_577))
    for status in (True, 99, 600, 200.0, "200"):
        fails(C.MALFORMED_RESPONSE, lambda status=status: AnthropicResponse(status, b""))  # type: ignore[misc]
    for body in (bytearray(b"{}"), memoryview(b"{}"), "{}", None):
        fails(C.MALFORMED_RESPONSE, lambda body=body: AnthropicResponse(200, body))  # type: ignore[misc]


class _SubResponse(AnthropicResponse):
    pass


def _unreadable() -> AnthropicResponse:
    return object.__new__(AnthropicResponse)  # no fields at all


@pytest.mark.parametrize(
    "make, code",
    [
        (lambda: {"status": 200, "body": b"{}"}, C.MALFORMED_RESPONSE),
        (lambda: _SubResponse(200, json.dumps(message()).encode()), C.MALFORMED_RESPONSE),
        (_unreadable, C.MALFORMED_RESPONSE),
        (lambda: bypass(True, b"{}"), C.MALFORMED_RESPONSE),
        (lambda: bypass(99, b""), C.MALFORMED_RESPONSE),
        (lambda: bypass(600, b""), C.MALFORMED_RESPONSE),
        (lambda: bypass(200, bytearray(b"{}")), C.MALFORMED_RESPONSE),
        (lambda: bypass(200, memoryview(b"{}")), C.MALFORMED_RESPONSE),
        (lambda: bypass(200, "{}"), C.MALFORMED_RESPONSE),
        (lambda: bypass(504, bytearray(b"")), C.MALFORMED_RESPONSE),
        (lambda: bypass(504, None), C.MALFORMED_RESPONSE),
        (lambda: bypass(504, b"x" * 1_048_577), C.RESPONSE_TOO_LARGE),
        (lambda: bypass(200, b"x" * 1_048_577), C.RESPONSE_TOO_LARGE),
        (lambda: bypass(429, b"x" * 1_048_577), C.RESPONSE_TOO_LARGE),
    ],
    ids=[
        "dict",
        "subclass",
        "unreadable",
        "bool-status",
        "status-99",
        "status-600",
        "bytearray",
        "memoryview",
        "str",
        "504-bytearray",
        "504-none",
        "504-oversized",
        "200-oversized",
        "429-oversized",
    ],
)
def test_admission_precedes_status_classification(
    make: Callable[[], object], code: AnthropicErrorCode
) -> None:
    fails(code, lambda: parse_response(make()))  # type: ignore[arg-type]
    fails(code, lambda: AnthropicProvider(Scripted(make())).generate(request()))


# --- statuses and error envelopes (G7-G11) ------------------------------------------------------


@pytest.mark.parametrize(
    "status, code",
    [
        (400, C.REQUEST_REJECTED),
        (401, C.AUTHENTICATION),
        (402, C.BILLING),
        (403, C.PERMISSION),
        (404, C.NOT_FOUND),
        (409, C.CONFLICT),
        (413, C.PAYLOAD_TOO_LARGE),
        (429, C.RATE_LIMITED),
        (500, C.SERVER_ERROR),
        (501, C.SERVER_ERROR),
        (503, C.SERVER_ERROR),
        (529, C.SERVER_ERROR),
        (599, C.SERVER_ERROR),
        (100, C.UNEXPECTED_STATUS),
        (201, C.UNEXPECTED_STATUS),
        (204, C.UNEXPECTED_STATUS),
        (301, C.UNEXPECTED_STATUS),
        (302, C.UNEXPECTED_STATUS),
        (405, C.UNEXPECTED_STATUS),
        (422, C.UNEXPECTED_STATUS),
        (499, C.UNEXPECTED_STATUS),
    ],
)
def test_each_status_maps_to_its_code(status: int, code: AnthropicErrorCode) -> None:
    fails(code, lambda: parse_response(raw(status, envelope("api_error"))))
    fails(code, lambda: parse_response(raw(status, b"")))


def _sized_envelope(kind: str, size: int) -> bytes:
    base = envelope(kind, request_id="")
    body = envelope(kind, request_id="p" * (size - len(base)))
    assert len(body) == size
    return body


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"{",
        b"not json",
        envelope("api_error"),
        envelope("overloaded_error"),
        envelope("timeout_error"),
        _sized_envelope("api_error", 65_537),
        _sized_envelope("api_error", 1_048_576),
    ],
    ids=["empty", "brace", "text", "api", "overloaded", "timeout", "over-inspection", "at-cap"],
)
def test_an_admitted_504_is_a_timeout_whatever_its_admitted_body(body: bytes) -> None:
    times_out(lambda: parse_response(raw(504, body)))


@pytest.mark.parametrize("status", [400, 429, 500, 529])
def test_a_valid_timeout_error_envelope_is_a_timeout_under_another_status(status: int) -> None:
    times_out(lambda: parse_response(raw(status, envelope("timeout_error"))))


@pytest.mark.parametrize("kind", ["api_error", "rate_limit_error", "a_brand_new_error_type"])
def test_an_ordinary_or_unknown_envelope_keeps_the_status(kind: str) -> None:
    fails(C.RATE_LIMITED, lambda: parse_response(raw(429, envelope(kind))))


TIMEOUT_DEFECTS = {
    "invalid-utf8": b'{"type":"error","error":{"type":"timeout_error","message":"\xff"}}',
    "bom": b'\xef\xbb\xbf{"type":"error","error":{"type":"timeout_error"}}',
    "malformed": b'{"type":"error","error":{"type":"timeout_error"}',
    "duplicate-top": b'{"type":"error","type":"error","error":{"type":"timeout_error"}}',
    "duplicate-nested": b'{"type":"error","error":{"type":"timeout_error","type":"timeout_error"}}',
    "duplicate-ignored": (
        b'{"type":"error","error":{"type":"timeout_error"},"request_id":"a","request_id":"b"}'
    ),
    "nan": b'{"type":"error","error":{"type":"timeout_error"},"x":NaN}',
    "infinity": b'{"type":"error","error":{"type":"timeout_error"},"x":-Infinity}',
    "overflow": b'{"type":"error","error":{"type":"timeout_error"},"x":1e999}',
    "long-integer": b'{"type":"error","error":{"type":"timeout_error"},"x":123456789012345678901}',
    "too-deep": (
        b'{"type":"error","error":{"type":"timeout_error"},"x":' + b"[" * 16 + b"]" * 16 + b"}"
    ),
    "trailing": b'{"type":"error","error":{"type":"timeout_error"}} x',
    "not-object": b'[{"type":"error","error":{"type":"timeout_error"}}]',
    "type-not-error": b'{"type":"Error","error":{"type":"timeout_error"}}',
    "type-missing": b'{"error":{"type":"timeout_error"}}',
    "type-not-string": b'{"type":1,"error":{"type":"timeout_error"}}',
    "error-missing": b'{"type":"error","timeout_error":true}',
    "error-not-object": b'{"type":"error","error":"timeout_error"}',
    "error-type-missing": b'{"type":"error","error":{"kind":"timeout_error"}}',
    "error-type-not-string": b'{"type":"error","error":{"type":["timeout_error"]}}',
    "error-type-pattern": b'{"type":"error","error":{"type":"Timeout_Error"}}',
    "error-type-hyphen": b'{"type":"error","error":{"type":"timeout-error"}}',
}


@pytest.mark.parametrize("name", sorted(TIMEOUT_DEFECTS))
@pytest.mark.parametrize("status, code", [(429, C.RATE_LIMITED), (500, C.SERVER_ERROR)])
def test_an_unusable_timeout_envelope_is_no_envelope_and_keeps_the_status(
    name: str, status: int, code: AnthropicErrorCode
) -> None:
    fails(code, lambda: parse_response(raw(status, TIMEOUT_DEFECTS[name])))


def test_a_valid_envelope_within_the_inspection_depth_is_still_inspected() -> None:
    body = b'{"type":"error","error":{"type":"timeout_error"},"x":' + b"[" * 14 + b"]" * 14 + b"}"
    times_out(lambda: parse_response(raw(429, body)))


def test_the_error_inspection_cap_is_exact() -> None:
    times_out(lambda: parse_response(raw(429, _sized_envelope("timeout_error", 65_536))))
    fails(
        C.RATE_LIMITED, lambda: parse_response(raw(429, _sized_envelope("timeout_error", 65_537)))
    )
    fails(
        C.RATE_LIMITED,
        lambda: parse_response(raw(429, _sized_envelope("timeout_error", 1_048_576))),
    )


# --- status 200: the envelope (V1-V3) -----------------------------------------------------------


def test_a_valid_end_turn_message_becomes_a_provider_response() -> None:
    response = parse_response(ok(message()))
    assert type(response) is ProviderResponse
    assert response.stop_kind is StopKind.END_TURN
    assert response.output_text == VERIFIER_JSON
    assert response.model_used == MODEL
    assert response.usage == ModelUsage(12, 34)


def _without(key: str) -> dict[str, Any]:
    document = message()
    del document[key]
    return document


ENVELOPE_DEFECTS: dict[str, object] = {
    "not-object": [message()],
    "type-wrong": message(type="error"),
    "type-missing": _without("type"),
    "type-not-string": message(type=["message"]),
    "role-wrong": message(role="user"),
    "role-missing": _without("role"),
    "model-missing": _without("model"),
    "model-not-string": message(model=7),
    "model-uppercase": message(model="Claude-Test"),
    "model-too-long": message(model="a" * 65),
    "stop-null": message(stop_reason=None),
    "stop-missing": _without("stop_reason"),
    "stop-not-string": message(stop_reason=1),
    "stop-pattern": message(stop_reason="End_Turn"),
    "stop-too-long": message(stop_reason="a" * 65),
    "content-missing": _without("content"),
    "content-not-list": message(content={"type": "text", "text": "x"}),
    "content-65-blocks": message(content=[{"type": "thinking"}] * 65),
    "block-not-object": message(content=["text"]),
    "block-type-missing": message(content=[{"text": "x"}]),
    "block-type-not-string": message(content=[{"type": 1}]),
    "block-type-pattern": message(content=[{"type": "Text"}]),
    "usage-missing": _without("usage"),
    "usage-not-object": message(usage=[12, 34]),
    "input-missing": message(usage={"output_tokens": 1}),
    "output-missing": message(usage={"input_tokens": 1}),
    "input-bool": message(usage={"input_tokens": True, "output_tokens": 1}),
    "input-float": message(usage={"input_tokens": 1.0, "output_tokens": 1}),
    "input-negative": message(usage={"input_tokens": -1, "output_tokens": 1}),
    "output-too-large": message(usage={"input_tokens": 1, "output_tokens": 10_000_001}),
    "input-string": message(usage={"input_tokens": "1", "output_tokens": 1}),
}


@pytest.mark.parametrize("stop", ["end_turn", "refusal", "max_tokens", "pause_turn"])
@pytest.mark.parametrize("name", sorted(ENVELOPE_DEFECTS))
def test_an_envelope_defect_is_malformed_under_every_stop_reason(name: str, stop: str) -> None:
    document = ENVELOPE_DEFECTS[name]
    if isinstance(document, dict) and "stop_reason" in document and not name.startswith("stop"):
        document = {**document, "stop_reason": stop}
    fails(C.MALFORMED_RESPONSE, lambda: parse_response(ok(document)))


def test_the_usage_bounds_are_inclusive() -> None:
    response = parse_response(ok(message(usage={"input_tokens": 0, "output_tokens": 10_000_000})))
    assert response.usage == ModelUsage(0, 10_000_000)


def test_content_may_hold_exactly_64_blocks() -> None:
    blocks = [{"type": "thinking", "thinking": "t"}] * 63 + [{"type": "text", "text": "x"}]
    assert parse_response(ok(message(content=blocks))).output_text == "x"


@pytest.mark.parametrize("body", [b"", b"   ", b"null", b"[]", b'"message"'])
def test_a_200_body_that_is_not_a_json_object_is_malformed(body: bytes) -> None:
    fails(C.MALFORMED_RESPONSE, lambda: parse_response(raw(200, body)))


def test_a_200_error_envelope_is_malformed() -> None:
    fails(C.MALFORMED_RESPONSE, lambda: parse_response(raw(200, envelope("timeout_error"))))


def test_ignored_fields_are_neither_required_nor_inspected() -> None:
    document = message(
        stop_details={"type": "anything", "nested": [1.5, {"deep": None}], "x": SENTINEL},
        container=None,
        some_future_field={"a": [1, 2, 3]},
        usage={
            "input_tokens": 1,
            "output_tokens": 2,
            "cache_creation_input_tokens": 3,
            "cache_read_input_tokens": 4.5,
            "service_tier": "standard",
        },
    )
    del document["id"]
    del document["stop_sequence"]
    response = parse_response(ok(document))
    assert response.usage == ModelUsage(1, 2)
    assert SENTINEL not in repr(response)


# --- status 200: stop mapping and blocks (V4-V9) ------------------------------------------------


@pytest.mark.parametrize(
    "reason, kind",
    [
        ("refusal", StopKind.REFUSAL),
        ("max_tokens", StopKind.MAX_TOKENS),
        ("model_context_window_exceeded", StopKind.OTHER),
        ("stop_sequence", StopKind.OTHER),
        ("tool_use", StopKind.OTHER),
        ("pause_turn", StopKind.OTHER),
        ("a_brand_new_reason", StopKind.OTHER),
    ],
)
def test_other_stop_reasons_map_and_carry_no_text(reason: str, kind: StopKind) -> None:
    response = parse_response(ok(message(stop_reason=reason)))
    assert response.stop_kind is kind and response.output_text == ""


@pytest.mark.parametrize(
    "stop, kind",
    [
        ("refusal", StopKind.REFUSAL),
        ("max_tokens", StopKind.MAX_TOKENS),
        ("tool_use", StopKind.OTHER),
    ],
)
@pytest.mark.parametrize(
    "content",
    [
        [{"type": "tool_use", "id": "t", "name": "n", "input": {}}],
        [{"type": "a_brand_new_block"}],
        [{"type": "text"}],
        [{"type": "text", "text": 1, "citations": [{"x": 1}]}],
        [{"type": "text", "text": "a"}, {"type": "text", "text": "b" * 70_000}],
        [],
    ],
    ids=["tool-use", "unknown", "text-without-text", "bad-text", "two-texts", "empty"],
)
def test_block_payloads_are_not_inspected_outside_end_turn(
    stop: str, kind: StopKind, content: list[dict[str, Any]]
) -> None:
    response = parse_response(ok(message(stop_reason=stop, content=content)))
    assert response.stop_kind is kind and response.output_text == ""


def test_thinking_blocks_are_skipped_under_end_turn() -> None:
    content = [
        {"type": "thinking", "thinking": SENTINEL, "signature": "sig"},
        {"type": "redacted_thinking", "data": SENTINEL},
        {"type": "text", "text": "answer"},
        {"type": "thinking", "thinking": "more"},
    ]
    response = parse_response(ok(message(content=content)))
    assert response.output_text == "answer"
    assert SENTINEL not in repr(response)


@pytest.mark.parametrize("citations", ["absent", None, []], ids=["absent", "null", "empty"])
def test_absent_null_or_empty_citations_are_accepted(citations: object) -> None:
    block: dict[str, Any] = {"type": "text", "text": "answer"}
    if citations != "absent":
        block["citations"] = citations
    assert parse_response(ok(message(content=[block]))).output_text == "answer"


END_TURN_DEFECTS: dict[str, list[dict[str, Any]]] = {
    "no-text": [{"type": "thinking", "thinking": "t"}],
    "empty-content": [],
    "two-texts": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}],
    "tool-use": [{"type": "text", "text": "a"}, {"type": "tool_use", "id": "t", "name": "n"}],
    "server-tool": [{"type": "server_tool_use", "id": "t"}, {"type": "text", "text": "a"}],
    "unknown-block": [{"type": "text", "text": "a"}, {"type": "a_brand_new_block"}],
    "text-missing": [{"type": "text"}],
    "text-not-string": [{"type": "text", "text": ["a"]}],
    "citations-nonempty": [{"type": "text", "text": "a", "citations": [{"type": "x"}]}],
    "citations-string": [{"type": "text", "text": "a", "citations": "x"}],
    "citations-object": [{"type": "text", "text": "a", "citations": {}}],
    "two-texts-one-oversized": [
        {"type": "text", "text": "a"},
        {"type": "text", "text": "b" * 65_537},
    ],
    "unknown-and-oversized": [
        {"type": "text", "text": "b" * 65_537},
        {"type": "a_brand_new_block"},
    ],
}


@pytest.mark.parametrize("name", sorted(END_TURN_DEFECTS))
def test_an_end_turn_block_defect_is_malformed(name: str) -> None:
    fails(C.MALFORMED_RESPONSE, lambda: parse_response(ok(message(content=END_TURN_DEFECTS[name]))))


def test_the_output_text_bound_is_exact_in_utf8_bytes() -> None:
    accepted = "é" * 32_768  # 65,536 UTF-8 bytes
    assert (
        parse_response(ok(message(content=[{"type": "text", "text": accepted}]))).output_text
        == accepted
    )
    refused = message(content=[{"type": "text", "text": "é" * 32_768 + "x"}])  # 65,537 bytes
    fails(C.OUTPUT_TOO_LARGE, lambda: parse_response(ok(refused)))


def test_an_escaped_lone_surrogate_in_the_text_is_malformed() -> None:
    body = (
        b'{"type":"message","role":"assistant","model":"claude-test-model-1",'
        b'"content":[{"type":"text","text":"a\\ud800b"}],"stop_reason":"end_turn",'
        b'"usage":{"input_tokens":1,"output_tokens":1}}'
    )
    fails(C.MALFORMED_RESPONSE, lambda: parse_response(raw(200, body)))
    paired = body.replace(b"\\ud800", b"\\ud83d\\ude00")
    assert parse_response(raw(200, paired)).output_text == "a\U0001f600b"


def test_empty_text_reaches_m5a_as_invalid_output() -> None:
    transport = Scripted(ok(message(content=[{"type": "text", "text": ""}])))
    result = call_validated(
        AnthropicProvider(transport), request(), clock=iter((1.0, 2.0)).__next__
    )
    assert result.outcome is CallOutcome.INVALID_OUTPUT and result.output is None


# --- strict JSON (J1-J7) ------------------------------------------------------------------------


def _body_with(field: bytes) -> bytes:
    """A valid end-turn message with one extra raw ``"x": <field>`` member."""
    return (
        b'{"type":"message","role":"assistant","model":"claude-test-model-1",'
        b'"content":[{"type":"text","text":"ok"}],"stop_reason":"end_turn",'
        b'"usage":{"input_tokens":1,"output_tokens":1},"x":' + field + b"}"
    )


@pytest.mark.parametrize(
    "field",
    [
        b"[" * 15 + b"]" * 15,  # depth 16 in total: the top object plus 15 arrays
        b'"' + b"[{" * 200 + b'"',  # brackets inside a string do not count
        b'"\\"[[[[[[[[[[[[[[[[[[\\\\"',  # escaped quotes and backslashes inside a string
        b"12345678901234567890",
        b"-12345678901234567890",
        b"1.5e300",
        b"-0.0",
        b"[1.25, 2e-5]",
    ],
    ids=[
        "depth-16",
        "brackets-in-string",
        "escapes",
        "20-digits",
        "neg-20-digits",
        "big-float",
        "neg-zero",
        "floats",
    ],
)
def test_strict_json_accepts_bounded_values_in_ignored_fields(field: bytes) -> None:
    assert parse_response(raw(200, _body_with(field))).output_text == "ok"


@pytest.mark.parametrize(
    "field",
    [
        b"[" * 16 + b"]" * 16,  # depth 17
        b"{" + b'"a":{' * 16 + b"}" * 17,
        b"NaN",
        b"Infinity",
        b"-Infinity",
        b"1e999",
        b"-1e999",
        b"[1, 1e400]",
        b"123456789012345678901",
        b"-123456789012345678901",
        b'{"a": 1, "a": 2}',
        b"[1,]",
        b"'single'",
    ],
    ids=[
        "depth-17",
        "object-depth-18",
        "nan",
        "infinity",
        "neg-infinity",
        "1e999",
        "neg-1e999",
        "1e400-in-list",
        "21-digits",
        "neg-21-digits",
        "duplicate-ignored",
        "trailing-comma",
        "single-quotes",
    ],
)
def test_strict_json_refuses_unbounded_values_even_in_ignored_fields(field: bytes) -> None:
    fails(C.MALFORMED_RESPONSE, lambda: parse_response(raw(200, _body_with(field))))


@pytest.mark.parametrize(
    "body",
    [
        b"\xef\xbb\xbf" + _body_with(b"1"),
        _body_with(b'"\xff"'),
        _body_with(b'"\xed\xa0\x80"'),  # an encoded surrogate
        _body_with(b'"\xc0\xaf"'),  # an overlong form
        _body_with(b"1") + b" trailing",
        _body_with(b"1") + b"{}",
        b'{"type":"message","type":"message","role":"assistant","model":"claude-test-model-1",'
        b'"content":[{"type":"text","text":"ok"}],"stop_reason":"end_turn",'
        b'"usage":{"input_tokens":1,"output_tokens":1}}',
        b'{"type":"message","role":"assistant","model":"claude-test-model-1",'
        b'"content":[{"type":"text","text":"ok","text":"other"}],"stop_reason":"end_turn",'
        b'"usage":{"input_tokens":1,"output_tokens":1}}',
    ],
    ids=[
        "bom",
        "invalid-utf8",
        "surrogate-bytes",
        "overlong",
        "trailing-text",
        "trailing-object",
        "duplicate-top",
        "duplicate-nested",
    ],
)
def test_strict_json_refuses_bad_encodings_trailing_data_and_duplicates(body: bytes) -> None:
    fails(C.MALFORMED_RESPONSE, lambda: parse_response(raw(200, body)))


def test_surrounding_json_whitespace_is_allowed() -> None:
    assert parse_response(raw(200, b" \n\t" + _body_with(b"1") + b" \r\n")).output_text == "ok"


def test_a_finite_float_where_an_integer_is_required_is_malformed() -> None:
    body = _body_with(b"1").replace(b'"input_tokens":1', b'"input_tokens":1.0')
    fails(C.MALFORMED_RESPONSE, lambda: parse_response(raw(200, body)))


def test_a_deep_1_mib_body_is_refused_before_the_decoder(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []
    original = json.loads

    def recording(*args: Any, **kwargs: Any) -> Any:
        calls.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr(json, "loads", recording)
    body = b"[" * 524_288 + b"]" * 524_288
    assert len(body) == 1_048_576
    fails(C.MALFORMED_RESPONSE, lambda: parse_response(raw(200, body)))
    # A deep error body within the inspection cap is no envelope: the status decides.
    fails(C.RATE_LIMITED, lambda: parse_response(raw(429, b'{"x":' + b"[" * 30_000)))
    assert calls == []
    assert parse_response(raw(200, _body_with(b"1"))).output_text == "ok"
    assert len(calls) == 1


def test_a_200_body_exactly_at_the_response_cap_is_decoded() -> None:
    base = _body_with(b'""')
    body = _body_with(b'"' + b"p" * (1_048_576 - len(base)) + b'"')
    assert len(body) == 1_048_576
    assert parse_response(raw(200, body)).output_text == "ok"


# --- mismatch precedence through call_validated ------------------------------------------------


@pytest.mark.parametrize("stop", ["end_turn", "refusal", "max_tokens", "pause_turn"])
def test_a_valid_response_from_another_model_is_a_model_mismatch(stop: str) -> None:
    transport = Scripted(ok(message(model=OTHER_MODEL, stop_reason=stop)))
    result = call_validated(
        AnthropicProvider(transport), request(), clock=iter((1.0, 2.0)).__next__
    )
    assert result.outcome is CallOutcome.MODEL_MISMATCH
    assert result.model_used == OTHER_MODEL and result.output is None


@pytest.mark.parametrize("stop", ["end_turn", "refusal", "max_tokens"])
def test_a_malformed_response_from_another_model_is_provider_failed(stop: str) -> None:
    document = message(model=OTHER_MODEL, stop_reason=stop, content=[{"text": "no type"}])
    result = call_validated(AnthropicProvider(Scripted(ok(document))), request())
    assert result.outcome is CallOutcome.PROVIDER_FAILED
    assert result.model_used is None and result.usage is None


@pytest.mark.parametrize(
    "outcome, expected",
    [
        (ok(message()), CallOutcome.COMPLETED),
        (ok(message(stop_reason="refusal")), CallOutcome.REFUSAL),
        (ok(message(stop_reason="max_tokens")), CallOutcome.MAX_TOKENS),
        (ok(message(stop_reason="pause_turn")), CallOutcome.UNEXPECTED_STOP),
        (ok(message(content=[{"type": "text", "text": "not json"}])), CallOutcome.INVALID_OUTPUT),
        (raw(504, b""), CallOutcome.TIMEOUT),
        (raw(429, envelope("timeout_error")), CallOutcome.TIMEOUT),
        (raw(429, envelope("rate_limit_error")), CallOutcome.PROVIDER_FAILED),
        (AnthropicError(C.TIMEOUT), CallOutcome.TIMEOUT),
        (RuntimeError(SENTINEL), CallOutcome.PROVIDER_FAILED),
    ],
)
def test_call_validated_records_the_m5a_outcome(outcome: object, expected: CallOutcome) -> None:
    result = call_validated(
        AnthropicProvider(Scripted(outcome)), request(), clock=iter((1.0, 2.0)).__next__
    )
    assert result.outcome is expected and result.dispatched is True
    assert result.latency_ms == 1000
    if expected is CallOutcome.COMPLETED:
        assert result.output is not None and result.usage == ModelUsage(12, 34)
        assert result.model_used == MODEL


# --- privacy -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "response",
    [
        raw(
            429,
            envelope(
                "api_error", request_id=SENTINEL, error={"type": "api_error", "message": SENTINEL}
            ),
        ),
        raw(400, SENTINEL.encode()),
        raw(200, json.dumps(message(content=[{"type": "tool_use", "name": SENTINEL}])).encode()),
        raw(200, json.dumps(message(model=SENTINEL.replace("-", "_"))).encode()),
        raw(200, json.dumps(message(content=[{"type": "text", "text": SENTINEL * 3000}])).encode()),
    ],
    ids=["envelope", "text-body", "tool-use", "bad-model", "oversized-text"],
)
def test_no_raised_error_carries_submitted_or_received_text(response: AnthropicResponse) -> None:
    with pytest.raises(AnthropicError) as info:
        AnthropicProvider(Scripted(response)).generate(request(user_text=SENTINEL))
    error = info.value
    for text in (str(error), repr(error), repr(error.args)):
        assert SENTINEL not in text
    assert error.__cause__ is None and error.__context__ is None
    assert SENTINEL not in repr(response)


def test_the_provider_keeps_no_state_between_calls() -> None:
    transport = Scripted(ok(message()))
    provider = AnthropicProvider(transport)
    first = provider.generate(request())
    transport.outcome = raw(500, b"")
    fails(C.SERVER_ERROR, lambda: provider.generate(request()))
    transport.outcome = ok(message())
    assert provider.generate(request()) == first
    assert len(transport.calls) == 3
    assert vars(provider) == {"transport": transport}
