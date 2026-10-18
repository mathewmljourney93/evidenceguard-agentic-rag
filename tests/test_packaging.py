import ast
import sys
from importlib.metadata import distribution, entry_points
from pathlib import Path
from types import ModuleType

import pytest

import evidenceguard_api
import evidenceguard_domain
import evidenceguard_observability
import evidenceguard_persistence
import evidenceguard_retrieval
import evidenceguard_worker
from evidenceguard_api.__main__ import main


def test_eg_api_console_script_is_registered() -> None:
    (script,) = entry_points(group="console_scripts", name="eg-api")

    assert script.value == "evidenceguard_api.__main__:main"
    assert script.dist is not None
    assert script.dist.name == "evidenceguard"
    assert script.load() is main


def test_distribution_requires_python_312() -> None:
    assert distribution("evidenceguard").metadata["Requires-Python"] == "<3.13,>=3.12"


def test_eg_api_help_exits_cleanly(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--help"])

    assert exit_info.value.code == 0
    assert "usage: eg-api" in capsys.readouterr().out


def _top_level_imports(package_dir: Path) -> set[str]:
    imported: set[str] = set()
    for source in package_dir.rglob("*.py"):
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
    return imported


@pytest.mark.parametrize(
    ("package", "forbidden"),
    [
        (
            evidenceguard_domain,
            {
                "evidenceguard_api",
                "evidenceguard_observability",
                "evidenceguard_persistence",
                "evidenceguard_retrieval",
                "evidenceguard_worker",
            },
        ),
        (
            evidenceguard_observability,
            {
                "evidenceguard_api",
                "evidenceguard_persistence",
                "evidenceguard_retrieval",
                "evidenceguard_worker",
            },
        ),
        (
            evidenceguard_persistence,
            {"evidenceguard_api", "evidenceguard_retrieval", "evidenceguard_worker"},
        ),
        (
            evidenceguard_retrieval,
            {
                "evidenceguard_api",
                "evidenceguard_observability",
                "evidenceguard_persistence",
                "evidenceguard_worker",
            },
        ),
        (evidenceguard_api, {"evidenceguard_worker"}),
        (evidenceguard_worker, {"evidenceguard_api"}),
    ],
)
def test_package_import_boundaries(package: ModuleType, forbidden: set[str]) -> None:
    assert package.__file__ is not None
    assert not _top_level_imports(Path(package.__file__).parent) & forbidden


def test_retrieval_imports_only_the_domain_and_the_standard_library() -> None:
    """M3d: the chunker is pure code with no I/O dependencies (ADR-0010)."""
    assert evidenceguard_retrieval.__file__ is not None
    imported = _top_level_imports(Path(evidenceguard_retrieval.__file__).parent)
    assert {name for name in imported if name.startswith("evidenceguard")} <= {
        "evidenceguard_domain",
        "evidenceguard_retrieval",
    }
    assert not imported & {"sqlalchemy", "psycopg", "httpx", "socket", "urllib", "requests", "os"}


def _module_imports(path: Path) -> set[str]:
    imported: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    return imported


@pytest.mark.parametrize(
    ("package", "allowed"),
    [
        (evidenceguard_domain, {"evidenceguard_domain"}),
        (
            evidenceguard_persistence,
            {"evidenceguard_domain", "evidenceguard_persistence", "sqlalchemy"},
        ),
        (
            evidenceguard_worker,
            {
                "evidenceguard_domain",
                "evidenceguard_persistence",
                "evidenceguard_retrieval",
                "sqlalchemy",
            },
        ),
    ],
)
def test_m4d_retrieval_modules_keep_the_accepted_boundaries(
    package: ModuleType, allowed: set[str]
) -> None:
    """M4d (ADR-0016): pure values and fusion in the domain, capture and retrieval in
    persistence, provider orchestration in the worker; standard library otherwise."""
    assert package.__file__ is not None
    module = Path(package.__file__).parent / "retrieval.py"
    third_party = _module_imports(module) - set(sys.stdlib_module_names)
    assert third_party <= allowed


@pytest.mark.parametrize(
    ("module", "allowed"),
    [
        ("evaluation/__init__.py", set()),
        ("evaluation/corpus.py", {"evidenceguard_domain"}),
        ("evaluation/anchors.py", {"evidenceguard_domain", "evidenceguard_retrieval"}),
        ("evaluation/recall.py", {"evidenceguard_retrieval"}),
    ],
)
def test_m4e_evaluation_modules_are_pure(module: str, allowed: set[str]) -> None:
    """M4e (ADR-0017): corpus, anchor and Recall code use only the standard library, the domain
    and the retrieval package: no file-system, database or network module, and no ``os``."""
    assert evidenceguard_retrieval.__file__ is not None
    imported = _module_imports(Path(evidenceguard_retrieval.__file__).parent / module)
    assert imported - set(sys.stdlib_module_names) <= allowed
    assert not imported & {"os", "pathlib", "shutil", "io", "socket", "urllib", "http", "sqlite3"}


def test_m4e_worker_orchestration_keeps_the_accepted_boundaries() -> None:
    """M4e (ADR-0017): the test-only orchestrator may use persistence, retrieval and SQLAlchemy,
    never the API."""
    assert evidenceguard_worker.__file__ is not None
    module = Path(evidenceguard_worker.__file__).parent / "evaluation.py"
    third_party = _module_imports(module) - set(sys.stdlib_module_names)
    assert third_party <= {
        "evidenceguard_domain",
        "evidenceguard_persistence",
        "evidenceguard_retrieval",
        "evidenceguard_worker",
        "sqlalchemy",
    }


def test_no_evaluation_command_is_installed() -> None:
    """M4e has no installed command; the PostgreSQL tests are the only callers."""
    names = {script.name for script in entry_points(group="console_scripts")}
    assert "eg-eval" not in names


def test_m4f_voyage_adapter_is_pure_and_network_free() -> None:
    """M4f (ADR-0018): the adapter uses only the standard library and the domain, with no
    network, file-system or environment module."""
    assert evidenceguard_retrieval.__file__ is not None
    imported = _module_imports(Path(evidenceguard_retrieval.__file__).parent / "voyage.py")
    assert imported - set(sys.stdlib_module_names) <= {"evidenceguard_domain"}
    assert not imported & {"os", "socket", "ssl", "http", "urllib", "pathlib", "io", "requests"}


def test_m4f_voyage_transport_uses_only_the_standard_library_and_pydantic() -> None:
    """M4f (ADR-0018): the HTTPS transport is ``http.client``-based, with no SDK, third-party
    HTTP client or environment access."""
    assert evidenceguard_worker.__file__ is not None
    module = Path(evidenceguard_worker.__file__).parent / "voyage_http.py"
    imported = _module_imports(module)
    assert imported - set(sys.stdlib_module_names) <= {"evidenceguard_retrieval", "pydantic"}
    assert not imported & {"os", "requests", "httpx", "aiohttp", "urllib3", "voyageai"}


def test_m4f_leaves_the_production_providers_registry_and_commands_unchanged() -> None:
    """M4f is constructed explicitly only: production indexing stays offline-only, the registry
    kinds and installed commands are unchanged, and no module reads a Voyage setting."""
    from evidenceguard_retrieval.embeddings import HASH_IDENTITY
    from evidenceguard_worker.handlers import production_registry
    from evidenceguard_worker.indexing import SUPPORTED_PROVIDERS

    assert tuple(SUPPORTED_PROVIDERS) == (HASH_IDENTITY.fingerprint,)
    assert production_registry().kinds == frozenset({"ingest_revision", "index_revision"})
    names = {
        script.name
        for script in entry_points(group="console_scripts")
        if script.dist is not None and script.dist.name == "evidenceguard"
    }
    assert names == {"eg-api", "eg-admin", "eg-worker"}
    mentions = set()
    for package in (evidenceguard_api, evidenceguard_persistence, evidenceguard_worker):
        assert package.__file__ is not None
        for source in Path(package.__file__).parent.rglob("*.py"):
            if "voyage" in source.read_text(encoding="utf-8").lower():
                mentions.add(source.name)
    assert mentions == {"voyage_http.py"}  # no registration, setting, CLI or API wiring
