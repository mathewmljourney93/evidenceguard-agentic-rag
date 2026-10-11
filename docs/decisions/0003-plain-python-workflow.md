# ADR-0003: Plain-Python workflow orchestration

- **Status:** Accepted
- **Date:** 2026-10-11
- **Records plan decisions:** D4, D5, D6, D7 and D9, and corrections B and E in [docs/plan.md](../plan.md). This ADR introduces no new architecture.

## Context

A review answers a fixed set of template questions about one vendor:

1. **Planner:** expands a versioned review template into bounded evidence questions.
2. **Retriever:** finds candidate passages from the tenant's documents.
3. **Evidence Verifier:** judges each question against the passages, with citations.
4. **Risk Analyst:** turns verified evidence into findings.
5. **Report Composer:** renders the draft report, including unresolved questions.
6. **Human Approval Gate:** an approver approves, rejects or finalizes an exact report revision.

The path through these steps is the same for every question. No step needs to decide which step comes next.

## Decision

### Orchestration
The workflow is ordinary Python code: a fixed sequence of named stages per question (`pending → retrieved → verified → analyzed`, or `failed`). Code, not a model, decides what runs next.

- Transitions are explicit and bounded. Each stage either produces its typed output or moves the question to `failed`.
- A failed question appears in the report as **unresolved**. It is never dropped and never shown as supported.
- Models receive no tools. They can only return a structured result for the stage that called them.

### Deterministic versus model-driven steps (D4, D5)
| Step | Approach |
|---|---|
| Planner | Deterministic template expansion |
| Retriever | Deterministic hybrid search over the review's snapshot of document revisions |
| Evidence Verifier | **Model**, returning a structured result that code then validates |
| Risk Analyst | **Model**, returning structured findings that code then validates |
| Report Composer | Deterministic rendering |
| Approval Gate, authorization, validation, state transitions | Deterministic |

Model calls will go through a typed provider interface. Each output is validated against the Pydantic contracts in `evidenceguard_domain.evidence`, for example `Verification` and `Finding`. Validation rejects any output that breaks the verdict/status/citation rules or tenant consistency. Code-side provenance checks are planned for M5: that each cited chunk was retrieved for the question and that each quote occurs in its chunk. Neither kind of check establishes semantic support or document authenticity.

### Durable jobs and workflow state (D7, corrections B and E), planned
- **Jobs.** Ingestion and reviews will run as PostgreSQL-backed jobs in a separate worker:
  - a worker claims a job with `FOR UPDATE SKIP LOCKED` and holds a lease, extended by heartbeats;
  - a job retries up to `max_attempts`, after which it is `dead`;
  - an expired lease can be reclaimed.
- **Stage state.** Each stage output will be stored under a unique key `(review_id, question_id, stage)`. A resumed review skips completed stages and reuses a provider response already stored under the same request hash.
- **Fencing.** Every write a job handler makes, including stage results and job completion, will first check that the job is still owned by this worker and attempt. A reclaimed, stale worker therefore cannot overwrite newer work.
- **Snapshots.** Each review will record the exact document revisions and configuration it uses, so later uploads don't change a running or resumed review.

### Bounds and failure handling (D9), planned
- Each model call has a 60 s timeout and 2 SDK retries. Each review has an attempt cap and a budget cap.
- Invalid structured output gets one repair attempt.
- A refusal, `max_tokens`, repeated invalid output or an exhausted budget leaves the question unresolved. There is no automatic fallback to another model.
- Database effects will be idempotent through unique keys and fenced writes. **Model calls are at-least-once.** A worker that crashes after receiving a response but before storing it will repeat the call on retry, which can duplicate cost. Exactly-once model calls are not promised.

### Human approval
Approval, rejection and finalization are bound to the exact report revision number **and** its SHA-256 content hash:
- any new revision removes the effective approval;
- only a finalized report can be exported;
- an identical retry changes nothing, and a changed retry is refused as a conflict.

## What exists today and what is planned

