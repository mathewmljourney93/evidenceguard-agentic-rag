"""Production wiring of the review handler (W8, ADR-0027).

``eg-worker`` calls ``load_review_provider`` once at startup, before any database setting is
read:

- reviews off (``EG_REVIEW_PROVIDER`` and ``EG_REVIEW_MODEL`` both unset): ``None``, and the
  worker never claims a review job;
- a partial or invalid review configuration, or a missing or invalid ``EG_ANTHROPIC_API_KEY``:
  ``ReviewConfigurationError`` naming the variable only (the worker exits with code 3);
- otherwise the Anthropic adapter over the standard-library HTTPS transport. Constructing it
  makes no network call.

``build_review_handler`` composes the provider with the worker's session factory and the logging
span sink. The model is never chosen here: each review pins its model id in its stored
configuration when the API creates it. This module never builds a scripted or fake provider.
"""

from collections.abc import Callable

from sqlalchemy.orm import Session, sessionmaker

from evidenceguard_agents.anthropic import AnthropicError, AnthropicProvider
from evidenceguard_agents.providers import ModelProvider
from evidenceguard_observability.jsonlog import LoggingSpanSink
from evidenceguard_persistence.settings import (
    ANTHROPIC_API_KEY_ENV,
    ReviewConfigurationError,
    ReviewProvider,
    load_anthropic_settings,
    load_review_settings,
)
from evidenceguard_worker.anthropic_http import HttpsAnthropicTransport
from evidenceguard_worker.registry import JobHandler
from evidenceguard_worker.review import make_run_review_handler

__all__ = [
    "ModelProvider",
    "ReviewHandlerFactory",
    "ReviewProviderLoader",
    "build_review_handler",
    "load_review_provider",
]

ReviewProviderLoader = Callable[[], ModelProvider | None]
ReviewHandlerFactory = Callable[[ModelProvider, sessionmaker[Session]], JobHandler]


def load_review_provider() -> ModelProvider | None:
    """The configured model provider, ``None`` when reviews are off, or a fixed
    ``ReviewConfigurationError`` whose message names a variable and never a value."""
    settings = load_review_settings()
    if settings is None:
        return None
    if settings.review_provider is not ReviewProvider.ANTHROPIC:  # the only supported provider
        raise ReviewConfigurationError("EG_REVIEW_PROVIDER is not a supported provider")
    key = load_anthropic_settings().anthropic_api_key
    provider: ModelProvider | None = None
    try:
        provider = AnthropicProvider(HttpsAnthropicTransport(key))
    except AnthropicError:
        provider = None
    if provider is None:  # raised outside the handler: no cause or context
        raise ReviewConfigurationError(f"{ANTHROPIC_API_KEY_ENV} is not a valid key")
    return provider


def build_review_handler(
    provider: ModelProvider, session_factory: sessionmaker[Session]
) -> JobHandler:
    """The production review handler: the M5g factory with the logging span sink."""
    return make_run_review_handler(
        provider, session_factory=session_factory, span_sink=LoggingSpanSink()
    )
