# ADR-0008: Sequential worker runtime and `eg-worker`

- **Status:** Accepted (M3b), following the implementation review and passing CI at commit `bc5f638` on branch `feat/worker-runtime`. It is **not yet merged into `main`**. See *Consequences and limits*.
  - The implementation came in Prompt 60, with corrections after review in Prompt 61: cancellation-check boundaries, exception-safe job-thread cleanup, and the abnormal exit despite cleanup failures.
  - The specification was accepted at review in Prompt 59.
- **Date:** 2026-10-12
- **Builds on:**
  - [ADR-0001](0001-packaging-and-layout.md): the `apps/worker/evidenceguard_worker` layout and the single distribution;
  - [ADR-0003](0003-plain-python-workflow.md): plain Python, PostgreSQL-backed jobs, leases and fencing;
  - [ADR-0007](0007-durable-job-core.md): the M3a job core, its 60 s lease, 20 s heartbeat interval, 5 s `lock_timeout`, attempt cap and backoff, all unchanged here;
  - the M3b specification in [docs/plan.md](../plan.md), accepted at review (Prompts 57–59 in [prompts.md](../../prompts.md)).

## Context

M3a provides durable jobs and the write fence, but nothing runs them. M3b adds the process that claims jobs, renews their leases and records outcomes, without a new queue, framework or dependency. No production job kind exists yet: M3d adds `ingest_revision`.

## Decisions

