# Plan: feat/approval-gate (M6 approval gate and export)

- **Tier:** critical (migration 0009, roles, new routes, append-only audit)
- **Author / model:** planner agent, Claude Opus 5.5, highest effort (the most capable model available to the session; Fable was unavailable). Owner decisions settled by the orchestrator, Claude Opus 5.5.
- **Date:** 2026-11-20
- **Status:** agreed (orchestrator under Mathew's written delegation, 2026-11-20)
- **Decision record:** ADR 0028 (draft at the end, written to `docs/decisions/0028-approval-gate-and-export.md` in the PR)
- **Base:** main after the agreement PR (#1) and the W8 PR, whichever have merged when the build starts

## Goal

Expose the stored review output as a report with immutable hash-bound revisions, approval or rejection, finalization and export, under `/v1/reports`. This meets the M6 acceptance criteria (docs/plan.md M6 block), the API rows at docs/plan.md:348-352, the report-integrity invariant at :7167-7189 and the F11 handover at :12164-12169. Acceptance tests A1 to A4 below.

## Existing code found

- Pure legacy transitions: `evidenceguard_domain/approval.py` (create_draft :97, approve :118, reject :154, revise :193, finalize :225, exportable_revision :257, `_EDITORS`/`_APPROVERS` :49-50). Aggregate in `report.py` (ReportStatus :49, ReportRevision :61, ApprovalDecision :97, Finalization :134, Report :145). Errors in `errors.py`. These bind the **legacy** digest `evidenceguard.report-content.v1`. F11 forbids feeding the wrapper digest into them, so they stay unchanged.
- Wrapper: `report_content.py` SCHEMA/RENDERER/LEGACY_SCHEMA :62-64, `ReviewReportContent`, `decode_review_report(data, *, expected_sha256)` :982. Renderer: `evidenceguard_agents/report.py:299 render_report_markdown`.
- Output row: `models.py:1339 ReviewOutputRow` (PK tenant_id, review_id; write-once). Persistence `review_outputs.py`: `load_review_output` :823 (full strict read, role check via READ_ROLES :105).
- API patterns: `auth.py:88 authenticated_actor`, role dependency `vendors.py:128-134`, 409 mapping `vendors.py:191`, `documents.py:552`, app factory seams `app.py:23-90`. No ETag or If-Match code exists.
- Layering (`tests/test_packaging.py:50-107`): persistence may not import agents; the API may import agents and persistence.
- Test harness: `tests/conftest.py:187 migrated`, `tests/review_postgres_world.py` (`review_world`, `provider`, `ReviewWorld.run`), in-memory `Keys` authenticator in `tests/test_document_api_postgres.py:130`, migration test pattern in `tests/test_review_handler_postgres.py:430`.

## Approach

1. **Report identity.** `report_id == review_id`, 1:1, enforced by CHECK. No lookup table; two reports can never exist for one review.
2. **Creation: lazy, on first access to any `/v1/reports/{id}` route**, not in the worker. Revision 1 is a pure function of the write-once `review_outputs` row (wrapper bytes and digest, finding order), so every creator produces byte-identical rows; `INSERT ... ON CONFLICT DO NOTHING` plus a re-select makes creation idempotent and race-safe. The reviewed M5g fenced finish transaction stays untouched. Materialization first calls `load_review_output` (full M5g read checks), then inside the report transaction re-reads the row `FOR SHARE` and requires the same `wrapper_sha256`.
3. **New schema-dispatched values** (F11) in a new domain module. Revision content schema `evidenceguard.review-report-revision.v1` binds tenant, report, review, the base wrapper schema and renderer, and the exact `base_wrapper_sha256`. The revision hash covers the wrapper hash, so approving revision n covers the exact wrapper bytes.
4. **What a reviser may change.** One disposition per wrapper finding (`open`, `accepted` or `dismissed`; a dismissal requires a note), an optional per-finding note, optional report notes. Machine conclusions (findings, statuses, quotes, unresolved reasons) are never edited: they live in the hashed wrapper. Dismissed findings stay in the export, marked dismissed.
5. **Canonical rules.** Bytes are `json.dumps({"schema": REVISION_SCHEMA, "content": content.model_dump(mode="json")}, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)`, dispositions in wrapper finding order. Hash is SHA-256 hex of those bytes. Stored as printable ASCII text, decoded strictly (re-encoding must equal the stored bytes).
6. **ETag and If-Match.** ETag `"r{n}-{sha}"`, strong only. POST revisions requires exactly one If-Match matching `^"r([1-9][0-9]{0,2})-([0-9a-f]{64})"$`: missing is 428, malformed is 422, non-current number or hash is 409.
7. **Concurrency.** Each mutation is one transaction: materialize, `SELECT ... FOR UPDATE` on `reports`, rebuild the aggregate from its rows, apply the pure transition, insert new rows, update the `reports` pointers, insert one audit event. An identical retry of approve or finalize returns the unchanged state and writes nothing.
8. **Separation of duties.** An approver may revise, but may not approve or finalize a revision whose `created_by` is themselves. Revision 1 (generated, `created_by` null) may be approved by any approver. Violations are 409 (InvalidTransitionError, message "approver authored this revision").
9. **Export.** Only a finalized report. Source is the stored revision bytes and the stored wrapper bytes (`decode_review_report`), rendered by `render_report_markdown`; no reads of stage or plan tables. Persistence receives a `render` callback from the API (persistence may not import agents). The audit event stores the format and the SHA-256 of the exact body, in the same transaction, committed before the response is sent.
10. **Audit.** One tenant-scoped `audit_events` table: actions revise, approve, reject, finalize, export. A DB trigger rejects UPDATE, DELETE and TRUNCATE; the same trigger guards `report_revisions`, `report_decisions`, `report_finalizations`. `reports` rejects DELETE and TRUNCATE only (its status and pointers change).

## Settled decisions (formerly open)

- Missing If-Match: 428. Revision identical to the current one: 409. Stale If-Match: 409 (docs/plan.md:349), not 412.
- No separate "generate" audit action; the revision 1 row records its creation (origin `generated`).
- Revision cap: 100 per report; the 101st is 409.
- Separation of duties as in Approach 8.

## Changes from the plan (2026-11-20)

Recorded after the first independent review. Each item is what the build does where it differs
from the sections below.

- **`ExportInput` and `ExportResult` live in the domain module** (`review_report_approval.py`),
  not in persistence. The agents renderers need them, and the agents package may not import
  persistence (`tests/test_packaging.py`). Persistence re-exports both names.
- **Two errors added beyond the plan's list.** `ReportRecordInconsistentError` (persistence)
  is raised when stored report rows do not rebuild into a valid report bound to their output, or
  when a rendered export's declared digest differs from its body; the API maps it to 503.
  `InvalidRevisionContentError` (domain) is raised when requested dispositions or notes do not
  form a valid revision, and by `decide_report` for a rejection without a comment (checked before
  any SQL); the API maps it to 422. No reachable persistence path raises a bare `ValueError` to the API. The one remaining
  `ValueError` (unsupported export format in `reports.py`) cannot be reached, because the route
  accepts only `md` or `json` and answers 422 to anything else.
- **Unqualified `ON CONFLICT DO NOTHING`** on the `reports` insert (no conflict target). Both
  unique constraints on `reports`, the primary key `(tenant_id, id)` and
  `(tenant_id, id, base_wrapper_sha256)`, contain `(tenant_id, id)`, so any conflict either can
  raise means the same report already exists, which is exactly the case to skip. A simultaneous
  creator may meet either constraint first, so naming one target could still raise on the other.
  Proven by `test_concurrent_first_reads_create_one_report` (two creators meet at a barrier on
  the insert; one report, one revision).
- **Explicit short trigger names.** Row triggers `eg_<table>_append_only` (BEFORE UPDATE OR
  DELETE) on the four history tables; statement triggers `eg_<table>_no_truncate`; on `reports`,
  `eg_reports_no_delete` and `eg_reports_no_truncate`. Ten triggers in total, one function.
- **Narrow exceptions in the packaging guards** (`tests/test_packaging.py`), each limited to one
  package and one file name: `agents/report_export.py` (the export renderers) is allowed to
  exist beside the other agents modules and to carry the disclaimer wording; the API's
  `reports.py` is exempt from the check that keeps the API off the renderers and from the check
  on mapping stored-output read errors; persistence's `reports.py` is exempt from the check on
  decoding stored wrapper bytes.
- **Offline migration tests.** The existing offline tests for 0003 and 0005 in
  `tests/test_persistence.py` now render up to `0008` instead of head, because 0009 adds
  triggers and a function that those assertions do not describe. 0009 has its own offline tests
  in `tests/test_report_migration.py`.
- **Head pins moved to 0009** in the existing tests that pin it (`test_persistence.py`,
  `test_persistence_postgres.py`, `test_readiness.py`, `test_review_stages_postgres.py`); the
  0008 model-constraint test in `test_review_output_values.py` allows the one unique 0009 adds
  to `ReviewOutputRow`.
- **`approval` in the response** is the latest decision (approve or reject) when it is on the
  current revision, otherwise `null`. A revision after a decision therefore shows no approval.
- **`format` is required** on `GET /{report_id}/export` (`md` or `json`); a missing or other
  value is 422. The plan did not say whether it had a default.
- **Export reads under a share lock** (review fix). `export_report` locks the `reports` row
  `FOR SHARE` before rebuilding, so a finalize committing meanwhile is either fully visible or
  waits for the export. Without it, a READ COMMITTED export could read the report row from before
  a finalize and the finalization row from after its commit and return 503. Tests:
  `test_an_export_that_read_the_report_first_makes_a_racing_finalize_wait` (409, then the
  finalize commits) and `test_an_export_racing_a_finalize_that_holds_the_report_waits_and_exports`
  (200).
- **Export digest check** (review fix). A rendered export whose declared digest differs from its
  body raises `ReportRecordInconsistentError` (503) and records nothing; tested in
  `tests/test_reports_persistence.py` and
  `test_an_export_whose_rendered_digest_differs_is_inconsistent_and_not_recorded`.
- **Threat model** (review fix): one limit line on audit growth per export.

## Migration 0009 (`migrations/versions/v0009_report_approval.py`, revision "0009", down_revision "0008")

Plain DDL; check text spelled out as in 0008. If W8 adds a migration first, renumber to the next free number and set down_revision accordingly.

- **`review_outputs`:** add unique `uq_review_outputs_tenant_id_review_id_wrapper_sha256 (tenant_id, review_id, wrapper_sha256)`. Additive.
- **`reports`:** tenant_id, id, review_id, base_schema_id, base_renderer_id, base_wrapper_sha256, status, current_revision_no, current_content_sha256, created_at, updated_at. PK (tenant_id, id); CHECK id = review_id; FK (tenant_id, review_id, base_wrapper_sha256) to that new unique. CHECKs: status in the 4 values; current_revision_no BETWEEN 1 AND 100; sha regex; schema/renderer literals. Unique (tenant_id, id, base_wrapper_sha256).
- **`report_revisions`:** tenant_id, report_id, revision_no, schema_id, base_wrapper_sha256, content_canonical text, content_sha256, origin, created_by uuid null, reason text null, created_at. PK (tenant_id, report_id, revision_no); unique (tenant_id, report_id, revision_no, content_sha256); FK (tenant_id, report_id, base_wrapper_sha256) to reports. CHECKs: origin in ('generated','revised'); `(origin = 'generated') = (created_by IS NULL)`; `(origin = 'generated') = (revision_no = 1)`; ASCII-printable and size checks as in 0008 (max 1048576 bytes); reason length 1 to 500 when present.
- **`report_decisions`:** tenant_id, report_id, decision_no smallint, revision_no, content_sha256, decision, decided_by, comment, decided_at. PK (tenant_id, report_id, decision_no); FK (tenant_id, report_id, revision_no, content_sha256) to the revisions unique; unique (tenant_id, report_id, decision_no, revision_no, content_sha256). CHECKs: decision in ('approve','reject'); reject requires a non-blank comment.
- **`report_finalizations`:** PK (tenant_id, report_id); revision_no, content_sha256, decision_no, finalized_by, finalized_at; FK (tenant_id, report_id, decision_no, revision_no, content_sha256) to the decisions unique.
- **`audit_events`:** id bigint GENERATED ALWAYS AS IDENTITY PK, tenant_id FK tenants, report_id, action, actor_id, revision_no, content_sha256, export_format null, export_sha256 null, occurred_at default clock_timestamp(). FK (tenant_id, report_id, revision_no, content_sha256) to the revisions unique. CHECKs: action in the 5 values; `(action = 'export') = (export_format IS NOT NULL AND export_sha256 IS NOT NULL)`; export_format in ('md','json'). Index (tenant_id, report_id, id).
- **Triggers:** function `eg_reject_append_only_change()` raising `USING ERRCODE = 'restrict_violation'`; triggers `eg_<table>_append_only` BEFORE UPDATE OR DELETE FOR EACH ROW plus BEFORE TRUNCATE FOR EACH STATEMENT on the four history tables; `reports` gets BEFORE DELETE and TRUNCATE.
- **Downgrade:** drop triggers and function, tables in reverse FK order, then the new review_outputs unique.
- All FKs NO ACTION, no cascades. Models in `models.py` mirror every column and constraint so `alembic check` passes; triggers are migration-only.

## Code changes (signatures)

### Domain: `packages/domain/evidenceguard_domain/review_report_approval.py` (new; legacy approval.py untouched)

- `REVISION_SCHEMA = "evidenceguard.review-report-revision.v1"`; `class Disposition(StrEnum)`: OPEN, ACCEPTED, DISMISSED.
- `class FindingDisposition(DomainModel)`: `finding_id: UUID`, `disposition: Disposition`, `note: str | None` (1 to 2000 chars, stripped; required when DISMISSED).
- `class RevisionContent(DomainModel)`: `tenant_id`, `report_id`, `review_id: UUID`, `base_schema_id: Literal[SCHEMA]`, `base_renderer_id: Literal[RENDERER]`, `base_wrapper_sha256: Sha256Hex`, `dispositions: tuple[FindingDisposition, ...]` (max 200), `notes: str | None` (1 to 4000).
- Codec: `revision_canonical_bytes(content) -> bytes`; `revision_sha256(content) -> str`; `decode_revision_content(data: bytes, *, expected_sha256: str) -> RevisionContent`; `initial_content(wrapper: ReviewReportContent, *, wrapper_sha256: str) -> RevisionContent` (all OPEN, notes None, report_id = review_id).
- Aggregate: `WrapperRevision` (schema_id Literal[REVISION_SCHEMA], report_id, revision_number, content, content_sha256, `created_by: UUID | None`, created_at; validates the hash; `created_by` is None iff revision 1). `WrapperApprovalDecision`, `WrapperFinalization`: legacy fields plus `schema_id`. `WrapperReport`: tenant_id, report_id, review_id, base_wrapper_sha256, `finding_ids: tuple[UUID, ...]`, status, revisions, decisions, finalization; validators mirror `Report._check_history`, plus every revision binds tenant, report, review and base wrapper, and its disposition finding ids equal `finding_ids` in order.
- Transitions (check order as approval.py; reuse ReportStatus, Decision and errors): `open_report(wrapper, *, wrapper_sha256, now)`; `revise(report, ctx, *, expected_revision_number, expected_sha256, dispositions, notes, now)` (identical content raises InvalidTransitionError); `approve(report, ctx, *, revision_number, content_sha256, now, comment=None)`; `reject(..., comment: str)`; `finalize(report, ctx, *, revision_number, content_sha256, now)`; `exportable_revision(report, ctx) -> WrapperRevision`. Role sets: editors {REVIEWER, APPROVER}; approvers {APPROVER}; ADMIN in neither (ADR 0005). approve, reject and finalize refuse when the target revision's `created_by` equals the actor (Approach 8).

### Persistence: `packages/persistence/evidenceguard_persistence/reports.py` (new)

- `ReportState(report: WrapperReport, wrapper: ReviewReportContent, wrapper_sha256: str)` with `etag -> str`; `ReportNotFoundError`; `ExportInput(state, revision, approval, finalization)`; `ExportResult(body: bytes, media_type: str, export_sha256: str)`.
- `load_report(session_factory, actor, report_id) -> ReportState`; `revise_report(session_factory, actor, report_id, *, expected_revision_number, expected_sha256, dispositions, notes, reason) -> ReportState`; `decide_report(session_factory, actor, report_id, *, revision_number, content_sha256, decision: Decision, comment) -> ReportState`; `finalize_report(session_factory, actor, report_id, *, revision_number, content_sha256) -> ReportState`; `export_report(session_factory, actor, report_id, *, export_format: Literal["md","json"], render: Callable[[ExportInput], ExportResult]) -> ExportResult`.
- Each starts with `SET LOCAL statement_timeout` as in review_outputs.py. A role outside READ_ROLES raises PermissionDeniedError before any SQL.

### Agents: `packages/agents/evidenceguard_agents/report_export.py` (new)

- `EXPORT_DISCLAIMER` (AI-assisted; citations prove provenance only, not entailment or authenticity; not legal advice or certification). `EXPORT_MD_RENDERER = "evidenceguard.report-export-markdown.v1"`; `EXPORT_JSON_SCHEMA = "evidenceguard.report-export.v1"`.
- `render_export_markdown(i: ExportInput) -> ExportResult`: header (report and review id, revision_no, content_sha256, wrapper_sha256, schema ids, approver id and time, finalizer and time), the disclaimer, dispositions and notes as escaped literals (same escaping as `render_report_markdown`), then `render_report_markdown(wrapper)`.
- `render_export_json(i) -> ExportResult`: canonical JSON with the same keys plus the decoded revision and wrapper objects.

### API: `apps/api/evidenceguard_api/reports.py` (new)

- Router prefix `/v1/reports`. Dependencies `report_reader` (REVIEWER or APPROVER, else 403) and `report_approver` (APPROVER, else 403). Protocol `ReportStore`, `DatabaseReportStore(database)`.
- Request models (extra=forbid): `ReportRevise{dispositions: list[DispositionIn], notes, reason}`; `ApprovalRequest{revision_no, content_sha256, decision: Literal["approve","reject"], comment}` (reject without comment is 422); `FinalizeRequest{revision_no, content_sha256}`.
- Response `ReportView` (ids, status, revision_no, content_sha256, wrapper_sha256, findings with disposition, notes, unresolved_question_ids, approval, finalization); every response carries the ETag header.
- Routes: `GET /{report_id}`; `POST /{report_id}/revisions` (201); `POST /{report_id}/approval` (200); `POST /{report_id}/finalize` (200); `GET /{report_id}/export?format=md|json` (attachment `report-{id}-r{n}.{ext}`; `text/markdown; charset=utf-8` and `application/json`).
- Errors: TenantMismatch, ReportNotFound, ReviewNotFound, ReviewOutputNotFound: 404. PermissionDenied: 403. Stale, ContentHashMismatch, InvalidTransition (including NotExportable, DecisionConflict, separation of duties): 409. ReviewOutputRecordInconsistent, database or configuration errors: 503.
- `app.py`: `report_store: ReportStore | None = None` in `create_app`, `app.state.report_store`, `include_router(reports_router)`. Additive next to W8's router.

## Tests

New `tests/test_reports_api_postgres.py`, `pytestmark = pytest.mark.integration`. Completes a review via `pw.review_world(...)` and `world.run(pw.provider(world.chunk_id))`, then an app with an in-memory `Keys` authenticator and `AppDatabase(lambda: engine)`.

Acceptance:

- **A1 (stale or wrong hash is 409):** `test_revise_with_a_stale_if_match_is_409`; `test_approve_with_a_stale_revision_or_wrong_hash_is_409` (parametrized stale, wrong_hash); `test_finalize_with_a_wrong_hash_is_409`.
- **A2:** `test_a_revision_after_approval_resets_to_draft_and_blocks_finalize` (approve r1, revise to r2 gives draft, finalize r1 gives 409, finalize r2 gives 409).
- **A3:** `test_export_before_finalize_is_409` (md and json, in draft and approved).
- **A4:** `test_a_reviewer_cannot_approve_reject_or_finalize_is_403`.

Supporting: `test_an_admin_gets_403_on_every_report_route`; `test_get_creates_revision_one_from_the_stored_output_with_etag`; `test_concurrent_first_reads_create_one_report`; `test_concurrent_revisions_with_the_same_if_match_one_201_one_409`; `test_missing_if_match_is_428_and_malformed_is_422`; `test_revise_a_finalized_report_is_409`; `test_repeated_identical_approval_and_finalize_are_idempotent_without_new_audit_events`; `test_approval_by_a_different_approver_is_409`; `test_an_approver_cannot_approve_their_own_revision_is_409`; `test_finalized_export_md_and_json_include_revision_hash_approver_and_disclaimer`; `test_export_reads_no_stage_or_plan_rows` (a `before_cursor_execute` hook asserts no SQL touches review_stage_results or review_plan_questions); `test_each_action_appends_one_audit_event_with_actor_revision_and_hash`; `test_history_and_audit_rows_reject_update_delete_and_truncate` (sqlstate 23001); `test_cross_tenant_report_is_404`; `test_a_review_without_output_is_404`; `test_migration_0009_downgrades_upgrades_and_matches_the_models`.

Unit: `tests/test_review_report_approval.py` (initial revision all open; hash matches an independent specimen; decode rejects noncanonical bytes and wrong digest; dispositions cover wrapper findings exactly once in order; dismissal needs a note; legacy decisions refused; reviewer cannot approve, reject or finalize; admin cannot revise, approve or export; revision after approval blocks finalization until reapproved; identical revision refused; approver cannot approve own revision; transitions do not mutate inputs). `tests/test_report_export.py` (markdown deterministic with binding and disclaimer; JSON canonical; reviewer text rendered as escaped literals). `tests/test_openapi.py`: extend `test_openapi_lists_every_route` with the five paths; add `test_openapi_documents_report_routes` (403, 409, 422, 428).

Every new test fails on base (modules missing; routes 404).

## Risks and rollback

- `alembic downgrade` of 0009 drops all report and audit data; fix forward with a new migration instead once reports exist.
- W8 also edits `app.py` and may edit `models.py`; keep both routers; ADR number 0028.
- Lazy creation makes GET write. Idempotent; reader role only.
- Database-level immutability depends on the runtime role not owning the tables; recorded as a limit in the threat model.

## Out of scope

W8 review routes, provider settings and run_review registration; worker changes; legacy approval.py and report.py; user management; PDF export; signed exports; the M7 evaluation.

## Steps

1. Branch `feat/approval-gate` from current `origin/main`.
2. Add `review_report_approval.py` and its unit tests. Run ruff, mypy strict, pytest (unit).
3. Add the models to `models.py`, plus the new unique on `ReviewOutputRow`.
4. Write migration 0009 and its migration test.
5. Add persistence `reports.py`.
6. Add agents `report_export.py` and its unit tests.
7. Add API `reports.py`, the `app.py` wiring and the OpenAPI updates.
8. Add `tests/test_reports_api_postgres.py`. Run the full suite and the integration suite against PostgreSQL 17 + pgvector (`EG_TEST_DATABASE_URL`), and `alembic check`.
9. Write `docs/decisions/0028-approval-gate-and-export.md` from the draft below; add a threat-model section for reports and audit (neutral wording, limits stated); add a CHANGELOG line.
10. Commit with explicit paths and why-bodies, push the branch, report the counts. The orchestrator opens the PR.

## Completeness checklist

- Evidence: each of A1 to A4 has a named test failing on base.
- Data: 0009 upgrade, downgrade, upgrade; `alembic check` clean.
- Tenant isolation: every query filters by actor tenant; cross-tenant test.
- Security: roles, separation of duties, append-only triggers, no stage reads on export.
- Integrity: export bytes derive only from stored hashed bytes; hash binding tested.
- Legacy approval.py, report.py and test_approval.py unchanged.
- Package import boundaries test passes.
- Docs: ADR 0028, threat model section, CHANGELOG.
- Money, dates, UI, deploy, backups: n/a (no money, timestamps are DB clock, no UI, no deploy).

## Pre-mortem

- Hash differs across processes: the canonical-bytes specimen test pins the bytes.
- Concurrent first read deadlocks or duplicates: ON CONFLICT DO NOTHING then FOR UPDATE, with a barrier test.
- Export drifts from approved content: export decodes stored bytes with expected digests; the test compares hashes.
- `alembic check` fails on identity or triggers: `Identity(always=True)` in the model; triggers are not autogenerate-visible.
- W8 merge breaks `app.py`: additive router include only.

## ADR 0028 draft: Approval gate and export

**Context:** F11 requires schema-dispatched wrapper revision and approval values bound to tenant, report, review and exact wrapper SHA-256; export must use the approved bytes only.

**Decision:** report id equals review id, created lazily from the write-once output; revision schema `evidenceguard.review-report-revision.v1` holding dispositions and notes over a hash-bound wrapper; compare-and-set under a row lock with ETag `"r{n}-{sha}"`; approver-only approve, reject and finalize, never on one's own revision; export only when finalized, rendered from stored bytes; append-only history and audit guarded by DB triggers.

| Option | Why not |
|---|---|
| Create revision 1 in the worker finish transaction | Widens the reviewed fenced M5g writer and conflicts with W8; lazy creation is deterministic, so creation time adds no integrity |
| Separate random report id | Needs a lookup table and allows two reports per review |
| Reuse legacy ReportRevision/ApprovalDecision with the wrapper digest | Forbidden by F11; silently changes the legacy digest meaning |
| Let revisions edit findings or wrapper content | Breaks wrapper validation and the integrity invariant |
| 412 for a stale If-Match | docs/plan.md:349 specifies 409 |
| Export by re-rendering from stage rows | Violates the invariant (:7187-7189) and F11 |
| Audit by application discipline only | No DB guard against UPDATE or DELETE |
| One generic audit JSON column | Loses FK binding of revision and hash |

**Consequences:** some duplication of legacy transition logic; GET can write; downgrade loses report data.
