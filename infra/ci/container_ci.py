"""CI checks for the M3f container stack (ADR-0012). Standard library only.

Run by the CI runner's ``python3`` from the repository root; it is not part of the distribution.

Subcommands (each exits 0 on success, 1 on a failed check, 2 on a usage or safety refusal):

- ``config``: validate the rendered Compose configuration (``docker compose config``).
- ``context``: verify the effective Docker build context. The committed tree is exported with
  ``git archive`` into a temporary directory, synthetic placeholder files are planted at nested
  paths that ``.dockerignore`` must exclude, and the context Docker actually sends is exported by
  a throwaway ``FROM scratch`` build and compared exactly with the expected file set.
- ``image``: check the CI-built image (user, entry points, offline migration SQL, contents).
- ``smoke``: the Compose smoke test (startup, image identity, synthetic account and key, upload,
  production-worker ingestion, verified views, duplicate upload, M4c offline indexing through the
  production ``eg-admin backfill-indexes`` and the registered worker, idle-worker stop).
  Indexing is verified with read-only ``psql`` queries: the index belongs to the same tenant
  and ingested revision with the offline profile fingerprint, it is ``ready``, its canonical
  ``index_revision`` job ``succeeded``, and its embedding count equals ``chunk_count``.
- ``cleanup``: remove only this run's Compose project and image tag.

Selection comes from the environment, set once by the workflow job: ``EG_COMPOSE_PROJECT``
(``eg-ci-<run id>-<attempt>``), ``EG_IMAGE`` (``evidenceguard:ci-<run id>-<attempt>``) and, for
``image`` and ``smoke``, ``EG_IMAGE_ID`` (the built image ID).

Privacy: the generated API key is held only in memory. The ``create-key`` stdout is captured
privately and never printed, stored or uploaded; every key-shaped string in either of its
streams is protected before its status or format is checked. Every other captured output
(commands, service logs) is redacted before it is displayed, including anything shaped like a
key; GitHub masking is only an extra layer. Retrieving every service's logs is part of the
smoke's acceptance, and cleanup refuses destructive steps when ownership cannot be verified.
HTTP bodies and exception representations are never printed: only status codes, fixed fields
and exception class names. Any occurrence of the key in captured service logs fails the smoke and
is reported as a service name and a count.

Every subprocess call and HTTP request has its own timeout, in addition to the polling deadline.
The first failure decides the exit status. Unavailable service logs fail an otherwise successful
smoke; after an earlier failure, they and other diagnostic errors are reported as secondary.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

COMPOSE_FILE = "docker-compose.yml"
PG_IMAGE = (
    "pgvector/pgvector:0.8.7-pg17@sha256:"
    "ac08538c6f8b9904c33c8224c5e5706dbe760aca29db1d096972b4052c22a75d"
)
APP_SERVICES = ("migrate", "api", "worker")
ALL_SERVICES = ("postgres", *APP_SERVICES)
APP_UID = "10001"
PROJECT_PATTERN = re.compile(r"eg-ci-([0-9]+)-([0-9]+)")
IMAGE_PATTERN = re.compile(r"evidenceguard:ci-([0-9]+)-([0-9]+)")
API_URL = "http://127.0.0.1:8000"

# Timeouts in seconds. Each bounds one call; the polling deadline bounds the ingestion loop.
PULL_TIMEOUT = 300
UP_WAIT = 180
UP_TIMEOUT = 240
COMMAND_TIMEOUT = 60
STOP_GRACE = 60
STOP_TIMEOUT = 90
DOWN_TIMEOUT = 120
BUILD_TIMEOUT = 300
HTTP_TIMEOUT = 10
INGESTION_DEADLINE = 90
INDEXING_DEADLINE = 90
POLL_INTERVAL = 2
LOG_TAIL = 200

# M4c indexing smoke (ADR-0015). The fingerprint is the offline HASH_IDENTITY's, pinned as a
# literal so the check does not depend on the code under test.
OFFLINE_FINGERPRINT = "ad53bb3be5d8c50909b9f984294703d572e8f1844a43c5223ef86cd4a1162376"
DB_USER = "evidenceguard"
DB_NAME = "evidenceguard_dev"
BACKFILL_LINE = re.compile(
    r"pending=(?P<pending>\d+) ready=(?P<ready>\d+) stalled=(?P<stalled>\d+) "
    r"ineligible=(?P<ineligible>\d+) conflict=(?P<conflict>\d+)"
)
INDEX_QUERY = (
    "SELECT ei.tenant_id, ei.revision_id, ep.fingerprint, ei.status, coalesce(j.status, '-'), "
    "(SELECT count(*) FROM chunk_embeddings ce WHERE ce.tenant_id = ei.tenant_id "
    "AND ce.index_id = ei.id), ei.chunk_count, cs.chunk_count "
    "FROM embedding_indexes ei "
    "JOIN embedding_profiles ep ON ep.tenant_id = ei.tenant_id AND ep.id = ei.profile_id "
    "JOIN chunk_sets cs ON cs.tenant_id = ei.tenant_id AND cs.revision_id = ei.revision_id "
    "LEFT JOIN jobs j ON j.tenant_id = ei.tenant_id AND j.kind = 'index_revision' "
    "AND j.idempotency_key = ei.id::text "
    "WHERE ei.tenant_id = '{tenant}' AND ei.revision_id = '{revision}'"
)

ROOT_FILES = ("pyproject.toml", "uv.lock", "README.md", "alembic.ini")
CONTEXT_DIRECTORIES = ("apps", "packages")
REQUIRED_PACKAGE_DATA = (
    "packages/persistence/evidenceguard_persistence/migrations/script.py.mako",
    "packages/persistence/evidenceguard_persistence/py.typed",
    "apps/api/evidenceguard_api/py.typed",
)
# Synthetic placeholders at nested paths that .dockerignore must exclude. Never real secrets.
PLANTED_FIXTURES = (
    "apps/api/.env",
    "apps/api/evidenceguard_api/.env.local",
    "packages/domain/.env.production",
    "packages/domain/.git/HEAD",
    "apps/worker/.local/notes.txt",
    "packages/persistence/.venv/bin/python",
    "apps/api/venv/lib/site.py",
    "apps/api/evidenceguard_api/__pycache__/app.cpython-312.pyc",
    "packages/retrieval/evidenceguard_retrieval/stray.pyc",
    "packages/retrieval/.mypy_cache/3.12/cache.json",
    "apps/worker/.ruff_cache/content",
    "packages/observability/.pytest_cache/v/cache/nodeids",
    "packages/persistence/dist/evidenceguard-0.0.0-py3-none-any.whl",
    "apps/api/build/lib/module.py",
    "packages/domain/evidenceguard_domain.egg-info/PKG-INFO",
    "apps/api/certs/server.pem",
    "packages/persistence/keys/signing.key",
    "apps/worker/deploy/id_rsa",
    "packages/observability/run.log",
)
FIXTURE_TEXT = "synthetic placeholder for the build-context check; not a secret\n"

MARKDOWN = (
    "# Security policy\n\n"
    "Customer data is encrypted at rest with AES-256.\n\n"
    "## Retention\n\n"
    "Backups are kept for 30 days and then deleted.\n"
)


class CheckFailed(Exception):
    """A failed check. The message is fixed text and never contains submitted or secret data."""


# --- output and redaction -------------------------------------------------------------------------


# Anything shaped like an EvidenceGuard API key (``egk_<prefix>_<secret>``).
KEY_PATTERN = re.compile(r"egk_[A-Za-z0-9_-]{8,256}")


class Redactor:
    """Replaces every registered secret, and anything shaped like an API key, before text is
    displayed. ``count`` reports occurrences of the registered secrets only."""

    MARK = "[REDACTED]"

    def __init__(self) -> None:
        self._secrets: list[str] = []

    def add(self, secret: str) -> None:
        if secret and secret not in self._secrets:
            self._secrets.append(secret)

    def redact(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, self.MARK)
        return KEY_PATTERN.sub(self.MARK, text)

    def count(self, text: str) -> int:
        return sum(text.count(secret) for secret in self._secrets)


Output = Callable[[str], None]


def _print(text: str) -> None:
    print(text, flush=True)


# --- subprocesses and HTTP ------------------------------------------------------------------------


@dataclass(frozen=True)
class Result:
    returncode: int
    stdout: str
    stderr: str


Runner = Callable[[Sequence[str], float], Result]


def run_process(args: Sequence[str], timeout: float) -> Result:
    """Run a command with captured output and a timeout. Errors never echo the arguments."""
    try:
        completed = subprocess.run(
            list(args),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise CheckFailed(f"timed out after {timeout:g} s") from None
    except OSError as error:
        raise CheckFailed(f"could not start ({type(error).__name__})") from None
    return Result(completed.returncode, completed.stdout or "", completed.stderr or "")


@dataclass(frozen=True)
class Response:
    status: int
    body: dict[str, Any] | None


Http = Callable[[str, str, Mapping[str, str], bytes | None, float], Response]
MAX_RESPONSE_BYTES = 1_000_000


def http_request(
    method: str, url: str, headers: Mapping[str, str], body: bytes | None, timeout: float
) -> Response:
    """One HTTP request with a socket timeout. Only the status and a parsed JSON object are
    returned; failures raise ``CheckFailed`` naming the exception class only."""
    request = urllib.request.Request(url, data=body, headers=dict(headers), method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status, raw = response.status, response.read(MAX_RESPONSE_BYTES)
    except urllib.error.HTTPError as error:
        status, raw = error.code, b""
        error.close()
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise CheckFailed(f"request failed ({type(error).__name__})") from None
    try:
        parsed = json.loads(raw) if raw else None
    except ValueError:
        parsed = None
    return Response(status, parsed if isinstance(parsed, dict) else None)


# --- Compose configuration ------------------------------------------------------------------------


def _duration_seconds(value: Any) -> float | None:
    """Parse a Compose duration as rendered (``60s``, ``1m0s``) or as seconds."""
    if isinstance(value, int | float):
        return float(value)
    if not isinstance(value, str):
        return None
    total, matched = 0.0, False
    for amount, unit in re.findall(r"([0-9.]+)(h|ms|m|s)", value):
        total += float(amount) * {"h": 3600.0, "m": 60.0, "s": 1.0, "ms": 0.001}[unit]
        matched = True
    return total if matched else None


def _command(service: Mapping[str, Any]) -> list[str]:
    command = service.get("command") or []
    return [str(part) for part in command] if isinstance(command, list) else [str(command)]


def _depends(service: Mapping[str, Any], name: str) -> str | None:
    depends = service.get("depends_on") or {}
    entry = depends.get(name) if isinstance(depends, dict) else None
    return entry.get("condition") if isinstance(entry, dict) else None


def validate_config(config: Mapping[str, Any], image: str) -> list[str]:
    """Problems with a rendered Compose configuration (``docker compose config --format json``)."""
    problems: list[str] = []
    services = config.get("services") or {}
    if set(services) != set(ALL_SERVICES):
        return [f"services must be exactly {sorted(ALL_SERVICES)}"]
    if services["postgres"].get("image") != PG_IMAGE:
        problems.append("postgres must use the approved digest-pinned image")
    for name in APP_SERVICES:
        service = services[name]
        if service.get("image") != image:
            problems.append(f"{name}: image must be the selected application image")
        if service.get("pull_policy") != "never":
            problems.append(f"{name}: pull_policy must be never")
        if service.get("read_only") is not True:
            problems.append(f"{name}: root filesystem must be read-only")
        if service.get("cap_drop") != ["ALL"]:
            problems.append(f"{name}: must drop all capabilities")
        if "no-new-privileges:true" not in (service.get("security_opt") or []):
            problems.append(f"{name}: must set no-new-privileges")
        if service.get("init") is not True:
            problems.append(f"{name}: must run an init process")
        if service.get("restart", "no") != "no":
            problems.append(f"{name}: must have no restart policy")
        if "/tmp" not in [str(entry).split(":")[0] for entry in service.get("tmpfs") or []]:
            problems.append(f"{name}: must mount a /tmp tmpfs")
        environment = service.get("environment") or {}
        if "@postgres:5432/" not in str(environment.get("EG_DATABASE_URL", "")):
            problems.append(f"{name}: EG_DATABASE_URL must target the postgres service")
        migrates = "alembic" in _command(service)
        if migrates != (name == "migrate"):
            problems.append(f"{name}: only the migrate service may run migrations")
    if _depends(services["migrate"], "postgres") != "service_healthy":
        problems.append("migrate must wait for a healthy database")
    for name in ("api", "worker"):
        if _depends(services[name], "postgres") != "service_healthy":
            problems.append(f"{name} must wait for a healthy database")
        if _depends(services[name], "migrate") != "service_completed_successfully":
            problems.append(f"{name} must wait for a successful migration")
    published: dict[str, list[tuple[str, str]]] = {}
    for name, service in services.items():
        for port in service.get("ports") or []:
            if not isinstance(port, dict):
                problems.append(f"{name}: unrecognised port entry")
                continue
            published.setdefault(name, []).append(
                (str(port.get("host_ip", "")), str(port.get("published", "")))
            )
    for name, entries in published.items():
        for host_ip, _published in entries:
            if host_ip != "127.0.0.1":
                problems.append(f"{name}: host ports must bind 127.0.0.1 only")
    if published.get("api") != [("127.0.0.1", "8000")]:
        problems.append("api must publish exactly 127.0.0.1:8000")
    if published.get("postgres") != [("127.0.0.1", "5433")]:
        problems.append("postgres must publish exactly 127.0.0.1:5433")
    for name in ("migrate", "worker"):
        if name in published:
            problems.append(f"{name} must not publish ports")
    worker = services["worker"]
    if worker.get("stop_signal", "SIGTERM") != "SIGTERM":
        problems.append("worker must stop with SIGTERM")
    if _duration_seconds(worker.get("stop_grace_period")) != float(STOP_GRACE):
        problems.append("worker stop grace period must be 60 s")
    test = " ".join(
        str(part) for part in (services["api"].get("healthcheck") or {}).get("test", [])
    )
    if "/readyz" not in test:
        problems.append("api health check must use /readyz")
    return problems


def check_config(runner: Runner, project: str, image: str, out: Output = _print) -> int:
    result = runner(
        ["docker", "compose", "-f", COMPOSE_FILE, "-p", project, "config", "--format", "json"],
        COMMAND_TIMEOUT,
    )
    if result.returncode != 0:
        out("compose config: failed to render the configuration")
        return 1
    problems = validate_config(json.loads(result.stdout), image)
    for problem in problems:
        out(f"compose config: {problem}")
    out("compose config: ok" if not problems else f"compose config: {len(problems)} problem(s)")
    return 1 if problems else 0


# --- effective build context ----------------------------------------------------------------------


def files_under(root: Path) -> set[str]:
    return {
        PurePosixPath(path.relative_to(root)).as_posix()
        for path in root.rglob("*")
        if path.is_file() or path.is_symlink()
    }


def expected_context(archive_files: Iterable[str]) -> set[str]:
    """The files the image build may see: the root allowlist plus everything under the
    allowlisted directories, as committed."""
    return {
        name
        for name in archive_files
        if name in ROOT_FILES or name.split("/", 1)[0] in CONTEXT_DIRECTORIES
    }


@dataclass
class ContextReport:
    missing: set[str] = field(default_factory=set)
    leaked_fixtures: set[str] = field(default_factory=set)
    unexpected: set[str] = field(default_factory=set)

    @property
    def ok(self) -> bool:
        return not (self.missing or self.leaked_fixtures or self.unexpected)


def compare_context(expected: set[str], actual: set[str], planted: set[str]) -> ContextReport:
    return ContextReport(
        missing=expected - actual,
        leaked_fixtures=actual & planted,
        unexpected=actual - expected - planted,
    )


def check_context(runner: Runner, repo: Path, out: Output = _print) -> int:
    with tempfile.TemporaryDirectory(prefix="eg-context-") as temporary:
        workdir = Path(temporary)
        context, exported, listing = workdir / "context", workdir / "exported", workdir / "listing"
        for directory in (context, exported, listing):
            directory.mkdir()
        archive = workdir / "tree.tar"
        result = runner(
            ["git", "-C", str(repo), "archive", "--format=tar", "-o", str(archive), "HEAD"],
            COMMAND_TIMEOUT,
        )
        if result.returncode != 0:
            out("context: git archive failed")
            return 1
        with tarfile.open(archive) as tar:
            tar.extractall(context, filter="data")
        expected = expected_context(files_under(context))
        absent = [name for name in REQUIRED_PACKAGE_DATA if name not in expected]
        if absent:
            out(f"context: committed tree lacks required package data: {absent}")
            return 1
        for name in PLANTED_FIXTURES:
            path = context / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(FIXTURE_TEXT, encoding="utf-8")
        # The listing Dockerfile lives outside the context with no Dockerfile-specific ignore
        # file, so the context root .dockerignore is the one Docker applies.
        dockerfile = listing / "Listing.Dockerfile"
        dockerfile.write_text("FROM scratch\nCOPY . /\n", encoding="utf-8")
        result = runner(
            [
                "docker",
                "build",
                "--file",
                str(dockerfile),
                "--output",
                f"type=local,dest={exported}",
                str(context),
            ],
            BUILD_TIMEOUT,
        )
        if result.returncode != 0:
            out("context: listing build failed")
            return 1
        report = compare_context(expected, files_under(exported), set(PLANTED_FIXTURES))
    for label, names in (
        ("missing (expected but excluded)", report.missing),
        ("planted fixtures that leaked into the context", report.leaked_fixtures),
        ("unexpected files in the context", report.unexpected),
    ):
        for name in sorted(names):
            out(f"context: {label}: {name}")
    if report.ok:
        planted = len(PLANTED_FIXTURES)
        out(f"context: ok ({len(expected)} files; {planted} planted fixtures excluded)")
        return 0
    return 1


# --- image checks ---------------------------------------------------------------------------------

CONTENT_CHECK = """
import os, shutil, sys
problems = []
if sorted(os.listdir("/app")) != ["alembic.ini"]:
    problems.append("/app must contain only alembic.ini")
