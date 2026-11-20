"""PostgreSQL integration tests for the W8 review routes (ADR-0027).

The app runs with an in-memory authenticator and the real ``DatabaseReviewService`` on the
disposable engine, with injected review settings (a synthetic model id that the scripted test
provider answers for). Revisions are ingested and indexed through the real worker paths; the
review job runs through ``production_registry`` given a review handler built by the production
``build_review_handler`` over the **test** provider. Nothing reaches a network. Skipped without
``EG_TEST_DATABASE_URL`` (required in CI).
"""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker

from evidenceguard_agents.scripted import FAKE_MODEL_ID
from evidenceguard_api.app import create_app
from evidenceguard_api.database import AppDatabase
from evidenceguard_api.problems import PublicMessage
from evidenceguard_api.reviews import DatabaseReviewService
from evidenceguard_domain.context import ActorContext
from evidenceguard_persistence.credentials import generate_api_key
from evidenceguard_persistence.db import create_session_factory
from evidenceguard_persistence.models import ReviewOutputRow
from evidenceguard_persistence.settings import ReviewProvider, ReviewSettings
from evidenceguard_worker.handlers import production_registry
from evidenceguard_worker.review_wiring import build_review_handler

if TYPE_CHECKING:
    import review_postgres_world as pw
else:
    from tests import review_postgres_world as pw

pytestmark = pytest.mark.integration

KEY = "w8-pg-review-0001"


class Keys:
    def __init__(self) -> None:
        self.known: dict[str, ActorContext] = {}

    def __call__(self, credential: str) -> ActorContext | None:
        return self.known.get(credential)

    def header(self, actor: ActorContext, key: str | None = KEY) -> dict[str, str]:
        credential = generate_api_key().plaintext.get_secret_value()
        self.known[credential] = actor
        headers = {"Authorization": f"Bearer {credential}"}
        if key is not None:
            headers["Idempotency-Key"] = key
        return headers


@dataclass
class World:
    engine: Engine
    factory: sessionmaker[Session]
    actor: ActorContext
    vendor_id: UUID
    revision_id: UUID
    chunk_id: UUID
    keys: Keys
    settings: list[ReviewSettings]
    client: TestClient

    def post(self, vendor_id: UUID | None = None, key: str = KEY) -> Any:
        return self.client.post(
            "/v1/reviews",
            json={"vendor_id": str(vendor_id or self.vendor_id)},
            headers=self.keys.header(self.actor, key),
        )

    def get(self, path: str) -> Any:
        return self.client.get(path, headers=self.keys.header(self.actor, None))


def _settings(model: str = FAKE_MODEL_ID) -> ReviewSettings:
    return ReviewSettings(review_provider=ReviewProvider.ANTHROPIC, review_model=model)


@pytest.fixture
def world(migrated: Engine, test_database_url: URL) -> Iterator[World]:
    engine = pw.engine_for(test_database_url)
    factory = create_session_factory(engine)
    actor = pw.tenant(engine, "w8-api")
    vendor_id = pw.vendor(engine, actor.tenant_id)
    revision_id = pw.ready_revision(factory, actor, vendor_id)
    (chunk_id,) = pw.chunk_ids(engine, revision_id)[:1]
    settings = [_settings()]
    keys = Keys()
    database = AppDatabase(engine_factory=lambda: engine)
    service = DatabaseReviewService(database, settings_loader=lambda: settings[-1])
    app = create_app(authenticator=keys, database=database, review_service=service)
    try:
        with TestClient(app) as client:
            yield World(
                engine, factory, actor, vendor_id, revision_id, chunk_id, keys, settings, client
            )
    finally:
        database.close()
        engine.dispose()


