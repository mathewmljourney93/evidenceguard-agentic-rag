"""Database URL policy and the destructive-test guard. Nothing here connects to a database.

The end-to-end guard tests run the real integration fixtures in a child pytest process with a
plugin that makes engine creation and psycopg connections raise, so a target that slipped past
the guard would be reported as ``ENGINE_CREATED`` instead of reaching any server.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from evidenceguard_persistence.safety import (
    TEST_DATABASE_URL_ENV,
    require_disposable_test_database,
)
from evidenceguard_persistence.settings import (
    DATABASE_URL_ENV,
    DatabaseConfigurationError,
    DatabaseIdentity,
    database_identity,
    load_database_settings,
    parse_postgres_url,
)

# Obviously fake markers; no database is contacted and no name is resolved.
PASSWORD = "not-a-real-password-marker"
OTHER_PASSWORD = "another-fake-password-marker"
QUERY_MARKER = "fake-query-value-marker"
MARKERS = (PASSWORD, OTHER_PASSWORD, QUERY_MARKER)
BASE = f"postgresql://someone:{PASSWORD}@db.invalid:5432/evidenceguard_test"
ROOT = Path(__file__).resolve().parents[1]


def _assert_no_markers(text: str) -> None:
    for marker in MARKERS:
        assert marker not in text


# --- URL policy -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        # Database and routing overrides.
        f"{BASE}?dbname=evidenceguard_dev",
        f"{BASE}?host=other.invalid",
        f"{BASE}?hostaddr=192.0.2.10",
        f"{BASE}?port=6543",
        f"{BASE}?service={QUERY_MARKER}",
        f"{BASE}?target_session_attrs=read-write",
        # Credentials and arbitrary options in the query.
        f"{BASE}?password={QUERY_MARKER}",
        f"{BASE}?user={QUERY_MARKER}",
        f"{BASE}?passfile={QUERY_MARKER}",
        f"{BASE}?options=-c%20search_path%3D{QUERY_MARKER}",
        f"{BASE}?application_name={QUERY_MARKER}",
        # Repeated parameters, even allowed ones with the same value.
        f"{BASE}?sslmode=require&sslmode=disable",
        f"{BASE}?connect_timeout=5&connect_timeout=5",
        # Malformed allowed values.
        f"{BASE}?sslmode={QUERY_MARKER}",
        f"{BASE}?sslmode=REQUIRE",
        f"{BASE}?connect_timeout=0",
        f"{BASE}?connect_timeout=601",
        f"{BASE}?connect_timeout=-1",
        f"{BASE}?connect_timeout=1e3",
        f"{BASE}?connect_timeout={QUERY_MARKER}",
        # Hosts, ports and database names.
        f"postgresql://someone:{PASSWORD}@db1.invalid,db2.invalid/evidenceguard_test",
        f"postgresql://someone:{PASSWORD}@db1.invalid:5432,db2.invalid:5433/evidenceguard_test",
        f"postgresql://someone:{PASSWORD}@%2Fvar%2Frun%2Fpostgresql/evidenceguard_test",
        f"postgresql://someone:{PASSWORD}@db_host.invalid/evidenceguard_test",
        f"postgresql://someone:{PASSWORD}@db.invalid:0/evidenceguard_test",
        f"postgresql://someone:{PASSWORD}@db.invalid:65536/evidenceguard_test",
        f"postgresql://someone:{PASSWORD}@db.invalid:/evidenceguard_test",
        f"postgresql://someone:{PASSWORD}@db.invalid/evidence/guard_test",
        f"postgresql://someone:{PASSWORD}@db.invalid/evidenceguard_test#{QUERY_MARKER}",
        f"postgresql://someone:{PASSWORD}@db.invalid/evidence%20guard_test",
    ],
)
def test_unsafe_urls_are_rejected_with_a_generic_error(
    monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    monkeypatch.setenv(DATABASE_URL_ENV, url)

    with pytest.raises(DatabaseConfigurationError) as exc_info:
        load_database_settings()

    assert str(exc_info.value) == f"{DATABASE_URL_ENV} is not a valid PostgreSQL URL"
    assert exc_info.value.__cause__ is None
    _assert_no_markers(repr(exc_info.value))
    with pytest.raises(ValueError) as parse_info:
        parse_postgres_url(url)
    _assert_no_markers(str(parse_info.value))


def test_allowed_query_parameters_are_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DATABASE_URL_ENV, f"{BASE}?sslmode=verify-full&connect_timeout=10")

    url = load_database_settings().sqlalchemy_url()

    assert dict(url.query) == {"sslmode": "verify-full", "connect_timeout": "10"}


@pytest.mark.parametrize(
    "url",
    [
        f"postgresql://someone:{PASSWORD}@[::1]:5433/evidenceguard_test",
        f"postgresql://someone:{PASSWORD}@192.0.2.10/evidenceguard_test",
        f"postgresql://someone:{PASSWORD}@DB.Example.invalid./evidenceguard-dev",
    ],
)
def test_single_host_forms_are_accepted(url: str) -> None:
    assert parse_postgres_url(url).drivername == "postgresql+psycopg"


def test_omitted_port_is_made_explicit() -> None:
    url = parse_postgres_url(f"postgresql://someone:{PASSWORD}@db.invalid/evidenceguard_test")

    assert url.port == 5432


# --- database identity ------------------------------------------------------------------


def _identity(raw: str) -> DatabaseIdentity:
    return database_identity(parse_postgres_url(raw))


@pytest.mark.parametrize(
    ("first", "second"),
    [
        # Different credentials.
        (BASE, f"postgresql://admin:{OTHER_PASSWORD}@db.invalid:5432/evidenceguard_test"),
        (BASE, "postgresql://db.invalid:5432/evidenceguard_test"),
        # Driver spelling, host case, trailing dot and default port.
        (BASE, f"postgresql+psycopg://someone:{PASSWORD}@DB.Invalid./evidenceguard_test"),
        # Allowed options do not change the target.
        (BASE, f"{BASE}?sslmode=require&connect_timeout=3"),
        # Database-name case is folded, conservatively.
        (BASE, f"postgresql://someone:{PASSWORD}@db.invalid/EvidenceGuard_Test"),
        # Loopback spellings.
        ("postgresql://localhost/a_test", "postgresql://127.0.0.1:5432/a_test"),
        ("postgresql://LOCALHOST./a_test", "postgresql://[::1]/a_test"),
        ("postgresql://127.0.0.1/a_test", "postgresql://127.1.2.3/a_test"),
        ("postgresql://localhost/a_test", "postgresql://[::ffff:127.0.0.1]/a_test"),
        ("postgresql://localhost/a_test", "postgresql://0.0.0.0/a_test"),
        ("postgresql://localhost/a_test", "postgresql://[0:0:0:0:0:0:0:1]/a_test"),
        ("postgresql://localhost/a_test", "postgresql://db.localhost/a_test"),
    ],
)
def test_equivalent_urls_share_an_identity(first: str, second: str) -> None:
    assert _identity(first) == _identity(second)


@pytest.mark.parametrize(
    "other",
    [
        "postgresql://db.invalid:5432/evidenceguard_dev",
        "postgresql://db.invalid:5433/evidenceguard_test",
        "postgresql://other.invalid:5432/evidenceguard_test",
    ],
)
def test_distinct_targets_have_distinct_identities(other: str) -> None:
    assert _identity(BASE) != _identity(other)


# --- destructive-test guard -------------------------------------------------------------

LOCAL_TEST = f"postgresql+psycopg://evidenceguard:{PASSWORD}@127.0.0.1:5433/evidenceguard_test"


@pytest.mark.parametrize(
    "app",
    [
        # Same target, different credentials.
        f"postgresql://owner:{OTHER_PASSWORD}@127.0.0.1:5433/evidenceguard_test",
        # Same target, other spellings of driver, loopback host and database case.
        f"postgresql://evidenceguard:{PASSWORD}@localhost:5433/evidenceguard_test",
        f"postgresql://evidenceguard:{PASSWORD}@LocalHost:5433/EVIDENCEGUARD_TEST",
        f"postgresql://evidenceguard:{PASSWORD}@[::1]:5433/evidenceguard_test",
        f"postgresql://evidenceguard:{PASSWORD}@127.0.0.1:5433/evidenceguard_test?sslmode=disable",
    ],
)
def test_guard_rejects_the_application_database(app: str) -> None:
    with pytest.raises(DatabaseConfigurationError) as exc_info:
        require_disposable_test_database(LOCAL_TEST, app)

    assert str(exc_info.value) == (
        f"{TEST_DATABASE_URL_ENV} targets the same database as {DATABASE_URL_ENV}"
    )
    _assert_no_markers(repr(exc_info.value))


def test_guard_rejects_same_target_with_default_port_spelling() -> None:
    test = f"postgresql://evidenceguard:{PASSWORD}@db.invalid/evidenceguard_test"
    app = f"postgresql://owner:{OTHER_PASSWORD}@DB.INVALID:5432/evidenceguard_test"

    with pytest.raises(DatabaseConfigurationError, match="targets the same database"):
        require_disposable_test_database(test, app)


@pytest.mark.parametrize(
    "app",
    [
        f"mysql://owner:{OTHER_PASSWORD}@127.0.0.1/evidenceguard_dev",
        f"postgresql://owner:{OTHER_PASSWORD}@127.0.0.1/evidenceguard_dev?dbname=x",
        f"not a url {OTHER_PASSWORD}",
        # Set but empty or blank is configured-and-invalid, not unset.
        "",
        " ",
        "\t\n",
    ],
)
def test_guard_fails_closed_on_an_invalid_application_url(app: str) -> None:
    with pytest.raises(DatabaseConfigurationError) as exc_info:
        require_disposable_test_database(LOCAL_TEST, app)

    assert str(exc_info.value) == f"{DATABASE_URL_ENV} is not a valid PostgreSQL URL"
    assert exc_info.value.__cause__ is None
    _assert_no_markers(repr(exc_info.value))


@pytest.mark.parametrize("test", [None, ""])
def test_guard_requires_a_test_url(test: str | None) -> None:
    with pytest.raises(DatabaseConfigurationError, match=f"^{TEST_DATABASE_URL_ENV} is not set$"):
        require_disposable_test_database(test, None)


@pytest.mark.parametrize(
    "test",
    [
        f"postgresql://evidenceguard:{PASSWORD}@127.0.0.1:5433/evidenceguard_dev",
        f"postgresql://evidenceguard:{PASSWORD}@127.0.0.1:5433/evidenceguard_TEST",
        f"postgresql://evidenceguard:{PASSWORD}@127.0.0.1:5433/evidenceguard_test_copy",
    ],
)
def test_guard_requires_the_test_suffix(test: str) -> None:
    with pytest.raises(DatabaseConfigurationError) as exc_info:
        require_disposable_test_database(test, None)

    assert "must end in _test" in str(exc_info.value)
    _assert_no_markers(repr(exc_info.value))


def test_guard_rejects_an_invalid_test_url() -> None:
    with pytest.raises(DatabaseConfigurationError) as exc_info:
        require_disposable_test_database(f"{LOCAL_TEST}?dbname=evidenceguard_dev", None)

    assert str(exc_info.value) == f"{TEST_DATABASE_URL_ENV} is not a valid PostgreSQL URL"
    _assert_no_markers(repr(exc_info.value))


@pytest.mark.parametrize(
    "app",
    [
        None,
        # The Compose layout: same server, a different (development) database.
        f"postgresql://evidenceguard:{PASSWORD}@127.0.0.1:5433/evidenceguard_dev",
        f"postgresql://evidenceguard:{PASSWORD}@127.0.0.1:5432/evidenceguard_test",
    ],
)
def test_guard_accepts_a_distinct_disposable_target(app: str | None) -> None:
    url = require_disposable_test_database(LOCAL_TEST, app)

    assert url.database == "evidenceguard_test"
    assert url.drivername == "postgresql+psycopg"


# --- the real integration fixtures never reach engine creation for rejected targets -------

_FORBID_CONNECTIONS_PLUGIN = '''
"""Make engine creation and driver connections fail loudly (loaded before collection)."""

import psycopg
import sqlalchemy
import sqlalchemy.engine


def _forbidden(*args, **kwargs):
    raise AssertionError("ENGINE_CREATED")


sqlalchemy.create_engine = _forbidden
sqlalchemy.engine.create_engine = _forbidden
psycopg.connect = _forbidden
'''


def _run_integration_fixture(tmp_path: Path, test_url: str, app_url: str | None) -> str:
    (tmp_path / "eg_forbid_connections.py").write_text(_FORBID_CONNECTIONS_PLUGIN, "utf-8")
    env = {key: value for key, value in os.environ.items() if not key.startswith(("EG_", "PG"))}
    env["PYTHONPATH"] = str(tmp_path)
    env[TEST_DATABASE_URL_ENV] = test_url
    if app_url is not None:
        env[DATABASE_URL_ENV] = app_url
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "eg_forbid_connections",
            "-p",
            "no:cacheprovider",
            "-q",
            "tests/test_persistence_postgres.py::test_no_extensions_are_created",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert result.returncode != 0
    return result.stdout + result.stderr


@pytest.mark.parametrize(
    ("test_url", "app_url"),
    [
        (LOCAL_TEST, f"postgresql://owner:{OTHER_PASSWORD}@localhost:5433/evidenceguard_test"),
        (LOCAL_TEST, f"postgresql://owner:{OTHER_PASSWORD}@127.0.0.1:5433/x?dbname=y"),
        (LOCAL_TEST, ""),
        (f"{LOCAL_TEST}?dbname=evidenceguard_dev", None),
        (f"postgresql://evidenceguard:{PASSWORD}@127.0.0.1:5433/evidenceguard_dev", None),
    ],
    ids=["same-target", "invalid-app-url", "empty-app-url", "query-override", "no-test-suffix"],
)
def test_rejected_targets_never_reach_engine_creation(
    tmp_path: Path, test_url: str, app_url: str | None
) -> None:
    output = _run_integration_fixture(tmp_path, test_url, app_url)

    assert "refusing to run" in output
    assert "ENGINE_CREATED" not in output
    _assert_no_markers(output)


def test_accepted_target_reaches_the_forbidden_engine(tmp_path: Path) -> None:
    """Control: proves the plugin intercepts engine creation, so the tests above are meaningful."""
    output = _run_integration_fixture(tmp_path, LOCAL_TEST, None)

    assert "ENGINE_CREATED" in output
    assert "refusing to run" not in output
