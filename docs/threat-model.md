# Threat model (initial draft, M1c)

**Status:** draft. This document grows with each milestone and must be complete before v0.1 ([plan](plan.md) correction F). It describes the planned system; most of it is **not implemented yet**.

## Scope and assets

EvidenceGuard helps a reviewer draft a vendor-risk report from uploaded vendor documents. The assets to protect are:
- each tenant's documents, evidence and reports;
- the integrity of report content and of the approval history;
- credentials (API keys, model-provider keys).

Only synthetic demonstration data is used.

## What is implemented and tested now (M1b)

These are **domain invariants** in `evidenceguard_domain`, enforced by validation and pure functions and covered by unit tests:

| Threat | Invariant |
|---|---|
| Evidence from one tenant appearing in another tenant's report | Citations, findings and report content must all carry the report's tenant ID; mixing tenants fails validation. |
| An actor acting on another tenant's report | Every transition checks that the actor's tenant matches the report's tenant. |
| Approving content that was never reviewed, or approving a stale revision | Approval names the exact current revision number and its SHA-256 content hash. Any mismatch is rejected. |
| Editing a report after approval and exporting it as approved | A new revision removes the effective approval. Finalization needs an approval of the exact current revision and hash. Only finalized reports are exportable. |
| Reusing an approval from another report, tenant or revision | Decisions are bound to tenant, report, revision and hash; the report aggregate rejects any decision that does not match. |
| Building an "approved" or "finalized" report object without a decision | The stored status must equal the status derived from the decision history. |
| Changing content after its hash was computed | Domain values are frozen and use tuples, not lists or dicts. `model_copy` re-validates. |
| Claiming support without evidence | Supported or conflicting statuses require citations; the status must match the cited source types. Conflicting evidence needs at least two distinct quotations. That is a structural check, not proof of a contradiction. |
| A report silently dropping a question it could not answer | Every question must be resolved by a finding or listed as unresolved. A vendor claim never resolves a question that requires documentary support. Any question named by a `missing` finding must be listed as unresolved, even if another finding supports it. |
| A rejection with no stated reason | Every rejection decision must carry a non-blank comment, including one built directly. |
| A retry quietly overwriting or discarding who decided what | Only an identical retry (same actor and comment) is idempotent, and it keeps the original decision and time. A changed request raises `DecisionConflictError` instead of being dropped or recorded twice. |
| Privilege escalation through an admin role | Only the approver role can approve, reject or finalize. The `admin` role (M2b) is in neither the report-editing nor the approval set, so it cannot draft, revise, approve, reject or finalize; tested. |

These invariants hold only for code that goes through the domain models and transitions. Pydantic's `model_construct` and `object.__setattr__` can bypass validation; domain code never uses them.

## API request handling (M1c, implemented and tested)

| Threat | Mitigation |
|---|---|
| Submitted values, credentials or quotations leaking into logs | Records rendered by the configured JSON formatter carry only a fixed event identifier (from a reviewed template table; message text and arguments are never formatted) and allowlisted fields: request ID, method, route template, status, duration and exception class. Uvicorn's access log is off. Handlers configured outside `logging_config()` are not covered. |
| Exception text or tracebacks leaking to clients or logs | Unexpected errors return a generic 500 problem. Logs record the exception class only, with no message and no traceback. |
| Validation errors echoing input | 422 problems list only `loc` and `type` for at most 20 errors. Values, messages and context are omitted. |
| `HTTPException.detail` echoing submitted values or internal text | Ordinary HTTP errors get a generic detail for their status class. A specific message must come from the reviewed `PublicMessage` catalogue through `PublicHTTPException`. |
| A client-chosen request ID being trusted | Only a single valid UUID is accepted, and it is used purely for correlation, never for identity or authorization. |
| Request context bleeding between concurrent requests | The request ID is held in a per-task `ContextVar`; tested with ten interleaved requests. |

The full design and limits are in [ADR-0002](decisions/0002-request-ids-logging-and-errors.md). A client-chosen extra field *name* can still appear, capped, in a 422 body.

## API-key authentication (M2b, verified in CI and on `main`)

