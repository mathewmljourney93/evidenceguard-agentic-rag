# EvidenceGuard implementation plan

**Status:** proposed plan, revised after the first architecture review (Prompt 5 in [prompts.md](../prompts.md)). No application code exists yet. Everything below is a plan, not a description of working software.

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
| Repository | [FACT] Published to GitHub. `main` is at `9d5a93a` (M2 accepted; see §9). |
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

### Lifecycles

Each lifecycle is a pure function in `evidenceguard_domain.state`, tested exhaustively.

**Document revision (correction B)**
1. An upload creates a revision with status `pending`. The document's `active_revision_id` does not change.
2. The worker sets `processing`, writes chunks and embeddings, then **activates the revision in one transaction**:
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
- It needs a MongoDB Atlas key and network access.
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
- Superseded revisions are not in a review's snapshot, so they are never retrieved as evidence.
- The report can note that an older revision existed and what it said, labelled "superseded".
- Two active revisions that disagree make the status `conflicting`. A superseded revision that disagrees with the active one does not.

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
- **M3d** has a detailed specification below, **accepted at review (Prompt 76, corrected in Prompts 77–79)**. It is **implemented on `feat/document-ingestion` (Prompts 80–81; [ADR-0010](decisions/0010-document-ingestion.md)) and reviewed (Prompts 82–83)**. It was verified in CI on `feat/document-ingestion` at `74904e6` ([CI run 38699149482](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38699149482)). From logs retrieved by the external reviewer: [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38699149482/job/116302837532) `1020 passed, 178 skipped in 20.13s`, [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38699149482/job/116302837727) `1019 passed, 179 skipped in 23.75s`, and the [PostgreSQL integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38699149482/job/116302837038) `178 passed, 1020 deselected in 51.89s`: the full suite, including M3d's 45 new tests. The [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38699149417) passed ([job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38699149417/job/116302836923): 33 commits scanned, no leaks found). PostgreSQL, Linux and Windows verification of that version are complete. M3d was then fast-forwarded onto `main` at `cdf7260` (`cdf7260d02b8af9affb369cc805d666be61f9ac0`, adding only documentation after `74904e6`), where [CI run 38701376504](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38701376504) passed again. From logs retrieved by the external reviewer: [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38701376504/job/116310119787) `1020 passed, 178 skipped in 19.71s`, [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38701376504/job/116310119664) `1019 passed, 179 skipped in 16.16s`, and the [PostgreSQL integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38701376504/job/116310119317) `178 passed, 1020 deselected in 53.28s`. The [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38701376501) passed ([job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38701376501/job/116310119403): 34 commits scanned, no leaks found). Both runs were push-triggered on `main`; the reviewer did not run the suite locally. These results demonstrate the tested behaviour, not a performance benchmark or a general security guarantee. The production registry registers `ingest_revision`; at that baseline, upload and document endpoints were not implemented. It assigned the dead-job projection to M3e (section E) as a condition of overall M3 acceptance; M3e implements it and is verified in CI and on `main` at `2e605e7` (below). M3f is not implemented, Compose is unverified, and **overall M3 acceptance is pending**.
- **M3e** has a detailed specification below (upload, document, revision, chunk and job endpoints, and the required `ingestion_state` projection), **accepted at external review (Prompt 86, corrected in Prompts 87–88)**. Its implementation (Prompt 89, corrected in Prompt 90; [ADR-0011](decisions/0011-document-api.md)) was accepted at external review (Prompt 91) and is **reviewed and verified in CI on `feat/document-api` at `ccdf08d` ([CI run 38755179760](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38755179760)): Ubuntu, Windows and the full 204-test PostgreSQL integration suite (including the 26 M3e tests) passed, per job logs retrieved by the external reviewer**. PostgreSQL, Ubuntu and Windows verification of that version is complete. It was then fast-forwarded onto `main` at `2e605e7` (`2e605e7bcf3b7b1ee90e9f12cb2acddb6950048f`, adding only documentation after `ccdf08d`), where [CI run 38758727669](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38758727669) passed again. From job logs retrieved by the external reviewer: [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38758727669/job/116503999468) `1261 passed, 204 skipped in 28.04s`, [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38758727669/job/116503999418) `1260 passed, 205 skipped in 29.97s`, and the [PostgreSQL integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38758727669/job/116503999580) `204 passed, 1261 deselected in 56.65s`. The [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38758727831) passed ([job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38758727831/job/116503999509): 38 commits scanned, no leaks found). Both runs were push events on `main`; the reviewer did not run the suite locally.
- **M3f** has a detailed specification below (container image, Compose API, worker and migration services, and a required CI Compose smoke), **proposed in Prompt 95, corrected in Prompt 96 and accepted at external review (Prompt 97)**. Its implementation (Prompt 98, corrected in Prompt 99; [ADR-0012](decisions/0012-containers.md)) was **accepted at external review for a local commit on `feat/container-stack`** (Prompt 100); nothing is pushed or merged. No image build, effective build-context check, image check, Compose smoke or real Docker cleanup has run, and container execution and CI verification remain pending. The reported local Windows results (Prompt 99) were `1363 passed, 205 skipped` (204 PostgreSQL skips and one POSIX-only signal skip), with `103 passed` for the focused helper and file tests. Local Compose remains unverified, and **overall M3 acceptance remains pending**.

