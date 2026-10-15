"""The M3f CI helper (``infra/ci/container_ci.py``) without Docker (ADR-0012).

The smoke test, cleanup and configuration validation run against fake subprocess and HTTP
functions, so failure handling, timeouts, redaction and failure precedence are exercised here.
The real container checks run only in CI.
"""

import importlib.util
import json
import sys
import threading
from collections.abc import Callable, Iterator, Mapping, Sequence
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
KEY = "egk_SmokePrefix0001_synthetic-secret-value-for-tests"
IMAGE_ID = "sha256:" + "ab" * 32
PROJECT = "eg-ci-123-1"
IMAGE = "evidenceguard:ci-123-1"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("container_ci", ROOT / "infra/ci/container_ci.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["container_ci"] = module
    spec.loader.exec_module(module)
    return module


ci = _load()


# --- fakes ----------------------------------------------------------------------------------------


class FakeDocker:
    """Answers the smoke test's docker commands; records every call with its timeout."""

    def __init__(self) -> None:
        self.calls: list[tuple[list[str], float]] = []
        self.overrides: dict[str, Callable[[list[str]], Any]] = {}
        self.worker_state = "exited 0 false"
        self.logs: dict[str, str] = {}
        self.image_ids: dict[str, str] = {}

    def __call__(self, args: Sequence[str], timeout: float) -> Any:
        command = list(args)
        self.calls.append((command, timeout))
        text = " ".join(command)
        for marker, handler in self.overrides.items():
            if marker in text:
                return handler(command)
        result = ci.Result
        if command[:2] == ["docker", "pull"]:
            return result(0, "pulled\n", "")
        if " up " in f" {text} ":
            return result(0, "", "")
        if "ps -a -q" in text:
            return result(0, f"cid-{command[-1]}\n", "")
        if "{{.Image}}" in text:
            return result(0, self.image_ids.get(command[-1], IMAGE_ID) + "\n", "")
        if "seed-demo" in text:
            seed = (
                "tenant=demo-a tenant_id=11111111-1111-5111-8111-111111111111 role=approver "
                "user_id=22222222-2222-5222-8222-222222222222 created\n"
                "tenant=demo-a tenant_id=11111111-1111-5111-8111-111111111111 role=reviewer "
                "user_id=33333333-3333-5333-8333-333333333333 created\n"
            )
            return result(0, seed, "")
        if "create-key" in text:
            return result(0, KEY + "\n", "created key prefix=SmokePrefix0001 key_id=x\n")
        if " stop " in f" {text} ":
            return result(0, "", "")
        if "{{.State.Status}}" in text:
            return result(0, self.worker_state + "\n", "")
        if " logs " in f" {text} ":
            return result(0, self.logs.get(command[-1], f"{command[-1]} log line\n"), "")
        if "ps -a" in text:
            return result(0, "NAME STATUS\n", "")
        raise AssertionError(f"unexpected command {command}")


class FakeApi:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, Mapping[str, str], float]] = []
        self.uploads = 0
        self.job_statuses = ["queued", "running", "succeeded"]
        self.overrides: dict[str, Any] = {}

    def __call__(
        self, method: str, url: str, headers: Mapping[str, str], body: bytes | None, timeout: float
    ) -> Any:
        path = url.removeprefix(ci.API_URL)
        self.calls.append((method, path, dict(headers), timeout))
        response = ci.Response
        for marker, value in self.overrides.items():
            if marker in path:
                if isinstance(value, Exception):
                    raise value
                return value
        if method == "POST" and path == "/v1/vendors":
            return response(201, {"id": "vendor-1"})
        if method == "POST" and path.endswith("/documents"):
            self.uploads += 1
            if self.uploads == 1:
                return response(
                    202, {"document_id": "doc-1", "revision_id": "rev-1", "job": {"id": "job-1"}}
                )
            return response(200, {"created": False, "revision_id": "rev-1"})
        if path == "/v1/jobs/job-1":
            status = (
                self.job_statuses.pop(0) if len(self.job_statuses) > 1 else self.job_statuses[0]
            )
            return response(200, {"status": status})
        if path == "/v1/documents/doc-1":
            return response(
                200,
                {"active_revision_id": "rev-1", "active_revision": {"ingestion_state": "active"}},
            )
        if path.endswith("/chunks"):
            return response(
                200,
                {"chunk_set": {"verified_complete": True, "chunk_count": 3, "stored_count": 3}},
            )
        raise AssertionError(f"unexpected request {method} {path}")


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def smoke(docker: FakeDocker, api: FakeApi, clock: Clock | None = None) -> tuple[Any, list[str]]:
    output: list[str] = []
    clock = clock or Clock()
    instance = ci.Smoke(
        project=PROJECT,
        image_id=IMAGE_ID,
        runner=docker,
        http=api,
        clock=clock,
        sleep=clock.sleep,
        out=output.append,
    )
    return instance, output


