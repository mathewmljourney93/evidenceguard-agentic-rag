"""Deterministic reports over run records, model selection and the docs/evaluation.md block.

- ``render_markdown``: one table per record (identity, checks and metrics); the same records
  always give the same bytes. Claim-support precision prints "not measured: no labels" while a
  run has no committed labels.
- ``select_model``: refuses records made under different selection or pricing digests, drops
  every model with a hard failure, then applies the thresholds in candidate order and returns
  the first model that meets all of them (the cheapest, because candidates are listed cheapest
  first), or ``None``.
- ``readme_block``: the text between ``<!-- eg-eval:begin -->`` and ``<!-- eg-eval:end -->`` in
  docs/evaluation.md, generated only from committed live runs; with none it reads "No committed
  live runs yet." README.md holds no block, only a pointer to docs/evaluation.md (AGENTS.md:
  status never lives in the README).
"""

from collections.abc import Mapping, Sequence
from decimal import Decimal
from fractions import Fraction
from typing import Any

from evidenceguard_evaluation.config import Selection, refuse

BEGIN = "<!-- eg-eval:begin -->"
END = "<!-- eg-eval:end -->"
NO_RUNS = "No committed live runs yet."
NOT_MEASURED = "not measured: no labels"

Named = tuple[str, Mapping[str, Any]]


def _fraction(value: Mapping[str, int] | None) -> Fraction | None:
    if value is None:
        return None
    return Fraction(value["numerator"], value["denominator"])


def _show(value: Mapping[str, int] | None) -> str:
    fraction = _fraction(value)
    if fraction is None:
        return "n/a"
    return f"{fraction.numerator}/{fraction.denominator}"


def render_markdown(records: Sequence[Named]) -> str:
    """A deterministic Markdown report, records ordered by their path."""
    lines = ["# EvidenceGuard evaluation report", ""]
    if not records:
        lines.append("No run records were given.")
        return "\n".join(lines) + "\n"
    for path, record in sorted(records, key=lambda item: item[0]):
        metrics = record["metrics"]
        checks = record["checks"]
        isolation = checks["isolation"]
        precision = metrics["claim_support_precision"]
        lines += [
            f"## {path}",
            "",
            f"- Stamp: {record['stamp']}",
            f"- Suite: {record['suite']} ({record['variant']}), status {record['status']}",
            f"- Model requested: {record['model_requested']}; used: "
            + (", ".join(record["models_used"]) or "none"),
            f"- Embeddings: {record['embeddings']}",
            f"- Git: {record['git_sha']}; record sha256: {record['record_sha256']}",
            "",
            "| Measure | Value |",
            "|---|---|",
            f"| Hard failures | {', '.join(record['hard_failures']) or 'none'} |",
            f"| Contract failures | {', '.join(record['contract_failures']) or 'none'} |",
            f"| Provenance violations | {checks['provenance_violations']} |",
            "| Isolation | "
            + (
                "pass"
                if isolation["foreign_review_hidden"]
                and isolation["foreign_output_hidden"]
                and not isolation["foreign_chunks"]
                and not isolation["tenant_canaries"]
                else "FAIL"
            )
            + " |",
            f"| Injected canary hits | {checks['injected_canary']} |",
            f"| Recall@5 / Recall@8 | {_show(metrics['recall_at_5'])} / "
            f"{_show(metrics['recall_at_8'])} |",
            "| Claim-support precision | "
            + (NOT_MEASURED if precision is None else _show(precision))
            + " |",
            f"| Coverage | {_show(metrics['coverage'])} |",
            f"| Correct / false abstention | {_show(metrics['abstention']['correct'])} / "
            f"{_show(metrics['abstention']['false'])} |",
            f"| Conflicts detected / false | {_show(metrics['conflicts']['detected'])} / "
            f"{_show(metrics['conflicts']['false'])} |",
            f"| Refusals | {_counts(record['refusals'])} |",
            f"| Latency n (min, max ms) | {metrics['latency']['n']} "
            f"({metrics['latency']['min']}, {metrics['latency']['max']}) |",
            "",
        ]
    return "\n".join(lines).rstrip("\n") + "\n"


def _counts(values: Mapping[str, int]) -> str:
    return ", ".join(f"{key} {value}" for key, value in sorted(values.items())) or "none"


def live_records(records: Sequence[Named]) -> list[Named]:
    return [item for item in records if item[1]["suite"] == "live"]


def _meets(record: Mapping[str, Any], selection: Selection) -> bool:
    metrics = record["metrics"]
    precision = _fraction(metrics["claim_support_precision"])
    coverage = _fraction(metrics["coverage"])
    if precision is None or coverage is None:
        return False
    thresholds = selection.thresholds
    return (
        Decimal(precision.numerator) / Decimal(precision.denominator)
        >= (thresholds.claim_support_precision_min)
        and Decimal(coverage.numerator) / Decimal(coverage.denominator) >= thresholds.coverage_min
    )


def select_model(records: Sequence[Named], selection: Selection) -> str | None:
    """The first candidate (cheapest first) whose live runs all pass (module docstring)."""
    live = live_records(records)
    if len({r["digests"]["selection"] for _, r in live}) > 1:
        raise refuse("the runs were made under different selection.toml versions")
    if len({r["digests"]["pricing"] for _, r in live}) > 1:
        raise refuse("the runs were made under different pricing.toml versions")
    for model in selection.candidates():
        runs = [r for _, r in live if r["model_requested"] == model]
        if not runs or any(r["hard_failures"] or r["status"] != "completed" for r in runs):
            continue
        if all(_meets(r, selection) for r in runs if r["variant"] == "clean"):
            return model
    return None


def readme_block(records: Sequence[Named]) -> str:
    """The generated block, markers included (module docstring)."""
    live = sorted(live_records(records), key=lambda item: item[0])
    lines = [BEGIN]
    if not live:
        lines.append(NO_RUNS)
    else:
        lines += [
            "Generated by `eg-eval report --format readme` from committed live runs only.",
            "",
            "| Run file | Model | Variant | Status | Claim-support precision | Coverage |",
            "|---|---|---|---|---|---|",
        ]
        for path, record in live:
            precision = record["metrics"]["claim_support_precision"]
            lines.append(
                f"| `{path}` | {record['model_requested']} | {record['variant']} | "
                f"{record['status']} | "
                f"{NOT_MEASURED if precision is None else _show(precision)} | "
                f"{_show(record['metrics']['coverage'])} |"
            )
    lines.append(END)
    return "\n".join(lines)


def replace_block(text: str, block: str) -> str:
    """``text`` with its marker block replaced by ``block`` (exactly one block required)."""
    if text.count(BEGIN) != 1 or text.count(END) != 1 or text.index(BEGIN) > text.index(END):
        raise refuse("the file must contain exactly one eg-eval marker block")
    start = text.index(BEGIN)
    end = text.index(END) + len(END)
    return text[:start] + block + text[end:]


def current_block(text: str) -> str:
    if text.count(BEGIN) != 1 or text.count(END) != 1:
        raise refuse("the file must contain exactly one eg-eval marker block")
    return text[text.index(BEGIN) : text.index(END) + len(END)]
