"""Database-independent persistence tests: settings, lifecycle, packaging and offline SQL.

None of these tests connects to a database. PostgreSQL behaviour is tested in
``test_persistence_postgres.py``.
"""

import io
import os
import subprocess
import sys
from importlib.resources import files
from typing import Any

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from pydantic import ValidationError
from sqlalchemy.pool import QueuePool

from evidenceguard_persistence.db import create_db_engine, transaction
from evidenceguard_persistence.migration_config import alembic_config
from evidenceguard_persistence.models import (
    CHUNK_CHARS_CHECK,
    CHUNK_CONTENT_SHA256_CHECK,
    CHUNK_HEADER_ALL_OR_NONE_CHECK,
    CHUNK_HEADER_BEFORE_BODY_CHECK,
    CHUNK_HEADER_ONLY_TABLES_CHECK,
    CHUNK_LINES_CHECK,
    CHUNK_ORDINAL_CHECK,
    CHUNK_SECTION_PATH_CHECK,
    CHUNK_SET_CHUNK_COUNT_CHECK,
    CHUNK_SET_CHUNKER_VERSION_CHECK,
    CHUNK_SET_MANIFEST_SHA256_CHECK,
    CHUNK_TEXT_CHECK,
    DOCUMENT_AUTHENTICITY_CHECK,
    DOCUMENT_KEY_CHECK,
    DOCUMENT_LATEST_REVISION_NO_CHECK,
    DOCUMENT_SOURCE_TYPE_CHECK,
    DOCUMENT_TITLE_CHECK,
    JOB_ATTEMPT_CHECK,
    JOB_FINISHED_CHECK,
    JOB_IDEMPOTENCY_KEY_CHECK,
    JOB_KIND_CHECK,
    JOB_LAST_ERROR_CHECK,
    JOB_LEASE_CHECK,
    JOB_MAX_ATTEMPTS_CHECK,
    JOB_PAYLOAD_CHECK,
    JOB_QUEUED_INDEX_WHERE,
    JOB_RUNNING_INDEX_WHERE,
    JOB_STATUS_CHECK,
    REVISION_ACTIVATED_AT_WHEN_ACTIVE_CHECK,
    REVISION_BYTE_SIZE_CHECK,
    REVISION_FAILED_AT_WHEN_FAILED_CHECK,
    REVISION_FAILURE_REASON_CODE_CHECK,
    REVISION_FAILURE_REASON_WHEN_FAILED_CHECK,
    REVISION_MEDIA_TYPE_CHECK,
    REVISION_NO_ACTIVATED_AT_BEFORE_SETTLED_CHECK,
    REVISION_NO_CHECK,
    REVISION_NOT_SUPERSEDED_BY_SELF_CHECK,
    REVISION_ONE_ACTIVE_WHERE,
    REVISION_SHA256_CHECK,
    REVISION_STATUS_CHECK,
    REVISION_SUPERSEDED_AT_WHEN_SUPERSEDED_CHECK,
    REVISION_SUPERSEDED_BY_WHEN_SUPERSEDED_CHECK,
    REVISION_VERSION_LABEL_CHECK,
    ROLE_CHECK,
    SECRET_SHA256_CHECK,
    Base,
    UserRole,
)
from evidenceguard_persistence.settings import (
    DATABASE_URL_ENV,
    DatabaseConfigurationError,
    DatabaseSettings,
    load_database_settings,
)

# Obviously fake credentials; no database is contacted.
FAKE_PASSWORD = "not-a-real-password-marker"
FAKE_URL = f"postgresql://someone:{FAKE_PASSWORD}@db.invalid:5432/evidenceguard_unit"


# --- settings ---------------------------------------------------------------------------


def test_missing_url_is_a_clear_configuration_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(DATABASE_URL_ENV, raising=False)

    with pytest.raises(DatabaseConfigurationError, match=f"^{DATABASE_URL_ENV} is not set$"):
        load_database_settings()


@pytest.mark.parametrize(
    "url",
    [
        f"sqlite:///{FAKE_PASSWORD}.db",
        f"mysql://someone:{FAKE_PASSWORD}@db.invalid/evidenceguard",
        f"postgresql://someone:{FAKE_PASSWORD}@/evidenceguard",
        f"not a url {FAKE_PASSWORD}",
    ],
)
def test_invalid_url_error_never_reveals_the_url(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    monkeypatch.setenv(DATABASE_URL_ENV, url)

    with pytest.raises(DatabaseConfigurationError) as exc_info:
        load_database_settings()

    assert str(exc_info.value) == f"{DATABASE_URL_ENV} is not a valid PostgreSQL URL"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__suppress_context__
    assert FAKE_PASSWORD not in repr(exc_info.value)


def test_direct_validation_error_hides_the_input() -> None:
    with pytest.raises(ValidationError) as exc_info:
        DatabaseSettings(database_url=f"mysql://someone:{FAKE_PASSWORD}@db.invalid/x")  # type: ignore[arg-type]

    assert FAKE_PASSWORD not in str(exc_info.value)


def test_valid_url_pins_psycopg_and_stays_masked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DATABASE_URL_ENV, FAKE_URL)

    settings = load_database_settings()
    url = settings.sqlalchemy_url()

    assert url.drivername == "postgresql+psycopg"
    assert url.database == "evidenceguard_unit"
    for text in (repr(settings), str(settings), repr(url), str(url)):
        assert FAKE_PASSWORD not in text