| Part | Status |
|---|---|
| Evidence contracts, verdict/status/citation rules, report coverage rules | **Implemented and unit-tested** (M1b, `evidenceguard_domain.evidence`) |
| Report revisions, content hashing, approval transitions | **Implemented and unit-tested as pure functions** (M1b, `evidenceguard_domain.report` and `.approval`). Not yet persisted or exposed through the API. |
| Request IDs, logging, problem+json errors | **Implemented and tested** (M1c, ADR-0002) |
| Planner, retriever, verifier, analyst, report composer, the per-question stage machine | **Planned** (M4–M5) |
| PostgreSQL jobs, leases, fencing, stored stage outputs, review snapshots | **Planned** (M2–M5) |
| Model provider interface, Claude calls, timeouts, retries, budgets | **Planned** (M5) |
| Database atomicity and concurrency control for approval transitions | **Planned** (with persistence). The pure functions give none. |

The status rows describe local verification on Windows. Linux and GitHub Actions have not run. Nothing here claims crash recovery, concurrency safety, provenance checking or evaluation results; those claims will need their own tests and committed evidence when the planned parts exist.

## Why not a dedicated agent framework

Graph and agent frameworks such as LangGraph are capable options. They can express fixed, linear workflows as well as branching ones, persist workflow state through checkpointing, and pause for human intervention. This decision is not that such a framework couldn't run this workflow. It is a project-specific choice for the initial scope:
- **The initial workflow is small and bounded.** It is a fixed sequence of stages per question, with no model-chosen steps or tools. It can be expressed directly as Python functions over typed contracts, without a graph abstraction.
- **We chose explicit storage.** Workflow state will live in our own PostgreSQL tables: jobs, stage outputs keyed by `(review_id, question_id, stage)`, and review snapshots. Tenant scoping, fencing and the approval binding are written into those tables and queries, where reviewers can read them directly.
- **Fewer dependencies.** Without a framework there is one less runtime to learn, pin, upgrade and keep consistent with our own tenancy and fencing rules.
- **Testability.** Plain functions are exercised directly by unit tests with a scripted fake provider.

**The cost of this choice:** we must implement and test job recovery, stage resumption, retries and fencing ourselves, including the crash and concurrency cases a mature framework may already handle. None of that exists yet. It is planned for M3–M5 and must be proven by tests before it is claimed.

## Alternatives considered

| Alternative | Why not now | Tradeoff accepted |
|---|---|---|
| Agent or graph framework such as LangGraph | It could run this workflow, with its own checkpointing and human-in-the-loop support. For the initial bounded scope we prefer plain Python with state in explicitly designed PostgreSQL tables and one fewer dependency. | We write and test job recovery, stage resumption and fencing ourselves |
| A model-driven agent loop with tools (the model decides what to retrieve next) | Harder to bound, reproduce and evaluate. A wrong tool call could cross the boundaries that code enforces today. | Retrieval quality depends on template queries rather than adaptive search |
| A workflow engine such as Temporal, or a task queue such as Celery | Needs extra infrastructure. Celery's usual broker, Redis, is excluded from v1. | PostgreSQL job claiming must be built and tested, and its throughput is unmeasured |
| A hosted agent service | Moves orchestration and data handling outside the project's control and review | No managed retries or observability; we build the minimum ourselves |

## When to reconsider

Revisit this decision if any of these becomes true:
- **Model-driven routing becomes a requirement.** For example, the reviewer approves letting the model choose further retrieval or tools, so control flow is no longer fixed.
- **Human pauses within a review.** The workflow needs human input in the middle of a review, not only at the final approval gate.
- **The stage machine stops being simple.** Conditional branches multiply until the explicit stage code is harder to review than a declarative graph.
- **The queue becomes a measured bottleneck.** Load tests with committed results show PostgreSQL job claiming limits throughput or reliability at the required scale.
- **A long-running process spans services.** It must coordinate several services, where a dedicated engine's guarantees would replace substantial custom code.

Any replacement must keep the same guarantees: bounded steps, validated structured outputs, tenant isolation, fenced idempotent writes, and approval bound to the exact revision and hash.
