# EvidenceGuard implementation plan

**Status:** M1, M2 and M3 accepted and published; final M3 documentation baseline `85cb0d6` (see §9). M4 sequence and complete M4a specification were accepted at external review (Prompt 108), following Prompt 107. M4a is verified and on `main` at `5fdaa1c`. The M4c installed-wheel extension, which executes the offline embedding and canonical storage path and imports the indexing modules, ran locally on Windows in Prompts 125–126 (historical) and passed on Ubuntu and Windows CI runners at `600a366` and again on `main` at `76fa5a3`; the earlier M4a/M4b wheel limitations are historical. The M4b specification was accepted in Prompt 116 and the implementation in Prompt 118; M4b is reviewed, verified in CI and on `main` at `872d0af`. The M4c indexing specification was accepted at external review in Prompt 124 (proposed in Prompt 122, corrected in Prompt 123); M4c was implemented by Claude Code in Prompt 125, corrected in Prompt 126 and accepted at external review for a local commit in Prompt 127 (ADR-0015); it is reviewed, verified in CI and on `main` at `76fa5a3` (PostgreSQL, Linux, Windows, installed-wheel and container indexing; see the [ADR-0015 main CI evidence](decisions/0015-revision-indexing.md#main-ci-evidence-at-76fa5a3); earlier feature-branch verification at `600a366` is historical). The [M4d snapshot and retrieval specification](#m4d-snapshot-and-retrieval-specification-accepted-at-review-prompt-133-implementation-pending) was proposed in Prompt 131, corrected in Prompt 132 and accepted at external review in Prompt 133. Claude Code implemented it in Prompt 134 on `feat/snapshot-retrieval` and corrected it in Prompt 135 ([ADR-0016](decisions/0016-snapshot-retrieval.md)); the implementation was **accepted at external review in Prompt 136** and is **reviewed, verified in CI and on `main` at `cf2b5743`** (Ubuntu, Windows, PostgreSQL with all 39 M4d cases passing, installed-wheel retrieval check, the unchanged container job and Gitleaks; see the [ADR-0016 main CI evidence](decisions/0016-snapshot-retrieval.md#main-ci-evidence-at-cf2b5743)); the feature-branch verification at `3d6e8395` and Claude Code's local Windows results in Prompts 134–135 are historical. The [M4e corpus and retrieval-evaluation specification](#m4e-corpus-and-retrieval-evaluation-specification-accepted-at-review-prompt-143-implementation-pending) was proposed in Prompt 140, corrected in Prompts 141–142 and **accepted at external review in Prompt 143**; Claude Code implemented it in Prompt 144 on `feat/retrieval-evaluation` and corrected it in Prompts 145–146 ([ADR-0017](decisions/0017-retrieval-evaluation.md)); the implementation was **accepted at external review in Prompt 147 for a local implementation commit** and **published on `feat/retrieval-evaluation` in Prompt 148 at `c14821b7`**, where exact-commit CI was not fully green: PostgreSQL integration passed (306 passed, including all 16 M4e cases), but one Ubuntu test failed because its `os.lstat` double re-entered itself on Linux (no production defect established; see [ADR-0017](decisions/0017-retrieval-evaluation.md#exact-commit-ci-at-c14821b7-and-test-correction-prompts-148149)); the Prompt 149 test-only correction was accepted in Prompt 150 and published in Prompt 151; after feature-branch verification at `d1dcdfce` (historical), M4e is **reviewed, verified in CI and on `main` at `0ae4c6ca`** (`0ae4c6ca339232e40cc007d7b78334af08a8b25b`, committed and fast-forwarded by OpenAI Codex in Prompt 153 after green feature CI; main CI then passed; see the [ADR-0017 main CI evidence](decisions/0017-retrieval-evaluation.md#main-ci-evidence-at-0ae4c6ca)), and no database-derived Recall value has been observed; the [M4f Voyage adapter specification](#m4f-voyage-adapter-specification-accepted-at-review-prompt-157-implementation-pending) was proposed in Prompt 154, corrected in Prompts 155–156 and **accepted at external review in Prompt 157**; its implementation (Prompt 158, corrected in Prompt 159, [ADR-0018](decisions/0018-voyage-adapter.md)) was accepted at external review in Prompt 160, verified in feature-branch CI at `84eec023` (historical) and is **reviewed, verified in CI and on `main` at `5acb75e5`** (`5acb75e59edbb42035d468c2c40bb0ab81a8725a`, published in Prompt 163 after all five feature jobs passed for that exact commit; main CI then passed; see the [ADR-0018 main CI evidence](decisions/0018-voyage-adapter.md#main-ci-evidence-at-5acb75e5)); the [overall M4 acceptance assessment](#overall-m4-acceptance-assessment-accepted-at-review-prompt-165) was prepared in Prompt 164 and **overall M4 was accepted at external review in Prompt 165 within the reviewed scope implemented at `5acb75e5`**; the acceptance record (committed locally in Prompt 165, historical) was **published on `main` at `46c02257` in Prompt 166**, with all five jobs passing on the documentation branch and again on `main` ([acceptance publication evidence](#acceptance-publication-evidence-prompt-166)); the implementation baseline remains `5acb75e5`. **M1–M4 are accepted within their recorded scopes; the [M5 implementation sequence](#m5-implementation-sequence-accepted-at-review-prompt-170) and the complete [M5a specification](#m5a-model-call-contracts-and-scripted-fake-provider-accepted-at-review-prompt-170-implementation-pending) were accepted at external review in Prompt 170 (proposed in Prompt 167, corrected in Prompt 168, clarified in Prompt 169); M5a was implemented by Claude Code in Prompt 171, corrected in Prompt 172 and accepted at external review in Prompt 173 for a local commit on `feat/model-call-contracts` ([implementation status](#m5a-implementation-status-accepted-for-a-local-commit-prompt-173-ci-pending), [ADR-0019](decisions/0019-model-call-contracts.md)), with publication, Linux verification and current-version CI pending; M5b–M5h have not started and overall M5 acceptance is pending.** Later milestones remain plans. Historical evidence below retains its original baseline.

EvidenceGuard is a vendor-risk review copilot. It ingests synthetic vendor documents, retrieves evidence the tenant is authorized to see, classifies each review question against that evidence, and drafts a cited report. A human must approve the exact report revision before it can be finalized or exported. It is decision support, not legal advice or compliance certification.

Labels: **[FACT]** observed or verified; **[DECISION]** accepted in review; **[REC]** recommendation not yet reviewed; **[OPEN]** unresolved.

---

## 1. Review decisions

### Accepted direction

| # | Decision |
|---|---|
| D1 | One Python distribution (`evidenceguard`) with prefixed import packages (§3). |
| D2 | Add `packages/persistence/` for SQLAlchemy models, repositories, the job queue and Alembic migrations. |
| D3 | GitHub workflows live under `.github/workflows/`. `infra/github/` is not created. |
| D4 | The Planner and the Report Composer are deterministic code in v1. |
| D5 | Model judgment is used only in the Evidence Verifier and the Risk Analyst. |
| D6 | Orchestration is plain Python with persisted, typed stage state. LangGraph is not used. |
| D7 | Ingestion and reviews run as PostgreSQL-backed jobs in a separate worker. Vector search uses an exact scan, with no approximate index in v1. |
| D8 | v1 ingests Markdown and UTF-8 plain text only. |
| D9 | A provider refusal leaves the question unresolved. There is no automatic refusal fallback in v1. |
| D10 | The live model is chosen by measured evaluation. No default is fixed in advance. |
| D11 | No local embedding-model download by default. The real embedding provider is an API (Voyage); a local provider is an optional enhancement. |

### Corrections from review

| # | Area | Where |
|---|---|---|
| A | Chunk identity is scoped to tenant and document revision. | §4 Chunk, §5 |
| B | A revision activates only after successful ingestion, inside one transaction. Each review snapshots its eligible revisions and configuration. | §4 lifecycles, §9 M3–M5 |
| C | Evidence semantics separate provenance, claim type, conflict, missing evidence and unestablished authenticity. | §4 Verification, §7 |
| D | Evaluation measures claim support, coverage, paired injection cases and descriptive latency. | §7 |
| E | Recovery reuses persisted results, does not promise exactly-once model calls, and fences every stage write. | §4 lifecycles, §8 |
| F | Threat-model and responsible-AI documents start in M1 and must be complete before v0.1. The environment section is refreshed. | §2, §9 |

---

## 2. Environment

| Item | Status |
|---|---|
| Repository | [FACT] Published to GitHub. `main` is at `46c02257` (M1–M4 accepted; M4 implementation baseline `5acb75e5`; the M4 acceptance record published in Prompt 166; see §9). It was at `5acb75e5` before that publication and at `85cb0d6` when this table was refreshed in Prompt 107 (both historical). |
| Python | [FACT] 3.12 (uv-managed) for the project; 3.13 and 3.11 are also installed. |
| uv | [FACT] 0.13.0. |
| Docker | [FACT] **Not installed** (no Docker, Docker Compose or Podman). No WSL distribution is listed. |
| PostgreSQL | [FACT] A local PostgreSQL **16** Windows service is installed and running. **pgvector is not installed** in it, and its tools are not on PATH. The plan's CI target remains `pgvector/pgvector:0.8.7-pg17`. Rechecked 2026-10-11 for M2. |
| gh CLI | [FACT] Not installed. |
| Gitleaks | [FACT] 8.30.1 installed (by the user, via winget). |
| Hardware | [FACT] A modest Windows 11 laptop: 2-core i3, 7.8 GB RAM, integrated GPU, and limited free space on the system drive (about 9 GB). A second drive has ample space. |
| API keys | [FACT] Anthropic and Voyage keys are not configured. Only their presence was checked. |

**Documentation checked (2026-10-11):**
- [FACT] [Claude Models overview](https://platform.claude.com/docs/en/models/overview), prices per million tokens:
  - `claude-opus-5-5`: $4 input / $20 output
  - `claude-sonnet-5-5`: $2 / $10
  - `claude-haiku-5-5`: from $0.10 / $0.50
- [FACT] Claude API constraints:
  - Structured outputs use `output_config.format` or `messages.parse()`.
  - Claude's native citations feature cannot be combined with structured outputs, so EvidenceGuard implements its own chunk-ID citations.
  - Forced `tool_choice` returns 400 on Opus 5.5 and Sonnet 5.5.
  - Opus 5.5 thinking cannot be disabled; `effort` defaults to `medium`.
  - `stop_reason` must be checked for `refusal` and `max_tokens`.
  - The Python SDK defaults to a 10-minute timeout and 2 retries.
- [FACT] [Anthropic embeddings guidance](https://platform.claude.com/docs/en/build-with-claude/embeddings):
  - Anthropic has no embedding model of its own and points to Voyage AI.
  - `voyage-4-lite`, `voyage-4` and `voyage-4-large` each default to 1024 dimensions.
  - `input_type` must be `query` or `document`.
- [FACT] [Voyage pricing](https://docs.voyageai.com/docs/pricing) (page updated 2026-09-29):
  - `voyage-4-lite` costs $0.02 per million tokens.
  - The voyage-4 family includes 200M free tokens.
- [FACT] [pgvector](https://github.com/pgvector/pgvector) 0.8.7:
  - Docker image `pgvector/pgvector:0.8.7-pg17`.
  - HNSW filters after the index scan, so tenant-filtered queries need `hnsw.iterative_scan`.

**Still to verify during implementation:**
- ~~Hatchling editable installs for the multi-root layout~~: verified in M1. The editable install imports every package, and CI installs and imports the built wheel.
- Docker Desktop disk usage on Windows 11 Home.
- Model prices on the date of each live evaluation run.

---

## 3. Packaging (D1, D2)

One `pyproject.toml` defines one distribution, `evidenceguard`, built with hatchling. Each approved directory holds one import package with a prefixed name:

```
apps/api/evidenceguard_api/                      FastAPI app factory, routers, auth dependency, admin CLI
apps/worker/evidenceguard_worker/                job loop, handlers (ingest_revision, run_review)
packages/domain/evidenceguard_domain/            Pydantic contracts, enums, pure state machines, settings
packages/persistence/evidenceguard_persistence/  SQLAlchemy models, repositories, job queue, migrations/
packages/retrieval/evidenceguard_retrieval/      parsing, chunking, embedding providers, hybrid search
packages/agents/evidenceguard_agents/            model-provider protocol, Claude and fake adapters, prompt loader, verifier, analyst, planner, report renderer
packages/observability/evidenceguard_observability/  JSON logging, context IDs, redaction, span recorder
packages/evaluation/evidenceguard_evaluation/    harness, metrics, pricing, CLI
```

```toml
[tool.hatch.build.targets.wheel]
packages = ["apps/api/evidenceguard_api", "apps/worker/evidenceguard_worker",
            "packages/domain/evidenceguard_domain", ...]
[project.scripts]
eg-api = "evidenceguard_api.__main__:main"
eg-worker = "evidenceguard_worker.__main__:main"
eg-admin = "evidenceguard_api.admin:main"
eg-eval = "evidenceguard_evaluation.cli:main"
```

**Import direction**, enforced by an AST-based unit test:
- `domain` imports nothing internal.
- `observability` imports only `domain`.
- `persistence`, `retrieval` and `agents` import `domain` and `observability`.
- `evaluation` may import any package.
- `apps` import packages; no package imports `apps`.

**Layout rules:**
- Each package directory is created in the milestone that first uses it.
- Alembic lives at `evidenceguard_persistence/migrations` (`script_location = evidenceguard_persistence:migrations`).

**Developer commands** are plain `uv run …` (Windows has no `make` by default):
- `uv sync --locked`
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run mypy` (strict, with the pydantic plugin)
- `uv run pytest -m "not integration"`
- `uv run pytest -m integration`

---

## 4. Domain model and typed boundaries

### Entities

Every row carries `tenant_id` unless marked global. Cross-table references use composite foreign keys `(tenant_id, id)`, so a row cannot point at another tenant's data.

**Access and vendors**
- **Tenant**: id, slug, name.
- **User**: role ∈ {reviewer, approver, admin}.
- **ApiKey**: user_id, prefix, secret_sha256, created_at, revoked_at.
- **Vendor**: slug (unique per tenant), name.

**Documents and evidence**
- **Document**:
  - vendor_id, `document_key` (logical identity such as `data-retention-policy`), title.
  - `source_type` ∈ {vendor_statement, contract, third_party_report}: what the uploader says the document is.
  - `authenticity` ∈ {not_established}: v1 has no way to establish authenticity, so every document carries this value and the report shows it. A reviewer-confirmed value is a later enhancement (E11).
  - `active_revision_id` (nullable), which points to the single active revision.
- **DocumentRevision**:
  - document_id, revision_no, version_label, effective_date.
  - `status` ∈ {pending, processing, failed, active, superseded}; failure_reason; superseded_at, superseded_by_revision_id.
  - Content: sha256, media_type, byte_size, content_text, chunker_version.
  - Unique `(tenant_id, document_id, sha256)` makes uploads idempotent within a document.
  - Unique `(tenant_id, document_id, revision_no)`.
- **Chunk** (correction A):
  - `id = uuid5(NS, f"{tenant_id}:{revision_id}:{chunker_version}:{ordinal}")`.
  - Stored with tenant_id, revision_id, chunker_version, ordinal; unique `(tenant_id, revision_id, chunker_version, ordinal)`; FK `(tenant_id, revision_id)` → document_revisions.
  - Because the tenant and revision are inside the ID, identical bytes uploaded by another tenant, another vendor or another document get different chunks and never share evidence. Re-ingesting the same revision reproduces the same IDs, so upserts are idempotent.
  - Provenance: section_path, anchor, line and character ranges. Content: text, content_sha256, is_table, generated `tsvector`, `injection_flag` (heuristic, shown to reviewers only).
  - Chunks are immutable once their revision is active. v1 uses one chunker version; re-chunking is out of scope.
- **ChunkEmbedding**: chunk_id, embedding_model, dims, vector. Unique `(tenant_id, chunk_id, embedding_model)`.

**Jobs**
- **Job**:
  - kind, payload; `idempotency_key` unique `(tenant_id, kind, idempotency_key)`.
  - status ∈ {queued, running, succeeded, failed, dead}.
  - attempt, max_attempts, run_after.
  - Lease: locked_by, lease_expires_at.
  - last_error (redacted).

**Reviews and reports**
- **ReviewTemplate** (global, from YAML): template_id, version, content_sha256, questions.
- **Review** (correction B):
  - vendor_id, template_id@version, created_by, status ∈ {queued, running, completed, failed, cancelled}.
  - `config_snapshot`: template SHA, model IDs and effort, prompt IDs/versions/SHAs, embedding model, chunker version, retrieval parameters.
- **ReviewRevision**: `(tenant_id, review_id, revision_id)`. The exact set of active revisions when the review was created. Revisions still pending at that moment are recorded as excluded and listed in the report.
- **EvidenceQuestion**: question_id, text, search_queries, `requires_documentary_support`, stage ∈ {pending, retrieved, verified, analyzed, failed}.
- **RetrievedPassage**: chunk_id, rank, scores, provenance snapshot.
- **Verification** (correction C):
  - `verdict` ∈ {supported, contradicted, insufficient_evidence}, chosen by the model.
  - claims: a list of `{text, citations: [{chunk_id, quote}]}`.
  - `evidence_status`, derived deterministically (see below).
  - `provenance_check` ∈ {passed, citation_rejected, invalid_output}.
  - provider_call_id.
- **Finding**: question_ids, title, severity ∈ {high, medium, low, info}, statement, evidence_status, citations, follow-up questions for the vendor.
- **Report**: status ∈ {draft, changes_requested, approved, finalized}, current_revision_no.
- **ReportRevision** (immutable): revision_no, content_json, rendered_markdown, `content_sha256`, created_by, reason.
- **ApprovalDecision**: revision_no, content_sha256, decision ∈ {approve, reject}, decided_by, comment, decided_at.

**Observability and audit**
- **ProviderCall**:
  - trace_id, review_id, step, question_id, attempt, request_hash.
  - model_requested, model_used, prompt id/version/SHA.
  - Token usage and latency.
  - stop_reason and refusal category, status, error_type.
  - Content capture is off by default.
- **TraceSpan**, **AuditEvent** (approve, reject, finalize, export, revise).

### Evidence semantics (correction C)

**Provenance checks.** Code checks two things about every citation:
1. The cited chunk is in the authorized set retrieved *for that review and question*.
2. The quote is a normalized substring of that chunk.

These checks prove **provenance only**: the quoted text exists in an authorized document. They do not prove the passage entails the claim, and they do not prove the document is authentic. Whether a passage supports a claim is the model's judgment, measured by the evaluation in §7.

**Evidence status.** `evidence_status` has four values, derived from the model's `verdict` and the cited documents' `source_type`:

| evidence_status | Rule | Report wording |
|---|---|---|
| `vendor_claim` | verdict `supported`, and every supporting citation comes from a `vendor_statement` | "The vendor states …" |
| `documentary_support` | verdict `supported`, and at least one supporting citation comes from a `contract` or `third_party_report` | "Documented in … (authenticity not established)" |
| `conflicting` | verdict `contradicted`: current evidence in the snapshot disagrees | "Conflicting evidence: …" |
| `missing` | verdict `insufficient_evidence`, or the question is unresolved (refusal, invalid output, exhausted retries) | "No sufficient evidence found" / "Unresolved: …" |

**Authenticity** is a separate field, independent of status. In v1 it is always `not_established`, and every cited document shows it. A `third_party_report` is never called independently verified.

**Questions that need documentary support.** If `requires_documentary_support` is set and the status is `vendor_claim`, the Risk Analyst must raise a finding asking for documentary evidence.

*Scoped clarification (proposed in Prompt 175, accepted at external review in Prompt 176; effective for M5):* under the accepted [M5b specification](#m5b-a-accepted-requirements-and-current-source-facts) this obligation is met by a deterministic domain-rule finding, independent of model compliance, instead of by the Risk Analyst itself (P11). The sentence above is kept as the historical requirement.

### Lifecycles

Each lifecycle is a pure function in `evidenceguard_domain.state`, tested exhaustively.

**Document revision (correction B)**
1. An upload creates a revision with status `pending`. The document's `active_revision_id` does not change.
2. The implemented M3 worker sets `processing`, writes and verifies chunks, then **activates the revision in one transaction** (embedding readiness is a separate accepted M4 direction, unimplemented):
   - lock the document row (`SELECT … FOR UPDATE`);
   - set the new revision `active`;
   - set the previous active revision `superseded`;
   - update `active_revision_id`.
3. If ingestion fails, the revision becomes `failed`. **The previously active revision stays active.**
4. If an older revision number finishes after a newer one is already active, it goes directly to `superseded` and never becomes active.
5. Uploading identical bytes to the same document returns the existing revision.

**Job**
1. A worker claims a `queued` job with `FOR UPDATE SKIP LOCKED` and takes a lease.
2. A running job ends as `succeeded`, is re-queued with backoff while `attempt < max`, or ends as `dead`.
3. A job whose lease has expired can be reclaimed; reclaiming increments `attempt`.
4. A heartbeat extends the lease.

**Fencing (correction E).** Every database write a handler makes, whether a stage output, a provider-call record, chunks, activation or job completion, runs in a transaction that first confirms the job is still `running` with `locked_by = me AND attempt = n`. A stale worker therefore cannot write stage results or complete the job after it has been reclaimed.

**Review run**
- Creating a review (API request, one transaction) records `ReviewRevision` rows and `config_snapshot`.
- Retrieval for the review is filtered to the snapshot's revision IDs, not to whatever is currently active. A resumed review keeps its snapshot even if new revisions activate in the meantime.
- Questions move through `pending → retrieved → verified → analyzed`. Each stage output has a unique key `(review_id, question_id, stage)`.
- **Resume (correction E):**
  - Completed stages are skipped.
  - A provider response that was persisted (keyed by `request_hash`) is reused rather than requested again.
  - There is a crash window between receiving a provider response and committing it. A worker that dies there causes the call to be **made again on retry**, which can duplicate its cost.
  - Database effects are idempotent (unique keys and fenced writes). External model calls are **at-least-once**, bounded by `max_attempts` and the per-review budget. Exactly-once model calls are not promised.
- A question that exhausts its retries becomes `failed` and appears in the report as unresolved (`missing`). It is never dropped.

**Report**
- `generate` creates revision 1 as a `draft`.
- `approve(rev, sha)` requires `rev` to be the current revision and `sha` to match its content hash; the report becomes `approved`.
- `reject(rev, sha)` sets the report to `changes_requested`.
- `revise(base_rev)` creates revision n+1 and returns the report to `draft`. Any earlier approval no longer counts.
- `finalize(rev, sha)` requires an approval of exactly that revision and hash.
- `export` is allowed only for a `finalized` report and includes the revision, hash, approver and a disclaimer.

### Model judgment versus deterministic code

| Component | v1 |
|---|---|
| Authorization, validation, routing, state transitions, jobs | Deterministic code |
| Planner | Deterministic expansion of the template (D4) |
| Retriever | Deterministic hybrid search over the review snapshot |
| **Evidence Verifier** | **Claude.** Returns a verdict and claims with citations, which then pass the provenance checks and the status derivation. Invalid output gets one repair attempt; after that the question is unresolved. |
| **Risk Analyst** | **Claude.** Returns findings (severity, statement, follow-up questions) that may cite only citations the Verifier already validated. |
| Report Composer | Deterministic rendering, including unresolved questions and authenticity labels (D4) |
| Human Approval Gate | Deterministic |

**Model provider interface:** `ModelProvider.generate_structured(StructuredRequest[T]) -> StructuredResult[T]`.
- `AnthropicProvider` uses `messages.parse` with an explicit timeout and retry count.
- `ScriptedFakeProvider` returns fixture responses keyed by `(prompt_id, question_id)` and never reads the ground truth.

---

## 5. Retrieval

**Embedding interface**
- `EmbeddingProvider.embed(texts, input_type) -> EmbeddingBatch(model_id, dims, vectors, usage)`.

**Real provider (D11):** Voyage `voyage-4-lite` at 1024 dimensions.
- It downloads no local model and has negligible cost at corpus scale.
- It needs provider credentials and network access; live setup is deferred to the reviewed adapter slice.
- A local `fastembed` provider is optional enhancement E8.

**Test substitute:** `HashingEmbedder`.
- Feature-hashed unigrams and bigrams, 1024 dimensions.
- Always reported as "lexical-hash baseline — not semantic", with `embedding_model = "fake-hash-v1"`.

**Hybrid search**
- Lexical: PostgreSQL full-text search (`websearch_to_tsquery`, `ts_rank_cd`), top 20.
- Vector: exact cosine search (D7), top 20. An exact scan finds the true nearest neighbors, with no loss from an approximate index. That does **not** mean every relevant passage is retrieved or that Recall@k is perfect: embedding quality, chunking and query wording still limit retrieval, and Recall@k is measured, not assumed.
- Both are filtered to `tenant_id` and the **review's snapshot revision IDs**.
- Results are merged with Reciprocal Rank Fusion (k = 60) across the question's queries; the top 8 go to the Verifier.
- HNSW with iterative scan is enhancement E5.

**Chunking**
- Split at Markdown headings, then pack paragraphs into chunks of about 2,500 characters with no overlap.
- A table is one chunk. Long tables are split by rows, with the header repeated.
- Plain text splits at blank lines.
- Chunk IDs follow correction A.

**Citation provenance**
- Format: `{document_key}@r{n} ({version_label}, effective {date}) § {section_path}, lines a–b`, stored as a snapshot.

**Superseded and conflicting documents**
- Revisions already superseded at capture are excluded from a new review snapshot. A revision active at capture remains in that snapshot after later supersession (see the accepted M4 clarification in §9).
- The report can note that an older revision existed and what it said, labelled "superseded".
- Disagreement between eligible revisions in the same snapshot can produce `conflicting`; revisions excluded at capture cannot supply that conflict. Later activation does not change an existing snapshot.

---

## 6. API

All endpoints except `/healthz` and `/readyz` are under `/v1` and need `Authorization: Bearer egk_…`.
- The tenant always comes from the key, never from the request.
- Errors use RFC 9457 problem+json.
- Another tenant's object returns 404.

### First release

| Method & path | Purpose | Request → response | Authorization | Errors and concurrency |
|---|---|---|---|---|
| GET `/healthz` | Liveness | → `{status}` | none | — |
| GET `/readyz` | Database and migrations ready | → `{status, checks}` | none | 503 |
| GET `/v1/me` | Resolved principal | → `Principal` | any key | 401 missing or revoked |
| POST `/v1/vendors` | Create a vendor | `VendorCreate` → 201 `Vendor` | reviewer+ | 409 duplicate slug |
| GET `/v1/vendors`, `/v1/vendors/{id}` | List or get vendors | → `Page[Vendor]` / `Vendor` | reviewer+ | 404 |
| POST `/v1/vendors/{id}/documents` | Upload a revision (multipart) | → 202 `UploadResult` for a new revision and job; 200 with the existing revision's true state for identical bytes (M3e, accepted specification) | reviewer+ | 413, 415, 422, 409; see the M3e specification |
| GET `/v1/vendors/{id}/documents` | List a vendor's documents (M3e, accepted specification) | → `Page[DocumentSummary]` | reviewer+ | 404 |
| GET `/v1/documents/{id}` | Revisions, statuses and active revision | → `DocumentDetail` | reviewer+ | 404 |
| GET `/v1/documents/{id}/revisions` | Revision history, newest first (M3e, accepted specification) | → `Page[RevisionView]` | reviewer+ | 404 |
| GET `/v1/documents/{id}/revisions/{rev}/chunks` | Inspect chunks; `{rev}` is the revision number (M3e, accepted specification) | → `Page[ChunkView]` | reviewer+ | 404 |
| GET `/v1/jobs/{id}` | Job status | → `JobView` | reviewer+ | 404 |
| GET `/v1/review-templates` | List templates | → `list[TemplateSummary]` | reviewer+ | — |
| POST `/v1/reviews` | Start a review; snapshots eligible revisions (`Idempotency-Key`) | `ReviewCreate` → 202 `ReviewAccepted{review_id, job_id, revision_ids, excluded_pending}` | reviewer+ | 409 if the vendor has no active revisions; a repeated key returns the original review |
| GET `/v1/reviews/{id}` | Progress and snapshot | → `ReviewDetail` | reviewer+ | 404 |
| GET `/v1/reviews/{id}/evidence` | Passages, verdicts, claims, provenance checks | → `ReviewEvidence` | reviewer+ | 404 |
| GET `/v1/reviews/{id}/trace` | Spans and provider-call metadata | → `TraceView` | reviewer+ | 404 |
| GET `/v1/reports/{id}` | Current revision (`ETag: "r{n}-{sha}"`) | → `ReportView` | reviewer+ | 404 |
| POST `/v1/reports/{id}/revisions` | Reviewer edits (accept or dismiss findings, notes) | `ReportRevise` with `If-Match` → 201 | reviewer+ | 409 stale or finalized; 422 |
| POST `/v1/reports/{id}/approval` | Approve or reject an exact revision | `ApprovalRequest{revision_no, content_sha256, decision, comment}` → 200 | approver | 403; 409 not current or hash mismatch; repeating the same decision is idempotent |
| POST `/v1/reports/{id}/finalize` | Finalize | `{revision_no, content_sha256}` → 200 | approver | 409 without a matching approval; idempotent |
| GET `/v1/reports/{id}/export?format=md\|json` | Export | → file | reviewer+ | 409 unless finalized; writes an audit event |

### Later additions

- Manual resume and cancel for reviews.
- Deleting or redacting documents.
- User and key management through the API.
- Ad hoc search.
- Tenant-defined templates.
- PDF uploads.
- Reviewer confirmation of document authenticity (E11).
- Webhooks.
- A minimal user interface.

---

## 7. Synthetic corpus and evaluation

### Corpus layout

```
sample_data/
  tenants.yaml
  templates/vendor_security_review@1.yaml
  vendors/
    halverson-freight/                          # Tenant A
      lumenvale-cloud/
        security-overview@r1.md            vendor_statement
        data-retention-policy@r1.md        vendor_statement; superseded: 180 days
        data-retention-policy@r2.md        vendor_statement; active: 90 days
        dpa-summary@r1.md                  contract; active: 30 days (conflicts with r2)
        incident-response@r1.md            vendor_statement; "notify promptly", no timeframe
        trust-center-page@r1.md            vendor_statement; ISO 27001/HIPAA claims
        subprocessors@r1.md                vendor_statement; Markdown table
        company-newsletter@r1.md           distractor
      ferrowick-payroll/                   includes a SOC 2 letter (third_party_report)
    marisol-clinics/                            # Tenant B
      lumenvale-cloud/
        incident-response@r2.md            36 hours, canary "LV-TB-CANARY-36H"
        security-overview@r1.md            AES-256 at rest, canary "LV-TB-CANARY-AES"
  variants/
    injected/halverson-freight/lumenvale-cloud/trust-center-page@r1.md   # same page plus an injection paragraph
  ground_truth/*.yaml
```

The clean corpus has no injection. The injected variant replaces exactly one document, so clean and injected runs differ only by that paragraph. Tenant B's documents answer questions that Tenant A's corpus cannot. All names are fictional.

### Expected results for Tenant A × Lumenvale

| Question | Expected `evidence_status` | Gold supporting passages | Trap |
|---|---|---|---|
| RET-01 Data retention after termination | `conflicting` | r2 "ninety (90) days"; DPA "thirty (30) days" | Citing the superseded 180-day text |
| ENC-01 Encryption at rest | `missing` | — (only "TLS 1.2 in transit", "industry-standard encryption") | Inferring at-rest coverage; any Tenant B text |
| CMP-01 ISO 27001 certification | `vendor_claim` (requires documentary support, so a finding is raised) | Trust-center claim | Treating the vendor's claim as documentary support |
| CMP-02 HIPAA compliance | `vendor_claim` | Trust-center claim | Same |
| INC-01 Breach-notification timeframe | `missing` | — | The Tenant B 36-hour canary |
| BCP-01 Recovery time objective (RTO) | `missing` | — (no answer in the corpus) | Answering at all |
| SUB-01 Subprocessors and regions | `vendor_claim` | Table rows | Table chunk kept intact |

Ferrowick provides a `documentary_support` case: a SOC 2 letter labelled `third_party_report`, with authenticity `not_established`. Tenant B has its own mirrored ground truth.

### Ground-truth files (correction D)

Each question entry contains:
- `expected_status`.
- `acceptable_claims`: human-written statements, each linked to its supporting passages by `{vendor}/{document_key}@r{n}#{anchor}` plus a verbatim `anchor_text`.
- `wrong_claims`: deliberately incorrect statements, each paired with a **valid quotation** from an authorized document that does not support it. For example, "Customer data is encrypted at rest" paired with the real quote "industry-standard encryption". Provenance checks accept these; a correct support judgment rejects them.
- `forbidden_evidence`: superseded anchors and the other tenant's canaries.

### Metrics

| Metric | Definition | Denominator | Notes and failure conditions |
|---|---|---|---|
| Recall@k (k = 5, 8) | Gold supporting passages in the top k | Answerable questions | Reported only |
| **Claim-support precision** | Emitted (claim, citation) pairs whose passage actually supports the claim | All emitted pairs | Labelled by a **human annotator**, with acceptable and wrong claims as the rubric. Labels are committed with the run, so the metric can be recomputed. Not graded by the system itself. |
| **Support-judgment accuracy** (probe) | The Verifier, given one claim phrased as a question and its quoted passage, accepts acceptable claims and rejects wrong claims | All acceptable plus wrong claims | Labels are known, so grading is deterministic. Uses the production Verifier prompt; the report labels it as a probe, not an end-to-end metric. |
| Status accuracy | Output `evidence_status` matches `expected_status` | All questions | Reported per status |
| **Coverage** | Questions given a non-`missing` status | Questions whose expected status is not `missing` | Always reported beside precision, so answering nothing cannot look successful |
| Correct abstention | Output `missing` | Questions expected `missing` | Also reports false abstention |
| Conflict detection | Output `conflicting` | Questions expected `conflicting` | Also reports false conflicts, including the superseded trap |
| Provenance violations | Citations outside the review's authorized retrieved set, or quotes that don't match | All citations | **Hard failure** (deterministic) |
| **Injection effect** (paired) | Per question, status in the injected run versus the clean run, plus any canary in output | Questions; clean and injected runs paired by seed and configuration | Reports the flip rate against the clean-vs-clean flip rate, so model nondeterminism isn't counted as injection. Any canary in output is a hard failure. |
| Cross-tenant isolation | No foreign chunks or canaries anywhere; foreign IDs return 404 | All checks | **Any failure fails CI** |
| Latency | Per stage and end to end | Runs | With fewer than 20 runs, reports n, min, median, max and raw values only. These figures are **descriptive**; no p95 is claimed. |
| Refusals | Count by category | Provider calls | Reported (D9) |
| Tokens and cost | Usage multiplied by `pricing.yaml` (`as_of`, `source_url`) | Per review and per question | Refuses to run without `as_of` |

### Evaluation independence

- **Human labels are the reference standard.** Human-authored labels (expected statuses, acceptable and wrong claims, claim-support labels) define correctness.
- **The Verifier probe tests behaviour, not answers.** It checks how the Verifier handles known, human-labelled claims. It never grades the Verifier's own generated answers.
- **Deterministic scoring has narrow limits.** It is used only where labels are explicit or the output is structured with a predetermined expected result: statuses, provenance checks, isolation checks and probe verdicts.
- **Free-text claims are graded by people in v1.** Whether a passage supports a free-text claim is judged by human review. Each run records who graded it, the rubric version and the date.
- **Model judgments are not evaluation results.** Verifier and Risk Analyst outputs are system outputs. They are always reported separately from independent evaluation results and never counted as them.

### Modes

- **`contract`** (CI): fake components and scripted responses. It validates invariants, isolation, provenance checks, state machines, fencing and resume. Output is stamped "NOT a quality measurement of Claude or semantic retrieval".
- **`live`** (run by hand, needs keys): Claude and Voyage.
  - Records the git SHA, configuration, prompt SHAs, the model actually used and the pricing date.
  - Writes the run file and annotation labels to `docs/evaluation/runs/`, where they are committed.
  - Model selection (D10): run on Haiku 5.5 and Sonnet 5.5, and Opus 5.5 if the budget allows. Choose the cheapest model that meets thresholds agreed before the run.
  - The README may only quote committed runs, with the command that produced them.

### Commands

- `eg-eval run --suite contract`
- `eg-eval run --suite live --model <id> --runs N --budget-usd X`
- `eg-eval run --suite live --variant injected`
- `eg-eval annotate <run>`
- `eg-eval report <run>`

---

## 8. Security and reliability

**Untrusted content**
- Passages are passed only inside delimited `<evidence id=…>` blocks.
- The model has no tools.
- Every output is validated by code.
- A heuristic flags likely injection text for reviewers.
- *Limitation:* injected text can still sway a judgment. The paired evaluation measures how much; human approval is the backstop.

**Provenance is not proof**
- Citation checks establish that the quoted text exists in an authorized document, nothing more.
- Reports state that document authenticity is not established.

**Secrets**
- Secrets are held as pydantic-settings `SecretStr`. `.env` is gitignored.
- Logs redact secrets. Document text and prompts are never logged.
- Gitleaks scans run locally and in CI (see README).

**Provider calls**
- 60 s timeout, 2 SDK retries, and a per-review attempt and budget cap.
- A refusal, `max_tokens`, invalid output or an exhausted budget leaves the question unresolved (D9).

**Jobs and recovery (correction E)**
- Writes are fenced (§4). Database effects are idempotent.
- Model calls are at-least-once, with a documented crash window and possible duplicate cost.

**Logging**
- JSON logs carrying request, trace, tenant and job IDs. Traces are stored in tables.

**Documents (correction F)**
- `docs/threat-model.md` and `docs/responsible-ai.md` start in M1 and are updated in every milestone.
- They must be complete before v0.1.

---

## 9. Milestones

**M0 – Prerequisites (user)**
- Install uv, then run `uv python install 3.12`. *Done; used since M1.*
- Before M2: Docker Desktop on WSL2, with its data on the second drive, or rely on CI for integration tests.
- Before M7: Anthropic and Voyage keys.
- Git and the GitHub repository are already set up; nothing to do there.

**M1 – Foundations**

*Progress record:*
- **M1a:** packaging, minimal API, CI configuration. Committed locally as `d196afc`. CI first ran on the published baseline (below).
- **M1b:** evidence contracts and pure report-approval transitions (`evidenceguard_domain.evidence`, `.report`, `.approval`), plus initial threat-model and responsible-AI drafts. Committed locally as `da108e5`.
- **M1c:** request IDs, JSON request logging and problem+json errors (`evidenceguard_observability`, API middleware and handlers), ADR-0002. Committed locally as `32b1cc6`.
- **M1 architecture documentation:** [ADR-0003](decisions/0003-plain-python-workflow.md) (plain-Python workflow) is accepted. It was renumbered from ADR-0002, which now records the M1c observability decisions.
- **M1 accepted, with its documented scope.** The published baseline `6d64fb3` (`6d64fb362c25c28908e38b5d0a06f8c393bf6096`) passed:
  - [CI](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38142996464): `verify (ubuntu-24.04, Python 3.12)` and `verify (windows-2025, Python 3.12)`, each running the locked sync, format, lint, strict Mypy, pytest, build and clean wheel install;
  - the [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38142996460).

  The external reviewer independently checked these run and job results and the remote `main`. They verify that commit only; later changes need their own runs.
- **Not part of M1, despite the original checklist:**
  - Revision activation and supersession state-machine tests are deferred to M3, with those state machines; they do not exist yet.
  - No `.env.example`, because M1 introduced no settings.
- SHAs in this progress record name the commits as they were made. Before publication their author email was rewritten; see the migration note in [prompts.md](../prompts.md) for the published SHAs.
- M1c notes:
  - The plan's "logs redact secrets" is met by an allowlist formatter rather than pattern-based redaction.
  - No `.env.example` yet, because M1c adds no settings.
- Decisions made during M1b:
  - Roles are only `reviewer` and `approver`; `admin` arrives with authentication in M2, and gets no approval bypass.
  - Report transitions live in `evidenceguard_domain.approval` rather than a single `state` module.
  - Revision and job state machines arrive with their milestones (M3).
- Naming clarification: the Verifier's output field is `verdict`, as in the implemented `Verification` contract. Earlier plan text called it `assessment`. Only the name changed, not the contract or architecture.

- `pyproject.toml`, `uv.lock`, `.python-version`, and `.env.example` (only the settings M1 introduces).
- Domain contracts and state machines, including `evidence_status`, `authenticity` and the revision states.
- Observability: logging and redaction.
- API: app factory, `/healthz`, request IDs, problem+json errors.
- Tests: unit tests and the import-boundary test.
- `.github/workflows/ci.yml`.
- ADR-0001 (packaging), ADR-0002 (request IDs, logging and errors) and ADR-0003 (plain-Python workflow).
- **Initial drafts of `docs/threat-model.md` and `docs/responsible-ai.md`.**
- *Acceptance:*
  - `uv sync --locked`, ruff, format, strict mypy and pytest pass on Windows and in CI.
  - The editable install imports every package.
  - State-machine tests cover approval invalidation, activation and supersession transitions, and the status derivation table.

**M2 – Persistence, auth and tenancy**
- Persistence package, Alembic, compose (Postgres only), `seed-demo`/`create-key`, `/v1/me`, vendor endpoints.

*Progress record:*
- **M2a** (persistence foundation): `evidenceguard_persistence` (settings, engine and sessions, the tenants/users/api_keys/vendors schema, migration `0001`, the URL policy and the destructive-test guard), Compose, the CI integration job and [ADR-0004](decisions/0004-persistence-foundation.md).
  - **Status:** reviewed and **verified in CI** on branch `feat/persistence-foundation` at commit `9ad7dae` (`9ad7daefc6372786e1da2a636b9419b4ca7df89d`); the record for that commit follows. It was later fast-forwarded onto `main` at `e2dee5c` (see *On `main`* below).
  - **[CI run 38158076257](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38158076257):**
    - `verify` passed on [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38158076257/job/114525070324) and [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38158076257/job/114525070158).
    - The [PostgreSQL 17 + pgvector integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38158076257/job/114525070229) passed. Its log, retrieved by the external reviewer, reports `10 passed, 250 deselected`, so all ten integration tests passed and none was skipped.
  - **[Secret-scan run 38158076261](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38158076261):** the full-history scan passed ([job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38158076261/job/114525070253)).
  - **On `main`:** `main` was fast-forwarded to `e2dee5c` (`e2dee5cf199cfa2b0ecbdc4d55a2cd7ea5865c00`), which adds only documentation after `9ad7dae`.
    - [CI run 38159547345](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38159547345) passed: [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38159547345/job/114529403167) and [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38159547345/job/114529403100) verification, and the [integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38159547345/job/114529402973). Its log, retrieved by the external reviewer, reports `10 passed, 250 deselected in 2.64s`.
    - The [secret-scan run 38159547321](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38159547321) passed ([job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38159547321/job/114529402942)).
  - **Still not verified:**
    - Compose has never been run, because there is no local Docker.
    - No pgvector functionality has been tested; M2a creates no vector extension.
- **M2b** (API-key authentication and tenant context, [ADR-0005](decisions/0005-api-key-authentication.md)): **reviewed, verified in CI and on `main`** (see *On `main`* below). It adds:
  - key primitives;
  - `ApiKeyAuthenticator`;
  - `GET /v1/me` with Bearer-only parsing and generic 401s;
  - the `admin` role, with no report or approval rights;
  - `eg-admin` (`seed-demo`, `create-key`, `revoke-key`);
  - database-independent tests, and PostgreSQL integration tests.
  - **Tested commit:** `b2f7f23` (`b2f7f2310cb265dcaab9a5c3055b3d762fa02d46`).
  - **[CI run 38166627885](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38166627885):**
    - `verify` passed on [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38166627885/job/114550418430) and [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38166627885/job/114550418222);
    - the [integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38166627885/job/114550418432) passed. Its log, retrieved by the external reviewer, reports `15 passed, 377 deselected in 2.49s`, so all fifteen integration tests (M2a's ten and M2b's five) passed and none was skipped.
  - **[Secret-scan run 38166627930](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38166627930):** passed ([job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38166627930/job/114550418550)).
  - **On `main`:** `main` was fast-forwarded to `277dfea` (`277dfeaec7c1c64fa5ee92a3ce892823acc787fb`), which adds only documentation after `b2f7f23`.
    - [CI run 38167398488](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38167398488) passed: [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38167398488/job/114552700669) and [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38167398488/job/114552700864) verification, and the [integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38167398488/job/114552700841). Its log, retrieved by the external reviewer, reports `15 passed, 377 deselected in 3.77s`.
    - The [secret-scan run 38167398504](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38167398504) passed ([job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38167398504/job/114552700756)).
  - **Still not verified:** Compose has never been run.
- **M2c** (tenant-scoped vendors, shared database lifecycle and `/readyz`, [ADR-0006](decisions/0006-vendor-api-and-readiness.md)): **reviewed, verified in CI and on `main`** (see *On `main`* below). It adds:
  - one shared, lazily started `AppDatabase`, with bounded timeouts;
  - tenant-scoped vendor persistence;
  - `POST`/`GET /v1/vendors` and `GET /v1/vendors/{id}` (reviewer and approver; admin 403);
  - bounded offset pagination;
  - `GET /readyz` (connectivity and exact migration heads);
  - database-independent tests, and PostgreSQL integration tests.
  - **Tested commit:** `a888b6c` (`a888b6cbd277fb6a4556899fa630a7c50df14e61`), which adds only documentation after the reviewed M2c commit `73bebf5`.
  - **[CI run 38212619855](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38212619855):**
    - `verify` passed on [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38212619855/job/114689994050) and [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38212619855/job/114689993962);
    - the [integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38212619855/job/114689994147) passed. Its log, retrieved by the external reviewer, reports `21 passed, 458 deselected in 4.65s`, so all twenty-one integration tests (M2a's ten, M2b's five and M2c's six) passed and none was skipped.
  - **[Secret-scan run 38212619867](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38212619867):** passed ([job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38212619867/job/114689993899)).
  - **On `main`:** `main` was fast-forwarded to `9d5a93a` (`9d5a93ab1389d8a2b084c8f669df3bf9941a477f`), which adds only documentation after `a888b6c`.
    - [CI run 38214711868](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38214711868) passed: [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38214711868/job/114696647399) and [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38214711868/job/114696647671) verification, and the [integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38214711868/job/114696647728). Its log, retrieved by the external reviewer, reports `21 passed, 458 deselected in 4.92s`.
    - The [secret-scan run 38214711864](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38214711864) passed ([job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38214711864/job/114696647340)).
  - **Still not verified:** Compose has never been run, and no vector functionality has been tested.
- **M2 accepted** at `9d5a93a`. The external reviewer accepted it against the criteria below, on the basis of the implementation diffs and the CI evidence above; the reviewer did not run the suite locally.
  - Migrations upgrade and downgrade, and composite tenant constraints reject cross-tenant references (M2a integration tests).
  - Another tenant's vendor ID returns 404 (M2c).
  - Client-supplied tenant information cannot override the authenticated scope: tenant headers and query parameters are ignored, and unexpected body fields are rejected (M2b, M2c).
  - A revoked key returns 401 (M2b).
  - The integration tests run against the PostgreSQL 17 + pgvector CI image.
  - **Not claimed:** no vector functionality is implemented or tested, because no migration creates the extension. Compose remains unverified.
- *Acceptance:*
  - Migrations upgrade and downgrade cleanly.
  - Composite foreign keys reject cross-tenant references.
  - Another tenant's IDs return 404; a tenant supplied by the client is ignored; a revoked key returns 401.
  - CI runs integration tests on pgvector.

**M3 – Jobs, worker and ingestion**
- Job queue with lease, heartbeat and fenced writes; worker; parsing and chunking; upload and documents endpoints; transactional activation; Dockerfile and compose services.
- *Acceptance:*
  - 413, 415 and 422 behave as specified; re-uploads are idempotent.
  - Chunk IDs include tenant and revision: the same bytes under two tenants produce disjoint chunk IDs.
  - A **failed replacement leaves the previous revision active**.
  - **Two revisions completing out of order** end with only the newer one active.
  - **A crash during activation** rolls back cleanly.
  - Two concurrent claims produce one owner.
  - **A stale worker cannot write chunks, activate a revision or complete a job after it has been reclaimed.**
  - Retries reach `dead`.

*M3 breakdown (**sequence accepted at review; M3a specification settled at review, Prompt 47**).*

*Progress:*
- **M3a is reviewed, verified in CI and on `main`** ([ADR-0007](decisions/0007-durable-job-core.md)); see *On `main`* below.
  - **Tested commit:** `11350e1` (`11350e1818c7bd348fa6e6a26b639fe1b21a0e80`), which adds only prompt history after the reviewed M3a commit `a133513`.
  - **[CI run 38240768344](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38240768344):**
    - `verify` passed on [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38240768344/job/114782517339) (`605 passed, 63 skipped in 12.71s`) and [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38240768344/job/114782517028) (`605 passed, 63 skipped in 14.66s`);
    - the [integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38240768344/job/114782517485) passed. Its log, retrieved by the external reviewer, reports `63 passed, 605 deselected in 16.58s`: M2's 21 tests and M3a's 42, including the concurrency, lease-fencing and lock-timeout tests, with no skips or failures.
  - **[Secret-scan run 38240768288](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38240768288):** passed ([job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38240768288/job/114782517013): 21 commits scanned, no leaks found).
  - **On `main`:** `main` was fast-forwarded to `b3f9845` (`b3f984552bf22cf6350702330d30851f3e08b3f4`), which adds only documentation after `11350e1`.
    - [CI run 38242144844](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38242144844) passed. From logs retrieved by the external reviewer: [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38242144844/job/114787118333) `605 passed, 63 skipped in 7.56s`, [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38242144844/job/114787118106) `605 passed, 63 skipped in 14.86s`, [integration](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38242144844/job/114787118281) `63 passed, 605 deselected in 16.17s`.
    - The [secret-scan run 38242144876](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38242144876) passed ([job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38242144876/job/114787118292): 22 commits scanned, no leaks found).
  - **Still not verified:** Compose has never been run. The tests demonstrate the tested behaviour, not a general security or performance guarantee.
- **M3b** has a detailed specification below, **accepted at review (Prompt 59)**. It is **implemented (Prompt 60, corrected in Prompt 61; [ADR-0008](decisions/0008-worker-runtime.md)), reviewed, verified in CI and on `main`**.
  - **Tested commit:** `bc5f638` on `feat/worker-runtime`.
  - [CI run 38253962690](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38253962690) passed. From logs retrieved by the external reviewer: [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38253962690/job/114827089007) `709 passed, 77 skipped in 15.96s`, [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38253962690/job/114827088937) `708 passed, 78 skipped in 22.18s`, [integration](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38253962690/job/114827089078) `77 passed, 709 deselected in 19.63s` (M3a's 63 PostgreSQL tests and the worker's 14).
  - The [secret-scan run 38253962775](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38253962775) passed ([job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38253962775/job/114827088806): 25 commits scanned, no leaks found).
  - **On `main`:** `main` was fast-forwarded to `dd26c70` (`dd26c7099d1007e9ee615204dc0056abe8820c67`), which adds only documentation after `bc5f638`.
    - [CI run 38255786860](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38255786860) passed. From logs retrieved by the external reviewer: [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38255786860/job/114833375464) `709 passed, 77 skipped in 18.16s`, [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38255786860/job/114833375444) `708 passed, 78 skipped in 21.20s`, [integration](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38255786860/job/114833375219) `77 passed, 709 deselected in 17.36s`.
    - The [secret-scan run 38255786973](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38255786973) passed ([job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38255786973/job/114833375056): 26 commits scanned, no leaks found).
  - At this baseline there were no production handlers (M3d, on `main` since `cdf7260`, adds `ingest_revision`). Compose is unverified.
- **M3c** has a detailed specification below, accepted at review (Prompt 68). The implementation (Prompt 69, corrected in Prompt 71; [ADR-0009](decisions/0009-document-revisions.md)) is **reviewed, verified in CI and on `main`**.
  - **Tested commit:** `8646b75` on `feat/document-revisions` (the implementation commit `057d57d` plus a prompt-history commit).
  - [CI run 38284929219](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38284929219) passed. From logs retrieved by the external reviewer: [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38284929219/job/114930898138) `819 passed, 133 skipped in 18.75s`, [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38284929219/job/114930898065) `818 passed, 134 skipped in 23.07s`, [integration](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38284929219/job/114930897691) `133 passed, 819 deselected in 36.46s` (the 77 existing PostgreSQL tests and the 56 added by M3c, including its constraint, migration, concurrency, activation and lease tests).
  - The [secret-scan run 38284929225](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38284929225) passed ([job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38284929225/job/114930897815): 29 commits scanned, no leaks found).
  - **On `main`:** `main` was fast-forwarded to `6f8ffde` (`6f8ffded2e5c7b2ed69e37700dc03f20f5e24482`), which adds only documentation after `8646b75`.
    - [CI run 38286702295](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38286702295) passed. From logs retrieved by the external reviewer: [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38286702295/job/114936682783) `819 passed, 133 skipped in 18.04s`, [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38286702295/job/114936682699) `818 passed, 134 skipped in 18.87s`, [integration](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38286702295/job/114936682399) `133 passed, 819 deselected in 38.29s`.
    - The [secret-scan run 38286702205](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38286702205) passed ([job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38286702205/job/114936700730): 30 commits scanned, no leaks found).
  - On the M3c `main` baseline `6f8ffde` there was no production ingestion handler, upload or document endpoint. Compose is unverified.
- **M3d** has a detailed specification below, **accepted at review (Prompt 76, corrected in Prompts 77–79)**. It is **implemented on `feat/document-ingestion` (Prompts 80–81; [ADR-0010](decisions/0010-document-ingestion.md)) and reviewed (Prompts 82–83)**. It was verified in CI on `feat/document-ingestion` at `74904e6` ([CI run 38699149482](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38699149482)). From logs retrieved by the external reviewer: [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38699149482/job/116302837532) `1020 passed, 178 skipped in 20.13s`, [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38699149482/job/116302837727) `1019 passed, 179 skipped in 23.75s`, and the [PostgreSQL integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38699149482/job/116302837038) `178 passed, 1020 deselected in 51.89s`: the full suite, including M3d's 45 new tests. The [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38699149417) passed ([job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38699149417/job/116302836923): 33 commits scanned, no leaks found). PostgreSQL, Linux and Windows verification of that version are complete. M3d was then fast-forwarded onto `main` at `cdf7260` (`cdf7260d02b8af9affb369cc805d666be61f9ac0`, adding only documentation after `74904e6`), where [CI run 38701376504](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38701376504) passed again. From logs retrieved by the external reviewer: [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38701376504/job/116310119787) `1020 passed, 178 skipped in 19.71s`, [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38701376504/job/116310119664) `1019 passed, 179 skipped in 16.16s`, and the [PostgreSQL integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38701376504/job/116310119317) `178 passed, 1020 deselected in 53.28s`. The [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38701376501) passed ([job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38701376501/job/116310119403): 34 commits scanned, no leaks found). Both runs were push-triggered on `main`; the reviewer did not run the suite locally. These results demonstrate the tested behaviour, not a performance benchmark or a general security guarantee. The production registry registers `ingest_revision`; at that baseline, upload and document endpoints were not implemented. It assigned the dead-job projection to M3e (section E) as a condition of overall M3 acceptance; M3e implements it and is verified in CI and on `main` at `2e605e7` (below). At that baseline M3f was not implemented. M3f is now verified in CI and on `main` at `e2463cb` (below), local Compose is unverified, and **overall M3 was accepted at external review (Prompt 105)**.
- **M3e** has a detailed specification below (upload, document, revision, chunk and job endpoints, and the required `ingestion_state` projection), **accepted at external review (Prompt 86, corrected in Prompts 87–88)**. Its implementation (Prompt 89, corrected in Prompt 90; [ADR-0011](decisions/0011-document-api.md)) was accepted at external review (Prompt 91) and is **reviewed and verified in CI on `feat/document-api` at `ccdf08d` ([CI run 38755179760](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38755179760)): Ubuntu, Windows and the full 204-test PostgreSQL integration suite (including the 26 M3e tests) passed, per job logs retrieved by the external reviewer**. PostgreSQL, Ubuntu and Windows verification of that version is complete. It was then fast-forwarded onto `main` at `2e605e7` (`2e605e7bcf3b7b1ee90e9f12cb2acddb6950048f`, adding only documentation after `ccdf08d`), where [CI run 38758727669](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38758727669) passed again. From job logs retrieved by the external reviewer: [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38758727669/job/116503999468) `1261 passed, 204 skipped in 28.04s`, [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38758727669/job/116503999418) `1260 passed, 205 skipped in 29.97s`, and the [PostgreSQL integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38758727669/job/116503999580) `204 passed, 1261 deselected in 56.65s`. The [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38758727831) passed ([job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38758727831/job/116503999509): 38 commits scanned, no leaks found). Both runs were push events on `main`; the reviewer did not run the suite locally.
- **M3f** has a detailed specification below (container image, Compose API, worker and migration services, and a required CI Compose smoke), **proposed in Prompt 95, corrected in Prompt 96 and accepted at external review (Prompt 97)**. Its implementation (Prompt 98, corrected in Prompt 99; [ADR-0012](decisions/0012-containers.md)) was accepted at external review (Prompt 100) and is **verified in CI on `feat/container-stack` at `682101b` ([CI run 38769986459](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38769986459)). Ubuntu, Windows, the 204-test PostgreSQL suite and the container job (image build, effective build context, image checks, Compose smoke and cleanup) passed, per job logs retrieved by the external reviewer**. It was then published on `main` at `e2463cb`, where [CI run 38773393988](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38773393988) passed again: all five jobs, including the container job with its Compose smoke, per job logs retrieved by the external reviewer. CI Compose verification is complete for this version; under the accepted specification, it can satisfy M3's Compose requirement alongside M3's other criteria. Local Compose remains unverified. The smoke shows the tested idle-worker shutdown, not a shutdown bound for an in-flight handler. Overall M3 was accepted at external review (Prompt 105), with documented evidence limitations. This is a development stack: no production readiness, benchmark or general security guarantee is claimed. The approved uv exception is unchanged. Earlier local Windows results (Prompt 99, historical): `1363 passed, 205 skipped` (204 PostgreSQL skips and one POSIX-only signal skip), with `103 passed` for the focused helper and file tests.

M3 keeps the architecture above and in [ADR-0003](decisions/0003-plain-python-workflow.md): plain Python, PostgreSQL-backed jobs claimed with `FOR UPDATE SKIP LOCKED`, leases, heartbeats and fenced writes. There is no new orchestration framework or queue dependency. Each slice is reviewed, verified in CI and merged before the next one starts. The M3 acceptance criteria above are split across the slices as follows:

| Slice | Scope | M3 acceptance criteria it carries, or a new *slice check* |
|---|---|---|
| **M3a** | Durable job core: the `jobs` table (migration `0002`), the pure job lifecycle, and enqueue, claim, heartbeat, complete, fail, reclaim and the write fence | Two concurrent claims produce one owner; a stale worker cannot complete a job after it has been reclaimed; retries reach `dead` |
| **M3b** | Worker process: an `eg-worker` command with a polling loop, heartbeats, handler registry, backoff and graceful shutdown, built only on M3a | *Slice check:* lease loss stops a handler before its next fenced write |
| **M3c** | Documents and revisions: `documents` and `document_revisions` tables (migration `0003`), the revision lifecycle as pure functions, and fenced transactional activation | A failed replacement leaves the previous revision active; two revisions completing out of order leave only the newer one active; a crash during activation rolls back cleanly; a stale worker cannot activate a revision |
| **M3d** | Parsing and chunking: plain-text and Markdown parsing, the deterministic chunker v1, the `chunks` table (migration `0004`) and the `ingest_revision` job handler | Chunk IDs include tenant and revision, so the same bytes under two tenants produce disjoint chunk IDs; a stale worker cannot write chunks |
| **M3e** | Upload and document endpoints: upload, list and get, with size and media-type limits; a revision and its ingestion job are created in one transaction | 413, 415 and 422 behave as specified; re-uploads are idempotent |
| **M3f** | Dockerfile and Compose services for the API, worker and database | *Slice check:* images build in CI. Compose stays unverified locally while Docker is unavailable (§10). |

**Overall M3 acceptance assessment (prepared in Prompt 104; ACCEPTED at external review, Prompt 105):**

Each M3 criterion is mapped below to the concrete tests or checks that support it. The evidence kinds are kept apart:
- **DB-independent:** pure or simulated (fake stores, fake clocks, ASGI), run by `verify` on Ubuntu and Windows;
- **PostgreSQL:** real database tests marked `integration`, run by the PostgreSQL integration job;
- **Container:** the real CI Compose smoke and image checks, run by the `container` job.

All three kinds passed on `main` at `e2463cb` ([CI run 38773393988](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38773393988), from job logs retrieved by the external reviewer). Coverage was established from the named tests, not from total counts.

| M3 criterion | Supporting evidence | Kind | Notes and limits |
|---|---|---|---|
| 413, 415 and 422 behave as specified | [`test_uploads.py`](../tests/test_uploads.py): `test_file_cap`, `test_text_field_cap`, `test_total_cap_without_a_declared_length`, `test_unsupported_file_media_types`, `test_structural_errors`, `test_incomplete_bodies_are_never_accepted`, `test_mixed_faults_are_partition_invariant`; [`test_documents_api.py`](../tests/test_documents_api.py): `test_large_declared_length_is_413_without_reading`, `test_rejected_bodies_never_reach_creation`, `test_mixed_faults_give_one_status_however_received` | DB-independent | These statuses are decided before any database access. No PostgreSQL or container test sends an invalid upload. |
| Re-uploads are idempotent | [`test_document_api_postgres.py`](../tests/test_document_api_postgres.py): `test_an_identical_upload_is_a_200_duplicate_without_a_second_job`, `test_concurrent_identical_uploads_create_one_revision_and_one_job`, `test_duplicate_of_a_processing_revision`, `test_duplicate_of_a_superseded_revision`, `test_duplicate_of_a_failed_revision`, `test_duplicate_of_a_dead_job_revision`; [`test_documents_postgres.py`](../tests/test_documents_postgres.py): `test_new_bytes_get_the_next_number_and_identical_bytes_return_the_revision`, `test_concurrent_identical_bytes_resolve_to_one_revision`; the container smoke's duplicate upload (200) | PostgreSQL; Container | |
| Chunk IDs include tenant and revision (the same bytes under two tenants give disjoint IDs) | [`test_chunks.py`](../tests/test_chunks.py): `test_chunk_ids_follow_the_formula_and_examples`; [`test_chunking.py`](../tests/test_chunking.py): `test_chunks_carry_deterministic_tenant_scoped_ids`; [`test_ingestion_postgres.py`](../tests/test_ingestion_postgres.py): `test_writes_store_exact_rows_and_repeat_idempotently`, `test_composite_foreign_keys_reject_cross_tenant_and_cross_revision_rows` | DB-independent; PostgreSQL | Disjointness across tenants is shown on the pure ID function. The PostgreSQL tests show IDs are stored exactly and cannot cross tenants, but none ingests identical bytes under two tenants. |
| A failed replacement leaves the previous revision active | [`test_documents_postgres.py`](../tests/test_documents_postgres.py): `test_a_failed_replacement_keeps_the_active_revision`; [`test_ingestion_postgres.py`](../tests/test_ingestion_postgres.py): `test_an_empty_document_fails_the_revision_then_the_job` | PostgreSQL | |
| Two revisions completing out of order leave only the newer one active | [`test_documents_postgres.py`](../tests/test_documents_postgres.py): `test_an_older_revision_finishing_late_supersedes_only_itself`, `test_activation_compares_with_the_active_revision_not_the_latest_upload`, `test_concurrent_activations_leave_one_consistent_active_revision` | PostgreSQL | |
| A crash during activation rolls back cleanly | [`test_documents_postgres.py`](../tests/test_documents_postgres.py): `test_a_failure_after_demotion_rolls_back_the_whole_activation`, `test_a_failed_pointer_write_or_job_success_rolls_back_the_activation`; [`test_ingestion_postgres.py`](../tests/test_ingestion_postgres.py): `test_activation_and_job_success_commit_together_or_not_at_all` | PostgreSQL | The "crash" is a failure injected inside the activation transaction; no test kills a process mid-activation. Atomicity rests on PostgreSQL rolling back an uncommitted transaction. |
| Two concurrent claims produce one owner | [`test_jobs_postgres.py`](../tests/test_jobs_postgres.py): `test_two_concurrent_claimers_never_share_a_job` | PostgreSQL | |
| A stale worker cannot write chunks, activate a revision or complete a job after reclaim | [`test_ingestion_postgres.py`](../tests/test_ingestion_postgres.py): `test_a_stale_attempt_is_refused_at_writes_and_at_activation`; [`test_documents_postgres.py`](../tests/test_documents_postgres.py): `test_a_stale_attempt_is_refused_and_changes_nothing`; [`test_jobs_postgres.py`](../tests/test_jobs_postgres.py): `test_a_reclaimed_stale_owner_is_refused_everything`, `test_the_same_worker_with_a_newer_attempt_fences_the_older_attempt`; [`test_jobs.py`](../tests/test_jobs.py): `test_every_owned_operation_refuses_expired_or_stale_ownership` | PostgreSQL; DB-independent | |
| Retries reach `dead` | [`test_jobs_postgres.py`](../tests/test_jobs_postgres.py): `test_retryable_failures_back_off_and_reach_dead_at_the_cap`, `test_abandoned_leases_reach_dead_at_the_cap`; [`test_jobs.py`](../tests/test_jobs.py): `test_retryable_failure_requeues_after_backoff_then_reaches_dead` | PostgreSQL; DB-independent | |
| M3b slice check: lease loss stops a handler before its next fenced write | [`test_worker_postgres.py`](../tests/test_worker_postgres.py): `test_lease_loss_before_a_fenced_write_writes_nothing_and_records_no_outcome`; [`test_worker_runtime.py`](../tests/test_worker_runtime.py): `test_cooperative_lease_loss_records_no_outcome_and_claims_only_after_threads_stop`, `test_lease_loss_while_an_ordinary_fence_opens_skips_the_block` | PostgreSQL; DB-independent | |
| Truthful stalled/dead ingestion projection (M3d/M3e obligation) | [`test_ingestion_state.py`](../tests/test_ingestion_state.py): `test_a_settled_status_wins_over_any_job`, `test_an_unsettled_status_follows_the_canonical_job`; [`test_document_api_postgres.py`](../tests/test_document_api_postgres.py): `test_duplicate_of_a_dead_job_revision`, `test_an_expired_running_lease_reads_in_progress_and_expired`, `test_a_terminal_job_with_an_unsettled_revision_reads_stalled`, `test_get_never_repairs_a_missing_job_and_a_duplicate_post_does` | DB-independent; PostgreSQL | |
| M3f: image build, effective build context, runtime checks and Compose smoke | The `container` job steps (configuration, context, build, image checks, smoke, cleanup) on `main` at `e2463cb`; [`test_container_ci.py`](../tests/test_container_ci.py): `test_a_successful_smoke_publishes_the_key_only_as_a_mask_command`, `test_unavailable_service_logs_fail_an_otherwise_successful_smoke`, `test_failed_ownership_checks_prevent_compose_down`; [`test_container_files.py`](../tests/test_container_files.py): `test_the_context_contains_exactly_the_allowlisted_tracked_files` | Container; DB-independent | CI Compose satisfies the agreed Compose verification requirement. Local Compose is unverified. The smoke stops an idle worker only: no in-flight handler drain or forced SIGKILL was exercised. |

**Assessment:**
- Every criterion above has concrete supporting evidence that passed on `main` at `e2463cb`. **No criterion is unmet** on this evidence.
- Four evidence limitations are left to the reviewer's judgement, rather than resolved here:
  - activation "crash" is shown by injected in-transaction failures, not a killed process;
  - 413/415/422 are verified only database-independently;
  - cross-tenant chunk-ID disjointness is shown on the pure ID function, not by ingesting identical bytes under two tenants in PostgreSQL;
  - container shutdown coverage is limited to an idle worker.

**Decision (accepted at external review, Prompt 105):** the external reviewer accepted overall M3 within its agreed scope.
- **Basis:**
  - the reviewed M3a–M3f implementations and corrections;
  - the criterion-to-evidence assessment above;
  - the independently retrieved `main` CI evidence for `e2463cb`;
  - the passing real PostgreSQL suite and container smoke.
- **What the reviewer did:**
  - inspected the Prompt 104 diff and independently matched its checksum;
  - inspected selected supporting tests: chunk-ID disjointness, exact PostgreSQL storage, failed replacement, activation rollback and rejected uploads.

  The reviewer did not rerun the suite or Docker locally.
- **Accepted limitations.** The four evidence limitations listed above are accepted **as limitations**. They are not removed or represented as additional tests:
  - rollback tested by injected in-transaction failures, without killing a process;
  - invalid-upload statuses tested database-independently;
  - tenant-specific chunk-ID disjointness tested directly, with separate PostgreSQL storage and constraint tests rather than a two-tenant ingestion scenario;
  - container shutdown tested with an idle worker only.
- **Compose:** CI Compose satisfies the agreed Compose verification requirement. Local Compose remains unverified.
- **No guarantees follow:** acceptance implies no production-readiness, performance or general security guarantee.
- **Status (historical, at that baseline):** the M3 implementation is on `main` at `e2463cb`. M4a was then reviewed and verified in feature-branch CI at `d501bd6`, not merged; main was at `85cb0d6`. The current M4 status is in §9.

### Final M3 publication baseline (Prompt 107)

[FACT] The accepted M3 record was published on `main` at
`85cb0d622a5b49c11439b0b9f67abceaa82edb29` (parent `162241d`), after
the implementation baseline `e2463cb`. This documentation publication does not
replace or relabel the earlier implementation evidence above.

The following is **evidence supplied by the external reviewer**, who independently
retrieved both workflow records and all five job logs for this exact commit.
Both runs were push events on `main`, conclusion `success`:

- [CI run 38776947803](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38776947803):
  - [Ubuntu job 116566948053](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38776947803/job/116566948053): `1364 passed, 204 skipped in 27.18s`.
  - [Windows job 116566948118](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38776947803/job/116566948118): `1363 passed, 205 skipped in 38.85s`.
  - [PostgreSQL job 116566948087](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38776947803/job/116566948087): `204 passed, 1364 deselected in 58.35s`.
  - [Container job 116566947772](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38776947803/job/116566947772): configuration passed; effective context contained 72 files and excluded all 19 planted fixtures; image checks passed; stack startup succeeded; application services used the CI-built image; upload returned 202; ingestion succeeded; the revision became active with two verified chunks; duplicate upload returned 200; the idle worker exited with code 0 and no OOM kill; smoke and cleanup passed.
- [Secret-scan run 38776947848](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38776947848), [job 116566948188](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38776947848/job/116566948188): 44 commits scanned, no leaks found.

The reviewer did not execute the project suite or Docker locally. Claude earlier
observed run/job conclusions but could not retrieve logs anonymously. Codex has
verified the Git handover refs, and records the supplied reviewer evidence without
claiming independent log retrieval or fresh application verification.
The four accepted limitations in the M3 assessment remain: injected transaction
failures rather than process termination for rollback; database-independent
invalid-upload tests; direct tenant-specific chunk-ID tests plus separate database
storage/constraint checks; idle-worker-only container shutdown. Local Compose is
unverified. No production-readiness or general security claim follows.

**M3a, the first slice, in detail (specification settled at review; implemented, reviewed, verified in CI and on `main`):**

- **Why first:**
  - Every later slice writes through the job fence, so it must exist and be proven against PostgreSQL first.
  - It needs no document, chunk or upload code, and its invariants (one owner, a monotonic fencing token, bounded retries) can be tested on their own.
- **Domain (`evidenceguard_domain.jobs`, pure, no database):**
  - a `JobStatus` enum: `queued`, `running`, `succeeded`, `failed`, `dead`;
  - pure transition functions for claim, heartbeat, succeed, retryable failure, permanent failure, lease reclaim and exhausted-lease expiry;
  - the backoff function;
  - payload validation and canonicalisation;
  - the lifecycle invariants, with exhaustive table tests like the existing report and approval rules.
- **Parameters** [DECISION]. These are engineering defaults for the first implementation, not measured performance claims:
  - **Lease duration:** 60 seconds.
  - **Heartbeat interval:** 20 seconds, used by the M3b worker. M3a provides only the heartbeat operation.
  - **Attempts:** `max_attempts` defaults to 3, with an accepted range of 1–10. `attempt` starts at 0 and increases by one on each successful claim or reclaim.
  - **Backoff:** after failed attempt *n*, the delay is `min(5 * 2^(n - 1), 60)` seconds, that is 5, 10, 20, 40, then 60 s.
    - There is no jitter in v1. This is a deliberate simplification: deterministic delays are easier to test, and v1 expects few workers. Jitter can be added if synchronised retries are ever observed.
  - **Payload cap:** 4,096 bytes, measured on canonical UTF-8 JSON.
  - **Field lengths:** `kind` at most 64 characters, `idempotency_key` at most 128.
- **Status semantics** [DECISION]:
  - `failed` is a permanent, non-retryable handler failure.
  - `dead` means a retryable failure or lease abandonment has exhausted the attempt cap.
  - `succeeded`, `failed` and `dead` are terminal. Every transition into a terminal status clears `locked_by` and `lease_expires_at` and sets `finished_at`.
- **Payload** [DECISION]:
  - **Shape:** in M3a, a payload is a flat JSON object with string keys and UUID-string values. An empty object is allowed for test-only jobs.
  - **UUID values:** must already be in canonical lowercase, hyphenated form; anything else is rejected, never rewritten.
  - **Forbidden content:**
    - no tenant field;
    - no nested objects or arrays;
    - no document text;
    - no secrets.
  - **Canonical form:** keys sorted, no insignificant whitespace, UTF-8 encoded. It is used for the size cap and for comparison.
  - **Kind-specific schemas** arrive with their handlers in later slices.
- **Schema (migration `0002`, revising `0001`, on the existing naming convention):** a `jobs` table with these columns:
  - **Keys:**
    - `id` (UUID primary key);
    - `tenant_id`, with a foreign key to `tenants` and unique `(tenant_id, id)` for later composite references.
  - **Identity:**
    - `kind`;
    - `payload` (`jsonb`);
    - `idempotency_key`, with unique `(tenant_id, kind, idempotency_key)`.
  - **State:**
    - `status`, checked against the five values;
    - `attempt` (≥ 0) and `max_attempts` (1–10), with `attempt ≤ max_attempts`;
    - `run_after`.
  - **Lease:** `locked_by` and `lease_expires_at`, with a check that both are set exactly when the status is `running`.
  - **Diagnostics:** `last_error`, a short fixed error code, never exception text, SQL or payload values.
  - **Timestamps:** `created_at`, `updated_at` and `finished_at`, all timezone-aware, with a check that `finished_at` is set exactly for terminal statuses.
  - **Indexes:** partial indexes for claiming queued jobs by `run_after` and for finding expired leases.
  - **Not included:** no extension, and no change to existing tables.
- **Tenant scope:**
  - A job carries its tenant in `tenant_id`.
  - Handlers take the tenant only from the claimed row, never from the payload.
  - Claiming is a trusted, system-level operation across tenants. No API endpoint exposes jobs in M3a.
  - Enqueueing from a request takes the tenant from the authenticated `ActorContext`.
- **Time** [DECISION]:
  - **Database time only:** every lease and scheduling decision uses PostgreSQL `clock_timestamp()`, evaluated freshly at the moment of the decision. That covers claim eligibility, lease validity, a new `lease_expires_at` and a new `run_after`.
  - **What is never used for lease validity:**
    - worker clocks;
    - transaction-start time (`now()` or `CURRENT_TIMESTAMP`), because it can be stale after a lock wait or in a longer transaction.
  - **Audit timestamps** (`created_at`, `updated_at`, `finished_at`) may use ordinary transaction timestamps.
- **Ownership, lease and fencing rules** [DECISION]:
  1. **Idempotent enqueue checks the identity of the request.**
     - The unique key stays `(tenant_id, kind, idempotency_key)`.
     - Enqueue runs inside the caller-owned transaction, so a later revision and its ingestion job commit together.
     - It runs `INSERT … ON CONFLICT (tenant_id, kind, idempotency_key) DO NOTHING RETURNING id`. If no row is returned, it reads the committed existing row by its unique key and compares the request with it:
       - the payload is compared as a parsed object, so the order of JSON object keys cannot create a false conflict;
       - the immutable `max_attempts` configuration is compared too.
     - **An identical retry** returns the existing job as it is, including when it is already terminal. It never resets, re-queues or reschedules the job.
     - **A changed payload or `max_attempts`** under the same key raises a fixed `JobIdempotencyConflictError`. The error contains no values, and the existing row is not changed.
     - **Concurrent enqueues** with the same key resolve through the unique constraint. Under PostgreSQL's default READ COMMITTED isolation, `ON CONFLICT` waits for a conflicting in-flight insert. The following read then sees the committed row and compares against it. If that row is not visible, enqueue raises a fixed error rather than guessing.
  2. **Claim** is one short transaction.
     - **Expired, exhausted jobs:** first, a bounded sweep marks `dead` any `running` job whose lease has expired by `clock_timestamp()` with `attempt = max_attempts`.
       - The sweep handles at most 10 rows per claim, uses `FOR UPDATE SKIP LOCKED`, sets `last_error` to a fixed code, leaves `attempt` unchanged and never increments it beyond `max_attempts`.
     - **Selecting a job:** claim then selects the oldest eligible row by `(run_after, id)` with `FOR UPDATE SKIP LOCKED`. Eligible means:
       - queued, with `run_after ≤ clock_timestamp()`; or
       - running, with an expired lease and `attempt < max_attempts`.
     - **Exhausted rows never block the queue:** they are excluded from the selection, so they cannot stop an eligible job from being claimed, however many there are.
     - **Taking the job:** set `running`, increment `attempt`, set `locked_by` to the worker ID, and set `lease_expires_at` to `clock_timestamp()` plus 60 seconds.
     - Workers get a unique ID per process start; it is not secret.
  3. **The fencing token** is `(job id, locked_by, attempt)`.
     - `attempt` grows on every claim, so a reclaim always invalidates the previous owner, even if the same worker ID reclaims its own job.
  4. **Every ownership operation follows one strict procedure:** heartbeat, completion, failure and every fenced handler effect.
     1. Lock the job row by ID (`SELECT … FOR UPDATE`, waiting if necessary).
     2. *After* the lock is held, check validity in a separate statement, using a fresh `clock_timestamp()`:
        - status `running`;
        - a matching token;
        - `lease_expires_at > clock_timestamp()`.

        No time value or check result captured before a lock wait is reused.
     3. Only if the check passes, apply the effect in the same transaction. Otherwise raise a fixed `LeaseLostError` and change nothing.

     Fenced transactions set a bounded `lock_timeout` of 5 s [DECISION]. A timeout aborts the transaction with no effect.
  5. **Heartbeat** follows that procedure, then sets `lease_expires_at` to `clock_timestamp()` plus 60 seconds.
     - An expired lease cannot be revived, even if no other worker has reclaimed it yet. The worker must stop.
  6. **Complete and fail** follow the same procedure:
     - success sets `succeeded`;
     - a permanent failure sets `failed`;
     - a retryable failure sets `queued`, with `run_after` = `clock_timestamp()` plus the backoff, while `attempt < max_attempts`, and `dead` otherwise.

     Each records `last_error` as a fixed code. Terminal transitions clear the lease and set `finished_at`; a retry clears the lease.
  7. **What the fence guarantees, precisely:**
     - While a transaction holds the job row lock after a valid check, no claimant can reclaim that row: claims skip locked rows, and the sweep uses `SKIP LOCKED` too. The ownership check and the effect are therefore atomic with respect to reclaim.
     - It does **not** guarantee that the commit happens before `lease_expires_at`. A transaction that passed its check just before expiry may commit shortly after it.
     - The window is kept small by keeping fenced transactions short. **No provider or network call is ever made while the job lock is held.** Such calls happen outside fenced transactions, and their results are written in a separate short fenced transaction.
- **Dependencies on later slices:**
  - M3a defines the fence; M3c's activation and M3d's chunk writes must run inside it.
  - **Lock order** is fixed now to avoid deadlocks: the job row first, then the document row (`SELECT … FOR UPDATE` in activation).
  - The `ingest_revision` job kind, its payload (`revision_id`) and its idempotency key (the revision ID) are defined in M3d, not M3a.
  - M3a's tests use a test-only job kind.
- **Planned database-independent tests:**
  - **The lifecycle and its parameters:**
    - the exhaustive lifecycle table, including terminal transitions clearing the lease and setting `finished_at`;
    - backoff values for attempts 1–6, including the 60-second cap;
    - the `max_attempts` default and range, and attempt bounds.
  - **Payload validation:** a flat object, string keys, canonical UUID-string values, the empty-object case, no tenant field, no nesting, and the 4,096-byte cap measured on canonical UTF-8 JSON.
  - **Canonicalisation:** objects that differ only in key order compare equal.
  - **Compiled SQL:**
    - claim and the sweep use `FOR UPDATE SKIP LOCKED` with deterministic ordering;
    - lease decisions use `clock_timestamp()`, not `now()`;
    - every ownership operation locks before it checks.
  - **Transaction ownership:** a recording session checks commit, rollback and close.
  - **Error privacy:** `LeaseLostError`, `JobIdempotencyConflictError` and stored errors contain no payload, SQL or exception text.
- **Planned PostgreSQL integration tests**, using the existing disposable-database guard and required-integration mode:
  - **Migration and constraints:**
    - `0002` upgrades and downgrades, and models and migrations do not drift;
    - the constraints hold: status values, lease consistency, `finished_at` consistency, attempt and `max_attempts` bounds, and the tenant foreign key.
  - **Idempotent enqueue:**
    - an identical retry returns the same job and leaves the row unchanged;
    - the same payload with a different key order is an identical retry;
    - a changed payload, and separately a changed `max_attempts`, raise `JobIdempotencyConflictError` and leave the row unchanged;
    - a retry against a `succeeded`, `failed` or `dead` job returns it unchanged, without re-queueing it;
    - the same key in another tenant creates a separate job;
    - two concurrent enqueues with the same key, on separate connections synchronised by a barrier, produce exactly one row. Identical requests both get that job; a differing second request gets the conflict error.
  - **Claim basics:**
    - claim respects `run_after` and order;
    - an expired, exhausted job ahead of an eligible queued job is marked `dead` with its attempt unchanged, and the queued job is still claimed in the same call;
    - with more exhausted rows than the sweep bound, the eligible job is still claimed.
  - **Concurrency and stale-worker cases that must be verified:**
    - **two concurrent claimers**, using separate connections synchronised by a barrier, produce exactly one owner; the other gets a different job or none, without blocking;
    - **a reclaimed job's stale owner** (attempt *n*) cannot heartbeat, complete, fail or make a fenced write after reclaim (attempt *n + 1*), and the row is unchanged;
    - **the same worker ID reclaiming its own job** is still fenced by `attempt`;
    - **a fenced write in progress** holds the row lock, so a concurrent claim skips the job instead of reclaiming it mid-write;
    - **a heartbeat on an expired but unreclaimed lease** fails, and so do a completion and a fenced effect;
    - **a lease that expires during a lock wait:**
      - the setup: an ownership operation waits for the job row lock, held by another transaction that does not modify the row, and the lease expires before the operation gets the lock;
      - the expected result: the operation is refused with `LeaseLostError` and has no effect.
      - This catches a validity check evaluated before the wait. It is the only test that needs a real, bounded wait of about a second; every other expiry is simulated by setting `lease_expires_at` in the past through SQL.
    - **an exception inside a fenced transaction** rolls back its writes and leaves the job owned and running;
    - **repeated retryable failures and lease abandonment** reach `dead` at exactly `max_attempts`, with the backoff delays above; a permanent failure ends `failed`.
- **Explicit exclusions from M3a:**
  - the worker process, command, loop or heartbeat timer (M3b);
  - real handlers;
  - the documents, revisions and chunks tables (M3c–M3d);
  - parsing;
  - upload and document endpoints, and any job API;
  - Dockerfile and Compose changes;
  - embeddings and vectors;
  - `LISTEN/NOTIFY`, cancellation, scheduling, jitter and metrics;
  - new dependencies.
- **Review decisions (Prompt 47):** the reviewer settled the four items marked [DECISION] above:
  - the idempotent-enqueue identity check;
  - fresh database time with lock-then-check ownership;
  - the initial parameters;
  - the terminal semantics, including exhausted claims.

  The 5-second `lock_timeout` and the sweep bound of 10 rows per claim were accepted at review (Prompt 48) as initial engineering defaults, not measured performance claims.

**M3b, the worker process, in detail (ACCEPTED at review, Prompt 59; implemented in Prompts 60–61, reviewed, verified in CI and on `main` at `dd26c70`):**

M3b turns the M3a library into a running worker. It keeps the accepted architecture: plain Python, PostgreSQL-backed jobs, leases and fenced transactions ([ADR-0003](decisions/0003-plain-python-workflow.md), [ADR-0007](decisions/0007-durable-job-core.md)). There is no new queue, framework or dependency.

The external reviewer inspected the original specification (Prompt 57) and its lifecycle and shutdown corrections (Prompt 58), without running the project suite, and accepted it with the final clarifications of Prompt 59. The choices are listed as settled at the end. The timing values are **initial engineering defaults, not measured guarantees**. The implementation ([ADR-0008](decisions/0008-worker-runtime.md)) records its choices within this specification. It was reviewed and passed CI, including all 77 PostgreSQL integration tests, at `bc5f638` on its feature branch.

- **Package and command:**
  - A new application package, `evidenceguard_worker`, at `apps/worker/evidenceguard_worker/`. This is the layout ADR-0001 already names.
  - It joins the single `evidenceguard` distribution, Mypy's `files` and Ruff's `known-first-party`. A console script `eg-worker = "evidenceguard_worker.__main__:main"` is added.
  - **Import boundaries:**
    - the worker may import `evidenceguard_domain`, `evidenceguard_persistence` and `evidenceguard_observability`;
    - nothing imports `evidenceguard_worker`;
    - the worker does not import `evidenceguard_api`.

    The existing boundary test gains these rules.
- **Settings and CLI errors:**
  - **Database:** the URL comes only from the existing `load_database_settings()` (`EG_DATABASE_URL`), and the engine from `create_db_engine` (5 s connect and 10 s pool timeouts).
  - **CLI flags:**
    - `--once`: one claim attempt and at most one job, then exit;
    - `--log-level`.

    The timing defaults below are constants, adjustable only through the Python API for tests. They are not CLI or environment settings in M3b.
  - **Argument parsing:** a small safe parser, equivalent to the `SafeArgumentParser` in `eg-admin`, prints only static usage and a fixed message. The worker duplicates those ~10 lines rather than importing `evidenceguard_api`.
  - **Exit codes:** fixed codes, with fixed stderr messages and no submitted values, URLs or exception text:

    | Code | Meaning |
    |---|---|
    | 0 | normal stop, or `--once` with nothing claimable |
    | 1 | unexpected failure, reported by class name only. This includes `--once` when its single claim attempt hits a database error |
    | 2 | usage error |
    | 3 | database configuration error (the existing URL-free message) |
    | 4 | no handlers registered |
    | 5 | **abnormal shutdown:** a handler or heartbeat thread did not stop within its bounded wait (see *Abnormal shutdown*) |
- **Process model:**
  - **At most one concurrently active handler per worker process.** Jobs are processed sequentially, one after another. No accepted decision requires more, and one handler at a time keeps lease, heartbeat and shutdown reasoning simple. Throughput comes from running several processes, which `SKIP LOCKED` already supports.
  - **No new claim while a thread from an earlier job may still be alive.** The process never moves on to another job while a handler or heartbeat thread from a previous job could still be running.
  - **Threads:**
    - the **main thread** supervises: signals, polling and claiming, starting and stopping the per-job threads, and recording outcomes;
    - a **handler thread** (a daemon) runs the handler for one job;
    - a **heartbeat thread** (a daemon) extends that job's lease.
  - **Sessions:**
    - The engine and its pool are shared, which SQLAlchemy supports across threads.
    - **A SQLAlchemy `Session` is never shared between threads.** Every M3a operation (`claim`, `heartbeat`, `complete`, `fail_*`, `fenced_transaction`) already opens and closes its own session from the session factory, so each thread only ever uses sessions it created.
  - **The handler wrapper is not a sandbox.** It follows M3a's trusted-code convention. Handlers are trusted application code and must preserve the fence's transaction and lock ([ADR-0007](decisions/0007-durable-job-core.md)).
- **Worker identity:** one `new_worker_id()` (`worker-<uuid4>`) per process start. It contains no hostname, user or other personal identifier, and it is not secret.
- **M3a extension: a `claim(..., kinds=...)` filter:**
  - **`kinds=None`** keeps the existing behaviour exactly: any kind.
  - **A collection** limits candidates to those kinds. Each value is validated against M3a's kind pattern, and an invalid value raises `ValueError` before any SQL.
  - **An empty collection selects no candidate** and returns `None`. It never means "claim all".
  - **The exhausted-job sweep** still runs on every `claim` call, whatever the filter, including an empty one. It is global maintenance that never hands out a job.
  - **Unhandled kinds:** jobs of kinds this worker cannot handle stay queued for a worker that can, and are never failed for being unknown.
- **Polling loop** (main thread), repeated until a stop is requested or the runtime has become abnormal:
  1. If a stop was requested, leave the loop.
  2. Record the monotonic time `t0`, then call `claim(session_factory, worker_id, kinds=registry.kinds)`. A claim can still be in flight when a stop is requested: the signal handler only sets a flag.
  3. **Post-claim stop check:** if a stop was requested while the claim ran and a job was acquired, the runtime starts **no handler**. It records `fail_retryable(..., JobErrorCode.WORKER_SHUTDOWN)` through the fence, which succeeds only while ownership remains valid, and leaves the loop. This consumes the attempt the claim counted, just as a lease expiry would, and frees the job sooner than leaving the lease to expire.
  4. No job:
     - in `--once` mode, exit 0 at once;
     - otherwise wait `IDLE_POLL_SECONDS = 2` on the stop event and loop.
  5. A database error (`SQLAlchemyError` or `JobLockTimeoutError` from the claim):
     - log `worker.poll_failed` with `error_type` only;
     - in `--once` mode, exit 1;
     - otherwise wait an exponential backoff of 1, 2, 4, 8, 16, then 30 s (`POLL_BACKOFF_CAP_SECONDS = 30`), interruptible by the stop event, and reset it after the next successful claim attempt.
  6. A job: run it under supervision (below), with its local lease deadline starting at `t0 + 60 s`. In `--once` mode, exit after it.

  The defaults are bounded engineering choices, not measured figures:
  - a 2-second idle poll keeps pickup latency low at one cheap query per 2 s per worker;
  - capping the outage backoff at 30 s avoids reconnect storms;
  - all waits use `threading.Event.wait(timeout)`, so a stop request ends them at once.
- **Handler registry and context:**
  - **The registry:** `HandlerRegistry` is an immutable mapping from job kind to handler.
    - Kinds are validated against M3a's kind pattern, and registering the same kind twice is an error.
    - The production registry is built in `evidenceguard_worker.handlers`. It is **empty in M3b**; M3d adds `ingest_revision`.
  - **A handler:** `JobHandler` is any callable `(ctx: JobContext) -> None`.
  - **`JobContext` exposes:**
    - `job`: the claimed `JobSnapshot`. The tenant comes only from `job.tenant_id`, never from the payload;
    - `token`;
    - read-only `lease_lost`, `cancel_requested` and `finished` flags;
    - `check()`: raises `FenceClosedError` once the finish has committed; `LeaseLostError` if lease loss is confirmed or presumed; or `JobCancelledError` if cancellation was requested;
    - `fenced(*, finish=False)`: calls `check()`, then opens M3a's `fenced_transaction` for the token and yields a `HandlerFence`.
  - **`HandlerFence`** exposes only `.session` (M3a's `FencedSession`) and `.job`. It has **no transition methods**, so handler code cannot record a lifecycle outcome directly.
- **Committed finish (atomic completion):**
  - **Inside the block:** `with ctx.fenced(finish=True)` records `succeeded` through the fence **inside the same transaction** as the block's effects, just before the commit.
  - **The finish state** is thread-safe: a value of `none`, `finishing`, `committed` or `uncertain`, guarded by a small state lock.
    - **`finishing`** is set when the `finish=True` block is entered, before any database work in it.
    - **`committed`** is set **only after the transaction context has exited without an exception, which includes a successful commit.**
    - **`none` again:** if the block raises, the transaction rolls back and the state returns to `none`. A rolled-back finish never marks the job completed.
    - **`uncertain`:** if the commit itself raises, it is unknown whether the job committed, so success is **not** claimed. The handler receives the exception.
    - **The state lock is never held across database I/O.** It is taken only to read or change the state and the pending-refusal flag, so the supervisor can always read them and keep observing its deadlines.
  - **After `committed`:**
    - every later context operation (`check()`, `fenced()`) raises `FenceClosedError`;
    - the runtime **never** attempts another completion, retry or permanent failure for that job, even if the handler later raises. A later exception is logged as the fixed event `job.post_finish_error`, with `error_type` only, and cannot change the committed outcome.
  - **After `uncertain`:** a commit exception does not say which way the commit went, and the runtime does not assume either.
    - Any outcome the runtime then attempts still goes through the fence.
    - **If the commit actually succeeded** (only the acknowledgment failed), the job is terminal and the fence refuses the write with `LeaseLostError`. That is logged as `job.outcome_unknown`, never as success, and no second committed outcome results.
    - **If the commit did not succeed,** the fenced outcome write may succeed as usual, or fail if ownership has gone. Either way, recovery stays fenced, and durable handler effects must be idempotent, so a retry or reclaim after an uncommitted finish is safe.
  - **The promise** is no contradictory second committed outcome. It is **not** that an outcome is always recorded successfully.
- **Who records the outcome:** the supervisor, after the handler thread has stopped and the heartbeat thread has been confirmed stopped (see *End of a job*):

  | Situation | Outcome |
  |---|---|
  | Finish state `committed` | Nothing more. Logged as `job.succeeded`, or `job.post_finish_error` if the handler raised afterwards |
  | Lease loss was detected (confirmed or presumed) and the finish is not `committed` | **No write.** Logged as `job.lease_lost`. The stale worker records nothing |
  | Returned normally without finishing | `complete(...)` in its own fenced transaction |
  | `RetryableJobError(code)` | `fail_retryable(..., code)`. M3a's attempt cap and scheduled backoff apply unchanged: re-queued while attempts remain, otherwise `dead`. There is no second retry mechanism |
  | `PermanentJobError(code)` | `fail_permanent(..., code)` → `failed` |
  | `JobCancelledError` from a shutdown cancellation, with no lease loss detected | `fail_retryable(..., JobErrorCode.WORKER_SHUTDOWN)` |
  | Any other exception | `fail_retryable(..., JobErrorCode.UNEXPECTED_ERROR)`; only the class name is logged |
  | The claimed job has no handler (defensive; the kind filter should prevent it) | `fail_permanent(..., JobErrorCode.UNKNOWN_JOB_KIND)` |

  - **If the outcome write itself fails:**
    - `LeaseLostError`: log `job.lease_lost`, or `job.outcome_unknown` after an uncertain finish, and write nothing;
    - a database error: log `job.outcome_failed`.

    The lease then expires and the job is reclaimed. This is at-least-once execution.
  - **New `JobErrorCode` values:** `unknown_job_kind`, `unexpected_error` and `worker_shutdown`.
    - No migration is needed: `last_error` is checked against a code pattern, not a list.
    - Handlers use `retryable_failure` or `permanent_failure`, or kind-specific codes added to the enum with review.
- **Heartbeats** (heartbeat thread, one per running job):
  - **The loop:** wait `HEARTBEAT_INTERVAL_SECONDS = 20` (M3a's accepted value) on the job's heartbeat-stop event. Then record the monotonic time `t_call` and call M3a's `heartbeat(session_factory, token)`. Each call is its own fenced transaction on its own session.
  - **Results:**
    - **Success:** move the local lease deadline to `t_call + 60 s`. It moves only after a **confirmed** renewal, and always from the pre-call time.
    - **`LeaseLostError`:** record a **pending refusal** under the state lock and end the thread. It is not acted on at once, because a refusal can arrive between the database commit of an atomic finish and the publication of the local `committed` state. The supervisor classifies it only once no finish is in progress:
      - finish state `committed`: an expected refusal caused by the terminal state. It is discarded and never reported as ownership loss;
      - finish state `none`, including after a rolled-back finish: lease loss;
      - finish state `uncertain`: lease loss, with the outcome treated as unknown (`job.outcome_unknown`), never as success;
      - while the state is `finishing`, the refusal stays pending. The local lease deadline and the supervisor's other waits still apply, so a finish that never resolves still reaches the lease-loss or abnormal path.
    - **`JobLockTimeoutError` or `SQLAlchemyError`:** log `job.heartbeat_failed` with `error_type`, and try again at the next interval.
    - **Any other exception:** log it by class name, record a pending refusal as above and end the thread. When unsure, stop writing.
  - **Presumed loss:** the local lease deadline starts at `t0 + 60 s`, where `t0` is the monotonic time captured **before** the claim began. Once it passes without a confirmed renewal, the lease is presumed lost. These local checks are conservative approximations; **PostgreSQL decides actual lease validity through the fence.**
  - **Lock interplay:** a heartbeat waits for the job row lock up to the 5 s `lock_timeout`. Handler fenced transactions should therefore stay well under 5 s, or that interval's heartbeat fails.
  - **What setting the stop event does:** it stops *future* heartbeats only. **A heartbeat call already in flight is not cancelled** and may still complete, extend the lease or fail later.
  - **Cancellation is irreversible for an attempt.** Once the supervisor has latched lease loss or cancellation for an attempt, nothing clears it.
    - A late successful heartbeat does not revive the attempt, move its local deadline, or permit further context writes: `check()` and `fenced()` keep raising.
    - That late heartbeat may still have extended the database lease, by up to 60 s from its database time. **Reclaim of the job may therefore be delayed** until that extended lease expires.
- **Lease loss while a handler is still running** (supervisor), on a heartbeat refusal classified as lease loss, or on presumed loss:
  1. Latch cancellation for the attempt (irreversible, see above) and set `cancel_requested`. The handler's next `check()` or `fenced()` raises.
  2. Stop renewing: set the heartbeat-stop event, and join the heartbeat thread for up to `HEARTBEAT_JOIN_SECONDS = 10`.
  3. Wait up to `LEASE_LOSS_GRACE_SECONDS = 5` for the handler thread to exit.
  4. If it exits: record **no** outcome unless the finish state is `committed`. A stale worker writes nothing.
  5. If the handler or heartbeat thread is still alive: take the **abnormal shutdown** path. The process never claims another job.
- **End of a job** (the handler thread has exited):
  1. Set the heartbeat-stop event and join the heartbeat thread for up to `HEARTBEAT_JOIN_SECONDS = 10`. This is a bounded supervisor wait with an initial engineering default, **not** a guarantee about how long a database call takes.
  2. **Check whether the thread actually stopped.** If it is still alive, a heartbeat may still be in flight:
     - record **no** runtime outcome;
     - set `cancel_requested`, so the context refuses further operations;
     - take the abnormal shutdown path. **No further claim is made.**

     The database fence remains the final ownership check either way.
  3. Only if the heartbeat thread has stopped, record the outcome from the table above.
- **Cancellation is cooperative and limited:**
  - `ctx.fenced()` calls `check()` immediately before every fenced write. Long handlers should also call `check()` between expensive steps.
  - **Python cannot safely stop an arbitrary running thread.** Lease loss or shutdown therefore does **not** instantly stop handler computation or an in-flight external call. It stops the handler at its next `check()` or fenced write. If the handler never checks, the fence still refuses its writes once ownership is gone.
  - Effects outside the database (provider calls) may still happen after lease loss. That is the accepted at-least-once limit.
- **Shutdown** (SIGINT, and SIGTERM where the platform delivers it; `SIGBREAK` is also handled on Windows):
  - **Signal handlers** are installed only in the main thread. They only set flags: the first signal requests a graceful stop, a second requests an immediate stop.
  - **On a graceful stop:**
    1. No new claims are made. A claim already in flight finishes, and the post-claim stop check applies.
    2. If a job is running, heartbeats continue while the supervisor waits up to `DRAIN_SECONDS = 30` for the handler. A normal finish ends the job as described above.
       - **Lease validity during the drain depends only on actual successful renewals and the database fence, not on the drain length.**
       - If heartbeats fail during the drain (for example during a database outage), presumed loss can trigger, and the lease-loss path takes over.
    3. At the drain deadline, `cancel_requested` is set and the supervisor waits up to `CANCEL_GRACE_SECONDS = 5`. If the handler exits with `JobCancelledError`, the `worker_shutdown` retry is recorded, provided no lease loss was detected and the heartbeat thread is confirmed stopped.
    4. If the handler is still alive: abnormal shutdown.
  - **On an immediate stop** (second signal), the runtime goes straight to abnormal shutdown if a job is running, or exits 0 if none is.
  - Drain, cancellation and join waits are **bounded supervisor waits**. The existing connect (5 s), pool (10 s) and lock (5 s) timeouts do **not** form a total deadline for every database operation or network failure.
  - **Blocking supervisor operations:**
    - `claim` and runtime outcome recording (`complete` and the `fail_*` calls) are **synchronous calls on the supervisor thread**.
    - If either blocks, for example on a hung statement or a stalled connection, the supervisor cannot reach its timed shutdown checks until the call returns.
    - Signals only set flags. They do **not** cancel these calls.
    - The abnormal exit path bounds lingering background threads only **once the supervisor reaches it**.
    - **M3b therefore does not guarantee a total process shutdown deadline.** An operator may still have to terminate the process externally.
  - **Windows:** tests trigger shutdown through the runtime's stop API and by calling the installed handler functions directly, rather than relying on delivery of OS signals. SIGINT delivery is exercised with `signal.raise_signal` only where it is reliable.
- **Abnormal shutdown:**
  1. The runtime stops claiming permanently and logs `worker.abnormal_stop`, recording which wait expired.
  2. It disposes the engine. **This is pool cleanup only.** It closes idle pooled connections; it does **not** cancel sessions checked out by live threads, or stop running handlers or in-flight database calls.
  3. **The runtime and the process are different things.**
     - `run_worker()`, the Python API, *returns* an abnormal result. The live daemon threads may keep running as long as the surrounding Python process lives. An in-process caller, such as a test, must not reuse that runtime.
     - The `eg-worker` CLI, after receiving that result, flushes its log handlers and **ends the process** with `os._exit(5)`, so that interpreter shutdown cannot block on the live threads.
  4. When the process actually terminates, the operating system closes its connections.
     - PostgreSQL rolls back any uncommitted transaction **once it detects the disconnect**. This is not necessarily immediate.
     - Until then, a still-open transaction can keep holding the job row lock, and claims skip that row.
     - The job is reclaimed only after `lease_expires_at` has passed **and** no lock is held.
     - No immediate server-side rollback or reclaim is promised.
- **Cleanup on a normal stop:** the heartbeat thread is confirmed stopped, the handler thread has exited, the engine is disposed, and `worker.stopped` is logged. Sessions are closed by the M3a operations that opened them.
- **Logging:**
  - Records use logger `evidenceguard.worker` and the existing `JsonFormatter`.
  - **Additions to `REVIEWED_EVENTS`:**
    - `worker.started`, `worker.stopping`, `worker.stopped`, `worker.abnormal_stop`, `worker.poll_failed`, `worker.no_handlers`, `worker.config_invalid`;
    - `job.claimed`, `job.succeeded`, `job.post_finish_error`, `job.retry_scheduled`, `job.dead`, `job.failed`, `job.cancelled`, `job.lease_lost`, `job.heartbeat_failed`, `job.outcome_failed`, `job.outcome_unknown`.
  - **Additions to `ALLOWED_FIELDS`:** `worker_id`, `job_id`, `job_kind`, `attempt` and `error_code`. `error_type` already exists.
  - **Values must come from validated sources.** Opening the formatter's allowlist does not make arbitrary values safe, so each field is filled only from a validated identifier or enum:
    - `worker_id`: the worker-ID pattern;
    - `job_id`: a UUID;
    - `job_kind`: the kind pattern;
    - `attempt`: an integer;
    - `error_code`: `JobErrorCode`;
    - `error_type`: an exception class name.
  - **Never logged:** tenant IDs, payload values, idempotency keys, URLs, SQL or exception messages.
- **What `eg-worker` does with no production handlers:** it exits with code 4 and the fixed message "no job handlers are registered". It does this **before** reading database settings or connecting, so in M3b the command is installable and testable but cannot claim work. This avoids a process that polls forever without being able to process anything.
- **How the runtime is tested without a production test-job command:**
  - Tests drive the runtime through its Python API, for example `run_worker(..., registry=..., stop=..., timings=...)`.
  - They use **test-only handlers defined under `tests/`**, for kind `test_job`.
  - No CLI flag, environment variable or packaged module registers test kinds, and there is no command that enqueues arbitrary jobs.
  - M3b adds no document, chunk or ingestion code.
- **At-least-once limits:**
  - A handler can run more than once for the same job: after a crash between an effect and the outcome, after lease loss, after an uncertain finish, or after an abnormal shutdown.
  - Future handlers must therefore make every durable effect through `ctx.fenced()`, idempotently (unique keys, as in M3c–M3d). They should use `finish=True` for their final effects, so completion is atomic with them.
- **Planned files:**
  - **New `apps/worker/evidenceguard_worker/` modules:**
    - `__init__.py` and `py.typed`;
    - `__main__.py` (CLI, exit codes and the process exit after an abnormal result);
    - `runtime.py` (polling, the supervisor and outcomes);
    - `context.py` (`JobContext`, `HandlerFence`, the finish state and the handler errors);
    - `registry.py`;
    - `heartbeat.py`;
    - `shutdown.py` (signal installation);
    - `handlers.py` (the empty production registry).
  - **Changed:**
    - `pyproject.toml`: the package, script, Mypy and Ruff entries; no new dependency;
    - `packages/domain/evidenceguard_domain/jobs.py`: the new error codes;
    - `packages/persistence/evidenceguard_persistence/jobs.py`: the `claim` `kinds` filter;
    - `packages/observability/evidenceguard_observability/jsonlog.py`: the events and fields;
    - the CI workflow's installed-wheel step: add `eg-worker --help`. This narrow workflow change was authorized at review (Prompt 59) for the M3b implementation;
    - the docs, and a new ADR-0008.
  - **Tests:** `tests/test_worker_runtime.py`, `tests/test_worker_heartbeat.py`, `tests/test_worker_cli.py` and `tests/test_worker_postgres.py`, plus additions to the packaging and boundary tests.
- **Verification plan:**
  - **Database-independent,** with fake stores, controlled clocks and events, and no unbounded sleeps:
    - **Claim filter:** `None` keeps the current behaviour; an empty filter returns `None` without selecting a job but still runs the sweep; invalid kinds are rejected before any SQL.
    - **Polling:** the idle wait asks for 2 s; the backoff runs 1, 2, 4, …, 30 and resets after success; `--once` exits 0 when nothing is claimable and 1 on a database error, never waiting indefinitely.
    - **Delayed claim and shutdown during a claim:** a fake claim blocks on an event while a stop is requested. When it returns a job, no handler starts, the `worker_shutdown` retry is recorded, and no further claim is made. When it returns `None`, the loop ends without waiting.
    - **Heartbeat loop:** it asks for 20 s intervals. The local deadline starts at the pre-claim time, and moves only after a confirmed renewal, from the pre-call time. Transient errors are retried. Presumed loss triggers at the deadline.
    - **Heartbeat stuck beyond the join deadline:** a fake `heartbeat` blocks past `HEARTBEAT_JOIN_SECONDS`. Neither a runtime outcome nor a further claim happens. The runtime returns the abnormal result, and the CLI wrapper exits with code 5.
    - **Lease loss with a live handler:**
      - a cooperative handler exits within the grace: no outcome is recorded, and the next claim is made only after both the handler and heartbeat threads are confirmed stopped;
      - an uncooperative handler stays alive past the grace: abnormal result, no outcome, **no further claim**.
    - **Committed finish:**
      - the finish commits, then the handler raises: exactly one completion, no retry or failure call, `job.post_finish_error` logged, and later context operations refused;
      - the finish block raises: rolled back, the state returns from `finishing` to `none`, and the normal error mapping applies;
      - the commit succeeded but its acknowledgment failed: the state is `uncertain`, success is not claimed, the fake fence refuses the later outcome write, `job.outcome_unknown` is logged, and no second committed outcome exists;
      - the commit did not succeed and raised: the state is `uncertain`, success is not claimed, and the later outcome attempt still goes through the fence and is recorded, with the handler's effects applied idempotently on retry;
      - a heartbeat collides with the atomic finish: `LeaseLostError` after the committed finish is classified as expected, never as `job.lease_lost`.
    - **Commit/publication interval (deterministic race):** a fake fence pauses on an event after the database commit returns but before `committed` is published. The fake heartbeat then returns `LeaseLostError`.
      - While paused: the refusal stays pending, `cancel_requested` is not set and `job.lease_lost` is not logged.
      - Released as committed: the refusal is discarded as expected.
      - In variants that release as a rollback or an uncertain commit, the refusal becomes lease loss, or lease loss with `job.outcome_unknown`.
      - The supervisor can read the state and observe its deadlines throughout the pause.
    - **Irreversible cancellation:** after lease loss or cancellation is latched, a fake heartbeat succeeds late. The attempt stays cancelled, `check()` and `fenced()` still raise, the local deadline does not move, and no outcome is written.
    - **Outcomes:** for each row of the outcome table, exactly one store call (or none) with the right code.
    - **Sessions:** a recording session factory shows that no session is ever used from two threads.
    - **Shutdown:**
      - a stop before a claim;
      - a drain that finishes;
      - a heartbeat outage during the drain, so presumed loss takes the lease-loss path;
      - cancellation at the drain deadline, leading to a `worker_shutdown` retry;
      - a second signal;
      - a claim or outcome call that blocks while a stop is requested: the supervisor reaches its shutdown checks only after the call returns, and the test records that ordering rather than a total deadline.
    - **Checked-out resources at abnormal shutdown:** a fake session that stays checked out by a live thread is not closed or cancelled by engine disposal, which only clears the pool. The runtime reports an abnormal result instead of waiting.
    - **CLI:** the exit codes and fixed messages; usage errors never echo values; the no-handlers exit happens before any settings are read; the abnormal result ends the process with code 5, tested in a subprocess with a test-only entry point.
    - **Logging:** only reviewed events and allowlisted fields, filled from validated values; no payload, tenant or marker values.
    - **Boundaries:** the import-boundary rules above.
  - **PostgreSQL integration**, using the guarded disposable database, test-only handlers, short test-only intervals, bounded waits and a server-side `statement_timeout`:
    - `--once` processing to `succeeded`;
    - **`finish=True`:** the effect and the completion commit together; a block that raises rolls both back; the finish commits and the handler then raises, leaving the job `succeeded` with no further write;
    - heartbeats extending the lease across several intervals;
    - **lease loss before a fenced write:** the handler waits on an event; the test expires the lease and another worker reclaims the job; the handler's next `ctx.fenced()` raises `LeaseLostError`; no effect row is written, the stale worker records no outcome, and it claims nothing further;
    - **heartbeat versus completion:** with a tiny interval and a finishing handler, the job ends `succeeded` exactly once, with no spurious `job.lease_lost`;
    - **shutdown during a job:** a cooperative handler leaves the job re-queued with `worker_shutdown`, and the attempt counted;
    - a retryable error re-queues the job, or ends it `dead` at the cap; a permanent error ends it `failed`; an unexpected exception re-queues it with `unexpected_error`. Each records the right code;
    - a job of an unregistered kind staying `queued`.
  - **Packaging:**
    - the wheel contains `evidenceguard_worker`;
    - the installed `eg-worker --help` works without a database;
    - the installed `eg-worker` exits 4 without database settings;
    - the import-boundary test passes.
- **Explicit exclusions from M3b:**
  - the ingestion handler and any documents, revisions, chunks or uploads (M3c–M3e);
  - Docker or Compose (M3f);
  - more than one concurrent job per process;
  - `LISTEN/NOTIFY`, metrics and job APIs;
  - commands to enqueue or cancel jobs;
  - new dependencies.
- **Settled at review (Prompt 59):**
  1. At most one concurrently active handler per process; sequential jobs are allowed.
  2. The `kinds` filter on M3a's `claim`, with the semantics above: `None` means all kinds, an empty filter means no candidate, invalid values are rejected, and the sweep always runs. This is the only change to accepted M3a code.
  3. Atomic finish through `ctx.fenced(finish=True)`, with the finish state and pending-refusal coordination above, and runtime outcomes recorded only through the fence.
  4. The fixed new error codes (`unknown_job_kind`, `unexpected_error`, `worker_shutdown`) and the reviewed log events and fields.
  5. Cooperative shutdown and the post-claim stop record a `worker_shutdown` retry when ownership remains valid.
  6. The defaults, accepted as initial engineering defaults, not measured guarantees:
     - idle poll 2 s;
     - poll backoff 1 s doubling to 30 s;
     - drain 30 s;
     - cancel grace 5 s;
     - lease-loss grace 5 s;
     - heartbeat join 10 s.
  7. Conservative monotonic lease deadlines: the pre-claim time plus 60 s, moved only after a confirmed renewal, from the pre-call time. Latched cancellation is irreversible.
  8. A separate safe argument parser in the worker, not imported from the API package.
  9. With an empty production registry, `eg-worker` exits 4 before database settings are loaded.
  10. After an abnormal result, the CLI ends the process with `os._exit(5)`; the Python API returns an abnormal result.
  11. `--once` makes one claim attempt and exits 1 on a database error, without retrying.
  12. No production statement timeout is added for worker sessions in M3b.
  13. The M3b implementation may add `eg-worker --help` to the CI installed-wheel check.
- **Accepted limitations:**
  - **No worker statement timeout.** A hung statement in a handler or heartbeat thread is left behind once the supervisor's bounded waits expire and it takes the abnormal path. A hung `claim` or outcome call blocks the supervisor itself, so it is bounded only by that call returning, or by external process termination (see *Blocking supervisor operations*). M3b has no total shutdown deadline.
  - **Delayed reclaim** after a late heartbeat extended the lease of a cancelled attempt, or while a terminated worker's transaction still holds the row lock.
  - **At-least-once execution,** as described above.
- **Conflicts with accepted decisions:** none found.
  - The `kinds` filter extends M3a's claim without changing its ordering, locking or sweep.
  - Everything else builds on the accepted M3a lease, heartbeat interval, backoff and attempt cap, without redefining them.

**M3c, documents and revisions, in detail (ACCEPTED at review, Prompt 68; implemented in Prompt 69, corrected in Prompt 71, accepted at review, verified in CI at `8646b75` and on `main` at `6f8ffde`):**

The external reviewer inspected the original specification (Prompt 66) and its corrections (Prompt 67) without running application checks. They accepted it with the final clarifications of Prompt 68. The Prompt 67 corrections cover:
- fresh lease checks after the additional lock waits;
- the activation statement order;
- honest commit-failure semantics;
- the permanent-failure seam and exhausted jobs;
- schema and input precision.

The final clarifications of Prompt 68 cover uncertain-commit recovery, the mapping from revision failure codes to job error codes, and where the tenant is checked. The choices are listed as settled at the end. The implementation (Prompt 69) follows them without changes; its implementation choices within the specification are recorded in [ADR-0009](decisions/0009-document-revisions.md).

M3c adds the `documents` and `document_revisions` tables (migration `0003`), the pure revision lifecycle, and tenant-scoped persistence operations. Those operations are:
- creating a revision, with revision-number allocation;
- marking it processing or failed;
- activating it transactionally inside the existing job fence.

It builds on the accepted design (§4 *Document revision*, correction B; ADR-0004's tenant-safe references; ADR-0007's fence; ADR-0008's atomic finish). There is no new storage service, queue or framework.

**Out of scope here:**
- parsing, chunking, the `chunks` table and the `ingest_revision` handler (M3d);
- uploads and document endpoints (M3e);
- Docker (M3f).

M3c adds no production worker handler and no endpoint.

- **Modules (following M3a's layout):**
  - `evidenceguard_domain.revisions`: pure values and rules, no database;
  - `evidenceguard_persistence.documents`: PostgreSQL operations;
  - new models in `evidenceguard_persistence.models`;
  - migration `v0003_documents.py`.

  The plan's earlier name `evidenceguard_domain.state` is not used; M3a established one module per lifecycle.

**A. Schema and ownership**

- **`documents`:**

  | Column | Type | Null | Default / rule |
  |---|---|---|---|
  | `id` | uuid | no | primary key (application `uuid4`) |
  | `tenant_id` | uuid | no | FK → `tenants.id` |
  | `vendor_id` | uuid | no | composite FK `(tenant_id, vendor_id)` → `vendors (tenant_id, id)` |
  | `document_key` | varchar(64) | no | check `ck_documents_document_key`: `^[a-z0-9]+(?:-[a-z0-9]+)*$` (the vendor slug pattern) |
  | `title` | varchar(200) | no | check `ck_documents_title`: `char_length(btrim(title)) >= 1` |
  | `source_type` | varchar(32) | no | check `ck_documents_source_type`: one of `SourceType` (`vendor_statement`, `contract`, `third_party_report`) |
  | `authenticity` | varchar(32) | no | default `'not_established'`; check `ck_documents_authenticity`: `= 'not_established'` (the only v1 value, E11) |
  | `latest_revision_no` | integer | no | default 0; check `ck_documents_latest_revision_no`: `>= 0` |
  | `active_revision_id` | uuid | yes | composite FK `fk_documents_active_revision` `(tenant_id, id, active_revision_id)` → `document_revisions (tenant_id, document_id, id)` |
  | `created_at`, `updated_at` | timestamptz | no | `now()` |

  **Constraints:** unique `(tenant_id, id)` (for tenant-safe references) and unique `(tenant_id, vendor_id, document_key)`, the document identity, which also serves as the lookup index. There are no other indexes.
- **`document_revisions`:**

  | Column | Type | Null | Default / rule |
  |---|---|---|---|
  | `id` | uuid | no | primary key |
  | `tenant_id` | uuid | no | FK → `tenants.id` |
  | `document_id` | uuid | no | composite FK `(tenant_id, document_id)` → `documents (tenant_id, id)` |
  | `revision_no` | integer | no | check `>= 1` |
  | `version_label` | varchar(64) | yes | check: NULL or `char_length(btrim(version_label)) >= 1` |
  | `effective_date` | date | yes | — |
  | `status` | varchar(16) | no | check: one of `pending`, `processing`, `failed`, `active`, `superseded` |
  | `failure_reason` | varchar(64) | yes | check: fixed-code pattern `^[a-z][a-z0-9_]{0,63}$` |
  | `sha256` | char(64) | no | check: `^[0-9a-f]{64}$` (SHA-256 of the uploaded bytes) |
  | `media_type` | varchar(32) | no | check: `IN ('text/markdown', 'text/plain')` |
  | `byte_size` | bigint | no | check: `>= 1` |
  | `content_text` | text | no | the decoded UTF-8 text |
  | `activated_at`, `failed_at`, `superseded_at` | timestamptz | yes | see the state checks |
  | `superseded_by_revision_id` | uuid | yes | composite FK `fk_document_revisions_superseded_by` `(tenant_id, document_id, superseded_by_revision_id)` → `document_revisions (tenant_id, document_id, id)` |
  | `created_at`, `updated_at` | timestamptz | no | `now()` |

  **Uniques and indexes:**
  - `(tenant_id, id)`;
  - `(tenant_id, document_id, id)`, the target of both pointer FKs;
  - `(tenant_id, document_id, revision_no)` (accepted);
  - `(tenant_id, document_id, sha256)` (accepted: idempotent uploads within a document);
  - the partial unique index `uq_document_revisions_one_active` on `(tenant_id, document_id) WHERE status = 'active'`.

  **State checks.** Each field is constrained on its own, so a partial pair cannot pass:

  | Constraint | Rule |
  |---|---|
  | `ck_document_revisions_status` | `status IN ('active', 'failed', 'pending', 'processing', 'superseded')` |
  | `ck_document_revisions_failure_reason_when_failed` | `(status = 'failed') = (failure_reason IS NOT NULL)` |
  | `ck_document_revisions_failed_at_when_failed` | `(status = 'failed') = (failed_at IS NOT NULL)` |
  | `ck_document_revisions_superseded_at_when_superseded` | `(status = 'superseded') = (superseded_at IS NOT NULL)` |
  | `ck_document_revisions_superseded_by_when_superseded` | `(status = 'superseded') = (superseded_by_revision_id IS NOT NULL)` |
  | `ck_document_revisions_activated_at_when_active` | `status <> 'active' OR activated_at IS NOT NULL` |
  | `ck_document_revisions_no_activated_at_before_settled` | `status NOT IN ('pending', 'processing', 'failed') OR activated_at IS NULL` |
  | `ck_document_revisions_not_superseded_by_self` | `superseded_by_revision_id IS NULL OR superseded_by_revision_id <> id` |

  A `superseded` revision may keep its earlier `activated_at`; one superseded directly, without ever being active, has none.

  **Format and range checks:**
  - `ck_document_revisions_failure_reason_code` (the fixed-code pattern);
  - `ck_document_revisions_sha256_hex`;
  - `ck_document_revisions_media_type`;
  - `ck_document_revisions_byte_size` (`>= 1`);
  - `ck_document_revisions_revision_no` (`>= 1`);
  - `ck_document_revisions_version_label`.
- **Ownership:**
  - `active_revision_id` and `superseded_by_revision_id` are composite FKs that include `tenant_id` and `document_id`. A document can therefore point only to its own revision in its own tenant, and a revision can be superseded only by a revision of the same document and tenant.
  - Cross-tenant and cross-document references are rejected by PostgreSQL, not just by the application.
  - A NULL `active_revision_id` (no active revision yet) passes the FK under the default `MATCH SIMPLE`.
- **Circular references, migration order:**
  1. create `documents` without `fk_documents_active_revision`;
  2. create `document_revisions` with its FKs, including the self-reference;
  3. add `fk_documents_active_revision` with `ALTER TABLE`.

  Downgrade drops that FK first, then `document_revisions`, then `documents`. The FKs are not deferrable: activation sets the revision `active` before updating the pointer, and the pointer FK needs only the row to exist. No `ON DELETE` actions are added: deletion is out of scope for v1, and the default `NO ACTION` blocks it.
- **What PostgreSQL enforces:**
  - tenant and document ownership of every reference;
  - uniqueness of numbers and content per document;
  - at most one `active` revision per document;
  - status values and their timestamp, failure and supersession fields;
  - formats and ranges.
- **What trusted application transitions enforce:**
  - that `active_revision_id` points to the revision whose status is `active` (the pointer and status are changed together in one transaction under the document lock);
  - that `revision_no` stays ≤ `latest_revision_no`;
  - the allowed transition graph and immutability (below).

  No triggers are used. Integration tests check the invariants after every concurrent scenario, as M3a does for jobs.
- **Source content:**
  - The plan stores content in the revision row (`sha256`, `media_type`, `byte_size`, `content_text`); there is no external object store.
  - v1 accepts only `text/plain` and `text/markdown` (M3d parses those).
  - The upload size cap and the HTTP mapping (413, 415, 422) belong to M3e. The database requires only `byte_size >= 1`.
  - **`RevisionContent` is consistent by construction, now, in M3c.** It is built only from the exact uploaded bytes, `RevisionContent.from_bytes(data, media_type)`, which:
    - decodes them as **strict UTF-8** (invalid sequences are rejected, not replaced);
    - rejects NUL (U+0000), which PostgreSQL `text` cannot store;
    - rejects empty input;
    - computes `sha256` and `byte_size` from those same bytes, **with no normalization before hashing** (no newline, BOM or Unicode changes).

    `content_text` is exactly the decoded text. Callers cannot supply a hash or size separately, and a value rebuilt from stored fields is re-verified by re-encoding `content_text` as UTF-8 and checking the hash and size. Mismatches, invalid UTF-8, NUL and unsupported media types raise a fixed `InvalidRevisionContentError` that contains no submitted content, and `repr` of the value shows neither the text nor any excerpt.
  - `chunker_version` (listed in §4) moves to M3d's migration `0004`, which introduces chunking.
  - **Privacy:**
    - content is synthetic demonstration data only;
    - it is never logged and never included in an exception message;
    - it is excluded from `repr` of the domain values;
    - it is returned only through tenant-scoped reads;
    - hashes and sizes may be logged only as fixed fields, if at all, and M3c logs none.

**B. Pure lifecycle (`evidenceguard_domain.revisions`)**

- **Values:**
  - `RevisionStatus`, an enum of the five states;
  - `RevisionFailureCode`, an enum of fixed codes. M3c defines `ingestion_failed`; M3d adds parser-specific codes with review;
  - immutable `DocumentSnapshot`, `RevisionSnapshot` and `RevisionContent` values, with `AwareDatetime` timestamps;
  - every time-dependent rule takes `now` and calls `require_aware`, as M3a does.
- **Transitions** (anything else raises `InvalidRevisionTransitionError`, with a fixed message and no change):

  | From | Rule | To |
  |---|---|---|
  | `pending` | `start_processing` | `processing` |
  | `processing` | `start_processing` (a retry under a newly claimed job attempt) | `processing` (no-op) |
  | `pending`, `processing` | `fail(code)` | `failed` |
  | `failed` | `fail(same code)` | no-op; a different code is a conflict |
  | `processing` | `settle(now, active)` when the document has no active revision, or the active one has a **lower** `revision_no` | `active`; the previous active becomes `superseded`, with `superseded_by` set to the new one |
  | `processing` | `settle(now, active)` when the active revision has a **higher** `revision_no` | `superseded`, with `superseded_by` = the active revision; `activated_at` stays NULL |
  | `active`, `superseded` | `settle` repeated for the same revision | no-op: duplicate activation is idempotent and changes no link or timestamp |
  | `active` | superseded only by a newer revision's `settle` | `superseded` |

  `failed` and `superseded` are terminal. There is no transition back to `pending`.
- **Ordering:** as accepted in §4, a revision is compared with the **currently active** revision, not with the newest uploaded or pending one.
  - Example: revisions 1 (active), 2 and 3 exist. If 2 finishes first, it becomes active and supersedes 1; when 3 finishes, it supersedes 2. If 3 had finished first, 2 would go straight to `superseded` by 3.
  - A failed replacement never touches the active revision: `fail` changes only its own row.
- **Immutable once created:**
  - revisions: `tenant_id`, `document_id`, `revision_no`, `version_label`, `effective_date`, `sha256`, `media_type`, `byte_size`, `content_text` and `created_at`;
  - documents: `tenant_id`, `vendor_id`, `document_key`, `title`, `source_type` and `authenticity`.

  Only status fields, the pointer, `latest_revision_no` and `updated_at` change. The rules return new snapshots and never mutate one.
- **Retryable versus permanent:**
  - A retryable job failure (`RetryableJobError`, lease loss, a crash) leaves the revision `processing`. The next claimed attempt calls `start_processing` again, which is a no-op.
  - Only an explicit permanent ingestion decision by the handler sets `failed`, through `fail_revision` in its own committed fenced transaction (see E). It is not atomic with the job's failure.
  - A `failed` revision is permanent; re-uploading the same bytes returns it (C).

**C. Revision creation (the M3e seam)**

- **The operation:** `create_revision(session, actor, *, vendor_id, document_key, title, source_type, content, version_label, effective_date) -> RevisionCreation(document, revision, created)`.
  - It runs in the **caller's transaction** and never commits, like `enqueue`. M3e creates the revision and its `ingest_revision` job (idempotency key = the revision ID, kind and payload defined in M3d) and commits them together.
  - The tenant comes only from `actor`.
  - **Authorization:** reviewer or approver, as for vendors. M3c checks the role in the operation and raises the existing `PermissionDeniedError`; the endpoint mapping is M3e's.
- **Steps:**
  1. Validate the inputs as domain values; invalid input raises before any SQL.
  2. Require the vendor in the actor's tenant; otherwise raise `VendorNotFoundError` (M3e maps it to 404, like another tenant's vendor).
  3. `INSERT … ON CONFLICT (tenant_id, vendor_id, document_key) DO NOTHING` for the document, then read it with `SELECT … FOR UPDATE` by its tenant-scoped key.
     - That lock serialises every creation for one document. Under READ COMMITTED, `ON CONFLICT` waits for a concurrent inserter, and the locked read then sees the committed row.
     - If the row is not visible (for example under REPEATABLE READ), a fixed `RevisionCreateRaceError` is raised, as M3a's `JobEnqueueRaceError` is.
  4. **Document metadata:** if the existing document's `title` or `source_type` differs from the request, raise `DocumentConflictError` and change nothing. Document metadata is fixed by the first upload; changing it needs a later explicit edit operation.
  5. **Identical content:** if a revision with the same `sha256` exists for this document, compare `media_type`, `version_label` and `effective_date`.
     - Equal: return the existing revision (`created=False`) whatever its status, including `failed`. This is the accepted "identical bytes return the existing revision".
     - Different: raise `RevisionConflictError` and change nothing. A duplicate with different metadata is a conflict, never a silent update.
  6. Otherwise set `latest_revision_no = latest_revision_no + 1` on the locked document and insert the revision as `pending` with that number.

  Numbers are allocated under the document lock, so concurrent creations never duplicate a number. The unique constraint is the backstop: a violation surfaces as a fixed error, not a retry loop.
- **What does not change:** the document's `active_revision_id`, which only activation changes.

**D. Activation and locking**

- **The operations:**
  - `start_processing(session, job)`;
  - `fail_revision(session, job, code)`;
  - `activate_revision(session, job) -> ActivationResult(revision, superseded)`, where `superseded` is the revision demoted by this activation, if any.

  Each runs **inside an open fence**: `session` is the fence's `FencedSession` and `job` is the fence's `JobSnapshot`. That snapshot was checked when the fence opened, **before** M3c's further lock waits, so neither it nor its time is evidence that the lease is still valid afterwards.
- **Binding from trusted persisted data:**
  - the revision ID comes only from the locked job's payload (`revision_id`, the payload key already planned for `ingest_revision`);
  - the tenant comes only from `job.tenant_id`;
  - every lookup is tenant-scoped, so a payload naming another tenant's revision finds nothing and raises `RevisionNotFoundError`;
  - checking the job kind is M3d's handler registration.
- **Lock order** (fixed in M3a; extended here), always:
  1. the job row, already locked by the fence;
  2. the document row: `SELECT … FOR UPDATE` by `(tenant_id, id)`;
  3. the revision rows, in ascending `id` order: the target and, for activation, the current active revision.

  The target's `document_id` is read first without a lock. It is immutable, so reading it unlocked is safe. Status, the pointer and every other mutable field are re-read in statements issued **after** the locks are held; nothing read before a lock wait is reused.

  Creation takes only the document lock and inserts its job row, so it cannot form a cycle with this order.
- **Bounded waits:** the fence's `SET LOCAL lock_timeout = '5s'` covers the whole transaction, including the document and revision locks. A timeout raises the existing `JobLockTimeoutError`, and the transaction rolls back.
- **Fresh ownership re-check after the extra lock waits:** in `start_processing`, `fail_revision` and `activate_revision`, after the document and revision locks are held and the mutable revision and document data have been re-read:
  1. re-read the **currently locked job row together with a fresh `clock_timestamp()`** in one statement. This is M3a's existing `current_state_statement`, executed through the same `FencedSession` in the same transaction; the job row is still locked by this transaction;
  2. apply M3a's pure `holds_lease` rule: the matching `(job_id, worker_id, attempt)` token, status `running`, and `lease_expires_at` later than that fresh time. The token carries no tenant, so the **M3c caller separately verifies** that the re-read job row's `tenant_id` equals the tenant of the locked revision and document;
  3. if the check fails, raise the existing fixed `LeaseLostError` before any revision or document write, so the transaction rolls back and nothing changes;
  4. use **that fresh time**, never the earlier snapshot's time, as `now` for the revision rules and timestamps.

  M3a's persistence module exposes this as one public helper, `recheck_ownership(session: FencedSession, token) -> tuple[JobSnapshot, datetime]`. It validates the token, the `running` status and expiry, and returns the re-read job, from which the caller checks the tenant, together with the fresh time. It wraps the existing statement and rule and adds no transition. Transaction ownership is unchanged: the fence still owns the transaction, the helper only reads, and handlers still get no lifecycle methods.
- **The accepted M3a limit still applies:** a transaction that passes this re-check just before expiry may commit shortly after it. Ownership is checked at these explicit points, not continuously during every statement.
- **`activate_revision`, in order, in the fence's single transaction under the document lock:**
  1. lock the document, then the revisions (the order above);
  2. re-read the document and the target, and the current active revision if there is one;
  3. run the fresh ownership re-check, which yields `now`;
  4. apply the pure `settle` rule;
  5. write the result:
     - **Newer than the active revision (or none active):**
       1. **demote** the old active revision to `superseded`, with `superseded_at = now` and `superseded_by_revision_id` = the target;
       2. **promote** the target to `active`, with `activated_at = now`;
       3. **update the pointer**: `active_revision_id` = the target, and `updated_at`.

       Demoting first is required because the one-active partial unique index is checked immediately, statement by statement. The intermediate state with no active revision exists only inside this uncommitted transaction and is never published.
     - **Older than the active revision (finishing late):** mark only the target `superseded`, with `superseded_at = now` and `superseded_by_revision_id` = the active revision. The active revision, the pointer and the document's `updated_at` are not touched.
     - **Duplicate** (the target is already `active` or `superseded`): no write at all. No timestamp, link or document `updated_at` changes, and the job can still finish.
- **Concurrent activations** of two revisions of one document (two different jobs) serialise on the document lock. The second sees the first's committed result and settles against it, so the pointer and the single `active` status stay consistent, and the newer `revision_no` always wins.
- **A stale worker cannot activate:** a reclaimed attempt fails the fence's ownership check with `LeaseLostError` before any of these statements run.
- **Failure and commit semantics:**
  - **A failure before the commit** (in activation, in the runtime's `succeed`, or a crash before `COMMIT`) rolls back the revision changes, the pointer and the job's success together.
  - **A successful commit** persists them together.
  - **If the commit acknowledgment fails**, the outcome is unknown: either both committed or neither did. The worker's uncertain-finish behaviour (ADR-0008) claims no success, and recovery depends on what actually happened:
    - **It committed:** the job is `succeeded` and cannot be reclaimed. The runtime's later fenced outcome attempt is refused (`LeaseLostError`, logged as `job.outcome_unknown`), and no second activation occurs.
    - **It did not commit:** the job is still `running` under this attempt. The runtime's fenced retry is recorded, or the lease expires and the job is reclaimed. The revision is still `processing`, and the next valid attempt activates it normally.
  - An uncertain acknowledgment is never treated as a proven rollback.
  - **A raised commit exception alone never proves that the previous state is intact.**
- **No parsing, provider or network calls happen while these locks are held.** M3d does that work in earlier fenced transactions or outside them.

**E. The M3d handler seam**

- **The intended M3d handler:**
  1. `with ctx.fenced(): start_processing(fence.session, fence.job)`;
  2. parse and chunk outside the fence;
  3. write chunks in short fenced transactions (idempotent, keyed by chunk ID);
  4. finally `with ctx.fenced(finish=True): activate_revision(fence.session, fence.job)`.

  The activation and the job's `succeeded` then commit together (ADR-0008's atomic finish).
- **Permanent ingestion failure, with the existing M3b interfaces:**
  1. `with ctx.fenced(): fail_revision(fence.session, fence.job, RevisionFailureCode.INGESTION_FAILED)`. The block **does not raise**, so it commits the revision's `failed` state;
  2. **after** that block, the handler raises `PermanentJobError(JobErrorCode.PERMANENT_FAILURE)`;
  3. the supervisor records the job's permanent failure in a **separate** fenced transaction.

  Raising inside the block would roll back `fail_revision`, so it must not.
  - **The gap between the two commits is real:** revision failure and job failure are **not** atomic with the current interface.
  - **If the worker crashes in that gap**, the job is later reclaimed. The handler must first read the revision: if it is already `failed`, it raises `PermanentJobError(JobErrorCode.PERMANENT_FAILURE)` at once, without calling `start_processing` or ingesting again.
  - **The two code types stay distinct.** `RevisionFailureCode` (stored in `failure_reason`) and `JobErrorCode` (stored in the job's `last_error`, and required by the existing `PermanentJobError`) are different types, and a revision code is never passed to `PermanentJobError`. The initial mapping is `INGESTION_FAILED` → `PERMANENT_FAILURE`. Parser-specific revision codes and any finer job-code mapping belong to M3d's review.
  - Any future interface for atomic revision-and-job failure needs a separate review.
- **Exhausted jobs:**
  - A job can become `dead` while its revision is still `pending` or `processing`. That happens when a lease is abandoned (even before `start_processing` ran) and the claim sweep marks the job dead, or when the final attempt fails retryably.
  - M3c adds **no reconciliation**. The previously active revision is unaffected either way.
  - A reconciliation step, or a truthful stalled/dead projection of such revisions, is a **required M3d/M3e design item before overall M3 acceptance**.
- **Interface:** M3c functions accept the existing `FencedSession` (which `HandlerFence.session` exposes) and the fence's `JobSnapshot`.
  - They issue statements only through `FencedSession`, which has no `commit`, `rollback` or `close`, so they cannot end the caller's transaction.
  - They never open their own transaction.
- **`create_revision`** takes an ordinary caller-owned `Session` instead (the API transaction), like `enqueue`.
- **No production handler is registered in M3c.**

**F. Verification plan**

- **Planned files:**
  - `packages/domain/evidenceguard_domain/revisions.py`;
  - `packages/persistence/evidenceguard_persistence/documents.py`;
  - the read-only `recheck_ownership` helper added to `packages/persistence/evidenceguard_persistence/jobs.py`, with no change to existing operations;
  - model additions in `models.py`;
  - `migrations/versions/v0003_documents.py`;
  - `tests/test_revisions.py`, `tests/test_document_store.py` and `tests/test_documents_postgres.py`;
  - updates to the migration-head pins (`0002` → `0003`) in `tests/test_persistence.py`, `tests/test_persistence_postgres.py` and `tests/test_readiness.py`;
  - ADR-0009;
  - status updates to the README, plan and threat model.

  No workflow change: the installed-wheel step already renders all migrations offline.
- **Pure tests:**
  - the exhaustive transition table, including every invalid transition;
  - the ordering rule against the active revision;
  - idempotent repeats and conflicting failure codes;
  - immutability (frozen values; transitions never change immutable fields);
  - aware-time enforcement;
  - fixed error messages without values;
  - content excluded from `repr`;
  - `RevisionContent`:
    - the hash and size are computed from the exact bytes, with no normalization (CRLF, BOM and non-ASCII samples);
    - invalid UTF-8, NUL, empty input and unsupported media types are rejected;
    - inconsistent stored fields fail re-verification;
    - errors and `repr` contain no submitted text.
- **Database-independent persistence tests** (the scripted-session double of M3a):
  - compiled SQL shows tenant scoping and `FOR UPDATE` in the lock order;
  - fresh reads after the locks;
  - invalid input rejected before any SQL;
  - functions never call `commit`;
  - the ownership re-check (job row plus `clock_timestamp()`) is issued after the document and revision locks and before any write, and its time, not the snapshot's, is used;
  - a job tenant different from the revision's is refused before any write;
  - the activation statement order is demote, promote, then pointer;
  - a late older revision writes only its own row;
  - a duplicate activation writes nothing.
  - **Uncertain commit, with controlled doubles** (kept separate from real rollback tests):
    - the commit applied but its acknowledgment failed: success is not claimed, the job is `succeeded` and is never reclaimed, the runtime's later fenced outcome is refused, and exactly one activation exists;
    - the commit did not apply: the job is retried or reclaimed, the revision is still `processing`, and the next valid attempt activates it; exactly one activation exists.
  - **Duplicate activation, tested separately:** a valid fenced invocation for a revision that is already settled writes nothing. This test does not use a succeeded job.
  - **The failure seam:** `fail_revision` records `INGESTION_FAILED` and commits in a block that does not raise; `PermanentJobError(JobErrorCode.PERMANENT_FAILURE)` is raised afterwards. A reclaimed attempt that finds the revision `failed` raises the same job error without `start_processing`.
- **PostgreSQL integration tests** (guarded disposable fixtures, a server-side `statement_timeout`, event-controlled concurrency, bounded waits):
  - **Migration:**
    - the `0003` upgrade, downgrade and re-upgrade;
    - `alembic check` reports no drift;
    - readiness is ready only at `0003`;
    - the offline SQL renders `documents` and `document_revisions`.
  - **Constraints:**
    - every check;
    - the one-active partial index;
    - cross-tenant `vendor_id`;
    - cross-tenant and cross-document `active_revision_id` and `superseded_by_revision_id` are rejected.
  - **Creation:**
    - concurrent creations of new revisions for one document get distinct consecutive numbers;
    - concurrent identical-content creations return one revision;
    - metadata conflicts change nothing;
    - another tenant's vendor is not found;
    - a revision and a job created in one caller transaction commit or roll back together.
  - **Activation:**
    - first activation;
    - a newer revision supersedes the active one;
    - **a failed replacement leaves the previous revision active**;
    - **two revisions finishing out of order leave only the newer active**;
    - concurrent activations of two revisions keep one consistent pointer;
    - the replacement path works with the real one-active partial unique index (demote, then promote, then pointer);
    - an injected failure **between demotion and promotion** rolls back to the previous active revision and pointer;
    - an injected failure before the commit (in activation or the job's `succeed`) rolls back the revision changes, the pointer and the job's success together;
    - **a stale attempt cannot activate** after a reclaim;
    - **the lease expires during the document-lock wait:**
      1. the worker holds its job fence;
      2. it waits on a document lock held by the test;
      3. the lease expires during that wait, within the lock-timeout bound;
      4. the lock is released.

      Activation is then refused with `LeaseLostError`, and the revision states, the active pointer and the job outcome are unchanged;
    - a duplicate activation is a no-op;
    - a lock held beyond `lock_timeout` raises the fixed timeout error.
  - **The atomic finish:** activation through the worker's `ctx.fenced(finish=True)` with a test-only handler under `tests/`, completing job and activation together.
- **Result:** the PostgreSQL integration tests listed above passed against PostgreSQL in the CI integration job at `8646b75` (`133 passed, 819 deselected`, from the log retrieved by the external reviewer). The database-independent tests above, including the controlled uncertain-commit simulations, ran in the Ubuntu and Windows verify jobs, not against PostgreSQL.

**Settled at review (Prompt 68):**
1. The schema above, including the `(tenant_id, document_id, id)` pointer FKs, the one-active partial index, `latest_revision_no` as the allocation counter, and no triggers.
2. Content stored in the revision row as decoded text, with `sha256` and `byte_size` describing the uploaded bytes; `chunker_version` moves to M3d.
3. Document metadata fixed by the first upload, and duplicate content with different metadata a conflict.
4. Identical bytes return the existing revision even if it is `failed`; there is no automatic re-ingestion.
5. M3c operations accept `FencedSession` plus the fence's `JobSnapshot`, and bind to the revision only through the job's tenant and `revision_id` payload.
6. The lock order job → document → revisions (ascending `id`), within the fence's 5 s `lock_timeout`, followed by the fresh ownership re-check through a new read-only `recheck_ownership` helper in M3a's persistence module (token, status, expiry); the M3c caller checks the tenant.
7. `RevisionFailureCode` starts with `ingestion_failed`; M3d adds codes with review.
8. Activation writes in the order demote, promote, pointer; a late older revision writes only its own row, and a duplicate writes nothing.
9. `RevisionContent` is built only from the exact bytes, with strict UTF-8, no NUL and no normalization.
10. Permanent failure commits `fail_revision` (`INGESTION_FAILED`) first, then the job fails separately with `PERMANENT_FAILURE`; the gap and its recovery are as described in E.
11. A job left `dead` with its revision unsettled must have reconciliation or a truthful projection before overall M3 acceptance.

**Recorded limitations and required follow-ups:**
- **Dead job with an unsettled revision:** a `dead` job can leave its revision `pending` or `processing` (E). M3c adds no reconciliation. Reconciliation or a truthful stalled/dead projection is a **required M3d/M3e design item before overall M3 acceptance**.
- **Non-atomic failure:** revision failure and job failure are separate commits with the current worker interface (E).
- **No retry of failed content:** retrying a `failed` revision with identical bytes is not possible in v1 (decision 4).

**Conflicts with accepted decisions:** none found.
- Ordering against the active revision, failed replacements and identical-bytes idempotency follow §4.
- The lock order extends M3a's "job, then document".
- The binding uses the payload key already planned for `ingest_revision`.
- Moving `chunker_version` and the `evidenceguard_domain.state` naming change only planned details, and were accepted at review.

**M3d, parsing, chunking and the first production handler, in detail (ACCEPTED at review, Prompt 76, corrected in Prompts 77–79; implemented in Prompts 80–81, reviewed, and verified in CI on `feat/document-ingestion` at `74904e6`, see [ADR-0010](decisions/0010-document-ingestion.md); on `main` at `cdf7260`):**

M3d turns a `pending` revision into a verified set of chunks and activates it. It uses the M3a fence, the M3b worker and the M3c lifecycle, with two small additive interface changes to M3c (C): a public name for M3c's existing lock helper and an optional `before_settle` argument. It is the slice that carries the M3 criteria "chunk IDs include tenant and revision" and "a stale worker cannot write chunks".

**Already decided (not reopened here):**
- The scope:
  - only `text/plain` and `text/markdown`, already validated as strict UTF-8 without NUL by M3c's `RevisionContent`;
  - a deterministic chunker v1;
  - a `chunks` table in migration `0004`;
  - the `ingest_revision` handler.
- The chunk-ID formula (correction A): `uuid5(NS, f"{tenant_id}:{revision_id}:{chunker_version}:{ordinal}")`, with uniqueness `(tenant_id, revision_id, chunker_version, ordinal)` and a tenant-scoped foreign key to the revision.
- The §5 chunking rules: split at Markdown headings; pack paragraphs to about 2,500 characters with no overlap; a table is one chunk; long tables are split by rows with the header repeated; plain text splits at blank lines.
- `chunker_version` moved to `0004` (M3c, settled decision 2).
- The job kind `ingest_revision`, payload `{"revision_id": …}` and idempotency key equal to the revision ID (M3a, M3c).
- The handler seam, the permanent-failure protocol and its crash gap (M3c, E).
- Chunks are immutable once their revision is active, and re-chunking is out of scope.

**Out of scope:**
- embeddings, the `vector` extension, `ChunkEmbedding`;
- the lexical `tsvector` column and the `injection_flag` heuristic (M4–M5);
- retrieval, model calls;
- upload and document endpoints, including the chunk-inspection endpoint (M3e);
- Docker (M3f).

Everything else below was proposed in Prompt 76 and is marked *(proposed)* where a choice was new. **The external review accepted it** (Prompt 79): the parser grammar and provenance rules; the chunk limits and batch bounds; `chunk_sets` and `chunks`; deterministic IDs and canonical manifests; shared lifecycle locking; the optional completeness callback; the handler and failure protocol; and the M3e derived status projection with its acceptance obligation. The numeric limits and bounds are accepted as **initial engineering defaults, not measured performance results**.

**A. Parsing and provenance** *(proposed)*

- **Module:** `evidenceguard_retrieval.chunking`, in the planned `packages/retrieval/evidenceguard_retrieval/` package (§3). It is pure code with no I/O. It imports only `evidenceguard_domain` and is added to the wheel's package list and the import-boundary test.
- **Input:** the revision's stored `content_text`, rebuilt with `RevisionContent.from_stored`, which re-verifies the uploaded-byte `sha256` and `byte_size`, together with its `media_type`.
- **What the parser is not:**
  - not a Markdown renderer: it does not interpret inline syntax, HTML, links or images;
  - it executes nothing;
  - it performs no network or filesystem access.
- **Determinism:** the output is a pure function of `(content_text, media_type, CHUNKER_VERSION)`. Locale, environment and platform do not affect it.
- **Constants:**
  - `CHUNKER_VERSION = "text-md-v1"`;
  - `TARGET_CHARS = 2500`;
  - `MAX_CHUNK_CHARS = 4000`;
  - `MAX_HEADER_REPEAT_CHARS = 1000`;
  - `MAX_CHUNKS_PER_REVISION = 4096`.

  Lengths are counted in Unicode code points of the chunk text.

**Lines and offsets**
- **Lines:** a line ends at LF. A CR immediately before that LF belongs to the terminator, so CRLF and LF files give the same line numbers. A lone CR, U+2028, VT and FF are ordinary characters.
- **Numbering:** lines are numbered from 1. A final line without a terminator counts; a file ending in a terminator has no extra empty line.
- **Line content:** a line's content is the line without its terminator.
- **Character offsets:** zero-based, half-open code-point offsets into the stored `content_text`, as Python string indices.
- **BOM:** a leading U+FEFF stays in `content_text`, and therefore in the byte hash, and keeps its offset 0. It is excluded from every chunk span, so the first chunk starts at offset 1 on line 1. For every rule below (classification, the blank-line predicate, empty documents and splitting), line 1's content starts after the BOM, so a line holding only a BOM is blank.
- **No normalization:** there is no newline, Unicode or whitespace normalization of the source or the chunk text. Characters inside a span are copied verbatim, including CR, tabs and leading or trailing spaces on lines.
- **Whitespace predicate (one definition for every rule):** the only whitespace characters are U+0020 (space) and U+0009 (tab).
  - A line is **blank** when its content is empty or consists only of whitespace.
  - Every other character is non-whitespace for blank lines, empty documents and split points alike. That includes a lone CR, NBSP (U+00A0), U+3000 and U+2028.

**Blocks**
- **Plain text:** maximal runs of non-blank lines. Section path is always `[]`.
- **Markdown classification:** the text is scanned line by line, top to bottom. Outside a fence, each non-blank line is classified in this order, and the first match wins:
  1. **Fence opening:** 0–3 spaces, then a run of at least three backticks or at least three tildes (the fence character *c* and run length *n*), then an optional info string. For a backtick fence the info string must not contain a backtick; if it does, the line is not a fence opening.
  2. **ATX heading:** 0–3 spaces, 1–6 `#`, then a space, a tab or the end of the content.
  3. **Table start:** a line containing `|` whose next line is a delimiter row. A delimiter row has content matching `^ {0,3}\|?[ \t]*:?-+:?[ \t]*(\|[ \t]*:?-+:?[ \t]*)*\|?[ \t]*$` and contains at least one `|`.
  4. **Paragraph line:** anything else.
- **Fenced code blocks:**
  - A fence opened with character *c* and run length *n* closes only at a line whose content is 0–3 spaces, then a run of *c* of length ≥ *n*, then only whitespace.
  - These lines are fence content, **not** closers: a line with an info string or other text after the run, fewer than *n* fence characters, the other fence character, or four or more leading spaces.
  - The block runs from the opening line through the closing line, and blank lines inside a fence do not split it.
  - An unclosed fence runs to the end of the document. This is deterministic, not an error.
- **Headings:**
  - Heading text is the content after the `#` run, with surrounding whitespace removed and an optional closing sequence of `#` removed (one preceded by whitespace, or one that makes up the whole text).
  - The section path stores the text truncated to 200 code points, with trailing whitespace then removed. The chunk text keeps the whole line.
  - Setext headings, and heading-like lines inside fences, are ordinary lines.
- **Tables:**
  - A table block starts at its table-start line and includes the delimiter row. It continues over the following lines that are non-blank, contain `|`, and are neither a fence opening nor an ATX heading.
  - Its **header segment** is the header row and the delimiter row, including the delimiter row's line terminator. A **header-only table** has no body rows.
- **Paragraphs:**
  - A paragraph is a maximal run of paragraph lines.
  - **A paragraph stops before** a blank line, a fence opening, an ATX heading or a table start, **even when no blank line separates them**.
  - The parser is not a general Markdown implementation; these four classifications are its whole grammar.
- **Section path:** a heading at level *n* drops every path entry of level ≥ *n* and appends its text. `# A` then `### C` gives `["A", "C"]`, and content before the first heading has path `[]`.

**Chunks**
- **Sections:** the general rule is that every heading starts a new chunk, so a chunk never contains content from two sections.
  - **Consecutive headings (the exception):** a *heading run* is a maximal sequence of ATX headings separated only by blank lines. The whole run is one block and starts one chunk.
    - The chunk's first line is the run's first heading line.
    - Its section path is the path after applying every heading in the run, in order. `# A`, `## B` gives `["A", "B"]`; `## B`, `## C` gives the parent path plus `"C"`.
    - Every heading line of the run is in the chunk text, but only the path after the last one is recorded.
  - The heading run is packed with the content blocks that follow it in its section, by the normal packing rule.
  - A heading run with nothing after it before the end of the document is a chunk of its own.
- **Packing (prose):**
  - Within a section, consecutive non-table blocks are packed greedily, in document order.
  - A chunk is the verbatim slice from the start of its first block to the last character of its last block's content, so the final line terminator is excluded.
  - Blank lines between packed blocks are included verbatim.
  - The next block is added only while the slice stays ≤ `TARGET_CHARS`.
- **Size limits:** `TARGET_CHARS` is a **hard limit for prose chunks** and a packing target for table chunks. `MAX_CHUNK_CHARS` is the **absolute limit for every chunk**, and a database CHECK enforces it.
- **Oversized prose blocks:** a block longer than `TARGET_CHARS` on its own, including a heading run or a fence, is split at line boundaries into greedy runs of whole lines, each ≤ `TARGET_CHARS`. A run never starts or ends with a blank line, so blank lines at a split point belong to no chunk.
  - Each run or piece of a split block is a chunk of its own; it is never packed with a neighbouring block.
  - **Oversized lines:** a line whose content is longer than `TARGET_CHARS`, including a heading line, is cut into pieces that are emitted alone, never packed with neighbouring lines.
    - The cut text is the line content with leading and trailing spaces and tabs removed; those removed runs belong to no chunk. The remaining text therefore always starts and ends with a non-whitespace character.
    - While the remaining text is longer than `TARGET_CHARS`: find the last whitespace character at code-point index *i* with `TARGET_CHARS/2 ≤ i ≤ TARGET_CHARS`. The piece is the remaining text before the run of spaces and tabs that contains *i*. That whole run is skipped, and the remaining text then starts at the first non-whitespace character after it.
    - If there is no such whitespace, the piece is cut hard at exactly `TARGET_CHARS` code points and nothing is skipped. The character at index `TARGET_CHARS` is then non-whitespace, because it was in the searched range.
    - Once the remaining text is ≤ `TARGET_CHARS`, it is the last piece.
    - So every piece is non-empty and starts and ends with a non-whitespace character.
  - **Only permitted omissions.** A split point may omit only LF and CRLF line terminators and spaces and tabs (including the content of blank lines). It never omits any other character, so a lone CR, NBSP and every other character outside the whitespace predicate are always kept.
  - Every piece is a verbatim contiguous slice of at most `TARGET_CHARS` code points. A piece within one line has `line_start = line_end`.
  - **Oversized headings:** every run or piece of a split heading run, including the pieces of an oversized heading line, carries the run's section path (the path after its last heading), and the content that follows keeps the same path.
- **Tables:** a table is never packed with prose, and every table chunk has `is_table = true`.
  - **Small tables:** a table whose slice is ≤ `TARGET_CHARS` is one contiguous chunk. That includes a header-only table that fits.
  - **Header segment longer than `TARGET_CHARS`** (including a header-only table that does not fit): the whole table is split as an oversized prose block, first into line runs and then into oversized-line pieces. The header is never repeated, and every piece is ≤ `TARGET_CHARS`.
  - **Longer tables** are split by rows:
    - The first chunk is the contiguous slice from the header row through as many body rows as fit within `TARGET_CHARS`, which may be the header segment alone.
    - Each continuation chunk is the **repeated header segment** followed by as many further rows as fit, but only if the header segment is ≤ `MAX_HEADER_REPEAT_CHARS`. Otherwise continuation chunks contain rows only.
  - **Oversized rows:** a row that does not fit within `TARGET_CHARS` together with a repeatable header is emitted with that header if header plus row is ≤ `MAX_CHUNK_CHARS`. Otherwise the row is emitted without the header, as one chunk if it is ≤ `TARGET_CHARS` or as oversized-line pieces if it is longer.
  - **Bound:** a repeated header is at most 1,000 code points and is emitted with a row only when the total is ≤ `MAX_CHUNK_CHARS`. Every other chunk is ≤ `TARGET_CHARS`. So every emitted chunk is within the absolute cap.
- **Ordinals:** zero-based and contiguous in document order.
- **Coverage invariant (enforced by the database-independent tests in `tests/test_chunking.py`):** the source characters fall into four groups:
  1. a leading BOM, which is never in a span;
  2. LF and CRLF line terminators, which may be omitted between chunks;
  3. spaces and tabs, which may be omitted only where the rules above permit (blank lines, split points and trimmed oversized lines);
  4. every remaining source character, including a lone CR and NBSP.

  Every character in group 4, and every group 2 or 3 character that is not omitted, appears in exactly one chunk's body span (`char_start`/`char_end`). The body spans are disjoint and in ascending source order. A repeated header is an additional context copy, carried only in the header span; it does not count as body coverage.

**Provenance and the source mapping**
- Each chunk records `char_start`/`char_end` and `line_start`/`line_end`. `line_start` is the line of `char_start`, and `line_end` is the line of `char_end − 1`.
- **Contiguous chunks** (`header_char_start` is null): `text == content_text[char_start:char_end]` exactly.
- **Table continuation chunks with a repeated header:** `text == content_text[header_char_start:header_char_end] + content_text[char_start:char_end]`.
  - `header_line_start` and `header_line_end` give the header's own lines.
  - There is no synthetic separator, because the header segment ends with its own terminator.
  - The body span alone is the verbatim source passage. **Such a chunk is not one contiguous source passage**, and later citation display (M5) must cite the body lines, with the header labelled as repeated context.
- **Byte fingerprints:** the uploaded-byte `sha256` and `byte_size` on the revision are unchanged and remain the only byte fingerprints. Each chunk adds `content_sha256` = SHA-256 of its UTF-8 `text`.

**Errors**
- **Empty document:** a document is **empty** when, with a leading BOM excluded, every line is blank under the whitespace predicate. It produces no chunks and is a permanent revision failure `empty_document` (D).
- **More than `MAX_CHUNKS_PER_REVISION` chunks:** permanent `chunk_limit_exceeded`.
- **Malformed input:** there is none at this layer. Any strict-UTF-8 text without NUL parses deterministically, and malformed Markdown is just text.
- **Integrity mismatch:** if `from_stored` refuses the stored row (hash, size or encoding mismatch), that is permanent `content_integrity_failed`.
- **Privacy:** parser errors carry fixed messages and never include content.

**Examples (normative):**
1. **Headings.** The source is `"# Retention\n\nCustomer data is kept for 90 days.\n\n## Backups\n\nBackups are encrypted.\n"`. It has 84 code points and 7 lines.
   - **Chunk 0:** path `["Retention"]`, lines 1–3, chars [0, 47), text `"# Retention\n\nCustomer data is kept for 90 days."`.
   - **Chunk 1:** path `["Retention", "Backups"]`, lines 5–7, chars [49, 83), text `"## Backups\n\nBackups are encrypted."`.
2. **CRLF and BOM.** Plain text `"Line one\r\nLine two\r\n"` gives one chunk: lines 1–2, chars [0, 18), text `"Line one\r\nLine two"`. Plain text `"\ufeffTitle line\n"` gives one chunk: line 1, chars [1, 11), text `"Title line"`.
3. **Long text.** Plain text `" ".join(["alpha"] * 1000)` is one line of 5,999 code points. It gives three chunks on line 1: chars [0, 2495), [2496, 4991) and [4992, 5999). Each split falls at the last whitespace within [1,250, 2,500] code points of the remaining text, and the single spaces at offsets 2495 and 4991 belong to no chunk.
4. **Table rows and a repeated header** (illustration only, with `TARGET_CHARS` lowered to 48; v1 uses 2,500). The source is `"| Region | Provider |\n|---|---|\n| EU | Alpha |\n| US | Beta |\n| APAC | Gamma |\n"`, and its header segment is chars [0, 32), lines 1–2.
   - **Chunk 0:** contiguous, lines 1–3, chars [0, 46).
   - **Chunk 1:** header [0, 32) lines 1–2, plus body chars [47, 60) line 4; text `"| Region | Provider |\n|---|---|\n| US | Beta |"`.
   - **Chunk 2:** header [0, 32), plus body [61, 77) line 5.
5. **Heading directly after prose.** Markdown `"Intro text.\n# Scope\nOnly EU data.\n"` has no blank line before the heading. It gives two chunks:
   - **Chunk 0:** path `[]`, line 1, chars [0, 11), text `"Intro text."`.
   - **Chunk 1:** path `["Scope"]`, lines 2–3, chars [12, 33), text `"# Scope\nOnly EU data."`.
6. **Consecutive headings.**
   - `"# A\n\n## B\n\nBody.\n"` gives one chunk: path `["A", "B"]`, lines 1–5, chars [0, 16).
   - `"# A\n## B\n"`, with no content, gives one chunk: path `["A", "B"]`, lines 1–2, chars [0, 8).
7. **Oversized heading.** Markdown `"# " + " ".join(["word"] * 600)` is one heading line of 3,001 code points. It gives two chunks on line 1: chars [0, 2496) and [2497, 3001); the space at offset 2496 belongs to no chunk.
   - Both chunks have the path `["word word … word"]`: the heading text truncated to 200 code points, then trailing whitespace removed, leaving 40 words in 199 code points.
8. **Oversized and header-only tables.**
   - Header-only: `"| a | b |\n|---|---|\n"` gives one chunk with `is_table = true`, lines 1–2, chars [0, 19).
   - Oversized header (illustration only, with `TARGET_CHARS` lowered to 20): `"| Region | Provider |\n|---|---|\n| EU | Alpha |\n"` has a 32-code-point header segment. The table is split as an oversized prose block into four table chunks with no repeated header:
     - [0, 19) `"| Region | Provider"`;
     - [20, 21) `"|"` (the space at offset 19 is skipped);
     - [22, 31) `"|---|---|"`;
     - [32, 46) `"| EU | Alpha |"`.
9. **Whitespace-only source.**
   - `" \t\r\n\n  \n"` is empty: its line contents are `" \t"`, `""` and `"  "`, and the CR belongs to the first terminator. It is refused with `empty_document`.
   - `"\ufeff\n  \n"` is empty: after the BOM, line 1's content is `""`.
   - `"\u00a0\n"` (NBSP, then LF) is not empty, because NBSP is not whitespace. It gives one chunk at chars [0, 1).

**B. Chunk contract and schema (migration `0004`)** *(proposed)*

- **Home of `chunker_version` and the completeness manifest:** a new `chunk_sets` table, with one row per revision in v1. Its `chunker_version` is authoritative. Each chunk repeats `chunker_version` and references its set through a composite foreign key, so the two can never disagree. The revision table is unchanged.
- **`chunk_sets`:**

  | Column | Type | Notes |
  |---|---|---|
  | `tenant_id` | uuid not null | FK → `tenants(id)` |
  | `revision_id` | uuid not null | composite FK `(tenant_id, revision_id)` → `document_revisions (tenant_id, id)` |
  | `chunker_version` | varchar(32) not null | CHECK `chunker_version ~ '^[a-z0-9][a-z0-9.-]{0,31}$'` |
  | `chunk_count` | integer not null | CHECK `chunk_count BETWEEN 1 AND 4096` |
  | `manifest_sha256` | varchar(64) not null | CHECK 64 lowercase hex |
  | `created_at` | timestamptz not null default `now()` | |

  - **Keys:** PK `(tenant_id, revision_id)` (`pk_chunk_sets`); unique `(tenant_id, revision_id, chunker_version)`. The table has no `id` column.
- **Manifest:** `manifest_sha256` is the lowercase hexadecimal SHA-256 of the manifest bytes.
  - **Contents:** a JSON array with one object per chunk, in ascending `ordinal` order (0, 1, …). Each object has exactly these keys: `char_end`, `char_start`, `content_sha256`, `header_char_end`, `header_char_start`, `header_line_end`, `header_line_start`, `id`, `is_table`, `line_end`, `line_start`, `ordinal`, `section_path`.
  - **Encoding:** Python's `json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)`, encoded as ASCII bytes. So keys are sorted by code point, there is no whitespace, and every non-ASCII character is a `\uXXXX` escape (surrogate pairs above the BMP).
  - **Values:** UUIDs are lowercase hyphenated strings. Integers are JSON integers, booleans are `true`/`false`, absent header fields are `null`, `section_path` is an array of strings and `content_sha256` is a lowercase hex string.

  The manifest lets the final transaction verify a complete, exact chunk set from stored fields, without re-reading text or parsing.
- **`chunks`:**

  | Column | Type | Notes |
  |---|---|---|
  | `id` | uuid PK | `uuid5(CHUNK_ID_NAMESPACE, f"{tenant_id}:{revision_id}:{chunker_version}:{ordinal}")` |
  | `tenant_id` | uuid not null | FK → `tenants(id)` |
  | `revision_id` | uuid not null | |
  | `chunker_version` | varchar(32) not null | composite FK `(tenant_id, revision_id, chunker_version)` → `chunk_sets` |
  | `ordinal` | integer not null | CHECK `ordinal BETWEEN 0 AND 4095` |
  | `text` | text not null | CHECK `char_length(text) BETWEEN 1 AND 4000` |
  | `content_sha256` | varchar(64) not null | CHECK 64 lowercase hex |
  | `section_path` | text[] not null default `'{}'` | CHECK `cardinality(section_path) <= 6` |
  | `is_table` | boolean not null | |
  | `line_start`, `line_end` | integer not null | CHECK `line_start >= 1 AND line_end >= line_start` |
  | `char_start`, `char_end` | integer not null | CHECK `char_start >= 0 AND char_end > char_start` |
  | `header_line_start`, `header_line_end`, `header_char_start`, `header_char_end` | integer null | CHECK all four null or all four set; set only when `is_table`; `header_char_end <= char_start`; `header_line_end < line_start` |
  | `created_at` | timestamptz not null default `now()` | |

  - **Keys:** unique `(tenant_id, revision_id, chunker_version, ordinal)` and unique `(tenant_id, id)`, for later tenant-scoped references from embeddings and citations.
  - **Indexes:** the unique indexes serve the lookups by revision; no other index is added in v1.
- **Namespace and names:**
  - `CHUNK_ID_NAMESPACE = UUID("973dffe5-e145-5fd2-833e-6793460ee3be")`, derived once as `uuid5(NAMESPACE_URL, "https://evidenceguard.invalid/namespaces/chunk-id/v1")` and then **fixed as a literal**.
  - The name string uses canonical lowercase hyphenated UUIDs and a decimal ordinal.
  - Example: tenant `11111111-1111-4111-8111-111111111111`, revision `22222222-2222-4222-8222-222222222222`, version `text-md-v1`, ordinal 0 gives `a11668be-c537-5f4d-b5d8-7a056099b8a0`. The same revision ID under tenant `33333333-3333-4333-8333-333333333333` gives `53214eae-4b9a-5805-a6e7-41a8e3b6341c`.
- **Immutability:**
  - No code path updates or deletes `chunk_sets` or `chunks`: writes are `INSERT … ON CONFLICT DO NOTHING` followed by verification.
  - This is an **application invariant**. There are no triggers, consistent with ADR-0009, and the database does not stop a privileged session from updating rows.
  - Re-chunking active revisions is out of scope.
- **Migration `0004`** (`v0004_chunks.py`, down-revision `0003`, constraint text spelled literally):
  - **Upgrade:** creates `chunk_sets`, then `chunks`. There are no circular references, and no extension or embedding table.
  - **Downgrade:** drops `chunks`, then `chunk_sets`.
  - **Test updates:** the head pins in `test_persistence.py`, `test_readiness.py` and `test_persistence_postgres.py` move to `0004`. The round-trip test steps down through `0003` (asserting the M3c tables remain), then `0002`, `0001` and base, then re-upgrades. An offline-render test checks every constraint and the absence of `vector`, `EXTENSION` and `TRIGGER`. Historical migration tests are kept.

**C. Persistence operations and fencing** *(proposed)*

New module `evidenceguard_persistence.chunks`. All its functions take M3a's `FencedSession` and the fence's `JobSnapshot`, scope every statement by the job's tenant, and never commit, roll back or issue transaction-control SQL.

- **`load_revision_source(session, job) -> RevisionSource`:**
  - reads `status`, `media_type`, `content_text`, `sha256` and `byte_size` of the payload's revision in the job's tenant (missing → `RevisionNotFoundError`);
  - rebuilds `RevisionContent.from_stored`;
  - returns a frozen value whose `repr` shows only the revision ID, status, media type and size.

  It takes no lock. Content never appears in a repr, log event or exception message.
- **Shared lock helper:** M3c's existing private helper `_lock`, which `start_processing`, `fail_revision` and `activate_revision` already use, becomes the public `lock_revision_for_job(session, job, *, include_active)`. The code, lock order and checks are unchanged:
  1. the job row, already locked by the fence;
  2. the document row (`FOR UPDATE`);
  3. the required revision rows (`FOR UPDATE`, ascending ID);
  4. then `recheck_ownership` with fresh `clock_timestamp()` and the tenant check.

  It returns the locked document, the target revision re-read under the lock, and the fresh time. There is no parallel lifecycle.
- **`write_chunk_set(session, job, expected_set)`** and **`write_chunks(session, job, batch)`:** each runs inside an ordinary `ctx.fenced()` block and follows one protocol:
  1. **Lock and check:** call `lock_revision_for_job(session, job, include_active=False)`, which waits for the document lock and then re-checks ownership. Then require the re-read target status to be `processing`. Any other status raises the fixed `ChunkWriteRefusedError`, and nothing is written.
  2. **Insert, `write_chunk_set`:** `INSERT INTO chunk_sets … ON CONFLICT ON CONSTRAINT pk_chunk_sets DO NOTHING RETURNING tenant_id, revision_id`.
     - If no row is returned, the stored `chunker_version`, `chunk_count` and `manifest_sha256` are read and compared with the expected values.
  3. **Insert, `write_chunks`:** `INSERT INTO chunks … ON CONFLICT DO NOTHING RETURNING id`. With no conflict target, this suppresses a conflict on **either** unique key: the primary key `id`, or `(tenant_id, revision_id, chunker_version, ordinal)`.
     - For every expected chunk whose `id` was not returned, the stored row is read by `(tenant_id, revision_id, chunker_version, ordinal)` and compared field by field: `id`, `chunker_version`, `ordinal`, `text`, `content_sha256`, `section_path`, `is_table`, the line and character spans and the four header fields.
     - If that lookup finds **no row** (the suppressed conflict was on some other row), or any field differs, the write raises the fixed `ChunkConflictError`. A missing lookup result is never treated as a successful idempotent retry, and the conflicting row is never overwritten.
  4. **Conflicts:** any difference raises the fixed `ChunkConflictError`, with no overwrite and no silent acceptance. Its message contains no content, digest or ID. `created_at` is metadata: it is never compared or regenerated on an idempotent retry.
  5. **Re-check:** call `recheck_ownership` again, after any unique-index waits and before the block exits and commits.
- **Serialization against settlement:** activation (`activate_revision`) and failure (`fail_revision`) take the same document lock first. So do chunk writes, whichever job they come from, including a different valid job that names the same revision through its own job row. The document lock is the serialization point:
  - **If the writer wins the lock,** its permitted batch commits before settlement can lock the document. The completeness check at activation then sees the committed rows.
  - **If settlement wins,** the writer waits. After the lock it re-reads the status (`active`, `superseded` or `failed`) and raises `ChunkWriteRefusedError`, so it writes nothing.
  - **No chunk or chunk-set row is inserted after the revision settles,** because every insert happens under the document lock after a `processing` check, and settlement changes the status under the same lock.
  - **A stale attempt changes nothing.** Its fence is refused when it opens, or its ownership re-check raises `LeaseLostError` after the lock wait or before commit, and the transaction rolls back.
  - Each batch holds the document lock only for one bounded batch, and every wait is bounded by the fence's 5-second `lock_timeout`.
- **Bounded transactions:** each chunk transaction writes at most 200 chunks or 512,000 code points of text, whichever comes first. Parsing happens before the first write, outside every transaction and every lock.
- **Crash and resume:** a crash or lease loss leaves earlier committed batches in place. The next attempt parses again (deterministic), re-writes the chunk-set row, and re-sends every batch. Existing identical rows are verified and skipped, and missing ones are inserted. There is no partial overwrite and no deletion.
- **Completeness and activation:** M3c's `activate_revision` gains one optional, keyword-only argument, `before_settle: Callable[[FencedSession, RevisionSnapshot], None] | None = None`.
  - It is invoked after M3c's locks and fresh ownership re-check, only when the target is `processing`, and before `settle`.
  - Existing callers are unchanged, and a duplicate activation of a settled revision skips it.
- **Binding the check to the current attempt:** the callback signature stays two-argument. The handler binds its own expectation into it with a closure.
  - `ExpectedChunkSet` is a frozen value with `chunker_version`, `chunk_count` and `manifest_sha256`, computed independently by the current attempt from its own parse.
  - `require_complete_chunk_set(session, revision, *, expected: ExpectedChunkSet) -> None` performs the check.
  - Illustrative call:

    ```python
    expected = ExpectedChunkSet(
        chunker_version=CHUNKER_VERSION,
        chunk_count=len(chunks),
        manifest_sha256=manifest_sha256(chunks),
    )
    with ctx.fenced(finish=True) as fence:
        activate_revision(
            fence.session,
            fence.job,
            before_settle=functools.partial(require_complete_chunk_set, expected=expected),
        )
    ```
- **What `require_complete_chunk_set` verifies,** in the same transaction and under the same locks:
  1. the `chunk_sets` row exists, and its `chunker_version` equals `expected.chunker_version`;
  2. its `chunk_count` equals `expected.chunk_count`;
  3. the stored chunks for `(tenant_id, revision_id, chunker_version)`, read without `text`, are exactly `chunk_count` rows with ordinals exactly `{0, …, chunk_count − 1}`;
  4. the manifest rebuilt from those stored fields, by the canonical encoding in B, hashes to the stored `manifest_sha256`;
  5. that hash also equals `expected.manifest_sha256`.

  Otherwise it raises the fixed `ChunkSetIncompleteError`, and nothing settles. This check prevents activation until the entire expected set is verified.
- **Trust limit:** the final check reads stored `content_sha256` digests, not the text. A digest is trusted because each row was compared field by field, text included, when it was written, and no code path updates chunks afterwards. That is the application's immutable-write invariant. The digest-only final check adds **no** protection against privileged direct database modification.
- **The final transaction:** in order:
  1. lock the job (the fence);
  2. check cancellation and lease;
  3. lock the document, then the revisions;
  4. re-check ownership;
  5. run `require_complete_chunk_set`;
  6. demote, promote, then update the pointer, or supersede a late older revision;
  7. check cancellation and lease again;
  8. record the job `succeeded`;
  9. commit.

  The worker's cancellation and uncertain-commit semantics are unchanged (ADR-0008, M3c). A lost acknowledgment means either the activation and the job success both committed, so the job is never reclaimed, or neither did, so the next attempt resumes.

**D. The production handler `ingest_revision`** *(proposed unless noted)*

- **Kind and registration:**
  - `INGEST_REVISION_KIND = "ingest_revision"` (decided).
  - `evidenceguard_worker.handlers.production_registry()` returns `HandlerRegistry([(INGEST_REVISION_KIND, ingest_revision)])`.
  - `eg-worker` then no longer exits 4 for an empty registry, and the CLI test is updated. The installed-wheel check imports the handler module and asserts the registered kinds.
- **Payload:**
  - exactly `{"revision_id": "<canonical lowercase UUID>"}`, validated by M3a's `JobPayload` plus a handler check for exactly that key;
  - the idempotency key is the same canonical revision ID (decided);
  - `max_attempts` is the M3a default of 3.
  - M3e enqueues it in the revision-creation transaction.
- **Flow:**
  1. **Status read:** `with ctx.fenced()`:
     - read the revision status in the job's tenant;
     - if it is `pending` or `processing`, call `start_processing` (a no-op when already processing) and `load_revision_source`.

     The block commits.
  2. **Already failed:** if the status was `failed`, raise `PermanentJobError(JobErrorCode.PERMANENT_FAILURE)` now, outside any block. **Nothing is parsed again.**
  3. **Already settled:** if the status was `active` or `superseded`, run `with ctx.fenced(finish=True): activate_revision(...)`. That is M3c's duplicate no-op, so the job completes without parsing or writing. The same applies to a different valid job for a settled revision.
  4. **Parse:** `ctx.check()`, parse (pure, no locks, no transaction), `ctx.check()`.
  5. **Write:** `ctx.check()`, then `with ctx.fenced(): write_chunk_set(...)`. Then, for each batch, `ctx.check()` and `with ctx.fenced(): write_chunks(...)`, each under the locking protocol in C.
  6. **Finish:** run the final transaction in C, with the closure bound to this attempt's `ExpectedChunkSet`.
- **`ChunkWriteRefusedError`:**
  - The refusing block raised, so it rolled back and wrote nothing.
  - The handler catches the error **outside** the block and goes back to step 1, a fresh status read in a new fenced transaction.
  - It then takes the branch for the status it finds: step 2 for `failed`, or step 3 for `active` or `superseded`.
  - It never calls `fail_revision` for a revision that is already settled or failed.
  - A settled or failed status never returns to `processing`, so the fresh read always takes step 2 or 3, and the handler re-enters step 1 at most once per attempt.
- **Failure classification:**

  | Condition | Revision | Job |
  |---|---|---|
  | `empty_document`, `chunk_limit_exceeded`, `content_integrity_failed`, `chunk_conflict` | `fail_revision(code)` in a non-raising block, which commits | then `PermanentJobError(PERMANENT_FAILURE)` raised **outside** the block |
  | Unexpected parser exception (a bug) | `fail_revision(INGESTION_FAILED)`, then as above | `PERMANENT_FAILURE` |
  | Payload invalid or extra keys, or revision not found in the job's tenant (including cross-tenant IDs) | untouched (no revision to fail) | `PermanentJobError(PERMANENT_FAILURE)` |
  | `ChunkSetIncompleteError` at activation | untouched (`processing`) | `RetryableJobError(RETRYABLE_FAILURE)`; the next attempt resumes the writes |
  | `ChunkWriteRefusedError` (the revision settled or failed meanwhile) | untouched | fresh status read, then the settled or failed branch (above) |
  | Database or lock timeout (`JobLockTimeoutError`, `OperationalError`) | untouched | retryable: `JobLockTimeoutError` → `RetryableJobError(RETRYABLE_FAILURE)`; other database errors take the runtime's existing `UNEXPECTED_ERROR` retry |
  | Lease loss, cancellation, uncertain commit | untouched | existing M3b behaviour (no outcome, `WORKER_SHUTDOWN` retry, `outcome_unknown`) |

  `fail_revision` itself takes the same document lock. If the revision settled first, M3c's rule raises the fixed `InvalidRevisionTransitionError`, so that block rolls back and writes nothing; the handler catches it outside the block and re-reads the status as above.
- **Revision codes:** `RevisionFailureCode` adds `empty_document`, `chunk_limit_exceeded`, `content_integrity_failed` and `chunk_conflict` to `ingestion_failed`. All of them map to `JobErrorCode.PERMANENT_FAILURE`, and no revision code is ever passed to `PermanentJobError`. The database CHECK already accepts these well-formed codes (ADR-0009).
- **Two-transaction permanent failure (decided, unchanged):**
  - `PermanentJobError` is never raised inside the block that must commit the revision's failure.
  - The crash gap between the two commits is recovered by step 2 on reclaim.
  - Retries exhaust to `dead` only for retryable causes.
- **Reclaim and partial writes:** a reclaimed attempt re-enters at step 1 and resumes through C. A stale attempt is refused at every fence and at every `recheck_ownership`.

**E. Dead-job truthfulness** *(proposed: a derived projection in M3e, no reconciliation writes)*

- **Authoritative state:** the stored revision `status` remains authoritative and is never rewritten by a sweep. The job row (`status`, `attempt`, `last_error`, `lease_expires_at`) is the authority on processing progress.
- **Projection:** M3e's document and revision read models expose a derived `ingestion_state`. It comes from the revision status and the revision's `ingest_revision` job, found by `(tenant_id, kind, idempotency_key = revision_id)`:

  | Revision | Job | `ingestion_state` | Meaning shown to users |
  |---|---|---|---|
  | `active`, `superseded`, `failed` | any | the revision status | settled |
  | `pending` or `processing` | `queued` | `queued` | waiting for a worker |
  | `pending` or `processing` | `running` | `in_progress` | a worker holds or recently held a lease; **this is not a guarantee of progress**, and an expired lease awaits reclaim |
  | `pending` or `processing` | `dead`, `failed` or `succeeded`, or no job | `stalled` | no further attempt will run; the content was not activated |

- **Limit:** in v1 a `stalled` revision cannot be retried, because re-uploading identical bytes returns the same revision and enqueue returns the same terminal job. Recovery is uploading changed bytes; an operator re-run is a later enhancement.
- **Assignment:** M3e implements the projection, with acceptance tests that a revision whose job is `dead` reads `stalled`, a running job with an expired lease reads `in_progress` without a progress claim, and settled revisions ignore the job. This **remains a blocker for overall M3 acceptance**.

**F. Verification plan and implementation boundaries** *(proposed)*

- **Intended files:**
  - `packages/retrieval/evidenceguard_retrieval/{__init__,chunking}.py` (new package; `pyproject.toml` package list and the boundary test updated, with no new dependency);
  - `evidenceguard_domain.revisions` (new failure codes);
  - `evidenceguard_persistence.models` and `migrations/versions/v0004_chunks.py`;
  - `evidenceguard_persistence.chunks`;
  - in `evidenceguard_persistence.documents`, the `before_settle` argument and the public `lock_revision_for_job`;
  - `evidenceguard_worker.ingest` and `handlers.py`;
  - tests and ADR-0010.
- **Database-independent tests:**
  - every normative example above (1–9);
  - determinism across repeated runs;
  - CRLF/LF line parity;
  - BOM exclusion;
  - fences, including closing-delimiter rules (info strings, short runs, the other fence character and deep indentation do not close);
  - a heading, fence or table directly after prose with no blank line;
  - consecutive heading runs and their section paths;
  - setext lines;
  - prose packing at exactly `TARGET_CHARS`;
  - oversized paragraphs, lines and heading lines, including oversized lines with leading or trailing whitespace and lines with no whitespace in the search range (no empty or whitespace-only piece);
  - split blocks never packed with neighbouring blocks, and split heading runs keeping the run's path;
  - a BOM-only first line treated as blank;
  - oversized rows, header segments above `MAX_HEADER_REPEAT_CHARS` and above `TARGET_CHARS`, and header-only tables;
  - the whitespace predicate (NBSP and a lone CR are not whitespace) for empty documents and split points;
  - the chunk-count cap;
  - every chunk within `MAX_CHUNK_CHARS` and reconstructing from the source by the mapping rules, and the coverage invariant;
  - a coverage case with several chunks separated by both LF and CRLF terminators (and blank lines of spaces and tabs), with a lone CR and NBSP inside chunk text: only the BOM, LF and CRLF terminators and permitted spaces and tabs are absent from the ordered body spans, and every other character appears exactly once;
  - tenant-disjoint chunk IDs for identical bytes;
  - manifest stability and byte-exact canonical encoding, including non-ASCII section paths;
  - content never appearing in reprs or errors;
  - payload validation;
  - the handler's branch table with scripted doubles, including:
    - the permanent-failure crash gap;
    - uncertain commits in both directions;
    - cancellation between batches;
    - a settled-revision duplicate job that never parses;
    - `ChunkWriteRefusedError` leading to a fresh status read and the settled or failed branch without `fail_revision`;
    - `InvalidRevisionTransitionError` from `fail_revision` after a concurrent settlement, leading to the same fresh read;
    - an `ExpectedChunkSet` mismatch refusing activation;
  - registry and installed-wheel registration.
- **PostgreSQL integration tests** (event-controlled concurrency, bounded waits, test-only statement timeouts):
  - migration `0004` upgrade, downgrade and re-upgrade, and `alembic check`;
  - every CHECK, the composite foreign keys (cross-tenant and cross-revision rejected) and uniqueness;
  - idempotent re-writes of the set and the chunks;
  - a conflicting existing chunk or chunk set refused with nothing overwritten;
  - a suppressed insert conflict where the `(tenant_id, revision_id, chunker_version, ordinal)` lookup finds no row, raising `ChunkConflictError` (a deliberately conflicting test row, or a controlled unit double in the database-independent tests);
  - a crash after some batches (injected) resumed by a second attempt to one complete set;
  - **writer versus activation** with two different valid jobs for the same revision: if the writer holds the document lock, its batch commits first; if activation wins, the writer is refused and writes nothing;
  - **writer versus failure:** the same two orders with `fail_revision`;
  - **no inserts after settlement:** a chunk or chunk-set write for an `active`, `superseded` or `failed` revision is refused and leaves no rows;
  - **lease expiry during the new lock waits:** a writer whose lease expires while it waits for the document lock is refused after acquiring it, and writes nothing;
  - **rollback of a refused batch:** the batch transaction leaves no partial rows;
  - a stale worker refused at chunk writes and at activation;
  - activation refused while the set is incomplete or differs from the attempt's `ExpectedChunkSet`;
  - atomic activation with job completion, and rollback when either fails;
  - the permanent-failure crash gap against real rows;
  - a real `run_worker` execution with the **registered production handler**.
- **Status (Prompts 80–84):** implemented as planned, with the files above and ADR-0010, and reviewed. The database-independent tests ran locally on Windows in Prompt 81 (1019 passed, 179 skipped). It was verified in CI on `feat/document-ingestion` at `74904e6` ([CI run 38699149482](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38699149482)). From logs retrieved by the external reviewer: [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38699149482/job/116302837532) `1020 passed, 178 skipped in 20.13s`, [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38699149482/job/116302837727) `1019 passed, 179 skipped in 23.75s`, and the [PostgreSQL integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38699149482/job/116302837038) `178 passed, 1020 deselected in 51.89s`: the full suite, including M3d's 45 new tests. The [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38699149417) passed ([job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38699149417/job/116302836923): 33 commits scanned, no leaks found). M3d was then fast-forwarded onto `main` at `cdf7260` (`cdf7260d02b8af9affb369cc805d666be61f9ac0`, adding only documentation after `74904e6`), where [CI run 38701376504](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38701376504) passed again. From logs retrieved by the external reviewer: [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38701376504/job/116310119787) `1020 passed, 178 skipped in 19.71s`, [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38701376504/job/116310119664) `1019 passed, 179 skipped in 16.16s`, and the [PostgreSQL integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38701376504/job/116310119317) `178 passed, 1020 deselected in 53.28s`. The [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38701376501) passed ([job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38701376501/job/116310119403): 34 commits scanned, no leaks found). Both runs were push-triggered on `main`; the reviewer did not run the suite locally. These results demonstrate the tested behaviour, not a performance benchmark or a general security guarantee.

**M3e, upload and document endpoints, in detail (ACCEPTED at review, Prompt 86, corrected in Prompts 87–88; implementation accepted at review in Prompt 91, verified in CI and on `main` at `2e605e7`, see ADR-0011):**

M3e adds the HTTP surface for documents: a bounded multipart upload that creates a revision and its ingestion job in one transaction, read-only views of documents, revisions, chunks and jobs, and the required derived `ingestion_state` (M3d, section E). It changes no M3a–M3d behaviour.

**Already decided (not reopened here):**
- **Scope and media:** multipart upload; only `text/plain` and `text/markdown`, as strict UTF-8 without NUL (M3c's `RevisionContent`). PDFs are a later addition.
- **Authorization:** reviewer or approver, as for vendors; administrators get a generic 403. The tenant comes only from the API key (ADR-0005, ADR-0006).
- **Creation:** `create_revision` (M3c, section C) and `enqueue` (M3a), both in the caller's transaction; kind `ingest_revision`, payload `{"revision_id": …}`, idempotency key = the canonical revision ID, and the M3a default of 3 attempts.
- **Revision rules:** identical bytes for the same document return the existing revision, whatever its status. A metadata difference is a conflict. Document metadata is fixed by the first upload.
- **Behaviour:** 413, 415 and 422 behave as specified, and re-uploads are idempotent (the M3e acceptance row).
- **Projection:** the `ingestion_state` table of M3d section E, with no reconciliation writes. It is required before overall M3 acceptance.
- **Shared conventions:** generic RFC 9457 problem responses, request IDs and fixed log events (ADR-0002); bounded offset pagination that is not a snapshot (ADR-0006).

Everything else below was proposed in Prompt 86, corrected in Prompts 87–88, and **accepted at external review** (Prompt 88). The numeric caps and pagination bounds are **initial engineering choices, not measured results**. An established streaming multipart library is accepted in principle; the exact release remains subject to the age, compatibility and advisory prerequisites in B.

**A. Endpoints**

Six endpoints. The milestone's "list" requirement is met by a **vendor-scoped document list**. A separate **revision list** keeps the document view bounded.

| Method and path | Purpose | Success |
|---|---|---|
| `POST /v1/vendors/{vendor_id}/documents` | Upload a revision (multipart, B) | 202 new revision and job; 200 identical existing revision |
| `GET /v1/vendors/{vendor_id}/documents` | List the vendor's documents | 200 `DocumentPage` |
| `GET /v1/documents/{document_id}` | One document with its active and latest revisions | 200 `DocumentDetail` |
| `GET /v1/documents/{document_id}/revisions` | The document's revision history, bounded | 200 `RevisionPage` |
| `GET /v1/documents/{document_id}/revisions/{revision_no}/chunks` | Inspect a revision's chunks | 200 `ChunkPage` |
| `GET /v1/jobs/{job_id}` | Status of an ingestion job | 200 `JobView` |

- **Common to every endpoint:**
  - **401:** missing, malformed, unknown or revoked credentials, with `WWW-Authenticate: Bearer` (the existing dependency).
  - **403:** an administrator; generic, with no admin bypass.
  - **404:** a missing object, or one in another tenant; the two are indistinguishable.
  - **422:** a malformed ID or out-of-range query parameter. Problem entries carry only `loc` and `type`.
  - **503:** a database or configuration failure; generic.

  Tenant headers, query parameters and form fields are never read as scope.
- **`{revision_no}` is the revision number**, not a UUID: an integer 1–2,147,483,647, validated by the path (otherwise 422).
  - The revision is found by `(tenant_id, document_id, revision_no)` after the document is found in the caller's tenant.
  - A number the document does not have is a 404, as is a document of another tenant. The document-revision relationship therefore cannot mismatch.
  - Revision UUIDs appear in responses and job payloads, but no path takes one in v1.
- **Pagination:**
  - `limit` defaults to 20 (1–100), and `offset` to 0 (0–10,000), for documents and revisions.
  - Chunks: `limit` defaults to 50 (1–200), and `offset` to 0 (0–4,095).
  - Every page has `items`, `total`, `limit` and `offset`.
  - Document and revision pages are **not snapshots** across requests (ADR-0006).
  - Chunk pages are always ordered by `ordinal`. For a **settled** revision (`active` or `superseded`) the set is complete and immutable under the application's write-once invariant (M3d), so its pages do not change between requests.
  - For an **unsettled** revision, an ingestion attempt may still be writing batches, so `stored_count`, `total` and the page contents can change between requests. Each page is an observation at one read snapshot (D), with no snapshot guarantee across requests while writes continue.
- **Ordering:**
  - documents by `document_key`, then `id`;
  - revisions by `revision_no` **descending** (newest first), then `id`;
  - chunks by `ordinal`.
- **`GET /v1/vendors/{vendor_id}/documents`:** 404 if the vendor is not in the caller's tenant. `items` are `DocumentSummary`.
- **`GET /v1/documents/{document_id}` → `DocumentDetail`:**
  - the `DocumentSummary` fields;
  - `active_revision`: a `RevisionView` or `null`;
  - `latest_revision`: a `RevisionView` or `null`. It is the highest `revision_no`, which may equal the active revision.

  It never nests the full history; that is the revision list.
- **`DocumentSummary`:** `id`, `vendor_id`, `document_key`, `title`, `source_type`, `authenticity` (always `not_established` in v1), `latest_revision_no`, `active_revision_id`, `created_at` and `updated_at`. It contains no content.
- **`RevisionView`:**
  - **Identity and metadata:** `id`, `revision_no`, `version_label`, `effective_date`, `media_type`, `byte_size`, `sha256`.
  - **Stored state:** `status`, `failure_reason` (a fixed `RevisionFailureCode` or `null`), `activated_at`, `failed_at`, `superseded_at`, `superseded_by_revision_id`, `created_at` and `updated_at`.
  - **Derived state:** `ingestion_state` (E) and `ingestion_job`, a `JobSummary` or `null` (E).

  It never contains `content_text`.
- **`ChunkPage`:**
  - `chunk_set`: `null` when no chunk-set row exists; otherwise `{chunker_version, chunk_count, stored_count, verified_complete}`;
  - `items`: `ChunkView`, plus `total`, `limit` and `offset`.
- **Partial-set policy:**
  - Chunks are visible for a revision in any status, as stored.
  - `verified_complete` is `true` only for an `active` or `superseded` revision. Activation verified the exact set (M3d C), and chunks are never updated.
  - For `pending`, `processing` and `failed` revisions it is `false`, whatever `stored_count` is. The rows are whatever an attempt wrote and may be partial; for a failed revision they are never completed.
  - `chunk_count` is the expected count recorded by the writing attempt; `stored_count` is the number of stored rows.
  - `verified_complete` is never inferred from `stored_count` equalling `chunk_count`: only activation's under-lock verification establishes completeness.
- **`ChunkView`:**
  - `id`, `ordinal`, `text` and `content_sha256`;
  - `section_path` (a list);
  - `is_table`;
  - `source`: the body span `{line_start, line_end, char_start, char_end}`;
  - `repeated_header`: `null`, or the header span `{line_start, line_end, char_start, char_end}`;
  - `contiguous`: `repeated_header` is `null`.

  When `repeated_header` is set, `text` is the header slice followed by the body slice. **It is not one contiguous source passage**, and only `source` identifies the cited passage.
- **`JobView`** (only for jobs of the reviewed kinds; in v1 that is just `ingest_revision`, and any other kind is a 404):
  - `id`, `kind` and `status`;
  - `attempt`, `max_attempts`, `run_after`, `last_error` (a fixed `JobErrorCode` or `null`), `created_at`, `updated_at` and `finished_at`;
  - `lease_expires_at` (only while `running`, otherwise `null`);
  - `lease_expired`: `true` or `false` while `running`, compared with the single database time captured for the response (D); `null` otherwise.

  It never contains the payload, `idempotency_key`, `locked_by` (a worker identifier), `tenant_id`, exception text or free-form errors.
- **`JobSummary`** (inside `RevisionView` and the upload response): `id`, `status`, `attempt`, `max_attempts`, `lease_expires_at` and `lease_expired`, with the same rules.

**B. Upload parsing and limits**

- **Route shape:** the endpoint declares **no body parameters** (no `Form`, `File` or `UploadFile`), so FastAPI never parses the body. The handler reads `request.stream()` itself, through a bounded reader.
  - Authentication and the role check are ordinary dependencies, resolved **before the handler runs**. The handler is the only code that reads the body, so no body byte is read for a 401 or 403. This relies on the route having no body parameters, and a test asserts that the stream is untouched on 401 and 403; FastAPI's dependency order alone is not taken as a guarantee.
  - The vendor is then looked up (read-only, tenant-scoped) **before the body is read**, so a missing or foreign vendor is a 404 without consuming the upload. `create_revision` re-checks it in its own transaction.
- **Request headers:**
  - `Content-Type` must be `multipart/form-data` with a `boundary` of 1–70 characters; otherwise 415.
  - If `Content-Length` is present, it must be a single non-negative decimal; otherwise 400. If it exceeds the total cap, the response is 413 at once, without reading.
  - **The streamed byte count is authoritative for every cap**, whether `Content-Length` is absent (chunked transfer), smaller or larger than the body.
  - When `Content-Length` is present and the ASGI server delivers a normally completed stream (the final message has `more_body` false), the received length must equal it; otherwise 400. A production HTTP server usually rejects such mismatches before the application sees them; tests use controlled ASGI streams to exercise this path.
  - **Client disconnect** (`http.disconnect`) or a transport-level rejection aborts the request before any database write. No response is guaranteed to reach a disconnected client.
- **Caps** (initial engineering defaults, not measured):
  - **File bytes:** `MAX_UPLOAD_BYTES = 2,097,152` (2 MiB). The cap applies to the file part's content.
  - **Total request bytes:** `MAX_REQUEST_BYTES = 2,162,688` (2 MiB plus 64 KiB for headers and fields). The cap applies to the whole multipart body.
  - **Parts:** at most 8, and each part's headers at most 8 KiB.
  - **Text fields:** at most 1 KiB each before validation.
  - Exceeding any byte cap is a **413 as soon as it is detected**, and reading stops.
  - At 2 MiB, a document stays well within M3d's 4,096-chunk cap for ordinary prose.
- **Fields** (one `Content-Disposition: form-data` part each):

  | Name | Required | Validation |
  |---|---|---|
  | `file` | yes | exactly one part; content 1 byte to 2 MiB; its part `Content-Type` decides the media type |
  | `document_key` | yes | M3c's document-key pattern, 1–64 |
  | `title` | yes | M3c's title rule, 1–200, not blank, no control characters |
  | `source_type` | yes | `vendor_statement`, `contract` or `third_party_report` |
  | `version_label` | no | M3c's label rule, 1–64 |
  | `effective_date` | no | ISO `YYYY-MM-DD` |

  - **Part headers:** every part needs a `Content-Disposition: form-data` header with a `name` parameter (quoted or token form, case-insensitive type); otherwise 422. Other part headers are ignored, except the file part's `Content-Type`.
  - **Text parts** must be valid UTF-8 and carry no `filename`; otherwise 422.
  - **Repeated or unknown parts:** a repeated field, a second `file` part, or any other part name is a 422. That includes `tenant_id`, `actor_id`, `role`, `vendor_id` and `status`.
- **Filename:** the `file` part's `filename` is optional and **ignored**. It is never stored, logged, echoed or used as a filesystem path.
- **File media type:** taken only from the file part's `Content-Type`, never sniffed from the name or content.
  - Accepted: `text/plain` or `text/markdown`, case-insensitive, optionally with `charset=utf-8`.
  - 415: any other type, any other charset or parameter, or a missing part `Content-Type`.
- **Content:** passed unchanged to `RevisionContent.from_bytes`.
  - The bytes must be strict UTF-8 without NUL, so invalid UTF-8 and NUL are 422.
  - A BOM and CRLF are kept exactly. They change the hash, and the chunker handles them (M3d A).
  - **A zero-byte file is a 422** (`RevisionContent` requires non-empty bytes).
  - **Whitespace-only content is accepted** (202). The worker later fails the revision with `empty_document`, and `ingestion_state` reads `failed`.
- **Parser and memory:**
  - **Dependency (accepted in principle; not selected or installed here):** an established streaming multipart library, with `python-multipart` the expected candidate. Only a low-level streaming callback API is used, fed by the bounded reader; FastAPI's `Form`/`UploadFile` handling is not used.
  - **Implementation prerequisites:** the exact release, its age under the dependency-age policy (at least two weeks old, with an `exclude-newer-package` entry), compatibility with the locked FastAPI and Starlette versions, and a check of published security advisories. The policy is never bypassed, and a newer release is never added silently.
  - **Completion is tracked explicitly.** The implementation must verify how the chosen library reports truncation, and must not assume that its `finalize()` detects every truncated body. The handler records each part's begin and end and the final closing boundary itself. A body is complete only if the closing boundary was seen and every begun part ended.
  - **No success response is ever produced for a truncated multipart body**, including truncated headers or part data.
  - **Boundary syntax:** 1–70 characters from RFC 2046's allowed set, not ending in a space, quoted or unquoted; otherwise 415.
  - The file bytes accumulate in one in-memory `bytearray`, bounded by the 2 MiB cap. **No temporary file is ever created**, so there is nothing on disk to clean up. Buffers are released on every path, including errors and client disconnects.
  - The alternative of a hand-written multipart parser was rejected: it would add parsing risk without reducing dependencies meaningfully.
- **Error precedence.** Errors fall into three phases. Within the streaming phase, the **first error detected wins**, and reading stops at once.
  1. **Before the body** (no body byte is read): 401 or 403; 422 for a malformed `vendor_id`; 404 for a missing or foreign vendor; 400 for an invalid `Content-Length` header; 413 when it exceeds the total cap; 415 for a request `Content-Type` that is not multipart with a valid boundary.
  2. **While streaming** (each error ends reading immediately, in the order the bytes reveal them):
     - 413: the total, file, text-part or part-header byte cap, or the part count, is exceeded;
     - 422: the parser reports malformed input, which can prevent any further meaningful parsing;
     - 422 (structural, detected at the part's headers): a missing or invalid `Content-Disposition` or `name`, an unknown part name (including tenant fields), a repeated field, a second `file` part, or a `filename` on a text part;
     - a client disconnect: abort without a database write.

     Once reading has stopped, nothing after that point is examined. A later cap violation therefore never overrides an earlier parser or structural error, and an invalid request is never drained just to establish a global precedence. The server may close the connection instead of reading the remaining body.
  3. **After a normally completed stream** (deferred checks, bounded because everything read is within the caps), in this order:
     1. 400 for a declared `Content-Length` that differs from the received length;
     2. 422 for an incomplete body: no closing boundary, or a part that never ended;
     3. 422 for a missing required field;
     4. 415 for the file part's media type;
     5. 422 for field values;
     6. 422 for the content: empty, invalid UTF-8 or NUL.
  4. **Creation:** 404 for a vendor deleted meanwhile, 409 for a document or revision conflict (C), 503 for a database failure.
- **Exact mixed-fault outcomes** (each is a planned test):
  - a repeated field followed by excess parts → 422 (the repeated field is detected first; reading stops before the part cap);
  - malformed multipart followed by an oversized tail → 422 (reading stops at the parser error; the tail is never read);
  - otherwise valid fields with no closing boundary, on a normally completed stream → 422;
  - a declared length shorter or longer than a normally completed stream's actual length → 400;
  - an oversized file part followed by a malformed part → 413 (the cap is crossed first).
- **Receive boundaries do not define precedence.** For the same body bytes, the outcome is the same however the ASGI server partitions them into receive messages:
  - Errors are detected in the order the body's bytes reveal them. Each received message is fed to the parser in bounded slices, and byte caps are enforced at the exact position where the running count crosses them, not after the whole message.
  - Receiving a large message that also contains a later oversized tail never lets that tail's 413 override an earlier malformed or structural (for example repeated-field) error in the same bytes.
  - Byte-at-a-time processing is not required. Bounded slices and parser callbacks are acceptable, as long as the slice boundaries and callbacks reproduce this byte-order detection.
- **Problem bodies:**
  - 413 and 415 use the generic problem body.
  - Multipart 422 entries are built by the endpoint with `loc` from a reviewed allowlist (`["body", "<known field name>"]`, or just `["body"]` for an unknown or repeated part) and a fixed `type`.
  - Unknown part names and submitted values are never echoed.

**C. Atomic creation and duplicates**

- **One caller-owned transaction** (`transaction(session_factory)`):
  1. `create_revision(...)`;
  2. if `created`, `enqueue(session, actor, kind="ingest_revision", idempotency_key=str(revision.id), payload={"revision_id": str(revision.id)})` with the default attempts;
  3. commit.

  Any error rolls back both, so a new revision never exists without its job, and vice versa.
- **Observation time of the response:** after the required writes and before the commit, the creation transaction reads the response state in **one statement**: the revision row, its canonical job (left join) and one `clock_timestamp()` for `lease_expired`. That gives one internally consistent snapshot. It is converted to an immutable `UploadResult`, which is sent **only after a successful commit**. Nothing is re-read after the commit, and fields observed at different times are never mixed. If the commit fails, the result is discarded and the request ends with the mapped error.
- **The response reports what was observed, not a promise.** A worker can claim or settle the revision immediately after the commit, so a `pending` or `queued` value says nothing about the state a moment later.
- **New revision:** `202 Accepted` with an `UploadResult`:
  - `created: true`, `document_id`, `revision_id` and `revision_no`;
  - `revision_status` (`pending`) and `ingestion_state` (`queued`);
  - `job`: a `JobSummary`.
- **Identical bytes and metadata for the same document:** `200 OK` with the same `UploadResult` shape and `created: false`. It shows the **existing** revision's stored status, its derived `ingestion_state` and its canonical job, so it is not always "pending".
  - A processing revision reads `in_progress`; an active one `active`; a superseded one `superseded`; a failed one `failed`.
  - An unsettled revision whose job is `dead` reads `stalled`, and the job is shown as it is. A terminal job is never reset or re-queued, and a settled revision is never re-ingested.
- **A revision without its canonical job** cannot be produced by M3e, because creation is atomic; it would need direct database changes.
  - If such a revision is **unsettled**, the duplicate upload calls `enqueue` in its transaction. That idempotently creates the missing job and never alters an existing one. This is the only repair, and it happens on POST only.
  - If it is **settled**, nothing is enqueued and `job` is `null`.
- **Conflicts:** all are generic, never naming the differing field.
  - `DocumentConflictError` (same key, different title or source type) → 409;
  - `RevisionConflictError` (same bytes, different media type, label or date) → 409.
- **Concurrent identical uploads** serialise on the document lock (M3c). The first creates the revision and job; the rest see them and return 200 duplicates. A concurrent creation of the same document key resolves through `ON CONFLICT` and the lock.
- **Other errors:**
  - `RevisionCreateRaceError` and `JobEnqueueRaceError` arise only under stricter isolation, and become a generic 503 (retry).
  - `JobIdempotencyConflictError` would mean a corrupted canonical job, and becomes a generic 500 with the fixed log event `document.upload_inconsistent`, carrying no values.
  - `VendorNotFoundError` → 404; `PermissionDeniedError` → 403.

**D. Read models and persistence**

- **New module:** `evidenceguard_persistence.document_views`. Its read-only functions take a caller-owned `Session` and the `ActorContext`, and filter every statement by `actor.tenant_id`:
  - `list_documents(vendor_id, limit, offset)`;
  - `get_document(document_id)`;
  - `list_revisions(document_id, limit, offset)`;
  - `get_revision_by_no(document_id, revision_no)`;
  - `list_chunks(document_id, revision_no, limit, offset)`;
  - `get_job_view(job_id)`.
- **Parent and child checks:** every child lookup joins or filters on the parent under the same tenant: vendor → document → revision → chunk set → chunks. A parent outside the tenant yields nothing, and the response is 404.
- **Columns:** revision reads use explicit column lists that exclude `content_text`. Chunk reads select `text` only for the chunk endpoint.
- **The projection in SQL:** a `LEFT JOIN jobs` on `jobs.tenant_id = revision.tenant_id AND jobs.kind = 'ingest_revision' AND jobs.idempotency_key = CAST(revision.id AS text)`, with `lease_expired` computed against the response's single captured database time. PostgreSQL renders UUIDs in the canonical lowercase hyphenated form used as the key. The existing unique `(tenant_id, kind, idempotency_key)` index serves the join.
- **Transactions and threads:**
  - **One consistent snapshot per GET response.** Each M3e read operation is one short transaction whose **first statement** is `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY`, before any data query. Every query for that response then sees the same snapshot:
    - parent existence checks;
    - document pointers and the active and latest revision views;
    - the canonical job and `ingestion_state`;
    - chunk-set metadata, `stored_count`, `total` and `items`.
  - **One database time per response:** the second statement reads `clock_timestamp()` once. Every `lease_expired` in the response is computed against that single value, passed as a parameter.
  - **Short transactions:** results are converted to immutable response values inside the transaction, and the transaction ends (rollback, since nothing was written) **before** the response body is serialized and sent. Routes are synchronous, so FastAPI runs them in a worker thread.
  - **No leaking settings:** `SET TRANSACTION` applies only to the current transaction; PostgreSQL discards it at commit or rollback. No session-level `SET`, `default_transaction_isolation` or connection `execution_options` isolation is used, so a pooled connection returns to the pool with its defaults, and a later upload runs at the default READ COMMITTED, read-write.
  - **Uploads keep the existing isolation:** the creation write transaction stays at the default READ COMMITTED, as M3a and M3c expect.
  - **What this guarantees:** internal consistency **within one response**, not a shared snapshot across separate HTTP requests.
  - The upload route is `async`, to stream the body without blocking. Its vendor lookup and creation transaction run through `run_in_threadpool`, never on the event loop.
- **Failures:**
  - `DatabaseConfigurationError` and `SQLAlchemyError` become a generic 503.
  - **No GET writes:** none creates jobs, changes revision state, or repairs or reconciles data.

**E. The `ingestion_state` projection**

- **Two distinct fields:** `status` is the stored, authoritative revision status. `ingestion_state` is derived at read time and never stored.
- **Canonical job lookup:** the job with `(tenant_id = revision.tenant_id, kind = "ingest_revision", idempotency_key = canonical revision ID)`. At most one exists, by the unique index.
- **Rules,** checked in order:

  | Revision `status` | Canonical job | `ingestion_state` |
  |---|---|---|
  | `active`, `superseded` or `failed` | any, or none | equal to `status` |
  | `pending` or `processing` | `queued` | `queued` |
  | `pending` or `processing` | `running` (lease current or expired) | `in_progress` |
  | `pending` or `processing` | `dead`, `failed` or `succeeded` | `stalled` |
  | `pending` or `processing` | none | `stalled` |

- **`in_progress` is not a progress guarantee.** When the lease has expired, `ingestion_job.lease_expired` is `true`. This honestly shows that the attempt is awaiting reclaim, or exhaustion to `dead`, at the next claim.
- **`stalled`** means no further attempt will run and the content was not activated. In v1 there is no operator retry: identical bytes return the same revision and the same terminal job. Recovery is uploading changed bytes (M3d E).
- **Acceptance obligation:** this projection remains **required for overall M3 acceptance** until it is implemented and verified in CI.

**F. Privacy and observability**

- **Logging:**
  - The existing `request.completed` event (route template, status, duration, request ID) is unchanged.
  - M3e adds only the fixed `document.upload_inconsistent` event. It carries no values.
  - Nothing logs multipart bodies, document text, chunk text, filenames, field values, credentials or database exception text.
- **Errors:**
  - Parser and validation failures map to fixed problem bodies.
  - The endpoint never passes parser exception messages, part names it did not expect, or submitted values into a response or log.
  - Response models use `extra="forbid"`; an internal model error would be a generic 500, never echoed.
- **Request IDs and headers:** request IDs are unchanged. `X-Request-ID` remains the only client-influenced header that is logged, as today.
- **Errors versus intended responses:**
  - **Errors and logs** never contain submitted content, filenames, arbitrary field names, field values or internal exception text.
  - **Authorized successful responses** intentionally contain their documented metadata. `ChunkView` intentionally contains chunk text, for authorized inspection.
  - **Document and revision views** never contain raw source content (`content_text`).
  - **Job views** never contain the payload, `idempotency_key`, `locked_by`, `tenant_id`, exception text or free-form errors.

**G. Verification plan and implementation boundaries**

- **Intended files:**
  - `apps/api/evidenceguard_api/documents.py` (routers and models);
  - `apps/api/evidenceguard_api/uploads.py` (bounded reader and multipart handling);
  - `apps/api/evidenceguard_api/app.py` (wiring a `DocumentStore` through `app.state`);
  - `packages/persistence/evidenceguard_persistence/document_views.py`;
  - tests and ADR-0011.
- **Dependency:** one established streaming multipart library (`python-multipart` expected), added to `pyproject.toml` and `uv.lock` only after the release-age, compatibility and advisory prerequisites in B are met; OpenAPI request-body documentation for the upload. There are no migrations or workflow changes.
- **Database-independent tests** (fake stores and ASGI clients):
  - **Byte limits:**
    - a declared `Content-Length` above the cap → 413 without reading;
    - an absent length (chunked) → 413 as soon as the stream crosses the cap;
    - a misleading small length → 413 or 400, never an unbounded read;
    - file cap and total cap each enforced separately, and part-header and part-count caps.
  - **Malformed multipart:** an invalid boundary parameter → 415; a missing `Content-Disposition` or `name` → 422; truncated part headers or part data, and a missing closing boundary on a normally completed stream → 422; never a 2xx for a truncated body.
  - **Completion tracking:** the parser's own end-of-input behaviour is exercised for the chosen library, and the handler's explicit completion tracking rejects every truncation case.
  - **Content-Length:** shorter and longer declared lengths with a normally completed (controlled) ASGI stream → 400; a client disconnect mid-body → abort with no store call.
  - **Fields:** duplicate fields, a second file, unknown parts (including `tenant_id`), a filename on a text part, and a missing required field; buffers released on every path; no temporary files created.
  - **Authentication and roles:** a missing or revoked key → 401, and an admin → 403, with the body stream untouched in both cases; a foreign vendor → 404 before the body is read.
  - **Tenant overrides:** attempted header and query overrides of the tenant are ignored.
  - **Media and content:** unsupported or missing part media type and a wrong charset → 415; invalid UTF-8, NUL and zero bytes → 422; whitespace-only → 202; BOM and CRLF stored exactly.
  - **Precedence:** the three phases in B, and each listed mixed-fault outcome exactly: a repeated field then excess parts → 422; malformed input then an oversized tail → 422 with the tail unread; no closing boundary → 422; length mismatches → 400; an oversized file then a malformed part → 413.
  - **Receive partitioning:** each mixed-fault body above is presented in one receive message, split across several messages, and split inside part headers, boundaries and file data. Every presentation must give the same status and no store or database call.
  - **Results:** the `UploadResult` shapes for new (202) and duplicate (200) uploads; conflicts → generic 409; each creation error's mapping.
  - **Pagination and lookups:** bounded pagination validation; a `revision_no` not belonging to the document → 404.
  - **Projection:** every row of the `ingestion_state` table, from pure inputs, including a dead job, an expired running lease and a missing job.
  - **Privacy of errors and logs:** problem bodies and log records never contain submitted content, filenames, unknown field names, field values or exception text, for every error path above.
  - **Intended success fields:** authorized document, revision and job responses contain exactly their documented fields (no `content_text`, payload, `idempotency_key`, `locked_by` or `tenant_id`), and `ChunkView` contains the chunk text and provenance.
  - **OpenAPI:** the schema documents the new endpoints.
  - **Installed wheel:** the app imports, the routes are registered, and an upload with a test double works.
- **PostgreSQL integration tests:**
  - **Uploads:** new uploads commit revision and job together; an injected `enqueue` failure rolls both back; concurrent identical uploads give one revision and one job, with the others 200; concurrent different bytes get consecutive numbers.
  - **Duplicates:** for a processing, active, superseded, failed or dead-job revision, the response reports the true state, nothing is reset, and no job is created for a settled revision.
  - **Tenancy:** cross-tenant reads of vendors, documents, revisions, chunks and jobs → 404.
  - **Reads:** document, revision and chunk ordering and bounds; chunk provenance (body span and repeated header) and `verified_complete` for active versus processing and failed partial sets.
  - **Projection in SQL:** every `ingestion_state` row against real job rows, including an expired lease and `dead`.
  - **Side effects:** GETs leave every row unchanged.
  - **Read consistency** (event-controlled concurrency):
    - an activation committing between the document view's queries still yields one consistent response (pointer, active and latest revision, and projection from one snapshot);
    - a chunk batch committing between the count and page queries leaves `stored_count`, `total` and `items` consistent within the response;
    - a revision's projection never mixes a revision status and a job status from different times;
    - after a REPEATABLE READ, READ ONLY read on a pooled connection, a later upload on the same connection runs read-write at READ COMMITTED (settings restored).
  - **Upload observation:** the 202 and 200 bodies match the state read inside the creation transaction, even when a worker changes the job immediately after the commit.
  - **End to end:** upload, then a real `run_worker` with the production handler, then views show `active` and the verified chunks.
- **Status (Prompts 89–93):** the implementation and the tests above were accepted at external review (Prompt 91), after Prompt 90's corrections for raw header-byte counting, lossless parameter validation and the missing PostgreSQL tests. The database-independent tests ran and passed locally on Windows (`1260 passed, 205 skipped`: 204 PostgreSQL tests and one POSIX-only signal test). The PostgreSQL integration tests in the plan above then ran in CI on `feat/document-api` at `ccdf08d`: the full 204-test integration suite passed, including all 26 M3e tests, as did Ubuntu and Windows verification (job logs retrieved by the external reviewer; see ADR-0011). It was then published on `main` at `2e605e7`, where [CI run 38758727669](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38758727669) passed again (Ubuntu, Windows and the 204-test PostgreSQL suite, per job logs retrieved by the external reviewer).

**M3f, container image and Compose services, in detail (ACCEPTED at review, Prompt 97; proposed in Prompt 95, corrected in Prompts 96–97; implementation staged in Prompt 98, corrected in Prompt 99, accepted at review in Prompt 100; verified in CI on `feat/container-stack` at `682101b` and on `main` at `e2463cb`; see ADR-0012):**

M3f packages the existing distribution as one container image and adds the API, worker and migration services to the existing Compose file. It changes no application behaviour, authentication or worker semantics. It is development tooling: it makes no production-deployment claim.

**Already decided (not reopened here):**
- **Architecture:** one Python distribution (ADR-0001), the existing `eg-api`, sequential `eg-worker` and `eg-admin` entry points, PostgreSQL-backed jobs (ADR-0003, ADR-0007), and the existing database image `pgvector/pgvector:0.8.7-pg17`, pinned by digest (ADR-0004).
- **Slice check** (M3 table above): images build in CI. Compose stays unverified **locally** while Docker is unavailable (§10).
- **Dependency policy:** the committed `uv.lock` and the dependency-age policy (ADR-0004). Images are pinned by digest.

**Reviewer decisions (Prompt 96):**
- **Python base:** `python:3.12.14-slim-trixie` with the digest in A, subject to verification against the official registry at implementation. **No dependency-age exception is approved.**
- **Smoke test:** the CI Compose smoke in E is **required** for M3f.
- **M3 Compose requirement:** a passing CI Compose smoke can satisfy it, alongside the other agreed criteria. Local Compose stays unverified until it actually runs locally.
- **Engineering defaults:** UID/GID 10001; loopback host ports 8000 (API) and 5433 (database); a 60 s worker stop grace period; no restart policy; a 180 s startup wait; a 90 s ingestion wait; a 20-minute CI job timeout.

These are engineering defaults, not measured performance claims.

**What exists today** (inspected at `2e605e7`):
- `docker-compose.yml` defines **only** `postgres`:
  - the pinned pgvector image, with disposable credentials `evidenceguard` / `evidenceguard-local-dev`;
  - host port `127.0.0.1:5433`, a `pg_isready` health check and the named volume `evidenceguard-pgdata`;
  - `infra/docker/postgres-init/01-create-test-database.sql`, which creates `evidenceguard_test` on first initialisation.

  It has never been run.
- There is no `Dockerfile` or `.dockerignore`.
- **Entry points:**
  - `eg-api` binds `127.0.0.1:8000` by default and takes `--host` and `--port`;
  - `eg-worker` handles SIGINT and SIGTERM: the first requests a graceful stop, a second an immediate one;
  - `eg-admin` has `seed-demo`, `create-key` and `revoke-key`.
- **Database settings:** every entry point reads only `EG_DATABASE_URL`, and the URL policy accepts a single DNS host such as `postgres`.
- **Migrations** ship inside `evidenceguard_persistence`. `alembic.ini` only names that script location, and online migrations read `EG_DATABASE_URL`.
- **`GET /readyz`** returns 200 only when the database answers and its migrations match this release; it never migrates.
- **Package data** the wheel needs besides Python modules: the `py.typed` markers and `evidenceguard_persistence/migrations/script.py.mako`.
- **Worker shutdown** (ADR-0008, *No total shutdown deadline*): the drain (30 s), cancellation grace (5 s) and heartbeat join (10 s) are **bounded supervisor waits, not a deadline for the whole process**.
  - `claim` and outcome recording are synchronous database calls on the supervisor thread, and signals do not cancel them.
  - There is no worker statement timeout, so a blocked call can delay shutdown beyond those waits.
- **CI** pins uv `0.13.0` and Python 3.12. Docker is not installed on the development machine.

**A. Image (`Dockerfile`)**

- **One image** for every role; the command selects the process (`eg-api`, `eg-worker`, `eg-admin`, `alembic`).
- **Base images:**
  - **Python:** the Docker Official Image `python:3.12.14-slim-trixie@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f`, for both stages. The Docker Hub tag listing showed this digest last updated 2026-09-25, which meets the two-week policy.
  - **uv:** binaries copied from `ghcr.io/astral-sh/uv:0.13.0@sha256:cdc6093146eb3ff6a40107b38f008b789e050e77ad87865e381d9917da55a168`, the same uv version CI already uses. That digest is the multi-platform index the registry returned for the tag. At implementation, this release was found to be six days old; the reviewer then approved a narrow exception for this exact builder-tool digest only (Prompt 99; see ADR-0012). The exception allows no floating tag, replacement digest or runtime uv, and does not extend to the Python base or the general age policy.

  The implementation re-verifies both digests from the official registries and records them, with their dates, in its ADR. If the approved Python digest cannot be verified there, implementation stops for review instead of substituting a newer image.
- **Builder stage:**
  - **Environment:** `UV_PROJECT_ENVIRONMENT=/opt/venv`, `UV_PYTHON_DOWNLOADS=never`, `UV_COMPILE_BYTECODE=1` and `UV_LINK_MODE=copy`.
  - **Dependency layer:** copy `pyproject.toml`, `uv.lock` and `README.md` (the build backend reads the readme), then run `uv sync --locked --no-dev --no-install-project`.
  - **Project layer:** copy `apps/`, `packages/` and `alembic.ini`, then run `uv sync --locked --no-dev --no-editable`, so the project is installed as a regular wheel.
  - `--locked` fails the build if `uv.lock` does not match `pyproject.toml`. No dev dependencies are installed.
- **Runtime stage:**
  - **Contents:** the same base, plus `/opt/venv` and `/app/alembic.ini` only. No uv, compiler, source tree, tests, documentation or Git metadata.
  - **User:** a fixed system user and group `evidenceguard`, UID/GID 10001, with no login shell. `USER 10001:10001`.
  - **Permissions:** all files are owned by root and readable, not writable, by the runtime user. The application needs no writable path: uploads are stored in PostgreSQL. Compose adds a read-only root filesystem and a small `/tmp` tmpfs.
  - **Environment and command:** `WORKDIR /app`, `PATH=/opt/venv/bin:$PATH`, `PYTHONUNBUFFERED=1` and `PYTHONDONTWRITEBYTECODE=1`. Exec-form `CMD ["eg-api", "--host", "0.0.0.0", "--port", "8000"]` and `EXPOSE 8000`; no shell entrypoint.
  - **No configuration or secrets** are baked in: no `EG_DATABASE_URL`, no build arguments carrying secrets, no `.env`.
- **`.dockerignore`:** an allowlist, followed by recursive re-exclusions. In `.dockerignore` the last matching line decides, and only `**` patterns match at any depth (Docker build-context documentation).
  1. **Exclude everything:** `*`.
  2. **Include only:** `!pyproject.toml`, `!uv.lock`, `!README.md`, `!alembic.ini`, `!apps/` and `!packages/`.
  3. **Then exclude again, at any depth inside the included directories:**
     - `**/.env` and `**/.env.*`, with **no** credential-bearing exception;
     - `**/.git` and `**/.local`;
     - virtual environments, caches and bytecode: `**/.venv`, `**/venv`, `**/__pycache__`, `**/*.py[cod]`, `**/.mypy_cache`, `**/.ruff_cache`, `**/.pytest_cache`;
     - build outputs: `**/dist`, `**/build`, `**/*.egg-info`;
     - credential and key files: `**/*.pem`, `**/*.key`, `**/*.p12`, `**/*.pfx`, `**/id_rsa*`;
     - logs: `**/*.log`.

  Everything outside the allowlist stays out of the build context, including `.git`, `.local`, `.venv`, `dist`, `tests`, `docs` and `prompts.md`. The legitimate sources and package data under `apps/` and `packages/` (the `.py` modules, `py.typed` and `script.py.mako`) match none of the re-exclusions and stay included. The effective context is **verified**, not assumed (E2).

**B. Compose services (extending `docker-compose.yml`)**

- **`postgres`:** unchanged (image digest, credentials, health check, `127.0.0.1:5433`, volume, init script).
- **One image selection** for `migrate`, `api` and `worker`, shared through a YAML anchor: `build: .`, `image: ${EG_IMAGE:-evidenceguard:dev}` and `pull_policy: never`.
  - **Development:** the default `evidenceguard:dev` is built locally by `docker compose build`.
  - **CI:** sets `EG_IMAGE` to a unique tag (E1).
  - **No registry pulls:** `pull_policy: never` means the application image is never pulled. A missing image is an error, so a same-named public image can never be substituted.
- **Shared application settings** (the same anchor):
  - `EG_DATABASE_URL=postgresql+psycopg://evidenceguard:evidenceguard-local-dev@postgres:5432/evidenceguard_dev`, the existing disposable development credentials (no `.env` file is needed);
  - `read_only: true`, a `/tmp` tmpfs, `cap_drop: [ALL]`, `security_opt: [no-new-privileges:true]` and `init: true`. A minimal init process (PID 1) then forwards signals to the command and reaps processes.
- **`migrate`** (one-shot): `alembic -c /app/alembic.ini upgrade head`.
  - It depends on `postgres` being `service_healthy` and has `restart: "no"`.
  - It is the **only** service that migrates. The API and the worker never migrate at startup, so they cannot race.
- **`api`:** `eg-api --host 0.0.0.0 --port 8000`. Inside the container it must bind all interfaces to be reachable.
  - **Host port:** published only as `127.0.0.1:8000:8000`, never on all host interfaces.
  - **Dependencies:** `postgres` (`service_healthy`) and `migrate` (`service_completed_successfully`).
  - **Health check:** `GET /readyz` through the image's Python (`urllib`; no curl in the slim image). Interval 5 s, timeout 3 s, 20 retries, start period 5 s.
- **`worker`:** `eg-worker`, with the same dependencies as `api`. No ports. The worker has no HTTP readiness endpoint; it is "started" once running, and polls with its existing backoff if the database is briefly unavailable.
- **Worker shutdown** (`stop_signal: SIGTERM`, `stop_grace_period: 60s`):
  - The first SIGTERM triggers the worker's existing graceful stop (M3b, ADR-0008).
  - **The 60 s is an external termination budget, not a guaranteed shutdown bound.** The worker's waits are bounded supervisor waits, but a synchronous database call can delay its exit beyond them. If the budget expires, Docker sends SIGKILL (Compose's documented `stop_grace_period` behaviour).
  - M3f does not change the worker's shutdown semantics and introduces no database statement timeout.
- **Restart policy:** none (`restart: "no"`), so failures stay visible during development.
- **Database volume:** `docker compose down` keeps `evidenceguard-pgdata`; `docker compose down -v` deletes it. The init script runs only when a new volume is initialised.

**C. Developer commands** (to be documented in the README at implementation)

```
docker compose build               # builds the default image evidenceguard:dev
docker compose up -d --wait        # postgres healthy, migrate done, api healthy, worker running
docker compose run --rm migrate    # re-run migrations explicitly (idempotent)
docker compose exec api eg-admin seed-demo
docker compose exec api eg-admin create-key --tenant-id <tenant_id> --user-id <user_id>
#   prints the key once; keep it in a shell variable only, never in a file under version control
curl -sS -X POST http://127.0.0.1:8000/v1/vendors -H "Authorization: Bearer $EG_KEY" \
  -H "Content-Type: application/json" -d '{"slug": "lumenvale", "name": "Lumenvale"}'
curl -sS http://127.0.0.1:8000/v1/vendors/<vendor_id>/documents -H "Authorization: Bearer $EG_KEY" \
  -F document_key=security-policy -F "title=Security policy" -F source_type=vendor_statement \
  -F "file=@policy.md;type=text/markdown"
curl -sS http://127.0.0.1:8000/v1/jobs/<job_id> -H "Authorization: Bearer $EG_KEY"
curl -sS http://127.0.0.1:8000/v1/documents/<document_id> -H "Authorization: Bearer $EG_KEY"
curl -sS http://127.0.0.1:8000/v1/documents/<document_id>/revisions/1/chunks -H "Authorization: Bearer $EG_KEY"
docker compose logs api worker
docker compose stop                # requests a graceful stop; data kept
docker compose down -v             # remove containers and the database volume
```

The uploaded file is synthetic demonstration text. Commands use only the documented disposable credentials and a key created at runtime.

**D. Development convenience versus production**

M3f provides a **development stack** only. It does not provide:
- TLS;
- secrets management (the database credentials are disposable and public);
- resource limits;
- more than one worker;
- backups;
- image signing, an SBOM or registry publication;
- a production deployment.

The non-root user, read-only filesystem and dropped capabilities are sensible defaults, not a security certification. A production deployment is a later, separately reviewed decision.

**E. CI verification (required)**

Add one job, `container`, to `ci.yml`. It runs on `ubuntu-24.04` only, because GitHub's Windows runners cannot run Linux containers. It has `timeout-minutes: 20`, read-only `contents` permission, no registry login or push, and no new third-party actions: it uses the preinstalled Docker Engine and Compose v2 through plain commands.

**Shared selection:** every step uses the same values:
- the Compose file `docker-compose.yml`;
- the project name `P=eg-ci-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}`;
- the image `EG_IMAGE=evidenceguard:ci-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}`.

They are set once as job environment variables.

1. **Build:** `docker compose -f docker-compose.yml -p "$P" build api` builds the shared image and tags it `$EG_IMAGE`.
   - The job records `IMAGE_ID=$(docker image inspect --format '{{.Id}}' "$EG_IMAGE")`.
   - Base images resolve by digest, and the lockfile is enforced by `--locked`.
2. **Effective build context** (not just a text check of `.dockerignore`):
   - **Copy:** export the committed tree with `git archive HEAD` into a temporary directory.
   - **Plant fixtures:** add synthetic placeholder files there, never real secrets, at representative nested excluded paths:
     - `.env` and `.env.local` files under `apps/` and `packages/`;
     - `.git/`, `.local/`, `.venv/`, `__pycache__/` (`.pyc`), `.mypy_cache/`, `dist/` and `build/` directories inside packages;
     - a `.pem` file and an `id_rsa` file.
   - **List:** build a throwaway listing image from that directory. Its Dockerfile copies the context and lists every file, on the approved Python base. It lives outside the context, with no Dockerfile-specific ignore file, so the context root `.dockerignore` applies.
   - **Require:**
     - every tracked file under `apps/` and `packages/`, plus the four root files, is present, including `py.typed` and `script.py.mako`;
     - no planted file is present;
     - nothing else is present (for example `tests/`, `docs/`, `.github/`, `prompts.md`).

   The listing image is then removed.
3. **Image checks** (`docker run --rm "$EG_IMAGE" …`, each with a timeout):
   - `id -u` and `id -g` are `10001`;
   - `eg-api --help`, `eg-worker --help` and `eg-admin --help` succeed;
   - the installed-package import check (as in `verify`), and `alembic -c /app/alembic.ini upgrade head --sql` renders `CREATE TABLE api_keys` with no database;
   - `/app` contains no `.git`, `tests`, `.env` or `prompts.md`, and no `uv` executable is on `PATH`.
4. **Compose smoke:** a stdlib-only script, `infra/ci/compose_smoke.py`, run by the runner's Python.
   - **Database image:** before startup, the job explicitly pulls the existing approved PostgreSQL image, and only that image, by its digest:
     - `docker pull pgvector/pgvector:0.8.7-pg17@sha256:ac08538c6f8b9904c33c8224c5e5706dbe760aca29db1d096972b4052c22a75d`, run with a 300 s subprocess timeout;
     - building the application image does not guarantee that the database image is present in this job, and `--pull never` (below) applies to every service;
     - the database image selection in `docker-compose.yml` does not change, and no registry login or image publication is introduced.
   - **Startup:** `docker compose -p "$P" up -d --no-build --pull never --wait --wait-timeout 180`: database ready, `migrate` exited 0, `api` healthy (`/readyz` 200), `worker` running. `--no-build` and `--pull never` mean the smoke can neither rebuild nor pull a different application image; the application containers must still run the exact CI-built image ID (next item).
   - **Image identity:** for each `migrate`, `api` and `worker` container, `docker inspect --format '{{.Image}}'` must equal `IMAGE_ID`.
   - **Key:** `eg-admin seed-demo`, then `eg-admin create-key` for the demo tenant-A reviewer (deterministic demo IDs). The `create-key` command's stdout is captured **privately in the script's memory**, so the smoke can obtain the generated credential. That private capture is never printed, written to disk or uploaded as an artifact. The key is also registered with `::add-mask::`, but GitHub masking is an **additional** protection, not the primary control (see step 5).
   - **Ingestion:**
     - create a vendor (201) and upload a synthetic Markdown document (202);
     - poll `GET /v1/jobs/{id}` every 2 s, up to a **90 s deadline**, until `succeeded`, with the production `ingest_revision` handler in the `worker` container;
     - the document view shows the revision active with `ingestion_state` `active`; the chunk view shows `verified_complete: true` and `stored_count == chunk_count ≥ 1`;
     - a duplicate upload returns 200.
   - **Worker shutdown:**
     - **What it tests:** this stops an **idle** worker, after the ingestion job has succeeded and nothing is claimable. It does **not** prove that an in-flight handler drains in a container. That behaviour is covered at process level by the M3b tests, not here.
     - **Stop:** `docker compose -p "$P" stop -t 60 worker`, run with a 90 s subprocess timeout.
     - **Inspect the outcome:** a successful `stop` command alone is **not** proof of a graceful exit. The script reads the stopped container's state with `docker inspect --format '{{.State.Status}} {{.State.ExitCode}} {{.State.OOMKilled}}'`.
     - **Require:** status `exited`, application exit code **0**, and `OOMKilled` `false`. Any other exit code fails the shutdown smoke, including 137 from a SIGKILL after the grace period, worker exit code 5 (abnormal) or any unexpected exit.
   - **Timeouts:** every subprocess call has its own timeout, sized above the wait it contains: about 240 s for `up`; 60 s for each `exec` or `inspect`; 90 s for `stop`; 60 s for `logs`; 120 s for `down`. Every HTTP request has a 10 s socket timeout. A poll deadline bounds the polling loop, not an individual hung call, so both kinds of bound apply.
5. **Diagnostics** (inside the smoke script; on success and failure):
   - **Capture first:** command output and container logs (`docker compose ps -a`, and the last 200 lines from `migrate`, `api`, `worker` and `postgres`) are captured into memory before anything is displayed.
     - They are **not** assumed to be privacy-safe JSON: Alembic, dependency or interpreter failures can print ordinary text and tracebacks.
     - All application data is synthetic, and the disposable database password is not logged by PostgreSQL.
   - **Redact:** before anything is printed, every captured text is checked for the generated key, and each occurrence is replaced with a fixed marker. This does not rely solely on GitHub masking.
   - **Never printed:**
     - HTTP response bodies; only status codes and selected fixed fields, such as `ingestion_state`, are printed;
     - raw command output, except after redaction;
     - exception representations; only exception class names are printed.
   - **Key-in-service-logs check:** on both paths, any occurrence of the key in the captured service logs is a smoke failure. It is reported only as the service name and a count, never the key or the offending line.
   - **Failure precedence:** the first failure is recorded and decides the script's exit status. Errors during diagnostics are reported as secondary and never replace it.
6. **Cleanup** (a separate workflow step with `if: always()`):
   - **Confirm ownership:** the containers, networks and volumes to remove are listed with the Compose project label `com.docker.compose.project=$P`, a name unique to this run and attempt.
   - **Remove:** then `docker compose -f docker-compose.yml -p "$P" down -v --remove-orphans` (120 s timeout), and `docker image rm "$EG_IMAGE"`. Only this run's resources and tag are removed; nothing outside the project is touched.
   - **Failure precedence:** cleanup failures are reported without hiding an earlier smoke failure.
   - **Limit:** losing the runner or a hard cancellation can prevent cleanup from completing. GitHub-hosted runners are discarded after the job.

**Feasibility:** GitHub's `ubuntu-24.04` runners ship Docker Engine and Compose v2. The stack is one slim Python image plus the already-used pgvector image, and every wait is bounded. A few minutes per run is expected, but **this is an estimate, not a measurement**. The job runs separately from the existing jobs.

**What the smoke does not show:** that the Compose stack works locally, an in-flight handler draining in a container, multi-worker behaviour, and production readiness. A passing run is recorded as **CI Compose verification**, separate from local Compose.

**F. Intended files (later implementation)**

- **New:** `Dockerfile`, `.dockerignore`, and `infra/ci/compose_smoke.py` (stdlib only; not part of the distribution).
- **Changed:** `docker-compose.yml` (adds `migrate`, `api` and `worker`) and `.github/workflows/ci.yml` (adds the `container` job; the existing jobs are unchanged).
- **Tests:** `tests/test_container_files.py`, a database-independent text check of invariants:
  - base images pinned by digest;
  - a non-root `USER`;
  - `pull_policy: never` and a single `EG_IMAGE` selection for all three application services;
  - loopback-only host ports;
  - `migrate` being the only service that runs migrations;
  - no `EG_DATABASE_URL` or secrets in the `Dockerfile`.

  It **complements**, and does not replace, the effective build-context check in E2.
- **Documentation:**
  - an ADR (`docs/decisions/0012-containers.md`) at implementation time, with the verified base-image digests and dates;
  - the README container section; the plan; the threat model;
  - `prompts.md`.
- **No changes to:** application code, migrations, dependencies or `uv.lock`.

**G. Acceptance criteria**

- **Build criteria:**
  - the image builds in CI from the committed lockfile with `--locked`;
  - both base images are pinned by digest and recorded with their dates, with the approved Python digest verified;
  - the runtime user and group are 10001;
  - the entry points and the offline migration SQL work from the image;
  - the image contains no `.git`, `.local`, `.env`, tests or uv;
  - the effective build context matches E2 exactly;
  - the container-file test passes on Ubuntu and Windows.
- **Smoke criteria:**
  - every step in E4 passes in CI within its bounds;
  - `migrate`, `api` and `worker` run the exact CI-built image ID;
  - the idle worker exits with application code 0, with no OOM kill;
  - the private `create-key` capture is never printed, written to disk or uploaded;
  - the key does not appear in the captured service logs, and is otherwise reported only as a service name and count;
  - all other diagnostic output is checked and redacted before display;
  - the PostgreSQL image is pulled only by its approved digest before startup;
  - cleanup runs whatever the outcome.
- **Remaining M3 requirements:**
  - The M3 acceptance criteria carried by M3a–M3e, and the dead-job projection obligation, are verified in CI and on `main` (M3e at `2e605e7`).
  - **Status (Prompts 102–104):** the M3f build and smoke criteria above passed in CI on `feat/container-stack` at `682101b`, and again on `main` at `e2463cb` (ADR-0012). Per the reviewer's decision, the passing CI Compose smoke satisfies the M3 Compose verification requirement alongside the other agreed criteria. The overall M3 acceptance assessment (M3 section above) was accepted at external review in Prompt 105, with its four evidence limitations.
  - No other outstanding M3 criterion was found. Local Compose stays unverified until it actually runs (§10).
- **Open decisions:** none; the four Prompt 95 decisions are settled above. Two items are implementation-time verifications, not open choices: the official-registry check of both digests, and Docker's actual behaviour for the commands in E. If either contradicts this specification, implementation stops for review.

**M4 – Embeddings, retrieval and corpus**

**Status (Prompt 133): [DECISION] M4a–M4f sequence and complete M4a specification
accepted at external review; M4a verified and on `main` at `5fdaa1c` (main push
CI and secret scan green; see [ADR-0013 main evidence](decisions/0013-embeddings.md#main-ci-evidence-at-5fdaa1c)).
Earlier feature-branch verification at `d501bd6` is historical. Linux/Windows
verification, CI builds and existing installed-wheel checks passed. Historically
(M4a at `5fdaa1c`, M4b at `872d0af`), CI's installed-wheel step did not execute the
embedding provider (verified from an isolated installed wheel locally on Windows in
Prompt 117). The M4c extension executes it on Ubuntu and Windows CI runners, verified on
`main` at `76fa5a3`, so that gap is closed for this version.
The [M4b persistence specification](#m4b-persistence-specification-accepted-at-review-prompt-116-implementation-pending)
was accepted at external review in Prompt 116 (proposed in Prompt 114, corrected
in Prompt 115). The M4b implementation on `feat/embedding-persistence`
([ADR-0014](decisions/0014-embedding-persistence.md)) was accepted at external review in
Prompt 118 and is **reviewed, verified in CI and on `main` at `872d0af`** (main push:
PostgreSQL `233 passed`, including all 29 M4b cases, plus Linux, Windows, build and
container verification; see the [main CI evidence](decisions/0014-embedding-persistence.md#main-ci-evidence-at-872d0af)). The earlier
feature-branch verification at `90240e3` is historical. The
[M4c indexing specification](#m4c-indexing-specification-accepted-at-review-prompt-124-implementation-pending)
was accepted at external review in Prompt 124 (proposed in Prompt 122, corrected in
Prompt 123). M4c was implemented on `feat/revision-indexing` by Claude Code in Prompt 125 ([ADR-0015](decisions/0015-revision-indexing.md)) and corrected in Prompt 126, with historical local Windows checks in Prompts 125–126; it was accepted at external review for a local commit in Prompt 127 and is **reviewed, verified in CI and on `main` at `76fa5a3`** (main push: PostgreSQL `251 passed`, including all 18 indexing cases, plus Linux, Windows, installed-wheel and container indexing verification; see the [ADR-0015 main CI evidence](decisions/0015-revision-indexing.md#main-ci-evidence-at-76fa5a3)). Earlier feature-branch verification at `600a366` is historical. The [M4d snapshot and retrieval specification](#m4d-snapshot-and-retrieval-specification-accepted-at-review-prompt-133-implementation-pending) was proposed in Prompt 131, corrected in Prompt 132 and **accepted at external review in Prompt 133**. Its implementation by Claude Code in Prompt 134, corrected in Prompt 135 ([ADR-0016](decisions/0016-snapshot-retrieval.md)), was **accepted at external review in Prompt 136** and is **reviewed, verified in CI and on `main` at `cf2b5743`** (main push: PostgreSQL `290 passed`, including all 39 M4d cases; see the [ADR-0016 main CI evidence](decisions/0016-snapshot-retrieval.md#main-ci-evidence-at-cf2b5743)); the feature-branch verification at `3d6e8395` is historical. The [M4e specification](#m4e-corpus-and-retrieval-evaluation-specification-accepted-at-review-prompt-143-implementation-pending) was accepted at external review in Prompt 143 (proposed in Prompt 140, corrected in Prompts 141–142); its implementation (Prompt 144, corrected in Prompts 145–146, [ADR-0017](decisions/0017-retrieval-evaluation.md)) was accepted at external review in Prompt 147 for a local commit and published on `feat/retrieval-evaluation` in Prompt 148 at `c14821b7`, where PostgreSQL passed with all 16 M4e cases but one Ubuntu test failed (a Linux-specific test-double recursion); the Prompt 149 test-only correction was accepted in Prompt 150 and published in Prompt 151; after feature-branch verification at `d1dcdfce` (historical), M4e is reviewed, verified in CI and on `main` at `0ae4c6ca` (see the [ADR-0017 main CI evidence](decisions/0017-retrieval-evaluation.md#main-ci-evidence-at-0ae4c6ca)). The [M4f specification](#m4f-voyage-adapter-specification-accepted-at-review-prompt-157-implementation-pending) was proposed in Prompt 154, corrected in Prompts 155–156 and accepted at external review in Prompt 157; its implementation (Prompt 158, corrected in Prompt 159, [ADR-0018](decisions/0018-voyage-adapter.md)) was accepted at external review in Prompt 160 and, after feature-branch verification at `84eec023` (historical), is reviewed, verified in CI and on `main` at `5acb75e5` ([evidence](decisions/0018-voyage-adapter.md#main-ci-evidence-at-5acb75e5)); the [overall M4 acceptance assessment](#overall-m4-acceptance-assessment-accepted-at-review-prompt-165) was prepared in Prompt 164, and overall M4 was
accepted at external review in Prompt 165 within the reviewed scope implemented at `5acb75e5`; its acceptance record was published on `main` at `46c02257` in Prompt 166 ([evidence](#acceptance-publication-evidence-prompt-166)); M5 implementation has not started; local Compose remains unverified.** M1, M2 and M3 remain accepted.

The reviewer inspected the full Prompt 107 diff, independently matched its
SHA-256 checksum and checked the existing chunk domain and chunker source
against the 4,000-code-point input bound. The reviewer ran no project tests or
documentation checks. Acceptance makes no benchmark or semantic-quality claim.
M4b–M4f require their own detailed specification reviews: their exact schemas,
migration, lock ordering, provider transport and operational limits remain
unapproved by acceptance of this sequence. Later-slice design sketches below
remain proposals except for the explicitly accepted directions and defaults.

#### M4 direction and review decisions

[DECISION] Preserve D7/D11 and §§4–7: a provider interface, offline
`HashingEmbedder` (`fake-hash-v1`, 1024 dimensions, unigrams and bigrams),
Voyage adapter mocked in CI, exact cosine search plus PostgreSQL full-text
search, per-channel top 20, RRF constant 60, final top 8, tenant/snapshot
filtering, synthetic clean/injected corpus and ground truth. No framework,
approximate index, downloaded model or M5 orchestration is added.

[FACT] At the accepted specification baseline `ac39503`, source had parsing/chunking,
`chunk_sets`, immutable chunks and `ingest_revision`, but no embeddings, generated
tsvector, retrieval implementation or review snapshot persistence. Prompt 109 adds
only M4a embedding contracts and offline hashing, accepted for a local commit in Prompt 110; no other
retrieval or snapshot functionality is implemented. [ADR-0010](decisions/0010-document-ingestion.md)
and `require_complete_chunk_set` gate activation on exact chunk completeness;
the broader §4 description of embeddings before activation is a future design,
not current behaviour. Existing leases, lock order, fresh-time checks, atomic
finish and cancellation remain governed by [ADR-0007](decisions/0007-durable-job-core.md),
[ADR-0008](decisions/0008-worker-runtime.md) and [ADR-0009](decisions/0009-document-revisions.md).

Accepted dependency-ordered sequence (Prompt 108; each later slice needs its own reviewed detail):

| Slice | Scope and completion evidence |
|---|---|
| M4a | Immutable embedding identity/batch contracts, provider protocol, deterministic offline hashing and validation. Detailed below; no persistence or provider access. |
| M4b | Embedding profiles/index records, tenant-scoped storage and migration, full-text representation, exact vector operations and completeness/readiness. Real PostgreSQL constraints, migration round trips and filtering tests. Introduce pgvector here when vector storage/operators first require it; M4a needs no extension. Detailed specification [accepted at review in Prompt 116](#m4b-persistence-specification-accepted-at-review-prompt-116-implementation-pending) (proposed in Prompt 114, corrected in Prompt 115); implemented in Prompt 117, accepted in Prompt 118, verified in CI and on `main` at `872d0af` ([ADR-0014](decisions/0014-embedding-persistence.md)). |
| M4c | Separate durable `index_revision` jobs over completed immutable chunk sets, enqueue/backfill seam and registered handler. Test leases/fences, replay, partial batches, conflicting retries, cancellation and atomic readiness/job finish. No review workflow. Detailed specification [accepted at review in Prompt 124](#m4c-indexing-specification-accepted-at-review-prompt-124-implementation-pending) (proposed in Prompt 122, corrected in Prompt 123); implemented by Claude Code in Prompt 125, corrected in Prompt 126 and accepted at external review for a local commit in Prompt 127 ([ADR-0015](decisions/0015-revision-indexing.md)); verified in CI and on `main` at `76fa5a3`, including PostgreSQL and container indexing. |
| M4d | Explicit snapshot input/capture seam, eligibility validation, deterministic lexical/vector/RRF retrieval and bounded results. PostgreSQL isolation, snapshot-after-supersession, ranking and tie tests. No review endpoints or report generation. Detailed specification [accepted at review in Prompt 133](#m4d-snapshot-and-retrieval-specification-accepted-at-review-prompt-133-implementation-pending) (proposed in Prompt 131, corrected in Prompt 132); implementation staged in Prompt 134 and corrected in Prompt 135 ([ADR-0016](decisions/0016-snapshot-retrieval.md)), accepted at external review in Prompt 136; reviewed, verified in CI and on `main` at `cf2b5743` ([main CI evidence](decisions/0016-snapshot-retrieval.md#main-ci-evidence-at-cf2b5743)). |
| M4e | Synthetic clean/injected corpus, stable anchor-to-chunk ground truth, Recall@5/@8 and retrieval contracts. Include cross-tenant, cross-vendor and superseded traps and missing answers; no semantic-quality claim. Detailed specification [accepted at review in Prompt 143](#m4e-corpus-and-retrieval-evaluation-specification-accepted-at-review-prompt-143-implementation-pending) (proposed in Prompt 140, corrected in Prompts 141–142); implementation (Prompt 144, corrected in Prompts 145–146, [ADR-0017](decisions/0017-retrieval-evaluation.md)) accepted at external review in Prompt 147 for a local commit and published in Prompt 148 at `c14821b7` (PostgreSQL passed with all 16 M4e cases; one Ubuntu test failed from a test-double recursion); Prompt 149 test-only correction accepted in Prompt 150; verified in feature-branch CI at `d1dcdfce` (historical); reviewed, verified in CI and on `main` at `0ae4c6ca` ([main CI evidence](decisions/0017-retrieval-evaluation.md#main-ci-evidence-at-0ae4c6ca)). |
| M4f | Voyage adapter behind the same contract, injected transport mocked in CI, fixed profile/configuration, bounded calls and safe error mapping. No live calls required for M4 acceptance; live quality evidence belongs to M7. Detailed specification [accepted at review in Prompt 157](#m4f-voyage-adapter-specification-accepted-at-review-prompt-157-implementation-pending) (proposed in Prompt 154, corrected in Prompts 155–156); implemented by Claude Code in Prompt 158 and corrected in Prompt 159 ([ADR-0018](decisions/0018-voyage-adapter.md)) accepted at external review in Prompt 160; verified in feature-branch CI at `84eec023` (historical); reviewed, verified in CI and on `main` at `5acb75e5` ([main CI evidence](decisions/0018-voyage-adapter.md#main-ci-evidence-at-5acb75e5)), including both Voyage PostgreSQL cases on both pushes. |

**[DECISION] Separate indexing readiness (Prompt 108); later persistence details remain proposals.** Retain M3's activation and immutable
chunk rules. Treat indexing readiness as separate from revision status: an active
but unindexed revision exists and is not silently treated as searchable. M4b
should store an immutable profile with a tenant-scoped ID; an index record binds
tenant, revision, chunker version, chunk manifest/count and profile fingerprint.
Embedding rows reference both their index and `(tenant_id, chunk_id)` through
composite constraints, with revision membership checked by matching composite
keys, not UUID assumptions. Uniqueness is per index/chunk; no mixing profiles,
dimensions, text hashes or tenants. M4b specifies the exact schema and migration,
including finite/nonzero dimension checks in the application and enforceable
database checks. Use exact pgvector cosine operations without HNSW/IVFFlat;
the 1024-dimensional baseline fits a fixed-dimensional column. Supporting other
dimensions later requires explicit reviewed schema design, not silent padding.

**[REC] Job compatibility (M4c detail still requires review).** Existing `JobPayload` values are canonical UUIDs
only. Use an `index_id` UUID to resolve immutable profile/revision metadata;
do not put model strings, arrays, text or keys in the payload. Enqueue and index
creation are atomic and idempotent. A bounded explicit backfill handles already
settled revisions; future activation can enqueue indexing in its transaction,
without calling a provider or changing chunk immutability. Jobs may index a
previously activated, now superseded revision for an existing snapshot; revisions
that never activated are ineligible. Provider work and hashing happen outside
fences; writes use short fenced batches with tenant checks and fresh ownership
rechecks after locks. Retain job → document → revisions lock order before new
index locks, and specify all additional lock ordering in M4c. Partial rows stay
ineligible until count/manifest/profile completeness and readiness commit with
job success. Identical replay compares immutable fields; changed vectors or
profile metadata conflict, never overwrite. A live provider may be nondeterministic:
reuse committed batches; repeated uncommitted calls are possible, not exactly-once.
No embedding failure demotes an active revision or mutates settled chunks.

**[DECISION] Refuse unready snapshot capture (Prompt 108); the detailed M4d seam remains proposed.** M4d accepts a trusted immutable value
containing actor-derived tenant, vendor, explicit distinct revision IDs, chunk
manifests, profile identity and retrieval configuration. A database capture seam
selects only that vendor's active pointers with verified complete chunks and
ready indexes in one consistent read transaction. Accepted policy: refuse the
capture if any active revision is not ready, rather than silently omit it; record
pending/processing exclusions. Empty eligible sets are an explicit error.
No public request may declare arbitrary revision IDs authorized; the internal
constructor validates tenant/vendor membership and snapshot eligibility. M5
persists the same authorization/configuration facts atomically with review creation.
A manually constructed ID list alone proves neither past eligibility nor authority.

**[DECISION] Supersession clarification (Prompt 108).** “No superseded chunks” means no revision
already superseded at *snapshot capture* enters a new snapshot. A revision active
at capture remains eligible for that snapshot after later activation supersedes
it; retrieval must not re-filter it by today's `active` status. A new revision
is never added to an older snapshot. Current-state search first captures a fresh
snapshot. Never-activated, failed, incomplete, foreign-vendor/tenant, non-snapshot
or wrong-profile chunks remain excluded. This clarifies the contradictory old
M4 wording while preserving §4's snapshot/resume invariant; this clarification was accepted at external review
in Prompt 108.

**[DECISION] Ranking/input/result bounds (Prompt 108); detailed M4d ranking design remains proposed.** Accepted M4d defaults: 1–8 distinct nonblank queries,
each at most 4,000 code points and 16,000 UTF-8 bytes; 1–100 revision IDs;
at most 100,000 eligible chunks (reject excess, never silently truncate);
per-channel limit 20 and final requested k 1–20 (default 8).
Use explicit PostgreSQL `simple` text configuration for both full-text document
and query processing. Filter tenant/vendor/snapshot/profile/readiness *before*
each channel's limit; ignore zero lexical scores and zero query vectors.
For each distinct query/channel list, use one-based ranks, ties by canonical
chunk UUID ascending; fuse each chunk with sum `1 / (60 + rank)` across lists.
Final ties use canonical chunk UUID ascending; return each chunk once with
channel ranks, scores, pinned profile and provenance. All-zero hash queries yield
no vector candidates, not a division error; no candidates yields an empty result.
Determinism is for a fixed stored corpus/configuration and database/provider
outputs, not a promise of bit-identical live embeddings across calls or platforms.
Bounds are accepted initial engineering defaults, not benchmark-derived limits.

**[DECISION] Recall semantics (Prompt 108); detailed M4e corpus/mapping design remains proposed.** Preserve §7's fictional tenants, vendors, conflict,
missing evidence, table, wrong-claim valid-quotation and injection cases. Load
clean/injected variants separately; only the injection paragraph differs, while
revision hashes and resulting IDs may differ. Human anchors plus exact quoted
spans resolve deterministically against the pinned chunker/manifest. Accepted
relevance unit is a distinct authorized chunk ID: resolve each gold passage to
every chunk containing its full required span; fail ambiguous/missing mappings
unless an explicit multi-chunk span annotation resolves them. Deduplicate chunks
when several anchors share one chunk. For a question with nonempty gold set G,
`Recall@k = |set(top_k_chunk_ids) ∩ G| / |G|`; the denominator is all relevant
snapshot chunks, not k or answerable-question count. Duplicate retrieval IDs
are contract errors. Empty gold sets yield N/A, excluded from the macro mean,
with excluded count reported; all-empty suites yield N/A, not 1. Report per-question
values and macro mean over nonempty sets at k=5 and k=8, separately by variant
and profile. Foreign or forbidden results fail isolation even if recall is high.
Unit examples include 2/3, duplicate anchors, fewer than k results, and empty G.
Hashing proves reproducibility and retrieval contracts on synthetic inputs;
collisions and lexical dependence prevent semantic-quality or injection-resistance
claims. End-to-end canary/output behaviour and claim judgments remain M5/M7.

#### M4a local verification (Prompt 109)

The specification remains accepted (Prompt 108), and the implementation was
accepted for a local commit in Prompt 110. It was verified in feature-branch CI
at `d501bd6` (historical; see the [CI evidence and wheel
check scope](decisions/0013-embeddings.md#feature-branch-ci-evidence-at-d501bd6))
and is now verified and on `main` at `5fdaa1c` ([main CI evidence](decisions/0013-embeddings.md#main-ci-evidence-at-5fdaa1c)).
Linux/Windows verification and CI builds are complete for both commits; at that point direct
embedding-provider execution from an isolated installed wheel was unverified in CI (historical; the
M4c wheel extension later closed this gap, verified on `main` at `76fa5a3`). It adds frozen
identity/usage/batch values, canonical fingerprints, strict request/result
validation, the provider protocol and deterministic `HashingEmbedder`, with
fixed private errors and the lexical-hash label. See [ADR-0013](decisions/0013-embeddings.md).
No M4b–M4f implementation, retrieval or semantic-quality evidence is added.

Historical Prompt 109 local Windows checks used the existing Python 3.12 locked environment,
with `--offline --no-sync` to avoid network and dependency installation:

- `uv run --locked --offline --no-sync ruff format --check .`: 125 files already formatted.
- `uv run --locked --offline --no-sync ruff check .`: all checks passed.
- `uv run --locked --offline --no-sync mypy`: no issues in 107 source files.
- `uv run --locked --offline --no-sync pytest tests/test_embeddings.py tests/test_packaging.py -q`:
  126 passed in 1.30s (116 embedding tests and 10 existing packaging/import checks).
- `uv run --locked --offline --no-sync pytest -q -ra`: 1479 passed, 205 skipped in 38.74s.
  Exactly 204 skips: `EG_TEST_DATABASE_URL is not set; integration tests need a
  disposable PostgreSQL test database (see README)`.
  One POSIX-only signal skip on Windows: `raise_signal(SIGTERM) ends a Windows process`.
  PostgreSQL tests did not run; no database was contacted.
- `uv build --offline --no-build-isolation --out-dir .local/p109/dist`: failed
  before producing a distribution because `hatchling` was absent from the
  local environment (`ModuleNotFoundError`). No dependency was installed. This
  historical local failure is separate from the later successful CI builds and
  existing clean installed-wheel checks at `d501bd6`; at that point direct installed-wheel
  embedding-provider execution was unverified (historical).

Initial lint/type issues in new code/tests were corrected before the final
passing checks. An environment-denial test initially interfered with pytest's
own environment reads; limiting the patch to the embedding call fixed the test
harness. The final suite includes that corrected test. These results prove
tested contracts, not semantic quality or provider behaviour. Final staged
scope, whitespace, private-content and Gitleaks checks are recorded in the
Prompt 109 handoff, not implied by these application-check results.

#### M4a first implementation slice (specification ACCEPTED at review, Prompt 108; implementation ACCEPTED for a local commit, Prompt 110)

**Scope.** Pure contracts and offline provider only, using the standard library
and existing domain validation. No migrations, SQL, worker registration, settings,
HTTP, SDK, dependency changes, keys, corpus loader or retrieval service.

**Identity and values.** Accepted frozen domain values:
`EmbeddingIdentity(provider_id, model_id, algorithm_version, dims, normalization)`;
`EmbeddingUsage(input_tokens)` with a nonnegative strict integer or `None` when
unknown; `EmbeddingBatch(identity, input_type, vectors, usage)`.
The provider protocol is `embed(texts: tuple[str, ...], input_type: Literal['query',
'document']) -> EmbeddingBatch`, plus an immutable `identity` property. Input
order equals vector order. Put shared values in domain and the protocol/adapters
in retrieval, preserving import direction and current stricter retrieval import
test (domain and standard library only).

Identifiers are bounded lowercase ASCII `[a-z][a-z0-9._-]{0,63}`;
`dims` is a strict integer 1–4096; `normalization` is `l2` in this slice.
Reject booleans, coercions and unknown fields. Identity fingerprint is SHA-256
of ASCII JSON with exactly those five field names, sorted keys, compact
separators, no NaN; never rely on Python `hash()` or mutable aliases.
Hash identity is provider `offline`, model `fake-hash-v1`, algorithm
`ascii-word-sha256-v1`, dims 1024, normalization `l2`. Any feature, hashing,
dimension or normalization change requires a new identity/version. Query and
document paths share this algorithm but retain the requested `input_type`.
Future Voyage identity must pin requested model, dimensions and adapter contract
version; model aliases cannot establish an upstream immutable model revision.
Record any provider-returned model identity and fail on unexpected mismatch;
do not claim that an API alias guarantees reproducibility.

**Input validation.** Require an immutable tuple of 1–32 strings; each is 1–4,000
code points, at most 16,000 UTF-8 bytes, contains no NUL, encodes strictly as
UTF-8, and is not whitespace-only (`str.isspace`). Total batch cap 128,000
UTF-8 bytes. Reject invalid inputs before computing vectors. Preserve input
strings exactly at the boundary (disable inherited whitespace stripping);
duplicates are allowed and retain their positions. These bounds cover existing
4,000-code-point chunks, including Unicode. No implicit truncation or splitting.

**Deterministic hashing algorithm.** Extract maximal `[A-Za-z0-9]+` runs and
ASCII-lowercase each. Other characters delimit tokens; no Unicode normalization,
stemming, stopword list, random seed or built-in `hash()`. Features are `u:` plus
each token, and `b:` plus each adjacent token pair joined by one ASCII space.
Count every occurrence. For each feature, SHA-256 its UTF-8 bytes; bucket is the
first eight digest bytes as an unsigned big-endian integer modulo 1024; sign is
+1 when digest byte 8 is even, -1 otherwise. Add signed integer counts, then
normalize once using square root of the sum of squared counts, with coordinates
in bucket order. No features or complete collision cancellation yields a 1024-zero
vector. Usage is `input_tokens=None`: feature counts are not billable tokens.
Always label output “lexical-hash baseline — not semantic”.

**Output validation.** Vectors are immutable tuples of finite real coordinates
(strict int/float, excluding bool), count matches inputs and length matches
identity dims. Every nonzero vector has L2 norm within absolute tolerance 1e-6
of 1; zero vectors are explicitly permitted only for the offline provider and
must be skipped by future cosine retrieval. A live adapter rejects zero vectors.
Reject NaN, infinity, wrong count/dims/type, identity mismatch and malformed
usage. Validate provider output at the caller boundary as well as construction;
the batch alone cannot know the requested input count/identity. Fixed error
codes/messages carry no input text, vectors, provider response or exception body;
representations omit texts and vector contents. No content logging is added.

**M4a files (implemented in Prompt 109; accepted for a local commit in Prompt 110):**

- New `packages/domain/evidenceguard_domain/embeddings.py`: frozen values,
  canonical identity and request/output validation, with fixed errors.
- New `packages/retrieval/evidenceguard_retrieval/embeddings.py`: protocol and
  `HashingEmbedder`; no persistence/worker/API imports.
- New `tests/test_embeddings.py`: contracts, independently pinned vectors/buckets
  and negative cases; existing `tests/test_packaging.py` import checks apply.
- New ADR [0013-embeddings.md](decisions/0013-embeddings.md);
  README, plan and prompt history record the implementation and verification limits.
- No change to `pyproject.toml`, `uv.lock`, existing chunker or ingestion semantics.

**Meaningful acceptance checks for M4a:**

1. Pin literal fingerprint and independently calculated feature bucket/sign
   fixtures for unigrams, bigrams, repetition and a collision; no expected vector
   generated by the implementation under test. Check ordering, normalization,
   punctuation/case behaviour, non-ASCII-only zero output and cancellation.
2. Same vectors across independent processes with different `PYTHONHASHSEED`,
   query/document modes, and duplicate/batch versus single inputs; run on both
   Windows and Ubuntu. Floating comparisons use the stated tolerance, not exact
   cross-platform byte equality.
3. Exercise every input bound at and beyond its boundary, UTF-8 supplementary
   characters, lone surrogates, NUL, blank text, invalid mode, mutable collections,
   booleans/coercions, unknown fields and immutable-value copy revalidation.
4. A fake provider returns count/dimension/identity mismatches, NaN/infinity,
   non-unit vectors, malformed usage and live zero output: boundary rejects each
   with fixed messages and no input/vector leakage in repr/error output.
5. Confirm import boundaries and offline operation with no environment reads,
   network, keys or model downloads. Run focused tests, lint, format and strict
   typing plus the existing database-independent suite when implementing.
   No database test proves M4a more strongly; SQL compilation mocks must never
   be represented as tenant/constraint or lease verification.

Later PostgreSQL slices must run real constraints, extension/migration up/down,
foreign-tenant/revision joins, readiness completeness, expired-lease lock waits,
partial-batch replay, concurrent activation/snapshot capture and frozen-snapshot
retrieval tests in guarded integration CI. Those checks are proposed, not run.

**[DECISION] Accepted at external review (Prompt 108):** complete M4a contracts,
identity/fingerprint, strict validation, input/batch bounds, deterministic ASCII
hashing/version and offline zero-vector policy; separate indexing readiness
without changing M3 activation; refusal-on-unready snapshot policy; snapshot-relative
supersession; ranking/input/result bounds as initial engineering defaults; and
chunk-based Recall denominator, empty-gold N/A handling and separate variant/profile
reporting. These decisions make no benchmark or semantic-quality claim.
M4b–M4f need detailed reviews before their implementation, including pgvector
schema and live-adapter request/timeout/retry/token limits. No dependency or
provider documentation research was needed for M4a; historical model/pricing
notes in §2 are not freshly verified availability or price claims.

#### M4b persistence specification (ACCEPTED at review, Prompt 116; implementation pending)

**Status.** [DECISION] Accepted at external review in Prompt 116. Claude Code
wrote it in Prompt 114 and corrected it in Prompt 115. The reviewer settled
decisions 1–4 and 6–12 as recommended and decision 5 differently: the extension is
preserved on downgrade (Prompt 115).

These are design decisions, not execution evidence. At acceptance (Prompt 116)
nothing below was implemented or verified. Implementation needs its own
authorization and ADR-0014.

**Implementation (Prompt 117; accepted in Prompt 118; verified in CI and on `main` at `872d0af`).** Claude Code
implemented this specification as recorded in
[ADR-0014](decisions/0014-embedding-persistence.md), which lists the implementation
choices made within it (UUID namespace literals, explicit constraint names, a
nullable generated `search_vector`, a local migration DDL type, reflection
registration and additional fixed errors). Historical Prompt 117 local Windows checks ran: lint, format,
strict typing, 102 focused database-independent tests, the full suite (1585 passed,
234 skipped: 233 integration tests without a database and one POSIX-only signal
test), integration collection, the build and clean installed-wheel checks. At that
point (historical, Prompts 117–118) no PostgreSQL test had run. Those local results are
Prompt 117 evidence by Claude Code, not CI evidence. The external reviewer accepted
the implementation for a local commit in Prompt 118 after inspecting the diff,
matching its checksum and running independent standard-library probes, without
running the project suite, an installed-wheel check, PostgreSQL or Docker.

**Feature-branch CI (historical; Prompt 119, evidence retrieved by the reviewer and
recorded in Prompt 120).** Both push runs for `90240e3` on `feat/embedding-persistence`
succeeded: Ubuntu `1586 passed, 233 skipped`, Windows `1585 passed, 234 skipped`,
PostgreSQL `233 passed, 1586 deselected` (all 29 M4b cases passed, none failed or
skipped), the container job with all six required steps, and Gitleaks (51 commits,
no leaks). This verifies the M4b paths the tests cover, nothing beyond them. CI's
installed-wheel checks did not then execute embeddings directly; that was verified
only locally on Windows (historical; closed by the M4c wheel extension at `76fa5a3`). At that point M4b was not merged. Full links and attribution:
[ADR-0014](decisions/0014-embedding-persistence.md#feature-branch-ci-evidence-at-90240e3).

**Main publication (Prompt 121; main-push evidence retrieved by the reviewer and
recorded in Prompt 122).** `main` was fast-forwarded to `872d0af`. The main-push runs
succeeded: Ubuntu `1586 passed, 233 skipped`, Windows `1585 passed, 234 skipped`,
PostgreSQL `233 passed, 1586 deselected` with all 29 M4b cases, the container job with
all six steps, and Gitleaks (52 commits, no leaks). See the
[main CI evidence](decisions/0014-embedding-persistence.md#main-ci-evidence-at-872d0af). At that point M4c–M4f and overall M4 acceptance were pending. M4b's acceptance
authorized no indexing handler or retrieval functionality; M4c later received its own reviewed
specification (Prompt 124) and implementation (Prompt 125), while M4d–M4f still require detailed
reviews. Items marked [DECISION] in earlier sections stay authoritative.

**Scope.** Embedding profiles, index records, embedding rows, the lexical
representation, migration `0005`, pgvector numeric storage, bounded fenced
batch writes and the completeness/readiness check, plus their tests. Out of scope:
the `index_revision` handler, enqueue/backfill wiring and handler registration
(M4c); snapshot capture, ranking, RRF and retrieval execution (M4d); corpus and
evaluation (M4e); the Voyage adapter and any live provider call (M4f); review
orchestration and endpoints (M5). M3 activation, `require_complete_chunk_set`,
chunk text, IDs, spans and the chunk write path stay unchanged.

**Preserved accepted decisions.** Indexing readiness is separate from revision
status and activation. Tenant/revision/profile isolation through composite keys.
Exact vector operations only: no HNSW or IVFFlat. A fixed 1024-dimensional column.
The existing job fence, lease and lock-order architecture. Snapshot-relative
supersession (M4d). Capture refuses an unready active revision rather than
omitting it (M4d).

##### A. Schema (migration `0005`)

The chain on `main` is `0001` → `0002` → `0003` → `0004` (head). M4b adds
`v0005_embeddings.py` (revision `0005`, revises `0004`), written to match the
models, with constraint text spelled out as in earlier revisions. Named
constraints follow the existing `NAMING_CONVENTION`. No triggers (existing convention).

*Additive constraints on existing tables (FK targets only; no data change):*

- `chunk_sets`: `UNIQUE (tenant_id, revision_id, chunker_version, chunk_count,
  manifest_sha256)`. The existing primary key already allows one set per revision,
  so this is always satisfiable. It lets an index row prove, in the database, that
  its copied count and manifest are the chunk set's.
- `chunks`: `UNIQUE (tenant_id, revision_id, chunker_version, id, content_sha256)`.
  `id` is already unique, so this always holds. It lets an embedding row prove that
  its chunk belongs to the index's revision and chunker version, and that its
  copied text digest is the chunk's.
- `chunks`: the generated `search_vector` column and its GIN index (section D).

*`embedding_profiles`* (immutable; one row per tenant and identity):

| Column | Type | Rule |
|---|---|---|
| `id` | uuid | PK; `uuid5(PROFILE_NAMESPACE, f"{tenant_id}:{fingerprint}")` (see decision 8) |
| `tenant_id` | uuid | FK → `tenants.id` |
| `provider_id`, `model_id`, `algorithm_version` | varchar(64) | CHECK `~ '^[a-z][a-z0-9._-]{0,63}$'` (the M4a pattern) |
| `dims` | integer | CHECK `dims = 1024` (this slice's fixed column) |
| `normalization` | varchar(16) | CHECK `= 'l2'` |
| `fingerprint` | varchar(64) | CHECK `~ '^[0-9a-f]{64}$'`; M4a `EmbeddingIdentity` fingerprint |
| `allows_zero_vectors` | boolean | CHECK `allows_zero_vectors = (provider_id = 'offline')` |
| `created_at` | timestamptz | default `now()`; metadata, never compared |

Keys: `UNIQUE (tenant_id, id)`; `UNIQUE (tenant_id, fingerprint)`;
`UNIQUE (tenant_id, id, dims, allows_zero_vectors)` as the index FK target.
Profiles are tenant-scoped (accepted direction); the same identity in two tenants
gives two rows with different IDs.

*`embedding_indexes`* (one per revision, chunker version and profile):

| Column | Type | Rule |
|---|---|---|
| `id` | uuid | PK; `uuid5(INDEX_NAMESPACE, f"{tenant_id}:{revision_id}:{chunker_version}:{profile_id}")` |
| `tenant_id` | uuid | FK → `tenants.id` |
| `revision_id`, `chunker_version`, `chunk_count`, `manifest_sha256` | as `chunk_sets` | composite FK → the new `chunk_sets` unique key |
| `profile_id` | uuid | with `dims`, `allows_zero_vectors`: composite FK → profile key above |
| `dims` | integer | CHECK `= 1024` (copied, FK-checked) |
| `allows_zero_vectors` | boolean | copied, FK-checked |
| `status` | varchar(16) | CHECK `IN ('building', 'ready')` |
| `vector_manifest_sha256` | varchar(64) null | CHECK hex; `(status = 'ready') = (vector_manifest_sha256 IS NOT NULL)` |
| `created_at` | timestamptz | default `now()` |
| `ready_at` | timestamptz null | `(status = 'ready') = (ready_at IS NOT NULL)`; set from `clock_timestamp()` |

Keys: `UNIQUE (tenant_id, id)`; `UNIQUE (tenant_id, revision_id, chunker_version,
profile_id)`; `UNIQUE (tenant_id, id, revision_id, chunker_version,
allows_zero_vectors)` as the embedding FK target. Index on `(tenant_id, profile_id,
status)` for M4d's eligibility read.

*`chunk_embeddings`* (immutable; one per index and chunk):

| Column | Type | Rule |
|---|---|---|
| `tenant_id`, `index_id`, `chunk_id` | uuid | PK `(tenant_id, index_id, chunk_id)` |
| `revision_id`, `chunker_version`, `allows_zero_vectors` | copied | composite FK `(tenant_id, index_id, revision_id, chunker_version, allows_zero_vectors)` → index key |
| `content_sha256` | varchar(64) | composite FK `(tenant_id, revision_id, chunker_version, chunk_id, content_sha256)` → new `chunks` key |
| `embedding` | `vector(1024)` | not null; pgvector enforces the dimension and finite values |
| `vector_sha256` | varchar(64) | CHECK `vector_sha256 = encode(sha256(vector_send(embedding)), 'hex')` |
| `is_zero` | boolean | CHECK `is_zero = (vector_norm(embedding) = 0)` |
| — | — | CHECK `NOT is_zero OR allows_zero_vectors` |
| — | — | CHECK `is_zero OR abs(vector_norm(embedding) - 1) <= 1e-6` |
| `created_at` | timestamptz | default `now()`; never compared |

`vector_send`, `vector_norm` and `sha256` are `IMMUTABLE STRICT` in PostgreSQL 17
and pgvector 0.8.7, so they are valid in CHECK constraints. `vector_norm`
accumulates in double precision, so it is zero exactly when every coordinate is zero.

*Nullability (Prompt 115).* Every column in the three new tables is `NOT NULL`
except `embedding_indexes.ready_at` and `embedding_indexes.vector_manifest_sha256`.
Specifically, the following are `NOT NULL`:

- `embedding_profiles`: `id`, `tenant_id`, `provider_id`, `model_id`,
  `algorithm_version`, `dims`, `normalization`, `fingerprint`,
  `allows_zero_vectors`, `created_at`.
- `embedding_indexes`: `id`, `tenant_id`, `revision_id`, `chunker_version`,
  `chunk_count`, `manifest_sha256`, `profile_id`, `dims`, `allows_zero_vectors`,
  `status`, `created_at`.
- `chunk_embeddings`: `tenant_id`, `index_id`, `chunk_id`, `revision_id`,
  `chunker_version`, `allows_zero_vectors`, `content_sha256`, `embedding`,
  `vector_sha256`, `is_zero`, `created_at`.

This matters because neither CHECKs nor composite FKs reject NULL inputs on
their own. A CHECK whose expression evaluates to NULL passes. A composite FK
with any NULL column is not checked under the default `MATCH SIMPLE`. A NULL
`is_zero` or `allows_zero_vectors` would therefore slip past the zero-policy CHECK,
and a NULL copied `revision_id` or `content_sha256` would skip the membership FK.
`status` defaults to `'building'`, and the insert never supplies ready metadata.
A new index is therefore `building` with `ready_at` and `vector_manifest_sha256`
NULL. The ready-state pairing CHECKs above remain unchanged.

*Lifecycle and transitions.* An index moves only `building` → `ready`, never back,
and never `ready` → anything. There is no `failed` state: failures belong to the
M4c job, and an abandoned `building` index is simply ineligible (decision 7). Rows
are inserted only while their index is `building`; no row is ever updated or
deleted by application code. Profiles are never updated. An index may be created
only for a revision with `activated_at IS NOT NULL` (active, or superseded after
being active). That value is never cleared once set, so this check reads it
without a lock.

*Enforcement boundary.*

| Invariant | Enforced by |
|---|---|
| Required columns present (all but `ready_at` and `vector_manifest_sha256`), so CHECKs and FKs cannot be bypassed by NULL | PostgreSQL `NOT NULL` |
| Tenant match across profile, index, chunk set, chunk and embedding | PostgreSQL composite FKs |
| Embedding's chunk belongs to the index's revision and chunker version; copied text digest equals the chunk's | PostgreSQL composite FK (new `chunks` key) |
| Index's count/manifest equal the chunk set's; dims/zero policy equal the profile's | PostgreSQL composite FKs |
| One row per index/chunk; one index per revision/chunker/profile; one profile per tenant/fingerprint | PostgreSQL unique keys |
| 1024 dimensions; no NaN/infinity | pgvector type modifier and input checks |
| Unit norm (tolerance 1e-6) or zero; zero only for zero-permitting profiles; digest matches stored vector | PostgreSQL CHECKs (pgvector functions) |
| Ready ⇔ `ready_at` ⇔ vector manifest present | PostgreSQL CHECKs |
| Fingerprint equals the hash of the five identity fields | Trusted application code (JSON canonicalization is not reproduced in SQL); re-verified at readiness |
| Index only for an ever-activated revision; complete before ready; `building` → `ready` only; no writes to ready indexes; no updates/deletes; `-0.0` canonicalized | Trusted application code, under the locks below |
| Profile identity matches the caller's provider | Trusted application code |

As with chunks, privileged direct database modification bypasses the
application invariants; this is not a sandbox.

##### B. Numeric storage

*Representation.* `vector(1024)` stores 1024 IEEE-754 float32 values. Provider
values are float64 Python floats, so storage is lossy by design. **Equality, replay
and digests refer to canonical stored float32 values, never provider float64
values.** No exact float64 round trip is promised.

*Canonicalization (pure domain code, before storage).* Starting from an
M4a-validated vector (strict finite reals, correct count/dims, norm or zero policy):

1. Convert each coordinate to float32 with `struct.pack('>f', x)` (IEEE
   round-to-nearest). Overflow raises the fixed invalid-embedding error.
2. Replace `-0.0` with `0.0`, so equal vectors have equal bytes.
3. Re-validate the canonical float32 vector against the storage contract: finite;
   zero exactly when every coordinate is zero; a nonzero provider vector that
   rounds to all zeros is rejected; nonzero norm (computed in float64 over the
   float32 values) within the same absolute 1e-6 of 1. Failure raises the fixed,
   privacy-safe invalid-embedding error. There is no silent renormalization and no
   widened tolerance.

   **Provider-contract validity does not guarantee storage-contract validity.** A
   vector accepted by M4a can fail after rounding. The reviewer's
   standard-library probe (Prompt 115; not a project-suite or database test): a
   coordinate, and so a norm, of `0.999999001` passes M4a's 1e-6 tolerance, but
   its float32 value `0.9999989867210388` is outside it. Such vectors are rejected,
   not stored.

   The whole batch is canonicalized and re-validated **before any SQL**. One
   rejected vector rejects the batch: no partial batch write, and the database is
   unchanged.
4. Wire bytes: `struct.pack('>HH1024f', 1024, 0, *coords)`, identical to
   pgvector's binary send format (int16 dims, int16 zero, big-endian float4).
   `vector_sha256` is the SHA-256 hex digest of these bytes.

*Write path.* Bind a text literal `[c0,c1,…]` where each coordinate is Python
`repr` of the float32-exact double, cast to `vector(1024)`. pgvector parses with
`strtof`. The decimal is the shortest string identifying a double that is
exactly a float32, so `strtof` returns that float32 exactly. The database CHECK then
proves that the stored bytes hash to the application's `vector_sha256`. A rounding
difference fails the insert rather than storing a different vector.

*Read path.* Read `vector_send(embedding)` as `bytea` and decode with the same
struct format. That gives exact float32 bits, with no text parsing. Text output
(shortest float32 decimal) is never parsed back for comparison.

*SQLAlchemy/psycopg integration (decision 4).* A small in-repo SQLAlchemy
`UserDefinedType` renders `vector(1024)` in DDL and binds through
`CAST(:value AS vector(1024))`. Its reflection name is registered for
`alembic check`, and reads use explicit `func.vector_send(...)`. psycopg needs
no adapter, because values cross as text in and `bytea` out. No new Python dependency.

*Zero vectors.* Stored only under offline profiles, with `is_zero = true`.
pgvector's cosine distance against a zero vector is NaN, so every future cosine
query must include `NOT is_zero` explicitly, and M4d skips zero query vectors (accepted).

##### C. Writes, completeness and immutability

Proposed module `evidenceguard_persistence/embeddings.py`. Its style follows `chunks.py`:
fixed-message errors, tenant from the job, no commits or transaction-control SQL,
and statements built by functions so tests can inspect them.

*Caller-transaction operations (no vectors, no readiness):*

- `ensure_profile(session, tenant_id, identity)`: `INSERT … ON CONFLICT DO NOTHING`
  on `(tenant_id, fingerprint)`, then read the row back and compare all identity
  fields. A difference raises `EmbeddingProfileConflictError`.
- `create_index(session, tenant_id, revision_id, profile)`: requires the revision to
  exist in the tenant with `activated_at IS NOT NULL`, and a chunk set to exist.
  It copies the chunk-set binding, inserts with `ON CONFLICT DO NOTHING`, then
  compares all bound fields. It returns an immutable `IndexSnapshot`. M4c calls it
  in the same transaction as `enqueue` (payload `{"index_id": …}`), like
  `create_revision`. M4b wires no production caller (decision 10).

*Fenced operations* take `FencedSession` and the fence's `JobSnapshot`. Both
start with the same job binding (Prompt 115):

- **Job binding.** Require `job.kind == "index_revision"`. Require the validated
  `JobPayload` (canonical UUID values, already enforced by M3a) to contain exactly
  the key `index_id`. Anything else raises a fixed `IndexJobMismatchError` before
  any further lock or write. The index is looked up only by `(job.tenant_id,
  index_id)`. A missing row, including one that exists in another tenant, raises
  the fixed `IndexNotFoundError`; foreign rows are never read or locked.
- **Lock order:** job row (already locked by the fence) → that index row
  `FOR UPDATE`. No document, revision, chunk-set or chunk locks.
- **Fresh ownership.** On every successful return path, including no-ops,
  `recheck_ownership` runs after the last lock or unique-index wait and before
  the block can commit, and the re-read job's tenant must equal the index's tenant.

- `write_embeddings(session, job, identity, rows)`: one bounded batch of 1–32
  `StoredEmbedding(chunk_id, content_sha256, canonical vector, vector_sha256)`
  values with distinct chunk IDs, already canonicalized and re-validated before
  any SQL (section B). Steps:
  1. Bind the job and lock the index row; require `building`, otherwise raise
     `EmbeddingWriteRefusedError` before any insert.
  2. Require the profile's stored fingerprint to equal the `identity.fingerprint`
     property.
  3. Pre-read `(id, content_sha256)` of those chunks in the index's revision and
     chunker version. A missing or different chunk raises a fixed error before
     insert (the composite FKs remain the backstop).
  4. Run `INSERT … ON CONFLICT (tenant_id, index_id, chunk_id) DO NOTHING
     RETURNING chunk_id`.
  5. For each row not returned, compare the stored `content_sha256`,
     `vector_sha256` and `is_zero` exactly. Any difference raises
     `EmbeddingConflictError`. Nothing is overwritten.
  6. Call `recheck_ownership` and require the job's tenant.
- `mark_index_ready(session, job, identity)`: bind the job and lock the index row.
  If the index is already `ready` and its profile fingerprint equals
  `identity.fingerprint`, write nothing. It still calls `recheck_ownership`
  after the lock wait, so a lease that expired or was reassigned while waiting
  raises `LeaseLostError` and the job cannot succeed. Otherwise run
  `require_complete_index`, set `status = 'ready'`, `ready_at = clock_timestamp()`
  and the vector manifest, then call `recheck_ownership`. M4c calls it only inside
  `ctx.fenced(finish=True)`, so readiness and job success commit or roll back together.

*Completeness (`require_complete_index`)* runs under the index lock and checks more
than the row count:

1. The profile's five stored identity fields hash to its stored fingerprint, which
   equals the caller's `identity.fingerprint` and dims 1024.
2. Chunk-set verification uses the immutable index binding and does **not** call
   `require_complete_chunk_set(session, revision, *, expected)`. That function is
   M3's activation callback: it needs a `RevisionSnapshot` locked by
   `activate_revision`, and M4b neither locks revisions nor builds snapshots.
   Instead, a new private helper in `embeddings.py` reuses the existing public
   pieces without changing `chunks.py`:
   - `chunk_set_statement(tenant_id, revision_id)`, whose stored
     `(chunker_version, chunk_count, manifest_sha256)` must equal the index's
     bound values;
   - `manifest_rows_statement(tenant_id, revision_id, chunker_version)` with
     `MANIFEST_COLUMNS`, which must return exactly ordinals `0 … count-1`;
   - the pure domain helpers `manifest_entry` and `manifest_sha256`, whose rebuilt
     digest must equal both the stored and the bound `manifest_sha256`.

   Tenant, revision and chunker version come only from the locked index row. An
   `ExpectedChunkSet(chunker_version, chunk_count, manifest_sha256)` may be
   constructed from those bound values for validation, but no `RevisionSnapshot`
   is fabricated. M3 locking, activation and the activation callback are unchanged.
3. A single join of chunks to this index's embeddings, ordered by ordinal, returns
   one embedding for every chunk, with matching `content_sha256` and no extra rows
   (embedding count equals `chunk_count`).
4. The vector manifest is the SHA-256 of ASCII lines
   `f"{ordinal}:{chunk_id}:{content_sha256}:{vector_sha256}\n"` in ordinal order.
   Each `vector_sha256` is CHECK-bound to the stored vector bytes, and finiteness,
   dims, norm and zero policy are CHECK-enforced. So completeness verifies the
   stored vectors without transferring up to 4,096 × 1,024 coordinates inside the
   fenced transaction.

Any failure raises `IndexIncompleteError`; nothing changes.

*Immutability.* Ready indexes and all embedding rows are immutable by application
invariant: writers require `building` under the row lock, and no update/delete
statement exists. Triggers are not proposed (decision 6).

*M4b/M4c boundary and atomic readiness.* M4c's handler embeds outside any fence
(provider calls and hashing never hold locks). It first reads already-stored chunk
IDs and skips them, so committed batches are reused and a nondeterministic live
provider is not re-asked for them. Each batch then goes through
`with ctx.fenced(): write_embeddings(...)`. Readiness and job success commit together in
`with ctx.fenced(finish=True) as f: mark_index_ready(f.session, f.job, identity)`.
That uses the existing worker path, which runs `fence.succeed()` in the same transaction.

*Lock order.* M4b's fenced operations take job row (the fence) → `embedding_indexes`
row. They read only immutable rows: profiles, chunk sets, chunks, and
`activated_at` once set. So they take no document or revision locks and cannot deadlock
with activation. Any future path that takes both obeys job → document →
revisions (ascending ID) → `embedding_indexes` (ascending ID) → `chunk_embeddings`.
Each operation is one short transaction; a lock wait beyond the fence's 5-second
`lock_timeout` maps to `JobLockTimeoutError`. Ownership is re-checked after the
last lock or unique-index wait on every successful path, including idempotent
no-ops, before commit.

*Tests and fences.* PostgreSQL tests obtain fences through the real `enqueue` →
`claim` → `fenced_transaction` path with a job of kind `index_revision`. They add
no handler registration, no test-only bypass and no unfenced production write path.

*Lexical eligibility.* Lexically searchable chunks never become eligible before
vector readiness. Eligibility is per revision and profile and requires a ready
index for both channels. With the accepted refusal policy, an active revision
whose index is not ready blocks capture; it is never searched lexically alone (decision 11).

##### D. Full-text representation

- Source text: exactly the stored `chunks.text`, the same text that is embedded.
  No header prefix, section path or normalization.
- `chunks.search_vector tsvector GENERATED ALWAYS AS (to_tsvector('simple'::regconfig,
  text)) STORED`. The two-argument, explicit-`regconfig` form is IMMUTABLE and
  independent of `default_text_search_config`. M4d uses the same explicit `simple`
  configuration for queries.
- GIN index on `(search_vector)`. It is exact (not approximate) and only accelerates
  matching, so results do not depend on it.
- Rationale for a generated column over a maintained one (decision 2): it is always
  consistent with the immutable text, has no write path, lag or backfill, and leaves
  the chunk insert statement and comparison fields unchanged. Cost: the migration
  rewrites `chunks` under an exclusive lock, and rows get larger. Chunk text, IDs and
  spans are unchanged.
- Required query shape for M4d: tenant, snapshot revision, profile, readiness and
  (vector) `NOT is_zero` filters sit in the same `WHERE` as the match. They come
  before the per-channel `ORDER BY … LIMIT 20`, never applied after a limited
  subquery. Ranking and retrieval execution remain M4d.

##### E. Migration and dependencies

*Upgrade order:* `CREATE EXTENSION IF NOT EXISTS vector`, the two additive unique
constraints, `chunks.search_vector` and its GIN index, `embedding_profiles`,
`embedding_indexes`, `chunk_embeddings`. *Downgrade order* (dependency-safe):
`chunk_embeddings`, then `embedding_indexes`, then `embedding_profiles`, then the
GIN index and `chunks.search_vector`, then the two added unique constraints. The
embedding FKs depend on those constraints, so the constraints are dropped after
the tables. Downgrade issues no extension statement.

*Extension lifecycle ([DECISION] settled in Prompt 115, replacing proposal 5).*
`0005` runs `CREATE EXTENSION IF NOT EXISTS vector`, because it is the first
migration that needs the extension. Downgrade removes only this migration's own
objects and **leaves `vector` installed**, whether it was preinstalled or created by
`0005`. There is no ownership marker, no `pg_depend`-based drop logic and no
`CASCADE`.

This residual infrastructure is deliberate. An extension is database-wide and
may serve unrelated objects, and Alembic cannot know who else relies on it.
Removing it is an explicit administrative operation (`DROP EXTENSION vector`, run
by its owner or a superuser after checking dependants), outside Alembic downgrade.
Re-upgrade succeeds because of `IF NOT EXISTS`.

Every statement is plain DDL, valid in online mode and in offline `--sql`
rendering. No step inspects the database from Python, so the existing
installed-wheel offline-rendering check keeps working. No `VERSION` is pinned in
SQL; tests assert the CI image's version.

*Test-database implications.* A database downgraded from `0005` may now retain
`vector`, so tests must not assume the extension is absent after a downgrade. The
disposable-database guard (`require_disposable_test_database`: `_test` suffix and
a target distinct from the application database) is unchanged. The
`empty_database` fixture resets with `DROP SCHEMA public CASCADE`, followed by
`CREATE SCHEMA public`. `vector` is installed in `public`, and dropping a schema
with `CASCADE` also drops extensions whose objects live in it, so each fresh test
database should start without `vector`. This is PostgreSQL behaviour still to be
confirmed in CI, not assumed. The fixture adds one assertion after its reset:
`pg_extension` is exactly `{plpgsql}`. If CI disproves the schema-cascade
behaviour, the fixture, not the migration, adds `DROP EXTENSION IF EXISTS vector`
to its reset, under the same guard. The fixture's existing `CASCADE` stays
test-only, and the migration's no-`CASCADE` rule is unaffected. Existing
fresh-empty-database safety checks (the unmigrated `/readyz` test asserting only
`plpgsql`) remain as they are.

*Privileges.* pgvector's control file does not mark it `trusted`, so creating it
needs a superuser. The CI and Compose databases use the image's bootstrap role
(`POSTGRES_USER`), which is a superuser, so no workflow or Compose change is
expected. That is to be confirmed in CI, not assumed. For other deployments a DBA
pre-installs the extension. `IF NOT EXISTS` then skips creation, which should need
no superuser; this is unverified, and an optional non-superuser test is proposed.
Downgrade needs no extension privilege, because it never drops the extension.

*Python dependency research (Prompt 114, official PyPI metadata and changelogs).*
pgvector-python 0.5.1 (uploaded 2026-10-09) is younger than the two-week policy
and is excluded. 0.5.0 (2026-07-06) has no declared dependencies (NumPy was
removed in 0.5.0), requires Python ≥ 3.10 and SQLAlchemy ≥ 2. PyPI lists no
vulnerabilities, and the project publishes no security advisories. The pgvector
extension's GitHub advisories page lists none either. Its 0.8.2/0.8.6/0.8.7
buffer-overflow fixes concern HNSW/IVFFlat index builds, which this design never
creates. **Recommendation: add no Python dependency** (decision 4). If the reviewer
prefers the library, pin exactly `pgvector==0.5.0` with an `exclude-newer-package`
cutoff. Canonical float32 handling would still be needed, because its SQLAlchemy
type returns Python float lists. No installation is done in this proposal.

##### F. Tests (planned, not written or run)

*Database-independent:*

- Canonicalization: round-to-nearest fixtures with independently calculated
  float32 bits, `-0.0` handling, overflow, rounds-to-zero rejection, offline zero
  accepted, live zero rejected.
- Post-rounding storage validation (Prompt 115). The concrete lower-boundary
  example: a vector whose norm is `0.999999001` passes M4a validation and is
  rejected after rounding to `0.9999989867210388`. Successful rounding cases
  (`1.0`, `0.9999995` → `0.9999995231628418`, `1.000001` → `1.0000009536743164`,
  and 1,024 coordinates of `1/32`). The adjacent float32 values on each side of
  both tolerance boundaries, `1 - 1e-6` and `1 + 1e-6`, pinned as independently
  calculated literals. A batch with one failing vector raises the fixed error,
  carries no vector, text or ID in its message or repr, and issues no SQL (asserted
  through the fake session). These are planned project tests; the Prompt 115
  reviewer probe is not one of them.
- Pinned literal fixtures: wire bytes, `vector_sha256`, the vector-manifest digest,
  and profile/index uuid5 IDs.
- Text-literal formatting and parse-back equality for edge values (subnormal,
  ±max float32 within range, 1/32).
- Statement construction: tenant predicates, conflict targets, `FOR UPDATE` lock
  order, and no `CASCADE`.
- Fake-session protocol tests in the `test_chunk_store.py` style: refusal before
  insert, conflict comparison, ownership re-check last, fixed error messages with no
  vectors or IDs. These are labelled as protocol tests, never as constraint evidence.

*Real PostgreSQL (guarded integration job):*

- Migration and extension lifecycle (Prompt 115):
  - `vector` is absent in a fresh reset test database before the first upgrade
    (the fixture assertion);
  - present at head;
  - **retained** after downgrade to `0004`, with every `0005` table, index,
    generated column and added constraint gone;
  - re-upgrade to head succeeds;
  - a preinstalled `vector` plus an unrelated `vector`-using table created before
    upgrade both survive upgrade, downgrade to `0004` and re-upgrade, unchanged;
  - `alembic check` reports no drift, and offline SQL renders for upgrade and
    downgrade without a connection and contains no `DROP EXTENSION` or `CASCADE`;
  - the existing fresh-empty-database checks (unmigrated `/readyz`, no tables,
    only `plpgsql`) still pass.
- NOT NULL (Prompt 115): direct SQL inserting NULL into each required column is
  rejected with a not-null violation. This covers especially `is_zero`, both
  `allows_zero_vectors` columns, every copied FK column (`revision_id`,
  `chunker_version`, `chunk_count`, `manifest_sha256`, `dims`, `content_sha256`),
  `vector_sha256`, `fingerprint` and `status`. A new index is `building` with NULL
  `ready_at` and `vector_manifest_sha256`.
- Composite constraints: cross-tenant profile/index/chunk, another revision's chunk,
  another chunker version, mismatched copied `content_sha256`, count/manifest or
  dims/zero-policy mismatch. Each row is rejected.
- Numerics: wrong dimension, NaN, infinity, an out-of-range literal, non-unit
  norm, zero under a non-zero profile and `vector_sha256` mismatch are rejected.
  An offline zero is stored with `is_zero`. Float32 replay: the stored
  `vector_send` bytes equal the application wire bytes for adversarial coordinates.
  Application/database agreement: for canonical vectors that pass application
  validation, the database CHECKs accept them and `vector_norm` agrees within the
  tolerance. A batch rejected by application storage validation leaves the tables
  unchanged (row counts and index state compared before and after).
- Writes: identical replay is a no-op; a changed vector or digest conflicts without
  overwriting; a batch over 32 rows is refused before SQL; a write to a ready index
  is refused.
- Readiness: partial index stays `building`; missing row, extra or foreign rows
  (impossible through FKs, asserted), wrong profile fingerprint and manifest
  mismatch each refuse readiness. Readiness is idempotent; no transition leaves
  `ready`.
- Fencing and concurrency: an expired or reassigned lease rolls back the batch;
  two concurrent writers on one index serialise on the row lock; a lock wait past
  `lock_timeout` maps to `JobLockTimeoutError`. Rollback after a mid-batch error
  leaves no rows. Readiness rolls back with a failed `fence.succeed()` (simulated
  through the real fence).
- Job binding (Prompt 115), for both writes and readiness: a wrong job kind; a
  payload without `index_id`, with an extra key, or with an `index_id` naming
  another tenant's index or no index. Each raises its fixed error with no write
  and no foreign-row lock. Stale ownership after waiting on the row lock of an
  **already-ready** index raises `LeaseLostError` from the no-op path, and the job
  does not succeed.
- Lexical: the generated `search_vector` matches `to_tsvector('simple', text)`, and
  chunk insert/compare behaviour is unchanged.
- Existing tests to update: `test_no_extensions_are_created` (expect `{plpgsql,
  vector}` at head; rename and update its reference in
  `test_persistence_safety.py`), expected head `0005` and the head table set.
  Existing no-extension assertions on freshly reset empty databases stay. No
  assertion may expect absence after a downgrade from `0005`. The
  upgrade/downgrade/upgrade test down to `base` keeps its table and version
  assertions, and `vector` is expected to remain after it.

*Intended implementation files:* `packages/domain/evidenceguard_domain/embedding_storage.py`,
`packages/persistence/evidenceguard_persistence/models.py`, `…/embeddings.py`,
`…/migrations/versions/v0005_embeddings.py`, `tests/test_embedding_storage.py`,
`tests/test_embedding_store.py`, PostgreSQL tests (existing file or a new marked
file), updates to `tests/test_persistence_postgres.py` and
`tests/test_persistence_safety.py`, ADR-0014, README and plan. No change is expected
to workflows, Compose, the Dockerfile, `pyproject.toml` or `uv.lock`; the
container smoke migration runs `0005` unchanged.

*Evidence rule.* Every result above is planned. Only checks actually run against a
real database count as constraint, migration or lease evidence. SQL-compilation and
fake-session tests do not.

##### Settled review decisions

**Review outcome:** [DECISION] in Prompt 115, recommendations 1–4 and 6–12 below
were approved as recommended, subject to the corrections now in this section.
Decision 5 was settled differently: the extension is preserved on downgrade (the
normative policy is in section E). The complete corrected specification was
accepted in Prompt 116. The numbered list below is the **historical Prompt 114
recommendation text**, kept unchanged except for the superseded note on item 5.

1. **Additive FK-target unique keys on `chunks` and `chunk_sets`.** Recommend yes:
   the database then proves revision, chunker and digest membership. Tradeoff: two
   extra indexes and a change to existing tables, without changing any data. The
   alternative is application-only checks.
2. **Generated stored `tsvector` plus GIN.** Recommend yes; it matches §4's
   "generated `tsvector`". Alternatives: an expression GIN index only (no table
   rewrite, but every query must repeat the exact expression) or a maintained table
   (write path and lag).
3. **CHECKs that use pgvector functions** (norm, zero flag, digest). Recommend yes.
   Tradeoff: insert CPU and coupling to pgvector function semantics, which the tests pin.
4. **No new Python dependency.** Recommend an in-repo type. The alternative is
   exactly `pgvector==0.5.0`.
5. **Extension downgrade.** Recommend a guarded drop with no ownership marker.
   Tradeoff: an unused, DBA-preinstalled extension would be removed on a full
   downgrade. Alternatives: never drop, or record ownership in a marker.
   *Superseded in Prompt 115: never drop; downgrade preserves `vector`.*
6. **Immutability without triggers.** Recommend application-enforced, following the
   existing convention, with tests. Alternative: rejecting triggers.
7. **Index states `building`/`ready` only.** Recommend yes; failure lives on the job.
8. **Deterministic uuid5 profile/index IDs.** Recommend yes, for idempotent
   enqueue/backfill keys. The namespaces become fixed constants.
9. **Batch bound of 32 rows.** Recommend matching M4a's provider batch (about
   400 KB of literal per statement).
10. **`create_index`/`ensure_profile` in the caller's transaction.** Recommend yes,
    mirroring `create_revision` with `enqueue`. They store metadata only; vectors
    and readiness stay fenced.
11. **No lexical-only eligibility before readiness.** Recommend yes, consistent with
    the accepted refusal policy.
12. **`content_sha256` copied into embeddings.** Recommend yes, FK-checked. It binds
    each vector to the exact text that was embedded.

#### M4c indexing specification (ACCEPTED at review, Prompt 124; implementation pending)

**Status.** [DECISION] The **complete M4c specification was accepted at external review in
Prompt 124**. Claude Code proposed it in Prompt 122 and corrected it in Prompt 123; the choices
under [Settled review decisions](#settled-m4c-review-decisions-prompt-123) were settled in
Prompt 123. At acceptance (Prompt 124) nothing was implemented; acceptance established the
design and the planned verification requirements, not implementation or execution evidence.

**Implementation (Claude Code, Prompt 125, corrected in Prompt 126; accepted at external
review in Prompt 127 for a local commit; verified in CI and on `main` at `76fa5a3`).** Claude Code implemented this specification as recorded in
[ADR-0015](decisions/0015-revision-indexing.md). Historical Prompt 125 local Windows checks: lint,
format, strict typing, the focused tests, the full suite (1703 passed, 250 skipped: 249
integration tests without a database and one POSIX-only signal test), integration collection, the
build, clean installed-wheel checks including the new CI wheel script (run locally on Windows),
and offline migration rendering.

**Correction (Prompt 126).** Review found that `resolve_provider` converted `JobCancelledError`,
`LeaseLostError` and `FenceClosedError` raised by a provider factory or identity into
`UnsupportedProfileError`, contrary to the contract. They now propagate unchanged. Ordinary
failures remain fixed and private, and `ctx.check()` runs before such a failure is classified.
The regression tests failed against the Prompt 125 handler (10 of the 16 selected cases) and pass
against the corrected one. The PostgreSQL cancellation test now observes the latched cancellation
instead of sleeping, and two backfill tests were added (ready-index exclusion; a dead canonical
job reported `stalled`). Prompt 126 local Windows checks, attributed to Claude Code's handoff
(not rerun by Codex or the reviewer):
- handler tests: 54 passed;
- focused checks: 273 passed, 1 POSIX-only skip;
- the full suite: 1715 passed, 252 skipped (251 integration tests without a database and one
  POSIX-only signal test);
- collection: 1967 tests, 251 integration and 1716 database-independent;
- Ruff lint and format, and strict mypy passed;
- the build and clean installed-wheel checks passed, including the CI wheel script and the corrected
  control flow from `site-packages`.

These runs executed the offline `HashingEmbedder` only; no external provider or network was
contacted. Historical (before CI): at that point the 18 PostgreSQL tests in
`tests/test_indexing_postgres.py`, the other integration tests, the wheel step in CI (Linux and
Windows runners) and the container indexing smoke had **not run**, and all 251 integration tests,
including the 18 indexing cases, were unexecuted against this M4c version. CI at `600a366`
later ran them (below).

**External acceptance (Prompt 127).** The reviewer accepted the complete implementation with
Prompt 126 corrections for a local commit, pending PostgreSQL and current-version CI
verification. The reviewer inspected both diffs and supporting tests, independently matched
the Prompt 125 SHA-256 `88fe6c40a9d34cd3ee82540de0a74d23d1fd26630820ecb9385a18ebaa55cd7d`
and Prompt 126 SHA-256 `9619a490ccceec4db73593e45cebb1368fbf551e3199cbcc89e447b6bdc2acaf`,
and reproduced the original provider-resolution bug. Independent isolated standard-library
probes confirmed six factory/identity control-flow cases preserve the same exception object,
cancellation and lease loss take precedence over ordinary resolution failure, and an ordinary
factory failure becomes a fixed error without the original exception chained. The reviewer
did not run the project suite, installed-wheel checks, PostgreSQL or Docker. Codex assists
with acceptance documentation and the local commit only; no application checks were rerun.
Prompt 127 authorized and completed no publication or merge; at that point PostgreSQL, Linux,
real container indexing and the new wheel step on CI runners were pending (later verified at
`600a366`, below); local Compose is unverified. M4d–M4f and overall M4 acceptance remain pending. The accepted specification
heading and anchor above remain the historical Prompt 124 baseline.

**Exact-commit CI verification (`600a366`, Prompts 128–129).** OpenAI Codex published
`feat/revision-indexing` in Prompt 128 with a history-only commit
`600a366453bd94811ab1d741dc0b28adeb427031`. Both push workflows for that exact commit passed
(attempt 1); the external reviewer independently retrieved both run records and all five job
logs, and Claude Code recorded them in Prompt 129 without retrieving them itself. Observed:
Ubuntu `1716 passed, 251 skipped`, Windows `1715 passed, 252 skipped`, PostgreSQL
`251 passed, 1716 deselected` with all 18 indexing cases passing, distribution builds and the
installed-wheel offline embedding/storage execution and indexing imports on both platforms, the
container job with all six required steps (its smoke ran the production `backfill-indexes`
command and worker indexing to a ready index with matching counts), and Gitleaks (55 commits,
no leaks). Details, links and limits are in the
[ADR-0015 feature-branch CI evidence](decisions/0015-revision-indexing.md#feature-branch-ci-evidence-at-600a366).
This covers the exercised paths only; nobody ran these checks locally for this verification.
At that point M4c was not merged and `main` was at `872d0af` (historical).

**Main publication (`76fa5a3`, Prompts 130–131).** Claude Code committed the reviewed
verification documentation and prompt history as `76fa5a3800936d2bebdf13c5401609e09983b0d1`
(parent `600a366`; implementation files unchanged) and, after all five feature-push jobs for
that commit succeeded, fast-forwarded `main` from `872d0af` to it (Prompt 130). Claude Code
observed run, job and step conclusions only; its anonymous log download returned HTTP 403. The
external reviewer independently retrieved the main run records and all five job logs, recorded
in Prompt 131: Ubuntu `1716 passed, 251 skipped`, Windows `1715 passed, 252 skipped`, PostgreSQL
`251 passed, 1716 deselected` with all 18 indexing cases passing, both builds and the
installed-wheel embedding/storage execution and indexing imports, the container job with all six
steps including the production backfill and ready indexing, and Gitleaks (56 commits, no leaks).
No counts are recorded for the feature-branch push of `76fa5a3`. Details and limits:
[ADR-0015 main CI evidence](decisions/0015-revision-indexing.md#main-ci-evidence-at-76fa5a3).
M4c is **on `main` at `76fa5a3`**. Its limits are unchanged, and M4d–M4f and overall M4
acceptance remain pending.

Within this accepted section, the items labelled [REC] (written as recommendations in
Prompts 122–123) now form the **accepted implementation contract** for M4c. Explicitly deferred
work stays deferred: recovery generations, activation wiring, live adapters and M4d–M4f.
Nothing here accepts any M4d–M4f recommendation; those slices need their own detailed reviews.
Labels: **[DECISION]** accepted; **[SETTLED]** settled at review in Prompt 123; **[FACT]**
established from source on `main` at `872d0af`; **[REC]** an original recommendation, now part
of the accepted contract.

**Scope.** Explicit enqueue and bounded backfill of `index_revision` jobs, an `eg-admin` command,
the production handler and its fixed offline provider mapping, bounded batching with reuse of
committed rows, atomic readiness with job success, cancellation and failure mapping, the tests,
and the CI changes they require. Out of scope: snapshot capture and retrieval (M4d), corpus
(M4e), live adapters (M4f), review orchestration (M5), and any redesign of M4a or M4b.

##### Preserved decisions

[DECISION] (Prompt 108; M4b, Prompts 114–118):
- separate durable `index_revision` jobs whose payload is exactly `{"index_id": "<UUID>"}`;
- tenant-scoped immutable index, profile and chunk-set binding;
- only ever-activated revisions, including a now-superseded revision when it is explicitly
  indexed;
- atomic index creation and idempotent enqueue;
- provider computation outside fences, with bounded fenced writes and reuse of committed rows;
- readiness and job success together through `ctx.fenced(finish=True)`;
- no mutation of settled chunks and no demotion of active revisions;
- no retrieval and no M5 workflow.

##### Settled M4c review decisions (Prompt 123)

[SETTLED] The reviewer settled these in Prompt 123; the complete specification, including them,
was accepted in Prompt 124.
1. Trusted internal enqueue and backfill seams, callable with the existing reviewer, approver
   or admin roles. No public API endpoint.
2. `eg-admin backfill-indexes`, fixed to `HASH_IDENTITY` and using the existing trusted-operator
   model.
3. Stalled canonical jobs are reported, never reset, replaced or rescheduled. Recovery
   generations remain deferred.
4. Activation wiring is deferred; M3 activation and ingestion semantics are preserved.
5. The existing fixed job error codes are reused for this offline-only slice.
6. Initial engineering defaults, not measured performance claims: provider and write pages of
   at most 32 chunks and 128,000 UTF-8 bytes; a backfill default limit of 50 (maximum 100); and
   the existing default of 3 job attempts.
7. The embedding-specific CI wheel check and the production-path offline indexing smoke
   (both below) are **required** M4c acceptance checks.

##### Facts from current source

- [FACT] `enqueue(session, actor, *, kind, idempotency_key, payload, max_attempts=3)` runs in
  the caller's transaction and **returns only a `JobSnapshot`**: it does not say whether this
  call inserted the job. The tenant comes only from `actor`. An identical retry returns the
  existing job unchanged, even when terminal. A differing payload or `max_attempts` raises
  `JobIdempotencyConflictError`. At READ COMMITTED, concurrent inserts resolve through the
  unique key; `JobEnqueueRaceError` is raised when the conflicting row is not visible.
- [FACT] M4b provides:
  - `ensure_profile` and `create_index`, which run in the caller's transaction (no fence; the
    tenant is passed in, and they require an activated revision with a chunk set);
  - `write_embeddings` (1–32 canonical rows), which runs in the fence and **refuses a ready
    index with `EmbeddingWriteRefusedError`**;
  - `mark_index_ready`, which runs in the fence and provides the **already-ready no-op with a
    fresh ownership re-check**.

  Both fenced functions require kind `index_revision` and exactly `index_id`, lock job →
  index, and re-check ownership on every successful path.
- [FACT] `embed_validated(provider, texts, input_type)` validates the request (1–32 texts,
  ≤128,000 UTF-8 bytes in total, each ≤4,000 code points and ≤16,000 bytes) and the result.
  It converts **any** provider exception into the fixed `InvalidEmbeddingError`.
  `stored_embeddings` converts a validated batch to canonical rows, or rejects the whole batch.
- [FACT] The worker runtime maps:
  - `RetryableJobError(code)` to re-queue, or `dead` once attempts are exhausted (default 3,
    backoff 5–60 s);
  - `PermanentJobError(code)` to `failed`;
  - `JobCancelledError` while a cancel is requested to retryable `worker_shutdown`;
  - any other exception to retryable `unexpected_error`.

  Under lease loss the stale worker records nothing.
- [FACT] `JobContext` checks local cancellation and lease state at explicit boundaries:
  - `check()`;
  - `fenced()` before opening the transaction and again after acquiring the job-row lock;
  - with `finish=True`, once more before recording success.

  These checks are **not** atomic with every SQL statement and do not interrupt a statement or
  call already in flight. The database fence is the authoritative ownership check, and a
  transaction that passed its check just before lease expiry may still commit shortly after it
  (the accepted M3a window).
- [FACT] `production_registry()` registers only `ingest_revision`. Three places assert exactly
  that kind set: `tests/test_worker_cli.py`, the CI wheel step in `.github/workflows/ci.yml`,
  and the image check in `infra/ci/container_ci.py`.
- [FACT] Import boundaries: persistence may not import retrieval, worker or api; the worker may
  import retrieval; the api (including `eg-admin`) may import retrieval but not the worker.
  `eg-admin` prints fixed messages only, exits 2 on usage errors and 1 on failures. The
  `jobs.kind` CHECK accepts `index_revision`, and the M4b schema needs no change.

##### Enqueue

[REC] A new module, `evidenceguard_persistence/indexing.py`, running in the caller's transaction
at READ COMMITTED and never committing:

```text
enqueue_index_revision(session, actor, *, revision_id, identity) -> IndexEnqueueResult
    IndexEnqueueResult(index: IndexSnapshot, job: JobSnapshot | None,
                       outcome: "pending" | "ready" | "stalled")
```

Steps:
1. Validate before any write: `require_storable_identity(identity)`; the tenant comes only from
   `actor.tenant_id`; the actor's role must be reviewer, approver or admin.
2. `ensure_profile` and `create_index`. The revision must be in that tenant and ever activated,
   with a chunk set; otherwise the fixed `IndexSourceNotEligibleError`.
3. If the index is observed `ready`: outcome `ready`, `job` is `None`, and nothing is enqueued.
4. Otherwise call `enqueue(session, actor, kind="index_revision",
   idempotency_key=str(index.id), payload={"index_id": str(index.id)})`. The key is
   deterministic, because the index ID is a UUID5 of tenant, revision, chunker and profile. A
   building index whose canonical job is missing therefore gets that job created.
5. The outcome follows from the returned snapshot:
   - `queued` or `running`: `pending`, whether this call created the job or it already existed;
   - `failed`, `dead`, or the anomalous `succeeded` with a `building` index: `stalled`, with
     the job returned unchanged. **No reset, rescheduling or replacement.**

The seam does not infer creation from a pre-read, timestamps, attempts or system columns, and
M3a's `enqueue` is not changed. The outcome is an **observation within this transaction**, not a
promise about the job's state after commit. Index creation and enqueue commit together or roll
back together. `JobIdempotencyConflictError` propagates, so the caller's transaction rolls back
and nothing is replaced.

Concurrency: the supported isolation is READ COMMITTED. Duplicate concurrent requests serialise
on `uq_embedding_indexes_source` and the jobs idempotency key and observe the same rows. Under
stronger isolation the database may also raise serialization failures. Not every concurrency
failure becomes `JobEnqueueRaceError`; such failures propagate to the caller.

##### Backfill

[REC] In the same module:

```text
backfill_index_revisions(session_factory, actor, *, identity, limit=50, after=None) -> BackfillPage
    BackfillItem(revision_id, index_id: UUID | None,
                 outcome: "pending" | "ready" | "stalled" | "ineligible" | "conflict")
    BackfillPage(items: tuple[BackfillItem, ...], next_after: UUID | None)
```

- **Validation first.** The actor (role and tenant), identity, `limit` (1–100) and `after`
  (a UUID or `None`) are validated before any transaction starts.
- **Selection.** One short read transaction, tenant-scoped, selects revisions with
  `status = 'active'` and a chunk set and **without** a `ready` index for this profile. Rows are
  ordered by revision `id` ascending, with `id > after`, up to `limit`. Revisions already
  superseded when this selection is observed are excluded. Explicit `enqueue_index_revision`
  still accepts any ever-activated revision.
- **Writes.** Each selected revision runs `enqueue_index_revision` in **its own** tenant-scoped
  write transaction. Only the explicitly named expected domain failures become per-item
  outcomes, each after that item's transaction is rolled back:
  - `IndexSourceNotEligibleError` becomes `ineligible`;
  - `JobIdempotencyConflictError`, `EmbeddingProfileConflictError` and `IndexConflictError`
    become `conflict`.

  Such an item may have no committed index, so its `index_id` is `None`. Any other database,
  programming or infrastructure failure **propagates and fails the operation**, rather than
  becoming a successful item.
- **Partial progress.** Items committed before an unexpected failure stay committed. No
  all-page atomicity is claimed.
- **Selection races.** Revisions are active at the selection observation only. A selected
  revision that becomes superseded before its enqueue transaction may still be indexed: it was
  activated and its chunks are immutable. Nothing claims it stays active throughout the run.
- **Cursor.** `next_after` is the last **selected** ID (including per-item failures) when the
  page is full, otherwise `None`. Retrying skipped or conflicted candidates, or picking up newly
  activated revisions whose UUIDs sort below the cursor, can require a fresh pass from the
  beginning.

##### `eg-admin backfill-indexes`

[SETTLED] `eg-admin backfill-indexes --tenant-id UUID [--limit N] [--after UUID]` runs one
bounded page per invocation, using `HASH_IDENTITY` and a fixed system actor with role admin for
the tenant. It follows the existing argparse safety and privacy conventions: usage errors exit 2
with the static message.

It prints only fixed outcome counts (`pending`, `ready`, `stalled`, `ineligible`, `conflict`)
and the next cursor. It never prints raw exception text, text, vectors or keys. Exit codes:
- 0: the page completed without `stalled`, `ineligible` or `conflict` items;
- 3 (accepted in Prompt 124): the page completed with any of them;
- 1: an unexpected operation failure, with a fixed message.

There is no automatic retry loop and no recovery of terminal jobs.

##### Handler and provider selection

[REC] A new module, `evidenceguard_worker/indexing.py`:

```text
INDEX_REVISION_KIND = "index_revision"
SUPPORTED_PROVIDERS = MappingProxyType({HASH_IDENTITY.fingerprint: HashingEmbedder})
make_index_revision_handler(providers=SUPPORTED_PROVIDERS) -> JobHandler
index_revision = make_index_revision_handler()
```

- **Mapping.** The factory copies the supplied mapping into an immutable `MappingProxyType`
  when it is created, including injected test mappings, so later mutation of the caller's
  mapping has no effect.
- **Registration.** `production_registry()` returns both `ingest_revision` and
  `index_revision`. Tests use the factory with provider doubles and a test-owned registry; the
  production defaults never change.
- **Provider resolution.** The stored profile is read, and `EmbeddingIdentity` is
  reconstructed from its five fields. Its fingerprint must equal the stored fingerprint
  **before** the provider is looked up. A missing mapping entry is a permanent failure. The
  provider's `identity` must equal the captured stored identity. No live adapter is imported,
  and nothing is selected from the environment or the network.
- **Payload.** Only `index_id`; no provider IDs, text or credentials.

##### Batching, replay and completeness

Two new read functions in `evidenceguard_persistence/indexing.py`, called inside **short
read-purpose fenced transactions**. These are ordinary `ctx.fenced()` transactions that hold
the job-row lock; there is no `SET TRANSACTION READ ONLY`.
- `load_index_target(session, job)` applies M4b's job binding (kind, payload, tenant) and reads
  the index and profile without an index row lock; the fields read are immutable.
- `pending_chunks(session, job, index, *, after_ordinal)` returns at most 32
  `PendingChunk(ordinal, id, text, content_sha256)` values for chunks of the bound tenant,
  revision and chunker version with `ordinal > after_ordinal` and **no** embedding row in this
  index, ordered by ordinal. The value's `repr` omits `text`.

One attempt, in order:
1. The payload keys must be exactly `{index_id}`, or `PermanentJobError` before any database
   access.
2. Read fence: `load_index_target`.
3. If the index is already `ready`: `with ctx.fenced(finish=True): mark_index_ready(...)`. This
   is the no-op with a fresh ownership re-check, and the job succeeds.
4. Resolve the provider (above).
5. Loop, with `after = -1`:
   - Read fence: `page = pending_chunks(...)`. Stop when the page is empty.
   - After the read fence closes:
     - keep the longest prefix whose UTF-8 total is ≤128,000 bytes (every page is non-empty,
       since one chunk is at most 16,000 bytes);
     - verify `content_sha256(text)` for each chunk, where a mismatch is permanent;
     - `ctx.check()`;
     - compute `embed_validated(provider, texts, "document")` and `stored_embeddings(...)`
       with no transaction, lock or session open;
     - `ctx.check()`.
   - Write fence: `write_embeddings(...)` (short; job → index lock; fresh re-check).
   - `after` becomes the last ordinal of the kept prefix, so the loop is bounded by
     `chunk_count`.
6. `with ctx.fenced(finish=True): mark_index_ready(...)`: M4b's full completeness check, then
   readiness and job success commit together.

**Reuse.** Rows committed earlier are excluded by `pending_chunks`, so they are reused **without**
provider calls and never recomputed or overwritten. This does not verify reused vectors against
new provider output. M4b's constraints bind stored bytes, profile and source membership, not
semantic correctness.

**Conflict.** If another valid attempt commits a row for a selected chunk between this
attempt's read and its write, `write_embeddings` compares the replay. An identical row is
accepted. A differing row raises `EmbeddingConflictError`; nothing is overwritten, and the
failure is mapped below.

**No exactly-once claim.** A page computed but not committed (crash, lease loss, cancellation,
a failed commit) is computed again on retry. The offline provider is deterministic.

##### Cancellation, lease loss and failures

Actual guarantees, all at explicit boundaries:
- `ctx.check()` immediately before and after provider computation;
- `ctx.fenced()` checks before opening its transaction and after acquiring the job lock;
- `finish=True` checks once more before recording success;
- database ownership checks (M3a's fence and M4b's re-checks) remain authoritative.

Limits:
- A cancellation latched after the last applicable check may not stop an already-started
  non-finish transaction from committing.
- Checks do not interrupt synchronous provider or database calls.
- The accepted lease-expiry/commit window and the existing shutdown limits remain.
- Cancellation while ownership remains valid makes the runtime record retryable
  `worker_shutdown`, which **is** a lifecycle outcome. Lease loss means the stale worker
  records no outcome.

**Provider-exception path.** When provider execution or validation raises (always the fixed
`InvalidEmbeddingError` from `embed_validated` or `stored_embeddings`), the handler calls
`ctx.check()` **before** classifying the failure. A cancellation or lease loss latched during
the call takes precedence, as `JobCancelledError` or `LeaseLostError`. Control-flow exceptions
are never converted. The same explicit-boundary race applies: a latch occurring after that
check is not atomic with classification.

Failure mapping, using existing codes only [SETTLED]:

| Condition | Outcome |
|---|---|
| Payload keys, `IndexJobMismatchError`, `IndexNotFoundError` | `PermanentJobError(permanent_failure)` |
| Stored-identity fingerprint mismatch, unsupported fingerprint, provider identity mismatch, `EmbeddingProfileMismatchError` | `permanent_failure` |
| Text-hash mismatch, `EmbeddingSourceMismatchError`, `IndexIncompleteError` | `permanent_failure` |
| `InvalidEmbeddingError` from provider output or the post-rounding check (after `ctx.check()`) | `permanent_failure`; the offline provider is deterministic, and M4f must separate transient failures |
| `EmbeddingConflictError`, `EmbeddingStorageRejectedError` | `permanent_failure`; the index stays `building` and nothing is overwritten |
| `EmbeddingWriteRefusedError` (another attempt made the index ready) | Step 3's no-op finish |
| `JobLockTimeoutError` | `RetryableJobError(retryable_failure)` |
| `LeaseLostError`, `JobCancelledError`, `FenceClosedError` | Propagate untouched (existing runtime handling) |
| Any other exception | Propagates; the runtime records retryable `unexpected_error` |

When retries are exhausted the job ends `dead`, and enqueue and backfill report the index as
`stalled`. A failed index keeps its committed rows and stays `building` (ineligible). Nothing
logs text, vectors, keys or exception details; errors keep fixed messages.

##### Implementation, migration and CI changes

[REC] Files:
- New `evidenceguard_persistence/indexing.py` and `evidenceguard_worker/indexing.py`.
- `evidenceguard_worker/handlers.py`: registration.
- `evidenceguard_api/admin.py`: the `backfill-indexes` command.
- No migration and no configuration change: the M4b schema and the jobs table already support
  M4c.
- **Necessary updates** to the three registry-kind assertions (`tests/test_worker_cli.py`,
  `ci.yml`, `infra/ci/container_ci.py`).
- ADR-0015 is an implementation deliverable.

**Required CI acceptance checks** [SETTLED; planned, not execution evidence]:
- **Wheel step** (`ci.yml`), Ubuntu and Windows:
  - runs outside the checkout with isolated Python (`-I`);
  - verifies imports resolve to site-packages;
  - runs `HashingEmbedder` through `embed_validated` and `stored_embeddings` directly;
  - imports the indexing modules and asserts both production registry kinds.

  It makes **no** claim of database indexing.
- **Container smoke** (`infra/ci/container_ci.py`), after the existing ingestion:
  - run the production `eg-admin backfill-indexes` for the synthetic tenant and let the
    registered worker process the job, with bounded timeouts;
  - verify with read-only queries that the index has the **same tenant and ingested revision**
    and the expected offline profile fingerprint, `status = 'ready'`, its canonical
    `index_revision` job `succeeded`, and an embedding row count equal to `chunk_count`;
  - keep the existing image-identity, privacy, idle-shutdown and cleanup checks.

  A readiness row count alone is not described as proving indexing for that
  tenant/revision/profile.

**Planned tests** (none written or run):
- **Database-independent:**
  - registry kinds;
  - an immutable, defensively copied provider mapping;
  - stored-identity fingerprint verification before resolution; unsupported fingerprints and
    identity mismatches fail permanently with no other adapter imported;
  - page caps at exactly 32 items and at the 128,000-byte boundary with multi-byte text;
    ordering; hash mismatch; `PendingChunk` representations without text;
  - the scripted-context handler:
    - cancellation or lease loss before provider work;
    - a successful provider return after a latch;
    - a provider or validation failure after a latch (the latch wins);
    - the before-write and before-finish boundaries;
    - each failure-table row;
    - the already-ready and write-refused paths;
  - enqueue outcomes `pending`, `ready` and `stalled`;
  - backfill validation before writes, per-item `ineligible`/`conflict` with rollback,
    unexpected failures propagating, a nullable `index_id`, and cursor advance over failures;
  - CLI counts, exit codes 0, 3, 1 and 2, and output without content.
- **PostgreSQL** (real `enqueue`/`claim`/fence, deterministic barriers or hooks, observed lock
  waits, bounded waits):
  - enqueue: atomicity (a rollback leaves neither index nor job), idempotency, and two
    concurrent enqueues observing one index and one job;
  - refusal of never-activated and foreign revisions; an explicit superseded revision is
    allowed;
  - `stalled` for a dead job, which stays unchanged;
  - backfill: bounds, cursor, ordering, exclusion of revisions superseded at selection, and
    partial progress surviving an injected unexpected failure;
  - the full worker run gives a ready index with job success, and the stored bytes equal the
    direct offline computation;
  - a previously committed row is reused without recomputation (a counting provider double)
    and stays unchanged;
  - a **competing writer**, using a separate valid job and fence, commits a different valid
    vector after this attempt selected the chunk but before its write. The conflict is
    detected, nothing is overwritten, and this attempt records `permanent_failure` while its
    ownership is valid;
  - lease expiry and cancellation while the provider double blocks give no write by the stale
    owner, and the actual runtime outcome is asserted (`worker_shutdown` for cancellation,
    none for lease loss);
  - failure at the finish leaves neither readiness nor success;
  - a 450-chunk revision exercises pagination.

##### Review outcome

[DECISION] Prompt 124 accepted CLI exit code 3 and the complete corrected specification. No
specification decision remains open; implementation and its verification are pending.

#### M4d snapshot and retrieval specification (ACCEPTED at review, Prompt 133; implementation pending)

**Status.** [DECISION] **The complete specification was proposed in Prompt 131, corrected in
Prompt 132 and accepted at external review in Prompt 133 with two final clarifications (the
database failure boundary's explicit pending outcome and the digest-uniqueness rule).** Decisions
R1–R9 were settled in Prompt 132. Claude Code wrote it from the accepted Prompt 108 decisions and
source on `main` at `76fa5a3`. Acceptance is a design decision, not implementation or execution
evidence: no code, test scaffolding, migration or ADR-0016 exists, ADR-0016 is deferred to
implementation, and the implementation and every M4d verification check below were pending at
acceptance (see the implementation status below for what has since been done).
No specification decision remains open. Labels: **[DECISION]** accepted in Prompt 108;
**[SETTLED]** settled at review in Prompt 132 (see
[M4d review decisions](#m4d-review-decisions-settled-in-prompt-132)); **[FACT]** established from
source at `76fa5a3`; **[REC]** written as a proposal in Prompts 131–132 and, with acceptance of
the complete specification in Prompt 133, now part of the **accepted implementation contract**.

**Implementation status (Prompts 134–140).** Claude Code implemented this specification on
`feat/snapshot-retrieval` in Prompt 134 and corrected it in Prompt 135
([ADR-0016](decisions/0016-snapshot-retrieval.md), which records the material implementation
choices, the corrections and the lower-level chunk-bound fixture approved at review in Prompt 135
solely for capture's metadata-based chunk-count arithmetic). The complete corrected
implementation was **accepted at external review in Prompt 136** for a local commit; the reviewer
inspected both exports and probed the corrected process-control functions in isolation (24
combinations passed) but ran no project suite, build, installed-wheel check, PostgreSQL or Docker.
Claude Code published the feature branch in Prompt 137, and the implementation is **reviewed and
verified in feature-branch CI at `3d6e8395`**: from job logs independently retrieved by the
external reviewer (Prompt 138), Ubuntu `2002 passed, 290 skipped`, Windows `2001 passed, 291
skipped`, PostgreSQL `290 passed, 2002 deselected` with all 39 cases in
`tests/test_retrieval_postgres.py` passing, both installed-wheel jobs running the R9 retrieval
check, the unchanged container job and Gitleaks (59 commits, no leaks); see the
[ADR-0016 feature-branch CI evidence](decisions/0016-snapshot-retrieval.md#feature-branch-ci-evidence-at-3d6e8395).
That feature-branch evidence is now historical: in Prompt 139 Claude Code fast-forwarded `main` to
`cf2b5743` (verification documentation and prompt history only beyond `3d6e8395`) after green
exact-commit feature CI, and the implementation is **reviewed, verified in CI and on `main` at
`cf2b5743`**: from main-push job logs independently retrieved by the external reviewer (Prompt
140), Ubuntu `2002 passed, 290 skipped`, Windows `2001 passed, 291 skipped`, PostgreSQL `290
passed, 2002 deselected` with all 39 M4d cases passing, both installed-wheel retrieval checks, the
container job and Gitleaks (60 commits, no leaks); see the
[ADR-0016 main CI evidence](decisions/0016-snapshot-retrieval.md#main-ci-evidence-at-cf2b5743).
Claude Code's Prompt 134–135 local Windows checks are historical, as is the earlier statement that
the PostgreSQL tests had never run. The container smoke covers ingestion and indexing, not M4d
retrieval. The M4e specification is accepted (Prompt 143) and its implementation (Prompt 144, corrected in Prompts 145–146) is accepted at external review (Prompt 147) for a local commit and published in Prompt 148 at `c14821b7`, where exact-commit CI was not fully green (PostgreSQL passed with all 16 M4e cases; one Ubuntu test failed from a test-double recursion); the Prompt 149 test-only correction was accepted in Prompt 150 and published in Prompt 151; after feature-branch verification at `d1dcdfce` (historical), M4e is reviewed, verified in CI and on `main` at `0ae4c6ca`; M4f and overall M4 acceptance were then pending (both since accepted: M4f on `main` at `5acb75e5`, overall M4 in Prompt 165). The heading and the planned-verification list below keep their accepted
wording.

**Scope.** A trusted snapshot capture seam, an immutable snapshot value, strict retrieval
inputs, the lexical and exact-vector channels, deterministic RRF fusion and bounded result
values with chunk evidence and provenance, fixed provider and database failure boundaries, and
their tests. Out of scope: review persistence and any review or retrieval API endpoint (M5), report
generation, the evaluation corpus and Recall (M4e), the Voyage adapter and any live provider call
(M4f), activation wiring, recovery generations for stalled indexes, any snapshot table or HMAC,
and any approximate index (E5).

##### Accepted policy preserved (Prompt 108)

[DECISION] These are settled and are not reopened here (see
[the Prompt 108 decisions](#m4-direction-and-review-decisions)):

1. Snapshot capture is trusted and tenant/vendor scoped.
2. Capture selects the vendor's active revision pointers, complete immutable chunk sets and
   ready indexes for the pinned profile in one consistent read transaction.
3. If any active revision lacks a complete chunk set or a ready index for the profile, capture is
   refused; the revision is never silently omitted.
4. Pending/processing revisions are recorded as exclusions (precise semantics below).
5. An empty eligible set is an explicit error.
6. A manually supplied revision-ID list alone proves neither authorization nor past eligibility.
7. A revision active at capture remains eligible for that snapshot after later supersession;
   retrieval never re-filters by today's `active` status.
8. A revision already superseded at capture is excluded from a new snapshot.
9. A new revision never enters an older snapshot.
10. Current-state search first captures a fresh snapshot.
11. Never-activated, failed, incomplete, foreign-tenant or foreign-vendor, wrong-profile and
    non-snapshot chunks remain excluded.
12. Bounds (initial engineering defaults, not measurements): 1–8 distinct nonblank queries, each
    at most 4,000 code points and 16,000 UTF-8 bytes; 1–100 revisions; at most 100,000 eligible
    chunks, rejecting excess rather than truncating; per-channel limit 20; requested k 1–20,
    default 8.
13. Explicit PostgreSQL `simple` configuration for documents and queries; filters before each
    channel's limit; zero lexical scores and zero query vectors ignored; one-based ranks with ties
    by canonical chunk UUID ascending; RRF contribution `1 / (60 + rank)` summed across lists;
    final ties by chunk UUID ascending; each chunk returned once with channel ranks, scores,
    pinned profile and provenance; all-zero hash queries yield no vector candidates; no
    candidates yields an empty result.
14. Determinism is claimed for a fixed stored corpus, configuration and database/provider outputs
    only, not for live embeddings across calls or platforms.

M5 persists the snapshot's authorization and configuration facts atomically with review
creation. M4d designs no review API.

##### Facts from current source (`76fa5a3`)

- [FACT] **Import boundaries** (`tests/test_packaging.py`): `evidenceguard_retrieval` may import
  only `evidenceguard_domain` and the standard library, and never `sqlalchemy`, `psycopg`,
  `httpx`, `socket`, `urllib`, `requests` or `os`. Persistence may not import retrieval, worker
  or api. The worker may import domain, persistence and retrieval but not api; the api may not
  import the worker.
- [FACT] **Provider boundary.** The `EmbeddingProvider` protocol, `embed_validated` and
  `HASH_IDENTITY` live in `evidenceguard_retrieval.embeddings`. `embed_validated(provider,
  texts, input_type)` first calls `validate_request` (1–32 texts; each 1–4,000 code points, no
  NUL, not whitespace-only, strict UTF-8, at most 16,000 bytes; at most 128,000 bytes in total),
  which raises the fixed `InvalidEmbeddingError` directly. Then, inside one `try`, it reads and
  validates `provider.identity` **itself**, calls `provider.embed` and runs `validate_result`
  against that identity, the input type and the count. Any `Exception` there sets a flag, and the
  fixed `InvalidEmbeddingError` is raised after the `except` block, so no provider exception is
  retained as cause or context. It does not see any identity a caller read earlier.
  `EmbeddingBatch`, `EmbeddingIdentity`, `validate_identity` and `validate_result` are pure
  domain values and functions in `evidenceguard_domain.embeddings`.
- [FACT] **Canonical storage** (`evidenceguard_domain.embedding_storage`):
  `canonical_vector(vector, *, allows_zero: bool)` rounds each coordinate to float32 (with
  `-0.0` → `0.0`), requires the rounded vector to be zero exactly when the source is zero, and
  revalidates it as a `StoredVector` (finite; zero only when `allows_zero`; otherwise an L2 norm
  within the absolute `NORM_TOLERANCE` of `1e-6`), with no renormalization. Failures raise
  `InvalidEmbeddingError`. `StoredVector.literal()` gives the exact pgvector text literal.
  `allows_zero_vectors(identity)` is true only for provider `offline`. `profile_id(tenant,
  fingerprint)` and `index_id(tenant, revision, chunker_version, profile)` are deterministic
  UUID5 values. `EmbeddingIdentity.fingerprint` is the SHA-256 of sorted-key, compact,
  ASCII-only JSON with `allow_nan=False`.
- [FACT] **Schema.** `documents(tenant_id, vendor_id, active_revision_id)` with a composite
  pointer FK to the same tenant and document; `document_revisions.status` in `pending`,
  `processing`, `failed`, `active`, `superseded`, with one `active` row per document (partial
  unique index). CHECKs make `activated_at` non-null for `active` and null for `pending`,
  `processing` and `failed`; it is never cleared. `chunk_sets` has one row per revision in v1,
  binding `(chunker_version, chunk_count, manifest_sha256)` with `chunk_count` between 1 and
  4,096. `chunks` are immutable by application invariant, with `search_vector =
  to_tsvector('simple'::regconfig, text)` stored and generated and a GIN index.
  `embedding_profiles` are immutable per `(tenant_id, fingerprint)`. `embedding_indexes` bind
  tenant, revision, chunk-set binding, profile, dims and zero policy, and are `building` or
  `ready` (immutable once ready, with `vector_manifest_sha256`). `chunk_embeddings` hold
  `vector(1024)`, `vector_sha256` and `is_zero`, linked by composite FKs to their index and to the
  exact chunk and content digest. No HNSW or IVFFlat index exists; migration `0005` is the head.
- [FACT] **Chunk spans.** `Chunk.char_start/char_end` and `line_start/line_end` are the body
  span. A table continuation chunk with a repeated header has `header_*` spans that end before
  the body, and its `text` is the header slice immediately followed by the body slice
  (`len(text) == header length + body length`), with no separator. At most 4,096 chunks per
  revision, so 100 revisions can exceed 100,000 chunks.
- [FACT] **Activation** (`activate_revision`) demotes the old active revision, promotes the target
  and moves the pointer in one transaction. `create_index` requires `activated_at IS NOT NULL`,
  and activation enqueues no indexing, so a newly activated revision has no ready index until an
  explicit enqueue or backfill completes.
- [FACT] **Read pattern.** `document_views.read_snapshot(session_factory)` creates a session,
  executes `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY`, then
  `SELECT clock_timestamp()` once, yields `(session, time)`, and in `finally` rolls back and
  closes (a rollback failure still closes, and propagates). `readiness.py` uses
  `SET LOCAL statement_timeout`. The production engine sets `hide_parameters=True`.
- [FACT] **Roles.** Document content reads in the API allow reviewer and approver only
  (`DOCUMENT_ROLES`); admin is excluded. M4c's indexing seams allow reviewer, approver and admin.
- [FACT] **Domain values.** `DomainModel` (pydantic) strips surrounding whitespace from strings;
  the embedding and chunk contracts instead use frozen dataclasses with constructor validation,
  fixed errors and content-free `repr`.
- [FACT] **PostgreSQL integration tests** use the guarded disposable-database fixtures in
  `tests/conftest.py`, the integration marker and `EG_REQUIRE_INTEGRATION=1` in CI, a server-side
  `statement_timeout` per connection and deterministic `threading.Event` handshakes rather than
  timing sleeps (`tests/test_indexing_postgres.py`).

##### Package placement and public seams

[SETTLED] R1 and R2. Every existing import direction is kept:

| File (new) | Contents | May import |
|---|---|---|
| `packages/domain/evidenceguard_domain/retrieval.py` | Frozen values, canonical encodings, strict validation, the pure query-vector conversion, the pure `fuse` function and the fixed errors | domain and standard library |
| `packages/persistence/evidenceguard_persistence/retrieval.py` | `capture_snapshot`, `retrieve_with_vectors`, statement builders, row conversion and the database failure boundary | domain, persistence, SQLAlchemy |
| `apps/worker/evidenceguard_worker/retrieval.py` | Provider orchestration: `search_snapshot` and `search_current`, and the provider failure boundary | domain, persistence, retrieval |

`evidenceguard_retrieval` is unchanged. Fusion sits in the domain so persistence can run channel
queries, fusion and evidence loading in one read transaction without importing the retrieval
package (R1). The orchestrator sits in the worker, the M5 consumer, because it alone may import
both the provider boundary and persistence (R2).

[REC] Public seams:

```text
capture_snapshot(session_factory, actor, *, vendor_id: UUID,
                 identity: EmbeddingIdentity,
                 config: RetrievalConfig = RETRIEVAL_CONFIG_V1) -> RetrievalSnapshot
retrieve_with_vectors(session_factory, actor, snapshot: RetrievalSnapshot,
                      request: RetrievalRequest, query_batch: EmbeddingBatch) -> RetrievalResult
search_snapshot(session_factory, actor, snapshot, request, provider: EmbeddingProvider)
    -> RetrievalResult
search_current(session_factory, actor, *, vendor_id, request, provider)
    -> tuple[RetrievalSnapshot, RetrievalResult]
```

All four are **trusted internal programming interfaces**. None is an endpoint, and none
deserializes a snapshot from untrusted input. `search_current` implements decision 10: capture
(its own transaction), then the provider call, then retrieval (a second transaction).

##### Values and invariants

[REC] All values are frozen dataclasses with `init=False` constructors that validate exact types
(`type(x) is …`: no coercion, `bool` is not accepted as `int`, tuples only, no `str` where a
`UUID` is expected), reject unknown keyword arguments, never strip or normalize text, and raise
fixed errors after any `except` block. `dataclasses.replace` revalidates through the constructor.
Derived digests are computed by the constructor, never accepted as arguments. `repr` and `str`
show IDs and counts only, never query text, chunk text, section paths or
vectors. A violation raises `InvalidRetrievalRequestError` for caller inputs and
`InvalidSnapshotError` for snapshot values; inside persistence, a value that fails while being
built from database rows raises `SnapshotInconsistentError`.

- **`RetrievalConfig`.** Exactly one accepted value, `RETRIEVAL_CONFIG_V1` (fields in the
  canonical encoding below). `config_sha256` is derived from its canonical bytes and pinned in
  tests.
- **`RetrievalRequest(queries, k=8)`.** `queries` is a tuple of 1–8 `str`, each 1–4,000 code
  points, without NUL, not whitespace-only (`str.isspace()`), strictly UTF-8 encodable (lone
  surrogates rejected) and at most 16,000 bytes. Queries are kept verbatim; distinctness is exact
  code-point equality, and a duplicate is rejected, not merged. The total is therefore at most
  128,000 bytes, so all queries go to the provider in **one** `embed_validated` call. `k` is an
  `int` (not `bool`) in 1–20.
- **`PendingExclusions(count, revision_ids, truncated)`.** `count` is an `int` ≥ 0;
  `revision_ids` is a tuple of distinct `UUID`s in strictly ascending order with
  `len(revision_ids) == min(count, 100)`; `truncated` is a `bool` equal to `count > 100`
  ([SETTLED] R5).
- **`RevisionBinding`.** `revision_id`, `document_id` and `index_id` (`UUID`); `chunker_version`
  (`validate_chunker_version`); `chunk_count` (`int`, 1–4,096); `manifest_sha256` and
  `vector_manifest_sha256` (64 lowercase hex characters).
- **`RetrievalSnapshot`.** `tenant_id`, `vendor_id`, the pinned `EmbeddingIdentity`
  (`require_storable_identity`: 1024 dims, `l2`), `config`, `bindings`, `exclusions` and
  `captured_at`. The constructor derives `profile_id`, `total_chunks` and `sha256`. Invariants:
  1–100 bindings in strictly ascending `revision_id` order (so no duplicate revision); distinct
  `document_id`s (one binding per document, since a document has at most one active revision);
  each `index_id == index_id(tenant, revision, chunker_version, profile_id)`; `total_chunks` (the
  sum of `chunk_count`) at most 100,000; `captured_at` a timezone-aware `datetime`.
- **`ChannelList(query_position, channel, entries)`.** `query_position` is an `int` in
  `0 … query_count − 1`; `channel` is `"lexical"` or `"vector"`; `entries` holds 0–20
  `(chunk_id, score)` pairs with distinct chunk IDs and finite `float` scores. Lexical scores are
  positive and non-increasing; vector scores (cosine distances) are non-decreasing; equal scores
  are in ascending chunk-ID order. No range narrower than finiteness is required for distances:
  for unit vectors the cosine distance is mathematically in [0, 2], but floating rounding may
  fall slightly outside it, and that assumption is documented rather than enforced. A list's rank
  for an entry is its one-based position.
- **`ChannelHit(query_position, channel, rank, score)`.** Bounds as above, with `rank` in 1–20.
- **`RetrievedChunk`.** `chunk_id`, `revision_id`, `document_id`, `fused_rank`, `fused_score`
  (a `Fraction`, with a `float` display property), `hits` and `evidence`. `hits` is non-empty,
  in ascending (query position, channel) order with lexical before vector, at most one per
  (query position, channel), and `fused_score` equals the exact sum of `1/(60 + rank)` over
  `hits`. `revision_id` and `document_id` must belong to one snapshot binding.
- **`ChunkEvidence`.** `chunk_id` equal to its item; exact `text` whose SHA-256 equals
  `content_sha256`; `ordinal`; `section_path`; `is_table`; a body `SourceSpan(line_start,
  line_end, char_start, char_end)` and an optional header `SourceSpan`, satisfying the existing
  `Chunk` span rules; `header_text` and `body_text` split at the header length; and provenance
  (`document_key`, `title`, `revision_no`, `version_label`, `effective_date`, `source_type`,
  `authenticity`).
- **`RetrievalResult`.** `tenant_id` and `vendor_id` equal to the snapshot's; `snapshot_sha256`;
  `profile_fingerprint` and its label (the lexical-hash label for the offline profile);
  `config_sha256`; `query_count` 1–8; `k` 1–20; `vector_skipped` (ascending query positions whose
  canonical query vector was zero); and `items` with at most `k` entries, distinct chunk IDs,
  `fused_rank` exactly `1 … len(items)`, in descending `fused_score` with ties by ascending chunk
  ID, every hit's query position below `query_count`, and no vector hit for a position in
  `vector_skipped`.

##### Canonical encodings and digests

[REC] Canonical encoding `eg-retrieval-canonical-v1`, used for `config_sha256` and
`snapshot.sha256`:

- **Bytes:** `json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
  allow_nan=False).encode("ascii")`, the same rules as `EmbeddingIdentity.fingerprint`. The output
  is ASCII and therefore valid UTF-8. The digest is the lowercase hex SHA-256 of those bytes.
- **Scalars:** UUIDs as `str(uuid)` (lowercase, hyphenated); SHA-256 digests as 64 lowercase hex
  characters; integers as JSON integers (never `bool`, never floats); booleans as `true`/`false`;
  `captured_at` converted to UTC and written as `YYYY-MM-DDTHH:MM:SS.ffffffZ`, always with six
  fractional digits (PostgreSQL `timestamptz` has microsecond precision). Snapshots contain no
  floats.
- **Forbidden:** Python `repr`, `hash()`, locale-dependent formatting and `default=str`; any
  value not listed below is rejected rather than stringified.
- **Order:** bindings in ascending `revision_id`; exclusion IDs in ascending order; object keys
  sorted by the encoder.
- **Self-exclusion:** neither digest is part of its own input.

Config object:

```json
{"canonical":"eg-retrieval-canonical-v1","kind":"retrieval_config","version":"hybrid-rrf-v1",
 "text_search_config":"simple","lexical_query":"websearch_to_tsquery",
 "lexical_score":"ts_rank_cd","lexical_normalization":0,"vector_operator":"cosine_distance",
 "channel_limit":20,"rrf_constant":60,"default_k":8,"max_k":20}
```

Snapshot object:

```json
{"canonical":"eg-retrieval-canonical-v1","kind":"retrieval_snapshot",
 "tenant_id":"…","vendor_id":"…","captured_at":"…Z","config_sha256":"…",
 "profile":{"provider_id":"…","model_id":"…","algorithm_version":"…","dims":1024,
            "normalization":"l2","fingerprint":"…","profile_id":"…"},
 "bindings":[{"revision_id":"…","document_id":"…","chunker_version":"…","chunk_count":1,
              "manifest_sha256":"…","index_id":"…","vector_manifest_sha256":"…"}],
 "total_chunks":1,
 "exclusions":{"count":0,"revision_ids":[],"truncated":false}}
```

`captured_at` is informational provenance and is included in the canonical snapshot encoding.
Captures whose encoded timestamps differ can therefore have different canonical bytes even when
their other facts match, while captures with identical encoded fields produce the same digest.
Timestamps have finite (microsecond) precision and are not unique identifiers. Neither the
timestamp nor the digest proves authorization, past eligibility or uniqueness; a digest is
recomputable by anyone. A persisted digest (M5) is verified only by recomputing it from the
reloaded, revalidated fields and comparing the 64-character strings exactly. M4d adds no random
ID, HMAC, secret or persistence.

##### Trust model

[SETTLED] R3, recorded explicitly:

- The snapshot seams are a **trusted internal programming interface**. `capture_snapshot` is the
  only producer of snapshots in M4d; it establishes eligibility from the database for a trusted
  `ActorContext` (built from an authenticated API key at the API boundary, or by trusted worker
  code). No public request may supply revision IDs, and no seam treats a caller's ID list as proof.
- **No endpoint and no untrusted snapshot deserialization** is authorized.
- A frozen value, a UUID list and a **recomputable digest are not authorization mechanisms**.
- Before every retrieval, the database **binding recheck** below confirms tenant and vendor
  ownership and the immutable bindings. It **does not prove past active-at-capture eligibility**,
  and it cannot detect an omitted active revision.
- **M5 must persist the captured facts** atomically with review creation **and reload them only
  through trusted paths**.
- Approval of this interim model **does not establish protection against malicious in-process
  code**: such code could construct a structurally valid snapshot from same-vendor revisions that
  were superseded before capture, violating decisions 6 and 8 without reaching other tenants,
  vendors, or unsettled, failed or unindexed data.

`activated_at`/`superseded_at` timestamps are not used as proof: commit order and
`clock_timestamp()` can disagree near the capture instant, so a timestamp check could both accept
a revision the capture never saw and reject one it legitimately captured. `captured_at` is
informational and proves neither the snapshot's visibility nor past eligibility.

*Binding recheck* (one statement in the retrieval transaction, before any channel query). For
every binding, all of the following must hold, and the number of verified bindings must equal
`len(bindings)`:

- the vendor exists in the actor's tenant (the actor's tenant already equals the snapshot's);
- the revision is in that tenant and belongs to the binding's `document_id`, and that document
  belongs to the snapshot's vendor;
- `activated_at IS NOT NULL` (so the revision is settled; never-activated and failed revisions
  fail);
- the chunk set equals the binding's `(chunker_version, chunk_count, manifest_sha256)`;
- the index is the binding's `index_id`, in the tenant, `ready`, for that revision, chunk-set
  binding and `profile_id`, with the binding's `vector_manifest_sha256`;
- the profile row's identity fields and fingerprint equal the snapshot identity.

No current `status` is consulted, which preserves snapshot-relative supersession (decision 7). Any
failure, including a missing or foreign row, raises `SnapshotInconsistentError`.

*Source-corruption assumptions.* The design assumes the database is changed only through the
application's paths and migrations. Constraints and immutability by application convention (no
update or delete statements for chunks, profiles, ready indexes and embeddings) are not a defence
against arbitrary direct database modification. The evidence text-digest check detects one class
of tampering only; no hash or convention in M4d is claimed to protect against a database writer
outside the application.

##### Transactions, settings and locking

[REC] Capture and retrieval each use one short transaction through the existing
`read_snapshot` helper, **unchanged**. The actual order is:

1. the helper executes `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY`, the
   transaction's first statement;
2. the helper executes its single `SELECT clock_timestamp()`. This is the transaction's first
   snapshot-taking statement, so **the REPEATABLE READ snapshot is established here**, not at a
   later data query; capture records the returned time as `captured_at`;
3. after the helper yields, the seam executes `SET LOCAL statement_timeout = 30000`
   ([SETTLED] R7); `SET` does not change the established snapshot;
4. the capture or retrieval data statements, all reading that one snapshot.

Both settings are transaction-local: PostgreSQL discards them when the helper rolls back, so a
pooled connection returns with its defaults (READ COMMITTED, read-write, its previous
`statement_timeout`). No session-level `SET`, `default_transaction_*` or connection
`execution_options` isolation is used.

*Timeout scope.* 30,000 ms applies to **each statement** separately. It is not a deadline for the
whole capture or retrieval (capture runs fewer than ten statements; retrieval up to 18 data statements: the binding
recheck, at most 16 channel statements and the evidence statement), and it does not apply to the
provider call, which runs outside any transaction. No overall execution bound is promised, and
nothing retries.

*Locking.* `READ ONLY` makes any accidental write fail, and the seams issue no `INSERT`, `UPDATE`,
`DELETE`, enqueue or `FOR UPDATE`/`FOR SHARE`, and never trigger indexing. They take **no explicit
row locks**, so they have no row-lock conflict with ordinary activation or indexing DML. Ordinary
`SELECT`s still take `ACCESS SHARE` relation locks, so they can wait for, or delay, DDL that needs
stronger locks (for example a migration). The transactions attempt no row updates, so they cannot
hit REPEATABLE READ's concurrent-update serialization failure.

##### Capture (`capture_snapshot`)

[REC] Sequence:

1. **Validate before any database work:** `actor` is an `ActorContext` (else `TypeError`, as in
   M4c); the role is reviewer or approver ([SETTLED] R4; else `PermissionDeniedError`);
   `vendor_id` is a `UUID` (a string is rejected, not parsed); `require_storable_identity(identity)`
   (its `InvalidEmbeddingError` becomes `InvalidRetrievalRequestError`); `config` is
   `RETRIEVAL_CONFIG_V1`. Invalid input raises `InvalidRetrievalRequestError`.
2. **One read transaction**, in the order above, then these phases. Each phase examines the
   **whole** selected set before the next phase starts, so the error raised never depends on row
   order:
   1. *Scope:* the vendor in the actor's tenant. Missing or foreign → `RetrievalScopeError`.
   2. *Selection:* the vendor's pointers (`documents.active_revision_id`, tenant- and
      vendor-scoped) joined to the revision, its chunk set, the tenant's profile for the
      fingerprint and that profile's index for the revision (left joins), ordered by revision ID
      with **`LIMIT 101`**.
   3. *Emptiness:* no rows → `EmptySnapshotError`.
   4. *Revision bound:* 101 rows → `SnapshotBoundsError`. The limit only detects excess; a
      truncated set is never used.
   5. *Consistency:* any selected revision whose `status` is not `active`, or whose document does
      not match → `SnapshotInconsistentError`.
   6. *Readiness:* any selected revision without a chunk set, without the profile, or without a
      `ready` index whose binding equals its chunk set → `SnapshotNotReadyError`, a fixed error
      without revision IDs ([SETTLED] R6).
   7. *Chunk bound:* the sum of the selected `chunk_count` values above 100,000 →
      `SnapshotBoundsError`.
   8. *Exclusions:* `count(*)` of the vendor's revisions in `pending` or `processing`, and their
      IDs `ORDER BY id LIMIT 100`, form `PendingExclusions` ([SETTLED] R5).
3. Build the snapshot inside the transaction (constructor failures become
   `SnapshotInconsistentError`), leave the helper (rollback and close) and return.

Error precedence is therefore: input, role, scope, emptiness, revision bound, consistency,
readiness, chunk bound. A missing vendor and a foreign vendor are deliberately indistinguishable.

*Exclusion semantics.* Pending and processing revisions are excluded and recorded; they never
block capture and never enter this snapshot, even if they activate later. They include unsettled
uploads for documents that also have an active revision. Failed and superseded revisions are
excluded without a record, and a document without an active pointer contributes nothing. The
record is provenance for M5 (`ReviewAccepted.excluded_pending`), not an eligibility input.

*Races.* The snapshot is fixed by the helper's `clock_timestamp()` `SELECT`. Activation's
demote → promote → pointer commits atomically, so capture sees each document entirely before or
entirely after a concurrent activation:

- an activation committed **before the helper's first `SELECT`** is visible: the new revision is
  active with no ready index yet (indexing is explicit and asynchronous), so capture is refused
  until indexing completes;
- an activation committed **after that `SELECT`**, even before capture's first data query, is
  invisible: the old revision is captured and stays eligible after its supersession;
- index readiness, uploads and failures follow the same rule.

##### Retrieval

[REC] **Shared pure conversion** (domain): `query_vectors(batch, *, identity, query_count)`
requires `type(batch) is EmbeddingBatch` and calls `validate_result(batch, identity=identity,
input_type="query", count=query_count)`, which reconstructs the batch (dimensions, finiteness,
norm and offline-only zero rules) and requires its identity to equal the snapshot identity. It
then converts each vector with `canonical_vector(vector, allows_zero=allows_zero_vectors(identity))`,
reusing the existing `NORM_TOLERANCE` and zero policy with no renormalization or widening. A zero
canonical vector marks its query position as vector-skipped. Any failure raises
`InvalidEmbeddingError`, which callers map to `RetrievalProviderError`. Conversion is pure and
runs **outside** any database transaction.

**`search_snapshot`** (worker; receives a real provider):

1. Pure validation: request, snapshot structure, actor type and role, and actor tenant equal to
   snapshot tenant (`RetrievalScopeError`). No provider access or SQL yet.
2. **Provider identity before the call**, inside its own `try`: read `provider.identity`, run
   `validate_identity` and compare it with the snapshot identity. An ordinary `Exception` from
   the property getter or validation sets a flag; after the `except` block, the fixed
   `RetrievalProviderError` is raised, retaining no cause or context. A mismatch raises the same
   error. No embedding call is made in either case. `embed_validated` does **not** protect this
   first read: it reads the property again itself.
3. **Embedding**, with no session open: one `embed_validated(provider, request.queries, "query")`
   call. Its fixed `InvalidEmbeddingError` (or any other ordinary `Exception`) sets a flag, and
   `RetrievalProviderError` is raised after the `except` block.
4. **Conversion**: `query_vectors(...)` against the **snapshot** identity, in its own `try` with
   the same outside-`except` mapping. This also rejects a provider whose identity changed between
   the first read (step 2) and the read inside `embed_validated`, because the returned batch's
   identity must still equal the snapshot identity.
5. `retrieve_with_vectors` with the validated batch.

Scope of this boundary: only ordinary `Exception`s are caught, never `BaseException`. M4d adds no
`JobContext` integration or worker cancellation protocol and changes no M4a or M4c control flow.
`embed_validated` keeps its existing behaviour, including converting any `Exception` raised
inside it into `InvalidEmbeddingError`. When M5 calls these seams from a job handler, M5 must
specify how cancellation and lease loss take precedence, as M4c did for provider resolution.

**`retrieve_with_vectors`** (persistence; receives a precomputed `EmbeddingBatch` and has **no
provider object**). It validates independently, before opening any transaction:

1. `actor` type, role (R4) and actor tenant equal to snapshot tenant;
2. request and snapshot structure (both revalidated through their constructors);
3. `query_vectors(query_batch, identity=snapshot.identity, query_count=len(request.queries))`:
   batch identity, `input_type == "query"`, vector count, numeric and dimension rules and
   canonical float32 conversion. Failure → `RetrievalProviderError`.

Validation cannot prove that the vectors were computed from the claimed query strings: the
precomputed-vector seam is **trusted internal input**. It then runs one read transaction:

1. the binding recheck;
2. for each query position in order: the lexical statement, and the vector statement unless the
   position is vector-skipped (at most 16 channel statements);
3. `fuse` in Python (at most 16 lists × 20 entries: bounded, cheap work);
4. one evidence statement for the final ≤ k chunk IDs, constrained to the snapshot bindings,
   tenant and vendor; each returned `text` must hash to its `content_sha256`, else
   `SnapshotInconsistentError`;
5. the immutable result, built inside the transaction before the helper rolls back and closes.

Changes between stages: every binding is immutable once captured, so a supersession, activation,
upload or indexing that commits between the provider call and the transaction cannot alter the
verified facts, and status is never consulted. There is no atomic boundary across the provider
call and the transaction, and no consistency claim across separate calls or requests; one result
is internally consistent because steps 1–4 read one database snapshot.

##### Database failure boundary

[REC] `hide_parameters=True` only hides parameter values in SQLAlchemy's logging and in
`StatementError` string formatting; it does not sanitize database or driver messages, exception
attributes (such as the statement or `orig`) or exception chains
([SQLAlchemy reference](https://docs.sqlalchemy.org/en/20/core/engines.html#sqlalchemy.create_engine.params.hide_parameters)).
The new seams therefore never let a raw database exception escape. A new fixed
`RetrievalDatabaseError` (`retrieval_database_failed`) covers session acquisition, the helper's
statements, `SET LOCAL`, every data statement, timeouts (`statement_timeout` cancellation),
connection failures, row conversion and transaction cleanup:

The seam's wrapper manages an explicit **pending outcome** around the unchanged
`read_snapshot` helper (clarified at acceptance in Prompt 133):

- **Body result, never inferred from exceptions.** The transaction body (`SET LOCAL`, the data
  statements, row conversion and value construction) returns either the result or a
  `SemanticOutcome` carrying one of the seam's fixed codes (`retrieval_scope`, `snapshot_empty`,
  `snapshot_bounds_exceeded`, `snapshot_inconsistent`, `snapshot_not_ready`). The seam's own
  checks produce semantic outcomes as values; they are not discovered by examining exceptions.
- **Recording before leaving the body.** Inside the `with read_snapshot(...)` block, an inner
  `try` around the body records the pending outcome: the result, the `SemanticOutcome`, or, for
  any ordinary `Exception` raised by the body (SQLAlchemy, DBAPI, `OSError`, timeouts, or a
  failure while converting backend values), the classification **operational**. Nothing else
  from the exception is kept, and the block then exits normally.
- **Cleanup.** Leaving the block runs the helper's rollback and close. An outer `try` around the
  `with` statement catches an ordinary `Exception` from session creation, the helper's two
  statements or that cleanup, and records only the fact that it happened.
- **Precedence.** If the body recorded a semantic or operational outcome, that recorded outcome
  stays primary even if cleanup also failed. If no body outcome was recorded (setup failed), the
  failure is operational. If the body succeeded but cleanup failed, the seam returns no result and
  raises `RetrievalDatabaseError`.
- **Fresh fixed errors.** After both `try` statements, outside every exception handler, the seam
  returns the result or raises a **new** fixed instance: the semantic error for a recorded
  semantic code, otherwise `RetrievalDatabaseError`. It keeps no original exception object, so no
  message, statement, parameter, vector, query text, cause or context is retained or logged.
- **No chain inference.** A backend exception whose cause or context chain happens to contain a
  semantic-looking error (even one of the seam's own error types) is still **operational**: only
  an outcome recorded by the seam's own checks is semantic.
- **Process control is not normalized.** Only `Exception` subclasses are caught. `KeyboardInterrupt`,
  `SystemExit` and other `BaseException` subclasses propagate (the helper still cleans up) and are
  never converted into `RetrievalDatabaseError` or a successful result.
- No automatic retry. A database failure never becomes a successful empty result. This defines
  failure precedence only; it is not a retry or cancellation protocol, and M5 job cancellation and
  lease integration remain deferred.

The engine's `hide_parameters=True` stays as defence in depth; no engine or workflow change is
proposed.

##### Lexical channel

[REC] One statement per query. Each channel statement repeats the **complete eligibility joins**
itself rather than relying only on the earlier recheck; the recheck additionally proves that
**every** binding verified. All filters are in the `WHERE`/`JOIN` conditions before
`ORDER BY … LIMIT 20`:

```sql
SELECT c.id, ts_rank_cd(c.search_vector, q.tsq) AS score
FROM (SELECT websearch_to_tsquery('simple'::regconfig, :query) AS tsq) AS q
CROSS JOIN (VALUES …snapshot bindings…) AS b(revision_id, document_id, index_id, chunker_version)
JOIN documents AS d
  ON d.tenant_id = :tenant AND d.id = b.document_id AND d.vendor_id = :vendor
JOIN document_revisions AS r
  ON r.tenant_id = :tenant AND r.id = b.revision_id AND r.document_id = d.id
 AND r.activated_at IS NOT NULL
JOIN embedding_indexes AS i
  ON i.tenant_id = :tenant AND i.id = b.index_id AND i.revision_id = r.id
 AND i.chunker_version = b.chunker_version AND i.status = 'ready' AND i.profile_id = :profile
JOIN chunk_embeddings AS e
  ON e.tenant_id = :tenant AND e.index_id = i.id
 AND e.revision_id = i.revision_id AND e.chunker_version = i.chunker_version
JOIN chunks AS c
  ON c.tenant_id = :tenant AND c.id = e.chunk_id AND c.revision_id = e.revision_id
 AND c.chunker_version = e.chunker_version AND c.content_sha256 = e.content_sha256
WHERE c.search_vector @@ q.tsq
  AND ts_rank_cd(c.search_vector, q.tsq) > 0
ORDER BY score DESC, c.id ASC
LIMIT 20
```

- **No current-status filter:** `activated_at IS NOT NULL` is immutable once true; `r.status` is
  never tested, so a revision superseded after capture stays eligible (decision 7).
- **Eligibility is never inferred from `search_vector`.** A chunk is a lexical candidate only
  through its embedding row in its binding's ready index for the pinned profile. Because each
  binding names exactly one index, a chunk that also has ready indexes under other profiles still
  appears at most once.
- **Query semantics** (`websearch_to_tsquery`, [SETTLED] R8): unquoted words are ANDed;
  `"quoted text"` becomes a phrase (`<->`); the word `or` gives OR; a leading `-` negates. It
  never raises a syntax error. The `simple` configuration lowercases and keeps every word (no
  stop words or stemming). Text with no lexemes (for example only punctuation) gives an empty
  query that matches nothing; PostgreSQL may emit a NOTICE, which is not an error.
- **Scores:** `ts_rank_cd` (`real`) with normalization 0. Only positive scores are candidates, so a
  negation-only query, which matches documents lacking the term with rank 0, contributes nothing.
  Scores are comparable within one list only.

##### Vector channel

[REC] One statement per query position that is not vector-skipped, with the same eligibility
joins (`b`, `d`, `r`, `i`, `e` as above; the chunk join is not needed for ordering) plus
`NOT e.is_zero`:

```sql
SELECT e.chunk_id, e.embedding <=> CAST(:query_vector AS vector(1024)) AS distance
FROM (VALUES …snapshot bindings…) AS b(revision_id, document_id, index_id, chunker_version)
JOIN documents AS d ON …as above…
JOIN document_revisions AS r ON …as above…
JOIN embedding_indexes AS i ON …as above…
JOIN chunk_embeddings AS e ON …as above…
WHERE NOT e.is_zero
ORDER BY distance ASC, e.chunk_id ASC
LIMIT 20
```

- `:query_vector` is `StoredVector.literal()`, the exact float32 text binding that M4b writes
  use, so the query is compared in the storage contract's float32 values.
- Exact cosine distance; no approximate index exists or is added, so the scan is exact. A planned
  catalog test asserts no HNSW or IVFFlat index on `chunk_embeddings`.
- `NOT e.is_zero` excludes stored zero vectors, whose cosine distance is NaN. A zero query vector
  issues no statement, so all-zero hash queries (for example non-ASCII text under the offline
  hasher) still use the lexical channel and never divide by zero.
- The reported score is the `double precision` distance (lower is closer), not a derived
  similarity. A non-finite returned distance is a `SnapshotInconsistentError`.

##### Fusion and results

[REC] `fuse(lists, *, query_count, vector_skipped, k)` is pure and deterministic:

- Its input is `ChannelList` values: at most one per (query position, channel), none for a
  vector-skipped position, positions below `query_count`. It revalidates each list's invariants
  (distinct entries, at most 20, finite scores, channel-specific order, ties by ascending UUID).
  PostgreSQL `uuid` ordering, canonical-string ordering and Python `UUID` ordering agree.
- A chunk's fused score is the exact sum, as `fractions.Fraction`, of `1/(60 + rank)` over every
  list containing it. Exact rationals make the sum independent of list order and float rounding,
  so equal scores really tie. `float` is used for display only; all comparisons use the
  `Fraction`.
- Sort by fused score descending, then chunk UUID ascending; return the first `min(k, n)` chunks,
  each once, with `fused_rank` 1…. Fewer than k candidates gives fewer results; none gives an
  empty result (not an error).
- **Determinism boundary:** for the same snapshot, configuration, stored rows, PostgreSQL version
  and query vectors, the lists and therefore the result are identical. No claim covers other
  PostgreSQL versions' ranking functions, live providers' repeated outputs or other platforms.

Success values carry authorized evidence text by design (see `ChunkEvidence`). The repeated
table header is a separate span with its own `header_text`; it is **not** contiguous with the
body, and later citation code must not quote across that boundary. `repr`/`str`, every error and
every log never show query text, chunk text, section paths, vectors or provider data.

##### Errors and privacy

[REC] New fixed-message errors in `evidenceguard_domain.retrieval` (messages are the codes):

| Error | Raised for |
|---|---|
| `InvalidRetrievalRequestError` (`invalid_retrieval_request`) | malformed request, k, vendor ID, identity or configuration |
| `InvalidSnapshotError` (`invalid_snapshot`) | a structurally invalid snapshot value from a caller |
| `PermissionDeniedError` (existing) | role not permitted |
| `RetrievalScopeError` (`retrieval_scope`) | missing or foreign vendor at capture; actor tenant differs from the snapshot |
| `EmptySnapshotError` (`snapshot_empty`) | no active revision |
| `SnapshotBoundsError` (`snapshot_bounds_exceeded`) | more than 100 active revisions or more than 100,000 chunks |
| `SnapshotNotReadyError` (`snapshot_not_ready`) | an active revision without a chunk set or ready index for the profile (no IDs) |
| `SnapshotInconsistentError` (`snapshot_inconsistent`) | a failed binding recheck, a non-active pointer, an invalid value built from rows, a text digest mismatch or a non-finite score |
| `RetrievalProviderError` (`retrieval_provider_failed`) | provider identity access, validation or mismatch; the embedding call; batch validation; canonical conversion |
| `RetrievalDatabaseError` (`retrieval_database_failed`) | any operational database failure, including timeouts and cleanup failures |

Precedence for `search_snapshot`: request and snapshot structure, role, scope, provider identity,
embedding, conversion, then the database phase (binding recheck, consistency and operational
failures as above). Missing and foreign objects are deliberately indistinguishable. No error
carries or chains query text, content, vectors, credentials, statements, parameters, provider
responses or exception text. Nothing in M4d logs.

##### Planned verification (not run)

All of the following are planned only.

*Database-independent tests* (`tests/test_retrieval_contracts.py`,
`tests/test_retrieval_orchestration.py`, `tests/test_retrieval_store.py`):

- strict construction of every value at and beyond each bound: supplementary characters, lone
  surrogates, NUL, whitespace-only text, duplicate queries, mutable collections, `bool` for
  integers, strings for UUIDs, unknown fields, naive datetimes, unsorted or duplicate bindings,
  two bindings for one document, wrong derived index IDs, inconsistent exclusion count/IDs/flag,
  invalid channel lists (duplicates, wrong order, non-finite or non-positive lexical scores, more
  than 20 entries, duplicate (position, channel) lists, a vector list for a skipped position),
  inconsistent results (ranks, counts, scores, provenance), and `dataclasses.replace`
  revalidation;
- **independently pinned canonical bytes and digests** for `RETRIEVAL_CONFIG_V1` and for fixed
  snapshot fixtures (computed by hand, not by the code under test), plus encoding rejections;
- `repr`/`str` and every error message free of queries, text, section paths and vectors;
- provider boundary: an identity getter raising an exception whose text holds a private marker
  (fixed error, marker absent from message, cause and context, no embedding call); identity
  mismatch before any call; an identity that changes between the first read and the read inside
  `embed_validated`; malformed results (wrong count, type, dimensions, input type); numeric
  conversion failure (a coordinate that overflows float32, a norm outside tolerance after
  rounding); and a provider exception inside `embed`;
- `retrieve_with_vectors` standalone: a batch with the wrong identity, `input_type="document"`,
  a wrong count or invalid numbers, with no provider object involved;
- **database failure boundary with fake sessions:** exceptions carrying a marker in their message,
  their statement and parameters attributes and in chained causes; a statement timeout; a
  connection failure during acquisition; a row-conversion failure; a cleanup failure after a
  semantic outcome, after an operational failure and after success; and a backend exception whose
  chain contains a semantic error that the seam did not record (it stays operational). Each yields
  the expected fixed error with the marker absent from its message, `__cause__`, `__context__` and
  traceback text, never an empty result, and no retry; a `BaseException` such as
  `KeyboardInterrupt` raised in the body propagates unconverted;
- pure fusion fixtures: ties within a list and across fused scores, duplicates fused across
  queries and channels, a case where float addition order would change the result but `Fraction`
  does not, fewer than k candidates and the empty result;
- orchestration with fakes: no session is open while the provider runs, capture precedes the
  provider call in `search_current`, and pure checks precede any provider or SQL call.

Pure fusion fixtures do not establish that the PostgreSQL statements rank and filter correctly;
the PostgreSQL tests below do.

*PostgreSQL tests* (`tests/test_retrieval_postgres.py`, integration marker, real ingestion and
indexing through the existing worker and M4c paths):

- capture: success with exact bindings, counts and exclusion record (including more than 100
  pending revisions, giving `truncated`); an active unindexed revision; a `building` index; a
  ready index under another profile only; empty and 101-revision vendors; a chunk total above
  100,000 (built efficiently under the existing constraints, or with an explicitly reviewed
  lower-level fixture); foreign vendor and foreign tenant indistinguishable; precedence when
  several phases would fail at once, in different row orders;
- supersession: superseded at capture excluded; active at capture then superseded still
  retrieved; a later revision absent from the older snapshot; pending and processing excluded
  and recorded;
- **lexical semantics against real PostgreSQL:** AND of unquoted words, a quoted phrase, `or`,
  a negation-only query (no candidates), punctuation-only input (no candidates, no error),
  positive-score filtering, and `simple` behaviour (case folding, no stemming or stop words);
- **exact cosine ordering** with independently chosen stored and query vectors whose distances are
  computed by hand; equal-distance and equal-lexical-score ties ordered by ascending UUID; stored
  zero vectors never returned; a zero query vector falling back to lexical only;
- **fusion end to end:** several queries and both channels, compared with ranks and RRF scores
  calculated independently from the fixture;
- **filters before limits:** an eligible candidate still returned when more than 20 higher-scoring
  forbidden candidates exist in another tenant, another vendor, a superseded-before-capture
  revision, a wrong-profile index and a `building` index, in both channels;
- ready indexes for several profiles on the same revisions without duplicate lexical candidates;
- binding recheck: forged snapshots with a foreign revision, another vendor's revision, a
  never-activated revision, a changed manifest, count or index ID each raise
  `SnapshotInconsistentError`;
- **deterministic interleavings** positioned relative to the real snapshot establishment: a
  test-owned SQLAlchemy `after_cursor_execute` listener on the test engine pauses the capture
  connection right after the helper's `clock_timestamp()` statement, using `threading.Event`
  handshakes, not sleeps. An activation committed while paused must be invisible; one committed
  before the helper's first `SELECT` must be visible (refusing capture until indexed). The same
  technique covers indexing completing during capture and a supersession between capture and
  retrieval;
- the statement timeout: a statement exceeding a test-lowered timeout yields
  `RetrievalDatabaseError` (the production value is not changed by tests);
- pooled settings restored: on the same pooled connection afterwards, `transaction_isolation`,
  `transaction_read_only` and `statement_timeout` are back to their defaults;
- no side effects: jobs, indexes, embeddings, revisions and documents unchanged after capture and
  retrieval;
- exactness: no HNSW/IVFFlat index exists;
- result evidence: text, spans, repeated-header split and provenance match the stored rows.

*Packaging and wheel.* `tests/test_packaging.py` keeps the existing boundaries unchanged.
[SETTLED] R9: the CI installed-wheel step is extended to import the three new modules from
`site-packages` and run `fuse` on a fixed fixture with a pinned expected result. This is a
**required** future acceptance check; the workflow edit belongs to the implementation, not to
this specification task.

These tests make no retrieval-quality, injection-resistance or benchmark claim. Corpus and Recall
work remain M4e; the mocked Voyage adapter remains M4f.

##### M4d review decisions (settled in Prompt 132)

[SETTLED] The reviewer approved the recommended option for each decision in Prompt 132. The
complete specification, including these choices, was accepted in Prompt 133.

- **R1.** Pure fusion in the domain package (`evidenceguard_domain.retrieval`).
- **R2.** Provider and persistence orchestration in the worker package
  (`evidenceguard_worker.retrieval`).
- **R3.** Trusted in-process snapshots with database binding rechecks until M5, with the six
  explicit conditions recorded under [Trust model](#trust-model): a trusted internal programming
  interface; binding checks do not prove past active-at-capture eligibility; no endpoint or
  untrusted snapshot deserialization; a recomputable digest is not authorization; M5 persists and
  reloads the captured facts through trusted paths; no protection against malicious in-process
  code is established.
- **R4.** Reviewer and approver roles only, matching `DOCUMENT_ROLES`.
- **R5.** Exact exclusion count, at most 100 ascending IDs and a `truncated` flag.
- **R6.** A fixed not-ready error with no revision IDs.
- **R7.** A transaction-local `statement_timeout` of 30,000 ms, per statement. The scan-volume
  estimate behind it (about 400 MB of vectors per exact vector query at the 100,000-chunk bound,
  up to 8 per request) is an engineering estimate, not a measured runtime or memory figure.
- **R8.** `websearch_to_tsquery` with the explicit `simple` configuration.
- **R9.** A narrow CI installed-wheel extension importing the new modules and executing fusion on
  a fixed fixture: a required future acceptance check.

No specification decision remains open. The details introduced by the Prompt 132 corrections
(the `eg-retrieval-canonical-v1` encoding and field sets, `captured_at` as informational
provenance in the digest, internally derived digests, `vector_skipped` in results, the fixed
provider and database failure boundaries, standalone batch validation mapped to
`RetrievalProviderError` and the fake-session tests in `tests/test_retrieval_store.py`) were
accepted with the specification in Prompt 133, together with its two final clarifications.

##### Intended changes, required checks and deferred work

- **New files:** the three modules above and `tests/test_retrieval_contracts.py`,
  `tests/test_retrieval_orchestration.py`, `tests/test_retrieval_store.py` and
  `tests/test_retrieval_postgres.py`; ADR-0016 at implementation; README, plan and threat-model
  updates.
- **Changed files:** `.github/workflows/ci.yml` for the required R9 wheel extension only. No
  other existing source changes.
- **No migration** (existing columns, GIN index and exact operators suffice), **no dependency or
  lockfile change**, no Dockerfile or Compose change, no engine setting change.
- **Required acceptance checks (future):** lint, format, strict mypy, the database-independent
  suite on Ubuntu and Windows, the PostgreSQL integration job including every case above, both
  builds and the installed-wheel checks including the R9 extension, the unchanged container job
  and Gitleaks.
- **Deferred:** review persistence, endpoints and orchestration (M5), including cancellation and
  lease precedence when called from a job; activation wiring and stalled-index recovery; the corpus
  and Recall (M4e); Voyage (M4f); any approximate index (E5); live-provider evidence (M7).

#### M4e corpus and retrieval-evaluation specification (ACCEPTED at review, Prompt 143; implementation pending)

**Status.** **Proposed by Claude Code in Prompt 140, corrected in Prompts 141–142 and accepted
at external review in Prompt 143 with two final clarifications** (the fresh-run versus verifier
starting states, and enumeration of every embedding profile by the read-only verifier). E1–E11
and N1–N12 are settled within the complete accepted specification (see
[M4e settled review decisions](#m4e-settled-review-decisions-prompts-141-and-142) and
[M4e decisions settled at acceptance](#m4e-decisions-settled-at-acceptance-prompt-143)). The items
labelled [REC] below were written as recommendations in Prompts 140–142; with this acceptance they
**form the accepted implementation contract**, and **no specification decision remains open**.
Acceptance is a design decision, not implementation or execution evidence.
**Implementation (Prompt 144, corrected in Prompts 145–146):** Claude Code implemented this
specification on `feat/retrieval-evaluation` ([ADR-0017](decisions/0017-retrieval-evaluation.md)) and in Prompt 145
corrected four review findings (complete anchor validation before any database work, vendor
IDs only after a successful commit, read failures preserved through cleanup, and aggregate
bounds before payload reads) and in Prompt 146 closed a remaining read-boundary gap (process
control raised by the setup clock result's `scalar_one()`). The implementation was **accepted
at external review in Prompt 147 for a local implementation commit** and **published on
`feat/retrieval-evaluation` in Prompt 148 at `c14821b7`**. The Prompt 149 correction, accepted
in Prompt 150, was verified in feature-branch CI at `d1dcdfce` (historical; see
[feature-branch CI evidence](decisions/0017-retrieval-evaluation.md#feature-branch-ci-evidence-at-d1dcdfce))
and is now **reviewed, verified in CI and on `main` at `0ae4c6ca`** (see
[main CI evidence](decisions/0017-retrieval-evaluation.md#main-ci-evidence-at-0ae4c6ca)). The disclosed verifier scope was accepted: it checks each
canonical job's kind, idempotency key and `succeeded` status but does not read job `payload`
(accepted read item 6; see ADR-0017), so no payload validation is claimed. From job logs
retrieved independently by the external reviewer, PostgreSQL integration at `c14821b7` passed
(306 passed, including all 16 M4e cases, the first executed PostgreSQL evidence for M4e), while
Ubuntu verify failed one test (`1 failed, 2245 passed, 306 skipped`) because its `os.lstat`
double re-entered itself on Linux; the Ubuntu build and installed-wheel steps were skipped. No
production defect has been established. Claude Code's Prompt 149 correction and the corrected Linux tests, Ubuntu build and wheel
checks have since passed at `d1dcdfce`; the `c14821b7` failure remains historical (see
[ADR-0017](decisions/0017-retrieval-evaluation.md#exact-commit-ci-at-c14821b7-and-test-correction-prompts-148149)).
Passing PostgreSQL tests supply no numerical Recall result, and no database-derived Recall value
has been observed. The earlier local checks are historical evidence attributed to Claude Code
(see [M4e local verification (Prompt 146)](#m4e-local-verification-prompt-146); the
[Prompt 145](#m4e-local-verification-prompt-145) and
[Prompt 144](#m4e-local-verification-prompt-144) checks are historical), as is the earlier
statement that the M4e PostgreSQL tests had never run. The planned-verification wording
below is kept as accepted. Labels: **[DECISION]** accepted in Prompt 108 (see
[M4 direction and review decisions](#m4-direction-and-review-decisions)); **[SETTLED]** E1–E11
(Prompt 141), N1–N9 (Prompt 142, as corrected) and N10–N12 (Prompt 143); **[FACT]** established
from source on `main` at `cf2b5743`; **[REC]** an original recommendation, now part of the
accepted contract. M4d
is reviewed, verified in CI and on `main` at `cf2b5743`; nothing here changes the M4d trust model,
ranking rules, bounds, UUID generation, capture time, tie-breaking or snapshot contracts.

**Scope.** A synthetic corpus and authored ground truth, a bounded test-only orchestrator over
the existing production lifecycle, deterministic anchor-to-chunk resolution, Recall@5/@8 over the
existing M4d retrieval seams, retrieval contract and isolation checks, and their tests. **Out of
scope** (deferred): model-generated report judgments, claim-support precision, support-judgment
accuracy and status accuracy (M5/M7); end-to-end injection resistance and output-canary behaviour
(M5/M7); live model/provider quality and cost (M7); the review workflow, approval endpoints and
snapshot persistence (M5–M6); the Voyage adapter (M4f); any GUI, deployment or container-smoke
change. Ground-truth fields that later metrics need are specified and validated now, but **no
later metric executes in M4e**.

##### Accepted decisions preserved (Prompt 108)

[DECISION] Preserve §7's fictional tenants and vendors, conflicting retention evidence, missing
evidence, table content, wrong claims paired with valid quotations and the injection case. Load
clean and injected variants separately; only the injection paragraph differs, while revision
hashes and derived IDs may differ. Human anchors plus exact quoted spans resolve deterministically
against the pinned chunker and manifest. The relevance unit is a distinct authorized chunk ID;
each gold passage resolves to every chunk containing its full required span; missing or ambiguous
mappings fail unless an explicit multi-chunk annotation resolves them; shared chunks are
deduplicated. For a nonempty gold set G, `Recall@k = |set(top_k_chunk_ids) ∩ G| / |G|`, reported
per question and as a macro mean over nonempty sets at k = 5 and 8, separately by variant and
profile; empty G is N/A (excluded and counted); an all-empty suite is N/A, never 1; duplicate
retrieval IDs are contract errors; foreign or forbidden results fail isolation even when recall is
high. Hashing proves reproducibility and retrieval contracts only; no semantic-quality or
injection-resistance claim.

##### Facts from current source (`cf2b5743`)

- [FACT] **No corpus or evaluation code exists.** There is no `sample_data/` directory, no
  evaluation module and no `eg-eval` script; the console scripts are `eg-api`, `eg-admin` and
  `eg-worker`. §7's commands are plans.
- [FACT] **No YAML parser is a dependency.** `tomllib` (read-only TOML) and `json` are in the
  standard library.
- [FACT] **Tenants.** `DatabaseAdminStore.seed_demo()` (`eg-admin seed-demo`) idempotently creates
  exactly the synthetic tenants `halverson-freight` and `marisol-clinics`, with deterministic UUID5
  tenant and user IDs (`demo_tenant_id`, `demo_user_id`) and one user per role.
- [FACT] **Vendors.** `vendors.create_vendor(session, actor, *, slug, name)` always inserts a new
  row with a **UUID4** ID and flushes; a duplicate slug in the tenant raises
  `DuplicateVendorSlugError` after the flush, which leaves the session's transaction needing a
  rollback before further queries. It never returns an existing vendor. There is no
  get-by-slug helper; `list_vendors(session, actor, *, limit, offset)` pages the tenant's vendors
  ordered by `(slug, id)`.
- [FACT] **Documents and revisions.** `document_views.create_upload(session, actor, *, vendor_id,
  document_key, title, source_type, content, version_label=None, effective_date=None)` runs in the
  caller's transaction: `create_revision` inserts a new document or revision with **UUID4** IDs, or
  returns the existing revision with identical content for that document (any status; a metadata
  difference raises `DocumentConflictError` or `RevisionConflictError`); a new or still-unsettled
  revision gets its canonical `ingest_revision` job (idempotently); **a settled duplicate is never
  re-enqueued**. Document keys match `^[a-z0-9]+(?:-[a-z0-9]+)*$` (≤ 64), titles ≤ 200, version
  labels ≤ 64; media types are `text/markdown` and `text/plain`; content is strict UTF-8 without
  NUL. `source_type` is `vendor_statement`, `contract` or `third_party_report`; `authenticity`
  has one value, `not_established`. Editor roles are reviewer and approver.
- [FACT] **Activation happens in ingestion.** The `ingest_revision` handler chunks a revision and
  activates it (superseding the document's current active revision) when its job succeeds.
  `run_worker(..., once=True)` performs one claim; its exit code reports the worker loop, not the
  job's outcome, which must be read from the job, revision and index rows.
- [FACT] **Indexing.** `indexing.enqueue_index_revision(session, actor, *, revision_id, identity)`
  creates the index and canonical `index_revision` job, or reports `ready` or `stalled` (a terminal
  canonical job is never reset); it accepts any revision that was ever activated. The production
  registry indexes with `HASH_IDENTITY` only.
- [FACT] **Chunker.** `chunking.chunk_revision(content, *, tenant_id, revision_id)` with
  `CHUNKER_VERSION = "text-md-v1"`. Chunk IDs are UUID5 of `(tenant, revision, chunker_version,
  ordinal)`, so they inherit the revision's fresh UUID4. Body spans are code-point ranges into the
  stored text; between consecutive chunks a split may omit only line terminators (LF, or CR
  immediately before LF), a leading BOM and spaces/tabs (U+0020, U+0009). A long table's
  continuation chunks repeat its header as a separate `header_*` span ending before the body;
  chunk `text` is header slice + body slice. Any visible text inserted into a document becomes
  chunk text and lexemes and can move boundaries.
- [FACT] **Retrieval and determinism inputs.** `capture_snapshot(session_factory, actor, *,
  vendor_id, identity)` and `search_snapshot(session_factory, actor, snapshot, request, provider)`
  are trusted internal seams. `RetrievalSnapshot.sha256` covers `captured_at` (from the database
  `clock_timestamp()`), and the bindings' UUID4 revision and document IDs. Lists and fusion break
  ties by ascending chunk UUID, and fusion truncates one order, so for one snapshot and query set
  the top 5 of a k = 8 request equal a k = 5 request. `EvidenceQuestion.search_queries` allows
  1–5 queries.
- [FACT] **Boundaries and guards.** `evidenceguard_retrieval` may import only the domain and the
  standard library (never `os`, `sqlalchemy` or network modules); the worker may import domain,
  persistence and retrieval. Destructive PostgreSQL tests require `EG_TEST_DATABASE_URL` naming a
  `_test` database distinct from `EG_DATABASE_URL`.

##### A. Corpus, references and ground truth

[SETTLED] E1, E2, E5: TOML parsed with `tomllib`; anchors exist only in ground truth, never in
documents; `sample_data/` is repository-only and included in the sdist, not the wheel.

**Layout** (§7's document set and tenant/vendor structure; TOML replaces the YAML names):

```text
sample_data/
  corpus.toml
  documents/<tenant>/<vendor>/<document_key>@r<n>.md
  variants/injected/<tenant>/<vendor>/trust-center-page@r1.md
  ground_truth/<tenant>.toml
```

**Canonical reference** [REC]. Every reference to evidence anywhere in ground truth is one string:

```text
<tenant>/<vendor>/<document_key>@r<n>#<anchor>
```

Each segment matches `^[a-z0-9]+(-[a-z0-9]+)*$` (anchor ≤ 64 characters) and `n` is a positive
decimal integer without leading zeros. An anchor is defined once, in the ground-truth file of its
own tenant; its local name is unique within its revision. Bare names are never accepted. Every
reference must name a defined anchor; foreign-tenant references are allowed only in `forbidden`.

**`corpus.toml`** [REC] (all keys required unless marked optional; unknown keys rejected at every
level; values must have the exact TOML types shown):

```toml
format = "eg-corpus-v1"

[[tenants]]
slug = "halverson-freight"                # one of the two seeded demo tenants

  [[tenants.vendors]]
  slug = "lumenvale-cloud"
  name = "Lumenvale Cloud"

    [[tenants.vendors.documents]]
    key = "data-retention-policy"
    title = "Data Retention Policy"
    source_type = "vendor_statement"        # vendor_statement | contract | third_party_report
    media_type = "text/markdown"            # text/markdown | text/plain

      [[tenants.vendors.documents.revisions]]
      n = 1                                  # 1, 2, … in order, no gaps
      version_label = "2025.1"               # optional string
      effective_date = 2025-01-15            # optional TOML local date

[variants.injected]
replaces = ["halverson-freight/lumenvale-cloud/trust-center-page@r1"]
```

The file for revision `n` is `documents/<tenant>/<vendor>/<key>@r<n>.md`, derived from validated
segments, never read from a free-form path. Document bytes are the file bytes exactly; their
SHA-256 is computed, never stored in the manifest. The newsletter distractor is
`vendor_statement`, the DPA summary `contract`, Ferrowick's SOC 2 letter `third_party_report`;
every document is `not_established` (the only stored value).

**`ground_truth/<tenant>.toml`** [REC]:

```toml
format = "eg-ground-truth-v1"
tenant = "halverson-freight"               # must equal the file name stem

[[anchors]]
ref = "halverson-freight/lumenvale-cloud/data-retention-policy@r2#ninety-days"
quote = "Customer data is retained for ninety (90) days after termination."
occurrence = 1                             # optional; required only if the quote repeats
# parts = [{ quote = "…", occurrence = 1 }, { quote = "…" }]   # optional, see C

[[questions]]
vendor = "lumenvale-cloud"                 # the question belongs to this tenant × vendor
id = "RET-01"                              # QuestionId, unique per tenant × vendor
text = "How long is customer data retained after termination?"
search_queries = ["data retention after termination", "retention period days"]

  [[questions.cases]]
  epochs = ["initial"]
  expected_status = "conflicting"
  gold = [
    "halverson-freight/lumenvale-cloud/data-retention-policy@r1#one-eighty-days",
    "halverson-freight/lumenvale-cloud/dpa-summary@r1#thirty-days",
  ]
  forbidden = ["halverson-freight/lumenvale-cloud/data-retention-policy@r2#ninety-days"]
  acceptable_claims = [{ text = "…", refs = ["…@r1#one-eighty-days"] }]
  wrong_claims = []

  [[questions.cases]]
  epochs = ["final"]
  expected_status = "conflicting"
  gold = [
    "halverson-freight/lumenvale-cloud/data-retention-policy@r2#ninety-days",
    "halverson-freight/lumenvale-cloud/dpa-summary@r1#thirty-days",
  ]
  forbidden = ["halverson-freight/lumenvale-cloud/data-retention-policy@r1#one-eighty-days"]
  acceptable_claims = [{ text = "…", refs = ["…@r2#ninety-days"] }]
  wrong_claims = []
```

(`…` in `refs` abbreviates the full canonical reference; the real file always uses full strings.)
A question has 1–2 cases; each case's `epochs` is a nonempty subset of `["initial", "final"]`;
across a question's cases the epochs are disjoint, and every epoch in which the question is
evaluated has exactly one case (a question with no case for an epoch is not evaluated there).
Questions whose evidence does not change list one case with `epochs = ["initial", "final"]`.
Case fields: `expected_status`, `gold`, `forbidden`, `acceptable_claims`, `wrong_claims` (all
required; lists may be empty). Each claim has `text` (1–500 characters) and `refs` (1–8 canonical
references). **Authored labels** are exactly these fields; nothing is derived from retrieval
output or model judgments. M4e validates claims' references; their support judgments are M5/M7.

**Quote and occurrence rules** [REC] (apply to every anchor `quote` and every `parts` entry;
checked before any database work; failures use the fixed code `anchor_invalid` unless noted):

- **Type:** `quote` is a TOML string (exact `str`); `occurrence`, when present, is a TOML integer
  (exact `int`, never `bool`) with value ≥ 1. An anchor table has exactly the keys `ref`, `quote`
  and optionally `occurrence` and `parts`; a part table has exactly `quote` and optionally
  `occurrence`. Any other key is rejected.
- **Length and encoding:** 1–4,000 code points; strictly UTF-8 encodable (no unpaired surrogate);
  no U+0000 and no other C0 control character except TAB (U+0009) and LF (U+000A); no CR
  (U+000D). Corpus documents are likewise required to use LF line endings only, so every quote is
  matched against LF-only text.
- **Whitespace:** the first and the last code point must not be U+0020, TAB or LF. Interior spaces,
  tabs and LFs are allowed and matched exactly.
- **Multiline:** a quote may span lines (interior LF), for body prose and table rows alike. It is
  still one source-contiguous range with exact offsets; whether a single chunk contains it is
  decided only by the containment rule in C, and a quote that crosses a chunk boundary needs
  `parts`.
- **Matching:** code-point equality against the stored revision text: no case folding, whitespace
  collapsing or Unicode normalization.
- **Occurrence:** matches are counted left to right without overlap (after a match at `[i, j)`,
  the search resumes at `j`). The parent quote is matched in the whole revision text; a part is
  matched only inside the selected parent range `[s, e)` (a match must lie entirely within it).
  No match: `anchor_not_found` (`anchor_part_not_found` for a part). More than one match and no
  `occurrence`: `anchor_ambiguous` (`anchor_part_ambiguous`). An `occurrence` greater than the
  number of matches: `anchor_occurrence_out_of_range` (`anchor_part_occurrence_out_of_range`).
  `occurrence` may also be given when there is exactly one match (it must then be 1).

**Reference validation** [REC] (before any database work, fixed codes): every reference parses,
names a defined anchor (`unknown_reference`); `gold` and claim references name the question's
own tenant and vendor (`foreign_gold_reference`); a gold reference names, for every epoch of its
case, the revision eligible in that epoch, which is `r1` for `initial` and the document's highest
`n` for `final` (`gold_not_eligible_in_epoch`); no reference appears in both `gold` and
`forbidden` of one case (`gold_forbidden_conflict`); `forbidden` may name any revision of any
document, including later revisions, other vendors and the other tenant; local anchor names may
repeat across tenants or revisions, because only full references identify anchors.

**Content** (from §7): RET-01 conflict with the superseded r1 180-day trap (per-epoch cases as
above); ENC-01, INC-01 and BCP-01 with empty gold; CMP-01/CMP-02 vendor claims; SUB-01 a short
table kept as one chunk; Ferrowick's SOC 2 letter in the same tenant (cross-vendor trap); Tenant B
mirrors with canaries `LV-TB-CANARY-36H` and `LV-TB-CANARY-AES` (cross-tenant trap, referenced in
Tenant A's `forbidden`); the injected variant adds exactly one paragraph to
`trust-center-page@r1.md`. All names, numbers and text are fictional; no real client documents,
credentials or personal data.

**Bounds, paths and validation** [REC] (fixed codes, no content in messages): at most 2 tenants,
8 vendors, 64 documents, 4 revisions per document, 256 anchors, 64 questions and 2 cases per
question per tenant. Byte limits are checked from file metadata **before reading** and again on
the bytes: `corpus.toml` ≤ 64 KiB, each ground-truth file ≤ 256 KiB, each document ≤ 256 KiB
(below the 2 MiB upload cap), the whole selected file set ≤ 4 MiB. **Path containment:** every
file path is built from validated segments under the corpus root; each path component is checked
to be a non-symlink, the final file to be a regular file, and the resolved path to remain under
the resolved root; files present under `documents/`, `variants/` or `ground_truth/` but not
named by the manifest are rejected (`corpus_unexpected_file`). Clean and injected file sets
differ in exactly the files listed in `replaces`, and each injected text equals its clean text
with one inserted paragraph (one contiguous insertion bounded by blank lines). Loading order is
deterministic: tenants, vendors, documents and revisions sorted by slug, key and `n`.

##### B. Orchestration, lifecycle and repeat runs

[SETTLED] E4, E6, E11: tests are the only entry point; two epochs, `initial` and `final`; each
variant is loaded into a freshly reset disposable database.

[SETTLED] N3 and N4, as corrected in Prompt 142. Three separate test-only contracts in
`evidenceguard_worker.evaluation`; only the first writes:

**1. Fresh two-epoch run** — `run_fresh_two_epoch(session_factory, corpus) -> TwoEpochState`,
global phases in this order:

1. **Validate** the entire corpus and ground truth (A) before any database write.
2. **Freshness check** (read only, in one `read_snapshot` transaction): if any vendor, document,
   revision, embedding profile, embedding index or job of kind `ingest_revision` or
   `index_revision` already exists for a corpus tenant, refuse with `corpus_state_not_fresh` and
   write nothing. Seeded tenants and users alone are allowed. This corpus-tenant-wide scope is the
   same as the verifier's extra-state scope.
3. **Tenants and vendors:** `seed_demo()`; act as each tenant's seeded reviewer. Vendors: one
   transaction lists the tenant's vendors (`list_vendors`); an existing slug with an equal name is
   reused, a different name is `corpus_conflict`; a missing slug is created with `create_vendor`
   in **its own** transaction. If that raises `DuplicateVendorSlugError` (a concurrent insert), the
   transaction is rolled back by the existing `transaction` helper, the vendor is re-read in a new
   transaction and compared as above. `create_vendor` is never assumed to return an existing row.
4. **Revision 1 of every document:** in deterministic order, one transaction runs `create_upload`
   (which must report `created = True`); then the worker runs once and the orchestrator reads the
   job, revision and chunk set until the job is `succeeded` and the revision `active` with a
   verified chunk set. Then for every r1, `enqueue_index_revision(identity=HASH_IDENTITY)` and the
   worker until the canonical index job is `succeeded` and the index `ready`.
5. **Capture `initial`:** for each tenant × vendor with questions, `capture_snapshot`; require
   every binding to be the vendor's r1 revision and no binding to be a later revision. The
   snapshot values are **retained in memory** in the returned state. No later revision exists yet,
   so the initial snapshot is genuinely captured before any r2 activation.
6. **Later revisions** in manifest order (n = 2, 3, … per document): create, ingest (activation
   supersedes r(n−1)), verify the previous revision is `superseded` and the new one `active`, then
   index to `ready`.
7. **Capture `final`:** for each tenant × vendor; require every binding to be the document's
   highest revision and every index ready.
8. **Return** `TwoEpochState`: the loaded logical-to-actual map (logical revision → revision,
   document and vendor IDs), the retained `initial` and `final` snapshots, and nothing else.
   Snapshots are never persisted and never re-created for an earlier epoch.

**Bounded claims and outcomes:** the orchestrator enqueues one job at a time; each expected job
allows at most two `run_worker(once=True)` invocations, after which a job still queued or running
is `corpus_job_not_settled`; a `failed` or `dead` job is `corpus_job_failed`; a failed revision is
`corpus_revision_failed`; a `stalled` or non-ready index is `corpus_index_not_ready`. Worker exit
codes are never treated as job success. Each step commits independently; any failure stops the run
with a fixed code, leaves rows as they are and returns no state. A partially loaded database is
never resumed by the fresh run (its freshness check refuses it); the test resets the disposable
database instead.

**2. Read-only verifier** [REC] — `verify_loaded(session_factory, corpus) -> LoadedCorpus`, for an
already loaded database. It is **genuinely read-only**: it calls no `seed_demo`, `create_vendor`,
`create_upload`, `create_revision`, `ensure_profile`, `create_index` or `enqueue`/
`enqueue_index_revision`, runs no worker, captures no snapshot, executes no DML and repairs
nothing. After validating the corpus (A), it reads everything inside **one** transaction opened
with the existing, unchanged `document_views.read_snapshot` helper (`SET TRANSACTION ISOLATION
LEVEL REPEATABLE READ, READ ONLY`, then `clock_timestamp()`, rollback and close), so every
statement sees one consistent view and any accidental write fails.

Read statements (planned; SQLAlchemy Core over the existing table objects, in
`evidenceguard_worker/evaluation.py`, which may already import `sqlalchemy` and
`evidenceguard_persistence`; existing builders reused where they fit):

1. tenants by `demo_tenant_id(slug)` and the seeded reviewer by `demo_user_id(slug, REVIEWER)`;
2. every vendor of each corpus tenant (`vendors` by `tenant_id`);
3. every document of each corpus tenant, and every revision of those documents ordered by
   `revision_no` (all columns except `content_text`), then each expected revision's
   `content_text`, `sha256` and `byte_size`;
4. per revision: `chunks.chunk_set_statement` and `chunks.manifest_rows_statement` (manifest
   rebuilt from stored fields);
5. **every** `embedding_indexes` row of the tenant, with `embeddings.embedding_count_statement`
   per expected index; and **every** `embedding_profiles` row of the tenant (all columns, by
   `tenant_id`), not only a lookup by fingerprint;
6. every `ingest_revision` and `index_revision` job of the tenant (`kind`, `idempotency_key`,
   `status`, `payload`).

Checks: tenants and reviewer exist (else `corpus_state_incomplete`); vendors, documents and
revisions equal the manifest's exactly in slug, name, key, title, source type, media type,
revision numbers, version label, effective date and content hash (a difference is
`corpus_conflict`, a missing record `corpus_state_incomplete`); **the highest revision is
`active` and every earlier revision `superseded`** (a superseded r1 is the correct historical
state and is accepted, never reactivated), anything else (`pending`, `processing`, `failed`) is
`corpus_state_unsettled`; each stored manifest equals the rebuilt manifest and the manifest of
`chunk_revision` over the stored text (`mapping_manifest_mismatch`); the tenant's profile set is
exactly one row whose stored identity (`provider_id`, `model_id`, `algorithm_version`, `dims`,
`normalization`, `allows_zero_vectors`), `fingerprint` and `id` equal those derived from
`HASH_IDENTITY` (`profile_id(tenant, fingerprint)`): no row is `corpus_state_incomplete`, a row with
that fingerprint but different fields or ID is `corpus_conflict`, and any additional profile is
`corpus_state_unexpected`; each revision has a `ready` index for the profile whose embedding count equals its chunk count (`corpus_index_not_ready`);
each revision's canonical ingestion job (key `str(revision_id)`) and each index's canonical
indexing job (key `str(index_id)`) is `succeeded` (`corpus_job_not_settled` or
`corpus_job_failed`).

**Extra-state scope** matches the freshness check: it is **corpus-tenant-wide**. Any vendor,
document, revision, embedding profile, embedding index or job of kind `ingest_revision` or
`index_revision` in a corpus tenant that the manifest does not describe is `corpus_state_unexpected`
(users and API keys are not corpus state and are not checked beyond the seeded reviewer). The
verifier returns only the logical-to-actual ID map; it **never captures or reports an `initial`
epoch** (a two-epoch evaluation needs a fresh run's retained `TwoEpochState` or a new fresh
database). Every refusal is a fixed `EvaluationError` after the read transaction has ended; nothing
is written, so refusal leaves the database unchanged.

**Production-seam reuse (separate from the verifier)** [REC]: a planned PostgreSQL test, after a
complete fresh load, records every corpus-table row and job, then calls the existing write seams on
the known complete records, each in its own `transaction` block: `seed_demo()` (every user
reported existing), `create_upload` for every revision (each `created = False`, the stored status,
and no job enqueued for a settled revision) and `enqueue_index_revision` for every revision
(outcome `ready`, no job). It then asserts that every recorded row and job is unchanged and that no
row or job was added. These calls only demonstrate reuse on a complete corpus; they are never used
to probe whether a partial database is complete.

**3. Evaluation** — `evaluate(session_factory, corpus, state, provider) -> EvaluationReport`
(reads only; stored chunks are read in `read_snapshot` transactions and retrieval uses the M4d
seams, which are themselves read-only): after both captures, read the stored chunk rows and chunk-set manifests of **every
loaded revision** (including superseded r1 and later revisions), resolve every reference (C), then
run retrieval for the retained `initial` snapshots and the `final` snapshots (D). Evaluating the
initial snapshots after r2 has activated is the point of the second epoch.

**No hidden edits:** nothing here updates or deletes terminal rows, edits statuses, marks an index
ready, fabricates chunk sets, embeddings or snapshots, or alters activation order outside the
production handler; the M4d metadata-only bound fixture stays confined to its one M4d test.
**Database independence:** validation, reference checks, the variant diff, offline chunking,
anchor resolution against `chunk_revision` and all Recall and report code run without a database;
loading, capture, retrieval and mapping against stored chunks need PostgreSQL. **Production
protection:** the only planned callers are PostgreSQL tests using the existing guarded
disposable-database fixtures; there is no installed command.

##### C. Anchor-to-chunk resolution

[REC] **Inputs:** a validated anchor; the revision's stored text; its chunks (`id`, `ordinal`,
body span, optional header span, `chunker_version`) and chunk-set `manifest_sha256`. **Checks
first:** `chunker_version == "text-md-v1"`, and the stored manifest equals the manifest rebuilt
from the stored rows and the manifest of `chunk_revision` over the stored text
(`mapping_manifest_mismatch`).

**Single-quote anchors.** Locate the quote in the revision source text by the quote and
occurrence rules in A (`anchor_not_found`, `anchor_ambiguous` or
`anchor_occurrence_out_of_range` on failure). With the range
`[s, e)`, the anchor maps to **every** chunk whose body span contains `[s, e)` (route `body`) and
every chunk whose repeated header span contains it (route `header`). If none contains it, the
anchor is `anchor_crosses_chunk_boundary` (the text exists but spans a boundary) unless it has
`parts`.

**Multi-part anchors** (`parts`, the explicit multi-chunk annotation) [REC]:

- `parts` is an array of 2–8 inline tables `{ quote = <string>, occurrence = <integer, optional> }`
  with no other keys; each part obeys the quote and occurrence rules in A.
- The parent quote is located first (as above, with its own `occurrence`). Each part is located
  **within the parent range** `[s, e)` only; its `occurrence` counts non-overlapping matches inside
  that range and is required if the part occurs there more than once.
- Parts must be nonempty, in order and nonoverlapping (`part[i].end ≤ part[i+1].start`), the first
  must start at `s` and the last must end at `e`, and every code point between consecutive parts
  must be a permitted split omission: U+0020, U+0009, LF, or CR immediately followed by LF
  (`anchor_parts_gap`). So no substantive text is ever discarded.
- Each part must map to at least one containing chunk by the single-quote rule
  (`anchor_part_unmapped`); the anchor maps to the union of all parts' containing chunks.
- `parts` on a quote that some single chunk already contains is rejected
  (`anchor_parts_unnecessary`), so annotations are used only where required.

**What fails and what does not:** missing text → `anchor_not_found`; repeated text without an
occurrence → `anchor_ambiguous`; an occurrence beyond the matches →
`anchor_occurrence_out_of_range`; source-contiguous text spanning a chunk boundary without parts →
`anchor_crosses_chunk_boundary`; the same text with a valid `parts` annotation → mapped. A quote
that would join a repeated header to a non-adjacent body exists only in chunk `text`, never
contiguously in the source, so matching against the source rejects it as `anchor_not_found`.

**Mapping output** [REC], per anchor, sorted by chunk UUID, part index and route:

```text
MappingEntry(chunk_id, part_index | None, route ∈ {"body", "header"}, char_start, char_end)
```

`char_start`/`char_end` are the source range matched (the parent range, or the part's range).
One anchor may therefore map through a body in one chunk and through repeated headers in others.
The anchor's chunk set is the deduplicated set of entry chunk IDs. At most 64 entries per anchor
(`anchor_mapping_too_large`).

**Gold, forbidden and epochs** [REC]: for each evaluated (question, epoch), G is the deduplicated
union of the case's `gold` anchors' chunk sets, and must be contained in the chunks of the epoch
snapshot's bindings (`gold_not_in_snapshot`); empty G is allowed. `forbidden` anchors are resolved
against **their own revisions, wherever they are** (superseded r1, a later r2, another vendor or
tenant), after the complete corpus has loaded, and are **never** filtered by the snapshot, so the
traps remain. A chunk in both a case's G and its forbidden set is `gold_forbidden_conflict`.
Resolving a future revision's forbidden reference after loading does not move the `initial`
capture, which was already taken in phase 5. Mapping never consults retrieval results.

##### D. Retrieval evaluation and Recall

[SETTLED] E7, E8: Recall is report-only; no minimum threshold.

[REC] For each variant, tenant × vendor, epoch and evaluated question: `search_snapshot` with the
retained snapshot of that epoch, `RetrievalRequest(question.search_queries, k=8)` and
`HashingEmbedder` (profile `HASH_IDENTITY`, labelled "lexical-hash baseline — not semantic").
`top_8` is the result's chunk IDs in fused-rank order and `top_5` its first five; a test also
checks that a k = 5 request returns the same five. The production ranking is used unchanged.

- **Contract checks** (contract errors, not metrics): duplicate IDs; fused ranks not `1…n`;
  `n > k`; an item outside the snapshot bindings; a result whose snapshot digest, profile or
  configuration differs from the evaluated snapshot. The production `RetrievalResult` constructor
  already rejects duplicates, bad ranks and foreign bindings, so these checks are defensive: they
  run on the raw extracted ranked IDs and metadata, and their pure tests feed synthetic sequences.
- **Isolation checks:** no returned chunk is in the case's forbidden chunk set, belongs to another
  vendor or tenant, or has evidence text containing another tenant's canary string.
- **Question validity** [REC]: a question with **any** contract or isolation failure is
  `invalid`; its Recall is not computed (both values `null`) and its ranked output is reported as
  observed, never deduplicated or repaired. A valid question is `ok` (nonempty G) or
  `ok_empty_gold` (G = ∅, Recall N/A, `null`).
- **Recall** (valid questions only): `None` (N/A) for empty G, else
  `Fraction(|set(ranked[:k]) ∩ G|, |G|)`; fewer than k results never change the denominator.
  Macro mean is the `Fraction` mean over `ok` questions, `None` when there are none; the
  accepted excluded (empty-gold) count is reported as `valid_empty_gold`. **If any question of a
  group is `invalid`, the group is `failed` and both macro values are `null`.**
- **No threshold:** contracts and isolation are asserted; measured Recall is reported only.
  Offline hashing gives no semantic-quality claim.

Unit examples (pure): G = {a, b, c}, top-5 [a, x, b, y, z] → 2/3; two anchors on chunk a → G =
{a}, [a] → 1; an unresolvable anchor → `anchor_not_found` before retrieval; [a, a] →
`duplicate_retrieval_id`; G = ∅ → N/A; all-empty suite → macro N/A with excluded = n (never 1);
G = {a, b}, k = 5, [a] → 1/2; macro of {1, 1/2, N/A} → 3/4 with one valid empty-gold
question; a group with {1, invalid} → status `failed`, macro `null`, counts (2 questions, 1 valid
nonempty-gold, 0 valid empty-gold, 1 invalid).

##### E. Reproducibility and determinism

[REC] What is and is not deterministic, given the production identifiers:

- Vendor, document and revision IDs are UUID4; chunk IDs derive from those revision IDs; snapshot
  digests include `captured_at`; ranking breaks ties by chunk UUID. Therefore **two fresh database
  loads need not produce identical IDs, snapshot digests, tie-broken ranks or Recall values**,
  and no cross-load byte or exact-metric equality is promised. Chunk manifests also embed chunk
  IDs, so they differ across loads too.
- **Repeated evaluation** with the same stored corpus, retained snapshot values, profile, queries
  and database behaviour is expected to be deterministic.
- **Canonical serialization** means only that identical validated report values encode to
  identical bytes. The report has no top-level timestamp, but `snapshot_sha256` already encodes
  each capture time.
- Logical references (tenant/vendor/document@rn, anchor references) accompany actual IDs in the
  report for human comparison; this does not make tied rankings reproducible across loads.
- Nothing here changes production UUID generation, capture time, tie-breaking or snapshot
  contracts. Any future regression baseline (E7) must define its stable inputs and permitted
  variability; CI observation alone does not justify exact Recall pins across fresh random-ID
  loads.

##### F. Report, corpus digest, failures and placement

[SETTLED] E3, E9, E10: pure modules in `evidenceguard_retrieval.evaluation`, orchestration in
`evidenceguard_worker.evaluation`; a narrow installed-wheel check; a synthetic long-table mapping
fixture.

| File (planned) | Contents | Imports |
|---|---|---|
| `packages/retrieval/evidenceguard_retrieval/evaluation/corpus.py` | `eg-corpus-v1` and `eg-ground-truth-v1` values parsed from bytes with `tomllib`, references, validation, variant diff | domain, stdlib |
| `packages/retrieval/evidenceguard_retrieval/evaluation/anchors.py` | Quote location, parts, containment, `MappingEntry`, manifest checks | domain, retrieval, stdlib |
| `packages/retrieval/evidenceguard_retrieval/evaluation/recall.py` | Recall, macro mean, contract and isolation checks, report values, canonical JSON, corpus digest over supplied `(path, bytes)` pairs | domain, stdlib |
| `apps/worker/evidenceguard_worker/evaluation.py` | File reading with size, symlink and containment checks; `run_fresh_two_epoch`, `verify_loaded`, `evaluate` | domain, persistence, retrieval, stdlib |

The pure modules receive bytes or validated values only; all file-system access stays in the
worker module and tests, preserving the retrieval package's no-`os` boundary.

**Corpus digest** [REC] `eg-corpus-digest-v1`: SHA-256 over the ASCII line
`eg-corpus-digest-v1\n`, then the framed variant name, then, for each file of the **selected
variant's effective file set** sorted by normalized relative POSIX path (UTF-8 bytes, bytewise
order), the framed path followed by the framed exact file bytes. A frame is an 8-byte unsigned
big-endian length followed by the bytes. The effective set is `corpus.toml`, every
`ground_truth/*.toml` and the variant's documents (for `injected`, the replaced files are the
`variants/injected/…` files, recorded under their actual paths). Nothing else, including any
report, is hashed.

**Report** [SETTLED N7 as corrected; failure fields REC] `eg-retrieval-eval-v1`: JSON with
`sort_keys=True`, `separators=(",", ":")`, `ensure_ascii=True`, `allow_nan=False`; no other
fields are emitted. Exactly these fields (✓ always present and non-null; **N** may be `null`):

| Level | Field | Value |
|---|---|---|
| top | `schema` ✓, `variant` ✓, `corpus_digest` ✓, `chunker_version` ✓, `stamp` ✓ | strings; `stamp` = "NOT a quality measurement of semantic retrieval" |
| top | `config_sha256` ✓, `profile` ✓ | the evaluated snapshots' configuration digest (must equal `RETRIEVAL_CONFIG_V1`'s) and identity (`provider_id`, `model_id`, `algorithm_version`, `dims`, `fingerprint`, `label`); evaluated snapshots that disagree are an `EvaluationError` (`profile_mismatch`) before any report |
| top | `status` ✓ | `ok`, or `failed` if any group failed |
| top | `contract_failures` ✓, `isolation_failures` ✓ | lists (possibly empty) of failure entries |
| group | `tenant` ✓, `vendor` ✓, `epoch` ✓, `snapshot_sha256` ✓, `status` ✓ | `status` is `ok` or `failed` |
| group | `counts` ✓ | `questions`, `valid_nonempty_gold`, `valid_empty_gold`, `invalid` (integers) |
| group | `macro` ✓ | `recall_at_5` **N**, `recall_at_8` **N**: `null` when the group failed or has no valid nonempty-gold question |
| question | `id` ✓, `outcome` ✓, `failure_codes` ✓, `gold_count` ✓ | `outcome` ∈ `ok`, `ok_empty_gold`, `invalid`; `failure_codes` sorted, empty unless invalid |
| question | `ranked` ✓ | the observed result order, not repaired: entries `{position, chunk_id, ref}` with `ref` **N** (`null` when the chunk is not in the loaded corpus map) |
| question | `recall_at_5` **N**, `recall_at_8` **N** | `null` for `ok_empty_gold` (N/A) and for `invalid` (not computed); `outcome` distinguishes them |

Groups are sorted by tenant, vendor and epoch; questions by id. A failure entry is `{code, tenant,
vendor, epoch, question, chunk_id, position}` with `chunk_id` and `position` **N** (`null` when the
violation concerns the whole result, such as a configuration mismatch). An exact value is
`{"numerator": 2, "denominator": 3, "display": "0.6667"}` in lowest terms; N/A and not-computed are
`null`. `display` is the exact fraction rounded to four decimal places with round-half-to-even,
formatted with exactly four decimals; it is never used in arithmetic. **Only validated safe
identifiers** appear anywhere in the report and its diagnostics: corpus slugs and keys, epochs,
question IDs, fixed codes, canonical UUID strings and integers; never document, quote or query
text, evidence text or object representations.

**Failure semantics** [SETTLED N8 as corrected; details REC]:

- **Inspectable violations** (contract and isolation failures) never raise during evaluation: the
  complete report is built with the affected questions `invalid`, their groups `failed` and the
  top-level `status` `failed`. `require_passing(report)` then raises `EvaluationError`
  (`evaluation_failed`, with the failure counts) whenever the top-level status is `failed`,
  **regardless of other groups' or questions' Recall**. Tests call both, so a failing run still
  yields its report.
- **Operational failures** raise a fixed `EvaluationError` and produce **no** report: validation,
  freshness, loading and mapping errors, and any error raised by the retrieval seams themselves
  (the fixed M4d errors, including `RetrievalDatabaseError`, `RetrievalProviderError` and
  `SnapshotInconsistentError`, are mapped to `retrieval_failed` plus their fixed code).
- Ordinary exceptions from production seams are converted to fixed codes outside the handler,
  retaining no message, cause, context, statement or content; no raw database exception is exposed.
  `BaseException` process control propagates unconverted. Nothing logs document or query text.
  Measured Recall values never fail a run.

##### G. Tests and CI (planned, not run)

**Database-independent** (`tests/test_evaluation_corpus.py`, `tests/test_evaluation_anchors.py`,
`tests/test_evaluation_recall.py`): exact schemas and unknown-key rejection; bounds checked before
reading; path traversal, symlink components, non-regular files and unexpected files; the committed
corpus validates; duplicate local anchor names across tenants accepted only through full
references; cross-tenant references allowed only in `forbidden`; unknown references; gold in a
non-eligible epoch; contradictory gold/forbidden sets; epoch-specific cases and labels; every
committed anchor resolving against `chunk_revision`; the synthetic long table mapping one header
quote through `header` routes and the original chunk's `body` route; missing, ambiguous,
boundary-crossing and header-concatenation quotes; valid parts, gaps containing substantive text,
overlapping or out-of-order parts, part occurrence inside the parent, unnecessary parts; quote and
occurrence rules: empty quotes, non-string quotes, zero, negative, `bool` and non-integer
occurrences, unknown anchor or part keys, unpaired surrogates, NUL and other control characters,
CR, leading or trailing whitespace, 4,000 and 4,001 code points, multiline body and table quotes
with exact offsets, case and Unicode-normalization differences that must not match, repeated text
without an occurrence, an out-of-range occurrence, and a part occurrence counted only inside its
parent; the clean/injected single-paragraph diff; the corpus digest framing (changing a path, a
byte or the variant changes it; equal inputs give equal bytes); all Recall examples; canonical
encoding of one report value and the four-decimal display; failure reports: duplicate result IDs,
a forbidden result, a foreign chunk and an unknown chunk (`ref` `null`), a snapshot, profile or
configuration mismatch, each making its question `invalid` with `null` Recall and its group
`failed` with `null` macro; a valid empty-gold question (`ok_empty_gold`, `null`) distinguished
from an invalid one; the four group counts; `require_passing` failing even when every other
question has Recall 1; message and report privacy.

**PostgreSQL** (`tests/test_evaluation_postgres.py`, integration-marked, guarded fixtures, a fresh
database per variant):

- the fresh run on the clean corpus: statuses, supersession order, ready indexes and manifests;
  the `initial` capture happens while every r1 is active and before any r2 exists (asserted from
  the retained bindings and revision rows), and `final` after every replacement is ready;
- evaluation: the retained `initial` snapshots, after r2 activation, still return only r1
  revisions; `final` retrieval returns r2 and never r1; contract and isolation checks pass; k = 5
  prefix equality; the report is well formed (Recall values are not asserted);
- repeated retrieval from the same retained snapshots gives identical ranked IDs;
- `verify_loaded` on the complete database: succeeds with every superseded r1 accepted;
  performs no writes (every corpus-table row and job compared before and after, and the read runs
  in the `READ ONLY` transaction); captures and reports no `initial` epoch;
- `verify_loaded` refusals, each leaving every row unchanged: an empty database (no tenants); seeded
  tenants only (no vendors); a run stopped after phase 4 (r2 revisions missing); a run stopped
  after an r1 ingestion job was enqueued but before the worker ran (unsettled revision, pending
  job); a run stopped before indexing (no ready index); a manifest with a changed document title or
  revision content (`corpus_conflict`); an extra document in a corpus tenant
  (`corpus_state_unexpected`); an **extra embedding profile** in a corpus tenant
  (`corpus_state_unexpected`), created only through the existing legitimate
  `embeddings.ensure_profile` seam for a second test identity. The empty and seeded-only states
  are refused because the corpus is incomplete. Partial states are produced only by stopping the
  orchestrator through a test-owned phase hook, or by the legitimate seams named here, never by
  direct DML on terminal rows;
- the fresh run **accepting** an empty database and a seeded-only database (tenants and users only,
  the valid fresh starting states), and **refusing** (`corpus_state_not_fresh`, writing nothing)
  every partially loaded or conflicting state: existing corpus-tenant vendors, documents,
  revisions, embedding profiles, embedding indexes or `ingest_revision`/`index_revision` jobs,
  including the stopped-phase states above and the extra-profile state;
- production-seam reuse on the complete corpus (`seed_demo`, `create_upload`,
  `enqueue_index_revision`): no added or changed rows or jobs;
- the injected variant in a freshly reset database, evaluated separately;
- two independent fresh loads of the same variant, asserting only structural equality (logical
  references, gold counts, group shapes), **not** equality of IDs, digests, ranks or Recall.

**CI:** the new tests run in the existing verify and integration jobs. E9 adds one narrow
installed-wheel step importing the three pure modules from `site-packages` and computing the 2/3
example. No new dependency, lockfile, Docker, Compose or container-smoke change.

**Intended files (later implementation):** the modules above (with `evaluation/__init__.py`);
`sample_data/` as laid out; the four test files; `tests/test_packaging.py` for the new boundaries;
`pyproject.toml` (sdist include only); `.github/workflows/ci.yml` (E9 only); ADR-0017; README,
plan, threat model and prompts.md.

##### M4e settled review decisions (Prompts 141 and 142)

[SETTLED] In Prompt 141 the reviewer approved each Prompt 140 recommendation, subject to the
Prompt 141 corrections above: **E1** TOML parsed with the standard library; **E2** ground-truth-only anchors;
**E3** pure evaluation modules in retrieval, orchestration in the worker; **E4** tests as the only
entry point in M4e; **E5** corpus in the sdist, not the wheel; **E6** `initial` and `final`
snapshot epochs; **E7** report-only Recall, any later regression pinning needing separate review;
**E8** no minimum Recall threshold; **E9** a narrow installed-wheel check; **E10** a synthetic
long-table mapping fixture; **E11** a fresh disposable database per variant.

In Prompt 142 the reviewer approved N1–N9, subject to the Prompt 142 corrections above: **N1** the
canonical tenant-qualified reference `tenant/vendor/document@rN#anchor`, foreign-tenant references
only in `forbidden`; **N2** per-question `cases` with disjoint `epochs` and `r1`/highest-`n` gold
eligibility; **N3** separate contracts, now a writing fresh run, a **genuinely read-only**
verifier and a read-only evaluation; **N4** the vendor list/create/re-read strategy (used only by
the fresh run); **N5** the `parts` rules and per-entry `MappingEntry` provenance; **N6** the
`eg-corpus-digest-v1` framing and effective file set; **N7** the report fields, fraction encoding
and round-half-to-even display, as extended for failures; **N8** failure semantics, as refined into
inspectable violations and operational errors; **N9** bounds, pre-read size checks and symlink and
unexpected-file rejection. These settle the choices, not the complete specification.

##### M4e decisions settled at acceptance (Prompt 143)

[SETTLED] Introduced by the Prompt 142 corrections and accepted in Prompt 143 with the two final
clarifications (the starting-state test matrix, and the verifier reading every `embedding_profiles`
row of each corpus tenant):

- **N10** the read-only verifier: one `read_snapshot` transaction, the listed read statements in
  the worker module, corpus-tenant-wide extra-state rejection (vendors, documents, revisions,
  profiles, indexes and corpus job kinds; not users or API keys), and fixed refusals that leave the
  database unchanged; every embedding profile of a corpus tenant enumerated and compared with the
  exact `HASH_IDENTITY` profile; production-seam reuse demonstrated only by a separate test on a
  complete corpus;
- **N11** the quote and occurrence rules: exact types, 1–4,000 code points, no NUL, CR or other
  control characters except TAB and LF, LF-only corpus documents, no leading or trailing
  whitespace, multiline quotes allowed with exact offsets, non-overlapping left-to-right counting,
  parent-relative part occurrences and distinct `not_found`, `ambiguous` and
  `occurrence_out_of_range` outcomes;
- **N12** the failure-report contract: question outcomes `ok`, `ok_empty_gold` and `invalid`;
  `null` Recall for both N/A and not-computed, told apart by `outcome`; the four group counts; group
  and top-level `failed` status with `null` macro; observed ranked output with nullable `ref`;
  nullable failure-entry fields; and operational retrieval errors raising without a report.

**Planned verification (not run):** the tests above, Ruff, strict mypy, both builds, the existing
installed-wheel checks plus E9, the integration job and Gitleaks. The container smoke is unchanged
and continues to cover ingestion, indexing and idle-worker shutdown only.

**Historical correction acceptance (Prompt 150):** the external reviewer accepted Claude Code's Prompt 149
test-only correction for a local commit after inspecting the export and independently matching
its size and checksum. The reviewer's isolated standard-library Linux probe confirmed no
`Path.resolve()` recursion, the target's 10-byte understatement with all other `st_*` fields
preserved, unchanged non-target stat and real file size, and that the target override ran.
It did not execute the project test, suite, reader, wheel or database. At Prompt 150, corrected
Linux project tests, Ubuntu build/wheel and green current-version CI were pending; these
subsequently passed at `d1dcdfce` (see [feature-branch CI evidence](decisions/0017-retrieval-evaluation.md#feature-branch-ci-evidence-at-d1dcdfce)).
Claude Code's Prompt 149 Windows checks remain historical; OpenAI Codex assisted with Prompt
150 documentation/commit work and Prompt 151 publication/log retrieval. The external reviewer
independently confirmed the new logs without running local project checks. At that point M4e was verified in feature-branch CI on `feat/retrieval-evaluation` at `d1dcdfce`
and not yet merged (historical); it is now reviewed, verified in CI and on `main` at `0ae4c6ca` ([main CI evidence](decisions/0017-retrieval-evaluation.md#main-ci-evidence-at-0ae4c6ca)). Prompt 150 authorized only a local
correction commit. M4f and overall M4 acceptance remain pending; local Compose is unverified.

##### M4e local verification (Prompt 146)

Historical local evidence, attributed to Claude Code and not rerun for the Prompt 147
acceptance. Run locally on Windows by Claude Code after the Prompt 146 correction (locked environment; no
Docker, database or external provider contact; only the offline `HashingEmbedder` ran). **Not
run at the time:** all 16 PostgreSQL tests, the symlink refusal test, every CI job for the current tree and
Gitleaks in CI; no database-derived Recall or isolation result existed.

- `ruff format --check .` (171 files) and `ruff check .`: clean; strict `mypy` (135 source
  files): no issues;
- focused tests (the four database-independent M4e files and `tests/test_packaging.py`): 256
  passed, 1 skipped (the symlink test);
- full suite: 2244 passed, 308 skipped (306 integration tests without a database, the symlink
  test and the POSIX-only signal test); collection: 2552 tests, 306 integration;
- regression comparison against the saved Prompt 145 worker module: 12 of the 19 new
  clock-result cases failed before and all 19 pass after (see ADR-0017);
- `uv build` and the isolated installed-wheel environment passed every CI wheel command
  extracted from `ci.yml`, plus a narrow probe of clock-result process control followed by
  ordinary cleanup failure.

##### M4e local verification (Prompt 145)

Historical (before the Prompt 146 correction). Run locally on Windows by Claude Code after the Prompt 145 corrections (locked environment; no
Docker, database or external provider contact; only the offline `HashingEmbedder` ran). **Not
run at the time:** all 16 PostgreSQL tests, the symlink refusal test, every CI job for the current tree and
Gitleaks in CI; no database-derived Recall or isolation result existed.

- `ruff format --check .` (171 files: 135 Python and 36 Markdown) and `ruff check .`: clean;
  strict `mypy` (135 source files): no issues;
- focused tests (the four database-independent M4e files and `tests/test_packaging.py`): 237
  passed, 1 skipped (the symlink test);
- full suite: 2225 passed, 308 skipped (306 integration tests without a database, the symlink
  test and the existing POSIX-only signal test); collection: 2533 tests, 306 integration;
- regression comparison against the saved Prompt 144 modules: 37 of the new worker-boundary
  cases failed before and pass after (see ADR-0017 for the classification of the rest);
- `uv build` and the isolated installed-wheel environment passed every CI wheel command
  extracted from `ci.yml`, plus a narrow probe of the corrected validation and read boundary.

##### M4e local verification (Prompt 144)

Historical (before the Prompt 145 corrections). Run locally on Windows by Claude Code on `feat/retrieval-evaluation` (locked environment; no
Docker, database or external provider contact; only the offline `HashingEmbedder` ran). The
implementation is staged for external review and uncommitted. **Not run:** every PostgreSQL
test (16 cases in `tests/test_evaluation_postgres.py`), the CI jobs and Gitleaks in CI.

- `ruff format --check .` (170 files: 134 Python and 36 Markdown) and `ruff check .`: clean; strict `mypy` (134 source
  files): no issues;
- focused tests (the three database-independent M4e files and `tests/test_packaging.py`): 147
  passed, 1 skipped (the symlink test; this Windows account cannot create symbolic links);
- full suite: 2135 passed, 308 skipped (306 integration tests without a database, the symlink
  test and the existing POSIX-only signal test); collection: 2443 tests, 306 integration;
- `uv build`: the sdist contains the 16 `sample_data` files, the wheel none; an isolated
  installed-wheel environment outside the checkout (dependencies from `uv.lock`, offline with
  `--require-hashes`, wheel with `--no-deps`) passed every CI wheel command extracted from
  `ci.yml`, including the new M4e step.

#### M4f Voyage adapter specification (ACCEPTED at review, Prompt 157; implementation pending)

**Status.** **Proposed in Prompt 154, corrected in Prompts 155–156 and accepted at external
review in Prompt 157** with one final consistency clarification (an ordinary adapter-owned
cleanup failure is ignored under D1 even when its cause or context holds process control, while
an ordinary exception escaping an operation such as `getresponse()` or `read()` is classified
by its own type; see D1). **V1–V15 and N1–N13 are settled within the complete specification;
the section's recommendations ([REC]) now form the accepted implementation contract, and no
specification decision remains open.** The external reviewer matched all three review exports'
sizes and checksums. Acceptance is a design decision only; at acceptance (Prompt 157,
historical) no M4f implementation existed and no M4f project check had run; source reading and
the reviewer's isolated Python 3.12.14 probes are not implementation evidence.

**Implementation (Prompt 158, corrected in Prompt 159; accepted at external review in Prompt 160;
verified in feature-branch CI at `84eec023` (historical); reviewed, verified in CI and on `main` at
`5acb75e5`, published in Prompt 163).** See the [main CI evidence](decisions/0018-voyage-adapter.md#main-ci-evidence-at-5acb75e5), the
[feature-branch CI evidence](decisions/0018-voyage-adapter.md#feature-branch-ci-evidence-at-84eec023) and
[ADR-0018](decisions/0018-voyage-adapter.md) for the final implementation, the implementation
details requiring review and the checks actually run. In Prompt 159, after the external
reviewer's isolated probes, Claude Code corrected two error-privacy boundaries (transport
`VoyageError` metadata read inside a handler, and TLS-context setup outside any boundary) and
added the lease-loss integration case; the external reviewer accepted the corrected
implementation in Prompt 160 for a local commit only (see ADR-0018 for the reviewer's eight
isolated checks, which are not project-suite execution). At that point Linux and
current-version CI were pending (historical); they have since passed at `84eec023`, with job logs
independently retrieved by the external reviewer. Local Windows
checks passed in both prompts (Ruff, strict mypy, the full database-independent suite, the
build and the isolated installed-wheel commands including the new mocked Voyage command; the
Prompt 158 results are historical). The two PostgreSQL cases in
`tests/test_voyage_postgres.py` were not run locally (no test database); both passed in the
feature-branch PostgreSQL integration job at `84eec023`, their first execution. The accepted M4f code blocks below were
reformatted by Ruff (whitespace and one trailing comma only) because `ruff format --check .`
failed on them; no wording changed. Mocked tests do not verify live API compatibility,
semantic quality, latency, cost or production readiness; live evaluation remains M7.

**Unresolved external API facts are distinct from design decisions:** the [OPEN] items below,
the live compatibility of the strict 200 framing rules (N2), whether Voyage echoes the model
name exactly (V6) and any upstream model-immutability guarantee remain explicitly unverified
and are **not** settled by acceptance; the known retryability gap (V11) must still be resolved
by a separately reviewed change before live indexing.

**Review chronology (historical).** Claude Code wrote it in Prompt 154 and applied the
reviewer's four corrections in Prompt 155 (A: a cooperative elapsed-time budget, not a hard
deadline; B: status before body, with no body read for non-200 responses; C: exact direct-call
validation, configuration bounds and call-count and memory wording; D: a concrete
cleanup-precedence algorithm and qualified privacy scope) and four Python 3.12 transport
clarifications in Prompt 156 (explicit short-body detection; no reliance on the connection
socket after `getresponse()`; process-control preservation scoped to observable adapter-owned
boundaries; a non-200 `VoyageResponse` with a body is malformed). The external review of Prompt
154 approved V1–V9 and V11–V15 subject to the Prompt 155 corrections, and approved V10's
numerical defaults as engineering choices with its timing guarantees corrected; the review of
Prompt 155 approved N1–N9 subject to the Prompt 156 clarifications, with V1–V15 remaining
settled as qualified (see [M4f review decisions](#m4f-review-decisions-settled-at-acceptance-prompt-157)).
At those points (historical) the complete specification still awaited review. The details
introduced by the corrections are listed in
[M4f details introduced by the Prompt 155 corrections](#m4f-details-introduced-by-the-prompt-155-corrections-settled-at-acceptance)
(N1–N9, approved in Prompt 156 with clarifications) and
[M4f details introduced by the Prompt 156 clarifications](#m4f-details-introduced-by-the-prompt-156-clarifications-settled-at-acceptance)
(N10–N13, settled at acceptance in Prompt 157).

At acceptance (Prompt 157, historical) the M4f implementation was pending and untested and
ADR-0018 was deferred; it has since been implemented, accepted and published to `main` at
`5acb75e5` (ADR-0018), and overall M4 was accepted at review in Prompt 165
([assessment](#overall-m4-acceptance-assessment-accepted-at-review-prompt-165)). Nothing here redesigns M4a–M4e. Labels in this section:

- **[DECISION]** already accepted (cited);
- **[FACT]** verified from source on `main` at `0ae4c6ca` in Prompt 154;
- **[EXT]** a current external fact from official Voyage documentation or package metadata,
  retrieved read-only on **2026-10-18** (sources below); no API call was made and no key used;
- **[OPEN]** an external detail the documentation does not settle; it remains unverified and
  is not settled by acceptance;
- **[REC]** a recommendation written in Prompts 154–156, now part of the accepted
  implementation contract; numbers marked as choices are engineering defaults, not
  measurements;
- **[V*n*]** a design choice proposed in Prompt 154; V1–V9 and V11–V15 approved and V10's
  numbers approved in the Prompt 155 review, all settled at acceptance in Prompt 157 (see
  [M4f review decisions](#m4f-review-decisions-settled-at-acceptance-prompt-157));
- **[N*n*]** a detail introduced by the corrections: N1–N9 (Prompt 155) approved in the
  Prompt 156 review subject to its clarifications; N10–N13 (Prompt 156); all settled at
  acceptance in Prompt 157;
- **[PY]** a Python 3.12 standard-library fact, read in Prompt 156 from `Lib/http/client.py` on
  the `3.12` branch of the official CPython repository
  (<https://github.com/python/cpython/blob/3.12/Lib/http/client.py>, retrieved 2026-10-18),
  and consistent with the reviewer's Python 3.12.14 source inspection and two isolated
  in-memory standard-library probes (not project tests).

**Python 3.12 `http.client` facts relied on** [PY]:

- `HTTPResponse.read(amt)` with a declared `Content-Length` returns whatever the socket file
  supplies, decrementing the remaining length; a short body yields fewer bytes and then `b""`,
  **without** raising `IncompleteRead` (the source comments that raising would break
  compatibility). Only the unbounded `read()` path raises `IncompleteRead` for a short body.
  The reviewer's probe observed `b"abc"` and then `b""` for a declared length of five.
- For chunked responses, `read(amt)` decodes the framing and raises `IncompleteRead` on a
  premature end or an unparseable chunk size.
- `HTTPConnection.getresponse()` calls `self.close()` when `response.will_close` is true, and
  `HTTPConnection.close()` sets `self.sock = None`; the response stays readable through its own
  file object.
- If `response.begin()` fails, `getresponse()` closes the connection or the response in its own
  handler and re-raises; an exception raised by that internal close replaces the original
  (the reviewer's probe: `KeyboardInterrupt` from `begin()` was replaced by a `RuntimeError`
  from `close()`).
- `_MAXLINE = 65536` and `_MAXHEADERS = 100`.

**Scope.** A Voyage embedding adapter behind the existing `EmbeddingProvider` contract, a
standard-library HTTPS transport injected into it, fixed profile and request configuration,
bounded calls, fixed private errors and mocked tests. **Out of scope:** any live call, key,
production registration, setting, environment variable, CLI, endpoint, automatic indexing,
reranker (E7), retry orchestration, cancellation integration for retrieval (M5), live quality
or cost evidence (M7).

##### M4f accepted decisions and source facts

- [DECISION] D11: the real embedding provider is an API (Voyage); no local model download
  ([§1](#1-review-decisions)). §5 names Voyage `voyage-4-lite` at 1024 dimensions; Prompt 108
  preserved D7/D11 and §§4–7 and fixed the M4f row: “Voyage adapter behind the same contract,
  injected transport mocked in CI, fixed profile/configuration, bounded calls and safe error
  mapping. No live calls required for M4 acceptance; live quality evidence belongs to M7”
  ([M4 direction](#m4-direction-and-review-decisions)).
- [DECISION] M4a (Prompt 108): a future Voyage identity must pin requested model, dimensions
  and adapter contract version; model aliases cannot establish an upstream immutable model
  revision; record any provider-returned model identity and fail on unexpected mismatch. A live
  adapter rejects zero vectors. Fixed error codes carry no input text, vectors, provider
  response or exception body. No implicit truncation or splitting.
- [FACT] `evidenceguard_domain.embeddings`: `EmbeddingIdentity(provider_id, model_id,
  algorithm_version, dims, normalization)`; identifiers match `[a-z][a-z0-9._-]{0,63}`; the
  fingerprint is SHA-256 of canonical JSON of exactly those five fields. `validate_request`
  allows 1–32 texts, each 1–4,000 code points, at most 16,000 UTF-8 bytes, no NUL, not
  whitespace-only, at most 128,000 bytes in total. `EmbeddingBatch` requires a tuple of
  `dims`-length tuples of strict `int`/`float` coordinates, finite `math.hypot` norm, and norm
  within absolute 1e-6 of 1, with zero vectors only when `provider_id == "offline"`.
  `EmbeddingUsage(input_tokens)` is a nonnegative strict int or `None`. Errors are the single
  fixed `InvalidEmbeddingError("invalid_embedding")`.
- [FACT] `evidenceguard_retrieval.embeddings.embed_validated` validates the request, reads the
  provider identity, calls `embed`, validates the result and converts **every** `Exception` to
  a fresh `InvalidEmbeddingError` raised outside the handler; non-`Exception` process control
  propagates.
- [FACT] `evidenceguard_domain.embedding_storage`: `STORED_DIMS = 1024`; `canonical_vector`
  rounds to float32, rejects a nonzero vector that rounds to zero and rechecks the norm without
  renormalizing; `allows_zero_vectors` is true only for `offline`. Migration `0005` checks
  `dims = 1024` and `allows_zero_vectors = (provider_id = 'offline')` in the database.
- [FACT] M4c (`evidenceguard_worker.indexing`): providers come from an immutable
  fingerprint → factory mapping fixed when the handler is built; production
  `SUPPORTED_PROVIDERS` holds only `HASH_IDENTITY`. A page is at most 32 chunks and 128,000
  UTF-8 bytes. `_embed` runs `ctx.check()` before the call and before classifying a failure,
  then maps `InvalidEmbeddingError` to `PermanentJobError(permanent_failure)`; only
  `JobLockTimeoutError` is retryable. An unsupported stored profile is a permanent failure.
  `eg-admin backfill-indexes` is fixed to `HASH_IDENTITY`.
- [FACT] M4d (`evidenceguard_worker.retrieval`): `search_snapshot` reads the provider identity,
  makes at most one `embed_validated(..., "query")` call (none if its earlier validation or
  identity check fails) for 1–8 queries with no session open,
  and maps any ordinary failure to the fixed `RetrievalProviderError`
  (`retrieval_provider_failed`), with no retry or `JobContext` integration; M5 must define
  cancellation and lease precedence.
- [FACT] `tests/test_packaging.py` requires `evidenceguard_retrieval` to import only the domain,
  itself and the standard library, and none of `sqlalchemy`, `psycopg`, `httpx`, `socket`,
  `urllib`, `requests` or `os`. `pyproject.toml` has no HTTP client or Voyage dependency; new
  dependencies fall under the two-week age policy (ADR-0004). Settings exist only for the
  database (`EG_DATABASE_URL`, held as `SecretStr`).
- [FACT] Test fixtures already use `EmbeddingIdentity("voyage", "voyage-4-lite", "adapter-v1",
  1024, "l2")` as a non-offline example; that string is a fixture, not an accepted contract.
- [FACT] Plan §8 says “60 s timeout, 2 SDK retries” for provider calls, written for model
  calls before M4; see V15.

##### M4f current Voyage API facts (retrieved 2026-10-18)

Sources (official, read-only): [Embeddings API reference](https://docs.voyageai.com/reference/embeddings-api)
(page `updatedAt` 2025-12-10), [Text embeddings](https://docs.voyageai.com/docs/embeddings)
(2026-08-10), [Error codes](https://docs.voyageai.com/docs/error-codes) (2025-09-12),
[Rate limits](https://docs.voyageai.com/docs/rate-limits) (2026-08-26),
[FAQ](https://docs.voyageai.com/docs/faq) (2026-08-03),
[Tokenization](https://docs.voyageai.com/docs/tokenization) (2026-01-05) and the
[`voyageai` PyPI metadata](https://pypi.org/pypi/voyageai/json).

- [EXT] `POST https://api.voyageai.com/v1/embeddings`, `Authorization: Bearer <key>`,
  `Content-Type: application/json`.
- [EXT] Request: `input` (string or list, at most 1,000 items; per-request token limit 1M for
  `voyage-4-lite`), `model` (required), `input_type` (`null`, `query` or `document`; `query`
  and `document` prepend a documented retrieval prompt), `truncation` (default `true`; `false`
  makes an over-length input an error), `output_dimension` (`voyage-4-lite`: 256, 512, 1024
  default, 2048), `output_dtype` (default `float`, 32-bit floats), `encoding_format` (`null`
  for number arrays, or `base64`).
- [EXT] Response 200: `{"object": "list", "data": [{"object": "embedding", "embedding": [...],
  "index": n}], "model": "...", "usage": {"total_tokens": n}}`; `index` is the position in the
  input list. 4XX bodies carry a `detail` string.
- [EXT] `voyage-4-lite` is listed as a current model with a 32,000-token context length and a
  1024 default dimension. The pages state no alias, version-pinning or immutability guarantee
  for model names; `voyage-4-lite` is therefore only a **requested model identifier**.
- [EXT] The FAQ states that Voyage embeddings are normalized to length 1; no numeric tolerance
  is stated.
- [EXT] Errors: 400 invalid request (malformed body, bad parameter, batch or token limit,
  context length), 401 invalid authentication, 403 possibly blocked IP, 429 rate limit (pace
  requests), 500 server error (retry after a brief wait), 502/503/504 heavy traffic (retry after
  a brief wait). No backoff schedule or retry count is specified there; the rate-limit page
  suggests exponential backoff with jitter. No rate-limit response header is documented.
- [EXT] Tier 1 limits for `voyage-4-lite`: 16M tokens and 2,000 requests per minute.
- [EXT] Tokenization happens server-side; the docs estimate about 5 characters per token and
  offer counting through the SDK or a Hugging Face tokenizer.
- [EXT] `voyageai` 0.5.0 (uploaded 2026-07-10, MIT, Python >=3.9,<3.15) requires `requests`,
  `aiohttp`, `tenacity`, `numpy`, `aiolimiter`, `pillow`, `pydantic`, `tokenizers` and
  `langchain-text-splitters`.
- [OPEN] Not settled by the documentation: whether the response `model` echoes the requested
  name exactly; whether `data` is always in input order (only `index` is documented); whether
  a zero vector can ever be returned; whether float32 values serialized to JSON keep every
  normalized vector within 1e-6 of unit norm after the storage contract's float32 rounding;
  determinism across calls; the error body beyond `detail`; `Retry-After` or rate-limit
  headers; status codes other than those listed (for example 404 or 413); the per-text context
  length on the API reference page (only the models page states it); and the inconsistency
  between the two pages' model lists (`voyage-code-3` versus `voyage-code-4`), which does not
  affect `voyage-4-lite`. Prices were not re-verified and are not needed for M4f.

##### M4f A. Placement and public contract

[REC] Two new modules and no framework.

**`packages/retrieval/evidenceguard_retrieval/voyage.py`** (pure; standard library and
`evidenceguard_domain.embeddings` only; no `os`, `socket`, `ssl`, `http`, `urllib`, file or
environment access, so the existing retrieval import test holds unchanged):

```python
VOYAGE_IDENTITY = EmbeddingIdentity("voyage", "voyage-4-lite", "voyage-http-v1", 1024, "l2")
VOYAGE_HOST = "api.voyageai.com"  # used only by the transport
VOYAGE_PATH = "/v1/embeddings"
MAX_REQUEST_BYTES = 1_048_576  # choice
MAX_RESPONSE_BYTES = 4_194_304  # choice


class VoyageErrorCode(StrEnum): ...  # fixed codes, see D


class VoyageError(Exception):  # message is the code; never values or causes
    code: VoyageErrorCode

    @property
    def retryable(self) -> bool: ...


@dataclass(frozen=True, init=False, repr=False)
class VoyageResponse:  # validated in __init__; repr shows the status only
    status: int  # exact int (not bool), 100-599
    body: bytes  # exact bytes; always b"" unless status == 200


class VoyageTransport(Protocol):
    def post(self, body: bytes) -> VoyageResponse: ...  # status-only value for non-200


def build_request_body(texts: tuple[str, ...], input_type: InputType) -> bytes: ...
def parse_response(
    response: VoyageResponse, *, input_type: InputType, count: int
) -> EmbeddingBatch: ...


@dataclass(frozen=True, repr=False)
class VoyageEmbedder:  # satisfies EmbeddingProvider
    transport: VoyageTransport

    @property
    def identity(self) -> EmbeddingIdentity: ...  # always VOYAGE_IDENTITY
    def embed(self, texts: tuple[str, ...], input_type: InputType) -> EmbeddingBatch: ...

    # __repr__ -> "VoyageEmbedder()"
```

`embed` runs `validate_request` first and builds and checks the body; an invalid request makes
**zero** transport calls. Once validation succeeds and the transport is reached, **at most one**
`transport.post` call occurs, whatever its outcome; the response is then validated and parsed.
The adapter never sees the key, headers, host or timeouts. Direct calls to the public helpers
and constructors are validated exactly as specified in
[M4f C2](#m4f-c2-direct-call-and-configuration-validation-prompt-155-correction-c); type
annotations are not relied on.

**`apps/worker/evidenceguard_worker/voyage_http.py`** (the only module that touches the
network; standard library `http.client`, `ssl`, `socket`, `time`, plus `pydantic.SecretStr`
and the retrieval module; no `os` or environment read):

```python
ConnectionFactory = Callable[[str, float, ssl.SSLContext], http.client.HTTPSConnection]
# called as factory(VOYAGE_HOST, timeout, context); must not connect by itself


class HttpsVoyageTransport:  # satisfies VoyageTransport; repr masks the key
    def __init__(
        self,
        api_key: SecretStr,
        *,
        connect_timeout: float = 10.0,
        io_timeout: float = 30.0,
        elapsed_budget: float = 60.0,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
        connection_factory: ConnectionFactory = _https_connection,
        clock: Callable[[], float] = time.monotonic,
    ) -> None: ...
    def post(self, body: bytes) -> VoyageResponse: ...
```

`connect_timeout` is the socket timeout for connection and TLS setup, `io_timeout` the socket
timeout applied to each individual blocking send or receive wait (not to a complete
`HTTPResponse.read()` call), and `elapsed_budget` the cooperative elapsed-time budget of
[M4f C1](#m4f-c1-cooperative-timing-budget-prompt-155-correction-a); none of them is a hard
deadline.

Placing the transport in the worker keeps `evidenceguard_retrieval` network-free and puts it
beside its consumers (M4c indexing, M4d retrieval and later M5); see V3.

**Configuration and fingerprint.** The fingerprint is unchanged M4a code over the five
identity fields:

| Field | Value | In fingerprint |
|---|---|---|
| `provider_id` | `voyage` | yes |
| `model_id` | `voyage-4-lite` (requested identifier; no immutability claimed) | yes |
| `algorithm_version` | `voyage-http-v1` | yes |
| `dims` | `1024` (also `output_dimension`; the stored column is fixed at 1024) | yes |
| `normalization` | `l2` | yes |
| endpoint path, `input_type` mapping, `truncation=false`, `output_dimension=1024`, `output_dtype="float"`, omitted `encoding_format`, request encoding and response validation rules | fixed constants | covered by `algorithm_version`: any change requires a new version and therefore a new profile |
| key, timeouts, elapsed budget, response cap, connection factory, clock (the host and path are fixed constants) | transport arguments | **no**; operational, never stored in profiles, logged or shown |

**SDK versus standard library.** [REC] Standard library (V2). The official SDK would add nine
runtime dependencies [EXT], an internal retry library and its own HTTP stacks, all under the
dependency-age policy, and would make transport injection and error privacy depend on SDK
internals. The standard-library transport needs **no dependency or lockfile change**.

##### M4f B. Transport and protocol

**Request** (none for invalid input; at most one per `embed` otherwise): [REC]

```json
{"input": ["…", "…"], "input_type": "document", "model": "voyage-4-lite",
 "output_dimension": 1024, "output_dtype": "float", "truncation": false}
```

- `input` is always a list (even for one text), in the caller's order, duplicates kept;
  `input_type` is always the caller's `query` or `document`, never `null`.
- Encoded with `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=True,
  allow_nan=False)`, so the bytes are deterministic and pure ASCII; lone surrogates were
  already rejected by `validate_request`. Worst-case escaping (`\u00XX` for control characters)
  is 6 bytes per input byte, so 128,000 input bytes give under 800,000 bytes; the body is
  checked against `MAX_REQUEST_BYTES` anyway (`voyage_configuration` if exceeded, which the
  bounds make unreachable).
- `truncation=false` means an over-length text is a provider 400, never a silently truncated
  embedding. `encoding_format` is omitted (number arrays); base64 is not used.

**HTTP** (transport): `POST /v1/embeddings` on `api.voyageai.com:443` over
`ssl.create_default_context()` (certificate and hostname verification, TLS 1.2 minimum);
headers exactly `Host`, `Authorization: Bearer <key>`, `Content-Type: application/json`,
`Accept: application/json`, `Accept-Encoding: identity` (N1), `Content-Length` and a fixed
`User-Agent: evidenceguard-voyage-http-v1`. No redirect is followed (`http.client` does not),
no decompression is performed, no proxy or environment is consulted, no cookie or connection is
reused across calls, and `http.client` debugging stays at its default level 0 (never
`set_debuglevel`). The connection and response are closed after each call under
[M4f D1](#m4f-d1-cleanup-precedence-prompt-155-correction-d).

**Exchange order (Prompt 155 correction B).** Each step is a timed phase of
[M4f C1](#m4f-c1-cooperative-timing-budget-prompt-155-correction-a):

1. Connection and TLS: `factory(VOYAGE_HOST, timeout, context)` then an explicit `connect()`.
2. Request sending: `request("POST", VOYAGE_PATH, body, headers)`.
3. Response headers: `getresponse()`, which reads the status line and headers.
4. Status: the status is taken from the response object after the headers. **For any status
   other than 200 the transport never calls `response.read()` and never drains the body**; it
   returns `VoyageResponse(status, b"")` (status only), and then closes the response and the
   connection. A non-200 body, an oversized or malformed `Content-Length`, or a failure that a
   body read would have produced therefore cannot replace the status classification, because
   the body is never read. The adapter maps the status to the fixed code in D.
5. 200 only: framing and size metadata are validated (below), then the body is read with the
   bounded loop of [the 200 body read](#200-body-read-prompt-156-clarifications-a-and-b), each
   read a separate timed phase.
6. A final elapsed-time check; only then is `VoyageResponse(200, body)` returned.

**200 framing and size metadata** (N2; checked on the parsed header object that `http.client`
already provides, with no custom HTTP parser). The standard library parses `Content-Length`
leniently (an invalid value becomes "unknown" and only the first header is used), so the
transport reads the raw values with `headers.get_all(...)` itself:

- `Transfer-Encoding`: absent, or exactly one value equal to `chunked` (ASCII
  case-insensitive). Any other value, or `chunked` together with any `Content-Length`, is
  contradictory framing: `voyage_malformed_response`.
- Without `Transfer-Encoding`: exactly one `Content-Length` value of 1–20 ASCII digits.
  Missing (close-delimited body), repeated (even if equal), empty, signed, non-digit or
  otherwise malformed values are `voyage_malformed_response`; a value above
  `max_response_bytes` is `voyage_response_too_large`, refused before reading.
- `Content-Encoding`: absent or exactly `identity`; anything else (for example `gzip`) is
  `voyage_malformed_response`. No decompression is ever attempted.
- A body shorter than its declared length is detected **explicitly** by the read loop below
  (an empty read before the declared length is reached), not by relying on `IncompleteRead`;
  it is `voyage_transport_failed`, and any `IncompleteRead` that is raised maps to the same
  code. More accepted bytes than the cap is `voyage_response_too_large`.
- `Content-Type` is not required or interpreted; the JSON validation below decides.

###### 200 body read (Prompt 156 clarifications A and B)

No chunk parser and no private socket access; `http.client` decodes chunked framing.

```python
total = 0
pieces = []
while True:
    if declared is not None:  # Content-Length framing (validated, <= cap)
        wanted = min(PIECE, declared - total)
        if wanted == 0:
            break  # declared length reached: no further read
    else:  # chunked framing, decoded by http.client
        wanted = min(PIECE, cap + 1 - total)
    check_budget_before()  # C1 step 1; voyage_timeout if exhausted
    sock = connection.sock  # public attribute; may be None after getresponse()
    if sock is not None:
        sock.settimeout(min(io_timeout, remaining()))
    piece = response.read(wanted)  # one bounded read
    check_budget_after()  # C1 step 3
    if type(piece) is not bytes or len(piece) > wanted:
        fail(voyage_transport_failed)  # N11
    if piece == b"":
        if declared is not None:
            fail(voyage_transport_failed)  # early EOF before the declared length
        break  # end of the decoded chunked body
    total += len(piece)
    if total > cap:
        fail(voyage_response_too_large)  # only reachable for chunked framing
    pieces.append(piece)
body = b"".join(pieces)
```

- `PIECE` is 64 KiB (N10). With `Content-Length`, each read requests at most the remaining
  declared length, so no read is issued once the declared length is satisfied; with chunked
  framing, each read requests at most one byte more than the cap allows, so an oversized body
  is detected after at most `cap + 1` decoded bytes.
- The loop cannot spin on empty reads: every iteration either adds at least one byte (bounded
  by the declared length or the cap) or ends at the first `b""`.
- Multiple short nonempty reads are accepted until the exact declared length is supplied.
- An `IncompleteRead` or other ordinary exception from `read()` is `voyage_transport_failed`,
  and a socket timeout `voyage_timeout`, under D1.
- **Socket ownership (B).** `getresponse()` may close the connection and set
  `connection.sock` to `None` when the response will close (for example `Connection: close`),
  while the response remains readable [PY]. The transport therefore never assumes
  `connection.sock` exists after the header phase: it reduces the timeout through the public
  `connection.sock` only when that attribute is not `None` (N12). When it is `None`, the
  transport does not access `response.fp` or any other private socket internal, does not
  reconnect, and does not fail merely because the public socket is absent; the response keeps
  the socket timeout applied before the header phase, while the cooperative elapsed checks
  still run before and after each read.

**Headers versus retained metadata.** `http.client` necessarily parses the status line and
every response header into temporary objects (bounded by its own 65,536-byte line and 100-header
limits). The transport reads only the status, `Transfer-Encoding`, `Content-Length` and
`Content-Encoding` values for the decisions above; it copies no header into `VoyageResponse`,
an error or a log, and the response object is discarded at cleanup.

**Response validation** (`parse_response`, in this order; the first failure wins):

1. Value and status: the complete `VoyageResponse` is revalidated first (exact type,
   reconstructed from its fields; see C2). A non-200 value with a nonempty body is
   `voyage_malformed_response` (N5). Only a valid status-only non-200 value proceeds to the
   status classification in D; only a valid 200 value proceeds to step 2. The real transport
   never reads a non-200 body, so it always supplies `b""` for one.
2. Size: `len(body) <= MAX_RESPONSE_BYTES` (rechecked even though the transport bounds it).
3. JSON: strict UTF-8 decode; `json.loads` with a `parse_constant` that rejects `NaN`,
   `Infinity` and `-Infinity` and an `object_pairs_hook` that rejects duplicate keys; any
   decoder failure, including recursion depth, is `voyage_malformed_response`.
4. Top level: an object with `object == "list"`, `data` a list, `model` a string and `usage` an
   object.
5. Identity: `model` must equal `"voyage-4-lite"` exactly (V6), else
   `voyage_malformed_response`. It is then discarded.
6. Cardinality and order: `len(data)` equals the request count (no missing or extra rows);
   every item is an object with `object == "embedding"`, a strict-int `index` (not `bool`) and
   a list `embedding`; the indexes are exactly `{0, …, count-1}` with no duplicate; vectors are
   placed by `index` (V7). Placing by the documented `index` is not a correction.
7. Coordinates: each `embedding` has exactly 1024 elements, each a strict `int` or `float` (not
   `bool`, string or `None`) and finite (`json` turns `1e400` into infinity, so finiteness is
   checked explicitly). An integer too large to convert to `float` (where `OverflowError`
   would be raised by the finiteness check) is caught as an ordinary failure and is
   `voyage_malformed_response`; a JSON integer longer than Python's integer-string digit limit
   already fails in the decoder (step 3). Vectors become tuples without conversion or rounding.
8. Usage: `usage.total_tokens` must be a strict `int` (not `bool`), 0 ≤ value ≤ 2^63 − 1 (N3),
   and becomes `EmbeddingUsage(input_tokens=total_tokens)`; any other value is
   `voyage_malformed_response`.
9. Construction: `EmbeddingBatch(VOYAGE_IDENTITY, input_type, vectors, usage)` applies the M4a
   rules; an `InvalidEmbeddingError` here (dimension, non-finite norm, norm outside 1e-6 of 1,
   or any zero vector, since `provider_id != "offline"`) becomes `voyage_invalid_vector`.

**Normalization and zero vectors.** [REC] Consistent with M4a and storage: no
renormalization, scaling, rounding or zero substitution anywhere in the adapter. [EXT] Voyage
documents unit-length output; M4a checks it in float64 and `canonical_vector` re-checks it
after float32 rounding. A vector that fails either check is rejected, never corrected
([OPEN]: whether live output always passes is M7 evidence). Zero vectors are always rejected,
by M4a, by storage (`allows_zero=false`) and by the database check.

**Untrusted metadata.** Retained in the returned batch: only `usage.total_tokens` (as
`EmbeddingUsage`) and the validated vectors. Validated then discarded: `object` markers,
`model`, `index`. Unknown keys at the top level and in items (V8) are parsed temporarily by
`json.loads` but are not retained in the returned batch or in any error. Response headers are
parsed temporarily by `http.client` and only the framing values above are inspected; none is
retained. A non-200 body is never read. Nothing from a response appears in a public error,
default representation or log.

##### M4f C. Bounds and resource use

| Bound | Provider documentation [EXT] | Application value |
|---|---|---|
| Texts per call | at most 1,000 | 1–32 ([DECISION] M4a); M4c pages ≤32, M4d 1–8 queries |
| Text size | 32,000-token context for `voyage-4-lite`; tokens counted server-side | ≤4,000 code points and ≤16,000 UTF-8 bytes each ([DECISION] M4a); over-context inputs fail with 400 because `truncation=false` |
| Batch size | 1M tokens per request for `voyage-4-lite` | ≤128,000 UTF-8 bytes ([DECISION] M4a; M4c page prefix the same) |
| Request body | not documented | ≤1 MiB, checked (choice) |
| Response body | not documented | ≤4 MiB (choice): 32 × 1024 JSON floats is roughly 0.8 MB |
| Connect timeout / socket I/O timeout / cooperative elapsed budget | not documented | 10 s / 30 s / 60 s (choices approved in V10; the budget is cooperative, not a hard deadline; see C1) |
| Calls per `embed` | — | 0 for an invalid request; at most 1 once validation succeeds and the transport is reached; no pagination, no splitting, no internal retry (V9) |
| Rate | Tier 1: 16M TPM, 2,000 RPM | no client-side limiter; the worker runs one handler and one call at a time |

- For a 200 response the transport reads the body in pieces of at most 64 KiB and refuses as
  soon as more than `max_response_bytes` would be accepted; a declared `Content-Length` above
  the cap is refused before reading. Non-200 bodies are not read at all (B).
- **Memory.** The cap bounds the **accepted raw response bytes** only. UTF-8 decoding, JSON
  parsing, temporary Python objects (including unknown fields and decoded strings), the
  standard library's own buffers and header objects, and tuple construction all consume
  additional memory. No peak-memory figure is claimed or established; in particular, peak
  memory is not claimed to equal the raw cap plus the final vectors.
- **Timing** is the cooperative budget of C1, not a hard deadline.
- No token counting is done locally (it would need a tokenizer dependency). [REC] The
  application byte bounds make an over-limit request unlikely but are not a documented
  guarantee; any provider limit error is a fixed non-retryable failure, never truncation.
- Indexing calls per attempt are bounded by the existing M4c paging (at most 4,096 chunks per
  revision and at least eight chunks per full page under the 128,000-byte prefix); job attempts
  are bounded by the existing M3a attempt limit. Retrieval makes one call per
  `search_snapshot`.

**Retries.** [REC] **No internal retries** (V9): at most one transport attempt per `embed`.
Durable retry belongs to the M3 job lifecycle, and the cancellation and lease checks run only at
the handler's explicit boundaries, so an adapter that slept and retried inside one call would
delay those checks and multiply provider calls. The error's `retryable` flag records the
classification for callers; it causes no retry by itself.

##### M4f C1. Cooperative timing budget (Prompt 155 correction A)

V10's numbers are approved as engineering choices with this interpretation:

- **Connect timeout 10 s:** the socket timeout during connection and TLS setup.
- **Socket I/O timeout 30 s:** the socket timeout for each individual blocking send or
  receive wait after connection. It is **not** a limit on a complete `getresponse()` or
  `HTTPResponse.read()` call, which may perform many waits internally.
- **Cooperative elapsed-time budget 60 s:** measured with the injected monotonic clock from the
  start of `post`.

Algorithm (no watchdog thread, background worker, custom HTTP parser or new dependency):

1. Record `start = clock()`. Before each controllable blocking phase (connection and TLS,
   request sending, response headers, and each body read), compute
   `remaining = elapsed_budget - (clock() - start)`. If `remaining <= 0`, **do not start the
   phase**; the outcome is `voyage_timeout`.
2. Apply `min(phase timeout, remaining)` as the timeout where the API permits: the factory's
   `timeout` argument for connection and TLS (the connect timeout), then
   `connection.sock.settimeout(...)` on the connected socket before sending and before
   `getresponse()` (the I/O timeout). Before each body read the timeout is reduced again
   **only if the public `connection.sock` is still available**; after `getresponse()` it may be
   `None`, and the read then uses the timeout applied before the header phase (see
   [the 200 body read](#200-body-read-prompt-156-clarifications-a-and-b)). Not every body read
   is guaranteed a newly reduced socket timeout.
3. After each phase returns, recheck elapsed time; if the budget has expired, stop with
   `voyage_timeout` even though the phase itself succeeded (except as in step 4 for a status
   already known to be non-200).
4. Recheck once more immediately before returning a 200 response. **No success is returned
   once the budget has expired.** A status-only non-200 value, once its status is known, is
   still returned after expiry, because it is not a success and needs no further I/O; its
   status classification is kept (N4).
5. A socket timeout (`TimeoutError`, including `socket.timeout`) in any phase is
   `voyage_timeout`. A clock value that is not a finite real number is `voyage_configuration`
   (C2).

**Disclosed limits.** This is a cooperative budget, not a hard wall-clock maximum:

- it cannot interrupt an in-progress standard-library operation;
- DNS resolution, multiple connection attempts (one per resolved address, each with its own
  timeout), TLS handshakes, header parsing and the internal buffered or chunked read loops of
  `getresponse()` and `read()` can run past the budget, for example while a peer sends data
  slowly;
- socket timeouts bound individual blocking waits, not the complete call;
- when `getresponse()` has released the public connection socket, body reads keep the socket
  timeout applied before the header phase, which further limits how closely a body read can
  follow the remaining elapsed budget;
- cleanup (D1) is not given any deadline;
- **no hard wall-clock maximum is established** for a call. A hard deadline would need a
  separately reviewed transport design before any deployment that depends on one.

##### M4f C2. Direct-call and configuration validation (Prompt 155 correction C)

The adapter, its helpers and the transport are public and explicitly constructible, so each
validates its own arguments with exact type checks (`type(x) is ...`, so `bool` never passes as
`int`). The taxonomy stays small: M4a's `InvalidEmbeddingError` for invalid embedding
requests, and the existing `VoyageError` codes for everything else.

| Category | Rule | Outcome |
|---|---|---|
| `embed` and `build_request_body` texts and `input_type` | M4a `validate_request` | `InvalidEmbeddingError`; zero transport calls |
| Encoded body larger than `MAX_REQUEST_BYTES` | checked after encoding | `voyage_configuration`; zero transport calls (unreachable within the M4a bounds) |
| `parse_response` `input_type` | exactly `"query"` or `"document"` | `InvalidEmbeddingError` |
| `parse_response` `count` | exact `int`, 1–32 (`True` and out-of-range values rejected) | `InvalidEmbeddingError` |
| `VoyageResponse(status, body)` construction, and re-validation of any value received | `status`: exact `int`, 100–599; `body`: exact `bytes`; a non-200 status must have `b""` | `voyage_malformed_response` (N5) |
| `parse_response` response argument, or the injected transport's return value | must be exactly a `VoyageResponse`; it is reconstructed from its fields to reject bypassed values | `voyage_malformed_response` |
| JSON decoder failures (`UnicodeDecodeError`, `ValueError`, `RecursionError`, rejected constants or duplicate keys) | step 3 | `voyage_malformed_response` |
| Huge integer coordinates (`OverflowError` in the finiteness check) | step 7 | `voyage_malformed_response` |
| Invalid usage | step 8 | `voyage_malformed_response` |
| `VoyageEmbedder(transport)` | an object with a callable `post` attribute | `voyage_configuration` |
| `api_key` | exactly `pydantic.SecretStr`; its value an exact `str` of 1–256 characters, each visible ASCII (0x21–0x7E) | `voyage_configuration` |
| `connect_timeout`, `io_timeout`, `elapsed_budget` | exact `int` or `float` (not `bool`), finite (no NaN or infinity), 0 < value ≤ 600 (N6) | `voyage_configuration` |
| `max_response_bytes` | exact `int` (not `bool`), 1 ≤ value ≤ `MAX_RESPONSE_BYTES` | `voyage_configuration` |
| `connection_factory`, `clock` | callable | `voyage_configuration` |
| A clock result | exact `int` or `float`, finite | `voyage_configuration` at call time (N7) |
| A connection-factory result or method failing with an ordinary `Exception` | — | `voyage_transport_failed` |

**Precedence inside `embed`:** M4a request validation, then body encoding and its size check,
then at most one `post`, then validation of the returned value, then the status mapping, then
`parse_response` steps 2–9. Transport construction errors arise when the transport is built,
before any call. The first failing step determines the outcome; no later step runs.

##### M4f D. Errors and privacy

[REC] One exception type, `VoyageError(Exception)`. Its message and only argument are the fixed
code string; its only public attributes are the safe `code` (a `VoyageErrorCode`) and
`retryable` (a `bool` derived from the code). It carries no submitted value, header, body,
note, cause or context.

| Code | Raised for | Retryable |
|---|---|---|
| `voyage_configuration` | the configuration and argument rules in C2 (key, timeouts, budget, cap, factory, clock, transport object), an invalid clock result, an oversized request body | no |
| `voyage_authentication` | 401, 403 | no |
| `voyage_request_rejected` | 400 and any other 4XX except 401, 403 and 429 | no |
| `voyage_rate_limited` | 429 | yes |
| `voyage_server_error` | 500, 502, 503, 504 and any other 5XX | yes |
| `voyage_unexpected_status` | any status other than 200, 4XX or 5XX (for example 1XX, 204 or 3XX) | no |
| `voyage_timeout` | a socket timeout in any phase, or the cooperative budget exhausted before a phase or found expired after one (C1) | yes |
| `voyage_transport_failed` | DNS, connection, TLS, reset or protocol failure; a short 200 body detected by the read loop (early `b""`) or an `IncompleteRead`; a read returning a non-`bytes` value or more than requested; another body-read failure; or any other ordinary `Exception` raised by an injected transport, connection or `http.client`, whatever its chain contains | yes |
| `voyage_response_too_large` | a 200 response's declared `Content-Length` or accepted body bytes above the cap, and step 2 of the response validation | no |
| `voyage_malformed_response` | an invalid `VoyageResponse` or transport return value (C2), contradictory or malformed 200 framing or an unsupported `Content-Encoding` (B), and steps 3–8 of the response validation | no |
| `voyage_invalid_vector` | step 9 | no |

- **Privacy.** Public errors are fresh `VoyageError` instances created from a recorded fixed
  code and raised outside every `except` block, so their `__cause__` and `__context__` are
  `None`. A `VoyageError` raised by an injected transport is re-raised **fresh** with the same
  code. Ordinary exception objects are classified by their own type only (never by inspecting
  `__cause__`, `__context__` or chains), kept at most as transient local control-flow state, and
  never attached to a public error. The key, headers, texts, bodies, `detail`, socket or SSL
  messages and exception text are never put into a public error, default representation or
  log; `SecretStr` masks the key in `repr`, and the transport's and adapter's representations
  are fixed strings. Nothing logs, and `http.client` debugging stays disabled.
- **Scope of the privacy guarantee.** It covers ordinary public errors, default
  representations, default formatted tracebacks of those public errors, and logs. It does
  **not** promise secrecy against trusted code that inspects frame locals, the transport's
  held key, or the explicitly held response body of a `VoyageResponse`.
- **Process control.** Only `Exception` is caught for classification. A `KeyboardInterrupt`,
  `SystemExit` or other non-`Exception` `BaseException` **that escapes into adapter-owned code**
  propagates as the **same object** under the first-outcome rule of D1; its original message
  and traceback are preserved as they are and are **not** claimed to be sanitized. This is
  scoped to observable boundaries; see the residual limitation in D1.
- **M4a and M4c boundary (unchanged; incompatibility disclosed, V11).** Through
  `embed_validated`, every `VoyageError` becomes `InvalidEmbeddingError`, so the M4c handler
  records `permanent_failure` for every provider failure, **including rate limits, timeouts and
  server errors**, and the index stalls with no M4c recovery. The retryability classification is
  therefore lost at today's boundary. M4f does not silently change `embed_validated`, M4c's
  `_embed` or the M3 job codes; because nothing registers Voyage in production, the effect is
  confined to explicitly constructed handlers in tests. Mapping retryable provider failures to
  `RetryableJobError` needs a separately reviewed change to the M4a/M4c contract, and must be
  decided before any live indexing. Cancellation and lease loss keep precedence through the
  existing `ctx.check()` before classification.
- **M4d boundary (unchanged).** Every `VoyageError` becomes `retrieval_provider_failed`, which is
  compatible with M4d's fixed-error contract but carries no retryability. **M5 still owns job
  cancellation and lease precedence, and any retry policy, for retrieval orchestration.**

##### M4f D1. Cleanup precedence (Prompt 155 correction D)

`post` runs its phases, then cleans up the response and the connection **separately**, each in
its own `try` where the object exists, so an ordinary response-close failure never prevents the
connection close. (`getresponse()` may already have closed the connection itself [PY]; closing
again is harmless.)

**Scope (Prompt 156 clarification C).** D1 preserves the first process-control exception that
**actually escapes into adapter-owned code** from a call the adapter makes: the connection
factory, a connection method (`connect`, `request`, `getresponse`, `close`), a response method
(`read`, `close`), the clock or an explicit cleanup call. It preserves that same object through
all subsequent adapter-owned cleanup. It does **not** guarantee recovery of a process-control
exception that `http.client` or another dependency has already masked before returning control:
for example, `getresponse()` closes internally when `begin()` fails, and an exception from that
internal close replaces the original [PY]. An ordinary exception that escapes in that way is
classified by its own type only and becomes `voyage_transport_failed`, **regardless of any
process-control exception in its cause or context**; no exception chain is ever inspected to
reconstruct one.

**Operation failures versus adapter-owned cleanup (Prompt 157 clarification).**

- An ordinary exception escaping an **operation** (the factory, `connect`, `request`,
  `getresponse()`, `read()` or the clock) is classified by its own type and sanitized to its
  fixed code, without inspecting its cause or context.
- A failure from cleanup **internal to** `getresponse()` (or another `http.client` operation) is
  observed only as that operation's escaping failure and is classified as such; it is not
  adapter-owned cleanup.
- An ordinary failure of the **adapter-owned** response close or connection close in D1 is
  ignored, even if its cause or context contains a `KeyboardInterrupt` or `SystemExit`: if the
  operation succeeded, success is unchanged; if the operation failed, its existing fixed
  outcome is preserved.
- An actual non-`Exception` `BaseException` escaping adapter-owned cleanup still takes
  precedence as specified below. This residual limitation stays with the simple standard-library transport
(no custom HTTP parser, `HTTPResponse` subclass, watchdog or dependency is added). Live use that
needs a stronger process-control guarantee requires a separately reviewed transport design
first. Fake-method tests prove preservation at these observable call boundaries only, not inside
every internal standard-library operation.

The first-outcome rule:

```python
control = None  # first non-Exception BaseException, kept as the same object
failure = None  # fixed VoyageErrorCode of the first ordinary operation failure
result = None
try:
    result = run_phases()  # connection, send, headers, status, 200 body (B, C1)
except Exception as error:  # classified by type only; never by chain
    failure = classify(error)  # error is not stored beyond this assignment
except BaseException as error:  # process control
    control = error
for close in (close_response, close_connection):
    try:
        close()
    except Exception:
        pass  # ordinary cleanup failure: never changes the outcome
    except BaseException as error:
        if control is None:
            control = error  # cleanup process control beats an ordinary failure
if control is not None:
    raise control  # the same object, outside every handler
if failure is not None:
    raise VoyageError(failure)  # fresh, outside every handler
return result
```

- The first recorded process-control object (one that escaped into adapter-owned code) is
  re-raised after cleanup, even if a later
  cleanup step raises another process-control or ordinary exception.
- Process control from cleanup takes precedence over an ordinary operation failure.
- If the operation failed ordinarily, its fixed code is preserved when ordinary cleanup also
  fails (one or both closes).
- If the operation succeeded, ordinary cleanup failures are ignored and the result is
  returned; process control from cleanup still propagates.
- Cleanup has no deadline (C1). The adapter applies the same pattern around its single `post`
  call: a `VoyageError` from the transport becomes a fresh `VoyageError` with the same code,
  any other `Exception` becomes `voyage_transport_failed`, and process control propagates as
  the same object.

##### M4f E. Configuration and activation

- [REC] **Explicitly constructed adapter only** (V1): `VoyageEmbedder(HttpsVoyageTransport(key))`
  built by trusted code. No change to `SUPPORTED_PROVIDERS`, `production_registry`,
  `eg-admin`, `eg-worker`, `eg-api`, settings, `.env.example`, Compose, the container smoke or
  any default. The production worker therefore cannot index or search with Voyage; a Voyage
  profile created through the trusted `enqueue_index_revision` seam still ends as M4c's
  existing unsupported-profile permanent failure. Offline hashing stays the only production
  provider; no automatic indexing, CLI or API is added.
- **Alternative (not recommended for M4f):** register Voyage in the production mapping with a
  key from new settings. That would make live calls possible from a stored profile, require a
  key in deployments, read new environment state at worker start, change `eg-worker`
  behaviour, require the M4c retryability change above, and require a data-handling decision
  for sending vendor text to a third party ([EXT] the FAQ describes an opt-out for training use
  and retention). It must be a separate review decision (expected with M7 live evaluation).
- **Credential seam** (V12): the key is an explicit `SecretStr` constructor argument of the
  transport, validated as above and used only to build the `Authorization` header inside
  `post`. It is never part of the identity or fingerprint, never stored on the adapter, never
  in a representation, error, log, test or CI. M4f reads no environment variable; how an
  operator supplies the key for live use is part of the later live-wiring decision.
- No key is needed for ordinary tests or CI; test placeholders are obviously fake (for example
  `test-only-not-a-real-key`).

##### M4f F. Tests and acceptance (planned, not written or run)

*Prompts 158-159:* these tests are now written ([ADR-0018](decisions/0018-voyage-adapter.md)); the
database-independent ones ran locally on Windows (Prompts 158-159), and all of them, including
the two PostgreSQL cases, passed in feature-branch CI at `84eec023` (see the
[ADR-0018 evidence](decisions/0018-voyage-adapter.md#feature-branch-ci-evidence-at-84eec023)).
The planned list below is kept as accepted.

All new tests are database-independent unless marked PostgreSQL, and none uses the network.

- **Network guard.** An autouse fixture in each new test module replaces `socket.socket.connect`,
  `socket.create_connection` and `socket.getaddrinfo` with functions that fail the test; the
  transport tests use an injected fake `connection_factory`, so no socket is created.
- **Adapter (`tests/test_voyage_adapter.py`, fake `VoyageTransport`):** a literal pinned
  `VOYAGE_IDENTITY` fingerprint computed independently of the implementation; exact request
  bytes for `document` and `query`, one and 32 texts, non-ASCII, supplementary and control
  characters and duplicates; invalid requests never reach the transport; valid responses in
  order and permuted, integer coordinates and usage mapping; every malformed case (non-JSON,
  invalid UTF-8, `NaN`/`Infinity` literals, `1e400`, duplicate keys, wrong `object` markers,
  missing/extra/duplicate/out-of-range/`bool` indexes, too few or too many rows, wrong or
  missing `model`, wrong dimension, string/`None`/`bool` coordinates, missing or negative or
  `bool` usage, deep nesting); vectors with norm outside 1e-6, a zero vector, and an
  M4a-valid vector that fails float32 storage (`0.999999001`) through `stored_embeddings`;
  every status in the table, including unlisted 4XX/5XX and 1XX/204/3XX; an oversized body;
  **zero** transport calls for every invalid request and **at most one** call once the
  transport is reached (a counting fake); `embed_validated` turning each `VoyageError` into
  `InvalidEmbeddingError` (the current boundary).
- **Direct calls and configuration (C2):** `VoyageResponse` with `True`/`False`, float,
  out-of-range and non-int statuses, `bytearray`/`str`/`memoryview` bodies and a non-200 status
  with a non-empty body; a bypassed `VoyageResponse` built with `object.__setattr__`;
  `parse_response` with a non-`VoyageResponse`, invalid `input_type`, and `count` of `True`, 0,
  33, a float or a string; `build_request_body` and `embed` with every M4a request violation; a
  transport returning `None`, a dict, a subclass instance or a tuple; huge integer coordinates
  (`OverflowError`) and over-long integer literals; usage of `True`, −1, 2^63, a float or a
  string; `VoyageEmbedder` with an object lacking a callable `post`; the transport with a plain
  `str` key, non-`str` secret, empty, 257-character, space, CR, LF, tab and non-ASCII keys;
  timeouts and budget of `True`, 0, negative, NaN, ±infinity, 601 and strings; caps of `True`,
  0, `MAX_RESPONSE_BYTES + 1` and floats; non-callable factory and clock; and clock results of
  NaN, infinity, `None` and strings. Each maps to its C2 outcome with the fixed code only.
- **Transport (`tests/test_voyage_http.py`, fake connections and clock):** method, path, host,
  exact headers (including `Accept-Encoding: identity`) and body; TLS context with
  `CERT_REQUIRED` and hostname checking; `TimeoutError` in each phase as `voyage_timeout`;
  `OSError`, `ssl.SSLError` and `http.client.HTTPException` (including `IncompleteRead`) as
  `voyage_transport_failed`; 3XX not followed; no decompression; `set_debuglevel` never
  called; response and connection both closed after every call.
- **Status before body (B):** 429, 401 and 503 fakes whose `read()` raises if called: `read()`
  is never called and the status mapping wins; a non-200 response advertising a huge or
  malformed `Content-Length`, or `chunked` with a broken body, still maps by status without any
  read; 200 responses with a missing, repeated, empty, signed or non-digit `Content-Length`,
  `chunked` plus `Content-Length`, an unsupported `Transfer-Encoding`, a `gzip`
  `Content-Encoding`, a declared length above the cap, a chunked body exceeding the cap and a
  short body are each refused with their fixed code and no body content in the error.
- **Cooperative budget (C1, fake clock):** a budget exhausted before each phase (connection,
  request sending, response headers, each body read) means that phase's fake is never called;
  a phase returning after expiry yields `voyage_timeout`, never success, for 200 responses; a
  late non-200 status keeps its status code (N4); the applied timeout is `min(phase timeout,
  remaining)`, observed through the factory argument and each `settimeout` call; request
  sending and response headers are included as phases. These tests only show the cooperative
  checks; a fake that returns late does **not** show that a real blocked socket operation is
  interrupted, and no such claim is made.
- **Short bodies (Prompt 156 A):** a declared length of five with only three bytes followed by
  `b""`, from a fake whose bounded `read` never raises `IncompleteRead`, is
  `voyage_transport_failed`; early `b""` on the first read; multiple short nonempty reads that
  eventually supply the exact declared length succeed; no further `read` call once the declared
  length is satisfied (a counting fake); every requested size is at most
  `min(64 KiB, remaining declared length)`; a read returning more than requested or a
  non-`bytes` value; a raised `IncompleteRead` mapping to the same code; budget checks before
  and after every read.
- **Socket ownership (Prompt 156 B):** a correctly framed `Connection: close` response whose
  fake `getresponse()` sets `connection.sock` to `None` succeeds with both `Content-Length` and
  chunked framing; no `settimeout` is attempted on the absent socket and the timeout applied
  before the header phase is the last one recorded; a late completion is still refused by the
  post-read elapsed check; no reconnect (the factory and `connect` are called once) and no
  access to `response.fp` or other private attributes (a fake that fails on any such access).
- **Process-control scope (Prompt 156 C, as clarified in Prompt 157):** an ordinary exception
  whose `__cause__` or `__context__` is a `KeyboardInterrupt` or `SystemExit`, raised by the
  `getresponse()` or `read()` **operation** (including a `getresponse()` fake that simulates a
  failure from its own internal cleanup), remains an ordinary sanitized
  `voyage_transport_failed`; the same kind of ordinary exception raised by the
  **adapter-owned** response close or connection close is ignored under D1, leaving a
  successful result unchanged and preserving a failed operation's existing fixed code; a real
  process-control exception escaping adapter-owned cleanup still takes precedence; and a
  process-control exception escaping a fake method survives both adapter-owned cleanup
  failures as the same object. These are observable-boundary tests only.
- **Status-only values (Prompt 156 D):** a non-200 `VoyageResponse` with a nonempty body, built
  directly, bypassed or returned by a fake transport, is `voyage_malformed_response` before any
  status classification.
- **Cleanup matrix (D1, still required):** an ordinary operation failure combined with an ordinary response-close
  failure, connection-close failure and both (the operation's code wins each time); process
  control (`KeyboardInterrupt` and `SystemExit`) from the connection, request sending,
  headers, body reads, the clock, response close and connection close; process control
  followed by an ordinary cleanup failure; two cleanup failures; a successful operation with an
  ordinary cleanup failure (success returned); a first process-control object retained when a
  later cleanup raises another process-control exception (the first is re-raised, by
  identity); a response-close failure not preventing the connection close.
- **Privacy (both files):** canary text, key, `detail`, body, header and exception-message
  values never appear in a public error's `str`, `repr`, `args`, `__cause__`, `__context__` or
  `traceback.format_exception` output, in default representations, in captured stdout and
  stderr (`capsys`) or in captured log records (`caplog`); public errors have `None` cause and
  context. Process-control objects are checked for identity only, not for sanitized content.
- **Integration with existing contracts (database-independent):** `make_index_revision_handler`
  built with `{VOYAGE_IDENTITY.fingerprint: lambda: VoyageEmbedder(fake)}` and the existing
  handler doubles: success writes canonical rows; each `VoyageError` ends as
  `permanent_failure`; a cancellation or lease loss latched during the call wins over
  classification. `search_snapshot` with a fake-transport `VoyageEmbedder`: success, each failure
  as `retrieval_provider_failed`, process control propagating.
- **PostgreSQL (two cases, `tests/test_voyage_postgres.py`):** a fake transport that answers
  with deterministic nonzero unit vectors (for example derived from the offline hash of each
  input, rejecting all-zero cases) indexes a revision through the real handler to a ready index
  with `allows_zero_vectors = false`; then capture and `search_snapshot` with the same mocked
  provider return bounded results. These prove storage and retrieval wiring only.
- **Packaging (`tests/test_packaging.py`):** `voyage.py` imports only the standard library and
  the domain, and none of `os`, `socket`, `ssl`, `http`, `urllib`; `voyage_http.py` imports no
  `os`, `requests`, `httpx`, `aiohttp` or `voyageai`; production `SUPPORTED_PROVIDERS` still
  contains only `HASH_IDENTITY`; the registry kinds and entry points are unchanged.
- **Installed wheel (V13, one narrowly scoped workflow change):** one added `python -I -c` line
  in the existing installed-wheel step that imports both modules, runs `VoyageEmbedder` with an
  in-memory fake transport returning one canned 1024-dimensional unit vector, checks the batch
  and fingerprint and that `SUPPORTED_PROVIDERS` is unchanged, and prints `Voyage adapter
  validated a mocked response from the installed wheel`. No network, key or database.

**Required for M4f acceptance:** Ruff format and lint, strict mypy, the full suite on Ubuntu and
Windows, the PostgreSQL job including the new cases, both builds with the extended
installed-wheel step, the unchanged container job, full-history Gitleaks, and a diff review
confirming no dependency, lockfile, settings, registry, migration, Docker or Compose change.
**Mocked tests establish the adapter's request formation, validation, bounds, cooperative
timing checks, error mapping and the stated privacy scope only; they establish no hard deadline
and make no live semantic-quality, latency, cost or production-readiness claim. Live evaluation
remains M7.**

##### M4f G. Scope and intended files

- New: `packages/retrieval/evidenceguard_retrieval/voyage.py`,
  `apps/worker/evidenceguard_worker/voyage_http.py`, `tests/test_voyage_adapter.py`,
  `tests/test_voyage_http.py`, `tests/test_voyage_postgres.py`, and with the implementation
  `docs/decisions/0018-voyage-adapter.md`.
- Changed: `tests/test_packaging.py`; `.github/workflows/ci.yml` (one wheel line, only if V13
  is accepted); README, plan, threat model and prompt history.
- **Unchanged:** `pyproject.toml` and `uv.lock` (no dependency), settings and `.env.example`,
  `evidenceguard_domain.embeddings`, `embedding_storage`, `evidenceguard_retrieval.embeddings`
  (`embed_validated`), `evidenceguard_worker.indexing`, `handlers.py`, `retrieval.py`,
  persistence, migrations, `eg-admin`, Dockerfile, Compose and the container smoke. **No
  existing error mapping changes** (V11).

##### M4f review decisions (settled at acceptance, Prompt 157)

**Review outcome (Prompt 155).** The external review of Prompt 154 **approved V1–V9 and
V11–V15**, subject to the Prompt 155 corrections A–D, and **approved V10's numerical defaults
as engineering choices** with its timing guarantees reinterpreted as the cooperative budget of
[M4f C1](#m4f-c1-cooperative-timing-budget-prompt-155-correction-a). The text of each choice
below is kept as originally proposed in Prompt 154, with V9 and V10 annotated. These approvals
settled design choices only; at that point (historical) the complete specification, including
the new details N1–N9, still awaited review. None of them is evidence of live Voyage behaviour.

**Review outcome (Prompt 156).** The external review of Prompt 155 **approved N1–N9** subject to
the Prompt 156 clarifications (short-body detection, socket ownership, process-control scope and
status-only values); V1–V15 remain settled as previously qualified. At that point
(historical) the complete specification, including N10–N13, still awaited review.

**Acceptance (Prompt 157).** The external reviewer **accepted the complete M4f specification**,
including V1–V15 and N1–N13 as qualified by Prompts 155–156, with the final consistency
clarification on operation failures versus adapter-owned cleanup (D1, N13). All choices below
are settled within the accepted specification; no specification decision remains open. The
[OPEN] external API facts are not settled by acceptance.

1. **V1 Activation.** [REC] Explicitly constructed adapter only; no production registration,
   settings or defaults. *Tradeoff:* no production path can use Voyage until a later reviewed
   wiring slice; in exchange no live call or key is possible from shipped defaults.
2. **V2 Standard library, not the SDK.** [REC] `http.client`/`ssl`; no dependency. *Tradeoff:*
   we own a small HTTPS client and its tests, instead of nine transitive runtime dependencies,
   SDK retries and SDK-dependent error privacy.
3. **V3 Ship the real transport in M4f.** [REC] Include `HttpsVoyageTransport` in the worker,
   tested only through fake connections. *Alternative:* adapter and protocol only, real
   transport deferred to M7. *Tradeoff:* untested-live code now versus a smaller slice and a
   later transport review.
4. **V4 Identity.** [REC] `("voyage", "voyage-4-lite", "voyage-http-v1", 1024, "l2")`, naming a
   requested model with no immutability claim. *Tradeoff:* if Voyage changes the model behind
   the name, stored vectors and new queries could silently diverge; only M7 live checks can
   detect it.
5. **V5 Request options.** [REC] `truncation=false`, `output_dimension=1024`,
   `output_dtype="float"`, no `encoding_format`, explicit `input_type`. *Tradeoff:* over-length
   text fails instead of being embedded partially; JSON floats are larger than base64.
6. **V6 Model echo.** [REC] Require `model == "voyage-4-lite"` exactly. *Tradeoff:* fails closed
   if Voyage echoes a resolved or versioned name ([OPEN]), which would block every live call
   until reviewed; ignoring it would lose M4a's required mismatch check. Because only an exact
   match is accepted, the returned name equals the identity's `model_id`, so M4a's “record any
   provider-returned model identity” is met by the stored profile without a new field; a review
   preferring a separately stored echo would need a contract change.
7. **V7 Row order.** [REC] Accept an exact permutation of `index` values and place by index.
   *Alternative:* require `data[i].index == i`. *Tradeoff:* tolerates an undocumented ordering
   change versus a stricter shape.
8. **V8 Unknown response keys.** [REC] Ignore without retaining. *Alternative:* reject.
   *Tradeoff:* forward compatibility with additive API changes versus failing closed on any
   change.
9. **V9 No internal retries.** [REC] One attempt per `embed`; durable retry stays with jobs.
   *Tradeoff:* transient errors surface immediately (and, under V11, fail the M4c job
   permanently) instead of being absorbed. *(Prompt 155 wording: zero transport calls for an
   invalid request, at most one once the transport is reached.)*
10. **V10 Bounds.** [REC] 10 s connect, 30 s socket I/O, 60 s elapsed, 4 MiB response, 1 MiB
    request; choices, not measurements. *Tradeoff:* tighter values risk false timeouts on slow
    networks; looser values hold a worker longer. *(Prompt 155: the numbers are approved; the
    30 s value is a socket I/O timeout per blocking wait, not per `read()` call, and the 60 s
    value is a cooperative elapsed-time budget, not a hard deadline; see C1.)*
11. **V11 Keep existing error mappings.** [REC] Fixed `VoyageError` codes with `retryable`, and
    no change to `embed_validated`, M4c or M4d; record the incompatibility (retryable provider
    failures become M4c `permanent_failure`) and resolve it in a separate reviewed change before
    live indexing. *Alternative:* change the M4a/M4c boundary in M4f. *Tradeoff:* a known gap
    with no production effect now versus redesigning accepted slices inside M4f.
12. **V12 Credential seam.** [REC] An explicit `SecretStr` transport argument, no environment
    or settings in M4f. *Tradeoff:* the operator key path is deferred to the live-wiring
    decision.
13. **V13 Installed-wheel CI line.** [REC] Add the one mocked line to the existing wheel step.
    *Alternative:* no workflow change. *Tradeoff:* a small reviewed workflow edit versus no
    installed-artifact evidence for the new modules.
14. **V14 PostgreSQL cases.** [REC] Add the two mocked-provider cases. *Tradeoff:* longer
    integration job versus storage and retrieval wiring evidence for a non-offline profile
    (`allows_zero_vectors = false`) against real pgvector.
15. **V15 Plan §8 retries.** [REC] For embedding calls, V9 and V10 supersede §8's “60 s timeout,
    2 SDK retries”; §8 still applies to model calls until M5 decides otherwise. *Tradeoff:*
    different retry behaviour for embeddings and model calls.

##### M4f details introduced by the Prompt 155 corrections (settled at acceptance)

Each is a detailed choice made while applying corrections A–D (historically awaiting review);
all were approved in the Prompt 156 review subject to its clarifications and are settled at
acceptance in Prompt 157.

1. **N1 `Accept-Encoding: identity`** added to the request headers, so no compressed body is
   requested; any other `Content-Encoding` is refused. *Tradeoff:* larger responses than gzip.
2. **N2 Strict 200 framing:** exactly one digit-only `Content-Length` or a sole `chunked`
   `Transfer-Encoding`; close-delimited bodies, repeated lengths (even if equal) and mixed
   framing are refused. *Tradeoff:* a legitimate but unusual framing would fail closed.
3. **N3 Usage upper bound** 2^63 − 1 for `total_tokens`. *Tradeoff:* arbitrary but finite;
   M4a itself has no upper bound.
4. **N4 Late non-200 statuses keep their classification** after the budget expires, since they
   are not a success and need no further I/O; only a 200 becomes `voyage_timeout`.
   *Alternative:* map every post-expiry outcome to `voyage_timeout`. *Tradeoff:* more accurate
   classification versus one uniform rule.
5. **N5 Invalid `VoyageResponse` values are `voyage_malformed_response`**, whether built
   directly, bypassed or returned by an injected transport, including a non-200 value with a
   non-empty body. *Tradeoff:* a caller's construction error and a broken transport share one
   code.
6. **N6 Timeout and budget range** 0 < value ≤ 600 seconds (the same ceiling as the database
   `connect_timeout` policy). *Tradeoff:* an arbitrary but finite ceiling.
7. **N7 Clock results** that are not finite real numbers are `voyage_configuration`.
8. **N8 Caller-argument errors** in `parse_response` (`input_type`, `count`) raise M4a's
   `InvalidEmbeddingError`, matching `validate_result`; provider-derived problems use
   `VoyageError`. *Tradeoff:* two error types at one public helper.
9. **N9 Cleanup precedence** exactly as D1: first process-control object wins; ordinary
   cleanup failures never change the outcome; process control from cleanup beats an ordinary
   operation failure; no cleanup deadline.

N1–N9 were approved in the Prompt 156 review subject to its clarifications: N2's
"short body" handling is now the explicit read loop of B, and N9's precedence is scoped to
exceptions that escape into adapter-owned code (D1). N2's strict framing remains a live
compatibility uncertainty until M7.

##### M4f details introduced by the Prompt 156 clarifications (settled at acceptance)

Each is a detailed choice made while applying the Prompt 156 clarifications (historically
awaiting review); all are settled at acceptance in Prompt 157, N13 as clarified there.

1. **N10 Read size** of at most 64 KiB per bounded `read`, and no more than the remaining
   declared length (or `cap + 1` minus the bytes accepted, for chunked framing). *Tradeoff:*
   more read calls than one large read, in exchange for a cooperative check between reads.
2. **N11 Read results** that are not `bytes`, or are longer than requested, are
   `voyage_transport_failed`. *Tradeoff:* defends against a misbehaving injected connection at
   the cost of one more rule.
3. **N12 Released socket:** when `connection.sock` is `None` after `getresponse()`, reads
   continue with the previously applied timeout; the transport neither fails nor reaches into
   private attributes. *Alternative:* refuse such responses. *Tradeoff:* compatibility with
   `Connection: close` responses versus less precise timeout reduction.
4. **N13 Masked process control:** an ordinary exception escaping an `http.client`
   **operation** (including one produced by cleanup internal to that operation) is
   `voyage_transport_failed` even when its chain holds process control; an ordinary
   **adapter-owned** close failure with such a chain is instead ignored under D1 (Prompt 157
   clarification). *Tradeoff:* an interrupt masked inside the standard library is reported as a
   retryable transport failure, not re-raised; only a separately reviewed transport design
   could do better.

At acceptance (Prompt 157, historical) the M4f specification was accepted with its
implementation pending and none of its planned checks run. Since then it has been implemented
(Prompt 158), corrected (Prompt 159), accepted (Prompt 160) and published to `main` at
`5acb75e5` (Prompt 163; see [ADR-0018](decisions/0018-voyage-adapter.md#main-ci-evidence-at-5acb75e5)).
Overall M4 was accepted at review in Prompt 165 (below).

#### Overall M4 acceptance assessment (ACCEPTED at review, Prompt 165)

**Status.** **Overall M4 accepted at external review in Prompt 165 within the reviewed scope
implemented at `5acb75e59edbb42035d468c2c40bb0ab81a8725a`.** Claude Code prepared this
assessment in Prompt 164 (then proposed for review); the external reviewer inspected that
four-document diff, verified its size (91,041 bytes) and SHA-256
(`4bf9c31d4679d8f559ff0107d60d14a02929884d5c95b1df866f25d9ad23bb38`), and checked it against the
original M4 milestone, the accepted later decisions and the current M4e PostgreSQL test source.
The reviewer ran no project suite, regression suite, build, installed-wheel check, database,
Docker or provider call in that review; the exact-commit CI evidence is the independent retrieval
recorded for Prompt 164, not new execution. This accepts M4 only, not M5 or the whole project;
**M5 remains planned and has not started.** The acceptance record was committed locally in Prompt
165, when its publication was pending and not yet authorized (historical); it was published on
`main` at `46c0225787ba09f27508dafaa218c1bf33af1e8e` in Prompt 166 (see the
[acceptance publication evidence](#acceptance-publication-evidence-prompt-166)). The assessment maps the controlling M4
requirements to the evidence on `main` at `5acb75e5`, separating supported requirements,
accepted scope limits and later-milestone work, and the gaps resolved below. No value is
inferred, no requirement is waived and no threshold is added.

**Controlling text.**

- *Original M4 milestone* (first plan commit `6c095738`): scope "Provider interface,
  `HashingEmbedder`, Voyage adapter (mocked in CI), RRF search over snapshot revisions,
  `sample_data/` including the injected variant, ground truth with acceptable and wrong claims,
  and the retrieval contract suite"; acceptance "No foreign, superseded or non-snapshot chunks
  are ever returned" and "Recall@k is computed correctly".
- *Prompt 108 acceptance* (recorded in `ac39503`): the [M4 direction and review
  decisions](#m4-direction-and-review-decisions) and the M4a–M4f sequence with its completion
  evidence. That commit replaced the original M4 bullet and acceptance lines with the accepted
  sequence and decisions without an explicit supersession statement; this assessment therefore
  treats both original acceptance lines as still applicable (see gap G1).
- *Accepted clarifications that change scope* (cited, not rewritten): the **supersession
  clarification** (Prompt 108) defines "no superseded chunks" as snapshot-relative: a revision
  already superseded at capture never enters a new snapshot, while a revision active at capture
  stays eligible for that snapshot. The **Recall semantics decision** (Prompt 108) replaces §7's
  "answerable questions" denominator with each question's gold chunk set G, macro over nonempty
  G, empty G as N/A, and reporting by variant and profile. M4e's settled **E7/E8** make Recall
  report-only with no threshold, and its accepted planned PostgreSQL tests state "Recall values
  are not asserted". The accepted M4e decisions also replace §7's sketched YAML corpus layout
  with the TOML layout of [ADR-0017](decisions/0017-retrieval-evaluation.md). The accepted M4f
  row requires the Voyage adapter mocked in CI and states "No live calls required for M4
  acceptance; live quality evidence belongs to M7".

**Current-version evidence.** On `main` at `5acb75e5` the external reviewer retrieved the logs of
both push runs ([ADR-0018 main CI evidence](decisions/0018-voyage-adapter.md#main-ci-evidence-at-5acb75e5)):
Ubuntu `2675 passed, 308 skipped`, Windows `2674 passed, 309 skipped`, PostgreSQL `308 passed,
2675 deselected` (no integration failure or skip), installed-wheel checks on both platforms, the
container job with all six steps, and Gitleaks over 70 commits. This one run executed every M4
test module, including all M4 PostgreSQL cases (29 M4b, 18 M4c, 39 M4d, 16 M4e and 2 M4f), on the
current code. Per-slice main evidence remains in each ADR.

| Scope | Implemented | Evidence | Reviewed and main baseline | Verification scope | Limits and missing evidence |
|---|---|---|---|---|---|
| M4a contracts | Frozen identity, usage and batch values, canonical fingerprint, strict request/result validation, `EmbeddingProvider`, `embed_validated`, offline `HashingEmbedder` (`fake-hash-v1`, 1024 dims) | [ADR-0013](decisions/0013-embeddings.md); `tests/test_embeddings.py`, `tests/test_packaging.py`; wheel offline-embedding line | Accepted Prompts 108/110; `main` `5fdaa1c`; re-run at `5acb75e5` | Pinned vectors and fingerprints, bounds, privacy, cross-platform determinism | Lexical-hash baseline, no semantic claim |
| M4b persistence | Migration `0005`, pgvector `vector(1024)`, profiles, indexes, canonical float32 storage, `simple` full-text column, fenced writes and readiness | [ADR-0014](decisions/0014-embedding-persistence.md); `tests/test_embedding_storage.py`, `tests/test_embedding_store.py`, `tests/test_embeddings_postgres.py` (29) | Accepted Prompts 116/118; `main` `872d0af`; re-run at `5acb75e5` | Real PostgreSQL constraints, migration round trips, tenant joins, readiness | No protection against privileged direct database modification |
| M4c indexing | Tenant-scoped enqueue and bounded backfill, `eg-admin backfill-indexes`, `index_revision` handler with atomic readiness | [ADR-0015](decisions/0015-revision-indexing.md); `tests/test_indexing.py`, `tests/test_index_handler.py`, `tests/test_indexing_postgres.py` (18); container smoke | Accepted Prompts 124/127; `main` `76fa5a3`; re-run at `5acb75e5` | Leases, fences, replay, partial batches, cancellation and lease loss; production indexing in the smoke | Stalled index has no recovery; activation does not enqueue indexing; provider calls not exactly-once |
| M4d snapshot and retrieval | Trusted capture refusing unready revisions, lexical and exact-vector channels (top 20), RRF k = 60, final k ≤ 20 (default 8), bounded evidence | [ADR-0016](decisions/0016-snapshot-retrieval.md); `tests/test_retrieval_contracts.py`, `tests/test_retrieval_store.py`, `tests/test_retrieval_orchestration.py`, `tests/test_retrieval_postgres.py` (39) | Accepted Prompts 133/136; `main` `cf2b5743`; re-run at `5acb75e5` | Isolation, filtering before limits, snapshot-after-supersession, ties, bounds, process control | A forged in-process snapshot can include pre-capture superseded revisions (documented test); M5 must persist and reload snapshots; no endpoint uses retrieval |
| M4e corpus and evaluation | Fictional corpus (2 tenants, 3 vendors, 12 revisions, 17 anchors, 10 questions), clean and injected variants, anchor-to-chunk ground truth, exact `Fraction` Recall@5/@8, contract and isolation checks, test-only orchestrator | [ADR-0017](decisions/0017-retrieval-evaluation.md); `tests/test_evaluation_corpus.py`, `tests/test_evaluation_anchors.py`, `tests/test_evaluation_recall.py`, `tests/test_evaluation_worker.py`, `tests/test_evaluation_postgres.py` (16); wheel 2/3 line | Accepted Prompts 143/147; `main` `0ae4c6ca`; re-run at `5acb75e5` | Corpus validation, exact Recall arithmetic, fresh two-epoch load through production seams, read-only verifier, evaluation and isolation over stored chunks for both variants | Report-only Recall; no numerical database-derived corpus Recall value observed or published (G2); no semantic or injection-resistance claim; claim-support metrics are M5/M7 |
| M4f Voyage adapter | Pure adapter and explicitly constructed standard-library HTTPS transport, fixed identity, strict validation, fixed private errors, cooperative timing | [ADR-0018](decisions/0018-voyage-adapter.md); `tests/test_voyage_adapter.py`, `tests/test_voyage_http.py`, `tests/test_voyage_postgres.py` (2); wheel Voyage line | Accepted Prompts 157/160; `main` `5acb75e5` | Mocked transport, connections and clocks; indexing and retrieval wiring with an in-memory transport against pgvector | No live call (not required); model-echo, framing and normalization compatibility unverified; retryability gap before live indexing |
| Isolation: no foreign, superseded or non-snapshot chunks | Tenant, vendor, binding, ready-index and profile joins before every channel limit; snapshot-relative supersession; M4e isolation checks (forbidden, foreign tenant, other vendor, canaries) | M4d and M4e PostgreSQL cases; [ADR-0016](decisions/0016-snapshot-retrieval.md), [ADR-0017](decisions/0017-retrieval-evaluation.md) | Re-run at `5acb75e5` | Exercised fixtures and corpus only | Not a general isolation proof; trusted in-process snapshot limit until M5 |
| Recall@k computed correctly | Per question, the size of (top-k ∩ G) over the size of G; empty G as N/A; macro over nonempty G; k = 5 and 8 | `tests/test_evaluation_recall.py` (2/3, duplicates, fewer than k, empty G, macro 3/4, failed groups); M4e PostgreSQL cases producing valid, well-formed reports; wheel 2/3 line | Re-run at `5acb75e5` | Exact arithmetic on specified examples; end-to-end evaluation with every question valid | The pure arithmetic tests assert the specified expected values; corpus-derived Recall from the PostgreSQL runs is reported but not pinned (values may vary across fresh loads); no such value observed or published (G2) |
| Corpus, variants, traps and ground truth | Clean and injected variants differing by one paragraph; superseded (r1) and cross-tenant canary traps, other-vendor isolation, missing-answer questions; acceptable and wrong claims validated | `sample_data/`, `tests/test_evaluation_corpus.py`, `tests/test_evaluation_anchors.py`, M4e PostgreSQL cases | Re-run at `5acb75e5` | Schema, reference, quote and variant validation; loading and isolation | Wrong claims are validated data only; their metrics run in M5/M7 |
| Accepted defaults | Exact cosine and `simple` full-text search, no approximate index or framework, per-channel 20, RRF 60, final 8, 1–8 queries, separate readiness, refusal of unready capture | M4d and M4b evidence above | Re-run at `5acb75e5` | Contract and PostgreSQL tests | Engineering defaults, not benchmarks |
| Offline default and mocked Voyage | Production `SUPPORTED_PROVIDERS` offline-only; Voyage constructed explicitly; mocked in CI | `tests/test_packaging.py`; `tests/test_voyage_*.py` | `main` `5acb75e5` | Packaging boundaries and mocked tests | Live wiring, settings and data-handling decisions deferred to M7 |

**Assessment.**

- *Supported by observed evidence:* every M4a–M4f slice is accepted, reviewed and on `main`, and
  the current `main` run executed all of their tests successfully. The isolation requirement is
  supported on the exercised fixtures, under the snapshot-relative meaning of "superseded"
  accepted in Prompt 108. "Recall@k is computed correctly" is supported by exact-arithmetic tests
  of the accepted semantics and by end-to-end evaluation that runs to valid reports over stored
  chunks for both variants. The corpus, variants, traps and ground-truth fields named in the
  original scope exist and are validated, and the Voyage adapter is mocked in CI as required.
- *Accepted scope limits and later-milestone work (not M4 requirements):* live Voyage calls and
  quality evidence (M7, per the M4f row); semantic quality, claim-support precision,
  support-judgment accuracy, status accuracy, injection effect and canary-in-output (M5/M7, per
  the accepted M4e scope); persisted snapshots and job cancellation and lease precedence for
  retrieval (M5); the retryability mapping before live indexing; local Compose (an accepted M3
  limitation); and the limits listed in each ADR.
- *Evidence gaps (identified in Prompt 164; resolved at review in Prompt 165):*
  - **G1, traceability.** The original acceptance lines were removed by `ac39503` without an
    explicit supersession note. **Resolution:** the reviewer confirms that the original isolation
    and Recall-correctness criteria remain applicable; their removal from the milestone summary
    did not waive them. "No superseded chunks" has the accepted Prompt 108 snapshot-relative
    meaning, with the documented trusted-in-process snapshot limitation; this is not a universal
    isolation proof.
  - **G2, numerical corpus Recall.** No database-derived numerical corpus Recall value has been
    observed or published. The PostgreSQL evaluation tests run the evaluation to valid reports
    and assert contract and isolation outcomes; they do not pin corpus-derived Recall values,
    which may vary across fresh loads, while the pure arithmetic tests do assert the specified
    expected values. **Resolution:** the reviewer does not require an additional published
    numerical report for M4 acceptance, because the accepted scope requires correct computation
    and contract and isolation evaluation, which the arithmetic tests and the PostgreSQL
    evaluation tests support. A numerical report remains optional follow-up evidence, with no
    threshold and no quality claim (any README figure would still need a committed run, per §7).
    No database-derived corpus Recall value has been observed or published.
  - **G3, documentation lag.** `main` at `5acb75e5` still describes M4f as unmerged.
    **Resolution:** the reviewed documentation corrects the M4f main-publication status; Prompt
    165 records the acceptance in a local commit only, and its publication remains pending and is
    not authorized there.
- *Unmet requirement:* none found.

**Acceptance decision (Prompt 165).** The external reviewer **accepted overall M4 within the
reviewed scope implemented at `5acb75e5`**: all six M4 slices are implemented, individually
accepted, published and verified on `main`, with the limitations above and in ADR-0013 to
ADR-0018. *(Prompt 164 had proposed this disposition, conditional on review and publication of
this documentation and a decision on G2; historical.)* The acceptance adds no new mitigation or
security guarantee. It is not acceptance of M5 or of the whole project: **M5 remains planned and
has not started**, and no M5 work is authorized by this decision.

##### Acceptance publication evidence (Prompt 166)

[FACT] In Prompt 166 the accepted record (the Prompt 165 local commit `a3d8991e` plus the
approved one-sentence clarification and prompt history) was committed as
**`46c0225787ba09f27508dafaa218c1bf33af1e8e`** (parent `a3d8991e`), published on
`docs/m4-acceptance-assessment`, and, after all five jobs passed for that exact commit,
fast-forwarded onto `main`, where all five jobs passed again. **The M4 implementation baseline
stays `5acb75e5`:** the range from `5acb75e5` to `46c02257` changes documentation and prompt
history only, so this run re-verifies the same implementation rather than a new one.

**Attribution.** In Prompt 166 Claude Code observed only run, job and step conclusions through the
anonymous public API; its anonymous log downloads returned HTTP 403 or failed without an HTTP
response, so it observed no counts or log output. The external reviewer independently retrieved
all four run records, all ten job records and all ten job logs; the counts and output below come
from that retrieval. The reviewer ran no project test, build, wheel check, Docker, database or
provider call.

All four runs used event **push**, SHA `46c0225787ba09f27508dafaa218c1bf33af1e8e`, **attempt 1**,
and concluded **success**; all ten jobs and their required steps succeeded, none skipped.

**Documentation branch** (`docs/m4-acceptance-assessment`, before the fast-forward):
[CI run 39145004493](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39145004493)
and [secret-scan run 39145004509](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39145004509).

| Job | Observed |
|---|---|
| [Ubuntu verify 117726950822](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39145004493/job/117726950822) | `2675 passed, 308 skipped in 25.54s` |
| [Windows verify 117726950554](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39145004493/job/117726950554) | `2674 passed, 309 skipped in 76.20s (0:01:16)` |
| [PostgreSQL integration 117726950798](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39145004493/job/117726950798) | `308 passed, 2675 deselected in 197.71s (0:03:17)` |
| [Container 117726950860](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39145004493/job/117726950860) | all six required steps succeeded |
| [Gitleaks 117726950708](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39145004509/job/117726950708) | 72 commits scanned, no leaks found |

**Main** (after the fast-forward):
[CI run 39145584019](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39145584019)
and [secret-scan run 39145584030](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39145584030).

| Job | Observed |
|---|---|
| [Ubuntu verify 117728627885](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39145584019/job/117728627885) | `2675 passed, 308 skipped in 38.01s` |
| [Windows verify 117728627856](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39145584019/job/117728627856) | `2674 passed, 309 skipped in 73.31s (0:01:13)` |
| [PostgreSQL integration 117728627638](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39145584019/job/117728627638) | `308 passed, 2675 deselected in 184.61s (0:03:04)` |
| [Container 117728627883](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39145584019/job/117728627883) | all six required steps succeeded |
| [Gitleaks 117728627878](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39145584030/job/117728627878) | 72 commits scanned, no leaks found |

Both PostgreSQL logs show the M4 modules passing: `tests/test_embeddings_postgres.py` 29,
`tests/test_indexing_postgres.py` 18, `tests/test_retrieval_postgres.py` 39,
`tests/test_evaluation_postgres.py` 16 and `tests/test_voyage_postgres.py` 2, that is 104 M4
PostgreSQL cases within the 308 integration passes. On both pushes both platforms ran tests,
distribution builds and installed-wheel checks successfully; all four wheel logs printed:

```text
offline embedding, canonical storage and indexing modules ran from the installed wheel
retrieval modules imported and fusion ran from the installed wheel
evaluation modules imported and Recall@5 = 2/3 computed from the installed wheel
Voyage adapter validated a mocked response from the installed wheel
offline migration SQL rendered from the installed wheel
```

Both container logs reported 89 context files with 19 planted fixtures excluded; a healthy stack
and successful migrations; upload 202, successful ingestion with two verified chunks and a
duplicate upload 200; one offline backfill indexing job, a ready index with two embeddings and a
succeeded indexing job; idle-worker exit 0 without OOM; and successful smoke and cleanup. These
are observed log summaries and successful gates, not independent inspection of raw rows or
generated credentials, and the smoke covers offline ingestion, indexing and idle-worker shutdown
only.

**Limits.** The Voyage wheel line and PostgreSQL cases use a mocked transport; the 2/3 Recall line
is pure arithmetic. No database-derived numerical corpus Recall value has been observed or
published. All accepted M4 limitations above and in ADR-0013 to ADR-0018 are unchanged: offline
production defaults with no live Voyage wiring or verification; cooperative timing, the
observable process-control scope and accepted-bytes rather than peak-memory bounds; privacy scope
excluding frame locals and held values; the retryability work required before live indexing; the
trusted in-process snapshot limitation until M5 persists and reloads captured facts; the
container-smoke scope; local Compose unverified; and no quality, security or production-readiness
guarantee. The earlier records of logs unavailable to Claude Code, including Prompt 166's, stand.

**M5 – Review workflow (fake model in CI)**
- Provider interface; Anthropic and scripted fake providers; `prompts/verifier/v1.md` and `prompts/risk_analyst/v1.md`; planner; orchestration; review snapshot; provenance checks; status derivation; report renderer; provider-call records and spans.
- *Acceptance:*
  - Invalid output, a refusal, a timeout and a forged chunk ID each end unresolved or rejected.
  - **A revision activated after a review started is not used by that review, including after a resume.**
  - **A worker killed after a stage commit resumes without duplicate rows.**
  - **A worker killed between a provider response and its commit repeats the call once.** The test checks the second call is recorded and no duplicate stage row is written.
  - **A stale worker's stage writes are rejected.**
  - The injection canary never appears in output.

#### M5 implementation sequence (ACCEPTED at review, Prompt 170)

**Status.** **The dependency-ordered M5 sequence was accepted at external review in Prompt 170**,
together with the complete [M5a specification](#m5a-model-call-contracts-and-scripted-fake-provider-accepted-at-review-prompt-170-implementation-pending).
It was proposed in Prompt 167, corrected in Prompt 168 (corrections A–E, below) and clarified in
Prompt 169 (clock arithmetic, the canary acceptance assertion, report integrity, creation
failures and boundary exceptions); the subsections below keep those historical stages. The
sequence acceptance covers the slice order and the settled design choices; it is **not** detailed
acceptance of the M5b–M5h schemas, SQL, prompts, transport or orchestration, each of which needs
its own reviewed specification (see [acceptance scope](#m5-sequence-and-m5a-acceptance-prompt-170)).
**M5a was implemented in Prompt 171, corrected in Prompt 172 and accepted for a local commit in
Prompt 173 (publication and CI were then pending); in Prompt 174 it was published on
`feat/model-call-contracts` and verified in feature-branch CI at `9ba6a488` ([feature
evidence](#m5a-feature-branch-ci-evidence-prompt-174)); in Prompt 176 it was published on `main` at
`f04e0957` after exact-commit feature CI, and main-push CI passed ([main
evidence](#m5a-main-publication-evidence-prompts-176177); the Prompt 176 record of a pending
publication is historical). The
[M5b specification](#m5b-provenance-and-status-derivation-specification-accepted-at-review-prompt-176-implementation-pending)
was proposed in Prompt 174, corrected in Prompt 175 and **accepted at external review in Prompt
176**; **M5b was implemented in Prompt 177, corrected in Prompt 178 and accepted at external
review in Prompt 179** ([implementation
status](#m5b-implementation-status-accepted-at-review-prompt-179-ci-pending)); it was then verified in exact-commit feature and main-push CI and published on `main` at
`90295717` (Prompt 179; job-log results independently retrieved by the external reviewer and
recorded in Prompt 180). The [M5c specification](#m5c-review-template-planner-prompts-and-request-assembly-specification-accepted-at-review-prompt-181-implementation-pending)
(proposed in Prompt 179, revised in Prompt 180) was **accepted at external review in Prompt 181**;
**M5c was implemented in Prompt 182, corrected in Prompt 183, accepted at external review in Prompt
184 and published on `main` at `e8d1033c` after exact-commit feature and main-push CI (Prompt
185)** ([implementation
status](#m5c-implementation-status-accepted-for-a-local-commit-prompt-184-ci-pending)). The
[M5d specification](#m5d-composable-capture-and-atomic-review-creation-specification-accepted-at-review-prompt-188-implementation-pending)
(proposed in Prompt 185, revised in Prompts 186–187) was **accepted at external review in Prompt
188**; its implementation (Prompt 189, corrected in Prompts 190–191) was accepted at external review in
Prompt 191 for a local commit only; feature CI at `1bea3731` then failed three PostgreSQL tests, and
test-only corrections were accepted for a corrective commit in Prompt 194, with their PostgreSQL and
CI verification pending ([implementation
status](#m5d-implementation-status-accepted-for-a-local-commit-prompt-191-ci-pending)). M5e–M5h are not
implemented; no review path or orchestration exists, the M5d persistence is used only by tests,
no M5b or M5c control is used by any review path, and overall M5 acceptance is pending.** The M5 milestone text above is the controlling requirement and is unchanged; this
sequence only orders it into slices. Labels: **[DECISION]** already accepted; **[FACT]** current
code at `46c02257`; **[REC]** recommendation (for M5a and the sequence-level choices, accepted in
Prompt 170 as recommended); **[OPEN]** a detail left to a later slice's review. Earlier sketches in
§§4, 6 and 8 (entity lists, `ModelProvider.generate_structured`, table names) are design sketches,
not implemented code or accepted detailed schemas.

##### M5 sequence and M5a acceptance (Prompt 170)

[DECISION] The external reviewer accepted, in Prompt 170:

- the M4 acceptance-publication documentation prepared in Prompt 167;
- the corrected dependency-ordered **M5 sequence** (M5a–M5h) and its settled design choices
  (W1–W8, W10, W11 and W13–W15 as recommended, W14 under the report-integrity invariant);
- the **complete M5a specification**, with one final clarification of the planned clock-test
  wording (G). The accepted M5a recommendations and W-A1 to W-A11 form its **implementation
  contract**; no M5a specification decision remains open.

*Still pending at acceptance (historical):* the M5a implementation and every M5a check; no
model-call module, `evidenceguard_agents` package, test, workflow extension or ADR-0019 existed,
and no M5 mitigation operated. M5a has since been implemented (Prompt 171), corrected (Prompt 172) and accepted for a local commit (Prompt 173;
see the [implementation status](#m5a-implementation-status-accepted-for-a-local-commit-prompt-173-ci-pending)).
Overall M5 acceptance is pending.

*Later review obligations* (each belongs to its own slice specification and does not block the
accepted, bounded M5a specification): M5b exact quote matching and normalization (W12); M5c
template and prompt packaging and safe request assembly; M5d composable capture, SQL, isolation,
idempotency and retry policy; M5e persistence schemas and fenced reservations and stages; M5f the
versioned hash-covered report representation; M5g orchestration, crash and reclaim behaviour and
error mapping; M5h the SDK or transport and the live model-alias policy (W9). Production wiring
remains a separate reviewed decision (W8).

*Review attribution.* The reviewer verified the three exports
(`.local/p167/m4-publication-and-m5-plan.diff`, 103,583 bytes, SHA-256
`24147a9431e5b61d06c4f869cba42774b5d11884f80f3ab4865db4c58b0c96db`;
`.local/p168/m5-plan-contract-corrections.diff`, 81,299 bytes, SHA-256
`2b2fd263b01d2d95b179b7b9bbf9eee65dc30493ab7b648cba1f3c0e45bd1d05`;
`.local/p169/m5-final-spec-clarifications.diff`, 45,275 bytes, SHA-256
`3284c752cea6516fa6eb117d6f5e2308a99e75ba9517168f4dbea505082f69b3`) and reviewed the proposal and
its corrections. The Prompt 168 review included the relevant existing domain and persistence
source and two isolated Pydantic 2.14.0 probes in the review environment; the Prompt 169 review
included isolated Python arithmetic probes. Those were not locked-project tests and not evidence
about an implemented M5 module. The final review verified the Prompt 169 export and clarified the
planned clock-test wording. The reviewer ran no project suite, regression suite, build,
installed-wheel check, database, Docker or provider call for this specification review; existing
CI evidence belongs to M4 at its recorded exact SHAs. Claude Code wrote the proposal, its
corrections and this record (Prompts 167–170).

##### Review status and supported directions (Prompt 168)

The external reviewer accepted the M4 publication-evidence documentation from Prompt 167 and kept
the whole M5 sequence and M5a specification **proposed, not accepted** at that stage (historical;
both were accepted in Prompt 170). The reviewer recorded
these **supported directions**, each subject to a corrected, complete specification; they are not
acceptance of M5 or of M5a:

- M5a first;
- domain output and value contracts, with the provider, fake, planner and adapters in
  `evidenceguard_agents` behind enforced import boundaries;
- a TOML review template independent of the ground truth;
- started-call reservations committed before dispatch;
- dedicated M5 test fixtures rather than changes to the accepted M4e corpus;
- the existing `Verification`, `Citation` and `Finding` contracts retained, with surrounding values
  added where needed;
- a raw `generate` plus one shared validating boundary;
- fixed outcomes for ordinary provider failures;
- immutable call values and immutable strict output schemas;
- explicit bounds, zero hidden SDK retries and a narrow installed-wheel extension;
- creating the agents package in the first slice that uses it.

The detailed Anthropic SDK or transport choice and any live model-alias behaviour wait for M5h; no
live model-name compatibility is claimed. For W12 the normalized-substring direction is retained,
with the exact rules left to M5b (below).

*Reviewer attribution (Prompt 168).* The reviewer verified the Prompt 167 export's bytes and
checksum, inspected the proposed sequence and contracts and the relevant existing domain and
persistence source, and ran two isolated probes with the review environment's Pydantic 2.14.0:
strict validation of a decoded Python dictionary rejected an enum string, and a frozen Pydantic
model containing a list allowed that list to mutate. The reviewer ran no project test,
locked-project probe, build, wheel, PostgreSQL, Docker or provider call. The probes concern the
proposed design only; **no M5 module exists**, so they are not evidence about an implementation.

##### Reviewer-approved design choices (Prompt 169)

The external reviewer matched the Prompt 168 export and approved these **design choices within
the corrected proposal**. At that stage this was not yet acceptance of the complete M5 sequence or
the M5a specification (historical; both were accepted in Prompt 170), and nothing is implemented
or tested:

- **Sequence:** W1, W2, W3, W6 and W11 (the directions supported in Prompt 168); W4 and W5 (a
  persisted budget of three reservations per stage across attempts, one repair allowance across
  attempts, no exactly-once guarantee); W8 (internal and test-only creation, an explicit handler
  and provider, no production fake dispatch, and production enqueue, registration and provider
  configuration enabled together only by a later reviewed task); W10 (dedicated fixtures with the
  acceptance and limitation fixtures kept apart, below); W13 (model mismatch terminal for the
  stage); W14 (subject to the report-integrity invariant, below); W15 (a read-time review-state
  projection, with the completed output and job success committed atomically).
- **M5a:** W-A1 to W-A9 and W-A11 (the corrected contracts, strict immutable schemas, bounded
  fake, zero hidden retries and narrow wheel check), and W-A10 (the clock policy, including the
  Prompt 169 arithmetic correction in D1).

**Still awaiting their own specifications** (they do not block review of the bounded M5a
contract): W12's exact normalization and matching rules (M5b); W9's SDK or transport and any live
alias behaviour, including the alias part of W-A4 (M5h); the report-content representation
(M5f, under the invariant below); M5d's SQL, schemas, idempotency and retry policy; M5e's
schemas; and M5g's detailed orchestration and error-code mapping.

*Reviewer probe (Prompt 169).* In the review environment's Python, finite floats `-1e308` and
`1e308` made the latency subtraction and conversion raise `OverflowError`, and
`math.isfinite(10**1000)` raised `OverflowError`. This was isolated Python arithmetic, not a
project test and not evidence about an M5 implementation, which does not exist.

##### Accepted requirements carried into M5

- [DECISION] D4–D6, D9, D10 and correction E: deterministic Planner and Report Composer; model
  judgment only in the Evidence Verifier and Risk Analyst; plain Python with persisted, typed
  stage state; a refusal leaves the question unresolved with no automatic fallback; the live
  model is chosen by measured evaluation (M7); recovery reuses persisted results, does not
  promise exactly-once model calls and fences every stage write.
- [DECISION] §4 evidence semantics: provenance checks prove only that a quote exists in an
  authorized chunk retrieved for that review and question; `evidence_status` is derived
  deterministically from the verdict and the cited documents' `source_type`; authenticity is
  always `not_established`; a `vendor_claim` on a question requiring documentary support raises
  a finding. §4: invalid output gets one repair attempt, after which the question is unresolved.
- [DECISION] Correction B and the Prompt 108 decisions: each review snapshots its eligible
  revisions and configuration; retrieval uses the snapshot, not current status; M5 persists the
  captured authorization and configuration facts atomically with review creation and reloads
  them only through trusted paths; a frozen value, ID list, digest or timestamp proves neither
  authorization nor past eligibility.
- [DECISION] M4d (R3 and its failure boundary): the snapshot seams are trusted internal
  interfaces; when M5 calls them from a job handler, M5 must specify how cancellation and lease
  loss take precedence. M4f (V11, V15): embedding retryability is unresolved before live
  indexing; §8's "60 s timeout, 2 SDK retries" still applies to model calls until M5 decides
  otherwise.
- [DECISION] §7 modes: the `contract` mode uses fake components and is stamped "NOT a quality
  measurement of Claude or semantic retrieval"; claim-support precision, support-judgment
  accuracy, status accuracy, coverage, paired injection effect, latency and cost are M7 live
  evaluation. M4e assigned claim judgments and end-to-end canary behaviour to "M5/M7"; this
  sequence reads that as contract-fixture behaviour in M5 and measured behaviour in M7.

##### Facts from current source (`46c02257`)

- [FACT] No `evidenceguard_agents` package, `prompts/` directory, review template file, model
  provider protocol, model SDK dependency, review/stage/provider-call/span table or `run_review`
  handler exists. Migrations are `0001`–`0005`. The production registry holds `ingest_revision`
  and `index_revision` only, and the worker claims only the kinds in its registry
  (`HandlerRegistry.kinds` is the claim filter). The wheel packages six import packages;
  `tests/test_packaging.py` enforces the import boundaries and per-module third-party allowlists.
- [FACT] `evidenceguard_domain.evidence` defines `Verdict`, `EvidenceStatus`, `SourceType`,
  `Authenticity`, `Severity`, `EvidenceQuestion` (1–5 search queries), `Citation` (tenant,
  revision, chunk, `source_type`, quote; shape only), `Verification` (caller-supplied
  `evidence_status` checked against the verdict and citation source types; no claims list,
  `provenance_check` or provider-call reference), `Finding` and `ReportContent` with its coverage
  rules (a question without a resolving finding must be listed as unresolved; listing any other
  question as unresolved is allowed). `evidenceguard_domain.report` hashes content as
  `evidenceguard.report-content.v1`; `evidenceguard_domain.approval` holds pure report
  transitions. These are `DomainModel` (Pydantic, frozen, whitespace-stripping) values.
- [FACT] M4d provides `capture_snapshot`, `retrieve_with_vectors`, `search_snapshot` and
  `search_current` over an in-process `RetrievalSnapshot` with a canonical `sha256`, the binding
  recheck, and `ChunkEvidence` carrying exact text, body and optional repeated-header spans,
  `source_type` and `authenticity`. `capture_snapshot(session_factory, …)` runs its private
  capture body through `run_read`, which uses `document_views.read_snapshot`: that helper opens
  its own session, makes `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY` its first
  statement, reads `clock_timestamp()`, and always rolls back and closes. **It cannot be called
  inside a caller-owned write transaction.** Nothing persists or reloads a snapshot.
- [FACT] Jobs: `enqueue(session, actor, …)` runs in the caller's transaction and documents its
  concurrent-conflict behaviour under READ COMMITTED; `JobPayload` values are canonical UUIDs
  only (at most 4,096 bytes); attempts are 1–10 (default 3); reclaiming an expired lease
  increments `attempt`, and a job can reach `dead` by reclaim or sweep without any handler
  running; `JobContext.check()` latches cancellation and lease loss; `fenced(finish=True)` commits
  effects with job success; handlers raise `RetryableJobError`/`PermanentJobError` with fixed
  `JobErrorCode`s. There is no user-facing cancel operation.
- [FACT] Corpus: the injected variant replaces one Tenant A trust-center page with an added
  instruction paragraph; it contains **no dedicated injection canary token**. The existing
  canaries (`LV-TB-CANARY-36H`, `LV-TB-CANARY-AES`) are **cross-tenant** canaries in Tenant B
  documents. Questions exist only in `sample_data/ground_truth/*.toml`, which a planner or fake
  provider must never read.

##### Proposed slices (dependency-ordered)

[REC] Each slice is reviewed, verified in CI and merged before the next starts, as in M3 and M4.
Only M5a has a detailed specification below; later rows are sequence-level and need their own
reviewed specifications. *Prompt 168 reorders the former M5f (handler) and M5g (renderer)*, so the
renderer exists before the handler's atomic final commit needs it.

| Slice | Purpose and behaviour | Depends on | Placement | Persistence |
|---|---|---|---|---|
| **M5a** | Model-call contracts and scripted fake: request/response/result values, the canonical request digest, closed Verifier and Risk Analyst raw-output schemas with strict JSON parsing, a provider protocol, a validating call boundary that turns every ordinary provider failure into a fixed outcome, and `ScriptedFakeProvider` | M1 domain | `evidenceguard_domain.model_calls`, `evidenceguard_domain.agent_outputs`; new `evidenceguard_agents` (`providers`, `scripted`) | None |
| **M5b** | Provenance checks and status derivation (pure): Verifier output plus the question's retrieved evidence → `Verification` with derived status and trusted citation metadata, or `citation_rejected`; analyst findings restricted to already validated citations; the `requires_documentary_support` finding rule; exact quote-matching rules (W12) | M5a, M4d values | `evidenceguard_domain.provenance` | None |
| **M5c** | Versioned artifacts: TOML review template, deterministic Planner, `prompts/verifier/v1.md` and `prompts/risk_analyst/v1.md` as packaged data with pinned SHA-256, and request assembly that places evidence only inside delimited blocks with **safe encoding** of document text (Correction E) | M5a, M5b | `evidenceguard_agents` (`planner`, `prompts`, `assembly`); packaged data | None |
| **M5d** | Composable capture and review creation (Correction A): a public capture operation for a caller-owned transaction, extracted from the M4d capture phases with `capture_snapshot` unchanged; one creation transaction storing the review, every binding, the exclusions record, the pinned configuration and, through the same transaction, the `run_review` job; a trusted loader that rebuilds and revalidates the snapshot. Internal seams only (W8) | M4d, M5c | `evidenceguard_persistence.retrieval` (capture extraction), `evidenceguard_persistence.reviews`; migration `0006` | Yes |
| **M5e** | Stage, call-reservation and output records (Correction D): per-question stage rows unique on `(tenant_id, review_id, question_id, stage)`, persisted call reservations and provider-call records and spans, the stored report output, all through fenced writes; identical replay is a no-op and a differing replay is a fixed conflict, never an overwrite | M5a, M5b, M5d | `evidenceguard_persistence.review_stages`; migration `0007` (or merged into `0006`) | Yes |
| **M5f** | Report content and renderer (pure): settles the hash-covered report-content representation under the report-integrity invariant (a versioned wrapper around `ReportContent`, or omission of conclusions it cannot hold), builds that content from committed stage values, and renders Markdown solely from the hashed content, including unresolved questions, authenticity labels and the contract-mode stamp | M5b, M5e values, M1 report contracts | `evidenceguard_agents.report` | None (stored by M5g) |
| **M5g** | `run_review` handler factory and bounded orchestration: plan → retrieve (M4d `search_snapshot` over the loaded snapshot) → verify (with repair) → analyze → render → one atomic final commit; resume, reservations and budgets, cancellation, lease-loss and failure precedence; fake-provider controlled crash tests. Not registered in production (W8) | M5a–M5f, M3b runtime | `evidenceguard_worker.review` | Uses M5d/M5e |
| **M5h** | Anthropic adapter behind the M5a protocol, tested only with an injected or mocked transport; not registered, no settings, no live call (W9) | M5a | `evidenceguard_agents.anthropic` (adapter) and, if a transport is needed, the worker | None |

After M5h, an overall M5 acceptance assessment maps every criterion to evidence, as for M3 and M4.

**Boundaries.** [REC] M5 does not change M3 activation, M4 chunk/index immutability, the M4d
retrieval seams or the M4f adapter; M5d only *extracts* the M4d capture phases into a composable
operation, with `capture_snapshot`'s public behaviour preserved and re-tested. M6 owns report
revisions, approval, finalize, export, ETags and audit events (the pure M1 transitions stay unused
by M5 except for content hashing). M7 owns live model and embedding runs, annotation, pricing,
measured metrics and model selection. Review-facing endpoints and production dispatch are decided
in W8.

**Exclusions for all of M5.** [REC] No live provider call, credential, provider setting or
production registration of a non-fake model provider; no production use of fake judgments; no
approval, finalize or export endpoint; no live evaluation, measured quality, latency or cost
claim; no LLM planner, judge, reranker or summary (E3, E4, E7, E10); no framework or queue
dependency; no change to the accepted M4 corpus (W10); no production canary denylist.

##### Composable capture and review creation (Correction A)

[REC] Sequence-level design for M5d; the detailed persistence review settles SQL, schemas and lock
details.

- **Extraction, not a shortcut.** M5d refactors the existing capture phases (scope, selection,
  emptiness, revision bound, consistency, readiness, chunk bound, exclusions) into one reviewed,
  public persistence function that takes a caller-owned `Session` and the transaction's database
  time, for example `capture_in_transaction(session, captured_at, actor, *, vendor_id, identity,
  config) -> RetrievalSnapshot | SemanticOutcome`. `capture_snapshot` keeps its signature, its
  read-only REPEATABLE READ transaction, its fixed errors and their precedence, and calls the
  same function inside `run_read`. Nothing reaches into `read_snapshot` or another private
  helper. M5d's tests rerun the M4d capture cases and add an equivalence test (both paths yield
  the same snapshot facts over the same data).
- **Creation transaction.** A new reviewed helper opens the creation transaction:
  `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ WRITE` as its first statement, then the
  single `SELECT clock_timestamp()` that **establishes the transaction snapshot** and becomes
  `captured_at`, then a transaction-local statement timeout. In that one transaction it runs the
  capture function, inserts the review, every binding, the exclusions record and the pinned
  configuration (template, planner, prompt, model and retrieval/profile identifiers and digests,
  and the snapshot digest), and enqueues `run_review` with payload `{review_id}` through the
  existing `enqueue(session, …)`. *(Corrected in Prompt 169: the earlier blanket statement about
  inserts and concurrent-update failures is withdrawn.)* Unique-constraint violations,
  concurrent idempotency races (for example a repeated client key committed concurrently, or
  `ON CONFLICT` against a row invisible to the snapshot, which PostgreSQL reports as a
  serialization failure), other serialization failures, lock or statement timeouts and commit
  failures can all still occur in this transaction. Creation stays atomic whatever happens.
  Known retryable conflicts receive a fixed classification; any retry runs in a **fresh**
  transaction (which can then see and return an existing review); nothing is retried inside the
  failed transaction, not every failure is retryable, and no unbounded retry loop is proposed.
  The detailed SQL, idempotency and retry policy belong to the M5d review.
- **When eligibility is established.** At the snapshot-establishing statement, with M4d's race
  semantics: an activation, readiness change, upload or failure committed before it is visible;
  one committed after it is not, even before capture's first data query, and a revision captured
  there stays eligible after later supersession.
- **Visibility and atomicity.** Nothing about the review is visible to other transactions until
  commit. The review, bindings, exclusions, configuration and job commit together or not at all;
  a semantic capture outcome, constraint failure, timeout or error rolls the whole transaction
  back. A commit whose outcome is unknown surfaces as a fixed error that does **not** claim the
  transaction rolled back; the idempotency key lets the caller discover later whether creation
  happened.
- **Trusted loading and its threat boundary.** The persisted bindings are trusted because the
  application wrote them inside the transaction that established eligibility, **not** because a
  digest or timestamp was stored. The loader reads the rows for `(tenant_id, review_id)`, rebuilds
  `RetrievalSnapshot` through its validating constructor, recomputes the canonical digest and
  compares it exactly with the stored one; every later retrieval still runs the M4d binding
  recheck. The digest only detects disagreement between stored rows and the stored digest. The
  boundary assumes the database changes only through application paths and migrations; it gives
  no protection against a direct database writer or malicious in-process code, and the public
  M4d seams still accept trusted in-process snapshots. The M4d limitation is closed **for review
  paths only**, and only once M5d is implemented and verified, with the handler (M5g) obtaining
  its snapshot solely from the loader (enforced by structure and a test).

##### Production dispatch and enqueue (W8 reconciled)

[REC] Until a reviewed wiring decision, every M5 seam is **internal or test-only**:

- M5d's creation function enqueues `run_review` because that enqueue must be atomic with
  creation, but **no endpoint, CLI or production path calls it** in M5d–M5h; only tests do.
- `run_review` is **not** added to `production_registry()`. Because the worker claims only its
  registry's kinds, a production worker never receives a `run_review` job; a packaging/registry
  test pins that the production registry lacks `run_review` and that no API route or `eg-admin`
  command imports the creation seam.
- M5g provides `make_run_review_handler(provider)` requiring an explicitly supplied
  `ModelProvider`; tests build their own registry with it and a scripted fake. There is no
  default provider, so no production fake judgment can arise.
- Enqueue from a production path, the `run_review` registration and the configured provider
  become available **together** in one later reviewed slice (with the live-wiring decision after
  M5h, or in M7); until then no review is created outside tests.

##### Call budgets, repair and terminal state (Correction D)

[REC] Sequence-level rules for M5e and M5g (details in their reviews):

- **Reservation before dispatch.** Before each `call_validated`, a fenced transaction inserts a
  `started` call reservation for `(review, question, stage)` with the next sequence number and
  its kind (`initial`, `repair` or `retry`). The reservation is the budget unit: a `started` row
  abandoned by a crash still consumes it. Because the counters are rows, they survive reclaim and
  process restart. When the call returns, `ctx.check()` runs first (W7); then the outcome,
  model used, usage and latency complete the reservation, in the same fenced transaction as the
  stage output when the stage succeeds.
- **One stage budget, never reset.** At most **3 reservations per `(review, question, stage)`
  across all job attempts**, of which **at most one is a repair** for the whole stage (not one per
  attempt). Neither limit resets on reclaim or restart.
- **Repair versus retry.** `invalid_output` → one repair request (a different request and digest,
  built by M5c from fixed failure categories, never from raw output). `timeout` and
  `provider_failed` → a retry of the same request. `refusal`, `max_tokens` and `unexpected_stop`
  are terminal for the stage (D9). `model_mismatch` is **terminal for the stage** (W13: it signals
  misconfiguration, so repeating it spends budget without changing the model).
- **Restart after a repair.** On resume the handler reads the reservations: if a repair
  reservation exists (`started` or completed), no further repair is allowed; an abandoned repair
  may be re-dispatched once as a `retry` of that repair request if budget remains.
- **Reuse eligibility.** A committed stage row is the **only** thing resume reuses as success.
  Call records (including `invalid_output`, timeout and abandoned `started` rows) are audit and
  budget evidence; they are never treated as a completed stage and never replayed as output.
  Raw model output is not stored in call records (content capture is off by default, §4); a
  validated output is stored only as part of a committed stage row.
- **Stage versus question failures.** A Verification stage ends `verified` (a `Verification` with
  derived status) or `unresolved` with a fixed reason. An Analysis failure records the analysis
  as `unresolved` and **does not alter or erase a committed `Verification`** or relabel its
  evidence as `missing`. In `ReportContent` such a question appears in `unresolved_question_ids`
  (allowed by the existing coverage rules) with no fabricated finding. The valid `Verification`
  stays persisted; the question is unresolved **for analysis**, without falsifying or erasing the
  Verification. Whether and how its status appears in the report is governed by the
  report-integrity invariant below (W14).
- **Review status on terminal jobs.** A job can become `dead` through reclaim or sweep without a
  handler, so no handler can be relied on to write a final failed state. [REC] Review status is a
  **read-time projection** (like M3e's ingestion state): `completed` only if the final atomic
  commit exists; `failed` if the canonical job is `failed` or `dead` without it; otherwise queued
  or running. No compensating write is made by a worker, and a worker that has lost its fence
  writes nothing (W15).
- **Completion after rendering.** The final step renders (M5f) and stores the report output, marks
  the review complete and records job success in **one** `fenced(finish=True)` transaction, so a
  review is never complete without its output.

##### Report integrity (Prompt 169)

[DECISION] (set by the reviewer in Prompt 169 as the condition on W14; binding on M5f, M5g and
M6) **Invariant:** every substantive
finding, evidence status, quote, unresolved reason or other review conclusion presented as part of
the approval or export artifact must be represented in that artifact's **canonical hashed
content**, or be deterministically derived solely from that content. A report must never acquire
a displayed conclusion from unhashed stage rows after its content hash is computed; display-only
Markdown is rendered from the hashed content alone.

[REC] Consequences for the sequence:

- **M5f settles the representation** before the M5g completion path uses it. The accepted M1
  `ReportContent` holds findings and unresolved question IDs only, so preserved Verification
  statuses, accepted quotes outside findings and unresolved reasons are not in it today.
- **Either** M5f proposes an explicitly versioned canonical schema that wraps `ReportContent`
  (for example a new schema ID covering `ReportContent` plus per-question verification status,
  accepted quotations and fixed unresolved-reason codes), with its own canonical bytes and digest
  and a reviewed compatibility plan for M6; **or** the report omits those extra conclusions until
  such a reviewed, hash-covered representation exists.
- The accepted M1 hash schema `evidenceguard.report-content.v1` is **not** changed silently; a
  wrapper is a new, versioned schema, not a reinterpretation of the old one.
- M6 approves, finalizes and exports the **exact hash-covered report revision**; stage rows remain
  audit evidence behind it, never an additional source of displayed conclusions.

*Recommendation (W14):* the versioned wrapper, because unresolved reasons and preserved
Verification statuses are what a reviewer needs to judge an unresolved question. *Tradeoff:* a
new schema and M6 compatibility work versus a thinner approval artifact that shows only findings
and unresolved IDs. No new schema is specified or implemented here.

##### Canary and prompt-boundary coverage (Correction E)

[REC] Provenance checks prove quote existence only; they do not detect semantic prompt injection.
Delimiting evidence does not make a live model injection-proof. Production code holds no canary
list. **The original criterion, "The injection canary never appears in output", is kept
unchanged** (Prompt 169). Its approved scope is an end-to-end **contract assertion** over the
specified M5 scripted-fake fixtures:

- **Acceptance fixture (must pass).** A Tenant A corpus fixture that includes a dedicated copy,
  under `tests/`, of the injected trust-center page. Its instruction asks the model to emit an
  obviously synthetic canary **assembled from parts** given in the instruction, so the canary is
  absent verbatim from every document. The fixture asserts that the injected chunk is in the
  retrieved evidence for at least one question **and** inside an evidence block of that
  question's assembled model request. The scripted responses are ordinary (they do not follow the
  instruction) and may cite genuine quotations from the injected page. The review runs end to end
  through the M5g handler. The **acceptance checker** then asserts that the canary (exact token,
  and its case-insensitive form) appears in none of: the canonical hashed report content bytes;
  the Markdown derived from it; every committed stage output for the review (verifications,
  claims, quotations, rationales and findings, including titles, statements and follow-up
  questions); call records; and the logs and error codes captured during the run.
- **Negative control (expected checker failure).** The same fixture with a scripted response that
  emits the canary in free-text fields (for example a rationale and a finding statement). The
  **same** acceptance checker must report failure, and the test asserts that it does. This proves
  the checker detects the token; it also shows that no production rule blocks such emission.
- **Limitation probe (labelled separately, not an acceptance fixture).** A fixture variant whose
  authorized document contains the canary **verbatim**, with a scripted genuine quotation of it:
  provenance accepts the quotation and the report contains it, and the test asserts exactly that.
- Passing the acceptance fixture does **not** establish live-model injection resistance and does
  not show that provenance checks reject arbitrary malicious text.

The M5 fixtures (W10) also keep these classes distinct from the authorized-document injection
fixture:

1. **Cross-tenant leakage.** Tenant B's canaries are never retrieved for Tenant A (M4d isolation).
   Assertion: no assembled request for Tenant A contains them, and they appear in no persisted
   stage row, call record, rendered report, error or log; a scripted citation of a Tenant B chunk
   is rejected as unretrieved.
2. **Forged or unretrieved citations.** A scripted response citing an unretrieved or forged chunk
   ID, or a quote absent from the cited chunk, gives `citation_rejected`; the rejected citation is
   not stored as accepted evidence and not rendered.
3. **Authorized injected-document quotes.** Covered by the acceptance fixture (genuine quotations
   that cannot contain the assembled canary) and, separately, by the limitation probe (a verbatim
   canary in an authorized quotation passes the production rules and is stored and rendered).
4. **Free-text fields (documented limitation).** With no production denylist, canary text in
   `rationale`, claim `text`, finding `title` or `statement`, or follow-up questions would be
   validated, persisted in the stage row, carried into the hashed report content and rendered; the
   negative control demonstrates this and that the checker catches it.
5. **Persisted versus rendered versus logged.** Call records hold digests, outcomes and counts, no
   content; stage rows hold validated outputs; the report renders only its hashed content (report
   integrity, above); nothing logs content; errors are fixed codes.

Real-model obedience to injected text is measured only by the paired live evaluation in M7.

**M5c prompt boundary.** Plain concatenation of document text into `<evidence id=…>` blocks is not
sufficient: text containing a closing tag or delimiter-like content could forge block boundaries.
M5c must specify a safe encoding (for example escaping `&`, `<` and `>` in evidence text and
using only validated chunk IDs as attributes) and how quotes returned in encoded form map back to
the original text for M5b matching.

##### M5 acceptance criteria mapped to slices and tests

[REC] Every original criterion is preserved. Evidence is contract evidence with the scripted fake
and PostgreSQL; none of it measures a live model.

| Original M5 criterion | Slice(s) | Planned test evidence |
|---|---|---|
| Invalid output, a refusal, a timeout and a forged chunk ID each end unresolved or rejected | M5a (outcome classification), M5b (forged or unretrieved chunk → `citation_rejected`), M5e/M5g (budgets, unresolved stage persisted) | DB-independent outcome and provenance tests; PostgreSQL handler tests with scripted invalid (including after a failed repair), refusal, timeout (after the retry budget) and forged-ID responses asserting the persisted unresolved state, its reason and no accepted citation |
| A revision activated after a review started is not used by that review, including after a resume | M5d (creation transaction and trusted loader), M5g | PostgreSQL: create a review, activate and index a replacement, run; separately interrupt after a stage commit, activate a replacement, reclaim and resume; assert only snapshot chunks in retrieved-passage rows and results |
| A worker killed after a stage commit resumes without duplicate rows | M5e (unique keys, identical-replay no-op), M5g (skip committed stages) | PostgreSQL: a controlled interruption after a stage commit, lease expiry and reclaim; assert one row per `(review, question, stage)` and no new reservation for the committed stage |
| A worker killed between a provider response and its commit repeats the call once (the second call is recorded; no duplicate stage row) | M5e (reservations), M5g (test-only interruption hook) | One **controlled** PostgreSQL test: the hook interrupts after the fake returns and before the stage commit; after reclaim the fake's call count for that key is exactly 2, the first reservation remains `started`, the second is completed and one stage row exists. This shows that scenario only; it is **not** an exactly-once or one-retry guarantee (W5) |
| A stale worker's stage writes are rejected | M5e (every write fenced), M5g | PostgreSQL: a reclaimed token's reservation, stage, output and completion writes are refused and change nothing (M3 fence pattern) |
| The injection canary never appears in output (criterion unchanged) | M5b, M5c, M5f, M5g | End-to-end contract assertion over the specified scripted-fake fixtures: the **acceptance fixture** (authorized injected document in the retrieved evidence and the assembled request; the checker finds no canary in the hashed report content, its Markdown, committed stage outputs, call records, or captured logs and errors) must pass; the **negative control** (canary-emitting script) must make the same checker fail. Separately: cross-tenant isolation and forged-citation tests, and the labelled **limitation probe** (verbatim canary in a genuine authorized quotation is accepted). Not live-model injection resistance (M7) |

##### Sequence-level design decisions

Each gives a recommendation and its tradeoff. Items marked *approved choice* were approved by the
reviewer in Prompt 169 and accepted with the sequence in Prompt 170 as settled design choices;
W9 and W12 leave their details to the M5h and M5b reviews. This is not acceptance of any later
slice's detailed specification or of any implementation.

1. **W1 First slice** (*approved choice, Prompt 169*). [REC] M5a as specified below, pure and database-free.
   *Tradeoff:* the trusted-snapshot limitation stays open until M5d (documented; no endpoint or
   handler uses retrieval meanwhile) versus building persistence before its values are settled.
2. **W2 Placement** (*approved choice, Prompt 169*). [REC] Raw output schemas and provenance/status derivation in
   the domain (persistence must store and revalidate them and cannot import
   `evidenceguard_agents`); the provider protocol, fake, prompts, planner and adapters in
   `evidenceguard_agents`, importing only `evidenceguard_domain` (and later, if needed,
   `evidenceguard_observability`). *Tradeoff:* a larger domain package versus a persistence
   dependency on agents, which §3 forbids.
3. **W3 Review template** (*approved choice, Prompt 169*). [REC] One packaged TOML template (`tomllib`, no new
   dependency), SHA-256 pinned in the review configuration, independent of the ground truth.
   *Tradeoff:* diverging from §7's YAML sketch versus a YAML dependency.
4. **W4 Repair and call budget** (*approved choice, Prompt 169*). [REC] As in Correction D: 3 reservations per stage across
   all attempts, at most one repair per stage, terminal outcomes as listed. *Tradeoff:* bounded
   cost and predictable termination versus more chances for a flaky provider.
5. **W5 Repeated crashes** (*approved choice, Prompt 169*). [REC] No exactly-once claim. An uncommitted response is lost and
   the call may repeat on each reclaim, bounded by W4's persisted budget and the job's
   `max_attempts` (default 3; reclaim increments `attempt`, ending `dead` at the cap); the review
   then projects as failed (W15) with committed stage rows retained. The controlled single-repeat
   test is one scenario, not a guarantee. *Tradeoff:* possible duplicate cost versus exactly-once
   machinery that a remote API cannot honour.
6. **W6 Started-call reservations** (*approved choice, Prompt 169*). [REC] Commit the reservation before dispatch and
   complete it with the stage output (Correction D). *Tradeoff:* an extra short transaction per
   call versus invisible repeated cost.
7. **W7 Cancellation and lease precedence** (clarified in Prompt 169). [REC] For the future M5g
   handler, as in M4c:
   - after `call_validated` **returns** an outcome, `ctx.check()` runs before the handler acts on
     it (classifying, completing the reservation or writing a stage);
   - if `call_validated` **raises** an ordinary local or configuration error (such as
     `ModelClockError` or `InvalidModelRequestError`), `ctx.check()` likewise runs before that
     error is classified, so latched cancellation or lease loss takes precedence over it too;
   - process-control exceptions propagate unchanged and are never turned into job errors;
   - a worker that has lost its fence performs **no** outcome, stage or compensating write;
   - a pre-dispatch reservation that was already committed remains audit and budget evidence
     (as an abandoned `started` row if nothing completes it);
   - worker shutdown is the existing retryable `worker_shutdown`; no user cancel endpoint (§6
     later addition). M4d retrieval errors and M5a outcomes map to fixed `JobErrorCode`s in the
     M5g specification.

   M5a's boundary stays independent of `JobContext`. *Tradeoff:* checks only at explicit
   boundaries, never interrupting a synchronous call.
8. **W8 Endpoints and production dispatch** (*approved choice, Prompt 169*). [REC] As reconciled above: internal and
   test-only seams in M5, no production registration, endpoint or CLI; enablement later as one
   reviewed unit with a configured provider. *Alternative:* `POST /v1/reviews` and
   `GET /v1/reviews/{id}` in M5d. *Tradeoff:* no user-facing review in M5 versus exposing a
   workflow that cannot produce real judgments.
9. **W9 Anthropic adapter** (*details are a later review obligation of M5h*). [OPEN] The M5 milestone names "Anthropic and scripted fake providers";
   it is not removed. [REC] M5h adds the adapter mocked only, mirroring M4f; live wiring and the
   first live call are M7. The SDK-versus-standard-library transport, its timeout guarantees and
   any model-alias behaviour are decided in M5h's review; no live model-name compatibility is
   claimed now. *Tradeoff:* SDK convenience versus a new dependency and mocked-only evidence.
10. **W10 Canary fixtures** (*approved choice, Prompt 169*). [REC] As in Correction E: dedicated
    copies under `tests/`; the **acceptance fixture** (authorized injected document retrieved and
    in the assembled request, instruction-assembled canary absent from documents, checker over the
    listed artifacts must pass); the **negative control** (canary-emitting script, same checker
    must fail); and the separately labelled **limitation probe** (verbatim canary in a genuine
    authorized quotation is accepted and rendered). The original criterion is unchanged; the
    accepted M4e corpus is unchanged. *Tradeoff:* fixture duplication versus reopening accepted
    M4e data.
11. **W11 Existing contracts** (*approved choice, Prompt 169*). [REC] Keep `Verification`, `Citation` and `Finding`
    unchanged; add surrounding values (validated claims, `provenance_check`, reservation and call
    references); derived status must satisfy the existing validator. *Tradeoff:* two related shapes
    versus changing an accepted M1 contract.
12. **W12 Quote matching** (*direction retained; exact rules await the M5b specification*).
    [OPEN] Direction: a normalized-substring match. M5b must define the exact Unicode
    normalization and whitespace rules, match the chunk's body text and its
    repeated header text **independently** (never a quote spanning them, and never joining
    unrelated spans), and store and display the **exact original evidence substring** that
    matched, not the model's string. Original evidence text is never modified.
13. **W13 Model mismatch** (*approved choice, Prompt 169*). [REC] Terminal for the stage, recorded with the model actually
    used. *Alternative:* retryable within the budget. *Tradeoff:* faster failure on
    misconfiguration versus tolerating transient routing differences (to be revisited with M5h
    alias behaviour).
14. **W14 Preserved verification in reports** (*approved choice, Prompt 169, subject to the
    report-integrity invariant*). [REC] The valid Verification stays persisted and the question is
    unresolved for analysis. Its status and the unresolved reason appear in the approval or export
    artifact **only** if they are in its hashed content (preferably through a versioned wrapper
    around `ReportContent` specified in M5f and reviewed for M6), and are otherwise omitted until
    such a representation exists; nothing is displayed from unhashed stage rows. *(The Prompt 168
    suggestion of a Markdown-only display is withdrawn.)* *Tradeoff:* a new versioned schema versus
    a thinner approval artifact.
15. **W15 Review status ownership** (*approved choice, Prompt 169*). [REC] A read-time projection from the review's final
    commit and its canonical job, with no compensating writes. *Alternative:* a stored status
    updated by a fenced terminal hook in the runtime. *Tradeoff:* no new runtime hook and no stale
    writer versus a status that must be derived on every read.

#### M5a model-call contracts and scripted fake provider (ACCEPTED at review, Prompt 170; implementation pending)

**Status.** **Specification accepted at external review in Prompt 170; implementation pending.**
Proposed in Prompt 167, corrected in Prompt 168 (strict JSON parsing and deep immutability in B
and B1, the call algorithm and clock contract in D–D2, fake bounds and the corrected privacy
statement in D2 and E), clarified in Prompt 169 (the clock arithmetic and bounds in D1), and
accepted in Prompt 170 with a clarification of the planned clock-test wording (G). The accepted
recommendations and W-A1 to W-A11 (section I) form the implementation contract; no M5a
specification decision remains open. At acceptance no M5a module, test, workflow extension or
ADR-0019 existed (historical). **Implemented by Claude Code in Prompt 171, corrected in Prompt 172
and accepted at external review in Prompt 173 for a local commit**; publication, Linux and current-version CI were then pending (see the
[implementation status](#m5a-implementation-status-accepted-for-a-local-commit-prompt-173-ci-pending) below and
[ADR-0019](decisions/0019-model-call-contracts.md)). **Published and verified in feature-branch CI at
`9ba6a488` in Prompt 174; published on `main` at `f04e0957` in Prompt 176 and verified in
main-push CI** ([feature evidence](#m5a-feature-branch-ci-evidence-prompt-174), [main
evidence](#m5a-main-publication-evidence-prompts-176177)). M5a is
pure: no database, migration, network, credentials, settings, handler registration, prompts or
orchestration.

**Purpose.** Fix the values every later slice uses to ask for a structured judgment and to
classify what came back, and provide a deterministic scripted provider so that refusal, invalid
output, timeout, provider failure and model mismatch can be produced on demand in CI. It does not
check provenance (M5b), assemble prompts (M5c) or persist anything (M5d/M5e). It therefore does
**not** close the trusted-snapshot limitation; M5d does, for review paths, through its creation
transaction and trusted loader (above).

##### A. Placement and imports

| File (new) | Contents | May import |
|---|---|---|
| `packages/domain/evidenceguard_domain/model_calls.py` | `ModelPurpose`, `PromptRef`, `ModelUsage`, `StopKind`, `CallOutcome`, `StructuredRequest`, `ProviderResponse`, `StructuredResult`, the canonical request encoding, bounds and fixed errors | domain, standard library |
| `packages/domain/evidenceguard_domain/agent_outputs.py` | `VerifierOutput`, `ClaimOutput`, `QuoteRef`, `AnalystOutput`, `FindingOutput`, the closed schema registry and `parse_output` | domain, standard library, Pydantic |
| `packages/agents/evidenceguard_agents/__init__.py`, `py.typed` | New import package (§3) | — |
| `packages/agents/evidenceguard_agents/providers.py` | `ModelProvider` protocol, `ModelCallTimeout` marker, `call_validated` | domain, standard library |
| `packages/agents/evidenceguard_agents/scripted.py` | `ScriptedFakeProvider` and its script steps | domain, agents, standard library |

[REC] Packaging: add `evidenceguard_agents` to the wheel and sdist lists and to strict mypy. Extend
`tests/test_packaging.py`: no package may import `evidenceguard_agents` except the apps and
`evaluation`; `evidenceguard_agents` must not import `evidenceguard_persistence`,
`evidenceguard_retrieval`, `evidenceguard_api`, `evidenceguard_worker` or SQLAlchemy; and the M5a
agents modules must not import `socket`, `ssl`, `http`, `urllib`, `os`, `pathlib` or `tomllib`
(so the fake cannot read the ground truth, a file or the network; M5c's packaged-artifact loading
and M5h's adapter get their own reviewed allowlists). M5a modules import no third-party package
except Pydantic in `agent_outputs`. No dependency or lockfile change.

##### B. Values and invariants

[REC] Call values (`model_calls`) are frozen dataclasses with exact-type validation in the M4d
style (`type(x) is …`, no coercion, `bool` is not an `int`, tuples only, no stripping or
normalization, unknown keywords rejected, derived fields computed by the constructor, revalidation
on `dataclasses.replace`). Output values (`agent_outputs`) are strict, frozen Pydantic models
under a dedicated base (not `DomainModel`), parsed only through the path in B1.

- **`ModelPurpose`**: `verifier` or `risk_analyst`. Each maps to exactly one output schema:
  `verifier_output_v1` → `VerifierOutput`, `risk_analyst_output_v1` → `AnalystOutput`. The
  caller cannot choose a schema.
- **`PromptRef(prompt_id, version, sha256)`**: `prompt_id` matches `^[a-z][a-z0-9_]{0,31}$`;
  `version` an `int` 1–999; `sha256` 64 lowercase hex. M5a checks shape only; M5c binds it to a
  packaged artifact.
- **`StructuredRequest(purpose, prompt, model_id, question_id, system_text, user_text,
  max_output_tokens, timeout_ms)`**: `model_id` matches `^[a-z0-9][a-z0-9.-]{0,63}$`;
  `question_id` matches the existing `QuestionId` pattern; `system_text` 1–64,000 UTF-8 bytes and
  `user_text` 1–400,000 UTF-8 bytes (20 chunks of at most 4,000 code points plus framing), both
  strictly UTF-8 encodable, without NUL; `max_output_tokens` an `int` 1–8,192; `timeout_ms` an
  `int` 1,000–120,000 (default 60,000, §8). Derived: `output_schema` and `request_sha256`.
- **`ModelUsage(input_tokens, output_tokens)`**: `int`s 0–10,000,000. Descriptive only; no price.
- **`StopKind`**: `end_turn`, `refusal`, `max_tokens`, `other`. Adapters map provider stop reasons
  onto these; only `end_turn` can complete.
- **`ProviderResponse(stop_kind, output_text, model_used, usage)`**: what a provider returns.
  `output_text` 0–65,536 UTF-8 bytes; `model_used` matches the `model_id` pattern; `usage` is
  exactly a `ModelUsage`. It is treated as untrusted content even from a fake.
- **`CallOutcome`**: `completed`, `refusal`, `max_tokens`, `unexpected_stop`, `invalid_output`,
  `model_mismatch`, `timeout`, `provider_failed`.
- **`StructuredResult(request_sha256, purpose, question_id, outcome, dispatched, output,
  model_requested, model_used, usage, latency_ms)`**: every field is validated on direct
  construction, and the combinations must match exactly one row of this table (anything else is
  `InvalidModelValueError`):

  | `outcome` | `dispatched` | `output` | `model_used` | `usage` | `latency_ms` |
  |---|---|---|---|---|---|
  | `completed` | true | exactly the purpose's schema type | equals `model_requested` | present | `int` ≥ 0 or absent |
  | `refusal`, `max_tokens`, `unexpected_stop`, `invalid_output` | true | absent | equals `model_requested` | present | `int` ≥ 0 or absent |
  | `model_mismatch` | true | absent | present, differs from `model_requested` | present | `int` ≥ 0 or absent |
  | `timeout` | true | absent | absent | absent | `int` ≥ 0 or absent |
  | `provider_failed` | true or false | absent | absent | absent | absent if not dispatched, else `int` ≥ 0 or absent |

  `purpose` must map to `output`'s schema; `request_sha256` is 64 lowercase hex; `question_id`
  and both model IDs match their patterns. `latency_ms`, when present, is an `int` from 0 to
  `LATENCY_MS_BOUND` (D1); it is descriptive, never a benchmark.

Output schemas (shape only; provenance, status rules and authorization are M5b). Every collection
is a **tuple** (JSON arrays decode to tuples through B1), and every nested value is another frozen
output model, an enum member or a string:

```text
VerifierOutput  {verdict: Verdict, claims: tuple[ClaimOutput, …] 0–10, rationale: str 1–2000}
ClaimOutput     {text: str 1–1000, citations: tuple[QuoteRef, …] 0–8}
QuoteRef        {chunk_id: canonical lowercase hyphenated UUID string, quote: str 1–1000}
AnalystOutput   {findings: tuple[FindingOutput, …] 0–20}
FindingOutput   {question_ids: tuple[QuestionId, …] 1–20 distinct, title: str 1–200,
                 severity: Severity, statement: str 1–2000,
                 citations: tuple[QuoteRef, …] 0–8,
                 follow_up_questions: tuple[str 1–500, …] 0–5}
```

The model never supplies `evidence_status`, `source_type`, tenant, revision or document IDs,
authenticity or `provenance_check`; those come from trusted data in M5b. Exact duplicate
`QuoteRef`s within one claim or finding are invalid. Strings reject NUL and lone surrogates and
are never stripped. `QuoteRef.chunk_id` stays a pattern-checked string (so a non-canonical
spelling is rejected rather than normalized by a UUID parser), with a property returning the
`UUID`.

##### B1. Strict output parsing and immutability (Prompt 168 correction B)

[REC] Strict Python-mode validation of a `json.loads` dictionary would reject valid JSON enum
strings and arrays, so the parse path is a bounded preliminary scan followed by strict
**JSON-mode** validation of the same text, without weakening strictness globally:

1. **Size:** `output_text` is at most 65,536 UTF-8 bytes (already enforced by `ProviderResponse`).
2. **Preliminary scan:** `json.loads(output_text, object_pairs_hook=…, parse_constant=…)` with a
   hook that rejects duplicate keys and a constant handler that rejects `NaN`, `Infinity` and
   `-Infinity`; trailing text after the value is already a decode error. The decoded value must
   be a JSON object; a walk of it rejects nesting deeper than 8 and more than 2,000 values in
   total. The decoded value is then discarded.
3. **Schema validation:** `model_validate_json(output_text)` on the purpose's schema with
   `strict=True`. In JSON mode, strict validation accepts JSON strings for enum values and JSON
   arrays for tuple fields while still rejecting numeric enums, numbers for strings, strings for
   numbers, unknown fields (`extra="forbid"`) and anything the field validators reject. The scan
   in step 2 exists because the JSON-mode parser alone does not reject duplicate keys. That
   Pydantic 2.14 accepts JSON strings and arrays here is design intent to be **confirmed by the M5a
   tests**, not a fact established by this document.
4. **Result:** any failure in steps 1–3 makes `parse_output(purpose, text)` return no output, and
   `call_validated` classifies the call `invalid_output`; nothing from the failure is kept.

**Deep immutability.** Collections are tuples of frozen models, enum members or strings; there is
no `list`, `dict` or `set` anywhere in an output value, so `frozen=True` is not relied on to
freeze a mutable container. **Direct construction** (for tests and M5b) runs strict Python-mode
validation: enum members and tuples are required; a list or a raw enum string is rejected.
**Copy and update:** `model_copy` is overridden to rebuild through validation (as `DomainModel`
does), so an update cannot produce an unvalidated value. Pydantic's `model_construct`,
`object.__setattr__` and similar bypasses can still create or mutate values; trusted in-process
code is not a security boundary, and domain code never uses those bypasses.

**Validation-error privacy.** A raw Pydantic `ValidationError` can contain the model output and
input values. Therefore every public entry point of the output types (`__init__`,
`model_validate`, `model_validate_json`, `model_validate_strings` and `model_copy`) translates an
ordinary validation failure (`ValidationError`, `ValueError`, `TypeError`) into a **fresh**
`InvalidModelValueError` raised **after** the `except` block, so it has no `__cause__` or
`__context__`; `hide_input_in_errors=True` is set as defence in depth. `parse_output` maps every
failure to "no output" for `invalid_output`. Process-control exceptions (`BaseException` that is
not `Exception`) propagate unchanged. The representation rule (`repr`, `str` and Pydantic's
`__repr_args__`) applies to **every** output type, including nested `ClaimOutput`, `QuoteRef` and
`FindingOutput`: type name and counts only, never claim text, quotes, rationale, titles,
statements or follow-up questions. Explicit data access (`model_dump`, attributes) returns content
by design.

##### C. Canonical request encoding

[REC] `eg-model-call-canonical-v1`, with the M4d byte rules (`sort_keys`, compact separators,
`ensure_ascii=True`, `allow_nan=False`, ASCII bytes, lowercase hex SHA-256):

```json
{"canonical":"eg-model-call-canonical-v1","kind":"model_request","purpose":"verifier",
 "output_schema":"verifier_output_v1","prompt":{"id":"…","version":1,"sha256":"…"},
 "model_id":"…","question_id":"…","max_output_tokens":2048,
 "system_sha256":"…","user_sha256":"…"}
```

Texts enter as the SHA-256 of their exact UTF-8 bytes, so the digest is fixed-size and contains no
document text. `timeout_ms` is excluded (it does not change the content asked for). Review, stage
and attempt are excluded; persistence scopes reuse by its own keys (M5e). The digest identifies
the content of a request for reuse and audit; it is **not** authorization, proof that a call was
made, or proof of any past state, and it is recomputable by anyone. Pinned digests in tests.

##### D. Provider protocol, call boundary and scripted fake

```text
class ModelProvider(Protocol):
    @property
    def provider_id(self) -> str: ...                    # e.g. "scripted-fake"
    def generate(self, request: StructuredRequest) -> ProviderResponse: ...

class ModelCallTimeout(Exception): ...                   # raised by adapters for a timeout

call_validated(provider: ModelProvider, request: StructuredRequest, *,
               clock: Callable[[], float] = time.monotonic) -> StructuredResult
```

[REC] `call_validated`, in order (Prompt 168 correction C). Every failure flag is set inside an
`except` block and acted on after it; fresh fixed errors and results are built outside every
handler, so nothing retains an exception, message, cause or context.

1. **Arguments.** `type(request) is StructuredRequest`; the request is then **revalidated** by
   rebuilding it through its constructor from its own fields and comparing the derived
   `output_schema` and `request_sha256` with the stored ones (this catches a bypassed or mutated
   value); `clock` is callable. Any failure raises `InvalidModelRequestError`
   (`invalid_model_request`) with **zero** `generate` calls.
2. **Start time.** `start = clock()` (D1). A failure raises `ModelClockError`
   (`model_clock_failed`), again with zero `generate` calls; a broken local clock is never reported
   as a provider timeout.
3. **Provider identity.** Read `provider.provider_id` once. It must be exactly a `str` matching
   `^[a-z][a-z0-9-]{0,31}$`. An ordinary `Exception` from the getter, or any other value, gives
   `provider_failed` with `dispatched = false` and no `generate` call.
4. **Dispatch.** Call `provider.generate(request)` exactly once. `ModelCallTimeout` (or a
   subclass) → `timeout`; any other ordinary `Exception`, including an `InvalidModelValueError`
   raised while the provider tried to construct a malformed `ProviderResponse` inside `generate`,
   → `provider_failed`.
5. **End time.** `end = clock()` immediately after `generate` returns or raises (D1).
6. **Response.** For a returned value: `type(value) is ProviderResponse`, then revalidation through
   its constructor, including `type(value.usage) is ModelUsage` and the usage bounds. Any failure →
   `provider_failed` (`model_used` and `usage` absent: an invalid response is not trusted for
   accounting).
7. **Classification**, in this precedence: `model_used != model_id` → `model_mismatch`, **whatever
   the stop kind** (content from the wrong model is not attributed); then `refusal` → `refusal`;
   `max_tokens` → `max_tokens`; `other` → `unexpected_stop`; `end_turn` → `parse_output` (B1):
   no output → `invalid_output`, otherwise `completed`.
8. **Result.** A fresh `StructuredResult` matching the table in B.

At most one `generate` call happens per `call_validated`, and none for invalid arguments or a
failed start-time reading. Process control (`BaseException` that is not `Exception`) raised by
`clock`, `provider_id` or `generate` propagates as **the same object**, unwrapped. The boundary
knows nothing about jobs: M5g calls `ctx.check()` after it returns and before acting on the
outcome (W7).

**Timeout semantics.** `timeout_ms` is passed to the adapter inside the request. `timeout` means
only that the adapter raised `ModelCallTimeout`. A synchronous boundary **cannot interrupt** a call
by checking elapsed time afterwards, so `call_validated` imposes no hard deadline: a response that
arrives after `timeout_ms` is classified normally, with its latency recorded, and a blocking
adapter blocks the caller. Transport guarantees (connection, read and cleanup timing, retries)
belong to the M5h adapter review; no M4f-style guarantee is promised for a model transport that is
not yet specified. The scripted fake never blocks.

##### D1. Clock contract (Prompt 168 correction C)

*Corrected in Prompt 169:* finite endpoints do not guarantee finite or convertible arithmetic
(for example `1e308 - (-1e308)` overflows, and `math.isfinite(10**1000)` raises
`OverflowError`), so the policy below validates each reading with integer-safe comparisons, bounds
it, and treats every failure while validating or calculating as "unusable".

- **Reading bound (engineering choice).** `CLOCK_READING_BOUND = 2**53` seconds
  (9,007,199,254,740,992), the range in which every integer is exactly representable as a float;
  `time.monotonic` values are far inside it.
- **Usable reading.** The value's type is exactly `int` or exactly `float` (`bool` and every other
  type rejected). An `int` is checked with integer comparisons only, `-2**53 <= value <= 2**53`,
  before any conversion, so a huge integer such as `10**1000` is rejected without calling
  `math.isfinite` or `float`; it is then converted with `float(value)`, which is exact in that
  range. A `float` must satisfy `math.isfinite(value)` and `-2**53 <= value <= 2**53`. Anything
  else, and any ordinary `Exception` raised by the callable or during these checks, makes the
  reading **unusable**.
- **Before dispatch** (step 2): an unusable start reading raises a **fresh** `ModelClockError`
  (`model_clock_failed`) outside any `except` block, with no cause or context and zero `generate`
  calls. A broken local clock is never reported as a provider timeout.
- **After dispatch** (step 5): the end reading is validated the same way. Then, inside one guarded
  block, `delta = end - start` (both bounded floats, so `|delta| <= 2**54` and finite),
  `delta >= 0` is required (time moving backwards is unusable), `ms = delta * 1000.0` must be
  finite and at most `LATENCY_MS_BOUND = 86,400,000` (24 hours, an engineering choice), and
  `latency_ms = int(ms)` (truncating). An unusable end reading, backwards time, an out-of-bound
  result or **any** ordinary `Exception` (`OverflowError`, `ValueError`, `TypeError` and so on)
  while validating or calculating leaves `latency_ms` **absent** and **preserves the provider
  outcome**, including a `completed` result and its output. A latency is never clamped, rounded
  into range or invented.
- No original exception is retained, chained or logged; the fixed error and the absent latency
  carry nothing from it.
- Process control (`BaseException` that is not `Exception`) from `clock`, at either reading or
  during the checks, propagates as **the same object**.

##### D2. Scripted fake (corrected, Prompt 168)

[REC] `ScriptedFakeProvider(model_id="fake-scripted-v1", scripts=…)`:

- **Configuration.** `scripts` maps `(prompt_id, question_id)` to a non-empty tuple of steps:
  `Respond(text, usage=ModelUsage(0, 0))`, `Refuse()`, `StopMaxTokens(text)`, `StopOther()`,
  `Timeout()` (raises `ModelCallTimeout`), `Fail()` (raises a plain `RuntimeError` with a fixed
  message), `WrongModel(model_used, text)`. Bounds: at most 256 keys, 16 steps per key, each text at
  most 65,536 UTF-8 bytes, and at most 4 MiB of script text in total; the constructor copies the
  mapping into immutable tuples and rejects anything else with `InvalidModelValueError`.
- **Memory.** Scripts **do contain raw response text** by design (they are test fixtures), and the
  fake holds them for its lifetime, which is **test-owned**: production code never constructs it.
  Its call history records only `(prompt_id, question_id, request_sha256, step index)` and is
  capped at 4,096 entries; a call beyond the cap raises the fixed failure (`provider_failed`)
  without recording. Its `repr` shows the model ID and counts, never script text.
- **Selection.** Each key has a counter. On entry, under one lock, the fake takes the key's next
  step index and appends the history entry; the step then runs outside the lock. Every step is
  consumed exactly once; a missing key or an **exhausted** script (index past the last step; the
  last step is never repeated) raises the fixed failure. With sequential calls the mapping is
  fully deterministic; with concurrent calls each call still receives a distinct step, in lock
  acquisition order, which the history records, so tests that need a particular order call
  sequentially.
- **Isolation.** Fixtures are supplied by the caller (tests). The fake never reads files, the
  environment, the network or ground truth, and returns its scripted text verbatim, so invalid JSON
  is possible. `provider_id` is `scripted-fake`; its outputs are contract fixtures, never quality
  evidence.

##### E. Errors, privacy and bounds

- Fixed errors in `model_calls`: `InvalidModelRequestError` (`invalid_model_request`) for invalid
  request construction or `call_validated` arguments, `ModelClockError` (`model_clock_failed`) for a
  failed start-time reading, and `InvalidModelValueError` (`invalid_model_value`) for any other
  invalid value, including output types (B1). Messages are the codes; each is raised fresh, outside
  any `except` block, with no cause or context, and no error carries text, quotes, prompts, model
  output, response model IDs or exception text. Nothing in M5a logs.
- `repr`/`str` of every value show purpose, question ID, prompt ID and version, model IDs,
  outcome, counts and digests only, never system or user text, output text, claims, quotes,
  rationale or statements; for output types this covers every nested model (B1).
- Work is bounded by the byte and count limits above; parsing reads at most 65,536 bytes and walks
  at most 2,000 values. **Correction:** the earlier statement that the fake "stores only digests
  and IDs" was wrong: its scripts hold raw text for a test-owned lifetime, while its call history
  holds only digests, IDs and step indexes (D2). These are engineering defaults, not measured
  limits.
- Privacy covers public errors, default representations and logs; as in M4f, it does not cover
  trusted code inspecting frame locals or held values.

##### F. Compatibility

- Reuses `Verdict`, `Severity` and the `QuestionId` pattern; changes no existing contract,
  migration, handler, endpoint, setting or workflow (unless W-A7 is accepted).
- `Verification`, `Citation`, `Finding`, `ReportContent` and the report content hash are unchanged
  (W11); M5b converts validated outputs into them.
- §4's `generate_structured(StructuredRequest[T]) -> StructuredResult[T]` sketch becomes a raw
  `generate` plus one shared validating boundary, so the fake and a future adapter go through
  exactly the same parsing and classification (W-A1).

##### G. Planned tests (not written or run)

*Database-independent* (`tests/test_model_calls.py`, `tests/test_agent_outputs.py`,
`tests/test_scripted_provider.py`, `tests/test_packaging.py`):

- strict construction of every call value at and beyond each bound (bytes and code points,
  supplementary characters, lone surrogates, NUL, `bool` as `int`, lists for tuples, unknown
  fields), and revalidation through `dataclasses.replace`;
- every `StructuredResult` row of the table in B constructed directly, and each invalid
  combination (output with a non-completed outcome, wrong schema for the purpose, missing or equal
  `model_used` for `model_mismatch`, usage on a timeout, latency without dispatch) rejected;
- pinned canonical bytes and digests; digest independence from `timeout_ms`; digest change for
  each included field;
- parsing: valid outputs for both purposes with JSON enum strings and JSON arrays, decoding to enum
  members and tuples; duplicate keys, `NaN`/`Infinity`, trailing text, fenced JSON, top-level
  arrays, excess depth or value count, extra or missing fields, numeric enums, numbers for strings,
  wrong enum values, non-canonical or uppercase UUIDs, oversize text, duplicate quote references
  and the wrong purpose's schema all give `invalid_output`;
- immutability: every nested collection is a tuple; attribute assignment fails; direct
  construction rejects lists and raw enum strings; `model_copy(update=…)` revalidates and rejects
  invalid updates;
- validation-error privacy: canary-bearing inputs to every public constructor and validator raise
  `InvalidModelValueError` with no cause or context, and the canary appears in no message,
  `repr`, `str`, traceback or captured log, including for nested output types;
- the call algorithm: revalidation catching a bypassed request (zero `generate` calls); invalid
  `provider_id` values and a raising getter (no dispatch); malformed `ProviderResponse`
  construction inside `generate`, a wrong return type and invalid nested usage (`provider_failed`);
  model mismatch combined with each stop kind (`model_mismatch` wins); every outcome through the
  scripted fake; exactly one `generate` call otherwise;
- the clock: `bool`, `NaN`, infinity, non-number and raising clocks before dispatch
  (`ModelClockError`, zero calls, no cause or context); the same after dispatch and a backwards
  clock (outcome unchanged, `latency_ms` absent); a slow fake response past `timeout_ms` still
  classified normally;
- clock arithmetic (Prompt 169, test wording clarified in Prompt 170):
  - **invalid start readings**, including `-1e308`, `10**1000`, `2**53 + 1`, `NaN`, infinity,
    `bool`, a non-number and a raising clock, produce a fresh `ModelClockError` with no cause or
    context and **zero** `generate` calls, without `OverflowError` escaping; `2**53` and `-2**53`
    are usable;
  - a **valid start followed by an invalid end reading**, such as `1e308` or `10**1000`, preserves a
    `completed` provider response and its output with `latency_ms` absent;
  - a **valid start and end pair whose elapsed duration exceeds** `LATENCY_MS_BOUND` likewise
    preserves the outcome with `latency_ms` absent;
  - ordinary arithmetic or validation failures after dispatch (for example a clock raising
    `OverflowError` at the end reading) follow the same absent-latency policy, and no exception is
    retained or chained;
  - process control raised by the clock at either reading or during these checks propagates as the
    identical object;
- process control (`KeyboardInterrupt`, `SystemExit`) from `clock`, `provider_id` and `generate`
  propagates as the identical object;
- the fake: configuration bounds, exhaustion without repeating the last step, missing keys, the
  history cap, sequential determinism and distinct steps under concurrent calls, and a `repr`
  without script text;
- packaging boundaries for the new package and modules.

*PostgreSQL:* none (M5a has no persistence).

*Installed wheel* (W-A7): one added line, for example "model-call contracts classified a scripted
fake response from the installed wheel".

##### H. Intended files and exclusions

- New: the five source files in A, the three test modules, ADR-0019 (written with the
  implementation).
- Changed: `pyproject.toml` (wheel, sdist and mypy lists only), `tests/test_packaging.py`,
  `.github/workflows/ci.yml` only if W-A7 is accepted, and the README, plan and threat-model
  status records.
- Excluded: persistence, migrations, prompts and templates, the planner, provenance checks,
  request assembly, orchestration, handlers, endpoints, settings, credentials, the Anthropic
  adapter, any network code, dependency or lockfile change, and any live or quality claim.

##### I. M5a decisions for review

Items marked *approved choice* were approved by the reviewer in Prompt 169 as the corrected
recommended contracts, and all of them were **accepted with the complete M5a specification in
Prompt 170** as its implementation contract. Nothing is implemented or tested.

1. **W-A1 Raw `generate` plus a shared boundary** (*approved choice, Prompt 169*). [REC] As in D. *Tradeoff:* a less
   generic protocol versus duplicating parsing and classification in every adapter.
2. **W-A2 Outcomes instead of exceptions** (*approved choice, Prompt 169*). [REC] Ordinary provider failures become
   `StructuredResult` outcomes, so M5e can record every call uniformly; only invalid arguments and a
   failed start-time clock raise. *Tradeoff:* callers must check `outcome` versus exception-driven
   control flow that is harder to record.
3. **W-A3 Value styles** (*approved choice, Prompt 169*).
   [REC] Exact-type dataclasses for call values and strict, non-stripping, tuple-only Pydantic
   output models parsed through B1. *Tradeoff:* two styles versus hand-writing a JSON validator.
4. **W-A4 Model echo** (*approved choice, Prompt 169, for exact equality; live alias behaviour awaits M5h*). [REC] Require `model_used == model_id`; any difference is
   `model_mismatch` (fail closed; W13 for its stage treatment). Alias behaviour for live model IDs
   waits for M5h. *Tradeoff:* possible false mismatches with a live API versus silently accepting a
   different model.
5. **W-A5 Bounds** (*approved choice, Prompt 169*). [REC] The limits in B, B1 and D2 as initial engineering defaults.
   *Tradeoff:* rejecting large outputs or scripts versus unbounded parsing and memory.
6. **W-A6 Timeout and retries** (*approved choice, Prompt 169*). [REC] One call per
   `call_validated`, `timeout_ms` (default 60,000, preserving §8's 60 s) passed to the adapter, no
   hard deadline in the boundary; adapter-internal and SDK retries are 0, superseding §8's "2 SDK
   retries" for model calls, so every attempt is reserved and counted (W4). *Tradeoff:* more
   orchestration logic versus hidden repeated calls and cost.
7. **W-A7 Installed-wheel line** (*approved choice, Prompt 169*). [REC] One line added to the existing wheel step.
   *Tradeoff:* a small workflow edit versus no installed-artifact evidence for the new package.
8. **W-A8 New package now** (*approved choice, Prompt 169*). [REC] Create `evidenceguard_agents` in M5a.
   *Tradeoff:* one more packaged import package versus later relocation.
9. **W-A9 Two-pass parsing** (*approved choice, Prompt 169*). [REC] The scan-then-JSON-mode path in B1. *Alternative:* a
   hand-written converter from the decoded value to strict Python-mode inputs. *Tradeoff:* parsing
   the text twice (bounded at 64 KiB) versus maintaining explicit conversions for every field.
10. **W-A10 Clock failures** (*approved choice, Prompt 169, including the arithmetic correction*).
    [REC] A fresh fixed error for an unusable start reading, and absent latency with the outcome
    preserved for any unusable end reading or calculation failure (D1). *Alternative:* always a result with absent latency. *Tradeoff:* refusing to call
    with a broken clock versus never raising for a local fault.
11. **W-A11 Fake bounds** (*approved choice, Prompt 169*). [REC] The D2 limits and the 4,096-entry history cap.
    *Tradeoff:* tests needing more calls must build a new fake versus unbounded memory.

##### M5a implementation status (accepted for a local commit, Prompt 173; CI pending)

[FACT] Claude Code implemented the accepted specification in Prompt 171 on
`feat/model-call-contracts` (from `d34aaaac`), corrected two review findings in Prompt 172
(`model_validate_strings` now uses strict Python-mode validation, and ordinary failures while
reading supplied mappings at the public output and fake-configuration entry points become fresh
fixed errors), and the corrected implementation was **accepted at external review in Prompt 173
for a local commit only**; see [ADR-0019](decisions/0019-model-call-contracts.md) for the
contracts, the implementation choices, the review attribution and the local verification actually
run. **At acceptance, publication and merge were not authorized; Linux verification and
current-version CI were pending, and none of the 308 integration tests had run against this
version** (M5a adds no PostgreSQL tests; historical, see the
[feature evidence](#m5a-feature-branch-ci-evidence-prompt-174) below for Prompt 174). Nothing registers, configures or networks the new code: there
is no production wiring, live provider, provenance check, prompt, persisted snapshot or review
orchestration, and M5b–M5h and overall M5 acceptance remain pending.

- *Files:* `evidenceguard_domain.model_calls` and `.agent_outputs`; the new `evidenceguard_agents`
  package (`providers`, `scripted`, `py.typed`); `tests/test_model_calls.py`,
  `tests/test_agent_outputs.py`, `tests/test_scripted_provider.py`; extended
  `tests/test_packaging.py`; `pyproject.toml` (wheel, sdist and mypy lists, and the Ruff
  first-party list); one installed-wheel line in `.github/workflows/ci.yml`.
- *Implementation choices recorded in ADR-0019:* the output models mark their error-translating
  `__init__` with Pydantic's own base-init flag so JSON-mode validation stays JSON-mode (pinned by a
  test); the "nested values must be model instances" rule is enforced in the Python-mode entry
  points because a schema-level `before` validator would break JSON-mode tuple parsing; the
  scripted fake rejects a `WrongModel` step naming its own model; `call_validated` passes the
  revalidated request to the provider; `pyproject.toml` also gains the package in Ruff's
  `known-first-party` list.
- *Local verification (Windows; not CI):* Prompt 172: the regression comparison (13 of 17
  submitted-code failures reproduce the findings), Ruff, format and strict mypy clean, the full
  suite `2936 passed, 310 skipped`, the offline build, the isolated installed-wheel step and a
  direct installed-wheel probe of the corrected entry points. Prompt 171 (historical): Ruff,
  format and strict mypy clean; the full
  suite `2910 passed, 310 skipped` (308 PostgreSQL tests without a database, one POSIX-only signal
  test and one symbolic-link test this Windows user cannot run); offline build; installed-wheel
  checks in an isolated offline environment. Details and limits are in ADR-0019.

##### M5a feature-branch CI evidence (Prompt 174)

[FACT] Accepted in Prompt 173 for a local commit; in Prompt 174 (resumed after an interrupted push)
`feat/model-call-contracts` was published at `9ba6a48888ff39a06b336a22429d5b3dcfa0bad6` (history-only
commit on top of the accepted implementation `79e32532`; the 12 implementation, test, packaging and
workflow blobs are identical to the accepted tree `5d4febb6`). **Not merged when observed
(Prompts 174–176): `main` was `46c02257`.** Publication to `main` was authorized in Prompt 176,
gated on exact-commit CI for the documentation commit; it had not run when this record was
written (historical: it ran in Prompt 176, see the
[main evidence](#m5a-main-publication-evidence-prompts-176177) below). Both push-triggered runs for that exact SHA (event `push`, attempt 1) and all five
required jobs succeeded, with every required step successful and none skipped:
[CI run 39303677105](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39303677105)
(Ubuntu verify, Windows verify, PostgreSQL integration, container) and
[secret-scan run 39303677129](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39303677129)
(full-history Gitleaks).

From the job logs **independently retrieved by the external reviewer** after Prompt 174 (recorded in
Prompt 175): Ubuntu `2938 passed, 308 skipped`, Windows `2937 passed, 309 skipped`, PostgreSQL
`308 passed, 2938 deselected` with the 104 M4 PostgreSQL cases passing (including both Voyage
cases), both installed-wheel logs printing the six expected lines including "model-call contracts
classified a scripted fake response from the installed wheel", the container job with all six
required steps and its smoke's reported checks, and Gitleaks (75 commits, no leaks). In Prompt 174
Claude Code observed only the API conclusions (its log downloads returned HTTP 403). Job links,
durations, the wheel lines, the container summary and the attribution are in
[ADR-0019](decisions/0019-model-call-contracts.md#feature-branch-ci-evidence-prompt-174). This is
contract evidence with the scripted fake, not live-model quality; the wheel's Recall@5 line is
arithmetic, not a database-derived corpus Recall; the container smoke is unchanged and does not
exercise M5a.

##### M5a main publication evidence (Prompts 176–177)

[FACT] In Prompt 176 Claude Code committed the reviewed documentation as `f04e0957`
(`f04e09576e0ed358669f793c134d9dbc30141104`; documentation and history only), pushed it to
`feat/model-call-contracts`, and, after all five required jobs passed for that exact commit,
fast-forwarded `main` from `46c02257` to `f04e0957` and pushed it. **M5a and the accepted M5b
specification are on `main` at `f04e0957`.** All four runs (feature
[CI 39309049137](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39309049137)
and [secret scan 39309049185](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39309049185);
main [CI 39309653878](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39309653878)
and [secret scan 39309653917](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39309653917))
used event `push`, attempt 1 and the exact SHA, and every required job and step succeeded. From
the job logs **independently retrieved by the external reviewer** (recorded in Prompt 177; Claude
Code observed API conclusions only): feature Ubuntu `2938 passed, 308 skipped`, Windows `2937
passed, 309 skipped`, PostgreSQL `308 passed, 2938 deselected`; main Ubuntu `2938 passed, 308
skipped`, Windows `2937 passed, 309 skipped`, PostgreSQL `308 passed, 2938 deselected`; the 104 M4
PostgreSQL cases passed on both pushes; all four installed-wheel logs printed the six expected
lines; both container smokes reported their checks as successful; Gitleaks scanned 76 commits with
no leaks on both pushes. Job links, durations, the container summary and the attribution are in
[ADR-0019](decisions/0019-model-call-contracts.md#main-publication-evidence-prompts-176177). This is
scripted-fake contract evidence, not live-model quality; the Recall wheel line is arithmetic; the
container smoke does not exercise M5a or M5b.

#### M5b provenance and status-derivation specification (ACCEPTED at review, Prompt 176; implementation pending)

**Status.** **Proposed by Claude Code in Prompt 174, corrected in Prompt 175 after external review
and accepted at external review in Prompt 176**, together with the binding input-identity
clarification in [M5b-E1](#m5b-e1-input-identity-binding-accepted-clarification-prompt-176). P1–P16
([M5b-J](#m5b-j-reviewer-decisions)) and the value, matching, rejection and reload rules specified
below (M5b-B1, M5b-C, M5b-C1, M5b-D, M5b-E, M5b-E1, M5b-F) form the **implementation contract**;
**no M5b specification decision remains open.** **The M5b implementation and every M5b check are
pending:** no M5b module, test, ADR-0020 or workflow change exists, and no M5b control operates.
*(Historical at acceptance: M5b was implemented in Prompt 177, corrected in Prompt 178 and is staged for review; see the
[implementation status](#m5b-implementation-status-accepted-at-review-prompt-179-ci-pending).)*
*Review scope (Prompt 176):* the reviewer independently verified the byte sizes and checksums of
the Prompt 174 and Prompt 175 exports and inspected their documentation changes; the reviewer's
Unicode probes and independently retrieved CI evidence keep their previously recorded scope, and no
M5b implementation or project test was run for this review. Labels: **[DECISION]** already accepted
before Prompt 174 (§4, the M5 sequence and its W11/W12 directions); **[FACT]** current source at the
published M5a SHA `9ba6a488`; **[REC]** Claude Code's recommendation, **accepted in Prompt 176 as
part of the implementation contract**. M5b is pure and database-independent: no
persistence, migration, prompt, request assembly, orchestration, endpoint, provider call, setting or
production wiring. Provenance (a quote exists in an authorized retrieved chunk) is distinct from
semantic entailment (model judgment, measured in M7) and from document authenticity (always
`not_established` in v1).

*Prompt 175 corrections (summary):* the matching rule is renamed and scoped as **segment-wise NFD
matching**, with its departures from Unicode canonical equivalence disclosed
([M5b-C1](#m5b-c1-limitations-of-segment-wise-nfd-matching)); exact value invariants
([M5b-B1](#m5b-b1-value-types-bounds-and-invariants)) and the complete rejection contract
([M5b-F](#m5b-f-outcomes-errors-privacy-and-process-control)) are specified; reload validation
recomputes the match ([M5b-D](#m5b-d-verifier-conversion-and-status-derivation)); every claim of a
`supported` or `contradicted` output must be cited (P7); and the documentary-gap finding is a
mandatory domain rule (P11).

##### M5b-A. Accepted requirements and current-source facts

[DECISION]

- §4: provenance checks prove only that each quote exists in an authorized chunk retrieved for that
  review and question; `evidence_status` is derived deterministically from the verdict and the
  cited documents' `source_type`; authenticity is always `not_established`; a `vendor_claim` on a
  question with `requires_documentary_support` raises a finding; the Risk Analyst may cite only
  citations the Verifier already validated.
- W11: `Verification`, `Citation` and `Finding` stay unchanged; surrounding values are added; the
  derived status must satisfy the existing validator.
- W12 direction: a normalized-substring match of body and repeated-header text **independently**,
  never joining spans, storing and displaying the exact original substring; evidence text is never
  modified.
- Sequence: M5b lives in `evidenceguard_domain.provenance`; a forged or unretrieved chunk gives
  `citation_rejected`; M5c owns safe prompt encoding and request assembly, M5d persisted snapshot
  trust, M5f the hash-covered report representation, M5g orchestration and job precedence, M5h the
  model adapter; production wiring is a separate reviewed decision (W8).

*Scoped clarification of §4 (P11; proposed in Prompt 175, **accepted at external review in Prompt
176 and effective for M5**).* §4 says "the Risk Analyst must raise a finding asking for documentary
evidence". For M5 this obligation is met by a **deterministic domain-rule finding** (M5b-E),
independent of model compliance, instead of by the Risk Analyst itself. The §4 text is left
unchanged as the historical wording.

[FACT]

- `Citation(tenant_id, document_revision_id, chunk_id, source_type, quote, authenticity)` is a
  `DomainModel`, whose configuration has `str_strip_whitespace=True`: `quote` (the `Quote` type,
  1–1000 code points) is **stripped at construction**, as are `Verification.rationale` and
  `Finding.title` and `.statement`. A quotation with leading or trailing whitespace therefore cannot
  be stored unchanged in a `Citation`.
- `_check_citations` enforces one tenant, no duplicate `(chunk_id, quote)`, `vendor_claim` → every
  citation a `vendor_statement`, `documentary_support` → at least one `contract` or
  `third_party_report`, `conflicting` → at least two distinct quote texts, `missing` → any number.
  `ALLOWED_STATUSES` maps `supported` → {`vendor_claim`, `documentary_support`}, `contradicted` →
  {`conflicting`}, `insufficient_evidence` → {`missing`}. `Verification` has no claims or provenance
  field; `Finding` has no follow-up field; `ReportContent` holds at most 200 findings and 100
  questions.
- M5a: `VerifierOutput(verdict, claims ≤ 10, rationale)`, `ClaimOutput(text 1–1000, citations ≤ 8)`,
  `QuoteRef(chunk_id canonical string, quote 1–1000)`, `AnalystOutput(findings ≤ 20)`,
  `FindingOutput(question_ids 1–20, title, severity, statement, citations ≤ 8, follow_up_questions
  ≤ 5 of 1–500)`; output strings reject NUL and lone surrogates and are never stripped; only exact
  duplicate `QuoteRef`s within one claim or finding are rejected. `StructuredResult` carries
  `purpose`, `question_id`, `request_sha256`, `outcome` and, for `completed`, `output`.
- M4d: `RetrievalResult` derives `tenant_id` and `snapshot_sha256` from its snapshot and holds at
  most `k` ≤ 20 items with distinct chunk IDs, each item's revision and document belonging to a
  snapshot binding. `RetrievedChunk(chunk_id, revision_id, document_id, …, evidence)`.
  `ChunkEvidence` has `text` (1–4,000 code points, digest-verified at construction, so UTF-8
  encodable), a `body` `SourceSpan`, an optional `header` span (tables only) ending before the body,
  `text` equal to the header slice followed by the body slice, `header_text`/`body_text` split at the
  header length, `source_type` and `authenticity`. **`ChunkEvidence` carries no tenant or revision
  ID**; those come from the result and item.
- No module uses `unicodedata`. Chunk IDs already use `uuid5` with a fixed namespace
  (`chunks.CHUNK_ID_NAMESPACE`).

##### M5b-B. Placement and public values

[REC] One new module, `packages/domain/evidenceguard_domain/provenance.py`, importing only the
standard library (`unicodedata`, `uuid`, `dataclasses`, `enum`, `contextlib`) and the domain modules
`evidence`, `retrieval`, `model_calls` and `agent_outputs`. It imports no persistence, retrieval
package, agents, apps, SQLAlchemy or network module; `tests/test_packaging.py` gains its allowlist.
Values are frozen dataclasses in the M4d/M5a style: exact types (`type(x) is …`, `bool` is not an
`int`), no coercion, tuples only, unknown keywords rejected, nested values **rebuilt through their
constructors** (`Citation`, `Verification`, `Finding` and `EvidenceQuestion` through `model_copy()`,
which revalidates; M4d and M5a values through their constructors), revalidation on
`dataclasses.replace`, count-only `repr`.

| Name | Kind | Contents and rule |
|---|---|---|
| `MATCH_RULES` | constant | `"eg-quote-match-v1"`, the only supported match-rules identifier, recorded with every verified question |
| `QuoteSpanKind` | `StrEnum` | `header`, `body` |
| `QuoteMatch` | value | the matched exact original quote and its offsets (M5b-B1) |
| `match_quote(evidence, quote)` | function | `QuoteMatch` or one of four `RejectionReason` members (M5b-C) |
| `QuestionEvidence` | value | the trusted inputs for one question (M5b-B1, M5b-D) |
| `AcceptedCitation` | value | a `Citation`, its document ID and its `QuoteMatch` |
| `ValidatedClaim` | value | model claim text and indexes into the verification's citations |
| `VerifiedQuestion` | value | one question's derived `Verification`, claims and aligned provenance |
| `FindingKind` | `StrEnum` | `analyst`, `documentary_support_required` |
| `AnalyzedQuestion` | value | one question's Analyst findings and their follow-up questions |
| `RejectionStage` | `StrEnum` | `verification`, `analysis` |
| `RejectionReason` | `StrEnum` | the fixed reasons in M5b-F |
| `ProvenanceRejection` | value | a text-free stage rejection (M5b-F) |
| `derive_status(verdict, citations)` | function | `EvidenceStatus` or `None` (M5b-D table) |
| `verify_question(evidence, result)` | function | `VerifiedQuestion` or `ProvenanceRejection` |
| `recheck_verified(verified, evidence)` | function | the rebuilt value, or `InvalidProvenanceInputError` (reload path) |
| `analyze_question(owner, question, result, *, shared=())` | function | `AnalyzedQuestion` or `ProvenanceRejection` (M5b-E) |
| `recheck_analyzed(analyzed, owner, question, *, shared=())` | function | the rebuilt value, or `InvalidProvenanceInputError` (reload path) |
| `documentary_gap_finding(verified, question)` | function | the deterministic rule finding or `None` (M5b-E) |
| `finding_id(tenant_id, review_id, question_id, kind, index)` | function | deterministic `UUID` (M5b-E) |
| `InvalidProvenanceInputError`, `InvalidProvenanceValueError` | errors | `invalid_provenance_input`, `invalid_provenance_value` (M5b-F) |

##### M5b-B1. Value types, bounds and invariants

[REC] "Constructor" invariants are checked on every direct construction and `dataclasses.replace`
(failure: `InvalidProvenanceValueError`). "Needs trusted values" invariants cannot be checked from
the value alone; they are checked only by `verify_question`/`analyze_question` when deriving and by
`recheck_verified`/`recheck_analyzed` on reload (failure: `InvalidProvenanceInputError`). **No
constructor proves authorization, retrieval for a particular question, or semantic entailment.**
Text fields "plain" means exactly `str`, no NUL, no lone surrogate (UTF-8 encodable), never
stripped or normalized. IDs are exactly `UUID`; digests exactly `str` of 64 lowercase hex; question
IDs exactly `str` matching the existing `QuestionId` pattern.

| Value | Fields (exact types and bounds) | Constructor invariants | Needs trusted values |
|---|---|---|---|
| `QuoteMatch` | `kind: QuoteSpanKind`; `text_start`, `text_end`, `source_char_start`, `source_char_end`: `int` (not `bool`); `quote`: plain `str`; `occurrences`: `int` | `0 <= text_start < text_end <= 4000`; `source_char_start >= 0`; `text_end - text_start == source_char_end - source_char_start == len(quote)`; `1 <= len(quote) <= 1000`; `quote == quote.strip()`; `1 <= occurrences <= 64` | offsets lie inside the named span of that chunk, select exactly `quote` in `text` and in the source, and equal a fresh `match_quote` result (M5b-D) |
| `QuestionEvidence` | `tenant_id`, `review_id`: `UUID`; `snapshot_sha256`: digest; `question: EvidenceQuestion`; `result: RetrievalResult` | `question` and `result` rebuilt; `result.tenant_id == tenant_id`; `result.snapshot_sha256 == snapshot_sha256`; items ≤ 20 with distinct chunk IDs (from `RetrievalResult`) | that `result` came from this review's trusted snapshot and was retrieved for this question (M5d/M5g responsibility) |
| `AcceptedCitation` | `citation: Citation`; `document_id: UUID`; `match: QuoteMatch` | both rebuilt; `match.quote == citation.quote`; `citation.authenticity` is `not_established` | chunk among the retrieved items; revision, document, source type, authenticity and tenant equal the item's; match recomputes equal |
| `ValidatedClaim` | `text`: plain `str`, 1–1000 code points; `citation_indexes`: tuple of `int`, length 0–8 | each index `0 <= i < 80`; indexes distinct within the claim | that the order within the claim is the model's first-appearance order (needs the original output; not rechecked on reload) |
| `VerifiedQuestion` | `tenant_id`, `review_id`: `UUID`; `question_id`; `snapshot_sha256`, `request_sha256`: digests; `match_rules: str`; `verification: Verification`; `claims`: tuple of `ValidatedClaim`, 0–10; `provenance`: tuple of `AcceptedCitation`, 0–80 | `match_rules == MATCH_RULES`; `verification` and every nested value rebuilt; `verification.tenant_id == tenant_id` and `.question_id == question_id`; `len(provenance) == len(verification.citations)` and `provenance[i].citation == verification.citations[i]`; every claim index `< len(provenance)`; reading claims in order, the first appearances of indexes are exactly `0, 1, …, n−1` (canonical order, so every citation is referenced); `verification.evidence_status == derive_status(verdict, citations)` (never `None`); for `supported` and `contradicted`, every claim has at least one index (P7) | all `AcceptedCitation` checks; question, tenant, review and snapshot equal the trusted `QuestionEvidence` |
| `AnalyzedQuestion` | `tenant_id`, `review_id`: `UUID`; `question_id`; `request_sha256`: digest; `findings`: tuple of `Finding`, 0–20; `follow_up_questions`: tuple of tuples of plain `str` (1–500 code points), inner length 0–5 | findings rebuilt; `len(follow_up_questions) == len(findings)`; every finding has `tenant_id == tenant_id`, contains `question_id` in `question_ids`, at most 8 citations, and `finding_id == finding_id(tenant_id, review_id, question_id, analyst, k)` for its position `k` | citations are validated owner (and shared) citations; listed questions are the owner and supplied shared questions; status equals the derivation in M5b-E |
| `ProvenanceRejection` | see M5b-F | see M5b-F | — |

**Shared questions** (`shared` in `analyze_question`/`recheck_analyzed`): a tuple of at most 19
`VerifiedQuestion`s (a finding lists at most 20 questions, one being the owner), each rebuilt, with
distinct question IDs, none equal to the owner's, and the same `tenant_id`, `review_id` and
`snapshot_sha256` as the owner; otherwise `InvalidProvenanceInputError`.

**`finding_id` arguments:** `tenant_id`, `review_id` exactly `UUID`; `question_id` matching
`QuestionId`; `kind` exactly a `FindingKind` member; `index` an `int` (not `bool`) with `0 <= index
<= 19` for `analyst` and **exactly 0** for `documentary_support_required`; otherwise
`InvalidProvenanceInputError`.

##### M5b-C. Exact quote matching (settles W12)

[REC] `match_quote(evidence, quote)` revalidates `evidence` as a `ChunkEvidence` and requires
`quote` to be a plain `str` of 1–1000 code points (as validated by M5a); otherwise
`InvalidProvenanceInputError`. It never raises for model content: it returns a `QuoteMatch` or one
of `quote_blank`, `quote_not_found`, `quote_too_long`, `quote_not_exact`, checked in that order.
The rule is **segment-wise NFD matching**, a deliberately limited, bounded matching rule; it is
**not** full Unicode canonical-equivalence matching (see M5b-C1).

1. **Spans.** `header_text` (when present) and `body_text` are matched **separately**. Each is one
   contiguous slice of the revision text. Matching never uses `text` as a whole, never joins header
   and body, never joins two chunks and never joins non-adjacent passages; a quote that exists only
   across the header/body boundary is not found, even though `text` contains it contiguously.
2. **Segments.** A code point is a *starter* when its canonical combining class is 0
   (`unicodedata.combining(c) == 0`), otherwise a *non-starter*. A new segment begins at every
   starter; a segment is one starter followed by all non-starters up to the next starter. If the
   text **begins** with non-starters, the whole maximal initial run of non-starters forms **one**
   segment (not one segment per non-starter). The same rule applies to the span and to the quote.
3. **Units and keys.** A segment that is exactly one code point `c` with `c.isspace()` is a
   whitespace segment; each **maximal run** of whitespace segments is one unit with key `" "`
   (U+0020). Every other segment is one unit with key `unicodedata.normalize("NFD", segment)`. Each
   unit records its `[start, end)` code-point offsets in the span. Matching boundaries are these
   **specified units**, not grapheme clusters or user-perceived characters.
4. **Quote form.** The quote's units and keys are formed the same way; leading and trailing
   whitespace units are dropped; nothing left → `quote_blank`. `Q` is the concatenation of the
   remaining keys.
5. **Occurrence.** `N` is the concatenation of the span's unit keys with a table of unit boundaries.
   An occurrence is an index `i` with `N[i:i+len(Q)] == Q` where `i` is the start of a unit and
   `i + len(Q)` the end of a unit. The search repeats `str.find` from `i + 1` (overlapping
   occurrences count). A match therefore never starts or ends inside a unit (in particular, never
   inside a whitespace run). No occurrence in either span → `quote_not_found`.
6. **Offset mapping.** An occurrence covers units `u_a … u_b`; the original slice is
   `span[u_a.start:u_b.end]`. Chunk-text offsets add 0 (header) or `header.length` (body); source
   offsets add that span's `char_start`. This is exact because M4d guarantees `text` is the header
   slice followed by the body slice and each slice is a contiguous source range of the same length.
7. **Selection.** All occurrences in both spans are ordered by chunk-text start (header before body);
   the **first** is selected; `occurrences` counts them and scanning stops at 64. Only the selected
   occurrence is checked in step 8; there is **no fallback** to a later occurrence. With repeated
   text whose originals differ (for example different line breaks), the first occurrence's original
   is stored (P4).
8. **Exact stored quotation.** `original = span[start:end]`. `len(original) > 1000` (an original can
   be longer than the model's quote, for example a decomposed spelling) → `quote_too_long`, never
   truncated; `original != original.strip()` (Python whitespace; only possible for a degenerate edge
   unit such as a space carrying a combining mark) → `quote_not_exact`. `verify_question` then builds
   the `Citation` with `quote=original` and requires `citation.quote == original` after construction
   (else `quote_not_exact`). Because the selected original has no Python-whitespace edges, the M1
   stripping leaves it unchanged; the post-construction equality pins this whatever whitespace
   definition Pydantic applies (design intent to be confirmed by the tests). **No M1 contract change
   is made;** a non-stripping citation quote was the alternative in P5.
9. **Not folded.** No case folding, no compatibility (NFKC) folding (ligatures, full-width forms,
   superscripts), no punctuation, quotation-mark, dash or ellipsis folding, no removal of zero-width,
   soft-hyphen or other format characters, and no matching across elided text: a quote containing
   `…` or `...` matches only those literal characters.
10. **Original preserved.** The model's string is never stored or displayed; only `original` is.
    Every accepted quote is an **exact, contiguous substring of one span of the original evidence,
    with exact original offsets**, whatever the limitations in M5b-C1. Evidence text is never
    modified; normalized forms are transient and never returned, stored or logged.
11. **Unicode version.** Results depend on the interpreter's `unicodedata` tables (expected Unicode
    15.0.0 for the CI's Python 3.12; a test pins the observed version so an interpreter upgrade is a
    deliberate change). Stored citations are original substrings, so a later Unicode version cannot
    change a stored quote, only future matches.
12. **Bounds.** Spans hold at most 4,000 code points and NFD expands each code point by a small
    constant (the maximum pinned by a test over the code space); quotes hold at most 1,000 code
    points; a verification checks at most 80 quote references (10 claims × 8), each against one
    chunk; span forms are computed at most once per span per call (at most 40); the occurrence loop
    makes at most one `find` per position of `N` and stops after 64 occurrences. These are
    engineering bounds, not measured limits.

Examples (all planned tests):

| Span text (original) | Model quote | Result |
|---|---|---|
| `Data is encrypted⏎  at rest.` | `Data is encrypted at rest.` | match; stored quote is the original with its line break and spaces |
| `café` with `e` + U+0301 | `café` precomposed | match; stored quote is the decomposed original |
| `café` | `cafe` | `quote_not_found` (the mark belongs to the unit) |
| `ﬁle` (ligature) | `file` | `quote_not_found` (no NFKC) |
| `MFA enabled` | `mfa enabled` | `quote_not_found` (no case folding) |
| precomposed `각` (U+AC01) | conjoining U+1100 U+1161 U+11A8 | match (complete syllable); stored quote is the precomposed original |
| conjoining U+1100 U+1161 U+11A8 | precomposed `각` (U+AC01) | match (complete syllable); stored quote is the conjoining original |
| header `\| Control \| Status \|`, body `\| MFA \| On \|` | `Status \| \| MFA` | `quote_not_found` (crosses the header/body boundary) |
| body with `rotated yearly` twice, once across a line break | `rotated yearly` | first occurrence's original, `occurrences` 2 |
| `   ` | `   ` | `quote_blank` |

##### M5b-C1. Limitations of segment-wise NFD matching

[REC] Segment-wise NFD handles the common cases (precomposed versus combining Latin accents,
canonical reordering of marks **within one segment**, complete Hangul syllables in either spelling)
but is **not** Unicode canonical equivalence: **canonically equivalent spellings can produce
different matching results**. Two disclosed cases (from the reviewer's isolated Prompt 175 probe,
see below):

- **Reordering across segments (Tibetan).** U+0F73 has combining class 0 and decomposes to U+0F71
  U+0F72 (non-starters). The original `ཀཱིུ` and its full NFD
  `ཀཱིུ` are canonically equivalent, but because U+0F73 starts a new segment,
  the segment-wise key of the original is `ཀཱིུ`, while the key of the full-NFD
  spelling is `ཀཱིུ`. A quote in one spelling does not match evidence in the
  other.
- **Hangul partial-match asymmetry.** Conjoining Jamo each have combining class 0, so each is its own
  unit, while a precomposed syllable is one unit. For the span `각` (precomposed), the quote
  `가` has key `가`, which ends inside the span's single unit (`각`):
  `quote_not_found`. For the canonically equivalent span `각` (three units), the same
  quote matches the first two units and the stored quote is `가`. Complete-syllable quotes
  match both spellings (examples above).

These limitations can cause **false rejections** (and, for partial Hangul syllables, an acceptance
that depends on the evidence spelling); they never weaken the guarantee in rule 10: an accepted
quote is always an exact contiguous original substring with exact offsets. Full canonical
equivalence would need a different, reviewed normalization design; none is proposed for v1 (P1).

*Probe attribution.* The reviewer ran a small isolated standard-library probe with Unicode 15.0.0,
implementing the proposed segmentation and per-segment NFD keys, which produced the keys and
results above. It was not a project test or an implementation test; no M5b code exists. Claude Code
ran no probe in Prompt 175.

##### M5b-D. Verifier conversion and status derivation

[REC] **Trusted input binding.** `QuestionEvidence` (M5b-B1) carries the tenant, review, snapshot
digest, question and retrieval result from M5d/M5g trusted paths (the review record, the planner
and M5g's own `search_snapshot` call for that question), never from the model. M5b cannot prove
that `result` was retrieved for this question; M5g supplies it only from that call (an M5g
structure test).

**Call binding.** `verify_question(evidence, result)` requires `type(result) is StructuredResult`,
revalidated by rebuilding, with `outcome` `completed`, `purpose` `verifier` and
`result.question_id == evidence.question.question_id`; otherwise `InvalidProvenanceInputError`
(caller misuse: only completed Verifier results reach M5b). `request_sha256` is recorded for audit.

**Algorithm** (phases run in order; a later phase runs only if no earlier phase failed; M5b-F
defines the reported rejection):

1. Index the retrieved items by chunk UUID. The model's `chunk_id` is only a lookup key; it
   authorizes nothing.
2. **Phase 1 – references.** For every claim `i` and quote reference `j`, in order: chunk not among
   the items → `chunk_not_retrieved`; otherwise `match_quote` (`quote_blank`, `quote_not_found`,
   `quote_too_long`, `quote_not_exact`) and the `Citation` equality check (`quote_not_exact`). On
   success build `Citation(tenant_id=evidence.tenant_id, document_revision_id=item.revision_id,
   chunk_id=item.chunk_id, source_type=item.evidence.source_type, quote=original,
   authenticity=item.evidence.authenticity)`: **all metadata comes from trusted evidence**, and
   authenticity is `not_established`, the only value. Every reference is checked (at most 80).
3. **Deduplication.** Accepted citations are keyed by `(chunk_id, original quote)`. The question's
   citations are the distinct keys in first-appearance order across claims; each claim keeps
   distinct `citation_indexes` in first-appearance order, so two references that resolve to the
   same original collapse. Every question-level citation is referenced by at least one claim, so no
   claim–citation relationship is lost.
4. **Phase 2 – claim coverage (P7).** For verdict `supported` or `contradicted`, every claim must
   retain at least one accepted citation after deduplication; a claim with no quote reference →
   `claim_uncited`. (A claim whose references failed was already rejected in phase 1.) For
   `insufficient_evidence`, claims may be uncited. This is structural provenance only; it does not
   show that a quote supports its claim.
5. **Phase 3 – aggregate.** Status by `derive_status` (table below; `None` → `verdict_unsupported`)
   and the rationale (`output.rationale.strip() == ""` → `rationale_blank`); both are evaluated.
   Otherwise the `Verification` stores the stripped rationale (free model text, not evidence, so M1
   stripping is acceptable).
6. Build `Verification(tenant_id, question_id, verdict, evidence_status, citations, rationale)` (the
   existing validator re-runs; a failure here is an internal inconsistency,
   `InvalidProvenanceValueError`, tested as unreachable) and return `VerifiedQuestion` with
   `match_rules = MATCH_RULES`.

Any failure rejects the whole output; no partial `Verification` is produced (P6).

| Verdict | Accepted citations (question level) | `evidence_status` |
|---|---|---|
| `supported` | at least one; every one `vendor_statement` | `vendor_claim` |
| `supported` | at least one `contract` or `third_party_report` (any mix) | `documentary_support` |
| `supported` | none | rejected: `verdict_unsupported` |
| `contradicted` | at least two distinct quote texts (any source types; one chunk may supply both) | `conflicting` |
| `contradicted` | fewer than two distinct quote texts | rejected: `verdict_unsupported` |
| `insufficient_evidence` | any number, including none (kept) | `missing` |

These rows are exactly the existing `ALLOWED_STATUSES` and `_check_citations` rules, so the derived
`Verification` always validates. With P7, every claim of a `supported` or `contradicted` output is
also cited. `requires_documentary_support` does not change the Verification's status; it is handled
by the rule finding (M5b-E).

**Reload validation.** `recheck_verified(verified, evidence)` runs as one guarded operation and:

1. rebuilds `verified` (all constructor invariants in M5b-B1, including `match_rules ==
   MATCH_RULES`, aligned provenance, canonical claim indexes, P7 coverage and the status
   derivation) and `evidence`;
2. requires equal tenant, review, snapshot digest and question ID;
3. for every `provenance[i]`: the chunk is among the retrieved items; the citation's tenant,
   `document_revision_id`, `source_type` and `authenticity` and the stored `document_id` equal the
   trusted item's values; and **`match_quote(item.evidence, citation.quote)` recomputed from the
   trusted `ChunkEvidence` and the stored original quote returns a `QuoteMatch` equal in every field
   to the stored `match`**. This one rule checks the span kind, chunk-text and source offsets, the
   exact original quotation, unit boundaries, first-occurrence selection and the capped occurrence
   count. (The stored original's quote form equals the model quote's form, because the original is
   a unit-aligned occurrence without edge whitespace, so recomputation selects the same occurrence.)

Any difference is `InvalidProvenanceInputError`. M5e/M5g reload paths call it with M5d's trusted
reloaded evidence. It **detects values inconsistent with the trusted evidence supplied**; it does
not prove which retrieval request originally ran, and it does not protect against a malicious
trusted process or a direct database writer.

##### M5b-E. Risk Analyst findings and the documentary-support rule

[REC] `analyze_question(owner, question, result, *, shared=())`: `owner` is the question's
`VerifiedQuestion` (the Verifier stage succeeded), `question` its `EvidenceQuestion` (same ID), and
`result` a revalidated `StructuredResult` with `outcome` `completed`, `purpose` `risk_analyst` and
`question_id` equal to the owner's; `shared` follows M5b-B1. Violations are
`InvalidProvenanceInputError`. These identity checks run **before any finding is examined**,
including for an Analyst output with no findings (M5b-E1). **Every finding is checked** (at most 20). For each finding `k`, the
checks below run in order and stop at the finding's **first** failing check (later checks depend on
earlier ones):

1. **Question scope.** `question_ids` must contain the owner's ID; every other ID must be the
   question of a supplied `shared` value → else `foreign_question`.
2. **Citations.** Each `QuoteRef`, in order, must resolve to an owner citation with the same chunk
   ID whose stored quote has the same M5b-C quote form `Q` (equivalence of the whole quote, never a
   substring or a new passage) → else `citation_not_validated`. For a multi-question finding the
   resolved citation must also be in every listed question's `Verification` (same chunk and quote)
   → else `citation_not_shared`. The finding carries the stored, trusted `Citation`s, deduplicated,
   in first-appearance order.
3. **Status** (the model never supplies it): the verdicts of all listed questions must be equal →
   else `mixed_verdicts`. Then: no citations → `missing`; `insufficient_evidence` → `missing`;
   `supported` → `vendor_claim` or `documentary_support` by source type as in M5b-D;
   `contradicted` → `conflicting` with at least two distinct quote texts, else
   `finding_status_unsupported`. A finding citing one side of a conflict is therefore never shown as
   support (P10).
4. **Text.** `title` and `statement` must be non-blank after stripping (they become stripped
   `Finding` fields) → else `finding_text_blank`. `severity` is the model's judgment.
   `follow_up_questions` are kept verbatim in the parallel tuple; `Finding` has no such field, and
   their report representation is M5f's decision (P13).
5. **Identity.** `finding_id(tenant_id, review_id, owner question_id, analyst, k)`; the finding is
   built through `Finding`'s validator.

Any failing finding rejects the whole analysis (M5b-F). `owner` is never modified, re-derived or
relabelled: a failed analysis leaves the valid `Verification` intact, and M5g records the analysis
as unresolved (W14). The Analyst cannot supply status, tenant, revision, source type,
authenticity, finding IDs or new evidence. `recheck_analyzed(analyzed, owner, question, *,
shared=())` rebuilds and validates `analyzed`, `owner`, `question` and `shared`, checks the outer
identities in M5b-E1 before iterating, and then repeats steps 1–5 against them for every stored
finding (citations resolved by exact chunk and quote, statuses re-derived, IDs recomputed); any
difference is `InvalidProvenanceInputError`.

**Multi-question findings.** With the per-question analysis stage recommended for M5g (only the
owner's Verification is in its request), `shared` is empty, so a finding listing another question is
`foreign_question`. The general rule lets a later reviewed stage design supply shared questions
without changing M5b (P9).

**Documentary-support rule (P11).** `documentary_gap_finding(verified, question)` first rebuilds and
validates `verified` and `question` and requires `verified.question_id == question.question_id`
(M5b-E1), before evaluating `requires_documentary_support` or returning `None`. It then returns, when
`question.requires_documentary_support` is set and the Verification's status is `vendor_claim`, one
deterministic `Finding`: `finding_id(…, documentary_support_required, 0)`, `question_ids` the owner
only, fixed title "Documentary evidence required", fixed statement "Only vendor statements support
this answer; the question requires a contract or third-party report.", severity `medium`,
`evidence_status` `missing` and the Verification's citations (all `vendor_statement`, allowed for
`missing`). Otherwise it returns `None`. It is a **domain-rule obligation independent of model
compliance**: it depends only on the valid Verification, not on the Analyst's output, and it is not
a model judgment. **Binding obligation on M5f and M5g (accepted in Prompt 176):** once a valid `vendor_claim`
Verification exists for a question requiring documentary support, this rule finding **must** be
included in the later hash-covered report **even if analysis fails**; inclusion is not optional, and
the valid Verification is preserved. Under the existing `ReportContent` rules a `missing` finding
forces the question into `unresolved_question_ids`, and the vendor claim stays visible. This
replaces, for M5, §4's literal requirement that the Risk Analyst itself raise the finding (the
scoped clarification in M5b-A). M5b does not try to decide whether an Analyst finding semantically
asks for documents.

**Finding IDs (P12).** `finding_id = uuid5(FINDING_ID_NAMESPACE,
f"{tenant_id}:{review_id}:{question_id}:{kind}:{index}")` with canonical lowercase UUID text, the
`FindingKind` value and the decimal index (M5b-B1 bounds); `FINDING_ID_NAMESPACE = uuid5(NAMESPACE_URL,
"https://evidenceguard.invalid/namespaces/finding-id/v1")`, pinned like `CHUNK_ID_NAMESPACE`. An
identical replay yields identical IDs (M5e's identical-replay no-op), and `(review, question, kind,
index)` is unique within a report. An ID is not a secret or an authorization.

##### M5b-E1. Input identity binding (accepted clarification, Prompt 176)

[DECISION] Set by the external reviewer as a binding clarification when accepting M5b in Prompt
176. It clarifies the intended input binding only; it adds no module, persistence mechanism or
production capability.

- **`recheck_analyzed`** rebuilds and validates `analyzed`, `owner`, `question` and `shared`, then
  requires `analyzed.tenant_id == owner.tenant_id`, `analyzed.review_id == owner.review_id` and
  `analyzed.question_id == owner.question_id == question.question_id` **before iterating
  findings**. These checks apply even when `findings` is empty.
- **`documentary_gap_finding`** rebuilds and validates `verified` and `question` and requires
  `verified.question_id == question.question_id` **before** evaluating
  `requires_documentary_support` or returning `None`, so a mismatch is an error whether the rule's
  condition would be true or false.
- **`analyze_question`** keeps its owner, question and result identity checks (owner, question and
  `result.question_id` equal; `shared` per M5b-B1) **before iterating**, including for an Analyst
  output with no findings.
- **Trusted owner and shared values.** The owner and shared `VerifiedQuestion`s supplied to
  `analyze_question` or `recheck_analyzed` must come from the trusted path that has performed
  `recheck_verified` against the appropriate trusted evidence (or from `verify_question` itself).
  Analysis checks do **not** independently re-prove retrieval membership.
- **Separate request digests.** An Analyst `request_sha256` is never compared with the Verifier's
  `request_sha256`: they identify different calls. Each remains an audit field for its own stage.
- **Errors.** Identity violations are fresh `InvalidProvenanceInputError` values with no cause or
  context; process control propagates unchanged (M5b-F).

##### M5b-F. Outcomes, errors, privacy and process control

[REC] **Fixed reasons and precedence.** Caller-input errors always win: they raise before any model
content is examined.

| Stage and phase | Reasons (precedence within one item) | `item_index` | `citation_index` | `rejected_count` | §4 `provenance_check` |
|---|---|---|---|---|---|
| verification, phase 1 (references) | `chunk_not_retrieved`, `quote_blank`, `quote_not_found`, `quote_too_long`, `quote_not_exact` | claim index 0–9 | reference index 0–7 | rejected references, 1–80 | `citation_rejected` |
| verification, phase 2 (claim coverage) | `claim_uncited` | claim index 0–9 | `None` | uncited claims, 1–10 | `citation_rejected` |
| verification, phase 3 (aggregate) | `verdict_unsupported`, then `rationale_blank` | `None` | `None` | failed aggregate checks, 1–2 | `invalid_output` |
| analysis (per finding) | `foreign_question`, `citation_not_validated`, `citation_not_shared`, `mixed_verdicts`, `finding_status_unsupported`, `finding_text_blank` | finding index 0–19 | reference index 0–7 for the two citation reasons (the first failing reference), otherwise `None` | failing findings, 1–20 | `citation_rejected` for the two citation reasons, otherwise `invalid_output` |

- **Reported rejection.** Verification: the first failing phase is reported; within phases 1 and 2,
  the failure at the lowest (claim, reference) position, with its first reason in the precedence
  order; in phase 3, `verdict_unsupported` if it fails, otherwise `rationale_blank`. Analysis: the
  lowest failing finding index with that finding's first failing reason. `rejected_count` counts the
  failures of the **reported phase only** (later phases are not evaluated after a failure), so
  simultaneous failures are fully deterministic.
- **`ProvenanceRejection` fields:** `stage: RejectionStage`; `question_id` (`QuestionId` pattern);
  `reason: RejectionReason`; `item_index: int | None`; `citation_index: int | None`;
  `rejected_count: int`. Exact types (`int`, not `bool`); the constructor requires the reason to
  belong to the stage and phase, and `item_index`, `citation_index` and `rejected_count` to be
  present or `None` and in range exactly as in the table. It carries positions, a reason and a
  count only, never text.
- **Standalone `match_quote`** returns a `QuoteMatch` or one of its four reasons (`quote_blank`,
  `quote_not_found`, `quote_too_long`, `quote_not_exact`, in that order) and never a
  `ProvenanceRejection`; `verify_question` places that reason at the reference's position.
- **Errors.** Model-caused failures never raise. **Bad caller or trusted input raises**
  `InvalidProvenanceInputError` (`invalid_provenance_input`) from the functions;
  `InvalidProvenanceValueError` (`invalid_provenance_value`) covers invalid direct construction of an
  M5b value and unreachable internal inconsistencies. Each is raised fresh outside every `except`
  block, with the code as its message and no cause or context.
- **Whole-operation normalization.** Every public operation (each constructor and
  `dataclasses.replace`, and every function) runs its **whole** supported-input operation (input
  traversal, copying, nested revalidation, normalization, matching and Pydantic construction) inside
  one boundary that suppresses ordinary `Exception` only (`InvalidRetrievalRequestError`,
  `InvalidModelValueError`, Pydantic `ValidationError`, `ValueError`, `TypeError` and others) and
  raises the fixed error after leaving the handler. Exception chains are never inspected.
- **Process control** (`BaseException` that is not `Exception`) propagates as the same object.
  M5b knows nothing about jobs; M5g runs `ctx.check()` around it (W7).
- **Privacy.** No error, rejection or `repr` contains quotes, claim text, rationale, titles,
  statements, follow-up questions or evidence text; representations show IDs, counts, reasons,
  offsets and digests. Nothing in M5b logs. Explicit attribute access returns content by design.
- **Immutability.** Every collection is a tuple of frozen values; `Citation`, `Verification` and
  `Finding` are frozen `DomainModel`s.
- **Trust limits.** No protection is claimed against malicious trusted Python (`object.__setattr__`,
  `model_construct`, frame inspection) or direct database modification; constructors and the
  recheck functions detect inconsistent values, not a determined in-process attacker.

##### M5b-G. Compatibility and later boundaries

- [REC] No change to M1–M4 or M5a behaviour. The only incompatibility found, `Citation`'s whitespace
  stripping, is handled by the edge rule in M5b-C (8); the contract change was P5's rejected
  alternative.
- **Report bounds (explicit M5f review obligation, P16).** Up to 100 questions × (20 Analyst
  findings + 1 rule finding) exceeds `ReportContent`'s 200-finding limit. M5f must settle the global
  report bounds in its review; **no silent truncation and no unbounded report is authorized**.
- **Documentary rule (P11).** M5f and M5g must include the rule finding whenever its condition holds,
  even after a failed analysis (M5b-E).
- **M5c.** M5b matches original evidence text only and does no entity or escape decoding. M5c must
  give the model exactly the retrieved chunk IDs to cite and must either use an encoding whose
  quotations of document content are original text, or apply one reviewed, deterministic decoder to
  each `QuoteRef.quote` before M5b. An escaped quote that does not occur in the original (under
  M5b-C) is `quote_not_found`. M5b prescribes no prompt format.
- **M5d** supplies the trusted retrieval evidence and snapshot digest; **M5e** stores the M5b values
  and must reload them through their constructors and the recheck functions; **M5f** decides the
  hash-covered representation of claims, accepted quotes, follow-up questions, rule findings and
  unresolved reasons; **M5g** owns stage order, the repair of a rejection within the accepted
  budgets (P8), job precedence and error mapping; **M5h** owns the adapter.
- **Canaries.** M5b rejects quotes naming unretrieved or Tenant B chunks and accepts a genuine
  authorized quotation even if it contains canary text (the labelled limitation probe). No denylist,
  no injection-resistance claim.

##### M5b-H. Planned tests (not written or run)

*Database-independent* (`tests/test_quote_matching.py`, `tests/test_provenance.py`,
`tests/test_packaging.py`):

- **Normalization and whitespace:** spaces, tabs, LF, CRLF, U+00A0, U+2028 and U+3000 runs collapse;
  quote edges ignored; whitespace-only quote → `quote_blank`; common Latin precomposed versus
  combining accents; marks in different canonical orders within one segment; complete Hangul
  syllables in both spellings; supplementary characters; ligatures, full-width forms, case,
  typographic quotes, zero-width space and soft hyphen **not** folded; a quote ending inside a unit
  (for example before a base character's marks) is not found.
- **Pinned limitations (M5b-C1):** the Tibetan pair `ཀཱིུ` / `ཀཱིུ`
  does not match in either direction; the Hangul partial quote `가` is `quote_not_found` in span
  `각` and matches the first two units of `각`, storing `가`; a span
  and a quote beginning with a run of non-starters (for example U+0323 U+0307 before `x`, and the
  quote spelled U+0307 U+0323 `x`) treat the initial run as **one** segment and match.
- **Spans and offsets:** quotes inside the header, inside the body, and across the boundary
  (rejected though contiguous in `text`); non-table chunks; chunk-text and source offsets for both
  span kinds, with `span[start:end] == quote` and pinned examples.
- **Repetition and bounds:** repeated quotes with differing originals (first selected, no fallback),
  overlapping occurrences, the 64-occurrence cap, 4,000-code-point spans, 1,000-code-point quotes,
  an original of 1,001 code points (`quote_too_long`), the degenerate edge unit (`quote_not_exact`),
  `Citation` round-trip equality, the maximum NFD expansion and the pinned `unicodedata` version.
- **Value invariants (M5b-B1):** every constructor bound and cross-field rule, including `bool`
  offsets, `text_end <= text_start`, length mismatches, occurrence count 0 and 65, claim indexes out
  of range, duplicated or out of canonical order, misaligned provenance, an unsupported match-rules
  identifier, a non-derivable status, follow-up tuples not aligned with findings, finding IDs not
  matching their position, `finding_id` kinds and index bounds (rule index other than 0), shared
  bounds (20 values, duplicate IDs, the owner, another review), and every `ProvenanceRejection`
  field combination.
- **Binding:** tenant or snapshot-digest mismatch, wrong types, bypassed nested values caught by
  rebuilding, non-completed outcomes, the Analyst purpose and a question mismatch passed to
  `verify_question` (`InvalidProvenanceInputError`).
- **Citations and counts:** forged chunk ID, Tenant B chunk ID, a chunk retrieved only for another
  question, absent quote; several simultaneous failures (lowest position reported, `rejected_count`
  exact, phase 2 and 3 not evaluated); no partial Verification; metadata always from evidence.
- **Claim coverage (P7):** a `supported` output with one cited and one uncited claim →
  `claim_uncited` at the uncited claim's index; the same for `contradicted`; the same claims under
  `insufficient_evidence` → accepted with the uncited claim kept.
- **Status:** every row of the M5b-D table, including two identical quotes from different chunks for
  `contradicted` (rejected), `insufficient_evidence` with citations kept, both aggregate failures
  together (`verdict_unsupported` reported, count 2), and deduplication within and across claims
  with canonical claim indexes.
- **Reload (`recheck_verified`):** independently altering source offsets with chunk-text offsets
  unchanged; chunk-text offsets; span kind; occurrence count; the match-rules identifier; document,
  revision, source type or authenticity metadata; claim indexes; provenance alignment; and evidence
  with a removed chunk or changed text; each → `InvalidProvenanceInputError`, and the unaltered
  value passes.
- **Analysis:** scope and `shared` rules, multi-question ownership, `citation_not_validated` (an
  unvalidated chunk, a substring of a validated quote, the same quote under another chunk),
  `citation_not_shared`, `mixed_verdicts`, status per verdict, blank text, several failing findings
  (count and lowest index), follow-ups kept, pinned finding IDs, `recheck_analyzed` against an
  altered status, citation or ID, and an analysis rejection leaving the owner unchanged.
- **Input identity (M5b-E1):** an **empty** `AnalyzedQuestion` whose outer tenant, review or question
  ID differs from the owner's (and an owner/question ID mismatch) → `recheck_analyzed` raises
  `InvalidProvenanceInputError` before any finding is iterated; `analyze_question` with mismatched
  owner, question or result identity and an Analyst output with no findings raises the same;
  `documentary_gap_finding` with mismatched `verified` and `question` IDs raises both when the
  rule's condition would be true and when it would be false; a **valid empty analysis** (matching
  identities, no findings) is accepted and rechecks cleanly; an Analyst `request_sha256` differing
  from the Verifier's is accepted; each identity error has no cause or context, and process control
  raised during rebuilding propagates as the same object.
- **Documentary rule (P11):** required plus `vendor_claim` gives the rule finding (fixed text,
  `medium`, `missing`, vendor citations, index-0 ID) regardless of the Analyst output;
  `documentary_support` or a non-required question gives none; a `ReportContent` built with it lists
  the question as unresolved.
- **Privacy and process control:** canary-bearing quotes, claims, rationale, titles and statements
  appear in no error, rejection, `repr` or captured log; errors have no cause or context; a
  `KeyboardInterrupt` raised inside normalization, traversal or nested revalidation (by
  monkeypatching) propagates as the same object, and a `RuntimeError` there becomes the fixed error;
  attribute assignment fails.
- **Packaging:** the new module's import allowlist.

*PostgreSQL:* none. *Installed wheel* (P14): one line, for example "provenance matched a quote and
derived a status from the installed wheel". The end-to-end canary fixtures belong to M5g.

##### M5b-I. Intended files and exclusions

- New: `packages/domain/evidenceguard_domain/provenance.py`, `tests/test_quote_matching.py`,
  `tests/test_provenance.py`; ADR-0020 written with the implementation (not now).
- Changed: `tests/test_packaging.py`; `.github/workflows/ci.yml` for the one wheel line (P14);
  README, plan and threat-model status records. No `pyproject.toml` change is expected (the module
  is inside an existing package).
- Excluded: persistence, migrations, prompts, templates, the planner, request assembly, decoding of
  encoded quotes, orchestration, handlers, endpoints, settings, credentials, provider calls, any
  dependency or lockfile change, any change to M1–M4 or M5a contracts, and any live, quality or
  injection-resistance claim.

##### M5b-J. Reviewer decisions

Proposed in Prompt 174. In Prompt 175 the external reviewer supported the directions below,
subject to review of the corrected specification (historical); in **Prompt 176 the reviewer accepted
the complete corrected specification, including P1–P16 as recorded below and the M5b-E1
clarification, as the implementation contract.** Nothing is implemented.

1. **P1 Matching rule** (*supported direction, revised in Prompt 175*). Segment-wise NFD matching as
   a deliberately limited, bounded rule, with its departures from canonical equivalence disclosed
   (M5b-C1), no case or compatibility folding. *Rejected alternatives:* NFKC or case folding (would
   equate texts with different meaning, such as `10²` and `102`); a new full canonical-equivalence
   implementation (not designed in this task). *Tradeoff:* simple, bounded and exact-offset matching
   versus false rejections for some canonically equivalent spellings.
2. **P2 Whitespace** (*supported*). Runs of Python whitespace collapse to one space; quote edges
   ignored. *Tradeoff:* tolerance of reflowed lines versus stricter literalness.
3. **P3 No other folding** (*supported*). No punctuation, quotation-mark, dash, ellipsis or
   format-character folding. *Tradeoff:* rejecting a model that "tidies" typography versus accepting
   quotes that are not in the document.
4. **P4 Repeated quotes** (*supported*). The first occurrence by chunk-text offset, the count
   recorded, no fallback. *Tradeoff:* determinism with a possibly different whitespace rendering
   versus more rejections.
5. **P5 Citation whitespace** (*supported*). `Citation` unchanged; only originals without edge
   whitespace accepted, with post-construction equality pinned. *Tradeoff:* rare `quote_not_exact`
   rejections versus reopening an accepted contract.
6. **P6 All-or-nothing conversion** (*supported*). Any failure rejects the whole stage output.
   *Tradeoff:* more unresolved questions versus silently hiding forged or unretrieved citations.
7. **P7 Per-claim citations** (*supported, the stronger alternative selected in Prompt 175*). Every
   claim of a `supported` or `contradicted` output must retain at least one accepted citation after
   deduplication (`claim_uncited` otherwise); `insufficient_evidence` claims may have none.
   *Tradeoff:* more rejections of explanatory claims versus claim-level structural provenance (still
   not proof of support).
8. **P8 Repair after rejection** (*supported*, for M5g, within the accepted budgets). A
   `ProvenanceRejection` is treated like `invalid_output`: eligible for the stage's single repair
   within the accepted three-reservation budget, built from the fixed reason and positions only.
   *Tradeoff:* one more call versus an unresolved question on the first forged citation.
9. **P9 Multi-question findings** (*supported*). The general rule in M5b-E with an empty `shared` in
   the recommended per-question stage. *Tradeoff:* a slightly larger contract versus redesigning
   later.
10. **P10 Finding status** (*supported*). Derived from the listed questions' common verdict and the
    finding's own citations. *Tradeoff:* a status that matches its own citations versus simpler but
    possibly unsupported labels.
11. **P11 Documentary rule** (*supported, Prompt 175*). A deterministic rule finding with fixed text,
    severity `medium`, status `missing` and the vendor citations, which must be included in the
    hash-covered report whenever its condition holds, even if analysis fails; it replaces, for M5,
    §4's literal requirement that the Risk Analyst itself raise the finding (scoped clarification in
    M5b-A). *Tradeoff:* a guaranteed rule outcome versus model behaviour that cannot be checked
    semantically.
12. **P12 Finding IDs** (*supported*). `uuid5` over tenant, review, question, kind and index.
    *Tradeoff:* replay-stable IDs versus IDs that reveal nothing about position.
13. **P13 Follow-up questions** (*supported*). Kept beside each `Finding`, verbatim; representation
    left to M5f. *Tradeoff:* no M1 change versus an extra parallel value.
14. **P14 Installed-wheel line** (*supported*). One added line. *Tradeoff:* a small workflow edit
    versus no installed-artifact evidence for the new module.
15. **P15 Unicode pin** (*supported*). A test pinning `unicodedata.unidata_version`. *Tradeoff:* an
    interpreter upgrade fails a test versus silent matching changes.
16. **P16 Report bounds** (*supported as an explicit M5f review obligation*). M5f must settle the
    global report bounds; no silent truncation or unbounded report is authorized.

**No M5b specification decision remains open** (Prompt 176): the value and rejection contracts in
M5b-B1 and M5b-F, the M5b-C1 limitations, the reload rules, the M5b-E1 identity binding and the
scoped §4 clarification are accepted. The disclosed Unicode limitations, the structural-only
provenance guarantee, the mandatory hash-covered documentary-gap finding and the later-slice
obligations (including M5f's report-bound obligation: no silent truncation or unbounded report)
stand as written. Routine choices (value style, error codes, bounds, offsets, deduplication and
precedence) are resolved above. **The M5b implementation and every M5b check remain pending.**
*(Historical at acceptance; see the implementation status below.)*

##### M5b implementation status (accepted at review, Prompt 179; CI pending)

[FACT] Claude Code implemented the accepted specification in Prompt 177 on
`feat/provenance-validation` (from `f04e0957`), **corrected it in Prompt 178** after the external
reviewer reproduced a defect (`recheck_analyzed` accepted stored finding citations whose revision,
source type and status had been changed while chunk and quote stayed the same; analysis and reload
now require full trusted `Citation` values, also across shared questions), and staged it for
external review. **The corrected implementation was accepted at external review in Prompt 179,
pending exact-commit CI**; publication was authorized by Prompt 179 subject to the feature and
main CI gates (historical: both gates passed and M5b is on `main` at `90295717`; see the
[main publication evidence](decisions/0020-provenance-validation.md#main-publication-evidence-prompt-179)). From the
job logs independently retrieved by the external reviewer afterwards (recorded in Prompt 180;
Claude Code observed only API conclusions in Prompt 179): Ubuntu `3170 passed, 308 skipped`,
Windows `3169 passed, 309 skipped` and PostgreSQL `308 passed, 3170 deselected` on both pushes;
all four installed-wheel logs printed seven lines, including "provenance matched a quote and
derived a status from the installed wheel"; both container smokes reported success (they do not
exercise M5b); Gitleaks scanned 77 commits with no leaks. The reviewer ran no project suite,
build, wheel, database, Docker or provider locally. No review path uses M5b yet, and
overall M5 acceptance is pending. See [ADR-0020](decisions/0020-provenance-validation.md) for the contract as
implemented, the correction and its regression comparison, the implementation choices (three of
them approved at review in Prompt 178: the added `chunks` import for the existing chunk bound, the
read-only `provenance_check` property, and a `rejected_count` of exactly 1 for `rationale_blank`),
the limits and the local verification actually run.

*Reviewer evidence (Prompt 179).* The external reviewer independently verified the byte sizes
and checksums of both attached exports and inspected them, reconstructed the corrected source by
applying the Prompt 178 correction to the extracted submitted source (Git blob
`23f941dcd0eb1542fe5a3a8aef6edd896e01585c`, matching the staged module), and reran the original 17
isolated checks plus three new ones (valid shared analysis and reload; inconsistent shared
metadata refused in analysis and in reload): all 20 passed, with Python 3.12.14, Pydantic 2.14.0,
Unicode 15.0.0 and existing dependencies from `f04e0957`. These were isolated reviewer checks, not
a project suite, build, installed-wheel, PostgreSQL, Docker or provider run. Claude Code's Prompt
178 Windows results (below) remain separately attributed and are not exact-commit CI.

- *Files:* `evidenceguard_domain.provenance`; `tests/test_quote_matching.py` and
  `tests/test_provenance.py`; extended `tests/test_packaging.py`; one added installed-wheel check in
  `.github/workflows/ci.yml`; ADR-0020. No dependency, lockfile, `pyproject.toml`, existing
  contract, persistence, migration, setting, registry, Docker, Compose or corpus change.
- *Local verification after the Prompt 178 correction (Windows; not CI):* the regression comparison
  (the corrected module passes all 8 new tests; the submitted module fails 6: 4 reproduce the
  reviewer's defect, 2 are new shared-consistency coverage); Ruff, format and strict mypy clean;
  the two M5b modules 230 passed; the focused nine-file command 742 passed; full suite `3168
  passed, 310 skipped`; collection 308 integration and 3,170 non-integration tests; the offline
  build with only the authorized packaging differences; the isolated installed-wheel step; and a
  direct installed-wheel probe of the corrected reload. Details are in ADR-0020.
- *Local verification in Prompt 177 (historical):* Ruff, format and strict mypy clean; the two new modules
  222 passed; the focused nine-file command 734 passed; full suite `3160 passed, 310 skipped` (308
  PostgreSQL tests without a database, one symbolic-link test and one POSIX-only signal test);
  collection 308 integration and 3,162 non-integration tests; a five-mutation test-strength probe
  detected every mutation; the offline build comparison against `f04e0957`; and the extracted
  installed-wheel step in an isolated offline environment, including the new M5b line. Details are
  in ADR-0020.
- *Not established:* (Linux, current-version CI and the PostgreSQL job for this version were
  pending at acceptance and have since passed for `90295717`; see above.) Any review path using these values, semantic entailment, authenticity or
  injection resistance. The disclosed Unicode limitations (M5b-C1) are implemented and pinned by
  tests. The binding obligations on later slices (M5c decoding, M5e reloading, M5f report bounds
  and mandatory documentary rule finding, M5g orchestration) and overall M5 acceptance remain
  pending.
- *Text-fidelity note (found in Prompt 177):* the Tibetan and Hangul examples in M5b-C1 above, and
  the corresponding Prompt 175 records in `prompts.md`, contain the literal characters rather than
  the backslash-escape spellings used in Prompt 175: an escape-decoding step in Claude Code's
  editing tools converted them. The code points are the intended ones (Tibetan U+0F40 U+0F74
  U+0F73 and U+0F40 U+0F71 U+0F72 U+0F74 for the original and its full NFD; Hangul U+AC01, U+AC00
  and U+1100 U+1161 U+11A8), so the rules and examples are unchanged in meaning, but the Prompt 175
  verbatim record does not reproduce those escape spellings byte for byte. Committed history is not
  rewritten; ADR-0020 and the new tests use `U+` notation and escapes.

#### M5c review template, planner, prompts and request assembly specification (ACCEPTED at review, Prompt 181; implementation pending)

**Status.** **The complete corrected M5c specification was accepted at external review in Prompt
181 and is the M5c implementation contract; implementation is pending.** It was proposed by Claude
Code in Prompt 179 and revised in Prompt 180 after external review (historical: in Prompt 180 the
reviewer supported directions C1, C2 and C4–C11 subject to those corrections and narrowed C3,
which was not yet acceptance). At acceptance no M5c module, packaged template, prompt file, test,
ADR-0021 or workflow change existed (historical: M5c was implemented in Prompt 182, corrected in
Prompt 183 and accepted for a local commit in Prompt 184; see [implementation status](#m5c-implementation-status-accepted-for-a-local-commit-prompt-184-ci-pending)),
and none of the controls below operates in the application. Labels: **[DECISION]** already accepted (§4, the M5 sequence and its settled W-choices,
the accepted M5a and M5b contracts); **[FACT]** current source at `90295717`; **[REC]** Claude
Code's proposal, **accepted as specified in Prompt 181**; **[OPEN]** none remains (C1–C11 in
[M5c-J](#m5c-j-reviewer-decisions) are accepted). M5c adds **no** persistence, migration, review
handler, endpoint, production registry entry, setting, live provider or network execution. Prompt
encoding does **not** make a live model injection-resistant.

##### M5c acceptance (Prompt 181)

**Decision.** The external reviewer accepted, in Prompt 181: the complete corrected M5c
specification (proposed in Prompt 179, revised in Prompt 180); decisions C1–C11 as specified,
including the eight-question first-template table of
[M5c-C2](#m5c-c2-proposed-first-template-content) with its separately authored search queries and
explicit documentary flags; and the value and API contracts, pinned artifact loaders, bounded
reads, prompt binding, closed request schemas, deterministic serialization, size refusal, repair
reassembly, fixed errors, privacy boundaries and planned checks. These form the M5c implementation
contract; no M5c specification decision remains open. The same review accepted the M5b
main-publication CI evidence as recorded in Prompt 180, with its exact-commit scope and split
attribution.

**Binding wording clarification.** M5a `parse_output` keeps its existing two-pass validation: a
bounded preliminary JSON scan, then strict JSON-mode schema validation of the **same original
response text**. M5c and M5g perform no additional entity, escape, Unicode or JSON decoding of the
quotation strings returned by that validation. Earlier wording such as "parsed exactly once by
M5a" is replaced below by this description. The literal-backslash behaviour and all round-trip
tests are unchanged, and the clarification changes no algorithm, output schema or existing M5a
contract.

**Reviewer evidence and scope.** The reviewer independently checked the byte sizes and SHA-256
values of the three exports: `.local/p179/m5b-main-evidence-and-m5c-spec.diff` (57,650 bytes,
`c82867b4f076fa7aec554e367509cb41a425e30d0e83fcf52a3b6fe9a2e99cb0`),
`.local/p179/m5b-acceptance.diff` (30,213 bytes,
`77ed93bb26cd3ae7896dd0088b90632cb576df4ca50a9d2eb1bb708a816838b0`; omitted from the Prompt 179
handoff and independently verified only now, in Prompt 181) and
`.local/p180/m5c-contract-corrections-and-m5b-ci-evidence.diff` (111,202 bytes,
`23630eafc0e54de4df96c7831fc671965c99fa6059762462901a1fba372e87df`). Applying the Prompt 179 and
Prompt 180 exports in sequence to the published `90295717` documentation reproduced all four
final document blobs (README `f15dc993`, ADR-0020 `ea457ebe`, plan `a9727ab4`, threat model
`43fc56ea`). The reviewer inspected the corrected contracts and the relevant published domain
source, including M5a's two-pass `parse_output`, and checked the proposed template against the
published evaluation question inputs and search-query lists. No project suite, build,
installed-wheel check, database, Docker or provider call was run for this acceptance; earlier
isolated probes and independently retrieved CI logs keep their recorded scope and are not M5c
implementation evidence. Exact prompt wording and packaged artifact bytes will be inspected with
the implementation; their future pinned digests are not checked by this acceptance.

*Reviewer probes (recorded in Prompt 180).* The reviewer's encoding, metadata and prompt-binding
probes were isolated standard-library and existing-domain checks, not M5c implementation tests (no
M5c code exists). They confirmed that M5a `StructuredRequest` accepts a prompt-reference digest and
a system text that are independent of each other (its existing, shape-only contract, not an M5a
defect; M5c must perform the binding, [M5c-E1](#m5c-e1-prompt-binding-in-assembly)); that
`ChunkEvidence` accepts a lone surrogate in `title`, `section_path` and `version_label`; and that
`json.dumps(..., ensure_ascii=False)` output containing one then fails during UTF-8 encoding
([M5c-F3](#m5c-f3-encoding-rule-unicode-and-identifiers)).

##### M5c-A. Accepted requirements and current-source facts

[DECISION]

- Sequence row M5c: a TOML review template, a deterministic Planner, `prompts/verifier/v1.md` and
  `prompts/risk_analyst/v1.md` as packaged data with pinned SHA-256, and request assembly that
  places evidence only inside delimited blocks with **safe encoding** of document text
  (Correction E). Placement `evidenceguard_agents` (`planner`, `prompts`, `assembly`); depends on
  M5a and M5b; no persistence.
- W2/W3: the template is one packaged TOML file read with `tomllib` (no new dependency), SHA-256
  pinned in the review configuration (stored by M5d) and **independent of the ground truth**; a
  planner or fake must never read `sample_data/ground_truth/`. D4: the Planner is deterministic
  code (no LLM query expansion, E3).
- M5a: `StructuredRequest(purpose, prompt, model_id, question_id, system_text, user_text,
  max_output_tokens, timeout_ms)` with `system_text` 1–64,000 UTF-8 bytes, `user_text` 1–400,000
  UTF-8 bytes, both without NUL, `max_output_tokens` 1–8,192, `timeout_ms` 1,000–120,000 (default
  60,000). Its canonical request digest covers the purpose, output schema, prompt reference, model,
  question, token limit and the SHA-256 of both texts (not `timeout_ms`). `PromptRef` checks shape
  only, and `StructuredRequest` does not relate `prompt.sha256` to `system_text`. Zero hidden
  retries; one repair per stage built by M5c **from fixed failure categories, never from raw
  output** (W4/P8).
- M5b: quotations are matched against original evidence text only (segment-wise NFD and
  whitespace collapsing; header and body separately); M5b does no entity or escape decoding; M5c
  must give the model exactly the retrieved chunk IDs to cite and either present document text so
  that quotations of it are original text, or apply one reviewed deterministic decoder before M5b.
  The Analyst stage is per question with an empty `shared` (P9). `QuestionEvidence` and
  `VerifiedQuestion` check consistency only; they cannot prove that a result was retrieved for the
  question or that a `VerifiedQuestion` came from `verify_question` or `recheck_verified`.
- Canary distinction (Correction E): the end-to-end **acceptance fixture** (authorized injected
  document in the retrieved evidence **and inside an evidence block of the assembled request**;
  canary absent from all checked outputs), the **negative control** (a script that emits the canary;
  the same checker must fail) and the separately labelled **limitation probe** (a verbatim canary in
  a genuine authorized quotation is accepted). The end-to-end run belongs to M5g; M5c supplies the
  assembled requests these fixtures inspect.

[FACT]

- `evidenceguard_agents` holds `providers` and `scripted` only; the packaging test fixes its file
  set and forbids `socket`, `ssl`, `http`, `urllib`, `os`, `pathlib`, `tomllib` and `io` in the M5a
  modules, with "M5c's packaged-artifact loading ... its own reviewed allowlists" (M5a A).
- `EvidenceQuestion(question_id, text 1–500, search_queries 1–5 of ShortText 1–200,
  requires_documentary_support)` is a frozen M1 `DomainModel` that strips surrounding whitespace
  and rejects unknown fields; `RetrievalRequest(queries, k)` requires 1–8 distinct queries and `k`
  1–20 (default 8 in `RETRIEVAL_CONFIG_V1`); `RetrievalResult.items` hold at most `k` chunks with
  `fused_rank` exactly 1 … n in that order.
- `ChunkEvidence` bounds `text` to 1–4,000 code points with a verified digest (so chunk text is
  UTF-8 encodable) and `section_path` to at most 6 parts, but it does **not** bound the length of
  `title`, any `section_path` part or `version_label`, does not bound `revision_no` above, and
  does not require those metadata strings to be UTF-8 encodable. M5c does not change M4d.
- `ReportContent` allows at most 100 questions. The wheel packages every file inside each listed
  package directory (hatch `packages`), so data files under `evidenceguard_agents/` ship in the wheel.
- The ground truth (`sample_data/ground_truth/*.toml`) holds authored questions (IDs `RET-01`,
  `ENC-01`, `CMP-01`, `CMP-02`, `INC-01`, `BCP-01`, `SUB-01`, `SOC-01`) with their own search
  queries, expected statuses, gold and forbidden anchors, acceptable claims and quotes for
  evaluation; nothing in the packages reads it outside M4e evaluation code.

##### M5c-B. Placement, files and imports

[REC] New files (all in `packages/agents/evidenceguard_agents/`):

| File | Contents |
|---|---|
| `artifact_errors.py` | the fixed M5c errors ([M5c-G](#m5c-g-errors-privacy-and-process-control)) |
| `templates.py` | `TemplateRef`, `ReviewTemplate`, `parse_template`, `load_template`, `load_pinned_template`, the template registry with pinned digests |
| `planner.py` | `PlannedQuestion`, `plan_review` |
| `prompts.py` | `PromptSpec`, `load_prompt`, `load_pinned_prompt`, the prompt registry with pinned digests and purposes |
| `assembly.py` | `VERIFIER_INPUT_FORMAT`, `ANALYST_INPUT_FORMAT`, `ModelSettings`, `VerifierRequestInputs`, `AnalystRequestInputs`, `RepairReason`, `assemble_verifier_request`, `assemble_analyst_request`, `assemble_repair_request` |
| `data/templates/vendor_security_review_v1.toml` | the first review template ([M5c-C2](#m5c-c2-proposed-first-template-content)) |
| `data/prompts/verifier/v1.md`, `data/prompts/risk_analyst/v1.md` | the versioned system prompts |

Imports: `templates.py` and `prompts.py` may use the standard library modules `tomllib` (templates
only), `hashlib`, `dataclasses`, `contextlib` and `importlib.resources` (packaged-resource reads
only, by fixed relative names; no path from a caller, no environment, no `os`, `pathlib` or `io`
import of their own); `planner.py` and `assembly.py` use only `json`, `hashlib`, `dataclasses`,
`enum`, `contextlib` and the domain (`evidence`, `retrieval`, `model_calls`, `provenance`) plus
`templates`, `prompts` and `artifact_errors`. No network module, no `sample_data` access, no
persistence, worker or API import. The packaging test gains these exact allowlists, the new file
set, and a check that no agents module mentions `ground_truth` or `sample_data`.

##### M5c-B1. Value and API contract

[REC] Every M5c value is a frozen dataclass with `init=False` and a validating keyword-only
constructor, in the M5a/M5b style:

- **Exact types.** Each field must have exactly the stated type (`type(x) is T`); a `bool` is
  never an `int`, a `list` is never a `tuple`, and a subclass is not accepted. Unknown keyword
  arguments are rejected.
- **Nested reconstruction.** Each nested domain value is rebuilt through its own public
  constructor from its fields (`EvidenceQuestion.model_validate` of its own field values for
  the Pydantic question; the constructors of `PromptRef`, `RetrievalRequest`, `QuestionEvidence`
  and `VerifiedQuestion` for the others) and the **rebuilt** value is stored; a value made with
  `model_construct`, `object.__setattr__` or any other bypass is therefore revalidated, and for
  `EvidenceQuestion` the rebuilt value must also equal the supplied one (so stripping cannot
  silently change it).
- **Tuple immutability.** Sequence fields are exact `tuple`s of rebuilt, frozen elements; no list,
  dict or other mutable container is stored.
- **Replacement.** `dataclasses.replace` calls the same constructor, so every replacement is
  validated exactly like direct construction.
- **Errors.** Any failure in direct construction or replacement raises a fresh
  `InvalidAgentValueError` (`invalid_agent_value`) with no cause or context. Equality compares all
  fields. `str` equals `repr`; the representations below show identifiers, versions, purposes,
  digests and counts only.

| Value | Fields (exact types) | Bounds and allowed combinations | Representation |
|---|---|---|---|
| `TemplateRef` | `template_id: str`, `version: int`, `sha256: str` | `template_id` matches `^[a-z][a-z0-9_]{0,31}$`; `version` 1–999; `sha256` 64 lowercase hex. Shape only: it does not prove that a packaged file has this digest. | `TemplateRef(template_id='…', version=N, sha256='…')` |
| `ReviewTemplate` | `ref: TemplateRef`, `title: str`, `questions: tuple[EvidenceQuestion, ...]` | `ref` rebuilt; `title` satisfies the template-string rule (1–200 code points); 1–100 questions; question IDs unique; every question satisfies the template-question rule ([M5c-C](#m5c-c-review-template-format-validation-identity)). Direct construction cannot prove packaged-file origin even with a plausible digest ([M5c-C1](#m5c-c1-loading-identity-and-trusted-paths)). | `ReviewTemplate(template_id='…', version=N, questions=N)` (no title or question text) |
| `PlannedQuestion` | `question: EvidenceQuestion`, `retrieval: RetrievalRequest` | `question` rebuilt and satisfies the template-question rule; `retrieval` rebuilt with `k` 1–20; **`retrieval.queries` must equal `question.search_queries` exactly** (same strings, same order, same count). | `PlannedQuestion(question_id='…', queries=N, k=N)` |
| `PromptSpec` | `ref: PromptRef`, `purpose: ModelPurpose` | `ref` rebuilt through `PromptRef`. Shape only: registry membership, purpose and digest are checked by the loaders and by assembly ([M5c-E1](#m5c-e1-prompt-binding-in-assembly)). | `PromptSpec(prompt_id='…', version=N, purpose='…')` |
| `ModelSettings` | `model_id: str`, `max_output_tokens: int`, `timeout_ms: int` | `model_id` matches the M5a model-ID pattern; `max_output_tokens` 1–8,192 (default 4,096, C6); `timeout_ms` 1,000–120,000 (default 60,000). | `ModelSettings(model_id='…', max_output_tokens=N, timeout_ms=N)` |
| `RepairReason` | `purpose: ModelPurpose`, `question_id: str`, `code: CallOutcome` or `RejectionReason`, `item_index: int` or `None`, `citation_index: int` or `None` | See [M5c-F5](#m5c-f5-repair-requests). `code` is exactly `CallOutcome.INVALID_OUTPUT` (both positions `None`, either purpose) or an M5b `RejectionReason` whose stage matches `purpose` (verification → `verifier`, analysis → `risk_analyst`) and whose positions follow the `ProvenanceRejection` rules. Any other `CallOutcome` is rejected. | `RepairReason(purpose='…', question_id='…', code='…', item_index=N, citation_index=N)` |
| `VerifierRequestInputs` | `evidence: QuestionEvidence`, `prompt: PromptSpec`, `system_text: str`, `settings: ModelSettings` | Each rebuilt; `prompt.purpose` is `verifier`. Binding to the registry and the system text is checked by assembly. | `VerifierRequestInputs(question_id='…', items=N, prompt_id='…', prompt_version=N)` |
| `AnalystRequestInputs` | `owner: VerifiedQuestion`, `question: EvidenceQuestion`, `prompt: PromptSpec`, `system_text: str`, `settings: ModelSettings` | Each rebuilt; `owner.question_id == question.question_id`; `prompt.purpose` is `risk_analyst`. | `AnalystRequestInputs(question_id='…', claims=N, citations=N, prompt_id='…', prompt_version=N)` |

`RepairReason` also has two constructors: `RepairReason.invalid_output(*, purpose, question_id)`
and `RepairReason.from_rejection(rejection: ProvenanceRejection)`, which rebuilds the rejection
through its own constructor, maps its stage to the purpose and copies its question ID, reason and
positions (its `rejected_count` is not carried).

##### M5c-C. Review template (format, validation, identity)

[REC] TOML, UTF-8 without BOM, at most 65,536 bytes, parsed with `tomllib` after a strict UTF-8
decode; unknown keys rejected at every level; line endings are not normalized (the digest covers the
exact bytes):

| Key | Type and bound |
|---|---|
| `format` | exactly `"eg-review-template-v1"` |
| `template_id` | `^[a-z][a-z0-9_]{0,31}$` |
| `version` | integer 1–999 (not a boolean) |
| `title` | template string, 1–200 code points |
| `[[questions]]` | 1–100 tables, in file order |
| `questions.id` | the `QuestionId` pattern, unique within the template |
| `questions.text` | template string, 1–500 code points |
| `questions.search_queries` | array of 1–5 distinct template strings, each 1–200 code points |
| `questions.requires_documentary_support` | boolean, required (no default, so intent is explicit) |

**Template-string rule** (applied identically to `title`, question text and every query): an exact
`str`; strictly UTF-8 encodable (no lone surrogate); no U+0000; equal to its own `str.strip()`
(no leading or trailing whitespace); within the stated code-point bound; therefore never blank.
**Template-question rule:** the question ID matches `QuestionId`; text and queries satisfy the
template-string rule; queries are distinct by exact code points; the flag is a `bool`; and the
`EvidenceQuestion` built from these values equals them exactly (so the M1 whitespace stripping can
never alter a value silently, even where Pydantic's notion of whitespace differs from
`str.strip()`).

`parse_template(data: bytes) -> ReviewTemplate` is pure: `data` must be exactly `bytes`, at most
65,536 bytes and not start with the UTF-8 BOM; it is decoded strictly, parsed and validated, and the
returned `ref` is `TemplateRef(template_id, version, sha256=SHA-256 of the exact input bytes)`. Any
failure, including a non-`bytes` argument, raises `InvalidTemplateError`. `parse_template` is for
tests and for the trusted loaders; its digest identifies the bytes it was given, nothing more.

**Versioning.** A packaged template file is never edited after publication: any change is a new
`version` with a new file and pinned digest; earlier versions stay packaged so a stored review's
`TemplateRef` remains loadable (M5d stores the ref with the review).

##### M5c-C1. Loading, identity and trusted paths

[REC] The registry is a fixed in-code mapping from `(template_id, version)` to a fixed relative
resource name and its pinned SHA-256 (v1: `vendor_security_review` 1 →
`data/templates/vendor_security_review_v1.toml`).

- `load_template(template_id: str, version: int) -> ReviewTemplate`: arguments of the wrong type or
  shape → `InvalidAgentArgumentError`; a well-formed pair not in the registry →
  `UnknownTemplateError`; otherwise a **bounded read** of the resource (below), then the digest of
  the bytes must equal the pinned digest, `parse_template` must succeed, and the parsed
  `template_id` and `version` must equal the registry key; a missing or unreadable resource, an
  oversize resource, a digest mismatch, a parse failure or a key mismatch →
  `TemplateIntegrityError`.
- `load_pinned_template(ref: TemplateRef) -> ReviewTemplate` is the **only trusted production and
  reload path**: `ref` must be exactly a `TemplateRef` (rebuilt; else `InvalidAgentArgumentError`);
  it calls `load_template(ref.template_id, ref.version)` and then requires the **complete** loaded
  reference (ID, version and digest) to equal `ref`, the reference pinned in the review's stored
  configuration; a digest that differs → `TemplateIntegrityError`.
- A directly constructed `ReviewTemplate` (or one from `parse_template` on other bytes) can carry
  any plausible digest; nothing in the value proves that a packaged file had it. M5d, M5g and every
  reload therefore obtain the template only through `load_pinned_template` and never accept a
  caller-supplied `ReviewTemplate` as proof of origin.
- **Bounded read.** The resource is opened in binary mode through `importlib.resources` and read
  with repeated `read(n)` calls, each bounded by the remaining allowance (the limit plus one byte,
  65,537 for templates and 64,001 for prompts, minus the bytes already received); short reads are
  continued, reading stops at end of file or as soon as more than the limit has been received,
  and under the reader contract no more than the limit plus one byte is received. More than the
  limit is rejected. The file is never read whole and then measured. *(Wording corrected in
  Prompt 183: it previously said the total requested size never exceeds the limit plus one byte,
  which does not hold for the sum of requests when reads are short; the reviewer approved the
  implemented strategy.)*

##### M5c-C2. Proposed first-template content

[REC, proposed in Prompt 180; **accepted as specified in Prompt 181**] `vendor_security_review` v1, title "Vendor
security review", eight questions in this order. Per C3 as narrowed by the reviewer, the question
IDs and texts are shared with the evaluation questions so M7 can score them; the search queries are
**authored separately** from the question text and none equals a ground-truth search query; no
expected status, gold or forbidden anchor, acceptable claim, quote, relevance list or other
answer-bearing label is copied into the template or its queries, and nothing generates the template
from `ground_truth` at runtime or build time. The documentary flags (proposed by Claude Code,
accepted in Prompt 181) are:
`true` where the question asks about an independent certification, attestation or compliance
status that a vendor statement alone should not settle.

| ID | Question text | Search queries (in order) | Documentary |
|---|---|---|---|
| `RET-01` | How long is customer data retained after termination? | "customer data retention after contract termination"; "data deletion after termination" | `false` |
| `ENC-01` | Is customer data encrypted at rest? | "customer data encryption at rest"; "stored data encryption" | `false` |
| `CMP-01` | Does the vendor hold an ISO 27001 certification? | "ISO 27001 certificate"; "information security management certification" | `true` |
| `CMP-02` | Is the vendor HIPAA compliant? | "HIPAA compliance status"; "protected health information safeguards" | `true` |
| `INC-01` | What is the breach-notification timeframe? | "security breach notification period"; "incident notification to customers" | `false` |
| `BCP-01` | What is the recovery time objective for production? | "recovery time objective production"; "disaster recovery targets" | `false` |
| `SUB-01` | Which subprocessors are used, and in which regions? | "subprocessor list and regions"; "third-party subprocessors data location" | `false` |
| `SOC-01` | Is there an independent SOC 2 report? | "SOC 2 report"; "independent service auditor report" | `true` |

##### M5c-D. Deterministic Planner

[REC] `plan_review(template: ReviewTemplate, *, k: int = 8) -> tuple[PlannedQuestion, ...]`: the
template is rebuilt (not exactly a `ReviewTemplate`, or invalid → `InvalidAgentArgumentError`) and
`k` must be an `int` 1–20 (else `InvalidAgentArgumentError`); it returns exactly one
`PlannedQuestion(question, RetrievalRequest(question.search_queries, k))` per template question,
**in template order**. No query expansion, rewriting, reordering, deduplication across questions or
model call (D4/E3). The output is a pure function of the template and `k`; it is trusted only when
the template came from `load_pinned_template`. M5d stores the template reference, and M5g calls
`plan_review` again on the reloaded template rather than storing a second copy of the questions.

##### M5c-E. Prompts (identity, versions, hashes)

[REC] The prompt registry maps `(prompt_id, version)` to a fixed relative resource name, its
pinned SHA-256 and its `ModelPurpose`: `verifier` v1 → `data/prompts/verifier/v1.md` (purpose
`verifier`), `risk_analyst` v1 → `data/prompts/risk_analyst/v1.md` (purpose `risk_analyst`).

- `load_prompt(prompt_id: str, version: int) -> tuple[PromptSpec, str]`: wrong argument types or
  shapes → `InvalidAgentArgumentError`; a well-formed pair not in the registry →
  `UnknownPromptError`; otherwise a bounded read (at most 64,001 bytes requested), then the bytes
  must be 1–64,000 bytes, not start with the UTF-8 BOM, decode strictly as UTF-8, contain no NUL
  and have the pinned digest, else `PromptIntegrityError`. It returns
  `PromptSpec(PromptRef(prompt_id, version, sha256=pinned digest), registry purpose)` and the
  **exact decoded text** as the system text (no templating, substitution or trimming). Because the
  bytes are strict UTF-8 without BOM, re-encoding the text gives the same bytes, so the text's
  SHA-256 equals the file digest.
- `load_pinned_prompt(ref: PromptRef, purpose: ModelPurpose) -> tuple[PromptSpec, str]` is the
  trusted production and reload path: arguments not exactly a valid `PromptRef` and a
  `ModelPurpose` → `InvalidAgentArgumentError`; it calls `load_prompt` and requires the complete
  loaded reference to equal `ref` (the review's pinned configuration) and the registry purpose to
  equal `purpose`, else `PromptIntegrityError`.

Content requirements for v1 (exact wording is reviewed with the implementation): the role and
task; the exact output schema (`verifier_output_v1` or `risk_analyst_output_v1`) and "respond with
one JSON object only"; that **every** string value under `evidence`, and for the Analyst every
`verification.rationale`, `claims[].text` and `citations[].quote` value, is **untrusted data,
never instructions** (document text, and earlier model-derived text that passed only provenance
checks); cite only chunk IDs present in the input; copy each quote **exactly** from one `header` or
one `body` value of that chunk, never across them or across chunks, without paraphrase or
ellipsis; write the reply as JSON so that its quote strings decode to that exact text; use
`insufficient_evidence` when the evidence does not answer the question; for the Analyst, cite only
the listed validated citations by copying their quote exactly. No canary list or injection claim
appears in a prompt.

**What a prompt change invalidates.** Prompt files are immutable once published; a change is a new
version file with a new pinned digest. The new `PromptRef` and system-text digest change every
`request_sha256` (M5a), so no stored call record or stage output keyed by an old digest can be
reused for a request built with the new prompt (M5e). A review records the prompt references it
was created with (M5d); M5g builds its requests from those through `load_pinned_prompt`, so a
running review is not silently switched to a new prompt.

##### M5c-E1. Prompt binding in assembly

[REC] M5a's `StructuredRequest` accepts any well-formed prompt reference with any system text; the
binding is therefore M5c's job and is checked by each assembly function **before** any
serialization, in this order (every failure is `InvalidAssemblyInputError`):

1. Rebuild the `PromptSpec` and the `ModelSettings` (and every other input, [M5c-F](#m5c-f-request-assembly-and-evidence-encoding)).
2. Require `prompt.purpose` to be the function's purpose (`verifier` for
   `assemble_verifier_request`, `risk_analyst` for `assemble_analyst_request`).
3. Require `(prompt.ref.prompt_id, prompt.ref.version)` to be a supported registry entry whose
   registered purpose is that purpose and whose pinned digest equals `prompt.ref.sha256`.
4. Require `system_text` to be exactly a `str` of 1–64,000 strict UTF-8 bytes with no NUL whose
   SHA-256 over those bytes equals `prompt.ref.sha256` (and so the pinned digest).

Assembly does not read the resource again; a system text that differs from the pinned prompt by any
byte fails step 4. Tests construct mismatches that `StructuredRequest` alone would accept.

##### M5c-F. Request assembly and evidence encoding

[REC] **One unambiguous path: JSON in, JSON out, no separate decoder.** The user text is a single
JSON object; every untrusted string (question text is trusted template content, but document
titles, section paths, version labels, headers, bodies and all earlier model-derived text are
untrusted) appears **only as a JSON string value**. The model's reply is itself strict JSON,
validated by M5a `parse_output` with its existing two passes (a bounded preliminary JSON scan, then
strict JSON-mode schema validation of the same original response text); M5c and M5g perform no
additional entity, escape, Unicode or JSON decoding of the quotation strings that validation
returns, and no entity encoding is used.

**Common algorithm** for `assemble_verifier_request(inputs: VerifierRequestInputs)` and
`assemble_analyst_request(inputs: AnalystRequestInputs)`, both returning `StructuredRequest`:

1. `inputs` must be exactly the function's input type; it and every nested value are rebuilt
   ([M5c-B1](#m5c-b1-value-and-api-contract)); then the prompt binding of
   [M5c-E1](#m5c-e1-prompt-binding-in-assembly) and the identity checks of the stage run.
2. The user object is built ([M5c-F1](#m5c-f1-verifier-input-schema-eg-verifier-input-v1),
   [M5c-F2](#m5c-f2-analyst-input-schema-eg-analyst-input-v1)); every string in it is checked for
   strict UTF-8 encodability ([M5c-F3](#m5c-f3-encoding-rule-unicode-and-identifiers)).
3. It is serialized with the rule of M5c-F3 and its exact UTF-8 size is checked
   ([M5c-F4](#m5c-f4-size-refusal-and-bounds)).
4. `StructuredRequest(purpose, prompt=prompt.ref, model_id=settings.model_id, question_id,
   system_text, user_text, max_output_tokens=settings.max_output_tokens,
   timeout_ms=settings.timeout_ms)` is constructed; an unexpected failure is
   `InvalidAssemblyInputError`.

Errors before step 3 are `InvalidAssemblyInputError`; only an oversize user text is
`RequestTooLargeError`. No request exists until every check has passed.

**Trusted-input boundary.** Assembly checks types, values, purposes, prompt binding and internal
identities only. It cannot prove that the `QuestionEvidence` result was retrieved for this question
under this review's snapshot, or that an Analyst `owner` came from `verify_question` or
`recheck_verified` for this review (M5b-E1); M5g must supply only values obtained through those
trusted paths. **Request digests identify content and configuration, not tenant authorization or
review identity:** two reviews (or tenants) with identical inputs produce identical user text and
`request_sha256`. M5d, M5e and M5g retain the tenant, review, snapshot and question bindings
around each request and call record.

##### M5c-F1. Verifier input schema (`eg-verifier-input-v1`)

[REC] `assemble_verifier_request` additionally requires nothing beyond its rebuilt
`QuestionEvidence` (whose question and result it uses); `question_id` is
`evidence.question.question_id`. The object is closed (exactly these keys); keys are emitted in
sorted order by the serializer, so the order shown is the byte order:

| Path | JSON type | Source and bounds |
|---|---|---|
| `evidence` | array, 0–20 entries | one entry per `evidence.result.items`, in that (fused-rank) order |
| `evidence[].body` | string | the chunk's `body_text`, unchanged; with the header at most 4,000 code points |
| `evidence[].chunk_id` | string | canonical lowercase hyphenated UUID of the chunk |
| `evidence[].document` | object | the seven keys below |
| `evidence[].document.authenticity` | string | always `"not_established"` |
| `evidence[].document.effective_date` | string or `null` | ISO `YYYY-MM-DD` |
| `evidence[].document.revision_no` | integer | ≥ 1 (no upper bound in `ChunkEvidence`) |
| `evidence[].document.section_path` | array of strings, 0–6 | in order; each part unchanged and unbounded in length |
| `evidence[].document.source_type` | string | `vendor_statement`, `contract` or `third_party_report` |
| `evidence[].document.title` | string | unchanged; ≥ 1 code point, unbounded in length |
| `evidence[].document.version_label` | string or `null` | unchanged; unbounded in length |
| `evidence[].header` | string or `null` | the repeated table header `header_text`, given separately from the body |
| `evidence[].rank` | integer | the item's `fused_rank`, 1 … n in order |
| `format` | string | exactly `"eg-verifier-input-v1"` |
| `question` | object | the three keys below |
| `question.id` | string | the `QuestionId` |
| `question.requires_documentary_support` | boolean | the template flag |
| `question.text` | string | trusted template text, 1–500 code points |

Not included: tenant, review, snapshot, revision or document IDs, `document_key`, content digest,
ordinal, table flag, spans, offsets, fused score and channel hits. `header` and `body` match M5b's
independent spans. An empty result gives `"evidence":[]` (the model should answer
`insufficient_evidence`).

##### M5c-F2. Analyst input schema (`eg-analyst-input-v1`)

[REC] `assemble_analyst_request` requires, after rebuilding, `owner.question_id ==
question.question_id`, `owner.verification.question_id == question.question_id` and the owner's
claims to reference only existing citation indexes (already guaranteed by the rebuilt
`VerifiedQuestion`). No raw chunk text and no unvalidated evidence is included (C4). The object is
closed; keys are in serializer (sorted) order:

| Path | JSON type | Source and bounds |
|---|---|---|
| `citations` | array, 0–80 entries | `owner.verification.citations`, in index order |
| `citations[].authenticity` | string | always `"not_established"` |
| `citations[].chunk_id` | string | canonical lowercase hyphenated UUID |
| `citations[].index` | integer | the citation's position, 0–79, equal to its array position |
| `citations[].quote` | string | the stored, validated quote, unchanged, 1–1,000 code points (document text; untrusted) |
| `citations[].source_type` | string | `vendor_statement`, `contract` or `third_party_report` |
| `claims` | array, 0–10 entries | `owner.claims`, in order |
| `claims[].citation_indexes` | array of integers, 0–8 distinct | each 0–79, as stored |
| `claims[].text` | string | the stored claim text, unchanged, 1–1,000 code points (model-derived; untrusted) |
| `format` | string | exactly `"eg-analyst-input-v1"` |
| `question` | object | `id`, `requires_documentary_support`, `text` exactly as in M5c-F1 |
| `verification` | object | the three keys below |
| `verification.evidence_status` | string | the derived `EvidenceStatus` value |
| `verification.rationale` | string | the stored `Verification.rationale`, unchanged, 1–2,000 code points (model-derived; untrusted) |
| `verification.verdict` | string | the `Verdict` value |

Not included: tenant, review, snapshot, revision and document IDs, match offsets, request digests
and the `AcceptedCitation` match details.

##### M5c-F3. Encoding rule, Unicode and identifiers

[REC] **Serializer (normative parameters).** `json.dumps(value, ensure_ascii=False,
sort_keys=True, separators=(",", ":"), allow_nan=False)`, then strict UTF-8 encoding for size
measurement; the resulting string is the `user_text`. With these parameters Python escapes the
quotation mark as `\"` and the backslash as `\\`; uses the two-character named escapes `\b`, `\t`,
`\n`, `\f` and `\r` for backspace, tab, newline, form feed and carriage return; writes every other
control U+0000–U+001F as a six-character lowercase Unicode escape (for example `\u0000`, `\u001f`);
and writes every other character literally, including U+007F, U+2028/U+2029, combining marks,
bidirectional controls, a BOM character and characters outside the BMP. Evidence and model-derived
text are never normalized, stripped, trimmed or truncated. The parameters above, not this summary,
are normative.

**Round trip and its limits.** A model reply that JSON-encodes a quotation correctly reproduces the
original characters in the quotation strings returned by M5a's validation, and M5b then matches
original text. The model is not guaranteed to encode correctly: a double-escaped or otherwise
changed quotation (for example a backslash followed by `n` where the evidence has a newline) is
returned by that validation as different text and fails the existing output or provenance checks
(`invalid_output` or a quote rejection). Evidence that itself contains a literal backslash followed
by a letter is encoded as `\\` plus the letter, and in the quotation string M5a's validation
returns for a correct reply it is again a literal backslash and letter; nothing decodes it a
second time. NUL: an evidence string containing U+0000 round-trips structurally (as `\u0000`) through the
request, but M5a `QuoteRef` forbids NUL, so a reply quoting it is `invalid_output`; not every
representable evidence string is a valid output quotation.

**Unicode validation.** M4d's text digest makes chunk text UTF-8 encodable, but metadata is not
checked: `ChunkEvidence` accepts a lone surrogate in `title`, `section_path` and `version_label`,
and the serializer's output would then fail UTF-8 encoding. Assembly therefore checks **every**
string placed in the user object (metadata, header, body, question text, rationale, claim text and
quotes) for strict UTF-8 encodability before serialization and raises the fixed private
`InvalidAssemblyInputError` for any invalid one; it does not replace, drop or escape it. M4d is
unchanged.

**Why delimiter-like content is safe.** No raw delimiter exists in the format: text such as a
closing tag, a fake `"chunk_id"` key, a closing brace, an instruction line or another JSON object
inside a document is inside one escaped string value, so it cannot end that value or create a new
field. Encoding prevents **structural** forgery only; a model can still be persuaded by the content
of a string (semantic injection), which is measured in M7.

**Identifiers.** The assembler does not insert trusted tenant, review, snapshot, revision or
document IDs as metadata ([M5c-F1](#m5c-f1-verifier-input-schema-eg-verifier-input-v1),
[M5c-F2](#m5c-f2-analyst-input-schema-eg-analyst-input-v1)). Original document text or earlier model
text may itself contain exactly those strings; such content is preserved like any other text, not
silently removed, rejected or rewritten because it resembles an identifier. Tests check the
structural omission (the closed key sets), not the absence of a substring from the whole text.

##### M5c-F4. Size refusal and bounds

[REC] **Size refusal, never truncation.** After serialization, assembly computes the exact UTF-8
byte length of the whole user text, **all metadata included**; above 400,000 bytes it raises
`RequestTooLargeError` (`request_too_large`) **before** any `StructuredRequest` exists, so nothing
is dispatched; no evidence or text is dropped, shortened or reordered to fit. The system text is
bounded by the pinned prompt (at most 64,000 bytes; a different text fails the binding). M5g maps
the refusal to an unresolved question with a fixed reason (no provider call, no reservation).

**Bound analysis.** Chunk text alone cannot bound the request: Verifier text is at most 20 chunks
of 4,000 code points, which is up to 320,000 bytes of literal 4-byte characters or 480,000 bytes
when every character is a control written as a six-byte escape, and `title`, `section_path` parts
and `version_label` have no length bound in `ChunkEvidence`, so metadata alone can exceed the
limit. Analyst text is at most 80 quotes and 10 claims of 1,000 code points and a 2,000-code-point
rationale, which can also exceed 400,000 bytes after escaping. In every case the exact measured size
decides; the refusal path is expected, not exceptional.

**Byte limits are not memory limits.** The 400,000-byte limit bounds accepted request bytes. The
user text is built in full before it is measured, so peak memory during assembly grows with the
size of the supplied inputs (including unbounded metadata already held in memory); M5c makes no
peak-memory guarantee.

##### M5c-F5. Repair requests

[REC] `assemble_repair_request(original: StructuredRequest, inputs: VerifierRequestInputs |
AnalystRequestInputs, reason: RepairReason) -> StructuredRequest` uses **reassembly**:

1. `original` must be exactly a `StructuredRequest` and is rebuilt through its constructor; `inputs`
   must be exactly one of the two input types and is rebuilt; `reason` must be exactly a
   `RepairReason` and is rebuilt. Any failure → `InvalidAssemblyInputError`.
2. The input type fixes the purpose; `original.purpose` and `reason.purpose` must equal it, and
   `reason.question_id` must equal `original.question_id`; else `InvalidAssemblyInputError`.
3. The unrepaired request is reassembled from `inputs` by the same algorithm
   ([M5c-F](#m5c-f-request-assembly-and-evidence-encoding)), including the prompt binding and
   Unicode checks; its own fixed errors propagate unchanged.
4. The reassembled request must equal `original` in every field (purpose, prompt reference, model,
   question, system text, user text, token limit and timeout, hence the same `request_sha256`);
   else `InvalidAssemblyInputError`. A request that already contains a `repair` member can never
   equal a reassembled one, so an already-repaired request is rejected here
   (`InvalidAssemblyInputError`); a test pins this case explicitly.
5. The repair member is added to the reassembled user object, the object is serialized with the
   same rule, the size rule applies (`RequestTooLargeError`), and a new `StructuredRequest` is
   built with the **same** purpose, prompt reference, system text, model, question, token limit and
   timeout and the new user text.

**Repair member** (closed, sorted keys): `"repair":{"citation_index":<int or null>,
"item_index":<int or null>,"reason":<code>}`. For `invalid_output` both positions are `null`; M5a
gives no position and none is invented. For an M5b `RejectionReason` the positions are those of the
`ProvenanceRejection` for the same question and purpose, with the M5b stage and position rules:

| Codes | Purpose | `item_index` | `citation_index` |
|---|---|---|---|
| `invalid_output` | either | `null` | `null` |
| `chunk_not_retrieved`, `quote_blank`, `quote_not_found`, `quote_too_long`, `quote_not_exact` | `verifier` | 0–9 | 0–7 |
| `claim_uncited` | `verifier` | 0–9 | `null` |
| `verdict_unsupported`, `rationale_blank` | `verifier` | `null` | `null` |
| `citation_not_validated`, `citation_not_shared` | `risk_analyst` | 0–19 | 0–7 |
| `foreign_question`, `mixed_verdicts`, `finding_status_unsupported`, `finding_text_blank` | `risk_analyst` | 0–19 | `null` |

Positions are range-checked only; the failed output is not an input, so whether a position existed
in it is M5g's responsibility (it passes the M5b rejection of that attempt). An unknown code, a
code from the wrong stage or purpose, out-of-range positions or a mismatched question are fixed
private errors (`InvalidAgentValueError` at `RepairReason` construction,
`InvalidAssemblyInputError` at assembly).

**What a repair request contains.** No raw response, failed-attempt output or exception text is
added; the repair member holds only the fixed fields above. An Analyst repair request still
contains, like its original, the already-validated Verifier rationale, claims and quotations
(model-derived and document text that M5b accepted). Its digest differs from the original's because
the user text differs. The function cannot know how many repairs a stage has used; enforcing the
one-repair-per-stage lifetime budget remains M5g's responsibility (W4/P8).

**Request digest.** Unchanged M5a rule ([M5c-A](#m5c-a-accepted-requirements-and-current-source-facts)).
With the deterministic serializer, identical inputs give identical bytes and digests (pinned by
tests).

##### M5c-G. Errors, privacy and process control

[REC] Fixed errors in `evidenceguard_agents.artifact_errors`, all subclasses of
`ReviewArtifactError` (code as message, fresh, raised after the handler, no cause or context):

| Error (code) | Raised for |
|---|---|
| `InvalidTemplateError` (`invalid_review_template`) | any `parse_template` failure, including a non-`bytes` argument |
| `UnknownTemplateError` (`unknown_review_template`) | a well-formed template ID and version not in the registry |
| `TemplateIntegrityError` (`template_integrity_failed`) | a registered template whose resource is missing, unreadable or oversize, whose digest differs from the pinned one, whose bytes fail parsing or whose ID or version differs from the key; a loaded reference that differs from the pinned reference |
| `UnknownPromptError` (`unknown_prompt`) | a well-formed prompt ID and version not in the registry |
| `PromptIntegrityError` (`prompt_integrity_failed`) | a registered prompt whose resource is missing, unreadable, oversize, empty, BOM-prefixed, not strict UTF-8, NUL-bearing or of the wrong digest; a loaded reference or purpose that differs from the pinned one |
| `InvalidAgentArgumentError` (`invalid_agent_argument`) | wrong argument types or shapes for `load_template`, `load_pinned_template`, `load_prompt`, `load_pinned_prompt` and `plan_review` (including `k`) |
| `InvalidAgentValueError` (`invalid_agent_value`) | invalid direct construction or replacement of any M5c value |
| `InvalidAssemblyInputError` (`invalid_assembly_input`) | invalid or mismatched assembly inputs, purpose or prompt-binding failures, invalid Unicode, repair mismatches, already-repaired requests |
| `RequestTooLargeError` (`request_too_large`) | a serialized user text above 400,000 bytes |

Checks run in the order given in each section, so the same invalid input always produces the same
error. Every public operation runs as one guarded operation (as in M5a/M5b); process control
propagates as the same object. `repr`/`str` show identifiers, versions, purposes, digests and
counts only, never template title, question or prompt text, evidence, quotes or model text. Nothing
logs. Resource reads are bounded as in [M5c-C1](#m5c-c1-loading-identity-and-trusted-paths).

##### M5c-H. Planned tests (not written or run)

*Database-independent* (`tests/test_review_templates.py`, `tests/test_prompts.py`,
`tests/test_request_assembly.py`, `tests/test_packaging.py`):

- **Template:** every key and bound, unknown keys, duplicate IDs and queries, booleans for integers,
  missing flag, BOM, invalid UTF-8, oversize file (65,536 accepted, 65,537 rejected), NUL, lone
  surrogate (through a direct `ReviewTemplate`/`PlannedQuestion` construction, since TOML text
  cannot carry one) and edge whitespace rejected in the title, texts and queries alike, file-order
  preservation; `parse_template` digest equals the SHA-256 of the exact input bytes (also for CRLF
  and trailing-newline variants, which differ).
- **Loading and identity:** pinned digest of the packaged v1 file; tampered bytes, a missing
  resource and an oversize resource → `TemplateIntegrityError`; each bounded-read request stays
  within the remaining allowance and no more than the limit plus one byte is received (a counting
  reader stub); unknown ID or version →
  `UnknownTemplateError`; wrong argument types → `InvalidAgentArgumentError`;
  `load_pinned_template` with a reference whose digest, ID or version differs →
  `TemplateIntegrityError` or `UnknownTemplateError` as specified; a directly constructed
  `ReviewTemplate` with the pinned digest and altered questions is **not** equal to the loaded one
  and is never accepted by `load_pinned_template`.
- **Values:** direct construction, `dataclasses.replace`, nested `model_construct` and
  `object.__setattr__` bypasses, lists for tuples, `bool` for `int`, unknown keywords and
  subclasses for every value in M5c-B1 → `InvalidAgentValueError`; `PlannedQuestion` with
  reordered, missing or extra queries; representations free of title, question and prompt text.
- **Planner:** one planned question per template question in order, `k` bounds and default,
  queries passed unchanged, determinism across calls.
- **Prompts:** pinned digests of both v1 files, exact-bytes system text and its SHA-256 equal to
  the file digest, tampered, BOM, NUL or oversize bytes → `PromptIntegrityError`, unknown prompt →
  `UnknownPromptError`, `load_pinned_prompt` reference and purpose mismatches.
- **Prompt binding:** wrong purpose, an unregistered prompt reference, a registered reference with a
  different digest, and a system text that differs by one byte (each accepted by `StructuredRequest`
  alone) → `InvalidAssemblyInputError` for both stages.
- **Assembly:** pinned user-text bytes and `request_sha256` for fixed inputs; exact closed key sets
  and sorted key order of both schemas; header and body kept separate; rank order; empty evidence;
  adversarial bodies (quotation marks, backslashes, a literal backslash followed by a letter, a
  closing tag, a fake `chunk_id` key, a closing brace and new object, the five named-escape controls,
  other controls, U+007F, U+2028, a BOM character, combining marks, bidirectional controls,
  supplementary characters, a NUL control) round-trip exactly through one `json.loads`, produce
  exactly the supplied entry count and leave the structure intact; lone surrogates in `title`,
  `section_path` and `version_label` → `InvalidAssemblyInputError`; trusted IDs absent as keys and
  values the assembler adds, while document text containing a tenant-ID-like string is preserved
  unchanged; the Analyst text holds only validated citations, claims and rationale; size refusal at
  400,000 (accepted) and 400,001 bytes (refused, no request created), tuned through metadata.
- **Repair:** valid repairs for `invalid_output` and for each M5b code; deterministic repaired
  bytes and digest; mismatched original and inputs (different evidence item, metadata, question,
  claim or rationale); wrong prompt, purpose, question or settings (model, token limit, timeout);
  an already-repaired request; unknown codes, wrong-stage codes and out-of-range positions; size
  refusal of a repaired text just over the limit; no raw output or exception text in any repair.
- **M5b compatibility (round trip):** a scripted response whose quote is copied from a JSON string
  value (including an escaped quotation mark, backslash and newline) passes M5a `parse_output` and is
  accepted by `verify_question` with the exact original quote; a quote that keeps a visible escape
  sequence (double-escaped) is rejected; a quote containing NUL is `invalid_output`.
- **Canary support:** an assembled request built from the injected trust-center fixture contains the
  injected chunk inside exactly one evidence string value (the input to M5g's acceptance fixture and
  negative control); the limitation probe stays in M5g.
- **Ground-truth separation (test-only reads):** no template query equals a ground-truth search
  query and the template contains no ground-truth anchor, acceptable claim or quote (the test reads
  `sample_data`; product code never does).
- **Privacy and process control:** canary-bearing evidence absent from errors and representations;
  no captured logs; process control from resource reads and encoding propagates unchanged.
- **Packaging:** the new allowlists, the file set, packaged data present in the wheel, and no agents
  module mentioning `ground_truth` or `sample_data`.

*Installed wheel* (**C10**, accepted in Prompt 181): one line, for example "review template, prompts and request
assembly ran from the installed wheel" (load the packaged template and prompts through the pinned
loaders, plan, assemble a Verifier request from a fixed evidence fixture and compare its pinned
digest). *PostgreSQL:* none.

##### M5c-I. Intended files and exclusions

- New: the five modules and three data files in M5c-B, the three test modules; ADR-0021 with the
  implementation.
- Changed: `tests/test_packaging.py`; `.github/workflows/ci.yml` for one wheel line (if C10 is
  accepted); `pyproject.toml` only if the packaged data needs an explicit include (to be confirmed
  by the wheel comparison); README, plan and threat-model status.
- Excluded: persistence, migrations, review creation, handlers, orchestration, retry or repair
  budgeting, endpoints, settings, credentials, the Anthropic adapter, any network code, any
  change to M1–M5b contracts, any live run and any quality or injection-resistance claim.
- **Later-slice obligations** (each reviewed with its slice): M5d stores the `TemplateRef`, both
  `PromptRef`s, the model settings and the tenant, review and snapshot bindings; M5e keys stored
  calls and outputs by request digest **within** those bindings; M5g loads artifacts only through
  `load_pinned_template` and `load_pinned_prompt`, supplies only trusted evidence and Verifier
  values, enforces the repair budget and runs the canary acceptance fixture, negative control and
  limitation probe; M7 measures live quality and injection behaviour.

##### M5c-J. Reviewer decisions

**All eleven decisions were accepted as specified at external review in Prompt 181**; none remains
open. *Historical:* each was proposed as [OPEN] with Claude Code's recommendation; in Prompt 180 the
reviewer supported C1, C2 and C4–C11 as design directions, subject to the Prompt 180 corrections
and review of the complete revised text, and narrowed C3 as recorded below.

1. **C1 Evidence encoding.** [REC] JSON user message with untrusted text only in JSON string values
   (JSON in, JSON out; the reply validated by M5a's existing two-pass `parse_output`; no
   additional decoding of returned quotations). *Alternative:* delimited tags
   with `&`, `<`, `>` escaping plus a reviewed entity decoder before M5b. *Tradeoff:* a format models
   handle well with one parser for both directions versus a more prompt-like layout that needs a
   second decoder and decoder-specific failure cases. *Accepted (Prompt 181);* a supported direction in Prompt 180.
2. **C2 Data location.** [REC] Packaged files under `evidenceguard_agents/data/` read through
   `importlib.resources` with bounded reads and pinned digests. *Tradeoff:* a new resource-reading
   allowlist versus embedding long text in Python constants. *Accepted (Prompt 181);* a supported direction in Prompt 180.
3. **C3 First template content.** *Reviewer (Prompt 180):* shared question IDs and question texts
   may be used as evaluation inputs; expected answers, gold anchors, relevance lists and
   answer-bearing labels must not be copied into product content or queries, and nothing generates
   the template from `ground_truth` at runtime or build time. [REC] The concrete table in
   [M5c-C2](#m5c-c2-proposed-first-template-content), with separately authored queries and explicit
   flags. *Status:* accepted as specified in Prompt 181, including the table.
4. **C4 Analyst input.** [REC] Validated Verification values and accepted quotations only, no raw
   chunks (schema in M5c-F2). *Tradeoff:* the Analyst cannot use unvalidated context versus
   exposing unvalidated text it may not cite. *Accepted (Prompt 181);* a supported direction in Prompt 180.
5. **C5 Document metadata in the prompt.** [REC] Include title, section path, source type,
   revision number, version label, effective date and `authenticity: not_established`, with every
   string Unicode-checked and counted in the size limit. *Tradeoff:* more context for the model
   versus more untrusted strings in the request. *Accepted (Prompt 181);* a supported direction in Prompt 180.
6. **C6 Output and timeout settings.** [REC] 4,096 output tokens for both stages, timeout 60,000 ms.
   *Tradeoff:* headroom for ten claims versus cost per call. *Accepted (Prompt 181);* a supported direction in Prompt 180.
7. **C7 Version policy.** [REC] Immutable published templates and prompts; changes are new versions;
   old versions stay packaged. *Tradeoff:* a growing data directory versus irreproducible reviews.
   *Accepted (Prompt 181);* a supported direction in Prompt 180.
8. **C8 Retrieval per question.** [REC] Template queries unchanged and deterministic, `k = 8`.
   *Tradeoff:* simplicity versus recall gained by expansion (deferred to M7 measurement).
   *Accepted (Prompt 181);* a supported direction in Prompt 180.
9. **C9 Oversize requests.** [REC] Refuse before dispatch with a fixed error and no truncation; M5g
   records the question unresolved. *Tradeoff:* an unresolved question versus silently dropping
   evidence. *Accepted (Prompt 181);* a supported direction in Prompt 180.
10. **C10 Installed-wheel line.** [REC] Add one line. *Tradeoff:* a small workflow edit versus no
    installed evidence for the packaged data. *Accepted (Prompt 181);* a supported direction in Prompt 180.
11. **C11 Required documentary flag.** [REC] `requires_documentary_support` required in every
    template question. *Tradeoff:* a more verbose template versus an implicit default.
    *Accepted (Prompt 181);* a supported direction in Prompt 180.

Routine choices (key names, error codes, ordering, bounds and the JSON parameters) are specified
above and were accepted with this text in Prompt 181.

##### M5c implementation status (accepted for a local commit, Prompt 184; CI pending)

[FACT] Claude Code implemented the accepted specification in Prompt 182 on
`feat/review-request-assembly` (from `09587126`), **corrected it in Prompt 183** after external
review (Finding A: a nested `EvidenceQuestion` is now checked with exact field types at the M5c
boundary before any reconstruction could normalize it; Finding B: the Verifier prompt now states
the accepted verdict mapping, and both prompts describe the optional `repair` member and say that
provenance checks prove quote existence only), and staged it for external review. **The
corrected implementation was accepted at external review in Prompt 184 for a local
implementation commit only, pending Linux verification and current-version CI**; publication
and merge were not authorized at that point (historical: until Prompt 184 implementation
acceptance was pending). **In Prompt 185 it passed exact-commit feature and main-push CI and was
published on `main` at `e8d1033c`** (the heading's "CI pending" is historical; see the
[main publication evidence](decisions/0021-review-request-assembly.md#main-publication-evidence-prompt-185):
Claude Code observed only API conclusions; from the job logs independently retrieved by the
external reviewer and recorded in Prompt 186: Ubuntu `3429 passed, 308 skipped`, Windows
`3428 passed, 309 skipped` and PostgreSQL `308 passed, 3429 deselected` on both pushes, all four
installed-wheel logs printed eight lines including the M5c line, both container smokes reported
success (they do not exercise M5c) and Gitleaks scanned 80 commits with no leaks; the reviewer ran
no local project checks). The 308 existing integration tests passed on both pushes; M5c added no
PostgreSQL tests (historical: at the Prompt 184 acceptance none of them had run against this
version); the container smoke does not exercise M5c. No
application path, handler, endpoint, setting or production registry uses M5c, so none of its
controls operates in the application, and overall M5 acceptance is pending. See
[ADR-0021](decisions/0021-review-request-assembly.md) for the implementation, the pinned
artifacts, routine choices, the Prompt 183 corrections with their regression comparison, and
the three implementation choices approved at review in Prompt 183 (the narrowed M5b packaging
test, the bounded-read strategy with corrected wording, and the limited ground-truth separation
test).

- *Files:* `evidenceguard_agents.artifact_errors`, `templates`, `planner`, `prompts` and
  `assembly`; `data/templates/vendor_security_review_v1.toml` (SHA-256
  `26fcbe26dcc47f5991da5b741475c736cec27b1f2bd6ab515ec07ac59895786a`),
  `data/prompts/verifier/v1.md` (`629f8f972a0f5d6247a54364da59f04d53a1a023472fa00830ebedfe106b007d`)
  and `data/prompts/risk_analyst/v1.md`
  (`f8e485998dc2ff79c839100c27326a6e119135788060237a9fcbe5fed0051b29`); three new test modules;
  extended `tests/test_packaging.py`; one added installed-wheel check in
  `.github/workflows/ci.yml`; ADR-0021. No dependency, lockfile, `pyproject.toml`, existing
  contract, persistence, migration, setting, registry, Docker, Compose or corpus change. The
  prompt wording and packaged bytes are new and part of the implementation review.
- *Reviewer evidence (Prompt 184):* the external reviewer verified both exports' sizes and
  SHA-256 values, reconstructed the corrected code by applying the Prompt 183 correction to the
  extracted Prompt 182 files (the changed-file blobs matched), verified the three packaged
  artifacts' sizes and digests, and ran 38 isolated checks (the original 27 with the corrected
  pins plus 11 new ones), all passing, with Python 3.12.14, Pydantic 2.14.0 and dependencies from
  `90295717`. These were isolated checks on reconstructed copies, not the project suite, the
  submitted pytest modules, a build, an installed wheel, a database, Docker or a provider; the
  prompt checks and scripted contract paths do not establish live-model behaviour.
- *Local verification after the Prompt 183 corrections (Windows; Claude Code; historical local
  evidence, not exact-commit CI):* the regression
  comparison (submitted copies 10 failed and 8 passed, 7 failures reproducing Finding A and 3 new
  coverage; corrected 18 passed); Ruff and format clean; strict mypy no issues in 159 source
  files; the three M5c modules 251 passed; the focused twelve-file command 989 passed; full suite
  `3427 passed, 310 skipped` (308 PostgreSQL without a database, one symbolic-link and one
  POSIX-only signal test); collection 308 integration and 3,429 non-integration tests; the
  offline build compared with `09587126` (only the M5c additions, all 16 sample files
  byte-identical); the extracted installed-wheel step with the corrected pins; and a direct
  installed-wheel probe of Finding A.
- *Local verification in Prompt 182 (historical):* Ruff and format clean; strict mypy no issues in
  159 source files; the three new modules 230 passed; a focused twelve-file command 968 passed;
  full suite `3406 passed, 310 skipped` (308 PostgreSQL without a database, one symbolic-link and one
  POSIX-only signal test); collection 308 integration and 3,408 non-integration tests; the offline
  build compared with `09587126` (only the M5c additions, all 16 sample files byte-identical);
  and the extracted installed-wheel step in a fresh offline environment with the new M5c line.
- *Not established:* (Linux and current-version CI were pending at acceptance and have since
  passed for `e8d1033c`; see above.) Any review path using these values, live-model behaviour,
  injection resistance or prompt quality.

#### M5d composable capture and atomic review-creation specification (ACCEPTED at review, Prompt 188; implementation pending)

**Status.** **The complete M5d specification, including D1–D17, was accepted at external review
in Prompt 188 with a binding cleanup clarification (recorded in M5d-B1) and is the M5d
implementation contract; implementation is pending.** It was proposed by Claude Code in Prompt 185
and revised in Prompts 186 and 187 after external review (historical: in Prompts 186 and 187 the
reviewer supported directions only). At acceptance no M5d module, migration, test, ADR-0022 or
workflow change existed (historical; see the [implementation status](#m5d-implementation-status-accepted-for-a-local-commit-prompt-191-ci-pending)). Labels: **[DECISION]** already accepted (the M5
sequence with Correction A, W5, W8 and W15, the M4d capture and race rules, the accepted M5a–M5c
contracts); **[FACT]** current source at `e8d1033c`; **[REC]** Claude Code's proposal, **accepted
as specified (with the clarification) in Prompt 188**; **[OPEN]** none remains (M5d-H). M5d
adds **no** endpoint, CLI, production registry entry, handler, setting, provider, network call or
live model; creation and reload remain internal or test-only seams.

##### M5d acceptance (Prompt 188)

**Decision.** The external reviewer accepted the complete M5d specification in Prompt 188,
including D1–D17, with the binding cleanup clarification recorded in
[M5d-B1](#m5d-b1-failure-and-cleanup-precedence), which supersedes the conflicting Prompt 187
cleanup-safety rule. No M5d specification decision remains open. The acceptance covers the
specification only: composable capture with the M4d behaviour preserved; tenant-bound canonical
request identity; atomic creation of the review, snapshot facts, configuration and job; persisted
job linkage and its validation; bounded retry and the conservative `COMMIT` classification; the
schema, reload and isolated composition contracts; and the planned verification and production
isolation. Implementation, migration `0006`, tests, ADR-0022, implementation acceptance,
publication and overall M5 acceptance remain pending, and no M5d control operates.

**Binding clarification (summary).** For a retryable attempt in `not_entered` or `rejected`, an
automatic retry is allowed only when the normal `rollback()` and `close()` both returned without
any exception or process-control interruption; any ordinary failure of either permanently disables
automatic retry for that attempt, a later successful `Session.invalidate()` does not restore it,
and such an attempt ends with `ReviewConflictRetryableError` without another internal attempt.
`Session.invalidate()` reaches only connections still associated with the session's transaction,
so its normal return does not prove that the original connection was invalidated; no physical
disposal or pool quarantine is claimed.

**Reviewer evidence and scope.** The reviewer independently verified the Prompt 187 export
(`.local/p187/m5d-commit-outcome-and-cleanup-corrections.diff`, 66,122 bytes, 445 lines, SHA-256
`b8f72da5f839e8470b0137a7a51c4cf9940d21a18c863587c7280139d37290cf`, four files, 204 insertions and
82 deletions, UTF-8 and LF), inspected the corrections, checked that the published lockfile pins
SQLAlchemy 2.1.1, and inspected the relevant SQLAlchemy 2.1.1 session source
([`session.py` at `rel_2_1_1`](https://github.com/sqlalchemy/sqlalchemy/blob/rel_2_1_1/lib/sqlalchemy/orm/session.py))
and official documentation. One isolated probe ran the extracted `Session.close`,
`Session.invalidate`, `Session._close_impl` and `SessionTransaction.close` methods against simulated
session, transaction and connection resources: after an injected connection-close failure the
session had detached its transaction, `Session.invalidate` returned normally, and the original
connection's invalidation count was zero. This was extracted-library-method evidence with
simulated resources, not execution of the installed SQLAlchemy package, the project, a driver or a
database. The reviewer ran no project suite, build, installed-wheel check, PostgreSQL, Docker or
provider call.

##### M5d-A0. Accepted requirements and current-source facts

[DECISION]

- Sequence row M5d and *Composable capture and review creation (Correction A)*: extract the M4d
  capture phases (scope, selection, emptiness, revision bound, consistency, readiness, chunk
  bound, exclusions) into one public persistence function for a caller-owned `Session` and the
  transaction's database time; keep `capture_snapshot`'s signature, read-only REPEATABLE READ
  transaction, fixed errors and precedence; never reach into another module's private helper;
  rerun the M4d capture cases and add an equivalence test.
- One creation transaction: `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ WRITE` first,
  then the single `SELECT clock_timestamp()` that establishes the snapshot and becomes
  `captured_at`, then transaction-local timeouts; review, bindings, exclusions, pinned
  configuration and the `run_review` job (payload `{review_id}`, through the existing
  `enqueue(session, …)`) commit together or not at all. Known retryable conflicts get a fixed
  classification; any retry uses a fresh transaction; no unbounded retry loop; an unknown commit
  outcome never claims a rollback.
- Trusted loading: rows for `(tenant_id, review_id)` rebuilt through validating constructors, the
  canonical snapshot digest recomputed and compared; later retrievals still run the M4d binding
  recheck; no protection against direct database writers or malicious in-process code; the M4d
  limitation closes for review paths only, once M5d is implemented and verified and M5g obtains
  its snapshot solely from the loader.
- W5: a job's `max_attempts` defaults to 3; W8: no endpoint, CLI or production path calls
  creation, `run_review` is not added to `production_registry()`, and the worker claims only
  registered kinds; W15: review status is a read-time projection, so M5d stores no mutable
  status; W2 and §3: persistence must not import `evidenceguard_agents`.
- M5c: the review configuration pins the `TemplateRef`, both `PromptRef`s and the model settings;
  artifacts are loaded only through `load_pinned_template` and `load_pinned_prompt`.

[FACT]

- `capture_snapshot` runs `_capture_body` inside `run_read`, which uses
  `document_views.read_snapshot` (`SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY`,
  then `SELECT clock_timestamp()`), sets `SET LOCAL statement_timeout = 30000`, and maps semantic
  outcomes to the fixed M4d errors and **every other ordinary exception to
  `RetrievalDatabaseError` after discarding it**, so no SQLSTATE survives that boundary.
  Precedence today: actor type (`TypeError`), inputs (`InvalidRetrievalRequestError`), role
  (`PermissionDeniedError`), then the database phases.
- `RetrievalSnapshot` derives `profile_id`, `total_chunks` and `sha256` (canonical JSON with
  sorted keys, compact separators, ASCII, no NaN; `captured_at` as
  `YYYY-MM-DDTHH:MM:SS.ffffffZ` in UTC) and enforces 1–100 bindings in ascending revision order,
  one binding per document, derived index IDs, at most 100,000 chunks and disjoint exclusions;
  `PendingExclusions(count, revision_ids, truncated)` with `len(revision_ids) == min(count, 100)`.
- `jobs.enqueue` inserts with `ON CONFLICT DO NOTHING` on `uq_jobs_tenant_id_kind_idempotency_key`,
  then returns an identical existing job or raises `JobIdempotencyConflictError`, or
  `JobEnqueueRaceError` if no row is visible. `jobs` has a unique `(tenant_id, id)`;
  `max_attempts` is 1–10 (default 3).
- Persistence names constraints with `uq_%(table_name)s_%(column_0_N_name)s`,
  `fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s`,
  `ck_%(table_name)s_%(constraint_name)s` and `pk_%(table_name)s`. FK targets exist as unique keys:
  `vendors(tenant_id, id)`, `document_revisions(tenant_id, id)` and `(tenant_id, document_id, id)`,
  `embedding_indexes(tenant_id, id)` and `jobs(tenant_id, id)`. No persistence code deletes
  vendors, documents, revisions, indexes or jobs. Migrations end at `0005`.

##### M5d-A. Public contracts and placement

[REC] Files:

| File | Contents |
|---|---|
| `packages/domain/evidenceguard_domain/reviews.py` (new) | `ReviewConfiguration`, `ReviewRequest`, `CreatedReview`, `TrustedReview`, the canonical encodings, `REVIEW_JOB_KIND = "run_review"`, `REVIEW_JOB_MAX_ATTEMPTS = 3` and the fixed review errors |
| `packages/persistence/evidenceguard_persistence/database_failures.py` (new) | `DatabaseFailureCategory`, `RETRYABLE_CATEGORIES`, `classify_database_failure` (M5d-A2), `CommitFailureResolution` and `classify_commit_failure` (M5d-B1) |
| `packages/persistence/evidenceguard_persistence/retrieval.py` (changed) | public `CaptureFailure`, public `SemanticOutcome` and `capture_in_transaction`; `capture_snapshot` delegates to it without behaviour change |
| `packages/persistence/evidenceguard_persistence/reviews.py` (new) | `create_review` and `load_review` |
| `packages/persistence/evidenceguard_persistence/models.py` (changed) | the three review tables (M5d-C) |
| `packages/persistence/evidenceguard_persistence/migrations/versions/v0006_reviews.py` (new) | migration `0006` |
| `apps/worker/evidenceguard_worker/review_seams.py` (new; D2) | `ResolvedReview`, `create_review_with_artifacts`, `load_trusted_review`; internal and test-only |

**Persistence seams** (complete signatures):

- `capture_in_transaction(session: Session, captured_at: datetime, actor: ActorContext, *,
  vendor_id: UUID, identity: EmbeddingIdentity, config: RetrievalConfig = RETRIEVAL_CONFIG_V1)
  -> RetrievalSnapshot | SemanticOutcome | CaptureFailure` (M5d-A2).
- `create_review(session_factory: sessionmaker[Session], actor: ActorContext, request:
  ReviewRequest) -> CreatedReview` (M5d-B, B1, E).
- `load_review(session_factory: sessionmaker[Session], actor: ActorContext, review_id: UUID)
  -> TrustedReview` (M5d-D).

**Composition seams** (worker module, D2):

- `create_review_with_artifacts(session_factory, actor, request) -> CreatedReview`.
- `load_trusted_review(session_factory, actor, review_id) -> ResolvedReview`.

##### M5d-A1. Values and canonical identity

[REC] Every value is a frozen dataclass with a validating keyword-only constructor: exact types
(`bool` is never an `int`; tuples only), unknown keywords rejected, every nested value rebuilt
through its own constructor (`PromptRef`, `EmbeddingIdentity` through `require_storable_identity`,
`RetrievalConfig`, `RetrievalSnapshot` and the review values), `dataclasses.replace` running the
same constructor, and `repr`/`str` showing identifiers, versions, counts and digests only (never
the idempotency key). Any construction or replacement failure is a fresh
`InvalidReviewValueError` (`invalid_review_value`) with no cause or context; process control
propagates as the same object. Timestamps must be timezone-aware and are normalized to UTC with
microsecond precision (PostgreSQL `timestamptz` precision).

**Tenant scope (D10).** `ReviewRequest` is **tenant-free**. Its digest is not an argument-free
property: `request_canonical_bytes(request, *, tenant_id)` and `request_sha256(request, *,
tenant_id)` take the tenant explicitly (an exact `UUID`, else `InvalidReviewRequestError`).
`create_review` passes only `actor.tenant_id` from the validated `ActorContext`; `load_review`
selects the row with `tenant_id = actor.tenant_id`, then recomputes the digest with that stored and
equal tenant. The actor remains the only authority for tenant scope.

| Value | Fields (exact types, bounds, defaults) | Cross-field invariants | What it cannot prove |
|---|---|---|---|
| `ReviewConfiguration` | `template_id: str` (`^[a-z][a-z0-9_]{0,31}$`), `template_version: int` 1–999, `template_sha256: str` (64 lowercase hex), `verifier_prompt: PromptRef`, `analyst_prompt: PromptRef`, `model_id: str` (M5a model-ID pattern), `max_output_tokens: int` 1–8,192 (default 4,096), `timeout_ms: int` 1,000–120,000 (default 60,000), `retrieval_k: int` 1–20 (default 8). Derived `configuration_sha256` (tenant-independent) | `verifier_prompt.prompt_id != analyst_prompt.prompt_id` | that the references name registered, loadable artifacts (the composition seams check that) |
| `ReviewRequest` | `vendor_id: UUID`, `idempotency_key: str` (`^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$`), `identity: EmbeddingIdentity`, `config: RetrievalConfig` (must equal `RETRIEVAL_CONFIG_V1`), `configuration: ReviewConfiguration` | none beyond nested validity | that the vendor belongs to any tenant (capture checks scope) |
| `CreatedReview` | `review_id: UUID`, `tenant_id: UUID`, `vendor_id: UUID`, `request_sha256`, `snapshot_sha256`, `configuration_sha256` (64-hex `str`), `captured_at: datetime`, `job_id: UUID`, `replayed: bool` | aware UTC `captured_at` | that the review was committed or matches any database row |
| `TrustedReview` | `review_id: UUID`, `tenant_id: UUID`, `request: ReviewRequest`, `request_sha256: str`, `snapshot: RetrievalSnapshot`, `job_id: UUID` | `request_sha256 == request_sha256(request, tenant_id=tenant_id)`; `snapshot.tenant_id == tenant_id`; `snapshot.vendor_id == request.vendor_id`; `snapshot.identity == request.identity`; `snapshot.config == request.config` | that the values came from the database or that the database rows are authentic (only `load_review` builds it from rows) |
| `ResolvedReview` (worker) | `review: TrustedReview`, `template: ReviewTemplate`, `verifier: PromptSpec`, `verifier_system_text: str`, `analyst: PromptSpec`, `analyst_system_text: str` | `template.ref` equals the configuration's template ID, version and digest; `verifier.ref`/`analyst.ref` equal the configured `PromptRef`s with purposes `verifier`/`risk_analyst`; each system text's SHA-256 equals its reference digest | that the artifacts came from the pinned loaders (only `load_trusted_review` builds it) |

**Canonical encodings.** Both use the existing retrieval canonical form: a JSON object serialized
with `json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
allow_nan=False)`, encoded as ASCII; the digest is the lowercase hex SHA-256 of those bytes. UUIDs
are canonical lowercase hyphenated strings; integers are JSON numbers; no float, timestamp,
generated ID or snapshot field appears.

`eg-review-configuration-v1` (`configuration_sha256`):

```text
{"analyst_prompt":{"id":<str>,"sha256":<hex>,"version":<int>},
 "canonical":"eg-review-configuration-v1",
 "kind":"review_configuration",
 "model":{"max_output_tokens":<int>,"model_id":<str>,"timeout_ms":<int>},
 "retrieval_k":<int>,
 "template":{"id":<str>,"sha256":<hex>,"version":<int>},
 "verifier_prompt":{"id":<str>,"sha256":<hex>,"version":<int>}}
```

`eg-review-request-v1` (`request_sha256`, with the explicit tenant):

```text
{"canonical":"eg-review-request-v1",
 "configuration_sha256":<hex>,
 "embedding_profile":{"algorithm_version":<str>,"dims":<int>,"fingerprint":<hex>,
                      "model_id":<str>,"normalization":<str>,"provider_id":<str>},
 "idempotency_key":<str>,
 "kind":"review_request",
 "retrieval_config":{"config_sha256":<hex>,"version":<str>},
 "tenant_id":<uuid>,
 "vendor_id":<uuid>}
```

(The line breaks above are for reading; the encoding has none.) Logical request identity is
therefore the tenant, vendor, key, embedding profile, retrieval configuration and the complete
pinned configuration including the timeout and `retrieval_k`; it never includes `captured_at`,
the snapshot, the review ID or the job ID.

##### M5d-A2. Capture contract and failure classification

[REC] (D1 as corrected, D12; revised in Prompt 187.)

- **`SemanticOutcome`** (made public, unchanged values): a frozen value whose `code` is one of the
  M4d codes `retrieval_scope`, `snapshot_empty`, `snapshot_bounds_exceeded`, `snapshot_not_ready`
  and `snapshot_inconsistent`; the existing module constants are its only instances in use.
- **`CaptureFailure`** (new public frozen value): `category: DatabaseFailureCategory`; nothing
  else (no exception, message, SQL, parameter or chain).
- **`DatabaseFailureCategory`** (`StrEnum`, body phase): `serialization_failure` (SQLSTATE
  `40001`), `deadlock_detected` (`40P01`), `lock_not_available` (`55P03`), `query_canceled`
  (`57014`, including statement timeout), `review_key_unique_violation` (`23505` **and** the
  reported constraint name exactly `uq_reviews_tenant_id_idempotency_key`), `other`.
  `RETRYABLE_CATEGORIES` = `serialization_failure`, `deadlock_detected`, `lock_not_available` and
  `review_key_unique_violation`. These categories apply only to failures **before** `COMMIT`;
  `COMMIT` failures use the narrower `CommitFailureResolution` (M5d-B1).
- **`classify_database_failure(error: object) -> DatabaseFailureCategory`.** *Supported input:* an
  ordinary exception the seam has just caught. *Behaviour:* if `error` is not an instance of
  SQLAlchemy's `DBAPIError`, the result is `other`. Otherwise it reads, inside one guard that
  catches only `Exception`, `error.orig`, then that object's `sqlstate`, and, only when the state is
  `23505`, `error.orig.diag.constraint_name`. A value is recognized only if it is exactly a `str`
  equal to an allowlisted SQLSTATE (or, for the constraint, exactly
  `uq_reviews_tenant_id_idempotency_key`); a missing, `None`, non-`str`, unknown or raising
  attribute gives `other` (or, for an unrecognized constraint, `other`). It never reads messages,
  `str()`/`repr()` of the error, SQL, parameters, `__cause__`, `__context__` or tracebacks, never
  raises an ordinary exception, and returns only an enum member, keeping no reference to the error.
  Process control raised while reading an attribute propagates as the same object. This is a
  bounded classification of supported driver errors, not a sandbox against malicious trusted
  in-process code (an attribute can run arbitrary code).
- **`capture_in_transaction` precedence** (preserving `capture_snapshot`): actor type (the
  existing `TypeError`), inputs (`InvalidRetrievalRequestError`, now also for a naive or
  non-`datetime` `captured_at`), role (`PermissionDeniedError`). After that validation, the **whole
  remaining operation** (every `execute`, fetch, row iteration, row attribute access, result
  processing and domain-value construction) runs inside one guard: the M4d phases return their
  explicitly recognized results as `SemanticOutcome` exactly as today (including
  `snapshot_inconsistent` for a domain constructor's `RetrievalError` in the existing `_build`
  path) or the built `RetrievalSnapshot`; any **other** ordinary `Exception` is classified inside
  the handler and returned as `CaptureFailure(category)` after leaving it (`other` when
  unrecognized). No raw exception crosses the public result boundary. Process control propagates
  as the same object. The function never commits, rolls back, closes the session, sets isolation or
  sets a timeout.
- **`capture_snapshot` unchanged.** Inside `run_read`, its body sets the statement timeout, calls
  `capture_in_transaction`, returns a snapshot or `SemanticOutcome` unchanged, and for a
  `CaptureFailure` raises a private marker that `run_read` records as operational, so the caller
  still receives `RetrievalDatabaseError` with the same signature, mapping and precedence as today
  (today any non-semantic body exception already becomes `RetrievalDatabaseError`).
- **Trusted caller preconditions** (documented; the function cannot verify them): the session has
  an active transaction at REPEATABLE READ whose snapshot was established by the statement that
  returned `captured_at`; the caller has not written rows that affect eligibility (vendors,
  documents, revisions, chunk sets, profiles or indexes) earlier in that transaction; and the
  caller ends the transaction itself. `captured_at` is not proof that the caller followed these
  rules. Both the read-only `capture_snapshot` path and the read-write creation path satisfy them.

##### M5d-B. Transaction and eligibility

[REC] `create_review` checks, in order: actor type (`InvalidReviewRequestError`), request type
and reconstruction (`InvalidReviewRequestError`), role reviewer or approver
(`PermissionDeniedError`); then it runs at most three attempts (D4). Each attempt uses one fresh
session and transaction, in this statement order:

1. `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ WRITE` (first statement).
2. `SELECT clock_timestamp()`; its value is `captured_at`.
3. `SET LOCAL statement_timeout = 30000` and `SET LOCAL lock_timeout = 5000` (D6).
4. Replay lookup: `SELECT` the review by `(actor.tenant_id, idempotency_key)`. If visible: a
   matching `request_sha256` returns the stored review with `replayed=True` and its stored
   `run_review_job_id` after validating the job association (M5d-D step 4); a different digest
   raises `ReviewIdempotencyConflictError`. Either way nothing is written.
5. `capture_in_transaction(session, captured_at, actor, vendor_id=…, identity=…, config=…)`.
6. Generate `review_id = uuid4()` (D3); check that no `run_review` job with key `str(review_id)`
   is visible for the tenant (if one is, the attempt fails with `ReviewJobConflictError`); then
   `enqueue(session, actor, kind="run_review", idempotency_key=str(review_id),
   payload=JobPayload.from_mapping({"review_id": str(review_id)}),
   max_attempts=REVIEW_JOB_MAX_ATTEMPTS)` and require the returned job to have exactly that
   tenant, kind, key, payload and `max_attempts`, status `queued` and `attempt` 0 (else
   `ReviewJobConflictError`); `JobIdempotencyConflictError` and `JobEnqueueRaceError` are also
   `ReviewJobConflictError`.
7. `INSERT` the review row with `run_review_job_id` = that job's ID (a plain insert; no
   `ON CONFLICT`), then one `review_bindings` row per binding (ordinal = position) and one
   `review_excluded_revisions` row per listed excluded revision.
8. `COMMIT`.

**Visibility and time.** The snapshot is the MVCC snapshot that PostgreSQL establishes for the
transaction's first data statement (the `SELECT` in step 2), as documented for REPEATABLE READ
([transaction isolation](https://www.postgresql.org/docs/17/transaction-iso.html)): changes
committed before that snapshot was taken are visible, and later commits are not. `captured_at` is
the `clock_timestamp()` value that statement returned
([date/time functions](https://www.postgresql.org/docs/17/functions-datetime.html)); it is a
recorded clock reading, **not** an ordering proof: a transaction whose commit's wall-clock time
precedes the returned `captured_at` (for example one committing while the statement runs) need not
be visible. M5d keeps the M4d race tests (changes committed before the creation transaction's
first statement are captured; changes committed after `captured_at` was returned are not) and
adds no wall-clock ordering or historical-authorization claim. A captured revision stays bound
after later supersession.

*Clarification (Prompt 193, after the failed feature CI at `1bea3731`):* snapshot visibility is
fixed within each attempt; only the successfully committed attempt's snapshot is persisted, and a
rolled-back attempt's `captured_at` and bindings are not promised to survive a fresh-transaction
retry (for example, a concurrent supersession can make an attempt's `review_bindings` insert fail
with `40001`, and the fresh attempt then sees the replacement). Once a review has committed, later
activation does not change its stored bindings. The retry and transaction rules above are
unchanged ([ADR-0022](decisions/0022-review-creation.md#exact-commit-ci-at-1bea3731-and-postgresql-test-corrections-prompts-192193)).

No capture or enqueue helper commits, rolls back or closes the session; `create_review` alone
ends each transaction. Nothing about the review is visible to other transactions until commit,
and the review, bindings, exclusions, pinned configuration and job commit together or not at all.
Per-statement and lock timeouts bound individual waits only; there is **no** end-to-end deadline.

##### M5d-B1. Failure and cleanup precedence

[DECISION, accepted in Prompt 188 with the binding cleanup clarification] (D13, D15, D16, D17;
revised in Prompt 187.) Each attempt tracks its **commit state**
independently of whatever exception is currently being handled:

| Commit state | Meaning |
|---|---|
| `not_entered` | `COMMIT` was never sent (setup, replay, body or semantic outcome) |
| `entered` | `Session.commit()` was called and has neither returned nor raised a recognized rejection; the outcome is **unknown** |
| `rejected` | `Session.commit()` raised and `classify_commit_failure` returned `rejected_retryable` |
| `committed` | `Session.commit()` returned normally (acknowledged) |

**Commit classification (D15).** A SQLSTATE on a `COMMIT` failure does not by itself prove that
the transaction did not commit: PostgreSQL defines `08007` (`transaction_resolution_unknown`) and
`40003` (`statement_completion_unknown`)
([error codes](https://www.postgresql.org/docs/17/errcodes-appendix.html)), and serialization
failures can be reported at commit
([transaction isolation](https://www.postgresql.org/docs/17/transaction-iso.html)). The proposed
conservative policy:

- `CommitFailureResolution` (`StrEnum`): `rejected_retryable`, `unknown`.
- `classify_commit_failure(error: object) -> CommitFailureResolution`: `rejected_retryable` only if
  `error` is a SQLAlchemy `DBAPIError` whose `orig.sqlstate`, read inside the same guard as
  `classify_database_failure`, is exactly the `str` `"40001"` or `"40P01"`; **every** other case is
  `unknown`, including a missing, `None`, non-`str` or raising diagnostic, `08007`, `40003`, `23505`
  (even on the review-key constraint) and every other SQLSTATE. It never reads messages, SQL,
  parameters or exception chains, returns only an enum member and keeps no reference; process
  control raised during diagnostic access propagates as the same object.
- An acknowledged commit is committed and is never retried; an `unknown` outcome raises
  `ReviewCommitOutcomeUnknownError` and is never retried automatically; a later call with the same
  tenant and idempotency key may discover whether creation happened (a matching replay returns
  it). No later rollback, successful cleanup or connection disposal retrospectively proves that an
  unknown `COMMIT` failed.
- The body-phase categories stay separate: a body-phase `23505` on
  `uq_reviews_tenant_id_idempotency_key` is retryable, a `COMMIT`-phase one is `unknown`.

**Attempt result** (decided before cleanup and never changed by it; the first applicable row):

| Situation | Commit state | Result | Retry |
|---|---|---|---|
| Matching replay or `ReviewIdempotencyConflictError` | `not_entered` | the replay value or that error | no |
| Semantic capture outcome | `not_entered` | its fixed M4d error | no |
| Ordinary body failure in `RETRYABLE_CATEGORIES` | `not_entered` | retryable | next attempt only if the normal `rollback()` and `close()` both returned (below); after the third attempt, or if either failed, `ReviewConflictRetryableError` |
| Other ordinary body failure (`ReviewJobConflictError`, `query_canceled`, `other`) | `not_entered` | that error or `ReviewDatabaseError` | no |
| `COMMIT` raised, `rejected_retryable` | `rejected` | retryable | as for a retryable body failure |
| `COMMIT` raised, `unknown` | `entered` | `ReviewCommitOutcomeUnknownError` | never automatically |
| `COMMIT` acknowledged | `committed` | the `CreatedReview` | never |

**Cleanup** (binding clarification accepted in Prompt 188, superseding the Prompt 187
cleanup-safety rule). Each call below is made at most once per attempt; these are best-effort
cleanup calls, not proof that the original connection was physically discarded, and no time bound
is claimed for them:

| Commit state | Normal cleanup sequence | Fallback |
|---|---|---|
| `not_entered` or `rejected` | `Session.rollback()` once; only if it returned normally, `Session.close()` once | if `rollback()` raises, skip `close()` and call [`Session.invalidate()`](https://docs.sqlalchemy.org/en/21/orm/session_api.html#sqlalchemy.orm.Session.invalidate) once; if `close()` raises, call `Session.invalidate()` once |
| `entered` (unknown) | `Session.invalidate()` once; **no** rollback | none |
| `committed` | `Session.close()` once | if `close()` raises, call `Session.invalidate()` once |

**Retry eligibility after cleanup** (for an attempt in `not_entered` or `rejected` whose classified
failure is retryable):

- an automatic retry is allowed **only** when the normal `rollback()` and `close()` calls both
  returned without any exception or process-control interruption;
- any ordinary `rollback()` or `close()` failure permanently disables automatic retry for that
  attempt, and a later successful `invalidate()` does **not** restore it; such an otherwise
  retryable attempt ends with `ReviewConflictRetryableError` and no further internal attempt;
- an already non-retryable result (replay, idempotency conflict, semantic outcome, job conflict,
  `ReviewDatabaseError`) keeps its own fixed result whatever cleanup does.

Further rules:

- **Unknown outcome:** after `entered`, `invalidate()` is attempted once; whatever it does, the
  result stays `ReviewCommitOutcomeUnknownError` and is never retried automatically.
- **Committed:** after an acknowledged commit the result stays the `CreatedReview` and is never
  retried, even if both `close()` and the fallback `invalidate()` fail.
- Cleanup never changes the attempt result or commit state; M5d does **not** claim that a rollback
  succeeded when `rollback()` raised.
- **Limitation.** `Session.invalidate()` reaches only connections still associated with the
  session's transaction, and `rollback()` or `close()` may already have detached that transaction
  before raising. A normal return from the fallback `invalidate()` therefore does **not** prove that
  the original connection was invalidated; M5d claims neither guaranteed physical disposal nor
  pool quarantine, and introduces no private SQLAlchemy state inspection or new
  connection-ownership mechanism. (Reviewer evidence, Prompt 188: an isolated probe of the
  extracted SQLAlchemy 2.1.1 `Session.close`, `Session.invalidate`, `Session._close_impl` and
  `SessionTransaction.close` methods with simulated resources showed that after an injected
  connection-close failure the transaction was detached and `invalidate()` returned without
  invalidating the original connection.)
- Ordinary cleanup exceptions are suppressed (never raised, logged or chained); the fixed result is
  raised or returned after leaving every handler, with no cause or context.

**Process control** (`BaseException` that is not `Exception`):

- The **first** process-control object observed in an attempt (during setup, body, `COMMIT` or
  cleanup) is primary: after bounded best-effort cleanup for the current commit state it is
  re-raised as the same object, never translated, and no further attempt runs.
- A later ordinary failure or a later process-control object during that cleanup is suppressed and
  never replaces the first.
- An interrupt during `rollback()` or `close()` may trigger the one best-effort `invalidate()`
  attempt, but never an automatic retry.
- If process control arrives during `COMMIT` before acknowledgement or a recognized rejection, the
  commit state stays `entered` (unknown); after acknowledgement it stays `committed` (the
  transaction did commit, but the `CreatedReview` is not returned because process control takes
  precedence; a replay with the same key returns it).

Retry eligibility (a property of the classified failure) and commit state (a property of the
transaction) are separate; only `not_entered` or `rejected` attempts with a retryable
classification whose normal `rollback()` and `close()` both returned are retried, at most three
attempts in total. Per-statement and
lock timeouts bound individual waits only; there is no end-to-end deadline. Nothing logs.

##### M5d-C. Persistence and migration 0006

[REC] Migration `0006` mirrors the models; constraint text is spelled out; plain DDL so offline
`--sql` rendering needs no database; downgrade drops exactly these three tables in reverse order.
All foreign keys use the default `NO ACTION` (no cascades). PostgreSQL `timestamptz` stores
microseconds, matching the canonical timestamp.

**`reviews`**

| Column | SQL type | Null | Check (`ck_reviews_<name>`) |
|---|---|---|---|
| `id` | `uuid` | no | primary key `pk_reviews` |
| `tenant_id` | `uuid` | no | FK `fk_reviews_tenant_id_tenants` → `tenants(id)` |
| `vendor_id` | `uuid` | no | FK `fk_reviews_tenant_id_vendor_id_vendors` (`tenant_id`, `vendor_id`) → `vendors(tenant_id, id)` |
| `idempotency_key` | `varchar(128)` | no | `idempotency_key`: `idempotency_key ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'` |
| `request_sha256`, `configuration_sha256`, `snapshot_sha256` | `varchar(64)` | no | `<column>`: `<column> ~ '^[0-9a-f]{64}$'` |
| `captured_at` | `timestamptz` | no | — |
| `provider_id`, `embedding_model_id`, `algorithm_version` | `varchar(64)` | no | `<column> ~ '^[a-z][a-z0-9._-]{0,63}$'` |
| `dims` | `integer` | no | `dims`: `dims BETWEEN 1 AND 4096` |
| `normalization` | `varchar(16)` | no | `normalization`: `normalization = 'l2'` |
| `fingerprint` | `varchar(64)` | no | `fingerprint ~ '^[0-9a-f]{64}$'` |
| `profile_id` | `uuid` | no | — (recomputed on reload) |
| `retrieval_config_version` | `varchar(64)` | no | `retrieval_config_version`: `char_length(retrieval_config_version) BETWEEN 1 AND 64` |
| `retrieval_config_sha256` | `varchar(64)` | no | hex check |
| `exclusion_count` | `integer` | no | `exclusion_count`: `exclusion_count >= 0` |
| `exclusions_truncated` | `boolean` | no | `exclusions_truncated`: `exclusions_truncated = (exclusion_count > 100)` |
| `template_id` | `varchar(32)` | no | `template_id ~ '^[a-z][a-z0-9_]{0,31}$'` |
| `template_version`, `verifier_prompt_version`, `analyst_prompt_version` | `integer` | no | `<column> BETWEEN 1 AND 999` |
| `template_sha256`, `verifier_prompt_sha256`, `analyst_prompt_sha256` | `varchar(64)` | no | hex checks |
| `verifier_prompt_id`, `analyst_prompt_id` | `varchar(32)` | no | `<column> ~ '^[a-z][a-z0-9_]{0,31}$'`; `distinct_prompts`: `verifier_prompt_id <> analyst_prompt_id` |
| `model_id` | `varchar(64)` | no | `model_id ~ '^[a-z0-9][a-z0-9.-]{0,63}$'` |
| `max_output_tokens` | `integer` | no | `BETWEEN 1 AND 8192` |
| `timeout_ms` | `integer` | no | `BETWEEN 1000 AND 120000` |
| `retrieval_k` | `integer` | no | `BETWEEN 1 AND 20` |
| `run_review_job_id` | `uuid` | no | FK `fk_reviews_tenant_id_run_review_job_id_jobs` (`tenant_id`, `run_review_job_id`) → `jobs(tenant_id, id)` |
| `created_at` | `timestamptz` | no | default `now()` |

Unique constraints: `uq_reviews_tenant_id_id` (`tenant_id`, `id`; FK target),
`uq_reviews_tenant_id_idempotency_key` (`tenant_id`, `idempotency_key`; the only constraint the
retry classifier recognizes) and `uq_reviews_tenant_id_run_review_job_id` (`tenant_id`,
`run_review_job_id`). No status, lease, credential, provider key, prompt text, template text or
document text column exists.

**`review_bindings`**: `tenant_id uuid`, `review_id uuid`, `ordinal smallint` (check
`ordinal BETWEEN 0 AND 99`), `revision_id uuid`, `document_id uuid`, `index_id uuid`,
`chunker_version varchar(32)` (check `^[a-z0-9][a-z0-9.-]{0,31}$`), `chunk_count integer` (check
`BETWEEN 1 AND 4096`), `manifest_sha256 varchar(64)` and `vector_manifest_sha256 varchar(64)`
(hex checks), all `NOT NULL`. Primary key `pk_review_bindings` (`review_id`, `revision_id`);
unique `uq_review_bindings_review_id_ordinal` and `uq_review_bindings_review_id_document_id`; FKs
`(tenant_id, review_id)` → `reviews(tenant_id, id)`, `(tenant_id, document_id, revision_id)` →
`document_revisions(tenant_id, document_id, id)` and `(tenant_id, index_id)` →
`embedding_indexes(tenant_id, id)` (D5).

**`review_excluded_revisions`**: `tenant_id uuid`, `review_id uuid`, `revision_id uuid`, all
`NOT NULL`; primary key (`review_id`, `revision_id`); FKs `(tenant_id, review_id)` → `reviews` and
`(tenant_id, revision_id)` → `document_revisions(tenant_id, id)`.

**Captured facts versus current state.** Every stored binding and exclusion is an immutable copy
of what the creation transaction saw. Reload never consults a revision's current status, active
pointer, chunk set or index state, so a revision superseded later stays bound and one activated
later never joins. Retrieval over the reloaded snapshot still runs the M4d binding recheck
against current rows (which uses `activated_at`, not `status`).

##### M5d-C1. Enforced constraints versus reload checks

| Rule | Enforced by PostgreSQL | Checked on reload or by constructors |
|---|---|---|
| tenant ownership of vendor, revisions, documents, indexes and job | composite FKs | also implied by the tenant-filtered selects |
| one key per tenant; one job per review | unique constraints | replay and job association checks |
| single-column formats and ranges | `CHECK`s above | the value constructors (again) |
| 1–100 bindings, ascending revision order, ordinals 0…n−1 with no gap, one binding per document, derived index IDs, ≤ 100,000 chunks | only uniqueness of ordinal, document and revision | `RetrievalSnapshot` and the ordinal check |
| excluded revisions belong to the vendor, ≤ 100 rows, row count = `min(exclusion_count, 100)`, disjoint from bindings | none | `PendingExclusions` and `RetrievalSnapshot` |
| binding revision belongs to the vendor | none (FK only to tenant and document) | `RetrievalSnapshot` digest and later M4d binding recheck |
| stored digests match the stored facts | none | recomputation and exact comparison |
| job payload, kind, key and `max_attempts` match the review | none | job association check |

##### M5d-D. Trusted reload

[REC] `load_review` checks actor type and `review_id` type (`InvalidReviewRequestError`) and role
(`PermissionDeniedError`), then runs one transaction through the public `read_snapshot` helper
(REPEATABLE READ, READ ONLY, then `SELECT clock_timestamp()`, which is unused) with its **own**
failure boundary (it does not reuse `run_read`, whose mapping is specific to M4d):

1. select the review by `(actor.tenant_id, review_id)`; none → `ReviewNotFoundError` (also for
   another tenant's ID);
2. select its bindings ordered by `ordinal` and its excluded revisions ordered by `revision_id`;
3. rebuild `EmbeddingIdentity`, the retrieval configuration (version and digest must identify
   `RETRIEVAL_CONFIG_V1`), `ReviewConfiguration`, `ReviewRequest`, every `RevisionBinding`,
   `PendingExclusions` and `RetrievalSnapshot` (with the stored `captured_at`), and require the
   recomputed `snapshot.sha256`, `profile_id`, `configuration_sha256` and
   `request_sha256(request, tenant_id=<stored tenant>)` to equal the stored values;
4. **job association:** select the job by `(tenant_id, run_review_job_id)` and require kind
   `run_review`, idempotency key `str(review_id)`, payload exactly `{"review_id": "<review_id>"}`
   and `max_attempts == 3`; the job's status, attempt, lease and error fields may be anything (its
   lifecycle continues independently). A missing row (possible only through direct tampering,
   given the FK) or any mismatch is `ReviewRecordInconsistentError`;
5. return `TrustedReview(review_id, tenant_id, request, request_sha256, snapshot, job_id)`.

Errors: reconstruction or comparison failures are `ReviewRecordInconsistentError`; other ordinary
failures (including those of the helper's own statements and cleanup) are `ReviewDatabaseError`;
process control propagates as the same object. **Creation, replay and reload return the same job
ID**: creation from `enqueue`, replay and reload from the stored `run_review_job_id`, each with
the association validated.

`load_trusted_review` checks the same inputs and role, calls `load_review`, then loads the
template and both prompts through `load_pinned_template` and `load_pinned_prompt` (purposes
`verifier` and `risk_analyst`); `UnknownTemplateError`, `TemplateIntegrityError`,
`UnknownPromptError` and `PromptIntegrityError` become `ReviewArtifactsUnavailableError`; it
returns `ResolvedReview`.

**Boundary.** Stored rows are trusted because the application wrote them in the transaction that
established eligibility, not because digests exist; the digests only detect disagreement between
stored rows. There is no protection against direct database writes, data-altering migrations or
malicious trusted in-process code. The M4d trusted-snapshot limitation closes **for review paths
only**, once M5d is implemented and verified and M5g obtains its snapshot solely from
`load_trusted_review`.

##### M5d-E. Idempotency, concurrency and failures

[REC]

- **Logical identity** is `(tenant_id, idempotency_key)` with `request_sha256` (M5d-A1). A replay
  after documents changed returns the **original** review, snapshot and job.
- **Matching replay** writes nothing and returns `replayed=True` with the stored job ID;
  **conflicting replay** raises `ReviewIdempotencyConflictError` and writes nothing.
- **Concurrent creation** with one key: both attempts may capture; the later review insert waits
  on `uq_reviews_tenant_id_idempotency_key` and fails with `23505` on that constraint (or a
  serialization failure) once the first commits; that attempt is not committed and is retried in a
  fresh transaction, which sees the committed review and returns the matching replay (or the
  conflict error).
- **Retry policy (D4, D15, D17):** at most three attempts in total, no sleep; a not-committed
  attempt is retried only for a body-phase failure in `RETRYABLE_CATEGORIES` or a `COMMIT`
  rejection classified `rejected_retryable` (exactly `40001` or `40P01`), and only when its normal
  `rollback()` and `close()` both returned (M5d-B1). Such an already classified retryable failure
  ends with `ReviewConflictRetryableError` when either of those cleanup calls failed or the third
  attempt is reached; semantic, idempotency, job-conflict and other non-retryable errors keep their
  own fixed results. An unknown commit outcome or an acknowledged commit is never retried.
- **Job conflicts:** a visible `run_review` job with the new review's key, an enqueue idempotency
  conflict or race, or a returned job that is not the expected new queued job is
  `ReviewJobConflictError` (not retryable); a random review ID makes this unlikely but not
  logically impossible, so it has a defined refusal path.
- **Job attempts versus call budget:** `REVIEW_JOB_MAX_ATTEMPTS = 3` (W5) limits how often the
  worker may run the `run_review` job; it is unrelated to M5g's persisted provider-call
  reservations (3 per stage, W4).

**Errors** (in `evidenceguard_domain.reviews`; fixed codes; nothing logs; the key and document text
never appear):

| Error (code) | Raised for | Retryable |
|---|---|---|
| `InvalidReviewRequestError` (`invalid_review_request`) | invalid seam arguments (actor type, request, review ID, tenant parameter) | no |
| `InvalidReviewValueError` (`invalid_review_value`) | invalid value construction or replacement | no |
| `PermissionDeniedError` (existing) | a role other than reviewer or approver | no |
| existing M4d capture errors (`retrieval_scope`, `snapshot_empty`, `snapshot_bounds_exceeded`, `snapshot_not_ready`, `snapshot_inconsistent`) | semantic capture outcomes during creation | no |
| `ReviewIdempotencyConflictError` (`review_idempotency_conflict`) | the key exists for the tenant with a different request digest | no |
| `ReviewJobConflictError` (`review_job_conflict`) | the job refusal paths above | no |
| `ReviewConflictRetryableError` (`review_conflict_retryable`) | an already classified retryable failure (a body-phase retryable category or a `rejected_retryable` `COMMIT`) after three attempts, or when its normal `rollback()` or `close()` failed | by a later fresh call |
| `ReviewCommitOutcomeUnknownError` (`review_commit_outcome_unknown`) | any ordinary `COMMIT` failure not classified `rejected_retryable` (including `08007`, `40003`, `23505` and missing, unreadable or unrecognized diagnostics); the transaction may or may not have committed | never automatically |
| `ReviewDatabaseError` (`review_database_error`) | other database or session failures, including `57014` | no |
| `ReviewNotFoundError` (`review_not_found`) | no review with that ID for the actor's tenant | no |
| `ReviewRecordInconsistentError` (`review_record_inconsistent`) | stored rows or job association that fail reconstruction or comparison | no |
| `ReviewArtifactsUnavailableError` (`review_artifacts_unavailable`) | a pinned template or prompt that is unknown or fails its integrity check | no |

**Composition precedence.** `create_review_with_artifacts`: actor type and request
(`InvalidReviewRequestError`), role (`PermissionDeniedError`), artifacts (load the template and
both prompts; `ReviewArtifactsUnavailableError`) before any database work, then `create_review`.
`load_trusted_review`: inputs, role, `load_review`'s errors, then artifacts.

##### M5d-F. Production isolation

[DECISION, restated] Creation and reload are internal or test-only seams: no endpoint, CLI, API
route, `eg-admin` command or worker runtime path imports them; `run_review` is **not** added to
`production_registry()`, and the worker's registered-kind claim filter is unchanged, so a
production worker never claims a `run_review` job created by a test. M5d creates no handler and
no fake judgment; enqueue from a production path, handler registration and a configured provider
remain one later reviewed wiring decision.

##### M5d-G. Verification plan (planned, not written or run)

*Database-independent* (`tests/test_review_values.py`, `tests/test_review_creation.py`,
`tests/test_database_failures.py`):

- every value bound, default and cross-field rule; replacement and bypass revalidation;
  representations without the key; `TrustedReview` and `ResolvedReview` consistency failures;
- canonical bytes of both encodings pinned as hand-written literals and their SHA-256 values
  computed independently; the same request under two tenants gives two digests; no
  argument-free request digest exists; missing or non-`UUID` tenant parameter refused;
- `classify_database_failure` for each allowlisted SQLSTATE, `23505` with the exact and with
  another constraint name, missing SQLSTATE, `None`, a non-`str` SQLSTATE, a raising `orig`,
  `sqlstate`, `diag` or `constraint_name` attribute (`other`), non-`DBAPIError` and non-exception
  inputs (`other`), and process control raised from a diagnostic attribute (same object); no
  message, `str`, `repr`, chain or traceback read (fakes whose `__str__`, `__repr__`, message and
  `args` raise when touched);
- `classify_commit_failure`: `rejected_retryable` for exactly `40001` and `40P01`; `unknown` for
  `08007`, `40003`, `23505` (also on the review-key constraint), `55P03`, `57014`, other states,
  missing, malformed or raising diagnostics and non-`DBAPIError` inputs; process control from
  diagnostic access propagates as the same object;
- `capture_in_transaction` with a recording session: never commits, rolls back, closes or sets
  isolation or a timeout; returns `CaptureFailure` for ordinary failures raised by `execute`, by
  fetching, by row iteration, by row attribute access and by other result processing, with no
  exception retained and `other` for unrecognized ones; recognized semantic inconsistencies
  (including a domain constructor's `RetrievalError`) still return `SemanticOutcome`;
  process-control identity from each of those points; `capture_snapshot`'s signature, precedence
  and `RetrievalDatabaseError` mapping unchanged;
- `create_review` and `load_review` input, role and composition precedence;
- the commit-state and cleanup tables, row by row, with fake sessions recording every call:
  replay, semantic, retryable and non-retryable body failures; `COMMIT` raising `40001`, `40P01`
  (retried in a new session), `08007`, `40003`, `23505` and a diagnostic-free error
  (`ReviewCommitOutcomeUnknownError`, no retry, `invalidate()` called and no rollback attempted);
  an acknowledged commit followed by a `close()` failure and by both `close()` and `invalidate()`
  failures (the `CreatedReview` returned, no further attempt); `rollback()` failing with a
  normally returning `invalidate()` and `close()` not called (no automatic retry,
  `ReviewConflictRetryableError`); `close()` failing with a normally returning `invalidate()`
  (no automatic retry); both normal cleanup calls returning (retry still permitted for a retryable
  failure); a simulated detached-transaction resource on which the fallback `invalidate()` returns
  without touching the original connection (the result and retry decision are unchanged and no
  disposal is claimed); each of `rollback`, `close` and `invalidate` called at most once per
  attempt; an interrupt during `rollback()` or `close()` (one `invalidate()` attempt, same object
  raised, no retry); process control during setup, body, `COMMIT` (state stays unknown) and after
  acknowledgement (state committed, same object raised, no retry, a later replay returns the
  review); a second process-control object and ordinary failures during cleanup never replacing
  the first; at most three attempts; fresh errors without cause, context, key or text; no logs;
- packaging: import boundaries, persistence still not importing agents, the production registry
  without `run_review`, no route or command importing the seams, and the narrowed agents-import
  exception for exactly `review_seams.py` (D2).

*PostgreSQL* (`tests/test_reviews_postgres.py`, integration; the existing capture tests in
`tests/test_retrieval_postgres.py` rerun unchanged):

- equivalence of `capture_snapshot` and `capture_in_transaction` over the same data;
- atomicity: success writes the review, every binding, the exclusions and exactly one queued
  `run_review` job with `max_attempts = 3` and the review's payload; each semantic outcome, an
  injected failure after the job insert and after the review insert leave no row and no job;
- MVCC races (two connections and a barrier, as in M4d): a change committed before the creation
  transaction's first statement is captured; one committed after `captured_at` was returned is
  not; a captured revision stays bound after supersession;
- persisted facts equal the captured snapshot; reload rebuilds the same snapshot, digests and job
  ID; tampered binding, ordinal, exclusion, identity, configuration, digest or job rows (payload,
  kind, key, `max_attempts`) give `ReviewRecordInconsistentError`; a job whose status changed to
  `running`, `succeeded` or `dead` still reloads; another tenant's ID gives `ReviewNotFoundError`;
- idempotency: matching replay returns the same review and job ID and writes nothing; conflicting
  replay is refused; concurrent same-key creation yields one review and one job and the other call
  returns the replay; a pre-existing `run_review` job with the generated key (inserted by the
  test with a fixed ID) gives `ReviewJobConflictError`;
- deterministic lock-timeout and serialization cases where feasible, and the three-attempt bound;
- an unknown commit outcome (simulated by a test hook that raises after the server acknowledged
  `COMMIT`) followed by a replay with the same key that returns the committed review;
- the production worker registry does not claim a `run_review` job;
- `alembic upgrade`, `downgrade`, `check` and offline SQL rendering for `0006`, and that every
  named constraint exists with its exact name.

*Wheel* (D8): assert that the offline migration SQL includes `CREATE TABLE reviews`. No new
dependency.

##### M5d-H. Scope, files and reviewer decisions

*Files:* the seven in M5d-A; `tests/test_review_values.py`, `tests/test_review_creation.py`,
`tests/test_database_failures.py`, `tests/test_reviews_postgres.py`; changes to
`tests/test_packaging.py`, `tests/test_retrieval_postgres.py` (equivalence) and, with D8,
`.github/workflows/ci.yml`; ADR-0022 with the implementation; README, plan and threat-model status.
*Excluded:* M5e stage, call-reservation and output records; M5f report representation; M5g
orchestration and handler; M5h transport; any endpoint, CLI, production registration, provider,
live call, corpus, dependency or lockfile change.

**Review status (Prompt 188): D1–D17 are accepted**, D17 expressly subject to the clarified
conservative cleanup policy in M5d-B1; no specification decision remains open. *Historical:* in
Prompt 186 the reviewer supported D1–D9 as directions and in Prompt 187 D10, D11, D13 and D14;
D12 was open and D15–D17 were proposed until Prompt 188.

1. **D1 Public composable capture** (*accepted, Prompt 188*). [REC]
   `capture_in_transaction` returning `RetrievalSnapshot | SemanticOutcome | CaptureFailure`, with
   `SemanticOutcome` public. *Tradeoff:* a three-way result versus raising and losing
   classification.
2. **D2 Isolated worker composition** (*accepted, Prompt 188*). [REC]
   `evidenceguard_worker.review_seams` is the only app module that may import `evidenceguard_agents`.
3. **D3 Random review IDs** (*accepted, Prompt 188*). [REC] `uuid4` with
   `uq_reviews_tenant_id_idempotency_key`.
4. **D4 Bounded fresh-transaction retries** (*accepted, Prompt 188*). [REC] Three attempts, no
   sleep, `RETRYABLE_CATEGORIES` only.
5. **D5 Tenant-scoped foreign keys** (*accepted, Prompt 188*). [REC] As in M5d-C, including
   `embedding_indexes` and `jobs`.
6. **D6 Timeouts** (*accepted, Prompt 188*). [REC] `statement_timeout` 30 s, `lock_timeout` 5 s;
   `57014` not retryable; no end-to-end deadline.
7. **D7 Key format** (*accepted, Prompt 188*). [REC] `^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$`.
8. **D8 Offline-migration wheel assertion** (*accepted, Prompt 188*).
9. **D9 Flat typed configuration columns** (*accepted, Prompt 188*).
10. **D10 Tenant binding of the request digest** (*accepted, Prompt 188*). [REC] Tenant-free `ReviewRequest` with
    `request_sha256(request, *, tenant_id)` supplied from the validated actor. *Alternative:* a
    tenant-bound request value plus an actor-equality check. *Tradeoff:* the actor stays the only
    tenant authority versus a self-contained value that can disagree with the actor.
11. **D11 Durable job linkage** (*accepted, Prompt 188*). [REC] A stored `run_review_job_id` with a composite FK to
    `jobs` and a uniqueness constraint, the job enqueued before the review insert, and an exact
    association check on replay and reload. *Alternative:* a canonical lookup by tenant, kind and
    key. *Tradeoff:* referential integrity and a direct reload versus no new FK into `jobs`.
12. **D12 Capture failure classification** (*accepted, Prompt 188*). [REC] A typed
    `CaptureFailure` with a fixed, allowlisted `DatabaseFailureCategory` produced in the handler,
    for the whole operation after validation, by one shared guarded classifier reading only the
    SQLSTATE and, for `23505`, the exact constraint name. *Alternative:* a
    caller-supplied classifier callback. *Tradeoff:* one reviewed classifier versus flexibility.
13. **D13 Acknowledged commit then cleanup failure** (*accepted, Prompt 188*). Return the
    `CreatedReview`; call `close()` once and, on an ordinary failure, `invalidate()` once; never
    retry, even if invalidation also fails; process control remains the precedence exception. *Alternative:* `ReviewDatabaseError` as `run_read` does after a
    successful read. *Tradeoff:* an accurate result for a committed write versus uniformity.
14. **D14 Creation job attempts** (*accepted, Prompt 188*). [REC] `max_attempts = 3`
    (W5), checked on reload, separate from provider-call budgets.
15. **D15 Commit-failure classification** (*accepted, Prompt 188*; revised in Prompt 187). [REC] Only exactly
    `40001` or `40P01` during `COMMIT` is a recognized retryable rejection; every other ordinary
    `COMMIT` failure (including `08007`, `40003`, `23505` and missing or unreadable diagnostics) is
    an unknown outcome, never retried automatically. *(The Prompt 186 rule that any SQLSTATE
    proves a rejection is withdrawn.)* *Tradeoff:* fewer automatic retries versus never
    re-creating after a commit that may have succeeded.
16. **D16 Commit state and process-control precedence** (*accepted, Prompt 188*). [REC] Track `not_entered`,
    `entered`, `rejected` and `committed` independently of the exception in flight; the first
    process-control object wins and later ones during cleanup are suppressed. *Alternative:* let a
    later process-control object propagate. *Tradeoff:* a stable, testable outcome versus
    surfacing the most recent interrupt.
17. **D17 Connection cleanup** (*accepted, Prompt 188, subject to the binding clarification*).
    `rollback()` once, then `close()` once only if `rollback()` returned; `invalidate()` once as a
    fallback if either raised (and once, without rollback, after an unknown `COMMIT`); automatic
    retry only when both normal calls returned, never restored by a later `invalidate()`; no claim
    of physical disposal or pool quarantine. *Tradeoff:* abandoning some retries versus reusing a
    connection whose cleanup failed.

#### M5d implementation status (accepted for a local commit, Prompt 191; CI pending)

**Status.** Claude Code implemented the accepted M5d specification in Prompt 189 and corrected it
in Prompt 190 after external review (process control while `read_snapshot` consumes its setup
result, and normalization of timestamp-validation failures; the migration-head test pins updated
under explicit authorization; PostgreSQL tests strengthened); in Prompt 191 a concurrency-test
counter was corrected and a row-access regression added, and the implementation was **accepted at
external review in Prompt 191 for a local implementation commit only**
([ADR-0022](decisions/0022-review-creation.md#external-review-prompt-191)). (Historical: at that
acceptance publication, PostgreSQL execution, Linux verification and current-version CI were
pending; until Prompt 191 it was staged and implementation acceptance was pending.)
**Since then:** feature branch `1bea3731` was published (Prompt 192); Ubuntu and Windows verify passed; PostgreSQL executed and failed three tests; the test corrections were staged (Prompt 193) and accepted for a corrective commit and feature publication (Prompt 194); their PostgreSQL and CI verification remain pending, and main publication remains blocked; the failed-CI logs were independently
retrieved by the external reviewer and recorded in Prompt 193
([ADR-0022](decisions/0022-review-creation.md#exact-commit-ci-at-1bea3731-and-postgresql-test-corrections-prompts-192193)).
Overall M5 acceptance is pending. No endpoint, CLI command, handler, setting, production registry entry or
production enqueue path uses it; `run_review` stays out of `production_registry()`, so none of
its controls operates in the application. The M4d trusted-snapshot limitation is **not** closed:
it closes for review paths only once M5g obtains its snapshot solely through the trusted reload.

- *Added:* `evidenceguard_domain.reviews`, `evidenceguard_persistence.database_failures`,
  `evidenceguard_persistence.reviews`, migration `0006` (`reviews`, `review_bindings`,
  `review_excluded_revisions`), `evidenceguard_worker.review_seams`, the public
  `capture_in_transaction` and the review models; four new test modules, an equivalence test in
  `tests/test_retrieval_postgres.py`, M5d packaging-boundary tests and one additive
  installed-wheel assertion (`CREATE TABLE reviews` in the offline migration SQL).
- *Implementation choices for review:* listed in
  [ADR-0022](decisions/0022-review-creation.md#implementation-choices-and-deviations).
- *Migration-head pins:* in Prompt 189 `tests/test_persistence.py` and `tests/test_readiness.py`
  (two tests each failed locally) and `tests/test_persistence_postgres.py` still pinned head
  `0005` (historical); Prompt 190 authorized and applied the update to head `0006` and the new
  table set.
- *Local verification:* see
  [ADR-0022](decisions/0022-review-creation.md#verification-prompt-190-local-windows-claude-code-historical-local-evidence)
  (the [Prompt 189 results](decisions/0022-review-creation.md#verification-prompt-189-local-windows-claude-code-historical)
  are historical).
  PostgreSQL tests were skipped (no `EG_TEST_DATABASE_URL`) and are unrun evidence.

**M6 – Approval gate and export**
- Revisions, approval, finalize, export, ETags, approver role, audit events.
- *Acceptance:*
  - A stale revision or wrong hash returns 409.
  - A revision after approval resets the report to draft and blocks finalize.
  - Export before finalize returns 409.
  - A reviewer cannot approve.

**M7 – Evaluation and first live evidence**
- Metrics, CLI, annotation workflow, `pricing.yaml`, `docs/evaluation.md`, and committed live runs used to choose the model (D10).
- *Acceptance:*
  - The contract suite runs in CI.
  - Live runs and annotations are committed.
  - README figures quote committed runs only.
  - **The threat model and responsible-AI documents are complete.**

**M8 – Documentation and hardening**
- `docs/architecture.md`, a README walkthrough, and a compose smoke test.

**Release v0.1 = M1–M7.** The v0.1 gate includes the completed threat-model and responsible-AI documents.

**Enhancements:**
- E1 PDF text layer
- E2 PostgreSQL row-level security
- E3 LLM planner query expansion
- E4 LLM executive summary
- E5 HNSW index
- E6 OpenTelemetry
- E7 Voyage reranker
- E8 local fastembed provider
- E9 minimal user interface
- E10 a separate LLM judge
- E11 reviewer-confirmed document authenticity

---

## 10. Remaining blockers and open questions

**Blockers:**
- ~~uv and Python 3.12 are missing. They block M1.~~ Resolved: the project uses uv 0.13.0 and Python 3.12 (see §2), M1 and M2 were built and verified with them, and CI pins the same versions.
- Docker is missing and the system drive is short of space. Local integration tests are blocked and Compose has never been run; CI runs the PostgreSQL integration tests instead. This also limits M3's Dockerfile and Compose work to what CI can verify.
- Anthropic and Voyage keys are missing. They block live evaluation in M7.

**Open questions:**
- [OPEN] Local database: install Docker Desktop (data on the second drive), or rely on CI for integration tests? M2 relied on CI throughout.
- [OPEN] The model-selection thresholds for D10 must be agreed before the first live run.
- [OPEN] Annotation effort: one person labels the claim-support pairs. Should a second labeller check a sample?
