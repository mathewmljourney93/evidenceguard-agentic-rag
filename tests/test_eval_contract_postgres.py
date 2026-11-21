"""M7 (ADR-0029): the ``eg-eval`` contract suite and the live path over PostgreSQL.

Skipped without ``EG_TEST_DATABASE_URL`` (required in CI). Every run uses the guarded disposable
test database, reset to an empty ``public`` schema first, through the runner's test hook (the
command itself only accepts ``_eval`` databases and never drops anything). The scripted fake
provides every model response; the live-path case uses a fake transport and a fake key.
"""

import json
import logging
import shutil
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import URL
from sqlalchemy.pool import NullPool

from evidenceguard_agents.anthropic import AnthropicResponse
from evidenceguard_evaluation.cli import RunOptions
from evidenceguard_worker import evaluation_run

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[1]
MODEL = "model-a-20260101"
CANARY_KEY = "sk-ant-eg-canary-" + "fedcba9876543210" * 3


def _reset(url: URL) -> None:
    engine = create_engine(url, poolclass=NullPool, hide_parameters=True)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("DROP SCHEMA public CASCADE")
            connection.exec_driver_sql("CREATE SCHEMA public")
    finally:
        engine.dispose()


@pytest.fixture
def fresh(test_database_url: URL) -> Iterator[URL]:
    _reset(test_database_url)
    yield test_database_url
    _reset(test_database_url)


def _contract(
    url: URL, output: Path, variant: str = "clean", **hooks: Any
) -> tuple[int, dict[str, Any]]:
    _reset(url)
    environment = evaluation_run.Environment(database_url=url, **hooks)
    options = RunOptions("contract", variant, output, None, 1, None, 30)
    code = evaluation_run.run_suite(options, environment)
    return code, json.loads(output.read_text(encoding="ascii"))


def _assert_contract_holds(record: dict[str, Any]) -> None:
    assert record["status"] == "completed"
    assert record["hard_failures"] == [] and record["contract_failures"] == []
    assert record["stamp"] == "NOT a quality measurement of Claude or semantic retrieval"
    checks = record["checks"]
    assert checks["provenance_violations"] == 0 and checks["injected_canary"] == 0
    assert checks["isolation"] == {
        "foreign_review_hidden": True,
        "foreign_output_hidden": True,
        "foreign_chunks": 0,
        "tenant_canaries": 0,
    }
    assert checks["retrieval_deterministic"] and checks["traps_unresolved"]
    assert checks["refusal_phase_unresolved"]
    reviews = record["reviews"]
    assert [(r["phase"], r["tenant"], r["vendor"]) for r in reviews] == [
        (phase, tenant, vendor)
        for tenant, vendor in (
            ("halverson-freight", "ferrowick-payroll"),
            ("halverson-freight", "lumenvale-cloud"),
            ("marisol-clinics", "lumenvale-cloud"),
        )
        for phase in ("refusal", "scripted")
    ]
    traps = {
        q["trap"]: (q["verification"], q["unresolved_reason"], q["claims"])
        for r in reviews
        for q in r["questions"]
        if q["trap"] is not None
    }
    assert traps == {
        "foreign_citation": ("unresolved", "citation_rejected", []),
        "quote_mismatch": ("unresolved", "citation_rejected", []),
        "wrong_model": ("unresolved", "model_mismatch", []),
        "invalid_json": ("unresolved", "invalid_output", []),
    }
    for review in reviews:
        assert review["review_status"] == "completed"
        if review["phase"] == "refusal":
            assert all(q["verification"] == "unresolved" for q in review["questions"])
            assert all(q["finding_count"] == 0 for q in review["questions"])


