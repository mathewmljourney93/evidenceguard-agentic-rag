# ADR-0028: Approval gate and export

- **Status:** implemented on branch `feat/approval-gate`; reviewed and CI-verified on the branch,
  to be accepted when merged.
- **Plan:** [`docs/plans/feat-approval-gate.md`](../plans/feat-approval-gate.md) (M6).

## Context

F11 requires schema-dispatched wrapper revision and approval values bound to tenant, report,
review and the exact wrapper SHA-256, and export must use the approved bytes only. The legacy
`approval.py` and `report.py` values bind the legacy digest `evidenceguard.report-content.v1`;
F11 forbids feeding the wrapper digest into them, so they stay unchanged.

## Decision

- **Identity.** The report ID equals the review ID (one report per review, enforced by a CHECK).
- **Creation.** Lazy, on the first access to any `/v1/reports/{id}` route, from the write-once
  `review_outputs` row. `load_review_output` runs the full M5g read checks first; inside the
  report transaction the output row is re-read `FOR SHARE` and must carry the same wrapper
  digest. Revision 1 is a pure function of that row, so `INSERT ... ON CONFLICT DO NOTHING`
  makes creation idempotent and race-safe. The worker's fenced finish transaction is untouched.
- **Revision values.** Schema `evidenceguard.review-report-revision.v1`
  (`evidenceguard_domain.review_report_approval`) holds one disposition per wrapper finding, in
  wrapper order (`open`, `accepted` or `dismissed`; a dismissal needs a note), optional notes per
  finding and for the report, and binds tenant, report, review, the wrapper schema and renderer,
  and the exact wrapper SHA-256. Machine conclusions are never edited; they live in the hashed
  wrapper. The revision hash is the SHA-256 of
  `json.dumps({"schema", "content"}, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
  allow_nan=False)`; stored as printable ASCII and decoded strictly (re-encoding must equal the
  stored bytes). Approving revision n therefore approves the exact wrapper bytes.
- **Compare-and-set.** ETag `"r{n}-{sha}"`, strong only. A revision requires exactly one
  `If-Match`: missing is 428, malformed is 422, a stale number or hash is 409. Each mutation is
  one transaction under `SELECT ... FOR UPDATE` on `reports`; an identical retry of approve,
  reject or finalize writes nothing. At most 100 revisions per report.
- **Roles.** Reviewers and approvers read, revise and export; only approvers approve, reject and
  finalize, and never a revision whose author is themselves (409). Revision 1 has no author.
  Administrators get 403 on every report route (ADR-0005).
- **Export.** Only a finalized report, as Markdown or canonical JSON, rendered from the stored
  revision and wrapper bytes (digest-checked on read) by `evidenceguard_agents.report_export`.
  Persistence receives a render callback, because it may not import the agents package. The
  export never reads stage or plan rows. The audit event stores the format and the SHA-256 of the
  exact body, in the same transaction, committed before the response is sent.
- **Audit and immutability.** One tenant-scoped `audit_events` table (revise, approve, reject,
  finalize, export), each row bound by foreign key to the exact revision and hash. A trigger
  function `eg_reject_append_only_change()` (fixed `search_path`, `SECURITY INVOKER`) rejects
  UPDATE, DELETE and TRUNCATE on `report_revisions`, `report_decisions`, `report_finalizations`
  and `audit_events`, and DELETE and TRUNCATE on `reports`, with SQLSTATE 23001.

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

## Consequences

- Some duplication of legacy transition logic in the new domain module.
- A GET can write (the first access creates revision 1). It is idempotent and needs the reader
  role.
- `alembic downgrade` of 0009 drops every report and audit row; once reports exist, fix forward
  with a new migration instead.
- Database-level immutability holds only while the runtime role does not own the tables (an
  owner or superuser can disable triggers). This is recorded as a limit in the threat model.
- `ExportInput` and `ExportResult` live in the domain module rather than in persistence, so the
  agents renderers can use them without importing persistence (package layering).
