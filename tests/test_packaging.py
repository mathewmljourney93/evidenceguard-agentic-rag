import ast
from importlib.metadata import distribution, entry_points
from pathlib import Path
from types import ModuleType

import pytest

import evidenceguard_domain
import evidenceguard_observability
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
        (evidenceguard_domain, {"evidenceguard_api", "evidenceguard_observability"}),
        (evidenceguard_observability, {"evidenceguard_api"}),
    ],
)
def test_package_import_boundaries(package: ModuleType, forbidden: set[str]) -> None:
    assert package.__file__ is not None
    assert not _top_level_imports(Path(package.__file__).parent) & forbidden
