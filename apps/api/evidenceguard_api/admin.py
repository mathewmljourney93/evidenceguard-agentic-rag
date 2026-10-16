"""``eg-admin``: account administration commands (ADR-0005).

- ``seed-demo``: create the synthetic two-tenant, three-role demo fixture. Idempotent; it
  never changes existing rows and never creates API keys.
- ``create-key --tenant-id T --user-id U``: create a key for a user that must belong to T.
  The plaintext key is printed once, to stdout, only after the database transaction commits.
- ``revoke-key --tenant-id T --prefix P``: mark the tenant's key revoked; the row is kept.
- ``backfill-indexes --tenant-id T [--limit N] [--after R]`` (M4c, ADR-0015): enqueue offline
  (``HASH_IDENTITY``) indexing for one bounded page of the tenant's active revisions, as a
  fixed system actor with role admin. It prints only fixed outcome counts and the next cursor,
  and exits 0 for a clean page, 3 for a page containing ``stalled``, ``ineligible`` or
  ``conflict`` items, 1 on failure and 2 on a usage error. It never retries or resets a job.

The commands never take a secret as an argument. ``--help`` and importing this module need no
database settings: the database is opened only when a command runs. Failures print a fixed,
generic message to stderr and exit 1; no URL, credential or exception text is printed.

Usage errors (invalid UUIDs, unknown commands or options, extra or missing arguments) are
handled by ``SafeArgumentParser`` in the root parser and every subparser: it prints only the
static usage line and a fixed message, and exits 2 before any database is opened. argparse's own
diagnostics are never printed, because they quote the offending values, which could be a key
pasted by mistake.
"""

import argparse
import sys
from collections.abc import Callable, Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager
from typing import NoReturn, Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_persistence.accounts import (
    AccountError,
    DatabaseAdminStore,
    DemoUser,
    RevokeOutcome,
)
from evidenceguard_persistence.credentials import NewApiKey, generate_api_key, is_valid_prefix
from evidenceguard_persistence.db import create_db_engine, create_session_factory, dispose_engine
from evidenceguard_persistence.indexing import (
    DEFAULT_BACKFILL_LIMIT,
    MAX_BACKFILL_LIMIT,
    BackfillOutcome,
    BackfillPage,
    backfill_index_revisions,
)
from evidenceguard_persistence.settings import DatabaseConfigurationError, load_database_settings
from evidenceguard_retrieval.embeddings import HASH_IDENTITY

PROG = "eg-admin"
USAGE_ERROR_MESSAGE = f"{PROG}: error: invalid arguments; run with --help for usage\n"
EXIT_ATTENTION = 3
ATTENTION_OUTCOMES = frozenset(
    {BackfillOutcome.STALLED, BackfillOutcome.INELIGIBLE, BackfillOutcome.CONFLICT}
)
SYSTEM_ACTOR_ID = uuid5(NAMESPACE_URL, "https://evidenceguard.invalid/actors/eg-admin/v1")
"""The fixed actor ID ``eg-admin backfill-indexes`` acts as (role admin, the given tenant)."""


class AdminStore(Protocol):
    def seed_demo(self) -> tuple[DemoUser, ...]: ...

    def create_api_key(self, tenant_id: UUID, user_id: UUID, key: NewApiKey) -> UUID: ...

    def revoke_api_key(self, tenant_id: UUID, prefix: str) -> RevokeOutcome: ...

    def backfill_indexes(
        self, tenant_id: UUID, *, limit: int, after: UUID | None
    ) -> BackfillPage: ...


StoreFactory = Callable[[], AbstractContextManager[AdminStore]]


