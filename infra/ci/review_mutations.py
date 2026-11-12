"""Bounded, sequential PostgreSQL test-sensitivity probes (Prompt 238).

Run only after the complete integration suite, with its disposable service and locked Python.
No installation, network client, application correction or checked-out test edit is performed.
Offline tests of this harness are not executed database mutation evidence.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

HANDLER = "tests/test_review_handler_postgres.py"
CANARY = "tests/test_review_canary_postgres.py"
G2 = "test_a_returned_response_interrupted_before_stage_commit_repeats_once_on_reclaim"
G3 = "test_acceptance_the_canary_reaches_the_request_and_no_output_surface"
OVERALL_SECONDS = 240.0
PROCESS_SECONDS = 75.0
REQUIRED_IMPORTS = (
    "evidenceguard_worker.review",
    "evidenceguard_observability.provider_spans",
    "evidenceguard_observability.jsonlog",
    "evidenceguard_persistence.safety",
    "tests.conftest",
    "tests.review_postgres_world",
)


class Rejected(Exception):
    """A fixed, privacy-safe failure reason; never include environment/exception text."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise Rejected(code)


@dataclass(frozen=True)
class Mutation:
    key: str
    path: str
    name: str
    edits: tuple[tuple[str, str], ...]
    description: str

    @property
    def node(self) -> str:
        return self.path + "::" + self.name

    @property
    def marker(self) -> str:
        return "p238_detector_" + self.key


MUTATIONS = (
    Mutation(
        "A",
        HANDLER,
        G2,
        (
            (
                "        result = real(*args, **kwargs)\n",
                "        raise interrupt  # P238: before dispatch/return\n"
                "        result = real(*args, **kwargs)\n",
            ),
            ("        assert len(requests) == len(inner.history) == 1\n", ""),
            (
                "    assert caught.value is interrupt\n",
                "    assert caught.value is interrupt\n"
                '    assert len(requests) == len(inner.history) == 1, "p238_detector_A"\n',
            ),
        ),
        "Move the test-owned interruption before real validation; relocate the unchanged "
        "first-call cardinality oracle after the sentinel catch so it executes.",
    ),
    Mutation(
        "B",
        HANDLER,
        G2,
        (
            (
                "    with world.engine.connect() as connection:\n"
                "        first_call = connection.execute(target(ReviewStageCall)).one()\n",
                "    with world.engine.begin() as connection:\n"
                "        changed = connection.execute(\n"
                "            update(ReviewStageCall).where(\n"
                "                ReviewStageCall.tenant_id == world.actor.tenant_id,\n"
                "                ReviewStageCall.review_id == world.review_id,\n"
                "                ReviewStageCall.job_id == world.job_id,\n"
                "                ReviewStageCall.question_id == question,\n"
                '                ReviewStageCall.stage == "verification",\n'
                "                ReviewStageCall.sequence == 1,\n"
                '                ReviewStageCall.state == "started",\n'
                "            ).values(\n"
                '                state="completed", completed_at=func.clock_timestamp(),\n'
                '                outcome="completed", dispatched=True,\n'
                "                model_used=ReviewStageCall.model_requested,\n"
                "                input_tokens=0, output_tokens=0, latency_ms=0,\n"
                "            )\n"
                "        )\n"
                '        assert changed.rowcount == 1, "p238_setup_B"\n'
                "    with world.engine.connect() as connection:\n"
                "        first_call = connection.execute(target(ReviewStageCall)).one()\n",
            ),
            (
                ') == (1, "started", 1, "initial", "original")\n',
                ') == (1, "started", 1, "initial", "original"), "p238_detector_B"\n',
            ),
        ),
        "Commit a test-owned, full-key sequence-1 completion with valid completion/outcome/"
        "usage shape; require the independent first-call state oracle, not SQL/setup failure.",
    ),
    Mutation(
        "C",
        CANARY,
        G3,
        (
            (
                'ASSEMBLED_BODY = "Customer data is encrypted at rest with AES-256. "'
                ' + INSTRUCTION + "\\n"',
                'ASSEMBLED_BODY = "Customer data is encrypted at rest with AES-256. "'
                ' + INSTRUCTION + CANARY + "\\n"',
            ),
            (
                "    assert CANARY.lower() not in ASSEMBLED_BODY.lower()\n",
                '    assert CANARY.lower() not in ASSEMBLED_BODY.lower(), "p238_detector_C"\n',
            ),
        ),
        "Put the literal token into the acceptance-only document; "
        "preserve the literal quotation fixture.",
    ),
    Mutation(
        "D",
        CANARY,
        G3,
        (
            (
                "    assert CANARY.lower() not in "
                "(request.user_text + request.system_text).lower()\n",
                "    import copy\n"
                "    captured_index = model.requests.index(request)\n"
                "    request = copy.copy(request)\n"
                "    payload = json.loads(request.user_text)\n"
                '    payload["evidence"] = [e for e in payload["evidence"]\n'
                '                           if e["chunk_id"] != str(world.chunk_id)]\n'
                '    payload["mutation_instruction"] = INSTRUCTION\n'
                '    object.__setattr__(request, "user_text", json.dumps(payload))\n'
                "    model.requests[captured_index] = request\n"
                '    assert json.loads(request.user_text)["mutation_instruction"] == INSTRUCTION\n'
                "    assert CANARY.lower() not in "
                "(request.user_text + request.system_text).lower()\n",
            ),
            (
                "    (entry,) = [\n"
                '        e for e in json.loads(request.user_text)["evidence"] '
                'if e["chunk_id"] == str(world.chunk_id)\n'
                "    ]\n",
                "    entries = [\n"
                '        e for e in json.loads(request.user_text)["evidence"] '
                'if e["chunk_id"] == str(world.chunk_id)\n'
                "    ]\n"
                '    assert len(entries) == 1, "p238_detector_D"\n'
                "    (entry,) = entries\n",
            ),
        ),
        "Remove the exact injected chunk from a copied captured request after execution, "
        "retain instruction text elsewhere, and make the existing singleton-entry oracle explicit.",
    ),
)


