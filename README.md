# EvidenceGuard: Auditable Multi-Agent RAG for Vendor Risk Review

EvidenceGuard is a planned vendor-risk review copilot. It is intended to:

- ingest synthetic vendor documents for one tenant at a time;
- retrieve only evidence that tenant is authorized to see, with provenance;
- identify supported answers, contradictions and missing information;
- draft a report in which every claim cites its evidence;
- require a human to approve the exact draft revision before it can be finalized or exported.

It is evidence-based decision support, not legal advice or compliance certification.

## Status: M1 accepted, M2a persistence on `main`, M2b authentication verified in CI on its branch (pre-alpha)

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
- **PostgreSQL persistence foundation** (M2a, on `main`): settings, engine and session lifecycle, the tenants/users/API keys/vendors schema with composite tenant constraints, Alembic migration `0001`, and a guarded PostgreSQL integration-test job. See [ADR-0004](docs/decisions/0004-persistence-foundation.md) and [Database](#database-m2a).
- **API-key authentication** (M2b, **reviewed and verified in CI on branch `feat/api-key-authentication`; not yet merged into `main`**):
  - `GET /v1/me` returns the tenant, user and role behind an `Authorization: Bearer` API key;
  - the `admin` role exists, with no report or approval rights;
  - an `eg-admin` command seeds a synthetic demo fixture and creates and revokes keys.

  At commit `b2f7f23`, all 15 PostgreSQL integration tests passed in CI, M2a's and M2b's ([job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38166627885/job/114550418432)). See [ADR-0005](docs/decisions/0005-api-key-authentication.md) and [Authentication](#authentication-and-eg-admin-m2b).
- Tests, Ruff and strict Mypy, run in GitHub Actions on Ubuntu and Windows, plus a PostgreSQL 17 + pgvector integration job on Ubuntu.

**Verified baseline:** `main` at commit `e2dee5c` (`e2dee5cf199cfa2b0ecbdc4d55a2cd7ea5865c00`, M2a) passed:
- [CI run 38159547345](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38159547345): verification on [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38159547345/job/114529403167) and [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38159547345/job/114529403100), and the [PostgreSQL integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38159547345/job/114529402973), whose log (retrieved by the external reviewer) reports `10 passed, 250 deselected in 2.64s`;
- the [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38159547321).

The earlier M1 baseline `6d64fb3` passed [CI](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38142996464) and the [secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38142996460). These results cover those commits only; every later change, including M2b, needs its own passing runs.

**Limits:**
- The M1b report rules are still in-memory only. Nothing persists reports yet, and there is no protection against concurrent requests.
- Apart from `/healthz`, the only endpoint is `/v1/me` (M2b, on its branch, not yet on `main`). No endpoint uses the report rules yet, and there are no vendor endpoints or `/readyz` (M2c).
- API keys are possession-based bearer credentials, with no rate limiting, lockout, expiry or scopes yet (see ADR-0005).
- A citation's shape is validated. Whether the tenant may see the chunk, whether the quote is really in it, and whether it supports the claim are **not** checked yet.
- Human approval in EvidenceGuard does not establish document authenticity or certify compliance. See [docs/responsible-ai.md](docs/responsible-ai.md) and [docs/threat-model.md](docs/threat-model.md).

**Still planned** (see [docs/plan.md](docs/plan.md)):
- Revision activation and supersession tests, deferred from M1 to M3, where those state machines are built.
- The rest of M2: merging M2b into `main` once authorized, then M2c (vendor endpoints, `/readyz` and the general API database wiring). M2 is not complete.
- After M2: ingestion, retrieval, model providers, the review workflow, API endpoints for the approval gate, and evaluation.

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
> - **On `main`:** M2a was fast-forwarded onto `main` at `e2dee5c`. [CI run 38159547345](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38159547345) passed there, including the [integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38159547345/job/114529402973) (`10 passed, 250 deselected in 2.64s`, log retrieved by the external reviewer), as did the [secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38159547321).
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

### Authentication and `eg-admin` (M2b)

> **Reviewed and verified in CI on branch `feat/api-key-authentication`; not yet merged into `main`.**
> - **Tested commit:** `b2f7f23` (`b2f7f2310cb265dcaab9a5c3055b3d762fa02d46`).
> - **[CI run 38166627885](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38166627885)** passed:
>   - verification on [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38166627885/job/114550418430) and [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38166627885/job/114550418222);
>   - the [PostgreSQL 17 + pgvector integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38166627885/job/114550418432). Its log, retrieved by the external reviewer, reports `15 passed, 377 deselected in 2.49s`, so none was skipped. The tests cover key creation, authentication, revocation, cross-tenant ownership, `seed-demo` idempotency and conflicts, and current-role reads.
> - **The [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38166627930)** passed.
> - **Compose** has never been run.
>
> Do not run these commands against a database you care about.

API keys look like `egk_<16 hex prefix>_<43-character secret>` (64 characters). Only the prefix and the SHA-256 of the secret are stored. A key is sent as `Authorization: Bearer <key>`. The tenant, user and role always come from the stored records, never from request headers, query parameters or bodies. Design and limits: [ADR-0005](docs/decisions/0005-api-key-authentication.md).

With `EG_DATABASE_URL` set and migrations applied (steps 2 and 3 above):

```powershell
uv run --locked eg-admin seed-demo     # synthetic demo tenants and users; idempotent; creates no keys
uv run --locked eg-admin create-key --tenant-id <tenant-id> --user-id <user-id>
uv run --locked eg-admin revoke-key --tenant-id <tenant-id> --prefix <16-hex-prefix>
```

- **`create-key`** prints the new key **once**, to stdout, only after it is stored. Store it securely; it cannot be shown again. No command accepts a secret as an argument, and usage errors print only static usage, never the arguments given.
- **`GET /v1/me`** returns `tenant_id`, `actor_id` and `role` for a valid key. Missing, malformed, unknown and revoked keys all get the same `401` with `WWW-Authenticate: Bearer`. If the database is not configured or not reachable, it returns a generic `503`. `/healthz` never needs a database.

Packaging layout: [ADR-0001](docs/decisions/0001-packaging-and-layout.md). Request IDs, logging and error format: [ADR-0002](docs/decisions/0002-request-ids-logging-and-errors.md). Workflow orchestration: [ADR-0003](docs/decisions/0003-plain-python-workflow.md). Persistence: [ADR-0004](docs/decisions/0004-persistence-foundation.md). API-key authentication: [ADR-0005](docs/decisions/0005-api-key-authentication.md).

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
