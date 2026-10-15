"""Static invariants of the M3f container files (ADR-0012), checked without Docker.

The ``.dockerignore`` test applies an approximation of Docker's matching rules (the last matching
line wins, a pattern also matches a path's parent directories, ``**`` spans directories) to the
repository's real tracked files and to nested fixtures. It complements, and does not replace,
CI's effective build-context check, which exercises Docker itself.
"""

import importlib.util
import json
import re
import subprocess
from pathlib import Path, PurePosixPath
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
PYTHON_IMAGE = (
    "python:3.12.14-slim-trixie@sha256:"
    "f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f"
)
UV_IMAGE = (
    "ghcr.io/astral-sh/uv:0.13.0@sha256:"
    "cdc6093146eb3ff6a40107b38f008b789e050e77ad87865e381d9917da55a168"
)


def _load_ci() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "container_ci_files", ROOT / "infra/ci/container_ci.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ci = _load_ci()


def _instructions(text: str) -> list[tuple[str, str]]:
    """Dockerfile instructions with continuation lines joined; comments dropped."""
    joined = re.sub(r"\\\n\s*", " ", text)
    result = []
    for line in joined.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            keyword, _, rest = stripped.partition(" ")
            result.append((keyword.upper(), rest.strip()))
    return result


DOCKERFILE = _instructions((ROOT / "Dockerfile").read_text(encoding="utf-8"))
COMPOSE = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")


# --- Dockerfile -----------------------------------------------------------------------------------


def test_every_base_image_is_the_approved_digest() -> None:
    bases = [rest.split()[0] for keyword, rest in DOCKERFILE if keyword == "FROM"]
    assert bases == [PYTHON_IMAGE, PYTHON_IMAGE]
    copied_from = [
        re.search(r"--from=(\S+)", rest)[1]  # type: ignore[index]
        for keyword, rest in DOCKERFILE
        if keyword == "COPY" and "--from=" in rest
    ]
    assert copied_from == [UV_IMAGE, "builder"]


def test_the_runtime_stage_is_minimal_and_non_root() -> None:
    runtime = DOCKERFILE[[k for k, _ in DOCKERFILE].index("FROM", 1) :]
    copies = [rest for keyword, rest in runtime if keyword in ("COPY", "ADD")]
    assert copies == [
        "--from=builder --chown=root:root /opt/venv /opt/venv",
        "--chown=root:root alembic.ini /app/alembic.ini",
    ]
    users = [rest for keyword, rest in runtime if keyword == "USER"]
    assert users == ["10001:10001"]
    assert any("--uid 10001 --gid 10001" in rest for keyword, rest in runtime if keyword == "RUN")
    assert not any("uv" in rest.split() for keyword, rest in runtime if keyword == "RUN")


def test_commands_are_exec_form_and_nothing_secret_is_baked_in() -> None:
    (cmd,) = [rest for keyword, rest in DOCKERFILE if keyword == "CMD"]
    assert json.loads(cmd) == ["eg-api", "--host", "0.0.0.0", "--port", "8000"]
    assert not [keyword for keyword, _ in DOCKERFILE if keyword in ("ENTRYPOINT", "ARG")]
    environment = " ".join(rest for keyword, rest in DOCKERFILE if keyword == "ENV")
    for forbidden in ("EG_DATABASE_URL", "PASSWORD", "SECRET", "TOKEN", "KEY"):
        assert forbidden not in environment.upper()


def test_dependencies_install_from_the_lockfile_without_dev_or_editable() -> None:
    syncs = [rest for keyword, rest in DOCKERFILE if keyword == "RUN" and "uv sync" in rest]
    assert syncs == [
        "uv sync --locked --no-dev --no-install-project",
        "uv sync --locked --no-dev --no-editable",
    ]
    copies = [rest for keyword, rest in DOCKERFILE[:12] if keyword == "COPY"]
    assert not any(part in " ".join(copies) for part in ("tests", "docs", "prompts.md", ". ."))


