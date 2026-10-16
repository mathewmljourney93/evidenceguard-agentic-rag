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

**Outcome note for Prompt 65 (added with Prompt 66; publication and CI happened after the Prompt 65 preflight note):**
- **Commit:** `dd26c7099d1007e9ee615204dc0056abe8820c67`, with parent `bc5f638`, using the noreply identity. Only `prompts.md` differed from the accepted tree `108db3b…`, and the full-history Gitleaks scan was clean before any push.
- **Feature push:** `feat/worker-runtime` moved from `bc5f638` to `dd26c70`.
  - [CI run 38255538870](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38255538870) succeeded: Ubuntu, Windows and integration.
  - [Secret-scan run 38255538708](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38255538708) succeeded.
- **Fast-forward of `main`:** after all four checks passed and a fresh fetch confirmed the preconditions, `main` was fast-forwarded with `git merge --ff-only` and pushed from `b3f9845` to `dd26c70`. No merge commit, force-push or tag push was made.
- **`main` CI for exactly `dd26c70`:**
  - [CI run 38255786860](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38255786860) and [secret-scan run 38255786973](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38255786973) succeeded.
  - From logs retrieved independently by the external reviewer:
    - Ubuntu `709 passed, 77 skipped in 18.16s`;
    - Windows `708 passed, 78 skipped in 21.20s`;
    - PostgreSQL `77 passed, 709 deselected in 17.36s`;
    - secret scan: 26 commits scanned, no leaks found.
  - Claude saw only job conclusions; the unauthenticated log endpoint returned 403.

## Prompt 66: Record M3b on main and propose the M3c specification

- **Stage:** Documentation only, on branch `docs/m3c-revision-spec` (staged for review, no commit)
- **Date:** 2026-10-12 (session date)

````text
Record M3b’s verified main publication and prepare the detailed M3c specification for review. Documentation only; do not implement M3c yet.

Follow CLAUDE.md. Work in:
D:\Claude\evidenceguard_agentic_rag

1. Verify starting state

Expected:
- Branch: main
- HEAD and origin/main:
  dd26c7099d1007e9ee615204dc0056abe8820c67
- Working tree clean, nothing untracked.
- Origin:
  https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git

Check remote refs freshly. Stop without changes if anything differs.

Create docs/m3c-revision-spec from HEAD.
If that branch already exists, stop and report its state rather than resetting or reusing it.

2. Read the accepted design and actual interfaces

Read:
- CLAUDE.md
- Relevant plan sections covering documents, revisions, ingestion, tenant constraints and the M3 sequence
- ADR-0003, ADR-0004, ADR-0007 and ADR-0008
- Existing persistence models, migrations, transaction helpers and job fence
- Implemented worker context, atomic finish and cancellation behavior
- Relevant integration fixtures and migration/readiness tests

Build on the existing architecture and interfaces. Do not introduce a new storage service, queue or framework.

3. Record M3b on main

Narrowly update README.md, ADR-0008, docs/plan.md and docs/threat-model.md:
- M3b was fast-forwarded onto main at dd26c70.
- All four main-push checks passed for that exact SHA.
- Preserve bc5f638’s earlier evidence as historical evidence.
- No production handlers exist yet.
- Compose remains unverified.
- M3c–M3f remain unimplemented and overall M3 acceptance is pending.

The reviewer independently retrieved these logs:

CI run:
https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38255786860

- Ubuntu job 114833375464:
  709 passed, 77 skipped in 18.16s
- Windows job 114833375444:
  708 passed, 78 skipped in 21.20s
- PostgreSQL job 114833375219:
  77 passed, 709 deselected in 17.36s

Secret-scan run:
https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38255786973

- Job 114833375056:
  26 commits scanned; no leaks found.

Both runs:
- head_sha: dd26c7099d1007e9ee615204dc0056abe8820c67
- head_branch: main
- conclusion: success

The reviewer retrieved GitHub evidence but did not run the project suite locally.

4. Detailed M3c specification in docs/plan.md

Mark the specification Proposed, awaiting review.

Scope:
- documents and document_revisions tables in migration 0003
- Pure revision lifecycle rules
- Tenant-scoped persistence operations
- Revision-number allocation
- Fenced transactional activation and supersession
- Tests and documentation

Parsing, chunking, the ingestion handler, uploads and document endpoints belong to later slices. Do not pull them into M3c.

Define concretely:

A. Schema and ownership
- Exact fields, types, nullability, defaults, uniqueness, indexes and named constraints.
- Relationships to tenants and vendors.
- Composite tenant constraints for tenant-scoped references.
- How active_revision_id can refer only to a revision belonging to that same tenant and document.
- Equivalent ownership constraints for superseded_by_revision_id.
- Migration ordering for circular document/revision references.
- What the database enforces versus what trusted application transitions enforce.
- Source-content storage and content-hash requirements from the existing plan, including privacy limits; do not invent an external storage service.

B. Pure lifecycle
- pending, processing, failed, active and superseded.
- Allowed transitions and invalid transitions.
- Idempotency and conflicting retries.
- Which fields are immutable.
- Timezone-aware timestamps and safe fixed failure codes.
- Retry of processing under a newly claimed job attempt.
- Distinguish retryable job failure from a revision that is permanently failed.
- A failed replacement must leave the prior active revision unchanged.

C. Revision creation
- Document identity and tenant-scoped lookup behavior.
- Concurrent revision-number allocation without duplicates.
- Same-document identical-content behavior consistent with the accepted upload design.
- How metadata differences on duplicate content are handled.
- The transaction boundary available to M3e for creating a revision and its ingestion job atomically.
- Keep authorization and tenant scope explicit without adding endpoints.

D. Activation and locking
- Use the existing job fence and worker atomic-finish contract.
- Verify the job tenant and revision/document binding from trusted persisted data.
- Exact lock order across job, document and revision rows.
- No reuse of time or ownership checks captured before a lock wait.
- Bounded lock waits consistent with the existing design.
- Concurrent activation by two different revision jobs for one document.
- When a newer revision becomes active, supersede the previous active revision and update the pointer in one transaction.
- If an older revision completes after a newer one is active, it becomes superseded without changing the active pointer.
- Clarify whether ordering is relative to the active revision or merely the newest uploaded/pending revision; preserve the accepted plan.
- Duplicate activation, supersession links and timestamps.
- Rollback when activation or final job completion fails.
- A stale worker cannot activate a revision.
- No provider calls or parsing while activation locks are held.

E. Future handler seam
- Describe how M3d will persist chunks and activate a revision through the fence, with final job success atomic where required.
- Define whether M3c functions accept the existing handler-facing FencedSession or another existing transaction interface.
- Avoid allowing a persistence function to commit the caller’s transaction.
- M3c adds no production worker handler.

F. Verification
Provide a proposed file list and focused tests:
- Pure lifecycle and immutable model tests.
- Database-independent persistence tests where useful.
- Real PostgreSQL constraint and migration round-trip tests.
- Concurrent revision allocation and duplicate-content creation.
- Failed replacement preserves prior active revision.
- Two revisions finishing out of order leave only the newer active.
- Concurrent activations maintain one consistent active pointer.
- Crash/failure during activation rolls back all changes.
- Stale job attempt refuses activation.
- Cross-tenant and cross-document references are rejected.
- Installed-wheel migration checks and readiness expectations.

Use event-controlled concurrency, bounded waits and guarded disposable fixtures. PostgreSQL verification remains pending future authorized publication.

Identify genuine new decisions as proposals and explain conflicts with existing accepted decisions. Resolve routine choices yourself; do not leave a broad questionnaire.

Do not write application code, migrations, tests or ADR-0009 yet.

5. Prompt history

Append this prompt verbatim as Prompt 66 if it is the next unused number; otherwise use the next unused number and explain it.

Add truthful notes recording:
- M3b publication and reviewer-retrieved main CI evidence.
- M3c specification is proposed, not accepted or implemented.
- Checks actually run.
- No commit, push or merge.

Keep earlier entries unchanged.

6. Checks and handoff

Stage only:
- README.md
- docs/decisions/0008-worker-runtime.md
- docs/plan.md
- docs/threat-model.md
- prompts.md

Check links, consistency and private content.
Run git diff --cached --check and the staged Gitleaks scan.
No application tests or builds are needed.

Return:
- Concise explanation of the M3c design.
- New proposed decisions and genuine unresolved conflicts.
- Actual check results.
- Staged tree ID, paths and Git status.
- COMPLETE staged diff excluding prompts.md in fenced diff blocks.
- Numbered parts at file boundaries if needed; never silently truncate.
- Summary of prompt-history additions.

Leave changes staged and uncommitted for review.
Do not push, merge, amend, rebase, start Docker or contact a local database.
````

**Outcome (documentation pending review; staged on `docs/m3c-revision-spec`, not committed or pushed):**
- **Starting state verified:**
  - branch `main`, with HEAD and `origin/main` at `dd26c70` (remote refs read freshly);
  - a clean tree and the expected origin.
  - Branch `docs/m3c-revision-spec` did not exist locally or on the remote, and was created from `dd26c70`.
- **M3b publication recorded** in the README, ADR-0008, the plan and the threat model:
  - M3b on `main` at `dd26c70`, with all four `main`-push checks passing;
  - the counts from the reviewer's independently retrieved logs.
  - The README's verified baseline moved to `dd26c70`, and the `bc5f638` and `b3f9845` evidence is kept as historical evidence.
  - There are no production handlers; Compose is unverified; M3c–M3f are not implemented; overall M3 acceptance is pending.
- **M3c specification:** added to `docs/plan.md` and marked **PROPOSED, awaiting review**. It is neither accepted nor implemented. It covers:
  - the schema, ownership and migration order;
  - the pure lifecycle;
  - revision creation;
  - activation and locking;
  - the M3d handler seam;
  - the verification plan;
  - seven decisions requested at review and one unresolved item.

  No code, migrations, tests, ADR-0009, dependencies or workflows changed.
- **Checks run:**
  - the link and anchor check;
  - a status-consistency search;
  - a private-content check of the staged additions;
  - `git diff --cached --check`;
  - the staged Gitleaks scan.

  Exact results are in the session handoff. No application tests or builds were run.
- **No commit, push or merge occurred.** `main` is unchanged at `dd26c70`.

**Review note for Prompt 66 (added with Prompt 67):**
- **Accepted:** the M3b publication documentation and the broad M3c schema and lifecycle approach.
- **Corrections requested to the M3c proposal:**
  - fresh lease checks after M3c's additional lock waits;
  - an explicit activation order for the immediate one-active index;
  - honest commit-failure semantics;
  - a correct permanent-failure seam, since raising inside a fenced block rolls back `fail_revision`;
  - a narrowly settled exhausted-job limitation;
  - per-field state checks;
  - `RevisionContent` consistency validated in M3c.
- **Status:** M3c remains proposed.

## Prompt 67: Correct the proposed M3c specification

- **Stage:** Documentation only, on branch `docs/m3c-revision-spec` (staged for review, no commit)
- **Date:** 2026-10-12 (session date)

````text
Correct the proposed M3c specification. Documentation only; leave changes staged and uncommitted.

Follow CLAUDE.md. Work in:
D:\Claude\evidenceguard_agentic_rag

Expected starting state:
- Branch: docs/m3c-revision-spec
- HEAD:
  dd26c7099d1007e9ee615204dc0056abe8820c67
- Staged tree:
  929800be9f0a87c8f888fb83771401ce3f3ed64f
- Exactly five staged files:
  README.md
  docs/decisions/0008-worker-runtime.md
  docs/plan.md
  docs/threat-model.md
  prompts.md
- Nothing unstaged or untracked.
- Expected origin for evidenceguard-agentic-rag.

Stop without changes if anything differs.
Record the pre-edit staged tree.

The reviewer accepts the M3b publication documentation and the broad M3c schema/lifecycle approach. M3c remains proposed pending review of these corrections.

1. Fresh lease checks after additional lock waits

The fence checks ownership before M3c acquires document and revision locks. Its JobSnapshot and earlier time cannot establish that the lease remains valid after those waits.

Specify for start_processing, fail_revision and activate_revision:
- Acquire locks in the accepted order.
- Re-read required mutable data after locks.
- Read the currently locked job state and fresh clock_timestamp().
- Revalidate tenant, token ownership, running status and unexpired lease immediately before applying revision effects.
- Raise the existing fixed LeaseLostError and change nothing if the check fails.
- Do not use the earlier JobSnapshot's timestamp as the current database time.

Explain how this is implemented through the existing FencedSession and pure job rules without changing transaction ownership or exposing lifecycle transitions to handlers.

Preserve M3a's accepted limit: a valid fenced transaction may commit shortly after expiry. Do not promise continuous lease validation during every statement.

Add a planned real PostgreSQL test:
- The worker holds its job fence.
- It waits on a document lock.
- The lease expires during that wait, within the lock-timeout bound.
- The lock is released.
- Activation is refused and revision states, active pointer and job outcome remain unchanged.

2. Explicit activation statement order

The partial unique index enforcing one active revision is immediate.

Specify:
- Demote the old active revision first.
- Then promote the new revision.
- Then update the document pointer.
- All occur in one transaction under the document lock.
- The temporary intermediate state is not published as a committed state.

For an older revision finishing late, leave the active revision and pointer unchanged and mark only the target superseded.

Duplicate activation must change no timestamps, links or document updated_at.

Add an integration test proving the successful replacement path works with the actual partial unique index, and rollback restores the previous active state after a failure between demotion and promotion.

3. Honest commit-failure semantics

Replace the statement that any commit exception necessarily rolls back everything.

Distinguish:
- A failure before commit rolls back the activation changes and job success together.
- A successfully committed transaction persists both together.
- If commit acknowledgment fails, the outcome may be unknown; either both committed or neither did.
- Recovery uses existing worker uncertain-finish behavior and idempotent revision transitions.
- Never claim a previous state is intact solely because commit raised.

Add planned coverage for both uncertain-commit cases, using controlled doubles where necessary. Keep real PostgreSQL rollback tests separate from simulated acknowledgment failure.

4. Permanent failure and exhausted jobs

The proposed “mark failed and raise a permanent error in one fenced transaction” is incorrect: raising inside the block rolls back fail_revision.

Correct the future M3d seam:
- Do not raise inside a fenced block intended to persist failure.
- With existing M3b interfaces, commit fail_revision in its fenced transaction, then raise PermanentJobError outside that block.
- The supervisor records the job failure in a separate fenced transaction.
- Explicitly document the gap between those commits.
- Define recovery if the worker crashes in that gap: a handler must recognize an already-failed revision and request permanent job failure without trying to start processing or perform ingestion again.
- Do not claim atomic revision failure and job failure with the current interface.
- Any future atomic-failure interface extension requires separate review.

Settle the exhausted-job limitation narrowly:
- A job can become dead while its revision remains pending or processing, including abandonment before start_processing.
- M3c does not introduce reconciliation.
- Record reconciliation or a truthful stalled/dead projection as a required M3d/M3e design item before overall M3 acceptance.
- The previous active revision remains unaffected.

5. Schema and input precision

Clarify the state checks so partial field pairs cannot pass:
- failure_reason and failed_at must each be non-null exactly for failed, and null otherwise.
- superseded_at and superseded_by_revision_id must each be non-null exactly for superseded, and null otherwise.
- failed, pending and processing have no activated_at.
- superseded may retain activated_at.
- Name each proposed constraint explicitly.

RevisionContent should validate consistency now, before persistence:
- Accept strict UTF-8 source bytes or derive validated hash/size from their exact encoding.
- sha256, byte_size and content_text must correspond to the same bytes.
- No normalization before hashing.
- Reject NUL content, which PostgreSQL text cannot store.
- Keep upload size/media HTTP response mapping in M3e.
- Validation errors and repr must not expose submitted content.

Do not defer consistency of caller-supplied content/hash/size to future endpoints.

6. Scope and handoff

Change only docs/plan.md and prompts.md unless another staged document directly contradicts a correction; explain any necessary additional edit.

Keep the other reasonable proposals:
- Composite tenant/document pointer constraints.
- Allocation counter under the document lock.
- No triggers.
- Metadata conflicts rather than silent updates.
- Identical failed content returns the existing revision.
- Domain module named revisions.
- chunker_version introduced with M3d.

Append this prompt verbatim as Prompt 67 if it is the next unused number; otherwise use the next unused number and explain it.
Record the review and corrections truthfully. Earlier entries remain unchanged.

Check links, consistency and private content.
Run git diff --cached --check and the staged Gitleaks scan.
No application tests or builds are needed.

Return:
- Explanation of the corrections and remaining design choices.
- Actual check results.
- New staged tree ID, paths and Git status.
- COMPLETE incremental diff against the recorded pre-edit staged tree, excluding prompts.md.
- Prompt-history additions.

Leave changes staged and uncommitted.
No code, migrations, tests, dependencies, workflow edits, push, merge, Docker or database contact.
````

**Outcome (corrections pending review; staged, not committed or pushed):**
- **Starting state verified:**
  - branch `docs/m3c-revision-spec`, HEAD `dd26c70`;
  - staged tree `929800b…` with exactly the five expected files;
  - nothing unstaged or untracked, and the expected origin.

  The pre-edit staged tree was recorded.
- **Only `docs/plan.md` changed,** besides this file. No other staged document contradicted the corrections. The M3c section stays **PROPOSED** and now specifies:
  - **Ownership re-check:** after the document and revision locks, the locked job row and a fresh `clock_timestamp()` are re-read through the same `FencedSession`, M3a's `holds_lease` is applied, and the fixed `LeaseLostError` is raised before any write.
    - That fresh time is used for the effects.
    - It is proposed as a read-only `recheck_ownership` helper, which adds no transition and leaves transaction ownership unchanged.
    - M3a's commit-shortly-after-expiry limit is kept.
  - **Activation order:** demote, then promote, then the pointer. A late older revision writes only its own row; a duplicate writes nothing.
  - **Commit semantics:** distinguished before the commit, after it, and with an unknown acknowledgment.
  - **Permanent failure:** commit `fail_revision` without raising, then raise `PermanentJobError` outside the block. The non-atomic gap and its crash recovery are documented.
  - **Dead jobs:** a job left dead with its revision unsettled is recorded as a required M3d/M3e design item before overall M3 acceptance.
  - **State checks:** per-field and named.
  - **`RevisionContent`:** built from the exact bytes, with strict UTF-8, no NUL and no normalization, and fixed errors.
  - **Tests:** the matching planned tests, including the lease expiring during the document-lock wait, the real partial index with a failure between demotion and promotion, and uncertain commits using controlled doubles.

  The other proposals are kept.
- **Checks run:**
  - the link and anchor check;
  - a consistency search for the superseded statements;
  - a private-content check of the staged additions;
  - `git diff --cached --check`;
  - the staged Gitleaks scan.

  Exact results are in the session handoff. No application tests or builds were run.
- **No commit, push or merge occurred.** `main` is unchanged at `dd26c70`.

**Acceptance note for Prompt 67 (added with Prompt 68):**
- **What was reviewed:** the external reviewer inspected the complete Prompt 66 documentation diff and the Prompt 67 corrections. They did not run application checks.
- **Accepted:** the corrected M3c specification and its decisions:
  - **Schema:** composite tenant and document ownership constraints, the one-active partial unique index, the allocation counter under the document lock, and no triggers.
  - **Content and creation:** exact-byte `RevisionContent` validation, immutable metadata with explicit duplicate conflicts, and identical failed content returning the existing revision.
  - **Naming and scope:** the `revisions` domain module, and `chunker_version` introduced in M3d.
  - **Locking and activation:** the job → document → ordered-revision lock order, the fresh ownership re-check after the extra lock waits, and the demote → promote → pointer activation order.
  - **Failure:** separate revision and job failure commits with documented recovery, and dead-job reconciliation or a truthful projection required before overall M3 acceptance.
- **Final clarifications** (applied in Prompt 68):
  - **Uncertain-commit recovery:** a committed atomic finish leaves the job `succeeded`, so it is not reclaimable; an uncommitted one is retried or reclaimed with the revision still `processing`. Duplicate activation is tested separately.
  - **Failure codes:** `RevisionFailureCode.INGESTION_FAILED` maps to `PermanentJobError(JobErrorCode.PERMANENT_FAILURE)`, and the two code types are never mixed.
  - **Tenant check:** `recheck_ownership` checks the token, status and expiry; the M3c caller checks the tenant.
- **Implementation of M3c has not started.**

## Prompt 68: Accept the M3c revision specification and commit it locally

- **Stage:** Documentation only, on branch `docs/m3c-revision-spec` (local commit authorized; no push)
- **Date:** 2026-10-12 (session date)

````text
Finalize and commit the reviewed M3c specification locally. Documentation only; do not implement or push.

Follow CLAUDE.md. Work in:
D:\Claude\evidenceguard_agentic_rag

1. Verify starting state

Expected:
- Branch: docs/m3c-revision-spec
- HEAD:
  dd26c7099d1007e9ee615204dc0056abe8820c67
- Staged tree:
  3fe4621973afad02f3a7b3f3cf3ed36016946f1b
- Exactly five staged files:
  README.md
  docs/decisions/0008-worker-runtime.md
  docs/plan.md
  docs/threat-model.md
  prompts.md
- Nothing unstaged or untracked.
- Expected origin:
  https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git

Stop without changes if anything differs.
Record the accepted staged tree before editing.

2. Accept the corrected specification

The reviewer inspected the complete Prompt 66 documentation diff and Prompt 67 corrections without running application checks.

Accept the corrected M3c specification and its listed decisions:
- Composite tenant/document ownership constraints.
- One-active partial unique index.
- Revision allocation counter under the document lock.
- No triggers.
- Exact-byte RevisionContent validation.
- Immutable metadata and explicit duplicate conflicts.
- Identical failed content returns the existing revision.
- revisions domain module.
- chunker_version introduced in M3d.
- Job → document → ordered revision locks.
- Fresh ownership recheck after additional lock waits.
- Demote → promote → pointer activation order.
- Separate revision/job failure commits with documented recovery.
- Required dead-job reconciliation or truthful projection before overall M3 acceptance.

Implementation remains pending.

3. Two final clarifications

A. Uncertain commit and reclaim

Correct the recovery wording and planned tests:
- If atomic activation plus job success actually committed, the job is succeeded and cannot be reclaimed. A later fenced outcome attempt is refused; no second activation occurs.
- If the atomic transaction did not commit, the job may be retried/reclaimed and the revision remains processing; the next valid attempt activates normally.
- An idempotent duplicate activation can still be tested separately using an appropriate valid fenced invocation, but do not describe a succeeded job as reclaimable.

Keep uncertain acknowledgment distinct from proven rollback.

B. Revision failure code versus job failure code

RevisionFailureCode and JobErrorCode are distinct types.
The existing PermanentJobError requires JobErrorCode.

Specify the initial mapping explicitly:
- fail_revision records RevisionFailureCode.INGESTION_FAILED.
- After that fenced transaction commits, the handler raises PermanentJobError(JobErrorCode.PERMANENT_FAILURE).
- Recovery of an already-failed revision uses the same job error mapping.
- Do not pass RevisionFailureCode directly to PermanentJobError.
- Additional parser-specific revision codes and any finer job-code mapping belong to M3d review.

Also clarify that recheck_ownership validates token/running/expiry, while the M3c caller explicitly verifies the persisted job tenant matches the revision/document scope. Do not imply JobLeaseToken itself carries a tenant.

4. Documentation status and history

Mark the M3c specification accepted at review, implementation pending.
Update README.md consistently.
Keep M3c–M3f unimplemented, Compose unverified and overall M3 acceptance pending.

Change only README.md, docs/plan.md and prompts.md unless another staged document directly contradicts these final clarifications. Explain any additional necessary edit.

Append this prompt verbatim as Prompt 68 if it is the next unused number; otherwise use the next unused number and explain it.
Add an acceptance note under Prompt 67 recording the reviewed diffs, final clarifications and verification limits.
Add a truthful pre-commit note.
Earlier history remains unchanged.

5. Checks and local commit

Inspect the incremental diff against the recorded accepted tree.
Check links, consistency and private content.
Confirm effective author and committer email:
257921624+mathewmljourney93@users.noreply.github.com

Run:
- git diff --cached --check
- Staged Gitleaks scan

Create one LOCAL commit:
docs: accept M3c revision specification and record M3b main results

Use the existing attribution convention.

After committing:
- Run the full-history Gitleaks scan.
- Verify parent, committed paths, identity and clean working tree.
- Confirm main remains unchanged.

No application tests or builds are needed for documentation-only changes.

6. Handoff

Return:
- Commit SHA, parent, subject and identity.
- Final clarifications.
- Actual checks and results.
- Prompt-history additions.
- COMPLETE incremental diff against the accepted staged tree, excluding prompts.md.
- Final Git status and remaining limitations.

No application code, migrations, tests, dependencies or workflow edits.
Do not push, merge, amend, rebase, start Docker or contact a database.
Do not begin M3c implementation in this task.
````

**Pre-commit note (written before the local commit):**
- **Starting state verified:**
  - branch `docs/m3c-revision-spec`, HEAD `dd26c70`;
  - staged tree `3fe4621…` with exactly the five expected files;
  - nothing unstaged or untracked, and the expected origin.

  The accepted staged tree was recorded before editing.
- **Changes:**
  - **`docs/plan.md`:** the M3c specification is marked accepted at review, implementation pending. The proposal markers became settled wording, and the final clarifications were applied.
  - **`README.md`:** the status was updated to match.
  - No other staged document contradicted the clarifications.
  - M3c–M3f remain unimplemented, Compose is unverified, and overall M3 acceptance is pending.
- **Checks before the commit:**
  - the link check;
  - the consistency and private-content searches;
  - the author and committer identity check;
  - `git diff --cached --check`;
  - the staged Gitleaks scan.

  Exact results are in the session handoff. No application tests or builds were run.
- **After the commit:** the full-history Gitleaks scan and the commit verification are reported in the session handoff, not recorded here.
- **No code, tests, dependencies, migrations or workflow edits. No push, merge, amend, rebase, Docker or database contact.**

**Outcome after the commit (recorded with Prompt 69):** the local commit `26021c2` (`26021c2daa6e2ad69ace5cfa4517f3b6ef7ce8a3`, parent `dd26c70`) was created on `docs/m3c-revision-spec` and was not pushed. Prompt 69's starting-state check confirmed that HEAD, its parent, a clean working tree, and `main` and `origin/main` still at `dd26c70`. The full-history Gitleaks scan after the commit was reported clean in the Prompt 68 session handoff; it was not re-run for this note.

## Prompt 69: Implement M3c documents, revisions and fenced activation

- **Stage:** M3c implementation on local branch `feat/document-revisions` (staged and uncommitted for review; no commit, push or database)
- **Date:** 2026-10-12 (session date)

````text
Implement M3c: tenant-scoped documents, revision lifecycle and fenced activation, following the accepted specification. Leave all implementation work staged and uncommitted for review.

Follow CLAUDE.md. Work in:
D:\Claude\evidenceguard_agentic_rag

1. Verify starting state

Expected:
- Branch: docs/m3c-revision-spec
- HEAD:
  26021c2daa6e2ad69ace5cfa4517f3b6ef7ce8a3
- Parent:
  dd26c7099d1007e9ee615204dc0056abe8820c67
- Working tree clean, nothing untracked.
- Local main and origin/main:
  dd26c7099d1007e9ee615204dc0056abe8820c67
- Origin:
  https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git

Stop without changes if anything differs.

Create feat/document-revisions from HEAD.
If that branch already exists, stop and report its state rather than resetting or reusing it.

2. Read the accepted design and actual interfaces

Read:
- CLAUDE.md
- The complete accepted M3c section in docs/plan.md
- ADR-0004, ADR-0007 and ADR-0008
- Existing domain models, persistence models and migrations
- Job fencing and worker atomic-finish interfaces
- Integration fixtures, migration checks and readiness tests

Implement the settled specification, including Prompts 67–68’s corrections. Do not reopen accepted decisions or silently redesign the architecture.

3. Implementation scope

Add:
- evidenceguard_domain.revisions
- evidenceguard_persistence.documents
- Document and DocumentRevision persistence models
- Migration 0003, following existing naming conventions
- The accepted read-only recheck_ownership helper
- Focused unit and PostgreSQL integration tests
- ADR-0009 and truthful progress documentation

Implement:
- Exact-byte RevisionContent validation
- Immutable document/revision snapshots and pure lifecycle rules
- Tenant-scoped document/revision creation
- Concurrent revision-number allocation
- Duplicate-content idempotency and explicit metadata conflicts
- Fenced start_processing, fail_revision and activate_revision
- Transactional activation, supersession and pointer updates

Do not add parsing, chunking, ingestion handlers, uploads, endpoints, reconciliation, Docker changes, new dependencies or a storage service.

4. Required invariants

Schema:
- Composite tenant references to vendors/documents.
- Active and supersession pointers must belong to the same tenant and document.
- Named status/field constraints reject partially filled failure or supersession pairs.
- At most one active revision per document.
- Circular-reference migration creation and downgrade order are correct.
- No triggers; distinguish application invariants from database constraints.

Content:
- Strict UTF-8, nonempty, no NUL.
- Hash and byte size derive from the exact bytes.
- No newline, BOM or Unicode normalization before hashing.
- Stored fields are re-verified when reconstructed.
- Do not inherit whitespace-stripping behavior that changes content_text.
- Errors, repr and validation diagnostics must not expose submitted document content.

Creation:
- Use the actor’s tenant and the accepted role rules.
- Lock the document before allocating revision numbers.
- Identical content returns the existing revision, including failed revisions.
- Metadata conflicts cause no committed changes.
- The caller owns the transaction; creation never commits.
- Preserve the seam for revision plus future ingestion-job creation in one transaction.

Lifecycle and activation:
- Failed replacement preserves the previous active revision.
- Compare against the currently active revision, not merely the latest uploaded one.
- Job → document → revisions in ascending ID lock order.
- Re-read mutable data after locks.
- Recheck the locked job with fresh database time after additional lock waits.
- Explicitly verify the re-read job tenant matches revision/document scope.
- Refuse stale or expired ownership before effects.
- Demote the previous active revision before promoting the target, then update the pointer.
- Older late completion changes only the target revision.
- Duplicate activation changes no links or timestamps.
- Use caller-owned FencedSession; no internal commit, rollback or transaction-control SQL.
- Activation and final job success can commit together through ctx.fenced(finish=True).
- Commit acknowledgment failure remains uncertain, not proof of rollback.
- A committed succeeded job cannot be reclaimed.

Failure:
- Keep RevisionFailureCode separate from JobErrorCode.
- The future seam commits revision INGESTION_FAILED first, then raises PermanentJobError(JobErrorCode.PERMANENT_FAILURE) outside the block.
- Document the separate-commit gap and recovery of an already-failed revision.
- Dead-job reconciliation/projection remains a required later M3d/M3e item, not implemented here.

If a genuine implementation conflict requires changing the accepted contract, stop and report the concrete conflict rather than silently changing it.

5. Tests

Implement the accepted verification plan, especially:
- Pure transition table, invalid transitions, idempotency and aware-time checks.
- Exact-byte hash/size consistency, CRLF, BOM, Unicode, invalid UTF-8, NUL and content privacy.
- SQL scoping, lock order and fresh ownership recheck.
- Migration upgrade/downgrade/re-upgrade and metadata drift.
- Actual composite constraints and one-active partial index.
- Concurrent creation of distinct and identical content.
- Revision plus job transaction rollback.
- Failed replacement preserves the active revision.
- Out-of-order and concurrent activations leave one consistent active pointer.
- Rollback after demotion but before promotion.
- Rollback when activation or final job success fails.
- Stale attempt refusal.
- Lease expiry during a document-lock wait.
- Lock-timeout mapping.
- Duplicate activation using a valid fenced invocation.
- Worker atomic-finish integration with test-only handlers.
- Both uncertain-commit cases using controlled doubles.

Use guarded disposable fixtures, event-controlled concurrency, bounded waits and test-only statement timeouts.

Do not start Docker or contact a local database. PostgreSQL tests remain pending authorized publication and CI.

Update existing migration-head expectations without weakening historical migration tests.

6. Verification

Run:
- uv sync --locked
- uv run --locked ruff format --check .
- uv run --locked ruff check .
- uv run --locked mypy
- uv run --locked pytest
- uv build
- Isolated installed-wheel imports and offline migration rendering outside the source tree
- git diff --cached --check
- Staged Gitleaks scan

No dependency or workflow change is expected. Report any required packaging adjustment explicitly.

Report actual passing and skipped counts, separating PostgreSQL skips from platform skips. Do not claim database verification from compiled SQL or unit tests.

7. Documentation and history

Create ADR-0009 covering implementation choices, invariants and limits.
Mark M3c implemented on its local branch, awaiting review and PostgreSQL CI.
Update README, plan and threat model consistently.

Keep:
- No production ingestion handler yet.
- Compose unverified.
- M3d–M3f unimplemented.
- Overall M3 acceptance pending.

Append this prompt verbatim as Prompt 69 if it is the next unused number; otherwise use the next unused number and explain it.
Add a truthful outcome note with actual checks and limitations.
Preserve earlier prompt history.

8. Review handoff

Stage the complete implementation, excluding generated outputs and local artifacts.

Return:
- What changed and why.
- Implementation choices within the accepted specification.
- Actual commands/results and failures corrected along the way.
- Staged tree ID, full staged paths and Git status.
- COMPLETE staged diff excluding prompts.md, including every new source file, migration, test and document.
- Numbered parts at file boundaries when needed; never silently truncate.
- If response limits prevent completion, identify exactly which files remain and preserve the complete diff under .local/ for continuation.
- Prompt-history additions and remaining verification limits.

Leave everything staged and uncommitted.
Do not push, merge, amend, rebase, start Docker or contact a local database.
Do not begin M3d.
````

**Outcome note (written before review; the work is staged and uncommitted):**
- **Starting state verified:** branch `docs/m3c-revision-spec` at `26021c2` with parent `dd26c70`, a clean tree, local `main` and `origin/main` at `dd26c70`, and the expected origin. `feat/document-revisions` did not exist and was created from HEAD.
- **Implemented** as specified, without changing an accepted decision:
  - `evidenceguard_domain.revisions`: exact-byte `RevisionContent`, immutable snapshots that keep strings exactly, and the pure lifecycle rules;
  - the `Document` and `DocumentRevision` models and migration `0003` (composite tenant references, same-document pointers, named paired checks, the one-active partial index, circular-reference ordering, no triggers);
  - the read-only `recheck_ownership` helper in `evidenceguard_persistence.jobs`;
  - `evidenceguard_persistence.documents`: creation in the caller's transaction, and fenced `start_processing`, `fail_revision` and `activate_revision`;
  - ADR-0009, and status updates to the README, plan and threat model.
- **Implementation choices** within the specification are listed in ADR-0009 (for example `sha256` as `varchar(64)` with a regex check, activation timestamps from the re-check's fresh time, and no `lock_timeout` on creation's caller-owned document lock).
- **Tests added or updated:** `tests/test_revisions.py` (60), `tests/test_document_store.py` (38, a scripted database double and a fake job store driving the real worker runtime), two offline migration tests, readiness and head pins, and `tests/test_documents_postgres.py` (55 PostgreSQL integration tests).
- **Checks run locally in this session (Windows):** `uv sync --locked`; `ruff format --check .`; `ruff check .`; `mypy` (81 source files); `pytest` (`809 passed, 133 skipped`: 132 PostgreSQL integration skips because `EG_TEST_DATABASE_URL` is unset, and 1 Windows platform skip); `uv build`; an installed-wheel check outside the source tree (imports and offline migration rendering of `0003`, upgrade and downgrade); `git diff --cached --check`; the staged Gitleaks scan. Exact output is in the session handoff.
- **Not verified:** none of the 55 new PostgreSQL tests, nor the updated migration round trip, has run. They are **pending** authorized publication and CI. Compiled SQL, the scripted double and unit tests are not database verification.
- **Remaining limits:** no production ingestion handler, endpoint or upload; no reconciliation of dead jobs (required before overall M3 acceptance); revision and job failure are separate commits; Compose is unverified; M3d–M3f are not implemented; overall M3 acceptance is pending.
- **Review status:** pending. No commit, push, merge, Docker or database contact.

**Review note for Prompt 69 (added with Prompt 71):** the external reviewer inspected the complete staged diff (Parts 1–7, Parts 1–6 supplied by Prompt 70) and reported three findings, corrected in Prompt 71. The reviewer reproduced the missing-pointer no-op with the pure functions in isolation and the duplicate-keyword `TypeError` in Python; they did not run the project suite or the PostgreSQL tests.

## Prompt 70: Supply the missing M3c review diff parts (read-only)

- **Stage:** Read-only review handoff on branch `feat/document-revisions` (no repository changes)
- **Date:** 2026-10-13 (session date)
- **Numbering:** this request said to defer its own recording to the next authorized history update, so it was not written when it ran. It is recorded now, with Prompt 71, as the next unused number (70).

````text
Provide the missing M3c review material. Do not change files, staging, history or branches.

Follow CLAUDE.md. Work in:
D:\Claude\evidenceguard_agentic_rag

Verify:
- Branch: feat/document-revisions
- HEAD: 26021c2daa6e2ad69ace5cfa4517f3b6ef7ce8a3
- Staged tree: 5eb3e036c43b156b9db68be91fc37c58316d679a
- The same 16 staged files reported for Prompt 69.
- Nothing unstaged or untracked.

Stop and report any mismatch.

The external reviewer received only Part 7 of 7 and the verification report. They have not received Parts 1–6.

Return the COMPLETE missing Parts 1–6 of the staged diff, excluding prompts.md, including:
- All domain and persistence implementation.
- The ownership-recheck helper.
- Models and migration 0003.
- test_document_store.py and test_documents_postgres.py.
- ADR-0009 and documentation changes.

Use the existing saved diff parts if they reproduce the current staged state exactly; otherwise generate the diff read-only.

Preserve numbered parts and file boundaries. Never silently truncate or substitute summaries for source or tests.

If response limits prevent returning all six parts, clearly identify which parts were supplied and which remain. Supply the remainder in subsequent responses without changing the repository.

Do not repeat Part 7 or rerun verification.
Do not append this read-only handoff request to prompts.md now; defer recording it until the next authorized history update.

Finish by confirming the staged tree and Git status remain unchanged.
No edits, commits, pushes, merges, Docker or database contact.
````

**Outcome note:** the starting state matched (branch, HEAD `26021c2`, staged tree `5eb3e03…`, the 16 staged paths, nothing unstaged or untracked). The saved diff parts under `.local/p69/parts/` were confirmed byte-identical to the staged diff with `cmp`, and Parts 1–6 were returned in full. No files, staging, history or branches changed (`git write-tree` only recorded the existing tree object), and no verification was re-run.

## Prompt 71: Correct three M3c review findings

- **Stage:** M3c correction on local branch `feat/document-revisions` (staged and uncommitted for review; no commit, push or database)
- **Date:** 2026-10-13 (session date)
- **Numbering:** 71 is the next unused number after the read-only Prompt 70 recorded above.

````text
Correct three M3c review findings. Leave everything staged and uncommitted for review.

Follow CLAUDE.md. Work in:
D:\Claude\evidenceguard_agentic_rag

1. Verify starting state

Expected:
- Branch: feat/document-revisions
- HEAD:
  26021c2daa6e2ad69ace5cfa4517f3b6ef7ce8a3
- Staged tree:
  5eb3e036c43b156b9db68be91fc37c58316d679a
- The same 16 staged paths reported for Prompt 69.
- Nothing unstaged or untracked.
- Expected origin for evidenceguard-agentic-rag.

Stop without changes if anything differs.
Record the pre-edit staged tree.

2. PostgreSQL failure-code test

In test_revision_checks_reject_partial_or_invalid_state, this case is structurally valid under the accepted schema:

status="failed", failure_reason="parser_crashed", failed_at=func.now()

The database checks the fixed-code pattern, not RevisionFailureCode enum membership.

Correct the test:
- Use a genuinely invalid code pattern for the rejection case.
- Add a separate test demonstrating that a structurally valid pattern code is accepted by PostgreSQL.
- Keep the application enum restriction explicit.
- Do not tighten the schema to an enum list merely to make the existing test pass.

Keep database enforcement and application validation distinct in documentation.

3. Metadata-conflict test invocation

test_metadata_conflicts_commit_nothing calls:

_create(..., version_label="v1", **overrides)

The version_label override case supplies that keyword twice and raises TypeError before entering _create.

Build one argument dictionary, apply overrides to it, then call the helper once.

Preserve assertions that:
- The intended DocumentConflictError or RevisionConflictError is raised.
- No document/revision state changes commit.
- Every parameter case actually reaches the persistence operation.

Do not weaken the test to accept TypeError.

4. Pure activation consistency

_require_consistent returns early when active is None and the document pointer is None. Consequently, an ACTIVE target with no active pointer is accepted by settle as an idempotent no-op.

Correct the consistency checks:
- An ACTIVE target must be the document's pointed-to active revision.
- A non-null active pointer must have a matching ACTIVE snapshot of the same tenant and document.
- A PROCESSING target cannot share the active revision's ID or revision number.
- Target and active revision numbers cannot exceed the document's latest_revision_no.
- Reject inconsistent combinations with the existing fixed InconsistentDocumentStateError before returning a no-op or constructing transitions.
- Preserve valid superseded retries and normal activation behavior.

Add focused tests covering these inconsistent cases and valid duplicate activation.

Show that the relevant new pure-rule regression tests fail against the previous revisions.py, then restore the corrected file and verify its identity.

The reviewer inspected Parts 1–6 plus the earlier Part 7, reproduced the missing-pointer no-op using the supplied pure functions in isolation, and reproduced Python's duplicate-keyword TypeError. The reviewer did not run the project suite or PostgreSQL tests.

5. Scope and verification

Make narrow changes to the domain rules, relevant tests and any directly affected documentation.
No migrations, dependencies or workflow changes should be needed.

Run:
- uv run --locked ruff format --check .
- uv run --locked ruff check .
- uv run --locked mypy
- uv run --locked pytest
- uv build
- Isolated installed-wheel imports and offline migration rendering
- git diff --cached --check
- Staged Gitleaks scan

Do not start Docker or contact a local database.
Keep PostgreSQL and platform skips separate.
The corrected PostgreSQL tests remain unverified until authorized publication and CI.

6. Prompt history and handoff

Append this prompt verbatim using the next unused prompt number. Explain the numbering, including whether the read-only missing-diff handoff was assigned a number.

Record that the missing Parts 1–6 were supplied without repository changes. Preserve earlier entries and outcomes.

Return:
- Explanation of each correction.
- New pure-rule test results against the previous implementation.
- Actual final verification results.
- New staged tree ID, staged paths and Git status.
- COMPLETE incremental diff against the recorded pre-edit staged tree, excluding prompts.md, including all changed tests.
- Prompt-history additions and remaining verification limits.

Leave everything staged and uncommitted.
Do not push, merge, amend, rebase, start Docker or contact a local database.
Do not begin M3d.
````

**Outcome note (written before review; the work is staged and uncommitted):**
- **Starting state verified:** branch, HEAD `26021c2`, staged tree `5eb3e036c43b156b9db68be91fc37c58316d679a` (recorded as the pre-edit tree), the 16 staged paths, nothing unstaged or untracked, and the expected origin.
- **Corrections:**
  1. *PostgreSQL failure-code test:* the rejection case now uses a code that breaks the pattern (`Not-A-Code`). A new integration test shows that PostgreSQL accepts a well-formed code outside the enum (`parser_crashed`), and a new unit test shows that the application rejects it. The schema is unchanged; ADR-0009 and the model docstring now separate the database pattern check from the application's enum restriction.
  2. *Metadata-conflict test:* one argument dictionary is built, overrides are applied to it, and the helper is called once. A recording wrapper around `create_revision` asserts that the persistence operation itself raised the expected conflict in every case.
  3. *Pure activation consistency:* `settle` now refuses, before any no-op or transition, an `active` target without the matching pointer, a pointer without a matching active snapshot (or one that is not the pointed-to `active` revision of the same tenant and document), a `processing` target sharing the active revision's ID or number, and a revision number above `latest_revision_no`.
- **Regression evidence (local, Windows):** against the previous `revisions.py` (sha256 `47cdfae9…`), 4 of the new pure-rule tests failed (missing pointer, shared ID, shared number, number above the counter; `4 failed, 65 passed`). The corrected file was restored (sha256 `df006d90…`, identity checked) and the module passed (`69 passed`).
- **Checks run in this session:** `ruff format --check .`, `ruff check .`, `mypy` (81 source files), `pytest` (`818 passed, 134 skipped`: 133 PostgreSQL integration skips and 1 Windows platform skip), `uv build`, an installed-wheel import and offline migration check outside the source tree, `git diff --cached --check` and the staged Gitleaks scan. Exact output is in the session handoff.
- **Not verified:** the corrected and new PostgreSQL tests have not run; they remain pending authorized publication and CI.
- **Review status:** pending. No commit, push, merge, Docker or database contact; M3d not started.

**Acceptance note for Prompt 71 (added with Prompt 72):** the external reviewer accepted M3c on the basis of Prompt 69's complete implementation diff (Parts 1–7) and Prompt 71's complete correction diff, together with the reported Windows checks:
- `pytest`: `818 passed, 134 skipped` (133 PostgreSQL integration skips and one POSIX-only platform skip);
- format, lint, strict type-check, build, installed-wheel and secret-scan results;
- four pure-rule regression failures against the earlier `revisions.py`, then 69 passing revision tests after restoration.

The reviewer reproduced the original missing-pointer behaviour and the duplicate-keyword `TypeError` in isolation, but did not run the project suite or the corrected tests. PostgreSQL verification (all 133 integration tests against this version), Linux verification, Compose, dead-job reconciliation or projection (M3d/M3e) and overall M3 acceptance remain pending.

## Prompt 72: Commit the reviewed M3c implementation locally

- **Stage:** Local commit of the accepted M3c staged tree on branch `feat/document-revisions` (local commit authorized; no push or merge)
- **Date:** 2026-10-13 (session date)

````text
Commit the reviewed M3c implementation locally. Do not push or merge.

Follow CLAUDE.md. Work in:
D:\Claude\evidenceguard_agentic_rag

1. Verify starting state

Expected:
- Branch: feat/document-revisions
- HEAD:
  26021c2daa6e2ad69ace5cfa4517f3b6ef7ce8a3
- Staged tree:
  feed6226ddcb49bea518780d4a33ec643f0e0779
- Exactly the same 16 staged paths reported for Prompt 71.
- Nothing unstaged or untracked.
- Origin:
  https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git
- Local main and origin/main:
  dd26c7099d1007e9ee615204dc0056abe8820c67

Stop without changes if anything differs.
Record the accepted staged tree before editing.

2. Preserve the reviewed implementation

The reviewer accepts:
- Prompt 69’s complete implementation diff, Parts 1–7.
- Prompt 71’s complete correction diff.

Acceptance rests on those diffs and the reported Windows checks:
- 818 passed, 134 skipped.
- 133 PostgreSQL integration skips and one POSIX-only platform skip.
- Format, lint, strict type-check, build, installed-wheel and secret-scan results.
- Four pure-rule regression failures against the earlier implementation, then 69 passing revision tests after restoration.

The reviewer reproduced the original missing-pointer behavior and duplicate-keyword TypeError in isolation, but did not run the project suite or corrected tests.

Keep every tracked file except prompts.md byte-identical to the accepted staged tree. Do not alter code, tests, migration, configuration or other documents.

3. Prompt history

Change only prompts.md, append-only:
- Add an acceptance note under Prompt 71 with the evidence and limits above.
- Append this prompt verbatim as Prompt 72 if that is the next unused number; otherwise use the next unused number and explain it.
- Add a truthful pre-commit note recording verified state, checks and local-only authorization.
- Keep earlier entries unchanged.
- Do not claim publication or PostgreSQL CI verification.

4. Checks and local commit

Inspect staged paths and diff.
Confirm no local artifacts or generated build outputs are staged.
Check staged additions for secrets and private information.

Confirm effective author and committer email:
257921624+mathewmljourney93@users.noreply.github.com

Run:
- git diff --cached --check
- Staged Gitleaks scan

Create one LOCAL commit:
feat: add tenant-scoped document revisions and fenced activation

Use the existing attribution convention.

After committing:
- Run the full-history Gitleaks scan.
- Verify parent is 26021c2daa6e2ad69ace5cfa4517f3b6ef7ce8a3.
- Verify the expected 16 committed paths.
- Verify every file except prompts.md matches the accepted staged tree.
- Verify identity and clean working tree.
- Confirm main remains unchanged.

Application checks need not be rerun because only prompt history changed since the reviewed verification.

5. Handoff

Return:
- Commit SHA, parent, subject and identity.
- Committed paths.
- Actual checks and results.
- Prompt-history additions and confirmation earlier entries are unchanged.
- Final Git status.
- Complete incremental diff against the accepted staged tree, excluding prompts.md. If none, explicitly say none.
- Remaining verification limits.

Keep these pending:
- PostgreSQL verification of M3c and the full 133-test integration suite against this version.
- Linux verification of M3c.
- Compose.
- Dead-job reconciliation/projection in M3d/M3e.
- Overall M3 acceptance.

Do not push, merge, amend, rebase, start Docker or contact a local database.
Do not begin M3d.
````

**Pre-commit note (written before the local commit):**
- **Starting state verified:** branch `feat/document-revisions`, HEAD `26021c2`, staged tree `feed6226ddcb49bea518780d4a33ec643f0e0779` (recorded as the accepted tree), exactly the 16 staged paths of Prompt 71, nothing unstaged or untracked, the expected origin, and local `main` and `origin/main` at `dd26c70`.
- **Change:** only this append to `prompts.md`; every other tracked file is kept byte-identical to the accepted staged tree. No application checks were re-run, because only prompt history changed since the reviewed verification.
- **Checks before the commit:** staged paths and diff inspected, no local artifacts or build outputs staged, staged additions checked for secrets and private information, effective author and committer email confirmed, `git diff --cached --check` and the staged Gitleaks scan. Exact results are in the session handoff.
- **After the commit:** the full-history Gitleaks scan and the commit verification are reported in the session handoff, not recorded here.
- **Authorization:** one local commit only. No push, merge, amend, rebase, Docker or database contact; M3d not started. Nothing here claims publication or PostgreSQL CI verification.

**Outcome after the commit (recorded with Prompt 73):** local commit `057d57d` (`057d57dd91c7a6f946137df565e79e0bac75bb3c`, parent `26021c2`, noreply identity) contains the 16 expected paths. Every file except `prompts.md` matches the accepted staged tree `feed622…`. The full-history Gitleaks scan after the commit reported 28 commits scanned and no leaks; the working tree was clean, and `main` stayed at `dd26c70`. It was not pushed.

## Prompt 73: Publish the M3c feature branch and verify CI

- **Stage:** Publication of branch `feat/document-revisions` only (push of this branch authorized; `main` not updated or merged)
- **Date:** 2026-10-13 (session date)

````text
Publish the reviewed M3c feature branch and verify CI. This authorizes pushing only feat/document-revisions. Do not update or merge main.

Follow CLAUDE.md. Work in:
D:\Claude\evidenceguard_agentic_rag

1. Verify starting state

Expected:
- Branch: feat/document-revisions
- HEAD:
  057d57dd91c7a6f946137df565e79e0bac75bb3c
- Parent:
  26021c2daa6e2ad69ace5cfa4517f3b6ef7ce8a3
- Working tree clean, nothing untracked.
- Origin:
  https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git
- No upstream configured.
- Local and remote main:
  dd26c7099d1007e9ee615204dc0056abe8820c67
- No remote feat/document-revisions branch.
- Remote main is an ancestor of HEAD.
- Effective author and committer email:
  257921624+mathewmljourney93@users.noreply.github.com

Check remote refs freshly. Stop without changes if anything differs.

2. Publication preflight

Inspect every commit and tracked change becoming public relative to remote main, including the specification commit 26021c2.

Confirm:
- Noreply author and committer identities.
- No tracked local artifacts, backups, bundles, real environment files, credentials or generated build outputs.
- Changes match the reviewed specification and implementation.
- Both workflows trigger on this branch’s push.
- Ubuntu verification, Windows verification, PostgreSQL integration and full-history secret scanning remain enabled.
- EG_REQUIRE_INTEGRATION=1 remains enabled.
- No workflow change was introduced by M3c.

Do not modify implementation or workflows.
Stop and report any publication blocker.

3. Record authorization

Change only prompts.md, append-only:
- Append this prompt verbatim as Prompt 73 if that is the next unused number; otherwise use the next unused number and explain it.
- Add a truthful preflight note covering verified state, publication scope, checks and branch-only authorization.
- Record historical Windows results accurately:
  818 passed, 134 skipped: 133 PostgreSQL tests and one POSIX-only platform test.
- The existing 77 integration tests passed for M3b; the 56 added by M3c have not run. All 133 remain unverified against this M3c version.
- Do not pre-record push or CI success.
- Keep earlier entries unchanged.

Stage only prompts.md.
Inspect its diff and private content.
Run git diff --cached --check and the staged Gitleaks scan.

Create one local commit:
docs: record M3c branch publication authorization

Use the noreply identity and existing attribution convention.
Verify it changes only prompts.md.
Run the full-history Gitleaks scan before pushing.
Stop on failure.

No local application checks need rerunning for this history-only change.

4. Publish only the feature branch

Run:
git push --set-upstream origin refs/heads/feat/document-revisions:refs/heads/feat/document-revisions

Confirm the remote feature branch matches the exact published HEAD and main remains unchanged.

Do not push another branch or tag. Do not force-push.

5. Monitor exact-SHA CI

Wait for:
- Ubuntu verification
- Windows verification
- PostgreSQL integration
- Full-history secret scan

Use available read-only GitHub access. Do not install tooling or change authentication configuration.

Bound monitoring to 20 minutes.
If any check fails or remains pending, report links and available diagnostics, then stop.
Do not automatically fix, commit or repush.

If logs are accessible, report actual pytest summaries and migration-check results.
The expected integration count is 133, but do not present that expectation as an observed result.

If logs are inaccessible, report job/step conclusions and explicitly say test counts were not observed.
Do not reuse historical counts as results for the published SHA.

6. Handoff

Return:
- Publication-history commit SHA and parent.
- Exact published SHA.
- Prompt-history additions.
- Preflight and scan results.
- Workflow/job links and conclusions for that SHA.
- Observed test summaries and migration results, or log-access limitations.
- Final Git status and remote refs.
- Complete incremental diff outside prompts.md; if none, explicitly say none.

Main remains unchanged.
Compose, dead-job reconciliation/projection in M3d/M3e, M3d–M3f and overall M3 acceptance remain pending.

Do not merge, amend, rebase, delete branches, start Docker or contact a local database.
Do not begin M3d.
````

**Preflight note (written before this history commit and the push):**
- **Verified state:**
  - branch `feat/document-revisions` at `057d57d` (parent `26021c2`);
  - a clean working tree with nothing untracked;
  - the expected origin, and no upstream configured;
  - fresh `git ls-remote`: remote `main` at `dd26c70`, and no remote `feat/document-revisions`;
  - remote `main` is an ancestor of HEAD;
  - effective author and committer email `257921624+mathewmljourney93@users.noreply.github.com`.
- **Publication scope:** two commits beyond remote `main`, plus this history commit:
  - `26021c2`, the accepted M3c specification (documentation and prompt history only);
  - `057d57d`, the reviewed M3c implementation.

  The 17 changed paths relative to `main` are those reviewed in Prompts 66–72. All commits use the noreply author and committer identity.
- **Preflight checks:**
  - no tracked local artifacts, backups, bundles, environment files, credentials or build outputs;
  - a search of the additions for credential patterns, private keys, credentialed URLs, personal email addresses or local paths found nothing;
  - no workflow file changed.
- **Workflows (unchanged):**
  - `ci` and `secret-scan` both trigger on every `push`;
  - `verify` still runs on `ubuntu-24.04` and `windows-2025`;
  - the PostgreSQL 17 + pgvector `integration` job still sets `EG_REQUIRE_INTEGRATION: "1"`;
  - Gitleaks still scans the full history (`fetch-depth: 0`).
- **Historical local results (Windows, Prompt 71):** `818 passed, 134 skipped`. The skips are 133 PostgreSQL integration tests and one POSIX-only platform test.
  - The 77 integration tests that existed for M3b passed in CI for M3b.
  - The 56 integration tests added by M3c have never run.
  - All 133 are unverified against this M3c version.
- **Not yet done when this note was written:** the push and the CI results are reported in the session handoff, not recorded here.
- **Authorization:** push only `feat/document-revisions`, without force. Do not update or merge `main`, push any other branch or tag, amend, rebase, delete branches, start Docker or contact a database. M3d is not started.

**Publication outcome for Prompt 73 (recorded with Prompt 74):**
- **Commit:** the local history commit `8646b75` (`8646b75d63bfe8a0f47b089824ded6d75c542f4e`, parent `057d57d`, noreply identity) changed only `prompts.md`. The full-history Gitleaks scan before the push reported 29 commits scanned and no leaks.
- **First push attempt:** it failed with `Could not resolve host: github.com`, and nothing reached the remote. The command reported exit code 0 only because its output was piped through `tail`; that status was not git's, and the push was not treated as successful. A fresh `git ls-remote` confirmed that the branch was still absent and that `main` was unchanged.
- **Retry:** the same authorized command, `git push --set-upstream origin refs/heads/feat/document-revisions:refs/heads/feat/document-revisions`, then succeeded (git's own exit status 0, a new branch with tracking).
- **Scope:** only `feat/document-revisions` was published, at `8646b75`, without force or tags. Remote `main` stayed at `dd26c70`.
- **CI for `8646b75`:** monitored read-only within the 20-minute bound. [ci run 38284929219](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38284929219) and [secret-scan run 38284929225](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38284929225) were both push events on `feat/document-revisions` with conclusion `success`, and every job and step succeeded. Job logs returned HTTP 403 without authentication, so no counts were observed in that session.
- **Reviewer-retrieved evidence:** the external reviewer then retrieved the logs:
  - Ubuntu `819 passed, 133 skipped in 18.75s`;
  - Windows `818 passed, 134 skipped in 23.07s`;
  - PostgreSQL integration `133 passed, 819 deselected in 36.46s`: all 133 integration tests, the 77 existing ones and the 56 added by M3c;
  - secret scan: 29 commits scanned, no leaks found.

  The integration suite includes the migration round-trip, linked-row downgrade and metadata-drift checks, which passed as part of the suite; no separate migration transcript or per-test listing was observed. The reviewer did not run the project suite locally.

## Prompt 74: Record the verified M3c feature-branch CI results

- **Stage:** Documentation only, on branch `feat/document-revisions` (staged and uncommitted for review; no push)
- **Date:** 2026-10-13 (session date)

````text
Record the verified M3c feature-branch CI results. Documentation only; leave changes staged and uncommitted for review.

Follow CLAUDE.md. Work in:
D:\Claude\evidenceguard_agentic_rag

1. Verify starting state

Expected:
- Branch: feat/document-revisions
- HEAD and upstream:
  8646b75d63bfe8a0f47b089824ded6d75c542f4e
- Working tree clean, nothing untracked.
- Origin:
  https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git
- Local and remote main:
  dd26c7099d1007e9ee615204dc0056abe8820c67

Check remote refs freshly. Stop without changes if anything differs.

2. Independently retrieved evidence

The reviewer retrieved the GitHub job logs.

CI run:
https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38284929219

Observed summaries:
- Ubuntu job 114930898138:
  819 passed, 133 skipped in 18.75s
- Windows job 114930898065:
  818 passed, 134 skipped in 23.07s
- PostgreSQL job 114930897691:
  133 passed, 819 deselected in 36.46s

Secret-scan run:
https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38284929225

Job 114930897815:
29 commits scanned; no leaks found.

Both runs:
- head_sha: 8646b75d63bfe8a0f47b089824ded6d75c542f4e
- head_branch: feat/document-revisions
- conclusion: success

All 133 integration tests passed: 77 existing plus 56 added by M3c.

The integration suite includes the reviewed migration round-trip, linked-row downgrade and metadata-drift checks. Record that those checks passed as part of the suite, but do not claim a separately observed migration transcript or individually named pytest entries.

The reviewer retrieved CI evidence but did not run the project suite locally.

3. Documentation updates

Narrowly update only:
- README.md
- docs/decisions/0009-document-revisions.md
- docs/plan.md
- docs/threat-model.md
- prompts.md

Record:
- M3c implementation is reviewed and verified in CI on feat/document-revisions at 8646b75.
- Actual CI summaries and links above.
- Real PostgreSQL verification includes M3c’s constraints, migration, concurrency, activation and lease tests.
- M3c is not yet merged into main.
- No production ingestion handler, upload or document endpoint exists.
- Compose remains unverified.
- Dead-job reconciliation/projection remains required in M3d/M3e.
- M3d–M3f are unimplemented and overall M3 acceptance remains pending.
- Existing transaction, uncertain-commit and separate-failure-commit limitations remain unchanged.

Mark ADR-0009 accepted using the repository’s accepted-and-CI-verified convention.

Preserve historical evidence. Passing tests demonstrate tested behavior, not a general security or performance guarantee.

Do not change source, tests, migrations, dependencies, workflows or engineering defaults.

4. Prompt history

Append this prompt verbatim as Prompt 74 if that is the next unused number; otherwise use the next unused number and explain it.

Record Prompt 73’s actual publication outcome, including:
- The initial DNS failure.
- The successful retry of the same authorized push.
- The misleading pipeline exit status, without treating it as a successful git command.
- Feature-only publication and unchanged main.
- Reviewer-retrieved CI evidence.

Add a truthful outcome note for this documentation task.
Keep earlier entries unchanged.

5. Checks and handoff

Check documentation links, consistency and private content.
Run:
- git diff --cached --check
- Staged Gitleaks scan

No application tests or builds are needed.

Stage only the five authorized files.

Return:
- Explanation of changes.
- Actual check results.
- Staged tree ID, staged paths and Git status.
- COMPLETE staged diff excluding prompts.md, directly in fenced diff blocks.
- Numbered parts at file boundaries if needed; never silently truncate.
- Prompt-history additions and confirmation earlier entries are unchanged.

Leave changes staged and uncommitted.
Do not push, merge, amend, rebase, start Docker or contact a local database.
Do not begin M3d.
````

**Outcome note (written before review; the changes are staged and uncommitted):**
- **Starting state verified:** branch `feat/document-revisions` with HEAD and upstream at `8646b75`, a clean tree with nothing untracked, the expected origin, and local and remote `main` at `dd26c70`. Remote refs were checked fresh.
- **Changes:** only `README.md`, `docs/decisions/0009-document-revisions.md`, `docs/plan.md`, `docs/threat-model.md` and this append to `prompts.md`.
  - They record that M3c is reviewed and verified in CI on `feat/document-revisions` at `8646b75` and is not yet merged into `main`.
  - They add the reviewer-retrieved CI summaries and links, and note that the real PostgreSQL verification includes M3c's constraint, migration, concurrency, activation and lease tests.
  - ADR-0009 is marked accepted, following ADR-0008's accepted-and-CI-verified wording.
  - They keep: no production ingestion handler, upload or document endpoint; Compose unverified; dead-job reconciliation or projection required in M3d/M3e; M3d–M3f unimplemented; overall M3 acceptance pending; and the unchanged transaction, uncertain-commit and separate-failure-commit limits.
  - Historical evidence is preserved, and the results are described as demonstrating tested behaviour, not a general guarantee.
- **Checks:** a local link check of the edited documents, consistency and private-content searches, `git diff --cached --check` and the staged Gitleaks scan. Exact results are in the session handoff. No application tests or builds were run (documentation only).
- **Review status:** pending. No commit, push, merge, Docker or database contact; M3d not started.

**Acceptance note for Prompt 74 (added with Prompt 75):** the external reviewer accepted Prompt 74's complete documentation diff, with one wording correction made in Prompt 75 (the M3c verification-plan result in `docs/plan.md` now refers only to the PostgreSQL integration tests). Acceptance rests on the supplied diff and the CI logs the reviewer retrieved independently:
- Ubuntu `819 passed, 133 skipped in 18.75s`;
- Windows `818 passed, 134 skipped in 23.07s`;
- PostgreSQL `133 passed, 819 deselected in 36.46s`;
- secret scan: 29 commits scanned, no leaks found.

The reviewer did not run the suite locally.

## Prompt 75: Commit the M3c results documentation, publish the branch, then fast-forward main

- **Stage:** Documentation commit on `feat/document-revisions`, then publication of that branch; `main` is fast-forwarded only after all four checks pass (push of the feature branch and of `main` authorized, in that order)
- **Date:** 2026-10-13 (session date)

````text
Commit the reviewed M3c results documentation, publish the feature branch, then fast-forward main only after all four required checks pass.

Follow CLAUDE.md. Work in:
D:\Claude\evidenceguard_agentic_rag

1. Verify starting state

Expected:
- Branch: feat/document-revisions
- HEAD and upstream:
  8646b75d63bfe8a0f47b089824ded6d75c542f4e
- Staged tree:
  49ed2b96fb66a13e6bed5a66f3e5f77204189362
- Exactly five staged files:
  README.md
  docs/decisions/0009-document-revisions.md
  docs/plan.md
  docs/threat-model.md
  prompts.md
- Nothing unstaged or untracked.
- Origin:
  https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git
- Local and remote main:
  dd26c7099d1007e9ee615204dc0056abe8820c67
- Remote feature branch matches HEAD.
- Main is an ancestor of HEAD.
- Effective author and committer email:
  257921624+mathewmljourney93@users.noreply.github.com

Check remote refs freshly. Stop without changes if anything differs.
Record the accepted staged tree before editing.

2. One narrow wording correction

In docs/plan.md, replace the M3c verification-plan sentence:

“all of the above passed against PostgreSQL”

with wording that explicitly refers only to the PostgreSQL integration tests listed above.

Keep the observed result:
133 passed, 819 deselected at 8646b75.

Do not imply that controlled uncertain-commit simulations ran against PostgreSQL.

Every other non-history file must remain byte-identical to the accepted tree. Keep “not yet merged” wording truthful at this pre-publication point.

3. Prompt history

The reviewer accepts Prompt 74’s complete documentation diff with the correction above, based on the supplied diff and independently retrieved CI logs:
- Ubuntu: 819 passed, 133 skipped in 18.75s
- Windows: 818 passed, 134 skipped in 23.07s
- PostgreSQL: 133 passed, 819 deselected in 36.46s
- Secret scan: 29 commits scanned, no leaks

The reviewer did not run the suite locally.

Append-only in prompts.md:
- Acceptance note under Prompt 74.
- This prompt verbatim as Prompt 75 if that is the next unused number; otherwise use the next unused number and explain it.
- Truthful preflight note with verified state, correction, checks, authorization order and stop conditions.

Do not pre-record push, CI or main-update success.
Keep earlier entries unchanged.

4. Commit and scan

Inspect staged paths, incremental diff, private content and identity.
Run git diff --cached --check and the staged Gitleaks scan.

Create one commit:
docs: record verified M3c results and main publication authorization

Use the noreply identity and existing attribution convention.

Verify:
- Parent is 8646b75d63bfe8a0f47b089824ded6d75c542f4e.
- Exactly the five authorized files changed.
- Only the specified plan sentence and prompts.md differ from the accepted tree.
- Working tree is clean.

Run the full-history Gitleaks scan before publication. Stop on failure.
No local application tests or builds need rerunning for documentation-only changes.

5. Publish the feature branch first

Push only:
git push origin refs/heads/feat/document-revisions:refs/heads/feat/document-revisions

Run git directly. Do not pipe it through tail or another command that masks its exit status.

Monitor all four checks for the exact new SHA:
- Ubuntu verification
- Windows verification
- PostgreSQL integration
- Full-history secret scan

Use available read-only GitHub access. Do not install tooling or change authentication configuration.

Bound monitoring to 20 minutes.
If any check fails or remains pending, report diagnostics and links, then stop before touching main.
Do not automatically fix or repush.

Report actual test summaries if accessible. Otherwise explicitly say counts were not observed; do not reuse historical summaries as results for this new SHA.

6. Fast-forward main after all four checks pass

Fetch main and the feature branch again. Confirm:
- Remote main remains dd26c7099d1007e9ee615204dc0056abe8820c67.
- Remote feature branch matches the newly verified SHA.
- Main is an ancestor of that SHA.
- Local main equals origin/main with no independent commits.
- Working tree is clean.

Stop if any condition differs.

Switch to main and fast-forward to the verified SHA using git merge --ff-only. Create no merge commit.

Push only:
git push origin refs/heads/main:refs/heads/main

Monitor all four checks for that SHA’s main-push runs, again bounded to 20 minutes.

Report failures or pending checks accurately. Do not automatically revert, rewrite history or make fixes.

7. Handoff

Return:
- Commit SHA, parent, subject and identity.
- Prompt-history additions.
- Checks and scan results.
- Feature and main workflow/job links and conclusions.
- Observed test summaries, or log-access limitations.
- Before/after refs and final Git status.
- COMPLETE incremental diff against the accepted staged tree, excluding prompts.md.
- Note that recording eventual main publication results requires a later documentation update.

Compose, dead-job reconciliation/projection, M3d–M3f and overall M3 acceptance remain pending.

Do not change source, tests, migrations, dependencies or workflows.
Do not force-push, amend, rebase, squash, delete branches or push tags.
Do not start Docker or contact a local database.
Do not begin M3d.
````

**Preflight note (written before this commit and any push):**
- **Verified state:**
  - branch `feat/document-revisions`, with HEAD, upstream and the fresh remote branch all at `8646b75`;
  - staged tree `49ed2b96fb66a13e6bed5a66f3e5f77204189362` (recorded as the accepted tree), with exactly the five authorized files staged and nothing unstaged or untracked;
  - the expected origin;
  - local and fresh remote `main` at `dd26c70`, an ancestor of HEAD;
  - effective author and committer email `257921624+mathewmljourney93@users.noreply.github.com`.
- **Correction:** in `docs/plan.md`, the verification-plan result now says that the PostgreSQL integration tests listed above passed in the CI integration job at `8646b75` (`133 passed, 819 deselected`). It also says that the database-independent tests, including the controlled uncertain-commit simulations, ran in the verify jobs and not against PostgreSQL. Every other non-history file is byte-identical to the accepted tree, and the "not yet merged into `main`" wording stays, which is truthful before publication.
- **Checks before the commit:** staged paths, the incremental diff against the accepted tree, private content and identity are inspected; `git diff --cached --check` and the staged Gitleaks scan are run. After the commit, a full-history Gitleaks scan runs before any push. No application tests or builds are re-run (documentation only). Exact results are in the session handoff.
- **Authorization order:**
  1. Push only `feat/document-revisions` (`git push origin refs/heads/feat/document-revisions:refs/heads/feat/document-revisions`, with git's own exit status, not piped).
  2. Monitor Ubuntu verify, Windows verify, PostgreSQL integration and the full-history secret scan for the exact new SHA, for at most 20 minutes.
  3. Only if all four pass, re-check that remote `main` is still `dd26c70`, that the remote branch equals the verified SHA, that `main` is its ancestor, and that local `main` equals `origin/main`.
  4. Fast-forward `main` with `git merge --ff-only`, push only `main`, and monitor its four checks for at most 20 minutes.
- **Stop conditions:** any mismatch, failed scan, failed or pending check, or non-fast-forward situation stops the work before `main` is touched; there is no automatic fix, repush, revert or history rewrite. No force-push, amend, rebase, squash, branch deletion, tags, Docker or database contact. M3d is not started.
- **Not yet done when this note was written:** the push, CI and `main` results are reported in the session handoff; recording them here needs a later documentation update.

**Publication outcome for Prompt 75 (recorded later, with Prompt 76):**
- **Commit:** `6f8ffde` (`6f8ffded2e5c7b2ed69e37700dc03f20f5e24482`, parent `8646b75`, noreply identity) changed exactly the five authorized files. Compared with the accepted tree `49ed2b9…`, only the plan sentence and `prompts.md` differed. The staged and full-history Gitleaks scans found no leaks (30 commits).
- **Feature push:** `git push origin refs/heads/feat/document-revisions:refs/heads/feat/document-revisions`, run directly, reported `8646b75..6f8ffde` with git's own exit status 0.
- **Feature CI:** [ci run 38286402740](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38286402740) and [secret-scan run 38286402386](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38286402386) succeeded for `6f8ffde`, with every job and step successful.
- **Fast-forward:** a fresh fetch confirmed remote `main` at `dd26c70`, the remote branch at `6f8ffde`, ancestry, local `main` equal to `origin/main`, and a clean tree. `main` was fast-forwarded with `git merge --ff-only`, creating no merge commit.
- **Main push:** `git push origin refs/heads/main:refs/heads/main` reported `dd26c70..6f8ffde`, exit status 0.
- **Main CI:** [ci run 38286702295](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38286702295) and [secret-scan run 38286702205](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38286702205) succeeded on `main` for `6f8ffde`. Job logs returned HTTP 403 in that session, so no counts were observed there.
- **Reviewer-observed results (later):** the external reviewer retrieved the main-run logs:
  - Ubuntu `819 passed, 133 skipped in 18.04s`;
  - Windows `818 passed, 134 skipped in 18.87s`;
  - PostgreSQL `133 passed, 819 deselected in 38.29s`;
  - secret scan: 30 commits scanned, no leaks found.

The historical "not yet merged" statements in Prompts 74 and 75 were true when written and are left unchanged.

## Prompt 76: Record M3c main verification and specify M3d ingestion

- **Stage:** Documentation and specification only, on branch `docs/m3d-ingestion-spec` (staged and uncommitted for review; no commit, push or merge)
- **Date:** 2026-10-13 (session date)
- **Numbering:** 76 is the next unused number after Prompt 75. No earlier read-only handoff from this session is left unrecorded: the read-only diff handoff was recorded as Prompt 70.

````text
Prompt 76 — Record M3c main verification and specify M3d ingestion

Work only inside D:\Claude\evidenceguard_agentic_rag. Follow CLAUDE.md and the existing architecture decisions.

This is a documentation and specification task. Do not implement M3d, commit, push, merge, rewrite history, start Docker, contact a database, install tools, or modify global configuration.

1. Verify the starting state before editing

Expected:
- Branch: main
- HEAD and origin/main:
  6f8ffded2e5c7b2ed69e37700dc03f20f5e24482
- Origin:
  https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git
- Clean working tree, nothing staged or untracked.
- Effective author and committer email:
  257921624+mathewmljourney93@users.noreply.github.com

Check remote main read-only. If the state differs, stop and report the difference without changing anything.

Read CLAUDE.md, the relevant plan sections, ADR-0007 through ADR-0009, and the existing revision, document-store, fenced-job and worker interfaces. Inspect the existing code before proposing interfaces.

Create docs/m3d-ingestion-spec from the verified HEAD.

2. Record verified M3c publication

Update README.md, ADR-0009, docs/plan.md and docs/threat-model.md where necessary to record that M3c was fast-forwarded onto main at 6f8ffde.

The external reviewer independently retrieved these results for that exact SHA:

Main CI:
https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38286702295

- Ubuntu job 114936682783:
  819 passed, 133 skipped in 18.04s
- Windows job 114936682699:
  818 passed, 134 skipped in 18.87s
- PostgreSQL integration job 114936682399:
  133 passed, 819 deselected in 38.29s

Main secret scan:
https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38286702205
- Job 114936700730:
  30 commits scanned, no leaks found

Both runs completed successfully on main with head_sha
6f8ffded2e5c7b2ed69e37700dc03f20f5e24482.

Attribute these observations to the external reviewer; do not claim you retrieved the logs or ran the suite yourself. Preserve earlier SHA-specific evidence as historical evidence.

M3c is verified and on main. Compose, M3d–M3f and overall M3 acceptance remain pending.

3. Write a reviewable M3d specification in docs/plan.md

Keep the accepted architecture and scope:
- Only UTF-8 text/plain and text/markdown.
- Deterministic chunker v1.
- A chunks table introduced by migration 0004, following 0003.
- The first production worker handler: ingest_revision.
- No embeddings, retrieval, model calls, upload endpoints or document endpoints in this slice.

Specify the following precisely. Distinguish existing decisions from proposed defaults needing review. Resolve routine choices with a concrete recommendation; do not leave a list of competing implementations.

A. Parsing and provenance

Define exact behavior for:
- Markdown headings and section paths.
- Paragraph boundaries and plain-text blank lines.
- Approximately 2,500-character chunks, with no overlap.
- Oversized paragraphs and oversized table rows.
- Markdown tables, including splitting by rows and repeating headers.
- LF and CRLF, BOMs, Unicode and whitespace.
- Empty or whitespace-only documents.
- Unsupported or malformed input.

Define whether the character target is a hard limit or a packing target.

Define source line numbering and how chunk text maps back to the original stored source. Repeated table headers must not create a false claim that generated chunk text is one contiguous verbatim source passage.

Preserve the original uploaded-byte hash and size. Explain any derived-text normalization separately. The parser is not a Markdown renderer, does not execute content and performs no network or filesystem access.

Provide small input/output examples covering headings, long text, tables and line provenance.

B. Chunk contract and database schema

Specify exact columns, types, constraints and indexes, including:
- Tenant and revision identity.
- Chunker version and ordinal.
- Deterministic UUID5 identity using tenant, revision, chunker version and ordinal.
- The fixed UUID namespace and ordinal convention.
- Chunk text and section/line provenance.
- Composite tenant-scoped foreign keys and uniqueness.
- An explicit, consistent home for chunker_version.
- Immutability after activation.
- Whether any content digest or manifest is required to verify a complete chunk set.

Re-chunking active revisions is out of scope.

Migration 0004 must not introduce embeddings or create the vector extension. Explain upgrade/downgrade order and migration-head test updates.

C. Persistence operations and fencing

Specify tenant-scoped source loading without exposing content through repr, logs or exception messages.

Specify chunk writes through the existing FencedSession and job fence:
- Parse outside database locks.
- Keep write transactions bounded.
- Check cancellation and current ownership at the required boundaries.
- Make retries idempotent.
- Verify that an existing deterministic chunk matches the expected immutable content and provenance; do not silently overwrite or ignore a mismatch.
- Define how partial writes resume after a crash.
- Prevent activation until the entire expected chunk set is verified.
- Preserve document/revision lock ordering and fresh ownership checks from M3c.

Explain the exact final transaction that verifies completeness, activates or supersedes the revision, and completes the job through ctx.fenced(finish=True).

Do not redesign the worker’s cancellation or uncertain-commit semantics.

D. Production handler

Define:
- Exact job kind: ingest_revision.
- Payload shape and validation.
- Idempotency key derived from revision identity.
- Registry registration and installed-wheel behavior.
- Processing of pending, processing, failed, active and superseded revisions.
- Retryable versus permanent failure classification.
- Fixed RevisionFailureCode and JobErrorCode mappings.
- Cancellation, lease loss, partial writes, reclaim and uncertain commit behavior.

Preserve the existing two-transaction permanent-failure protocol unless proposing a separately reviewed interface change. Never raise PermanentJobError inside the fenced block that must commit the revision’s failure.

Already-failed revisions must not be parsed again.

Describe behavior when a different valid job refers to an already-settled revision, and explain how malformed or cross-tenant payloads fail safely.

E. Dead-job truthfulness

A dead job can leave a revision pending or processing. Select and specify a concrete approach:
- reconciliation, or
- a truthful derived status projection for M3e.

Explain the authoritative stored revision status, the related job status, lease expiry and what users will eventually see. Do not imply a currently live lease guarantees progress.

If implementation belongs in M3e, explicitly assign it there with acceptance tests and retain it as a blocker for overall M3 acceptance. Do not leave this responsibility unspecified.

F. Verification and implementation boundaries

List intended files and meaningful tests:
- Pure parser/chunker determinism and provenance.
- Tenant-disjoint chunk IDs for identical source bytes.
- Validation and privacy.
- Idempotent chunk persistence and conflicting existing chunks.
- Real PostgreSQL constraints and migration checks.
- Partial-write crash and resume.
- Stale worker and lease expiry during lock waits.
- Completeness enforcement before activation.
- Atomic activation and job completion.
- Permanent-failure crash gap.
- Cancellation and uncertain commit.
- Real worker execution with the registered production handler.
- Installed-wheel packaging.

Separate database-independent tests from real PostgreSQL tests. PostgreSQL verification remains pending an authorized publication and successful CI.

Do not claim any M3d implementation, test result or performance measurement exists yet.

4. Prompt history

Use the next unused prompt number; expect 76, but verify it.

Append this prompt verbatim to prompts.md, followed by an outcome note describing the actual work and verification.

Record the Prompt 75 publication outcome and the reviewer-observed main results above as a later outcome update. Preserve all earlier text byte-for-byte; do not rewrite historical “not yet merged” statements inside old prompt entries.

If any earlier read-only handoff continuation remains unrecorded, append an accurately labelled note without inventing its verbatim text.

5. Verify and stage for review

Allowed tracked changes:
- README.md
- docs/decisions/0009-document-revisions.md
- docs/plan.md
- docs/threat-model.md
- prompts.md

No application, test, migration, dependency or workflow changes.

Check documentation consistency, relative links and anchors, private content, git diff --cached --check and the staged Gitleaks scan.

Application tests and builds are unnecessary for this documentation-only task.

Leave all changes staged and uncommitted.

6. Review handoff

Provide:
- A concise explanation of the recommended M3d design and proposed defaults.
- Verification commands and actual results.
- Branch, HEAD, staged tree, staged paths and working-tree status.
- The COMPLETE staged diff excluding prompts.md, directly in fenced diff blocks.
- Split at file boundaries into numbered parts if necessary. Do not truncate or substitute summaries.
- If response limits prevent completion, save the complete diff under .local/ and clearly identify which inline parts remain to be supplied.

Nothing is authorized to be committed, pushed or merged.
````

**Outcome note (written before review; the changes are staged and uncommitted):**
- **Starting state verified:** branch `main` with HEAD, `origin/main` and a fresh read-only `git ls-remote` all at `6f8ffde`; the expected origin; a clean tree with nothing staged or untracked; and the noreply identity. Branch `docs/m3d-ingestion-spec` was created from that HEAD.
- **Read before editing:** `CLAUDE.md`, the plan's data-model, lifecycle, retrieval, M3 and M3c sections, and ADR-0007 to ADR-0009. Also the existing interfaces in:
  - `evidenceguard_domain.revisions` and `evidenceguard_domain.jobs`;
  - `evidenceguard_persistence.documents` and `evidenceguard_persistence.jobs` (`enqueue`, `FencedSession`, `recheck_ownership`);
  - `evidenceguard_worker` (`context`, `registry`, `handlers` and the runtime's outcome mapping);
  - the import-boundary and packaging tests.
- **M3c publication recorded:** `README.md`, ADR-0009, `docs/plan.md` and `docs/threat-model.md` record the fast-forward onto `main` at `6f8ffde` and the reviewer-retrieved main CI results, attributed to the external reviewer. The branch evidence at `8646b75` is kept as history.
- **M3d specification added (proposed, not implemented):** in `docs/plan.md`, it separates decided items from proposed defaults and covers:
  - parsing and provenance, with exact line, offset, BOM, heading, fence, table and size rules and four normative examples;
  - the `chunk_sets` and `chunks` schema in migration `0004`, with the fixed UUID namespace literal and a completeness manifest;
  - fenced, bounded and idempotent chunk writes with conflict verification and crash resume;
  - completeness checked in M3c's activation transaction through a new optional `before_settle` argument;
  - the `ingest_revision` handler, with its payload, registry and failure classification, new revision failure codes all mapped to `PERMANENT_FAILURE`, and the unchanged two-transaction failure protocol;
  - a derived `ingestion_state` projection for dead jobs, assigned to M3e as a blocker for overall M3 acceptance;
  - the verification plan, split into database-independent and PostgreSQL tests.

  The examples' offsets and the example chunk IDs were computed with Python's standard library in this session.
- **Checks:** relative links and anchors in the four edited documents, consistency and private-content searches, `git diff --cached --check` and the staged Gitleaks scan. Exact results are in the session handoff. No application tests or builds were run (documentation only).
- **Not done:** no M3d code, migration, test or measurement exists. Nothing was committed, pushed or merged. No Docker, database contact or global configuration change.
- **Review status:** pending.

## Prompt 77: Correct the M3d specification (interrupted; exact text unavailable)

- **Stage:** Specification correction, on branch `docs/m3d-ingestion-spec`. Interrupted by the session usage limit before verification, prompt-history update or staging.
- **Date:** 2026-10-13 (session date)
- **Exact text unavailable:** the interrupted session did not record Prompt 77, and its text could not be recovered in the resuming session (Prompt 78). The only project-local material is the session's own scripts under `.local/p77/`. This entry is therefore an honestly labelled interruption note, **not** the verbatim prompt. Prompt 78 restates the correction requirements (INSERT return values, serializing chunk writes with lifecycle changes, parser boundary rules, binding completeness to the current attempt), and those requirements were used to complete the work.

**Outcome note (written in Prompt 78, from the recovered state):**
- **Work present on recovery:** `.local/p77/apply.py` had run and left `docs/plan.md` with **unstaged** changes (174 insertions, 65 deletions) to the M3d section: rewritten line, block and chunk rules, normative examples 5–9, `chunk_sets` return values and the canonical manifest encoding, the lock-protocol and serialization rules, the bound `ExpectedChunkSet` callback, and the handler's refusal handling and test lists.
- **Not done by the interrupted session:** no verification, no prompt-history entry and no staging. The staged tree was still the Prompt 76 tree `fc9e360`.
- **Completion:** in Prompt 78 (below).

## Prompt 78: Resume interrupted Prompt 77 — recover, complete and hand off

- **Stage:** Recovery and specification correction, documentation only, on branch `docs/m3d-ingestion-spec` (staged and uncommitted for review; no commit, push or merge)
- **Date:** 2026-10-13 (session date)
- **Numbering:** 77 was unused on recovery and is taken by the interruption note above; 78 is the next unused number.

````text
Resume interrupted Prompt 77 — recover, complete and hand off

This is a fresh Claude Code session.

Work only inside D:\Claude\evidenceguard_agentic_rag. Read CLAUDE.md first.

Load only the relevant M3d section of docs/plan.md and the recent prompt-history entries needed for this task. Do not load the entire prompts.md or previous session transcript.

Our workflow:
- Claude performs the work locally.
- Mathew brings the complete diff and results to an external reviewer.
- Implementation and corrections remain staged and uncommitted until reviewed.
- Commit, push and merge require explicit authorization.

No implementation, commit, push, merge, history rewrite, Docker, database contact, installation or global configuration change is authorized by this prompt.

1. Recover the actual repository state

The previous session hit its usage limit during Prompt 77.

Its last visible action successfully ran:
python .local/p77/apply.py

It reported changes to docs/plan.md:
174 insertions and 65 deletions.

Verification, prompt-history updates and staging may be incomplete.

Do not rerun that script or repeat corrections blindly.

Inspect:
- branch, HEAD and origin;
- git status;
- staged paths and unstaged changes;
- current staged tree;
- staged and unstaged diffs;
- recent entries at the end of prompts.md;
- existing .local/p77/ files, if present.

Expected branch:
docs/m3d-ingestion-spec

Expected HEAD:
6f8ffded2e5c7b2ed69e37700dc03f20f5e24482

Expected origin:
https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git

Expected repository-local identity:
257921624+mathewmljourney93@users.noreply.github.com

The staged tree before Prompt 77 was:
fc9e360b2f643b4689f591db5a76b05b035a6d9e

That baseline contained:
README.md
docs/decisions/0009-document-revisions.md
docs/plan.md
docs/threat-model.md
prompts.md

Partial staged or unstaged edits to docs/plan.md and prompts.md are expected after the interruption. Those alone are not a starting-state failure.

If the branch or HEAD differs, or unrelated tracked files changed, stop and report the discrepancy. Preserve existing work.

Record the recovered state before editing. Do not reset, restore or discard work to recreate the baseline.

2. Recover and complete Prompt 77

Read Prompt 77 from prompts.md if recorded. Otherwise inspect available project-local recovery material.

If its exact original text is unavailable, the correction requirements below are sufficient to complete the task. Do not invent a verbatim historical prompt.

Inspect the edits already applied. Complete only missing or incorrect corrections.

A. Correct INSERT return values

chunk_sets has a composite primary key and no id column.

Specify valid RETURNING columns separately for write_chunk_set and write_chunks. Do not add an artificial id column merely to match earlier wording.

Define immutable fields compared on conflict. Creation timestamps are metadata, not regenerated expectations for retries.

Errors must use fixed messages without source content.

B. Serialize chunk writes with lifecycle changes

The original proposal checked processing status without locking the revision. A job lock alone does not serialize different jobs referring to the same revision.

Specify a protocol compatible with M3c:
- job lock from the fence;
- document lock;
- required revision locks in ascending ID order;
- fresh ownership check after lock waits;
- fresh processing-status check under those locks;
- insert and verify the batch;
- fresh ownership check after unique-index waits and before returning.

Use existing M3c locking machinery where appropriate.

Required behavior:
- If the writer wins the locks, its permitted batch commits before settlement proceeds.
- If activation or failure wins, the writer sees the new status and writes nothing.
- No chunk or chunk-set insertion occurs after settlement.
- A stale attempt changes nothing.

Specify how ChunkWriteRefusedError leads to a fresh status read and the correct settled/failed branch, without trying to fail an already-settled revision.

Keep parsing outside transactions and locks.

Add planned PostgreSQL cases for:
- writer versus activation using different jobs for the same revision;
- writer versus failure;
- insertion attempts after settlement;
- lease expiry during these lock waits;
- rollback of a refused batch.

C. Complete parser boundary rules

Clarify:
- Paragraphs stop before recognized headings, fence openings and table starts, even without a blank line.
- Fence-closing recognition is precise.
- Consecutive headings are an explicit exception to the general heading boundary rule, with defined chunk membership and section paths.
- Oversized heading lines have a defined splitting rule.
- Oversized table headers and header-only tables are handled within every size limit.
- Every emitted piece reconstructs exactly from its documented source spans.
- Empty-document and split-whitespace predicates are explicit and consistent with blank-line handling.
- Omitted separators never lose non-whitespace source characters.

Add normative examples and planned tests for:
- prose immediately followed by a heading;
- consecutive headings;
- oversized headings;
- oversized headers and header-only tables;
- whitespace-only source under the chosen predicate.

Preserve existing correct examples and the fixed UUID namespace.

D. Bind completeness to the current attempt

Specify how the final callback receives or captures this attempt’s expected manifest, count and chunker version. Include an unambiguous illustrative call.

Define canonical manifest JSON encoding:
- key ordering;
- separators;
- Unicode escaping;
- UUID representation;
- null representation;
- ordinal ordering.

The final check verifies:
- expected chunker version;
- expected chunk count and exact ordinal set;
- stored set manifest;
- manifest reconstructed from stored chunk fields;
- equality with this attempt’s independently computed manifest.

Explain that digest-only verification relies on application immutability and does not protect against privileged database modification.

Preserve the proposed optional callback interface and atomic activation/job-success transaction. Do not redesign worker cancellation or uncertain-commit semantics.

3. Preserve accepted scope and content

The M3c publication documentation is accepted.

Relative to baseline fc9e360:
- README.md, ADR-0009 and docs/threat-model.md remain byte-identical.
- Only docs/plan.md and prompts.md may change for the correction.
- CLAUDE.md may additionally change for the session guidance below.

Keep these M3d proposals:
- text/plain and text/markdown only;
- text-md-v1;
- 2,500-character prose limit;
- 4,000-character absolute chunk limit;
- 1,000-character repeated-header limit;
- 4,096 chunks per revision;
- batches bounded by 200 chunks and 512,000 code points;
- chunk_sets and chunks in migration 0004;
- no embeddings, extensions, retrieval or model calls;
- existing worker and two-transaction permanent-failure semantics;
- M3e derived dead-job projection, required before overall M3 acceptance.

M3d remains proposed and unimplemented until the corrected specification is accepted.

4. Add persistent session guidance to CLAUDE.md

Add a concise “Session management” section, without duplicating existing rules:

- Recommend a fresh session at the boundary between milestone slices, after the current slice has a reviewable handoff.
- Recommend a fresh session when Claude Code reports that a large expired context will be re-cached, or when context is dominated by unrelated completed work.
- Use any available context/usage indicators as evidence. Never invent a token count or claim a measured saving.
- State the recommendation explicitly: “Start a new Claude session before the next task,” with a brief reason.
- Before recommending a switch during unfinished work, provide a recovery handoff: branch, HEAD, staging and working-tree state, completed work, outstanding work and the next prompt.
- Keep immediate corrections in the current session when its relevant context remains useful.
- Starting a new session never authorizes discarding changes or rewriting Git history.
- In a fresh session, read project instructions and targeted relevant files. Avoid loading the entire prompt archive by default.

This is guidance, not a mandatory interruption in the middle of useful work. Finish the authorized task and its handoff unless a real limit prevents it.

5. Prompt history

Verify the next unused number.

Do not append Prompt 77 twice.

If Prompt 77 is absent:
- record it verbatim only if its exact original text is available;
- otherwise append an honestly labelled interruption note explaining that the exact text was unavailable in this session.

Append this prompt verbatim once under the next unused number.

Preserve all earlier history byte-for-byte.

Record:
- the interruption;
- work already present on recovery;
- corrections completed after recovery;
- session guidance added;
- actual verification results;
- that M3d remains unimplemented and unaccepted.

Do not claim tests, publication or review acceptance that did not happen.

6. Verify and stage for review

Allowed staged paths:
CLAUDE.md
README.md
docs/decisions/0009-document-revisions.md
docs/plan.md
docs/threat-model.md
prompts.md

Check:
- corrected specification consistency and normative examples;
- relative links and anchors;
- private content;
- byte identity of the three unchanged documents;
- git diff --cached --check;
- staged Gitleaks scan.

No application tests or builds are necessary for documentation-only changes.

Leave the authorized files staged and uncommitted. Do not stage .local/ artifacts or unrelated files. Report any remaining unstaged or untracked files.

7. Complete review handoff

Provide:
- recovered starting state;
- what was already completed before interruption;
- what changed in this session;
- actual verification commands and results;
- branch, HEAD, final staged tree and staged paths;
- remaining unstaged or untracked files;
- prompt-history additions;
- whether a fresh session is recommended before the next task, and why.

Include the COMPLETE incremental diff against:
fc9e360b2f643b4689f591db5a76b05b035a6d9e

Exclude prompts.md, but include the full CLAUDE.md change.

Print the diff directly in fenced diff blocks, split into numbered parts at file boundaries if necessary. Do not truncate or replace it with a summary.

Use .local/ only as a fallback and identify any inline parts still missing.

Nothing may be committed, pushed, merged or implemented.
````

**Outcome note (written before review; the changes are staged and uncommitted):**
- **Recovered starting state (verified before editing):** branch `docs/m3d-ingestion-spec`, HEAD `6f8ffde`, the expected origin and noreply identity. The staged tree was exactly the Prompt 76 tree `fc9e360`. The only unstaged change was `docs/plan.md` (174 insertions, 65 deletions) from `.local/p77/apply.py`; `prompts.md` had no Prompt 77 entry, and there were no untracked files. That script was not rerun.
- **Recovered edits kept:** they already covered most of A–D (see the Prompt 77 note), and were checked against the M3c code: `_lock(session, job, *, include_active)` performs exactly the documented job → document → revisions → `recheck_ownership` sequence, and `recheck_ownership`, `RevisionSnapshot` and `InvalidRevisionTransitionError` exist as named.
- **Corrections completed in this session (`docs/plan.md`):**
  - a leading BOM is excluded from line 1's content for every rule, so a BOM-only line is blank and the empty-document predicate agrees with blank-line handling;
  - the oversized-line rule now trims leading and trailing spaces and tabs before cutting, ends when the remainder fits, and never emits an empty or whitespace-only piece;
  - runs and pieces of a split block are never packed with neighbouring blocks, and a split heading run keeps the run's section path;
  - `fail_revision` racing a settlement raises `InvalidRevisionTransitionError`, which the handler catches outside the block and answers with the same fresh status read; the re-read happens at most once per attempt;
  - example 9 spells NBSP as an escape instead of an invisible literal, and gains a BOM-only empty case;
  - matching planned tests.
- **Session guidance added:** a "Session management" section in `CLAUDE.md`.
- **Checks run in this session:** see the session handoff for exact commands and results. They covered:
  - every normative example's offsets, slices and lengths, the oversized-line splits, the namespace literal and both example chunk IDs, recomputed with Python's standard library (all matched);
  - relative links and anchors, the private-content search, and byte identity of `README.md`, ADR-0009 and `docs/threat-model.md` with `fc9e360`;
  - `git diff --cached --check` and the staged Gitleaks scan.

  No application tests or builds were run (documentation only).
- **Not done:** M3d remains **proposed, unimplemented and unaccepted**. No code, migration or test exists. Nothing was committed, pushed or merged. No Docker, database contact, installation or global configuration change.
- **Review status:** pending.

**Review note (recorded in Prompt 79):**
- **Accepted:** the external reviewer accepted the M3d specification from Prompt 76 together with the corrections recovered and completed in Prompts 77–78, subject to two final clarifications made in Prompt 79 (source coverage, and chunk insert conflicts). The session-management guidance in `CLAUDE.md` was also accepted.
- **How it was reviewed:** the reviewer inspected the diffs supplied in the handoffs. The reviewer had previously checked the UUID examples and the table offsets independently. The reviewer did not run the project tests or the documentation checker; the documentation checks and secret-scan results were reported by Claude.
- **Still pending:** the M3d implementation and all of its verification.

## Prompt 79: Accept and commit the M3d specification locally

- **Stage:** Documentation acceptance and a local commit on branch `docs/m3d-ingestion-spec` (no push or merge)
- **Date:** 2026-10-13 (session date)
- **Numbering:** 79 is the next unused number after Prompt 78; verified before appending.

````text
Prompt 79 — Accept and commit the M3d specification locally

Work only inside D:\Claude\evidenceguard_agentic_rag. Follow CLAUDE.md.

The external reviewer accepts the M3d specification from Prompt 76 plus the recovered corrections in Prompt 78, subject to the two narrow clarifications below. The session-management guidance is also accepted.

This authorizes a local documentation commit only. No implementation, push, merge, history rewrite, Docker, database contact, installation or global configuration change.

1. Verify the starting state

Expected:
- Branch: docs/m3d-ingestion-spec
- HEAD:
  6f8ffded2e5c7b2ed69e37700dc03f20f5e24482
- Staged tree:
  43baa6b17e88872548fbd9761fea963cd50e0048
- Exactly six staged paths:
  CLAUDE.md
  README.md
  docs/decisions/0009-document-revisions.md
  docs/plan.md
  docs/threat-model.md
  prompts.md
- Nothing unstaged or untracked.
- Expected origin:
  https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git
- Effective author and committer email:
  257921624+mathewmljourney93@users.noreply.github.com

If anything differs, stop and report it without changing anything.

Record the accepted staged tree before editing.

2. Apply two final specification clarifications

A. Source coverage

The whitespace predicate intentionally contains only space and tab. LF and CRLF terminators are excluded from line content and may be omitted between chunks.

Correct “Only whitespace is ever omitted” and the coverage invariant to distinguish:
- a leading BOM;
- LF and CRLF line terminators;
- permitted omitted spaces and tabs;
- all remaining source characters.

The invariant must require every source character other than these permitted omissions to appear exactly once in the ordered body spans. Repeated headers are additional context copies, not additional body coverage.

Preserve lone CR, NBSP and other characters treated as non-whitespace.

Change “Coverage invariant (tested)” to wording that clearly identifies a planned test. No M3d tests exist yet.

Add a planned coverage case with multiple chunks separated by LF and CRLF, proving the permitted omissions and preservation of every remaining character.

Do not change the parser examples or whitespace predicate.

B. Chunk insert conflicts

Remove the absolute claim that the chunk ID and ordinal uniqueness constraints always conflict together.

Specify:
- ON CONFLICT DO NOTHING can suppress a conflict on either unique key.
- If an expected insert returns no ID, perform the existing tenant/revision/version/ordinal lookup.
- If the expected row is absent, or any immutable field differs, raise fixed ChunkConflictError.
- Never treat a missing lookup result as a successful idempotent retry.
- Never overwrite the conflicting row.

Add a planned test for a suppressed insert conflict where the expected tuple lookup finds no row. This may use a controlled unit double or deliberately conflicting test row; do not claim such a test has run.

Preserve the accepted schema and deterministic ID formula.

3. Mark specification acceptance accurately

Make only narrow wording changes in README.md and docs/plan.md:
- M3d specification accepted at review.
- Implementation pending.
- Engineering defaults accepted as initial choices, not measured performance results.

Record acceptance of:
- parser grammar and provenance rules;
- the chunk limits and batch bounds;
- chunk_sets and chunks;
- deterministic IDs and canonical manifests;
- shared lifecycle locking;
- the optional completeness callback;
- the handler and failure protocol;
- the M3e derived status projection and its acceptance obligation.

M3d is not implemented. Compose and overall M3 acceptance remain pending.

Keep CLAUDE.md, ADR-0009 and docs/threat-model.md byte-identical to the accepted tree.

Do not redesign anything else.

4. Prompt history

Append a review note under Prompt 78 recording:
- acceptance of the original specification and recovered corrections, with these final clarifications;
- acceptance of session-management guidance;
- that the reviewer inspected the supplied diffs;
- that the reviewer previously checked UUID examples and table offsets independently;
- that the reviewer did not run project tests or the documentation checker;
- that documentation checks and secret-scan results were reported by Claude;
- that implementation and its verification remain pending.

Append this prompt verbatim using the next unused number; expect 79 and verify it.

Preserve earlier history byte-for-byte.

Add a truthful pre-commit note. Do not pre-record a successful commit or include the future commit’s own SHA in its content.

5. Verify and commit locally

Confirm:
- only the six authorized paths are staged;
- no .local/ or build artifacts are staged;
- the three unchanged files are byte-identical to the accepted tree;
- the complete incremental diff contains only the authorized clarifications, acceptance wording and prompt history;
- documentation links and anchors resolve;
- no private content is introduced;
- git diff --cached --check passes;
- staged Gitleaks scan passes;
- effective author and committer use the noreply identity.

No application tests or builds are required for documentation-only changes.

Commit with subject:
docs: record accepted M3d ingestion specification and session guidance

Preserve the existing co-author attribution convention.

After the commit:
- verify parent, identity and committed paths;
- run the full-history Gitleaks scan;
- confirm a clean working tree;
- confirm main was not changed.

Do not push.

6. Handoff

Provide:
- commit SHA, parent, subject and identity;
- committed paths;
- actual verification results;
- prompt-history additions;
- final branch and working-tree status;
- confirmation that nothing was pushed or implemented.

Include the COMPLETE incremental diff against
43baa6b17e88872548fbd9761fea963cd50e0048,
excluding prompts.md, directly in fenced diff blocks.

Split into numbered parts if needed. Do not truncate or replace the diff with a summary.

End with:
“Start a new Claude session before M3d implementation.”

Explain that the accepted specification is now on disk and the implementation prompt will provide the new session’s scope. Do not start implementation or invent its authorization.
````

**Pre-commit note (written before the commit; the commit's own SHA is not recorded here):**
- **Starting state verified:** branch `docs/m3d-ingestion-spec`, HEAD `6f8ffde`, staged tree `43baa6b` with exactly the six expected paths, nothing unstaged or untracked, the expected origin, and the noreply author and committer identity. The accepted tree was recorded under `.local/` before editing.
- **Clarifications applied (`docs/plan.md`):**
  - source coverage separates a leading BOM, LF and CRLF terminators, permitted spaces and tabs, and every remaining character (lone CR and NBSP included), and is now marked as a planned test;
  - the chunk insert rule no longer claims the two unique keys always conflict together. A returned-ID gap leads to the tuple lookup, and a missing row or any differing field raises `ChunkConflictError`, without overwrite;
  - matching planned tests: a coverage case with LF- and CRLF-separated chunks, and a suppressed conflict whose lookup finds no row.

  The parser examples, the whitespace predicate, the schema and the ID formula are unchanged.
- **Acceptance wording:** `README.md` and `docs/plan.md` record the specification as accepted at review, with its implementation pending and its limits accepted as initial engineering defaults, not measured results. `CLAUDE.md`, ADR-0009 and `docs/threat-model.md` are byte-identical to `43baa6b`.
- **Checks run before this entry was written:** relative links and anchors (54 links, 0 problems), the private-content search of the added lines (no matches) and byte identity of the three unchanged files. `git diff --cached --check`, the staged Gitleaks scan and the post-commit checks run after this entry is staged; their results are in the session handoff.
- **Not done:** no M3d implementation, test or measurement. Nothing pushed or merged. No Docker, database contact, installation or global configuration change.

**Outcome note for Prompt 79 (recorded in Prompt 80):** the documentation was committed locally as `a3e15465be71893627121dca75be121e48613d49` on `docs/m3d-ingestion-spec`, with parent `6f8ffde` and the noreply author and committer identity. It contains the six authorized paths. After the commit, the full-history Gitleaks scan reported 31 commits scanned and no leaks found, the working tree was clean, and `main` stayed at `6f8ffde`. Nothing was pushed.

## Prompt 80: Implement M3d ingestion and revise session guidance

- **Stage:** Implementation on branch `feat/document-ingestion`, created from `a3e1546` (staged and uncommitted for review; no commit, push or merge)
- **Date:** 2026-10-13 (session date)
- **Numbering:** 80 is the next unused number after Prompt 79.
- **Interrupted:** the session hit its weekly usage limit after the installed-wheel checks and before documentation, prompt history, staging and the handoff. It was resumed in the same session as Prompt 81 below, so the text below is the exact prompt as received.

````text
Prompt 80 — Implement M3d ingestion and revise session guidance

Work only inside D:\Claude\evidenceguard_agentic_rag. Follow CLAUDE.md, subject to the explicit session preference below.

This prompt authorizes M3d implementation, verification and staging for external review. It does not authorize any commit, push, merge, history rewrite, Docker startup or database contact.

1. Verify the starting state

Expected:
- Branch: docs/m3d-ingestion-spec
- HEAD:
  a3e15465be71893627121dca75be121e48613d49
- Parent:
  6f8ffded2e5c7b2ed69e37700dc03f20f5e24482
- Clean working tree, nothing staged or untracked.
- Origin:
  https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git
- Local main and origin/main:
  6f8ffded2e5c7b2ed69e37700dc03f20f5e24482

If anything differs, stop and report it without changing anything.

Create feat/document-ingestion from the verified HEAD.

Read the accepted M3d specification in docs/plan.md and the relevant existing domain, persistence, worker and packaging interfaces. Read only relevant prompt-history entries; do not load the entire archive.

2. Correct the session-management preference

Mathew explicitly rejects restarting after every milestone or after one or two prompts.

Update CLAUDE.md narrowly:
- Keep the current session through implementation and immediate reviews.
- Consider recommending a fresh session after roughly 20 substantial prompts, as a guideline rather than a hard cutoff.
- Recommend an earlier switch only when concrete context/usage evidence or a large expired-cache warning makes it worthwhile.
- A milestone boundary alone is not a reason to restart.
- Never invent token counts or measured savings.
- Before a necessary switch during unfinished work, provide a complete recovery handoff.
- Preserve targeted reading and preservation of saved work.

Remove or replace conflicting recommendations to restart automatically at milestone boundaries.

This explicit user preference supersedes the closing recommendation in Prompt 79. No new session is needed now.

3. Implement the accepted M3d specification

docs/plan.md is authoritative, including the corrections and acceptance from Prompts 77–79. Implement it without redesigning the architecture.

Scope:
- Deterministic text/plain and text/markdown parsing and chunking.
- evidenceguard_retrieval.chunking and its package registration.
- chunk_sets and chunks, migration 0004.
- Tenant-scoped source loading and fenced chunk persistence.
- Shared revision locking helper.
- Optional before_settle completeness callback.
- Production ingest_revision handler and registry.
- Fixed failure codes and existing worker failure protocol.
- Tests, ADR-0010 and accurate documentation.

No embeddings, vector extension, retrieval engine, model calls, upload/document endpoints, Docker work or M3e projection implementation.

The M3e projection remains explicitly assigned and required before overall M3 acceptance.

4. Preserve the critical contracts

Parser:
- Implement the accepted grammar, priority and boundary rules.
- Preserve exact source slices and separate repeated-header provenance.
- Enforce all accepted size, count and batch bounds.
- Use the accepted whitespace and permitted-omission rules.
- Preserve every other source character exactly once in ordered body spans.
- Implement all normative examples as meaningful tests.
- Keep original revision byte hash and size unchanged.

Persistence:
- Use the specified composite tenant references and constraints.
- Keep model and migration definitions aligned.
- Use fixed deterministic chunk IDs and canonical manifest encoding.
- Preserve idempotent insert-and-compare behavior.
- Missing conflict lookups and mismatched immutable fields raise ChunkConflictError.
- Never overwrite existing chunks.
- Serialize writers with activation/failure through the accepted job → document → revisions lock order.
- Re-check ownership with fresh database time after waits.
- Refuse all writes after settlement.
- Verify the complete set against the current attempt’s expected version, count and manifest before settlement.

Worker:
- Parse outside transactions and locks.
- Keep cancellation and lease checks at the accepted boundaries.
- Resume partial writes deterministically.
- Complete activation and job success together through ctx.fenced(finish=True).
- Preserve uncertainty after a lost commit acknowledgment.
- Preserve the two-transaction permanent-failure protocol.
- Never raise PermanentJobError inside the block that must commit revision failure.
- Already-failed or settled revisions are not parsed again.
- Handle settlement races with the specified fresh-status branches.
- Register the production handler and update empty-registry expectations accurately.

Protect content:
- No document text, credential values, submitted content or internal exception messages in logs, reprs or public errors.
- Use fixed error codes and messages.
- Keep existing privacy-safe logging behavior.

If the specification conflicts with an existing interface, identify the concrete conflict. Resolve routine implementation details within the accepted design; do not silently change architecture or broaden scope.

5. Verification

Run the repository’s relevant checks, including:
- uv sync --locked
- Ruff formatting and lint
- strict Mypy
- focused new tests
- full database-independent suite
- package build
- isolated installed-wheel checks outside the source tree
- offline rendering of migrations through 0004
- git diff --cached --check
- staged Gitleaks scan

Include a clean-wheel parser/manifest smoke check and production registry verification. Do not start the production worker against a database.

Write the real PostgreSQL tests specified in the plan, including:
- constraints and migration round trips;
- conflicting and idempotent writes;
- partial-write resume;
- writer/activation and writer/failure races;
- refusal after settlement;
- lease expiry during lock waits;
- completeness and expected-manifest mismatch;
- atomic finish and rollback;
- permanent-failure crash gap;
- execution through the registered production handler.

Do not run PostgreSQL tests locally or contact a database. Ensure database URLs cannot accidentally enable local integration work. Report PostgreSQL tests as collected/skipped or unrun, with exact observed results. Their execution remains pending authorized publication and CI.

Do not weaken existing assertions or remove historical migration coverage merely to make checks pass.

6. Documentation and prompt history

Add ADR-0010 explaining the final implementation, accepted decisions and limits.

Update README.md, docs/plan.md and docs/threat-model.md accurately:
- implemented locally and under review;
- no commit or publication;
- actual local verification;
- PostgreSQL and Linux verification pending for this version;
- Compose, M3e–M3f and overall M3 acceptance pending.

Record Prompt 79’s actual local commit outcome as a later history note.

Append this prompt verbatim using the next unused number; expect 80 and verify it. Preserve earlier history byte-for-byte.

Record the revised user session preference and actual implementation outcome. Never pre-record successful checks or review acceptance.

7. Stage and hand off for review

Stage only relevant implementation, test, configuration and documentation files. Do not stage .local/, environments, credentials, backups or build outputs.

Leave the work staged and uncommitted.

Provide:
- implementation decisions and any deviations;
- changed paths;
- actual verification commands and results;
- skipped/unrun verification and limitations;
- branch, HEAD, staged tree and working-tree status;
- prompt-history additions.

Include the COMPLETE staged diff excluding prompts.md directly in fenced diff blocks.

Split large output into numbered parts at file boundaries. Do not truncate, omit tests or replace source with summaries.

If response limits prevent delivering every part, save the complete diff under .local/, list all parts and clearly identify which remain to be supplied. Do not declare the handoff complete while parts are missing.

Keep this Claude session for the immediate review and corrections. Recommend a new session only under the revised user preference.

Nothing may be committed, pushed or merged.
````

**Outcome note (written in Prompt 81, before review; the work is staged and uncommitted):**
- **Starting state verified:** branch `docs/m3d-ingestion-spec` at `a3e1546` with parent `6f8ffde`, a clean tree, the expected origin, and local `main` and `origin/main` at `6f8ffde`. Branch `feat/document-ingestion` was created from that HEAD.
- **Session preference recorded:** `CLAUDE.md`'s "Session management" section now keeps the session through implementation and immediate reviews. It considers a fresh session after roughly 20 substantial prompts (a guideline), switches earlier only on concrete context or usage evidence or a large expired-cache warning, and treats a milestone boundary alone as no reason to restart. This replaces the milestone-boundary recommendation from Prompt 78 and supersedes the closing recommendation of Prompt 79.
- **Implemented before the interruption (this session):**
  - **Domain:** `evidenceguard_domain.chunks`, the shared chunk contract; and four new `RevisionFailureCode` values.
  - **Parser:** the pure chunker `evidenceguard_retrieval.chunking` in a new packaged `evidenceguard_retrieval`.
  - **Persistence:** the `ChunkSet` and `Chunk` models with migration `0004`; `evidenceguard_persistence.chunks`; and, in `documents`, the public `lock_revision_for_job` and the optional `before_settle`.
  - **Worker:** the `ingest_revision` handler, registered in `production_registry()`.
  - **Packaging:** `pyproject.toml` package registration and a CI installed-wheel registry assertion.
  - **Tests:** updated head pins, registry, boundary and failure-code tests. New `test_chunking.py`, `test_chunks.py`, `test_chunk_store.py` and `test_ingest_handler.py`, plus 45 PostgreSQL integration tests in `test_ingestion_postgres.py`.
- **Verification before the interruption (Prompt 80, reported in that session):**
  - the format, lint, strict type-check and full database-independent suite passed;
  - all nine normative examples matched the specification;
  - the isolated installed-wheel checks passed: parser/manifest smoke, production registry, offline `0004` upgrade/downgrade SQL, and both `--help` commands.
- **Completed in Prompt 81:** see that entry below.
- **Review status:** pending. Nothing is accepted, committed or published.

## Prompt 81: Resume interrupted Prompt 80 — finish M3d and provide the review handoff

- **Stage:** Recovery, documentation and the review handoff on branch `feat/document-ingestion` (staged and uncommitted; no commit, push or merge)
- **Date:** 2026-10-15 (session date)
- **Numbering:** 80 was unused on recovery and now holds the interrupted prompt above; 81 is the next unused number.

````text
Resume interrupted Prompt 80 — finish M3d and provide the review handoff

Work only inside D:\Claude\evidenceguard_agentic_rag. Read CLAUDE.md and the accepted M3d specification in docs/plan.md. Read only relevant recent prompt-history entries.

Prompt 80 was interrupted by the weekly usage limit. The last visible message reported installed-wheel checks passing:
- parser/manifest smoke check;
- production registry;
- offline migration 0004 upgrade/downgrade SQL;
- both CLI --help commands.

Claude was about to write ADR-0010 and update documentation. Final checks, staging and the complete diff handoff were not confirmed.

Do not rerun Prompt 80 blindly or recreate files that already exist.

1. Recover the actual state before editing

Expected:
- Branch: feat/document-ingestion
- HEAD:
  a3e15465be71893627121dca75be121e48613d49
- Origin:
  https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git
- Local main:
  6f8ffded2e5c7b2ed69e37700dc03f20f5e24482

Inspect:
- branch, HEAD and origin;
- staged, unstaged and untracked files;
- current diffs and staged tree;
- relevant .local/ verification records;
- whether Prompt 80 and its outcome are already recorded;
- implemented code, tests and remaining documentation.

Partial implementation changes are expected. Preserve them.

If branch or HEAD differs, or unrelated work is present, stop and report the discrepancy. Do not reset, restore, discard or rewrite anything.

2. Recover the implementation requirements

Read Prompt 80 if recorded and the accepted specification.

Scope:
- deterministic text/plain and text/markdown chunking;
- retrieval package registration;
- chunk_sets and chunks, migration 0004;
- tenant-scoped source loading;
- fenced, idempotent chunk writes;
- shared revision locking;
- completeness callback bound to the current attempt’s manifest;
- production ingest_revision handler;
- fixed failure codes;
- tests, ADR-0010 and accurate documentation.

Preserve:
- exact source provenance and permitted omissions;
- repeated headers as separate context spans;
- deterministic IDs and canonical manifests;
- insert-conflict comparison, including missing lookup results;
- job → document → revision lock order and fresh lease checks;
- no writes after settlement;
- deterministic partial-write recovery;
- atomic activation and job success;
- permanent-failure crash-gap recovery;
- cancellation and uncertain-commit semantics;
- content privacy.

No embeddings, retrieval engine, model calls, endpoints, M3e projection implementation or Docker work.

Inspect what already exists. Complete missing work and correct concrete defects within the accepted scope.

3. Finish documentation and session guidance

Create or complete ADR-0010.

Update README.md, docs/plan.md and docs/threat-model.md to describe actual implementation and limitations:
- local implementation awaiting review;
- PostgreSQL and Linux verification pending for this version;
- Compose, M3e–M3f and overall M3 acceptance pending.

Check CLAUDE.md reflects Mathew’s preference:
- keep sessions through implementation and immediate corrections;
- consider a new session after roughly 20 substantial prompts;
- switch earlier only for concrete context/usage reasons;
- milestone boundaries alone do not require a restart.

Do not change that preference back to frequent restarts.

4. Verification

Distinguish previous-session results from checks executed now. Never claim a historical check ran in this session.

Run the relevant final checks on the completed state:
- uv sync --locked;
- Ruff formatting and lint;
- strict Mypy;
- focused tests and the full database-independent suite;
- package build;
- isolated installed-wheel checks outside the source tree;
- offline migration rendering through 0004;
- git diff --cached --check;
- staged Gitleaks scan.

Check parser/manifest behavior and production registry from the installed wheel without starting a worker against a database.

No Docker startup or database contact is authorized. Prevent environment variables from accidentally enabling PostgreSQL tests. Report integration tests as collected/skipped or unrun, with exact observed results.

Preserve historical tests and meaningful assertions.

5. Prompt history

Do not duplicate Prompt 80.

If its exact original text is unavailable, record an honestly labelled interruption note rather than inventing a verbatim entry.

Append this resumption prompt verbatim under the next unused number. Record:
- recovered state;
- work already present;
- work completed now;
- historical versus current verification;
- remaining limitations.

Preserve earlier history byte-for-byte. Do not claim acceptance or publication.

6. Stage and provide the complete review handoff

Stage only relevant source, tests, configuration and documentation. Exclude .local/, credentials, environments, backups and build outputs.

Leave everything staged and uncommitted.

Report:
- recovered state and completed work;
- design decisions and any deviations;
- changed paths;
- actual checks and results;
- skipped/unrun verification;
- branch, HEAD, staged tree and working-tree status;
- prompt-history additions.

Provide the COMPLETE staged diff excluding prompts.md directly in fenced diff blocks.

Split into numbered parts at file boundaries. Do not truncate or omit source or tests. If output limits prevent completion, save the full diff under .local/ and clearly identify all parts still missing.

No commit, push, merge, history rewrite, installation of unrelated tools, global configuration change, Docker startup or database contact is authorized.
````

**Outcome note (written before review; the work is staged and uncommitted):**
- **Recovered state (verified before editing):**
  - branch `feat/document-ingestion` at HEAD `a3e1546`, with the expected origin and local `main` at `6f8ffde`;
  - nothing staged;
  - the Prompt 80 work present as 14 modified and 12 untracked paths, all within M3d scope;
  - no Prompt 80 entry in the history.

  Nothing was reset, restored or discarded. The exact Prompt 80 text was still available in this session, so it is recorded verbatim above rather than as a reconstruction.
- **Completed now:**
  - ADR-0010 (`docs/decisions/0010-document-ingestion.md`);
  - `README.md`, `docs/plan.md` and `docs/threat-model.md`, marking M3d as implemented locally, awaiting review, with its PostgreSQL integration tests unrun and PostgreSQL and Linux verification pending, and Compose, M3e–M3f and overall M3 acceptance pending;
  - this prompt history.

  `CLAUDE.md` was checked: it already holds the revised session preference from Prompt 80, and it was not changed again. No source or test defects were found during recovery, so no code changed in this prompt.
- **Checks run in Prompt 81 (Windows, no database; the `EG_` database variables unset):**
  - `uv sync --locked`, `ruff format --check .` (108 files already formatted), `ruff check .` (all checks passed) and `mypy` (no issues in 92 source files);
  - the focused M3d tests: 196 passed, 45 skipped;
  - the full suite: 1019 passed, 179 skipped. The skips are 178 PostgreSQL integration tests and 1 Windows-only signal test; `pytest -m integration --collect-only` collected 178 integration tests;
  - `uv build` into `.local/`;
  - in a fresh isolated environment outside the source tree: the parser/manifest smoke (normative example 1 and the documented chunk ID), the production registry (`ingest_revision`), offline migration SQL through `0004` (upgrade and `0004:0003` downgrade), and `eg-worker --help` and `eg-api --help` exiting 0.

  `git diff --cached --check` and the staged Gitleaks scan run after this entry is staged; their results are in the session handoff.
- **Not run:** no PostgreSQL integration test ran (45 new, 178 in all); there was no database contact or Docker, and no Linux run. No performance was measured.
- **Limits:** see ADR-0010.
  - The digest-only completeness check does not protect against privileged database modification.
  - The M3e `stalled` projection is still required before overall M3 acceptance.
  - Compose is unverified.
- **Review status:** pending. Nothing is accepted, committed, pushed or merged.

**Review note (recorded in Prompt 82):**
- **Accepted for a local commit**, subject to narrow documentation cleanup. The basis was the complete implementation diff supplied as `p80-staged.diff` and the Windows checks reported in Prompt 81: 1019 passed and 179 skipped, the skips being 178 PostgreSQL tests and the POSIX-only signal test, which is skipped on Windows.
- **How it was reviewed:** the reviewer inspected the source, tests, schema, migration and worker integration but did not run the project suite.
- **Claim order:** a suspected claim-order issue was checked and is not a defect.
- **Still pending:** PostgreSQL and Linux verification of this version.
- **Handoff format:** from Prompt 82, review handoffs export the complete diff to a file under `.local/` instead of printing it in chat.

## Prompt 82: Local M3d commit and file-based review handoffs

- **Stage:** Documentation cleanup and a local commit on branch `feat/document-ingestion` (no push or merge)
- **Date:** 2026-10-15 (session date)
- **Numbering:** 82 is the next unused number after Prompt 81; verified before appending.

````text
Prompt 82 — Local M3d commit and file-based review handoffs

Work only inside D:\Claude\evidenceguard_agentic_rag. Follow CLAUDE.md, with the explicit handoff-rule change below.

The external reviewer inspected the complete p80-staged.diff and accepts the M3d implementation for a local commit, subject to narrow documentation cleanup.

No push, merge, history rewrite, Docker, database contact or M3e implementation is authorized.

1. Verify the starting state

Expected:
- Branch: feat/document-ingestion
- HEAD:
  a3e15465be71893627121dca75be121e48613d49
- Staged tree:
  4b7519fbcf9d591b752b62b1b68c820b7edd90ce
- Exactly the 31 staged paths reported in Prompt 81.
- Nothing unstaged or untracked.
- Expected origin:
  https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git
- Local main and origin/main:
  6f8ffded2e5c7b2ed69e37700dc03f20f5e24482
- Effective author and committer:
  257921624+mathewmljourney93@users.noreply.github.com

If anything differs, stop and report the discrepancy without changing anything.

Record the accepted staged tree before editing.

2. Change the persistent review-handoff rule

In CLAUDE.md, replace conflicting requirements to print complete diffs in chat.

The new rule:
- Export the complete implementation staged diff, excluding prompts.md, directly to a UTF-8 .diff file under gitignored .local/.
- Correction handoffs export the complete incremental diff against the explicitly recorded previously reviewed tree, excluding prompts.md.
- Do not print complete diffs in chat unless Mathew explicitly requests it.
- Never truncate exported diffs or omit source, tests, migrations or configuration.
- Report the exact file path, baseline tree or commit, final tree or commit, byte size and SHA-256.
- Keep the response concise: changes, actual verification, Git state and remaining limitations.
- End every handoff with an explicit instruction saying whether Mathew should return “output only” or “output plus the diff file”, naming that file.
- Implementation and correction reviews require output plus the appropriate diff file.
- If there are no changes outside prompts.md, say so; no empty diff attachment is needed.

Preserve the revised session preference. Do not recommend restarting this session merely because implementation is complete.

3. Narrow documentation cleanup

Update README.md, docs/plan.md, docs/threat-model.md and ADR-0010 only where needed.

A. Remove ambiguity about the production registry:
- Historical M3b/M3c statements describing an empty registry or no production ingestion handler must be explicitly scoped to those milestone baselines or current main at 6f8ffde.
- The local M3d implementation registers ingest_revision.
- Upload and document endpoints remain unimplemented.
- Preserve historical CI evidence and earlier prompt history.

B. Record the review status accurately:
- M3d implementation accepted at external review for a local commit.
- PostgreSQL and Linux verification of this version remain pending publication and CI.
- No new CI results exist.
- The 133 earlier PostgreSQL tests passed against M3c, but the complete 178-test suite has not run against M3d; its 45 new tests have never run.
- Compose, M3e–M3f and overall M3 acceptance remain pending.

Avoid embedding this new commit’s own SHA in its content or pre-recording a successful commit.

Do not change application code, tests, migrations, dependencies or workflows.

4. Prompt history

Append a review note under Prompt 81 recording:
- acceptance based on the complete supplied implementation diff and reported Windows checks;
- 1019 passed and 179 skipped locally: 178 PostgreSQL tests plus the POSIX-only signal test skipped on Windows;
- the reviewer inspected source, tests, schema, migration and worker integration but did not run the project suite;
- PostgreSQL and Linux verification remain pending;
- the earlier suspected claim-order issue was checked and was not a defect;
- the switch to file-based review handoffs.

Append this prompt verbatim using the next unused number; expect 82 and verify it.

Preserve earlier prompt-history bytes unchanged. Add a truthful pre-commit note without claiming future results.

5. Verify and commit locally

Allowed changes relative to the accepted staged tree:
CLAUDE.md
README.md
docs/decisions/0010-document-ingestion.md
docs/plan.md
docs/threat-model.md
prompts.md

Confirm all other staged files remain byte-identical to the accepted tree. Keep exactly the expected 31 paths staged; do not stage .local/ or build artifacts.

Run:
- documentation consistency and relative-link/anchor checks;
- private-content check of new additions;
- git diff --cached --check;
- staged Gitleaks scan;
- effective identity checks.

Do not rerun application checks or rebuild merely for these documentation changes. Attribute the application results to Prompt 81, rather than claiming they ran now.

Commit with subject:
feat: add deterministic document ingestion and fenced chunk storage

Keep the existing co-author attribution convention.

After committing:
- verify the parent, identity and committed paths;
- confirm every file outside the six permitted documentation/history paths is byte-identical to the accepted tree;
- run the full-history Gitleaks scan;
- confirm the working tree is clean;
- confirm main was not changed.

Do not push.

6. Export the incremental review file

Export the COMPLETE diff from:
4b7519fbcf9d591b752b62b1b68c820b7edd90ce

to the new local commit, excluding prompts.md, as:
.local/p82/m3d-commit-incremental.diff

Write it directly from Git output without printing the diff into chat. Preserve UTF-8 correctly; do not use a shell redirection method that converts it to UTF-16.

Report:
- baseline tree;
- resulting commit;
- exact file path;
- byte size;
- SHA-256.

Keep it gitignored and untracked by Git.

7. Concise handoff

Report:
- commit SHA, parent, subject and identity;
- committed paths;
- documentation and handoff-rule changes;
- actual checks and results;
- historical application results clearly labelled;
- final Git state;
- pending PostgreSQL/Linux verification, Compose and M3 acceptance.

Do not print the diff.

End with:
“Return this output plus .local/p82/m3d-commit-incremental.diff to the external reviewer.”

Nothing may be pushed or merged.
````

**Pre-commit note (written before the commit; the commit's own SHA is not recorded here):**
- **Starting state verified:** branch `feat/document-ingestion`, HEAD `a3e1546`, staged tree `4b7519f` with the 31 paths of Prompt 81 and nothing unstaged or untracked. Also the expected origin, local `main` and `origin/main` at `6f8ffde`, and the noreply author and committer identity. The accepted tree was recorded under `.local/p82/` before editing.
- **Handoff rule:** `CLAUDE.md`'s "Review handoffs" now exports complete diffs to UTF-8 files under `.local/` instead of printing them in chat. Each handoff reports the path, baseline, final tree or commit, byte size and SHA-256, and ends with an explicit return instruction. The session preference is unchanged.
- **Documentation:**
  - `README.md`, `docs/plan.md` and `docs/threat-model.md` scope the historical "no production handler" and empty-registry statements to the M3a–M3c baselines or to `main` at `6f8ffde`. They state that the local M3d implementation registers `ingest_revision`, and that upload and document endpoints are not implemented.
  - These files and ADR-0010 record M3d as accepted at external review for a local commit.
  - They also record that no new CI results exist: the 133 earlier PostgreSQL tests passed against M3c, but the complete 178-test suite has not run against M3d, and its 45 new tests have never run. PostgreSQL and Linux verification are pending.
  - No application code, test, migration, dependency or workflow changed.
- **Application results:** these are from Prompt 81 and were not rerun for these documentation changes.
- **Checks for this commit:** the documentation, staged-scan and identity checks run after this entry is staged, then the post-commit checks; results are in the session handoff.
- **Still pending:** PostgreSQL and Linux verification, Compose, M3e–M3f and overall M3 acceptance. Nothing pushed or merged.

**Outcome note for Prompt 82 (recorded in Prompt 83):**
- **Commit:** `4207cc8a7a481791de6a292a5c5fdb73a09703cd` (`feat: add deterministic document ingestion and fenced chunk storage`) on `feat/document-ingestion`. Its parent is `a3e1546` and its tree `783be90`, with the noreply author and committer identity, and it contains the 31 paths of Prompt 81.
- **Changes from the accepted tree:** only the six permitted documentation and history paths differ from `4b7519f`.
- **Post-commit checks:** the full-history Gitleaks scan reported 32 commits scanned and no leaks found; the working tree was clean; `main` and `origin/main` stayed at `6f8ffde`. Nothing was pushed.
- **Review file:** `.local/p82/m3d-commit-incremental.diff`, from tree `4b7519f` to commit `4207cc8`, excluding `prompts.md`: 45,546 bytes, SHA-256 `99594e143e915e3985ae25be49eb09e4d38ba8f39318be48c85d0989d0ce66c5`.
- **Review note:** the external reviewer accepted that incremental documentation diff. The reviewer inspected the diff and independently checked its SHA-256, which matched, but did not run the project checks.

## Prompt 83: Publish the reviewed M3d feature branch and observe CI

- **Stage:** Prompt-history commit and publication of `feat/document-ingestion` only (no merge, no `main` update)
- **Date:** 2026-10-15 (session date)
- **Numbering:** 83 is the next unused number after Prompt 82; verified before appending.

````text
Prompt 83 — Publish the reviewed M3d feature branch and observe CI

Work only inside D:\Claude\evidenceguard_agentic_rag. Follow CLAUDE.md.

The reviewer accepts Prompt 82’s incremental documentation diff. Its SHA-256 was independently checked and matches:
99594e143e915e3985ae25be49eb09e4d38ba8f39318be48c85d0989d0ce66c5

This authorizes a prompt-history commit and publication of feat/document-ingestion only.

Do not merge, update main, force-push, amend, rebase, delete branches, push tags, start Docker, contact a local database or begin M3e.

1. Verify the starting state

Expected:
- Branch: feat/document-ingestion
- HEAD:
  4207cc8a7a481791de6a292a5c5fdb73a09703cd
- Parent:
  a3e15465be71893627121dca75be121e48613d49
- Clean working tree.
- Origin:
  https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git
- Effective author and committer:
  257921624+mathewmljourney93@users.noreply.github.com

Read fresh remote refs:
- main must still be:
  6f8ffded2e5c7b2ed69e37700dc03f20f5e24482
- feat/document-ingestion should not exist remotely.
- Remote main must be an ancestor of HEAD.
- No upstream should already be configured for this branch.

If the state differs, stop and report it without changing anything.

2. Publication preflight

Inspect everything that will become public relative to remote main, including:
- a3e1546, the accepted specification;
- 4207cc8, the implementation;
- the history commit authorized below.

Confirm:
- expected commit identities use the noreply address;
- no tracked .local/, environment secrets, backups, bundles or build artifacts;
- no real credentials or private information in published content;
- both workflows trigger on this branch;
- Ubuntu and Windows verification remain enabled;
- PostgreSQL integration uses EG_REQUIRE_INTEGRATION=1;
- full-history secret scanning remains enabled.

Do not redesign workflows or install tooling.

3. Prompt-history commit

Only prompts.md may change.

Append:
- the actual Prompt 82 commit outcome;
- acceptance of its incremental diff, stating that the reviewer inspected the diff and checked its checksum but did not run project checks;
- this prompt verbatim under the next unused number, expected 83;
- a truthful publication-preflight note.

Preserve earlier history byte-for-byte.

Do not pre-record successful pushes or CI results. Keep prior local test results clearly labelled as historical.

Run:
- private-content check of additions;
- git diff --cached --check;
- staged Gitleaks scan.

Commit with subject:
docs: record M3d branch publication authorization

Preserve the existing co-author convention.

Verify only prompts.md changed, then run the full-history Gitleaks scan before pushing.

Do not rerun application checks: no application content is changing.

4. Publish only the feature branch

Use:
git push --set-upstream origin refs/heads/feat/document-ingestion:refs/heads/feat/document-ingestion

Run Git directly and report its actual exit status. Do not pipe it through commands that mask failures.

Confirm the remote feature ref equals the exact new local HEAD and remote main is unchanged.

If the push fails, inspect the result and remote state. Do not change authentication, configuration or publication scope automatically.

5. Observe CI for the exact published SHA

Monitor the push-triggered runs for at most 20 minutes:
- Ubuntu verification;
- Windows verification;
- PostgreSQL integration;
- full-history Gitleaks.

Use existing available read-only access. Do not install gh or request broader credentials solely to obtain logs.

Use bounded polling, avoiding repeated verbose output.

If any check fails, stop and report the failed job, step and available diagnostics. Do not edit or retry implementation automatically.

If checks remain pending at the limit, report their links and status.

Where logs are accessible, report actual pytest summaries. Otherwise distinguish observed successful job/step conclusions from expected test counts.

The 178 integration tests are an expectation until observed. Do not infer or fabricate their exact count.

Do not merge or update main even if every check passes.

6. Concise handoff

Report:
- history commit SHA and parent;
- exact published SHA;
- push result and remote refs;
- workflow/job links and conclusions;
- observed test summaries, or the precise log-access limitation;
- checks actually run;
- final Git state and remaining limitations.

Only prompts.md should have changed, so no diff file is needed. Do not print a diff.

End with:
“Return this output only to the external reviewer; no diff attachment is required.”
````

**Publication-preflight note (written before the history commit and the push; neither result is recorded here):**
- **Starting state verified:** branch `feat/document-ingestion` at `4207cc8` with parent `a3e1546`, a clean tree, the expected origin and the noreply identity. A fresh `git ls-remote` showed remote `main` at `6f8ffde`, an ancestor of HEAD, and no remote `feat/document-ingestion`. No upstream was configured.
- **What will become public:** `a3e1546` (the accepted M3d specification), `4207cc8` (the implementation) and this history commit. Every commit in `6f8ffde..HEAD` has the noreply author and committer.
- **Tracked files:** no `.local/`, environment secret, backup, bundle, wheel, sdist or other build artifact. The only environment-like path is the long-standing placeholder `.env.example`, unchanged from `main`.
- **Content:** the search of lines added since `main` found no credential patterns, user paths or private email addresses.
- **Workflows:** both run on every push. CI verifies on `ubuntu-24.04` and `windows-2025`, and its PostgreSQL integration job sets `EG_REQUIRE_INTEGRATION: "1"`. The secret scan checks out the full history (`fetch-depth: 0`) and runs Gitleaks over it. No workflow was changed in this prompt.
- **Historical local results (Prompt 81, Windows, no database):** 1019 passed and 179 skipped, the skips being 178 PostgreSQL tests and 1 POSIX-only signal test. No application check was rerun in this prompt, and no CI result for M3d exists yet. The 178 integration tests are an expectation until CI reports them.
- **Not done:** no merge, `main` update, force-push, tag, Docker or database contact.

**Outcome note for Prompt 83 (recorded in Prompt 84):**
- **History commit:** `74904e6407afca656d5f6b860552c86756678582` (`docs: record M3d branch publication authorization`), with parent `4207cc8`, the noreply identity and only `prompts.md` changed. Before the push, the full-history Gitleaks scan reported 33 commits scanned and no leaks found.
- **Push:** `git push --set-upstream origin refs/heads/feat/document-ingestion:refs/heads/feat/document-ingestion` exited 0 and created the branch. A fresh `git ls-remote` showed `feat/document-ingestion` at `74904e6` and `main` unchanged at `6f8ffde`. Nothing was merged.
- **CI observed by Claude:** push-triggered runs for `74904e6`, read through the anonymous Actions API. [ci run 38699149482](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38699149482) and [secret-scan run 38699149417](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38699149417) both concluded `success`, with every job and step successful or skipped.
- **Log access was limited:** the anonymous job-log endpoint returned `HTTP 403 Forbidden`, so Claude observed no pytest summaries, and no credentials were added.

**Reviewer-evidence note (recorded in Prompt 84):** the external reviewer retrieved the workflow metadata and job logs for `74904e6`. Both runs were triggered by a push to `feat/document-ingestion` and concluded `success`:
- Ubuntu job 116302837532: `1020 passed, 178 skipped in 20.13s`;
- Windows job 116302837727: `1019 passed, 179 skipped in 23.75s`;
- PostgreSQL integration job 116302837038: `178 passed, 1020 deselected in 51.89s`. This is the full 178-test suite against M3d, including the 45 new tests; no per-test listing or migration transcript was recorded;
- secret-scan job 116302836923: 33 commits scanned, no leaks found.

The reviewer did not run the suite locally.

## Prompt 84: Record verified M3d results for review

- **Stage:** Documentation only, on branch `feat/document-ingestion` (staged and uncommitted for review; no commit, push or merge)
- **Date:** 2026-10-15 (session date)
- **Numbering:** 84 is the next unused number after Prompt 83; verified before appending.

````text
Prompt 84 — Record verified M3d results for review

Work only inside D:\Claude\evidenceguard_agentic_rag. Follow CLAUDE.md.

This authorizes documentation changes and staging only. No commit, push, merge, history rewrite, Docker, database contact or M3e implementation.

1. Verify starting state

Expected:
- Branch: feat/document-ingestion
- HEAD and upstream:
  74904e6407afca656d5f6b860552c86756678582
- Parent:
  4207cc8a7a481791de6a292a5c5fdb73a09703cd
- Clean working tree.
- Expected origin:
  https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git
- Local and remote main:
  6f8ffded2e5c7b2ed69e37700dc03f20f5e24482

Check remote refs read-only. If anything differs, stop and report it without changing anything.

2. Record independently observed CI evidence

The external reviewer retrieved the workflow metadata and job logs for this exact SHA:
74904e6407afca656d5f6b860552c86756678582

Both runs were triggered by a push to feat/document-ingestion and concluded success.

CI:
https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38699149482

Ubuntu job 116302837532:
1020 passed, 178 skipped in 20.13s

Windows job 116302837727:
1019 passed, 179 skipped in 23.75s

PostgreSQL integration job 116302837038:
178 passed, 1020 deselected in 51.89s

Secret scan:
https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38699149417

Job 116302836923:
33 commits scanned, no leaks found

Attribute log retrieval to the external reviewer. The reviewer did not run the suite locally. Do not claim you retrieved logs that your session could not access.

The full 178-test PostgreSQL suite passed against M3d, including its 45 new tests as part of that suite. Do not claim a separately observed per-test listing or migration transcript.

3. Update only these files

README.md
docs/decisions/0010-document-ingestion.md
docs/plan.md
docs/threat-model.md
prompts.md

Record:
- M3d reviewed and verified in CI on feat/document-ingestion at 74904e6.
- PostgreSQL and Linux verification of that version are now complete.
- Windows verification and full-history secret scanning passed.
- M3d has not been merged into main.
- Main remains the M3c baseline at 6f8ffde.
- Compose remains unverified.
- M3e, its required stalled-revision projection, M3f and overall M3 acceptance remain pending.
- No performance benchmark or general security guarantee is established.

Preserve the architecture, implementation and earlier SHA-specific results.

Correct current statements that the M3d integration tests have never run. Preserve historical statements inside earlier prompt entries.

Do not expand scope or change source, tests, migrations, dependencies, workflows or CLAUDE.md.

4. Prompt history

Append:
- Prompt 83’s actual publication outcome, including its limited anonymous log access.
- A later reviewer-evidence note with the observed results above.
- This prompt verbatim under the next unused number; expect 84 and verify it.
- An accurate outcome note.

Preserve all earlier history byte-for-byte. Do not pre-record review acceptance, a commit or a main update.

5. Verify and stage

Run documentation consistency, relative-link/anchor and private-content checks, git diff --cached --check and the staged Gitleaks scan.

Do not rerun application tests or builds for documentation-only changes.

Leave exactly the five authorized files staged and uncommitted, with nothing unstaged or untracked.

6. Export the review diff

Export the complete staged diff against HEAD, excluding prompts.md, directly to:
.local/p84/m3d-verification-docs.diff

Use UTF-8 without BOM. Do not print the diff in chat.

Report its baseline commit, final staged tree, byte size and SHA-256.

7. Concise handoff

Report:
- documentation changes;
- actual checks and results;
- branch, HEAD, staged tree and staged paths;
- remaining limitations;
- prompt-history additions;
- exact diff-file path and checksum.

End with:
“Return this output plus .local/p84/m3d-verification-docs.diff to the external reviewer.”

Nothing may be committed, pushed or merged.
````

**Outcome note (written before review; the changes are staged and uncommitted):**
- **Starting state verified:** branch `feat/document-ingestion` with HEAD and upstream at `74904e6` and parent `4207cc8`, a clean tree and the expected origin. Local and remote `main` were at `6f8ffde`, confirmed read-only with `git ls-remote`.
- **Documentation updated:** `README.md`, ADR-0010, `docs/plan.md` and `docs/threat-model.md`.
  - **Verification recorded:** M3d is reviewed and verified in CI on `feat/document-ingestion` at `74904e6`, with the reviewer-retrieved results above attributed to the reviewer. PostgreSQL, Linux and Windows verification of that version are complete, and the full-history secret scan passed.
  - **Not merged:** `main` remains the M3c baseline at `6f8ffde`.
  - **Stale statements corrected:** earlier current-state wording said the M3d integration tests had never run; that is replaced. Remaining mentions of a "local" M3d implementation now name the unmerged branch.
  - **Pending:** Compose is unverified; M3e, its required stalled-revision projection, M3f and overall M3 acceptance remain pending; no performance benchmark or general security guarantee is claimed.
  - **Unchanged:** no source, test, migration, dependency, workflow or `CLAUDE.md` changed.
- **Checks:** the documentation-consistency, link and anchor, private-content, `git diff --cached --check` and staged Gitleaks checks run after this entry is staged; results are in the session handoff. No application tests or builds were rerun.
- **Review status:** pending. Nothing is committed, pushed or merged.

**Review note (recorded in Prompt 85):**
- **Accepted:** the external reviewer accepted the Prompt 84 documentation diff `.local/p84/m3d-verification-docs.diff`, which was inspected and checksum-checked: SHA-256 `a6bdedc08ec60e1e365e4ab337ec52147a3400c7e6e4e9da8009aa6de317d42b`, matching.
- **CI evidence:** the reviewer independently retrieved the CI evidence for `74904e6`, but did not run the suite locally.

## Prompt 85: Commit verified M3d documentation and publish to main

- **Stage:** Documentation commit, feature-branch push, and a fast-forward of `main` only after all four feature checks pass
- **Date:** 2026-10-15 (session date)
- **Numbering:** 85 is the next unused number after Prompt 84; verified before appending.

````text
Prompt 85 — Commit verified M3d documentation and publish to main

Work only inside D:\Claude\evidenceguard_agentic_rag. Follow CLAUDE.md.

The reviewer accepts Prompt 84’s documentation diff, including its independently verified checksum:
a6bdedc08ec60e1e365e4ab337ec52147a3400c7e6e4e9da8009aa6de317d42b

This authorizes the local documentation commit, feature-branch push, and a fast-forward of main only after all four feature checks pass.

No implementation, force-push, amend, rebase, squash, branch deletion, tag push, Docker or local database contact.

1. Verify starting state

Expected:
- Branch: feat/document-ingestion
- HEAD and upstream:
  74904e6407afca656d5f6b860552c86756678582
- Staged tree:
  ae6263ffe56f9f956b75831b1095f76e21880fc3
- Exactly five staged paths:
  README.md
  docs/decisions/0010-document-ingestion.md
  docs/plan.md
  docs/threat-model.md
  prompts.md
- Nothing unstaged or untracked.
- Origin:
  https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git
- Effective author and committer:
  257921624+mathewmljourney93@users.noreply.github.com

Fetch fresh remote refs. Local and remote main must be:
6f8ffded2e5c7b2ed69e37700dc03f20f5e24482

Remote feature must equal HEAD, and main must be its ancestor.

If anything differs, stop and report it without changing anything.

2. Commit the reviewed documentation

Record the accepted staged tree.

Keep the four reviewed documents byte-identical to that tree. Only prompts.md may change.

Append:
- acceptance of Prompt 84’s diff, inspected and checksum-checked by the reviewer;
- that the reviewer independently retrieved CI evidence for 74904e6 but did not run the suite locally;
- this prompt verbatim under the next unused number, expected 85;
- a truthful preflight note covering the authorization order and stop conditions.

Preserve earlier history byte-for-byte. Do not pre-record push or CI success.

Verify authorized paths, identity, private content, git diff --cached --check and staged Gitleaks.

Commit with subject:
docs: record verified M3d results and main publication authorization

Keep the existing co-author convention.

Verify parent and paths, and confirm the four reviewed documents remain byte-identical. Run the full-history Gitleaks scan before publication.

No application tests or builds need to be rerun locally: only documentation changed.

3. Push the feature branch and observe CI

Push only:
git push origin refs/heads/feat/document-ingestion:refs/heads/feat/document-ingestion

Use Git directly and report its actual exit status.

Confirm remote feature equals the new commit. Monitor push-triggered checks for that exact SHA:
- Ubuntu verification;
- Windows verification;
- PostgreSQL integration;
- full-history secret scan.

Allow at most 20 minutes, with bounded polling and concise output.

If any check fails, is cancelled, or remains pending at the limit, stop. Do not update main or automatically fix code.

4. Fast-forward main only after four successful checks

Fetch fresh refs again and confirm:
- remote main is still 6f8ffde;
- remote feature equals the exact verified commit;
- main is an ancestor of that commit;
- local main equals origin/main with no independent commits;
- the working tree is clean.

If any precondition fails, stop.

Switch to main and fast-forward with:
git merge --ff-only <the exact verified full SHA>

Push only:
git push origin refs/heads/main:refs/heads/main

No merge commit and no force-push.

Monitor the push-triggered main runs for that exact SHA, with the same four checks and a 20-minute maximum. Report failures without automatically reverting or editing.

5. Concise handoff

Report:
- new commit SHA, parent, identity and paths;
- confirmation the reviewed documents stayed byte-identical;
- scans actually run;
- both push results and before/after refs;
- feature and main workflow/job links and conclusions;
- observed pytest summaries if logs are accessible;
- precise access limitations if logs are unavailable;
- final branch and working-tree status.

Do not reuse 74904e6’s counts as observed results for the new SHA.

Use existing read-only CI access. Do not install tools or change credentials solely to retrieve logs.

The documentation predates the main update. Leave its historical state intact during this task; record the eventual publication result in the next authorized documentation task.

Compose, M3e–M3f and overall M3 acceptance remain pending. Do not start M3e.

Only prompts.md should differ from the accepted staged tree, so no new diff file is required.

End with:
“Return this output only to the external reviewer; no diff attachment is required.”
````

**Preflight note (written before the commit, pushes and CI; none of their results is recorded here):**
- **Starting state verified:** branch `feat/document-ingestion`, with HEAD and upstream at `74904e6`.
  - The staged tree was `ae6263f`, with exactly the five authorized paths and nothing unstaged or untracked.
  - The origin and the noreply identity were as expected.
  - After a fresh `git fetch`, local `main`, `origin/main` and the remote feature branch were at `6f8ffde`, `6f8ffde` and `74904e6`, and `main` is an ancestor of HEAD.
  - The accepted tree was recorded under `.local/p85/`.
- **Authorized order:**
  1. commit this history;
  2. push only `feat/document-ingestion`;
  3. observe its four checks: Ubuntu, Windows, PostgreSQL integration and the full-history secret scan, for at most 20 minutes;
  4. only if all four succeed, re-fetch and re-check the preconditions, fast-forward local `main` to that exact commit with `--ff-only`, and push only `main`;
  5. observe the four checks on `main`.
- **Stop conditions:** a failed, cancelled or still-pending feature check, or any failed precondition, stops the task before `main` changes. Code is not fixed and nothing is reverted automatically.
- **Not done:** no force-push, amend, rebase, squash, branch deletion, tag, Docker or database contact. The documentation's state predates the `main` update and is intentionally left as it is.
- **Still pending:** Compose, M3e–M3f and overall M3 acceptance.

**Outcome note for Prompt 85 (recorded in Prompt 86):**
- **Commit:** `cdf7260d02b8af9affb369cc805d666be61f9ac0` (`docs: record verified M3d results and main publication authorization`). Its parent is `74904e6`, it uses the noreply identity, and its four reviewed documents are byte-identical to the accepted tree `ae6263f`; only `prompts.md` differs. Before publication, the full-history Gitleaks scan reported 34 commits scanned and no leaks found.
- **Feature push:** the push of `feat/document-ingestion` exited 0, moving it from `74904e6` to `cdf7260`. The push-triggered [ci run 38701060085](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38701060085) (Ubuntu, Windows and PostgreSQL integration) and [secret-scan run 38701060034](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38701060034) all concluded `success`.
- **Fast-forward of `main`:** the preconditions were re-checked after a fresh fetch. Local `main` was fast-forwarded with `git merge --ff-only cdf7260d02b8af9affb369cc805d666be61f9ac0`, with no merge commit, and `git push origin refs/heads/main:refs/heads/main` exited 0, moving `main` from `6f8ffde` to `cdf7260`.
- **CI on `main`:** the push-triggered [ci run 38701376504](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38701376504) and [secret-scan run 38701376501](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38701376501) concluded `success`.
- **Log access:** Claude read only the conclusions through the anonymous API. The job logs need authentication, so no pytest summaries were observed in that session.

**Reviewer-evidence note for `main` (recorded in Prompt 86):** the external reviewer independently retrieved the metadata and logs for `cdf7260` on `main`. Both runs were push-triggered on `main` and concluded `success`:
- Ubuntu job 116310119787: `1020 passed, 178 skipped in 19.71s`;
- Windows job 116310119664: `1019 passed, 179 skipped in 16.16s`;
- PostgreSQL job 116310119317: `178 passed, 1020 deselected in 53.28s`;
- secret-scan job 116310119403: 34 commits scanned, no leaks found.

The reviewer did not run the suite locally.

## Prompt 86: Record M3d main verification and specify M3e APIs

- **Stage:** Documentation and specification only, on branch `docs/m3e-api-spec` (staged and uncommitted for review; no commit, push or merge)
- **Date:** 2026-10-15 (session date)
- **Numbering:** 86 is the next unused number after Prompt 85; verified before appending.

````text
Prompt 86 — Record M3d main verification and specify M3e APIs

Work only inside D:\Claude\evidenceguard_agentic_rag. Follow CLAUDE.md.

This is a documentation/specification task. No implementation, commit, push, merge, history rewrite, Docker, database contact, dependency installation or global configuration change.

1. Verify starting state

Expected:
- Branch: main
- HEAD and origin/main:
  cdf7260d02b8af9affb369cc805d666be61f9ac0
- Clean working tree.
- Origin:
  https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git

Read remote refs read-only. If anything differs, stop and report it without changing anything.

Create docs/m3e-api-spec from this HEAD.

Read the relevant plan sections, ADR-0006 through ADR-0010, and existing API authentication, database, problem-response, revision, job and chunk interfaces. Use targeted reads rather than loading the full prompt archive.

2. Record M3d main publication

Update README.md, ADR-0010, docs/plan.md and docs/threat-model.md to record M3d on main at cdf7260.

The external reviewer independently retrieved metadata and logs for this exact SHA:

Main CI:
https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38701376504

- Ubuntu job 116310119787:
  1020 passed, 178 skipped in 19.71s
- Windows job 116310119664:
  1019 passed, 179 skipped in 16.16s
- PostgreSQL job 116310119317:
  178 passed, 1020 deselected in 53.28s

Main secret scan:
https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38701376501
- Job 116310119403:
  34 commits scanned, no leaks found

Both runs were push-triggered on main and concluded success.

Attribute retrieval to the external reviewer, who did not run the suite locally. Preserve prior feature-branch evidence as historical results.

M3e, M3f, Compose verification and overall M3 acceptance remain pending.

3. Specify M3e in docs/plan.md

Produce a concrete proposed design for review, grounded in existing interfaces. Clearly separate existing accepted decisions from new proposed defaults. Recommend one approach for each open detail.

Do not implement it.

A. Endpoint scope and contracts

Cover the planned:
- POST /v1/vendors/{id}/documents
- GET /v1/documents/{id}
- GET /v1/documents/{id}/revisions/{rev}/chunks
- GET /v1/jobs/{id}

Resolve the M3e milestone’s “list” requirement explicitly, recommending a vendor-scoped document-list endpoint if needed.

For each endpoint specify:
- authorization;
- path/query/form fields;
- exact response shape;
- status codes and safe errors;
- sorting and bounded pagination;
- foreign-tenant and missing-object behavior.

Use reviewer/approver authorization consistent with vendors. No admin bypass. Tenant scope comes only from authentication.

Define whether {rev} is a revision number or UUID and consistently validate the document/revision relationship.

Do not return unbounded nested revision histories. Give a concrete bounded design.

B. Upload parsing and limits

Keep multipart uploads and the accepted text/plain/text/markdown scope.

Specify:
- file part and metadata field names;
- required/optional fields and validation;
- duplicate and unknown form fields;
- rejection of tenant fields;
- file count, metadata bounds and filename handling;
- a concrete file-byte cap and total-request cap;
- behavior with absent, incorrect or chunked Content-Length;
- strict UTF-8, BOM, CRLF, NUL and media-type handling;
- distinctions between zero-byte invalid input and whitespace-only content that the worker later marks empty_document.

The byte limits must be enforced while receiving the body, before an unbounded multipart parse or file read. Content-Length alone is insufficient.

Explain authentication timing, parser/framework limits, temporary-file cleanup on every path, and any proposed multipart dependency. Avoid promising that a normal FastAPI dependency necessarily runs before body parsing.

Define 413, 415 and 422 behavior and error precedence. Preserve generic privacy-safe problem responses.

Uploaded filenames must never become filesystem paths.

C. Atomic revision and job creation

Reuse create_revision and enqueue in one caller-owned transaction:
- kind ingest_revision;
- payload revision_id;
- canonical revision-ID idempotency key;
- existing attempt default.

Specify:
- new revision plus new job: both commit or neither;
- exact duplicate uploads: 200 and the existing revision/job;
- metadata conflicts and concurrent duplicate uploads;
- response fields for already-processing, active, superseded, failed or dead-job cases;
- no resetting terminal jobs or silently re-ingesting settled revisions;
- behavior if a revision exists without its canonical ingestion job.

Do not always label a duplicate response pending.

Preserve the existing immutable document metadata and content identity rules.

D. Read models and persistence

Define tenant-scoped queries and API database integration:
- all parent-child relationships checked under tenant scope;
- stable ordering with tie-breakers;
- bounded pagination and existing offset-pagination limitations;
- explicit handling of database failures;
- blocking database work kept off the event loop.

Document views exclude raw source content.

Chunk views may expose text for authorized inspection, with the accepted section, line, character and repeated-header provenance. Specify whether partial/failed ingestion chunks are visible and how their completeness is represented. Never imply a repeated-header chunk is one contiguous source passage.

Job views expose only reviewed operational fields. Do not expose raw payloads, owner identifiers, idempotency keys, exception text or unrestricted error details.

GET operations must not create jobs, change revision state or repair data.

E. Required ingestion_state projection

Implement the accepted M3d section E design in M3e:
- settled revision states take precedence;
- unsettled plus queued job → queued;
- unsettled plus running job → in_progress, including expired leases, without a progress guarantee;
- unsettled plus dead/failed/succeeded or missing canonical job → stalled.

Define the response fields and canonical job lookup precisely. Explain stored revision status separately from derived ingestion_state.

If lease information is exposed, use it to explain expiry honestly without claiming progress. Preserve the documented lack of an operator retry in v1.

This projection remains a required overall M3 acceptance item until implemented and verified.

F. Privacy and observability

Preserve existing request IDs, fixed log events and generic problem responses.

Specify protections against logging:
- multipart bodies and document text;
- filenames and arbitrary submitted metadata;
- credentials and database exceptions.

Review any proposed response validation errors so submitted values are not echoed accidentally.

G. Verification and implementation boundaries

List intended files, any narrow dependency/configuration changes and planned ADR-0011.

Separate database-independent tests from real PostgreSQL tests.

Plan meaningful cases for:
- upload byte limits with absent/misleading Content-Length;
- malformed multipart, duplicate fields/files and cleanup;
- authentication, roles and cross-tenant access;
- media type, UTF-8, NUL, empty bytes and whitespace-only input;
- unknown tenant fields and attempted header overrides;
- duplicate and conflicting uploads;
- atomic rollback and concurrent idempotency;
- bounded lists and document/revision mismatch;
- chunk provenance and partial-set policy;
- safe job responses;
- every ingestion_state row, especially dead and expired-running jobs;
- privacy-safe errors/logging;
- installed-wheel API smoke checks.

PostgreSQL execution remains pending an authorized publication and CI. No M3e implementation or result exists yet.

4. Prompt history

Append:
- Prompt 85’s actual main-publication outcome;
- the later reviewer-observed main results above;
- this prompt verbatim under the next unused number, expected 86;
- an accurate outcome note.

Preserve earlier history byte-for-byte. Do not pre-record specification acceptance, implementation or commits.

5. Verification and staging

Allowed tracked changes:
README.md
docs/decisions/0010-document-ingestion.md
docs/plan.md
docs/threat-model.md
prompts.md

Check consistency, relative links/anchors, private content, git diff --cached --check and staged Gitleaks.

No application tests or builds are necessary.

Leave the five files staged and uncommitted.

6. File-based review handoff

Export the complete staged diff excluding prompts.md to:
.local/p86/m3e-api-spec.diff

Write it directly from Git output as UTF-8 without BOM. Do not print the diff.

Give a concise summary of decisions, proposed defaults, actual checks, Git state and limitations.

Report the baseline commit, final staged tree, exact diff path, byte size and SHA-256.

End with:
“Return this output plus .local/p86/m3e-api-spec.diff to the external reviewer.”

Keep the current Claude session. Nothing may be committed, pushed or merged.
````

**Outcome note (written before review; the changes are staged and uncommitted):**
- **Starting state verified:** branch `main` with HEAD, `origin/main` and a read-only `git ls-remote` all at `cdf7260`, the expected origin and a clean tree. Branch `docs/m3e-api-spec` was created from that HEAD.
- **Read before editing** (targeted reads): the vendor endpoints, authentication, the shared database resource and the problem responses in the API; ADR-0006's pagination; M3c's creation seam; M3d section E; and the job snapshot fields. `python-multipart` was confirmed absent from `pyproject.toml` and `uv.lock`.
- **M3d publication recorded:** `README.md`, ADR-0010, `docs/plan.md` and `docs/threat-model.md` now record M3d on `main` at `cdf7260`.
  - The reviewer-retrieved results above are attributed to the reviewer.
  - Earlier statements that said "not merged" or "unmerged branch" are corrected.
  - Statements about the M3c baseline are scoped to `6f8ffde`.
  - The `74904e6` feature-branch evidence is kept as historical.
- **M3e specification added (proposed, not implemented):** a new M3e section in `docs/plan.md`, separating accepted decisions from proposed defaults. It covers:
  - **Endpoints:** six, including a vendor-scoped document list and a bounded revision list; `{rev}` is the revision number.
  - **Uploads:** a bounded multipart design. No body parameters, so authentication and the vendor check happen before any body read. Caps of 2 MiB for the file and 2 MiB plus 64 KiB for the request, enforced while streaming. In-memory buffering with no temporary files. The proposed `python-multipart` dependency, used only through its streaming parser. A defined 413/415/422 precedence.
  - **Creation:** atomic revision-and-job creation, with 202 for new uploads and 200 reporting the true state for duplicates.
  - **Reads:** tenant-scoped read models, chunk provenance and a partial-set policy (`verified_complete` only for `active` or `superseded` revisions), and reviewed job fields.
  - **Projection:** the required `ingestion_state` projection.
  - **Privacy and tests:** privacy rules, and a test plan split into database-independent and PostgreSQL tests.

  The first-release API table and the threat model point to the specification.
- **Checks:** the consistency, link and anchor, private-content, `git diff --cached --check` and staged Gitleaks checks run after this entry is staged; results are in the session handoff. No application tests or builds were run.
- **Not done:** no implementation, dependency installation, commit, push or merge. M3e, M3f, Compose verification and overall M3 acceptance remain pending.
- **Review status:** pending.

**Review note (recorded in Prompt 87):**
- **M3d `main` publication documentation accepted.** The reviewer inspected `.local/p86/m3e-api-spec.diff`; its checksum matched the reported value.
- **M3e specification not yet accepted.** The reviewer inspected it and requested the corrections in Prompt 87: read consistency, the upload-response observation time, the multipart parsing contract, the dependency wording and the privacy wording. M3e remains proposed.
- **No project tests run:** the reviewer did not run the project tests.

## Prompt 87: Correct M3e read consistency and upload parsing contracts

- **Stage:** Documentation corrections on branch `docs/m3e-api-spec` (staged and uncommitted for review; no commit, push or merge)
- **Date:** 2026-10-15 (session date)
- **Numbering:** 87 is the next unused number after Prompt 86; verified before appending.

````text
Prompt 87 — Correct M3e read consistency and upload parsing contracts

Work only inside D:\Claude\evidenceguard_agentic_rag. Follow CLAUDE.md.

Documentation corrections only. No implementation, commit, push, merge, dependency installation, Docker, database contact or global configuration change.

1. Verify starting state

Expected:
- Branch: docs/m3e-api-spec
- HEAD:
  cdf7260d02b8af9affb369cc805d666be61f9ac0
- Staged tree:
  89a9b73396f2b597e78ae143a69e52643170f75e
- Five staged files:
  README.md
  docs/decisions/0010-document-ingestion.md
  docs/plan.md
  docs/threat-model.md
  prompts.md
- Nothing unstaged or untracked.

If anything differs, stop and report it without changing anything.

Record the current staged tree as the incremental baseline.

2. Preserve accepted material

The reviewer accepts the M3d main-publication documentation. Its uploaded diff checksum matched the reported value.

Keep README.md, ADR-0010 and docs/threat-model.md byte-identical to the starting staged tree.

Keep M3e’s endpoint scope, authorization, upload caps, source formats, atomic creation, immutable revision rules and accepted ingestion_state projection.

Only docs/plan.md and prompts.md may change.

3. Correct read consistency

A. Chunk pagination

Remove the blanket claim that chunk pages are stable because individual rows are immutable.

An unsettled revision can receive additional chunk batches. Its count and page contents can change between requests.

Specify:
- stable ordinal ordering;
- partial-set pages are observations at a particular read snapshot;
- no cross-request snapshot guarantee while writes continue;
- settled chunk sets are immutable under the application invariant;
- verified_complete is not inferred merely from a matching row count.

Preserve the accepted visibility policy and repeated-header provenance.

B. One consistent snapshot per GET response

“One transaction” at default READ COMMITTED is insufficient when several SELECTs build one response.

Specify a short REPEATABLE READ, READ ONLY transaction for the M3e read operations, established before their first data query. Keep the upload write transaction at the existing isolation.

Within one GET response, use the same snapshot for:
- parent existence checks;
- document pointers and active/latest revision views;
- canonical job and ingestion_state;
- chunk-set metadata, stored_count, total and items.

Capture one database-time value for lease-expired calculations within that response.

Do not keep transactions open while sending response bodies. Define how connection-level settings are scoped/reset so pooled connections do not leak isolation or read-only settings into later writes.

This guarantees internal consistency within one response, not a shared snapshot across separate HTTP requests.

C. Upload response observation time

Specify exactly when the UploadResult state is observed:
- construct one internally consistent response snapshot within the creation transaction after the required writes;
- send it only after successful commit;
- do not independently re-read selected fields after commit and mix observation times.

A worker may change the state immediately after commit. Explain that the response reports the observed snapshot, not a promise that the state will remain pending or queued.

Preserve 202 for newly created revisions and 200 for duplicates.

Add planned PostgreSQL concurrency tests for:
- activation between document-view reads;
- a chunk batch committing between count and page reads;
- consistent revision/job projection;
- pooled-connection settings restored before a later upload write.

4. Tighten the multipart contract

A. Explicit parser completion

Specify validation of:
- required disposition headers and field names;
- syntactically valid boundary parameters;
- final closing boundary;
- truncated headers or part data;
- client disconnect.

Do not assume that calling MultipartParser.finalize() necessarily detects every truncated body. Implementation must verify the selected library’s actual behavior and explicitly track parser completion where needed.

No success response is allowed for a truncated multipart body.

B. Content-Length

Keep streaming byte counts authoritative for size enforcement.

When Content-Length is present and the ASGI server provides a normal completed stream, require the actual received body length to match it; otherwise 400.

For disconnects or transport rejection, abort without database writes. Do not guarantee a response can always be delivered after disconnect.

Tests may use controlled ASGI streams for mismatches a production HTTP server would reject before the application sees them.

C. Error precedence and bounds

Make the current precedence implementable:
- duplicate/unknown fields and a second file are structural 422 errors;
- exceeding a part-count or byte cap is 413;
- malformed parser input may prevent further meaningful parsing.

Specify which errors are deferred while bounded parsing continues and which terminate immediately. Do not promise that a later cap violation overrides an earlier parser failure after reading has already stopped.

Retain bounded memory and immediate enforcement of hard caps. Never drain an arbitrarily large invalid request solely to establish global error precedence.

Add mixed-fault tests with exact expected outcomes, including:
- duplicate field followed by excess parts;
- malformed multipart before a later oversized tail;
- missing closing boundary despite otherwise valid fields;
- short/long declared lengths with a normally completed ASGI stream.

5. Clarify dependency and privacy wording

The reviewer accepts using an established streaming multipart library in principle. No dependency is installed or selected by this prompt.

Keep release-age, compatibility and advisory checks as implementation prerequisites. Do not bypass the age policy or add a newer release silently.

Correct the broad privacy-test statement:
- errors and logs must not contain submitted content, filenames, arbitrary field names, values or internal exceptions;
- authorized successful responses intentionally contain documented metadata and, for ChunkView, chunk text;
- document views exclude raw source content;
- job views exclude the specified internal fields.

Add tests for both safe error/log behavior and intended authorized success fields.

6. Prompt history and verification

Append this prompt verbatim under the next unused number, expected 87, plus an accurate review/outcome note.

Record:
- M3d publication documentation accepted;
- M3e remains proposed;
- reviewer inspected the specification and checked its checksum;
- reviewer did not run project tests;
- corrections made and checks actually run.

Preserve earlier history byte-for-byte.

Run documentation consistency, relative-link/anchor and private-content checks, git diff --cached --check and staged Gitleaks.

No application tests or builds.

Keep all five files staged and uncommitted. Confirm the three unchanged documents remain byte-identical.

7. File-based handoff

Export the complete incremental diff against:
89a9b73396f2b597e78ae143a69e52643170f75e

Exclude prompts.md and save as:
.local/p87/m3e-spec-corrections.diff

Use UTF-8 without BOM. Do not print the diff.

Report the changes, actual checks, branch, HEAD, new staged tree, staged paths, file size and SHA-256.

End with:
“Return this output plus .local/p87/m3e-spec-corrections.diff to the external reviewer.”

Keep the current session. Nothing may be implemented, committed, pushed or merged.
````

**Outcome note (written before review; the changes are staged and uncommitted):**
- **Starting state verified:** branch `docs/m3e-api-spec`, HEAD `cdf7260`, staged tree `89a9b73` with the five expected paths, and nothing unstaged or untracked. That tree was recorded as the incremental baseline under `.local/p87/`.
- **Corrections (in `docs/plan.md` only):**
  - **Chunk pages:** the blanket stability claim is removed. Chunk pages are ordinal-ordered. Settled sets are immutable; unsettled sets can grow between requests, and each page is an observation at one read snapshot. `verified_complete` is never inferred from a matching count.
  - **One snapshot per GET response:** a transaction-scoped `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY` as the first statement, and one captured database time for every `lease_expired`. The transaction ends before the body is sent. No session-level settings are used, so pooled connections keep their defaults. The guarantee is consistency within one response only.
  - **Upload observation time:** the `UploadResult` is read in one statement inside the creation transaction after the writes, and sent only after the commit. It is never re-read afterwards, and it reports an observation, not a promise.
  - **Multipart contract:** required `Content-Disposition` and `name`, boundary syntax, explicit completion tracking (closing boundary and part ends) without relying on `finalize()`, and no 2xx for truncated bodies. A `Content-Length` mismatch on a normally completed stream is 400. A disconnect aborts without writes or a guaranteed response.
  - **Error precedence:** three implementable phases. Errors found while streaming terminate reading immediately, and the first one detected wins. Deferred checks run only after a normally completed stream. Exact mixed-fault outcomes are listed.
  - **Dependency wording:** an established streaming multipart library is accepted in principle, with none selected or installed. Release age, compatibility and advisories are implementation prerequisites.
  - **Privacy wording:** errors and logs are separated from intended authorized response fields.
  - **New planned tests:** read-consistency and pooled-setting tests in PostgreSQL, upload-observation tests, and mixed-fault, completion and privacy tests.
- **Unchanged:** endpoint scope, authorization, caps, source formats, atomic creation, revision rules and the projection. `README.md`, ADR-0010 and `docs/threat-model.md` are byte-identical to `89a9b73`.
- **Checks:** run after this entry is staged; results are in the session handoff. No application tests or builds were run.
- **Review status:** M3e remains **proposed** and unimplemented. Nothing is committed, pushed or merged.

**Review note (recorded in Prompt 88):**
- **Accepted:** the external reviewer accepted the complete M3e specification (Prompt 86) and its corrections (Prompt 87), subject to one final clarification made in Prompt 88: ASGI receive-message boundaries do not define error precedence.
- **How it was reviewed:** the reviewer inspected the supplied diffs `.local/p86/m3e-api-spec.diff` and `.local/p87/m3e-spec-corrections.diff`, and independently checked both reported SHA-256 checksums, which matched. The reviewer did not run project tests or documentation checks.
- **Still pending:** the M3e implementation and its verification.

## Prompt 88: Accept and commit the M3e specification locally

- **Stage:** Documentation acceptance and a local commit on branch `docs/m3e-api-spec` (no push or merge)
- **Date:** 2026-10-15 (session date)
- **Numbering:** 88 is the next unused number after Prompt 87; verified before appending.

````text
Prompt 88 — Accept and commit the M3e specification locally

Work only inside D:\Claude\evidenceguard_agentic_rag. Follow CLAUDE.md.

The external reviewer accepts the M3e specification from Prompt 86 plus the Prompt 87 corrections, with the narrow test clarification below.

Local documentation commit only. No implementation, dependency installation, push, merge, history rewrite, Docker, database contact or global configuration change.

1. Verify starting state

Expected:
- Branch: docs/m3e-api-spec
- HEAD:
  cdf7260d02b8af9affb369cc805d666be61f9ac0
- Staged tree:
  07d71534733ea870753b95c03d29918729f4b962
- Five staged paths:
  README.md
  docs/decisions/0010-document-ingestion.md
  docs/plan.md
  docs/threat-model.md
  prompts.md
- Nothing unstaged or untracked.
- Expected origin:
  https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git
- Effective author and committer:
  257921624+mathewmljourney93@users.noreply.github.com

If anything differs, stop and report it without changing anything.

Record the accepted staged tree before editing.

2. Final narrow clarification

In the M3e multipart specification and planned tests, clarify that ASGI receive-message boundaries do not define semantic error precedence.

For the same body bytes:
- preserve the specified order of detection;
- enforce byte caps at the correct position while feeding the parser;
- do not let receiving one large ASGI message make a later oversized tail override an earlier malformed or duplicate part;
- do not require byte-at-a-time processing; bounded slices and parser callbacks are acceptable.

Add planned tests presenting the same mixed-fault bodies:
- in one receive message;
- split across multiple messages;
- with splits inside headers, boundaries and file data.

Require equivalent status outcomes and no database writes. Do not claim tests have been implemented or run.

Do not otherwise redesign the parser contract or scope.

3. Record specification acceptance

Update README.md and docs/plan.md narrowly:
- M3e specification accepted at external review.
- Implementation pending.
- Numeric caps and pagination bounds are initial engineering choices, not measured results.
- The multipart library is accepted in principle, with exact release selection subject to the existing age, compatibility and advisory prerequisites.
- M3f, Compose verification and overall M3 acceptance remain pending.

Make the M3e status and decision wording internally consistent. Preserve accepted endpoint, transaction, projection and privacy contracts.

Keep ADR-0010 and docs/threat-model.md byte-identical to the accepted staged tree.

4. Prompt history

Append a review note under Prompt 87 recording:
- acceptance of the complete M3e specification and corrections, with the final ASGI partitioning clarification;
- that the reviewer inspected the supplied diffs and independently checked both reported checksums;
- that the reviewer did not run project tests or documentation checks;
- that implementation and its verification remain pending.

Append this prompt verbatim using the next unused number, expected 88, with a truthful pre-commit note.

Preserve earlier history byte-for-byte. Do not pre-record successful commits or include this commit’s own SHA in its content.

5. Verify and commit locally

Only README.md, docs/plan.md and prompts.md may change relative to the accepted staged tree.

Verify:
- exactly the five authorized files staged;
- ADR-0010 and threat model byte-identical;
- no artifacts, secrets or unrelated changes;
- documentation consistency and relative links/anchors;
- git diff --cached --check;
- staged Gitleaks;
- effective identity.

No application tests or builds are needed.

Commit with subject:
docs: record accepted M3e upload and document API specification

Preserve the existing co-author convention.

After committing:
- verify parent, identity and committed paths;
- run full-history Gitleaks;
- confirm a clean working tree;
- confirm main was not changed.

Do not push or start implementation.

6. Export and hand off

Export the complete incremental diff from:
07d71534733ea870753b95c03d29918729f4b962

to the new commit, excluding prompts.md, as:
.local/p88/m3e-spec-acceptance.diff

Write UTF-8 without BOM directly from Git output. Do not print the diff.

Report:
- commit SHA, parent, subject and identity;
- changed paths;
- actual verification results;
- prompt-history additions;
- final Git state;
- baseline, final commit, diff path, byte size and SHA-256.

Keep the current Claude session.

End with:
“Return this output plus .local/p88/m3e-spec-acceptance.diff to the external reviewer.”
````

**Pre-commit note (written before the commit; the commit's own SHA is not recorded here):**
- **Starting state verified:** branch `docs/m3e-api-spec`, HEAD `cdf7260`, staged tree `07d7153` with the five expected paths and nothing unstaged or untracked. The origin and the noreply author and committer identity were as expected. The accepted tree was recorded under `.local/p88/`.
- **Clarification (`docs/plan.md`):** ASGI receive-message boundaries do not define precedence.
  - For the same body bytes, errors are detected in byte order, with caps enforced at the exact crossing position while bounded slices are fed to the parser.
  - A later oversized tail in the same large message never overrides an earlier malformed or structural error.
  - Byte-at-a-time processing is not required.
  - Planned tests present each mixed-fault body in one message, across several messages, and split inside headers, boundaries and file data, requiring the same status and no store or database call. The tests are planned, not implemented or run.
- **Acceptance wording (`README.md`, `docs/plan.md`):**
  - the M3e specification is accepted at external review, and its implementation is pending;
  - the caps and pagination bounds are initial engineering choices, not measured results;
  - the multipart library is accepted in principle, with release selection subject to the age, compatibility and advisory prerequisites;
  - M3f, Compose verification and overall M3 acceptance remain pending.

  ADR-0010 and `docs/threat-model.md` are byte-identical to `07d7153`.
- **Checks for this commit:** the documentation, staged-scan and identity checks, and the post-commit checks, run after this entry is staged; results are in the session handoff. No application tests or builds were run.
- **Not done:** no M3e implementation, no dependency installed, nothing pushed or merged.

**Commit outcome (recorded in Prompt 89):**
- **Commit:** `98ca70b8e43ff4fd74349647b520213962374151` ("docs: record accepted M3e upload and document API specification"), parent `cdf7260d02b8af9affb369cc805d666be61f9ac0`, on `docs/m3e-api-spec`, with the noreply author and committer identity.
- **Checks reported in the Prompt 88 handoff:** full-history Gitleaks scanned 35 commits with no leaks found; the working tree was clean afterwards and `main` was unchanged.
- **Diff:** `.local/p88/m3e-spec-acceptance.diff`, 16,305 bytes, SHA-256 `38640973a57eea3f270840df0fcb4556569bef72236d9ef8878cbad2ef36dbbc`.
- Nothing was pushed or merged.

**Review note (recorded in Prompt 89):**
- **Accepted:** the external reviewer accepted the Prompt 88 incremental diff.
- **How it was reviewed:** the reviewer inspected `.local/p88/m3e-spec-acceptance.diff` and independently computed its SHA-256, which matched the reported value. The reviewer ran no project checks.
- **Next:** Prompt 89 authorizes the M3e implementation, staged and uncommitted for review.

## Prompt 89: Implement the accepted M3e upload and document API specification

- **Stage:** Implementation on branch `feat/document-api`, created from `98ca70b`; staged and uncommitted for external review (no commit, push or merge)
- **Date:** 2026-10-15 (session date)
- **Numbering:** 89 is the next unused number after Prompt 88; verified before appending.

````text
Written for: Mathew and the external reviewer.

Prompt 89: Implement the accepted M3e upload and document API specification

Implement M3e according to the accepted specification in docs/plan.md, including the corrections in Prompts 87–88. Leave the work staged and uncommitted for external review.

Do not commit, push, merge, amend, rebase, change main, start Docker, or contact a local database. Do not begin M3f.

1. Verify the starting state

Work only within D:\Claude\evidenceguard_agentic_rag, apart from necessary installed-tool/reference access allowed by CLAUDE.md.

Read CLAUDE.md and the relevant accepted M3e specification and architecture records. Avoid rereading the complete prompts.md history; inspect its tail and relevant entries only.

Expected state:
- Branch: docs/m3e-api-spec.
- HEAD: 98ca70b8e43ff4fd74349647b520213962374151.
- Parent: cdf7260d02b8af9affb369cc805d666be61f9ac0.
- Working tree clean, with nothing staged, unstaged or untracked.
- Local main and origin/main: cdf7260d02b8af9affb369cc805d666be61f9ac0.
- Origin: https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git.
- Effective author and committer email:
  257921624+mathewmljourney93@users.noreply.github.com.

Stop and report any material mismatch without overwriting work.

Create feat/document-api from the verified HEAD. If that branch already exists, inspect and report its state before proceeding.

2. Implement the accepted scope

Use docs/plan.md as the detailed contract. Implement all six M3e endpoints:
- POST /v1/vendors/{vendor_id}/documents.
- GET /v1/vendors/{vendor_id}/documents.
- GET /v1/documents/{document_id}.
- GET /v1/documents/{document_id}/revisions.
- GET /v1/documents/{document_id}/revisions/{revision_no}/chunks.
- GET /v1/jobs/{job_id}.

Preserve the accepted role restrictions, tenant scoping, foreign-object 404 behaviour, pagination bounds, response fields, safe errors and privacy rules.

Reuse the existing persistence, authentication, database wiring, worker and revision contracts. Avoid unrelated refactoring.

3. Multipart dependency and upload parsing

An established streaming multipart library is authorized in principle. Before adding it:
- Inspect the repository’s dependency-age policy.
- Check official release information, compatibility with the locked stack, and published security advisories.
- Select an eligible release and retain the age policy.
- Record the selected version, sources and reasoning.
- Update pyproject.toml and uv.lock as needed.

Do not bypass the policy. If no suitable release is available, report the concrete blocker.

Use the streaming parser API with bounded in-memory buffers and no temporary files. Do not use automatic Form/File/UploadFile body parsing.

Implement the complete accepted multipart contract, including:
- Authentication, authorization and vendor validation before reading body bytes.
- Header, boundary, part, field, file and whole-request limits.
- Exact byte preservation, strict UTF-8 validation and the accepted content rules.
- Explicit part-end and closing-boundary tracking.
- Disconnect handling and normally completed Content-Length mismatch handling.
- The three-phase error precedence.
- Byte-order error detection independent of ASGI receive-message partitioning.

Verify the selected parser’s actual completion and callback behaviour. Do not assume finalize() detects truncation.

Tests must exercise the same mixed-fault bytes in one receive message and multiple partitions, including splits inside headers, boundaries and file data. A later oversized tail must not override an earlier parser or structural error.

“No store/database call” in rejected-body tests means no upload-creation operation or write after the permitted authentication and vendor prechecks. Keep those prechecks before body consumption.

4. Atomic upload creation and response observation

Create the revision and canonical ingestion job in one caller-owned transaction.

Implement the accepted new-versus-duplicate response behaviour, metadata conflicts, missing-job repair restrictions and terminal-job preservation.

Build UploadResult from one SQL statement inside that transaction after the writes. Send it only after commit succeeds. Do not independently reread after commit.

Keep synchronous database work off the async event loop. Preserve truthful observations of revision and job state, including duplicate uploads whose ingestion has already advanced.

5. Consistent, read-only views

Implement the proposed document_views persistence module and typed API response models.

For each GET:
- Start a short read transaction.
- Make SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY its first statement before data access.
- Capture clock_timestamp() once for the response.
- Read parent checks, pointers, revisions, job projection, counts, chunk metadata and items from that snapshot.
- Construct immutable result values within the transaction.
- End the transaction before sending the response.
- Ensure pooled connections retain no read-only or isolation-setting changes.

Uploads continue using READ COMMITTED.

Implement the accepted ingestion_state table, canonical-job lookup and lease_expired projection. GET requests must never repair or modify state.

Keep partial chunk inspection honest: verified_complete depends on settled revision status and the activation invariant, not count equality. Preserve separate repeated-header provenance.

6. Tests

Implement the accepted database-independent and PostgreSQL test plans.

Include meaningful coverage of:
- Roles, tenant isolation and parent-child lookups.
- Authentication and vendor checks before body reads.
- Multipart limits, completion, mixed faults, partition invariance and disconnects.
- Atomic creation, duplicate observations and conflict mappings.
- Safe errors/logs and intentionally exposed success fields.
- Every ingestion_state case.
- Read-only GET behaviour and bounded pagination.
- Concurrent activation, chunk insertion and revision/job changes during reads.
- Connection settings restored before a subsequent upload.
- Upload-to-production-worker-to-read-model integration.

Use real PostgreSQL for the integration tests in CI. Do not substitute SQLite or claim that mocks verify PostgreSQL behaviour.

Do not run PostgreSQL tests locally without an authorized disposable database. Keep them pending CI.

7. Documentation and prompt history

Add ADR-0011 for the implemented M3e design and its tradeoffs.

Update README.md, docs/plan.md and docs/threat-model.md accurately:
- Implementation staged and awaiting review.
- Actual local verification results.
- PostgreSQL and Linux verification pending CI.
- Compose, M3f and overall M3 acceptance still pending.
- No performance or general security claims.

Do not mark M3e accepted as an implementation merely because its specification was accepted.

Append to prompts.md without changing earlier entries:
- Prompt 88’s reported local commit outcome.
- The reviewer’s acceptance of its supplied incremental diff and independently matched checksum; the reviewer ran no project checks.
- This prompt verbatim, using the next unused number if numbering has changed.
- A truthful outcome note.

8. Verification and review handoff

Run the relevant targeted tests during implementation, then one final verification after corrections:
- uv sync --locked
- Ruff format check and lint
- Strict Mypy
- Full database-independent suite, reporting all skips
- Build
- Isolated installed-wheel checks for the changed API/package behaviour
- git diff --cached --check
- Staged Gitleaks scan
- Private-content and tracked-artifact checks

Use the repository’s established commands and tooling. Report failures and fixes honestly. Do not repeatedly rerun unchanged checks without a reason.

Stage only the intended implementation, tests, dependency and documentation files.

Export the COMPLETE staged diff against HEAD, excluding prompts.md, directly from Git to:
.local/p89/m3e-implementation.diff

Use UTF-8 without a BOM. Do not print the diff in chat or truncate it.

Report:
- Summary of behaviour and important implementation decisions.
- Dependency selection and source references.
- Verification commands and actual results.
- Known limitations and anything deviating from the accepted specification.
- Branch, HEAD, staged tree, staged paths and working-tree status.
- Diff path, baseline, final tree, byte size and SHA-256.

Keep the current session. Do not recommend restarting merely because this implementation is substantial; flag a new session only for a concrete context problem or after roughly 20 substantial prompts as a guideline.

End with:
“Return this output plus .local/p89/m3e-implementation.diff to the external reviewer.”

Nothing is authorized to be committed, pushed or merged.
````

**Outcome note (written before staging; implementation awaiting external review):**
- **Starting state verified:** branch `docs/m3e-api-spec` at `98ca70b` (parent `cdf7260`) with a clean tree; `main` and `origin/main` at `cdf7260`; origin and the noreply identity as expected. Branch `feat/document-api` was created from `98ca70b`.
- **Dependency:** `python-multipart` 0.0.32, published 2026-06-04, with an `exclude-newer-package` cutoff of `2026-10-01T00:00:00Z` (the age policy was not bypassed). The PyPI metadata lists no vulnerabilities and OSV no advisory affecting 0.0.32; the historical advisories were fixed in 0.0.7 to 0.0.31. It is compatible with the locked FastAPI 0.143.0 and Starlette 1.7.0.
- **Implemented (staged, unreviewed):**
  - the six endpoints;
  - the bounded multipart reader with explicit completion tracking;
  - atomic creation with a single-statement observation returned after commit;
  - REPEATABLE READ, READ ONLY read snapshots;
  - the `ingestion_state` projection;
  - ADR-0011 and status updates in README, plan and threat model.
- **Parser finding:** `python-multipart` 0.0.32 checks a header name's size before its characters, across the whole span to the next colon or the end of the write. With large writes, an earlier invalid character could therefore be reported as a later 413. The reader feeds header and boundary regions one byte at a time, and part data in slices that stop before each delimiter. Tests reproduce the case in both directions.
- **Checks actually run in this session (Windows, local):**
  - `uv sync --locked`, `ruff format --check .`, `ruff check .` and `mypy` (101 source files): passed;
  - full suite: `1214 passed, 192 skipped`. Every skip is a PostgreSQL integration test without `EG_TEST_DATABASE_URL`: the 179 existing ones plus the 13 new M3e tests;
  - `uv build`, and installed-wheel checks in a clean venv under `.local/p89/`: imports, both CLIs, the production registry, offline migration SQL, and a 202 upload through a test double with the routes registered.

  The staged-diff, whitespace, Gitleaks and artifact checks run after this entry is staged; their results are in the session handoff.
- **Pending:**
  - **the PostgreSQL integration tests are written but not run** (no authorized disposable database), and Linux CI has not run;
  - concurrent identical uploads through the API, and event-controlled interleavings inside one view, are not covered yet;
  - external review, Compose, M3f and overall M3 acceptance.
- **Not done:** nothing committed, pushed or merged; `main` unchanged; no Docker or database contact.

**Review note (recorded in Prompt 90):**
- **How it was reviewed:** the external reviewer inspected the complete supplied diff `.local/p89/m3e-implementation.diff` and matched its SHA-256 against the reported value. The reviewer ran isolated parser probes with `python-multipart` 0.0.32 against the supplied upload reader; the reviewer did not run the project suite or the PostgreSQL tests.
- **Not accepted yet.** Findings:
  - **Header-byte cap undercount:** the parser consumes leading spaces in `HEADER_VALUE_START` without reporting them through `on_header_value`. Two headers of the form `X-One:<5000 spaces>a` and `X-Two:<5000 spaces>b`, each below the line cap, passed parsing with over 10,000 header bytes, because the aggregate cap counted reported names and values plus a synthetic 4 bytes per line.
  - **Lossy parameter parsing:** `parse_options_header` ignores extended parameters containing `*` and collapses repeated names. So `filename*` on a text field evaded the no-filename rule, `text/plain; charset*=utf-8''latin-1` was accepted, and `text/plain; charset=latin-1; charset=utf-8` was accepted after the first value was overwritten.
  - **Missing verification:** PostgreSQL tests that the accepted specification required were omitted. They cover concurrent uploads through the API, interleavings inside one response, the pooled connection after a snapshot followed by a real write, duplicates against real rows, the missing-job behaviour of GET, and the upload observation boundary.
  - **Skip accounting:** the reported "192 PostgreSQL skips, including 179 existing tests" appears to include the Windows POSIX-only signal skip; the earlier baseline had 178 PostgreSQL tests and one POSIX-only skip.

## Prompt 90: Correct M3e multipart validation and complete the agreed tests

- **Stage:** Correction of the staged M3e implementation on `feat/document-api`; staged and uncommitted for external review (no commit, push or merge)
- **Date:** 2026-10-15 (session date)
- **Numbering:** 90 is the next unused number after Prompt 89; verified before appending.

````text
Written for: Mathew and the external reviewer.

Prompt 90: Correct M3e multipart validation and complete the agreed tests

Correct the reviewed M3e implementation. Leave everything staged and uncommitted.

Do not commit, push, merge, amend, rebase, change main, start Docker, contact a local database, or begin M3f.

1. Verify and record the starting state

Expected:
- Branch: feat/document-api.
- HEAD: 98ca70b8e43ff4fd74349647b520213962374151.
- Staged tree: ce122c308c4179d092b0845f671ee6ce062d2fba.
- Exactly the 19 paths reported in Prompt 89 staged.
- Nothing unstaged or untracked.
- Local main and origin/main unchanged at cdf7260d02b8af9affb369cc805d666be61f9ac0.
- Existing origin and repository-local noreply identity unchanged.

Record the pre-edit staged tree under .local/p90/. Use that tree as the incremental review baseline.

Stop on a material mismatch without overwriting work.

Read CLAUDE.md and relevant code/specification sections. Do not reload the entire prompt history.

2. Fix the actual multipart header-byte cap

The reviewer reproduced this against the supplied upload reader and python-multipart 0.0.32:

A valid part with these additional headers passes parsing despite containing over 10,000 header bytes:

X-One:<5000 spaces>a\r\n
X-Two:<5000 spaces>b\r\n

Each individual line stays below the parser’s line cap. The parser consumes leading spaces in HEADER_VALUE_START without reporting them through on_header_value. Consequently, _Collector’s name/value callbacks plus synthetic four-byte overhead undercount the actual aggregate header bytes.

Correct the aggregate cap to count the actual received header bytes, including whitespace and syntax, according to an explicit, consistent definition of the header region. Do not approximate it using normalized header names and values.

Preserve:
- The accepted 8 KiB cap.
- First-error detection in byte order.
- ASGI receive-partition invariance.
- Existing safe errors and parser-log suppression.
- Bounded memory and no temporary files.

Add regressions for:
- The two whitespace-heavy headers above.
- Exact-limit and one-byte-over-limit cases.
- Header lines without the optional space after the colon.
- An aggregate cap crossing before a later malformed byte, and the reverse ordering.
- Single-message and fragmented presentations.

Demonstrate that the whitespace-heavy regression fails against the previous implementation, then restore the corrected files and verify their identity.

3. Validate parameters before information is discarded

python-multipart 0.0.32’s parse_options_header ignores extended parameters containing "*", and collapses repeated parameter names.

Consequences in the current implementation:
- Checking b"filename*" in its returned dictionary cannot detect that parameter.
- A text field with filename* can evade the no-filename rule.
- A file Content-Type such as text/plain; charset*=utf-8''latin-1 is accepted because the unsupported parameter disappears.
- text/plain; charset=latin-1; charset=utf-8 is accepted after the first value is overwritten.

Validate the relevant raw parameter structure without relying on a lossy dictionary to prove that disallowed parameters were absent.

Keep the accepted contract:
- Text fields cannot carry filenames.
- File media types are text/plain or text/markdown, optionally with the permitted UTF-8 charset.
- Unsupported or ambiguous charset parameters must not become accepted because parsing dropped or overwrote them.
- Disposition structural errors are safe 422 responses.
- File media-type errors remain deferred 415 responses at the accepted phase.
- No submitted parameter text appears in errors or logs.

Use established parsing facilities where suitable. Do not introduce a replacement multipart parser or another dependency without a concrete need.

Add focused tests for extended filename parameters on text fields, extended media parameters, conflicting duplicate charset parameters, and ordinary valid quoted/token forms. Preserve receive-partition invariance.

4. Complete the accepted PostgreSQL verification plan

The accepted specification explicitly required tests that are currently omitted. Implement them using the existing guarded disposable-database fixtures, but do not execute them locally.

Add deterministic, bounded tests for:
- Concurrent identical uploads through the real API: one revision, one canonical job, one 202 and a duplicate 200.
- Concurrent different-content uploads with correct revision allocation.
- Activation committing between the document pointer and revision reads of one response.
- A chunk batch committing between a chunk count and page-item read.
- Consistent revision/job projection while a worker transaction changes their state.
- A later upload on the same pooled connection after a read-only snapshot: settings restored and the upload actually writes successfully.
- Duplicate uploads of processing, superseded, failed and dead-job revisions against real rows, preserving terminal jobs and returning the actual observed state.
- The remaining accepted SQL projection and partial-chunk cases not already meaningfully covered.

Use explicit events/barriers or controlled query hooks, bounded waits and reliable cleanup. Do not use timing-only sleeps as the proof of an interleaving.

Exercise the production store/read operations. A generic test showing that PostgreSQL supports REPEATABLE READ does not replace tests of the actual multi-query operations.

Improve the existing missing-job test:
- After deleting the canonical job, GET must report stalled with no job and leave the database unchanged.
- Only a subsequent permitted duplicate POST repairs the missing job.
- Verify that GET itself never repairs anything.

Add a focused test of the upload observation boundary: a state change immediately after commit must not cause a post-commit reread or replace the observation returned by the creation transaction.

Review the accepted test matrix for other omissions. Reuse existing meaningful coverage rather than adding redundant tests.

5. Correct documentation and verification accounting

Check the actual skip reasons and integration collection count.

The reported “192 PostgreSQL skips, including 179 existing tests” appears to include the Windows POSIX-only signal skip. The earlier baseline had 178 PostgreSQL tests and one POSIX-only Windows skip; 13 added PostgreSQL tests would produce 191 PostgreSQL skips plus that signal skip.

Report the actual breakdown after these corrections, based on collection and skip reasons. Do not change markers just to match an expected count.

Update ADR-0011, the plan, README and threat model only where needed:
- Explain the corrected raw-header counting and parameter validation.
- Remove claims that the agreed concurrency tests are intentionally outside this slice once they are written.
- Distinguish tests written from tests executed.
- Keep implementation review, PostgreSQL execution, Linux CI, Compose, M3f and overall M3 acceptance pending as appropriate.
- Scope historical “no document endpoints” statements to their named baseline where necessary.

Do not weaken the accepted specification to match incomplete implementation.

6. Prompt history

Preserve earlier prompts.md bytes.

Append:
- A review note recording that the reviewer inspected the complete supplied diff and matched its checksum.
- The concrete header-counting and parameter findings, the missing verification, and the skip-accounting correction.
- State that the reviewer ran isolated parser probes with python-multipart 0.0.32, not the project suite or PostgreSQL tests.
- This prompt verbatim.
- A truthful outcome note.

Do not record acceptance of the implementation yet.

7. Verification and handoff

Run focused regression tests during correction, followed by one final appropriate verification:
- uv sync --locked
- Ruff formatting and lint
- Strict Mypy
- Full database-independent suite, with actual skip breakdown
- Integration-test collection without contacting a database
- Build and isolated installed-wheel checks appropriate to the changed parser
- git diff --cached --check
- Staged Gitleaks and private-content/artifact checks

Do not repeatedly rerun unchanged checks without a reason.

Keep the corrected work staged and uncommitted.

Export the COMPLETE incremental diff against staged tree
ce122c308c4179d092b0845f671ee6ce062d2fba,
excluding prompts.md, directly from Git to:

.local/p90/m3e-corrections.diff

Use UTF-8 without a BOM. Do not print the diff in chat.

Report:
- Findings corrected and relevant design choices.
- Regression results against the previous implementation.
- Verification commands and actual results.
- PostgreSQL tests added and their still-unexecuted status.
- Branch, HEAD, final staged tree and staged paths.
- Diff baseline, final tree, byte size and SHA-256.
- Any remaining deviation from the accepted specification.

Keep the current Claude session.

End with:
“Return this output plus .local/p90/m3e-corrections.diff to the external reviewer.”
````

**Outcome note (written before staging; corrections awaiting external review, implementation not accepted):**
- **Starting state verified:**
  - branch `feat/document-api`, HEAD `98ca70b`, staged tree `ce122c308c4179d092b0845f671ee6ce062d2fba` with the 19 Prompt 89 paths;
  - nothing unstaged or untracked;
  - `main` and `origin/main` at `cdf7260`; origin and the noreply identity unchanged.

  The baseline tree is recorded under `.local/p90/`.
- **Header-byte cap:** the per-part 8 KiB cap now counts the raw header region. That is every byte the parser consumes in a header state, from after the boundary line's line ending through the empty line's line ending, inclusive. It no longer counts callback-reported names and values plus a synthetic overhead. The feeder already sends header regions one byte at a time, so it refuses the byte that crosses the cap before the parser sees it. Earlier malformed bytes still win, and the result does not depend on receive partitioning.
- **Parameters:** a strict RFC 9110 parameter parser keeps extended and repeated parameters, and replaces `parse_options_header` for the request `Content-Type`, the part `Content-Disposition` and the file `Content-Type`. As a result:
  - `filename*` on a text field is a 422;
  - `charset*` and repeated or conflicting `charset` parameters are deferred 415s;
  - repeated, extended or missing disposition `name` parameters are 422;
  - repeated or extended `boundary` parameters are 415.
- **Regression demonstration:** with the Prompt 89 reader temporarily restored from the baseline index blob, 23 of the new regression tests failed, including the whitespace-heavy headers, every exact-limit case and the lossy-parameter cases. The corrected file was restored, and its SHA-256 matched the saved copy.
- **PostgreSQL tests:** 13 tests were added or strengthened, for 26 in `tests/test_document_api_postgres.py`. They cover:
  - concurrent identical and different uploads through the API (barrier);
  - activation between the pointer and revision reads, a job and revision change mid-read, and a chunk batch between the count and page reads (deterministic statement hooks on a separate engine);
  - a later upload writing on the same pooled connection after a snapshot;
  - duplicates of processing, superseded, failed and dead-job revisions;
  - GET never repairing a missing job, while a duplicate POST does;
  - the upload observation boundary;
  - terminal jobs with unsettled revisions;
  - partial chunk sets.

  They are **written, not executed**.
- **Skip accounting corrected:** Prompt 89's suite had 191 PostgreSQL skips plus 1 Windows POSIX-only signal skip, not "179 existing + 13". This run has 204 PostgreSQL skips (178 earlier + 26 M3e) plus that 1 signal skip, which matches the integration collection of 204.
- **Checks actually run in this session (Windows, local):**
  - `uv sync --locked`, `ruff format --check .`, `ruff check .` and `mypy` (101 source files): passed;
  - full suite: `1260 passed, 205 skipped`;
  - integration collection without a database: `204/1465 tests collected`;
  - `uv build`, and installed-wheel checks in a clean venv under `.local/p90/`: imports, both CLIs, the registry, offline migration SQL, a 202 upload through a test double, and the corrected parser behaviour (raw header cap 413, `filename*` 422, `charset*` 415).

  The staged-diff, whitespace, Gitleaks and artifact checks run after this entry is staged; their results are in the session handoff.
- **Pending:**
  - external review of the corrections;
  - execution of the PostgreSQL tests in CI;
  - Linux CI, Compose, M3f and overall M3 acceptance.
- **Not done:** nothing committed, pushed or merged; `main` unchanged; no Docker or database contact.

**Acceptance note (recorded in Prompt 91):**
- **Accepted:** the external reviewer accepted the Prompt 89 implementation plus the Prompt 90 corrections for a local commit.
- **What the reviewer inspected:** the complete Prompt 89 implementation diff (`.local/p89/m3e-implementation.diff`) and the Prompt 90 incremental correction diff (`.local/p90/m3e-corrections.diff`). Both supplied SHA-256 checksums independently matched.
- **Findings and their correction:** the reviewer had earlier reproduced the raw-header counting and lossy-parameter findings with isolated probes against `python-multipart` 0.0.32. After the correction, isolated probes rejected the oversized headers with 413 and the tested invalid charset parameters with 415.
- **PostgreSQL tests:** the reviewer inspected the added concurrency and state tests but did not execute them.
- **Basis:** acceptance also relies on the reported Windows checks (`1260 passed, 205 skipped`: 204 PostgreSQL tests and one POSIX-only signal test). The reviewer did not run the project suite or the PostgreSQL tests.
- **Pending:** CI verification (PostgreSQL and Linux), Compose, M3f and overall M3 acceptance.

## Prompt 91: Commit the reviewed M3e implementation locally

- **Stage:** Acceptance wording and a local commit on branch `feat/document-api` (no push or merge)
- **Date:** 2026-10-15 (session date)
- **Numbering:** 91 is the next unused number after Prompt 90; verified before appending.

````text
Written for: Mathew and the external reviewer.

Prompt 91: Commit the reviewed M3e implementation locally

Commit the reviewed M3e implementation locally. No push, merge or main update is authorized.

1. Verify the starting state

Expected:
- Branch: feat/document-api.
- HEAD: 98ca70b8e43ff4fd74349647b520213962374151.
- Staged tree: a2e6ed04c897a0c79ebcf2fcba50efd86b99942c.
- The same 19 staged paths reported in Prompt 90.
- Nothing unstaged or untracked.
- Local main and origin/main unchanged at cdf7260d02b8af9affb369cc805d666be61f9ac0.
- Origin:
  https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git
- Effective author and committer:
  mathewmljourney93 <257921624+mathewmljourney93@users.noreply.github.com>

Record the accepted staged tree under .local/p91/ before editing.

Stop on a material mismatch without overwriting work.

2. Preserve the accepted implementation

The external reviewer accepts the Prompt 89 implementation plus the Prompt 90 corrections for a local commit.

Do not change application code, tests, dependencies, migrations, workflows or configuration in this step.

Outside prompts.md, permit only narrow acceptance/status wording in:
- README.md
- docs/decisions/0011-document-api.md
- docs/plan.md
- docs/threat-model.md

Record:
- M3e accepted at external review for a local commit.
- The reported Windows verification: 1260 passed, 205 skipped.
- The skips comprise 204 PostgreSQL tests and one POSIX-only signal test.
- The 26 M3e PostgreSQL tests are written but have not executed.
- PostgreSQL and Linux verification of this implementation remain pending CI.
- Compose, M3f and overall M3 acceptance remain pending.
- Nothing is published or merged.

Keep historical results and their attribution intact. Do not mark overall M3 accepted.

3. Prompt history

Preserve all earlier prompts.md bytes.

Append an acceptance note under Prompt 90 stating:
- The reviewer inspected the complete Prompt 89 implementation diff and Prompt 90 incremental correction diff.
- Both supplied checksums independently matched.
- The reviewer previously reproduced the raw-header counting and lossy-parameter findings with isolated probes against python-multipart 0.0.32.
- After correction, isolated probes rejected the oversized headers with 413 and the tested invalid charset parameters with 415.
- The reviewer inspected the added PostgreSQL concurrency and state tests but did not execute them.
- Acceptance also relies on the reported Windows checks.
- The reviewer did not run the project suite or PostgreSQL tests.
- CI verification remains pending.

Append this prompt verbatim, using the next unused prompt number if necessary, and a truthful pre-commit note.

Do not write the new commit’s own SHA into a file included in that commit. Report it in the handoff instead.

4. Check and commit locally

Confirm:
- Exactly the intended 19 paths are staged.
- No .local/, build output, environment files, backups or credentials are staged.
- Earlier prompt-history content is byte-identical.
- Every file outside the four permitted documents and prompts.md is byte-identical to accepted tree a2e6ed04c897a0c79ebcf2fcba50efd86b99942c.
- Documentation links remain valid.
- Staged additions contain no private information or secrets.
- git diff --cached --check passes.
- The staged Gitleaks scan passes.
- Author and committer use the repository’s noreply identity.

No application tests or builds need rerunning because implementation files must remain unchanged.

Create the local commit with subject:

feat: add bounded document uploads and tenant-scoped read API

Retain the existing co-author convention.

After committing:
- Run the full-history Gitleaks scan.
- Verify the parent, committed paths and identity.
- Verify byte identity against the accepted tree outside the explicitly permitted documentation and prompt-history changes.
- Verify the working tree is clean.
- Confirm main and origin/main remain unchanged.

Do not push, merge, amend, rebase, delete branches, create tags, start Docker or contact a database.

5. Review handoff

Export the COMPLETE incremental diff from accepted tree
a2e6ed04c897a0c79ebcf2fcba50efd86b99942c
to the new commit, excluding prompts.md, directly from Git to:

.local/p91/m3e-commit-incremental.diff

Use UTF-8 without a BOM. Do not print the diff in chat.

Report:
- Commit SHA, parent, subject, author and committer.
- Committed paths.
- Narrow documentation changes.
- Verification commands and actual results.
- Final Git status and unchanged main refs.
- Diff path, baseline, final commit, byte size and SHA-256.
- Pending PostgreSQL, Linux, Compose, M3f and overall M3 verification.

Keep the current Claude session.

End with:
“Return this output plus .local/p91/m3e-commit-incremental.diff to the external reviewer.”
````

**Pre-commit note (written before the commit; the commit's own SHA is not recorded here):**
- **Starting state verified:**
  - branch `feat/document-api`, HEAD `98ca70b`, staged tree `a2e6ed04c897a0c79ebcf2fcba50efd86b99942c` with the same 19 paths;
  - nothing unstaged or untracked;
  - `main` and `origin/main` at `cdf7260`;
  - origin and the noreply author and committer identity as expected.

  The accepted tree is recorded under `.local/p91/`.
- **Changes in this step:** narrow acceptance and status wording only, in `README.md`, `docs/decisions/0011-document-api.md`, `docs/plan.md` and `docs/threat-model.md`. The wording records:
  - M3e accepted at external review for a local commit;
  - the reported Windows verification (`1260 passed, 205 skipped`: 204 PostgreSQL tests and one POSIX-only signal test);
  - the 26 M3e PostgreSQL tests written but not executed;
  - PostgreSQL and Linux verification pending CI;
  - Compose, M3f and overall M3 acceptance pending;
  - nothing published or merged.

  No application code, tests, dependencies, migrations, workflows or configuration changed.
- **Checks for this commit:** run after this entry is staged; results are in the session handoff. They are the staged-path, byte-identity, link, private-content, `git diff --cached --check`, staged Gitleaks and identity checks, and after the commit the full-history Gitleaks scan. No application tests or builds were rerun, because the implementation files are byte-identical to the accepted tree.
- **Not done:** nothing pushed or merged; `main` unchanged; no Docker or database contact.

**Commit outcome (recorded in Prompt 92):**
- **Commit:** `0dd1ebde0430322a6283420973fcb7b6f63d6019` ("feat: add bounded document uploads and tenant-scoped read API"), parent `98ca70b8e43ff4fd74349647b520213962374151`, tree `353bdefaca51702cdf826987a5440f76d7916c2b`, on `feat/document-api`, with the noreply author and committer identity.
- **Content:** the 19 reviewed paths. Only `README.md`, ADR-0011, `docs/plan.md`, `docs/threat-model.md` and `prompts.md` differed from accepted tree `a2e6ed0`.
- **Checks reported in the Prompt 91 handoff:**
  - staged Gitleaks: no leaks;
  - full-history Gitleaks after the commit: 36 commits scanned, no leaks found;
  - working tree clean; `main` and `origin/main` unchanged at `cdf7260`.
- **Diff:** `.local/p91/m3e-commit-incremental.diff`, 27,860 bytes, SHA-256 `af15e9bbfe4b4412b484b12934883b4a19bc30903930aad0e2684d4cf8ff9741`.
- Nothing was pushed or merged.

**Review note (recorded in Prompt 92):**
- **Accepted:** the external reviewer accepted the Prompt 91 incremental documentation diff.
- **How it was reviewed:** the reviewer independently computed its SHA-256, which matched the reported value. The reviewer ran no project checks.

## Prompt 92: Publish the reviewed M3e feature branch and verify CI

- **Stage:** Publication of `feat/document-api` only, and CI monitoring (no merge, no `main` update)
- **Date:** 2026-10-15 (session date)
- **Numbering:** 92 is the next unused number after Prompt 91; verified before appending.

````text
Written for: Mathew and the external reviewer.

Prompt 92: Publish the reviewed M3e feature branch and verify CI

You are authorized to publish only feat/document-api and monitor its CI. No merge or main update is authorized.

1. Verify the starting state

Expected:
- Branch: feat/document-api.
- HEAD: 0dd1ebde0430322a6283420973fcb7b6f63d6019.
- Parent: 98ca70b8e43ff4fd74349647b520213962374151.
- Working tree clean.
- Local main and origin/main:
  cdf7260d02b8af9affb369cc805d666be61f9ac0.
- Origin:
  https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git
- Effective author and committer use:
  257921624+mathewmljourney93@users.noreply.github.com.

Read fresh remote refs. Confirm remote main is still cdf7260 and an ancestor of HEAD. Confirm the feature branch does not already exist remotely.

Stop on a material mismatch without changing or overwriting work.

2. Publication preflight

Inspect everything that will become public compared with remote main, including the specification commit 98ca70b and implementation commit 0dd1ebd.

Confirm:
- Commit identities use the noreply address.
- No tracked .local/, environment files, backups, bundles, credentials or build outputs.
- No secrets or private information in the publication content.
- The workflows still trigger on this branch.
- Ubuntu and Windows verification, PostgreSQL integration with EG_REQUIRE_INTEGRATION=1, and full-history secret scanning remain enabled.

Do not change application code, tests, dependencies, configuration, workflows or the four reviewed documents.

3. Prompt history and local history commit

Preserve earlier prompts.md bytes.

Append:
- Prompt 91’s reported commit outcome.
- The reviewer’s acceptance of its incremental documentation diff, with independently matched checksum; the reviewer did not run project checks.
- This prompt verbatim.
- A preflight note recording verified facts and the branch-only publication authorization.

Keep historical Windows results distinct from future CI:
- 1260 passed, 205 skipped.
- 204 PostgreSQL skips plus one POSIX-only Windows signal skip.
- The 26 new M3e PostgreSQL tests have not run.
- The full 204-test PostgreSQL suite is unverified against this implementation.

Do not pre-record a successful push or CI result.

Stage only prompts.md. Check its append-only history, private content, git diff --cached --check and staged Gitleaks scan.

Commit with subject:
docs: record M3e branch publication authorization

Retain the existing co-author convention.

Verify that the commit changes only prompts.md, has parent 0dd1ebd, uses the noreply identity, and leaves a clean working tree.

Run the full-history Gitleaks scan before pushing. Stop if it fails.

4. Publish only the feature branch

Run git directly, without piping away its exit status:

git push --set-upstream origin refs/heads/feat/document-api:refs/heads/feat/document-api

No force-push, other branches or tags.

Confirm the remote feature ref matches the exact new HEAD and remote main remains unchanged.

5. Monitor CI for the exact published SHA

Wait for these four checks:
- Ubuntu verification.
- Windows verification.
- PostgreSQL 17 + pgvector integration.
- Full-history Gitleaks.

Use available authenticated tooling where already configured; otherwise use read-only public GitHub APIs. Do not install tools or add credentials merely to retrieve logs.

Poll at reasonable intervals, for at most 20 minutes. Verify each run’s head SHA, branch and event.

If a job fails, report its failing step and available diagnostic output, then stop. Do not fix implementation or push further changes without review.

If logs are accessible, report actual pytest summaries and any integration failures. If logs are inaccessible, report job conclusions and links, and clearly label test counts as unobserved. Do not present the expected 204 integration tests as an observed result.

Do not merge or update main even if all checks pass.

6. Handoff

Report:
- History commit SHA and parent.
- Exact published SHA.
- Preflight and scan results.
- Push command and Git’s exit status.
- Workflow and job links, conclusions and observed summaries.
- Remote refs and final working-tree status.
- Remaining verification limits.

No application checks need rerunning locally because only prompts.md changes.

No diff attachment is required because nothing outside prompts.md changes.

Keep the current Claude session.

End with:
“Return this output only to the external reviewer; no diff attachment is required.”
````

**Preflight note (written before the push; no push or CI result is recorded here):**
- **Authorization:** Prompt 92 authorizes publishing **only** `feat/document-api` and monitoring its CI. No merge, no `main` update, no force-push, no other branch and no tag.
- **Starting state verified:**
  - branch `feat/document-api` at `0dd1ebd` (parent `98ca70b`), working tree clean;
  - local `main` and `origin/main` at `cdf7260`; origin and the noreply author and committer identity as expected.
- **Fresh remote refs (`git ls-remote`, then `git fetch --prune`):** remote `main` is `cdf7260` and an ancestor of HEAD; `feat/document-api` does not exist remotely.
- **Publication content:** commits `98ca70b` (specification) and `0dd1ebd` (implementation), plus this history commit, which changes only `prompts.md`.
  - All use the noreply identity.
  - No tracked `.local/`, build outputs, bundles, backups, keys or credentials. The only environment file is the existing `.env.example`, which holds obvious placeholders and is unchanged by this publication.
  - No binary files; the added lines hold no private paths, addresses or tokens.
  - Gitleaks over `origin/main..HEAD` found no leaks.
- **Workflows (unchanged):**
  - `ci.yml` and `secret-scan.yml` trigger on every push and pull request, without branch filters;
  - `verify` runs on `ubuntu-24.04` and `windows-2025`;
  - `integration` runs PostgreSQL 17 + pgvector with `EG_REQUIRE_INTEGRATION=1`;
  - `gitleaks` scans the full history (`fetch-depth: 0`).
- **Verification status before CI:**
  - The local Windows result was `1260 passed, 205 skipped`: 204 PostgreSQL skips plus one POSIX-only Windows signal skip.
  - The 26 new M3e PostgreSQL tests have **never run**, and the full 204-test PostgreSQL suite is **unverified** against this implementation.
  - Any CI result belongs to the session handoff and later history, not to this note.

**Publication outcome (recorded in Prompt 93):**
- **History commit:** `ccdf08d3b901c348da8fbe03a87421e6d9c92ca7` ("docs: record M3e branch publication authorization"), parent `0dd1ebd`, changing only `prompts.md`. Full-history Gitleaks before the push scanned 37 commits and found no leaks.
- **Push:** `git push --set-upstream origin refs/heads/feat/document-api:refs/heads/feat/document-api` exited 0 and created the remote branch. Remote `feat/document-api` matched `ccdf08d` exactly; remote `main` stayed at `cdf7260`. No force-push, other branch or tag.
- **What Claude observed** through the public GitHub API: [ci run 38755179760](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38755179760) and [secret-scan run 38755179509](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38755179509) were push events on `feat/document-api` with head SHA `ccdf08d`. All four jobs concluded `success`: Ubuntu verify, Windows verify, PostgreSQL integration and full-history Gitleaks.
- **What Claude could not observe:** the job-log endpoint requires repository admin rights, so Claude could not retrieve the logs, and reported every test count as unobserved.

**Reviewer evidence note (recorded in Prompt 93):** the external reviewer independently retrieved both workflow records and all four job logs. Both runs were successful push events on `feat/document-api` at exact head SHA `ccdf08d3b901c348da8fbe03a87421e6d9c92ca7`. The reviewer did not execute the suite locally. Observed results:
- Ubuntu job 116491605348: `1261 passed, 204 skipped in 18.44s`.
- Windows job 116491604657: `1260 passed, 205 skipped in 33.03s`.
- PostgreSQL integration job 116491605959: `204 passed, 1261 deselected in 59.29s`. Collection reported 204 selected, and the `tests/test_document_api_postgres.py` line showed all 26 tests passing.
- Secret-scan job 116491603175: 37 commits scanned, no leaks found.

## Prompt 93: Record verified M3e CI results for review

- **Stage:** Documentation of verified CI results on `feat/document-api`; staged and uncommitted for review (no commit, push or merge)
- **Date:** 2026-10-15 (session date)
- **Numbering:** 93 is the next unused number after Prompt 92; verified before appending.

````text
Written for: Mathew and the external reviewer.

Prompt 93: Record verified M3e CI results for review

Update the documentation to record the independently retrieved M3e CI evidence. Leave the changes staged and uncommitted.

No commit, push, merge or main update is authorized. Do not change application code, tests, dependencies, migrations, workflows or configuration. Do not start M3f, Docker or a local database.

1. Verify the starting state

Expected:
- Branch: feat/document-api.
- HEAD and upstream: ccdf08d3b901c348da8fbe03a87421e6d9c92ca7.
- Parent: 0dd1ebde0430322a6283420973fcb7b6f63d6019.
- Working tree clean.
- Local and remote main:
  cdf7260d02b8af9affb369cc805d666be61f9ac0.
- Origin:
  https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git
- Existing noreply identity unchanged.

Read fresh remote refs. Stop on a material mismatch without overwriting work.

2. Record the verified evidence

The external reviewer independently retrieved both workflow records and all four job logs.

Both runs were successful push events on feat/document-api with exact head commit `ccdf08d3b901c348da8fbe03a87421e6d9c92ca7`

CI run:
https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38755179760

Observed results:
- Ubuntu job 116491605348:
  1261 passed, 204 skipped in 18.44s.
- Windows job 116491604657:
  1260 passed, 205 skipped in 33.03s.
- PostgreSQL integration job 116491605959:
  204 passed, 1261 deselected in 59.29s.
  Collection reported 204 selected.
  The tests/test_document_api_postgres.py line showed all 26 tests passing.

Secret-scan run:
https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38755179509

- Job 116491603175:
  37 commits scanned, no leaks found.

Attribute these counts to the job logs retrieved by the external reviewer. The reviewer did not execute the suite locally.

These are observed results for ccdf08d, not inferred counts or results for a future documentation commit.

3. Update only these five files

- README.md
- docs/decisions/0011-document-api.md
- docs/plan.md
- docs/threat-model.md
- prompts.md

Make narrow status corrections:
- M3e is reviewed and verified in CI on feat/document-api at ccdf08d.
- PostgreSQL, Ubuntu and Windows verification of that version is complete.
- The full 204-test integration suite passed, including the 26 new M3e tests.
- Replace current claims that those tests have never executed or that Linux verification remains pending.
- Keep historical statements and results correctly scoped.
- M3e is not merged; main remains at cdf7260.
- Compose, M3f and overall M3 acceptance remain pending.
- Do not claim performance benchmarks or general security guarantees.

Avoid repeating the full evidence in every paragraph. Use concise references where appropriate.

4. Prompt history

Preserve earlier prompts.md bytes.

Append:
- Prompt 92’s publication outcome, distinguishing Claude’s observed API conclusions from its inability to retrieve logs.
- A separate reviewer-evidence note with the observed results above.
- This prompt verbatim.
- A truthful outcome note marking the documentation as awaiting review.

Do not rewrite the earlier statement that the counts were unobserved by Claude.

5. Checks and handoff

Check:
- Exactly the five permitted files are staged.
- Earlier prompt history is byte-identical.
- Relative documentation links and anchors.
- Stale current-status wording.
- Private content and unintended artifacts.
- git diff --cached --check.
- Staged Gitleaks scan.

No application tests or builds need rerunning for these documentation-only changes.

Export the COMPLETE staged diff against HEAD, excluding prompts.md, directly from Git to:

.local/p93/m3e-verification-docs.diff

Use UTF-8 without a BOM. Do not print the diff in chat.

Report:
- Documentation changes.
- Checks actually run.
- Branch, HEAD, staged tree, staged paths and working-tree status.
- Diff path, baseline, final staged tree, byte size and SHA-256.
- Remaining limitations.

Keep the current Claude session.

End with:
“Return this output plus .local/p93/m3e-verification-docs.diff to the external reviewer.”
````

**Outcome note (documentation staged, awaiting review):**
- **Starting state verified:**
  - branch `feat/document-api`; HEAD and upstream `ccdf08d` (parent `0dd1ebd`); working tree clean;
  - local and remote `main` at `cdf7260` (fresh `git fetch` and `git ls-remote`); origin and noreply identity unchanged.
- **Documentation:** narrow status corrections in `README.md`, ADR-0011, `docs/plan.md` and `docs/threat-model.md`.
  - **New status:** M3e is reviewed and verified in CI on `feat/document-api` at `ccdf08d`. PostgreSQL, Ubuntu and Windows verification of that version is complete, and the full 204-test integration suite passed, including the 26 M3e tests. The counts are attributed to job logs retrieved by the external reviewer.
  - **Replaced:** claims that those tests never executed, or that Linux verification was pending, including the stale "M3e–M3f are not implemented" clause in the M3d status line.
  - **Kept:** historical results with their scope and attribution. M3e is not merged, `main` remains at `cdf7260`, and Compose, M3f and overall M3 acceptance remain pending.
- **Checks:** the staged-path, history, link, stale-wording, private-content, `git diff --cached --check` and staged Gitleaks checks run after this entry is staged; results are in the session handoff. No application tests or builds were run (documentation only).
- **Not done:** nothing committed, pushed or merged; no Docker or database contact.

**Formatting exception note (recorded in Prompt 94):** Prompt 93 above is **not verbatim** in one place. Prompt 94 authorized a one-time formatting exception, limited to that then-uncommitted entry.
- **Why:** the staged Gitleaks scan had mistaken a public commit identifier for a credential (rule `generic-api-key`). The identifier was the published head commit of `feat/document-api`, which in the original text sat on its own line after the label `head SHA:`.
- **Change:** the identifier was moved inline with the preceding sentence and enclosed in backticks, and its immediate label `SHA:` was replaced with `commit`. Moving it inline alone, with the label kept, was still flagged; with the label replaced, the scan found no leaks.
- **Unchanged:** the identifier itself and the instruction's meaning. No `.gitleaksignore`, allowlist, inline suppression, rule change or exclusion was added, and scanning was not disabled. No previously committed prompt-history byte changed.

**Review note (recorded in Prompt 94):**
- **Accepted:** the external reviewer accepted the Prompt 93 documentation diff (`.local/p93/m3e-verification-docs.diff`, 36,870 bytes) and independently matched its SHA-256 (`3037542263977899b086f46f171626723ddaeccadf17ba7471a5f32a219e543d`).
- **Basis:** acceptance rests on that diff and on GitHub evidence the reviewer retrieved independently. The reviewer did not run the suite locally.

## Prompt 94: Resolve the prompt-history false positive and publish M3e to main

- **Stage:** Prompt-history formatting correction, a documentation commit, publication of `feat/document-api`, and a fast-forward of `main` only after four green checks
- **Date:** 2026-10-15 (session date)
- **Numbering:** 94 is the next unused number after Prompt 93; verified before appending.

````text
Written for: Mathew and the external reviewer.

Prompt 94: Resolve the prompt-history false positive and publish M3e to main

You are authorized to:
- Make the narrowly defined Prompt 93 formatting correction below.
- Commit the reviewed documentation.
- Push feat/document-api.
- Fast-forward and push main only after all four checks pass for the exact new commit.

1. Verify the starting state

Expected:
- Branch: feat/document-api.
- HEAD and upstream: ccdf08d3b901c348da8fbe03a87421e6d9c92ca7.
- Staged tree: e393d0360ca6811522b21e131b3462e53e3b1fe0.
- Exactly five staged files:
  README.md
  docs/decisions/0011-document-api.md
  docs/plan.md
  docs/threat-model.md
  prompts.md
- Nothing unstaged or untracked.
- Local and remote main: cdf7260d02b8af9affb369cc805d666be61f9ac0.
- Origin and noreply author/committer identity unchanged.

Record the accepted staged tree before editing. Read fresh remote refs and stop on a material mismatch without overwriting work.

2. Resolve the public-commit false positive

The reviewer accepts the four documentation files exactly as staged. Keep them byte-identical to the accepted tree.

A one-time exception to verbatim prompt recording is authorized ONLY within the uncommitted Prompt 93 entry:
- Put its flagged public commit reference inline with the preceding sentence.
- Enclose the commit identifier in backticks.
- If needed, replace only its immediate label with “commit”.
- Preserve the identifier and the instruction’s meaning.

Do not change any previously committed prompt-history bytes.

Append a clearly labelled note explaining:
- Prompt 93 was recorded with this narrowly authorized formatting exception.
- Gitleaks had mistaken a public commit identifier for a credential.
- The identifier and instruction’s meaning are unchanged.
- This is not verbatim formatting.

Do not add .gitleaksignore, allowlists, inline scanner suppression, rule changes or exclusions. Do not disable scanning.

Rerun the staged scan after the correction. If it still flags the reference, stop and report the result rather than broadening the exception.

3. Prompt history

Append:
- The reviewer’s acceptance of the Prompt 93 documentation diff and independently matched checksum.
- That acceptance rests on the diff and independently retrieved GitHub evidence; the reviewer did not run the suite locally.
- This prompt verbatim.
- A preflight note recording the verified state, the formatting exception and publication authorization.

Do not pre-record successful pushes, CI or main publication.

Keep every earlier byte unchanged except the expressly authorized formatting correction within the currently uncommitted Prompt 93 entry.

4. Commit the documentation

Verify:
- Exactly the five authorized files are staged.
- The four reviewed documents are byte-identical to accepted tree e393d0360ca6811522b21e131b3462e53e3b1fe0.
- Application code, tests, dependencies, migrations, configuration and workflows are unchanged.
- Prompt-history changes match the narrow exception and authorized additions.
- Private-content checks, documentation links and git diff --cached --check pass.
- Staged Gitleaks passes without suppression.
- Author and committer use the noreply identity.

Commit with subject:
docs: record verified M3e results and main publication authorization

Retain the existing co-author convention.

Verify the parent, paths and clean working tree. Run the full-history Gitleaks scan before publication. Stop if it fails.

No local application tests or builds need rerunning for documentation-only changes.

5. Publish the feature branch first

Run git directly and preserve its exit status:

git push origin refs/heads/feat/document-api:refs/heads/feat/document-api

Monitor the exact new commit for:
- Ubuntu verification.
- Windows verification.
- PostgreSQL integration.
- Full-history Gitleaks.

Allow up to 20 minutes. Confirm run SHA, branch and event.

If any required check fails, is cancelled or remains pending beyond the bound, stop. Do not change main or make implementation fixes.

6. Fast-forward main only after four green checks

Fetch fresh refs and verify:
- Remote main is still cdf7260d02b8af9affb369cc805d666be61f9ac0.
- Remote feat/document-api equals the new commit.
- Remote main is an ancestor of that commit.
- Local main equals origin/main with no independent commits.
- The working tree is clean.

If all preconditions hold:
- Switch to main.
- Fast-forward it using git merge --ff-only with the exact new commit.
- Push only main:

git push origin refs/heads/main:refs/heads/main

No force-push, merge commit, squash, amend, rebase, tags or branch deletion.

Monitor all four checks again for the exact commit and the main push, with the same 20-minute bound.

If main CI fails, report it and stop. Do not rewrite or roll back history automatically.

7. Report results honestly

Use existing available tooling. Do not install tools or add credentials just to read logs.

Report actual pytest summaries when accessible. Otherwise report successful job conclusions and links, with counts explicitly unobserved.

The previously verified counts belong to ccdf08d:
- Ubuntu: 1261 passed, 204 skipped.
- Windows: 1260 passed, 205 skipped.
- PostgreSQL: 204 passed, 1261 deselected.
- Secret scan: 37 commits, no leaks.

Do not reuse those as observed results for the new commit.

Report:
- The exact prompt-formatting change.
- Commit SHA, parent and identity.
- Checks and scanner results.
- Feature and main pushes with Git exit statuses.
- Workflow/job links and conclusions for each push.
- Refs before and after, and final working-tree status.
- Remaining limits.

Leave the reviewed documentation unchanged after publication; later work can record the main results.

Compose, M3f and overall M3 acceptance remain pending. Do not start them.

No diff attachment is required: the four reviewed documents must remain byte-identical, and only prompts.md may change from the accepted staged tree.

Keep the current Claude session.

End with:
“Return this output only to the external reviewer; no diff attachment is required.”
````

**Preflight note (written before the commit; no push, CI or `main` result is recorded here):**
- **Starting state verified:**
  - branch `feat/document-api`; HEAD and upstream `ccdf08d`;
  - staged tree `e393d0360ca6811522b21e131b3462e53e3b1fe0` with exactly the five authorized files; nothing unstaged or untracked;
  - fresh remote refs: local and remote `main` at `cdf7260`, remote `feat/document-api` at `ccdf08d`;
  - origin and the noreply author and committer identity unchanged.

  The accepted staged tree is recorded under `.local/p94/`.
- **Formatting exception:** applied only within the uncommitted Prompt 93 entry, as described in the note above. After it, the staged Gitleaks scan found no leaks, without any suppression.
- **Reviewed documents:** `README.md`, `docs/decisions/0011-document-api.md`, `docs/plan.md` and `docs/threat-model.md` are to stay byte-identical to the accepted tree. No application code, tests, dependencies, migrations, configuration or workflows change.
- **Authorization (Prompt 94):**
  - commit this documentation, then push `feat/document-api` only;
  - fast-forward `main` to the exact new commit and push only `main`, **only after** Ubuntu, Windows, PostgreSQL integration and full-history Gitleaks all pass for that commit;
  - no force-push, merge commit, squash, amend, rebase, tag or branch deletion.
- **Earlier CI counts** (Ubuntu `1261 passed, 204 skipped`; Windows `1260 passed, 205 skipped`; PostgreSQL `204 passed, 1261 deselected`; secret scan 37 commits, no leaks) belong to `ccdf08d` only, not to the new commit.
- **Still pending:** Compose, M3f and overall M3 acceptance.

**Publication outcome (recorded in Prompt 95):**
- **Formatting exception:** applied as authorized, only within the then-uncommitted Prompt 93 entry. Moving the identifier inline with the `SHA:` label kept was still flagged. Replacing that label with `commit` made the staged Gitleaks scan pass, with no suppression, allowlist or rule change. The existing account in the formatting exception note above is unchanged.
- **Documentation commit:** `2e605e7bcf3b7b1ee90e9f12cb2acddb6950048f`, parent `ccdf08d`, noreply identity. Only `prompts.md` differed from accepted tree `e393d03`. Full-history Gitleaks before publication scanned 38 commits and found no leaks.
- **Feature push:** `git push origin refs/heads/feat/document-api:refs/heads/feat/document-api` exited 0. Claude observed through the public API that [ci run 38758322301](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38758322301) and [secret-scan run 38758322339](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38758322339) (push events on `feat/document-api` at `2e605e7`) concluded `success` in all four jobs.
- **Main fast-forward:**
  - Preconditions held on fresh refs: remote `main` at `cdf7260` and an ancestor; remote feature branch at `2e605e7`; local `main` equal to `origin/main`; clean tree.
  - `git merge --ff-only` and `git push origin refs/heads/main:refs/heads/main` both exited 0 (`cdf7260..2e605e7`).
  - Claude observed [ci run 38758727669](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38758727669) and [secret-scan run 38758727831](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38758727831) (push events on `main` at `2e605e7`) concluding `success` in all four jobs.
- **Not observed by Claude:** the job logs need admin rights, so Claude reported every count for `2e605e7` as unobserved.
- **Not done:** no force-push, merge commit, tag or branch deletion.

**Reviewer evidence note (recorded in Prompt 95):** the external reviewer independently retrieved both `main` workflow records and all four job logs. Both runs were successful push events on `main` at commit `2e605e7bcf3b7b1ee90e9f12cb2acddb6950048f`. The reviewer did not run the suite locally. Observed results:
- Ubuntu job 116503999468: `1261 passed, 204 skipped in 28.04s`.
- Windows job 116503999418: `1260 passed, 205 skipped in 29.97s`.
- PostgreSQL job 116503999580: `204 passed, 1261 deselected in 56.65s`.
- Secret-scan job 116503999509: 38 commits scanned, no leaks found.

## Prompt 95: Record M3e main verification and specify M3f containers

- **Stage:** Documentation only, on branch `docs/m3f-container-spec` created from `2e605e7`; staged and uncommitted for review
- **Date:** 2026-10-15 (session date)
- **Numbering:** 95 is the next unused number after Prompt 94; verified before appending.

````text
Written for: Mathew and the external reviewer.

Prompt 95: Record M3e main verification and specify M3f containers

Record the verified M3e main publication and propose the detailed M3f implementation plan. This is documentation work only.

Leave changes staged and uncommitted. Do not implement containers, change workflows, install tools, start Docker, contact databases, commit, push or merge.

1. Verify the starting state

Expected:
- Current branch: main.
- HEAD and origin/main: 2e605e7bcf3b7b1ee90e9f12cb2acddb6950048f.
- Local and remote feat/document-api point to the same commit.
- Working tree clean.
- Origin:
  https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git
- Existing noreply identity unchanged.

Check fresh remote refs. Stop on a material mismatch without overwriting work.

Create docs/m3f-container-spec from the verified HEAD. If that branch exists already, inspect its state before proceeding.

Read CLAUDE.md, the relevant M3 plan and the existing Docker/Compose, packaging, database and CLI configuration. Avoid rereading the complete prompt history.

2. Record verified M3e main results

The reviewer independently retrieved both main workflow records and all four job logs.

Both runs were successful push events on main at commit `2e605e7bcf3b7b1ee90e9f12cb2acddb6950048f`.

CI run:
https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38758727669

Observed results:
- Ubuntu job 116503999468:
  1261 passed, 204 skipped in 28.04s.
- Windows job 116503999418:
  1260 passed, 205 skipped in 29.97s.
- PostgreSQL job 116503999580:
  204 passed, 1261 deselected in 56.65s.

Secret-scan run:
https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38758727831

- Job 116503999509:
  38 commits scanned, no leaks found.

Attribute these observations to the reviewer’s retrieval of GitHub logs. The reviewer did not run the suite locally.

Update current “not merged” wording for M3e. Preserve the earlier ccdf08d feature-branch results as historical evidence.

Compose, M3f and overall M3 acceptance remain pending.

3. Propose the M3f specification in docs/plan.md

Keep the accepted architecture: one Python distribution, the existing API and sequential worker, PostgreSQL-backed jobs, and the existing PostgreSQL image.

Inspect what already exists before proposing changes.

Specify a concrete, modest implementation covering:

- Dockerfile layout and build stages.
- Reproducible installation from the committed lockfile.
- Runtime packages and entry points for API, worker and administrative commands.
- A non-root runtime, suitable working directory and file permissions.
- Build context and .dockerignore rules excluding .git, .local, .env, credentials, caches and build artifacts.
- Compose API, worker and database services.
- A deliberate migration/startup sequence that avoids API and worker racing to migrate.
- Database readiness, API readiness and startup dependencies.
- API binding inside the container and safe host port exposure.
- Worker signal delivery and graceful shutdown using its existing semantics.
- Disposable development credentials, environment settings and database-volume lifecycle.
- Commands for building, starting, migrating, seeding, creating a key, uploading a document, inspecting ingestion and stopping the stack.
- Clear separation between development convenience and production deployment claims.

Do not redesign application behaviour, authentication or the worker.

Inspect the current dependency/base-image policy. If selecting base image and uv versions requires research, use official sources and record the proposed versions and rationale. Do not silently change dependency policy.

4. Define what CI will verify

The existing M3f slice requires images to build in CI.

Propose the smallest meaningful CI validation:
- Image build.
- Installed entry-point/import checks.
- Where practical, an isolated Compose smoke run using only disposable CI resources:
  database readiness, migrations, API readiness, synthetic account/key setup, upload, production-worker ingestion, and verified active/chunk views.

Explain whether the Compose smoke is feasible within the current workflows and resource limits. If recommending build-only verification, state precisely what would remain unverified.

Do not equate a successful Docker image build with a working Compose stack.

Plan cleanup on success and failure, bounded waits, useful privacy-safe diagnostics and no committed plaintext generated keys. Do not send credentials or uploaded content to logs.

No local Docker installation or local execution is required or authorized. Local Compose remains unverified until it actually runs; CI Compose execution, if implemented later, should be labelled separately.

5. Specify files and acceptance criteria

List the intended files, expected workflow changes and documentation/ADR additions for the later implementation.

Separate:
- Already accepted architectural requirements.
- Proposed engineering defaults needing review.
- Exact build and smoke-test acceptance criteria.
- Remaining M3 acceptance requirements.

Check the overall M3 acceptance list for any other outstanding obligation. Do not mark M3 complete or silently defer an unmet criterion.

Mark the M3f specification proposed for review, with no implementation yet.

6. Documentation and prompt history

Change only:
- README.md
- docs/decisions/0011-document-api.md
- docs/plan.md
- docs/threat-model.md
- prompts.md

Keep the M3f detailed proposal in the plan; do not create its implementation ADR yet.

Preserve earlier prompts.md bytes. Append:
- Prompt 94’s actual publication outcome.
- The narrowly authorized Prompt 93 formatting exception and successful unsuppressed scans, without rewriting the existing account.
- A reviewer-evidence note for the main results above.
- This prompt verbatim.
- A truthful outcome note marking the M3f specification awaiting review.

Write public commit references inline in backticks in your own notes. Do not introduce broad exceptions to verbatim prompt recording or secret scanning.

7. Checks and handoff

Check:
- Exactly the five permitted files staged.
- Earlier prompt history unchanged.
- Relative links and anchors.
- Current status wording.
- Private content and unintended artifacts.
- git diff --cached --check.
- Staged Gitleaks.

Do not run application tests or builds for this documentation-only task.

Export the COMPLETE staged diff against HEAD, excluding prompts.md, directly from Git to:

.local/p95/m3f-container-spec.diff

Use UTF-8 without a BOM. Do not print the diff in chat.

Report:
- The recorded M3e results.
- Proposed M3f design, decisions and verification scope.
- Outstanding decisions or blockers.
- Checks actually run.
- Branch, HEAD, staged tree and staged paths.
- Diff path, baseline, final tree, byte size and SHA-256.

Keep the current Claude session.

End with:
“Return this output plus .local/p95/m3f-container-spec.diff to the external reviewer.”
````

**Outcome note (documentation staged; M3f specification awaiting review):**
- **Starting state verified:**
  - branch `main`; HEAD, `origin/main` and local and remote `feat/document-api` all at `2e605e7`;
  - working tree clean; origin and noreply identity unchanged.

  Branch `docs/m3f-container-spec` was created from `2e605e7` (it did not exist locally or remotely).
- **M3e main results recorded** in `README.md`, ADR-0011, `docs/plan.md` and `docs/threat-model.md`, attributed to the reviewer's retrieval of GitHub logs. Current "not merged" wording was replaced. The `ccdf08d` feature-branch results are kept as historical evidence.
- **M3f specification** added to `docs/plan.md`, marked **proposed for review, not implemented**. It covers:
  - a two-stage image from the locked dependencies, non-root and read-only;
  - an allowlisted build context;
  - Compose `migrate`, `api` and `worker` services beside the existing `postgres`, with the API on loopback only and the worker's 60 s stop grace period;
  - developer commands and a development-only scope;
  - a CI `container` job with a build, image checks and a bounded Compose smoke run;
  - intended files and acceptance criteria;
  - four open decisions: the base patch version under the age policy, Compose smoke versus build-only, whether CI Compose satisfies the M3 Compose requirement, and the engineering defaults.
- **Base-image facts** were read from official registries: the Docker Hub tag listing for `python` and the GHCR manifest for `astral-sh/uv`. Nothing was installed, pulled, built or run.
- **Checks:** the staged-path, history, link, status-wording, private-content, `git diff --cached --check` and staged Gitleaks checks run after this entry is staged; results are in the session handoff. No application tests or builds were run (documentation only).
- **Not done:** nothing committed, pushed or merged; no Docker, database contact or container implementation.

**Review note (recorded in Prompt 96):**
- **Accepted:** the external reviewer accepted the M3e publication documentation from Prompt 95. They independently computed the SHA-256 of `.local/p95/m3f-container-spec.diff`, which matched (`98bd148e9df0151c6ae5c26ab776321cdfec8b5385638b3e32a0a4ca1731208c`).
- **Reviewed, not executed:** the reviewer inspected the diff and ADR-0008, and ran neither Docker nor any project checks.
- **Decisions:**
  - **Python base:** `python:3.12.14-slim-trixie` with the proposed digest, subject to official-registry verification at implementation. No dependency-age exception is approved.
  - **Smoke test:** the CI Compose smoke is required for M3f.
  - **M3 Compose requirement:** a passing CI Compose smoke can satisfy it, alongside the other agreed criteria. Local Compose stays unverified until it actually runs locally.
  - **Engineering defaults:** UID/GID 10001; loopback host ports 8000 and 5433; a 60 s worker stop grace period; no restart policy; a 180 s startup wait; a 90 s ingestion wait; a 20-minute CI job timeout. These are engineering defaults, not measured performance claims.
- **Specification corrections requested:**
  - **Worker shutdown:** remove the claim that the drain, cancel and heartbeat waits add up to a guaranteed 45 s shutdown bound (ADR-0008, *No total shutdown deadline*). Describe the 60 s grace period as an external termination budget. Require the smoke to inspect the stopped worker's actual exit status (exit code 0, no OOM kill), and state that it stops an idle worker.
  - **Image selection:** make the selection of the CI-built image explicit, verify that each service runs that exact image ID, and rule out any silent rebuild or pull.
  - **Diagnostics:** stop treating migrate, API and worker logs as privacy-safe JSON. Capture and redact the generated key before printing, report a key found in logs safely, give every subprocess and network call its own timeout, and keep the original failure.
  - **Cleanup:** use a unique project name per run and attempt, and confirm resource ownership before destructive cleanup.
  - **Build context:** add explicit recursive exclusions inside `apps/` and `packages/`, and verify the effective build context with nested excluded fixtures.

## Prompt 96: Correct and finalize the M3f container specification

- **Stage:** Specification correction on branch `docs/m3f-container-spec`; staged and uncommitted for review
- **Date:** 2026-10-15 (session date)
- **Numbering:** 96 is the next unused number after Prompt 95; verified before appending.

````text
Written for: Mathew and the external reviewer.

Prompt 96: Correct and finalize the M3f container specification

Correct the M3f specification only. Leave the documentation staged and uncommitted for review.

No implementation, dependency installation, Docker execution, database contact, commit, push or merge is authorized.

1. Verify the starting state

Expected:
- Branch: docs/m3f-container-spec.
- HEAD: 2e605e7bcf3b7b1ee90e9f12cb2acddb6950048f.
- Staged tree: 759ec7b33494ccb5803f05afc10b6a22c27a22d5.
- Exactly five staged files:
  README.md
  docs/decisions/0011-document-api.md
  docs/plan.md
  docs/threat-model.md
  prompts.md
- Nothing unstaged or untracked.
- Local main and origin/main unchanged at HEAD.
- Origin and noreply identity unchanged.

Record the pre-edit staged tree under .local/p96/ as the incremental review baseline.

Stop on a material mismatch without overwriting work.

2. Record the reviewer’s decisions

The reviewer approves:
- Python 3.12.14-slim-trixie, using the proposed digest subject to official-registry verification during implementation. No dependency-age exception is approved.
- The CI Compose smoke test is required for M3f.
- A passing CI Compose smoke can satisfy the M3 Compose requirement, alongside the other agreed criteria. Local Compose remains unverified until actually executed locally.
- UID/GID 10001, loopback host ports 8000 and 5433, a 60-second worker stop grace period, no restart policy, a 180-second startup wait, a 90-second ingestion wait and a 20-minute CI job timeout.

These are engineering defaults, not measured performance claims.

The M3e publication documentation is accepted. Keep README.md and ADR-0011 byte-identical to the baseline tree. Keep the threat-model wording unchanged unless a narrow correction below requires it.

3. Correct worker shutdown claims

Read ADR-0008’s “No total shutdown deadline” limitation.

Remove claims that adding drain, cancel and heartbeat waits produces a guaranteed 45-second process shutdown bound.

State accurately:
- Those are bounded supervisor waits.
- Synchronous database calls can delay shutdown beyond them.
- The 60-second Compose grace period is an external termination budget.
- Docker may force termination if that budget expires.
- M3f does not change the worker’s existing semantics or introduce a database statement timeout.

Strengthen the smoke acceptance:
- A successful docker compose stop command alone is not proof of a graceful worker exit.
- Inspect the stopped worker container’s actual exit status.
- Require application exit code 0 and no OOM termination.
- Unexpected exit or forced termination fails the shutdown smoke.
- State whether this smoke stops an idle worker after successful ingestion. Do not claim it proves draining an in-flight handler if it does not test that scenario.

Use Docker’s official documentation where command behaviour needs verification.

4. Make the CI-built image selection explicit

The plan builds evidenceguard:ci but Compose currently proposes evidenceguard:dev.

Specify one explicit mechanism for selecting the image, such as a shared image variable with a development default and a CI override.

Require:
- migrate, api and worker use the exact image built by the CI job.
- The smoke does not silently rebuild or pull a different application image.
- Inspect their image IDs against the built image ID.
- Build, smoke, diagnostics and cleanup use the same Compose files, project name and image selection.

Keep the development commands straightforward.

5. Correct diagnostics and cleanup

Remove the assumption that migrate, API and worker logs are all privacy-safe JSON. Alembic and dependency failures can produce ordinary text and tracebacks.

Specify:
- Capture subprocess output and container logs before displaying them.
- Check for and redact the generated API key before printing diagnostics, on both success and failure paths.
- Do not rely solely on GitHub masking.
- Do not print unsanitized HTTP bodies, command outputs or exception representations that could carry the key.
- Report a key-in-logs finding safely without printing the key or offending raw line.
- Preserve the original smoke failure if diagnostics or cleanup also fail.

Every subprocess and network operation needs an appropriate timeout. Poll deadlines do not bound an individual hung command.

Use a unique CI project name including run ID and attempt. Confirm that CI resources and volumes belong to that project before destructive cleanup. Do not remove unrelated resources.

Keep always-run cleanup in the workflow, while acknowledging that runner loss or hard cancellation can prevent cleanup from completing.

6. Tighten build-context exclusions

The build-context allowlist must not accidentally include nested secrets or artifacts inside apps/ or packages/.

Specify explicit recursive exclusions applied after directory inclusion for:
- .env files, preserving no credential-bearing exception;
- .git and .local directories;
- virtual environments, caches and Python bytecode;
- dist/build outputs and credential/key files.

Preserve the legitimate source files and package data required by the wheel.

Require verification of effective build-context contents, including representative nested excluded paths. Do not rely solely on a text assertion that .dockerignore contains certain strings.

7. Status and prompt history

Make only the narrow plan and related documentation corrections above.

Keep M3f marked as awaiting final specification review. No implementation exists yet. Overall M3 acceptance remains pending.

Preserve earlier prompts.md bytes. Append:
- A review note accepting the M3e publication documentation and recording that the checksum independently matched.
- The four decisions above.
- The specification corrections requested here.
- That the reviewer inspected the diff and ADR-0008 but did not run Docker or project checks.
- This prompt verbatim and a truthful outcome note.

Do not require a session restart for this correction. We can finish specification review and its acceptance commit in this session, then use a fresh session for M3f implementation.

8. Checks and handoff

Run only appropriate documentation checks:
- Permitted staged paths.
- Earlier prompt-history prefix unchanged.
- Relative links and anchors.
- Consistent shutdown, verification and acceptance wording.
- Private-content/artifact checks.
- git diff --cached --check.
- Staged Gitleaks.

No application tests, builds or Docker execution.

Export the COMPLETE incremental diff against tree
759ec7b33494ccb5803f05afc10b6a22c27a22d5,
excluding prompts.md, directly from Git to:

.local/p96/m3f-spec-corrections.diff

Use UTF-8 without a BOM. Do not print the diff in chat.

Report:
- Corrections and settled decisions.
- Checks actually run.
- Branch, HEAD, final staged tree and staged paths.
- Byte identity of the accepted M3e documents.
- Diff path, baseline, final tree, byte size and SHA-256.
- Any unresolved specification decision.

End with:
“Return this output plus .local/p96/m3f-spec-corrections.diff to the external reviewer.”
````

**Outcome note (specification corrected and staged; awaiting final specification review):**
- **Starting state verified:**
  - branch `docs/m3f-container-spec` at `2e605e7`;
  - staged tree `759ec7b33494ccb5803f05afc10b6a22c27a22d5` with the five expected files; nothing unstaged or untracked;
  - `main` and `origin/main` at HEAD; origin and noreply identity unchanged.

  The baseline tree is recorded under `.local/p96/`.
- **Only `docs/plan.md` changed** among the four documents. `README.md`, ADR-0011 and `docs/threat-model.md` are byte-identical to `759ec7b`, because their existing M3f wording ("proposed for review") remains accurate.
- **Decisions recorded** in the M3f specification, which no longer lists open decisions; the four Prompt 95 decisions are settled.
- **Worker shutdown:**
  - The drain, cancel and heartbeat waits are described as bounded supervisor waits that synchronous database calls can outlast. The 60 s grace period is an external termination budget, after which Docker may SIGKILL.
  - No change to worker semantics, and no statement timeout.
  - The smoke stops an **idle** worker and inspects its state: exited, code 0, not OOM-killed. It does not claim to prove an in-flight drain.
- **Image selection:**
  - `image: ${EG_IMAGE:-evidenceguard:dev}` with `pull_policy: never` for all three application services.
  - CI builds through Compose with a per-run, per-attempt tag and project name, runs `up --no-build --pull never`, and checks each container's image ID against the built image.
- **Diagnostics and cleanup:**
  - Output is captured and the key redacted before printing, on success and failure, without relying solely on masking. A key found in logs is reported as a count only. Only fixed fields and exception class names are printed.
  - Every subprocess and HTTP call has its own timeout, and the first failure is preserved.
  - Cleanup confirms ownership through the project label and removes only this run's resources and tag. The runner-loss limit is stated.
- **Build context:**
  - Explicit recursive re-exclusions follow the allowlist, with no `.env` exception.
  - The legitimate package data (`py.typed`, `script.py.mako`) is preserved.
  - A required effective-context check plants synthetic nested excluded fixtures in a `git archive` copy, lists the context through a throwaway build, and requires an exact match.
- **Docker command behaviour** checked against Docker's official documentation:
  - `stop_grace_period` (10 s default, then SIGKILL), `stop_signal` and `init`;
  - `pull_policy: never`;
  - `up --no-build`, `--pull never`, `--wait` and `--wait-timeout`;
  - `${VAR:-default}` interpolation;
  - `.dockerignore` matching (last match wins; `**` for any depth).

  The documentation lists no command to print the effective build context, hence the listing build.
- **Checks:** the documentation checks run after this entry is staged; results are in the session handoff. No application tests, builds or Docker execution.
- **Status:** M3f is awaiting final specification review, with no implementation; overall M3 acceptance is pending.
- **Not done:** nothing committed, pushed or merged.

**Acceptance note (recorded in Prompt 97):**
- **Accepted:** the external reviewer accepted the M3f container specification, subject to the two final clarifications below.
- **What the reviewer inspected:**
  - the original specification diff (`.local/p95/m3f-container-spec.diff`) and the correction diff (`.local/p96/m3f-spec-corrections.diff`), independently matching both checksums;
  - ADR-0008 and Docker's official documentation.

  The reviewer did not execute Docker or project checks.
- **Final clarifications (applied in Prompt 97):**
  - **Database image availability:** the CI `container` job explicitly pulls only the approved digest-pinned PostgreSQL image, with a bounded timeout, before Compose startup. The database image selection does not change; `--no-build --pull never` is kept for startup; the application containers must still run the exact CI-built image ID; no registry login or image publication is introduced.
  - **Private key capture versus published output:**
    - the `create-key` stdout is captured privately in process memory and is never printed, written to disk or uploaded;
    - the key must not appear in the captured service logs, and all other diagnostic output is checked and redacted before display;
    - GitHub masking is an additional protection, not the primary control;
    - a key-in-service-logs failure is reported without exposing the key or the offending line.

## Prompt 97: Commit the accepted M3f container specification locally

- **Stage:** Specification acceptance and a local commit on branch `docs/m3f-container-spec` (no push or merge)
- **Date:** 2026-10-15 (session date)
- **Numbering:** 97 is the next unused number after Prompt 96; verified before appending.

````text
Written for: Mathew and the external reviewer.

Prompt 97: Commit the accepted M3f container specification locally

Commit the reviewed documentation and M3f specification locally, including the two narrow clarifications below.

No implementation, Docker execution, database contact, push, merge or main update is authorized.

1. Verify the starting state

Expected:
- Branch: docs/m3f-container-spec.
- HEAD: 2e605e7bcf3b7b1ee90e9f12cb2acddb6950048f.
- Staged tree: b494d3b991c45a2bd958db8aece7522a52edc0a9.
- Exactly five staged files:
  README.md
  docs/decisions/0011-document-api.md
  docs/plan.md
  docs/threat-model.md
  prompts.md
- Nothing unstaged or untracked.
- Local main and origin/main unchanged at HEAD.
- Origin and noreply identity unchanged.

Record the accepted staged tree under .local/p97/ before editing.

Stop on a material mismatch without overwriting work.

2. Add two narrow specification clarifications

A. Database image availability

The container CI job must explicitly pull the existing digest-pinned PostgreSQL image before Compose startup.

Building the application image does not guarantee that the database image is present in that job.

Specify:
- Pull only the approved digest-pinned PostgreSQL image, with a bounded timeout.
- Do not change its image selection.
- Retain --no-build --pull never during smoke startup.
- Application containers must still run the exact CI-built image ID.
- No registry login or image publication is introduced.

This is planned behaviour only; do not run Docker.

B. Private key capture versus published output

Correct the acceptance wording that currently says the key must never appear in captured output.

Specify:
- The create-key command’s stdout is captured privately in process memory so the smoke can obtain the generated credential.
- That private capture is never printed, written to disk or uploaded.
- The key must not appear in captured service logs.
- All other diagnostic output is checked and redacted before display.
- GitHub masking is an additional protection, not the primary control.
- A key-in-service-logs failure is reported without exposing the key or offending line.

Preserve the existing privacy and failure-handling design.

3. Record specification acceptance

Make narrow status updates in README.md, docs/plan.md and docs/threat-model.md:
- M3f specification accepted at external review.
- Implementation pending; no container implementation exists yet.
- Required CI build, effective-context checks and Compose smoke remain unexecuted.
- Local Compose remains unverified.
- Overall M3 acceptance remains pending.

Keep docs/decisions/0011-document-api.md byte-identical to the accepted staged tree.

Do not change historical M3e evidence or redesign the specification.

4. Prompt history

Preserve earlier prompts.md bytes.

Append:
- An acceptance note under Prompt 96 recording that the reviewer inspected the original specification and correction diffs and independently matched both checksums.
- The two final clarifications in this prompt.
- That the reviewer inspected ADR-0008 and official Docker documentation but did not execute Docker or project checks.
- This prompt verbatim.
- A truthful pre-commit note.

Do not record implementation, future CI results or the new commit’s own SHA inside that commit.

5. Check and commit locally

Confirm:
- Exactly the five permitted files staged.
- Changes since the accepted tree are limited to the authorized wording and prompt history.
- ADR-0011 is byte-identical.
- Earlier prompt-history bytes remain unchanged.
- Relative links and anchors are valid.
- No private information, credentials or unintended artifacts.
- git diff --cached --check passes.
- Staged Gitleaks passes without suppression.
- Author and committer use the noreply identity.

No application tests, builds or Docker execution are needed.

Commit with subject:
docs: record M3e main results and accepted M3f container specification

Retain the existing co-author convention.

After committing:
- Run the full-history Gitleaks scan.
- Verify the parent, committed paths and identity.
- Confirm a clean working tree.
- Confirm main and origin/main remain unchanged.
- Do not push or merge.

6. Review handoff

Export the COMPLETE incremental diff from accepted tree
b494d3b991c45a2bd958db8aece7522a52edc0a9
to the new commit, excluding prompts.md, directly from Git to:

.local/p97/m3f-spec-acceptance.diff

Use UTF-8 without a BOM. Do not print the diff in chat.

Report:
- Commit SHA, parent, subject and identity.
- Committed paths.
- Final clarifications and acceptance wording.
- Checks actually run.
- ADR-0011 byte identity.
- Final Git state.
- Diff path, baseline, final commit, byte size and SHA-256.

Finish this task in the current session. The next implementation task will use a fresh Claude session, recovering from the committed specification and repository instructions.

End with:
“Return this output plus .local/p97/m3f-spec-acceptance.diff to the external reviewer.”
````

**Pre-commit note (written before the commit; the commit's own SHA is not recorded here):**
- **Starting state verified:**
  - branch `docs/m3f-container-spec` at `2e605e7`;
  - staged tree `b494d3b991c45a2bd958db8aece7522a52edc0a9` with the five expected files; nothing unstaged or untracked;
  - `main` and `origin/main` at HEAD; origin and noreply identity unchanged.

  The accepted tree is recorded under `.local/p97/`.
- **Changes since the accepted tree:**
  - the two clarifications in the M3f specification (`docs/plan.md`, E4 and G);
  - narrow acceptance wording in `README.md`, `docs/plan.md` and `docs/threat-model.md`: the M3f specification accepted at review; implementation pending; the required CI build, effective-context checks and Compose smoke not run; local Compose unverified; overall M3 acceptance pending;
  - this prompt history.

  ADR-0011 is byte-identical to the accepted tree, and the historical M3e evidence is unchanged.
- **Checks for this commit:** run after this entry is staged; results are in the session handoff. They are the staged-path, accepted-tree comparison, ADR-0011 identity, prompt-history prefix, link, private-content, `git diff --cached --check`, staged Gitleaks and identity checks, and after the commit the full-history Gitleaks scan. No application tests, builds or Docker execution.
- **Not done:** no container implementation, no Docker or database contact, nothing pushed or merged.

**Commit outcome (recorded in Prompt 98):**
- **Commit:** `b7c9ea28808cfa54a66d55b2ab63f80016594c03` ("docs: record M3e main results and accepted M3f container specification"), parent `2e605e7`, tree `71ca97ddbf14b7c8df80bdd2eab5b0a70cf4ee64`, on the local branch `docs/m3f-container-spec`, with the noreply author and committer identity.
- **Checks reported in the Prompt 97 handoff:**
  - ADR-0011 byte-identical to the accepted tree;
  - staged Gitleaks: no leaks;
  - full-history Gitleaks after the commit: 39 commits scanned, no leaks found;
  - working tree clean; `main` and `origin/main` unchanged at `2e605e7`.
- **Diff:** `.local/p97/m3f-spec-acceptance.diff`, 19,848 bytes, SHA-256 `af4c64baffd32d5308ddd694e7d3e989b7b37832a879f78a54e67eefb0c6f77e`.
- Nothing was pushed or merged.

**Review note (recorded in Prompt 98):**
- **Accepted:** the external reviewer accepted the Prompt 97 final diff and independently matched its checksum.
- **How it was reviewed:** the reviewer ran no project or Docker checks.
- **Next:** Prompt 98 authorizes implementing M3f on top of the local specification commit, staged and uncommitted for review.

## Prompt 98: Implement the accepted M3f container specification

- **Stage:** M3f implementation on branch `feat/container-stack`, created from `b7c9ea2`; staged and uncommitted for external review (no commit, push or merge)
- **Date:** 2026-10-15 (session date)
- **Numbering:** 98 is the next unused number after Prompt 97; verified before appending.

````text
Written for: Mathew and the external reviewer.

Prompt 98: Implement the accepted M3f container specification

This is a fresh Claude session continuing EvidenceGuard. Implement M3f from the accepted specification in docs/plan.md. Leave the implementation staged and uncommitted for external review.

The specification commit is local only. You are authorized to implement directly on top of it; publishing or merging it separately is unnecessary.

No commit, push, merge, main update, Docker installation, local Docker execution or database contact is authorized. Container execution will be verified in CI after a later authorized publication.

1. Recover context and verify state

Work in D:\Claude\evidenceguard_agentic_rag.

Read:
- CLAUDE.md.
- The accepted M3f specification in docs/plan.md.
- The relevant packaging, Compose, CI, CLI and database configuration.
- ADR-0008’s shutdown limitations.

Read only relevant prompt-history entries and its tail, not the entire prompts.md file.

Expected starting state:
- Branch: docs/m3f-container-spec.
- HEAD: b7c9ea28808cfa54a66d55b2ab63f80016594c03.
- Parent: 2e605e7bcf3b7b1ee90e9f12cb2acddb6950048f.
- Working tree clean.
- Local main and origin/main:
  2e605e7bcf3b7b1ee90e9f12cb2acddb6950048f.
- Origin:
  https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git
- Effective author and committer:
  mathewmljourney93 <257921624+mathewmljourney93@users.noreply.github.com>.

Stop on a material mismatch without overwriting work.

Create feat/container-stack from the verified HEAD. Inspect before proceeding if that branch already exists.

2. Implement the accepted specification

The detailed M3f specification in docs/plan.md is authoritative, including the Prompt 96–97 corrections.

Implement:
- Dockerfile.
- .dockerignore.
- Compose migration, API and worker services.
- CI container build, effective-context verification, image checks and Compose smoke.
- The supporting stdlib-only scripts and meaningful tests.
- ADR-0012 and accurate usage/status documentation.

Preserve existing application behaviour, migrations, dependencies and uv.lock. Keep the existing CI jobs unchanged while adding the container job.

Do not redesign authentication, ingestion or worker semantics.

3. Image and build context

Use the approved two-stage image design and locked, non-editable installation.

Verify the proposed Python and uv digests against their official registries through read-only metadata requests. Do not pull images locally.

Use the approved Python 3.12.14-slim-trixie digest. No dependency-age exception or substitute image is authorized. Report a concrete blocker if the approved digest cannot be verified.

Preserve:
- One runtime image for all roles.
- Non-root UID/GID 10001.
- Root-owned runtime files.
- No uv, source tree, tests, Git metadata or secrets in the runtime.
- Required package data and migration configuration.
- Exec-form process commands.

Implement the allowlisted build context and recursive exclusions exactly enough to preserve required sources while excluding nested secrets and artifacts.

The required CI effective-context check must exercise Docker’s actual ignore behaviour using synthetic nested fixtures in an isolated archive copy. Text assertions alone are insufficient.

4. Compose and image identity

Implement the shared EG_IMAGE selection with a development default and pull_policy: never for application services.

Preserve the existing pinned PostgreSQL image and development credentials.

Implement:
- Database health gating.
- One-shot migrate service.
- API and worker depending on successful migration.
- Loopback-only host port publication.
- Read-only application filesystems, tmpfs, dropped capabilities, no-new-privileges and init.
- API readiness health check.
- Worker SIGTERM and 60-second external stop budget.
- No restart policy.

Do not claim the worker has a total shutdown deadline or add a statement timeout.

CI must explicitly pull the approved database image by digest before startup. Start the stack without rebuilding or pulling application images.

Verify migrate, api and worker use the recorded CI-built image ID.

5. CI smoke and diagnostics

Implement the accepted end-to-end smoke:
- Startup with bounded waits.
- Seed synthetic accounts.
- Capture a generated API key privately in memory.
- Create a vendor and upload synthetic Markdown.
- Observe production-worker ingestion.
- Verify active revision and verified chunks.
- Verify duplicate upload returns 200.
- Stop the idle worker and inspect actual container state: exited, code 0, no OOM kill.

Do not present a successful stop command alone as proof of graceful exit.

Use per-operation subprocess/network timeouts as well as polling deadlines.

Preserve the agreed privacy handling:
- Never publish the private create-key capture.
- Check service logs for the generated key.
- Capture and redact diagnostics before printing.
- Do not rely solely on GitHub masking.
- Avoid raw HTTP bodies and exception representations.
- Preserve the first failure if diagnostics or cleanup also fail.

Use a unique project/image selection per CI run and attempt. Cleanup must be scoped to owned resources and run in an always step. Acknowledge hard-cancellation limitations.

Do not execute the smoke locally.

6. Tests and local verification

Add focused tests for meaningful container/configuration invariants and the smoke helper’s error handling, timeout handling and redaction where these can run without Docker.

Avoid tests that merely restate implementation strings when a stronger behavioural check is practical.

Run appropriate local checks:
- Locked environment synchronization.
- Ruff formatting and lint.
- Strict Mypy using the repository’s established scope.
- Relevant new tests.
- One final full database-independent suite, reporting actual skips.
- Build and isolated installed-wheel checks if required by repository policy or changes.
- git diff --cached --check.
- Staged Gitleaks and private-content/artifact checks.

Do not repeatedly rerun unchanged checks without a reason.

Do not claim image builds, Compose operation or Linux/container verification passed locally. Those remain pending CI.

7. Documentation and prompt history

Add docs/decisions/0012-containers.md with:
- Verified image identities and sources.
- Build and startup design.
- CI verification scope.
- Privacy and shutdown limitations.
- Development-only scope.

Update README.md, docs/plan.md and docs/threat-model.md accurately:
- Implementation staged, awaiting review.
- Container build and CI Compose verification pending.
- Local Compose unverified.
- Overall M3 acceptance pending.

Include usable developer commands, respecting the project’s Windows environment. Do not imply those commands were executed.

Preserve earlier prompts.md bytes. Append:
- Prompt 97’s reported local commit outcome.
- The reviewer’s acceptance of its final diff and independently matched checksum; no project or Docker checks run by the reviewer.
- This prompt verbatim.
- A truthful outcome note.

Public commit references in your own notes should be inline and backticked. Do not add scanner suppressions.

8. Handoff

Stage only the intended implementation, tests and documentation. Leave everything uncommitted.

Export the COMPLETE staged diff against HEAD, excluding prompts.md, directly from Git to:

.local/p98/m3f-implementation.diff

Use UTF-8 without a BOM. Do not print the diff in chat.

Report:
- What was implemented and important decisions.
- Official image-verification sources and results.
- Local commands and actual results.
- Anything differing from the accepted specification.
- Container checks written but not executed.
- Branch, HEAD, staged tree, staged paths and working-tree status.
- Diff path, baseline, final staged tree, byte size and SHA-256.

Keep this new session for implementation and its review corrections. Do not recommend restarting after one or two prompts.

End with:
“Return this output plus .local/p98/m3f-implementation.diff to the external reviewer.”
````

**Outcome note (written before staging; implementation awaiting external review):**
- **Starting state verified:**
  - branch `docs/m3f-container-spec` at `b7c9ea2` (parent `2e605e7`), working tree clean;
  - `main` and `origin/main` at `2e605e7`; origin and the noreply identity as expected.

  Branch `feat/container-stack` was created from `b7c9ea2`.
- **Implemented (staged, unreviewed):**
  - `Dockerfile` (two stages, locked non-editable install, UID/GID 10001, root-owned runtime files, exec-form command);
  - `.dockerignore` (allowlist plus recursive re-exclusions);
  - `docker-compose.yml` (`migrate`, `api` and `worker` beside the unchanged `postgres`; shared `EG_IMAGE` selection with `pull_policy: never`);
  - the CI `container` job;
  - `infra/ci/container_ci.py` (stdlib-only `config`, `context`, `image`, `smoke` and `cleanup` subcommands);
  - `tests/test_container_ci.py` and `tests/test_container_files.py`;
  - ADR-0012, and status and usage documentation.

  No application code, migration, dependency or `uv.lock` changed. `pyproject.toml` changed only to add the CI helper to the strict mypy scope.
- **Image verification** (read-only registry metadata, nothing pulled):
  - The approved Python digest `f77ac9e…` is what `3.12.14-slim-trixie` resolves to; its `linux/amd64` image configuration was created on 2026-09-19, which meets the age policy.
  - The approved uv digest `cdc6093…` is what `0.13.0` resolves to. But uv 0.13.0 and its image date from 2026-10-09, which is **below the two-week threshold**. It is recorded as an open review item in ADR-0012; no exception or substitute was chosen.
- **Differences from the specification:**
  - one helper script with subcommands, instead of `compose_smoke.py` alone;
  - an added rendered-configuration (`config`) check;
  - the effective-context listing uses a `FROM scratch` export instead of a listing on the Python base;
  - diagnostics are displayed only on failure, while the key check runs on both paths;
  - the CI helper was added to the mypy scope.
- **Checks actually run in this session (Windows, local):**
  - `uv sync --locked`, `ruff format --check .`, `ruff check .` and `mypy` (104 source files): passed;
  - full suite: `1337 passed, 205 skipped` (204 PostgreSQL skips plus one POSIX-only signal skip);
  - `uv build`: the wheel's 72 entries contain no `infra/`, `tests/` or `Dockerfile` content.

  The staged-diff, whitespace, Gitleaks and artifact checks run after this entry is staged; their results are in the session handoff.
- **Written but not executed:** the image build, the effective build-context check, the image checks and the Compose smoke. Docker was not installed or run, and no database was contacted.
- **Pending:** external review, the uv age decision, the CI container verification, local Compose and overall M3 acceptance.
- **Not done:** nothing committed, pushed or merged.

**Review note (recorded in Prompt 99):**
- **How it was reviewed:** the external reviewer inspected the complete Prompt 98 diff (`.local/p98/m3f-implementation.diff`) and independently matched its SHA-256. The reviewer ran isolated probes of the CI helper, not Docker or the project suite.
- **Not accepted yet.** Reproduced helper failures:
  - **Service-log verification failed open:** with otherwise successful smoke steps, `Smoke.run` returned 0 when every `logs` command exited nonzero, and also when they timed out. `diagnostics()` ignored log return codes, and diagnostic errors never became a primary failure.
  - **Credential exposure before validation:** when `create-key` printed a valid key on stdout, echoed it on stderr and exited nonzero, `create_key` stored stderr for diagnostics but raised before registering the key for redaction. Failure diagnostics then printed the plaintext key.
  - **Cleanup ignored failed ownership checks:** when every label-filtered resource listing exited nonzero, `cleanup` still ran `compose down` and returned 0.
- **Approved exception:** the exact uv 0.13.0 builder-tool image digest already selected in the specification and used by CI, despite its six-day age at implementation. The scope is that pinned digest only:
  - no floating tag or replacement digest;
  - no uv binary in the runtime image;
  - no application dependency or lockfile change;
  - no exception for the Python base image, and no broad dependency-age policy change.

## Prompt 99: Correct M3f CI failure handling and record the uv exception

- **Stage:** Correction of the staged M3f implementation on `feat/container-stack`; staged and uncommitted for review (no commit, push or merge)
- **Date:** 2026-10-15 (session date)
- **Numbering:** 99 is the next unused number after Prompt 98; verified before appending.

````text
Written for: Mathew and the external reviewer.

Prompt 99: Correct M3f CI failure handling and record the uv exception

Correct the reviewed M3f implementation. Leave everything staged and uncommitted.

No commit, push, merge, main update, Docker installation/execution or database contact is authorized.

1. Verify and record the baseline

Expected:
- Branch: feat/container-stack.
- HEAD: b7c9ea28808cfa54a66d55b2ab63f80016594c03.
- Staged tree: dad3438846863ad6d01db447e13a88de4b6980be.
- The same 13 staged paths reported in Prompt 98.
- Nothing unstaged or untracked.
- Local main and origin/main unchanged at 2e605e7bcf3b7b1ee90e9f12cb2acddb6950048f.
- Origin and noreply identity unchanged.

Record the pre-edit staged tree under .local/p99/. Stop on a material mismatch without overwriting work.

2. Service-log verification must fail closed

The reviewer reproduced:
- With successful smoke steps but every logs command returning a nonzero status, Smoke.run returns 0.
- With successful smoke steps but logs commands timing out, it also returns 0.

diagnostics() ignores log-command return codes, and diagnostic errors never become a primary failure when the main steps succeeded.

Correct this:
- Successful retrieval of each required service’s logs is part of smoke acceptance.
- Nonzero status, timeout or retrieval exception must fail an otherwise successful smoke.
- A legitimate empty log from a successful command is permitted.
- If an earlier step already failed, retain that primary failure and report log failures as secondary.
- Never claim the key-in-service-logs check passed when the logs were unavailable.
- Preserve safe diagnostics and redaction.

Add regression tests for nonzero status, timeout and unexpected retrieval exceptions, both with and without an earlier failure.

3. Protect credentials before create-key success is validated

The reviewer reproduced:
- create-key returns a valid key on stdout, echoes it on stderr, and exits nonzero.
- create_key stores stderr for diagnostics, but raises before registering the key for redaction.
- Failure diagnostics then print the plaintext key.

Correct credential handling on every create-key outcome:
- Treat its stdout and stderr as private until safely processed.
- Recognizable credential material must be protected before any return-code or format error can trigger diagnostics.
- Never publish raw failed-command stdout/stderr.
- If output cannot be parsed safely, report a fixed failure and withhold potentially sensitive diagnostics.
- Do not depend on GitHub masking to cover this failure path.
- Continue protecting service logs if the command produced a recognizable key before failing.

Add tests for:
- Nonzero exit with a valid key on stdout and stderr.
- Zero exit with malformed output containing a recognizable key.
- Failure before a key can be safely recovered.
- No plaintext credential in emitted diagnostic output.
- Existing successful key creation and masking still work.

Do not print the probe keys or failing raw output in the handoff.

4. Cleanup must respect failed ownership verification

The reviewer reproduced:
- All label-filtered resource listings return nonzero.
- cleanup still runs compose down and returns 0.

Correct this:
- Check every ownership-listing command’s return status.
- Distinguish a successful empty inventory from an unavailable inventory.
- If ownership verification fails, refuse the destructive operation that depends on it and return failure.
- Do not convert inspection errors into “nothing exists”.
- Check post-cleanup listing failures too; do not report successful cleanup without verification.
- Validate that project and image selections identify the same run and attempt.
- Keep removal scoped to this project and image tag.
- Preserve an earlier workflow failure while separately reporting cleanup failure.

Add tests showing that failed ownership checks prevent compose down, and that verification failures cannot produce cleanup: ok.

5. Record the narrowly approved uv exception

The external reviewer approves the exact uv 0.13.0 image digest already selected in the specification and used by CI, despite its reported six-day age at implementation.

Scope:
- Only the pinned uv builder-tool image.
- No floating tag or replacement digest.
- No uv binary in the runtime image.
- No application dependency or lockfile changes.
- No exception for the Python base image.
- No broad dependency-age policy change.

Record the exception and rationale in ADR-0012, the plan and relevant threat-model wording. Replace the unresolved-decision wording.

The reason is consistency with the existing CI toolchain and the explicitly reviewed digest. Do not claim age-policy compliance or general safety from this exception.

6. Preserve scope and verify

Keep application code, migrations, uv.lock and runtime behaviour unchanged.

Demonstrate the new regression tests failing against the previously staged helper, then restore the corrections and verify file identity.

Run:
- Focused helper tests.
- Ruff formatting and lint.
- Strict Mypy.
- One final full database-independent suite, with actual skip reasons.
- git diff --cached --check.
- Staged Gitleaks and private-content/artifact checks.

No rebuild or wheel check is needed if only CI tooling, tests and documentation changed. Explain any additional verification that is necessary.

Do not run Docker or claim the container checks have executed.

7. Documentation and prompt history

Update only relevant statements to describe the corrected behaviour and approved exception.

Keep M3f implementation review and container verification pending. Overall M3 acceptance and local Compose verification remain pending.

Preserve earlier prompts.md bytes. Append:
- A reviewer note: the complete Prompt 98 diff was inspected and its checksum independently matched.
- The three reproduced helper failures.
- The reviewer ran isolated helper probes, not Docker or the project suite.
- The narrowly approved uv exception.
- This prompt verbatim.
- A truthful outcome note.

8. Review handoff

Export the COMPLETE incremental diff against staged tree
dad3438846863ad6d01db447e13a88de4b6980be,
excluding prompts.md, directly from Git to:

.local/p99/m3f-corrections.diff

Use UTF-8 without a BOM. Do not print the diff in chat.

Report:
- Corrections and regression evidence.
- Actual verification commands/results.
- Files changed and unchanged scope.
- Branch, HEAD, final staged tree and Git status.
- Diff path, baseline, final tree, byte size and SHA-256.
- Remaining limitations.

Keep the current Claude session.

End with:
“Return this output plus .local/p99/m3f-corrections.diff to the external reviewer.”
````

**Outcome note (corrections staged; implementation awaiting external review):**
- **Starting state verified:**
  - branch `feat/container-stack`, HEAD `b7c9ea2`;
  - staged tree `dad3438846863ad6d01db447e13a88de4b6980be` with the 13 Prompt 98 paths; nothing unstaged or untracked;
  - `main` and `origin/main` at `2e605e7`; origin and identity unchanged.

  The baseline tree and the staged helper are recorded under `.local/p99/`.
- **Service logs fail closed:** retrieving every service's logs is now part of smoke acceptance. A nonzero status, a timeout or any retrieval error fails an otherwise successful smoke. After an earlier failure, it is reported as secondary. The key check is reported as not performed for unavailable logs, never as passed. Empty logs from a successful command are accepted.
- **Credentials protected before validation:**
  - Both `create-key` streams are private. Every key-shaped string in either is registered for redaction, service-log checks and masking before the exit status or format is checked. The command's raw output is never kept for display.
  - Redaction also replaces any unregistered key-shaped string.
  - A failure before any key is recoverable reports a fixed message.
- **Cleanup respects ownership:**
  - Every inventory listing's exit status is checked, and an unavailable inventory is never treated as empty. A failed ownership check refuses `compose down` and fails cleanup. A failed post-cleanup verification also fails it, so cleanup reports `ok` only after successful verification.
  - The project and image must name the same run and attempt.
  - The image tag is found with `docker image ls`, which distinguishes an absent tag from an unavailable inventory.
- **uv exception recorded** in ADR-0012, the plan and the threat model, for the exact builder-tool digest only, replacing the open-decision wording.
- **Regression demonstration:** with the Prompt 98 helper temporarily restored from the staged blob, 22 of the 26 new tests failed: every log, credential and cleanup failure the reviewer reproduced. The other 4 confirm unchanged correct behaviour. The corrected helper was restored, and its SHA-256 matched the saved copy.
- **Checks actually run in this session (Windows, local):**
  - `ruff format --check .`, `ruff check .` and `mypy` (104 source files): passed;
  - helper and file tests: `103 passed`;
  - full suite: `1363 passed, 205 skipped` (204 PostgreSQL skips plus one POSIX-only signal skip).

  No rebuild or wheel check: only CI tooling, tests and documentation changed. The staged-diff, whitespace, Gitleaks and artifact checks run after this entry is staged; their results are in the session handoff.
- **Not executed:** the image build and all container checks remain pending CI. Docker was not run, and no database was contacted.
- **Pending:** external review, CI container verification, local Compose and overall M3 acceptance.
- **Not done:** nothing committed, pushed or merged.

**Acceptance note (recorded in Prompt 100):**
- **Accepted:** the external reviewer accepted the Prompt 98 implementation and the Prompt 99 corrections for a local commit.
- **What the reviewer inspected:** both diffs (`.local/p98/m3f-implementation.diff` and `.local/p99/m3f-corrections.diff`), independently matching their reported SHA-256 checksums.
- **What the reviewer probed:** the earlier helper failures were reproduced in isolation, and the corrected helper was checked with isolated probes:
  - unavailable service logs, by nonzero exit or timeout, fail the smoke;
  - failed `create-key` output does not expose the credential in diagnostics, apart from the intentional GitHub `::add-mask::` workflow command;
  - a failed cleanup inventory prevents `compose down` and fails cleanup.
- **Not run by the reviewer:** the project suite, the new pytest regression suite or Docker.
- **Basis:** acceptance also relies on the reported Windows checks and on the regression comparison, in which 22 new tests failed and 4 passed against the Prompt 98 helper.
- **Still pending:** actual container execution, CI for the current version on PostgreSQL and Linux, local Compose and overall M3 acceptance.

## Prompt 100: Commit the reviewed M3f implementation locally

- **Stage:** Acceptance wording and a local commit on branch `feat/container-stack` (no push or merge)
- **Date:** 2026-10-15 (session date)
- **Numbering:** 100 is the next unused number after Prompt 99; verified before appending.

````text
Written for: Mathew and the external reviewer.

Prompt 100 — Commit the reviewed M3f implementation locally. Do not push or merge.

Read CLAUDE.md and the relevant current status sections. Avoid reloading the full prompt history or printing diffs in chat.

Authorization
Commit the reviewed Prompt 98 implementation plus the Prompt 99 corrections locally, with narrowly scoped acceptance wording and prompt-history additions. No publication is authorized.

1. Verify the starting state before editing

Expected:
- Branch: feat/container-stack.
- HEAD: b7c9ea28808cfa54a66d55b2ab63f80016594c03.
- Staged tree: 50da664aec976822b134024d8de401dcd5869b98.
- Exactly these 13 paths staged:
  .dockerignore
  Dockerfile
  .github/workflows/ci.yml
  README.md
  docker-compose.yml
  docs/decisions/0012-containers.md
  docs/plan.md
  docs/threat-model.md
  infra/ci/container_ci.py
  prompts.md
  pyproject.toml
  tests/test_container_ci.py
  tests/test_container_files.py
- Nothing unstaged or untracked.
- Local main and origin/main:
  2e605e7bcf3b7b1ee90e9f12cb2acddb6950048f.
- Origin:
  https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git
- Effective author and committer:
  mathewmljourney93 <257921624+mathewmljourney93@users.noreply.github.com>.

If the state differs materially, stop and report the mismatch without altering it. Record the accepted staged tree under .local/p100/.

2. Preserve the reviewed implementation

Do not change application code, CI tooling, tests, Dockerfile, .dockerignore, Compose configuration, workflows, dependencies, lockfile or tool settings.

Only these files may change relative to the accepted staged tree:
- README.md
- docs/decisions/0012-containers.md
- docs/plan.md
- docs/threat-model.md
- prompts.md

Make only narrow status edits in the four documents:
- M3f is accepted at external review for a local commit.
- Container execution and CI verification remain pending.
- No image build, effective-context check, image check, Compose smoke or real Docker cleanup has run.
- Historical local Windows results are 1363 passed and 205 skipped: 204 PostgreSQL skips and one POSIX-only signal skip.
- The focused helper/file checks reported 103 passed.
- Local Compose and overall M3 acceptance remain pending.
- Nothing is pushed or merged.

Preserve the precise, approved uv exception and its limitations. Do not broaden it or claim age compliance, general safety or production readiness.

Do not redesign the specification or rewrite historical evidence.

3. Record the review accurately

Append an acceptance note under Prompt 99, followed by Prompt 100 verbatim and a truthful pre-commit note.

The acceptance note should record:
- The reviewer accepted the Prompt 98 implementation and Prompt 99 corrections for a local commit.
- The reviewer inspected both diffs and independently matched their reported SHA-256 checksums.
- The reviewer reproduced the earlier helper failures in isolation and checked the corrected helper with isolated probes:
  - unavailable service logs, by nonzero exit or timeout, fail the smoke;
  - failed create-key output does not expose the credential in diagnostics, apart from the intentional GitHub masking workflow command;
  - failed cleanup inventory prevents compose down and fails cleanup.
- The reviewer did not run the project suite, the new pytest regression suite or Docker.
- Acceptance also relies on the reported Windows checks and the regression comparison: 22 new tests failed and four passed against the Prompt 98 helper.
- Actual container execution, current-version PostgreSQL/Linux CI, local Compose and overall M3 acceptance remain pending.

Keep all earlier committed prompt history byte-identical. Do not insert the new commit’s own SHA into its committed note.

4. Check and commit locally

Before committing:
- Verify the staged paths remain exactly the expected 13.
- Confirm every file outside the four permitted documents and prompts.md is byte-identical to accepted tree 50da664aec976822b134024d8de401dcd5869b98.
- Verify the earlier prompts.md content is an identical prefix.
- Check relative links and anchors in the changed documents.
- Check new additions for private content and unintended artifacts without printing sensitive matches.
- Run git diff --cached --check.
- Run the staged Gitleaks scan without suppression or allowlisting.
- Confirm the effective author and committer identity again.

Do not rerun application tests or builds: the implementation must remain unchanged. Do not start Docker or contact a database.

Commit with subject:
feat: add development container stack and CI Compose smoke

Use the same Co-Authored-By trailer as the earlier commits.

After committing:
- Run the full-history Gitleaks scan.
- Confirm the parent is b7c9ea28808cfa54a66d55b2ab63f80016594c03.
- Confirm the expected 13 committed paths.
- Confirm all files outside the four permitted documents and prompts.md remain byte-identical to the accepted tree.
- Confirm the working tree is clean.
- Confirm main and origin/main remain unchanged.

If a check fails, report it accurately. Do not suppress findings, amend, reset or publish.

5. Export the incremental review diff

Export the complete diff from accepted tree
50da664aec976822b134024d8de401dcd5869b98
to the new commit, excluding prompts.md, to:

.local/p100/m3f-commit-incremental.diff

Use UTF-8 without BOM. Report:
- baseline tree and final commit;
- changed paths and diff statistics;
- byte size and SHA-256.

Do not print the diff in chat.

6. Handoff

Report the commit SHA, parent, subject, identity, committed paths, checks, byte-identity verification and final Git state.

Clearly separate historical Windows results from checks performed in this task. State that all real container verification remains pending an authorized publication and CI.

No push, merge, force-push, amend, rebase, tag, branch deletion, Docker execution or database contact is authorized.

Return this output plus .local/p100/m3f-commit-incremental.diff to the external reviewer.
````

**Pre-commit note (written before the commit; the commit's own SHA is not recorded here):**
- **Starting state verified:**
  - branch `feat/container-stack`, HEAD `b7c9ea2`;
  - staged tree `50da664aec976822b134024d8de401dcd5869b98` with exactly the 13 expected paths; nothing unstaged or untracked;
  - `main` and `origin/main` at `2e605e7`; origin and the noreply identity as expected.

  The accepted tree is recorded under `.local/p100/`.
- **Changes since the accepted tree:**
  - narrow status wording in `README.md`, ADR-0012, `docs/plan.md` and `docs/threat-model.md`: M3f accepted at external review for a local commit; container execution and CI verification pending; no image build, effective-context check, image check, Compose smoke or real Docker cleanup run; local Compose and overall M3 acceptance pending; nothing pushed or merged;
  - this prompt history.

  The approved uv exception is unchanged. Every other file is to remain byte-identical to the accepted tree.
- **Historical local results** (Prompt 99, Windows), not rerun here: `1363 passed, 205 skipped` (204 PostgreSQL skips and one POSIX-only signal skip), and `103 passed` for the focused helper and file tests.
- **Checks for this commit:** run after this entry is staged; results are in the session handoff. They are the staged-path, accepted-tree byte-identity, prompt-history prefix, link, private-content, `git diff --cached --check`, staged Gitleaks and identity checks, and after the commit the full-history Gitleaks scan. No application tests, builds or Docker execution.
- **Not done:** nothing pushed or merged; no Docker or database contact.

**Commit outcome (recorded in Prompt 101):**
- **Commit:** `56fc3b5327ff860a9ed9a092dfd591b8edb7dcdf` ("feat: add development container stack and CI Compose smoke"), parent `b7c9ea2`, tree `7caae5d853eefecf743eaac64b353276213a6ef5`, on the local branch `feat/container-stack`, with the noreply author and committer identity and the existing co-author trailer.
- **Content:** the 13 reviewed paths. Only `README.md`, ADR-0012, `docs/plan.md`, `docs/threat-model.md` and `prompts.md` differed from accepted tree `50da664`.
- **Checks reported in the Prompt 100 handoff:**
  - byte identity of every other file;
  - an identical earlier prompt-history prefix;
  - no broken links; no private-content matches;
  - a clean `git diff --cached --check`; staged Gitleaks with no leaks;
  - full-history Gitleaks after the commit: 40 commits scanned, no leaks found;
  - working tree clean; `main` and `origin/main` unchanged at `2e605e7`.
- **Diff:** `.local/p100/m3f-commit-incremental.diff`, 18,560 bytes, SHA-256 `5906bf220c5a787419287d2a15d18c73a61815f3756de9de06cefc03702f276b`.
- Nothing was pushed or merged.

**Review note (recorded in Prompt 101):**
- **Accepted:** the external reviewer accepted the Prompt 100 incremental documentation diff.
- **How it was reviewed:** the reviewer inspected it and independently matched its checksum. The reviewer ran no project tests and no Docker in this review.

## Prompt 101: Publish only the reviewed M3f feature branch and monitor CI

- **Stage:** Publication of `feat/container-stack` only, and CI monitoring (no merge, no `main` update)
- **Date:** 2026-10-15 (session date)
- **Numbering:** 101 is the next unused number after Prompt 100; verified before appending.

````text
Written for: Mathew and the external reviewer.

Prompt 101 — Publish only the reviewed M3f feature branch and monitor CI. Do not merge or update main.

Read CLAUDE.md and the relevant workflow sections. Do not reload the full prompt history or print diffs.

1. Verify the starting state

Expected:
- Branch: feat/container-stack.
- HEAD: 56fc3b5327ff860a9ed9a092dfd591b8edb7dcdf.
- Parent: b7c9ea28808cfa54a66d55b2ab63f80016594c03.
- Working tree clean.
- No upstream or remote feat/container-stack branch.
- Local main and origin/main:
  2e605e7bcf3b7b1ee90e9f12cb2acddb6950048f.
- Origin:
  https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git
- Effective author and committer use:
  mathewmljourney93 <257921624+mathewmljourney93@users.noreply.github.com>.

Read fresh remote refs. Confirm remote main is unchanged and an ancestor of HEAD. If the state differs materially, stop without modifying it.

2. Publication preflight

Inspect everything that would become public relative to remote main:
- the specification commit b7c9ea2;
- the implementation commit 56fc3b5;
- the history commit authorized below.

Confirm:
- noreply author and committer identities;
- no tracked local artifacts, backups, bundles, real environment files, credentials or build outputs;
- no secrets, personal paths or unintended private content in the additions;
- the existing .env.example remains a documented placeholder file;
- both workflows trigger on this branch.

Confirm CI retains:
- Ubuntu verification;
- Windows verification;
- PostgreSQL integration with EG_REQUIRE_INTEGRATION=1;
- the new container job;
- full-history Gitleaks.

There are now FIVE expected jobs, not four. The container job is required for this publication review.

Do not modify source, tests, Docker configuration, workflows, dependencies, lockfile or the reviewed documentation.

3. Append prompt history and commit

Change prompts.md only, append-only:
- Record the Prompt 100 commit outcome and its reported checks.
- Record the reviewer's acceptance of the incremental documentation diff: inspected and checksum independently matched; no project tests or Docker run by the reviewer in this review.
- Append Prompt 101 verbatim.
- Add a preflight note with the verified state, publication scope, checks and branch-only authorization.

Keep historical Windows results separate from new CI:
1363 passed, 205 skipped, including 204 PostgreSQL skips and one POSIX-only signal skip.

State that all real container execution was pending before publication. Do not pre-record push or CI outcomes.

Verify the earlier history is an identical prefix, scan the additions for private content, run git diff --cached --check and the staged Gitleaks scan without suppression.

Commit prompts.md only with subject:
docs: record M3f branch publication authorization

Use the existing co-author trailer and noreply identity.

Verify only prompts.md changed, the parent is 56fc3b5 and the tree is clean. Run the full-history Gitleaks scan before pushing. Stop on a finding; do not allowlist or suppress it.

4. Push only the feature branch

Run directly, preserving Git's own exit status:

git push --set-upstream origin refs/heads/feat/container-stack:refs/heads/feat/container-stack

No other ref, tag or main update is authorized. Confirm the remote branch matches the exact published HEAD.

5. Monitor CI for that exact commit

Monitor both push-triggered workflow runs for the published SHA on feat/container-stack, for up to 25 minutes total.

Use existing GitHub access or the public read-only API. Do not install tools or add credentials. Use bounded requests and sensible polling intervals.

Report these five jobs separately:
- verify: Ubuntu;
- verify: Windows;
- PostgreSQL integration;
- container;
- Gitleaks full history.

For the container job, report the actual step conclusions for:
- rendered Compose configuration;
- effective build-context check;
- application image build;
- runtime image checks;
- Compose smoke;
- cleanup.

A green job with a skipped smoke step does not establish smoke verification. Distinguish success, failure and skipped steps.

Retrieve pytest summaries and container output if accessible. If logs are inaccessible, report that explicitly and give the run and job links. Do not invent counts or treat old counts as new results.

If a job fails:
- report the failing job, step and accessible diagnostic evidence;
- redact credentials and private output;
- do not change files, retry failed workflows, make a fix commit or push again;
- stop for review.

If monitoring times out, report what remains pending. Do not claim a background poll continues after this task ends.

6. Final handoff

Report:
- history commit SHA and parent;
- exact published SHA;
- push command and exit status;
- run/job links and conclusions;
- observed test summaries, separately from unobserved expectations;
- which real container checks actually executed;
- final branch/upstream and working-tree state;
- confirmation that main remains unchanged.

Do not update documentation after CI in this task. Recording the results will be a later reviewed task.

Do not run local Docker, contact a local database, merge, update main, force-push, amend, rebase, tag or delete branches. Overall M3 acceptance remains pending even if CI passes. Local Compose remains unverified.

Return this output only to the external reviewer; no diff attachment is required.
````

**Preflight note (written before the push; no push or CI result is recorded here):**
- **Authorization:** Prompt 101 authorizes publishing **only** `feat/container-stack` and monitoring its CI. No merge, no `main` update, no force-push, no other ref and no tag.
- **Starting state verified:**
  - branch `feat/container-stack` at `56fc3b5` (parent `b7c9ea2`), working tree clean, no upstream;
  - fresh remote refs: no remote `feat/container-stack`, and remote `main` at `2e605e7`, an ancestor of HEAD;
  - origin and the noreply identity as expected.
- **Publication scope:** the specification commit `b7c9ea2`, the implementation commit `56fc3b5`, and this history commit, which changes only `prompts.md`.
- **Preflight checks:**
  - All commits use the noreply identity.
  - No tracked `.local/`, backups, bundles, build outputs, wheels, keys or real environment files. The only environment file is the existing placeholder `.env.example`, which is unchanged in this range.
  - No binary files.
  - One added line matched the private-path pattern: the repository path in Prompt 98's verbatim text, which already appears 83 times in published history.
  - Gitleaks over `origin/main..HEAD`: 2 commits scanned, no leaks found.
- **Workflows:** both trigger on every push and pull request, with no branch filters. CI keeps five jobs:
  - Ubuntu and Windows `verify`;
  - PostgreSQL integration with `EG_REQUIRE_INTEGRATION=1`;
  - the new `container` job;
  - full-history Gitleaks (`fetch-depth: 0`).
- **Verification status before publication:**
  - **Historical local Windows results** (Prompt 99): `1363 passed, 205 skipped` (204 PostgreSQL skips and one POSIX-only signal skip).
  - **Not yet run:** all real container execution (image build, effective build-context check, image checks, Compose smoke and Docker cleanup), and CI for this version.

**Publication outcome (recorded in Prompt 102):**
- **History commit:** `682101b4f06d099b147b8d21734fa83f7f53637f` ("docs: record M3f branch publication authorization"), parent `56fc3b5`, changing only `prompts.md`. Full-history Gitleaks before the push scanned 41 commits and found no leaks.
- **Push:** `git push --set-upstream origin refs/heads/feat/container-stack:refs/heads/feat/container-stack` exited 0 and created the remote branch. Remote `feat/container-stack` matched `682101b` exactly; remote `main` stayed at `2e605e7`. No other ref, tag or force-push.
- **What Claude observed** through the public GitHub API: [ci run 38769986459](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38769986459) and [secret-scan run 38769986224](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38769986224) were push events on `feat/container-stack` at `682101b`, and all five jobs concluded `success`: Ubuntu verify, Windows verify, PostgreSQL integration, container and full-history Gitleaks. Every container step concluded `success` and none was skipped: rendered Compose configuration, effective build context, image build, image checks, Compose smoke and cleanup.
- **What Claude could not observe:** the job-log endpoint returned HTTP 403 (admin rights required), so Claude reported every test count and all container output as unobserved.

**Reviewer evidence note (recorded in Prompt 102):** the external reviewer retrieved both workflow-run records and all five job logs. Both runs were push events on `feat/container-stack` at exact head commit `682101b4f06d099b147b8d21734fa83f7f53637f`, with conclusion success. The reviewer did not run the project suite or Docker locally. Observed results:
- Ubuntu job 116542962186: `1364 passed, 204 skipped in 27.63s`.
- Windows job 116542962338: `1363 passed, 205 skipped in 39.61s`.
- PostgreSQL job 116542961580: `204 passed, 1364 deselected in 59.62s`.
- Container job 116542962209:
  - `compose config: ok`; `context: ok (72 files; 19 planted fixtures excluded)`; the application image built;
  - UID and GID 10001 checks passed; `eg-api`, `eg-worker` and `eg-admin` `--help` checks passed; installed imports, offline migration SQL and runtime contents checks passed;
  - the stack started (database healthy, migration complete, API healthy), and `migrate`, `api` and `worker` used the CI-built image;
  - an API key was created and held in memory; the upload was accepted with 202; the ingestion job succeeded; the revision was active with 2 verified chunks;
  - a duplicate upload returned the existing revision with 200; the idle worker exited with code 0 and no OOM kill;
  - `smoke: ok`; `cleanup: ok`.
- Secret-scan job 116542954404: 41 commits scanned, no leaks found.

## Prompt 102: Record verified M3f feature-branch CI results

- **Stage:** Documentation of verified CI results on `feat/container-stack`; staged and uncommitted for review (no commit, push or merge)
- **Date:** 2026-10-15 (session date)
- **Numbering:** 102 is the next unused number after Prompt 101; verified before appending.

````text
Written for: Mathew and the external reviewer.

Prompt 102 — Record verified M3f feature-branch CI results. Stage documentation for review; do not commit, push or merge.

Read CLAUDE.md and relevant status sections only. Do not reload the complete prompt history or print diffs.

1. Verify starting state

Expected:
- Branch: feat/container-stack.
- HEAD and upstream:
  682101b4f06d099b147b8d21734fa83f7f53637f.
- Parent:
  56fc3b5327ff860a9ed9a092dfd591b8edb7dcdf.
- Working tree clean.
- Local main and origin/main:
  2e605e7bcf3b7b1ee90e9f12cb2acddb6950048f.
- Expected origin and noreply identity unchanged.

Check fresh remote refs read-only. Stop on a material mismatch. Record the baseline under .local/p102/.

2. Record independently retrieved evidence

The external reviewer retrieved all five job logs and both workflow-run records. Both runs were push events on feat/container-stack with exact head commit `682101b4f06d099b147b8d21734fa83f7f53637f` and conclusion success.

CI run:
https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38769986459

Observed summaries:
- Ubuntu job 116542962186:
  1364 passed, 204 skipped in 27.63s.
- Windows job 116542962338:
  1363 passed, 205 skipped in 39.61s.
- PostgreSQL job 116542961580:
  204 passed, 1364 deselected in 59.62s.

Container job 116542962209:
https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38769986459/job/116542962209

Observed output:
- compose config: ok
- context: ok (72 files; 19 planted fixtures excluded)
- application image built successfully
- UID and GID 10001 checks passed
- eg-api, eg-worker and eg-admin --help checks passed
- installed imports, offline migration SQL and runtime contents checks passed
- stack started: database healthy, migration complete, API healthy
- migrate, api and worker used the CI-built image
- API key created and held in memory
- upload accepted with 202
- ingestion job succeeded
- revision active; 2 verified chunks
- duplicate upload returned the existing revision with 200
- idle worker exited with code 0 and no OOM kill
- smoke: ok
- cleanup: ok

Secret-scan run:
https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38769986224
Job 116542954404:
41 commits scanned, no leaks found.

Attribute these log results to the external reviewer. The reviewer did not run the project suite or Docker locally. Preserve Claude's earlier account that its anonymous API session could not retrieve logs.

3. Documentation scope

Modify only:
- README.md
- docs/decisions/0012-containers.md
- docs/plan.md
- docs/threat-model.md
- prompts.md

Record M3f as reviewed and verified in CI on feat/container-stack at `682101b`, not merged. Main remains at `2e605e7`.

Replace current claims that no container build, context check, image check, Compose smoke or cleanup has run. Preserve historical pre-CI statements when clearly labelled historical.

Include full evidence and links in the README M3f entry and ADR-0012; concise references elsewhere. Keep the historical Windows results separate.

State precisely:
- CI Compose verification is complete for this version.
- Under the accepted specification, this can satisfy M3's Compose requirement alongside its other criteria.
- Local Compose remains unverified.
- The smoke proves the tested idle-worker shutdown, not an in-flight handler shutdown bound.
- Overall M3 acceptance remains pending a separate review.
- The stack is for development; no production readiness, benchmark or general security guarantee is claimed.
- The approved uv exception remains unchanged.

Sweep current M3 status sections for contradictory M3f wording. Narrowly correct stale present-tense claims such as “M3f is not implemented”, while preserving historical baseline descriptions.

Do not implement anything or begin M4.

4. Prompt history

Append:
- The Prompt 101 publication outcome, separating Claude's API observations from the logs it could not retrieve.
- A reviewer-evidence note containing the verified results above.
- Prompt 102 verbatim and an outcome note marking this documentation as awaiting review.

Preserve all earlier bytes. Write commit references inline in backticks to avoid the earlier public-SHA Gitleaks false positive. Do not alter the existing formatting-exception history.

5. Checks and staging

Stage exactly the five permitted files.

Verify:
- earlier prompts.md content is an identical prefix;
- relative links and anchors;
- stale current-status wording;
- no private content or unintended artifacts;
- git diff --cached --check;
- staged Gitleaks without suppression or allowlisting.

No application tests, builds, Docker or database contact are needed for this documentation-only task.

Do not commit, push, merge, amend, rebase, tag or delete branches.

6. Review export and handoff

Export the complete staged diff against HEAD, excluding prompts.md, to:
.local/p102/m3f-verification-docs.diff

Use UTF-8 without BOM. Report baseline commit, final staged tree, changed paths, statistics, byte size and SHA-256. Do not print the diff.

Report checks and final Git state. Keep overall M3 acceptance and merging into main pending.

Return this output plus .local/p102/m3f-verification-docs.diff to the external reviewer.
````

**Outcome note (documentation staged, awaiting review):**
- **Starting state verified:**
  - branch `feat/container-stack`; HEAD and upstream `682101b` (parent `56fc3b5`); working tree clean;
  - fresh remote refs: remote `feat/container-stack` at `682101b`, local and remote `main` at `2e605e7`;
  - origin and noreply identity unchanged.

  The baseline is recorded under `.local/p102/`.
- **Documentation:** status updates in `README.md`, ADR-0012, `docs/plan.md` and `docs/threat-model.md`.
  - **New status:** M3f is reviewed and verified in CI on `feat/container-stack` at `682101b`, not merged, with `main` at `2e605e7`. The full evidence is in the README container section and ADR-0012, with concise references elsewhere, attributed to the reviewer's retrieval of the logs.
  - **Replaced:** current claims that no container check had run, labelling the pre-CI statement in ADR-0012 as historical.
  - **Stale wording corrected:** the M3d status line's present-tense "M3f is not implemented" is now scoped to its baseline.
  - **Kept:** the historical Windows results separate; the uv exception unchanged.
  - **Stated:**
    - CI Compose verification is complete for this version, and can satisfy M3's Compose requirement under the accepted specification;
    - local Compose is unverified;
    - the smoke shows idle-worker shutdown only, not an in-flight handler bound;
    - overall M3 acceptance needs a separate review;
    - there is no production-readiness, benchmark or general security claim.
- **Checks:** the staged-path, history, link, stale-wording, private-content, `git diff --cached --check` and staged Gitleaks checks run after this entry is staged; results are in the session handoff. No application tests, builds, Docker or database contact.
- **Not done:** nothing committed, pushed or merged.

**Acceptance note (recorded in Prompt 103):**
- **Accepted:** the external reviewer accepted the Prompt 102 documentation diff, with one clarification applied in Prompt 103: ADR-0012's "Docker behaviour relied on" bullet now separates the behaviours the passing run exercised from Docker's documented forced SIGKILL after `stop_grace_period`, which the run did not exercise.
- **How it was reviewed:** the reviewer inspected `.local/p102/m3f-verification-docs.diff`, independently matched its SHA-256, and checked it against the previously retrieved CI logs.
- **Not run by the reviewer:** a local suite or Docker.

## Prompt 103: Commit the reviewed M3f results, publish the feature branch, then fast-forward main

- **Stage:** A documentation commit on `feat/container-stack`, publication of the feature branch, and a fast-forward of `main` only after all five checks pass
- **Date:** 2026-10-15 (session date)
- **Numbering:** 103 is the next unused number after Prompt 102; verified before appending.

````text
Written for: Mathew and the external reviewer.

Prompt 103 — Commit the reviewed M3f results, publish the feature branch, then fast-forward main only after all five checks pass.

Read CLAUDE.md and relevant workflow/status sections. Do not reload full prompt history or print diffs.

1. Verify starting state

Expected:
- Branch: feat/container-stack.
- HEAD, upstream and remote feature branch:
  682101b4f06d099b147b8d21734fa83f7f53637f.
- Staged tree:
  d3917b0d994915e88508f34d187dcee8c4feef69.
- Exactly five staged paths:
  README.md
  docs/decisions/0012-containers.md
  docs/plan.md
  docs/threat-model.md
  prompts.md
- Nothing unstaged or untracked.
- Local main, origin/main and remote main:
  2e605e7bcf3b7b1ee90e9f12cb2acddb6950048f.
- Expected origin and noreply author/committer identity unchanged.

Fetch fresh refs. Confirm main is an ancestor of HEAD and has no independent local commits. Stop on material mismatch. Record the accepted staged tree under .local/p103/.

2. One authorized documentation clarification

In ADR-0012's final “Docker behaviour relied on” bullet, distinguish:
- behaviours exercised by the passing run;
- Docker's documented forced-SIGKILL behaviour after stop_grace_period, which was NOT exercised because the idle worker exited normally.

Keep the 60-second external termination budget and existing shutdown limitations unchanged. This is a wording clarification only.

Otherwise preserve README, plan and threat model byte-identical to the accepted tree. No source, tests, Docker configuration, workflows, dependencies or tool settings may change.

Do not mark overall M3 accepted.

3. Prompt history and local commit

Append:
- Acceptance note under Prompt 102: reviewer inspected the diff, independently matched its checksum, checked it against the previously retrieved CI logs, and accepted it with the SIGKILL wording clarification. Reviewer ran no local suite or Docker.
- Prompt 103 verbatim.
- A preflight note recording the verified state, checks, authorized publication order and stop conditions.

Preserve all earlier bytes. Do not pre-record pushes, new CI outcomes or the main update.

Check:
- exactly five staged paths;
- only ADR-0012 and prompts.md differ from the accepted tree;
- earlier prompts.md content is an identical prefix;
- links and anchors;
- private content and unintended artifacts;
- git diff --cached --check;
- staged Gitleaks without suppression;
- effective author and committer identity.

Commit with subject:
docs: record verified M3f results and main publication authorization

Use the existing co-author trailer.

Verify parent, paths and clean tree. Run full-history Gitleaks before publication. Stop on a finding. Do not suppress, allowlist or amend.

No application tests, builds, local Docker or database contact are needed.

4. Push the feature branch and verify five jobs

Run directly, preserving Git's exit status:

git push origin refs/heads/feat/container-stack:refs/heads/feat/container-stack

Confirm the exact remote SHA. Monitor push-triggered workflows for that SHA and branch, up to 25 minutes.

All FIVE jobs must succeed:
- Ubuntu verify;
- Windows verify;
- PostgreSQL integration;
- container;
- full-history Gitleaks.

The container configuration, context, build, image, smoke and cleanup steps must execute successfully, not be skipped.

If any required job fails, is cancelled or remains pending at the limit, stop without changing main. Report accessible evidence; do not fix files, rerun workflows or push again.

Use existing GitHub access or public read-only API. Do not add credentials or install tools. Retrieve logs if accessible; otherwise report counts as unobserved. Never reuse the 682101b counts as results for the new SHA.

5. Fast-forward main only after five green jobs

Fetch fresh refs again and verify:
- remote main is still 2e605e7bcf3b7b1ee90e9f12cb2acddb6950048f;
- remote feature equals the newly verified commit;
- main is an ancestor of that commit;
- local main equals origin/main with no independent commits;
- working tree clean.

If any precondition fails, stop.

Switch to main and fast-forward using:
git merge --ff-only <the exact verified commit>

Then push only:
git push origin refs/heads/main:refs/heads/main

No force-push or merge commit.

Monitor all five jobs again for the exact commit's push to main, up to 25 minutes. Report failures accurately and stop; do not roll back, fix, rerun or make further pushes.

6. Handoff

Report:
- commit SHA, parent, subject, identity and paths;
- exact changes against the accepted tree;
- scans and checks;
- both push commands and Git exit statuses;
- all five job conclusions and run/job links for each push;
- container step conclusions;
- observed summaries separately from inaccessible counts;
- refs before/after and final working-tree status.

Leave documents unchanged after publication. Recording main results and overall M3 acceptance belongs to a later review.

No force-push, amend, rebase, squash, tag, branch deletion, local Docker or database contact. Do not start M4.

Export the incremental diff from accepted tree d3917b0d994915e88508f34d187dcee8c4feef69 to the new commit, excluding prompts.md, to:
.local/p103/m3f-publication-incremental.diff

Report baseline/final, size and SHA-256; UTF-8 without BOM. Do not print it.

Return this output plus .local/p103/m3f-publication-incremental.diff to the external reviewer.
````

**Preflight note (written before the commit; no push, CI or `main` result is recorded here):**
- **Starting state verified:**
  - branch `feat/container-stack`; HEAD, upstream and remote feature branch at `682101b`;
  - staged tree `d3917b0d994915e88508f34d187dcee8c4feef69` with exactly the five expected paths; nothing unstaged or untracked;
  - fresh refs: local `main`, `origin/main` and remote `main` at `2e605e7`, an ancestor of HEAD, with no independent local commits;
  - origin and the noreply identity as expected.

  The accepted tree is recorded under `.local/p103/`.
- **Changes since the accepted tree:** only the authorized ADR-0012 wording clarification, and this prompt history. `README.md`, `docs/plan.md` and `docs/threat-model.md` are to stay byte-identical.
- **Checks before the commit:** run after this entry is staged; results are in the session handoff. They are the staged-path, accepted-tree comparison, prompt-history prefix, link, private-content, `git diff --cached --check`, staged Gitleaks and identity checks, then full-history Gitleaks before publication.
- **Authorized publication order:**
  1. commit locally;
  2. push `feat/container-stack` only;
  3. require all five jobs to succeed for that exact commit (Ubuntu verify, Windows verify, PostgreSQL integration, container with its configuration, context, build, image, smoke and cleanup steps executed successfully, and full-history Gitleaks);
  4. re-verify fresh refs, fast-forward `main` with `--ff-only` to that exact commit, and push only `main`;
  5. monitor the five jobs again.
- **Stop conditions:**
  - any finding from a scan;
  - any required job failing, cancelled, skipped in a required container step, or pending after 25 minutes;
  - any precondition for the fast-forward not holding.

  On any stop: no fixes, reruns, rollbacks or further pushes.
- **Not authorized:** force-push, amend, rebase, squash, tag, branch deletion, local Docker or database contact. Overall M3 acceptance remains pending.

**Publication outcome (recorded in Prompt 104):**
- **Documentation commit:** `e2463cb5a94d7c40eb1d894b8fded29a866165a8`, parent `682101b`, noreply identity. Only ADR-0012 (the SIGTERM/SIGKILL clarification) and `prompts.md` differed from accepted tree `d3917b0`. Full-history Gitleaks before publication scanned 42 commits and found no leaks.
- **Feature push:** `git push origin refs/heads/feat/container-stack:refs/heads/feat/container-stack` exited 0 (`682101b..e2463cb`). Claude observed through the public API that [ci run 38772852347](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38772852347) and [secret-scan run 38772852507](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38772852507) (push events on `feat/container-stack` at `e2463cb`) concluded `success` in all five jobs, and that all six container steps concluded `success`, none skipped.
- **Main fast-forward:**
  - Preconditions held on fresh refs: remote `main` still at `2e605e7` and an ancestor; remote feature branch at `e2463cb`; local `main` equal to `origin/main`; clean tree.
  - `git merge --ff-only` and `git push origin refs/heads/main:refs/heads/main` both exited 0 (`2e605e7..e2463cb`).
  - Claude observed [ci run 38773393988](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38773393988) and [secret-scan run 38773393999](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38773393999) (push events on `main` at `e2463cb`) concluding `success` in all five jobs, with all six container steps `success`.
- **Not observed by Claude:** the job-log endpoint returned HTTP 403, so Claude reported every count and all container output for `e2463cb` as unobserved.
- **Not done:** no force-push, merge commit, tag or branch deletion.

**Reviewer evidence note (recorded in Prompt 104):**
- **Incremental diff:** the external reviewer inspected the Prompt 103 incremental diff (`.local/p103/m3f-publication-incremental.diff`) and independently matched its checksum. It contains only the approved SIGTERM/SIGKILL wording clarification.
- **Main results:** the reviewer retrieved both `main` workflow-run records and all five job logs. Both runs were push events on `main` at exact head commit `e2463cb5a94d7c40eb1d894b8fded29a866165a8`, with conclusion success. The reviewer did not run the suite or Docker locally. Observed results:
  - Ubuntu job 116554736110: `1364 passed, 204 skipped in 28.13s`.
  - Windows job 116554736342: `1363 passed, 205 skipped in 39.10s`.
  - PostgreSQL job 116554736165: `204 passed, 1364 deselected in 61.97s (0:01:01)`.
  - Container job 116554735789:
    - `compose config: ok`; `context: ok (72 files; 19 planted fixtures excluded)`;
    - image checks passed (UID/GID 10001, all three CLI helps, installed imports, offline migration SQL, runtime contents);
    - the stack started with the database healthy, migration complete and API healthy, and `migrate`, `api` and `worker` used the CI-built image;
    - an API key was created and held in memory; the upload was accepted with 202; the ingestion job succeeded; the revision was active with 2 verified chunks;
    - a duplicate upload returned the existing revision with 200; the idle worker exited with code 0 and no OOM kill;
    - `smoke: ok`; `cleanup: ok`.
  - Secret-scan job 116554735382: 42 commits scanned, no leaks found.

## Prompt 104: Record M3f main verification and prepare the overall M3 acceptance assessment

- **Stage:** Documentation only, on branch `docs/m3-acceptance` created from `e2463cb`; staged and uncommitted for review
- **Date:** 2026-10-16 (session date)
- **Numbering:** 104 is the next unused number after Prompt 103; verified before appending.

````text
Written for: Mathew and the external reviewer.

Prompt 104 — Record M3f main verification and prepare the overall M3 acceptance assessment. Documentation only; stage for review.

Read CLAUDE.md and relevant plan, ADR and test sections. Avoid reloading full prompt history. Do not print diffs.

1. Verify starting state

Expected:
- Current branch: main.
- HEAD, origin/main and remote main:
  e2463cb5a94d7c40eb1d894b8fded29a866165a8.
- Parent:
  682101b4f06d099b147b8d21734fa83f7f53637f.
- Local and remote feat/container-stack at the same commit.
- Working tree clean.
- Expected origin and noreply identity unchanged.

Read fresh remote refs. Stop on material mismatch.

Create docs/m3-acceptance from HEAD, provided that branch does not already exist. Do not overwrite an existing branch.

2. Record verified main results

The external reviewer retrieved both main workflow-run records and all five job logs. Both runs were push events on main at exact head commit `e2463cb5a94d7c40eb1d894b8fded29a866165a8`, conclusion success.

CI:
https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38773393988

Observed summaries:
- Ubuntu, job 116554736110:
  1364 passed, 204 skipped in 28.13s.
- Windows, job 116554736342:
  1363 passed, 205 skipped in 39.10s.
- PostgreSQL, job 116554736165:
  204 passed, 1364 deselected in 61.97s (0:01:01).

Container job 116554735789:
- compose config: ok
- context: ok (72 files; 19 planted fixtures excluded)
- image checks passed: UID/GID 10001, all three CLI helps, installed imports, offline migration SQL, runtime contents
- stack started with database healthy, migration complete and API healthy
- migrate, api and worker used the CI-built image
- API key created and held in memory
- upload accepted with 202
- ingestion job succeeded
- revision active; 2 verified chunks
- duplicate upload returned the existing revision with 200
- idle worker exited with code 0 and no OOM kill
- smoke: ok
- cleanup: ok

Secret scan:
https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38773393999
Job 116554735382:
42 commits scanned, no leaks found.

Attribute the logs to the external reviewer, who did not run the suite or Docker locally. Preserve Claude's earlier report that its anonymous session could not retrieve logs.

The reviewer also inspected the Prompt 103 incremental diff and independently matched its checksum. It contains only the approved SIGTERM/SIGKILL wording clarification.

3. Documentation scope

Modify only:
- README.md
- docs/decisions/0012-containers.md
- docs/plan.md
- docs/threat-model.md
- prompts.md

Record M3f as verified and on main at e2463cb. Replace current “not merged” wording, preserving the earlier 682101b feature-branch evidence as historical.

Include full main evidence and links in the README M3f entry and ADR-0012, with concise references elsewhere.

Preserve:
- local Compose remains unverified;
- CI Compose satisfies the agreed Compose verification requirement;
- shutdown smoke covers an idle worker, not an in-flight handler bound or forced SIGKILL;
- the uv exception remains unchanged;
- development-only scope and existing limitations.

4. Prepare an overall M3 acceptance assessment

In docs/plan.md, add a concise criterion-to-evidence table covering:
- specified upload errors and idempotent re-uploads;
- tenant- and revision-specific chunk IDs;
- failed replacement retaining the previous active revision;
- out-of-order completion leaving only the newer revision active;
- activation rollback;
- concurrent claims producing one owner;
- stale-worker fencing for chunks, activation and job completion;
- retries reaching dead;
- worker lease-loss cancellation;
- truthful stalled/dead ingestion projection;
- image build, effective context, runtime checks and Compose smoke.

Inspect the existing test names and relevant implementation as needed to identify concrete supporting tests and their verification jobs. Link to actual files and use real test names. Do not infer coverage merely from total test counts.

Distinguish database-independent simulations from real PostgreSQL tests and from the real Compose smoke. Identify any unmet criterion honestly.

Mark this assessment “prepared for external review”. Do not mark overall M3 accepted yet. Do not weaken criteria to make them pass.

Do not design or start M4 in this task.

5. Prompt history

Append:
- Prompt 103 publication outcome, keeping Claude's observations separate from unavailable logs;
- reviewer evidence for main, including the results above;
- the incremental-diff acceptance and checksum verification;
- Prompt 104 verbatim and an outcome note marking overall M3 acceptance as awaiting review.

Preserve all earlier bytes. Use inline backticked commit references in your own notes.

6. Checks and staging

Stage exactly the five permitted files.

Check:
- earlier prompts.md content remains an identical prefix;
- relative links and anchors;
- current status wording versus historical statements;
- private content and unintended artifacts;
- git diff --cached --check;
- staged Gitleaks without suppression.

No application tests, builds, Docker or database contact are needed. Do not commit, push, merge, amend, rebase, tag or delete branches.

7. Review export

Export the complete staged diff against HEAD, excluding prompts.md, to:
.local/p104/m3-acceptance-assessment.diff

UTF-8 without BOM. Report baseline commit, final staged tree, changed paths, statistics, byte size and SHA-256. Do not print the diff.

Report any acceptance gaps, checks and final Git state.

Return this output plus .local/p104/m3-acceptance-assessment.diff to the external reviewer.
````

**Outcome note (documentation staged; overall M3 acceptance awaiting review):**
- **Starting state verified:**
  - branch `main`; HEAD, `origin/main` and remote `main` at `e2463cb` (parent `682101b`);
  - local and remote `feat/container-stack` at the same commit; working tree clean;
  - origin and noreply identity unchanged.

  Branch `docs/m3-acceptance` was created from `e2463cb` (it did not exist before).
- **M3f main results recorded:** in `README.md`, ADR-0012, `docs/plan.md` and `docs/threat-model.md`, attributed to the reviewer's retrieval of the logs.
  - The full `main` evidence is in the README container section and ADR-0012, with concise references elsewhere.
  - Current "not merged" wording was replaced; the `682101b` feature-branch evidence is kept and labelled historical.
  - Unchanged: local Compose unverified; CI Compose satisfying the agreed Compose verification requirement; the idle-worker-only shutdown coverage (no in-flight drain or forced SIGKILL); the uv exception; the development-only scope.
- **Overall M3 acceptance assessment** added to `docs/plan.md` and marked **prepared for external review**.
  - **Table:** maps each criterion to real test names in 14 linked test files. Every name was checked to exist, and the PostgreSQL evidence was checked to be integration-marked.
  - **Evidence kinds:** DB-independent, PostgreSQL and the real container smoke are kept apart.
  - **Finding:** no criterion is unmet on this evidence. Four evidence limitations are left to the reviewer: activation "crash" shown by injected in-transaction failures; 413/415/422 verified only database-independently; cross-tenant chunk-ID disjointness shown on the pure function; container shutdown limited to an idle worker.
  - Overall M3 is **not** marked accepted.
- **Checks:** the staged-path, history, link, status-wording, private-content, `git diff --cached --check` and staged Gitleaks checks run after this entry is staged; results are in the session handoff. No application tests, builds, Docker or database contact.
- **Not done:** nothing committed, pushed or merged; M4 not started.

**Acceptance note (recorded in Prompt 105):**
- **Decision:** the external reviewer accepted overall M3 within its agreed scope.
- **Basis:**
  - the reviewed M3a–M3f implementations and corrections;
  - the criterion-to-evidence assessment;
  - the independently retrieved `main` CI evidence for `e2463cb`;
  - the passing real PostgreSQL suite and container smoke.
- **What the reviewer did:**
  - inspected the Prompt 104 diff (`.local/p104/m3-acceptance-assessment.diff`) and independently matched its checksum;
  - inspected selected supporting tests: chunk-ID disjointness, exact PostgreSQL storage, failed replacement, activation rollback and rejected uploads.

  The reviewer did not rerun the suite or Docker locally.
- **Accepted limitations.** The four documented evidence limitations are accepted as limitations, not removed or represented as additional tests:
  - rollback tested by injected in-transaction failures, without killing a process;
  - invalid-upload statuses tested database-independently;
  - tenant-specific chunk-ID disjointness tested directly, with separate PostgreSQL storage and constraint tests rather than a two-tenant ingestion scenario;
  - container shutdown tested with an idle worker only.
- **Compose:** CI Compose satisfies the agreed Compose verification requirement. Local Compose remains unverified.
- **No guarantees follow:** acceptance implies no production-readiness, performance or general security guarantee.

## Prompt 105: Record overall M3 acceptance and commit the reviewed documentation locally

- **Stage:** Acceptance wording and a local commit on branch `docs/m3-acceptance` (no push or merge)
- **Date:** 2026-10-16 (session date)
- **Numbering:** 105 is the next unused number after Prompt 104; verified before appending.

````text
Written for: Mathew and the external reviewer.

Prompt 105 — Record overall M3 acceptance and commit the reviewed documentation locally. Do not push or merge.

Read CLAUDE.md and relevant status sections only. Do not reload full prompt history or print diffs.

1. Verify starting state

Expected:
- Branch: docs/m3-acceptance.
- HEAD:
  e2463cb5a94d7c40eb1d894b8fded29a866165a8.
- Staged tree:
  a3ab3645a0f9e9cd9a594cd926a2fe309a1b9e57.
- Exactly five staged paths:
  README.md
  docs/decisions/0012-containers.md
  docs/plan.md
  docs/threat-model.md
  prompts.md
- Nothing unstaged or untracked.
- Local main and origin/main at HEAD.
- Expected origin and noreply author/committer identity unchanged.

Stop on a material mismatch. Record the accepted staged tree under .local/p105/.

2. Record the acceptance decision

The external reviewer accepts overall M3 within its agreed scope, based on:
- the reviewed M3a–M3f implementations and corrections;
- the criterion-to-evidence assessment;
- the independently retrieved main CI evidence for e2463cb;
- the passing real PostgreSQL suite and container smoke.

The reviewer inspected the Prompt 104 diff and independently matched its checksum. The reviewer also inspected selected supporting tests for chunk-ID disjointness, exact PostgreSQL storage, failed replacement, activation rollback and rejected uploads. The reviewer did not rerun the suite or Docker locally.

The four documented evidence limitations are accepted as limitations, not silently removed or represented as additional tests:
- rollback tested by injected in-transaction failures, without killing a process;
- invalid-upload statuses tested database-independently;
- tenant-specific chunk-ID disjointness tested directly, with separate PostgreSQL storage/constraint tests rather than a two-tenant ingestion scenario;
- container shutdown tested with an idle worker only.

CI Compose satisfies the agreed Compose verification requirement. Local Compose remains unverified. No production-readiness, performance or general security guarantee follows from acceptance.

3. Narrow documentation edits

Only the existing five staged files may change.

Update current overall-M3 status wording consistently:
- M1, M2 and M3 accepted;
- M3 implementation is on main at e2463cb;
- the acceptance record is being committed locally on this documentation branch;
- M4 implementation has not started.

In docs/plan.md:
- change the assessment heading from prepared for review to accepted at external review, Prompt 105;
- retain the criterion table, test names, evidence kinds, CI references and four limitations;
- replace the unresolved-review wording with the acceptance decision and rationale above;
- update current overall-M3-pending statements without rewriting historical baseline records.

Make corresponding narrow status changes in README, ADR-0012 and the threat model where needed.

Do not redesign or specify M4. Do not change source, tests, configurations, workflows, migrations, dependencies, lockfile or CLAUDE.md.

4. Prompt history

Append:
- acceptance note under Prompt 104 with the reviewer’s actual work, evidence and decision;
- Prompt 105 verbatim;
- a truthful pre-commit note.

Preserve earlier bytes. Do not include the new commit’s own SHA in its committed note. Do not pre-record publication.

5. Checks and local commit

Verify:
- exactly the five permitted paths staged;
- differences against the accepted tree are only the authorized acceptance wording and prompt history;
- earlier prompts.md content is an identical prefix;
- relative links and anchors;
- current versus historical status wording;
- private content and unintended artifacts;
- git diff --cached --check;
- staged Gitleaks without suppression;
- effective author and committer identity.

Commit with subject:
docs: record M3 acceptance and verified main baseline

Use the existing co-author trailer.

After committing:
- verify parent e2463cb5a94d7c40eb1d894b8fded29a866165a8;
- verify exactly five committed paths;
- run full-history Gitleaks;
- confirm working tree clean;
- confirm main and origin/main remain unchanged.

No application tests or builds are needed for these documentation-only edits. Do not run Docker or contact a database.

Stop on failed checks without suppressing findings or amending.

6. Review export and handoff

Export the complete incremental diff from accepted tree
a3ab3645a0f9e9cd9a594cd926a2fe309a1b9e57
to the new commit, excluding prompts.md, to:
.local/p105/m3-acceptance-commit-incremental.diff

Use UTF-8 without BOM. Report baseline/final, paths, statistics, byte size and SHA-256. Do not print the diff.

Report commit SHA, parent, identity, checks and final Git state.

No push, merge, force-push, amend, rebase, tag, branch deletion or M4 work is authorized.

Return this output plus .local/p105/m3-acceptance-commit-incremental.diff to the external reviewer.
````

**Pre-commit note (written before the commit; the commit's own SHA is not recorded here):**
- **Starting state verified:**
  - branch `docs/m3-acceptance`, HEAD `e2463cb`;
  - staged tree `a3ab3645a0f9e9cd9a594cd926a2fe309a1b9e57` with exactly the five expected paths; nothing unstaged or untracked;
  - local `main` and `origin/main` at HEAD; origin and the noreply identity as expected.

  The accepted tree is recorded under `.local/p105/`.
- **Changes since the accepted tree:** narrow acceptance wording only, plus this prompt history.
  - **`README.md`:** the status heading now reads M1, M2 and M3 accepted, with M3 on `main` at `e2463cb` and M4 not started; the M3 summary and the container-section qualifier are updated.
  - **`docs/plan.md`:** the assessment heading now reads accepted at external review (Prompt 105). The pending line became the acceptance decision and rationale. The criterion table, test names, evidence kinds, CI references and the four limitations are kept. The current "pending" statements are updated; historical baseline records are left as written.
  - **ADR-0012:** status and qualifier.
  - **`docs/threat-model.md`:** one sentence noting that acceptance changes no guarantee.
- **Unchanged:** source, tests, configuration, workflows, migrations, dependencies, `uv.lock` and `CLAUDE.md`. M4 is neither specified nor started.
- **Checks for this commit:** run after this entry is staged; results are in the session handoff. They are the staged-path, accepted-tree comparison, prompt-history prefix, link, status-wording, private-content, `git diff --cached --check`, staged Gitleaks and identity checks, and after the commit the full-history Gitleaks scan. No application tests, builds, Docker or database contact.
- **Not done:** nothing pushed or merged; publication of this branch is not authorized.

**Commit outcome (recorded in Prompt 106):**
- **Commit:** `162241d0547330620aba12bf7ed8f4ebbd6de646` ("docs: record M3 acceptance and verified main baseline"), parent `e2463cb`, tree `b9351d0b71fcaa2713c0c87901aa664e8ef4fed4`, on the local branch `docs/m3-acceptance`, with the noreply author and committer identity and the existing co-author trailer.
- **Content:** exactly five paths (`README.md`, ADR-0012, `docs/plan.md`, `docs/threat-model.md`, `prompts.md`), with only acceptance wording and prompt history changed against accepted tree `a3ab364`.
- **Checks reported in the Prompt 105 handoff:**
  - an identical earlier prompt-history prefix;
  - no broken links; no private-content matches;
  - a clean `git diff --cached --check`; staged Gitleaks with no leaks;
  - full-history Gitleaks after the commit: 43 commits scanned, no leaks found;
  - working tree clean; `main` and `origin/main` unchanged at `e2463cb`.
- **Diff:** `.local/p105/m3-acceptance-commit-incremental.diff`, 29,123 bytes, SHA-256 `a54646707357e0ea094ffa05af528c66d6e68a7ac16d29463a41035553ff8dfb`.
- Nothing was pushed or merged.

**Review note (recorded in Prompt 106):**
- **Accepted:** the external reviewer accepted the Prompt 105 incremental diff.
- **How it was reviewed:** the reviewer inspected it and independently matched its checksum, with no new local suite or Docker execution.

**Session-count correction (recorded in Prompt 106):** the Prompt 105 handoff said that this Claude session had run Prompts 77–105. That was inaccurate: this Claude session began at Prompt 98. The earlier history is left unchanged; this note corrects it. The session continues, and no restart is required on that count alone.

## Prompt 106: Publish the reviewed M3 acceptance record, then fast-forward main

- **Stage:** A prompt-history commit, publication of `docs/m3-acceptance`, and a fast-forward of `main` only after all five checks pass
- **Date:** 2026-10-16 (session date)
- **Numbering:** 106 is the next unused number after Prompt 105; verified before appending.

````text
Written for: Mathew and the external reviewer.

Prompt 106 — Publish the reviewed M3 acceptance record, then fast-forward main after all five checks pass. Do not start M4.

Read CLAUDE.md and relevant workflows. Avoid reloading full prompt history. Do not print diffs.

1. Verify starting state

Expected:
- Branch: docs/m3-acceptance.
- HEAD:
  162241d0547330620aba12bf7ed8f4ebbd6de646.
- Parent:
  e2463cb5a94d7c40eb1d894b8fded29a866165a8.
- Working tree clean.
- No upstream or remote docs/m3-acceptance branch.
- Local main, origin/main and remote main:
  e2463cb5a94d7c40eb1d894b8fded29a866165a8.
- Expected origin and noreply author/committer identity unchanged.

Fetch fresh refs and confirm main is an ancestor of HEAD, with no independent local main commits. Stop on material mismatch.

2. Preflight and history commit

Review what will become public relative to remote main. Confirm:
- only the reviewed acceptance documentation and prompt history;
- noreply identities;
- no unintended private content, credentials, artifacts, backups or real environment files;
- all five CI jobs remain enabled for this branch.

Modify prompts.md only, append-only:
- Record the Prompt 105 commit outcome and reported checks.
- Record the reviewer's acceptance of its incremental diff: inspected and checksum independently matched; no new local suite or Docker execution.
- Correct the session-count statement in a new note, without editing earlier history: this Claude session began at Prompt 98, so the statement that it handled Prompts 77–105 was inaccurate. Continue this session; no restart is required solely on that count.
- Append Prompt 106 verbatim.
- Add a preflight note recording verified state, scope, authorization order and stop conditions.

Do not pre-record publication or CI outcomes. Preserve the four reviewed documents byte-identical to HEAD.

Check history prefix, private content, git diff --cached --check, staged Gitleaks without suppression, and identity.

Commit prompts.md only with subject:
docs: record M3 acceptance publication authorization

Use the existing co-author trailer.

Verify parent 162241d, only prompts.md changed, and working tree clean. Run full-history Gitleaks before publication. Stop on a finding without suppression or amend.

No application tests, builds, local Docker or database contact are needed.

3. Publish only the documentation branch

Run directly, preserving Git's exit status:

git push --set-upstream origin refs/heads/docs/m3-acceptance:refs/heads/docs/m3-acceptance

Confirm the remote equals the exact new HEAD.

Monitor push-triggered workflows for that exact SHA and branch, up to 25 minutes:
- Ubuntu verify;
- Windows verify;
- PostgreSQL integration;
- container;
- full-history Gitleaks.

All five must succeed. Required container configuration, context, build, image, smoke and cleanup steps must execute successfully, not be skipped.

Use existing GitHub access or public read-only API; do not install tools or add credentials. Retrieve logs if accessible. Otherwise report summaries as unobserved, without reusing historical counts.

If any required job fails, is cancelled or remains pending at the limit, stop without changing main. Report evidence; do not fix files, rerun workflows or push again.

4. Fast-forward main only after five green jobs

Fetch fresh refs again and confirm:
- remote main remains e2463cb5a94d7c40eb1d894b8fded29a866165a8;
- remote documentation branch equals the verified commit;
- main is an ancestor of that commit;
- local main equals origin/main, with no independent commits;
- working tree clean.

Stop if any precondition fails.

Switch to main and run:
git merge --ff-only <exact verified commit>

Then push only:
git push origin refs/heads/main:refs/heads/main

Preserve Git's exit statuses. No force-push or merge commit.

Monitor all five jobs for the exact SHA's push to main, up to 25 minutes. Report failures and stop; do not roll back, fix, rerun or make further pushes.

5. Handoff

Report:
- history commit SHA, parent, identity and changed path;
- both push commands and exit statuses;
- exact published SHA;
- all five job conclusions and run/job links for each push;
- required container step conclusions;
- observed summaries separately from inaccessible counts;
- refs before/after and final working-tree status.

Leave documentation unchanged after publication. Existing e2463cb results remain evidence for that implementation baseline; do not relabel them as results for the new commit.

M1, M2 and M3 are accepted. M4 has not started. Local Compose remains unverified.

No force-push, amend, rebase, squash, tag, branch deletion, local Docker or database contact is authorized.

Return this output only to the external reviewer; no diff attachment is required.
````

**Preflight note (written before the commit; no push, CI or `main` result is recorded here):**
- **Starting state verified:**
  - branch `docs/m3-acceptance` at `162241d` (parent `e2463cb`), working tree clean, no upstream;
  - fresh refs: no remote `docs/m3-acceptance`; local `main`, `origin/main` and remote `main` at `e2463cb`, an ancestor of HEAD, with no independent local commits;
  - origin and the noreply identity as expected.
- **Publication scope:** relative to remote `main`, the reviewed acceptance commit `162241d` (only `README.md`, ADR-0012, `docs/plan.md`, `docs/threat-model.md` and `prompts.md`) and this history commit (only `prompts.md`).
  - All commits use the noreply identity.
  - No binaries, artifacts, backups or environment files are in the range, and no private-content matches.
  - Gitleaks over `origin/main..HEAD` before this entry: 1 commit scanned, no leaks found.
- **Workflows:** both trigger on every push, without branch filters. Ubuntu and Windows `verify`, PostgreSQL integration (`EG_REQUIRE_INTEGRATION=1`), `container` and full-history Gitleaks (`fetch-depth: 0`) remain enabled.
- **Authorized order:**
  1. commit `prompts.md` only;
  2. run full-history Gitleaks;
  3. push `docs/m3-acceptance` only;
  4. require all five jobs to succeed for that exact commit, with the container configuration, context, build, image, smoke and cleanup steps executed successfully;
  5. re-verify fresh refs, fast-forward `main` with `--ff-only` to that exact commit, and push only `main`;
  6. monitor the five jobs again.
- **Stop conditions:**
  - any scan finding;
  - any required job failing, cancelled, skipped in a required container step, or pending after 25 minutes;
  - any failed fast-forward precondition.

  On any stop: no fixes, reruns, rollbacks or further pushes.
- **Status:** the `e2463cb` CI results remain evidence for that implementation baseline only. M1, M2 and M3 are accepted; M4 has not started; local Compose remains unverified.


**Prompt 106 outcome (recorded in Prompt 107):** publication completed at
`85cb0d622a5b49c11439b0b9f67abceaa82edb29`, parent
`162241d0547330620aba12bf7ed8f4ebbd6de646`. The commit changes only
`prompts.md` and uses the expected noreply author/committer, with the existing
co-author trailer. The documentation branch and main now point to that commit.
Codex independently verified local main, origin/main, local docs/m3-acceptance,
fresh remote main and remote docs/m3-acceptance at that SHA in Prompt 107.
The prior publication command exit statuses and branch-push run IDs were not
supplied to Codex; they are not reconstructed here.

**Reviewer evidence supplied for Prompt 107:** the external reviewer independently
retrieved both main workflow records and all five job logs for this exact SHA.
Both runs were successful push events on main. The detailed counts, container
observations and links are recorded under the final M3 publication baseline in
`docs/plan.md`. The reviewer did not execute the suite or Docker locally.
Claude previously observed run/job conclusions but could not retrieve logs
anonymously. Codex records this supplied evidence; it did not retrieve those logs
or rerun those checks. Earlier `e2463cb` evidence remains attributed to that SHA.

## Prompt 107: Codex handover and proposed M4 breakdown

- **Date:** 2026-10-16 (Asia/Bangkok).
- **Status:** documentation only; proposed specification, pending external review.
- **Session:** first substantial prompt in this Codex session.

````text
Written for: Mathew and the external reviewer.

Prompt 107 — Codex handover and proposed M4 breakdown. Documentation only; no implementation or publication.

You are taking over implementation assistance from Claude Code in the existing EvidenceGuard repository. ChatGPT acts as the external reviewer. Mathew transfers your output and exported diff to that reviewer.

Read any applicable AGENTS.md instructions. Also read CLAUDE.md explicitly as the existing project working agreement, preserving its relevant repository conventions even though you are Codex. Read the relevant README, plan, architecture decisions and source sections.

Do not read the entire prompts.md history. Read only its tail as needed to establish the next prompt number and recent state. Do not print full diffs in chat.

1. Verify the handover state before changing anything

Expected:
- Repository: evidenceguard-agentic-rag.
- Origin:
  https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git
- Current branch: main.
- HEAD, origin/main and remote main:
  85cb0d622a5b49c11439b0b9f67abceaa82edb29.
- Parent:
  162241d0547330620aba12bf7ed8f4ebbd6de646.
- Working tree clean.
- docs/m3-acceptance exists locally and remotely at the same HEAD.
- Repository identity:
  mathewmljourney93 <257921624+mathewmljourney93@users.noreply.github.com>.

Read fresh remote refs without modifying them. Stop on a material mismatch.

Create docs/m4-retrieval-spec from HEAD if that branch does not already exist. Do not overwrite an existing branch.

2. Established project state

M1, M2 and M3 are accepted.

Implemented and verified:
- Python 3.12, uv, locked dependencies, installable package, strict typing, lint and cross-platform CI.
- Tenant-scoped PostgreSQL persistence, API-key authentication, vendor endpoints and readiness.
- Durable jobs, leases, heartbeats, retries and fenced writes.
- Sequential worker runtime and safe lease cancellation.
- Document revisions, transactional activation and supersession.
- Deterministic plain-text/Markdown parsing and chunk storage.
- Bounded document uploads and tenant-scoped document, revision, chunk and job views.
- Development container stack and real CI Compose smoke.

No retrieval, model-driven review workflow, completed risk reports or evaluation results exist yet. Existing evidence and approval domain contracts are foundations, not completed product workflows.

Accepted M3 limitations remain:
- activation rollback tested through injected transaction failures, not process termination;
- invalid uploads tested database-independently;
- tenant-specific chunk IDs tested directly, with separate database storage/constraint checks;
- container shutdown smoke tests an idle worker only.
Local Compose remains unverified. No production-readiness or general security claim is made.

3. Record the final M3 publication evidence

The external reviewer independently retrieved both main workflow records and all five job logs for exact commit `85cb0d622a5b49c11439b0b9f67abceaa82edb29`.

Both runs were push events on main with conclusion success.

CI run:
https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38776947803

Observed:
- Ubuntu job 116566948053:
  1364 passed, 204 skipped in 27.18s.
- Windows job 116566948118:
  1363 passed, 205 skipped in 38.85s.
- PostgreSQL job 116566948087:
  204 passed, 1364 deselected in 58.35s.
- Container job 116566947772:
  configuration passed;
  effective context contained 72 files and excluded all 19 planted fixtures;
  image checks passed;
  stack started successfully;
  application services used the CI-built image;
  upload returned 202;
  ingestion succeeded;
  revision became active with two verified chunks;
  duplicate upload returned 200;
  idle worker exited with code 0 and no OOM kill;
  smoke and cleanup passed.

Secret-scan run:
https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38776947848
Job 116566948188:
44 commits scanned, no leaks found.

The reviewer did not execute the project suite or Docker locally. Claude previously observed run/job conclusions but could not retrieve logs anonymously. Preserve that distinction and the earlier e2463cb evidence.

4. Propose the M4 sequence and first-slice specification

Inspect the existing plan's embeddings, retrieval, snapshot, provider, corpus and evaluation requirements before proposing changes.

M4 currently includes:
- provider interface;
- HashingEmbedder;
- Voyage adapter, mocked in CI;
- RRF retrieval over snapshot revisions;
- synthetic sample_data, including an injected variant;
- ground truth and retrieval contract tests.

Acceptance includes tenant/snapshot isolation, exclusion of ineligible chunks and correct Recall@k calculation.

Propose a small, dependency-ordered slice sequence, comparable to M3's reviewed slices. Fully specify only the first implementation slice; keep later slices concise.

Resolve or explicitly flag:
- embedding identity, version, dimension and validation;
- deterministic offline provider versus live provider behaviour;
- persistence and migration requirements, including when pgvector is actually needed;
- tenant and revision constraints;
- indexing jobs and how they use existing leases/fences;
- how indexing relates to immutable completed chunk sets;
- retrieval eligibility and snapshot inputs before M5 introduces review orchestration;
- the meaning of “no superseded chunks” versus preserving a review's snapshot after later revision activation;
- deterministic ranking, tie-breaking, bounded inputs and result sizes;
- what the synthetic corpus proves, without pretending hashing measures semantic quality;
- Recall@k's relevance unit, denominator and treatment of empty relevance sets;
- database-independent versus real PostgreSQL verification.

Preserve accepted architecture and existing invariants. Do not add a framework or expand the product scope.

Clearly distinguish existing decisions from proposed defaults and questions needing reviewer judgement. Include intended files and meaningful acceptance tests for the first slice.

Do not install dependencies, create migrations, implement code, make provider calls, require keys, run Docker or contact a database. If dependency research is necessary, use official sources and record proposals only.

5. Authorized changes

Modify only:
- README.md
- docs/plan.md
- prompts.md

README: concise final M3 publication reference and M4 planning status.
Plan: final M3 baseline reference, proposed M4 sequence and detailed first-slice specification.
Prompt history: append the Prompt 106 outcome, reviewer evidence, this prompt verbatim and a truthful outcome note.

Keep M4 proposed and unimplemented. Do not mark its specification accepted.

Do not rewrite earlier prompt history. Do not alter CLAUDE.md, create AGENTS.md, change co-author conventions or make a commit in this task.

6. Verification and review export

Stage exactly those three files.

Check:
- earlier prompts.md content is an identical prefix;
- relative links and anchors;
- status consistency;
- private content and unintended artifacts;
- git diff --cached --check;
- staged Gitleaks without suppression.

No application suite or build is necessary for documentation-only work.

Export the complete staged diff against HEAD, excluding prompts.md, to:
.local/p107/m4-retrieval-spec.diff

Use UTF-8 without BOM. Report baseline commit, final staged tree, paths, statistics, byte size and SHA-256. Do not print the diff.

Keep the handoff concise: proposed sequence, first-slice scope, decisions needed, checks, Git state and diff metadata.

No commit, push, merge, amend, rebase, tag, branch deletion, implementation, Docker or database contact is authorized.

Session preference:
Do not recommend a new session after one or two tasks. Continue through implementation and correction work. Around 20 substantial prompts, or if context problems actually arise, recommend a handover at a suitable checkpoint. Count this Codex session from this prompt.

Return this output plus .local/p107/m4-retrieval-spec.diff to the external reviewer.
````

**Prompt 107 outcome:** documentation prepared on `docs/m4-retrieval-spec` from
verified baseline `85cb0d622a5b49c11439b0b9f67abceaa82edb29`. Fresh remote refs
were read with `git ls-remote` without fetching or changing remote-tracking refs;
main and docs/m3-acceptance matched locally and remotely. Expected origin,
parent, identity and clean starting tree were verified. The branch did not
previously exist and was created without overwriting any branch.

Only README.md, docs/plan.md and this append-only history changed. The plan
records final M3 publication evidence supplied by the reviewer, preserves earlier
e2463cb evidence and accepted limitations, and proposes M4a through M4f. Only
M4a has a detailed implementation specification: immutable embedding contracts,
validation, versioned deterministic hashing, intended files and acceptance tests.
Indexing/readiness, snapshot-relative supersession, bounds and Recall semantics
are explicit proposals/questions. M4 is unimplemented and not accepted.

Checks already run before this note: exact earlier-history byte prefix and
verbatim request, README/plan relative file links and anchors, current status
consistency, added-text private-path/key/token checks, and git diff --check.
Final staging, git diff --cached --check, staged Gitleaks without suppression,
post-note prefix/link/status/scope checks and export validation follow this note;
their actual outcomes and final staged tree are reported in the session handoff.
No application suite/build, dependency installation, migration, live provider,
Docker or database operation ran. No commit or publication was made. Scratch
and export files are confined to ignored .local/p107/. This is Codex session
prompt 1; no new-session recommendation is needed.

Review export: complete staged diff against HEAD, excluding prompts.md, written
directly from Git as UTF-8 without BOM to .local/p107/m4-retrieval-spec.diff.
Mathew returns output plus that diff file to the external reviewer.


**Prompt 107 acceptance (external review, Prompt 108):** the reviewer inspected
the full Prompt 107 diff and independently matched its SHA-256 checksum. The
reviewer also checked the existing chunk domain and chunker source, confirming
that the 4,000-code-point input bound covers the existing maximum chunk length.
The reviewer ran no project tests or documentation checks.

Accepted: the dependency-ordered M4a–M4f sequence; complete M4a contracts/hashing
specification, including identity/fingerprint, strict validation, input/batch
bounds, deterministic ASCII hashing and offline zero-vector policy; separate
indexing readiness preserving M3 activation; refusal of snapshot capture when
any active revision is unready; snapshot-relative supersession; ranking/input/
result bounds as initial engineering defaults; chunk-based Recall denominator,
empty-gold N/A treatment and separate variant/profile reporting. No benchmark
or semantic-quality claim follows. M4 implementation is pending. M4b–M4f still
require detailed specification reviews; exact schemas, migration, lock ordering,
provider transport and operational limits are not approved by this sequence.

## Prompt 108: Record accepted M4 sequence and embedding contracts specification

- **Date:** 2026-10-16 (Asia/Bangkok).
- **Scope:** acceptance documentation and local commit only.

````text
Written for: Mathew and the external reviewer.

Prompt 108 — Record acceptance of the M4 sequence and M4a specification, then commit the documentation locally. No implementation or publication.

Read applicable AGENTS.md instructions and the relevant CLAUDE.md working agreement. Avoid reloading full prompt history or printing diffs.

1. Verify starting state

Expected:
- Branch: docs/m4-retrieval-spec.
- HEAD:
  85cb0d622a5b49c11439b0b9f67abceaa82edb29.
- Staged tree:
  24eec1b6543cd22ce8e490fced91aeb791d6f9df.
- Exactly README.md, docs/plan.md and prompts.md staged.
- Nothing unstaged or untracked.
- Local main and origin/main at HEAD.
- Expected origin and noreply identity unchanged.

Stop on a material mismatch. Record the accepted staged tree under .local/p108/.

2. Acceptance decision

The external reviewer inspected the full Prompt 107 diff and independently matched its SHA-256 checksum.

The reviewer also checked the existing chunk domain and chunker source, confirming that the proposed 4,000-code-point per-input bound covers the existing maximum chunk length. No project tests or documentation checks were run by the reviewer.

Accepted:
- the dependency-ordered M4a–M4f sequence;
- the complete M4a contracts/hashing specification;
- M4a identity, fingerprint, strict validation, input/batch bounds, deterministic ASCII hashing and explicit offline zero-vector policy;
- separate indexing readiness without changing M3 activation semantics;
- refusing snapshot capture when any active revision lacks a ready index;
- snapshot-relative supersession, preserving revisions active at capture after later supersession;
- proposed ranking/input/result bounds as initial engineering defaults;
- chunk-based Recall denominator, empty-gold N/A handling and separate variant/profile reporting.

These decisions make no benchmark or semantic-quality claim. M4b–M4f still require their own detailed specification reviews before implementation. Exact schemas, migration, lock ordering, provider transport and operational limits are not approved merely by approving the sequence.

3. Narrow documentation edits

Only these three files may change:
- README.md
- docs/plan.md
- prompts.md

In README and plan:
- record the M4 sequence and M4a specification as accepted at external review, Prompt 108;
- keep all M4 implementation pending;
- convert the explicitly approved recommendations/open-decision entries consistently to accepted decisions;
- retain the detailed contracts, algorithm, bounds, tests and limitations without redesign;
- preserve the final M3 evidence and historical attribution;
- retain the requirement for detailed later-slice reviews.

Do not claim embeddings, retrieval, live adapters, corpus evaluation or M5 functionality exists.

Do not change source, tests, dependencies, lockfile, configuration, migrations, workflows, CLAUDE.md or AGENTS.md.

4. Prompt history

Append:
- acceptance note under Prompt 107, recording the actual reviewer work and decisions above;
- Prompt 108 verbatim;
- a truthful pre-commit note.

Preserve all earlier bytes. Do not include the new commit's own SHA in its committed note or pre-record publication.

5. Checks and local commit

Verify:
- exactly the three permitted paths staged;
- changes against the accepted staged tree are only acceptance wording and prompt history;
- earlier prompts.md content remains an identical prefix;
- relative links and anchors;
- consistent accepted-specification versus unimplemented status;
- private content and unintended artifacts;
- git diff --cached --check;
- staged Gitleaks without suppression;
- effective author and committer identity.

Commit with subject:
docs: record accepted M4 sequence and embedding contracts specification

Follow the repository's applicable commit-attribution conventions accurately. Do not attribute new Codex work to Claude.

After committing:
- verify parent 85cb0d622a5b49c11439b0b9f67abceaa82edb29;
- verify exactly the three committed paths;
- run full-history Gitleaks;
- confirm working tree clean;
- confirm main and origin/main unchanged.

No application tests or builds are needed for documentation-only changes. Do not install dependencies, call providers, run Docker or contact a database.

Stop on failed checks without suppression, amend or reset.

6. Review export and handoff

Export the complete incremental diff from accepted tree
24eec1b6543cd22ce8e490fced91aeb791d6f9df
to the new commit, excluding prompts.md, to:
.local/p108/m4-spec-acceptance.diff

Use UTF-8 without BOM. Report baseline/final, paths, statistics, byte size and SHA-256. Do not print the diff.

Report commit SHA, parent, attribution, checks and final Git state.

No push, merge, force-push, amend, rebase, tag, branch deletion or implementation is authorized.

Return this output plus .local/p108/m4-spec-acceptance.diff to the external reviewer.
````

**Prompt 108 pre-commit note (no commit or publication result recorded here):**
- Recovery found Prompt 108 unfinished: original HEAD and accepted staged tree
  unchanged, no Prompt 108 entry or acceptance note, no unstaged/untracked files.
  The automatic approval review had failed because of a usage limit before the
  requested tree-recording action executed. No rollback was assumed.
- Verified branch docs/m4-retrieval-spec; HEAD, main and origin/main at
  85cb0d622a5b49c11439b0b9f67abceaa82edb29; expected origin and effective noreply
  author/committer identity. Accepted pre-edit tree
  24eec1b6543cd22ce8e490fced91aeb791d6f9df is recorded under .local/p108/.
- Only README.md, docs/plan.md and prompts.md are authorized. Relative to the
  accepted tree, README/plan edits record acceptance without changing contract,
  hashing, validation, bounds, tests, M3 evidence or historical attribution.
  Later-slice detailed designs remain subject to review; all implementation pending.
- This history appends one acceptance note and Prompt 108 verbatim, preserving
  the complete earlier byte prefix. Recovery is part of Prompt 108, not a new prompt.
- Pre-commit checks follow this note: staged scope, acceptance-only comparison,
  prefix/links/anchors/status/private-content/artifact checks, cached whitespace
  check, staged Gitleaks without suppression and effective identity checks.
  Actual results will be reported in the handoff; no results are pre-recorded.
- Authorized local commit subject: docs: record accepted M4 sequence and embedding contracts specification.
  Use the configured noreply author and committer; identify Codex assistance in
  the commit body. Do not copy Claude's co-author trailer from older commits.
  No applicable instruction specifies a Codex co-author email.
- After the commit, verify parent and paths, clean working tree, unchanged main
  and origin/main, and full-history Gitleaks. Stop on failure without amend/reset.
  Export the complete incremental diff from the accepted tree, excluding prompts.md,
  to .local/p108/m4-spec-acceptance.diff as UTF-8 without BOM.
- No implementation, application tests/builds, dependency installation, provider
  calls, Docker, database contact, push or merge is authorized or claimed.


**Prompt 108 outcome (recorded in Prompt 109):** committed locally as
ac395039fa43ef19c8e316d253af639f0e35fe0f, parent
85cb0d622a5b49c11439b0b9f67abceaa82edb29, tree
66ffb2f5ac466f857b70faf6dd4972f73deb5e91. Exactly README.md, docs/plan.md and
prompts.md changed. Expected noreply author/committer; commit body identifies
OpenAI Codex assistance without a Claude trailer. Prior handoff reported all
requested documentation checks and staged Gitleaks passed; full-history Gitleaks
scanned 45 commits with no leaks. Working tree was clean; main/origin/main unchanged.
Incremental export .local/p108/m4-spec-acceptance.diff: 15,867 bytes, SHA-256
a0bf652e0ded2d66ec192dc66b7920c3255a61ec6281c66bf34f9f401e1c9070.

**Reviewer acceptance of Prompt 108:** incremental diff accepted, checksum
independently matched; no new project checks. This records the supplied review
decision, not a new execution of project checks by Codex.

## Prompt 109: Implement accepted M4a embedding contracts and offline provider

- **Date:** 2026-10-16 (Asia/Bangkok).
- **Scope:** M4a only; stage for external review, no commit or publication.

````text
Written for: Mathew and the external reviewer.

Prompt 109 — Implement the accepted M4a embedding contracts and deterministic offline provider. Stage for external review; do not commit or publish.

Read applicable AGENTS.md instructions, CLAUDE.md and the accepted M4a specification in docs/plan.md. Read existing domain validation and retrieval import-boundary conventions. Avoid reloading the full prompt history.

1. Verify starting state

Expected:
- Branch: docs/m4-retrieval-spec.
- HEAD:
  ac395039fa43ef19c8e316d253af639f0e35fe0f.
- Parent:
  85cb0d622a5b49c11439b0b9f67abceaa82edb29.
- Working tree clean.
- Local main and origin/main:
  85cb0d622a5b49c11439b0b9f67abceaa82edb29.
- Expected origin and noreply identity unchanged.

Stop on a material mismatch. Record the baseline under .local/p109/.

Create feat/embedding-contracts from HEAD if it does not exist. Do not overwrite an existing branch. The accepted specification commit may remain local beneath this implementation branch; no separate publication is needed now.

2. Implement only M4a

Follow the accepted specification exactly:
- frozen embedding identity, usage and batch values;
- canonical identity fingerprint;
- strict request validation;
- provider protocol with immutable identity;
- deterministic HashingEmbedder;
- caller-boundary validation of provider results;
- fixed, privacy-safe errors and representations.

Use these intended files:
- packages/domain/evidenceguard_domain/embeddings.py
- packages/retrieval/evidenceguard_retrieval/embeddings.py
- tests/test_embeddings.py
- docs/decisions/0013-embeddings.md, if that number is available
- README.md
- docs/plan.md
- prompts.md

If an additional file change is necessary, explain why and keep it minimal. Do not add dependencies or change uv.lock.

Preserve import direction: shared values in domain; provider protocol and offline implementation in retrieval. Keep existing import-boundary tests.

Implement the specified tuple-only inputs, limits, exact text preservation, UTF-8 validation, identity fields, hashing features, bucket/sign calculation, normalization and zero-vector policy. Do not silently truncate, normalize Unicode, change tokenization or substitute Python hash().

Hashing outputs must remain clearly labelled as a lexical-hash baseline, not semantic embeddings.

Treat malformed provider output as untrusted at the caller boundary:
- requested identity, mode and count must match;
- dimensions, coordinate types, finite values, norm, zero policy and usage must be checked;
- reject booleans and coercions;
- avoid leaking input, vectors or raw exception text.
Handle extreme numeric inputs safely without exposing raw conversion errors.

Do not introduce persistence, SQL, pgvector, indexing jobs, worker registration, settings, environment reads, network calls, SDKs, model downloads, corpus loading or retrieval ranking.

If an accepted requirement cannot be implemented as written, stop and explain the concrete issue rather than silently redesigning it.

3. Meaningful tests

Cover the accepted M4a checks, including:
- literal pinned fingerprint and independently calculated bucket/sign fixtures;
- unigram/bigram features, repetition, collisions and cancellation;
- normalization, ordering, case/punctuation and non-ASCII-only zero vectors;
- duplicate positions and batch versus individual equivalence;
- query/document equivalence while preserving the requested mode;
- independent processes with different PYTHONHASHSEED values;
- every request bound at and beyond its boundary;
- supplementary Unicode, lone surrogates, NUL and blank inputs;
- mutable collections, booleans, coercions and unknown fields;
- frozen values and supported copy/revalidation paths;
- malformed fake-provider outputs and privacy-safe errors/repr;
- offline operation and import boundaries.

Do not derive expected golden outputs using the implementation under test. Use the specified tolerance for floating comparisons.

Tests may control PYTHONHASHSEED in child processes; production embedding code must not read environment variables.

4. Documentation and prompt history

ADR-0013 should explain the implemented contracts, fingerprint, exact hashing algorithm, validation boundaries and limitations.

README and plan must distinguish:
- accepted specification;
- implementation staged and awaiting review;
- checks actually run locally;
- Linux/current-version CI pending.

M4a adds no retrieval or semantic-quality evidence. M4b–M4f remain unimplemented and require detailed reviews.

Append:
- Prompt 108 outcome;
- reviewer acceptance of its incremental diff, with independently matched checksum and no new project checks;
- Prompt 109 verbatim;
- truthful outcome note.

Preserve all earlier prompt-history bytes. Do not attribute Codex work to Claude.

5. Verification

Run appropriate checks:
- focused embedding tests;
- Ruff format and lint;
- strict mypy;
- full existing suite using the repository's locked commands;
- build and a clean installed-wheel smoke check for the new modules and offline provider;
- git diff --cached --check;
- staged Gitleaks without suppression;
- private-content/artifact check.

Do not weaken existing tests or integration guards. PostgreSQL tests may skip when no test database is configured; report exact skip reasons/counts rather than claiming they ran.

No local Docker, database contact, provider calls or dependency installation is authorized. Use the existing locked environment; report a missing prerequisite rather than changing dependencies.

6. Stage and export for review

Stage only the intended implementation, tests, documentation and prompt history. Do not stage .local/, dist/ or build artifacts.

Export the complete staged diff against HEAD, excluding prompts.md, to:
.local/p109/m4a-implementation.diff

UTF-8 without BOM. Report baseline commit, final staged tree, paths, statistics, byte size and SHA-256. Do not print the diff in chat.

Handoff:
- what was built;
- deviations or unresolved questions;
- actual commands/results and remaining verification;
- Git state;
- diff metadata.

Do not commit, push, merge, amend, rebase, tag, delete branches or begin M4b.

Return this output plus .local/p109/m4a-implementation.diff to the external reviewer.
````

**Prompt 109 outcome:** M4a implemented on feat/embedding-contracts, based on
ac395039fa43ef19c8e316d253af639f0e35fe0f (parent 85cb0d6), with main and
origin/main unchanged at 85cb0d622a5b49c11439b0b9f67abceaa82edb29. Starting
branch, clean tree, parent, origin and effective noreply identities matched.
Baseline and original prompt-history bytes are saved under .local/p109/.

Only the seven intended paths changed: two embeddings modules, tests/test_embeddings.py,
ADR-0013, README.md, docs/plan.md and prompts.md. Frozen dataclasses follow the
existing chunk contract pattern, with dataclasses.replace as supported revalidating
copy. The protocol/HashingEmbedder remain domain/stdlib-only. Caller-boundary
validation reconstructs provider values and checks the captured identity, mode,
count, shapes, finite/unit/zero rules and usage. Fixed errors and repr omit content;
huge integer conversions and raw provider failures cannot expose raw errors.
Algorithm, bounds, exact input text and zero policy follow the accepted specification.
No specification deviation or unresolved implementation-design question was found.

Final local checks: Ruff format (125 files), lint, strict mypy (107 source files),
focused embedding+packaging tests (126 passed in 1.30s), and full locked suite
(1479 passed, 205 skipped in 38.74s). Exact skips: 204 because EG_TEST_DATABASE_URL
is not set and a disposable PostgreSQL test database is required (see README);
one because raise_signal(SIGTERM) ends a Windows process. No PostgreSQL tests ran.
The final checks use uv run --locked --offline --no-sync. Earlier lint/type and
test-harness failures were corrected, without weakening existing checks.

Build attempted with uv build --offline --no-build-isolation --out-dir .local/p109/dist;
failed because the existing environment lacks hatchling. No dependency installation
was authorized or performed. No new wheel exists, so the clean installed-wheel
smoke remains unperformed. Linux/current-version CI, implementation acceptance,
build and wheel verification remain pending. M4b–M4f are unimplemented and need
detailed review. No retrieval, semantic-quality or production-readiness evidence.

Final stage/export checks follow this outcome note: exact seven-path scope,
identical earlier prompt-history prefix and verbatim Prompt 109, relative links/
anchors, status/private-content/artifact review, cached whitespace and staged
Gitleaks without suppression. Results, staged tree and export metadata are reported
in the handoff. Complete staged diff against HEAD, excluding prompts.md, goes to
.local/p109/m4a-implementation.diff as UTF-8 without BOM. No commit, push, merge,
dependency installation, Docker, database contact, provider call or M4b work.
Codex performed this work; no Claude attribution is added.


**Prompt 109 acceptance (external review, Prompt 110):** the reviewer inspected
the complete implementation diff and independently matched its SHA-256 checksum.
Independent standard-library probes passed for canonical fingerprint, SHA-256
feature buckets/signs and golden vector, collision handling, non-ASCII zero
output, input rejection, private provider errors and extreme numerics. The
reviewer did not rerun the pytest suite because pytest was unavailable in its
review environment. Acceptance also relies on the reported Windows checks:
1479 passed, 205 skipped (204 PostgreSQL skips and one POSIX-only signal skip),
with 126 focused embedding/packaging checks passed. M4a is accepted for a local
commit; build, clean installed-wheel and Linux/current-version CI verification
remain pending. Local build is blocked by missing hatchling under offline/no-install
constraints. M4b–M4f and overall M4 acceptance remain pending. This note records
the supplied reviewer evidence, not fresh execution of those probes by Codex.

## Prompt 110: Commit reviewed M4a implementation locally

- **Date:** 2026-10-16 (Asia/Bangkok).
- **Scope:** local commit only; no push or merge.

````text
Written for: Mathew and the external reviewer.

Prompt 110 — Commit the reviewed M4a implementation locally. No push or merge.

Read applicable AGENTS.md instructions and CLAUDE.md. Avoid reloading full prompt history or printing diffs.

1. Verify starting state

Expected:
- Branch: feat/embedding-contracts.
- HEAD:
  ac395039fa43ef19c8e316d253af639f0e35fe0f.
- Staged tree:
  6edf253f38d929fb3ace8b16bfa9249275d813c6.
- Exactly seven staged paths:
  README.md
  docs/plan.md
  docs/decisions/0013-embeddings.md
  packages/domain/evidenceguard_domain/embeddings.py
  packages/retrieval/evidenceguard_retrieval/embeddings.py
  tests/test_embeddings.py
  prompts.md
- Nothing unstaged or untracked.
- Local main and origin/main:
  85cb0d622a5b49c11439b0b9f67abceaa82edb29.
- Expected origin and noreply identity unchanged.

Stop on material mismatch. Record the accepted staged tree under .local/p110/.

2. Preserve implementation

The external reviewer accepts Prompt 109 for a local commit.

Keep both embedding modules and tests/test_embeddings.py byte-identical to accepted tree 6edf253f38d929fb3ace8b16bfa9249275d813c6.

Only README.md, docs/plan.md, ADR-0013 and prompts.md may change relative to that tree.

Make narrow status changes:
- M4a implementation accepted at external review for a local commit;
- historical Windows results: 1479 passed, 205 skipped, comprising 204 PostgreSQL skips and one POSIX-only signal skip;
- focused embedding/packaging checks: 126 passed;
- Linux/current-version CI pending;
- local build blocked by missing hatchling under the offline/no-install constraints;
- build and clean installed-wheel verification remain pending;
- no persistence, indexing, retrieval or live provider functionality added;
- M4b–M4f and overall M4 acceptance remain pending.

ADR-0013 may become Accepted, explicitly scoped to this reviewed implementation with the verification limits above.

Do not change dependencies or install hatchling in this task. Do not redesign the contracts or hashing algorithm.

3. Prompt history

Append an acceptance note under Prompt 109:
- reviewer inspected the complete diff and independently matched its checksum;
- independent standard-library probes passed for canonical fingerprint, SHA-256 feature buckets/signs and golden vector, collision handling, non-ASCII zero output, input rejection, private provider errors and extreme numerics;
- reviewer did not rerun the pytest suite because pytest was unavailable in its review environment;
- acceptance also relies on the reported Windows checks;
- build, installed-wheel and current-version CI verification remain pending.

Append Prompt 110 verbatim and a truthful pre-commit note. Preserve earlier bytes. Do not include the new commit's own SHA or pre-record publication.

4. Checks and local commit

Verify:
- exactly seven staged paths;
- implementation and tests byte-identical to the accepted tree;
- earlier prompts.md content remains an identical prefix;
- links and anchors;
- truthful status/verification wording;
- private content and unintended artifacts;
- git diff --cached --check;
- staged Gitleaks without suppression;
- noreply author and committer identity.

Commit with subject:
feat: add validated embedding contracts and deterministic hashing

Use accurate Codex attribution under the applicable repository conventions. Do not attribute new work to Claude.

After committing:
- verify parent ac395039fa43ef19c8e316d253af639f0e35fe0f;
- verify the seven committed paths;
- verify both modules and the embedding tests still match the accepted tree;
- run full-history Gitleaks;
- confirm clean working tree;
- confirm main and origin/main unchanged.

No application tests or builds need repeating because implementation is unchanged. Stop on failed checks without suppression, amend or reset.

5. Review export

Export the complete incremental diff from accepted tree
6edf253f38d929fb3ace8b16bfa9249275d813c6
to the new commit, excluding prompts.md, to:
.local/p110/m4a-commit-incremental.diff

UTF-8 without BOM. Report baseline/final, paths, statistics, byte size and SHA-256. Do not print the diff.

Report commit SHA, parent, attribution, checks and final Git state.

No push, merge, force-push, amend, rebase, tag, branch deletion, dependency installation, Docker, database contact, provider calls or M4b work is authorized.

Return this output plus .local/p110/m4a-commit-incremental.diff to the external reviewer.
````

**Prompt 110 pre-commit note (no new commit SHA or publication result recorded):**
- Starting branch feat/embedding-contracts, HEAD
  ac395039fa43ef19c8e316d253af639f0e35fe0f, staged tree
  6edf253f38d929fb3ace8b16bfa9249275d813c6 verified; exactly the seven intended
  paths staged, nothing unstaged/untracked. main and origin/main remained at
  85cb0d622a5b49c11439b0b9f67abceaa82edb29, expected origin and noreply effective
  author/committer identity. Accepted staged tree saved under .local/p110/.
- Only README.md, docs/plan.md, ADR-0013 and appended prompt history change
  relative to that tree. Both embedding modules and tests/test_embeddings.py
  remain byte-identical. Status records reviewed implementation acceptance for
  a local commit, historical Windows evidence, blocked local build and pending
  build/wheel/Linux CI verification. No later-slice or overall M4 acceptance.
- Pre-commit checks follow this note: exact scope, implementation/test bytes,
  earlier-history identical prefix and verbatim prompt, links/anchors, truthful
  status, private content/artifacts, cached whitespace, staged Gitleaks without
  suppression and effective noreply identities. Actual outcomes go in the handoff.
- Authorized subject: feat: add validated embedding contracts and deterministic hashing.
  Use configured noreply author/committer and identify OpenAI Codex assistance
  in the commit body; do not copy older Claude attribution.
- After the local commit, verify parent, seven paths, byte-identical implementation/
  tests, clean working tree and unchanged main/origin/main, then full-history
  Gitleaks. Stop on failed checks without suppression, amend or reset.
- No application test/build repetition, dependency installation, Docker, database
  contact, provider calls, M4b work or publication. Build remains blocked by absent
  hatchling under the offline/no-install constraints; no build or clean-wheel result
  is claimed. M4b–M4f and overall M4 acceptance remain pending.
- Export complete incremental diff from accepted tree to the new commit, excluding
  prompts.md, as UTF-8 without BOM: .local/p110/m4a-commit-incremental.diff.


**Prompt 110 outcome (recorded in Prompt 111):** local commit
82e8e3111ee6bac87eab381c7a99bf8f6e2c7484, parent
ac395039fa43ef19c8e316d253af639f0e35fe0f, tree
cb8207911a2fe545d256dd81ebcb7de480efd563. Exactly seven intended paths changed;
both embedding modules and tests/test_embeddings.py remained byte-identical
to reviewed tree 6edf253f38d929fb3ace8b16bfa9249275d813c6. Expected noreply
author/committer; commit body identifies OpenAI Codex assistance, no Claude trailer.
Reported documentation/status/prefix/link/privacy/scope checks and staged
Gitleaks passed; full-history Gitleaks scanned 46 commits with no leaks. No
application tests or builds were repeated. Working tree clean; main/origin/main
unchanged at 85cb0d6. Incremental export .local/p110/m4a-commit-incremental.diff:
23,458 bytes, SHA-256 12b716f00530c4b6851834d7f3dd9747d311e30ac07675c3dee1f61aacd4f8cf.

**Reviewer acceptance of Prompt 110:** incremental diff inspected and checksum
independently matched; accepted, with no new application tests or build run by
the reviewer. This records the supplied review decision.

## Prompt 111: Publish reviewed M4a feature branch and monitor exact-commit CI

- **Date:** 2026-10-16 (Asia/Bangkok).
- **Scope:** prompt-history commit, feature-branch-only push and CI monitoring.

````text
Written for: Mathew and the external reviewer.

Prompt 111 — Publish only the reviewed M4a feature branch and monitor CI. Do not update main.

Read applicable AGENTS.md instructions, CLAUDE.md and the workflows. Avoid reloading full prompt history or printing diffs.

1. Verify starting state

Expected:
- Branch: feat/embedding-contracts.
- HEAD:
  82e8e3111ee6bac87eab381c7a99bf8f6e2c7484.
- Parent:
  ac395039fa43ef19c8e316d253af639f0e35fe0f.
- Working tree clean.
- No upstream or remote feat/embedding-contracts branch.
- Local main and origin/main:
  85cb0d622a5b49c11439b0b9f67abceaa82edb29.
- Expected origin and noreply author/committer identity unchanged.

Read fresh remote refs. Confirm remote main is unchanged and an ancestor of HEAD. Stop on material mismatch.

2. Publication preflight

Inspect everything that would become public relative to remote main:
- ac39503: accepted specification;
- 82e8e31: reviewed implementation;
- the history commit authorized below.

Confirm accurate identities/attribution, no unintended private content or secrets, and no tracked local artifacts, backups, bundles, real environment files or build outputs.

Confirm both workflows trigger on this branch and all five jobs remain enabled:
- Ubuntu verification;
- Windows verification;
- PostgreSQL integration with EG_REQUIRE_INTEGRATION=1;
- container;
- full-history Gitleaks.

Do not modify source, tests, documentation, dependencies, workflows or configuration.

3. Append prompt history and commit

Modify prompts.md only, append-only:
- Record the Prompt 110 commit outcome and reported checks.
- Record the reviewer's acceptance of its incremental diff: inspected and checksum independently matched; no new application tests or build run by the reviewer.
- Append Prompt 111 verbatim.
- Add a preflight note with the verified state, publication scope and branch-only authorization.

Keep historical Windows results separate from new CI:
1479 passed, 205 skipped, including 204 PostgreSQL skips and one POSIX-only signal skip.

Record that local build and installed-wheel verification remained blocked by missing hatchling under the earlier offline/no-install constraints. CI's existing build environment may perform its normal dependency setup; no workflow or lockfile change is authorized.

Do not pre-record publication or CI outcomes.

Check history prefix, private content, git diff --cached --check, staged Gitleaks without suppression and identity.

Commit prompts.md only with subject:
docs: record M4a branch publication authorization

Use accurate Codex attribution under repository conventions.

Verify parent 82e8e31, only prompts.md changed, and working tree clean. Run full-history Gitleaks before pushing. Stop on a finding without suppression, amend or reset.

4. Publish only this branch

Run directly, preserving Git's exit status:

git push --set-upstream origin refs/heads/feat/embedding-contracts:refs/heads/feat/embedding-contracts

Confirm the remote matches the exact published HEAD. No other branch or tag may be pushed.

5. Monitor exact-commit CI

Monitor push-triggered runs for the published SHA on feat/embedding-contracts for up to 25 minutes.

Report all five jobs separately. Required container configuration, context, build, image, smoke and cleanup steps must execute successfully, not be skipped.

Pay particular attention to:
- Ubuntu and Windows embedding tests;
- distribution build;
- clean installed-wheel checks;
- container context and runtime checks after adding the embedding modules.

Do not claim an embedding-specific installed-wheel smoke occurred unless the actual checks exercise it. Report exactly what the existing wheel checks establish.

Use existing GitHub access or the public read-only API. Do not install tools or add credentials. Retrieve logs if accessible; otherwise give links and label counts/output unobserved.

If any job fails, is cancelled or remains pending at the limit:
- report the failing step and accessible evidence;
- stop without changing files, rerunning workflows or making another push.

Do not claim background polling continues after the task ends.

6. Handoff

Report:
- history commit SHA, parent and attribution;
- exact published SHA;
- push command and exit status;
- five job conclusions and run/job links;
- build, wheel and container step conclusions;
- observed summaries separately from unobserved expectations;
- final branch/upstream and clean-tree status;
- confirmation that main remains unchanged.

Do not update documentation after CI in this task. Recording results is a later reviewed task.

No merge, main update, force-push, amend, rebase, tag, branch deletion, local Docker, database contact, provider calls or M4b work.

Return this output only to the external reviewer; no diff attachment is required.
````

**Prompt 111 preflight note (written before commit/publication; no CI result recorded):**
- Verified feat/embedding-contracts at 82e8e3111ee6bac87eab381c7a99bf8f6e2c7484,
  parent ac395039fa43ef19c8e316d253af639f0e35fe0f; clean starting tree; no upstream.
  Fresh git ls-remote showed remote main unchanged at
  85cb0d622a5b49c11439b0b9f67abceaa82edb29 and no remote feature branch. Local
  main/origin/main match that commit, verified as an ancestor of HEAD. Expected
  origin and effective noreply author/committer identities are unchanged.
- Publication scope is ac39503 (accepted specification), 82e8e31 (reviewed
  implementation), plus this prompts.md-only authorization commit. The range
  contains exactly seven reviewed text paths, no tracked artifacts, backups,
  bundles, real environment files or build outputs. Both existing commits have
  noreply identities and accurate Codex attribution. No private-path/key/token
  pattern matches in added content; staged and full-history secret scans follow.
- Both workflows trigger on every push without branch/path filters. Ubuntu and
  Windows verification, PostgreSQL integration with EG_REQUIRE_INTEGRATION=1,
  container and full-history Gitleaks remain enabled. Container configuration,
  effective context, build, image, smoke and cleanup steps are present; cleanup
  has if: always(). No workflow or lockfile changes are authorized.
- Historical Prompt 109 Windows results remain 1479 passed, 205 skipped:
  204 PostgreSQL skips and one POSIX-only signal skip; focused checks 126 passed.
  They are not results for the new publication. Local build and installed-wheel
  verification remained blocked by missing hatchling under offline/no-install
  constraints. CI may use its existing normal dependency/build setup.
- Existing clean-wheel checks import the application/domain package, create the
  app, run entry-point help, check ingest_revision registration and render offline
  migration SQL. They do not directly import or exercise the embedding modules;
  no embedding-specific installed-wheel smoke is claimed in advance.
- Only prompts.md is modified, append-only. Before committing: verify prefix,
  private content, cached whitespace, staged Gitleaks without suppression and
  identity. Use subject docs: record M4a branch publication authorization and
  identify OpenAI Codex assistance. Verify parent/path/clean tree; full-history
  Gitleaks must pass before pushing. Stop on any finding without amend/reset.
- Authorization is only the explicit feature-branch push command above; no other
  branch or tag. Confirm exact remote SHA, then monitor push runs for that SHA
  and branch for at most 25 minutes. Stop on failure/cancellation/timeout without
  fixes, reruns, documentation updates or another push. Main must remain unchanged.


**Prompt 111 publication outcome (recorded in Prompt 112):** prompts.md-only
authorization commit d501bd6de68a965c283a2187665170502af083e2, parent
82e8e3111ee6bac87eab381c7a99bf8f6e2c7484; expected noreply author/committer,
with OpenAI Codex assistance identified in the body. Prefix, scope, private-content,
cached whitespace, staged Gitleaks and identity checks passed. Full-history
Gitleaks before push: 47 commits scanned, no leaks. The explicit command
git push --set-upstream origin refs/heads/feat/embedding-contracts:refs/heads/feat/embedding-contracts
exited 0. Remote feature branch matched exact HEAD; main stayed at 85cb0d6.
All five exact-commit push jobs succeeded. Codex retrieved both workflow records
and all five logs: Ubuntu 1480 passed/204 skipped in 25.65s; Windows 1479 passed/
205 skipped in 32.31s; PostgreSQL 204 passed/1480 deselected in 59.32s. Embedding
tests ran in both verification jobs; both builds and existing installed-wheel
checks passed. Container config/context/build/image/smoke/cleanup succeeded:
74 context files, all 19 planted fixtures excluded; CI-built service image;
upload 202, ingestion success, active revision with two verified chunks,
duplicate 200, idle-worker exit 0/no OOM. CI Gitleaks: 47 commits, no leaks.
Full links and the exact wheel-check scope are in ADR-0013. Final branch tracked
origin/feat/embedding-contracts, tree clean, local/origin/remote main unchanged.
No documentation was updated after CI in Prompt 111; no merge or main update.

**Reviewer verification supplied in Prompt 112:** the reviewer independently
retrieved both successful push workflow records and all five logs for exact SHA
d501bd6de68a965c283a2187665170502af083e2 on feat/embedding-contracts, confirming
the observations above. Both implementing Codex and reviewer retrieved logs
independently. The reviewer did not execute the project suite or Docker locally.
Earlier Prompt 109 local Windows results and the local hatchling failure remain
historical local evidence, separate from this CI result. Existing wheel checks
do not execute embeddings directly; isolated installed-wheel embedding execution
remains unverified. Local Compose is unverified. No semantic-quality claim.

## Prompt 112: Record verified M4a feature-branch results

- **Date:** 2026-10-16 (Asia/Bangkok).
- **Scope/status:** documentation only, staged for external review; no commit or publication.

````text
Written for: Mathew and the external reviewer.

Prompt 112 — Record verified M4a feature-branch results. Documentation only, staged for review. No commit, push or merge.

Read applicable AGENTS.md instructions, CLAUDE.md and relevant status sections. Avoid reloading full prompt history or printing diffs.

1. Verify starting state

Expected:
- Branch: feat/embedding-contracts.
- HEAD, upstream and remote feature branch:
  d501bd6de68a965c283a2187665170502af083e2.
- Parent:
  82e8e3111ee6bac87eab381c7a99bf8f6e2c7484.
- Working tree clean.
- Local main, origin/main and remote main:
  85cb0d622a5b49c11439b0b9f67abceaa82edb29.
- Expected origin and noreply identity unchanged.

Read fresh remote refs. Stop on material mismatch. Record the baseline under .local/p112/.

2. Verified evidence

The external reviewer independently retrieved both workflow records and all five job logs. Both runs were successful push events on feat/embedding-contracts at exact commit `d501bd6de68a965c283a2187665170502af083e2`.

CI:
https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38789281404

Observed:
- Ubuntu, job 116609328373:
  1480 passed, 204 skipped in 25.65s.
- Windows, job 116609328257:
  1479 passed, 205 skipped in 32.31s.
- PostgreSQL, job 116609327970:
  204 passed, 1480 deselected in 59.32s.
- Embedding tests ran successfully in both verify jobs.
- Both distribution builds and existing clean installed-wheel checks passed.

Container job 116609328164:
- configuration passed;
- effective context: 74 files, all 19 planted fixtures excluded;
- image checks passed;
- stack startup and CI-built image identity passed;
- upload 202, ingestion succeeded, active revision with two verified chunks;
- duplicate upload 200;
- idle-worker exit 0, no OOM kill;
- smoke and cleanup passed.

Secret scan:
https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38789281505
Job 116609328947:
47 commits scanned, no leaks found.

Both the implementing Codex session and the external reviewer retrieved logs independently. The reviewer did not execute the project suite or Docker locally.

3. Authorized documentation changes

Modify only:
- README.md
- docs/decisions/0013-embeddings.md
- docs/plan.md
- prompts.md

Record:
- M4a reviewed and verified in CI at d501bd6 on the feature branch;
- not merged; main remains at 85cb0d6;
- Linux and Windows verification and CI builds are complete for this version;
- existing clean installed-wheel checks passed;
- those wheel checks cover application imports/factory, entry points, ingestion registration and offline migrations, not a direct embedding-provider smoke;
- direct embedding-provider execution from an isolated installed wheel remains unverified;
- the earlier local hatchling failure remains historical and local, not a current CI build failure;
- no semantic-quality, retrieval or live-provider evidence is claimed;
- M4b–M4f and overall M4 acceptance remain pending;
- local Compose remains unverified.

Use full evidence and links in ADR-0013 or the plan, with concise references elsewhere. Keep older results tied to their original commits.

Replace stale present-tense “Linux/current-version CI pending” and general build-pending claims. Preserve the narrower installed-embedding limitation.

Do not change the accepted algorithm, specification, source, tests, configuration, dependencies, lockfile or workflows.

4. Prompt history

Append:
- Prompt 111 publication outcome and its actual observations;
- reviewer verification of the exact-commit runs/logs above;
- Prompt 112 verbatim and a truthful outcome marking this documentation awaiting review.

Preserve all earlier bytes. Do not claim the reviewer ran the suite locally.

5. Checks and export

Stage exactly the four permitted files.

Check:
- unchanged earlier prompts.md prefix;
- links and anchors;
- truthful status and verification scope;
- private content and unintended artifacts;
- git diff --cached --check;
- staged Gitleaks without suppression.

No application tests, builds, installs, Docker, database contact or provider calls are needed.

Export the complete staged diff against HEAD, excluding prompts.md:
.local/p112/m4a-verification-docs.diff

UTF-8 without BOM. Report baseline/final staged tree, paths, statistics, byte size and SHA-256. Do not print the diff.

No commit, push, merge, amend, rebase, tag, branch deletion or M4b work.

Return this output plus .local/p112/m4a-verification-docs.diff to the external reviewer.
````

**Prompt 112 outcome (documentation awaiting external review):** verified clean
feat/embedding-contracts at d501bd6de68a965c283a2187665170502af083e2, expected
parent 82e8e31, matching upstream and fresh remote feature ref. main/origin/main
and fresh remote main matched 85cb0d622a5b49c11439b0b9f67abceaa82edb29. Expected
origin and noreply effective identity verified. Baseline saved under .local/p112/.
Only README.md, ADR-0013, docs/plan.md and this append-only history changed.
ADR-0013 records full exact-commit CI evidence/links and independent log retrieval
by Codex and reviewer; concise references replace stale general CI/build-pending
claims. Direct isolated installed-wheel embedding execution remains unverified;
the historical local hatchling failure, unverified local Compose and pending
M4b–M4f/overall M4 acceptance are retained. Accepted contracts/algorithm and all
source/tests/config/dependencies/workflows are unchanged. No semantic-quality,
retrieval or live-provider evidence is claimed. The reviewer did not run the
suite or Docker locally. This documentation is staged for review, not accepted.

Checks after this note: exact four-path staged scope, identical earlier history
prefix and verbatim Prompt 112, links/anchors, status/verification scope,
private-content/artifact checks, cached whitespace and staged Gitleaks without
suppression. Actual results and export metadata are reported in the handoff.
Complete staged diff against HEAD excluding prompts.md is exported as UTF-8
without BOM to .local/p112/m4a-verification-docs.diff. No application tests,
builds, installs, Docker, database/provider contact, commit, push, merge or M4b work.


**Prompt 112 acceptance (recorded in Prompt 113):** reviewer inspected the full
documentation diff, independently matched SHA-256
f72016094f9dc2475e824d5b73ebc7e9b1c0536d03097556e125cefeb2b5fcd4 and compared
it with previously retrieved exact-commit CI evidence. Accepted; no new local
application checks. Accepted staged tree 776b48a2d01649e6e4366e04b7597d63e557bc37.
The three reviewed documents are preserved byte-identical for this task.

## Prompt 113: Commit M4a CI documentation, publish feature, conditionally fast-forward main

- **Date:** 2026-10-16 (Asia/Bangkok).
- **Scope:** reviewed documentation commit; gated feature and main publication.

````text
Written for: Mathew and the external reviewer.

Prompt 113 — Commit the reviewed M4a CI documentation, publish the feature branch, then fast-forward main only after all five checks pass.

Read applicable AGENTS.md instructions, CLAUDE.md and the workflows. Avoid reloading full prompt history or printing diffs.

1. Verify starting state

Expected:
- Branch: feat/embedding-contracts.
- HEAD, upstream and remote feature branch:
  d501bd6de68a965c283a2187665170502af083e2.
- Staged tree:
  776b48a2d01649e6e4366e04b7597d63e557bc37.
- Exactly four staged paths:
  README.md
  docs/decisions/0013-embeddings.md
  docs/plan.md
  prompts.md
- Nothing unstaged or untracked.
- Local main, origin/main and remote main:
  85cb0d622a5b49c11439b0b9f67abceaa82edb29.
- Expected origin and noreply identity unchanged.

Fetch fresh refs. Confirm main is an ancestor of HEAD with no independent local main commits. Stop on material mismatch. Record the accepted staged tree under .local/p113/.

2. Preserve reviewed documents and append history

Keep README.md, ADR-0013 and docs/plan.md byte-identical to the accepted staged tree.

Modify prompts.md only, append-only:
- Record acceptance of the Prompt 112 diff: reviewer inspected it, independently matched its checksum and compared it with the previously retrieved CI evidence; no new local application checks.
- Append Prompt 113 verbatim.
- Add a preflight note with verified state, checks, publication order and stop conditions.

Do not pre-record publication or new CI results.

Verify:
- exactly four staged paths;
- only prompts.md differs from the accepted tree;
- earlier prompt history unchanged;
- links/anchors;
- private content and unintended artifacts;
- git diff --cached --check;
- staged Gitleaks without suppression;
- effective identity.

Commit with subject:
docs: record verified M4a results and main publication authorization

Use accurate Codex attribution.

Verify parent d501bd6, expected paths, document byte identity and clean tree. Run full-history Gitleaks before publication. Stop on a finding without suppression or amend.

No application tests or builds need repeating locally.

3. Feature-branch push and CI

Run directly, preserving Git's exit status:

git push origin refs/heads/feat/embedding-contracts:refs/heads/feat/embedding-contracts

Confirm the remote equals the exact new HEAD.

Monitor push-triggered workflows for that SHA and branch for up to 25 minutes. All five jobs must succeed:
- Ubuntu verify;
- Windows verify;
- PostgreSQL integration;
- container;
- full-history Gitleaks.

Required container configuration, context, build, image, smoke and cleanup steps must execute successfully, not be skipped.

Use existing GitHub access or read-only API. Retrieve logs if accessible; otherwise label counts/output unobserved. Do not reuse d501bd6 counts as results for the new SHA.

If any required job fails, is cancelled or remains pending at the limit, stop without changing main. Report accessible evidence. Do not fix files, rerun workflows or push again.

4. Fast-forward main only after five green jobs

Fetch fresh refs again and confirm:
- remote main remains 85cb0d622a5b49c11439b0b9f67abceaa82edb29;
- remote feature equals the verified commit;
- main is its ancestor;
- local main equals origin/main with no independent commits;
- working tree clean.

Stop if any precondition fails.

Switch to main, then:
git merge --ff-only <exact verified commit>

Push only:
git push origin refs/heads/main:refs/heads/main

Preserve Git exit statuses. No merge commit or force-push.

Monitor all five jobs again for the exact SHA's push to main, up to 25 minutes. Report failures and stop without rollback, fixes, reruns or further pushes.

5. Final handoff

Report:
- commit SHA, parent, identity and paths;
- reviewed documents' byte identity;
- checks/scans;
- both push commands and exit statuses;
- exact SHA and all five run/job conclusions for each push;
- build, wheel and required container step results;
- observed summaries separately from inaccessible output;
- refs before/after and final working-tree state.

Existing wheel checks still do not directly exercise the embedding provider. Preserve this limitation unless independently verified; no additional smoke or workflow change is authorized here.

Leave documents unchanged after publication. Recording main results is a later reviewed task.

No force-push, amend, rebase, squash, tag, branch deletion, local Docker, database contact, provider calls or M4b work.

Return this output only to the external reviewer; no diff attachment is required.
````

**Prompt 113 preflight note (before commit/publication; no new CI outcome recorded):**
- Verified feat/embedding-contracts, HEAD/upstream/fresh remote feature at
  d501bd6de68a965c283a2187665170502af083e2; accepted staged tree
  776b48a2d01649e6e4366e04b7597d63e557bc37 with exactly README.md, ADR-0013,
  docs/plan.md and prompts.md staged; nothing unstaged/untracked. Accepted tree
  recorded under .local/p113/. git fetch origin completed; local main,
  origin/main and fresh remote main at 85cb0d622a5b49c11439b0b9f67abceaa82edb29,
  an ancestor of HEAD, without independent local main commits. Expected origin
  and effective noreply author/committer identity unchanged.
- Only prompts.md changes relative to the accepted tree, preserving every earlier
  byte. README, ADR-0013 and plan remain byte-identical. Source, tests, algorithm,
  workflows, dependencies and configuration are untouched. Both workflows still
  trigger on branch pushes with all five jobs enabled; integration requires
  EG_REQUIRE_INTEGRATION=1; required container steps and full-history scan remain.
- Before commit: verify four-path scope, accepted document bytes, earlier history
  prefix and verbatim prompt, links/anchors, privacy/artifacts, cached whitespace,
  staged Gitleaks without suppression and effective identity. Checks run after
  this note; actual outcomes are reported in the handoff, not pre-recorded here.
- Commit subject: docs: record verified M4a results and main publication authorization.
  Use expected noreply identities and OpenAI Codex assistance in the body; no
  Claude attribution. Verify parent d501bd6, four paths, preserved documents and
  clean tree; full-history Gitleaks must pass before publication.
- Order: push feature only; verify exact remote SHA; require all five push jobs
  on that SHA/branch to succeed within 25 minutes, with container config/context/
  build/image/smoke/cleanup executed successfully. Stop on any failure, cancelled
  job or timeout without fixes, reruns, another push or changing main.
- Only after five green jobs: fetch again; require clean tree, remote main still
  85cb0d6, remote feature equal to verified commit, local main equal origin/main,
  no independent main commits and main ancestor of verified commit. Then switch
  to main, merge --ff-only exact verified SHA, and push main only. Monitor that
  SHA's main push separately for all five jobs up to 25 minutes. On failure stop
  without rollback/fixes/reruns/further pushes. No force or merge commit.
- Existing d501bd6 evidence stays tied to d501bd6. New-SHA counts/output require
  retrieved logs; inaccessible output is unobserved. Existing installed-wheel
  checks do not directly exercise embeddings, and this limitation is preserved.
- No local application tests/builds, Docker, database/provider contact, M4b work,
  history rewriting or tags. Documents stay unchanged after publication;
  recording main evidence belongs to a later reviewed task.

**Prompt 113 outcome (recorded in Prompt 114 by Claude Code):** at the start of
Prompt 114, local and fresh remote `main` and `feat/embedding-contracts` were all at
5fdaa1cecbcac876af007e6f4328436ef6faeda2 (parent
d501bd6de68a965c283a2187665170502af083e2), with a clean tree, the expected origin
and the noreply author/committer identity. The documentation commit was therefore
created and published, and `main` was fast-forwarded to it. This session did not
receive the implementing Codex session's handoff: feature-branch push-run IDs and
results for 5fdaa1c are not recorded here, and nothing beyond the repository
state and the reviewer evidence below is claimed.

**Reviewer main evidence for 5fdaa1c (supplied in Prompt 114):** the external
reviewer retrieved both main workflow records and all five job logs for exact
commit 5fdaa1cecbcac876af007e6f4328436ef6faeda2. Both runs were push events on
main with conclusion success. CI run 38791558180: Ubuntu job 116617134276
`1480 passed, 204 skipped in 28.81s`; Windows job 116617133905 `1479 passed,
205 skipped in 33.37s`; PostgreSQL job 116617134528 `204 passed, 1480 deselected
in 62.80s (0:01:02)`; container job 116617133613: configuration, context, build,
image checks, smoke and cleanup passed, with 74 context files and all 19 planted
fixtures excluded; application services used the CI-built image; upload 202,
successful ingestion, active revision with two verified chunks; duplicate upload
200; the idle worker exited 0 without an OOM kill. Distribution builds and the
existing installed-wheel checks passed. Secret-scan run 38791558235, job
116617134227: 48 commits scanned, no leaks found. The implementing Codex session
and the reviewer retrieved the logs independently; the reviewer did not execute
the project suite or Docker locally. Direct embedding-provider execution from an
isolated installed wheel remains unverified. Earlier d501bd6 feature-branch
evidence remains historical.

## Prompt 114: Record M4a main verification and propose the M4b persistence specification

- **Date:** 2026-10-16 (Asia/Bangkok).
- **Session:** Claude Code (resuming after Codex Prompts 107–113).
- **Scope/status:** documentation only, staged for external review; no commit or publication.

````text
Written for: Mathew and the external reviewer.

Prompt 114 — Record M4a main verification and propose the detailed M4b persistence specification. Documentation only; stage for review.

You are Claude Code, resuming after Codex completed Prompts 107–113. References to the implementing Codex session describe historical work; preserve that attribution. Record your new work accurately as Claude Code work.

Do not repeat completed tasks or rewrite earlier prompt history.

Read applicable AGENTS.md instructions, CLAUDE.md, the accepted M4 direction, ADR-0013, existing persistence models/migrations, chunk storage and fenced-write conventions. Avoid reloading full prompt history or printing diffs.

1. Verify starting state

Expected:
- Branch: main.
- HEAD, origin/main and remote main:
  5fdaa1cecbcac876af007e6f4328436ef6faeda2.
- Parent:
  d501bd6de68a965c283a2187665170502af083e2.
- Local and remote feat/embedding-contracts at HEAD.
- Working tree clean.
- Origin:
  https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git
- Author and committer identity:
  mathewmljourney93 <257921624+mathewmljourney93@users.noreply.github.com>.

Read fresh remote refs. Stop on a material mismatch without changing files, staging or branches.

Create docs/m4b-persistence-spec from HEAD if it does not exist. Do not overwrite an existing branch. Record the baseline under .local/p114/.

2. Record independently verified main evidence

The external reviewer retrieved both main workflow records and all five job logs for exact commit `5fdaa1cecbcac876af007e6f4328436ef6faeda2`.

Both runs were push events on main, conclusion success.

CI:
https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38791558180

Observed:
- Ubuntu job 116617134276:
  1480 passed, 204 skipped in 28.81s.
- Windows job 116617133905:
  1479 passed, 205 skipped in 33.37s.
- PostgreSQL job 116617134528:
  204 passed, 1480 deselected in 62.80s (0:01:02).
- Container job 116617133613:
  configuration, context, build, image checks, smoke and cleanup passed;
  74 context files, all 19 planted fixtures excluded;
  application services used the CI-built image;
  upload 202, successful ingestion, active revision with two verified chunks;
  duplicate upload 200;
  idle worker exited 0 without OOM kill.
- Distribution builds and existing installed-wheel checks passed.

Secret scan:
https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38791558235
Job 116617134227:
48 commits scanned, no leaks found.

The implementing Codex session and external reviewer independently retrieved logs. The reviewer did not execute the project suite or Docker locally.

Preserve the distinction that direct embedding-provider execution from an isolated installed wheel remains unverified. Preserve earlier feature-branch evidence as historical.

3. Propose M4b in docs/plan.md

M4b is embedding persistence, full-text representation and index completeness/readiness. Keep it proposed and unimplemented.

Preserve accepted decisions:
- indexing readiness is separate from document activation;
- M3 activation and immutable chunks remain unchanged;
- tenant/revision/profile isolation;
- exact vector operations, no approximate index;
- fixed 1024-dimensional baseline;
- existing job fencing architecture;
- later snapshot-relative supersession;
- no silent omission of unready active revisions at snapshot capture.

Produce a concrete specification covering:

A. Schema
- Exact tables, columns, keys, composite foreign keys, uniqueness, checks and indexes.
- Immutable embedding profile identity/fingerprint and tenant scope.
- Index binding to revision, chunker, source manifest/count and profile.
- Embedding-row membership in the correct index, revision, chunk and tenant.
- Partial versus ready state, timestamps and permissible transitions.
- How schema constraints prevent mismatched dimensions/profiles and cross-tenant or cross-revision rows.
- Identify which invariants are database-enforced and which rely on trusted application code.

B. Numeric storage
- pgvector representation and SQLAlchemy/psycopg integration.
- Application validation before storage and validation after conversion to the stored representation.
- Finite values, unit-norm tolerance and permitted offline zero vectors.
- Float32 rounding, deterministic canonicalization and idempotent replay comparisons.
- Define whether equality refers to provider values or canonical stored values; do not promise exact float64 round trips.
- Future cosine queries must exclude zero vectors explicitly.

C. Completeness and immutability
- Bounded idempotent batch writes and conflict handling.
- How completeness verifies exact chunk membership, hashes, profile and stored vectors rather than row count alone.
- Ready indexes become immutable.
- Define how M4c will combine readiness with fenced job success atomically, without implementing its handler now.
- Define lock ordering and ownership responsibilities at the M4b/M4c boundary; do not introduce an unfenced production write path merely to simplify tests.
- Clarify whether lexically searchable chunks can ever become eligible before vector readiness.

D. Full-text representation
- Exact source text and explicit PostgreSQL simple configuration.
- Generated versus maintained tsvector choice and indexing rationale.
- No changes to chunk text, IDs or source spans.
- Tenant/snapshot filters must precede future channel limits.
- M4d ranking and retrieval execution remain outside this slice.

E. Migration and dependencies
- Next migration number after inspecting the actual chain.
- Create the vector extension only when this migration first needs it.
- Online and offline migration behaviour, upgrade/downgrade ordering and extension ownership.
- Do not drop an extension used by unrelated objects on downgrade.
- Required PostgreSQL privileges and test/CI implications.
- Propose any Python dependency only if necessary. Research official documentation, release age and advisories before recommending an exact release.
- No installation or policy bypass.

F. Tests and scope
- Meaningful database-independent contract/serialization tests.
- Real PostgreSQL tests for composite constraints, wrong dimensions, invalid numerics, zero handling, float32 replay, partial readiness, conflicting writes, immutability and migration round trips.
- Relevant fenced-write, concurrency and rollback cases.
- Separate written/planned tests from execution evidence.
- Intended implementation files and any required CI/container changes.
- No live providers, indexing handler, review orchestration, retrieval endpoint, corpus evaluation or M4c implementation.

List unresolved decisions with recommended choices and tradeoffs. Do not silently broaden accepted scope.

4. Authorized changes

Only:
- README.md
- docs/decisions/0013-embeddings.md
- docs/plan.md
- prompts.md

Update M4a status to verified and on main at 5fdaa1c. Add the proposed M4b specification to the plan and a concise README planning reference.

Preserve historical results and limitations. Do not create ADR-0014 until the implementation task unless separately authorized.

Append Prompt 113 outcome, reviewer main evidence, Prompt 114 verbatim and a truthful outcome note. Preserve earlier prompt-history bytes.

5. Checks and review export

Stage exactly the four authorized files.

Check:
- earlier prompts.md content remains an identical prefix;
- relative links and anchors;
- status consistency;
- private content and unintended artifacts;
- git diff --cached --check;
- staged Gitleaks without suppression or allowlisting.

No application tests, build, dependency installation, Docker, database contact or provider calls.

Export the full staged diff against HEAD, excluding prompts.md:
.local/p114/m4b-persistence-spec.diff

Use UTF-8 without BOM. Report baseline commit, final staged tree, changed paths, statistics, byte size and SHA-256. Do not print the diff.

Report the proposed design, decisions needed, checks and Git state concisely.

No commit, push, merge, amend, rebase, tag, branch deletion or implementation is authorized.

6. Session and handoff rules

Do not recommend a new session after one or two tasks. Continue through implementation and corrections. Around 20 substantial prompts, or if actual context problems arise, recommend a handover at a suitable checkpoint. Count only prompts actually handled in this Claude session; do not count Codex's prompts as Claude-session work.

When supplying any subsequent prompt to Mathew, provide the complete copy-paste prompt, including necessary context and instructions. Do not provide only a preamble, amendment or reference to an earlier prompt.

Return this output plus .local/p114/m4b-persistence-spec.diff to the external reviewer.
````

**Prompt 114 outcome (Claude Code; documentation awaiting external review):**
verified main, HEAD, origin/main and fresh remote main and feat/embedding-contracts
at 5fdaa1c (parent d501bd6), a clean tree, the expected origin and the noreply
identity. Created docs/m4b-persistence-spec from HEAD; baseline saved under
.local/p114/. Changed only README.md, ADR-0013, docs/plan.md and this append-only
history. M4a is recorded as verified and on main at 5fdaa1c, from the reviewer's
main evidence; the d501bd6 feature-branch evidence is kept as historical, and the
limitation on direct installed-wheel embedding execution is preserved. The plan
adds a PROPOSED, unimplemented M4b specification: migration 0005, three tables,
additive FK-target keys on chunks and chunk_sets, a generated `simple` tsvector,
float32 canonicalization, CHECK-bound vector digests, fenced batch writes and
readiness, the M4c boundary and lock order, a planned test matrix and 12
unresolved decisions. Dependency research used official PyPI metadata, changelogs
and GitHub advisory pages only; nothing was installed. No ADR-0014, source, test,
migration, workflow or dependency change was made. No application tests, builds,
Docker, database or provider contact. Staged-scope, prefix, link, privacy,
whitespace and Gitleaks results are reported in the handoff, not pre-recorded here.

**Prompt 114 review (recorded in Prompt 115):** the external reviewer inspected the
Prompt 114 diff and independently matched its SHA-256
7e014c5f780ea829799ef82f92070803f0242fe4b602fc3ddf41daa54ded936d. The M4a
publication documentation is accepted. For M4b, recommendations 1–4 and 6–12 were
approved as recommended, subject to corrections: additive composite FK-target
unique keys; generated stored tsvector and GIN index; pgvector-backed
numeric/checksum checks; no new Python dependency and a small in-repo SQLAlchemy
type; application-enforced immutability without triggers; building/ready states;
deterministic UUID5 profile/index IDs; batches of at most 32; metadata creation in
the caller's transaction; no lexical-only eligibility before index readiness;
copied, FK-bound chunk content hashes. Decision 5 was settled differently: preserve
the vector extension on downgrade. Corrections requested: the extension lifecycle;
removing the claim that every M4a-valid vector passes post-float32 validation;
explicit NOT NULL; job-kind/payload/tenant/fresh-ownership binding for writes and
readiness, including already-ready no-ops; exact reuse of chunk-set helpers rather
than calling `require_complete_chunk_set` without its arguments; the
`identity.fingerprint` property. The reviewer inspected the pgvector 0.8.7
source/function declarations and the existing completeness helper, and ran a
standard-library float32 probe (norm 0.999999001 → float32 0.9999989867210388,
outside 1e-6). The reviewer ran no project suite, Docker or database tests. The
complete M4b specification remains proposed; no implementation is authorized.

## Prompt 115: Correct the proposed M4b persistence specification and record review decisions

- **Date:** 2026-10-16 (Asia/Bangkok).
- **Session:** Claude Code.
- **Scope/status:** documentation only, staged for external review; no commit or implementation.

````text
Written for: Mathew and the external reviewer.

Prompt 115 — Correct the proposed M4b persistence specification and record review decisions. Documentation only; no implementation or commit.

Read CLAUDE.md and the relevant M4b specification. Do not reload full prompt history or print diffs.

1. Verify starting state

Expected:
- Branch: docs/m4b-persistence-spec.
- HEAD:
  5fdaa1cecbcac876af007e6f4328436ef6faeda2.
- Staged tree:
  f555a70936228eeb7153ec8fa5cc973151767db6.
- Exactly README.md, docs/decisions/0013-embeddings.md, docs/plan.md and prompts.md staged.
- Nothing unstaged or untracked outside ignored local artifacts.
- main and origin/main unchanged at HEAD.
- Expected origin and noreply identity unchanged.

Stop on material mismatch. Record the baseline tree under .local/p115/.

2. Review decisions

The reviewer inspected the Prompt 114 diff and independently matched its checksum. The M4a publication documentation is accepted.

For M4b, approve the recommended choices numbered 1–4 and 6–12 in the proposal, subject to the corrections below:
- additive composite FK-target unique keys;
- generated stored tsvector and GIN index;
- pgvector-backed numeric/checksum checks;
- no new Python dependency and a small in-repo SQLAlchemy type;
- application-enforced immutability without triggers;
- building/ready states;
- deterministic UUID5 profile/index IDs;
- batches of at most 32;
- metadata creation in the caller's transaction;
- no lexical-only eligibility before index readiness;
- copied, FK-bound chunk content hashes.

Decision 5 is settled differently: preserve the vector extension on downgrade.

The complete M4b specification remains proposed pending review of these corrections. No implementation is authorized.

3. Extension lifecycle correction

Replace the proposed guarded extension drop:
- Upgrade creates vector with IF NOT EXISTS when migration 0005 first needs it.
- Downgrade removes this migration's tables, indexes, generated column and added constraints, in dependency-safe order.
- Downgrade leaves the vector extension installed, whether preinstalled or created by this migration.
- No ownership marker, pg_depend-based drop logic or CASCADE.
- Explain this deliberate residual infrastructure and that extension removal is an explicit administrative operation outside Alembic downgrade.

Update planned tests:
- extension absent before the first upgrade in a fresh test database;
- extension present at head;
- extension retained after downgrade to 0004;
- re-upgrade succeeds;
- a preinstalled extension and unrelated vector-using objects survive;
- fresh-empty-database safety checks remain intact.

Inspect the existing integration-fixture cleanup and migration tests. Specify any adjustments needed because a downgraded database may now retain vector; do not weaken the disposable-database guard or pretend extension absence is still guaranteed after downgrade.

Offline SQL rendering must remain supported without database introspection.

4. Float32 correction

Remove the statement that all M4a-valid vectors necessarily pass storage validation after rounding.

The reviewer independently reproduced:
- provider coordinate/norm: 0.999999001;
- accepted by M4a's absolute 1e-6 norm tolerance;
- float32 value: 0.9999989867210388;
- outside the same 1e-6 storage tolerance.

Retain the proposed policy:
- validate the provider vector;
- round to float32 and canonicalize negative zero;
- revalidate the canonical stored vector;
- reject with a fixed error if post-conversion validation fails;
- no silent renormalization or widened tolerance;
- perform this validation before SQL;
- no partial batch writes on a rejected vector.

Explain that provider-contract validity does not guarantee storage-contract validity.

Add planned tests for:
- this concrete lower-boundary example;
- successful rounding cases;
- upper/lower tolerance boundaries;
- application/database agreement for canonical vectors;
- fixed privacy-safe rejection and unchanged database state.

Do not label the numerical reproduction as a project-suite or database test.

5. Complete the schema contract

Explicitly state NOT NULL for all required columns, including:
- identity fields, dimensions, fingerprints and zero policy;
- index source/profile bindings and status;
- embedding membership, content/vector digests and is_zero;
- required timestamps.

Only ready_at and vector_manifest_sha256 are nullable as specified for building indexes.

Explain that CHECKs and composite foreign keys do not by themselves reject NULL inputs. Include planned direct-SQL null rejection tests for required fields, especially booleans and copied FK columns.

Specify initial building state and NULL ready metadata, and retain the existing ready-state consistency checks.

6. Fence and completeness clarifications

For both vector writes and readiness:
- require job kind index_revision;
- obtain index_id from the locked job's validated payload;
- enforce tenant scope;
- use job → index lock ordering;
- recheck fresh ownership after lock/uniqueness waits on every successful path, including already-ready idempotent no-ops;
- readiness and successful job completion remain in one fenced transaction.

Add planned tests for wrong job kind, malformed/mismatched payload, foreign tenant and stale ownership after waiting on an already-ready index.

The reviewer inspected the existing require_complete_chunk_set signature:
require_complete_chunk_set(session, revision, *, expected)

Specify exactly how M4b obtains the RevisionSnapshot and ExpectedChunkSet from its immutable index/chunk-set binding, or which pure manifest helper it reuses. Do not imply the activation callback can be called without its required arguments. Do not change M3 locking or activation semantics.

Correct fingerprint access to the existing property identity.fingerprint, not identity.fingerprint().

7. Scope and prompt history

Change only docs/plan.md and prompts.md relative to baseline f555a70936228eeb7153ec8fa5cc973151767db6.

Keep README.md and ADR-0013 byte-identical to that baseline. Keep the M4b heading/anchor stable unless an unavoidable link correction is explained.

Append:
- review note recording accepted M4a documentation, matched checksum, settled M4b choices and requested corrections;
- reviewer inspected pgvector 0.8.7 source/function declarations and the existing completeness helper, and ran a standard-library float32 probe;
- reviewer ran no project suite, Docker or database tests;
- Prompt 115 verbatim and a truthful outcome note.

Preserve earlier prompt-history bytes.

8. Checks and review export

Keep exactly the existing four files staged.

Check:
- only plan and prompt history changed from the baseline tree;
- README and ADR-0013 byte identity;
- earlier prompts.md prefix unchanged;
- links/anchors, status consistency, private content/artifacts;
- git diff --cached --check;
- staged Gitleaks without suppression.

Do not run application tests, builds, installations, Docker, databases or providers.

Export the complete incremental diff from baseline staged tree
f555a70936228eeb7153ec8fa5cc973151767db6
to the final staged tree, excluding prompts.md:
.local/p115/m4b-spec-corrections.diff

UTF-8 without BOM. Report baseline/final, paths, statistics, byte size and SHA-256. Do not print the diff.

No commit, push, merge, amend, rebase, tag, branch deletion or implementation.

Return this output plus .local/p115/m4b-spec-corrections.diff to the external reviewer.
````

**Prompt 115 outcome (Claude Code; corrections awaiting external review):**
verified the branch docs/m4b-persistence-spec, HEAD 5fdaa1c, staged tree
f555a70936228eeb7153ec8fa5cc973151767db6 with exactly the four expected paths,
nothing unstaged or untracked, main/origin/main at HEAD, and the expected origin
and noreply identity. Baseline saved under .local/p115/.

Only docs/plan.md and this history changed; README.md and ADR-0013 are unchanged
from the baseline, and the M4b heading and anchor are unchanged. The plan records
the settled choices: 1–4 and 6–12 approved, and 5 replaced by preserving the
extension. It replaces the guarded drop with a downgrade that leaves `vector`
installed (no marker, pg_depend logic or CASCADE). It specifies the test-fixture
implications, notably that the `DROP SCHEMA public CASCADE` reset should remove
`vector` (to be confirmed in CI, with an assertion added to the fixture); the
disposable-database guard is unchanged. It removes the claim that every M4a-valid
vector survives rounding and adds post-rounding rejection before any SQL. It adds
explicit NOT NULL with the reason, the job-kind/payload/tenant/fresh-ownership
binding including already-ready no-ops, reuse of the chunk-set statement builders
and the pure manifest helpers instead of calling `require_complete_chunk_set`, the
`identity.fingerprint` property, and the corresponding planned tests.

Claude Code also ran a standard-library float32 probe locally, outside the project
suite. It reproduced the reviewer's lower-boundary values and showed 1.000001
rounding to 1.0000009536743164, inside the tolerance. No application tests,
builds, installs, Docker, database or provider contact. Staged-scope, byte-identity,
prefix, link, privacy, whitespace and Gitleaks results are reported in the handoff,
not pre-recorded here.

**Prompt 115 acceptance (recorded in Prompt 116):** the external reviewer accepts the
complete M4b specification from Prompt 114, as corrected in Prompt 115. The reviewer
inspected both specification diffs and independently matched both checksums
(Prompt 114: 7e014c5f780ea829799ef82f92070803f0242fe4b602fc3ddf41daa54ded936d;
Prompt 115: 9f34fcd8f2fda42232dbbe3726663c92dbce92044e8ed0c4e9b70994958df481). The
reviewer also inspected the pgvector 0.8.7 vector-send/norm source and function
declarations and the existing chunk completeness helper, and reproduced the float32
tolerance issue with a standard-library probe. The reviewer ran no project suite,
Docker or database tests. Accepted staged tree
13f53832b3af49ca658f229fbda520572ef3bf97.

Accepted decisions:
- the three-table schema and composite tenant/revision/profile constraints;
- explicit required-column NOT NULL constraints;
- the generated stored full-text representation and GIN index;
- float32 canonicalization, stored-byte digests and post-rounding rejection;
- no new Python dependency;
- bounded fenced writes and completeness/readiness checks;
- job-kind/payload binding and fresh ownership checks, including no-ops;
- application-enforced immutability;
- metadata creation in the caller's transaction;
- preserving vector on downgrade;
- the documented test-fixture adjustments and real PostgreSQL verification
  requirements.

These are design decisions, not execution evidence. The migration, constraints,
numeric storage, reflection, fixture reset and concurrency behaviour remain
unimplemented and unverified. M4c–M4f still require detailed reviews before
implementation. No indexing handler or retrieval functionality is authorized.

## Prompt 116: Record acceptance of the corrected M4b specification and commit locally

- **Date:** 2026-10-16 (Asia/Bangkok).
- **Session:** Claude Code.
- **Scope:** acceptance wording and a local documentation commit; no implementation or publication.

````text
Written for: Mathew and the external reviewer.

Prompt 116 — Record acceptance of the corrected M4b specification and commit the documentation locally. No implementation or publication.

Read CLAUDE.md and applicable repository instructions. Avoid reloading full prompt history or printing diffs.

1. Verify starting state

Expected:
- Branch: docs/m4b-persistence-spec.
- HEAD:
  5fdaa1cecbcac876af007e6f4328436ef6faeda2.
- Staged tree:
  13f53832b3af49ca658f229fbda520572ef3bf97.
- Exactly four staged paths:
  README.md
  docs/decisions/0013-embeddings.md
  docs/plan.md
  prompts.md
- Nothing unstaged or untracked outside ignored artifacts.
- Local main and origin/main unchanged at HEAD.
- Expected origin and noreply identity unchanged.

Stop on a material mismatch. Record the accepted staged tree under .local/p116/.

2. Acceptance decision

The external reviewer accepts the complete M4b specification from Prompt 114, corrected in Prompt 115.

The reviewer:
- inspected both specification diffs and independently matched both checksums;
- inspected pgvector 0.8.7 vector-send/norm source and function declarations;
- inspected the existing chunk completeness helper;
- reproduced the float32 tolerance issue with a standard-library probe;
- ran no project suite, Docker or database tests.

Accepted decisions include:
- the three-table schema and composite tenant/revision/profile constraints;
- explicit required-column NOT NULL constraints;
- generated stored full-text representation and GIN index;
- float32 canonicalization, stored-byte digests and post-rounding rejection;
- no new Python dependency;
- bounded fenced writes and completeness/readiness checks;
- job-kind/payload binding and fresh ownership checks, including no-ops;
- application-enforced immutability;
- metadata creation in the caller's transaction;
- preserving vector on downgrade;
- the documented test-fixture adjustments and real PostgreSQL verification requirements.

These are design decisions, not execution evidence. Migration, constraints, numeric storage, reflection, fixture reset and concurrency behaviour remain unimplemented and unverified.

M4c–M4f still require detailed reviews before implementation. No indexing handler or retrieval functionality is authorized by this specification acceptance.

3. Narrow documentation edits

Only the existing four staged files may change.

Update README, ADR-0013 and plan consistently:
- M4a remains verified and on main at 5fdaa1c;
- M4b specification accepted at external review, Prompt 116;
- M4b implementation pending;
- overall M4 acceptance pending.

In the plan:
- update the M4b heading/status and all affected relative anchors;
- change the unresolved-decisions heading to settled review decisions;
- preserve the historical recommendations, clearly labelled historical;
- retain the corrected normative extension policy;
- preserve the schema, numeric rules, fencing, test plan and limitations without redesign.

Do not claim any M4b tests have run. Keep the direct installed-wheel embedding limitation and local Compose limitation.

Do not change source, tests, migrations, dependencies, workflows, configuration, CLAUDE.md or create ADR-0014.

4. Prompt history

Append:
- acceptance note under Prompt 115 with the reviewer's actual work and decision above;
- Prompt 116 verbatim;
- truthful pre-commit note.

Preserve earlier bytes. Do not include the new commit's own SHA or pre-record publication.

5. Checks and local commit

Verify:
- exactly four permitted paths staged;
- differences against the accepted tree are only acceptance wording, necessary anchor updates and prompt history;
- earlier prompts.md content is an identical prefix;
- links/anchors and consistent status;
- private content and unintended artifacts;
- git diff --cached --check;
- staged Gitleaks without suppression;
- effective noreply author and committer identity.

Commit with subject:
docs: record accepted embedding persistence specification

Use the repository's established Claude co-author convention.

After committing:
- verify parent 5fdaa1cecbcac876af007e6f4328436ef6faeda2;
- verify exactly the four committed paths;
- run full-history Gitleaks;
- confirm clean working tree;
- confirm main and origin/main unchanged.

No application tests, builds, dependency installation, Docker, database contact or provider calls are needed.

Stop on failed checks without suppression, amend or reset.

6. Export and handoff

Export the complete incremental diff from accepted tree
13f53832b3af49ca658f229fbda520572ef3bf97
to the new commit, excluding prompts.md:
.local/p116/m4b-spec-acceptance.diff

UTF-8 without BOM. Report baseline/final, paths, statistics, byte size and SHA-256. Do not print the diff.

Report commit SHA, parent, attribution, checks and final Git state.

No push, merge, force-push, amend, rebase, tag, branch deletion or implementation.

Return this output plus .local/p116/m4b-spec-acceptance.diff to the external reviewer.
````

**Prompt 116 pre-commit note (Claude Code; written before the commit):** verified the
branch docs/m4b-persistence-spec, HEAD 5fdaa1c, accepted staged tree 13f53832 with
exactly the four expected paths, nothing unstaged or untracked, local main and
origin/main at HEAD, and the expected origin and noreply identity. The accepted
tree is recorded under .local/p116/.

Edits relative to the accepted tree are acceptance wording only:
- the M4b heading becomes "ACCEPTED at review, Prompt 116; implementation pending",
  with every relative anchor in README, ADR-0013 and the plan updated to the new
  slug;
- the status text in all three documents is consistent;
- the decisions heading is now "Settled review decisions", and the numbered list
  is labelled as the historical Prompt 114 recommendation text;
- section E's normative policy of preserving the extension is retained.

The schema, numeric rules, fencing, test plan and limitations are unchanged. No M4b
test has run. The installed-wheel embedding and local Compose limitations are kept.
No source, tests, migrations, dependencies, workflows, configuration, CLAUDE.md or
ADR-0014 changed.

Planned before commit: four-path scope, prefix, links/anchors, privacy/artifacts,
cached whitespace, staged Gitleaks and identity checks. Commit subject: "docs: record
accepted embedding persistence specification", with the repository's
Co-Authored-By Claude trailer. After the commit: verify the parent, the four paths,
full-history Gitleaks, a clean tree, and main/origin/main unchanged. Actual results
and the commit SHA are reported in the handoff, not recorded here. No push, merge or
implementation.

**Prompt 116 outcome (recorded in Prompt 117 by Claude Code):** committed locally as
e5ed17e7638bf2a223d08e6fc22a2cba6f3c758e (parent
5fdaa1cecbcac876af007e6f4328436ef6faeda2, tree
1ea9ff391f2627a8e8f486c452c568bd5b4f793d) on docs/m4b-persistence-spec. Subject:
"docs: record accepted embedding persistence specification", with the noreply author
and committer and a Co-Authored-By Claude trailer. Exactly README.md, ADR-0013,
docs/plan.md and prompts.md were committed. Pre-commit checks passed: four-path scope,
identical history prefix, 103 links and anchors, privacy, cached whitespace and staged
Gitleaks. After the commit, full-history Gitleaks scanned 49 commits and found no leaks,
the tree was clean, and main/origin/main were unchanged at 5fdaa1c. Nothing was pushed.
The acceptance diff .local/p116/m4b-spec-acceptance.diff was 19,049 bytes, SHA-256
6ccbc138e290ff593eab954084ac470580ffbc1a501aa7fff2e3b00b6ae910ea.

**Prompt 116 review (recorded in Prompt 117):** the external reviewer accepted the
Prompt 116 incremental diff after independently matching its SHA-256. No new project
checks were run by the reviewer.

## Prompt 117: Implement the accepted M4b embedding persistence specification

- **Date:** 2026-10-16 (Asia/Bangkok).
- **Session:** Claude Code.
- **Scope/status:** implementation staged for external review; no commit or publication.

````text
Written for: Mathew and the external reviewer.

Prompt 117 — Implement the accepted M4b embedding persistence specification. Stage for external review; do not commit or publish.

Read CLAUDE.md, applicable repository instructions, the accepted M4b specification in docs/plan.md, ADR-0013 and existing persistence/fencing conventions. Avoid reloading full prompt history or printing diffs.

1. Verify starting state

Expected:
- Branch: docs/m4b-persistence-spec.
- HEAD:
  e5ed17e7638bf2a223d08e6fc22a2cba6f3c758e.
- Parent:
  5fdaa1cecbcac876af007e6f4328436ef6faeda2.
- Working tree clean.
- Local main and origin/main:
  5fdaa1cecbcac876af007e6f4328436ef6faeda2.
- Expected origin and noreply identity unchanged.

Stop on material mismatch. Record the baseline under .local/p117/.

Create feat/embedding-persistence from HEAD if it does not exist. Do not overwrite an existing branch. The local specification commit remains beneath this branch; do not publish it separately.

2. Implement the accepted specification

Implement M4b only:
- pure canonical storage values and validation;
- the small in-repo SQLAlchemy vector type and reflection support;
- embedding profiles, indexes and rows;
- migration 0005;
- generated full-text representation;
- metadata creation, bounded fenced writes and readiness/completeness verification;
- meaningful database-independent and real PostgreSQL tests;
- ADR-0014 and truthful implementation-status documentation.

Follow the exact accepted schema, composite constraints, NOT NULL rules, identity bindings, UUID namespaces, numeric format and digest rules. Record literal namespace constants and independent fixtures.

No new Python dependency. Do not change uv.lock.

A. Numeric boundary
- Validate M4a provider values first.
- Canonicalize float32 and negative zero exactly as specified.
- Revalidate the stored representation; do not renormalize or widen tolerance.
- Validate the complete batch before its write helper issues SQL.
- Preserve fixed, privacy-safe errors.
- Equality and replay comparisons concern canonical stored values, not float64 provider values.
- Pin binary-send/digest fixtures and test the accepted lower-norm rounding rejection.
- Do not change the accepted M4a contract to make storage validation pass.

B. Persistence and fencing
- Profiles and indexes are tenant-scoped with the accepted composite FKs and unique keys.
- Metadata creation uses the caller's transaction; no production caller is wired yet.
- Vector writes/readiness require the real job fence, kind index_revision and exactly the validated index_id payload.
- Look up and lock the index only within the job tenant.
- Respect job → index lock order.
- Recheck fresh ownership after waits on every successful path, including no-ops.
- Reject writes to ready indexes.
- Compare replayed immutable fields; never overwrite conflicting rows.
- Completeness checks exact source membership/manifests, profile identity and stored-vector manifest, not count alone.
- Reuse the accepted public chunk query/manifest helpers without changing M3 activation locking.
- Readiness and job success must be capable of committing atomically through the existing fence.
- No unfenced production vector-write or readiness bypass for tests.

C. Migration and full text
- Match models and migration exactly.
- Create vector only in migration 0005, using IF NOT EXISTS.
- Downgrade removes this migration's own objects and always preserves vector.
- No extension-drop logic, ownership marker or CASCADE in the migration.
- Preserve offline upgrade/downgrade rendering.
- Use the accepted explicit simple text configuration.
- Do not change chunk text, IDs, source spans or ingestion behaviour.
- Do not add HNSW/IVFFlat indexes.

If the specification proves impossible or internally inconsistent, report the concrete issue before redesigning it.

3. Files and scope

Expected new files:
- packages/domain/evidenceguard_domain/embedding_storage.py
- packages/persistence/evidenceguard_persistence/embeddings.py
- packages/persistence/evidenceguard_persistence/migrations/versions/v0005_embeddings.py
- tests/test_embedding_storage.py
- tests/test_embedding_store.py
- a dedicated marked PostgreSQL embedding-persistence test module
- docs/decisions/0014-embedding-persistence.md, if that number is available

Update existing models, integration fixtures, migration/schema/head expectations and safety-test references only as required by the accepted specification.

README, plan, relevant threat-model statements and prompts.md may be updated truthfully. Explain any additional file change.

No live adapter, provider calls, indexing handler, enqueue/backfill command, worker registration, retrieval service/API, corpus evaluation or M4c implementation.

Do not change workflows, Compose or Dockerfile merely to avoid a failing check. Report any concrete necessary change for review.

4. Meaningful tests

Implement the accepted test plan, including:
- independent float32/wire/digest/UUID fixtures;
- strict storage-value validation and private errors;
- statement/protocol checks, explicitly distinguished from database evidence;
- real composite-FK and required-NULL rejection;
- numeric CHECKs, offline zero policy and stored-byte equality;
- application/database agreement on canonical vectors;
- bounded batch writes, no-op replay and conflicting replay;
- partial/incomplete indexes and ready-state immutability;
- job kind/payload/tenant binding;
- stale leases, concurrent writers, lock timeout and stale already-ready no-op;
- transactional rollback and atomic readiness/job success;
- generated full-text correctness;
- migration up/down/up, extension retention and unrelated-object survival;
- reflection/alembic drift and offline SQL.

Use real enqueue, claim and fenced transactions for PostgreSQL cases. Ensure event/barrier tests assert their interleaving actually occurred and have bounded waits.

Preserve the disposable-database guard. Fixture reset may need the accepted assertion or test-only extension cleanup; do not weaken safety or assume downgrade removes vector.

5. Verification

Use existing locked project commands for:
- focused database-independent tests;
- Ruff format/lint;
- strict mypy;
- full local suite;
- integration-test collection without executing against a database;
- distribution build and clean installed-wheel checks;
- offline migration rendering;
- git diff --cached --check;
- staged Gitleaks without suppression;
- private-content/artifact checks and documentation links.

For installed-wheel verification, directly import the new modules and M4a embedding provider using isolated Python outside the source checkout. Verify module paths resolve to site-packages, run a small offline hashing/canonicalization check and render migration SQL without a database. This may close the previously documented embedding-specific wheel limitation only if it actually passes.

Normal locked environment setup and the project's existing declared build-backend resolution are authorized. Do not add dependencies, change lockfiles, bypass release-age policy or install tools globally. If a prerequisite remains unavailable, report the blocked check accurately.

No local Docker, database contact or live provider calls. PostgreSQL tests are written and collected only; they remain unverified until authorized CI.

6. Documentation and prompt history

Record implementation as staged and awaiting review. Separate checks run locally from PostgreSQL/Linux/CI checks still pending.

Preserve the accepted specification and historical evidence. Explain implementation deviations, if any. Do not claim retrieval, semantic quality or overall M4 completion.

Append:
- Prompt 116 outcome;
- reviewer acceptance of its incremental diff, checksum independently matched, no new project checks;
- Prompt 117 verbatim;
- truthful outcome note.

Preserve earlier prompt-history bytes.

7. Stage and export

Stage only relevant source, migration, tests and documentation. No .local/, distributions, environments, caches or build artifacts.

Export the complete staged diff against HEAD, excluding prompts.md:
.local/p117/m4b-implementation.diff

UTF-8 without BOM. Report baseline commit, final staged tree, paths, statistics, byte size and SHA-256. Do not print the diff.

Handoff: implementation summary, deviations/questions, actual checks and skip accounting, unexecuted PostgreSQL tests, final Git state and export metadata.

No commit, push, merge, amend, rebase, tag, branch deletion or M4c work.

Return this output plus .local/p117/m4b-implementation.diff to the external reviewer.
````

**Prompt 117 outcome (Claude Code; implementation staged for external review, not
committed):** verified docs/m4b-persistence-spec at e5ed17e (parent 5fdaa1c), a clean
tree, local main and origin/main at 5fdaa1c, and the expected origin and noreply
identity. Created feat/embedding-persistence from HEAD; baseline saved under .local/p117/.

Implemented M4b per the accepted specification, as documented in ADR-0014:
- pure canonical storage values (float32 rounding, `-0.0` canonicalization,
  post-rounding revalidation with no renormalization, wire bytes and digests, UUID5
  IDs, whole-batch validation before SQL);
- an in-repo `Vector` type with reflection registration;
- three tenant-scoped tables with composite FKs, NOT NULL and pgvector-backed CHECKs;
- two FK-target keys and a generated `simple` tsvector with a GIN index on existing
  tables;
- migration 0005 (`IF NOT EXISTS` extension; the downgrade keeps the extension, with
  no CASCADE);
- caller-transaction metadata creation;
- fenced writes and readiness with job binding, job → index locks and fresh ownership
  re-checks on every successful path.

Implementation choices within the specification are recorded in ADR-0014: namespace
literals, explicit constraint names, a nullable generated column, a local migration
DDL type, reflection registration, additional fixed errors and the tolerance edges.
Existing tests were updated only for head 0005, table sets, the extension expectation,
the renamed extension test and its safety reference, and the readiness heads. The
`empty_database` fixture gained the accepted plpgsql-only assertion. No source outside
M4b, dependency, lockfile, workflow, Compose, Dockerfile or threat-model change was made.

Local Windows checks actually run (locked environment, offline, no sync):
- Ruff format and lint, strict mypy (113 files): clean;
- focused embedding tests: 102 passed;
- full suite: 1585 passed, 234 skipped (233 integration tests without a database,
  one POSIX-only signal test);
- integration collection: 233 collected (29 in tests/test_embeddings_postgres.py);
- `uv build`: succeeded;
- clean installed-wheel checks outside the checkout, with dependencies from uv.lock
  and the wheel with `--no-deps`: the existing CI checks plus direct site-packages
  imports and execution of the M4a provider and M4b canonicalization, and offline
  upgrade/downgrade SQL, all passed.

That closes the embedding-specific wheel limitation locally on Windows only; CI's
wheel step is unchanged. PostgreSQL, Linux, container and CI checks have not run:
constraints, migration, numeric storage, reflection, fixture reset, extension lifecycle
and concurrency remain unverified. No Docker, database or provider contact. No
retrieval, semantic-quality or overall M4 claim. Staged-scope, whitespace, Gitleaks,
privacy and link results are reported in the handoff, not pre-recorded here.

**Prompt 117 outcome (recorded in Prompt 118, from Claude Code's Prompt 117 handoff):** M4b was
implemented on `feat/embedding-persistence` from `e5ed17e` and staged, not committed: 16 paths
in staged tree `7c2ec10f4792abb710e611afd4be34b7c7c2b853`. Local Windows checks reported in
that handoff:
- Ruff format and lint, strict mypy (113 files): clean;
- focused embedding tests: 102 passed;
- full suite: 1585 passed, 234 skipped (233 PostgreSQL/integration tests without a database,
  one POSIX-only signal test);
- integration collection: 233 collected (29 in `tests/test_embeddings_postgres.py`);
- `uv build`: succeeded;
- clean installed-wheel checks in an isolated venv outside the checkout, including direct
  embedding-provider and M4b storage execution: passed;
- cached whitespace check, staged Gitleaks, links, encoding and privacy checks: passed.

No PostgreSQL, Linux, container or CI check ran. The export
`.local/p117/m4b-implementation.diff` was 196,203 bytes, SHA-256
`47687999bb849967aedd1005494b1b43a4116536ea14a2f8ff4e1e1c50db8a4d`.

**Prompt 117 review (recorded in Prompt 118):** the external reviewer inspected the complete
Prompt 117 implementation diff and independently matched its SHA-256
`47687999bb849967aedd1005494b1b43a4116536ea14a2f8ff4e1e1c50db8a4d`. The reviewer also inspected
the existing M3 chunk-store and job-fence source. Independent standard-library probes passed
for wire encoding and digests, both float32 norm boundaries, the accepted lower-boundary
rejection, invalid numeric inputs and 200 seeded vector round trips. The reviewer did not run
the project suite, installed-wheel checks, PostgreSQL or Docker; acceptance also rests on
Claude Code's reported Prompt 117 verification. The M4b implementation and its recorded
implementation choices are accepted for a local commit, with documentation corrections. This
does not establish PostgreSQL behaviour, current-version CI verification or overall M4
acceptance.

## Prompt 118: Record M4b implementation acceptance and commit locally

- **Date:** 2026-10-16 (Asia/Bangkok).
- **Session:** Claude Code.
- **Scope:** documentation corrections and a local commit; no publication.

````text
Written for: Mathew and the external reviewer.

# Prompt 118: Record M4b implementation acceptance and commit locally

Read CLAUDE.md and any applicable repository instructions. Preserve the existing session preference: this session began at Prompt 114; a new session is not needed merely for this task.

The external reviewer inspected the complete Prompt 117 implementation diff and independently matched its SHA-256:
`47687999bb849967aedd1005494b1b43a4116536ea14a2f8ff4e1e1c50db8a4d`.

The reviewer also inspected the existing M3 chunk-store and job-fence source. Independent standard-library probes passed for wire encoding and digests, both float32 norm boundaries, the accepted lower-boundary rejection, invalid numeric inputs, and 200 seeded vector round trips.

The reviewer did not run the project suite, installed-wheel checks, PostgreSQL or Docker. Acceptance also rests on Claude Code's reported Prompt 117 verification.

The M4b implementation and its recorded implementation choices are accepted for a LOCAL COMMIT, with the documentation corrections below. This does not establish PostgreSQL behaviour, current-version CI verification or overall M4 acceptance.

## 1. Verify the starting state

Expected:
- Branch: `feat/embedding-persistence`.
- HEAD: `e5ed17e7638bf2a223d08e6fc22a2cba6f3c758e`.
- HEAD parent: `5fdaa1cecbcac876af007e6f4328436ef6faeda2`.
- Staged tree: `7c2ec10f4792abb710e611afd4be34b7c7c2b853`.
- Exactly the same 16 staged paths as Prompt 117:
  - README.md
  - docs/decisions/0014-embedding-persistence.md
  - docs/plan.md
  - packages/domain/evidenceguard_domain/embedding_storage.py
  - packages/persistence/evidenceguard_persistence/embeddings.py
  - packages/persistence/evidenceguard_persistence/migrations/versions/v0005_embeddings.py
  - packages/persistence/evidenceguard_persistence/models.py
  - tests/conftest.py
  - tests/test_embedding_storage.py
  - tests/test_embedding_store.py
  - tests/test_embeddings_postgres.py
  - tests/test_persistence.py
  - tests/test_persistence_postgres.py
  - tests/test_persistence_safety.py
  - tests/test_readiness.py
  - prompts.md
- Nothing unstaged or untracked outside ignored local artifacts.
- Local main and origin/main remain at `5fdaa1cecbcac876af007e6f4328436ef6faeda2`.
- Origin remains `https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git`.
- Effective author and committer:
  `mathewmljourney93 <257921624+mathewmljourney93@users.noreply.github.com>`.

Use local checks. No fetch or remote mutation is required for this local documentation-and-commit task.

If the state differs materially, stop and report it without overwriting work.

Before editing, record the accepted staged tree and necessary baseline evidence under `.local/p118/`.

## 2. Documentation changes only

Only these files may change from the accepted staged tree:
- README.md
- docs/decisions/0014-embedding-persistence.md
- docs/plan.md
- prompts.md

Every other staged file must remain byte-identical to the accepted tree.

### Correct two stale README statements

1. In “Milestone record and remaining work”, the sentence currently says M4b is implemented and staged, then says “M4b–M4f remain unimplemented”.

   Correct that remaining range to M4c–M4f, while applying the local acceptance status described below.

2. The “Remaining after M3” bullet still lists direct embedding-provider execution from an isolated installed wheel as generally unverified.

   Replace that with the precise remaining limitation:
   - direct embedding-provider execution and the new storage modules were verified from an isolated installed wheel locally on Windows in Prompt 117;
   - the existing CI installed-wheel step does not exercise embeddings directly;
   - adding equivalent embedding-specific CI wheel coverage remains a possible follow-up.

Do not imply the reviewer independently ran the wheel checks, or that CI already contains this additional check.

### Record narrow implementation acceptance

Update the current M4b status in README, the plan and ADR-0014 to say:
- accepted at external review in Prompt 118 for a local commit;
- PostgreSQL and current-version Linux/CI verification remain pending;
- no publication or merge is authorized or completed by this task;
- the 29 new PostgreSQL tests are written and collected but have never executed;
- all 233 integration tests remain unverified against this implementation;
- M4c–M4f and overall M4 acceptance remain pending;
- local Compose remains unverified.

ADR-0014 may change from its staged-review status to Accepted, explicitly scoped to this local implementation acceptance and pending CI.

Keep the historical Prompt 117 results and their attribution:
- focused tests: 102 passed;
- full local Windows suite: 1585 passed, 234 skipped;
- skips: 233 PostgreSQL/integration tests plus one POSIX-only signal test;
- build and isolated installed-wheel checks passed locally on Windows.

Do not turn those historical results into newly executed checks or CI evidence.

Preserve:
- the accepted specification and its existing anchor;
- schema, numeric, fencing and extension-lifecycle decisions;
- the recorded implementation choices;
- migration retention of the vector extension;
- all application code, tests, migrations and configuration;
- the distinction between local wheel verification and CI coverage.

Do not add embedding-specific CI work in this task.

## 3. Append prompt history accurately

Preserve all earlier committed and staged prompt-history bytes as an identical prefix.

Append:
- the Prompt 117 outcome, attributed to its handoff;
- a reviewer acceptance note containing the exact review scope and independent probes described above;
- Prompt 118 verbatim;
- a pre-commit note recording the verified state, permitted changes and checks actually performed.

Do not claim the reviewer ran the project suite, PostgreSQL, installed-wheel checks or Docker.

Do not pre-record the new commit's SHA, publication or CI outcomes.

Use inline, backticked commit identifiers in your own notes to avoid the previously encountered Gitleaks false positive.

## 4. Verify before committing

Run the relevant documentation and commit checks:
- exactly the expected 16 paths remain staged;
- only the four permitted documentation/history files differ from accepted tree `7c2ec10f4792abb710e611afd4be34b7c7c2b853`;
- every other file is byte-identical;
- earlier prompts.md bytes are unchanged;
- relative links and anchors resolve;
- current status statements are consistent;
- no private content, credentials, artifacts, CR characters or BOM were introduced;
- `git diff --cached --check`;
- staged Gitleaks, without allowlisting or suppression;
- effective author and committer identity.

Application tests and builds need not be repeated because implementation files must remain byte-identical. Do not install dependencies, contact a database or provider, or run Docker.

If a check fails, correct only an authorized documentation issue. Stop for an unexpected implementation or security finding.

## 5. Commit locally

Commit the complete reviewed M4b implementation and the authorized documentation/history changes with subject:

`feat: add tenant-scoped embedding persistence and index readiness`

Use the expected noreply author and committer. Follow the repository's existing Claude Code attribution convention.

After committing, verify:
- parent is `e5ed17e7638bf2a223d08e6fc22a2cba6f3c758e`;
- exactly the expected 16 paths were committed;
- every file outside the four permitted documentation/history paths is byte-identical to the accepted tree;
- working tree is clean;
- main and origin/main are unchanged;
- full-history Gitleaks passes without suppression.

No push, merge, amend, rebase, tag, branch deletion, M4c implementation or other work is authorized.

## 6. Export and hand off

Export an incremental diff directly from Git:
- baseline: accepted tree `7c2ec10f4792abb710e611afd4be34b7c7c2b853`;
- final: the new local commit;
- exclude prompts.md;
- path: `.local/p118/m4b-commit-incremental.diff`;
- UTF-8 without BOM.

Do not print the complete diff in chat.

Report:
- commit SHA, parent and tree;
- identity and attribution;
- committed paths;
- concise documentation changes;
- checks actually run;
- byte-identity result;
- historical verification and remaining limitations;
- final Git state;
- export baseline, final commit, paths, statistics, byte size and SHA-256.

End with this explicit instruction:

Mathew: return this output plus `.local/p118/m4b-commit-incremental.diff` to the external reviewer.
````

**Prompt 118 pre-commit note (Claude Code; written before the commit):** verified locally, without
a fetch:
- branch `feat/embedding-persistence`, HEAD `e5ed17e`, parent `5fdaa1c`;
- accepted staged tree `7c2ec10f4792abb710e611afd4be34b7c7c2b853` with exactly the 16
  expected paths, and nothing unstaged or untracked;
- local main and origin/main at `5fdaa1c`;
- the expected origin and noreply author/committer.

The accepted tree, paths, blobs and history prefix are recorded under `.local/p118/`.

Only README.md, ADR-0014, docs/plan.md and this history changed:
- README: the remaining range is corrected to M4c–M4f, and "Remaining after M3" now states
  the precise wheel limitation (local Windows verification in Prompt 117, CI's wheel step not
  exercising embeddings, equivalent CI coverage a possible follow-up).
- README, plan and ADR-0014 record acceptance for a local commit in Prompt 118. No
  publication or merge; the 29 new PostgreSQL tests never executed; all 233 integration tests
  unverified against it; PostgreSQL and current-version Linux/CI pending; M4c–M4f and overall
  M4 pending; local Compose unverified.
- The plan's top-level status and a stale M3-section status line were also corrected; the
  latter is now marked historical.

The Prompt 117 results stay historical and attributed. The accepted specification, its anchor
and all code, tests, migrations and configuration are unchanged.

Checks planned before the commit: 16-path scope, byte identity of the twelve other files
against the accepted tree, history prefix, links and anchors, status consistency,
privacy/CR/BOM, cached whitespace, staged Gitleaks and identity. Application tests and builds
are not repeated, because implementation files are byte-identical. Actual results and the
commit SHA are reported in the handoff, not recorded here. No push, merge or M4c work.

**Prompt 118 outcome (recorded in Prompt 119, from Claude Code's Prompt 118 handoff):** committed
locally as `691a44c7e7200d72f701843feb885ff65a5916c0` (parent
`e5ed17e7638bf2a223d08e6fc22a2cba6f3c758e`, tree `59dc7e0b5829b85fb2ae3d3a3cc0648d5f122ca2`) on
`feat/embedding-persistence`. Subject: "feat: add tenant-scoped embedding persistence and index
readiness", with the noreply author and committer and a Co-Authored-By Claude trailer.

Exactly the 16 accepted paths were committed. Only README.md, ADR-0014, docs/plan.md and
prompts.md differed from accepted tree `7c2ec10f4792abb710e611afd4be34b7c7c2b853`; the other 12
files were byte-identical. Checks that passed:
- the history prefix;
- 112 links and anchors;
- privacy, CR and BOM;
- the cached whitespace check;
- staged Gitleaks;
- full-history Gitleaks after the commit (50 commits, no leaks).

The tree was clean, main/origin/main were unchanged at `5fdaa1c`, and nothing was pushed. The
incremental diff `.local/p118/m4b-commit-incremental.diff` was 24,389 bytes, SHA-256
`a68f11ab343a53af78efc378bb683e958605711eed772e1672a1fdfc5a2aa671`.

**Prompt 118 review (recorded in Prompt 119):** the external reviewer inspected the complete
Prompt 118 incremental diff and independently matched its SHA-256
`a68f11ab343a53af78efc378bb683e958605711eed772e1672a1fdfc5a2aa671`. The documentation changes
are accepted. The reviewer ran no additional application tests, builds, PostgreSQL or Docker
checks.

## Prompt 119: Publish the M4b feature branch and verify exact-commit CI

- **Date:** 2026-10-16 (Asia/Bangkok).
- **Session:** Claude Code.
- **Scope:** prompt-history commit, publication of `feat/embedding-persistence` only, and
  exact-commit CI monitoring. No merge or main update.

````text
Written for: Mathew and the external reviewer.

# Prompt 119: Publish the M4b feature branch and verify exact-commit CI

Read CLAUDE.md and applicable repository instructions. Continue the current session; this is its sixth substantial prompt, so no session switch is needed on that count.

The external reviewer inspected the complete Prompt 118 incremental diff and independently matched its SHA-256:
`a68f11ab343a53af78efc378bb683e958605711eed772e1672a1fdfc5a2aa671`.

The documentation changes are accepted. The reviewer ran no additional application tests, builds, PostgreSQL or Docker checks.

Authorize publication of ONLY `feat/embedding-persistence`, including the accepted specification commit, implementation commit and the prompt-history commit described below. Do not merge or update main.

## 1. Verify the starting state

Expected:
- Branch: `feat/embedding-persistence`.
- HEAD: `691a44c7e7200d72f701843feb885ff65a5916c0`.
- Parent: `e5ed17e7638bf2a223d08e6fc22a2cba6f3c758e`.
- HEAD tree: `59dc7e0b5829b85fb2ae3d3a3cc0648d5f122ca2`.
- Working tree clean, with nothing staged, unstaged or untracked outside ignored local artifacts.
- No upstream or remote branch for `feat/embedding-persistence`.
- Local main and origin/main:
  `5fdaa1cecbcac876af007e6f4328436ef6faeda2`.
- Origin:
  `https://github.com/mathewmljourney93/evidenceguard-agentic-rag.git`.
- Effective author and committer:
  `mathewmljourney93 <257921624+mathewmljourney93@users.noreply.github.com>`.

Fetch fresh remote refs and inspect them read-only. Confirm:
- remote main remains at the expected commit;
- remote main is an ancestor of HEAD;
- the remote feature branch does not exist.

Record baseline evidence under `.local/p119/`.

If the expected state differs materially, stop and report the mismatch without overwriting work or publishing anything.

## 2. Publication preflight

Inspect everything that would become public relative to fresh remote main.

Expected existing commits:
- `e5ed17e7638bf2a223d08e6fc22a2cba6f3c758e`: accepted M4b specification.
- `691a44c7e7200d72f701843feb885ff65a5916c0`: reviewed M4b implementation.

Check:
- intended paths and identities;
- no tracked local artifacts, backups, bundles, build outputs, credentials or real environment files;
- private-content and secret scans over the publication range;
- no unexpected dependency, lockfile, workflow, Compose or Dockerfile changes.

The unchanged, placeholder-only `.env.example` is permitted.

Inspect the workflows and confirm the five required jobs still run on this branch's push:
1. Ubuntu verification.
2. Windows verification.
3. PostgreSQL integration with `EG_REQUIRE_INTEGRATION=1`.
4. Container verification.
5. Full-history Gitleaks.

Confirm the integration command collects the new M4b module through the existing integration marker. Do not modify workflows or tests.

## 3. Append history and commit it

Modify only prompts.md.

Preserve all earlier bytes as an identical prefix. Append:
- the Prompt 118 local-commit outcome, attributed to its handoff;
- the reviewer's acceptance of the incremental diff and independently matched checksum;
- Prompt 119 verbatim;
- a preflight note stating the verified publication scope and authorization.

Keep historical verification distinct:
- Prompt 117 Windows: 1585 passed, 234 skipped.
- Those skips were 233 integration tests and one POSIX-only signal test.
- The 29 new M4b PostgreSQL tests have never executed.
- All 233 integration tests remain unverified against M4b before this CI run.
- Direct embedding-provider and storage execution from an isolated installed wheel passed locally on Windows only.
- CI's existing wheel checks do not exercise embeddings directly.

Do not pre-record push results, CI outcomes or the new commit's own SHA.

Check:
- prompts.md prefix unchanged;
- only prompts.md staged;
- no private content;
- `git diff --cached --check`;
- staged Gitleaks without suppression;
- expected author and committer.

Commit with subject:
`docs: record M4b branch publication authorization`

Follow the repository's existing Claude Code attribution convention.

Verify the new commit:
- parent is `691a44c7e7200d72f701843feb885ff65a5916c0`;
- changes only prompts.md;
- all other files remain byte-identical;
- working tree is clean.

Run full-history Gitleaks before pushing. Stop if any required preflight or scan fails.

## 4. Publish only the feature branch

Run directly, preserving git's actual exit status:

git push --set-upstream origin refs/heads/feat/embedding-persistence:refs/heads/feat/embedding-persistence

No force-push, tags or other refs.

Record the exact published commit and confirm the remote feature ref equals it. Confirm remote main is unchanged.

If git reports a network failure, inspect the remote before considering one retry of the identical authorized command. Do not mask failures through a pipeline or retry indefinitely.

## 5. Monitor exact-commit CI

Monitor push-triggered workflow runs for:
- this repository;
- `feat/embedding-persistence`;
- the exact published head commit.

Use a maximum overall monitoring window of 25 minutes. Poll at reasonable intervals and leave no background polling running afterward.

Require all five jobs to succeed. For the container job, confirm these required steps actually executed and succeeded, rather than being skipped:
- rendered Compose configuration;
- effective build context;
- application image build;
- runtime image checks;
- Compose smoke;
- cleanup.

Retrieve job logs using available access if possible. Do not add credentials, change account configuration or request new privileges.

From retrieved logs, report actual observations:
- Ubuntu and Windows pytest summaries;
- PostgreSQL pytest summary;
- whether the M4b integration module ran, to the extent the logs establish it;
- migration/reflection or fixture failures, if any;
- build and existing installed-wheel results;
- container context, image, smoke and cleanup output;
- Gitleaks commit count and result.

Do not treat the expected 233 integration tests as an observed count unless the logs confirm it. Do not claim unchanged CI wheel checks directly executed embeddings.

If logs are unavailable, report job and step conclusions separately from unobserved counts and output.

If any job fails, is cancelled, is unexpectedly skipped, or monitoring times out:
- stop and report the exact state and available failure evidence;
- do not change code, fixtures, migrations, workflows or dependencies;
- do not commit a repair, rerun workflows or publish another commit.

In particular, a fixture-reset, extension-lifecycle or vector-reflection failure needs a subsequent reviewed correction. This prompt authorizes verification, not implementation repairs.

## 6. Final handoff

Do not update documentation after CI in this task.

Report concisely:
- starting-state and preflight results;
- history commit SHA, parent, identity and changed path;
- checks actually run;
- push command and actual exit status;
- exact published SHA;
- workflow and job links, event, branch, head commit and conclusions;
- required container-step conclusions;
- observed log results and anything unobserved;
- final local/remote refs and working-tree state;
- remaining verification or failures.

Do not rerun local application tests, builds, Docker or database operations. CI performs the authorized verification.

Do not merge, update main, amend, rebase, tag, delete branches, start M4c or mark overall M4 accepted.

End with:

Mathew: return this output only to the external reviewer; no diff attachment is required.
````

**Prompt 119 preflight note (Claude Code; written before the history commit and push):**

Verified state, from fresh remote refs:
- `feat/embedding-persistence` at `691a44c` (parent `e5ed17e`, tree `59dc7e0`), clean;
- no upstream or remote feature branch;
- local main, origin/main and remote main at `5fdaa1c`, an ancestor of HEAD;
- the expected origin and noreply author/committer.

The publication scope relative to remote main is `e5ed17e` (accepted M4b specification),
`691a44c` (reviewed M4b implementation) and this prompt-history commit, all with the noreply
identity. Preflight results:
- 17 intended paths, with no dependency, lockfile, workflow, Compose or Dockerfile change;
- no tracked artifacts, backups, bundles, builds or real environment files (only the unchanged,
  placeholder `.env.example`);
- Gitleaks over the range and the private-content scan: clean;
- both workflows trigger on any branch push, with no branch filters;
- the five jobs are Ubuntu and Windows verification, PostgreSQL integration
  (`pytest -m integration`, `EG_REQUIRE_INTEGRATION=1`), the container job and full-history
  Gitleaks;
- `tests/test_embeddings_postgres.py` is marked `integration`.

Authorization: publish only `feat/embedding-persistence`, with no merge or main update.

Historical verification, kept distinct:
- Prompt 117 Windows: 1585 passed, 234 skipped (233 integration tests and one POSIX-only signal
  test).
- The 29 new M4b PostgreSQL tests have never executed, and all 233 integration tests remain
  unverified against M4b before this CI run.
- Direct embedding-provider and storage execution from an isolated installed wheel passed
  locally on Windows only; CI's existing wheel checks do not exercise embeddings directly.

Push results and CI outcomes are reported in the handoff, not recorded here.
