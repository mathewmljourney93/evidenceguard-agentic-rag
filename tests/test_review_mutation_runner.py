"""Offline harness tests only: no PostgreSQL mutation, Docker, provider or network execution."""

import importlib.util
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "review_mutations", ROOT / "infra/ci/review_mutations.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


runner = load()
IMPORT_PATHS = {
    "evidenceguard_worker.review": "apps/worker/evidenceguard_worker/review.py",
    "evidenceguard_observability.provider_spans": (
        "packages/observability/evidenceguard_observability/provider_spans.py"
    ),
    "evidenceguard_observability.jsonlog": (
        "packages/observability/evidenceguard_observability/jsonlog.py"
    ),
    "evidenceguard_persistence.safety": "packages/persistence/evidenceguard_persistence/safety.py",
    "tests.conftest": "tests/conftest.py",
    "tests.review_postgres_world": "tests/review_postgres_world.py",
    "tests.test_review_handler_postgres": runner.HANDLER,
    "tests.test_review_canary_postgres": runner.CANARY,
}
ENV = {"EG_REQUIRE_INTEGRATION": "1", "EG_TEST_DATABASE_URL": "synthetic-not-connected"}


@pytest.fixture
def checkout(tmp_path: Path) -> tuple[Path, dict[str, bytes], Path]:
    sources = {p: (ROOT / p).read_bytes() for p in {*IMPORT_PATHS.values(), "pyproject.toml"}}
    root = tmp_path / "checkout"
    for name, data in sources.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    output = tmp_path / "records"
    output.mkdir()
    return root, sources, output


class FakeExecutor:
    """Fabricates process/XML/phase records, never executes application or database code."""

    def __init__(self, bad_case: str = "", mode: str = "") -> None:
        self.bad_case = bad_case
        self.mode = mode
        self.calls: list[str] = []

    def __call__(
        self, command: list[str], copy: Path, env: dict[str, str], timeout: float
    ) -> subprocess.CompletedProcess[str]:
        folder = Path(command[3]).parent
        label = folder.name
        self.calls.append(label)
        assert 0 < timeout <= runner.PROCESS_SECONDS
        assert env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
        nodes = [a for a in command if ".py::" in a]
        mutation = next((m for m in runner.MUTATIONS if m.key == label), None)
        marker = mutation.marker if mutation else "unrelated"
        line = runner.transform((ROOT / mutation.path).read_bytes(), mutation)[1] if mutation else 1
        mode = self.mode if label == self.bad_case else ""
        if mode == "timeout":
            raise subprocess.TimeoutExpired(command, timeout, output="synthetic-not-connected")
        testsuite = ET.Element("testsuite")
        reports: list[dict[str, Any]] = []
        failed = mutation is not None or mode == "controls_fail"
        if mode == "survive":
            failed = False
        for node in nodes:
            path, name = node.split("::")
            case = ET.SubElement(
                testsuite, "testcase", classname=path[:-3].replace("/", "."), name=name
            )
            if failed:
                message = (
                    "unrelated assertion" if mode == "unrelated" else "AssertionError: " + marker
                )
                ET.SubElement(
                    case, "failure", type="AssertionError", message=message
                ).text = message
            for when in ("setup", "call", "teardown"):
                record: dict[str, Any] = dict(
                    node=node,
                    when=when,
                    outcome="failed" if when == "call" and failed else "passed",
                )
                if when == "call" and failed:
                    record.update(type="AssertionError", path=str(copy / path), line=line)
                reports.append(record)
        if mode == "wrong_line":
            reports[1]["line"] += 1
        if mode == "wrong_type":
            reports[1]["type"] = "ValueError"
        if mode == "collection":
            ET.SubElement(testsuite, "error", message="collection failed")
        if mode == "setup":
            ET.SubElement(testsuite[0], "error", message="fixture constraint failed")
            reports[0]["outcome"] = "failed"
        if mode == "skip":
            ET.SubElement(testsuite[0], "skipped")
        if mode == "missing":
            testsuite.remove(testsuite[0])
        if mode == "missing_phase":
            reports.pop()
        imports = {}
        for name, relative in IMPORT_PATHS.items():
            path = copy / relative
            imports[name] = dict(
                path=str(path),
                relative=relative,
                sha256=runner.hashes({relative: path.read_bytes()})[relative],
            )
        if mode == "import_path":
            imports["evidenceguard_worker.review"]["path"] = str(
                ROOT / IMPORT_PATHS["evidenceguard_worker.review"]
            )
        if mode == "import_hash":
            imports["evidenceguard_worker.review"]["sha256"] = "0" * 64
        if mode == "import_alias":
            imports["evidenceguard_worker.review"] = dict(
                imports["evidenceguard_observability.jsonlog"]
            )
        if mode == "missing_import":
            del imports["evidenceguard_worker.review"]
        if mode == "source":
            (copy / runner.HANDLER).write_bytes(b"# unexpected drift\n")
        probe = dict(import_error=mode == "import_error", imports=imports, reports=reports)
        runner.write_json(folder / "imports.json", probe)
        ET.ElementTree(testsuite).write(folder / "junit.xml", encoding="unicode")
        return subprocess.CompletedProcess(
            command, 1 if failed else 0, "synthetic subprocess output", ""
        )