| Threat | Mitigation |
|---|---|
| A client choosing its own tenant, user or role | The principal is derived only from the stored key, user and tenant rows (the key joined to its user on `tenant_id` and `user_id`). `/v1/me` takes no parameters; tenant headers and query values are ignored. Tested with spoofed headers and query parameters. |
| Stolen database contents revealing usable keys | Only the public prefix and the SHA-256 of a 256-bit random secret are stored. |
| Distinguishing why a credential failed | Missing, repeated, oversized, malformed, unknown, wrong-secret and revoked credentials all get the same 401 body and `WWW-Authenticate: Bearer`. An unknown prefix still performs a digest comparison. |
| Credentials leaking into logs, errors or representations | Keys are carried only in masked `SecretStr` wrappers. Request logs keep only allowlisted fields (tested against rendered and raw records). Errors never echo the header. `eg-admin` prints a new key once, to stdout, after commit, and never takes secrets as arguments. Its usage errors print only static usage and a fixed message, never the submitted arguments. |
| A revoked key or demoted user keeping access | No caching: each request reads the current revocation state and role. Tested with role changes and revocation. |
| Database or configuration errors leaking details | They return a generic 503 with no URL, exception text or credential. |

**Limits** (ADR-0005):
- **Possession is access:** there is no second factor, expiry, scopes or rotation schedule.
- **No rate limiting or lockout.**
- **Residual timing:** the database lookup can take different time for known and unknown prefixes; prefixes are not secret.
- **Transport:** keys are bearer tokens, so non-local deployments need TLS in front.
- **Verification:** at commit `b2f7f23` on `feat/api-key-authentication`, the [integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38166627885/job/114550418432) passed with all fifteen PostgreSQL tests (`15 passed, 377 deselected`). M2b was then fast-forwarded onto `main` at `277dfea`, where the [integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38167398488/job/114552700841) passed again (`15 passed, 377 deselected in 3.77s`). Compose has never been run.

## Tenant-scoped vendors and readiness (M2c, verified in CI and on `main`)

| Threat | Mitigation |
|---|---|
| Reading or creating another tenant's vendors | Every vendor query takes the authenticated `ActorContext` and filters by its tenant in SQL. A vendor is read by `(tenant_id, id)` together; the list and its count use the same filter. Create takes the tenant only from the key. Tested with spoofed headers, query parameters and body fields. |
| Learning that another tenant's vendor exists | A foreign ID and a nonexistent ID return the same generic 404. Duplicate slugs are checked only within the caller's tenant. |
| Supplying a tenant, actor or role in the body | `VendorCreate` accepts only `slug` and `name`; any other field is a 422. |
| Privilege use by administrators | Admin keys get a generic 403 on vendor routes. |
| Partial writes after a failure | Each operation is one transaction: commit before the response, rollback on any error (including commit failure), session always closed. Only the vendor slug unique constraint is reported as a 409. |
| Readiness leaking internals or changing the database | `/readyz` returns only fixed check names and states, never URLs, revisions, SQL or errors. It reads `alembic_version` in a rolled-back, time-limited transaction and never migrates or creates anything. |
| A slow or unreachable database tying up the API | Connection (5 s), pool (10 s) and readiness statement (2 s) timeouts. Database work runs in worker threads, not on the event loop. |

**Limits** (ADR-0006): offset pagination is not a snapshot; readiness checks connectivity and revisions only; `/readyz` is unauthenticated; the API-key limits above still apply.

**Verification:** at commit `a888b6c` on `feat/vendor-api-readiness`, the [integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38212619855/job/114689994147) passed with all twenty-one PostgreSQL tests, including M2c's six (`21 passed, 458 deselected in 4.65s`, from the log retrieved by the external reviewer). M2c was then fast-forwarded onto `main` at `9d5a93a`, where the [integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38214711868/job/114696647728) passed again (`21 passed, 458 deselected in 4.92s`). Compose has never been run.

## Durable job core (M3a, verified in CI and on `main`)

