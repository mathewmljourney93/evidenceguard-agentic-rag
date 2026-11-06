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

    Failure selection (the accepted M5g G15 rule, ADR-0025). Once ``session_factory()`` has
    returned a session, ``commit()`` is attempted at most once (only after the block returned),
    ``rollback()`` at most once (only after a block or commit failure) and ``close()`` exactly
    once; nothing is retried. Across the block, ``commit()``, ``rollback()`` and ``close()`` the
    **first** ``BaseException`` that is not an ``Exception`` (process control) is raised as the
    same object; every later failure is dropped without inspection. Without process control,
    the ordinary exception selected is the one the earlier helper raised: the block or commit
    error, replaced by a rollback error, replaced by a close error. If ``session_factory()``
    raises, no commit, rollback or close is attempted and its exception propagates unchanged.
    None of this proves that a rollback ran, that a connection was disposed or what a commit's
    outcome was. Nothing here logs or reads exception text.
    """
    session = session_factory()
    control: BaseException | None = None
    ordinary: BaseException | None = None
    try:
        yield session
    except BaseException as error:  # thrown into the generator at the yield
        control, ordinary = _selected(error, control, ordinary)
    else:
        try:
            session.commit()
        except BaseException as error:
            control, ordinary = _selected(error, control, ordinary)
    if control is not None or ordinary is not None:
        try:
            session.rollback()
        except BaseException as error:
            control, ordinary = _selected(error, control, ordinary)
    try:
        session.close()
    except BaseException as error:
        control, ordinary = _selected(error, control, ordinary)
    if control is not None:
        raise control
    if ordinary is not None:
        raise ordinary


def _selected(
    error: BaseException, control: BaseException | None, ordinary: BaseException | None
) -> tuple[BaseException | None, BaseException | None]:
    """The G15 selection: the first process-control object is kept by identity; without one, a
    later ordinary failure replaces the earlier one (the earlier helper's behaviour)."""
    if control is not None:
        return control, ordinary
    if not isinstance(error, Exception):
        return error, ordinary
    return None, error


def dispose_engine(engine: Engine) -> None:
    """Close all pooled connections. Call once when the process stops using the engine."""
    engine.dispose()
