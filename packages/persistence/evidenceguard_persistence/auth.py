"""Authenticate a presented API key against the stored records.

``ApiKeyAuthenticator`` turns a presented credential into a domain ``ActorContext`` or ``None``.
The tenant, actor and role come only from the stored ``api_keys`` and ``users`` rows. The key
is joined to its user on both ``tenant_id`` and ``user_id``, matching the composite foreign
key. Every rejection (malformed, unknown prefix, wrong secret, revoked key, unmapped role)
returns the same ``None``, and an unknown prefix still performs a digest comparison so that it
does not return measurably faster than a wrong secret.

Nothing is cached: each call opens one session, reads the current role and revocation state,
and closes the session on every outcome. Database errors propagate unchanged for the caller to
translate; this module never logs.
"""

from sqlalchemy import and_, select
from sqlalchemy.orm import Session, sessionmaker

from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_persistence.credentials import ParsedApiKey, digest_matches, parse_api_key
from evidenceguard_persistence.models import ApiKey, User, UserRole

# Stored role -> domain role. Explicit, so a new stored role is never mapped by accident.
ROLE_MAP: dict[str, Role] = {
    UserRole.REVIEWER.value: Role.REVIEWER,
    UserRole.APPROVER.value: Role.APPROVER,
    UserRole.ADMIN.value: Role.ADMIN,
}

# Compared against when the prefix is unknown, so that path does the same digest work.
_UNKNOWN_KEY_DIGEST = "0" * 64


class ApiKeyAuthenticator:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def __call__(self, credential: str) -> ActorContext | None:
        key = parse_api_key(credential)
        if key is None:
            return None
        return self._authenticate(key)

    def _authenticate(self, key: ParsedApiKey) -> ActorContext | None:
        statement = (
            select(ApiKey.secret_sha256, ApiKey.revoked_at, User.tenant_id, User.id, User.role)
            .join(User, and_(User.tenant_id == ApiKey.tenant_id, User.id == ApiKey.user_id))
            .where(ApiKey.prefix == key.prefix)
        )
        session = self._session_factory()
        try:
            row = session.execute(statement).one_or_none()
        finally:
            session.close()

        if row is None:
            digest_matches(key, _UNKNOWN_KEY_DIGEST)
            return None
        stored_digest, revoked_at, tenant_id, user_id, stored_role = row
        matches = digest_matches(key, stored_digest)
        role = ROLE_MAP.get(stored_role)
        if not matches or revoked_at is not None or role is None:
            return None
        return ActorContext(tenant_id=tenant_id, actor_id=user_id, role=role)
