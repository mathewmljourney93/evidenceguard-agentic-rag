# ADR-0006: Tenant-scoped vendors, shared database lifecycle and readiness

- **Status:** Proposed, under review (M2c)
- **Date:** 2026-10-12
- **Builds on:** [ADR-0004](0004-persistence-foundation.md) (the `vendors` table and its constraints), [ADR-0005](0005-api-key-authentication.md) (API-key authentication and roles), plan sections on the API and M2, and the M2 decisions recorded under Prompt 24 in [prompts.md](../../prompts.md)

## Context

M2b authenticated requests but only `/v1/me` used the database, through a private engine inside the authenticator. M2c adds the first tenant-owned resource (vendors) and `/readyz`, so the API needs one shared database lifecycle, tenant-scoped queries and a readiness check that never changes the database.

## Decisions

### One shared, app-owned database resource
- **`AppDatabase`** (`evidenceguard_api.database`) holds the API's engine and session factory, shared by authentication, vendor operations and readiness. It replaces M2b's authenticator-private engine.
- **Lazy start:** the engine is created on first use, not at import, app construction, startup or for `/healthz`, so those need no database settings and make no connection.
- **Ownership:**
  - `create_app()` creates and owns an `AppDatabase` and disposes it on shutdown.
  - A `database` passed in is used but not closed by the app; its owner closes it.
- **Test seams:**
  - `create_app(authenticator=..., vendor_store=..., readiness=..., database=...)`; `create_app(authenticator=...)` still works as in M2b.
  - `AppDatabase(engine_factory)` lets integration tests supply their disposable test engine.
- **Bounded waits:**
  - New connections time out after 5 seconds, unless the URL sets its own validated `connect_timeout`.
  - Waiting for a pooled connection times out after 10 seconds.
  - The readiness query runs with a 2-second `statement_timeout`.
- **Threads:** routes and the authentication dependency are synchronous, so FastAPI runs them, and their blocking database work, in a worker thread rather than on the event loop.
- **Transactions:**
  - Each vendor operation is one `transaction`. A write commits before the response is built; any error, including a failed commit, rolls back.
  - The session is closed on every outcome.

### Tenant-scoped vendor persistence
- **Tenant scope:** `evidenceguard_persistence.vendors` functions take the authenticated `ActorContext` and use only its `tenant_id`; no function accepts a tenant separately.
  - A vendor is read by `(tenant_id, id)` in one query, never read globally and filtered afterwards.
  - The list and its total count filter by the same tenant.
- **Ordering:** by `slug`, then `id`. `slug` is unique per tenant and `id` is a unique tie-breaker.
- **Duplicates:** only a violation of the `uq_vendors_tenant_id_slug` constraint, identified by the driver's reported constraint name, becomes `DuplicateVendorSlugError`. Every other integrity error propagates unchanged and is not reported as a duplicate.
- **No schema change:** M2c uses the existing `vendors` table, with no migration.
- **Out of scope:** update, delete, ingestion, jobs and report endpoints.

### Vendor API
- **Routes:**
  - `POST /v1/vendors` → 201 with `{id, slug, name}`;
  - `GET /v1/vendors` → `{items, total, limit, offset}`;
  - `GET /v1/vendors/{vendor_id}` → `{id, slug, name}`.
- **Authorization:** reviewer and approver may use every route. Admin gets a generic 403, because administration grants no report or vendor rights (ADR-0005). Missing or invalid credentials keep the generic 401 from ADR-0005, which is checked before body validation.
- **`VendorCreate`** accepts only `slug` and `name`. Any other field, including `tenant_id`, `actor_id` or `role`, is a 422.
  - `slug` matches `^[a-z0-9]+(?:-[a-z0-9]+)*$` (lowercase letters and digits, joined by single hyphens) and is 1–64 characters.
  - `name` is 1–200 characters, not blank, and contains no null character (U+0000).
  - The bounds equal the column lengths. Invalid values are rejected, never rewritten or truncated.
- **Errors:**
  - A duplicate slug in the same tenant is a generic 409; the same slug in another tenant is allowed.
  - Another tenant's vendor and a nonexistent ID return the same generic 404.
  - Database or configuration failures return a generic 503.
  - All errors are problem+json with the request ID, using generic details; no submitted value is echoed.
- **Tenant scope at the boundary:** tenant headers and query parameters are ignored; the tenant comes only from the API key.
- **Pagination:** `limit` defaults to 20 (1–100) and `offset` to 0 (0–10,000). Offset pagination is **not a snapshot**: a concurrent insert or delete can make a later page repeat or skip an item, and the count and page are read separately under PostgreSQL's default READ COMMITTED isolation.

### `GET /readyz`
- **Unauthenticated.** It returns `{status, checks}`, where `status` is `ready` or `not_ready` and `checks` has fixed keys `database` and `migrations`, each `ok`, `failed` or `not_checked`.
- **Ready means:** the database answers `SELECT 1`, and the set of applied Alembic revisions equals the packaged migration heads. A reachable but unmigrated database, a missing version table or a different revision is **not** ready.
- **Status codes:** 200 only when ready; otherwise 503. Missing or invalid settings, connection failures and timeouts are `database: failed` with `migrations: not_checked`.
- **What it reveals:** nothing but the fixed values. No URL, revision identifier, SQL or exception text is returned.
- **It never changes the database.** Alembic's `MigrationContext` reads `alembic_version` without creating it, the transaction is rolled back, and no migration runs and no extension is created.
- **`/healthz` is unaffected** and stays successful when readiness fails.

## Consequences and limits

- **Not run against PostgreSQL yet.** The M2c PostgreSQL integration tests have not run:
  - vendor create, list and get through the API;
  - two-tenant isolation with identical slugs;
  - duplicate rollback;
  - pagination;
  - readiness when ready, unmigrated and on a revision mismatch.

  No local database is used. They are **pending** until a reviewed branch is published and its CI integration job passes.
- **The PostgreSQL error code is not checked.** Duplicate detection relies on psycopg reporting the constraint name. If a future driver stopped reporting it, duplicates would surface as 503s rather than 409s, never as false 409s.
- **Readiness is coarse.** It checks connectivity and revision equality only. It does not prove that every table matches the models; `alembic check` in CI does that.
- **Readiness is not access-controlled.** It is unauthenticated and reveals only that the service is or is not ready, plus which of the two fixed checks failed.
- **Pagination** is offset-based, bounded and not a snapshot; cursor pagination is a later enhancement.
- **The API-key limits from ADR-0005 still apply:** possession is access, and there is no rate limiting, expiry or scopes.
- **Compose has never been run.**
