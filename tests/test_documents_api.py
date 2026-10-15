"""Document endpoints without a database: injected authenticator and in-memory store doubles.

Uploads are also driven through a raw ASGI ``receive`` that counts its calls, so the tests can
show that no body byte is read before authentication, the role check and the vendor lookup, and
can present controlled streams (length mismatches, disconnects) that an HTTP client cannot.
"""

import asyncio
import contextlib
import json
import logging
from collections.abc import Iterator, MutableMapping
from dataclasses import replace
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from evidenceguard_api.app import create_app
from evidenceguard_api.uploads import ParsedUpload
from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_domain.evidence import SourceType
from evidenceguard_domain.ingestion import IngestionState
from evidenceguard_domain.jobs import JobErrorCode, JobIdempotencyConflictError, JobStatus
from evidenceguard_domain.revisions import MediaType, RevisionStatus
from evidenceguard_observability.jsonlog import JsonFormatter
from evidenceguard_persistence.credentials import generate_api_key
from evidenceguard_persistence.document_views import (
    ChunkPageRecord,
    ChunkRecord,
    ChunkSetRecord,
    DocumentDetailRecord,
    DocumentPageRecord,
    DocumentRecord,
    JobSummaryRecord,
    JobViewRecord,
    RevisionPageRecord,
    RevisionRecord,
    UploadRecord,
)
from evidenceguard_persistence.documents import (
    DocumentConflictError,
    RevisionConflictError,
    RevisionCreateRaceError,
    VendorNotFoundError,
)
from evidenceguard_persistence.jobs import JobEnqueueRaceError
from evidenceguard_persistence.settings import DatabaseConfigurationError

PROBLEM = "application/problem+json"
SUBMITTED_MARKER = "submitted-marker-value"
FAILURE_MARKER = "fake-internal-failure-marker"
BOUNDARY = "eg-api-test-boundary"
TENANT_A, TENANT_B = uuid4(), uuid4()
NOW = datetime(2026, 10, 15, 9, 30, tzinfo=UTC)


# --- records -------------------------------------------------------------------------------------


def job_summary(status: JobStatus = JobStatus.QUEUED) -> JobSummaryRecord:
    running = status is JobStatus.RUNNING
    return JobSummaryRecord(
        id=uuid4(),
        status=status,
        attempt=1 if running else 0,
        max_attempts=3,
        lease_expires_at=NOW if running else None,
        lease_expired=True if running else None,
    )


def revision(
    revision_no: int = 1, status: RevisionStatus = RevisionStatus.ACTIVE
) -> RevisionRecord:
    return RevisionRecord(
        id=uuid4(),
        revision_no=revision_no,
        version_label="v1",
        effective_date=date(2026, 9, 30),
        media_type=MediaType.TEXT_MARKDOWN,
        byte_size=42,
        sha256="ab" * 32,
        status=status,
        failure_reason=None,
        activated_at=NOW,
        failed_at=None,
        superseded_at=None,
        superseded_by_revision_id=None,
        created_at=NOW,
        updated_at=NOW,
        ingestion_state=IngestionState.ACTIVE,
        ingestion_job=job_summary(JobStatus.SUCCEEDED),
    )


def document(vendor_id: UUID, key: str = "security-policy") -> DocumentRecord:
    return DocumentRecord(
        id=uuid4(),
        vendor_id=vendor_id,
        document_key=key,
        title="Security policy",
        source_type=SourceType.VENDOR_STATEMENT,
        authenticity="not_established",
        latest_revision_no=1,
        active_revision_id=None,
        created_at=NOW,
        updated_at=NOW,
    )


def chunk(ordinal: int, *, header: bool) -> ChunkRecord:
    return ChunkRecord(
        id=uuid4(),
        ordinal=ordinal,
        text="| a | b |\n| 1 | 2 |" if header else "Data is encrypted at rest.",
        content_sha256="cd" * 32,
        section_path=("Security", "Encryption"),
        is_table=header,
        line_start=10,
        line_end=12,
        char_start=100,
        char_end=140,
        header_line_start=1 if header else None,
        header_line_end=2 if header else None,
        header_char_start=0 if header else None,
        header_char_end=20 if header else None,
    )


