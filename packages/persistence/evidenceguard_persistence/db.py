"""Explicit engine and session lifecycle.

Nothing here runs at import time. Callers create one engine per process, create sessions from
a factory, and own each transaction through ``transaction``. Engines never echo SQL and hide
SQL parameter values in errors and logs.

Waits are bounded: a new connection gives up after ``CONNECT_TIMEOUT_SECONDS`` (unless the URL
sets its own validated ``connect_timeout``), and waiting for a pooled connection gives up after
``POOL_TIMEOUT_SECONDS``.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from evidenceguard_persistence.settings import DatabaseSettings

CONNECT_TIMEOUT_SECONDS = 5
POOL_TIMEOUT_SECONDS = 10


def create_db_engine(settings: DatabaseSettings) -> Engine:
    """Create (but do not connect) an engine for the configured database."""
    url = settings.sqlalchemy_url()
    connect_args = (
        {} if "connect_timeout" in url.query else {"connect_timeout": CONNECT_TIMEOUT_SECONDS}
    )
    return create_engine(
        url,
        echo=False,
        echo_pool=False,
        hide_parameters=True,
        pool_pre_ping=True,
        pool_timeout=POOL_TIMEOUT_SECONDS,
        connect_args=connect_args,
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@contextmanager
def transaction(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """One unit of work that this block owns.

    Commits when the block finishes normally, rolls back if it raises, and always closes the
    session. Code inside the block must not commit or roll back the session itself.
    """
    session = session_factory()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


def dispose_engine(engine: Engine) -> None:
    """Close all pooled connections. Call once when the process stops using the engine."""
    engine.dispose()