if shutil.which("uv") is not None:
    problems.append("uv must not be on PATH")
for root, dirs, files in os.walk("/opt/venv"):
    for name in dirs + files:
        path = os.path.join(root, name)
        info = os.lstat(path)
        if info.st_uid != 0:
            problems.append("runtime files must be owned by root")
            break
        if not os.path.islink(path) and os.access(path, os.W_OK):
            problems.append("runtime files must not be writable by the runtime user")
            break
    if problems:
        break
print("\\n".join(problems) if problems else "content ok")
sys.exit(1 if problems else 0)
"""

IMPORT_CHECK = (
    "import evidenceguard_api, evidenceguard_domain;"
    " from evidenceguard_api.app import create_app; create_app();"
    " from evidenceguard_worker.handlers import production_registry;"
    " assert production_registry().kinds == frozenset({'ingest_revision', 'index_revision'});"
    " assert 'site-packages' in evidenceguard_api.__file__; print('imports ok')"
)


def image_checks(image: str) -> list[tuple[str, list[str], Callable[[Result], bool]]]:
    def docker_run(*command: str) -> list[str]:
        return [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            image,
            *command,
        ]

    def succeeded(result: Result) -> bool:
        return result.returncode == 0

    return [
        ("uid is 10001", docker_run("id", "-u"), lambda r: r.stdout.strip() == APP_UID),
        ("gid is 10001", docker_run("id", "-g"), lambda r: r.stdout.strip() == APP_UID),
        ("eg-api --help", docker_run("eg-api", "--help"), succeeded),
        ("eg-worker --help", docker_run("eg-worker", "--help"), succeeded),
        ("eg-admin --help", docker_run("eg-admin", "--help"), succeeded),
        ("installed imports", docker_run("python", "-I", "-c", IMPORT_CHECK), succeeded),
        (
            "offline migration SQL",
            docker_run("alembic", "-c", "/app/alembic.ini", "upgrade", "head", "--sql"),
            lambda r: r.returncode == 0 and "CREATE TABLE api_keys" in r.stdout,
        ),
        ("runtime contents", docker_run("python", "-I", "-c", CONTENT_CHECK), succeeded),
    ]


def check_image(runner: Runner, image: str, image_id: str, out: Output = _print) -> int:
    failures = 0
    inspected = runner(
        ["docker", "image", "inspect", "--format", "{{.Id}}", image], COMMAND_TIMEOUT
    )
    if inspected.returncode != 0 or inspected.stdout.strip() != image_id:
        out("image: the selected tag does not resolve to the recorded image ID")
        return 1
    for label, command, passed in image_checks(image):
        try:
            result = runner(command, COMMAND_TIMEOUT)
            ok = passed(result)
        except CheckFailed as error:
            ok = False
            out(f"image: {label}: {error}")
        out(f"image: {label}: {'ok' if ok else 'FAILED'}")
        failures += 0 if ok else 1
    return 1 if failures else 0


# --- Compose smoke --------------------------------------------------------------------------------

SEED_LINE = re.compile(
    r"tenant=(?P<slug>\S+) tenant_id=(?P<tenant>[0-9a-f-]{36}) role=(?P<role>\w+) "
    r"user_id=(?P<user>[0-9a-f-]{36}) (?:created|existing)"
)


def multipart(fields: Mapping[str, str], content: bytes) -> tuple[bytes, str]:
    boundary = f"eg-smoke-{uuid.uuid4().hex}"
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        for name, value in fields.items()
    ]
    parts.append(
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="policy.md"\r\n'
            "Content-Type: text/markdown\r\n\r\n"
        ).encode()
        + content
        + b"\r\n"
    )
    return b"".join(parts) + f"--{boundary}--\r\n".encode(), boundary


class Smoke:
    """The Compose smoke test. ``run`` returns the exit status (0 or 1)."""

    def __init__(
        self,
        *,
        project: str,
        image_id: str,
        runner: Runner = run_process,
        http: Http = http_request,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        out: Output = _print,
        base_url: str = API_URL,
    ) -> None:
        self.project = project
        self.image_id = image_id
        self._runner = runner
        self._http = http
        self._clock = clock
        self._sleep = sleep
        self._out = out
        self.base_url = base_url
        self.redactor = Redactor()
        self.captured: dict[str, str] = {}
        self.containers: dict[str, str] = {}
        self._key: str | None = None

    # Plumbing ----------------------------------------------------------------------------------

    def emit(self, text: str) -> None:
        self._out(self.redactor.redact(text))

    def compose(self, *args: str) -> list[str]:
        return ["docker", "compose", "-f", COMPOSE_FILE, "-p", self.project, *args]

    def command(self, label: str, args: Sequence[str], timeout: float) -> Result:
        try:
            result = self._runner(args, timeout)
        except CheckFailed as error:
            raise CheckFailed(f"{label}: {error}") from None
        self.captured[label] = result.stdout + result.stderr
        if result.returncode != 0:
            raise CheckFailed(f"{label}: exit status {result.returncode}")
        return result

    def request(
        self,
        label: str,
        method: str,
        path: str,
        body: bytes | None = None,
        content_type: str | None = None,
    ) -> Response:
        headers = {"Accept": "application/json"}
        if self._key is not None:
            headers["Authorization"] = f"Bearer {self._key}"
        if content_type is not None:
            headers["Content-Type"] = content_type
        try:
            return self._http(method, self.base_url + path, headers, body, HTTP_TIMEOUT)
        except CheckFailed as error:
            raise CheckFailed(f"{label}: {error}") from None

    def expect(self, label: str, response: Response, status: int) -> dict[str, Any]:
        if response.status != status:
            raise CheckFailed(f"{label}: HTTP {response.status}, expected {status}")
        if response.body is None:
            raise CheckFailed(f"{label}: response was not a JSON object")
        return response.body

    # Steps -------------------------------------------------------------------------------------

    def steps(self) -> None:
        self.command("pull database image", ["docker", "pull", PG_IMAGE], PULL_TIMEOUT)
        self.command(
            "compose up",
            self.compose(
                "up",
                "-d",
                "--no-build",
                "--pull",
                "never",
                "--wait",
                "--wait-timeout",
                str(UP_WAIT),
            ),
            UP_TIMEOUT,
        )
        self.emit("smoke: stack started (database healthy, migrate done, api healthy)")
        self.check_image_identity()
        tenant, user = self.seed()
        self.create_key(tenant, user)
        vendor = self.expect(
            "create vendor",
            self.request(
                "create vendor",
                "POST",
                "/v1/vendors",
                json.dumps({"slug": "smoke-vendor", "name": "Smoke Vendor"}).encode(),
                "application/json",
            ),
            201,
        )
        upload = self.expect("upload", self.upload(str(vendor.get("id"))), 202)
        document_id, revision_id = str(upload.get("document_id")), str(upload.get("revision_id"))
        job = upload.get("job") or {}
        self.emit("smoke: upload accepted (202)")
        self.wait_for_ingestion(str(job.get("id")))
        chunk_count = self.check_views(document_id, revision_id)
        duplicate = self.expect("duplicate upload", self.upload(str(vendor.get("id"))), 200)
        if duplicate.get("created") is not False or duplicate.get("revision_id") != revision_id:
            raise CheckFailed("duplicate upload: did not return the existing revision")
        self.emit("smoke: duplicate upload returned the existing revision (200)")
        self.backfill_indexes(tenant)
        self.wait_for_indexing(tenant, revision_id, chunk_count)
        self.stop_worker()

    def check_image_identity(self) -> None:
        for service in APP_SERVICES:
            result = self.command(
                f"find {service}", self.compose("ps", "-a", "-q", service), COMMAND_TIMEOUT
            )
            ids = result.stdout.split()
            if len(ids) != 1:
                raise CheckFailed(f"find {service}: expected one container, found {len(ids)}")
            self.containers[service] = ids[0]
            inspected = self.command(
                f"inspect {service}",
                ["docker", "inspect", "--format", "{{.Image}}", ids[0]],
                COMMAND_TIMEOUT,
            )
            if inspected.stdout.strip() != self.image_id:
                raise CheckFailed(f"{service}: container does not run the CI-built image")
        self.emit("smoke: migrate, api and worker run the CI-built image")

    def seed(self) -> tuple[str, str]:
        result = self.command(
            "seed-demo",
            self.compose("exec", "-T", "api", "eg-admin", "seed-demo"),
            COMMAND_TIMEOUT,
        )
        for line in result.stdout.splitlines():
            match = SEED_LINE.fullmatch(line.strip())
            if match and match["role"] == "reviewer":
                return match["tenant"], match["user"]
        raise CheckFailed("seed-demo: no reviewer in the demo fixture output")

    def create_key(self, tenant: str, user: str) -> None:
        args = self.compose(
            "exec", "-T", "api", "eg-admin", "create-key", "--tenant-id", tenant, "--user-id", user
        )
        try:
            result = self._runner(args, COMMAND_TIMEOUT)
        except CheckFailed as error:
            raise CheckFailed(f"create-key: {error}") from None
        except Exception as error:
            raise CheckFailed(f"create-key: unexpected error ({type(error).__name__})") from None
        # Both streams are private. Every recognisable key in either is protected before any
        # status or format check can fail, so failure diagnostics and service-log checks cover
        # it. The raw output is never kept for display, on success or failure.
        self.captured["create-key"] = "(output withheld: it may contain a credential)"
        for stream in (result.stdout, result.stderr):
            for match in KEY_PATTERN.finditer(stream):
                self.protect(match.group())
        if result.returncode != 0:
            raise CheckFailed(f"create-key: exit status {result.returncode}")
        key = result.stdout.strip()
        if KEY_PATTERN.fullmatch(key) is None:
            raise CheckFailed("create-key: output did not have the expected key format")
        self._key = key
        self.emit("smoke: API key created (held in memory only)")

    def protect(self, secret: str) -> None:
        """Register a secret for redaction and service-log checks, then ask GitHub to mask it.
        Masking is an additional layer only; redaction is the control."""
        if secret in self.redactor._secrets:
            return
        self.redactor.add(secret)
        self._out(f"::add-mask::{secret}")

    def upload(self, vendor_id: str) -> Response:
        body, boundary = multipart(
            {
                "document_key": "smoke-security-policy",
                "title": "Smoke security policy",
                "source_type": "vendor_statement",
            },
            MARKDOWN.encode(),
        )
        return self.request(
            "upload",
            "POST",
            f"/v1/vendors/{vendor_id}/documents",
            body,
            f"multipart/form-data; boundary={boundary}",
        )

    def wait_for_ingestion(self, job_id: str) -> None:
        deadline = self._clock() + INGESTION_DEADLINE
        while True:
            job = self.expect("job", self.request("job", "GET", f"/v1/jobs/{job_id}"), 200)
            status = job.get("status")
            if status == "succeeded":
                self.emit("smoke: ingestion job succeeded")
                return
            if status in ("failed", "dead"):
                raise CheckFailed(f"ingestion: job ended as {status}")
            if self._clock() >= deadline:
                raise CheckFailed(f"ingestion: not succeeded within {INGESTION_DEADLINE} s")
            self._sleep(POLL_INTERVAL)

    def check_views(self, document_id: str, revision_id: str) -> int:
        document = self.expect(
            "document", self.request("document", "GET", f"/v1/documents/{document_id}"), 200
        )
        active = document.get("active_revision") or {}
        if (
            document.get("active_revision_id") != revision_id
            or active.get("ingestion_state") != "active"
        ):
            raise CheckFailed("document: the uploaded revision is not active")
        chunks = self.expect(
            "chunks",
            self.request("chunks", "GET", f"/v1/documents/{document_id}/revisions/1/chunks"),
            200,
        )
        chunk_set = chunks.get("chunk_set") or {}
        count = chunk_set.get("chunk_count")
        if (
            chunk_set.get("verified_complete") is not True
            or not isinstance(count, int)
            or count < 1
            or chunk_set.get("stored_count") != count
        ):
            raise CheckFailed("chunks: the chunk set is not verified complete")
        self.emit(f"smoke: revision active; {count} verified chunk(s)")
        return count

    def backfill_indexes(self, tenant: str) -> None:
        """Run the production backfill CLI once; one new pending index is expected."""
        result = self.command(
            "backfill-indexes",
            self.compose(
                "exec", "-T", "api", "eg-admin", "backfill-indexes", "--tenant-id", tenant
            ),
            COMMAND_TIMEOUT,
        )
        lines = result.stdout.splitlines()
        match = BACKFILL_LINE.fullmatch(lines[0].strip()) if lines else None
        if match is None:
            raise CheckFailed("backfill-indexes: output did not have the expected format")
        counts = {name: int(value) for name, value in match.groupdict().items()}
        if counts != {"pending": 1, "ready": 0, "stalled": 0, "ineligible": 0, "conflict": 0}:
            raise CheckFailed("backfill-indexes: expected exactly one pending index")
        self.emit("smoke: backfill-indexes enqueued one offline indexing job")

    def index_state(self, tenant: str, revision: str) -> list[str]:
        """The index's verification row, read in a read-only session (one row expected)."""
        query = INDEX_QUERY.format(tenant=str(uuid.UUID(tenant)), revision=str(uuid.UUID(revision)))
        result = self.command(
            "index state",
            self.compose(
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                DB_USER,
                "-d",
                DB_NAME,
                "-v",
                "ON_ERROR_STOP=1",
                "-qAt",
                "-F",
                "|",
                "-c",
                "SET default_transaction_read_only = on",
                "-c",
                query,
            ),
            COMMAND_TIMEOUT,
        )
        rows = [line for line in result.stdout.splitlines() if line.strip()]
        if len(rows) != 1:
            raise CheckFailed(f"index state: expected one index row, found {len(rows)}")
        return rows[0].split("|")

    def wait_for_indexing(self, tenant: str, revision: str, chunk_count: int) -> None:
        try:
            uuid.UUID(tenant), uuid.UUID(revision)
        except ValueError:
            raise CheckFailed("indexing: tenant or revision is not a UUID") from None
        deadline = self._clock() + INDEXING_DEADLINE
        while True:
            fields = self.index_state(tenant, revision)
            if len(fields) != 8:
                raise CheckFailed("index state: unexpected row format")
            row_tenant, row_revision, fingerprint, status, job_status = fields[:5]
            if (row_tenant, row_revision) != (tenant, revision):
                raise CheckFailed("indexing: the index is not the ingested revision's")
            if fingerprint != OFFLINE_FINGERPRINT:
                raise CheckFailed("indexing: the index does not use the offline profile")
            if job_status in ("failed", "dead"):
                raise CheckFailed(f"indexing: job ended as {job_status}")
            if status == "ready" and job_status == "succeeded":
                stored, bound, chunk_set = (int(value) for value in fields[5:8])
                if not stored == bound == chunk_set == chunk_count:
                    raise CheckFailed("indexing: embedding count does not equal chunk_count")
                self.emit(
                    f"smoke: index ready for the ingested revision; {stored} embedding(s), "
                    "indexing job succeeded"
                )
                return
            if self._clock() >= deadline:
                raise CheckFailed(f"indexing: not ready within {INDEXING_DEADLINE} s")
            self._sleep(POLL_INTERVAL)

    def stop_worker(self) -> None:
        # This stops an idle worker after ingestion succeeded. It does not test draining an
        # in-flight handler. A successful stop command alone is not proof of a graceful exit.
        self.command(
            "stop worker", self.compose("stop", "-t", str(STOP_GRACE), "worker"), STOP_TIMEOUT
        )
        state = self.command(
            "worker state",
            [
                "docker",
                "inspect",
                "--format",
                "{{.State.Status}} {{.State.ExitCode}} {{.State.OOMKilled}}",
                self.containers["worker"],
            ],
            COMMAND_TIMEOUT,
        ).stdout.split()
        if state != ["exited", "0", "false"]:
            raise CheckFailed(
                "worker stop: expected status exited, exit code 0 and no OOM kill; got "
                + " ".join(state[:3])
            )
        self.emit("smoke: idle worker exited with code 0 (no OOM kill)")

    # Diagnostics -------------------------------------------------------------------------------

    def diagnostics(self, *, show: bool) -> tuple[list[str], list[str]]:
        """Retrieve every service's logs, check them for the key and (if ``show``) display them
        redacted. Returns (acceptance failures, secondary errors).

        Retrieving each service's logs is part of acceptance: a nonzero status, a timeout or any
        retrieval error is a failure, and the key check is never reported as passed for logs
        that were unavailable. An empty log from a successful command is accepted."""
        findings: list[str] = []
        errors: list[str] = []
        logs: dict[str, str] = {}
        for service in ALL_SERVICES:
            try:
                result = self._runner(
                    self.compose("logs", "--no-color", "--tail", str(LOG_TAIL), service),
                    COMMAND_TIMEOUT,
                )
            except CheckFailed as error:
                findings.append(f"service logs unavailable (logs {service}: {error})")
                continue
            except Exception as error:
                findings.append(
                    f"service logs unavailable (logs {service}: "
                    f"unexpected error ({type(error).__name__}))"
                )
                continue
            if result.returncode != 0:
                findings.append(
                    f"service logs unavailable (logs {service}: exit status {result.returncode})"
                )
                continue
            logs[service] = result.stdout + result.stderr
        unchecked = [service for service in ALL_SERVICES if service not in logs]
        if unchecked:
            findings.append("key-in-service-logs check not performed for: " + ", ".join(unchecked))
        for service, text in logs.items():
            occurrences = self.redactor.count(text)
            if occurrences:
                findings.append(
                    f"generated key found in captured service logs "
                    f"(service={service}, occurrences={occurrences})"
                )
        if show:
            try:
                status = self._runner(self.compose("ps", "-a"), COMMAND_TIMEOUT)
                self.emit("--- docker compose ps -a")
                self.emit(status.stdout + status.stderr)
                if status.returncode != 0:
                    errors.append(f"ps: exit status {status.returncode}")
            except CheckFailed as error:
                errors.append(f"ps: {error}")
            except Exception as error:
                errors.append(f"ps: unexpected error ({type(error).__name__})")
            for label, text in self.captured.items():
                self.emit(f"--- command output: {label}")
                self.emit(text)
            for service, text in logs.items():
                self.emit(f"--- logs: {service} (last {LOG_TAIL} lines)")
                self.emit(text)
        return findings, errors

    def run(self) -> int:
        failure: str | None = None
        try:
            self.steps()
        except CheckFailed as error:
            failure = str(error)
        except Exception as error:  # never print the representation; it could carry data
            failure = f"unexpected error ({type(error).__name__})"
        try:
            findings, errors = self.diagnostics(show=failure is not None)
        except Exception as error:
            findings = [f"diagnostics: unexpected error ({type(error).__name__})"]
            errors = []
        # Acceptance failures from diagnostics become the primary failure only if no step had
        # already failed; otherwise they are reported as secondary.
        for finding in findings:
            if failure is None:
                failure = finding
            else:
                errors.append(finding)
        for secondary in errors:
            self.emit(f"smoke: secondary: {secondary}")
        if failure is not None:
            self.emit(f"smoke: FAILED: {failure}")
            return 1
        self.emit("smoke: ok")
        return 0


