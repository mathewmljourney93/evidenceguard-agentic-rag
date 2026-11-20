# AGENTS.md

Working agreement for any AI agent (and any person) working in this repository. Read it in
full before changing anything. `CLAUDE.md` only points here.

**Precedence.** This file governs how work is done here. A safety floor sits on top and
nothing here relaxes it: agents never deploy anything; no secrets in the repo, in chat or in
output; no force push and no rewriting pushed history; security findings stay private until
the fix has merged; nobody claims a verification level they did not reach; standard and
critical work gets an independent review. A rule change is its own PR.

## What this project is

EvidenceGuard is an auditable multi-agent RAG service for vendor risk review: Python 3.12,
FastAPI (`apps/api`), a durable PostgreSQL job worker (`apps/worker`), and shared packages
under `packages/` (domain, persistence, retrieval, agents, observability). PostgreSQL 17 with
pgvector. It is a portfolio project. It has no production deployment and none is planned.
The data is synthetic.

People:

- **Mathew** [`mathewmljourney93`] owns the repository, decides scope and is the only human.
- **The orchestrator** is the Claude session working with Mathew. It plans, briefs agents,
  integrates their results and merges under the rule below.
- **Builder, reviewer, security reviewer, scout and checker agents** each do one job from a
  written brief. A reviewer never sees the build process.

## Rules and their mechanisms

| Rule | Mechanism | In force since | Status |
| ---- | --------- | -------------- | ------ |
| Nothing lands on `main` directly | branch protection: pull request required, required checks below, no force push, no deletion | 2026-11-20 | on |
| Suites run on every PR | `.github/workflows/ci.yml` (verify on Ubuntu and Windows, PostgreSQL integration, container build and Compose smoke) | before this agreement | on |
| Secret scan over the whole history | `.github/workflows/secret-scan.yml` (Gitleaks) | before this agreement | on |
| Merge commits only | merges done with the merge-commit method; squash and rebase merging disabled in settings | 2026-11-20 | on |
| Agents never deploy | there is no deploy path in this repository | always | n/a |

## How work flows

1. **Every change is a branch and a pull request**, cut from freshly fetched `main`.
   Branch names: `<type>/<topic>` (`feat`, `fix`, `docs`, `test`, `chore`, `refactor`).
2. **Every PR carries a tier** in its body:
   - `standard`: a feature inside existing patterns. Plan file `docs/plans/<branch>.md`
     (branch name with `/` replaced by `-`).
   - `critical`: a migration, authentication or roles, API routes, model or other paid API
     calls, uploads, CI or this file, anything cross-package or hard to undo. Plan file
     written by the most capable model.
   - `small` is not used here: there is no second human to merge a small PR, so every
     change gets at least the standard review.
3. **Plan before code.** The plan is committed on the branch. If the code diverges, update
   the plan first. A choice with lasting consequences where the obvious alternative was
   reasonable gets an ADR in `docs/decisions/` with a "why not" table.
4. **Reuse first.** Search before building and name what you found in the plan. One home
   per capability: model calls through `evidenceguard_agents` call boundaries; tenancy and
   authentication through the API's existing dependencies; persistence through
   `evidenceguard_persistence`.
5. **Independent review.** A fresh reviewer agent that never saw the build reviews every PR
   against its plan and gives one verdict line: `VERDICT: ready | changes needed | do not
   merge`. A security reviewer also reviews any change that touches authentication, roles,
   routes, migrations, uploads, model calls, input handling, secrets or outbound requests.
   After a send-back, the same reviewer re-reviews. The PR body's Review record carries only
   the canonical lines, never finding details.
6. **Done** means the affected suites and the full CI show no failure, with counts in the
   PR body. **Integration-verified** means done and exercised for real, with evidence
   matched to the change (migration applied from the previous head and invariants checked;
   API path called end to end against PostgreSQL). Say which level was reached.
7. **Merge.** Mathew authorised in writing (2026-11-20, in the working session) that the
   orchestrator may merge a PR to `main` itself, with a merge commit, only when all of these
   hold on the exact head commit: the independent review gave `VERDICT: ready`; the security
   review, when triggered, found nothing open; every CI check is green; every PR comment was
   read. Otherwise the PR stays a draft. Every merge gets a one-line merge note.

## Safety

- No real vendor, client or personal data. Synthetic data only.
- Never print, echo or commit a credential. Live provider keys live only in the gitignored
  `.env` or the shell environment, never in a file under version control. Placeholders are
  obviously fake.
- Live model calls (Anthropic, Voyage) run only inside a spend limit Mathew has set, and
  their results are committed as run records, never as keys or raw secrets.
- Stage explicit paths; never `git add -A` or `git add .`.
- Never force push. Once a branch is pushed, bring `main` in with `git merge main`.
- Security findings go to Mathew in chat and stay out of the repository until the fix has
  merged.

## Local verification

- `uv sync --locked` then `uv run --locked pytest` (database tests skip without a database).
- Database tests: point `EG_TEST_DATABASE_URL` at a disposable PostgreSQL 17 + pgvector
  database, then `uv run --locked pytest -m integration`.
- Lint and types: `uv run --locked ruff check .`, `uv run --locked ruff format --check .`,
  `uv run --locked mypy` (see `pyproject.toml`).

## Where things are recorded

- Plans: `docs/plans/`. Decisions: `docs/decisions/`. Changes: `CHANGELOG.md`.
- Status lives in PR bodies and the CHANGELOG, never in the README.
- Scratch files go under `.local/`, which is gitignored.
- `prompts.md` and the long status sections of `docs/plan.md` are historical. Do not append
  to them.
