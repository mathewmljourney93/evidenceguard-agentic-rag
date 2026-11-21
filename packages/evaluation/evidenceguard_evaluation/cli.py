"""The ``eg-eval`` argument parser and command dispatch (M7, ADR-0029).

Commands (the annotation workflow and the Verifier probe are deferred with the live runs):

- ``eg-eval run --suite contract --output PATH [--variant injected]``
- ``eg-eval run --suite live --model ID --runs N --budget-usd X [--variant injected]``
- ``eg-eval report RUN... [--select] [--format md|readme] [--write]``

Exit codes: 0 completed with no hard failure; 1 runtime failure (fixed generic message); 2
usage; 3 configuration refusal; 4 budget preflight refused, nothing called; 5 completed with a
hard failure, record written; 6 stopped by the budget guard or the deadline, partial record
written. ``--help`` needs no environment, usage errors never echo a value, and no option takes a
secret: the provider key is read from ``EG_ANTHROPIC_API_KEY`` only.

``main`` takes the runner (the worker's composition root) as an argument, so this package never
imports an application.
"""

import argparse
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import NoReturn

from evidenceguard_evaluation import report
from evidenceguard_evaluation.config import (
    EXIT_CONFIGURATION,
    EXIT_OK,
    EXIT_RUNTIME,
    EXIT_USAGE,
    EvaluationRefusal,
    parse_selection,
)
from evidenceguard_evaluation.records import parse_record

PROG = "eg-eval"
USAGE_ERROR_MESSAGE = f"{PROG}: error: invalid arguments; run with --help for usage\n"
RUNS_DIRECTORY = Path("docs") / "evaluation" / "runs"
SELECTION_FILE = Path("docs") / "evaluation" / "selection.toml"
DOCUMENTS_WITH_BLOCK = (Path("README.md"), Path("docs") / "evaluation.md")
MAX_RUNS = 20
MAX_DEADLINE_MINUTES = 24 * 60


class SafeArgumentParser(argparse.ArgumentParser):
    """An ``ArgumentParser`` whose usage errors never echo submitted values (the ``eg-admin``
    and ``eg-worker`` pattern, duplicated so this package imports no application)."""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)  # static: built from the parser definition only
        self.exit(EXIT_USAGE, USAGE_ERROR_MESSAGE)


@dataclass(frozen=True)
class RunOptions:
    suite: str
    variant: str
    output: Path | None
    model: str | None
    runs: int
    budget_usd: Decimal | None
    deadline_minutes: int


Runner = Callable[[RunOptions], int]


def _budget(text: str) -> Decimal:
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise argparse.ArgumentTypeError("invalid") from None
    if not value.is_finite() or value < 0:
        raise argparse.ArgumentTypeError("invalid")
    return value


def _bounded(high: int) -> Callable[[str], int]:
    def parse(text: str) -> int:
        if not text.isdigit() or not 1 <= int(text) <= high:
            raise argparse.ArgumentTypeError("invalid")
        return int(text)

    return parse


def parser() -> argparse.ArgumentParser:
    root = SafeArgumentParser(
        prog=PROG,
        allow_abbrev=False,
        description=(
            "Run and report EvidenceGuard evaluations. The contract suite uses scripted fake "
            "responses and is NOT a quality measurement. Live runs read EG_ANTHROPIC_API_KEY and "
            "EG_EVAL_DATABASE_URL (an empty database whose name ends in _eval) and refuse unless "
            "docs/evaluation/selection.toml and pricing.toml allow them."
        ),
    )
    commands = root.add_subparsers(dest="command", required=True, metavar="COMMAND")
    run = commands.add_parser("run", help="run a suite", allow_abbrev=False)
    run.add_argument("--suite", choices=("contract", "live"), required=True)
    run.add_argument("--variant", choices=("clean", "injected"), default="clean")
    run.add_argument("--output", type=Path, help="record path (contract suite only)")
    run.add_argument("--model", help="full dated model id (live suite only)")
    run.add_argument("--runs", type=_bounded(MAX_RUNS), help="runs per pair (live suite only)")
    run.add_argument("--budget-usd", type=_budget, help="spend limit (live suite only)")
    run.add_argument(
        "--deadline-minutes",
        type=_bounded(MAX_DEADLINE_MINUTES),
        default=60,
        help="overall deadline (default: 60)",
    )
    show = commands.add_parser("report", help="report run records", allow_abbrev=False)
    show.add_argument("records", nargs="*", type=Path, metavar="RUN")
    show.add_argument("--select", action="store_true", help="apply the selection rule")
    show.add_argument("--format", choices=("md", "readme"), default="md")
    show.add_argument(
        "--write",
        action="store_true",
        help="with --format readme: rewrite the marker blocks in README.md and docs/evaluation.md",
    )
    return root


def _fail(message: str, code: int) -> int:
    print(f"{PROG}: error: {message}", file=sys.stderr)
    return code


def _under(path: Path, directory: Path) -> bool:
    return path.resolve().is_relative_to(directory.resolve())


def _run_options(args: argparse.Namespace, root: Path) -> RunOptions | None:
    if args.suite == "contract":
        if args.output is None or any(
            value is not None for value in (args.model, args.runs, args.budget_usd)
        ):
            return None
        if _under(args.output, root / RUNS_DIRECTORY):
            return None  # contract records are never committed as runs
        return RunOptions(
            "contract", args.variant, args.output, None, 1, None, args.deadline_minutes
        )
    if args.output is not None or args.model is None or args.runs is None:
        return None
    if args.budget_usd is None:
        return None
    return RunOptions(
        "live", args.variant, None, args.model, args.runs, args.budget_usd, args.deadline_minutes
    )


def _report(args: argparse.Namespace, root: Path) -> int:
    named = []
    for path in args.records:
        named.append((path.as_posix(), parse_record(path.read_bytes())))
    if args.select:
        selection = parse_selection((root / SELECTION_FILE).read_bytes())
        chosen = report.select_model(named, selection)
        print(f"selected: {chosen or 'none'}")
        return EXIT_OK
    if args.format == "readme":
        block = report.readme_block(named)
        if args.write:
            for relative in DOCUMENTS_WITH_BLOCK:
                target = root / relative
                text = target.read_text(encoding="utf-8")
                target.write_text(report.replace_block(text, block), encoding="utf-8")
        print(block)
        return EXIT_OK
    sys.stdout.write(report.render_markdown(named))
    return EXIT_OK


def main(argv: Sequence[str] | None = None, *, runner: Runner, root: Path) -> int:
    """Parse ``argv`` and dispatch; ``runner`` executes ``run``, ``root`` is the source tree."""
    args = parser().parse_args(argv)
    if args.command == "run":
        options = _run_options(args, root)
        if options is None:
            parser().print_usage(sys.stderr)
            sys.stderr.write(USAGE_ERROR_MESSAGE)
            return EXIT_USAGE
        return runner(options)
    try:
        return _report(args, root)
    except EvaluationRefusal as refusal:
        return _fail(refusal.message, refusal.exit_code)
    except OSError:
        return _fail("a record or document could not be read or written", EXIT_CONFIGURATION)
    except Exception:
        return _fail("the report failed", EXIT_RUNTIME)
