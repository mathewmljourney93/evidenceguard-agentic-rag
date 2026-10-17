# ADR-0017: Synthetic corpus, anchor-to-chunk ground truth and retrieval evaluation

- **Status:** **Accepted at external review in Prompt 147 for a local implementation commit,
  pending current-version CI** (see [External review](#external-review-prompt-147)); not
  published or merged. Implemented by Claude Code in Prompt 144 on `feat/retrieval-evaluation`
  and corrected in Prompts 145 and 146 (see [Prompt 145 corrections](#prompt-145-corrections)
  and [Prompt 146 correction](#prompt-146-correction)). Implements the
  [accepted M4e specification](../plan.md#m4e-corpus-and-retrieval-evaluation-specification-accepted-at-review-prompt-143-implementation-pending)
  (proposed in Prompt 140, corrected in Prompts 141–142, accepted at external review in Prompt
  143). Only database-independent checks ran, locally on Windows, as historical evidence
  attributed to Claude Code (see [Verification (Prompt 146)](#verification-prompt-146); the
  [Prompt 145](#verification-prompt-145) and [Prompt 144](#verification-prompt-144) checks
  are separately scoped). **Pending:** every PostgreSQL test (all 16 M4e cases have never run,
  and none of the 306 integration tests has run against this version), Linux and
  current-version CI (including the installed-wheel step and Gitleaks in CI) and the symlink
  refusal test; no claim depending on PostgreSQL has been executed and no database-derived
  Recall or isolation result exists. M4d remains reviewed, verified in CI and on `main` at `cf2b5743`; M4f and overall M4
  acceptance remain pending. Local Compose remains unverified.
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

**Outstanding:** no PostgreSQL test (none of the 16 M4e cases and none of the 306 integration tests against this version) has run, Linux and current-version CI are pending, the symlink refusal test has not run, and no database-derived Recall or isolation result exists. The implementation is not published or merged.

## Verification (Prompt 146)

Historical local evidence, attributed to Claude Code and not rerun for acceptance. Run locally on Windows by Claude Code (locked environment; no Docker, database or external
provider contact; only the offline `HashingEmbedder` ran). **Pending:** all 16 PostgreSQL
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
provider contact; only the offline `HashingEmbedder` ran). **Pending:** all 16 PostgreSQL
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
provider contact; only the offline `HashingEmbedder` ran). **Pending:** every PostgreSQL test,
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