def test_post_review_then_production_registry_with_test_provider_completes_it(
    world: World,
) -> None:
    accepted = world.post()
    assert accepted.status_code == 202
    body = accepted.json()
    assert body["status"] == "queued"
    assert body["revision_ids"] == [str(world.revision_id)]
    assert body["excluded_pending"] == {"count": 0, "revision_ids": [], "truncated": False}
    review_id = body["review_id"]

    detail = world.get(f"/v1/reviews/{review_id}").json()
    assert detail["model_id"] == FAKE_MODEL_ID
    assert (detail["template_id"], detail["template_version"]) == ("vendor_security_review", 1)
    assert detail["job_id"] == body["job_id"] and detail["status"] == "queued"

    handler = build_review_handler(pw.provider(world.chunk_id), world.factory)
    registry = production_registry(review_handler=handler)
    assert pw.work(world.factory, registry).exit_code == 0

    assert pw.job_row(world.engine, UUID(body["job_id"])).status == "succeeded"
    assert world.get(f"/v1/reviews/{review_id}").json()["status"] == "completed"
    result = world.get(f"/v1/reviews/{review_id}/result")
    assert result.status_code == 200
    out = result.json()
    with world.engine.connect() as connection:
        row = connection.execute(
            select(ReviewOutputRow.__table__).where(ReviewOutputRow.review_id == UUID(review_id))
        ).one()
    assert out["review_id"] == review_id and out["job_attempt"] == 1
    assert out["wrapper_sha256"] == row.wrapper_sha256
    assert out["markdown_sha256"] == row.markdown_sha256
    assert out["question_count"] == len(pw.question_ids()) == 8
    assert (out["finding_count"], out["unresolved_count"], out["markdown_bytes"]) == (
        row.finding_count,
        row.unresolved_count,
        row.markdown_bytes,
    )
    assert isinstance(out["report"], dict) and out["report"]


def test_registry_without_review_handler_leaves_review_queued(world: World) -> None:
    body = world.post().json()

    assert "run_review" not in production_registry().kinds
    assert pw.work(world.factory, production_registry()).exit_code == 0

    job = pw.job_row(world.engine, UUID(body["job_id"]))
    assert (job.status, job.attempt) == ("queued", 0)
    assert world.get(f"/v1/reviews/{body['review_id']}").json()["status"] == "queued"
    result = world.get(f"/v1/reviews/{body['review_id']}/result")
    assert result.status_code == 409
    assert result.json()["detail"] == PublicMessage.RESULT_NOT_READY.value


def test_repeated_key_returns_original_review_over_http(world: World) -> None:
    first = world.post()
    second = world.post()

    assert (first.status_code, second.status_code) == (202, 200)
    assert second.json() == first.json()

    other_vendor = pw.vendor(world.engine, world.actor.tenant_id, slug="other-vendor")
    reused = world.post(vendor_id=other_vendor)
    assert reused.status_code == 409
    assert reused.json()["detail"] == PublicMessage.IDEMPOTENCY_KEY_REUSED.value
    assert KEY not in reused.text

    world.settings.append(_settings("fake-other-model-v1"))  # the digest covers the model id
    changed = world.post()
    assert changed.status_code == 409
    assert changed.json()["detail"] == PublicMessage.IDEMPOTENCY_KEY_REUSED.value

    empty = world.post(vendor_id=other_vendor, key="w8-pg-review-0002")
    assert empty.status_code == 409
    assert empty.json()["detail"] == PublicMessage.NO_ACTIVE_REVISIONS.value
    missing = world.post(vendor_id=uuid4(), key="w8-pg-review-0003")
    assert missing.status_code == 404


def test_job_view_shows_the_run_review_job(world: World) -> None:
    body = world.post().json()

    response = world.get(f"/v1/jobs/{body['job_id']}")

    assert response.status_code == 200
    job = response.json()
    assert (job["id"], job["kind"], job["status"]) == (body["job_id"], "run_review", "queued")
    assert (job["attempt"], job["max_attempts"]) == (0, 3)
    other = pw.tenant(world.engine, "w8-api-other")
    foreign = world.client.get(f"/v1/jobs/{body['job_id']}", headers=world.keys.header(other, None))
    assert foreign.status_code == 404
    review = world.client.get(
        f"/v1/reviews/{body['review_id']}", headers=world.keys.header(other, None)
    )
    assert review.status_code == 404
