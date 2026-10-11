"""Alembic environment for EvidenceGuard.

Offline mode (``--sql``) renders PostgreSQL DDL without a URL or a connection. Online mode uses
the URL passed through ``alembic_config(database_url=...)``, or else ``EG_DATABASE_URL``.
"""

from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.pool import NullPool

from evidenceguard_persistence.migration_config import DATABASE_URL_ATTRIBUTE
from evidenceguard_persistence.models import Base
from evidenceguard_persistence.settings import load_database_settings

config = context.config
target_metadata = Base.metadata


def _database_url() -> URL:
    supplied = config.attributes.get(DATABASE_URL_ATTRIBUTE)
    if isinstance(supplied, URL):
        return supplied
    return load_database_settings().sqlalchemy_url()


def run_migrations_offline() -> None:
    context.configure(
        dialect_name="postgresql",
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_database_url(), poolclass=NullPool, hide_parameters=True)
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection, target_metadata=target_metadata, compare_type=True
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
