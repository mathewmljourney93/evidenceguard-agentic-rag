# EvidenceGuard: Auditable Multi-Agent RAG for Vendor Risk Review

EvidenceGuard is a planned vendor-risk review copilot. It is intended to:

- ingest synthetic vendor documents for one tenant at a time;
- retrieve only evidence that tenant is authorized to see, with provenance;
- identify supported answers, contradictions and missing information;
- draft a report in which every claim cites its evidence;
- require a human to approve the exact draft revision before it can be finalized or exported.

It is evidence-based decision support, not legal advice or compliance certification.

## Status: M1 foundation accepted (pre-alpha)

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
- Tests, Ruff and strict Mypy, run in GitHub Actions on Ubuntu and Windows.

**Verified baseline:** commit `6d64fb3` (`6d64fb362c25c28908e38b5d0a06f8c393bf6096`) passed [CI on Ubuntu and Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38142996464) and the [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38142996460). These results cover that commit only; every later change needs its own passing runs.

**Limits:**
- The M1b domain rules are in-memory only. There is no authentication, database, tenancy enforcement in storage, or protection against concurrent requests yet.
- No API endpoint uses them yet; the only application endpoint is `/healthz`.
- A citation's shape is validated. Whether the tenant may see the chunk, whether the quote is really in it, and whether it supports the claim are **not** checked yet.
- Human approval in EvidenceGuard does not establish document authenticity or certify compliance. See [docs/responsible-ai.md](docs/responsible-ai.md) and [docs/threat-model.md](docs/threat-model.md).

**Still planned** (see [docs/plan.md](docs/plan.md)):
- Revision activation and supersession tests, deferred from M1 to M3, where those state machines are built.
- Everything after M1: authentication, tenancy, persistence, ingestion, retrieval, model providers, the review workflow, API endpoints for the approval gate, and evaluation.

No retrieval, agent workflow, evaluation results, security guarantees or benchmarks are claimed. Any future results will be published with their committed inputs, configuration and the command that reproduces them.

## Development (Windows, PowerShell)

**Prerequisite:** [uv](https://docs.astral.sh/uv/) 0.13 or later. uv provides Python 3.12; the repository pins it in `.python-version`.

Set up:

```powershell
uv python install 3.12
uv sync --locked
```

Check (no database needed; PostgreSQL integration tests are skipped unless `EG_TEST_DATABASE_URL` is set):

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

### Database (M2a)

The persistence package (`evidenceguard_persistence`) adds PostgreSQL settings, the tenancy schema (tenants, users, API keys and vendors) and Alembic migrations. See [ADR-0004](docs/decisions/0004-persistence-foundation.md).

> **Verified in CI; Compose not run.**
> - **What passed:** on branch `feat/persistence-foundation` at commit `9ad7dae`, the [PostgreSQL 17 + pgvector integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38158076257/job/114525070229) ran all ten integration tests against a disposable service database. They cover migration upgrade, downgrade and re-upgrade, the drift check, tenant constraints and that no extension is created. Its log reports `10 passed, 250 deselected`, so none was skipped.
> - **Other checks in the same runs:** the database-independent checks passed on [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38158076257/job/114525070324) and [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38158076257/job/114525070158) in [CI run 38158076257](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38158076257), and the [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38158076261) passed.
> - **Not yet on `main`:** this work has not been merged.
> - **Compose:** Docker is not available on the development machine, so `docker-compose.yml` has never been run.
> - **pgvector:** M2a creates no vector extension, so no pgvector functionality has been tested.

1. Start a disposable PostgreSQL 17 + pgvector server. `docker-compose.yml` binds it to `127.0.0.1:5433` with **disposable local-only credentials**: user `evidenceguard`, password `evidenceguard-local-dev`, databases `evidenceguard_dev` and `evidenceguard_test`. Never reuse these anywhere else.

   ```powershell
   docker compose up -d
   ```

2. Set the database URLs in your shell. Variable names are listed in `.env.example`; EvidenceGuard does not read a `.env` file automatically. URLs must name exactly one host, an optional port (5432 if omitted) and a database. The only query parameters accepted are `sslmode` and `connect_timeout` (1–600 seconds), each at most once. Anything else, such as `dbname`, `host`, `service`, `password` or `options`, is rejected with an error that never repeats the URL.

   ```powershell
   $env:EG_DATABASE_URL = "postgresql+psycopg://evidenceguard:evidenceguard-local-dev@127.0.0.1:5433/evidenceguard_dev"
   $env:EG_TEST_DATABASE_URL = "postgresql+psycopg://evidenceguard:evidenceguard-local-dev@127.0.0.1:5433/evidenceguard_test"
   ```

3. Run migrations:

   ```powershell
   uv run --locked alembic upgrade head          # apply (uses EG_DATABASE_URL)
   uv run --locked alembic downgrade base        # remove every table
   uv run --locked alembic upgrade head --sql    # print the SQL only; needs no database
   ```

4. Run the integration tests. They use **only** `EG_TEST_DATABASE_URL`, and drop and recreate the `public` schema of that database. **Point it only at a database you can lose.** Before creating any engine, they refuse to run if:
   - the URL is invalid;
   - the database name doesn't end in `_test`;
   - `EG_DATABASE_URL` is set but invalid;
   - `EG_DATABASE_URL` targets the same host, port and database. This ignores credentials, driver spelling, host case, an omitted default port and loopback spellings such as `localhost`, `127.0.0.1` and `[::1]`.

   The check compares URLs only. It cannot tell that two different DNS names (or a name and an IP address) reach the same server.

   ```powershell
   $env:EG_REQUIRE_INTEGRATION = "1"   # fail, rather than skip, if the URL is missing or nothing runs
   uv run --locked pytest -m integration
   ```

CI runs step 4 on Ubuntu against a PostgreSQL 17 + pgvector service container. Database-independent checks still run on Ubuntu and Windows.

Packaging layout: [ADR-0001](docs/decisions/0001-packaging-and-layout.md). Request IDs, logging and error format: [ADR-0002](docs/decisions/0002-request-ids-logging-and-errors.md). Workflow orchestration: [ADR-0003](docs/decisions/0003-plain-python-workflow.md). Persistence: [ADR-0004](docs/decisions/0004-persistence-foundation.md).

The request ID is for correlating logs only. It is not authentication and says nothing about who made a request. Logs are local JSON lines on stderr; there is no monitoring or telemetry service.

## Engineering record

[prompts.md](prompts.md) records, verbatim and in order, every prompt given to the Claude Code implementation session, with a short note on each outcome. [CLAUDE.md](CLAUDE.md) holds the standing development rules.

## Secret scanning

A GitHub Actions workflow ([secret-scan.yml](.github/workflows/secret-scan.yml)) runs [Gitleaks](https://github.com/gitleaks/gitleaks) v8.30.1 over the full Git history on every push and pull request. It [passed](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38142996460) for the published baseline `6d64fb3`.

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
