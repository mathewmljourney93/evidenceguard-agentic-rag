"""Guard for destructive integration tests, checked before any engine or connection exists.

The PostgreSQL integration tests drop and recreate the ``public`` schema of their target, so
``require_disposable_test_database`` refuses any target that is not plainly a disposable test
database. It only parses URLs; it never resolves host names or connects. M7 generalises it
as ``require_disposable_database`` for the evaluation command's ``_eval`` databases.

Limits: URL comparison cannot prove that two different DNS names (or a name and an IP address)
reach different servers. The test database must be explicitly disposable; the ``_test`` suffix
and this comparison are a safety net, not a substitute for that.
"""

from sqlalchemy.engine import URL

from evidenceguard_persistence.settings import (
    DATABASE_URL_ENV,
    DatabaseConfigurationError,
    database_identity,
    parse_postgres_url,
)

TEST_DATABASE_URL_ENV = "EG_TEST_DATABASE_URL"
TEST_DATABASE_SUFFIX = "_test"


def _parse(raw: str, variable: str) -> URL:
    try:
        return parse_postgres_url(raw)
    except ValueError:
        raise DatabaseConfigurationError(f"{variable} is not a valid PostgreSQL URL") from None


def require_disposable_database(
    raw: str | None, app_raw: str | None, variable: str, suffix: str
) -> URL:
    """Return the validated URL held in ``variable``, or raise ``DatabaseConfigurationError``.

    ``raw`` is the value of ``variable`` and ``app_raw`` that of ``EG_DATABASE_URL`` (``None``
    when unset). The database name must end in ``suffix`` and must not be the application's
    database. A supplied application URL is always validated, so an empty or blank value fails
    closed. Messages name variables, never URLs (M7 generalises the M2a test guard).
    """
    if not raw:
        raise DatabaseConfigurationError(f"{variable} is not set")
    url = _parse(raw, variable)
    if not (url.database or "").endswith(suffix):
        raise DatabaseConfigurationError(f"the {variable} database name must end in {suffix}")
    if app_raw is not None:
        app_url = _parse(app_raw, DATABASE_URL_ENV)
        if database_identity(url) == database_identity(app_url):
            raise DatabaseConfigurationError(
                f"{variable} targets the same database as {DATABASE_URL_ENV}"
            )
    return url


def require_disposable_test_database(test_raw: str | None, app_raw: str | None) -> URL:
    """Return the validated test URL, or raise ``DatabaseConfigurationError``.

    ``test_raw`` is the value of ``EG_TEST_DATABASE_URL`` and ``app_raw`` that of
    ``EG_DATABASE_URL`` (``None`` when unset). A supplied application URL is always validated,
    so an empty or blank value fails closed. Messages name variables, never URLs.
    """
    return require_disposable_database(
        test_raw, app_raw, TEST_DATABASE_URL_ENV, TEST_DATABASE_SUFFIX
    )