def job_view(status: JobStatus = JobStatus.RUNNING) -> JobViewRecord:
    running = status is JobStatus.RUNNING
    return JobViewRecord(
        id=uuid4(),
        kind="ingest_revision",
        status=status,
        attempt=1,
        max_attempts=3,
        run_after=NOW,
        last_error=None if running else JobErrorCode.PERMANENT_FAILURE,
        lease_expires_at=NOW if running else None,
        lease_expired=False if running else None,
        created_at=NOW,
        updated_at=NOW,
        finished_at=None if running else NOW,
    )


# --- doubles -------------------------------------------------------------------------------------


class FakeAuthenticator:
    def __init__(self) -> None:
        self.known: dict[str, ActorContext] = {}

    def add(self, actor: ActorContext) -> str:
        key = generate_api_key().plaintext.get_secret_value()
        self.known[key] = actor
        return key

    def __call__(self, credential: str) -> ActorContext | None:
        return self.known.get(credential)


class FakeDocumentStore:
    """Tenant-scoped like the database store; records each call with the actor's tenant."""

    def __init__(self) -> None:
        self.vendors: dict[UUID, set[UUID]] = {TENANT_A: set(), TENANT_B: set()}
        self.documents: dict[UUID, tuple[UUID, DocumentDetailRecord]] = {}
        self.revisions: dict[UUID, tuple[RevisionRecord, ...]] = {}
        self.chunks: dict[tuple[UUID, int], ChunkPageRecord] = {}
        self.jobs: dict[UUID, tuple[UUID, JobViewRecord]] = {}
        self.calls: list[tuple[str, UUID]] = []
        self.uploads: list[ParsedUpload] = []
        self.error: Exception | None = None
        self.upload_error: Exception | None = None
        self.next_upload: UploadRecord | None = None

    def _call(self, op: str, actor: ActorContext) -> None:
        self.calls.append((op, actor.tenant_id))
        if self.error is not None:
            raise self.error

    def ops(self) -> list[str]:
        return [op for op, _tenant in self.calls]

    def vendor_exists(self, actor: ActorContext, vendor_id: UUID) -> bool:
        self._call("vendor_exists", actor)
        return vendor_id in self.vendors[actor.tenant_id]

    def create_upload(
        self, actor: ActorContext, vendor_id: UUID, upload: ParsedUpload
    ) -> UploadRecord:
        self._call("create_upload", actor)
        self.uploads.append(upload)
        if self.upload_error is not None:
            raise self.upload_error
        assert self.next_upload is not None
        return self.next_upload

    def list_documents(
        self, actor: ActorContext, vendor_id: UUID, *, limit: int, offset: int
    ) -> DocumentPageRecord | None:
        self._call("list_documents", actor)
        if vendor_id not in self.vendors[actor.tenant_id]:
            return None
        items = [
            detail.document
            for tenant, detail in self.documents.values()
            if tenant == actor.tenant_id and detail.document.vendor_id == vendor_id
        ]
        return DocumentPageRecord(items=tuple(items[offset : offset + limit]), total=len(items))

    def _detail(self, actor: ActorContext, document_id: UUID) -> DocumentDetailRecord | None:
        tenant, detail = self.documents.get(document_id, (None, None))
        return detail if tenant == actor.tenant_id else None

    def get_document(self, actor: ActorContext, document_id: UUID) -> DocumentDetailRecord | None:
        self._call("get_document", actor)
        return self._detail(actor, document_id)

    def list_revisions(
        self, actor: ActorContext, document_id: UUID, *, limit: int, offset: int
    ) -> RevisionPageRecord | None:
        self._call("list_revisions", actor)
        if self._detail(actor, document_id) is None:
            return None
        items = self.revisions.get(document_id, ())
        return RevisionPageRecord(items=items[offset : offset + limit], total=len(items))

    def list_chunks(
        self, actor: ActorContext, document_id: UUID, revision_no: int, *, limit: int, offset: int
    ) -> ChunkPageRecord | None:
        self._call("list_chunks", actor)
        if self._detail(actor, document_id) is None:
            return None
        return self.chunks.get((document_id, revision_no))

    def get_job(self, actor: ActorContext, job_id: UUID) -> JobViewRecord | None:
        self._call("get_job", actor)
        tenant, job = self.jobs.get(job_id, (None, None))
        return job if tenant == actor.tenant_id else None


