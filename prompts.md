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
