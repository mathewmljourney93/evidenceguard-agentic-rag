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

**Limits** (ADR-0007): handlers are trusted code, and the fence assumes they preserve its transaction and lock. `execute` accepts arbitrary SQL and Python exposes the underlying objects, so a handler that issued transaction-control SQL, used the underlying connection or edited ownership fields could defeat the fence. A fenced transaction that passed its check just before expiry may commit shortly after the lease expires; the database enforces only that the payload is a JSON object, not the finer payload rules or the byte cap; on `main` there is no worker yet. Passing tests demonstrate the tested behaviour, not a general security or performance guarantee.

**Verification:** at commit `11350e1` on `feat/durable-job-core`, the [integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38240768344/job/114782517485) passed with all 63 PostgreSQL tests (`63 passed, 605 deselected in 16.58s`, from the log retrieved by the external reviewer). They include M3a's concurrent-claim, stale-worker, lease-fencing, lock-wait and lock-timeout tests. M3a was then fast-forwarded onto `main` at `b3f9845`, where the [integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38242144844/job/114787118281) passed again (`63 passed, 605 deselected in 16.17s`). On `main` there is still no worker process (M3b is implemented only on a local branch; see below), and Compose has never been run.

## Worker runtime (M3b, implemented on a local branch; under review, PostgreSQL verification pending)

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

**Limits** (ADR-0008): execution is at least once, so durable effects must be fenced and idempotent, and effects outside the database can repeat. Cancellation is cooperative: Python cannot stop a running thread. `claim` and outcome recording are synchronous and there is no worker statement timeout, so there is **no total shutdown deadline** and a hung call may need external termination. Engine disposal does not cancel checked-out connections; PostgreSQL rolls back a dead worker's transaction only when it detects the disconnect. Reclaim can be delayed by a late heartbeat or a lingering transaction. Handlers are trusted code; the handler wrapper is not a sandbox. There are no production handlers yet.

**Verification:** only the database-independent tests have run, locally. The worker's PostgreSQL integration tests have **not run yet**; they are pending authorized publication and CI.

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
- **Upload limits and untrusted-file handling** (M3).
- **Provenance checks:** that a cited chunk was actually retrieved for the review and that the quote occurs in it (M5).
- **Secret handling beyond the database URL and API keys.** The database URL (M2a) and API keys (M2b) are covered above. Other secrets, such as model-provider keys, arrive with later milestones. Request logging (M1c) writes only allowlisted fields; see ADR-0002.

## Open risks

- **Prompt injection.** Uploaded documents are untrusted and may contain instructions aimed at the model. The planned mitigations (delimited evidence, no model tools, validated structured output, human approval) reduce but cannot eliminate the risk. Paired clean/injected evaluation is planned for M7; nothing is measured yet.
- **Semantic support.** No component yet checks whether a cited passage actually supports a claim. That needs model judgment plus human review.
- **Document authenticity.** Not established anywhere in v1 (see [responsible-ai.md](responsible-ai.md)).
- **Secrets in the repository.** Mitigated by Gitleaks locally and in CI. The full-history scan [passed](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38142996460) for the published baseline `6d64fb3` and [again](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38159547321) for `main` at `e2dee5c` and [at `277dfea`](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38167398504), and for branch `feat/vendor-api-readiness` [at `a888b6c`](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38212619867), and for `main` [at `9d5a93a`](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38214711864) and [at `b3f9845`](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38242144876). Pattern scanners cannot detect every secret.