class DatabaseStore(DatabaseAdminStore):
    """The account store plus M4c's backfill seam, for one command's database."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        super().__init__(session_factory)
        self._backfill_factory = session_factory

    def backfill_indexes(self, tenant_id: UUID, *, limit: int, after: UUID | None) -> BackfillPage:
        actor = ActorContext(tenant_id=tenant_id, actor_id=SYSTEM_ACTOR_ID, role=Role.ADMIN)
        return backfill_index_revisions(
            self._backfill_factory, actor, identity=HASH_IDENTITY, limit=limit, after=after
        )


@contextmanager
def database_store() -> Iterator[AdminStore]:
    """Open the configured database for one command and dispose the engine afterwards."""
    engine = create_db_engine(load_database_settings())
    try:
        yield DatabaseStore(create_session_factory(engine))
    finally:
        dispose_engine(engine)


class SafeArgumentParser(argparse.ArgumentParser):
    """An ``ArgumentParser`` whose usage errors never echo submitted values.

    Subparsers created through ``add_subparsers`` inherit this class, so every command is
    covered. ``--help`` output is static and unaffected.
    """

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)  # static: built from the parser definition only
        self.exit(2, USAGE_ERROR_MESSAGE)


def _parser() -> argparse.ArgumentParser:
    parser = SafeArgumentParser(
        prog=PROG,
        allow_abbrev=False,
        description="Administer EvidenceGuard tenants, users and API keys. Uses EG_DATABASE_URL.",
    )
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    commands.add_parser(
        "seed-demo",
        allow_abbrev=False,
        help="create the synthetic demo tenants and users (idempotent; creates no keys)",
    )
    create = commands.add_parser(
        "create-key",
        allow_abbrev=False,
        help="create an API key for a user and print it once",
        description="Create an API key. The key is printed once, to stdout, after it is stored.",
    )
    create.add_argument("--tenant-id", type=UUID, required=True, help="the user's tenant")
    create.add_argument("--user-id", type=UUID, required=True, help="the user to own the key")
    revoke = commands.add_parser(
        "revoke-key",
        allow_abbrev=False,
        help="revoke an API key (the record is kept)",
        description="Revoke a tenant's API key, identified by its public prefix.",
    )
    revoke.add_argument("--tenant-id", type=UUID, required=True, help="the key's tenant")
    revoke.add_argument(
        "--prefix", required=True, help="the key's 16-character public prefix (not the secret)"
    )
    backfill = commands.add_parser(
        "backfill-indexes",
        allow_abbrev=False,
        help="enqueue offline indexing for one page of a tenant's active revisions",
        description=(
            "Enqueue offline (lexical-hash) indexing for one bounded page of the tenant's active "
            "revisions. Prints outcome counts and the next cursor. Exit 0: clean page; 3: page "
            "with stalled, ineligible or conflict items; 1: failure; 2: usage error."
        ),
    )
    backfill.add_argument("--tenant-id", type=UUID, required=True, help="the tenant to backfill")
    backfill.add_argument(
        "--limit",
        type=_limit,
        default=DEFAULT_BACKFILL_LIMIT,
        help=f"revisions in this page (1-{MAX_BACKFILL_LIMIT}, default {DEFAULT_BACKFILL_LIMIT})",
    )
    backfill.add_argument(
        "--after", type=UUID, default=None, help="the cursor printed by the previous page"
    )
    return parser


def _limit(value: str) -> int:
    """A backfill page size; invalid values become a safe usage error."""
    if not value.isascii() or not value.isdigit():
        raise argparse.ArgumentTypeError("invalid limit")
    limit = int(value)
    if not 1 <= limit <= MAX_BACKFILL_LIMIT:
        raise argparse.ArgumentTypeError("invalid limit")
    return limit


def _fail(message: str) -> int:
    print(f"{PROG}: error: {message}", file=sys.stderr)
    return 1


def _seed_demo(store: AdminStore) -> int:
    for user in store.seed_demo():
        state = "created" if user.created else "existing"
        print(
            f"tenant={user.tenant_slug} tenant_id={user.tenant_id} "
            f"role={user.role.value} user_id={user.user_id} {state}"
        )
    return 0


def _create_key(store: AdminStore, tenant_id: UUID, user_id: UUID) -> int:
    key = generate_api_key()
    key_id = store.create_api_key(tenant_id, user_id, key)
    # Reached only after the transaction committed. The plaintext is never shown again.
    print(key.plaintext.get_secret_value())
    print(
        f"created key prefix={key.prefix} key_id={key_id}; store it now, it cannot be shown again",
        file=sys.stderr,
    )
    return 0


def _revoke_key(store: AdminStore, tenant_id: UUID, prefix: str) -> int:
    outcome = store.revoke_api_key(tenant_id, prefix)
    if outcome is RevokeOutcome.NOT_FOUND:
        return _fail("no such key in that tenant")
    print("revoked" if outcome is RevokeOutcome.REVOKED else "already revoked")
    return 0


def _backfill_indexes(store: AdminStore, tenant_id: UUID, limit: int, after: UUID | None) -> int:
    page = store.backfill_indexes(tenant_id, limit=limit, after=after)
    counts = {outcome: 0 for outcome in BackfillOutcome}
    for item in page.items:
        counts[item.outcome] += 1
    print(" ".join(f"{outcome.value}={counts[outcome]}" for outcome in BackfillOutcome))
    print(f"next_after={page.next_after if page.next_after is not None else '-'}")
    return EXIT_ATTENTION if any(counts[outcome] for outcome in ATTENTION_OUTCOMES) else 0


def main(argv: Sequence[str] | None = None, *, store_factory: StoreFactory | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "revoke-key" and not is_valid_prefix(args.prefix):
        return _fail("--prefix must be 16 lowercase hexadecimal characters")
    factory = store_factory or database_store
    try:
        with factory() as store:
            if args.command == "seed-demo":
                return _seed_demo(store)
            if args.command == "create-key":
                return _create_key(store, args.tenant_id, args.user_id)
            if args.command == "backfill-indexes":
                return _backfill_indexes(store, args.tenant_id, args.limit, args.after)
            return _revoke_key(store, args.tenant_id, args.prefix)
    except DatabaseConfigurationError as exc:
        return _fail(str(exc))  # names the variable, never the URL
    except AccountError as exc:
        return _fail(str(exc))  # fixed messages only
    except SQLAlchemyError:
        return _fail("the database operation failed")
    except Exception as exc:  # report the class name only, never its text
        return _fail(f"unexpected {type(exc).__name__}")


if __name__ == "__main__":
    sys.exit(main())