def lines_with_key(output: list[str]) -> list[str]:
    return [line for line in output if KEY in line]


# --- the smoke test -------------------------------------------------------------------------------


def test_a_successful_smoke_publishes_the_key_only_as_a_mask_command() -> None:
    docker, api = FakeDocker(), FakeApi()
    instance, output = smoke(docker, api)

    assert instance.run() == 0
    assert output[-1] == "smoke: ok"
    assert lines_with_key(output) == [f"::add-mask::{KEY}"]
    assert all(KEY not in text for text in instance.captured.values())
    assert "smoke: idle worker exited with code 0 (no OOM kill)" in output


def test_every_command_and_request_has_its_own_timeout() -> None:
    docker, api = FakeDocker(), FakeApi()
    instance, _ = smoke(docker, api)
    instance.run()

    assert docker.calls and all(0 < timeout <= ci.PULL_TIMEOUT for _, timeout in docker.calls)
    assert api.calls and all(timeout == ci.HTTP_TIMEOUT for *_, timeout in api.calls)
    pulls = [command for command, _ in docker.calls if command[:2] == ["docker", "pull"]]
    assert pulls == [["docker", "pull", ci.PG_IMAGE]]
    up = next(command for command, _ in docker.calls if "up" in command)
    assert {"--no-build", "--wait"} <= set(up) and up[up.index("--pull") + 1] == "never"
    assert all(
        command[:6] == ["docker", "compose", "-f", "docker-compose.yml", "-p", PROJECT]
        for command, _ in docker.calls
        if command[:2] == ["docker", "compose"]
    )


def test_a_key_in_service_logs_fails_without_exposing_it() -> None:
    docker, api = FakeDocker(), FakeApi()
    docker.logs["worker"] = f"something logged Authorization: Bearer {KEY}\n"
    instance, output = smoke(docker, api)

    assert instance.run() == 1
    assert output[-1] == (
        "smoke: FAILED: generated key found in captured service logs "
        "(service=worker, occurrences=1)"
    )
    assert lines_with_key(output) == [f"::add-mask::{KEY}"]
    assert all("Authorization: Bearer" not in line for line in output)  # logs hidden on success


def test_diagnostics_are_redacted_and_the_first_failure_is_kept() -> None:
    docker, api = FakeDocker(), FakeApi()
    api.overrides["/chunks"] = ci.Response(500, None)
    docker.logs["api"] = f"Traceback ... token={KEY}\n"

    def failing_logs(command: list[str]) -> Any:
        if command[-1] == "postgres":
            raise ci.CheckFailed("timed out after 60 s")
        return docker.__class__.__call__(_without_override(docker), command, 1)

    docker.overrides[" logs "] = failing_logs
    instance, output = smoke(docker, api)

    assert instance.run() == 1
    assert output[-1] == "smoke: FAILED: chunks: HTTP 500, expected 200"
    assert (
        "smoke: secondary: service logs unavailable (logs postgres: timed out after 60 s)" in output
    )
    assert any(
        "generated key found in captured service logs (service=api" in line for line in output
    )
    assert any(f"token={ci.Redactor.MARK}" in line for line in output)  # shown, redacted
    assert lines_with_key(output) == [f"::add-mask::{KEY}"]


def _without_override(docker: FakeDocker) -> FakeDocker:
    plain = FakeDocker()
    plain.logs = docker.logs
    return plain


def test_a_startup_failure_is_reported_first_even_if_diagnostics_fail() -> None:
    docker, api = FakeDocker(), FakeApi()
    docker.overrides[" up "] = lambda command: ci.Result(1, "", "dependency failed to start")

    def broken(command: list[str]) -> Any:
        raise ci.CheckFailed("timed out after 60 s")

    docker.overrides[" logs "] = broken
    instance, output = smoke(docker, api)

    assert instance.run() == 1
    assert output[-1] == "smoke: FAILED: compose up: exit status 1"
    assert sum("smoke: secondary: service logs unavailable" in line for line in output) == len(
        ci.ALL_SERVICES
    )
    assert not lines_with_key(output)  # the key was never created


