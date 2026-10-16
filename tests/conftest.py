import os
from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import URL
from sqlalchemy.pool import NullPool

from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_domain.evidence import (
    Citation,
    EvidenceQuestion,
    EvidenceStatus,
    Finding,
    ReportContent,
    Severity,
    SourceType,
)
from evidenceguard_persistence.migration_config import alembic_config
from evidenceguard_persistence.safety import (
    TEST_DATABASE_URL_ENV,
    require_disposable_test_database,
)
from evidenceguard_persistence.settings import DATABASE_URL_ENV, DatabaseConfigurationError


@pytest.fixture
def tenant_a() -> UUID:
    return uuid4()


@pytest.fixture
def tenant_b() -> UUID:
    return uuid4()


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 10, 11, 12, 0, tzinfo=UTC)


@pytest.fixture
def reviewer(tenant_a: UUID) -> ActorContext:
    return ActorContext(tenant_id=tenant_a, actor_id=uuid4(), role=Role.REVIEWER)


@pytest.fixture
def approver(tenant_a: UUID) -> ActorContext:
    return ActorContext(tenant_id=tenant_a, actor_id=uuid4(), role=Role.APPROVER)


@pytest.fixture
def other_tenant_approver(tenant_b: UUID) -> ActorContext:
    return ActorContext(tenant_id=tenant_b, actor_id=uuid4(), role=Role.APPROVER)


@pytest.fixture
def content(tenant_a: UUID) -> ReportContent:
    """Synthetic tenant-A report: one vendor-claim finding and one unresolved question."""
    citation = Citation(
        tenant_id=tenant_a,
        document_revision_id=uuid4(),
        chunk_id=uuid4(),
        source_type=SourceType.VENDOR_STATEMENT,
        quote="Customer data is retained for ninety (90) days after termination.",
    )
    return ReportContent(
        tenant_id=tenant_a,
        title="Lumenvale Cloud security review",
        questions=(
            EvidenceQuestion(
                question_id="RET-01",
                text="How long is customer data retained after termination?",
                search_queries=("data retention after termination",),
            ),
            EvidenceQuestion(
                question_id="BCP-01",
                text="What is the recovery time objective for production?",
                search_queries=("recovery time objective",),
            ),
        ),
        findings=(
            Finding(
                tenant_id=tenant_a,
                finding_id=uuid4(),
                question_ids=("RET-01",),
                title="Retention period stated only by the vendor",
                severity=Severity.MEDIUM,
                statement="The vendor states a 90-day retention period after termination.",
                evidence_status=EvidenceStatus.VENDOR_CLAIM,
                citations=(citation,),
            ),
        ),
        unresolved_question_ids=("BCP-01",),
    )


# --- PostgreSQL integration-test gating (see ADR-0004) ------------------------------------

REQUIRE_INTEGRATION_ENV = "EG_REQUIRE_INTEGRATION"
_integration_passed: list[str] = []


def _integration_required() -> bool:
    return os.environ.get(REQUIRE_INTEGRATION_ENV) == "1"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip integration tests without a test database, unless they are explicitly required."""
    integration = [item for item in items if item.get_closest_marker("integration")]
    if _integration_required():
        if not os.environ.get(TEST_DATABASE_URL_ENV):
            raise pytest.UsageError(
                f"{REQUIRE_INTEGRATION_ENV}=1 but {TEST_DATABASE_URL_ENV} is not set"
            )
        if not integration:
            raise pytest.UsageError(
                f"{REQUIRE_INTEGRATION_ENV}=1 but no integration tests were collected"
            )
        return
    if not os.environ.get(TEST_DATABASE_URL_ENV):
        reason = (
            f"{TEST_DATABASE_URL_ENV} is not set; integration tests need a disposable "
            "PostgreSQL test database (see README)"
        )
        for item in integration:
            item.add_marker(pytest.mark.skip(reason=reason))


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if report.when == "call" and report.passed and "integration" in report.keywords:
        _integration_passed.append(report.nodeid)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """When integration tests are required, fail the run if none of them actually passed."""
    if _integration_required() and exitstatus == 0 and not _integration_passed:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


# --- disposable PostgreSQL fixtures, shared by the integration test modules ------------


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
    """Reset the disposable test database to an empty public schema.

    Migration 0005 installs ``vector`` in ``public`` and its downgrade deliberately keeps it, so
    a downgraded database may still have it. Dropping the schema with ``CASCADE`` also drops an
    extension whose objects live in it; the assertion below proves each test starts without
    ``vector`` rather than assuming it (M4b, ADR-0014)."""
    engine = create_engine(test_database_url, poolclass=NullPool, hide_parameters=True)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP SCHEMA public CASCADE")
        connection.exec_driver_sql("CREATE SCHEMA public")
        extensions = set(connection.exec_driver_sql("SELECT extname FROM pg_extension").scalars())
    assert extensions == {"plpgsql"}, "the reset test database still has an extension"
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
