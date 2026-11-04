# ADR-0023: Stage and call-reservation persistence

- **Status:** **M5e is reviewed, verified in CI and on main at `14f510e` (Prompt 206)**
  ([main publication and exact-SHA evidence](#main-publication-and-exact-sha-ci-prompt-206)). Claude Code
  implemented it in Prompt 200 and corrected exact question validation and nested rebuilds in
  Prompt 201 ([corrections](#prompt-201-corrections)); the external reviewer accepted the local
  implementation and recorded choices in Prompt 202 ([review](#external-review-prompt-202)).
  The failed `5b94d18a` feature gate and its test-setup correction by OpenAI Codex in Prompt 204
  remain historical ([diagnosis](#feature-ci-failure-and-test-setup-correction-prompts-203204)).
  The correction was accepted in Prompt 205, passed feature CI at `15cbfbae`, and the reviewer
  accepted both evidence exports in Prompt 206. The new documentation commit's separate feature
  and main gates then passed at `14f510e`. Neither the prior failure nor the correction is a
  demonstrated production reload defect. Implements the
  [accepted M5e specification](../plan.md#m5e-stage-and-call-reservation-persistence-specification-accepted-at-review-prompt-199-implementation-pending)
  (proposed in Prompt 196, corrected in Prompts 197–198, accepted in Prompt 199 with E1–E20 and
  clarifications A and B), the fifth slice of the
  [accepted M5 sequence](../plan.md#m5-implementation-sequence-accepted-at-review-prompt-170).
  No application review path uses M5e and `run_review` stays unregistered; no M5e control operates
  in the application. E7 assigns output work to M5f/M5g, and overall M5 acceptance remains pending.
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
of the local implementation commit only. At that acceptance PostgreSQL execution and exact-commit
CI were pending; the later failed feature gate is recorded below.

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
in Prompt 202. Earlier reviewer and assistance attribution remains unchanged. At that acceptance,
publication, PostgreSQL execution and exact-commit current-version CI were pending; see the
[later feature run](#feature-ci-failure-and-test-setup-correction-prompts-203204) for the current failed gate.

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
application tests, builds or wheel checks in Prompt 202: every implementation and test blob then
remained identical to accepted tree `c6ca841a6c4e2c49e567d0557a17e42c6770ac60`. At that
acceptance PostgreSQL had not run; collection and skips verified none of its behaviour. The
subsequent published feature run executed PostgreSQL and failed one case, as recorded below.
All later-slice and runtime limitations below remain in force; M5f–M5h and overall M5 acceptance remain pending.

## Feature CI failure and test-setup correction (Prompts 203–204)

**Historical state before corrective feature CI.** M5e was published on
`feat/review-stage-persistence` at
`5b94d18a4053e0a7d6e32d8add631ecb5ccde70b` in Prompt 203. Mathew completed the push
manually after Codex's earlier attempt stalled in Git Credential Manager and was stopped.
Four jobs passed and PostgreSQL ran but failed one test, with 384 passing integration cases.
The test-only correction by OpenAI Codex in Prompt 204 was accepted at external review in
Prompt 205 for a corrective commit and feature publication. At commit time the feature gate was
not fully green; correction-specific PostgreSQL execution and exact-version CI were pending,
and main publication was blocked. No production code, constraint, migration, model,
resource, packaging or workflow change is part of the correction.

### Published feature evidence at 5b94d18a (Prompt 203)

Both runs were **push** events, **attempt 1**, on `feat/review-stage-persistence`, at the full
SHA above. They are evidence for that published version only, not the later corrective commit.

CI run [41739339372](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/41739339372)
completed with **failure**:

| Job | Conclusion | Observed log result |
| --- | --- | --- |
| [Ubuntu verify, 126276607907](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/41739339372/job/126276607907) | success | 3,968 passed, 385 skipped |
| [Windows verify, 126276607952](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/41739339372/job/126276607952) | success | 3,967 passed, 386 skipped |
| [PostgreSQL integration, 126276607831](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/41739339372/job/126276607831) | failure | 1 failed, 384 passed, 3,968 deselected |
| [Container, 126276607520](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/41739339372/job/126276607520) | success | smoke and cleanup reported success |

Secret-scan run [41739339351](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/41739339351)
completed with **success**:

| Job | Conclusion | Observed log result |
| --- | --- | --- |
| [Gitleaks, 126276607571](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/41739339351/job/126276607571) | success | 87 commits scanned, no leaks |

**Attribution.** The external reviewer independently retrieved both run records, all five job
conclusions and all five logs through GitHub (reported in Prompt 204). Separately, OpenAI Codex
observed the exact-SHA API metadata and retrieved/read all five logs during Prompt 203, then
stopped at the failed gate. Its saved records and logs are under `.local/p203/`. Neither
account is Claude Code's historical Prompt 200–201 local evidence; no remote read or CI rerun
was made in Prompt 204.

Both verify logs printed the production registry and all ten installed-wheel behaviour lines,
including "stage migration SQL rendered and an abandoned repair planned as a retry from the
installed wheel". Those checks are offline, separate from the PostgreSQL execution. The Recall
example is arithmetic, the Voyage response mocked and model calls scripted; the unchanged
container smoke does not exercise M5e. None establishes live-model quality, entailment,
authenticity or injection resistance.

### Test-setup diagnosis and correction (Prompt 204)

The sole failure was
`tests/test_review_stages_postgres.py::test_the_reload_refuses_tampered_rows[<lambda>8]`.
Its final tamper parameter executed `UPDATE jobs SET attempt=0` while retaining the running
job's lease fields. PostgreSQL correctly refused that setup under
`ck_jobs_lease_while_running`, before the expected reload assertion. Running jobs require a
lease and attempt at least one; non-running jobs require no lease owner or lease expiry.
The original failed CI execution supplies the old setup-failure evidence. It does not
demonstrate a production reload defect.

The correction removes only that final parameter and replaces it with the named standalone
`test_the_reload_refuses_an_unclaimed_canonical_job_with_persisted_history`. It builds the
committed fixture, confirms an initial reload succeeds and records the existing plan/stage
rows. Through the existing committing tamper helper, it selects only the fixture tenant's
canonical job by tenant and job ID and sets `status="queued"`, `attempt=0`, `locked_by=None`,
`lease_expires_at=None` and `finished_at=None`. It reads the row back and asserts that exact
state, confirms all persisted M5e rows remain identical, then requires
`StageRecordInconsistentError` from reload. Thus a setup failure cannot be mistaken for the
intended refusal. The other eight tamper cases and the valid control for a genuinely unclaimed
review with no stored history remain unchanged. No constraint is weakened, and no skip,
xfail or acceptance of `IntegrityError` replaces the reload expectation.

The intended scenario is a database-valid job that has never been claimed but nevertheless
has persisted plan/stage history. **At Prompt 204, the corrected case had not run against
PostgreSQL.** Local collection and skips prove no corrected database behaviour; the published run's 384
passes do not verify this changed case. Local Prompt 204 checks are recorded in its handoff
and prompt-history outcome; builds and installed-wheel checks are not repeated because the
production, resource, packaging and workflow blobs remain unchanged. Review accepted the
correction in Prompt 205; correction-specific PostgreSQL execution and exact-commit CI were
pending at commit time. The later corrective feature CI is recorded below. All scope limitations
and overall M5 acceptance remain unchanged.

### Correction acceptance (Prompt 205)

The external reviewer accepted the Prompt 204 test-only correction for a corrective commit
and feature publication to `feat/review-stage-persistence` in Prompt 205. The reviewer verified
the export's bytes, checksum, paths and statistics (56,483 bytes, 319 lines, five files,
173 insertions and 24 deletions; SHA-256
`efdfc2350fabb552c623daf38b2c8c4c73e79e19b688dd0ab5cc84dd63a35ba5`) and inspected the
replacement test against the published source. The reviewed test blob is
`cb13b6289f74e202e1d2f6586c9c14fef1599e7d` and is preserved unchanged.

The reviewer did **not** run the corrected case locally or against PostgreSQL. The original
failure occurred during the tampering `UPDATE`, before reload; this is a test-setup correction,
not a production reload fix. Correction-specific PostgreSQL execution and exact-commit CI
were pending at commit time. The failed `5b94d18a` feature gate above remains historical
evidence for that published version, separate from the corrective commit. At acceptance the
feature gate was not yet green and main publication was blocked; the later successful feature
gate is recorded below. Main publication was still unauthorized at that point; Prompt 206
subsequently grants the gated authorization recorded below.

OpenAI Codex wrote the Prompt 204 correction and documentation and performed the Prompt 205
recovery, acceptance documentation and commit preparation. The external reviewer's independent
export verification, source inspection and acceptance retain their own attribution, as do
Codex's Prompt 203 observations and Claude Code's earlier implementation, corrections and
historical local evidence. Prompt 204's local checks are historical and are not repeated in
Prompt 205 because the reviewed test and all production blobs remain unchanged.

### Local correction checks (Prompt 204, OpenAI Codex)

Historical local results, run by OpenAI Codex in Prompt 204 with `uv run --locked --offline`
in the existing Windows Python 3.12.15 environment; not repeated in Prompt 205:

| Check | Result |
| --- | --- |
| Ruff formatting and lint | 220 files already formatted; all lint checks passed |
| strict mypy | no issues in 176 source files |
| focused M5e values, planner, persistence, evidence-recheck and PostgreSQL module | 326 passed, 46 skipped |
| full suite | 3,966 passed, 387 skipped (385 PostgreSQL cases and two platform skips) |
| collection | 385 integration and 3,968 non-integration, 4,353 total, unchanged |

The eight retained generic tamper cases and the unclaimed empty-history control are unchanged.
One parameter became one standalone test, preserving the collected total. No local test
database was configured: the named corrected case was collected and skipped, **not run against
PostgreSQL at those local checks**.
Local skips establish nothing about the correction's database behaviour. No build,
installed-wheel check, provider call or CI rerun was performed for the correction.

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

Historical Prompt 201 status: PostgreSQL tests were written but **not run** locally (no
`EG_TEST_DATABASE_URL`); collection and skips verified no database behaviour. No CI was run in
that prompt. The later Prompt 203 PostgreSQL execution is recorded above.

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

**Historical Prompt 200 status: PostgreSQL tests were written but not run.** No disposable test
database was configured locally (`EG_TEST_DATABASE_URL` was unset), so the 46 tests in `test_review_stages_postgres.py`, the two
new tests in `test_retrieval_postgres.py` and the updated migration tests in
`test_reviews_postgres.py` and `test_persistence_postgres.py` were collected and skipped. Their
correctness, including the migration upgrade/downgrade/`alembic check`, the constraint names, the
concurrency and lease-expiry tests and every database-backed binding, replay and reload case, is
**unverified** at that time. No CI was run in Prompt 200; the later published PostgreSQL run
is recorded above, separately from the later corrective commit's evidence below.

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

## Corrective feature CI at 15cbfbae (Prompt 205)

**Historical Prompt 205 state: M5e was feature-published and feature-CI verified at
`15cbfbae88c52ecefb9f287f985bec734e8c535f`, but not merged.** The corrective commit's
parent is `5b94d18a4053e0a7d6e32d8add631ecb5ccde70b` and its tree is
`90e29b527a33b43a313cb57d868e446d6dc44a64`. The reviewed test remains exactly blob
`cb13b6289f74e202e1d2f6586c9c14fef1599e7d`; production, migrations, models, resources,
packaging and workflows are unchanged. Mathew completed the corrective feature push manually
after Codex's one attempt stalled in Git Credential Manager and was stopped without retry.
Codex then verified feature/HEAD/upstream equality and unchanged main, and resumed monitoring
without another push. Main publication and merge were not authorized in Prompt 205; the
subsequent gated authorization is recorded below.

Both runs below were **push** events, **attempt 1**, on `feat/review-stage-persistence`, at the
full corrective SHA above. All five required jobs explicitly concluded **success**; no parent
success was substituted for an unresolved job. The earlier failed `5b94d18a` run remains
historical evidence above and supplies no counts or conclusions for this correction.

CI run [41751683294](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/41751683294)
completed with **success**:

| Job | Conclusion | Output actually read in this job's log |
| --- | --- | --- |
| [Ubuntu verify, 126318003800](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/41751683294/job/126318003800) | success | 3,968 passed, 385 skipped; formatting, lint, strict mypy, build and installed-wheel steps succeeded |
| [Windows verify, 126318003627](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/41751683294/job/126318003627) | success | 3,967 passed, 386 skipped; formatting, lint, strict mypy, build and installed-wheel steps succeeded |
| [PostgreSQL integration, 126318004051](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/41751683294/job/126318004051) | success | 385 passed, 3,968 deselected in 199.95 seconds; no failed or skipped integration cases reported |
| [Container, 126318004071](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/41751683294/job/126318004071) | success | configuration, context and image checks succeeded; smoke and cleanup reported success |

Secret-scan run [41751683205](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/41751683205)
completed with **success**:

| Job | Conclusion | Output actually read in this job's log |
| --- | --- | --- |
| [Gitleaks, 126318003741](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/41751683205/job/126318003741) | success | Gitleaks 8.30.1; 88 commits scanned; no leaks |

**Corrected-case evidence and limit.** The PostgreSQL log shows 46 passing positions for
`tests/test_review_stages_postgres.py` (35 dots followed by 11 dots) and the successful
385-case integration summary. It does **not** print
`test_the_reload_refuses_an_unclaimed_canonical_job_with_persisted_history` or a named PASS
line. Thus the corrected module participated in the successful integration run, but the named
replacement's execution and result are **not individually confirmed by the available log**.
Prompt 204's collection identified that case in the reviewed source; it is historical local
collection evidence, not a separate named CI result. No individual result is invented from a
green conclusion, and no extra test dispatch or rerun was made to obtain one.

**Observed steps and boundaries.** Both verify logs printed the production registry
(`ingest_revision`, `index_revision`) and all ten installed-wheel behaviour lines, including
"stage migration SQL rendered and an abandoned repair planned as a retry from the installed
wheel". These wheel assertions render migration SQL offline and are separate from database
execution. The Recall example is arithmetic, Voyage is mocked and model calls scripted.
The unchanged container smoke reported ingestion/indexing success with two chunks and two
embeddings and `smoke: ok`; it does not exercise M5e. No application review path or
`run_review` registration was added. None of this establishes entailment, authenticity,
injection resistance or live-model quality.

**Attribution and access limits.** OpenAI Codex observed final run records through GitHub's
public API, final job/step conclusions through the connected GitHub tool, and retrieved/read
all five job logs through that tool. All five logs were available and saved under
`.local/p205/logs/`; their sizes and SHA-256 values are recorded in `.local/p205/ci-final.json`.
One metadata read had a transient transport failure and the final public job refresh was
rate-limited (HTTP 403); the connected tool supplied explicit final job conclusions without
an authentication or permission change. Final run and job conclusions agree. These are
Codex's observations for the corrective SHA, distinct from the external reviewer's earlier
independent review, Prompt 204's local checks, Claude Code's historical work and the failed
parent's evidence. Monitoring finished within 25 minutes of publication; no monitor or push
was left running.

The post-CI evidence updates were staged and uncommitted for review in Prompt 205 and were
not pushed in that prompt. Prompt 206 accepts them for a documentation commit and gated
publication. The `15cbfbae` exact-SHA CI does not verify these later documentation blobs. E7, discarded U4 evidence,
worker composition obligations, the accepted M3 lease window and the open M4d trusted-snapshot
limitation remain. M5f–M5h and overall M5 acceptance remain pending. M5e was not merged at
that Prompt 205 checkpoint; the subsequent gated main publication is recorded below.

### Reviewer acceptance and gated main authorization (Prompt 206)

The external reviewer accepts both Prompt 205 exports and independently confirms the successful
feature gate at `15cbfbae88c52ecefb9f287f985bec734e8c535f`. It verified both exports' bytes,
checksums, paths and statistics; checked the corrective commit's parent, tree and six-file scope;
confirmed test blob `cb13b6289f74e202e1d2f6586c9c14fef1599e7d`; and retrieved both run
records, all five final job conclusions and all five logs. The independently confirmed results
are those recorded above under CI run `41751683294` and secret-scan run `41751683205`:
Ubuntu 3,968 passed/385 skipped, Windows 3,967 passed/386 skipped, PostgreSQL 385 passed/3,968
deselected in 199.95 seconds, successful container smoke/cleanup and Gitleaks 88 commits/no leaks.
Both verify logs printed the registry and all ten installed-wheel behaviour lines. PostgreSQL
shows 46 passing review-stage module positions without naming the replacement individually.
That distinction remains; the evidence is sufficient to accept the feature gate and no extra
test dispatch or CI rerun is required. This is the reviewer's independent evidence and decision,
separate from Codex's observations above and earlier Claude Code assistance. The failed parent
remains historical evidence.

Prompt 206 authorizes committing this reviewed documentation and **gated main publication**:
Mathew manually publishes the new documentation commit to the feature branch; only after all
five required jobs explicitly pass for that exact commit may Codex freshly verify refs, scope
and clean state, fast-forward local main with `--ff-only`, and prepare Mathew's manual main push.
Main's own exact-SHA five-job gate must then pass before main-publication evidence is staged.
No automated push was authorized. At that acceptance note, neither main publication nor the
new feature/main CI results had happened; their subsequent completion is recorded below. No production change, history rewrite, branch deletion,
CI rerun or M5f work is authorized; overall M5 acceptance remains pending.

## Main publication and exact-SHA CI (Prompt 206)

**M5e is reviewed, verified in CI and on main at
`14f510e23e89bd890b2428405de922ef1fcb2232`.** The published documentation commit's
parent is `15cbfbae88c52ecefb9f287f985bec734e8c535f` and its tree is
`fce760c4fad950942ab5ec5152490fe6d3f00495`. It changes only the five reviewed
documentation/history files; the reviewed PostgreSQL test remains blob
`cb13b6289f74e202e1d2f6586c9c14fef1599e7d`. All production, other test, migration,
model, resource, packaging, dependency and workflow blobs remain unchanged from the reviewed
corrective source. M5f–M5h and overall M5 acceptance remain pending.

### Publication sequence and attribution

The external reviewer accepted both Prompt 205 exports and independently confirmed the
`15cbfbae` gate, as recorded above. OpenAI Codex recorded that acceptance and prepared
`14f510e`. Mathew manually pushed the feature branch. After the usage-limit interruption,
Codex recovered the actual clean state: feature at `14f510e`, local and remote main still at
`1efe3ed3f0aa9697ce4e71cee295293a89c94909`, and no remaining task/monitor. It retrieved
the existing final feature records and all five logs, without starting new runs or a redundant
monitor, and confirmed explicit success for every required job and step.

Fresh main-publication checks then confirmed the clean tree, main/origin/main/remote-main
baseline, exact feature ref, ancestry, the five reviewed commits and their 23-path union,
protected blob/mode identity, unchanged reviewed workflow/dependency/resource content, privacy
and publication scans. Range Gitleaks scanned five commits and full-history Gitleaks 89,
both without leaks. Codex switched to main and ran `git merge --ff-only` to the exact verified
commit. No merge commit was created. Mathew manually pushed main; Codex verified remote main,
local main, origin/main and the retained feature branch all at the exact SHA above. Codex
performed no automated push, history rewrite, branch deletion, CI rerun or M5f work.

The following are **Codex's observed records and actual log output**. At the Prompt 206
handoff, this was not a claim that the reviewer separately examined these later runs; that
qualification is historical following the independent Prompt 207 review recorded below. Both stages were **push** events, **attempt 1**,
at the full `14f510e` SHA. Feature and main are separate runs; neither stage's counts or
conclusions are inferred from the other. The failed `5b94d18a` run and successful `15cbfbae`
run remain historical and supply no counts for these newer runs. Earlier Claude Code
implementation/corrections and local results retain their existing attribution.

### Documentation-commit feature gate

Feature CI run [41757399847](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/41757399847),
branch `feat/review-stage-persistence`, completed with **success**:

| Job | Explicit conclusion | Output actually read in its log |
| --- | --- | --- |
| [Ubuntu verify, 126336644043](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/41757399847/job/126336644043) | success | 3,968 passed, 385 skipped |
| [Windows verify, 126336643968](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/41757399847/job/126336643968) | success | 3,967 passed, 386 skipped |
| [PostgreSQL, 126336644016](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/41757399847/job/126336644016) | success | 385 passed, 3,968 deselected in 259.95 seconds |
| [Container, 126336643752](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/41757399847/job/126336643752) | success | smoke and cleanup reported success |

Feature secret-scan run [41757400849](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/41757400849),
same feature branch and SHA, completed with **success**:

| Job | Explicit conclusion | Output actually read in its log |
| --- | --- | --- |
| [Gitleaks, 126336646243](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/41757400849/job/126336646243) | success | 89 commits scanned, no leaks |

### Separate main gate

Main CI run [41788993019](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/41788993019),
branch `main`, completed with **success**:

| Job | Explicit conclusion | Output actually read in its log |
| --- | --- | --- |
| [Ubuntu verify, 126437699334](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/41788993019/job/126437699334) | success | 3,968 passed, 385 skipped |
| [Windows verify, 126437699275](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/41788993019/job/126437699275) | success | 3,967 passed, 386 skipped |
| [PostgreSQL, 126437699044](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/41788993019/job/126437699044) | success | 385 passed, 3,968 deselected in 248.53 seconds |
| [Container, 126437699439](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/41788993019/job/126437699439) | success | smoke and cleanup reported success |

Main secret-scan run [41788993093](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/41788993093),
same main branch and SHA, completed with **success**:

| Job | Explicit conclusion | Output actually read in its log |
| --- | --- | --- |
| [Gitleaks, 126437699395](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/41788993093/job/126437699395) | success | 89 commits scanned, no leaks |

### Evidence precision and limits

Every required job and step explicitly succeeded. No successful parent run substituted for
an unresolved job, and final run/job metadata agree. Public GitHub API run records and
connected GitHub job/step records were inspected. All ten job logs across these two gates
were retrieved/read and saved under `.local/p206/feature-logs/` and `.local/p206/main-logs/`,
with hashes and source metadata in `feature-ci-final.json` and `main-ci-final.json`. No log
was unavailable and no authentication or permission change was used to obtain output.
Separate main monitoring finished within the 25-minute bound, with no monitor left running.

Both PostgreSQL logs show 46 passing review-stage module positions, but neither prints
`test_the_reload_refuses_an_unclaimed_canonical_job_with_persisted_history` or a named PASS
line. The corrected module participated in each successful 385-case integration run; an
individual named result for the replacement remains **not directly confirmed by the logs**.
No extra test dispatch or rerun was made to obtain one. The earlier reviewer accepted this
distinction; it is preserved rather than replaced by an invented individual result.

Each of the four verify logs across these gates printed the production registry
(`ingest_revision`, `index_revision`) and all ten installed-wheel behaviour lines, including
the M5e stage-migration and abandoned-repair line. Formatting, lint, strict mypy, distribution
build and installed-wheel steps succeeded. The wheel migration assertions are **offline**,
separate from PostgreSQL execution. The Recall example is arithmetic, Voyage is mocked and
model calls are scripted. Both unchanged container smokes exercise ingestion/indexing, not
M5e. None establishes live-model quality, entailment, authenticity or injection resistance.

These main-publication evidence updates are staged, uncommitted and unpushed for review; they
are not part of the published SHA and are not covered by its CI. No local application test,
build or wheel check was repeated for them. No application review path or `run_review`
registration was added. E7 keeps output work in M5f/M5g; U4 discarded evidence cannot be
re-proved at reload; worker obligations, the accepted M3 lease window and the open M4d
trusted-snapshot limitation remain. Overall M5 acceptance and M5f–M5h remain pending.

## External-review evidence acceptance (Prompt 207)

The external reviewer accepts both Prompt 206 exports and confirms M5e's publication
evidence. **Reviewer attribution:** the reviewer independently verified the exports' sizes,
line counts, full SHA-256 values, paths, statistics and wording; independently retrieved the
documentation commit's feature job conclusions and all five logs; and previously independently
retrieved the separate main run records, all five main job conclusions and all five main
logs. The reviewer confirmed the exact main SHA
`14f510e23e89bd890b2428405de922ef1fcb2232`, branch, push event, attempt 1, successful
conclusions and remote main at that observation. These are supplied independent-review
observations, separate from Codex's Prompt 206 observations above; Codex made no remote
observation in Prompt 207.

The accepted feature evidence is [CI 41757399847](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/41757399847)
and [secret scan 41757400849](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/41757400849):
Ubuntu 3968 passed/385 skipped, Windows 3967 passed/386 skipped, PostgreSQL 385 passed/3968
deselected in 259.95 seconds, container smoke/cleanup success, and Gitleaks 89 commits/no leaks.
The separate accepted main evidence is [CI 41788993019](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/41788993019)
and [secret scan 41788993093](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/41788993093):
Ubuntu 3968 passed/385 skipped, Windows 3967 passed/386 skipped, PostgreSQL 385 passed/3968
deselected in 248.53 seconds, container smoke/cleanup success, and Gitleaks 89 commits/no leaks.
The individual job links and Codex's log evidence remain under their own runs above.
The 46 passing review-stage module positions do not name the replacement case individually;
the reviewer accepts this qualification without another dispatch or CI rerun. The failed
parent, local checks and earlier acceptance records remain historical.

**M5e is reviewed, verified in CI and on main within its recorded scope.** This does not
accept overall M5 or close any runtime limitation below. OpenAI Codex records that acceptance
and proposes the [M5f report content and renderer specification](../plan.md#m5f-report-content-and-renderer-specification)
in Prompt 207. M5f is proposed, unaccepted, unimplemented and untested; no M5f control operates.
M5g–M5h and overall M5 acceptance remain pending. No new ADR, implementation or migration is
created by this documentation-only proposal.

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
