"""PostgreSQL integration tests for the M6 report approval gate and export (ADR-0028).

Skipped without ``EG_TEST_DATABASE_URL`` (required in CI). A review is completed through the real
worker path with the scripted fake provider (no network), then the API runs with an in-memory
authenticator and the real ``DatabaseReportStore`` on the disposable engine. Concurrency cases
meet at a two-party ``threading.Barrier`` (bounded wait) on a named statement, never on timing;
every hook is removed in ``finally`` and every test asserts that its hook fired.
"""

import hashlib
import json
import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event, select, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from evidenceguard_agents.report_export import EXPORT_DISCLAIMER
from evidenceguard_api.app import create_app
from evidenceguard_api.database import AppDatabase
from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_domain.review_report_approval import ExportInput, ExportResult
from evidenceguard_persistence import reports as report_store
from evidenceguard_persistence.credentials import generate_api_key
from evidenceguard_persistence.models import (
    AuditEvent,
    ReportRevisionRow,
    ReportRow,
    ReviewOutputRow,
)

if TYPE_CHECKING:
    import review_postgres_world as pw
else:
    from tests import review_postgres_world as pw

pytestmark = pytest.mark.integration

RESTRICT_VIOLATION = "23001"
BARRIER_TIMEOUT = 10.0
HISTORY_TABLES = ("report_revisions", "report_decisions", "report_finalizations", "audit_events")


class Keys:
    def __init__(self) -> None:
        self.known: dict[str, ActorContext] = {}

    def __call__(self, credential: str) -> ActorContext | None:
        return self.known.get(credential)

    def header(self, actor: ActorContext) -> dict[str, str]:
        key = generate_api_key().plaintext.get_secret_value()
        self.known[key] = actor
        return {"Authorization": f"Bearer {key}"}


class Api:
    def __init__(self, world: pw.ReviewWorld) -> None:
        self.world = world
        self.engine = world.engine
        self.keys = Keys()
        self.app = create_app(authenticator=self.keys, database=AppDatabase(lambda: world.engine))
        self.client = TestClient(self.app)
        self.report_id = world.review_id
        self.base = f"/v1/reports/{world.review_id}"
        tenant = world.actor.tenant_id
        self.reviewer = self.actor(tenant, Role.REVIEWER)
        self.approver = self.actor(tenant, Role.APPROVER)
        self.second_approver = self.actor(tenant, Role.APPROVER)
        self.admin = self.actor(tenant, Role.ADMIN)

    def actor(self, tenant_id: UUID, role: Role) -> tuple[ActorContext, dict[str, str]]:
        actor = ActorContext(tenant_id=tenant_id, actor_id=uuid4(), role=role)
        return actor, self.keys.header(actor)

    def get(self, who: tuple[ActorContext, dict[str, str]]) -> Any:
        return self.client.get(self.base, headers=who[1])

    def revise(
        self,
        who: tuple[ActorContext, dict[str, str]],
        etag: str | None,
        *,
        notes: str = "Checked by a reviewer.",
        client: TestClient | None = None,
        findings: list[dict[str, Any]] | None = None,
    ) -> Any:
        if findings is None:
            findings = self.get(self.reviewer).json()["findings"]
        body = {
            "dispositions": [
                {"finding_id": f["finding_id"], "disposition": "accepted", "note": "Seen."}
                for f in findings
            ],
            "notes": notes,
            "reason": "Synthetic review pass.",
        }
        headers = dict(who[1])
        if etag is not None:
            headers["If-Match"] = etag
        return (client or self.client).post(self.base + "/revisions", headers=headers, json=body)

    def decide(
        self,
        who: tuple[ActorContext, dict[str, str]],
        number: int,
        sha: str,
        decision: str = "approve",
        comment: str | None = None,
    ) -> Any:
        body: dict[str, Any] = {"revision_no": number, "content_sha256": sha, "decision": decision}
        if comment is not None:
            body["comment"] = comment
        return self.client.post(self.base + "/approval", headers=who[1], json=body)

    def finalize(self, who: tuple[ActorContext, dict[str, str]], number: int, sha: str) -> Any:
        body = {"revision_no": number, "content_sha256": sha}
        return self.client.post(self.base + "/finalize", headers=who[1], json=body)

    def export(self, who: tuple[ActorContext, dict[str, str]], fmt: str) -> Any:
        return self.client.get(self.base + "/export", headers=who[1], params={"format": fmt})

    def current(self) -> tuple[int, str, str]:
        view = self.get(self.reviewer).json()
        number, sha = view["revision_no"], view["content_sha256"]
        return number, sha, f'"r{number}-{sha}"'

    def finalized(self) -> tuple[int, str]:
        """r1, revised by the reviewer to r2, approved by one approver, finalized by the other."""
        _, _, etag = self.current()
        assert self.revise(self.reviewer, etag).status_code == 201
        number, sha, _ = self.current()
        assert self.decide(self.approver, number, sha).status_code == 200
        assert self.finalize(self.second_approver, number, sha).status_code == 200
        return number, sha

    def audit(self) -> list[Any]:
        with self.engine.connect() as connection:
            return list(
                connection.execute(select(AuditEvent.__table__).order_by(AuditEvent.id)).all()
            )

    def count(self, table: str) -> int:
        with self.engine.connect() as connection:
            value: int = connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
        return value


