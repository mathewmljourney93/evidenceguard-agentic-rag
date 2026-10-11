"""PostgreSQL integration tests for the M2a schema and migrations.

They run only against the disposable database named by ``EG_TEST_DATABASE_URL``, and they drop
and recreate its ``public`` schema. Before any engine is created, the target must pass
``require_disposable_test_database``: a valid URL, a database name ending in ``_test``, and a
host, port and database different from ``EG_DATABASE_URL`` when that is set. No other URL is
ever used. Without the variable these tests are skipped; with ``EG_REQUIRE_INTEGRATION=1`` (as
in CI) a missing URL or a run where no integration test passes is a failure.
"""

import os
from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, func, insert, inspect, select, text, update
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import NullPool

from evidenceguard_api.app import create_app
from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_persistence.accounts import (
    DatabaseAdminStore,
    DemoUserConflictError,
    RevokeOutcome,
    UserNotInTenantError,
    demo_tenant_id,
    demo_user_id,
)
from evidenceguard_persistence.auth import ApiKeyAuthenticator
from evidenceguard_persistence.credentials import generate_api_key
from evidenceguard_persistence.db import create_session_factory
from evidenceguard_persistence.migration_config import alembic_config
from evidenceguard_persistence.models import ApiKey, Tenant, User, UserRole, Vendor
from evidenceguard_persistence.safety import (
    TEST_DATABASE_URL_ENV,
    require_disposable_test_database,
)
from evidenceguard_persistence.settings import DATABASE_URL_ENV, DatabaseConfigurationError

pytestmark = pytest.mark.integration

M2A_TABLES = {"tenants", "users", "api_keys", "vendors"}
FOREIGN_KEY_VIOLATION = "23503"
UNIQUE_VIOLATION = "23505"
CHECK_VIOLATION = "23514"


@pytest.fixture(scope="session")
def test_database_url() -> URL:
    """The validated disposable target. Every fixture that connects depends on this one."""
    try:
        return require_disposable_test_database(
            os.environ.get(TEST_DATABASE_URL_ENV), os.environ.get(DATABASE_URL_ENV)
        )
    except DatabaseConfigurationError as exc:
        message = f"refusing to run: {exc}"
    pytest.fail(message, pytrace=False)


@pytest.fixture
def empty_database(test_database_url: URL) -> Iterator[Engine]:
    """Reset the disposable test database to an empty public schema."""
    engine = create_engine(test_database_url, poolclass=NullPool, hide_parameters=True)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP SCHEMA public CASCADE")
        connection.exec_driver_sql("CREATE SCHEMA public")
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def config(test_database_url: URL) -> Config:
    return alembic_config(database_url=test_database_url)


@pytest.fixture
def migrated(empty_database: Engine, config: Config) -> Engine:
    command.upgrade(config, "head")
    return empty_database


def _tables(engine: Engine) -> set[str]:
    return set(inspect(engine).get_table_names())


def _sqlstate(error: IntegrityError) -> str | None:
    return getattr(error.orig, "sqlstate", None)


def _tenant(engine: Engine, slug: str) -> UUID:
    tenant_id = uuid4()
    with engine.begin() as connection:
        connection.execute(insert(Tenant).values(id=tenant_id, slug=slug, name=slug.title()))
    return tenant_id


def _user(engine: Engine, tenant_id: UUID, role: str = UserRole.REVIEWER) -> UUID:
    user_id = uuid4()
    with engine.begin() as connection:
        connection.execute(insert(User).values(id=user_id, tenant_id=tenant_id, role=role))
    return user_id


def _api_key(engine: Engine, tenant_id: UUID, user_id: UUID, prefix: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            insert(ApiKey).values(
                id=uuid4(),
                tenant_id=tenant_id,
                user_id=user_id,
                prefix=prefix,
                secret_sha256="0" * 64,
            )
        )


def _vendor(engine: Engine, tenant_id: UUID, slug: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            insert(Vendor).values(id=uuid4(), tenant_id=tenant_id, slug=slug, name=slug.title())
        )


# --- migrations -------------------------------------------------------------------------


def test_upgrade_downgrade_upgrade_on_an_empty_database(
    empty_database: Engine, config: Config
) -> None:
    assert _tables(empty_database) == set()

    command.upgrade(config, "head")
    assert _tables(empty_database) == M2A_TABLES | {"alembic_version"}
    with empty_database.connect() as connection:
        assert (
            connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0001"
        )

    command.downgrade(config, "base")
    assert _tables(empty_database) == {"alembic_version"}

    command.upgrade(config, "head")
    assert _tables(empty_database) == M2A_TABLES | {"alembic_version"}


def test_models_and_migrations_do_not_drift(migrated: Engine, config: Config) -> None:
    command.check(config)  # raises AutogenerateDiffsDetected on any difference


