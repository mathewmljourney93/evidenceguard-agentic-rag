"""Vendor persistence and ``DatabaseVendorStore`` transactions, without a database.

A recording session double captures the compiled SQL (to check tenant filters) and the
commit, rollback and close calls (to check transaction ownership on every outcome).
"""

from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError, OperationalError

from evidenceguard_api.vendors import DatabaseVendorStore
from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_persistence.vendors import (
    VENDOR_SLUG_CONSTRAINT,
    DuplicateVendorSlugError,
    VendorRecord,
)

_DIALECT = postgresql.dialect()  # type: ignore[no-untyped-call]
TENANT = UUID("11111111-1111-4111-8111-111111111111")
ACTOR = ActorContext(tenant_id=TENANT, actor_id=uuid4(), role=Role.REVIEWER)


class _Diag:
    def __init__(self, constraint_name: str | None) -> None:
        self.constraint_name = constraint_name


class _DriverError(Exception):
    def __init__(self, constraint_name: str | None) -> None:
        super().__init__("driver error text that must not be shown")
        self.diag = _Diag(constraint_name)


def _integrity_error(constraint_name: str | None) -> IntegrityError:
    return IntegrityError("INSERT INTO vendors ...", {}, _DriverError(constraint_name))


class _Result:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalar_one(self) -> Any:
        return self._rows[0]

    def all(self) -> list[Any]:
        return self._rows

    def one_or_none(self) -> Any:
        return self._rows[0] if self._rows else None


class _Session:
    def __init__(self, factory: "_Factory") -> None:
        self.factory = factory
        self.added: list[Any] = []

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        self.factory.events.append("flush")
        if self.factory.flush_error is not None:
            raise self.factory.flush_error

    def execute(self, statement: Any) -> _Result:
        compiled = statement.compile(dialect=_DIALECT)
        self.factory.sql.append((" ".join(str(compiled).split()), dict(compiled.params)))
        return _Result(self.factory.results.pop(0))

    def commit(self) -> None:
        self.factory.events.append("commit")
        if self.factory.commit_error is not None:
            raise self.factory.commit_error

    def rollback(self) -> None:
        self.factory.events.append("rollback")

    def close(self) -> None:
        self.factory.events.append("close")


class _Factory:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.sql: list[tuple[str, dict[str, Any]]] = []
        self.results: list[list[Any]] = []
        self.flush_error: Exception | None = None
        self.commit_error: Exception | None = None

    def __call__(self) -> _Session:
        return _Session(self)


class _Database:
    def __init__(self, factory: _Factory) -> None:
        self.factory = factory

    def session_factory(self) -> _Factory:
        return self.factory


def _store(factory: _Factory) -> DatabaseVendorStore:
    return DatabaseVendorStore(_Database(factory))  # type: ignore[arg-type]


class _Row:
    def __init__(self, id: UUID, slug: str, name: str) -> None:
        self.id, self.slug, self.name = id, slug, name


# --- create ------------------------------------------------------------------------------


def test_create_uses_the_actors_tenant_and_commits_then_closes() -> None:
    factory = _Factory()

    record = _store(factory).create(ACTOR, slug="alpha", name="Alpha")

    assert isinstance(record, VendorRecord) and record.slug == "alpha"
    assert factory.events == ["flush", "commit", "close"]


def test_create_assigns_the_tenant_from_the_actor_only() -> None:
    factory = _Factory()
    sessions: list[_Session] = []

    def capture() -> _Session:
        session = factory()
        sessions.append(session)
        return session

    DatabaseVendorStore(_Database(capture)).create(ACTOR, slug="alpha", name="Alpha")  # type: ignore[arg-type]

    (vendor,) = sessions[0].added
    assert vendor.tenant_id == TENANT


def test_duplicate_slug_constraint_becomes_duplicate_error_and_rolls_back() -> None:
    factory = _Factory()
    factory.flush_error = _integrity_error(VENDOR_SLUG_CONSTRAINT)

    with pytest.raises(DuplicateVendorSlugError) as exc_info:
        _store(factory).create(ACTOR, slug="alpha", name="Alpha")

    assert factory.events == ["flush", "rollback", "close"]
    assert exc_info.value.__cause__ is None
    assert "driver error text" not in str(exc_info.value)


@pytest.mark.parametrize(
    "constraint", ["fk_vendors_tenant_id_tenants", "uq_vendors_tenant_id_id", "pk_vendors", None]
)
def test_other_integrity_errors_are_not_classified_as_duplicates(constraint: str | None) -> None:
    factory = _Factory()
    factory.flush_error = _integrity_error(constraint)

    with pytest.raises(IntegrityError):
        _store(factory).create(ACTOR, slug="alpha", name="Alpha")

    assert factory.events == ["flush", "rollback", "close"]


def test_commit_failure_rolls_back_closes_and_propagates() -> None:
    factory = _Factory()
    factory.commit_error = OperationalError("COMMIT", {}, Exception("connection lost"))

    with pytest.raises(OperationalError):
        _store(factory).create(ACTOR, slug="alpha", name="Alpha")

    assert factory.events == ["flush", "commit", "rollback", "close"]


# --- get and list ------------------------------------------------------------------------


def test_get_filters_by_tenant_and_id_in_sql() -> None:
    factory = _Factory()
    vendor_id = uuid4()
    factory.results = [[]]

    assert _store(factory).get(ACTOR, vendor_id) is None

    ((sql, params),) = factory.sql
    assert "WHERE vendors.tenant_id = %(tenant_id_1)s::UUID AND vendors.id = %(id_1)s::UUID" in sql
    assert params == {"tenant_id_1": TENANT, "id_1": vendor_id}
    assert factory.events == ["commit", "close"]


def test_get_returns_the_row() -> None:
    factory = _Factory()
    row = _Row(uuid4(), "alpha", "Alpha")
    factory.results = [[row]]

    assert _store(factory).get(ACTOR, row.id) == VendorRecord(row.id, "alpha", "Alpha")


def test_list_and_count_both_filter_by_tenant_and_order_deterministically() -> None:
    factory = _Factory()
    rows = [_Row(uuid4(), "alpha", "Alpha"), _Row(uuid4(), "bravo", "Bravo")]
    factory.results = [[7], rows]

    page = _store(factory).list(ACTOR, limit=2, offset=4)

    assert page.total == 7 and [item.slug for item in page.items] == ["alpha", "bravo"]
    (count_sql, count_params), (page_sql, page_params) = factory.sql
    assert "count(*)" in count_sql
    assert "WHERE vendors.tenant_id = %(tenant_id_1)s::UUID" in count_sql
    assert count_params == {"tenant_id_1": TENANT}
    assert "WHERE vendors.tenant_id = %(tenant_id_1)s::UUID" in page_sql
    assert "ORDER BY vendors.slug, vendors.id" in page_sql
    assert page_params == {"tenant_id_1": TENANT, "param_1": 2, "param_2": 4}
    assert factory.events == ["commit", "close"]


def test_read_failure_rolls_back_and_closes() -> None:
    factory = _Factory()
    factory.results = []  # execute() will fail with IndexError

    with pytest.raises(IndexError):
        _store(factory).list(ACTOR, limit=1, offset=0)

    assert factory.events == ["rollback", "close"]
