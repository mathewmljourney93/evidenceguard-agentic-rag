"""Database settings, read from the environment only when explicitly requested.

The URL is read from ``EG_DATABASE_URL`` in the process environment. No ``.env`` file or other
configuration source is read implicitly. The URL is held as a ``SecretStr``, and
``load_database_settings`` turns any problem into a ``DatabaseConfigurationError`` whose message
names the variable but never the URL, its query values or its credentials. That wrapper is the
supported error boundary: pydantic's ``hide_input_in_errors`` only hides the input in a printed
``ValidationError``, not in structured dumps such as ``errors()`` or ``json()``.

URL policy (``parse_postgres_url``). SQLAlchemy's psycopg dialect passes URL query parameters to
the driver as connection arguments, where they could override the validated database or host,
add credentials that URL masking does not hide, or set arbitrary server options. So:

- only ``postgresql://`` or ``postgresql+psycopg://``, normalized to psycopg;
- exactly one explicit host (a DNS name or an IP literal; no lists, sockets or escapes);
- a port from 1 to 65535, with an omitted port made explicit as 5432 so the process
  environment (``PGPORT``) cannot change it;
- a database name of letters, digits, ``_`` and ``-`` only;
- query parameters limited to ``sslmode`` (a libpq mode) and ``connect_timeout`` (1 to 600
  seconds), each at most once. Everything else is rejected.

Review settings (W8, ADR-0027) follow the same rules: environment only, no ``.env`` file, and a
wrapper error (``ReviewConfigurationError``) whose message names the variable but never its
value, raised with no cause or context. ``EG_REVIEW_PROVIDER`` switches reviews on and
``EG_REVIEW_MODEL`` names the model; both are set or both are unset (empty counts as unset).
``EG_ANTHROPIC_API_KEY`` is read only by the worker, through ``load_anthropic_settings``, and is
held as a ``SecretStr``.
"""

import ipaddress
import re
from enum import StrEnum
from typing import NamedTuple, Self

from pydantic import SecretStr, ValidationError, field_validator, model_validator
from pydantic_core import PydanticCustomError
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError

from evidenceguard_domain.model_calls import is_model_id

DATABASE_URL_ENV = "EG_DATABASE_URL"
REVIEW_PROVIDER_ENV = "EG_REVIEW_PROVIDER"
REVIEW_MODEL_ENV = "EG_REVIEW_MODEL"
ANTHROPIC_API_KEY_ENV = "EG_ANTHROPIC_API_KEY"
MAX_API_KEY_LENGTH = 256
DRIVER = "postgresql+psycopg"
DEFAULT_PORT = 5432
_ACCEPTED_DRIVERS = frozenset({"postgresql", DRIVER})
_SSLMODES = frozenset({"disable", "allow", "prefer", "require", "verify-ca", "verify-full"})
_MAX_CONNECT_TIMEOUT = 600
_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
_HOSTNAME = re.compile(rf"(?=.{{1,254}}$){_LABEL}(?:\.{_LABEL})*\.?")
_DATABASE_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_-]{0,62}")
_DIGITS = re.compile(r"[0-9]{1,4}")


class DatabaseConfigurationError(RuntimeError):
    """Database settings are missing or invalid. Messages never include the URL."""


def _check_query(url: URL) -> None:
    for key, value in url.query.items():
        if not isinstance(value, str):
            raise ValueError("query parameters must not be repeated")
        if key == "sslmode":
            if value not in _SSLMODES:
                raise ValueError("sslmode is not a recognised libpq mode")
        elif key == "connect_timeout":
            if not _DIGITS.fullmatch(value) or not 1 <= int(value) <= _MAX_CONNECT_TIMEOUT:
                raise ValueError(f"connect_timeout must be 1 to {_MAX_CONNECT_TIMEOUT} seconds")
        else:
            raise ValueError("only the sslmode and connect_timeout query parameters are allowed")


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def parse_postgres_url(raw: str) -> URL:
    """Parse and validate a PostgreSQL URL, pin the psycopg 3 driver and make the port explicit.

    Raises ``ValueError`` with a message that never contains the URL, its query values or its
    credentials.
    """
    try:
        url = make_url(raw)
    except (ArgumentError, ValueError):
        raise ValueError("not a valid database URL") from None
    if url.drivername not in _ACCEPTED_DRIVERS:
        raise ValueError("must be a postgresql:// or postgresql+psycopg:// URL")
    host = url.host
    if not host or not (_HOSTNAME.fullmatch(host) or _is_ip_literal(host)):
        raise ValueError("must include exactly one host name or IP address")
    port = DEFAULT_PORT if url.port is None else url.port
    if not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    if not url.database or not _DATABASE_NAME.fullmatch(url.database):
        raise ValueError("must include a database name of letters, digits, '_' or '-'")
    _check_query(url)
    return url.set(drivername=DRIVER, port=port)


class DatabaseIdentity(NamedTuple):
    """Which database a URL targets, ignoring credentials, driver spelling and options."""

    host: str
    port: int
    database: str


def _normalized_host(host: str) -> str:
    """Lower-case the host and fold every loopback or unspecified address into one value.

    Deliberately conservative: two spellings that might reach the same local server compare
    equal. Distinct DNS names are not resolved, so aliases of one server compare unequal.
    """
    host = host.lower().rstrip(".")
    if host == "localhost" or host.endswith(".localhost"):
        return "loopback"
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    if address.is_loopback or address.is_unspecified:
        return "loopback"
    return address.compressed