def test_clean_and_injected_contract_suites_pass_and_repeat_deterministically(
    fresh: URL, tmp_path: Path
) -> None:
    code, first = _contract(fresh, tmp_path / "first.json")
    assert code == 0
    _assert_contract_holds(first)
    code, second = _contract(fresh, tmp_path / "second.json")
    assert code == 0
    assert second["deterministic_sha256"] == first["deterministic_sha256"]
    assert second["run_id"] != first["run_id"]
    code, injected = _contract(fresh, tmp_path / "injected.json", variant="injected")
    assert code == 0
    _assert_contract_holds(injected)
    assert injected["variant"] == "injected"
    assert injected["digests"]["corpus"] != first["digests"]["corpus"]


def test_a_scripted_canary_in_a_rationale_is_reported_as_injected_canary(
    fresh: URL, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    marker = "SYSTEM NOTE TO AUTOMATED REVIEWERS"
    code, record = _contract(fresh, tmp_path / "canary.json", rationale_extra=marker.lower())
    assert code == 5
    assert record["status"] == "hard_failure"
    assert record["hard_failures"] == ["injected_canary"]
    assert record["checks"]["injected_canary"] >= 1
    assert marker.lower() not in (tmp_path / "canary.json").read_text(encoding="ascii")
    assert "status: hard_failure" in capsys.readouterr().out


def test_a_non_empty_database_is_refused(
    migrated: Engine, test_database_url: URL, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    environment = evaluation_run.Environment(database_url=test_database_url)
    options = RunOptions("contract", "clean", tmp_path / "c.json", None, 1, None, 30)
    assert evaluation_run.run_suite(options, environment) == 3
    assert "database is not empty" in capsys.readouterr().err
    assert not (tmp_path / "c.json").exists()
    with migrated.connect() as connection:  # nothing was dropped
        assert connection.exec_driver_sql("SELECT count(*) FROM tenants").scalar_one() == 0


class _RefusingTransport:
    """A fake Anthropic transport: every call is a refusal with small usage."""

    def __init__(self, key: Any) -> None:
        self.key = key
        self.posts = 0

    def post(self, body: bytes, *, timeout_ms: int) -> AnthropicResponse:
        self.posts += 1
        assert CANARY_KEY.encode() not in body
        document = {
            "id": "msg_synthetic_01",
            "type": "message",
            "role": "assistant",
            "model": MODEL,
            "content": [{"type": "text", "text": "{}"}],
            "stop_reason": "refusal",
            "stop_sequence": None,
            "usage": {"input_tokens": 1200, "output_tokens": 3},
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


def test_the_live_path_with_a_fake_transport_writes_a_record_without_the_key(
    fresh: URL,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    caplog.set_level(logging.DEBUG)
    monkeypatch.setenv("EG_ANTHROPIC_API_KEY", CANARY_KEY)
    transports: list[_RefusingTransport] = []

    def factory(key: Any) -> _RefusingTransport:
        transports.append(_RefusingTransport(key))
        return transports[-1]

    root = _tree(tmp_path / "tree")
    environment = evaluation_run.Environment(
        root=root, database_url=fresh, git=lambda arguments: "", transport_factory=factory
    )
    options = RunOptions("live", "clean", None, MODEL, 1, Decimal("100"), 30)
    assert evaluation_run.run_suite(options, environment) == 0
    (path,) = sorted((root / "docs" / "evaluation" / "runs").glob("*.json"))
    assert path.name.endswith(f"-{MODEL}-clean-r1.json")
    record = json.loads(path.read_text(encoding="ascii"))
    assert record["suite"] == "live" and record["status"] == "completed"
    assert record["models_used"] == [MODEL]
    assert record["pricing"] == {
        "as_of": "2026-11-15",
        "source_url": "https://example.invalid/pricing",
    }
    assert record["refusals"] == {"refusal": 24}
    assert record["budget"]["dispatched_calls"] == 24 == transports[0].posts
    assert Decimal(record["budget"]["spent_usd"]) == Decimal(24) * (
        Decimal(1200) + Decimal(3) * 5
    ) / Decimal(1_000_000)
    captured = capsys.readouterr()
    for surface in (path.read_text(encoding="ascii"), captured.out, captured.err, caplog.text):
        assert CANARY_KEY not in surface and "sk-ant-eg-canary" not in surface