@pytest.fixture
def api(migrated: Engine, test_database_url: URL) -> Iterator[Api]:
    world = pw.review_world(migrated, test_database_url, slug="m6")
    try:
        assert world.run(pw.provider(world.chunk_id)).exit_code == 0
        assert world.job().status == "succeeded"
        yield Api(world)
    finally:
        world.engine.dispose()


@contextmanager
def on_statement(
    engine: Engine,
    match: Callable[[str], bool],
    action: Callable[[], object],
    *,
    after: bool = False,
) -> Iterator[list[str]]:
    """Run ``action`` before (or, with ``after``, once it has executed) each matching statement."""
    fired: list[str] = []
    identifier = "after_cursor_execute" if after else "before_cursor_execute"

    def hook(_conn: Any, _cursor: Any, statement: str, *_: Any) -> None:
        if match(statement):
            fired.append(statement)
            action()

    event.listen(engine, identifier, hook)
    try:
        yield fired
    finally:
        event.remove(engine, identifier, hook)


def wait_until_blocked_or_done(engine: Engine, future: Future[Any]) -> None:
    """Return once ``future`` has finished or another session in this database waits on a lock
    (bounded by ``BARRIER_TIMEOUT``). Either outcome is a state, not a timing assumption."""
    deadline = time.monotonic() + BARRIER_TIMEOUT
    while time.monotonic() < deadline:
        if future.done():
            return
        with engine.connect() as connection:
            waiting = connection.execute(
                text(
                    "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                    "AND wait_event_type = 'Lock' AND pid <> pg_backend_pid()"
                )
            ).scalar_one()
        if waiting:
            return
        time.sleep(0.01)
    raise AssertionError("the other request neither finished nor waited on a lock")


def _sqlstate(error: DBAPIError) -> str | None:
    return getattr(error.orig, "sqlstate", None)


# --- creation and reads --------------------------------------------------------------------------


def test_get_creates_revision_one_from_the_stored_output_with_etag(api: Api) -> None:
    first = api.get(api.reviewer)
    assert first.status_code == 200
    view = first.json()
    assert view["report_id"] == view["review_id"] == str(api.report_id)
    assert view["status"] == "draft" and view["revision_no"] == 1
    assert first.headers["ETag"] == f'"r1-{view["content_sha256"]}"'
    assert view["findings"] and {f["disposition"] for f in view["findings"]} == {"open"}
    assert view["approval"] is None and view["finalization"] is None and view["notes"] is None
    with api.engine.connect() as connection:
        output = connection.execute(select(ReviewOutputRow.__table__)).one()
        revision = connection.execute(select(ReportRevisionRow.__table__)).one()
        report = connection.execute(select(ReportRow.__table__)).one()
    assert view["wrapper_sha256"] == output.wrapper_sha256 == report.base_wrapper_sha256
    assert revision.origin == "generated" and revision.created_by is None
    assert revision.content_sha256 == view["content_sha256"]
    assert hashlib.sha256(revision.content_canonical.encode("ascii")).hexdigest() == (
        revision.content_sha256
    )
    assert output.wrapper_sha256 in revision.content_canonical
    second = api.get(api.approver)
    assert second.status_code == 200 and second.headers["ETag"] == first.headers["ETag"]
    assert api.count("reports") == 1 and api.count("report_revisions") == 1
    assert api.audit() == []  # creation is recorded by the generated revision row only


