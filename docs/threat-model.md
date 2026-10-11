# Threat model (initial draft, M1b)

**Status:** draft. This document grows with each milestone and must be complete before v0.1 ([plan](plan.md) correction F). It describes the planned system; most of it is **not implemented yet**.

## Scope and assets

EvidenceGuard helps a reviewer draft a vendor-risk report from uploaded vendor documents. The assets to protect are:
- each tenant's documents, evidence and reports;
- the integrity of report content and of the approval history;
- credentials (API keys, model-provider keys).

Only synthetic demonstration data is used.

## What is implemented and tested now (M1b)

These are **domain invariants** in `evidenceguard_domain`, enforced by validation and pure functions and covered by unit tests:

| Threat | Invariant |
|---|---|
| Evidence from one tenant appearing in another tenant's report | Citations, findings and report content must all carry the report's tenant ID; mixing tenants fails validation. |
| An actor acting on another tenant's report | Every transition checks that the actor's tenant matches the report's tenant. |
| Approving content that was never reviewed, or approving a stale revision | Approval names the exact current revision number and its SHA-256 content hash. Any mismatch is rejected. |
| Editing a report after approval and exporting it as approved | A new revision removes the effective approval. Finalization needs an approval of the exact current revision and hash. Only finalized reports are exportable. |
| Reusing an approval from another report, tenant or revision | Decisions are bound to tenant, report, revision and hash; the report aggregate rejects any decision that does not match. |
| Building an "approved" or "finalized" report object without a decision | The stored status must equal the status derived from the decision history. |
| Changing content after its hash was computed | Domain values are frozen and use tuples, not lists or dicts. `model_copy` re-validates. |
| Claiming support without evidence | Supported or conflicting statuses require citations; the status must match the cited source types. Conflicting evidence needs at least two distinct quotations. That is a structural check, not proof of a contradiction. |
| A report silently dropping a question it could not answer | Every question must be resolved by a finding or listed as unresolved. A vendor claim never resolves a question that requires documentary support. Any question named by a `missing` finding must be listed as unresolved, even if another finding supports it. |
| A rejection with no stated reason | Every rejection decision must carry a non-blank comment, including one built directly. |
| A retry quietly overwriting or discarding who decided what | Only an identical retry (same actor and comment) is idempotent, and it keeps the original decision and time. A changed request raises `DecisionConflictError` instead of being dropped or recorded twice. |
| Privilege escalation through an admin role | Only the approver role can approve, reject or finalize. There is no admin role or bypass. |

These invariants hold only for code that goes through the domain models and transitions. Pydantic's `model_construct` and `object.__setattr__` can bypass validation; domain code never uses them.

## Not implemented yet

- **Authentication.** `ActorContext` is trusted as given. Nothing yet derives it from a credential. Planned: hashed per-user API keys (M2).
- **Database tenancy.** No database exists. Planned: composite `(tenant_id, id)` foreign keys and tenant-filtered queries (M2), with row-level security as a later enhancement.
- **Atomic, concurrent-safe transitions.** The transitions are pure functions. Two simultaneous requests could both pass validation; persistence must serialize them (for example with a row lock or compare-and-set on revision and hash).
- **Upload limits and untrusted-file handling** (M3).
- **Provenance checks:** that a cited chunk was actually retrieved for the review and that the quote occurs in it (M5).
- **Log redaction and secret handling in code** (observability, still pending in M1).

## Open risks

- **Prompt injection.** Uploaded documents are untrusted and may contain instructions aimed at the model. The planned mitigations (delimited evidence, no model tools, validated structured output, human approval) reduce but cannot eliminate the risk. Paired clean/injected evaluation is planned for M7; nothing is measured yet.
- **Semantic support.** No component yet checks whether a cited passage actually supports a claim. That needs model judgment plus human review.
- **Document authenticity.** Not established anywhere in v1 (see [responsible-ai.md](responsible-ai.md)).
- **Secrets in the repository.** Mitigated by Gitleaks locally and in CI. The CI workflows have not yet run on GitHub.
