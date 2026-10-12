# ADR-0007: Durable PostgreSQL job core

- **Status:** Accepted (M3a), following the implementation review and passing CI at commit `11350e1` on branch `feat/durable-job-core`, then fast-forwarded onto `main` at `b3f9845`, where CI passed again. See *Consequences and limits*.
- **Date:** 2026-10-12
- **Builds on:**
  - [ADR-0003](0003-plain-python-workflow.md): plain Python, PostgreSQL-backed jobs, leases and fencing;
  - [ADR-0004](0004-persistence-foundation.md): the schema conventions, transaction ownership and the disposable-database tests;
  - the M3a specification accepted at review in [docs/plan.md](../plan.md) (Prompts 46–48 in [prompts.md](../../prompts.md)).

## Context

Every later M3 slice (activation, chunk writes, the worker) must write through a fence that a reclaimed, stale worker cannot pass. M3a builds only that core: the `jobs` table, the lifecycle and the transactional operations. There is no worker, handler or endpoint yet.

## Decisions

### Pure lifecycle (`evidenceguard_domain.jobs`)
- **Immutable values:**
  - `JobSnapshot`, `JobRequest`, `JobPayload` and `JobLeaseToken` are immutable `DomainModel` values;
  - transitions are pure functions that take the current time as an argument and never read a clock or a database.
- **Statuses:**
  - `queued`, `running`, `succeeded`, `failed`, `dead`;
  - `failed` means a permanent handler failure;
  - `dead` means a retryable failure or an abandoned lease has exhausted the attempt cap;
  - the three terminal statuses clear the lease, set `finished_at` and are never claimed or reset again.
- **Attempts:**
  - `attempt` starts at 0 and increases by one on every claim or reclaim;
  - it never exceeds `max_attempts`, which defaults to 3 and must be 1–10.
- **Backoff:**
  - after failed attempt *n*, the delay is `min(5 * 2^(n - 1), 60)` seconds;
  - there is no jitter, a deliberate v1 simplification.
- **Other defaults:**
  - a 60 s lease;
  - a 20 s heartbeat interval, recorded for the M3b worker; M3a has no timer;
  - a 5 s `lock_timeout` for fenced transactions;
  - at most 10 exhausted rows swept per claim.

  These are engineering defaults, not measured performance claims.
- **The fencing token** is `(job_id, worker_id, attempt)`. Because every claim increments `attempt`, a reclaim invalidates the old owner even when the same worker ID reclaims the job.
- **Ownership** (`holds_lease`) requires:
  - a running job;
  - the matching token;
  - `now < lease_expires_at`. The lease is expired from the instant `lease_expires_at` is reached, and an expired lease is never revived.
- **Timezone-aware time:** snapshot timestamps use Pydantic's `AwareDatetime`. Every public time-dependent function rejects a naive `now`, or one whose `utcoffset()` is `None`, with a fixed `ValueError`. A naive value is never assumed to be UTC, and aware values with any offset are compared by their actual instants.
- **Errors carry fixed messages only:** `LeaseLostError`, `JobIdempotencyConflictError`, `InvalidJobTransitionError` and `InvalidJobPayloadError` never include payload values, SQL or other exception text.

### Payload: what the application enforces versus PostgreSQL

| Rule | Enforced by |
|---|---|
| A flat JSON object | the application (`JobPayload`); PostgreSQL also checks `jsonb_typeof(payload) = 'object'` |
| Keys are lowercase identifiers of at most 64 characters, with no key containing `tenant` | the application only |
| Values are canonical lowercase, hyphenated UUID strings; no nesting, arrays, numbers, booleans, nulls, text or secrets | the application only |
| At most 4,096 bytes of canonical UTF-8 JSON (sorted keys, compact separators) | the application only. PostgreSQL does **not** enforce an equivalent byte cap |
| Key order does not affect identity | the application: a payload is a sorted tuple of pairs. JSONB equality is also order-insensitive |

An empty object is allowed for test-only jobs. Kind-specific schemas arrive with their handlers. Invalid input is rejected, never rewritten.

### Schema (migration `0002`)
- **Table:** `jobs`, with a UUID primary key and `tenant_id` referencing `tenants`.
- **Uniqueness:**
  - unique `(tenant_id, id)` for later composite references;
  - unique `(tenant_id, kind, idempotency_key)`.