def run(checkout: tuple[Path, dict[str, bytes], Path], fake: FakeExecutor, **kwargs: Any) -> None:
    root, sources, output = checkout
    runner.run_plan(root, sources, output, ENV, executor=fake, **kwargs)


def test_all_intended_failures_require_controls_imports_and_restoration(
    checkout: tuple[Path, dict[str, bytes], Path],
) -> None:
    root, sources, output = checkout
    fake = FakeExecutor()
    run(checkout, fake)
    assert fake.calls == ["baseline", "A", "B", "C", "D", "restored"]
    for label in fake.calls:
        record = json.loads((output / label / "record.json").read_text())
        assert record["status"] == ("caught" if label in "ABCD" else "passed")
        assert record["baseline_hashes"] == record["restored_hashes"] == runner.hashes(sources)
        assert record["checkout_unchanged"]
        assert record["imported_modules"]
        assert (output / label / "stdout.txt").is_file()
    assert not list(output.glob("copy-*"))
    assert runner.read_sources(root, list(sources)) == sources


@pytest.mark.parametrize(
    "mode",
    [
        "survive",
        "unrelated",
        "wrong_line",
        "wrong_type",
        "collection",
        "setup",
        "skip",
        "missing",
        "missing_phase",
        "timeout",
        "import_path",
        "import_hash",
        "import_alias",
        "import_error",
        "missing_import",
        "source",
    ],
)
def test_reject_bad_mutation_results_and_cleanup(
    checkout: tuple[Path, dict[str, bytes], Path],
    mode: str,
) -> None:
    root, sources, output = checkout
    fake = FakeExecutor("A", mode)
    with pytest.raises(runner.Rejected):
        run(checkout, fake)
    record = json.loads((output / "A/record.json").read_text())
    assert record["status"] == "incomplete"
    assert record["restored_hashes"] == runner.hashes(sources)
    assert not list(output.glob("copy-*"))
    assert runner.read_sources(root, list(sources)) == sources
    assert fake.calls == ["baseline", "A"]


@pytest.mark.parametrize("label", ["baseline", "restored"])
def test_failing_controls_reject_entire_run(
    checkout: tuple[Path, dict[str, bytes], Path],
    label: str,
) -> None:
    with pytest.raises(runner.Rejected):
        run(checkout, FakeExecutor(label, "controls_fail"))
    assert not list(checkout[2].glob("copy-*"))


