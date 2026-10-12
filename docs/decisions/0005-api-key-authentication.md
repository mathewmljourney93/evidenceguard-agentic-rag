# ADR-0005: API-key authentication and tenant context

- **Status:** Accepted (M2b). Verified in CI at commit `b2f7f23` on branch `feat/api-key-authentication`, then fast-forwarded onto `main` at `277dfea`, where CI passed again. See *Consequences and limits*. The default database wiring below is superseded, under review, by the shared `AppDatabase` in [ADR-0006](0006-vendor-api-and-readiness.md).
- **Date:** 2026-10-12
- **Builds on:** [ADR-0002](0002-request-ids-logging-and-errors.md) (problem responses and logging), [ADR-0004](0004-persistence-foundation.md) (the `api_keys` and `users` tables), plan decision G12, and the M2 decisions recorded under Prompt 24 in [prompts.md](../../prompts.md)

## Context

M2a stored tenants, users and API keys but nothing authenticated a request: the domain trusted any `ActorContext` it was given. M2b adds per-user API keys, derives the tenant context from them at the API boundary, adds the `admin` role and an `eg-admin` command. Vendor endpoints, the general API database wiring and `/readyz` remain M2c.

## Decisions

### Key format and storage
- **Format:** exactly 64 ASCII characters, `egk_<prefix>_<secret>`.
  - `egk_` is a fixed marker, so people and secret scanners can recognise keys.
  - `<prefix>` is 16 lowercase hex characters (64 random bits from `secrets.token_hex`). It is a public lookup identifier, unique across all tenants (the existing `uq_api_keys_prefix` constraint).
  - `<secret>` is 43 URL-safe base64 characters (256 random bits from `secrets.token_urlsafe`), generated separately from the prefix.
  - Both parts have fixed lengths, so parsing is unambiguous even though `_` can occur in the secret. Any other length or character is rejected before a database lookup.
- **Storage:** only the prefix and the SHA-256 hex digest of the secret are stored, in the existing `api_keys` table; there is no schema change. A plain digest is enough because the secret is uniformly random and 256 bits long: there is nothing for salting or key stretching to protect.
- **Comparison:** digests are compared with `hmac.compare_digest`.
- **Plaintext handling:** a plaintext key or secret is only ever held in pydantic `SecretStr`, whose `repr` and `str` are masked. The `NewApiKey` and `ParsedApiKey` holders never show the secret or its digest.

### Authentication
- `evidenceguard_persistence.auth.ApiKeyAuthenticator` turns a credential into an `ActorContext` or `None`:
  - it looks the key up by prefix and joins the owning user on **both** `tenant_id` and `user_id`, matching the composite foreign key;
  - the tenant, actor and role come only from the stored rows;
  - stored roles map to domain roles through an explicit table (`reviewer`, `approver`, `admin`). An unmapped value is rejected;
  - malformed, unknown, wrong-secret, revoked and unmapped-role keys all return the same `None`. An unknown prefix still performs a digest comparison, so it does not skip that work.
- **No caching.** Every call opens one session, reads the current role and revocation state, and closes the session on every outcome, including errors. A role change or a revocation applies to the next request.

### HTTP boundary
- **Credentials come only from `Authorization: Bearer <key>`.** The scheme name is case-insensitive. Exactly one space separates it from the key, and the key may contain no whitespace.
- **Rejected without consulting the authenticator:** a missing header, more than one `Authorization` header, a header longer than 128 bytes, non-ASCII bytes, any other scheme, or extra tokens.
- **Every authentication failure gets the same response:** 401 `application/problem+json`, `detail` "Authentication is required.", `WWW-Authenticate: Bearer`, and the request ID in both the header and the body. Nothing distinguishes a malformed key from an unknown, wrong or revoked one.
- **If the database is not configured or fails,** authentication returns a generic 503. No URL, exception text or credential is returned. Other unexpected errors use the existing generic 500.
- **`GET /v1/me`** returns only `tenant_id`, `actor_id` and `role`, with `Cache-Control: no-store`. It takes no parameters. Tenant headers, query parameters and other submitted values are ignored and cannot override the authenticated scope.
- **OpenAPI** documents an `http`/`bearer` security scheme named `ApiKey` on `/v1/me`. `/healthz` stays unauthenticated.
- **Logging** is unchanged. The request log carries only the allowlisted fields from ADR-0002, so credentials are never logged. A test checks the rendered and raw log records.

### Application wiring
- **The injection seam:** `create_app(authenticator=...)` accepts any callable from credential to `ActorContext | None`. Tests inject doubles.
- **Default wiring:** without an authenticator, the app owns a `DatabaseAuthenticator`.
  - It reads `EG_DATABASE_URL` and creates its engine only when the first *well-formed* credential arrives.
  - Importing modules, building the app, starting it and serving `/healthz` therefore need no database settings and make no connection.
  - The app's lifespan disposes the engine on shutdown. An injected authenticator is never closed by the app.
- **Scope:** only the wiring needed for authentication and `/v1/me` is added. M2c adds the general request-scoped database wiring.

