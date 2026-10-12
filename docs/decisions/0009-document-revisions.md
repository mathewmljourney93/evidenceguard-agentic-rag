# ADR-0009: Documents, revisions and fenced activation

- **Status:** Implemented on local branch `feat/document-revisions` (Prompt 69), staged and uncommitted, **under review**. PostgreSQL verification is **pending** authorized publication and CI; no database was contacted locally.
- **Date:** 2026-10-12
- **Builds on:**
  - [ADR-0004](0004-persistence-foundation.md): tenant-safe composite references, naming conventions and migration policy;
  - [ADR-0007](0007-durable-job-core.md): the fence, its 5 s `lock_timeout`, database time and the `holds_lease` rule, all unchanged;
  - [ADR-0008](0008-worker-runtime.md): `ctx.fenced(finish=True)`, commit-state handling and `PermanentJobError`, all unchanged;
  - the M3c specification in [docs/plan.md](../plan.md), accepted at review (Prompts 66–68 in [prompts.md](../../prompts.md)).

## Context

M3d's ingestion handler needs revisions to process and a safe way to make one revision active. M3c adds the documents and revisions, their lifecycle and fenced activation, with no parser, chunker, handler, upload, endpoint, storage service, dependency or Docker change.

## Decisions

### Modules
- `evidenceguard_domain.revisions`: content validation, immutable snapshots and the pure lifecycle rules. No I/O.
- `evidenceguard_persistence.documents`: tenant-scoped creation and the fenced transitions.
- `evidenceguard_persistence.jobs.recheck_ownership`: a new read-only helper. It re-reads the job row, already locked by the fence, with a fresh `clock_timestamp()` and applies M3a's unchanged `holds_lease` rule. It returns the job and that time. It does not check the tenant: the token carries none, so the caller does.

### Schema (migration `0003`)
- **`documents`:**
  - `(tenant_id, vendor_id)` references `vendors (tenant_id, id)`;
  - unique `(tenant_id, vendor_id, document_key)` and `(tenant_id, id)`;
  - `latest_revision_no` is the allocation counter;
  - `active_revision_id` with `fk_documents_active_revision`: `(tenant_id, id, active_revision_id)` references `document_revisions (tenant_id, document_id, id)`, so the pointer can only name a revision of the same tenant and document.
- **`document_revisions`:**
  - `(tenant_id, document_id)` references `documents (tenant_id, id)`;
  - unique `(tenant_id, id)`, `(tenant_id, document_id, revision_no)`, `(tenant_id, document_id, sha256)` and `(tenant_id, document_id, id)`;
  - `fk_document_revisions_superseded_by`: `(tenant_id, document_id, superseded_by_revision_id)` references the same table's `(tenant_id, document_id, id)`.
- **Named CHECKs** for key, title, source type, authenticity, counter, status, number, label, failure-code *pattern*, `sha256` (64 lowercase hex characters, stored as `varchar(64)`), media type and size. Status/field pairs (`failed` ⇔ reason and time; `superseded` ⇔ time and successor; `active` ⇒ `activated_at`; no `activated_at` before settlement; no self-succession) reject partially filled pairs.
- **One active revision per document:** the partial unique index `uq_document_revisions_one_active` on `(tenant_id, document_id) WHERE status = 'active'`.
- **Circular references:** the upgrade creates `documents` without its pointer constraint, then `document_revisions`, the partial index, and finally adds `fk_documents_active_revision`. The downgrade drops that constraint first, then the index and the tables in reverse order. The migration spells constraint text literally; offline-rendering tests compare it with the model.
- **Database checks versus application validation:** the failure-code CHECK enforces only the fixed-code pattern (`^[a-z][a-z0-9_]{0,63}$`), so a well-formed code outside `RevisionFailureCode` (for example `parser_crashed`) is accepted by PostgreSQL. Restricting codes to the enum is application validation (`fail` and `RevisionSnapshot`); M3d adds codes with review without a schema change.
- **No triggers.** The database enforces the per-row and cross-row rules above. These remain **application invariants**: revision numbers are consecutive, the pointer names the `active` revision, `superseded_by` names a later active successor, and only the lifecycle functions change status.

### Content
- `RevisionContent` is built only by `from_bytes(data, media_type)`, which decodes strict UTF-8, rejects empty input and NUL, and computes `sha256` and `byte_size` from those exact bytes. There is no newline, BOM, whitespace or Unicode normalization. `from_stored` re-encodes stored text and verifies the hash and size again.
- The class is not a pydantic model, and `RevisionSnapshot`/`DocumentSnapshot` turn off the domain models' default whitespace stripping. Titles and labels are validated but never rewritten.
- `repr`, errors and validation messages are fixed and never include content. Snapshots carry no content; the persistence module's revision reads exclude `content_text`. No API reads content yet.