| Threat | Mitigation |
|---|---|
| Two workers processing one job | Claims take rows with `FOR UPDATE SKIP LOCKED` in one short transaction; a claimed row is running with one owner. |
| A stale worker writing after its job was reclaimed | Every effect and transition runs in a fenced transaction: lock the job row, then re-check the `(job, worker, attempt)` token and an unexpired lease with fresh `clock_timestamp()` in a separate statement. `attempt` grows on every claim, so even the same worker ID cannot reuse an old attempt. |
| A decision based on time read before a lock wait | Ownership is checked only after the lock is acquired, with database time read after the wait; worker clocks, `now()` and `CURRENT_TIMESTAMP` are never used for leases. |
| Committing partial handler work by accident | The fence owns its transaction: it commits only when its block finishes and rolls back on any uncaught error, including a failed commit. `FencedSession` omits `commit`, `rollback` and `close`, so ordinary session calls cannot end the transaction early. This guards against mistakes by trusted handler code; it is not a sandbox (see the limits below). |
| Tenant confusion in jobs | A job's tenant comes from the authenticated actor at enqueue; payloads may not carry tenant fields; `tenant_id` references `tenants`. |
| Data leakage through jobs | Payloads hold only identifier keys and canonical UUID strings (at most 4,096 canonical bytes, enforced by the application); `last_error` holds fixed codes only; errors carry fixed messages. |
| Exhausted jobs blocking the queue | A bounded `SKIP LOCKED` sweep marks them `dead`, and claim selection excludes them. |

**Limits** (ADR-0007): handlers are trusted code, and the fence assumes they preserve its transaction and lock. `execute` accepts arbitrary SQL and Python exposes the underlying objects, so a handler that issued transaction-control SQL, used the underlying connection or edited ownership fields could defeat the fence. A fenced transaction that passed its check just before expiry may commit shortly after the lease expires; the database enforces only that the payload is a JSON object, not the finer payload rules or the byte cap; at the M3a and M3b baselines the worker had no production handlers (M3d, on `main` since `cdf7260`, registers `ingest_revision`). Passing tests demonstrate the tested behaviour, not a general security or performance guarantee.

**Verification:** at commit `11350e1` on `feat/durable-job-core`, the [integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38240768344/job/114782517485) passed with all 63 PostgreSQL tests (`63 passed, 605 deselected in 16.58s`, from the log retrieved by the external reviewer). They include M3a's concurrent-claim, stale-worker, lease-fencing, lock-wait and lock-timeout tests. M3a was then fast-forwarded onto `main` at `b3f9845`, where the [integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38242144844/job/114787118281) passed again (`63 passed, 605 deselected in 16.17s`). The M3b worker is now on `main` (see below), and Compose has never been run.

## Worker runtime (M3b, verified in CI and on `main`)

| Threat | Mitigation |
|---|---|
| A stale worker recording an outcome after losing its lease | Outcomes are written only through the fence, after both job threads are confirmed stopped. Lease loss (a refused heartbeat, a refused fenced write, or a passed local deadline) is latched irreversibly and suppresses every outcome. |
| Two jobs, or a lingering thread and a new job, in one process | At most one handler runs at a time. After every bounded wait the runtime checks that the handler and heartbeat threads really stopped; otherwise it stops claiming for good and the CLI ends the process (exit 5). |
| A contradictory second outcome after an atomic finish | `committed` is published only after the transaction context exits successfully; afterwards no completion, retry or failure is attempted. A commit that raises is `uncertain`, is never reported as success, and any recovery stays fenced. |
| A heartbeat refusal caused by the job's own commit read as ownership theft | A refusal during a finish stays pending and is classified only once the finish resolves. |
| A late heartbeat reviving a cancelled attempt | Cancellation and lease loss cannot be cleared; a late renewal moves no deadline and permits no write. |
| Handler work after cancellation or lease loss was latched while a fence waited for its lock | Permission is checked again after the fence acquires its lock, and before an atomic finish records success; a failed check rolls the transaction back before the block runs or commits. |
| An unexpected supervisor failure leaving job threads behind | Cancellation is latched, heartbeats stop and the started threads are joined for a bounded time; no outcome is recorded and no further claim is made. A thread still alive makes the result abnormal, and the CLI exits 5 even if later cleanup fails. |
| Sessions shared across threads | Every M3a call opens its own session; a test records the thread that uses each session. |
| Leaking private values in worker logs | Fixed reviewed events only; the new fields are filled from validated identifiers and enums; no tenant IDs, payloads, idempotency keys, URLs, SQL, exception text or tracebacks. CLI usage and configuration errors print fixed messages. |
| An empty or misconfigured deployment polling forever | With no registered handlers `eg-worker` exits 4 before reading database settings; the claim filter means unhandled kinds stay queued for a capable worker. |