def test_no_extensions_are_created(migrated: Engine) -> None:
    with migrated.connect() as connection:
        extensions = set(connection.execute(text("SELECT extname FROM pg_extension")).scalars())
    assert extensions == {"plpgsql"}


# --- tenant constraints -----------------------------------------------------------------


def test_api_key_cannot_reference_another_tenants_user(migrated: Engine) -> None:
    tenant_a = _tenant(migrated, "tenant-a")
    tenant_b = _tenant(migrated, "tenant-b")
    user_in_b = _user(migrated, tenant_b)

    with pytest.raises(IntegrityError) as exc_info:
        _api_key(migrated, tenant_a, user_in_b, "crosstenant01")
    assert _sqlstate(exc_info.value) == FOREIGN_KEY_VIOLATION
    assert "fk_api_keys_tenant_id_user_id_users" in str(exc_info.value)

    _api_key(migrated, tenant_b, user_in_b, "sametenant001")  # the same user in its own tenant


@pytest.mark.parametrize("table", ["users", "vendors"])
def test_rows_cannot_reference_a_missing_tenant(migrated: Engine, table: str) -> None:
    missing_tenant = uuid4()

    with pytest.raises(IntegrityError) as exc_info:
        if table == "users":
            _user(migrated, missing_tenant)
        else:
            _vendor(migrated, missing_tenant, "orphan")
    assert _sqlstate(exc_info.value) == FOREIGN_KEY_VIOLATION


def test_vendor_slug_is_unique_within_a_tenant_and_reusable_across_tenants(
    migrated: Engine,
) -> None:
    tenant_a = _tenant(migrated, "tenant-a")
    tenant_b = _tenant(migrated, "tenant-b")
    _vendor(migrated, tenant_a, "lumenvale-cloud")

    with pytest.raises(IntegrityError) as exc_info:
        _vendor(migrated, tenant_a, "lumenvale-cloud")
    assert _sqlstate(exc_info.value) == UNIQUE_VIOLATION

    _vendor(migrated, tenant_b, "lumenvale-cloud")


def test_api_key_prefixes_are_unique_across_tenants(migrated: Engine) -> None:
    tenant_a = _tenant(migrated, "tenant-a")
    tenant_b = _tenant(migrated, "tenant-b")
    _api_key(migrated, tenant_a, _user(migrated, tenant_a), "sharedprefix1")

    with pytest.raises(IntegrityError) as exc_info:
        _api_key(migrated, tenant_b, _user(migrated, tenant_b), "sharedprefix1")
    assert _sqlstate(exc_info.value) == UNIQUE_VIOLATION


def test_unknown_role_is_rejected(migrated: Engine) -> None:
    tenant = _tenant(migrated, "tenant-a")

    with pytest.raises(IntegrityError) as exc_info:
        _user(migrated, tenant, role="superuser")
    assert _sqlstate(exc_info.value) == CHECK_VIOLATION

    for role in UserRole:
        _user(migrated, tenant, role=role)


def test_secret_hash_must_be_sha256_hex(migrated: Engine) -> None:
    tenant = _tenant(migrated, "tenant-a")
    user = _user(migrated, tenant)

    with pytest.raises(IntegrityError) as exc_info, migrated.begin() as connection:
        connection.execute(
            insert(ApiKey).values(
                id=uuid4(),
                tenant_id=tenant,
                user_id=user,
                prefix="badhash00001",
                secret_sha256="not-a-sha256-digest",
            )
        )
    assert _sqlstate(exc_info.value) == CHECK_VIOLATION


# --- API-key authentication and eg-admin operations (M2b) -------------------------------


def _store(engine: Engine) -> tuple[DatabaseAdminStore, ApiKeyAuthenticator]:
    session_factory = create_session_factory(engine)
    return DatabaseAdminStore(session_factory), ApiKeyAuthenticator(session_factory)


