# ADR-0027: Production review path wiring

- **Status:** proposed (W8). Plan: [`docs/plans/feat-review-api.md`](../plans/feat-review-api.md).

## Context

The W8 reconciliation requires review enqueue, `run_review` registration and model provider
configuration to arrive together, as one reviewed unit. ADR-0025 requires a composition review
for any production registration of the review handler. Before W8, `run_review` existed only in
test registries, no route created reviews, and no setting configured the Anthropic adapter
(ADR-0026).

## Decision

- `EG_REVIEW_PROVIDER` switches reviews on in both processes (`anthropic` is the only value).
  `EG_REVIEW_MODEL` names the model; the two are set together or not at all, and empty counts
  as unset. Settings are read from the process environment only, never from a `.env` file, and
  every error names the variable, never its value.
- `EG_REVIEW_MODEL` is pinned into each review's configuration digest when the API creates the
  review. It must be a full dated model id (aliases are unverified, ADR-0026). The worker uses
  the model stored with each review; a worker model allowlist is deferred.
- `EG_ANTHROPIC_API_KEY` is read by the worker only, as a `SecretStr`. The API never reads it
  and never calls a model; Compose passes it to the worker service only.
- The worker registers `run_review` only with a fully valid configuration: `AnthropicProvider`
  over `HttpsAnthropicTransport`, with `LoggingSpanSink`, built in
  `evidenceguard_worker/review_wiring.py`. With reviews off it logs `worker.review_disabled`
  and never claims a review job; with a partial or invalid configuration it exits with code 3
  before reading database settings. `production_registry()` without a handler keeps exactly the
  ingestion and indexing kinds.
- The API creates reviews through the M5c loaders (`load_template`, `load_prompt`) and the M5d
  `create_review` seam with the offline `HASH_IDENTITY` profile, and returns 503
  `REVIEWS_NOT_CONFIGURED` when reviews are off or misconfigured. Routes: `POST /v1/reviews`
  (202, or 200 for an idempotent replay), `GET /v1/reviews/{review_id}`,
  `GET /v1/reviews/{review_id}/result` (409 until completed) and `GET /v1/review-templates`.
  `GET /v1/jobs/{job_id}` also shows review jobs.
- Review concurrency is bounded per tenant: `EG_REVIEW_MAX_IN_FLIGHT` (1 to 20, default 2, used
  by the API; the worker also validates it at startup and exits 3 on an invalid value) caps the tenant's `run_review` jobs that are queued or running. `create_review` checks
  the cap inside the creation transaction after the replay lookup, serialised per tenant by a
  no-op update of the tenant row (a lock alone would count from the stale `REPEATABLE READ`
  snapshot; the update makes a concurrent creator fail with `40001` and retry). Over the cap,
  POST is 429 `REVIEW_LIMIT_REACHED` with `Retry-After: 60`; a replay of an existing key is
  never refused.

## Consequences

- Production model calls become possible once both processes are configured. CI makes no live
  call; the first live call and the model choice are M7.
- Configuration skew is visible: an API with reviews on and a worker with reviews off leaves
  reviews queued, shown by `GET /v1/reviews/{review_id}` and the worker's startup event.
- Changing `EG_REVIEW_MODEL` makes a replayed idempotency key return 409, because the digest
  covers the model id.
- Evidence and trace routes are deferred: no stage-row read API exists and spans are logged,
  not persisted. M6 finds a report through the `review_outputs` row for (tenant, review_id),
  bound to the `wrapper_sha256` returned by `/result`.
- Rollback: unset `EG_REVIEW_PROVIDER` on both processes, or revert the merge. No migration.

## Why not

| Option | Why not |
|---|---|
| POST accepts and queues when unconfigured | Silent backlog that never runs; caller cannot tell reviews are off |
| Register `run_review` always and fail at run time without a key | Claims the job, burns attempts, marks reviews failed |
| Fall back to `ScriptedFakeProvider` | Fake judgments in production |
| Worker exits when the provider is unset | Breaks ingestion-only runs and the keyless CI smoke |
| One settings class with the key, read by the API too | The API never calls the model; least privilege keeps the key in the worker |
| API calls `review_seams.create_review_with_artifacts` | API must not import the worker |
| New agents module for artifact rebuild | Agents module set is pinned; the loaders exist |
| Anthropic SDK client | ADR-0026 accepted the stdlib transport |
| Evidence and trace routes now | No stage-row read API exists; spans are logged, not persisted |
| No cap on reviews in flight | Without a cap one reviewer key could queue unlimited reviews at once. The cap limits concurrency only; it is not a spend limit, which the owner sets separately as AGENTS.md requires |
