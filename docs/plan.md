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
| Repository | [FACT] Initialized by cloning the GitHub repository `mathewmljourney93/evidenceguard-agentic-rag`. `origin` is correct. Branch `chore/repository-foundation` holds the foundation files. There are no commits yet. |
| Python | [FACT] 3.13 and 3.11 are installed. **3.12 is not.** |
| uv | [FACT] **Not installed.** |
| Docker | [FACT] **Not installed.** No WSL distribution is listed. |
| PostgreSQL / gh CLI | [FACT] Not installed. |
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
- Hatchling editable installs for the multi-root layout (an M1 acceptance check).
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
  - `assessment` ∈ {supported, contradicted, insufficient_evidence}, chosen by the model.
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

**Evidence status.** `evidence_status` has four values, derived from the model's `assessment` and the cited documents' `source_type`:

| evidence_status | Rule | Report wording |
|---|---|---|
| `vendor_claim` | assessment `supported`, and every supporting citation comes from a `vendor_statement` | "The vendor states …" |
| `documentary_support` | assessment `supported`, and at least one supporting citation comes from a `contract` or `third_party_report` | "Documented in … (authenticity not established)" |
| `conflicting` | assessment `contradicted`: current evidence in the snapshot disagrees | "Conflicting evidence: …" |
| `missing` | assessment `insufficient_evidence`, or the question is unresolved (refusal, invalid output, exhausted retries) | "No sufficient evidence found" / "Unresolved: …" |

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
| **Evidence Verifier** | **Claude.** Returns an assessment and claims with citations, which then pass the provenance checks and the status derivation. Invalid output gets one repair attempt; after that the question is unresolved. |
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
| GET `/v1/reviews/{id}/evidence` | Passages, assessments, claims, provenance checks | → `ReviewEvidence` | reviewer+ | 404 |
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
- Install uv, then run `uv python install 3.12`.
- Before M2: Docker Desktop on WSL2, with its data on the second drive, or rely on CI for integration tests.
- Before M7: Anthropic and Voyage keys.
- Git and the GitHub repository are already set up; nothing to do there.

**M1 – Foundations**

*Progress record:*
- **M1a:** packaging, minimal API, CI configuration. Committed locally as `d196afc`; CI has not run on GitHub.
- **M1b:** evidence contracts and pure report-approval transitions (`evidenceguard_domain.evidence`, `.report`, `.approval`), plus initial threat-model and responsible-AI drafts. Committed locally as `da108e5`.
- **M1c:** request IDs, JSON request logging and problem+json errors (`evidenceguard_observability`, API middleware and handlers), ADR-0002. Under review.
- **Pending:** ADR-0003 (plain-Python workflow, renumbered from ADR-0002 because ADR-0002 now records the M1c observability decisions).
- M1c notes:
  - The plan's "logs redact secrets" is met by an allowlist formatter rather than pattern-based redaction.
  - No `.env.example` yet, because M1c adds no settings.
- Decisions made during M1b:
  - Roles are only `reviewer` and `approver`; `admin` arrives with authentication in M2, and gets no approval bypass.
  - Report transitions live in `evidenceguard_domain.approval` rather than a single `state` module.
  - Revision and job state machines arrive with their milestones (M3).

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
- uv and Python 3.12 are missing. They block M1.
- Docker is missing and the system drive is short of space. Local integration tests from M2 onward are blocked; CI is unaffected.
- Anthropic and Voyage keys are missing. They block live evaluation in M7.

**Open questions:**
- [OPEN] Local database: install Docker Desktop (data on the second drive), or rely on CI for integration tests?
- [OPEN] The model-selection thresholds for D10 must be agreed before the first live run.
- [OPEN] Annotation effort: one person labels the claim-support pairs. Should a second labeller check a sample?
