"""``DatabaseAdminStore.seed_demo`` against an in-memory session double (no database).

The double answers exactly the statements ``seed_demo`` issues: the PostgreSQL ``INSERT ... ON
CONFLICT DO NOTHING`` for tenants and users, and the ``SELECT``s that read rows back. It records
commits and rollbacks, so the tests also check that refusals roll back. Real PostgreSQL behaviour
is covered in ``test_persistence_postgres.py``.
"""

from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.dml import Insert

from evidenceguard_persistence.accounts import (
    DEMO_TENANTS,
    DatabaseAdminStore,
    DemoTenantConflictError,
    DemoUserConflictError,
    demo_tenant_id,
    demo_user_id,
)
from evidenceguard_persistence.models import UserRole

_DIALECT = postgresql.dialect()  # type: ignore[no-untyped-call]


class _Result:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows

    def first(self) -> tuple[Any, ...] | None:
        return self._rows[0] if self._rows else None

    def one(self) -> tuple[Any, ...]:
        assert len(self._rows) == 1
        return self._rows[0]

    def scalar_one(self) -> Any:
        assert len(self._rows) == 1
        return self._rows[0][0]

    def scalar_one_or_none(self) -> Any:
        return self._rows[0][0] if self._rows else None


class _Database:
    """Tenants as ``{id: slug}`` and users as ``{id: (tenant_id, role)}``."""

    def __init__(self) -> None:
        self.tenants: dict[UUID, str] = {}
        self.users: dict[UUID, tuple[UUID, str]] = {}
        self.events: list[str] = []

    def __call__(self) -> "_Session":
        return _Session(self)


class _Session:
    def __init__(self, db: _Database) -> None:
        self.db = db
        self.pending_tenants: dict[UUID, str] = {}
        self.pending_users: dict[UUID, tuple[UUID, str]] = {}

    def _tenants(self) -> dict[UUID, str]:
        return {**self.db.tenants, **self.pending_tenants}

    def _users(self) -> dict[UUID, tuple[UUID, str]]:
        return {**self.db.users, **self.pending_users}

    def execute(self, statement: Any) -> _Result:
        params = statement.compile(dialect=_DIALECT).params
        if isinstance(statement, Insert):
            if statement.table.name == "tenants":
                if params["id"] in self._tenants() or params["slug"] in self._tenants().values():
                    return _Result([])
                self.pending_tenants[params["id"]] = params["slug"]
                return _Result([(params["id"],)])
            if params["id"] in self._users():
                return _Result([])
            self.pending_users[params["id"]] = (params["tenant_id"], params["role"])
            return _Result([(params["id"],)])
        table = statement.get_final_froms()[0].name
        if table == "tenants":
            slug = params["slug_1"]
            return _Result([(tid,) for tid, s in self._tenants().items() if s == slug])
        user = self._users().get(params["id_1"])
        return _Result([user] if user else [])

    def commit(self) -> None:
        self.db.tenants.update(self.pending_tenants)
        self.db.users.update(self.pending_users)
        self.db.events.append("commit")

    def rollback(self) -> None:
        self.pending_tenants.clear()
        self.pending_users.clear()
        self.db.events.append("rollback")

    def close(self) -> None:
        self.db.events.append("close")


def _store(db: _Database) -> DatabaseAdminStore:
    return DatabaseAdminStore(db)  # type: ignore[arg-type]


def test_first_seed_creates_two_tenants_with_one_user_per_role() -> None:
    db = _Database()

    users = _store(db).seed_demo()

    assert len(db.tenants) == 2 and len(db.users) == 6
    assert all(user.created for user in users)
    assert [(u.tenant_slug, u.role) for u in users] == [
        (slug, role) for slug, _ in DEMO_TENANTS for role in UserRole
    ]
    assert db.events == ["commit", "close"]


def test_reseeding_reports_the_stored_role_and_changes_nothing() -> None:
    db = _Database()
    _store(db).seed_demo()
    slug = DEMO_TENANTS[0][0]
    reviewer = demo_user_id(slug, UserRole.REVIEWER)
    db.users[reviewer] = (demo_tenant_id(slug), "approver")  # changed by an operator
    before = dict(db.users)

    users = _store(db).seed_demo()

    (reported,) = [user for user in users if user.user_id == reviewer]
    assert reported.role is UserRole.APPROVER
    assert reported.created is False
    assert not any(user.created for user in users)
    assert db.users == before


def test_demo_user_id_owned_by_another_tenant_is_refused_and_rolled_back() -> None:
    db = _Database()
    other_tenant = uuid4()
    db.tenants[other_tenant] = "unrelated-tenant"
    taken = demo_user_id(DEMO_TENANTS[0][0], UserRole.ADMIN)
    db.users[taken] = (other_tenant, "admin")

    with pytest.raises(DemoUserConflictError, match=r"^a demo user ID already belongs"):
        _store(db).seed_demo()

    assert db.events == ["rollback", "close"]
    assert db.tenants == {other_tenant: "unrelated-tenant"}
    assert db.users == {taken: (other_tenant, "admin")}


def test_demo_tenant_slug_owned_by_another_tenant_is_refused() -> None:
    db = _Database()
    db.tenants[uuid4()] = DEMO_TENANTS[0][0]

    with pytest.raises(DemoTenantConflictError):
        _store(db).seed_demo()

    assert db.events == ["rollback", "close"]
    assert db.users == {}