class Harness:
    def __init__(self) -> None:
        self.auth = FakeAuthenticator()
        self.store = FakeDocumentStore()
        self.keys = {
            (tenant, role): self.auth.add(
                ActorContext(tenant_id=tenant, actor_id=uuid4(), role=role)
            )
            for tenant in (TENANT_A, TENANT_B)
            for role in Role
        }
        self.vendor_id = uuid4()
        self.store.vendors[TENANT_A].add(self.vendor_id)
        self.app = create_app(authenticator=self.auth, document_store=self.store)

    def headers(self, tenant: UUID = TENANT_A, role: Role = Role.REVIEWER) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.keys[(tenant, role)]}"}

    def add_document(self, tenant: UUID = TENANT_A) -> DocumentDetailRecord:
        vendor = self.vendor_id if tenant == TENANT_A else uuid4()
        self.store.vendors[tenant].add(vendor)
        active = revision(1, RevisionStatus.ACTIVE)
        latest = revision(2, RevisionStatus.PROCESSING)
        latest = replace(
            latest,
            ingestion_state=IngestionState.IN_PROGRESS,
            ingestion_job=job_summary(JobStatus.RUNNING),
            activated_at=None,
        )
        doc = replace(document(vendor), latest_revision_no=2, active_revision_id=active.id)
        detail = DocumentDetailRecord(document=doc, active_revision=active, latest_revision=latest)
        self.store.documents[doc.id] = (tenant, detail)
        self.store.revisions[doc.id] = (latest, active)
        return detail


@pytest.fixture
def harness() -> Harness:
    return Harness()


@pytest.fixture
def client(harness: Harness) -> Iterator[TestClient]:
    with TestClient(harness.app, raise_server_exceptions=False) as test_client:
        yield test_client


# --- multipart bodies ----------------------------------------------------------------------------


def part(
    name: str, value: bytes, *, filename: str | None = None, ctype: str | None = None
) -> bytes:
    disposition = f'Content-Disposition: form-data; name="{name}"'
    if filename is not None:
        disposition += f'; filename="{filename}"'
    head = disposition + (f"\r\nContent-Type: {ctype}" if ctype else "")
    return f"--{BOUNDARY}\r\n{head}\r\n\r\n".encode() + value + b"\r\n"


def upload_body(
    file: bytes = b"# Policy\n\nData is encrypted at rest.\n", **fields: bytes
) -> bytes:
    values = {
        "document_key": b"security-policy",
        "title": b"Security policy",
        "source_type": b"vendor_statement",
        **fields,
    }
    parts = b"".join(part(name, value) for name, value in values.items())
    file_part = part("file", file, filename="policy.md", ctype="text/markdown")
    return parts + file_part + f"--{BOUNDARY}--\r\n".encode()


MULTIPART = {"Content-Type": f"multipart/form-data; boundary={BOUNDARY}"}


def upload_record(created: bool = True, **changes: Any) -> UploadRecord:
    record = UploadRecord(
        created=created,
        document_id=uuid4(),
        revision_id=uuid4(),
        revision_no=1,
        revision_status=RevisionStatus.PENDING,
        ingestion_state=IngestionState.QUEUED,
        job=job_summary(JobStatus.QUEUED),
    )
    return replace(record, **changes)


def post(client: TestClient, harness: Harness, body: bytes, **kwargs: Any) -> Any:
    headers = {**harness.headers(kwargs.pop("tenant", TENANT_A), kwargs.pop("role", Role.REVIEWER))}
    headers.update(kwargs.pop("headers", MULTIPART))
    vendor = kwargs.pop("vendor_id", harness.vendor_id)
    return client.post(f"/v1/vendors/{vendor}/documents", content=body, headers=headers, **kwargs)


def assert_problem(response: Any, status: int) -> dict[str, Any]:
    assert response.status_code == status
    assert response.headers["content-type"] == PROBLEM
    body: dict[str, Any] = response.json()
    assert body["status"] == status
    assert body["request_id"] == response.headers["X-Request-ID"]
    return body


# --- raw ASGI driver -----------------------------------------------------------------------------


class Exchange:
    def __init__(self) -> None:
        self.receive_calls = 0
        self.status: int | None = None
        self.body = b""