# --- cleanup --------------------------------------------------------------------------------------


def check_selection(project: str, image: str) -> str | None:
    project_match = PROJECT_PATTERN.fullmatch(project)
    image_match = IMAGE_PATTERN.fullmatch(image)
    if project_match is None:
        return "refusing: EG_COMPOSE_PROJECT is not an eg-ci-<run>-<attempt> name"
    if image_match is None:
        return "refusing: EG_IMAGE is not an evidenceguard:ci-<run>-<attempt> tag"
    if project_match.groups() != image_match.groups():
        return "refusing: EG_COMPOSE_PROJECT and EG_IMAGE name different runs or attempts"
    return None


def cleanup(runner: Runner, project: str, image: str, out: Output = _print) -> int:
    """Remove only this run's Compose project and image tag.

    Ownership is verified first, from the Compose project label. If any inventory command fails,
    the inventory is unavailable (not empty), so the destructive ``down`` is refused and cleanup
    fails. Afterwards the inventory is checked again; cleanup reports ``ok`` only when that
    verification succeeds and shows nothing left."""
    refusal = check_selection(project, image)
    if refusal is not None:
        out(f"cleanup: {refusal}")
        return 2
    label = f"label=com.docker.compose.project={project}"
    problems = 0
    listings = {
        "containers": ["docker", "ps", "-a", "-q"],
        "volumes": ["docker", "volume", "ls", "-q"],
        "networks": ["docker", "network", "ls", "-q"],
    }

    def inventory(stage: str) -> dict[str, list[str]] | None:
        found: dict[str, list[str]] = {}
        for kind, command in listings.items():
            try:
                result = runner([*command, "--filter", label], COMMAND_TIMEOUT)
            except CheckFailed as error:
                out(f"cleanup: {stage} inventory of {kind} unavailable: {error}")
                return None
            except Exception as error:
                out(
                    f"cleanup: {stage} inventory of {kind} unavailable "
                    f"(unexpected error ({type(error).__name__}))"
                )
                return None
            if result.returncode != 0:
                out(
                    f"cleanup: {stage} inventory of {kind} unavailable "
                    f"(exit status {result.returncode})"
                )
                return None
            found[kind] = result.stdout.split()
        return found

    def summary(found: dict[str, list[str]]) -> str:
        return ", ".join(f"{len(ids)} {kind}" for kind, ids in found.items())

    before = inventory("ownership")
    if before is None:
        out("cleanup: ownership verification failed; refusing compose down")
        problems += 1
    else:
        out(f"cleanup: owned by {project}: {summary(before)}")
        try:
            down = runner(
                [
                    "docker",
                    "compose",
                    "-f",
                    COMPOSE_FILE,
                    "-p",
                    project,
                    "down",
                    "-v",
                    "--remove-orphans",
                ],
                DOWN_TIMEOUT,
            )
            if down.returncode != 0:
                out(f"cleanup: compose down exit status {down.returncode}")
                problems += 1
        except CheckFailed as error:
            out(f"cleanup: compose down: {error}")
            problems += 1
        after = inventory("post-cleanup")
        if after is None:
            out("cleanup: post-cleanup verification failed")
            problems += 1
        elif any(after.values()):
            out(f"cleanup: resources remain: {summary(after)}")
            problems += 1
    # The image tag is unique to this run and attempt; it is removed only when listed.
    try:
        listed = runner(["docker", "image", "ls", "-q", image], COMMAND_TIMEOUT)
        if listed.returncode != 0:
            out(f"cleanup: image inventory unavailable (exit status {listed.returncode})")
            problems += 1
        elif listed.stdout.strip():
            removed = runner(["docker", "image", "rm", image], COMMAND_TIMEOUT)
            if removed.returncode != 0:
                out(
                    f"cleanup: could not remove the CI image tag (exit status {removed.returncode})"
                )
                problems += 1
    except CheckFailed as error:
        out(f"cleanup: image removal: {error}")
        problems += 1
    out("cleanup: ok" if not problems else f"cleanup: FAILED ({problems} problem(s))")
    return 1 if problems else 0


# --- entry point ----------------------------------------------------------------------------------


def _require(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise SystemExit(f"{name} is not set")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="M3f container CI checks (ADR-0012).")
    parser.add_argument("command", choices=["config", "context", "image", "smoke", "cleanup"])
    args = parser.parse_args(argv)
    project, image = _require("EG_COMPOSE_PROJECT"), _require("EG_IMAGE")
    refusal = check_selection(project, image)
    if refusal is not None:
        _print(refusal)
        return 2
    if args.command == "config":
        return check_config(run_process, project, image)
    if args.command == "context":
        return check_context(run_process, Path.cwd())
    if args.command == "image":
        return check_image(run_process, image, _require("EG_IMAGE_ID"))
    if args.command == "smoke":
        return Smoke(project=project, image_id=_require("EG_IMAGE_ID")).run()
    return cleanup(run_process, project, image)


if __name__ == "__main__":
    sys.exit(main())
