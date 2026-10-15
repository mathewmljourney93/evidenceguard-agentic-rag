"""``eg-worker`` without a database: fake stores and test-only handlers (ADR-0008).

Test handlers are defined here, never in the package. The abnormal exit is checked in a real
subprocess, because the CLI ends its process with ``os._exit(5)``.
"""

import logging
import os
import signal
import subprocess
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from importlib.metadata import entry_points
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy.exc import OperationalError

from evidenceguard_domain.jobs import JobPayload, JobSnapshot, JobStatus, LeaseLostError
from evidenceguard_persistence.settings import DATABASE_URL_ENV
from evidenceguard_worker import __main__ as cli
from evidenceguard_worker.context import JobContext
from evidenceguard_worker.handlers import production_registry
from evidenceguard_worker.ingest import INGEST_REVISION_KIND, ingest_revision
from evidenceguard_worker.registry import HandlerRegistry
from evidenceguard_worker.runtime import JobStore, Timings
from evidenceguard_worker.shutdown import StopController, install_signal_handlers

SUBMITTED_MARKER = "submitted-marker-value"  # obviously fake; stands in for a mistyped secret
T0 = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)
FAST = Timings(heartbeat_interval=0.01, lease_loss_grace=0.2, heartbeat_join=0.2, stop_check=0.01)
_LOGGER_NAMES = ("evidenceguard", "uvicorn", "uvicorn.error", "uvicorn.access")


@pytest.fixture(autouse=True)
def restore_loggers() -> Iterator[None]:
    """``main`` applies the JSON logging configuration; undo it after each test."""
    saved = {
        name: (list(lg.handlers), lg.level, lg.propagate)
        for name, lg in ((n, logging.getLogger(n)) for n in _LOGGER_NAMES)
    }
    yield
    for name, (handlers, level, propagate) in saved.items():
        logger = logging.getLogger(name)
        logger.handlers = handlers
        logger.setLevel(level)
        logger.propagate = propagate


def _job(worker_id: str) -> JobSnapshot:
    return JobSnapshot(
        id=uuid4(),
        tenant_id=uuid4(),
        kind="test_job",
        idempotency_key="key-1",
        payload=JobPayload(),
        status=JobStatus.RUNNING,
        attempt=1,
        max_attempts=3,
        run_after=T0,
        locked_by=worker_id,
        lease_expires_at=T0 + timedelta(seconds=60),
        created_at=T0,
        updated_at=T0,
    )


class ScriptedStore:
    """Only ``claim`` and ``heartbeat`` are needed by these tests."""

    def __init__(self, claim: Any = None, heartbeat_error: Exception | None = None) -> None:
        self._claim = claim
        self._heartbeat_error = heartbeat_error
        self.claims = 0

    def claim(self, worker_id: str, kinds: Any) -> JobSnapshot | None:
        self.claims += 1
        if isinstance(self._claim, Exception):
            raise self._claim
        if self._claim == "job":
            return _job(worker_id)
        return None

    def heartbeat(self, token: Any) -> JobSnapshot:
        if self._heartbeat_error is not None:
            raise self._heartbeat_error
        raise AssertionError("unexpected heartbeat")

    def fenced(self, token: Any) -> Any:
        raise AssertionError("unexpected fenced transaction")

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"unexpected store call: {name}")


def _registry() -> HandlerRegistry:
    return HandlerRegistry([("test_job", lambda ctx: None)])


def _factory(store: ScriptedStore) -> Any:
    @contextmanager
    def factory() -> Iterator[JobStore]:
        yield store

    return factory


def _no_store() -> Any:
    raise AssertionError("the store must not be opened")


# --- registration and help ------------------------------------------------------------------


def test_eg_worker_console_script_is_registered() -> None:
    (script,) = entry_points(group="console_scripts", name="eg-worker")

    assert script.value == "evidenceguard_worker.__main__:main"
    assert script.load() is cli.main