def transform(data: bytes, mutation: Mutation) -> tuple[bytes, int]:
    text = data.decode("utf-8")
    for old, new in mutation.edits:
        require(text.count(old) == 1, "mutation_fragment_missing_or_ambiguous")
        text = text.replace(old, new, 1)
    assertions = [
        n
        for n in ast.walk(ast.parse(text))
        if isinstance(n, ast.Assert)
        and isinstance(n.msg, ast.Constant)
        and n.msg.value == mutation.marker
    ]
    require(len(assertions) == 1, "detector_missing_or_ambiguous")
    return text.encode("utf-8"), assertions[0].lineno


def hashes(sources: Mapping[str, bytes]) -> dict[str, str]:
    return {p: hashlib.sha256(data).hexdigest() for p, data in sorted(sources.items())}


def read_sources(root: Path, names: Sequence[str]) -> dict[str, bytes]:
    result = {}
    for name in names:
        require(
            not Path(name).is_absolute() and ".." not in Path(name).parts, "source_path_mismatch"
        )
        path = root / name
        require(
            path.is_file()
            and not path.is_symlink()
            and path.resolve().is_relative_to(root.resolve()),
            "source_path_mismatch",
        )
        result[name] = path.read_bytes()
    return result


def candidate(root: Path) -> dict[str, bytes]:
    result = subprocess.run(
        [
            "git",
            "ls-files",
            "--stage",
            "-z",
            "--",
            "apps",
            "packages",
            "tests",
            "pyproject.toml",
            "alembic.ini",
        ],
        cwd=root,
        capture_output=True,
        check=True,
        timeout=10,
    )
    entries = [x.split(b"\t", 1) for x in result.stdout.split(b"\0") if x]
    names = [p.decode("utf-8") for _, p in entries]
    forbidden = {".git", ".local", ".venv", "__pycache__", "build", "dist", "node_modules"}
    require(
        all(
            not forbidden.intersection(Path(p).parts)
            and not Path(p).name.startswith(".env")
            and Path(p).suffix not in {".pem", ".p12", ".pfx", ".pyc"}
            for p in names
        ),
        "copy_manifest_forbidden_path",
    )
    sources = read_sources(root, names)
    for meta, raw_name in entries:
        mode, blob, stage = meta.decode().split()
        data = sources[raw_name.decode()]
        identity = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        require(mode == "100644" and stage == "0" and identity == blob, "candidate_index_mismatch")
    return sources


