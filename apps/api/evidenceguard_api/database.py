"""The API's shared database resource (ADR-0006).

One ``AppDatabase`` per app serves authentication, vendor operations and readiness. It creates
its engine and session factory on first use, never at import, app construction, startup or for
``/healthz``, so those need no database settings. ``close`` disposes the engine; ``create_app``
calls it on shutdown when the app owns the resource.

``engine_factory`` is the injection seam: by default it reads ``EG_DATABASE_URL`` and builds an
engine with bounded connection and pool timeouts. Integration tests pass a factory for their
disposable test engine. Configuration errors propagate as ``DatabaseConfigurationError``, whose
message never contains the URL.
"""

import threading
from collections.abc import Callable

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from evidenceguard_persistence.db import create_db_engine, create_session_factory, dispose_engine
from evidenceguard_persistence.settings import load_database_settings


def _engine_from_settings() -> Engine:
    return create_db_engine(load_database_settings())


class AppDatabase:
    def __init__(self, engine_factory: Callable[[], Engine] = _engine_from_settings) -> None:
        self._engine_factory = engine_factory
        self._lock = threading.Lock()
        self._engine: Engine | None = None
        self._session_factory: sessionmaker[Session] | None = None

    @property
    def started(self) -> bool:
        return self._engine is not None

    def engine(self) -> Engine:
        with self._lock:
            if self._engine is None:
                engine = self._engine_factory()
                self._session_factory = create_session_factory(engine)
                self._engine = engine
            return self._engine

    def session_factory(self) -> sessionmaker[Session]:
        self.engine()
        assert self._session_factory is not None
        return self._session_factory

    def close(self) -> None:
        with self._lock:
            if self._engine is not None:
                dispose_engine(self._engine)
            self._engine = None
            self._session_factory = None
