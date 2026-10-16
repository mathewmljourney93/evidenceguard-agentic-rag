# ADR-0015: Revision indexing, backfill and atomic readiness

- **Status:** **M4c is accepted at review, reviewed and verified in CI on
  `feat/revision-indexing` at `600a366`, not merged. Main remains at `872d0af`.** Implemented by
  Claude Code in Prompt 125 and corrected in Prompt 126; accepted at external review in Prompt 127
  for a local commit; the feature branch was published in Prompt 128. The
  [specification](../plan.md#m4c-indexing-specification-accepted-at-review-prompt-124-implementation-pending)
  was accepted at review in Prompt 124. Both push workflows for exact commit `600a366` passed,
  including the 18 PostgreSQL indexing cases, the installed-wheel embedding/indexing check on
  Ubuntu and Windows and the container indexing smoke (see
  [Feature-branch CI evidence](#feature-branch-ci-evidence-at-600a366)). Publication to `main` is
  pending. M4d–M4f and overall M4 acceptance remain pending. Local Compose remains unverified.
- **Date:** 2026-10-16
- **Builds on:** [ADR-0014](0014-embedding-persistence.md) (M4b store), [ADR-0013](0013-embeddings.md)
  (M4a provider boundary), [ADR-0007](0007-durable-job-core.md) and [ADR-0008](0008-worker-runtime.md)
  (fences, runtime), [ADR-0005](0005-api-key-authentication.md) (`eg-admin`).

## Decision

M4c turns M4b's storage into a working offline indexing path. It adds enqueue and bounded backfill
seams, the `eg-admin backfill-indexes` command and the production `index_revision` handler. No
migration, dependency, lockfile, Dockerfile or Compose change was needed. Activation wiring,
recovery of terminal jobs, live providers, retrieval and M4d–M4f are not implemented.

| File | Content |
|---|---|
| `evidenceguard_persistence/indexing.py` | `enqueue_index_revision`, `backfill_index_revisions`, `load_index_target`, `pending_chunks`, `PendingChunk` |
| `evidenceguard_worker/indexing.py` | `make_index_revision_handler`, the immutable `SUPPORTED_PROVIDERS`, `page_prefix`, `stored_identity`, `resolve_provider` |
| `evidenceguard_worker/handlers.py` | Registers `index_revision` beside `ingest_revision` |
| `evidenceguard_api/admin.py` | `backfill-indexes` and `DatabaseStore` (the account store plus the backfill seam) |
| `.github/workflows/ci.yml`, `infra/ci/container_ci.py` | Registry assertions; the embedding wheel check; the indexing smoke |

## Enqueue and backfill

`enqueue_index_revision(session, actor, *, revision_id, identity)` runs in the caller's READ
COMMITTED transaction. It validates the actor (reviewer, approver or admin), the revision ID and
the storable identity before any write. It then runs M4b's `ensure_profile` and `create_index`,
and, unless the index is ready, M3a's `enqueue` with payload `{"index_id": …}` and key
`str(index.id)`, using the default 3 attempts. The outcome is `ready` (nothing enqueued),
`pending` (the job is queued or running) or `stalled` (a terminal job for a building index,
returned unchanged). It is an observation within the transaction. Creation is never inferred, and
M3a's `enqueue` is unchanged. Conflicts propagate, and the caller's transaction rolls back.

`backfill_index_revisions(session_factory, actor, *, identity, limit=50, after=None)` validates
its inputs before any transaction. It then selects up to `limit` (1–100) of the tenant's revisions
that are `active` at selection, with a chunk set and without a ready index for the profile,
ordered by revision ID after the cursor. Each selected revision is enqueued in its own
transaction. `IndexSourceNotEligibleError` becomes `ineligible`, and
`JobIdempotencyConflictError`, `EmbeddingProfileConflictError` or `IndexConflictError` becomes
`conflict`, each with a null `index_id` after that item's rollback. Any other failure propagates;
items committed earlier stay committed. `next_after` is the last selected ID when the page is full.
The supersession-race and cursor limits of the specification apply as written.

`eg-admin backfill-indexes --tenant-id T [--limit N] [--after R]` runs one page with
`HASH_IDENTITY`. It acts as the fixed system actor
`uuid5(NAMESPACE_URL, "https://evidenceguard.invalid/actors/eg-admin/v1")` with role admin for the
tenant. It prints `pending=… ready=… stalled=… ineligible=… conflict=…` and `next_after=…` only,
and exits 0 for a clean page, 3 for a page with stalled, ineligible or conflict items, 1 on failure
(fixed message) and 2 on a usage error (static message, before any database access). An invalid
`--limit` (outside 1–100, not plain digits) is a usage error.

## Handler

1. The payload must be exactly `{index_id}`, or `PermanentJobError` before any fence.
2. A short read-purpose fenced transaction (an ordinary fence holding the job lock, not `READ
   ONLY`) reads the index and its stored profile, tenant-scoped and without an index row lock.
3. `stored_identity` rebuilds the `EmbeddingIdentity` and requires its fingerprint to equal the
   stored one before any provider is resolved.
4. An already-ready index finishes through `mark_index_ready` in `ctx.fenced(finish=True)` (M4b's
   no-op with a fresh ownership check).
5. `resolve_provider` looks the fingerprint up in an immutable `MappingProxyType` copied when the
   handler is built. The production mapping holds only the offline `HASH_IDENTITY`. The provider's
   identity must equal the stored identity.
6. Each page is read in a short fenced transaction: at most 32 chunks with no embedding in this
   index, ordinal greater than the cursor, ordered by ordinal. After the fence closes:
   - the handler keeps the longest prefix within 128,000 UTF-8 bytes and verifies each text hash;
   - it calls `ctx.check()`, runs `embed_validated` and `stored_embeddings` with no transaction,
     lock or session open, then calls `ctx.check()` again;
   - it writes through `write_embeddings` in a short fenced transaction;
   - the cursor advances to the last **kept** ordinal.

   Rows committed earlier are excluded by the read, so they are reused without provider calls;
   they are not re-verified against new provider output.
7. The finish block runs `mark_index_ready` (M4b's full completeness check) and records success in
   the same transaction.

A `write_embeddings` refusal (`EmbeddingWriteRefusedError`, another attempt made the index ready)
goes to the no-op finish. If provider execution or validation fails, `ctx.check()` runs before the
failure is classified, so a latched cancellation or lease loss wins.

**Provider resolution boundary (corrected in Prompt 126).** `resolve_provider` re-raises
`JobCancelledError`, `LeaseLostError` and `FenceClosedError` raised by the factory or the
provider's `identity` property unchanged. A `BaseException` that is not an `Exception` is never
caught. Any other failure of the factory or identity becomes the fixed `UnsupportedProfileError`,
raised outside the handler so the original exception and its text are not chained. The handler
then calls `ctx.check()` before classifying that failure as permanent, so a cancellation or lease
loss latched during the factory or identity call wins (subject to the same explicit-boundary race
as every other check). The Prompt 125 version caught every `Exception` there and converted the
three control-flow errors into `UnsupportedProfileError`; the reviewer reproduced this with an
isolated probe.

| Condition | Outcome |
|---|---|
| Payload, job binding or missing index | `PermanentJobError(permanent_failure)` |
| Stored-identity fingerprint mismatch, unsupported fingerprint, provider identity mismatch, an ordinary factory or identity failure (after `ctx.check()`), `EmbeddingProfileMismatchError` | `permanent_failure` |
| Text-hash mismatch, `EmbeddingSourceMismatchError`, `IndexIncompleteError` | `permanent_failure` |
| `InvalidEmbeddingError` from the provider boundary or post-rounding storage validation | `permanent_failure` |
| `EmbeddingConflictError`, `EmbeddingStorageRejectedError` | `permanent_failure`; nothing is overwritten |
| `JobLockTimeoutError` | `RetryableJobError(retryable_failure)` |
| `LeaseLostError`, `JobCancelledError`, `FenceClosedError`, anything else | Propagate (the runtime records `worker_shutdown`, nothing, or `unexpected_error`) |

**Guarantees and limits.** Checks happen at explicit boundaries only: before and after provider
work, at fence entry and after the job lock, and before success in the finish. They do not
interrupt synchronous provider or database calls, and a cancellation latched after the last check
may not stop a non-finish transaction already under way. The database fence remains
authoritative, and the accepted lease-expiry/commit window remains. Worker shutdown semantics are
unchanged. No exactly-once provider call is claimed, and an uncommitted page is recomputed on
retry. Nothing logs text, vectors, keys or exception details.

## Implementation details within the accepted contract

These are recorded for review; none changes an accepted behaviour.
1. `eg-admin` uses `DatabaseStore`, a subclass of the existing `DatabaseAdminStore` that adds
   `backfill_indexes`, so the existing account commands are unchanged.
2. The system actor ID is a fixed UUID5 literal (above). Backfill does not check that the tenant
   exists; a tenant with no eligible revisions yields an empty page and exit 0.
3. New fixed errors: `InvalidBackfillRequestError` (limit or cursor, before any transaction) in
   persistence, and `UnsupportedProfileError` and `SourceIntegrityError` in the worker. Both worker
   errors map to `permanent_failure`. A provider factory or identity property that raises an
   ordinary exception is treated as an unsupported profile; control-flow errors propagate.
4. `enqueue_index_revision` also rejects a revision ID that is not a `UUID` before any SQL.
5. `pending_chunks` re-applies the job binding and requires the passed index to be the job's own
   index in the job's tenant.
6. The container smoke expects exactly `pending=1` because its synthetic tenant has exactly one
   active revision. It compares the stored count with the index's and chunk set's `chunk_count`
   and with the count the API verified.

## CI changes

- **Registry assertions:** both kinds are now expected in `tests/test_worker_cli.py`, the CI wheel
  step and the image check.
- **Wheel step (Ubuntu and Windows):** a new isolated `python -I` script outside the checkout. It
  checks that the storage, indexing, provider and handler modules resolve to `site-packages`, runs
  `HashingEmbedder` through `embed_validated` and `stored_embeddings` (non-zero and zero rows, the
  4,100-byte wire format), checks the pinned offline fingerprint and the single-entry provider
  mapping, and checks both registry kinds. It contacts no database and does not establish indexing.
- **Container smoke:** after ingestion and the duplicate upload, and before the idle-worker stop,
  the smoke:
  - runs `eg-admin backfill-indexes` for the synthetic tenant, expecting exactly `pending=1` and
    exit 0;
  - polls, within a 90 s deadline and with per-command timeouts, a read-only `psql` session
    (`SET default_transaction_read_only = on`), with the tenant and revision UUID-validated
    before interpolation;
  - requires one index row with the same tenant and ingested revision and the pinned offline
    fingerprint, `ready`, its canonical `index_revision` job `succeeded`, and an embedding count
    equal to both `chunk_count` values and the API's verified count.

  A failed or dead job fails at once. The existing image-identity, privacy, log, first-failure,
  idle-shutdown and cleanup checks are unchanged.

## Tests added in Prompt 126

- **`tests/test_index_handler.py`:**
  - each control-flow error raised by the provider factory, and by the provider's identity
    property, escapes as the same object;
  - a cancellation or lease loss latched during a factory or identity call that then raises an
    ordinary error wins over the permanent classification, with no page read, write or success;
  - an ordinary factory or identity failure without a latch is a fixed `permanent_failure`
    whose exception chain and formatted traceback contain neither the original exception nor its
    text.
- **`tests/test_indexing_postgres.py`:**
  - the cancellation test now uses a test-owned handler wrapper that captures the real
    `JobContext`. It waits (bounded) until `cancel_requested` is actually latched before releasing
    the provider, and releases it in `finally`;
  - the competing-writer and lease-loss tests also release in `finally`;
  - two new tests: backfill excludes an index the real worker made ready, and reports a canonical
    job that the real lifecycle (three abandoned attempts, then a claim's sweep) made `dead` as
    `stalled`, leaving it unchanged.

## Verification

**Historical local verification (Prompts 125–126).** Claude Code's local Windows results are
recorded in the plan and in its Prompt 125 and 126 handoffs; neither Codex nor the reviewer ran
these project checks. Prompt 125 results are historical; Prompt 126 results are recorded
separately. Both runs executed the offline `HashingEmbedder` locally, in tests and from an
isolated installed wheel. No external provider, network service, Docker or database was
contacted. At that point (before CI), the PostgreSQL tests (`tests/test_indexing_postgres.py`
and all other integration tests), Linux, the wheel step in CI and the container smoke had not
run, and all 251 integration tests, including the 18 indexing cases, were unexecuted against this
M4c version. The new wheel script ran locally on Windows in Prompts 125–126; the corrected
installed-wheel provider-resolution probe ran in Prompt 126. Those gaps were later closed for
`600a366` by the [feature-branch CI evidence](#feature-branch-ci-evidence-at-600a366) below. No
retrieval, semantic-quality, benchmark or production-readiness claim follows.

The external reviewer accepted the complete corrected implementation in Prompt 127 after
inspecting the implementation, corrections and supporting tests, independently matching both
export checksums and reproducing the original provider-resolution bug. Isolated standard-library
probes confirmed the same exception object in six factory/identity control-flow cases,
cancellation and lease-loss precedence over ordinary resolution failure, and a fixed ordinary
factory failure without the original exception chained. These probes do not replace project-suite,
installed-wheel, PostgreSQL or Docker execution; the reviewer ran none of those checks.

## Feature-branch CI evidence at 600a366

M4c was verified in CI on `feat/revision-indexing` at exact commit
`600a366453bd94811ab1d741dc0b28adeb427031`, which adds only prompt history after the
implementation commit `cd5b99c`. It is **not merged**: `main` remains at
`872d0af367be890cce25b2cce0d71a627c993479`. Both workflow records are successful **push** events
on that branch and SHA, attempt 1. These results belong to `600a366`, not to any later
documentation commit or `main` push.

**Attribution.** OpenAI Codex published the branch in Prompt 128 and its handoff reports
retrieving all five job logs through connected GitHub tooling. The external reviewer then
independently retrieved both run records, all five job logs and the job and step summaries; the
counts and log output below come from that independent retrieval. Claude Code did not retrieve
these logs; it recorded this evidence in Prompt 129. Nobody ran the project suite, build, wheel
check, PostgreSQL or Docker locally for this verification; reading CI logs is distinct from
running those checks. Earlier HTTP 403 log-access records belong to their own historical tasks.

[CI run 38942231882](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38942231882):

- [Ubuntu job 117112458418](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38942231882/job/117112458418): `1716 passed, 251 skipped in 30.42s`. Formatting, lint, mypy, distribution build and installed-wheel checks passed. The installed-wheel log reports `offline embedding, canonical storage and indexing modules ran from the installed wheel`.
- [Windows job 117112458897](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38942231882/job/117112458897): `1715 passed, 252 skipped in 29.09s`. Formatting, lint, mypy, distribution build and installed-wheel checks passed, including the same offline embedding/storage execution and indexing imports. The one-test skip difference is the POSIX-only signal test.
- [PostgreSQL integration job 117112458533](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38942231882/job/117112458533): `251 passed, 1716 deselected in 100.13s (0:01:40)`. The log shows `tests/test_indexing_postgres.py ..................`: all 18 indexing cases passed, none skipped or failed.
- [Container job 117112458136](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38942231882/job/117112458136): all six required steps executed and succeeded, none skipped (rendered Compose configuration, effective build context, application image build, image checks, Compose smoke, cleanup). Observed:
  - `compose config: ok`;
  - `context: ok (79 files; 19 planted fixtures excluded)`;
  - image UID and GID 10001;
  - eg-api, eg-worker and eg-admin help checks, installed imports, offline migration SQL and runtime contents checks passed;
  - the stack started with the database healthy, migration complete and API healthy, and migrate, API and worker ran the CI-built image;
  - an API key was created and held in memory only;
  - upload returned 202, the ingestion job succeeded, the revision became active with two verified chunks, and a duplicate upload returned the existing revision with 200;
  - `backfill-indexes enqueued one offline indexing job`;
  - `index ready for the ingested revision; 2 embedding(s), indexing job succeeded`;
  - the idle worker exited 0 without an OOM kill;
  - `smoke: ok` and `cleanup: ok`.

[Secret-scan run 38942231871](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38942231871),
[Gitleaks job 117112458026](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38942231871/job/117112458026): `55 commits scanned`, `no leaks found`.

**What these checks establish.** For the paths exercised at `600a366`:
- the 18 PostgreSQL indexing cases cover atomic and idempotent enqueue, concurrent enqueues,
  tenant scoping and activation eligibility, stalled reporting without change, superseded-revision
  handling, bounded and resumable backfill pages with partial progress, conflict items, production
  worker indexing with atomic readiness and job success, committed-row reuse, a competing writer,
  lease loss and cancellation while the provider blocks, a failure at the finish, a 450-chunk
  revision in bounded pages, ready-index exclusion and a dead canonical job reported as `stalled`;
  the other 233 integration tests also passed against this version;
- the installed-wheel check, on Ubuntu and Windows, executes the offline `HashingEmbedder` and
  canonical storage from the installed wheel, checks the pinned identity and storage properties
  and imports the indexing modules from `site-packages`. It contacts no database and does not by
  itself establish database indexing;
- the container smoke ran the production `eg-admin backfill-indexes` command and the production
  worker indexing path in the CI-built image. Its success gates the matching tenant, revision and
  offline profile, the canonical indexing job's success, index readiness, embedding counts
  matching the chunk counts, and the absence of the API key from service logs. Its indexing
  checks query through a read-only session and print a summary; raw database rows and the
  generated key were not emitted or independently inspected, and the printed summary is not a
  raw-row observation.

They verify nothing beyond those tests and checks; they do not establish general correctness.

**Limits.** The smoke covers idle-worker shutdown only, not an in-flight drain. Activation does
not enqueue indexing automatically, and a stalled index has no recovery path. Provider calls are
not exactly-once, and reused vectors are not compared against fresh provider output. Cancellation
and lease checks run at the accepted explicit boundaries and do not interrupt synchronous calls
already running. Only the offline lexical-hash baseline ran; it makes no semantic-quality claim,
and no live provider was verified. Local Compose remains unverified. M4c is not on `main`;
publication to `main`, M4d–M4f and overall M4 acceptance remain pending. No retrieval, benchmark,
production-readiness or general security claim follows.