def test_concurrent_first_reads_create_one_report(api: Api) -> None:
    barrier = threading.Barrier(2, timeout=BARRIER_TIMEOUT)
    with on_statement(
        api.engine, lambda s: s.lstrip().startswith("INSERT INTO reports"), barrier.wait
    ) as fired:
        clients = (TestClient(api.app), TestClient(api.app))
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda c: c.get(api.base, headers=api.reviewer[1]), clients))
    assert len(fired) == 2
    assert [r.status_code for r in results] == [200, 200]
    assert results[0].headers["ETag"] == results[1].headers["ETag"]
    assert api.count("reports") == 1 and api.count("report_revisions") == 1


def test_cross_tenant_report_is_404(api: Api) -> None:
    assert api.get(api.reviewer).status_code == 200
    other = uuid4()
    with api.engine.begin() as connection:
        connection.execute(
            text("INSERT INTO tenants (id, slug, name) VALUES (:id, 'm6-other', 'Other')"),
            {"id": other},
        )
    stranger = api.actor(other, Role.APPROVER)
    assert api.get(stranger).status_code == 404
    _, sha, etag = api.current()
    assert api.decide(stranger, 1, sha).status_code == 404
    assert api.revise(stranger, etag).status_code == 404
    assert api.export(stranger, "md").status_code == 404
    assert api.count("reports") == 1 and api.audit() == []


def test_a_review_without_output_is_404(api: Api) -> None:
    review_id, _job_id = pw.second_review(api.world, key="m6-second-review")
    response = api.client.get(f"/v1/reports/{review_id}", headers=api.reviewer[1])
    assert response.status_code == 404
    missing = api.client.get(f"/v1/reports/{uuid4()}", headers=api.reviewer[1])
    assert missing.status_code == 404
    assert api.count("reports") == 0


# --- roles ---------------------------------------------------------------------------------------


def test_a_reviewer_cannot_approve_reject_or_finalize_is_403(api: Api) -> None:
    number, sha, _ = api.current()
    assert api.decide(api.reviewer, number, sha).status_code == 403
    assert api.decide(api.reviewer, number, sha, "reject", "Not enough.").status_code == 403
    assert api.decide(api.approver, number, sha).status_code == 200
    assert api.finalize(api.reviewer, number, sha).status_code == 403
    assert api.get(api.reviewer).json()["status"] == "approved"


def test_an_admin_gets_403_on_every_report_route(api: Api) -> None:
    number, sha, etag = api.current()
    responses = [
        api.get(api.admin),
        api.revise(api.admin, etag),
        api.decide(api.admin, number, sha),
        api.finalize(api.admin, number, sha),
        api.export(api.admin, "md"),
    ]
    assert [r.status_code for r in responses] == [403] * 5
    assert api.audit() == [] and api.count("report_revisions") == 1


# --- If-Match and compare-and-set ----------------------------------------------------------------


def test_missing_if_match_is_428_and_malformed_is_422(api: Api) -> None:
    _, sha, etag = api.current()
    assert api.revise(api.reviewer, None).status_code == 428
    for bad in (
        f'W/"r1-{sha}"',
        f'"r0-{sha}"',
        f'"r1-{sha.upper()}"',
        f"r1-{sha}",
        f'"r1-{sha[:-1]}"',
        f'"r1000-{sha}"',
        "*",
        f'"r1-{sha}", "r1-{sha}"',
    ):
        assert api.revise(api.reviewer, bad).status_code == 422, bad
    findings = api.get(api.reviewer).json()["findings"]
    body = {
        "dispositions": [{"finding_id": f["finding_id"], "disposition": "open"} for f in findings],
        "notes": "Twice.",
    }
    twice = api.client.post(
        api.base + "/revisions",
        headers=[*api.reviewer[1].items(), ("If-Match", etag), ("If-Match", etag)],
        json=body,
    )
    assert twice.status_code == 422
    assert api.count("report_revisions") == 1