### Creation (`create_revision`)
- Caller-owned `Session`; it never commits, so a revision and its future ingestion job commit or roll back together (M3e).
- The tenant comes only from the actor. Reviewers and approvers may create; other roles get `PermissionDeniedError`. Role, validation and type checks happen before any SQL.
- The vendor is checked in the actor's tenant. The document row is inserted with `ON CONFLICT DO NOTHING` and then locked `FOR UPDATE` by its key, so every creation for that document is serialized. Under that lock: a title or source-type difference raises `DocumentConflictError`; identical bytes (same `sha256`) return the existing revision, whatever its status, including `failed`, but a different media type, size, label or effective date raises `RevisionConflictError`; otherwise the counter advances and a `pending` revision is inserted.
- The document lock has no explicit `lock_timeout` here, because the transaction belongs to the caller (M3e's request transaction); a unique violation that slips past the lock is mapped to the fixed `RevisionCreateRaceError`.

### Fenced transitions
`start_processing`, `fail_revision` and `activate_revision` take the fence's `FencedSession` and `JobSnapshot`. They never commit, roll back or issue transaction-control SQL. Each one:
1. reads the revision's immutable `document_id` from the job's tenant and `revision_id` payload, without a lock (missing → `RevisionNotFoundError`);
2. locks the document, then the revision rows in ascending ID order (job → document → revisions; activation also locks the active revision);
3. uses only the data re-read by those locking statements;
4. calls `recheck_ownership` and requires the re-read job's tenant and the document's tenant to equal the job snapshot's tenant, raising `LeaseLostError` before any write;
5. applies the pure rule with the fresh time and writes only if something changed.

A lock wait beyond the fence's `lock_timeout` (SQLSTATE `55P03`) raises the existing `JobLockTimeoutError`.

**Activation** compares the target with the currently **active** revision, not the latest uploaded one. A newer target writes, in order: the old active revision's demotion, the target's promotion, then the pointer. The partial index is checked per statement, so this order never has two active rows, and the intermediate state is never committed. An older target finishing late becomes `superseded` by the active revision and writes only its own row. A duplicate activation (`active` or `superseded` already) writes nothing, not even timestamps. Before any no-op or transition, `settle` refuses with `InconsistentDocumentStateError` any combination the locked rows could not legitimately form: an active snapshot without a matching pointer (or a pointer without one), an active snapshot that is not the pointed-to `active` revision of the same tenant and document, an `active` target that is not that revision, a `processing` target sharing the active revision's ID or number, or a revision number above `latest_revision_no`. Activation timestamps use the re-check's fresh time; creation's `updated_at` uses transaction time.

**Commit:** activation and job success commit together through `ctx.fenced(finish=True)`. A commit whose acknowledgment fails is `uncertain`, not proof of rollback: if it committed, the job is `succeeded` and never reclaimed; if it did not, the job is retried or reclaimed and activation runs again.

### Failure seam
`RevisionFailureCode` (`ingestion_failed`) is separate from `JobErrorCode`, and `fail_revision` refuses anything else. The future handler commits `fail_revision(INGESTION_FAILED)` in a fenced block that does not raise, then raises `PermanentJobError(JobErrorCode.PERMANENT_FAILURE)` outside it. Those are **two commits**: a crash between them leaves a failed revision and a job that is later reclaimed. On reclaim, the handler sees the revision already `failed` and fails the job again without rewriting the revision (repeating `fail` with the same code is also a no-op).

## Consequences and limits
- The checks run at explicit points, not atomically with every statement: a transaction that passes the re-check just before expiry may commit shortly after (the M3a limit).
- **Dead jobs:** a job can become `dead` while its revision stays `pending` or `processing`. M3c adds no reconciliation; reconciliation or a truthful projection is a **required M3d/M3e item before overall M3 acceptance**.
- Failed content cannot be retried with identical bytes in v1.
- There is no production ingestion handler, endpoint, upload or job-kind check yet; tests use test-only handlers.
- **Verification:** unit tests and a scripted database double cover the content rules, lifecycle table, statement scoping, lock order, the fresh re-check, write order and both uncertain-commit cases. The PostgreSQL integration tests (constraints, migration step, concurrency, lock waits and timeouts, rollback and worker integration) have **not run**: they are pending publication and CI. Compiled SQL and the double are not database verification.