- **CHECK constraints:**
  - the status values;
  - the `kind` pattern;
  - a non-empty `idempotency_key` (at most 128 characters through its column type);
  - a JSON object payload;
  - `0 ≤ attempt ≤ max_attempts`;
  - `max_attempts` between 1 and 10;
  - the lease fields set exactly while running, with `attempt ≥ 1` while running;
  - `finished_at` set exactly for terminal statuses;
  - `last_error` restricted to a fixed-code pattern.
- **Partial indexes:**
  - `(run_after, id)` where `status = 'queued'`;
  - `(lease_expires_at)` where `status = 'running'`.
- **Not included:** no extension, and no change to existing tables.
- **Drift checks:** `alembic check` compares neither CHECK constraints nor partial-index predicates, so a database-independent test pins the migration's literal constraint and predicate text to the model's constants.

### Operations (`evidenceguard_persistence.jobs`)
- **They return `JobSnapshot` values,** never session-bound ORM objects.
- **Time:** every lease and scheduling decision uses a fresh PostgreSQL `clock_timestamp()`, never worker time, `now()` or `CURRENT_TIMESTAMP`. Audit timestamps (`created_at`, `updated_at`) may use ordinary transaction time.
- **`enqueue(session, actor, …)`** runs in the **caller's** transaction and never commits.
  - **Tenant:** taken only from the `ActorContext`.
  - **Insert:** `INSERT … ON CONFLICT ON CONSTRAINT uq_jobs_tenant_id_kind_idempotency_key DO NOTHING RETURNING …`, with `run_after = clock_timestamp()`.
  - **On conflict,** it reads the committed row and compares the canonical payload and `max_attempts`:
    - an identical request returns that job unchanged, even when it is terminal;
    - a changed request raises `JobIdempotencyConflictError` and changes nothing;
    - if the row is not visible (possible only above READ COMMITTED), it raises the fixed `JobEnqueueRaceError`.
- **`claim(session_factory, worker_id)`** owns one short transaction and is a trusted, system-level operation across tenants:
  1. **Sweep:** take at most 10 running rows whose lease has expired with `attempt ≥ max_attempts`, using `FOR UPDATE SKIP LOCKED`, and mark them `dead` with `attempt` unchanged.
  2. **Select:** take one row by `(run_after, id)` with `FOR UPDATE SKIP LOCKED`. Every candidate has `attempt < max_attempts` and is either queued and due, or running with an expired lease. Exhausted rows are excluded, so they cannot obstruct eligible work.
  3. **Take it:** increment `attempt`, set the worker ID and a 60 s lease from fresh database time.
- **Worker IDs** (`new_worker_id()`, `worker-<uuid4>`) are unique per process start. They are not secrets and name no host or user.

### The fence (`fenced_transaction`)
- **One transaction does all of this:**
  1. `SET LOCAL lock_timeout = '5s'`.
  2. Lock the job row by ID (`SELECT id … FOR UPDATE`), waiting if necessary. A lock timeout becomes the fixed `JobLockTimeoutError`.
  3. In a **separate statement**, read the row with a fresh `clock_timestamp()` and require a running job, the matching token and an unexpired lease. Nothing read before the lock wait is reused. Otherwise `LeaseLostError`, with no effect.
  4. Run the caller's block. It writes through `Fence.session`, which offers `execute`, `scalar`, `scalars`, `add` and `flush` but omits `commit`, `rollback` and `close`. Lifecycle transitions (`heartbeat`, `succeed`, `fail_retryable`, `fail_permanent`) re-check ownership with fresh time before writing. A transition that ends or re-queues the attempt closes the fence to further work.
  5. Commit when the block finishes; roll back on any uncaught error, including a failed commit; always close the session. The fence also closes after its block.
- **Single-purpose operations:** `heartbeat`, `complete`, `fail_retryable` and `fail_permanent` are each one fenced transaction.
- **The guarantee:**
  - While a transaction holds the row lock after a valid check, no claimant can reclaim the job, because claims and the sweep use `SKIP LOCKED`.
  - It does **not** guarantee the commit happens before `lease_expires_at`: a transaction that passed its check just before expiry may commit shortly afterwards.
  - Fenced transactions must therefore stay short, and no provider or network call may be made while the lock is held.
- **The boundary is a convention, not a sandbox.**
  - Handlers are trusted application code. Omitting `commit`, `rollback` and `close` discourages ending the transaction by accident through ordinary session methods.
  - It is not an enforceable prohibition on every possible early commit: `execute` accepts arbitrary SQL, and Python exposes the underlying objects.
  - Handlers must not issue transaction-control SQL, reach into the underlying session, transaction or connection, or modify the job's ownership fields directly.
  - The guarantee above assumes callers preserve the fence's transaction and lock. There is deliberately no SQL parser, blacklist or sandbox.