M3 keeps the architecture above and in [ADR-0003](decisions/0003-plain-python-workflow.md): plain Python, PostgreSQL-backed jobs claimed with `FOR UPDATE SKIP LOCKED`, leases, heartbeats and fenced writes. There is no new orchestration framework or queue dependency. Each slice is reviewed, verified in CI and merged before the next one starts. The M3 acceptance criteria above are split across the slices as follows:

| Slice | Scope | M3 acceptance criteria it carries, or a new *slice check* |
|---|---|---|
| **M3a** | Durable job core: the `jobs` table (migration `0002`), the pure job lifecycle, and enqueue, claim, heartbeat, complete, fail, reclaim and the write fence | Two concurrent claims produce one owner; a stale worker cannot complete a job after it has been reclaimed; retries reach `dead` |
| **M3b** | Worker process: an `eg-worker` command with a polling loop, heartbeats, handler registry, backoff and graceful shutdown, built only on M3a | *Slice check:* lease loss stops a handler before its next fenced write |
| **M3c** | Documents and revisions: `documents` and `document_revisions` tables (migration `0003`), the revision lifecycle as pure functions, and fenced transactional activation | A failed replacement leaves the previous revision active; two revisions completing out of order leave only the newer one active; a crash during activation rolls back cleanly; a stale worker cannot activate a revision |
| **M3d** | Parsing and chunking: plain-text and Markdown parsing, the deterministic chunker v1, the `chunks` table (migration `0004`) and the `ingest_revision` job handler | Chunk IDs include tenant and revision, so the same bytes under two tenants produce disjoint chunk IDs; a stale worker cannot write chunks |
| **M3e** | Upload and document endpoints: upload, list and get, with size and media-type limits; a revision and its ingestion job are created in one transaction | 413, 415 and 422 behave as specified; re-uploads are idempotent |
| **M3f** | Dockerfile and Compose services for the API, worker and database | *Slice check:* images build in CI. Compose stays unverified locally while Docker is unavailable (§10). |

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

**M3f, container image and Compose services, in detail (ACCEPTED at review, Prompt 97; proposed in Prompt 95, corrected in Prompts 96–97; implementation staged in Prompt 98, corrected in Prompt 99, accepted at review and committed locally in Prompt 100; container CI not yet run; see ADR-0012):**

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
  - What remains: the M3f build and smoke criteria above, then review of overall M3 acceptance. Per the reviewer's decision, a passing CI Compose smoke can satisfy the M3 Compose requirement alongside the other agreed criteria.
  - No other outstanding M3 criterion was found. Local Compose stays unverified until it actually runs (§10).
- **Open decisions:** none; the four Prompt 95 decisions are settled above. Two items are implementation-time verifications, not open choices: the official-registry check of both digests, and Docker's actual behaviour for the commands in E. If either contradicts this specification, implementation stops for review.

**M4 – Embeddings, retrieval and corpus**
- Provider interface, `HashingEmbedder`, Voyage adapter (mocked in CI), RRF search over snapshot revisions, `sample_data/` including the injected variant, ground truth with acceptable and wrong claims, and the retrieval contract suite.
- *Acceptance:*
  - No foreign, superseded or non-snapshot chunks are ever returned.
  - Recall@k is computed correctly.

**M5 – Review workflow (fake model in CI)**
- Provider interface; Anthropic and scripted fake providers; `prompts/verifier/v1.md` and `prompts/risk_analyst/v1.md`; planner; orchestration; review snapshot; provenance checks; status derivation; report renderer; provider-call records and spans.
- *Acceptance:*
  - Invalid output, a refusal, a timeout and a forged chunk ID each end unresolved or rejected.
  - **A revision activated after a review started is not used by that review, including after a resume.**
  - **A worker killed after a stage commit resumes without duplicate rows.**
  - **A worker killed between a provider response and its commit repeats the call once.** The test checks the second call is recorded and no duplicate stage row is written.
  - **A stale worker's stage writes are rejected.**
  - The injection canary never appears in output.

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