def test_restoration_failure_cannot_publish_caught_status(
    checkout: tuple[Path, dict[str, bytes], Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved = runner.restore

    def broken(copy: Path, sources: dict[str, bytes]) -> dict[str, str]:
        value: dict[str, str] = saved(copy, sources)
        value[runner.HANDLER] = "wrong"
        return value

    monkeypatch.setattr(runner, "restore", broken)
    with pytest.raises(runner.Rejected, match="restoration_mismatch"):
        run(checkout, FakeExecutor())
    assert json.loads((checkout[2] / "baseline/record.json").read_text())["status"] == "incomplete"
    assert not list(checkout[2].glob("copy-*"))


def test_overall_timeout(checkout: tuple[Path, dict[str, bytes], Path]) -> None:
    times = iter((0.0, 0.0, 241.0))
    with pytest.raises(runner.Rejected, match="overall_timeout"):
        run(checkout, FakeExecutor(), clock=lambda: next(times))
    assert not list(checkout[2].glob("copy-*"))


@pytest.mark.parametrize("mutation", runner.MUTATIONS, ids=lambda m: m.key)
def test_transform_exact_target_and_detector(mutation: Any) -> None:
    original = (ROOT / mutation.path).read_bytes()
    transformed, line = runner.transform(original, mutation)
    assert transformed != original
    assert transformed.decode().splitlines()[line - 1].strip().startswith("assert ")
    assert transformed.decode().count(mutation.marker) == 1
    assert mutation.node in runner.control_ids(
        {p: (ROOT / p).read_bytes() for p in (runner.HANDLER, runner.CANARY)}
    )
    if mutation.key == "B":
        for required in (
            'state="completed"',
            'outcome="completed"',
            "completed_at=func.clock_timestamp()",
            "model_used=ReviewStageCall.model_requested",
            "input_tokens=0, output_tokens=0",
            "ReviewStageCall.tenant_id",
            "ReviewStageCall.review_id",
            "ReviewStageCall.job_id",
            "ReviewStageCall.question_id",
            "ReviewStageCall.stage",
            "ReviewStageCall.sequence == 1",
        ):
            assert required in transformed.decode()
    if mutation.key == "D":
        assert 'payload["mutation_instruction"] = INSTRUCTION' in transformed.decode()
        assert 'if e["chunk_id"] != str(world.chunk_id)' in transformed.decode()
    if mutation.key == "C":
        literal = original.decode().split("LITERAL_BODY =", 1)[1].split("class _Logs", 1)[0]
        assert literal in transformed.decode()
    assert (ROOT / mutation.path).read_bytes() == original


@pytest.mark.parametrize("mutation", runner.MUTATIONS, ids=lambda m: m.key)
@pytest.mark.parametrize("ambiguous", [False, True])
def test_transform_refuses_every_missing_or_ambiguous_fragment(
    mutation: Any, ambiguous: bool
) -> None:
    original = (ROOT / mutation.path).read_text(encoding="utf-8")
    for old, _ in mutation.edits:
        changed = original.replace(old, old + old if ambiguous else "", 1)
        with pytest.raises((runner.Rejected, SyntaxError)):
            runner.transform(changed.encode(), mutation)


@pytest.mark.parametrize(
    "env", [{}, {"EG_REQUIRE_INTEGRATION": "1"}, {"EG_TEST_DATABASE_URL": "fake"}]
)
def test_missing_database_gate_refuses_before_execution(
    checkout: tuple[Path, dict[str, bytes], Path],
    env: dict[str, str],
) -> None:
    fake = FakeExecutor()
    with pytest.raises(runner.Rejected, match="required_disposable_database_not_configured"):
        runner.run_plan(*checkout[:2], checkout[2], env, executor=fake)
    assert not fake.calls and list(checkout[2].iterdir()) == []


def test_environment_is_not_a_credentials_or_import_channel() -> None:
    env = {
        **ENV,
        "PYTHONPATH": "original-checkout",
        "PYTEST_ADDOPTS": "bad",
        "EG_API_KEY": "synthetic",
        "UNRELATED_SECRET": "synthetic",
        "PATH": "installed-tools",
    }
    child = runner.child_env(env)
    assert set(child) == {*ENV, "PATH", "PYTEST_DISABLE_PLUGIN_AUTOLOAD"}
    secret = "p238-only-password"
    url = "postgresql+psycopg://synthetic:" + secret + "@localhost/synthetic_test"
    assert secret not in runner.redact(url + " " + secret, {"EG_TEST_DATABASE_URL": url})


def test_workflow_only_adds_one_step_after_original_suite() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    block = (
        "      - name: Run review database mutation controls\n"
        "        run: uv run --locked --no-sync --offline python infra/ci/review_mutations.py\n"
    )
    assert workflow.count(block) == 1
    assert "run: uv run --locked pytest -m integration\n\n" + block in workflow
    # Stable at candidate HEAD too; CI checkouts need not contain historical commit objects.
    baseline = workflow.replace("\n" + block, "").encode()
    assert runner.hashes({"workflow": baseline})["workflow"] == (
        "4a6a5ccf7861d1e98d6503bc9a5694bb6a339ee037c372fb0b0d6f3f5dc88e87"
    )  # exact reviewed workflow at 2a388dc3, before the single additive step


@pytest.mark.parametrize(
    ("body", "failed"),
    [
        ('    assert True, "p238_detector_A"\n', False),
        ('    assert False, "p238_detector_A"\n', True),
        (
            '    assert (\n        1,\n        "completed",\n'
            '    ) == (1, "started"), "p238_detector_A"\n',
            True,
        ),
    ],
)
def test_real_bootstrap_uses_only_isolated_stub_modules(
    tmp_path: Path, body: str, failed: bool
) -> None:
    """Real pytest subprocess over inert stubs, not application/database controls."""
    copy = tmp_path / "copy"
    sources = {p: b"" for p in IMPORT_PATHS.values() if not p.endswith("postgres.py")}
    sources.update(
        {
            "pyproject.toml": b"[tool.pytest.ini_options]\n",
            "tests/__init__.py": b"",
            "tests/test_probe.py": (
                "from tests import review_postgres_world\ndef test_probe():\n" + body
            ).encode(),
        }
    )
    for name in list(sources):
        if "/evidenceguard_" in name:
            sources[str(Path(name).parent / "__init__.py").replace("\\", "/")] = b""
    for name, data in sources.items():
        path = copy / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    runner.write_json(copy / "_p238_manifest.json", runner.hashes(sources))
    (copy / "_p238_bootstrap.py").write_text(runner.BOOTSTRAP)
    probe = tmp_path / "imports.json"
    xml = tmp_path / "junit.xml"
    command = [
        sys.executable,
        "-I",
        str(copy / "_p238_bootstrap.py"),
        str(probe),
        "-c",
        str(copy / "pyproject.toml"),
        "--junitxml=" + str(xml),
        "-p",
        "no:cacheprovider",
        "--import-mode=importlib",
        "tests/test_probe.py::test_probe",
    ]
    result = runner.execute(command, copy, {"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}, 25)
    assert result.returncode == int(failed), result.stdout + result.stderr
    observed = json.loads(probe.read_text())
    nodes = ("tests/test_probe.py::test_probe",)
    runner.validate_imports(observed, copy, runner.hashes(sources), nodes)
    mutation = (
        runner.Mutation("A", "tests/test_probe.py", "test_probe", (), "inert stub")
        if failed
        else None
    )
    runner.judge(
        xml.read_text(), observed, result.returncode, nodes, mutation, 3 if failed else None
    )


def test_candidate_manifest_excludes_untracked_and_rejects_index_drift(tmp_path: Path) -> None:
    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, capture_output=True, check=True)

    git("init", "--quiet")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/control.py").write_bytes(b"# synthetic\n")
    git("add", "--", "tests/control.py")
    (tmp_path / "tests/.env").write_bytes(b"synthetic-private-not-copied")
    (tmp_path / "tests/local.py").write_bytes(b"# unrelated\n")
    assert runner.candidate(tmp_path) == {"tests/control.py": b"# synthetic\n"}
    (tmp_path / "tests/control.py").write_bytes(b"# changed after staging\n")
    with pytest.raises(runner.Rejected, match="candidate_index_mismatch"):
        runner.candidate(tmp_path)


def test_real_subprocess_timeout_kills_only_its_child(tmp_path: Path) -> None:
    command = [sys.executable, "-I", "-c", "import time; time.sleep(20)"]
    with pytest.raises(subprocess.TimeoutExpired):
        runner.execute(command, tmp_path, {}, 0.2)


def test_copy_source_mismatch_refuses_dispatch(
    checkout: tuple[Path, dict[str, bytes], Path],
) -> None:
    root, _, output = checkout
    (root / runner.HANDLER).write_bytes(b"# unexpected change\n")
    fake = FakeExecutor()
    with pytest.raises(runner.Rejected, match="checkout_source_mismatch"):
        run(checkout, fake)
    assert not fake.calls and not list(output.glob("copy-*"))


def test_actual_source_copy_imports_and_collects_without_database(tmp_path: Path) -> None:
    """Collection/import-path proof only; no fixture or database test body is executed."""
    sources = runner.candidate(ROOT)
    copy = tmp_path / "actual-source-copy"
    for name, data in sources.items():
        path = copy / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    runner.write_json(copy / "_p238_manifest.json", runner.hashes(sources))
    (copy / "_p238_bootstrap.py").write_text(runner.BOOTSTRAP, encoding="utf-8")
    probe = tmp_path / "imports.json"
    environment = {
        k: v
        for k, v in os.environ.items()
        if k.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "TMP", "TEMP"}
    }
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    result = runner.execute(
        [
            sys.executable,
            "-I",
            str(copy / "_p238_bootstrap.py"),
            str(probe),
            "-c",
            str(copy / "pyproject.toml"),
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            "--import-mode=importlib",
            runner.HANDLER,
            runner.CANARY,
        ],
        copy,
        environment,
        30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "12 tests collected" in result.stdout
    observed = json.loads(probe.read_text(encoding="utf-8"))
    assert observed["reports"] == []
    runner.validate_imports(observed, copy, runner.hashes(sources), runner.control_ids(sources))
    assert runner.hashes(runner.read_sources(ROOT, list(sources))) == runner.hashes(sources)