**Limits** (ADR-0008): execution is at least once, so durable effects must be fenced and idempotent, and effects outside the database can repeat. Cancellation is cooperative: Python cannot stop a running thread. `claim` and outcome recording are synchronous and there is no worker statement timeout, so there is **no total shutdown deadline** and a hung call may need external termination. Engine disposal does not cancel checked-out connections; PostgreSQL rolls back a dead worker's transaction only when it detects the disconnect. Reclaim can be delayed by a late heartbeat or a lingering transaction. Handlers are trusted code; the handler wrapper is not a sandbox. At the M3b baseline there were no production handlers.

**Verification:** at commit `bc5f638` on `feat/worker-runtime`, [CI run 38253962690](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38253962690) passed on [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38253962690/job/114827089007) (`709 passed, 77 skipped in 15.96s`) and [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38253962690/job/114827088937) (`708 passed, 78 skipped in 22.18s`). The [integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38253962690/job/114827089078) passed with all 77 PostgreSQL tests (`77 passed, 709 deselected in 19.63s`): M3a's 63 and the worker's 14, including lease loss before a fenced write, heartbeats racing atomic completion, and shutdown re-queueing. All counts are from logs retrieved by the external reviewer. M3b was then fast-forwarded onto `main` at `dd26c70`, where the [integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38255786860/job/114833375219) passed again (`77 passed, 709 deselected in 17.36s`). These results demonstrate the tested behaviour, not a general security or performance guarantee. At that baseline there were no production handlers, and Compose has never been run.

## Documents and revisions (M3c, verified in CI and on `main`)

Reviewed and verified in CI on branch `feat/document-revisions` at commit `8646b75`, then fast-forwarded onto `main` at `6f8ffde`, where CI passed again. The mitigations below were exercised by M3c's PostgreSQL integration tests: constraints, migration, concurrency, activation and lease loss.

| Threat | Mitigation |
|---|---|
| A document or revision linked across tenants | Composite `(tenant_id, …)` foreign keys to vendors and documents; the active and successor pointers reference `(tenant_id, document_id, id)`, so they can only name a revision of the same tenant and document. Every query filters by the actor's or the job's tenant. |
| A job naming another tenant's revision | The revision is looked up only in the job's tenant and is then not found; after the locks, the re-read job's tenant and the document's tenant must match, or the operation is refused before any write. |
| A stale or expired worker activating a revision | After the document and revision lock waits, ownership is re-checked against the locked job row with fresh database time; a stale attempt or an expired lease raises `LeaseLostError` before any write. |
| Two active revisions, or a pointer to a non-active revision | A partial unique index allows one `active` revision per document; activation runs under the document lock and writes demote → promote → pointer in one transaction. Pointer consistency itself is an application invariant (no triggers). |
| A failed or late replacement replacing good content | A failure touches only its own revision; a late older revision becomes `superseded` without touching the active one or the pointer. |
| Content altered between upload and hashing | The hash and size come from the exact bytes, with no newline, BOM or Unicode normalization; stored content is re-verified when reconstructed. |
| Document text leaking through errors or logs | Content types have fixed messages and a content-free `repr`; snapshots and revision reads exclude the text; M3c logs nothing. |
| Concurrent uploads allocating the same number | Numbers are allocated under the document row lock; unique constraints back this up and map to a fixed error. |

**Limits** (ADR-0009): the re-check is not atomic with the commit (the M3a limit). Revision failure and job failure are separate commits. A `dead` job can leave its revision unsettled until M3d/M3e add reconciliation or a projection, which is required before overall M3 acceptance. At the M3c baseline (`6f8ffde`) there was no production handler, upload or endpoint, and document text is untrusted input for later milestones.

**Verification:** at commit `8646b75` on `feat/document-revisions`, [CI run 38284929219](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38284929219) passed on [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38284929219/job/114930898138) (`819 passed, 133 skipped in 18.75s`) and [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38284929219/job/114930898065) (`818 passed, 134 skipped in 23.07s`). The [integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38284929219/job/114930897691) passed all 133 PostgreSQL tests (`133 passed, 819 deselected in 36.46s`): the 77 existing ones and the 56 added by M3c, including cross-tenant references, the one-active index, concurrent creation and activation, rollback after demotion, stale attempts, lease expiry during a lock wait and the lock timeout. The [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38284929225) passed (29 commits scanned, no leaks found). M3c was then fast-forwarded onto `main` at `6f8ffde`, where the [integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38286702295/job/114936682399) passed again (`133 passed, 819 deselected in 38.29s`) and the [secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38286702205) passed (30 commits scanned, no leaks found). All counts are from logs retrieved by the external reviewer. These results demonstrate the tested behaviour, not a general security or performance guarantee. There was no production ingestion handler on the M3c `main` baseline `6f8ffde` (M3d, on `main` since `cdf7260`, registers `ingest_revision`; see below), and Compose has never been run.