- **Lock order** for later slices: the job row first, then any document row.

## Tests

- **Database-independent (run locally):**
  - lifecycle transitions and terminal invariants;
  - attempt bounds and defaults;
  - the backoff values and cap;
  - payload shape, canonicalisation, UUID canonical form and the exact 4,096-byte boundary;
  - fixed error messages;
  - compiled SQL for claim, sweep and fence (`SKIP LOCKED`, ordering, limits, `clock_timestamp()`, lock before check);
  - the fence protocol and transaction ownership with a scripted session: commit, rollback and close on success, on a refused check, on a lock timeout, on a failing effect and on a failing commit;
  - migration SQL rendered offline.
- **PostgreSQL integration (`tests/test_jobs_postgres.py`):** run in the existing CI job with the guarded disposable database and required-integration mode; they passed at `11350e1` (see *Consequences and limits*). They cover:
  - constraints and the tenant reference;
  - identical, reordered, changed, terminal, cross-tenant and concurrent enqueues;
  - due-time and deterministic claiming;
  - two concurrent claimers;
  - exhausted rows below and above the sweep limit;
  - a reclaimed stale owner, and the same worker ID with a newer attempt;
  - a held fence preventing reclaim;
  - expired, unreclaimed ownership;
  - a lease expiring during a real lock wait;
  - the real 5-second `lock_timeout` raising `JobLockTimeoutError` without running the block;
  - rollback of failed fenced effects;
  - retries, abandonment and permanent failure.

  Concurrency tests use separate connections, barriers or events, bounded waits and a server-side `statement_timeout`.
- **The shared disposable-database fixtures** moved unchanged from `test_persistence_postgres.py` to `tests/conftest.py`, so both integration modules use one copy of the guard.

## Consequences and limits

- **Verified in CI.** The tested commit is `11350e1` (`11350e1818c7bd348fa6e6a26b639fe1b21a0e80`) on branch `feat/durable-job-core`. It adds only prompt history after the reviewed M3a commit `a133513`.
  - In [CI run 38240768344](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38240768344), the [PostgreSQL 17 + pgvector integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38240768344/job/114782517485) passed. Its log, retrieved by the external reviewer, reports `63 passed, 605 deselected in 16.58s`.
  - That covers M2's 21 integration tests and M3a's 42, with no skips or failures. Among them:
    - one owner per job under concurrent claims;
    - stale-worker refusal;
    - refusal after a lease expires during a lock wait;
    - the migration round trip with `0002`;
    - rollback of failed fenced effects;
    - `test_a_lock_held_beyond_the_lock_timeout_raises_the_fixed_error`, which passed as part of that suite. No individual log line or duration was observed for it.
  - The database-independent checks passed on [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38240768344/job/114782517339) (`605 passed, 63 skipped in 12.71s`) and [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38240768344/job/114782517028) (`605 passed, 63 skipped in 14.66s`).
  - The [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38240768288) passed ([job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38240768288/job/114782517013): 21 commits scanned, no leaks found).
  - **On `main` at `b3f9845`** (`b3f984552bf22cf6350702330d30851f3e08b3f4`): [CI run 38242144844](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38242144844) passed. From logs retrieved by the external reviewer: [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38242144844/job/114787118333) `605 passed, 63 skipped in 7.56s`, [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38242144844/job/114787118106) `605 passed, 63 skipped in 14.86s`, [integration](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38242144844/job/114787118281) `63 passed, 605 deselected in 16.17s`. The [secret-scan run 38242144876](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38242144876) also passed ([job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38242144876/job/114787118292): 22 commits scanned, no leaks found).
- **What the tests show.** Passing tests demonstrate the tested behaviour, not a general security or performance guarantee.
- **At-least-once handling.** A handler effect can commit shortly after lease expiry (see the guarantee). External calls made by later handlers are at-least-once (ADR-0003).
- **Claim cost.** Claiming scans eligible rows ordered by `(run_after, id)`. The partial indexes serve the common cases, but no performance or throughput figure is claimed.
- **Payload rules beyond "JSON object" live in the application.** Rows written outside `enqueue` are only checked against the database constraints, and reading an invalid payload back fails validation.
- **Not included in M3a:**
  - the worker process and heartbeat timer (M3b);
  - handlers;
  - documents, revisions and chunks (M3c–M3d);
  - uploads;
  - Docker changes;
  - embeddings and model calls.
- **Compose has never been run.**
