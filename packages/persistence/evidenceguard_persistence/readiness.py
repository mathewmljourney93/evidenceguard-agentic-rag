"""Database readiness: reachable, and migrated to exactly the packaged Alembic heads (ADR-0006).

``check_readiness`` opens one connection, bounds the transaction with a short
``statement_timeout``, runs ``SELECT 1`` and reads the applied revisions from
``alembic_version`` through Alembic's ``MigrationContext``, which reports an empty set when the
table does not exist and never creates it. Nothing is written, migrated or installed, and the
transaction is rolled back.

The result is two booleans. Callers expose only fixed check names and states: never URLs,
revision identifiers, SQL or exception text. Any exception while probing counts as "database
not reachable".
"""

from collections.abc import Callable, Collection
from dataclasses import dataclass
from functools import cache

from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, text

from evidenceguard_persistence.migration_config import alembic_config

READINESS_STATEMENT_TIMEOUT_MS = 2000


@dataclass(frozen=True)
class ReadinessResult:
    """``migrations`` is ``None`` when the database could not be checked at all."""

    database: bool
    migrations: bool | None

    @property
    def ready(self) -> bool:
        return self.database and self.migrations is True


@cache
def packaged_migration_heads() -> frozenset[str]:
    """The head revisions shipped with this package (read from files; no database)."""
    return frozenset(ScriptDirectory.from_config(alembic_config()).get_heads())


def applied_revisions(engine: Engine) -> tuple[str, ...]:
    """Connect, prove the connection works and return the applied revisions (may be empty)."""
    with engine.connect() as connection:
        connection.execute(text(f"SET LOCAL statement_timeout = {READINESS_STATEMENT_TIMEOUT_MS}"))
        connection.execute(text("SELECT 1"))
        revisions = tuple(MigrationContext.configure(connection).get_current_heads())
        connection.rollback()
    return revisions


def evaluate_readiness(
    probe: Callable[[], Collection[str]], expected_heads: frozenset[str]
) -> ReadinessResult:
    try:
        applied = frozenset(probe())
    except Exception:  # unreachable, timed out, refused: the reason is never exposed
        return ReadinessResult(database=False, migrations=None)
    return ReadinessResult(database=True, migrations=bool(applied) and applied == expected_heads)


def check_readiness(engine: Engine) -> ReadinessResult:
    return evaluate_readiness(lambda: applied_revisions(engine), packaged_migration_heads())