def asgi_post(
    harness: Harness,
    messages: list[dict[str, Any]],
    headers: dict[str, str],
    *,
    vendor_id: UUID | None = None,
) -> Exchange:
    exchange = Exchange()
    path = f"/v1/vendors/{vendor_id or harness.vendor_id}/documents"
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "query_string": b"",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }
    pending = list(messages)

    async def receive() -> MutableMapping[str, Any]:
        exchange.receive_calls += 1
        return pending.pop(0) if pending else {"type": "http.disconnect"}

    async def send(message: MutableMapping[str, Any]) -> None:
        if message["type"] == "http.response.start":
            exchange.status = message["status"]
        elif message["type"] == "http.response.body":
            exchange.body += message.get("body", b"")

    # An unhandled error is re-raised after the generic 500 was sent.
    with contextlib.suppress(Exception):
        asyncio.run(harness.app(scope, receive, send))
    return exchange


def chunks_of(body: bytes, size: int) -> list[dict[str, Any]]:
    pieces = [body[i : i + size] for i in range(0, len(body), size)] or [b""]
    return [
        {"type": "http.request", "body": piece, "more_body": index < len(pieces) - 1}
        for index, piece in enumerate(pieces)
    ]


# --- authorization and body-read ordering --------------------------------------------------------


@pytest.mark.parametrize("role", [Role.REVIEWER, Role.APPROVER])
def test_reviewers_and_approvers_can_upload_and_read(
    client: TestClient, harness: Harness, role: Role
) -> None:
    harness.store.next_upload = upload_record()
    assert post(client, harness, upload_body(), role=role).status_code == 202
    detail = harness.add_document()
    for path in (
        f"/v1/vendors/{harness.vendor_id}/documents",
        f"/v1/documents/{detail.document.id}",
        f"/v1/documents/{detail.document.id}/revisions",
    ):
        assert client.get(path, headers=harness.headers(role=role)).status_code == 200


def test_admin_gets_a_generic_403_everywhere(client: TestClient, harness: Harness) -> None:
    detail = harness.add_document()
    admin = harness.headers(role=Role.ADMIN)
    paths = [
        f"/v1/vendors/{harness.vendor_id}/documents",
        f"/v1/documents/{detail.document.id}",
        f"/v1/documents/{detail.document.id}/revisions",
        f"/v1/documents/{detail.document.id}/revisions/1/chunks",
        f"/v1/jobs/{uuid4()}",
    ]
    for path in paths:
        assert_problem(client.get(path, headers=admin), 403)
    assert_problem(post(client, harness, upload_body(), role=Role.ADMIN), 403)
    assert harness.store.calls == []


@pytest.mark.parametrize(
    "auth",
    [{}, {"Authorization": "Bearer egk_unknown_000000"}, {"Authorization": "Basic abc"}],
)
def test_401_and_403_never_read_the_body(harness: Harness, auth: dict[str, str]) -> None:
    for headers in (auth, harness.headers(role=Role.ADMIN)):
        exchange = asgi_post(harness, chunks_of(upload_body(), 64), {**MULTIPART, **headers})
        assert exchange.status in (401, 403)
        assert exchange.receive_calls == 0
    assert harness.store.calls == []


def test_a_foreign_or_missing_vendor_is_404_before_the_body(harness: Harness) -> None:
    foreign = uuid4()
    harness.store.vendors[TENANT_B].add(foreign)
    for vendor in (foreign, uuid4()):
        exchange = asgi_post(
            harness,
            chunks_of(upload_body(), 64),
            {**MULTIPART, **harness.headers()},
            vendor_id=vendor,
        )
        assert exchange.status == 404
        assert exchange.receive_calls == 0
    assert harness.store.ops() == ["vendor_exists", "vendor_exists"]


def test_a_malformed_vendor_id_is_422(client: TestClient, harness: Harness) -> None:
    response = post(client, harness, upload_body(), vendor_id="not-a-uuid")
    body = assert_problem(response, 422)
    assert body["errors"] == [{"loc": ["path", "vendor_id"], "type": "uuid_parsing"}]


# --- upload results ------------------------------------------------------------------------------


