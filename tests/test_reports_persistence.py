"""Unit tests (no database) for the error mapping in ``evidenceguard_persistence.reports``.

Each refused input must raise an error the API maps (422 or 503), never a bare ``ValueError``,
which would surface as a 500.
"""

import hashlib
from typing import Any, cast
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session, sessionmaker

from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_domain.report import Decision
from evidenceguard_domain.review_report_approval import ExportResult, InvalidRevisionContentError
from evidenceguard_persistence import reports


def _no_database() -> sessionmaker[Session]:
    def refuse(*_args: Any, **_kwargs: Any) -> Session:
        raise AssertionError("no SQL may run for this input")

    return cast(sessionmaker[Session], refuse)


def test_a_rejection_without_a_comment_is_invalid_content_before_any_sql() -> None:
    actor = ActorContext(tenant_id=uuid4(), actor_id=uuid4(), role=Role.APPROVER)
    with pytest.raises(InvalidRevisionContentError) as raised:
        reports.decide_report(
            _no_database(),
            actor,
            uuid4(),
            revision_number=1,
            content_sha256="0" * 64,
            decision=Decision.REJECT,
            comment=None,
        )
    assert not isinstance(raised.value, ValueError)


def test_an_export_whose_declared_digest_differs_from_its_body_is_inconsistent() -> None:
    body = b"# Report\n"
    good = ExportResult(
        body=body, media_type="text/markdown", export_sha256=hashlib.sha256(body).hexdigest()
    )
    assert reports._checked_export_digest(good) == good.export_sha256
    bad = ExportResult(body=body, media_type="text/markdown", export_sha256="0" * 64)
    with pytest.raises(reports.ReportRecordInconsistentError) as raised:
        reports._checked_export_digest(bad)
    assert not isinstance(raised.value, ValueError)
