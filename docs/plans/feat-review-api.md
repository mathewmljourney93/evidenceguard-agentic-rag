# Plan: feat/review-api (W8 production review path)

- **Tier:** critical (new routes, production AI provider wiring, new secret settings)
- **Author / model:** planner agent, Claude Opus 5.5, highest effort (the most capable model available to the session; Fable was unavailable). Owner decisions settled by the orchestrator, Claude Opus 5.5.
- **Date:** 2026-11-20
- **Status:** agreed (orchestrator under Mathew's written delegation, 2026-11-20)
- **Decision record:** ADR 0027 (draft at the end, written to `docs/decisions/0027-production-review-path.md` in the PR)
- **Base:** main after the agreement PR (#1)

## Goal

Enable, as one reviewed unit: (a) production configuration of the Anthropic provider, (b) registration of `run_review` in the production worker registry, (c) API routes to start a review and read its progress and result. After this, a reviewer or approver key can POST a review for a vendor and a configured worker runs it end to end. Without configuration both processes fail closed. CI makes no live call. The first live call happens in M7, not here.

## Existing code found (re-checked at bb61b32)

- `apps/worker/evidenceguard_worker/review.py:529` `make_run_review_handler(provider, *, session_factory, embedding_providers=SUPPORTED_PROVIDERS, clock, span_sink)`; no default provider; the model comes from the stored `ReviewConfiguration.model_id`.
- `apps/worker/evidenceguard_worker/handlers.py:15-18` `production_registry()` registers ingest and index only. `__main__.py:131-142` checks for an empty registry (exit 4) before settings, then opens `database_store()`. `DatabaseJobStore` (runtime.py:130) holds `_factory`.
- `packages/persistence/evidenceguard_persistence/reviews.py:505` `create_review(session_factory, actor, request) -> CreatedReview` (replay returns `replayed=True`); `:736` `load_review` -> `TrustedReview`. Role check `:166` uses `RETRIEVAL_ROLES` = {reviewer, approver}.
- `apps/worker/evidenceguard_worker/review_seams.py:188` `create_review_with_artifacts` is in the worker; the API may not import the worker (tests/test_packaging.py:104).
- `packages/persistence/evidenceguard_persistence/review_outputs.py:823` `load_review_output`, `:839` `load_review_status` -> `ReviewStatus` {queued, running, completed, failed}, `READ_ROLES :105`.
- Pinned artifacts: `evidenceguard_agents.templates.load_template("vendor_security_review", 1)` (8 questions); `evidenceguard_agents.prompts.load_prompt("verifier", 1)` and `("risk_analyst", 1)`.
- Provider: `evidenceguard_agents/anthropic.py:433` `AnthropicProvider(transport)`; `apps/worker/evidenceguard_worker/anthropic_http.py:137` `HttpsAnthropicTransport(api_key: SecretStr)` (key 1 to 256 printable ASCII); `evidenceguard_observability.jsonlog.LoggingSpanSink`.
- API patterns: `auth.py:88` `authenticated_actor`; role dependency `vendors.py:128`, `documents.py:344`; `_database_errors_as_503`; `problems.PublicMessage`; `create_app` injection seams; `document_views.VIEWABLE_JOB_KINDS :66` = {ingest_revision}.
- Settings: `persistence/settings.py` `DatabaseSettings` (env_prefix EG_, env_file None, frozen, hide_input_in_errors) with a wrapper error naming the variable only.
- CI: `.github/workflows/ci.yml:68,89,382,423,460` and `infra/ci/container_ci.py:485` `IMPORT_CHECK` assert `production_registry()` (no argument) has the two kinds. They stay true.

## Settled decisions

- W8 builds the production wiring; the first live call and model choice are M7.
- POST when reviews are not configured: 503 `REVIEWS_NOT_CONFIGURED` (no silent backlog).
- Replay of an Idempotency-Key: 200 with the original body (M3e upload precedent).
- Worker model allowlist: deferred (out of scope); EG_REVIEW_MODEL must be a full dated model id.

## Approach

### Settings (`packages/persistence/evidenceguard_persistence/settings.py`, extend)

- `class ReviewProvider(StrEnum): ANTHROPIC = "anthropic"`.
- `class ReviewSettings(BaseSettings)`, same model_config as `DatabaseSettings` plus `env_ignore_empty=True`: `review_provider: ReviewProvider | None = None`, `review_model: str | None = None`. Validator: model matches `MODEL_ID_PATTERN` (domain `model_calls.is_model_id`); provider and model both set or both unset.
- `class AnthropicSettings(BaseSettings)` (same config): `anthropic_api_key: SecretStr`, 1 to 256 printable ASCII.
- `class ReviewConfigurationError(RuntimeError)`. `load_review_settings() -> ReviewSettings | None` (None when both unset; raises when only one set or a value is invalid). `load_anthropic_settings() -> AnthropicSettings`. Messages name EG_REVIEW_PROVIDER, EG_REVIEW_MODEL or EG_ANTHROPIC_API_KEY, never a value; `from None` wrapper like `load_database_settings`.
- Env vars: EG_REVIEW_PROVIDER (switch, both processes), EG_REVIEW_MODEL (both), EG_ANTHROPIC_API_KEY (worker only). Voyage and embeddings unchanged: reviews use the offline `HASH_IDENTITY` production indexing already uses. Add the three names, empty, to `.env.example`.

### Worker

- `handlers.py`: `production_registry(review_handler: JobHandler | None = None) -> HandlerRegistry`; appends `(REVIEW_JOB_KIND, review_handler)` when given.
- New `apps/worker/evidenceguard_worker/review_wiring.py`:
  - `load_review_provider() -> ModelProvider | None`: None if `load_review_settings()` is None; else `AnthropicProvider(HttpsAnthropicTransport(load_anthropic_settings().anthropic_api_key))`. An `AnthropicError` from construction becomes `ReviewConfigurationError("EG_ANTHROPIC_API_KEY is not a valid key")`.
  - `build_review_handler(provider: ModelProvider, session_factory: sessionmaker[Session]) -> JobHandler` = `make_run_review_handler(provider, session_factory=session_factory, span_sink=LoggingSpanSink())`.
  - Module docstring must not contain "voyage" or "provenance" (text pins).
- `runtime.py`: read-only property `DatabaseJobStore.session_factory`.
- `__main__.py main(...)`: keyword arguments `review_provider_loader: Callable[[], ModelProvider | None] = load_review_provider` and `review_handler_factory = build_review_handler`. Order: arguments and logging; base registry and exit-4 check (unchanged); `provider = review_provider_loader()` (on `ReviewConfigurationError` log `worker.config_invalid`, exit 3 with `str(exc)`, before any database settings are read); log `worker.review_enabled` or `worker.review_disabled`; inside `store_factory()`, if a provider is set, `registry = production_registry(review_handler_factory(provider, store.session_factory))`. Add both events to `jsonlog.WORKER_EVENTS`; update the docstring exit-code list.

### API (new `apps/api/evidenceguard_api/reviews.py`, router included in `app.py`)

- `REVIEW_ROLES = RETRIEVAL_ROLES`; `review_actor` dependency, generic 403 for admin. Tenant always from `actor.tenant_id`; body forbids extra fields.
- `class ReviewService(Protocol)`: `create(actor, vendor_id, template_id, template_version, idempotency_key) -> ReviewCreated`, `detail(actor, review_id)`, `result(actor, review_id)`, `templates()`. `DatabaseReviewService(database: AppDatabase, settings_loader=load_review_settings)`. Settings read per POST, never at app build. `create_app(..., review_service: ReviewService | None = None)`.
- `_pinned_configuration(template_id, version, model_id) -> ReviewConfiguration` via `load_template` and `load_prompt`; agents errors become `ReviewArtifactsUnavailableError` (500); unknown template ids 422. Runs before database work. Agents imports limited to `templates` and `prompts`.
- **POST /v1/reviews**, header `Idempotency-Key` (`Header(pattern=IDEMPOTENCY_KEY_PATTERN)`), body `ReviewCreate{vendor_id: UUID, template_id: str = "vendor_security_review", template_version: int = 1}`. Flow: settings (None gives 503), configuration, `ReviewRequest(identity=HASH_IDENTITY, ...)`, `create_review`, `load_review`. Success 202 `ReviewAccepted{review_id, job_id, status, revision_ids, excluded_pending{count, revision_ids, truncated}}`; replay 200 same body. Errors: `EmptySnapshotError` 409 `NO_ACTIVE_REVISIONS`; `SnapshotNotReadyError` 409 `DOCUMENTS_NOT_READY`; `ReviewIdempotencyConflictError` 409 `IDEMPOTENCY_KEY_REUSED`; `RetrievalScopeError` 404; `SnapshotBoundsError` 422; `ReviewConflictRetryableError`, `ReviewCommitOutcomeUnknownError`, `ReviewDatabaseError`, DB/config errors 503; `*RecordInconsistentError`, `SnapshotInconsistentError` 500. The key is never echoed or logged.
- **GET /v1/reviews/{review_id}**: `load_review` then `load_review_status` -> `ReviewDetail{id, vendor_id, job_id, status, captured_at, template_id, template_version, model_id, revision_ids, excluded_pending, snapshot_sha256, configuration_sha256}`. Not found or other tenant: 404.
- **GET /v1/reviews/{review_id}/result**: `load_review_output` -> `ReviewResult{review_id, job_attempt, created_at, wrapper_sha256, markdown_sha256, markdown_bytes, question_count, finding_count, unresolved_count, report: json.loads(wrapper_canonical)}`. Not ready: 409 `RESULT_NOT_READY`.
- **GET /v1/review-templates** -> `list[TemplateSummary{template_id, version, title, question_count, sha256}]` from constant `REVIEW_TEMPLATES = (("vendor_security_review", 1),)`.
- `document_views.VIEWABLE_JOB_KINDS` adds `REVIEW_JOB_KIND`; GET /v1/jobs summary becomes "Get a job".
- New `PublicMessage` members with fixed sentences: REVIEWS_NOT_CONFIGURED, NO_ACTIVE_REVISIONS, DOCUMENTS_NOT_READY, IDEMPOTENCY_KEY_REUSED, RESULT_NOT_READY.
- Routes are sync (threadpool), following vendors.

### Fail-closed summary

Unset provider: worker never claims `run_review`; POST 503. Partial or invalid config: worker exit 3; POST 503. API configured but worker not: jobs stay queued, visible on GET. No fake provider outside tests (packaging test).

### CI and containers

- `docker-compose.yml`: api gets `EG_REVIEW_PROVIDER: ${EG_REVIEW_PROVIDER:-}`, `EG_REVIEW_MODEL: ${EG_REVIEW_MODEL:-}`; worker gets those two plus `EG_ANTHROPIC_API_KEY: ${EG_ANTHROPIC_API_KEY:-}`.
- `container_ci.validate_config`: the api service must not define EG_ANTHROPIC_API_KEY; in the CI-rendered config the worker key is empty.
- Smoke `steps()`: after indexing, `check_reviews_disabled()` asserts POST /v1/reviews is 503 and the worker logs contain `worker.review_disabled` and no `run_review` claim.
- ci.yml: one wheel block asserts `load_review_settings()` is None in a clean env; `production_registry(review_handler=make_run_review_handler(ScriptedFakeProvider(...), session_factory=sessionmaker()))` has three kinds; `create_app()` OpenAPI contains /v1/reviews. Existing registry lines unchanged.

## Alternatives rejected

| Option | Why not |
|---|---|
| POST accepts and queues when unconfigured | Silent backlog that never runs; caller cannot tell reviews are off |
| Register `run_review` always and fail at run time without a key | Claims the job, burns attempts, marks reviews failed |
| Fall back to `ScriptedFakeProvider` | Fake judgments in production |
| Worker exits when the provider is unset | Breaks ingestion-only runs and the keyless CI smoke |
| One settings class with the key, read by the API too | The API never calls the model; least privilege keeps the key in the worker |
| API calls `review_seams.create_review_with_artifacts` | API must not import the worker |
| New agents module for artifact rebuild | Agents module set is pinned; the loaders exist |
| Anthropic SDK client | ADR 0026 accepted the stdlib transport |
| Evidence and trace routes now | No stage-row read API exists; spans are logged, not persisted |

## Tests (all new tests fail on base)

- `tests/test_review_settings.py`: `test_unset_review_settings_return_none`; `test_provider_without_model_is_a_configuration_error`; `test_model_without_provider_is_a_configuration_error`; `test_unknown_provider_is_rejected`; `test_invalid_model_id_is_rejected`; `test_empty_values_count_as_unset`; `test_anthropic_key_never_appears_in_errors_repr_or_dump` (canary); `test_review_settings_ignore_dotenv_files`.
- `tests/test_review_wiring.py`: `test_disabled_settings_build_no_provider`; `test_enabled_settings_build_the_https_anthropic_provider_without_network` (connection factory asserted never called); `test_missing_or_invalid_key_is_a_configuration_error`; `test_build_review_handler_is_registered_as_run_review`.
- `tests/test_worker_cli.py`: `test_unconfigured_worker_never_claims_run_review`; `test_configured_worker_claims_run_review` (injected test provider); `test_partial_review_configuration_exits_three_before_database_settings`; `test_review_configuration_errors_never_print_the_key`.
- `tests/test_reviews_api.py` (fake `ReviewService`): `test_create_review_returns_202_with_snapshot_ids`; `test_replayed_key_returns_200_and_the_original_review`; `test_missing_or_invalid_idempotency_key_is_422`; `test_tenant_or_extra_fields_in_body_are_422`; `test_admin_gets_403_and_anonymous_401`; `test_unconfigured_reviews_return_503`; `test_no_active_revisions_409`; `test_documents_not_ready_409`; `test_key_reuse_with_different_body_409`; `test_foreign_or_missing_vendor_404`; `test_commit_outcome_unknown_503`; `test_review_detail_404_for_other_tenant`; `test_result_409_until_completed_then_200_with_digests`; `test_review_templates_list_the_pinned_template`; `test_problem_bodies_never_echo_the_idempotency_key`.
- `tests/test_review_api_postgres.py` (integration): `test_post_review_then_production_registry_with_test_provider_completes_it`; `test_registry_without_review_handler_leaves_review_queued`; `test_repeated_key_returns_original_review_over_http`; `test_job_view_shows_the_run_review_job`.
- `tests/test_openapi.py`: update the ordered paths list; add `test_review_routes_document_auth_and_errors`.
- `tests/test_container_ci.py`: `test_validate_config_rejects_key_on_api`; `test_smoke_checks_reviews_disabled`.
- `tests/test_packaging.py`: add `test_production_paths_never_construct_the_scripted_provider`, `test_review_api_imports_only_templates_and_prompts_from_agents`, `test_review_wiring_keeps_the_accepted_imports`.
- Updated pins (deliberate, each with a `# W8:` comment): test_packaging.py:296-318 (allow api `reviews.py`, templates and prompts only); :496-511 (add `review_wiring.py` to `M5G_AGENT_IMPORTERS`); :513-533 (rename to `test_m5d_creation_is_wired_only_through_the_review_api`; only api `reviews.py` may mention `persistence.reviews`; only `review_wiring.py` and `review.py` mention run_review in the worker); :735-754 (allow `review_wiring.py` factory and api `reviews.py` `review_outputs`); :801-829 (allow `review_wiring.py`); :222-230 and :656-683 unchanged but re-read. test_review_handler.py:550-555 also asserts `production_registry(review_handler=h)` includes `run_review`. test_review_handler_postgres.py:257, test_reviews_postgres.py:866-874, test_review_stages_postgres.py:1852 renamed "...without a configured provider...", logic unchanged. test_worker_runtime.py:1222 WORKER_EVENTS adds the two events.

## Risks and rollback

- Model alias behaviour is unverified (ADR 0026); a mismatch ends the stage under W13. Use a full dated model id.
- Cost per review bounded by 8 questions x 2 stages x 3 reservations plus 1 repair; no hard wall-clock limit.
- Config skew: API enabled, worker disabled leaves jobs queued. Changing EG_REVIEW_MODEL makes a replayed key return 409 (digest covers model_id).
- Rollback: unset EG_REVIEW_PROVIDER on both processes, or revert the merge. No migration.

## Out of scope

/v1/reviews/{id}/evidence and /trace; /v1/reports/* (M6); cancel and resume; a worker model allowlist; Voyage; live evaluation (M7); a provider readiness check. M6 finds the report through the `review_outputs` row for (tenant, review_id), bound to `wrapper_sha256` as returned by /result.

## Steps

1. Branch `feat/review-api` from current `origin/main`.
2. Settings classes, loaders, errors; `tests/test_review_settings.py`; `.env.example` names.
3. `production_registry(review_handler=None)`, `DatabaseJobStore.session_factory`, `review_wiring.py`, `__main__` changes and events; worker tests.
4. API `reviews.py`, `PublicMessage` members, `create_app` seam and router, `VIEWABLE_JOB_KINDS`; unit and PostgreSQL API tests; openapi test.
5. Update the pinned tests above; run ruff, ruff format check, mypy strict, the full pytest suite, and the integration suite against PostgreSQL 17 + pgvector (`EG_TEST_DATABASE_URL`).
6. Compose env, `container_ci` validate and smoke step, its tests, the ci.yml wheel block.
7. Docs: `docs/decisions/0027-production-review-path.md` from the draft below; docstrings in reviews.py, review_outputs.py, review_seams.py and review.py that say "unregistered"; one CHANGELOG line. Do not edit `docs/plan.md`, `prompts.md` or the README status sections.
8. Commit with explicit paths and why-bodies, push the branch, report the counts. The orchestrator opens the PR.

## Completeness checklist

- No production path builds a fake provider.
- Key is SecretStr, read only by the worker, never logged or echoed.
- Unset provider: no `run_review` claim, POST 503.
- Partial configuration: exit 3 before the database.
- Tenant only from actor; extra body fields 422.
- Idempotent replay returns the original review.
- Every pin change carries a `# W8:` comment.
- CI makes no network call; wheel and smoke updated.
- ADR 0027 and CHANGELOG updated.
- Money, migrations, UI, deploy: n/a.

## Pre-mortem

- Worker claims nothing because EG_REVIEW_PROVIDER is set only on the API: the `worker.review_enabled` and `review_disabled` startup events show it.
- A live alias returns a dated model and every stage ends as model_mismatch: require a dated id; the first live run in M7 is supervised.
- A text pin was loosened too broadly and a later change wires a fake: allowlists name exact files, plus the scripted-provider packaging test.

## ADR 0027 draft: Production review path wiring

- **Status:** proposed (W8).
- **Context:** The W8 reconciliation requires enqueue, registration and provider configuration to arrive together; ADR 0025 requires a composition review for any production registration.
- **Decision:** EG_REVIEW_PROVIDER switches reviews on in both processes; EG_REVIEW_MODEL is pinned into each review's configuration digest at creation; EG_ANTHROPIC_API_KEY is read by the worker only; the worker registers `run_review` only with a fully valid configuration, built from `AnthropicProvider` over `HttpsAnthropicTransport` with `LoggingSpanSink`; the API creates reviews through the M5c loaders and `create_review`, and returns 503 when reviews are off.
- **Consequences:** production model calls become possible; config skew is visible as queued reviews; evidence and trace routes are deferred.
- **Why not:** the alternatives table above.
