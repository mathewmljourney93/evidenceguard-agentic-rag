# ADR-0022: Composable capture, atomic review creation and trusted reload

- **Status:** **Implemented by Claude Code in Prompt 189, corrected in Prompt 190 (see
  [Prompt 190 corrections](#prompt-190-corrections)), test-corrected in Prompt 191 and accepted at
  external review in Prompt 191 for a local implementation commit only** (see
  [External review (Prompt 191)](#external-review-prompt-191)). Historical: until Prompt 191 the
  implementation was staged and implementation acceptance was pending, and at that acceptance
  publication, Linux verification, PostgreSQL execution and current-version CI were pending.
  **Since then:** feature branch `1bea3731` was published (Prompt 192); Ubuntu and Windows verify passed; PostgreSQL executed and failed three tests; the test corrections were staged (Prompt 193) and accepted for a corrective commit and feature publication (Prompt 194); their PostgreSQL and CI verification remain pending, and main publication remains blocked (see
  [Exact-commit CI and PostgreSQL test corrections](#exact-commit-ci-at-1bea3731-and-postgresql-test-corrections-prompts-192193) and
  [External review (Prompt 194)](#external-review-prompt-194)). No endpoint, CLI command, handler,
  setting, production registry entry or production enqueue path uses M5d: creation and reload are
  internal or test-only seams and `run_review` is not registered, so none of its controls operates
  in the application, and overall M5 acceptance is pending. PostgreSQL tests were not run locally
  (no test database is configured; see
  [Verification (Prompt 190)](#verification-prompt-190-local-windows-claude-code-historical-local-evidence)).
  Implements the
  [accepted M5d specification](../plan.md#m5d-composable-capture-and-atomic-review-creation-specification-accepted-at-review-prompt-188-implementation-pending)
  (proposed in Prompt 185, revised in Prompts 186–187, accepted at external review in Prompt 188
  with D1–D17 and the binding cleanup clarification in M5d-B1), the fourth slice of the
  [accepted M5 sequence](../plan.md#m5-implementation-sequence-accepted-at-review-prompt-170).
- **Date:** 2026-10-22
- **Builds on:** [ADR-0016](0016-snapshot-retrieval.md) (snapshot capture and its race rules),
  [ADR-0019](0019-model-call-contracts.md) (`PromptRef`) and
  [ADR-0021](0021-review-request-assembly.md) (pinned template and prompt loaders).

## Decision

M5d adds a review value module, a bounded database-failure classifier, the composable capture
seam, migration `0006` with three review tables, atomic review creation with idempotent replay,
the trusted reload, and one isolated worker module that composes them with the M5c pinned
loaders. It adds no endpoint, CLI command, production enqueue path, handler registration,
provider, live call, setting or dependency.

**What it establishes.** A review, its snapshot bindings and exclusions, its pinned template,
prompt and model configuration and its `run_review` job are committed together or not at all, in
one REPEATABLE READ, READ WRITE transaction whose visibility follows the snapshot established by
its `clock_timestamp()` read. A tenant-scoped client key replays a matching request (tenant-bound
digest) and refuses a different one. Reload rebuilds every stored value through its constructor
and recomputes and compares the stored digests and the job association. **What it does not.**
The digests detect disagreement between stored rows only; nothing protects against direct
database writes or malicious trusted in-process code. The M4d trusted-snapshot limitation closes
for review paths only once M5g obtains its snapshot solely through this reload; it is **not**
closed by this slice. Timeouts bound individual statements and lock waits, not the operation.

## Modules and public contract

| Path | Contents |
| --- | --- |
| `packages/domain/evidenceguard_domain/reviews.py` (new) | `ReviewConfiguration`, `ReviewRequest`, `CreatedReview`, `TrustedReview`; `request_canonical_object`, `request_canonical_bytes`, `request_sha256(request, *, tenant_id)`, `rebuilt_request`; the fixed review errors |
| `packages/persistence/evidenceguard_persistence/database_failures.py` (new) | `DatabaseFailureCategory`, `RETRYABLE_CATEGORIES`, `classify_database_failure`, `CommitFailureResolution`, `classify_commit_failure` |
| `packages/persistence/evidenceguard_persistence/retrieval.py` (changed) | public `capture_in_transaction` returning `RetrievalSnapshot \| SemanticOutcome \| CaptureFailure`; `capture_snapshot` unchanged in behaviour |
| `packages/persistence/evidenceguard_persistence/models.py` (changed) | `Review`, `ReviewBinding`, `ReviewExcludedRevision` |
| `packages/persistence/evidenceguard_persistence/migrations/versions/v0006_reviews.py` (new) | migration `0006` (down revision `0005`) |
| `packages/persistence/evidenceguard_persistence/reviews.py` (new) | `create_review`, `load_review`, `CommitState` |
| `apps/worker/evidenceguard_worker/review_seams.py` (new) | `ResolvedReview`, `create_review_with_artifacts`, `load_trusted_review` |

Canonical encodings (`eg-review-configuration-v1`, `eg-review-request-v1`) are
`json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)` encoded
as ASCII. The request digest takes the tenant explicitly and the seams take it only from the
validated `ActorContext`. The idempotency key never appears in a representation or error.

## Implementation choices and deviations

Routine choices within the accepted contract, **approved at external review in Prompt 191**
within the documented scope:

1. **Testable steps.** The creation steps (`_begin`, `_replay`, `_create_job`, `_insert`) and the
   imported `capture_in_transaction` are module-level names, so the control-flow tests replace
   them with recording fakes; the real steps are tested separately against recording sessions
   and, in CI, against PostgreSQL.
2. **Module-decided refusals.** A private `_Refusal` exception carries a fixed error class out of
   the steps (idempotency conflict, job conflict, inconsistent replay record). It is never a
   database error and is never classified.
3. **`capture_snapshot` preserved.** `_capture_body` now calls `capture_in_transaction` after the
   unchanged timeout and turns a `CaptureFailure` into a private `_CaptureFailed`, so `run_read`
   still reports `RetrievalDatabaseError`; the M4d phases moved unchanged into `_capture_phases`.
4. **Replay depth.** A replay checks the stored request digest, validates the job association and
   rebuilds the `CreatedReview` (any failure is `ReviewRecordInconsistentError`); it does not
   rebuild the full snapshot. Full reconstruction happens in `load_review`.
5. **Job creation.** An already visible `run_review` job for the new key is refused before
   `enqueue`; `JobIdempotencyConflictError` and `JobEnqueueRaceError` from `enqueue`, and any
   returned job other than exactly the expected new queued job, are `ReviewJobConflictError`.
6. **Process control first seen during cleanup.** It is the first process-control object of the
   attempt, so it propagates as the same object even after a committed attempt (whose
   `CreatedReview` is then not returned) and no further attempt runs; an ordinary cleanup failure
   after a commit keeps the `CreatedReview`.
7. **Session-factory failure.** With no session there is no cleanup; an ordinary failure is
   classified like a body failure, and a retryable category without normal cleanup ends with
   `ReviewConflictRetryableError` rather than another attempt.
8. **Reload recording session.** `load_review` wraps each session in a private
   `_RecordingSession`, and (since Prompt 190) each result its `execute` returns in a private
   `_RecordingResult`, so the first process-control object raised inside `read_snapshot` (while
   executing, consuming a result or cleaning up) or by the reload body is recorded and re-raised
   even if the helper's cleanup then raises an ordinary exception or a later interrupt.
9. **Seam artifact check.** `create_review_with_artifacts` loads the pinned template and both
   prompts before any session, so an unregistered digest is `ReviewArtifactsUnavailableError`
   without database work.

**Migration-head pins (resolved in Prompt 190).** Migration `0006` changes the Alembic head and
the table set. In Prompt 189 three test modules outside that prompt's authorized paths still
pinned head `0005` (four non-integration tests failed locally); Prompt 190 explicitly authorized
updating them, as recorded below.

## Prompt 190 corrections

**Reviewer evidence (Prompt 190).** The external reviewer verified the Prompt 189 export's size,
line count and SHA-256, inspected the implementation and the relevant tests, and inspected the
published source of the public `read_snapshot` helper and the existing migration-head tests. The
reviewer's probes used extracted submitted functions with simulated collaborators; they did not
import the complete project or execute SQLAlchemy, PostgreSQL, the project suite, builds or
installed wheels. M5d implementation is not yet accepted.

**Finding A: process control while consuming `read_snapshot`'s setup result.** `read_snapshot`
reads the clock with `execute(...).scalar_one()`. The submitted `_RecordingSession` recorded only
exceptions raised by `execute`, `rollback` and `close`, so an interrupt raised by `scalar_one()`
before the helper yielded was not recorded: an ordinary rollback failure in the helper's cleanup
then surfaced as `ReviewDatabaseError`, and a later cleanup interrupt replaced the first object.
In the reviewer's isolated probe (the extracted `_Load`, `_RecordingSession`, `_recording` and
`load_review` with the published helper and simulated sessions), `KeyboardInterrupt`,
`SystemExit` and `GeneratorExit` from the clock result were preserved with normal cleanup but not
with an ordinary or interrupting cleanup failure: 3 passed, 6 failed. **Correction:** results
returned through the recording session are wrapped in `_RecordingResult`, which records process
control raised by attribute access, method calls (`scalar_one`, `first`, …) and iteration before
re-raising it; ordinary exceptions pass through unchanged, so SQL, result semantics and the fixed
review errors are unchanged, and the public `read_snapshot` helper and its signature are reused
as before.

**Finding B: timestamp-validation failures.** `capture_in_transaction` called
`captured_at.utcoffset()` outside any guard, so a `datetime` whose `tzinfo` raised an ordinary
exception leaked it (the reviewer's sentinel `PRIVATE_CLOCK_MARKER` surfaced in a
`RuntimeError`). **Correction:** a private `_is_aware_datetime` check treats an ordinary failure
while reading the timestamp as invalid, and the fixed `InvalidRetrievalRequestError` is raised
fresh after leaving the guard (no cause, context or original text). Actor, input and role
precedence are unchanged, no SQL runs for an invalid timestamp, and process control propagates
as the same object. This is error normalization for supported inputs, not a sandbox.

**Migration-head pins.** Applied after inspecting the Prompt 189 proposal: the current head is
`0006` (with `0006` following `0005` and `v0006_reviews.py` packaged); the current table sets gain
the three review tables; readiness uses `0006` as the current head, with `0005` now a
previous-head refusal, `0007` the future-head case and `("0005", "0006")` the multiple-head case.
Tests of historical migration `0005` and older downgrade ranges are unchanged, and readiness
production code is unchanged.

**PostgreSQL coverage strengthened (written, not executed).** The concurrency test now proves the
conflicting path: the second creation's own review insert is reached (a test-owned
`before_cursor_execute` event) while the first creation's row is inserted and uncommitted, and the
second must run exactly two attempts before replaying. *(Prompt 191 correction: the submitted
assertion counted that review insert after execution; the second creation's review INSERT is
attempted once and rejected by the conflict, so it never executes successfully — see
[Prompt 191 test corrections](#prompt-191-test-corrections-and-verification).)* The atomicity test
that failed after every insert is renamed accordingly, and new tests fail after the job insert but
before the review insert, and after the review insert but before the binding or exclusion rows.
A real-database test fixes the generated review ID with an existing `run_review` job for its key
and asserts `ReviewJobConflictError` with no row change. The connection-default test now uses a
one-connection `QueuePool` and checks that the same backend served the creation before reading
the defaults.

**Regression classification.** The finding-specific tests in `tests/test_review_creation.py`
(selected with `-k "reload_setup or reload_execute or reload_cleanup or capture_timestamp"`, 21
tests) ran against isolated copies of the submitted `reviews.py` and `retrieval.py` (the exact
blobs of tree `0090ecdf`, placed first on `PYTHONPATH`; import locations confirmed) and against
the corrected modules. Submitted: **7 failed, 14 passed**. The failures reproduce the findings:
six are Finding A (each of the three interrupt kinds with an ordinary or an interrupting cleanup
failure; the three normal-cleanup cases passed, matching the reviewer's 3 passed, 6 failed) and
one is Finding B (the private ordinary failure). The 14 passes are controls and new coverage
(execute, body and cleanup interrupts, ordinary setup failures, timestamp process control, and
naive, invalid and valid timestamps). Corrected: **21 passed**. The reviewer's extracted-function
probe was not a project test.

## External review (Prompt 191)

**Decision.** The external reviewer accepted the corrected M5d implementation in Prompt 191 for a
local implementation commit only, subject to the binding PostgreSQL test correction below. The
implementation choices above are approved within the documented scope, including replay depth,
module-level test seams, private refusals, session-factory failure handling and the recording
session and result wrappers. Acceptance does not establish PostgreSQL execution, Linux
verification, current-version CI, production use or overall M5 acceptance; publication and merge
are not authorized.

**Reviewer evidence.** The reviewer independently verified the Prompt 190 export's size (79,170
bytes), line count (970), SHA-256
(`4333e9ca79be20111580638d76b22cee47ca165b6b1d17d8067848072fdb02f8`), eleven-file scope, +587/−79
statistics and UTF-8/LF encoding; inspected the corrections, the migration-head updates and the
strengthened database tests; and inspected the SQLAlchemy 2.1.1 execution source to confirm that
`after_cursor_execute` follows successful cursor execution, so a rejected INSERT does not reach
that event. The reviewer ran 26 isolated checks with extracted corrected functions, the published
`read_snapshot` helper and simulated collaborators: 20 reload checks (clock-result and
row-attribute process control for `KeyboardInterrupt`, `SystemExit` and `GeneratorExit` with
normal, ordinary-failure and interrupting cleanup, plus two ordinary setup-failure controls) and
6 capture checks (ordinary timestamp-validation failure and privacy, three process-control
identities, naive rejection and valid acceptance); all 26 passed. These were extracted-function
checks with simulated collaborators, not imports or execution of the complete project,
SQLAlchemy or a database; the reviewer ran no project suite, build, installed-wheel check,
PostgreSQL, Docker or provider call. Claude Code's Prompt 190 project checks remain separately
attributed historical local evidence.

## Prompt 191 test corrections and verification

**Concurrency counters (binding correction).** In
`test_concurrent_creations_with_one_key_produce_one_review`, the helper counts statements after
successful execution, but the second creation's conflicting review INSERT is rejected and its
replay transaction inserts no review, so the submitted expectation of one counted review insert
was wrong. The test now asserts separately, on the second creation's engine: exactly two
transactions (attempts, counted after their `SET TRANSACTION` executed); exactly one
**attempted** review INSERT (counted by its `before_cursor_execute` listener, which also signals
that the conflicting path was reached before the first creation is released); and **zero
successfully executed** review INSERTs (`after_cursor_execute`). The final database state is one
review and one `run_review` job, the first result is the creation and the second the matching
replay with the same review and job IDs. The bounded synchronization is unchanged. Test-only;
no production transaction, retry or SQL behaviour changed.

**Row-access regression.** A public `load_review` test reads the review row in the reload body
through a row whose attribute access raises a designated `KeyboardInterrupt`, `SystemExit` or
`GeneratorExit`, with normal cleanup, an ordinary cleanup failure and a later cleanup interrupt:
the first object propagates by identity in all nine cases. It also passes against the Prompt 189
modules (the body's own handler already recorded that case), so it is new coverage, not a
reproduced defect.

**Local verification (Prompt 191, Windows, Claude Code; locked offline, no database URL).** Only
`tests/test_reviews_postgres.py` and `tests/test_review_creation.py` changed among code and tests;
every production, migration, model, packaging, workflow and head-pin-test blob is identical to the
accepted Prompt 190 tree `2fbb2fd5`. `ruff check .` clean; `ruff format --check .` 211 files
formatted; strict `mypy` no issues in 168 source files. Row-access regression: 9 passed (also 9
passed against the Prompt 189 modules). Focused command (`test_review_creation`,
`test_review_values`, `test_database_failures`, `test_reviews_postgres`, `test_persistence`,
`test_readiness`, `test_packaging`): 298 passed, 26 skipped (PostgreSQL). Full suite: **3635
passed, 337 skipped, 0 failed** (335 PostgreSQL tests, one symbolic-link test and one POSIX-only
signal test); collection 335 integration and 3,637 non-integration tests (3,972). **PostgreSQL:
not run** — the corrected concurrency test and every other M5d database test remain unexecuted
until exact-commit CI. No build or installed-wheel check was repeated: production blobs are
unchanged, so the Prompt 190 build and installed-wheel results stand as historical local evidence,
not exact-commit CI.

## Exact-commit CI at `1bea3731` and PostgreSQL test corrections (Prompts 192–193)

**Failed feature CI (Prompt 192).** Feature branch `feat/review-creation` was published at
`1bea3731f965c4555b9dc6bf0d9fa64447bf3789` (the Prompt 191 implementation commit `755c13a7` plus a
history-only commit). Its push runs, attempt 1 for that exact SHA:
[ci 39739061688](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39739061688) (failure) and
[secret-scan 39739061684](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39739061684) (success). Claude Code observed only the API run,
job and step conclusions; its job-log download returned HTTP 403. The external reviewer then
independently retrieved the run records, job metadata, all five job logs and the relevant
published source (recorded in Prompt 193); the results below are theirs, and they are results for
`1bea3731`, not for the corrections in this section.

| Job | Reviewer-observed result |
| --- | --- |
| [verify (ubuntu-24.04)](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39739061688/job/119691602245) | 3637 passed, 335 skipped; format, lint, mypy, tests, build and installed-wheel steps succeeded |
| [verify (windows-2025)](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39739061688/job/119691602154) | 3636 passed, 336 skipped; the same required steps succeeded |
| [integration (PostgreSQL 17 + pgvector)](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39739061688/job/119691602147) | **3 failed, 332 passed, 3637 deselected** |
| [container](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39739061688/job/119691601997) | success |
| [Gitleaks](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39739061684/job/119691601837) | 83 commits scanned, no leaks |

Both verify logs printed these nine installed-wheel result lines: "offline embedding, canonical
storage and indexing modules ran from the installed wheel"; "retrieval modules imported and fusion
ran from the installed wheel"; "evaluation modules imported and Recall@5 = 2/3 computed from the
installed wheel"; "Voyage adapter validated a mocked response from the installed wheel";
"model-call contracts classified a scripted fake response from the installed wheel"; "provenance
matched a quote and derived a status from the installed wheel"; "review template, prompts and
request assembly ran from the installed wheel"; "offline migration SQL rendered from the installed
wheel"; and "offline review migration SQL rendered from the installed wheel". (The earlier local
count of ten lines included the production-registry line; it is Claude Code's historical local
observation, not independently confirmed here.) The container smoke reported: effective build
context 109 files with 19 planted fixtures excluded; database healthy, migrations completed and API
healthy; upload 202 and ingestion succeeded with two verified active chunks; duplicate upload 200
with the same revision; one offline backfill job, two embeddings and a ready index; idle worker
exit 0 without OOM; smoke succeeded. These are the smoke's reported checks; it does not exercise
M5d review creation. The Recall line is arithmetic and the Voyage line mocked; none of these
results establishes live-model quality, injection resistance or production readiness.

**The three failures** (all in `tests/test_reviews_postgres.py`; diagnoses from the reviewer's log
and source inspection):

1. `test_tenants_are_isolated`: the corpus fixture leaves an ingestion job queued; the helper ran
   the worker once for another tenant's revision, the worker claimed the older job, the target
   revision stayed inactive and the indexing enqueue raised `IndexSourceNotEligibleError`. A test
   fixture defect.
2. `test_an_activation_committed_after_the_snapshot_is_established_is_not_bound`: the held
   attempt's `review_bindings` insert failed with SQLSTATE `40001` (the foreign-key check's
   key-share lock on `document_revisions` met the concurrently committed supersession); creation
   retried in a fresh transaction as accepted, the replacement was active but unindexed, and the
   fresh attempt correctly raised `SnapshotNotReadyError`. The test's expectation was wrong, not
   the creation behaviour.
3. `test_creation_returns_its_pooled_connection_with_default_settings`: the listener matched every
   statement containing `clock_timestamp`, which includes the job enqueue's values as well as the
   capture clock read, so it recorded the same backend twice. A test observation defect.

**Per-attempt visibility versus persisted bindings (clarification).** Snapshot visibility is fixed
within each attempt. Only the successfully committed attempt's snapshot becomes the persisted
review snapshot; a rolled-back attempt's `captured_at` and bindings are not promised to survive a
fresh-transaction retry. Once a review has committed, later revision activation does not change its
stored bindings. This clarifies the accepted contract; the retry, classification and transaction
rules are unchanged.

**Corrections (Prompt 193, test-only; accepted for a corrective commit and feature publication
in Prompt 194; not yet PostgreSQL-verified or CI-verified).**

- *Target-specific completion.* A test helper `_complete` runs the worker one claim at a time until
  the **target** job has succeeded. It counts all other queued jobs whose kinds the registry can
  run (it does not establish their queue position relative to the target); its loop bound is that
  count plus one, and the caller limits the permitted other queued fixture work (`other_queued`).
  More such work than permitted, a failed target attempt or an exhausted bound fails clearly.
  *(Prompt 194 wording correction: earlier text said the bound was the jobs "actually ahead of"
  the target, which the query does not establish.)* `_ingest` requires the target revision
  to end `active`; `_index` requires it to be `active` before enqueueing and the target index to
  end `ready`. The tenant-isolation test declares the corpus fixture's pending ingestion job as the
  one other queued job; fixtures that need pending revisions are not drained.
- *Concurrent activation.* The misleading test is replaced by three: (a) a concurrent replacement
  left unindexed: two attempts, one attempted and zero successfully executed `review_bindings`
  inserts, the one rejected statement being that insert with `40001`, then
  `SnapshotNotReadyError` and no review, `run_review` job or child row; (b) a concurrent
  replacement fully ingested and indexed before the held attempt is released: the same `40001`,
  then a committed review bound only to the replacement, one review, one binding, one
  `run_review` job (the committed attempt's) and no exclusion row; (c) a review committed before
  a replacement is activated: its reloaded bindings, snapshot and digest and job identity are
  unchanged. Synchronization uses bounded events with `finally` release and listener cleanup;
  failed statements are recorded by a test-owned `handle_error` listener, attempted ones before
  execution and successful ones after it.
- *Pooled connection.* The listener records the backend of every creation statement, and the test
  requires the nonempty set to equal the backend that then serves the settings read; the
  one-connection `QueuePool` and the four default-setting assertions are unchanged.

The Prompt 191 local-commit acceptance stays a historical, scoped decision; the feature CI gate at
`1bea3731` failed, and main publication remains blocked until corrected CI passes and is reviewed.

**Local verification (Prompt 193, Windows, Claude Code; locked offline, no database URL).**
Only `tests/test_reviews_postgres.py` changed among code and tests; every production, migration,
model, dependency, packaging, workflow and other test blob is identical to `1bea3731`. `ruff check
.` clean; `ruff format --check .` 211 files formatted; strict `mypy` no issues in 168 source files.
Focused command (`test_reviews_postgres`, `test_review_creation`, `test_review_values`,
`test_database_failures`, `test_persistence`, `test_readiness`, `test_packaging`): 298 passed, 28
skipped (PostgreSQL). Full suite: 3635 passed, 339 skipped, 0 failed (337 PostgreSQL tests, one
symbolic-link test and one POSIX-only signal test); collection 337 integration (one test replaced
by three) and 3,637 non-integration tests (3,974). **PostgreSQL: not run** — the corrected and
new database tests are written but unexecuted; local skips prove nothing about them. No build or
installed-wheel check was repeated: production and packaging blobs are unchanged, and the passing
`1bea3731` verify jobs remain the exact-commit evidence for that published version.

## External review (Prompt 194)

**Decision.** The external reviewer accepted the Prompt 193 test corrections for a commit and
feature-branch publication, pending actual PostgreSQL and exact-commit CI results. They are not yet
PostgreSQL-verified, and main publication remains blocked pending successful CI and subsequent
review. The independently retrieved failed-CI evidence for `1bea3731` above is unchanged.

**Reviewer evidence.** The reviewer independently checked the Prompt 193 export's size (63,687
bytes), line count (552) and SHA-256
(`0955695679822bb5d65782be81dea2fccd920db64d0ae8e7b5f0d80fd33e697b`), inspected the complete diff,
applied the test patch to the published `1bea3731` source and verified the resulting test blob
`981d7f209967dd340a44cfe5417eea1aa2db34ec`, and ran eight isolated checks of the extracted
`_complete` helper's control flow with substitutes for database operations (target first; older
job first; target before another queued job; excess queued work; failed target; retrying target;
exhausted bound; worker error), all passing. The reviewer did not run the project suite,
PostgreSQL, a build, Docker or an installed-wheel check. These isolated checks do not verify SQL
execution, queue ordering, foreign-key behaviour or either serialization race.

**Prompt 194 changes.** Documentation only (status wording, this section and the `_complete`
bound description); `tests/test_reviews_postgres.py` keeps the reviewed blob. The Prompt 193 local
checks above are historical local evidence; no application test, build or installed-wheel check
was repeated for these documentation adjustments.

## Verification (Prompt 190, local Windows, Claude Code; historical local evidence)

Locked offline environment, no database URL configured.

- `uv run --locked --offline ruff check .`: all checks passed; `ruff format --check .`: 211 files
  already formatted; `mypy` (strict): no issues in 168 source files.
- Finding regressions: submitted copies 7 failed, 14 passed; corrected 21 passed (classified in
  [Prompt 190 corrections](#prompt-190-corrections)).
- Focused command (the four M5d test modules, `test_packaging`, `test_retrieval_store`,
  `test_retrieval_orchestration`, `test_retrieval_contracts`, `test_retrieval_postgres`,
  `test_jobs`, `test_persistence`, `test_readiness` and `test_persistence_postgres`): **685
  passed, 87 skipped** (PostgreSQL tests).
- Full suite: **3626 passed, 337 skipped, 0 failed**: 335 PostgreSQL tests skipped
  (`EG_TEST_DATABASE_URL` not set), one symbolic-link test and one POSIX-only signal test. The four
  Prompt 189 head-pin failures are resolved. Collection: 335 integration and 3,628
  non-integration tests (3,963 in total); `tests/test_reviews_postgres.py` now has 26 integration
  tests.
- **PostgreSQL: not run.** None of the M5d database tests, including the strengthened
  concurrency, atomicity, existing-job and pooled-connection tests and the updated migration-head
  expectations in `tests/test_persistence_postgres.py`, has executed against a database; they await
  exact-commit CI.
- Offline `uv build` of the staged tree compared with a `git archive` build of `76f0b2c0`: wheel
  104 → 109 and sdist 211 → 221 members with only the M5d additions and changes (the sdist now also
  changes the three head-pin test modules); all 16 `sample_data` files byte-identical. Compared
  with the submitted Prompt 189 build, the wheel changes only `retrieval.py`, `reviews.py`,
  `METADATA` and `RECORD`.
- The complete installed-wheel step extracted from `.github/workflows/ci.yml` ran in a fresh
  environment outside the checkout (hashed offline requirements, wheel with `--no-deps`): exit 0,
  all ten lines. A direct probe with the installed wheel's interpreter (`python -I`, modules from
  `site-packages`) passed: the clock-result interrupt preserved by identity for all nine
  combinations of `KeyboardInterrupt`, `SystemExit` and `GeneratorExit` with normal, ordinary-failure
  and interrupting cleanup, plus controls (ordinary setup failure is `ReviewDatabaseError`; a
  raising `tzinfo` gives a fresh `InvalidRetrievalRequestError` without the private text; an
  interrupting `tzinfo` propagates as the same object).

Not run: Linux, CI, PostgreSQL, Docker, the container smoke, any provider, network or live model
call.

## Verification (Prompt 189, local Windows, Claude Code; historical)

Historical results for the submitted Prompt 189 tree; superseded by the Prompt 190 verification
above. Locked offline environment, no database URL configured.

- `uv run --locked --offline ruff check .`: all checks passed; `ruff format --check .`: 211 files
  already formatted.
- `uv run --locked --offline mypy` (strict): no issues in 168 source files.
- The three new non-integration modules (`tests/test_review_values.py`,
  `tests/test_database_failures.py`, `tests/test_review_creation.py`): **172 passed**.
- Focused command (those three, `tests/test_reviews_postgres.py`, `test_packaging`,
  `test_retrieval_store`, `test_retrieval_orchestration`, `test_retrieval_contracts`,
  `test_retrieval_postgres`, `test_jobs`, `test_persistence` and `test_readiness`): **4 failed,
  659 passed, 62 skipped**. The four failures are the out-of-scope head and table-set pins listed
  above; the skips are PostgreSQL tests.
- Full suite: **4 failed, 3600 passed, 333 skipped**: the same four failures; 331 PostgreSQL
  tests skipped (`EG_TEST_DATABASE_URL` not set), one symbolic-link test and one POSIX-only signal
  test. Collection: 331 integration and 3,606 non-integration tests (3,937 in total); the 23 new
  integration tests are the 22 in `tests/test_reviews_postgres.py` and the capture equivalence
  test.
- **PostgreSQL: not run.** No M5d database behaviour (atomicity, replay, concurrency, MVCC races,
  tampered rows, constraints, migration `0006` upgrade, downgrade and `alembic check`) has
  executed against a database. The offline migration SQL was rendered and its 49 constraint names
  match the model DDL, without a database.
- Canonical bytes and digests in the tests are hand-written literals whose SHA-256 values were
  computed independently with the standard library, not by calling the code under test.
- Offline `uv build` of the staged tree compared with a `git archive` build of `76f0b2c0`: wheel
  104 → 109 members (added the five new modules; changed only `models.py`, `retrieval.py`,
  `METADATA` (its long description is the README) and `RECORD`; nothing removed); sdist 211 → 221
  members (added the five modules, this ADR and four test modules; changed only `PKG-INFO`,
  `README.md`, `models.py`, `retrieval.py`, `tests/test_packaging.py` and
  `tests/test_retrieval_postgres.py`; nothing removed); all 16 `sample_data` files and the pinned
  template and prompt files byte-identical.
- The complete installed-wheel step extracted from `.github/workflows/ci.yml` ran in a fresh
  environment outside the checkout (locked non-development requirements exported with hashes and
  installed offline with `--require-hashes`, the wheel installed with `--no-deps`), once for a
  preliminary build and again for the wheel rebuilt from the final staged tree: exit 0 both times,
  all ten lines printed including "offline review migration SQL rendered from the installed wheel",
  with the production registry still exactly `ingest_revision` and `index_revision`.

Not run: Linux, CI, PostgreSQL, Docker, the container smoke, any provider, network or live model
call.

## Limits and later-slice obligations

- Creation and reload are trusted internal seams; M5h owns any transport and M5g the handler and
  orchestration, which must obtain the snapshot only through `load_trusted_review`.
- `Session.invalidate()` reaches only connections still associated with the session's
  transaction; no physical disposal or pool quarantine is claimed.
- An unknown `COMMIT` outcome is never retried automatically; the caller may repeat the request
  with the same key, which replays if the earlier commit succeeded.
- M5e stores stage calls and outputs; M5f the report representation; M7 measures live behaviour.