def test_a_new_revision_is_202_with_the_observed_state(
    client: TestClient, harness: Harness
) -> None:
    record = upload_record()
    harness.store.next_upload = record
    response = post(client, harness, upload_body(version_label=b"v1", effective_date=b"2026-09-30"))

    assert response.status_code == 202
    body = response.json()
    assert set(body) == {
        "created",
        "document_id",
        "revision_id",
        "revision_no",
        "revision_status",
        "ingestion_state",
        "job",
    }
    assert body["created"] is True
    assert body["revision_id"] == str(record.revision_id)
    assert (body["revision_status"], body["ingestion_state"]) == ("pending", "queued")
    assert set(body["job"]) == {
        "id",
        "status",
        "attempt",
        "max_attempts",
        "lease_expires_at",
        "lease_expired",
    }
    parsed = harness.store.uploads[0]
    assert (parsed.document_key, parsed.version_label) == ("security-policy", "v1")
    assert parsed.effective_date == date(2026, 9, 30)
    assert harness.store.ops() == ["vendor_exists", "create_upload"]


@pytest.mark.parametrize(
    ("status", "state", "job"),
    [
        (RevisionStatus.PROCESSING, IngestionState.IN_PROGRESS, job_summary(JobStatus.RUNNING)),
        (RevisionStatus.PENDING, IngestionState.STALLED, job_summary(JobStatus.DEAD)),
        (RevisionStatus.ACTIVE, IngestionState.ACTIVE, job_summary(JobStatus.SUCCEEDED)),
        (RevisionStatus.SUPERSEDED, IngestionState.SUPERSEDED, None),
        (RevisionStatus.FAILED, IngestionState.FAILED, job_summary(JobStatus.SUCCEEDED)),
    ],
)
def test_a_duplicate_is_200_with_the_existing_state(
    client: TestClient,
    harness: Harness,
    status: RevisionStatus,
    state: IngestionState,
    job: JobSummaryRecord | None,
) -> None:
    harness.store.next_upload = upload_record(
        created=False, revision_status=status, ingestion_state=state, job=job
    )
    response = post(client, harness, upload_body())
    assert response.status_code == 200
    body = response.json()
    assert (body["created"], body["revision_status"], body["ingestion_state"]) == (
        False,
        status.value,
        state.value,
    )
    assert (body["job"] is None) == (job is None)
    if job is not None and job.status is JobStatus.RUNNING:
        assert body["job"]["lease_expired"] is True


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (DocumentConflictError(), 409),
        (RevisionConflictError(), 409),
        (VendorNotFoundError(), 404),
        (RevisionCreateRaceError(), 503),
        (JobEnqueueRaceError(), 503),
        (OperationalError(FAILURE_MARKER, {}, Exception(FAILURE_MARKER)), 503),
        (DatabaseConfigurationError(FAILURE_MARKER), 503),
    ],
)
def test_creation_errors_are_generic(
    client: TestClient, harness: Harness, error: Exception, status: int
) -> None:
    harness.store.upload_error = error
    response = post(client, harness, upload_body())
    body = assert_problem(response, status)
    assert FAILURE_MARKER not in response.text
    assert "errors" not in body


def test_a_corrupted_canonical_job_is_a_500_with_a_fixed_event(
    client: TestClient, harness: Harness, caplog: pytest.LogCaptureFixture
) -> None:
    harness.store.upload_error = JobIdempotencyConflictError()
    with caplog.at_level(logging.INFO):
        response = post(client, harness, upload_body())
    assert_problem(response, 500)
    assert FAILURE_MARKER not in response.text
    rendered = [json.loads(JsonFormatter().format(r)) for r in caplog.records]
    assert [r for r in rendered if r["event"] == "document.upload_inconsistent"]
    assert all(FAILURE_MARKER not in json.dumps(r) for r in rendered)


# --- rejected bodies: no creation call -----------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "headers", "status"),
    [
        (upload_body(), {"Content-Type": "application/json"}, 415),
        (upload_body(), {"Content-Type": "multipart/form-data"}, 415),
        (upload_body(tenant_id=str(TENANT_B).encode()), MULTIPART, 422),
        (upload_body(role=b"admin"), MULTIPART, 422),
        (upload_body(title=b"T" * 2000), MULTIPART, 413),
        (upload_body(file=b"a" * (2_097_152 + 1)), MULTIPART, 413),
        (upload_body(file=b""), MULTIPART, 422),
        (upload_body(file=b"a\x00b"), MULTIPART, 422),
        (upload_body()[:-10], MULTIPART, 422),
        (b"", MULTIPART, 422),
    ],
    ids=[
        "json",
        "no boundary",
        "tenant field",
        "role field",
        "long title",
        "large file",
        "empty file",
        "nul",
        "truncated",
        "empty body",
    ],
)
def test_rejected_bodies_never_reach_creation(
    client: TestClient, harness: Harness, body: bytes, headers: dict[str, str], status: int
) -> None:
    response = post(client, harness, body, headers=headers)
    assert_problem(response, status)
    assert harness.store.ops() == ["vendor_exists"]


