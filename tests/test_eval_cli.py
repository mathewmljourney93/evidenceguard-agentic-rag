"""M7 (ADR-0029): ``eg-eval`` exit codes, usage privacy, offline help and no secret option."""

import argparse
from decimal import Decimal
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any

import pytest

from evidenceguard_evaluation import cli
from evidenceguard_evaluation.cli import RunOptions
from evidenceguard_worker import evaluation_run

ROOT = Path(__file__).resolve().parents[1]
MARKER = "VALUE-MARKER-must-not-echo"


class _Runner:
    def __init__(self, code: int = 0) -> None:
        self.code = code
        self.options: list[RunOptions] = []

    def __call__(self, options: RunOptions) -> int:
        self.options.append(options)
        return self.code


def _main(argv: list[str], runner: Any = None) -> int:
    return cli.main(argv, runner=runner or _Runner(), root=ROOT)


def test_eg_eval_is_installed_and_targets_the_worker_composition_root() -> None:
    (script,) = entry_points(group="console_scripts", name="eg-eval")
    assert script.value == "evidenceguard_worker.evaluation_run:main"
    assert script.load() is evaluation_run.main


@pytest.mark.parametrize("argv", [["--help"], ["run", "--help"], ["report", "--help"]])
def test_help_needs_no_environment(
    argv: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name in ("EG_EVAL_DATABASE_URL", "EG_DATABASE_URL", "EG_ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(SystemExit) as exited:
        evaluation_run.main(argv)
    assert exited.value.code == 0
    assert "usage: eg-eval" in capsys.readouterr().out


def _option_strings(parser: argparse.ArgumentParser) -> list[str]:
    found: list[str] = []
    for action in parser._actions:
        found += action.option_strings
        if isinstance(action, argparse._SubParsersAction):
            for child in action.choices.values():
                found += _option_strings(child)
    return found


def test_no_option_takes_a_secret() -> None:
    names = _option_strings(cli.parser())
    assert "--budget-usd" in names and "--output" in names
    for name in names:
        for word in ("key", "token", "secret", "password", "credential", "url"):
            assert word not in name, name


@pytest.mark.parametrize(
    "argv",
    [
        ["run", "--suite", MARKER],
        ["run", "--suite", "contract"],  # --output is required
        ["run", "--suite", "contract", "--output", "x.json", "--model", MARKER],
        ["run", "--suite", "contract", "--output", "docs/evaluation/runs/c.json"],
        ["run", "--suite", "live", "--model", MARKER, "--runs", "1"],  # no budget
        ["run", "--suite", "live", "--model", "m", "--runs", MARKER, "--budget-usd", "1"],
        ["run", "--suite", "live", "--model", "m", "--runs", "1", "--budget-usd", MARKER],
        ["run", "--suite", "live", "--model", "m", "--runs", "1", "--budget-usd", "-1"],
        [
            "run",
            "--suite",
            "live",
            "--model",
            "m",
            "--runs",
            "1",
            "--budget-usd",
            "1",
            "--output",
            "x.json",
        ],
        [MARKER],
    ],
)
def test_usage_errors_exit_2_and_echo_no_value(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    runner = _Runner()
    try:
        code = _main(argv, runner)
    except SystemExit as exited:
        code = int(exited.code or 0)
    assert code == 2 and runner.options == []
    captured = capsys.readouterr()
    assert MARKER not in captured.out + captured.err
    assert "invalid arguments" in captured.err


def test_run_passes_the_parsed_options_to_the_runner() -> None:
    runner = _Runner(code=5)
    argv = ["run", "--suite", "contract", "--output", "out/c.json", "--variant", "injected"]
    assert _main(argv, runner) == 5
    assert runner.options == [
        RunOptions("contract", "injected", Path("out/c.json"), None, 1, None, 60)
    ]
    argv = ["run", "--suite", "live", "--model", "m-1", "--runs", "3", "--budget-usd", "2.5"]
    assert _main(argv, runner) == 5
    assert runner.options[-1] == RunOptions("live", "clean", None, "m-1", 3, Decimal("2.5"), 60)


def test_a_configuration_refusal_exits_3_naming_the_variable_only(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.delenv("EG_EVAL_DATABASE_URL", raising=False)
    options = RunOptions("contract", "clean", tmp_path / "c.json", None, 1, None, 60)
    assert evaluation_run.run_suite(options) == 3
    assert "EG_EVAL_DATABASE_URL is not set" in capsys.readouterr().err
    monkeypatch.setenv("EG_EVAL_DATABASE_URL", f"postgresql://u:{MARKER}@localhost/db_test")
    assert evaluation_run.run_suite(options) == 3
    err = capsys.readouterr().err
    assert "must end in _eval" in err and MARKER not in err
    assert not (tmp_path / "c.json").exists()


def test_the_committed_files_refuse_a_live_run_with_exit_4(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EG_ANTHROPIC_API_KEY", "sk-ant-eg-fake-test-key-not-real-0002")
    argv = ["run", "--suite", "live", "--model", "m-1", "--runs", "1", "--budget-usd", "5"]
    assert evaluation_run.main(argv) == 4


def test_a_runtime_failure_exits_1_with_a_fixed_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def failing(options: RunOptions, environment: Any) -> int:
        raise RuntimeError(MARKER)

    monkeypatch.setattr(evaluation_run, "_execute", failing)
    options = RunOptions("contract", "clean", Path("c.json"), None, 1, None, 60)
    assert evaluation_run.run_suite(options) == 1
    err = capsys.readouterr().err
    assert "the evaluation run failed" in err and MARKER not in err


def test_record_statuses_map_to_exit_codes_0_5_and_6() -> None:
    assert evaluation_run.exit_code_for("completed") == 0
    assert evaluation_run.exit_code_for("hard_failure") == 5
    assert evaluation_run.exit_code_for("budget_stopped") == 6
    assert evaluation_run.exit_code_for("deadline_stopped") == 6
    with pytest.raises(ValueError):
        evaluation_run.exit_code_for("other")


def test_report_without_records_and_report_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _main(["report"]) == 0
    assert "No run records were given." in capsys.readouterr().out
    assert _main(["report", "--format", "readme"]) == 0
    assert "No committed live runs yet." in capsys.readouterr().out
    bad = tmp_path / "bad.json"
    bad.write_text('{"schema": 1}', encoding="ascii")
    assert _main(["report", str(bad)]) == 3
    assert _main(["report", str(tmp_path / "missing.json")]) == 3