def test_revise_with_a_stale_if_match_is_409(api: Api) -> None:
    _, sha1, etag1 = api.current()
    created = api.revise(api.reviewer, etag1)
    assert created.status_code == 201 and created.json()["revision_no"] == 2
    _, sha2, etag2 = api.current()
    assert created.headers["ETag"] == etag2 and sha2 != sha1
    assert api.revise(api.reviewer, etag1, notes="Again.").status_code == 409
    assert api.revise(api.reviewer, f'"r2-{sha1}"', notes="Again.").status_code == 409
    assert api.revise(api.reviewer, f'"r3-{sha2}"', notes="Again.").status_code == 409
    assert api.count("report_revisions") == 2


def test_concurrent_revisions_with_the_same_if_match_one_201_one_409(api: Api) -> None:
    _, _, etag = api.current()
    findings = api.get(api.reviewer).json()["findings"]  # read before the barrier
    barrier = threading.Barrier(2, timeout=BARRIER_TIMEOUT)
    with on_statement(
        api.engine,
        lambda s: "FROM reports" in s and "FOR UPDATE" in s,
        barrier.wait,
    ) as fired:
        clients = (TestClient(api.app), TestClient(api.app))
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(
                    api.revise, api.reviewer, etag, notes=f"Pass {n}.", client=c, findings=findings
                )
                for n, c in enumerate(clients)
            ]
            codes = sorted(f.result().status_code for f in futures)
    assert len(fired) == 2
    assert codes == [201, 409]
    assert api.count("report_revisions") == 2
    assert [e.action for e in api.audit()] == ["revise"]


@pytest.mark.parametrize("case", ["stale", "wrong_hash"])
def test_approve_with_a_stale_revision_or_wrong_hash_is_409(api: Api, case: str) -> None:
    number1, sha1, etag1 = api.current()
    assert api.revise(api.reviewer, etag1).status_code == 201
    number2, sha2, _ = api.current()
    if case == "stale":
        response = api.decide(api.approver, number1, sha1)
    else:
        response = api.decide(api.approver, number2, "0" * 64)
    assert response.status_code == 409
    assert api.count("report_decisions") == 0
    assert api.decide(api.approver, number2, sha2).status_code == 200


def test_finalize_with_a_wrong_hash_is_409(api: Api) -> None:
    number, sha, _ = api.current()
    assert api.decide(api.approver, number, sha).status_code == 200
    assert api.finalize(api.second_approver, number, "f" * 64).status_code == 409
    assert api.finalize(api.second_approver, number + 1, sha).status_code == 409
    assert api.count("report_finalizations") == 0
    assert api.finalize(api.second_approver, number, sha).status_code == 200


def test_a_revision_after_approval_resets_to_draft_and_blocks_finalize(api: Api) -> None:
    number1, sha1, etag1 = api.current()
    approved = api.decide(api.approver, number1, sha1)
    assert approved.status_code == 200 and approved.json()["status"] == "approved"
    revised = api.revise(api.reviewer, etag1)
    assert revised.status_code == 201
    view = revised.json()
    assert view["status"] == "draft" and view["revision_no"] == 2 and view["approval"] is None
    assert api.finalize(api.approver, number1, sha1).status_code == 409
    assert api.finalize(api.approver, 2, view["content_sha256"]).status_code == 409
    assert api.count("report_finalizations") == 0


def test_revise_a_finalized_report_is_409(api: Api) -> None:
    api.finalized()
    _, _, etag = api.current()
    assert api.revise(api.reviewer, etag, notes="After the fact.").status_code == 409
    number, sha, _ = api.current()
    assert api.decide(api.approver, number, sha, "reject", "Too late.").status_code == 409


# --- decisions -----------------------------------------------------------------------------------


def test_repeated_identical_approval_and_finalize_are_idempotent_without_new_audit_events(
    api: Api,
) -> None:
    number, sha, _ = api.current()
    first = api.decide(api.approver, number, sha, comment="Looks right.")
    again = api.decide(api.approver, number, sha, comment="Looks right.")
    assert first.status_code == again.status_code == 200
    assert first.json() == again.json()
    final = api.finalize(api.second_approver, number, sha)
    final_again = api.finalize(api.second_approver, number, sha)
    assert final.status_code == final_again.status_code == 200
    assert (
        final.json() == final_again.json() and final.headers["ETag"] == final_again.headers["ETag"]
    )
    assert [e.action for e in api.audit()] == ["approve", "finalize"]
    assert api.count("report_decisions") == 1 and api.count("report_finalizations") == 1
    assert api.finalize(api.approver, number, sha).status_code == 409  # another finalizer


