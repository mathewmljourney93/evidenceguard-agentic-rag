# ADR-0017: Synthetic corpus, anchor-to-chunk ground truth and retrieval evaluation

- **Status:** **Accepted at external review in Prompt 147**, corrected by Claude Code in
  Prompt 149, with that test-only correction accepted in Prompt 150; **reviewed, verified in CI
  and on `main` at `0ae4c6ca`** (`0ae4c6ca339232e40cc007d7b78334af08a8b25b`; see
  [Main CI evidence at `0ae4c6ca`](#main-ci-evidence-at-0ae4c6ca)). Feature-branch CI passed
  for that exact commit before the fast-forward, and main CI then passed. Claude Code
  implemented M4e in Prompt 144, corrected it in Prompts 145–146 and corrected the Linux test
  in Prompt 149; OpenAI Codex handled the subsequent documentation, commits and publication in
  Prompts 150–153. Implements the
  [accepted M4e specification](../plan.md#m4e-corpus-and-retrieval-evaluation-specification-accepted-at-review-prompt-143-implementation-pending)
  (proposed in Prompt 140, corrected in Prompts 141–142, accepted in Prompt 143).
  The [feature-branch evidence at `d1dcdfce`](#feature-branch-ci-evidence-at-d1dcdfce) and
  the failed Ubuntu run and passing PostgreSQL results at `c14821b7`
  ([historical evidence](#exact-commit-ci-at-c14821b7-and-test-correction-prompts-148149))
  remain historical. Recall is report-only with no threshold; no numerical database-derived
  corpus Recall value is supplied. M4f and overall M4 acceptance remain pending; local Compose
  is unverified.
- **Date:** 2026-10-17
- **Builds on:** [ADR-0016](0016-snapshot-retrieval.md) (M4d snapshot capture and retrieval),
  [ADR-0015](0015-revision-indexing.md) (M4c indexing), [ADR-0010](0010-document-ingestion.md)
  (the `text-md-v1` chunker), [ADR-0011](0011-document-api.md) (`create_upload`, `read_snapshot`).

## Decision

M4e adds a fictional evaluation corpus with hand-authored ground truth, pure code that validates
it, maps anchors to stored chunks and computes exact Recall@5 and Recall@8, and a test-only
worker module that loads the corpus through the production lifecycle, verifies a loaded database
read-only and runs the production M4d retrieval for two epochs. The results are **reported, never
gated on a Recall threshold**; the evaluation fails only on contract or isolation failures. Every
report carries the stamp "NOT a quality measurement of semantic retrieval": the offline hashing
profile is a lexical baseline, not a semantic one.

There is no migration, schema, dependency, lockfile, Dockerfile, Compose, container-smoke,
registry or handler change, no endpoint and **no installed command** (`eg-eval` does not exist).
The PostgreSQL tests are the only callers of the orchestrator, always through the existing guarded
disposable-database fixtures, which are unchanged.

## Layout

- `sample_data/`: `corpus.toml` (`eg-corpus-v1`), `documents/<tenant>/<vendor>/<key>@r<n>.md`,
  `variants/injected/...` (one replaced document) and `ground_truth/<tenant>.toml`
  (`eg-ground-truth-v1`). Two demo tenants (Halverson Freight, Marisol Clinics), three fictional
  vendors, 12 revisions, 17 anchors and 10 questions. It ships in the sdist, not the wheel.
- `evidenceguard_retrieval.evaluation` (pure; standard library, domain and retrieval only, no
  `os`, file, database or network access): `corpus` (schemas, bounds, references, quote rules,
  variant check, file-set check), `anchors` (exact location, chunk mapping, `parts`, manifest
  verification) and `recall` (exact `Fraction` Recall, digest, contract and isolation checks,
  canonical report).
- `evidenceguard_worker.evaluation` (test-only): the file reader, `run_fresh_two_epoch`,
  `verify_loaded` and `evaluate`.

## Corpus and ground truth

References are always qualified, `tenant/vendor/document@rN#anchor`; bare anchor names are never
accepted, so the same local name in two tenants or revisions is unambiguous. Each question has one
or more cases, each naming the epochs (`initial`, `final`) it applies to; gold must name the
revision eligible in that epoch (r1 for `initial`, the document's latest for `final`), belong to
the question's own tenant and vendor, and be disjoint from `forbidden`. Forbidden references may
cross tenants; foreign-tenant forbidden anchors provide the canaries. Quotes follow N11 exactly
(type, 1–4,000 code points, strict UTF-8, no CR or controls except TAB and LF, no leading or
trailing whitespace, multiline allowed, no normalization; non-overlapping left-to-right
`occurrence`). The injected variant must equal its clean document with exactly one paragraph
inserted. Unknown keys and out-of-bound values are rejected before any database work.

The reader refuses symlinks at every path component, non-regular files, unexpected files under
`documents/`, `variants/` or `ground_truth/`, and files over their byte bound (checked before and
after reading). The corpus digest `eg-corpus-digest-v1` hashes the variant name and the effective
file set (paths sorted by UTF-8 bytes), each field framed by an 8-byte big-endian length.

## Orchestration (three contracts)

1. `run_fresh_two_epoch` first re-derives and completely validates the suite (see
   [Prompt 145 corrections](#prompt-145-corrections)), then refuses any existing corpus-tenant vendor, document, revision, profile,
   index or corpus job (`corpus_state_not_fresh`), accepting an empty or a seeded-only database;
   then seeds, creates vendors, uploads, ingests and indexes every r1, captures and **retains** the
   `initial` snapshots while no later revision exists, applies later revisions in manifest order
   and captures `final`. Job outcomes come from the rows, never from worker exit codes; each job
   allows at most two single-claim worker runs. `stop_after` is the test hook for partial states.
2. `verify_loaded` runs entirely in one `read_snapshot` transaction (REPEATABLE READ, READ ONLY),
   compares every corpus-tenant record with the corpus, enumerates every embedding profile of
   each corpus tenant and returns only the logical-to-actual ID map. It writes, captures and
   repairs nothing, and never produces an `initial` epoch.
3. `evaluate` reads stored chunks of every loaded revision, verifies each manifest against the
   rebuilt and offline manifests, resolves every anchor against the stored spans, and runs
   `search_snapshot` (k = 8; Recall@5 uses the first five) for every retained snapshot.

## Reports, errors and determinism

- **Question outcomes.** `ok` (Recall@5 and Recall@8 as exact fractions), `ok_empty_gold` (valid,
  Recall `null`, excluded from the macro) and `invalid` (any contract or isolation failure; Recall
  `null`). Any invalid question fails its group, whose macro values are then both `null`, and
  fails the report; `require_passing` raises `evaluation_failed` whatever the Recall elsewhere.
  Recall is never gated on a threshold.
- **Observed output is kept.** The report lists each question's ranked chunk IDs as returned,
  duplicates and forbidden results included, with the owning logical reference or an explicit
  `null` for a chunk outside the loaded corpus. Failure entries name the code, tenant, vendor,
  epoch, question and, where applicable, the chunk ID and position.
- **Privacy.** Errors and reports carry fixed codes, logical references, IDs, counts and
  fractions only: never document text, quotes, evidence text or raw exception content.
  Operational failures (loading, capture, retrieval) raise a fixed `EvaluationError` and produce
  no report.
- **Encoding.** Canonical JSON (sorted keys, compact separators, ASCII), groups sorted by tenant,
  vendor and epoch, questions by ID; fractions as numerator, denominator and a round-half-even
  four-decimal display.
- **Determinism limits.** Production UUIDs, timestamps and tie-breaking are unchanged. The same
  retained snapshots give byte-identical reports; two fresh databases are compared only
  structurally (logical references, group shapes, gold counts), never by IDs, digests, tied ranks
  or Recall.

## Material implementation choices

- **Failure conversion.** `_guard` keeps an own `EvaluationError`, maps an M4d `RetrievalError` to
  `retrieval_failed` with its fixed code as `detail`, and maps any other `Exception` to the step's
  fixed code, raising outside the handler so no message, cause or context is retained.
  `BaseException` process control propagates unconverted.
- **Vendors.** `ensure_vendor` lists, creates, and on `DuplicateVendorSlugError` re-reads; a stored
  name that differs from the manifest is `corpus_conflict`.
- **Capture check.** Each capture must bind exactly the expected epoch revisions
  (`corpus_capture_mismatch`); evaluation additionally requires gold within the snapshot's chunks
  (`gold_not_in_snapshot`) and every snapshot to share one profile and configuration.
- **Canaries** are the quotes of the case's forbidden anchors in other tenants; a returned chunk
  whose evidence text contains one is `foreign_canary`. The two Marisol canary strings
  (`LV-TB-CANARY-36H`, `LV-TB-CANARY-AES`) are authored isolation content of the fictional
  documents; no marker is inserted into any document to support anchor mapping.
- **Resetting within a test.** Two PostgreSQL tests need a second clean database within one test
  (two fresh loads; an extra-profile fresh-run refusal). They reset the already validated
  disposable database exactly as the shared `empty_database` and `migrated` fixtures do; the
  fixtures and guards themselves are unchanged.
- **Verifier reads.** Revision rows are read in one statement including `content_text`, which is
  compared exactly with the corpus text. Job `payload` is not read: the accepted checks compare
  each canonical job's kind, idempotency key and status only. This omission from the accepted
  read list (item 6) is disclosed and was accepted in Prompt 147 as this slice's verification
  scope; no payload validation is claimed and the read list is not redefined.

## Tests

- Database-independent: `tests/test_evaluation_corpus.py` (committed corpus, schemas, bounds,
  references, epoch cases, quote and occurrence rules, `parts`, documents, variant, file sets and
  reader safety including symlinks), `tests/test_evaluation_anchors.py` (exact location without
  normalization, body and header routes, `parts` outcomes, a synthetic long table with repeated
  headers, manifest verification) and `tests/test_evaluation_recall.py` (the 2/3 example, Recall
  and macro cases, display rounding, digest framing, contract and isolation classification, group
  counts and failed groups, `require_passing`, canonical and private reports).
- PostgreSQL (`tests/test_evaluation_postgres.py`, 16 integration cases): the fresh run and both
  epochs, evaluation, repeatability and the k = 5 prefix; verifier success with no writes (row
  comparison and recorded statements); refusals for empty, seeded-only, every stopped phase,
  conflicting metadata and content, an extra document and an extra profile; fresh-run refusal of
  every partial state; production-seam reuse; the injected variant; two structurally equal loads.
- Prompt 145 regressions (database-independent): `tests/test_evaluation_worker.py` (complete
  validation before any session-factory call, the `_read` process-control, refusal, ordinary
  and cleanup matrix and the three read entry points, vendor creation with transaction
  doubles, and instrumented reader bounds) and `validate_suite` cases in
  `tests/test_evaluation_anchors.py` (missing, ambiguous and out-of-range quotes, a quote
  crossing a boundary without `parts`, invalid `parts`, forbidden-only and unused anchors,
  the selected variant's text, both committed variants and a tampered suite).
- Prompt 146 regressions: 19 cases in `tests/test_evaluation_worker.py` for process control
  and ordinary failures from the setup clock result's `scalar_one()`, through `_read` and the
  three read entry points, plus a successful result path through the proxy.
- `tests/test_packaging.py`: the evaluation modules' import boundaries, the worker module's
  boundaries and the absence of an `eg-eval` command.
- CI (E9): one installed-wheel step importing the three pure modules from `site-packages` and
  computing the 2/3 example.

## Prompt 145 corrections

The external reviewer's isolated probes (extracted code with infrastructure doubles; no project
suite, build, Docker, PostgreSQL or provider call) and source inspection found four gaps,
corrected here:

- **A. Complete validation before any database work.** `build_suite` checks schemas and
  references only. `anchors.validate_suite` adds, for every defined anchor (gold, forbidden-only,
  claim-only or unused alike), exact location in the selected variant's text and mapping to the
  chunks of the pinned `text-md-v1` chunker run offline (`anchors.offline_spans`, under a fixed
  placeholder identity, since spans do not depend on IDs), raising the anchor's fixed code. It
  lives in `anchors`, which already imports `corpus`, so there is no import cycle. `Suite` now
  records `source_files` (the effective set plus, for the injected variant, each replaced clean
  document); `anchors.revalidate` re-derives a suite from those bytes and requires equality
  (`corpus_invalid` otherwise). `load_suite` returns only a completely validated suite, and
  `run_fresh_two_epoch`, `verify_loaded` and `evaluate` each re-derive the suite before any
  database access, so a caller-constructed or altered `Suite` value is never trusted.
  Stored-manifest verification at evaluation time is unchanged.
- **B. Vendor identity only after commit.** `ensure_vendor` keeps the created ID only once the
  `transaction` context has exited without raising; a failure in `create_vendor`, flush, commit
  or cleanup is a fresh `corpus_vendor_failed` raised outside the handler. A
  `DuplicateVendorSlugError` (rolled back by the context) is followed by a re-read in a new
  transaction: a missing vendor is `corpus_vendor_failed`, a different name `corpus_conflict`.
  Process control is never caught. The vendor store and transaction helper are unchanged.
- **C. Read failures preserved through cleanup.** Every evaluation read (freshness counts, job,
  revision and index status, `verify_loaded`, stored spans) goes through `_read`, an
  evaluation-owned boundary around the unchanged `read_snapshot` helper. A session proxy records
  the first non-`Exception` raised by any session call (`SET TRANSACTION`, `clock_timestamp()`,
  the body's statements, rollback, close). Afterwards, in order: a recorded process-control
  exception is re-raised as the same object even if rollback or close then failed; a body's
  fixed `EvaluationError` refusal is re-raised fresh (code, detail and counts) even if cleanup
  failed; any other failure, including a cleanup failure after a successful body, is a fresh
  `corpus_read_failed` and returns no result. M4d's `run_read` was not reused, because its
  outcomes are M4d retrieval errors and semantic codes. No exception chain is inspected and no raw
  text is retained.
- **D. Bounds before payload reads.** `load_suite` reads `corpus.toml` only after checking its
  size (64 KiB). Before reading any other payload it checks every file that `validation_paths`
  names (non-symlink components, regular file, containment under the root, per-file bound of
  256 KiB for each document or ground-truth file) and requires the effective set's reported
  total, including `corpus.toml`, to be at most 4 MiB. The injected variant's replaced clean
  documents are bounded per file and outside that total, so a load reads at most 4 MiB plus
  256 KiB per replacement. Each read requests at most the checked size plus one byte and must
  return exactly that size (`corpus_file_changed` otherwise), and the actual effective total is
  checked again. The digest's effective file set is unchanged. A concurrent file-system change
  between check and read is detected only as an observed size or type mismatch; it is not
  otherwise prevented.

**Regression comparison.** `tests/test_evaluation_worker.py` (80 cases) ran against temporary
copies of the saved Prompt 144 modules (under `.local/p145/old/`, first on `PYTHONPATH`, imports
confirmed) and against the corrected modules: 26 passed and 54 failed before; 80 passed after.
**37 of the 54 failures reproduce the findings:** A 4 (an absent quote, a forbidden-only invalid
anchor, a schema-valid unmappable suite reaching the session factory, a tampered suite); B 1 (a
commit failure returning the created ID); C 29 (18 process-control cases with rollback and/or
close failure, 1 process control from rollback replaced by a close failure, 6 entry-point cases,
3 refusals lost to cleanup failure and the verifier's refusal lost to a rollback failure); D 3
(an over-budget set read before rejection, for each variant, and a file larger than its reported
size accepted). **The other 17 are not counted:** 12 ordinary-failure and 3
successful-body-with-cleanup-failure cases failed only because the Prompt 144 `_read` let raw
exceptions reach its callers, whose `_guard` normalized them; 2 use seams that did not exist
before (`Suite.source_files`, `_read_exact`). The 26 that passed before (for example the
per-file size refusal before reading) are not counted as reproductions. The new
`validate_suite` tests in `tests/test_evaluation_anchors.py` use the new function and were not
run against Prompt 144. The comparison never modified the corrected modules; their hashes are
recorded under `.local/p145/`.

## Prompt 146 correction

The external reviewer's isolated probe of the corrected read boundary with the unchanged
`read_snapshot` helper (an infrastructure double, not a project test; no project suite, build,
Docker, PostgreSQL or provider call) confirmed 24 of 24 process-control, setup-stage and cleanup
combinations, and found one remaining gap: the helper's setup reads
`session.execute(select(func.clock_timestamp())).scalar_one()`, and the Prompt 145 session proxy
recorded exceptions only from session methods, so a `KeyboardInterrupt` or `SystemExit` raised by
the result's `scalar_one()` after `execute` returned was replaced by an ordinary rollback failure
and became `EvaluationError`.

Correction: the proxy's `execute` now returns a small result proxy (`_RecordingResult`) whose
method calls record a non-`Exception` exactly as session calls do; iteration is passed through
unwrapped, since consuming results is the body's and the body boundary records it. Precedence is
unchanged: recorded process control (the same object) first, then a fixed refusal, then a fresh
private `corpus_read_failed` with no result. `read_snapshot`, M4d code, SQLAlchemy and the
transaction order are unchanged.

**Regression comparison.** 19 new cases in `tests/test_evaluation_worker.py` (the result double's
`scalar_one` raises after `execute` returns): 8 process-control cases (two classes; no cleanup
failure, rollback, close, both), 4 ordinary-failure cases, 6 entry-point cases
(`verify_loaded`, `run_fresh_two_epoch`, `evaluate`; two classes; rollback failure) and 1
successful-result case. Against the saved Prompt 145 worker module (a temporary copy first on
`PYTHONPATH`, import confirmed) 12 failed and 7 passed; with the correction all 19 pass. **All 12
failures are behavioural reproductions** (6 boundary cases with a cleanup failure, 6 entry-point
cases). The 7 that passed before (the two cases without cleanup failure, the four ordinary
failures and the successful result) are not counted. The 80 Prompt 145 cases pass with both
modules and are unchanged; the result double gained an optional `scalar_one` failure (default
none) to express the new cases. The comparison did not modify the corrected module; its hash is
recorded under `.local/p146/`.

## External review (Prompt 147)

The external reviewer **accepted the complete M4e implementation** (Prompt 144, with the Prompt
145–146 corrections) **for a local implementation commit, pending current-version CI**. Scope of
the review:

- The reviewer inspected the implementation diff and both correction diffs and independently
  matched all three sizes and checksums: `.local/p144/m4e-implementation.diff` (242,353 bytes,
  SHA-256 `6a0ce6a3b595b9f986d808d842e8aa5eac59dbe243b9a1ca5d50c57b7188d811`),
  `.local/p145/m4e-corrections.diff` (117,524 bytes, SHA-256
  `f379f194b0d4a5b7a4c6f56ea3a5797cf4181d8d4fb9b7970e6eff3277a1b5fa`) and
  `.local/p146/m4e-read-result-correction.diff` (66,626 bytes, SHA-256
  `a1ab2dee69b572319d31e704cbbd08bb66562ca399c74ae788fe6f7619e6700f`).
- The Prompt 145 review used isolated extracted-code probes with infrastructure doubles to
  reproduce the missing-anchor validation, the vendor commit failure and the read-cleanup
  process-control failures.
- The Prompt 146 review confirmed 24 of 24 existing control combinations and reproduced the
  additional clock-result `scalar_one()` gap for both exception classes.
- The final review inspected the result wrapper and the new tests; final isolated probes
  confirmed the 24 existing combinations plus both previously failing `scalar_one()` cases now
  preserving the same exception object.
- These probes are not the project suite, Claude Code's regression comparisons, the
  installed-wheel checks or PostgreSQL evidence. The reviewer ran no project suite, build,
  PostgreSQL, Docker or provider call. Acceptance also rests on the attributed local Windows
  results reported by Claude Code (below), not on independent reruns.
- The disclosed verifier scope is accepted for this slice: it checks each canonical job's kind,
  idempotency key and `succeeded` status but does not read job `payload`. No payload validation
  is claimed.

**Outstanding at acceptance (historical, before the Prompt 148 CI run):** no PostgreSQL test (none of the 16 M4e cases and none of the 306 integration tests against this version) had run, Linux and current-version CI were pending, the symlink refusal test had not run, and no database-derived Recall or isolation result existed. The implementation was not yet published or merged.

## Main CI evidence at `0ae4c6ca`

In Prompt 153 OpenAI Codex committed the reviewed verification documentation as
**`0ae4c6ca339232e40cc007d7b78334af08a8b25b`** (parent `d1dcdfce`), published it on
`feat/retrieval-evaluation`, and only after the push-triggered feature CI and secret-scan runs
for that exact SHA had passed, fast-forwarded `main` to it and pushed. The push-triggered main
runs then passed. Relative to `d1dcdfce`, `0ae4c6ca` changes verification documentation and
prompt history only (README, ADR-0017, plan, threat model and prompts.md), not implementation,
tests, corpus or workflow.

**Attribution:** Codex's run and log observations are attributed to its Prompt 153 handoff. For
Prompt 154 the external reviewer independently retrieved all four workflow records, all ten
job/step records, all ten job logs and the remote `main` ref; the counts and output below come
from that retrieval. The reviewer ran no local project tests, builds, wheel checks, PostgreSQL,
Docker or provider calls. Claude Code, in Prompt 154, retrieved no workflow logs and only
records this supplied evidence.

All four runs used SHA `0ae4c6ca339232e40cc007d7b78334af08a8b25b`, event **push**,
**attempt 1**, and concluded **success**. Every job and step succeeded on both pushes; both
platforms' tests, distribution builds and installed-wheel checks executed successfully on each
push.

**Feature push** (`feat/retrieval-evaluation`, before the fast-forward):
[ci run](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39061146590)
and
[secret-scan run](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39061146559).

| Job | Observed |
|---|---|
| [Ubuntu verify](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39061146590/job/117479200417) | `2246 passed, 306 skipped in 31.31s` |
| [Windows verify](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39061146590/job/117479200373) | `2245 passed, 307 skipped in 28.18s` |
| [PostgreSQL integration](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39061146590/job/117479200429) | `306 passed, 2246 deselected in 174.69s`; all 16 M4e cases passed |
| [Container](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39061146590/job/117479200247) | all six steps succeeded |
| [Gitleaks (full history)](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39061146559/job/117479200081) | 66 commits scanned, no leaks |

**Main push** (`main`, after the fast-forward):
[CI run 39061528249](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39061528249)
and
[secret-scan run 39061528188](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39061528188).

| Job | Observed |
|---|---|
| [Ubuntu verify](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39061528249/job/117480324329) | `2246 passed, 306 skipped in 24.55s` |
| [Windows verify](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39061528249/job/117480324350) | `2245 passed, 307 skipped in 40.96s` |
| [PostgreSQL integration](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39061528249/job/117480324114) | `306 passed, 2246 deselected in 187.68s`; all 16 M4e cases passed |
| [Container](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39061528249/job/117480324342) | all six steps succeeded |
| [Gitleaks (full history)](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39061528188/job/117480323798) | 66 commits scanned, no leaks |

All four installed-wheel logs (Ubuntu and Windows, both pushes) printed:

```text
offline embedding, canonical storage and indexing modules ran from the installed wheel
retrieval modules imported and fusion ran from the installed wheel
evaluation modules imported and Recall@5 = 2/3 computed from the installed wheel
offline migration SQL rendered from the installed wheel
```

Both container jobs: all six steps succeeded (configuration, context, build, image checks,
smoke and cleanup); 87 context files with 19 planted fixtures excluded; upload accepted with
202; successful ingestion with two verified chunks; a duplicate upload returning the existing
revision with 200; one offline backfill indexing job enqueued; a ready index with two
embeddings and a succeeded indexing job; the idle worker exiting 0 without OOM; and a
successful smoke.

**Limits.** These are observed log summaries and passing gates, not independent inspection of
raw database rows or generated credentials. The smoke covers ingestion, indexing and idle-worker
shutdown only; it does not exercise M4e evaluation, and local Compose remains unverified. The
wheel's 2/3 Recall fixture is pure arithmetic, not database-derived corpus Recall; no numerical
corpus Recall result was supplied. Recall remains report-only with no threshold. Offline hashing
supplies no semantic-quality claim and no live provider was verified. No injection-resistance,
production-readiness or general security guarantee follows; trusted in-process snapshots cannot
prove past eligibility, and M5 obligations remain. This evidence covers the exercised paths for
this commit only. M4f and overall M4 acceptance remain pending.

## Feature-branch CI evidence at `d1dcdfce`

Claude Code's Prompt 149 test correction was accepted in Prompt 150, committed locally as
`cc924ede1ecf8d1488db88dcfa98f5b5f1a7f11c`, and published with the Prompt 151 history-only
commit **`d1dcdfcebdd084f654060bcdf1a468c847291ee0`** on `feat/retrieval-evaluation`.
The [ci run](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39059247990)
and [secret-scan run](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39059247979)
both used event **push**, that branch and exact SHA, **attempt 1**, and concluded **success**.
All five jobs and their required steps completed successfully; no required step was skipped.

**Attribution:** OpenAI Codex's Prompt 151 handoff reports retrieval of both workflow records,
job/step records and logs through connected GitHub tools. For Prompt 152 the external reviewer
independently retrieved and confirmed both workflow records, all five job/step records and all
five logs through connected GitHub tooling. The reviewer ran no local project suite, build,
wheel, PostgreSQL, Docker or provider check. Claude Code's Prompt 148 API-only observations and
HTTP 403 record belong to the earlier `c14821b7` run, not this log evidence.

- [Ubuntu verify](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39059247990/job/117473630036):
  `2246 passed, 306 skipped in 30.80s`. Formatting, lint, type-check, Test, distribution build
  and installed-wheel steps all succeeded. The build and wheel checks actually ran.
- [Windows verify](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39059247990/job/117473630066):
  `2245 passed, 307 skipped in 33.63s`. All verification, distribution build and installed-wheel
  steps succeeded.
- [PostgreSQL integration](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39059247990/job/117473630038):
  `306 passed, 2246 deselected in 204.77s`. `tests/test_evaluation_postgres.py` shows all
  16 M4e cases passing, with no failed or skipped integration cases.
- [Container](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39059247990/job/117473629927):
  all six steps executed and succeeded: configuration, effective context, image build, image
  checks, smoke and cleanup. The context summary reports 87 files and 19 planted fixtures
  excluded. Production backfill enqueued one offline indexing job; the index became ready for
  the ingested revision with two embeddings and a succeeded indexing job. The idle worker
  exited with code 0 without OOM. These printed summaries and passing gates are not independent
  inspection of raw database rows. The smoke covers ingestion/indexing and idle-worker shutdown
  only, not retrieval or M4e evaluation; local Compose remains unverified.
- [Gitleaks](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39059247979/job/117473629950):
  65 commits scanned, no leaks found. Pattern scanning is not a general security guarantee.

Both successful installed-wheel logs contain these output lines:

```text
offline embedding, canonical storage and indexing modules ran from the installed wheel
retrieval modules imported and fusion ran from the installed wheel
evaluation modules imported and Recall@5 = 2/3 computed from the installed wheel
offline migration SQL rendered from the installed wheel
```

The wheel's 2/3 Recall fixture is pure arithmetic, not measured corpus Recall from PostgreSQL.
No numerical database-derived corpus Recall value was supplied. Ubuntu's relevant corpus and
worker modules showed passing dots; the corrected test and symlink test were not individually
named. The green suite is evidence for the paths exercised under the unchanged collection
configuration, not an individually named test-log observation or a guarantee beyond those paths.
The PostgreSQL cases exercise fresh loading, the read-only verifier, evaluation and isolation
against stored chunks; the tests establish their asserted behaviour on the exercised fixtures.

Recall remains report-only with no threshold. Ranking/mapping determinism has the documented
limits, including variation across fresh loads. Offline hashing supplies no semantic-quality
claim; no live provider was verified. No injection-resistance, production-readiness or general
security guarantee follows. Trusted in-process snapshots cannot prove past eligibility; M5
obligations remain. At that point (Prompt 152, historical), M4e was reviewed and verified on the
feature branch, not merged, with main at `cf2b5743`, and reviewed publication to main was still
required; Prompt 152 staged documentation for review only. That publication has since occurred
(see [Main CI evidence at `0ae4c6ca`](#main-ci-evidence-at-0ae4c6ca)). M4f and overall M4
acceptance remain pending.

## Exact-commit CI at `c14821b7` and test correction (Prompts 148–149)

**Publication (Prompt 148).** Claude Code published `feat/retrieval-evaluation` at
`c14821b72d82f3a174123011b4d2c002fdcadbf3` (a history-only commit on top of the accepted
implementation commit `f01af7eb`). The push-triggered
[ci run](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39051603984)
(attempt 1) **failed**; the secret-scan run succeeded. Claude Code observed only GitHub API
conclusions (its anonymous log downloads returned HTTP 403): Ubuntu verify failed at its `Test`
step, with the build and installed-wheel steps skipped; Windows verify, PostgreSQL integration,
the container job (all six steps) and full-history Gitleaks succeeded.

**Evidence retrieved independently by the external reviewer** (connected GitHub log retrieval;
not observed by Claude Code):

- [Ubuntu verify](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39051603984/job/117451164827):
  `1 failed, 2245 passed, 306 skipped in 23.00s`. The failure is
  `tests/test_evaluation_worker.py::test_a_file_larger_than_its_reported_size_fails_within_its_bound`,
  asserting at line 598: expected `corpus_file_changed`, received `corpus_read_failed`.
  Formatting, lint and type checks passed; the build and installed-wheel steps were skipped.
- [PostgreSQL integration](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39051603984/job/117451164752):
  `306 passed, 2246 deselected in 212.64s`; the log shows all 16 tests in
  `tests/test_evaluation_postgres.py` passing. This is the first executed PostgreSQL evidence for
  M4e. The logs supply no numerical Recall result, and none is claimed.
- No additional counts or output were supplied for the Windows, container or secret-scan jobs.

**Diagnosis (external reviewer).** The test replaced `os.lstat` with a double that called
`Path(path).resolve()` to identify its target. On Linux, `Path.resolve()` itself calls
`os.lstat`, so the double re-entered itself (by Claude Code's reading of the reader, the
resulting ordinary `RecursionError` is what its guard converts to the private
`corpus_read_failed`). The reviewer reproduced the recursion with a
standalone standard-library probe on Linux. This is a defect in the test double; no production
defect has been established. On Windows, `Path.resolve()` does not call `os.lstat`, which is why
the test passed there.

**Correction (Claude Code, Prompt 149, test-only; accepted at external review in Prompt 150 for a local commit).** The double now
identifies its target with a purely lexical key (`os.path.normcase(os.path.abspath(...))`),
computed for the target before the patch is installed, so it performs no file-system operation
that could re-enter the patched function. It keeps every `st_*` field of the real result and
reports the target's size 10 bytes smaller, so the reader's bounded read still observes
`corpus_file_changed`. A new assertion requires that the understated result was actually
returned for the target, so the test cannot pass without exercising the intended condition. The
production reader, its validation and its error codes are unchanged, and the test is not skipped
on any platform. The other file-system doubles in the file (`os.open`, `Path.read_bytes`,
`os.fdopen`) use only lexical path operations and were left unchanged.

**Historical verification (Prompt 149).** Run locally on Windows by Claude Code (locked environment, offline;
no Docker, database or external provider contact):

- the corrected test passed, and `tests/test_evaluation_worker.py`: 99 passed;
- `ruff format --check .` (171 files) and `ruff check .`: clean; strict `mypy` (135 source
  files): no issues;
- full suite: 2244 passed, 308 skipped (306 integration tests without a database, the symlink
  test and the POSIX-only signal test);
- a standalone standard-library probe on Windows, calling `posixpath.realpath` (the function
  `Path.resolve()` uses on POSIX), reproduced the recursion with the old double's pattern and
  showed the new lexical key making no `os.lstat` call. This is a stand-in, not Linux execution.

At Prompt 149 no Linux environment was available, so corrected Linux execution and the Ubuntu
build and installed-wheel steps were pending. These gaps were subsequently closed for
`d1dcdfce` by the feature-branch CI evidence above; the Windows results here remain historical.

## External review acceptance of the test correction (Prompt 150)

The external reviewer inspected Claude Code's Prompt 149 correction export, independently
matched its size and SHA-256, and **accepted the test-only correction for a local commit**.
OpenAI Codex assisted with acceptance documentation and the local commit in Prompt 150;
Claude Code's implementation, correction and historical checks remain attributed to Claude Code.

The reviewer also ran a standalone standard-library probe on Linux using the corrected mock
pattern. It confirmed that `Path.resolve()` terminates without recursion; the target reports
10 fewer bytes while every other `st_*` field is preserved; a non-target file's stat result
is unchanged; the real file size remains unchanged and differs from the mocked size; and
the target override is exercised. This was an isolated probe, not execution of the project
test, suite, reader, wheel or database. **At Prompt 150**, corrected Linux project tests, the
Ubuntu build and installed-wheel steps, and green current-version CI were pending; these
subsequently passed at `d1dcdfce` (feature-branch evidence above). No project checks were
repeated by Codex for that documentation/commit task. The failed-run and passing PostgreSQL
evidence in the historical `c14821b7` section remain scoped to that commit; no
database-derived Recall number is supplied. At Prompt 150, M4e was published on the feature
branch and not merged to `main` (historical). Prompt 150 authorized a local correction commit only, with no push,
CI rerun or merge. M4f and overall M4 acceptance remain pending; local Compose is unverified.

## Verification (Prompt 146)

Historical local evidence, attributed to Claude Code and not rerun for acceptance. Run locally on Windows by Claude Code (locked environment; no Docker, database or external
provider contact; only the offline `HashingEmbedder` ran). **Pending at the time:** all 16 PostgreSQL
tests, the symlink refusal test, every CI job for the current tree and Gitleaks in CI.

- `ruff format --check .` (171 files) and `ruff check .`: clean; strict `mypy` (135 source
  files): no issues;
- focused tests (the four database-independent M4e files and `tests/test_packaging.py`): 256
  passed, 1 skipped (the symlink test);
- full suite: 2244 passed, 308 skipped (306 integration tests without a database, the symlink
  test and the POSIX-only signal test); collection: 2552 tests, 306 integration;
- `uv build` and an isolated installed-wheel environment outside the checkout (dependencies from
  `uv.lock`, offline with `--require-hashes`, wheel with `--no-deps`): every CI wheel command
  extracted from `ci.yml` passed; a narrow probe from the installed wheel showed
  `KeyboardInterrupt` and `SystemExit` from the clock result's `scalar_one()` escaping as the
  same objects despite rollback and close failures, and an ordinary `scalar_one()` failure
  becoming a private `corpus_read_failed`; the Prompt 145 probe also still passed.

## Verification (Prompt 145)

Historical (before the Prompt 146 correction). Run locally on Windows by Claude Code (locked environment; no Docker, database or external
provider contact; only the offline `HashingEmbedder` ran). **Pending at the time:** all 16 PostgreSQL
tests, the symlink refusal test (it needs a symlink-capable account or Linux CI), every CI job
for the current tree and Gitleaks in CI.

- `ruff format --check .` (171 files: 135 Python and 36 Markdown) and `ruff check .`: clean;
  strict `mypy` (135 source files): no issues;
- focused tests (the four database-independent M4e files and `tests/test_packaging.py`): 237
  passed, 1 skipped (the symlink test);
- full suite: 2225 passed, 308 skipped (306 integration tests without a database, the symlink
  test and the existing POSIX-only signal test); collection: 2533 tests, 306 integration;
- `uv build`: the sdist contains the 16 `sample_data` files and the new test file; the wheel
  contains no `sample_data`;
- isolated installed-wheel environment outside the checkout (dependencies from `uv.lock`,
  offline with `--require-hashes`, wheel with `--no-deps`): every CI wheel command extracted
  from `ci.yml` passed, including the M4e step; a narrow probe from the installed wheel showed
  both committed variants passing `validate_suite`, a schema-valid suite with an unmappable
  anchor refused by `run_fresh_two_epoch` before its session factory was called, and `_read`
  re-raising the same `KeyboardInterrupt` object despite a rollback failure.

## Verification (Prompt 144)

Historical (before the Prompt 145 corrections). Run locally on Windows by Claude Code (locked environment; no Docker, database or external
provider contact; only the offline `HashingEmbedder` ran). **Pending at the time:** every PostgreSQL test,
all CI jobs and Gitleaks in CI.

- `ruff format --check .` (170 files: 134 Python and 36 Markdown) and `ruff check .`: clean; strict `mypy` (134 source
  files): no issues;
- focused tests (the three database-independent files and `tests/test_packaging.py`): 147 passed,
  1 skipped (the symlink test: this Windows account cannot create symbolic links);
- full suite: 2135 passed, 308 skipped (306 integration tests without a database, the symlink
  test and the existing POSIX-only signal test);
- collection: 2443 tests, 306 integration (16 in `tests/test_evaluation_postgres.py`);
- `uv build`: the sdist contains the 16 `sample_data` files and the four test files; the wheel
  contains the evaluation modules and no `sample_data`;
- isolated installed-wheel check outside the checkout (dependencies from `uv.lock`, offline with
  `--require-hashes`, wheel with `--no-deps`): every CI wheel command extracted from `ci.yml`
  passed, including the new M4e step.

## Limits

- Recall from the offline hashing profile measures lexical overlap on a tiny fictional corpus; it
  is not a semantic-quality, benchmark or production result, and no threshold is applied.
- Isolation checks cover the returned chunks and the corpus's canaries only; they do not prove
  tenant isolation in general. End-to-end canary and output behaviour remain M5/M7, and the
  injected variant makes no injection-resistance claim.
- The orchestrator trusts its caller to pass a guarded disposable database; it has no production
  entry point.
