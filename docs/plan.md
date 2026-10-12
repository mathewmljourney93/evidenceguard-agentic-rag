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
| POST `/v1/vendors/{id}/documents` | Upload a revision (multipart) | → 202 `UploadAccepted{document_id, revision_id, revision_no, job_id, status: pending}` | reviewer+ | 413, 415, 422; same bytes for the same document return 200 with the existing revision |
| GET `/v1/documents/{id}` | Revisions, statuses and active revision | → `DocumentDetail` | reviewer+ | 404 |
| GET `/v1/documents/{id}/revisions/{rev}/chunks` | Inspect chunks | → `Page[ChunkView]` | reviewer+ | 404 |
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
- **M3b** has a detailed specification below, **accepted at review (Prompt 59)**. It is **implemented on local branch `feat/worker-runtime` (Prompt 60, corrected in Prompt 61; [ADR-0008](decisions/0008-worker-runtime.md)), awaiting review and CI**; its PostgreSQL verification is pending. There are no production handlers yet. M3c–M3f are not implemented, Compose is unverified, and **overall M3 acceptance is pending**.

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

**M3b, the worker process, in detail (ACCEPTED at review, Prompt 59; implemented on branch `feat/worker-runtime` in Prompt 60, under review; PostgreSQL verification pending):**

M3b turns the M3a library into a running worker. It keeps the accepted architecture: plain Python, PostgreSQL-backed jobs, leases and fenced transactions ([ADR-0003](decisions/0003-plain-python-workflow.md), [ADR-0007](decisions/0007-durable-job-core.md)). There is no new queue, framework or dependency.

The external reviewer inspected the original specification (Prompt 57) and its lifecycle and shutdown corrections (Prompt 58), without running the project suite, and accepted it with the final clarifications of Prompt 59. The choices are listed as settled at the end. The timing values are **initial engineering defaults, not measured guarantees**. The implementation ([ADR-0008](decisions/0008-worker-runtime.md)) records its choices within this specification; it is under review, and its PostgreSQL integration tests have not run yet.

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
