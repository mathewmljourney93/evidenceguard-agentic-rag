# ADR-0016: Trusted snapshot capture and snapshot-relative hybrid retrieval

- **Status:** **Accepted at external review in Prompt 136; reviewed and verified in
  feature-branch CI at `3d6e8395`; not merged.** `main` is unchanged at `76fa5a3`. Implemented by
  Claude Code in Prompt 134 and corrected in Prompt 135 (see
  [Prompt 135 corrections](#prompt-135-corrections) and
  [External review](#external-review-prompt-136)) from the
  [accepted specification](../plan.md#m4d-snapshot-and-retrieval-specification-accepted-at-review-prompt-133-implementation-pending)
  (proposed in Prompt 131, corrected in Prompt 132, accepted at review in Prompt 133). The
  push-triggered CI and secret-scan runs for exact commit `3d6e8395` passed on Ubuntu, Windows,
  PostgreSQL (all 39 M4d cases), the container job and Gitleaks (see
  [Feature-branch CI evidence](#feature-branch-ci-evidence-at-3d6e8395)); this is the first
  executed PostgreSQL evidence for M4d. Claude Code's local Windows checks under
  [Verification](#verification) are historical. M4c remains verified and on `main` at `76fa5a3`. M4e–M4f and overall M4 acceptance remain
  pending. Local Compose remains unverified.
- **Date:** 2026-10-17
- **Builds on:** [ADR-0015](0015-revision-indexing.md) (M4c indexing), [ADR-0014](0014-embedding-persistence.md)
  (M4b storage), [ADR-0013](0013-embeddings.md) (M4a provider boundary), [ADR-0011](0011-document-api.md)
  (`read_snapshot`).

## Decision

M4d adds a trusted snapshot capture seam, an immutable snapshot value, strict retrieval inputs,
the lexical and exact-vector channels, deterministic reciprocal-rank fusion (RRF), bounded results
with chunk evidence and provenance, and fixed provider and database failure boundaries. Settled
decisions R1–R9 and the Prompt 108 policies apply unchanged. There is no migration, schema,
extension, dependency, lockfile, Dockerfile, Compose or engine-setting change, no endpoint, CLI,
worker handler or registry kind, no review persistence, report, activation wiring, stalled-index
recovery, corpus, Recall, live provider or approximate index.

| File | Content |
|---|---|
| `evidenceguard_domain/retrieval.py` | Frozen values, the `eg-retrieval-canonical-v1` encoding and digests, `query_vectors`, the pure `fuse`, fixed errors |
| `evidenceguard_persistence/retrieval.py` | `capture_snapshot`, `retrieve_with_vectors`, the statements, row conversion and the database failure boundary (`run_read`) |
| `evidenceguard_worker/retrieval.py` | `search_snapshot`, `search_current` and the provider failure boundary |
| `.github/workflows/ci.yml` | R9 only: import the three modules from the installed wheel and run `fuse` on a pinned fixture |

`evidenceguard_retrieval`, `read_snapshot` and every existing import direction are unchanged.

## Values, encoding and digests

Every value is a frozen dataclass whose constructor validates exact types (no coercion, no
`bool` for `int`, tuples only, no `str` for a `UUID`), rejects unknown keyword arguments, keeps
text verbatim and raises a fixed error outside any `except` block; `dataclasses.replace`
revalidates. Derived values (`config_sha256`; the snapshot's `profile_id`, `total_chunks` and
`sha256`; the result's tenant, vendor, digests, fingerprint and label) are computed by the
constructor and cannot be supplied. `repr`/`str` show identifiers and counts only. The canonical
encoding and both object layouts are exactly those of the specification; `captured_at` is stored
in UTC and encoded with six fractional digits. Identical encoded fields give the same digest,
different encoded timestamps can give different digests, and neither a digest nor a timestamp is
authorization, proof of past eligibility or a unique capture identifier.

## Trust model (unchanged from R3)

The seams are trusted internal programming interfaces; no endpoint calls them and no snapshot is
deserialized from untrusted input. `capture_snapshot` is the only producer of snapshots and takes
the tenant only from the trusted `ActorContext` (reviewer or approver, R4). Before every
retrieval, one statement rechecks every immutable binding (vendor, document, settled revision,
chunk set, ready index, profile) without consulting the current revision `status`, so a revision
active at capture stays eligible after supersession and a new revision never enters an older
snapshot. The recheck **cannot prove past active-at-capture eligibility**: a structurally valid
snapshot built by in-process code from a same-vendor revision superseded before capture passes
it (a PostgreSQL test documents this). M5 must persist the captured facts with review creation and
reload them only through trusted paths. No protection against malicious in-process code is
claimed. The precomputed-vector seam is trusted input: validation cannot prove that the vectors
were computed from the claimed query strings.

## Transactions and failure boundaries

Capture and retrieval each run one transaction through the unchanged `read_snapshot`: `SET
TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY`, then its `SELECT clock_timestamp()`,
which establishes the snapshot, then `SET LOCAL statement_timeout = 30000` (per statement), then
the data statements. Nothing is written, enqueued or explicitly locked. Provider calls and
canonical query conversion run outside any transaction.

**Database boundary (`run_read`).** The body returns a result or a `SemanticOutcome` value; a
semantic outcome is never inferred from an exception or its chain. An inner `try` records any
ordinary body `Exception` as operational; an outer `try` records failures of session creation,
the helper's statements or cleanup. After both, outside every handler, the seam returns the result
or raises a fresh fixed error: the recorded semantic error (which stays primary if cleanup also
fails), otherwise `RetrievalDatabaseError`, also when a successful body is followed by a cleanup
failure. No original exception, statement, parameter, cause or context is kept, nothing retries
and nothing logs. `BaseException` subclasses that are not `Exception` propagate unconverted. The
session handed to the unchanged helper records any process-control exception raised by its
`execute`, `rollback` or `close`, including during the helper's two setup statements; the body
records one it raises. If an ordinary cleanup failure then replaces it, that same control
exception object is re-raised. This records process control only and never classifies semantic
outcomes.

**Provider boundary.** `search_snapshot` reads and validates `provider.identity` in its own
`try`, then calls `embed_validated` once, then converts against the snapshot identity, each with
the same outside-`except` mapping to `RetrievalProviderError`. `retrieve_with_vectors` validates
the batch again independently. No `JobContext` integration or cancellation protocol is added; M5
must define cancellation and lease precedence.

## Material implementation choices

These are routine choices within the accepted contract, recorded for review:

1. **Bindings as typed arrays.** Channel, recheck and evidence statements read the bindings from
   `unnest(CAST(:… AS uuid[]), …) AS b(…)` instead of a literal `VALUES` list: the same relation,
   constant SQL text and explicit types. Each channel statement still repeats the complete
   eligibility joins before its `LIMIT 20`.
2. **`ts_rank_cd(…, 0)`** passes the accepted normalization explicitly.
3. **Validation precedence.** The specification's summary order is applied everywhere: actor
   type, then input and structure (request, snapshot or capture inputs), then role, then scope,
   then provider or batch, then the database phase. Its step list for `retrieve_with_vectors`
   names role before structure; the summary order was chosen so that all seams agree.
4. **Error classes for result values.** `ChannelList`, `ChannelHit`, `FusedChunk`, `SourceSpan`,
   `ChunkEvidence`, `RetrievedChunk`, `RetrievalResult` and `fuse` raise
   `InvalidRetrievalRequestError` when called directly; persistence maps any such failure while
   building from rows to `SnapshotInconsistentError`. The errors share a `RetrievalError` base
   whose message is the fixed code; constructors take no arguments.
5. **Additional values.** `FusedChunk` carries a fused candidate between `fuse` and evidence
   loading. `RetrievalResult` holds its snapshot and derives the tenant, vendor and digests from it,
   so binding ownership of every item can be checked.
6. **Stricter snapshot invariants.** Excluded revision IDs must be disjoint from the bindings, and
   `revalidate_snapshot` requires the rebuilt value to equal the original, so a value altered after
   construction is rejected.
7. **Capture classification.** A stored profile whose fingerprint matches but whose fields differ
   is a consistency failure; an index ID that is not the derived ID fails when the snapshot is
   built (after the phases), as `SnapshotInconsistentError`.
8. **Row conversion.** Only fixed domain validation errors raised while constructing values from
   rows are semantic (`snapshot_inconsistent`); any other exception while reading rows is
   operational.
9. **`search_current`** checks actor type, request, vendor ID and role, then reads the provider
   identity (needed to pin the profile, protected like `search_snapshot`'s read) before capture.
10. **No evidence statement** runs when fusion yields no candidates.
11. **`STATEMENT_TIMEOUT_MS`** is a module constant read at call time; one PostgreSQL test lowers
    it locally with `monkeypatch` to provoke a timeout. The production value is not changed.

## Tests

| File | Kind | Content |
|---|---|---|
| `tests/test_retrieval_contracts.py` | database-independent | strict bounds and malformed values, independently pinned canonical bytes and digests, timestamps, invariants, `replace` revalidation, representations, query-vector conversion, fusion fixtures (ties, duplicates across queries and channels, a case where float order differs but `Fraction` ties, fewer than k, empty) |
| `tests/test_retrieval_store.py` | database-independent, fake sessions | statement order, phases and their precedence under permuted row orders, exclusions, channel SQL shape, recheck and row failures, standalone batch validation, setup/body/cleanup failure matrix, chained-semantic cases, privacy of messages, chains and tracebacks, no logging, no retry, process-control propagation including with cleanup failure; from Prompt 135, a process-control matrix (`KeyboardInterrupt` and `SystemExit` during `SET TRANSACTION`, `clock_timestamp()` or the body, with no, rollback, close or both cleanup failures, plus control raised by cleanup itself) |
| `tests/test_retrieval_orchestration.py` | database-independent | ordering, identity-getter failures, mismatch, identity change between reads, malformed results, provider exceptions, no session open during embedding, capture before the provider call |
| `tests/test_retrieval_postgres.py` | PostgreSQL integration | capture, exclusions and truncation, refusal cases, bounds and precedence, scope, supersession, real lexical semantics, exact cosine ordering and ties, zero vectors, end-to-end fusion, filters before limits, multiple profiles and a building index, more than 20 tempting wrong-profile and partial building-index rows (Prompt 135), binding recheck forgeries, the documented R3 limitation, deterministic capture interleavings and a replacement activated while retrieval pauses after the recheck (Prompt 135), timeouts, pooled settings, unchanged rows, no approximate index and evidence with a repeated header |
| `tests/test_packaging.py` | database-independent | the three modules' import boundaries |

**Lower-level fixture exception (approved at review in Prompt 135).** `_chunk_heavy_vendor`
(PostgreSQL tests) marks revisions active and indexes ready directly, with chunk sets that declare
4,096 chunks and store none, so the 100,000-chunk bound can be exercised without inserting about
100,000 chunks and vectors. Prompt 134 proposed it; the reviewer approved it in Prompt 135
**solely for testing capture's metadata-based chunk-count arithmetic**. It may bypass ingestion
completeness and indexing readiness verification for that isolated bound test, and it proves
neither ingestion/indexing correctness nor actual stored-vector completeness. Every other
retrieval test uses the real ingestion and indexing paths. Other tests modify rows directly only
to simulate corruption (a pointer naming a superseded revision) or forge snapshots.

## Prompt 135 corrections

The external review of Prompt 134 found two defects with isolated standard-library probes (no
project suite, PostgreSQL or Docker), and asked for further PostgreSQL coverage:

1. **Setup-time process control.** `run_read` recorded process control only inside the yielded
   body. A `KeyboardInterrupt`/`SystemExit` raised by the helper's `SET TRANSACTION` or
   `clock_timestamp()` statement, followed by an ordinary rollback or close failure, surfaced as
   `RetrievalDatabaseError` and the control exception was lost. The session handed to the unchanged
   helper now records process control from `execute`, `rollback` and `close`, and the same object is
   re-raised. The regression matrix also showed that control raised by `rollback` and then replaced
   by an ordinary `close` failure was lost in Prompt 134; it is now preserved too.
2. **Chunk-bound fixture.** `_chunk_heavy_vendor` restarted at `heavy-0` on its second call, so
   `create_revision` returned the existing revision and the chunk-set insert would have duplicated
   its key. It now takes an explicit `start`, and the test asserts 25 distinct documents,
   revisions, chunk sets and ready indexes declaring 102,400 chunks before the rejection.
3. **Added PostgreSQL coverage (written, not run in Prompt 135; passed in feature-branch CI at
   `3d6e8395`).** A retrieval paused right after the binding
   recheck while a replacement is ingested, activated and indexed through the real lifecycle,
   then resumed: only the old revision is returned. And more than 20 tempting rows from a
   wrong-profile ready index (26 rows) and a building index with one committed page (32 of 40
   rows, the second provider page failing), all at cosine distance 0 to the query: the eligible
   target stays first in both channels and no row leaks or duplicates.

No other implementation file changed.

## External review (Prompt 136)

The external reviewer accepted the complete implementation with the Prompt 135 corrections for a
local implementation commit, then pending PostgreSQL and current-version CI verification (since
completed on the feature branch; see
[Feature-branch CI evidence](#feature-branch-ci-evidence-at-3d6e8395)). The reviewer
inspected both exports and independently matched their checksums
(`.local/p134/m4d-implementation.diff`, 274,711 bytes, SHA-256
`ea65813114e1d316e74f23b88551f4aea61227215a54a90a4d9eba9e157db33b`;
`.local/p135/m4d-corrections.diff`, 70,514 bytes, SHA-256
`ef1d8b5954a5b1465c5c016a000cdb2d76c26128bad3e6897b6a690525b6348c`); inspected the
implementation, corrections, supporting tests, workflow extension and documentation; probed the
original setup-time process-control and fixture-reuse failures with doubles; and probed the
corrected process-control functions in isolation, where 24 combinations passed (`KeyboardInterrupt`
and `SystemExit` during either setup statement or the body, with no cleanup failure, a rollback
failure, a close failure or both). The reviewer also inspected the corrected fixture and the added
PostgreSQL tests. The reviewer ran no project suite, regression suite, build, installed-wheel
check, PostgreSQL or Docker. That 24-case probe is separate from Claude Code's 34-case regression
matrix and installed-wheel probes below, which remain Claude Code's evidence.

## Verification

### Prompt 135 (Claude Code; historical)

Run locally on Windows by Claude Code (locked environment; no Docker, database or external
provider contact; only the offline `HashingEmbedder` ran):

- regression comparison of the new process-control matrix (34 cases): against the saved Prompt
  134 persistence module, **14 failed and 20 passed** (the 12 setup-phase cases with a rollback or
  close failure, and the 2 cases of control from `rollback` replaced by a `close` failure);
  against the corrected module, **34 passed**. The corrected file was restored and its SHA-256
  matched the saved corrected copy;
- `ruff format --check .` (147 files) and `ruff check .`: clean; strict `mypy` (125 source
  files): no issues;
- focused affected tests: 310 passed, 39 skipped (the M4d PostgreSQL tests, without a database);
- full suite: 2001 passed, 291 skipped, being 290 integration tests without a database (251
  existing plus 39 M4d) and one POSIX-only signal test;
- collection: 2292 tests, 290 integration (39 in `tests/test_retrieval_postgres.py`);
- `uv build` and the isolated installed-wheel checks (dependencies from `uv.lock`, offline with
  `--require-hashes`, wheel with `--no-deps`) passed, including every CI wheel command and a
  direct installed-wheel probe of `run_read`: `KeyboardInterrupt` and `SystemExit` during either
  setup statement with a rollback or close failure escaped as the same object (8 of 8), and an
  ordinary setup failure stayed a private `RetrievalDatabaseError`.

### Prompt 134 (historical)

Run locally on Windows by Claude Code in Prompt 134 (locked environment; no Docker, database or
external provider contact; only the offline `HashingEmbedder` ran):

- `ruff format --check .` (146 files) and `ruff check .`: clean; strict `mypy` (125 source
  files): no issues;
- focused new and affected tests: 473 passed, 37 skipped (the 37 M4d PostgreSQL tests, without a
  database);
- full suite: 1967 passed, 289 skipped, being 288 integration tests without a database (251
  existing plus 37 new) and one POSIX-only signal test. The 252 new database-independent tests
  (167 contracts, 56 store, 26 orchestration, 3 packaging) all ran and passed;
- collection: 2256 tests, 288 integration (37 in `tests/test_retrieval_postgres.py`), 1968
  database-independent;
- `uv build`: the sdist and wheel built;
- isolated installed wheel: a venv outside the checkout with dependencies from `uv.lock`
  (`uv export --frozen --no-dev --no-emit-project`, installed offline with `--require-hashes`)
  and the wheel with `--no-deps`. Every CI wheel command, extracted verbatim from `ci.yml`
  (including the new M4d step), passed; the three new modules resolved to `site-packages`.

**Historical (before Prompt 137 CI):** at the time of these local results, the 39 PostgreSQL
integration tests (written and collected, not executed), Linux, the CI installed-wheel step on CI
runners and every current-version CI job were pending. They have since run in feature-branch CI at
`3d6e8395` (below). The unchanged container smoke verifies ingestion and indexing, not M4d
retrieval. The pure fusion fixtures do not establish that PostgreSQL ranks or filters correctly;
the PostgreSQL tests do, for the cases they cover.

## Feature-branch CI evidence at 3d6e8395

The push-triggered `ci` and `secret-scan` runs for exact commit
`3d6e8395f09dbb6d9eb602fe24bcfed46a7f88f2` on `feat/snapshot-retrieval` (event `push`, attempt 1)
both concluded **success**:
[CI run 39018717538](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39018717538)
and
[secret-scan run 39018717584](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39018717584).
In Prompt 137, Claude Code published the branch and observed run, job and step conclusions through
the public API only; its anonymous log downloads returned HTTP 403. The external reviewer then
independently retrieved both run records, all five job records and all five job logs through
connected GitHub tooling (Prompt 138); the log details below come from that retrieval. The
reviewer ran no local project suite, PostgreSQL, Docker or provider calls for this evidence.

| Job | Observed |
|---|---|
| [Ubuntu verify](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39018717538/job/117356036652) | `2002 passed, 290 skipped in 19.97s` (the 290 PostgreSQL tests are skipped in this job); format, lint, type-check, distribution build and clean installed-wheel checks passed |
| [Windows verify](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39018717538/job/117356036659) | `2001 passed, 291 skipped in 27.42s` (the 290 PostgreSQL tests and the POSIX-only signal test); the same checks passed |
| [PostgreSQL integration](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39018717538/job/117356036581) | `290 passed, 2002 deselected in 121.28s (0:02:01)`; the log shows all 39 cases in `tests/test_retrieval_postgres.py` passing, none failed or skipped |
| [Container](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39018717538/job/117356036757) | all six steps executed and succeeded (rendered Compose configuration, effective build context, image build, image checks, Compose smoke, scoped cleanup) |
| [Gitleaks (full history)](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39018717584/job/117356036744) | 59 commits scanned, no leaks found |

No required job or step was skipped, failed or cancelled.

- **Installed wheel (Ubuntu and Windows):** the output contained `offline embedding, canonical
  storage and indexing modules ran from the installed wheel`, `retrieval modules imported and
  fusion ran from the installed wheel` (the R9 check) and `offline migration SQL rendered from the
  installed wheel`.
- **PostgreSQL:** the first executed PostgreSQL evidence for M4d, including the Prompt 135
  corrections and coverage: capture and its refusals and bounds (with the approved metadata-only
  chunk-bound fixture), lexical semantics, exact cosine ordering and ties, fusion, filters before
  limits, profile and building-index isolation, binding rechecks, deterministic interleavings,
  timeouts, pooled settings, unchanged rows and evidence provenance.
- **Container (printed summaries, not independently inspected rows):** effective context `82
  files; 19 planted fixtures excluded`; UID and GID 10001 checks; `eg-api`, `eg-worker` and
  `eg-admin` help; installed imports, offline migration SQL and runtime-content checks; healthy
  database, completed migration and healthy API, with migrate, API and worker on the CI-built
  image; an API key created and held in memory only; an upload accepted with 202, the ingestion
  job succeeding and the revision active with two verified chunks; a duplicate upload returning the
  existing revision with 200; the production backfill enqueuing one offline indexing job, and the
  index becoming ready with two embeddings and the job succeeding; the idle worker exiting with
  code 0 and no OOM kill; `smoke: ok`; ownership-scoped cleanup with `cleanup: ok`. This unchanged
  smoke verifies ingestion and indexing only, **not M4d retrieval**, and idle-worker shutdown only.

This evidence establishes the covered paths in this run for this commit. It is not a
semantic-quality, retrieval-quality, benchmark, production-readiness or general security guarantee,
and it says nothing about other PostgreSQL versions, platforms or live providers. M4d is not
merged; `main` is unchanged at `76fa5a3`.

## Limits

- No semantic-quality, retrieval-quality, injection-resistance, benchmark or production-readiness
  claim. The offline profile is a lexical-hash baseline, not semantic.
- Determinism is claimed only for a fixed snapshot, configuration, stored rows, PostgreSQL version
  and query vectors.
- The per-statement timeout is not a deadline for a whole capture or retrieval; the 100,000-chunk
  scan-volume figure is an engineering estimate, not a measurement.
- The trusted in-process snapshot model and its past-eligibility limitation hold until M5.
- Repeated table headers are a separate span; later citation code must not quote across the
  header/body boundary.