# --- .dockerignore (approximation of Docker's rules) ---------------------------------------------


def _segment_regex(segment: str) -> str:
    out, index = "", 0
    while index < len(segment):
        char = segment[index]
        if char == "*":
            out += "[^/]*"
        elif char == "?":
            out += "[^/]"
        elif char == "[":
            end = segment.index("]", index)
            out += segment[index : end + 1]
            index = end
        else:
            out += re.escape(char)
        index += 1
    return out


def _pattern(pattern: str) -> re.Pattern[str]:
    segments = [s for s in pattern.strip("/").split("/") if s]
    parts = []
    for position, segment in enumerate(segments):
        last = position == len(segments) - 1
        if segment == "**":
            parts.append(".*" if last else "(?:[^/]+/)*")
        else:
            parts.append(_segment_regex(segment) + ("" if last else "/"))
    return re.compile("".join(parts))


def _rules() -> list[tuple[bool, re.Pattern[str]]]:
    rules = []
    for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        include = line.startswith("!")
        rules.append((include, _pattern(line.lstrip("!"))))
    return rules


RULES = _rules()


def sent_to_docker(path: str) -> bool:
    candidates = [
        str(PurePosixPath(*PurePosixPath(path).parts[: n + 1]))
        for n in range(len(PurePosixPath(path).parts))
    ]
    included = True
    for include, regex in RULES:
        if any(regex.fullmatch(candidate) for candidate in candidates):
            included = include
    return included


def tracked_files() -> list[str]:
    output = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True, check=True, timeout=60
    ).stdout.decode("utf-8")
    return [name for name in output.split("\0") if name and (ROOT / name).is_file()]


def test_the_context_contains_exactly_the_allowlisted_tracked_files() -> None:
    files = tracked_files()
    sent = {name for name in files if sent_to_docker(name)}
    assert sent == ci.expected_context(files)
    for name in ci.REQUIRED_PACKAGE_DATA:
        assert name in sent


@pytest.mark.parametrize(
    "name",
    [
        *ci.PLANTED_FIXTURES,
        ".env",
        ".git/config",
        ".local/p98/x",
        "tests/test_x.py",
        "prompts.md",
        "docs/plan.md",
        "dist/x.whl",
        ".venv/bin/python",
        ".github/workflows/ci.yml",
    ],
)
def test_nested_secrets_and_artifacts_are_excluded(name: str) -> None:
    assert not sent_to_docker(name)


# --- Compose and CI wiring ------------------------------------------------------------------------


def test_compose_keeps_the_approved_database_image_and_loopback_ports() -> None:
    images = re.findall(r"^\s+image:\s*(\S+)", COMPOSE, re.M)
    assert ci.PG_IMAGE in images
    assert "${EG_IMAGE:-evidenceguard:dev}" in images
    published = re.findall(r'^\s+- "([^"]+:[0-9]+:[0-9]+)"', COMPOSE, re.M)
    assert published and all(entry.startswith("127.0.0.1:") for entry in published)
    assert sorted(published) == ["127.0.0.1:5433:5432", "127.0.0.1:8000:8000"]
    assert re.search(r"^\s+pull_policy:\s*never\s*$", COMPOSE, re.M)


def test_the_container_job_runs_every_check_and_always_cleans_up() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    job = workflow[workflow.index("\n  container:") :]
    assert "timeout-minutes: 20" in job
    for command in ("config", "context", "image", "smoke", "cleanup"):
        assert f"python3 infra/ci/container_ci.py {command}" in job
    cleanup = job[job.index("Clean up") :]
    assert "if: always()" in cleanup
    assert "EG_COMPOSE_PROJECT: eg-ci-${{ github.run_id }}-${{ github.run_attempt }}" in job
    assert "EG_IMAGE: evidenceguard:ci-${{ github.run_id }}-${{ github.run_attempt }}" in job
    assert "docker login" not in job and "docker push" not in job
    for existing in ("\n  verify:", "\n  integration:"):
        assert existing in workflow
