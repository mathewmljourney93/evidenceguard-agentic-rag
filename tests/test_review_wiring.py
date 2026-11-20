"""W8 production review wiring (ADR-0027) without a network or a database."""

import http.client
from typing import Any

import pytest
from sqlalchemy.orm import sessionmaker

from evidenceguard_agents.anthropic import AnthropicError, AnthropicErrorCode, AnthropicProvider
from evidenceguard_agents.scripted import Respond, ScriptedFakeProvider
from evidenceguard_observability.jsonlog import LoggingSpanSink
from evidenceguard_persistence.settings import (
    ANTHROPIC_API_KEY_ENV,
    REVIEW_MODEL_ENV,
    REVIEW_PROVIDER_ENV,
    ReviewConfigurationError,
)
from evidenceguard_worker import review_wiring
from evidenceguard_worker.anthropic_http import HttpsAnthropicTransport
from evidenceguard_worker.handlers import production_registry
from evidenceguard_worker.review import make_run_review_handler

MODEL = "claude-example-20990101"  # synthetic
KEY_CANARY = "sk-test-obviously-fake-wiring-canary"  # obviously fake


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (REVIEW_PROVIDER_ENV, REVIEW_MODEL_ENV, ANTHROPIC_API_KEY_ENV):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    attempts: list[str] = []

    def refuse(self: Any) -> None:
        attempts.append("connect")
        raise AssertionError("no network connection may be opened")

    monkeypatch.setattr(http.client.HTTPSConnection, "connect", refuse)
    return attempts


def _enable(monkeypatch: pytest.MonkeyPatch, key: str | None = KEY_CANARY) -> None:
    monkeypatch.setenv(REVIEW_PROVIDER_ENV, "anthropic")
    monkeypatch.setenv(REVIEW_MODEL_ENV, MODEL)
    if key is not None:
        monkeypatch.setenv(ANTHROPIC_API_KEY_ENV, key)


def test_disabled_settings_build_no_provider(
    monkeypatch: pytest.MonkeyPatch, no_network: list[str]
) -> None:
    monkeypatch.setenv(ANTHROPIC_API_KEY_ENV, KEY_CANARY)  # ignored while reviews are off

    assert review_wiring.load_review_provider() is None
    assert no_network == []


def test_enabled_settings_build_the_https_anthropic_provider_without_network(
    monkeypatch: pytest.MonkeyPatch, no_network: list[str]
) -> None:
    _enable(monkeypatch)
    factory_calls: list[str] = []
    built: list[HttpsAnthropicTransport] = []

    def recording_transport(api_key: Any) -> HttpsAnthropicTransport:
        def factory(*args: Any) -> Any:
            factory_calls.append("called")
            raise AssertionError("the connection factory must not be called")

        transport = HttpsAnthropicTransport(api_key, connection_factory=factory)
        built.append(transport)
        return transport

    monkeypatch.setattr(review_wiring, "HttpsAnthropicTransport", recording_transport)

    provider = review_wiring.load_review_provider()

    assert type(provider) is AnthropicProvider
    assert provider.transport is built[0]
    assert provider.provider_id == "anthropic"
    assert factory_calls == [] and no_network == []
    assert KEY_CANARY not in repr(provider) + repr(provider.transport)


def test_the_default_transport_is_built_without_network(
    monkeypatch: pytest.MonkeyPatch, no_network: list[str]
) -> None:
    _enable(monkeypatch)

    provider = review_wiring.load_review_provider()

    assert type(provider) is AnthropicProvider
    assert type(provider.transport) is HttpsAnthropicTransport
    assert no_network == []


@pytest.mark.parametrize(
    ("key", "message"),
    [
        (None, "EG_ANTHROPIC_API_KEY is not set"),
        ("", "EG_ANTHROPIC_API_KEY is not set"),
        (KEY_CANARY + " with space", "EG_ANTHROPIC_API_KEY is not a valid key"),
        ("k" * 257, "EG_ANTHROPIC_API_KEY is not a valid key"),
    ],
)
def test_missing_or_invalid_key_is_a_configuration_error(
    key: str | None, message: str, monkeypatch: pytest.MonkeyPatch, no_network: list[str]
) -> None:
    _enable(monkeypatch, key)

    with pytest.raises(ReviewConfigurationError) as info:
        review_wiring.load_review_provider()

    assert str(info.value) == message
    assert info.value.__cause__ is None and info.value.__context__ is None
    assert KEY_CANARY not in repr(info.value)
    assert no_network == []


def test_a_transport_refusal_is_a_configuration_error_without_a_cause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable(monkeypatch)

    def refuse(api_key: Any) -> Any:
        raise AnthropicError(AnthropicErrorCode.CONFIGURATION)

    monkeypatch.setattr(review_wiring, "HttpsAnthropicTransport", refuse)

    with pytest.raises(ReviewConfigurationError) as info:
        review_wiring.load_review_provider()

    assert str(info.value) == "EG_ANTHROPIC_API_KEY is not a valid key"
    assert info.value.__cause__ is None and info.value.__context__ is None


def test_partial_review_settings_fail_before_the_key_is_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(REVIEW_PROVIDER_ENV, "anthropic")

    def forbidden() -> Any:
        raise AssertionError("the key must not be read")

    monkeypatch.setattr(review_wiring, "load_anthropic_settings", forbidden)

    with pytest.raises(ReviewConfigurationError, match=r"^EG_REVIEW_MODEL is not set$"):
        review_wiring.load_review_provider()


def test_build_review_handler_is_registered_as_run_review(monkeypatch: pytest.MonkeyPatch) -> None:
    factory: sessionmaker[Any] = sessionmaker()
    fake = ScriptedFakeProvider(scripts={("verifier", "SEC-01"): (Respond("{}"),)})
    calls: list[tuple[Any, dict[str, Any]]] = []

    def recording(provider: Any, **kwargs: Any) -> Any:
        calls.append((provider, kwargs))
        return make_run_review_handler(provider, **kwargs)

    monkeypatch.setattr(review_wiring, "make_run_review_handler", recording)

    handler = review_wiring.build_review_handler(fake, factory)
    registry = production_registry(review_handler=handler)

    assert registry.kinds == frozenset({"ingest_revision", "index_revision", "run_review"})
    assert registry["run_review"] is handler
    ((provider, kwargs),) = calls
    assert provider is fake
    assert set(kwargs) == {"session_factory", "span_sink"}
    assert kwargs["session_factory"] is factory
    assert type(kwargs["span_sink"]) is LoggingSpanSink
    assert production_registry().kinds == frozenset({"ingest_revision", "index_revision"})
