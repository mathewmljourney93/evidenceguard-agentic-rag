"""M7 (ADR-0029): run records are allowlisted, canonical and carry no secret or raw text."""

import json
import logging
import shutil
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from evidenceguard_agents.anthropic import AnthropicProvider, AnthropicResponse
from evidenceguard_domain.model_calls import ModelPurpose, PromptRef, StructuredRequest
from evidenceguard_evaluation.budget import BudgetGuard
from evidenceguard_evaluation.cli import RunOptions
from evidenceguard_evaluation.config import EvaluationRefusal
from evidenceguard_evaluation.records import (
    RECORD,
    ObservedCall,
    ObservedCitation,
    ObservedClaim,
    ObservedQuestion,
    ObservedReview,
    RetrievedItem,
    RunContext,
    build_record,
    canonical_json,
    parse_record,
    record_bytes,
    validate_record,
)
from evidenceguard_worker import evaluation_run

ROOT = Path(__file__).resolve().parents[1]
MODEL = "model-a-20260101"
CANARY_KEY = "sk-ant-eg-canary-" + "0123456789abcdef" * 3
RATIONALE = "A rationale that must never reach a record."


def _context(**changes: Any) -> RunContext:
    values: dict[str, Any] = {
        "run_id": "run-1",
        "suite": "live",
        "variant": "clean",
        "created_at": "2026-11-20T00:00:00Z",
        "git_sha": "0" * 40,
        "corpus_digest": "c" * 64,
        "template_digest": "t" * 64,
        "prompt_digests": {"verifier": "v" * 64, "risk_analyst": "a" * 64},
        "model_requested": MODEL,
        "runs": 1,
        "anchors": {"halverson-freight/lumenvale-cloud/doc@r1#a": "retained for ninety days"},
    }
    values.update(changes)
    return RunContext(**values)


def _review(**changes: Any) -> ObservedReview:
    item = RetrievedItem("c1", "lumenvale-cloud/doc@r1#c0", "Data is retained for ninety days.")
    question = ObservedQuestion(
        question_id="RET-01",
        expected_status="vendor_claim",
        status="vendor_claim",
        verification="verified",
        unresolved_reason=None,
        trap=None,
        retrieved=(item,),
        claims=(
            ObservedClaim("Ninety days.", (ObservedCitation("c1", "retained for ninety days"),)),
        ),
        finding_citations=(),
        finding_count=0,
        free_text=(("rationale", RATIONALE),),
        gold_refs=frozenset({"lumenvale-cloud/doc@r1#c0"}),
    )
    values: dict[str, Any] = {
        "run": 1,
        "phase": "live",
        "tenant": "halverson-freight",
        "vendor": "lumenvale-cloud",
        "configuration_sha256": "f" * 64,
        "review_status": "completed",
        "questions": (question,),
        "calls": (ObservedCall("verification", "RET-01", 1, "completed", None, MODEL, 10, 5, 123),),
        "foreign_review_hidden": True,
        "foreign_output_hidden": True,
        "foreign_chunks": 0,
        "output_text": "{}",
    }
    values.update(changes)
    return ObservedReview(**values)


def test_a_record_round_trips_canonically() -> None:
    record = build_record(_context(), [_review()])
    data = record_bytes(record)
    assert data == canonical_json(record) + b"\n"
    assert parse_record(data) == record
    claim = record["reviews"][0]["questions"][0]["claims"][0]
    assert claim["citations"][0] == {
        "ref": "lumenvale-cloud/doc@r1",
        "anchor": "halverson-freight/lumenvale-cloud/doc@r1#a",
        "quote": "retained for ninety days",
    }
    assert record["metrics"]["recall_at_5"] == {"numerator": 1, "denominator": 1}


def test_unknown_or_missing_fields_are_rejected() -> None:
    record = build_record(_context(), [_review()])
    with pytest.raises(EvaluationRefusal, match="unknown or missing"):
        validate_record({**record, "api_key": "x"})
    nested = json.loads(json.dumps(record))
    nested["reviews"][0]["questions"][0]["rationale"] = RATIONALE
    with pytest.raises(EvaluationRefusal):
        validate_record(nested)
    tampered = json.loads(json.dumps(record))
    tampered["status"] = "completed" if record["status"] != "completed" else "hard_failure"
    with pytest.raises(EvaluationRefusal, match="digests"):
        parse_record(canonical_json(tampered))


def _keys(spec: Any) -> set[str]:
    if isinstance(spec, dict):
        return set(spec) | {k for value in spec.values() for k in _keys(value)}
    if isinstance(spec, tuple):
        return _keys(spec[1])
    return set()


def test_the_schema_has_no_field_for_rationales_raw_text_keys_or_errors() -> None:
    names = _keys(RECORD)
    for forbidden in ("rationale", "response", "header", "api_key", "secret", "exception", "error"):
        assert not any(forbidden in name for name in names), forbidden
    record = build_record(_context(), [_review()])
    assert RATIONALE not in record_bytes(record).decode("ascii")


def test_two_records_differing_only_in_timings_share_the_deterministic_digest() -> None:
    first = build_record(_context(), [_review()])
    slower = _review(
        calls=(ObservedCall("verification", "RET-01", 1, "completed", None, MODEL, 10, 5, 999),)
    )
    second = build_record(_context(run_id="run-2", created_at="2026-11-21T00:00:00Z"), [slower])
    assert first["deterministic_sha256"] == second["deterministic_sha256"]
    assert first["record_sha256"] != second["record_sha256"]


