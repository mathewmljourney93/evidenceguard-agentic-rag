import ast
import sys
from importlib.metadata import distribution, entry_points
from pathlib import Path
from types import ModuleType

import pytest

import evidenceguard_agents
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
                "evidenceguard_agents",
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
                "evidenceguard_agents",
                "evidenceguard_api",
                "evidenceguard_persistence",
                "evidenceguard_retrieval",
                "evidenceguard_worker",
            },
        ),
        (
            evidenceguard_persistence,
            {
                "evidenceguard_agents",
                "evidenceguard_api",
                "evidenceguard_retrieval",
                "evidenceguard_worker",
            },
        ),
        (
            evidenceguard_retrieval,
            {
                "evidenceguard_agents",
                "evidenceguard_api",
                "evidenceguard_observability",
                "evidenceguard_persistence",
                "evidenceguard_worker",
            },
        ),
        (
            evidenceguard_agents,
            {
                "evidenceguard_api",
                "evidenceguard_persistence",
                "evidenceguard_retrieval",
                "evidenceguard_worker",
                "sqlalchemy",
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


# --- M5a (ADR-0019) ------------------------------------------------------------------------------

M5A_FORBIDDEN_MODULES = {"socket", "ssl", "http", "urllib", "os", "pathlib", "tomllib", "io"}


@pytest.mark.parametrize(
    ("module", "allowed"),
    [
        ("model_calls.py", {"evidenceguard_domain"}),
        ("agent_outputs.py", {"evidenceguard_domain", "pydantic"}),
    ],
)
def test_m5a_domain_modules_keep_the_accepted_imports(module: str, allowed: set[str]) -> None:
    """M5a: the call values use only the standard library and the domain; the output schemas
    add Pydantic. These are architectural checks against accidental access, not a sandbox."""
    assert evidenceguard_domain.__file__ is not None
    imported = _module_imports(Path(evidenceguard_domain.__file__).parent / module)
    assert imported - set(sys.stdlib_module_names) <= allowed
    assert not imported & M5A_FORBIDDEN_MODULES


@pytest.mark.parametrize("module", ["__init__.py", "providers.py", "scripted.py"])
def test_m5a_agents_modules_use_only_the_domain_and_the_standard_library(module: str) -> None:
    """M5a: the provider boundary and the scripted fake cannot reach files, the environment,
    the network or the ground truth through these imports, and use no third-party package."""
    assert evidenceguard_agents.__file__ is not None
    imported = _module_imports(Path(evidenceguard_agents.__file__).parent / module)
    assert imported - set(sys.stdlib_module_names) <= {
        "evidenceguard_domain",
        "evidenceguard_agents",
    }
    assert not imported & M5A_FORBIDDEN_MODULES


def test_m5a_agents_package_contains_only_the_accepted_modules() -> None:
    """The M5a modules plus exactly the accepted M5c modules and data directory (M5c-B)."""
    assert evidenceguard_agents.__file__ is not None
    root = Path(evidenceguard_agents.__file__).parent
    names = {path.name for path in root.iterdir() if path.name != "__pycache__"}
    assert names == {
        "__init__.py",
        "py.typed",
        "providers.py",
        "scripted.py",
        "report.py",  # M5f: only the accepted pure builder/renderer is added.
        *M5C_MODULES,
        "data",
    }


def test_m5a_is_not_imported_by_other_packages_or_registered() -> None:
    """Only the apps (and later evaluation) may import ``evidenceguard_agents``; M5a adds no
    handler, command or production wiring. The accepted M5d composition module
    (``evidenceguard_worker/review_seams.py``, D2) is the only exception."""
    from evidenceguard_worker.handlers import production_registry

    for package in (
        evidenceguard_api,
        evidenceguard_domain,
        evidenceguard_observability,
        evidenceguard_persistence,
        evidenceguard_retrieval,
        evidenceguard_worker,
    ):
        assert package.__file__ is not None
        for source in Path(package.__file__).parent.rglob("*.py"):
            if package is evidenceguard_worker and source.name in M5G_AGENT_IMPORTERS:
                continue  # M5d composition (D2) and M5g orchestration (G12)
            assert "evidenceguard_agents" not in _module_imports(source), source.name
    assert production_registry().kinds == frozenset({"ingest_revision", "index_revision"})


M5G_AGENT_IMPORTERS = {"review_seams.py", "review.py"}
"""The only worker modules that import ``evidenceguard_agents``: M5d (D2) and M5g (G12)."""


# --- M5b (ADR-0020) ------------------------------------------------------------------------------


def test_m5b_provenance_uses_only_the_domain_and_the_standard_library() -> None:
    """M5b is pure: no Pydantic import of its own, no other package, no network, file, logging
    or environment module. An architectural check against accidental access, not a sandbox."""
    assert evidenceguard_domain.__file__ is not None
    path = Path(evidenceguard_domain.__file__).parent / "provenance.py"
    imported = _module_imports(path)
    assert imported - set(sys.stdlib_module_names) == {"evidenceguard_domain"}
    assert not imported & (M5A_FORBIDDEN_MODULES | {"logging", "pydantic"})
    domain_modules = {
        node.module
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("evidence")
    }
    assert domain_modules == {
        "evidenceguard_domain.agent_outputs",
        "evidenceguard_domain.chunks",
        "evidenceguard_domain.evidence",
        "evidenceguard_domain.model_calls",
        "evidenceguard_domain.retrieval",
    }


def test_m5b_is_not_wired_into_any_application_or_handler() -> None:
    """M5b adds no handler, endpoint, command or persistence use; later slices own that. The
    accepted M5c request assembly and M5f pure report builder may use its values; the accepted
    M5e stage persistence (M5e-A) remains the only persistence consumer."""
    allowed = {
        (evidenceguard_agents, "assembly.py"),
        (evidenceguard_agents, "report.py"),  # M5f's accepted pure provenance rechecks.
        (evidenceguard_persistence, "review_stages.py"),
        (evidenceguard_worker, "review.py"),  # M5g orchestration composes the M5b conversions.
    }
    for package in (
        evidenceguard_agents,
        evidenceguard_api,
        evidenceguard_observability,
        evidenceguard_persistence,
        evidenceguard_retrieval,
        evidenceguard_worker,
    ):
        assert package.__file__ is not None
        for source in Path(package.__file__).parent.rglob("*.py"):
            if (package, source.name) in allowed:
                continue
            assert "provenance" not in source.read_text(encoding="utf-8"), source.name


# --- M5c (ADR-0021) ------------------------------------------------------------------------------

M5C_MODULES = {"artifact_errors.py", "templates.py", "planner.py", "prompts.py", "assembly.py"}
M5C_DATA_FILES = {
    "templates/vendor_security_review_v1.toml",
    "prompts/verifier/v1.md",
    "prompts/risk_analyst/v1.md",
}
# M5c-B: the standard library each module may import, and the domain modules it may use.
M5C_STDLIB = {
    "artifact_errors.py": {"collections", "typing"},
    "templates.py": {"tomllib", "hashlib", "dataclasses", "contextlib", "importlib"},
    "prompts.py": {"tomllib", "hashlib", "dataclasses", "contextlib", "importlib"},
    "planner.py": {"json", "hashlib", "dataclasses", "enum", "contextlib"},
    "assembly.py": {"json", "hashlib", "dataclasses", "enum", "contextlib"},
}
M5C_DOMAIN = {
    "artifact_errors.py": set(),
    "templates.py": {"evidenceguard_domain.evidence", "evidenceguard_domain.model_calls"},
    "prompts.py": {"evidenceguard_domain.model_calls"},
    "planner.py": {"evidenceguard_domain.evidence", "evidenceguard_domain.retrieval"},
    "assembly.py": {
        "evidenceguard_domain.evidence",
        "evidenceguard_domain.model_calls",
        "evidenceguard_domain.provenance",
    },
}


def _agents_root() -> Path:
    assert evidenceguard_agents.__file__ is not None
    return Path(evidenceguard_agents.__file__).parent


def test_m5c_packaged_data_is_exactly_the_accepted_file_set() -> None:
    data = _agents_root() / "data"
    found = {path.relative_to(data).as_posix() for path in data.rglob("*") if path.is_file()}
    assert found == M5C_DATA_FILES


@pytest.mark.parametrize("module", sorted(M5C_MODULES))
def test_m5c_modules_keep_the_accepted_imports(module: str) -> None:
    """M5c-B allowlists: no network, file-path, environment, logging or third-party import;
    resources are read only through ``importlib.resources``. Architectural checks against
    accidental access, not a sandbox."""
    path = _agents_root() / module
    imported = _module_imports(path)
    stdlib = imported & set(sys.stdlib_module_names)
    assert stdlib <= M5C_STDLIB[module]
    assert imported - stdlib <= {"evidenceguard_agents", "evidenceguard_domain"}
    assert not imported & {"os", "pathlib", "io", "socket", "ssl", "http", "urllib", "logging"}
    tree = ast.parse(path.read_text(encoding="utf-8"))
    domain = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module
        and node.module.startswith("evidenceguard_domain")
    }
    assert domain == M5C_DOMAIN[module]
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("importlib"):
            assert node.module == "importlib.resources"
            assert [alias.name for alias in node.names] == ["files"]
        if isinstance(node, ast.Import):
            assert not any(alias.name.startswith("importlib") for alias in node.names)


def test_no_agents_module_reads_the_evaluation_data() -> None:
    for source in _agents_root().rglob("*.py"):
        text = source.read_text(encoding="utf-8")
        assert "ground_truth" not in text and "sample_data" not in text, source.name


def test_m5c_resources_are_readable_through_the_package() -> None:
    from importlib.resources import files

    root = files("evidenceguard_agents").joinpath("data")
    for name in M5C_DATA_FILES:
        assert root.joinpath(*name.split("/")).is_file(), name


# --- M5d (ADR-0022) ------------------------------------------------------------------------------


def _source(package: ModuleType, name: str) -> Path:
    assert package.__file__ is not None
    return Path(package.__file__).parent / name


def test_m5d_domain_values_use_only_the_domain_and_the_standard_library() -> None:
    imported = _module_imports(_source(evidenceguard_domain, "reviews.py"))
    assert imported - set(sys.stdlib_module_names) == {"evidenceguard_domain"}
    assert not imported & {"os", "pathlib", "io", "socket", "logging", "sqlalchemy", "pydantic"}


def test_m5d_database_failure_classifier_imports_only_sqlalchemy_errors() -> None:
    path = _source(evidenceguard_persistence, "database_failures.py")
    imported = _module_imports(path)
    assert imported - set(sys.stdlib_module_names) == {"sqlalchemy"}
    modules = {
        node.module
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert modules == {"enum", "sqlalchemy.exc"}


def test_m5d_persistence_reviews_keep_the_accepted_boundaries() -> None:
    imported = _module_imports(_source(evidenceguard_persistence, "reviews.py"))
    assert imported - set(sys.stdlib_module_names) == {
        "evidenceguard_domain",
        "evidenceguard_persistence",
        "sqlalchemy",
    }
    assert not imported & {"evidenceguard_agents", "logging", "os", "socket", "time"}


def test_m5d_review_seams_are_the_only_worker_module_importing_agents() -> None:
    importing = {
        source.name
        for source in _source(evidenceguard_worker, "__init__.py").parent.rglob("*.py")
        if "evidenceguard_agents" in _module_imports(source)
    }
    assert importing == M5G_AGENT_IMPORTERS  # M5d's D2 module plus M5g's G12 module
    imported = _module_imports(_source(evidenceguard_worker, "review_seams.py"))
    assert imported - set(sys.stdlib_module_names) == {
        "evidenceguard_agents",
        "evidenceguard_domain",
        "evidenceguard_persistence",
        "sqlalchemy",
    }


def test_m5d_creation_is_not_wired_into_any_route_command_or_runtime_path() -> None:
    """W8: creation and reload stay internal or test-only; ``run_review`` stays unregistered."""
    from evidenceguard_worker.handlers import production_registry

    for package in (evidenceguard_api, evidenceguard_observability, evidenceguard_retrieval):
        assert package.__file__ is not None
        for source in Path(package.__file__).parent.rglob("*.py"):
            text = source.read_text(encoding="utf-8")
            assert "review_seams" not in text and "persistence.reviews" not in text, source.name
            assert "run_review" not in text, source.name
    assert evidenceguard_worker.__file__ is not None
    for source in Path(evidenceguard_worker.__file__).parent.rglob("*.py"):
        if source.name == "review_seams.py":
            continue
        text = source.read_text(encoding="utf-8")
        assert "persistence.reviews" not in text, source.name
        if source.name == "review.py":
            continue  # M5g: the unregistered run_review composition uses the M5d seams (G12)
        assert "review_seams" not in text, source.name
        assert "run_review" not in text, source.name
    assert "run_review" not in production_registry().kinds


# --- M5e (ADR-0023) ------------------------------------------------------------------------------

M5E_FORBIDDEN = {"os", "pathlib", "io", "socket", "ssl", "http", "urllib", "logging", "time"}


def _domain_imports(path: Path) -> set[str]:
    """Every ``evidenceguard_domain`` module imported anywhere in ``path``, including local or
    deferred imports inside functions (``ast.walk`` visits every node)."""
    return {
        node.module
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.ImportFrom)
        and node.module
        and node.module.startswith("evidenceguard_domain")
    }


def test_m5e_domain_module_imports_only_the_accepted_domain_modules() -> None:
    """M5e-A: the pure module imports only the standard library and the domain (``model_calls``,
    ``provenance``, ``retrieval``, ``evidence``, ``jobs``), never ``evidenceguard_agents``, also
    not through a local or deferred import, and no third-party package of its own."""
    path = _source(evidenceguard_domain, "review_stages.py")
    imported = _module_imports(path)
    assert imported - set(sys.stdlib_module_names) == {"evidenceguard_domain"}
    assert not imported & (M5E_FORBIDDEN | {"pydantic", "sqlalchemy", "evidenceguard_agents"})
    assert _domain_imports(path) == {
        "evidenceguard_domain.evidence",
        "evidenceguard_domain.jobs",
        "evidenceguard_domain.model_calls",
        "evidenceguard_domain.provenance",
        "evidenceguard_domain.retrieval",
    }


@pytest.mark.parametrize(
    "package,name,allowed",
    [
        (evidenceguard_domain, "report_content.py", {"evidenceguard_domain"}),
        (evidenceguard_agents, "report.py", {"evidenceguard_domain", "evidenceguard_agents"}),
    ],
)
def test_m5f_report_modules_keep_the_pure_import_boundary(
    package: ModuleType,
    name: str,
    allowed: set[str],
) -> None:
    path = _source(package, name)
    assert _module_imports(path) - set(sys.stdlib_module_names) <= allowed
    tree = ast.parse(path.read_text(encoding="utf-8"))
    forbidden_calls = {
        "open",
        "files",
        "load_template",
        "load_pinned_template",
        "load_prompt",
        "load_pinned_prompt",
        "now",
        "utcnow",
        "uuid4",
        "connect",
        "urlopen",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = (
                node.func.attr
                if isinstance(node.func, ast.Attribute)
                else node.func.id
                if isinstance(node.func, ast.Name)
                else ""
            )
            assert name not in forbidden_calls


def test_m5f_is_not_wired_into_any_application_or_worker() -> None:
    for package in (evidenceguard_api, evidenceguard_worker, evidenceguard_persistence):
        assert package.__file__ is not None
        for path in Path(package.__file__).parent.rglob("*.py"):
            if package is evidenceguard_worker and path.name == "review.py":
                continue  # M5g: the only consumer of the M5f builder/renderer (G12)
            imports = _module_imports(path)
            assert "evidenceguard_agents.report" not in _domain_imports(path)
            assert "evidenceguard_domain.report_content" not in _domain_imports(path)
            assert "report_content" not in imports


def test_m5e_persistence_module_keeps_the_accepted_boundaries() -> None:
    """M5e-A: the domain, persistence (jobs, reviews' values, retrieval) and SQLAlchemy only;
    never the agents, the worker or a provider."""
    path = _source(evidenceguard_persistence, "review_stages.py")
    imported = _module_imports(path)
    assert imported - set(sys.stdlib_module_names) == {
        "evidenceguard_domain",
        "evidenceguard_persistence",
        "sqlalchemy",
    }
    assert not imported & (M5E_FORBIDDEN | {"evidenceguard_agents", "evidenceguard_worker"})
    modules = {
        node.module
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.ImportFrom)
        and node.module
        and node.module.startswith("evidenceguard_persistence")
    }
    assert modules == {
        "evidenceguard_persistence.document_views",
        "evidenceguard_persistence.jobs",
        "evidenceguard_persistence.models",
        "evidenceguard_persistence.retrieval",
    }


def test_m5e_migration_and_modules_are_packaged() -> None:
    assert _source(evidenceguard_domain, "review_stages.py").is_file()
    assert _source(evidenceguard_persistence, "review_stages.py").is_file()
    migration = _source(evidenceguard_persistence, "migrations/versions/v0007_review_stages.py")
    assert migration.is_file()
    assert not _module_imports(migration) & {"evidenceguard_persistence", "evidenceguard_domain"}


def test_m5e_is_not_wired_into_any_route_command_handler_or_registry() -> None:
    """W8: M5e stays internal. Only M5f's pure report consumer may use its domain values;
    no application/worker/observability use, output table/writer (E7), or run_review registration.
    """
    from evidenceguard_worker.handlers import production_registry

    for package in (
        evidenceguard_agents,
        evidenceguard_api,
        evidenceguard_observability,
        evidenceguard_retrieval,
        evidenceguard_worker,
    ):
        assert package.__file__ is not None
        for source in Path(package.__file__).parent.rglob("*.py"):
            if package is evidenceguard_agents and source.name == "report.py":
                continue  # M5f consumes domain stage values, never persistence/runtime seams.
            if package is evidenceguard_worker and source.name == "review.py":
                continue  # M5g: the unregistered orchestration is the M5e consumer (G12).
            assert "review_stages" not in source.read_text(encoding="utf-8"), source.name
    persistence = _source(evidenceguard_persistence, "__init__.py").parent
    users = {
        source.name
        for source in persistence.rglob("*.py")
        if "review_stages" in source.read_text(encoding="utf-8")
    }
    assert users == {"review_stages.py", "review_outputs.py"}  # M5g reuses ``StageFence``
    assert "run_review" not in production_registry().kinds
    assert production_registry().kinds == frozenset({"ingest_revision", "index_revision"})


# --- M5g (ADR-0025) ------------------------------------------------------------------------------


def test_m5g_domain_outputs_use_only_the_domain_and_the_standard_library() -> None:
    path = _source(evidenceguard_domain, "review_outputs.py")
    assert _module_imports(path) - set(sys.stdlib_module_names) == {"evidenceguard_domain"}
    assert _domain_imports(path) == {"evidenceguard_domain.report_content"}
    assert not _module_imports(path) & (M5E_FORBIDDEN | {"pydantic", "sqlalchemy"})


def test_m5g_persistence_outputs_never_import_the_agents_or_the_worker() -> None:
    path = _source(evidenceguard_persistence, "review_outputs.py")
    imported = _module_imports(path)
    assert imported - set(sys.stdlib_module_names) == {
        "evidenceguard_domain",
        "evidenceguard_persistence",
        "sqlalchemy",
    }
    assert not imported & (M5E_FORBIDDEN | {"evidenceguard_agents", "evidenceguard_worker"})
    migration = _source(evidenceguard_persistence, "migrations/versions/v0008_review_outputs.py")
    assert migration.is_file()
    assert not _module_imports(migration) & {"evidenceguard_persistence", "evidenceguard_domain"}


def test_m5g_orchestration_keeps_the_accepted_boundaries() -> None:
    imported = _module_imports(_source(evidenceguard_worker, "review.py"))
    assert imported - set(sys.stdlib_module_names) == {
        "evidenceguard_agents",
        "evidenceguard_domain",
        "evidenceguard_persistence",
        "evidenceguard_retrieval",
        "evidenceguard_worker",
        "sqlalchemy",
    }
    assert not imported & {"logging", "os", "socket", "http", "urllib", "ssl"}


def test_m5g_is_not_wired_into_any_route_command_setting_or_production_registry() -> None:
    """W8: ``run_review`` stays unregistered; nothing outside tests builds the handler."""
    from evidenceguard_worker.handlers import production_registry

    for package in (
        evidenceguard_api,
        evidenceguard_observability,
        evidenceguard_persistence,
        evidenceguard_retrieval,
        evidenceguard_agents,
        evidenceguard_domain,
        evidenceguard_worker,
    ):
        assert package.__file__ is not None
        for source in Path(package.__file__).parent.rglob("*.py"):
            if package is evidenceguard_worker and source.name == "review.py":
                continue
            text = source.read_text(encoding="utf-8")
            assert "make_run_review_handler" not in text, source.name
            assert "evidenceguard_worker.review " not in text, source.name
            assert "from evidenceguard_worker.review import" not in text, source.name
            if package is not evidenceguard_persistence and package is not evidenceguard_domain:
                assert "review_outputs" not in text, source.name
    assert production_registry().kinds == frozenset({"ingest_revision", "index_revision"})
