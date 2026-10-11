from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from evidenceguard_domain.evidence import ReportContent
from evidenceguard_domain.report import ReportRevision, content_sha256


def _reversed_keys(value: Any) -> Any:
    """Rebuild nested dicts with their keys in reverse insertion order."""
    if isinstance(value, dict):
        return {key: _reversed_keys(value[key]) for key in reversed(list(value))}
    if isinstance(value, list | tuple):
        return [_reversed_keys(item) for item in value]
    return value


def test_hash_is_stable_across_equal_content(content: ReportContent) -> None:
    rebuilt = ReportContent.model_validate(_reversed_keys(content.model_dump(mode="json")))

    assert rebuilt == content
    assert content_sha256(rebuilt) == content_sha256(content)


def test_surrounding_whitespace_is_not_substantive(content: ReportContent) -> None:
    padded = content.model_copy(update={"title": f"  {content.title}  "})

    assert content_sha256(padded) == content_sha256(content)


@pytest.mark.parametrize(
    "change",
    [
        "title",
        "finding statement",
        "finding order",
        "unresolved questions",
        "question flag",
    ],
)
def test_substantive_changes_change_the_hash(content: ReportContent, change: str) -> None:
    finding = content.findings[0]
    if change == "title":
        changed = content.model_copy(update={"title": "Another title"})
    elif change == "finding statement":
        edited = finding.model_copy(update={"statement": "The vendor states 30 days."})
        changed = content.model_copy(update={"findings": (edited,)})
    elif change == "finding order":
        second = finding.model_copy(update={"finding_id": uuid4()})
        content = content.model_copy(update={"findings": (finding, second)})
        changed = content.model_copy(update={"findings": (second, finding)})
    elif change == "unresolved questions":
        changed = content.model_copy(update={"unresolved_question_ids": ("RET-01", "BCP-01")})
    else:
        unresolved = content.questions[1]
        assert unresolved.question_id in content.unresolved_question_ids
        flagged = unresolved.model_copy(update={"requires_documentary_support": True})
        changed = content.model_copy(update={"questions": (content.questions[0], flagged)})

    assert content_sha256(changed) != content_sha256(content)


def test_metadata_does_not_change_the_hash(content: ReportContent, now: datetime) -> None:
    report_id = uuid4()
    first = ReportRevision.create(
        report_id=report_id,
        revision_number=1,
        content=content,
        created_by=uuid4(),
        created_at=now,
    )
    second = ReportRevision.create(
        report_id=report_id,
        revision_number=1,
        content=content,
        created_by=uuid4(),
        created_at=now + timedelta(days=3),
    )

    assert first.content_sha256 == second.content_sha256 == content_sha256(content)


def test_revision_rejects_a_hash_that_does_not_match(content: ReportContent, now: datetime) -> None:
    with pytest.raises(ValidationError, match="does not match"):
        ReportRevision(
            report_id=uuid4(),
            revision_number=1,
            content=content,
            content_sha256="0" * 64,
            created_by=uuid4(),
            created_at=now,
        )


def test_revision_requires_a_timezone_aware_timestamp(content: ReportContent) -> None:
    with pytest.raises(ValidationError):
        ReportRevision.create(
            report_id=uuid4(),
            revision_number=1,
            content=content,
            created_by=uuid4(),
            created_at=datetime(2026, 10, 11, 12, 0),
        )


def test_revision_content_cannot_change_after_creation(
    content: ReportContent, now: datetime
) -> None:
    revision = ReportRevision.create(
        report_id=uuid4(),
        revision_number=1,
        content=content,
        created_by=uuid4(),
        created_at=now,
    )
    original_hash = revision.content_sha256

    with pytest.raises(ValidationError):
        revision.content.findings[0].statement = "Tampered"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        revision.content.findings.append(revision.content.findings[0])  # type: ignore[attr-defined]

    assert content_sha256(revision.content) == original_hash


def test_model_copy_revalidates_instead_of_bypassing_the_hash(
    content: ReportContent, now: datetime
) -> None:
    revision = ReportRevision.create(
        report_id=uuid4(),
        revision_number=1,
        content=content,
        created_by=uuid4(),
        created_at=now,
    )
    edited = content.model_copy(update={"title": "Edited"})

    with pytest.raises(ValidationError, match="does not match"):
        revision.model_copy(update={"content": edited})
