# ADR-0013: Embedding contracts and deterministic offline hashing

- **Status:** Accepted (M4a implementation reviewed in Prompt 110; specification
  accepted in Prompt 108). Verified and on `main` at `5fdaa1c` (fast-forward of
  `feat/embedding-contracts`; see [main CI evidence](#main-ci-evidence-at-5fdaa1c)).
  Earlier feature-branch verification at `d501bd6` is retained as historical.
  Linux/Windows verification, CI builds and existing clean installed-wheel checks
  passed; direct isolated installed-wheel embedding-provider execution remains
  unverified. The M4b specification was accepted at review in Prompt 116, and its
  implementation is pending. M4c–M4f and overall M4 acceptance remain pending.
- **Date:** 2026-10-16
- **Builds on:** the accepted M4a specification in [the plan](../plan.md#m4a-first-implementation-slice-specification-accepted-at-review-prompt-108-implementation-accepted-for-a-local-commit-prompt-110)
  and [ADR-0010](0010-document-ingestion.md). M3 ingestion and activation are unchanged.

## Contracts and boundaries

`evidenceguard_domain.embeddings` defines frozen, closed `EmbeddingIdentity`,
`EmbeddingUsage` and `EmbeddingBatch` dataclasses. This follows the existing
chunk-value pattern. Constructors validate strict types without coercion;
`dataclasses.replace` is the supported copy/revalidation path. Unknown fields
are rejected. Collections are tuples and nested values are frozen contracts.
As with other Python domain values, privileged `object.__setattr__` can bypass
immutability; this is not a sandbox. Provider output is revalidated even when
it already has the expected Python class.

Identity has exactly `provider_id`, `model_id`, `algorithm_version`, `dims` and
`normalization`. Identifiers match `[a-z][a-z0-9._-]{0,63}`; dimensions are strict
integers 1–4096; normalization is `l2`. The fingerprint hashes ASCII JSON with
these five keys, sorted keys, compact separators and no NaN, using SHA-256.
The offline identity is `offline` / `fake-hash-v1` / `ascii-word-sha256-v1` /
1024 / `l2`. Feature, algorithm, dimension or normalization changes require a
new identity/version. This is distinct from upstream API model-version guarantees.

`evidenceguard_retrieval.embeddings` defines `EmbeddingProvider` with a read-only
identity property and `embed(texts, input_type) -> EmbeddingBatch`, plus the
frozen `HashingEmbedder`. `embed_validated` validates the request, captures and
validates the requested identity before calling the provider, then reconstructs
and checks the returned batch against identity, mode and input count. It rejects
malformed nested values, wrong vector shape/types/norm, zero-policy violations
and malformed usage. Raw provider exceptions are replaced by the fixed
`InvalidEmbeddingError` (`invalid_embedding`) outside the exception handler,
without retaining the provider exception as context. Representations omit text,
vector contents, submitted identity strings and usage counts.

## Input and numeric validation

Inputs are tuples of 1–32 strings, each 1–4,000 code points and at most 16,000
strict UTF-8 bytes, nonblank under `str.isspace`, without NUL or lone surrogates.
The aggregate limit is 128,000 UTF-8 bytes. The per-input byte limit is also
implied by 4,000 code points in strict UTF-8; it is checked explicitly. Input
strings pass unchanged: no stripping, Unicode normalization or truncation.
Mode is strictly `query` or `document`. Duplicates retain their positions.

Coordinates are strict int/float values, excluding booleans, in immutable tuples.
They must be finite; nonzero vectors have L2 norm within absolute tolerance 1e-6
of one. `math.hypot` validates the norm without squared-coordinate overflow or
underflow. Extreme integer conversion failures become the same fixed error,
with no raw conversion exception attached. Zero vectors are allowed only for
the offline provider and must be excluded from future cosine candidates. A live
provider zero vector is rejected. Usage is a nonnegative strict integer token
count, or `None` when unknown; hashing always returns `None`, never a fabricated
billable token count.

## Exact hashing algorithm

1. Extract maximal ASCII `[A-Za-z0-9]+` runs and lowercase their ASCII letters.
   Other characters delimit tokens; no stemming or stopword filtering occurs.
2. Emit `u:` plus each token, and `b:` plus each adjacent token pair joined by
   one ASCII space. Count every occurrence, including repetition.
3. SHA-256 each UTF-8 feature. Interpret the first eight digest bytes as an
   unsigned big-endian integer modulo 1024 for the bucket. Digest byte 8 even
   gives +1; odd gives -1. Sum signed integer counts by bucket.
4. Divide coordinates by the square root of the sum of squared counts in bucket
   order; a zero norm gives 1024 zero coordinates. No built-in `hash`, random
   seed, environment read, network, downloaded model or SDK is used.

All offline output is labelled **lexical-hash baseline — not semantic**.
Query/document vectors share the algorithm but retain their requested mode.
Literal fingerprint and bucket/sign fixtures are calculated independently of
the implementation. Tests cover repetition, opposite-sign collisions and
cancellation, Unicode/no-feature zeros, cross-process hash-seed independence,
bounds, strict types, copying, malicious provider outputs and privacy.

## Feature-branch CI evidence at d501bd6

Historical record. M4a is reviewed and verified in CI on `feat/embedding-contracts` at exact commit
`d501bd6de68a965c283a2187665170502af083e2`. At that point it was **not merged**;
`main` was at `85cb0d622a5b49c11439b0b9f67abceaa82edb29`. It later reached
`main` at `5fdaa1c` (below).
Both workflow records are successful **push** events on that feature branch and SHA.
The implementing Codex session and the external reviewer independently retrieved
both records and all five job logs. The reviewer did not execute the project
suite or Docker locally. This records observed logs, not fresh local execution.

[CI run 38789281404](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38789281404):

- [Ubuntu job 116609328373](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38789281404/job/116609328373): `1480 passed, 204 skipped in 25.65s`.
- [Windows job 116609328257](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38789281404/job/116609328257): `1479 passed, 205 skipped in 32.31s`.
- [PostgreSQL job 116609327970](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38789281404/job/116609327970): `204 passed, 1480 deselected in 59.32s`.
- Embedding tests ran successfully in both verify jobs. Linux and Windows
  verification and both distribution builds are complete for this version.
  Both existing clean installed-wheel checks passed: application imports and
  factory creation, API/worker entry-point help, `ingest_revision` registration
  and offline migration SQL rendering. These checks do **not** directly import
  and execute the embedding provider. Direct embedding-provider execution from
  an isolated installed wheel remains unverified.
- [Container job 116609328164](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38789281404/job/116609328164): configuration passed; effective context contained 74 files and excluded all 19 planted fixtures; application image build and image checks passed; stack startup and CI-built service-image identity passed; upload returned 202; ingestion succeeded; the revision became active with two verified chunks; duplicate upload returned 200; idle worker exited 0 with no OOM kill; smoke and cleanup passed. All required configuration, context, build, image, smoke and cleanup steps executed successfully, without being skipped.

[Secret-scan run 38789281505](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38789281505),
[job 116609328947](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38789281505/job/116609328947):
47 commits scanned, no leaks found.

## Main CI evidence at 5fdaa1c

`main` was fast-forwarded to exact commit
`5fdaa1cecbcac876af007e6f4328436ef6faeda2` (parent `d501bd6`, adding only
documentation), which is also the `feat/embedding-contracts` head. Both workflow
records are successful **push** events on `main` for that SHA. The implementing
Codex session and the external reviewer independently retrieved both records and
all five job logs; the reviewer did not execute the project suite or Docker locally.

[CI run 38791558180](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38791558180):

- [Ubuntu job 116617134276](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38791558180/job/116617134276): `1480 passed, 204 skipped in 28.81s`.
- [Windows job 116617133905](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38791558180/job/116617133905): `1479 passed, 205 skipped in 33.37s`.
- [PostgreSQL job 116617134528](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38791558180/job/116617134528): `204 passed, 1480 deselected in 62.80s (0:01:02)`.
- [Container job 116617133613](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38791558180/job/116617133613): configuration, context, build, image checks, smoke and cleanup passed; 74 context files with all 19 planted fixtures excluded; application services used the CI-built image; upload returned 202, ingestion succeeded and the revision became active with two verified chunks; duplicate upload returned 200; the idle worker exited 0 without an OOM kill.
- Distribution builds and the existing installed-wheel checks passed. They still
  do not directly execute the embedding provider from an isolated installed wheel.

[Secret-scan run 38791558235](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38791558235),
[job 116617134227](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38791558235/job/116617134227):
48 commits scanned, no leaks found.

## Verification and limits

Historical Prompt 109 local Windows checks (1479 passed, 205 skipped: 204
PostgreSQL skips and one POSIX-only signal skip; 126 focused embedding/packaging
checks passed) are recorded in the
[plan](../plan.md#m4a-local-verification-prompt-109). The earlier local build
attempt used offline mode with build isolation disabled and failed because the
local environment lacked `hatchling`; no dependency was installed. This remains
historical local evidence, not a current CI build failure. Later CI builds and
existing installed-wheel checks passed for `d501bd6` and again on `main` at
`5fdaa1c`, as recorded above; direct
embedding-provider execution from an isolated installed wheel remains unverified.
Local Compose remains unverified; the container smoke is CI-only evidence.

This slice adds no persistence, migration, pgvector, indexing job, worker
registration, live adapter, corpus evaluation, ranking or review workflow.
It demonstrates deterministic lexical contracts, not semantic quality or an
end-to-end prompt-injection defence. M4b–M4f remain unimplemented. The M4b
persistence specification was
[accepted at review in the plan](../plan.md#m4b-persistence-specification-accepted-at-review-prompt-116-implementation-pending)
in Prompt 116 and gets its own ADR only when implementation is authorized;
M4c–M4f still require their own detailed specification reviews. No benchmark or production-readiness
claim follows.