def test_approval_by_a_different_approver_is_409(api: Api) -> None:
    number, sha, _ = api.current()
    assert api.decide(api.approver, number, sha).status_code == 200
    assert api.decide(api.second_approver, number, sha).status_code == 409
    assert api.decide(api.approver, number, sha, comment="Changed.").status_code == 409
    assert api.count("report_decisions") == 1


def test_an_approver_cannot_approve_their_own_revision_is_409(api: Api) -> None:
    _, _, etag = api.current()
    assert api.revise(api.approver, etag).status_code == 201  # an approver may revise
    number, sha, _ = api.current()
    assert api.decide(api.approver, number, sha).status_code == 409
    assert api.decide(api.approver, number, sha, "reject", "Mine.").status_code == 409
    assert api.decide(api.second_approver, number, sha).status_code == 200
    assert api.finalize(api.approver, number, sha).status_code == 409
    assert api.finalize(api.second_approver, number, sha).status_code == 200


def test_reject_requires_a_comment_and_returns_changes_requested(api: Api) -> None:
    number, sha, _ = api.current()
    assert api.decide(api.approver, number, sha, "reject").status_code == 422
    assert api.decide(api.approver, number, sha, "reject", "   ").status_code == 422
    rejected = api.decide(api.approver, number, sha, "reject", "Needs evidence.")
    assert rejected.status_code == 200 and rejected.json()["status"] == "changes_requested"
    assert rejected.json()["approval"]["decision"] == "reject"
    assert api.decide(api.approver, number, sha).status_code == 409


# --- export --------------------------------------------------------------------------------------


@pytest.mark.parametrize("fmt", ["md", "json"])
def test_export_before_finalize_is_409(api: Api, fmt: str) -> None:
    assert api.export(api.reviewer, fmt).status_code == 409  # draft
    number, sha, _ = api.current()
    assert api.decide(api.approver, number, sha).status_code == 200
    assert api.export(api.reviewer, fmt).status_code == 409  # approved
    assert api.audit()[-1].action == "approve"


def test_finalized_export_md_and_json_include_revision_hash_approver_and_disclaimer(
    api: Api,
) -> None:
    number, sha = api.finalized()
    approver_id = str(api.approver[0].actor_id)
    finalizer_id = str(api.second_approver[0].actor_id)
    wrapper_sha = api.get(api.reviewer).json()["wrapper_sha256"]

    md = api.export(api.reviewer, "md")
    assert md.status_code == 200
    assert md.headers["content-type"] == "text/markdown; charset=utf-8"
    assert md.headers["content-disposition"] == (
        f'attachment; filename="report-{api.report_id}-r{number}.md"'
    )
    assert md.headers["ETag"] == f'"r{number}-{sha}"'
    text_body = md.content.decode("utf-8")
    for value in (sha, wrapper_sha, approver_id, finalizer_id, EXPORT_DISCLAIMER):
        assert value in text_body

    js = api.export(api.approver, "json")
    assert js.status_code == 200 and js.headers["content-type"] == "application/json"
    assert js.headers["content-disposition"].endswith(f'r{number}.json"')
    obj = json.loads(js.content)
    assert obj["revision_no"] == number and obj["content_sha256"] == sha
    assert obj["approved_by"] == approver_id and obj["finalized_by"] == finalizer_id
    assert obj["disclaimer"] == EXPORT_DISCLAIMER and obj["wrapper_sha256"] == wrapper_sha
    with api.engine.connect() as connection:
        stored = connection.execute(
            select(ReportRevisionRow.content_canonical).where(
                ReportRevisionRow.revision_no == number
            )
        ).scalar_one()
        wrapper = connection.execute(select(ReviewOutputRow.wrapper_canonical)).scalar_one()
    canonical = json.dumps(obj["revision"], sort_keys=True, separators=(",", ":"))
    assert canonical == stored  # the export embeds exactly the approved revision bytes
    assert json.dumps(obj["wrapper"], sort_keys=True, separators=(",", ":")) == wrapper
    assert api.export(api.reviewer, "pdf").status_code == 422


