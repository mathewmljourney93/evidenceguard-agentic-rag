"""Shared PostgreSQL setup for the M5g integration tests (not a test module).

It follows the M5d/M5e integration precedent: revisions are ingested and indexed through the real
worker and M4c paths (offline hash profile), the review is created through M5d with the **pinned**
template and prompts, and ``run_review`` runs through the real runtime (``run_worker`` with a
**test** registry; production never registers it) or a real ``JobContext`` over the M3 fence. Model
results come from the scripted fake provider; nothing reaches a network. Every module importing
this one is marked ``integration`` and is skipped without ``EG_TEST_DATABASE_URL``.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Engine, create_engine, insert, select
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from evidenceguard_agents.prompts import load_prompt
from evidenceguard_agents.scripted import Respond, ScriptedFakeProvider, Step
from evidenceguard_agents.templates import load_template
from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_domain.evidence import SourceType
from evidenceguard_domain.jobs import JobPayload
from evidenceguard_domain.reviews import ReviewConfiguration, ReviewRequest
from evidenceguard_domain.revisions import RevisionContent
from evidenceguard_persistence import documents as revision_store
from evidenceguard_persistence import indexing
from evidenceguard_persistence import jobs as job_store
from evidenceguard_persistence.db import create_session_factory, transaction
from evidenceguard_persistence.models import Chunk, Job, Tenant, Vendor
from evidenceguard_retrieval.embeddings import HASH_IDENTITY
from evidenceguard_worker.handlers import production_registry
from evidenceguard_worker.ingest import INGEST_REVISION_KIND, ingest_revision
from evidenceguard_worker.registry import HandlerRegistry, JobHandler
from evidenceguard_worker.review import make_run_review_handler
from evidenceguard_worker.review_seams import create_review_with_artifacts
from evidenceguard_worker.runtime import DatabaseJobStore, Timings, WorkerResult, run_worker

MARKDOWN = "text/markdown"
QUOTE = "encrypted at rest"
BODY = "Customer data is encrypted at rest with AES-256.\n"
TIMINGS = Timings(
    idle_poll=0.05,
    backoff_initial=0.05,
    backoff_cap=0.2,
    heartbeat_interval=0.2,
    drain=5.0,
    cancel_grace=5.0,
    lease_loss_grace=5.0,
    heartbeat_join=5.0,
    stop_check=0.01,
)
INGEST_ONLY = HandlerRegistry([(INGEST_REVISION_KIND, ingest_revision)])


def engine_for(url: URL) -> Engine:
    return create_engine(
        url,
        poolclass=NullPool,
        hide_parameters=True,
        connect_args={"options": "-c statement_timeout=20000"},
    )


def pinned_configuration() -> ReviewConfiguration:
    template = load_template("vendor_security_review", 1)
    verifier, _ = load_prompt("verifier", 1)
    analyst, _ = load_prompt("risk_analyst", 1)
    return ReviewConfiguration(
        template_id=template.ref.template_id,
        template_version=template.ref.version,
        template_sha256=template.ref.sha256,
        verifier_prompt=verifier.ref,
        analyst_prompt=analyst.ref,
        model_id="fake-scripted-v1",
    )


def question_ids() -> tuple[str, ...]:
    return tuple(q.question_id for q in load_template("vendor_security_review", 1).questions)


def tenant(engine: Engine, slug: str, role: Role = Role.REVIEWER) -> ActorContext:
    tenant_id = uuid4()
    with engine.begin() as connection:
        connection.execute(insert(Tenant).values(id=tenant_id, slug=slug, name=slug.title()))
    return ActorContext(tenant_id=tenant_id, actor_id=uuid4(), role=role)


def vendor(engine: Engine, tenant_id: UUID, slug: str = "lumenvale") -> UUID:
    vendor_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            insert(Vendor).values(id=vendor_id, tenant_id=tenant_id, slug=slug, name=slug.title())
        )
    return vendor_id


def work(factory: sessionmaker[Session], registry: HandlerRegistry) -> WorkerResult:
    return run_worker(
        DatabaseJobStore(factory), registry, worker_id="w-m5g", timings=TIMINGS, once=True
    )


def job_row(engine: Engine, job_id: UUID) -> Any:
    with engine.connect() as connection:
        return connection.execute(select(Job.__table__).where(Job.id == job_id)).one()


def drain(factory: sessionmaker[Session], registry: HandlerRegistry, limit: int = 4) -> None:
    for _ in range(limit):
        assert work(factory, registry).exit_code == 0


def ready_revision(
    factory: sessionmaker[Session],
    actor: ActorContext,
    vendor_id: UUID,
    key: str = "security-overview",
    body: str = BODY,
) -> UUID:
    """Create, ingest and index a revision (one queued job at a time)."""
    with transaction(factory) as session:
        created = revision_store.create_revision(
            session,
            actor,
            vendor_id=vendor_id,
            document_key=key,
            title=key.replace("-", " ").title(),
            source_type=SourceType.VENDOR_STATEMENT,
            content=RevisionContent.from_bytes(body.encode(), MARKDOWN),
        )
        job_store.enqueue(
            session,
            actor,
            kind=INGEST_REVISION_KIND,
            idempotency_key=str(created.revision.id),
            payload=JobPayload.from_mapping({"revision_id": str(created.revision.id)}),
        )
    assert work(factory, INGEST_ONLY).exit_code == 0
    with transaction(factory) as session:
        enqueued = indexing.enqueue_index_revision(
            session, actor, revision_id=created.revision.id, identity=HASH_IDENTITY
        )
    if enqueued.outcome is not indexing.EnqueueOutcome.READY:
        assert work(factory, production_registry()).exit_code == 0
    return created.revision.id


def chunk_ids(engine: Engine, revision_id: UUID) -> list[UUID]:
    with engine.connect() as connection:
        return list(
            connection.execute(
                select(Chunk.id).where(Chunk.revision_id == revision_id).order_by(Chunk.ordinal)
            ).scalars()
        )


def verifier_text(chunk_id: UUID, *, quote: str = QUOTE, rationale: str = "Cited.") -> str:
    import json

    return json.dumps(
        {
            "verdict": "supported",
            "claims": [
                {"text": "Stated.", "citations": [{"chunk_id": str(chunk_id), "quote": quote}]}
            ],
            "rationale": rationale,
        }
    )


def analyst_text(
    question_id: str, chunk_id: UUID, *, statement: str = "The vendor states it."
) -> str:
    import json

    return json.dumps(
        {
            "findings": [
                {
                    "question_ids": [question_id],
                    "title": "Vendor statement only",
                    "severity": "low",
                    "statement": statement,
                    "citations": [{"chunk_id": str(chunk_id), "quote": QUOTE}],
                    "follow_up_questions": ["Which evidence supports it?"],
                }
            ]
        }
    )


def provider(
    chunk_id: UUID, overrides: Mapping[tuple[str, str], tuple[Step, ...]] | None = None
) -> ScriptedFakeProvider:
    scripts: dict[tuple[str, str], tuple[Step, ...]] = {}
    for question_id in question_ids():
        scripts[("verifier", question_id)] = (Respond(verifier_text(chunk_id)),)
        scripts[("risk_analyst", question_id)] = (Respond(analyst_text(question_id, chunk_id)),)
    scripts.update(overrides or {})
    return ScriptedFakeProvider(scripts=scripts)


@dataclass
class ReviewWorld:
    engine: Engine
    factory: sessionmaker[Session]
    actor: ActorContext
    vendor_id: UUID
    revision_id: UUID
    chunk_id: UUID
    review_id: UUID
    job_id: UUID

    def registry(self, model: Any, **kwargs: Any) -> HandlerRegistry:
        handler: JobHandler = make_run_review_handler(model, session_factory=self.factory, **kwargs)
        return HandlerRegistry([("run_review", handler)])

    def run(self, model: Any, **kwargs: Any) -> WorkerResult:
        return work(self.factory, self.registry(model, **kwargs))

    def job(self) -> Any:
        return job_row(self.engine, self.job_id)


def review_world(
    migrated: Engine,
    url: URL,
    *,
    slug: str = "m5g",
    body: str = BODY,
    before_review: Callable[[sessionmaker[Session], ActorContext, UUID], None] | None = None,
) -> ReviewWorld:
    engine = engine_for(url)
    factory = create_session_factory(engine)
    actor = tenant(engine, slug)
    vendor_id = vendor(engine, actor.tenant_id)
    revision_id = ready_revision(factory, actor, vendor_id, body=body)
    if before_review is not None:
        before_review(factory, actor, vendor_id)
    request = ReviewRequest(
        vendor_id=vendor_id,
        idempotency_key=f"{slug}-review",
        identity=HASH_IDENTITY,
        configuration=pinned_configuration(),
    )
    created = create_review_with_artifacts(factory, actor, request)
    (chunk_id,) = chunk_ids(engine, revision_id)[:1]
    return ReviewWorld(
        engine=engine,
        factory=factory,
        actor=actor,
        vendor_id=vendor_id,
        revision_id=revision_id,
        chunk_id=chunk_id,
        review_id=created.review_id,
        job_id=created.job_id,
    )


def second_review(world: ReviewWorld, key: str = "m5g-second-review") -> tuple[UUID, UUID]:
    """Another review (and its own canonical ``run_review`` job) for the same tenant and vendor,
    created through M5d; it has no stages and no output."""
    request = ReviewRequest(
        vendor_id=world.vendor_id,
        idempotency_key=key,
        identity=HASH_IDENTITY,
        configuration=pinned_configuration(),
    )
    created = create_review_with_artifacts(world.factory, world.actor, request)
    return created.review_id, created.job_id