@pytest.mark.parametrize(
    ("state", "reason"),
    [
        ("exited 137 false", "137"),
        ("exited 0 true", "true"),
        ("exited 5 false", "5"),
        ("running 0 false", "running"),
    ],
)
def test_the_worker_must_exit_cleanly(state: str, reason: str) -> None:
    docker, api = FakeDocker(), FakeApi()
    docker.worker_state = state
    instance, output = smoke(docker, api)

    assert instance.run() == 1
    assert output[-1].startswith("smoke: FAILED: worker stop: expected status exited")
    assert reason in output[-1]


def test_a_successful_stop_command_alone_is_not_accepted() -> None:
    docker, api = FakeDocker(), FakeApi()
    instance, _ = smoke(docker, api)
    instance.run()
    commands = [" ".join(command) for command, _ in docker.calls]
    stop = next(index for index, text in enumerate(commands) if " stop -t 60 worker" in text)
    assert "{{.State.Status}} {{.State.ExitCode}} {{.State.OOMKilled}}" in commands[stop + 1]


def test_containers_must_run_the_ci_built_image() -> None:
    docker, api = FakeDocker(), FakeApi()
    docker.image_ids["cid-worker"] = "sha256:" + "cd" * 32
    instance, output = smoke(docker, api)

    assert instance.run() == 1
    assert output[-1] == "smoke: FAILED: worker: container does not run the CI-built image"


def test_ingestion_has_a_polling_deadline() -> None:
    docker, api, clock = FakeDocker(), FakeApi(), Clock()
    api.job_statuses = ["queued"]
    instance, output = smoke(docker, api, clock)

    assert instance.run() == 1
    assert output[-1] == "smoke: FAILED: ingestion: not succeeded within 90 s"
    polls = [path for _, path, *_ in api.calls if path == "/v1/jobs/job-1"]
    assert len(polls) == ci.INGESTION_DEADLINE // ci.POLL_INTERVAL + 1


def test_a_dead_job_fails_immediately() -> None:
    docker, api = FakeDocker(), FakeApi()
    api.job_statuses = ["dead"]
    instance, output = smoke(docker, api)
    assert instance.run() == 1
    assert output[-1] == "smoke: FAILED: ingestion: job ended as dead"


def test_unexpected_create_key_output_is_never_echoed() -> None:
    docker, api = FakeDocker(), FakeApi()
    leaked = "not-a-key but private text"
    docker.overrides["create-key"] = lambda command: ci.Result(0, leaked + "\n", "")
    instance, output = smoke(docker, api)

    assert instance.run() == 1
    assert output[-1] == "smoke: FAILED: create-key: output did not have the expected key format"
    assert all(leaked not in line for line in output)


def test_http_failures_report_only_fixed_text() -> None:
    docker, api = FakeDocker(), FakeApi()
    api.overrides["/v1/vendors"] = ci.CheckFailed("request failed (TimeoutError)")
    instance, output = smoke(docker, api)
    assert instance.run() == 1
    assert output[-1] == "smoke: FAILED: create vendor: request failed (TimeoutError)"


def test_unexpected_exceptions_report_only_their_class() -> None:
    docker, api = FakeDocker(), FakeApi()
    api.overrides["/v1/documents/doc-1"] = RuntimeError(f"boom {KEY}")
    instance, output = smoke(docker, api)
    assert instance.run() == 1
    assert output[-1] == "smoke: FAILED: unexpected error (RuntimeError)"
    assert lines_with_key(output) == [f"::add-mask::{KEY}"]


# --- subprocess and HTTP helpers ------------------------------------------------------------------


def test_run_process_captures_output() -> None:
    result = ci.run_process([sys.executable, "-c", "print('out'); import sys; sys.exit(3)"], 30)
    assert (result.returncode, result.stdout.strip()) == (3, "out")


def test_run_process_times_out_without_echoing_arguments() -> None:
    secret_arg = "argument-that-must-not-be-echoed"
    with pytest.raises(ci.CheckFailed) as caught:
        ci.run_process([sys.executable, "-c", f"import time; time.sleep(30)  # {secret_arg}"], 0.5)
    assert str(caught.value) == "timed out after 0.5 s"