## Document ingestion (M3d, verified in CI and on `main`)

Reviewed and verified in CI at `74904e6` on `feat/document-ingestion`, then on `main` at `cdf7260`. The mitigations below are covered by the database-independent tests and by the PostgreSQL integration suite, which passed in full in CI.

| Threat | Mitigation |
|---|---|
| Chunks linked across tenants or revisions | `chunk_sets` references the revision through `(tenant_id, revision_id)`; `chunks` references its set through `(tenant_id, revision_id, chunker_version)`; chunk IDs include the tenant and revision, so identical bytes in two tenants get disjoint IDs. |
| A stale worker writing or activating chunks | Every write and the activation run in the M3a fence, take the document and revision locks, then re-check ownership with fresh database time, and re-check again before the write commits. |
| Chunks written after a revision settled or failed | Writes, activation and failure all take the same document lock first; a write re-reads the status under that lock and is refused unless `processing`. |
| An incomplete or different chunk set becoming active | Activation verifies, under its locks, the stored set's version, count, exact ordinals and rebuilt manifest against the current attempt's own expected manifest, in the same transaction as the job's success. |
| Existing chunks silently replaced or accepted | Inserts never overwrite; every existing row is compared field by field, text included, and a missing row after a suppressed conflict is a fixed conflict error. |
| Source text altered or lost by chunking | Chunk text is an exact source slice; only a BOM, line terminators and permitted spaces and tabs may be omitted; stored content is re-verified against its hash before parsing. |
| Document text leaking through errors or logs | Chunk and source values have content-free `repr`s; parser and store errors have fixed messages; the handler logs nothing. |
| Pathological input exhausting resources | At most 4,096 chunks per revision, 4,000 code points per chunk, and bounded write batches. These are initial defaults, not measured limits; there is no upload size limit until M3e. |

**Limits** (ADR-0010): the digest-only completeness check relies on the application's write-once invariant and does not protect against privileged direct database modification; there are no triggers. A `dead` job can still leave a revision unsettled until the M3e projection, which is required before overall M3 acceptance. The parser is a small grammar, not a Markdown renderer, and chunk text remains untrusted input for later slices.

**Verification:** It was verified in CI on `feat/document-ingestion` at `74904e6` ([CI run 38699149482](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38699149482)). From logs retrieved by the external reviewer: [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38699149482/job/116302837532) `1020 passed, 178 skipped in 20.13s`, [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38699149482/job/116302837727) `1019 passed, 179 skipped in 23.75s`, and the [PostgreSQL integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38699149482/job/116302837038) `178 passed, 1020 deselected in 51.89s`: the full suite, including M3d's 45 new tests. The [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38699149417) passed ([job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38699149417/job/116302836923): 33 commits scanned, no leaks found). M3d was then fast-forwarded onto `main` at `cdf7260` (`cdf7260d02b8af9affb369cc805d666be61f9ac0`, adding only documentation after `74904e6`), where [CI run 38701376504](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38701376504) passed again. From logs retrieved by the external reviewer: [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38701376504/job/116310119787) `1020 passed, 178 skipped in 19.71s`, [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38701376504/job/116310119664) `1019 passed, 179 skipped in 16.16s`, and the [PostgreSQL integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38701376504/job/116310119317) `178 passed, 1020 deselected in 53.28s`. The [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38701376501) passed ([job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38701376501/job/116310119403): 34 commits scanned, no leaks found). Both runs were push-triggered on `main`; the reviewer did not run the suite locally. These results demonstrate the tested behaviour, not a performance benchmark or a general security guarantee. At that baseline, upload and document endpoints were not implemented; Compose has never been run.

## Document API (M3e, verified in CI and on `main`)

