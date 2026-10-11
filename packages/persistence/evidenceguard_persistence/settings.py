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
"""

import ipaddress
import re
from typing import NamedTuple

from pydantic import SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError

DATABASE_URL_ENV = "EG_DATABASE_URL"
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
