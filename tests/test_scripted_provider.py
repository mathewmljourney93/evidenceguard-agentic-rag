"""M5a ``ScriptedFakeProvider``: configuration bounds, step selection, history and privacy
(ADR-0019). No test touches the network (autouse guard)."""

import logging
import socket
import threading
import traceback
from collections.abc import Iterator, Mapping
from typing import Any

import pytest

from evidenceguard_agents import scripted
from evidenceguard_agents.providers import ModelCallTimeout
from evidenceguard_agents.scripted import (
    FAKE_MODEL_ID,
    FAKE_PROVIDER_ID,
    MAX_SCRIPT_KEYS,
    MAX_STEPS_PER_KEY,
    CallRecord,
    Fail,
    Refuse,
    Respond,
    ScriptedFakeError,
    ScriptedFakeProvider,
    StopMaxTokens,
    StopOther,
    Timeout,
    WrongModel,
)
from evidenceguard_domain.model_calls import (
    InvalidModelValueError,
    ModelPurpose,
    ModelUsage,
    PromptRef,
    StopKind,
    StructuredRequest,
)

CANARY = "EG-M5A-CANARY-7731"
KEY = ("verifier", "RET-01")


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: object, **kwargs: object) -> Any:
        raise AssertionError("a test attempted network access")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


def request(prompt_id: str = "verifier", question_id: str = "RET-01") -> StructuredRequest:
    return StructuredRequest(
        purpose=ModelPurpose.VERIFIER,
        prompt=PromptRef(prompt_id=prompt_id, version=1, sha256="1" * 64),
        model_id=FAKE_MODEL_ID,
        question_id=question_id,
        system_text="system",
        user_text="user",
        max_output_tokens=256,
    )


def fake(*steps: scripted.Step, key: tuple[str, str] = KEY) -> ScriptedFakeProvider:
    return ScriptedFakeProvider(scripts={key: steps})


# --- configuration -------------------------------------------------------------------------------


def test_identity() -> None:
    provider = fake(Refuse())
    assert provider.provider_id == FAKE_PROVIDER_ID == "scripted-fake"
    assert provider.model_id == FAKE_MODEL_ID == "fake-scripted-v1"


@pytest.mark.parametrize(
    "scripts",
    [
        {},
        [(KEY, (Refuse(),))],
        {KEY: [Refuse()]},
        {KEY: ()},
        {KEY: (Refuse(),) * (MAX_STEPS_PER_KEY + 1)},
        {KEY: ("respond",)},
        {KEY: (Refuse,)},
        {"verifier": (Refuse(),)},
        {("verifier",): (Refuse(),)},
        {("Verifier", "RET-01"): (Refuse(),)},
        {("verifier", "ret-01"): (Refuse(),)},
        {("verifier", "RET-01", "extra"): (Refuse(),)},
        {("verifier", 1): (Refuse(),)},
        {KEY: (WrongModel(FAKE_MODEL_ID, "{}"),)},  # not a different model
    ],
)
def test_invalid_scripts_are_rejected(scripts: Any) -> None:
    with pytest.raises(InvalidModelValueError):
        ScriptedFakeProvider(scripts=scripts)


def test_script_bounds() -> None:
    keys = {("verifier", f"QQ-{index:03d}"): (Refuse(),) for index in range(MAX_SCRIPT_KEYS)}
    assert ScriptedFakeProvider(scripts=keys)
    keys[("verifier", "QZ-999")] = (Refuse(),)
    with pytest.raises(InvalidModelValueError):
        ScriptedFakeProvider(scripts=keys)
    assert fake(*(Refuse(),) * MAX_STEPS_PER_KEY)
    big = "x" * 65_536
    assert Respond(big).text == big
    with pytest.raises(InvalidModelValueError):
        Respond(big + "x")
    with pytest.raises(InvalidModelValueError):
        StopMaxTokens("\ud800")
    with pytest.raises(InvalidModelValueError):
        Respond(b"{}")  # type: ignore[arg-type]
    # 64 full-size texts are exactly 4 MiB; one more byte anywhere exceeds the total.
    at_limit = {("verifier", f"QQ-{index:03d}"): (Respond(big),) for index in range(64)}
    assert ScriptedFakeProvider(scripts=at_limit)
    at_limit[("verifier", "QZ-999")] = (Respond("x"),)
    with pytest.raises(InvalidModelValueError):
        ScriptedFakeProvider(scripts=at_limit)