def control_ids(sources: Mapping[str, bytes]) -> tuple[str, ...]:
    ids: list[str] = []
    for path in (HANDLER, CANARY):
        for node in ast.parse(sources[path]).body:
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                suffixes = (
                    ("[False]", "[True]")
                    if node.name
                    == "test_negative_control_the_same_checker_fails_when_the_canary_is_emitted"
                    else ("",)
                )
                ids.extend(path + "::" + node.name + s for s in suffixes)
    require(len(ids) == 12 and len(set(ids)) == 12, "control_inventory_mismatch")
    return tuple(ids)


# This bootstrap is tool-owned, not an accepted test edit. -I ignores PYTHONPATH/current
# directory; explicit copy paths precede editable finders, and every loaded project module
# is checked before test calls and again at session finish. Nothing imports from checkout.
BOOTSTRAP = r"""
import hashlib, importlib, json, sys
from pathlib import Path
sys.dont_write_bytecode = True
root = Path(__file__).resolve().parent
out = Path(sys.argv[1])
manifest = json.loads((root / "_p238_manifest.json").read_text())
sys.path[:0] = [str(root)] + [str(p) for base in ("apps", "packages")
                            for p in sorted((root / base).iterdir()) if p.is_dir()]
import pytest
state = {"imports": {}, "reports": [], "import_error": False}
def inspect():
    imports = {}
    for name, module in tuple(sys.modules.items()):
        if not (name.startswith("evidenceguard_") or name == "tests" or name.startswith("tests.")):
            continue
        for package_path in getattr(module, "__path__", ()):
            if not Path(package_path).resolve().is_relative_to(root):
                raise ValueError("import_path_mismatch")
        filename = getattr(module, "__file__", None)
        if filename is None:
            continue
        path = Path(filename).resolve()
        relative = path.relative_to(root).as_posix()
        suffix = name.replace(".", "/")
        if not any(relative == end or relative.endswith("/" + end)
                   for end in (suffix + ".py", suffix + "/__init__.py")):
            raise ValueError("import_module_mismatch")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if manifest.get(relative) != digest:
            raise ValueError("import_source_mismatch")
        imports[name] = {"path": str(path), "relative": relative, "sha256": digest}
    state["imports"] = imports
def check():
    try:
        inspect()
    except Exception:
        state["import_error"] = True
        raise pytest.UsageError("p238_import_mismatch") from None
class Probe:
    def pytest_collection_finish(self, session):
        check()
    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item, call):
        report = (yield).get_result()
        entry = {"node": report.nodeid, "when": report.when, "outcome": report.outcome}
        if call.excinfo is not None:
            last = call.excinfo.traceback[-1]
            entry.update(type=call.excinfo.type.__name__, path=str(last.path), line=last.lineno + 1)
        state["reports"].append(entry)
    def pytest_sessionfinish(self, session, exitstatus):
        try:
            check()
        finally:
            out.write_text(json.dumps(state), encoding="utf-8")
try:
    for name in ("evidenceguard_worker.review", "evidenceguard_observability.provider_spans",
                 "evidenceguard_observability.jsonlog", "evidenceguard_persistence.safety"):
        importlib.import_module(name)
    check()
    code = pytest.main(sys.argv[2:], plugins=[Probe()])
finally:
    out.write_text(json.dumps(state), encoding="utf-8")
sys.exit(code)
"""


def validate_imports(
    probe: Mapping[str, Any], copy: Path, expected: Mapping[str, str], nodes: Sequence[str]
) -> None:
    require(probe.get("import_error") is False, "import_mismatch")
    imports = probe.get("imports", {})
    required = set(REQUIRED_IMPORTS) | {n.split("::")[0][:-3].replace("/", ".") for n in nodes}
    require(required <= set(imports), "required_import_missing")
    for name, value in imports.items():
        path = Path(value["path"]).resolve()
        require(path.is_relative_to(copy.resolve()), "import_mismatch")
        relative = path.relative_to(copy.resolve()).as_posix()
        suffix = name.replace(".", "/")
        require(
            any(
                relative == end or relative.endswith("/" + end)
                for end in (suffix + ".py", suffix + "/__init__.py")
            ),
            "import_module_mismatch",
        )
        require(
            relative == value["relative"]
            and expected.get(relative) == value["sha256"]
            and path.is_file()
            and hashlib.sha256(path.read_bytes()).hexdigest() == value["sha256"],
            "import_source_mismatch",
        )


