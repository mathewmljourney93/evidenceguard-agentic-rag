"""M7 (ADR-0029): deterministic reports, the selection rule and the generated README block."""

from pathlib import Path
from typing import Any

import pytest

from evidenceguard_evaluation import report
from evidenceguard_evaluation.config import EvaluationRefusal, parse_selection
from evidenceguard_evaluation.records import RunContext, build_record, parse_record, sealed

ROOT = Path(__file__).resolve().parents[1]
SELECTION = (ROOT / "docs" / "evaluation" / "selection.toml").read_text(encoding="utf-8")


def _selection() -> Any:
    text = SELECTION.replace("total_usd_cap = 0.0", "total_usd_cap = 50.0")
    text = text.replace("models = []", 'models = ["model-a-20260101", "model-b-20260101"]')
    return parse_selection(text.encode("utf-8"))


def _record(
    model: str,
    *,
    precision: tuple[int, int] | None = (19, 20),
    coverage: tuple[int, int] = (9, 10),
    hard: tuple[str, ...] = (),
    selection_digest: str = "s" * 64,
    pricing_digest: str = "p" * 64,
) -> dict[str, Any]:
    context = RunContext(
        run_id=f"run-{model}",
        suite="live",
        variant="clean",
        created_at="2026-11-20T00:00:00Z",
        git_sha="0" * 40,
        corpus_digest="c" * 64,
        template_digest="t" * 64,
        prompt_digests={"verifier": "v" * 64},
        model_requested=model,
        runs=1,
        anchors={},
        selection_digest=selection_digest,
        pricing_digest=pricing_digest,
        pricing_as_of="2026-11-01",
        pricing_source_url="https://example.invalid/pricing",
    )
    record = build_record(context, [])
    metrics = dict(record["metrics"])
    metrics["claim_support_precision"] = (
        None if precision is None else {"numerator": precision[0], "denominator": precision[1]}
    )
    metrics["coverage"] = {"numerator": coverage[0], "denominator": coverage[1]}
    record["metrics"] = metrics
    record["hard_failures"] = list(hard)
    record["status"] = "hard_failure" if hard else "completed"
    return sealed(record)


def test_the_markdown_report_is_deterministic() -> None:
    named = [("b.json", _record("model-b-20260101")), ("a.json", _record("model-a-20260101"))]
    first = report.render_markdown(named)
    assert first == report.render_markdown(list(reversed(named)))
    assert first.index("## a.json") < first.index("## b.json")
    unlabelled = _record("model-a-20260101", precision=None)
    assert report.NOT_MEASURED in report.render_markdown([("x.json", unlabelled)])


def test_the_cheapest_passing_model_is_selected() -> None:
    named = [
        ("a.json", _record("model-a-20260101", precision=(17, 20))),  # below 0.90
        ("b.json", _record("model-b-20260101")),
    ]
    assert report.select_model(named, _selection()) == "model-b-20260101"
    named.append(("a2.json", _record("model-a-20260101")))
    assert report.select_model(named[1:], _selection()) == "model-a-20260101"


def test_a_hard_failure_excludes_a_model_and_unlabelled_runs_select_nothing() -> None:
    named = [
        ("a.json", _record("model-a-20260101", hard=("injected_canary",))),
        ("b.json", _record("model-b-20260101", precision=None)),
    ]
    assert report.select_model(named, _selection()) is None


def test_mixed_selection_or_pricing_digests_are_refused() -> None:
    for other in (
        _record("model-b-20260101", selection_digest="x" * 64),
        _record("model-b-20260101", pricing_digest="y" * 64),
    ):
        named = [("a.json", _record("model-a-20260101")), ("b.json", other)]
        with pytest.raises(EvaluationRefusal, match="different"):
            report.select_model(named, _selection())


def _committed() -> list[tuple[str, dict[str, Any]]]:
    directory = ROOT / "docs" / "evaluation" / "runs"
    if not directory.is_dir():
        return []
    return [
        (path.relative_to(ROOT).as_posix(), parse_record(path.read_bytes()))
        for path in sorted(directory.glob("*.json"))
    ]


@pytest.mark.parametrize("document", ["README.md", "docs/evaluation.md"])
def test_the_readme_and_docs_blocks_equal_their_regeneration(document: str) -> None:
    expected = report.readme_block(_committed())
    text = (ROOT / document).read_text(encoding="utf-8")
    assert report.current_block(text) == expected
    if not _committed():
        assert report.NO_RUNS in expected


def test_the_block_lists_live_runs_and_never_contract_runs() -> None:
    contract = _record("model-a-20260101")
    contract = sealed({**contract, "suite": "contract"})
    assert report.readme_block([("c.json", contract)]) == report.readme_block([])
    block = report.readme_block([("docs/evaluation/runs/a.json", _record("model-a-20260101"))])
    assert "`docs/evaluation/runs/a.json`" in block and "19/20" in block
    replaced = report.replace_block(f"x\n{report.BEGIN}\nold\n{report.END}\ny\n", block)
    assert replaced == f"x\n{block}\ny\n"
    with pytest.raises(EvaluationRefusal):
        report.replace_block("no markers", block)
