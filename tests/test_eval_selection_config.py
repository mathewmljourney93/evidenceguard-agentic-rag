"""M7 (ADR-0029): the owner's selection file and the committed $0 cap."""

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from evidenceguard_evaluation.cli import RunOptions
from evidenceguard_evaluation.config import (
    EXIT_BUDGET_PREFLIGHT,
    EvaluationRefusal,
    parse_selection,
    require_live_selection,
    selection_digest,
)
from evidenceguard_worker import evaluation_run

ROOT = Path(__file__).resolve().parents[1]
COMMITTED = ROOT / "docs" / "evaluation" / "selection.toml"
FAKE_KEY = "sk-ant-eg-fake-test-key-not-real-0000"

VALID = b"""
format = "eg-selection-v1"
status = "confirmed"
confirmed_by = "Example Owner"
confirmed_on = "2026-11-20"
[budget]
total_usd_cap = 25.0
[thresholds]
hard_fail = ["provenance_violation", "cross_tenant_leak", "injected_canary"]
claim_support_precision_min = 0.90
coverage_min = 0.80
[candidates]
models = ["model-a-20260101", "model-b-20260101"]
optional = ["model-c-20260101"]
[runs]
clean = 3
injected = 3
[annotation]
mode = "human"
check_fraction = 0.20
[embeddings]
identity = "hash"
"""


def test_the_committed_selection_has_a_zero_total_cap() -> None:
    selection = parse_selection(COMMITTED.read_bytes())
    assert selection.total_usd_cap == Decimal("0.0")
    assert "total_usd_cap = 0.0" in COMMITTED.read_text(encoding="utf-8")
    assert selection.candidates() == ()


class _CountingTransport:
    posts = 0

    def post(self, body: bytes, *, timeout_ms: int) -> Any:
        type(self).posts += 1
        raise AssertionError("no provider call may happen")


def test_a_live_preflight_against_the_committed_selection_exits_4_with_no_provider_call(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("EG_ANTHROPIC_API_KEY", FAKE_KEY)
    monkeypatch.delenv("EG_EVAL_DATABASE_URL", raising=False)
    built: list[object] = []

    def factory(key: Any) -> _CountingTransport:
        built.append(key)
        return _CountingTransport()

    environment = evaluation_run.Environment(transport_factory=factory)
    options = RunOptions("live", "clean", None, "model-a-20260101", 1, Decimal("5"), 60)
    assert evaluation_run.run_suite(options, environment) == EXIT_BUDGET_PREFLIGHT
    assert built == [] and _CountingTransport.posts == 0
    captured = capsys.readouterr()
    assert "spend cap" in captured.err
    assert FAKE_KEY not in captured.out + captured.err


def test_a_proposed_selection_refuses_live_runs() -> None:
    selection = parse_selection(VALID.replace(b'"confirmed"', b'"proposed"', 1))
    with pytest.raises(EvaluationRefusal) as refused:
        require_live_selection(selection, "model-a-20260101")
    assert refused.value.exit_code == 3


def test_a_confirmed_selection_requires_who_and_when() -> None:
    for line in (b'confirmed_by = "Example Owner"\n', b'confirmed_on = "2026-11-20"\n'):
        with pytest.raises(EvaluationRefusal, match="confirmed_by and confirmed_on"):
            parse_selection(VALID.replace(line, b""))


def test_only_candidates_may_run_in_selection_order() -> None:
    selection = parse_selection(VALID)
    assert selection.candidates() == ("model-a-20260101", "model-b-20260101", "model-c-20260101")
    require_live_selection(selection, "model-c-20260101")
    with pytest.raises(EvaluationRefusal, match="not a candidate"):
        require_live_selection(selection, "model-z-20260101")


@pytest.mark.parametrize(
    "change",
    [
        (b"[embeddings]", b"surprise = 1\n[embeddings]"),
        (b"coverage_min = 0.80", b"coverage_min = 0.80\ncoverage_max = 1.0"),
        (b'identity = "hash"', b'identity = "voyage"'),
        (b"total_usd_cap = 25.0", b"total_usd_cap = -1.0"),
        (b'"injected_canary"]', b'"other"]'),
        (b'mode = "human"', b'mode = "llm"'),
    ],
)
def test_unknown_keys_and_invalid_values_are_refused(change: tuple[bytes, bytes]) -> None:
    with pytest.raises(EvaluationRefusal) as refused:
        parse_selection(VALID.replace(*change))
    assert refused.value.exit_code == 3
    assert b"voyage" not in str(refused.value).encode() and "llm" not in str(refused.value)


def test_the_digest_is_stable_and_bound_to_the_bytes() -> None:
    assert parse_selection(VALID).digest == selection_digest(VALID)
    assert parse_selection(VALID).digest == parse_selection(VALID).digest
    assert parse_selection(VALID + b"\n").digest != parse_selection(VALID).digest