def test_hard_failures_are_recomputed_from_stored_sets() -> None:
    leak = _review(
        foreign_output_hidden=False,
        output_text="see lv-tb-canary-aes",
        tenant_canaries=("LV-TB-CANARY-AES",),
    )
    record = build_record(_context(), [leak])
    assert record["hard_failures"] == ["cross_tenant_leak"]
    assert record["checks"]["isolation"]["tenant_canaries"] == 1
    bad = _review()
    question = bad.questions[0]
    unauthorized = ObservedQuestion(
        **{**question.__dict__, "claims": (ObservedClaim("x", (ObservedCitation("c9", "q"),)),)}
    )
    record = build_record(_context(), [_review(questions=(unauthorized,))])
    assert record["hard_failures"] == ["provenance_violation"]
    assert record["reviews"][0]["questions"][0]["claims"][0]["citations"][0]["ref"] == (
        "unauthorized"
    )


# --- the provider key never reaches a record, a log or the terminal ------------------------------


class _FakeTransport:
    def __init__(self, key: Any) -> None:
        self.key = key
        self.posts = 0

    def post(self, body: bytes, *, timeout_ms: int) -> AnthropicResponse:
        self.posts += 1
        document = {
            "id": "msg_synthetic_01",
            "type": "message",
            "role": "assistant",
            "model": MODEL,
            "content": [{"type": "text", "text": "{}"}],
            "stop_reason": "refusal",
            "stop_sequence": None,
            "usage": {"input_tokens": 12, "output_tokens": 3},
        }
        return AnthropicResponse(200, json.dumps(document).encode("utf-8"))


def _tree(tmp_path: Path) -> Path:
    shutil.copytree(ROOT / "sample_data", tmp_path / "sample_data")
    evaluation = tmp_path / "docs" / "evaluation"
    evaluation.mkdir(parents=True)
    selection = (ROOT / "docs" / "evaluation" / "selection.toml").read_text(encoding="utf-8")
    selection = selection.replace("total_usd_cap = 0.0", "total_usd_cap = 1000.0")
    selection = selection.replace("models = []", f'models = ["{MODEL}"]')
    (evaluation / "selection.toml").write_text(selection, encoding="utf-8")
    (evaluation / "pricing.toml").write_text(
        'as_of = "2026-11-15"\nsource_url = "https://example.invalid/pricing"\n'
        f'[models."{MODEL}"]\ninput_usd_per_mtok = 1\noutput_usd_per_mtok = 5\n',
        encoding="utf-8",
    )
    return tmp_path


def test_canary_key_never_appears_in_record_labels_or_logs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The live path up to the record, with a fake transport: preflight reads the key, the
    adapter and budget guard call the fake, and the record is written. No labels exist at v0.1
    (annotation is deferred), so the record is the only artefact."""
    caplog.set_level(logging.DEBUG)
    monkeypatch.setenv("EG_ANTHROPIC_API_KEY", CANARY_KEY)
    root = _tree(tmp_path)
    options = RunOptions("live", "clean", None, MODEL, 1, Decimal("100"), 60)
    setup = evaluation_run.live_preflight(
        options, root=root, git=lambda arguments: "", today=date(2026, 11, 20)
    )
    assert setup.key.get_secret_value() == CANARY_KEY
    transport = _FakeTransport(setup.key)
    guard = BudgetGuard(AnthropicProvider(transport), price=setup.price, budget_usd=Decimal(100))
    request = StructuredRequest(
        purpose=ModelPurpose.VERIFIER,
        prompt=PromptRef(prompt_id="verifier", version=1, sha256="1" * 64),
        model_id=MODEL,
        question_id="RET-01",
        system_text="system",
        user_text="user",
        max_output_tokens=100,
    )
    response = guard.generate(request)
    assert transport.posts == 1 and response.usage.input_tokens == 12
    record = build_record(
        _context(
            selection_digest=setup.selection.digest,
            pricing_digest=setup.pricing.digest,
            pricing_as_of=setup.pricing.as_of.isoformat(),
            pricing_source_url=setup.pricing.source_url,
        ),
        [_review()],
        budget={
            "budget_usd": "100",
            "spent_usd": str(guard.totals.spent_usd),
            "dispatched_calls": guard.totals.dispatched_calls,
            "refused_calls": 0,
            "stopped": False,
        },
    )
    target = root / "docs" / "evaluation" / "runs" / "r.json"
    target.parent.mkdir(parents=True)
    target.write_bytes(record_bytes(record))
    captured = capsys.readouterr()
    surfaces = [target.read_text(encoding="ascii"), captured.out, captured.err, caplog.text]
    surfaces += [repr(setup), repr(guard), repr(transport.key)]
    for surface in surfaces:
        assert CANARY_KEY not in surface
        assert "sk-ant-eg-canary" not in surface


def test_a_dirty_tree_is_refused() -> None:
    with pytest.raises(EvaluationRefusal) as refused:
        evaluation_run.require_clean_tree(lambda arguments: " M README.md\n")
    assert refused.value.exit_code == 3
    with pytest.raises(EvaluationRefusal):
        evaluation_run.require_clean_tree(lambda arguments: None)
