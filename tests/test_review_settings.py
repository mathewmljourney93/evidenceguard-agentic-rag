"""W8 review settings (ADR-0027): environment only, fail closed, never echo a value."""

from pathlib import Path

import pytest
from pydantic import SecretStr

from evidenceguard_persistence.settings import (
    ANTHROPIC_API_KEY_ENV,
    DEFAULT_REVIEW_MAX_IN_FLIGHT,
    REVIEW_MAX_IN_FLIGHT_ENV,
    REVIEW_MODEL_ENV,
    REVIEW_PROVIDER_ENV,
    AnthropicSettings,
    ReviewConfigurationError,
    ReviewProvider,
    ReviewSettings,
    load_anthropic_settings,
    load_review_settings,
)

MODEL = "claude-example-20990101"  # synthetic; not a real model id
KEY_CANARY = "sk-test-obviously-fake-canary-0000"  # obviously fake
VALUE_MARKER = "submitted-marker-value"
REVIEW_VARIABLES = (REVIEW_PROVIDER_ENV, REVIEW_MODEL_ENV, ANTHROPIC_API_KEY_ENV)


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (*REVIEW_VARIABLES, REVIEW_MAX_IN_FLIGHT_ENV):
        monkeypatch.delenv(name, raising=False)


def _error(monkeypatch: pytest.MonkeyPatch, **values: str) -> str:
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    with pytest.raises(ReviewConfigurationError) as info:
        load_review_settings()
    assert info.value.__cause__ is None and info.value.__context__ is None
    return str(info.value)


def test_unset_review_settings_return_none() -> None:
    assert load_review_settings() is None


def test_both_review_settings_are_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(REVIEW_PROVIDER_ENV, "anthropic")
    monkeypatch.setenv(REVIEW_MODEL_ENV, MODEL)

    settings = load_review_settings()

    assert settings is not None
    assert (settings.review_provider, settings.review_model) == (ReviewProvider.ANTHROPIC, MODEL)


def test_provider_without_model_is_a_configuration_error(monkeypatch: pytest.MonkeyPatch) -> None:
    message = _error(monkeypatch, EG_REVIEW_PROVIDER="anthropic")
    assert message == "EG_REVIEW_MODEL is not set"


def test_model_without_provider_is_a_configuration_error(monkeypatch: pytest.MonkeyPatch) -> None:
    message = _error(monkeypatch, EG_REVIEW_MODEL=MODEL)
    assert message == "EG_REVIEW_PROVIDER is not set"
    assert MODEL not in message


def test_unknown_provider_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    message = _error(monkeypatch, EG_REVIEW_PROVIDER=VALUE_MARKER, EG_REVIEW_MODEL=MODEL)
    assert message == "EG_REVIEW_PROVIDER is not a supported provider"
    assert VALUE_MARKER not in message and MODEL not in message


@pytest.mark.parametrize(
    "model", ["Claude-Upper", "claude model", "-leading-dash", "x" * 65, f"{VALUE_MARKER}/x"]
)
def test_invalid_model_id_is_rejected(model: str, monkeypatch: pytest.MonkeyPatch) -> None:
    message = _error(monkeypatch, EG_REVIEW_PROVIDER="anthropic", EG_REVIEW_MODEL=model)
    assert message == "EG_REVIEW_MODEL is not a valid model id"
    assert VALUE_MARKER not in message


def test_empty_values_count_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(REVIEW_PROVIDER_ENV, "")
    monkeypatch.setenv(REVIEW_MODEL_ENV, "")
    monkeypatch.setenv(ANTHROPIC_API_KEY_ENV, "")

    assert load_review_settings() is None
    monkeypatch.setenv(REVIEW_PROVIDER_ENV, "anthropic")
    with pytest.raises(ReviewConfigurationError, match=r"^EG_REVIEW_MODEL is not set$"):
        load_review_settings()
    with pytest.raises(ReviewConfigurationError, match=r"^EG_ANTHROPIC_API_KEY is not set$"):
        load_anthropic_settings()


@pytest.mark.parametrize("key", [KEY_CANARY + " space", KEY_CANARY + "é", "k" * 257])
def test_anthropic_key_never_appears_in_errors_repr_or_dump(
    key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ANTHROPIC_API_KEY_ENV, key)
    with pytest.raises(ReviewConfigurationError) as info:
        load_anthropic_settings()
    assert str(info.value) == "EG_ANTHROPIC_API_KEY is not a valid key"
    assert key not in repr(info.value)
    assert info.value.__cause__ is None and info.value.__context__ is None

    monkeypatch.setenv(ANTHROPIC_API_KEY_ENV, KEY_CANARY)
    settings = load_anthropic_settings()
    assert type(settings.anthropic_api_key) is SecretStr
    assert settings.anthropic_api_key.get_secret_value() == KEY_CANARY
    for rendered in (
        repr(settings),
        str(settings),
        str(settings.model_dump()),
        settings.model_dump_json(),
    ):
        assert KEY_CANARY not in rendered


def test_missing_anthropic_key_is_named_without_a_value() -> None:
    with pytest.raises(ReviewConfigurationError, match=r"^EG_ANTHROPIC_API_KEY is not set$"):
        load_anthropic_settings()


def test_review_settings_ignore_dotenv_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".env").write_text(
        f"EG_REVIEW_PROVIDER=anthropic\nEG_REVIEW_MODEL={MODEL}\n"
        f"EG_ANTHROPIC_API_KEY={KEY_CANARY}\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    assert load_review_settings() is None
    with pytest.raises(ReviewConfigurationError, match="is not set"):
        load_anthropic_settings()
    assert ReviewSettings.model_config.get("env_file") is None
    assert AnthropicSettings.model_config.get("env_file") is None


# --- in-flight cap (W8 fix round 1, ADR-0027) ---------------------------------------------------


def _enable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(REVIEW_PROVIDER_ENV, "anthropic")
    monkeypatch.setenv(REVIEW_MODEL_ENV, MODEL)


@pytest.mark.parametrize("value", [None, ""])
def test_in_flight_cap_defaults_to_two_when_unset_or_empty(
    value: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable(monkeypatch)
    if value is not None:
        monkeypatch.setenv(REVIEW_MAX_IN_FLIGHT_ENV, value)

    settings = load_review_settings()

    assert settings is not None
    assert settings.review_max_in_flight == DEFAULT_REVIEW_MAX_IN_FLIGHT == 2


@pytest.mark.parametrize(("value", "expected"), [("1", 1), ("7", 7), ("20", 20)])
def test_in_flight_cap_accepts_one_to_twenty(
    value: str, expected: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable(monkeypatch)
    monkeypatch.setenv(REVIEW_MAX_IN_FLIGHT_ENV, value)

    settings = load_review_settings()

    assert settings is not None and settings.review_max_in_flight == expected


@pytest.mark.parametrize("value", ["0", "21", "-1", "2.5", "two", VALUE_MARKER])
def test_invalid_in_flight_cap_is_a_configuration_error(
    value: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable(monkeypatch)

    message = _error(monkeypatch, EG_REVIEW_MAX_IN_FLIGHT=value)

    assert message == "EG_REVIEW_MAX_IN_FLIGHT must be an integer from 1 to 20"
    assert VALUE_MARKER not in message and MODEL not in message


def test_invalid_in_flight_cap_fails_closed_even_with_reviews_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = _error(monkeypatch, EG_REVIEW_MAX_IN_FLIGHT="0")
    assert message == "EG_REVIEW_MAX_IN_FLIGHT must be an integer from 1 to 20"
