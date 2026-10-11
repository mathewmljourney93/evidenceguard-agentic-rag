import ast
from importlib.metadata import distribution, entry_points
from pathlib import Path

import pytest

import evidenceguard_domain
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


def test_domain_does_not_import_api() -> None:
    package_dir = Path(evidenceguard_domain.__file__).parent
    imported: set[str] = set()
    for source in package_dir.rglob("*.py"):
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)

    assert not any(name.split(".")[0] == "evidenceguard_api" for name in imported)
