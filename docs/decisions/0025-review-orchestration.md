# ADR-0025: Review orchestration and atomic output

- **Status:** M5g is **feature-CI verified at `3d41f435`, not merged**
  ([evidence](#feature-ci-at-3d41f435-prompt-223)), and main publication is not authorized.
  The sequence was:
  - **Prompt 218:** implemented by Claude Code.
  - **Prompt 219:** tests corrected.
  - **Prompt 220:** accepted at external review for a local commit only
    ([external review](#external-review-prompt-220)). Until Prompt 221 no PostgreSQL test had
    run for it.
  - **Prompt 221:** feature CI at `f0d4ce92` failed one PostgreSQL test, an invalid
    cross-question test comparison
    ([f0d4ce92 evidence and correction](#feature-ci-at-f0d4ce92-and-the-abandoned-reservation-test-correction-prompts-221222)).
  - **Prompt 222:** that test corrected.
  - **Prompt 223:** the correction accepted for a corrective commit
    ([review](#external-review-of-the-test-correction-prompt-223)); feature CI for `3d41f435`
    then passed all five required jobs. Claude Code saw conclusions only; the reviewer later
    retrieved the logs and accepted the evidence in Prompt 224 ([reviewer logs](#reviewer-retrieved-3d41f435-logs-and-acceptance-prompt-224)).

  Merge, M5h, M6 and overall M5 acceptance are pending. Statements below that M5g is staged,
  unaccepted, unexecuted or blocked describe the state at the time and are historical.
- **Specification:** [accepted M5g specification](../plan.md#m5g-review-orchestration-and-atomic-output-specification-accepted-at-review-prompt-217-implementation-pending),
  G1–G15 and G17–G24 with binding clarifications A and B
  ([acceptance](../plan.md#m5g-acceptance-prompt-217)); G16 not selected.
  [Implementation status](../plan.md#m5g-implementation-status-accepted-for-a-local-commit-prompt-220-postgresql-and-ci-pending).
- **Preceding evidence:** M5a–M5f are reviewed, verified in CI and on main within their recorded
  scopes ([ADR-0024](0024-review-report-content.md) for M5f at `e7dd3be3`). That evidence is
  theirs; nothing below re-attributes it.

## Decision

Four new modules implement the accepted contract; no M5a–M5f production module, migration
`0001`–`0007`, dependency, setting, endpoint, command or production registration changes.

| Module | Owns |
| --- | --- |
| `evidenceguard_domain.review_outputs` | `ReviewOutput`, `StoredReviewOutput`, `ReviewOutputWrite`, `ReviewStatus`, `decode_stored_review_output`, two fixed errors |
| `evidenceguard_persistence.review_outputs` | `write_review_output`, `load_review_output`, `load_review_status`, eight fixed errors |
| `migrations/versions/v0008_review_outputs.py` | migration `0008` |
| `evidenceguard_worker.review` | `make_run_review_handler`, `REVIEW_WORKER_ACTOR_ID`, `MAX_ITERATIONS`, `TrustedReviewOutput`, `load_trusted_review_output`, worker errors, the orchestration |

Two existing production files change, both within the accepted scope:
`models.py` (the `review_outputs` metadata and `uq_reviews_tenant_id_id_run_review_job_id`) and
`db.py` (the G15 `transaction()` rule only).

**`run_review` remains unregistered.** `production_registry()` still claims only
`ingest_revision` and `index_revision`. Only test registries build the handler, and the factory
has no default model provider.

## How the contract is implemented

- **Values (M5g-A).** Frozen dataclasses with keyword-only constructors guarded by one fixed
  error each. A missing keyword is detected through a private sentinel default, so it is the
  value's fixed error rather than Python's `TypeError`. Types are exact; nested content is
  rebuilt with `revalidate_review_report` and every derived field is recomputed (derived fields
  cannot be passed). `created_at` is converted to UTC. Representations carry identifiers,
  digests and counts only.
- **Decoder.** Closed key set, exact column types and patterns, the printable-ASCII and size
  checks before decoding, the strict M5f decode against the stored digest, the rebuild, then
  every derived column.
- **Migration `0008`.** It first adds the `reviews` unique, then creates `review_outputs` with
  the 17 named checks, the primary key, the `(tenant_id, job_id)` unique and three `NO ACTION`
  foreign keys. Downgrade drops exactly the table, then that unique.
- **Writer (F2).** Arguments (with `JobSnapshot` and `ReviewOutput` rebuilt), fence
  association with an entry ownership recheck, binding, completeness, replay or conflict,
  insert with `job_attempt` from the fence and `created_at` by `RETURNING`, final ownership
  recheck. It never commits, rolls back, closes, retries or logs.
- **Reads (F2, F4, G3).** The actor is rebuilt and the review ID type-checked before the role
  check, and both before any session is opened. One `read_snapshot` transaction with recording
  wrappers; the missing-review and non-canonical-job checks; then one shared lifecycle/presence
  function for both loaders. `load_trusted_review_output` inherits all of it, then renders and
  compares (F3). Drift raises `ReviewRendererDriftError` and repairs nothing.
- **Orchestration (B–D).** Pure job and payload checks, the fixed actor, the M5d loader, the M5c
  planner, one fenced `record_planned_questions`, the M5e trusted reload, then each question in
  order: the Verification loop (bound 5) and the owner-only Analysis loop (bound 4) driven only
  by `plan_stage`. Requests are reconstructed exactly as in C3, with the repair reason always
  built from the call numbered `trigger`. Completion runs a second reload, the M5f build and its
  source-bound recheck, the pinned render, then `write_review_output` inside
  `ctx.fenced(finish=True)`.
- **Failures (E, E2, H).** Guarded steps keep only the failure class, run `ctx.check()` and then
  raise a fresh job error. Fenced writes classify only an escaping object that **is** the body's
  own fixed error, after leaving the context and after `ctx.check()`. Every other ordinary
  context-exit failure becomes `ReviewFenceExitError`, with no `ctx.check()` on that branch.
  Control flow and process control are never caught or converted.

## Material implementation choices

These resolve details the specification left to the implementation. None changes accepted
behaviour; each was a review question. Choices 1–4 were approved in Prompt 219, and all ten
were accepted at external review in Prompt 220.

1. **Unrecognized step failures.** The precedence rule's "fixed guarded-call error" is a new
   internal `ReviewStepError` (code `review_step_failed`). Like `ReviewFenceExitError` it is
   privacy normalization only: the runtime records `unexpected_error` (retryable). Known classes
   map as in M5g-H.
2. **`StageCallInFlightError`** (which `reserve_call` can raise and the H table does not list)
   is a retryable body classification, consistent with G6's treatment of `PlanInFlight`.
3. **Reload checks.** Each trusted reload must cover the planned questions in order and name
   this job (otherwise permanent), and its `job_attempt` must equal the attempt being run
   (otherwise the same retryable composition error as `PlanInFlight`: the state is not this
   attempt's).
4. **A committed S1 seen mid-attempt.** C4 returns `PlanReuse` stages. G4 requires the owner to
   come from the reload or this attempt's `verify_question`. An S1 that appears after the entry
   reload without a trusted owner value (possible only out-of-band) is therefore the retryable
   composition error, so the next attempt reloads it.
5. **`ctx.check()` after every guarded step**, pure steps included. This is more boundaries than
   the minimum list in M5g-E, never fewer, and it never runs on a process-control or uncertain
   context-exit path.
6. **Replay and the final check.** An identical-row replay still runs the final ownership
   recheck (read-only) before returning `replayed=True`.
7. **Completeness by shape.** The writer and the reader derive a stored stage row's shape from
   its outcome and reason (the M5e-C rule) and compare it with the wrapper's `ReportStage`
   together with the outcome, reason and four digests.
8. **Read statement timeout.** The reads set the transaction-local 30-second statement timeout
   used by the M5e reload. This bounds statements, not the read.
9. **Names.** The ORM class is `ReviewOutputRow`, to avoid colliding with the domain value. The
   private composition error has a retryable subclass rather than an instance flag, so that
   classification stays by class.
10. **`TrustedReviewOutput`** verifies the Markdown digest and size itself. An invalid
    construction is `InvalidStoredOutputError`; the loader reports any render or comparison
    failure as `ReviewRendererDriftError`.

## G15: the narrow `transaction()` change

The helper now applies the E3 rule. Across the body, `commit()`, `rollback()` and `close()`, the
first `BaseException` that is not an `Exception` is raised as the same object, and later
failures are dropped uninspected. Without process control, the ordinary object selected is the
one the previous helper selected. Once a session exists, `commit()` runs at most once,
`rollback()` at most once and `close()` exactly once. A failing `session_factory()` makes no
lifecycle call and its exception propagates unchanged (clarification B).

Nothing is logged, retried or inspected, and no rollback, disposal or commit outcome is claimed.
G16's public uncertain-finish property is not added.

**Regression evidence, run locally in Prompt 218:**

- `tests/test_transaction_process_control.py` checks all 625 phase combinations against an
  independent E3 oracle (identity and call counts).
- The same module checks 16 ordinary-only combinations against a verbatim copy of the published
  helper (same object, same calls) and session-construction failure for an ordinary error and
  each process-control type.
- It also checks that `GeneratorExit` thrown at the yield comes back as the same object, and
  pins the published helper's loss of identity.
- The existing non-database transaction, job, fence, runtime, ingest, index, API, M5d and M5e
  tests all pass unchanged in the full run.
- Their PostgreSQL counterparts were **not executed** here.

## Output atomicity, lifecycle reads and runtime uncertainty

The output row and the job's `succeeded` transition are written in one finish transaction. The
fake-session tests drive the real `transaction()`, `JobContext` and `run_worker` and cover these
cases:

- **A commit that raised before taking effect:** neither the output nor the success exists.
- **A commit that took effect but raised, or a `close()` failure after it:** both exist. The
  finish is `UNCERTAIN`, the handler raises `ReviewFenceExitError`, and the runtime's
  `fail_retryable` is refused, so `job.outcome_unknown` is logged.

Outcome-write failures are read back, never inferred from `job.outcome_failed` (clarification A):

- a failure before `COMMIT` leaves the job `running`;
- a raising commit that did not apply leaves it `running`;
- an acknowledged commit followed by a raising `close()` leaves it `succeeded`.

No runtime behaviour changed.

## Evidence attribution and verification limits

All checks below were run by Claude Code in Prompt 218 on the staged sources (commands, exit
codes and hashes are in the handoff):

- Ruff format and lint, and strict mypy.
- The focused M5g modules, and the full suite with skip reasons.
- Integration and non-integration collection.
- Baseline and candidate builds with a member comparison.
- The complete installed-wheel CI step in a fresh environment outside the checkout.

**Not established:**

- **PostgreSQL behaviour.** `test_review_outputs_postgres.py`, `test_review_handler_postgres.py`
  and `test_review_canary_postgres.py`, and every existing PostgreSQL test, were skipped: no
  `EG_TEST_DATABASE_URL`. The constraint, writer, read and end-to-end database behaviour is
  therefore unverified. `alembic check` against PostgreSQL was not run.
- **CI and review.** No CI ran and nothing is reviewed or accepted.
- **The installed-wheel assertion** imports the modules, refuses a provider-less factory and
  renders `0008` offline. It is not PostgreSQL execution.
- **Model behaviour.** The canary tests use scripted outputs. Passing them does not establish
  live-model injection resistance, and there is no production denylist.

## Remaining limitations

- **No live provider and no production review path.** `run_review` is unregistered; no endpoint,
  command, setting or enqueue path exists. M5h, M6 and overall M5 acceptance are pending.
- **M4d trusted-snapshot limitation.** The mechanisms that could close it for the `run_review`
  path now exist:
  - the handler's only retrieval is `search_snapshot` over the M5d-loaded snapshot, enforced by
    a structure test;
  - nothing recaptures the snapshot.

  It is **not closed**: the replacement-activation PostgreSQL test has not run, and the
  implementation is unreviewed. Outside that claim stay `search_current` callers, direct
  database writes, malicious in-process code, original retrieval membership and rank beyond
  M5e-J1, and the U4 discarded bytes.
- **E7 (output scope).** The output table and atomic writer now exist in code and their offline
  shape is tested. Their database behaviour is unverified, so E7 is not claimed satisfied.
- **The lease window.** It is unchanged: a fenced transaction that passed its last check may
  commit shortly after the lease expires.
- **Fixed limits:** no overall review deadline (G7) and no exactly-once provider call.
- **Uncertain finishes stay unreadable** to the handler, by design (G11, G16 not selected).

## Prompt 219: review findings and test corrections

**Status after Prompt 219.** M5g is still **staged for review and not implementation-accepted**.
It is not committed, published or CI-verified. No production, migration, model, workflow,
packaging or dependency byte changed; only tests, shared test helpers and documentation did.

**The reviewer's evidence (the reviewer's, not Claude Code's).** The reviewer:

- verified the Prompt 218 export's hash, size, lines and statistics;
- reviewed the production modules, migration, tests and this ADR against the accepted contract;
- exercised the submitted `transaction()` helper, extracted from its source, over 625 failure
  combinations, and confirmed that the 16 ordinary-only combinations select the same object and
  call sequence as the earlier helper.

The reviewer ran no project suite, installed wheel, SQLAlchemy database, PostgreSQL or CI, and
demonstrated no production defect.

**Outcome choices approved; implementation not accepted.** The reviewer approved four
implementation choices (1–4 above), as implementation choices only:

1. Unrecognized ordinary non-fenced step failures become `ReviewStepError` and reach the runtime
   as `unexpected_error`.
2. `StageCallInFlightError` is retryable.
3. A trusted reload for another attempt is refused as retryable.
4. A mid-attempt S1 without a trusted owner is refused as retryable rather than reused.

This approval does not accept the implementation as a whole.

**Finding A: constraint-test attribution.** The submitted PostgreSQL test deleted the fully
populated review and required the reported constraint to start with `fk_review_outputs_review`.
The review's bindings, planned questions and other child rows also reference it, so PostgreSQL
may report any of those references first. This was found by review, not observed in a
PostgreSQL run. The corrected tests in `tests/test_review_outputs_postgres.py`:

- **Catalogue.** Read `pg_constraint` and pin each key and foreign key of `review_outputs`:
  exact referencing columns, referenced table and columns, `NO ACTION` on update and delete,
  `MATCH SIMPLE`, not deferrable, plus the referenced `reviews` unique.
- **Isolated invalid references.** Each case first deletes the stored output in the same
  transaction, so neither of its keys interferes:
  - *missing review:* the reported constraint must be one of the two review references, an
    overlap that is documented;
  - *missing job:* one of the two job references, also a documented overlap;
  - *existing review with another existing job:* exactly `fk_review_outputs_review_job`, the
    only constraint that can refuse it.
- **Keys.** The primary key is tested with a second output for one review on an unused job. The
  `(tenant_id, job_id)` unique is tested with a second real review reusing the first review's
  job. Each comment states that the review/job binding would also refuse the row, and that
  PostgreSQL checks non-deferrable keys at row insertion before its foreign-key triggers. A
  positive control inserts the second review's row with its own job and succeeds.
- **Populated deletion.** Deleting the populated review, or its job, must fail with a
  foreign-key violation whose reported constraint references the deleted table, and every
  related row count must be unchanged. The result is not attributed to any particular output
  constraint.

**Finding B: the real persistence boundaries were not exercised.** The handler world fakes the
persistence calls, so it is orchestration evidence only. The new
`tests/test_review_output_persistence.py` calls the real `write_review_output`,
`load_review_output`, `load_review_status` and `load_trusted_review_output`. Only the SQLAlchemy
session is scripted, and the production `read_snapshot`, recording wrappers, `Fence`,
`FencedSession` and `recheck_ownership` run unchanged. It covers:

- **Read precedence:** the missing-review, non-canonical-job and lifecycle/presence precedence
  (all ten rows through all three loaders, with rendering only after a successful strict load);
  tampered rows; ordinary failures at twelve points, each giving a fixed, cause-free,
  sentinel-free `ReviewOutputDatabaseError`.
- **Read process control:** `KeyboardInterrupt`, `SystemExit` and `GeneratorExit` at the clock
  result, query-result consumption and row access. Each runs with clean cleanup, an ordinary
  cleanup failure and a later different interrupt, and the first object propagates by identity.
  Interrupts during session construction are covered too. The reads never write or commit.
- **Writer:** binding before completeness before replay or conflict; fence mismatch; ownership
  loss at entry, and at the final recheck on both the insert and replay paths;
  `LeaseLostError`, `FenceClosedError` and `JobLockTimeoutError` passing through by identity;
  only a `23505` unique violation as a conflict; no commit, rollback, close or retry; and
  process-control identity.

The SQL is matched by text and never executed, so this is boundary evidence, not database
evidence. Seven mutation probes of the real persistence module were each killed by these tests,
and the module was restored byte for byte.

**Outcome-choice tests** in `tests/test_review_handler.py` pin each approved choice with a valid
control and with cancellation or process-control precedence. Mutation probes confirm that
reverting any one choice fails its tests.

**Database status after Prompt 219.**

- **M5g PostgreSQL modules:** 54 tests written and collected, **none executed**:
  `test_review_outputs_postgres.py` 44, `test_review_handler_postgres.py` 7,
  `test_review_canary_postgres.py` 3.
- **Collected integration total:** 439, being the 385 integration tests that existed before
  M5g plus these 54. All 439 are skipped locally.
- **Correction:** the Prompt 218 total of 432 was likewise the earlier 385 plus 47 new M5g
  cases, not "432 existing" tests.

## External review (Prompt 220)

**Decision (the external reviewer's).** The M5g implementation from Prompt 218, with Prompt 219's
test corrections, is **accepted for a local commit only**.

- **Findings:** both verification findings (A, constraint-test attribution; B, real
  persistence boundaries) are resolved.
- **Outcome choices:** the four approved in Prompt 219 remain approved.
- **Remaining choices:** the other documented implementation choices above (5–10) are accepted.
- **Open decisions:** no implementation review decision remains open.

**The reviewer's evidence.** The reviewer:

- previously reviewed the Prompt 218 implementation, migration, tests and this ADR;
- previously exercised the source-extracted submitted transaction helper over 625 failure
  combinations, including the 16 ordinary-only comparisons;
- reviewed the Prompt 219 correction diff statically;
- independently verified that diff's size, lines, file and change statistics and SHA-256;
- confirmed that the export is UTF-8 without BOM, LF only and without replacement characters;
- confirmed that the revised tests explicitly account for overlapping constraints and call the
  real persistence boundaries over scripted sessions.

The reviewer did not rerun the project suite, the installed wheel, PostgreSQL or CI for
Prompt 219. The local tests, builds, wheel checks and mutation probes recorded above are Claude
Code's, tied to the versions and artifact hashes actually checked; none of them is exact-commit
CI.

**Limits of this acceptance.**

- **PostgreSQL:** no PostgreSQL behaviour is accepted as verified. All 54 M5g PostgreSQL cases
  remain written and collected but unexecuted.
- **CI:** no exact-commit CI exists yet for the local commit.
- **Not closed:** M4d and E7 are not declared closed.
- **Not authorized:** a production review path or `run_review` registration.
- **Pending:** publication, merge, M5h, M6 and overall M5 acceptance.

## Feature CI at `f0d4ce92` and the abandoned-reservation test correction (Prompts 221–222)

**Publication (Prompt 221).**

- **What was pushed:** after the preparation commit
  `f0d4ce921a4e58ce381d3f3d26e9a0a80ad94b2c` (README and threat-model status corrections),
  Mathew pushed it manually as the new branch `feat/review-orchestration`. Main was unchanged at
  `e7dd3be3`.
- **What Claude Code could see:** using anonymous API access it observed only run, job and step
  conclusions. The integration job failed at "Run integration tests" and the other four required
  jobs succeeded.
- **Access limitation (historical):** its job-log download returned HTTP 403, so it recorded no
  counts or test names.

**Logs retrieved by the external reviewer (the reviewer's observations, not Claude Code's).** All
were from commit `f0d4ce92`, branch `feat/review-orchestration`, the push event, attempt 1.

- [ci run 42205208269](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42205208269):
  - [verify (ubuntu-24.04)](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42205208269/job/127849986602):
    `4999 passed, 439 skipped in 128.52s`.
  - [verify (windows-2025)](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42205208269/job/127849986480):
    `4998 passed, 440 skipped in 183.71s`.
  - Both verify logs printed `production registry: ingest_revision, index_revision` and all
    twelve installed-wheel result lines, including "review orchestration imported and migration
    0008 rendered offline from the installed wheel".
  - [integration (PostgreSQL 17 + pgvector)](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42205208269/job/127849986506):
    `1 failed, 438 passed, 4999 deselected in 345.13s`, with 439 of 5438 collected tests
    selected.
  - [container](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42205208269/job/127849986032):
    the smoke and cleanup succeeded.
- [secret-scan run 42205208210](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42205208210):
  [Gitleaks](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42205208210/job/127849986119)
  scanned 96 commits and found no leaks.

**What those passes do not show:**

- The container smoke exercises the existing ingestion and indexing path, not M5g review
  orchestration.
- The wheel's Recall line is arithmetic and its Voyage line mocked.
- The offline `0008` SQL rendering is not database execution.

Claude Code holds no copy of the reviewer's log archive.

**Diagnosis (the reviewer's).** The one failure was
`tests/test_review_handler_postgres.py::test_a_reservation_abandoned_before_dispatch_is_retried_on_the_next_attempt`,
at its final assertion:

- **The flaw:** the final query selected every Verification call across all questions, ordered
  them by `question_id` and `sequence`, and compared the first retry with the first row. The
  pinned template begins with `RET-01`, but alphabetical order puts `BCP-01` first, so the
  assertion compared request digests of **different questions**.
- **What did pass:** the log shows the earlier assertions passing. The cancellation raised
  `JobCancelledError`, one sequence-1 started reservation from attempt 1 remained, the next
  worker run exited successfully, and the job reached `succeeded`.
- **Conclusion:** the failure is an invalid test comparison, not a demonstrated production retry
  defect.

**Correction (Prompt 222; this test only, no production byte changed).**

- **Before the retry:** the test captures the single interrupted reservation and requires its
  complete identity: tenant, review, job, the first **planned** question (template order),
  `verification`, sequence 1, `initial`/`original`, `started` and job attempt 1. It records that
  row's request digest.
- **After the retry:** it queries only that tenant, review, question and stage, ordered by
  sequence. It requires exactly sequence 1 (`initial`/`original`, still `started`, attempt 1)
  and sequence 2 (`retry`/`original`, `completed`, attempt 2), and both digests must equal the
  captured digest. The `succeeded` job assertion is kept.
- **No-dispatch proof:** the cancelling provider now records every call, and the test asserts
  zero. Raising inside `generate` alone proved nothing, because `call_validated` maps an ordinary
  provider exception to `provider_failed`.
- **Unchanged:** no hardcoded digest, template-order, planner, retry-rule or production change.

**Status.**

- **Database execution:** for `f0d4ce92`, PostgreSQL has now executed and the gate failed (one
  test). The corrected test is collected but **not executed locally**: no disposable test
  database is configured.
- **Scope of the passing jobs:** they are evidence for `f0d4ce92` only, not for the correction.
- **Prompt 220 acceptance:** it remains a historical decision, scoped to a local commit.
- **Blocked:** feature CI is not verified, and main publication remains blocked until CI passes
  on the corrected version.
- **Not claimed:** M4d and E7 are not declared closed, and M5h, M6 and overall M5 acceptance
  remain pending.

## External review of the test correction (Prompt 223)

**Decision (the external reviewer's).** The Prompt 222 correction is **accepted for a corrective
commit and feature publication**:

- the cross-question comparison defect is corrected;
- the test captures the interrupted reservation and compares only its own question and stage
  history;
- it requires the expected initial and retry reservations with the captured digest;
- it explicitly asserts zero calls to the cancelling provider.

**The reviewer's evidence.** The reviewer:

- statically reviewed the correction diff;
- independently verified its size, line count and SHA-256;
- earlier retrieved all five `f0d4ce92` job logs.

Claude Code's local checks are its own.

**Limit.** This acceptance does **not** establish that the corrected test has passed against
PostgreSQL or in CI. That verification is still pending for the corrective commit.

**Current status.**

- **`f0d4ce92`:** feature-published; four required jobs passed, and the PostgreSQL job ran and
  failed one test.
- **Correction:** accepted for a corrective commit.
- **Verification:** corrected-version PostgreSQL and CI verification are pending, and main
  publication stays blocked until that gate passes.
- **Not claimed:** M4d and E7 are not closed.

## Feature CI at `3d41f435` (Prompt 223)

**Publication.** Claude Code committed the corrective commit `3d41f435aa5cb65128751e7bee9c9ba163ae1626` (parent `f0d4ce92`, test
blob `837136d61e1ec815a1fa2324ff596e83dc55d591` unchanged from the accepted correction). Mathew
pushed it manually to `feat/review-orchestration` as a fast-forward, `f0d4ce9..3d41f43`. Main was
unchanged at `e7dd3be3`.

**Exact-SHA CI.** These are Claude Code's observations through the anonymous public API: run, job
and step conclusions only. All runs are for push event, attempt 1, branch
`feat/review-orchestration` and SHA `3d41f435`. Monitoring started at 2026-11-06T11:28:15Z and
both runs completed by 11:35:17Z.

- [ci run 42210425265](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42210425265): **success**.
  - [verify (ubuntu-24.04, Python 3.12)](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42210425265/job/127867418645): success. Reviewer's log:
    `4999 passed, 439 skipped in 77.31s`.
  - [verify (windows-2025, Python 3.12)](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42210425265/job/127867418511): success. Reviewer's log:
    `4998 passed, 440 skipped in 164.74s`.
  - Both verify logs (reviewer's) printed `production registry: ingest_revision,
    index_revision` and all twelve installed-wheel result lines, including "review
    orchestration imported and migration 0008 rendered offline from the installed wheel".
  - [integration (ubuntu-24.04, PostgreSQL 17 + pgvector)](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42210425265/job/127867418142): success. Every
    step succeeded, including step 7, "Run integration tests" (`EG_REQUIRE_INTEGRATION: "1"`,
    `uv run --locked pytest -m integration`). Reviewer's log: `439 passed, 4999 deselected in
    394.31s`, including `test_review_handler_postgres.py` 7 passing positions,
    `test_review_outputs_postgres.py` 44 and `test_review_canary_postgres.py` 3.
  - [container (ubuntu-24.04, image build and Compose smoke)](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42210425265/job/127867418591): success.
    Reviewer's log: the smoke and cleanup succeeded (ingestion and indexing only).
- [secret-scan run 42210425244](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42210425244): **success**.
  - [Gitleaks (full history)](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42210425244/job/127867418251): success. Reviewer's log: 97 commits
    scanned, no leaks.

**Access limitation (Claude Code's, historical).** Claude Code's anonymous job-log downloads
returned HTTP 403 ("Must have admin rights to Repository"), and no authentication was
changed. Claude Code itself therefore observed **none** of the following for `3d41f435`
(the reviewer's log figures above were added in Prompt 224):

- test, skip or deselection counts;
- the corrected test's individual result or any per-module M5g result;
- migration or `alembic check` output;
- installed-wheel lines, container output or Gitleaks output.

The `f0d4ce92` counts (reviewer-retrieved, above) are **not** results for this commit.

**What the job conclusions show.** The required PostgreSQL integration job's test step concluded
successfully on this exact commit, so this is the first green exact-commit PostgreSQL run for
M5g. On its own the step-level conclusion supported nothing more specific; the reviewer's
logs ([Prompt 224](#reviewer-retrieved-3d41f435-logs-and-acceptance-prompt-224)) add the counts.

**Status.**

- **Feature CI:** M5g is **feature-CI verified at `3d41f435`, not merged**. At Prompt 223 main
  publication was not authorized; Prompt 224 authorizes it subject to new gates
  ([acceptance and authorization](#reviewer-retrieved-3d41f435-logs-and-acceptance-prompt-224)).
- **Not authorized:** a production review registration or live provider.
- **Not claimed:** model quality or injection resistance; the container smoke covers ingestion
  and indexing only. M4d and E7 are not declared closed, and M5h, M6 and overall M5 acceptance
  remain pending.
- **Historical:** the failed `f0d4ce92` gate and its reviewer-retrieved evidence remain separate.

## Reviewer-retrieved `3d41f435` logs and acceptance (Prompt 224)

**Evidence (the external reviewer's observations, from logs the reviewer retrieved; separate from
Claude Code's anonymous API observations above).** All are for SHA
`3d41f435aa5cb65128751e7bee9c9ba163ae1626`, branch `feat/review-orchestration`, the push event,
attempt 1. The per-job figures are recorded under each job link in the
[Prompt 223 section](#feature-ci-at-3d41f435-prompt-223):

- **verify:** Ubuntu `4999 passed, 439 skipped`, Windows `4998 passed, 440 skipped`.
- **PostgreSQL:** `439 passed, 4999 deselected`. All 439 selected integration tests passed,
  including the 54 M5g PostgreSQL positions (7, 44 and 3).
- **Container:** the smoke and cleanup succeeded.
- **Gitleaks:** 97 commits scanned, no leaks.

**Limits of this evidence.**

- **Not named individually:** the log prints module positions, not test names, so the corrected
  `test_a_reservation_abandoned_before_dispatch_is_retried_on_the_next_attempt` result is not
  separately named. It is within the seven passing `test_review_handler_postgres.py` positions.
- **No separate migration output:** no separately printed migration or `alembic check` output
  line is recorded. The migration tests are among the passing positions.
- **What the passing jobs do not cover:**
  - the container smoke covers ingestion and indexing, not review orchestration;
  - the wheel's Recall line is arithmetic and its Voyage line mocked, and the offline SQL
    rendering is offline only;
  - no live-model quality, entailment, authenticity or injection-resistance claim follows.

**Acceptance (Prompt 224).** The external reviewer accepted the Prompt 223 evidence
documentation and independently confirmed the corrective feature gate at `3d41f435`.

**Publication authorization (subject to gates).** Mathew authorized the following, in order:

1. a local evidence commit, manually pushed with its own exact-commit feature CI;
2. only after that gate passes, a main preflight and an `--ff-only` fast-forward;
3. a manual main push with separate exact-commit main CI.

This section records the authorization; it does **not** record that any of those steps
happened.

**Unchanged.** There is no production `run_review` registration or live provider. M4d and E7
closure and overall M5 acceptance remain pending. The failed `f0d4ce92` gate stays historical.
