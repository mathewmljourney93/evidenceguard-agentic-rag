# ADR-0014: Embedding persistence, full-text representation and index readiness

- **Status:** Accepted (implementation accepted at external review for a local commit in
  Prompt 118). **Reviewed and verified in CI on `feat/embedding-persistence` at `90240e3`**,
  not merged; `main` remains at `5fdaa1c`. Current-version PostgreSQL, Linux, Windows, build
  and container verification completed for that feature-branch commit (see
  [feature-branch CI evidence](#feature-branch-ci-evidence-at-90240e3)). The
  [specification](../plan.md#m4b-persistence-specification-accepted-at-review-prompt-116-implementation-pending)
  was accepted at review in Prompt 116. CI's existing installed-wheel step does not execute
  embeddings directly; embedding-specific installed-wheel execution remains verified only
  locally on Windows (Prompt 117). M4c–M4f and overall M4 acceptance remain pending; local
  Compose remains unverified.
- **Date:** 2026-10-16
- **Builds on:** [ADR-0013](0013-embeddings.md) (M4a contracts), [ADR-0010](0010-document-ingestion.md)
  (chunks), [ADR-0007](0007-durable-job-core.md) and [ADR-0008](0008-worker-runtime.md) (fences).

## Decision

M4b stores tenant-scoped embedding profiles, one index per revision/chunker/profile and one
canonical float32 vector per index and chunk. It adds the generated lexical representation and
the fenced write and readiness operations M4c will call. It registers no handler and adds no
enqueue/backfill caller, provider call, retrieval query or API. M3 activation, chunk text, IDs,
spans, the chunk write path and `require_complete_chunk_set` are unchanged.

| File | Content |
|---|---|
| `evidenceguard_domain/embedding_storage.py` | Pure canonical values: float32 rounding, wire bytes, digests, UUID5 IDs, whole-batch validation, vector manifest |
| `evidenceguard_persistence/models.py` | In-repo `Vector` type (registered for reflection), three tables, two FK-target keys, `chunks.search_vector` and its GIN index |
| `evidenceguard_persistence/migrations/versions/v0005_embeddings.py` | Migration `0005` |
| `evidenceguard_persistence/embeddings.py` | `ensure_profile`, `create_index` (caller's transaction); `write_embeddings`, `mark_index_ready`, `require_complete_index` (fenced) |

No Python dependency, lockfile, workflow, Compose or Dockerfile change.

## Schema

The schema follows the accepted specification. The three new tables mark every column
`NOT NULL` except `embedding_indexes.ready_at` and `vector_manifest_sha256`, because neither
CHECKs nor composite FKs reject NULLs. Composite FKs bind:

- each index to its chunk set (`chunk_count` and `manifest_sha256` included), through the new
  `uq_chunk_sets_binding`;
- each index to its profile (`dims` and `allows_zero_vectors` included);
- each row to its index (revision, chunker version and zero policy included);
- each row to a chunk of that revision and chunker version with the same `content_sha256`,
  through the new `uq_chunks_membership`.

pgvector's `vector(1024)` modifier rejects wrong dimensions and non-finite values. CHECKs over
the `IMMUTABLE` functions `vector_norm`, `vector_send` and `sha256` bind `is_zero`, the unit
norm (absolute 1e-6), the zero policy and the stored-byte digest. Readiness pairing is CHECKed.
Immutability of rows and of ready indexes, the `building` → `ready` transition, the fingerprint's
derivation and index creation only for ever-activated revisions are trusted application
invariants, without triggers.

## Numeric storage

Provider vectors are first validated by M4a. Then each coordinate is rounded to float32 with
`struct.pack('>f', x)`, `-0.0` becomes `0.0`, and the rounded vector is validated against the
storage contract with the **same** absolute 1e-6 tolerance, with no renormalization. Provider
validity does not imply storage validity. The reviewer's example (norm `0.999999001`, float32
`0.9999989867210388`) is rejected with the fixed `invalid_embedding` error. A whole write batch
is canonicalized and revalidated before any SQL, so one bad vector writes nothing.

Equality, replay and digests use canonical stored float32 values, never provider float64
values. Values are written as a text literal (`repr` of each float32-exact double, which
`strtof` parses back exactly) in `CAST(… AS VECTOR(1024))`, and read as `vector_send` bytes.
`vector_sha256` is the SHA-256 of `struct.pack('>HH1024f', 1024, 0, *coordinates)`, pgvector's
binary send format, and the database recomputes it in a CHECK. Zero vectors are stored only
under offline profiles, with `is_zero = true`; future cosine queries must filter `NOT is_zero`.

## Fencing, completeness and the M4c boundary

`write_embeddings` and `mark_index_ready` take M3a's `FencedSession` and `JobSnapshot`. Each:

1. requires kind `index_revision` and a payload of exactly `index_id`;
2. locks that index row `FOR UPDATE`, looked up only within the job's tenant (lock order
   job → index; no document, revision or chunk lock);
3. calls `recheck_ownership` after the last lock or unique-index wait on every successful
   path, including the already-ready no-op.

Writes insert with `ON CONFLICT DO NOTHING`, compare the immutable fields of replayed rows,
never overwrite, and refuse ready indexes.

`require_complete_index` checks four things:

- the profile's stored identity and its deterministic ID;
- the bound chunk set and its rebuilt manifest, using M3d's public `chunk_set_statement`,
  `manifest_rows_statement`, `MANIFEST_COLUMNS` and the domain manifest helpers (it does not
  call the activation callback or build a `RevisionSnapshot`);
- exact chunk membership with matching text digests, and the row count;
- the vector manifest built from CHECK-bound digests, so coordinates are never transferred.

M4c will call `mark_index_ready` inside `ctx.fenced(finish=True)`, so readiness and job success
commit or roll back together. The PostgreSQL tests exercise this through the real fence.

## Migration and extension lifecycle

`0005` runs `CREATE EXTENSION IF NOT EXISTS vector`, adds the two FK-target keys, the stored
generated `to_tsvector('simple'::regconfig, text)` column and its GIN index (rewriting `chunks`),
then the three tables. Downgrade removes exactly these objects in reverse dependency order and
**always leaves `vector` installed**; removing it is an administrative operation outside
Alembic. There is no `CASCADE`, extension-drop logic, ownership marker, trigger, HNSW or
IVFFlat. Offline `--sql` rendering needs no database. Creating the untrusted extension needs a
superuser; the CI and Compose databases use the image's bootstrap superuser. The
`empty_database` fixture asserts that its `DROP SCHEMA public CASCADE` reset leaves only
`plpgsql`; the disposable-database guard is unchanged. The passing PostgreSQL CI run at
`90240e3` (233 passed, none failed or skipped) is consistent with both in the CI database:
extension creation succeeded and no reset assertion failed. That is CI-image evidence, not a
statement about other deployments, and local Compose remains unverified.

## Implementation choices within the specification

These are recorded for review, not silent redesigns:

1. **UUID namespaces.** The specification named them without values. They follow the chunk-ID
   convention: `uuid5(NAMESPACE_URL, "https://evidenceguard.invalid/namespaces/embedding-{profile,index}-id/v1")`,
   giving `b6e99a93-0055-5a05-970d-26eb33f56723` and `5adfc50a-fb67-5caa-a6ca-81c69eaf4285`.
2. **Constraint names.** New keys and FKs have explicit names because convention-generated names
   would exceed PostgreSQL's 63-character limit.
3. **`search_vector` nullability.** It is a nullable generated column. The NOT NULL rule covered
   the three new tables; it is generated from `NOT NULL` text, so it is never NULL in practice.
4. **Migration DDL type.** The migration defines a local `VECTOR(1024)` DDL type instead of
   importing the model type, so the revision stays fixed.
5. **Reflection.** `Vector` is registered with `ischema_names.setdefault("vector", Vector)` at
   models import: a process-wide registration in SQLAlchemy's PostgreSQL dialect.
6. **Additional fixed errors.** `EmbeddingStorageRejectedError` replaces any driver
   `IntegrityError` from the insert, because PostgreSQL's error detail can contain row values; it
   is raised outside the handler. Steps the specification described as "a fixed error" use
   `EmbeddingProfileMismatchError`, `EmbeddingSourceMismatchError`,
   `IndexSourceNotEligibleError` and `IndexConflictError`.
7. **Already-ready no-op.** It also requires the profile fingerprint, as the specification states,
   before its ownership re-check.
8. **Tolerance edges.** A single provider coordinate that passes M4a cannot round above
   `1 + 1e-6`, so the upper edge is tested on canonical values directly (`1.0000009536743164`
   accepted, `1.000001072883606` rejected). Application `math.hypot` and database `vector_norm`
   may differ by about 1e-16; within that distance of the tolerance edge the CHECK is the
   backstop, and the insert fails with the fixed error rather than storing.

## Verification

Claude Code ran these locally on Windows (Python 3.12, locked environment, `--offline --no-sync`)
in Prompt 117:

- Ruff format and lint, strict mypy (113 source files): clean.
- `pytest tests/test_embedding_storage.py tests/test_embedding_store.py`: 102 passed. These are
  independent float32/wire/digest/UUID fixtures and fake-session protocol tests, **not**
  database evidence.
- Full suite: 1585 passed, 234 skipped. That is 233 integration tests without
  `EG_TEST_DATABASE_URL` (204 existing plus 29 new) and one POSIX-only signal test.
- `pytest -m integration --collect-only`: 233 collected; `tests/test_embeddings_postgres.py`
  collects 29.
- `uv build` (declared hatchling backend): sdist and wheel built under `.local/`.
- Clean installed-wheel checks in an isolated venv outside the checkout, with dependencies
  installed from the exported `uv.lock` and the wheel with `--no-deps`. The existing CI checks
  passed. New check: `evidenceguard_domain.embedding_storage`,
  `evidenceguard_persistence.embeddings` and `evidenceguard_retrieval.embeddings` resolved to
  `site-packages`; `HashingEmbedder` ran through `embed_validated` with pinned
  fingerprint, digest and ID literals and the lower-boundary rejection; offline SQL rendered for
  upgrade to `0005` and downgrade `0005:0004` without `EXTENSION` or `CASCADE`.

That last check **closes, locally on Windows only**, the earlier limitation that embedding-provider
execution from an isolated installed wheel was unverified. The CI workflow's installed-wheel step
is unchanged and still does not run it. Adding that step to CI is a possible follow-up for review.

**Review (Prompt 118).** The external reviewer inspected the complete Prompt 117 diff,
independently matched its SHA-256 and inspected the existing M3 chunk-store and job-fence
source. The reviewer's independent standard-library probes passed for wire encoding and
digests, both float32 norm boundaries, the accepted lower-boundary rejection, invalid numeric
inputs and 200 seeded vector round trips. The reviewer ran no project suite, installed-wheel
check, PostgreSQL or Docker; acceptance also rests on the Prompt 117 verification reported by
Claude Code above.

**Historical, at Prompt 117 and 118 (before CI):** PostgreSQL tests (no Docker or database
contact was authorized), Linux, the container smoke and CI had not run at that point. They
have since run in CI at `90240e3`, recorded below.

## Feature-branch CI evidence at 90240e3

M4b is reviewed and verified in CI on `feat/embedding-persistence` at exact commit
`90240e3969e93e32cabd11a49664ca27a8553593`, which adds only prompt history after the
implementation commit `691a44c`. It is **not merged**; `main` remains at
`5fdaa1cecbcac876af007e6f4328436ef6faeda2`. Both workflow records are successful **push**
events on that branch and SHA. These results belong to `90240e3`, not to any later
documentation commit or `main` push.

**Attribution.** The external reviewer independently retrieved both workflow records, the
job and step records, and all five job logs; the counts and log output below come from that
retrieval. The reviewer did not run the suite or Docker locally. Claude Code's anonymous API
session in Prompt 119 separately observed the same runs, jobs and steps with all conclusions
`success`. It could not download logs (HTTP 403), so it observed no counts or log output.

[CI run 38856680385](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38856680385):

- [Ubuntu job 116829602477](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38856680385/job/116829602477): `1586 passed, 233 skipped in 28.62s`. Formatting, lint, type checking, tests, distribution build and the existing installed-wheel checks passed.
- [Windows job 116829602600](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38856680385/job/116829602600): `1585 passed, 234 skipped in 37.31s`. Formatting, lint, type checking, tests, distribution build and the existing installed-wheel checks passed.
- [PostgreSQL 17 + pgvector job 116829602553](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38856680385/job/116829602553): `233 passed, 1586 deselected in 96.48s (0:01:36)`. The log shows all 29 collected cases in `tests/test_embeddings_postgres.py` passing, and the integration run had no failed or skipped tests.
- [Container job 116829602560](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38856680385/job/116829602560): all six required steps executed and succeeded (rendered Compose configuration, effective build context, application image build, image checks, Compose smoke, cleanup). Observed:
  - `compose config: ok`;
  - `context: ok (77 files; 19 planted fixtures excluded)`;
  - image UID and GID 10001;
  - eg-api, eg-worker and eg-admin help checks, installed imports, offline migration SQL and runtime contents checks passed;
  - the stack started with the database healthy, migration complete and API healthy, and migrate, API and worker used the CI-built image;
  - an API key was created and held in memory only;
  - upload returned 202, the ingestion job succeeded, the revision became active with two verified chunks, and a duplicate upload returned the existing revision with 200;
  - the idle worker exited 0 without an OOM kill;
  - `smoke: ok` and `cleanup: ok`.

[Secret-scan run 38856680352](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38856680352),
[Gitleaks job 116829602242](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38856680352/job/116829602242): `51 commits scanned`, `no leaks found`.

**What the PostgreSQL run verifies.** It verifies the M4b paths those 29 tests and the
updated existing tests cover:
- constraints and required-column rejection;
- stored float32 bytes, digests and numeric checks;
- migration round trips, and vector reflection through the existing migration-drift check;
- the fixture reset;
- extension retention and unrelated-object survival;
- fenced writes, replay, readiness and atomic job completion;
- the tested concurrency, lease-loss and lock-timeout cases.

It verifies nothing beyond those tests.

**Limits.** The container smoke still covers ingestion and idle-worker shutdown only. It runs no
embedding indexing, because no indexing handler exists, and proves no in-flight shutdown bound.
CI's installed-wheel checks passed but do not execute the embedding provider directly;
embedding-specific installed-wheel execution remains verified only locally on Windows
(Prompt 117). Local Compose remains unverified. No retrieval, semantic-quality, benchmark,
production-readiness or general security claim follows.