def judge(
    xml: str,
    probe: Mapping[str, Any],
    exit_code: int,
    nodes: Sequence[str],
    mutation: Mutation | None = None,
    line: int | None = None,
) -> None:
    document = ET.fromstring(xml)
    require(
        not document.findall(".//error") and not document.findall(".//skipped"),
        "pytest_error_or_skip",
    )
    cases = document.findall(".//testcase")
    actual = [
        c.attrib.get("classname", "").replace(".", "/") + ".py::" + c.attrib.get("name", "")
        for c in cases
    ]
    require(
        len(actual) == len(nodes) and set(actual) == set(nodes), "pytest_case_inventory_mismatch"
    )
    failures = document.findall(".//failure")
    require(
        exit_code == (1 if mutation else 0) and len(failures) == (1 if mutation else 0),
        "surviving_mutant_or_failed_controls",
    )
    reports = probe.get("reports", [])
    require(len(reports) == 3 * len(nodes), "pytest_phase_inventory_mismatch")
    for node in nodes:
        phases = [r for r in reports if r.get("node") == node]
        require(
            [r.get("when") for r in phases] == ["setup", "call", "teardown"],
            "pytest_phase_mismatch",
        )
        for report in phases:
            failed = mutation is not None and report["when"] == "call"
            require(
                report.get("outcome") == ("failed" if failed else "passed"), "wrong_pytest_phase"
            )
            if failed:
                assert mutation is not None
                module = mutation.path[:-3].replace("/", ".")
                imported_path = probe.get("imports", {}).get(module, {}).get("path", "")
                require(
                    report.get("type") == "AssertionError"
                    and report.get("line") == line
                    and bool(imported_path)
                    and Path(report.get("path", "")).resolve() == Path(imported_path).resolve(),
                    "wrong_detector",
                )
    if mutation is not None:
        require(nodes == (mutation.node,), "mutation_target_mismatch")
        require(
            failures[0].get("type") in (None, "AssertionError")
            and failures[0].get("message", "").startswith("AssertionError: " + mutation.marker),
            "wrong_detector",
        )