Implemented in Prompt 89, corrected in Prompt 90, accepted at external review (Prompt 91), and reviewed and verified in CI on `feat/document-api` at `ccdf08d` ([CI run 38755179760](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38755179760)): Ubuntu, Windows and the full 204-test PostgreSQL integration suite (including the 26 M3e tests) passed, per job logs retrieved by the external reviewer. The [secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38755179509) passed (37 commits scanned, no leaks found). It was then published on `main` at `2e605e7`, where [CI run 38758727669](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38758727669) passed again (Ubuntu, Windows and the 204-test PostgreSQL suite, per job logs retrieved by the external reviewer); the secret scan passed there too (38 commits scanned, no leaks found). These results demonstrate the tested behaviour, not a general security or performance guarantee.

| Threat | Mitigation |
|---|---|
| Oversized or endless uploads | Caps on the streamed count, never on `Content-Length`: 2 MiB of file bytes, 2 MiB + 64 KiB in total, 8 parts, 8 KiB of headers per part, 1 KiB per text field. Reading stops at the first error; a declared length over the cap is refused before reading. The file is one bounded in-memory buffer and no temporary file is created. |
| Reading a body before authorization | The route declares no body parameters; authentication, the role check and the vendor lookup finish before the first `receive`, which raw-ASGI tests assert. |
| Truncated or malformed multipart accepted | The parser's `finalize()` is a no-op, so the reader requires the closing boundary and every begun part to have ended; a truncated body is never a 2xx. |
| Outcomes depending on how bytes arrive | Header and boundary regions are fed to the parser one byte at a time and part data in slices that stop before each delimiter, so the first error in byte order wins for any receive partitioning; tests cover single, split and random partitions. |
| Header bytes hidden from the cap | The 8 KiB per-part cap counts the raw header region as received (names, colons, whitespace, values and line endings), not names and values reconstructed from parser callbacks, which omit some bytes. |
| Parameters hidden from validation | `Content-Disposition` and `Content-Type` parameters are parsed without dropping extended (`filename*`, `charset*`) or repeated names, so they cannot evade the no-filename rule or the UTF-8 charset rule. |
| Tenant or role injected through the form | Only six known part names are accepted; any other name, including `tenant_id` or `role`, is a 422, and the tenant comes only from the API key. |
| Submitted values leaking through errors or logs | 422 entries carry fixed locations and types; unknown names, filenames, values and parser messages are never echoed. The parser's own logger is disabled, and the only new log event (`document.upload_inconsistent`) carries no values. |
| A revision without its job, or a job reset by a re-upload | Revision and job are created in one transaction; a duplicate never resets or re-queues an existing job and never re-enqueues a settled revision. |
| Content, payloads or worker IDs exposed by reads | Revision views never select `content_text`; job views omit the payload, idempotency key, worker ID and tenant; response models forbid extra fields. Objects of other tenants are 404. |
| Inconsistent or misleading status | Each GET is one REPEATABLE READ, READ ONLY snapshot with one database time; `ingestion_state` is derived, `in_progress` shows `lease_expired`, and `verified_complete` is true only for active or superseded revisions. |

**Limits** (ADR-0011): the reader depends on the verified behaviour of `python-multipart` 0.0.32, which an upgrade must re-verify. Per-byte header feeding costs CPU bounded by the header caps. The upload response is an observation that a worker may change at once. `stalled` revisions have no operator retry in v1.

## Containers (M3f, verified in CI and on `main`)

Implemented in Prompt 98, corrected in Prompt 99, accepted at external review (Prompt 100), and verified in CI on `feat/container-stack` at `682101b` ([CI run 38769986459](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38769986459)). Ubuntu, Windows, the 204-test PostgreSQL suite and the container job (image build, effective build context, image checks, Compose smoke and cleanup) passed, per job logs retrieved by the external reviewer; it was then published on `main` at `e2463cb`, where the same checks passed again ([ADR-0012](decisions/0012-containers.md)). In that run, the container job checked these mitigations in a real container:
- the effective build context excluded all 19 planted fixtures;
- the runtime ran as UID/GID 10001;
- the application containers ran the CI-built image;
- the smoke passed, including its key-in-service-logs check and the idle-worker exit check;
- cleanup verified ownership.

Local Compose is unverified. It is a development stack only, with no production-readiness or general security guarantee; the acceptance of overall M3 at external review (Prompt 105) does not change that.

