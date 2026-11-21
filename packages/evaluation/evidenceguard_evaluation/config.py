"""The owner's selection file ``docs/evaluation/selection.toml`` (format ``eg-selection-v1``).

It holds the decisions that must exist before any live run (D10): the status and who confirmed
it, the total spend cap, the thresholds, the candidate models (full dated ids, cheapest first),
the number of runs, the annotation mode and the embedding identity. Unknown keys are refused, so
a typo can never silently relax a decision. Parsing never echoes a value: every refusal is an
``EvaluationRefusal`` with a fixed message.

``selection_digest`` is the SHA-256 of the file bytes, recorded in every run record so that a
report can refuse runs made under different decisions.
"""

import hashlib
import re
import tomllib
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

SELECTION_FORMAT = "eg-selection-v1"
HARD_FAIL_NAMES = frozenset({"provenance_violation", "cross_tenant_leak", "injected_canary"})
STATUSES = frozenset({"proposed", "confirmed"})
ANNOTATION_MODES = frozenset({"human", "model"})
MAX_SELECTION_BYTES = 64 * 1024
MAX_RUNS = 20
MODEL_ID = re.compile(r"^[a-z0-9][a-z0-9.-]{0,63}$")

EXIT_OK = 0
EXIT_RUNTIME = 1
EXIT_USAGE = 2
EXIT_CONFIGURATION = 3
EXIT_BUDGET_PREFLIGHT = 4
EXIT_HARD_FAILURE = 5
EXIT_STOPPED = 6


class EvaluationRefusal(Exception):
    """A fixed refusal with the exit code it maps to. The message never contains a value read
    from a file, the environment or the command line."""

    def __init__(self, message: str, exit_code: int = EXIT_CONFIGURATION) -> None:
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code


def refuse(message: str, exit_code: int = EXIT_CONFIGURATION) -> EvaluationRefusal:
    return EvaluationRefusal(message, exit_code)


@dataclass(frozen=True)
class Thresholds:
    hard_fail: tuple[str, ...]
    claim_support_precision_min: Decimal
    coverage_min: Decimal


@dataclass(frozen=True)
class Selection:
    status: str
    confirmed_by: str | None
    confirmed_on: date | None
    total_usd_cap: Decimal
    thresholds: Thresholds
    models: tuple[str, ...]
    optional: tuple[str, ...]
    clean_runs: int
    injected_runs: int
    annotation_mode: str
    check_fraction: Decimal
    embeddings: str
    digest: str

    @property
    def confirmed(self) -> bool:
        return self.status == "confirmed"

    def candidates(self) -> tuple[str, ...]:
        """Every candidate in selection order: required models first, then optional ones."""
        return self.models + self.optional


_TOP = {"format", "status", "confirmed_by", "confirmed_on", "budget", "thresholds"}
_TOP |= {"candidates", "runs", "annotation", "embeddings"}
_REQUIRED_TOP = _TOP - {"confirmed_by", "confirmed_on"}


