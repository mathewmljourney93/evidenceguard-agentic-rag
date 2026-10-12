# EvidenceGuard: Auditable Multi-Agent RAG for Vendor Risk Review

EvidenceGuard is a planned vendor-risk review copilot. It is intended to:

- ingest synthetic vendor documents for one tenant at a time;
- retrieve only evidence that tenant is authorized to see, with provenance;
- identify supported answers, contradictions and missing information;
- draft a report in which every claim cites its evidence;
- require a human to approve the exact draft revision before it can be finalized or exported.

It is evidence-based decision support, not legal advice or compliance certification.

## Status: M1 and M2 accepted (persistence, authentication, tenant-scoped vendors and readiness on `main`); M3a durable job core on `main`; M3b worker runtime reviewed and verified in CI on branch `feat/worker-runtime`, not yet on `main` (pre-alpha)

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
- **API-key authentication** (M2b, on `main`):
  - `GET /v1/me` returns the tenant, user and role behind an `Authorization: Bearer` API key;
  - the `admin` role exists, with no report or approval rights;
  - an `eg-admin` command seeds a synthetic demo fixture and creates and revokes keys.

  At commit `b2f7f23`, all 15 PostgreSQL integration tests passed in CI, M2a's and M2b's ([job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38166627885/job/114550418432)). See [ADR-0005](docs/decisions/0005-api-key-authentication.md) and [Authentication](#authentication-and-eg-admin-m2b).
- **Tenant-scoped vendors and readiness** (M2c, on `main`):
  - `POST /v1/vendors`, `GET /v1/vendors` (bounded pages) and `GET /v1/vendors/{id}`, always scoped to the API key's tenant;
  - `GET /readyz`, which checks database connectivity and migration revisions;
  - one shared, lazily started database resource for the whole API.

  At commit `a888b6c`, all 21 PostgreSQL integration tests passed in CI, including the six added in M2c ([job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38212619855/job/114689994147)), and again on `main` at `9d5a93a`. See [ADR-0006](docs/decisions/0006-vendor-api-and-readiness.md) and [Vendors and readiness](#vendors-and-readiness-m2c).
- **Durable job core** (M3a, on `main`):
  - a `jobs` table (migration `0002`) and pure lifecycle rules;
  - idempotent enqueue, claim with `SKIP LOCKED`, reclaim of expired leases, heartbeat, completion and failure;
  - a fenced transaction that checks the `(job, worker, attempt)` token and the lease with fresh database time before any effect.

  On `main` it is a library only, with no worker process, handler or endpoint. At commit `11350e1`, all 63 PostgreSQL integration tests passed in CI ([job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38240768344/job/114782517485)), including the job concurrency, lease-fencing and lock-timeout tests, and again on `main` at `b3f9845` ([job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38242144844/job/114787118281)). These results demonstrate the tested behaviour, not a general security or performance guarantee. See [ADR-0007](docs/decisions/0007-durable-job-core.md).
- **Worker runtime** (M3b, reviewed and verified in CI on branch `feat/worker-runtime` at `bc5f638`; **not yet merged into `main`**):
  - an `eg-worker` command that claims jobs of its registered kinds, runs one handler at a time, renews leases with heartbeats and records outcomes only through the M3a fence;
  - atomic completion with a handler's final effects, and cooperative cancellation checked at explicit points;
  - a graceful shutdown with bounded supervisor waits that ends the process with exit code 5 if a job thread does not stop. This is not a total shutdown deadline: a blocked database call can delay it (see ADR-0008).

  There are **no production handlers yet**, so `eg-worker` exits with code 4 before reading any settings. At commit `bc5f638`, [CI run 38253962690](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38253962690) passed on [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38253962690/job/114827089007) (`709 passed, 77 skipped in 15.96s`) and [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38253962690/job/114827088937) (`708 passed, 78 skipped in 22.18s`), and the [PostgreSQL integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38253962690/job/114827089078) passed all 77 integration tests, M3a's 63 and the worker's 14 (`77 passed, 709 deselected in 19.63s`), all from logs retrieved by the external reviewer. The [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38253962775) passed (25 commits scanned, no leaks found). These results demonstrate the tested behaviour, not a general security or performance guarantee. See [ADR-0008](docs/decisions/0008-worker-runtime.md).
- Tests, Ruff and strict Mypy, run in GitHub Actions on Ubuntu and Windows, plus a PostgreSQL 17 + pgvector integration job on Ubuntu.

**M2 accepted.** The external reviewer accepted M2 against its agreed criteria (see [docs/plan.md](docs/plan.md)), on the basis of the implementation diffs and the CI evidence below; the reviewer did not run the suite locally. This does not claim any vector functionality: the CI database image includes pgvector, but no migration creates the extension. Compose has never been run.

**Verified baseline:** `main` at commit `b3f9845` (`b3f984552bf22cf6350702330d30851f3e08b3f4`, M2 and M3a) passed:
- [CI run 38242144844](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38242144844): verification on [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38242144844/job/114787118333) (`605 passed, 63 skipped in 7.56s`) and [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38242144844/job/114787118106) (`605 passed, 63 skipped in 14.86s`), and the [PostgreSQL integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38242144844/job/114787118281) (`63 passed, 605 deselected in 16.17s`), all from logs retrieved by the external reviewer;
- the [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38242144876) (22 commits scanned, no leaks found).

Earlier, `main` at commit `9d5a93a` (`9d5a93ab1389d8a2b084c8f669df3bf9941a477f`, M2a, M2b and M2c) passed:
- [CI run 38214711868](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38214711868): verification on [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38214711868/job/114696647399) and [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38214711868/job/114696647671), and the [PostgreSQL integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38214711868/job/114696647728), whose log (retrieved by the external reviewer) reports `21 passed, 458 deselected in 4.92s`;
- the [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38214711864).

Earlier, `main` at commit `277dfea` (`277dfeaec7c1c64fa5ee92a3ce892823acc787fb`, M2a and M2b) passed:
- [CI run 38167398488](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38167398488): verification on [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38167398488/job/114552700669) and [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38167398488/job/114552700864), and the [PostgreSQL integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38167398488/job/114552700841), whose log (retrieved by the external reviewer) reports `15 passed, 377 deselected in 3.77s`;
- the [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38167398504).

Earlier, `main` at commit `e2dee5c` (`e2dee5cf199cfa2b0ecbdc4d55a2cd7ea5865c00`, M2a) passed:
- [CI run 38159547345](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38159547345): verification on [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38159547345/job/114529403167) and [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38159547345/job/114529403100), and the [PostgreSQL integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38159547345/job/114529402973), whose log (retrieved by the external reviewer) reports `10 passed, 250 deselected in 2.64s`;
- the [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38159547321).

The earlier M1 baseline `6d64fb3` passed [CI](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38142996464) and the [secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38142996460). These results cover those commits only; every later change needs its own passing runs. M2c's branch results are under [Vendors and readiness](#vendors-and-readiness-m2c).

**Limits:**
- The M1b report rules are still in-memory only. Nothing persists reports yet, and there is no protection against concurrent requests.
- The endpoints are `/healthz`, `/readyz`, `/v1/me` and the vendor endpoints. No endpoint uses the report rules yet. There are no documents, uploads or production job handlers yet. On `main` the job core (M3a) has no worker process; the M3b worker is verified in CI on its feature branch but not yet merged.
- Vendor pages use offset pagination, which is not a snapshot under concurrent changes (see ADR-0006).
- API keys are possession-based bearer credentials, with no rate limiting, lockout, expiry or scopes yet (see ADR-0005).
- A citation's shape is validated. Whether the tenant may see the chunk, whether the quote is really in it, and whether it supports the claim are **not** checked yet.
- Human approval in EvidenceGuard does not establish document authenticity or certify compliance. See [docs/responsible-ai.md](docs/responsible-ai.md) and [docs/threat-model.md](docs/threat-model.md).

**Still planned** (see [docs/plan.md](docs/plan.md)):
- Revision activation and supersession tests, deferred from M1 to M3, where those state machines are built.
- The rest of M3 (worker, documents and revisions, parsing and chunking, uploads, Docker), following the accepted slice sequence in [docs/plan.md](docs/plan.md). The M3b worker runtime is reviewed and verified in CI on `feat/worker-runtime` but not yet merged into `main`; M3c–M3f are not implemented, Compose is unverified, and overall M3 acceptance is pending.
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

> **Reviewed and verified in CI, and on `main`** since the fast-forward to `277dfea` ([CI run 38167398488](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38167398488), [integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38167398488/job/114552700841): `15 passed, 377 deselected in 3.77s`). The branch record follows.
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

### Vendors and readiness (M2c)

> **Reviewed and verified in CI, and on `main`** since the fast-forward to `9d5a93a` ([CI run 38214711868](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38214711868), [integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38214711868/job/114696647728): `21 passed, 458 deselected in 4.92s`, from the log retrieved by the external reviewer). The branch record follows.
> - **Tested commit:** `a888b6c` (`a888b6cbd277fb6a4556899fa630a7c50df14e61`), which adds only documentation after the reviewed M2c commit `73bebf5`.
> - **[CI run 38212619855](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38212619855)** passed:
>   - verification on [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38212619855/job/114689994050) and [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38212619855/job/114689993962);
>   - the [PostgreSQL 17 + pgvector integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38212619855/job/114689994147). Its log, retrieved by the external reviewer, reports `21 passed, 458 deselected in 4.65s`, so none was skipped. M2c's six tests cover API create/list/get, two-tenant isolation with identical slugs, duplicate rollback, pagination, and readiness when ready, unmigrated or mismatched.
> - **The [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38212619867)** passed.
> - **Not verified:** Compose has never been run. No vector functionality is tested: the CI database image includes pgvector, but no migration creates the extension.

With a reviewer or approver key (admins get `403`):

```powershell
$h = @{ Authorization = "Bearer <your API key>" }
Invoke-RestMethod -Method Post http://127.0.0.1:8000/v1/vendors -Headers $h -ContentType "application/json" -Body '{"slug": "lumenvale-cloud", "name": "Lumenvale Cloud"}'
Invoke-RestMethod "http://127.0.0.1:8000/v1/vendors?limit=20&offset=0" -Headers $h
Invoke-RestMethod http://127.0.0.1:8000/readyz   # no key needed
```

- **Vendors belong to the key's tenant.** The body takes only `slug` (lowercase letters and digits joined by single hyphens, at most 64 characters) and `name` (1–200 characters, not blank, no null character). Any other field is a `422`. A duplicate slug in the same tenant is a `409`; another tenant may reuse it. Another tenant's vendor and a missing one both return `404`.
- **Pages** are ordered by slug, then ID, with `limit` 1–100 (default 20) and `offset` 0–10,000. They are not a snapshot when vendors are added concurrently.
- **`GET /readyz`** returns `200 {"status": "ready", ...}` only when the database answers and its migrations exactly match this release; otherwise `503` with fixed check states. It never migrates or changes the database. `/healthz` is unaffected.

Packaging layout: [ADR-0001](docs/decisions/0001-packaging-and-layout.md). Request IDs, logging and error format: [ADR-0002](docs/decisions/0002-request-ids-logging-and-errors.md). Workflow orchestration: [ADR-0003](docs/decisions/0003-plain-python-workflow.md). Persistence: [ADR-0004](docs/decisions/0004-persistence-foundation.md). API-key authentication: [ADR-0005](docs/decisions/0005-api-key-authentication.md). Vendors, shared database lifecycle and readiness: [ADR-0006](docs/decisions/0006-vendor-api-and-readiness.md). Durable job core: [ADR-0007](docs/decisions/0007-durable-job-core.md). Worker runtime: [ADR-0008](docs/decisions/0008-worker-runtime.md).

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
