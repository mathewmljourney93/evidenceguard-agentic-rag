# ADR-0004: Persistence foundation

- **Status:** Accepted (M2a). Verified in CI at commit `9ad7dae` on branch `feat/persistence-foundation`; not yet merged into `main`. See *Consequences and limits*.
- **Date:** 2026-10-11
- **Builds on:** plan decisions D2 and D7, and the M2 decisions recorded under Prompt 24 in [prompts.md](../../prompts.md)

## Context

M2 adds PostgreSQL. M2a covers only the persistence foundation:
- settings;
- engine and session lifecycle;
- the tenancy schema: tenants, users, API keys and vendors;
- migrations;
- test configuration.

Authentication, admin commands, vendor endpoints and `/readyz` arrive in later M2 slices.

## Decisions

### Package and dependencies
- **The package:** a new `evidenceguard_persistence` package under `packages/persistence/`, following ADR-0001. It must not import `evidenceguard_api`, and `domain` and `observability` must not import it; tests enforce both.
- **The database stack:** synchronous SQLAlchemy 2 with the psycopg 3 driver, Alembic for migrations, and pydantic-settings for configuration.
- **Dependency-age policy:** new dependencies resolve to releases published at least two weeks before they are added. This is enforced with `[tool.uv] exclude-newer-package`, applied only to the packages added in M2a and their new transitive dependencies; existing locked versions are unaffected. The resulting versions are SQLAlchemy 2.1.1, Alembic 1.20.0, psycopg 3.3.6, pydantic-settings 2.15.0, Mako 1.4.3, MarkupSafe 3.0.3, python-dotenv 1.2.3 and tzdata 2026.4. The cutoffs should be reviewed, and lifted or moved, at the next dependency update.

### Settings and lifecycle
- **Where settings are read:** database settings live in persistence, read from the `EG_DATABASE_URL` environment variable **only** when `load_database_settings()` is called. Importing any module, and `/healthz`, need no database configuration. No `.env` file is read implicitly.
- **Accepted URLs:** only `postgresql://` or `postgresql+psycopg://`, which are normalized to the psycopg driver.
  - Exactly one host is required: a DNS name or an IP literal. Host lists, socket paths and escaped hosts are rejected.
  - The port must be 1–65535. An omitted port is written into the URL as 5432, so libpq's `PGPORT` cannot change it.
  - The database name may contain only letters, digits, `_` and `-`.
- **Query parameters:** SQLAlchemy's psycopg dialect passes URL query parameters to the driver as connection arguments. A parameter could therefore override the validated database (`dbname`), reroute the connection (`host`, `hostaddr`, `port`, `service`), add credentials that URL masking does not hide (`password`, `passfile`), or set server options. So the parser accepts only `sslmode` (a libpq mode name) and `connect_timeout` (an integer from 1 to 600). Each may appear at most once, and every other parameter is rejected. Added after review (Prompt 26).
- **Keeping credentials out of output:**
  - the URL is held as a `SecretStr`;
  - `load_database_settings()` wraps every problem in a `DatabaseConfigurationError`. Its message names the variable but never the URL, a query value or a credential, and it suppresses the exception chain. **This wrapper is the supported error boundary.**
  - pydantic's `hide_input_in_errors` only keeps the input out of a *printed* `ValidationError`. It does not make structured dumps such as `errors()` or `json()` safe, so code must not log a raw `ValidationError` from `DatabaseSettings`;
  - SQLAlchemy `URL` and engine representations mask the password;
  - engines never echo SQL and hide SQL parameter values (`hide_parameters=True`).
- **Engines and sessions:** `create_db_engine` creates an engine without connecting, and `create_session_factory` makes sessions.
- **Transaction ownership:** `transaction()` owns one unit of work. It commits on success, rolls back on error and always closes the session; code inside the block must not commit or roll back itself. `dispose_engine` releases the connection pool.

### Schema (M2a tables only)
- **`tenants`** is the root table: `id`, `slug` (unique), `name`.
- **`users`**: `id`, `tenant_id` → `tenants`, `role`. A check constraint allows only `reviewer`, `approver` and `admin`.
  - `admin` is stored, but **grants no approval rights**. Approval transitions are unchanged and accept only `approver`.
  - The domain `Role` enum is not changed in M2a. How stored roles map to the domain `ActorContext` is decided with authentication in M2b.
- **`api_keys`**: `id`, `tenant_id` → `tenants`, `user_id`, `prefix`, `secret_sha256`, `created_at`, `revoked_at`.
  - A composite foreign key `(tenant_id, user_id)` → `users (tenant_id, id)` means a key can never belong to a user in another tenant.
  - `prefix` is unique across all tenants, so lookup by prefix is unambiguous.
  - Only the SHA-256 hex digest of the secret is stored, enforced by a check constraint; never the plaintext.
