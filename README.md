# EvidenceGuard: Auditable Multi-Agent RAG for Vendor Risk Review

EvidenceGuard is a planned vendor-risk review copilot. It is intended to:

- ingest synthetic vendor documents for one tenant at a time;
- retrieve only evidence that tenant is authorized to see, with provenance;
- identify supported answers, contradictions and missing information;
- draft a report in which every claim cites its evidence;
- require a human to approve the exact draft revision before it can be finalized or exported.

It is evidence-based decision support, not legal advice or compliance certification.

## Status: milestone M1c (pre-alpha)

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
- Tests, Ruff and strict Mypy. A CI workflow is configured for Ubuntu and Windows but **has not yet run in GitHub Actions**.

**Limits:**
- The M1b domain rules are in-memory only. There is no authentication, database, tenancy enforcement in storage, or protection against concurrent requests yet.
- No API endpoint uses them yet; the only application endpoint is `/healthz`.
- A citation's shape is validated. Whether the tenant may see the chunk, whether the quote is really in it, and whether it supports the claim are **not** checked yet.
- Human approval in EvidenceGuard does not establish document authenticity or certify compliance. See [docs/responsible-ai.md](docs/responsible-ai.md) and [docs/threat-model.md](docs/threat-model.md).

**Still planned** (see [docs/plan.md](docs/plan.md)):
- M1 acceptance, which still needs CI to run on GitHub Actions; Linux is unverified. The remaining M1 architecture record, [ADR-0003](docs/decisions/0003-plain-python-workflow.md) (plain-Python workflow), is accepted.
- Everything after M1: authentication, tenancy, persistence, ingestion, retrieval, model providers, the review workflow, API endpoints for the approval gate, and evaluation.

No retrieval, agent workflow, evaluation results, security guarantees or benchmarks are claimed. Any future results will be published with their committed inputs, configuration and the command that reproduces them.

## Development (Windows, PowerShell)

**Prerequisite:** [uv](https://docs.astral.sh/uv/) 0.13 or later. uv provides Python 3.12; the repository pins it in `.python-version`.

Set up:

```powershell
uv python install 3.12
uv sync --locked
```

Check:

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

Packaging layout: [ADR-0001](docs/decisions/0001-packaging-and-layout.md). Request IDs, logging and error format: [ADR-0002](docs/decisions/0002-request-ids-logging-and-errors.md). Workflow orchestration: [ADR-0003](docs/decisions/0003-plain-python-workflow.md).

The request ID is for correlating logs only. It is not authentication and says nothing about who made a request. Logs are local JSON lines on stderr; there is no monitoring or telemetry service.

## Engineering record

[prompts.md](prompts.md) records, verbatim and in order, every prompt given to the Claude Code implementation session, with a short note on each outcome. [CLAUDE.md](CLAUDE.md) holds the standing development rules.

## Secret scanning

A GitHub Actions workflow ([secret-scan.yml](.github/workflows/secret-scan.yml)) is configured to run [Gitleaks](https://github.com/gitleaks/gitleaks) v8.30.1 over the full Git history on every push and pull request. **It has not yet run in GitHub Actions.**

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
