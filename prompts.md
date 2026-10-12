# Prompt history

This file is the public engineering record for EvidenceGuard. It holds, verbatim and in chronological order, the prompts submitted to the Claude Code implementation session, with a short outcome note after each one.

- Only user prompts are recorded. System instructions, model reasoning, credentials and environment contents are excluded.
- Prompts are reproduced exactly as received, inside fenced blocks so their formatting is preserved.
- Outcome notes are separate from the prompts. "Pending" means the work has not yet been reviewed.
- Dates: Prompts 1–5 were given in one Claude Code session whose reported date was 2026-10-11. Exact times were not recorded.

## Coverage and completeness

- **Covered:** every prompt submitted to the Claude Code implementation session, starting with Prompt 1.
- **Not covered:** the project was coordinated and reviewed in separate ChatGPT conversations. Those conversations, including any earlier project brief written there, are not in this file. Only the prompts brought into the Claude Code session appear here.
- **Completeness:** Prompts 1–5 are complete and verbatim. Nothing was redacted, because none of them contained credentials or confidential material.
- **Non-prompt interaction:** between Prompts 1 and 2, the user declined a plan-approval request without sending any text, so there is nothing to record for it.

---

## Prompt 1: Architecture and implementation planning

- **Stage:** Planning (no writes permitted)
- **Date:** 2026-10-11 (session date)

````text
You are the implementation engineer for a new public portfolio repository:

evidenceguard-agentic-rag

Public title:
EvidenceGuard: Auditable Multi-Agent RAG for Vendor Risk Review

ChatGPT is coordinating and reviewing the project. I will bring your output back there before implementation begins.

THIS TURN IS PLANNING ONLY.

Inspect the environment and repository using read-only commands. Do not create, edit, delete, stage, commit or push files. Do not install dependencies, start services, provision infrastructure or call paid model APIs. Return the proposed plan in this conversation.

If the repository contains existing work, inspect it and account for it. Do not assume it is empty or replace anything.

PROJECT PURPOSE

Build a vendor-risk review copilot that ingests synthetic vendor documents, retrieves authorized evidence, identifies supported answers, contradictions and missing information, and produces a cited draft report.

A human must explicitly approve the current draft before finalization or export. This is evidence-based decision support, not legal advice or compliance certification.

The repository should demonstrate Python, FastAPI, RAG, bounded agent workflows, evaluation, tenant isolation, reliability and operational judgment through working behavior and reproducible evidence.

Do not add architecture simply to cover job-advertisement keywords. Do not claim production readiness or measured performance before supporting evidence exists.

APPROVED STACK

- Python 3.12 and uv
- FastAPI and Pydantic v2
- PostgreSQL and pgvector
- SQLAlchemy 2 and Alembic
- Anthropic Claude as the primary real model provider
- A typed model-provider abstraction
- A deterministic fake provider for tests and CI
- Versioned prompt files
- Structured JSON logging with request and trace identifiers
- Pytest, Ruff and Mypy
- Docker Compose
- GitHub Actions

Use explicit typed workflow state. Recommend LangGraph only if it materially improves recovery or inspection over ordinary Python.

Use PostgreSQL-backed ingestion jobs and a separate worker, with safe job claiming, idempotency and retry behavior. Do not add Redis, Kubernetes, billing, a large frontend, multiple cloud providers or DynamoDB to version one.

APPROVED STRUCTURE

apps/
  api/
  worker/
packages/
  agents/
  domain/
  evaluation/
  observability/
  retrieval/
prompts/
  planner/
  verifier/
  risk_analyst/
  report_writer/
sample_data/
  vendors/
tests/
  unit/
  integration/
  adversarial/
docs/
  decisions/
  architecture.md
  evaluation.md
  responsible-ai.md
  threat-model.md
infra/
  docker/
  github/
.env.example
.gitignore
docker-compose.yml
pyproject.toml
README.md

Explain a concrete, importable Python packaging arrangement within this structure. Prefer one distribution initially unless multiple distributions solve a real problem. Avoid empty decorative directories.

GitHub Actions must live under .github/workflows/ so GitHub discovers them; explain that necessary addition.

APPROVED WORKFLOW

1. Review Planner: converts a review template into bounded evidence questions.
2. Retriever: obtains tenant-scoped passages with provenance.
3. Evidence Verifier: classifies support, contradiction or insufficient evidence.
4. Risk Analyst: creates findings from verified evidence.
5. Report Composer: creates a cited draft with unresolved questions.
6. Human Approval Gate: controls finalization and export.

Components communicate through typed contracts and structured outputs.

Ordinary code handles authorization, validation, routing and state transitions. Explain which components actually require model judgment and which should be deterministic.

SECURITY AND RELIABILITY

Tenant identity must come from authenticated credentials, never an arbitrary client-supplied tenant identifier.

Plan:
- Tenant-scoped access to vendors, documents, chunks, jobs, reviews, reports and traces.
- Treatment of uploaded and retrieved content as untrusted data.
- File-format and size limits.
- Secret handling and log redaction.
- Citation validation against actual authorized evidence.
- Provider timeouts, bounded retries and invalid-output handling.
- Durable review progress and safe resume behavior.
- Worker interruption, duplicate delivery and stale job recovery.
- Approval tied to an exact report revision; subsequent changes invalidate approval.
- Honest limitations, including the limits of prompt-injection defenses.

Choose a narrow first set of document formats. Do not attempt every format.

Keep document processing and inference costs manageable on a modest Windows laptop.

RETRIEVAL DECISIONS THAT MUST BE RESOLVED

Claude is the generation provider. Do not assume this also supplies an embedding service.

Recommend:
- An explicit embedding-provider interface.
- A practical real embedding option and its resource/cost tradeoffs.
- A deterministic test substitute, clearly distinguished from meaningful semantic retrieval.
- A lexical/vector retrieval approach.
- Chunk boundaries and stable identifiers.
- Citation provenance, including document revision and page or section.
- Handling of superseded policies and conflicting current documents.

Verify current official documentation where necessary. Identify anything you cannot verify instead of inventing an API or model identifier.

SYNTHETIC DEMONSTRATION CORPUS

Use fictional vendors and at least two tenants. Include:
- Conflicting retention periods.
- Encryption mentioned without evidence of coverage at rest.
- Unsupported regulatory-compliance claims.
- Missing incident-notification details.
- A question with no answer in the corpus.
- An embedded prompt-injection instruction.
- Irrelevant retrieval distractors.
- Similar evidence belonging to another tenant.
- A superseded policy and its newer revision.
- A table or formatting case supported by the chosen ingestion formats.

Separate vendor claims from verified facts. Never use confidential or proprietary client material.

EVALUATION

Design a repeatable harness for:
- Retrieval Recall@k.
- Citation precision.
- Supported-claim rate.
- Correct abstention rate.
- Contradiction detection.
- Prompt-injection resistance.
- Cross-tenant isolation.
- End-to-end latency.
- Token usage and estimated cost.

Define the ground truth, denominators and failure conditions. Distinguish deterministic contract/security tests from real-model quality evaluation.

Fake-provider results must never be presented as evidence of Claude's reasoning or semantic retrieval quality. Do not use the same logic to generate answers and independently “grade” them.

No README benchmark is allowed without committed inputs, configuration and a reproducible command. Cost estimates must record their pricing assumptions and date.

YOUR TASK NOW

1. Inspect:
   - Current directory and existing files.
   - Applicable repository instructions.
   - Git status, branch and remotes.
   - Available Python, uv and relevant tooling.
   - Existing packaging/configuration, if present.

Do not print credentials, environment secrets or authentication tokens. Describe missing tools without installing them.

2. Validate the approved architecture:
   - Keep the product direction.
   - Identify concrete gaps, conflicts or implementation risks.
   - Recommend the simplest defensible choice for each.
   - Label observed facts, recommendations and unresolved assumptions separately.

3. Define the domain model and typed boundaries:
   - Entities, relationships and tenant ownership.
   - Document and ingestion lifecycles.
   - Evidence questions, passages, verification results and findings.
   - Review/report state transitions.
   - Approval/rejection semantics.
   - Trace and provider-call metadata.

4. Propose an API table:
   - HTTP method and path.
   - Purpose.
   - Request and response schemas.
   - Authorization.
   - Important error behavior.
   - Idempotency or concurrency behavior where relevant.

Separate first-release endpoints from later additions.

5. Design the synthetic corpus and evaluation fixtures:
   - Vendor/document layout.
   - Expected evidence outcomes.
   - Stable ground-truth references.
   - Adversarial cases.
   - Evaluation methodology and commands to implement later.

6. Produce a staged implementation plan:
   - Small, coherent milestones.
   - Files/modules introduced at each stage.
   - Concrete acceptance criteria.
   - Relevant verification commands.
   - Dependencies and risks.
   - Suggested commit boundaries.

Aim for a narrow usable release in several focused sessions, followed by clearly marked enhancements.

The first implementation milestone should establish packaging, developer commands, a minimal API and the essential typed contracts. It should not attempt the entire system.

7. Finish with a concise review handoff:
   - What you actually inspected.
   - Architecture recommendations requiring review.
   - Proposed first implementation milestone.
   - Missing prerequisites or genuine blockers.
   - Any questions whose answers would materially change implementation.

Do not implement anything after presenting the plan. Wait for me to return with the reviewed next prompt.
````

**Outcome (pending review):**
- Read-only inspection of the then-empty project folder and the local toolchain. Missing: uv, Python 3.12, Docker, a WSL distribution, PostgreSQL and the gh CLI. The folder was not yet a Git repository.
- Model, embedding and pgvector details were checked against official documentation.
- A staged plan was produced, covering architecture gaps, domain model, API, corpus, evaluation and milestones M0–M8. It was saved in Claude Code's own plan storage, outside the repository.
- Nothing was written inside the repository.

---

## Prompt 2: Workspace-boundary diagnostic

- **Stage:** Diagnostic (read-only)
- **Date:** 2026-10-11 (session date)

````text
Before proceeding, verify the workspace boundary.

The intended project root is:
D:\Claude\evidenceguard_agentic_rag

Your plan appears to have been saved under:
D:\Claude\fix_vibe\claude-config\plans\

Use read-only checks and report:
1. Your actual current working directory.
2. The Git repository root and remote URL for the intended project.
3. Which files or directories outside the intended project you inspected during this session, based on the tool history available to you.
4. Which files outside the project you wrote or modified.
5. Why the plan was saved under fix_vibe: a configured Claude plan-storage location, your working directory, or another reason.
6. Whether any instructions or content from another project influenced this plan.

Do not read unrelated project files to investigate this. Do not expose credentials or secrets. If your tool history is incomplete, state that explicitly.

Do not implement, install, stage, commit, push or delete anything. Return your findings in the conversation and remain in Plan Mode.
````

**Outcome (reported, pending review):**
- The working directory was the project folder. At that time it was not a Git repository and had no remote.
- The only file written outside the project was the plan file. It went to the plan-storage folder inside the configured Claude configuration directory, because Plan Mode requires that location.
- Outside the project, Claude had listed only the names of sibling folders and opened none of them. No content from another project influenced the plan.

---

## Prompt 3: Return the full plan; justify the model and fallback proposals

- **Stage:** Planning review (no repository writes)
- **Date:** 2026-10-11 (session date)

````text
Return the full existing plan in this conversation for external review. Do not implement anything or copy the plan into the project yet.

Include the exact model identifier and official source supporting the proposed “Claude Opus 5.5” choice. Explain what “server-side refusal fallbacks” means, where that recommendation came from, and why it belongs in this project. Treat both as unapproved proposals.

For subsequent project inspection, stay within D:\Claude\evidenceguard_agentic_rag. Tool-version checks and explicitly relevant configuration checks are acceptable; do not enumerate sibling projects.
````

**Outcome (pending review):**
- The full plan was returned in the conversation.
- Model ID `claude-opus-5-5` was verified against Anthropic's official Models overview page. Both proposals were traced to the default guidance in Claude Code's bundled Claude API reference.
- The server-side refusal fallback recommendation was changed to *off* for v1, so refusals fail closed. Default model choice by measurement was left open.
- Both remain unapproved proposals.

---

## Prompt 4: Repository foundation

- **Stage:** Repository configuration and documentation (no application code)
- **Date:** 2026-10-11 (session date)

````text
Set up the repository foundation for EvidenceGuard. This authorizes repository configuration and documentation only, not application implementation.

Project root:
D:\Claude\evidenceguard_agentic_rag

Expected GitHub remote:
https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git

First inspect the current files, applicable instructions, Git root, status, branch, remotes and recent commits. Confirm the Git root is exactly this project folder and origin points to the expected repository. If either check fails, stop and report it.

Preserve existing files and changes. Do not inspect unrelated projects.

Create a working branch named chore/repository-foundation if doing so is safe. Do not commit or push during this task.

Implement the following limited foundation.

1. Git hygiene

Create or update .gitignore to exclude:
- Python virtual environments, caches and build artifacts.
- Local environment files and secret-bearing configuration.
- Local uploaded documents, database files and runtime artifacts.
- Local Claude settings, transcripts and scratch files where appropriate.

Explicitly allow .env.example.

Do not use broad patterns that hide intended synthetic fixtures, evaluation inputs, reproducible results or prompts.md.

Add .gitattributes with sensible text normalization, including LF for Python, Markdown, YAML and shell scripts. Handle any Windows-specific scripts appropriately.

Create .env.example only if its configuration names are settled. Use obvious placeholders only. Do not invent configuration that the application does not yet use.

2. Complete prompt history

Create prompts.md as a public engineering record.

Record verbatim, in chronological order, every user-supplied project prompt available in this Claude session, including:
- The initial architecture/planning prompt.
- The workspace-boundary diagnostic prompt.
- The request to return the plan and justify model/fallback recommendations.
- This repository-foundation prompt.

Preserve full wording, including code blocks. Do not replace full prompts with summaries.

For each entry include:
- Sequential prompt number.
- Stage or purpose.
- Date, if known; never invent a precise timestamp.
- Full prompt text.
- A short, clearly separate outcome note. Mark unreviewed work as pending.

Record user prompts only. Do not publish hidden system instructions, internal reasoning, credentials, environment contents or unrelated conversations.

If an earlier prompt is unavailable or truncated, mark the gap explicitly. Do not reconstruct it from memory or pretend the history is complete.

If a prompt contains a credential or confidential material, redact only that material with an explicit marker and explain the redaction. Full history must not expose secrets.

Avoid machine-specific absolute paths in short outcome notes. Preserve paths in historical prompt text unless they contain sensitive information.

3. Persistent development instructions

Create a concise CLAUDE.md covering:
- Inspect current repository state before changes.
- Keep work within the project and agreed milestone.
- Append each new implementation/review prompt verbatim to prompts.md before doing its authorized work.
- For planning-only turns that prohibit writes, retain the prompt for the next authorized documentation update.
- Keep prompts.md outcome notes accurate and distinguish reported checks from verified checks.
- Preserve working code and unrelated changes.
- Use synthetic demonstration data only.
- Never put credentials in source, prompts.md, fixtures or logs.
- Never claim checks passed unless they actually ran.
- Before a commit, inspect status, staged paths and the staged diff, and run relevant checks and secret scanning.
- Never push, merge or deploy without Mathew's explicit approval.
- Do not amend or rewrite existing history without explicit instruction.

4. Public README

Create or update a concise README identifying the approved project, its purpose and its current planning/foundation status.

Link to prompts.md so an employer can find the engineering workflow.

Do not claim working RAG, security guarantees, passing evaluations, production readiness or benchmarks at this stage.

5. Secret detection

Propose and implement a small, reproducible secret-scanning setup using Gitleaks or another justified maintained scanner.

Verify installation instructions and action/version references against official sources. Do not invent versions or use a moving main/master reference for a GitHub Action. Prefer an immutable action commit SHA.

Add a GitHub Actions workflow under .github/workflows/ that scans Git history with sufficient checkout depth. Give it minimal permissions.

Keep synthetic placeholder credentials clearly fake. Do not disable rules broadly or add sweeping allowlists to make scans pass.

Document how to run the scanner locally before committing. A CI scan runs after upload, so explain that it cannot replace a local check before publication.

Do not install system tools or scan unrelated directories. If a required scanner is unavailable locally, report the missing prerequisite and exact verified installation command. Do not claim the scan passed.

6. Review handoff

Return:
- Verified Git root, branch and remote.
- Files created or modified.
- Full diffs for the configuration, CLAUDE.md, README and workflow.
- Prompt-history entry titles and any missing-history gaps.
- Commands actually run and their results.
- Secret-scanning status and remaining prerequisites.
- git diff --check output.
- Final git status.

Do not print any discovered secret. Report its file location and type without exposing the value.

Do not stage, commit, push, install application dependencies, create application modules or start the main implementation. Stop after the review handoff.
````

**Outcome (pending review; nothing staged, committed or pushed):**
- The Git root and `origin` were verified. Branch `chore/repository-foundation` was created on the empty repository.
- Added `.gitignore`, `.gitattributes`, `CLAUDE.md`, `README.md`, this file and `.github/workflows/secret-scan.yml`. The workflow pins Gitleaks v8.30.1 by SHA-256 and `actions/checkout` by commit SHA.
- `.env.example` was not created, because no configuration names are settled yet.
- Gitleaks is not installed locally, so **no local secret scan has run**. The CI workflow has not run yet either.

---

## Prompt 5: Repository-foundation review corrections

- **Stage:** Foundation corrections and plan recording (no application code)
- **Date:** 2026-10-11 (session date)

````text
Complete the repository-foundation review corrections only. Do not begin application implementation.

Work in:
D:\Claude\evidenceguard_agentic_rag

Inspect current instructions, files, Git root, branch, status and remotes first. Preserve existing changes. The expected remote is:
https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git

Append this prompt verbatim to prompts.md under the existing history rules.

1. Review and complete the foundation

- Inspect prompts.md against the user prompts available in this session. Confirm the full text is present, not summaries.
- Define its coverage honestly: prompts submitted to the Claude implementation session. Do not claim it contains every conversation or the earlier ChatGPT project brief unless those are actually included.
- Preserve historical wording and pending-review labels. Do not invent missing history.
- Show the full prompts.md in your handoff so the external reviewer can inspect it.

- Extend .gitignore to exclude local Claude transcripts, session exports, scratchpads and memory artifacts if placed inside this repository. Use narrow patterns based on actual or documented locations.
- Preserve tracked CLAUDE.md, prompts.md and intentionally shared Claude configuration. Do not ignore all of .claude indiscriminately.
- Recheck that synthetic data, evaluation fixtures and intended results remain trackable.

- Update README to say the secret-scanning workflow is configured but has not yet run in GitHub Actions.
- Document checking `gitleaks version` after installation.
- Document that scanners do not detect every secret, and that staging review is also required.
- Explain that full-history scanning cannot validate an unborn repository with no commits; scan staged content before the first commit instead.
- Keep commands consistent with the installed scanner.

2. Record architecture review decisions

Create docs/plan.md containing the existing proposed plan, updated with the following decisions. This explicitly authorizes copying your existing EvidenceGuard plan from its known Claude-managed plan file. Do not inspect other files outside the project.

Accepted direction:
- One Python distribution with prefixed import packages.
- Add packages/persistence/.
- GitHub workflows under .github/workflows/.
- Deterministic planner and report renderer.
- Model judgment in verifier and risk analyst.
- Plain Python orchestration.
- PostgreSQL jobs and exact vector search.
- Markdown and UTF-8 text ingestion initially.
- Provider refusals remain unresolved; no automatic refusal fallback in v1.
- Live model selection remains deferred to measured evaluation.
- No local embedding-model download by default.

Correct the plan:

A. Chunk identity
Scope deterministic chunk identity to tenant and document revision, as well as chunker version and ordinal. Identical bytes across tenants or vendors must not collide or share evidence accidentally. Keep database constraints consistent.

B. Revision activation and review snapshots
A newly uploaded revision is pending until ingestion succeeds. Failed replacements must not retire the previously active revision. Activation and supersession are transactional.
Each review records the exact eligible revision IDs and relevant configuration it uses. Resumed reviews retain that snapshot even if new documents arrive. Add concurrency and failure tests to the relevant milestones.

C. Evidence semantics
Citation membership and quote matching validate provenance, not semantic entailment or document authenticity.
Do not call an uploaded third-party document independently authenticated merely because its source_type says third_party_attestation.
Define typed statuses that distinguish:
- support for what a vendor claims;
- documentary support for a factual assertion;
- missing evidence;
- conflicting evidence;
- authenticity that has not been established.
Keep the schema narrow and internally consistent.

D. Evaluation
Citation precision must measure whether citations support the associated claims, not simply whether they contain a gold keyword.
Use human-authored acceptable claims, supporting passages and deliberately wrong claims with valid quotations.
Report coverage alongside supported-claim precision so universal abstention cannot appear successful.
Use paired clean/injected cases to evaluate prompt injection.
Label latency percentiles from very small samples as descriptive; do not imply statistically reliable p95 performance.

E. Recovery
Reuse persisted responses and completed stages where safe. Do not promise exactly-once external model calls.
Document the crash window between receiving a provider response and persisting it, its possible duplicate cost, and the distinction between idempotent database effects and external calls.
Ensure stale-worker fencing protects stage/result writes as well as job completion.

F. Release scope
Write initial threat-model and responsible-AI documentation early, and complete them before v0.1.
Refresh the environment section: Git is now initialized by cloning, the remote is correct, and the foundation branch exists. Do not repeat git init or repository creation.

3. Verify and stage for review

Check whether Gitleaks is available. Do not install system tools yourself.

If available:
- Report its version.
- Inspect every intended file for credentials and accidental private content without printing any secret.
- Stage only the explicit foundation/documentation files covered by this task.
- Inspect the staged paths and diff.
- Run git diff --cached --check.
- Run the supported Gitleaks staged scan with redaction.
- Report actual output and exit codes. Account for the repository having no commits.

If unavailable:
- Leave everything unstaged.
- Report the missing prerequisite.
- Do not claim secret scanning passed.

Do not create a commit or push. Do not change global Git settings, credentials or unrelated Claude configuration.

Return:
- Git root, branch and remote.
- Changes made and relevant diffs.
- Full prompts.md.
- Updated plan decisions and remaining genuine blockers.
- Verification commands, output and exit codes.
- Final staged paths and git status.
- Explicit confirmation that nothing was committed or pushed.
````

**Outcome (pending review; staged, not committed or pushed):**
- Git root, branch `chore/repository-foundation` and `origin` were re-verified. The repository still has no commits.
- `prompts.md` coverage was restated as the Claude Code implementation session only, excluding the separate ChatGPT conversations. This prompt was appended verbatim.
- `.gitignore` now also excludes Claude Code's documented local-only paths (`.claude/agent-memory-local/`, `.claude/worktrees/`). Session exports and scratch files go under the ignored `.local/` directory, a convention added to `CLAUDE.md`.
- The README now covers: the workflow has not run yet, the `gitleaks version` check, reviewing staged content before every commit, the limits of scanners, and staged scanning before the first commit.
- `docs/plan.md` records accepted decisions D1–D11 and corrections A–F.
- **Verified in this session:**
  - Gitleaks 8.30.1 (installed by the user) found no leaks in the staged content (exit 0).
  - A full-history scan read 0 bytes (exit 0), confirming it cannot check a repository with no commits.
  - `git diff --cached --check` reported no problems (exit 0).
  - A manual check found no credential patterns. The only local paths are inside verbatim historical prompts.
- **Not yet run:** the GitHub Actions secret-scan workflow.

**Review note (added with Prompt 6):** the external reviewer accepted the foundation changes and the staged-scan results reported above for a local commit. That acceptance was based on the reported results; the reviewer did not run local commands. The GitHub Actions secret-scan workflow is still unverified.

---

## Prompt 6: First local foundation commit

- **Stage:** Plan clarification, final checks and first local commit (no push, no application code)
- **Date:** 2026-10-11 (session date)

````text
Finalize and create the first local repository-foundation commit. Do not push or begin application implementation.

Inspect CLAUDE.md, Git root, branch, remotes, status and the current staged diff first.

Expected root:
D:\Claude\evidenceguard_agentic_rag

Expected branch:
chore/repository-foundation

Expected origin:
https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git

Preserve existing work. If unexpected changes are present, report them before incorporating them.

Append this prompt verbatim to prompts.md.

The external reviewer has accepted the supplied foundation changes and staged-scan results for a local commit, subject to the following plan clarification and fresh checks. GitHub Actions has not yet been verified.

1. Make two narrow clarifications in docs/plan.md:

Evaluation independence:
- Human-authored labels are the reference standard.
- A Verifier probe against known claims measures the Verifier's behavior; it must not grade its own generated answers.
- Deterministic scoring is appropriate only for explicitly defined labels or structured outputs with predetermined expected results.
- Semantic support for free-text claims requires human review in v1, with the grading process recorded.
- Keep model-generated judgments distinct from independent evaluation results.

Retrieval:
- Exact vector scanning computes nearest neighbors without approximate-index loss.
- It does not guarantee that all relevant evidence is retrieved or that Recall@k is perfect.

Do not redesign the evaluation harness or other architecture in this task.

2. Keep historical outcome notes intact. Add a brief review note identifying acceptance of the foundation and the outstanding CI check. Do not imply that the external reviewer independently executed local commands.

3. Stage only these seven files, including their authorized updates:
- .gitattributes
- .github/workflows/secret-scan.yml
- .gitignore
- CLAUDE.md
- README.md
- docs/plan.md
- prompts.md

Review the complete staged diff for accidental private content and secrets. Do not print any discovered secret.

Run:
- git diff --cached --check
- gitleaks git --pre-commit --staged --redact --verbose .

If either fails, fix only issues within this scope and rerun the affected checks. Do not suppress scanner rules or add broad allowlists.

4. If the final staged content passes, create one local commit:

chore: establish repository foundation and engineering record

Do not amend an existing commit, change branches, merge, push, or modify global configuration.

5. After committing:
- Run the full-history Gitleaks scan with redaction.
- Confirm the new commit exists and its file list matches the intended seven files.
- Report final git status.
- If the history scan fails, stop and report the finding type/location without exposing its value. Do not rewrite history or push.

Return a concise handoff:
- Commit SHA, branch and subject.
- Files committed and diff summary.
- Verification output and exit codes.
- Final git status.
- Explicit confirmation that nothing was pushed.

Do not reproduce the entire prompts.md again unless you detect a history discrepancy.
````

**Outcome (pending review):**
- `docs/plan.md` received two narrow clarifications: evaluation independence, and the limits of exact vector search. Nothing else was redesigned.
- The seven foundation files were re-staged. `git diff --cached --check` and the Gitleaks staged scan were rerun before committing.
- One local commit was created on `chore/repository-foundation`. The commit SHA and full-history scan result are in the session handoff, because a commit cannot contain its own SHA.
- Not pushed. The GitHub Actions secret-scan workflow is still unverified.

**Review note (added with Prompt 7):** the foundation commit `52acebd` was accepted on the basis of the reported checks. GitHub Actions is still unverified.

---

## Prompt 7: M1a, Python packaging and minimal FastAPI app

- **Stage:** Implementation, milestone M1a (staged for review, no commit)
- **Date:** 2026-10-11 (session date)

````text
Implement M1a only: reproducible Python packaging and a minimal FastAPI application.

Inspect CLAUDE.md, docs/plan.md, existing files, Git status, branch, remotes and HEAD before editing.

Expected project:
D:\Claude\evidenceguard_agentic_rag

Expected starting commit:
52acebd1eb33946970a60549cc4366743687ce72

Expected remote:
https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git

The foundation commit has been accepted based on the reported checks. GitHub Actions remains unverified.

If the starting state differs, explain the difference and preserve existing work.

Append this prompt verbatim to prompts.md. Create branch feat/python-api-foundation from the current committed foundation, provided the working tree is clean.

SCOPE

Implement a small, working foundation:
- Python 3.12.
- uv dependency management and a committed lockfile.
- One distribution using Hatchling.
- Two import packages only:
  apps/api/evidenceguard_api/
  packages/domain/evidenceguard_domain/
- Minimal FastAPI app factory.
- GET /healthz returning a typed {"status": "ok"} response.
- An eg-api console entry point that starts Uvicorn.
- OpenAPI documentation generated by FastAPI.
- Meaningful packaging/API tests.
- Ruff and strict Mypy.
- A GitHub Actions verification workflow.
- A short packaging ADR and accurate README instructions.

Do not create the unused packages or empty directories.

Do not implement authentication, readiness checks, persistence, workers, retrieval, providers, review/report state machines, approval endpoints, UI or Docker in this task.

ENVIRONMENT

Check uv and available Python versions.

If uv is unavailable, stop before implementation and give the exact missing prerequisite.

You may use uv to obtain Python 3.12 and create the project virtual environment, generate the lockfile, install project dependencies and build the distribution. These project setup operations are authorized.

Do not install system tools, alter global settings, call paid APIs or download embedding models.

If the currently configured environment uses another Python version, preserve it and create the appropriate project environment safely. Do not silently run this milestone on Python 3.13.

PACKAGING

- Define the Python 3.12 requirement clearly.
- Pin the development interpreter through .python-version.
- Configure Hatchling for the approved nested package layout.
- Declare runtime and development dependencies separately.
- Add only dependencies needed by this milestone.
- Commit uv.lock; ignore environments and build artifacts.
- Keep domain independent of API.
- Make imports work through the installed distribution, without sys.path patches or PYTHONPATH workarounds.
- Do not claim packaging works solely because tests can import from the source checkout.

API

- Use a create_app() factory with no import-time server startup.
- Keep /healthz a process-liveness endpoint. It must not imply database readiness or complete application functionality.
- Use a small Pydantic response contract in the domain package.
- Do not expose environment variables, filesystem paths or secrets through the endpoint.
- Keep the startup entry point straightforward and suitable for Windows.
- Avoid speculative configuration. Add .env.example only if implemented settings actually require it.

TESTS AND CHECKS

Verify:
- /healthz returns HTTP 200 and the expected JSON.
- OpenAPI describes the endpoint and response schema.
- The console entry point is packaged correctly.
- The built wheel imports successfully in a separate temporary environment outside the source package paths.

Keep temporary environments and inspection artifacts in ignored project-local paths. Do not modify unrelated directories.

Configure and run:
- uv sync --locked
- uv run --locked ruff check .
- uv run --locked ruff format --check .
- uv run --locked mypy
- uv run --locked pytest
- uv build

Resolve failures without broad type-check exclusions, blanket ignores or weakening assertions.

Perform a brief real-server smoke check of /healthz, then stop the server. Report the command and response. Do not leave a background process running.

CI

Add .github/workflows/ci.yml that verifies this milestone on Python 3.12, on both Ubuntu and Windows.

- Use locked dependencies.
- Run formatting, linting, typing and tests.
- Use minimal permissions.
- Verify action references against official sources and pin actions to immutable commit SHAs.
- Preserve the existing secret-scan workflow.
- Do not claim CI passed before an actual GitHub run.

DOCUMENTATION

- Update README with exact Windows-friendly setup, checking and startup commands.
- State what currently works and what remains planned.
- Add a concise packaging ADR explaining one distribution, prefixed packages and the nested layout.
- Identify this as M1a, with domain state machines and observability still pending.
- Update the prompt outcome note accurately before final verification.

HANDOFF

Review the intended diff and run git diff --check.

You may stage only files belonging to this milestone for inspection and run the staged Gitleaks scan with redaction. Do not commit or push.

Return:
- Starting and final Git state.
- Files added/changed and a concise explanation.
- Full new application code, pyproject.toml, CI workflow and tests.
- Lockfile dependency summary rather than its full contents.
- Actual commands, results and exit codes.
- Wheel-install/import smoke-check evidence.
- Real-server smoke-check evidence.
- Secret-scan result.
- Any remaining limitations or blocked checks.

Do not reproduce the full prompt history. Stop after this handoff.
````

**Outcome (pending review; staged for inspection, not committed or pushed):**
- Branch `feat/python-api-foundation` was created from `52acebd`, with a clean working tree.
- uv 0.13.0 was already installed. Python 3.12.15 was added with `uv python install 3.12 --no-bin --no-registry`, so there are no PATH shims or registry entries. The project environment uses 3.12.15. The existing Python 3.13 was left untouched.
- Added:
  - `pyproject.toml`: one Hatchling distribution, `requires-python >=3.12,<3.13`, separate runtime and dev dependencies.
  - `.python-version`, `uv.lock`.
  - `evidenceguard_domain.health.HealthStatus`.
  - `evidenceguard_api` with `create_app()`, `GET /healthz` and the `eg-api` Uvicorn entry point.
  - Tests, Ruff and strict Mypy configuration.
  - `.github/workflows/ci.yml` (Ubuntu and Windows, Python 3.12, actions pinned to commit SHAs).
  - ADR-0001 and README updates.
- Starlette deprecates using `httpx` with its test client, so the dev dependency is `httpx2`. pytest treats warnings as errors.
- **Verified locally** (Windows, Python 3.12.15), all exit 0:
  - `uv sync --locked`, `ruff check`, `ruff format --check`, `mypy` (strict) and `pytest` (10 passed), plus `uv build`.
  - The wheel was installed into a fresh environment under `.local/`. Both packages imported from `site-packages` with no source-tree paths on `sys.path`, and `eg-api --help` ran from that environment.
  - A real Uvicorn server returned HTTP 200 `{"status":"ok"}` on `/healthz`, then was stopped.
  - The full final check results are in the session handoff.
- **Not verified:** the CI workflow has not run on GitHub. Linux behaviour is checked only by that workflow.

**Review note (added with Prompt 8):** the external reviewer accepted the M1a application code, packaging configuration, tests and CI configuration for a local commit. The acceptance relies on the Windows verification reported above; the reviewer did not run local commands. GitHub Actions and Linux have not run.

---

## Prompt 8: Local M1a commit

- **Stage:** Commit of reviewed M1a work (no code changes, no push)
- **Date:** 2026-10-11 (session date)

````text
Create the local M1a commit from the reviewed implementation. Do not push or start the next milestone.

Inspect CLAUDE.md, Git root, branch, HEAD, status and staged diff first.

Expected:
- Root: D:\Claude\evidenceguard_agentic_rag
- Branch: feat/python-api-foundation
- HEAD: 52acebd1eb33946970a60549cc4366743687ce72
- Origin: https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git
- The 17 M1a files are staged, with no unrelated changes.

If the state differs, identify the difference and preserve existing work.

The external reviewer accepts the supplied application code, packaging configuration, tests and CI configuration for a local commit. This acceptance relies on the reported Windows verification; GitHub Actions and Linux have not run.

Append this prompt verbatim to prompts.md and add a separate review note recording that acceptance and its limits. Preserve historical prompt text and outcome notes.

Make no application-code or dependency changes.

Re-stage the authorized prompts.md update. Inspect the final staged paths and diff for accidental private content.

Run:
- git diff --cached --check
- gitleaks git --pre-commit --staged --redact --verbose .

The application checks already passed against the reviewed code. Do not rerun the full suite merely because prompt documentation changed. If code or configuration has changed since that verification, rerun the affected checks and report why.

If all required checks pass, create one local commit:

feat: add Python packaging and minimal health API

Do not amend, merge, change branches or push.

After committing:
- Run the full-history Gitleaks scan with redaction.
- Inspect the commit's file list.
- Confirm final Git status.
- If a check fails, stop and report it without exposing secrets or rewriting history.

Return:
- Commit SHA, branch and subject.
- Files committed and concise change summary.
- Verification results and exit codes.
- Final Git status.
- Confirmation that nothing was pushed.
````

**Outcome (pending review):**
- Only `prompts.md` changed: this prompt and the review note above. No application code, configuration or dependencies changed, so the application checks were not rerun.
- `prompts.md` was re-staged. `git diff --cached --check` and the Gitleaks staged scan were run before committing.
- One local commit was created on `feat/python-api-foundation`. The SHA and post-commit history scan are in the session handoff.
- Not pushed. GitHub Actions and Linux remain unverified.

---

## Prompt 9: M1b, evidence contracts and report-approval transitions

- **Stage:** Implementation, milestone M1b (staged for review, no commit)
- **Date:** 2026-10-11 (session date)

````text
Implement M1b only: essential typed evidence contracts and pure report-approval state transitions.

Inspect CLAUDE.md, docs/plan.md, the existing domain package, tests, Git status, branch, remotes and HEAD first.

Expected starting commit:
d196afc41734bfe14ea55f91632f99d9cb2e0a61

Expected root:
D:\Claude\evidenceguard_agentic_rag

Expected origin:
https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git

Preserve existing code. If the state differs, explain the difference before proceeding.

Append this prompt verbatim to prompts.md. From the clean current commit, create branch feat/evidence-contracts-approval.

SCOPE

Add contracts and pure domain behavior under evidenceguard_domain, with meaningful unit tests.

No database, authentication implementation, new API endpoints, worker, model calls, retrieval, observability package or frontend in this milestone. Preserve the existing API behavior.

Do not implement every entity from the plan. Introduce only what these contracts and approval transitions need.

1. Evidence contracts

Use Pydantic v2, explicit enums/literals, forbidden extra fields and appropriately immutable values.

Define small contracts for:
- Tenant/principal context, including actor ID and role.
- Bounded evidence question.
- Citation with tenant, document revision, chunk identity and nonempty quotation.
- Verification result.
- Risk finding.
- Report content composed from findings and unresolved questions.

Follow the approved evidence semantics:
- Verdict: supported, contradicted or insufficient evidence.
- Evidence status: vendor_claim, documentary_support, conflicting or missing.
- Authenticity: not_established in v1.

Explain and validate the permitted verdict/status combinations. Supported and contradictory assertions need citations. Missing evidence can still cite an incomplete policy, so do not require every insufficient-evidence result to have zero citations.

A citation contract does not itself establish authorization, quote membership, semantic support or document authenticity. Those checks belong to later components; state this plainly.

Keep relationships internally consistent:
- Findings reference known evidence questions.
- Report evidence belongs to the report's tenant.
- Cross-tenant references are rejected.
- Unsupported assertions cannot be represented as supported findings without citations.

Prefer typed fields over arbitrary dictionaries. Avoid creating a general-purpose compliance schema.

2. Immutable report revisions and content hashing

Define an immutable report revision and a small report state/aggregate sufficient for approval.

Use deterministic SHA-256 over explicitly defined canonical report content. Document exactly what is hashed.

- Stable serialization must not depend on incidental dictionary insertion order.
- A substantive content change changes the hash.
- Actor, timestamp and decision metadata should not accidentally alter the content hash.
- Bind decisions separately to tenant ID, report ID, revision number and content hash.
- Reject a supplied hash that does not match the actual content.

Do not introduce a mutable nested list/dictionary that can change content after hashing. Pydantic frozen=True is shallow; choose immutable collections or another explicit defensible approach.

Do not use model_copy(update=...) or similar bypasses to create invalid validated states.

3. Pure approval transitions

Implement small pure functions that return validated new state and do not mutate their inputs:

- Create draft revision.
- Approve an exact current revision.
- Reject an exact current revision.
- Revise from an expected current revision.
- Finalize an exact approved revision.
- Check export eligibility.

Use the approved states:
draft, changes_requested, approved, finalized.

Rules:
- The context tenant must match the report tenant.
- Only the approver role can approve, reject or finalize in this milestone. Do not invent an implicit admin approval bypass.
- Reviewer and approver roles may revise an unfinalized report.
- Approval/rejection requests must identify the current revision and matching hash.
- Revision changes invalidate the effective approval while preserving decision history.
- An approval for another report, tenant or revision cannot authorize finalization.
- Rejection removes any effective approval.
- Finalization requires a matching current approval.
- Finalized reports cannot be revised, rejected or otherwise changed.
- Export is allowed only for finalized reports.
- Repeated identical approval/finalization requests are idempotent where the state permits them.
- Invalid transitions produce explicit domain errors.
- Pure functions do not claim database atomicity or protection against concurrent requests. That enforcement comes with persistence.

Ensure callers cannot construct an apparently approved/finalized valid aggregate without the corresponding matching decision.

Keep approval history compact and typed. Do not add event sourcing or a workflow framework.

4. Meaningful tests

Cover:
- Valid supported, contradictory and insufficient evidence.
- Invalid verdict/status combinations.
- Claims lacking required citations.
- Cross-tenant evidence and report access.
- Stable hashes and substantive content changes.
- Resistance to nested mutation after revision creation.
- Approval of the exact current revision.
- Wrong revision, wrong hash and another report's approval.
- Reviewer attempts to approve/finalize.
- Approve → revise → finalize failing until the new revision is approved.
- Approve → reject preventing finalization.
- Finalization without approval.
- Finalized immutability and export eligibility.
- Idempotent repeated requests.
- Inputs remaining unchanged after transitions.
- Invalid approved/finalized aggregate construction.

Use behavior-focused tests. Avoid snapshotting incidental field ordering or hard-coding implementation details.

5. Documentation

Add initial docs/threat-model.md and docs/responsible-ai.md as concise drafts.

Distinguish:
- Domain invariants implemented and tested now.
- Authentication, database tenancy and atomic transitions not yet implemented.
- Semantic evidence validation and prompt-injection evaluation still pending.
- Human approval does not establish document authenticity or certify compliance.

Update README with M1b behavior and limitations. Preserve accurate M1a instructions.

Update the milestone record and prompt outcome note without rewriting historical prompts.

6. Verification and handoff

Run locked dependency sync, Ruff formatting/lint, strict Mypy and the test suite. Build and repeat the isolated wheel import check because the packaged domain code changed.

No new runtime dependencies should be necessary. Justify any dependency change explicitly.

Inspect the diff, stage only this milestone's files, run staged whitespace checking and the redacted staged Gitleaks scan.

Do not commit or push.

Return:
- Contract and state-transition design, including hashing and immutability choices.
- Full new/changed domain implementation.
- New tests and relevant configuration changes.
- Actual verification commands, results and exit codes.
- Files changed, staged paths and final Git status.
- Honest limitations.

Do not reproduce the entire prompts.md. Stop after the review handoff.
````

**Outcome (pending review; staged for inspection, not committed or pushed):**
- Branch `feat/evidence-contracts-approval` was created from `d196afc`, with a clean working tree.
- New in `evidenceguard_domain`:
  - `_base.DomainModel`: frozen models, tuple-only collections, extra fields forbidden, validating `model_copy`.
  - `context`: `ActorContext`; roles are reviewer and approver only.
  - `evidence`: questions, citations, verifications, findings and report content, with the verdict/status/citation rules.
  - `report`: canonical SHA-256 content hashing, immutable revisions, bound decisions and a status derived from history.
  - `approval`: pure transitions.
  - `errors`: explicit domain errors.
- Added tests for evidence, hashing and approval, plus shared fixtures. Added initial `docs/threat-model.md` and `docs/responsible-ai.md`. Updated the README and the M1 progress record in `docs/plan.md`.
- No dependency or API changes.
- **Verified locally** (Windows, Python 3.12.15): the locked sync, Ruff, strict Mypy, pytest, build and isolated wheel import check were run before staging. Results are in the session handoff.
- **Not verified:** GitHub Actions and Linux.

**Review note (added with Prompt 10):** the external review identified issues in the M1b work: the conflicting-evidence rule, report question coverage, and rejection and retry validation. They are corrected under Prompt 10 below. The M1b work above remains uncommitted.

---

## Prompt 10: M1b review corrections

- **Stage:** Corrections to staged M1b work (no commit, no push)
- **Date:** 2026-10-11 (session date)

````text
Correct the identified M1b issues and provide the complete review diff. Do not commit, push or start another milestone.

Inspect current repository instructions, status and staged changes. Expected branch is feat/evidence-contracts-approval, with HEAD d196afc41734bfe14ea55f91632f99d9cb2e0a61 and the M1b changes staged.

Preserve existing work and append this prompt verbatim to prompts.md.

1. Conflicting evidence within one chunk

Replace the requirement for two distinct chunk IDs with a requirement for at least two distinct evidence quotations.

Two different quotations from the same chunk may describe conflicting claims. Exact duplicate quotations from that chunk must not count twice.

Keep tenant consistency and duplicate-citation checks. Do not claim that counting quotations proves a semantic contradiction.

Add tests for:
- Two different quotations from one chunk accepted as structurally valid conflicting evidence.
- An exact duplicate citation not satisfying the requirement.
- A single quotation rejected.
- Different chunks continuing to work.

Update the relevant documentation.

2. Report question coverage

Every known report question must be accounted for by a finding or explicitly listed as unresolved. Reject silently omitted questions.

A finding with evidence_status=missing must not by itself make a question appear resolved: its referenced questions must also be listed as unresolved.

If a question requires_documentary_support and has only vendor_claim findings, it must remain unresolved. A vendor claim may still be shown as a finding.

Do not impose a blanket ban on a question appearing in both findings and the unresolved list; partial evidence can coexist with an unresolved question.

Add tests for these cases. Keep the schema small.

3. Consistent rejection validation

Require a nonblank comment whenever ApprovalDecision.decision is REJECT, including direct model construction.

Validate rejection inputs before returning an idempotent result. A repeated rejection with an invalid comment must not silently succeed.

Clarify repeated-decision behavior:
- An identical retry must preserve the original decision and attribution.
- A different actor or comment must not be described as an identical retry.
- Choose and document a narrow explicit behavior for such changed requests: reject the conflict or record another validated decision.
- Do not silently discard changed decision information.

Apply the same distinction to approval retries where relevant, and add behavior-focused tests.

4. Verify and provide review evidence

Run Ruff formatting/lint, strict Mypy and the full tests after these changes.

Rebuild and check the installed wheel because packaged domain behavior changed.

Update prompt outcome notes, stage only authorized M1b changes, and rerun staged whitespace checking and the redacted staged Gitleaks scan.

Return:
- What changed and why.
- Actual verification output and exit codes.
- The complete staged diff excluding prompts.md, including all domain code, test fixtures, tests and documentation.
- Final Git status.

If the diff is too long for one response, provide it in numbered parts or save it under .local/m1b-review.diff for me to bring to the external reviewer. Do not substitute test summaries for the test source.

Do not commit or push.
````

**Outcome (pending review; staged for inspection, not committed or pushed):**
- **Conflicting evidence** now needs at least two distinct quotations. Two different quotations from one chunk are accepted; identical text counts once; exact duplicate citations are still rejected. The docs state that this is structural, not proof of a contradiction.
- **Question coverage.** `ReportContent` now requires every question to be resolved by a finding or listed as unresolved:
  - a `missing` finding never resolves a question;
  - a `vendor_claim` does not resolve a question that requires documentary support;
  - a question may appear both in a finding and in the unresolved list.
- **Rejections.** `ApprovalDecision` requires a non-blank comment for every rejection, including direct construction.
- **Retries.** Decision inputs are validated before any retry is recognised:
  - an identical retry (same actor and comment) returns the report unchanged, with the original decision and time;
  - a changed approval, rejection or finalization raises the new `DecisionConflictError`.
- Five existing tests were adjusted only where their fixtures now violated the coverage rule or relied on the old two-chunk rule. New tests cover each rule. The threat model, responsible-AI notes and README were updated.
- **Verified locally** (Windows, Python 3.12.15): Ruff, strict Mypy, the full pytest suite, the build and the isolated wheel check were run before staging. Results are in the session handoff.
- The complete review diff, excluding `prompts.md`, is saved to the gitignored `.local/m1b-review.diff`.
- **Not verified:** GitHub Actions and Linux.

---

## Prompt 11: M1b coverage fix for missing-evidence findings

- **Stage:** Narrow correction to staged M1b work (no commit, no push)
- **Date:** 2026-10-11 (session date)

````text
Fix one remaining M1b report-coverage issue. Do not commit or push.

Inspect the current staged work and repository instructions. Stay on feat/evidence-contracts-approval and preserve existing changes. Append this prompt verbatim to prompts.md.

In ReportContent, the current coverage check accepts a question whenever any finding resolves it. Consequently, a question with both a supported finding and a missing-evidence finding can omit its unresolved entry.

Correct this narrowly:
- Every question referenced by any finding with evidence_status=MISSING must appear in unresolved_question_ids, even when another finding supports that question.
- Preserve the existing rules for omitted questions and questions requiring documentary support.
- Continue allowing supported findings and unresolved entries to coexist.
- Do not change the schema or approval behavior.

Add regression tests:
1. Supported and missing findings for the same question, without an unresolved entry: rejected.
2. The same findings with the unresolved entry: accepted.
3. A missing finding referencing multiple questions: every referenced question must be listed as unresolved, including any that also has supported evidence.

Update the coverage documentation to state this rule accurately.

Run formatting, lint, strict typing and the full test suite. Rebuild the wheel and repeat the isolated domain import check.

Update the outcome note, re-stage only the authorized files, and run staged whitespace checking and the redacted staged Gitleaks scan.

Return:
- The incremental diff against the previously supplied M1b review, including implementation, tests and documentation.
- Actual verification output and exit codes.
- Final Git status.

Do not resend the entire 2,314-line diff. Do not commit or push.
````

**Outcome (pending review; staged, not committed or pushed):**
- `ReportContent` now requires every question named by any `missing` finding to be listed in `unresolved_question_ids`, even when another finding supports it. The rules for omitted questions and questions requiring documentary support are unchanged. Supported findings and unresolved entries can still coexist. No schema or approval changes.
- Added three regression tests. Two of them were confirmed to fail against the previous implementation and pass with the fix; the third is an acceptance case that passes under both.
- The coverage wording in `evidence.py`, the threat model, the responsible-AI notes and the README was updated.
- **Verified locally** (Windows, Python 3.12.15): Ruff, strict Mypy, the full pytest suite, the build and the isolated wheel check were run before staging. Results are in the session handoff.
- **Not verified:** GitHub Actions and Linux.

**Review note (added with Prompt 12):**
- The external reviewer accepted M1b for a local commit after reviewing the supplied implementation and the incremental coverage fix.
- The acceptance relied on Claude's reported Windows verification, including 109 passing tests. The reviewer did not run those commands independently.
- Linux and GitHub Actions remain unverified.

---

## Prompt 12: Local M1b commit

- **Stage:** Commit of reviewed M1b work (no code changes, no push)
- **Date:** 2026-10-11 (session date)

````text
Commit the reviewed M1b implementation locally.

Work only in `D:\Claude\evidenceguard_agentic_rag`. Do not push, merge, amend commits, change branches, modify global configuration, or begin the next milestone.

1. Verify the starting state:
   - Git root is this project.
   - Branch is `feat/evidence-contracts-approval`.
   - HEAD is `d196afc41734bfe14ea55f91632f99d9cb2e0a61`.
   - Origin is `https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git`.
   - Exactly the previously reported 15 M1b files are staged, with nothing unstaged or untracked.
   If anything differs, stop and report it.

2. Append this prompt verbatim to `prompts.md` using the next sequential prompt number. Add a separate review note recording:
   - The external reviewer accepted M1b for a local commit after reviewing the supplied implementation and incremental coverage fix.
   - Acceptance relied on Claude’s reported Windows verification, including 109 passing tests.
   - The reviewer did not run those commands independently.
   - Linux and GitHub Actions remain unverified.
   Preserve all earlier prompts and outcome notes.

3. Make no application, dependency, configuration, or test changes. Stage the prompt-history update alongside the existing reviewed files.

4. Inspect the staged paths and check for secrets and private content without displaying credential values. Run:
   - `git diff --cached --check`
   - `gitleaks git --pre-commit --staged --redact --verbose .`

   Stop if either check fails. Application checks need not be repeated if only `prompts.md` changed since the successful verification.

5. Create one local commit with subject:
   `feat: add evidence contracts and revision-bound approval gate`

6. Run the full-history secret scan:
   `gitleaks git --redact --verbose .`

7. Report the commit SHA, branch, committed paths, check results, and final Git status. State explicitly that nothing was pushed. If a post-commit check fails, report it without amending or rewriting history.
````

**Outcome (pending review):**
- Only `prompts.md` changed: this prompt and the review note above. No application, dependency, configuration or test changes, so the application checks were not rerun.
- `git diff --cached --check` and the Gitleaks staged scan were run before committing.
- One local commit was created on `feat/evidence-contracts-approval`. The SHA and post-commit history scan are in the session handoff.
- Not pushed. Linux and GitHub Actions remain unverified.

---

## Prompt 13: M1c, API observability and consistent error responses

- **Stage:** Implementation, milestone M1c (staged for review, no commit)
- **Date:** 2026-10-11 (session date)

````text
Implement M1c only: API observability and consistent error responses.

Work in `D:\Claude\evidenceguard_agentic_rag`. Read `CLAUDE.md`, `docs/plan.md`, the existing API, tests, packaging configuration and CI workflow first. Keep work within this project.

Do not commit, push, merge, change global configuration, install system tools, or implement later milestones.

Starting state
- Branch: `feat/evidence-contracts-approval`
- HEAD: `da108e5a4e87ae1afcc9acd818a6ee3fe4d1e564`
- Origin: `https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git`
- Clean working tree.

Verify these before changing anything. If they differ, stop and report the difference. Create `feat/api-observability` from this HEAD.

Scope

1. Request IDs
- Associate each request with a request ID.
- Accept an incoming `X-Request-ID` only when it is a valid UUID; normalize it. Otherwise generate a fresh UUID.
- Return `X-Request-ID` on successful and error responses, including unexpected server errors.
- Make the ID available to handlers and logging without leaking context across concurrent requests.
- Treat it only as a correlation identifier, never as authentication or evidence of identity.

2. Structured logging
- Use a small standard-library implementation unless the existing plan justifies a dependency.
- Emit JSON request-completion logs containing the request ID, HTTP method, route template where available, response status and elapsed time.
- Avoid logging raw URL paths when no route matches. Do not log query strings, bodies, headers, credentials, evidence quotations, or validation input values.
- Do not expose exception messages or tracebacks in public responses. Keep default logs free of arbitrary exception text.
- Avoid duplicate handlers or duplicate completion logs when multiple app instances are created.
- Do not add telemetry services or claim production monitoring.

3. Consistent errors
- Implement `application/problem+json` responses following the relevant standard and current FastAPI/Starlette public APIs.
- Handle HTTP errors, request-validation failures and unexpected exceptions.
- Include the same request ID in the response header and problem body.
- Return useful, bounded validation details without echoing submitted input, arbitrary exception text or sensitive context.
- Preserve HTTP status codes and required exception headers.
- Unexpected errors return a generic 500 response.
- Keep `/healthz` success behaviour unchanged. Do not expose domain approval operations as new endpoints.
- Do not suppress unexpected exceptions merely to make tests pass.

4. Tests
Add focused tests for:
- Generated, accepted and invalid incoming request IDs.
- IDs on success, 404, validation failure and unexpected 500 responses.
- Concurrent requests retaining their own IDs.
- Correct problem content type, status and preserved required headers.
- Sensitive submitted values and exception messages absent from public errors and default logs.
- Structured completion logs and no duplicate logging across app instances.

Use test-only routes where needed; do not add diagnostic endpoints to the application.

5. Documentation and prompt history
- Add ADR-0002 explaining request-ID handling, logging choices, error format and privacy limits.
- Update README and milestone status accurately.
- Append this entire prompt verbatim to `prompts.md` using the next sequential number, with a separate truthful outcome note. Preserve earlier entries.
- Check the existing plan for M1c-specific requirements. Report material conflicts instead of silently redesigning the plan.

Verification
Run locked dependency sync, Ruff formatting and lint checks, strict Mypy, the full test suite, package build, and isolated wheel-import verification. Run staged whitespace checks and the staged redacted Gitleaks scan.

Stage only intended M1c files. Leave everything uncommitted.

Handoff
Report changed paths, design decisions, exact verification commands and results, and final Git status. State what remains unverified.

Provide the complete staged diff excluding `prompts.md`. If too large to paste, save it under the already gitignored `.local/` directory and give me its path so I can bring it to the reviewer. Never truncate the review diff or stage that local artifact.

Nothing should be committed or pushed.
````

**Outcome (pending review; staged, not committed or pushed):**
- Branch `feat/api-observability` was created from `da108e5`, with a clean working tree.
- Added the planned `evidenceguard_observability` package (`context.py`, `jsonlog.py`), standard library only. Added `RequestContextMiddleware` (`middleware.py`) and problem+json handlers (`problems.py`) to the API. `eg-api` now runs Uvicorn with the JSON logging config and with the access log disabled.
- `/healthz` success behaviour is unchanged, apart from the added `X-Request-ID` header. No new application endpoints; the tests use test-only routes.
- **Plan conflicts, reported and resolved narrowly:**
  - The plan reserved ADR-0002 for the plain-Python workflow. As this prompt instructs, ADR-0002 now records the observability decisions, and the workflow ADR is renumbered ADR-0003 in `docs/plan.md`.
  - The plan's "logs redact secrets" is met by an allowlist formatter rather than pattern redaction.
- `pyproject.toml` registers the new package for the wheel, sdist, Ruff and Mypy. No dependency or lockfile changes.
- The first staged Gitleaks scan **failed**. Rule `generic-api-key` flagged the synthetic, key-shaped test marker in `tests/test_problems.py` and `tests/test_logging.py`. It was replaced with an obviously fake, low-entropy marker rather than allowlisted, and the checks were rerun.
- **Verified locally** (Windows, Python 3.12.15): the locked sync, Ruff, strict Mypy, the full pytest suite, the build, the isolated wheel check and real-server smoke checks were run before staging. Results are in the session handoff.
- **Not verified:** GitHub Actions and Linux.

**Review note (added with Prompt 14):** the external reviewer inspected the M1c diff and found two privacy issues:
- `JsonFormatter` wrote log messages verbatim;
- `HTTPException.detail` strings were published automatically.

The reviewer reproduced the formatter leak in isolation but did not run the full application suite. Both issues are corrected under Prompt 14 below. The M1c work remains uncommitted.

---

## Prompt 14: M1c privacy fixes

- **Stage:** Corrections to staged M1c work (no commit, no push)
- **Date:** 2026-10-11 (session date)

````text
Fix the two M1c privacy findings before committing.

Remain in `D:\Claude\evidenceguard_agentic_rag`, on `feat/api-observability`, with HEAD `da108e5a4e87ae1afcc9acd818a6ee3fe4d1e564`. Preserve the existing staged implementation. Do not commit, push, change branches, or modify global configuration.

1. Close the unrestricted log-message path.
- JsonFormatter currently writes record.getMessage() verbatim as "event". This bypasses the structured-field allowlist.
- Emit reviewed, fixed event identifiers. Unknown messages must become a generic fixed identifier without copying their message, arguments, exception text or traceback.
- Apply this protection to both EvidenceGuard and Uvicorn records handled by this formatter.
- Keep useful safe fields and existing request-completion behaviour. Do not replace this with heuristic secret-pattern matching.
- Correct documentation claiming third-party messages are safe because they use fixed templates.

Add regression tests showing that:
- A directly embedded sensitive marker is absent from formatted output.
- A marker supplied through logging interpolation arguments is absent.
- An exception interpolated into a message is absent, even without exc_info.
- The fixed request.completed event and its safe fields remain intact.

2. Make HTTP problem details explicitly safe.
- Do not automatically publish arbitrary HTTPException.detail strings.
- Ordinary HTTP exceptions should receive generic public details while preserving status and required headers.
- If useful application-specific messages remain supported, provide an explicit mechanism for reviewed public messages. Document that submitted values and internal exception text must never enter it.
- Update the existing authentication-detail test to reflect the chosen mechanism.

Add a test-only route that raises HTTPException with a submitted marker in its string detail. Verify that the marker is absent from the response while status, problem content type, request ID and required headers remain correct.

3. Update README, ADR-0002 and the threat model to describe the actual guarantees and remaining limits accurately. Avoid absolute claims extending to logging handlers outside this configuration.

Append this prompt verbatim to prompts.md with the next sequential number. Add a separate review note explaining that the reviewer inspected the diff and reproduced the formatter leak in isolation, but did not run the full application suite. Record the fixes and verification truthfully without changing earlier history.

Run formatting, lint, strict Mypy, the full test suite, build and isolated installed-wheel checks. Run staged whitespace and redacted secret scans.

Leave intended changes staged and uncommitted. Provide the complete incremental diff against the previously reviewed M1c staged version, excluding prompts.md, plus verification results and final status. Save the untruncated diff under gitignored .local/ if needed; do not stage it.

Nothing should be committed or pushed.
````

**Outcome (pending review; staged, not committed or pushed):**
- **Logging.** `JsonFormatter` no longer formats record messages.
  - `event` is looked up from a reviewed table keyed by the unformatted template. The table holds `request.completed` and Uvicorn 0.54's lifecycle templates.
  - Anything else becomes `log.unreviewed_message`. Message text, arguments and interpolated exceptions are never written, for EvidenceGuard and Uvicorn records alike.
  - Safe allowlisted fields are unchanged. No pattern-based secret matching was added.
- **HTTP errors.**
  - Ordinary `HTTPException` details are replaced with a generic sentence for the status class; status and headers are preserved.
  - Specific messages now require `PublicHTTPException` with a member of the reviewed `PublicMessage` enum (only `AUTHENTICATION_REQUIRED` so far). The authentication test was updated to use it.
  - A test-only route raises `HTTPException` with submitted input in its detail; the input does not reach the response.
- ADR-0002, the threat model and the README were updated. They now scope the logging guarantees to records rendered through `logging_config()`, and no longer claim that third-party messages are safe.
- **Verified locally** (Windows, Python 3.12.15):
  - The new and updated tests were run against the previously staged implementation: 13 failed and showed the leaks. With the fix, all pass.
  - Ruff, strict Mypy, the full pytest suite, the build, the isolated installed-wheel check, a real-server smoke check and the staged scans were run before staging. Results are in the session handoff.
- **Not verified:** GitHub Actions and Linux.

**Review note (added with Prompt 15):**
- The external reviewer inspected the original and incremental M1c diffs and accepted both privacy corrections for a local commit.
- The reviewer reproduced the original formatter leak in isolation, but did not independently run the revised application suite.
- The acceptance also relied on Claude's reported Windows verification of 155 passing tests.
- Linux and GitHub Actions remain unverified.

---

## Prompt 15: Local M1c commit and review-handoff guidance

- **Stage:** Commit of reviewed M1c work, plus a `CLAUDE.md` workflow update (no application changes, no push)
- **Date:** 2026-10-11 (session date)

````text
Commit the reviewed M1c implementation locally.

Work only in `D:\Claude\evidenceguard_agentic_rag`. Do not push, merge, amend commits, change branches, modify global configuration, or begin another milestone.

1. Verify the starting state:
- Branch: `feat/api-observability`
- HEAD: `da108e5a4e87ae1afcc9acd818a6ee3fe4d1e564`
- Origin: `https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git`
- The expected 18 M1c files are staged, with nothing unstaged or untracked.
- No `.local/` artifacts are staged.

Stop and report any difference.

2. Append this entire prompt verbatim to `prompts.md` using the next sequential number. Add a separate review note recording:
- The external reviewer inspected the original and incremental M1c diffs and accepted both privacy corrections for a local commit.
- The reviewer reproduced the original formatter leak in isolation, but did not independently run the revised application suite.
- Acceptance also relied on your reported Windows verification of 155 passing tests.
- Linux and GitHub Actions remain unverified.

Preserve all earlier prompts and outcome notes. Make no application, test, dependency or configuration changes.

3. Record our review handoff preference in the existing workflow guidance in `CLAUDE.md`:
- Future implementation handoffs must include the complete staged diff, excluding `prompts.md`, directly in the response inside fenced `diff` blocks.
- Future correction handoffs must include the complete incremental diff against the previously reviewed staged version, excluding `prompts.md`.
- Never truncate or replace the diff with a summary. Split large diffs into numbered parts at file boundaries and provide all parts.
- Include verification results and Git status separately.
- Attachments are a fallback if response limits prevent providing the complete diff.
- Implementation and correction work remains staged and uncommitted until reviewed. Commit and push require explicit authorization.

Keep this edit narrow and consistent with existing instructions. This prompt authorizes the local commit below only.

4. Stage the `prompts.md` and `CLAUDE.md` updates alongside the reviewed M1c files. Inspect staged content for secrets and private material without displaying credential values.

Run:
- `git diff --cached --check`
- `gitleaks git --pre-commit --staged --redact --verbose .`

Stop if either check fails. Application checks need not be repeated if only these documentation files changed since the successful verification.

5. Create one local commit with subject:
`feat: add request correlation and privacy-safe API observability`

6. Run the full-history secret scan:
`gitleaks git --redact --verbose .`

If a post-commit check fails, report it without amending or rewriting history.

7. In your final response:
- Report the commit SHA, branch, committed paths, check results and final Git status.
- Include the complete `CLAUDE.md` diff introduced in this step in a fenced `diff` block. The previously reviewed application diff need not be repeated.
- Summarize the appended prompt-history entries separately.
- State explicitly that nothing was pushed.

Nothing should be pushed or merged.
````

**Outcome (pending review):**
- Only `prompts.md` (this prompt and the review note above) and `CLAUDE.md` changed. `CLAUDE.md` gained a "Review handoffs" section, and its commit rule now keeps work staged until reviewed. No application, test, dependency or configuration changes, so the application checks were not rerun.
- `git diff --cached --check` and the Gitleaks staged scan were run before committing.
- One local commit was created on `feat/api-observability`. The SHA and post-commit history scan are in the session handoff.
- Not pushed. Linux and GitHub Actions remain unverified.

---

## Prompt 16: ADR-0003, plain-Python workflow

- **Stage:** Documentation, remaining M1 architecture record (staged for review, no commit)
- **Date:** 2026-10-11 (session date)

````text
Implement the remaining M1 documentation task: ADR-0003 for the plain-Python workflow.

Work only in `D:\Claude\evidenceguard_agentic_rag`. Read `CLAUDE.md`, `docs/plan.md`, existing ADRs and README first.

Do not commit, push, merge, modify global configuration, install tools, or implement later milestones.

Verify the starting state:
- Branch: `feat/api-observability`
- HEAD: `32b1cc630ddef1296f5d8a59eedac0197dbf5bc5`
- Origin: `https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git`
- Clean working tree.

Stop and report any difference. Create `docs/plain-python-workflow` from this HEAD.

1. Add `docs/decisions/0003-plain-python-workflow.md`.

Document the workflow already approved in the plan, without introducing a new architecture:
- Plain Python orchestration with explicit, bounded transitions.
- Deterministic planning and report rendering.
- Model-driven verification and risk analysis with structured contracts.
- PostgreSQL-backed durable jobs and persistent workflow state when those milestones arrive.
- Retry limits, idempotency, failure handling and human approval bound to the exact report revision and content hash.
- Why a dedicated agent framework is unnecessary for the initial scope.
- Alternatives considered, tradeoffs, and concrete conditions that would justify reconsidering the decision.

Clearly distinguish what is implemented today from planned orchestration and persistence. Do not invent guarantees about crash recovery, concurrency, provenance or evaluation.

2. Update README and docs/plan.md narrowly:
- Link ADR-0003.
- Record that the remaining M1 architecture documentation is under review.
- Keep Linux and GitHub Actions explicitly unverified.
- Do not declare M1 acceptance complete while its CI requirement remains unmet.

3. Append this entire prompt verbatim to prompts.md using the next sequential number, with a separate truthful outcome note. Preserve earlier entries.

4. Verify the documentation links and consistency with the approved plan and current implementation. Inspect the staged content for secrets and private material without displaying credential values. Run:
- `git diff --cached --check`
- `gitleaks git --pre-commit --staged --redact --verbose .`

Application tests and package builds need not be rerun for documentation-only changes.

Stage only the intended documentation files. Leave everything uncommitted.

In your final response, include the complete staged diff excluding prompts.md directly inside fenced diff blocks. Never truncate or replace it with a summary. If necessary, split it into numbered parts at file boundaries and provide every part.

Report verification results, staged paths and final Git status separately. Summarize prompt-history additions. State explicitly that nothing was committed or pushed.
````

**Outcome (pending review; staged, not committed or pushed):**
- Branch `docs/plain-python-workflow` was created from `32b1cc6`, with a clean working tree.
- Added `docs/decisions/0003-plain-python-workflow.md`. It records plan decisions D4–D7 and D9 and corrections B and E without new architecture, and separates what is implemented (M1b contracts and pure approval transitions, M1c observability) from what is planned (stages, PostgreSQL jobs, fencing, snapshots, provider calls). It makes no crash-recovery, concurrency, provenance or evaluation claims.
- `docs/plan.md` and `README.md` now link ADR-0003, mark it as under review, and state that M1 acceptance is incomplete because CI has not run. Linux and GitHub Actions remain unverified. The plan's M1c entry now records its local commit `32b1cc6`.
- **Consistency note:** the plan names the Verifier's field `assessment`, while the implemented contract uses `verdict`. The ADR uses `verdict`; the plan text was not changed.
- Documentation only, so the application tests and build were not rerun. The relative-link check, the staged whitespace check and the staged Gitleaks scan were run; results are in the session handoff.

**Review note (added with Prompt 17):** the external reviewer reviewed the staged ADR-0003 diff and requested two documentation corrections:
- use `verdict` in the plan where it describes the implemented Verifier output;
- correct the ADR's framework rationale, which mischaracterised graph frameworks.

The ADR remains under review and M1 acceptance remains pending.

---

## Prompt 17: ADR-0003 documentation corrections

- **Stage:** Corrections to staged documentation (no commit, no push)
- **Date:** 2026-10-11 (session date)

````text
Make two narrow documentation corrections to the staged ADR-0003 work.

Work only in `D:\Claude\evidenceguard_agentic_rag`, on `docs/plain-python-workflow`, with HEAD `32b1cc630ddef1296f5d8a59eedac0197dbf5bc5`.

Preserve the existing staged documentation. Do not commit, push, change branches, change application code, or implement later milestones.

1. Reconcile `assessment` versus `verdict`.
- Where docs/plan.md describes the implemented Verification output field, use `verdict`, matching the domain contract.
- Do not replace unrelated uses of “assessment”.
- Record this naming clarification without changing the contract or architecture.

2. Correct the framework rationale in ADR-0003.
- Remove the claim that a graph runtime’s main feature is model-driven routing.
- Acknowledge that graph frameworks can support fixed workflows, persistence and human intervention.
- Explain the project-specific choice: the initial bounded workflow can be expressed directly in Python, with explicit PostgreSQL state and fewer dependencies.
- Retain the tradeoff that we must implement and test job recovery, stage resumption and fencing ourselves.
- Describe explicit storage as our chosen approach; do not claim framework checkpoint storage is inherently opaque or must duplicate our state.
- Preserve the existing reconsideration criteria and distinction between implemented and planned behaviour.

Leave the ADR under review and M1 acceptance pending. Linux and GitHub Actions remain unverified.

Append this prompt verbatim to prompts.md using the next sequential number. Add a separate truthful review and outcome note. Preserve earlier history.

Check documentation links and consistency. Stage only intended documentation changes, then run:
- `git diff --cached --check`
- `gitleaks git --pre-commit --staged --redact --verbose .`

No application tests or build are needed for documentation-only changes.

Include the complete incremental diff against the previously reviewed staged version, excluding prompts.md, directly in fenced diff blocks. Do not truncate or summarize it; split into numbered parts at file boundaries if necessary.

Report checks, staged paths and final Git status separately. Leave everything staged and uncommitted. Nothing should be pushed.
````

**Outcome (pending review; staged, not committed or pushed):**
- **`docs/plan.md`:** every reference to the Verifier's output field now says `verdict`, matching the implemented `Verification` contract. That covers the field definition, the status-derivation table, the model-judgment row and the evidence endpoint description. A naming-clarification note was added to the M1 progress record. The contract and architecture are unchanged.
- **ADR-0003:** the framework rationale was rewritten. It now:
  - acknowledges that graph frameworks support fixed workflows, persistence and human intervention;
  - presents plain Python with explicit PostgreSQL state and fewer dependencies as a project-specific choice;
  - keeps the tradeoff that job recovery, stage resumption and fencing must be built and tested in-house.

  The claims that model-driven routing is a graph runtime's main feature and that framework checkpoints are opaque duplicates were removed, including from the alternatives table. The status, the implemented-versus-planned table and the reconsideration criteria are unchanged.
- The ADR stays under review and M1 acceptance stays pending. Linux and GitHub Actions remain unverified.
- Documentation only, so no tests or build were run. The link check, the staged whitespace check and the staged Gitleaks scan were run; results are in the session handoff.

**Review note (added with Prompt 18):** the external reviewer accepted the original ADR-0003 documentation and both incremental corrections for a local commit. The acceptance was based on inspecting the supplied diffs and on Claude's reported documentation checks; the reviewer did not run those checks independently. M1 acceptance remains pending because Linux and GitHub Actions are unverified.

---

## Prompt 18: Local ADR-0003 commit

- **Stage:** Status updates and commit of reviewed documentation (no application changes, no push)
- **Date:** 2026-10-11 (session date)

````text
Commit the reviewed ADR-0003 documentation locally.

Work only in `D:\Claude\evidenceguard_agentic_rag`. Do not push, merge, amend, change branches, modify global configuration, or begin another milestone.

Verify:
- Branch: `docs/plain-python-workflow`
- HEAD: `32b1cc630ddef1296f5d8a59eedac0197dbf5bc5`
- Origin: `https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git`
- Exactly these four files are staged, with nothing unstaged or untracked:
  - README.md
  - docs/decisions/0003-plain-python-workflow.md
  - docs/plan.md
  - prompts.md

Stop and report any difference.

The external reviewer has accepted the original documentation and both incremental corrections for a local commit.

Make these narrow status updates:
- Mark ADR-0003 as accepted.
- Update its README and plan references from “under review” to accepted.
- Keep M1 acceptance explicitly pending because Linux and GitHub Actions remain unverified.
- Do not change architecture, application code or other milestone requirements.

Append this entire prompt verbatim to prompts.md using the next sequential number. Add a separate review note recording acceptance based on inspection of the supplied diffs and your reported documentation checks. Preserve earlier history.

Stage the documentation updates. Check relative links and inspect staged content for secrets and private material without displaying credential values.

Run:
- `git diff --cached --check`
- `gitleaks git --pre-commit --staged --redact --verbose .`

If checks pass, create one local commit:
`docs: record plain Python workflow architecture`

Then run:
`gitleaks git --redact --verbose .`

Report the commit SHA, committed paths, checks and final Git status. Include the complete incremental documentation diff introduced in this step, excluding prompts.md, directly in fenced diff blocks. Never truncate it; split into numbered parts if necessary.

Application tests and builds are unnecessary for these documentation-only changes. If a post-commit check fails, report it without rewriting history.

State explicitly that nothing was pushed or merged.
````

**Outcome (pending review):**
- ADR-0003 is marked accepted, and its README and plan references now say accepted. M1 acceptance remains explicitly pending because Linux and GitHub Actions are unverified. No architecture, application or milestone-requirement changes.
- Documentation only, so no tests or build were run. The relative-link check, the staged whitespace check and the staged Gitleaks scan were run before committing.
- One local commit was created on `docs/plain-python-workflow`. The SHA and post-commit history scan are in the session handoff.
- Not pushed or merged.

---

## Prompt 19: Pre-publication inspection

- **Stage:** Read-only publication readiness check; only this prompt-history entry is staged (no commit, no push)
- **Date:** 2026-10-11 (session date)

````text
Prepare the reviewed repository for its first GitHub publication. Do not push yet.

Work only in `D:\Claude\evidenceguard_agentic_rag`. Read CLAUDE.md first. Do not change application code, dependencies, workflows, branches, global configuration or Git history.

Verify:
- Branch: `docs/plain-python-workflow`
- HEAD: `48872f41fad88c8eef40402e3be34d42fe864f84`
- Origin: `https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git`
- Clean working tree.
- History contains the five reviewed commits.
- `git ls-remote origin` still shows no refs.

Stop and report unexpected differences.

1. Inspect `.github/workflows/ci.yml` and `secret-scan.yml`.
- Include both complete files in your response.
- Explain whether a first push to `main` would trigger both workflows.
- Identify the configured operating systems, checks and workflow permissions.
- Report any publication blocker without changing the workflows.

2. Inspect the tracked file list and full Git history for secrets and unintended private content.
- Run `gitleaks git --redact --verbose .`.
- Check for tracked environment files, credentials, local artifacts, logs, database files and build outputs.
- Do not display credential values.
- Distinguish intentionally recorded local paths in verbatim prompts from accidental private content.

3. Inspect local branch refs and whether GitHub CLI is available.
- Do not install tools or initiate authentication.
- Do not print tokens or credential configuration.
- Report whether local `main` exists and its commit, if any.

4. Propose the exact commands to publish the reviewed history as remote `main`, preserving all commits.
- Account for the actual local branch state.
- Do not use force push, rebase or amend.
- Do not execute the publication commands.
- Note that subsequent work will still be reviewed here before pushing.

5. Append this entire prompt verbatim to prompts.md using the next sequential number, with a truthful outcome note. Preserve earlier history. Stage only this prompt-history update.

Run staged whitespace and redacted secret checks. Leave the update uncommitted.

Report results, the proposed publication commands and final Git status. If any other change becomes necessary, provide its complete proposed diff directly in fenced diff blocks for review.

Nothing should be committed, pushed or merged.
````

**Outcome (pending review; only this entry staged; nothing committed, pushed or merged):**
- **State verified:** branch `docs/plain-python-workflow` at `48872f4`, a clean tree, five linear reviewed commits, and an empty remote (no refs).
- **Branches:** no local `main`. The five local branches point at the five commits. Local Git config still holds a `branch.main` upstream (`origin`, `refs/heads/main`) left over from the original clone.
- **Tooling and remote:** the GitHub CLI is not installed. An unauthenticated read of GitHub's public metadata shows the repository is **public** and empty.
- **Workflows:** both `ci.yml` and `secret-scan.yml` trigger on every `push` (no branch filter), `pull_request` and `workflow_dispatch`, with `contents: read` permissions. Neither has run yet.
- **Secrets and artifacts:** the full-history Gitleaks scan found no leaks. No credential patterns or email addresses appear in any commit's content. No environment, key, log, database, build, cache or `.local/` files were ever tracked: 45 paths, all of them current.
- **Local paths:** the 16 in `prompts.md` are all inside verbatim prompt text (15 are the project path; 1 is the Claude plan-storage path quoted in Prompt 2). They are intentional records, not accidental content.
- **For the user to decide before publishing:**
  - every commit's author and committer address is a personal email, which becomes public on push;
  - `docs/plan.md` describes the development laptop's hardware in general terms;
  - nothing was changed for either, and changing the commit email would require rewriting history.
- Proposed publication commands are in the session handoff; none were run. The staged whitespace check and the staged Gitleaks scan were run on this entry.

---

## Prompt 20: Commit email privacy rewrite

- **Stage:** Authorized metadata-only rewrite of unpublished history, plus one prompt-history commit (no push, no merge)
- **Date:** 2026-10-11 (session date)

````text
Replace my personal email in this repository’s unpublished commit history with:

257921624+mathewmljourney93@users.noreply.github.com

I explicitly authorize this metadata-only history rewrite and one local prompt-history commit. Do not push or merge.

Work only in `D:\Claude\evidenceguard_agentic_rag`. Read CLAUDE.md first. Do not modify global Git configuration, install tools, or change application code.

1. Verify the starting state:
- Branch: `docs/plain-python-workflow`
- HEAD: `48872f41fad88c8eef40402e3be34d42fe864f84`
- Origin: `https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git`
- Exactly prompts.md is staged from the publication preflight, with nothing unstaged or untracked.
- Remote still has no refs.
- Five commits form the reviewed linear history:
  `52acebd` → `d196afc` → `da108e5` → `32b1cc6` → `48872f4`

Verify the existing local branches and their commit positions. Stop and report unexpected differences.

2. Create a recovery backup inside gitignored `.local/`:
- A Git bundle containing the original local branches and history.
- A copy of the staged prompts.md changes.
- Verify that the bundle is valid.
- Do not create backup branches or tags that could accidentally be published.
- The backup contains the old email, so keep it local and never stage or upload it.

3. Set repository-local `user.email` to the noreply address above. Leave user.name and global configuration unchanged.

4. Rewrite only the author and committer email addresses in the five reviewed commits.
- Preserve each commit’s exact file tree, full message, author and committer names, timestamps and timezone offsets.
- Preserve the Claude co-author trailers.
- Preserve the linear parent relationships using the rewritten parent SHAs.
- Use a controlled Git plumbing method with the tools already available; do not install a history-rewriting utility.
- Update all five existing local branch tips to their corresponding rewritten commits.
- Use expected-old-SHA checks when updating refs.
- Preserve the staged prompts.md changes throughout. Do not use a destructive reset or discard any working-tree content.

5. Verify every old/new commit pair:
- File-tree IDs are identical.
- Full commit messages are identical.
- Names and dates are identical.
- Both author and committer emails use the supplied noreply address.
- Parent relationships match the original history.
- All existing branch tips point to their correct rewritten counterparts.

Do not replace historical SHAs inside prompts.md or docs. They truthfully describe the commits that existed at that time. Add an old-to-new SHA mapping as a separate migration note.

6. Append this entire prompt verbatim to prompts.md using the next sequential number. Preserve the staged preflight entry and all earlier history.

Add a truthful outcome note recording the privacy rewrite, backup location, verification results and SHA mapping. Do not record checks as passed before running them.

Inspect and stage only prompts.md. Run:
- `git diff --cached --check`
- `gitleaks git --pre-commit --staged --redact --verbose .`
- `gitleaks git --redact --verbose .`

Stop on failure. If checks pass, create one local commit:
`docs: record publication preflight and commit email privacy migration`

Run the full-history redacted secret scan again after this commit.

7. Report:
- The five old-to-new SHA mappings.
- The new prompt-history commit SHA.
- Verification that the original file trees and messages were preserved.
- Repository-local email configuration.
- Branch tips, check results and final Git status.
- Confirmation that the remote is still empty.

Include any changes outside prompts.md as a complete fenced diff. None are expected. Summarize prompt-history additions separately.

Application tests and builds are unnecessary because application content must remain identical.

Do not push, merge, amend further, delete the recovery backup, or begin another milestone. If anything fails, report the state without improvising another history rewrite.
````

**Outcome (pending review; local only, not pushed or merged):**
- **Starting state verified:** branch, HEAD `48872f4`, origin, only `prompts.md` staged, an empty remote, five linear commits, the five branch tips at their expected commits, and no tags or stash.
- **Recovery backup** in the gitignored `.local/backup-email-rewrite/`:
  - `pre-email-rewrite.bundle`: all five original branches; `git bundle verify` reported it valid with complete history;
  - `prompts.md.staged` and `prompts.md.staged.diff`: the staged preflight entry;
  - `original-branch-tips.txt`, plus the rewrite and verification scripts.

  The backup contains the old email. It is not tracked or staged and must not be uploaded.
- **Repository-local `user.email`** is set to the noreply address. `user.name` and the global configuration were left unchanged.
- **The rewrite.** A Python script used `git cat-file commit` and `git hash-object -t commit -w`. Only the author and committer email bytes were replaced, and each parent line was pointed at the rewritten parent. The five branch tips were then moved with `git update-ref`, each guarded by its expected old SHA. No reset was used, and the staged `prompts.md` stayed byte-identical to the backup throughout.
- **Verification, run before the refs were moved.** For every pair:
  - the tree, the full message bytes, the author and committer names, timestamps and timezone offsets, and the Co-Authored-By trailer are identical;
  - both emails are the noreply address;
  - the parents map to the rewritten parents;
  - the object differs from the original only by the email and parent substitution.

  All branch tips point to their rewritten counterparts. No branch commit contains the old email.
- **Not changed:** historical SHAs elsewhere in this file and in the docs describe the commits as they existed then. The mapping is recorded in the migration note below.
- The staged whitespace check and both Gitleaks scans run before the commit, and the post-commit history scan, are reported in the session handoff. The original commits remain in the local object store and reflogs until Git garbage-collects them. They are not reachable from any branch, so they would not be pushed.

### Migration note: commit email privacy rewrite (2026-10-11)

Before first publication, the five unpublished commits were rewritten to replace the personal author and committer email with GitHub's noreply address. Trees, messages, names and dates are unchanged. SHAs quoted in earlier entries refer to the original commits:

| Original commit | Rewritten commit | Subject |
|---|---|---|
| `52acebd1eb33946970a60549cc4366743687ce72` | `6c095738613b1da76240496c58a26e3a4ab07174` | chore: establish repository foundation and engineering record |
| `d196afc41734bfe14ea55f91632f99d9cb2e0a61` | `7961c885d30da0433f9a78c5f3d637bc23f72039` | feat: add Python packaging and minimal health API |
| `da108e5a4e87ae1afcc9acd818a6ee3fe4d1e564` | `ea1c74f099cb3aa9503869a667c6bc020913085d` | feat: add evidence contracts and revision-bound approval gate |
| `32b1cc630ddef1296f5d8a59eedac0197dbf5bc5` | `c69ccd62929ebbb38a4df113ae363111b26021a1` | feat: add request correlation and privacy-safe API observability |
| `48872f41fad88c8eef40402e3be34d42fe864f84` | `3ea97f5451eba0bb4bb42fca27deb45711f4099e` | docs: record plain Python workflow architecture |

---

## Prompt 21: First repository publication

- **Stage:** Authorized first publication of `main` (one normal push; no other branches, tags, force, merge or deploy)
- **Date:** 2026-10-11 (session date)

````text
Publish the reviewed repository to GitHub for the first time.

I authorize one normal push of the reviewed history, plus this prompt-history entry, to `origin/main`. Do not push other branches or tags, force push, merge, deploy, or change application code.

Work only in `D:\Claude\evidenceguard_agentic_rag`. Read CLAUDE.md first.

1. Verify:
- Branch: `docs/plain-python-workflow`
- HEAD: `2f3aadc6095992c414d6fa56c38e5f2d93dd9a8f`
- Origin: `https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git`
- Clean working tree.
- Remote has no refs.
- No local main branch exists.
- All six reachable commits use `257921624+mathewmljourney93@users.noreply.github.com` for both author and committer.

Stop and report unexpected differences. Do not publish the original-history backup, any `.local/` files, or old commit refs.

2. Append this entire prompt verbatim to prompts.md using the next sequential number. Preserve earlier history.

Record that publication is explicitly authorized after external review and the verified email migration. Before the push, describe publication as pending; do not claim success in advance.

Stage only prompts.md. Inspect its additions for secrets and private content, then run:
- `git diff --cached --check`
- `gitleaks git --pre-commit --staged --redact --verbose .`

If checks pass, create one local commit:
`docs: record authorization for first repository publication`

Run:
`gitleaks git --redact --verbose .`

Stop if any check fails.

3. Create and switch to local main at the new HEAD, preserving all existing branches:
`git switch -c main`

Immediately recheck that origin is correct and the remote is still empty. If it has changed, stop.

Publish only main:
`git push -u origin main`

Do not use --all, --mirror, --tags or any force option.

If authentication or GitHub email protection blocks the push, report the failure. Do not change account security settings, install tools, expose credentials or rewrite history again.

4. Verify that `refs/heads/main` on origin matches the exact local HEAD SHA. Report final branch, upstream and working-tree status.

Check the GitHub Actions runs for that exact SHA using available read-only access. GitHub CLI is not installed; do not install it. Report CI and secret-scan run links and their actual status. If results are unavailable or still pending, say so. Do not claim Linux verification or M1 acceptance until the relevant jobs pass.

5. Final handoff:
- Published commit SHA and repository link.
- Confirmation that remote main matches local HEAD.
- Prompt-history commit and verification results.
- Actual Actions statuses and links, if accessible.
- Final Git status.
- Confirmation that only main was pushed and nothing was merged or deployed.

No application changes are authorized. If any unexpected tracked change occurs, stop and provide its complete diff directly in fenced diff blocks for review. Never truncate it.

Do not make another commit or push to record the publication outcome in this task; report that outcome here, and we will record it in the next prompt-history update.
````

**Outcome (recorded before the push; publication pending):**
- The external reviewer explicitly authorized publication after reviewing the history and the verified commit email migration. All six reachable commits use the noreply address for both author and committer.
- The plan is to create local `main` at this entry's commit and push only `main` to `origin` with one normal push. No other branches, tags, `.local/` files or original-history objects are to be published.
- Publication has **not** happened when this entry is written. As instructed, its result (remote SHA match and GitHub Actions status) will be recorded in the next prompt-history update, not in this commit.

**Publication outcome (added with Prompt 23):**
- Local `main` was created at `6d64fb362c25c28908e38b5d0a06f8c393bf6096` and published with one normal `git push -u origin main`. No authentication or email-protection rejection occurred.
- Only `main` was pushed: no other branches, tags, `.local/` files or original-history objects. `origin/main` was confirmed to match the local HEAD exactly.
- GitHub Actions for that SHA succeeded on the first attempt:
  - CI, Ubuntu and Windows jobs: https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38142996464
  - Full-history secret scan: https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38142996460
- Nothing was merged or deployed.

---

## Prompt 22: Report the GitHub Actions results

- **Stage:** Read-only results report (no file changes permitted, so recorded here at the next documentation update)
- **Date:** 2026-10-11 (session date)

````text
Report the final GitHub Actions results for the commit just pushed: Ubuntu CI, Windows CI and secret-scan. Include the commit SHA and run links. For failures, include the failing step and relevant error output. Do not change files, commit or push anything.
````

**Outcome:** Claude re-queried the public GitHub Actions API, read-only, for `6d64fb3`:
- `verify (ubuntu-24.04, Python 3.12)`: success, all 13 steps passed.
- `verify (windows-2025, Python 3.12)`: success, all 13 steps passed.
- `Gitleaks (full history)`: success, all 6 steps passed.

There were no failures to report. No files were changed.

---

## Prompt 23: Record M1 results and plan M2

- **Stage:** Documentation update and M2 planning (staged for review; no commit, no push)
- **Date:** 2026-10-11 (session date)

````text
Record the verified M1 publication results and prepare a bounded implementation plan for M2.

Work only in `D:\Claude\evidenceguard_agentic_rag`. Read CLAUDE.md, docs/plan.md, the ADRs, README, packaging configuration and workflows.

Do not commit, push, install tools, change global configuration, start services, or implement M2 yet.

Verify:
- Branch: main
- Local HEAD and origin/main: `6d64fb362c25c28908e38b5d0a06f8c393bf6096`
- Expected origin and clean working tree.

Stop on unexpected differences. Create `docs/m1-results-m2-plan` from this HEAD.

1. Record the verified publication results:
- Ubuntu and Windows CI succeeded:
  https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38142996464
- Full-history secret scanning succeeded:
  https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38142996460
- All results apply to the exact SHA above.
- The external reviewer independently checked the GitHub run and job results and remote main.

Update README and docs/plan.md narrowly. Remove stale statements that Linux and GitHub Actions have never run. Distinguish verification of this baseline from verification of future changes.

Record the implemented M1 foundation as accepted with its documented scope. Keep revision activation and supersession testing explicitly deferred to M3; do not claim those tests exist or that every original checklist item has been implemented.

2. Prepare M2 implementation slices based on the approved plan:
- Persistence package, database configuration and migrations.
- API-key authentication, tenant context and administrative CLI.
- Vendor endpoints and PostgreSQL integration tests.

For each slice, propose exact scope, expected files, dependencies, meaningful tests and acceptance criteria. Keep later job, ingestion, retrieval and approval-persistence work in their assigned milestones. Identify any unresolved decision that materially affects implementation.

3. Check database readiness using read-only commands:
- Check whether Docker, Docker Compose and PostgreSQL client tools are available on PATH.
- If Docker exists, check whether its daemon is accessible.
- Do not search unrelated folders, inspect other projects, read credentials, connect to an unspecified database or enumerate personal environment variables.
- Do not install or start anything.

Report whether we can run the planned PostgreSQL/pgvector integration tests locally. If not, explain the specific missing prerequisite and practical options without silently changing the architecture.

4. Append this entire prompt verbatim to prompts.md using the next sequential number. Record the publication outcome and this task’s results truthfully. Preserve earlier history.

Stage only intended documentation changes. Check links, staged whitespace and secrets. No application tests or build are needed for documentation-only changes.

Include the complete staged diff excluding prompts.md directly in fenced diff blocks. Do not truncate; split into numbered parts at file boundaries if necessary.

Report the M2 slices, database-readiness findings, verification results and final Git status separately. Leave everything staged and uncommitted. Nothing should be pushed.
````

**Outcome (pending review; staged, not committed or pushed):**
- **Starting state verified:** branch `main`, local HEAD and `origin/main` both `6d64fb3`, the expected origin, a clean tree. Branch `docs/m1-results-m2-plan` was created from it.
- **Documentation updated:**
  - The verified publication results were recorded in the README and `docs/plan.md`, scoped to that exact commit; later changes need their own runs.
  - Stale "CI has not run" statements were removed from the README, the plan, ADR-0003 and the threat model.
  - M1 is recorded as accepted with its documented scope. Revision activation and supersession tests remain explicitly deferred to M3 and are not claimed to exist.
  - The plan's environment table was refreshed with current facts.
- **Database readiness** (read-only; nothing installed, started or connected to):
  - Docker, Docker Compose and Podman are not installed, and no WSL distribution exists.
  - A PostgreSQL 16 Windows service is installed and running, with port 5432 listening. Its client tools are not on PATH, and the pgvector extension is not installed in it.
  - The planned pgvector integration tests therefore cannot run locally as specified. Options are in the session handoff; the architecture was not changed.
- **M2 plan:** three proposed slices and the unresolved decisions are in the session handoff. They are not yet written into `docs/plan.md`, pending review.
- Documentation only, so no tests or build were run. The link check, the staged whitespace check and the staged secret scan were run; results are in the session handoff.

**Review note (added with Prompt 24):** the external reviewer accepted the Prompt 23 documentation diff without further redesign. Its decisions on the M2 questions are recorded under Prompt 24 below.

---

## Prompt 24: Commit M1 results documentation; record M2 decisions

- **Stage:** Commit of reviewed documentation (no application changes, no push)
- **Date:** 2026-10-11 (session date)

````text
Commit the reviewed M1 results documentation locally.

Work only in `D:\Claude\evidenceguard_agentic_rag`. Do not push, merge, change branches, modify global configuration, install tools, or implement M2.

Verify:
- Branch: `docs/m1-results-m2-plan`
- HEAD: `6d64fb362c25c28908e38b5d0a06f8c393bf6096`
- Expected origin.
- Exactly these five documentation files are staged, with nothing unstaged or untracked:
  - README.md
  - docs/decisions/0003-plain-python-workflow.md
  - docs/plan.md
  - docs/threat-model.md
  - prompts.md

Stop on unexpected differences.

The external reviewer accepted the supplied documentation diff. Preserve it without further redesign.

Append this entire prompt verbatim to prompts.md using the next sequential number. Record the review acceptance and these decisions for the next implementation prompt:
- M2 integration tests will run against real PostgreSQL/pgvector in CI; local unit tests remain database-independent. Integration verification stays pending until a reviewed branch is explicitly authorized for publication and its CI passes.
- Retain the approved admin role in M2, with no approval bypass.
- Tenants is the root table; composite tenant constraints apply to tenant-scoped tables.
- Database settings belong in persistence.
- Unexpected tenant fields in request bodies are rejected; tenant headers cannot override authenticated scope.
- Use bounded limit/offset vendor pagination.
- Defer vector-extension creation until a migration actually needs it.
- Keep the planned Postgres-only Compose configuration, clearly marking local Docker verification unavailable.
- Implement /readyz with the API database wiring in a later M2 slice.

Preserve earlier prompt history. Make no application changes.

Check documentation links, staged paths and private content without displaying credentials. Run:
- `git diff --cached --check`
- `gitleaks git --pre-commit --staged --redact --verbose .`

If checks pass, commit:
`docs: record verified M1 baseline and M2 preparation`

Then run:
`gitleaks git --redact --verbose .`

Report the commit SHA, paths, checks and final Git status. No application tests or build are needed for documentation-only changes.

If any file outside prompts.md changes in this step, include its complete incremental diff directly in fenced diff blocks without truncation.

Nothing should be pushed or merged.
````

**M2 decisions recorded for the next implementation prompt** (made by the external reviewer):
1. **Integration tests:** they run against real PostgreSQL with pgvector in CI, and local unit tests stay database-independent. Integration verification remains **pending** until a reviewed branch is explicitly authorized for publication and its CI passes.
2. **Admin role:** the approved `admin` role is kept in M2. It gets **no approval bypass**.
3. **Tenancy:** `tenants` is the root table. Composite tenant constraints apply to tenant-scoped tables.
4. **Database settings** belong in the persistence package.
5. **Tenant input:** unexpected tenant fields in request bodies are rejected, and tenant headers cannot override the authenticated scope.
6. **Vendor pagination:** bounded limit/offset.
7. **The vector extension** is created only when a migration actually needs it.
8. **Compose:** the planned Postgres-only configuration is kept, clearly marked as not verified locally because Docker is unavailable.
9. **`/readyz`** is implemented with the API database wiring, in a later M2 slice.

**Outcome (pending review):**
- Only `prompts.md` changed in this step: this prompt, the review note and the recorded decisions. The accepted documentation diff was preserved without redesign, and there were no application changes.
- The link check, the staged whitespace check and the staged secret scan were run before committing. One local commit was created on `docs/m1-results-m2-plan`; its SHA and the post-commit history scan are in the session handoff.
- Not pushed or merged.

---

## Prompt 25: M2a, persistence foundation

- **Stage:** Implementation, milestone M2a (staged for review, no commit)
- **Date:** 2026-10-11 (session date)

````text
Implement M2a only: the persistence foundation.

Work only in `D:\Claude\evidenceguard_agentic_rag`. Read CLAUDE.md, docs/plan.md, existing ADRs, packaging configuration, tests and workflows first. Follow the M2 decisions recorded under Prompt 24.

Do not commit, push, merge, install system tools, change global configuration, or connect to the laptop’s existing PostgreSQL service.

Starting state:
- Branch: `docs/m1-results-m2-plan`
- HEAD: `6d05e12475e27795398f2af8aa5463f6079cb217`
- origin/main: `6d64fb362c25c28908e38b5d0a06f8c393bf6096`
- Expected origin and clean working tree.

Verify these. Stop on unexpected differences. Create `feat/persistence-foundation` from the current HEAD, preserving the local documentation commit.

Scope

1. Persistence package
- Add the typed `evidenceguard_persistence` package following ADR-0001.
- Use synchronous SQLAlchemy 2 and psycopg 3, with Alembic and pydantic-settings.
- Resolve dependency versions according to the repository’s policy and update uv.lock.
- Keep domain independent of persistence and API.
- Imports must not connect to a database or require database configuration.
- `/healthz` and existing tests must work without a database.

2. Database configuration and lifecycle
- Database settings live in persistence and use EG_DATABASE_URL.
- Require a valid PostgreSQL URL only when database functionality is explicitly requested.
- Protect credentials from representations, validation errors and logs. Disable SQL echo and hide SQL parameter values.
- Provide explicit engine/session creation and cleanup with clear transaction ownership.
- Do not silently load configuration from outside the project.

3. Initial schema
Implement only tenants, users, api_keys and vendors:
- Tenants is the root table.
- Tenant-scoped tables reference tenants and expose the composite uniqueness needed for tenant-safe references.
- API keys reference users through `(tenant_id, user_id)`.
- Roles include reviewer, approver and admin. Do not alter approval behaviour or add an admin bypass.
- Vendor slugs are unique within each tenant.
- API-key prefixes must support unambiguous lookup. Store only the planned secret hash and metadata, never plaintext secrets.
- Use the approved plan for column definitions and constraints.

Do not implement key generation, authentication, administrative commands, vendor endpoints, report persistence or later-milestone tables.

4. Migrations and packaging
- Add the initial reversible Alembic migration and configuration.
- Package migration files and templates so migrations work from an installed wheel, outside the source checkout.
- Avoid duplicating schema definitions in ways that hide model/migration drift.
- Do not create the vector extension yet.
- Extend package import-boundary checks.

5. Database test configuration
- Add the planned Postgres-only Compose configuration using the approved pgvector/PostgreSQL image. Bind any published database port to localhost.
- Use explicitly documented disposable development credentials only.
- Add an Ubuntu CI integration job with a PostgreSQL/pgvector service and readiness checks, following existing action-pin and permission conventions.
- Keep Ubuntu and Windows database-independent checks.
- Integration tests must require an explicit dedicated test database URL. Never fall back to another URL or the existing local PostgreSQL service.
- Without that URL, normal local tests may skip integration tests with a clear reason. The explicit CI integration command must fail if the URL is missing or no integration tests execute.
- Destructive migration tests must be restricted to the disposable test database.

Meaningful integration tests:
- Upgrade an empty database, downgrade, then upgrade again.
- Check model/migration drift with Alembic.
- Prove the database rejects an API key referencing another tenant’s user.
- Prove missing tenant references fail.
- Prove vendor slug uniqueness within a tenant and reuse across tenants.

Do not substitute SQLite, mocked database calls or metadata inspection for these PostgreSQL checks.

6. Documentation and history
- Document setup, migration commands, local unit-test commands and the explicit integration command.
- Clearly state that local Docker and PostgreSQL integration verification are unavailable and CI is pending.
- Record narrow persistence decisions in ADR-0004 and update milestone progress.
- Add a placeholder-only .env.example without real credentials.
- Append this entire prompt verbatim to prompts.md using the next sequential number, with a truthful outcome note. Preserve earlier history.

Verification and handoff

Run locked sync, formatting, lint, strict Mypy, the full locally runnable test suite, build and isolated wheel checks. Verify installed migration resources and offline migration generation without connecting to a database.

Report passed, skipped and unrun checks separately. Do not claim migrations, tenant constraints or Compose have been verified against a live database.

Stage only intended files. Run staged whitespace and redacted secret scans. Leave everything staged and uncommitted.

Include the complete staged diff excluding prompts.md directly in fenced diff blocks. Never truncate or summarize it. Split into numbered parts at file boundaries and provide all parts when necessary.

Report dependency changes, design decisions, verification commands and results, staged paths and final Git status separately.

Nothing should be committed or pushed.
````

**Outcome (pending review; staged, not committed or pushed):**
- **Starting state verified:** branch, HEAD `6d05e12`, `origin/main` `6d64fb3`, the expected origin, a clean tree. Branch `feat/persistence-foundation` was created from `6d05e12`.
- **Added `evidenceguard_persistence`:**
  - environment-only `EG_DATABASE_URL` settings, held as a secret, with validation errors that never echo the URL;
  - explicit engine and session lifecycle with `transaction()` ownership, no SQL echo and hidden SQL parameters;
  - the tenants/users/api_keys/vendors schema, with composite tenant constraints;
  - packaged Alembic migrations and `alembic_config()`;
  - root `alembic.ini`, Postgres-only `docker-compose.yml` (localhost-bound, disposable credentials), a test-database init script, a placeholder-only `.env.example`, an Ubuntu CI integration job, ADR-0004, and README, plan and threat-model updates.
- **Dependencies:** SQLAlchemy 2.1.1, Alembic 1.20.0, psycopg[binary] 3.3.6 and pydantic-settings 2.15.0 were added, with five transitive packages. They were resolved under a two-week age cutoff applied only to the new packages; no existing locked version changed. The pinned pgvector image digest is younger than two weeks and is flagged for review.
- **Verified locally** (Windows, Python 3.12.15): the locked sync, Ruff, strict Mypy, the database-independent tests, offline migration SQL, the build and the isolated wheel checks. Exact results are in the session handoff.
- **Not verified:**
  - The PostgreSQL integration tests were **skipped** because no test database exists locally.
  - Migrations, tenant constraints, the drift check and Compose have **not** been run against PostgreSQL.
  - CI integration verification is pending an authorized publication.
- No connection was made to the laptop's existing PostgreSQL service.

## Prompt 26: Correct M2a database URL validation and destructive-test safeguards

- **Stage:** Correction, milestone M2a (staged for review, no commit)
- **Date:** 2026-10-11 (session date)

````text
Prompt 26 — Correct M2a database URL validation and destructive-test safeguards

Work only in D:\Claude\evidenceguard_agentic_rag. Read CLAUDE.md and the relevant project instructions.

Expected starting state:
- Branch: feat/persistence-foundation
- HEAD: 6d05e12475e27795398f2af8aa5463f6079cb217
- origin/main: 6d64fb362c25c28908e38b5d0a06f8c393bf6096
- The reported M2a implementation is staged and uncommitted.

Verify the starting state. Preserve the existing staged implementation. Record its tree ID before editing so the final incremental diff can be measured against this reviewed version.

Do not commit, push, merge, rewrite history, install system tools, start Docker, or connect to any database. PostgreSQL integration verification remains pending until an authorized publication and successful CI run.

The reviewer identified two issues:

1. tests/test_persistence_postgres.py compares EG_TEST_DATABASE_URL and EG_DATABASE_URL as raw strings. Different credentials or equivalent URL spellings can target the same database and bypass the safeguard before DROP SCHEMA public CASCADE.

2. parse_postgres_url accepts unrestricted query parameters. SQLAlchemy's psycopg dialect merges URL query parameters into connection arguments. A dbname parameter can override the database name validated in the URL path. Other parameters can override routing or introduce credentials that ordinary URL password masking does not hide.

Make these narrow corrections:

A. Database URL policy
- Enforce an explicit, small query-parameter allowlist in the shared parser. Permit only validated sslmode and connect_timeout parameters for this slice, if needed.
- Reject all other query parameters, including database/routing overrides, service configuration, credentials and arbitrary options.
- Reject repeated parameters and malformed allowed values.
- Require a single explicit host and database; reject unsupported multi-host forms.
- Validate ports and use a consistent default-port interpretation.
- Keep configuration errors generic. Never include submitted URLs, query values or credentials in error messages.
- Do not introduce a new dependency.

B. Destructive integration-test guard
- Extract a database-independent validation helper and run it before creating an engine or opening a connection.
- Retain the required explicit test URL and _test database-name suffix.
- Compare parsed database identities: host, effective port and database. Ignore credentials and accepted driver spelling when determining whether two URLs target the same database.
- Normalize hostname case, omitted/default port and known loopback spellings conservatively.
- If EG_DATABASE_URL is present but invalid, fail closed with a safe message.
- Reject a test target matching the configured application database even when credentials or URL spelling differ.
- Preserve CI's disposable database setup and the required-integration enforcement.
- Document that arbitrary DNS aliases cannot be proven distinct through URL comparison and that the test database must be explicitly disposable.

C. Regression tests
Add database-independent tests covering:
- Same target with different credentials.
- Equivalent driver spelling, hostname case and omitted/explicit default port.
- Relevant loopback aliases.
- Invalid application URL.
- Missing test URL and a database without the _test suffix.
- Query database/routing overrides, query credentials, duplicate parameters and invalid allowed values.
- A valid distinct disposable target.
- Rejected targets cannot reach engine creation or database connection.
- Safe configuration errors do not reveal synthetic credential markers.

Demonstrate that the relevant new regression tests catch the previous implementation using a temporary local restoration or equivalent controlled comparison. Restore the corrected files afterwards. Do not connect to PostgreSQL during this demonstration.

D. Documentation and prompt history
- Update the relevant README, ADR and threat-model statements to describe the actual safeguards and their limits.
- Clarify that Pydantic hide_input_in_errors controls printed validation errors; it does not make arbitrary structured ValidationError dumps safe. Keep the generic configuration-error wrapper as the supported boundary.
- Append this prompt verbatim to prompts.md with a truthful outcome note.
- Record the review findings without claiming the reviewer ran the application suite or reproduced the issue.
- Preserve all earlier prompt text and outcome notes.

Verification:
Run the relevant database-independent tests, the full local suite with PostgreSQL tests skipped, locked dependency synchronization, Ruff formatting and linting, strict Mypy, build and isolated installed-wheel checks. Run git diff --cached --check and the staged secret scan after staging.
Report exact commands, results and skipped checks. Do not claim Linux, Compose, PostgreSQL or GitHub Actions verification.

Leave the corrected work staged and uncommitted.

Final handoff:
1. Explain the corrections and remaining limitations.
2. Include the COMPLETE incremental diff against the recorded pre-edit staged tree, excluding prompts.md, directly in fenced diff blocks.
3. Split large diffs into numbered parts at file boundaries and provide every part without truncation. Use a gitignored .local/ diff file only if response limits prevent complete inclusion.
4. Report prompt-history additions, verification results, staged paths, HEAD and final Git status separately.
5. Confirm that nothing was committed, pushed or connected to a database.
````

**Outcome (correction pending review; staged, not committed or pushed):**
- **Starting state verified:** branch, HEAD `6d05e12`, `origin/main` `6d64fb3`, M2a staged and uncommitted. The pre-edit staged tree was `9ff1b77765cf121332a9ae1c46ef6e484ec7f810`.
- **Review findings recorded:**
  1. The integration-test guard compared `EG_TEST_DATABASE_URL` and `EG_DATABASE_URL` as raw strings.
  2. `parse_postgres_url` accepted unrestricted query parameters, which SQLAlchemy's psycopg dialect passes to the driver.

  The findings came from code review. They do not record that the reviewer ran the application suite or reproduced the issue.
- **URL policy** (`settings.py`):
  - exactly one host, a DNS name or an IP literal;
  - a port from 1 to 65535, with an omitted port made explicit as 5432;
  - a restricted database-name character set;
  - only `sslmode` (a libpq mode) and `connect_timeout` (1–600) as query parameters, each at most once; everything else is rejected;
  - generic errors that never contain the URL, its query values or its credentials.

  A new `database_identity()` helper compares host, effective port and database. It ignores credentials, driver spelling and options, folds case, and treats every loopback or unspecified address as one host.
- **Destructive-test guard:** the new `evidenceguard_persistence.safety.require_disposable_test_database` runs in the session fixture before any engine exists. It requires a valid test URL with the `_test` suffix, fails closed on an invalid `EG_DATABASE_URL`, and refuses a matching database identity.
- **Tests:** 74 database-independent tests in `tests/test_persistence_safety.py`. They include a child-pytest run of the real fixture, with engine creation and psycopg connections forced to fail, plus a positive control.
- **Previous implementation, controlled comparison** (pre-edit files restored temporarily in the working tree, then restored with matching SHA-256):
  - With the previous fixture, 3 of 4 rejected-target cases failed. The same-target and invalid-app-URL cases reached engine creation.
  - With the previous parser, 28 of 30 unsafe URLs were accepted, and 5 further guard and policy tests failed.
  - No database was contacted.
- **Documentation:** README, ADR-0004 and the threat model now describe:
  - the URL policy;
  - the guard and its limits: no DNS-alias detection, libpq environment variables not controlled, and the test database must be explicitly disposable;
  - that `hide_input_in_errors` covers only *printed* `ValidationError`s, and that the generic configuration-error wrapper is the supported boundary.
- **Verified locally** (Windows, Python 3.12.15): the locked sync, Ruff, strict Mypy (39 files), and the full suite (247 passed, 10 PostgreSQL integration tests skipped). Also the required-integration usage error, the build, and the isolated installed-wheel checks. Exact results are in the session handoff.
- **Not verified:**
  - Linux, Compose, PostgreSQL and GitHub Actions were not exercised.
  - The integration tests remain **pending** CI on an authorized publication.
  - No connection was made to any database.

## Prompt 27: Distinguish an unset application database URL from an empty one

- **Stage:** Correction, milestone M2a (staged for review, no commit)
- **Date:** 2026-10-11 (session date)

````text
Prompt 27 — Distinguish an unset application database URL from an empty one

Work only in D:\Claude\evidenceguard_agentic_rag. Follow CLAUDE.md.

Expected state:
- Branch feat/persistence-foundation
- HEAD 6d05e12475e27795398f2af8aa5463f6079cb217
- All 29 M2a files staged; nothing unstaged or untracked.

Verify this state and record the current staged tree before editing. Preserve the staged implementation.

The reviewer accepts the main Prompt 26 corrections but found one remaining edge case:

require_disposable_test_database currently uses `if app_raw:`, treating an empty EG_DATABASE_URL as unset. The acceptance test also explicitly permits "". This contradicts the requirement to fail closed when EG_DATABASE_URL is configured but invalid.

Make only this correction:
- Treat None as unset.
- Validate every supplied application URL, including "".
- An empty or whitespace-only application URL must produce the existing generic DatabaseConfigurationError.
- Remove "" from the accepted-target cases.
- Add empty and whitespace-only values to the invalid-application-URL cases.
- Add an empty application URL to the real-fixture test proving rejection occurs before engine creation.
- Preserve acceptance when the application URL is genuinely unset.

Append this prompt verbatim and a truthful outcome note to prompts.md. Preserve earlier entries. Record that the reviewer inspected the diff but did not run the application tests.

Do not commit, push, merge, start Docker or connect to any database.

Run the relevant persistence and safety tests, the full local suite with PostgreSQL tests skipped, Ruff formatting/linting, strict Mypy, git diff --cached --check and the staged secret scan. Report exact results and remaining verification limits.

Leave the work staged and uncommitted.

Include the COMPLETE incremental diff against the recorded pre-edit staged tree, excluding prompts.md, directly in fenced diff blocks. Do not truncate; split into numbered parts at file boundaries if necessary. Report prompt-history additions, verification results and final Git status separately.
````

**Outcome (correction pending review; staged, not committed or pushed):**
- **Starting state verified:** branch, HEAD `6d05e12`, 29 files staged, nothing unstaged or untracked. The pre-edit staged tree was `5923351fe0214448dfc54f8745ceb4c77b7b2023`.
- **Review finding:** `require_disposable_test_database` used `if app_raw:`, so an empty `EG_DATABASE_URL` was treated as unset and accepted. The reviewer inspected the diff and did not run the application tests.
- **Correction:**
  - Only `None` now means unset. Every supplied application URL is validated, including `""`.
  - An empty or whitespace-only value raises the existing generic `DatabaseConfigurationError` ("EG_DATABASE_URL is not a valid PostgreSQL URL").
  - A genuinely unset application URL is still accepted.
- **Tests:**
  - `""` was removed from the accepted-target cases.
  - `""`, `" "` and a tab-newline value were added to the invalid-application-URL cases.
  - An empty application URL was added to the real-fixture test. Its child process ran with `EG_DATABASE_URL` set to `""` and was refused before engine creation.
  - Against the pre-edit `safety.py` (restored temporarily in the working tree, then restored with a matching SHA-256), the two empty-string cases failed. The whitespace cases already passed, because a blank string is truthy.
- **Verified locally** (Windows, Python 3.12.15): the persistence and safety tests, the full suite with the PostgreSQL tests skipped, Ruff, strict Mypy, the staged whitespace check and the staged secret scan. Exact results are in the session handoff.
- **Not verified:** Linux, Compose, PostgreSQL and GitHub Actions were not exercised. The integration tests remain pending CI on an authorized publication. No database was contacted.

**Review note (added with Prompt 28):** the external reviewer accepted M2a for a local commit. The decision covers the original M2a staged diff (Prompt 25) and the incremental correction diffs from Prompts 26 and 27. It relied on inspecting those diffs and on Claude's reported Windows checks: the full suite gave 250 passed, with the 10 PostgreSQL integration tests skipped. The reviewer did not run the application checks. PostgreSQL, Linux, Compose and GitHub Actions verification all remain **pending**.

## Prompt 28: Commit the reviewed M2a persistence foundation locally

- **Stage:** Local commit of reviewed milestone M2a (no push)
- **Date:** 2026-10-11 (session date)

````text
Prompt 28 — Commit the reviewed M2a persistence foundation locally

Work only in D:\Claude\evidenceguard_agentic_rag. Follow CLAUDE.md.

This prompt authorizes one local commit of the reviewed M2a work. It does not authorize pushing, merging or rewriting history.

Verify:
- Branch: feat/persistence-foundation
- HEAD: 6d05e12475e27795398f2af8aa5463f6079cb217
- Origin: https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git
- Exactly the 29 reported M2a files are staged.
- Nothing is unstaged or untracked; no .local/ paths are staged.

Inspect the staged paths and complete staged diff. Do not modify application code, tests, dependencies, configuration or architecture.

Update prompts.md only:
- Add a separate review note under Prompt 27 recording acceptance of M2a for a local commit, based on the original and correction diffs and your reported Windows checks: 250 passed, 10 PostgreSQL tests skipped.
- State that the reviewer did not run the application checks.
- Keep PostgreSQL, Linux, Compose and GitHub Actions verification marked pending.
- Append this prompt verbatim and a truthful outcome note.
- Preserve every earlier prompt and outcome note.

Stage prompts.md. Confirm all other staged files remain byte-identical to the accepted staged state.

Before committing:
- Confirm the effective author and committer email is:
  257921624+mathewmljourney93@users.noreply.github.com
- Inspect staged content for credentials and unintended private information without printing secret values.
- Run git diff --cached --check.
- Run gitleaks git --pre-commit --staged --redact --verbose .
- If any check fails, correct only within this task's scope or report the blocker; do not commit failed checks.

Create one local commit:
feat: add PostgreSQL persistence foundation and migration checks

After committing:
- Run gitleaks git --redact --verbose . against the full history.
- Report the full commit SHA, parent, subject, committed paths, checks and final Git status.
- Report prompt-history additions separately.
- Include any incremental diff outside prompts.md in full, directly in fenced diff blocks. If none exists, explicitly say so.

Application checks need not be repeated if only prompts.md changed. Do not start Docker or contact any database.

Do not push, merge, amend, rebase or change global configuration. Leave the working tree clean.
````

**Outcome (committed locally; not pushed):**
- **Starting state verified:** branch `feat/persistence-foundation`, HEAD `6d05e12`, the expected origin, exactly the 29 M2a paths staged (accepted staged tree `0501a903deeeb6bcccc061a9b0332a76c2036944`), no `.local/` paths staged, nothing unstaged or untracked.
- **Only `prompts.md` changed** in this step: the review note above, and this prompt with its outcome note. Every other staged file was confirmed byte-identical to the accepted staged tree before committing.
- **Pre-commit checks:**
  - the effective author and committer email is the GitHub noreply address;
  - the staged content was inspected for credentials and private information. Only documented disposable Compose and CI credentials and obviously fake test markers were found;
  - `git diff --cached --check` and the staged Gitleaks scan both passed.

  Exact results are in the session handoff.
- **Commit:** one local commit, `feat: add PostgreSQL persistence foundation and migration checks`, whose parent is `6d05e12`. It contains this note, so its SHA is reported in the session handoff rather than here. A full-history Gitleaks scan was run after committing.
- **Application checks** were not rerun, because only `prompts.md` changed since the reported run of 250 passed and 10 skipped.
- **Still pending:** PostgreSQL integration, Linux, Compose and GitHub Actions verification, until an authorized publication and a successful CI run. Nothing was pushed or merged, and no database was contacted.

## Prompt 29: Publish the reviewed M2a branch and verify CI

- **Stage:** Publication of reviewed branch `feat/persistence-foundation` (no merge)
- **Date:** 2026-10-12 (session date)

````text
Prompt 29 — Publish the reviewed M2a branch and verify CI

Work only in D:\Claude\evidenceguard_agentic_rag. Follow CLAUDE.md.

This prompt explicitly authorizes publishing the reviewed feat/persistence-foundation branch. It does not authorize merging, pushing main, force-pushing or rewriting history.

Verify the starting state:
- Branch: feat/persistence-foundation
- HEAD: 32eea73d5cc35eae4016dcab3aecb088a1574e39
- Parent: 6d05e12475e27795398f2af8aa5463f6079cb217
- Origin: https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git
- Working tree clean.
- Effective author and committer email:
  257921624+mathewmljourney93@users.noreply.github.com

Publication preflight:
1. Inspect both workflow files. Confirm publishing this branch will trigger CI and the full-history secret scan, including Ubuntu verification, Windows verification and the PostgreSQL integration job.
2. If workflow triggers need changing, leave that narrow change staged, provide its complete diff and stop before committing or pushing. It needs review first.
3. Read the remote refs. Confirm remote main remains 6d64fb362c25c28908e38b5d0a06f8c393bf6096. If the feature branch already exists remotely, inspect its relationship to local history before proceeding; never overwrite divergent history.
4. Inspect all changes that will become public relative to remote main, including prompts.md and commit identities. Check for unintended private information without printing sensitive values. Confirm no .local/ files or backup bundle are tracked.

If preflight passes:
- Append this prompt verbatim to prompts.md.
- Add a truthful note recording the successful preflight and authorization to publish. Do not record a push or CI success before it happens.
- Preserve all earlier prompt text and outcome notes.
- Commit only this prompt-history update locally with subject:
  docs: record M2a branch publication authorization

Before publication, run:
- git diff --cached --check before the documentation commit.
- The staged Gitleaks scan before that commit.
- gitleaks git --redact --verbose . after the commit.

Only if all checks pass, push this single explicit ref and establish its upstream:
git push --set-upstream origin refs/heads/feat/persistence-foundation:refs/heads/feat/persistence-foundation

Do not push any other branch or tag.

Verify the remote branch SHA equals the published local HEAD, and remote main is unchanged.

Using available GitHub tooling or its public read-only Actions API, inspect workflow runs for that exact published SHA. Do not install system tools.
- Report run and job links.
- Check Ubuntu verification, Windows verification, PostgreSQL integration and full-history secret scanning.
- Confirm the PostgreSQL tests actually ran and were not skipped.
- If a job fails, return its failing step and relevant redacted output. Do not change code or publish another fix in this task.
- If runs are still pending, report their actual current status. Do not claim continued background monitoring unless a real persistent process exists.

Application checks need not be repeated if only prompts.md changed. Do not start Docker or contact the machine's PostgreSQL service.

Final handoff:
- Published commit SHA and branch.
- Prompt-history commit and additions.
- Preflight and scan results.
- Workflow/job results for the exact published SHA, with any checks still pending.
- Final Git status and confirmation that main was unchanged.
- Complete incremental diff outside prompts.md, if any; otherwise explicitly state there was none.

Do not merge or mark M2a integration verification complete unless the relevant CI job has actually passed.
````

**Preflight note (recorded before publication):**
- **Starting state verified:** branch `feat/persistence-foundation`, HEAD `32eea73` (parent `6d05e12`), the expected origin, a clean working tree. The effective author and committer email is the GitHub noreply address.
- **Workflows:** both `ci.yml` and `secret-scan.yml` trigger on `push` to any branch, as well as on `pull_request` and `workflow_dispatch`.
  - `ci` runs `verify` on `ubuntu-24.04` and `windows-2025`, plus the Ubuntu `integration` job with the PostgreSQL 17 + pgvector service and `EG_REQUIRE_INTEGRATION=1`.
  - `secret-scan` checks out the full history (`fetch-depth: 0`) and runs a checksum-verified Gitleaks 8.30.1.
  - No trigger change was needed.
- **Remote refs:** `refs/heads/main` is `6d64fb3`, and `feat/persistence-foundation` does not exist on the remote yet.
- **Content to be published** (relative to remote `main`: commits `6d05e12` and `32eea73`, 30 files):
  - both commits use the noreply identity for author and committer;
  - no `.local/` files, bundles or backups are tracked;
  - credential-like matches are limited to the documented disposable Compose and CI passwords, the `.env.example` placeholder and labelled fake test markers;
  - the only email address is the noreply one, and no personal paths or identifiers were found.
- **Authorization:** Prompt 29 authorizes publishing this single branch. It does not authorize a merge, a push to `main`, a force-push or a history rewrite.
- **Not yet recorded here:** the push result and CI results happen after this commit, so they are reported in the session handoff. M2a PostgreSQL integration verification stays **pending** until the CI integration job has actually passed.

**Outcome (Prompt 29, publication and CI; added with Prompt 30):**
- **Published:** the branch `feat/persistence-foundation` was pushed as `9ad7daefc6372786e1da2a636b9419b4ca7df89d`, with its upstream set, using `git push --set-upstream origin refs/heads/feat/persistence-foundation:refs/heads/feat/persistence-foundation` (exit 0).
  - The remote branch SHA matched local HEAD.
  - Remote `main` stayed at `6d64fb3`.
  - No other branch or tag was pushed, and nothing was merged or force-pushed.
- **Checks before the push:** `git diff --cached --check`, the staged Gitleaks scan, and a full-history Gitleaks scan after the documentation commit `9ad7dae` all passed.
- **CI for `9ad7dae`, all successful:**
  - [ci run 38158076257](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38158076257), with jobs:
    - [`verify (ubuntu-24.04, Python 3.12)` 114525070324](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38158076257/job/114525070324);
    - [`verify (windows-2025, Python 3.12)` 114525070158](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38158076257/job/114525070158);
    - [`integration (ubuntu-24.04, PostgreSQL 17 + pgvector)` 114525070229](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38158076257/job/114525070229).
  - [secret-scan run 38158076261](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38158076261), with job [`Gitleaks (full history)` 114525070253](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38158076261/job/114525070253).
- **Integration-test evidence:**
  - Claude could not read the integration job log. The public Actions API refused an anonymous log download (HTTP 403, "Must have admin rights to Repository"), and `gh` was not installed. Claude therefore inferred, from the `EG_REQUIRE_INTEGRATION=1` gating, that integration tests had run, and did not confirm the count.
  - The external reviewer later retrieved the integration log independently. It reports `10 passed, 250 deselected in 2.07s`, so all ten PostgreSQL integration tests passed and none was skipped.
  - The reviewer inspected GitHub evidence, not a locally run application suite.
- **Still open:** Compose has never been run, and nothing has been merged into `main`.

## Prompt 30: Record independently verified M2a CI results

- **Stage:** Documentation update (staged for review, no commit)
- **Date:** 2026-10-12 (session date)

````text
Prompt 30 — Record independently verified M2a CI results

Work only in D:\Claude\evidenceguard_agentic_rag. Follow CLAUDE.md.

Verify:
- Branch feat/persistence-foundation
- HEAD 9ad7daefc6372786e1da2a636b9419b4ca7df89d
- Upstream origin/feat/persistence-foundation matches HEAD.
- Working tree is clean.
- Remote main remains 6d64fb362c25c28908e38b5d0a06f8c393bf6096.

Update documentation only. Do not change application code, tests, dependencies, workflows or database configuration.

Verified evidence for published commit 9ad7dae:
- CI run 38158076257 succeeded.
- Ubuntu verification job 114525070324 succeeded.
- Windows verification job 114525070158 succeeded.
- PostgreSQL integration job 114525070229 succeeded.
- Secret-scan run 38158076261 and job 114525070253 succeeded.
- The external reviewer independently retrieved the integration log. It reports:
  "10 passed, 250 deselected in 2.07s"
- Therefore all ten PostgreSQL integration tests passed; none was skipped.
- The reviewer inspected GitHub evidence, not a locally executed application suite.
- Compose has still never been run.
- Nothing has been merged into main.

Update README.md, docs/plan.md, ADR-0004 and docs/threat-model.md narrowly:
- Replace obsolete M2a CI/PostgreSQL-pending statements with the verified results.
- Mark ADR-0004 accepted and M2a's implemented persistence foundation verified in CI.
- Link the exact runs/jobs and identify the tested commit.
- Preserve the Compose limitation and all other unresolved limitations.
- Keep M2b authentication, M2c vendor endpoints/readiness and overall M2 completion pending.
- Do not claim pgvector retrieval or vector-extension functionality was tested; M2a deliberately creates no vector extension.

In prompts.md:
- Add a separate outcome note under Prompt 29 recording the actual publication and CI results.
- Preserve Claude's earlier anonymous-log access limitation as a historical fact.
- Record that the external reviewer subsequently obtained the log and directly confirmed the ten passing tests.
- Append this prompt verbatim with a truthful outcome note.
- Preserve all earlier text and outcome notes.

Check documentation links, consistency, git diff --cached --check, staged private-content checks and the staged Gitleaks scan.

Leave the changes staged and uncommitted. Do not push, merge, rewrite history, start Docker or contact any database.

Final handoff:
- Include the COMPLETE staged diff excluding prompts.md directly in fenced diff blocks.
- Never truncate; split into numbered parts at file boundaries if necessary.
- Report prompt-history additions, verification results, staged paths and final Git status separately.
````

**Outcome (documentation update pending review; staged, not committed):**
- **Starting state verified:** branch `feat/persistence-foundation`, HEAD `9ad7dae` equal to `origin/feat/persistence-foundation`, a clean tree, remote `main` `6d64fb3`.
- **Prompt history:** a separate outcome note under Prompt 29 now records the publication and CI results. It keeps Claude's earlier anonymous-log limitation (HTTP 403) as historical fact, and records that the external reviewer then retrieved the integration log and confirmed `10 passed, 250 deselected`.
- **Documentation:** README, `docs/plan.md`, ADR-0004 and `docs/threat-model.md` were updated narrowly.
  - The obsolete M2a pending statements are replaced with the verified CI results for commit `9ad7dae`, with links to the exact runs and jobs.
  - ADR-0004 is marked Accepted.
  - The Compose limitation (never run) is kept, along with the statement that no pgvector functionality was tested.
  - The documents say the work is not merged into `main`, and that M2b, M2c and overall M2 completion remain pending.
- **Checks:** the six Actions links returned HTTP 200, relative links resolve, no stale M2a pending wording remains, `git diff --cached --check` passed, the staged private-content check passed, and the staged Gitleaks scan passed. Exact results are in the session handoff.
- **No application checks were run;** only documentation changed. No application code, tests, dependencies, workflows or database configuration changed. Nothing was committed or pushed, Docker was not started, and no database was contacted.

**Review note (added with Prompt 31):** the external reviewer accepted the Prompt 30 documentation diff. The acceptance relied on the reviewed diff and on GitHub CI evidence that the reviewer retrieved independently, including the integration log reporting `10 passed, 250 deselected`. Compose remains unverified because it has never been run. M2b (authentication), M2c (vendor endpoints and readiness) and overall M2 completion remain pending. Nothing has been merged into `main`.

## Prompt 31: Commit the reviewed M2a verification documentation

- **Stage:** Local documentation commit (no push)
- **Date:** 2026-10-12 (session date)

````text
Prompt 31 — Commit the reviewed M2a verification documentation

Work only in D:\Claude\evidenceguard_agentic_rag. Follow CLAUDE.md.

This prompt authorizes one local documentation commit. Do not push or merge.

Verify:
- Branch feat/persistence-foundation
- HEAD 9ad7daefc6372786e1da2a636b9419b4ca7df89d
- Upstream matches HEAD.
- Exactly these five files are staged:
  README.md
  docs/decisions/0004-persistence-foundation.md
  docs/plan.md
  docs/threat-model.md
  prompts.md
- Nothing unstaged or untracked.
- Origin is the expected evidenceguard-agentic-rag repository.

Record the accepted staged tree before editing.

Update prompts.md only:
- Add a separate review note under Prompt 30 recording acceptance of its documentation diff.
- State that acceptance relied on the reviewed diff and the reviewer's independently retrieved GitHub CI evidence.
- Preserve Compose as unverified and M2b/M2c as pending.
- Append this prompt verbatim with a truthful outcome note.
- Preserve all earlier entries.

Stage prompts.md and confirm every other file remains byte-identical to the accepted staged state.

Before committing:
- Verify author and committer use:
  257921624+mathewmljourney93@users.noreply.github.com
- Inspect staged content for unintended private information.
- Run git diff --cached --check.
- Run gitleaks git --pre-commit --staged --redact --verbose .
- Do not commit if checks fail.

Create one local commit:
docs: record verified M2a persistence results

After committing:
- Run gitleaks git --redact --verbose . against full history.
- Report the full SHA, parent, subject, committed paths, checks and final Git status.
- Summarize prompt-history additions separately.
- Include any incremental diff outside prompts.md completely in fenced diff blocks. If none exists, say so.

No application checks are needed because only documentation changed.

Do not push, merge, amend, rebase, change global configuration, start Docker or contact any database. Leave the working tree clean.
````

**Outcome (committed locally; not pushed):**
- **Starting state verified:** branch `feat/persistence-foundation`, HEAD `9ad7dae` equal to its upstream, the expected origin, exactly the five accepted files staged (accepted staged tree `bd223db9e2a73e5db42832f93555f1678ade3ec7`), nothing unstaged or untracked.
- **Only `prompts.md` changed** in this step: the review note above, and this prompt with its outcome note. The other four staged files were confirmed byte-identical to the accepted staged tree.
- **Pre-commit checks:**
  - the author and committer email is the GitHub noreply address;
  - the staged content was inspected for private information;
  - `git diff --cached --check` and the staged Gitleaks scan both passed.

  Exact results are in the session handoff.
- **Commit:** one local commit, `docs: record verified M2a persistence results`, whose parent is `9ad7dae`. It contains this note, so its SHA is reported in the session handoff. A full-history Gitleaks scan was run after committing.
- **No application checks were run;** only documentation changed. Nothing was pushed or merged, Docker was not started, and no database was contacted. Compose remains unverified, and M2b, M2c and overall M2 completion remain pending.

## Prompt 32: Publish verified M2a documentation and fast-forward main

- **Stage:** Publication of `feat/persistence-foundation` and an authorized fast-forward of `main`
- **Date:** 2026-10-12 (session date)

````text
Prompt 32 — Publish verified M2a documentation and fast-forward main

Work only in D:\Claude\evidenceguard_agentic_rag. Follow CLAUDE.md.

This prompt explicitly authorizes:
- Publishing the reviewed feat/persistence-foundation branch.
- After successful CI, fast-forwarding local main to that exact branch tip.
- Publishing only that main update.

Verify:
- Branch feat/persistence-foundation
- HEAD 7cf15e7398b0aed91ef8702e468c6463e381f9e0
- Working tree clean.
- Origin:
  https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git
- Remote feature branch:
  9ad7daefc6372786e1da2a636b9419b4ca7df89d
- Remote main:
  6d64fb362c25c28908e38b5d0a06f8c393bf6096

Read current remote refs before proceeding. Stop if either has changed unexpectedly or history diverges. Never force-push.

Change prompts.md only:
- Append this prompt verbatim.
- Add a truthful preflight note recording the verified starting state and publication/fast-forward authorization.
- Preserve all earlier entries, including historical statements that the branch was not yet merged.
- Do not record future actions as completed.

Verify the noreply author and committer identity. Inspect the additions, run git diff --cached --check and the staged Gitleaks scan.

Commit only prompts.md:
docs: record M2a main publication authorization

Run the full-history Gitleaks scan. Proceed only if all checks pass.

Publish only the feature branch:
git push origin refs/heads/feat/persistence-foundation:refs/heads/feat/persistence-foundation

Confirm its remote SHA matches local HEAD.

Inspect GitHub Actions for that exact SHA. Require success for:
- Ubuntu verification.
- Windows verification.
- PostgreSQL integration.
- Full-history secret scan.

If any job fails, report its failing step and relevant redacted output. Do not change code or merge.
If checks remain pending, report their current status and leave main unchanged.

Once all four jobs have passed:
- Fetch main and the feature branch.
- Reconfirm remote main is still the expected baseline.
- Confirm main is an ancestor of the verified feature tip.
- Switch to local main and ensure it has no divergent local history.
- Fast-forward main using git merge --ff-only to the exact verified feature commit.
- Push only main with an explicit refspec:
  git push origin refs/heads/main:refs/heads/main

Do not create a merge commit, squash commits, rebase, amend, delete branches or push tags.

Confirm local main, remote main and the verified feature tip match. Inspect the new main workflow runs for that exact SHA and report their actual results. Do not claim success while checks are pending.

Final handoff:
- Prompt-history commit and additions.
- Published SHA and remote refs.
- Feature-branch and main workflow links/results.
- Scan results and final Git status.
- Any incremental diff outside prompts.md in full; otherwise say none exists.
- Preserve Compose as unverified and M2b/M2c as pending.

Do not change application code, start Docker, contact a local database or change global configuration.
````

**Preflight note (recorded before publication and before any change to `main`):**
- **Starting state verified:** branch `feat/persistence-foundation`, HEAD `7cf15e7`, a clean tree, the expected origin. The noreply identity is the effective author and committer.
- **Remote refs, read before this commit:**
  - `refs/heads/feat/persistence-foundation` is `9ad7dae`;
  - `refs/heads/main` is `6d64fb3`, and local `main` matches it;
  - both remote refs are ancestors of local HEAD, so history has not diverged.
- **Commits to be published on the feature branch and then fast-forwarded onto `main`:** `6d05e12`, `32eea73`, `9ad7dae`, `7cf15e7` and this prompt-history commit.
- **Authorization:** Prompt 32 authorizes three things, in order:
  1. pushing the feature branch;
  2. **only after** the Ubuntu verification, Windows verification, PostgreSQL integration and full-history secret-scan jobs pass for the exact pushed SHA, fast-forwarding local `main` to that commit with `git merge --ff-only`;
  3. pushing only `main` with an explicit refspec.

  No force-push, merge commit, squash, rebase, amend, branch deletion or tag push is authorized.
- **Not yet recorded here:** the push, the CI results and the `main` update happen after this commit, so they are reported in the session handoff.
- **Still open:** Compose remains unverified (never run). M2b, M2c and overall M2 completion remain pending.

## Prompt 33: Implement M2b API-key authentication and tenant context

- **Stage:** Implementation, milestone M2b (staged for review, no commit)
- **Date:** 2026-10-12 (session date)

````text
Prompt 33 — Implement M2b API-key authentication and tenant context

Work only in D:\Claude\evidenceguard_agentic_rag. Read CLAUDE.md, the implementation plan, relevant ADRs and existing contracts before editing.

Verify:
- Local main and origin/main:
  e2dee5cf199cfa2b0ecbdc4d55a2cd7ea5865c00
- Working tree clean.
- Origin:
  https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git

Create feat/api-key-authentication from that exact main commit.

Implement M2b only. Leave all work staged and uncommitted for external review. Do not push, merge, rewrite history, install system tools, start Docker or connect to the existing local PostgreSQL service.

Scope

1. API-key primitives
- Use Python secrets to generate a cryptographically random secret with at least 256 bits of entropy and a separately generated lookup prefix.
- Define one strict, bounded key format and document it.
- Store only the prefix and SHA-256 digest of the secret in the existing api_keys table.
- Verify the digest using hmac.compare_digest.
- Never log credentials or include them in representations, errors or API responses.
- Use a secret wrapper for any object carrying the plaintext key.
- Avoid new dependencies unless necessary.

2. Persistence authentication
- Look up keys by their globally unique prefix.
- Reject unknown, malformed, incorrect and revoked keys uniformly.
- Join the owning user using both tenant_id and user_id.
- Derive tenant, actor and role only from stored records.
- Read current role and revocation state on authentication; do not introduce credential caching.
- Manage sessions explicitly and close them on every outcome.
- Keep database code in persistence and preserve package import boundaries.

3. Authenticated API boundary
- Add GET /v1/me returning only tenant_id, actor_id and role.
- Accept credentials only through Authorization: Bearer.
- Reject duplicate Authorization headers and malformed or oversized credentials.
- Missing or invalid credentials return generic 401 problem+json with WWW-Authenticate: Bearer.
- Preserve request-ID correlation and existing privacy-safe logging.
- Tenant headers, query parameters and other submitted values must not override the authenticated scope.
- Document the security scheme in OpenAPI.
- Add only the database/session wiring required for authentication and /v1/me. General vendor wiring and /readyz remain M2c.
- Provide an explicit injection seam for tests.
- Importing modules, constructing the app and calling /healthz must still work without database configuration or a database connection.
- Manage any app-owned engine lifecycle explicitly. Configuration or database failures must not expose URLs or exception text.

4. Roles
- Add ADMIN to the domain Role enum and map stored roles explicitly.
- Preserve existing approval authorization: only APPROVER can approve or finalize. ADMIN gets no approval bypass.
- Update the ActorContext documentation to distinguish authenticated API construction from trusted direct domain callers.

5. Admin CLI
Register eg-admin in the existing distribution, under the API application package, with:
- seed-demo: create a minimal deterministic synthetic tenant/user fixture for two tenants and the three roles.
- create-key: require explicit tenant and user IDs; verify ownership; create the key transactionally.
- revoke-key: require explicit tenant scope and key identifier; revoke without deleting history.

Rules:
- seed-demo is idempotent, creates no API keys, and never resets existing roles or revocations.
- No sample document corpus or ingestion work yet.
- Print a newly created plaintext key only once, to stdout, after its database transaction succeeds.
- Do not accept plaintext secrets as command-line arguments.
- CLI help and module imports need no database configuration.
- Use generic safe errors and nonzero exit codes.
- Do not execute these commands against a real database locally.

6. Tests
Keep unit/API tests database-independent through explicit test doubles.

Cover:
- Key generation, format, bounded parsing and secret-safe representations.
- Wrong secret, unknown prefix, malformed input and revoked key.
- Duplicate authorization headers.
- Authenticated tenant/user/role mapping and tenant-header spoofing.
- Generic 401 bodies, challenge headers and matching request IDs.
- Health and imports without database settings.
- Session cleanup and failure paths.
- ADMIN cannot approve or finalize.
- CLI output only after successful commit, safe failure output and help without settings.

Add real PostgreSQL integration tests for:
- Key creation, successful authentication and revocation.
- Cross-tenant ownership rejection.
- seed-demo idempotency.
- Current stored role reflected in authentication.

Use the existing disposable-database guard and CI integration job. Do not weaken required-integration enforcement. Local PostgreSQL checks remain skipped until publication is authorized and CI passes.

7. Documentation
- Add ADR-0005 for API-key authentication and its limits.
- Update README, plan and threat model for M2b's implemented scope.
- Correct current-status statements saying M2a is not merged.
- Record M2a main at e2dee5c:
  CI run 38159547345, secret-scan run 38159547321.
  The external reviewer retrieved the main integration log:
  "10 passed, 250 deselected in 2.64s".
- Preserve the earlier 9ad7dae verification record.
- Keep Compose unverified, M2b's new integration verification pending, M2c pending and overall M2 incomplete.
- State remaining API-key limitations plainly, including possession-based access and no rate limiting yet.
- Append this prompt verbatim to prompts.md with truthful outcomes. Preserve earlier entries.

Verification
Run locked synchronization, Ruff formatting/linting, strict Mypy, the full local database-independent suite, build, isolated installed-wheel imports/CLI-help checks, git diff --cached --check and staged Gitleaks scanning.

Do not print newly generated real credentials in the review handoff. Use clearly synthetic test markers.

Final handoff
- Explain behavior, architectural choices and remaining limits.
- Include the COMPLETE staged diff excluding prompts.md directly in fenced diff blocks.
- Never truncate. Split into numbered parts at file boundaries and provide every part.
- Use a gitignored .local/ diff file only if response limits prevent full inclusion.
- Report prompt-history additions, exact verification results, skipped checks, staged paths, HEAD and Git status separately.
- Confirm nothing was committed or pushed and no local database was contacted.
````

**Outcome (M2b implementation pending review; staged, not committed or pushed):**
- **Starting state verified:** local `main` and `origin/main` at `e2dee5c`, a clean tree, the expected origin. Branch `feat/api-key-authentication` was created from `e2dee5c`.
- **Persistence:**
  - `credentials` holds the key primitives: the 64-character format `egk_<16-hex prefix>_<43-character secret>`, with 256-bit secrets from `secrets`, SHA-256 digests, `hmac.compare_digest`, and `SecretStr` wrappers;
  - `auth.ApiKeyAuthenticator` looks keys up by prefix, joins the user on `tenant_id` and `user_id`, maps roles explicitly, rejects every failure uniformly, does no caching, and closes its session on every outcome;
  - `accounts.DatabaseAdminStore` provides the idempotent synthetic `seed-demo`, ownership-checked transactional key creation, and revocation that keeps the row.
- **API:**
  - `GET /v1/me` returns only `tenant_id`, `actor_id` and `role`;
  - credentials are accepted only from one Bearer header. Duplicate, oversized, non-ASCII and malformed headers are rejected;
  - authentication failures get a generic 401 with `WWW-Authenticate: Bearer`, and database or configuration failures a generic 503;
  - OpenAPI documents the `ApiKey` scheme;
  - `create_app(authenticator=...)` is the injection seam. The default app-owned authenticator creates its engine lazily and disposes it on shutdown.
- **Domain:** `Role.ADMIN` was added, with no report-editing or approval rights, and the `ActorContext` documentation was updated.
- **`eg-admin`** is registered, with `seed-demo`, `create-key` and `revoke-key`.
- **Documentation:** ADR-0005 was added. README, plan, threat model and ADR-0004 were updated, correcting the statements that M2a was not merged and recording `main` at `e2dee5c` (CI run 38159547345, secret-scan run 38159547321, reviewer-retrieved integration log `10 passed, 250 deselected in 2.64s`). The `9ad7dae` record is preserved.
- **Tests:** database-independent tests were added for the key primitives, the authenticator (through a session double), the API boundary (through an injected authenticator) and `eg-admin` (through a fake store). Four PostgreSQL integration tests were added to the existing guarded module.
- **Verified locally** (Windows, Python 3.12.15): the locked sync, Ruff format and lint, strict Mypy (48 files), and the full suite (344 passed, 14 PostgreSQL integration tests skipped). Also the integration collection (14) and the required-mode usage error (exit 4), the build, and the isolated installed-wheel imports with `/healthz`, `/v1/me` 401 and CLI help without database settings, plus the staged whitespace and Gitleaks checks. Exact results are in the session handoff.
- **Not verified:**
  - The four new PostgreSQL integration tests and the `eg-admin` database operations have **not** run against PostgreSQL. They are pending an authorized publication and CI.
  - Compose remains unverified, M2c is pending, and M2 is incomplete.
  - No `eg-admin` command was run against a database, and no local database was contacted.

## Prompt 34: Correct M2b CLI error privacy and demo-role reporting

- **Stage:** Correction, milestone M2b (staged for review, no commit)
- **Date:** 2026-10-12 (session date)

````text
Prompt 34 — Correct M2b CLI error privacy and demo-role reporting

Work only in D:\Claude\evidenceguard_agentic_rag. Follow CLAUDE.md.

Verify:
- Branch feat/api-key-authentication
- HEAD e2dee5cf199cfa2b0ecbdc4d55a2cd7ea5865c00
- The reported 23 M2b files staged.
- Nothing unstaged or untracked.

Record the pre-edit staged tree for the incremental review diff. Preserve the existing implementation.

Do not commit, push, merge, start Docker or contact any database.

Correction 1: CLI usage-error privacy

admin.main calls argparse before its safe error handling. Default argparse errors echo invalid UUID values and unrecognized arguments, including a mistakenly submitted key.

Make usage errors safe across the root parser and every subparser:
- Retain exit code 2 and useful static usage/help.
- Never print supplied argument values or argparse's raw diagnostic message.
- Handle invalid UUIDs, unknown commands/options, extra positional arguments and missing required arguments through the safe boundary.
- Keep --help working with exit code 0 and without database configuration.
- Do not allow parsing failures to open the store.
- Avoid a new dependency.

Add regression tests with synthetic secret markers in invalid UUID values and unknown/extra arguments. Assert the marker is absent from stdout and stderr, exit code is 2, and the store was never opened.

Correction 2: seed-demo reports actual stored records

DatabaseAdminStore.seed_demo currently appends DemoUser using the requested role even when ON CONFLICT DO NOTHING preserves a different stored role.

After ensuring each user exists:
- Read its actual tenant and role.
- Return the actual stored role in DemoUser and CLI output.
- Preserve existing roles, keys and revocations.
- If an existing deterministic user ID belongs to another tenant, refuse with a fixed safe AccountError rather than reporting it as belonging to the demo tenant.
- Preserve transactional rollback and idempotency.

Update the PostgreSQL idempotency test:
- Change a stored reviewer's role to approver.
- Reseed and assert both the returned record and stored row remain approver.
- Preserve assertions about row counts and revocation.
- Add coverage for a conflicting deterministic user ID owned by another tenant.

Add appropriate database-independent coverage for CLI reporting of the role returned by the store.

Documentation and history:
- Update ADR-0005 and relevant privacy/reporting descriptions narrowly.
- Append this prompt verbatim and a truthful outcome note to prompts.md.
- Record that the reviewer inspected the diff and reproduced argparse echoing in isolation, but did not run the project suite.
- Preserve earlier entries and keep new PostgreSQL verification pending.

Verification:
- Demonstrate the new relevant regression tests fail against the previous behavior, without contacting a database.
- Run Ruff format/lint, strict Mypy and the full local suite with PostgreSQL tests skipped.
- Build and repeat installed-wheel CLI help and safe usage-error checks.
- Run git diff --cached --check and the staged Gitleaks scan.

Leave the work staged and uncommitted.

Final handoff:
- Explain the corrections and verification limits.
- Include the COMPLETE incremental diff against the recorded pre-edit staged tree, excluding prompts.md, directly in fenced diff blocks.
- Do not truncate; split into numbered parts at file boundaries if needed.
- Report prompt-history additions, exact check results, staged paths, HEAD and Git status separately.
- Correct the added/modified file-count breakdown: the previous handoff's category counts did not match its listed paths.
````

**Outcome (correction pending review; staged, not committed or pushed):**
- **Starting state verified:** branch `feat/api-key-authentication`, HEAD `e2dee5c`, 23 M2b files staged (10 added, 13 modified), nothing unstaged or untracked. The pre-edit staged tree was `8444eb3f523322df0755392567910349db34b24f`.
- **Review findings:** argparse usage errors in `eg-admin` echoed submitted values, and `seed_demo` reported the requested role instead of the stored one. The reviewer inspected the diff and reproduced the argparse echoing in isolation, but did not run the project suite.
- **Correction 1:** `SafeArgumentParser` is used by the root parser and, through inheritance, by every subparser.
  - Usage errors print only the static usage line and a fixed message, exit 2, and never open the store.
  - Option abbreviations are disabled, and `--help` is unchanged.
- **Correction 2:** `seed_demo` reads back each user's stored tenant and role and reports the stored role. A demo user ID owned by another tenant now raises `DemoUserConflictError`, rolling back the whole transaction. The demo-tenant slug check now also handles a missing slug.
- **Tests:**
  - CLI tests cover usage errors with synthetic markers (invalid UUIDs, unknown options, abbreviations, extra positionals, unknown commands), missing arguments, a key pasted by mistake, and reporting of store-returned roles.
  - A new `tests/test_accounts.py` exercises the real `seed_demo` against an in-memory session double.
  - The PostgreSQL idempotency test now expects the stored `approver` role in both the returned record and the row. A new PostgreSQL test covers the cross-tenant demo user conflict.
- **Comparison with the previous code:** the pre-edit `admin.py` and `accounts.py` were restored temporarily in the working tree, then restored with matching SHA-256. No database was contacted.
  - With the previous `admin.py`, 19 of the 20 selected CLI tests failed. Store-returned role reporting already passed, because that bug was in the store.
  - With the previous `accounts.py` (only `DemoUserConflictError` shimmed so the tests import), the stored-role and conflict tests failed. The first-seed and tenant-slug tests passed.
- **Documentation:** ADR-0005, the README and the threat model were updated narrowly.
- **Verified locally** (Windows, Python 3.12.15): Ruff format and lint, strict Mypy (49 files), and the full suite (368 passed, 15 PostgreSQL tests skipped). Also the build, the installed-wheel CLI help and safe usage-error checks, and the staged whitespace and Gitleaks checks. Exact results are in the session handoff.
- **Not verified:** the new and updated PostgreSQL tests have not run, and are pending an authorized publication and CI. Compose remains unverified, M2c is pending, and M2 is incomplete.

## Prompt 35: Complete parser consistency and commit reviewed M2b locally

- **Stage:** Final parser adjustment and local commit of reviewed milestone M2b (no push)
- **Date:** 2026-10-12 (session date)

````text
Prompt 35 — Complete parser consistency and commit reviewed M2b locally

Work only in D:\Claude\evidenceguard_agentic_rag. Follow CLAUDE.md.

Verify:
- Branch feat/api-key-authentication
- HEAD e2dee5cf199cfa2b0ecbdc4d55a2cd7ea5865c00
- Exactly the reported 24 files staged.
- Nothing unstaged or untracked.
- Expected origin and noreply author/committer identity.

Record the accepted staged tree before editing.

The reviewer accepts the Prompt 34 privacy and stored-role corrections for a local commit, subject to this precise parser adjustment:
- Pass allow_abbrev=False explicitly to the seed-demo, create-key and revoke-key subparser constructors.
- The root setting does not propagate to them.
- Add focused tests showing abbreviated --tenant-id, --user-id and --prefix options are refused without opening the store. Supply all other required arguments so rejection cannot be caused by an unrelated missing argument.
- Preserve generic usage errors and unchanged help behavior.

Make no other application, dependency or architecture changes.

Run the CLI tests, full local suite with PostgreSQL tests skipped, Ruff formatting/linting and strict Mypy.

Update prompts.md:
- Record acceptance based on the original and correction diffs and reported Windows checks.
- State that the reviewer reproduced argparse behavior in isolation but did not run the project suite.
- Record this final parser adjustment and its actual verification results.
- Append this prompt verbatim and a truthful outcome note.
- Preserve earlier entries.
- Keep PostgreSQL verification, Compose, M2c and overall M2 pending.

Inspect the complete staged diff and private-content checks. Run git diff --cached --check and the staged Gitleaks scan. Commit only if all checks pass.

This prompt authorizes one local commit:
feat: add API-key authentication and tenant administration

After committing, run the full-history Gitleaks scan.

Final handoff:
- Full commit SHA, parent, subject and committed paths.
- COMPLETE incremental diff against the recorded accepted staged tree, excluding prompts.md, directly in fenced diff blocks.
- Exact verification results and remaining limits.
- Prompt-history additions and final Git status.
- Confirm that changes outside the specified parser adjustment, its tests and prompts.md were absent.

Do not push, merge, amend, rebase, change global configuration, start Docker or contact any database. Leave the working tree clean.
````

**Review note (recorded with Prompt 35):** the external reviewer accepted M2b, including the Prompt 34 CLI-privacy and stored-role corrections, for a local commit. The acceptance relied on the original Prompt 33 diff, the Prompt 34 incremental diff and Claude's reported Windows checks (Prompt 34: 368 passed, 15 PostgreSQL tests skipped). The reviewer reproduced the argparse behaviour in isolation but did not run the project suite. One final adjustment was required: subparsers do not inherit the root parser's `allow_abbrev=False`.

**Outcome (committed locally; not pushed):**
- **Starting state verified:** branch `feat/api-key-authentication`, HEAD `e2dee5c`, exactly 24 files staged, nothing unstaged or untracked, the expected origin and the noreply identity. The accepted staged tree was `859e078ab6ec9ae28a3f4e89fc4187426d3a388e`.
- **The finding was reproduced first:** `create-key --tenant <uuid> --user-id <uuid>` was accepted and reached the store.
- **Parser adjustment:** `allow_abbrev=False` is now passed explicitly to the `seed-demo`, `create-key` and `revoke-key` subparser constructors.
- **Tests:**
  - 7 focused cases abbreviate exactly one of `--tenant-id`, `--user-id` or `--prefix`, with every other required argument valid. Each must exit 2 with the generic usage error, without echoing anything or opening the store.
  - A control test confirms that the same arguments spelled in full reach the store.
  - A test confirms that every subparser is a `SafeArgumentParser` with abbreviations disabled.
- **Against the accepted `admin.py`** (restored temporarily in the working tree, then restored with a matching SHA-256), 8 of these tests failed and the control passed.
- **No other change:** no application, dependency or architecture change beyond this adjustment and its tests.
- **Verified locally** (Windows, Python 3.12.15): CLI tests (51 passed), the full suite (377 passed, 15 PostgreSQL tests skipped), Ruff format and lint, strict Mypy (49 files). The staged whitespace check, the private-content check and the staged Gitleaks scan were run before committing, and a full-history Gitleaks scan after. Exact results are in the session handoff.
- **Commit:** one local commit, `feat: add API-key authentication and tenant administration`, whose parent is `e2dee5c`. It contains this note, so its SHA is reported in the session handoff.
- **Pending:** the M2b PostgreSQL integration tests (15 in total locally skipped, including M2a's) await an authorized publication and CI. Compose remains unverified, M2c is pending, and M2 is incomplete. Nothing was pushed or merged, and no database was contacted.

**Review note (added with Prompt 36):** the external reviewer accepted the final Prompt 35 parser diff, which passes `allow_abbrev=False` to each subparser and adds focused tests. The acceptance relied on that diff and on Claude's reported Windows checks: 377 passed, 15 PostgreSQL integration tests skipped. The reviewer did not run the project suite.

## Prompt 36: Publish reviewed M2b and verify branch CI

- **Stage:** Publication of branch `feat/api-key-authentication` (no merge, `main` untouched)
- **Date:** 2026-10-12 (session date)

````text
Prompt 36 — Publish reviewed M2b and verify branch CI

Work only in D:\Claude\evidenceguard_agentic_rag. Follow CLAUDE.md.

This prompt authorizes publishing feat/api-key-authentication only. It does not authorize merging or pushing main.

Verify:
- Branch feat/api-key-authentication
- HEAD cfe5e3274d0461801f72cdb2b3e96afa51cd323f
- Parent e2dee5cf199cfa2b0ecbdc4d55a2cd7ea5865c00
- Working tree clean.
- Expected origin:
  https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git
- Author and committer use:
  257921624+mathewmljourney93@users.noreply.github.com

Read remote refs. Confirm main remains e2dee5c and the new feature branch does not exist remotely. Stop on unexpected changes or divergence.

Inspect everything that will become public relative to remote main:
- Commit identities, tracked paths and full diff, including prompts.md.
- No .local/ files, backups, real credentials or unintended private information.
- Confirm both workflows trigger on this branch and required integration enforcement remains enabled.

Change prompts.md only:
- Record the reviewer's acceptance of the final parser diff, based on the diff and reported Windows checks: 377 passed, 15 skipped.
- State that the reviewer did not run the project suite.
- Append this prompt verbatim and a truthful publication preflight note.
- Preserve earlier entries.
- Do not record publication or CI success before they happen.

Inspect and stage that update. Run git diff --cached --check and the staged Gitleaks scan.

Create one documentation commit:
docs: record M2b branch publication authorization

Run gitleaks git --redact --verbose . against full history. Proceed only if all checks pass.

Push this single explicit ref:
git push --set-upstream origin refs/heads/feat/api-key-authentication:refs/heads/feat/api-key-authentication

Confirm the remote feature SHA matches local HEAD and remote main is unchanged.

Inspect Actions runs for the exact published SHA. Report:
- Ubuntu verification.
- Windows verification.
- PostgreSQL integration.
- Full-history secret scan.

Obtain the integration test count from the job log if accessible. If logs are unavailable, distinguish successful job status from an inferred test count.

If a check fails, report its failing step and relevant redacted output. Do not change code or push fixes in this task.
If checks remain pending, report their actual status without claiming continued monitoring unless a persistent process exists.

Final handoff:
- Published SHA, branch and remote refs.
- Prompt-history commit and additions.
- Scan results.
- Workflow and job links/results for that exact SHA.
- Integration test count and its evidence, or the access limitation.
- Final Git status.
- Complete incremental diff outside prompts.md, if any; otherwise state none exists.

Do not merge, push main, force-push, rewrite history, start Docker, contact a local database or change global configuration. Keep Compose unverified, M2c pending and overall M2 incomplete.
````

**Preflight note (recorded before publication):**
- **Starting state verified:** branch `feat/api-key-authentication`, HEAD `cfe5e32` (parent `e2dee5c`), a clean tree, the expected origin. The noreply identity is the effective author and committer.
- **Remote refs, read before this commit:** `main` and `feat/persistence-foundation` are both `e2dee5c`, and `feat/api-key-authentication` does not exist on the remote. Remote `main` is an ancestor of local HEAD, so history has not diverged.
- **Content to be published** (relative to remote `main`: commit `cfe5e32` plus this prompt-history commit; 24 files in `cfe5e32`):
  - the noreply identity throughout;
  - no `.local/` files, bundles or backups tracked;
  - no key-shaped literals or personal identifiers;
  - the only credential-like value is a labelled fake test marker, and every email-pattern match is a code decorator.
- **Workflows:** both `ci.yml` and `secret-scan.yml` trigger on `push` to any branch. The workflows and `tests/conftest.py` are unchanged from `main`, so the integration job still runs with `EG_REQUIRE_INTEGRATION=1`.
- **Authorization:** Prompt 36 authorizes pushing only `feat/api-key-authentication`. It does not authorize merging, pushing `main`, force-pushing or rewriting history.
- **Not yet recorded here:** the push and CI results happen after this commit, so they are reported in the session handoff.
- **Still open:** M2b's PostgreSQL integration verification is pending until CI passes. Compose remains unverified, M2c is pending, and M2 is incomplete.

**Outcome (Prompt 36, publication and CI; added with Prompt 37):**
- **Published:** the branch `feat/api-key-authentication` was pushed as `b2f7f2310cb265dcaab9a5c3055b3d762fa02d46`, with its upstream set, using `git push --set-upstream origin refs/heads/feat/api-key-authentication:refs/heads/feat/api-key-authentication` (exit 0).
  - The remote branch SHA matched local HEAD.
  - Remote `main` stayed at `e2dee5c`.
  - No other ref was pushed, and nothing was merged or force-pushed.
- **Checks before the push:** `git diff --cached --check`, the staged Gitleaks scan, and a full-history Gitleaks scan after the documentation commit `b2f7f23` all passed.
- **CI for `b2f7f23`, all successful:**
  - [ci run 38166627885](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38166627885), with jobs:
    - [`verify (ubuntu-24.04, Python 3.12)` 114550418430](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38166627885/job/114550418430);
    - [`verify (windows-2025, Python 3.12)` 114550418222](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38166627885/job/114550418222);
    - [`integration (ubuntu-24.04, PostgreSQL 17 + pgvector)` 114550418432](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38166627885/job/114550418432).
  - [secret-scan run 38166627930](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38166627930), with job [`Gitleaks (full history)` 114550418550](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38166627930/job/114550418550).
- **Integration-test evidence:**
  - Claude again could not read the integration job log: the anonymous log download was refused with HTTP 403 ("Must have admin rights to Repository"), and `gh` was not installed. Claude therefore reported the successful job status separately from an inferred count of 15 passed.
  - The external reviewer later retrieved the log independently. It reports `15 passed, 377 deselected in 2.49s`, so all fifteen integration tests passed and none was skipped. The reviewer inspected GitHub evidence and did not run the project suite locally.
- **Correction:** Claude's session handoff for Prompt 36 predicted `15 passed, 362 deselected`. That was wrong. The deselected count is the 377 non-integration tests, as the log shows. The prediction was in the handoff only, not in this file.
- **Still open:** M2b is not merged into `main`. Compose remains unverified, M2c is pending, and M2 is incomplete.

## Prompt 37: Record verified M2b CI results

- **Stage:** Documentation update (staged for review, no commit)
- **Date:** 2026-10-12 (session date)

````text
Prompt 37 — Record verified M2b CI results

Work only in D:\Claude\evidenceguard_agentic_rag. Follow CLAUDE.md.

Verify:
- Branch feat/api-key-authentication
- HEAD and upstream:
  b2f7f2310cb265dcaab9a5c3055b3d762fa02d46
- Working tree clean.
- Remote main remains:
  e2dee5cf199cfa2b0ecbdc4d55a2cd7ea5865c00

Update documentation only. Do not change application code, tests, dependencies, workflows or configuration.

Verified evidence for b2f7f23:
- CI run 38166627885 succeeded.
- Ubuntu job 114550418430 succeeded.
- Windows job 114550418222 succeeded.
- PostgreSQL integration job 114550418432 succeeded.
- Secret-scan run 38166627930 and job 114550418550 succeeded.
- The external reviewer independently retrieved the integration log:
  "15 passed, 377 deselected in 2.49s"
- All fifteen integration tests passed; none was skipped.
- The reviewer inspected GitHub evidence and did not run the project suite locally.

Update README.md, docs/plan.md, ADR-0005 and docs/threat-model.md narrowly:
- Mark M2b reviewed and verified in CI, and ADR-0005 accepted.
- Identify the exact tested commit and link the runs/jobs.
- Replace obsolete M2b PostgreSQL-pending statements.
- Keep M2b not yet merged into main.
- Preserve API-key limitations, Compose as unverified, M2c as pending and overall M2 incomplete.

Update prompts.md:
- Add a separate outcome note under Prompt 36 recording publication and CI results.
- Preserve the earlier anonymous-log access limitation as historical fact.
- Record that the external reviewer subsequently retrieved the log.
- Correct the earlier inferred count through the new note: the actual result is 15 passed, 377 deselected, not 362 deselected. Do not rewrite the historical entry.
- Append this prompt verbatim with a truthful outcome note.
- Preserve earlier entries.

Check documentation links, consistency, staged private content, git diff --cached --check and the staged Gitleaks scan.

Leave changes staged and uncommitted. Do not push, merge, rewrite history, start Docker or contact a database.

Final handoff:
- Include the COMPLETE staged diff excluding prompts.md directly in fenced diff blocks.
- Never truncate; split into numbered parts at file boundaries if necessary.
- Report prompt-history additions, exact verification results, staged paths, HEAD and final Git status separately.
````

**Outcome (documentation update pending review; staged, not committed):**
- **Starting state verified:** branch `feat/api-key-authentication`, HEAD and upstream `b2f7f23`, a clean tree, remote `main` `e2dee5c`.
- **Prompt history:** a separate outcome note under Prompt 36 records the publication and CI results.
  - It keeps Claude's anonymous-log limitation (HTTP 403) as historical fact.
  - It records that the reviewer later retrieved the log, which reports `15 passed, 377 deselected in 2.49s`.
  - It corrects Claude's handoff prediction of 362 deselected to the actual 377.
- **Documentation:** README, `docs/plan.md`, ADR-0005 and `docs/threat-model.md` were updated narrowly.
  - M2b is marked reviewed and verified in CI at `b2f7f23`, with links to the exact runs and jobs, and ADR-0005 is marked Accepted.
  - The obsolete pending statements for M2b's PostgreSQL tests were replaced.
  - The documents say M2b is not yet merged into `main`, keep the API-key limitations and Compose as unverified, and keep M2c pending and M2 incomplete.
- **Checks:** the six Actions links returned HTTP 200, relative links and anchors resolve, no stale M2b wording remains, `git diff --cached --check` passed, the private-content check passed, and the staged Gitleaks scan passed. Exact results are in the session handoff.
- **No application checks were run;** only documentation changed. Nothing was committed or pushed, Docker was not started, and no database was contacted.

**Review note (added with Prompt 38):** the external reviewer accepted the Prompt 37 documentation diff. The acceptance relied on the reviewed diff and on GitHub evidence the reviewer retrieved independently: CI run 38166627885 and secret-scan run 38166627930 for `b2f7f23`, with the integration log reporting `15 passed, 377 deselected in 2.49s`. The reviewer did not run the project suite locally. Compose remains unverified, M2c is pending and M2 is incomplete.

## Prompt 38: Commit verified M2b documentation and fast-forward main

- **Stage:** Local documentation commit, publication of `feat/api-key-authentication`, and an authorized fast-forward of `main`
- **Date:** 2026-10-12 (session date)

````text
Prompt 38 — Commit verified M2b documentation and fast-forward main

Work only in D:\Claude\evidenceguard_agentic_rag. Follow CLAUDE.md.

This prompt authorizes:
- One local commit of the reviewed documentation.
- Publishing feat/api-key-authentication.
- Fast-forwarding and publishing main only after all required feature-branch checks pass.

Verify:
- Branch feat/api-key-authentication
- HEAD and upstream:
  b2f7f2310cb265dcaab9a5c3055b3d762fa02d46
- Exactly these five files staged:
  README.md
  docs/decisions/0005-api-key-authentication.md
  docs/plan.md
  docs/threat-model.md
  prompts.md
- Nothing unstaged or untracked.
- Expected origin.
- Remote main:
  e2dee5cf199cfa2b0ecbdc4d55a2cd7ea5865c00

Read current remote refs. Stop on unexpected changes or divergence.

Record the accepted staged tree. Modify prompts.md only:
- Add a separate acceptance note under Prompt 37, based on the reviewed documentation diff and the GitHub evidence independently retrieved by the reviewer.
- Append this prompt verbatim and a truthful preflight note.
- Preserve earlier entries.
- Do not record future publication, merge or CI results as completed.

Confirm the four other documentation files remain byte-identical to their accepted staged versions.

Verify author and committer use:
257921624+mathewmljourney93@users.noreply.github.com

Inspect staged private content, run git diff --cached --check and the staged Gitleaks scan. Commit only if all checks pass:
docs: record verified M2b results and main publication authorization

Run the full-history Gitleaks scan before publication.

Push only:
git push origin refs/heads/feat/api-key-authentication:refs/heads/feat/api-key-authentication

Confirm the remote SHA matches local HEAD.

Inspect Actions for that exact SHA. Require successful:
- Ubuntu verification.
- Windows verification.
- PostgreSQL integration.
- Full-history secret scan.

If a check fails, report the failing step and relevant redacted output; do not change code or merge.
If checks remain pending, report their actual status and leave main unchanged.

After all four checks pass:
- Fetch main and the feature branch.
- Reconfirm remote main is still the expected baseline.
- Confirm main is an ancestor of the verified feature tip.
- Switch to local main and ensure no divergent local commits exist.
- Fast-forward with git merge --ff-only to the exact verified feature SHA.
- Push only:
  git push origin refs/heads/main:refs/heads/main

Never force-push, create a merge commit, squash, rebase, amend, delete branches or push tags.

Confirm local main, remote main and the verified feature tip match. Inspect the main workflows for that exact SHA and report their actual results.

Final handoff:
- Commit SHA, parent, subject and committed paths.
- Prompt-history additions.
- Feature and main workflow/job links and results.
- Integration count if logs are accessible; otherwise distinguish inference from direct evidence.
- Scan results, remote refs and final Git status.
- Complete incremental diff outside prompts.md against the accepted staged tree, if any; otherwise state none exists.

Application checks need not be rerun locally because only documentation changed.

Do not change application code, start Docker, contact a local database or change global configuration. Keep Compose unverified, M2c pending and overall M2 incomplete.
````

**Preflight note (recorded before the commit, publication and any change to `main`):**
- **Starting state verified:** branch `feat/api-key-authentication`, HEAD and upstream `b2f7f23`, the expected origin, the noreply identity.
  - Exactly the five reviewed documentation files were staged, with nothing unstaged or untracked.
  - The accepted staged tree was `46dc757e6b6adf0a3bc52b9613d1a3dfb4487d82`.
- **Remote refs, read before this commit:**
  - `main` (and `feat/persistence-foundation`) is `e2dee5c`, and local `main` matches it;
  - `feat/api-key-authentication` is `b2f7f23`;
  - remote `main` is an ancestor of the local feature HEAD, so history has not diverged.
- **This commit** adds only the reviewed Prompt 37 documentation and this prompt-history update.
- **Authorization:** Prompt 38 authorizes three things, in order:
  1. pushing the feature branch;
  2. **only after** Ubuntu verification, Windows verification, PostgreSQL integration and the full-history secret scan all pass for the exact pushed SHA, fast-forwarding local `main` to that commit with `git merge --ff-only`;
  3. pushing only `main`.

  No force-push, merge commit, squash, rebase, amend, branch deletion or tag push is authorized.
- **Not yet recorded here:** the push, the CI results and the `main` update happen after this commit, so they are reported in the session handoff.
- **Still open:** Compose remains unverified, M2c is pending, and M2 is incomplete.

## Prompt 39: Implement tenant-scoped vendors and database readiness

- **Stage:** Implementation, milestone M2c (staged for review, no commit)
- **Date:** 2026-10-12 (session date)

````text
Prompt 39 — Implement tenant-scoped vendors and database readiness

Work only in D:\Claude\evidenceguard_agentic_rag. Read CLAUDE.md, the plan, relevant ADRs and existing authentication/persistence code.

Verify:
- Local main and origin/main:
  277dfeaec7c1c64fa5ee92a3ce892823acc787fb
- Working tree clean.
- Expected origin.

Create feat/vendor-api-readiness from that exact commit.

Implement M2c only. Leave changes staged and uncommitted for external review. Do not push, merge, rewrite history, install system tools, start Docker or contact any local database.

1. Shared API database lifecycle
- Consolidate the minimal M2b database wiring into an app-owned resource shared by authentication, vendor operations and readiness.
- Initialize lazily; importing modules, constructing/starting the app and serving /healthz must still need no database configuration or connection.
- Dispose app-owned engines on shutdown.
- Preserve create_app(authenticator=...) compatibility and provide explicit database-independent test injection seams.
- Close sessions on every outcome. Writes commit before a successful response and roll back on failure.
- Keep synchronous database work off the async event loop.
- Set bounded connection and readiness-query timeouts.
- Preserve safe errors, secret masking and package import boundaries.

2. Vendor persistence
Use the existing vendors table; no schema migration is expected.
- Create, list and retrieve vendors through persistence code.
- Require an authenticated tenant scope for every operation.
- Get by both tenant_id and vendor ID; never retrieve globally and filter afterwards.
- List and total-count queries must both filter by tenant.
- Create takes tenant_id only from the authenticated actor.
- Translate only the specific vendor tenant/slug unique-constraint violation into a duplicate-slug conflict. Do not classify every IntegrityError as a duplicate.
- No update/delete, ingestion, jobs or report endpoints in this slice.

3. Vendor API
Implement:
- POST /v1/vendors → 201.
- GET /v1/vendors → a documented page object.
- GET /v1/vendors/{id} → vendor or generic 404.

Authorization:
- REVIEWER and APPROVER can use these routes.
- ADMIN receives generic 403, consistent with the plan's reviewer+ policy and existing lack of report rights.
- Missing/invalid credentials retain the existing generic 401.

Contracts:
- VendorCreate accepts only slug and name; reject extra fields, including tenant_id, actor_id and role, with 422.
- Bound slug/name to existing database lengths; use a documented lowercase slug grammar and reject blank names.
- Do not silently truncate values.
- Return only documented vendor fields.
- Duplicate slug within one tenant returns generic 409; the same slug in another tenant is valid.
- Foreign-tenant and nonexistent IDs return indistinguishable 404 responses.
- Tenant headers and query parameters never override authenticated scope.

Pagination:
- limit defaults to 20, allowed 1–100.
- offset defaults to 0, allowed 0–10,000.
- Return items, total, limit and offset.
- Use deterministic ordering with a unique tie-breaker.
- Document that offset pagination does not provide a snapshot during concurrent changes.

Preserve problem+json, request IDs, fixed public error messages, privacy-safe route-template logging and OpenAPI documentation.

4. GET /readyz
Unauthenticated, as specified in the plan:
- Return {status, checks}.
- Check database connectivity and whether the applied Alembic revision set matches the packaged migration heads.
- Return 200 only when both pass.
- Return 503 for missing/invalid configuration, unreachable database, missing version table or mismatched migration revisions.
- Expose only fixed check names/status values; never URLs, revision values, SQL or exception text.
- Never apply migrations or create extensions.
- Keep /healthz independent and successful when readiness fails.
- A reachable but unmigrated database must not be reported ready.

5. Tests
Unit/API tests remain database-independent using explicit doubles.

Cover:
- Authorization for every role.
- Tenant-scoped create/list/get/count.
- Body tenant-field rejection and header/query spoofing.
- Same-tenant duplicate versus cross-tenant identical slug.
- Foreign/nonexistent ID parity.
- Validation and pagination bounds/order.
- Commit, rollback and session cleanup, including commit failure.
- Safe readiness failure paths and migration mismatch.
- Health independence, lazy shared resources and shutdown disposal.
- Request-ID/problem responses and absence of submitted markers in logs/errors.

Add real PostgreSQL integration tests using the existing disposable guard for:
- Authenticated create/list/get through the API.
- Two-tenant isolation and identical slugs.
- Duplicate creation and rollback.
- Pagination.
- Ready, unmigrated and revision-mismatch cases.

Preserve existing migration/authentication tests and required-integration enforcement. Do not run integration tests locally.

6. Documentation and history
- Add ADR-0006 for tenant-scoped vendor access, shared lifecycle and readiness.
- Update README, plan and threat model for the implemented M2c scope and limits.
- Correct current-status wording saying M2b is not merged.
- Record main at 277dfea:
  CI run 38167398488, secret-scan run 38167398504.
  The external reviewer retrieved its integration log:
  "15 passed, 377 deselected in 3.77s".
- Preserve earlier verification records.
- Keep M2c integration verification and overall M2 acceptance pending.
- Preserve Compose as unverified and existing API-key limitations.
- Append this prompt verbatim to prompts.md with truthful outcomes; preserve earlier entries.

Verification
Run locked synchronization, Ruff formatting/linting, strict Mypy, the full local suite with integration tests skipped, build, isolated installed-wheel API/CLI/import checks, git diff --cached --check and staged Gitleaks scanning.

Final handoff
- Explain behavior, architectural choices and remaining limits.
- Include the COMPLETE staged diff excluding prompts.md directly in fenced diff blocks.
- Never truncate; split into numbered parts at file boundaries and provide every part.
- Use a gitignored .local/ file only if response limits prevent full inclusion.
- Report prompt-history additions, exact check results, skipped tests, staged paths, HEAD and Git status separately.
- Confirm nothing was committed or pushed and no local database was contacted.
````

**Outcome (M2c implementation pending review; staged, not committed or pushed):**
- **Starting state verified:** local `main` and `origin/main` at `277dfea`, a clean tree, the expected origin. Branch `feat/vendor-api-readiness` was created from `277dfea`.
- **Shared lifecycle:**
  - `evidenceguard_api.database.AppDatabase` is one lazily started engine and session factory, shared by authentication, vendors and readiness. It replaces M2b's authenticator-private engine and is disposed on shutdown when app-owned.
  - The injection seams are `create_app(authenticator=, vendor_store=, readiness=, database=)` and `AppDatabase(engine_factory)`.
  - Bounded waits: connect 5 s (unless the URL sets `connect_timeout`), pool 10 s, readiness statement 2 s.
  - Routes and dependencies are synchronous, so they run in worker threads.
- **Vendors:**
  - `evidenceguard_persistence.vendors` queries are scoped by the actor's tenant in SQL: get by `(tenant_id, id)`, list and count with the same filter, ordering by `(slug, id)`.
  - Only the `uq_vendors_tenant_id_slug` violation becomes a duplicate.
  - The routes are `POST /v1/vendors` (201), `GET /v1/vendors` (page object, `limit` 1–100 default 20, `offset` 0–10,000) and `GET /v1/vendors/{id}` (generic 404 for foreign or missing IDs). Reviewers and approvers may use them; admins get a generic 403.
  - Only `slug` (pattern-bounded, 1–64) and `name` (1–200, not blank) are accepted, without truncation; a duplicate slug is a generic 409. There is no schema change.
- **`/readyz`:** unauthenticated; returns `{status, checks}` with fixed values. It is 200 only when `SELECT 1` succeeds and the applied Alembic revisions equal the packaged heads, and 503 otherwise. It is read-only and rolled back, and it never migrates.
- **Tests:**
  - Database-independent tests were added for the vendor API (injected authenticator and in-memory store), vendor persistence and store transactions (recording session), and readiness and the shared lifecycle.
  - Three existing tests were adapted to the new structure: the lazy-engine test in `tests/test_auth_api.py`, the unknown-path test in `tests/test_health.py`, which used `/readyz`, and the OpenAPI path list.
  - Six PostgreSQL integration tests were added to the existing guarded module.
- **Documentation:** ADR-0006 was added. README, plan, threat model and ADR-0005 were updated.
  - The statements that M2b was not merged were corrected.
  - `main` is recorded at `277dfea`: CI run 38167398488, secret-scan run 38167398504, and the reviewer-retrieved integration log `15 passed, 377 deselected in 3.77s`. Earlier verification records are preserved.
- **Verified locally** (Windows, Python 3.12.15): the locked sync, Ruff format and lint, strict Mypy (57 files), and the full suite (455 passed, 21 PostgreSQL integration tests skipped). Also the integration collection (21), the required-mode usage error (exit 4), the build, and the isolated installed-wheel API, CLI and import checks without database settings. Link checks, the staged whitespace check, the private-content check and the staged Gitleaks scan were also run. Exact results are in the session handoff.
- **Not verified:**
  - The six new PostgreSQL integration tests have **not** run against PostgreSQL. They are pending an authorized publication and CI.
  - Compose remains unverified, and M2c review and overall M2 acceptance are pending.
  - No local database was contacted.

## Prompt 40: Read-only resume and M2c review handoff

- **Stage:** Context restoration and review handoff for staged M2c (read-only; no file changes)
- **Date:** 2026-10-12 (session date)

````text
Resume EvidenceGuard after an overnight pause. This is a context-restoration and review handoff task, not an implementation task.

Read the repository’s CLAUDE.md first and follow its boundaries. Work only in:
D:\Claude\evidenceguard_agentic_rag

Do not inspect other projects or global Claude configuration.

Expected saved state
- Branch: feat/vendor-api-readiness
- HEAD: 277dfeaec7c1c64fa5ee92a3ce892823acc787fb
- Origin: https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git
- 22 M2c files staged.
- Nothing unstaged or untracked.
- M2c is uncommitted and has never been pushed.
- main was last verified at the same HEAD, with M2a and M2b complete.
- The external reviewer received the M2c handoff but has NOT completed its review or approved a commit.

First verify
Run read-only Git commands to confirm:
1. Working directory and Git root.
2. Current branch and full HEAD SHA.
3. Origin URL.
4. Git status, staged file list and staged diff summary.
5. Whether unstaged changes or untracked files exist.

If the state differs, report the differences and stop. Do not attempt to repair it, switch branches, discard changes or restage anything.

Restore project context
Read the current README.md, docs/plan.md, ADR-0005, ADR-0006 and the latest relevant entries in prompts.md. Use the repository’s actual contents as the source of truth.

M2c’s reported scope:
- Shared lazy application database resource for authentication, vendors and readiness.
- Tenant-scoped vendor persistence and authenticated create/list/get endpoints.
- Reviewer and approver access; admin has no bypass.
- Bounded limit/offset pagination.
- Generic privacy-safe errors.
- Unauthenticated /readyz checking database connectivity and exact Alembic revision agreement.
- /healthz remains database-independent.
- Updated documentation and six new PostgreSQL integration tests.

Previous-session verification was reported as:
- 455 tests passed; 21 PostgreSQL integration tests skipped.
- Ruff formatting, lint and strict Mypy passed.
- Build and isolated installed-wheel checks passed.
- Staged Gitleaks scan passed.
These are historical reported results, not checks you ran in this session. Do not claim otherwise.

Still pending:
- External review of the complete M2c diff.
- M2c PostgreSQL and GitHub Actions verification.
- Compose verification.
- Overall M2 acceptance.

Produce the review handoff
- Include the COMPLETE current staged diff, excluding prompts.md, directly in your response inside fenced diff blocks.
- Split it into numbered parts at file boundaries if needed.
- Do not truncate files or replace any portion with a summary.
- If response limits prevent a complete inline handoff, explicitly identify the omitted files and save the complete diff under the gitignored .local/ directory as a fallback.
- Separately summarize the latest prompt-history entries without reproducing the entire prompts.md.
- Report current Git state separately from historical verification results.
- Run git diff --cached --check and report its actual result.

Restrictions
- Do not change any tracked files, including prompts.md, during this read-only resume task.
- Do not implement fixes or add features.
- Do not commit, push, merge, amend, rebase, reset, stash or unstage.
- Do not install tools or dependencies, start servers or Docker, or contact any database.
- Do not rerun the application suite merely to restore context.
- Leave all existing staged work exactly as found.

Finish by confirming that M2c remains staged and uncommitted, awaiting external review.
````

**Outcome (read-only; recorded with Prompt 41 because Prompt 40 forbade file changes):**
- **State verified as expected:**
  - branch `feat/vendor-api-readiness`, HEAD `277dfea`, the expected origin;
  - the 22 M2c files staged, with nothing unstaged or untracked;
  - no remote `feat/vendor-api-readiness` branch;
  - local `main` at `277dfea`.
- **Handoff:** the complete staged diff, excluding `prompts.md`, was given inline in eight parts.
- **Checks:** `git diff --cached --check` printed nothing and exited 0. No tracked file was changed, and no test, server, Docker or database was run or contacted.

**Review note (added with Prompt 41):** the external reviewer inspected the supplied M2c diff and found two issues:
- `create_app()` chose `authenticator`, `vendor_store` and `readiness` with `or`, so an injected component that evaluates as false would be replaced by the database-backed default;
- `VendorCreate.name` did not reject the null character U+0000 before persistence.

The reviewer did not run the project suite. Both issues are corrected under Prompt 41 below. M2c remains uncommitted and is not accepted.

## Prompt 41: Correct M2c injected-component selection and null characters in vendor names

- **Stage:** Corrections to staged M2c work (no commit, no push)
- **Date:** 2026-10-12 (session date)

````text
Correct two findings from the external M2c review. Leave the result staged and uncommitted for another review.

Follow CLAUDE.md. Work only inside:
D:\Claude\evidenceguard_agentic_rag

Expected starting state
- Branch: feat/vendor-api-readiness
- HEAD: 277dfeaec7c1c64fa5ee92a3ce892823acc787fb
- Origin: https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git
- The existing 22 M2c files are staged.
- Nothing is unstaged or untracked.
- Nothing from M2c is committed or pushed.

Verify the state first. If it differs, report the difference and stop without repairing it.

Record the pre-edit staged tree so the correction handoff can show an exact incremental diff. Keep any review artifacts in gitignored .local/.

Correction 1: honour injected components regardless of truthiness
In create_app(), use explicit “is not None” checks when selecting authenticator, vendor_store and readiness.

A supplied component must be retained even if its __bool__ returns False or its __len__ returns zero. Only None selects the database-backed default.

Add a focused regression test supplying valid false-valued doubles for all three components:
- Assert app.state retains each exact supplied object.
- Exercise their corresponding routes to confirm the doubles are used.
- Confirm the shared database never starts.
- Preserve the existing ownership and shutdown behaviour.

Correction 2: reject null characters in vendor names
VendorCreate.name must reject U+0000 before persistence, in addition to its existing non-blank and length rules.

Do not strip, replace or truncate the submitted value. Do not impose a general ASCII restriction or redesign the name rules.

Add a regression test submitting a valid slug and a non-blank name containing an embedded null character:
- Response is 422 application/problem+json.
- The request-ID body/header contract holds.
- The vendor store is never called.
- The submitted name is absent from the error response.

Add or retain a positive test proving an ordinary Unicode display name is accepted unchanged.

Update ADR-0006’s name-validation description to include the null-character restriction. Keep the documentation edit narrow.

Regression verification
Run the new focused tests against the pre-edit implementation to demonstrate that they detect these findings, then restore the corrected files and verify restoration. Use the recorded staged tree as the baseline; do not rewrite commits or disturb unrelated work.

Then run:
- uv run --locked ruff format --check .
- uv run --locked ruff check .
- uv run --locked mypy
- uv run --locked pytest
- uv build
- git diff --cached --check
- gitleaks git --pre-commit --staged --redact --verbose .

Stage only the intended corrections and prompt-history additions before the staged checks. PostgreSQL tests should remain skipped locally; do not contact a database or start Docker.

Prompt history
- Preserve earlier prompts and outcome notes.
- Append the preceding read-only resume prompt verbatim if it is available in this session and has not yet been recorded.
- Append this correction prompt verbatim, using the next available sequential prompt number.
- Add a separate review note recording these two findings.
- State accurately that the reviewer inspected the supplied diff but did not run the project suite.
- Record actual verification results and keep M2c PostgreSQL verification, Compose and overall M2 acceptance pending.
- Do not invent missing prompt text or record acceptance of the corrections before the next review.

Final handoff
Include:
1. A brief explanation of the corrections.
2. The COMPLETE incremental staged diff against the recorded pre-edit staged tree, excluding prompts.md, directly inside fenced diff blocks.
3. Numbered parts split at file boundaries if needed; no truncation or summary replacing diff content.
4. A separate summary of prompt-history additions.
5. Commands actually run, results and skipped checks.
6. Current branch, full HEAD, staged paths and Git status.

If response limits prevent the complete inline diff, explicitly identify any omitted files and save the complete diff under gitignored .local/ as a fallback.

Do not commit, push, merge, amend, rebase, reset, start servers, install tools or contact a database. Leave the corrections staged for external review.
````

**Outcome (corrections pending review; staged, not committed or pushed):**
- **Starting state verified:**
  - branch `feat/vendor-api-readiness`, HEAD `277dfea`, the expected origin;
  - the 22 M2c files staged, with nothing unstaged or untracked.
  - The pre-edit staged tree, `005fa5cc95c7784ad5c0b10aa723a0edf01dd903`, was recorded under `.local/`.
- **Correction 1:** `create_app()` now selects each of `authenticator`, `vendor_store` and `readiness` with `is not None`, so only `None` selects the database-backed default. Ownership and shutdown are unchanged.
  - The new test `test_falsy_injected_components_are_kept_and_the_database_never_starts` in `tests/test_readiness.py` injects doubles whose `__bool__` is `False` or whose `__len__` is 0.
  - It checks that `app.state` holds each exact object, exercises `/v1/me`, `/v1/vendors` and `/readyz` through them, and checks that the shared database never starts.
- **Correction 2:** `VendorCreate.name` now rejects U+0000 with a 422. The value is not stripped, replaced or truncated, and the other name rules are unchanged.
  - New tests in `tests/test_vendors_api.py`: an embedded null gives a 422 problem response with the request-ID contract, the store is never called, and the submitted name is absent from the response; an ordinary Unicode display name is accepted and stored unchanged.
  - ADR-0006's name rule now mentions the null character.
- **Regression demonstration:** the staged pre-edit `app.py` and `vendors.py` were temporarily restored, after confirming that they matched the index.
  - Against them, the falsy-component and null-character tests **failed**: `app.state.authenticator` was a `DatabaseAuthenticator`, and the response was 201 instead of 422. The Unicode test passed, as a positive test should.
  - The falsy-component test stops at its first assertion, so only the authenticator substitution was observed directly against the pre-edit code.
  - The corrected files were then restored, confirmed byte-identical with `cmp`, and the three tests passed.
- **Verified locally** (Windows):
  - `uv run --locked ruff format --check .`: 69 files already formatted.
  - `uv run --locked ruff check .`: all checks passed. A first run flagged RUF001 (an en dash in the new Unicode test string); the character was removed and the checks were rerun.
  - `uv run --locked mypy`: no issues in 57 source files.
  - `uv run --locked pytest`: 458 passed, 21 PostgreSQL integration tests skipped (`EG_TEST_DATABASE_URL` not set).
  - `uv build`: the sdist and wheel were built.
  - After staging only the corrected files and this prompt history: `git diff --cached --check` printed nothing (exit 0), and `gitleaks git --pre-commit --staged --redact --verbose .` found no leaks. Both were rerun after this note was staged.
  - The installed-wheel checks from Prompt 39 were not rerun.
- **Not verified:**
  - The M2c PostgreSQL integration tests have still not run against PostgreSQL; they are pending an authorized publication and CI.
  - Compose remains unverified.
  - Review of these corrections and overall M2 acceptance are pending.
  - No local database was contacted, and Docker was not started.

**Review note (added with Prompt 42):**
- The external reviewer accepted the original M2c diff (Prompt 39), together with the Prompt 41 correction diff, for a local commit:
  - explicit `None` checks keep injected components that evaluate as false;
  - vendor names containing U+0000 are rejected before persistence;
  - the regression tests and the narrow ADR-0006 clarification.
- The acceptance rests on the supplied diffs and on Claude's reported Windows checks: 458 passed, with 21 PostgreSQL integration tests skipped. The reviewer did not run the project suite.
- M2c PostgreSQL verification, Compose and overall M2 acceptance remain pending.

## Prompt 42: Commit reviewed M2c locally

- **Stage:** Local commit of reviewed M2c work (no push, no merge)
- **Date:** 2026-10-12 (session date)

````text
Commit the reviewed M2c work locally. This authorizes one local commit only, with no push or merge.

Follow CLAUDE.md. Work only in:
D:\Claude\evidenceguard_agentic_rag

Verify the expected starting state:
- Branch: feat/vendor-api-readiness
- HEAD: 277dfeaec7c1c64fa5ee92a3ce892823acc787fb
- Origin: https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git
- Staged tree: aecadadb4e6477d1cfead4e0933c54b4e24b0da6
- Exactly the existing 22 M2c paths staged.
- Nothing unstaged or untracked.
- No .local/ paths staged.

If anything differs, report it and stop without changing the state.

The external reviewer accepts the original M2c diff plus Prompt 41’s correction diff for a local commit:
- explicit None checks preserve false-valued injected components;
- vendor names containing U+0000 are rejected before persistence;
- the regression tests and narrow ADR clarification are accepted.

Acceptance rests on the supplied diffs and your reported Windows checks: 458 passed, 21 PostgreSQL integration tests skipped. The reviewer did not run the project suite. M2c PostgreSQL verification, Compose and overall M2 acceptance remain pending.

Changes permitted in this task:
Only append to prompts.md:
1. A review note under Prompt 41 recording this acceptance and its verification limits.
2. This prompt verbatim, using the next sequential number.
3. A truthful pre-commit outcome note.

Preserve all earlier entries. Do not change application code, tests, dependencies, configuration or other documentation.

Before committing:
- Confirm every staged file except prompts.md remains byte-identical to the accepted staged tree.
- Inspect the staged paths and diff.
- Check the staged content for secrets and private information without printing sensitive values.
- Confirm effective author and committer use:
  257921624+mathewmljourney93@users.noreply.github.com
- Run git diff --cached --check.
- Run gitleaks git --pre-commit --staged --redact --verbose .

If these checks pass, create one local commit:
feat: add tenant-scoped vendor API and database readiness

Keep the existing attribution convention. Do not modify global Git configuration or rewrite history.

After committing:
- Run gitleaks git --redact --verbose . for the full history.
- Confirm the commit parent, committed paths and clean working tree.
- Confirm the committed non-prompts.md files match the accepted tree.

Application checks need not be rerun if only prompts.md changed. Report previous checks as historical, not as checks run in this task.

Final handoff:
- Full commit SHA, parent, subject, author and committer.
- Committed paths and verification results.
- Prompt-history additions.
- Final Git status.
- Complete incremental diff against the accepted tree, excluding prompts.md, inside fenced diff blocks if any such changes exist. If none, state that explicitly.
- State that PostgreSQL verification, Compose and overall M2 acceptance remain pending.

Do not push, merge, amend, rebase, delete branches, start Docker or contact any database.
````

**Pre-commit note (recorded before the commit):**
- **Starting state verified:**
  - branch `feat/vendor-api-readiness`, HEAD `277dfea`, the expected origin;
  - staged tree `aecadadb4e6477d1cfead4e0933c54b4e24b0da6`, with exactly the 22 M2c paths staged, no `.local/` path staged, and nothing unstaged or untracked.
  - The effective author and committer identity is `257921624+mathewmljourney93@users.noreply.github.com`.
- **This commit** adds the reviewed M2c work and this prompt-history update. Since the accepted tree, only `prompts.md` has changed.
- **Checks on the staged content, including this note:** the byte-identity comparison, the private-content check, `git diff --cached --check` and the staged Gitleaks scan run before the commit. The full-history Gitleaks scan runs after the commit. All of their results are reported in the session handoff.
- **Not rerun in this task:** the application checks, because only `prompts.md` changed. The last results are the historical Prompt 41 results: 458 passed and 21 PostgreSQL integration tests skipped.
- **Still pending:**
  - M2c PostgreSQL verification and CI, which need an authorized publication;
  - Compose verification;
  - overall M2 acceptance.

  No push or merge is authorized.

## Prompt 43: Publish reviewed M2c and verify branch CI

- **Stage:** Local documentation commit and publication of `feat/vendor-api-readiness` (no merge, `main` unchanged)
- **Date:** 2026-10-12 (session date)

````text
Publish the reviewed M2c feature branch and report its CI results. This authorizes pushing only feat/vendor-api-readiness. It does not authorize merging or changing main.

Follow CLAUDE.md. Work only in:
D:\Claude\evidenceguard_agentic_rag

Verify the starting state:
- Branch: feat/vendor-api-readiness
- HEAD: 73bebf58ed6a3703707e21fe4ddf112d7e07127c
- Parent: 277dfeaec7c1c64fa5ee92a3ce892823acc787fb
- Origin: https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git
- Working tree clean.
- Effective author and committer email:
  257921624+mathewmljourney93@users.noreply.github.com

Read remote refs. Confirm:
- Remote main remains 277dfeaec7c1c64fa5ee92a3ce892823acc787fb.
- The remote feature branch does not exist.
- Remote main is an ancestor of HEAD.

If the state differs, report it and stop without repairing it.

Publication preflight
- Inspect everything that will become public compared with remote main.
- Confirm no secrets, private identifiers, tracked .local/ files, backups or bundles.
- Confirm the commits to be published use the noreply identity.
- Inspect the CI and secret-scan workflows. Confirm push triggers cover this branch and the PostgreSQL integration job retains EG_REQUIRE_INTEGRATION=1.
- Do not alter application code, tests, dependencies or workflows.

Prompt history
Append this prompt verbatim using the next sequential number, with a truthful preflight note.
Record the publication authorization, checks and remaining limits. Do not record a push or CI result before it happens.
Preserve earlier entries.

Stage only prompts.md. Run:
- git diff --cached --check
- gitleaks git --pre-commit --staged --redact --verbose .

If clean, create one local documentation commit:
docs: record M2c branch publication authorization

Run a full-history secret scan:
gitleaks git --redact --verbose .

Only if the scan passes, push with this explicit refspec:
git push --set-upstream origin refs/heads/feat/vendor-api-readiness:refs/heads/feat/vendor-api-readiness

No force-push, other refs or tags.

CI verification
Monitor workflows for the exact published HEAD SHA until completion:
1. Ubuntu verification.
2. Windows verification.
3. PostgreSQL 17 + pgvector integration.
4. Full-history secret scan.

Report run/job links and conclusions for that exact SHA.
Where logs are accessible, retrieve the actual pytest summary, especially the integration passed/skipped count. There are currently 21 integration tests, but do not present an expected count as an observed result.
If logs are inaccessible, distinguish confirmed job success from inferred test execution.

If a job fails, report the failing step and available diagnostics, then stop. Do not implement or publish fixes automatically.
If monitoring reaches its time limit, report pending jobs accurately.

Final handoff
- Published full SHA and documentation commit parent.
- Prompt-history additions.
- Preflight and scan results.
- Workflow/job links, exact SHA and observed test counts.
- Remote main and feature-branch refs after publication.
- Final Git status.
- Complete incremental diff outside prompts.md, if any, inside fenced diff blocks. If none, state that.
- Keep Compose and overall M2 acceptance pending.

Do not merge, switch or update main, rewrite history, delete branches, start Docker or contact a local database.
````

**Preflight note (recorded before this documentation commit and before any push):**
- **Starting state verified:**
  - branch `feat/vendor-api-readiness`, HEAD `73bebf5` with parent `277dfea`, the expected origin;
  - a clean working tree;
  - author and committer `257921624+mathewmljourney93@users.noreply.github.com`.
- **Remote refs, read before this commit:**
  - `main` is `277dfea`, and `feat/vendor-api-readiness` does not exist;
  - remote `main` is an ancestor of HEAD.
- **Publication preflight against remote `main`:**
  - the only commit to publish, besides this documentation commit, is `73bebf5`, with the noreply author and committer;
  - it changes the 22 reviewed M2c paths;
  - no `.local/`, backup, bundle, environment or key files are tracked;
  - a pattern scan of the added lines found no API keys, credentialed database URLs, tokens, cloud keys, private keys, local user paths or personal email addresses.
- **Workflows**, unchanged by M2c:
  - `ci.yml` and `secret-scan.yml` both trigger on every `push` without branch filters, so they cover this branch;
  - the integration job keeps `EG_REQUIRE_INTEGRATION: "1"`.
- **Authorization:** Prompt 43 authorizes this documentation commit and pushing only `feat/vendor-api-readiness` with the explicit refspec, and only after the full-history secret scan passes. It does not authorize merging or changing `main`, force-pushing, other refs or tags.
- **Not yet recorded here:**
  - the push and the CI results happen after this commit and are reported in the session handoff;
  - the M2c PostgreSQL integration tests have not run yet.
- **Not rerun in this task:** the application checks, because only `prompts.md` changes. The last local results are the historical Prompt 41 results: 458 passed and 21 PostgreSQL integration tests skipped.
- **Still pending:**
  - M2c CI verification;
  - Compose verification;
  - overall M2 acceptance.

**Outcome note for Prompt 43 (added with Prompt 44; publication and CI happened after the Prompt 43 commit):**
- **Documentation commit:** `a888b6cbd277fb6a4556899fa630a7c50df14e61`, `docs: record M2c branch publication authorization`, with parent `73bebf5` and the noreply author and committer.
  - Before it: `git diff --cached --check` printed nothing and the staged Gitleaks scan found no leaks.
  - After it, before the push: the full-history Gitleaks scan found no leaks.
- **Push:** `git push --set-upstream origin refs/heads/feat/vendor-api-readiness:refs/heads/feat/vendor-api-readiness` created the remote branch at `a888b6c`. Remote `main` stayed at `277dfea`. There was no force-push, and no other ref or tag was pushed.
- **CI for exactly `a888b6c`:** Claude confirmed the run and job conclusions through the public GitHub REST API.
  - [CI run 38212619855](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38212619855) succeeded:
    - [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38212619855/job/114689994050) and [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38212619855/job/114689993962) verification;
    - the [PostgreSQL 17 + pgvector integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38212619855/job/114689994147).
  - [Secret-scan run 38212619867](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38212619867) succeeded ([job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38212619867/job/114689993899)).
- **Integration count:**
  - Claude could not read the job logs: the unauthenticated log endpoint returned 403.
  - The external reviewer independently retrieved the integration log, which reports `21 passed, 458 deselected in 4.65s`, with no integration test skipped. That covers M2a's ten tests, M2b's five and M2c's six.

## Prompt 44: Record verified M2c CI results

- **Stage:** Documentation update for verified M2c CI (staged for review, no commit)
- **Date:** 2026-10-12 (session date)

````text
Prepare the M2c verification documentation. Leave it staged and uncommitted for external review.

Follow CLAUDE.md. Work only in:
D:\Claude\evidenceguard_agentic_rag

Verify:
- Branch: feat/vendor-api-readiness
- HEAD: a888b6cbd277fb6a4556899fa630a7c50df14e61
- Upstream: origin/feat/vendor-api-readiness, at the same SHA.
- Origin: https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git
- Working tree clean.
- Remote main remains 277dfeaec7c1c64fa5ee92a3ce892823acc787fb.

If anything differs, report it and stop without repairing the state.

Verified evidence
The external reviewer independently retrieved GitHub evidence for the exact published SHA a888b6cbd277fb6a4556899fa630a7c50df14e61:
- CI run 38212619855: completed successfully.
- Secret-scan run 38212619867: completed successfully.
- PostgreSQL integration job 114689994147:
  21 passed, 458 deselected in 4.65s.
- No integration tests were skipped in that run.

Links:
https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38212619855
https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38212619855/job/114689994147
https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38212619867

Documentation changes only
Update:
- README.md
- docs/decisions/0006-vendor-api-and-readiness.md
- docs/plan.md
- docs/threat-model.md
- prompts.md

Record:
1. M2c was reviewed, committed locally and published on its feature branch.
2. Ubuntu, Windows, PostgreSQL integration and full-history secret scanning passed for the tested SHA.
3. All 21 integration tests passed, including the six added in M2c.
4. Attribute the observed integration summary to evidence independently retrieved by the external reviewer. Do not claim you accessed logs yourself unless you actually do.
5. ADR-0006 is accepted following the implementation review and passing CI.
6. M2c is not yet merged into main.
7. Overall M2 acceptance remains pending the main publication and acceptance review.
8. Compose remains unverified. Do not imply vector functionality was tested merely because CI uses a pgvector image.
9. Existing authentication, pagination and readiness limitations remain applicable.

Keep historical prompt entries unchanged. Append a separate outcome note for Prompt 43 recording the actual publication and verified CI results, then append this prompt verbatim using the next sequential number and add its truthful outcome note.

Keep the edits narrow. Do not alter application code, tests, workflows, dependencies or architecture.

Checks
- Check relative links and anchors in changed documentation.
- Check the staged additions for secrets and private information.
- Run git diff --cached --check.
- Run gitleaks git --pre-commit --staged --redact --verbose .
- Confirm only the five authorized documentation files are staged.

Application tests and builds need not be rerun for documentation-only changes.

Final handoff
- Include the COMPLETE staged diff excluding prompts.md directly in fenced diff blocks.
- Split into numbered parts at file boundaries if needed; do not truncate.
- Summarize prompt-history additions separately.
- Report checks actually run and final Git status.
- Distinguish the tested published commit from these new, uncommitted documentation edits.

Do not commit, push, merge, update main, rewrite history, start Docker or contact a database.
````

**Outcome (documentation pending review; staged, not committed or pushed):**
- **Starting state verified:**
  - branch `feat/vendor-api-readiness`, HEAD and upstream `a888b6c`, the expected origin, a clean tree;
  - remote `main` at `277dfea`.
- **Documentation updated:** README, ADR-0006, the plan and the threat model now record that M2c was reviewed, committed and published on its branch, and that it passed CI at `a888b6c`:
  - Ubuntu and Windows verification;
  - the integration job, with `21 passed, 458 deselected in 4.65s` from the log retrieved by the external reviewer, including M2c's six tests;
  - the full-history secret scan.
- **Status changes:**
  - ADR-0006 is now *Accepted*, following the implementation review and passing CI.
  - M2c is recorded as not yet merged into `main`. Overall M2 acceptance is pending the `main` publication and acceptance review.
  - Compose is unverified, and no vector functionality is claimed as tested.
  - The existing authentication, pagination and readiness limits are kept.
  - The README's name rule now also mentions the null-character restriction from Prompt 41.
- **Not changed:** ADR-0005 is outside this prompt's file list. Its status line still describes ADR-0006's shared `AppDatabase` as "under review".
- **Checks run:**
  - a relative link and anchor check of the four changed documents: no problems;
  - a private-content check of the staged additions;
  - `git diff --cached --check`;
  - the staged Gitleaks scan.

  Exact results are in the session handoff. Application tests and builds were not rerun, because only documentation changed.
- **Tested commit versus these edits:** CI verified the published commit `a888b6c`. These documentation edits are newer, uncommitted and untested by CI.

**Review note (added with Prompt 45):**
- The external reviewer accepted the Prompt 44 documentation diff, staged as tree `0c3a30275b91dc5c47a1562c81d171c6ca8036c7`.
- The acceptance rests on that diff and on CI evidence for `a888b6c` that the reviewer retrieved independently:
  - [CI run 38212619855](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38212619855) succeeded;
  - [secret-scan run 38212619867](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38212619867) succeeded;
  - [integration job 114689994147](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38212619855/job/114689994147) reported `21 passed, 458 deselected in 4.65s`.
- The reviewer did not run the project suite locally.
- Compose and overall M2 acceptance remain pending.

## Prompt 45: Commit verified M2c documentation and fast-forward main

- **Stage:** Local documentation commit, publication of `feat/vendor-api-readiness`, and an authorized fast-forward of `main` after CI passes
- **Date:** 2026-10-12 (session date)

````text
Commit the reviewed M2c verification documentation, publish the feature branch, then fast-forward main only after all four CI checks pass.

Follow CLAUDE.md. Work only in:
D:\Claude\evidenceguard_agentic_rag

Verify the starting state:
- Branch: feat/vendor-api-readiness
- HEAD and upstream: a888b6cbd277fb6a4556899fa630a7c50df14e61
- Origin: https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git
- Exactly five documentation files staged:
  README.md
  docs/decisions/0006-vendor-api-and-readiness.md
  docs/plan.md
  docs/threat-model.md
  prompts.md
- Nothing unstaged or untracked.
- Remote main: 277dfeaec7c1c64fa5ee92a3ce892823acc787fb
- Remote main is an ancestor of HEAD.

If the state differs, report it and stop without repairing it.

Review acceptance
The external reviewer accepts the Prompt 44 documentation diff, based on that diff and independently retrieved CI evidence for a888b6c:
- CI run 38212619855 succeeded.
- Secret-scan run 38212619867 succeeded.
- Integration job 114689994147 reported:
  21 passed, 458 deselected in 4.65s.

The reviewer did not run the project suite locally. Compose and overall M2 acceptance remain pending.

One additional authorized edit
In docs/decisions/0005-api-key-authentication.md, change only the status-line phrase:
“superseded, under review, by”
to:
“superseded by”

This makes it consistent with the accepted ADR-0006. Preserve the rest of ADR-0005.

Prompt history
Record the accepted staged tree before editing.
Append:
- A review note under Prompt 44 recording acceptance and its evidence.
- This prompt verbatim, using the next sequential number.
- A truthful preflight note explaining the publication sequence and limits.

Preserve earlier entries. Do not record future push, merge or CI results as already completed.

Pre-commit checks
- Confirm only the six authorized documentation files are staged.
- Confirm the four previously reviewed non-prompts.md files remain byte-identical to the accepted staged tree.
- Confirm ADR-0005 contains only the exact authorized phrase change.
- Check documentation links and staged additions for secrets/private information.
- Confirm effective author and committer email:
  257921624+mathewmljourney93@users.noreply.github.com
- Run git diff --cached --check.
- Run gitleaks git --pre-commit --staged --redact --verbose .

If clean, commit:
docs: record verified M2c results and main publication authorization

Keep the existing attribution convention.
Run gitleaks git --redact --verbose . after the commit.
Do not publish if the scan fails.

Publication sequence
1. Push only the feature branch with an explicit refspec:
   git push origin refs/heads/feat/vendor-api-readiness:refs/heads/feat/vendor-api-readiness

2. Wait for all four checks on the exact new HEAD SHA:
   - Ubuntu verification
   - Windows verification
   - PostgreSQL integration
   - Full-history secret scan

3. If any check fails or remains pending at the monitoring limit, stop and report. Do not update main or implement fixes.

4. Once all four pass, fetch main and the feature branch again. Confirm:
   - Remote main is still 277dfeaec7c1c64fa5ee92a3ce892823acc787fb.
   - That commit is an ancestor of the verified feature HEAD.
   - Local main has no independent commits or divergence.
   - The working tree is clean.
   If any condition differs, stop.

5. Switch to main and fast-forward with git merge --ff-only to the exact verified feature SHA.

6. Push only main:
   git push origin refs/heads/main:refs/heads/main

7. Monitor the workflows triggered by the main push for that exact SHA and report their results.

Do not force-push, create a merge commit, squash, amend, rebase, delete branches or push tags.

Final handoff
- Full commit SHA, parent, subject and identity.
- Complete incremental diff against the accepted staged tree, excluding prompts.md, directly in fenced diff blocks. This should contain only the ADR-0005 phrase correction.
- Prompt-history additions and actual checks run.
- Feature and main workflow/job links, conclusions and exact tested SHA.
- Actual integration test counts if logs are accessible; otherwise state that the count is unobserved.
- Remote refs before and after publication.
- Final Git status.
- Keep Compose and overall M2 acceptance pending.

No application checks need to run locally for these documentation-only changes. Do not start Docker or contact a local database.
````

**Preflight note (recorded before the commit, publication and any change to `main`):**
- **Starting state verified:**
  - branch `feat/vendor-api-readiness`, HEAD and upstream `a888b6c`, the expected origin;
  - exactly the five reviewed documentation files staged, with nothing unstaged or untracked.
  - The accepted staged tree, `0c3a30275b91dc5c47a1562c81d171c6ca8036c7`, was recorded before any edit.
- **Remote refs, read before this commit:**
  - `main` is `277dfea`, and local `main` matches it;
  - `feat/vendor-api-readiness` is `a888b6c`;
  - remote `main` is an ancestor of HEAD.
- **This commit** adds:
  - the accepted Prompt 44 documentation;
  - the authorized ADR-0005 status-line correction ("superseded, under review, by" becomes "superseded by");
  - this prompt-history update.
- **Authorization:** Prompt 45 authorizes these steps, in order:
  1. push only the feature branch;
  2. **only after** Ubuntu verification, Windows verification, PostgreSQL integration and the full-history secret scan all pass for the exact pushed SHA, and remote `main` is confirmed still at `277dfea` and an ancestor of it, fast-forward local `main` to that SHA with `git merge --ff-only`;
  3. push only `main`, then monitor its workflows.

  No force-push, merge commit, squash, amend, rebase, branch deletion or tag push is authorized.
- **Stop conditions:** if a check fails or is still pending at the monitoring limit, `main` is not changed.
- **Not yet recorded here:** the push, the CI results and any `main` update happen after this commit, so they are reported in the session handoff.
- **Not rerun:** application checks, because only documentation changes.
- **Still open:** Compose remains unverified, and overall M2 acceptance is pending.

**Outcome note for Prompt 45 (added with Prompt 46; publication and CI happened after the Prompt 45 commit):**
- **Documentation commit:** `9d5a93ab1389d8a2b084c8f669df3bf9941a477f`, with parent `a888b6c` and the noreply author and committer.
  - Before it: only the six authorized files were staged, the four reviewed documents were byte-identical to the accepted tree, and ADR-0005 changed only by the authorized phrase. The link, whitespace and staged Gitleaks checks passed.
  - After it, before any push: the full-history Gitleaks scan found no leaks.
- **Feature push:** `git push origin refs/heads/feat/vendor-api-readiness:refs/heads/feat/vendor-api-readiness` moved the branch from `a888b6c` to `9d5a93a`.
- **Feature CI for exactly `9d5a93a`:** Claude confirmed the conclusions through the public GitHub REST API.
  - [CI run 38214461017](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38214461017) succeeded:
    - [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38214461017/job/114695840669) and [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38214461017/job/114695840752) verification;
    - the [integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38214461017/job/114695840580).
  - [Secret-scan run 38214460994](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38214460994) succeeded.
- **Fast-forward of `main`:** after all four checks passed, a fresh fetch confirmed the preconditions:
  - remote `main` was still `277dfea`, and it is an ancestor of `9d5a93a`;
  - local `main` equalled `origin/main`;
  - the tree was clean.

  Local `main` was then fast-forwarded with `git merge --ff-only`, and `git push origin refs/heads/main:refs/heads/main` moved `main` from `277dfea` to `9d5a93a`. No merge commit, force-push or tag push was made.
- **`main` CI for exactly `9d5a93a`:**
  - [CI run 38214711868](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38214711868) succeeded:
    - [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38214711868/job/114696647399) and [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38214711868/job/114696647671) verification;
    - the [integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38214711868/job/114696647728).
  - [Secret-scan run 38214711864](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38214711864) succeeded.
- **Integration counts:**
  - Claude could not read the job logs: the unauthenticated log endpoint returned 403.
  - The external reviewer independently retrieved the `main` integration log, which reports `21 passed, 458 deselected in 4.92s`.
  - The count for the feature run `38214461017` was not observed.

## Prompt 46: Record M2 acceptance and propose the M3 breakdown

- **Stage:** Documentation only, on branch `docs/m2-acceptance-m3-plan` (staged for review, no commit)
- **Date:** 2026-10-12 (session date)

````text
Record M2 acceptance and prepare a bounded M3 implementation plan. Documentation only; leave changes staged and uncommitted for review.

Follow CLAUDE.md. Work only in:
D:\Claude\evidenceguard_agentic_rag

Verify:
- Current branch: main
- HEAD and origin/main:
  9d5a93ab1389d8a2b084c8f669df3bf9941a477f
- Origin:
  https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git
- Working tree clean.

If the state differs, report it and stop without repairing it.

Create a local branch:
docs/m2-acceptance-m3-plan

Verified evidence
The external reviewer independently confirmed:
- Main CI run 38214711868 succeeded for the exact SHA above.
- Main secret-scan run 38214711864 succeeded for that SHA.
- Integration job 114696647728 reported:
  21 passed, 458 deselected in 4.92s.

Links:
https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38214711868
https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38214711868/job/114696647728
https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38214711864

M2 acceptance
The reviewer accepts M2 against the agreed criteria:
- Migration upgrade/downgrade.
- Composite tenant constraints.
- Foreign vendor IDs return 404.
- Client-supplied tenant information cannot override authenticated scope.
  Headers/query parameters are ignored; unexpected body fields are rejected.
- Revoked keys return 401.
- Integration tests execute against the PostgreSQL + pgvector CI image.

This does not claim vector functionality is implemented or tested.
Compose remains unverified.
The reviewer inspected implementation diffs and retrieved CI evidence but did not run the suite locally.

Update documentation
Make narrow status/evidence updates in:
- README.md
- docs/decisions/0006-vendor-api-and-readiness.md
- docs/plan.md
- docs/threat-model.md
- prompts.md

Record M2c on main at the verified SHA and mark M2 accepted.
Preserve historical evidence and limitations.
In docs/plan.md, correct stale current blockers where repository evidence establishes they are resolved, such as Python/uv being missing. Keep genuine unresolved blockers. Do not inspect system folders or recheck installed tools outside the project.

M3 preparation
Read the approved plan and relevant ADRs. Propose a small, ordered breakdown of M3, keeping its existing architecture and acceptance criteria.

Describe the first implementation slice precisely:
- intended schema/domain changes and migration;
- job ownership, lease, heartbeat and fencing rules;
- dependencies on later document/revision activation work;
- database-independent tests versus real PostgreSQL integration tests;
- concurrency and stale-worker cases that must be verified;
- explicit exclusions.

Choose the smallest useful slice with coherent invariants. Do not build all of M3 at once or introduce a new orchestration framework.
Put the proposed breakdown in docs/plan.md, clearly marked as proposed, awaiting review.
Do not implement code, migrations, worker services, upload endpoints or Docker changes.

Prompt history
Append a separate outcome note for Prompt 45 recording the actual main publication and CI results.
Append this prompt verbatim using the next sequential number, plus a truthful outcome note.
Preserve earlier prompts and outcomes.

Verification
- Check documentation links and anchors.
- Inspect staged additions for secrets/private information.
- Run git diff --cached --check.
- Run gitleaks git --pre-commit --staged --redact --verbose .
- Confirm only the five authorized documentation files are staged.

Do not rerun application tests or builds for documentation-only changes.

Final handoff
- Brief M2 acceptance summary and proposed M3 sequence.
- COMPLETE staged diff excluding prompts.md directly in fenced diff blocks.
- Numbered parts at file boundaries if needed; no truncation.
- Prompt-history additions separately.
- Actual checks and final Git status.

Do not commit, push, merge, rewrite history, install tools, start Docker or contact a database.
````

**Outcome (documentation pending review; staged on `docs/m2-acceptance-m3-plan`, not committed or pushed):**
- **Starting state verified:**
  - branch `main`, HEAD and `origin/main` `9d5a93a`, the expected origin, a clean tree.
  - Branch `docs/m2-acceptance-m3-plan` was created from `9d5a93a`.
- **M2 acceptance recorded:**
  - README, ADR-0006, the plan and the threat model now record M2c on `main` at `9d5a93a`, with the `main` CI and secret-scan runs and the reviewer-retrieved `21 passed, 458 deselected in 4.92s`.
  - M2 is marked accepted. Each criterion is mapped to the tests that cover it, the reviewer's verification limits are stated, and it is explicit that no vector functionality is claimed and Compose is unverified.
  - Earlier verification records and limitations are kept.
- **Plan corrections:**
  - the environment table's stale `main` SHA was updated;
  - the "uv and Python 3.12 are missing" blocker was marked resolved, using repository evidence (§2 records the versions, M1 and M2 used them, and CI pins them);
  - the Docker blocker, the API-key blocker and the open questions remain. No tools were rechecked outside the project.
- **M3 proposal:** a breakdown into slices M3a–M3f, marked *PROPOSED, awaiting review*, which maps the existing M3 acceptance criteria to slices. M3a, the durable job core, is described in detail:
  - schema and migration `0002`;
  - lifecycle;
  - ownership, lease, heartbeat and fencing rules;
  - lock order and dependencies;
  - database-independent and PostgreSQL tests;
  - concurrency and stale-worker cases;
  - exclusions;
  - decisions requested at review.

  No code, migration, worker, endpoint or Docker change was made.
- **Checks:** the link and anchor check, the private-content check, `git diff --cached --check` and the staged Gitleaks scan were run on the staged content. Exact results are in the session handoff. Application tests and builds were not rerun.

**Review note (added with Prompt 47):**
- **Accepted:**
  - the Prompt 46 M2 acceptance documentation;
  - the overall M3a–M3f sequence.
- **Required before implementation:** the detailed M3a specification needed clarifications and parameter decisions.
  1. **Idempotent enqueue must check the identity of the request.**
     - An identical retry returns the existing job, even when terminal, without resetting or rescheduling it.
     - A changed canonical payload or `max_attempts` under the same key raises a fixed `JobIdempotencyConflictError` without changing the row.
     - JSON key order must not create a false conflict.
     - Concurrent inserts resolve through the unique constraint and a comparison with the committed row.
  2. **Lease decisions must use fresh database time.**
     - `clock_timestamp()` is used, not worker time or transaction-start time.
     - The job row is locked before ownership and lease validity are checked, and validity is rechecked after any lock wait.
     - The same strict policy applies to heartbeat, completion, failure and fenced effects. Expired leases cannot be revived.
     - Fenced transactions are short, with no provider or network calls under the job lock.
     - The guarantee is stated precisely: no reclaim while a valid fence holds the lock, but no promise that the commit precedes lease expiry.
  3. **Initial parameters:**
     - a 60 s lease and a 20 s heartbeat (heartbeat timer in M3b);
     - `max_attempts` defaults to 3, with a range of 1–10;
     - `attempt` starts at 0 and increments on each claim or reclaim;
     - backoff of `min(5 * 2^(n - 1), 60)` s, with no jitter in v1;
     - a 4,096-byte payload cap on canonical UTF-8 JSON;
     - a flat object payload with UUID-string values;
     - `kind` and key lengths of 64 and 128.
  4. **Terminal semantics:**
     - `failed` is permanent and `dead` is exhaustion; all three terminal statuses clear the lease and set `finished_at`;
     - an expired, exhausted job is marked `dead` without incrementing `attempt`;
     - exhausted rows must not obstruct claiming of other eligible jobs.
- **Planned tests required** for:
  - identical, changed, reordered, terminal, cross-tenant and concurrent enqueues;
  - an operation whose lease expires while it waits for the lock;
  - an exhausted expired job ahead of an eligible queued job.
- **Basis of the review:** the reviewer inspected the documentation and retrieved the M2 CI evidence, but did not run the project suite.
- **Status:** M3a implementation remains pending.

## Prompt 47: Finalize the M3a planning specification after review

- **Stage:** Documentation-only correction on branch `docs/m2-acceptance-m3-plan` (staged for review, no commit)
- **Date:** 2026-10-12 (session date)

````text
Finalize the M3 planning specification after external review. Documentation only; leave changes staged and uncommitted.

Follow CLAUDE.md. Work only in:
D:\Claude\evidenceguard_agentic_rag

Expected starting state:
- Branch: docs/m2-acceptance-m3-plan
- HEAD: 9d5a93ab1389d8a2b084c8f669df3bf9941a477f
- Origin: https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git
- Five files staged: README.md, ADR-0006, docs/plan.md, docs/threat-model.md, prompts.md.
- Nothing unstaged or untracked.

Verify first. If anything differs, report it and stop without repairing it.
Record the pre-edit staged tree for the incremental review diff.

Review outcome
The external reviewer accepts the M2 acceptance documentation and the overall M3a–M3f sequence. The detailed M3a specification requires the following clarifications and parameter decisions before implementation.

Modify docs/plan.md and prompts.md only.
Keep README, ADR-0006 and the threat model byte-identical to their starting staged versions.

1. Idempotent enqueue must check request identity
- The unique key remains (tenant_id, kind, idempotency_key).
- An identical retry returns the existing job, including when it is already terminal. It never resets or reschedules it.
- Compare canonical payload content and immutable max_attempts configuration.
- Changed payload or max_attempts under the same key raises a fixed JobIdempotencyConflictError, without exposing values or changing the existing row.
- JSON object key order must not create a false conflict.
- Concurrent inserts must resolve safely through the unique constraint and comparison against the committed existing row.
- Enqueue remains inside the caller-owned transaction.

Add planned tests for identical retries, changed payload/configuration, object key order, terminal-job retries, cross-tenant key reuse and concurrent enqueue.

2. Fresh database time for lease decisions
- Use PostgreSQL clock_timestamp() for fresh lease/scheduling decisions; do not use worker time or transaction-start now()/CURRENT_TIMESTAMP for lease validity.
- Acquire the job row lock before evaluating the owner token and current lease validity.
- Recheck validity after any lock wait. Do not rely on a time value captured before waiting.
- Heartbeat, completion, failure and fenced effects must use the same strict ownership policy.
- An expired lease cannot be revived, even if not reclaimed.
- Keep fenced transactions short; never perform provider/network calls while holding the job lock.
- Once a valid fence holds the job lock, a claimant cannot reclaim that row before the transaction finishes. State this precisely rather than promising that commit can never occur after lease expiry.
- Audit timestamps may still use ordinary transaction timestamps where appropriate.

Add a planned PostgreSQL test where an operation waits for a lock and the lease expires before it acquires the lock: the operation must be refused with no effect.

3. Set the initial M3a parameters
These are engineering defaults for the first implementation, not measured performance claims:
- Lease duration: 60 seconds.
- Worker heartbeat interval: 20 seconds, implemented in M3b.
- max_attempts: default 3; accepted range 1–10.
- attempt starts at 0 and increments on each successful claim/reclaim.
- Backoff after failed attempt n:
  min(5 * 2^(n - 1), 60) seconds.
- No jitter in v1; document that as a deliberate simplification.
- Payload cap: 4,096 bytes measured on canonical UTF-8 JSON.
- M3a payload: a flat JSON object with string keys and UUID-string values. Empty objects are allowed for test-only jobs. No tenant field, nested objects, document text or secrets. Kind-specific schemas arrive with their handlers.
- Preserve kind length 64 and idempotency-key length 128.

4. Confirm terminal semantics and exhausted claims
- failed: permanent, non-retryable handler failure.
- dead: retryable failure or lease abandonment exhausts the attempt cap.
- succeeded, failed and dead are terminal.
- Terminal transitions clear lease fields and set finished_at.
- A claim encountering an expired exhausted job marks it dead without incrementing beyond max_attempts.
- Claiming must still be able to reach other eligible jobs; exhausted-row cleanup must not indefinitely obstruct the queue.
- Add a planned test with an exhausted expired job followed by an eligible queued job.

Keep the M3a implementation pending. Record these as review decisions in the proposed specification; do not claim code or tests exist.

Prompt history
- Add a separate review note under Prompt 46 recording acceptance of the M2 documentation and the M3 sequence, with the detailed clarifications.
- Append this prompt verbatim using the next sequential number.
- Add a truthful outcome note.
- Preserve earlier entries.
- State that the reviewer inspected the documentation and retrieved M2 CI evidence, but did not run the project suite.

Checks
- Check documentation links.
- Confirm only docs/plan.md and prompts.md changed from the recorded starting staged tree.
- Run git diff --cached --check.
- Run gitleaks git --pre-commit --staged --redact --verbose .
- No application tests or builds are needed for this documentation-only task.

Final handoff
- Briefly list the settled decisions.
- Include the COMPLETE incremental staged diff against the pre-edit staged tree, excluding prompts.md, directly in fenced diff blocks.
- Split at file boundaries if necessary; do not truncate.
- Summarize prompt-history additions separately.
- Report actual checks, full HEAD and final Git status.

Do not implement M3a, commit, push, merge, install tools, start Docker or contact a database.
````

**Outcome (documentation pending review; staged, not committed or pushed):**
- **Starting state verified:**
  - branch `docs/m2-acceptance-m3-plan`, HEAD `9d5a93a`, the expected origin;
  - the five files staged, with nothing unstaged or untracked.
  - The pre-edit staged tree, `5df0dd7ff478d33d4849e17ef4cd183a14e170ee`, was recorded under `.local/`.
- **`docs/plan.md`:** the M3 section is now marked as "sequence accepted at review; M3a specification settled at review; implementation pending". The M3a specification records the four review decisions:
  - idempotent enqueue with an identity check, the conflict error, key-order-insensitive comparison, terminal retries and concurrent inserts;
  - fresh `clock_timestamp()` time, with a lock-then-check procedure shared by heartbeat, completion, failure and fenced effects, no revival of expired leases, no network calls under the lock, and a precise statement of the fence guarantee;
  - the initial parameters, with no jitter as a deliberate simplification;
  - the terminal semantics, with a bounded, `SKIP LOCKED` exhausted-job sweep that cannot obstruct eligible jobs.
- **New planned tests:**
  - the requested enqueue cases;
  - the lease that expires during a lock wait;
  - the exhausted job ahead of a queued job.
- **Remaining minor proposals,** to confirm at implementation review: the 5 s `lock_timeout` and the sweep bound of 10 rows per claim. No code, migration or test exists.
- **Unchanged:** README, ADR-0006 and the threat model are byte-identical to their starting staged versions. The README's wording that the M3 breakdown "awaits review" was left as it is, because this prompt keeps the README unchanged.
- **Checks:** the link check, the comparison with the recorded tree, `git diff --cached --check` and the staged Gitleaks scan were run on the staged content. Exact results are in the session handoff. No application tests or builds were run.

**Acceptance note (added with Prompt 48):**
- **Accepted by the external reviewer:**
  - Prompt 46's M2 acceptance documentation and M3 sequence;
  - Prompt 47's revised M3a specification;
  - the 5-second `lock_timeout`;
  - the exhausted-job sweep limit of 10 rows per claim.
- **Nature of the parameters:** they are initial engineering defaults, not measured performance claims.
- **Basis of the review:** the reviewer inspected the documentation and independently retrieved the M2 CI evidence, but did not run the project suite.
- **Status:** M3a remains unimplemented, and Compose remains unverified.

## Prompt 48: Commit the M2 acceptance record and reviewed M3 plan locally

- **Stage:** Local documentation commit on branch `docs/m2-acceptance-m3-plan` (no push, no merge)
- **Date:** 2026-10-12 (session date)

````text
Commit the reviewed M2 acceptance record and M3 plan locally. This authorizes one local documentation commit only.

Follow CLAUDE.md. Work only in:
D:\Claude\evidenceguard_agentic_rag

Verify:
- Branch: docs/m2-acceptance-m3-plan
- HEAD: 9d5a93ab1389d8a2b084c8f669df3bf9941a477f
- Origin: https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git
- Exactly five files staged:
  README.md
  docs/decisions/0006-vendor-api-and-readiness.md
  docs/plan.md
  docs/threat-model.md
  prompts.md
- Nothing unstaged or untracked.

If anything differs, report it and stop without repairing it.
Record the accepted staged tree before editing.

Review acceptance
The external reviewer accepts:
- Prompt 46’s M2 acceptance documentation and M3 sequence.
- Prompt 47’s revised M3a specification.
- The 5-second lock_timeout.
- The exhausted-job sweep limit of 10 rows per claim.

These are initial engineering defaults, not measured performance claims.
M3a remains unimplemented. Compose remains unverified.
The reviewer inspected the documentation and independently retrieved M2 CI evidence, but did not run the project suite.

Only these additional edits are authorized:
1. README.md:
   Replace the current claims that the M3 sequence awaits review with wording that the sequence and M3a specification are accepted, while implementation remains pending.
   Update “M3 proposed” in the status heading accordingly.
   Do not imply any M3 code exists.

2. docs/plan.md:
   Mark the 5-second lock timeout and 10-row sweep limit as accepted defaults rather than pending proposals.
   Preserve the rest of the reviewed specification.

3. prompts.md:
   Append a separate acceptance note under Prompt 47.
   Append this prompt verbatim using the next sequential number.
   Add a truthful pre-commit outcome note.
   Preserve earlier entries.

Before committing:
- Show and inspect the exact incremental diff against the accepted staged tree.
- Confirm ADR-0006 and docs/threat-model.md remain byte-identical to that tree.
- Confirm all changes are limited to the authorized status/default wording and prompt-history additions.
- Check relative documentation links and anchors.
- Check staged additions for secrets/private information without printing sensitive values.
- Confirm effective author and committer email:
  257921624+mathewmljourney93@users.noreply.github.com
- Run git diff --cached --check.
- Run gitleaks git --pre-commit --staged --redact --verbose .

If checks pass, create one local commit:
docs: record M2 acceptance and reviewed M3 job specification

Keep the existing attribution convention.
Run gitleaks git --redact --verbose . after committing.
Confirm the parent and clean working tree.

No application tests or builds are needed for these documentation-only changes.

Final handoff:
- Full SHA, parent, subject, author and committer.
- Committed paths.
- COMPLETE incremental diff against the accepted staged tree, excluding prompts.md, directly in fenced diff blocks.
- Prompt-history additions separately.
- Checks actually run and final Git status.
- State that nothing was pushed, M3a is unimplemented and Compose remains unverified.

Do not implement M3a, push, merge, amend, rebase, delete branches, install tools, start Docker or contact a database.
````

**Pre-commit note (recorded before the commit):**
- **Starting state verified:**
  - branch `docs/m2-acceptance-m3-plan`, HEAD `9d5a93a`, the expected origin;
  - exactly the five reviewed files staged, with nothing unstaged or untracked.
  - The accepted staged tree, `40a49a1600bb59fa09f3f09db51a9fb1255aeb63`, was recorded under `.local/` before editing.
- **Authorized edits:**
  - **README:** the status heading now reads "M3 specification accepted, implementation pending", and the "Still planned" item says that the slice sequence and the M3a specification are accepted, implementation is pending and no M3 code exists.
  - **`docs/plan.md`:** the 5 s `lock_timeout` and the 10-row sweep bound are marked as accepted initial defaults.
  - **This prompt history.**
- **Checks on the staged content, including this note:**
  - the incremental diff against the accepted tree;
  - byte identity of ADR-0006 and the threat model;
  - the link and anchor check;
  - the private-content check;
  - `git diff --cached --check`;
  - the staged Gitleaks scan.

  They run before the commit, and the full-history Gitleaks scan runs after it. All results are reported in the session handoff.
- **Not run:** application tests and builds, because only documentation changes.
- **Not authorized:** no push or merge.
- **Still pending:** M3a is unimplemented, and Compose remains unverified.

## Prompt 49: Implement M3a, the durable PostgreSQL job core

- **Stage:** Implementation, milestone M3a, on branch `feat/durable-job-core` (staged for review, no commit)
- **Date:** 2026-10-12 (session date)

````text
Implement M3a: the durable PostgreSQL job core, following the accepted specification in docs/plan.md.

Leave all implementation work staged and uncommitted for external review. No push or merge is authorized.

Follow CLAUDE.md. Work only in:
D:\Claude\evidenceguard_agentic_rag

Starting state
Verify:
- Branch: docs/m2-acceptance-m3-plan
- HEAD: 077c2ba6305737097d3d3f5289e5e5042b8cfaf4
- Parent: 9d5a93ab1389d8a2b084c8f669df3bf9941a477f
- Origin: https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git
- Working tree clean.

If anything differs, report it and stop without repairing it.

Create:
feat/durable-job-core
from the verified HEAD.

Read the accepted M3a specification and relevant ADRs before editing. Preserve the existing package boundaries and architecture. Resolve routine implementation choices yourself and report material deviations.

Scope
Implement only:
- Pure typed job contracts and lifecycle rules.
- Migration 0002 and the jobs model.
- Transactional enqueue, claim, reclaim, heartbeat, completion and failure.
- A reusable fenced-transaction boundary.
- Database-independent tests and real PostgreSQL integration tests.
- Relevant documentation and prompt history.

Do not implement the worker process, handlers, uploads, document/revision/chunk tables, embeddings, model calls or Docker changes. Add no dependencies.

1. Domain contracts and lifecycle
Add evidenceguard_domain.jobs using the existing immutable domain conventions.

Statuses:
queued, running, succeeded, failed, dead.

Rules:
- attempt starts at 0.
- Every successful claim/reclaim increments attempt.
- max_attempts defaults to 3, range 1–10.
- Never increment beyond max_attempts.
- failed means permanent handler failure.
- dead means retryable failure or lease abandonment exhausted the cap.
- All terminal states clear lease fields and set finished_at.
- Retry clears lease fields and schedules the next attempt.
- Terminal jobs cannot be claimed or reset by retries.

Defaults:
- Lease: 60 seconds.
- Future worker heartbeat interval: 20 seconds; no timer in M3a.
- Backoff after failed attempt n:
  min(5 * 2^(n - 1), 60) seconds.
- No jitter.
- Fenced lock_timeout: 5 seconds.
- Exhausted-job sweep: at most 10 rows per claim.

Pure functions receive explicit times supplied by callers; they must not read clocks or databases.

Payload:
- Flat JSON object with string keys and canonical lowercase hyphenated UUID-string values.
- Empty object allowed.
- No tenant field, nesting, arrays, document text or secrets.
- At most 4,096 bytes of canonical UTF-8 JSON.
- Sorted keys and compact separators; key order must not affect identity.
- Preserve immutability without breaking serialization.
- Kind-specific schemas arrive with later handlers.

Use fixed safe messages for LeaseLostError and JobIdempotencyConflictError. Do not expose payload values, SQL or internal exception text through these errors.

2. Schema and migration
Add jobs through migration 0002, revising 0001.

Follow the existing naming convention and tenant constraints:
- UUID primary key.
- tenant_id foreign key to tenants.
- UNIQUE (tenant_id, id).
- UNIQUE (tenant_id, kind, idempotency_key).
- kind: bounded lowercase identifier, maximum 64.
- idempotency_key: non-empty, maximum 128.
- payload: JSONB object.
- status, attempt, max_attempts, run_after.
- locked_by and lease_expires_at.
- last_error: fixed diagnostic code.
- Timezone-aware created_at, updated_at, finished_at.
- Lease fields populated exactly while running.
- finished_at populated exactly for terminal states.
- Status and attempt bounds enforced by database constraints.
- Appropriate partial indexes for queued eligibility and expired leases.

Document precisely which payload restrictions are enforced by application validation and which by PostgreSQL. Do not claim database enforcement of the canonical byte cap unless actually implemented equivalently.

No extension or unrelated table change.

3. Persistence and transaction ownership
Keep database logic in evidenceguard_persistence.
Return typed snapshots rather than session-bound ORM objects.

Enqueue:
- Runs in the caller-owned transaction.
- Tenant comes from ActorContext.
- INSERT ON CONFLICT for the tenant/kind/idempotency key.
- An identical payload and max_attempts returns the existing job unchanged, including terminal jobs.
- Changed payload or max_attempts raises JobIdempotencyConflictError and leaves the existing row unchanged.
- Concurrent inserts must resolve safely under READ COMMITTED.
- Do not reset or reschedule an existing job.

Claim:
- Trusted system operation across tenants.
- Short transaction.
- Bounded exhausted-lease sweep using FOR UPDATE SKIP LOCKED.
- Mark swept jobs dead without incrementing attempt.
- Select eligible jobs deterministically by (run_after, id), using FOR UPDATE SKIP LOCKED.
- Every claim candidate must have attempt < max_attempts.
- Queued candidates must be due; running candidates must have expired leases.
- Exclude exhausted rows from selection so they cannot obstruct eligible work.
- Increment attempt, assign worker ID and create the lease.

Worker IDs are unique per process start; they are not secrets.
The fencing token is (job_id, locked_by, attempt).

4. Fresh time and fencing
Every lease/scheduling decision uses fresh PostgreSQL clock_timestamp(), not worker time, now() or CURRENT_TIMESTAMP.

For heartbeat, completion, failure and fenced effects:
- Apply transaction-local lock_timeout of 5 seconds.
- Acquire the job row lock.
- After acquiring it, check status, token and lease in a separate statement using fresh database time.
- Never reuse a check or time captured before waiting for the lock.
- Refuse missing, terminal, mismatched or expired ownership with LeaseLostError and no effect.
- Keep the lock through the effect and transaction completion.
- An expired lease cannot be revived.
- No provider/network calls while holding the lock.

The reusable fence must allow future handler writes in the same session/transaction. It must not validate ownership in one transaction and perform the effect in another.

State the guarantee correctly: reclaim cannot occur while a valid fence holds the row lock. A transaction can commit shortly after lease expiry.

Ensure rollback and session cleanup on failed effects and commit failures. Make transaction ownership clear so future callers cannot accidentally commit partial handler work.

5. Tests
Add meaningful database-independent tests for:
- Lifecycle transitions and terminal invariants.
- Attempt bounds, defaults and backoff cap.
- Payload shape, canonicalization, UUID values and exact byte limits.
- Safe errors.
- Transaction commit/rollback/cleanup.
- Claim and fence SQL structure.

Add real PostgreSQL tests under the existing disposable-database guard and required-integration mode:
- Upgrade/downgrade/re-upgrade and migration/model drift.
- Constraints and tenant references.
- Identical enqueue, changed payload/configuration, reordered keys, terminal retries and cross-tenant key reuse.
- Concurrent identical and conflicting enqueue.
- Due-time eligibility and deterministic claiming.
- Two concurrent claimers produce only one owner of a job.
- Exhausted rows, including more than the sweep limit, do not block an eligible job.
- A reclaimed stale owner cannot heartbeat, complete, fail or make a fenced write.
- Same worker ID with a newer attempt still fences the older attempt.
- A held fence prevents reclaim during the effect.
- Expired but unreclaimed ownership is refused.
- A lease expiring during a lock wait is refused after acquisition.
- Failed fenced effects roll back.
- Retryable failures and abandoned leases reach dead at the cap; permanent failure ends failed.

Use separate connections, synchronization and bounded waits for concurrency tests. Ensure failures cannot hang CI or leave threads/connections running. Simulate expiry by SQL except for the bounded lock-wait expiry case.

Preserve existing coverage:
- Historical migration 0001 tests should remain meaningful.
- Update installed-head expectations to 0002 where appropriate.
- Do not weaken tests merely because the latest migration changed.

Do not run PostgreSQL tests locally or contact any database. Their execution remains pending authorized publication and CI.

6. Documentation
Add ADR-0007 for the job core, clearly separating implemented local behaviour from PostgreSQL verification still pending.

Update README, plan and threat model narrowly:
- M3a implemented, under review.
- Worker and later slices still absent.
- No crash/concurrency guarantee claimed as verified until PostgreSQL CI passes.
- Compose remains unverified.
- M2 baseline evidence remains intact.

Append this prompt verbatim to prompts.md using the next sequential number, with truthful outcomes. Preserve earlier entries.

7. Verification
Run:
- uv sync --locked
- uv run --locked ruff format --check .
- uv run --locked ruff check .
- uv run --locked mypy
- uv run --locked pytest
- uv build
- Isolated installed-wheel imports and migration-head/resource checks, without a database.
- git diff --cached --check
- gitleaks git --pre-commit --staged --redact --verbose .

Confirm no dependency/lockfile change unless genuinely required; this slice should need none.
Report commands actually run, failures corrected and integration skips accurately.

Final review handoff
- Summarize implementation and material choices.
- Include the COMPLETE staged diff excluding prompts.md directly in fenced diff blocks.
- Split into numbered parts at file boundaries; never truncate or replace files with summaries.
- Use a gitignored .local/ complete diff only if response limits prevent full inline output, identifying any omitted files explicitly.
- Summarize prompt-history additions separately.
- Report verification results, staged paths, branch, full HEAD and Git status.
- Identify PostgreSQL verification as pending.

Do not commit, push, merge, amend, rebase, install unrelated tools, start Docker or contact a database. Leave the work staged for external review.
````

**Outcome (M3a implementation pending review; staged, not committed or pushed):**
- **Starting state verified:**
  - branch `docs/m2-acceptance-m3-plan`, HEAD `077c2ba` with parent `9d5a93a`, the expected origin, a clean tree.
  - Branch `feat/durable-job-core` was created from `077c2ba`.
- **Implemented:**
  - **`evidenceguard_domain.jobs`:**
    - immutable `JobPayload`, `JobRequest`, `JobLeaseToken` and `JobSnapshot` values;
    - the five statuses;
    - pure, time-parameterised transitions: claim or reclaim, exhausted expiry, heartbeat, succeed, retryable and permanent failure;
    - the accepted defaults: 60 s lease, 20 s heartbeat (constant only), `max_attempts` 3 within 1–10, backoff `min(5 * 2^(n - 1), 60)` with no jitter, 5 s lock timeout, 10-row sweep, 4,096-byte canonical payload;
    - fixed-message errors.
  - **Migration `0002` and the `Job` model:** constraints, two partial indexes, no extension, and no change to existing tables.
  - **`evidenceguard_persistence.jobs`:**
    - `enqueue`, in the caller's transaction, with an identity check;
    - `claim`, with a bounded `SKIP LOCKED` sweep and selection;
    - `fenced_transaction`, which takes the lock, then checks ownership with fresh `clock_timestamp()` in a separate statement, and exposes a restricted `FencedSession` with no commit or rollback;
    - `heartbeat`, `complete`, `fail_retryable` and `fail_permanent`.
  - **ADR-0007**, plus narrow README, plan and threat-model updates.
- **Material choices, reported for review:**
  - Payload keys are lowercase identifiers (at most 64 characters), and any key containing `tenant` is rejected.
  - Reclaiming an abandoned lease records `last_error = lease_expired`.
  - Transitions inside a fence re-check ownership with fresh time, so a lease that expires mid-block refuses the transition and rolls back the block.
  - A lock timeout on the fence's lock becomes the fixed `JobLockTimeoutError`; `JobEnqueueRaceError` covers an invisible conflicting row.
  - The guarded disposable-database fixtures moved unchanged from `tests/test_persistence_postgres.py` to `tests/conftest.py`, so the new `tests/test_jobs_postgres.py` shares one copy of the guard.
  - A database-independent test pins the migration's literal CHECK and partial-index text to the model, because `alembic check` compares neither.
- **Tests:**
  - **Database-independent tests added:** lifecycle, payload, error, SQL-structure and fence-protocol tests in `tests/test_jobs.py` and `tests/test_job_store.py`.
  - **Head expectations moved to `0002`.** The `0001` checks are kept (resource, history and offline downgrade), and offline `0002` upgrade and downgrade tests were added.
  - **The existing PostgreSQL round-trip test** now passes through `0001`, `0002`, `0001`, base and back to `0002`.
  - **41 PostgreSQL integration tests** were added in `tests/test_jobs_postgres.py`. **They have not run** against PostgreSQL; no database was contacted.
- **Verified locally** (Windows, Python 3.12):
  - `uv sync --locked`;
  - `uv run --locked ruff format --check .` (76 files formatted);
  - `uv run --locked ruff check .`;
  - `uv run --locked mypy` (no issues, 63 files);
  - `uv run --locked pytest`: **570 passed, 62 skipped**. All 62 skips are PostgreSQL integration tests: 21 existing and 41 new, skipped because `EG_TEST_DATABASE_URL` is not set.
  - `uv build`;
  - an isolated installed-wheel check in a throwaway environment, without database settings: imports from `site-packages`, `create_app()`, both migration resources packaged, head `0002`, packaged readiness heads `{"0002"}`, offline `jobs` DDL, and `eg-api --help` and `eg-admin --help`;
  - required-integration mode without a URL exits 4.
  - `uv.lock` and `pyproject.toml` are unchanged.
  - The staged whitespace check and the staged Gitleaks scan results are in the session handoff.
- **Corrected during the work:**
  - Ruff import order and `SIM117` (nested `with`) findings.
  - Strict Mypy findings: `Any` returns and row-mapping types.
  - Pydantic wrapped the payload error in a `ValidationError`, so `from_mapping` now validates before construction.
  - A test UUID was made of digits only, which made its uppercase variant identical; it now contains letters.
  - Compiled-SQL expectations were updated for the `::VARCHAR` and `::INTEGER` casts.
- **Not verified:**
  - the 41 new PostgreSQL integration tests, and with them every concurrency, stale-worker, lock-wait and rollback guarantee;
  - a re-run of the 21 existing integration tests against migration `0002`.

  Both are pending an authorized publication and CI. The remaining unverified items:
  - Compose;
  - review of this implementation.

## Prompt 50: Complete the M3a review handoff (read-only)

- **Stage:** Read-only review handoff for staged M3a (no file changes)
- **Date:** 2026-10-12 (session date)

````text
Complete the M3a review handoff. Read-only task; do not change the implementation.

Follow CLAUDE.md. Work only in:
D:\Claude\evidenceguard_agentic_rag

Verify:
- Branch: feat/durable-job-core
- HEAD: 077c2ba6305737097d3d3f5289e5e5042b8cfaf4
- The existing 16 M3a files remain staged.
- Nothing unstaged or untracked.

If the state differs, report it and stop without repairing it.

The external reviewer has inspected the production code, migration, model and existing-test changes from Prompt 49. Review is incomplete because seven files were omitted from the inline handoff.

Provide the COMPLETE current staged diffs for these seven files:
1. README.md
2. docs/plan.md
3. docs/threat-model.md
4. docs/decisions/0007-durable-job-core.md
5. tests/test_jobs.py
6. tests/test_job_store.py
7. tests/test_jobs_postgres.py

Use fenced diff blocks, numbered parts at file boundaries.
Do not replace source with summaries or truncate any file.
Do not repeat the production-code diffs already supplied.

If the response limit prevents providing all seven:
- Clearly identify which complete files were included and which remain.
- Keep the full staged diff available at .local/p49/staged.diff.
- End with precise continuation instructions.
- Do not suggest that the review is complete.

Also include the current contents of:
packages/domain/evidenceguard_domain/_base.py
in a fenced python block, as supporting context for reviewing immutable job contracts and datetime validation.

Finish with:
- The current staged tree ID from git write-tree.
- git diff --cached --check result.
- Git status.
- Confirmation that no files were changed and nothing was committed or pushed.

Do not run tests, install anything, start Docker or contact a database.
Do not edit prompts.md during this read-only task. Preserve this prompt for verbatim recording at the next authorized prompt-history update.
````

**Outcome (read-only; recorded with Prompt 52):**
- **State verified:** branch `feat/durable-job-core`, HEAD `077c2ba`, 16 files staged, staged tree `44aacb2852f60fab0e6067e57209f596f01cf147`, nothing unstaged or untracked.
- **Supplied in full:**
  - the diffs of `README.md`, `docs/plan.md`, `docs/threat-model.md`, `docs/decisions/0007-durable-job-core.md`, `tests/test_jobs.py` and `tests/test_job_store.py`;
  - the contents of `_base.py`, with a note that it does not itself require timezone-aware datetimes.
- **Deferred for response length:** `tests/test_jobs_postgres.py`. Its complete diff stayed in `.local/p49/`, with continuation instructions.
- **Checks:** `git diff --cached --check` passed. No tracked file was changed, and nothing was committed or pushed.

## Prompt 51: Provide the final missing M3a review file (read-only)

- **Stage:** Read-only review handoff (no file changes)
- **Date:** 2026-10-12 (session date)

````text
Provide the final missing M3a review file. Read-only; change nothing.

Verify:
- Branch: feat/durable-job-core
- HEAD: 077c2ba6305737097d3d3f5289e5e5042b8cfaf4
- Staged tree: 44aacb2852f60fab0e6067e57209f596f01cf147
- 16 files staged; nothing unstaged or untracked.

If the state differs, report it and stop.

Return ONLY:
1. The COMPLETE staged diff for tests/test_jobs_postgres.py, inside a fenced diff block. Include every line; no summary or truncation.
2. A brief final Git-state confirmation.

Do not repeat previously supplied files.
Do not edit prompts.md, run tests, commit, push or contact a database.
Preserve this prompt for verbatim recording at the next authorized prompt-history update.
````

**Outcome (read-only; recorded with Prompt 52):**
- **State verified** as listed in the prompt.
- **Supplied in full:** the diff of `tests/test_jobs_postgres.py`, after confirming it was byte-identical to the index.
- **No changes:** no file was changed, and nothing was committed or pushed.

**Review note (added with Prompt 52):**
- **Basis of the review:** the external reviewer inspected the complete M3a diffs, from Prompts 49–51. The reviewer did not run the project suite.
- **Corrections required:**
  1. **Job timestamps must be timezone-aware:**
     - `AwareDatetime` for the snapshot timestamps;
     - a fixed `ValueError` for a naive `now`, or one whose offset is `None`, at every public time-dependent function;
     - correct comparison of non-UTC offsets.
  2. **The `FencedSession` boundary must be described accurately.** It omits the direct transaction methods, but it is not a sandbox: `execute` accepts arbitrary SQL, and the underlying objects are reachable. The docstrings, ADR-0007, the threat model and the test name must say so.
  3. **The lock-timeout mapping needs a real PostgreSQL test.**
- **Choices accepted:**
  - lowercase, bounded payload keys and the tenant-key ban;
  - `lease_expired` as the reclaim diagnostic;
  - fresh ownership checks before transitions inside a fence;
  - the fixed lock-timeout and enqueue-race errors;
  - the fixtures moved into `conftest.py`;
  - the offline checks of constraints and index predicates.
- **Status:** the corrections are under review. They are not accepted yet.

## Prompt 52: Correct the M3a review findings

- **Stage:** Corrections to staged M3a work (no commit, no push)
- **Date:** 2026-10-12 (session date)

````text
Correct the M3a review findings. Leave everything staged and uncommitted for review.

Follow CLAUDE.md. Work only in:
D:\Claude\evidenceguard_agentic_rag

Verify:
- Branch: feat/durable-job-core
- HEAD: 077c2ba6305737097d3d3f5289e5e5042b8cfaf4
- Staged tree: 44aacb2852f60fab0e6067e57209f596f01cf147
- Existing 16 M3a files staged.
- Nothing unstaged or untracked.

If anything differs, report it and stop without repairing it.
Record the pre-edit staged tree for the incremental diff.

1. Require timezone-aware job timestamps
In JobSnapshot, use the existing Pydantic AwareDatetime convention for:
- run_after
- lease_expires_at, when present
- created_at
- updated_at
- finished_at, when present

Validate explicit now arguments at the pure lifecycle boundary too:
- Reject a datetime whose tzinfo is absent or whose utcoffset() is None.
- Raise a fixed ValueError without input values.
- Do not assume a naive value means UTC or silently attach a timezone.
- Keep pure functions clock-free.
- Accept aware datetimes with non-UTC offsets and compare their actual instants correctly.

Apply this consistently to public time-dependent predicates and transitions. Do not leave some operations producing incidental TypeError while others accept naive values.

Add focused tests:
- Each snapshot timestamp rejects a naive datetime, including optional fields in otherwise-valid snapshots.
- Validated model_copy cannot introduce a naive timestamp.
- Each public time-dependent operation rejects a naive now with the fixed error.
- A tzinfo object returning utcoffset() = None is rejected.
- Aware non-UTC offsets work correctly around lease/due-time boundaries.

Demonstrate that representative new tests fail against the pre-edit implementation, then restore and verify the corrected files.

2. State the FencedSession boundary accurately
The wrapper omits commit/rollback/close methods, but execute/scalar/scalars accept arbitrary SQL and Python exposes underlying objects.

Correct the module/class docstrings, ADR-0007 and threat-model wording:
- The wrapper discourages accidental transaction termination through ordinary session methods.
- Handlers are trusted application code.
- Handlers must not issue transaction-control SQL, access underlying transaction/connection internals, or modify ownership fields directly.
- The fence guarantee assumes callers preserve its transaction and lock.
- It is not a security sandbox or an enforceable prohibition on every possible early commit.

Keep the existing transaction-ownership design. Do not introduce a SQL parser, blacklist or sandbox.

Rename or clarify the unit test that currently claims the session “cannot end the transaction”: its actual assertion proves only that direct commit/rollback/close methods are absent.

Keep genuine guarantees:
- Lock before fresh ownership check.
- Effects share the same transaction.
- Uncaught failures and commit failures roll back.
- The fence closes after its block or a terminal/requeue transition.

3. Verify the lock-timeout mapping against PostgreSQL
Add a real integration test using the existing guarded disposable database:
- One connection holds the relevant job row lock.
- Another attempts a fenced operation.
- The held lock outlasts the configured 5-second lock_timeout.
- Observe JobLockTimeoutError, with its fixed safe message.
- Confirm the fenced block did not execute and the job/effect rows are unchanged.
- Release locks and close connections/executors in finally paths.
- Use bounded server statements and waits, with sufficient timeout margin.

This test remains skipped locally; do not contact a database.

Other review choices
The reviewer accepts:
- Lowercase bounded payload keys and the conservative tenant-key ban.
- lease_expired as the reclaim diagnostic.
- Fresh ownership checks before lifecycle transitions inside a fence.
- Fixed lock-timeout and enqueue-race errors.
- Moving the guarded fixtures into conftest.py.
- Explicit offline checks for migration constraints and index predicates.

Do not redesign those choices.

Documentation and prompt history
Keep implementation and PostgreSQL verification marked pending review/CI.

Record the read-only handoff prompts verbatim if available in this session and not already recorded, using sequential numbers. Do not invent unavailable prompt text.
Append this prompt verbatim and a separate review/outcome note.
Preserve earlier entries.
State that the reviewer inspected the complete diffs but did not run the project suite.
Do not record acceptance of these corrections yet.

Verification
Run:
- uv run --locked ruff format --check .
- uv run --locked ruff check .
- uv run --locked mypy
- uv run --locked pytest
- uv build
- git diff --cached --check
- gitleaks git --pre-commit --staged --redact --verbose .

Stage only the intended corrections and documentation/history updates.
No new dependencies or schema changes are required.
Report the actual passing/skipped counts; do not reuse old counts.

Final handoff
- Explain the corrections and regression evidence.
- Include the COMPLETE incremental staged diff against the recorded pre-edit staged tree, excluding prompts.md, directly in fenced diff blocks.
- Split at file boundaries if needed; do not truncate.
- Summarize prompt-history additions separately.
- Report actual checks, staged paths, full HEAD and Git status.
- Keep all PostgreSQL verification and Compose unverified.

Do not commit, push, merge, rewrite history, start Docker or contact a database.
````

**Outcome (corrections pending review; staged, not committed or pushed):**
- **Starting state verified** as listed. The pre-edit staged tree, `44aacb2852f60fab0e6067e57209f596f01cf147`, was recorded under `.local/`.
- **Correction 1 (aware time):**
  - `JobSnapshot` timestamps are now `AwareDatetime`.
  - A new `require_aware(now)` is called first in every public time-dependent function: `lease_expired`, `is_claimable`, `is_exhausted_abandoned`, `holds_lease`, `claim`, `expire_exhausted`, `heartbeat`, `succeed`, `fail_permanently` and `fail_retryably`. It raises the fixed `ValueError` "now must be a timezone-aware datetime" for a value with no `tzinfo` or with a `utcoffset()` of `None`.
  - Pure functions still read no clock.
  - A pre-check confirmed that Pydantic's `AwareDatetime` also rejects a `tzinfo` whose `utcoffset()` is `None`.
- **Correction 2 (boundary wording):** the module and `FencedSession` docstrings, ADR-0007 and the threat model now say the following:
  - the wrapper omits the direct transaction methods to prevent accidents by trusted handlers;
  - it is not a sandbox, since `execute` accepts arbitrary SQL and the underlying objects are reachable;
  - handlers must not issue transaction-control SQL, use the underlying session, transaction or connection, or edit ownership fields;
  - the guarantee assumes they preserve the transaction and lock.

  The unit test was renamed to `test_fenced_session_omits_direct_transaction_methods`. No parser, blacklist or sandbox was added.
- **Correction 3 (lock timeout):** a new PostgreSQL test holds the job row lock beyond the real 5-second `lock_timeout`. It expects `JobLockTimeoutError` with its fixed message, a wait of at least about 5 seconds, a block that never ran, no effect row and an unchanged job row. The lock is released and the connection closed in `finally`. **It has not run.**
- **Regression evidence:**
  - With the pre-edit domain module restored temporarily (after confirming it matched the index), **33 of the 35 new aware-time tests failed**.
  - The 2 non-UTC offset tests passed, because they check behaviour the old code already handled correctly.
  - The corrected module was then restored, confirmed byte-identical with `cmp`, and all 35 passed.
- **Verified locally** (Windows, Python 3.12):
  - `uv run --locked ruff format --check .` (76 files formatted);
  - `uv run --locked ruff check .`;
  - `uv run --locked mypy` (no issues, 63 files);
  - `uv run --locked pytest`: **605 passed, 63 skipped**. All 63 skips are PostgreSQL integration tests: 21 existing and 42 job tests, skipped because `EG_TEST_DATABASE_URL` is not set;
  - `uv build`.

  `uv.lock` and `pyproject.toml` are unchanged, and there is no schema change. The staged whitespace check and the Gitleaks scan results are in the session handoff.
- **Not verified:**
  - all PostgreSQL integration tests, including the new lock-timeout test, pending an authorized publication and CI;
  - Compose;
  - review of these corrections.

**Acceptance note (added with Prompt 53):**
- **Accepted for a local commit:** the external reviewer accepted the complete M3a implementation (Prompts 49–51) and the Prompt 52 corrections, as staged tree `ecfffb122382779990aa846e67f7d06527714757`.
- **Basis of the acceptance:** the supplied diffs, and Claude's reported Windows results of 605 passed and 63 PostgreSQL integration tests skipped. The reviewer did not run the suite.
- **Still pending:**
  - all PostgreSQL verification, including the lock-timeout test;
  - Compose;
  - overall M3 acceptance.

**Note on a repeated prompt:** after Prompt 52, the same correction prompt was submitted again. It expected staged tree `44aacb2…`, but the actual tree was already `ecfffb1…` with the corrections applied, so the run stopped at its state check without any change. It is not recorded again here, because its text is identical to Prompt 52.

## Prompt 53: Commit the reviewed M3a work locally

- **Stage:** Local commit of reviewed M3a work on `feat/durable-job-core` (no push, no merge)
- **Date:** 2026-10-12 (session date)

````text
This is a new task: commit the already-reviewed M3a work locally. Do not repeat Prompt 52’s corrections.

Follow CLAUDE.md. Work only in:
D:\Claude\evidenceguard_agentic_rag

Expected starting state:
- Branch: feat/durable-job-core
- HEAD: 077c2ba6305737097d3d3f5289e5e5042b8cfaf4
- Staged tree: ecfffb122382779990aa846e67f7d06527714757
- Origin: https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git
- Exactly 16 M3a files staged.
- Nothing unstaged or untracked.

Verify first. If anything differs, report it and stop.

The external reviewer has accepted the complete M3a implementation and Prompt 52’s corrections for a local commit, based on the supplied diffs and reported Windows results: 605 passed, 63 PostgreSQL tests skipped. The reviewer did not run the suite.

Only change prompts.md:
- Append an acceptance note under Prompt 52.
- Append this prompt verbatim using the next available sequential number.
- Add a truthful pre-commit outcome note.
- Briefly record that the repeated correction prompt stopped without changes.
Preserve earlier entries and avoid duplicating the already-recorded correction prompt.

Confirm every other staged file remains byte-identical to the accepted tree.

Before committing:
- Inspect staged paths and diff.
- Check for secrets/private information without printing sensitive values.
- Confirm author and committer use:
  257921624+mathewmljourney93@users.noreply.github.com
- Run git diff --cached --check.
- Run gitleaks git --pre-commit --staged --redact --verbose .

If clean, create ONE LOCAL commit:
feat: add durable PostgreSQL jobs and lease fencing

Keep the existing attribution convention.

Afterward:
- Run gitleaks git --redact --verbose .
- Confirm the parent, committed paths and clean working tree.
- Confirm committed files other than prompts.md match the accepted tree.

No application tests or builds need rerunning for prompt-history-only additions.

Return:
- Full commit SHA, parent, subject and identity.
- Actual check results.
- Prompt-history additions and final Git status.
- Any incremental diff outside prompts.md, complete in fenced diff blocks; explicitly state if none.
- PostgreSQL verification, Compose and overall M3 acceptance remain pending.

Do not push, merge, amend, rebase, start Docker or contact a database.
````

**Pre-commit note (recorded before the commit):**
- **Starting state verified:**
  - branch `feat/durable-job-core`, HEAD `077c2ba`, the expected origin;
  - staged tree `ecfffb1…`, with exactly 16 M3a files staged and nothing unstaged or untracked;
  - author and committer `257921624+mathewmljourney93@users.noreply.github.com`.
- **This commit** adds the reviewed M3a work and this prompt-history update. Only `prompts.md` changes since the accepted tree.
- **Checks on the staged content, including this note:** the byte-identity comparison, the private-content check, `git diff --cached --check` and the staged Gitleaks scan run before the commit. The full-history Gitleaks scan runs after it. All results are reported in the session handoff.
- **Not rerun:** application tests and builds, because only the prompt history changes. The last local results are the historical Prompt 52 results: 605 passed and 63 PostgreSQL integration tests skipped.
- **Not authorized:** no push or merge.
- **Still pending:**
  - all M3a PostgreSQL verification, including the lock-timeout test;
  - Compose;
  - overall M3 acceptance.

## Prompt 54: Publish reviewed M3a and verify branch CI

- **Stage:** Local documentation commit and publication of `feat/durable-job-core` (no merge, `main` unchanged)
- **Date:** 2026-10-12 (session date)

````text
Publish the reviewed M3a feature branch and verify its CI results. This authorizes pushing only feat/durable-job-core. It does not authorize merging or updating main.

Follow CLAUDE.md. Work only in:
D:\Claude\evidenceguard_agentic_rag

1. Verify the starting state before making changes

Expected:
- Branch: feat/durable-job-core
- HEAD: a133513ea45297fd665f147d6ab6699f6785f3c0
- Parent: 077c2ba6305737097d3d3f5289e5e5042b8cfaf4
- Working tree clean, with nothing staged, unstaged or untracked.
- Origin: https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git
- No upstream configured for this branch.
- Remote main: 9d5a93ab1389d8a2b084c8f669df3bf9941a477f
- No remote feat/durable-job-core branch.
- Remote main is an ancestor of HEAD.
- Effective author and committer email:
  257921624+mathewmljourney93@users.noreply.github.com

Read remote refs to confirm them. If anything differs, stop and report the discrepancy without changing files or refs.

2. Publication preflight

Inspect every commit and tracked-file change that will become public relative to remote main, including the M2 acceptance/M3 specification commit.

Confirm:
- Author and committer identities use the noreply email.
- No .local/ files, backups, bundles, real environment files or credentials are tracked.
- Publication contains the reviewed documentation and M3a implementation.
- Both workflows trigger on a push to this feature branch.
- CI includes Ubuntu verification, Windows verification, PostgreSQL integration and full-history secret scanning.
- The integration job retains EG_REQUIRE_INTEGRATION=1.

Do not modify workflows or application code. If a problem blocks publication, stop and report it.

3. Record this authorization

Change only prompts.md, append-only:
- Record this prompt verbatim as Prompt 54, provided that is the next unused number. Otherwise use the next unused number and explain the numbering.
- Add a truthful preflight note recording the verified starting state, publication scope, checks and authorization.
- State that PostgreSQL verification is pending until CI runs.
- Do not pre-record a successful push or CI result.

Stage only prompts.md. Inspect its staged diff, check for private content, run git diff --cached --check, and run the staged Gitleaks scan.

Create one local commit:
docs: record M3a branch publication authorization

Use the repository-local noreply identity and existing attribution convention. Verify that the commit changes only prompts.md, then run the full-history Gitleaks scan. Stop if any check fails.

No application tests or builds need rerunning locally because only prompt history changed.

4. Publish only the feature branch

After all preflight checks and scans pass, run:

git push --set-upstream origin refs/heads/feat/durable-job-core:refs/heads/feat/durable-job-core

Do not push main, another branch or any tag. Do not force-push.

Confirm the remote feature branch matches the exact published HEAD and remote main remains unchanged.

5. Monitor CI for the exact published SHA

Wait for:
- Ubuntu verification
- Windows verification
- PostgreSQL integration
- Full-history secret scan

Report results only for runs associated with this exact SHA and feature-branch push. Use available read-only GitHub access; do not install tooling or alter authentication configuration.

The previous local results were 605 passed and 63 PostgreSQL tests skipped. These are historical local results, not CI results.

If logs are accessible, report the actual pytest summaries, particularly the integration count and the new lock-timeout test result. If logs are inaccessible, distinguish observed job/step success from inferred test execution. Do not present the expected 63 integration tests as an observed result.

Bound monitoring to 20 minutes. If checks remain pending, report their links and status without claiming completion. If any check fails, report the failing step and available diagnostics, then stop. Do not automatically edit, commit or repush fixes.

6. Final handoff

Return:
- Publication-history commit SHA and parent.
- Exact published SHA.
- Changes to prompts.md.
- Preflight and secret-scan results.
- Workflow and job links with results.
- Observed test counts, or an explicit statement that counts could not be retrieved.
- Local Git status and remote branch/main refs.
- Remaining verification limits.

Include the complete incremental diff outside prompts.md in fenced diff blocks. If none, explicitly say none.

Do not merge, update main, amend, rebase, delete branches, start Docker or contact a local database.

Compose verification and overall M3 acceptance remain pending. Successful M3a CI does not mean the remaining M3 slices are implemented.
````

**Preflight note (recorded before this documentation commit and before any push):**
- **Starting state verified:**
  - branch `feat/durable-job-core`, HEAD `a133513` with parent `077c2ba`;
  - a clean tree, the expected origin, and no upstream configured;
  - author and committer `257921624+mathewmljourney93@users.noreply.github.com`.
- **Remote refs, read before this commit:**
  - `main` is `9d5a93a`;
  - no remote `feat/durable-job-core` exists;
  - remote `main` is an ancestor of HEAD.
- **Publication scope, against remote `main`:** two commits, both with the noreply author and committer, plus this documentation commit:
  - `077c2ba` (the M2 acceptance record and the reviewed M3 specification);
  - `a133513` (the reviewed M3a implementation).

  They change 17 paths: the documentation, `jobs.py` in the domain and persistence packages, migration `0002`, `models.py`, the shared fixtures, and the new and updated tests.
- **Content checks:**
  - no `.local/`, backup, bundle, environment or key files are tracked;
  - a pattern scan of the added lines found no keys, credentialed URLs, tokens, private keys, local user paths or personal email addresses.
- **Workflows**, unchanged relative to `main`:
  - `ci.yml` and `secret-scan.yml` trigger on every push, with no branch filter;
  - CI runs `verify` on Ubuntu 24.04 and Windows 2025, the PostgreSQL 17 + pgvector integration job with `EG_REQUIRE_INTEGRATION: "1"`, and the full-history Gitleaks scan (`fetch-depth: 0`).
- **Authorization:** this prompt authorizes this commit and pushing only `feat/durable-job-core` with the explicit refspec. It does not authorize merging or updating `main`, force-pushing, other refs or tags.
- **Not yet recorded here:**
  - the push and the CI results happen after this commit and are reported in the session handoff;
  - **M3a's PostgreSQL verification is pending until CI runs.** The last local results (605 passed, 63 PostgreSQL integration tests skipped) are historical local results, not CI results.
- **Still pending:**
  - Compose;
  - overall M3 acceptance. M3b–M3f are not implemented.

## Prompt 55: Record verified M3a CI results

- **Stage:** Documentation update for verified M3a CI on `feat/durable-job-core` (staged for review, no commit)
- **Date:** 2026-10-12 (session date)

````text
Record the verified M3a CI results in the project documentation. Leave all changes staged and uncommitted for review. No push or merge is authorized.

Follow CLAUDE.md. Work in:
D:\Claude\evidenceguard_agentic_rag

1. Verify starting state

Expected:
- Branch: feat/durable-job-core
- HEAD and upstream:
  11350e1818c7bd348fa6e6a26b639fe1b21a0e80
- Working tree clean, nothing untracked.
- Origin:
  https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git
- Remote main:
  9d5a93ab1389d8a2b084c8f669df3bf9941a477f

Check remote refs read-only. Stop without changes if the state differs.

2. Evidence independently retrieved by the reviewer

Both runs have head_sha 11350e1818c7bd348fa6e6a26b639fe1b21a0e80,
head_branch feat/durable-job-core, and conclusion success.

CI run:
https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38240768344

Observed job-log summaries:
- Ubuntu job 114782517339:
  605 passed, 63 skipped in 12.71s
- Windows job 114782517028:
  605 passed, 63 skipped in 14.66s
- PostgreSQL integration job 114782517485:
  63 passed, 605 deselected in 16.58s

Secret-scan run:
https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38240768288

Job 114782517013:
21 commits scanned; no leaks found.

The committed lock-timeout test is:
test_a_lock_held_beyond_the_lock_timeout_raises_the_fixed_error

It belongs to the integration suite. All 63 integration tests passed, with no skips or failures. Record that the lock-timeout test passed as part of that suite, without claiming an individually named log entry or individual duration was observed.

The reviewer retrieved the GitHub evidence but did not run the project suite locally.

3. Documentation updates only

Inspect the existing wording and make narrow, consistent updates to:
- README.md
- docs/decisions/0007-durable-job-core.md
- docs/plan.md
- docs/threat-model.md
- prompts.md

Record:
- M3a implementation is reviewed and verified on its feature branch at 11350e1.
- The actual CI summaries and links above.
- Real PostgreSQL verification now covers M3a, including its concurrency, lease fencing and lock-timeout tests.
- M3a is not yet merged into main.
- Compose remains unverified.
- M3b–M3f remain unimplemented, and overall M3 acceptance is pending.
- Passing tests demonstrate the tested behavior, not a general security or performance guarantee.

Update ADR-0007’s status consistently with the repository’s accepted-and-CI-verified ADR convention. Do not redesign the architecture or change engineering defaults.

Do not change application code, tests, dependencies, migrations or workflows.

4. Prompt history

Append this prompt verbatim as Prompt 55 if that is the next unused number; otherwise use the next unused number and explain it.

Add a truthful outcome note recording:
- the reviewer independently retrieved the CI evidence;
- what documentation changed;
- checks actually run in this task;
- that main remains unchanged and no commit, push or merge occurred.

Keep all earlier prompt and outcome text unchanged.

5. Verification and handoff

Check documentation links and consistency.
Inspect staged additions for secrets and private information.
Run:
- git diff --cached --check
- the staged Gitleaks scan

Application tests and builds need not be rerun for documentation-only changes.

Stage only the five authorized files.

Return:
- A concise explanation of the changes.
- Check commands and actual results.
- The staged tree ID, staged paths and Git status.
- The COMPLETE staged diff excluding prompts.md directly in fenced diff blocks.
- Split into numbered parts at file boundaries if needed; never silently truncate.
- A summary of prompts.md additions and confirmation that earlier entries are unchanged.

Leave everything staged and uncommitted.
Do not push, merge, amend, rebase, start Docker or contact a local database.
````

**Outcome (documentation pending review; staged, not committed or pushed):**
- **Starting state verified:**
  - branch `feat/durable-job-core`, HEAD and upstream `11350e1`;
  - a clean tree with nothing untracked, and the expected origin;
  - remote refs read without changing them: `main` at `9d5a93a`, the feature branch at `11350e1`.
- **Evidence:** the external reviewer independently retrieved the CI evidence for `11350e1`:
  - [CI run 38240768344](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38240768344): Ubuntu `605 passed, 63 skipped in 12.71s`; Windows `605 passed, 63 skipped in 14.66s`; integration `63 passed, 605 deselected in 16.58s`;
  - [secret-scan run 38240768288](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38240768288): 21 commits scanned, no leaks found.

  The reviewer did not run the project suite. Claude had observed only the job and step conclusions, because the job logs returned 403 without authentication.
- **Documentation updated:**
  - **README:** M3a is described as reviewed and verified in CI on its branch and not merged, with the 63-test integration result. The plans list merging, then M3b–M3f, with M3 acceptance pending.
  - **ADR-0007:** the status is now *Accepted*, following the review and passing CI at `11350e1`, not yet on `main`. The tests and consequences sections record the CI summaries and links, the lock-timeout test passing as part of the 63-test suite (no individual log line or duration observed), and that the tests show only the tested behaviour.
  - **Plan:** the M3 progress note records the CI evidence, states that M3b–M3f are not started, and that M3 acceptance and Compose remain pending.
  - **Threat model:** the M3a section heading is updated, and a verification line is added with the same limits.
  - No code, tests, dependencies, migrations or workflows changed.
- **Checks run in this task:**
  - a link and anchor check of the four documents;
  - a consistency check of the CI figures;
  - a private-content check of the staged additions;
  - `git diff --cached --check`;
  - the staged Gitleaks scan.

  Exact results are in the session handoff. No application tests or builds were run.
- **No commit, push or merge occurred.** `main` is unchanged at `9d5a93a`.
- **Still pending:**
  - merging M3a into `main`;
  - Compose;
  - M3b–M3f;
  - overall M3 acceptance.

**Acceptance note (added with Prompt 56):**
- **Accepted:** the external reviewer accepted the complete Prompt 55 documentation diff, staged as tree `0f0f06a4d316da773c5ea45bb5cbbc89ac0f15f8`.
- **Evidence for `11350e1`, retrieved independently by the reviewer:**
  - Ubuntu `605 passed, 63 skipped in 12.71s`;
  - Windows `605 passed, 63 skipped in 14.66s`;
  - PostgreSQL `63 passed, 605 deselected in 16.58s`;
  - secret scan: 21 commits scanned, no leaks.
- **Basis:** the reviewer did not run the project suite locally.

## Prompt 56: Commit verified M3a documentation and fast-forward main

- **Stage:** Local documentation commit, publication of `feat/durable-job-core`, and an authorized fast-forward of `main` after CI passes
- **Date:** 2026-10-12 (session date)

````text
Commit the reviewed M3a verification documentation, publish the feature branch, and fast-forward main only after all four required CI checks pass.

Follow CLAUDE.md. Work in:
D:\Claude\evidenceguard_agentic_rag

1. Verify starting state

Expected:
- Branch: feat/durable-job-core
- HEAD and upstream:
  11350e1818c7bd348fa6e6a26b639fe1b21a0e80
- Staged tree:
  0f0f06a4d316da773c5ea45bb5cbbc89ac0f15f8
- Exactly five staged files:
  README.md
  docs/decisions/0007-durable-job-core.md
  docs/plan.md
  docs/threat-model.md
  prompts.md
- Nothing unstaged or untracked.
- Origin:
  https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git
- Remote feature branch: 11350e1818c7bd348fa6e6a26b639fe1b21a0e80
- Local and remote main:
  9d5a93ab1389d8a2b084c8f669df3bf9941a477f
- Main is an ancestor of HEAD.
- Effective author and committer email:
  257921624+mathewmljourney93@users.noreply.github.com

Read remote refs freshly. Stop without changes if anything differs.

2. Preserve the accepted documentation

Record the accepted staged tree before editing.

The reviewer accepted Prompt 55’s complete documentation diff, based on that diff and independently retrieved GitHub evidence:
- Ubuntu: 605 passed, 63 skipped in 12.71s
- Windows: 605 passed, 63 skipped in 14.66s
- PostgreSQL: 63 passed, 605 deselected in 16.58s
- Secret scan: 21 commits scanned, no leaks

The reviewer did not run the project suite locally.

Keep all four non-history documents byte-identical to the accepted tree. Their statements that M3a is not yet merged are true at this point; do not record future publication results.

Change only prompts.md, append-only:
- Add an acceptance note under Prompt 55.
- Record this prompt verbatim as Prompt 56 if that is the next unused number; otherwise use the next unused number and explain it.
- Add a truthful preflight note covering verified state, checks and the publication authorization below.
- Do not pre-record push, CI or main-update success.
- Keep earlier entries unchanged.

3. Commit

Inspect staged paths and diff, confirm the noreply identity, check additions for secrets/private information, run git diff --cached --check and the staged Gitleaks scan.

Create one commit:
docs: record verified M3a results and main publication authorization

Use the existing attribution convention.

Verify:
- Parent is 11350e1818c7bd348fa6e6a26b639fe1b21a0e80.
- Exactly the five authorized files changed.
- Every file except prompts.md matches the accepted staged tree.
- Working tree is clean.

Run the full-history Gitleaks scan before publication. Stop on any failure.

No local application tests or builds need rerunning for documentation-only changes.

4. Publish the feature branch first

Push only:
git push origin refs/heads/feat/durable-job-core:refs/heads/feat/durable-job-core

Monitor these four checks for the exact new commit SHA:
- Ubuntu verification
- Windows verification
- PostgreSQL integration
- Full-history secret scan

Use available read-only GitHub access. Do not install tooling or change authentication configuration.

Allow at most 20 minutes for this monitoring phase. If anything fails or remains pending, report it and stop before touching main. Do not automatically fix or repush.

Report observed test summaries when logs are accessible. Otherwise report job conclusions and explicitly say the counts were not observed. Do not reuse 11350e1’s counts as observed results for the new SHA.

5. Fast-forward main only after all four checks succeed

Fetch main and the feature branch again, then confirm:
- Remote main remains exactly 9d5a93ab1389d8a2b084c8f669df3bf9941a477f.
- Remote feature branch matches the newly verified SHA.
- Main is an ancestor of that SHA.
- Local main equals origin/main and has no independent commits.
- Working tree is clean.

If any condition differs, stop and report it.

Switch to main and fast-forward it to the verified SHA using git merge --ff-only. Create no merge commit.

Push only:
git push origin refs/heads/main:refs/heads/main

Monitor all four checks for that exact SHA’s main-push runs, again for at most 20 minutes.

If a main check fails or remains pending, report it accurately. Do not automatically revert, rewrite history or make fixes.

6. Final handoff

Return:
- Commit SHA, parent, subject and identity.
- Prompt-history additions.
- Preflight and scan results.
- Feature-branch and main workflow/job links and conclusions.
- Actual observed test counts, or the log-access limitation.
- Before/after remote refs and final Git status.
- Remaining limits: Compose unverified, M3b–M3f unimplemented, overall M3 acceptance pending.
- Note that the committed documentation predates the main update; recording that result belongs in a later documentation task.

Include the complete incremental diff against the accepted staged tree, excluding prompts.md. If none, explicitly say none.

Do not change application code, tests, dependencies, migrations or workflows.
Do not force-push, amend, rebase, squash, delete branches or push tags.
Do not start Docker or contact a local database.
Do not begin M3b in this task.
````

**Preflight note (recorded before the commit, publication and any change to `main`):**
- **Starting state verified,** with remote refs read freshly:
  - branch `feat/durable-job-core`, HEAD and upstream `11350e1`;
  - staged tree `0f0f06a…`, with exactly the five reviewed files staged and nothing unstaged or untracked;
  - the expected origin, and the remote feature branch at `11350e1`;
  - local and remote `main` at `9d5a93a`, an ancestor of HEAD;
  - author and committer `257921624+mathewmljourney93@users.noreply.github.com`.
- **The accepted tree** `0f0f06a…` was recorded before editing. The four non-history documents stay byte-identical to it. Their statement that M3a is not yet merged is true when this note is written.
- **Authorization:** this prompt authorizes, in order:
  1. this commit;
  2. pushing only the feature branch;
  3. **only after** Ubuntu verification, Windows verification, PostgreSQL integration and the full-history secret scan all succeed for the exact new SHA, and remote `main` is confirmed still at `9d5a93a` and an ancestor of it, fast-forwarding local `main` with `git merge --ff-only`;
  4. pushing only `main`, then monitoring its checks.

  Each monitoring phase is limited to 20 minutes. No force-push, merge commit, amend, rebase, squash, branch deletion or tag push is authorized.
- **Not yet recorded here:** the push, the CI results and any `main` update happen after this commit and are reported in the session handoff. Recording them needs a later documentation task.
- **Not rerun:** application tests and builds, because only the prompt history changes.
- **Still pending:**
  - Compose;
  - M3b–M3f;
  - overall M3 acceptance.

**Outcome note for Prompt 56 (added with Prompt 57; publication and CI happened after the Prompt 56 commit):**
- **Commit:** `b3f984552bf22cf6350702330d30851f3e08b3f4`, with parent `11350e1`. Its four documents were byte-identical to the accepted tree `0f0f06a…`. The staged and full-history Gitleaks scans found no leaks.
- **Feature push:** `feat/durable-job-core` moved from `11350e1` to `b3f9845`.
  - [CI run 38241917267](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38241917267) succeeded: Ubuntu, Windows and integration.
  - [Secret-scan run 38241916958](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38241916958) succeeded.
- **Fast-forward of `main`:** after all four checks passed and a fresh fetch confirmed the preconditions, `main` was fast-forwarded with `git merge --ff-only` and pushed from `9d5a93a` to `b3f9845`. No merge commit, force-push or tag push was made.
- **`main` CI for exactly `b3f9845`:**
  - [CI run 38242144844](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38242144844) and [secret-scan run 38242144876](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38242144876) succeeded.
  - From logs retrieved independently by the external reviewer:
    - Ubuntu `605 passed, 63 skipped in 7.56s`;
    - Windows `605 passed, 63 skipped in 14.86s`;
    - PostgreSQL `63 passed, 605 deselected in 16.17s`;
    - secret scan: 22 commits scanned, no leaks found.
  - Claude saw only job conclusions; the unauthenticated log endpoint returned 403.

## Prompt 57: Record M3a on main and propose the M3b worker specification

- **Stage:** Documentation only, on branch `docs/m3b-worker-spec` (staged for review, no commit)
- **Date:** 2026-10-12 (session date)

````text
Prepare the detailed M3b worker specification for review, and record M3a’s verified publication on main. Documentation only: do not implement M3b yet.

Follow CLAUDE.md. Work in:
D:\Claude\evidenceguard_agentic_rag

1. Verify starting state

Expected:
- Branch: main
- HEAD and origin/main:
  b3f984552bf22cf6350702330d30851f3e08b3f4
- Working tree clean, nothing untracked.
- Origin:
  https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git

Read remote refs freshly. Stop without changes if anything differs.

Create a new local branch:
docs/m3b-worker-spec

If that branch already exists, stop and report its state rather than resetting or reusing it.

2. Read the existing design and implementation

Read CLAUDE.md, the relevant plan sections, ADR-0003, ADR-0007, packaging/import-boundary guidance, the implemented domain and persistence job modules, logging configuration and relevant tests.

Base the specification on the actual M3a interfaces. Preserve the accepted architecture: plain Python, PostgreSQL-backed jobs, leases and fenced transactions. No new queue or orchestration framework.

3. Record M3a publication

Narrowly update README.md, ADR-0007, docs/plan.md and docs/threat-model.md:
- M3a was fast-forwarded onto main at b3f9845.
- All four main-push checks passed for that exact SHA.
- Keep the earlier 11350e1 evidence as historical evidence.
- Compose remains unverified.
- M3b–M3f remain unimplemented and overall M3 acceptance remains pending.

The reviewer independently retrieved these main-push results:

CI run:
https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38242144844

- Ubuntu job 114787118333:
  605 passed, 63 skipped in 7.56s
- Windows job 114787118106:
  605 passed, 63 skipped in 14.86s
- PostgreSQL job 114787118281:
  63 passed, 605 deselected in 16.17s

Secret-scan run:
https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38242144876

- Job 114787118292:
  22 commits scanned; no leaks found.

Both runs have head_sha b3f984552bf22cf6350702330d30851f3e08b3f4,
head_branch main and conclusion success.

The reviewer retrieved GitHub logs but did not run the project suite locally.

4. Write a detailed M3b specification in docs/plan.md

Mark the new specification Proposed, awaiting review.

Define concrete interfaces, execution order, failure handling and test criteria for:

- The evidenceguard_worker application package and eg-worker command, consistent with the existing packaging and import boundaries.
- Validated settings and safe CLI errors. No secrets or database URLs in output.
- A single active job per worker process initially, unless existing accepted decisions require otherwise.
- Process worker identity using the existing identity mechanism, without hostname or personal identifiers.
- Polling with an interruptible wait, including idle polling and database-error backoff. Propose explicit bounded defaults and explain them.
- A handler registry and handler context carrying the claimed job, cancellation/lease-loss state and access to fenced writes.
- Ownership of the job outcome: who completes or fails the job, and how handler effects and terminal transitions avoid contradictory or duplicate completion.
- Heartbeats every 20 seconds with the existing 60-second lease, using separate transactions and independent sessions.
- Session/thread ownership: never share a SQLAlchemy Session between heartbeat and handler execution.
- How heartbeat exceptions, database outages, lease expiry and LeaseLostError affect execution.
- How cancellation is checked immediately before the next fenced write, while the database fence remains the final ownership check.
- Cooperative cancellation limits: Python cannot safely terminate an arbitrary running thread. Do not promise that lease loss instantly stops all handler computation or external calls.
- Retryable and permanent handler errors, fixed persisted error codes, unknown job kinds and unexpected exceptions.
- Reuse of M3a’s attempt cap and scheduled retry backoff without introducing a second conflicting retry mechanism.
- Completion/failure races with heartbeats and shutdown.
- SIGINT/SIGTERM behavior where supported, Windows-compatible testing, stopping new claims, bounded draining and what happens to an unfinished lease.
- Cleanup of owned engines, sessions, heartbeat tasks and handler execution resources.
- Privacy-safe fixed logging events compatible with the current formatter. Identify any required reviewed event-table additions.
- At-least-once execution limits and the requirement that future handlers make durable effects through the existing fence.

Resolve the design of the test handler explicitly:
- M3b has no ingestion handler yet.
- Propose a minimal way to test the runtime without exposing an unrestricted production test-job command or adding document/chunk functionality.
- Define what eg-worker does when no production handlers are registered.

Give a proposed file list and a focused verification plan:
- Database-independent tests using controlled clocks/events and fake stores.
- Real PostgreSQL tests for worker claim/heartbeat/outcome integration and lease loss before a fenced write.
- Race tests for heartbeat versus completion and shutdown.
- Packaging, installed-wheel and CLI checks.
- Avoid unbounded sleeps and tests that merely repeat implementation.

Identify new engineering choices as proposals. Explain genuine conflicts with existing decisions instead of silently changing them.

Do not add migrations, worker code, tests, dependencies, Docker services or new API endpoints in this task.

5. Prompt history

Append this prompt verbatim as Prompt 57 if that is the next unused number; otherwise use the next unused number and explain it.

Add a truthful outcome note:
- M3a publication and CI evidence came from reviewer-retrieved logs.
- M3b specification is proposed, not accepted or implemented.
- Checks actually run.
- No commit, push or merge occurred.

Keep all earlier entries unchanged.

6. Verification and review handoff

Stage only:
- README.md
- docs/decisions/0007-durable-job-core.md
- docs/plan.md
- docs/threat-model.md
- prompts.md

Check documentation links and consistency.
Inspect staged additions for secrets/private information.
Run git diff --cached --check and the staged Gitleaks scan.

No application tests or builds are needed for documentation-only changes.

Return:
- A concise explanation of the proposed worker design.
- New decisions and any unresolved questions.
- Check commands and actual results.
- Staged tree ID, staged paths and Git status.
- COMPLETE staged diff excluding prompts.md, directly in fenced diff blocks.
- Split large output into numbered parts at file boundaries and provide every part. Never silently truncate.
- Summary of prompts.md additions and confirmation that earlier entries are unchanged.

Leave everything staged and uncommitted for review.
Do not push, merge, amend, rebase, start Docker or contact a local database.
````

**Outcome (documentation pending review; staged on `docs/m3b-worker-spec`, not committed or pushed):**
- **Starting state verified:**
  - branch `main`, HEAD and `origin/main` `b3f9845` (remote refs read freshly), a clean tree, the expected origin.
  - Branch `docs/m3b-worker-spec` did not exist locally or on the remote, and was created from `b3f9845`.
- **M3a publication recorded** in README, ADR-0007, the plan and the threat model:
  - M3a on `main` at `b3f9845`, with all four `main`-push checks passing;
  - the counts from the external reviewer's independently retrieved logs: Ubuntu `605 passed, 63 skipped in 7.56s`, Windows `605 passed, 63 skipped in 14.86s`, PostgreSQL `63 passed, 605 deselected in 16.17s`, and a secret scan of 22 commits with no leaks.
  - The README's verified baseline moved to `b3f9845`. The earlier `9d5a93a` and `11350e1` evidence is kept as historical evidence.
  - Compose is unverified; M3b–M3f are unimplemented; M3 acceptance is pending.
- **M3b specification:** added to `docs/plan.md` and marked **PROPOSED, awaiting review**. It is neither accepted nor implemented. It covers:
  - the package and command;
  - settings and CLI errors;
  - one job per process;
  - identity and polling defaults;
  - the registry, context and outcome ownership, including atomic `finish=True`;
  - heartbeats, threads and sessions;
  - cooperative cancellation and its limits;
  - error codes;
  - shutdown and draining;
  - cleanup and logging additions;
  - the no-handlers behaviour and the test-handler approach;
  - files, the verification plan, exclusions and ten decisions requested at review.

  No code, tests, migrations, dependencies, workflows or Docker files changed.
- **Checks run:**
  - the link and anchor check and a consistency check of the four documents;
  - a private-content check of the staged additions;
  - `git diff --cached --check`;
  - the staged Gitleaks scan.

  Exact results are in the session handoff. No application tests or builds were run.
- **No commit, push or merge occurred.** `main` is unchanged at `b3f9845`.

## Prompt 58: Correct the proposed M3b specification for lifecycle and shutdown edge cases

- **Stage:** Documentation only, on branch `docs/m3b-worker-spec` (staged for review, no commit)
- **Date:** 2026-10-12 (session date)

````text
Correct the proposed M3b specification for lifecycle and shutdown edge cases. Documentation only; do not implement or commit anything.

Follow CLAUDE.md. Work in:
D:\Claude\evidenceguard_agentic_rag

Expected starting state:
- Branch: docs/m3b-worker-spec
- HEAD: b3f984552bf22cf6350702330d30851f3e08b3f4
- Staged tree: 340216a359a04b7000f13fa71f1a5ecc3e9e0ba8
- Exactly five staged files:
  README.md
  docs/decisions/0007-durable-job-core.md
  docs/plan.md
  docs/threat-model.md
  prompts.md
- Nothing unstaged or untracked.
- Expected origin for evidenceguard-agentic-rag.

Stop without changes if the state differs. Record the pre-edit staged tree for the incremental review diff.

The reviewer accepts the M3a publication documentation and the broad M3b architecture. The worker specification remains proposed until the corrections below are reviewed.

1. Heartbeat join timeout

The current statement that a bounded join guarantees no heartbeat/outcome race is incorrect: the heartbeat may still be running after join returns.

Specify:
- Set the heartbeat stop event, then join for the stated bound.
- Check whether the thread actually stopped.
- If it remains alive, do not record a runtime outcome or claim another job. Cancel further handler activity cooperatively and take the abnormal shutdown path.
- Preserve database fencing as the final ownership check.
- Explain that a heartbeat already in flight may still complete; setting an event does not cancel a database call.
- Add a test where heartbeat remains blocked beyond the join deadline, proving no outcome and no subsequent claim occur.

Keep the 10-second join value as a proposed default, not a guarantee about database-call duration.

2. Lease loss and live handlers

Define what the supervisor does if lease loss is detected while a handler continues running:
- Request cooperative cancellation.
- Stop renewing the lease.
- Wait a bounded grace period.
- If the handler exits, record no stale outcome.
- If it remains alive, terminate the worker process through the abnormal shutdown path; never move on to another job in that process.

This preserves the one-active-handler-per-process rule.

Distinguish the Python runtime returning an abnormal result from the CLI process actually exiting. A daemon thread may continue running while the surrounding Python process remains alive.

Add tests for both cooperative and uncooperative handlers after lease loss, including prevention of another claim.

3. Atomic finish and subsequent exceptions

Define a thread-safe committed-finish state:
- It is set only after the finish=True transaction context has exited successfully, including commit.
- A rolled-back finish must not mark the job completed.
- Once finish has committed, the runtime must never attempt another completion, retry or permanent failure, even if the handler later raises.
- A later handler exception is a fixed diagnostic event; it cannot change the committed job outcome.
- Subsequent context operations are refused.
- Coordinate heartbeat handling with committed finish so a completion-related LeaseLostError is not misreported as ownership theft.

Keep uncertain commit outcomes honest: if commit raises and whether it committed is unknown, do not claim success. Any recovery/outcome attempt remains fenced, and durable effects must be idempotent.

Add tests for:
- finish commits, then handler raises;
- finish block raises and rolls back;
- commit raises;
- heartbeat collides with atomic finish.

The promise should be no contradictory second committed outcome, not that an outcome is always successfully recorded.

4. Accurate shutdown and timing limits

Remove these unsupported implications:
- “30 s is less than the 60 s lease, so a job that finishes during drain still holds a valid lease.”
- Disposing the engine closes connections currently checked out by live threads.
- An in-flight database call necessarily finishes within the heartbeat join deadline.

Replace them with:
- Lease validity depends on actual successful renewals and the database fence, not the drain duration alone.
- Drain, cancellation and join waits are bounded supervisor waits.
- Existing connect, pool and lock timeouts do not form a total deadline for every database operation or network failure.
- Engine disposal is pool cleanup; it does not forcibly cancel checked-out sessions or running handlers.
- Actual process termination closes its connections; uncommitted transactions then roll back when PostgreSQL detects the disconnect.
- Do not claim immediate server-side rollback or lease reclaim if a connection or transaction remains live.
- Claim itself can be in flight when a stop is requested. Define the post-claim stop check and handling of an acquired job without starting a new handler.

Define the initial local lease deadline conservatively from the monotonic time captured before claim begins. For heartbeat renewals, update it only after a confirmed successful renewal, using the pre-call monotonic time. Local checks remain conservative approximations; PostgreSQL decides actual lease validity.

Add focused test cases for delayed claim return, shutdown during claim, heartbeat outage during drain, and checked-out resources remaining active at abnormal shutdown.

5. Small interface clarifications

Specify:
- kinds=None preserves existing claim behavior.
- An empty kinds collection yields no candidate; it must never mean “claim all”.
- Kind values are validated, and define whether the global exhausted-job sweep still runs for an empty filter.
- --once handles no claimable job without waiting forever.
- Proposed log fields are populated from validated identifiers/enums; opening the formatter allowlist does not make arbitrary field values safe.
- The worker’s handler wrapper follows M3a’s trusted-code convention and is not a security sandbox.

The existing proposed defaults, empty production registry, test-only handlers, safe parser duplication and installed-wheel CLI check are reasonable. Keep them proposed pending final specification review.

6. Scope, history and handoff

Change only docs/plan.md and prompts.md unless another staged document contains wording directly contradicted by these corrections. Explain any such necessary edit.

Append this prompt verbatim as Prompt 58 if it is the next unused number; otherwise use the next unused number and explain it.

Record the review findings and correction outcome honestly. Earlier prompt entries remain unchanged.

Check links, consistency and private content.
Run git diff --cached --check and the staged Gitleaks scan.
No application tests or builds are needed.

Return:
- Explanation of the corrections and any remaining unresolved design choices.
- Actual check results.
- New staged tree ID, staged paths and Git status.
- COMPLETE incremental diff against the recorded pre-edit staged tree, excluding prompts.md, in fenced diff blocks.
- Prompt-history additions.

Leave changes staged and uncommitted.
No code, tests, dependency, migration or workflow changes.
No push, merge, Docker or database contact.

````

**Review findings recorded with this prompt (from the external reviewer of Prompt 57):**
- The M3a publication documentation and the broad M3b architecture were accepted. The M3b specification stays proposed.
- The Prompt 57 specification overstated several lifecycle guarantees:
  - that a bounded heartbeat join prevents any heartbeat/outcome race;
  - that a 30 s drain under a 60 s lease keeps the lease valid;
  - that engine disposal closes connections checked out by live threads;
  - that in-flight database calls finish within the join deadline.
- It also left these undefined:
  - lease loss with a live handler;
  - the committed-finish state, and later handler exceptions;
  - a claim in flight at shutdown;
  - the local lease deadline;
  - the semantics of the `kinds` filter;
  - `--once` termination;
  - the provenance of log-field values.

**Outcome (documentation pending review; staged on `docs/m3b-worker-spec`, not committed or pushed):**
- **Starting state verified:** branch `docs/m3b-worker-spec`, HEAD `b3f9845`, staged tree `340216a…` with exactly the five expected files, nothing unstaged or untracked, the expected origin. The pre-edit staged tree was recorded for the incremental diff.
- **Only `docs/plan.md` changed,** besides this file. The M3b section was rewritten to apply the six corrections and remains marked **PROPOSED**:
  - the heartbeat join is followed by a liveness check; a still-alive thread means no outcome, no further claim and the abnormal shutdown path;
  - lease loss with a live handler: cooperative cancellation, renewal stops, a bounded grace, no stale outcome, and abnormal shutdown if a thread stays alive. The runtime's abnormal result is distinguished from the CLI's process exit;
  - a thread-safe `none`/`committed`/`uncertain` finish state, with no second outcome after a committed finish, and uncertain commits never reported as success;
  - the unsupported timing and disposal claims were removed. A post-claim stop check and a conservative monotonic lease deadline were added;
  - the `kinds` semantics, `--once` termination, validated log-field sources and the not-a-sandbox wording;
  - the matching tests, two new unresolved questions and the updated decisions list.
- **No other staged document needed changes:** README, ADR-0007 and the threat model contain no wording that these corrections contradict.
- **Checks run:**
  - the link and anchor check;
  - a consistency search for the removed claims;
  - a private-content check of the changed text;
  - `git diff --cached --check`;
  - the staged Gitleaks scan.

  Exact results are in the session handoff. No application tests or builds were run.
- **No code, test, dependency, migration or workflow changes; no commit, push, merge, Docker or database contact.**

**Acceptance note for Prompt 58 (added with Prompt 59):**
- **What was reviewed:** the external reviewer inspected the complete Prompt 57 documentation diff and the Prompt 58 incremental corrections (staged tree `3ab25e4…`). They did not run the project suite or any application checks.
- **Result:** the corrected M3b specification was accepted, subject to five narrow clarifications applied under Prompt 59:
  - wording for at most one concurrently active handler;
  - blocking supervisor operations, with no total shutdown deadline;
  - pending-refusal coordination between the atomic finish and heartbeats;
  - irreversible cancellation;
  - uncertain-finish tests covering both commit possibilities.
- **Settled choices:**
  - at most one concurrently active handler per process, with sequential jobs allowed;
  - the `kinds` filter semantics;
  - atomic finish and fenced runtime outcomes;
  - the fixed error codes and the reviewed log events and fields;
  - `worker_shutdown` retries after a cooperative shutdown or a post-claim stop, when ownership remains valid;
  - the timing defaults, as initial engineering defaults, not measured guarantees;
  - conservative monotonic lease deadlines;
  - a separate safe worker argument parser;
  - exit 4 with an empty production registry, before settings are loaded;
  - `os._exit(5)` from the CLI after an abnormal result, while the Python API returns that result;
  - `--once` exits 1 on a database error, without retrying;
  - no production worker statement timeout in M3b, with the limitation documented;
  - authorization for the M3b implementation to add `eg-worker --help` to the CI installed-wheel check.
- **Implementation of M3b has not started.**

## Prompt 59: Accept the M3b worker specification and commit it locally

- **Stage:** Documentation only, on branch `docs/m3b-worker-spec` (local commit authorized; no push)
- **Date:** 2026-10-12 (session date)

````text
Finalize and commit the reviewed M3b worker specification locally. Do not implement M3b or push anything.

Follow CLAUDE.md. Work in:
D:\Claude\evidenceguard_agentic_rag

1. Verify starting state

Expected:
- Branch: docs/m3b-worker-spec
- HEAD:
  b3f984552bf22cf6350702330d30851f3e08b3f4
- Staged tree:
  3ab25e4752f23e5cd116b180c30ed75bd42b4408
- Exactly five staged files:
  README.md
  docs/decisions/0007-durable-job-core.md
  docs/plan.md
  docs/threat-model.md
  prompts.md
- Nothing unstaged or untracked.
- Expected origin:
  https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git

Stop without changes if anything differs. Record the accepted staged tree before editing.

2. Acceptance and settled decisions

The reviewer inspected the complete Prompt 57 documentation diff and Prompt 58 incremental corrections, without running the project suite.

Accept the corrected M3b specification, subject to the narrow clarifications below.

Settle the proposed choices:
- Single concurrently active handler per process; sequential jobs are allowed.
- kinds filter with the documented None/empty/validation/sweep semantics.
- Atomic finish and fenced runtime outcomes.
- Fixed new error codes and reviewed logging events/fields.
- Cooperative shutdown and post-claim stop use worker_shutdown retries when ownership remains valid.
- Proposed polling, drain, cancellation, lease-loss grace and heartbeat-join defaults are accepted as initial engineering defaults, not measured guarantees.
- Conservative monotonic lease deadlines.
- Separate safe worker argument parser.
- Empty production registry exits 4 before database settings are loaded.
- Abnormal CLI shutdown exits the process with code 5 using os._exit; the Python API returns an abnormal result.
- --once makes one claim attempt and exits 1 on a database error, without retrying.
- No production worker statement timeout is added in M3b. Document the resulting limitation accurately.
- The future implementation may add eg-worker --help to the CI installed-wheel check. This authorizes that narrow workflow change when implementing M3b.

3. Final specification clarifications

Make only these narrow corrections:

A. Concurrent-handler wording
Replace “one active handler per worker process, ever” with “at most one concurrently active handler per worker process.” Sequential processing is intended.

B. Blocking supervisor operations
The absence of a statement timeout must not be described as every hung statement being bounded by supervisor waits.

Explicitly state:
- Claim and runtime outcome recording are synchronous supervisor operations.
- If either blocks, the supervisor may not reach its timed shutdown checks until the call returns.
- Signals set flags and do not automatically cancel these calls.
- The abnormal exit path bounds lingering background threads only once the supervisor reaches it.
- A total process shutdown deadline is not guaranteed in M3b.

C. Completion/heartbeat coordination
Define synchronization around atomic finish so a heartbeat refusal during the interval between database commit and publication of the local committed flag does not prematurely trigger lease-loss cancellation.

The heartbeat can record a pending refusal. Classify it after the in-progress finish resolves:
- confirmed committed finish: expected terminal-state refusal;
- rollback or uncertain finish: apply conservative lease-loss/unknown-outcome handling.

Do not hold a shared state lock across database I/O in a way that prevents the supervisor from observing deadlines.

Add a planned deterministic race test for this exact commit/publication interval.

D. Irreversible cancellation
Once the supervisor has latched lease loss or cancellation for an attempt, a late successful heartbeat must not revive that attempt or permit further context writes.

A heartbeat success received after cancellation may have extended the database lease, but the local attempt remains cancelled. Document that reclaim may therefore be delayed.

E. Uncertain finish tests
Cover both possibilities:
- commit succeeded but acknowledgment failed: no second committed outcome;
- commit did not succeed: recovery remains fenced and idempotent.

Do not assume every commit exception means the database fence will refuse a subsequent outcome.

4. Documentation status

Mark the M3b specification accepted at review, implementation pending.
Update README.md consistently.
Keep M3b–M3f unimplemented, Compose unverified and overall M3 acceptance pending.

Preserve the accepted M3a publication evidence and engineering architecture. No additional redesign.

5. Prompt history

Append this prompt verbatim as Prompt 59 if that is the next unused number; otherwise use the next unused number and explain it.

Add an acceptance note under Prompt 58 recording:
- the reviewed original and correction diffs;
- the final clarifications and settled choices above;
- that the reviewer did not run application checks;
- that implementation has not started.

Add a truthful pre-commit note. Earlier history remains unchanged.

6. Checks and local commit

Inspect staged paths and the complete incremental diff against the recorded accepted tree.
Check documentation links, consistency and private content.
Confirm author and committer use:
257921624+mathewmljourney93@users.noreply.github.com

Run git diff --cached --check and the staged Gitleaks scan.

Create one LOCAL commit:
docs: accept M3b worker specification and record M3a main results

Use the existing attribution convention.

After committing:
- Run the full-history Gitleaks scan.
- Verify parent, committed paths, identity and clean working tree.
- Confirm main was not changed.

No application tests or builds are needed for documentation-only changes.

7. Handoff

Return:
- Commit SHA, parent, subject and identity.
- Settled choices and final clarifications.
- Actual checks and results.
- Prompt-history additions.
- COMPLETE incremental diff against the accepted staged tree, excluding prompts.md, in fenced diff blocks.
- Final Git status and remaining limitations.

No worker code, tests, dependencies, migrations or workflow edits in this task.
Do not push, merge, amend, rebase, start Docker or contact a database.
````

**Pre-commit note (written before the local commit):**
- **Starting state verified:**
  - branch `docs/m3b-worker-spec`, HEAD `b3f9845`;
  - staged tree `3ab25e4…` with exactly the five expected files;
  - nothing unstaged or untracked, and the expected origin.

  The accepted staged tree was recorded before editing.
- **Changes:**
  - `docs/plan.md`: the M3b specification is marked accepted at review, implementation pending, with the five clarifications (A–E). The proposal markers became settled wording; the decisions list became the settled choices; the unresolved list became accepted limitations.
  - `README.md`: the status wording says the same.
  - The threat model and ADR-0007 needed no change.
  - M3b–M3f remain unimplemented, Compose remains unverified, and overall M3 acceptance remains pending.
- **Checks run before the commit:**
  - the link check;
  - the consistency and private-content searches;
  - the author and committer identity check;
  - `git diff --cached --check`;
  - the staged Gitleaks scan.

  Exact results are in the session handoff. No application tests or builds were run.
- **After the commit:** the full-history Gitleaks scan and the commit verification are reported in the session handoff, not recorded here.
- **No worker code, tests, dependencies, migrations or workflow edits; no push, merge, amend, rebase, Docker or database contact.**

**Outcome note for Prompt 59 (added with Prompt 60; the commit happened after the Prompt 59 pre-commit note):**
- **Commit:** `f340b23cc03bfec53aad904398b40b931b653219` on `docs/m3b-worker-spec`, with parent `b3f9845`, subject `docs: accept M3b worker specification and record M3a main results`, and author and committer `257921624+mathewmljourney93@users.noreply.github.com`.
- **Checks:** the staged and full-history Gitleaks scans found no leaks (23 commits scanned).
- **Not published:** the branch was not pushed, and `main` stayed at `b3f9845`.

## Prompt 60: Implement M3b, the worker runtime and `eg-worker`

- **Stage:** Implementation, on branch `feat/worker-runtime` (staged for review, no commit)
- **Date:** 2026-10-12 (session date)

````text
Implement M3b: the worker runtime and eg-worker command, following the accepted specification. Leave the implementation staged and uncommitted for external review.

Follow CLAUDE.md. Work in:
D:\Claude\evidenceguard_agentic_rag

1. Verify starting state

Expected:
- Branch: docs/m3b-worker-spec
- HEAD:
  f340b23cc03bfec53aad904398b40b931b653219
- Parent:
  b3f984552bf22cf6350702330d30851f3e08b3f4
- Working tree clean, nothing untracked.
- Local main and origin/main:
  b3f984552bf22cf6350702330d30851f3e08b3f4
- Origin:
  https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git

Stop without changes if anything differs.

Create feat/worker-runtime from the current HEAD. If it already exists, stop and report its state rather than resetting or reusing it.

2. Read and implement the accepted specification

Read:
- CLAUDE.md
- The full accepted M3b section in docs/plan.md
- ADR-0001, ADR-0003 and ADR-0007
- Actual domain/persistence job interfaces
- Logging configuration, packaging configuration and relevant tests

Implement the accepted design without reopening settled decisions or adding unrelated functionality.

Scope:
- evidenceguard_worker under apps/worker/
- eg-worker console command
- Validated immutable handler registry
- JobContext and handler-facing fence
- Sequential worker supervisor
- Heartbeats using independent sessions
- Cooperative cancellation and irreversible lease-loss state
- Atomic finish and uncertain-commit handling
- Safe shutdown and abnormal-result handling
- Privacy-safe worker logging
- The additive claim kinds filter
- Accepted fixed JobErrorCode additions
- Packaging, import boundaries and focused tests
- ADR-0008 and truthful progress documentation

No ingestion handler, documents, revisions, chunks, uploads, new migrations, queue framework, Docker changes or new dependencies.

3. Preserve the reviewed lifecycle semantics

Pay particular attention to:

- No new claim while a previous handler or heartbeat thread remains alive.
- No Session shared between threads.
- State locks are never held across database I/O.
- Initial local deadline captured before claim; renewal deadlines captured before successful heartbeat calls.
- Cancellation cannot be cleared by a late heartbeat.
- Check actual thread termination after bounded joins.
- A stuck heartbeat means no runtime outcome and no subsequent claim.
- Cooperative lease loss produces no stale outcome.
- Uncooperative handlers produce abnormal shutdown, never another job.
- Atomic finish commits handler effects and success together.
- Publish committed state only after successful transaction exit.
- Coordinate pending heartbeat refusal with the finishing state.
- Committed finish followed by a handler exception never records another outcome.
- Uncertain commit acknowledgment does not establish whether commit succeeded.
- Recovery is fenced and durable effects remain idempotent.
- Post-claim shutdown starts no handler and attempts only the accepted fenced worker_shutdown retry.
- Synchronous claim/outcome calls have no promised total shutdown deadline.
- Engine disposal does not cancel checked-out connections.
- The CLI exits the process with code 5 after an abnormal runtime result; the reusable Python API returns the result.
- Empty production registry exits 4 before reading database settings.
- --help works without settings or a database.
- --once performs one claim attempt, exits 0 when no job is available and 1 on a claim database error.
- kinds=None preserves existing behavior; empty kinds selects nothing but still runs the global exhausted-job sweep; invalid kinds fail before SQL.

Keep the M3a lock, lease, attempt and retry defaults unchanged.

If a genuine implementation conflict requires changing the accepted contract, stop and report the concrete conflict instead of silently redesigning it.

4. Logging and privacy

Use the existing JSON logging configuration and reviewed fixed events.

Populate new log fields only from validated identifiers/enums.
Never log payloads, tenant IDs, idempotency keys, URLs, SQL, exception messages or tracebacks.

Retain the formatter’s existing protections for arbitrary messages and message arguments. CLI usage errors must not echo submitted values.

5. Tests and verification

Implement the accepted verification plan, including deterministic event-controlled tests for:
- Polling and backoff
- Kind filtering
- Delayed claims and shutdown during claim
- Heartbeat success, failures and conservative deadlines
- Blocked heartbeat beyond join deadline
- Cooperative and uncooperative lease loss
- Atomic finish, rollback and both uncertain-commit cases
- The database-commit/local-publication heartbeat race
- Late heartbeat after latched cancellation
- Shutdown drain, cancellation, second signal and cleanup
- No sessions crossing threads
- CLI errors, empty registry and abnormal subprocess exit
- Logging privacy and import boundaries

Add real PostgreSQL integration tests using the existing guarded disposable fixtures. Use bounded waits and test-only statement timeouts. Keep test handlers under tests; do not package or expose a production test-job command.

Do not start Docker or contact a local database. Integration tests remain pending authorized publication and CI.

Run:
- uv sync --locked
- uv run --locked ruff format --check .
- uv run --locked ruff check .
- uv run --locked mypy
- uv run --locked pytest
- uv build
- An isolated installed-wheel check outside the source tree:
  package imports, eg-worker --help, and empty-registry exit 4 without database settings
- git diff --cached --check
- Staged Gitleaks scan

The narrow CI change adding eg-worker --help to the installed-wheel step is already authorized. Preserve other workflow behavior and required-integration mode.

Report actual results and skipped integration counts. Do not claim PostgreSQL verification from unit tests.

6. Documentation and prompt history

Create ADR-0008 describing the implemented worker decisions and limits. Mark implementation under review and PostgreSQL verification pending.

Update relevant README, plan and threat-model wording truthfully:
- M3b implemented on its local branch, awaiting review and CI.
- No production handlers yet.
- Compose and overall M3 acceptance pending.
- M3c–M3f unimplemented.

Append this prompt verbatim as Prompt 60 if that is the next unused number; otherwise use the next unused number and explain it.
Add a truthful outcome note with actual checks, limitations and no commit/push/merge.

Preserve earlier prompt history.

7. Review handoff

Stage the complete implementation, excluding .local/ artifacts and generated build outputs.

Return:
- What changed and why.
- Any implementation choices within the accepted design.
- Actual commands and results, including failures corrected along the way.
- Staged tree ID, full staged-path list and Git status.
- COMPLETE staged diff excluding prompts.md, including all new source, tests, configuration and docs.
- Split the diff into numbered parts at file boundaries and provide every part. Never silently truncate or replace test/code diffs with summaries.
- If response limits prevent completion, identify precisely which files remain and preserve the full diff under .local/ for continuation.
- Summary of prompts.md additions.
- Remaining verification limits.

Leave all work staged and uncommitted.
Do not push, merge, amend, rebase, start Docker or contact a local database.
````

**Outcome (implementation pending review; staged on `feat/worker-runtime`, not committed or pushed):**
- **Starting state verified:**
  - branch `docs/m3b-worker-spec` at `f340b23` (parent `b3f9845`), a clean tree;
  - local `main` and `origin/main` at `b3f9845`, and the expected origin;
  - `feat/worker-runtime` did not exist locally or on the remote, and was created from `f340b23`.
- **Implemented**, following the accepted M3b specification (see ADR-0008):
  - the `evidenceguard_worker` package and the `eg-worker` command;
  - an immutable, validated handler registry, empty in production;
  - `JobContext` and `HandlerFence`;
  - the sequential supervisor and the heartbeat thread;
  - the shared attempt state: a `finishing` state, pending refusals, and irreversible lease loss and cancellation;
  - atomic finish and uncertain-commit handling;
  - the post-claim stop check, drain, cancellation and abnormal shutdown, with the CLI ending the process with `os._exit(5)`;
  - the reviewed log events and fields;
  - the additive `claim(..., kinds=...)` filter;
  - the three new `JobErrorCode` values;
  - packaging and import boundaries;
  - the authorized `eg-worker --help` line in the CI installed-wheel step;
  - ADR-0008 and status updates in the README, plan and threat model.
- **No** migrations, dependencies, lockfile changes, Docker changes, ingestion code or production handlers. The M3a lock, lease, attempt and retry defaults are unchanged.
- **Checks run locally (Windows):**
  - `uv sync --locked`;
  - `ruff format --check`, `ruff check` and `mypy` (75 source files): all clean;
  - `pytest`: 693 passed and 78 skipped. The skips are the 77 PostgreSQL integration tests (63 existing and 14 new) without `EG_TEST_DATABASE_URL`, plus the POSIX-only SIGTERM test;
  - `uv build`;
  - an isolated installed-wheel check outside the source tree: the imports resolve to `site-packages`, `eg-worker --help` exits 0, and `eg-worker` exits 4 without database settings.

  Exact results, and the staged diff and secret-scan checks, are in the session handoff.
- **Corrected along the way:**
  - a SQLite pool test switched from in-memory SQLite (a singleton pool) to a file database (`QueuePool`);
  - the CLI test fakes lacked `fenced`, which made the abnormal subprocess exit 1 and then hang on its deliberately non-daemon thread;
  - an empty-filter test also matched `FOR UPDATE` when looking for the `UPDATE` statement;
  - a weak packaging test was removed.
- **Not verified:**
  - the PostgreSQL integration tests have not run anywhere; they are pending authorized publication and CI;
  - Compose is unverified;
  - M3c–M3f are not implemented;
  - overall M3 acceptance is pending.
- **No commit, push or merge occurred.** No Docker or database was used.

**Review note for Prompt 60 (added with Prompt 61):**
- **Scope:** the external reviewer inspected the complete Prompt 60 staged diff.
- **Reproduced in isolation:** `JobContext.fenced` checked permission only before opening the fence. Cancellation latched while the fence was opening still let the handler body run. The reviewer did not run the project suite.
- **Further findings:**
  - job threads could be left running after an unexpected startup or supervisor exception;
  - a cleanup or flushing failure after an abnormal result could prevent `exit_process(5)`;
  - the uncertain-commit retry test used two different job IDs;
  - "bounded graceful shutdown" could be read as a total shutdown deadline.

## Prompt 61: Correct M3b cancellation and exception cleanup

- **Stage:** Correction, on branch `feat/worker-runtime` (staged for review, no commit)
- **Date:** 2026-10-12 (session date)

````text
Correct M3b cancellation and exception cleanup. Leave everything staged and uncommitted for review.

Follow CLAUDE.md. Work in:
D:\Claude\evidenceguard_agentic_rag

1. Verify starting state

Expected:
- Branch: feat/worker-runtime
- HEAD:
  f340b23cc03bfec53aad904398b40b931b653219
- Staged tree:
  92f5e613b2c138b852369f334a5f30d922a9ac45
- The same 25 staged paths reported for Prompt 60.
- Nothing unstaged or untracked.
- Expected origin for evidenceguard-agentic-rag.

Stop without changes if anything differs.
Record the pre-edit staged tree for the incremental review diff.

2. Cancellation during fence acquisition

Current JobContext.fenced calls check() before opening the database fence, then yields without checking again.

The reviewer reproduced this sequence in isolation:
- Initial check passes.
- Cancellation is latched while the fence opens.
- The handler body still executes despite cancel_requested=True.

Correct both ordinary and finish=True contexts:
- Retain the check before opening the fence.
- Recheck attempt permission after the fence has opened/acquired its lock, before yielding the HandlerFence.
- If cancellation or lease loss was latched during acquisition, raise and roll back without entering the handler body.
- Before recording atomic success after the handler block, recheck cancellation/lease-loss permission. Do not call the public check in a way that incorrectly rejects the legitimate FINISHING state.
- Preserve committed/uncertain finish semantics and pending-heartbeat-refusal coordination.
- Do not hold the attempt-state lock across database I/O.

This does not require interrupting statements already in flight. Document that cancellation checks occur at explicit boundaries and are not atomic with every SQL statement.

Add deterministic regression tests:
- Cancellation while an ordinary fence opens: no handler body/effect.
- Lease loss while a fence opens: no handler body/effect.
- Cancellation while a finish=True fence opens: no effect or completion.
- Cancellation during the finish block before success recording: rollback of effects and no atomic success.
- Existing committed-finish and heartbeat race tests remain intact.

Show that the relevant new tests fail against the previous implementation, then restore the corrected files and verify their identity.

3. Exception-safe job-thread lifecycle

Once any per-job thread has started, an unexpected supervisor or startup exception must not simply escape while leaving threads active.

Add an exception-safe lifecycle around per-job startup and supervision:
- Track which threads actually started.
- On an unexpected failure, latch cancellation, stop future heartbeats and perform bounded cleanup of started threads.
- Never join a thread that was not started.
- Never record an outcome or make another claim while a previous thread remains alive.
- If cleanup leaves any live job thread, return an abnormal result so the CLI takes the process-exit path.
- If all threads stopped, report the unexpected failure truthfully without claiming a successful job outcome.

Preserve the accepted limitation that synchronous database calls can block the supervisor; this correction does not promise a total shutdown deadline.

Add deterministic tests for:
- Heartbeat starts but handler-thread startup fails.
- An unexpected supervisor failure while a handler is running.
- Cooperative cleanup versus a thread that remains alive.
- No subsequent claim and no contradictory outcome.

4. Abnormal CLI exit must survive cleanup failures

Current main obtains an abnormal result inside the store context, but disposal or output flushing can raise before exit_process(5) is reached.

Once an abnormal result has been obtained:
- Cleanup and diagnostic-output failures must not downgrade it to an ordinary exit or prevent the required process termination.
- Ensure exit_process(5) is reached through exception-safe control flow even if store-context cleanup, signal restoration or output flushing fails.
- Keep diagnostics fixed and privacy-safe.
- Preserve injectable exit_process for in-process tests.
- Test actual termination in a bounded subprocess, including cleanup or flushing failure with a deliberately live thread.

Do not introduce a new logging service or shutdown framework.

5. Strengthen the uncertain-commit retry test

The existing “commit did not succeed ... stays idempotent” test creates two jobs with different IDs. That does not demonstrate retrying the same durable job.

Change the scenario to represent two attempts of the same job ID with matching tenant, kind and payload:
- First finish does not commit and leads to a fenced retry.
- Second attempt is a valid reclaim of that same job.
- Exactly one durable effect exists after successful completion.
- Token/attempt ownership is represented accurately.

Keep both uncertain-commit cases covered.

6. Documentation and verification

Update ADR-0008 and relevant documentation narrowly:
- Explicit cancellation-check boundaries.
- Exception-safe cleanup and abnormal-exit behavior.
- Still under review; PostgreSQL verification pending.
- Remove or qualify “bounded graceful shutdown” wording wherever it could imply a total process shutdown deadline.

No unrelated redesign, migrations, dependencies or Docker changes.

Run:
- uv run --locked ruff format --check .
- uv run --locked ruff check .
- uv run --locked mypy
- uv run --locked pytest
- uv build
- Isolated installed-wheel checks for imports, --help and empty-registry exit 4
- git diff --cached --check
- Staged Gitleaks scan

Do not start Docker or contact a local database.
Report PostgreSQL skips separately from platform skips.

7. History and handoff

Append this prompt verbatim as Prompt 61 if that is the next unused number; otherwise use the next unused number and explain it.

Record:
- The reviewer inspected the complete Prompt 60 diff.
- The reviewer reproduced the fence-acquisition cancellation issue in isolation, but did not run the project suite.
- The corrections, regression evidence and actual verification results.
- Earlier prompt entries remain unchanged.

Return:
- Explanation of the fixes.
- New-test results against the previous implementation.
- Actual final check results.
- New staged tree ID, staged paths and Git status.
- COMPLETE incremental diff against the recorded pre-edit staged tree, excluding prompts.md, including all changed tests and docs.
- Numbered fenced diff parts if necessary; never silently truncate.

Leave everything staged and uncommitted.
No push, merge, amend, rebase, Docker or local database contact.
````

**Outcome (corrections pending review; staged on `feat/worker-runtime`, not committed or pushed):**
- **Starting state verified:**
  - branch `feat/worker-runtime`, HEAD `f340b23`;
  - staged tree `92f5e61…` with the same 25 paths;
  - nothing unstaged or untracked, and the expected origin.

  The pre-edit staged tree was recorded.
- **Fence boundaries:** `JobContext.fenced` now checks permission:
  - before opening the fence;
  - again after the fence has acquired its lock, before the handler block;
  - with `finish=True`, again before recording `succeeded`.

  A failed check raises inside the transaction, which rolls back. `finishing` remains permitted. The checks are explicit boundaries, not atomic with every SQL statement.
- **Exception-safe job lifecycle:** the runtime tracks which job threads actually started. On an unexpected startup or supervisor failure it:
  - latches cancellation and stops future heartbeats;
  - joins only the started threads, each for a bounded time;
  - records no outcome;
  - returns an abnormal result if a thread is still alive, or otherwise re-raises the failure, so no further claim is made.
- **CLI:** once an abnormal result exists, failures in engine disposal, signal restoration or diagnostic output can no longer prevent or downgrade `exit_process(5)`. A cleanup failure after a normal stop is reported as an unexpected error (exit 1) instead of being hidden.
- **Tests:**
  - the uncertain-commit retry test now reclaims the same job ID (attempts 1 and 2), with exactly one durable effect;
  - the fake store's ownership is per attempt;
  - new regression tests cover:
    - fence-acquisition cancellation and lease loss;
    - finish cancellation;
    - handler-thread startup failure;
    - supervisor failure, cooperative and uncooperative;
    - the abnormal exit despite disposal, restoration or flush failures, in process and in a bounded subprocess with a live non-daemon thread;
    - a cleanup failure after a normal stop;
    - `finishing` permitted by `check()`.
- **Regression evidence:** the new and changed tests were run against the previous implementation files.
  - 13 failed and 4 passed. The 4 were the baseline subprocess case, the `finishing` check, the strengthened retry test, which is a test-only change, and the normal-stop cleanup report.
  - The previous CLI's subprocess cases hung until their 60 s timeout.
  - The corrected files were restored, and their SHA-256 hashes were verified identical.
- **Docs:** ADR-0008, the README, the plan status line and the threat model now describe the check boundaries, exception-safe cleanup and the abnormal exit. They qualify the shutdown wording as bounded supervisor waits, not a total shutdown deadline. The implementation is still under review, and PostgreSQL verification is pending.
- **Checks run locally (Windows):**
  - `ruff format --check`, `ruff check` and `mypy` (75 source files): clean;
  - `pytest`: 708 passed and 78 skipped. The skips are 77 PostgreSQL integration tests without `EG_TEST_DATABASE_URL`, plus 1 platform skip, the POSIX-only SIGTERM test;
  - `uv build`;
  - the isolated installed-wheel check: the imports, `--help` exiting 0, and an empty registry exiting 4.

  The staged diff check and the staged Gitleaks scan are reported in the session handoff.
- **Not verified:** the PostgreSQL integration tests have not run anywhere; Compose is unverified; M3c–M3f are not implemented; overall M3 acceptance is pending.
- **No commit, push or merge occurred.** No Docker or database was used.

**Acceptance note for Prompt 61 (added with Prompt 62):**
- **What was accepted:** the external reviewer accepted the complete Prompt 60 implementation plus the Prompt 61 corrections for a local commit.
- **What the acceptance rests on:**
  - the complete original and incremental diffs;
  - the reported Windows results: 708 passed and 78 skipped. The skips are 77 PostgreSQL integration tests and one POSIX-only SIGTERM test;
  - the reported format, lint, strict type-check, build, installed-wheel and secret-scan results;
  - the regression evidence: 13 failures against the previous implementation, then passing checks after the corrected files were restored.
- **What the reviewer ran:** they reproduced the original cancellation issue in isolation, but did not run the project suite or the corrected regression tests.
- **Still pending:** PostgreSQL verification, Linux, Compose and overall M3 acceptance.

## Prompt 62: Commit the reviewed M3b implementation locally

- **Stage:** Local commit only, on branch `feat/worker-runtime` (no push or merge)
- **Date:** 2026-10-12 (session date)

````text
Commit the reviewed M3b implementation locally. Do not push or merge.

Follow CLAUDE.md. Work in:
D:\Claude\evidenceguard_agentic_rag

1. Verify starting state

Expected:
- Branch: feat/worker-runtime
- HEAD:
  f340b23cc03bfec53aad904398b40b931b653219
- Staged tree:
  e0c69cd0461e3ee035b4441e71a5a612e44ca94a
- Exactly the same 25 staged paths reported in Prompt 61.
- Nothing unstaged or untracked.
- Origin:
  https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git
- Local main and origin/main:
  b3f984552bf22cf6350702330d30851f3e08b3f4

Stop without changes if anything differs.
Record the accepted staged tree before editing.

2. Preserve the reviewed implementation

The reviewer accepts the complete Prompt 60 implementation plus the Prompt 61 corrections for a local commit.

Acceptance rests on:
- The complete original and incremental diffs.
- Reported Windows results: 708 passed, 78 skipped.
- Reported format, lint, strict type-check, build, installed-wheel and secret-scan results.
- Regression evidence: 13 failures against the previous implementation, followed by passing checks after restoration.

The reviewer reproduced the original cancellation issue in isolation but did not run the project suite or corrected regression tests.

The 78 skips comprise:
- 77 PostgreSQL integration tests.
- One POSIX-only SIGTERM test.

PostgreSQL, Linux, Compose and overall M3 acceptance remain pending.

Every tracked file except prompts.md must remain byte-identical to the accepted staged tree. Do not alter code, tests, configuration or other documentation.

3. Prompt history

Change only prompts.md, append-only:
- Add an acceptance note under Prompt 61 with the evidence and limits above.
- Append this prompt verbatim as Prompt 62 if that is the next unused number; otherwise use the next unused number and explain it.
- Add a truthful pre-commit note recording the verified state, checks and local-only authorization.
- Keep earlier entries unchanged.
- Do not claim publication or CI verification.

4. Checks and local commit

Inspect Git status, staged paths and staged diff.
Confirm no .local/ files or generated build outputs are staged.
Check staged additions for secrets and private information.
Confirm effective author and committer email:
257921624+mathewmljourney93@users.noreply.github.com

Run:
- git diff --cached --check
- Staged Gitleaks scan

Create one LOCAL commit:
feat: add sequential worker runtime and safe lease cancellation

Use the existing attribution convention.

After committing:
- Run the full-history Gitleaks scan.
- Verify parent is f340b23cc03bfec53aad904398b40b931b653219.
- Verify the expected 25 committed paths.
- Verify all files except prompts.md match the accepted staged tree.
- Verify noreply identity and clean working tree.
- Confirm main remains unchanged.

Application checks need not be rerun because only prompt history changed since the reviewed verification.

5. Handoff

Return:
- Commit SHA, parent, subject and identity.
- Committed paths.
- Actual check results.
- Prompt-history additions and confirmation that earlier entries are unchanged.
- Final Git status.
- Complete incremental diff against the accepted staged tree, excluding prompts.md. If none, explicitly say none.
- Remaining verification limits.

Do not push, merge, amend, rebase, start Docker or contact a local database.
Do not begin M3c.
````

**Pre-commit note (written before the local commit):**
- **Starting state verified:**
  - branch `feat/worker-runtime`, HEAD `f340b23`;
  - staged tree `e0c69cd…` with the same 25 paths;
  - nothing unstaged or untracked;
  - the expected origin;
  - local `main` and `origin/main` at `b3f9845`.

  The accepted staged tree was recorded before editing.
- **Change:** only `prompts.md`, append-only: this acceptance note, this prompt and this pre-commit note. Every other tracked file stays byte-identical to the accepted tree.
- **Checks before the commit:**
  - the staged paths and diff inspected, with no `.local/` or build outputs staged;
  - the private-content check;
  - the author and committer identity check;
  - `git diff --cached --check`;
  - the staged Gitleaks scan.

  Exact results are in the session handoff. The application checks were not rerun, because only the prompt history changed since the reviewed verification.
- **Authorization:** local commit only. No push, merge, CI run or publication is claimed. The post-commit verification is reported in the session handoff.

**Outcome note for Prompt 62 (added with Prompt 63):**
- **Commit:** `6547e9f179720b876d7ae94fe8e7b2aefa866a03`, with parent `f340b23` and subject `feat: add sequential worker runtime and safe lease cancellation`, using the noreply identity.
- **Only `prompts.md` changed** relative to the accepted tree `e0c69cd…`.
- **Checks:** the staged and full-history Gitleaks scans found no leaks (24 commits scanned).
- **Not published:** the commit was not pushed.

## Prompt 63: Publish the reviewed M3b feature branch and verify CI

- **Stage:** Publication of `feat/worker-runtime` only (no change to `main`)
- **Date:** 2026-10-12 (session date)

````text
Publish the reviewed M3b feature branch and verify CI. This authorizes pushing only feat/worker-runtime. Do not update or merge main.

Follow CLAUDE.md. Work in:
D:\Claude\evidenceguard_agentic_rag

1. Verify starting state

Expected:
- Branch: feat/worker-runtime
- HEAD:
  6547e9f179720b876d7ae94fe8e7b2aefa866a03
- Parent:
  f340b23cc03bfec53aad904398b40b931b653219
- Working tree clean, nothing untracked.
- Origin:
  https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git
- No upstream configured.
- Local and remote main:
  b3f984552bf22cf6350702330d30851f3e08b3f4
- No remote feat/worker-runtime branch.
- Remote main is an ancestor of HEAD.
- Effective author and committer email:
  257921624+mathewmljourney93@users.noreply.github.com

Check remote refs freshly. Stop without changes if anything differs.

2. Publication preflight

Inspect all commits and tracked changes that will become public relative to remote main, including f340b23’s specification documentation.

Confirm:
- Noreply author and committer identities.
- No tracked .local/ files, backups, bundles, real environment files, credentials or generated build outputs.
- Changes match the reviewed specification and implementation.
- Both workflows trigger on this branch’s push.
- CI retains Ubuntu verification, Windows verification, PostgreSQL integration and full-history secret scanning.
- EG_REQUIRE_INTEGRATION=1 remains enabled.
- The only reviewed workflow change is eg-worker --help in the installed-wheel step.

Do not modify implementation or workflows. Stop and report any publication blocker.

3. Record authorization

Change only prompts.md, append-only:
- Append this prompt verbatim as Prompt 63 if it is the next unused number; otherwise use the next unused number and explain it.
- Add a truthful preflight note recording verified state, publication scope, checks and branch-only authorization.
- Clarify verification history:
  - The existing 63 PostgreSQL tests passed for M3a.
  - The 14 new worker integration tests have not run.
  - All 77 integration tests remain unverified against this M3b version.
  - Historical Windows results are 708 passed and 78 skipped: 77 PostgreSQL plus one POSIX-only SIGTERM test.
- Do not pre-record push or CI success.
- Keep earlier entries unchanged.

Stage only prompts.md.
Inspect its diff and private content.
Run git diff --cached --check and the staged Gitleaks scan.

Create one local commit:
docs: record M3b branch publication authorization

Use the noreply identity and existing attribution convention.
Verify it changes only prompts.md.
Run the full-history Gitleaks scan before pushing. Stop on failure.

No local application checks need rerunning for this history-only change.

4. Publish only the feature branch

Run:
git push --set-upstream origin refs/heads/feat/worker-runtime:refs/heads/feat/worker-runtime

Confirm the remote feature branch matches the exact published HEAD and main remains unchanged.

Do not push another branch or tag. Do not force-push.

5. Monitor CI for the exact published SHA

Wait for:
- Ubuntu verification
- Windows verification
- PostgreSQL integration
- Full-history secret scan

Use available read-only GitHub access. Do not install tooling or change authentication configuration.

Bound monitoring to 20 minutes. If a check fails or remains pending, report available diagnostics and links, then stop. Do not automatically edit, commit or repush fixes.

If logs are accessible, report actual pytest summaries:
- Integration is expected to collect 77 tests, but report the observed count.
- Ubuntu should also exercise the POSIX-only SIGTERM test.
- Windows retains its platform skip.

Do not present expected or historical counts as observed results for this SHA. If logs are inaccessible, report job/step conclusions and explicitly identify the missing test summaries.

6. Handoff

Return:
- Publication-history commit SHA and parent.
- Exact published SHA.
- Prompt-history additions.
- Preflight and scan results.
- Workflow/job links and conclusions for that SHA.
- Observed test summaries, or the log-access limitation.
- Final Git status and remote refs.
- Complete incremental diff outside prompts.md; if none, explicitly say none.

Main remains unchanged. Compose, overall M3 acceptance and M3c–M3f remain pending.

Do not merge, amend, rebase, delete branches, start Docker or contact a local database.
Do not begin M3c.
````

**Preflight note (written before the push; push and CI results are not recorded here):**
- **Verified state, from freshly fetched remote refs:**
  - branch `feat/worker-runtime` at `6547e9f`, with parent `f340b23`, a clean tree and no upstream;
  - origin as expected;
  - local and remote `main` at `b3f9845`, which is an ancestor of HEAD;
  - no remote `feat/worker-runtime`;
  - author and committer use the noreply address.
- **Publication scope (relative to remote `main`):**
  - commits `f340b23` (the accepted M3b specification and the M3a `main` results) and `6547e9f` (the reviewed M3b implementation);
  - this history commit.

  All of them carry noreply identities.
- **Preflight checks:**
  - no tracked `.local/`, backup, bundle, environment, credential or build-output files;
  - no private-content matches in the published additions;
  - the only workflow change is the reviewed `eg-worker --help` line in the installed-wheel step;
  - both workflows trigger on `push`;
  - CI keeps the Ubuntu and Windows verify jobs, the PostgreSQL integration job with `EG_REQUIRE_INTEGRATION=1`, and the full-history secret scan.
- **Verification history:**
  - The existing 63 PostgreSQL tests passed in CI for M3a.
  - The 14 new worker integration tests have never run.
  - All 77 integration tests are still unverified against this M3b version.
  - The historical local Windows result is 708 passed and 78 skipped: 77 PostgreSQL tests, plus one POSIX-only SIGTERM test.
- **Authorization:** push `feat/worker-runtime` only. No `main` update, merge, tag or force-push.

**Outcome note for Prompt 63 (added with Prompt 64; publication and CI happened after the Prompt 63 preflight note):**
- **Commit:** `bc5f6385ce092d1d47f69b4e8a6cd0a453e90451`, with parent `6547e9f`; it changes only `prompts.md`. The full-history Gitleaks scan was clean before the push.
- **Push:** only `feat/worker-runtime` was pushed, as a new branch tracking `origin/feat/worker-runtime`, at `bc5f638`. `main` stayed at `b3f9845`. Nothing was force-pushed and no tag was pushed.
- **CI:** for `bc5f638`, [CI run 38253962690](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38253962690) (verify on Ubuntu and Windows, plus integration) and [secret-scan run 38253962775](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38253962775) succeeded within the 20-minute monitoring bound.
- **Logs:** Claude saw only job and step conclusions; the unauthenticated log endpoint returned 403.

## Prompt 64: Record the verified M3b feature-branch CI results

- **Stage:** Documentation only, on branch `feat/worker-runtime` (staged for review, no commit)
- **Date:** 2026-10-12 (session date)

````text
Record the verified M3b feature-branch CI results. Documentation only; leave changes staged and uncommitted for review.

Follow CLAUDE.md. Work in:
D:\Claude\evidenceguard_agentic_rag

1. Verify starting state

Expected:
- Branch: feat/worker-runtime
- HEAD and upstream:
  bc5f6385ce092d1d47f69b4e8a6cd0a453e90451
- Working tree clean, nothing untracked.
- Origin:
  https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git
- Local and remote main:
  b3f984552bf22cf6350702330d30851f3e08b3f4

Check remote refs freshly. Stop without changes if anything differs.

2. Independently retrieved CI evidence

The reviewer retrieved the logs directly from GitHub.

CI run:
https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38253962690

Observed summaries:
- Ubuntu job 114827089007:
  709 passed, 77 skipped in 15.96s
- Windows job 114827088937:
  708 passed, 78 skipped in 22.18s
- PostgreSQL integration job 114827089078:
  77 passed, 709 deselected in 19.63s

Secret-scan run:
https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38253962775

Job 114827088806:
25 commits scanned; no leaks found.

Both runs:
- head_sha: bc5f6385ce092d1d47f69b4e8a6cd0a453e90451
- head_branch: feat/worker-runtime
- conclusion: success

All 77 PostgreSQL tests passed: 63 existing plus 14 worker integration tests.
Ubuntu’s database-independent run has one additional passing test compared with Windows, consistent with the POSIX-only SIGTERM test running on Ubuntu and being skipped on Windows. Do not claim an individually named test log entry was observed.

The reviewer retrieved CI evidence but did not run the project suite locally.

3. Narrow documentation updates

Update only:
- README.md
- docs/decisions/0008-worker-runtime.md
- docs/plan.md
- docs/threat-model.md
- prompts.md

Record:
- M3b implementation is reviewed and verified in CI on feat/worker-runtime at bc5f638.
- Actual summaries and links above.
- PostgreSQL verification now includes the worker tests.
- Linux verification has run.
- M3b is not yet merged into main.
- Production handler registry remains empty.
- Compose remains unverified.
- M3c–M3f remain unimplemented.
- Overall M3 acceptance remains pending.
- Existing accepted runtime limitations remain unchanged.

Mark ADR-0008 accepted, following the repository’s accepted-and-CI-verified ADR convention.

Preserve historical evidence and distinguish tested behavior from general security or performance guarantees.

Do not change source, tests, dependencies, migrations, workflows or engineering defaults.

4. Prompt history

Append this prompt verbatim as Prompt 64 if it is the next unused number; otherwise use the next unused number and explain it.

Add a truthful outcome note covering:
- Reviewer-retrieved evidence.
- Documentation changes.
- Checks actually run.
- No commit, push or merge.
- Main remains unchanged.

Keep earlier entries unchanged.

5. Checks and handoff

Check documentation links, status consistency and private content.
Run:
- git diff --cached --check
- Staged Gitleaks scan

No application tests or builds are needed for documentation-only changes.

Stage only the five authorized files.

Return:
- Concise explanation of changes.
- Actual check commands and results.
- Staged tree ID, staged paths and Git status.
- COMPLETE staged diff excluding prompts.md, including all changed documents, directly in fenced diff blocks.
- Numbered parts at file boundaries if necessary; never silently truncate.
- Summary of prompts.md additions and confirmation earlier entries are unchanged.

Leave everything staged and uncommitted.
Do not push, merge, amend, rebase, start Docker or contact a local database.
Do not begin M3c.
````

**Outcome (documentation pending review; staged on `feat/worker-runtime`, not committed or pushed):**
- **Starting state verified, from freshly fetched remote refs:**
  - branch `feat/worker-runtime`, with HEAD and upstream at `bc5f638`;
  - a clean tree and the expected origin;
  - local and remote `main` at `b3f9845`.
- **Evidence:** the external reviewer retrieved these from GitHub; they did not run the project suite locally.
  - Ubuntu: `709 passed, 77 skipped in 15.96s`.
  - Windows: `708 passed, 78 skipped in 22.18s`.
  - PostgreSQL: `77 passed, 709 deselected in 19.63s`. That is all 77 integration tests: the 63 existing and the 14 worker tests.
  - Secret scan: 25 commits scanned, no leaks.

  Ubuntu's one extra passing test is consistent with the POSIX-only SIGTERM test; no individual log entry for it was observed.
- **Documentation changes:**
  - **ADR-0008:** marked accepted, following the ADR-0007 convention.
  - **README, plan and threat model:** now say M3b is reviewed and verified in CI on `feat/worker-runtime` at `bc5f638`, and that the PostgreSQL verification includes the worker tests. They also say:
    - M3b is not merged into `main`;
    - the production registry is empty;
    - Compose is unverified;
    - M3c–M3f are not implemented;
    - M3 acceptance is pending.

  Historical evidence and the runtime limitations are unchanged. No source, tests, dependencies, migrations, workflows or defaults changed.
- **Checks run:**
  - the link and anchor check;
  - a status-consistency search;
  - a private-content check of the staged additions;
  - `git diff --cached --check`;
  - the staged Gitleaks scan.

  Exact results are in the session handoff. No application tests or builds were run.
- **No commit, push or merge occurred.** `main` is unchanged at `b3f9845`.

**Acceptance note for Prompt 64 (added with Prompt 65):**
- **What was accepted:** the external reviewer accepted Prompt 64's complete documentation diff.
- **Basis:** that diff and the GitHub evidence they retrieved independently for `bc5f638`:
  - Ubuntu: `709 passed, 77 skipped in 15.96s`;
  - Windows: `708 passed, 78 skipped in 22.18s`;
  - PostgreSQL: `77 passed, 709 deselected in 19.63s`;
  - secret scan: 25 commits scanned, no leaks.
- **What the reviewer ran:** nothing locally; they did not run the project suite.
- **Unchanged documents:** the four non-history documents stay byte-identical to the accepted tree `108db3b…`. Their "not yet merged" statements are true before publication.

## Prompt 65: Commit the M3b verification documentation, publish the branch, then fast-forward main

- **Stage:** Commit, publish `feat/worker-runtime`, then fast-forward `main` after all four checks pass
- **Date:** 2026-10-12 (session date)

````text
Commit the reviewed M3b verification documentation, publish the feature branch, then fast-forward main only after all four required checks pass.

Follow CLAUDE.md. Work in:
D:\Claude\evidenceguard_agentic_rag

1. Verify starting state

Expected:
- Branch: feat/worker-runtime
- HEAD and upstream:
  bc5f6385ce092d1d47f69b4e8a6cd0a453e90451
- Staged tree:
  108db3baf56986276b6e7b5449082590be9ca941
- Exactly five staged files:
  README.md
  docs/decisions/0008-worker-runtime.md
  docs/plan.md
  docs/threat-model.md
  prompts.md
- Nothing unstaged or untracked.
- Origin:
  https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git
- Local and remote main:
  b3f984552bf22cf6350702330d30851f3e08b3f4
- Remote feature branch matches HEAD.
- Main is an ancestor of HEAD.
- Effective author and committer email:
  257921624+mathewmljourney93@users.noreply.github.com

Check remote refs freshly. Stop without changes if anything differs.
Record the accepted staged tree before editing.

2. Preserve the reviewed documents

The reviewer accepted Prompt 64’s complete documentation diff, based on that diff and independently retrieved GitHub evidence for bc5f638:
- Ubuntu: 709 passed, 77 skipped in 15.96s
- Windows: 708 passed, 78 skipped in 22.18s
- PostgreSQL: 77 passed, 709 deselected in 19.63s
- Secret scan: 25 commits scanned, no leaks

The reviewer did not run the project suite locally.

Keep all four non-history documents byte-identical to the accepted tree. Their “not yet merged” statements are true before publication; do not pre-record future results.

Change only prompts.md, append-only:
- Add an acceptance note under Prompt 64.
- Append this prompt verbatim as Prompt 65 if that is the next unused number; otherwise use the next unused number and explain it.
- Add a truthful preflight note recording verified state, checks, authorization order and stop conditions.
- Do not pre-record push, CI or main-update success.
- Keep earlier entries unchanged.

3. Commit and scan

Inspect staged paths, diff, private content and effective identity.
Run git diff --cached --check and the staged Gitleaks scan.

Create one commit:
docs: record verified M3b results and main publication authorization

Use the noreply identity and existing attribution convention.

Verify:
- Parent is bc5f6385ce092d1d47f69b4e8a6cd0a453e90451.
- Exactly the five authorized files changed.
- All files except prompts.md match the accepted staged tree.
- Working tree is clean.

Run the full-history Gitleaks scan before publication. Stop on failure.
No local application tests or builds need rerunning for documentation-only changes.

4. Publish the feature branch first

Push only:
git push origin refs/heads/feat/worker-runtime:refs/heads/feat/worker-runtime

Monitor all four checks for the exact new SHA:
- Ubuntu verification
- Windows verification
- PostgreSQL integration
- Full-history secret scan

Use available read-only GitHub access. Do not install tooling or change authentication configuration.

Bound monitoring to 20 minutes. If anything fails or remains pending, report diagnostics and links, then stop before touching main. Do not automatically fix or repush.

Report actual test summaries if logs are accessible. Otherwise say counts were not observed; do not reuse bc5f638’s summaries as observed results for the new SHA.

5. Fast-forward main after all four checks pass

Fetch main and the feature branch again. Confirm:
- Remote main remains b3f984552bf22cf6350702330d30851f3e08b3f4.
- Remote feature branch matches the newly verified SHA.
- Main is an ancestor of that SHA.
- Local main equals origin/main and has no independent commits.
- Working tree is clean.

Stop if any condition differs.

Switch to main, then fast-forward to the verified SHA with git merge --ff-only. Create no merge commit.

Push only:
git push origin refs/heads/main:refs/heads/main

Monitor all four checks for that exact SHA’s main-push runs, again bounded to 20 minutes.

If a main check fails or remains pending, report it accurately. Do not automatically revert, rewrite history or make fixes.

6. Handoff

Return:
- Commit SHA, parent, subject and identity.
- Prompt-history additions.
- Checks and scan results.
- Feature and main workflow/job links and conclusions.
- Observed test summaries, or log-access limitations.
- Before/after refs and final Git status.
- Complete incremental diff against the accepted staged tree, excluding prompts.md. If none, explicitly say none.
- Note that recording the eventual main publication results requires a later documentation update.

Compose remains unverified. No production handlers exist yet. M3c–M3f and overall M3 acceptance remain pending.

Do not change application code, tests, dependencies, migrations or workflows.
Do not force-push, amend, rebase, squash, delete branches or push tags.
Do not start Docker or contact a local database.
Do not begin M3c.
````

**Preflight note (written before the commit; push, CI and `main` results are not recorded here):**
- **Verified state, from freshly fetched remote refs:**
  - branch `feat/worker-runtime`, with HEAD, upstream and the remote feature branch all at `bc5f638`;
  - staged tree `108db3b…` with exactly the five authorized files, and nothing unstaged or untracked;
  - the expected origin;
  - local and remote `main` at `b3f9845`, which is an ancestor of HEAD;
  - author and committer use the noreply address.

  The accepted staged tree was recorded before editing.
- **Change:** only `prompts.md`, append-only.
- **Checks before the commit:**
  - the staged paths, diff, private content and identity inspected;
  - `git diff --cached --check`;
  - the staged Gitleaks scan.

  After the commit, and before any push, the full-history Gitleaks scan runs.
- **Authorization order:**
  1. Commit.
  2. Push only `feat/worker-runtime`.
  3. Monitor the four required checks (Ubuntu and Windows verification, PostgreSQL integration, full-history secret scan) for the exact new SHA, for at most 20 minutes.
  4. Only if all four pass, re-fetch and confirm:
     - remote `main` is still `b3f9845`;
     - the remote feature branch equals the verified SHA;
     - `main` is an ancestor of it;
     - local `main` equals `origin/main`;
     - the tree is clean.
  5. Fast-forward `main` with `git merge --ff-only`.
  6. Push only `main`.
  7. Monitor its four checks for at most 20 minutes.
- **Stop conditions:**
  - any failed or pending check, or any differing ref, stops the run before `main` is touched;
  - a failure after `main` is pushed is reported, never reverted or rewritten.

  There is no force-push, amend, rebase, squash, branch deletion or tag push.