def test_export_reads_no_stage_or_plan_rows(api: Api) -> None:
    api.finalized()
    with on_statement(api.engine, lambda _s: True, lambda: None) as fired:
        response = api.export(api.reviewer, "md")
    assert response.status_code == 200
    assert fired and any("audit_events" in s for s in fired)
    for statement in fired:
        assert "review_stage_results" not in statement
        assert "review_plan_questions" not in statement


def _is_export_report_read(statement: str) -> bool:
    """The rebuild's read of the report row outside a mutation (export or GET), not the
    ``FOR UPDATE`` read of a mutation and not the existence probe."""
    head = statement.lstrip()
    return head.startswith("SELECT reports.tenant_id") and "FOR UPDATE" not in head


def test_an_export_that_read_the_report_first_makes_a_racing_finalize_wait(api: Api) -> None:
    """Export reads the report row, then a finalize runs: the export must not combine the report
    row from before the finalize with the finalization row from after it (409, never 503)."""
    number, sha, _ = api.current()
    assert api.decide(api.approver, number, sha).status_code == 200
    finalizer = TestClient(api.app)
    body = {"revision_no": number, "content_sha256": sha}
    started: list[Future[Any]] = []
    with ThreadPoolExecutor(max_workers=1) as pool:

        def start_finalize() -> None:
            if started:
                return
            started.append(
                pool.submit(
                    finalizer.post,
                    api.base + "/finalize",
                    headers=api.second_approver[1],
                    json=body,
                )
            )
            wait_until_blocked_or_done(api.engine, started[0])

        with on_statement(api.engine, _is_export_report_read, start_finalize, after=True) as fired:
            exported = api.export(api.reviewer, "md")
        finalized = started[0].result(timeout=BARRIER_TIMEOUT)
    assert len(fired) == 1
    assert exported.status_code == 409  # the export saw the report before the finalize
    assert finalized.status_code == 200  # the finalize waited for the export, then committed
    assert api.export(api.reviewer, "md").status_code == 200
    assert [e.action for e in api.audit()] == ["approve", "finalize", "export"]


def test_an_export_racing_a_finalize_that_holds_the_report_waits_and_exports(api: Api) -> None:
    """A finalize holds the report row and has written its rows; an export arriving then waits
    for its commit and exports the finalized revision (200, never 503)."""
    number, sha, _ = api.current()
    assert api.decide(api.approver, number, sha).status_code == 200
    exporter = TestClient(api.app)
    started: list[Future[Any]] = []
    with ThreadPoolExecutor(max_workers=1) as pool:

        def start_export() -> None:
            if started:
                return
            started.append(
                pool.submit(
                    exporter.get,
                    api.base + "/export",
                    headers=api.reviewer[1],
                    params={"format": "md"},
                )
            )
            wait_until_blocked_or_done(api.engine, started[0])

        with on_statement(
            api.engine, lambda s: s.lstrip().startswith("INSERT INTO audit_events"), start_export
        ) as fired:
            finalized = api.finalize(api.second_approver, number, sha)
        exported = started[0].result(timeout=BARRIER_TIMEOUT)
    assert fired  # the finalize's audit row (the export's may follow after the hook is removed)
    assert finalized.status_code == 200
    assert exported.status_code == 200  # it waited for the finalize to commit
    assert [e.action for e in api.audit()] == ["approve", "finalize", "export"]


def test_an_export_whose_rendered_digest_differs_is_inconsistent_and_not_recorded(
    api: Api,
) -> None:
    api.finalized()
    before = len(api.audit())

    def lying_render(_i: ExportInput) -> ExportResult:
        return ExportResult(body=b"# body\n", media_type="text/markdown", export_sha256="0" * 64)

    factory: sessionmaker[Session] = sessionmaker(bind=api.engine)
    with pytest.raises(report_store.ReportRecordInconsistentError):
        report_store.export_report(
            factory, api.reviewer[0], api.report_id, export_format="md", render=lying_render
        )
    assert len(api.audit()) == before  # the export transaction rolled back


# --- audit and append-only history ---------------------------------------------------------------