def test_step_and_provider_arguments_are_validated() -> None:
    with pytest.raises(InvalidModelValueError):
        Respond("{}", usage=(1, 2))  # type: ignore[arg-type]
    with pytest.raises(InvalidModelValueError):
        WrongModel("Not A Model", "{}")
    with pytest.raises(InvalidModelValueError):
        Refuse(extra=1)
    with pytest.raises(InvalidModelValueError):
        ScriptedFakeProvider(scripts={KEY: (Refuse(),)}, model_id="Bad Model")
    with pytest.raises(InvalidModelValueError):
        ScriptedFakeProvider(scripts={KEY: (Refuse(),)}, unknown=True)


def test_configuration_is_copied() -> None:
    scripts: dict[tuple[str, str], tuple[scripted.Step, ...]] = {KEY: (Refuse(),)}
    provider = ScriptedFakeProvider(scripts=scripts)
    scripts[KEY] = (Fail(),)
    scripts[("verifier", "ENC-01")] = (Fail(),)
    assert provider.generate(request()).stop_kind is StopKind.REFUSAL
    with pytest.raises(ScriptedFakeError):
        provider.generate(request(question_id="ENC-01"))


# --- steps ---------------------------------------------------------------------------------------


def test_each_step_produces_its_response_or_error() -> None:
    provider = fake(
        Respond('{"x":1}', ModelUsage(7, 8)),
        Refuse(),
        StopMaxTokens("partial"),
        StopOther(),
        WrongModel("other-model", "{}"),
        Timeout(),
        Fail(),
    )
    first = provider.generate(request())
    assert (first.stop_kind, first.output_text, first.model_used, first.usage) == (
        StopKind.END_TURN,
        '{"x":1}',
        FAKE_MODEL_ID,
        ModelUsage(7, 8),
    )
    refusal = provider.generate(request())
    assert refusal.stop_kind is StopKind.REFUSAL and refusal.output_text == ""
    limited = provider.generate(request())
    assert limited.stop_kind is StopKind.MAX_TOKENS and limited.output_text == "partial"
    assert provider.generate(request()).stop_kind is StopKind.OTHER
    wrong = provider.generate(request())
    assert wrong.model_used == "other-model" and wrong.stop_kind is StopKind.END_TURN
    with pytest.raises(ModelCallTimeout):
        provider.generate(request())
    with pytest.raises(RuntimeError) as caught:
        provider.generate(request())
    assert type(caught.value) is RuntimeError and str(caught.value) == "scripted_failure"


def test_respond_text_is_returned_verbatim() -> None:
    raw = '  not JSON at all {"verdict": \n'
    assert fake(Respond(raw)).generate(request()).output_text == raw


# --- selection, exhaustion and history ------------------------------------------------------------


def test_missing_keys_and_exhausted_scripts_raise_the_fixed_failure() -> None:
    provider = fake(Respond("{}"), Refuse())
    with pytest.raises(ScriptedFakeError) as caught:
        provider.generate(request(question_id="ENC-01"))
    assert str(caught.value) == "scripted_fake_unavailable"
    assert provider.generate(request()).stop_kind is StopKind.END_TURN
    assert provider.generate(request()).stop_kind is StopKind.REFUSAL
    for _ in range(3):  # the last step is never repeated
        with pytest.raises(ScriptedFakeError):
            provider.generate(request())
    assert provider.calls_for(*KEY) == 2
    assert len(provider.history) == 2


def test_history_records_identifiers_digests_and_indexes_only() -> None:
    provider = ScriptedFakeProvider(
        scripts={KEY: (Respond(CANARY), Refuse()), ("verifier", "ENC-01"): (Refuse(),)}
    )
    provider.generate(request())
    provider.generate(request(question_id="ENC-01"))
    provider.generate(request())
    digest = request().request_sha256
    assert provider.history == (
        CallRecord("verifier", "RET-01", digest, 0),
        CallRecord("verifier", "ENC-01", request(question_id="ENC-01").request_sha256, 0),
        CallRecord("verifier", "RET-01", digest, 1),
    )
    assert type(provider.history) is tuple
    assert CANARY not in repr(provider.history)


def test_the_history_cap_stops_calls_without_recording(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scripted, "MAX_HISTORY", 2)
    provider = fake(Refuse(), Refuse(), Refuse())
    provider.generate(request())
    provider.generate(request())
    with pytest.raises(ScriptedFakeError):
        provider.generate(request())
    assert len(provider.history) == 2 and provider.calls_for(*KEY) == 2


def test_the_default_history_cap() -> None:
    assert scripted.MAX_HISTORY == 4_096


def test_non_request_input_is_refused() -> None:
    provider = fake(Refuse())
    with pytest.raises(ScriptedFakeError):
        provider.generate("request")  # type: ignore[arg-type]
    assert provider.calls_for(*KEY) == 0