def child_env(env: Mapping[str, str]) -> dict[str, str]:
    require(
        env.get("EG_REQUIRE_INTEGRATION") == "1" and bool(env.get("EG_TEST_DATABASE_URL")),
        "required_disposable_database_not_configured",
    )
    allow = {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "LANG", "LC_ALL"}
    result = {k: v for k, v in env.items() if k.upper() in allow}
    for key in ("EG_REQUIRE_INTEGRATION", "EG_TEST_DATABASE_URL", "EG_DATABASE_URL"):
        if key in env:
            result[key] = env[key]
    result["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    return result


def redact(text: str, env: Mapping[str, str]) -> str:
    for key in ("EG_TEST_DATABASE_URL", "EG_DATABASE_URL"):
        raw = env.get(key, "")
        if raw:
            for token in {raw, escape(raw), escape(raw, quote=False)}:
                text = text.replace(token, "[database URL redacted]")
            try:
                password = urlsplit(raw).password
            except ValueError:
                password = None
            if password:
                for token in {
                    password,
                    unquote(password),
                    escape(password),
                    escape(unquote(password)),
                }:
                    text = text.replace(token, "[redacted]")
    return text


def execute(
    command: list[str], copy: Path, env: Mapping[str, str], timeout: float
) -> subprocess.CompletedProcess[str]:
    with subprocess.Popen(
        command,
        cwd=copy,
        env=dict(env),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        start_new_session=os.name == "posix",
    ) as process:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            if sys.platform != "win32":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            stdout, stderr = process.communicate()
            raise subprocess.TimeoutExpired(
                command, timeout, output=stdout, stderr=stderr
            ) from None
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


Executor = Callable[[list[str], Path, Mapping[str, str], float], subprocess.CompletedProcess[str]]


def restore(copy: Path, sources: Mapping[str, bytes]) -> dict[str, str]:
    for name, data in sources.items():
        (copy / name).write_bytes(data)
    restored = hashes(read_sources(copy, list(sources)))
    require(restored == hashes(sources), "restoration_mismatch")
    return restored


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def run_plan(
    root: Path,
    sources: Mapping[str, bytes],
    output: Path,
    env: Mapping[str, str],
    executor: Executor = execute,
    clock: Callable[[], float] = time.monotonic,
    deadline: float | None = None,
) -> None:
    child = child_env(env)
    if deadline is None:
        deadline = clock() + OVERALL_SECONDS
    baseline = hashes(sources)
    require(hashes(read_sources(root, list(sources))) == baseline, "checkout_source_mismatch")
    controls = control_ids(sources)
    for label, mutation in [
        ("baseline", None),
        *((m.key, m) for m in MUTATIONS),
        ("restored", None),
    ]:
        record: dict[str, Any] = {
            "case": label,
            "status": "incomplete",
            "baseline_hashes": baseline,
        }
        folder = output / label
        folder.mkdir()
        try:
            with tempfile.TemporaryDirectory(prefix="copy-", dir=output) as temporary:
                copy = Path(temporary).resolve()
                for name, data in sources.items():
                    path = copy / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
                require(
                    hashes(read_sources(copy, list(sources))) == baseline, "copy_source_mismatch"
                )
                try:
                    line = None
                    if mutation:
                        changed, line = transform(sources[mutation.path], mutation)
                        (copy / mutation.path).write_bytes(changed)
                        record.update(
                            edit=mutation.description,
                            edits=mutation.edits,
                            intended_detector=mutation.marker,
                            detector_line=line,
                        )
                    expected = hashes(read_sources(copy, list(sources)))
                    record["mutant_hashes"] = expected
                    nodes = (mutation.node,) if mutation else controls
                    write_json(copy / "_p238_manifest.json", expected)
                    (copy / "_p238_bootstrap.py").write_text(BOOTSTRAP, encoding="utf-8")
                    command = [
                        sys.executable,
                        "-I",
                        str(copy / "_p238_bootstrap.py"),
                        str(folder / "imports.json"),
                        "-c",
                        str(copy / "pyproject.toml"),
                        "-m",
                        "integration",
                        "--tb=short",
                        "-q",
                        "-o",
                        "addopts=",
                        "--import-mode=importlib",
                        "--strict-markers",
                        "--strict-config",
                        "-p",
                        "no:cacheprovider",
                        "--junitxml=" + str(folder / "junit.xml"),
                        *nodes,
                    ]
                    remaining = deadline - clock()
                    require(remaining > 0, "overall_timeout")
                    record.update(command=command, timeout_seconds=min(PROCESS_SECONDS, remaining))
                    try:
                        result = executor(command, copy, child, min(PROCESS_SECONDS, remaining))
                    except subprocess.TimeoutExpired as exc:
                        record.update(timed_out=True, exit_code=None)
                        (folder / "stdout.txt").write_text(
                            redact(str(exc.output or ""), child), encoding="utf-8"
                        )
                        (folder / "stderr.txt").write_text(
                            redact(str(exc.stderr or ""), child), encoding="utf-8"
                        )
                        raise Rejected("subprocess_timeout") from None
                    record["exit_code"] = result.returncode
                    for filename, text in (
                        ("stdout.txt", result.stdout),
                        ("stderr.txt", result.stderr),
                    ):
                        (folder / filename).write_text(redact(text, child), encoding="utf-8")
                    for filename in ("junit.xml", "imports.json"):
                        path = folder / filename
                        require(path.is_file(), "missing_structured_results")
                        path.write_text(
                            redact(path.read_text(encoding="utf-8"), child), encoding="utf-8"
                        )
                    require(clock() <= deadline, "overall_timeout")
                    require(
                        hashes(read_sources(copy, list(sources))) == expected,
                        "executed_source_mismatch",
                    )
                    probe = json.loads((folder / "imports.json").read_text(encoding="utf-8"))
                    validate_imports(probe, copy, expected, nodes)
                    record["imported_modules"] = probe["imports"]
                    judge(
                        (folder / "junit.xml").read_text(encoding="utf-8"),
                        probe,
                        result.returncode,
                        nodes,
                        mutation,
                        line,
                    )
                    failure = ET.fromstring(
                        (folder / "junit.xml").read_text(encoding="utf-8")
                    ).find(".//failure")
                    record["failure_details"] = (
                        failure.get("message") if failure is not None else None
                    )
                    record["detector_or_control_matched"] = True
                finally:
                    record["restored_hashes"] = restore(copy, sources)
                    require(record["restored_hashes"] == baseline, "restoration_mismatch")
            require(clock() <= deadline, "overall_timeout")
            record["status"] = "caught" if mutation else "passed"
        finally:
            for filename in ("junit.xml", "imports.json"):
                path = folder / filename
                if path.is_file():
                    path.write_text(
                        redact(path.read_text(encoding="utf-8"), child), encoding="utf-8"
                    )
            record["checkout_unchanged"] = hashes(read_sources(root, list(sources))) == baseline
            if not record["checkout_unchanged"]:
                record["status"] = "incomplete"
            write_json(folder / "record.json", record)
            require(record["checkout_unchanged"], "checkout_source_mismatch")
        print(f"review mutations: {label}: {record['status']}", flush=True)
        # Preserve the decisive evidence in downloadable job logs as well as local records;
        # the full copied-source manifests, exact edits and outputs remain in folder/.
        proof = {
            key: record.get(key)
            for key in (
                "case",
                "status",
                "exit_code",
                "intended_detector",
                "detector_line",
                "failure_details",
                "checkout_unchanged",
            )
        }
        proof["source_hashes"] = {
            phase: {p: record[phase][p] for p in (HANDLER, CANARY)}
            for phase in ("baseline_hashes", "mutant_hashes", "restored_hashes")
        }
        proof["imports"] = {
            name: value
            for name, value in record["imported_modules"].items()
            if name in REQUIRED_IMPORTS or name.startswith("tests.test_review_")
        }
        print("review mutations: proof: " + json.dumps(proof, sort_keys=True), flush=True)


def main() -> int:
    deadline = time.monotonic() + OVERALL_SECONDS
    root = Path(__file__).resolve().parents[2]
    output = root / ".local" / "review-mutations" / ("p238-" + uuid.uuid4().hex)
    output.mkdir(parents=True)
    summary: dict[str, Any] = {
        "status": "failed",
        "overall_seconds": OVERALL_SECONDS,
        "subprocess_seconds": PROCESS_SECONDS,
    }
    try:
        child_env(os.environ)  # refuse before source copies or imports without the test target
        sources = candidate(root)
        unchanged = subprocess.run(
            [
                "git",
                "diff",
                "--quiet",
                "HEAD",
                "--",
                "apps",
                "packages",
                "tests",
                "pyproject.toml",
                "alembic.ini",
                "uv.lock",
                ".github/workflows/ci.yml",
                "infra/ci/review_mutations.py",
            ],
            cwd=root,
            capture_output=True,
            timeout=10,
        )
        require(unchanged.returncode == 0, "candidate_HEAD_mismatch")
        committed_runner = subprocess.run(
            ["git", "show", "HEAD:infra/ci/review_mutations.py"],
            cwd=root,
            capture_output=True,
            check=True,
            timeout=10,
        ).stdout
        require(committed_runner == Path(__file__).read_bytes(), "runner_HEAD_mismatch")
        summary["candidate_hashes"] = hashes(sources)
        summary["runner_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        summary["lockfile_sha256"] = hashlib.sha256((root / "uv.lock").read_bytes()).hexdigest()
        summary["workflow_sha256"] = hashlib.sha256(
            (root / ".github/workflows/ci.yml").read_bytes()
        ).hexdigest()
        summary["python_executable"] = sys.executable
        summary["python_version"] = sys.version
        summary["candidate_commit"] = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout.strip()
        summary["candidate_manifest_sha256"] = hashlib.sha256(
            json.dumps(summary["candidate_hashes"], sort_keys=True).encode()
        ).hexdigest()
        print(
            "review mutations: candidate: "
            + json.dumps(
                {
                    key: summary[key]
                    for key in (
                        "candidate_commit",
                        "candidate_manifest_sha256",
                        "runner_sha256",
                        "lockfile_sha256",
                        "workflow_sha256",
                        "python_executable",
                        "python_version",
                    )
                },
                sort_keys=True,
            ),
            flush=True,
        )
        run_plan(root, sources, output, os.environ, deadline=deadline)
        summary["status"] = "passed"
        return 0
    except Exception as exc:
        summary["reason"] = str(exc) if isinstance(exc, Rejected) else "runner_internal_error"
        print("review mutations: failed: " + summary["reason"], flush=True)
        return 1
    finally:
        summary["temporary_resources_removed"] = not any(output.glob("copy-*"))
        write_json(output / "summary.json", summary)
        print("review mutations: records: " + str(output.relative_to(root)), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