def test_multipart_422s_use_allowlisted_locations(client: TestClient, harness: Harness) -> None:
    unknown = assert_problem(post(client, harness, upload_body(**{SUBMITTED_MARKER: b"x"})), 422)
    assert unknown["errors"] == [{"loc": ["body"], "type": "extra_forbidden"}]
    value = assert_problem(post(client, harness, upload_body(document_key=b"Bad Key")), 422)
    assert value["errors"] == [{"loc": ["body", "document_key"], "type": "value_error"}]


def test_whitespace_only_content_is_accepted(client: TestClient, harness: Harness) -> None:
    harness.store.next_upload = upload_record()
    assert post(client, harness, upload_body(file=b"  \n\t\n")).status_code == 202
    assert harness.store.uploads[0].content.text == "  \n\t\n"


def test_large_declared_length_is_413_without_reading(harness: Harness) -> None:
    headers = {**MULTIPART, **harness.headers(), "Content-Length": str(2_162_688 + 1)}
    exchange = asgi_post(harness, chunks_of(upload_body(), 64), headers)
    assert (exchange.status, exchange.receive_calls) == (413, 0)


def test_chunked_upload_over_the_total_cap_stops_reading(harness: Harness) -> None:
    body = upload_body() + b"x" * (3 * 2_162_688)  # oversized epilogue, no Content-Length
    messages = chunks_of(body, 65_536)
    exchange = asgi_post(harness, messages, {**MULTIPART, **harness.headers()})
    assert exchange.status == 413
    assert exchange.receive_calls < len(messages)
    assert harness.store.ops() == ["vendor_exists"]


@pytest.mark.parametrize("delta", [-5, 5])
def test_content_length_mismatch_on_a_completed_stream_is_400(harness: Harness, delta: int) -> None:
    body = upload_body()
    headers = {**MULTIPART, **harness.headers(), "Content-Length": str(len(body) + delta)}
    exchange = asgi_post(harness, chunks_of(body, 100), headers)
    assert exchange.status == 400
    assert harness.store.ops() == ["vendor_exists"]


def test_a_matching_content_length_is_accepted(harness: Harness) -> None:
    harness.store.next_upload = upload_record()
    body = upload_body()
    headers = {**MULTIPART, **harness.headers(), "Content-Length": str(len(body))}
    assert asgi_post(harness, chunks_of(body, 100), headers).status == 202


def test_a_client_disconnect_aborts_without_creation(harness: Harness) -> None:
    body = upload_body()
    messages: list[dict[str, Any]] = [
        {"type": "http.request", "body": body[:50], "more_body": True},
        {"type": "http.disconnect"},
    ]
    exchange = asgi_post(harness, messages, {**MULTIPART, **harness.headers()})
    assert exchange.status != 202
    assert harness.store.ops() == ["vendor_exists"]


@pytest.mark.parametrize("size", [1, 7, 4096, 1_000_000])
def test_mixed_faults_give_one_status_however_received(harness: Harness, size: int) -> None:
    close = f"--{BOUNDARY}--\r\n".encode()
    repeated = part("title", b"T") + part("title", b"Again") + part("extra", b"x") * 12 + close
    tail = part("document_key", b"k") + f"--{BOUNDARY}\r\nNo colon\r\n".encode() + b"t" * 2_200_000
    for body, expected in ((repeated, 422), (tail, 422)):
        if size == 1 and len(body) > 10_000:
            continue
        exchange = asgi_post(harness, chunks_of(body, size), {**MULTIPART, **harness.headers()})
        assert exchange.status == expected
    assert "create_upload" not in harness.store.ops()