### Roles
- **The domain `Role` gains `ADMIN`.** It administers accounts and keys.
- **No admin bypass:** `ADMIN` is in neither the report-editing set nor the approval set. It cannot draft, revise, approve, reject or finalize a report. Only `APPROVER` approves, rejects or finalizes, as before.
- **How `ActorContext` is built:** its docstring now separates construction at the API, which happens only from an authenticated key and stored records, from direct domain callers, which are trusted to pass a principal established elsewhere.

### `eg-admin`
`eg-admin` is registered in the existing distribution and implemented in `evidenceguard_api.admin`. Its database operations are in `evidenceguard_persistence.accounts`, and each operation is one transaction.

- **`seed-demo`** creates a deterministic synthetic fixture:
  - two fictional tenants (`halverson-freight`, `marisol-clinics`), each with one user per role;
  - IDs derived with `uuid5` from a fixed namespace, using `INSERT … ON CONFLICT DO NOTHING`.
  - It is idempotent and never changes an existing tenant, user, role or revocation.
  - It reports each user's **stored** role, read back after the insert, which may differ from the default if an operator changed it.
  - It refuses, with a fixed message and a full rollback, a demo tenant slug or demo user ID that already belongs to a different tenant.
  - It creates no API keys and no documents.
- **`create-key --tenant-id T --user-id U`** checks inside the transaction that U belongs to T, then stores the key.
  - The plaintext key is printed **once, to stdout, only after the transaction commits**.
  - The prefix and key ID go to stderr.
- **`revoke-key --tenant-id T --prefix P`:**
  - it sets `revoked_at` on that tenant's key and keeps the row;
  - an earlier revocation time is never moved;
  - another tenant's key is reported as not found.
- **No secret is ever accepted as an argument.**
- **No database needed for `--help` or imports.**
- **Errors:** failures print a fixed message to stderr and exit 1. Unexpected exceptions are reported by class name only.
- **Usage errors:** invalid UUIDs, unknown commands or options, extra arguments and missing required arguments go through `SafeArgumentParser`, which the root parser and every subparser use.
  - It prints only the static usage line and a fixed message, and exits 2 before any database is opened.
  - argparse's own diagnostics are never printed, because they quote the offending value, which could be a key pasted by mistake.
  - Option abbreviations are disabled. `--help` is unchanged and needs no database.

### Testing
- **Database-independent tests use explicit doubles:** an injected authenticator for the API, a recording session for `ApiKeyAuthenticator`, and a fake store for `eg-admin`.
- **PostgreSQL integration tests** run in the existing CI job behind the disposable-database guard, with required-integration enforcement unchanged. They cover:
  - key creation, authentication through `/v1/me`, and revocation;
  - cross-tenant ownership rejection;
  - `seed-demo` idempotency;
  - authentication reflecting the current stored role.

## Consequences and limits

- **Possession is access.** Anyone who holds a valid key acts as its user until the key is revoked. There is no second factor, client binding, key expiry, rotation schedule, scope restriction or IP allowlist.
- **No rate limiting or lockout yet.** Guessing a 256-bit secret is infeasible, but nothing limits request volume or repeated failures. Each well-formed credential costs one database lookup.
- **Residual timing difference.** An unknown prefix and a known prefix with a wrong secret both perform a digest comparison, but the database lookup itself may take measurably different time. Prefixes are not secret, so this reveals at most whether a prefix exists.
- **Transport.** Keys are bearer tokens. `eg-api` binds to `127.0.0.1` by default and terminates no TLS. Any non-local deployment must add TLS in front.
- **Printing the key.** `create-key` writes the key to stdout once. Terminal scrollback, redirection or session recording can retain it, and operators must store it securely.
- **No usage or audit trail beyond timestamps.** Only `created_at` and `revoked_at` are kept; there is no `last_used_at` or administrative audit log yet.
- **Demo identities are public.** The `seed-demo` IDs are deterministic and documented. They are for demonstrations only.
- **Revocation and in-flight requests.** Revocation takes effect on the next authentication; requests already authenticated finish.
- **Verified in CI.** The tested commit is `b2f7f23` (`b2f7f2310cb265dcaab9a5c3055b3d762fa02d46`) on branch `feat/api-key-authentication`.
  - In [CI run 38166627885](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38166627885), the [integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38166627885/job/114550418432) ran against a PostgreSQL 17 + pgvector service container. Its log, retrieved by the external reviewer, reports `15 passed, 377 deselected in 2.49s`, so none was skipped. That covers M2a's ten tests and M2b's five.
  - The database-independent checks passed on [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38166627885/job/114550418430) and [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38166627885/job/114550418222), and the [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38166627930) passed.
  - **On `main` at `277dfea`** (`277dfeaec7c1c64fa5ee92a3ce892823acc787fb`): [CI run 38167398488](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38167398488) passed, including the [integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38167398488/job/114552700841). Its log, retrieved by the external reviewer, reports `15 passed, 377 deselected in 3.77s`. The [secret-scan run 38167398504](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38167398504) also passed.
- **Not verified locally.** No local database is used, and Compose has never been run.