def test_sequential_calls_are_deterministic() -> None:
    def run() -> list[tuple[StopKind, str]]:
        provider = fake(Respond("a"), StopMaxTokens("b"), Refuse())
        responses = [provider.generate(request()) for _ in range(3)]
        return [(r.stop_kind, r.output_text) for r in responses]

    assert (
        run()
        == run()
        == [
            (StopKind.END_TURN, "a"),
            (StopKind.MAX_TOKENS, "b"),
            (StopKind.REFUSAL, ""),
        ]
    )


def test_concurrent_calls_each_consume_a_distinct_step() -> None:
    steps = tuple(Respond(f"step-{index}") for index in range(MAX_STEPS_PER_KEY))
    provider = fake(*steps)
    barrier = threading.Barrier(MAX_STEPS_PER_KEY)
    outputs: list[str] = []
    lock = threading.Lock()

    def worker() -> None:
        barrier.wait()
        text = provider.generate(request()).output_text
        with lock:
            outputs.append(text)

    threads = [threading.Thread(target=worker) for _ in range(MAX_STEPS_PER_KEY)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(outputs) == sorted(step.text for step in steps)
    assert sorted(record.step_index for record in provider.history) == list(range(16))
    with pytest.raises(ScriptedFakeError):
        provider.generate(request())


# --- privacy -------------------------------------------------------------------------------------


def test_representations_never_show_script_text() -> None:
    provider = ScriptedFakeProvider(
        scripts={
            KEY: (
                Respond(CANARY),
                StopMaxTokens(CANARY),
                WrongModel("other-model", CANARY),
                Refuse(),
                StopOther(),
                Timeout(),
                Fail(),
            )
        }
    )
    provider.generate(request())
    rendered = repr(provider) + str(provider)
    for step in provider._scripts[KEY]:
        rendered += repr(step)
    assert CANARY not in rendered
    assert repr(provider) == (
        "ScriptedFakeProvider(model_id='fake-scripted-v1', keys=1, steps=7, calls=1)"
    )


# --- Prompt 172 regressions: configuration error boundary ----------------------------------------


class RaisingScripts(dict[tuple[str, str], tuple[scripted.Step, ...]]):
    def __init__(self, error: BaseException, methods: set[str]) -> None:
        super().__init__({KEY: (Refuse(),)})
        self._error = error
        self._methods = methods

    def items(self) -> Any:
        if "items" in self._methods:
            raise self._error
        return super().items()

    def __iter__(self) -> Any:
        if "__iter__" in self._methods:
            raise self._error
        return super().__iter__()


class RaisingMappingScripts(Mapping[tuple[str, str], tuple[scripted.Step, ...]]):
    """A non-``dict`` mapping whose iteration (and so its ``items()`` view) fails."""

    def __init__(self, error: BaseException) -> None:
        self._error = error

    def __getitem__(self, key: tuple[str, str]) -> tuple[scripted.Step, ...]:
        raise self._error

    def __iter__(self) -> Iterator[tuple[str, str]]:
        raise self._error

    def __len__(self) -> int:
        return 1


@pytest.mark.parametrize(
    "scripts",
    [
        RaisingScripts(RuntimeError(CANARY), {"items"}),
        RaisingScripts(RuntimeError(CANARY), {"items", "__iter__"}),
        RaisingMappingScripts(RuntimeError(CANARY)),
    ],
)
def test_failing_script_mappings_raise_a_fixed_error(
    scripts: Any, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    """Finding B (d): reading the supplied configuration is inside the error boundary."""
    caplog.set_level(logging.DEBUG)
    with pytest.raises(InvalidModelValueError) as caught:
        ScriptedFakeProvider(scripts=scripts)
    error = caught.value
    assert type(error) is InvalidModelValueError and str(error) == "invalid_model_value"
    assert error.__cause__ is None and error.__context__ is None
    assert CANARY not in "".join(traceback.format_exception(error)) + repr(error)
    captured = capsys.readouterr()
    assert CANARY not in captured.out + captured.err
    assert not caplog.records


@pytest.mark.parametrize("error", [KeyboardInterrupt(), SystemExit(5)])
def test_process_control_from_script_mappings_propagates_unchanged(error: BaseException) -> None:
    for scripts in (RaisingScripts(error, {"items"}), RaisingMappingScripts(error)):
        with pytest.raises(type(error)) as caught:
            ScriptedFakeProvider(scripts=scripts)
        assert caught.value is error


def test_ordinary_configuration_remains_usable() -> None:
    provider = ScriptedFakeProvider(scripts={KEY: (Refuse(),)})
    assert provider.generate(request()).stop_kind is StopKind.REFUSAL