def test_problem_bodies_and_logs_never_echo_submitted_values(
    client: TestClient, harness: Harness, caplog: pytest.LogCaptureFixture
) -> None:
    marker = SUBMITTED_MARKER.encode()
    bodies = [
        upload_body(**{SUBMITTED_MARKER: marker}),
        upload_body(title=marker + b"\xff"),
        upload_body(document_key=marker + b" !"),
        upload_body(effective_date=marker),
        upload_body(file=marker + b"\x00"),
        part("title", marker, filename=SUBMITTED_MARKER) + f"--{BOUNDARY}--\r\n".encode(),
        f"--{BOUNDARY}\r\n{SUBMITTED_MARKER}\r\n\r\n".encode(),
    ]
    with caplog.at_level(logging.DEBUG):
        for body in bodies:
            response = post(client, harness, body)
            assert response.status_code in (413, 415, 422)
            assert SUBMITTED_MARKER not in response.text
            assert "policy.md" not in response.text
    for record in caplog.records:
        assert SUBMITTED_MARKER not in record.getMessage()
        assert SUBMITTED_MARKER not in JsonFormatter().format(record)


def test_tenant_overrides_are_ignored(client: TestClient, harness: Harness) -> None:
    harness.store.next_upload = upload_record()
    headers = {**MULTIPART, "X-Tenant-ID": str(TENANT_B)}
    response = client.post(
        f"/v1/vendors/{harness.vendor_id}/documents?tenant_id={TENANT_B}",
        content=upload_body(),
        headers={**harness.headers(), **headers},
    )
    assert response.status_code == 202
    assert {tenant for _op, tenant in harness.store.calls} == {TENANT_A}


# --- reads ---------------------------------------------------------------------------------------

DOCUMENT_FIELDS = {
    "id",
    "vendor_id",
    "document_key",
    "title",
    "source_type",
    "authenticity",
    "latest_revision_no",
    "active_revision_id",
    "created_at",
    "updated_at",
}
REVISION_FIELDS = {
    "id",
    "revision_no",
    "version_label",
    "effective_date",
    "media_type",
    "byte_size",
    "sha256",
    "status",
    "failure_reason",
    "activated_at",
    "failed_at",
    "superseded_at",
    "superseded_by_revision_id",
    "created_at",
    "updated_at",
    "ingestion_state",
    "ingestion_job",
}


def test_document_list_and_detail(client: TestClient, harness: Harness) -> None:
    detail = harness.add_document()
    listing = client.get(f"/v1/vendors/{harness.vendor_id}/documents", headers=harness.headers())
    assert listing.status_code == 200
    page = listing.json()
    assert (page["total"], page["limit"], page["offset"]) == (1, 20, 0)
    assert set(page["items"][0]) == DOCUMENT_FIELDS

    one = client.get(f"/v1/documents/{detail.document.id}", headers=harness.headers()).json()
    assert set(one) == DOCUMENT_FIELDS | {"active_revision", "latest_revision"}
    assert set(one["active_revision"]) == REVISION_FIELDS
    assert one["latest_revision"]["ingestion_state"] == "in_progress"
    assert one["latest_revision"]["ingestion_job"]["lease_expired"] is True
    assert one["active_revision"]["status"] == "active"


def test_revision_list(client: TestClient, harness: Harness) -> None:
    detail = harness.add_document()
    response = client.get(
        f"/v1/documents/{detail.document.id}/revisions?limit=1&offset=1", headers=harness.headers()
    )
    page = response.json()
    assert (page["total"], page["limit"], page["offset"]) == (2, 1, 1)
    assert [item["revision_no"] for item in page["items"]] == [1]
    assert set(page["items"][0]) == REVISION_FIELDS