def database_identity(url: URL) -> DatabaseIdentity:
    """The target of a URL returned by ``parse_postgres_url``."""
    if url.host is None or url.database is None:
        raise ValueError("URL has no host or database")
    port = DEFAULT_PORT if url.port is None else url.port
    return DatabaseIdentity(_normalized_host(url.host), port, url.database.lower())


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="EG_",
        env_file=None,
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )

    database_url: SecretStr

    @field_validator("database_url")
    @classmethod
    def _require_postgres(cls, value: SecretStr) -> SecretStr:
        parse_postgres_url(value.get_secret_value())
        return value

    def sqlalchemy_url(self) -> URL:
        """The validated URL. ``URL``'s repr and ``str`` hide the password."""
        return parse_postgres_url(self.database_url.get_secret_value())


def load_database_settings() -> DatabaseSettings:
    """Read ``EG_DATABASE_URL`` from the environment, or raise ``DatabaseConfigurationError``."""
    try:
        return DatabaseSettings()
    except ValidationError as exc:
        missing = any(error["type"] == "missing" for error in exc.errors(include_input=False))
        problem = "is not set" if missing else "is not a valid PostgreSQL URL"
        raise DatabaseConfigurationError(f"{DATABASE_URL_ENV} {problem}") from None


# --- review settings (W8, ADR-0027) ---------------------------------------------------------------


class ReviewConfigurationError(RuntimeError):
    """Review settings are partial or invalid. Messages name the variable, never its value."""


class ReviewProvider(StrEnum):
    ANTHROPIC = "anthropic"


_PROVIDER_MISSING = "review_provider_missing"
_MODEL_MISSING = "review_model_missing"
_SETTINGS_CONFIG = SettingsConfigDict(
    env_prefix="EG_",
    env_file=None,
    env_ignore_empty=True,
    extra="ignore",
    frozen=True,
    hide_input_in_errors=True,
)


class ReviewSettings(BaseSettings):
    """Whether reviews are on, and with which model. Read by the API and the worker."""

    model_config = _SETTINGS_CONFIG

    review_provider: ReviewProvider | None = None
    review_model: str | None = None

    @field_validator("review_model")
    @classmethod
    def _require_model_id(cls, value: str | None) -> str | None:
        if value is not None and not is_model_id(value):
            raise ValueError("not a valid model id")
        return value

    @model_validator(mode="after")
    def _require_both_or_neither(self) -> Self:
        if self.review_provider is not None and self.review_model is None:
            raise PydanticCustomError(_MODEL_MISSING, "the review model is not set")
        if self.review_provider is None and self.review_model is not None:
            raise PydanticCustomError(_PROVIDER_MISSING, "the review provider is not set")
        return self


def _is_api_key(value: str) -> bool:
    return 1 <= len(value) <= MAX_API_KEY_LENGTH and all(
        0x21 <= ord(character) <= 0x7E for character in value
    )


class AnthropicSettings(BaseSettings):
    """The worker's Anthropic API key. The API process never reads it."""

    model_config = _SETTINGS_CONFIG

    anthropic_api_key: SecretStr

    @field_validator("anthropic_api_key")
    @classmethod
    def _require_printable_ascii(cls, value: SecretStr) -> SecretStr:
        if not _is_api_key(value.get_secret_value()):
            raise ValueError("not a valid key")
        return value


def _review_problem(exc: ValidationError) -> str:
    for error in exc.errors(include_input=False, include_context=False, include_url=False):
        if error["type"] == _MODEL_MISSING:
            return f"{REVIEW_MODEL_ENV} is not set"
        if error["type"] == _PROVIDER_MISSING:
            return f"{REVIEW_PROVIDER_ENV} is not set"
        if error["loc"][:1] == ("review_provider",):
            return f"{REVIEW_PROVIDER_ENV} is not a supported provider"
    return f"{REVIEW_MODEL_ENV} is not a valid model id"


def load_review_settings() -> ReviewSettings | None:
    """Read ``EG_REVIEW_PROVIDER`` and ``EG_REVIEW_MODEL``. ``None`` when both are unset or
    empty; ``ReviewConfigurationError`` when only one is set or a value is invalid. The error is
    raised after the handler, so it carries no cause or context (the pydantic error could)."""
    problem: str | None = None
    settings: ReviewSettings | None = None
    try:
        settings = ReviewSettings()
    except ValidationError as exc:
        problem = _review_problem(exc)
    if problem is not None or settings is None:
        raise ReviewConfigurationError(problem or f"{REVIEW_PROVIDER_ENV} is not valid")
    if settings.review_provider is None:
        return None
    return settings


def load_anthropic_settings() -> AnthropicSettings:
    """Read ``EG_ANTHROPIC_API_KEY``, or raise ``ReviewConfigurationError`` naming it only,
    with no cause or context."""
    problem: str | None = None
    settings: AnthropicSettings | None = None
    try:
        settings = AnthropicSettings()
    except ValidationError as exc:
        missing = any(error["type"] == "missing" for error in exc.errors(include_input=False))
        problem = "is not set" if missing else "is not a valid key"
    if problem is not None or settings is None:
        raise ReviewConfigurationError(f"{ANTHROPIC_API_KEY_ENV} {problem or 'is not valid'}")
    return settings