def test_run_process_reports_a_missing_executable_by_class_only() -> None:
    with pytest.raises(ci.CheckFailed) as caught:
        ci.run_process(["eg-definitely-missing-executable"], 5)
    assert str(caught.value).startswith("could not start (")
    assert "eg-definitely-missing-executable" not in str(caught.value)


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/ok":
            body = json.dumps({"status": "ready"}).encode()
            self.send_response(200)
        else:
            body = json.dumps({"detail": "private body text"}).encode()
            self.send_response(503)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        pass


@pytest.fixture
def server() -> Iterator[str]:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_http_request_returns_status_and_json(server: str) -> None:
    assert ci.http_request("GET", f"{server}/ok", {}, None, 5) == ci.Response(
        200, {"status": "ready"}
    )


def test_http_errors_never_expose_their_body(server: str) -> None:
    assert ci.http_request("GET", f"{server}/fail", {}, None, 5) == ci.Response(503, None)


def test_http_connection_failures_name_only_the_class() -> None:
    with pytest.raises(ci.CheckFailed) as caught:
        ci.http_request("GET", "http://127.0.0.1:9/unreachable", {}, None, 2)
    assert str(caught.value).startswith("request failed (")


def test_redactor() -> None:
    redactor = ci.Redactor()
    redactor.add("")
    assert redactor.redact("nothing") == "nothing"
    redactor.add(KEY)
    assert redactor.redact(f"a {KEY} b {KEY}") == f"a {ci.Redactor.MARK} b {ci.Redactor.MARK}"
    assert redactor.count(f"{KEY}{KEY}") == 2


# --- Compose configuration ------------------------------------------------------------------------


def good_config() -> dict[str, Any]:
    app = {
        "image": IMAGE,
        "pull_policy": "never",
        "read_only": True,
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges:true"],
        "init": True,
        "restart": "no",
        "tmpfs": ["/tmp"],
        "environment": {
            "EG_DATABASE_URL": "postgresql+psycopg://u:p@postgres:5432/evidenceguard_dev"
        },
    }
    after = {
        "postgres": {"condition": "service_healthy"},
        "migrate": {"condition": "service_completed_successfully"},
    }
    return {
        "services": {
            "postgres": {
                "image": ci.PG_IMAGE,
                "ports": [{"host_ip": "127.0.0.1", "published": "5433", "target": 5432}],
            },
            "migrate": {
                **app,
                "command": ["alembic", "-c", "/app/alembic.ini", "upgrade", "head"],
                "depends_on": {"postgres": {"condition": "service_healthy"}},
            },
            "api": {
                **app,
                "command": ["eg-api", "--host", "0.0.0.0", "--port", "8000"],
                "depends_on": after,
                "ports": [{"host_ip": "127.0.0.1", "published": "8000", "target": 8000}],
                "healthcheck": {"test": ["CMD", "python", "-c", "... /readyz ..."]},
            },
            "worker": {
                **app,
                "command": ["eg-worker"],
                "depends_on": after,
                "stop_signal": "SIGTERM",
                "stop_grace_period": "1m0s",
            },
        }
    }


def test_a_valid_configuration_passes() -> None:
    assert ci.validate_config(good_config(), IMAGE) == []


@pytest.mark.parametrize(
    ("mutate", "problem"),
    [
        (
            lambda c: c["services"]["api"]["ports"][0].update(host_ip="0.0.0.0"),
            "api: host ports must bind 127.0.0.1 only",
        ),
        (
            lambda c: c["services"]["worker"].update(pull_policy="missing"),
            "worker: pull_policy must be never",
        ),
        (
            lambda c: c["services"]["migrate"].update(image="evidenceguard:other"),
            "migrate: image must be the selected application image",
        ),
        (
            lambda c: c["services"]["api"].update(command=["alembic", "upgrade", "head"]),
            "api: only the migrate service may run migrations",
        ),
        (
            lambda c: c["services"]["worker"].update(stop_grace_period="10s"),
            "worker stop grace period must be 60 s",
        ),
        (
            lambda c: c["services"]["worker"].update(restart="unless-stopped"),
            "worker: must have no restart policy",
        ),
        (
            lambda c: c["services"]["api"]["depends_on"].pop("migrate"),
            "api must wait for a successful migration",
        ),
        (
            lambda c: c["services"]["postgres"].update(image="pgvector/pgvector:pg17"),
            "postgres must use the approved digest-pinned image",
        ),
        (
            lambda c: c["services"]["worker"].update(
                ports=[{"host_ip": "127.0.0.1", "published": "9"}]
            ),
            "worker must not publish ports",
        ),
        (
            lambda c: c["services"]["api"].update(read_only=False),
            "api: root filesystem must be read-only",
        ),
    ],
)
def test_configuration_problems_are_detected(mutate: Callable[[Any], Any], problem: str) -> None:
    config = good_config()
    mutate(config)
    assert problem in ci.validate_config(config, IMAGE)