def test_help_needs_no_settings_or_database(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv(DATABASE_URL_ENV, raising=False)

    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--help"], store_factory=_no_store)

    assert exit_info.value.code == 0
    assert "usage: eg-worker" in capsys.readouterr().out


@pytest.mark.parametrize(
    "argv",
    [
        ["--log-level", SUBMITTED_MARKER],
        [SUBMITTED_MARKER],
        [f"--{SUBMITTED_MARKER}"],
        ["--once", "--once-more"],
    ],
)
def test_usage_errors_exit_two_without_echoing_values(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(argv, store_factory=_no_store)

    assert exit_info.value.code == 2
    captured = capsys.readouterr()
    assert SUBMITTED_MARKER not in captured.out + captured.err
    assert captured.err.endswith(cli.USAGE_ERROR_MESSAGE)


# --- exit codes -----------------------------------------------------------------------------


def test_the_production_registry_registers_exactly_ingest_revision() -> None:
    registry = production_registry()

    assert registry.kinds == frozenset({INGEST_REVISION_KIND}) == frozenset({"ingest_revision"})
    assert registry[INGEST_REVISION_KIND] is ingest_revision


def test_no_handlers_exit_four_before_reading_database_settings(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def forbidden() -> None:
        raise AssertionError("database settings must not be read")

    monkeypatch.setattr(cli, "load_database_settings", forbidden)
    monkeypatch.setenv(DATABASE_URL_ENV, f"postgresql://{SUBMITTED_MARKER}")

    # The production registry is no longer empty (M3d); an empty one is injected.
    assert cli.main([], registry_factory=HandlerRegistry) == 4
    err = capsys.readouterr().err
    assert "eg-worker: error: no job handlers are registered" in err
    assert '"event":"worker.no_handlers"' in err
    assert SUBMITTED_MARKER not in err


@pytest.mark.parametrize(
    ("value", "problem"),
    [(None, "is not set"), (f"mysql://{SUBMITTED_MARKER}@host/db", "is not a valid")],
)
def test_database_configuration_errors_exit_three_without_the_url(
    value: str | None,
    problem: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    if value is None:
        monkeypatch.delenv(DATABASE_URL_ENV, raising=False)
    else:
        monkeypatch.setenv(DATABASE_URL_ENV, value)

    assert cli.main(["--once"], registry_factory=_registry) == 3
    err = capsys.readouterr().err
    assert f"eg-worker: error: {DATABASE_URL_ENV} {problem}" in err
    assert '"event":"worker.config_invalid"' in err
    assert SUBMITTED_MARKER not in err


def test_once_with_nothing_claimable_exits_zero() -> None:
    store = ScriptedStore()

    assert cli.main(["--once"], registry_factory=_registry, store_factory=_factory(store)) == 0
    assert store.claims == 1


def test_once_with_a_claim_database_error_exits_one(capsys: pytest.CaptureFixture[str]) -> None:
    store = ScriptedStore(claim=OperationalError("SELECT", {}, Exception(SUBMITTED_MARKER)))

    assert cli.main(["--once"], registry_factory=_registry, store_factory=_factory(store)) == 1
    err = capsys.readouterr().err
    assert "eg-worker: error: the database operation failed" in err
    assert SUBMITTED_MARKER not in err
    assert store.claims == 1


def test_unexpected_failures_exit_one_with_the_class_name_only(
    capsys: pytest.CaptureFixture[str],
) -> None:
    store = ScriptedStore(claim=RuntimeError(SUBMITTED_MARKER))

    assert cli.main(["--once"], registry_factory=_registry, store_factory=_factory(store)) == 1
    err = capsys.readouterr().err
    assert "eg-worker: error: unexpected RuntimeError" in err
    assert SUBMITTED_MARKER not in err


def test_an_abnormal_result_ends_the_process_with_code_five(
    capsys: pytest.CaptureFixture[str],
) -> None:
    release = threading.Event()
    exits: list[int] = []

    def uncooperative(ctx: JobContext) -> None:
        release.wait(30)

    store = ScriptedStore(claim="job", heartbeat_error=LeaseLostError())
    try:
        code = cli.main(
            ["--once"],
            registry_factory=lambda: HandlerRegistry([("test_job", uncooperative)]),
            store_factory=_factory(store),
            timings=FAST,
            exit_process=exits.append,
        )
    finally:
        release.set()

    assert (code, exits) == (5, [5])
    assert "a job thread did not stop in time" in capsys.readouterr().err


ABNORMAL_SCRIPT = """
import sys
import threading
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from evidenceguard_domain.jobs import JobPayload, JobSnapshot, JobStatus, LeaseLostError
from evidenceguard_worker import __main__ as cli
from evidenceguard_worker.registry import HandlerRegistry
from evidenceguard_worker.runtime import Timings

T0 = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)


class Store:
    def claim(self, worker_id, kinds):
        return JobSnapshot(
            id=uuid4(), tenant_id=uuid4(), kind="test_job", idempotency_key="key-1",
            payload=JobPayload(), status=JobStatus.RUNNING, attempt=1, max_attempts=3,
            run_after=T0, locked_by=worker_id, lease_expires_at=T0 + timedelta(seconds=60),
            created_at=T0, updated_at=T0,
        )

    def heartbeat(self, token):
        raise LeaseLostError()

    def fenced(self, token):
        raise AssertionError("unexpected fenced transaction")


MODE = sys.argv[1]


def boom(*args):
    raise RuntimeError("cleanup failure marker")


@contextmanager
def store_factory():
    try:
        yield Store()
    finally:
        if MODE == "dispose":
            boom()


if MODE == "restore":
    cli.install_signal_handlers = lambda stop: boom
if MODE == "flush":
    cli._flush_output = boom

# A non-daemon thread that never ends: a normal interpreter exit would wait for it forever.
threading.Thread(target=threading.Event().wait, name="never-ends").start()
cli.main(
    ["--once"],
    registry_factory=lambda: HandlerRegistry([("test_job", lambda ctx: threading.Event().wait())]),
    store_factory=store_factory,
    timings=Timings(heartbeat_interval=0.01, lease_loss_grace=0.2, heartbeat_join=0.2),
)
raise SystemExit("unreachable: main should have ended the process")
"""


@pytest.mark.parametrize("failure", ["none", "dispose", "restore", "flush"])
def test_the_cli_process_really_exits_with_code_five_after_an_abnormal_result(
    failure: str,
) -> None:
    env = {key: value for key, value in os.environ.items() if key != DATABASE_URL_ENV}

    completed = subprocess.run(
        [sys.executable, "-c", ABNORMAL_SCRIPT, failure],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
        check=False,
    )

    assert completed.returncode == 5
    assert "a job thread did not stop in time" in completed.stderr
    assert '"event":"worker.abnormal_stop"' in completed.stderr
    assert '"error_type":"HandlerStillRunning"' in completed.stderr
    assert "unreachable" not in completed.stderr
    assert "cleanup failure marker" not in completed.stderr


def _failing_cleanup(monkeypatch: pytest.MonkeyPatch, failure: str, store: ScriptedStore) -> Any:
    def boom(*args: Any) -> None:
        raise RuntimeError(SUBMITTED_MARKER)

    if failure == "restore":
        monkeypatch.setattr(cli, "install_signal_handlers", lambda stop: boom)
    if failure == "flush":
        monkeypatch.setattr(cli, "_flush_output", boom)

    @contextmanager
    def factory() -> Iterator[JobStore]:
        try:
            yield store
        finally:
            if failure == "dispose":
                boom()

    return factory


@pytest.mark.parametrize("failure", ["dispose", "restore", "flush"])
def test_cleanup_failures_never_prevent_the_abnormal_exit(
    failure: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    release = threading.Event()
    exits: list[int] = []
    store = ScriptedStore(claim="job", heartbeat_error=LeaseLostError())

    def uncooperative(ctx: JobContext) -> None:
        release.wait(30)

    try:
        code = cli.main(
            ["--once"],
            registry_factory=lambda: HandlerRegistry([("test_job", uncooperative)]),
            store_factory=_failing_cleanup(monkeypatch, failure, store),
            timings=FAST,
            exit_process=exits.append,
        )
    finally:
        release.set()

    assert (code, exits) == (5, [5])
    assert SUBMITTED_MARKER not in capsys.readouterr().err


def test_a_cleanup_failure_after_a_normal_stop_is_reported_not_hidden(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exits: list[int] = []
    store = ScriptedStore()

    code = cli.main(
        ["--once"],
        registry_factory=_registry,
        store_factory=_failing_cleanup(monkeypatch, "dispose", store),
        exit_process=exits.append,
    )

    assert (code, exits) == (1, [])
    err = capsys.readouterr().err
    assert "eg-worker: error: unexpected RuntimeError" in err
    assert SUBMITTED_MARKER not in err


# --- signals ----------------------------------------------------------------------------------


def test_signal_handlers_escalate_and_restore() -> None:
    previous = signal.getsignal(signal.SIGINT)
    stop = StopController()
    restore = install_signal_handlers(stop)
    try:
        handler = signal.getsignal(signal.SIGINT)
        assert callable(handler)
        handler(signal.SIGINT, None)
        assert (stop.requested, stop.immediate) == (True, False)
        handler(signal.SIGINT, None)
        assert stop.immediate
        if hasattr(signal, "SIGBREAK"):
            assert signal.getsignal(signal.SIGBREAK) is handler
    finally:
        restore()
    assert signal.getsignal(signal.SIGINT) is previous


@pytest.mark.skipif(sys.platform == "win32", reason="raise_signal(SIGTERM) ends a Windows process")
def test_a_delivered_sigterm_requests_a_graceful_stop() -> None:
    stop = StopController()
    restore = install_signal_handlers(stop)
    try:
        signal.raise_signal(signal.SIGTERM)
    finally:
        restore()

    assert (stop.requested, stop.immediate) == (True, False)


def test_signal_handlers_are_installed_only_from_the_main_thread() -> None:
    errors: list[BaseException] = []

    def install() -> None:
        try:
            install_signal_handlers(StopController())
        except RuntimeError as error:
            errors.append(error)

    thread = threading.Thread(target=install)
    thread.start()
    thread.join(10)

    assert len(errors) == 1
