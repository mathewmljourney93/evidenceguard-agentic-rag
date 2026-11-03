# ADR-0023: Stage and call-reservation persistence

- **Status:** **Implemented by Claude Code in Prompt 200, corrected in Prompt 201 after external
  review (exact question validation and nested aggregate rebuilds; see
  [Prompt 201 corrections](#prompt-201-corrections)); accepted at external review for a local
  implementation commit only in Prompt 202 ([review](#external-review-prompt-202)), including the
  recorded implementation choices. Publication, PostgreSQL execution and exact-commit
  current-version CI remain pending.** OpenAI Codex recovered the state, recorded acceptance and
  prepared the local commit. Implements the
  [accepted M5e specification](../plan.md#m5e-stage-and-call-reservation-persistence-specification-accepted-at-review-prompt-199-implementation-pending)
  (proposed in Prompt 196, corrected in Prompts 197–198, accepted at external review in Prompt 199
  with E1–E20 and binding clarifications A and B), the fifth slice of the
  [accepted M5 sequence](../plan.md#m5-implementation-sequence-accepted-at-review-prompt-170).
  No endpoint, CLI command, handler, setting, production registry entry or production enqueue path
  uses M5e, `run_review` stays unregistered, so none of its controls operates in the application.
  The report output stays allocated to M5f/M5g (E7), and overall M5 acceptance is pending.
- **Date:** 2026-10-23 (implementation); acceptance recorded 2026-11-04 (Prompt 202)
- **Builds on:** [ADR-0007](0007-durable-job-core.md) (the M3 fence and `recheck_ownership`),
  [ADR-0016](0016-snapshot-retrieval.md) (snapshot retrieval and its evidence checks),
  [ADR-0019](0019-model-call-contracts.md) (model-call values),
  [ADR-0020](0020-provenance-validation.md) (provenance values and rechecks) and
  [ADR-0022](0022-review-creation.md) (reviews, the trusted review reload and the read-boundary
  pattern).

## Decision

M5e adds a pure domain module, a persistence module, migration `0007` with four tables, and the
extracted evidence-recheck helper in the M4d retrieval module. It adds no output table or writer,
endpoint, CLI command, handler registration, provider, live call, setting or dependency.

**What it establishes.** Every planned question, its evidence, every provider-call reservation
and every committed stage of a review is stored through the caller's M3 fence, bound to the
review's canonical `run_review` job, with ownership rechecked at entry and after the last write.
At most three reservations and one repair per stage exist across job attempts; an abandoned
`started` reservation consumes budget; a committed stage is the only reusable success; identical
replay is a no-op and a differing replay a fixed conflict. A successful call and its stage are
written atomically, and an Analysis failure never alters a committed Verification. The trusted
reload rebuilds every stored value, revalidates every history and shape, and rechecks evidence
against database chunks and content with the M5b rechecks.

**What it does not establish.** Template origin of the planned questions, the original retrieval
execution, relevance or ranking, request reassembly before dispatch (a worker obligation), the
U5/U6 size assertions, or the bytes and original binding of a U4 stage's discarded evidence. It
makes no entailment, authenticity or injection-resistance claim, and no review can become
`completed` until M5f/M5g add the output slice.

## Modules and public contract

| Path | Contents |
| --- | --- |
| `packages/domain/evidenceguard_domain/review_stages.py` (new) | enumerations, `PlannedQuestionSet`, `EvidenceRecord`, `CallRejection`, `CallRecord`, `StageRecord`, `StageHistory` (V1–V12), the plan variants and `plan_stage` (T0–T9), `StageState`, `TrustedQuestionStages`, `TrustedStages`, the five canonical encodings and the bounded strict decoders |
| `packages/persistence/evidenceguard_persistence/review_stages.py` (new) | `record_planned_questions`, `read_stage_state`, `record_evidence`, `reserve_call`, `complete_failed_call`, `commit_verified`, `commit_analyzed`, `commit_unresolved`, `load_trusted_stages` and the persistence errors |
| `packages/persistence/evidenceguard_persistence/retrieval.py` (changed) | `recheck_bindings`, `load_snapshot_evidence`, `RetrievedEvidenceRow`, `EvidenceRecheckFailure` and `recheck_evidence_in_transaction`; `retrieve_with_vectors` reuses the two steps |
| `packages/persistence/evidenceguard_persistence/models.py` (changed) | `ReviewPlanQuestion`, `ReviewQuestionEvidence`, `ReviewStageCall`, `ReviewStageResult` |
| `packages/persistence/evidenceguard_persistence/migrations/versions/v0007_review_stages.py` (new) | migration `0007` (down revision `0006`) |

The successful-completion APIs take the explicit question (clarification A):
`commit_verified(fence, review_id, question_id, *, sequence, result, verified)` and
`commit_analyzed(fence, review_id, question_id, *, sequence, result, analyzed, owner)`. B3 selects
the call by `(job.tenant_id, review_id, question_id, fixed stage, sequence)`; B4 then binds the
result's question, B7 the content's identity and B8 the owner. A well-formed U4 stage has no
evidence row and no calls, reloads as valid, replays identically as a no-op after E1–E8, and
cannot be reopened by `record_evidence` (clarification B).

The domain module imports only the standard library and the domain modules `evidence`, `jobs`,
`model_calls`, `provenance` and `retrieval` (no `evidenceguard_agents`, also not lazily). The
persistence module imports the domain, `document_views`, `jobs`, `models`, `retrieval` and
SQLAlchemy. Packaging tests pin both boundaries.

## Values, state machine, persistence and reload

- **Values** follow M5e-B1: frozen dataclasses with keyword-only validating constructors, exact
  types, nested values rebuilt and required to equal the input, derived fields never accepted,
  UTC datetimes, fresh fixed errors without cause or context, and text-free representations.
  Timestamps are audit values only (V12): a call completed "before" it started is accepted.
- **Encodings** follow M5e-B2 exactly, including `float.hex()` scores, recomputed `Fraction`
  fused scores, the integer range 0…2,147,483,647 (lexical and magnitude checks) and the
  admission narrowing for inherited integers. The two maximal-size literals were derived
  independently twice in the tests (by encoding test-owned maximal dictionaries and by byte
  arithmetic without `json`): **1,135,720** and **3,090,153** bytes, matching the accepted
  values, so there is no size discrepancy.
- **State machine.** `StageHistory` enforces V1–V12; V5/V6 are checked by requiring every call to
  be what the plan of its prefix allowed. `plan_stage` is total over valid histories.
- **Persistence** follows M5e-E/F/G/H: argument checks, fence association, the ordered checks
  (E1–E8, B1–B9 or the per-API rules), replay, the mutation preconditions M1–M3, the writes and
  the final ownership recheck. The completion update is guarded by key, `started` and the current
  attempt.
- **Reload** follows M5e-J/J1 in one read-only REPEATABLE READ transaction, with M5d's
  recording wrappers so the first process-control object survives cleanup by identity.

## Implementation choices and deviations (for review)

The following recorded choices are approved at external review in Prompt 202 within the scope
of the local implementation commit only; PostgreSQL execution and exact-commit CI remain pending.

1. **Error placement.** The two domain errors and a common base `ReviewStageError` live in the
   domain module; the thirteen persistence errors subclass it in the persistence module (M5d put
   all its errors in the domain). Codes and meanings are as specified.
2. **Additional public names.** The domain module also exposes `StageShape` (a derived `shape`
   field on `StageRecord`), `plan_without_stage` (the plan of the calls without the committed
   stage, used for the M5e-C shape rule), `completion_shape_holds`, `CallRejection.stage_reason`
   (the M5b-F mapping), `PlannedQuestionSet.position`, the `revalidated_*` helpers used by the
   write APIs' argument checks, `dependency_canonical`/`dependency_sha256`,
   `plan_question_canonical`/`plan_question_sha256`, `encode_verified`/`encode_analyzed` and the
   three decoders.
3. **Unspecified error choices.** A verification reservation or U5 without a stored evidence row
   is `StageDependencyError` (evidence is the verification dependency); a recheck returning a job
   of another tenant and a missing review are `StageFenceMismatchError`; a fence whose `session`
   is not exactly a `FencedSession` or whose `job` is not exactly a `JobSnapshot` is an argument
   error (`InvalidStageRequestError`); an impossible stage/reason pair (`evidence_too_large` on
   analysis, `verification_unresolved` on verification) is an argument error.
4. **`commit_unresolved` precedence.** A committed stage with another outcome or reason is
   `StageConflictError` before the references are derived, because a committed success makes the
   history without its stage invalid (V9). Otherwise the derived shape decides
   (`StagePlanMismatchError`/`StageDependencyError`) and replay compares every reference.
5. **Replay and the final recheck.** The final ownership recheck also runs on a replay no-op
   (stricter than "after the last write"). `read_stage_state` writes nothing and rechecks
   ownership at entry only; it applies the E7 classification and digest checks.
6. **Unique violations.** `23505` is read from the driver diagnostics with a guarded local
   reader, because `database_failures.py` was not an authorized path; every other failure,
   including a foreign-key violation, is `StageDatabaseError`.
7. **Evidence recheck precedence.** A structurally invalid snapshot or item tuple is
   `InvalidRetrievalRequestError` (M5e-J1 step 2), whereas M4d's `check_retrieval_access` raises
   `InvalidSnapshotError` for a snapshot. `RetrievedEvidenceRow` validates its identifiers with
   the fixed M4d error, so an invalid row becomes `snapshot_inconsistent` at the same point as
   before. `load_snapshot_evidence` builds every row in the requested (fused) order before
   `_items` builds the result items; because a `RetrievedChunk` cannot fail once its evidence row
   is valid, results, outcomes and error precedence of `retrieve_with_vectors` are unchanged (the
   existing M4d tests pass unmodified).
8. **Reload details.** The reload sets `SET LOCAL statement_timeout = 30000` itself (it is the
   caller the helper's precondition names). After its rows are read, any ordinary failure while
   rebuilding them is `StageRecordInconsistentError`; the helper reports database failures as
   values (`StageDatabaseError`). It duplicates M5d's small private recording wrappers instead of
   importing private names from `reviews.py`.
9. **Schema text.** `models._sql_list` renders enumeration lists sorted, so the `IN (…)` lists in
   the constraints are alphabetical (semantically identical to the specification); the two
   `stage_reason` expressions are one check named `stage_reason`; the migration spells the
   constraint text out literally (rendered once from the models), as `0006` does.
10. **Tests.** The planner enumeration checks every one-step extension of every valid history of
    up to two calls at current attempts 1–3 (142,692 histories, 4,120 valid) against an
    independent oracle; histories with an invalid proper prefix are invalid by the same rules.
    The one PostgreSQL test that must observe a lease expiring during a real lock wait follows
    the accepted M3 precedent (a two-second lease and bounded polling).

No accepted contract was reinterpreted and no validation was weakened.

## Prompt 201 corrections

**Reviewer evidence and its limits.** The external reviewer probed the submitted domain module's
constructors in isolation (Python 3.12.14, Pydantic 2.14.0) with values built through
`model_construct` and bypass-built dataclass instances. This tested the declared constructor
boundary only; it was not a project-suite, installed-wheel, database or PostgreSQL run, and it
does not establish a database-reload defect or require protection against hostile in-process
code.

**Finding A: question validation.** `revalidated_question(q)` and `PlannedQuestionSet` accepted a
question whose `requires_documentary_support` was the integer `1` and silently turned it into
`True`; a question with `search_queries` as a list was refused, but only after
`model_copy`/`model_dump` emitted a Pydantic warning containing the query text. The submitted
rebuild compared values with `==`, which treats `1 == True` and a `str` subclass as equal.
**Correction:** the shared question boundary now reads each field and requires an exact `str` ID
and text, an exact `tuple` of exact `str` queries and an exact `bool` flag **before** any
operation that can normalize or serialize; it then rebuilds through the existing `EvidenceQuestion`
validation (never `model_copy`) and requires every field to stay unchanged in value and type, so
padding the model would strip is refused. The question constraints and the fixed
`InvalidStageValueError` (`InvalidStageRequestError` at the write APIs) are unchanged; refusals
emit no warning, output or log; process control propagates as the same object. Every entry point
that takes a question uses it: `revalidated_question`, `plan_question_canonical`,
`PlannedQuestionSet`, `EvidenceRecord`, `TrustedQuestionStages` and `decode_evidence`; the domain
still imports nothing from `evidenceguard_agents`.

**Finding B: nested aggregates.** `TrustedQuestionStages` accepted an exact `QuestionEvidence`
whose `result` was a string, because it checked the class and a few identity fields only, and
`TrustedStages` retained exact `TrustedQuestionStages` instances without rebuilding them.
**Correction:** `TrustedQuestionStages` rebuilds its `QuestionEvidence` through the M5b constructor
from exactly typed fields (its question through the corrected boundary, its result through the M4d
constructor) and rebuilds any supplied `verification`/`analysis` stage before comparing it with the
history's; `TrustedStages` rebuilds every `TrustedQuestionStages`. `StageState` accepted its plan
by `==` only (a bypass-built `PlanInFlight` with `sequence=True` equalled the computed plan and was
retained); it now rebuilds the plan through its variant's constructor and stores the rebuilt
value. The other M5e aggregates already rebuilt their nested values (`PlannedQuestionSet` through
the question boundary, `EvidenceRecord`'s result, `CallRecord`'s usage and rejection,
`StageRecord`'s content, `PlanReuse`'s stage and `StageHistory`'s calls and stage). Construction
remains a consistency check only; it proves no database origin, authorization or provenance.

**Not changed.** The M5b rebuilds of its own Pydantic values (`Verification`, `Citation`,
`Finding`) inside `VerifiedQuestion`/`AnalyzedQuestion` still use M5b's accepted `model_copy`
pattern; M5e relies on that accepted contract and does not change M5a–M5d contracts. This is noted
for review, not demonstrated as a defect here.

**Regression classification.** The 65 finding-specific tests were run against an isolated
overlay containing the exact submitted module (import location confirmed) and against the
corrected module. Submitted: 24 passed, 41 failed; corrected: 65 passed.

| Class | Submitted failures |
| --- | --- |
| Genuine reproductions of the reviewer's probes (integer flags accepted and coerced at five entry points; list queries refused with a warning at five; at the persistence boundary integer flags reached SQL and list queries warned; evidence with a string result accepted directly and inside `TrustedStages`) | 20 |
| Further demonstrated instances of the same omissions (`str`-subclass ID, text and query accepted at five entry points; evidence inconsistent with its result; `TrustedStages` items with a string evidence or a malformed question; `StageState` retaining an equal-but-`bool` plan) | 19 |
| Coverage of the corrected path, not reproductions (two process-control identity tests patch constructors the submitted code never called) | 2 |

The 24 submitted passes are valid controls and cases the submitted code already refused (padded
text, evidence with a malformed question or a non-evidence value, invalid histories).

## External review (Prompt 202)

**Decision.** The external reviewer accepted the corrected M5e implementation and the recorded
implementation choices for a local implementation commit only. The specification was accepted
in Prompt 199; Claude Code implemented it in Prompt 200 and corrected findings A and B in
Prompt 201. OpenAI Codex performed this recovery, acceptance documentation and commit preparation
in Prompt 202. Earlier reviewer and assistance attribution remains unchanged. Publication,
PostgreSQL execution and exact-commit current-version CI remain pending.

**Reviewer evidence (supplied decision, not checks run by Codex).** The reviewer independently
verified the Prompt 201 export's size (73,242 bytes), line count (682), SHA-256
`6fea269e5527b5d1d2e82d04413223e8c2ce5bfa985e607cfb813ddc1bb9a4b4`, paths and
statistics; reconstructed the corrected domain module and confirmed Git blob
`78f228c678f5f05e0e3ccfb5bd7431e2b1bf4461`; inspected the corrections and regression
tests; and ran 59 isolated constructor check cases with Python 3.12.14 and Pydantic 2.14.0,
all passing. These covered malformed questions, warning-free refusals, valid controls, invalid
nested evidence and question entries, the equal-but-bool `StageState` plan, nested rebuilding,
replacement and process-control identity.

**Limits and attribution.** Those were isolated checks in a reconstructed review environment,
not a project-suite, installed-wheel, database or PostgreSQL run; they did not byte-verify the
entire staged repository. The bypass-built constructor probes neither demonstrate a
database-reload bypass nor establish a defence against hostile in-process code. The note about
M5b's accepted `model_copy` pattern is not a demonstrated new defect. The findings, corrections
and regression classification above remain the historical record.

Claude Code's separately attributed Prompt 201 Windows results below (658 focused passes;
3,966 full-suite passes and 387 skips; collection of 385 integration and 3,968 non-integration
tests; static checks, offline build, installed-wheel step and direct wheel probes) and the
Prompt 200 results are historical local evidence, not exact-commit CI. Codex did not repeat
application tests, builds or wheel checks: every implementation and test blob remains identical
to accepted tree `c6ca841a6c4e2c49e567d0557a17e42c6770ac60`. All PostgreSQL-backed
behaviour remains unverified; collection and skips verify none of it. All later-slice and
runtime limitations below remain in force; M5f–M5h and overall M5 acceptance remain pending.

## Verification (Prompt 201, local Windows, Claude Code)

Historical local evidence recorded by Claude Code in Prompt 201; not rerun in Prompt 202.

| Check | Result |
| --- | --- |
| `ruff format --check .` | 220 files already formatted (the formatter also counts Markdown; ADR-0023 did not exist at the Prompt 200 count) |
| `ruff check .` | all checks passed |
| `mypy` (strict) | no issues in 176 source files |
| focused M5e, packaging and M4d retrieval unit tests | 658 passed |
| full suite | 3,966 passed, 387 skipped (385 PostgreSQL tests without a database, 2 platform skips) |
| collection | 385 integration and 3,968 non-integration tests |
| offline build, comparison and installed wheel | see [Build and installed wheel (Prompt 201)](#build-and-installed-wheel-prompt-201) |

PostgreSQL tests remain written but **not run** (no `EG_TEST_DATABASE_URL`); collecting or
skipping them verifies no database behaviour. No CI was run.

### Build and installed wheel (Prompt 201)

- `uv build --offline` ran on a `git archive` of the staged tree. Against the preserved `313b523d`
  baseline the member sets are as in Prompt 200 (wheel 109 → 112, sdist 221 → 230, nothing
  removed). Against the submitted Prompt 200 build the only differences are the correction:
  wheel `evidenceguard_domain/review_stages.py`, `METADATA` (README) and `RECORD`; sdist the same
  module, the two corrected test modules, `README.md`, ADR-0023 and `PKG-INFO`. All 16
  `sample_data` files and the packaged template and prompts are byte-identical.
- The complete installed-wheel step from `ci.yml` (227 lines) ran in a fresh environment outside
  the checkout (hashed offline dependencies, wheel `--no-deps`) and exited 0, importing from
  `site-packages` and printing every expected line.
- Direct probes against that installed wheel: questions with an integer flag `1` or `0`, list
  queries or a `str`-subclass ID were refused by `revalidated_question` and `PlannedQuestionSet`
  with a fixed error and no warning; `TrustedStages` refused a `TrustedQuestionStages` whose
  evidence was a string, and the valid control constructed. These are offline constructor checks,
  not PostgreSQL execution.

## Verification (Prompt 200, local Windows, Claude Code)

Historical local evidence: run by Claude Code in Prompt 200 with the locked offline environment;
not rerun in Prompt 202.

| Check | Result |
| --- | --- |
| `ruff format --check .` | 219 files already formatted |
| `ruff check .` | all checks passed |
| `mypy` (strict) | no issues in 176 source files |
| new and affected tests | `test_review_stage_values` 107, `test_review_stage_planner` 46, `test_evidence_recheck` 37, `test_review_stage_persistence` 71, M4d retrieval unit tests 283, packaging/persistence/readiness 101, workflow tests 124: all passed |
| full suite | 3,901 passed, 387 skipped |
| collection | 385 integration and 3,903 non-integration tests |
| offline build and comparison | see [Build and installed wheel](#build-and-installed-wheel-prompt-200) |

**PostgreSQL tests were written but not run.** No disposable test database is configured here
(`EG_TEST_DATABASE_URL` is unset), so the 46 tests in `test_review_stages_postgres.py`, the two
new tests in `test_retrieval_postgres.py` and the updated migration tests in
`test_reviews_postgres.py` and `test_persistence_postgres.py` were collected and skipped. Their
correctness, including the migration upgrade/downgrade/`alembic check`, the constraint names, the
concurrency and lease-expiry tests and every database-backed binding, replay and reload case, is
**unverified** until the CI PostgreSQL job runs them. No CI was run for this change.

### Build and installed wheel (Prompt 200)

`uv build --offline` ran on a `git archive` of the staged tree and of the baseline `313b523d`.

- **Wheel:** 109 → 112 members. Added: `evidenceguard_domain/review_stages.py`,
  `evidenceguard_persistence/review_stages.py`,
  `evidenceguard_persistence/migrations/versions/v0007_review_stages.py`. Changed:
  `evidenceguard_persistence/models.py` and `retrieval.py` (this slice), `METADATA` (the README
  long description) and `RECORD` (the new files). Nothing removed.
- **Sdist:** 221 → 230 members. Added: ADR-0023, the three new modules and the five new test
  modules. Changed: `PKG-INFO`, `README.md`, ADR-0022, `models.py`, `retrieval.py` and the six
  updated test modules. Nothing removed.
- All 16 `sample_data` files are byte-identical to the baseline; the packaged template and both
  prompts are byte-identical (SHA-256 `26fcbe26…786a`, `629f8f97…007d`, `f8e48599…1b29`).
- **Installed wheel:** the complete installed-wheel step extracted from `ci.yml` (227 lines) ran
  in a fresh environment outside the checkout, with the locked non-development requirements
  exported with hashes and installed offline with `--require-hashes`, and the wheel installed with
  `--no-deps`. It exited 0, imported from `site-packages` and printed every expected line,
  including the new "stage migration SQL rendered and an abandoned repair planned as a retry from
  the installed wheel". This is an offline assertion; it is **not** PostgreSQL execution.

## Limits and later-slice obligations

- No output table, value or writer exists; M5f/M5g must review the output schema and the atomic
  output-plus-job-success writer before completion is enabled (E7). No review can become
  `completed`.
- The worker composition (M5g) must prove template origin, reassemble requests from rechecked
  inputs and require their digests before every dispatch or retry, build M5c's `RepairReason`
  from stored fields with public factories, assert the U5/U6 sizes, and obtain owners from a
  trusted path.
- A U4 stage's oversized evidence bytes and their original binding assertion cannot be re-proved
  at reload; the reload proves only the well-formed U4 shape and the planned question.
- An M5e error must escape the caller's fenced block; suppressing it can commit a partial effect
  (shown by a PostgreSQL test written to document the obligation).
- Statements may run after lease expiry and are rolled back when the final recheck fails; a
  transaction that passes the final recheck just before expiry may still commit shortly after
  (the accepted M3 limit).
- The byte caps are accepted engineering limits, not measured performance or memory guarantees.
- The M4d trusted-snapshot limitation closes for review paths only once M5g obtains its snapshot
  solely through the trusted reload.