def test_durations_parse_like_compose_renders_them() -> None:
    assert ci._duration_seconds("1m0s") == 60.0
    assert ci._duration_seconds("60s") == 60.0
    assert ci._duration_seconds("1m30s") == 90.0
    assert ci._duration_seconds(None) is None


# --- build context and cleanup --------------------------------------------------------------------


def test_expected_context_and_comparison() -> None:
    tree = {
        "pyproject.toml",
        "uv.lock",
        "README.md",
        "alembic.ini",
        "apps/a.py",
        "packages/b.py",
        "tests/t.py",
        "docs/d.md",
        "prompts.md",
        ".dockerignore",
    }
    expected = ci.expected_context(tree)
    assert expected == {
        "pyproject.toml",
        "uv.lock",
        "README.md",
        "alembic.ini",
        "apps/a.py",
        "packages/b.py",
    }
    planted = {"apps/.env"}
    report = ci.compare_context(
        expected, (expected - {"apps/a.py"}) | {"apps/.env", "docs/d.md"}, planted
    )
    assert (report.missing, report.leaked_fixtures, report.unexpected) == (
        {"apps/a.py"},
        {"apps/.env"},
        {"docs/d.md"},
    )
    assert not report.ok
    assert ci.compare_context(expected, set(expected), planted).ok


def test_planted_fixtures_are_inside_the_allowlisted_directories() -> None:
    for name in ci.PLANTED_FIXTURES:
        assert name.split("/", 1)[0] in ci.CONTEXT_DIRECTORIES
    assert len(set(ci.PLANTED_FIXTURES)) == len(ci.PLANTED_FIXTURES)


@pytest.mark.parametrize(
    ("project", "image"),
    [("evidenceguard", IMAGE), (PROJECT, "evidenceguard:dev"), ("eg-ci-1", IMAGE), ("", "")],
)
def test_cleanup_refuses_unowned_selections(project: str, image: str) -> None:
    calls: list[list[str]] = []

    def runner(args: Sequence[str], timeout: float) -> Any:
        calls.append(list(args))
        return ci.Result(0, "", "")

    assert ci.cleanup(runner, project, image, out=lambda text: None) == 2
    assert calls == []


def test_cleanup_is_scoped_and_continues_after_errors() -> None:
    calls: list[tuple[list[str], float]] = []
    output: list[str] = []

    def runner(args: Sequence[str], timeout: float) -> Any:
        command = list(args)
        calls.append((command, timeout))
        if "down" in command:
            raise ci.CheckFailed("timed out after 120 s")
        if command[:3] == ["docker", "image", "ls"]:
            return ci.Result(0, "sha256:abc\n", "")
        return ci.Result(0, "", "")

    assert ci.cleanup(runner, PROJECT, IMAGE, out=output.append) == 1
    label = f"label=com.docker.compose.project={PROJECT}"
    listings = [command for command, _ in calls if label in command]
    assert len(listings) == 6  # containers, volumes and networks, before and after
    down = next(command for command, _ in calls if "down" in command)
    assert down == [
        "docker",
        "compose",
        "-f",
        "docker-compose.yml",
        "-p",
        PROJECT,
        "down",
        "-v",
        "--remove-orphans",
    ]
    assert ["docker", "image", "rm", IMAGE] in [command for command, _ in calls]
    assert all(timeout > 0 for _, timeout in calls)
    assert "cleanup: compose down: timed out after 120 s" in output


# --- Prompt 99 regressions: fail-closed service logs ---------------------------------------------


def _logs_failing_with(kind: str) -> Callable[[list[str]], Any]:
    def handler(command: list[str]) -> Any:
        if kind == "nonzero":
            return ci.Result(1, "", "error from the docker daemon\n")
        if kind == "timeout":
            raise ci.CheckFailed("timed out after 60 s")
        raise RuntimeError("retrieval broke")

    return handler