### Package and command
- **Package:** `evidenceguard_worker` (`apps/worker/evidenceguard_worker/`), in the single `evidenceguard` distribution. It imports the domain, persistence and observability packages, never `evidenceguard_api`, and nothing imports it. The boundary test enforces both rules.
- **Command:** `eg-worker [--once] [--log-level LEVEL]`. Usage errors print only static usage and a fixed message (a small duplicate of `eg-admin`'s safe parser).
- **Exit codes:**
  - 0: normal stop, or `--once` with nothing claimable;
  - 1: unexpected failure (class name only), including a `--once` claim that hits a database error;
  - 2: usage error;
  - 3: database configuration error (URL-free message);
  - 4: no handlers registered;
  - 5: abnormal shutdown.
- **Empty registry:** the production registry (`evidenceguard_worker.handlers`) is empty in M3b, so `eg-worker` exits 4 **before** database settings are read. `--help` needs no settings or database.
- **Test handlers** live only under `tests/`. No flag, variable or packaged module registers test kinds, and no command enqueues jobs.

### Process model
- **At most one concurrently active handler per process.** Jobs are processed one after another; throughput comes from more processes, which `SKIP LOCKED` already supports.
- **Threads:** the main thread supervises (polling, claiming, deadlines, outcomes). Each job gets a daemon handler thread and a daemon heartbeat thread.
- **No session crosses threads.** Every M3a operation opens and closes its own session; a test records the thread that uses each session.
- **No new claim while a thread from an earlier job may be alive.** After every bounded join the runtime checks that the thread actually stopped; otherwise it takes the abnormal path and never claims again.

### Claim filter (the only change to M3a code)
- `claim(..., kinds=None)` keeps the M3a behaviour exactly.
- A collection allows only those kinds. Every value is validated against M3a's kind pattern before any SQL; a string is rejected rather than read as characters.
- An **empty** collection selects no candidate and returns `None`; it never means "claim all". The global exhausted-job sweep still runs.
- The worker claims with its registry's kinds, so unhandled kinds stay queued for a worker that can run them.

### Polling
- **Local lease deadline:** the monotonic time is captured before each claim; the attempt's local deadline starts there plus the lease.
- **No job:** wait 2 s, or exit at once with `--once`.
- **Claim database errors** (`SQLAlchemyError`, `JobLockTimeoutError`): log `worker.poll_failed`, then back off 1, 2, 4, 8, 16, then 30 s, resetting after the next successful claim. `--once` exits 1 without retrying.
- **Post-claim stop check:** if a stop was requested while the claim was in flight and a job was acquired, no handler starts; the only write is the fenced `worker_shutdown` retry.

### Handler context and atomic finish
- **`JobContext`:** `job`, `token`, `check()` and `fenced(finish=False)`. `HandlerFence` exposes only `.session` and `.job`. This follows M3a's trusted-code convention and is **not a sandbox**.
- **Shared attempt state:** one thread-safe `AttemptState` per attempt. Its lock is never held across database I/O.
- **Finish state:** `none` → `finishing` → `committed`, back to `none` (rolled back), or `uncertain`.
  - `ctx.fenced(finish=True)` records `succeeded` in the same transaction as the block's effects.
  - `committed` is published only after the transaction context exits without an exception.
  - A commit that raises makes the finish `uncertain`: success is never claimed.
- **After `committed`:** context operations raise `FenceClosedError`, and no further completion, retry or failure is attempted. A later handler exception is only logged (`job.post_finish_error`).
- **Cancellation-check boundaries:** `fenced()` checks the attempt's permission at three explicit points.
  1. Before the fence opens.
  2. Again after the fence has acquired its lock, because cancellation or lease loss may have been latched during the wait. A failed check raises inside the transaction, which rolls back, and the handler's block never runs.
  3. With `finish=True`, once more after the block and before `succeeded` is recorded. A failed check rolls back the block's effects, and nothing is committed.

  The `finishing` state itself is permitted. These checks are not atomic with every SQL statement and do not interrupt a statement already in flight; the database fence remains the final ownership check.
- **After `uncertain`:** context operations are refused too. Any outcome the runtime attempts still goes through the fence, which refuses it if the finish did commit (logged `job.outcome_unknown`). If the commit did not happen, the fenced retry is recorded normally, so durable effects must be idempotent.

### Heartbeats, lease loss and cancellation
- **Renewal:** every 20 s, a heartbeat records the monotonic time and then renews through M3a. A confirmed renewal moves the local deadline to that pre-call time plus the lease.
- **Refusals:** a refusal (or an unexpected heartbeat error) is classified against the finish state.
  - While a finish is in progress, it stays **pending**, because it may come from the job's own commit that is not yet published locally.
  - It is resolved when the finish ends: discarded if committed; lease loss if rolled back; lease loss with an unknown outcome if uncertain.
- **Transient errors:** lock timeouts and SQLAlchemy errors are logged and retried at the next interval.
- **Presumed loss:** once the local deadline passes without a confirmed renewal. Local checks only stop a handler earlier; PostgreSQL decides actual validity through the fence.
- **Irreversible cancellation:** latched lease loss and latched cancellation are permanent for the attempt. A late successful heartbeat moves nothing and permits nothing, although it may have extended the database lease and so delayed reclaim.
- **On lease loss:**
  1. cancellation is requested;
  2. the heartbeat is stopped and joined (10 s);
  3. the handler gets a 5 s grace.

  If both threads stop, no stale outcome is written. If either is still alive, the runtime takes the abnormal path.
- **Cooperative only:** Python cannot stop a running thread, so cancellation takes effect at the handler's next `check()` or `fenced()`.

### Outcomes
- **Who writes:** the supervisor records outcomes only after both threads are confirmed stopped, and only through the fence.

| Handler result | Outcome |
|---|---|
| Finish committed | nothing more |
| Lease loss detected (including a `LeaseLostError` from the handler's own fence) | no write |
| Normal return | `complete` |
| `RetryableJobError(code)` | `fail_retryable(code)` |
| `PermanentJobError(code)` | `fail_permanent(code)` |
| `JobCancelledError` after a runtime cancellation | `fail_retryable(worker_shutdown)` |
| Anything else (including `JobCancelledError` the runtime did not request) | `fail_retryable(unexpected_error)` |
| A claimed kind with no handler | `fail_permanent(unknown_job_kind)` |

- **New codes:** `unknown_job_kind`, `unexpected_error` and `worker_shutdown` were added to `JobErrorCode`; `last_error` is checked by pattern, so no migration is needed.
- **Failed writes:** a refused outcome is logged as `job.lease_lost`, or `job.outcome_unknown` after an uncertain finish. Any other failure is logged as `job.outcome_failed`; the lease then expires and the job is reclaimed.

### Shutdown
- **Signals:** SIGINT, SIGTERM where delivered, and SIGBREAK on Windows.
  - Handlers are installed only from the main thread, and only set plain flags: no locks, so they cannot deadlock the thread they interrupt.
  - The first signal requests a graceful stop, the second an immediate one.
  - The main thread re-checks the flags at least every 0.1 s, an implementation detail rather than a lifecycle default.
- **Graceful stop:**
  1. no new claims;
  2. heartbeats continue while the handler gets a 30 s drain;
  3. then cancellation and a 5 s grace;
  4. then the abnormal path.

  Lease validity during the drain depends only on actual renewals and the fence.
- **Immediate stop:** goes straight to the abnormal path while a job runs, or exits 0 if none is.
- **Abnormal path:** log `worker.abnormal_stop` with the fixed reason as `error_type` (`HandlerStillRunning` or `HeartbeatStillRunning`), and never claim again.
  - `run_worker()` **returns** an `ABNORMAL` result; its daemon threads may keep running while the process lives.
  - The CLI disposes the engine, flushes its output and **ends the process with `os._exit(5)`**. A subprocess test proves the exit even with a non-daemon thread still alive.
- **Exception-safe job lifecycle:** after an unexpected failure while starting a job's threads or supervising them, the runtime:
  - records no outcome;
  - latches cancellation and stops future heartbeats;
  - joins only the threads that actually started, each for a bounded time.

  If a thread is still alive, the result is abnormal (exit 5 through the CLI). Otherwise the failure is re-raised (the CLI reports `unexpected <class>` and exits 1), so no further claim is made.
- **The abnormal exit survives cleanup failures:** once the runtime has returned an abnormal result, failures in engine disposal, signal restoration or diagnostic output cannot prevent or downgrade `exit_process(5)`.
- **Engine disposal** is pool cleanup only: it does not cancel sessions checked out by live threads. Uncommitted transactions roll back when PostgreSQL detects the disconnect after the process ends, which is not necessarily immediate.

### Logging
- **Logger:** `evidenceguard.worker`, through the existing `JsonFormatter`, which still drops message arguments, exception text and tracebacks.
- **New reviewed events:** 18 fixed events, each its own message template:
  - `worker.*`: `started`, `stopping`, `stopped`, `abnormal_stop`, `poll_failed`, `no_handlers`, `config_invalid`;
  - `job.*`: `claimed`, `succeeded`, `post_finish_error`, `retry_scheduled`, `dead`, `failed`, `cancelled`, `lease_lost`, `heartbeat_failed`, `outcome_failed`, `outcome_unknown`.
- **New allowlisted fields:** `worker_id`, `job_id`, `job_kind`, `attempt` and `error_code`. They are filled only from validated values: the worker-ID pattern, a validated `JobSnapshot`, `JobErrorCode` and exception class names.
- **Never logged:** tenant IDs, payloads, idempotency keys, URLs, SQL, exception messages or tracebacks.

### Timing defaults
These are accepted as initial engineering defaults, not measured guarantees. They are adjustable only through the Python API (`Timings`), for tests:

| Setting | Default |
|---|---|
| Idle poll | 2 s |
| Backoff | 1 s doubling to 30 s |
| Drain | 30 s |
| Cancel grace | 5 s |
| Lease-loss grace | 5 s |
| Heartbeat join | 10 s |

The 60 s lease and the 20 s heartbeat interval are M3a's.

## Consequences and limits

- **At-least-once execution.** A handler can run more than once: after a crash, lease loss, an uncertain finish or an abnormal stop. Durable effects must go through `ctx.fenced()` and be idempotent; effects outside the database can repeat.
- **No total shutdown deadline.** The drain, cancellation, grace and join waits are bounded supervisor waits, not a deadline for the whole process. `claim` and outcome recording are synchronous calls on the supervisor thread. If one blocks, the timed checks wait until it returns, and signals do not cancel it. There is no worker statement timeout in M3b, so a hung `claim` or outcome call can require external termination.
- **Delayed reclaim** is possible after a late heartbeat extended a cancelled attempt's lease, or while a terminated worker's transaction still holds the row lock.
- **Trusted handlers.** The handler wrapper is not a sandbox.
- **No production handlers yet.** The command is installable and testable but cannot claim work until M3d.
- **Verified in CI.** The tested commit is `bc5f638` (`bc5f6385ce092d1d47f69b4e8a6cd0a453e90451`) on branch `feat/worker-runtime`. It adds only prompt history after the reviewed M3b commit `6547e9f`.
  - In [CI run 38253962690](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38253962690), from logs retrieved by the external reviewer:
    - [verify on Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38253962690/job/114827089007) reported `709 passed, 77 skipped in 15.96s`;
    - [verify on Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38253962690/job/114827088937) reported `708 passed, 78 skipped in 22.18s`;
    - the [PostgreSQL 17 + pgvector integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38253962690/job/114827089078) reported `77 passed, 709 deselected in 19.63s`. That is all 77 integration tests, M3a's 63 and the worker's 14 from `tests/test_worker_postgres.py`, with no skips or failures.
  - Ubuntu passed one more database-independent test than Windows. That is consistent with the POSIX-only SIGTERM delivery test running on Ubuntu and being skipped on Windows; no individual log entry for that test was observed.
  - The [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38253962775) passed ([job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38253962775/job/114827088806): 25 commits scanned, no leaks found).
  - Earlier local Windows runs used fake stores, scripted clocks and event-controlled ordering, including the regression tests added in Prompt 61.
- **Not yet verified or delivered:**
  - M3b is not merged into `main`;
  - the production handler registry is still empty;
  - Compose is unverified;
  - M3c–M3f are not implemented;
  - overall M3 acceptance is pending.
- **Scope of the evidence:** passing tests demonstrate the tested behaviour, not a general security or performance guarantee. The limits above are unchanged.
