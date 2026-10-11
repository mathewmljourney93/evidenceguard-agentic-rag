"""Alembic configuration that works from the source checkout and from an installed wheel.

The migration scripts ship inside this package (``evidenceguard_persistence/migrations``), so
``alembic_config()`` needs no ``alembic.ini`` file. A database URL can be passed in directly;
otherwise online migrations read ``EG_DATABASE_URL``. Offline (``--sql``) generation needs no
URL and does not connect to a database.
"""

from typing import TextIO

from alembic.config import Config
from sqlalchemy.engine import URL

SCRIPT_LOCATION = "evidenceguard_persistence:migrations"
DATABASE_URL_ATTRIBUTE = "database_url"


def alembic_config(
    *, database_url: URL | None = None, output_buffer: TextIO | None = None
) -> Config:
    """Build an Alembic ``Config`` for EvidenceGuard's packaged migrations.

    The URL is passed through ``Config.attributes``, never written into Alembic's ini options,
    so credentials are not exposed through configuration dumps.
    """
    config = Config(output_buffer=output_buffer)
    config.set_main_option("script_location", SCRIPT_LOCATION)
    if database_url is not None:
        config.attributes[DATABASE_URL_ATTRIBUTE] = database_url
    return config
