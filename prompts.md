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