| Threat | Mitigation |
|---|---|
| Secrets or artifacts entering the image | The build context is an allowlist with recursive re-exclusions (`.env*`, `.git`, `.local`, virtual environments, caches, build outputs, keys). CI is to verify the effective context with planted nested fixtures. The runtime image holds only the virtual environment and `alembic.ini`, with no build arguments or baked-in configuration. |
| A substituted or unexpected image | Base images and the database image are pinned by digest. Application services never pull (`pull_policy: never`), and CI is to check that every application container runs the CI-built image ID. |
| Excess privilege in containers | UID/GID 10001; root-owned files the runtime user cannot modify; a read-only root filesystem with a `/tmp` tmpfs; all capabilities dropped; `no-new-privileges`; an init process. |
| Exposure on the network | Host ports bind `127.0.0.1` only (API 8000, database 5433). |
| Migration races | Only the one-shot `migrate` service migrates; the API and worker start after it succeeds. |
| The CI API key leaking into logs | The key stays in memory. Every key-shaped string from `create-key` is protected before its status or format is checked, and its raw output is never shown. Captured output is redacted before display, including anything key-shaped. Unavailable service logs fail the smoke rather than passing the key check, and a key found in service logs fails it (reported as a count). GitHub masking is only an extra layer. |
| Cleanup removing unrelated resources | Cleanup removes only resources labelled with this run's Compose project and this run's image tag, after checking that both name the same run and attempt. It refuses `down` when ownership cannot be verified, and reports success only after a successful post-cleanup verification. |

**Limits** (ADR-0012): the database credentials are disposable and public. Stopping the worker has an external 60 s budget, not a guaranteed shutdown bound (ADR-0008). The smoke stops an idle worker only. Cleanup can be prevented by runner loss. The uv builder-tool image is used under a narrowly approved exception to the two-week age policy, for its exact digest only (no runtime uv; no change to the Python base or the general policy). The exception does not claim age compliance or general safety. There is no production deployment.

## Revision indexing (M4c, accepted for a local commit; not verified in CI)

Implemented by Claude Code in Prompt 125 and corrected in Prompt 126 under the accepted M4c
specification ([ADR-0015](decisions/0015-revision-indexing.md)). The complete corrected implementation
is **accepted at external review in Prompt 127 for a local commit, pending current-version CI**.
No publication or merge is authorized or completed by this task. PostgreSQL, Linux and real
container indexing verification remain pending CI. All 251 integration tests remain unexecuted
against this M4c version, including the 18 indexing cases. Claude Code ran the new wheel script
locally on Windows in Prompts 125–126 and the corrected installed-wheel provider-resolution probe
in Prompt 126; neither Codex nor the reviewer ran those checks. The new wheel step has not run
on CI runners; the existing coverage on `main` at `872d0af` predates this extension. M4d–M4f
and overall M4 acceptance remain pending. Local Compose remains unverified.

| Threat | Mitigation |
|---|---|
| Indexing another tenant's revision | The tenant comes only from the validated actor (enqueue/backfill) or the job (handler). Every selection, enqueue and read is tenant-scoped, and M4b's composite keys back this in the database. |
| Unauthorized or unbounded operator action | `eg-admin backfill-indexes` follows the existing trusted-operator model, with no API endpoint. It processes one bounded page (limit 1–100) per invocation, never retries or resets a terminal job, and prints only fixed outcome counts and the cursor. |
| Leaking text, vectors or keys | Job payloads hold only `index_id`. Page values and errors never show text or vectors, the handler does not log, and CLI and runtime output carry fixed counts and codes only. |
| An unexpected or networked provider | Providers come only from an immutable mapping fixed when the handler is built (production: the offline `HASH_IDENTITY`). The stored identity's fingerprint is verified before resolution, and no live adapter, network or environment is used. |
| Stale writes after cancellation or lease loss | Provider work runs with no transaction or lock open. `ctx.check()` runs before and after it (and before classifying a provider or provider-resolution failure), each write and the finish are fenced, and M4b re-checks ownership. Cancellation, lease loss and fence closure raised during provider resolution propagate unchanged. Readiness and job success commit together. |

**Limits:** checks happen at explicit boundaries only. They do not interrupt synchronous calls,
and a cancellation latched after the last check may not stop a non-finish transaction already
under way; the accepted lease-expiry/commit window remains. Reused committed vectors are not
re-verified against provider output, and provider calls are not exactly-once. A stalled index
(terminal canonical job) has no recovery in M4c. The offline provider is a lexical-hash
baseline with no semantic-quality claim.

