# ADR-0010: Document ingestion: deterministic chunking and the first production handler

- **Status:** Accepted (M3d). Reviewed (Prompts 82–83) and verified in CI on branch `feat/document-ingestion` at `74904e6`; see *Consequences and limits*. Not merged into `main`, which remains the M3c baseline at `6f8ffde`.
  - The specification was accepted at review in Prompt 79 (proposed in Prompt 76, corrected in Prompts 77–79).
- **Date:** 2026-10-15
- **Builds on:**
  - [ADR-0007](0007-durable-job-core.md): the fence, its 5 s `lock_timeout`, database time and `recheck_ownership`, all unchanged;
  - [ADR-0008](0008-worker-runtime.md): `ctx.fenced(finish=True)`, cancellation, uncertain commits and `PermanentJobError`, all unchanged;
  - [ADR-0009](0009-document-revisions.md): the revision lifecycle and lock order, with two additive interface changes (below);
  - the M3d specification in [docs/plan.md](../plan.md), accepted at review.

## Context

M3c stores a revision's exact content but nothing reads it. M3d turns a `pending` revision into a verified, immutable set of chunks with exact source provenance, then activates it. It carries the M3 criteria "chunk IDs include tenant and revision" and "a stale worker cannot write chunks". Embeddings, retrieval, model calls, endpoints, Docker and the M3e projection are out of scope.

## Decisions

### Modules

- `evidenceguard_domain.chunks`: the shared contract. The `Chunk` value (frozen; `repr` never shows text or section path), deterministic chunk IDs, the canonical manifest encoding, `ExpectedChunkSet` and batch bounds. It lives in the domain because the parser and the store both need it, and neither may import the other.
- `evidenceguard_retrieval.chunking` (new package `packages/retrieval/evidenceguard_retrieval`): the pure chunker `text-md-v1`. It imports only the domain, which the import-boundary test enforces.
- `evidenceguard_persistence.chunks`: source loading, fenced chunk writes and the completeness check.
- `evidenceguard_worker.ingest`: the `ingest_revision` handler, registered by `production_registry()`.

### Chunker `text-md-v1`

The rules are those of the accepted specification (section A of the M3d plan), unchanged:

- lines end at LF; a CR immediately before LF belongs to the terminator; offsets are code-point indices; a leading BOM keeps offset 0 but is in no span;
- the whitespace predicate is space and tab only;
- Markdown classification by priority (fence opening, ATX heading, table start, paragraph line), with paragraphs stopping before the others;
- heading runs; greedy packing to 2,500 code points within a section;
- tables never packed with prose, split by rows with a repeated header of at most 1,000 code points, never exceeding 4,000;
- oversized blocks and lines split as specified;
- at most 4,096 chunks.

Every chunk's text is an exact source slice, or, for a table continuation, the header slice followed by the body slice, with the header recorded in its own span. Only a leading BOM, LF and CRLF terminators and permitted spaces and tabs are ever omitted. All nine normative examples are tests.

Implementation details resolved within the specification:

- An unclosed fence runs to the last non-blank line, so a block never ends with a blank line, consistent with "a run never starts or ends with a blank line".
- `segment()` accepts a lowered `target_chars` only for the specification's illustrations (examples 4 and 8); `chunk_revision()` always uses `TARGET_CHARS`.

### Schema (migration `0004`)

- `chunk_sets`:
  - PK `(tenant_id, revision_id)` (`pk_chunk_sets`), with no `id` column;
  - unique `(tenant_id, revision_id, chunker_version)`;
  - FK `(tenant_id, revision_id)` to the revision;
  - checks on the version pattern, the count (1–4,096) and the manifest digest.
- `chunks`:
  - the deterministic `id` as PK, and unique `(tenant_id, id)`;
  - unique `(tenant_id, revision_id, chunker_version, ordinal)`;
  - composite FK `(tenant_id, revision_id, chunker_version)` to `chunk_sets`;
  - checks on the ordinal, text length (1–4,000), digest, section-path depth (at most 6), line and character spans, and the header fields (all-or-none, tables only, before the body).

The migration spells its constraint text literally; an offline test compares it with the model constants. Downgrade drops `chunks`, then `chunk_sets`. There are no triggers, no extensions and no changes to existing tables.

### IDs and manifest

- `id = uuid5(973dffe5-e145-5fd2-833e-6793460ee3be, "{tenant}:{revision}:{chunker_version}:{ordinal}")`, so identical bytes in two tenants get disjoint IDs.
- The manifest is a JSON array in ordinal order of objects with exactly thirteen keys. It is encoded with `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)` as ASCII bytes and hashed with SHA-256.

### Writes and locking