def test_created_key_authenticates_until_it_is_revoked(migrated: Engine) -> None:
    store, authenticator = _store(migrated)
    store.seed_demo()
    tenant, other_tenant = demo_tenant_id("halverson-freight"), demo_tenant_id("marisol-clinics")
    user = demo_user_id("halverson-freight", UserRole.APPROVER)
    key = generate_api_key()
    plaintext = key.plaintext.get_secret_value()

    key_id = store.create_api_key(tenant, user, key)

    with migrated.connect() as connection:
        stored = connection.execute(select(ApiKey).where(ApiKey.id == key_id)).one()
    assert (stored.tenant_id, stored.user_id, stored.prefix) == (tenant, user, key.prefix)
    assert stored.secret_sha256 == key.secret_sha256
    assert all(plaintext[21:] not in str(value) for value in stored)
    expected = ActorContext(tenant_id=tenant, actor_id=user, role=Role.APPROVER)
    assert authenticator(plaintext) == expected
    assert (
        authenticator(plaintext[:21] + generate_api_key().plaintext.get_secret_value()[21:]) is None
    )
    with TestClient(create_app(authenticator=authenticator)) as client:
        response = client.get("/v1/me", headers={"Authorization": f"Bearer {plaintext}"})
    assert response.status_code == 200
    assert response.json() == {"tenant_id": str(tenant), "actor_id": str(user), "role": "approver"}

    assert store.revoke_api_key(other_tenant, key.prefix) is RevokeOutcome.NOT_FOUND
    assert authenticator(plaintext) == expected
    assert store.revoke_api_key(tenant, key.prefix) is RevokeOutcome.REVOKED
    assert authenticator(plaintext) is None
    with migrated.connect() as connection:
        revoked_at = connection.execute(
            select(ApiKey.revoked_at).where(ApiKey.id == key_id)
        ).scalar_one()
    assert revoked_at is not None
    assert store.revoke_api_key(tenant, key.prefix) is RevokeOutcome.ALREADY_REVOKED
    with migrated.connect() as connection:
        assert (
            connection.execute(select(ApiKey.revoked_at).where(ApiKey.id == key_id)).scalar_one()
            == revoked_at
        )


def test_create_key_rejects_a_user_from_another_tenant(migrated: Engine) -> None:
    store, _ = _store(migrated)
    store.seed_demo()

    with pytest.raises(UserNotInTenantError):
        store.create_api_key(
            demo_tenant_id("halverson-freight"),
            demo_user_id("marisol-clinics", UserRole.ADMIN),
            generate_api_key(),
        )
    with migrated.connect() as connection:
        assert connection.execute(select(func.count()).select_from(ApiKey)).scalar_one() == 0


def test_seed_demo_is_idempotent_and_never_resets_roles_or_revocations(migrated: Engine) -> None:
    store, _ = _store(migrated)
    first = store.seed_demo()
    assert len(first) == 6 and all(user.created for user in first)
    assert {user.role for user in first} == set(UserRole)

    tenant = demo_tenant_id("marisol-clinics")
    reviewer = demo_user_id("marisol-clinics", UserRole.REVIEWER)
    with migrated.begin() as connection:
        connection.execute(update(User).where(User.id == reviewer).values(role="approver"))
    key = generate_api_key()
    store.create_api_key(tenant, reviewer, key)
    store.revoke_api_key(tenant, key.prefix)

    second = store.seed_demo()

    (reported,) = [user for user in second if user.user_id == reviewer]
    assert (reported.tenant_id, reported.role) == (tenant, UserRole.APPROVER)
    assert [(u.tenant_id, u.user_id) for u in second] == [(u.tenant_id, u.user_id) for u in first]
    assert [u.role for u in second if u.user_id != reviewer] == [
        u.role for u in first if u.user_id != reviewer
    ]
    assert not any(user.created for user in second)
    with migrated.connect() as connection:
        assert connection.execute(select(func.count()).select_from(Tenant)).scalar_one() == 2
        assert connection.execute(select(func.count()).select_from(User)).scalar_one() == 6
        assert connection.execute(select(func.count()).select_from(ApiKey)).scalar_one() == 1
        assert (
            connection.execute(select(User.role).where(User.id == reviewer)).scalar_one()
            == "approver"
        )
        assert connection.execute(select(ApiKey.revoked_at)).scalar_one() is not None


def test_authentication_reflects_the_current_stored_role(migrated: Engine) -> None:
    store, authenticator = _store(migrated)
    store.seed_demo()
    tenant = demo_tenant_id("halverson-freight")
    user = demo_user_id("halverson-freight", UserRole.REVIEWER)
    key = generate_api_key()
    store.create_api_key(tenant, user, key)
    plaintext = key.plaintext.get_secret_value()

    first = authenticator(plaintext)
    with migrated.begin() as connection:
        connection.execute(update(User).where(User.id == user).values(role="admin"))
    second = authenticator(plaintext)

    assert first is not None and first.role is Role.REVIEWER
    assert second is not None and second.role is Role.ADMIN
    assert (second.tenant_id, second.actor_id) == (tenant, user)


def test_seed_demo_refuses_a_demo_user_id_owned_by_another_tenant(migrated: Engine) -> None:
    store, _ = _store(migrated)
    other_tenant = _tenant(migrated, "unrelated-tenant")
    taken = demo_user_id("halverson-freight", UserRole.ADMIN)
    with migrated.begin() as connection:
        connection.execute(insert(User).values(id=taken, tenant_id=other_tenant, role="admin"))

    with pytest.raises(DemoUserConflictError):
        store.seed_demo()

    with migrated.connect() as connection:
        assert connection.execute(select(Tenant.slug)).scalars().all() == ["unrelated-tenant"]
        assert connection.execute(select(User.id, User.tenant_id)).all() == [(taken, other_tenant)]