- **`vendors`**: `id`, `tenant_id` → `tenants`, `slug`, `name`, with `slug` unique per tenant.
- **Tenant-safe references:** every tenant-scoped table also has a unique `(tenant_id, id)`, so later tables can reference it through composite keys.
- **Constraint names** follow a fixed naming convention, so migrations and models agree.
- **IDs** are UUIDs generated by the application.

### Migrations
- **Packaging:** the migration environment, revision template and revisions ship inside the package. `migration_config.alembic_config()` builds an Alembic configuration that works from an installed wheel without `alembic.ini`. The repository's `alembic.ini` points at the same package location for use from the checkout.
- **How the URL is passed:** through `Config.attributes`, never written into Alembic's ini options. Offline SQL generation (`--sql`) needs no URL and does not connect.
- **One schema source:** the models are the single schema definition, and the first migration (`0001`) is written to match them.
  - Drift between the two is detected by `alembic check` in the PostgreSQL integration tests.
  - Autogenerate does not compare check constraints. Instead, a unit test confirms the migration renders the model's exact check expressions, and integration tests confirm PostgreSQL enforces them.
- **No extensions:** migration `0001` creates none. The `vector` extension arrives with the first migration that needs it.

### Integration testing
- **Where they run:** integration tests run against real PostgreSQL 17 with pgvector (`pgvector/pgvector:0.8.7-pg17`, pinned by digest) in a dedicated Ubuntu CI job. GitHub service containers need a Linux runner.
- **The test database:** tests use only `EG_TEST_DATABASE_URL`, never `EG_DATABASE_URL`, any other variable or the machine's existing PostgreSQL service. The tests drop and recreate the `public` schema of that database, so it must be **explicitly disposable**.
- **The destructive-test guard:** `evidenceguard_persistence.safety.require_disposable_test_database` runs in the session fixture that every connecting fixture depends on, before any engine exists. It refuses to run in four cases:
  - the test URL is missing or invalid under the URL policy above;
  - its database name doesn't end in `_test`;
  - `EG_DATABASE_URL` is set but invalid (it fails closed);
  - both URLs target the same *database identity*.
- **Database identity:** host, effective port and database.
  - Credentials, driver spelling and allowed options are ignored.
  - Host and database names are compared case-insensitively, and a trailing dot on the host is ignored.
  - Every loopback or unspecified address (`localhost`, `*.localhost`, `127.0.0.0/8`, `::1`, IPv4-mapped loopback, `0.0.0.0`, `::`) is treated as one host, erring towards refusal.
  - A database-independent test runs the real fixture in a child pytest process where engine creation is forced to fail. It shows that rejected targets never reach engine creation.
  - Added after review (Prompt 26), replacing a raw string comparison.
- **Without the variable:** integration tests are skipped with a clear reason.
- **In CI:** with `EG_REQUIRE_INTEGRATION=1`, a missing URL, no collected integration tests, or a run where none passes is a failure.
- **Compose:** `docker-compose.yml` provides the same image locally on `127.0.0.1:5433`, with documented, disposable development credentials.

## Consequences and limits

- **Verified against PostgreSQL in CI.** The tested commit is `9ad7dae` (`9ad7daefc6372786e1da2a636b9419b4ca7df89d`) on branch `feat/persistence-foundation`.
  - The [integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38158076257/job/114525070229) in [CI run 38158076257](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38158076257) ran against a PostgreSQL 17 + pgvector service container. Its log reports `10 passed, 250 deselected`, so none was skipped.
  - It covered:
    - migration upgrade, downgrade and re-upgrade;
    - the `alembic check` drift check;
    - that no extension is created;
    - the cross-tenant, missing-tenant, uniqueness, role and secret-hash constraints.
  - The database-independent checks, including the URL policy and the guard's refusal paths, passed on [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38158076257/job/114525070324) and [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38158076257/job/114525070158). The [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38158076261) passed.
  - The integration log was retrieved by the external reviewer.
- **Not verified locally.** Docker is not installed on the development machine, and the existing local PostgreSQL 16 service is deliberately not used. So `docker-compose.yml` has **never been run**.
- **No pgvector functionality tested.** M2a creates no vector extension. The pgvector image is used only as the PostgreSQL server.
- **Guard limits.** URL comparison cannot prove that two different DNS names, or a name and an IP address, reach different servers. Nothing is resolved. The `_test` suffix and the identity check are a safety net; the test database must still be one that can be lost. The URL policy also does not control libpq environment variables (for example `PGHOSTADDR`, `PGOPTIONS` or `PGSERVICEFILE`) set in the process that runs the tests or the application.
- **Image age.** The pinned image digest was published on 2026-10-01, under two weeks before it was pinned. The registry does not list older digests for this tag, so the dependency-age rule could not be applied to it.
- **Pagination.** Bounded limit/offset pagination, `/readyz`, authentication and key handling are later M2 slices.
