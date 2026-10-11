from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_domain.evidence import (
    Citation,
    EvidenceQuestion,
    EvidenceStatus,
    Finding,
    ReportContent,
    Severity,
    SourceType,
)


@pytest.fixture
def tenant_a() -> UUID:
    return uuid4()


@pytest.fixture
def tenant_b() -> UUID:
    return uuid4()


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 10, 11, 12, 0, tzinfo=UTC)


@pytest.fixture
def reviewer(tenant_a: UUID) -> ActorContext:
    return ActorContext(tenant_id=tenant_a, actor_id=uuid4(), role=Role.REVIEWER)


@pytest.fixture
def approver(tenant_a: UUID) -> ActorContext:
    return ActorContext(tenant_id=tenant_a, actor_id=uuid4(), role=Role.APPROVER)


@pytest.fixture
def other_tenant_approver(tenant_b: UUID) -> ActorContext:
    return ActorContext(tenant_id=tenant_b, actor_id=uuid4(), role=Role.APPROVER)


@pytest.fixture
def content(tenant_a: UUID) -> ReportContent:
    """Synthetic tenant-A report: one vendor-claim finding and one unresolved question."""
    citation = Citation(
        tenant_id=tenant_a,
        document_revision_id=uuid4(),
        chunk_id=uuid4(),
        source_type=SourceType.VENDOR_STATEMENT,
        quote="Customer data is retained for ninety (90) days after termination.",
    )
    return ReportContent(
        tenant_id=tenant_a,
        title="Lumenvale Cloud security review",
        questions=(
            EvidenceQuestion(
                question_id="RET-01",
                text="How long is customer data retained after termination?",
                search_queries=("data retention after termination",),
            ),
            EvidenceQuestion(
                question_id="BCP-01",
                text="What is the recovery time objective for production?",
                search_queries=("recovery time objective",),
            ),
        ),
        findings=(
            Finding(
                tenant_id=tenant_a,
                finding_id=uuid4(),
                question_ids=("RET-01",),
                title="Retention period stated only by the vendor",
                severity=Severity.MEDIUM,
                statement="The vendor states a 90-day retention period after termination.",
                evidence_status=EvidenceStatus.VENDOR_CLAIM,
                citations=(citation,),
            ),
        ),
        unresolved_question_ids=("BCP-01",),
    )
