# EvidenceGuard: Auditable Multi-Agent RAG for Vendor Risk Review

EvidenceGuard is a planned vendor-risk review copilot. It is intended to:

- ingest synthetic vendor documents for one tenant at a time;
- retrieve only evidence that tenant is authorized to see, with provenance;
- identify supported answers, contradictions and missing information;
- draft a report in which every claim cites its evidence;
- require a human to approve the exact draft revision before it can be finalized or exported.

It is evidence-based decision support, not legal advice or compliance certification.

## Status: M1, M2 and M3 accepted (persistence, authentication, tenant-scoped vendors and readiness; durable jobs, the worker, documents and revisions, ingestion, the document API and the development container stack, all on `main`, M3 implementation at `e2463cb`, final acceptance publication at `85cb0d6`); M4 sequence and M4a specification accepted at external review (Prompt 108); M4a verified and on `main` at `5fdaa1c`; M4b persistence specification accepted at external review (Prompt 116); M4b implementation reviewed, verified in CI and on `main` at `872d0af`; M4c specification accepted (Prompt 124); M4c implementation accepted at external review for a local commit (Prompt 127) on `feat/revision-indexing`, CI verification pending (pre-alpha)

**Final M3 publication:** accepted documentation is on `main` at `85cb0d622a5b49c11439b0b9f67abceaa82edb29`. The external reviewer independently retrieved both successful main push workflow records and all five job logs: [CI](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38776947803) and [secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38776947848). See the [final M3 publication baseline](docs/plan.md#final-m3-publication-baseline-prompt-107) for counts, container observations and attribution. The reviewer did not run the suite or Docker locally; Claude had observed conclusions without anonymous log access. Earlier `e2463cb` evidence remains separate. The four accepted M3 evidence limitations and unverified local Compose status remain.

**M4 planning:** the [M4 sequence and M4a specification](docs/plan.md#m4-direction-and-review-decisions) were accepted at external review (Prompt 108). M4a embedding contracts and deterministic offline hashing are verified and on `main` at `5fdaa1c`: both main push workflows passed ([main CI evidence](docs/decisions/0013-embeddings.md#main-ci-evidence-at-5fdaa1c)); earlier verification on `feat/embedding-contracts` at `d501bd6` is historical ([feature-branch CI evidence](docs/decisions/0013-embeddings.md#feature-branch-ci-evidence-at-d501bd6), [historical local verification](docs/plan.md#m4a-local-verification-prompt-109)). Linux/Windows verification, both CI builds and existing clean installed-wheel checks passed. The [M4b persistence specification](docs/plan.md#m4b-persistence-specification-accepted-at-review-prompt-116-implementation-pending) (embedding profiles, index records, pgvector storage, full-text representation and readiness) was accepted at external review in Prompt 116. Claude Code implemented it in Prompt 117 ([ADR-0014](docs/decisions/0014-embedding-persistence.md)): migration `0005` with pgvector, three tenant-scoped tables, a generated `simple` full-text column, canonical float32 storage and fenced writes/readiness. The implementation was accepted at external review in Prompt 118 and is **reviewed, verified in CI and on `main` at `872d0af`**. From main-push job logs retrieved by the external reviewer ([main CI evidence](docs/decisions/0014-embedding-persistence.md#main-ci-evidence-at-872d0af)): Ubuntu `1586 passed, 233 skipped`, Windows `1585 passed, 234 skipped`, PostgreSQL `233 passed, 1586 deselected` with all 29 M4b cases passing, the container job with all six required steps, and Gitleaks (52 commits, no leaks). This covers the tested M4b paths only. Earlier feature-branch verification at `90240e3` is historical ([feature-branch evidence](docs/decisions/0014-embedding-persistence.md#feature-branch-ci-evidence-at-90240e3)). The [M4c indexing specification](docs/plan.md#m4c-indexing-specification-accepted-at-review-prompt-124-implementation-pending) (enqueue/backfill, `eg-admin backfill-indexes` with exit codes 0/3/1/2, the `index_revision` handler and atomic readiness) was accepted at external review in Prompt 124 (proposed in Prompt 122, corrected in Prompt 123). Claude Code implemented it in Prompt 125 ([ADR-0015](docs/decisions/0015-revision-indexing.md)): tenant-scoped enqueue and bounded backfill, `eg-admin backfill-indexes`, the registered offline `index_revision` handler with committed-row reuse and atomic readiness, plus the required CI wheel and container indexing checks. Review found that provider-resolution control flow (cancellation, lease loss, fence closure) was converted to a permanent failure; Prompt 126 corrected that, and the complete implementation with those corrections is **accepted at external review in Prompt 127 for a local commit, pending current-version CI verification**. This task authorizes and completes no publication or merge. Claude Code reported local Windows checks passing (Prompt 126 full suite: 1715 passed, 252 skipped, being 251 integration tests without a database and one POSIX-only signal test; Prompt 125: 1703 passed, 250 skipped), and the new wheel script ran locally on Windows in Prompts 125–126, including the corrected installed-wheel provider-resolution probe in Prompt 126. Codex and the reviewer did not run these project checks. All 251 integration tests remain unexecuted against this M4c version, including the 18 indexing cases. Only the offline `HashingEmbedder` ran; no external provider was contacted. Its PostgreSQL tests, the wheel step in CI and the container indexing smoke have not run, so PostgreSQL, Linux and container verification is pending CI. M4d–M4f still require their own detailed reviews. Claude Code's historical Prompt 117 local Windows results (102 focused tests; full suite 1585 passed, 234 skipped) were pre-CI. M4d–M4f remain unimplemented and require their own detailed specification reviews. For both M4a commits, Codex and the reviewer independently retrieved the logs; the reviewer did not run the suite or Docker locally. The offline provider is labelled “lexical-hash baseline — not semantic”; it provides no semantic-quality evidence. The earlier missing-hatchling build failure was local and historical. The existing wheel coverage on `main` at `872d0af` predates the M4c extension: it covers application imports/factory, entry points, ingestion registration and offline migrations. The new embedding/indexing wheel step has run locally on Windows in Prompts 125–126, but has not run on CI runners; Prompt 117's embedding-provider wheel results remain historical. Overall M4 acceptance is pending; local Compose remains unverified. Retrieval, live adapters, review orchestration, completed risk reports and evaluation results remain unimplemented.

**What works now:**
- One installable Python 3.12 package (`evidenceguard`), managed with uv, with a committed lockfile (M1a).
- A minimal FastAPI app with one endpoint: `GET /healthz` returns `{"status": "ok"}`. This is a **process-liveness** check only. It does not check databases or any other dependency, and it does not mean the product works (M1a).
- An `eg-api` command that serves the app with Uvicorn, plus FastAPI's generated OpenAPI docs at `/docs` and `/openapi.json` (M1a).
- **Typed evidence contracts** in `evidenceguard_domain` (M1b):
  - actor context, evidence questions, citations, verification results, findings and report content;
  - the permitted verdict/status combinations;
  - citation rules for each status;
  - tenant consistency across everything a report contains;
  - every report question either answered by a finding or listed as unresolved; any question named by a missing-evidence finding is always listed as unresolved.
- **Pure report-approval transitions** (M1b):
  - draft, approve, reject, revise, finalize and export eligibility;
  - approval is bound to the exact revision and its SHA-256 content hash;
  - any revision removes the effective approval;
  - rejections must state a reason;
  - identical retries are idempotent, and changed retries are refused as conflicts;
  - only finalized reports can be exported.
- **API request handling** (M1c):
  - every response carries an `X-Request-ID` (a valid incoming UUID is reused, otherwise a new one is generated);
  - errors are `application/problem+json` (RFC 9457) with the same request ID;
  - `eg-api` writes one JSON log line per request with the route template, status and duration;
  - log lines carry only fixed, reviewed event names and allowlisted fields. Message text, raw paths, query strings, bodies and exception messages are not written by this logging configuration;
  - error responses never echo submitted values or exception text. Specific error messages come only from a reviewed catalogue.

  See [ADR-0002](docs/decisions/0002-request-ids-logging-and-errors.md), including what these guarantees do not cover.
- **PostgreSQL persistence foundation** (M2a, on `main`): settings, engine and session lifecycle, the tenants/users/API keys/vendors schema with composite tenant constraints, Alembic migration `0001`, and a guarded PostgreSQL integration-test job. See [ADR-0004](docs/decisions/0004-persistence-foundation.md) and [Database](#database-m2a).
- **API-key authentication** (M2b, on `main`):
  - `GET /v1/me` returns the tenant, user and role behind an `Authorization: Bearer` API key;
  - the `admin` role exists, with no report or approval rights;
  - an `eg-admin` command seeds a synthetic demo fixture and creates and revokes keys.

  At commit `b2f7f23`, all 15 PostgreSQL integration tests passed in CI, M2a's and M2b's ([job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38166627885/job/114550418432)). See [ADR-0005](docs/decisions/0005-api-key-authentication.md) and [Authentication](#authentication-and-eg-admin-m2b).
- **Tenant-scoped vendors and readiness** (M2c, on `main`):
  - `POST /v1/vendors`, `GET /v1/vendors` (bounded pages) and `GET /v1/vendors/{id}`, always scoped to the API key's tenant;
  - `GET /readyz`, which checks database connectivity and migration revisions;
  - one shared, lazily started database resource for the whole API.

  At commit `a888b6c`, all 21 PostgreSQL integration tests passed in CI, including the six added in M2c ([job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38212619855/job/114689994147)), and again on `main` at `9d5a93a`. See [ADR-0006](docs/decisions/0006-vendor-api-and-readiness.md) and [Vendors and readiness](#vendors-and-readiness-m2c).
- **Durable job core** (M3a, on `main`):
  - a `jobs` table (migration `0002`) and pure lifecycle rules;
  - idempotent enqueue, claim with `SKIP LOCKED`, reclaim of expired leases, heartbeat, completion and failure;
  - a fenced transaction that checks the `(job, worker, attempt)` token and the lease with fresh database time before any effect.

  The M3b worker below runs it; at the M3a and M3b baselines there was no production handler, and there is still no job endpoint. At commit `11350e1`, all 63 PostgreSQL integration tests passed in CI ([job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38240768344/job/114782517485)), including the job concurrency, lease-fencing and lock-timeout tests, and again on `main` at `b3f9845` ([job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38242144844/job/114787118281)). These results demonstrate the tested behaviour, not a general security or performance guarantee. See [ADR-0007](docs/decisions/0007-durable-job-core.md).
- **Worker runtime** (M3b, on `main`):
  - an `eg-worker` command that claims jobs of its registered kinds, runs one handler at a time, renews leases with heartbeats and records outcomes only through the M3a fence;
  - atomic completion with a handler's final effects, and cooperative cancellation checked at explicit points;
  - a graceful shutdown with bounded supervisor waits that ends the process with exit code 5 if a job thread does not stop. This is not a total shutdown deadline: a blocked database call can delay it (see ADR-0008).

  At the M3b baseline (and on the M3c `main` baseline `6f8ffde`) there were **no production handlers**, so `eg-worker` exited with code 4 before reading any settings; M3d, on `main` since `cdf7260`, registers `ingest_revision` (below). At commit `bc5f638`, [CI run 38253962690](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38253962690) passed on [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38253962690/job/114827089007) (`709 passed, 77 skipped in 15.96s`) and [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38253962690/job/114827088937) (`708 passed, 78 skipped in 22.18s`), and the [PostgreSQL integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38253962690/job/114827089078) passed all 77 integration tests, M3a's 63 and the worker's 14 (`77 passed, 709 deselected in 19.63s`), all from logs retrieved by the external reviewer. The [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38253962775) passed (25 commits scanned, no leaks found). It was then fast-forwarded onto `main` at `dd26c70`, where all four checks passed again (see *Verified baseline*). These results demonstrate the tested behaviour, not a general security or performance guarantee. See [ADR-0008](docs/decisions/0008-worker-runtime.md).
- **Documents and revisions** (M3c, on `main`):
  - `documents` and `document_revisions` tables (migration `0003`) with composite tenant references, same-document active and successor pointers, paired status/field checks, at most one active revision per document, and no triggers;
  - exact-byte revision content: strict UTF-8, no NUL, hash and size from the uploaded bytes, no normalization;
  - tenant-scoped revision creation in the caller's transaction, with numbers allocated under a document lock and identical bytes returning the existing revision;
  - fenced processing, failure and activation that lock job → document → revisions, re-check ownership with fresh database time, and keep the previous active revision when a replacement fails or finishes late.

  On the M3c `main` baseline `6f8ffde` there was **no production ingestion handler**; M3d, on `main` since `cdf7260`, adds `ingest_revision` (below). At that baseline there was no document endpoint or upload. At commit `8646b75` on `feat/document-revisions` (the reviewed implementation `057d57d` plus a prompt-history commit), [CI run 38284929219](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38284929219) passed on [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38284929219/job/114930898138) (`819 passed, 133 skipped in 18.75s`) and [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38284929219/job/114930898065) (`818 passed, 134 skipped in 23.07s`), and the [PostgreSQL integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38284929219/job/114930897691) passed all 133 integration tests: the 77 existing ones and the 56 added by M3c (`133 passed, 819 deselected in 36.46s`). The [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38284929225) passed (29 commits scanned, no leaks found). It was then fast-forwarded onto `main` at `6f8ffde`, where all four checks passed again (see *Verified baseline*). All counts are from logs retrieved by the external reviewer. The PostgreSQL tests include M3c's constraint, migration, concurrency, activation and lease tests. The documented limits are unchanged: the ownership re-check is not atomic with the commit, a lost commit acknowledgment leaves the outcome uncertain, revision failure and job failure are separate commits, and dead-job reconciliation or a projection is still required in M3d/M3e. These results demonstrate the tested behaviour, not a general security or performance guarantee. See [ADR-0009](docs/decisions/0009-document-revisions.md).
- **Document ingestion** (M3d, **reviewed, verified in CI and on `main` at `cdf7260`**):
  - a deterministic chunker `text-md-v1` for `text/plain` and `text/markdown` (`evidenceguard_retrieval.chunking`), with exact source spans, repeated table headers kept as a separate span, and only a BOM, line terminators and permitted spaces and tabs ever omitted;
  - `chunk_sets` and `chunks` tables (migration `0004`) with composite tenant references and deterministic, tenant-scoped chunk IDs;
  - fenced, idempotent chunk writes that compare existing rows field by field, are refused once a revision has settled, and serialise with activation and failure on the document lock;
  - the first production handler, `ingest_revision`, which activates a revision only after verifying its complete chunk set against the current attempt's manifest, in the same transaction as the job's success.

  It was verified in CI on `feat/document-ingestion` at `74904e6` ([CI run 38699149482](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38699149482)). From logs retrieved by the external reviewer: [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38699149482/job/116302837532) `1020 passed, 178 skipped in 20.13s`, [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38699149482/job/116302837727) `1019 passed, 179 skipped in 23.75s`, and the [PostgreSQL integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38699149482/job/116302837038) `178 passed, 1020 deselected in 51.89s`: the full suite, including M3d's 45 new tests. The [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38699149417) passed ([job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38699149417/job/116302836923): 33 commits scanned, no leaks found). M3d was then fast-forwarded onto `main` at `cdf7260` (`cdf7260d02b8af9affb369cc805d666be61f9ac0`, adding only documentation after `74904e6`), where [CI run 38701376504](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38701376504) passed again. From logs retrieved by the external reviewer: [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38701376504/job/116310119787) `1020 passed, 178 skipped in 19.71s`, [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38701376504/job/116310119664) `1019 passed, 179 skipped in 16.16s`, and the [PostgreSQL integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38701376504/job/116310119317) `178 passed, 1020 deselected in 53.28s`. The [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38701376501) passed ([job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38701376501/job/116310119403): 34 commits scanned, no leaks found). Both runs were push-triggered on `main`; the reviewer did not run the suite locally. These results demonstrate the tested behaviour, not a performance benchmark or a general security guarantee. See [ADR-0010](docs/decisions/0010-document-ingestion.md). At that baseline no embeddings, retrieval, model calls, upload or document endpoints existed; offline embedding contracts/provider (M4a) are now verified and on `main` at `5fdaa1c`; retrieval and model calls remain unimplemented.
- **Document API** (M3e, **reviewed, verified in CI and on `main` at `2e605e7`**):
  - `POST /v1/vendors/{vendor_id}/documents`: a bounded multipart upload (2 MiB of file content; `text/plain` or `text/markdown`, strict UTF-8) parsed with `python-multipart` 0.0.32's streaming callback API, without temporary files. The revision and its `ingest_revision` job are created in one transaction: 202 for a new revision, 200 with the existing revision's observed state for identical bytes;
  - read-only views of a vendor's documents, one document, its revisions, a revision's chunks and an ingestion job, each from one REPEATABLE READ, READ ONLY snapshot;
  - the derived `ingestion_state` (`queued`, `in_progress`, `stalled`, `active`, `superseded`, `failed`), with `lease_expired` for running jobs.

  The caps and pagination bounds are initial engineering choices, not measured results. Ruff, strict Mypy and the database-independent suite ran and passed locally on Windows (Prompts 89–90; Prompt 90 corrected raw header-byte counting and parameter validation after review). At acceptance (Prompt 91), the reported local Windows verification was `1260 passed, 205 skipped`, where the skips are 204 PostgreSQL tests and one POSIX-only signal test. It was verified in CI on `feat/document-api` at `ccdf08d` (`ccdf08d3b901c348da8fbe03a87421e6d9c92ca7`; [CI run 38755179760](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38755179760)). From job logs retrieved by the external reviewer: [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38755179760/job/116491605348) `1261 passed, 204 skipped in 18.44s`, [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38755179760/job/116491604657) `1260 passed, 205 skipped in 33.03s`, and the [PostgreSQL integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38755179760/job/116491605959) `204 passed, 1261 deselected in 59.29s`: the full 204-test integration suite, including all 26 M3e tests. The [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38755179509) passed ([job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38755179509/job/116491603175): 37 commits scanned, no leaks found). The reviewer did not run the suite locally. These results demonstrate the tested behaviour, not a performance benchmark or a general security guarantee. It was then fast-forwarded onto `main` at `2e605e7` (`2e605e7bcf3b7b1ee90e9f12cb2acddb6950048f`, adding only documentation after `ccdf08d`), where [CI run 38758727669](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38758727669) passed again. From job logs retrieved by the external reviewer: [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38758727669/job/116503999468) `1261 passed, 204 skipped in 28.04s`, [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38758727669/job/116503999418) `1260 passed, 205 skipped in 29.97s`, and the [PostgreSQL integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38758727669/job/116503999580) `204 passed, 1261 deselected in 56.65s`. The [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38758727831) passed ([job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38758727831/job/116503999509): 38 commits scanned, no leaks found). Both runs were push events on `main`; the reviewer did not run the suite locally. See [ADR-0011](docs/decisions/0011-document-api.md).
- Tests, Ruff and strict Mypy, run in GitHub Actions on Ubuntu and Windows, plus a PostgreSQL 17 + pgvector integration job on Ubuntu.

**M2 accepted.** The external reviewer accepted M2 against its agreed criteria (see [docs/plan.md](docs/plan.md)), on the basis of the implementation diffs and the CI evidence below; the reviewer did not run the suite locally. This does not claim any vector functionality: the CI database image includes pgvector, but no migration creates the extension. Compose has never been run.

**Verified baseline:** `main` at commit `6f8ffde` (`6f8ffded2e5c7b2ed69e37700dc03f20f5e24482`, M2, M3a, M3b and M3c) passed:
- [CI run 38286702295](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38286702295): verification on [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38286702295/job/114936682783) (`819 passed, 133 skipped in 18.04s`) and [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38286702295/job/114936682699) (`818 passed, 134 skipped in 18.87s`), and the [PostgreSQL integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38286702295/job/114936682399) (`133 passed, 819 deselected in 38.29s`), all from logs retrieved by the external reviewer;
- the [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38286702205) (30 commits scanned, no leaks found).

Earlier, `main` at commit `dd26c70` (`dd26c7099d1007e9ee615204dc0056abe8820c67`, M2, M3a and M3b) passed:
- [CI run 38255786860](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38255786860): verification on [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38255786860/job/114833375464) (`709 passed, 77 skipped in 18.16s`) and [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38255786860/job/114833375444) (`708 passed, 78 skipped in 21.20s`), and the [PostgreSQL integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38255786860/job/114833375219) (`77 passed, 709 deselected in 17.36s`), all from logs retrieved by the external reviewer;
- the [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38255786973) (26 commits scanned, no leaks found).

Earlier, `main` at commit `b3f9845` (`b3f984552bf22cf6350702330d30851f3e08b3f4`, M2 and M3a) passed:
- [CI run 38242144844](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38242144844): verification on [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38242144844/job/114787118333) (`605 passed, 63 skipped in 7.56s`) and [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38242144844/job/114787118106) (`605 passed, 63 skipped in 14.86s`), and the [PostgreSQL integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38242144844/job/114787118281) (`63 passed, 605 deselected in 16.17s`), all from logs retrieved by the external reviewer;
- the [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38242144876) (22 commits scanned, no leaks found).

Earlier, `main` at commit `9d5a93a` (`9d5a93ab1389d8a2b084c8f669df3bf9941a477f`, M2a, M2b and M2c) passed:
- [CI run 38214711868](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38214711868): verification on [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38214711868/job/114696647399) and [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38214711868/job/114696647671), and the [PostgreSQL integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38214711868/job/114696647728), whose log (retrieved by the external reviewer) reports `21 passed, 458 deselected in 4.92s`;
- the [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38214711864).

Earlier, `main` at commit `277dfea` (`277dfeaec7c1c64fa5ee92a3ce892823acc787fb`, M2a and M2b) passed:
- [CI run 38167398488](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38167398488): verification on [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38167398488/job/114552700669) and [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38167398488/job/114552700864), and the [PostgreSQL integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38167398488/job/114552700841), whose log (retrieved by the external reviewer) reports `15 passed, 377 deselected in 3.77s`;
- the [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38167398504).

Earlier, `main` at commit `e2dee5c` (`e2dee5cf199cfa2b0ecbdc4d55a2cd7ea5865c00`, M2a) passed:
- [CI run 38159547345](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38159547345): verification on [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38159547345/job/114529403167) and [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38159547345/job/114529403100), and the [PostgreSQL integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38159547345/job/114529402973), whose log (retrieved by the external reviewer) reports `10 passed, 250 deselected in 2.64s`;
- the [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38159547321).

The earlier M1 baseline `6d64fb3` passed [CI](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38142996464) and the [secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38142996460). These results cover those commits only; every later change needs its own passing runs. M2c's branch results are under [Vendors and readiness](#vendors-and-readiness-m2c).

**Limits:**
- The M1b report rules are still in-memory only. Nothing persists reports yet, and there is no protection against concurrent requests.
- The endpoints are `/healthz`, `/readyz`, `/v1/me` and the vendor endpoints. No endpoint uses the report rules yet. On `main` since `cdf7260`, M3d's `ingest_revision` handler chunks and activates revisions; since `2e605e7`, the M3e upload and document endpoints are on `main` too.
- Vendor pages use offset pagination, which is not a snapshot under concurrent changes (see ADR-0006).
- API keys are possession-based bearer credentials, with no rate limiting, lockout, expiry or scopes yet (see ADR-0005).
- A citation's shape is validated. Whether the tenant may see the chunk, whether the quote is really in it, and whether it supports the claim are **not** checked yet.
- Human approval in EvidenceGuard does not establish document authenticity or certify compliance. See [docs/responsible-ai.md](docs/responsible-ai.md) and [docs/threat-model.md](docs/threat-model.md).

**Milestone record and remaining work** (see [docs/plan.md](docs/plan.md)):
- Revision activation and supersession tests, deferred from M1 to M3: now on `main` with M3c and passing in CI, including against PostgreSQL.
- M3 (worker, documents and revisions, parsing and chunking, uploads, Docker) is complete, following the accepted slice sequence in [docs/plan.md](docs/plan.md). M3a, M3b and M3c are on `main`; the M3d ingestion specification (parsing, chunking, migration `0004` and the `ingest_revision` handler) was accepted at review in [docs/plan.md](docs/plan.md), with its limits as initial engineering defaults rather than measured results, and is implemented, reviewed, verified in CI and on `main` at `cdf7260`; the M3e upload and document API specification was accepted at review in [docs/plan.md](docs/plan.md), with its caps and pagination bounds as initial engineering choices rather than measured results, and its implementation is reviewed, verified in CI and on `main` at `2e605e7`; the M3f container specification was accepted at review in [docs/plan.md](docs/plan.md), and its implementation is reviewed, verified in CI and on `main` at `e2463cb`, including the image build, effective build-context check, image checks, CI Compose smoke and cleanup ([ADR-0012](docs/decisions/0012-containers.md)). Local Compose is unverified. Overall M3 was accepted at external review (Prompt 105), with its four documented evidence limitations (see the assessment in [docs/plan.md](docs/plan.md)). M4a is verified and on `main` at `5fdaa1c`; the M4b specification is accepted (Prompt 116) and its implementation is accepted (Prompt 118), verified in CI and on `main` at `872d0af`; the M4c specification is accepted (Prompt 124) and its implementation by Claude Code in Prompt 125, corrected in Prompt 126, is accepted at external review for a local commit (Prompt 127), with CI verification pending; M4d–M4f remain unimplemented and overall M4 acceptance is pending.
- Remaining after M3: embedding/indexing installed-wheel coverage on CI runners (the new script ran locally on Windows in Prompts 125–126, including the corrected provider-resolution probe in Prompt 126; `main` at `872d0af` predates the extension), current-version PostgreSQL, Linux and real container indexing CI verification of the accepted M4c implementation, live embedding adapters, retrieval, model providers, the review workflow, API endpoints for the approval gate, and evaluation.

No retrieval, agent workflow, evaluation results, security guarantees or benchmarks are claimed. Any future results will be published with their committed inputs, configuration and the command that reproduces them.

## Development (Windows, PowerShell)

**Prerequisite:** [uv](https://docs.astral.sh/uv/) 0.13 or later. uv provides Python 3.12; the repository pins it in `.python-version`.

Set up:

```powershell
uv python install 3.12
uv sync --locked
```

Check (no database needed; PostgreSQL integration tests are skipped unless `EG_TEST_DATABASE_URL` is set):

```powershell
uv run --locked ruff format --check .
uv run --locked ruff check .
uv run --locked mypy
uv run --locked pytest
uv build
```

Run the API (Ctrl+C to stop):

```powershell
uv run --locked eg-api            # http://127.0.0.1:8000
uv run --locked eg-api --port 8765
```

Then open `http://127.0.0.1:8000/healthz` or `http://127.0.0.1:8000/docs`. The same commands work in a POSIX shell.

### Database (M2a)

The persistence package (`evidenceguard_persistence`) adds PostgreSQL settings, the tenancy schema (tenants, users, API keys and vendors) and Alembic migrations. See [ADR-0004](docs/decisions/0004-persistence-foundation.md).

> **Verified in CI; Compose not run.**
> - **What passed:** on branch `feat/persistence-foundation` at commit `9ad7dae`, the [PostgreSQL 17 + pgvector integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38158076257/job/114525070229) ran all ten integration tests against a disposable service database. They cover migration upgrade, downgrade and re-upgrade, the drift check, tenant constraints and that no extension is created. Its log reports `10 passed, 250 deselected`, so none was skipped.
> - **Other checks in the same runs:** the database-independent checks passed on [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38158076257/job/114525070324) and [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38158076257/job/114525070158) in [CI run 38158076257](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38158076257), and the [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38158076261) passed.
> - **On `main`:** M2a was fast-forwarded onto `main` at `e2dee5c`. [CI run 38159547345](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38159547345) passed there, including the [integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38159547345/job/114529402973) (`10 passed, 250 deselected in 2.64s`, log retrieved by the external reviewer), as did the [secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38159547321).
> - **Compose:** Docker is not available on the development machine, so `docker-compose.yml` has never been run.
> - **pgvector:** M2a creates no vector extension, so no pgvector functionality has been tested.

1. Start a disposable PostgreSQL 17 + pgvector server. `docker-compose.yml` binds it to `127.0.0.1:5433` with **disposable local-only credentials**: user `evidenceguard`, password `evidenceguard-local-dev`, databases `evidenceguard_dev` and `evidenceguard_test`. Never reuse these anywhere else.

   ```powershell
   docker compose up -d postgres
   ```

2. Set the database URLs in your shell. Variable names are listed in `.env.example`; EvidenceGuard does not read a `.env` file automatically. URLs must name exactly one host, an optional port (5432 if omitted) and a database. The only query parameters accepted are `sslmode` and `connect_timeout` (1–600 seconds), each at most once. Anything else, such as `dbname`, `host`, `service`, `password` or `options`, is rejected with an error that never repeats the URL.

   ```powershell
   $env:EG_DATABASE_URL = "postgresql+psycopg://evidenceguard:evidenceguard-local-dev@127.0.0.1:5433/evidenceguard_dev"
   $env:EG_TEST_DATABASE_URL = "postgresql+psycopg://evidenceguard:evidenceguard-local-dev@127.0.0.1:5433/evidenceguard_test"
   ```

3. Run migrations:

   ```powershell
   uv run --locked alembic upgrade head          # apply (uses EG_DATABASE_URL)
   uv run --locked alembic downgrade base        # remove every table
   uv run --locked alembic upgrade head --sql    # print the SQL only; needs no database
   ```

4. Run the integration tests. They use **only** `EG_TEST_DATABASE_URL`, and drop and recreate the `public` schema of that database. **Point it only at a database you can lose.** Before creating any engine, they refuse to run if:
   - the URL is invalid;
   - the database name doesn't end in `_test`;
   - `EG_DATABASE_URL` is set but invalid;
   - `EG_DATABASE_URL` targets the same host, port and database. This ignores credentials, driver spelling, host case, an omitted default port and loopback spellings such as `localhost`, `127.0.0.1` and `[::1]`.

   The check compares URLs only. It cannot tell that two different DNS names (or a name and an IP address) reach the same server.

   ```powershell
   $env:EG_REQUIRE_INTEGRATION = "1"   # fail, rather than skip, if the URL is missing or nothing runs
   uv run --locked pytest -m integration
   ```

CI runs step 4 on Ubuntu against a PostgreSQL 17 + pgvector service container. Database-independent checks still run on Ubuntu and Windows.

### Authentication and `eg-admin` (M2b)

> **Reviewed and verified in CI, and on `main`** since the fast-forward to `277dfea` ([CI run 38167398488](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38167398488), [integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38167398488/job/114552700841): `15 passed, 377 deselected in 3.77s`). The branch record follows.
> - **Tested commit:** `b2f7f23` (`b2f7f2310cb265dcaab9a5c3055b3d762fa02d46`).
> - **[CI run 38166627885](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38166627885)** passed:
>   - verification on [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38166627885/job/114550418430) and [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38166627885/job/114550418222);
>   - the [PostgreSQL 17 + pgvector integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38166627885/job/114550418432). Its log, retrieved by the external reviewer, reports `15 passed, 377 deselected in 2.49s`, so none was skipped. The tests cover key creation, authentication, revocation, cross-tenant ownership, `seed-demo` idempotency and conflicts, and current-role reads.
> - **The [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38166627930)** passed.
> - **Compose** has never been run.
>
> Do not run these commands against a database you care about.

API keys look like `egk_<16 hex prefix>_<43-character secret>` (64 characters). Only the prefix and the SHA-256 of the secret are stored. A key is sent as `Authorization: Bearer <key>`. The tenant, user and role always come from the stored records, never from request headers, query parameters or bodies. Design and limits: [ADR-0005](docs/decisions/0005-api-key-authentication.md).

With `EG_DATABASE_URL` set and migrations applied (steps 2 and 3 above):

```powershell
uv run --locked eg-admin seed-demo     # synthetic demo tenants and users; idempotent; creates no keys
uv run --locked eg-admin create-key --tenant-id <tenant-id> --user-id <user-id>
uv run --locked eg-admin revoke-key --tenant-id <tenant-id> --prefix <16-hex-prefix>
```

- **`create-key`** prints the new key **once**, to stdout, only after it is stored. Store it securely; it cannot be shown again. No command accepts a secret as an argument, and usage errors print only static usage, never the arguments given.
- **`GET /v1/me`** returns `tenant_id`, `actor_id` and `role` for a valid key. Missing, malformed, unknown and revoked keys all get the same `401` with `WWW-Authenticate: Bearer`. If the database is not configured or not reachable, it returns a generic `503`. `/healthz` never needs a database.

### Vendors and readiness (M2c)

> **Reviewed and verified in CI, and on `main`** since the fast-forward to `9d5a93a` ([CI run 38214711868](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38214711868), [integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38214711868/job/114696647728): `21 passed, 458 deselected in 4.92s`, from the log retrieved by the external reviewer). The branch record follows.
> - **Tested commit:** `a888b6c` (`a888b6cbd277fb6a4556899fa630a7c50df14e61`), which adds only documentation after the reviewed M2c commit `73bebf5`.
> - **[CI run 38212619855](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38212619855)** passed:
>   - verification on [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38212619855/job/114689994050) and [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38212619855/job/114689993962);
>   - the [PostgreSQL 17 + pgvector integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38212619855/job/114689994147). Its log, retrieved by the external reviewer, reports `21 passed, 458 deselected in 4.65s`, so none was skipped. M2c's six tests cover API create/list/get, two-tenant isolation with identical slugs, duplicate rollback, pagination, and readiness when ready, unmigrated or mismatched.
> - **The [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38212619867)** passed.
> - **Not verified:** Compose has never been run. No vector functionality is tested: the CI database image includes pgvector, but no migration creates the extension.

With a reviewer or approver key (admins get `403`):

```powershell
$h = @{ Authorization = "Bearer <your API key>" }
Invoke-RestMethod -Method Post http://127.0.0.1:8000/v1/vendors -Headers $h -ContentType "application/json" -Body '{"slug": "lumenvale-cloud", "name": "Lumenvale Cloud"}'
Invoke-RestMethod "http://127.0.0.1:8000/v1/vendors?limit=20&offset=0" -Headers $h
Invoke-RestMethod http://127.0.0.1:8000/readyz   # no key needed
```

- **Vendors belong to the key's tenant.** The body takes only `slug` (lowercase letters and digits joined by single hyphens, at most 64 characters) and `name` (1–200 characters, not blank, no null character). Any other field is a `422`. A duplicate slug in the same tenant is a `409`; another tenant may reuse it. Another tenant's vendor and a missing one both return `404`.
- **Pages** are ordered by slug, then ID, with `limit` 1–100 (default 20) and `offset` 0–10,000. They are not a snapshot when vendors are added concurrently.
- **`GET /readyz`** returns `200 {"status": "ready", ...}` only when the database answers and its migrations exactly match this release; otherwise `503` with fixed check states. It never migrates or changes the database. `/healthz` is unaffected.

Packaging layout: [ADR-0001](docs/decisions/0001-packaging-and-layout.md). Request IDs, logging and error format: [ADR-0002](docs/decisions/0002-request-ids-logging-and-errors.md). Workflow orchestration: [ADR-0003](docs/decisions/0003-plain-python-workflow.md). Persistence: [ADR-0004](docs/decisions/0004-persistence-foundation.md). API-key authentication: [ADR-0005](docs/decisions/0005-api-key-authentication.md). Vendors, shared database lifecycle and readiness: [ADR-0006](docs/decisions/0006-vendor-api-and-readiness.md). Durable job core: [ADR-0007](docs/decisions/0007-durable-job-core.md). Worker runtime: [ADR-0008](docs/decisions/0008-worker-runtime.md). Documents and revisions: [ADR-0009](docs/decisions/0009-document-revisions.md).

The request ID is for correlating logs only. It is not authentication and says nothing about who made a request. Logs are local JSON lines on stderr; there is no monitoring or telemetry service.

### Containers (M3f; verified in CI and on `main`; not run locally)

> **Verified in CI; not run locally.** Docker is not available on the development machine, so none of these commands has been run locally.

**Feature branch (historical):** it was verified in CI on `feat/container-stack` at `682101b` (`682101b4f06d099b147b8d21734fa83f7f53637f`; [CI run 38769986459](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38769986459), a push event, conclusion success). From job logs retrieved by the external reviewer:
- [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38769986459/job/116542962186): `1364 passed, 204 skipped in 27.63s`;
- [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38769986459/job/116542962338): `1363 passed, 205 skipped in 39.61s`;
- [PostgreSQL integration](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38769986459/job/116542961580): `204 passed, 1364 deselected in 59.62s`;
- [container job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38769986459/job/116542962209):
  - `compose config: ok` and `context: ok (72 files; 19 planted fixtures excluded)`;
  - the application image built;
  - the image checks passed: UID and GID 10001, `--help` for `eg-api`, `eg-worker` and `eg-admin`, installed imports, offline migration SQL and runtime contents;
  - the stack started with the database healthy, the migration complete and the API healthy, and `migrate`, `api` and `worker` ran the CI-built image;
  - an API key was created and held in memory; the upload was accepted (202), the ingestion job succeeded, and the revision was active with 2 verified chunks;
  - a duplicate upload returned the existing revision (200), and the idle worker exited with code 0 and no OOM kill;
  - `smoke: ok` and `cleanup: ok`;
- the [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38769986224) ([job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38769986224/job/116542954404)): 41 commits scanned, no leaks found.

The reviewer did not run the suite or Docker locally. Claude's anonymous API session saw only the job and step conclusions (all `success`, none skipped) and could not retrieve the logs.

**On `main`:** It was then fast-forwarded onto `main` at `e2463cb` (`e2463cb5a94d7c40eb1d894b8fded29a866165a8`, adding only documentation after `682101b`), where [CI run 38773393988](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38773393988) passed again (a push event, conclusion success). From job logs retrieved by the external reviewer:
- [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38773393988/job/116554736110): `1364 passed, 204 skipped in 28.13s`;
- [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38773393988/job/116554736342): `1363 passed, 205 skipped in 39.10s`;
- [PostgreSQL integration](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38773393988/job/116554736165): `204 passed, 1364 deselected in 61.97s (0:01:01)`;
- [container job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38773393988/job/116554735789):
  - `compose config: ok` and `context: ok (72 files; 19 planted fixtures excluded)`;
  - the image checks passed: UID/GID 10001, all three CLI helps, installed imports, offline migration SQL and runtime contents;
  - the stack started with the database healthy, the migration complete and the API healthy, and `migrate`, `api` and `worker` ran the CI-built image;
  - an API key was held in memory; the upload was accepted (202), the ingestion job succeeded, and the revision was active with 2 verified chunks;
  - a duplicate upload returned the existing revision (200), and the idle worker exited with code 0 and no OOM kill;
  - `smoke: ok` and `cleanup: ok`;
- the [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38773393999) ([job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38773393999/job/116554735382)): 42 commits scanned, no leaks found.

The reviewer did not run the suite or Docker locally. Claude's anonymous API session saw only the job and step conclusions (all `success`) and could not retrieve the logs.

CI Compose verification is complete for this version; under the accepted specification, it can satisfy M3's Compose requirement alongside M3's other criteria. Local Compose remains unverified. The smoke shows the tested idle-worker shutdown, not a shutdown bound for an in-flight handler. Overall M3 was accepted at external review (Prompt 105), with documented evidence limitations. This is a development stack: no production readiness, benchmark or general security guarantee is claimed. The approved uv exception is unchanged. See [ADR-0012](docs/decisions/0012-containers.md). The stack has no TLS, secrets management or production deployment.

`docker-compose.yml` defines four services:
- `postgres`: the existing pinned pgvector image, on `127.0.0.1:5433`;
- `migrate`: a one-shot Alembic upgrade, the only service that migrates;
- `api`: on `127.0.0.1:8000`, healthy when `/readyz` returns 200;
- `worker`: the sequential worker.

The application services all run one locally built image, `evidenceguard:dev` by default (set `EG_IMAGE` to change it), which is never pulled from a registry. They run as UID 10001 with a read-only filesystem. The database credentials are the disposable ones above.

```powershell
docker compose build                     # builds evidenceguard:dev
docker compose up -d --wait              # database healthy, migrate done, api healthy, worker running
docker compose run --rm migrate          # re-run migrations explicitly (idempotent)
docker compose exec api eg-admin seed-demo
docker compose exec api eg-admin create-key --tenant-id <tenant_id> --user-id <user_id>
$env:EG_KEY = Read-Host "Paste the key printed above"   # stays in this shell only; never commit it
$headers = @{ Authorization = "Bearer $env:EG_KEY" }
$vendor = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/v1/vendors -Headers $headers `
  -ContentType application/json -Body '{"slug": "lumenvale", "name": "Lumenvale"}'
curl.exe -sS "http://127.0.0.1:8000/v1/vendors/$($vendor.id)/documents" -H "Authorization: Bearer $env:EG_KEY" `
  -F document_key=security-policy -F "title=Security policy" -F source_type=vendor_statement `
  -F "file=@policy.md;type=text/markdown"
Invoke-RestMethod -Uri http://127.0.0.1:8000/v1/jobs/<job_id> -Headers $headers
Invoke-RestMethod -Uri http://127.0.0.1:8000/v1/documents/<document_id> -Headers $headers
Invoke-RestMethod -Uri http://127.0.0.1:8000/v1/documents/<document_id>/revisions/1/chunks -Headers $headers
docker compose logs api worker
docker compose stop                      # requests a graceful stop; the database volume is kept
docker compose down -v                   # removes the containers and the database volume
```

- **Upload file:** `policy.md` is any synthetic Markdown file.
- **Starting only the database:** use `docker compose up -d postgres`.
- **Stopping the worker:** `docker compose stop` sends SIGTERM and allows the worker 60 s. That is an external termination budget, not a guaranteed shutdown time: a blocked database call can outlast it, after which Docker kills the container (ADR-0008, ADR-0012).

## Engineering record

[prompts.md](prompts.md) records, verbatim and in order, every prompt given to the Claude Code implementation session, with a short note on each outcome. [CLAUDE.md](CLAUDE.md) holds the standing development rules.

## Secret scanning

A GitHub Actions workflow ([secret-scan.yml](.github/workflows/secret-scan.yml)) runs [Gitleaks](https://github.com/gitleaks/gitleaks) v8.30.1 over the full Git history on every push and pull request. It [passed](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38142996460) for the published baseline `6d64fb3`.

A CI scan runs only after code has reached GitHub, so it cannot stop a secret from being published. Scan locally before every commit and push.

### Install and check

On Windows, winget installs the official release binary at a pinned version:

```powershell
winget install --id Gitleaks.Gitleaks --exact --version 8.30.1
gitleaks version   # expect: 8.30.1
```

On other platforms, download a binary from the [v8.30.1 release](https://github.com/gitleaks/gitleaks/releases/tag/v8.30.1), verify it against `gitleaks_8.30.1_checksums.txt`, then run `gitleaks version`.

### Before every commit (including the first)

1. Review what is staged:

   ```powershell
   git status
   git diff --cached --name-only
   git diff --cached
   ```

2. Scan the staged content:

   ```powershell
   gitleaks git --pre-commit --staged --redact --verbose .
   ```

A new repository with no commits has no history to scan, so a full-history scan cannot check it. Before the first commit, scan the staged content instead.

### Before pushing

Once commits exist, scan the whole local history:

```powershell
gitleaks git --redact --verbose .
```

### Limits

- `--redact` keeps detected values out of the terminal output.
- If Gitleaks reports a finding, remove the secret and rotate the credential. Do not allowlist it.
- Scanners match known patterns and cannot detect every secret or every piece of private data. A clean scan does not replace a human review of the staged diff.