def _table(value: object, allowed: set[str], required: set[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise refuse(f"selection.toml: [{name}] must be a table")
    keys = set(value)
    if keys - allowed:
        raise refuse(f"selection.toml: [{name}] has an unknown key")
    if required - keys:
        raise refuse(f"selection.toml: [{name}] is missing a required key")
    return value


def _decimal(value: object, name: str, *, low: Decimal, high: Decimal | None = None) -> Decimal:
    if type(value) not in (int, float):
        raise refuse(f"selection.toml: {name} must be a number")
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        raise refuse(f"selection.toml: {name} must be a number") from None
    if not number.is_finite() or number < low or (high is not None and number > high):
        raise refuse(f"selection.toml: {name} is out of range")
    return number


def _count(value: object, name: str) -> int:
    if type(value) is not int or not 0 <= value <= MAX_RUNS:
        raise refuse(f"selection.toml: {name} is out of range")
    return value


def _models(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise refuse(f"selection.toml: {name} must be a list")
    models: list[str] = []
    for item in value:
        if type(item) is not str or MODEL_ID.fullmatch(item) is None:
            raise refuse(f"selection.toml: {name} has an invalid model id")
        models.append(item)
    if len(set(models)) != len(models):
        raise refuse(f"selection.toml: {name} repeats a model id")
    return tuple(models)


def parse_selection(data: bytes) -> Selection:
    """Parse and validate ``selection.toml`` bytes, or raise ``EvaluationRefusal`` (exit 3)."""
    if len(data) > MAX_SELECTION_BYTES:
        raise refuse("selection.toml is too large")
    try:
        document = tomllib.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError):
        raise refuse("selection.toml is not valid TOML") from None
    top = _table(document, _TOP, _REQUIRED_TOP, "top level")
    if top["format"] != SELECTION_FORMAT:
        raise refuse("selection.toml: format must be eg-selection-v1")
    status = top["status"]
    if status not in STATUSES:
        raise refuse("selection.toml: status must be proposed or confirmed")
    confirmed_by = top.get("confirmed_by")
    confirmed_on = top.get("confirmed_on")
    if confirmed_by is not None and (type(confirmed_by) is not str or not confirmed_by.strip()):
        raise refuse("selection.toml: confirmed_by must be a non-empty string")
    if confirmed_on is not None:
        if type(confirmed_on) is str:
            try:
                confirmed_on = date.fromisoformat(confirmed_on)
            except ValueError:
                raise refuse("selection.toml: confirmed_on must be an ISO date") from None
        elif type(confirmed_on) is not date:
            raise refuse("selection.toml: confirmed_on must be an ISO date")
    if status == "confirmed" and (confirmed_by is None or confirmed_on is None):
        raise refuse("selection.toml: a confirmed selection needs confirmed_by and confirmed_on")
    budget = _table(top["budget"], {"total_usd_cap"}, {"total_usd_cap"}, "budget")
    thresholds = _table(
        top["thresholds"],
        {"hard_fail", "claim_support_precision_min", "coverage_min"},
        {"hard_fail", "claim_support_precision_min", "coverage_min"},
        "thresholds",
    )
    hard_fail = thresholds["hard_fail"]
    if (
        not isinstance(hard_fail, list)
        or not all(type(name) is str for name in hard_fail)
        or set(hard_fail) != HARD_FAIL_NAMES
        or len(hard_fail) != len(HARD_FAIL_NAMES)
    ):
        raise refuse("selection.toml: hard_fail must list exactly the three hard failures")
    candidates = _table(top["candidates"], {"models", "optional"}, {"models", "optional"}, "c")
    models = _models(candidates["models"], "candidates.models")
    optional = _models(candidates["optional"], "candidates.optional")
    if set(models) & set(optional):
        raise refuse("selection.toml: a model is both required and optional")
    runs = _table(top["runs"], {"clean", "injected"}, {"clean", "injected"}, "runs")
    annotation = _table(
        top["annotation"], {"mode", "check_fraction"}, {"mode", "check_fraction"}, "annotation"
    )
    if annotation["mode"] not in ANNOTATION_MODES:
        raise refuse("selection.toml: annotation.mode must be human or model")
    embeddings = _table(top["embeddings"], {"identity"}, {"identity"}, "embeddings")
    if embeddings["identity"] != "hash":
        raise refuse("selection.toml: embeddings.identity must be hash")
    one = Decimal(1)
    return Selection(
        status=status,
        confirmed_by=confirmed_by,
        confirmed_on=confirmed_on,
        total_usd_cap=_decimal(budget["total_usd_cap"], "total_usd_cap", low=Decimal(0)),
        thresholds=Thresholds(
            hard_fail=tuple(sorted(hard_fail)),
            claim_support_precision_min=_decimal(
                thresholds["claim_support_precision_min"],
                "claim_support_precision_min",
                low=Decimal(0),
                high=one,
            ),
            coverage_min=_decimal(
                thresholds["coverage_min"], "coverage_min", low=Decimal(0), high=one
            ),
        ),
        models=models,
        optional=optional,
        clean_runs=_count(runs["clean"], "runs.clean"),
        injected_runs=_count(runs["injected"], "runs.injected"),
        annotation_mode=annotation["mode"],
        check_fraction=_decimal(
            annotation["check_fraction"], "check_fraction", low=Decimal(0), high=one
        ),
        embeddings="hash",
        digest=selection_digest(data),
    )


def selection_digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require_live_selection(selection: Selection, model: str) -> None:
    """The live-run conditions on the selection: confirmed, and ``model`` a candidate."""
    if not selection.confirmed:
        raise refuse("selection.toml is not confirmed; live runs need a confirmed selection")
    if model not in selection.candidates():
        raise refuse("the model is not a candidate in selection.toml")