def test_each_action_appends_one_audit_event_with_actor_revision_and_hash(api: Api) -> None:
    _, _, etag = api.current()
    assert api.revise(api.reviewer, etag).status_code == 201
    n2, sha2, etag2 = api.current()
    assert api.decide(api.approver, n2, sha2, "reject", "Needs more.").status_code == 200
    assert api.revise(api.reviewer, etag2, notes="Second pass.").status_code == 201
    n3, sha3, _ = api.current()
    assert api.decide(api.approver, n3, sha3).status_code == 200
    assert api.finalize(api.second_approver, n3, sha3).status_code == 200
    body = api.export(api.reviewer, "json").content
    events = api.audit()
    assert [(e.action, e.actor_id, e.revision_no, e.content_sha256) for e in events] == [
        ("revise", api.reviewer[0].actor_id, 2, sha2),
        ("reject", api.approver[0].actor_id, 2, sha2),
        ("revise", api.reviewer[0].actor_id, 3, sha3),
        ("approve", api.approver[0].actor_id, 3, sha3),
        ("finalize", api.second_approver[0].actor_id, 3, sha3),
        ("export", api.reviewer[0].actor_id, 3, sha3),
    ]
    assert all(e.tenant_id == api.world.actor.tenant_id for e in events)
    assert all(e.report_id == api.report_id for e in events)
    assert [(e.export_format, e.export_sha256) for e in events[:-1]] == [(None, None)] * 5
    assert events[-1].export_format == "json"
    assert events[-1].export_sha256 == hashlib.sha256(body).hexdigest()


def test_history_and_audit_rows_reject_update_delete_and_truncate(api: Api) -> None:
    api.finalized()
    assert api.export(api.reviewer, "md").status_code == 200
    statements: list[str] = []
    for table in HISTORY_TABLES:
        statements += [
            f"UPDATE {table} SET tenant_id = tenant_id",
            f"DELETE FROM {table}",
            f"TRUNCATE {table} CASCADE",
        ]
    statements += ["DELETE FROM reports", "TRUNCATE reports CASCADE"]
    for statement in statements:
        with pytest.raises(DBAPIError) as raised, api.engine.begin() as connection:
            connection.execute(text(statement))
        assert _sqlstate(raised.value) == RESTRICT_VIOLATION, statement
    for table in (*HISTORY_TABLES, "reports"):
        assert api.count(table) >= 1, table
    with api.engine.begin() as connection:  # the report row itself is mutable (status, pointers)
        connection.execute(text("UPDATE reports SET updated_at = updated_at"))


# --- migration -----------------------------------------------------------------------------------


def test_migration_0009_downgrades_upgrades_and_matches_the_models(
    migrated: Engine, config: Config
) -> None:
    def names(sql: str) -> set[str]:
        with migrated.connect() as connection:
            return set(connection.execute(text(sql)).scalars())

    def tables() -> set[str]:
        return names("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")

    def triggers() -> set[str]:
        return names("SELECT tgname FROM pg_trigger WHERE NOT tgisinternal")

    def functions() -> set[str]:
        return names(
            "SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'public' AND p.proname LIKE 'eg_%'"
        )

    new_tables = {"reports", *HISTORY_TABLES}
    unique = "uq_review_outputs_tenant_id_review_id_wrapper_sha256"
    assert new_tables <= tables()
    assert len(triggers()) == 10 and functions() == {"eg_reject_append_only_change"}
    with migrated.connect() as connection:
        config_row = connection.execute(
            text(
                "SELECT p.proconfig, p.prosecdef FROM pg_proc p "
                "WHERE p.proname = 'eg_reject_append_only_change'"
            )
        ).one()
    assert config_row.proconfig == ["search_path=pg_catalog, pg_temp"]
    assert config_row.prosecdef is False  # SECURITY INVOKER
    assert unique in names("SELECT conname FROM pg_constraint")
    try:
        command.downgrade(config, "0008")
        assert not new_tables & tables() and "review_outputs" in tables()
        assert triggers() == set() and functions() == set()
        assert unique not in names("SELECT conname FROM pg_constraint")
        command.upgrade(config, "0009")
        assert new_tables <= tables() and len(triggers()) == 10
    finally:
        command.upgrade(config, "head")
    command.check(config)  # raises AutogenerateDiffsDetected on any difference
