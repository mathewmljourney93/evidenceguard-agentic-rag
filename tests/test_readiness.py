"""``/readyz``, readiness evaluation and the shared database resource, without a database."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError

from evidenceguard_api import readiness as api_readiness
from evidenceguard_api.app import create_app
from evidenceguard_api.database import AppDatabase
from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_persistence import readiness as persistence_readiness
from evidenceguard_persistence.credentials import generate_api_key
from evidenceguard_persistence.readiness import (
    READINESS_STATEMENT_TIMEOUT_MS,
    ReadinessResult,
    check_readiness,
    evaluate_readiness,
    packaged_migration_heads,
)
from evidenceguard_persistence.settings import DATABASE_URL_ENV
from evidenceguard_persistence.vendors import VendorPage, VendorRecord

FAILURE_MARKER = "fake-internal-failure-marker"
HEADS = frozenset({"0003"})


# --- evaluation --------------------------------------------------------------------------


def test_packaged_heads_are_read_from_the_installed_migrations() -> None:
    assert packaged_migration_heads() == HEADS


def _raise() -> tuple[str, ...]:
    raise OperationalError("SELECT 1", {}, Exception(FAILURE_MARKER))


@pytest.mark.parametrize(
    ("probe", "expected"),
    [
        (lambda: ("0003",), ReadinessResult(database=True, migrations=True)),
        (lambda: (), ReadinessResult(database=True, migrations=False)),  # no version table
        (lambda: ("0002",), ReadinessResult(database=True, migrations=False)),  # one behind
        (lambda: ("0001",), ReadinessResult(database=True, migrations=False)),
        (lambda: ("0004",), ReadinessResult(database=True, migrations=False)),
        (lambda: ("0002", "0003"), ReadinessResult(database=True, migrations=False)),
        (_raise, ReadinessResult(database=False, migrations=None)),
    ],
)
def test_evaluate_readiness(probe: Any, expected: ReadinessResult) -> None:
    assert evaluate_readiness(probe, HEADS) == expected


def test_only_a_reachable_and_exactly_migrated_database_is_ready() -> None:
    assert ReadinessResult(True, True).ready
    assert not ReadinessResult(True, False).ready
    assert not ReadinessResult(False, None).ready


class _FakeConnection:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.rolled_back = False

    def execute(self, statement: Any) -> None:
        self.statements.append(str(statement))

    def rollback(self) -> None:
        self.rolled_back = True


class _FakeEngine:
    def __init__(self) -> None:
        self.connection = _FakeConnection()

    @contextmanager
    def connect(self) -> Iterator[_FakeConnection]:
        yield self.connection


class _FakeMigrationContext:
    @staticmethod
    def configure(connection: Any) -> "_FakeMigrationContext":
        return _FakeMigrationContext()

    def get_current_heads(self) -> tuple[str, ...]:
        return ("0003",)


def test_probe_bounds_the_query_reads_heads_and_rolls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(persistence_readiness, "MigrationContext", _FakeMigrationContext)
    engine = _FakeEngine()

    result = check_readiness(engine)  # type: ignore[arg-type]

    assert result == ReadinessResult(database=True, migrations=True)
    assert engine.connection.statements == [
        f"SET LOCAL statement_timeout = {READINESS_STATEMENT_TIMEOUT_MS}",
        "SELECT 1",
    ]
    assert engine.connection.rolled_back


def test_unreachable_database_is_not_ready_and_nothing_is_contacted() -> None:
    def refuse() -> Any:
        raise OperationalError("connect", {}, Exception(FAILURE_MARKER))

    engine = create_engine("postgresql+psycopg://", creator=refuse)
    try:
        assert check_readiness(engine) == ReadinessResult(database=False, migrations=None)
    finally:
        engine.dispose()


# --- /readyz ---------------------------------------------------------------------------------


class FakeReadiness:
    def __init__(self, result: ReadinessResult | Exception) -> None:
        self.result = result
        self.calls = 0

    def __call__(self) -> ReadinessResult:
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.mark.parametrize(
    ("result", "status", "body"),
    [
        (
            ReadinessResult(True, True),
            200,
            {"status": "ready", "checks": {"database": "ok", "migrations": "ok"}},
        ),
        (
            ReadinessResult(True, False),
            503,
            {"status": "not_ready", "checks": {"database": "ok", "migrations": "failed"}},
        ),
        (
            ReadinessResult(False, None),
            503,
            {"status": "not_ready", "checks": {"database": "failed", "migrations": "not_checked"}},
        ),
        (
            RuntimeError(FAILURE_MARKER),
            503,
            {"status": "not_ready", "checks": {"database": "failed", "migrations": "not_checked"}},
        ),
    ],
)
def test_readyz_reports_only_fixed_states(
    result: ReadinessResult | Exception, status: int, body: dict[str, Any]
) -> None:
    readiness = FakeReadiness(result)
    with TestClient(create_app(readiness=readiness)) as client:
        response = client.get("/readyz")
        health = client.get("/healthz")

    assert response.status_code == status
    assert response.json() == body
    assert response.headers["Cache-Control"] == "no-store"
    assert FAILURE_MARKER not in response.text
    assert health.status_code == 200
    assert readiness.calls == 1


def test_readyz_needs_no_credentials() -> None:
    with TestClient(create_app(readiness=FakeReadiness(ReadinessResult(True, True)))) as client:
        assert client.get("/readyz").status_code == 200


def test_default_readyz_without_settings_is_not_ready_and_health_still_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(DATABASE_URL_ENV, raising=False)
    app = create_app()
    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200
        response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["checks"] == {"database": "failed", "migrations": "not_checked"}
    assert DATABASE_URL_ENV not in response.text
    assert not app.state.database.started


def test_default_readyz_with_an_invalid_url_does_not_reveal_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(DATABASE_URL_ENV, f"mysql://someone:{FAILURE_MARKER}@db.invalid/x")
    with TestClient(create_app()) as client:
        response = client.get("/readyz")

    assert response.status_code == 503
    assert FAILURE_MARKER not in response.text and "db.invalid" not in response.text


# --- the shared, lazily started database resource ------------------------------------------


def test_default_components_share_one_lazily_started_database() -> None:
    app = create_app()
    shared = app.state.database

    assert app.state.authenticator._database is shared
    assert app.state.vendor_store._database is shared
    assert isinstance(app.state.readiness, api_readiness.DatabaseReadiness)
    assert app.state.readiness._database is shared
    assert not shared.started


def test_injected_database_is_used_lazily_and_not_closed_by_the_app() -> None:
    created: list[Any] = []

    def factory() -> Any:
        engine = create_engine("postgresql+psycopg://", creator=lambda: None)
        created.append(engine)
        return engine

    database = AppDatabase(factory)
    with TestClient(create_app(database=database)) as client:
        assert client.get("/healthz").status_code == 200
        assert created == []

    assert created == []  # never started: nothing to dispose
    database.engine()
    assert len(created) == 1 and database.started
    database.close()
    assert not database.started


class _FalsyAuthenticator:
    def __init__(self, key: str, actor: ActorContext) -> None:
        self.key, self.actor = key, actor
        self.calls = 0

    def __bool__(self) -> bool:
        return False

    def __call__(self, credential: str) -> ActorContext | None:
        self.calls += 1
        return self.actor if credential == self.key else None


class _EmptyVendorStore:
    def __init__(self) -> None:
        self.calls = 0

    def __len__(self) -> int:
        return 0

    def create(self, actor: ActorContext, *, slug: str, name: str) -> VendorRecord:
        raise AssertionError("not used")

    def list(self, actor: ActorContext, *, limit: int, offset: int) -> VendorPage:
        self.calls += 1
        return VendorPage(items=(), total=0)

    def get(self, actor: ActorContext, vendor_id: UUID) -> VendorRecord | None:
        raise AssertionError("not used")


class _FalsyReadiness(FakeReadiness):
    def __bool__(self) -> bool:
        return False


def test_falsy_injected_components_are_kept_and_the_database_never_starts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(DATABASE_URL_ENV, raising=False)
    key = generate_api_key().plaintext.get_secret_value()
    actor = ActorContext(tenant_id=uuid4(), actor_id=uuid4(), role=Role.REVIEWER)
    authenticator = _FalsyAuthenticator(key, actor)
    vendor_store = _EmptyVendorStore()
    readiness = _FalsyReadiness(ReadinessResult(True, True))
    assert not authenticator and not vendor_store and not readiness

    app = create_app(authenticator=authenticator, vendor_store=vendor_store, readiness=readiness)
    assert app.state.authenticator is authenticator
    assert app.state.vendor_store is vendor_store
    assert app.state.readiness is readiness

    headers = {"Authorization": f"Bearer {key}"}
    with TestClient(app) as client:
        me = client.get("/v1/me", headers=headers)
        vendors = client.get("/v1/vendors", headers=headers)
        ready = client.get("/readyz")

    assert me.status_code == 200 and me.json()["tenant_id"] == str(actor.tenant_id)
    assert vendors.status_code == 200 and vendors.json()["total"] == 0
    assert ready.status_code == 200
    assert (authenticator.calls, vendor_store.calls, readiness.calls) == (2, 1, 1)
    assert not app.state.database.started


def test_owned_database_is_closed_on_shutdown(monkeypatch: pytest.MonkeyPatch) -> None:
    closed: list[bool] = []
    monkeypatch.setattr(AppDatabase, "close", lambda self: closed.append(True))

    with TestClient(create_app()):
        pass
    assert closed == [True]

    closed.clear()
    with TestClient(create_app(database=AppDatabase())):
        pass
    assert closed == []
