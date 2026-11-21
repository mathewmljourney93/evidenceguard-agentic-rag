"""M7 (ADR-0029): CI runs the contract suite and never the live suite or a provider key."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")


def _job(name: str) -> str:
    start = WORKFLOW.index(f"\n  {name}:")
    following = [
        WORKFLOW.find(f"\n  {other}:", start + 1)
        for other in ("verify", "integration", "container")
    ]
    ends = [index for index in following if index > start]
    return WORKFLOW[start : min(ends) if ends else len(WORKFLOW)]


def test_the_integration_job_runs_both_contract_suites_after_pytest() -> None:
    job = _job("integration")
    pytest_step = job.index("uv run --locked pytest -m integration")
    for database, variant in (
        ("evidenceguard_contract_eval", ""),
        ("evidenceguard_contract_injected_eval", " --variant injected"),
    ):
        assert f"createdb -U evidenceguard {database}" in job
        command = f"eg-eval run --suite contract{variant} --output"
        assert command in job and job.index(command) > pytest_step
        assert (
            f"EG_EVAL_DATABASE_URL: postgresql+psycopg://evidenceguard:evidenceguard-ci-only@localhost:5432/{database}"
            in job
        )
    assert "$RUNNER_TEMP" in job or "${RUNNER_TEMP}" in job


def test_the_wheel_check_runs_eg_eval_help() -> None:
    assert '"${bin}/eg-eval" --help' in _job("verify")


def test_ci_never_runs_the_live_suite_or_reads_a_provider_key() -> None:
    assert "--suite live" not in WORKFLOW
    assert "EG_ANTHROPIC_API_KEY:" not in WORKFLOW
    assert "secrets.EG_ANTHROPIC_API_KEY" not in WORKFLOW
    assert "ANTHROPIC_API_KEY }}" not in WORKFLOW
