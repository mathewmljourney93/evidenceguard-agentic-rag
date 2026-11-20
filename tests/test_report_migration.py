"""Migration 0009 (M6, ADR-0028) rendered offline: tables, trigger function and triggers.

No database. The PostgreSQL round trip and ``alembic check`` are in
``test_reports_api_postgres.py``.
"""

import io
import re

import pytest
from alembic import command
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from evidenceguard_persistence.migration_config import alembic_config
from evidenceguard_persistence.models import Base
from evidenceguard_persistence.settings import DATABASE_URL_ENV


def _offline_0009(monkeypatch: pytest.MonkeyPatch, *, upgrade: bool) -> str:
    monkeypatch.delenv(DATABASE_URL_ENV, raising=False)
    buffer = io.StringIO()
    config = alembic_config(output_buffer=buffer)
    if upgrade:
        command.upgrade(config, "0008:0009", sql=True)
    else:
        command.downgrade(config, "0009:0008", sql=True)
    return buffer.getvalue()


def test_offline_0009_renders_the_tables_function_and_triggers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rendered = _offline_0009(monkeypatch, upgrade=True)
    assert re.findall(r"CREATE TABLE (\w+)", rendered) == [
        "reports",
        "report_revisions",
        "report_decisions",
        "report_finalizations",
        "audit_events",
    ]
    assert rendered.index("uq_review_outputs_tenant_id_review_id_wrapper_sha256") < rendered.index(
        "CREATE TABLE reports"
    )
    assert "ON DELETE" not in rendered and "ON UPDATE" not in rendered and "CASCADE" not in rendered
    assert "SET search_path = pg_catalog, pg_temp" in rendered
    assert "SECURITY INVOKER" in rendered and "SECURITY DEFINER" not in rendered
    assert "ERRCODE = 'restrict_violation'" in rendered
    assert "GENERATED ALWAYS AS IDENTITY" in rendered
    triggers = re.findall(r"CREATE TRIGGER (\w+) (BEFORE [A-Z ]+) ON public\.(\w+)", rendered)
    assert len(triggers) == 10
    for table in ("report_revisions", "report_decisions", "report_finalizations", "audit_events"):
        assert (f"eg_{table}_append_only", "BEFORE UPDATE OR DELETE", table) in triggers
        assert (f"eg_{table}_no_truncate", "BEFORE TRUNCATE", table) in triggers
    assert ("eg_reports_no_delete", "BEFORE DELETE", "reports") in triggers
    assert ("eg_reports_no_truncate", "BEFORE TRUNCATE", "reports") in triggers
    for name in ("reports", "report_revisions", "report_decisions", "audit_events"):
        model = str(
            CreateTable(Base.metadata.tables[name]).compile(dialect=postgresql.dialect())  # type: ignore[no-untyped-call]
        )
        for check in re.findall(r"CONSTRAINT (ck_\w+) CHECK \((.*)\)", model):
            assert f"CONSTRAINT {check[0]} CHECK ({check[1]})" in rendered, check[0]


def test_offline_0009_downgrade_drops_triggers_function_tables_then_the_unique(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rendered = _offline_0009(monkeypatch, upgrade=False)
    statements = [line for line in rendered.splitlines() if line.startswith(("DROP", "ALTER"))]
    assert len([s for s in statements if s.startswith("DROP TRIGGER")]) == 10
    assert statements[10:] == [
        "DROP FUNCTION public.eg_reject_append_only_change();",
        "DROP INDEX ix_audit_events_report_order;",
        "DROP TABLE audit_events;",
        "DROP TABLE report_finalizations;",
        "DROP TABLE report_decisions;",
        "DROP TABLE report_revisions;",
        "DROP TABLE reports;",
        "ALTER TABLE review_outputs DROP CONSTRAINT "
        "uq_review_outputs_tenant_id_review_id_wrapper_sha256;",
    ]
