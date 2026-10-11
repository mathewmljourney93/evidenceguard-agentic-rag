"""Account administration used by ``eg-admin``: demo fixture, key creation and revocation.

Each ``DatabaseAdminStore`` method is one transaction (``transaction``): it commits when the
method returns and rolls back if it raises. Callers must therefore act on a result (for
example, print a new key) only after the method has returned.

The demo fixture is synthetic and deterministic: two fictional tenants, each with one user per
role, with IDs derived by ``uuid5`` from a fixed namespace. Seeding inserts only missing rows
(``ON CONFLICT DO NOTHING``), so running it again never changes an existing tenant, user,
role or key, and it never creates API keys. After each insert the user's stored tenant and role
are read back, and the result reports that stored role (which an operator may have changed),
not the role the fixture would have created. A demo tenant slug or user ID already owned by a
different tenant is refused, and the whole seeding transaction rolls back.
"""

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID, uuid4, uuid5

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from evidenceguard_persistence.credentials import NewApiKey
from evidenceguard_persistence.db import transaction
from evidenceguard_persistence.models import ApiKey, Tenant, User, UserRole

DEMO_NAMESPACE = UUID("5b0f6c7e-2d1a-5c3e-9f4b-0e8d7a6c5b4a")
DEMO_TENANTS: tuple[tuple[str, str], ...] = (
    ("halverson-freight", "Halverson Freight (synthetic demo tenant)"),
    ("marisol-clinics", "Marisol Clinics (synthetic demo tenant)"),
)


class AccountError(Exception):
    """An account operation was refused. Messages are fixed and contain no submitted values."""


class UserNotInTenantError(AccountError):
    def __init__(self) -> None:
        super().__init__("the user does not exist in that tenant")


class DemoTenantConflictError(AccountError):
    def __init__(self) -> None:
        super().__init__("a demo tenant slug is already used by a different tenant")


class DemoUserConflictError(AccountError):
    def __init__(self) -> None:
        super().__init__("a demo user ID already belongs to a different tenant")


class RevokeOutcome(StrEnum):
    REVOKED = "revoked"
    ALREADY_REVOKED = "already_revoked"
    NOT_FOUND = "not_found"


@dataclass(frozen=True)
class DemoUser:
    """A demo user as stored. ``role`` is the stored role, which may differ from the default."""

    tenant_slug: str
    tenant_id: UUID
    user_id: UUID
    role: UserRole
    created: bool


def demo_tenant_id(slug: str) -> UUID:
    return uuid5(DEMO_NAMESPACE, f"tenant:{slug}")


def demo_user_id(slug: str, role: UserRole) -> UUID:
    return uuid5(DEMO_NAMESPACE, f"user:{slug}:{role.value}")


class DatabaseAdminStore:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def seed_demo(self) -> tuple[DemoUser, ...]:
        users: list[DemoUser] = []
        with transaction(self._session_factory) as session:
            for slug, name in DEMO_TENANTS:
                tenant_id = demo_tenant_id(slug)
                session.execute(
                    insert(Tenant)
                    .values(id=tenant_id, slug=slug, name=name)
                    .on_conflict_do_nothing()
                )
                stored_tenant = session.execute(
                    select(Tenant.id).where(Tenant.slug == slug)
                ).scalar_one_or_none()
                if stored_tenant != tenant_id:
                    raise DemoTenantConflictError()
                for default_role in UserRole:
                    user_id = demo_user_id(slug, default_role)
                    created = session.execute(
                        insert(User)
                        .values(id=user_id, tenant_id=tenant_id, role=default_role.value)
                        .on_conflict_do_nothing()
                        .returning(User.id)
                    ).first()
                    owner, stored_role = session.execute(
                        select(User.tenant_id, User.role).where(User.id == user_id)
                    ).one()
                    if owner != tenant_id:
                        raise DemoUserConflictError()
                    users.append(
                        DemoUser(
                            slug, tenant_id, user_id, UserRole(stored_role), created is not None
                        )
                    )
        return tuple(users)

    def create_api_key(self, tenant_id: UUID, user_id: UUID, key: NewApiKey) -> UUID:
        """Store a new key for a user that must belong to ``tenant_id``. Returns the key ID."""
        key_id = uuid4()
        with transaction(self._session_factory) as session:
            owner = session.execute(
                select(User.id).where(User.tenant_id == tenant_id, User.id == user_id)
            ).one_or_none()
            if owner is None:
                raise UserNotInTenantError()
            session.add(
                ApiKey(
                    id=key_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    prefix=key.prefix,
                    secret_sha256=key.secret_sha256,
                )
            )
        return key_id

    def revoke_api_key(self, tenant_id: UUID, prefix: str) -> RevokeOutcome:
        """Mark a tenant's key revoked. The row is kept; an earlier revocation is not moved."""
        with transaction(self._session_factory) as session:
            row = session.execute(
                select(ApiKey.id, ApiKey.revoked_at)
                .where(ApiKey.tenant_id == tenant_id, ApiKey.prefix == prefix)
                .with_for_update()
            ).one_or_none()
            if row is None:
                return RevokeOutcome.NOT_FOUND
            if row.revoked_at is not None:
                return RevokeOutcome.ALREADY_REVOKED
            session.execute(update(ApiKey).where(ApiKey.id == row.id).values(revoked_at=func.now()))
        return RevokeOutcome.REVOKED