- `lock_revision_for_job` is M3c's former private `_lock`, made public with its code unchanged. It locks job (by the fence) → document → revisions in ascending ID order, then re-checks ownership with a fresh `clock_timestamp()` and the tenant.
- `write_chunk_set` and `write_chunks` each run in one fenced transaction:
  1. lock, then require `processing`, otherwise the fixed `ChunkWriteRefusedError` before any insert;
  2. `INSERT … ON CONFLICT DO NOTHING RETURNING` the key;
  3. for every expected row not returned, look it up by its natural key and compare every immutable field. A missing row or any difference is the fixed `ChunkConflictError`. Nothing is overwritten, and `created_at` is never compared;
  4. re-check ownership before the block commits.
- Batches are at most 200 chunks and 512,000 code points.
- Because activation, failure and chunk writes all take the same document lock first, whichever holds it first finishes before the other proceeds, and nothing is inserted after settlement.

### Completeness and activation

M3c's `activate_revision` gains an optional keyword-only `before_settle(session, revision)`. It is called under the locks, only for a `processing` target, before `settle`. The handler binds it to the current attempt with `functools.partial(require_complete_chunk_set, expected=ExpectedChunkSet.of(chunks))`. The check requires:

- the set row with the expected version and count;
- stored ordinals exactly `0 … count-1`;
- the manifest rebuilt from the stored fields equal to the stored digest;
- that digest equal to the attempt's expected digest.

Activation and the job's success commit together in `ctx.fenced(finish=True)`.

### Handler

1. Status read; `start_processing` and source load when `pending` or `processing`.
2. `failed`: raise `PermanentJobError` without parsing (this closes the crash gap).
3. `active` or `superseded`: a duplicate activation that succeeds the job.
4. Parse outside every transaction and lock, between `ctx.check()` calls.
5. Write the set row, then the batches, with a check before each.
6. The bound finish.

Error handling:

- **Refusals:** `ChunkWriteRefusedError` or `InvalidRevisionTransitionError` trigger one fresh status read, then the failed or settled branch. The handler never fails an already-settled revision.
- **Permanent failures:** `empty_document`, `chunk_limit_exceeded`, `content_integrity_failed`, `chunk_conflict`, and `ingestion_failed` for a parser bug. Each commits `fail_revision` in a non-raising block, then raises `PermanentJobError(PERMANENT_FAILURE)` outside it.
- **Retryable:** `ChunkSetIncompleteError` and `JobLockTimeoutError` raise `RetryableJobError`.
- **Missing revision:** an invalid payload or a revision missing from the tenant raises `PermanentJobError` without touching any revision.
- **Unchanged:** lease loss, cancellation and uncertain commits propagate untouched.

## Consequences and limits

- **Verification:** locally on Windows without a database (Prompt 81: 1019 passed, 179 skipped): format, lint, strict type-check, the database-independent suite, build, installed-wheel and offline-migration checks, and the staged secret scan. It was verified in CI on `feat/document-ingestion` at `74904e6` ([CI run 38699149482](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38699149482)). From logs retrieved by the external reviewer: [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38699149482/job/116302837532) `1020 passed, 178 skipped in 20.13s`, [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38699149482/job/116302837727) `1019 passed, 179 skipped in 23.75s`, and the [PostgreSQL integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38699149482/job/116302837038) `178 passed, 1020 deselected in 51.89s`: the full suite, including M3d's 45 new tests. The [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38699149417) passed ([job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38699149417/job/116302836923): 33 commits scanned, no leaks found). The PostgreSQL suite includes the 45 new tests: constraints, migration round trips, idempotent and conflicting writes, races with activation and failure, refusal after settlement, lease expiry during lock waits, completeness, the atomic finish, the crash gap and the registered production handler. M3d is not merged into `main`, which remains the M3c baseline at `6f8ffde`. These results demonstrate the tested behaviour, not a performance benchmark or a general security guarantee.
- **Digest trust:** the final check trusts stored `content_sha256` values because rows are compared field by field, text included, when written, and no code path updates them. It adds no protection against privileged direct database modification. Immutability is an application invariant; there are no triggers.
- **Exhausted jobs:** a `dead` job can still leave a revision `pending` or `processing`. The derived `stalled` projection is assigned to M3e and remains required before overall M3 acceptance.
- **Re-ingestion:** a `stalled` revision cannot be retried in v1, because identical bytes return the same revision and job. Re-chunking active revisions is out of scope.
- **Limits are defaults:** they are accepted as initial engineering defaults, not measured performance results. No performance has been measured.
- **Unvalidated in production:** the parser is a deliberately small grammar, not a Markdown renderer. Document text remains untrusted input for later slices.
