"""``eg-worker``: run the EvidenceGuard job worker (M3b, ADR-0008).

Exit codes, each with a fixed stderr message that never contains submitted values, URLs or
exception text:

- 0: normal stop, or ``--once`` with nothing claimable;
- 1: unexpected failure (class name only), including ``--once`` when its claim hits a
  database error;
- 2: usage error;
- 3: database configuration error (the existing URL-free message);
- 4: no job handlers are registered. Checked **before** database settings are read;
- 5: abnormal shutdown: a handler or heartbeat thread did not stop within its bounded wait.
  The process then ends with ``os._exit(5)``, so interpreter shutdown cannot block on the
  threads that are still alive. Once the runtime has returned an abnormal result, failures in
  later cleanup (engine disposal, signal restoration) or in writing diagnostics never prevent
  or downgrade this exit.

``--help`` needs no settings and no database. Signal handlers only set flags: the first SIGINT
or SIGTERM (or SIGBREAK on Windows) requests a graceful stop, a second an immediate one.
"""

import argparse
import logging
import os
import sys
from collections.abc import Callable, Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager, suppress
from typing import NoReturn

from sqlalchemy.exc import SQLAlchemyError

from evidenceguard_observability.jsonlog import configure_logging, log_event
from evidenceguard_persistence.db import create_db_engine, create_session_factory, dispose_engine
from evidenceguard_persistence.settings import DatabaseConfigurationError, load_database_settings
from evidenceguard_worker.handlers import production_registry
from evidenceguard_worker.registry import HandlerRegistry
from evidenceguard_worker.runtime import (
    LOGGER,
    DatabaseJobStore,
    JobStore,
    Timings,
    WorkerOutcome,
    WorkerResult,
    run_worker,
)
from evidenceguard_worker.shutdown import StopController, install_signal_handlers

PROG = "eg-worker"
USAGE_ERROR_MESSAGE = f"{PROG}: error: invalid arguments; run with --help for usage\n"
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")

EXIT_UNEXPECTED = 1
EXIT_CONFIGURATION = 3
EXIT_NO_HANDLERS = 4
EXIT_ABNORMAL = 5

StoreFactory = Callable[[], AbstractContextManager[JobStore]]


class SafeArgumentParser(argparse.ArgumentParser):
    """An ``ArgumentParser`` whose usage errors never echo submitted values.

    A small duplicate of ``eg-admin``'s parser, so the worker does not import the API package.
    """

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)  # static: built from the parser definition only
        self.exit(2, USAGE_ERROR_MESSAGE)


def _parser() -> argparse.ArgumentParser:
    parser = SafeArgumentParser(
        prog=PROG,
        allow_abbrev=False,
        description=(
            "Run the EvidenceGuard job worker. Uses EG_DATABASE_URL. Processes one job at a "
            "time until SIGINT or SIGTERM."
        ),
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="make one claim attempt, process at most one job, then exit",
    )
    parser.add_argument(
        "--log-level", choices=LOG_LEVELS, default="INFO", help="log level (default: INFO)"
    )
    return parser


@contextmanager
def database_store() -> Iterator[JobStore]:
    """Open the configured database for the worker and dispose the engine afterwards.

    Disposal is pool cleanup only: it does not cancel sessions checked out by threads that are
    still running.
    """
    engine = create_db_engine(load_database_settings())
    try:
        yield DatabaseJobStore(create_session_factory(engine))
    finally:
        dispose_engine(engine)


def _fail(code: int, message: str) -> int:
    print(f"{PROG}: error: {message}", file=sys.stderr)
    return code


def _flush_output() -> None:
    for handler in logging.getLogger("evidenceguard").handlers:
        handler.flush()
    sys.stdout.flush()
    sys.stderr.flush()


def _exit_abnormally(exit_process: Callable[[int], object]) -> None:
    """Best-effort fixed diagnostics, then the process exit, which they can never prevent."""
    try:
        with suppress(BaseException):
            _fail(EXIT_ABNORMAL, "a job thread did not stop in time; the process is exiting")
        with suppress(BaseException):
            _flush_output()
    finally:
        exit_process(EXIT_ABNORMAL)  # os._exit: does not return


def main(
    argv: Sequence[str] | None = None,
    *,
    registry_factory: Callable[[], HandlerRegistry] = production_registry,
    store_factory: StoreFactory = database_store,
    timings: Timings | None = None,
    exit_process: Callable[[int], object] = os._exit,
) -> int:
    args = _parser().parse_args(argv)
    configure_logging(args.log_level)

    registry = registry_factory()
    if not registry:
        log_event(LOGGER, "worker.no_handlers", logging.ERROR)
        return _fail(EXIT_NO_HANDLERS, "no job handlers are registered")

    stop = StopController()
    restore_signals = install_signal_handlers(stop)
    result: WorkerResult | None = None
    try:
        try:
            with store_factory() as store:
                result = run_worker(store, registry, stop=stop, timings=timings, once=args.once)
        finally:
            restore_signals()
    except BaseException as exc:
        if result is not None and result.outcome is WorkerOutcome.ABNORMAL:
            pass  # a cleanup failure must not downgrade or prevent the abnormal exit below
        elif not isinstance(exc, Exception):
            raise
        elif isinstance(exc, DatabaseConfigurationError):
            log_event(LOGGER, "worker.config_invalid", logging.ERROR)
            return _fail(EXIT_CONFIGURATION, str(exc))  # names the variable, never the URL
        elif isinstance(exc, SQLAlchemyError):
            return _fail(EXIT_UNEXPECTED, "the database operation failed")
        else:  # report the class name only, never its text
            return _fail(EXIT_UNEXPECTED, f"unexpected {type(exc).__name__}")

    assert result is not None  # every path without a result returned or raised above
    if result.outcome is WorkerOutcome.ABNORMAL:
        _exit_abnormally(exit_process)
        return EXIT_ABNORMAL
    if result.outcome is WorkerOutcome.CLAIM_FAILED:
        return _fail(EXIT_UNEXPECTED, "the database operation failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