def test_chunk_page_shapes(client: TestClient, harness: Harness) -> None:
    detail = harness.add_document()
    doc_id = detail.document.id
    harness.store.chunks[(doc_id, 1)] = ChunkPageRecord(
        chunk_set=ChunkSetRecord(
            chunker_version="v1", chunk_count=2, stored_count=2, verified_complete=True
        ),
        items=(chunk(0, header=False), chunk(1, header=True)),
        total=2,
    )
    harness.store.chunks[(doc_id, 2)] = ChunkPageRecord(chunk_set=None, items=(), total=0)

    page = client.get(
        f"/v1/documents/{doc_id}/revisions/1/chunks", headers=harness.headers()
    ).json()
    assert set(page) == {"chunk_set", "items", "total", "limit", "offset"}
    assert (page["limit"], page["offset"]) == (50, 0)
    assert page["chunk_set"]["verified_complete"] is True
    plain, table = page["items"]
    assert set(plain) == {
        "id",
        "ordinal",
        "text",
        "content_sha256",
        "section_path",
        "is_table",
        "source",
        "repeated_header",
        "contiguous",
    }
    assert (plain["contiguous"], plain["repeated_header"]) == (True, None)
    assert plain["text"] == "Data is encrypted at rest."
    assert plain["source"] == {"line_start": 10, "line_end": 12, "char_start": 100, "char_end": 140}
    assert table["contiguous"] is False
    assert table["repeated_header"] == {
        "line_start": 1,
        "line_end": 2,
        "char_start": 0,
        "char_end": 20,
    }

    empty = client.get(f"/v1/documents/{doc_id}/revisions/2/chunks", headers=harness.headers())
    assert empty.json()["chunk_set"] is None
    missing = client.get(f"/v1/documents/{doc_id}/revisions/9/chunks", headers=harness.headers())
    assert_problem(missing, 404)


def test_job_view_has_only_reviewed_fields(client: TestClient, harness: Harness) -> None:
    job = job_view(JobStatus.DEAD)
    harness.store.jobs[job.id] = (TENANT_A, job)
    body = client.get(f"/v1/jobs/{job.id}", headers=harness.headers()).json()
    assert set(body) == {
        "id",
        "kind",
        "status",
        "attempt",
        "max_attempts",
        "run_after",
        "last_error",
        "lease_expires_at",
        "lease_expired",
        "created_at",
        "updated_at",
        "finished_at",
    }
    assert (body["status"], body["last_error"], body["lease_expired"]) == (
        "dead",
        "permanent_failure",
        None,
    )


def test_foreign_and_missing_objects_are_identical_404s(
    client: TestClient, harness: Harness
) -> None:
    foreign = harness.add_document(TENANT_B)
    foreign_job = job_view()
    harness.store.jobs[foreign_job.id] = (TENANT_B, foreign_job)
    paths = []
    for document_id, job_id in ((foreign.document.id, foreign_job.id), (uuid4(), uuid4())):
        paths += [
            f"/v1/vendors/{foreign.document.vendor_id}/documents",
            f"/v1/documents/{document_id}",
            f"/v1/documents/{document_id}/revisions",
            f"/v1/documents/{document_id}/revisions/1/chunks",
            f"/v1/jobs/{job_id}",
        ]
    bodies = set()
    for path in paths:
        body = assert_problem(client.get(path, headers=harness.headers()), 404)
        bodies.add((body["title"], body["detail"]))
    assert len(bodies) == 1


@pytest.mark.parametrize(
    "path",
    [
        "/v1/vendors/{vendor}/documents?limit=0",
        "/v1/vendors/{vendor}/documents?limit=101",
        "/v1/vendors/{vendor}/documents?offset=10001",
        "/v1/documents/{doc}/revisions?offset=-1",
        "/v1/documents/{doc}/revisions/0/chunks",
        "/v1/documents/{doc}/revisions/2147483648/chunks",
        "/v1/documents/{doc}/revisions/1/chunks?limit=201",
        "/v1/documents/{doc}/revisions/1/chunks?offset=4096",
        "/v1/documents/not-a-uuid",
        "/v1/jobs/not-a-uuid",
    ],
)
def test_bounds_and_ids_are_validated(client: TestClient, harness: Harness, path: str) -> None:
    url = path.format(vendor=harness.vendor_id, doc=uuid4())
    body = assert_problem(client.get(url, headers=harness.headers()), 422)
    assert all(set(error) == {"loc", "type"} for error in body["errors"])
    assert harness.store.calls == []


@pytest.mark.parametrize(
    "error",
    [
        OperationalError(FAILURE_MARKER, {}, Exception(FAILURE_MARKER)),
        DatabaseConfigurationError("x"),
    ],
)
def test_read_database_failures_are_a_generic_503(
    client: TestClient, harness: Harness, error: Exception
) -> None:
    harness.store.error = error
    response = client.get(f"/v1/jobs/{uuid4()}", headers=harness.headers())
    assert_problem(response, 503)
    assert FAILURE_MARKER not in response.text
    upload = post(client, harness, upload_body())
    assert_problem(upload, 503)