@pytest.mark.parametrize(
    ("kind", "reason"),
    [
        ("nonzero", "exit status 1"),
        ("timeout", "timed out after 60 s"),
        ("exception", "unexpected error (RuntimeError)"),
    ],
)
def test_unavailable_service_logs_fail_an_otherwise_successful_smoke(
    kind: str, reason: str
) -> None:
    docker, api = FakeDocker(), FakeApi()
    docker.overrides[" logs "] = _logs_failing_with(kind)
    instance, output = smoke(docker, api)

    assert instance.run() == 1
    assert output[-1] == f"smoke: FAILED: service logs unavailable (logs postgres: {reason})"
    assert "smoke: ok" not in output
    unchecked = "key-in-service-logs check not performed for: postgres, migrate, api, worker"
    assert f"smoke: secondary: {unchecked}" in output


@pytest.mark.parametrize("kind", ["nonzero", "timeout", "exception"])
def test_unavailable_logs_after_an_earlier_failure_are_secondary(kind: str) -> None:
    docker, api = FakeDocker(), FakeApi()
    api.overrides["/chunks"] = ci.Response(500, None)
    docker.overrides[" logs "] = _logs_failing_with(kind)
    instance, output = smoke(docker, api)

    assert instance.run() == 1
    assert output[-1] == "smoke: FAILED: chunks: HTTP 500, expected 200"
    assert sum("smoke: secondary: service logs unavailable" in line for line in output) == 4
    assert any("key-in-service-logs check not performed" in line for line in output)


def test_one_unavailable_service_log_is_enough_to_fail() -> None:
    docker, api = FakeDocker(), FakeApi()
    plain = FakeDocker()

    def handler(command: list[str]) -> Any:
        if command[-1] == "worker":
            return ci.Result(125, "", "")
        return plain(command, 1)

    docker.overrides[" logs "] = handler
    instance, output = smoke(docker, api)
    assert instance.run() == 1
    assert output[-1] == "smoke: FAILED: service logs unavailable (logs worker: exit status 125)"
    assert "smoke: secondary: key-in-service-logs check not performed for: worker" in output


def test_an_empty_log_from_a_successful_command_is_accepted() -> None:
    docker, api = FakeDocker(), FakeApi()
    docker.logs = {service: "" for service in ci.ALL_SERVICES}
    instance, output = smoke(docker, api)
    assert instance.run() == 0
    assert output[-1] == "smoke: ok"


# --- Prompt 99 regressions: credentials protected before validation ------------------------------

OTHER_KEY = "egk_OtherPrefix0002_another-synthetic-secret"


def _assert_no_plaintext_keys(output: list[str], *keys: str) -> None:
    for line in output:
        for key in keys:
            if key in line:
                assert line == f"::add-mask::{key}"  # the masking command only


def test_a_failed_create_key_never_publishes_its_output() -> None:
    docker, api = FakeDocker(), FakeApi()
    docker.overrides["create-key"] = lambda command: ci.Result(
        1, KEY + "\n", f"warning: created {KEY} but could not commit\n"
    )
    docker.logs["api"] = f"api echoed {KEY}\n"
    instance, output = smoke(docker, api)

    assert instance.run() == 1
    assert output[-1] == "smoke: FAILED: create-key: exit status 1"
    _assert_no_plaintext_keys(output, KEY)
    assert "could not commit" not in "\n".join(output)
    assert "(output withheld: it may contain a credential)" in "\n".join(output)
    # The key the command produced is still checked for in the service logs.
    assert any(
        "generated key found in captured service logs (service=api" in line for line in output
    )


def test_malformed_create_key_output_with_a_key_is_protected() -> None:
    docker, api = FakeDocker(), FakeApi()
    docker.overrides["create-key"] = lambda command: ci.Result(0, f"unexpected banner\n{KEY}\n", "")
    instance, output = smoke(docker, api)

    assert instance.run() == 1
    assert output[-1] == "smoke: FAILED: create-key: output did not have the expected key format"
    _assert_no_plaintext_keys(output, KEY)
    assert f"::add-mask::{KEY}" in output
    assert "unexpected banner" not in "\n".join(output)


