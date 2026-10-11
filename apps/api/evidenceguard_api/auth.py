"""API-key authentication at the HTTP boundary (ADR-0005).

Credentials are accepted only from a single ``Authorization: Bearer <key>`` header. A missing,
repeated, oversized, non-ASCII or malformed header, an unknown or wrong key and a revoked key
all produce the same 401 problem response with ``WWW-Authenticate: Bearer``. The authenticated
``ActorContext`` comes only from stored records; no header, query parameter or body value can
supply or override its tenant, actor or role.

``create_app`` takes an ``Authenticator``, a callable from credential to ``ActorContext`` or
``None``. Tests inject a double. By default the app owns a ``DatabaseAuthenticator``, which
reads ``EG_DATABASE_URL`` and creates its engine only on the first well-formed credential, never
at import or app construction, so ``/healthz`` needs no database. The app disposes that engine
when it shuts down. If the database is not configured or fails, the request gets a generic 503:
no URL, exception text or credential is ever returned or logged here.
"""

import threading
from typing import Annotated, Protocol

from fastapi import HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from evidenceguard_api.problems import PublicHTTPException, PublicMessage
from evidenceguard_domain.context import ActorContext
from evidenceguard_persistence.auth import ApiKeyAuthenticator
from evidenceguard_persistence.credentials import KEY_LENGTH, parse_api_key
from evidenceguard_persistence.db import create_db_engine, create_session_factory, dispose_engine
from evidenceguard_persistence.settings import DatabaseConfigurationError, load_database_settings

BEARER_SCHEME = "Bearer"
# "Bearer " plus one key, with generous headroom; anything longer is rejected unparsed.
MAX_AUTHORIZATION_LENGTH = 128
CHALLENGE_HEADERS = {"WWW-Authenticate": BEARER_SCHEME}

# Documents the scheme in OpenAPI only. Parsing is done by ``_bearer_credential`` below,
# because HTTPBearer reads just the first of several Authorization headers.
bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="ApiKey",
    bearerFormat=f"egk_<prefix>_<secret> ({KEY_LENGTH} characters)",
    description="Per-user API key created with `eg-admin create-key`. Sent as a Bearer token.",
)


class Authenticator(Protocol):
    def __call__(self, credential: str) -> ActorContext | None: ...


class DatabaseAuthenticator:
    """The app-owned authenticator. Creates its engine lazily and disposes it in ``close``."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._engine: Engine | None = None
        self._delegate: ApiKeyAuthenticator | None = None

    def __call__(self, credential: str) -> ActorContext | None:
        if parse_api_key(credential) is None:
            return None  # malformed: no need to configure or touch the database
        return self._authenticator()(credential)

    def _authenticator(self) -> ApiKeyAuthenticator:
        with self._lock:
            if self._delegate is None:
                engine = create_db_engine(load_database_settings())
                self._engine = engine
                self._delegate = ApiKeyAuthenticator(create_session_factory(engine))
            return self._delegate

    def close(self) -> None:
        with self._lock:
            if self._engine is not None:
                dispose_engine(self._engine)
            self._engine = None
            self._delegate = None


def _unauthorized() -> PublicHTTPException:
    return PublicHTTPException(
        401, PublicMessage.AUTHENTICATION_REQUIRED, headers=dict(CHALLENGE_HEADERS)
    )


def _bearer_credential(request: Request) -> str | None:
    values: list[bytes] = [
        value
        for name, value in request.scope.get("headers", [])
        if name.lower() == b"authorization"
    ]
    if len(values) != 1 or len(values[0]) > MAX_AUTHORIZATION_LENGTH:
        return None
    try:
        text = values[0].decode("ascii")
    except UnicodeDecodeError:
        return None
    scheme, separator, token = text.partition(" ")
    if not separator or scheme.lower() != BEARER_SCHEME.lower():
        return None
    if not token or any(character.isspace() for character in token):
        return None
    return token


def authenticated_actor(
    request: Request,
    _documented: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)],
) -> ActorContext:
    """FastAPI dependency: the authenticated principal, or a generic 401."""
    credential = _bearer_credential(request)
    if credential is None:
        raise _unauthorized()
    authenticator: Authenticator = request.app.state.authenticator
    try:
        actor = authenticator(credential)
    except (DatabaseConfigurationError, SQLAlchemyError):
        raise HTTPException(status_code=503) from None
    if actor is None:
        raise _unauthorized()
    return actor