def test_settings_do_not_read_a_dotenv_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    (tmp_path / ".env").write_text(f"{DATABASE_URL_ENV}={FAKE_URL}\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(DATABASE_URL_ENV, raising=False)

    with pytest.raises(DatabaseConfigurationError, match="is not set"):
        load_database_settings()


# --- engine and session lifecycle -------------------------------------------------------


def test_engine_hides_sql_and_credentials_and_does_not_connect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(DATABASE_URL_ENV, FAKE_URL)

    engine = create_db_engine(load_database_settings())
    try:
        assert engine.echo is False
        assert engine.hide_parameters is True
        assert FAKE_PASSWORD not in repr(engine)
        assert isinstance(engine.pool, QueuePool)
        assert engine.pool.checkedout() == 0
    finally:
        engine.dispose()


class _RecordingSession:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def commit(self) -> None:
        self.calls.append("commit")

    def rollback(self) -> None:
        self.calls.append("rollback")

    def close(self) -> None:
        self.calls.append("close")


def test_transaction_commits_and_closes_on_success() -> None:
    session = _RecordingSession()

    with transaction(lambda: session):  # type: ignore[arg-type]
        pass

    assert session.calls == ["commit", "close"]


def test_transaction_rolls_back_and_closes_on_error() -> None:
    session = _RecordingSession()

    with pytest.raises(RuntimeError), transaction(lambda: session):  # type: ignore[arg-type]
        raise RuntimeError("unit of work failed")

    assert session.calls == ["rollback", "close"]


# --- imports and packaging --------------------------------------------------------------


def test_importing_persistence_needs_no_database_configuration() -> None:
    env = {key: value for key, value in os.environ.items() if not key.startswith("EG_")}
    code = (
        "import evidenceguard_persistence.db, evidenceguard_persistence.models, "
        "evidenceguard_persistence.migration_config, evidenceguard_persistence.auth, "
        "evidenceguard_persistence.accounts, evidenceguard_persistence.credentials, "
        "evidenceguard_persistence.jobs, evidenceguard_domain.jobs, "
        "evidenceguard_api.admin, evidenceguard_api.app; "
        "from evidenceguard_api.app import create_app; create_app(); "
        "print('imported')"
    )

    result = subprocess.run(
        [sys.executable, "-I", "-c", code], env=env, capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "imported"


def test_migration_resources_are_packaged() -> None:
    migrations = files("evidenceguard_persistence") / "migrations"

    assert (migrations / "env.py").is_file()
    assert (migrations / "script.py.mako").is_file()
    assert (migrations / "versions" / "v0001_tenancy.py").is_file()
    assert (migrations / "versions" / "v0002_jobs.py").is_file()
    assert (migrations / "versions" / "v0003_documents.py").is_file()
    assert (migrations / "versions" / "v0004_chunks.py").is_file()


def test_migration_history_has_one_head() -> None:
    script = ScriptDirectory.from_config(alembic_config())

    assert script.get_heads() == ["0004"]
    assert script.get_revision("0004").down_revision == "0003"
    assert script.get_revision("0003").down_revision == "0002"
    assert script.get_revision("0002").down_revision == "0001"
    assert script.get_revision("0001").down_revision is None


def test_schema_tables_are_m2a_jobs_documents_and_chunks() -> None:
    assert set(Base.metadata.tables) == {
        "tenants",
        "users",
        "api_keys",
        "vendors",
        "jobs",
        "documents",
        "document_revisions",
        "chunk_sets",
        "chunks",
    }
    assert {role.value for role in UserRole} == {"reviewer", "approver", "admin"}


# --- offline migration SQL (no connection) ----------------------------------------------


def _offline_sql(
    monkeypatch: pytest.MonkeyPatch, *, upgrade: bool, revisions: str = "0001:base"
) -> str:
    monkeypatch.delenv(DATABASE_URL_ENV, raising=False)
    buffer = io.StringIO()
    config = alembic_config(output_buffer=buffer)
    if upgrade:
        command.upgrade(config, "head", sql=True)
    else:
        command.downgrade(config, revisions, sql=True)
    return buffer.getvalue()


def test_offline_upgrade_sql_renders_without_a_database(monkeypatch: pytest.MonkeyPatch) -> None:
    sql = _offline_sql(monkeypatch, upgrade=True)

    for table in ("tenants", "users", "api_keys", "vendors"):
        assert f"CREATE TABLE {table} (" in sql
    assert "FOREIGN KEY(tenant_id, user_id) REFERENCES users (tenant_id, id)" in sql
    assert "UNIQUE (tenant_id, slug)" in sql
    assert ROLE_CHECK in sql
    assert SECRET_SHA256_CHECK in sql
    assert "EXTENSION" not in sql.upper()


def test_offline_upgrade_creates_jobs_with_the_model_constraints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The migration's literal constraint text must equal the model's (alembic check does not
    compare CHECK constraints or partial-index predicates)."""
    sql = _offline_sql(monkeypatch, upgrade=True)

    assert "CREATE TABLE jobs (" in sql
    assert "payload JSONB NOT NULL" in sql
    for check in (
        JOB_STATUS_CHECK,
        JOB_KIND_CHECK,
        JOB_IDEMPOTENCY_KEY_CHECK,
        JOB_PAYLOAD_CHECK,
        JOB_ATTEMPT_CHECK,
        JOB_MAX_ATTEMPTS_CHECK,
        JOB_LEASE_CHECK,
        JOB_FINISHED_CHECK,
        JOB_LAST_ERROR_CHECK,
    ):
        assert f"CHECK ({check})" in sql
    assert "FOREIGN KEY(tenant_id) REFERENCES tenants (id)" in sql
    assert "UNIQUE (tenant_id, kind, idempotency_key)" in sql
    assert "UNIQUE (tenant_id, id)" in sql
    assert (
        f"CREATE INDEX ix_jobs_queued_run_after ON jobs (run_after, id) "
        f"WHERE {JOB_QUEUED_INDEX_WHERE}" in sql
    )
    assert (
        f"CREATE INDEX ix_jobs_running_lease_expires_at ON jobs (lease_expires_at) "
        f"WHERE {JOB_RUNNING_INDEX_WHERE}" in sql
    )
    assert "UPDATE alembic_version SET version_num='0002'" in sql


def test_offline_downgrade_from_0002_drops_only_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    sql = _offline_sql(monkeypatch, upgrade=False, revisions="0002:0001")

    assert "DROP INDEX ix_jobs_running_lease_expires_at;" in sql
    assert "DROP INDEX ix_jobs_queued_run_after;" in sql
    assert "DROP TABLE jobs;" in sql
    for table in ("vendors", "api_keys", "users", "tenants"):
        assert f"DROP TABLE {table};" not in sql


def test_offline_downgrade_sql_drops_every_table(monkeypatch: pytest.MonkeyPatch) -> None:
    sql = _offline_sql(monkeypatch, upgrade=False)

    for table in ("vendors", "api_keys", "users", "tenants"):
        assert f"DROP TABLE {table};" in sql


def test_offline_upgrade_creates_documents_with_the_model_constraints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Migration 0003's literal constraint text must equal the model's (alembic check does not
    compare CHECK constraints or partial-index predicates)."""
    sql = _offline_sql(monkeypatch, upgrade=True)

    assert "CREATE TABLE documents (" in sql
    assert "CREATE TABLE document_revisions (" in sql
    assert "content_text TEXT NOT NULL" in sql
    for check in (
        DOCUMENT_KEY_CHECK,
        DOCUMENT_TITLE_CHECK,
        DOCUMENT_SOURCE_TYPE_CHECK,
        DOCUMENT_AUTHENTICITY_CHECK,
        DOCUMENT_LATEST_REVISION_NO_CHECK,
        REVISION_STATUS_CHECK,
        REVISION_NO_CHECK,
        REVISION_VERSION_LABEL_CHECK,
        REVISION_FAILURE_REASON_CODE_CHECK,
        REVISION_SHA256_CHECK,
        REVISION_MEDIA_TYPE_CHECK,
        REVISION_BYTE_SIZE_CHECK,
        REVISION_FAILURE_REASON_WHEN_FAILED_CHECK,
        REVISION_FAILED_AT_WHEN_FAILED_CHECK,
        REVISION_SUPERSEDED_AT_WHEN_SUPERSEDED_CHECK,
        REVISION_SUPERSEDED_BY_WHEN_SUPERSEDED_CHECK,
        REVISION_ACTIVATED_AT_WHEN_ACTIVE_CHECK,
        REVISION_NO_ACTIVATED_AT_BEFORE_SETTLED_CHECK,
        REVISION_NOT_SUPERSEDED_BY_SELF_CHECK,
    ):
        assert f"CHECK ({check})" in sql
    assert "FOREIGN KEY(tenant_id, vendor_id) REFERENCES vendors (tenant_id, id)" in sql
    assert "FOREIGN KEY(tenant_id, document_id) REFERENCES documents (tenant_id, id)" in sql
    assert (
        "CONSTRAINT fk_document_revisions_superseded_by FOREIGN KEY(tenant_id, document_id, "
        "superseded_by_revision_id) REFERENCES document_revisions (tenant_id, document_id, id)"
        in sql
    )
    assert (
        f"CREATE UNIQUE INDEX uq_document_revisions_one_active ON document_revisions "
        f"(tenant_id, document_id) WHERE {REVISION_ONE_ACTIVE_WHERE}" in sql
    )
    # The circular reference is added after both tables exist.
    alter = (
        "ALTER TABLE documents ADD CONSTRAINT fk_documents_active_revision FOREIGN KEY(tenant_id, "
        "id, active_revision_id) REFERENCES document_revisions (tenant_id, document_id, id)"
    )
    assert alter in sql
    assert sql.index("CREATE TABLE documents (") < sql.index("CREATE TABLE document_revisions (")
    assert sql.index("CREATE TABLE document_revisions (") < sql.index(alter)
    assert "UPDATE alembic_version SET version_num='0003'" in sql
    assert "TRIGGER" not in sql.upper()


def test_offline_downgrade_from_0003_drops_the_pointer_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sql = _offline_sql(monkeypatch, upgrade=False, revisions="0003:0002")

    drop_fk = "ALTER TABLE documents DROP CONSTRAINT fk_documents_active_revision;"
    assert drop_fk in sql
    assert "DROP INDEX uq_document_revisions_one_active;" in sql
    assert sql.index(drop_fk) < sql.index("DROP TABLE document_revisions;")
    assert sql.index("DROP TABLE document_revisions;") < sql.index("DROP TABLE documents;")
    for table in ("jobs", "vendors", "api_keys", "users", "tenants"):
        assert f"DROP TABLE {table};" not in sql


def test_offline_upgrade_creates_chunks_with_the_model_constraints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Migration 0004's literal constraint text must equal the model's (alembic check does not
    compare CHECK constraints)."""
    sql = _offline_sql(monkeypatch, upgrade=True)

    assert "CREATE TABLE chunk_sets (" in sql
    assert "CREATE TABLE chunks (" in sql
    assert "text TEXT NOT NULL" in sql
    assert "section_path TEXT[] DEFAULT '{}' NOT NULL" in sql
    for check in (
        CHUNK_SET_CHUNKER_VERSION_CHECK,
        CHUNK_SET_CHUNK_COUNT_CHECK,
        CHUNK_SET_MANIFEST_SHA256_CHECK,
        CHUNK_ORDINAL_CHECK,
        CHUNK_TEXT_CHECK,
        CHUNK_CONTENT_SHA256_CHECK,
        CHUNK_SECTION_PATH_CHECK,
        CHUNK_LINES_CHECK,
        CHUNK_CHARS_CHECK,
        CHUNK_HEADER_ALL_OR_NONE_CHECK,
        CHUNK_HEADER_ONLY_TABLES_CHECK,
        CHUNK_HEADER_BEFORE_BODY_CHECK,
    ):
        assert f"CHECK ({check})" in sql
    assert "CONSTRAINT pk_chunk_sets PRIMARY KEY (tenant_id, revision_id)" in sql
    assert "UNIQUE (tenant_id, revision_id, chunker_version)" in sql
    assert (
        "FOREIGN KEY(tenant_id, revision_id) REFERENCES document_revisions (tenant_id, id)" in sql
    )
    assert (
        "FOREIGN KEY(tenant_id, revision_id, chunker_version) REFERENCES chunk_sets "
        "(tenant_id, revision_id, chunker_version)" in sql
    )
    assert "UNIQUE (tenant_id, revision_id, chunker_version, ordinal)" in sql
    assert sql.index("CREATE TABLE chunk_sets (") < sql.index("CREATE TABLE chunks (")
    assert "UPDATE alembic_version SET version_num='0004'" in sql
    upper = sql.upper()
    assert "TRIGGER" not in upper
    assert "EXTENSION" not in upper
    assert "VECTOR" not in upper


def test_offline_downgrade_from_0004_drops_chunks_then_chunk_sets_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sql = _offline_sql(monkeypatch, upgrade=False, revisions="0004:0003")

    assert "DROP TABLE chunks;" in sql
    assert "DROP TABLE chunk_sets;" in sql
    assert sql.index("DROP TABLE chunks;") < sql.index("DROP TABLE chunk_sets;")
    for table in ("document_revisions", "documents", "jobs", "vendors", "tenants"):
        assert f"DROP TABLE {table};" not in sql
    assert "UPDATE alembic_version SET version_num='0003'" in sql