def test_a_create_key_failure_before_any_key_is_recoverable() -> None:
    docker, api = FakeDocker(), FakeApi()

    def times_out(command: list[str]) -> Any:
        raise ci.CheckFailed("timed out after 60 s")

    docker.overrides["create-key"] = times_out
    instance, output = smoke(docker, api)
    assert instance.run() == 1
    assert output[-1] == "smoke: FAILED: create-key: timed out after 60 s"
    assert not any(line.startswith("::add-mask::") for line in output)


def test_key_shaped_text_is_redacted_even_if_never_registered() -> None:
    docker, api = FakeDocker(), FakeApi()
    api.overrides["/chunks"] = ci.Response(500, None)
    docker.logs["worker"] = f"stray credential {OTHER_KEY}\n"
    instance, output = smoke(docker, api)
    assert instance.run() == 1
    assert all(OTHER_KEY not in line for line in output)
    assert any(f"stray credential {ci.Redactor.MARK}" in line for line in output)


def test_successful_key_creation_still_masks_once() -> None:
    docker, api = FakeDocker(), FakeApi()
    instance, output = smoke(docker, api)
    assert instance.run() == 0
    assert [line for line in output if line.startswith("::add-mask::")] == [f"::add-mask::{KEY}"]


# --- Prompt 99 regressions: cleanup ownership ----------------------------------------------------


def _cleanup_runner(
    failing_listing: str | None = None, *, stage: str = "both", raise_error: bool = False
) -> tuple[Callable[[Sequence[str], float], Any], list[list[str]]]:
    calls: list[list[str]] = []
    seen: dict[str, int] = {}

    def runner(args: Sequence[str], timeout: float) -> Any:
        command = list(args)
        calls.append(command)
        if "--filter" in command:
            kind = command[1]
            seen[kind] = seen.get(kind, 0) + 1
            phase = "ownership" if seen[kind] == 1 else "post"
            if failing_listing in (kind, "all") and stage in (phase, "both"):
                if raise_error:
                    raise ci.CheckFailed("timed out after 60 s")
                return ci.Result(1, "", "Cannot connect to the Docker daemon")
            return ci.Result(0, "", "")
        if command[:3] == ["docker", "image", "ls"]:
            return ci.Result(0, "sha256:abc\n", "")
        return ci.Result(0, "", "")

    return runner, calls


@pytest.mark.parametrize("raise_error", [False, True])
@pytest.mark.parametrize("failing", ["all", "ps", "volume", "network"])
def test_failed_ownership_checks_prevent_compose_down(failing: str, raise_error: bool) -> None:
    runner, calls = _cleanup_runner(failing, stage="ownership", raise_error=raise_error)
    output: list[str] = []

    assert ci.cleanup(runner, PROJECT, IMAGE, out=output.append) == 1
    assert not any("down" in command for command in calls)
    assert "cleanup: ownership verification failed; refusing compose down" in output
    assert "cleanup: ok" not in output


def test_failed_post_cleanup_verification_is_not_ok() -> None:
    runner, calls = _cleanup_runner("volume", stage="post")
    output: list[str] = []

    assert ci.cleanup(runner, PROJECT, IMAGE, out=output.append) == 1
    assert any("down" in command for command in calls)
    assert "cleanup: post-cleanup verification failed" in output
    assert "cleanup: ok" not in output


def test_successful_empty_inventories_allow_cleanup() -> None:
    runner, calls = _cleanup_runner()
    output: list[str] = []
    assert ci.cleanup(runner, PROJECT, IMAGE, out=output.append) == 0
    assert output[-1] == "cleanup: ok"
    assert ["docker", "image", "rm", IMAGE] in calls


def test_an_unavailable_image_inventory_is_a_failure() -> None:
    def runner(args: Sequence[str], timeout: float) -> Any:
        if list(args)[:3] == ["docker", "image", "ls"]:
            return ci.Result(1, "", "")
        return ci.Result(0, "", "")

    output: list[str] = []
    assert ci.cleanup(runner, PROJECT, IMAGE, out=output.append) == 1
    assert "cleanup: ok" not in output


@pytest.mark.parametrize(
    ("project", "image"),
    [("eg-ci-123-1", "evidenceguard:ci-123-2"), ("eg-ci-123-1", "evidenceguard:ci-124-1")],
)
def test_project_and_image_must_name_the_same_run_and_attempt(project: str, image: str) -> None:
    runner, calls = _cleanup_runner()
    assert ci.cleanup(runner, project, image, out=lambda text: None) == 2
    assert calls == []
