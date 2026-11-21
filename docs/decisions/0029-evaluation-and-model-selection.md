# ADR-0029: Evaluation harness and model selection

- **Status:** proposed (M7). Implemented on branch `feat/evaluation-harness`; pending review.
  No live run has been made: the owner's spend cap is $0 (2026-11-20).
- **Plan:** [`docs/plans/feat-evaluation.md`](../plans/feat-evaluation.md) (PR A).

## Context

D10 requires measured model selection against thresholds agreed in advance. Section 7 of
`docs/plan.md` defines the metrics and evaluation independence. The review handler lives in the
worker, and packages may not import applications. The owner set the spend cap to $0 for v0.1,
so the live runs, the annotation workflow and the Verifier probe are deferred.

## Decision

- **Pure package** `evidenceguard_evaluation`: selection file, pricing, budget guard, run
  records, metrics, contract scripts, report and the argument parser. It imports packages only;
  only `contract.py` imports the scripted fake and only `budget.py` the provider protocol.
- **Composition root** `evidenceguard_worker.evaluation_run`: `eg-eval` points there. It runs the
  real W8 review handler (`build_review_handler`) in-process against an empty `_eval` database
  (`require_disposable_database`, generalised from the test guard) seeded by the M4e loader. It
  never drops anything.
- **Contract suite** in CI: the scripted fake in a refusal phase and a scripted phase per pair,
  with four fixed traps; stamped "NOT a quality measurement".
- **Live suite**: hash embeddings (the shipped W8 path), prices from `pricing.toml` with a
  required `as_of`, and a worst-case `BudgetGuard`. Thresholds, the cap and the annotation mode
  live in a committed `selection.toml`; a zero remaining cap refuses with exit 4 before any other
  check. Allowlisted records under `docs/evaluation/runs`; README figures only from them.
- **Annotation and probe**: not built in PR A (no live outputs can exist at a $0 cap); the
  metrics they feed exist as pure functions and print "not measured: no labels".

## Consequences

Reproducible, auditable model choice once a cap exists; Voyage quality stays unmeasured; small n
gives wide intervals, reported as such. At v0.1 the M7 acceptance items "live runs and
annotations are committed" and the D10 choice are not met.

| Option | Why not |
|---|---|
| Choose a default model in advance | Violates D10 |
| HTTP-driven harness | More moving parts, no extra coverage |
| Voyage in live runs | Not the shipped path; confounds the model choice |
| System or LLM self-grading as the reference | Breaks evaluation independence |
| Thresholds written after the runs | Lets results choose the thresholds |
| eg-eval in packages/evaluation | Would import apps |
| pricing.yaml with PyYAML | A new dependency; `tomllib` matches the corpus files |
| The command drops and recreates the schema | Destructive; an empty-database requirement suffices |