## Not implemented yet

- **Rate limiting, lockout, key expiry and usage auditing** for API keys. Direct domain callers (tests, later the worker) still construct `ActorContext` themselves and are trusted.
- **Database tenancy.** The M2a schema adds tenant foreign keys, unique `(tenant_id, id)` keys, and a composite `(tenant_id, user_id)` key from API keys to users. PostgreSQL enforcement of these constraints was verified in CI for commit `9ad7dae` ([integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38158076257/job/114525070229): 10 passed, none skipped); M2a was then fast-forwarded onto `main` at `e2dee5c`, where the [integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38159547345/job/114529402973) passed again (`10 passed, 250 deselected`). M2b derives the tenant only from authenticated records; M2c adds tenant-filtered vendor queries, whose two-tenant isolation passed against PostgreSQL in CI at `a888b6c` on its branch and again on `main` at `9d5a93a`. Row-level security is a later enhancement.
- **Database credentials and URLs.** `EG_DATABASE_URL` is read only from the environment and held as a secret.
  - **Query parameters:** only `sslmode` and `connect_timeout` are accepted, each once. So a URL cannot use the query to override the validated database or host, or to carry credentials and server options that password masking would not hide.
  - **Errors:** configuration errors from `load_database_settings()` never include the URL, its query values or its credentials. That wrapper is the supported boundary, because pydantic's `hide_input_in_errors` does not make structured `ValidationError` dumps safe. Representations and engine logs mask the password.
  - **Logging:** SQL echo is off and SQL parameters are hidden.
  - **Process environment:** libpq environment variables (such as `PGHOSTADDR`) are outside this validation.
  - **Disposable credentials:** the Compose and CI credentials are disposable and documented as such.
- **Destructive integration tests.** The PostgreSQL tests drop the `public` schema of `EG_TEST_DATABASE_URL`. Before any engine exists, they refuse a missing or invalid URL, a database name without the `_test` suffix, an invalid `EG_DATABASE_URL`, or a target with the same host, port and database as `EG_DATABASE_URL` (ignoring credentials, spelling and loopback aliases). URL comparison cannot detect two different DNS names for one server, so the test database must be explicitly disposable. In CI for commit `9ad7dae`, the guard accepted the disposable service database before the [integration tests](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38158076257/job/114525070229) ran against it. Its refusal paths are covered by database-independent tests on Ubuntu and Windows. Compose has never been run.
- **Atomic, concurrent-safe transitions.** The report transitions are pure functions. Two simultaneous requests could both pass validation; persistence must serialize them (for example with a row lock or compare-and-set on revision and hash). The M3a job fence (above) provides this pattern for jobs; reports do not use it yet.
- **Upload limits and untrusted-file handling** (M3e): implemented, reviewed, **verified in CI and on `main`** (see *Document API* above).
- **Provenance checks:** that a cited chunk was actually retrieved for the review and that the quote occurs in it (M5).
- **Secret handling beyond the database URL and API keys.** The database URL (M2a) and API keys (M2b) are covered above. Other secrets, such as model-provider keys, arrive with later milestones. Request logging (M1c) writes only allowlisted fields; see ADR-0002.

## Open risks

- **Prompt injection.** Uploaded documents are untrusted and may contain instructions aimed at the model. The planned mitigations (delimited evidence, no model tools, validated structured output, human approval) reduce but cannot eliminate the risk. Paired clean/injected evaluation is planned for M7; nothing is measured yet.
- **Semantic support.** No component yet checks whether a cited passage actually supports a claim. That needs model judgment plus human review.
- **Document authenticity.** Not established anywhere in v1 (see [responsible-ai.md](responsible-ai.md)).
- **Secrets in the repository.** Mitigated by Gitleaks locally and in CI. The full-history scan [passed](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38142996460) for the published baseline `6d64fb3` and [again](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38159547321) for `main` at `e2dee5c` and [at `277dfea`](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38167398504), and for branch `feat/vendor-api-readiness` [at `a888b6c`](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38212619867), and for `main` [at `9d5a93a`](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38214711864) and [at `b3f9845`](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38242144876). Pattern scanners cannot detect every secret.
